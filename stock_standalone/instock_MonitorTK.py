# -*- coding:utf-8 -*-
import os
import gc
import sys
import time
import json
import threading
import multiprocessing as mp
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox,Menu,simpledialog
import warnings
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*"
)

import pandas as pd
import re
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from JohnsonUtil import inStockDb as inDb
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd
import win32pipe, win32file,win32api
from datetime import datetime, timedelta
import shutil
import ctypes
from ctypes import windll
import platform
from screeninfo import get_monitors
import pyperclip  # 用于复制到剪贴板
from stock_handbook import StockHandbook
from stock_live_strategy import StockLiveStrategy
from collections import deque

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import numpy as np
import hashlib
import sqlite3


# import matplotlib.pyplot as plt
# plt.ion()  # 开启交互模式
import hashlib

import argparse
import traceback

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
import configparser


class SafeLoggerWriter:
    #放置管道关闭时，Queue.put() 抛 WinError 232
    # 程序会报错，日志爆炸
    # 这是你最早遇到的问题
    def __init__(self, log_func):
        self.log_func = log_func
        self.alive = True

    def write(self, message):
        if not self.alive:
            return

        msg = message.strip()
        if not msg:
            return

        try:
            self.log_func(msg)
        except Exception:
            # logger 或 Queue 已关闭
            self.alive = False
            sys.__stdout__.write(msg + "\n")

    def flush(self):
        try:
            sys.__stdout__.flush()
        except:
            pass



class LoggerWriter:
    """将 print 重定向到 logger，支持 end= 与防递归"""
    def __init__(self, log_func):
        self.log_func = log_func
        self._working = False
        self._buffer = ""   # ⭐ stdout 缓冲

    def write(self, message):
        if not message:
            return

        if self._working:
            return

        try:
            self._working = True

            self._buffer += message

            # 按行拆分
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.strip()
                if line:
                    self.log_func(line)

        finally:
            self._working = False

    def flush(self):
        """程序结束时强制刷掉未换行内容"""
        if self._buffer.strip():
            self.log_func(self._buffer.strip())
            self._buffer = ""

def get_indb_df(days=10):
    indf = inDb.showcount(inDb.selectlastDays(days),sort_date=True)
    if len(indf) == 0:
        indf = inDb.showcount(inDb.selectlastDays(days+5),sort_date=True)
    return indf

def init_logging(log_file="appTk.log", level=LoggerFactory.ERROR, redirect_print=False, show_detail=True):
    """初始化全局日志"""

    logger = LoggerFactory.getLogger(
        name="instock_TK",
        logpath=log_file,
        show_detail=show_detail
    )
    logger.setLevel(level)

    if redirect_print:
        import sys
        sys.stdout = LoggerWriter(LoggerFactory.INFO)
        # sys.stdout = LoggerWriter(lambda msg: logger.log(level, msg))
        sys.stderr = LoggerWriter(LoggerFactory.ERROR)

    logger.info("日志初始化完成")
    return logger


def init_logging_noprint(log_file="appTk.log", level=LoggerFactory.ERROR, redirect_print=False, show_detail=True):
    """初始化全局日志"""
    logger = LoggerFactory.getLogger("instock_TK", logpath=log_file,show_detail=show_detail)

    logger.setLevel(level)

    # ⚠️ 可选重定向 print
    if redirect_print:
        import sys
        class LoggerWriter:
            def __init__(self, level_func):
                self.level_func = level_func
            def write(self, msg):
                msg = msg.strip()
                if msg:
                    self.level_func(msg)
            def flush(self):
                pass
        sys.stdout = LoggerWriter(level)
        sys.stderr = LoggerWriter(logger.error)

    logger.info("日志初始化完成")
    return logger

# 全局单例
logger = init_logging(log_file='instock_tk.log',redirect_print=False) 
# logger.handlers.clear()
# logger.setLevel(LoggerFactory.DEBUG)
# logger.setLevel(LoggerFactory.INFO)

# ✅ 性能优化模块导入
try:
    from performance_optimizer import (
        TreeviewIncrementalUpdater,
        DataFrameCache,
        PerformanceMonitor,
        optimize_dataframe_operations
    )
    PERFORMANCE_OPTIMIZER_AVAILABLE = True
    logger.info("✅ 性能优化模块已加载")
except ImportError as e:
    PERFORMANCE_OPTIMIZER_AVAILABLE = False
    logger.warning(f"⚠️ 性能优化模块未找到,将使用传统刷新方式: {e}")

# ✅ 股票特征标记模块导入
try:
    from stock_feature_marker import StockFeatureMarker
    FEATURE_MARKER_AVAILABLE = True
    logger.info("✅ 股票特征标记模块已加载")
except ImportError as e:
    FEATURE_MARKER_AVAILABLE = False
    logger.warning(f"⚠️ 股票特征标记模块未找到: {e}")


def df_hash(df: pd.DataFrame) -> str:
    """计算 DataFrame 的唯一哈希，用于一致性检测"""
    if df is None or df.empty:
        return "empty"
    # 转成字符串或二进制哈希
    h = pd.util.hash_pandas_object(df, index=True).sum()
    return hashlib.md5(str(h).encode()).hexdigest()[:8]  # 截取前8位

def init_logging_nopdb(log_file="appTk.log", level=LoggerFactory.ERROR):
    """初始化全局日志，避免重复打印"""
    logger = LoggerFactory.getLogger("instock_MonitorTK")  # 指定子 logger
    logger.setLevel(level)

    if not logger.handlers:  # 避免重复添加 handler
        formatter = LoggerFactory.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')

        # 文件 handler
        fh = LoggerFactory.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # 控制台 handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # 子 logger 不向 root logger 冒泡
    logger.propagate = True

    # 重定向 print
    sys.stdout = LoggerWriter(logger.info)
    sys.stderr = LoggerWriter(logger.error)

    # 捕获未处理异常
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("未捕获异常:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logger.info("日志初始化完成")
    return logger

conf_ini= cct.get_conf_path('global.ini')
if not conf_ini:
    print("global.ini 加载失败，程序无法继续运行")

CFG = cct.GlobalConfig(conf_ini)
marketInit = CFG.marketInit
marketblk = CFG.marketblk
scale_offset = CFG.scale_offset
resampleInit = CFG.resampleInit 
duration_sleep_time = CFG.duration_sleep_time
write_all_day_date = CFG.write_all_day_date
detect_calc_support = CFG.detect_calc_support
alert_cooldown = CFG.alert_cooldown

saved_width,saved_height = CFG.saved_width,CFG.saved_height
# def remove_condition_query(expr: str, cond: str) -> str:
def remove_invalid_conditions(query: str, invalid_cols: list,showdebug=True):
    """
    从 query 表达式中剔除包含无效列的条件（连带 and/or）
    """
    original_query = query
    # 为防止影响原始括号结构，去掉多余空格方便处理
    query = re.sub(r'\s+', ' ', query).strip()

    # 逐个无效列处理
    for col in invalid_cols:
        # 匹配各种形式：
        # and close > nclose
        # or close > nclose
        # (close > nclose)
        # close > nclose and
        # close > nclose or
        pattern = (
            rf'(\b(and|or)\s+[^()]*\b{col}\b[^()]*?)'  # 前面带 and/or
            rf'|(\([^()]*\b{col}\b[^()]*\))'          # 在括号内
            rf'|([^()]*\b{col}\b[^()]*\s+(and|or))'   # 后面带 and/or
            rf'|([^()]*\b{col}\b[^()]*)'              # 独立条件
        )

        def replacer(m):
            text = m.group(0)
            # 检查括号是否被完整包裹，如果是就删除整个子句
            if text.startswith("(") and text.endswith(")"):
                return ""
            # 如果前后是逻辑符号，删除逻辑符号连带条件
            return ""

        query = re.sub(pattern, replacer, query, flags=re.IGNORECASE)

    # 清理多余的空格与重复逻辑符号
    query = re.sub(r'\s+(and|or)\s+(\)|$)', ' ', query)
    query = re.sub(r'(\(|^)\s*(and|or)\s+', ' ', query)
    query = re.sub(r'\s{2,}', ' ', query).strip()

    # 检查括号平衡（自动修复）
    open_count = query.count("(")
    close_count = query.count(")")
    if open_count > close_count:
        query += ")" * (open_count - close_count)
    elif close_count > open_count:
        query = "(" * (close_count - open_count) + query
    if showdebug:
        logger.info(f"原始: {original_query}\n剔除后: {query}\n{'-'*60}")
    return query

# --- 辅助函数：DPI 处理（放在类的外面） ---

# Windows API 常量
LOGPIXELSX = 88
DEFAULT_DPI = 96.0

DB_PATH = "./concept_pg_data.db"

# --- SQLite 初始化 ---
def init_concept_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS concept_data (
            date TEXT,
            concept_name TEXT,
            init_data TEXT,
            prev_data TEXT,
            PRIMARY KEY (date, concept_name)
        )
    """)
    conn.commit()
    conn.close()

def save_concept_pg_data(win, concept_name):
    """保存每个概念当天数据到 SQLite，自动转换所有 NumPy 类型，并保留浮点数两位小数"""
    import numpy as np
    import sqlite3, json, traceback
    from datetime import datetime

    try:
        init_concept_db()
        date_str = datetime.now().strftime("%Y%m%d")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        def to_serializable(obj):
            """将 NumPy 类型自动转换为原生 Python 类型，并保留浮点数两位小数"""
            if isinstance(obj, np.ndarray):
                return [to_serializable(v) for v in obj.tolist()]
            elif isinstance(obj, (np.integer, np.int32, np.int64)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float32, np.float64, float)):
                return round(float(obj), 2)  # 保留两位小数
            elif isinstance(obj, dict):
                return {k: to_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [to_serializable(v) for v in obj]
            else:
                return obj

        base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
        prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)
        if base_data is None:
            logger.info(f'[save_concept_pg_data] base_data is None for {concept_name}')
            conn.close()
            return

        init_serial = to_serializable(base_data)
        prev_serial = to_serializable(prev_data) if prev_data else {}

        cur.execute("""
            INSERT INTO concept_data (date, concept_name, init_data, prev_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, concept_name)
            DO UPDATE SET
                init_data=excluded.init_data,
                prev_data=excluded.prev_data
        """, (
            date_str,
            concept_name,
            json.dumps(init_serial, ensure_ascii=False),
            json.dumps(prev_serial, ensure_ascii=False)
        ))

        conn.commit()
        conn.close()
        logger.info(f"[保存成功] {concept_name} 数据已写入 SQLite")
    except Exception as e:
        traceback.print_exc()
        logger.info(f"[保存失败] {concept_name} -> {e}")


def save_concept_pg_data_simple(win, concept_name):
    """保存每个概念当天数据到 SQLite（自动处理 ndarray -> list）"""
    try:
        init_concept_db()
        date_str = datetime.now().strftime("%Y%m%d")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 将 ndarray 转为 list
        def arr_to_list(a):
            return a.tolist() if isinstance(a, np.ndarray) else a

        base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
        prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)

        if not base_data:
            logger.info(f"[保存失败] {concept_name} base_data is None")
            conn.close()
            return

        init_data = {
            "concepts": base_data["concepts"],
            "avg_percents": arr_to_list(base_data.get("avg_percents", [])),
            "scores": arr_to_list(base_data.get("scores", [])),
            "follow_ratios": arr_to_list(base_data.get("follow_ratios", [])),
        }
        prev_data_dict = {
            "concepts": prev_data.get("concepts", []) if prev_data else [],
            "avg_percents": arr_to_list(prev_data.get("avg_percents", [])) if prev_data else [],
            "scores": arr_to_list(prev_data.get("scores", [])) if prev_data else [],
            "follow_ratios": arr_to_list(prev_data.get("follow_ratios", [])) if prev_data else [],
        }

        cur.execute("""
            INSERT INTO concept_data (date, concept_name, init_data, prev_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, concept_name)
            DO UPDATE SET
                init_data=excluded.init_data,
                prev_data=excluded.prev_data
        """, (date_str, concept_name,
              json.dumps(init_data, ensure_ascii=False),
              json.dumps(prev_data_dict, ensure_ascii=False)))

        conn.commit()
        conn.close()
        logger.info(f"[保存成功] {concept_name} 数据已写入 SQLite")
    except Exception as e:
        traceback.print_exc()
        logger.info(f"[保存失败] {concept_name} -> {e}")



def load_concept_pg_data_no_serializable(concept_name):
    """加载当天数据"""
    date_str = datetime.now().strftime("%Y%m%d")

    if not sqlite3.connect(DB_PATH):
        return None, None

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT init_data, prev_data FROM concept_data WHERE date=? AND concept_name=?",
                    (date_str, concept_name))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None, None

        init_data = json.loads(row[0]) if row[0] else None
        prev_data = json.loads(row[1]) if row[1] else None
        return init_data, prev_data
    except Exception as e:
        logger.info(f"[加载失败] {concept_name} -> {e}")
        return None, None

def load_all_concepts_pg_data():
    """
    一次性加载当天所有 concept 的 init_data 和 prev_data
    返回 dict: concept_name -> (init_data, prev_data)
    保证 init_data 和 prev_data 都是 dict，并且内部字段是 list
    """
    from datetime import datetime
    import sqlite3, json, traceback

    date_str = datetime.now().strftime("%Y%m%d")
    result = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT concept_name, init_data, prev_data FROM concept_data WHERE date=?", (date_str,))
        rows = cur.fetchall()
        conn.close()

        for concept_name, init_json, prev_json in rows:
            try:
                init_data = json.loads(init_json) if init_json else {}
                prev_data = json.loads(prev_json) if prev_json else {}

                # 补齐字段，保证一致性
                for key in ["concepts", "avg_percents", "scores", "follow_ratios"]:
                    init_data.setdefault(key, [])
                    prev_data.setdefault(key, [])

                result[concept_name] = (init_data, prev_data)
            except Exception:
                traceback.print_exc()
                logger.info(f"[加载单个概念失败] {concept_name}")
    except Exception as e:
        traceback.print_exc()
        logger.info(f"[加载全部概念失败] {e}")

    return result


# def load_all_concepts_pg_data():
#     """
#     一次性加载当天所有 concept 的 init_data 和 prev_data
#     返回 dict: concept_name -> (init_data, prev_data)
#     """
#     date_str = datetime.now().strftime("%Y%m%d")
#     result = {}
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cur = conn.cursor()
#         cur.execute("SELECT concept_name, init_data, prev_data FROM concept_data WHERE date=?", (date_str,))
#         rows = cur.fetchall()
#         conn.close()

#         for concept_name, init_json, prev_json in rows:
#             init_data = json.loads(init_json) if init_json else None
#             prev_data = json.loads(prev_json) if prev_json else None
#             result[concept_name] = (init_data, prev_data)
#     except Exception as e:
#         logger.info(f"[加载全部概念失败] {e}")
#     return result


# def set_process_dpi_awareness():
#     """强制设置进程的 DPI 意识级别，确保窗口不模糊。"""
#     try:
#         # Per-Monitor DPI Aware (2) - 推荐在 Windows 8.1/10/11 上使用
#         # SetProcessDpiAwareness(1) 对应的是 PROCESS_DPI_AWARENESS.PROCESS_SYSTEM_DPI_AWARE，即 System DPI Aware。
#         # SetProcessDpiAwareness(2) 对应的是 PROCESS_DPI_AWARENESS.PROCESS_PER_MONITOR_DPI_AWARE，即 Per-Monitor DPI Aware
#         # 无论是 (1) 还是 (2)，它们都会告诉 Windows：“我的程序会处理 DPI 缩放，不要对我的程序进行位图拉伸。”
#         ctypes.windll.shcore.SetProcessDpiAwareness(2)
#     except Exception:
#         try:
#             # System DPI Aware (1) - 备用
#             ctypes.windll.user32.SetProcessDPIAware()
#         except Exception:
#             pass

def set_process_dpi_awareness():
    try:
        if sys.platform == "win32":
            # 对 Windows 10+ 启用 Per-Monitor DPI 感知
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("[DPI] 已启用 Per-Monitor DPI Aware")
    except Exception as e:
        logger.info(f"[DPI] 启用失败: {e}")

def set_process_dpi_awareness_Close():
    if sys.platform.startswith('win'):
        # 强制 DPI Unaware 模式 (值 0)
        # 这将允许 Windows / RDP 客户端负责拉伸
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(0)
        except:
            # 备用： SetProcessDPIAware() 实际上设置为 System Aware，所以最好避免
            pass 
            
        # 确保 Qt 不会启用自己的缩放
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0'
        os.environ['QT_QPA_PLATFORM'] = 'windows:dpiawareness=0' 
    
    # ... 然后再导入 PyqtGraph.Qt ...
def is_rdp_session():
    """
    检测当前是否通过远程桌面 (RDP) 连接。
    """
    SM_REMOTESESSION = 0x1000
    return bool(ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION))

def scale_tk_window_for_rdp(root, scale_factor=1.5):
    """在 RDP 环境下自动放大 Tk 窗口尺寸"""
    if is_rdp_session():
        w = int(root.winfo_width() * scale_factor)
        h = int(root.winfo_height() * scale_factor)
        root.geometry(f"{w}x{h}")
        logger.info(f"[RDP] 已按 {scale_factor} 缩放 Tk 窗口: {w}x{h}")

def monitor_rdp_and_scale(win, interval_ms=3000, scale_factor=1.5):
    """
    每隔 interval_ms 毫秒检测是否进入 RDP，
    若进入则自动放大窗口及字体。
    """
    if not hasattr(win, "_last_rdp_state"):
        win._last_rdp_state = is_rdp_session()

    current_state = is_rdp_session()
    if current_state != win._last_rdp_state:
        win._last_rdp_state = current_state

        if current_state:
            # --- 已切入 RDP 会话 ---
            logger.info(f"[RDP] 检测到远程登录，放大 Tk 窗口 scale={scale_factor}")
            try:
                win.tk.call('tk', 'scaling', scale_factor)  # 放大字体/UI
                w = int(win.winfo_width() * scale_factor)
                h = int(win.winfo_height() * scale_factor)
                win.geometry(f"{w}x{h}")
            except Exception as e:
                logger.info(f"[RDP] 调整窗口缩放失败: {e}")
        else:
            # --- 退出 RDP 回本地 ---
            logger.info("[RDP] 返回本地会话，恢复默认缩放")
            try:
                win.tk.call('tk', 'scaling', 1.0)
                w = int(win.winfo_width() / scale_factor)
                h = int(win.winfo_height() / scale_factor)
                win.geometry(f"{w}x{h}")
            except Exception as e:
                logger.info(f"[RDP] 恢复窗口缩放失败: {e}")

    # 继续检测
    win.after(interval_ms, lambda: monitor_rdp_and_scale(win, interval_ms, scale_factor))

def get_window_dpi_scale(window):
    try:
        hwnd = window.winfo_id()
        dpi = windll.user32.GetDpiForWindow(hwnd)
        return dpi / 96.0
    except Exception:
        return 1.0

def get_current_window_scale(tk):
    hwnd = tk.winfo_id()
    dpi = windll.user32.GetDpiForWindow(hwnd)
    
    scale = round(dpi / 96, 2)
    return dpi, scale

def get_windows_dpi_scale_factor():
    """
    获取 Windows 缩放因子：
    - 默认 DPI 96 -> scale 1.0
    - 如果远程桌面下未缩放返回 2
    - 返回 float
    """
    try:
        LOGPIXELSX = 88  # 获取水平 DPI
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        dc = user32.GetDC(0)
        dpi = gdi32.GetDeviceCaps(dc, LOGPIXELSX)
        user32.ReleaseDC(0, dc)
        scale = dpi / 96.0
        # 如果 scale == 1 且是远程桌面，则用 Tk 的效果（2倍）
        _is_rdp_session = is_rdp_session()
        logger.info(f'scale : {scale} is_rdp_session : {_is_rdp_session} os.environ.get("SESSIONNAME") : {os.environ.get("SESSIONNAME")}')
        if scale == 1.0 and _is_rdp_session:
            return 2.0
        return scale
    except Exception:
        return 1.0  # 默认

# ----------------------------------------------------
# 使用方法：
# ----------------------------------------------------



if sys.platform.startswith('win'):
    set_process_dpi_awareness()  # 假设设置为 Per-Monitor V2
    # 1. 获取缩放因子
    scale_factor = get_windows_dpi_scale_factor()
    # 2. 设置环境变量（在导入 Qt 之前）
    # 禁用 Qt 自动缩放，改为显式设置缩放因子
    # os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
    # os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1' 
    # os.environ['QT_FONT_DPI'] = '1'  # 这个设置通常无效或被忽略
    os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
    os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1' 
    # os.environ['QT_SCALE_FACTOR'] = str(scale_factor-0.25)


    # os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
    # os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0' 
    # os.environ['QT_QPA_PLATFORM'] = 'windows:dpiawareness=0'

    # 打印检查
    logger.info(f"Windows 系统 DPI 缩放因子: {scale_factor}")
    # logger.info(f"已设置 QT_SCALE_FACTOR = {os.environ['QT_SCALE_FACTOR']}")




# -------------------- 常量 -------------------- #
sort_cols, sort_keys = ct.get_market_sort_value_key('3 0')
DISPLAY_COLS = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,sort_cols[:2])

def get_base_path():
    """
    获取程序基准路径。在 Windows 打包环境 (Nuitka/PyInstaller) 中，
    使用 Win32 API 优先获取真实的 EXE 目录。
    """
    
    # 检查是否为 Python 解释器运行
    is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
    # 1. 普通 Python 脚本模式
    if is_interpreter and not getattr(sys, "frozen", False):
        # 只有当它是 python.exe 运行 且 没有 frozen 标志时，才进入脚本模式
        try:
            # 此时 __file__ 是可靠的
            path = os.path.dirname(os.path.abspath(__file__))
            logger.info(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
            return path
        except NameError:
             pass # 忽略交互模式
    
    # 2. Windows 打包模式 (Nuitka/PyInstaller EXE 模式)
    # 只要不是解释器运行，或者 sys.frozen 被设置，我们就认为是打包模式
    if sys.platform.startswith('win'):
        try:
            # 无论是否 Onefile，Win32 API 都会返回真实 EXE 路径
            real_path = cct._get_win32_exe_path()
            
            # 核心：确保我们返回的是 EXE 的真实目录
            if real_path != os.path.dirname(os.path.abspath(sys.executable)):
                 # 这是一个强烈信号：sys.executable 被欺骗了 (例如 Nuitka Onefile 启动器)，
                 # 或者程序被从其他地方调用，我们信任 Win32 API。
                 logger.info(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
                 return real_path
            
            # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
            if not is_interpreter:
                 logger.info(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
                 return real_path

        except Exception:
            pass 

    # 3. 最终回退（适用于所有打包模式，包括 Linux/macOS）
    if getattr(sys, "frozen", False) or not is_interpreter:
        path = os.path.dirname(os.path.abspath(sys.executable))
        logger.info(f"[DEBUG] Path Mode: Final Fallback. Path: {path}")
        return path

    # 4. 极端脚本回退
    logger.info(f"[DEBUG] Path Mode: Final Script Fallback.")
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def load_display_config_ini(config_file, stock_data, code, name, close, boll, signal_icon, breakthrough, strength):
    """
    根据自定义 ini 文件生成 lines 和 colors
    """
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")

    lines = []
    colors = []

    placeholders = {
        'code': code,
        'name': name,
        'close': close,
        'ratio': stock_data.get('ratio', 'N/A'),
        'volume': stock_data.get('volume', 'N/A'),
        'red': stock_data.get('red', 'N/A'),
        'boll': boll,
        'signal_icon': signal_icon,
        'upper': stock_data.get('upper', 'N/A'),
        'lower': stock_data.get('lower', 'N/A'),
        'breakthrough': breakthrough,
        'strength': strength
    }

    # 按顺序遍历 lines
    for key in sorted(config['lines'], key=lambda x: int(x.replace('line',''))):
        line_template = config['lines'][key]
        line_text = line_template.format(**placeholders)
        color_value = config['colors'].get(key, 'black')  # 默认黑色
        lines.append(line_text)
        colors.append(color_value)

    return lines, colors

BASE_DIR = get_base_path()
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def get_conf_path(fname,BASE_DIR=BASE_DIR):
    """
    获取并验证 stock_codes.conf

    逻辑：
      1. 优先使用 BASE_DIR/stock_codes.conf
      2. 不存在 → 从 JSONData/stock_codes.conf 释放
      3. 校验文件
    """
    # default_path = os.path.join(BASE_DIR, "stock_codes.conf")
    default_path = os.path.join(BASE_DIR, fname)

    # --- 1. 直接存在 ---
    if os.path.exists(default_path):
        if os.path.getsize(default_path) > 0:
            # logger.info(f"使用本地配置: {default_path}")
            return default_path
        else:
            logger.warning("配置文件存在但为空，将尝试重新释放")

    # --- 2. 释放默认资源 ---
    cfg_file = cct.get_resource_file(
        rel_path=f"{fname}",
        out_name=fname,
        BASE_DIR=BASE_DIR
    )

    # --- 3. 校验释放结果 ---
    if not cfg_file:
        logger.error(f"获取 {fname} 失败（释放阶段）")
        return None

    if not os.path.exists(cfg_file):
        logger.error(f"释放后文件仍不存在: {cfg_file}")
        return None

    if os.path.getsize(cfg_file) == 0:
        logger.error(f"配置文件为空: {cfg_file}")
        return None

    # logger.info(f"使用内置释放配置: {cfg_file}")
    if os.path.exists(cfg_file):
        return cfg_file
    else:
        logger.critical(f"资源文件不存在: {cfg_file}")
        return None
    return cfg_file

DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)

# WINDOW_CONFIG_FILE = os.path.join(BASE_DIR, "window_config.json")
# SEARCH_HISTORY_FILE = os.path.join(DARACSV_DIR, "search_history.json")
# MONITOR_LIST_FILE = os.path.join(BASE_DIR, "monitor_category_list.json")
# CONFIG_FILE = "display_cols.json"
# icon_path= get_conf_path("MonitorTK.ico")

SEARCH_HISTORY_FILE = get_conf_path("search_history.json",DARACSV_DIR)
WINDOW_CONFIG_FILE = get_conf_path("window_config.json",BASE_DIR)
WINDOW_CONFIG_FILE2 = get_conf_path("scale2_window_config.json",BASE_DIR)
MONITOR_LIST_FILE = get_conf_path("monitor_category_list.json",BASE_DIR)
CONFIG_FILE = get_conf_path("display_cols.json",BASE_DIR)
icon_path = get_conf_path("MonitorTK.ico",BASE_DIR)

if not icon_path:
    logger.critical("MonitorTK.ico 加载失败，程序无法继续运行")
# icon_path = os.path.join(BASE_DIR, "MonitorTK.ico")
# icon_path = os.path.join(BASE_DIR, "MonitorTK.png")

START_INIT = 0
# st_key_sort = '3 0'

DEFAULT_DISPLAY_COLS = [
    'name', 'trade', 'boll', 'dff', 'df2', 'couts',
    'percent', 'per1d', 'perc1d', 'ra', 'ral',
    'topR', 'volume', 'red', 'lastdu4', 'category'
]

# import ctypes

# try:
#     ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
# except Exception:
#     try:
#         ctypes.windll.user32.SetProcessDPIAware()  # Windows 7 fallback
#     except Exception:
#         pass
# 作用：告诉 Windows，这个程序会自己处理 DPI，因此系统不会强制缩放 Tkinter 窗口。
# 这能让 Tkinter 在高分屏和多屏之间的字体保持一致大小。 


def load_display_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"current": DEFAULT_DISPLAY_COLS, "sets": []}

def save_display_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_monitor_by_point(x, y):
    """返回包含坐标(x,y)的屏幕信息字典"""
    monitors = []
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long)
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_long),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_long)
        ]

    def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        rc = info.rcMonitor
        monitors.append({
            "left": rc.left,
            "top": rc.top,
            "right": rc.right,
            "bottom": rc.bottom,
            "width": rc.right - rc.left,
            "height": rc.bottom - rc.top
        })
        return 1

    MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int,
                                         ctypes.c_ulong,
                                         ctypes.c_ulong,
                                         ctypes.POINTER(RECT),
                                         ctypes.c_double)
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(monitor_enum_proc), 0)

    for m in monitors:
        if m['left'] <= x < m['right'] and m['top'] <= y < m['bottom']:
            return m
    # 如果没有匹配，返回主屏幕
    if monitors:
        return monitors[0]
    else:
        # fallback
        width, height = get_monitors_info()
        return {"left": 0, "top": 0, "width": width, "height": height}

# # 定义常量
# WM_MOUSEHWHEEL = 0x020E

# def enable_horizontal_mouse_wheel(widget):
#     """为 Treeview 或 Canvas 启用鼠标水平滚轮 (Windows only)"""
#     if not isinstance(widget, tk.Widget):
#         return

#     hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())

#     # 定义回调函数
#     def low_level_proc(hwnd, msg, wparam, lparam):
#         if msg == WM_MOUSEHWHEEL:
#             delta = ctypes.c_short(wparam >> 16).value
#             widget.xview_scroll(-int(delta / 120), "units")
#             return 0  # 已处理
#         return ctypes.windll.user32.CallWindowProcW(old_proc, hwnd, msg, wparam, lparam)

#     # 设置消息钩子
#     WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_int)
#     old_proc = ctypes.windll.user32.GetWindowLongW(hwnd, -4)
#     new_proc = WNDPROC(low_level_proc)
#     ctypes.windll.user32.SetWindowLongW(hwnd, -4, new_proc)


def bind_mouse_scroll(widget,speed=3):
    """改进版：支持 Alt + 滚轮、Shift + 滚轮、直接水平滚动（持续触发）"""

    system = platform.system()

    def on_vertical_scroll(event):
        widget.yview_scroll(-int(event.delta / 120) * speed, "units")

    def on_horizontal_scroll(event):
        widget.xview_scroll(-int(event.delta / 120) * speed, "units")

    if system == "Windows":
        # 垂直滚动（普通）
        widget.bind("<MouseWheel>", on_vertical_scroll)
        # Shift 或 Alt 滚轮 → 水平滚动
        widget.bind("<Shift-MouseWheel>", on_horizontal_scroll)
        widget.bind("<Alt-MouseWheel>", on_horizontal_scroll)

    elif system == "Darwin":  # macOS
        widget.bind("<MouseWheel>", lambda e: widget.yview_scroll(-int(e.delta), "units"))
        widget.bind("<Shift-MouseWheel>", lambda e: widget.xview_scroll(-int(e.delta), "units"))
        widget.bind("<Alt-MouseWheel>", lambda e: widget.xview_scroll(-int(e.delta), "units"))

    else:  # Linux
        widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: widget.yview_scroll(1, "units"))
        widget.bind("<Shift-Button-4>", lambda e: widget.xview_scroll(-1, "units"))
        widget.bind("<Shift-Button-5>", lambda e: widget.xview_scroll(1, "units"))
        widget.bind("<Alt-Button-4>", lambda e: widget.xview_scroll(-1, "units"))
        widget.bind("<Alt-Button-5>", lambda e: widget.xview_scroll(1, "units"))

def enable_native_horizontal_scroll(tree: ttk.Treeview, speed=5):
    """
    为 Treeview 添加跨平台水平滚动支持
    - Windows: 支持 Shift+滚轮
    - macOS/Linux: 支持 Button-6/7 事件
    - 不阻塞 GUI，完全非线程方式
    """
    def on_shift_wheel(event):
        delta = -1 if event.delta > 0 else 1
        tree.xview_scroll(delta * speed, "units")
        return "break"

    # Windows: 捕获 Shift + 滚轮
    tree.bind("<Shift-MouseWheel>", on_shift_wheel)

    # macOS/Linux 专用
    if platform.system() != "Windows":
        def on_button_scroll(event):
            if event.num == 6:  # 左
                tree.xview_scroll(-speed, "units")
            elif event.num == 7:  # 右
                tree.xview_scroll(speed, "units")
            return "break"

        tree.bind("<Button-6>", on_button_scroll)
        tree.bind("<Button-7>", on_button_scroll)

# -----------------------------
# 初始化显示器信息（程序启动时调用一次）
# -----------------------------
MONITORS = []  # 全局缓存

def get_all_monitors():
    """返回所有显示器的边界列表 [(left, top, right, bottom), ...]"""
    monitors = []
    for handle_tuple in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(handle_tuple[0])
        monitors.append(info["Monitor"])  # (left, top, right, bottom)
    return monitors

def init_monitors():
    """扫描所有显示器并缓存信息"""
    global MONITORS
    MONITORS = get_all_monitors()
    if not MONITORS:
        # 至少保留主屏幕
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        MONITORS = [(0, 0, screen_width, screen_height)]
    logger.info(f"✅ Detected {len(MONITORS)} monitor(s).")


init_monitors()

def get_monitor_index_for_window(window):
    """根据窗口位置找到所属显示器索引"""
    global MONITORS
    if not MONITORS:
        return 0
    try:
        geom = window.geometry()
        _, x_part, y_part = geom.split("+")
        x, y = int(x_part), int(y_part)
    except Exception:
        return 0

    for idx, (left, top, right, bottom) in enumerate(MONITORS):
        if left <= x <= right and top <= y <= bottom:
            return idx
    return 0  # 默认主屏

# def clamp_window_to_screens(x, y, w, h, monitors=MONITORS):
#     """保证窗口在可见显示器范围内"""
#     global MONITORS
#     monitors = MONITORS or [(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))]
#     for left, top, right, bottom in monitors:
#         if left <= x < right and top <= y < bottom:
#             x = max(left, min(x, right - w))
#             y = max(top, min(y, bottom - h))
#             return x, y
#     # 如果完全不在任何显示器内，放到主屏幕左上角
#     x, y = monitors[0][0], monitors[0][1]
#     return x, y



import win32api

# def clamp_window_to_screens(x, y, w, h):
#     """
#     保证窗口 (x, y, w, h) 位于可见的显示器范围内。
#     - 自动检测所有显示器
#     - 若不在任何显示器内，则放主屏左上角
#     - 自动修正超出边界的情况
#     """
#     # 获取所有显示器信息
#     monitors = []
#     try:
#         for handle_tuple in win32api.EnumDisplayMonitors():
#             info = win32api.GetMonitorInfo(handle_tuple[0])
#             monitors.append(info["Monitor"])  # (left, top, right, bottom)
#     except Exception:
#         pass

#     # 如果检测不到，默认用主屏幕
#     if not monitors:
#         screen_width = win32api.GetSystemMetrics(0)
#         screen_height = win32api.GetSystemMetrics(1)
#         monitors = [(0, 0, screen_width, screen_height)]

#     # 检查窗口位置是否在任何显示器内
#     for left, top, right, bottom in monitors:
#         if left <= x < right and top <= y < bottom:
#             # 修正窗口不要超出边界
#             x = max(left, min(x, right - w))
#             y = max(top, min(y, bottom - h))
#             logger.info(f"✅ clamp_window_to_screens: 命中屏幕 ({left},{top},{right},{bottom}) -> ({x},{y})")
#             return x, y

#     # 完全不在屏幕内 -> 放主屏左上角
#     left, top, right, bottom = monitors[0]
#     logger.info(f"⚠️ clamp_window_to_screens: 未命中屏幕，放主屏 (465, 442)")
#     return (465, 442)

def tk_geometry_to_rect(tk_win):
    """把 Tk geometry 字符串转换为 QRect 或简单坐标"""
    geom = tk_win.geometry()  # '2162x1026+786+860'
    size_pos = geom.split('+')
    w, h = map(int, size_pos[0].split('x'))
    x, y = map(int, size_pos[1:])
    return QtCore.QRect(x, y, w, h)

def is_window_covered_pg(win_pg, win_main, cover_ratio=0.4):
    """判断 PG 窗口是否被主窗口覆盖超过一定比例"""
    rect_pg = win_pg.geometry()
    if isinstance(win_main, tk.Tk) or isinstance(win_main, tk.Toplevel):
        rect_main = tk_geometry_to_rect(win_main)
    else:
        rect_main = win_main.geometry()

    # 计算交集矩形
    left = max(rect_pg.left(), rect_main.left())
    top = max(rect_pg.top(), rect_main.top())
    right = min(rect_pg.right(), rect_main.right())
    bottom = min(rect_pg.bottom(), rect_main.bottom())

    if right < left or bottom < top:
        logger.info(f'没交集 → 完全没被覆盖')
        return False   # 没交集 → 完全没被覆盖

    intersection_area = (right - left) * (bottom - top)
    pg_area = rect_pg.width() * rect_pg.height()

    # 覆盖比例超过 40% 就认为需要提升
    return (intersection_area / pg_area) > cover_ratio

def clamp_window_to_screens_mod(x, y, w, h, monitors):
    """保证窗口在可见显示器范围内"""
    for left, top, right, bottom in monitors:
        if left <= x < right and top <= y < bottom:
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            return x, y
    # 如果完全不在任何显示器内，放到主屏幕左上角
    x, y = monitors[0][0], monitors[0][1]
    logger.info(f"⚠️ 窗口不在任何屏幕，放主屏左上角 ({x},{y})")
    return 100, 100

def clamp_window_to_screens_logical(x, y, w, h):
    """
    使用 DPI 逻辑坐标进行 clamp 判断
    """
    monitors = []
    for hndl in win32api.EnumDisplayMonitors():
        logger.info(f'EnumDisplayMonitors :{hndl}')

        mi = win32api.GetMonitorInfo(hndl[0])
        left, top, right, bottom = mi["Work"]  # 工作区
        # 转逻辑像素
        scale = win32api.GetDeviceCaps(win32api.GetDC(0), 10) / 96.0
        monitors.append((int(left / scale), int(top / scale),
                         int(right / scale), int(bottom / scale)))

    # 检查窗口是否有交集
    for left, top, right, bottom in monitors:
        if (x + w > left and x < right and
            y + h > top and y < bottom):
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            return x, y

    # 默认回主屏左上角
    left, top, right, bottom = monitors[0]
    return left, top

def clamp_window_to_screens(x, y, w, h):
    """
    保证窗口 (x, y, w, h) 位于可见显示器范围内。
    - 优先保持窗口原位置
    - 自动修正超出边界的情况
    - 不在任何屏幕则放主屏左上角
    """

    monitors = []
    try:
        for handle_tuple in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(handle_tuple[0])
            monitors.append(info["Monitor"])  # (left, top, right, bottom)
    except Exception:
        pass

    if not monitors:
        sw, sh = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
        monitors = [(0, 0, sw, sh)]
        # logger.info(f'x:{x} y:{y} w:{w} h:{h}')
    """保证窗口在可见显示器范围内"""
    for left, top, right, bottom in monitors:
        # logger.info(f'left: {left} top : {top} right:{right} bottom:{bottom}')
        # logger.info(x , w , left , x , right ,  y , h , top , y , bottom)
        if left <= x < right and top <= y < bottom:
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            # logger.info(f'left <= x < right and top <= y < bottom: {left <= x < right and top <= y < bottom:} x:{x} y: {y} ')
            return x, y

    # return (x,y)
    # 完全不在屏幕内 -> 放主屏左上角
    left, top, right, bottom = monitors[0]
    x, y = left, top
    logger.info(f"⚠️ 窗口不在任何屏幕，放主屏左上角 ({x},{y})")
    return (100, 100)


def get_centered_window_position_mainWin(parent,win_width, win_height, x_root=None, y_root=None, parent_win=None):
    """
    多屏环境下获取窗口显示位置
    """
    # 默认取主屏幕
    screen = get_monitor_by_point(0, 0)
    x = (screen['width'] - win_width) // 2
    y = (screen['height'] - win_height) // 2

    # 鼠标右键优先
    if x_root is not None and y_root is not None:
        screen = get_monitor_by_point(x_root, y_root)
        x, y = x_root, y_root
        if x + win_width > screen['right']:
            x = max(screen['left'], x_root - win_width)
        if y + win_height > screen['bottom']:
            y = max(screen['top'], y_root - win_height)

    # 父窗口位置
    elif parent_win is not None:
        parent_win.update_idletasks()
        px, py = parent_win.winfo_x(), parent_win.winfo_y()
        pw, ph = parent_win.winfo_width(), parent_win.winfo_height()
        screen = get_monitor_by_point(px, py)
        x = px + pw // 2 - win_width // 2
        y = py + ph // 2 - win_height // 2

    # 边界检查
    x = max(screen['left'], min(x, screen['right'] - win_width))
    y = max(screen['top'], min(y, screen['bottom'] - win_height))
    # logger.info(x,y)
    return x, y

def get_centered_window_position_single(parent, win_width, win_height, margin=10):
    # 获取鼠标位置
    mx = parent.winfo_pointerx()
    my = parent.winfo_pointery()

    # 屏幕尺寸
    screen_width = parent.winfo_screenwidth()
    screen_height = parent.winfo_screenheight()

    # 默认右边放置
    x = mx + margin
    y = my - win_height // 2  # 垂直居中鼠标位置

    # 如果右边放不下，改到左边
    if x + win_width > screen_width:
        x = mx - win_width - margin

    # 防止y超出屏幕
    if y + win_height > screen_height:
        y = screen_height - win_height - margin
    if y < 0:
        y = margin
    x,y = clamp_window_to_screens(x, y, win_width, win_height)
    return x, y


def askstring_at_parent_single(parent, title, prompt, initialvalue=""):
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.title(title)
    dlg.resizable(True, True)

    # 屏幕宽度限制（你原本的逻辑）
    screen = get_monitor_by_point(0, 0)
    screen_width_limit = int(screen['width'] * 0.5)

    base_width, base_height = 600, 300
    char_width = 8
    text_len = max(len(prompt), len(initialvalue))
    win_width = min(max(base_width, text_len * char_width // 2), screen_width_limit)
    win_height = base_height + (prompt.count("\n") * 20)

    x, y = get_centered_window_position_single(parent, win_width, win_height)
    dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

    result = {"value": None}

    lbl = tk.Label(dlg, text=prompt, anchor="w", justify="left", wraplength=win_width - 40)
    lbl.pack(pady=5, padx=5, fill="x")

    # ✅ 获取系统默认字体，统一字号
    default_font = tkfont.nametofont("TkDefaultFont")
    text_font = default_font.copy()
    text_font.configure(size=default_font.cget("size"))  # 可加粗或放大
    # text_font.configure(size=default_font.cget("size") + 1)

    # ✅ 多行输入框 + 自动换行 + 指定字体
    text = tk.Text(dlg, wrap="word", height=6, font=text_font)
    text.pack(pady=5, padx=5, fill="both", expand=True)
    if initialvalue:
        text.insert("1.0", initialvalue)
    text.focus_set()

    def on_ok():
        result["value"] = text.get("1.0", "end-1c").replace("\n", " ")
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    frame_btn = tk.Frame(dlg)
    frame_btn.pack(pady=5)
    tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
    tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

    dlg.bind("<Escape>", lambda e: on_cancel())
    text.bind("<Return>",lambda e: on_ok())       # 回车确认
    text.bind("<Shift-Return>", lambda e: text.insert("insert", "\n"))  # Shift+回车换行

    dlg.grab_set()
    parent.wait_window(dlg)
    return result["value"]

# def askstring_at_parent_single_nofont(parent, title, prompt, initialvalue=""):
#     """带自动换行多行输入框的 askstring 版本"""
#     dlg = tk.Toplevel(parent)
#     dlg.transient(parent)
#     dlg.title(title)
#     dlg.resizable(True, True)

#     # 获取屏幕信息
#     screen = get_monitor_by_point(0, 0)
#     screen_width_limit = int(screen['width'] * 0.5)

#     # --- 智能计算初始大小 ---
#     base_width, base_height = 400, 200
#     char_width = 8
#     text_len = max(len(prompt), len(initialvalue))
#     win_width = min(max(base_width, text_len * char_width // 2), screen_width_limit)
#     win_height = base_height + (prompt.count("\n") * 20)

#     # --- 居中 ---
#     x, y = get_centered_window_position_single(parent, win_width, win_height)
#     dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

#     result = {"value": None}

#     # --- 提示文字 ---
#     lbl = tk.Label(dlg, text=prompt, anchor="w", justify="left", wraplength=win_width - 40)
#     lbl.pack(pady=5, padx=5, fill="x")

#     # --- ✅ 多行文本输入框（自动换行） ---
#     text = tk.Text(dlg, wrap="word", height=6)  # wrap="word" 按单词换行
#     text.pack(pady=5, padx=5, fill="both", expand=True)
#     if initialvalue:
#         text.insert("1.0", initialvalue)
#     text.focus_set()

#     # --- 按钮 ---
#     def on_ok():
#         # ✅ 保存时去掉换行符，恢复为单行字符串
#         result["value"] = text.get("1.0", "end-1c").replace("\n", " ")
#         dlg.destroy()

#     def on_cancel():
#         dlg.destroy()

#     frame_btn = tk.Frame(dlg)
#     frame_btn.pack(pady=5)
#     tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
#     tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

#     dlg.bind("<Escape>", lambda e: on_cancel())

#     dlg.grab_set()
#     parent.wait_window(dlg)
#     return result["value"]


def askstring_at_parent_single_base(parent, title, prompt, initialvalue=""):
    # 创建临时窗口
    dlg = tk.Toplevel(parent)
    dlg.transient(parent)
    dlg.title(title)
    dlg.resizable(True, True)

    screen = get_monitor_by_point(0, 0)
    screen_width_limit = int(screen['width'] * 0.5)

    # --- 智能计算初始大小 ---
    base_width, base_height = 300, 120
    char_width = 9  # 每个字符大约宽 9 像素
    text_len = max(len(prompt), len(initialvalue))
    extra_width = min(text_len * char_width, screen_width_limit)
    win_width = max(base_width, extra_width)
    win_height = base_height + (prompt.count("\n") * 15)

    # --- 居中定位 ---
    x, y = get_centered_window_position_single(parent, win_width, win_height)
    dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

    result = {"value": None}

    # --- 提示文字 ---
    lbl = tk.Label(dlg, text=prompt, justify="left", anchor="w")
    lbl.pack(pady=5, padx=5, fill="x")

    # 初始化时设置一次 wraplength
    lbl.update_idletasks()
    lbl.config(wraplength=lbl.winfo_width() - 20)

    # 当窗口大小变化时动态调整 wraplength
    def on_resize(event):
        new_width = event.width - 20
        if new_width > 100:
            lbl.config(wraplength=new_width)

    dlg.bind("<Configure>", on_resize)

    # --- 输入框 ---
    entry = tk.Entry(dlg)
    entry.pack(pady=5, padx=5, fill="x", expand=True)
    entry.insert(0, initialvalue)
    entry.focus_set()

    # --- 按钮 ---
    def on_ok():
        result["value"] = entry.get()
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    frame_btn = tk.Frame(dlg)
    frame_btn.pack(pady=5)
    tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
    tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

    # --- ESC 键关闭 ---
    dlg.bind("<Escape>", lambda e: on_cancel())

    dlg.grab_set()
    parent.wait_window(dlg)
    return result["value"]


# def get_system_dpi_scale():
#     """获取系统 DPI 缩放比例（Windows 默认 1.0 = 100%）"""
#     try:
#         user32 = ctypes.windll.user32
#         user32.SetProcessDPIAware()
#         dpi_x = user32.GetDpiForSystem()  # 仅 Win10+
#         scale = dpi_x / 96.0
#         return round(scale, 2)
#     except Exception:
#         return 1.0

# def clamp_window_to_screens(x, y, w, h, monitors=None, default_pos=(465, 442)):
#     """
#     确保窗口在可见屏幕内。
#     返回 (x, y)，并考虑 DPI 缩放。
#     """
#     monitors = monitors or get_monitors()
#     dpi_scale = get_system_dpi_scale()

#     if not monitors:
#         return default_pos

#     for m in monitors:
#         left, top = m.x, m.y
#         right, bottom = m.x + m.width, m.y + m.height
#         if left <= x < right and top <= y < bottom:
#             new_x = max(left, min(x, right - w))
#             new_y = max(top, min(y, bottom - h))
#             logger.info(f"✅ 命中屏幕 ({left},{top},{right},{bottom}) DPI={dpi_scale:.2f} → ({new_x},{new_y})")
#             return new_x, new_y

#     logger.info(f"⚠️ 未命中任何屏幕，使用默认位置 {default_pos}")
#     return default_pos


from collections import Counter, OrderedDict

def counterCategory(df, col='category', limit=50, topn=10, table=False):
    """
    统计 DataFrame 某列中前 limit 条的概念出现频率。
    用于分析涨幅榜中哪些板块/概念最集中。

    参数：
        df : pandas.DataFrame
        col : str, 目标列名，如 'category'
        limit : int, 取前多少条股票进行统计
        topn : int, 输出前多少个概念
        table : bool, True 返回表格字符串；False 打印简要结果
    """
    if df is None or len(df) == 0 or col not in df.columns:
        return ""

    # 取前 limit 行的分类字段
    series = df[col].head(limit).dropna().astype(str)

    # 按分隔符拆解成单个概念
    all_concepts = []
    for text in series:
        if ';' in text:
            all_concepts.extend([t.strip() for t in text.split(';') if len(t.strip()) > 1])
        elif '+' in text:
            all_concepts.extend([t.strip() for t in text.split('+') if len(t.strip()) > 1])

    # 统计出现频次
    top_counts = Counter(all_concepts)
    if len(top_counts) == 0:
        return ""

    # 排序并截取前 topn 个
    topn_items = OrderedDict(top_counts.most_common(topn))

    # 格式化输出
    if table:
        return " ".join([f"{k}:{v}" for k, v in topn_items.items()])
    else:
        return(" | ".join([f"{k}:{v}" for k, v in topn_items.items()]))
        # return topn_items


def get_row_tags(latest_row):
        """
        根据最新行情数据返回 Treeview 行标签列表
        """
        row_tags = []

        low = latest_row.get("low")
        lastp1d = latest_row.get("lastp1d")
        high = latest_row.get("high")
        high4 = latest_row.get("high4")
        ma5d = latest_row.get("ma5d")
        ma20d = latest_row.get("ma20d")
        percent = latest_row.get("percent", latest_row.get("per1d", 0))

        # 1️⃣ 红色：低点 > 昨收
        if pd.notna(low) and pd.notna(lastp1d):
            if low > lastp1d:
                row_tags.append("red_row")

        # 2️⃣ 橙色：高点或低点突破 high4
        if pd.notna(high) and pd.notna(high4):
            if high > high4 or (pd.notna(low) and low > high4):
                row_tags.append("orange_row")

        # 3️⃣ 紫色：弱势，低于 ma5d
        if pd.notna(high) and pd.notna(ma5d):
            if high < ma5d:
                row_tags.append("purple_row")

        # 4️⃣ 黄色：临界或预警，低于 ma20d
        if pd.notna(low) and pd.notna(ma20d):
            if low < ma20d:
                row_tags.append("yellow_row")

        # 5️⃣ 绿色：跌幅明显 <2% 且低于昨收
        if pd.notna(percent) and pd.notna(low) and pd.notna(lastp1d):
            if percent < 2 and low < lastp1d:
                row_tags.append("green_row")
        # logger.debug(f'get_row_tags row_tags: {row_tags}')
        return row_tags
# 假设 df 是你提供的涨幅榜表格
# counterCategory(df, 'category', limit=50)

def filter_concepts(cat_dict):
    #批量过滤后期处理用
    INVALID = [
        "国企改革", "沪股通", "深股通", "融资融券", "MSCI", "富时", 
        "标普", "中字头", "央企", "基金重仓", "机构重仓", "大盘股", "高股息"
    ]
    VALID_HINTS = [
        "能源", "科技", "芯片", "AI", "人工智能", "光伏", "储能", 
        "汽车", "机器人", "碳", "半导体", "电力", "通信", "军工", "医药"
    ]
    res = {}
    for k, v in cat_dict.items():
        if any(bad in k for bad in INVALID):
            continue
        if len(v) > 500 or len(v) < 2:  # 太大或太小的概念过滤
            continue
        if not any(ok in k for ok in VALID_HINTS):
            # 名称不含实际产业关键词，也不保留
            continue
        res[k] = v
    return res

# === 概念过滤逻辑 ===
GENERIC_KEYWORDS = [
    "国企改革", "沪股通", "深股通", "融资融券", "高股息", "MSCI", "中字头",
    "央企改革", "标普概念", "B股", "AH股", "转融券", "股权转让", "新股与次新股",
    "战略", "指数", "主题", "计划", "预期", "改革", "通", "国企", "央企"
]

REAL_CONCEPT_KEYWORDS = [
    "半导体", "AI", "机器人", "光伏", "锂电", "医药", "芯片", "5G", "储能",
    "新能源", "军工", "卫星", "航天", "汽车", "算力", "氢能", "量子", "云计算",
    "电商", "游戏", "消费电子", "数据要素", "AI", "大模型"
]

def is_generic_concept(concept_name: str) -> bool:
    """识别是否为泛概念（需过滤）"""
    if any(k in concept_name for k in REAL_CONCEPT_KEYWORDS):
        return False
    if any(k in concept_name for k in GENERIC_KEYWORDS):
        return True
    if len(concept_name) <= 3:
        return True
    # 包含“通”、“改革”、“计划”等关键词的多为无实际含义
    if any(x in concept_name for x in ["通", "改革", "指数", "主题", "计划", "战略", "预期"]):
        return True
    return False


def test_code_against_queries(df_code, queries):
    """
    df_code: DataFrame（单只股票的数据）
    queries: list[dict]，每个包含 'query' 键
    返回每条 query 是否命中
    """
    def ensure_parentheses_balanced(expr: str) -> str:
        expr = expr.strip()
        left_count = expr.count("(")
        right_count = expr.count(")")

        # 自动补齐括号
        if left_count > right_count:
            expr += ")" * (left_count - right_count)
        elif right_count > left_count:
            expr = "(" * (right_count - left_count) + expr

        # ✅ 如果原本已经完整成对，就不再包外层
        if not (expr.startswith("(") and expr.endswith(")")):
            expr = f"({expr})"
        elif expr.startswith("((") and expr.endswith("))"):
            # 如果已经双层包裹，就不处理
            pass

        # # 外层包裹一层括号
        # if not (expr.startswith("(") and expr.endswith(")")):
        #     expr = f"({expr})"

        return expr
    if not isinstance(df_code, pd.DataFrame) or df_code.empty:
        logger.info("df_code : empty or invalid")
        return

    results = []
    ignore_keywords = {"and", "or", "not", "True", "False", "None"}

    for q in queries:
        expr = q.get("query", "")
        query = expr
        if not (query.isdigit() and len(query) == 6):
            # ====== 条件清理 ======
            bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

            # 2️⃣ 替换掉原 query 中的这些部分
            for bracket in bracket_patterns:
                query = query.replace(f'and {bracket}', '')

            conditions = [c.strip() for c in query.split('and')]
            # logger.info(f'conditions {conditions}')
            valid_conditions = []
            removed_conditions = []
            # logger.info(f'conditions: {conditions} bracket_patterns : {bracket_patterns}')
            for cond in conditions:
                cond_clean = cond.lstrip('(').rstrip(')')
                # cond_clean = ensure_parentheses_balanced(cond_clean)
                if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 or cond.find('or') >= 0:
                    if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                        ensure_cond = ensure_parentheses_balanced(cond)
                        # logger.info(f'cond : {cond} ensure_cond : {ensure_cond}')
                        valid_conditions.append(ensure_cond)
                        continue

                # 提取条件中的列名
                cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

                # 所有列都必须存在才保留
                if all(col in df_code.columns for col in cols_in_cond):
                    valid_conditions.append(cond_clean)
                else:
                    removed_conditions.append(cond_clean)
                    # logger.info(f"剔除不存在的列条件: {cond_clean}")

            # 去掉在 bracket_patterns 中出现的内容
            removed_conditions = [
                cond for cond in removed_conditions
                if not any(bp.strip('() ').strip() == cond.strip() for bp in bracket_patterns)
            ]

            if not valid_conditions:
                logger.info(f'valid_conditions not valid_condition : {expr}')
                continue
            # logger.info(f'valid_conditions : {valid_conditions}')
            # ====== 拼接 final_query 并检查括号 ======
            final_query = ' and '.join(f"({c})" for c in valid_conditions)
            # logger.info(f'final_query : {final_query}')
            if bracket_patterns:
                final_query += ' and ' + ' and '.join(bracket_patterns)
            # logger.info(f'final_query : {final_query}')
            left_count = final_query.count("(")
            right_count = final_query.count(")")
            if left_count != right_count:
                if left_count > right_count:
                    final_query += ")" * (left_count - right_count)
                elif right_count > left_count:
                    final_query = "(" * (right_count - left_count) + final_query

            if expr.count('or') > 0 and expr.count('(') > 0:
                final_query = expr
                if removed_conditions:
                    final_query = remove_invalid_conditions(final_query, removed_conditions)
                # logger.info(f'{query.count("or")} OR query: {final_query[:30]}')
                query_engine = 'numexpr'
                if any('index.' in c.lower() for c in query) or ('.str' in query and '|' in query):
                    query_engine = 'python'
            else:
                # ====== 决定 engine ======
                query_engine = 'numexpr'
                if any('index.' in c.lower() for c in valid_conditions):
                    query_engine = 'python'
        else:
            final_query = expr
            query_engine = 'numexpr'
        hit_count = 0
        try:
            # 用 DataFrame.query() 执行逻辑表达式
            # missing_cols = [col for col in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expr)
            #                 if col not in df_code.columns and col not in ignore_keywords]
            # if missing_cols:
            #     logger.info(f"缺少字段: {missing_cols}")
            #     continue
            # logger.info(f'expr : {expr} final_query :{final_query} engine : {query_engine}')
            df_hit = df_code.query(final_query, engine=query_engine)
            # df_hit = df_code.query(final_query)
            # 命中条件：返回非空
            # hit = not df_hit.empty
            hit_count = len(df_hit)

        except Exception as e:
            logger.info(f"[ERROR] 执行 query 出错: {final_query}, {e}")
            # hit = False
            hit_count = 0


        results.append({
            "query": expr,
            "note": q.get("note", ""),
            "starred": q.get("starred", 0),
            "hit": hit_count
        })
            # "hit": bool(hit)
    return results



def estimate_virtual_volume_simple(now=None):
# def estimate_virtual_volume_simple(current_volume, avg_volume_6d, now=None):
    """
    根据当前成交量估算全天预期成交量 + 计算虚拟量比
    
    参数：
        current_volume : float 当前实时成交量
        avg_volume_6d  : float 最近6日平均成交量
        now            : datetime.datetime 或 None，默认为当前时间
        
    返回：
        est_volume   : float  预估全天成交量
        passed_ratio : float  当前时间已完成的成交量比例（0~1）
        vol_ratio    : float  预估虚拟量比（全天预估量 / 6日均量）
    """
    if now is None:
        now = datetime.now()
    t = now.time()
    minutes = t.hour * 60 + t.minute

    # ---- A股真实经验比例（可微调）----
    # 开盘 9:30 - 10:00 约 25%
    # 10:00 - 11:00 约 50%
    # 11:00 - 11:30 约 60%
    # 午后 13:00 - 14:00 约 78%
    # 14:00 - 15:00 约 100%
    segments = [
        (9*60+30, 10*60, 0.25),
        (10*60, 11*60, 0.50),
        (11*60, 11*60+30, 0.60),
        (13*60, 14*60, 0.78),
        (14*60, 15*60, 1.00),
    ]

    passed_ratio = 0.0
    prev_end = 9*60+30
    prev_ratio = 0.0

    for start, end, ratio in segments:
        if minutes <= start:
            passed_ratio = prev_ratio
            break
        elif start < minutes <= end:
            seg_progress = (minutes - start) / (end - start)
            passed_ratio = prev_ratio + (ratio - prev_ratio) * seg_progress
            break
        prev_ratio = ratio
        prev_end = end
    else:
        passed_ratio = 1.0  # 超过收盘

    # 防止过早时刻分母太小
    passed_ratio = max(passed_ratio, 0.05)

    # # 预测全天成交量
    # est_volume = current_volume / passed_ratio

    # # 计算虚拟量比（全天预估量 ÷ 6日平均量）
    # if avg_volume_6d > 0:
    #     vol_ratio = round(est_volume / avg_volume_6d, 2)
    # else:
    #     vol_ratio = 0.0

    # return est_volume, passed_ratio, vol_ratio
    return passed_ratio

def rearrange_monitors_per_screen(align="left", sort_by="id", layout="horizontal",monitor_list=None,win_var=None):
    """
    多屏幕窗口重排（自动换列/换行 + 左右对齐 + 屏幕内排序）
    
    align: "left" 或 "right" 控制对齐方向
    sort_by: "id" 或 "title" 窗口排序依据
    layout: "vertical" -> 竖排 (上下叠加，满高换列)
            "horizontal" -> 横排 (左右并排，满宽换行)
    """
    if not MONITORS:
        init_monitors()

    # 取监控窗口列表
    windows = [info for info in monitor_list.values() if "win" in info]

    # 按屏幕分组
    screen_groups = {i: [] for i in range(len(MONITORS))}
    for win_info in windows:
        win = win_info["win"]
        try:
            x, y = win.winfo_x(), win.winfo_y()
            for idx, (l, t, r, b) in enumerate(MONITORS):
                if l <= x < r and t <= y < b:
                    screen_groups[idx].append(win_info)
                    break
        except Exception as e:
            logger.info(f"⚠ 获取窗口位置失败: {e}")

    # 每个屏幕内排序并排列
    for idx, group in screen_groups.items():
        if not group:
            continue

        # 排序
        if sort_by == "id":
            group.sort(key=lambda info: info['stock_info'][0]) 
        elif sort_by == "title":
            group.sort(key=lambda info: info['stock_info'][1]) 

        l, t, r, b = MONITORS[idx]
        screen_width = r - l
        screen_height = b - t

        margin_x = 10   # 距离边缘 30px
        margin_y = 5    # 距离顶部 5px

        if align == "left":
            current_x = l + margin_x
        elif align == "right":
            current_x = r - margin_x
        else:
            raise ValueError("align 参数必须是 'left' 或 'right'")

        current_y = t + margin_y

        max_col_width = 0
        max_row_height = 0

        for win_info in group:
            win = win_info["win"]
            try:
                w = win.winfo_width()
                h = win.winfo_height()
                win_state = win_var.get()
                if layout == "vertical" or  win_state:
                    # -------- 竖排逻辑 --------
                    if align == "right" and max_col_width == 0:
                        current_x -= w

                    if current_y + h + margin_y > b:
                        # 换列
                        if align == "left":
                            current_x += max_col_width + margin_x
                        else:
                            current_x -= max_col_width + margin_x

                        current_y = t + margin_y
                        max_col_width = 0

                        if align == "right":
                            current_x -= w

                    win.geometry(f"{w}x{h}+{current_x}+{current_y}")
                    current_y += h + margin_y
                    max_col_width = max(max_col_width, w)

                else:
                    # -------- 横排逻辑 --------
                    if align == "right" and max_row_height == 0:
                        current_x -= w

                    if current_x + w + margin_x > r:
                        # 换行
                        current_y += max_row_height + margin_y

                        if align == "left":
                            current_x = l + margin_x
                        else:
                            current_x = r - margin_x - w

                        max_row_height = 0

                    win.geometry(f"{w}x{h}+{current_x}+{current_y}")

                    if align == "left":
                        current_x += w + margin_x
                    else:
                        current_x -= w + margin_x

                    max_row_height = max(max_row_height, h)

            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")

# --- 数据持久化函数 ---
def save_monitor_list(monitor_list):
    """保存当前的监控股票列表到文件"""
    monitor_list = [win['stock_info'] for win in monitor_list.values()]
    mo_list = []
    if len(monitor_list) > 0:
        for m in monitor_list:
            stock_code = m[0]
            if stock_code:
                stock_code = stock_code.zfill(6)

            if  not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
                logger.info(f"错误请输入有效的6位股票代码:{m}")
                continue
            # ✅ 确保结构升级：带 create_time

            if len(m) < 4:
                create_time = datetime.now().strftime("%Y-%m-%d %H")
                m.append(create_time)
            mo_list.append(m)
        # 写入文件
        with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(mo_list, f, ensure_ascii=False, indent=2)

    else:
        logger.info('no window find')

    logger.info(f"监控列表已保存到 {MONITOR_LIST_FILE} : count: {len(monitor_list)}")



def load_monitor_list(MONITOR_LIST_FILE=MONITOR_LIST_FILE):
    """从文件加载监控股票列表"""
    if os.path.exists(MONITOR_LIST_FILE):
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            try:
                loaded_list = json.load(f)
                # 确保加载的数据是列表，并且包含列表/元组
                if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
                    return [list(item) for item in loaded_list]
                return []
            except (json.JSONDecodeError, TypeError):
                return []
    return []


def clean_bad_columns(df):
    bad_cols = [
        c for c in df.columns
        if not isinstance(c, str) or not c.isidentifier()
    ]
    if bad_cols:
        print("清理异常列:", bad_cols)
        df = df.drop(columns=bad_cols)
    return df


LOCK_FILE = "clean_once_{date}.lock"

def cross_process_lock(date):
    lock = LOCK_FILE.format(date=date)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        return fd
    except FileExistsError:
        return None

def _get_clean_flag_path(today):
    """
    当天清理完成的跨进程标记文件
    """
    return os.path.join(
        cct.get_ramdisk_dir(),
        f".tdx_last_df.cleaned.{today}"
    )


def cleanup_old_clean_flags(keep_days=5):
    """
    清理过期的 clean flag 文件
    """
    base = cct.get_ramdisk_dir()
    today = datetime.today().date()

    for fn in os.listdir(base):
        if not fn.startswith(".tdx_last_df.cleaned."):
            continue
        try:
            date_str = fn.rsplit(".", 1)[-1]
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if (today - d).days > keep_days:
                os.remove(os.path.join(base, fn))
        except Exception:
            pass

def clean_expired_tdx_file(logger, g_values):
    """
    每个交易日 08:30–09:15
    清理一次 tdx_last_df（跨进程 / 跨循环安全）
    """

    # ① 是否交易日
    if not cct.get_trade_date_status():
        return False

    today = cct.get_today()
    now_time = cct.get_now_time_int()

    # ② 进程内已完成 → 直接短路
    if (
        g_values.getkey("tdx.clean.done") is True
        and g_values.getkey("tdx.clean.date") == today
    ):
        return True

    # ③ 时间窗口校验
    if not (830 <= now_time <= 915):
        logger.debug(
            f"[CLEAN_SKIP] {today} now={now_time} 不在清理窗口"
        )
        return False

    fname = cct.get_ramdisk_path("tdx_last_df")
    flag_path = _get_clean_flag_path(today)

    logger.debug(
        f"[CLEAN_CHECK] pid={os.getpid()} "
        f"today={today} now={now_time} "
        f"file_exists={os.path.exists(fname)} "
        f"flag_exists={os.path.exists(flag_path)}"
    )

    # ④ 跨进程：今天已完成
    if os.path.exists(flag_path):
        g_values.setkey("tdx.clean.done", True)
        g_values.setkey("tdx.clean.date", today)
        return True

    # ⑤ 文件不存在 → 直接视为完成
    if not os.path.exists(fname):
        logger.info(
            f"[CLEAN_DONE] {today} 文件不存在，直接标记完成"
        )
        try:
            open(flag_path, "w").close()
        except Exception as e:
            logger.error(
                f"[CLEAN_ERR] flag 写入失败: {flag_path}, err={e}"
            )
            return False

        g_values.setkey("tdx.clean.done", True)
        g_values.setkey("tdx.clean.date", today)
        return True

    # ⑥ 真正删除
    try:
        os.remove(fname)
        MultiIndex_fname = cct.get_ramdisk_path("sina_MultiIndex_data")
        if os.path.exists(MultiIndex_fname):
            os.remove(MultiIndex_fname)
            logger.info(
            f"[CLEAN_OK] {today} 已清理过期文件: {MultiIndex_fname}"
        )
        logger.info(
            f"[CLEAN_OK] {today} 已清理过期文件: {fname}"
        )
    except Exception as e:
        logger.error(
            f"[CLEAN_ERR] 删除失败: {fname}, err={e}"
        )
        return False   # 删除失败，不写 flag，允许后续重试

    # ⑦ 写入完成标记
    try:
        open(flag_path, "w").close()
        logger.info(
            f"[CLEAN_FLAG] {today} 清理完成标记已写入"
        )
    except Exception as e:
        logger.error(
            f"[CLEAN_ERR] flag 写入失败: {flag_path}, err={e}"
        )
        return False

    # ⑧ 同步进程内状态（关键）
    g_values.setkey("tdx.clean.done", True)
    g_values.setkey("tdx.clean.date", today)

    return True


def is_tdx_clean_done(today=None):
    if today is None:
        today = cct.get_today()
    flag_path = _get_clean_flag_path(today)
    return os.path.exists(flag_path)

# ---------------- 状态控制 ----------------

# _CLEAN_LOCK = threading.Lock()
# _LAST_CLEAN_DATE = None      # 上一次成功执行的交易日

# def clean_expired_tdx_file(logger):
#     """
#     每个交易日 09:00–09:30 执行一次文件清理
#     （跨日运行程序也能再次触发）
#     """

#     global _LAST_CLEAN_DATE

#     # ✅ 是否交易日
#     if not cct.get_trade_date_status():
#         return

#     today = cct.get_today()   # 例如：2025-12-09


#     # ✅ 当前时间窗口
#     now_time = cct.get_now_time_int()
#     if not (830 <= now_time <= 915):
#         logger.debug(f"{today} 当前时间 {now_time} 不在清理窗口，跳过")
#         return

#     logger.info(f"{today} clean_expired准备清理过期文件: {cct.get_ramdisk_path('tdx_last_df')}")
#     # ✅ 当前交易日
#     # logger.info(f"{today}清理过期文件: {cct.get_run_path_tdx('tdx_last_df')}")
#     # ✅ 计算文件路径
#     fname = cct.get_ramdisk_path('tdx_last_df')
#     if os.path.exists(fname):
#         # fd = cross_process_lock(today)
#         # if not fd:
#         #     logger.info(f"{today} fd:{LOCK_FILE.format(date=today)}文件已存在: {fname}")
#         #     return     # 多进程安全版本其他进程已执行

#         # ✅ 并发保护
#         try:
#             with _CLEAN_LOCK:

#                 # 当天已经执行过
#                 if _LAST_CLEAN_DATE == today:
#                     logger.info(f"{today} _LAST_CLEAN_DATE: {_LAST_CLEAN_DATE} 已清理过期文件: {fname}")
#                     return
#                 try:
#                     os.remove(fname)
#                     logger.info(f"{today} 清理过期文件: {fname}")
#                 except Exception as e:
#                     logger.error(f"{today} 清理文件失败: {fname}, err={e}")
#                 # else:
#                 #     logger.info(f"{today} 待清理文件不存在: {fname}")
#                 finally:
#                     # ✅ 标记今天已完成
#                     _LAST_CLEAN_DATE = today
#         finally:
#             # os.close(fd)
#             logger.info(f"{today} 清理过期文件完毕: {fname}")
#     else:
#         logger.info(f"{today} 待清理文件不存在: {fname}")
#         _LAST_CLEAN_DATE = today

def sanitize(df):
    """
    全面修复重复 index / 重复主键 / 异常残留
    """
    if df is None or df.empty:
        return df

    # 1. index 去重
    df = df.loc[~df.index.duplicated(keep='last')]

    # 2. 常见主键去重
    if 'code' in df.columns:
        if 'date' in df.columns:
            df = df.drop_duplicates(subset=['code', 'date'], keep='last')
        else:
            df = df.drop_duplicates(subset=['code'], keep='last')

    # 3. 删除 NA index
    if df.index.isna().any():
        df = df.loc[~df.index.isna()]

    return df


# ------------------ 后台数据进程 ------------------ #
def fetch_and_process(shared_dict,queue, blkname="boll", flag=None,log_level=None,detect_calc_support=False):
    logger = LoggerFactory.getLogger()  # ✅ 必须调用一次，确保 QueueHandler 添加
    if log_level is not None:
        logger.setLevel(log_level.value)
        # logger.setLevel(log_level)
    logger.info(f"子进程开始，日志等级: {log_level.value}")
    global START_INIT,duration_sleep_time
    g_values = cct.GlobalValues(shared_dict)  # 主进程唯一实例
    resample = g_values.getkey("resample") or "d"
    # logger.info(f'getkey("market") : {g_values.getkey("market")} marketInit:{marketInit}')
    market = g_values.getkey("market", marketInit)        # all / sh / cyb / kcb / bj
    blkname = g_values.getkey("blkname", marketblk)  # 对应的 blk 文件
    logger.info(f"当前选择市场: {market}, blkname={blkname}")
    st_key_sort =  g_values.getkey("st_key_sort", "3 0") 
    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(st_key_sort)
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    logger.info(f"init resample: {resample} flag.value : {flag.value} detect_calc_support:{detect_calc_support.value}")
    while True:
        # logger.info(f'resample : new : {g_values.getkey("resample")} last : {resample} st : {g_values.getkey("st_key_sort")}')
        # if flag is not None and not flag.value:   # 停止刷新
        # logger.info(f'worktime : {cct.get_work_time()} {not cct.get_work_time()} , START_INIT : {START_INIT}')
        try:
            time_s = time.time()
            if not flag.value:   # 停止刷新
                   for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                   # logger.info(f'flag.value : {flag.value} 停止更新')
                   continue
            elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                logger.info(f'resample : new : {g_values.getkey("resample")} last : {resample} ')
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
            elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                # logger.info(f'market : new : {g_values.getkey("market")} last : {market} ')
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
            elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                # logger.info(f'st_key_sort : new : {g_values.getkey("st_key_sort")} last : {st_key_sort} ')
                st_key_sort = g_values.getkey("st_key_sort")
            # elif  830 <= cct.get_now_time_int() <= 915:
            #     # global _LAST_CLEAN_DATE
            #     # ✅ 计算文件路径
            #     fname = cct.get_ramdisk_path('tdx_last_df')
            #     # if _LAST_CLEAN_DATE != cct.get_today():
            #     time_init = time.time()
            #     if os.path.exists(fname) and _LAST_CLEAN_DATE != cct.get_today():
            #         # logger.info(f"{cct.get_today()} 准备清理过期文件: {cct.get_ramdisk_path('tdx_last_df')}")
            #         clean_expired_tdx_file(logger)
            #         START_INIT = 0
            #         if cct.get_now_time_int() <= 900:
            #             top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            #             for res_m in ['d','3d','w','m']:
            #                 if res_m != g_values.getkey("resample"):
            #                     logger.info(f'start init_tdx resample: {res_m}')
            #                     top_all_d, lastpTDX_DF_d = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[res_m],resample=res_m)
            #                 # top_all_3d, lastpTDX_DF_3d = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['3d'],resample='3d')
            #                 # top_all_w, lastpTDX_DF_w = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['w'],resample='w')
            #                 # top_all_m, lastpTDX_DF_m = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['m'],resample='m')
            #         else:
            #             top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            #             for res_m in ['3d']:
            #                 logger.info(f'start init_tdx resample: {res_m}')
            #                 top_all_d, lastpTDX_DF_d = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[res_m],resample=res_m)
            #         logger.info(f'init_tdx 用时:{time.time()-time_init:.2f}')
            elif 830 <= cct.get_now_time_int() <= 915:

                today = cct.get_today()

                # 0️⃣ init 今天已经完成 → 直接跳过
                if (
                    g_values.getkey("tdx.init.done") is True
                    and g_values.getkey("tdx.init.date") == today
                ):
                    continue

                # 1️⃣ 清理（未完成 → 不允许 init）
                if not clean_expired_tdx_file(logger, g_values):
                    logger.info(f"{today} 清理尚未完成，跳过 init_tdx")
                    continue

                # 2️⃣ 再次确认时间（防止跨 09:15）
                now_time = cct.get_now_time_int()
                if now_time > 915:
                    logger.info(
                        f"{today} 已超过初始化截止时间 {now_time}"
                    )
                    continue

                # 3️⃣ 正式 init（只会执行一次）
                time_init = time.time()
                START_INIT = 0

                top_now = tdd.getSinaAlldf(
                    market=market,
                    vol=ct.json_countVol,
                    vtype=ct.json_countType
                )

                if now_time <= 900:
                    resamples = ['d','3d', 'w', 'm']
                else:
                    resamples = ['3d']

                for res_m in resamples:
                    time_init_m = time.time()
                    if res_m != g_values.getkey("resample"):
                        now_time = cct.get_now_time_int()
                        if now_time <= 905:
                            logger.info(f"start init_tdx resample: {res_m}")
                            tdd.get_append_lastp_to_df(
                                top_now,
                                dl=ct.Resample_LABELS_Days[res_m],
                                resample=res_m)
                        else:
                            logger.info(f'resample:{res_m} now_time:{now_time} > 905 终止初始化 init_tdx 用时:{time.time()-time_init_m:.2f}')
                            break
                        logger.info(f'resample:{res_m} init_tdx 用时:{time.time()-time_init_m:.2f}')
                
                # 4️⃣ 关键：标记 init 已完成（跨循环）
                g_values.setkey("tdx.init.done", True)
                g_values.setkey("tdx.init.date", today)

                logger.info(
                    f"init_tdx tdx.init.done:{tdx.init.done} tdx.init.date:{tdx.init.date} 总用时: {time.time() - time_init:.2f}s"
                )

                # 5️⃣ 节流
                for _ in range(30):
                    if not flag.value:
                        break
                    time.sleep(1)

                continue

            elif START_INIT > 0 and (not cct.get_work_time()):
                    # logger.info(f'not worktime and work_duration')
                    for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                    continue
            else:
                logger.info(f'start work : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')
            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", marketInit)        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", marketblk)  # 对应的 blk 文件
            logger.info(f"resample Main: {resample} flag.value : {flag.value} market : {market} blkname :{blkname} ")
            # if START_INIT == 0:
            #     clean_expired_tdx_file(logger, g_values)
            if market == 'indb':
                indf = get_indb_df()
                stock_code_list = indf.code.tolist()
                top_now = tdd.getSinaAlldf(market=stock_code_list,vol=ct.json_countVol, vtype=ct.json_countType)
            else:
                top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                logger.info("top_now.empty no data fetched")
                time.sleep(duration_sleep_time)
                continue

            if top_all.empty:
                if lastpTDX_DF.empty:
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl= ct.Resample_LABELS_Days[resample], resample=resample,detect_calc_support=detect_calc_support.value)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF,detect_calc_support=detect_calc_support.value)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            logger.info(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
            top_temp = top_all.copy()
            # if blkname == "boll":
            #     if "market_value" in top_temp.columns:
            #         top_temp = top_temp.dropna(subset=["market_value"])
            #         top_temp["market_value"] = top_temp["market_value"].fillna("0")
            #         top_temp = top_temp[top_temp["market_value"].apply(lambda x: str(x).replace('.','',1).isdigit())]
            #     top_temp = stf.getBollFilter(df=top_temp, resample=resample, down=True)
            #     if top_temp is None:
            #         top_temp = pd.DataFrame(columns=DISPLAY_COLS)

            top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            logger.info(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape} detect_calc_support:{detect_calc_support.value}')
            df_all = clean_bad_columns(top_temp)
            df_all = sanitize(df_all)
            queue.put(df_all)
            gc.collect()
            logger.info(f'now: {cct.get_now_time_int()}  用时: {round(time.time() - time_s,1)/len(df_all):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            for _ in range(duration_sleep_time):
                if not flag.value: break
                time.sleep(0.5)
            START_INIT = 1

        except Exception as e:
            logger.error(f"resample: {resample} Error in background process: {e}", exc_info=True)
            # print(f"fetch_and_process error: {e}")
            # log.error(f"resample: {resample}: 读取fetch_and_process error:异常: {e}\n{traceback.format_exc()}")
            time.sleep(duration_sleep_time)
        # finally:
        #     try:
        #         queue.put(None)  # 避免父进程阻塞
        #     except:
        #         pass
# ------------------ 指标计算 ------------------ #
def calc_indicators(top_all, resample):
    # if cct.get_trade_date_status():
    #     for co in ['boll', 'df2']:
    #         top_all[co] = list(
    #             map(lambda x, y, m, z: z + (1 if (x > y) else 0),
    #                 top_all.close.values,
    #                 top_all.upper.values,
    #                 top_all.llastp.values,
    #                 top_all[co].values)
    #         )
            
    # top_all = top_all[(top_all.df2 > 0) & (top_all.boll > 0)]

    ratio_t = cct.get_work_time_ratio(resample=resample)
    # ratio_t = estimate_virtual_volume_simple()
    logger.info(f'ratio_t: {round(ratio_t,2)}')
    top_all['volume'] = list(
        map(lambda x, y: round(x / y / ratio_t, 1),
            top_all['volume'].values,
            top_all.last6vol.values)
    )
    now_time = cct.get_now_time_int()
    if  cct.get_trade_date_status():  
        logger.info(f'lastbuy :{"lastbuy" in top_all.columns}')
        if 'lastbuy' in top_all.columns:
            if 915 < now_time < 930:
                top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                # logger.info(f'dff2 :{top_all["dff2"][:5]}')

            elif 926 < now_time < 1455:
                top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                # logger.info(f'dff2 :{top_all["dff2"][:5]}')

            else:
                top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                # logger.info(f'dff2 :{top_all["dff2"][:5]}')

        else:
            top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
            top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)

    else:
        top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
        top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
        
    return top_all.sort_values(by=['dff','percent','volume','ratio','couts'], ascending=[0,0,0,1,1])

def ensure_parentheses_balanced(expr: str) -> str:
    expr = expr.strip()
    left_count = expr.count("(")
    right_count = expr.count(")")

    # 自动补齐括号
    if left_count > right_count:
        expr += ")" * (left_count - right_count)
    elif right_count > left_count:
        expr = "(" * (right_count - left_count) + expr

    # ✅ 如果原本已经完整成对，就不再包外层
    if not (expr.startswith("(") and expr.endswith(")")):
        expr = f"({expr})"
    elif expr.startswith("((") and expr.endswith("))"):
        # 如果已经双层包裹，就不处理
        pass

    # # 外层包裹一层括号
    # if not (expr.startswith("(") and expr.endswith(")")):
    #     expr = f"({expr})"

    return expr


PIPE_NAME = r"\\.\pipe\my_named_pipe"

def send_code_via_pipe(code):

    if isinstance(code, dict):
        code = json.dumps(code, ensure_ascii=False)

    for _ in range(1):
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )
            # logger.info(f'handle : {handle}')
            win32file.WriteFile(handle, code.encode("utf-8"))
            win32file.CloseHandle(handle)
            return True
        except Exception as e:
            logger.info(f"发送失败，重试中...:{e}")
            time.sleep(0.5)
    return False

def list_archives(prefix="search_history"):
    """列出所有存档文件"""
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith(prefix) and f.endswith(".json")],
        reverse=True
    )
    return files

MAX_KEEP = 15  # 每个前缀只保留最近 15 个文件

def archive_file_tools(src_file, prefix):
    """
    通用备份函数
    src_file: 需要备份的文件路径，如 "alerts.json"
    prefix  : 文件名前缀，如 "alerts", "monitor_list"
    """
    if not os.path.exists(src_file):
        logger.info(f"⚠ {src_file} 不存在，跳过存档")
        return

    try:
        with open(src_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取 {src_file}: {e}")
        return

    if not content or content in ("[]", "{}", ""):
        logger.info(f"⚠ {src_file} 内容为空，跳过存档")
        return

    # 确保存档目录存在
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 检查最近一个存档是否相同
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith(prefix + "_")],
        reverse=True
    )

    if files:
        last_file = os.path.join(ARCHIVE_DIR, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if content == last_content:
                logger.info(f"⚠ {src_file} 与上一次 {prefix} 存档相同，跳过存档")
                return
        except Exception as e:
            logger.info(f"⚠ 无法读取最近存档: {e}")

    # --- 生成存档文件名 ---
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{prefix}_{today}.json"
    dest = os.path.join(ARCHIVE_DIR, filename)

    # 如果同一天已有 → 加时间戳避免覆盖
    # if os.path.exists(dest):
    #     timestamp = datetime.now().strftime("%H%M%S")
    #     filename = f"{prefix}_{today}_{timestamp}.json"
    #     dest = os.path.join(ARCHIVE_DIR, filename)

    # 复制文件
    shutil.copy2(src_file, dest)
    rel_path = os.path.relpath(dest)
    logger.info(f"✅ 已归档：{rel_path}")

    # --- 清理旧备份，只保留最近 MAX_KEEP 个 ---
    files = sorted(
        [os.path.join(ARCHIVE_DIR, f) for f in os.listdir(ARCHIVE_DIR) if f.startswith(prefix + "_")],
        key=os.path.getmtime,
        reverse=True
    )
    logger.info(f'files:{len(files)} : {files}')
    for old_file in files[MAX_KEEP:]:
        try:
            os.remove(old_file)
            logger.info(f"🗑 删除旧归档: {os.path.basename(old_file)}")
        except Exception as e:
            logger.info(f"⚠ 删除失败 {old_file} -> {e}")

def archive_search_history_list(MONITOR_LIST_FILE=SEARCH_HISTORY_FILE,ARCHIVE_DIR=ARCHIVE_DIR):
    """归档监控文件，避免空或重复存档"""
    archive_file_tools("monitor_category_list.json", "monitor_category_list")

    if not os.path.exists(MONITOR_LIST_FILE):
        logger.info("⚠ search_history.json 不存在，跳过归档")
        return

    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        logger.info("⚠ search_history.json 内容为空，跳过归档")
        return

    # 确保存档目录存在
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 检查是否和最近一个存档内容相同
    files = sorted(list_archives(), reverse=True)
    if files:
        last_file = os.path.join(ARCHIVE_DIR, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if not content or content in ("[]", "{}") or content == last_content:
                logger.info("⚠ 内容与上一次存档相同，跳过归档")
                return
        except Exception as e:
            logger.info(f"⚠ 无法读取最近存档: {e}")

    # 生成带日期的存档文件名
    # today = datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d-%H")
    filename = f"search_history_{today}.json"
    dest = os.path.join(ARCHIVE_DIR, filename)

    # 如果当天已有存档，加时间戳避免覆盖
    if os.path.exists(dest):
        filename = f"search_history_{today}.json"
        dest = os.path.join(ARCHIVE_DIR, filename)

    # 复制文件
    shutil.copy2(MONITOR_LIST_FILE, dest)
    logger.info(f"✅ 已归档监控文件: {dest}")

# ------------------ Tk 前端 ------------------ #
# class StockMonitorApp(tk.Tk):
#     def __init__(self, queue):
#         super().__init__()
#         self.queue = queue
#         self.title("Stock Monitor")
#         self.load_window_position()

#         # ----------------- 控件框 ----------------- #
#         ctrl_frame = tk.Frame(self)
#         ctrl_frame.pack(fill="x", padx=5, pady=2)

#         tk.Label(ctrl_frame, text="blkname:").pack(side="left")
#         self.blk_label = tk.Label(ctrl_frame, text=cct.GlobalValues().getkey("blkname") or "boll")
#         self.blk_label.pack(side="left", padx=2)

#         tk.Label(ctrl_frame, text="resample:").pack(side="left", padx=5)
#         self.resample_combo = ttk.Combobox(ctrl_frame, values=["d","w","m"], width=5)
#         self.resample_combo.set(cct.GlobalValues().getkey("resample") or "d")
#         self.resample_combo.pack(side="left")
#         self.resample_combo.bind("<<ComboboxSelected>>", self.set_resample)

#         tk.Label(ctrl_frame, text="Search:").pack(side="left", padx=5)
#         self.search_entry = tk.Entry(ctrl_frame, width=30)
#         self.search_entry.pack(side="left", padx=2)
#         tk.Button(ctrl_frame, text="Go", command=self.set_search).pack(side="left", padx=2)

#         # 数据存档按钮
#         tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
#         tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

#         # ----------------- 状态栏 ----------------- #
#         self.status_var = tk.StringVar()
#         self.status_bar = tk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
#         self.status_bar.pack(fill="x", side="bottom")

#         # ----------------- TreeView ----------------- #
#         tree_frame = tk.Frame(self)
#         tree_frame.pack(fill="both", expand=True)
#         self.tree = ttk.Treeview(tree_frame, columns=["code"] + DISPLAY_COLS, show="headings")
#         vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
#         hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
#         self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
#         vsb.pack(side="right", fill="y")
#         hsb.pack(side="bottom", fill="x")
#         self.tree.pack(fill="both", expand=True)

#         # checkbuttons 顶部右侧
#         self.init_checkbuttons(ctrl_frame)

#         # TreeView 列头
#         for col in ["code"] + DISPLAY_COLS:
#             width = 120 if col=="name" else 80
#             self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
#             self.tree.column(col, width=width, anchor="center", minwidth=50)

#         self.current_df = pd.DataFrame()
#         self.after(500, self.update_tree)
#         self.protocol("WM_DELETE_WINDOW", self.on_close)
#         # Tree selection event
#         self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
#         self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)

from alerts_manager import AlertManager, open_alert_center, set_global_manager, check_alert

class StockMonitorApp(tk.Tk):
    def __init__(self):
        # (确保 Tkinter 以高 DPI 模式启动，解决模糊问题)
        # if sys.platform.startswith('win'):
        #     set_process_dpi_awareness()
        # 初始化 tk.Tk()
        super().__init__()
        
        # 💥 关键修正 1：在所有代码执行前，初始化为安全值
        self.main_window = self   # ✨ 正确
        self.scale_factor = 1.0 
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font_size = self.default_font.cget("size")
        self.default_font_bold = tkfont.nametofont("TkDefaultFont").copy()
        # self.default_font_bold.configure(weight="bold")  # 只加粗，不修改字号或字体
        self.default_font_bold.configure(family="Microsoft YaHei", size=10, weight="bold")

        # #保存初始化基准值
        # self.base_font_size = self.default_font.cget("size")
        # self.base_font_bold_size = self.default_font_bold.cget("size")
        # self.base_window_width = self.winfo_width()
        # self.base_window_height = self.winfo_height()


        global duration_sleep_time
        # 💥 关键修正 2：立即执行 DPI 缩放并重新赋值
        if sys.platform.startswith('win'):
            # 确保 self._apply_dpi_scaling() 总是返回一个 float
            result_scale = self._apply_dpi_scaling()
            if result_scale is not None and isinstance(result_scale, (float, int)):
                self.scale_factor = result_scale

        # self.last_dpi_scale = get_windows_dpi_scale_factor()
        self.last_dpi_scale = self.scale_factor
        # 3. 接下来是 Qt 初始化，它不应该影响 self.scale_factor
        if not QtWidgets.QApplication.instance():
            self.app = pg.mkQApp()

        self.title("Stock Monitor")
        self.initial_w, self.initial_h, self.initial_x, self.initial_y  = self.load_window_position(self, "main_window", default_width=1200, default_height=480)
        self.monitor_windows = {}
        # self.iconbitmap(icon_path)  # Windows 下 .ico 文件
        # 判断文件是否存在再加载
        if os.path.exists(icon_path):
            # self.iconbitmap(icon_path)
            self.after(1000, lambda: self.iconbitmap(icon_path))

        else:
            print(f"图标文件不存在: {icon_path}")
        # self._icon = tk.PhotoImage(file=icon_path)
        # self.iconphoto(True, self._icon)
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.select_code = None
        self.ColumnSetManager = None
        self.ColManagerconfig = None
        self._open_column_manager_job = None
        # self._last_cat_dict = filter_concepts(new_cat_dict)
        # self._last_categories = list(self._last_cat_dict.keys())
        self._concept_dict_global = {}

        # 刷新开关标志
        self.refresh_enabled = True
        from multiprocessing import Manager
        self.manager = Manager()
        self.global_dict = self.manager.dict()  # 共享字典
        self.global_dict["resample"] = resampleInit   
        # self.global_dict["resample"] = 'w'
        self.global_values = cct.GlobalValues(self.global_dict)
        resample = self.global_values.getkey("resample")
        logger.info(f'app init getkey resample:{self.global_values.getkey("resample")}')
        self.global_values.setkey("resample", resample)
        # self.blkname = self.global_values.getkey("blkname") or "061.blk"
        self.blkname = ct.Resample_LABELS_Blk[resample] or "060.blk"
        self.global_values.setkey("blkname", self.blkname)
        # 用于保存 detail_win
        self.detail_win = None
        self.txt_widget = None

        # ----------------- 控件框 ----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=1)

        self.st_key_sort = self.global_values.getkey("st_key_sort") or "3 0"

        # ====== 底部状态栏 ======
        status_frame = tk.Frame(self, relief="sunken", bd=1)
        status_frame.pack(side="bottom", fill="x")

        # 使用 PanedWindow 水平分割，支持拖动
        pw = tk.PanedWindow(status_frame, orient=tk.HORIZONTAL, sashrelief="sunken", sashwidth=4)
        pw.pack(fill="x", expand=True)

        # 左侧状态信息
        left_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var = tk.StringVar()
        status_label_left = tk.Label(
            left_frame, textvariable=self.status_var, anchor="w", padx=10, pady=1
        )
        status_label_left.pack(fill="x", expand=True)

        # 右侧状态信息
        right_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var2 = tk.StringVar()
        status_label_right = tk.Label(
            right_frame, textvariable=self.status_var2, anchor="e", padx=10, pady=1
        )
        status_label_right.pack(fill="x", expand=True)

        # 添加左右面板 状态栏
        # 动态调整宽度
        self.update_status_bar_width(pw, left_frame, right_frame)

        # 延时更新状态栏宽度
        self.after(200, lambda: self.update_status_bar_width(pw, left_frame, right_frame))

        # ----------------- TreeView ----------------- #
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        global DISPLAY_COLS
        self.tree = ttk.Treeview(tree_frame, columns=["code"] + DISPLAY_COLS, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # self.tree.bind("<Shift-MouseWheel>", lambda e: self.tree.xview_scroll(-1 * int(e.delta / 120), "units"))
        # ✅ 启用鼠标水平滚轮支持
        # enable_horizontal_mouse_wheel(self.tree)
        bind_mouse_scroll(self.tree)
        # enable_native_horizontal_scroll(self.tree, speed=5)

        self.current_cols = ["code"] + DISPLAY_COLS
        # TreeView 列头
        for col in ["code"] + DISPLAY_COLS:
            width = 80 if col=="name" else 60
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, self.sortby_col_ascend))
            self.tree.column(col, width=width, anchor="center", minwidth=50)
            # self.tree.heading(col, command=lambda c=col: self.show_column_menu(c))

        # 双击表头绑定
        # self.tree.bind("<Double-1>", self.on_tree_header_double_click)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-2>", self.copy_code)
        


        self.df_all = pd.DataFrame()      # 保存 fetch_and_process 返回的完整原始数据
        self.current_df = pd.DataFrame()

        # 队列接收子进程数据
        self.queue = mp.Queue()

        # UI 构建
        self._build_ui(ctrl_frame)

        # checkbuttons 顶部右侧
        self.init_checkbuttons(ctrl_frame)

        # ✅ 股票特征标记器初始化（必须在性能优化器之前）
        if FEATURE_MARKER_AVAILABLE:
            try:
                # 使用win_var控制颜色显示（如果win_var存在）
                enable_colors = not self.win_var.get() if hasattr(self, 'win_var') else True
                self.feature_marker = StockFeatureMarker(self.tree, enable_colors=enable_colors)
                self._use_feature_marking = True
                logger.info(f"✅ 股票特征标记器已初始化 (颜色显示: {enable_colors})")
            except Exception as e:
                logger.warning(f"⚠️ 股票特征标记器初始化失败: {e}")
                self._use_feature_marking = False
        else:
            self._use_feature_marking = False
        
        # ✅ 初始化标注手札
        self.handbook = StockHandbook()
        # ✅ 初始化实时监控策略 (延迟初始化，防止阻塞主窗口显示)
        self.live_strategy = None
        self.after(3000, self._init_live_strategy)
        
        # ✅ 性能优化器初始化
        if PERFORMANCE_OPTIMIZER_AVAILABLE:
            try:
                # 传入feature_marker以支持特征标记
                feature_marker_instance = None
                if FEATURE_MARKER_AVAILABLE and hasattr(self, 'feature_marker'):
                    feature_marker_instance = self.feature_marker
                
                self.tree_updater = TreeviewIncrementalUpdater(
                    self.tree, 
                    self.current_cols,
                    feature_marker=feature_marker_instance
                )
                self.df_cache = DataFrameCache(ttl=5)  # 5秒缓存
                self.perf_monitor = PerformanceMonitor("TreeUpdate")
                self._use_incremental_update = True
                logger.info("✅ 性能优化器已初始化 (增量更新模式)")
            except Exception as e:
                logger.warning(f"⚠️ 性能优化器初始化失败,使用传统模式: {e}")
                self._use_incremental_update = False
        else:
            self._use_incremental_update = False
            logger.info("ℹ️ 使用传统刷新模式")
        
        # 启动后台进程
        self._start_process()

        # 定时检查队列
        self.after(1000, self.update_tree)

        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)  
        self.tree.bind("<Button-1>", self.on_single_click)
        # ✅ 绑定单击事件用于显示股票信息提示框
        # self.tree.bind("<ButtonRelease-1>", self.on_tree_click_for_tooltip)
        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)

        self.bind("<Alt-c>", lambda e:self.open_column_manager())
        self.bind("<Alt-d>", lambda event: self.open_handbook_overview())
        self.bind("<Alt-e>", lambda event: self.open_voice_monitor_manager())
        # 启动周期检测 RDP DPI 变化
        self.after(3000, self._check_dpi_change)
        self.auto_adjust_column = self.dfcf_var.get()

    # scheduler
    def schedule_15_30_job(self):
        from datetime import datetime, time

        now = datetime.now()
        today_1530 = datetime.combine(now.date(), time(15,30))

        if not hasattr(self, "_last_run_date"):
            logger.info("schedule_15_30_job，开始_last_run_date...")
            self._last_run_date = None

        if now >= today_1530 and self._last_run_date != now.date():
            self._last_run_date = now.date()
            logger.info(f'start run Write_market_all_day_mp')
            threading.Thread(
                target=self.run_15_30_task,
                daemon=True
            ).start()

        self.after(60*1000, self.schedule_15_30_job)

    # worker
    def run_15_30_task(self):
        if getattr(self, "_task_running", False):
            return

        if hasattr(self, "live_strategy"):
            try:
                # 提取窗口名称用于保存位置
                # unique_code 格式为 "concept_name_code" 或 "concept_name"
                now_time = cct.get_now_time_int()
                if now_time > 1500:
                    self.live_strategy._save_monitors()
                    logger.info(f"[on_close] self.live_strategy._save_monitors SAVE OK")
                else:
                    logger.info(f"[on_close] now:{now_time} 未到收盘时间 未进行_save_monitors SAVE")

            except Exception as e:
                logger.warning(f"[on_close] self.live_strategy._save_monitors 失败: {e}")

        today = cct.get_today('')
        if write_all_day_date == today:
            logger.info(f'Write_market_all_day_mp 已经完成')
            return
        self._task_running = True
        try:
            logger.info(f'start Write_market_all_day_mp OK')
            tdd.Write_market_all_day_mp('all')
            logger.info(f'run Write_market_all_day_mp OK')
            CFG = cct.GlobalConfig(conf_ini)
            # cct.GlobalConfig(conf_ini, write_all_day_date=20251205)
            CFG.set_and_save("general", "write_all_day_date", today)

        finally:
            self._task_running = False

    def save_all_monitor_windows(self):
        """保存当前所有监控窗口"""
        try:
            save_monitor_list(self._pg_top10_window_simple)
        except Exception as e:
            logger.info(f"保存监控列表失败: {e}")


    def restore_all_monitor_windows(self):
        """启动时从文件恢复窗口"""
        monitor_data = load_monitor_list()
        if not monitor_data:
            logger.info("无监控窗口记录。")
            return

        logger.info(f"正在恢复 {len(monitor_data)} 个监控窗口...")
        for m in monitor_data:
            try:
                code = m[0]
                stock_name = m[1] if len(m) > 1 else ""
                concept_name = m[2] if len(m) > 2 else ""   # 视你的 stock_info 结构而定
                create_time = m[3] if len(m) > 3 else "" 
                # 唯一key
                # unique_code = f"{concept_name or ''}_{code or ''}"
                unique_code = f"{concept_name or ''}_"

                # 创建窗口
                win = self.show_concept_top10_window_simple(concept_name, code=code, auto_update=True, interval=30)

                # 注册回监控字典
                self._pg_top10_window_simple[unique_code] = {
                    "win": win,
                    "code": unique_code,
                    "stock_info": m
                }
                logger.info(f"恢复窗口 {unique_code}: {concept_name} - {stock_name} ({code}) [{create_time}]")
            except Exception as e:
                logger.info(f"恢复窗口失败: {m}, 错误: {e}")
        # if len(monitor_data) > 2:
            # rearrange_monitors_per_screen(align="left", sort_by="id", layout="horizontal",monitor_list=self._pg_top10_window_simple, win_var=self.win_var)

    def update_status_bar_width(self, pw, left_frame, right_frame):
        """ 根据 DPI 缩放调整左右面板的宽度比例 """
        left_width = int(900 * self.scale_factor)
        right_width = int(100 * self.scale_factor)

        # 移除并重新添加左、右面板
        pw.forget(left_frame)
        pw.forget(right_frame)

        pw.add(left_frame, minsize=100, width=left_width)
        pw.add(right_frame, minsize=100, width=right_width)
        # logger.info(f'update_status_bar_width')

    # def correct_window_geometry(self, initial_x, initial_y, initial_w, initial_h):
    def correct_window_geometry(self):
        """
        在 Qt 初始化后运行，修复 Tkinter 窗口的位置错乱问题。

        Args:
            initial_x (int): 窗口期望的逻辑像素 X 坐标。
            initial_y (int): 窗口期望的逻辑像素 Y 坐标。
            initial_w (int): 窗口期望的逻辑像素宽度。
            initial_h (int): 窗口期望的逻辑像素高度。
        """
        
        # 强制 Tkinter 处理挂起事件，使其在 Qt 更改 DPI 后刷新内部状态
        return
        self.update_idletasks()

        # 💥 使用保存的类属性
        initial_x = self.initial_x
        initial_y = self.initial_y
        initial_w = self.initial_w # 尽管这个参数在您的逻辑中可能没用到，最好也引入
        initial_h = self.initial_h
        # scale_factor = self.scale_factor # 假设您已在 __init__ 中保存

        if sys.platform.startswith('win'):
            # 1. 重新获取当前的 DPI 缩放因子
            # 注意：这里的 DPI 可能被 Qt 更改，但我们仍使用初始获取的值（2.0）
            # 假设您在 __init__ 中保存了 scale_factor
            try:
                logger.info(f'self.scale_factor: {self.scale_factor}')
                scale_factor = self.scale_factor 
            except AttributeError:
                # 如果没有保存，重新获取，但可能不准
                scale_factor = get_windows_dpi_scale_factor()
            
            # 2. 重新计算窗口的物理像素位置 (因为 Qt 启动后 Tkinter 切换到了物理坐标系)
            # 注意：这里的 (x, y) 坐标需要被缩放才能在 4K 坐标系中正确显示。
            target_x = int(initial_x * scale_factor)
            target_y = int(initial_y * scale_factor)
            
            # 3. 检查 Tkinter 报告的当前屏幕尺寸 (现在很可能是 4K 物理分辨率)
            screen_width_phys = self.winfo_screenwidth()
            screen_height_phys = self.winfo_screenheight()
            
            # 4. 重新应用几何信息
            # 获取窗口当前的宽度和高度 (它们应该是缩放后的物理尺寸)
            current_w = self.winfo_width()
            current_h = self.winfo_height()
            
            # 修正 target_x, target_y，确保不超出 4K 屏幕边界
            target_x = max(0, min(target_x, screen_width_phys - current_w))
            target_y = max(0, min(target_y, screen_height_phys - current_h))

            self.geometry(f'{current_w}x{current_h}+{target_x}+{target_y}')
        else:
            # 非 Windows 系统，只需刷新即可
            current_geometry = self.geometry()
            self.geometry(current_geometry)

        logger.info(f"✅ Tkinter 窗口几何信息已在 Qt 启动后刷新。重新定位到 ({target_x},{target_y}) 物理像素。")

    def print_tk_dpi_detail(self):
        px_per_inch = self.winfo_fpixels('1i')
        width_px = self.winfo_screenwidth()
        height_px = self.winfo_screenheight()
        width_in = self.winfo_screenmmwidth() / 25.4
        height_in = self.winfo_screenmmheight() / 25.4
        screen_dpi = round(width_px / width_in / 96,2)
        dpi, scale = get_current_window_scale(self)
        print("当前显示器 DPI:", dpi)
        print("缩放倍率:", scale)

        # if screen_dpi != self.scale_factor:
        #     logger.info(f"{cct.get_now_time_int()} 分辨率: {width_px}×{height_px}")
        #     logger.info(f"{cct.get_now_time_int()} 物理尺寸: {width_in:.2f}×{height_in:.2f} inch")
        #     logger.info(f"{cct.get_now_time_int()} 实际 DPI: {screen_dpi:.2f}, last_dpi: {self.scale_factor} Tk DPI: {px_per_inch/96:.2f}")
        #     self.scale_factor = screen_dpi

        # logger.info(f"分辨率: {width_px}×{height_px}")
        # logger.info(f"实际 DPI: {screen_dpi:.2f}, Tk DPI: {px_per_inch/96:.2f}")
        return  (width_px,height_px)

            # width_px,height_px = self.print_tk_dpi_detail()
            # if width_px == 1920:
            #     current_scale = 1.25
            # elif  width_px == 3840 or width_px == 2560:
            #     current_scale = 2
            # else:
            #     current_scale = 1

    def _check_dpi_change(self):
            """定期检测 DPI 是否变化（例如 RDP 登录）"""
            # dpi, scale = get_current_window_scale(self)
            scale = get_window_dpi_scale(self)
            # print("当前显示器 DPI:", dpi)
            # print("缩放倍率:", scale)
            current_scale = scale
            # logger.info(f'width_px : {width_px}')
            if abs(current_scale - self.last_dpi_scale) > 0.05:
                logger.info(f"{cct.get_now_time_int()}  current_scale:{current_scale}")
                # logger.info(f"{cct.get_now_time_int()} 分辨率: {width_px}×{height_px} current_scale:{current_scale}")
                logger.info(f"[DPI变化检测] 从 {self.last_dpi_scale:.2f} → {current_scale:.2f}")
                self._apply_scale_dpi_change(current_scale)
                self.on_dpi_changed_qt(current_scale)
                # self.scale_factor = current_scale
                self.last_dpi_scale = current_scale

            # 每 5 秒检测一次
            self.after(5000, self._check_dpi_change)

    def get_qt_window_scale_base(self,win: QtWidgets.QWidget):
        try:
            handle = win.windowHandle()  # 获取 QWindow
            if handle is None:
                # 有些 QWidget 还没显示，会返回 None
                return 96, 1.0
            screen = handle.screen()  # QScreen
            scale = screen.devicePixelRatio()
            dpi = screen.logicalDotsPerInch()
            return dpi, scale
        except Exception as e:
            logger.warning(f"获取 Qt 窗口缩放失败: {e}")
            return 96, 1.0

    def get_qt_window_scale(self,win: QtWidgets.QWidget):
        try:
            handle = win.windowHandle()
            if handle is None:
                return 1.0  # 还没显示窗口，默认 1.0
            screen = handle.screen()
            # logical DPI
            logical_dpi = screen.logicalDotsPerInch()   # 通常 96
            # 物理 DPI = logical DPI * devicePixelRatio()
            physical_dpi = logical_dpi * screen.devicePixelRatio()
            # 基准 DPI = 96
            scale = physical_dpi / 96.0
            return scale
        except Exception as e:
            logger.warning(f"获取 Qt 窗口缩放失败: {e}")
            return 1.0

    def on_dpi_changed_qt(self, new_scale):
        """RDP 或 DPI 变化时自动缩放窗口"""
        try:
            if  hasattr(self, "_pg_windows"):
                for k, v in self._pg_windows.items():
                    win = v.get("win")
                    try:
                        if  v.get("win") is not None:
                            # 已存在，聚焦并显示 (PyQt)
                            win_qt_scale = self.get_qt_window_scale(win)
                            if win_qt_scale == new_scale:
                                logger.info(f'get_qt_window_scale: {self.get_qt_window_scale(win)} get_qt_window_scale_base:{self.get_qt_window_scale_base(win)}')
                                geom = win.geometry()
                                width, height = geom.width(), geom.height()
                                base = self._dpi_base
                                scale_ratio = new_scale / base["scale"]
                                # new_w = int(width * new_scale)
                                # new_h = int(height * new_scale)
                                new_w = int(width * scale_ratio)
                                new_h = int(height * scale_ratio)
                                win.resize(new_w, new_h)
                                code = v.get("code", "N/A")
                                logger.info(f"[DPI] code={code} 窗口自动放大到 {new_scale:.2f} 倍-> {scale_ratio:.2f}倍 ({new_w}x{new_h})")
                                # 如果你使用 PyQtGraph 或 Label，也可重设字体：
                                for child in win.findChildren(QtWidgets.QWidget):
                                    font = child.font()
                                    font.setPointSizeF(font.pointSizeF() * scale_ratio)
                                    child.setFont(font)

                    except Exception as e:
                        logger.info(f'e:{e} pg win is None will remove:{v.get("win")}')
                        del self._pg_windows[k]
                    finally:
                        pass
                

        except Exception as e:
            logger.info(f"[DPI] 自动缩放失败: {e}")

    # def get_dynamic_dpi_scale(self):
    #     """通过当前显示器分辨率动态估算缩放比例"""
    #     screen = self.app.primaryScreen()
    #     dpi = screen.logicalDotsPerInch()
    #     scale = dpi / 96.0
    #     # logger.info(f"[DPI] Qt 检测 scale = {scale:.2f}, DPI = {dpi}")
    #     return scale

    # def get_tk_dpi_scale(self):
    #     # 返回当前屏幕缩放比例，例如 1.0、1.25、2.0
    #     dpi = self.winfo_fpixels('1i')
    #     scale = dpi / 96.0
    #     logger.info(f"[Tk] DPI={dpi:.2f}, scale={scale:.2f}")
    #     return scale

    # def _apply_scale_dpi_change_2_125_no(self, new_scale):
    #     """
    #     完整 DPI 缩放方法（窗口尺寸、字体、TreeView 行高和列宽、全局 Tk scaling）
    #     """
    #     try:
    #         # 初始化基准值
    #         if not hasattr(self, "_dpi_base"):
    #             base_tree_colwidths = []
    #             if hasattr(self, 'tree'):
    #                 base_tree_colwidths = [self.tree.column(c)['width'] for c in self.tree['columns']]
    #             self._dpi_base = {
    #                 "width": self.winfo_width(),
    #                 "height": self.winfo_height(),
    #                 "font_size": self.default_font.cget("size"),
    #                 "tree_rowheight": 22,
    #                 "tree_colwidths": base_tree_colwidths,
    #                 "scale": self.scale_factor
    #             }
    #             logger.info(f"[DPI] 初始化基准值: 窗口 {self._dpi_base['width']}x{self._dpi_base['height']}, "
    #                         f"字体 {self._dpi_base['font_size']}pt, TreeView行高 {self._dpi_base['tree_rowheight']}")

    #         base = self._dpi_base
    #         scale_ratio = new_scale / base["scale"]

    #         # 1️⃣ 窗口尺寸
    #         new_w = int(base["width"] * scale_ratio)
    #         new_h = int(base["height"] * scale_ratio)
    #         self.geometry(f"{new_w}x{new_h}")

    #         # 2️⃣ 字体
    #         new_font_size = max(6, min(int(base["font_size"] * scale_ratio), 24))
    #         self.default_font.configure(size=new_font_size)
    #         self.default_font_bold.configure(size=new_font_size)

    #         # 3️⃣ TreeView 行高和列宽
    #         if hasattr(self, 'tree'):
    #             style = ttk.Style(self)
    #             new_rowheight = int(base["tree_rowheight"] * scale_ratio)
    #             style.configure('Treeview', rowheight=new_rowheight)
    #             style.configure('Treeview.Heading', font=self.default_font)
    #             # 列宽按比例更新
    #             for i, col in enumerate(self.tree['columns']):
    #                 if i < len(base["tree_colwidths"]):
    #                     self.tree.column(col, width=int(base["tree_colwidths"][i] * scale_ratio))

    #         # 4️⃣ 全局 Tk scaling
    #         self.tk.call('tk', 'scaling', new_scale)

    #         # 5️⃣ 递归更新内部所有控件字体
    #         for widget in self.winfo_children():
    #             self._update_widget_font_recursive(widget, self.default_font)

    #         # 6️⃣ 保存 scale
    #         self.scale_factor = new_scale
    #         logger.info(f"[DPI] ✅ 完成全部缩放: scale={new_scale:.2f}")

    #     except Exception as e:
    #         logger.error(f"[DPI] ❌ 应用缩放失败: {e}", exc_info=True)

    # def _update_widget_font_recursive(self, widget, font):
    #     """
    #     递归更新 widget 及其子控件的字体
    #     """
    #     try:
    #         if isinstance(widget, (tk.Label, tk.Entry, tk.Button, ttk.Combobox, tk.Text)):
    #             widget.configure(font=font)
    #         elif isinstance(widget, ttk.Treeview):
    #             # TreeView 已经在 _apply_scale_dpi_change 中单独处理
    #             pass
    #         elif isinstance(widget, tk.PanedWindow):
    #             # PanedWindow 内部可能还有子控件
    #             for child in widget.winfo_children():
    #                 self._update_widget_font_recursive(child, font)
    #         elif isinstance(widget, tk.Frame):
    #             for child in widget.winfo_children():
    #                 self._update_widget_font_recursive(child, font)
    #         else:
    #             # 其他通用控件
    #             if hasattr(widget, "winfo_children"):
    #                 for child in widget.winfo_children():
    #                     self._update_widget_font_recursive(child, font)
    #     except Exception as e:
    #         logger.warning(f"[DPI] 更新控件字体失败: {e} ({widget})")

    def scale_single_window(self,window, scale_factor):
        # 调整窗口尺寸
        width = window.winfo_width()
        height = window.winfo_height()
        window.geometry(f"{int(width*scale_factor)}x{int(height*scale_factor)}")

        # 遍历窗口控件缩放字体
        for child in window.winfo_children():
            if isinstance(child, tk.Label) or isinstance(child, tk.Entry):
                font = tkfont.nametofont(child.cget("font"))
                font.configure(size=int(font.cget("size") * scale_factor))
                child.configure(font=font)

        # Treeview 行高
        if isinstance(window, ttk.Treeview):
            style = ttk.Style(window)
            style.configure("Treeview", rowheight=int(22 * scale_factor))


    def scale_tk_window(self,window, scale_factor: float,name:str):
        """
        对单个 Tk 窗口进行 DPI 缩放
        ✅ 不使用 tk scaling
        ✅ 不影响其它窗口
        """

        # 初始化基准值
        if not hasattr(window, "_dpi_base"):
            base_tree_colwidths = []
            if hasattr(window, 'tree'):
                base_tree_colwidths = [window.tree.column(c)['width'] for c in window.tree['columns']]
            window._dpi_base = {
                "width": window.winfo_width(),
                "height": window.winfo_height(),
                "font_size": self.default_font_size,
                "tree_rowheight": 22,
                "tree_colwidths": base_tree_colwidths,
                "scale": get_window_dpi_scale(window)
            }
            logger.info(f"[DPI] {name} 初始化基准值: {window._dpi_base['scale']} 窗口 {window._dpi_base['width']}x{window._dpi_base['height']}, "
                        f"字体 {window._dpi_base['font_size']}pt, TreeView行高 {window._dpi_base['tree_rowheight']}")
            return

        base = window._dpi_base
        base_scale_factor = base["scale"]
        font_size = base["font_size"]
        rowheight = base["tree_rowheight"]

        if scale_factor == base_scale_factor:
            return
        logger.info(f"[DPI] {name} font_size: {font_size} rowheight:{rowheight} 变化: {base_scale_factor} to {scale_factor}")
        # scale_ratio = scale_factor / base["scale"]

        # # 1. 缩放窗口尺寸
        # width = window.winfo_width()
        # height = window.winfo_height()
        # new_w = int(width * scale_factor / base_scale_factor)
        # new_h = int(height * scale_factor / base_scale_factor)
        # logger.info(f'[DPI变化] scale_factor: {scale_factor:.2f} old_scale: {base_scale_factor:.2f} window_size: {width}x{height} -> {new_w}x{new_h}')
        # window.geometry(f"{new_w}x{new_h}")
        
        # --- 递归控件字体 ---
        def scale_widgets(parent,font_size):
            for child in parent.winfo_children():
                try:
                    base = tkfont.nametofont(child.cget("font"))
                    f = tkfont.Font(family=base.cget("family"), size=font_size, weight=base.cget("weight"), slant=base.cget("slant"))
                    child.configure(font=f)

                except Exception:
                    pass

                scale_widgets(child,font_size)

        scale_widgets(window,font_size)

        # --- Treeview 私有行高 ---
        # style = ttk.Style(window)
        # style_name = f"Treeview_{id(window)}"
        # style.configure(style_name, rowheight=rowheight)

        # if hasattr(self, "tree"):
        #     try:
        #         self.tree.configure(style=style_name)
        #     except Exception:
        #         pass
        # --- 3. 当前Treeview样式 ---

        if hasattr(window, "tree"):
            style = ttk.Style(window)
            style_name = f"{window.winfo_id()}.Treeview"
            style.configure(style_name, rowheight=rowheight)
            window.tree.configure(style=style_name)

    def scale_refesh_windows(self,scale_factor):

        if hasattr(self, "_concept_win") and self._concept_win:
            if self._concept_win.winfo_exists():
                logger.info(f"scale_tk_window  _concept_win窗口scale: {scale_factor}")
                self.scale_tk_window(self._concept_win,scale_factor,name="_concept_win")
        # 如果 KLineMonitor 存在且还没销毁，保存位置
        if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
            try:
                logger.info(f"scale_tk_window  kline_monitor窗口scale: {scale_factor}")
                self.scale_tk_window(self.kline_monitor,scale_factor,name="kline_monitor")
            except Exception:
                pass

        # --- 保存并关闭所有 monitor_windows（概念前10窗口）---
        if hasattr(self, "monitor_windows") and self.monitor_windows:
            for unique_code, win_info in list(self.monitor_windows.items()):
                win = win_info.get('toplevel')
                if win and win.winfo_exists():
                    try:
                        # 提取窗口名称用于保存位置
                        logger.info(f"scale_tk_window {unique_code}窗口scale: {scale_factor}")
                        self.scale_tk_window(win,scale_factor,name=unique_code)
                    except Exception as e:
                        logger.warning(f"scale_tk_window {unique_code}窗口scale:  {scale_factor} 失败: {e}")
        logger.info(f'scale_refesh_win  done')

        # --- 关闭所有 concept top10 窗口 --- 同 monitor_windows
        # if hasattr(self, "_pg_top10_window_simple"):
        #     for key, win_info in list(self._pg_top10_window_simple.items()):
        #         win = win_info.get("win")
        #         if win and win.winfo_exists():
        #             try:
        #                 # 如果窗口，先调用
        #                 logger.info(f'scale_tk_window {win_info.get("stock_info")} 窗口scale: {scale_factor}')
        #                 self.scale_tk_window(win,scale_factor)
        #             except Exception as e:
        #                 logger.warning(f'scale_tk_window {win_info.get("stock_info")}窗口scale {scale_factor} 失败: {e}')

    def _apply_scale_dpi_change(self, scale_factor: float):
        """
        当 DPI 变化时，同步缩放 Tk + Qt
        ✅ 禁止几何反复 resize
        ✅ 使用 Tk 原生 scaling
        ✅ 完整同步命名字体
        """

        try:
            # self.scale_refesh_windows(scale_factor)

            # 初始化基准值
            if not hasattr(self, "_dpi_base"):
                base_tree_colwidths = []
                if hasattr(self, 'tree'):
                    base_tree_colwidths = [self.tree.column(c)['width'] for c in self.tree['columns']]
                self._dpi_base = {
                    "width": self.winfo_width(),
                    "height": self.winfo_height(),
                    "font_size": self.default_font.cget("size"),
                    "tree_rowheight": 22,
                    "tree_colwidths": base_tree_colwidths,
                    "scale": self.scale_factor
                }
                logger.info(f"[DPI] 初始化基准值Main: 窗口 {self._dpi_base['width']}x{self._dpi_base['height']}, "
                            f"字体 {self._dpi_base['font_size']}pt, TreeView行高 {self._dpi_base['tree_rowheight']}")

            base = self._dpi_base
            font_size = base["font_size"]
            scale_ratio = scale_factor / base["scale"]

            # 1️⃣ 调整窗口大小
            width = self.winfo_width()
            height = self.winfo_height()
            new_w = int(width * scale_factor / self.scale_factor)
            new_h = int(height * scale_factor / self.scale_factor)
            logger.info(f'[DPI变化] scale_factor: {scale_factor:.2f} old_scale: {self.scale_factor:.2f} window_size: {width}x{height} -> {new_w}x{new_h}')
            self.geometry(f"{new_w}x{new_h}")

            old_scale = self.scale_factor or 1.0

            # --- 1. 防抖 ---
            if abs(scale_factor - old_scale) < 0.01:
                return

            self.scale_factor = scale_factor

            logger.info(
                f"[DPI变化] scale: {old_scale:.2f}x -> {scale_factor:.2f}x"
            )

            # ✅ 2. Tk 全局 scaling
            # Tk scaling = DPI / 72
            # scale = DPI / 96
            # => tk = scale * 96/72 = scale * 4/3
            # -------------------------------
            tk_scaling = scale_factor * (4/3)
            # self.tk.call("tk", "scaling", tk_scaling)

            logger.info(
                f"[DPI变化] 应该Tk scaling = {tk_scaling:.3f}"
            )

            # -------------------------------
            # ✅ 3. 同步所有 Tk 命名字体
            # -------------------------------

            # new_size = max(9, round(self.default_font_size * scale_ratio))
            new_size = max(9, round(font_size * scale_ratio))

            font_names = [
                "TkDefaultFont",
                "TkTextFont",
                "TkFixedFont",
                "TkHeadingFont",
                "TkMenuFont",
            ]

            for name in font_names:
                try:
                    f = tkfont.nametofont(name)
                    f.configure(size=new_size)
                except Exception:
                    pass

            # 保留你自定义字体引用
            self.default_font.configure(size=new_size)
            self.default_font_bold.configure(size=new_size)

            logger.info(
                f"[DPI变化] Tk font size: {self.default_font_size}pt -> {new_size}pt"
            )
            # self.default_font_size = new_size
            # -------------------------------
            # ✅ 4. Treeview 行高缩放
            # -------------------------------
            if hasattr(self, "tree"):
                try:
                    style = ttk.Style(self)
                    BASE_ROW_HEIGHT = 22
                    style.configure(
                        "Treeview",
                        rowheight=int(BASE_ROW_HEIGHT * scale_factor)
                    )
                except Exception as e:
                    logger.warning(f"[DPI变化] 设置 Treeview 行高失败: {e}")

            # -------------------------------
            # ✅ 5. Qt 窗口同步
            # -------------------------------

            self.on_dpi_changed_qt(scale_factor)

            logger.info(
                f"[DPI变化] ✅ DPI同步完成 Tk+Qt @ {scale_factor:.2f}x"
            )

            # self.scale_refesh_windows(scale_factor)

        except Exception as e:
            logger.error(
                f"[DPI变化] ❌ DPI同步失败: {e}",
                exc_info=True
            )
        finally:
            self.scale_factor = scale_factor


    # def _apply_scale_dpi_change_last_nostatus(self, scale_factor):
    #         """当检测到 DPI 变化时，自动放大/缩小主窗口及所有 UI 元素"""
    #         try:
    #             # 1️⃣ 调整窗口大小
    #             width = self.winfo_width()
    #             height = self.winfo_height()
    #             new_w = int(width * scale_factor / self.scale_factor)
    #             new_h = int(height * scale_factor / self.scale_factor)
    #             logger.info(f'[DPI变化] scale_factor: {scale_factor:.2f} old_scale: {self.scale_factor:.2f} window_size: {width}x{height} -> {new_w}x{new_h}')
    #             self.geometry(f"{new_w}x{new_h}")

    #             # 2️⃣ 调整字体大小
    #             old_size = self.default_font.cget("size")
    #             new_size = int(old_size * scale_factor / self.scale_factor)
    #             new_size = max(6, min(new_size, 16))  # 最小6 最大16
    #             self.default_font.configure(size=new_size)
    #             self.default_font_bold.configure(size=new_size)
    #             logger.info(f'[DPI变化] 字体大小: {old_size}pt -> {new_size}pt')

    #             # 3️⃣ 更新缩放因子
    #             old_scale = self.scale_factor
    #             self.scale_factor = scale_factor

    #             # 4️⃣ 触发 TreeView 列宽重新计算
    #             if hasattr(self, 'current_cols') and hasattr(self, 'tree'):
    #                 logger.info(f'[DPI变化] 重新计算 TreeView 列宽')
    #                 self._setup_tree_columns(
    #                     self.tree,
    #                     tuple(self.current_cols),
    #                     sort_callback=self.sort_by_column,
    #                     other={}
    #                 )

    #             # 5️⃣ 应用全局 Tkinter 缩放（字体和像素度量）
    #             tk_scaling_value = (scale_factor * DEFAULT_DPI) / 72.0
    #             self.tk.call('tk', 'scaling', tk_scaling_value)
    #             logger.info(f'[DPI变化] Tkinter scaling 设置为 {tk_scaling_value:.3f}（对应 {scale_factor:.2f}x DPI）')

    #             # 6️⃣ 🔑 设置 TreeView 行高（显式设置，确保正确缩放）
    #             if hasattr(self, 'tree'):
    #                 try:
    #                     style = ttk.Style(self)
    #                     BASE_ROW_HEIGHT = 22  # 基础行高像素
    #                     scaled_row_height = int(BASE_ROW_HEIGHT * scale_factor)
    #                     style.configure('Treeview', rowheight=scaled_row_height)
    #                     logger.info(f'[DPI变化] TreeView 行高设置为 {scaled_row_height}px')
    #                 except Exception as e_row:
    #                     logger.warning(f'[DPI变化] 设置 TreeView 行高失败: {e_row}')

    #             # 7️⃣ 🔑 重新配置 TreeView 列标题的字体（使其自动缩放）
    #             if hasattr(self, 'tree'):
    #                 try:
    #                     style = ttk.Style(self)
    #                     style.configure('Treeview.Heading', font=self.default_font)
    #                     logger.info(f'[DPI变化] TreeView 列标题字体已更新')
    #                 except Exception as e_heading:
    #                     logger.warning(f'[DPI变化] 更新 TreeView 列标题失败: {e_heading}')

    #             # 8️⃣ 🔑 重新配置状态栏标签字体（使其自动缩放）
    #             try:
    #                 for widget in self.winfo_children():
    #                     if isinstance(widget, tk.PanedWindow):
    #                         for child in widget.winfo_children():
    #                             for label in child.winfo_children():
    #                                 if isinstance(label, tk.Label):
    #                                     label.configure(font=self.default_font)
    #                 logger.info(f'[DPI变化] 状态栏标签字体已更新')
    #             except Exception as e_status:
    #                 logger.warning(f'[DPI变化] 更新状态栏标签失败: {e_status}')

    #             # 9️⃣ 🔑 重新配置 PG 窗口（概念分析）中的文字字体（PyQt TextItem）
    #             if hasattr(self, '_pg_windows'):
    #                 try:
    #                     for unique_code, w_dict in list(self._pg_windows.items()):
    #                         texts = w_dict.get("texts", [])
    #                         # 获取当前应用字体大小（已在步骤 2 中更新）
    #                         app_font = QtWidgets.QApplication.font()
    #                         font_size = app_font.pointSize()
                            
    #                         # 更新每个 TextItem 的字体
    #                         for text in texts:
    #                             try:
    #                                 text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
    #                             except Exception as e_text:
    #                                 logger.warning(f'[DPI变化] 更新 PG 文字字体失败: {e_text}')
    #                     logger.info(f'[DPI变化] PG 窗口文字字体已更新（{len(self._pg_windows)} 个窗口）')
    #                 except Exception as e_pg:
    #                     logger.warning(f'[DPI变化] 更新 PG 窗口失败: {e_pg}')

    #             logger.info(f"[DPI变化] ✅ 完成全部缩放：{old_scale:.2f}x -> {scale_factor:.2f}x (窗口/字体/TreeView/状态栏/PG总览)")

    #         except Exception as e:
    #             logger.error(f"[DPI变化] ❌ 应用缩放失败: {e}", exc_info=True)

    # def _apply_dpi_scaling_base(self):

    #     hwnd = self.winfo_id()
    #     scale = get_window_dpi_scale(hwnd)
    #     logger.info(f'scale: {scale}')
    #     # 应用到 Tk
    #     self.tk.call("tk", "scaling", scale)

    #     return scale

    def _apply_dpi_scaling(self,scale_factor=None):
        """自动计算并设置 Tkinter 的内部 DPI 缩放。"""
        # 获取系统的缩放因子 (例如 2.0)

        if not scale_factor: 
            self.scale_factor = get_window_dpi_scale(self)
            # self.scale_factor = get_windows_dpi_scale_factor()
            scale_factor = self.scale_factor
        else:
            self.scale_factor = scale_factor
        logger.info(f'_apply_dpi_scaling scale_factor : {scale_factor}')

        if scale_factor > 1.0:
            # Tkinter 'scaling' 值 = (系统 DPI / 72 DPI)
            logger.info(f'scale_factor apply: {scale_factor} {self.scale_factor}')
            tk_scaling_value = (scale_factor * DEFAULT_DPI) / 72.0 
            # 这一步会放大所有基于像素定义的组件尺寸和默认字体大小
            self.tk.call('tk', 'scaling', tk_scaling_value)

            logger.info(f"[初始化缩放] ✅ Tkinter scaling 设置为 {tk_scaling_value:.3f}（对应 {scale_factor}x DPI）")

            # ✅ 不再需要手动设置 ttk.Style rowheight
            # tk.call('tk', 'scaling') 已经自动处理了所有的像素度量和字体
            # 手动设置 rowheight 会导致 scaling 失效或冲突
            # 不在启动时修改默认字体或标签字体；仅使用 tk scaling 改变像素度量。
            # 所有字体、Treeview 行高与 Label 的显式调整将在实际发生 DPI 变化时
            # 由 `_apply_scale_dpi_change(scale_factor)` 统一处理，避免启动时字体被放大。
            # 但是为避免字体变大后行高不足导致文字重叠，仍需确保 Treeview 的 rowheight 足够
            try:
                style = ttk.Style(self)
                BASE_ROW_HEIGHT = 22
                scaled_row_height = int(BASE_ROW_HEIGHT * scale_factor)
                style.configure('Treeview', rowheight=scaled_row_height)
                # 如果主 tree 已创建，确保样式应用
                try:
                    if hasattr(self, 'tree') and self.tree is not None:
                        # 直接调用 configure 以确保已存在 Treeview 更新
                        self.tree.configure(selectmode=self.tree.cget('selectmode'))
                except Exception:
                    pass
                logger.info(f"[初始化缩放] Treeview 行高设置为 {scaled_row_height}px")
            except Exception as e_rowinit:
                logger.warning(f"[初始化缩放] 设置 Treeview 行高失败: {e_rowinit}")
        return scale_factor


    def bind_treeview_column_resize(self):
        def on_column_release(event):
            # # 获取当前列宽
            # col_widths = {col: self.tree.column(col)["width"] for col in self.tree["columns"]}
            # logger.info("当前列宽：", col_widths)

            # # 如果需要，可以单独保存name列宽
            # if "name" in col_widths:
            #     self._name_col_width = col_widths["name"]
            #     logger.info("name列宽更新为:", self._name_col_width)

            # 只记录 name 列宽
            if "name" in self.tree["columns"]:
                self._name_col_width = self.tree.column("name")["width"]
                # logger.info("name列宽更新为:", self._name_col_width)

        self.tree.bind("<ButtonRelease-1>", on_column_release)

    def reload_cfg_value(self):
        global marketInit,marketblk,scale_offset,resampleInit
        global duration_sleep_time,write_all_day_date,detect_calc_support
        conf_ini= cct.get_conf_path('global.ini')
        if not conf_ini:
            logger.info("global.ini 加载失败，程序无法继续运行")

        CFG = cct.GlobalConfig(conf_ini)

        marketInit = CFG.marketInit
        marketblk = CFG.marketblk
        scale_offset = CFG.scale_offset
        resampleInit = CFG.resampleInit
        duration_sleep_time = CFG.duration_sleep_time
        write_all_day_date = CFG.write_all_day_date
        detect_calc_support = CFG.detect_calc_support
        alert_cooldown = CFG.alert_cooldown

        saved_width,saved_height = CFG.saved_width,CFG.saved_height 
        logger.info(f"reload cfg marketInit : {marketInit} marketblk: {marketblk} scale_offset: {scale_offset} saved_width:{saved_width},{saved_height} duration_sleep_time:{duration_sleep_time} detect_calc_support:{detect_calc_support}")

    def get_scaled_value(self):
        """返回当前的缩放因子（用于 TreeView 列宽计算）"""
        # ✅ 直接返回 scale_factor，不要做奇怪的减法
        global scale_offset
        sf = self.scale_factor
        offset = float(scale_offset)
        # if sf <= 1.25:
        #     offset = 0.15
        # elif sf < 1.5:
        #     offset = 0.25
        # elif sf < 2:
        #     offset = 0.25
        # else:
        #     offset = 0.25
        return sf - offset

    def _setup_tree_columns(self,tree, cols, sort_callback=None, other={}):
        """
        通用 Treeview 列初始化函数
        - 自动绑定点击排序
        - 按列名自动分配宽度
        - 自动应用 DPI 缩放
        - 可自定义 name 列宽度
        """
        # co2int = ['ra', 'ral', 'fib', 'fibl', 'op', 'ratio', 'ra']
        # col_scaled = self.get_scaled_value() 
        # width = int(60 * col_scaled)  # 缩小一点，保持紧凑
        # minwidth = int(30 * col_scaled)
        # stretch = False

        # if col in co2int or col in co2width:
        #     width = int(40 * col_scaled)  # 缩小一点，保持紧凑
        #     minwidth = int(25 * col_scaled)
        #     # stretch = self.auto_adjust_column
        #     stretch = not self.dfcf_var.get()
        # else:
        #     width = int(60 * col_scaled)  # 更小的宽度
        #     minwidth = int(30 * col_scaled)
        #     stretch = not self.dfcf_var.get()
        # tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=stretch)
        co2int = ['ra', 'ral', 'fib', 'fibl', 'op', 'ratio', 'ra']
        co2width = ['boll', 'kind', 'red']
        co3other = ['MainU']
        col_scaled = self.get_scaled_value() 

        for col in cols:
            # 绑定排序点击事件
            if sort_callback:
                tree.heading(col, text=col, command=lambda _col=col: sort_callback(_col, False))
            else:
                tree.heading(col, text=col)
            # 动态列宽计算
            if col == "code":
                # width = int((name_width or 100) * col_scaled)
                width = int(100 * col_scaled)
                minwidth = int(60 * col_scaled)
                stretch = False
            elif col == "name":
                # width = int((name_width or 100) * col_scaled)
                width = int(getattr(self, "_name_col_width", 80*col_scaled))  # 使用记录的 name 宽度
                minwidth = int(60 * col_scaled)
                stretch = False
            elif col in co3other:
                width = int(60 * col_scaled)  # 缩小一点，保持紧凑
                minwidth = int(30 * col_scaled)
                stretch = False

            elif col in co2int or col in co2width:
                width = int(40 * col_scaled)  # 缩小一点，保持紧凑
                minwidth = int(25 * col_scaled)
                # stretch = self.auto_adjust_column
                stretch = not self.dfcf_var.get()
            else:
                width = int(60 * col_scaled)  # 更小的宽度
                minwidth = int(30 * col_scaled)
                stretch = not self.dfcf_var.get()
            tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=stretch)

    def update_treeview_cols(self, new_cols):
        try:
            # ✅ 1. 安全检查 - 确保df_all存在且有数据
            if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
                logger.warning("⚠️ df_all为空,无法更新列配置,将在数据加载后自动应用")
                # 保存列配置,等数据加载后再应用
                self._pending_cols = new_cols
                return
            
            # 2. 过滤出有效的列(只保留df_all中存在的列)
            valid_cols = [c for c in new_cols if c in self.df_all.columns]
            
            # 如果没有有效列,使用默认列
            if not valid_cols:
                logger.warning(f"⚠️ 请求的列都不存在于数据中: {new_cols}")
                logger.warning(f"可用列: {list(self.df_all.columns)}")
                # 使用前5列作为默认
                valid_cols = list(self.df_all.columns)[:5]
            
            # 确保code列在第一位
            if 'code' not in valid_cols:
                if 'code' in self.df_all.columns:
                    valid_cols = ["code"] + valid_cols
                else:
                    # 如果没有code列,使用index
                    logger.info("ℹ️ 数据中没有code列,将使用index")

            # 相同就跳过
            if valid_cols == getattr(self, 'current_cols', []):
                logger.info("ℹ️ 列配置未变化,跳过更新")
                return

            self.current_cols = valid_cols
            cols = tuple(self.current_cols)
            
            logger.info(f"✅ 更新列配置: {len(cols)}列 - {cols[:5]}...")

            # ✅ 3. 先清空列配置,避免冲突
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()

            # 4. 设置新列
            self.tree["columns"] = cols
            self.tree["displaycolumns"] = cols
            self.tree.configure(show="headings")

            # 5. 设置列宽
            if not hasattr(self, "_name_col_width"):
                self._name_col_width = int(80*self.get_scaled_value())
                logger.info(f'_name_col_width : {int(80*self.get_scaled_value())}')

            logger.info(f'update_treeview_cols self.scale_factor : {self.scale_factor}')
            self._setup_tree_columns(
                self.tree,
                cols,
                sort_callback=self.sort_by_column,
                other={}
            )

            # 6. 延迟刷新
            self.tree.after(100, self.refresh_tree)
            self.tree.after(500, self.bind_treeview_column_resize)

        except Exception as e:
            traceback.print_exc()
            logger.error(f"❌ 更新 Treeview 列失败：{e}")
            # 尝试恢复到之前的列配置
            if hasattr(self, 'current_cols') and self.current_cols:
                try:
                    self.tree["columns"] = tuple(self.current_cols)
                    self.tree["displaycolumns"] = tuple(self.current_cols)
                    logger.info("✅ 已恢复到之前的列配置")
                except:
                    pass



    # def update_treeview_cols_remember_col(self, new_cols):
    #     try:
    #         # 1. 合法列
    #         valid_cols = [c for c in new_cols if c in self.df_all.columns]
    #         if 'code' not in valid_cols:
    #             valid_cols = ["code"] + valid_cols

    #         # 相同就跳过
    #         if valid_cols == self.current_cols:
    #             return

    #         self.current_cols = valid_cols

    #         # 2. 暂时清空列
    #         self.tree["displaycolumns"] = ()
    #         self.tree["columns"] = ()
    #         self.tree.update_idletasks()

    #         # 3. 重新配置列
    #         cols = tuple(self.current_cols)
    #         self.tree["columns"] = cols
    #         self.tree["displaycolumns"] = cols
    #         self.tree.configure(show="headings")

    #         # 4. 设置列宽，只在第一次初始化或新增列时设置宽度
    #         if not hasattr(self, "_col_widths"):
    #             self._col_widths = {}

    #         for col in cols:
    #             if col not in self._col_widths:
    #                 # 初始化宽度
    #                 self._col_widths[col] = 80 if col == "name" else 60
    #             self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
    #             self.tree.column(col, width=self._col_widths[col], anchor="center", minwidth=50,
    #                              stretch=(col != "name"))

    #         # 🔹 5. 自动调整列宽（可选）
    #         # self.adjust_column_widths()
    #         # 5. 延迟刷新
    #         self.tree.after(100, self.refresh_tree)

    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
    #         logger.info("更新 Treeview 列失败：", e)



    # def update_treeview_cols(self, new_cols):
    #     try:
    #         # 🔹 1. 保证 new_cols 合法：必须存在于 df_all.columns 中
    #         valid_cols = [c for c in new_cols if c in self.df_all.columns]
    #         if 'code' not in valid_cols:
    #             valid_cols = ["code"] + valid_cols

    #         # 如果完全相同就跳过
    #         if valid_cols == self.current_cols:
    #             return

    #         # logger.info(f"[update_treeview_cols] current={self.current_cols}, new={valid_cols}")

    #         self.current_cols = valid_cols
    #         # cols = tuple(self.current_cols)
    #         # self.after_idle(lambda: self.reset_tree_columns(self.tree, cols, self.sort_by_column))

    #         # 🔹 2. 暂时清空列，避免 Invalid column index 残留
    #         self.tree["displaycolumns"] = ()
    #         self.tree["columns"] = ()
    #         self.tree.update_idletasks()

    #         # 🔹 3. 重新配置列
    #         cols = tuple(self.current_cols)
    #         self.tree["columns"] = cols
    #         self.tree["displaycolumns"] = cols
    #         self.tree.configure(show="headings")

    #         # # 🔹 4. 重新设置表头和列宽
    #         # for col in cols:
    #         #     width = 120 if col == "name" else 80
    #         #     self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
    #         #     self.tree.column(col, width=width, anchor="center", minwidth=50)

    #         # 获取当前列宽
    #         col_widths = {col: self.tree.column(col)["width"] for col in self.tree["columns"]}

    #         for col in cols:
    #             width = col_widths.get(col, 120 if col == "name" else 80)
    #             self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
    #             self.tree.column(col, width=width, anchor="center", minwidth=50)

    #         # 🔹 5. 自动调整列宽（可选）
    #         # self.adjust_column_widths()

    #         # 🔹 6. 延迟刷新数据
    #         self.tree.after(100, self.refresh_tree)

    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
    #         logger.info("更新 Treeview 列失败：", e)


    


    # 防抖 resize（避免重复刷新）
    # ---------------------------
    def _on_open_column_manager(self):
        if self._open_column_manager_job:
            self.after_cancel(self._open_column_manager_job)
        self._open_column_manager_job = self.after(1000, self.open_column_manager)

    def open_column_manager(self):
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            # 已存在，直接激活
            # self.ColumnSetManager.deiconify()
            # self.ColumnSetManager.lift()
            # self.ColumnSetManager.focus_set()
            # if not self.ColManagerconfig:
            #     self.ColManagerconfig = load_display_config()
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config()
                # 创建新窗口
                self.ColumnSetManager = ColumnSetManager(
                    self,
                    self.df_all.columns,
                    self.ColManagerconfig,
                    self.update_treeview_cols,  # 回调更新函数
                    default_cols=self.current_cols,  # 默认列
                        )
                # 关闭时清理引用
                self.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.on_close_column_manager)
            else:
                self.after(1000,self._on_open_column_manager)

    def open_column_manager_init(self):
        # global DISPLAY_COLS
        def _on_open_column_manager_init():
            if self._open_column_manager_job:
                self.after_cancel(self._open_column_manager_job)
            self._open_column_manager_job = self.after(1000, self.open_column_manager_init)
        
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            # 已存在，直接激活
            # self.ColumnSetManager.deiconify()
            # self.ColumnSetManager.lift()
            # self.ColumnSetManager.focus_set()
            # if not self.ColManagerconfig:
            #     self.ColManagerconfig = load_display_config()
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config()
                # 创建新窗口
                self.ColumnSetManager = ColumnSetManager(
                    self,
                    self.df_all.columns,
                    self.ColManagerconfig,
                    self.update_treeview_cols,  # 回调更新函数
                    default_cols=self.current_cols,  # 默认列
                    auto_apply_on_init=True     #   ✅ 初始化自动执行 apply_current_set()
                        )
                # 关闭时清理引用
                self.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.on_close_column_manager)
                # DISPLAY_COLS = self.current_cols
            else:
                self.after(1000,_on_open_column_manager_init)

    def on_close_column_manager(self):
        if self.ColumnSetManager is not None:
            self.ColumnSetManager.destroy()
            self.ColumnSetManager = None
            self._open_column_manager_job = None

    # def get_following_concepts_by_correlation(self, code, top_n=10):
    #     df_all = self.df_all.copy()
        
    #     try:
    #         # stock_percent = df_all.loc[df_all['code'] == code, 'percent'].values[0]
    #         stock_percent = df_all.loc[code, 'percent']
    #     except IndexError:
    #         return []
        
    #     # 构建概念字典：概念 -> 股票涨幅列表
    #     concept_dict = {}
    #     for idx, row in df_all.iterrows():
    #         categories = [c.strip() for c in str(row['category']).split(';') if c.strip()]
    #         for c in categories:
    #             concept_dict.setdefault(c, []).append(row['percent'])
        
    #     # 计算跟随指数：目标股票涨幅与概念板块涨幅的匹配程度
    #     concept_score = []
    #     for c, percents in concept_dict.items():
    #         percents = [p for p in percents if p is not None]
    #         if not percents:
    #             continue
    #         # 概念涨幅平均值
    #         avg_percent = sum(percents) / len(percents)
    #         # 股票涨幅超过概念板块平均涨幅的比例（跟随指数）
    #         follow_ratio = sum(1 for p in percents if p <= stock_percent) / len(percents)
    #         # 可以结合平均涨幅和跟随比例作为得分
    #         score = avg_percent * follow_ratio
    #         concept_score.append((c, score, avg_percent, follow_ratio))
        
    #     # 按得分排序
    #     concept_score.sort(key=lambda x: x[1], reverse=True)
        
    #     # 返回前 top_n
    #     return concept_score[:top_n]

    # def get_stock_percent(df_all, code=None):
    #     # --- 确保 percent 列存在 ---
    #     if 'percent' not in df_all.columns and 'per1d' in df_all.columns:
    #         df_all['percent'] = df_all['per1d']
    #     elif 'percent' in df_all.columns and 'per1d' in df_all.columns:
    #         # percent 为 NaN 或 0 时用 per1d 补充
    #         df_all['percent'] = df_all.apply(
    #             lambda r: r['per1d'] if pd.isna(r['percent']) or r['percent']==0 else r['percent'],
    #             axis=1
    #         )

    #     # --- 处理 code ---
    #     if code is None or code not in df_all.index:
    #         # 取 percent 最大的股票
    #         # 如果 percent 全为 0，再用 per1d 最大值
    #         if df_all['percent'].max() == 0 and 'per1d' in df_all.columns:
    #             max_idx = df_all['per1d'].idxmax()
    #             max_percent = df_all.loc[max_idx, 'per1d']
    #         else:
    #             max_idx = df_all['percent'].idxmax()
    #             max_percent = df_all.loc[max_idx, 'percent']
    #         return max_idx, max_percent
    #     else:
    #         # 获取指定股票涨幅
    #         percent = df_all.loc[code, 'percent']
    #         # 如果 percent 为 0 或 NaN，使用 per1d
    #         if (percent == 0 or pd.isna(percent)) and 'per1d' in df_all.columns:
    #             percent = df_all.loc[code, 'per1d']
    #         return code, percent
    # def get_stock_code_none(self, code=None):
    #     # --- 处理 code ---
    #     df_all = self.df_all.copy()
    #     if code is None or code not in df_all.index:
    #         # 取 percent 最大的股票
    #         # 如果 percent 全为 0，再用 per1d 最大值

    #         if df_all['percent'].max() == 0 and 'per1d' in df_all.columns:
    #             max_idx = df_all['per1d'].idxmax()
    #             percent = df_all.loc[max_idx, 'per1d']
    #         else:
    #             max_idx = df_all['percent'].idxmax()
    #             percent = df_all.loc[max_idx, 'percent']
    #         return max_idx, percent
    #     else:
    #         # 获取指定股票涨幅
    #         percent = df_all.loc[code, 'percent']
    #         # 如果 percent 为 0 或 NaN，使用 per1d
    #         # if (percent == 0 or pd.isna(percent)) and 'per1d' in df_all.columns:
    #         #     percent = df_all.loc[code, 'per1d']
    #         return code, percent

    # def get_stock_code_none(self, code=None):
    #     df_all = self.df_all.copy()
    #     # --- 如果没有 percent 列，用 per1d 补充 ---
    #     if 'percent' not in df_all.columns and 'per1d' in df_all.columns:
    #         df_all['percent'] = df_all['per1d']
    #     elif 'percent' in df_all.columns and 'per1d' in df_all.columns:
    #         df_all['percent'] = df_all.apply(
    #             lambda r: r['per1d'] if pd.isna(r['percent']) or r['percent']==0 else r['percent'],
    #             axis=1
    #         )

    #     # --- 判断市场是否开盘 ---
    #     zero_ratio = (df_all['percent'] == 0).sum() / len(df_all)
    #     use_per1d = zero_ratio > 0.5 and 'per1d' in df_all.columns
    def get_stock_code_none(self, code=None):
        df_all = self.df_all.copy()

        # --- 如果没有 percent 列，用 per1d 补充 ---
        if 'percent' not in df_all.columns and 'per1d' in df_all.columns:
            df_all['percent'] = df_all['per1d']
        elif 'percent' in df_all.columns and 'per1d' in df_all.columns:
            # 优先使用非空且非0的percent，否则用per1d
            df_all['percent'] = df_all.apply(
                lambda r: r['per1d'] if pd.isna(r['percent']) or r['percent'] == 0 else r['percent'],
                axis=1
            )

        # --- 判断是否需要用 per1d 替换 ---
        zero_ratio = (df_all['percent'] == 0).sum() / len(df_all)
        extreme_ratio = ((df_all['percent'] >= 100) | (df_all['percent'] <= -100)).mean()

        # 如果停牌占比高 或 有 ±100% 的异常，使用 per1d
        use_per1d = (zero_ratio > 0.5 or extreme_ratio > 0.01) and 'per1d' in df_all.columns

        if use_per1d:
            df_all['percent'] = df_all['per1d']

        # --- 处理 code ---
        if code is None or code not in df_all.index:
            if use_per1d:
                max_idx = df_all['per1d'].idxmax()
                percent = df_all.loc[max_idx, 'per1d']
            else:
                max_idx = df_all['percent'].idxmax()
                percent = df_all.loc[max_idx, 'percent']
            return max_idx, percent
        else:
            percent = df_all.loc[code, 'percent']
            if (percent == 0 or pd.isna(percent)) and use_per1d:
                percent = df_all.loc[code, 'per1d']
            return code, percent

    # def init_global_concept_data(self, win, concepts, avg_percents, scores, follow_ratios, force_reset=False):
    def init_global_concept_data(self, concepts, avg_percents, scores, follow_ratios, force_reset=False):
        """
        全局初始化概念数据
        force_reset: True 表示强制重新加载当天数据
        """
        today = datetime.now().date()
        
        # 判断是否需要重置
        need_reset = force_reset or not hasattr(self, "_concept_data_loaded") or getattr(self, "_concept_data_date", None) != today

        if need_reset:
            self._concept_data_loaded = True
            self._concept_data_date = today

            # 读取当天所有 concept 数据
            all_data = load_all_concepts_pg_data()
            # all_data = {}
            self._global_concept_init_data = {}
            self._global_concept_prev_data = {}
            for c_name, (init_data, prev_data) in all_data.items():
                if init_data:
                    self._global_concept_init_data[c_name] = {k: np.array(v) for k, v in init_data.items()}
                if prev_data:
                    self._global_concept_prev_data[c_name] = {k: np.array(v) for k, v in prev_data.items()}

            for i, c_name in enumerate(concepts):
                # 初始化 base_data
                if c_name not in self._global_concept_init_data:
                    # 全局没有数据，初始化基础数据
                    base_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_init_data[c_name] = base_data
                    # logger.info("[DEBUG] 已初始概念数据(_init_prev_concepts_data)")
        else:
            for i, c_name in enumerate(concepts):
                # 初始化 prev_data
                if c_name not in self._global_concept_prev_data:
                    prev_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_prev_data[c_name] = prev_data
                    # logger.info("[DEBUG] 已初始概念数据(_init_prev_concepts_data)")
            logger.debug(f"[init_global_concept_data] 新增 prev_data: {concepts[0]}")


    def get_following_concepts_by_correlation(self, code, top_n=10):
        def compute_follow_ratio(percents, stock_percent):
            """
            percents: 概念内所有股票涨幅列表
            stock_percent: 目标股票或大盘涨幅
            """
            percents = np.array(percents)
            stock_sign = np.sign(stock_percent)
            stock_sign = 1 if stock_sign > 0 else (-1 if stock_sign < 0 else 0)
            # 概念内每只股票是否跟随
            follow_flags = np.sign(percents) == stock_sign
            return follow_flags.sum() / len(percents)
        # logger.info(f"by_correlation [Debug] df_all_hash={df_hash(self.df_all)} len={len(self.df_all)} time={datetime.now():%H:%M:%S}")
        df_all = self.df_all.copy()
        # --- ✅ 修正涨幅替代逻辑 ---
        if 'percent' in df_all.columns and 'per1d' in df_all.columns:
            df_all['percent'] = df_all.apply(
                lambda r: r['per1d']
                if (r.get('percent', 0) == 0 or pd.isna(r.get('percent', 0)))
                else r['percent'],
                axis=1
            )
        elif 'percent' not in df_all.columns and 'per1d' in df_all.columns:
            df_all['percent'] = df_all['per1d']
        elif 'percent' not in df_all.columns:
            raise ValueError("DataFrame 必须包含 'percent' 或 'per1d' 列")

        # --- 获取目标股票涨幅 ---
        try:
            # if code in None:
            #     df_all.loc[code, 'percent']
            # else:
            stock_percent = df_all.loc[code, 'percent']
            stock_row = df_all.loc[code]
            # code, stock_percent = get_stock_percent(self.df_all,code)
            # stock_row = df_all.loc[code]
        except Exception:
            try:
                # stock_row = df_all.loc[df_all['code'] == code].iloc[0]
                stock_row = df_all.loc[code]
                stock_percent = stock_row['percent']
            except Exception:
                logger.info(f"[WARN] 未找到 {code} 的数据")
                return []
        # --- 获取股票所属的概念列表 ---
        # stock_row = df_all.loc[code]
        stock_categories = [
            c.strip() for c in str(stock_row.get('category', '')).split(';') if c.strip()
        ]
        # logger.info(f'stock_categories : {stock_categories}')
        if not stock_categories:
            logger.info(f"[INFO] {code} 无概念数据。")
            return []

        # concept_dict = {}
        # for idx, row in df_all.iterrows():
        #     categories = [c.strip() for c in str(row['category']).split(';') if c.strip()]
        #     for c in categories:
        #         concept_dict.setdefault(c, []).append(row['percent'])
        concept_dict = {}
        for idx, row in df_all.iterrows():
            # 拆分概念，去掉空字符串或 '0'
            categories = [
                c.strip() for c in str(row.get('category', '')).split(';') 
                if c.strip() and c.strip() != '0'
            ]
            for c in categories:
                concept_dict.setdefault(c, []).append(row['percent'])

        # --- 丢弃成员少于 4 的概念 ---
        concept_dict = {k: v for k, v in concept_dict.items() if len(v) >= 4}


        # --- top_n==1 时，只保留股票所属概念 ---
        if top_n == 1:
            concept_dict = {c: concept_dict[c] for c in stock_categories if c in concept_dict}
            # logger.info(f'top_n == 1 stock_categories : {stock_categories}  concept_dict:{concept_dict}')
        # --- 计算概念强度 ---
        concept_score = []
        for c, percents in concept_dict.items():
            percents = [p for p in percents if not pd.isna(p)]
            if not percents:
                continue

            avg_percent = sum(percents) / len(percents)
            # follow_ratio = sum(1 for p in percents if p <= stock_percent) / len(percents)
            follow_ratio = compute_follow_ratio(percents, stock_percent)
            score = avg_percent * follow_ratio
            concept_score.append((c, score, avg_percent, follow_ratio))

        # --- 排序并返回 ---
        concept_score.sort(key=lambda x: x[1], reverse=True)
        concepts = [c[0] for c in concept_score]
        scores = np.array([c[1] for c in concept_score])
        avg_percents = np.array([c[2] for c in concept_score])
        follow_ratios = np.array([c[3] for c in concept_score])
        # 仅在工作日 9:25 后第一次刷新时重置
        now = datetime.now()
        now_t = int(now.strftime("%H%M"))
        today = now.date()

        force_reset = False

        # 检查是否跨天，跨天就重置阶段标记
        if getattr(self, "_concept_data_date", None) != today:
            self._concept_data_date = today
            self._concept_first_phase_done = False
            self._concept_second_phase_done = False

        # 第一阶段：9:15~9:24触发一次
        if cct.get_trade_date_status() and (915 <= now_t <= 924) and not getattr(self, "_concept_first_phase_done", False):
            self._concept_first_phase_done = True
            force_reset = True
            logger.info(f"{today} 触发 9:15~9:24 第一阶段刷新")

        # 第二阶段：9:25 后触发一次
        elif cct.get_trade_date_status() and (now_t >= 925) and not getattr(self, "_concept_second_phase_done", False):
            self._concept_second_phase_done = True
            force_reset = True
            logger.info(f"{today} 触发 9:25 第二阶段全局重置")

        self.init_global_concept_data(concept_score, avg_percents, scores, follow_ratios, force_reset)

        # logger.info(f'concept_score[:10]:{concept_score[:10]}')
        return concept_score[:10]



    def open_alert_editorAuto(self, stock_info, new_rule=False):
        code = stock_info.get("code")
        name = stock_info.get("name")
        price = stock_info.get("price", 0.0)
        change = stock_info.get("change", 0.0)
        volume = stock_info.get("volume", 0)

        # 如果是新建规则，检查是否已有历史报警
        rules = self.alert_manager.get_rules(code)
        if new_rule or not rules:
            rules = [
                {"field": "价格", "op": ">=", "value": price, "enabled": True, "delta": 1},
                {"field": "涨幅", "op": ">=", "value": change, "enabled": True, "delta": 1},
                {"field": "量", "op": ">=", "value": volume, "enabled": True, "delta": 100}
            ]
            self.alert_manager.set_rules(code, rules)

        # 创建 Toplevel 编辑窗口，自动填充规则
        editor = tk.Toplevel(self)
        editor.title(f"设置报警规则 - {name} {code}")
        editor.geometry("500x300")
        editor.focus_force()
        editor.grab_set()

        # 创建规则 Frame 并渲染 rules
        # ...（这里可以复用你现有 add_rule、保存/删除按钮逻辑）


    def open_alert_editor(parent, stock_info=None, new_rule=True):
        """
        打开报警规则编辑窗口
        :param parent: 主窗口
        :param stock_info: 选中的股票信息 (tuple/list)，比如 (code, name, price, ...)
        :param new_rule: True=新建规则，False=编辑规则
        """
        win = tk.Toplevel(parent)
        win.title("新建报警规则" if new_rule else "编辑报警规则")
        win.geometry("400x300")

        # 如果 stock_info 有内容，在标题里显示
        stock_str = ""
        if stock_info:
            try:
                code, name = stock_info[0], stock_info[1]
                stock_str = f"{code} {name}"
            except Exception:
                stock_str = str(stock_info)
        if stock_str:
            # tk.Label(win, text=f"股票: {stock_str}", font=("Arial", 12, "bold")).pack(pady=1)
            tk.Label(win, text=f"股票: {stock_str}", font=self.default_font_bold).pack(pady=1)

        # 报警条件输入区
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(frame, text="条件类型:").grid(row=0, column=0, sticky="w")
        cond_type_var = tk.StringVar(value="价格大于")
        cond_type_entry = ttk.Combobox(frame, textvariable=cond_type_var,
                                       values=["价格大于", "价格小于", "涨幅超过", "跌幅超过"], state="readonly")
        cond_type_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(frame, text="阈值:").grid(row=1, column=0, sticky="w")
        threshold_var = tk.StringVar(value="")
        threshold_entry = tk.Entry(frame, textvariable=threshold_var)
        threshold_entry.grid(row=1, column=1, sticky="ew")

        # 保存按钮
        def save_rule():
            rule = {
                "stock": stock_str,
                "cond_type": cond_type_var.get(),
                "threshold": threshold_var.get()
            }
            logger.info(f"保存报警规则: {rule}")
            stock_code = rule.get("stock")  # 或者从 UI 里获取选中的股票代码
            logger.info(f'stock_code:{stock_code}')
            parent.alert_manager.save_rule(stock_code['name'],rule)  # 保存到 AlertManager
            messagebox.showinfo("成功", "规则已保存")
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="保存", command=save_rule).pack(side="left", padx=5)
        tk.Button(btn_frame, text="取消", command=win.destroy).pack(side="left", padx=5)

    def _build_ui(self, ctrl_frame):

        # Market 下拉菜单
        tk.Label(ctrl_frame, text="Market:").pack(side="left", padx=2)

        # 显示中文 → 内部 code + blkname
        self.market_map = {
            "全部": {"code": "all", "blkname": "061.blk"},
            "上证": {"code": "sh",  "blkname": "062.blk"},
            "深证": {"code": "sz",  "blkname": "066.blk"},
            "创业板": {"code": "cyb", "blkname": "063.blk"},
            "科创板": {"code": "kcb", "blkname": "064.blk"},
            "北证": {"code": "bj",  "blkname": "065.blk"},
            "indb": {"code": "indb",  "blkname": "066.blk"},
        }

        self.market_combo = ttk.Combobox(
            ctrl_frame,
            values=list(self.market_map.keys()),  # 显示中文
            width=8,
            state="readonly"
        )

        values = list(self.market_map.keys())

        # 根据 code 找 index
        idx = next(
            (i for i, k in enumerate(values)
             if self.market_map[k]["code"] == marketInit),
            0   # 找不到则回退到 "全部"
        )

        self.market_combo.current(idx)  # 默认 "全部"
        self.market_combo.pack(side="left", padx=5)

        # 绑定选择事件，存入 GlobalValues
        def on_market_select(event=None):
            market_cn = self.market_combo.get()
            market_info = self.market_map.get(market_cn, {"code": "all", "blkname": "061.blk"})
            self.global_values.setkey("market", market_info["code"])
            self.global_values.setkey("blkname", market_info["blkname"])
            logger.info(f"选择市场: {market_cn}, code={market_info['code']}, blkname={market_info['blkname']}")

        self.market_combo.bind("<<ComboboxSelected>>", on_market_select)
        # ✅ 关键：同步一次状态
        on_market_select()
        
        tk.Label(ctrl_frame, text="stkey:").pack(side="left", padx=2)
        self.st_key_sort_value = tk.StringVar()
        self.st_key_sort_entry = tk.Entry(ctrl_frame, textvariable=self.st_key_sort_value,width=5)
        self.st_key_sort_entry.pack(side="left")
        # 绑定回车键提交
        self.st_key_sort_entry.bind("<Return>", self.on_st_key_sort_enter)
        self.st_key_sort_value.set(self.st_key_sort) 
        
        # --- resample 下拉框 ---
        resampleValues = ["d",'3d', "w", "m"]
        tk.Label(ctrl_frame, text="resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=resampleValues, width=3)
        self.resample_combo.current(resampleValues.index(self.global_values.getkey("resample")))
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        # --- 刷新按钮 ---
        # tk.Button(ctrl_frame, text="刷新", command=self.refresh_data).pack(side="left", padx=5)

        # 在 __init__ 中

        # self.search_var = tk.StringVar()
        # self.search_combo = ttk.Combobox(ctrl_frame, textvariable=self.search_var, values=self.search_history, width=30)
        # self.search_combo.pack(side="left", padx=5)
        # self.search_combo.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_search())  # 选中历史也刷新
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)


        # 在初始化时（StockMonitorApp.__init__）创建并注册：
        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=logger)
        set_global_manager(self.alert_manager)

        # --- 控件区 ---
        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # --- 底部搜索框 2 ---
        bottom_search_frame = tk.Frame(self)
        bottom_search_frame.pack(side="bottom", fill="x", pady=1)

        # # --- 顶部工具栏 ---
        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # # 功能按钮
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=5)

        # top_search_frame = tk.Frame(ctrl_frame)
        # top_search_frame.pack(side="left", fill="x", expand=True, padx=5)
        # 搜索框 1（在顶部）

     
        # self.combobox1["values"] = values1
        # self.combobox2["values"] = values2

        self.search_history1 = []
        self.search_history2 = []
        self.search_history3 = []
        self._search_job = None

        self.search_var1 = tk.StringVar()
        self.search_combo1 = ttk.Combobox(bottom_search_frame, textvariable=self.search_var1, values=self.search_history1, width=30)
        self.search_combo1.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo1.bind("<Return>", lambda e: self.apply_search())
        self.search_combo1.bind("<<ComboboxSelected>>", lambda e: self.apply_search())
        self.search_var1.trace_add("write", self._on_search_var_change)


        self.search_var2 = tk.StringVar()
        self.search_combo2 = ttk.Combobox(ctrl_frame, textvariable=self.search_var2, values=self.search_history2, width=30)
        self.search_combo2.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo2.bind("<Return>", lambda e: self.apply_search())
        self.search_combo2.bind("<<ComboboxSelected>>", lambda e: self.apply_search())
        self.search_var2.trace_add("write", self._on_search_var_change)

        self.search_combo2.bind("<Button-3>", self.on_right_click_search_var2)

        self.query_manager = QueryHistoryManager(
            self,
            search_var1=self.search_var1,
            search_var2=self.search_var2,
            search_combo1=self.search_combo1,
            search_combo2=self.search_combo2,
            history_file=SEARCH_HISTORY_FILE,
            sync_history_callback = self.sync_history_from_QM,
            test_callback=self.on_test_code
        )
            # search_combo3=self.search_combo3,

        # self.search_history1, self.search_history2 = self.load_search_history()
        self.search_history1, self.search_history2,self.search_history3 = self.query_manager.load_search_history()

        # 从 query_manager 获取历史
        h1, h2, h3 = self.query_manager.history1, self.query_manager.history2, self.query_manager.history3

        # 提取 query 字段用于下拉框
        self.search_history1 = [r["query"] for r in h1]
        self.search_history2 = [r["query"] for r in h2]   
        self.search_history3 = [r["query"] for r in h3]

        # 其他功能按钮
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        tk.Button(bottom_search_frame, text="搜索", command=lambda: self.apply_search()).pack(side="left", padx=3)
        tk.Button(bottom_search_frame, text="清空", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="删除", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="管理", command=lambda: self.open_column_manager()).pack(side="left", padx=2)


        # 功能选择下拉框（固定宽度）
        options = ["窗口重排","Query编辑","停止刷新", "启动刷新" , "保存数据", "读取存档", "报警中心","覆写TDX", "手札总览", "语音预警"]
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            bottom_search_frame, textvariable=self.action_var,
            values=options, state="readonly", width=10
        )
        self.action_combo.set("功能选择")
        self.action_combo.pack(side="left", padx=10, pady=1, ipady=1)

        def run_action(action):

            if action == "窗口重排":
                rearrange_monitors_per_screen(align="left", sort_by="id", layout="horizontal",monitor_list=self._pg_top10_window_simple, win_var=self.win_var)
            elif action == "Query编辑":
                self.query_manager.open_editor()  # 打开 QueryHistoryManager 编辑窗口
            elif action == "停止刷新":
                self.stop_refresh()
            elif action == "启动刷新":
                self.start_refresh()
            elif action == "保存数据":
                self.save_data_to_csv()
            elif action == "读取存档":
                self.load_data_from_csv()
            elif action == "报警中心":
                open_alert_center(self)
            elif action == "覆写TDX":
                self.write_to_blk(append=False)
            elif action == "手札总览":
                self.open_handbook_overview()
            elif action == "语音预警":
                self.open_voice_monitor_manager()


        def on_select(event=None):
            run_action(self.action_combo.get())
            self.action_combo.set("功能选择")

        self.action_combo.bind("<<ComboboxSelected>>", on_select)



        # 其他功能按钮
        # tk.Button(bottom_search_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(bottom_search_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        # tk.Button(ctrl_frame, text="测试", command=lambda: self.on_test_code()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="清空", command=lambda: self.clean_search(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除", command=lambda: self.delete_search_history(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="监控", command=lambda: self.KLineMonitor_init()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="写入", command=lambda: self.write_to_blk()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="存档", command=lambda: self.open_archive_loader(), font=('Microsoft YaHei', 9), padx=2, pady=2).pack(side="left", padx=2)

        # # 搜索区（可拉伸）
        # search_frame = tk.Frame(ctrl_frame)
        # search_frame.pack(side="left", fill="x", expand=True, padx=5)

        # # self.search_history = self.load_search_history()
        # self.search_history1, self.search_history2 = self.load_search_history()

        # # 第一个搜索框 + 独立历史
        # self.search_var1 = tk.StringVar()
        # self.search_combo1 = ttk.Combobox(search_frame, textvariable=self.search_var1, values=self.search_history1)
        # self.search_combo1.pack(side="left", fill="x", expand=True, padx=(0, 5))
        # self.search_combo1.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo1.bind("<<ComboboxSelected>>", lambda e: self.apply_search())

        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除", command=self.delete_search_history).pack(side="left", padx=2)

        # # 第二个搜索框 + 独立历史
        # self.search_var2 = tk.StringVar()
        # self.search_combo2 = ttk.Combobox(search_frame, textvariable=self.search_var2, values=self.search_history2)
        # self.search_combo2.pack(side="left", fill="x", expand=True, padx=(5, 0))
        # self.search_combo2.bind("<Return>", lambda e: self.apply_search())
        # self.search_combo2.bind("<<ComboboxSelected>>", lambda e: self.apply_search())



        # self.search_combo1['values'] = self.search_history1
        # self.search_combo2['values'] = self.search_history2

        # # --------------------
        # # 其他按钮区（固定宽度，不拉伸）
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除", command=self.delete_search_history).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=5)

        if len(self.search_history1) > 0:
            self.search_var1.set(self.search_history1[0])
        if len(self.search_history2) > 0:
            self.search_var2.set(self.search_history2[0])

        self.open_column_manager_init()
        # # 程序启动时恢复
        # self.restore_all_monitor_windows()

        # self.focus_force()
        # self.lift()
        # self.search_btn1.config(
        #     command=lambda: self.apply_search(self.search_var1, self.search_history1, self.search_combo1, "search1")
        # )
        # self.search_btn2.config(
        #     command=lambda: self.apply_search(self.search_var2, self.search_history2, self.search_combo2, "search2")
        # )

        # ctrl_frame = tk.Frame(self)
        # ctrl_frame.pack(side="top", fill="x", pady=5)

        # # 功能选择
        # combo.pack(side="left", padx=10, pady=2, ipady=1)

        # # 第二搜索框
        # self.search_combo2.pack(side="left", padx=5)

        # # 原搜索框
        # self.search_combo.pack(side="left", padx=5)


        #2
        # options = ["保存数据", "读取存档", "停止刷新", "启动刷新", "报警中心"]

        # self.action_var = tk.StringVar()
        # combo = ttk.Combobox(ctrl_frame, textvariable=self.action_var, values=options, state="readonly")
        # combo.set("选择操作")  # 默认提示
        # combo.pack(side="left", padx=5)

        # def on_select(event=None):
        #     run_action(combo.get())

        # combo.bind("<<ComboboxSelected>>", on_select)

        # # --- 数据存档按钮 ---
        # tk.Button(ctrl_frame, text="保存数据", command=self.save_data_to_csv).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="读取存档", command=self.load_data_from_csv).pack(side="left", padx=2)

        # # --- 刷新控制按钮 ---
        # tk.Button(ctrl_frame, text="停止刷新", command=self.stop_refresh).pack(side="left", padx=5)
        # tk.Button(ctrl_frame, text="启动刷新", command=self.start_refresh).pack(side="left", padx=2)

        #         # 在初始化时（StockMonitorApp.__init__）创建并注册：
        # self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
        # set_global_manager(self.alert_manager)
        # # 在 UI 控件区加个按钮：
        # tk.Button(ctrl_frame, text="报警中心", command=lambda: open_alert_center(self)).pack(side="left", padx=2)

    # def replace_st_key_sort_col_gpt_bug(self, old_col, new_col):
    #     """安全替换 Treeview 中的一列（含完整检查）"""
    #     try:
    #         logger.info(f"diff : ({old_col}, {new_col})")
    #         logger.info(f"old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}")

    #         # 🧩 Step 1. 数据检查
    #         if self.df_all is None or self.df_all.empty:
    #             logger.info("⚠️ df_all 为空，无法替换列。")
    #             return
    #         if new_col not in self.df_all.columns:
    #             logger.info(f"⚠️ 新列 {new_col} 不存在于 df_all.columns，跳过。")
    #             return

    #         # 🧩 Step 2. 获取 Tree 当前列
    #         current_tree_cols = list(self.tree["columns"])

    #         # old_col 不在当前 tree，直接跳过
    #         if old_col not in current_tree_cols:
    #             logger.info(f"⚠️ {old_col} 不在 TreeView columns：{current_tree_cols}")
    #             # 保险策略：如果 new_col 不在，也追加进去
    #             if new_col not in current_tree_cols:
    #                 current_tree_cols.append(new_col)
    #             # 同步到 current_cols
    #             self.current_cols = current_tree_cols
    #             self.update_treeview_cols(self.current_cols)
    #             return

    #         # 🧩 Step 3. 清空 Tree 结构（避免无效列引用）
    #         self.tree["displaycolumns"] = ()
    #         self.tree["columns"] = ()
    #         self.tree.update_idletasks()

    #         # 🧩 Step 4. 替换 self.current_cols
    #         if old_col in self.current_cols:
    #             self.current_cols = [
    #                 new_col if c == old_col else c for c in self.current_cols
    #             ]
    #         else:
    #             logger.info(f"⚠️ {old_col} 不在 current_cols，追加新列 {new_col}")
    #             if new_col not in self.current_cols:
    #                 self.current_cols.append(new_col)

    #         # 🧩 Step 5. 过滤无效列（仅保留 df_all 中存在的）
    #         self.current_cols = [c for c in self.current_cols if c in self.df_all.columns]

    #         # 🧩 Step 6. 调用安全更新函数
    #         self.update_treeview_cols(self.current_cols)

    #         logger.info(f"✅ 替换完成：{old_col} → {new_col}")
    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
    #         logger.info(f"❌ 替换列时出错：{e}")


    def replace_st_key_sort_col(self, old_col, new_col):
        """替换显示列并刷新表格"""
        if old_col in self.current_cols and new_col not in self.current_cols:
            logger.info(f'old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}')
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 去掉重复列
            new_columns = []
            for col in ["code"] + self.current_cols:
                if col not in new_columns:
                    new_columns.append(col)

            # #判断是否有这个col
            # new_columns = [c for c in new_columns if c in self.df_all.columns]

            # # 确保 Treeview 先注册所有列
            # for col in new_columns:
            #     if col not in self.tree["columns"]:
            #         self.tree["columns"] = list(self.tree["columns"]) + [col]

            # 只保留 DataFrame 中存在的列，避免 TclError
            new_columns = [c for c in new_columns if c in self.df_all.columns or c == "code"]

            self.update_treeview_cols(new_columns)
            # # 注册所有新列
            # existing_cols = list(self.tree["columns"])
            # for col in new_columns:
            #     if col not in existing_cols:
            #         existing_cols.append(col)
            # self.tree["columns"] = existing_cols

            # # # 重新设置 tree 的列集合
            # # if "code" not in self.current_cols:
            # #     new_columns = ["code"] + self.current_cols
            # # else:
            # #     new_columns = self.current_cols

            # self.tree.config(columns=new_columns)
            # self.tree["displaycolumns"] = new_columns
            # self.tree.configure(show="headings")

            # # 重新设置表头
            # for col in new_columns:
            #     # self.tree.heading(col, text=col, anchor="center")
            #     if col in self.tree['columns']:
            #         self.tree.heading(col, text=col, anchor="center", command=lambda _col=col: self.sort_by_column(_col, False))
            #                       # command=lambda c=col: self.show_column_menu(c))
            #     else:
            #         # 如果 Treeview 没有这个列，可以选择添加或者跳过
            #         logger.info(f"⚠️ Treeview 没有列 {col}，跳过")
            # # 重新加载数据
            # self.refresh_tree(self.df_all)


    def on_st_key_sort_enter(self, event):
        sort_val = self.st_key_sort_value.get()
        # try:
        #     nums = list(map(int, sort_val.strip().split()))
        #     if len(nums) != 2:
        #         raise ValueError
        # except:
        #     logger.info("输入格式错误，例如：'3 0'")
        #     return
        def diff_and_replace_all(old_cols, new_cols):
            """找出两个列表不同的元素，返回替换规则 (old, new)"""
            replace_rules = []
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    replace_rules.append((old, new))
            return replace_rules
            #
            # diffs = diff_and_replace(DISPLAY_COLS, DISPLAY_COLS_2)
            # for old_col, new_col in diffs:
            #     self.replace_st_key_sort_col(old_col, new_col)


        # def first_diff_and_replace(old_cols, new_cols, current_cols):
        #     """
        #     查找 old_cols 与 new_cols 的第一个不同项，并在 current_cols 中替换。
        #     若当前列中不存在 old，则继续找下一个不同项。
        #     返回 (old, new) 若替换成功，否则返回 None。
        #     """
        #     for old, new in zip(old_cols, new_cols):
        #         if old != new:
        #             if old in current_cols:
        #                 idx = current_cols.index(old)
        #                 current_cols[idx] = new
        #                 logger.info(f"✅ 替换: {old} -> {new}")
        #                 return old, new
        #             else:
        #                 logger.info(f"⚠️ {old} 不在 current_cols 中，继续查找下一组差异...")
        #     logger.info("⚠️ 没有可替换的差异列。")
        #     return None

        # def first_diff(old_cols, new_cols):
        #     for old, new in zip(old_cols, new_cols):
        #         if old != new:
        #             return old, new
        #     return None

        def first_diff(old_cols, new_cols, current_cols):
            """
            找出 old_cols 与 new_cols 的第一个不同项，
            且 old 在 current_cols 中存在。
            返回 (old, new)，若无则返回 None。
            """
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    if old in current_cols:
                        logger.info(f"✅ 可替换列对: ({old}, {new})")
                        return old, new
                    else:
                        logger.info(f"⚠️ {old} 不在 current_cols 中，跳过...")
            logger.info("⚠️ 未找到可替换的差异列。")
            return None


        def update_display_cols_if_diff(display_cols, display_cols_2, current_cols):
            """
            检测并自动更新 display_cols，如果发现有匹配差异则替换。
            返回 (新的 display_cols, diff)
            """
            diff = first_diff(display_cols, display_cols_2, current_cols)
            if diff:
                old, new = diff
                # 替换第一个匹配的 old 为 new
                updated_cols = [new if c == old else c for c in display_cols]
                logger.info(f"🟢 已更新 DISPLAY_COLS: 替换 {old} → {new}")
                return updated_cols, diff
            else:
                logger.info("🔸 无可更新的列。")
                return display_cols, None



        global DISPLAY_COLS 

        if sort_val:
            sort_val = sort_val.strip()
            self.global_values.setkey("st_key_sort", sort_val)
            self.status_var.set(f"设置 st_key_sort : {sort_val}")
            self.st_key_sort = sort_val
            self.sortby_col = None
            self.sortby_col_ascend = None
            self.select_code = None

            if self.df_all is not None and not self.df_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(sort_val,self.df_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(sort_val)

            DISPLAY_COLS_2 = ct.get_Duration_format_Values(
                ct.Monitor_format_trade,sort_cols[:2])
            # logger.info(f'DISPLAY_COLS : {DISPLAY_COLS}')
            # logger.info(f'self.current_cols[1:] : {self.current_cols[1:]}')
            # logger.info(f'DISPLAY_COLS_2 : {DISPLAY_COLS_2}')
            # diff = first_diff(self.current_cols[1:], DISPLAY_COLS_2)
            # diff = first_diff(DISPLAY_COLS, DISPLAY_COLS_2,self.current_cols[1:])
            # 第一次调用
            DISPLAY_COLS, diff = update_display_cols_if_diff(DISPLAY_COLS, DISPLAY_COLS_2, self.current_cols[1:])
            # logger.info(f'diff : {diff}')
            if diff:
                logger.info(f'diff : {diff}')
                # bug index 
                # self.replace_st_key_sort_col(*diff)
                self.replace_column(*diff,apply_search=False)
            # DISPLAY_COLS = DISPLAY_COLS_2
            # self.current_cols = ["code"] + DISPLAY_COLS_2

    def refresh_data(self):
        """
        手动刷新：更新 resample 全局配置，触发后台进程下一轮 fetch_and_process
        """
        resample = self.resample_combo.get().strip()
        logger.info(f'set resample : {resample}')
        # cct.GlobalValues().setkey("resample", resample)
        self.global_values.setkey("resample", resample)
        self.blkname = ct.Resample_LABELS_Blk[resample] or "060.blk"
        self.global_values.setkey("blkname", self.blkname)
        
        self.refresh_flag.value = False
        time.sleep(0.6)
        self.refresh_flag.value = True
        self.status_var.set(f"手动刷新: resample={resample}")

    def _start_process(self):
        self.refresh_flag = mp.Value('b', True)
        self.log_level = mp.Value('i', log_level)  # 'i' 表示整数
        self.detect_calc_support = mp.Value('b', detect_calc_support)  # 'i' 表示整数
        # self.proc = mp.Process(target=fetch_and_process, args=(self.queue,))
        self.proc = mp.Process(target=fetch_and_process, args=(self.global_dict,self.queue, "boll", self.refresh_flag,self.log_level, self.detect_calc_support))
        # self.proc.daemon = True
        self.proc.daemon = False 
        self.proc.start()

    # def update_tree(self):
    #     try:
    #         while not self.queue.empty():
    #             df = self.queue.get_nowait()
    #             self.refresh_tree(df)
    #             self.status_var.set(f"刷新完成: 共 {len(df)} 行数据")
    #     except Exception as e:
    #         LoggerFactory.log.error(f"Error updating tree: {e}", exc_info=True)
    #     finally:
    #         self.after(1000, self.update_tree)

    # def refresh_tree(self, df):
    #     # 清理旧数据
    #     for col in self.tree["columns"]:
    #         self.tree.heading(col, text="")
    #     self.tree.delete(*self.tree.get_children())

    #     if df.empty:
    #         return

    #     # 重新加载表头
    #     self.tree["columns"] = list(df.columns)
    #     for col in df.columns:
    #         self.tree.heading(col, text=col)

    #     # 插入数据
    #     for idx, row in df.iterrows():
    #         self.tree.insert("", "end", values=list(row))

    # def apply_search(self):
        # query = self.search_var.get().strip()
        # if not query:
        #     self.status_var.set("搜索框为空")
        #     return
        # self.status_var.set(f"搜索: {query}")

    # # ----------------- 启停刷新 ----------------- #
    # def stop_refresh(self):
    #     self.refresh_enabled = False
    #     self.status_var.set("刷新已停止")

    # def start_refresh(self):
    #     self.refresh_enabled = True
    #     self.status_var.set("刷新已启动")
    def stop_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False
            logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("刷新已停止")

    def start_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = True
            logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("刷新已启动")

    def format_next_time(self,delay_ms=None):
        """把 root.after 的延迟时间转换成 %H:%M 格式"""
        if delay_ms == None:
            target_time = datetime.now()
        else:
            delay_sec = delay_ms / 1000
            target_time = datetime.now() + timedelta(seconds=delay_sec)
        return target_time.strftime("%H:%M")
    # ----------------- 数据刷新 ----------------- #
    def update_tree(self):
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return  # 已销毁，直接返回
        try:
            if self.refresh_enabled:  # ✅ 只在启用时刷新
                has_update = False
                while not self.queue.empty():
                    df = self.queue.get_nowait()
                    # logger.info(f'df:{df[:1]}')
                    if self.sortby_col is not None:
                        logger.info(f'update_tree sortby_col : {self.sortby_col} sortby_col_ascend : {self.sortby_col_ascend}')
                        df = df.sort_values(by=self.sortby_col, ascending=self.sortby_col_ascend)
                    if df is not None and not df.empty and len(df) > 30:
                        time_s = time.time()
                        df = detect_signals(df)
                        self.df_all = df.copy()
                        has_update = True
                        logger.info(f'detect_signals duration time:{time.time()-time_s:.2f}')
                    # logger.info(f"self.queue [Debug] df_all_hash={df_hash(self.df_all)} len={len(self.df_all)} time={datetime.now():%H:%M:%S}")
                        
                        # ✅ 仅在第一次获取 df_all 后恢复监控窗口
                        if not hasattr(self, "_restore_done"):
                            self._restore_done = True
                            logger.info("首次数据加载完成，开始恢复监控窗口...")
                            self.after(1000,self.restore_all_monitor_windows)
                            logger.info("首次数据加载完成，开始监控...")
                            self.after(30*1000,self.KLineMonitor_init)
                            self.after(60*1000, self.schedule_15_30_job)

                        if self.search_var1.get() or self.search_var2.get():
                            self.apply_search()
                        else:
                            self.refresh_tree(self.df_all)
                            
                # --- 注入: 实时策略检查 (移出循环，只在有更新时执行一次) ---
                if has_update and hasattr(self, 'live_strategy'):
                        self.live_strategy.process_data(self.df_all)
                # -------------------------

                self.status_var2.set(f'queue update: {self.format_next_time()}')
        except Exception as e:
            logger.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

    def push_stock_info(self,stock_code, row):
        """
        从 self.df_all 的一行数据提取 stock_info 并推送
        """
        try:
            stock_info = {
                "code": str(stock_code),
                "name": str(row["name"]),
                "high": str(row["high"]),
                "lastp1d": str(row["lastp1d"]),
                "percent": float(row.get("percent", 0)),
                "price": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0))
            }
            # code, _ , percent,price, vol
            # 转为 JSON 字符串
            payload = json.dumps(stock_info, ensure_ascii=False)

            # ---- 根据传输方式选择 ----
            # 如果用 WM_COPYDATA，需要 encode 成 bytes 再传
            # if hasattr(self, "send_wm_copydata"):
            #     self.send_wm_copydata(payload.encode("utf-8"))

            # 如果用 Pipe / Queue，可以直接传 str
            # elif hasattr(self, "pipe"):
            #     self.pipe.send(payload)


            # 推送给异动联动（用管道/消息）
            send_code_via_pipe(payload)   # 假设你用 multiprocessing.Pipe
            # 或者 self.queue.put(stock_info)  # 如果是队列
            # 或者 send_code_to_other_window(stock_info) # 如果是 WM_COPYDATA
            logger.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            logger.error(f"推送 stock_info 出错: {e} {row}")
            return False


    def open_alert_rule_new(self):
        """新建报警规则"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            auto_close_message("提示", "请先选择一个股票！")
            return
        
        # new_rule=True 表示创建新规则
        self.open_alert_editor(stock_info=stock_info, new_rule=True)

    def open_alert_rule_edit(self):
        """编辑报警规则"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            messagebox.showwarning("提示", "请先选择一只股票")
            return
        self.open_alert_editor(self, stock_info=stock_info, new_rule=False)

    def on_tree_select(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            self.selected_stock_info = None
            return
        item_id = selected_item[0]
        item = self.tree.item(selected_item[0])
        values = item.get("values")
        # 假设你的 tree 列是 (code, name, price, …)
        stock_info = {
            "code": values[0],
            "name": values[1] if len(values) > 1 else "",
            "extra": values  # 保留整行
        }
        self.selected_stock_info = stock_info

        if selected_item:
            stock_info = self.tree.item(selected_item, 'values')
            stock_code = stock_info[0]

            send_tdx_Key = (self.select_code != stock_code)
            self.select_code = stock_code

            stock_code = str(stock_code).zfill(6)
            logger.info(f'stock_code:{stock_code}')
            # logger.info(f"选中股票代码: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)

            # =========================
            # ✅ 构造 fake mouse event
            # =========================
            from types import SimpleNamespace
            try:
                # ==========================
                # ✅ 构造模拟 event
                # ==========================

                x_root = getattr(self, "event_x_root", None)
                y_root = getattr(self, "event_y_root", None)

                # 没有鼠标坐标就退回到行中心
                if x_root is None or y_root is None:
                    bbox = self.tree.bbox(item_id)
                    if not bbox:
                        return
                    x, y, w, h = bbox

                    x_root = self.tree.winfo_rootx() + x + w + 10
                    y_root = self.tree.winfo_rooty() + y + h // 2

                fake_event = SimpleNamespace(
                    x=0,
                    y=0,
                    x_root=x_root,
                    y_root=y_root
                )

                # ✅ 复用 Tooltip 入口
                self.on_tree_click_for_tooltip(fake_event,stock_code)

            except Exception as e:
                logger.warning(f"Tooltip select trigger failed: {e}")

    def update_send_status(self, status_dict):
        # 更新状态栏
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        # self.status_var.set(status_text)
        # logger.info(status_text)

    def scale_size(self,base_size):
        """根据 DPI 缩放返回尺寸"""
        scale = get_windows_dpi_scale_factor()
        return int(base_size * scale)
    

    def init_checkbuttons(self, parent_frame):
        # 保持 Tk.Frame 不变，因为它是容器
        frame_right = tk.Frame(parent_frame, bg="#f0f0f0") 
        frame_right.pack(side=tk.RIGHT, padx=2, pady=1)

        self.win_var = tk.BooleanVar(value=False)
        # ✅ 绑定win_var变化回调，实时切换特征颜色显示
        self.win_var.trace_add('write', lambda *args: self.toggle_feature_colors())
        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=True)
        self.dfcf_var = tk.BooleanVar(value=False)
        checkbuttons_info = [
            ("Win", self.win_var),
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var)
        ]
        
        # 💥 修正：使用 ttk.Checkbutton 替代 tk.Checkbutton
        for text, var in checkbuttons_info:
            cb = ttk.Checkbutton(
                frame_right, 
                text=text, 
                variable=var, 
                command=self.update_linkage_status,
                # 💥 注意：ttk 组件不再使用 bg, font 等直接参数
                # bg="#f0f0f0", 
                # font=('Microsoft YaHei', 9), # 字体应该通过 Style 统一设置
                # padx=0, pady=0, bd=0, highlightthickness=0
            )
            cb.pack(side=tk.LEFT, padx=1)

    def update_linkage_status(self):
        # 此处处理 checkbuttons 状态
        if not self.tdx_var.get() or self.ths_var.get():
            self.sender.reload()
        if  self.dfcf_var.get() != self.auto_adjust_column:
            logger.info(f"DC:{self.dfcf_var.get()} self.auto_adjust_column :{self.auto_adjust_column}")
            self.auto_adjust_column = self.dfcf_var.get()
            # self.apply_search()
            # self.after(50, self.adjust_column_widths)
            self._setup_tree_columns(self.tree,self.current_cols, sort_callback=self.sort_by_column, other={})
            self.reload_cfg_value()
            # self.update_treeview_cols(self.current_cols)

        logger.info(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()}")

    # def refresh_tree(self, df):
    #     for i in self.tree.get_children():
    #         self.tree.delete(i)
    #     logger.debug(f'refresh_tree df:{df[:2]}')
    #     if not df.empty:
    #         df = df.copy()
    #         # 检查 DISPLAY_COLS 中 code 是否已经存在
    #         if 'code' not in df.columns:
    #             df.insert(0, "code", df.index)
    #         # 如果 df 已经有 code，确保列顺序和 DISPLAY_COLS 一致
    #         cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
    #         df = df.reindex(columns=cols_to_show)
    #         # 插入到 TreeView
    #         for _, row in df.iterrows():
    #             self.tree.insert("", "end", values=list(row))
    #     self.current_df = df
    #     self.adjust_column_widths()
    #     self.update_status()

    # def load_data(self, df):
    #     """加载新的数据到 TreeView"""
    #     self.df_all = df.copy()
    #     self.current_df = df.copy()
    #     self.refresh_tree()

    # def refresh_tree(self):
    #     """刷新 TreeView 显示"""
    #     if self.df_display.empty:
    #         self.tree.delete(*self.tree.get_children())
    #         return

    #     self.tree.delete(*self.tree.get_children())
    #     for idx, row in self.df_display.iterrows():
    #         vals = [row[col] for col in self.df_display.columns]
    #         self.tree.insert("", "end", values=vals)

    # def filter_and_refresh_tree(self, query_dict):
    #     """
    #     query_dict = {
    #         '关键列1': '值或%like%',
    #         '关键列2': '值或%like%',
    #     }
    #     """
    #     if self.df_all.empty:
    #         return
    #     df_filtered = self.df_all.copy()
    #     for col, val in query_dict.items():
    #         if col not in df_filtered.columns:
    #             continue

    #         # 支持模糊 like 查询
    #         if isinstance(val, str) and "%" in val:
    #             pattern = val.replace("%", ".*")
    #             df_filtered = df_filtered[df_filtered[col].astype(str).str.match(pattern)]
    #         else:
    #             df_filtered = df_filtered[df_filtered[col] == val]
    #     # 根据过滤结果保留原始未查询列
    #     self.current_df = self.df_all.loc[df_filtered.index].copy()
    #     self.refresh_tree()


    def update_query_combo(self):
        pass
        # values = [f"{i+1}: {q.get('desc','')} " for i,q in enumerate(self.query_history)]
        # self.query_combo['values'] = values


    # def save_query_history(self, query_dict, desc=None):
    #     if query_dict not in self.query_history:
    #         self.query_history.append({'query': query_dict, 'desc': desc})

    # def on_query_select(self, event=None):
    #     sel = self.query_combo.current()
    #     if sel < 0:
    #         return
    #     query_dict = self.query_history[sel]['query']
        
    #     # 刷新 TreeView 数据
    #     self.refresh_tree_with_query(query_dict)
        
    #     # 更新查询说明
    #     self.query_desc_label.config(text=self.query_history[sel].get('desc', ''))

    # # 执行查询
    # def on_query(self):
    #     # query_text = self.query_var.get().strip()
    #     query_text = self.query_combo_var.get().strip()
    #     if not query_text:
    #         return
    #     # 构造 query_dict，例如：{'name':'ABC','percent':">1"}
    #     query_dict = self.parse_query_text(query_text)
    #     logger.info(f'query_dict:{query_dict}')
    #     # 保存到历史
    #     desc = query_text  # 简单说明为输入文本
    #     # self.query_history.append({'query': query_dict, 'desc': desc})
    #     self.query_history.append({'query': query_dict})

    #     # 更新下拉框
    #     # self.query_combo['values'] = [q['desc'] for q in self.query_history]
    #     # self.query_combo.current(len(self.query_history)-1)

    #     # 执行刷新
    #     self.refresh_tree_with_query(query_dict)
    #     # self.query_desc_label.config(text=desc)

    # 选择历史查询
    def on_query_select(self, event=None):

        sel = self.query_combo.current()
        # query_text = self.query_combo_var.get()
        # if query_text:
        #     query_dict = query_text
        #     self.on_query(query_dict)
        # else:
        if sel < 0:
            return
        else:
            query_dict = self.query_history[sel]['query']
            # desc = self.query_history[sel].get('desc', '')
            # 更新查询说明
            # self.query_desc_label.config(text=desc)
            self.refresh_tree_with_query(query_dict)

    # TreeView 刷新函数
    # def refresh_tree_with_query(self, query_dict):
    #     if not hasattr(self, 'temp_df'):
    #         return
    #     df = self.temp_df.copy()

    #     # 根据 query_dict 自动过滤
    #     for col, cond in query_dict.items():
    #         if col in df.columns:
    #             if isinstance(cond, str) and cond.startswith(('>', '<', '>=', '<=', '==')):
    #                 df = df.query(f"{col}{cond}")
    #             else:
    #                 df = df[df[col]==cond]

    #     # 只显示 DISPLAY_COLS 列
    #     display_df = df[DISPLAY_COLS]
    #     # 刷新 TreeView
    #     self.tree.delete(*self.tree.get_children())
    #     for idx, row in display_df.iterrows():
    #         self.tree.insert("", "end", values=[row[col] for col in DISPLAY_COLS])

    # 将查询文本解析为 dict（可根据你需求改）
    def parse_query_text(self, text):
        # 简单示例：name=ABC;percent>1
        # result = {}
        # for part in text.split(';'):
        #     if '=' in part:
        #         k,v = part.split('=',1)
        #         result[k.strip()] = v.strip()
        #     elif '>' in part:
        #         k,v = part.split('>',1)
        #         result[k.strip()] = f">{v.strip()}"
        #     elif '<' in part:
        #         k,v = part.split('<',1)
        #         result[k.strip()] = f"<{v.strip()}"
        query_dict = {}
        for cond in text.split(";"):
            cond = cond.strip()
            if not cond:
                continue
            # name%中信 -> key=name, val=%中信
            if "%":
                for op in [">=", "<=", "~", "%"]:
                    if op in cond:
                        key, val = cond.split(op, 1)
                        query_dict[key.strip()] = op + val.strip() if op in [">=", "<="] else val.strip()
                        break
        return query_dict
    #old query_var
    # def on_query(self):
    #     query_text = self.query_var.get()
    #     if not query_text.strip():
    #         self.refresh_tree_with_query(None)
    #         return
    #     query_dict = {}
    #     for cond in query_text.split(";"):
    #         cond = cond.strip()
    #         if not cond:
    #             continue
    #         # name%中信 -> key=name, val=%中信
    #         if "%":
    #             for op in [">=", "<=", "~", "%"]:
    #                 if op in cond:
    #                     key, val = cond.split(op, 1)
    #                     query_dict[key.strip()] = op + val.strip() if op in [">=", "<="] else val.strip()
    #                     break
        
    #     self.save_query_history()
    #     self.refresh_tree_with_query(query_dict)

    def on_query(self):
        query_text = self.query_var.get().strip()
        if not query_text:
            return

        # 构造 query_dict
        query_dict = self.parse_query_text(query_text)

        # 保存到历史
        desc = query_text
        self.query_history.append({'query': query_dict, 'desc': desc})

        # 更新下拉框
        self.query_combo['values'] = [q['desc'] for q in self.query_history]
        if self.query_history:
            self.query_combo.current(len(self.query_history) - 1)

        # 执行刷新
        self.refresh_tree_with_query(query_dict)
        self.query_desc_label.config(text=desc)


    def refresh_tree_with_query(self, query_dict):
        if not hasattr(self, 'temp_df'):
            return
        df = self.temp_df.copy()

        # 支持范围查询和等值查询
        for col, cond in query_dict.items():
            if col not in df.columns:
                continue
            if isinstance(cond, str):
                cond = cond.strip()
                if '~' in cond:  # 区间查询 5~15
                    try:
                        low, high = map(float, cond.split('~'))
                        df = df[(df[col] >= low) & (df[col] <= high)]
                    except:
                        pass
                elif cond.startswith(('>', '<', '>=', '<=', '==')):
                    df = df.query(f"{col}{cond}")
                else:  # 模糊匹配 like
                    df = df[df[col].astype(str).str.contains(cond)]
            else:
                df = df[df[col]==cond]

        # 保留 DISPLAY_COLS
        display_df = df[DISPLAY_COLS]
        self.tree.delete(*self.tree.get_children())
        for idx, row in display_df.iterrows():
            self.tree.insert("", "end", values=[row[col] for col in DISPLAY_COLS])

    def refresh_tree_with_query2(self, query_dict=None):
        """
        刷新 TreeView 并支持高级查询
        query_dict: dict, key=列名, value=查询条件
        """
        if self.df_all.empty:
            return

        # 1. 原始数据保留
        df_raw = self.df_all.copy()

        # 2. 处理查询
        if query_dict:
            df_filtered = df_raw.copy()
            for col, val in query_dict.items():
                if col not in df_filtered.columns:
                    continue
                s = df_filtered[col]
                if isinstance(val, str):
                    val = val.strip()
                    if val.startswith(">="):
                        try:
                            df_filtered = df_filtered[s.astype(float) >= float(val[2:])]
                            continue
                        except: pass
                    elif val.startswith("<="):
                        try:
                            df_filtered = df_filtered[s.astype(float) <= float(val[2:])]
                            continue
                        except: pass
                    elif "~" in val:
                        try:
                            low, high = map(float, val.split("~"))
                            df_filtered = df_filtered[s.astype(float).between(low, high)]
                            continue
                        except: pass
                    elif "%" in val:
                        pattern = val.replace("%", ".*")
                        df_filtered = df_filtered[s.astype(str).str.contains(pattern, regex=True)]
                        continue
                    else:
                        df_filtered = df_filtered[s == val]
                else:
                    df_filtered = df_filtered[s == val]
        else:
            df_filtered = df_raw.copy()

        # 3. 构造显示 DataFrame
        # 仅保留 DISPLAY_COLS，如果 DISPLAY_COLS 中列不在 df_all 中，填充空值
        df_display = pd.DataFrame(index=df_filtered.index)
        for col in DISPLAY_COLS:
            if col in df_filtered.columns:
                df_display[col] = df_filtered[col]
            else:
                df_display[col] = ""

        self.current_df = df_display
        self.refresh_tree()


    def filter_and_refresh_tree(self, query_dict):
        """
        高级过滤 TreeView 显示

        query_dict = {
            'name': '%中%',        # 模糊匹配
            '涨幅': '>=2',         # 数值匹配
            '量': '10~100'         # 范围匹配
        }
        """
        if self.df_all.empty:
            return

        df_filtered = self.df_all.copy()

        for col, val in query_dict.items():
            if col not in df_filtered.columns:
                continue

            s = df_filtered[col]

            # 数值范围或比较符号
            if isinstance(val, str):
                val = val.strip()
                if val.startswith(">="):
                    try:
                        threshold = float(val[2:])
                        df_filtered = df_filtered[s.astype(float) >= threshold]
                        continue
                    except:
                        pass
                elif val.startswith("<="):
                    try:
                        threshold = float(val[2:])
                        df_filtered = df_filtered[s.astype(float) <= threshold]
                        continue
                    except:
                        pass
                elif "~" in val:
                    try:
                        low, high = map(float, val.split("~"))
                        df_filtered = df_filtered[s.astype(float).between(low, high)]
                        continue
                    except:
                        pass
                elif "%" in val:
                    pattern = val.replace("%", ".*")
                    df_filtered = df_filtered[s.astype(str).str.contains(pattern, regex=True)]
                    continue
                else:
                    # 精确匹配
                    df_filtered = df_filtered[s == val]
            else:
                # 数值精确匹配
                df_filtered = df_filtered[s == val]

        # 保留原始未查询列数据，总列数不变
        self.current_df = self.df_all.loc[df_filtered.index].copy()
        self.refresh_tree()

    # def refresh_tree1(self, df=None):
    #     if df is None:
    #         df = self.current_df.copy()

    #     for i in self.tree.get_children():
    #         self.tree.delete(i)

    #     if df.empty:
    #         self.current_df = df
    #         self.update_status()
    #         return

    #     df = df.copy()
    #     # 确保 code 列存在
    #     if 'code' not in df.columns:
    #         df.insert(0, "code", df.index)
    #     cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
    #     df = df.reindex(columns=cols_to_show)

    #     # 自动搜索过滤 初始版本的query
    #     # query = self.search_var.get().strip()
    #     # if query:
    #     #     try:
    #     #         df = df.query(query)
    #     #     except Exception as e:
    #     #         logger.error(f"自动搜索过滤错误: {e}")

    #     # 插入到 TreeView
    #     for _, row in df.iterrows():
    #         self.tree.insert("", "end", values=list(row))

    #     self.current_df = df
    #     self.adjust_column_widths()
    #     self.update_status()


    def open_column_selector(self, col_index):
        """弹出横排窗口选择新的列名"""
        if self.current_df is None or self.current_df.empty:
            return

        # 创建弹出窗口
        win = tk.Toplevel(self)
        win.title("选择列")
        win.geometry("800x400")  # 可调大小
        win.transient(self)

        # 滚动条 + 画布 + frame，避免列太多放不下
        canvas = tk.Canvas(win)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 当前所有列
        all_cols = list(self.current_df.columns)

        def on_select(col_name):
            # 替换 Treeview 的列
            if 0 <= col_index < len(DISPLAY_COLS):
                DISPLAY_COLS[col_index] = col_name
                self.refresh_tree(self.current_df)
            win.destroy()

        # 生成按钮（横排，自动换行）
        for i, col in enumerate(all_cols):
            btn = tk.Button(scroll_frame, text=col, width=15,
                            command=lambda c=col: on_select(c))
            btn.grid(row=i // 5, column=i % 5, padx=5, pady=5, sticky="w")

        win.grab_set()  # 模态

    def get_centered_window_position_center(win_width, win_height, x_root=None, y_root=None, parent_win=None):
        """
       在多屏环境下，为新窗口选择合适位置，避免遮挡父窗口(root)。
       优先顺序：右侧 -> 下方 -> 左侧 -> 上方 -> 居中
       """
       # 默认取主屏幕
        screen = get_monitor_by_point(0, 0)
        x = (screen['width'] - win_width) // 2
        y = (screen['height'] - win_height) // 2

        if parent_win:
           parent_win.update_idletasks()
           px, py = parent_win.winfo_x(), parent_win.winfo_y()
           pw, ph = parent_win.winfo_width(), parent_win.winfo_height()
           screen = get_monitor_by_point(px, py)

           # --- 尝试放右侧 ---
           if px + pw + win_width <= screen['right']:
               x, y = px + pw + 10, py
           # --- 尝试放下方 ---
           elif py + ph + win_height <= screen['bottom']:
               x, y = px, py + ph + 10
           # --- 尝试放左侧 ---
           elif px - win_width >= screen['left']:
               x, y = px - win_width - 10, py
           # --- 尝试放上方 ---
           elif py - win_height >= screen['top']:
               x, y = px, py - win_height - 10
           # --- 实在不行，屏幕居中 ---
           else:
               x = (screen['width'] - win_width) // 2
               y = (screen['height'] - win_height) // 2
        elif x_root is not None and y_root is not None:
           # 鼠标点的屏幕
           screen = get_monitor_by_point(x_root, y_root)
           x, y = x_root, y_root
           if x + win_width > screen['right']:
               x = max(screen['left'], x_root - win_width)
           if y + win_height > screen['bottom']:
               y = max(screen['top'], y_root - win_height)

        # 边界检查
        x = max(screen['left'], min(x, screen['right'] - win_width))
        y = max(screen['top'], min(y, screen['bottom'] - win_height))

        logger.info(f"[定位] x={x}, y={y}, screen={screen}")
        return x, y


    def get_centered_window_position(self,win_width, win_height, x_root=None, y_root=None, parent_win=None):
        """
        多屏环境下获取窗口显示位置
        """
        # 默认取主屏幕
        screen = get_monitor_by_point(0, 0)
        x = (screen['width'] - win_width) // 2
        y = (screen['height'] - win_height) // 2

        # 鼠标右键优先
        if x_root is not None and y_root is not None:
            screen = get_monitor_by_point(x_root, y_root)
            x, y = x_root, y_root
            if x + win_width > screen['right']:
                x = max(screen['left'], x_root - win_width)
            if y + win_height > screen['bottom']:
                y = max(screen['top'], y_root - win_height)

        # 父窗口位置
        elif parent_win is not None:
            parent_win.update_idletasks()
            px, py = parent_win.winfo_x(), parent_win.winfo_y()
            pw, ph = parent_win.winfo_width(), parent_win.winfo_height()
            screen = get_monitor_by_point(px, py)
            x = px + pw // 2 - win_width // 2
            y = py + ph // 2 - win_height // 2

        # 边界检查
        x = max(screen['left'], min(x, screen['right'] - win_width))
        y = max(screen['top'], min(y, screen['bottom'] - win_height))
        # logger.info(x,y)
        return x, y

    # def on_single_click(self, event):
    #     """统一处理 alert_tree 的单击和双击"""
    #     sel_row = self.tree.identify_row(event.y)
    #     sel_col = self.tree.identify_column(event.x)  # '#1', '#2' ...

    #     if not sel_row or not sel_col:
    #         return

    #     values = self.tree.item(sel_row, "values")
    #     if not values:
    #         return

    #     # item = self.tree.item(selected_item[0])
    #     # values = item.get("values")

    #     # 假设你的 tree 列是 (code, name, price, …)
    #     stock_info = {
    #         "code": values[0],
    #         "name": values[1] if len(values) > 1 else "",
    #         "extra": values  # 保留整行
    #     }
    #     self.selected_stock_info = stock_info

    #     if values:
    #         # stock_info = self.tree.item(selected_item, 'values')
    #         stock_code = values[0]

    #         send_tdx_Key = (self.select_code != stock_code)
    #         self.select_code = stock_code

    #         stock_code = str(stock_code).zfill(6)
    #         logger.info(f'stock_code:{stock_code}')
    #         # logger.info(f"选中股票代码: {stock_code}")
    #         if send_tdx_Key and stock_code:
    #             self.sender.send(stock_code)
    def on_single_click(self, event=None, values=None):
        """
        统一处理 alert_tree 的单击和双击
        event: Tkinter事件对象（Treeview点击）
        values: 可选，直接传入行数据（来自 KLineMonitor）
        """
        # 如果没有 values，就从 event 里取
        if values is None and event is not None:
            sel_row = self.tree.identify_row(event.y)
            sel_col = self.tree.identify_column(event.x)

            if not sel_row or not sel_col:
                return

            values = self.tree.item(sel_row, "values")
            if not values:
                return

        if not values:
            return

        # 假设你的 tree 列是 (code, name, price, …)
        stock_info = {
            "code": values[0],
            "name": values[1] if len(values) > 1 else "",
            "extra": values  # 保留整行
        }
        self.selected_stock_info = stock_info

        stock_code = values[0]

        send_tdx_Key = (getattr(self, "select_code", None) != stock_code)
        self.select_code = stock_code
        if event:   # 只在真实鼠标触发时保存
            self.event_x_root = event.x_root
            self.event_y_root = event.y_root
        self.on_tree_click_for_tooltip(event)

        stock_code = str(stock_code).zfill(6)
        logger.info(f'stock_code:{stock_code}')
        # logger.info(f"选中股票代码: {stock_code}")

        if send_tdx_Key and stock_code:
            self.sender.send(stock_code)


    def is_window_covered_by_main(self, win):
        """
        判断 win 是否完全在主窗口 self 范围内（可能被遮挡）
        返回 True 表示被覆盖
        """
        if not win.winfo_exists():
            return False

        main_x, main_y = self.winfo_x(), self.winfo_y()
        main_w, main_h = self.winfo_width(), self.winfo_height()

        win_x, win_y = win.winfo_x(), win.winfo_y()
        win_w, win_h = win.winfo_width(), win.winfo_height()

        inside_x = main_x <= win_x and win_x + win_w <= main_x + main_w
        inside_y = main_y <= win_y and win_y + win_h <= main_y + main_h

        return inside_x and inside_y


    def show_category_detail(self, code, name, category_content):
        def on_close():
            """关闭时清空引用"""
            try:
                self.save_window_position(self.detail_win, "detail_win_Category")
            except Exception:
                pass
            if self.detail_win and self.detail_win.winfo_exists():
                self.detail_win.destroy()
            self.detail_win = None
            self.txt_widget = None

        if self.detail_win and self.detail_win.winfo_exists():
            # 已存在 → 更新内容
            self.detail_win.title(f"{code} {name} - Category Details")
            self.txt_widget.config(state="normal")
            self.txt_widget.delete("1.0", tk.END)
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")

            # # 检查窗口是否最小化或被遮挡
            state = self.detail_win.state()
            # if state == "iconic":  # 最小化
            if (state == "iconic" or self.is_window_covered_by_main(self.detail_win)):
                self.detail_win.deiconify()  # 恢复
                self.detail_win.lift()
                self.detail_win.attributes("-topmost", True)
                self.detail_win.after(50, lambda: self.detail_win.attributes("-topmost", False))
            else:

                try:
                    if not self.detail_win.focus_displayof():
                        self.detail_win.lift()
                        self.detail_win.focus_force()
                except Exception:
                    pass

        else:
            # 第一次创建

            self.detail_win = tk.Toplevel(self)
            self.detail_win.title(f"{code} {name} - Category Details")
            # 先强制绘制一次
            # self.detail_win.update_idletasks()
            self.detail_win.withdraw()  # 先隐藏，避免闪到默认(50,50)

            self.load_window_position(self.detail_win, "detail_win_Category", default_width=400, default_height=200)

            # win_width, win_height = 400, 200
            # x, y = self.get_centered_window_position(win_width, win_height, parent_win=self)
            # self.detail_win.geometry(f"{win_width}x{win_height}+{x}+{y}")
            # 再显示出来
            self.detail_win.deiconify()

            # logger.info(
            #     f"位置: ({self.detail_win.winfo_x()}, {self.detail_win.winfo_y()}), "
            #     f"大小: {self.detail_win.winfo_width()}x{self.detail_win.winfo_height()}"
            # )
            # logger.info("geometry:", self.detail_win.geometry())
            # 字体设置
            # font_style = tkfont.Font(family="微软雅黑", size=12)
            self.txt_widget = tk.Text(self.detail_win, wrap="word", font=self.default_font)
            self.txt_widget.pack(expand=True, fill="both")
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")
            self.detail_win.lift()

            # 右键菜单
            menu = tk.Menu(self.detail_win, tearoff=0)
            menu.add_command(label="复制", command=lambda: self.detail_win.clipboard_append(self.txt_widget.selection_get()))
            menu.add_command(label="全选", command=lambda: self.txt_widget.tag_add("sel", "1.0", "end"))

            def show_context_menu(event):
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

            self.txt_widget.bind("<Button-3>", show_context_menu)
            # ESC 关闭
            self.detail_win.bind("<Escape>", lambda e: on_close())
            # 点窗口右上角 × 关闭
            self.detail_win.protocol("WM_DELETE_WINDOW", on_close)

            # 初次创建才强制前置
            self.detail_win.focus_force()
            self.detail_win.lift()

    def on_double_click(self, event):
        # logger.info(f'on_double_click')
        sel_row = self.tree.identify_row(event.y)
        sel_col = self.tree.identify_column(event.x)

        if not sel_row or not sel_col:
            return

        # 列索引
        col_idx = int(sel_col.replace("#", "")) - 1
        col_name = 'category'  # 这里假设只有 category 列需要弹窗

        vals = self.tree.item(sel_row, "values")
        if not vals:
            return

        # 获取股票代码
        code = vals[0]
        name = vals[1]

        # 通过 code 从 df_all 获取 category 内容
        try:
            category_content = self.df_all.loc[code, 'category']
        except KeyError:
            category_content = "未找到该股票的 category 信息"

        self.show_category_detail(code,name,category_content)
        pyperclip.copy(code)
        # # 如果 detail_win 已经存在，则更新内容，否则创建新的
        # if self.detail_win and self.detail_win.winfo_exists():
        #     self.detail_win.title(f"{code} { name }- Category Details")
        #     self.txt_widget.config(state="normal")
        #     self.txt_widget.delete("1.0", tk.END)
        #     self.txt_widget.insert("1.0", category_content)
        #     self.txt_widget.config(state="disabled")
        #     # self.detail_win.focus_force()           # 强制获得焦点
        #     # self.detail_win.lift()
        # else:
        #     self.detail_win = tk.Toplevel(self)
        #     self.detail_win.title(f"{code} { name }- Category Details")
        #     # self.detail_win.geometry("400x200")

        #     win_width, win_height = 400 , 200
        #     x, y = self.get_centered_window_position(win_width, win_height, parent_win=self)
        #     self.detail_win.geometry(f"{win_width}x{win_height}+{x}+{y}")
        #     # 字体设置
        #     font_style = tkfont.Font(family="微软雅黑", size=12)
        #     self.txt_widget = tk.Text(self.detail_win, wrap="word", font=font_style)
        #     self.txt_widget.pack(expand=True, fill="both")
        #     self.txt_widget.insert("1.0", category_content)
        #     self.txt_widget.config(state="disabled")
        #     self.detail_win.focus_force()           # 强制获得焦点
        #     self.detail_win.lift()                  # 提升到顶层

        #     # 右键菜单
        #     menu = tk.Menu(self.detail_win, tearoff=0)
        #     menu.add_command(label="复制", command=lambda: self.detail_win.clipboard_append(self.txt_widget.selection_get()))
        #     menu.add_command(label="全选", command=lambda: self.txt_widget.tag_add("sel", "1.0", "end"))

        #     def show_context_menu(event):
        #         try:
        #             menu.tk_popup(event.x_root, event.y_root)
        #         finally:
        #             menu.grab_release()

        #     self.txt_widget.bind("<Button-3>", show_context_menu)
        #     # 绑定 ESC 键关闭窗口
        #     self.detail_win.bind("<Escape>", lambda e: self.detail_win.destroy())

        # # 弹窗显示 category 内容
        # detail_win = tk.Toplevel(self)
        # detail_win.title(f"{code} - Category Details")
        # # detail_win.geometry("400x200")

        # win_width, win_height = 400 , 200
        # x, y = self.get_centered_window_position(win_width, win_height, parent_win=self)
        # detail_win.geometry(f"{win_width}x{win_height}+{x}+{y}")

        # # 设置字体
        # font_style = tkfont.Font(family="微软雅黑", size=12)  # 可以换成你想要的字体和大小

        # txt = tk.Text(detail_win, wrap="word", font=font_style)
        # txt.pack(expand=True, fill="both")
        # txt.insert("1.0", category_content)
        # txt.config(state="disabled")



    def on_tree_right_click(self, event):
        """右键点击 TreeView 行"""
        # 确保选中行
        item_id = self.tree.identify_row(event.y)
        # if item_id:
        #     self.tree.selection_set(item_id)
            # self.tree_menu.post(event.x_root, event.y_root)
        # selected_item = self.tree.selection()

        if item_id:
            # 选中该行
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            
            # 获取基本信息
            values = self.tree.item(item_id, 'values')
            stock_code = values[0]
            stock_name = values[1] if len(values) > 1 else "未知"
            
            # 创建菜单
            menu = tk.Menu(self, tearoff=0)
            
            menu.add_command(label=f"📝 复制提取信息 ({stock_code})", 
                            command=lambda: self.copy_stock_info(stock_code))
                            
            menu.add_separator()
            
            menu.add_command(label="🏷️ 添加标注备注", 
                            command=lambda: self.add_stock_remark(stock_code, stock_name))
            
            menu.add_command(label="🔔 加入语音预警",
                            command=lambda: self.add_voice_monitor_dialog(stock_code, stock_name))
                            
            menu.add_command(label="📖 查看标注手札", 
                            command=lambda: self.view_stock_remarks(stock_code, stock_name))
            
            menu.add_separator()
            
            menu.add_command(label=f"🚀 发送到关联软件", 
                            command=lambda: self.original_push_logic(stock_code))
                            
            # 弹出菜单
            menu.post(event.x_root, event.y_root)

    def get_stock_info_text(self, code):
        """获取格式化的股票信息文本"""
        if code not in self.df_all.index:
            return None
            
        stock_data = self.df_all.loc[code]
        
        # 计算/获取字段
        name = stock_data.get('name', 'N/A')
        close = stock_data.get('trade', 'N/A')
        
        # 计算 Boll
        upper = stock_data.get('upper', 'N/A')
        lower = stock_data.get('lower', 'N/A')
        
        # 判断逻辑
        try:
            high = float(stock_data.get('high', 0))
            low = float(stock_data.get('low', 0))
            c_close = float(close) if close != 'N/A' else 0
            c_upper = float(upper) if upper != 'N/A' else 0
            c_lower = float(lower) if lower != 'N/A' else 0
            
            boll = "Yes" if high > c_upper else "No"
            breakthrough = "Yes" if high > c_upper else "No"
            
            # 信号图标逻辑
            signal_val = stock_data.get('signal', '')
            signal_icon = "🔴" if signal_val else "⚪"
            
            # 强势判断 (L1>L2 & H1>H2 这种需要历史数据，这里简化)
            strength = "Check Graph" 
            
        except Exception:
            boll = "CalcError"
            breakthrough = "Unknown"
            signal_icon = "?"
            strength = "Unknown"

        # 构建文本
        info_text = (
            f"【{code}】{name}:{close}\n"
            f"{'─' * 20}\n"
            f"📊 换手率: {stock_data.get('ratio', 'N/A')}\n"
            f"📊 成交量: {stock_data.get('volume', 'N/A')}\n"
            f"🔴 连阳: {stock_data.get('red', 'N/A')}\n"
            f"📈 突破布林: {boll}\n"
            f"  signal: {signal_icon} (low<10 & C>5)\n"
            f"  Upper:  {upper}\n"
            f"  Lower:  {lower}\n"
            f"🚀 突破: {breakthrough} (high > upper)\n"
            f"💪 强势: {strength} (L1>L2 & H1>H2)"
        )
        return info_text

    def original_push_logic(self, stock_code):
        """原有的推送逻辑 + 自动添加手札"""
        try:
            # 1. 尝试获取价格和信息，用于自动添加备注
            close_price = "N/A"
            info_text = ""
            if stock_code in self.df_all.index:
                close_price = self.df_all.loc[stock_code].get('trade', 'N/A')
                info_text = self.get_stock_info_text(stock_code)

            # 2. 执行原有推送
            if self.push_stock_info(stock_code, self.df_all.loc[stock_code] if stock_code in self.df_all.index else None):
                 self.status_var2.set(f"发送成功: {stock_code}")
                 
                 # 3. 如果发送成功，自动添加手札
                 if info_text:
                     # 构造备注内容
                     remark_content = f"添加Close:{close_price}\n{info_text}"
                     self.handbook.add_remark(stock_code, remark_content)
                     logger.info(f"已自动添加手札: {stock_code}")
                     
                     # 可选：也复制到剪贴板，方便粘贴
                     pyperclip.copy(remark_content)

            else:
                 self.status_var2.set(f"发送失败: {stock_code}")

        except Exception as e:
            logger.error(f"Push logic error: {e}")

    def copy_stock_info(self, code):
        """提取并复制格式化信息"""
        try:
            info_text = self.get_stock_info_text(code)
            if not info_text:
                messagebox.showwarning("数据缺失", f"未找到代码 {code} 的完整数据")
                return

            pyperclip.copy(info_text)
            
            # 获取名称用于提示
            name = "未知"
            if code in self.df_all.index:
                name = self.df_all.loc[code].get('name', '未知')
                
            self.status_var2.set(f"已复制 {name} 信息")
            
        except Exception as e:
            logger.error(f"Copy Info Error: {e}")
            messagebox.showerror("错误", f"提取信息失败: {e}")

    def add_stock_remark(self, code, name):
        """添加备注 - 使用自定义窗口支持多行"""
        try:
            win = tk.Toplevel(self)
            win.title(f"添加备注 - {name} ({code})")
            
            # --- 窗口定位: 右下角在鼠标附近 ---
            w, h = 500, 300
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            pos_x, pos_y = mx - w - 20, my - h - 20
            pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            
            tk.Label(win, text="请输入备注/心得 (支持多行/粘贴，Ctrl+Enter保存):").pack(anchor="w", padx=10, pady=5)
            
            text_area = tk.Text(win, wrap="word", height=10, font=("Arial", 10))
            text_area.pack(fill="both", expand=True, padx=10, pady=5)
            text_area.focus_set()
            
            # --- 1. 右键菜单 (支持粘贴) ---
            def show_text_menu(event):
                menu = tk.Menu(win, tearoff=0)
                menu.add_command(label="剪切", command=lambda: text_area.event_generate("<<Cut>>"))
                menu.add_command(label="复制", command=lambda: text_area.event_generate("<<Copy>>"))
                menu.add_command(label="粘贴", command=lambda: text_area.event_generate("<<Paste>>"))
                menu.add_separator()
                menu.add_command(label="全选", command=lambda: text_area.tag_add("sel", "1.0", "end"))
                menu.post(event.x_root, event.y_root)

            text_area.bind("<Button-3>", show_text_menu)

            # --- 保存逻辑 ---
            def save(event=None):
                content = text_area.get("1.0", "end-1c").strip()
                if content:
                    self.handbook.add_remark(code, content)
                    messagebox.showinfo("成功", "备注已添加", parent=win)
                    win.destroy()
                else:
                    win.destroy()  # 空内容直接关闭
                    
            def cancel(event=None):
                save()
                win.destroy()
                return "break"
            
            # --- 2. 快捷键绑定 ---
            # 回车自动保存 (Ctrl+Enter)
            text_area.bind("<Control-Return>", save)
            
            win.bind("<Escape>", cancel)

            btn_frame = tk.Frame(win)
            btn_frame.pack(pady=10)
            tk.Button(btn_frame, text="保存 (Ctrl+Enter)", width=15, command=save, bg="#e1f5fe").pack(side="left", padx=10)
            tk.Button(btn_frame, text="取消 (ESC)", width=10, command=cancel).pack(side="left", padx=10)
        except Exception as e:
            logger.error(f"Add remark error: {e}")

    def view_stock_remarks(self, code, name):
        """查看备注手札窗口"""
        try:
            win = tk.Toplevel(self)
            win.title(f"标注手札 - {name} ({code})")
            
            # --- 窗口定位 ---
            w, h = 600, 500
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            pos_x, pos_y = mx - w - 20, my - h - 20
            pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            
            # ESC 关闭
            def close_view_win(event=None):
                win.destroy()
                return "break"
            win.bind("<Escape>", close_view_win)
            
            # ... UI 构建 ...
            # --- 顶部信息区域 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text=f"【{code}】{name}", font=("Microsoft YaHei", 14, "bold"), fg="#333").pack(anchor="w")
            
            category_info = "暂无板块信息"
            if code in self.df_all.index:
                row = self.df_all.loc[code]
                cats = row.get('category', '')
                if cats:
                    category_info = f"板块: {cats}"
            
            msg = tk.Message(top_frame, text=category_info, width=560, font=("Arial", 10), fg="#666") 
            msg.pack(anchor="w", fill="x", pady=2)

            tk.Label(top_frame, text="💡 双击查看 / 右键删除 / ESC关闭", fg="gray", font=("Arial", 9)).pack(anchor="e")

            # --- 列表区域 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            columns = ("time", "content")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            tree.heading("time", text="时间")
            tree.heading("content", text="内容概要")
            tree.column("time", width=140, anchor="center", stretch=False)
            tree.column("content", width=400, anchor="w")
            
            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            # 加载数据
            remarks = self.handbook.get_remarks(code)
            for r in remarks:
                raw_content = r['content']
                display_content = raw_content.replace('\n', ' ')
                if len(display_content) > 50:
                    display_content = display_content[:50] + "..."
                tree.insert("", "end", values=(r['time'], display_content))
            
            # --- 详情弹窗 ---
            def show_detail_window(time_str, content, click_x=None, click_y=None):
                d_win = tk.Toplevel(win)
                d_win.title(f"手札详情 - {time_str}")
                
                dw, dh = 600, 450
                if click_x is None:
                    click_x = d_win.winfo_pointerx()
                    click_y = d_win.winfo_pointery()
                
                dx, dy = click_x - dw - 20, click_y - dh - 20
                dx, dy = max(0, dx), max(0, dy)
                d_win.geometry(f"{dw}x{dh}+{dx}+{dy}")
                
                # ESC 关闭详情
                def close_detail_win(event=None):
                    d_win.destroy()
                    return "break" # 阻止事件传播
                d_win.bind("<Escape>", close_detail_win)
                
                # 设为 Topmost 并获取焦点，防止误触底层
                d_win.attributes("-topmost", True)
                d_win.focus_force()
                d_win.grab_set() # 模态窗口，强制焦点直到关闭
                
                tk.Label(d_win, text=f"记录时间: {time_str}", font=("Arial", 10, "bold"), fg="#004d40").pack(pady=5, anchor="w", padx=10)
                
                txt_frame = tk.Frame(d_win)
                txt_frame.pack(fill="both", expand=True, padx=10, pady=5)
                
                txt_scroll = ttk.Scrollbar(txt_frame)
                txt = tk.Text(txt_frame, wrap="word", font=("Arial", 11), yscrollcommand=txt_scroll.set, padx=5, pady=5)
                txt_scroll.config(command=txt.yview)
                
                txt.pack(side="left", fill="both", expand=True)
                txt_scroll.pack(side="right", fill="y")
                
                txt.insert("1.0", content)
                txt.config(state="disabled") 
                
                def copy_content():
                    try:
                        win.clipboard_clear()
                        win.clipboard_append(content)
                        messagebox.showinfo("提示", "内容已复制", parent=d_win)
                    except:
                        pass
                
                btn_frame = tk.Frame(d_win)
                btn_frame.pack(pady=5)
                tk.Button(btn_frame, text="复制全部", command=copy_content).pack(side="left", padx=10)
                tk.Button(btn_frame, text="关闭 (ESC)", command=d_win.destroy).pack(side="left", padx=10)

            def on_double_click(event):
                item = tree.selection()
                if not item: return
                values = tree.item(item[0], "values")
                time_str = values[0]
                
                full_content = ""
                for r in self.handbook.get_remarks(code):
                    if r['time'] == time_str:
                        full_content = r['content']
                        break
                
                if full_content:
                    show_detail_window(time_str, full_content, event.x_root, event.y_root)

            tree.bind("<Double-1>", on_double_click)

            # 右键删除
            def on_rmk_right_click(event):
                item = tree.identify_row(event.y)
                if item:
                    tree.selection_set(item)
                    menu = tk.Menu(win, tearoff=0)
                    menu.add_command(label="删除此条", command=lambda: delete_current(item))
                    menu.post(event.x_root, event.y_root)
                    
            def delete_current(item):
                values = tree.item(item, "values")
                time_str = values[0]
                confirm = messagebox.askyesno("确认", "确定删除这条备注吗?", parent=win)
                if confirm:
                    target_ts = None
                    for r in self.handbook.get_remarks(code):
                        if r['time'] == time_str:
                            target_ts = r['timestamp']
                            break
                    if target_ts:
                        self.handbook.delete_remark(code, target_ts)
                        tree.delete(item)
            
            tree.bind("<Button-3>", on_rmk_right_click)
        except Exception as e:
            logger.error(f"View remarks error: {e}")
            messagebox.showerror("Error", f"开启手札失败: {e}")

    def open_handbook_overview(self):
        """手札总览窗口"""
        try:
            win = tk.Toplevel(self)
            win.title("手札总览")
            # --- 窗口定位 ---
            w, h = 900, 600
            # 居中显示
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            pos_x = (sw - w) // 2
            pos_y = (sh - h) // 2
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            
            # ESC 关闭
            win.bind("<Escape>", lambda e: win.destroy())
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 顶部滤镜/操作区域 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text="🔍 快速浏览所有手札", font=("Arial", 12, "bold")).pack(side="left")
            
            # --- 列表区域 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            columns = ("time", "code", "name", "content")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            # 排序状态
            self._hb_sort_col = None
            self._hb_sort_reverse = False

            def treeview_sort_column(col):
                """通用排序函数"""
                l = [(tree.set(k, col), k) for k in tree.get_children('')]
                
                # 简单值比较
                l.sort(reverse=self._hb_sort_reverse)
                self._hb_sort_reverse = not self._hb_sort_reverse  # 反转

                for index, (val, k) in enumerate(l):
                    tree.move(k, '', index)
                    
                # 更新表头显示 (可选)
                for c in columns:
                     tree.heading(c, text=c.capitalize()) # 重置
                
                arrow = "↓" if self._hb_sort_reverse else "↑"
                tree.heading(col, text=f"{col.capitalize()} {arrow}")

            tree.heading("time", text="时间", command=lambda: treeview_sort_column("time"))
            tree.heading("code", text="代码", command=lambda: treeview_sort_column("code"))
            tree.heading("name", text="名称", command=lambda: treeview_sort_column("name"))
            tree.heading("content", text="内容概要", command=lambda: treeview_sort_column("content"))
            
            tree.column("time", width=160, anchor="center")
            tree.column("code", width=100, anchor="center")
            tree.column("name", width=120, anchor="center")
            tree.column("content", width=500, anchor="w")
            
            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            # --- 加载数据 ---
            all_data = self.handbook.get_all_remarks() 
            # all_data format: { "code1": [ {time, content, timestamp}, ... ], ... }
            
            flat_rows = []
            for code, remarks in all_data.items():
                name = "Unknown"
                if code in self.df_all.index:
                    name = self.df_all.loc[code].get('name', 'N/A')
                
                for r in remarks:
                    raw = r['content'].replace('\n', ' ')
                    if len(raw) > 60:
                        raw = raw[:60] + "..."
                    flat_rows.append({
                        "time": r['time'],
                        "code": code,
                        "name": name,
                        "content": raw,
                        "timestamp": r.get('timestamp', 0),
                        "full_content": r['content']
                    })
            
            # 默认按时间倒序
            flat_rows.sort(key=lambda x: x['time'], reverse=True)
            
            for row in flat_rows:
                tree.insert("", "end", values=(row['time'], row['code'], row['name'], row['content']))



            def on_handbook_right_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return
                values = tree.item(item_id, "values")
                # values: (time, code, name, content_preview)
                target_code = values[1]
                stock_code = str(target_code).zfill(6)
                # pyperclip.copy(stock_code)
                # toast_message(self, f"stock_code: {stock_code} 已复制")
                self.tree_scroll_to_code(stock_code)

            def on_handbook_on_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return

                values = tree.item(item_id, "values")
                # values: (time, code, name, content_preview)

                target_time = values[0]
                target_code = values[1]
                target_name = values[2]

                stock_code = str(target_code).zfill(6)
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)

            def on_handbook_tree_select(event):
                item = tree.selection()
                if not item: return
                values = tree.item(item[0], "values")
                # values: (time, code, name, content_preview)
                
                target_code = values[1]
                target_time = values[0]
                target_name = values[2]
                stock_code = str(target_code).zfill(6)
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)

            # --- 双击事件 (复用之前的 detail window) ---
            def on_handbook_double_click(event):
                item = tree.selection()
                if not item: return
                values = tree.item(item[0], "values")
                # values: (time, code, name, content_preview)
                
                target_code = values[1]
                target_time = values[0]
                target_name = values[2]
                
                # 再次查找完整内容 (效率稍低但简单)
                full_content = ""
                rmks = self.handbook.get_remarks(target_code)
                for r in rmks:
                    if r['time'] == target_time:
                        full_content = r['content']
                        break
                
                if full_content:
                    # 调用之前定义的 show_detail_window ?
                    # 由于作用域问题，最好是把 show_detail_window 提出来变成类方法，
                    # 或者这里再复制一份简单的。为避免重复代码，这里简单实现一个。
                    # logger.info(f'on_handbook_double_click stock_code:{target_code} name:{target_name}')
                    show_simple_detail(target_time, target_code, values[2], full_content, event.x_root, event.y_root)

            def show_simple_detail(time_str, code, name, content, cx, cy):
                d_win = tk.Toplevel(win)
                d_win.title(f"手札详情 - {name}({code})")
                d_win.attributes("-topmost", True)
                
                dw, dh = 600, 450
                dx, dy = cx - dw - 20, cy - dh - 20
                dx, dy = max(0, dx), max(0, dy)
                d_win.geometry(f"{dw}x{dh}+{dx}+{dy}")
                
                d_win.bind("<Escape>", lambda e: d_win.destroy())
                d_win.focus_force()
                d_win.grab_set()

                tk.Label(d_win, text=f"股票: {name} ({code})   时间: {time_str}", font=("Arial", 10, "bold"), fg="#004d40").pack(pady=5, anchor="w", padx=10)
                
                txt_frame = tk.Frame(d_win)
                txt_frame.pack(fill="both", expand=True, padx=10, pady=5)
                
                txt_scroll = ttk.Scrollbar(txt_frame)
                txt = tk.Text(txt_frame, wrap="word", font=("Arial", 11), yscrollcommand=txt_scroll.set, padx=5, pady=5)
                txt_scroll.config(command=txt.yview)
                
                txt.pack(side="left", fill="both", expand=True)
                txt_scroll.pack(side="right", fill="y")
                
                txt.insert("1.0", content)
                txt.config(state="disabled") 
                
                tk.Button(d_win, text="关闭 (ESC)", command=d_win.destroy).pack(pady=5)

            tree.bind("<Button-1>", on_handbook_on_click)
            tree.bind("<Button-3>", on_handbook_right_click)
            tree.bind("<Double-1>", on_handbook_double_click)
            tree.bind("<<TreeviewSelect>>", on_handbook_tree_select) 
        except Exception as e:
            logger.error(f"Handbook Overview Error: {e}")
            messagebox.showerror("错误", f"打开总览失败: {e}")

    def _create_monitor_ref_panel(self, parent, row_data, curr_price, set_callback):
        """创建监控参考数据面板"""
        if row_data is None:
            tk.Label(parent, text="无详细数据", fg="#999").pack(pady=20)
            return

        def create_clickable_info(p, label, value, value_type="price"):
            f = tk.Frame(p)
            f.pack(fill="x", pady=2)
            
            lbl_name = tk.Label(f, text=f"{label}:", width=10, anchor="w", fg="#666")
            lbl_name.pack(side="left")
            
            # 价格对比逻辑
            val_str = f"{value}"
            arrow = ""
            arrow_fg = ""
            
            if isinstance(value, float):
                val_str = f"{value:.2f}"
                if value_type == "price" and curr_price > 0 and value > 0:
                    if value > curr_price:
                        arrow =  "🟥 "
                        # arrow = "🔴 "

                        arrow_fg = "green"
                    elif value < curr_price:
                        arrow =  "🟩 "
                        # arrow = "🟢 "
                        arrow_fg = "red"
            
            # 如果有箭头，先显示箭头
            if arrow:
                tk.Label(f, text=arrow, fg=arrow_fg, font=("Arial", 10, "bold")).pack(side="left")
            
            lbl_val = tk.Label(f, text=val_str, fg="blue", cursor="hand2", font=("Arial", 10, "underline"))
            lbl_val.pack(side="left")
            
            def on_click(e):
                set_callback(val_str, value_type, value)
                # Flash effect
                lbl_val.config(fg="red")
                parent.after(200, lambda: lbl_val.config(fg="blue"))
                
            lbl_val.bind("<Button-1>", on_click)
            
        # 指标列表
        metrics = [
            ("MA5", row_data.get('ma5d', 0), "price"),
            ("MA10", row_data.get('ma10d', 0), "price"),
            ("MA20", row_data.get('ma20d', 0), "price"),
            ("MA30", row_data.get('ma30d', 0), "price"),
            ("MA60", row_data.get('ma60d', 0), "price"),
            ("压力位", row_data.get('support_next', 0), "price"),
            ("支撑位", row_data.get('support_today', 0), "price"),
            ("上轨", row_data.get('upper', 0), "price"),
            ("下轨", row_data.get('lower', 0), "price"),
            ("昨收", row_data.get('lastp1d', 0), "price"),
            ("开盘", row_data.get('open', 0), "price"),
            ("最高", row_data.get('high', 0), "price"),
            ("最低", row_data.get('low', 0), "price"),
            ("涨停价", row_data.get('high_limit', 0), "price"),
            ("跌停价", row_data.get('low_limit', 0), "price"),
        ]
        
        # 涨幅类
        if 'per1d' in row_data:
            metrics.append(("昨日涨幅%", row_data['per1d'], "percent"))
        if 'per2d' in row_data:
            metrics.append(("前日涨幅%", row_data['per2d'], "percent"))
            
        for label, val, vtype in metrics:
            try:
                if val is None: continue
                v = float(val)
                if abs(v) > 0.001: # 过滤0值
                    create_clickable_info(parent, label, v, vtype)
            except:
                pass

    def add_voice_monitor_dialog(self, code, name):
        """
        弹出添加预警监控的对话框 (优化版)
        """
        try:
            win = tk.Toplevel(self)
            win.title(f"添加语音预警 - {name} ({code})")
            window_id = "添加语音预警"
            # --- 窗口定位 & 尺寸调整 ---
            # w, h = 750, 520# 增加高度以容纳更多数据
            # mx, my = self.winfo_pointerx(), self.winfo_pointery()
            # pos_x, pos_y = mx - w - 20, my - h - 20
            # pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            # win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            # win.bind("<Escape>", lambda e: win.destroy())
            self.load_window_position(win, window_id, default_width=900, default_height=650)
            # --- 布局 ---
            main_frame = tk.Frame(win)
            main_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            left_frame = tk.Frame(main_frame) 
            left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
            
            right_frame = tk.LabelFrame(main_frame, text="参考数据 (点击自动填入)", width=380)
            right_frame.pack(side="right", fill="both", padx=(10, 0))
            # right_frame.pack_propagate(False)

            # --- 左侧：输入区域 ---
            
            # 获取当前数据
            curr_price = 0.0
            curr_change = 0.0
            row_data = None
            if code in self.df_all.index:
                row_data = self.df_all.loc[code]
                try:
                    curr_price = float(row_data.get('trade', 0))
                    curr_change = float(row_data.get('changepercent', 0))
                except:
                    pass
            
            tk.Label(left_frame, text=f"当前价格: {curr_price}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
            tk.Label(left_frame, text=f"当前涨幅: {curr_change:.2f}%", font=("Arial", 10), fg="#b71c1c" if curr_change>=0 else "#00695c").pack(pady=5, anchor="w")
            
            tk.Label(left_frame, text="选择监控类型:").pack(anchor="w", pady=(15, 5))
            
            type_var = tk.StringVar(value="price_up")
            e_val_var = tk.StringVar(value=str(curr_price)) # 绑定Entry变量
            
            def on_type_change():
                """切换类型时更新默认值"""
                t = type_var.get()
                if t == "change_up":
                     # 切换到涨幅时，填入当前涨幅方便修改，或者清空
                     e_val_var.set(f"{curr_change:.2f}")
                else:
                     # 切换回价格
                     e_val_var.set(str(curr_price))

            types = [("价格突破 (Price >=)", "price_up"), 
                     ("价格跌破 (Price <=)", "price_down"),
                     ("涨幅超过 (Change% >=)", "change_up")]
            
            for text, val in types:
                tk.Radiobutton(left_frame, text=text, variable=type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)
                
            tk.Label(left_frame, text="触发阈值:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))
            
            # 阈值输入区域 (包含 +/- 按钮)
            val_frame = tk.Frame(left_frame)
            val_frame.pack(fill="x", padx=10, pady=5)
            
            e_val = tk.Entry(val_frame, textvariable=e_val_var, font=("Arial", 12))
            e_val.pack(side="left", fill="x", expand=True)
            e_val.focus() # 聚焦
            
            def adjust_val(pct):
                try:
                    current_val = float(e_val_var.get())
                    # 如果是价格，按比例调整
                    # 如果是涨幅(小于20通常视为涨幅)，直接加减数值?
                    # 按照用户需求 "1%增加或减少"，如果是价格通常指价格 * 1.01
                    # 如果是涨幅类型，通常指涨幅 + 1
                    
                    t = type_var.get()
                    if t == "change_up":
                         # 涨幅直接加减 1 (单位%)
                         new_val = current_val + pct
                    else:
                         # 价格按百分比调整
                         new_val = current_val * (1 + pct/100)
                    
                    e_val_var.set(f"{new_val:.2f}")
                except ValueError:
                    pass

            # 按钮
            tk.Button(val_frame, text="-1%", width=4, command=lambda: adjust_val(-1)).pack(side="left", padx=2)
            tk.Button(val_frame, text="+1%", width=4, command=lambda: adjust_val(1)).pack(side="left", padx=2)

            # --- 右侧：数据参考面板 ---
            def set_val_callback(val_str, value_type, value):
                e_val_var.set(val_str)
                if value_type == "percent":
                    type_var.set("change_up")
                else:
                    if value > curr_price:
                        type_var.set("price_up")
                    else:
                        type_var.set("price_down")

            self._create_monitor_ref_panel(right_frame, row_data, curr_price, set_val_callback)

            # --- 底部按钮 ---
            btn_frame = tk.Frame(win)
            btn_frame.pack(side="bottom", fill="x", pady=10, padx=10)
            
            def confirm(event=None):
                val_str = e_val_var.get()
                try:
                    val = float(val_str)
                    rtype = type_var.get()
                    
                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.add_monitor(code, name, rtype, val)
                        # 自动关闭，不再弹窗确认，提升效率 (或者用 toast)
                        # messagebox.showinfo("成功", f"已添加监控: {name} {rtype} {val}", parent=win)
                        logger.info(f"Monitor added: {name} {rtype} {val}")
                        on_close()   # ✅ 正确
                    else:
                        messagebox.showerror("错误", "实时监控模块未初始化", parent=win)
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的数字", parent=win)
            # ESC / 关闭
            def on_close(event=None):
                # update_window_position(window_id)
                self.save_window_position(win, window_id)
                win.destroy()

            win.bind("<Escape>", on_close)
            win.protocol("WM_DELETE_WINDOW", on_close)
            win.bind("<Return>", confirm)
            tk.Button(btn_frame, text="确认添加 (Enter)", command=confirm, bg="#ccff90", height=2).pack(side="left", fill="x", expand=True, padx=5)
            tk.Button(btn_frame, text="取消 (Esc)", command=on_close, height=2).pack(side="left", fill="x", expand=True, padx=5)
            
        except Exception as e:
            logger.error(f"Add monitor dialog error: {e}")
            messagebox.showerror("Error", f"开启监控对话框失败: {e}")

    def _init_live_strategy(self):
        """延迟初始化策略模块"""
        try:
            self.live_strategy = StockLiveStrategy(alert_cooldown=alert_cooldown)
            # 注册报警回调
            self.live_strategy.set_alert_callback(self.on_voice_alert)
            logger.info("✅ 实时监控策略模块已启动")
        except Exception as e:
            logger.error(f"Failed to init live strategy: {e}")

    def on_voice_alert(self, code, name, msg):
        """
        处理语音报警触发: 弹窗显示股票详情
        """
        # 必须回到主线程操作 GUI
        self.after(0, lambda: self._show_alert_popup(code, name, msg))

    def _update_alert_positions(self):
        """重新排列所有报警弹窗"""
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
            
        # Right-Bottom origin
        w, h = 400, 260 # 稍微增高
        margin = 10
        taskbar = 80 # 避开任务栏
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        
        # Max columns that fit
        max_cols = (sw - 100) // (w + margin)
        if max_cols < 1: max_cols = 1
        
        # 清理已销毁的窗口
        self.active_alerts = [win for win in self.active_alerts if win.winfo_exists()]

        for i, win in enumerate(self.active_alerts):
            try:
                col = i % max_cols
                row = i // max_cols
                
                # 从右向左排列
                x = sw - (col + 1) * (w + margin)
                y = sh - taskbar - (row + 1) * (h + margin)
                
                win.geometry(f"{w}x{h}+{x}+{y}")
            except Exception as e:
                logger.error(f"Resize alert error: {e}")

    def _close_alert(self, win):
        """关闭弹窗并刷新布局"""
        if hasattr(self, 'active_alerts') and win in self.active_alerts:
            self.active_alerts.remove(win)
        win.destroy()
        self.after(100, self._update_alert_positions)

    def _show_alert_popup(self, code, name, msg):
        """显示报警弹窗"""
        try:
            if not hasattr(self, 'active_alerts'):
                self.active_alerts = []
                
            # 获取 category content
            category_content = "暂无详细信息"
            if code in self.df_all.index:
                category_content = self.df_all.loc[code].get('category', '')
            
            win = tk.Toplevel(self)
            win.title(f"🔔 触发报警 - {name} ({code})")
            win.attributes("-topmost", True) # 强制置顶
            win.attributes("-toolwindow", True) # 工具窗口样式
            
            # 记录并定位
            self.active_alerts.append(win)
            self._update_alert_positions()
            
            # 关闭回调
            win.protocol("WM_DELETE_WINDOW", lambda: self._close_alert(win))
            
            # 自动关闭 (60秒)
            self.after(2*60000, lambda: self._close_alert(win))
            
            # 闪烁效果
            def flash(count=0):
                if not win.winfo_exists(): return
                if count > 6: return
                bg = "#ffcdd2" if count % 2 == 0 else "#ffebee"
                win.configure(bg=bg)
                win.after(300, lambda: flash(count+1))
            flash()
            
            # 内容框架
            frame = tk.Frame(win, bg="#fff", padx=10, pady=10)
            frame.pack(fill="both", expand=True)

            # --- 底部按钮区 (优先 Pack 保证可见) ---
            def send_to_tdx():
                if hasattr(self, 'sender'):
                     try:
                        self.sender.send(code)
                        btn_send.config(text="✅ 已发送", bg="#ccff90")
                     except Exception as e:
                        logger.error(f"Send stock error: {e}")
                else:
                     logger.warning("Sender module not available")

            btn_frame = tk.Frame(frame, bg="#fff")
            btn_frame.pack(side="bottom", fill="x", pady=5)
            
            btn_send = tk.Button(btn_frame, text="🚀 发送到通达信", command=send_to_tdx, bg="#e0f7fa", font=("Arial", 10, "bold"), cursor="hand2")
            btn_send.pack(side="left", fill="x", expand=True, padx=5)
            
            tk.Button(btn_frame, text="关闭", command=lambda: self._close_alert(win), bg="#eee").pack(side="right", padx=5)

            # --- 上部内容 ---
            tk.Label(frame, text=f"⚠️{code} {msg}", font=("Microsoft YaHei", 12, "bold"), fg="#d32f2f", bg="#fff", wraplength=380).pack(pady=5)
            # tk.Label(frame, text=f"[{code}] {name}", font=("Arial", 14, "bold"), bg="#fff").pack(pady=5)
            
            # 详情文本 (自适应剩余空间)
            text_box = tk.Text(frame, height=4, font=("Arial", 10), bg="#f5f5f5", relief="flat")
            text_box.pack(fill="both", expand=True, pady=5)
            text_box.insert("1.0", category_content)
            text_box.config(state="disabled")
            
        except Exception as e:
            logger.error(f"Show alert popup error: {e}")

    def open_voice_monitor_manager(self):
        """语音预警管理窗口"""
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("提示", "实时监控模块尚未启动，请稍后再试")
            return

        try:
            win = tk.Toplevel(self)
            win.title("语音预警管理")
            window_id = "语音预警管理"
            # --- 窗口定位 ---
            # w, h = 800, 500
            # sw = self.winfo_screenwidth()
            # sh = self.winfo_screenheight()
            # pos_x = (sw - w) // 2
            # pos_y = (sh - h) // 2
            # win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            # win.bind("<Escape>", lambda e: win.destroy())
            self.load_window_position(win, window_id, default_width=800, default_height=500)
            # --- 顶部操作区域 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text="🔔 实时语音监控列表", font=("Arial", 12, "bold")).pack(side="left")
            
            tk.Button(top_frame, text="测试报警音", command=lambda: self.live_strategy.test_alert(), bg="#e0f7fa").pack(side="right", padx=5)
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 列表区域 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 显示 ID 是为了方便管理 (code + rule_index)
            columns = ("code", "name", "rule_type", "value", "id")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            tree.heading("code", text="代码")
            tree.heading("name", text="名称")
            tree.heading("rule_type", text="规则类型")
            tree.heading("value", text="阈值")
            tree.heading("id", text="ID (Code_Idx)")
            
            tree.column("code", width=80, anchor="center")
            tree.column("name", width=100, anchor="center")
            tree.column("rule_type", width=150, anchor="center")
            tree.column("value", width=100, anchor="center")
            tree.column("id", width=0, stretch=False) # 隐藏 ID 列
            
            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            def load_data():
                """加载数据到列表"""
                for item in tree.get_children():
                    tree.delete(item)
                    
                monitors = self.live_strategy.get_monitors()
                for code, data in monitors.items():
                    name = data['name']
                    rules = data['rules']
                    for idx, rule in enumerate(rules):
                        rtype_map = {
                            "price_up": "价格突破 >=",
                            "price_down": "价格跌破 <=",
                            "change_up": "涨幅超过 >="
                        }
                        display_type = rtype_map.get(rule['type'], rule['type'])
                        # unique id
                        uid = f"{code}_{idx}"
                        tree.insert("", "end", values=(code, name, display_type, rule['value'], uid))

            load_data()
            
            # --- 底部按钮 ---
            btn_frame = tk.Frame(win)
            btn_frame.pack(pady=10)
            
            def add_new():
                # 弹出一个简单的输入框，或者复用 add_voice_monitor_dialog
                # 但 add_voice_monitor_dialog 需要 code, name 参数
                # 这里可以做一个更通用的添加对话框
                
                add_win = tk.Toplevel(win)
                add_win.title("添加新监控")
                wx, wy = win.winfo_x() + 100, win.winfo_y() + 100
                add_win.geometry(f"300x250+{wx}+{wy}")
                
                tk.Label(add_win, text="股票代码:").pack(anchor="w", padx=20, pady=5)
                e_code = tk.Entry(add_win)
                e_code.pack(fill="x", padx=20)
                
                # 监控类型等复用之前的逻辑
                # ... 为简化，这里建议用户先在主界面右键添加，这里主要做管理
                # 或者调用之前的 dialog，但要先手动输入 code 获取 name
                pass
                
                # 简化实现：提示用户去主界面添加
                messagebox.showinfo("提示", "请在主界面股票列表右键点击股票添加监控", parent=add_win)
                add_win.destroy()

            def delete_selected(event=None):
                selected = tree.selection()
                if not selected:
                    return
                
                # if not messagebox.askyesno("确认", "确定删除选中的规则吗?", parent=win):
                #     return

                # 这里直接删，为了顺手，可以不弹二次确认，或者仅在 list 选中时弹
                if not messagebox.askyesno("删除确认", "确定删除选中项?", parent=win):
                    return

                for item in selected:
                     values = tree.item(item, "values")
                     code = values[0]
                     uid = values[4]
                     # 由于 uid 是 'code_idx'，但如果删除了前面的，后面的 idx 会变
                     # 最稳妥的是：倒序删除，或者重新加载。
                     # 我们的界面是单选还是多选？Treeview 默认多选。
                     # 简单处理：只处理第一个
                     try:
                        idx = int(uid.split('_')[1])
                        self.live_strategy.remove_rule(code, idx)
                     except:
                        pass
                     break # 仅删一个，防止索引错乱
                
                load_data()

            def on_voice_tree_select(event):
                selected = tree.selection()
                if not selected: return
                item = selected[0]
                values = tree.item(item, "values")
                target_code = values[0]
                name = values[1]
                stock_code = str(target_code).zfill(6)
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)

            def on_voice_right_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return
                values = tree.item(item_id, "values")
                # values: (time, code, name, content_preview)
                target_code = values[0]
                stock_code = str(target_code).zfill(6)
                # pyperclip.copy(stock_code)
                # toast_message(self, f"stock_code: {stock_code} 已复制")
                self.tree_scroll_to_code(stock_code)
                
            def on_voice_on_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return

                values = tree.item(item_id, "values")
                code = values[0]
                name = values[1]

                stock_code = str(code).zfill(6)
                if stock_code:
                    # logger.info(f'on_voice_on_click stock_code:{stock_code} name:{name}')
                    self.sender.send(stock_code)

            def edit_selected(event=None):
                 selected = tree.selection()
                 if not selected: return
                 item = selected[0]
                 values = tree.item(item, "values")
                 code = values[0]
                 name = values[1]
                 old_val = values[3]
                 uid = values[4]
                 idx = int(uid.split('_')[1])
                 # logger.info(f'on_voice_edit_selected stock_code:{code} name:{name}')
                 
                 current_type = "price_up"
                 monitors = self.live_strategy.get_monitors()
                 if code in monitors:
                     rules = monitors[code]['rules']
                     if idx < len(rules):
                         current_type = rules[idx]['type']

                 # 弹出编辑框 (UI 与 Add 保持一致)
                 edit_win = tk.Toplevel(win)
                 edit_win.title(f"编辑规则 - {name}")
                 edit_win_id = "编辑规则"
                 # w, h = 750, 480
                 # mx, my = self.winfo_pointerx(), self.winfo_pointery()
                 # pos_x, pos_y = max(0, mx - w - 20), max(0, my - h - 20)
                 # edit_win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
                 # edit_win.bind("<Escape>", lambda e: edit_win.destroy())
                 self.load_window_position(edit_win, edit_win_id, default_width=900, default_height=600)

                 main_frame = tk.Frame(edit_win)
                 main_frame.pack(fill="both", expand=True, padx=10, pady=10)
                 
                 left_frame = tk.Frame(main_frame) 
                 left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
                 
                 right_frame = tk.LabelFrame(main_frame, text="参考数据 (点击自动填入)", width=350)
                 right_frame.pack(side="right", fill="both", padx=(10, 0))
                 # right_frame.pack_propagate(False)

                 # --- 左侧 ---
                 curr_price = 0.0
                 curr_change = 0.0
                 row_data = None
                 if code in self.df_all.index:
                    row_data = self.df_all.loc[code]
                    try:
                        curr_price = float(row_data.get('trade', 0))
                        curr_change = float(row_data.get('changepercent', 0))
                    except: pass
                 
                 tk.Label(left_frame, text=f"当前价格: {curr_price}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
                 # tk.Label(left_frame, text=f"当前涨幅: {curr_change:.2f}%", font=("Arial", 10)).pack(pady=5, anchor="w")

                 tk.Label(left_frame, text="规则类型:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))
                 
                 new_type_var = tk.StringVar(value=current_type)
                 val_var = tk.StringVar(value=str(old_val))

                 def on_type_change():
                    # 切换默认值
                    t = new_type_var.get()
                    if t == "change_up":
                         val_var.set(f"{curr_change:.2f}")
                    else:
                         val_var.set(str(curr_price))

                 types = [("价格突破 (Price >=)", "price_up"), 
                          ("价格跌破 (Price <=)", "price_down"),
                          ("涨幅超过 (Change% >=)", "change_up")]
                 
                 for text, val in types:
                     tk.Radiobutton(left_frame, text=text, variable=new_type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)

                 tk.Label(left_frame, text="触发阈值:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))
                 
                 # 阈值输入区域 (包含 +/- 按钮)
                 val_frame = tk.Frame(left_frame)
                 val_frame.pack(fill="x", padx=10, pady=5)

                 e_new = tk.Entry(val_frame, textvariable=val_var, font=("Arial", 12))
                 e_new.pack(side="left", fill="x", expand=True)
                 e_new.focus()
                 e_new.select_range(0, tk.END)
                 
                 def adjust_val_edit(pct):
                    try:
                        current_val = float(val_var.get())
                        t = new_type_var.get()
                        if t == "change_up":
                             new_val = current_val + pct
                        else:
                             new_val = current_val * (1 + pct/100)
                        val_var.set(f"{new_val:.2f}")
                    except ValueError:
                        pass

                 tk.Button(val_frame, text="-1%", width=4, command=lambda: adjust_val_edit(-1)).pack(side="left", padx=2)
                 tk.Button(val_frame, text="+1%", width=4, command=lambda: adjust_val_edit(1)).pack(side="left", padx=2)
                 
                 # --- 右侧参考面板 ---
                 def set_val_callback(val_str, value_type, value):
                    val_var.set(val_str)
                    if value_type == "percent":
                        new_type_var.set("change_up")
                    else:
                        if value > curr_price:
                            new_type_var.set("price_up")
                        else:
                            new_type_var.set("price_down")

                 self._create_monitor_ref_panel(right_frame, row_data, curr_price, set_val_callback)
                 
                 def confirm_edit(event=None):
                     try:
                         val = float(e_new.get())
                         new_type = new_type_var.get()
                         
                         self.live_strategy.update_rule(code, idx, new_type, val)
                         
                         load_data()
                         edit_win.on_close()
                     except ValueError:
                         messagebox.showerror("错误", "无效数字", parent=edit_win)
                 # ESC / 关闭
                 def on_close(event=None):
                     # update_window_position(window_id)
                     self.save_window_position(edit_win, edit_win_id)
                     edit_win.destroy()

                 edit_win.bind("<Escape>", on_close)
                 edit_win.protocol("WM_DELETE_WINDOW", on_close)
                 edit_win.bind("<Return>", confirm_edit)
                 
                 btn_frame = tk.Frame(edit_win)
                 btn_frame.pack(pady=10, side="bottom", fill="x", padx=10)
                 tk.Button(btn_frame, text="保存 (Enter)", command=confirm_edit, bg="#ccff90", height=2).pack(side="left", fill="x", expand=True, padx=5)
                 tk.Button(btn_frame, text="取消 (Esc)", command=on_close, height=2).pack(side="left", fill="x", expand=True, padx=5)

            tk.Button(btn_frame, text="✏️ 修改阈值", command=edit_selected).pack(side="left", padx=10)
            tk.Button(btn_frame, text="🗑️ 删除规则 (Del)", command=delete_selected, fg="red").pack(side="left", padx=10)
            tk.Button(btn_frame, text="刷新列表", command=load_data).pack(side="left", padx=10)
            tree.bind("<Button-1>", on_voice_on_click)
            tree.bind("<Button-3>", on_voice_right_click)
            # 双击编辑
            tree.bind("<Double-1>", lambda e: edit_selected())
            tree.bind("<<TreeviewSelect>>", on_voice_tree_select) 
            # 按 Delete 键删除
            tree.bind("<Delete>", delete_selected)
            # ESC / 关闭
            def on_close(event=None):
                # update_window_position(window_id)
                self.save_window_position(win, window_id)
                win.destroy()

            win.bind("<Escape>", on_close)
            win.protocol("WM_DELETE_WINDOW", on_close)

            # --- 测试真实报警 ---
            def test_selected_monitor():
                selected = tree.selection()
                if not selected:
                    messagebox.showinfo("提示", "请先选择一条规则")
                    return
                
                item = selected[0]
                values = tree.item(item, "values")
                code = values[0]
                name = values[1] 
                rule_desc = values[2]
                val = values[3]
                
                msg = f"{rule_desc} {val} (测试)"
                self.live_strategy.test_alert_specific(code, name, msg)

            tk.Button(top_frame, text="🔊 测试选中报警", command=test_selected_monitor, bg="#fff9c4").pack(side="right", padx=5)
            
        except Exception as e:
            logger.error(f"Voice Monitor Manager Error: {e}")
            messagebox.showerror("错误", f"打开管理窗口失败: {e}")
            
    def copy_code(self,event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            code = tree.item(item_id, "values")[0]  # 假设第一列是 code
            pyperclip.copy(code)
            logger.info(f"已复制: {code}")

    def on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            # 双击表头逻辑
            self.on_tree_header_double_click(event)
        elif region == "cell":
            # 双击行逻辑
            self.on_double_click(event)

    def on_tree_header_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":  # 确认点击在表头
            col = self.tree.identify_column(event.x)
            col_index = int(col.replace("#", "")) - 1
            if 0 <= col_index < len(self.tree["columns"]):
                col_name = self.tree["columns"][col_index]
                self.show_column_menu(col_name,event)  # 弹出列选择菜单

    # def show_column_menu(self, current_col=None):
    #     """弹出列选择窗口，自动自适应行列布局"""
    #     all_cols = list(self.df_all.columns)  # 全部列来源
    #     selected_cols = getattr(self, "display_cols", list(self.tree["columns"]))

    #     win = tk.Toplevel(self)
    #     win.title("选择显示列")
    #     win.geometry("500x400")
    #     win.transient(self)
    #     win.grab_set()

    #     frm = tk.Frame(win)
    #     frm.pack(fill="both", expand=True, padx=10, pady=10)

    #     n = len(all_cols)
    #     max_cols_per_row = 5  # 每行最多 5 个，可改
    #     cols_per_row = min(n, max_cols_per_row)
    #     nrows = math.ceil(n / cols_per_row)

    #     var_map = {}
    #     for i, col in enumerate(all_cols):
    #         var = tk.BooleanVar(value=(col in selected_cols))
    #         var_map[col] = var
    #         r = i // cols_per_row
    #         c = i % cols_per_row
    #         cb = tk.Checkbutton(frm, text=col, variable=var, anchor="w")
    #         cb.grid(row=r, column=c, sticky="w", padx=4, pady=2)

    #     def apply_cols():
    #         new_cols = [col for col, var in var_map.items() if var.get()]
    #         if not new_cols:
    #             tk.messagebox.showwarning("提示", "至少选择一列")
    #             return
    #         self.display_cols = new_cols
    #         self.tree["columns"] = ["code"] + new_cols
    #         for col in self.tree["columns"]:
    #             self.tree.heading(col, text=col, anchor="center")
    #         win.destroy()
    #         self.refresh_tree()

    #     tk.Button(win, text="应用", command=apply_cols).pack(side="bottom", pady=6)

    # def show_column_menu1(self, col):
    #     """表头点击后弹出列替换菜单"""
    #     menu = Menu(self, tearoff=0)

    #     # 显示 df_all 所有列（除了已经在 current_cols 的）
    #     for new_col in self.df_all.columns:
    #         if new_col not in self.current_cols:
    #             menu.add_command(
    #                 label=f"替换 {col} → {new_col}",
    #                 command=lambda nc=new_col, oc=col: self.replace_column(oc, nc)
    #             )

    #     # 弹出菜单
    #     menu.post(self.winfo_pointerx(), self.winfo_pointery())

    # def show_column_menu(self, col):
    #     # 弹出一个 Toplevel 网格窗口显示 df_all 的列，点击即可替换
    #     win = tk.Toplevel(self)
    #     win.transient(self)  # 弹窗在父窗口之上
    #     win.grab_set()
    #     win.title(f"替换列: {col}")

    #     # 过滤掉已经在 current_cols 的列
    #     all_cols = [c for c in self.df_all.columns if c not in self.current_cols or c == col]

    #     # 网格排列参数
    #     cols_per_row = 5  # 每行显示5个按钮，可根据需要调整
    #     btn_width = 15
    #     btn_height = 1

    #     for i, c in enumerate(all_cols):
    #         btn = tk.Button(win,
    #                         text=c,
    #                         width=btn_width,
    #                         height=btn_height,
    #                         command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #         btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)



    # def _show_column_menu(self, col ,event):
    #     # 找到列
    #     # col = self.tree.identify_column(event.x)
    #     # col_idx = int(col.replace('#','')) - 1
    #     # col_name = self.current_cols[col_idx]
    #     def default_filter(c):
    #         if c in self.current_cols:
    #             return False
    #         if any(k in c.lower() for k in ["perc","percent","trade","volume","boll","macd","ma"]):
    #             return True
    #         return False
    #     # 弹窗位置在鼠标指针
    #     x = event.x_root
    #     y = event.y_root

    #     win = tk.Toplevel(self)
    #     win.transient(self)
    #     win.grab_set()
    #     win.title(f"替换列: {col}")
    #     win.geometry(f"+{x}+{y}")

    #     # all_cols = [c for c in self.df_all.columns if c not in self.current_cols or c == col]
    #     all_cols = [c for c in self.df_all.columns if default_filter(c)]
    #     # 自动计算网格布局
    #     n = len(all_cols)
    #     if n <= 10:
    #         cols_per_row = min(n, 5)
    #     else:
    #         cols_per_row = 5

    #     for i, c in enumerate(all_cols):
    #         btn = tk.Button(win, text=c, width=12, command=lambda nc=c, oc=col: [self.replace_column(oc, nc), win.destroy()])
    #         btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)

    def show_column_menu(self, col, event):
        """
        右键弹出选择列菜单。
        col: 当前列
        event: 鼠标事件，用于获取指针位置
        """

        # 如果是 code 列，直接返回
        if col == "code" or col in ("#1", "code"):  # 看你的列 id 定义方式
            return

        if not hasattr(self, "_menu_frame"):
            self._menu_frame = None  # 防止重复弹出

        # 防止多次重复弹出
        if self._menu_frame and self._menu_frame.winfo_exists():
            self._menu_frame.destroy()

        # # 获取当前鼠标指针位置
        # x = event.x_root
        # y = event.y_root


        # 创建顶级 Frame，用于承载按钮
        menu_frame = tk.Toplevel(self)
        menu_frame.overrideredirect(True)  # 去掉标题栏
        # menu_frame.lift()                  # ⬅️ 把窗口置顶
        # menu_frame.attributes("-topmost", True)  # ⬅️ 确保不被遮挡

        self._menu_frame = menu_frame
        # 添加一个搜索框
        search_var = tk.StringVar()
        search_entry = ttk.Entry(menu_frame, textvariable=search_var)
        search_entry.pack(fill="x", padx=4, pady=1)

        # 布局按钮 Frame
        btn_frame = ttk.Frame(menu_frame)
        btn_frame.pack(fill="both", expand=True)

        # 鼠标点击的绝对坐标
        x_root, y_root = event.x_root, event.y_root

        # 等待 Tk 渲染完毕，才能获取实际宽高
        # menu_frame.update_idletasks()
        # menu_frame.update()  
        win_w = 300
        win_h = 300
        # win_w = menu_frame.winfo_width()
        # win_h = menu_frame.winfo_height()

        # 当前窗口宽度（相对坐标用 event.x）
        # window_w = self.winfo_width()

       
        # 屏幕边界保护
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # 默认以鼠标右上角为参考
        x = x_root - win_w
        y = y_root

        # 判断左侧/右侧显示逻辑
        if x < screen_w / 2:  # 左半屏，向右展开
            x = x_root
        else:  # 右半屏，向左展开
            x = x_root - win_w

        # 边界检测
        if x < 0:
            x = 0
        if x + win_w > screen_w:
            x = screen_w - win_w
        if y + win_h > screen_h:
            y = screen_h - win_h
        if y < 0:
            y = 0

        # 设置菜单窗口位置
        menu_frame.geometry(f"+{x}+{y}")

        # logger.info(f"[DEBUG] event.x={event.x}, window_w={window_w}, win_w={win_w}, win_h={win_h}, pos=({x},{y})")

        # 更新 geometry 才能拿到真实宽高
        # menu_frame.update_idletasks()
        # menu_frame.withdraw()  # 先隐藏，避免闪到默认(50,50)

        # x, y = self.get_centered_window_position(win_width, win_height, parent_win=self)
        # menu_frame.geometry(f"{win_width}x{win_height}+{x}+{y}")
        # 再显示出来
        # menu_frame.deiconify()
        # 屏幕大小

        # menu_frame.geometry(f"+{x}+{y}")
        # menu_frame.deiconify()



        # 默认防抖刷新
        # def refresh_buttons():
        #     # 清空旧按钮
        #     for w in btn_frame.winfo_children():
        #         w.destroy()
        #     # 获取搜索过滤
        #     key = search_var.get().lower()
        #     filtered = [c for c in all_cols if key in c.lower()]
        #     # 自动计算行列布局
        #     n = len(filtered)
        #     if n == 0:
        #         return
        #     cols_per_row = min(6, n)  # 每行最多6个
        #     rows = (n + cols_per_row - 1) // cols_per_row
        #     for idx, c in enumerate(filtered):
        #         btn = ttk.Button(btn_frame, text=c,
        #                          command=lambda nc=c: self.replace_column(col, nc))
        #         btn.grid(row=idx // cols_per_row, column=idx % cols_per_row, padx=2, pady=2, sticky="nsew")

        #     # 自动扩展列宽
        #     for i in range(cols_per_row):
        #         btn_frame.columnconfigure(i, weight=1)
        def refresh_buttons():
            for w in btn_frame.winfo_children():
                w.destroy()
            kw = search_var.get().lower()

            # 搜索匹配所有列，但排除已经在 current_cols 的
            if kw:
                filtered = [c for c in self.df_all.columns if kw in c.lower() and c not in self.current_cols]
            else:
                # 默认显示符合默认规则且不在 current_cols
                keywords = ["perc","status","obs","hold","bull","has","lastdu","red","ma"]
                filtered = [c for c in self.df_all.columns if any(k in c.lower() for k in keywords) and c not in self.current_cols]

            n = len(filtered)
            cols_per_row = 5 if n > 5 else n
            for i, c in enumerate(filtered):
                btn = tk.Button(btn_frame, text=c, width=12,
                                command=lambda nc=c, oc=col: [self.replace_column(oc, nc), menu_frame.destroy()])
                btn.grid(row=i // cols_per_row, column=i % cols_per_row, padx=2, pady=2)

        def default_filter(c):
            if c in self.current_cols:
                return False
            # keywords = ["perc","percent","trade","volume","boll","macd","ma"]
            keywords = ["perc","status","obs","hold","bull","has","lastdu","red","ma"]
            return any(k in c.lower() for k in keywords)

        # 防抖机制
        def on_search_changed(*args):
            if hasattr(self, "_search_after_id"):
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(200, refresh_buttons)

        # 获取可选列，排除当前已经显示的
        # all_cols = [c for c in self.df_all.columns if c not in self.current_cols]   
        all_cols = [c for c in self.df_all.columns if default_filter(c)]
        # logger.info(f'allcoulumns : {self.df_all.columns.values}')
        # logger.info(f'all_cols : {all_cols}')
        search_var.trace_add("write", on_search_changed)

        # 初次填充
        refresh_buttons()

        # 点击其他地方关闭菜单
        def close_menu(event=None):
            if menu_frame.winfo_exists():
                menu_frame.destroy()

        menu_frame.bind("<FocusOut>", close_menu)
        menu_frame.focus_force()

    def replace_column(self, old_col, new_col,apply_search=True):
        """替换显示列并刷新表格"""

        if old_col in self.current_cols:
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 🔹 2. 暂时清空列，避免 Invalid column index 残留
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()

            # 🔹 3. 重新配置列
            new_columns = tuple(self.current_cols)
            self.tree["columns"] = new_columns
            self.tree["displaycolumns"] = new_columns
            self.tree.configure(show="headings")

            # # 🔹 4. 重新设置表头和列宽
            # for col in cols:
            #     self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            #     width = 120 if col == "name" else 80
            #     self.tree.column(col, width=width, anchor="center", minwidth=50)

            # # 重新设置 tree 的列集合
            # if "code" not in self.current_cols:
            #     new_columns = ["code"] + self.current_cols
            # else:
            #     new_columns = self.current_cols

            # self.tree.config(columns=new_columns)
            logger.info(f'replace_column get_scaled_value:{self.get_scaled_value()}')
            # 重新设置表头
            # for col in new_columns:
            #     # self.tree.heading(col, text=col, anchor="center", command=lambda _col=col: self.sort_by_column(_col, False))
            #     width = int(getattr(self, "_name_col_width", int(120*self.get_scaled_value()))) if col == "name" else int(60*self.get_scaled_value())
            #     self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            #     self.tree.column(col, width=width, anchor="center", minwidth=int(60*self.get_scaled_value()))

            # co2int = ['ra','ral','fib','fibl','op', 'ratio','ra']
            # co2width = ['boll','kind','red']
            # col_scaled = self.get_scaled_value() 
            # for col in new_columns:
            #     self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            #     if col == "name":
            #         width = int(getattr(self, "_name_col_width", 100*col_scaled))  # 使用记录的 name 宽度
            #         minwidth = int(60*col_scaled)
            #         self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=False)
            #     elif col in co2int:
            #         width = int(60*col_scaled)  # 数字列宽度可小
            #         minwidth = int(22*col_scaled)
            #         self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)
            #     elif col in co2width:
            #         width = int(60*col_scaled)  # 数字列宽度可小
            #         minwidth = int(22*col_scaled)
            #         self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)
            #     else:
            #         width = int(80*col_scaled)
            #         minwidth = int(50*col_scaled)
            #         self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)

            self._setup_tree_columns(self.tree,new_columns, sort_callback=self.sort_by_column, other={})


            # 重新加载数据
            # self.refresh_tree(self.df_all)
            if apply_search:
                self.apply_search()
            else:
                # 重新加载数据
                self.tree.after(100, self.refresh_tree(self.df_all))

    def restore_tree_selection(tree, code: str, col_index: int = 0):
        """
        恢复 Treeview 的选中和焦点位置

        :param tree: ttk.Treeview 对象
        :param code: 要匹配的值
        :param col_index: values 中用于匹配的列索引（默认第 0 列）
        """
        if not code:
            return False

        for iid in tree.get_children():
            values = tree.item(iid, "values")
            if values and len(values) > col_index and values[col_index] == code:
                tree.selection_set(iid)  # 选中
                tree.focus(iid)          # 焦点恢复，保证键盘上下可用
                tree.see(iid)            # 滚动到可见
                return True
        return False


    def reset_tree_columns(self,tree, cols_to_show, sort_func=None):
        """
        安全地重新配置 Treeview 的列定义，防止 TclError: Invalid column index
        参数：
            tree        - Tkinter Treeview 实例
            cols_to_show - 新的列名列表（list/tuple）
            sort_func   - 排序回调函数，形如 lambda col, reverse: ...
        """

        current_cols = list(tree["columns"])
        if current_cols == list(cols_to_show):
            return  # 无需更新

        # logger.info(f"[Tree Reset] old_cols={current_cols}, new_cols={cols_to_show}")

        # 1️⃣ 清空旧列配置
        for col in current_cols:
            try:
                tree.heading(col, text="")
                tree.column(col, width=0)
            except Exception as e:
                logger.info(f"clear col err: {col}, {e}")

        # 2️⃣ 清空列定义，确保内部索引干净
        tree["columns"] = ()
        tree.update_idletasks()

        # 3️⃣ 重新设置列定义
        tree.config(columns=cols_to_show)
        tree.configure(show="headings")
        tree["displaycolumns"] = cols_to_show
        tree.update_idletasks()

        # 4️⃣ 为每个列重新设置 heading / column
        logger.info(f'reset_tree_columns self.scale_factor :{self.scale_factor} col_scaled:{self.get_scaled_value()}')
        # for col in cols_to_show:
        #     if sort_func:
        #         tree.heading(col, text=col, command=lambda _c=col: sort_func(_c, False))
        #     else:
        #         tree.heading(col, text=col)
        #     width = int(80*self.get_scaled_value()) if col == "name" else int(60*self.get_scaled_value())
        #         width = int(60*col_scaled)  # 数字列宽度可小
        #         minwidth = int(22*col_scaled)
        #         tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)
        #     else:
        #         width = int(80*col_scaled)
        #         minwidth = int(50*col_scaled)
        #         tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)

        self._setup_tree_columns(tree,cols_to_show, sort_callback=sort_func, other={})


        # logger.info(f"[Tree Reset] applied cols={list(tree['columns'])}")


    def tree_scroll_to_code(self, code):
        """在 Treeview 中自动定位到指定 code 行"""
        if not code or not (code.isdigit() and len(code) == 6):
            return

        try:
            # --- 2. 清空原有选择（可选） ---
            # self.tree.selection_remove(self.tree.selection())

            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                # values[0] 通常是 code，如果你的 code 列不是第一列可以传入 index 参数
                if values and str(values[0]) == str(code):
                    self.tree.selection_set(iid)   # 设置选中
                    self.tree.focus(iid)           # 键盘焦点
                    self.tree.see(iid)             # 自动滚动，使其可见
                    return True
            toast_message(self, f"{code} is not Found Main")
        except Exception as e:
            logger.info(f"[tree_scroll_to_code] Error: {e}")
            return False

        return False  # 未找到


    def on_tree_click_for_tooltip(self, event,stock_code=None):
        """处理树视图点击事件，延迟显示提示框"""
        logger.debug(f"[Tooltip] 点击事件触发: x={event.x}, y={event.y}")

        # 取消之前的定时器
        if getattr(self, '_tooltip_timer', None):
            try:
                self.after_cancel(self._tooltip_timer)
            except Exception:
                pass
            self._tooltip_timer = None

        # 销毁之前的提示框
        if getattr(self, '_current_tooltip', None):
            try:
                self._current_tooltip.destroy()
            except Exception:
                pass
            self._current_tooltip = None

        if stock_code is None:
            # 获取点击的行
            item = self.tree.identify_row(event.y)
            if not item:
                logger.debug("[Tooltip] 未点击到有效行")
                return

            # 获取股票代码
            values = self.tree.item(item, 'values')
            if not values:
                logger.debug("[Tooltip] 行没有数据")
                return
            code = str(values[0])  # code在第一列
        else:
            code = stock_code
        # x_root, y_root = event.x_root, event.y_root  # 保存坐标
        logger.debug(f"[Tooltip] 获取到代码: {code}, 设置0.2秒定时器")

        # 设置0.2秒延迟定时器
        self._tooltip_timer = self.after(200, lambda e=event:self.show_stock_tooltip(code, e))


    def show_stock_tooltip(self, code, event):
        """显示股票信息提示框，柔和背景 + 分色文字"""
        logger.debug(f"[Tooltip] show_stock_tooltip 被调用: code={code}")

        # 清理定时器引用
        self._tooltip_timer = None

        # 从 df_all 获取股票数据
        if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
            logger.debug("[Tooltip] df_all 为空或不存在")
            return

        # 清理代码前缀
        code_clean = code.strip()
        for icon in ['🔴', '🟢', '📊', '⚠️']:
            code_clean = code_clean.replace(icon, '').strip()

        if code_clean not in self.df_all.index:
            logger.debug(f"[Tooltip] 代码 {code_clean} 不在 df_all.index 中")
            return

        stock_data = self.df_all.loc[code_clean]

        logger.debug(f"[Tooltip] 找到股票数据，准备创建提示框")

        # 创建 tooltip
        tooltip = tk.Toplevel(self)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+15}+{event.y_root+15}")
        tooltip.configure(bg='#FFF8E7')
        self._current_tooltip = tooltip

        # 获取多行文本和对应颜色
        lines, colors = self._format_stock_info(stock_data)

        # 使用 Text 控件显示
        text_widget = tk.Text(
            tooltip,
            bg='#FFF8E7',
            bd=0,
            padx=8,
            pady=6,
            height=len(lines),
            width=max(len(line) for line in lines),
            font=("Microsoft YaHei", 9)  # 默认文字字体
        )
        text_widget.pack()

        for i, (line, color) in enumerate(zip(lines, colors)):
            tag_name = f"line_{i}"          # 每行一个唯一 tag
            text_widget.insert(tk.END, line + "\n", tag_name)
            text_widget.tag_config(tag_name, foreground=color, font=("Microsoft YaHei", 9))

            # 检查 signal 行，单独设置图标颜色和大小
            if "signal:" in line:
                # 找到图标位置
                icon_index = line.find("👍")
                if icon_index == -1:
                    icon_index = line.find("🚀")
                if icon_index == -1:
                    icon_index = line.find("☀️")

                if icon_index != -1:
                    start = f"{i+1}.{icon_index}"       # 第 i+1 行，第 icon_index 个字符
                    end = f"{i+1}.{icon_index+2}"       # 图标占 1-2 个字符
                    text_widget.tag_add(f"icon_{i}", start, end)
                    text_widget.tag_config(f"icon_{i}", foreground="#FF6600", font=("Microsoft YaHei", 12, "bold"))

        text_widget.config(state=tk.DISABLED)

        # 计算显示位置
        x = event.x_root + 15
        y = event.y_root + 15
        tooltip.update_idletasks()  # 确保 Text 完全渲染
        width = text_widget.winfo_reqwidth()
        height = text_widget.winfo_reqheight()
        tooltip.geometry(f"{width}x{height}+{x}+{y}")

        # 保存引用
        self._current_tooltip = tooltip

        logger.debug(f"[Tooltip] 提示框已创建并显示在 ({event.x_root+15}, {event.y_root+15})")



    def _format_stock_info(self, stock_data):
        """格式化股票信息为显示文本，并返回颜色标签"""
        code = stock_data.name
        name = stock_data.get('name', '未知')

        close = stock_data.get('close', 0)
        low = stock_data.get('low', 0)
        high = stock_data.get('high', 0)
        boll = stock_data.get('boll', 0)
        upper = stock_data.get('upper', 0)
        upper1 = stock_data.get('upper1', 0)  # 假设有 upper1
        upper2 = stock_data.get('upper2', 0)  # 假设有 upper1
        high4 = stock_data.get('high4', 0)
        ma5d = stock_data.get('ma5d', 0)
        ma10d = stock_data.get('ma10d', 0)

        lastl1d = stock_data.get('lastl1d', 0)
        lastl2d = stock_data.get('lastl2d', 0)
        lasth1d = stock_data.get('lasth1d', 0)
        lasth2d = stock_data.get('lasth2d', 0)

        # 默认无信号
        signal_icon = ""

        # 条件判断顺序很重要，从弱到强
        try:
            if close > ma5d and low < ma10d:
                signal_icon = "👍"  # 反抽
                if close > high4:
                    signal_icon = "🚀"  # 突破高点
                    if close > upper1:
                        signal_icon = "☀️"  # 超越上轨
            elif close >= lasth1d > lasth2d:
                signal_icon = "🚀"  # 突破高点
                if close > upper2:
                    signal_icon = "☀️"  # 超越上轨
        except Exception as e:
            if close > ma5d and low < ma5d:
                signal_icon = "👍"  # 反抽
                if close > high4:
                    signal_icon = "🚀"  # 突破高点
                    if close > upper1:
                        signal_icon = "☀️"  # 超越上轨
            elif close >= lasth1d > lasth2d:
                signal_icon = "🚀"  # 突破高点
                if close > upper2:
                    signal_icon = "☀️"  # 超越上轨
        finally:
            pass

        # 计算突破和强势
        breakthrough = "✓" if high > upper else "✗"
        strength = "✓" if (lastl1d > lastl2d and lasth1d > lasth2d) else "✗"

        lines = [
            f"【{code}】{name}:{close}",
            "─" * 20,
            f"📊 换手率: {stock_data.get('ratio', 'N/A')}",
            f"📊 成交量: {stock_data.get('volume', 'N/A')}",
            f"🔴 连阳: {stock_data.get('red', 'N/A')}",
            f"📈 突破布林: {boll}",
            f"  signal: {signal_icon} (low<10 & C>5)",
            f"  Upper:  {stock_data.get('upper', 'N/A')}",
            f"  Lower:  {stock_data.get('lower', 'N/A')}",
            f"🚀 突破: {breakthrough} (high > upper)",
            f"💪 强势: {strength} (L1>L2 & H1>H2)",
        ]

        # 定义每行颜色
        colors = [
            'blue',        # 股票代码
            'black',       # 分割线
            'red',       # 换手率
            'green',       # 成交量
            'red',         # 连阳
            'orange',      # 布林带标题
            'orange',      # Upper
            'orange',      # Middle
            'orange',      # Lower
            'purple',      # 突破
            'purple',      # 强势
        ]

        return lines, colors


    def toggle_feature_colors(self):
        """
        切换特征颜色显示状态（响应win_var变化）
        实时更新颜色显示并刷新界面
        """


        if not hasattr(self, 'feature_marker') or not hasattr(self, 'win_var'):
            return
        
        try:
            # 获取win_var当前状态
            enable_colors = not self.win_var.get()
            
            # 更新feature_marker的颜色显示状态
            self.feature_marker.set_enable_colors(enable_colors)
            logger.debug(f"self.feature_marker : {hasattr(self, 'feature_marker')}")
            # 立即刷新显示以应用新的颜色状态
            self.refresh_tree()
            
            logger.info(f"✅ 特征颜色显示已{'开启' if enable_colors else '关闭'}")
        except Exception as e:
            logger.error(f"❌ 切换特征颜色失败: {e}")

    def refresh_tree(self, df=None):
        """刷新 TreeView，保证列和数据严格对齐。"""
        start_time = time.time()
        
        if df is None:
            df = self.current_df.copy()

        # 若 df 为空，更新状态并返回
        if df is None or df.empty:
            self.current_df = pd.DataFrame() if df is None else df
            
            # ✅ 使用增量更新清空
            if self._use_incremental_update and hasattr(self, 'tree_updater'):
                self.tree_updater.update(pd.DataFrame(), force_full=True)
            else:
                # 传统方式清空
                for iid in self.tree.get_children():
                    self.tree.delete(iid)
            
            self.update_status()
            return

        df = df.copy()

        # 确保 code 列存在并为字符串（便于显示）
        if 'code' not in df.columns:
            df.insert(0, 'code', df.index.astype(str))

        # 要显示的列顺序
        cols_to_show = [c for c in self.current_cols if c in df.columns]

        # ✅ 使用增量更新机制
        if self._use_incremental_update and hasattr(self, 'tree_updater'):
            try:
                # 更新列配置（如果列发生变化）
                if self.tree_updater.columns != cols_to_show:
                    self.tree_updater.columns = cols_to_show
                    logger.info(f"[TreeUpdater] 列配置已更新: {len(cols_to_show)}列")
                
                # ✅ 检测是否只是排序（数据相同但顺序不同）
                # 如果是排序操作，强制全量刷新以确保顺序正确
                force_full = False
                if hasattr(self, '_last_df_codes'):
                    current_codes = df['code'].astype(str).tolist()
                    # 如果code集合相同但顺序不同，说明是排序操作
                    if set(current_codes) == set(self._last_df_codes) and current_codes != self._last_df_codes:
                        force_full = True
                        logger.debug(f"[TreeUpdater] 检测到排序操作，执行全量刷新")
                
                # 保存当前的code列表用于下次比较
                self._last_df_codes = df['code'].astype(str).tolist()
                
                # 执行增量更新
                added, updated, deleted = self.tree_updater.update(df[cols_to_show], force_full=force_full)
                
                # 恢复选中状态
                if self.select_code:
                    self.tree_updater.restore_selection(self.select_code)
                
                # 记录性能
                duration = time.time() - start_time
                self.perf_monitor.record(duration)
                
                # 每10次更新打印一次性能报告
                stats = self.perf_monitor.get_stats()
                if stats.get("count", 0) % 10 == 0:
                    logger.info(self.perf_monitor.report())
                
            except Exception as e:
                logger.error(f"[TreeUpdater] 增量更新失败,回退到全量刷新: {e}")
                # 回退到传统方式
                self._refresh_tree_traditional(df, cols_to_show)
        else:
            # 使用传统方式刷新
            self._refresh_tree_traditional(df, cols_to_show)

        # ✅ 双击表头绑定 - 需要保留以支持列组合管理器
        # 这个绑定不会干扰排序,因为on_tree_double_click会区分heading和cell区域
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        # 保存完整数据
        self.current_df = df
        
        # 调整列宽
        self.adjust_column_widths()
        
        # 更新状态栏
        self.update_status()
    
    def _refresh_tree_traditional(self, df, cols_to_show):
        """传统的全量刷新方式(作为增量更新的备用方案)"""
        # 清空所有行
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        
        # 重新插入所有行
        for idx, row in df.iterrows():
            values = [row.get(col, "") for col in cols_to_show]
            
            # ✅ 如果启用了特征标记,在name列前添加图标
            if self._use_feature_marking and hasattr(self, 'feature_marker'):
                try:
                    # 准备行数据用于特征检测
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    
                    # 获取图标
                    icon = self.feature_marker.get_icon_for_row(row_data)
                    if icon:
                        # 在name列前添加图标(假设name在第2列,index 1)
                        name_idx = cols_to_show.index('name') if 'name' in cols_to_show else -1
                        if name_idx >= 0 and name_idx < len(values):
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception as e:
                    logger.debug(f"添加图标失败: {e}")
            
            # 插入行
            iid = self.tree.insert("", "end", values=values)
            
            # ✅ 应用颜色标记
            if self._use_feature_marking and hasattr(self, 'feature_marker'):
                try:
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    # 获取并应用标签(不添加图标,因为已经在values中添加了)
                    tags = self.feature_marker.get_tags_for_row(row_data)
                    if tags:
                        self.tree.item(iid, tags=tuple(tags))
                except Exception as e:
                    logger.debug(f"应用颜色标记失败: {e}")
        
        # 恢复选中状态
        if self.select_code:
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                if values and values[0] == self.select_code:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break


    def adjust_column_widths(self):
        """根据当前 self.current_df 和 tree 的列调整列宽（只作用在 display 的列）"""
        # cols = list(self.tree["displaycolumns"]) if self.tree["displaycolumns"] else list(self.tree["columns"])
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return  # 已销毁，直接返回
        cols = list(self.tree["columns"])

        # 遍历显示列并设置合适宽度
        for col in cols:
            # 跳过不存在于 df 的列
            if col not in self.current_df.columns:
                # 仍要确保列有最小宽度
                self.tree.column(col, width=int(50*self.get_scaled_value()))
                continue
            # # 计算列中最大字符串长度
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            width = int(min(max(max_len * 8, int(60*self.get_scaled_value())) , 300))  # 经验值：每字符约8像素，可调整

            # try:
            #     max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            # except Exception:
            #     max_len = len(col)

            # # 使用 self.get_scaled_value() 代替 DPI 缩放比例
            # scale = self.get_scaled_value()  # 返回 self.scale_factor - offset
            # base_char_width = 8  # 每字符经验值
            # width = int(max(max_len * base_char_width * scale, 60))  # 最小宽度 60
            # width = min(width, 300)  # 最大宽度 300

            if col == 'name':
                # width = int(width * 2)
                # width = int(width * 1.5 * self.get_scaled_value())
                width = int(getattr(self, "_name_col_width", 80*self.scale_factor))
                # logger.info(f'col width: {width}')
                # logger.info(f'col : {col} width: {width}')
            self.tree.column(col, width=int(width))
        logger.debug(f'adjust_column_widths done :{len(cols)}')
    # ----------------- 排序 ----------------- #
    def sort_by_column(self, col, reverse):
        if col not in self.current_df.columns:
            return
        self.select_code = None
        self.sortby_col =  col
        self.sortby_col_ascend = not reverse
        logger.debug(f'self.sortby_col_ascend: {self.sortby_col_ascend}')
        if col in ['code']:
            # df_sorted = self.current_df.reset_index().sort_values(
            #     by=col, key=lambda s: s.astype(str), ascending=not reverse)
            df_sorted = self.current_df.reset_index(drop=True).sort_values(
                by=col, key=lambda s: s.astype(str), ascending=not reverse)

        elif pd.api.types.is_numeric_dtype(self.current_df[col]):
            df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        else:
            df_sorted = self.current_df.sort_values(by=col, key=lambda s: s.astype(str), ascending=not reverse)

        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))
        self.tree.yview_moveto(0)

    # import re

    def process_query_test(query: str):
        """
        提取 query 中 `and (...)` 的部分，剔除后再拼接回去
        """

        # 1️⃣ 提取所有 `and (...)` 的括号条件
        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2️⃣ 剔除原始 query 里的这些条件
        new_query = query
        for bracket in bracket_patterns:
            new_query = new_query.replace(f'and {bracket}', '')

        # 3️⃣ 保留剔除的括号条件（后面可单独处理，比如分类条件）
        removed_conditions = bracket_patterns

        # 4️⃣ 示例：把条件拼接回去
        if removed_conditions:
            final_query = f"{new_query} and " + " and ".join(removed_conditions)
        else:
            final_query = new_query

        return new_query.strip(), removed_conditions, final_query.strip()


        # 🔍 测试
        query = '(lastp1d > ma51d  and lasth1d > lasth2d  > lasth3d and lastl1d > lastl2d > lastl3d and (high > high4 or high > upper)) and (category.str.contains("固态电池"))'

        new_query, removed, final_query = process_query(query)

        logger.info(f"去掉后的 query: {new_query}")
        logger.info(f"提取出的条件: {removed}")
        logger.info(f"拼接后的 final_query:{final_query}")

    def _on_search_var_change(self, *_):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        if not val1 and not val2:
            return

        # 构建原始查询语句
        if val1 and val2:
            query = f"({val1}) and ({val2})"
        elif val1:
            query = val1
        else:
            query = val2

        # 如果新值和上次一样，就不触发
        if hasattr(self, "_last_value") and self._last_value == query:
            return
        self._last_value = query

        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(3000, self.apply_search)  # 3000ms后执行

    # def sync_history_from_QM(self,search_history1=None,search_history2=None):
    #     if search_history1:
    #         self.search_history1 = [r["query"] for r in search_history1]
    #     if search_history2:
    #         self.search_history2 = [r["query"] for r in search_history2]

    def sync_history_from_QM(self, search_history1=None, search_history2=None, search_history3=None):
        self.query_manager.clear_hits()

        if search_history1 is not None:
            if search_history1 is self.query_manager.history2:
                logger.info("[警告] sync_history_from_QM 收到错误引用（history2）→ 覆盖 history1 被阻止")
                return
            self.search_history1 = [r["query"] for r in list(search_history1)]

        if search_history2 is not None:
            if search_history2 is self.query_manager.history1:
                logger.info("[警告] sync_history_from_QM 收到错误引用（history1）→ 覆盖 history2 被阻止")
                return
            self.search_history2 = [r["query"] for r in list(search_history2)]
        if search_history3 is not None:
            if search_history3 is self.query_manager.history1 or search_history3 is self.query_manager.history2:
                logger.info("[警告] sync_history_from_QM 收到错误引用（history1/2）→ 覆盖 history3 被阻止")
                return

            # ✅ 如果 self.search_history3 已存在，就直接更新原对象
            if hasattr(self, "search_history3") and isinstance(self.search_history3, list):
                self.search_history3.clear()
                self.search_history3.extend([r["query"] for r in list(search_history3)])
            else:
                # 第一次初始化才创建
                self.search_history3 = [r["query"] for r in list(search_history3)]
            # ✅ 同步 combobox
            # if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
            # ✅ 如果 kline_monitor 存在，就刷新 ComboBox
            if hasattr(self, "kline_monitor") and getattr(self.kline_monitor, "winfo_exists", lambda: False)():
                try:
                    self.kline_monitor.refresh_search_combo3()
                except Exception as e:
                    logger.info(f"[警告] 刷新 KLineMonitor ComboBox 失败: {e}")

    def sync_history(self, val, search_history, combo, history_attr, current_key):


        # ⚙️ 检查是否是刚编辑过的 query
        edited_pair = getattr(self.query_manager, "_just_edited_query", None)
        if edited_pair:
            old_query, new_query = edited_pair
            # 清除标记，防止影响下次
            self.query_manager._just_edited_query = None
            if val == new_query and old_query in search_history:
                # 🔹 替换旧值而非新增
                search_history.remove(old_query)
                if new_query not in search_history:
                    search_history.insert(0, new_query)
            elif val == old_query:
                # 若 val 仍是旧的，直接跳过同步
                return
        else:

            if val in search_history:
                search_history.remove(val)
            search_history.insert(0, val)
            # if len(search_history) > 20:
            #     search_history[:] = search_history[:20]
        combo['values'] = search_history
        try:
            combo.set(val)
        except Exception:
            pass

        # ----------------------
        # ⚠️ 增量同步到 QueryHistoryManager
        # ----------------------
        history = getattr(self.query_manager, history_attr)
        existing_queries = {r["query"]: r for r in history}
        # logger.info(f'val: {val} {val in existing_queries}')
        new_history = []
        for q in search_history:
            if q in existing_queries:
                # 保留原来的 note / starred
                new_history.append(existing_queries[q])
            else:
                # 新建
                # if hasattr(self, "_last_value") and self._last_value.find(q) >=0:
                #     continue
                new_history.append({"query": q, "starred":  0, "note": ""})

        setattr(self.query_manager, history_attr, new_history)

        if self.query_manager.current_key == current_key:
            self.query_manager.current_history = new_history
            self.query_manager.refresh_tree()

        # # --- 2️⃣ 如果编辑器已显示，直接写入 entry_query ---
        # if self.query_manager.editor_frame.winfo_ismapped():
        #     self.query_manager.entry_query.delete(0, tk.END)
        #     self.query_manager.entry_query.insert(0, self._Categoryresult)
        #     return

    def update_category_result(self, df_filtered):
        """统计概念异动，在主窗口上方显示摘要"""
        try:
            if df_filtered is None or df_filtered.empty:
                logger.info("[update_category_result] df_filtered is empty")
                return

            # --- 统计当前概念 ---
            cat_dict = {}  # {concept: [codes]}
            all_cats = []  # 用于统计出现次数
            topN = df_filtered.head(50)

            for code, row in topN.iterrows():
                if isinstance(row.get("category"), str):
                    cats = [c.strip() for c in row["category"].replace("；", ";").replace("+", ";").split(";") if c.strip()]
                    for ca in cats:
                        # 过滤泛概念
                        if is_generic_concept(ca):
                            continue
                        all_cats.append(ca)
                        # 添加其他信息到元组里，比如 (code, name, percent, volume)
                        percent = row.get("percent")
                        if pd.isna(percent) or percent == 0:
                            percent = row.get("per1d", 0)
                        cat_dict.setdefault(ca, []).append((
                            code,
                            row.get("name", ""),
                            # row.get("percent", 0) or row.get("per1d", 0),
                            percent,
                            row.get("volume", 0)
                            # 如果还有其他列，可以继续加: row.get("其他列")
                        ))

            if not all_cats:
                logger.info("[update_category_result] No concepts found in filtered data")
                return

            # --- 统计出现次数 ---
            counter = Counter(all_cats)
            top5 = OrderedDict(counter.most_common(5))

            display_text = "  ".join([f"{k}:{v}" for k, v in top5.items()])
            # logger.info(f'display_text : {display_text}  list(top5.keys()) : { list(top5.keys()) }')
            # 取前5个类别
            # current_categories = set(top5.keys())
            current_categories =  list(top5.keys())  #保持顺序

            # 获取 Tk 默认字体
            # default_font = tkfont.nametofont("TkDefaultFont").copy()
            # default_font.configure(weight="bold")  # 只加粗，不修改字号或字体
            # font=("微软雅黑", 10, "bold"),

            # --- 标签初始化 ---
            if not hasattr(self, "lbl_category_result"):
                self.lbl_category_result = tk.Label(
                    self,
                    text="",
                    font=self.default_font_bold,
                    fg="green",
                    bg="#f7f7f7",
                    anchor="w",
                    justify="left",
                    cursor="hand2"
                )
                self.lbl_category_result.pack(fill="x", padx=8, pady=(2, 4), before=self.children[list(self.children.keys())[0]])
                self.lbl_category_result.bind("<Button-1>", lambda e: self.show_concept_detail_window())
                self._last_categories = current_categories
                self._last_cat_dict = cat_dict
                self.lbl_category_result.config(text=f"当前概念：{display_text}")
                return

            # --- 对比上次结果 ---
            old_categories = getattr(self, "_last_categories", set())
            # added = current_categories - old_categories
            # removed = old_categories - current_categories
            added = [c for c in current_categories if c not in old_categories]
            removed = [c for c in old_categories if c not in current_categories]


            if added or removed:
                diff_texts = []
                if added:
                    diff_texts.append(f"🆕 新增：{'、'.join(sorted(added))}")
                if removed:
                    diff_texts.append(f"❌ 消失：{'、'.join(sorted(removed))}")
                diff_summary = "  ".join(diff_texts)
                self.lbl_category_result.config(text=f"概念异动：{diff_summary}", fg="red")

                def flash_label(count=0):
                    if count >= 6:
                        self.lbl_category_result.config(fg="red")
                        return
                    cur_color = self.lbl_category_result.cget("fg")
                    new_color = "green" if cur_color == "red" else "red"
                    self.lbl_category_result.config(fg=new_color)
                    self.lbl_category_result.after(300, flash_label, count + 1)

                flash_label()
            else:
                self.lbl_category_result.config(text=f"当前概念：{display_text}", fg="green")

            # 保存状态
            self._last_categories = current_categories
            self._last_cat_dict = cat_dict

        except Exception as e:
            logger.error(f"[update_category_result] 更新概念信息出错: {e}", exc_info=True)

    def on_code_click(self, code):
        """点击异动窗口中的股票代码"""
        if code != self.select_code:
            self.select_code = code
            logger.info(f"select_code: {code}")
            # ✅ 可改为打开详情逻辑，比如：
            # if hasattr(self, "show_stock_detail"):
            #     self.show_stock_detail(code)
            self.sender.send(code)

    # --- 类内部方法 ---
    def show_concept_detail_window(self):
        """弹出详细概念异动窗口（复用+自动刷新+键盘/滚轮+高亮）"""
        if not hasattr(self, "_last_categories"):
            return
        # code, name = self.get_stock_code_none()
        self.plot_following_concepts_pg()
        # --- 检查窗口是否已存在 ---
        if getattr(self, "_concept_win", None):
            try:
                if self._concept_win.winfo_exists():
                    win = self._concept_win
                    win.deiconify()
                    win.lift()
                    # 仅清理旧内容区，不销毁窗口结构
                    for widget in win._content_frame.winfo_children():
                        widget.destroy()
                    self.update_concept_detail_content()
                    return
                else:
                    self._concept_win = None
            except Exception:
                self._concept_win = None

        win = tk.Toplevel(self)
        self._concept_win = win
        win.title("概念异动详情")
        self.load_window_position(win, "detail_window", default_width=220, default_height=400)
        #将 win 设为 父窗口的临时窗口
        # 在 Windows 上表现为 没有单独任务栏图标
        # 常用于 工具窗口 / 弹窗
        # win.transient(self)

        # --- 主Frame + Canvas + 滚动 ---
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas)

        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- 鼠标滚轮 ---
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def unbind_mousewheel(event=None):
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except Exception:
                pass

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)

        # --- 保存引用 ---
        win._canvas = canvas
        win._content_frame = scroll_frame
        win._unbind_mousewheel = unbind_mousewheel

        # --- 键盘滚动与高亮初始化 ---
        self._label_widgets = []
        self._selected_index = 0

        # 键盘事件只在滚动区域有效
        canvas.bind("<Up>", self._on_key)
        canvas.bind("<Down>", self._on_key)
        canvas.bind("<Prior>", self._on_key)
        canvas.bind("<Next>", self._on_key)
        # 获取焦点
        canvas.focus_set()
        # --- 关闭窗口 ---
        def on_close_detail_window():
            self.save_window_position(win, "detail_window")
            unbind_mousewheel()
            try:
                win.grab_release()
            except:
                pass
            win.destroy()
            self._concept_win = None

        win.protocol("WM_DELETE_WINDOW", on_close_detail_window)
        # --- 初始内容 ---
        self.update_concept_detail_content()
        def _keep_focus(event):
            """防止焦点丢失"""
            if self._concept_win._content_frame and self._concept_win._content_frame.winfo_exists():
                self._concept_win._content_frame.focus_set()

        # 在初始化中绑定一次
        canvas.bind("<FocusOut>", _keep_focus)
        # win.bind("<FocusIn>", lambda e, w=win: self.on_monitor_window_focus(w))
        # 初始化时绑定
        win.bind("<Button-1>", lambda e, w=win: self.on_monitor_window_focus(w))

    def update_concept_detail_content(self, limit=5):
        """刷新概念详情窗口内容（后台可调用）"""
        if not hasattr(self, "_concept_win") or not self._concept_win:
            return
        if not self._concept_win.winfo_exists():
            self._concept_win = None
            return

        scroll_frame = self._concept_win._content_frame
        canvas = self._concept_win._canvas

        # 清空旧内容
        for widget in scroll_frame.winfo_children():
            widget.destroy()
        self._label_widgets = []

        # --- 数据逻辑 ---
        current_categories = getattr(self, "_last_categories", [])
        prev_categories = getattr(self, "_prev_categories", [])
        cat_dict = getattr(self, "_last_cat_dict", {})

        added = [c for c in current_categories if c not in prev_categories]
        removed = [c for c in prev_categories if c not in current_categories]
        # default_font = tkfont.nametofont("TkDefaultFont").copy()
        # default_font.configure(weight="bold")  # 只加粗，不修改字号或字体
        # === 有新增或消失 ===
        if added or removed:
            if added:
                tk.Label(scroll_frame, text="🆕 新增概念", font=self.default_font, fg="green").pack(anchor="w", pady=(0, 5))
                for c in added:
                    tk.Label(scroll_frame, text=c, fg="blue", font=self.default_font_bold).pack(anchor="w", padx=5)
                    stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)[:limit]  # 只取前 limit
                    for code, name, percent, volume in stocks:
                        lbl = tk.Label(scroll_frame, text=f"  {code} {name} {percent:.2f}% {volume}",
                                       fg="black", cursor="hand2", anchor="w", takefocus=True)    # ⭐ 必须
                        lbl.pack(anchor="w", padx=6)
                        lbl._code = code
                        lbl._concept = c
                        idx = len(self._label_widgets)
                        lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                        lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                        # lbl.bind("<Up>", self._on_key)
                        # lbl.bind("<Down>", self._on_key)
                        # lbl.bind("<Return>", self._on_key)
                        lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))
                        self._label_widgets.append(lbl)

            if removed:
                tk.Label(scroll_frame, text="❌ 消失概念", font=self.default_font_bold, fg="red").pack(anchor="w", pady=(10, 5))
                for c in removed:
                    tk.Label(scroll_frame, text=c, fg="gray", font=self.default_font_bold).pack(anchor="w", padx=5)

        else:
            tk.Label(scroll_frame, text="📊 当前前5概念", font=self.default_font_bold, fg="blue").pack(anchor="w", pady=(0, 5))
            for c in current_categories[:5]:
                tk.Label(scroll_frame, text=c, fg="black", font=self.default_font_bold).pack(anchor="w", padx=5)
                stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)[:limit]  # 只取前 limit
                for code, name, percent, volume in stocks:
                    lbl = tk.Label(scroll_frame, text=f"  {code} {name} {percent:.2f}% {volume}",
                                   fg="gray", cursor="hand2", anchor="w",takefocus=True)    # ⭐ 必须
                    lbl.pack(anchor="w", padx=6)
                    lbl._code = code
                    lbl._concept = c
                    idx = len(self._label_widgets)
                    lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                    lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                    # lbl.bind("<Up>", self._on_key)
                    # lbl.bind("<Down>", self._on_key)
                    # lbl.bind("<Return>", self._on_key)
                    lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))
                    self._label_widgets.append(lbl)

        # --- 默认选中第一条 ---
        if self._label_widgets:
            self._selected_index = 0
            self._label_widgets[0].configure(bg="lightblue")

        # --- 滚动到顶部 ---
        canvas.yview_moveto(0)

        # --- 更新状态 ---
        self._prev_categories = list(current_categories)



    # --- 类内部方法：选择和点击 ---
    def _update_selection(self, idx):
        """更新选中高亮并滚动"""
        if not hasattr(self, "_concept_win") or not self._concept_win:
            return
        canvas = self._concept_win._canvas
        scroll_frame = self._concept_win._content_frame

        for lbl in self._label_widgets:
            lbl.configure(bg=self._concept_win.cget("bg"))
        if 0 <= idx < len(self._label_widgets):
            lbl = self._label_widgets[idx]
            lbl.configure(bg="lightblue")
            self._selected_index = idx

            # 滚动 Canvas 使当前 Label 可见
            canvas.update_idletasks()
            scroll_frame.update_idletasks()
            lbl_top = lbl.winfo_y()
            lbl_bottom = lbl_top + lbl.winfo_height()
            view_top = canvas.canvasy(0)
            view_bottom = view_top + canvas.winfo_height()
            if lbl_top < view_top:
                canvas.yview_moveto(lbl_top / max(1, scroll_frame.winfo_height()))
            elif lbl_bottom > view_bottom:
                canvas.yview_moveto((lbl_bottom - canvas.winfo_height()) / max(1, scroll_frame.winfo_height()))


    def _on_label_click(self, code, idx):
        """点击标签事件"""
        self._update_selection(idx)
        self.on_code_click(code)
        # 确保键盘事件仍绑定有效

        if hasattr(self._concept_win, "_canvas"):
            canvas = self._concept_win._canvas
            yview = canvas.yview()  # 保存当前滚动条位置
            self._concept_win._canvas.focus_set()
            canvas.yview_moveto(yview[0])  # 恢复原位置

    def on_right_click_search_var2(self,event):
        try:
            # 获取剪贴板内容
            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        # 插入到光标位置
        # event.widget.insert(tk.INSERT, clipboard_text)
        # 先清空再黏贴
        if clipboard_text.isdigit() and len(clipboard_text) == 6:
            clipboard_text = f'index.str.contains("^{clipboard_text}")'
            # clipboard_text = query_str = f'index.str.contains("^{clipboard_text}")'
        else:
            # match = re.search(r'[\u4e00-\u9fa5A-Za-z0-9（）\(\)\-]+', clipboard_text)
            # pattern = r'[\u4e00-\u9fa5]+[A-Za-z0-9\-\(\)（）]*'
            allowed = r'\-\(\)'
            pattern = rf'[\u4e00-\u9fa5]+[A-Za-z0-9{allowed}（）]*'
            matches = re.findall(r'[\u4e00-\u9fa5]+[A-Za-z0-9\-\(\)（）]*', clipboard_text)
            if matches:
                clipboard_text = f'category.str.contains("^{matches[0]}")'

        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)
        # self.on_test_click()


    def _on_label_on_code_click(self, code,idx):
        self._update_selection_top10(idx)
        """点击异动窗口中的股票代码"""
        self.select_code = code

        # logger.info(f"select_code: {code}")
        # ✅ 可改为打开详情逻辑，比如：
        self.sender.send(code)
        if hasattr(self._concept_top10_win, "_canvas_top10"):
            canvas = self._concept_top10_win._canvas_top10
            yview = canvas.yview()  # 保存当前滚动条位置
            self._concept_top10_win._canvas_top10.focus_set()
            canvas.yview_moveto(yview[0])  # 恢复原位置


    def _on_key_top10(self, event):
        """键盘上下/分页滚动（仅Top10窗口用）"""
        if not hasattr(self, "_top10_label_widgets") or not self._top10_label_widgets:
            return

        idx = getattr(self, "_top10_selected_index", 0)

        if event.keysym == "Up":
            idx = max(0, idx - 1)
        elif event.keysym == "Down":
            idx = min(len(self._top10_label_widgets) - 1, idx + 1)
        elif event.keysym == "Prior":  # PageUp
            idx = max(0, idx - 5)
        elif event.keysym == "Next":   # PageDown
            idx = min(len(self._top10_label_widgets) - 1, idx + 5)
        else:
            return

        self._top10_selected_index = idx
        self._update_selection_top10(idx)

        # 点击行为（可复用 on_code_click）
        lbl = self._top10_label_widgets[idx]
        code = getattr(lbl, "_code", None)
        if code:
            self.on_code_click(code)


    def _on_label_right_click_top10(self,code ,idx):
        # self._update_selection_top10(idx)
        stock_code = code
        self.select_code = code
        self.sender.send(code)
        pyperclip.copy(code)
        if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
            # 如果发送成功，更新状态标签
            self.status_var2.set(f"发送成功: {stock_code}")
        else:
            # 如果发送失败，更新状态标签
            self.status_var2.set(f"发送失败: {stock_code}")

    def _on_label_double_click_top10(self, code, idx):
        """
        双击股票标签时，显示该股票所属概念详情。
        如果 _label_widgets 不存在或 concept_name 获取失败，
        则自动使用 code 计算该股票所属强势概念并显示详情。
        """
        try:
            # ---------------- 原逻辑 ----------------
            concept_name = None
            # if hasattr(self, "_label_widgets"):
            #     try:
            #         concept_name = getattr(self._label_widgets[idx], "_concept", None)
            #     except Exception:
            #         concept_name = None

            # ---------------- 回退逻辑 ----------------
            if not concept_name:
                # logger.info(f"[Info] 未从 _label_widgets 获取到概念，尝试通过 {code} 自动识别强势概念。")
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"自动识别强势概念：{concept_name}")
                    else:
                        messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                        return
                except Exception as e:
                    logger.info(f"[Error] 回退获取概念失败：{e}")
                    traceback.print_exc()
                    messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                    return

            # ---------------- 绘图逻辑 ----------------
            self.plot_following_concepts_pg(code,top_n=1)

            # ---------------- 打开/复用 Top10 窗口 ----------------
            # self.show_concept_top10_window(concept_name,code=code)
            self.show_concept_top10_window_simple(concept_name,code=code)

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 更新标题 ---
                win.title(f"{concept_name} 概念前10放量上涨股")

                # --- 检查窗口状态 ---
                try:
                    state = win.state()

                    if state == "iconic" or self.is_window_covered_by_main(win):
                        win.deiconify()
                        win.lift()
                        win.focus_force()
                        win.attributes("-topmost", True)
                        win.after(100, lambda: win.attributes("-topmost", False))
                    else:
                        if not win.focus_displayof():
                            win.lift()
                            win.focus_force()

                except Exception as e:
                    logger.info(f"窗口状态检查失败：{e}")

                # --- 恢复 Canvas 滚动位置 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

        except Exception as e:
            logger.info(f"获取概念详情失败：{e}")
            traceback.print_exc()

    def _update_selection_top10(self, idx):
        """更新 Top10 窗口选中高亮并滚动"""
        if not hasattr(self, "_concept_top10_win") or not self._concept_top10_win:
            return

        win = self._concept_top10_win
        canvas = win._canvas_top10
        scroll_frame = win._content_frame_top10

        normal_bg = win.cget("bg")
        highlight_bg = "lightblue"

        # 清除所有高亮
        for rf in self._top10_label_widgets:
            if isinstance(rf, list):
                for ch in rf:
                    ch.configure(bg=normal_bg)
            else:
                for ch in rf.winfo_children():
                    ch.configure(bg=normal_bg)

        # 高亮选中
        if 0 <= idx < len(self._top10_label_widgets):
            rf = self._top10_label_widgets[idx]
            if isinstance(rf, list):
                for ch in rf:
                    ch.configure(bg=highlight_bg)
                code = rf[0]._code
            else:
                for ch in rf.winfo_children():
                    ch.configure(bg=highlight_bg)
                code = rf.winfo_children()[0]._code

            self._top10_selected_index = idx
            self.select_code = code

            # 滚动 Canvas 使当前 Label 可见
            canvas.update_idletasks()
            scroll_frame.update_idletasks()
            if isinstance(rf, list):
                lbl_top = rf[0].winfo_y()
                lbl_bottom = rf[-1].winfo_y() + rf[-1].winfo_height()
            else:
                lbl_top = rf.winfo_y()
                lbl_bottom = lbl_top + rf.winfo_height()
            view_top = canvas.canvasy(0)
            view_bottom = view_top + canvas.winfo_height()
            if lbl_top < view_top:
                canvas.yview_moveto(lbl_top / max(1, scroll_frame.winfo_height()))
            elif lbl_bottom > view_bottom:
                canvas.yview_moveto((lbl_bottom - canvas.winfo_height()) / max(1, scroll_frame.winfo_height()))

            # 发送消息
            self.sender.send(code)

    def _bind_copy_expr(self, win):
        """绑定或重新绑定复制表达式按钮"""
        btn_frame = getattr(win, "_btn_frame", None)
        if btn_frame is None: return
        # 销毁旧按钮
        if hasattr(win, "_btn_copy_expr") and win._btn_copy_expr.winfo_exists():
            win._btn_copy_expr.destroy()
        def _copy_expr():
            concept = getattr(win, "_concept_name","未知概念")
            q = f'category.str.contains("{concept}", na=False)'
            pyperclip.copy(q)
            self.after(100, lambda: toast_message(self,f"已复制筛选条件：{q}"))
        btn = tk.Button(btn_frame, text="复制", command=_copy_expr)
        btn.pack(side="left", padx=4)
        win._btn_copy_expr = btn

   
    def show_concept_top10_window_simple(self, concept_name, code=None, auto_update=True, interval=30,stock_name=None,focus_force=False):
        """
        显示指定概念的前10放量上涨股，不复用已有窗口，简单独立创建
        参数：
            concept_name: 概念名称
            code: 股票代码，可选
            auto_update: 是否自动刷新
            interval: 刷新间隔（秒）
            stock_name: 股票名称（可选）
        """

        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            toast_message(self, "df_all 数据为空，无法筛选概念股票")
            return

        try:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        except Exception as e:
            toast_message(self, f"筛选表达式错误: {e}")
            return

        if df_concept.empty:
            toast_message(self, f"概念【{concept_name}】暂无匹配股票")
            return

        if not hasattr(self, "_pg_top10_window_simple"):
            self._pg_top10_window_simple = {}

        # unique_code = f"{concept_name or ''}_{code or ''}"
        unique_code = f"{concept_name or ''}_"
        # --- 检查是否已有相同 code 的窗口 ---
        for k, v in self._pg_top10_window_simple.items():
            if v.get("code") == unique_code and v.get("win") is not None and v.get("win").winfo_exists():
                # 已存在，聚焦并显示TK
                logger.info(f'已存在，聚焦并显示TK:{unique_code}')
                v["win"].deiconify()      # 如果窗口最小化了，恢复
                v["win"].lift()           # 提到最前
                v["win"].focus_force()    # 获得焦点
                if hasattr(v["win"], "_tree_top10"):
                    v["win"]._tree_top10.selection_set(v["win"]._tree_top10.get_children()[0])  # 选中第一行（可选）
                    v["win"]._tree_top10.focus_set() # 获得焦点
                v["win"].attributes("-topmost", True)
                v["win"].after(100, lambda: v["win"].attributes("-topmost", False))
                return  # 不创建新窗口

        # --- 新窗口 ---
        win = tk.Toplevel(self)
        win.title(f"{concept_name} 概念前10放量上涨股")
        # win.minsize(460, 320)
        real_width = int(saved_width * self.scale_factor)
        real_height = int(saved_height * self.scale_factor)
        win.minsize(real_width, real_height)
        # win.attributes('-toolwindow', True)  # 去掉最大化/最小化按钮，只留关闭按钮

        # now = datetime.now()
        # timestamp_suffix = f"{now:%M%S}{int(now.microsecond/1000):03d}"[:6]
        # key = f"{concept_name}_{timestamp_suffix}"
        # key = f"{concept_name}_{timestamp_suffix}"
        # logger.info(f'show_concept_top10_window_simple : {unique_code}')
        # 缓存窗口
        # --- 如果传了code但没传stock_name，则从self.df_all查找 ---
        if code and not stock_name:
            try:
                if hasattr(self, "df_all") and code in self.df_all.index:
                    stock_name = self.df_all.loc[code, "name"]
                elif hasattr(self, "df_all") and "code" in self.df_all.columns:
                    match = self.df_all[self.df_all["code"].astype(str) == str(code)]
                    if not match.empty:
                        stock_name = match.iloc[0]["name"]
            except Exception as e:
                logger.info(f"查找股票名称出错: {e}")

        # 确保格式化
        code = str(code).zfill(6) if code else ""
        stock_name = stock_name or "未命名"

        self._pg_top10_window_simple[unique_code] = {
            "win": win,
            "toplevel": win,
            "code": f"{concept_name or ''}_{code or ''}",
            "stock_info": [ code , stock_name, concept_name]   # 这里保存股票详细信息
        }

        # 这里可以继续填充窗口内容

        # "plot": plot, "bars": bars, "texts": texts,
        # "timer": timer, "chk_auto": chk_auto, "spin": spin_interval
        # 主体 Treeview
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        columns = ("code", "name", "percent", "volume","red")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量","red":"连阳"}
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            tree.column(col, anchor="center", width=60 if col != "name" else 80)

        # 保存引用，独立窗口不复用 _concept_top10_win
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="red")        # 涨幅或低点大于前一日
        win._tree_top10.tag_configure("orange_row", foreground="orange")  # 高位或突破
        win._tree_top10.tag_configure("green_row", foreground="green")    # 跌幅明显
        win._tree_top10.tag_configure("blue_row", foreground="#555555")      # 弱势或低于均线低于 ma5d
        win._tree_top10.tag_configure("purple_row", foreground="purple")  # 成交量异常等特殊指标
        win._tree_top10.tag_configure("yellow_row", foreground="yellow")  # 临界或预警

        win._concept_name = concept_name
        # 在创建窗口时保存定时器 id
        win._auto_refresh_id = None
        # 初始化窗口状态（放在创建 win 后）
        win._selected_index = 0
        win.select_code = None
        win.is_refreshing = False

        # 使用 unique_code 构造唯一的窗口保存名
        window_name = f"concept_top10_window-{unique_code}"
        try:
            self.load_window_position(win, window_name, default_width=420, default_height=340)
        except Exception:
            win.geometry("420x340")

        # 鼠标滚轮悬停滚动
        def on_mousewheel(event):
            tree.yview_scroll(int(-1*(event.delta/120)), "units")
        def bind_mousewheel(event):
            tree.bind_all("<MouseWheel>", on_mousewheel)
            tree.bind_all("<Button-4>", lambda e: tree.yview_scroll(-1,"units"))
            tree.bind_all("<Button-5>", lambda e: tree.yview_scroll(1,"units"))
        def unbind_mousewheel(event=None):
            tree.unbind_all("<MouseWheel>")
            tree.unbind_all("<Button-4>")
            tree.unbind_all("<Button-5>")

        tree.bind("<Enter>", bind_mousewheel)
        tree.bind("<Leave>", unbind_mousewheel)


        # 双击 / 右键
        tree.bind("<Double-1>", lambda e: self._on_tree_double_click_newTop10(tree))
        tree.bind("<Button-3>", lambda e: self._on_tree_right_click_newTop10(tree, e))

        self.monitor_windows[unique_code] = {
                'toplevel': win,
                'monitor_tree': tree,
                'stock_info': code  # 新增这一行
            }
        # -------------------
        # 鼠标点击统一处理
        # -------------------
        def select_row_by_item(item):
            children = list(tree.get_children())
            if item not in children:
                return
            idx = children.index(item)
            win._selected_index = idx

            code = tree.item(item, "values")[0]
            if code != win.select_code:
                win.select_code = code
                self.sender.send(code)

            # 高亮
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                select_row_by_item(sel[0])

        tree.bind("<<TreeviewSelect>>", on_click)

        # -------------------
        # 键盘操作
        # -------------------
        def on_key(event):
            children = list(tree.get_children())
            if not children:
                return "break"

            idx = getattr(win, "_selected_index", 0)

            if event.keysym == "Up":
                idx = max(0, idx-1)
            elif event.keysym == "Down":
                idx = min(len(children)-1, idx+1)
            elif event.keysym in ("Prior", "Next"):  # PageUp / PageDown
                step = 10
                idx = max(0, idx-step) if event.keysym=="Prior" else min(len(children)-1, idx+step)
            elif event.keysym == "Return":
                sel = tree.selection()
                if sel:
                    code = tree.item(sel[0], "values")[0]
                    self._on_label_double_click_top10(code, int(sel[0]))
                return "break"
            else:
                return

            target_item = children[idx]
            tree.selection_set(target_item)
            tree.focus(target_item)
            tree.see(target_item)
            select_row_by_item(target_item)
            win._selected_index = idx
            return "break"  # ❌ 阻止 Treeview 默认上下键移动

        # 绑定键事件到 tree（或 win），确保 tree 有焦点

        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)
        tree.bind("<Prior>", on_key)
        tree.bind("<Next>", on_key)
        tree.bind("<Return>", on_key)
        tree.focus_set()

        # --- 按钮和控制栏区域 ---
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=4)
        win._btn_frame = btn_frame  # 保存引用，方便复用
        # --- 自动更新控制栏 ---
        ctrl_frame = tk.Frame(btn_frame)
        ctrl_frame.pack(side="left", padx=6)

        chk_auto = tk.BooleanVar(value=True)  # 默认开启自动更新
        chk_btn = tk.Checkbutton(ctrl_frame, text="自动更新", variable=chk_auto,takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=5,takefocus=False)
        spin_interval.delete(0, "end")
        spin_interval.insert(0, duration_sleep_time)  # 默认30秒
        spin_interval.pack(side="left")
        tk.Label(ctrl_frame, text="秒").pack(side="left")
        spin_interval.configure(takefocus=0)
        chk_btn.configure(takefocus=0)
        # 保存引用到窗口，方便复用
        win._chk_auto = chk_auto
        win._spin_interval = spin_interval
        
        # --- 在创建窗口或复用窗口后调用 ---
        # self._bind_copy_expr(win)
        def _bind_copy_expr(win):
            """绑定或重新绑定复制表达式按钮"""
            btn_frame = getattr(win, "_btn_frame", None)
            if btn_frame is None: return
            # 销毁旧按钮
            if hasattr(win, "_btn_copy_expr") and win._btn_copy_expr.winfo_exists():
                win._btn_copy_expr.destroy()
            def _copy_expr():
                concept = getattr(win, "_concept_name","未知概念")
                q = f'category.str.contains("{concept}", na=False)'
                pyperclip.copy(q)
                self.after(100, lambda: toast_message(self,f"已复制筛选条件：{q}"))
            btn = tk.Button(btn_frame, text="复制", command=_copy_expr)
            btn.pack(side="left", padx=4)
            win._btn_copy_expr = btn

        _bind_copy_expr(win)

        # --- 状态栏 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        lbl_status = tk.Label(btn_frame, text=f"显示 {visible_count}/{total_count} 只", anchor="e",
                              fg="#555", font=self.default_font)
        lbl_status.pack(side="right", padx=8)
        win._status_label_top10 = lbl_status

        def auto_refresh():
            if not win.winfo_exists():
                # 窗口已经关闭，取消定时器
                if getattr(win, "_auto_refresh_id", None):
                    win.after_cancel(win._auto_refresh_id)
                    win._auto_refresh_id = None
                return

            if chk_auto.get():
                # 仅工作时间刷新
                if not cct.get_work_time():
                    pass
                else:
                    try:
                        concept_name = getattr(win, "_concept_name", None)
                        if not concept_name:
                            logger.info('win._concept_name  : None')
                            return
                        df_latest = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
                        self._fill_concept_top10_content(win, concept_name, df_latest, code=code)
                    except Exception as e:
                        logger.info(f"[WARN] 自动刷新失败: {e}")

            # 安全地重新注册下一次刷新
            win._auto_refresh_id = win.after(int(spin_interval.get()) * 1000, auto_refresh)

        # 启动循环
        auto_refresh()

        def _on_close():
            try:
                window_name = f"concept_top10_window-{unique_code}"
                self.save_window_position(win, window_name)
            except Exception:
                pass

            # 取消自动刷新
            if getattr(win, "_auto_refresh_id", None):
                win.after_cancel(win._auto_refresh_id)
                win._auto_refresh_id = None

            unbind_mousewheel()
            # ✅ 安全删除 _pg_top10_window_simple 中对应项
            try:
                # 用字典推导找到对应键
                for k, v in list(self._pg_top10_window_simple.items()):
                    if v.get("win") == win:
                        del self._pg_top10_window_simple[k]
                        break
            except Exception as e:
                logger.info(f"清理 _pg_top10_window_simple 出错: {e}")

            win.destroy()
            self._concept_top10_win = None



        win.protocol("WM_DELETE_WINDOW", _on_close)
        win.bind("<Escape>", lambda e: _on_close())  # ESC关闭窗口
        # 填充数据
        self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
        if focus_force:
            logger.info(f'已存在，focus_force聚焦并显示TK:{unique_code}')
            win.transient(self)              # 关联主窗口（非常关键）
            win.attributes("-topmost", True) # 临时置顶
            win.deiconify()                  # 确保不是最小化
            win.lift()
            win.focus_force()    # 获得焦点
            if hasattr(win, "tree"):
                tree.selection_set(tree.get_children()[0])  # 选中第一行（可选）
                tree.focus_set()


            # 延迟激活焦点（绕过 Windows 限制）
            # win.after(50, lambda: (
            #     win._tree_top10.focus_set()   # 获得焦点focus_set(),
            #     win.attributes("-topmost", False)))
        # logger.info(f"_focus_top10_tree = {self._focus_top10_tree}")
        # self._focus_top10_tree(win)
        return win

    def _focus_top10_tree(self,win):
        try:
            if not hasattr(win, "_tree_top10"):
                return
            tree = win._tree_top10
            if not tree.winfo_exists():
                return

            def do_focus():
                children = tree.get_children()
                if children:
                    tree.selection_set(children[0])
                    tree.focus(children[0])
                    tree.see(children[0])
                tree.focus_set()

            # 等 UI / after / PG timer 全部稳定下来
            win.after(500, do_focus)
        except Exception as e:
            logger.info(f"聚焦 Top10 Tree 失败: {e}")

    def show_concept_top10_window(self, concept_name, code=None, auto_update=True, interval=30,bring_monitor_status=True):
        """
        显示指定概念的前10放量上涨股（Treeview 高性能版，完全替代 Canvas 版本）
        auto_update: 是否自动刷新
        interval: 自动刷新间隔秒
        """
        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            toast_message(self, "df_all 数据为空，无法筛选概念股票")
            return

        query_expr = f'category.str.contains("{concept_name}", na=False)'
        try:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        except Exception as e:
            toast_message(self,  f"筛选表达式错误: {query_expr}\n{e}")
            return

        if df_concept.empty:
            logger.info(f"概念【{concept_name}】暂无匹配股票")
            self.after(100, lambda: toast_message(self,f"概念【{concept_name}】暂无匹配股票"))
            return

        # --- 复用窗口 ---
        try:
            if getattr(self, "_concept_top10_win", None) and self._concept_top10_win.winfo_exists():
                win = self._concept_top10_win
                win.deiconify()
                win.lift()
                win._concept_name = concept_name  # 更新概念名
                if hasattr(win, "_chk_auto") and hasattr(win, "_spin_interval"):
                    # 复用已有控件，恢复值
                    chk_auto = win._chk_auto
                    spin_interval = win._spin_interval
                # 重新绑定复制按钮
                # self._bind_copy_expr(win)

                self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
                return

        except Exception:
            self._concept_top10_win = None

        # --- 新窗口 ---
        win = tk.Toplevel(self)
        self._concept_top10_win = win
        win.title(f"{concept_name} 概念前10放量上涨股")
        # win.attributes('-toolwindow', True)  # 去掉最大化/最小化按钮，只留关闭按钮
        win._concept_name = concept_name
        real_width = int(saved_width * self.scale_factor)
        real_height = int(saved_height * self.scale_factor)
        win.minsize(real_width, real_height)
        # win.minsize(460, 320)
        # 在创建窗口时保存定时器 id
        win._auto_refresh_id = None
        # 初始化窗口状态（放在创建 win 后）
        win._selected_index = 0
        win.select_code = None
        win.is_refreshing = False

        try:
            self.load_window_position(win, "concept_top10_window", default_width=520, default_height=420)
        except Exception:
            win.geometry("520x420")

        # --- Treeview 主体 ---
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        columns = ("code", "name", "percent", "volume","red")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量"}
        col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量","red":"连阳"}
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            tree.column(col, anchor="center", width=60 if col != "name" else 80)

        # 保存引用
        win._content_frame_top10 = frame
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="red")        # 涨幅或低点大于前一日
        win._tree_top10.tag_configure("orange_row", foreground="orange")  # 高位或突破
        win._tree_top10.tag_configure("green_row", foreground="green")    # 跌幅明显
        win._tree_top10.tag_configure("blue_row", foreground="#555555")      # 弱势或低于均线低于 ma5d
        win._tree_top10.tag_configure("purple_row", foreground="purple")  # 成交量异常等特殊指标
        win._tree_top10.tag_configure("yellow_row", foreground="yellow")  # 临界或预警

        # 鼠标滚轮悬停滚动
        def on_mousewheel(event):
            tree.yview_scroll(int(-1*(event.delta/120)), "units")
        def bind_mousewheel(event):
            tree.bind_all("<MouseWheel>", on_mousewheel)
            tree.bind_all("<Button-4>", lambda e: tree.yview_scroll(-1,"units"))
            tree.bind_all("<Button-5>", lambda e: tree.yview_scroll(1,"units"))
        def unbind_mousewheel(event=None):
            tree.unbind_all("<MouseWheel>")
            tree.unbind_all("<Button-4>")
            tree.unbind_all("<Button-5>")

        tree.bind("<Enter>", bind_mousewheel)
        tree.bind("<Leave>", unbind_mousewheel)

        # 双击 / 右键
        tree.bind("<Double-1>", lambda e: self._on_tree_double_click_newTop10(tree))
        tree.bind("<Button-3>", lambda e: self._on_tree_right_click_newTop10(tree, e))

        # unique_code = f"{code or ''}_{top_n or ''}"
        unique_code = f"{concept_name or ''}_{code or ''}"
        self.monitor_windows[unique_code] = {
                'toplevel': win,
                'monitor_tree': tree,
                'stock_info': code  # 新增这一行
            }

        # -------------------
        # 鼠标点击统一处理
        # -------------------
        def select_row_by_item(item):
            children = list(tree.get_children())
            if item not in children:
                return
            idx = children.index(item)
            win._selected_index = idx

            code = tree.item(item, "values")[0]
            if code != win.select_code:
                win.select_code = code
                self.sender.send(code)

            # 高亮
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                select_row_by_item(sel[0])

        tree.bind("<<TreeviewSelect>>", on_click)

        # -------------------
        # 键盘操作
        # -------------------
        def on_key(event):
            children = list(tree.get_children())
            if not children:
                return "break"

            idx = getattr(win, "_selected_index", 0)

            if event.keysym == "Up":
                idx = max(0, idx-1)
            elif event.keysym == "Down":
                idx = min(len(children)-1, idx+1)
            elif event.keysym in ("Prior", "Next"):  # PageUp / PageDown
                step = 10
                idx = max(0, idx-step) if event.keysym=="Prior" else min(len(children)-1, idx+step)
            elif event.keysym == "Return":
                sel = tree.selection()
                if sel:
                    code = tree.item(sel[0], "values")[0]
                    self._on_label_double_click_top10(code, int(sel[0]))
                return "break"
            else:
                return

            target_item = children[idx]
            tree.selection_set(target_item)
            tree.focus(target_item)
            tree.see(target_item)
            select_row_by_item(target_item)
            win._selected_index = idx

            return "break"  # ❌ 阻止 Treeview 默认上下键移动


        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)
        tree.bind("<Prior>", on_key)
        tree.bind("<Next>", on_key)
        tree.bind("<Return>", on_key)
        tree.bind("<FocusIn>", lambda e: tree.focus_set())
        # tree.focus_set()

        # --- 按钮和控制栏区域 ---
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=4)
        win._btn_frame = btn_frame  # 保存引用，方便复用
        # --- 自动更新控制栏 ---
        ctrl_frame = tk.Frame(btn_frame)
        ctrl_frame.pack(side="left", padx=6)

        chk_auto = tk.BooleanVar(value=True)  # 默认开启自动更新
        chk_btn = tk.Checkbutton(ctrl_frame, text="自动更新", variable=chk_auto,takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=5,takefocus=False)
        spin_interval.delete(0, "end")
        spin_interval.insert(0, duration_sleep_time)  # 默认30秒
        spin_interval.pack(side="left")
        tk.Label(ctrl_frame, text="秒").pack(side="left")
        spin_interval.configure(takefocus=0)
        chk_btn.configure(takefocus=0)
        # 保存引用到窗口，方便复用
        win._chk_auto = chk_auto
        win._spin_interval = spin_interval
        # # --- 复制表达式按钮 ---
        # def _copy_expr():
        #     import pyperclip
        #     q = f'category.str.contains("{concept_name}", na=False)'
        #     pyperclip.copy(q)
        #     self.after(100, lambda: toast_message(self, f"已复制筛选条件：{q}"))

        # tk.Button(btn_frame, text="复制筛选", command=_copy_expr).pack(side="left", padx=4)

        
        # --- 在创建窗口或复用窗口后调用 ---
        self._bind_copy_expr(win)

        # --- 状态栏 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        lbl_status = tk.Label(btn_frame, text=f"显示 {visible_count}/{total_count} 只", anchor="e",
                              fg="#555", font=self.default_font)
        lbl_status.pack(side="right", padx=8)
        win._status_label_top10 = lbl_status

        def auto_refresh():
            if not win.winfo_exists():
                # 窗口已经关闭，取消定时器
                if getattr(win, "_auto_refresh_id", None):
                    win.after_cancel(win._auto_refresh_id)
                    win._auto_refresh_id = None
                return

            if chk_auto.get():
                # 仅工作时间刷新
                if not cct.get_work_time():
                    pass
                else:
                    try:
                        concept_name = getattr(win, "_concept_name", None)
                        if not concept_name:
                            logger.info('win._concept_name  : None')
                            return
                        df_latest = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
                        self._fill_concept_top10_content(win, concept_name, df_latest, code=code)
                    except Exception as e:
                        logger.info(f"[WARN] 自动刷新失败: {e}")

            # 安全地重新注册下一次刷新
            win._auto_refresh_id = win.after(int(spin_interval.get()) * 1000, auto_refresh)

        # 启动循环
        auto_refresh()


        def _on_close():
            try:
                self.save_window_position(win, "concept_top10_window")
            except Exception:
                pass

            # 取消自动刷新
            if getattr(win, "_auto_refresh_id", None):
                win.after_cancel(win._auto_refresh_id)
                win._auto_refresh_id = None

            unbind_mousewheel()
            win.destroy()
            self._concept_top10_win = None
        def window_focus_bring_monitor_status(win):
            if bring_monitor_status:
                self.on_monitor_window_focus(win)
                # win.lift()           # 提前显示
                # win.focus_force()    # 聚焦
                # win.attributes("-topmost", True)
                # win.after(100, lambda: win.attributes("-topmost", False))
        
        win.bind("<Button-1>", lambda e, w=win: window_focus_bring_monitor_status(w))
        win.protocol("WM_DELETE_WINDOW", _on_close)
        # 填充数据
        self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
        # 窗口已创建 / 已复用
        # logger.info(f"_focus_top10_tree = {self._focus_top10_tree}")
        self._focus_top10_tree(win)

    def _fill_concept_top10_content(self, win, concept_name, df_concept=None, code=None, limit=50):
        """
        填充概念Top10内容到Treeview（支持实时刷新）。
        - df_concept: 可选，若为 None 则从 self.df_all 获取
        - code: 打开窗口或刷新时优先选中的股票 code
        - limit: 显示前 N 条
        """
        tree = win._tree_top10

        # # ✅ 先确保 tag 配置只做一次
        # if not getattr(tree, "_tag_inited", False):
        #     tree.tag_configure("red_row", foreground="red")        # 涨幅或低点大于前一日
        #     tree.tag_configure("green_row", foreground="green")    # 跌幅明显
        #     tree.tag_configure("orange_row", foreground="orange")  # 高位或突破
        #     #tree.tag_configure("blue_row", foreground="#555555")    # 灰色弱势或低于均线  “purple”紫色、“magenta”品红/洋红 深灰（#555555）
        #     #tree.tag_configure("purple_row", foreground="purple")  # 弱势 / 低于 ma5d
        #     tree.tag_configure("purple_row", foreground="purple")  # 成交量异常等特殊指标
        #     tree.tag_configure("yellow_row", foreground="yellow")  # 临界或预警临界 / 低于 ma20d
        #     tree._tag_inited = True


        # 清空旧行
        tree.delete(*tree.get_children())

        # 如果 df_concept 为 None，则从 self.df_all 动态获取
        if df_concept is None:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        if df_concept.empty:
            return

        # 排序状态
        win._top10_sort_state = getattr(win, "_top10_sort_state", {"col": "percent", "asc": False})
        sort_col = win._top10_sort_state["col"]
        ascending = win._top10_sort_state["asc"]
        if sort_col in df_concept.columns:
            df_concept = df_concept.sort_values(sort_col, ascending=ascending)

        # 限制显示前 N 条
        df_display = df_concept.head(limit).copy()
        tree._full_df = df_concept.copy()
        tree._display_limit = limit
        tree.config(height=5)
        # 插入 Treeview 并建立 code -> iid 映射
        code_to_iid = {}
        for idx, (code_row, row) in enumerate(df_display.iterrows()):
            iid = str(idx)
            latest_row = self.df_all.loc[code_row] if code_row in self.df_all.index else row
            percent = latest_row.get("percent")
            # === 行条件判断 ===
            # row_tags = []
            row_tags = get_row_tags(latest_row)

            # low = latest_row.get("low")
            # lastp1d = latest_row.get("lastp1d")
            # high = latest_row.get("high")
            # high4 = latest_row.get("high4")  # 假设 high4 在 latest_row 中

            # row_tags = []

            # # 红色条件
            # if pd.notna(low) and pd.notna(lastp1d):
            #     if low > lastp1d:
            #         row_tags.append("red_row")

            # # 橙色条件
            # if pd.notna(high) and pd.notna(high4):
            #     if high > high4 or (pd.notna(low) and low > high4):
            #         row_tags.append("orange_row")


            if pd.isna(percent) or percent == 0:
                percent = latest_row.get("per1d", row.get("per1d", 0))

            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    code_row,
                    latest_row.get("name", row.get("name", "")),
                    f"{percent:.2f}",
                    f"{latest_row.get('volume', row.get('volume', 0)):.1f}",
                    latest_row.get("red", row.get("red", 0)),
                ),
                tags=tuple(row_tags)
            )

            # tree.insert("", "end", iid=iid,
            #             values=(code_row,
            #                     latest_row.get("name", row.get("name", "")),
            #                     # f"{latest_row.get('percent', row.get('percent', 0)):.2f}",
            #                     f"{percent:.2f}",
            #                     f"{latest_row.get('volume', row.get('volume', 0)):.1f}",
            #                     latest_row.get("red", row.get("red", 0)) ))

            code_to_iid[code_row] = iid

        # --- 默认选中逻辑 ---
        children = list(tree.get_children())
        if children:
            # 优先使用窗口当前选中 code，其次使用传入 code
            target_code = getattr(win, "select_code", None) or code
            target_iid = code_to_iid.get(target_code, children[0])

            tree.selection_set(target_iid)
            tree.focus(target_iid)
            # # 强制刷新 Treeview 渲染，再滚动
            win.update_idletasks()      # 确保 Treeview 已渲染
            # tree.see(target_iid)

            # 延迟滚动 + 高亮
            # def scroll_and_highlight():
            #     tree.see(target_iid)
            #     self._highlight_tree_selection(tree, target_iid)
            def scroll_and_highlight():
                tree.see(target_iid)
                self._highlight_tree_selection(tree, target_iid)
                # # 高亮后保持红色行
                # for iid in tree.get_children():
                #     tags = tree.item(iid, "tags")
                #     if "red_row" in tags:
                #         tree.item(iid, tags=tags)  # 强制刷新标签


            win.after(50, scroll_and_highlight)
            # 更新窗口索引和选中 code
            win._selected_index = children.index(target_iid)
            win.select_code = tree.item(target_iid, "values")[0]

            # 高亮
            # self._highlight_tree_selection(tree, target_iid)

        # --- 更新状态栏 ---
        if hasattr(win, "_status_label_top10"):
            visible_count = len(df_display)
            total_count = len(df_concept)
            win._status_label_top10.config(text=f"显示 {visible_count}/{total_count} 只")
            win._status_label_top10.pack(side="bottom", fill="x", pady=(0, 4))

        win.update_idletasks()


    def _setup_tree_bindings_newTop10(self, tree):
        """
        给 Treeview 绑定事件（单击、双击、右键、键盘上下）
        """
        # 左键单击选中行
        def on_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                tree.focus(item)

        # 双击打开
        def on_double_click(event):
            item = tree.focus()
            if item:
                code = tree.item(item, "values")[0]
                self._on_label_double_click_top10(code, int(item))

        # 右键菜单
        def on_right_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                tree.focus(item)
                code = tree.item(item, "values")[0]
                self._on_label_right_click_top10(code, int(item))

        # 键盘上下移动选中项
        def on_key(event):
            sel = tree.selection()
            if not sel:
                return
            cur = sel[0]
            all_items = tree.get_children()
            if cur in all_items:
                idx = all_items.index(cur)
                if event.keysym == "Up" and idx > 0:
                    new_item = all_items[idx - 1]
                elif event.keysym == "Down" and idx < len(all_items) - 1:
                    new_item = all_items[idx + 1]
                else:
                    return
                tree.selection_set(new_item)
                tree.focus(new_item)
                tree.see(new_item)

        # 绑定事件
        tree.bind("<Button-1>", on_click)
        tree.bind("<Double-Button-1>", on_double_click)
        tree.bind("<Button-3>", on_right_click)
        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)

        # 让 Treeview 能获得焦点（按键事件才有效）
        tree.focus_set()
        tree.bind("<FocusIn>", lambda e: tree.focus_set())


    # def _highlight_tree_selection(self, tree, item):
    #     """
    #     Treeview 高亮选中行（背景蓝色，其他清除）
    #     """
    #     for iid in tree.get_children():
    #         tree.item(iid, tags=())
    #     tree.item(item, tags=("selected",))
    #     tree.tag_configure("selected", background="#d0e0ff")

    def _highlight_tree_selection(self, tree, item):
        """
        Treeview 高亮选中行（背景蓝色，其他清除，但保留 red_row）
        """
        for iid in tree.get_children():
            tags = list(tree.item(iid, "tags"))
            if "selected" in tags:
                tags.remove("selected")  # 移除旧的 selected
            tree.item(iid, tags=tuple(tags))

        # 给新选中行添加 selected
        tags = list(tree.item(item, "tags"))
        if "selected" not in tags:
            tags.append("selected")
        tree.item(item, tags=tuple(tags))

        tree.tag_configure("selected", background="#d0e0ff")


    def _sort_treeview_column_newTop10_bug(self, tree, col, reverse=None):
        if not hasattr(tree, "_full_df") or tree._full_df.empty:
            return

        # 初始化排序状态
        if not hasattr(tree, "_sort_state"):
            tree._sort_state = {}

        # 切换排序顺序
        if reverse is None:
            reverse = not tree._sort_state.get(col, False)
        tree._sort_state[col] = not reverse

        # 排序完整数据
        df_sorted = tree._full_df.sort_values(col, ascending=not reverse)

        # 填充前 limit 条
        limit = getattr(tree, "_display_limit", 50)
        df_display = df_sorted.head(limit)

        tree.delete(*tree.get_children())
        for idx, (code_row, row) in enumerate(df_display.iterrows()):
            iid = str(code_row)  # 使用原 DataFrame index 或股票 code 保证唯一
            percent = row.get("percent")
            if pd.isna(percent) or percent == 0:
                percent = row.get("per1d")
            tree.insert("", "end", iid=iid,
                        values=(code_row, row["name"], f"{percent:.2f}", f"{row.get('volume',0):.1f}", f"{row.get('red',0)}"))


        # 保留选中状态
        if hasattr(tree, "_selected_index") and tree.get_children():
            sel_iid = str(getattr(tree, "_selected_index", tree.get_children()[0]))
            if sel_iid in tree.get_children():
                tree.selection_set(sel_iid)
                tree.focus(sel_iid)
                tree.see(sel_iid)

        # 更新heading command
        tree.heading(col, command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, not reverse))


    def _sort_treeview_column_newTop10(self, tree, col, reverse=None):

        if not hasattr(tree, "_full_df") or tree._full_df.empty:
            logger.info("[WARN] Treeview _full_df 为空")
            return

        # 初始化排序状态
        if not hasattr(tree, "_sort_state"):
            tree._sort_state = {}

        # 切换排序顺序
        if reverse is None:
            reverse = not tree._sort_state.get(col, False)
        tree._sort_state[col] = not reverse

        # 排序完整数据
        df_sorted = tree._full_df.sort_values(col, ascending=not reverse)

        # 调试信息
        # logger.info(f"[DEBUG] Sorting column: {col}, ascending: {not reverse}, total rows: {len(df_sorted)}")

        # 填充前 limit 条
        limit = getattr(tree, "_display_limit", 50)
        df_display = df_sorted.head(limit)
        # logger.info(f"[DEBUG] Displaying top {limit} rows after sort")

        tree.delete(*tree.get_children())
        for idx, (code_row, row) in enumerate(df_display.iterrows()):
            iid = str(code_row)  # 使用原 DataFrame index 或股票 code 保证唯一
            tags_for_row = get_row_tags(row)  # 或 get_row_tags_kline(row, idx)
            percent = row.get("percent")
            if pd.isna(percent) or percent == 0:
                percent = row.get("per1d")
            tree.insert("", "end", iid=iid,
                        values=(code_row, row["name"], f"{percent:.2f}", f"{row.get('volume',0):.1f}", f"{row.get('red',0)}"),tags=tuple(tags_for_row))

        # 保留选中状态
        if hasattr(tree, "_selected_index") and tree.get_children():
            sel_iid = str(getattr(tree, "_selected_index", tree.get_children()[0]))
            if sel_iid in tree.get_children():
                tree.selection_set(sel_iid)
                tree.focus(sel_iid)
                tree.see(sel_iid)


        # 更新heading command
        tree.heading(col, command=lambda c=col: self._sort_treeview_column_newTop10(tree, c,not reverse))
        tree.yview_moveto(0)



    def _on_tree_double_click_newTop10(self, tree):
        sel = tree.selection()
        if sel:
            idx = sel[0]
            code = tree.item(idx, "values")[0]
            self._on_label_double_click_top10(code, int(idx))


    def _on_tree_right_click_newTop10(self, tree, event):
        item = tree.identify_row(event.y)
        if not item:
            return

        # 清除旧的 tag 高亮
        for iid in tree.get_children():
            tree.item(iid, tags=())

        # 设置选中行 tag
        tree.item(item, tags=("selected",))
        tree.tag_configure("selected", background="#d0e0ff")

        # 设置 selection / focus 让键盘上下键能继续用
        tree.selection_set(item)
        tree.focus(item)

        # 获取 code 并执行逻辑
        code = tree.item(item, "values")[0]
        self._on_label_right_click_top10(code, int(item))

    

    def plot_following_concepts_pg(self, code=None, top_n=10):

        if not hasattr(self, "_pg_windows"):
            self._pg_windows = {}
            self._pg_data_hash = {}

        # --- 获取股票数据 ---
        if code is None or code == "总览":
            tcode, _ = self.get_stock_code_none()
            top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n)
            code = "总览"
            name = "All"
            unique_code = f"{code or ''}_{top_n or ''}"
            logger.info(f'concepts_pg concepts : {top_concepts[0]} unique_code: {unique_code} ')
        else:
            top_concepts = self.get_following_concepts_by_correlation(code, top_n=top_n)
            name = self.df_all.loc[code]['name'] if code in self.df_all.index else code
            unique_code = f"{code or ''}_{top_n or ''}"
            concepts = [c[0] for c in top_concepts]
            logger.info(f'concepts_pg concepts : {top_concepts} unique_code: {unique_code} ')
        if not top_concepts:
            logger.info("未找到相关概念")
            return

        unique_code = f"{code or ''}_{top_n or ''}"


        # --- 检查是否已有相同 code 的窗口 ---
        for k, v in self._pg_windows.items():
            win = v.get("win")
            try:
                if v.get("code") == unique_code and v.get("win") is not None:
                    # 已存在，聚焦并显示 (PyQt)
                    win.show()               # 如果窗口被最小化或隐藏
                    win.raise_()             # 提到最前
                    win.activateWindow()     # 获得焦点
                    return  # 不创建新窗口
            except Exception as e:
                logger.info(f'e:{e} pg win is None will remove:{v.get("win")}')
                del self._pg_windows[k]
            finally:
                pass
            

        concepts = [c[0] for c in top_concepts]
        scores = np.array([c[1] for c in top_concepts])
        avg_percents = np.array([c[2] for c in top_concepts])
        follow_ratios = np.array([c[3] for c in top_concepts])
        data_hash = hashlib.md5(str(concepts[:3]).encode()).hexdigest()

        # logger.info(f'concepts : {concepts} unique_code: {unique_code} ')
        # --- 创建主窗口 ---
        win = QtWidgets.QWidget()
        win.setWindowTitle(f"{code} 概念分析Top{top_n}")
        layout = QtWidgets.QVBoxLayout(win)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # window_handle = win.windowHandle()
        # if window_handle and window_handle.screen():
            # screen = window_handle.screen()
        # else:
            # screen = self.app.primaryScreen()
        # self._dpi_now = screen.logicalDotsPerInch()
        self.dpi_scale =  1
        # logger.info(f'self.dpi_scale : {self.dpi_scale} self._dpi_now  : {self._dpi_now}')

        # 控制栏
        ctrl_layout = QtWidgets.QHBoxLayout()
        chk_auto = QtWidgets.QCheckBox("自动更新")
        spin_interval = QtWidgets.QSpinBox()
        spin_interval.setRange(5, 300)
        spin_interval.setValue(duration_sleep_time)
        spin_interval.setSuffix(" 秒")
        ctrl_layout.addWidget(chk_auto)
        ctrl_layout.addWidget(spin_interval)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # 绘图区域
        pg_widget = pg.GraphicsLayoutWidget()
        pg_widget.setContentsMargins(0, 0, 0, 0)
        pg_widget.ci.layout.setContentsMargins(0, 0, 0, 0)
        pg_widget.ci.layout.setSpacing(0)
        layout.addWidget(pg_widget)

        plot = pg_widget.addPlot()
        plot.setContentsMargins(0, 0, 0, 0)
        plot.invertY(True)
        plot.setLabel('bottom', '综合得分 (score)')
        plot.setLabel('left', '概念')

        y = np.arange(len(concepts))
        color_map = pg.colormap.get('CET-R1')
        brushes = [pg.mkBrush(color_map.map(s)) for s in scores]
        bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
        plot.addItem(bars)


        font = QtWidgets.QApplication.font()
        font_size = font.pointSize()
        self._font_size = font_size
        logger.info(f"concepts_pg 默认字体大小: {font_size}")

        texts = []
        max_score = max(scores.max(), 1)
        for i, (avg, score) in enumerate(zip(avg_percents, scores)):
            text = pg.TextItem(f"score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
            # text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
            text.setPos(score + 0.03 * max_score, y[i])
            plot.addItem(text)
            texts.append(text)
            # logger.info(f"[DEBUG] : avg={avg:.2f}, score={score:.2f}")

        plot.getAxis('left').setTicks([list(zip(y, concepts))])


        from PyQt5.QtCore import QPoint
        # 禁用右键菜单
        plot.setMenuEnabled(False)  # ✅ 关键
        current_idx = {"value": 0}  # 用 dict 保持可变引用

        plot._data_ref = {
               "concepts": concepts,
               "scores": scores,
               "avg_percents": avg_percents,
               "follow_ratios": follow_ratios,
               "bars" : bars,
               "brushes" : brushes,
               "code" : unique_code
           }
        

        # # --- 同步更新到 plot._data_ref（给 tooltip / 点击事件使用）---
        # if hasattr(plot, "_data_ref"):
        #     plot._data_ref["concepts"] = concepts
        #     plot._data_ref["scores"] = scores
        #     plot._data_ref["avg_percents"] = avg_percents
        #     plot._data_ref["follow_ratios"] = follow_ratios
        #     plot._data_ref["bars"] = bars
        #     plot._data_ref["brushes"] = brushes

        # else:
        #     # 如果第一次还没有绑定，就直接创建
        #     plot._data_ref = {
        #         "concepts": concepts,
        #         "scores": scores,
        #         "avg_percents": avg_percents,
        #         "follow_ratios": follow_ratios,
        #         "bars" : bars,
        #         "brushes" : brushes
        #     }

        # def highlight_bar(index):
        #     """高亮当前选中的 bar（通过改变颜色或添加边框实现）"""
        #     if not (0 <= index < len(concepts)):
        #         return
        #     # 恢复所有 bar 的 brush
        #     bars.setOpts(brushes=brushes)
        #     # 高亮当前选中项
        #     highlight_brushes = brushes.copy()
        #     highlight_brushes[index] = pg.mkBrush((255, 255, 0, 180))  # 黄色高亮
        #     bars.setOpts(brushes=highlight_brushes)
        #     plot.update()

        def highlight_bar(index):
            """高亮当前选中的 bar（动态读取 plot._data_ref）"""
            data = plot._data_ref
            concepts = data.get("concepts", [])
            bars = data.get("bars", None)        # 你需要把 BarGraphItem 也存到 plot._data_ref
            brushes = data.get("brushes", None)  # 同理，存默认颜色列表

            if bars is None or brushes is None:
                return
            if not (0 <= index < len(concepts)):
                return

            # 恢复所有 bar 的 brush
            bars.setOpts(brushes=brushes)

            # 高亮当前选中项
            highlight_brushes = brushes.copy()
            highlight_brushes[index] = pg.mkBrush((255, 255, 0, 180))  # 黄色高亮
            bars.setOpts(brushes=highlight_brushes)
            plot.update()

        # --- 鼠标点击事件 ---
        def mouse_click(event):
            if plot.sceneBoundingRect().contains(event.scenePos()):
                vb = plot.vb
                mouse_point = vb.mapSceneToView(event.scenePos())
                idx = int(round(mouse_point.y()))

                # ✅ 动态读取最新数据
                data = plot._data_ref
                concepts = data.get("concepts", [])
                # 获取 plot 对应的顶层窗口
                # 调用你的聚焦函数，并传入 win
                unique_code = data.get("code", '')
                self.on_monitor_window_focus_pg(unique_code)

                if 0 <= idx < len(concepts):
                    current_idx["value"] = idx
                    highlight_bar(idx)

                    if event.button() == QtCore.Qt.LeftButton:
                        self._call_concept_top10_win(code, concepts[idx])
                        win.raise_()
                        win.activateWindow()

                    elif event.button() == QtCore.Qt.RightButton:
                        concept_text = concepts[idx]
                        clipboard = QtWidgets.QApplication.clipboard()
                        copy_concept_text = f'category.str.contains("{concept_text}")'
                        clipboard.setText(copy_concept_text)

                        from PyQt5.QtCore import QPoint
                        pos = event.screenPos()
                        pos_int = QPoint(int(pos.x()), int(pos.y()))
                        QtWidgets.QToolTip.showText(pos_int, f"已复制: {copy_concept_text}", win)
                    # ⭐ 未处理的按键继续向下传播
                    event.ignore()

        plot.scene().sigMouseClicked.connect(mouse_click)

        # --- 鼠标悬停 tooltip ---
        def show_tooltip(event):
            pos = event
            vb = plot.vb
            if plot.sceneBoundingRect().contains(pos):
                mouse_point = vb.mapSceneToView(pos)
                idx = int(round(mouse_point.y()))

                # ✅ 动态读取最新数据
                data = plot._data_ref
                concepts = data.get("concepts", [])
                scores = data.get("scores", [])
                avg_percents = data.get("avg_percents", [])
                follow_ratios = data.get("follow_ratios", [])

                if 0 <= idx < len(concepts):
                    msg = (f"概念: {concepts[idx]}\n"
                           f"平均涨幅: {avg_percents[idx]:.2f}%\n"
                           f"跟随指数: {follow_ratios[idx]:.2f}\n"
                           f"综合得分: {scores[idx]:.2f}")
                    QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), msg, win)

        plot.scene().sigMouseMoved.connect(show_tooltip)

        # --- 键盘事件 ---
        def key_event(event):
            key = event.key()
            data = plot._data_ref  # ✅ 动态读取最新数据
            concepts = data.get("concepts", [])
            
            if key == QtCore.Qt.Key_R:
                self.plot_following_concepts_pg(code, top_n)
                event.accept()

            elif key in (QtCore.Qt.Key_Q, QtCore.Qt.Key_Escape):
                QtCore.QTimer.singleShot(0, win.close)
                event.accept()

            elif key == QtCore.Qt.Key_Up:
                current_idx["value"] = max(0, current_idx["value"] - 1)
                highlight_bar(current_idx["value"])
                self._call_concept_top10_win(code, concepts[current_idx["value"]])
                win.raise_()
                win.activateWindow()
                event.accept()

            elif key == QtCore.Qt.Key_Down:
                current_idx["value"] = min(len(concepts) - 1, current_idx["value"] + 1)
                highlight_bar(current_idx["value"])
                self._call_concept_top10_win(code, concepts[current_idx["value"]])
                win.raise_()
                win.activateWindow()
                event.accept()

            elif key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                idx = current_idx["value"]
                if 0 <= idx < len(concepts):
                    self._call_concept_top10_win(code, concepts[idx])
                    win.raise_()
                    # win.activateWindow()
                event.accept()
            # ⭐ 未处理的按键继续向下传播
            event.ignore()
        win.keyPressEvent = key_event

        # --- 屏幕/DPI 切换重定位文本 ---
        def reposition_texts1():
            app_font = QtWidgets.QApplication.font()
            family = app_font.family()
            logger.info(f"reposition_texts 默认字体大小: {self._font_size}")
            for i, text in enumerate(texts):
                if i >= len(concepts):
                    continue

                avg = avg_percents[i]
                score = scores[i]
                if not hasattr(win, "_prev_concepts_data"):
                    win._prev_concepts_data = {
                        "avg_percents": np.zeros(len(avg_percents)),
                        "scores": np.zeros(len(scores)),
                        "follow_ratios": np.zeros(len(follow_ratios))
                    }
                prev_data = win._prev_concepts_data
                # 平均涨幅箭头
                diff_avg = avg - prev_data["avg_percents"][i] if i < len(prev_data["avg_percents"]) else avg
                arrow_avg = "↑" if diff_avg > 0 else ("↓" if diff_avg < 0 else "→")

                # 综合得分箭头
                diff_score = score - prev_data["scores"][i] if i < len(prev_data["scores"]) else score
                arrow_score = "↑" if diff_score > 0 else ("↓" if diff_score < 0 else "→")

                # 更新文字内容
                text.setText(f"avg:{arrow_avg} {avg:.2f}%\nscore:{arrow_score} {score:.2f}")

                # ✅ 安全地设置字体大小（不调用 text.font()）
                text.setFont(QtGui.QFont("Microsoft YaHei", self._font_size))

                # 更新坐标
                x = (scores[i] + 0.03 * max_score) * self.dpi_scale
                y_pos = y[i] * self.dpi_scale
                text.setPos(x, y_pos)
                # 设置位置
                # text.setPos(score + 0.03 * max_score, y[i])
                text.setAnchor((0, 0.5))  # 垂直居中
            plot.update()

        # 定时轮询 DPI / 屏幕变化
        prev_screen = None
        prev_dpi = None
        base_fontsize = None
        # app = QtWidgets.QApplication.instance() or pg.mkQApp()
        # screen = app.primaryScreen()
        # dpi = screen.logicalDotsPerInch()
        # font_size = max(7, int(10 * dpi / 96))  # 根据 DPI 调整字体
        # logger.info(f"[DEBUG] 当前屏幕: {screen.name()}, DPI={dpi}, 字体大小={font_size}")

        def check_screen():
            nonlocal prev_screen, prev_dpi ,base_fontsize
            window_handle = win.windowHandle()
            if window_handle and window_handle.screen():
                screen = window_handle.screen()
            else:
                screen = self.app.primaryScreen()
            self._dpi_now = screen.logicalDotsPerInch()
            # self.dpi_scale = self._dpi_now / prev_dpi if prev_dpi else 1
            # logger.info(f'self.dpi_scale : {self.dpi_scale}')
            if prev_screen or  prev_dpi:
                if screen != prev_screen or self._dpi_now  != prev_dpi:
                    logger.info(f'dpi_now :{self._dpi_now } prev_dpi :{prev_dpi}')
                    prev_screen, prev_dpi = screen, self._dpi_now
                    # self.dpi_scale = self._dpi_now / prev_dpi
                    # if self._dpi_now == 96 and font_size == self.base_font_size:
                    #     self._font_size = int(self._font_size / self.scale_factor)
                        # dpi_scale = dpi_now / prev_dpi if prev_dpi else 1
                    # self._font_size = int(self.base_font_size * self.scale_factor)
                        # logger.info(f'check_screen _font_size : {self._font_size}')
                    # reposition_texts()

                    font = self.app.font()
                    self.dpi_scale =  1.5 if self._dpi_now / 96 > 1.5 else self._dpi_now / 96
                    font.setPointSize(int(base_font_size * self.dpi_scale))
                    self.app.setFont(font)
                    # logger.info(f'dpi : {dpi} _dpi_now : {self._dpi_now} fontsize: {font.pointSize()} ratio :  {(self._dpi_now  / 96)}')

            else:
                font = self.app.font()
                self.dpi_scale =  1.5 if self._dpi_now / 96 > 1.5 else self._dpi_now / 96
                font.setPointSize(int(self.base_font_size  * self.dpi_scale))
                self.app.setFont(font)
                logger.info(f'_dpi_now : {self._dpi_now} fontsize: {font.pointSize()} ratio :  {(self._dpi_now  / 96)}')

                # self._font_size = int(self.base_font_size * self.dpi_scale)
                # self._font_size = int(self.base_font_size * self.scale_factor)
                # if self._dpi_now == 96:
                #     # self.dpi_scale = self._dpi_now / (self.scale_factor*96)
                #     logger.info(f'self.dpi_scale init: {self.dpi_scale}')
                #     # if  font_size == self.base_font_size:
                #     #     self._font_size = int(self._font_size / self.scale_factor)
                logger.info(f'self._font_size init: {self._font_size}')
                prev_screen, prev_dpi = screen, self._dpi_now 

        # screen_timer = QtCore.QTimer(win)
        # screen_timer.timeout.connect(check_screen)
        # screen_timer.start(500)

        # 关闭事件

        def on_close(evt):
            timer.stop()
            # 遍历窗口涉及的 concept，只保存自己拥有的概念数据

            for concept_name in concepts:
                base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
                prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)
                if base_data or prev_data:
                    save_concept_pg_data(win, concept_name)  # 已改写为安全单概念保存

            self.save_window_position_qt(win, f"概念分析Top{top_n}")
            self._pg_windows.pop(unique_code, None)
            self._pg_data_hash.pop(code, None)
            evt.accept()


        win.closeEvent = on_close

        
        self._pg_data_hash[code] = data_hash

        self.load_window_position_qt(win, f"概念分析Top{top_n}")

        win.show()


        # --- 初始化多 concept 数据容器 ---
        if not hasattr(win, "_init_prev_concepts_data"):
            win._init_prev_concepts_data = {}  # 每个 concept_name 对应初始数据
        if not hasattr(win, "_prev_concepts_data"):
            win._prev_concepts_data = {}       # 每个 concept_name 对应上次刷新数据

            
        # # --- 全局一次加载当天数据 ---
        # if not hasattr(self, "_concept_data_loaded"):
        #     self._concept_data_loaded = True
        #     # 读取当天所有 concept 数据，一次性加载
        #     all_data = load_all_concepts_pg_data()  # 自定义 NoSQL 函数，返回 dict: concept_name -> (init_data, prev_data)
            
        #     self._global_concept_init_data = {}
        #     self._global_concept_prev_data = {}
        #     for c_name, (init_data, prev_data) in all_data.items():
        #         if init_data:
        #             self._global_concept_init_data[c_name] = {k: np.array(v) for k, v in init_data.items()}
        #         if prev_data:
        #             self._global_concept_prev_data[c_name] = {k: np.array(v) for k, v in prev_data.items()}

        # # --- 窗口初始化各自 concept 数据 ---
        for i, c_name in enumerate(concepts):
            # 初始化 base_data
            if c_name not in win._init_prev_concepts_data:
                base_data = self._global_concept_init_data.get(c_name)
                if base_data is None:
                    # 全局没有数据，初始化基础数据
                    base_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_init_data[c_name] = base_data
                win._init_prev_concepts_data[c_name] = base_data
                # logger.info("[DEBUG] 已初始概念数据(_init_prev_concepts_data)")
            # 初始化 prev_data
            if c_name not in win._prev_concepts_data:
                prev_data = self._global_concept_prev_data.get(c_name)
                if prev_data is None:
                    prev_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_prev_data[c_name] = prev_data
                win._prev_concepts_data[c_name] = prev_data

        # 自动刷新
        timer = QtCore.QTimer(win)
        timer.timeout.connect(lambda: self._refresh_pg_window(code, top_n))

        # 缓存窗口
        self._pg_windows[unique_code] = {
            "win": win, "plot": plot, "bars": bars, "texts": texts, "code" : unique_code,
            "timer": timer, "chk_auto": chk_auto, "spin": spin_interval, "_concepts": concepts
        } 
            # "_scores" : scores,"_avg_percents" :avg_percents ,"_follow_ratios" : follow_ratios

        # if code == "总览" and name == "All":
        chk_auto.setChecked(True)
        timer.start(spin_interval.value() * 1000)
        chk_auto.toggled.connect(lambda state: timer.start(spin_interval.value() * 1000) if state else timer.stop())
        spin_interval.valueChanged.connect(lambda v: timer.start(v * 1000) if chk_auto.isChecked() else None)


    def update_pg_plot(self, w_dict, concepts, scores, avg_percents, follow_ratios):
        """
        更新 PyQtGraph 条形图窗口（NoSQL 多 concept 版本），保证排序对齐：
        1. 每个 concept 独立保存初始分数和上次刷新分数。
        2. 绘制主 BarGraphItem 显示当前分数。
        3. 绘制增量条（相对于初始分数）。
        4. 增量条正增量绿色，负增量红色，文字箭头显示方向。
        5. 支持增量条闪烁。
        6. 自动恢复当天已有数据（NoSQL 存储）。
        """

        # === 🧩 调试信息 ===
        def quick_hash(arr):
            try:
                if isinstance(arr, (list, tuple, np.ndarray)):
                    s = ",".join(map(str, arr[:10]))
                    return hashlib.md5(s.encode()).hexdigest()[:8]
                return str(type(arr))
            except Exception as e:
                return f"err:{e}"

        logger.info(
            f"[DEBUG {datetime.now():%H:%M:%S}] update_pg_plot 调用 "
            f"概念数={len(concepts)} thread={threading.current_thread().name} "
            f"hash_concepts={quick_hash(concepts)} hash_scores={quick_hash(scores)}"
        )

        win = w_dict["win"]
        plot = w_dict["plot"]
        texts = w_dict["texts"]

        # # --- 按 scores 降序排序，保证绘图、文字对齐 ---
        # sort_idx = np.argsort(-np.array(scores))
        # concepts = [concepts[i] for i in sort_idx]
        # scores = np.array(scores)[sort_idx]
        # avg_percents = np.array(avg_percents)[sort_idx]
        # follow_ratios = np.array(follow_ratios)[sort_idx]
        # texts = [texts[i] for i in sort_idx]

        # --- 判断是否需要 9:25 后重置 ---
        # force_reset = False
        # now = datetime.now()
        # if now.time() >= time(9, 25) and getattr(self, "_concept_data_date", None) != now.date():
        #     force_reset = True

        now = datetime.now()
        now_t = int(now.strftime("%H%M"))
        today = now.date()

        force_reset = False

        # 检查是否跨天，跨天就重置阶段标记
        if getattr(self, "_concept_data_date", None) != today:
            win._concept_data_date = today
            win._concept_first_phase_done = False
            win._concept_second_phase_done = False

        # 第一阶段：9:15~9:24触发一次
        if cct.get_trade_date_status() and (915 <= now_t <= 924) and not getattr(self, "_concept_first_phase_done", False):
            win._concept_first_phase_done = True
            force_reset = True
            logger.info(f"{today} 触发 9:15~9:24 第一阶段刷新")

        # 第二阶段：9:25 后触发一次
        elif cct.get_trade_date_status() and (now_t >= 925) and not getattr(self, "_concept_second_phase_done", False):
            win._concept_second_phase_done = True
            force_reset = True
            logger.info(f"{today} 触发 9:25 第二阶段全局重置")

        # --- 初始化多 concept 数据容器 ---
        if not hasattr(win, "_init_prev_concepts_data") or force_reset:
            win._init_prev_concepts_data = {}
        if not hasattr(win, "_prev_concepts_data") or force_reset:
            win._prev_concepts_data = {}

        # --- 全局一次加载当天数据 ---
        if not hasattr(self, "_concept_data_loaded"):
            self._concept_data_loaded = True
            all_data = load_all_concepts_pg_data()  # dict: concept_name -> (init_data, prev_data)
            self._global_concept_init_data = {}
            self._global_concept_prev_data = {}
            for c_name, (init_data, prev_data) in all_data.items():
                if init_data:
                    self._global_concept_init_data[c_name] = {k: np.array(v) for k, v in init_data.items()}
                if prev_data:
                    self._global_concept_prev_data[c_name] = {k: np.array(v) for k, v in prev_data.items()}

        # --- 窗口初始化各自 concept 数据 ---
        for i, c_name in enumerate(concepts):
            if c_name not in win._init_prev_concepts_data:
                base_data = self._global_concept_init_data.get(c_name)
                if base_data is None:
                    base_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_init_data[c_name] = base_data
                win._init_prev_concepts_data[c_name] = base_data

            if c_name not in win._prev_concepts_data:
                prev_data = self._global_concept_prev_data.get(c_name)
                if prev_data is None:
                    prev_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_prev_data[c_name] = prev_data
                win._prev_concepts_data[c_name] = prev_data

        # --- 检查是否需要刷新（数据完全一致时跳过） ---
        data_changed = False
        for i, c_name in enumerate(concepts):
            prev_data = win._prev_concepts_data.get(c_name)
            if prev_data is None:
                data_changed = True
                break
            if (abs(prev_data["avg_percents"][0] - avg_percents[i]) > 1e-6 or
                abs(prev_data["scores"][0] - scores[i]) > 1e-6 or
                abs(prev_data["follow_ratios"][0] - follow_ratios[i]) > 1e-6):
                data_changed = True
                break

        if not data_changed:
            logger.info("[DEBUG] 数据未变化，跳过刷新 ✅")
            return

        y = np.arange(len(concepts))
        max_score = max(scores) if len(scores) > 0 else 1

        # --- 清除旧 BarGraphItem ---
        for item in plot.items[:]:
            if isinstance(item, pg.BarGraphItem):
                plot.removeItem(item)

        # --- 按新顺序生成 y 轴 ---
        y = np.arange(len(concepts))
        max_score = max(scores) if len(scores) > 0 else 1

        # --- 主 BarGraphItem（使用排序后的 scores 和 y） ---
        color_map = pg.colormap.get('CET-R1')
        brushes = [pg.mkBrush(color_map.map(s)) for s in scores]
        main_bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
        plot.addItem(main_bars)
        w_dict["bars"] = main_bars

        # # --- 清除所有 TextItem ---
        # for item in plot.items[:]:
        #     if isinstance(item, pg.TextItem):
        #         plot.removeItem(item)

        # # --- 创建新的 TextItem ---
        # texts = []
        # max_score = max(scores.max(), 1)
        # for i, (avg, score) in enumerate(zip(avg_percents, scores)):
        #     # text = pg.TextItem(f"avg:{avg:.2f}%\nscore:{score:.2f}", anchor=(0, 0.5))
        #     text = pg.TextItem(f"score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
        #     # text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
        #     text.setPos(score + 0.03 * max_score, y[i])
        #     plot.addItem(text)
        #     texts.append(text)
        #     logger.info(f"update[DEBUG] : avg={avg:.2f}, score={score:.2f}")

        # # --- 更新左轴刻度 ---
        # plot.getAxis('left').setTicks([list(zip(y, concepts))])

        # --- 绘制增量条 ---
        delta_bars_list = []
        for i, c_name in enumerate(concepts):
            score = scores[i]
            base_score = win._init_prev_concepts_data[c_name]["scores"][0]
            delta = score - base_score

            if abs(delta) < 1e-6:
                delta_bars_list.append(None)
                continue

            color = (0, 255, 0, 150) if delta > 0 else (255, 0, 0, 150)
            x0 = base_score if delta > 0 else score
            bar = pg.BarGraphItem(x0=x0, y=[y[i]], height=0.6, width=[abs(delta)], brushes=[pg.mkBrush(color)])
            plot.addItem(bar)
            delta_bars_list.append(bar)
        w_dict["delta_bars"] = delta_bars_list
        # logger.info(f'texts: {texts}')
        # --- 更新文字显示（顺序保持和 y 对齐） ---
        app_font = QtWidgets.QApplication.font()
        font_family = app_font.family()
        for i, text in enumerate(texts):
            score = scores[i]
            delta = score - win._init_prev_concepts_data[concepts[i]]["scores"][0]

            if delta > 0:
                arrow = "↑"
                color = "green"
            elif delta < 0:
                arrow = "↓"
                color = "red"
            else:
                arrow = "→"
                color = "gray"

            # text.setText(f"{arrow} {delta} {score:.2f} \n ({avg_percents[i]:.2f}%)")
            # text.setText(f"{arrow} {delta} {score:.2f} \n ({avg_percents[i]:.2f}%)")
            text.setText(f"{arrow}{delta:.1f} score:{score:.2f}\navg:{avg_percents[i]:.2f}%")
            #     text = pg.TextItem(f"score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
            text.setColor(QtGui.QColor(color))
            # text.setFont(QtGui.QFont(font_family, self._font_size))
            # text.setPos((score + 0.03 * max_score) * self.dpi_scale, y[i] * self.dpi_scale)
            text.setPos(score + 0.03 * max_score, y[i])
            text.setAnchor((0, 0.5))

        plot.getAxis('left').setTicks([list(zip(y, concepts))])



        # texts = []
        # max_score = max(scores.max(), 1)
        # for i, (avg, score) in enumerate(zip(avg_percents, scores)):
        #     text = pg.TextItem(f"avg:{avg:.2f}%\nscore:{score:.2f}", anchor=(0, 0.5))
        #     text = pg.TextItem(f"score:{score:.2f}\navg:{avg:.2f}%", anchor=(0, 0.5))
        #     # text.setFont(QtGui.QFont("Microsoft YaHei", font_size))
        #     text.setPos(score + 0.03 * max_score, y[i])
        #     plot.addItem(text)
        #     texts.append(text)
        #     logger.info(f"[DEBUG] : avg={avg:.2f}, score={score:.2f}")

        # plot.getAxis('left').setTicks([list(zip(y, concepts))])

        plot._data_ref["concepts"] = concepts
        plot._data_ref["scores"] = scores
        plot._data_ref["avg_percents"] = avg_percents
        plot._data_ref["follow_ratios"] = follow_ratios
        plot._data_ref["bars"] = main_bars
        plot._data_ref["brushes"] = brushes


        # --- 保存当前刷新数据 ---
        for i, c_name in enumerate(concepts):
            win._prev_concepts_data[c_name] = {
                "concepts": [c_name],
                "avg_percents": np.array([avg_percents[i]]),
                "scores": np.array([scores[i]]),
                "follow_ratios": np.array([follow_ratios[i]])
            }

        # --- 增量条闪烁 ---
        if not hasattr(win, "_flash_timer"):
            win._flash_state = True
            win._flash_timer = QtCore.QTimer(win)

            def flash_delta():
                for bar in w_dict["delta_bars"]:
                    if bar is not None:
                        bar.setVisible(win._flash_state)
                win._flash_state = not win._flash_state

            win._flash_timer.timeout.connect(flash_delta)
            win._flash_timer.start(30000)  # 30 秒闪烁一次


    # def update_pg_plot_no_sql(self, w_dict, concepts, scores, avg_percents, follow_ratios):
    #     """
    #     更新 PyQtGraph 条形图窗口：
    #     1. 绘制主 BarGraphItem 显示当前分数。
    #     2. 绘制增量条，比较当前分数与初始分数 (_init_prev_concepts_data)。
    #     3. 增量条正增量绿色，负增量红色。
    #     4. 条形闪烁，文字箭头显示增减方向。
    #     """

    #     win = w_dict["win"]
    #     plot = w_dict["plot"]
    #     texts = w_dict["texts"]

    #     # --- 初始化：保存初始参考数据 (_init_prev_concepts_data) ---
    #     # 用于计算每次刷新后的增量
    #     if not hasattr(win, "_init_prev_concepts_data"):
    #         win._init_prev_concepts_data = {
    #             "concepts":concepts,
    #             "avg_percents": np.array(avg_percents, copy=True),
    #             "scores": np.array(scores, copy=True),
    #             "follow_ratios": np.array(follow_ratios, copy=True)
    #         }
    #         logger.info("[DEBUG] 已保存初始概念数据(_init_prev_concepts_data)")

    #     # --- 当前数据与上次刷新数据 (_prev_concepts_data) ---
    #     # 用于比较上一次刷新后的变化（非初始参考）
    #     if not hasattr(win, "_prev_concepts_data"):
    #         win._prev_concepts_data = {
    #             "concepts":concepts,
    #             "avg_percents": np.zeros(len(avg_percents)),
    #             "scores": np.zeros(len(scores)),
    #             "follow_ratios": np.zeros(len(follow_ratios))
    #         }

    #     prev_data = win._prev_concepts_data
    #     base_data = win._init_prev_concepts_data

    #     y = np.arange(len(concepts))
    #     max_score = max(scores) if len(scores) > 0 else 1

    #     # --- 清除旧 BarGraphItem ---
    #     for item in plot.items[:]:
    #         if isinstance(item, pg.BarGraphItem):
    #             plot.removeItem(item)

    #     # --- 主 BarGraphItem ---
    #     # 显示当前分数
    #     color_map = pg.colormap.get('CET-R1')
    #     brushes = [pg.mkBrush(color_map.map(s)) for s in scores]
    #     main_bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
    #     plot.addItem(main_bars)
    #     w_dict["bars"] = main_bars  # 保存引用

    #     # --- 计算相对初始的变化（增量 delta_from_init） ---
    #     # 用于绘制正负增量条
    #     delta_from_init = np.array(scores) - base_data["scores"]

    #     # --- 绘制增量条 ---
    #     delta_bars_list = []
    #     for i, d in enumerate(delta_from_init):
    #         if abs(d) < 1e-6:  # 无变化则跳过
    #             delta_bars_list.append(None)
    #             continue
    #         # 正增量绿色，负增量红色，半透明
    #         color = (0, 255, 0, 150) if d > 0 else (255, 0, 0, 150)
    #         # x0 起点：正增量从初始分数开始，负增量从当前分数开始
    #         x0 = base_data["scores"][i] if d > 0 else scores[i]
    #         bar = pg.BarGraphItem(x0=x0, y=[y[i]], height=0.6, width=[abs(d)], brushes=[pg.mkBrush(color)])
    #         plot.addItem(bar)
    #         delta_bars_list.append(bar)
    #     w_dict["delta_bars"] = delta_bars_list  # 保存引用以便闪烁

    #     # --- 更新文字显示 ---
    #     app_font = QtWidgets.QApplication.font()
    #     font_family = app_font.family()
    #     for i, text in enumerate(texts):
    #         if i >= len(concepts):
    #             continue
    #         avg = avg_percents[i]
    #         score = scores[i]
    #         diff_score = delta_from_init[i]

    #         # 箭头和文字颜色表示增减方向
    #         if diff_score > 0:
    #             arrow = "↑"
    #             color = "green"
    #         elif diff_score < 0:
    #             arrow = "↓"
    #             color = "red"
    #         else:
    #             arrow = "→"
    #             color = "gray"

    #         text.setText(f"{arrow}{score:.2f} ({avg:.2f}%)")
    #         text.setColor(QtGui.QColor(color))
    #         text.setFont(QtGui.QFont(font_family, self._font_size))
    #         text.setPos((scores[i] + 0.03 * max_score) * self.dpi_scale, y[i] * self.dpi_scale)
    #         text.setAnchor((0, 0.5))  # 垂直居中

        # # --- 保存当前刷新数据 (_prev_concepts_data) ---
        # win._prev_concepts_data = {
        #     "concepts":concepts,
        #     "avg_percents": np.array(avg_percents, copy=True),
        #     "scores": np.array(scores, copy=True),
        #     "follow_ratios": np.array(follow_ratios, copy=True)
        # }

    #     # --- 增量条闪烁定时器 ---
    #     if not hasattr(win, "_flash_timer"):
    #         win._flash_state = True  # 控制可见性状态
    #         win._flash_timer = QtCore.QTimer(win)

    #         def flash_delta():
    #             # 切换增量条显示状态
    #             for bar in w_dict["delta_bars"]:
    #                 if bar is not None:
    #                     bar.setVisible(win._flash_state)
    #             win._flash_state = not win._flash_state

    #         win._flash_timer.timeout.connect(flash_delta)
    #         win._flash_timer.start(30000)  # 每10秒闪烁一次



    # --- 定时刷新 ---
    def _refresh_pg_window(self, code, top_n):
        unique_code = f"{code or ''}_{top_n or ''}"
        if unique_code not in self._pg_windows:
            return
        if not cct.get_work_time():  # 仅工作时间刷新
            return

        logger.info(f'unique_code : {unique_code}')
        w_dict = self._pg_windows[unique_code]
        win = w_dict["win"]

        # --- 获取最新概念数据 ---
        if code == "总览":
            tcode, _ = self.get_stock_code_none()
            top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n)
            unique_code = f"{code or ''}_{top_n or ''}"
            # logger.info(f'_refresh_pg_window concepts : {top_concepts} unique_code: {unique_code} ')
        else:
            top_concepts = self.get_following_concepts_by_correlation(code, top_n=top_n)

        if not top_concepts:
            logger.info(f"[Auto] 无法刷新 {code} 数据为空")
            return

        # --- 对概念按 score 降序排序 ---
        top_concepts_sorted = sorted(top_concepts, key=lambda x: x[1], reverse=True)

        concepts = [c[0] for c in top_concepts_sorted]
        scores = np.array([c[1] for c in top_concepts_sorted])
        avg_percents = np.array([c[2] for c in top_concepts_sorted])
        follow_ratios = np.array([c[3] for c in top_concepts_sorted])

        # --- 判断概念顺序是否变化 ---
        old_concepts = w_dict.get("_concepts", [])
        concept_changed = old_concepts != concepts
        # if concept_changed:
        #     logger.info(f"[DEBUG] 概念顺序变化，会重建文字:old_concepts {old_concepts} → concepts:{concepts}")
        #     # w_dict["texts"] = []  # 强制重建文字
        # else:
        #     logger.info(f"[DEBUG] 概念顺序未变，仅更新文字内容")

        # --- 调试输出 ---
        # logger.info(f'_refresh_pg_window top_concepts_sorted : {top_concepts_sorted} unique_code: {unique_code} ')
        logger.info(f'更新图形: {unique_code} : {concepts}')
        # --- 更新图形 ---
        self.update_pg_plot(w_dict, concepts, scores, avg_percents, follow_ratios)

        logger.info(f"[Auto] 已自动刷新 {code}")


    # def plot_following_concepts_mp(self, code=None, top_n=10):
    #     if not hasattr(self, "_figs_opened"):
    #         self._figs_opened = {}      # 保存 Figure 对象
    #         self._figs_data_hash = {}   # 保存数据摘要

    #     # 设置中文字体
    #     plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    #     plt.rcParams['axes.unicode_minus'] = False
    #     if code is None:
    #         tcode, percent = self.get_stock_code_none()
    #         logger.info(f'tcode: {tcode} percent :{percent}')
    #         top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n)
    #     else:
    #         top_concepts = self.get_following_concepts_by_correlation(code, top_n=top_n)

    #     if not top_concepts:
    #         logger.info("未找到相关概念")
    #         return

    #     concepts = [c[0] for c in top_concepts]
    #     scores = [c[1] for c in top_concepts]
    #     avg_percents = [c[2] for c in top_concepts]
    #     follow_ratios = [c[3] for c in top_concepts]

    #     # --- 生成摘要，只检查这四个列表是否一致 ---

    #     data_hash = tuple(concepts[:3])

    #     logger.info(f'data_hash : {data_hash}')
    #     # 如果数据完全一样且已有窗口，则不重复打开
    #     to_delete = []
    #     # --- 检查是否已有相同数据的窗口 ---
    #     for key, hash_val in list(self._figs_data_hash.items()):
    #         logger.info(f'key : {key} hash_val : {hash_val}')

    #         fig = self._figs_opened.get(key, None)

    #         # 如果图表已经被关闭或不存在，删除字典记录
    #         if fig is None or not plt.fignum_exists(fig.number):
    #             logger.info(f"[Info] 图表 {key} 已关闭，清理记录")
    #             self._figs_opened.pop(key, None)
    #             self._figs_data_hash.pop(key, None)
    #             continue

    #         # 如果数据完全一样，则不重复打开
    #         if hash_val == data_hash:
    #             try:
    #                 fig.show()
    #                 manager = plt.get_current_fig_manager()
    #                 try:
    #                     manager.window.attributes('-topmost', 1)
    #                     manager.window.attributes('-topmost', 0)
    #                 except Exception:
    #                     pass
    #             except Exception:
    #                 # 图表异常或已关闭，再清理记录
    #                 self._figs_opened.pop(key, None)
    #                 self._figs_data_hash.pop(key, None)
    #             else:
    #                 logger.info("数据与已有窗口相同，不重复打开。")
    #                 return


    #     for k in to_delete:
    #         del self._figs_opened[key]
    #         del self._figs_data_hash[k]

    #     colors = [plt.cm.Reds(r) for r in follow_ratios]
    #     if code is None:
    #         code = '总览'
    #         name = 'All'
    #     else:
    #         name = self.df_all.loc[code]['name']
    #     fig, ax = plt.subplots(figsize=(6, 4))
    #     bars = ax.barh(concepts, scores, color=colors)
    #     ax.set_xlabel('跟随指数 (score)')
    #     ax.set_title(f'{code} {name} 今日可能跟随上涨概念前 {top_n}')
    #     ax.invert_yaxis()

    #     for bar, avg, ratio in zip(bars, avg_percents, follow_ratios):
    #         width = bar.get_width()
    #         ax.text(width + 0.01, bar.get_y() + bar.get_height()/2,
    #                 f'avg: {avg:.2f}%, ratio: {ratio:.2f}', va='center')

    #     # ✅ 点击事件
    #     def on_click(event):
    #         if event.inaxes != ax:
    #             return
    #         for i, bar in enumerate(bars):
    #             if bar.contains(event)[0]:
    #                 concept = concepts[i]
    #                 avgp = avg_percents[i]
    #                 ratio = follow_ratios[i]
    #                 score = scores[i]

    #                 msg = (f"概念: {concept}\n"
    #                        f"平均涨幅: {avgp:.2f}%\n"
    #                        f"跟随指数: {ratio:.2f}\n"
    #                        f"综合得分: {score:.3f}")
    #                 logger.info(f'[Click] {msg}')
    #                 self._call_concept_top10_win(code, concept)
    #                 break

    #     fig.canvas.mpl_connect("button_press_event", on_click)

    #     # 键盘事件
    #     def on_key_press(event):
    #         if event.key == "r":
    #             logger.info(f"[Key] 刷新 {code} 概念分析")
    #             plt.close(fig)
    #             self.plot_following_concepts_pg(code, top_n=top_n)
    #         elif event.key == "q":
    #             logger.info("[Key] 退出图表")
    #             plt.close(fig)
    #         elif event.key == "n":
    #             logger.info("[Key] 下一个概念")
    #             if concepts:
    #                 self._call_concept_top10_win(code, concepts[0])
    #         elif event.key == "escape":
    #             logger.info("[Key] ESC 按下，关闭图表并退出")
    #             plt.close(fig)
    #             try:
    #                 del self._figs_opened[code]
    #                 del self._figs_data_hash[code]
    #             except KeyError:
    #                 pass
    #             # try:
    #             #     # 如果希望主窗口也退出
    #             #     import tkinter as tk
    #             #     root = tk._default_root
    #             #     if root:
    #             #         root.quit()
    #             # except Exception:
    #             #     pass

    #     fig.canvas.mpl_connect("key_press_event", on_key_press)
    #     def on_close(event):
    #         # fig 被关闭时自动删除记录
    #         try:
    #             del self._figs_opened[code]
    #         except KeyError:
    #             pass
    #         try:
    #             del self._figs_data_hash[code]
    #         except KeyError:
    #             pass

    #     fig.canvas.mpl_connect('close_event', on_close)
    #     # --- 记录当前打开的窗口 ---
    #     self._figs_opened[code] = fig
    #     self._figs_data_hash[code] = data_hash

    #     plt.tight_layout()
    #     # plt.show()
    #     fig.show()
    #     plt.pause(0.001)

    def _call_concept_top10_win(self,code,concept_name):
        # 打开或复用 Top10 窗口
        if code is None:
            return
        self.show_concept_top10_window(concept_name,code=code,bring_monitor_status=False)
        if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
            win = self._concept_top10_win

            # --- 更新标题 ---
            win.title(f"{concept_name} 概念前10放量上涨股")

            # --- 检查窗口状态 ---
            try:
                state = win.state()

                # 最小化或被主窗口遮挡
                if state == "iconic" or self.is_window_covered_by_main(win):
                    win.deiconify()      # 恢复窗口
                    win.lift()           # 提前显示
                    win.focus_force()    # 聚焦
                    win.attributes("-topmost", True)
                    win.after(100, lambda: win.attributes("-topmost", False))
                else:
                    # 没被遮挡但未聚焦
                    if not win.focus_displayof():
                        win.lift()
                        win.focus_force()

            except Exception as e:
                logger.info(f"窗口状态检查失败： {e}")

            # --- 恢复 Canvas 滚动位置 ---
            if hasattr(win, "_canvas_top10"):
                canvas = win._canvas_top10
                yview = canvas.yview()
                canvas.focus_set()
                canvas.yview_moveto(yview[0])
                # --- 关键：强制聚焦并启用键盘捕获 ---
                # try:
                #     # 1. 激活窗口
                #     win.focus_force()
                #     # 2. 稍微延迟再聚焦 canvas，防止系统阻止焦点抢占
                #     win.after(100, lambda: canvas.focus_set())
                # except Exception as e:
                #     logger.info("焦点设置失败：", e)

    def _on_label_double_click(self, code, idx):
        """
        双击股票标签时，显示该股票所属概念详情。
        如果 _label_widgets 不存在或 concept_name 获取失败，
        则自动使用 code 计算该股票所属强势概念并显示详情。
        """
        try:

            # ---------------- 原逻辑 ----------------
            if hasattr(self, "_label_widgets"):
                try:
                    concept_name = getattr(self._label_widgets[idx], "_concept", None)
                except Exception:
                    concept_name = None

            # ---------------- 回退逻辑 ----------------
            if not concept_name:
                # logger.info(f"[Info] 未从 _label_widgets 获取到概念，尝试通过 {code} 自动识别强势概念。")
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"自动识别强势概念：{concept_name}")
                    else:
                        messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                        return
                except Exception as e:
                    logger.info(f"[Error] 回退获取概念失败：{e}")
                    traceback.print_exc()
                    messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                    return

            # ---------------- 绘图逻辑 ----------------
            self.plot_following_concepts_pg(code,top_n=1)
            # ---------------- 打开/复用 Top10 窗口 ----------------
            self.show_concept_top10_window(concept_name,code=code)

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 更新标题 ---
                win.title(f"{concept_name} 概念前10放量上涨股")

                # --- 检查窗口状态 ---
                try:
                    state = win.state()

                    if state == "iconic" or self.is_window_covered_by_main(win):
                        win.deiconify()
                        win.lift()
                        win.focus_force()
                        win.attributes("-topmost", True)
                        win.after(100, lambda: win.attributes("-topmost", False))
                    else:
                        if not win.focus_displayof():
                            win.lift()
                            win.focus_force()

                except Exception as e:
                    logger.info(f"窗口状态检查失败： {e}")

                # --- 恢复 Canvas 滚动位置 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

        except Exception as e:
            logger.info(f"获取概念详情失败：{e}")
            traceback.print_exc()


    def _on_label_double_click_debug(self, code, idx):
        """
        双击股票标签时，显示该股票所属概念详情。
        如果 _label_widgets 不存在或 concept_name 获取失败，
        则自动使用 code 计算该股票所属强势概念并显示详情。
        """
        try:
            t0 = time.time()
            concept_name = None

            # ---------------- 原逻辑 ----------------
            if hasattr(self, "_label_widgets"):
                t1 = time.time()
                logger.info(f"[DEBUG] 开始访问 _label_widgets，len={len(self._label_widgets)}")
                try:
                    concept_name = getattr(self._label_widgets[idx], "_concept", None)
                except Exception as e:
                    logger.info(f"[DEBUG] 获取 _concept 失败 idx={idx}: {e}")
                t2 = time.time()
                logger.info(f"[DEBUG] _label_widgets 访问耗时: {(t2-t1)*1000:.2f} ms")

            # ---------------- 回退逻辑 ----------------
            if not concept_name:
                t3 = time.time()
                logger.info(f"[DEBUG] 回退逻辑开始，通过 code={code} 获取概念")
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"[DEBUG] 自动识别强势概念：{concept_name}")
                    else:
                        messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                        return
                except Exception as e:
                    logger.info(f"[ERROR] 回退获取概念失败：{e}")
                    traceback.print_exc()
                    messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                    return
                t4 = time.time()
                logger.info(f"[DEBUG] 回退逻辑耗时: {(t4-t3)*1000:.2f} ms")

            # ---------------- 绘图逻辑 ----------------
            t5 = time.time()
            self.plot_following_concepts_pg(code, top_n=1)
            t6 = time.time()
            logger.info(f"[DEBUG] 绘图耗时: {(t6-t5)*1000:.2f} ms")

            # ---------------- 打开/复用 Top10 窗口 ----------------
            t7 = time.time()
            self.show_concept_top10_window(concept_name,code=code)
            t8 = time.time()
            logger.info(f"[DEBUG] show_concept_top10_window 耗时: {(t8-t7)*1000:.2f} ms")

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 更新标题 ---
                win.title(f"{concept_name} 概念前10放量上涨股")

                # --- 检查窗口状态 ---
                try:
                    state = win.state()
                    if state == "iconic" or self.is_window_covered_by_main(win):
                        win.deiconify()
                        win.lift()
                        win.focus_force()
                        win.attributes("-topmost", True)
                        win.after(100, lambda: win.attributes("-topmost", False))
                    else:
                        if not win.focus_displayof():
                            win.lift()
                            win.focus_force()
                except Exception as e:
                    logger.info(f"窗口状态检查失败：{e}")

                # --- 恢复 Canvas 滚动位置 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

            t9 = time.time()
            logger.info(f"[DEBUG] _on_label_double_click 总耗时: {(t9-t0)*1000:.2f} ms")

        except Exception as e:
            logger.info(f"获取概念详情失败：{e}")
            traceback.print_exc()



    def _on_label_double_click_copy(self, code, idx):
        """
        双击股票标签时，显示该股票的概念详情
        """
        try:
            # 假设 self.get_concept_by_code(code) 可返回该股票所属概念列表

            # --- 调用 on_code_click ---
            concepts = getattr(self._label_widgets[idx], "_concept", None)
            # if concepts:
            #     self.on_code_click(code)
            if not concepts:
                messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                return

            # text = "\n".join(concepts)
            text = f'category.str.contains("{concepts.strip()}")'
            pyperclip.copy(text)
            logger.info(f"已复制: {text}")
            # messagebox.showinfo("概念详情", f"{code} 所属概念：\n{text}")
        except Exception as e:
            logger.info(f"获取概念详情失败：{e}")


    def _on_label_right_click(self,code ,idx):
        self._update_selection(idx)
        stock_code = code
        pyperclip.copy(code)
        if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
            # 如果发送成功，更新状态标签
            self.status_var2.set(f"发送成功: {stock_code}")
        else:
            # 如果发送失败，更新状态标签
            self.status_var2.set(f"发送失败: {stock_code}")

    def _on_key(self, event):
        """键盘上下/分页滚动"""
        if not self._label_widgets:
            return
        idx = self._selected_index
        if event.keysym == "Up":
            idx = max(0, idx - 1)
        elif event.keysym == "Down":
            idx = min(len(self._label_widgets) - 1, idx + 1)
        elif event.keysym == "Prior":  # PageUp
            idx = max(0, idx - 5)
        elif event.keysym == "Next":   # PageDown
            idx = min(len(self._label_widgets) - 1, idx + 5)
        self._update_selection(idx)
        # --- 调用 on_code_click ---
        code = getattr(self._label_widgets[idx], "_code", None)
        if code:
            self.on_code_click(code)

    def auto_refresh_detail_window(self):
        # ... 逻辑更新 _last_categories / _last_cat_dict ...
        if getattr(self, "_concept_win", None) and self._concept_win.winfo_exists():
            self.update_concept_detail_content()


    def open_stock_detail(self, code):
        """点击概念窗口中股票代码弹出详情"""
        win = tk.Toplevel(self)
        win.title(f"股票详情 - {code}")
        win.geometry("400x300")
        tk.Label(win, text=f"正在加载个股 {code} ...", font=self.default_font_bold).pack(pady=10)

        # 如果有 df_filtered 数据，可以显示详细行情
        if hasattr(self, "_last_cat_dict"):
            for c, lst in self._last_cat_dict.items():
                for row_code, name in lst:
                    if row_code == code:
                        tk.Label(win, text=f"{row_code} {name}", font=self.default_font).pack(anchor="w", padx=10)
                        # 可以加更多字段，如 trade、涨幅等

    def apply_search(self):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        if not val1 and not val2:
            self.status_var.set("搜索框为空")
            return

        self.query_manager.clear_hits()
        query = (f"({val1}) and ({val2})" if val1 and val2 else val1 or val2)
        self._last_value = query

        try:
            # 🔹 同步两个搜索框的历史，不依赖 current_key
            if val1:
                self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")
            if val2:
                self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")
        except Exception as ex:
            logger.exception("更新搜索历史时出错: %s", ex)

        # ================= 数据为空检查 =================
        if self.df_all.empty:
            self.status_var.set("当前数据为空")
            return

        # # === 测试 ===
        # expr = "(topR > 0 or (per1d > 1) and (per2d > 0)"
        # result = ensure_parentheses_balanced(expr)
        # logger.info("原始:", expr)
        # logger.info("修正:", result)


        # ====== 条件清理 ======
        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2️⃣ 替换掉原 query 中的这些部分
        for bracket in bracket_patterns:
            query = query.replace(f'and {bracket}', '')

        conditions = [c.strip() for c in query.split('and')]
        # logger.info(f'conditions {conditions}')
        valid_conditions = []
        removed_conditions = []
        # logger.info(f'conditions: {conditions} bracket_patterns : {bracket_patterns}')
        for cond in conditions:
            cond_clean = cond.lstrip('(').rstrip(')')
            # cond_clean = ensure_parentheses_balanced(cond_clean)
            if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 or cond.find('or') >= 0:
                if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                    ensure_cond = ensure_parentheses_balanced(cond)
                    # logger.info(f'cond : {cond} ensure_cond : {ensure_cond}')
                    valid_conditions.append(ensure_cond)
                    continue

            # 提取条件中的列名
            cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

            # 所有列都必须存在才保留
            if all(col in self.df_all.columns for col in cols_in_cond):
                valid_conditions.append(cond_clean)
            else:
                removed_conditions.append(cond_clean)
                # logger.info(f"剔除不存在的列条件: {cond_clean}")

        # 去掉在 bracket_patterns 中出现的内容
        removed_conditions = [
            cond for cond in removed_conditions
            if not any(bp.strip('() ').strip() == cond.strip() for bp in bracket_patterns)
        ]

        # 打印剔除条件列表
        if removed_conditions:
            # # logger.info(f"剔除不存在的列条件: {removed_conditions}")
            unique_conditions = tuple(sorted(set(removed_conditions)))
            # 初始化缓存
            if not hasattr(self, "_printed_removed_conditions"):
                self._printed_removed_conditions = set()
            # 只打印新的
            if unique_conditions not in self._printed_removed_conditions:
                logger.info(f"剔除不存在的列条件: {unique_conditions}")
                self._printed_removed_conditions.add(unique_conditions)

        if not valid_conditions:
            self.status_var.set("没有可用的查询条件")
            return
        # logger.info(f'valid_conditions : {valid_conditions}')
        # ====== 拼接 final_query 并检查括号 ======
        final_query = ' and '.join(f"({c})" for c in valid_conditions)
        # logger.info(f'final_query : {final_query}')
        if bracket_patterns:
            final_query += ' and ' + ' and '.join(bracket_patterns)
        # logger.info(f'final_query : {final_query}')
        left_count = final_query.count("(")
        right_count = final_query.count(")")
        if left_count != right_count:
            if left_count > right_count:
                final_query += ")" * (left_count - right_count)
            elif right_count > left_count:
                final_query = "(" * (right_count - left_count) + final_query

        # ====== 决定 engine ======
        df_filtered = pd.DataFrame()
        query_engine = 'numexpr'
        if any('index.' in c.lower() for c in valid_conditions):
            query_engine = 'python'
        # ====== 数据过滤 ======
        try:

            if val1.count('or') > 0 and val1.count('(') > 0:
                if val2 :
                    query_search = f"({val1}) and {val2}"
                    logger.info(f'query: {query_search} ')

                else:
                    query_search = f"({val1})"
                    logger.info(f'query: {query_search} ')
                # if removed_conditions:
                #     query_search = remove_invalid_conditions(query_search, removed_conditions,showdebug=False)
                #     logger.info(f'removed_query_search: {query_search} removed_conditions:{removed_conditions}')

                # logger.info(f'apply_search {query_search.count("or")} or query: {query_search} ')
                df_filtered = self.df_all.query(query_search, engine=query_engine)
                self.refresh_tree(df_filtered)
                self.status_var2.set('')
                self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {val1} and {val2}")
            else:
                # 检查 category 列是否存在
                if 'category' in self.df_all.columns:
                    # 强制转换为字符串，避免 str.contains 报错
                    if not pd.api.types.is_string_dtype(self.df_all['category']):
                        self.df_all['category'] = self.df_all['category'].astype(str).str.strip()
                        # self.df_all['category'] = self.df_all['category'].astype(str)
                        # 可选：去掉前后空格
                        # self.df_all['category'] = self.df_all['category'].str.strip()
                df_filtered = self.df_all.query(final_query, engine=query_engine)

                # 假设 df 是你提供的涨幅榜表格
                # result = counterCategory(df_filtered, 'category', limit=50, table=True)
                # self._Categoryresult = result
                # self.query_manager.entry_query.set(self._Categoryresult)
                self.after(500,self.refresh_tree(df_filtered))
                # 打印剔除条件列表
                if removed_conditions:
                    # logger.info(f"[剔除的条件列表] {removed_conditions}")
                    # 显示到状态栏
                    self.status_var2.set(f"已剔除条件: {', '.join(removed_conditions)}")
                    self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
                else:
                    self.status_var2.set('')
                    self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
                logger.info(f'final_query: {final_query}')
        except Exception as e:
            traceback.print_exc()
            logger.error(f"query_check: {([c for c in self.df_all.columns if not c.isidentifier()])}")
            logger.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")
        if df_filtered.empty:
            return
        self.on_test_code()
        self.auto_refresh_detail_window()
        self.update_category_result(df_filtered)
        if not hasattr(self, "_start_init_show_concept_detail_window"):
            # 已经创建过，直接显示
            # self.kline_monitor.deiconify()
            # self.kline_monitor.lift()
            # self.kline_monitor.focus_force()
            self.show_concept_detail_window()
            self._start_init_show_concept_detail_window = True

    def on_test_code(self,onclick=False):
        # if self.query_manager.current_key == 'history2':
        #     return
        code = self.query_manager.entry_query.get().strip()
        result = getattr(self, "_Categoryresult", "")
        # if not code:
        #     toast_message(self, "请输入股票代码")
        #     return
        # 判断是否为 6 位数字
        # if not (code.isdigit() and len(code) == 6):

        if code and code == result:
            df_code = self.df_all
        elif code and not (code.isdigit() and len(code) == 6):
            # toast_message(self, "请输入6位数字股票代码")
            # return
            df_code = self.df_all
        elif code and code.isdigit() and len(code) == 6:
            # 初始化上次选中的 code
            if not hasattr(self, "_select_on_test_code"):
                self._select_on_test_code = None

            # 判断是否为新的 code
            if self._select_on_test_code != code:
                # 更新缓存，并筛选对应行
                self._select_on_test_code = code
                df_code = self.df_all.loc[self.df_all.index == code]
            else:
                if onclick:
                    df_code = self.df_all.loc[self.df_all.index == code]
                    self.tree_scroll_to_code(code)
                    if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                        self.kline_monitor.tree_scroll_to_code_kline(code)
                # 连续选择相同 code，则显示全部
                else:
                    df_code = self.df_all
        else:
            df_code = self.df_all

        results = self.query_manager.test_code(df_code)

        # 更新当前历史的命中结果
        for i, r in enumerate(results):
            if i < len(self.query_manager.current_history):
                self.query_manager.current_history[i]["hit"] = r["hit"]

        self.query_manager.refresh_tree()
        # toast_message(self, f"{code} 测试完成，共 {len(results)} 条规则")



    def clean_search(self, which):
        """清空指定搜索框内容"""
        if which == 1:
            self.search_var1.set("")
        else:
            # if len(self.search_var2.get()) == 6:
            self.search_var2.set("")

        self.select_code = None
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.refresh_tree(self.df_all)
        resample = self.resample_combo.get()
        # self.status_var.set(f"搜索框 {which} 已清空")
        # self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")
        self.query_manager.entry_query.delete(0, tk.END)

    def delete_search_history(self, which, entry=None):
        """
        删除指定搜索框的历史条目
        which = 1 -> 顶部搜索框
        which = 2 -> 底部搜索框
        entry: 指定要删除的条目，如果为空则用搜索框当前内容
        """
        if which == 1:
            history = self.search_history1
            combo = self.search_combo1
            var = self.search_var1
            key = "history1"
        elif which == 2:
            history = self.search_history2
            combo = self.search_combo2
            var = self.search_var2
            key = "history2"

        target = entry or var.get().strip()
        if not target:
            self.status_var.set(f"搜索框 {which} 内容为空，无可删除项")
            return

        if target in history:
            # 从主窗口 history 移除
            history.remove(target)
            combo['values'] = history
            if var.get() == target:
                var.set("")

            # 从 QueryHistoryManager 移除（保留 note/starred）
            manager_history = getattr(self.query_manager, key, [])
            manager_history = [r for r in manager_history if r["query"] != target]
            setattr(self.query_manager, key, manager_history)

            # 如果当前视图正在显示这个历史，刷新
            if self.query_manager.current_key == key:
                self.query_manager.current_history = manager_history
                self.query_manager.refresh_tree()

            # 保存
            # self.query_manager.save_search_history()

            self.status_var.set(f"搜索框 {which} 已删除历史: {target}")
        else:
            self.status_var.set(f"搜索框 {which} 历史中没有: {target}")

    def KLineMonitor_init(self):
        # logger.info("启动K线监控...")

        # # 仅初始化一次监控对象
        # if not hasattr(self, "kline_monitor"):
        #     self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=10)
        # else:
        #     logger.info("监控已在运行中。")
        logger.info("启动K线监控...")
        if not hasattr(self, "kline_monitor") or not getattr(self.kline_monitor, "winfo_exists", lambda: False)():
            self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=duration_sleep_time,history3=lambda: self.search_history3)
            # self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=15,history3=self.search_history3)
        else:
            logger.info("监控已在运行中。")
            # 前置窗口
            # self.kline_monitor.lift()                # 提升窗口层级
            # self.kline_monitor.attributes('-topmost', True)  # 暂时置顶
            # self.kline_monitor.focus_force()         # 获取焦点
            # self.kline_monitor.attributes('-topmost', False) # 取消置顶

            if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                # 已经创建过，直接显示
                self.kline_monitor.deiconify()
                self.kline_monitor.lift()
                self.kline_monitor.focus_force()

        # 在这里可以启动你的实时监控逻辑，例如:
        # 1. 调用获取数据的线程
        # 2. 计算MACD/BOLL/EMA等指标
        # 3. 输出买卖点提示、强弱信号
        # 4. 定期刷新UI 或 控制台输出
    def sort_column_archive_view(self,tree, col, reverse):
        """支持列排序，包括日期字符串排序。"""
        data = [(tree.set(k, col), k) for k in tree.get_children("")]

        # 时间列特殊处理
        if col == "time":
            from datetime import datetime
            data.sort(key=lambda t: datetime.strptime(t[0], "%Y-%m-%d %H"), reverse=reverse)

        else:
            # 尝试数字排序
            try:
                data.sort(key=lambda t: float(t[0]), reverse=reverse)
            except:
                data.sort(key=lambda t: t[0], reverse=reverse)

        # 重排
        for index, item in enumerate(data):
            tree.move(item[1], "", index)

        # 下次点击反向
        tree.heading(col, command=lambda: self.sort_column_archive_view(tree, col, not reverse))

    def load_archive(self,selected_file,readfile=True):
        """加载选中的存档文件并刷新监控"""
        archive_file = os.path.join(ARCHIVE_DIR, selected_file)
        if not os.path.exists(archive_file):
            messagebox.showerror("错误", "存档文件不存在")
            return
        if readfile:
            initial_monitor_list = load_monitor_list(MONITOR_LIST_FILE=archive_file)
            logger.info('readfile:{archive_file}')
            return initial_monitor_list

    def open_archive_view_window(self, filename):
        """
        从 filename 读取存档数据并显示
        数据格式：[code, name, tag, time]
        """

        try:
            data_list = self.load_archive(filename, readfile=True)

        except Exception as e:
            messagebox.showerror("读取失败", f"读取 {filename} 时发生错误:\n{e}")
            return

        if not data_list:
            messagebox.showwarning("无数据", f"{filename} 中没有可显示的数据。")
            return

        win = tk.Toplevel(self)
        win.title(f"存档预览 — {filename}")
        win.geometry("600x480")

        window_id = "存档预览"

        columns = ["code", "name", "tag", "time"]
        col_names = {
            "code": "代码",
            "name": "名称",
            "tag":  "概念",
            "time": "时间"
        }

        self.load_window_position(win, window_id, default_width=600, default_height=480)
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        tree = ttk.Treeview(frame, columns=columns, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # === 列设置 ===
        for c in columns:
            tree.heading(c, text=col_names[c],
                         anchor="center",
                         command=lambda _c=c: self.sort_column_archive_view(tree, _c, False))
            if c == "code":
                tree.column(c, width=60, anchor="center")
            elif c == "name":
                tree.column(c, width=90, anchor="w")
            elif c == "tag":
                tree.column(c, width=120, anchor="w")
            else:  # time
                tree.column(c, width=100, anchor="center")

        # === 插入数据 ===
        for row in data_list:
            # row: [code, name, tag, time]
            tree.insert("", "end", values=row)

        # === 行选择逻辑 ===
        def on_tree_select(event):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            if not vals:
                return
            code = str(vals[0]).zfill(6)
            self.sender.send(str(vals[0]).zfill(6))


        def on_single_click(event):
            row_id = tree.identify_row(event.y)
            if not row_id:
                return
            vals = tree.item(row_id, "values")
            if not vals:
                return
            self.sender.send(str(vals[0]).zfill(6))

        def on_double_click(event):
            item = tree.focus()
            if item:
                # code = tree.item(item, "values")[0]
                m = tree.item(item, "values")
                # self._on_label_double_click_top10(code)
                try:
                    code = m[0]
                    stock_name = m[1] if len(m) > 1 else ""
                    concept_name = m[2] if len(m) > 2 else ""   # 视你的 stock_info 结构而定
                    create_time = m[3] if len(m) > 3 else "" 
                    # 唯一key
                    # unique_code = f"{concept_name or ''}_{code or ''}"
                    unique_code = f"{concept_name or ''}_"

                    # 创建窗口
                    win = self.show_concept_top10_window_simple(concept_name, code=code, auto_update=True, interval=30,focus_force=True)

                    # 注册回监控字典
                    self._pg_top10_window_simple[unique_code] = {
                        "win": win,
                        "code": unique_code,
                        "stock_info": m
                    }
                    logger.info(f"恢复窗口 {unique_code}: {concept_name} - {stock_name} ({code}) [{create_time}]")
                except Exception as e:
                    logger.info(f"恢复窗口失败: {m}, 错误: {e}")

        tree.bind("<<TreeviewSelect>>", on_tree_select)
        tree.bind("<Button-1>", on_single_click)
        tree.bind("<Double-Button-1>", on_double_click)

        # ESC / 关闭
        def on_close(event=None):
            # update_window_position(window_id)
            self.save_window_position(win, window_id)
            win.destroy()

        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)

        # 默认按时间倒序
        win.after(10, lambda: self.sort_column_archive_view(tree, "time", True))


    def open_archive_loader(self):
        """打开存档选择窗口"""
        win = tk.Toplevel(self)
        win.title("加载历史监控数据")
        win.geometry("400x300")
        window_id = "历史监控数据"   # <<< 每个窗口一个唯一 ID
        # self.get_centered_window_position(win, window_id)
        self.load_window_position(win, window_id, default_width=400, default_height=300)
        files = list_archives(prefix='monitor_category_list')
        if not files:
            tk.Label(win, text="没有历史存档文件").pack(pady=20)
            return

        selected_file = tk.StringVar(value=files[0])
        combo = ttk.Combobox(win, textvariable=selected_file, values=files, state="readonly")
        combo.pack(pady=10)

        # 加载按钮
        # ttk.Button(win, text="加载", command=lambda: load_archive(selected_file.get())).pack(pady=5)
        ttk.Button(win, text="显示", command=lambda: self.open_archive_view_window(selected_file.get())).pack(pady=5)

        def on_close(event=None):
            """
            统一关闭函数，ESC 和右上角 × 都能使用
            """
            # 在这里可以加任何关闭前的逻辑，比如保存数据或确认
            # if messagebox.askokcancel("关闭窗口", "确认要关闭吗？"):
            # update_window_position(window_id)
            self.save_window_position(win, window_id)
            win.destroy()

        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", lambda: on_close())
        win.after(60*1000, lambda: on_close())   # 自动关闭

    def write_to_blk(self,append=True):
        if self.current_df.empty:
            return
        # codew=stf.WriteCountFilter(top_temp, writecount=args.dl)
        codew = self.current_df.index.tolist()
        # codew = self.current_df.index.tolist()[:50]
        block_path = tdd.get_tdx_dir_blocknew() + self.blkname
        cct.write_to_blocknew(block_path, codew,append=append,doubleFile=False,keep_last=0,dfcf=False,reappend=True)
        logger.info("wri ok:%s" % block_path)
        self.status_var2.set(f"wri ok: {self.blkname} count: {len(codew)}")
        # if args.code == 'a':
        #     cct.write_to_blocknew(block_path, codew,doubleFile=False,keep_last=0,dfcf=True,reappend=True)
        # else:
        #     cct.write_to_blocknew(block_path, codew, append=False,doubleFile=False,keep_last=0,dfcf=True,reappend=True)
    # def delete_search_history(self, which, entry=None):
    #     """
    #     删除指定搜索框的历史条目
    #     which = 1 -> 顶部搜索框
    #     which = 2 -> 底部搜索框
    #     entry: 指定要删除的条目，如果为空则用搜索框当前内容
    #     """
    #     if which == 1:
    #         history = self.search_history1
    #         combo = self.search_combo1
    #         var = self.search_var1
    #         if self.query_manager.current_key == "history1":
    #             query_manager_his = self.query_manager.history1
    #     else:
    #         history = self.search_history2
    #         combo = self.search_combo2
    #         var = self.search_var2
    #         if self.query_manager.current_key == "history2":
    #             query_manager_his = self.query_manager.history2

    #     target = entry or var.get().strip()
    #     if not target:
    #         self.status_var.set(f"搜索框 {which} 内容为空，无可删除项")
    #         return

    #     if target in history:
    #         history.remove(target)
    #         combo['values'] = history
    #         query_manager_his= [{"query": q, "starred":  0, "note": ""} for q in history]

    #         if self.query_manager.current_key == "history1" and which == 1:
    #             self.query_manager.current_history = query_manager_his
    #             self.query_manager.refresh_tree()
    #         elif self.query_manager.current_key == "history2" and which == 2:
    #             self.query_manager.current_history = query_manager_his
    #             self.query_manager.refresh_tree()

    #         self.query_manager.save_search_history()
    #         self.status_var.set(f"搜索框 {which} 已删除历史: {target}")
    #         if var.get() == target:
    #             var.set('')
    #     else:
    #         self.status_var.set(f"搜索框 {which} 历史中没有: {target}")


    # def clean_search(self, entry=None):
    #     """删除指定历史，默认删除当前搜索框内容"""
    #     self.search_var.set('')
    #     self.select_code = None
    #     self.sortby_col = None
    #     self.sortby_col_ascend = None
    #     self.refresh_tree(self.df_all)
    #     resample = self.resample_combo.get()
    #     self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")
    
    # def delete_search_history(self, entry=None):
    #     """删除指定历史，默认删除当前搜索框内容"""
    #     target = entry or self.search_var.get().strip()
    #     if target in self.search_history:
    #         self.search_history.remove(target)
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()
    #         self.status_var.set(f"已删除历史: {target}")


    # ----------------- 搜索 ----------------- #
    # def set_search(self):
    #     query = self.search_entry.get().strip()
    #     if query and not self.current_df.empty:
    #         try:
    #             df_filtered = self.current_df.query(query)
    #             self.refresh_tree(df_filtered)
    #         except Exception as e:
    #             logger.error(f"Query error: {e}")

    # # ----------------- Resample ----------------- #
    # def set_resample(self, event=None):
    #     val = self.resample_combo.get().strip()
    #     if val:
    #         cct.GlobalValues().setkey("resample", val)

    # ----------------- 状态栏 ----------------- #
    def update_status(self):
        cnt = len(self.current_df)
        # blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        # search = self.search_entry.get()
        search = self.search_var1.get()
        self.status_var.set(f"Rows: {cnt} | blkname: {self.blkname} | resample: {resample} | st: {self.st_key_sort} | search: {search}")

    # ----------------- 数据刷新 ----------------- #
    # def update_tree(self):
    #     try:
    #         while not self.queue.empty():
    #             df = self.queue.get_nowait()
    #             logger.debug(f'df:{df[:2]}')
    #             self.refresh_tree(df)
    #     except Exception as e:
    #         logger.error(f"Error updating tree: {e}", exc_info=True)
    #     finally:
    #         self.after(1000, self.update_tree)

    # ----------------- 数据存档 ----------------- #
    # def save_data_to_csv(self):
    #     if self.current_df.empty:
    #         return
    #     file_name = os.path.join(DARACSV_DIR, f"monitor_{self.resample_combo.get()}_{time.strftime('%Y%m%d_%H%M')}.csv")
    #     self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")
    #     idx =file_name.find('monitor')
    #     status_txt = file_name[idx:]
    #     self.status_var2.set(f"已保存数据到 {status_txt}")

    def save_data_to_csv(self):
        """保存当前 DataFrame 到 CSV 文件，并自动带上当前 query 的 note"""
        if self.current_df.empty:
            return

        resample_type = self.resample_combo.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        # 获取当前选中的 query（优先从 active combo）
        current_query = ""
        try:
            if hasattr(self, "search_combo1") and self.search_combo1 and self.search_combo1.get():
                current_query = self.search_combo1.get().strip()
            elif hasattr(self, "search_combo2") and self.search_combo2 and self.search_combo2.get():
                current_query = self.search_combo2.get().strip()
        except Exception:
            pass

        note = ""

        try:
            # 遍历两个历史，查找匹配的 query
            for hist_list in [getattr(self.query_manager, "history1", []),
                              getattr(self.query_manager, "history2", [])]:
                for record in self.query_manager.history1:
                    if record.get("query") == current_query:
                        note = record.get("note", "")
                        break
                if note:
                    break
        except Exception as e:
            logger.info(f"[save_data_to_csv] 获取 note 失败: {e}")
            
        # 处理 note
        if note:
            note = re.sub(r'[\\/*?:"<>|]', "_", note.strip())

        # 拼接文件名
        file_name = os.path.join(
            DARACSV_DIR,
            f"monitor_{resample_type}_{timestamp}{'_' + note if note else ''}.csv"
        )

        # 保存 CSV
        self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")

        # 状态栏提示
        idx = file_name.find("monitor")
        status_txt = file_name[idx:]
        self.status_var2.set(f"已保存数据到 {status_txt}")
        logger.info(f"[save_data_to_csv] 文件已保存: {file_name}")


    def load_data_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            try:
                df = pd.read_csv(file_path, index_col=0)
                # 如果 CSV 本身已经有 code 列，不要再插入
                if 'code' in df.columns:
                    df = df.copy()
                #停止刷新
                self.stop_refresh()
                self.df_all = df
                self.refresh_tree(df)
                idx =file_path.find('monitor')
                status_txt = file_path[idx:]
                # logger.info(f'status_txt:{status_txt}')
                self.status_var2.set(f"已加载数据: {status_txt}")
            except Exception as e:
                logger.error(f"加载 CSV 失败: {e}")


    # def load_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE, default_width=500, default_height=500):
    #     """从统一配置文件加载窗口位置"""
    #     if os.path.exists(file_path):
    #         try:
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #                 if window_name in data:
    #                     pos = data[window_name]
    #                     x, y = clamp_window_to_screens(pos['x'], pos['y'], pos['width'], pos['height'])
    #                     win.geometry(f"{pos['width']}x{pos['height']}+{x}+{y}")
    #                     # Tkinter geometry 格式
    #                     return pos['width'],pos['height'],x,y
    #         except Exception as e:
    #             logger.error(f"读取窗口位置失败: {e}")
    #     # 默认居中
    #     self.center_window(win, default_width, default_height)

    # def save_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """保存指定窗口位置到统一配置文件"""
    #     pos = {
    #         "x": win.winfo_x(),
    #         "y": win.winfo_y(),
    #         "width": win.winfo_width(),
    #         "height": win.winfo_height()
    #     }

    #     data = {}
    #     if os.path.exists(file_path):
    #         try:
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #         except Exception as e:
    #             logger.error(f"读取窗口配置失败: {e}")

    #     data[window_name] = pos

    #     try:
    #         with open(file_path, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)
    #     except Exception as e:
    #         logger.error(f"保存窗口位置失败: {e}")

    # def load_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE, default_width=500, default_height=500):
    #     """从统一配置文件加载窗口位置"""
    #     scale = get_windows_dpi_scale_factor()

    #     if os.path.exists(file_path):
    #         try:
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #                 if window_name in data:
    #                     pos = data[window_name]
    #                     # 根据当前 DPI 比例调整
    #                     width = int(pos['width'] * scale)
    #                     height = int(pos['height'] * scale)
    #                     x = int(pos['x'] * scale)
    #                     y = int(pos['y'] * scale)
    #                     # x, y = clamp_window_to_screens(pos['x'], pos['y'], pos['width'], pos['height'])
    #                     x, y = clamp_window_to_screens(x, y, width, height)
    #                     win.geometry(f"{pos['width']}x{pos['height']}+{x}+{y}  {width}  {height}")
    #                     # Tkinter geometry 格式
    #                     return width,height,x,y
    #         except Exception as e:
    #             logger.error(f"读取窗口位置失败: {e}")
    #     # 默认居中
    #     self.center_window(win, default_width, default_height)

    def is_window_visible_on_top(self,tk_window):
        """判断 Tk 窗口是否仍在最前层"""
        hwnd = int(tk_window.frame(), 0) if isinstance(tk_window.frame(), str) else tk_window.frame()
        user32 = ctypes.windll.user32
        foreground = user32.GetForegroundWindow()
        return hwnd == foreground

    def bring_monitor_to_front(self, active_window):
        target_monitor = get_monitor_index_for_window(active_window)

        for win_id, win_info in self.monitor_windows.items():
            toplevel = win_info.get("toplevel")
            if not (toplevel and toplevel.winfo_exists()):
                continue

            monitor_idx = get_monitor_index_for_window(toplevel)
            if monitor_idx != target_monitor:
                continue

            # 如果窗口被最小化，则恢复
            if toplevel.state() == "iconic":
                toplevel.deiconify()
                win_info["is_lifted"] = False

            # 检查是否真的还在最前层
            if not self.is_window_visible_on_top(toplevel):
                win_info["is_lifted"] = False

            # 提升逻辑
            if not win_info.get("is_lifted", False):
                toplevel.lift()
                toplevel.attributes("-topmost", 1)
                toplevel.attributes("-topmost", 0)
                win_info["is_lifted"] = True


    # def bring_monitor_to_front_pg(self, active_window):
    #     for k, v in self._pg_windows.items():
    #         win = v.get("win")
    #         if win is None:
    #             continue
    #         if v.get("code") == active_window:
    #             continue
    #         # 如果窗口被最小化，恢复
    #         if win.isMinimized():
    #             win.setWindowState(QtCore.Qt.WindowNoState)

    #         # 显示窗口
    #         win.show()              # 如果窗口被隐藏
    #         win.raise_()            # 提到最前
    #         # win.activateWindow()    # 获取焦点

    #         # 窗口置顶逻辑（短暂置顶）
    #         win.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
    #         win.show()  # 需要调用 show 让 flag 生效
    #         win.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
    #         win.show()  # 取消置顶后刷新
    def bring_monitor_to_front_pg(self, active_code):
        """仅在当前 PG 窗口被主窗口遮挡时才提升"""
        # main_win = self.main_window     # 主窗口
        main_win = self.main_window     # 主窗口
        if main_win is None:
            return

        for k, v in self._pg_windows.items():
            win = v.get("win")
            if win is None:
                continue

            if v.get("code") == active_code:
                continue  # 不处理当前活动窗口

            # 判断是否被遮挡
            logger.info(f'win: {win} main_win: {main_win} type: {type(main_win)}')

            if is_window_covered_pg(win, main_win):
                # 若被最小化，恢复
                logger.info(f'v.get("code"): {v.get("code")}')
                if win.isMinimized():
                    win.showNormal()

                # 轻量提升 → 不抢焦点
                win.raise_()
                win.activateWindow()


    def on_monitor_window_focus_pg(self,active_windows):
        """
        当任意窗口获得焦点时，协调两个窗口到最前。
        """

        win_state = self.win_var.get()
        if win_state:
            self.bring_monitor_to_front_pg(active_windows)

    def on_monitor_window_focus(self,active_windows):
        """
        当任意窗口获得焦点时，协调两个窗口到最前。
        """
        win_state = self.win_var.get()
        if win_state:
            self.bring_monitor_to_front(active_windows)
            self.bring_monitor_to_front_pg(active_windows)
        else:
           for win_id, win_info in self.monitor_windows.items():
               toplevel = win_info.get("toplevel")
               if not (toplevel and toplevel.winfo_exists()):
                   continue

               # 提升逻辑
               if  win_info.get("is_lifted", True):
                   win_info["is_lifted"] = False
                   
    def _get_dpi_scale_factor(self):
        """获取当前 DPI 缩放因子（统一处理）"""
        try:
            scale = getattr(self, 'scale_factor', 1.0)
            if not isinstance(scale, (int, float)) or scale <= 0:
                scale = 1.0
            return scale
        except Exception as e:
            logger.warning(f"[_get_dpi_scale_factor] 获取缩放失败，使用默认值: {e}")
            return 1.0

    def _get_config_file_path(self, base_file_path, scale):
        """根据缩放因子获取配置文件路径（统一处理）"""
        if scale > 1.5:
            base, filename = os.path.split(base_file_path)
            return os.path.join(base, f"scale{int(scale)}_{filename}")
        return base_file_path

    def load_window_position(self, win, window_name, file_path=WINDOW_CONFIG_FILE, default_width=500, default_height=500, offset_step=100):
        """从统一配置文件加载窗口位置（自动按当前 DPI 缩放）"""
        try:
            window_name = str(window_name)
            win_name = f"{window_name}-{getattr(win, '_concept_name')}" if hasattr(win, '_concept_name') else window_name
            scale = self._get_dpi_scale_factor()
            logger.debug(f'[load_window_position] scale={scale}')

            # 获取正确的配置文件路径
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)

            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if window_name in data:
                    pos = data[window_name]
                    # ✅ 配置文件中存储的是标准化值（scale=1.0时的坐标）
                    # 现在需要按当前 scale 乘以还原到物理像素
                    width = int(pos["width"] * scale)
                    height = int(pos["height"] * scale)
                    x = int(pos["x"] * scale)
                    y = int(pos["y"] * scale)

                    # 处理叠加窗口的偏移
                    if window_name == 'concept_top10_window_simple' and hasattr(self, "_pg_top10_window_simple"):
                        active_windows = self._pg_top10_window_simple.values()
                        count_active_window = len(active_windows)
                        if count_active_window > 0:
                            logger.debug(f'[load_window_position] 处理叠加窗口 {window_name}')
                            x += offset_step * count_active_window
                            y += offset_step * (count_active_window - 1)

                    # 防止窗口位置越界
                    x, y = clamp_window_to_screens(x, y, width, height)
                    win.geometry(f"{width}x{height}+{x}+{y}")
                    logger.debug(f"[load_window_position] 加载 {window_name}: {width}x{height}+{x}+{y}")
                    return width, height, x, y

            # 没有记录则默认居中
            logger.debug(f"[load_window_position] 未找到 {window_name} 配置，使用默认居中")
            self.center_window(win, default_width, default_height)
            return default_width, default_height, None, None

        except Exception as e:
            logger.error(f"[load_window_position] 读取窗口位置失败: {e}")
            self.center_window(win, default_width, default_height)
            return default_width, default_height, None, None



    def save_window_position(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
        """保存指定窗口位置到统一配置文件（按 DPI 反向缩放存储为标准值）"""
        try:
            window_name = str(window_name)
            win_name = f"{window_name}-{getattr(win, '_concept_name')}" if hasattr(win, '_concept_name') else window_name
            scale = self._get_dpi_scale_factor()
            logger.debug(f'[save_window_position] scale={scale}')

            # ✅ 获取窗口的物理坐标/大小，除以 scale 得到标准化值存储
            pos = {
                "x": int(win.winfo_x() / scale),
                "y": int(win.winfo_y() / scale),
                "width": int(win.winfo_width() / scale),
                "height": int(win.winfo_height() / scale)
            }

            # 获取正确的配置文件路径
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            logger.debug(f'[save_window_position] config_file_path={config_file_path} width: {win.winfo_width()/ scale}x{win.winfo_height() / scale} ')

            # 读取旧数据
            data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.error(f"[save_window_position] 读取窗口配置失败: {e}")

            # 更新数据
            data[window_name] = pos

            # 写入文件
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"[save_window_position] 已保存 {window_name}: {pos}")

        except Exception as e:
            logger.error(f"[save_window_position] 保存窗口位置失败: {e}")

    # def load_window_position(self, win, window_name, file_path=WINDOW_CONFIG_FILE,
    #                          default_width=500, default_height=500, offset_step=100):
    #     """从统一配置文件加载窗口位置（不依赖 DPI 缩放）"""
    #     try:
    #         window_name = str(window_name)

    #         if os.path.exists(file_path):
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)

    #             if window_name in data:
    #                 pos = data[window_name]
    #                 width = int(pos.get("width", default_width))
    #                 height = int(pos.get("height", default_height))
    #                 x = int(pos.get("x", 100))
    #                 y = int(pos.get("y", 100))

    #                 # --- 检查是否有同类型窗口 ---
    #                 if hasattr(self, "_pg_top10_window_simple"):
    #                     active_windows = self._pg_top10_window_simple.values()
    #                     count_active_window = len(active_windows)
    #                     same_name_count = count_active_window - 1
    #                     if count_active_window > 1:
    #                         # 每个叠加窗口偏移 offset_step
    #                         x += offset_step * count_active_window
    #                         y += offset_step * same_name_count

    #                 # --- 防止窗口位置越界 ---
    #                 x, y = clamp_window_to_screens(x, y, width, height)

    #                 # --- 应用窗口位置 ---
    #                 win.geometry(f"{width}x{height}+{x}+{y}")
    #                 logger.info(f"[load_window_position] 加载 {window_name}: {width}x{height}+{x}+{y}")
    #                 return width, height, x, y

    #         # 没有记录则默认居中
    #         logger.info(f"[load_window_position] 未找到 {window_name} 配置，使用默认居中")
    #         self.center_window(win, default_width, default_height)
    #         return default_width, default_height, None, None

    #     except Exception as e:
    #         logger.error(f"[load_window_position] 读取窗口位置失败: {e}")
    #         self.center_window(win, default_width, default_height)
    #         return default_width, default_height, None, None


    # def save_window_position(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """保存指定窗口位置到统一配置文件（不依赖 DPI 缩放）"""
    #     try:
    #         window_name = str(window_name)

    #         # --- 获取当前窗口位置 ---
    #         pos = {
    #             "x": int(win.winfo_x()),
    #             "y": int(win.winfo_y()),
    #             "width": int(win.winfo_width()),
    #             "height": int(win.winfo_height())
    #         }

    #         # --- 读取旧配置 ---
    #         data = {}
    #         if os.path.exists(file_path):
    #             try:
    #                 with open(file_path, "r", encoding="utf-8") as f:
    #                     data = json.load(f)
    #             except Exception as e:
    #                 logger.error(f"[save_window_position] 读取旧配置失败: {e}")

    #         # --- 更新并写入 ---
    #         data[window_name] = pos
    #         with open(file_path, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)

    #         logger.info(f"[save_window_position] 已保存 {window_name}: {pos}")

    #     except Exception as e:
    #         logger.error(f"[save_window_position] 保存窗口位置失败: {e}")


    # def load_window_position_qt_guisave(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """从 JSON 中恢复 Qt 窗口位置（Base64 geometry）"""
    #     try:
    #         import base64, os, json
    #         if not os.path.exists(file_path):
    #             return

    #         with open(file_path, "r", encoding="utf-8") as f:
    #             data = json.load(f)

    #         geom_b64 = data.get(window_name)
    #         if geom_b64:
    #             geom_bytes = base64.b64decode(geom_b64)
    #             win.restoreGeometry(geom_bytes)
    #             logger.info(f"[load_window_position_qt] 已恢复 {window_name}")
    #     except Exception as e:
    #         logger.error(f"[load_window_position_qt] 恢复窗口位置失败: {e}")


    def load_window_position_qt(self, win, window_name, file_path=WINDOW_CONFIG_FILE,
                                 default_width=500, default_height=500, offset_step=30):
        """加载 Qt 窗口位置（支持自动错开已存在的窗口，DPI缩放一致化）"""
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()
            logger.debug(f'[load_window_position_qt] scale={scale}')

            x = y = None
            width = default_width
            height = default_height

            # 获取正确的配置文件路径
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            logger.debug(f'[load_window_position_qt] config_file_path={config_file_path}')

            # --- 从文件加载保存的窗口位置 ---
            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if window_name in data:
                    pos = data[window_name]
                    # ✅ 配置文件中存储的是标准化值，现在需要按 scale 乘以还原到物理像素
                    width = int(pos.get("width", default_width) * scale)
                    height = int(pos.get("height", default_height) * scale)
                    x = int(pos.get("x", 0) * scale)
                    y = int(pos.get("y", 0) * scale)

                    # 防止窗口位置越界
                    x, y = clamp_window_to_screens(x, y, width, height)
                    logger.debug(f'width: {pos.get("width")}  height: {pos.get("height")}+{x}+{y}')
                    logger.debug(f"[load_window_position_qt] 加载 {window_name}: {width}x{height} {x}+{y}")

            # --- 如果没有存储位置，则居中 ---
            screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
            if x is None or y is None:
                x = (screen.width() - width) // 2
                y = (screen.height() - height) // 2

            # --- 检查是否已有同名窗口正在显示，并自动偏移 ---
            if hasattr(self, "_pg_windows"):
                active_windows = [w["win"] for w in self._pg_windows.values()
                                  if isinstance(w.get("win"), QtWidgets.QWidget) and w["win"].isVisible()]
                same_name_count = sum(1 for w in active_windows if w.windowTitle() == win.windowTitle())
                if same_name_count > 0:
                    x += offset_step * same_name_count
                    y += offset_step * same_name_count
                    # 限制不超出屏幕
                    if x + width > screen.width():
                        x = screen.width() - width - 10
                    if y + height > screen.height():
                        y = screen.height() - height - 10

            # ✅ 设置窗口几何（物理像素）
            win.setGeometry(x, y, width, height)
            return width, height, x, y

        except Exception as e:
            logger.error(f"[load_window_position_qt] 加载失败: {e}")
            traceback.print_exc()
            # 默认居中
            screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
            x = (screen.width() - default_width) // 2
            y = (screen.height() - default_height) // 2
            win.setGeometry(x, y, default_width, default_height)
            return default_width, default_height, x, y


    # def load_window_position_qt(self, win, window_name, file_path=WINDOW_CONFIG_FILE, default_width=500, default_height=500, offset_step=30):
    #     """加载 Qt 窗口位置（支持自动错开已存在的窗口）"""
    #     try:
    #         window_name = str(window_name)
    #         scale = 1.0
    #         try:
    #             scale = get_windows_dpi_scale_factor()
    #             if not isinstance(scale, (int, float)) or scale <= 0:
    #                 scale = 1.0
    #         except Exception as e:
    #             logger.info(f"[load_window_position_qt] 获取 DPI 缩放失败: {e}")

    #         x = y = None
    #         width = default_width
    #         height = default_height

    #         if os.path.exists(file_path):
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #             if window_name in data:
    #                 pos = data[window_name]
    #                 # ✳️ 按当前 DPI 放大回去
    #                 width = int(pos["width"] * scale)
    #                 height = int(pos["height"] * scale)
    #                 # width = int(pos["width"] )
    #                 # height = int(pos["height"] )
    #                 x = int(pos["x"] * scale)
    #                 y = int(pos["y"] * scale)
    #                 # 防止窗口位置越界
    #                 x, y = clamp_window_to_screens(x, y, width, height)

    #                 logger.info(f"[load_window_position_qt] 加载 {window_name}: {width}x{height}+{x}+{y}")
    #                 # return width, height, x, y
    #         # --- 检查屏幕边界 ---
    #         screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    #         if x is None or y is None:
    #             x = (screen.width() - width) // 2
    #             y = (screen.height() - height) // 2

    #         # --- 检查是否已有同名窗口正在显示，并自动偏移 ---
    #         if hasattr(self, "_pg_windows"):
    #             active_windows = [w["win"] for w in self._pg_windows.values()
    #                              if isinstance(w.get("win"), QtWidgets.QWidget) and w["win"].isVisible()]
    #             same_name_count = sum(1 for w in active_windows if w.windowTitle() == win.windowTitle())
    #             if same_name_count > 0:
    #                 x += offset_step * same_name_count
    #                 y += offset_step * same_name_count
    #                 # 限制不超出屏幕
    #                 if x + width > screen.width():
    #                     x = screen.width() - width - 50
    #                 if y + height > screen.height():
    #                     y = screen.height() - height - 50


    #         # ✅ 设置窗口位置
    #         win.setGeometry(x, y, width, height)
    #         logger.info(f"[load_window_position_qt] 加载 {window_name}: {width}x{height}+{x}+{y}")
    #         return width, height, x, y

    #     except Exception as e:
    #         logger.info(f"[load_window_position_qt] 加载失败: {e}")
    #         # 默认居中
    #         traceback.print_exc()
    #         screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    #         x = (screen.width() - default_width) // 2
    #         y = (screen.height() - default_height) // 2
    #         win.setGeometry(x, y, default_width, default_height)
    #         return default_width, default_height, x, y

    # def save_window_position_qt_nodpi(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """保存 PyQt 窗口位置到统一配置文件（逻辑坐标，不依赖 DPI）"""
    #     try:
    #         window_name = str(window_name)
    #         geom = win.geometry()  # QRect
    #         pos = {
    #             "x": int(geom.x()),
    #             "y": int(geom.y()),
    #             "width": int(geom.width()),
    #             "height": int(geom.height())
    #         }

    #         data = {}
    #         if os.path.exists(file_path):
    #             try:
    #                 with open(file_path, "r", encoding="utf-8") as f:
    #                     data = json.load(f)
    #             except Exception as e:
    #                 logger.error(f"[save_window_position_qt] 读取配置失败: {e}")

    #         data[window_name] = pos
    #         with open(file_path, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)

    #         logger.info(f"[save_window_position_qt] 已保存 {window_name}: {pos}")

    #     except Exception as e:
    #         logger.error(f"[save_window_position_qt] 保存窗口位置失败: {e}")



    # "概念分析Top1": "AdnQywACAAAAAAGUAAAApAAAAn8AAAHAAAABlwAAALQAAAJ8AAABvQAAAAAAAAAABEk=",
    # "概念分析Top10": "AdnQywACAAAAAAC3AAAAuAAAA0AAAAJlAAAAugAAAMgAAAM9AAACYgAAAAAAAAAABEk="

    # def save_window_position_qt_gui(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """保存 PyQt 窗口位置到统一配置文件（Base64 存储 geometry，自动按 DPI 缩放）"""
    #     try:
    #         window_name = str(window_name)
    #         from PyQt5 import QtCore
    #         import base64
    #         import os, json

    #         # 获取窗口 geometry 字节串
    #         geom_bytes = win.saveGeometry()
    #         # 转成 Base64 可存 JSON
    #         geom_b64 = base64.b64encode(geom_bytes).decode('ascii')

    #         # 读取已有 JSON
    #         data = {}
    #         if os.path.exists(file_path):
    #             try:
    #                 with open(file_path, "r", encoding="utf-8") as f:
    #                     data = json.load(f)
    #             except Exception as e:
    #                 logger.error(f"[save_window_position_qt] 读取配置失败: {e}")

    #         # 保存当前窗口 geometry
    #         data[window_name] = geom_b64

    #         with open(file_path, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)

    #         logger.info(f"[save_window_position_qt] 已保存 {window_name}（Base64 geometry）")

    #     except Exception as e:
    #         logger.error(f"[save_window_position_qt] 保存窗口位置失败: {e}")


    def save_window_position_qt(self, win, window_name, file_path=WINDOW_CONFIG_FILE):
        """保存 PyQt 窗口位置到统一配置文件（按 DPI 反向缩放存储为标准值）"""
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()
            logger.debug(f'[save_window_position_qt] scale={scale}')

            geom = win.geometry()  # QRect
            # ✅ 获取窗口的物理坐标/大小，除以 scale 得到标准化值存储
            width = max(130, min(int(geom.width() / scale), 500))
            height = max(150, min(int(geom.height() / scale), 450))
            pos = {
                "x": int(geom.x() / scale),
                "y": int(geom.y() / scale),
                "width": width,
                "height": height
            }
            logger.debug(f'width: {geom.width()}  height: {geom.height()}')

            # 获取正确的配置文件路径
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            logger.debug(f'[save_window_position_qt] config_file_path={config_file_path}')

            # 读取旧数据
            data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.error(f"[save_window_position_qt] 读取配置失败: {e}")

            # 更新数据
            data[window_name] = pos

            # 写入文件
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"[save_window_position_qt] 已保存 {window_name}: {pos}")

        except Exception as e:
            logger.error(f"[save_window_position_qt] 保存窗口位置失败: {e}")


    # def save_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE):
    #     """保存指定窗口位置到统一配置文件"""
    #     scale = get_windows_dpi_scale_factor()
    #     pos = {
    #             "x": int(win.winfo_x() / scale),
    #             "y": int(win.winfo_y() / scale),
    #             "width": int(win.winfo_width() / scale),
    #             "height": int(win.winfo_height() / scale)
    #         }

    #     data = {}
    #     if os.path.exists(file_path):
    #         try:
    #             with open(file_path, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #         except Exception as e:
    #             logger.error(f"读取窗口配置失败: {e}")

    #     data[window_name] = pos

    #     try:
    #         with open(file_path, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)
    #     except Exception as e:
    #         logger.error(f"保存窗口位置失败: {e}")

    def center_window(self,win, width, height):
        """
        将指定窗口居中显示
        win: Tk 或 Toplevel
        width, height: 窗口宽高
        """
        win.update_idletasks()  # 更新窗口信息
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")
        logger.debug(f"{width}x{height}+{x}+{y}")


    def on_close(self):
        self.alert_manager.save_all()
        # self.save_window_position()
        # 3. 如果 concept 窗口存在，也保存位置并隐藏
        if hasattr(self, "_concept_win") and self._concept_win:
            if self._concept_win.winfo_exists():
                self.save_window_position(self._concept_win, "detail_window")
                self._concept_win.destroy()
        # 如果 KLineMonitor 存在且还没销毁，保存位置
        if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
            try:
                self.save_window_position(self.kline_monitor, "KLineMonitor")
                self.kline_monitor.on_kline_monitor_close()
                self.kline_monitor.destroy()
            except Exception:
                pass

        # 如果 KLineMonitor 存在且还没销毁，保存位置
        if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
            try:
                self.save_window_position(self.kline_monitor, "KLineMonitor")
                self.kline_monitor.on_kline_monitor_close()
                self.kline_monitor.destroy()
            except Exception:
                pass

        # --- 保存并关闭所有 monitor_windows（概念前10窗口）---
        if hasattr(self, "live_strategy"):
            try:
                # 提取窗口名称用于保存位置
                # unique_code 格式为 "concept_name_code" 或 "concept_name"
                now_time = cct.get_now_time_int()
                if now_time > 1500:
                    self.live_strategy._save_monitors()
                    logger.info(f"[on_close] self.live_strategy._save_monitors SAVE OK")
                else:
                    logger.info(f"[on_close] now:{now_time} 不到收盘时间 未进行_save_monitors SAVE OK")

            except Exception as e:
                logger.warning(f"[on_close] self.live_strategy._save_monitors 失败: {e}")

        # --- 关闭所有 concept top10 窗口 ---
        if hasattr(self, "_pg_top10_window_simple"):
            self.save_all_monitor_windows()
            for key, win_info in list(self._pg_top10_window_simple.items()):
                win = win_info.get("win")
                if win and win.winfo_exists():
                    try:
                        # 如果窗口有 on_close 方法，先调用
                        if hasattr(win, "on_close") and callable(win.on_close):
                            win.on_close()
                        else:
                            # 没有 on_close 的就直接销毁
                            win.destroy()
                    except Exception as e:
                        logger.info(f"关闭窗口 {key} 出错: {e}")
            self._pg_top10_window_simple.clear()

        # --- 关闭所有 concept top10 窗口 (PyQt 版) ---
        if hasattr(self, "_pg_windows"):
            for key, win_info in list(self._pg_windows.items()):
                win = win_info.get("win")
                if win is not None:
                    try:
                        # 如果窗口有 on_close 方法，先调用
                        if hasattr(win, "on_close") and callable(win.on_close):
                            win.on_close()
                        else:
                            # 没有 on_close 的就直接关闭窗口
                            win.close()  # QWidget 的关闭方法
                    except Exception as e:
                        logger.info(f"关闭窗口 {key} 出错: {e}")
            self._pg_windows.clear()

        self.save_window_position(self,"main_window")
        # self.save_search_history()
        self.query_manager.save_search_history()
        archive_search_history_list()
        self.stop_refresh()
        if self.proc.is_alive():
            self.proc.join(timeout=1)    # 等待最多 5 秒
            if self.proc.is_alive():
                self.proc.terminate()    # 强制终止
        # try:
        #     self.manager.shutdown()
        # except Exception as e: 
        #     logger.info(f'manager.shutdown : {e}')
        # plt.close('all')
        self.destroy()

# class QueryHistoryManager(tk.Frame):
#     def __init__(self, master, search_var1, search_var2, search_combo1, search_combo2, history_file):
#         super().__init__(master)  
class QueryHistoryManager:
    def __init__(self, root=None,search_var1=None, search_var2=None, search_var3=None,search_combo1=None,search_combo2=None,search_combo3=None,auto_run=False,history_file="query_history.json",sync_history_callback=None,test_callback=None):
        """
        root=None 时不创建窗口，只管理数据
        auto_run=True 时直接打开编辑窗口
        """
        self.root = root
        self.history_file = history_file
        self.search_var1 = search_var1
        self.search_var2 = search_var2
        self.search_var3 = search_var3
        self.his_limit = 30
        self.search_combo1 = search_combo1
        self.search_combo2 = search_combo2
        self.search_combo3 = search_combo3
        self.deleted_stack = []  # 保存被删除的 query 记录

        self.sync_history_callback = sync_history_callback
        self.test_callback = test_callback
        # 读取历史
        # self.history1, self.history2 = self.load_search_history()
        self.history1, self.history2, self.history3 = self.load_search_history()
        self.current_history = self.history1
        self.current_key = "history1"
        self.MAX_HISTORY = 500
        # if root and auto_run:
        self._build_ui()



    def _build_ui(self):
        # self.root.title("Query History Manager")

        if hasattr(self, "editor_frame"):
            self.editor_frame.destroy()  # 重建

        self.editor_frame = tk.Frame(self.root)
        # self.editor_frame.pack(side="right", fill="y")  # 右侧显示
        # --- 输入区 ---
        # frame_input = tk.Frame(self.root)
        frame_input = tk.Frame(self.editor_frame)
        frame_input.pack(fill="x", padx=5, pady=1, expand=True)

        tk.Label(frame_input, text="Query:").pack(side="left")
        self.entry_query = tk.Entry(frame_input)
        self.entry_query.pack(side="left", padx=5, fill="x", expand=True)

        btn_add = tk.Button(frame_input, text="测试", command=self.on_test_click).pack(side="left", padx=2)
        btn_add = tk.Button(frame_input, text="添加", command=self.add_query)
        btn_add.pack(side="left", padx=5)

        btn_add2 = tk.Button(frame_input, text="使用选中", command=self.use_query)
        btn_add2.pack(side="left", padx=5)
        btn_add3 = tk.Button(frame_input, text="保存", command=self.save_search_history)
        btn_add3.pack(side="right", padx=5)

        self.entry_query.bind("<Button-3>", self.on_right_click)

        # 下拉选择管理 history1 / history2
        # self.combo_group = ttk.Combobox(frame_input, values=["history1", "history2"], state="readonly", width=10)
        # self.combo_group.set("history1")
        # self.combo_group.pack(side="left", padx=5, ipady=1)
        # self.combo_group.bind("<<ComboboxSelected>>", self.switch_group)

        # 下拉选择管理 history1 / history2 / history3
        self.combo_group = ttk.Combobox(
            frame_input,
            values=["history1", "history2", "history3"],  # 加入 history3
            state="readonly", width=10
        )
        self.combo_group.set("history1")
        self.combo_group.pack(side="left", padx=5, ipady=1)
        self.combo_group.bind("<<ComboboxSelected>>", self.switch_group)


        # --- Treeview ---
        self.tree = ttk.Treeview(
            self.editor_frame, columns=("query", "star", "note","hit"), show="headings", height=12
        )
        self.tree.heading("query", text="Query")
        self.tree.heading("star", text="⭐")
        self.tree.heading("note", text="备注")
        self.tree.heading("hit", text="命中")  # 新增 hit 列

        # # 设置初始列宽（按比例 6:1:3）
        # total_width = 600  # 初始宽度参考
        # self.tree.column("query", width=int(total_width * 0.6), anchor="w")
        # self.tree.column("star", width=int(total_width * 0.1), anchor="center")
        # self.tree.column("note", width=int(total_width * 0.2), anchor="w")
        # self.tree.column("hit", width=int(total_width * 0.1), anchor="w")
        # self.tree.pack(fill="both", expand=True, padx=5, pady=1)

        # 初始列宽参考比例 6:1:2:1
        col_ratios = {"query": 0.7, "star": 0.05, "note": 0.2, "hit": 0.05}

        for col in self.tree["columns"]:
            self.tree.column(col, width=1, anchor="w", stretch=True)  # 先给最小宽度

        self.tree.pack(expand=True, fill="both")

        # --- 窗口绘制完成后调整列宽 ---
        def adjust_column_widths():
            if not hasattr(self, "tree") or not self.tree.winfo_exists():
                return  # 已销毁，直接返回
            total_width = self.tree.winfo_width()
            if total_width <= 1:  # 尚未绘制完成，延迟再执行
                self.tree.after(50, adjust_column_widths)
                return
            for col, ratio in col_ratios.items():
                self.tree.column(col, width=int(total_width * ratio))

        # self.tree.after_idle(adjust_column_widths)  # 窗口绘制完成后执行
        # 延迟执行一次，确保 Treeview 已经有宽度
        self.tree.after(50, adjust_column_widths)

        # --- 可选：绑定窗口调整事件，实现动态调整 ---
        def on_resize(event):
            total_width = event.width
            for col, ratio in col_ratios.items():
                self.tree.column(col, width=int(total_width * ratio))

        self.editor_frame.bind("<Configure>", on_resize)

        # 单击星标 / 双击修改 / 右键菜单
        self.tree.bind("<Button-1>", self.on_click_star)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # --- 自动按比例调整列宽 ---
        def resize_columns(event):
            total_width = self.tree.winfo_width()
            if total_width <= 0:
                return
            self.tree.column("query", width=int(total_width * 0.75))
            self.tree.column("star", width=int(total_width * 0.05))
            self.tree.column("note", width=int(total_width * 0.2))

        self.tree.bind("<Configure>", resize_columns)


        # 单击星标
        self.tree.bind("<Button-1>", self.on_click_star)
        # 双击修改
        self.tree.bind("<Double-1>", self.on_double_click)
        # 右键菜单
        self.tree.bind("<Button-3>", self.show_context_menu)
        # 键盘 Delete 删除
        self.tree.bind("<Delete>", self.on_delete_key)

        self.root.bind("<Control-z>", self.undo_delete)  # 快捷键绑定
        self.root.bind("<Escape>", lambda event: self.open_editor())
        self.root.bind("<Alt-q>", lambda event: self.open_editor())

        # 为每列绑定排序
        for col in ("query", "star", "note","hit"):
            self.tree.heading(col, text=col.capitalize(), command=lambda _col=col: self.treeview_sort_column(self.tree, _col))

        self.refresh_tree()

    def on_right_click(self,event):
        try:
            # 获取剪贴板内容
            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        # 插入到光标位置
        # event.widget.insert(tk.INSERT, clipboard_text)
        # 先清空再黏贴
        # event.widget.delete(0, tk.END)
        # event.widget.insert(0, clipboard_text)
        # self.on_test_click()
        # 正则提取 6 位数字代码（如 002171）
        if clipboard_text.find('and') < 0:
            match = re.search(r'\b\d{6}\b', clipboard_text)
            if match:
                code = match.group(0)
                # 清空输入框并插入代码
                event.widget.delete(0, tk.END)
                event.widget.insert(0, code)
                self.on_test_click()
            # 自动触发查询
            else:
                logger.info(f"[on_right_click] 未找到6位数字代码: {clipboard_text}")
        else:
            event.widget.delete(0, tk.END)
            event.widget.insert(0, clipboard_text)
            self.on_test_click()


    # 先给每列绑定排序事件
    def treeview_sort_column(self,tv, col, reverse=False):
        """按列排序"""
        # 获取所有行的内容
        data_list = [(tv.set(k, col), k) for k in tv.get_children('')]
        
        # 判断内容是否是数字，便于数值排序
        try:
            data_list.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            data_list.sort(key=lambda t: t[0], reverse=reverse)
        
        # 重新排列行
        for index, (val, k) in enumerate(data_list):
            tv.move(k, '', index)
        
        # 下一次点击反转排序
        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))



    def open_editor(self):
        """在已有 root 上打开编辑窗口"""

        if not hasattr(self, "editor_frame"):
            self._build_ui()
            self.editor_frame.pack(fill="both", expand=True)  # 仅显示，不移动位置
        else:

            if self.editor_frame.winfo_ismapped():
                self.editor_frame.pack_forget()  # 隐藏
            else:
                self.editor_frame.pack(fill="both", expand=True)  # 仅显示，不移动位置


    # def save_search_history_h1h2(self, confirm_threshold=10):
    #     #fix add test_code save clear history bug
    #     """保存搜索历史，合并编辑记录到历史顶部，超过 confirm_threshold 条变动时提示确认"""
    #     try:
    #         # ---------- 工具函数 ----------
    #         def dedup(history):
    #             seen = set()
    #             result = []
    #             for r in history:
    #                 q = r.get("query") if isinstance(r, dict) else str(r)
    #                 if q not in seen:
    #                     seen.add(q)
    #                     result.append(r)
    #             return result

    #         def normalize_history(history):
    #             normalized = []
    #             for r in history:
    #                 if not isinstance(r, dict):
    #                     continue
    #                 q = r.get("query", "")
    #                 starred = r.get("starred", 0)
    #                 note = r.get("note", "")
    #                 if isinstance(starred, bool):
    #                     starred = 1 if starred else 0
    #                 elif not isinstance(starred, int):
    #                     starred = 0
    #                 normalized.append({"query": q, "starred": starred, "note": note})
    #             return normalized

    #         def merge_history(current, old):
    #             seen = set()
    #             result = []
    #             for r in current:
    #                 q = r.get("query") if isinstance(r, dict) else str(r)
    #                 if q not in seen:
    #                     seen.add(q)
    #                     result.append(r)
    #             for r in old:
    #                 q = r.get("query") if isinstance(r, dict) else str(r)
    #                 if q not in seen:
    #                     seen.add(q)
    #                     result.append(r)
    #             return result[:self.MAX_HISTORY]

    #         # ---------- 加载旧历史 ----------
    #         old_data = {"history1": [], "history2": []}
    #         if os.path.exists(self.history_file):
    #             with open(self.history_file, "r", encoding="utf-8") as f:
    #                 try:
    #                     loaded_data = json.load(f)
    #                     old_data["history1"] = dedup(loaded_data.get("history1", []))
    #                     old_data["history2"] = dedup(loaded_data.get("history2", []))
    #                 except json.JSONDecodeError:
    #                     pass

    #         # ---------- 规范当前历史 ----------
    #         self.history1 = normalize_history(self.history1)
    #         self.history2 = normalize_history(self.history2)

    #         # ---------- 合并历史 ----------
    #         merged_data = {
    #             "history1": normalize_history(merge_history(self.history1, old_data.get("history1", []))),
    #             "history2": normalize_history(merge_history(self.history2, old_data.get("history2", []))),
    #         }

    #         # ---------- 检测变动量 ----------
    #         def changes_count(old_list, new_list):
    #             old_set = {r['query'] for r in old_list}
    #             new_set = {r['query'] for r in new_list}
    #             return len(new_set - old_set) + len(old_set - new_set)

    #         delta1 = changes_count(old_data.get("history1", []), merged_data["history1"])
    #         delta2 = changes_count(old_data.get("history2", []), merged_data["history2"])

    #         if delta1 + delta2 >= confirm_threshold:
    #             if not messagebox.askyesno(
    #                 "确认保存",
    #                 f"搜索历史发生较大变动（{delta1 + delta2} 条），是否继续保存？"
    #             ):
    #                 logger.info("❌ 用户取消保存搜索历史")
    #                 return

    #         # ---------- 写回文件 ----------
    #         with open(self.history_file, "w", encoding="utf-8") as f:
    #             json.dump(merged_data, f, ensure_ascii=False, indent=2)

    #         logger.info(f"✅ 搜索历史已保存 "
    #               f"(history1: {len(merged_data['history1'])} 条 / "
    #               f"history2: {len(merged_data['history2'])} 条)，starred 已统一为整数")

    #     except Exception as e:
    #         messagebox.showerror("错误", f"保存搜索历史失败: {e}")

    def save_search_history(self, confirm_threshold=10):
        #fix add test_code save clear history bug
        """保存搜索历史，合并编辑记录到历史顶部，超过 confirm_threshold 条变动时提示确认"""
        try:
            # ---------- 工具函数 ----------
            def dedup(history):
                seen = set()
                result = []
                for r in history:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                return result

            def normalize_history(history):
                normalized = []
                for r in history:
                    if not isinstance(r, dict):
                        continue
                    q = r.get("query", "")
                    starred = r.get("starred", 0)
                    note = r.get("note", "")
                    if isinstance(starred, bool):
                        starred = 1 if starred else 0
                    elif not isinstance(starred, int):
                        starred = 0
                    normalized.append({"query": q, "starred": starred, "note": note})
                return normalized

            def merge_history(current, old):
                seen = set()
                result = []
                for r in current:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                for r in old:
                    q = r.get("query") if isinstance(r, dict) else str(r)
                    if q not in seen:
                        seen.add(q)
                        result.append(r)
                return result[:self.MAX_HISTORY]

            # ---------- 加载旧历史 ----------
            old_data = {"history1": [], "history2": [] , "history3": []}
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    try:
                        loaded_data = json.load(f)
                        old_data["history1"] = dedup(loaded_data.get("history1", []))
                        old_data["history2"] = dedup(loaded_data.get("history2", []))
                        old_data["history3"] = dedup(loaded_data.get("history3", []))
                    except json.JSONDecodeError:
                        pass

            # ---------- 规范当前历史 ----------
            self.history1 = normalize_history(self.history1)
            self.history2 = normalize_history(self.history2)
            self.history3 = normalize_history(self.history3)

            # ---------- 合并历史 ----------
            merged_data = {
                "history1": normalize_history(merge_history(self.history1, old_data.get("history1", []))),
                "history2": normalize_history(merge_history(self.history2, old_data.get("history2", []))),
                "history3": normalize_history(merge_history(self.history3, old_data.get("history3", []))),
            }

            # ---------- 检测变动量 ----------
            def changes_count(old_list, new_list):
                old_set = {r['query'] for r in old_list}
                new_set = {r['query'] for r in new_list}
                return len(new_set - old_set) + len(old_set - new_set)

            delta1 = changes_count(old_data.get("history1", []), merged_data["history1"])
            delta2 = changes_count(old_data.get("history2", []), merged_data["history2"])
            delta3 = changes_count(old_data.get("history3", []), merged_data["history3"])

            if delta1 + delta2 >= confirm_threshold:
                if not messagebox.askyesno(
                    "确认保存",
                    f"搜索历史发生较大变动（{delta1 + delta2} 条），是否继续保存？"
                ):
                    logger.info("❌ 用户取消保存搜索历史")
                    return

            # ---------- 写回文件 ----------
            # with open(self.history_file, "w", encoding="utf-8") as f:
            #     json.dump(merged_data, f, ensure_ascii=False, indent=2)

            # logger.info(f"✅ 搜索历史已保存 "
            #       f"(history1: {len(merged_data['history1'])} 条 / "
            #       f"history2: {len(merged_data['history2'])} 条)，starred 已统一为整数")
            # ---------- 写回文件 ----------
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump({
                    "history1": merged_data["history1"],
                    "history2": merged_data["history2"],
                    "history3": merged_data["history3"]  # ✅ 单独保存，不参与合并
                }, f, ensure_ascii=False, indent=2)

                    # "history3": self.history3,  # ✅ 单独保存，不参与合并
            logger.info(f"✅ 搜索历史已保存 "
                  f"(h1: {len(merged_data['history1'])} / "
                  f"h2: {len(merged_data['history2'])} / "
                  f"h3: {len(merged_data['history3'])})")


        except Exception as e:
            messagebox.showerror("错误", f"保存搜索历史失败: {e}")

    def load_search_history(self):
        """从文件加载，支持 history3（仅加载与保存，不参与同步）"""
        h1, h2, h3 = [], [], []
        upgraded = False

        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # --- 标准化函数 ---
                def normalize_starred_field(history_list):
                    nonlocal upgraded
                    for r in history_list:
                        val = r.get("starred", 0)
                        if isinstance(val, bool):
                            r["starred"] = 1 if val else 0
                            upgraded = True
                        elif not isinstance(val, int):
                            r["starred"] = 0
                            upgraded = True

                def dedup(history):
                    seen = set()
                    result = []
                    for r in history:
                        q = r.get("query", "")
                        if q not in seen:
                            seen.add(q)
                            result.append(r)
                    return result

                raw_h1 = [self._normalize_record(r) for r in data.get("history1", [])]
                raw_h2 = [self._normalize_record(r) for r in data.get("history2", [])]
                raw_h3 = [self._normalize_record(r) for r in data.get("history3", [])]  # ✅ 新增

                normalize_starred_field(raw_h1)
                normalize_starred_field(raw_h2)
                normalize_starred_field(raw_h3)

                raw_h1, raw_h2, raw_h3 = map(dedup, (raw_h1, raw_h2, raw_h3))

                h1 = raw_h1[:self.his_limit]
                h2 = raw_h2[:self.his_limit]
                h3 = raw_h3[:self.his_limit]

                if upgraded:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump(
                            {"history1": raw_h1, "history2": raw_h2, "history3": raw_h3},
                            f, ensure_ascii=False, indent=2
                        )
                    logger.info("✅ 自动升级 search_history.json，starred 字段格式已统一")

            except Exception as e:
                messagebox.showerror("错误", f"加载搜索历史失败: {e}")

        return h1, h2, h3


    def load_search_history_h1h2(self):
        """从文件加载，只取最后 N 条作为当前编辑数据，并自动升级 starred 字段为整数"""
        h1, h2 = [], []
        upgraded = False  # 是否发生过格式升级

        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 自动兼容/升级 starred 字段
                def normalize_starred_field(history_list):
                    nonlocal upgraded
                    for r in history_list:
                        val = r.get("starred", 0)
                        if isinstance(val, bool):
                            r["starred"] = 1 if val else 0
                            upgraded = True
                        elif not isinstance(val, int):
                            # 出现异常类型也统一置0
                            r["starred"] = 0
                            upgraded = True

                raw_h1 = [self._normalize_record(r) for r in data.get("history1", [])]
                raw_h2 = [self._normalize_record(r) for r in data.get("history2", [])]

                # 升级字段
                normalize_starred_field(raw_h1)
                normalize_starred_field(raw_h2)

                # 去重函数
                def dedup(history):
                    seen = set()
                    result = []
                    for r in history:
                        q = r.get("query", "")
                        if q not in seen:
                            seen.add(q)
                            result.append(r)
                    return result

                raw_h1 = dedup(raw_h1)
                raw_h2 = dedup(raw_h2)

                # 只取最近 self.his_limit 条
                h1 = raw_h1[:self.his_limit] if len(raw_h1) > self.his_limit else raw_h1
                h2 = raw_h2[:self.his_limit] if len(raw_h2) > self.his_limit else raw_h2

                # 如果有升级，自动保存回文件（避免下次重复升级）
                if upgraded:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump({"history1": raw_h1, "history2": raw_h2}, f, ensure_ascii=False, indent=2)
                    logger.info("✅ 已自动升级 search_history.json 的 starred 字段为整数格式")

            except Exception as e:
                messagebox.showerror("错误", f"加载搜索历史失败: {e}")

        return h1, h2


    def _normalize_record(self, r):
        """兼容旧数据格式"""
        if isinstance(r, dict):
            # 如果 'query' 里面是字符串带字典形式，尝试提取
            q = r.get("query", "")
            try:
                q_dict = eval(q)
                if isinstance(q_dict, dict) and "query" in q_dict:
                    q = q_dict["query"]
            except:
                pass
            return {"query": q, "starred": r.get("starred", False), "note": r.get("note", "")}
        elif isinstance(r, str):
            return {"query": r, "starred":  0, "note": ""}
        else:
            return {"query": str(r), "starred":  0, "note": ""}

    # def switch_group(self, event=None):
    #     group = self.combo_group.get()
    #     self.current_key = group
    #     if group == "history1":
    #         self.current_history = self.history1
    #     elif group == "history2":
    #         self.current_history = self.history2
    #     elif group == "history3":
    #         self.current_history = self.history3  # ✅ 新增
    #     self.refresh_tree()

    def switch_group(self, event=None):
        self.clear_hits()
        if getattr(self, "_suppress_switch", False):
            return

        sel = self.combo_group.get()
        if sel == "history1":
            self.current_history = self.history1
            self.current_key = "history1"
        elif sel == "history2":
            self.current_history = self.history2
            self.current_key = "history2"
        elif sel == "history3":
            self.current_history = self.history3
            self.current_key = "history3"
        logger.info(f"[SWITCH] 当前分组切换到：{sel}")
        self.refresh_tree()


    def edit_query(self, iid):
        values = self.tree.item(iid, "values")
        if not values:
            return
        current_query = values[0]

        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == current_query), None)
        if idx is None:
            return

        record = self.current_history[idx]
        # new_query = self.askstring_at_parent(self.root, "修改 Query", "请输入新的 Query：", initialvalue=record.get("query", ""))
        new_query = askstring_at_parent_single(self.root, "修改 Query", "请输入新的 Query：", initialvalue=record.get("query", ""))
        if new_query and new_query.strip():
            new_query = new_query.strip()
            old_query = record["query"]
            # record["query"] = new_query
            if self.current_key == "history1":
                self.history1[idx]["query"] = new_query

            elif self.current_key == "history2":
                self.history2[idx]["query"] = new_query

            elif self.current_key == "history3":
                self.history3[idx]["query"] = new_query
                # --- 可选回调同步到主程序 ---
                if hasattr(self, "sync_history_callback") and callable(self.sync_history_callback):
                    try:
                        self.sync_history_callback(search_history3=self.history3)
                        self.refresh_tree()
                    except Exception as e:
                        logger.info(f"[警告] 同步 search_history3 失败: {e}")

                logger.info(f"✅ 已将 [{new_query}] 置顶 history3")

            # ✅ 设置全局标志（主窗口 sync_history 会读取）
            self._just_edited_query = (old_query, new_query)
            # self.sync_history_current(record)
            self.refresh_tree()
            # if self.current_key == "history1":
            self.use_query(new_query)
            # self.save_search_history()

    def add_query(self):
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入 Query")
            return

        # 判断是否为 6 位数字
        if (query.isdigit() or len(query) == 6):
            toast_message(self.root, "股票代码仅测试使用")
            return

        # 查重：是否已存在相同 query
        existing = next((item for item in self.current_history if item["query"] == query), None)

        if existing:
            # 如果已有星标或备注，则仅置顶，不覆盖
            if existing.get("starred", 0) > 0 or existing.get("note", "").strip():
                self.current_history.remove(existing)
                self.current_history.insert(0, existing)
            else:
                # 没有星标/备注，替换为新的记录
                self.current_history.remove(existing)
                self.current_history.insert(0, {"query": query, "starred": 0, "note": ""})
        else:
            # 新增记录
            self.current_history.insert(0, {"query": query, "starred": 0, "note": ""})

        if self.current_key == "history1":
            self.history1 = self.current_history
        elif  self.current_key == "history2":
            self.history2 = self.current_history
        elif  self.current_key == "history3":
            self.history3 = self.current_history

        self.refresh_tree()
        self.entry_query.delete(0, tk.END)
        self.use_query(query)
        # self.save_search_history()

    def on_click_star(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#2":  # 第二列是星标
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        idx = int(row_id) - 1
        if 0 <= idx < len(self.current_history):
            record = self.current_history[idx]
            # 原布尔值兼容转 int
            old_val = record.get("starred", 0)
            if isinstance(old_val, bool):
                old_val = 1 if old_val else 0

            # 循环 0 → 1 → 2 → 3 → 4 → 0
            record["starred"] = (old_val + 1) % 5
            self.refresh_tree()

    def get_centered_window_position_query(self, parent, win_width, win_height, margin=10):
        """
        自动定位弹窗在鼠标附近（多屏+高DPI兼容）
        """
        # 获取鼠标全局坐标
        mx = parent.winfo_pointerx()
        my = parent.winfo_pointery()

        # DPI 缩放修正（防止4K屏太小）
        # scale = get_system_dpi_scale()
        scale = 1
        win_width = int(win_width * scale)
        win_height = int(win_height * scale)

        # 默认在鼠标右侧显示
        x = mx + margin
        y = my - win_height // 2

        # -----------------------------
        # 获取所有显示器信息
        # -----------------------------
        monitors = []
        try:
            for handle_tuple in win32api.EnumDisplayMonitors():
                info = win32api.GetMonitorInfo(handle_tuple[0])
                monitors.append(info["Monitor"])  # (left, top, right, bottom)
        except Exception as e:
            logger.info(f"[WARN] 获取显示器信息失败: {e}")

        # 如果检测不到，使用主屏幕尺寸
        if not monitors:
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            monitors = [(0, 0, screen_width, screen_height)]

        # -----------------------------
        # 检查并限制窗口在显示器边界内
        # -----------------------------
        hit_monitor = None
        for left, top, right, bottom in monitors:
            if left <= mx < right and top <= my < bottom:
                hit_monitor = (left, top, right, bottom)
                break

        if hit_monitor:
            left, top, right, bottom = hit_monitor
            # 如果右边放不下，则放左侧
            if x + win_width > right:
                x = mx - win_width - margin

            # 防止超出边界
            x = max(left, min(x, right - win_width))
            y = max(top, min(y, bottom - win_height))
            logger.info(f"✅ 命中屏幕 ({left},{top},{right},{bottom}) scale={scale:.2f} → ({x},{y})")
        else:
            # 未命中任何屏幕则居中主屏
            main_left, main_top, main_right, main_bottom = monitors[0]
            x = main_left + (main_right - main_left - win_width) // 2
            y = main_top + (main_bottom - main_top - win_height) // 2
            logger.info(f"⚠️ 未命中屏幕, 使用主屏居中 scale={scale:.2f} → ({x},{y})")

        return int(x), int(y)


    def askstring_at_parent(self, parent, title, prompt, initialvalue=""):

        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(True, True)  # ✅ 允许自由拉伸

        # --- 计算窗口初始位置 ---
        screen_width = win32api.GetSystemMetrics(0)
        screen_width_limit = screen_width * 0.8
        char_width = 10
        min_width = int(400 * self.root.scale_factor)
        max_width = 2000 if 1000 * self.root.scale_factor < screen_width_limit else screen_width_limit
        win_width = max(min_width, min(len(initialvalue) * char_width + 100, max_width))
        win_height = 120

        x, y = self.get_centered_window_position_query(parent, win_width, win_height)
        dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
        logger.info(f"askstring_at_parent : {int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

        result = {"value": None}

        # --- 提示文字（自动换行） ---
        lbl = tk.Label(
            dlg,
            text=prompt,
            anchor="w",
            justify="left",        # 多行文字左对齐
            wraplength=int(win_width * 0.9)  # ✅ 超过宽度自动换行
        )
        lbl.pack(pady=(10, 6), padx=10, fill="x")

        # --- 输入框 ---
        entry = ttk.Entry(dlg)
        entry.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        entry.insert(0, initialvalue)
        entry.focus_set()

        # --- 按钮区 ---
        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=(0, 10))
        tk.Button(frame_btn, text="确定", width=10, command=lambda: on_ok()).pack(side="left", padx=6)
        tk.Button(frame_btn, text="取消", width=10, command=lambda: on_cancel()).pack(side="left", padx=6)

        # --- 回调函数 ---
        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        # ✅ 绑定 ESC 关闭
        dlg.bind("<Escape>", lambda e: on_cancel())
        dlg.bind("<Return>", lambda e: on_ok())

        # ✅ 让输入框随窗口变化自动扩展
        dlg.grid_rowconfigure(1, weight=1)
        dlg.grid_columnconfigure(0, weight=1)

        dlg.grab_set()
        parent.wait_window(dlg)
        return result["value"]



    def on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        # 取出该行的 query（更可靠）
        values = self.tree.item(row_id, 'values')
        if not values:
            return
        query_text = values[0]

        # 在 current_history 中找到对应记录（按 query 匹配）
        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == query_text), None)
        if idx is None:
            # 兜底：也可能 iid 就是索引
            try:
                idx = int(row_id) - 1
            except Exception:
                return

        record = self.current_history[idx]

        # 如果是备注列（第三列）
        if col == "#3":

            new_note = self.askstring_at_parent(self.root, "修改备注", "请输入新的备注：", initialvalue=record.get("note", ""))
            if new_note is not None:
                record["note"] = new_note
                # ⚠️ 同步到主视图
                if self.current_key == "history1":
                    self.history1[idx]["note"] = new_note
                elif self.current_key == "history2":
                    self.history2[idx]["note"] = new_note
                elif self.current_key == "history3":
                    self.history3[idx]["note"] = new_note
                # if self.current_key != "history1":
                self.current_history[idx]["note"] = new_note
                # 同步到主视图的 combobox values（如果你用的是 query 字符串列表）
                # 如果你维护 combobox values 为 [r["query"] for r in self.history1]，备注不影响 combobox
                self.refresh_tree()
                # self.save_search_history()
            return

        # 否则把 query 放到输入框准备编辑（原逻辑）
        # self.editing_idx = idx
        # self.entry_query.delete(0, tk.END)
        # self.entry_query.insert(0, record["query"])

        self.use_query(record["query"])

    def use_query(self,query=None):
        if query is None:
            item = self.tree.selection()
            if not item:
                return
            idx = int(item[0]) - 1
            query = self.current_history[idx]["query"]

        # 推送到 tk 主界面的输入框 / 下拉框
        if self.current_key == "history1":
            self.search_var1.set(query)  # 直接设置 Entry/Combobox
            # 可选：更新下拉列表
            # self.history1 = self.current_history
            if query not in self.search_combo1["values"]:
                values = list(self.search_combo1["values"])
                values.insert(0, query)
                self.search_combo1["values"] = values
        elif self.current_key == "history2": # history2
            self.search_var2.set(query)
            # self.history2 = self.current_history
            if query not in self.search_combo2["values"]:
                values = list(self.search_combo2["values"])
                values.insert(0, query)
                self.search_combo2["values"] = values
        # elif self.current_key == "history3": # history2
        #     # self.search_var3.set(query)
        #     # # self.history3 = self.current_history
        #     # if query not in self.search_combo3["values"]:
        #     #     values = list(self.search_combo3["values"])
        #     #     values.insert(0, query)
        #     #     self.search_combo3["values"] = values
        #     self.sync_history_callback(search_history3=self.history3)

        elif self.current_key == "history3":
            # query = self.tree.item(self.tree.focus(), "values")[0]  # 获取点击的 query
            item = self.tree.selection()
            if not item:
                return
            idx = int(item[0]) - 1
            query = self.current_history[idx]["query"]

            history_list = self.current_history  # 当前指向的列表（字典结构）

            # --- 查找条目索引 ---
            idx = next((i for i, item in enumerate(history_list) if item.get("query") == query), None)
            if idx is not None and idx != 0:
                # 将已有条目移动到最上面
                item = history_list.pop(idx)
                history_list.insert(0, item)
            elif idx is None:
                # 新条目，直接插入最上面
                history_list.insert(0, {"query": query, "starred": 0, "note": ""})
            self.current_history =  history_list
            self.history3 =  self.current_history    
            # # --- 更新下拉框显示 ---
            # values = [item["query"] for item in history_list]
            # if hasattr(self, "search_combo3"):
            #     self.search_combo3["values"] = values
            #     self.search_combo3.set(query)

            # # --- 同步 Entry/Combobox 文本 ---
            # if hasattr(self, "search_var3"):
            #     self.search_var3.set(query)

            # --- 可选回调同步到主程序 ---
            if hasattr(self, "sync_history_callback") and callable(self.sync_history_callback):
                try:
                    self.sync_history_callback(search_history3=self.history3)
                    self.refresh_tree()
                except Exception as e:
                    logger.info(f"[警告] 同步 search_history3 失败: {e}")

            logger.info(f"✅ 已将 [{query}] 置顶 history3")


    # ========== 右键菜单 ==========
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item: return
        self.tree.selection_set(item)
        menu = tk.Menu(self.editor_frame, tearoff=0)
        menu.add_command(label="使用", command=lambda: self.use_query())
        menu.add_command(label="编辑Query", command=lambda: self.edit_query(item))
        # menu.add_command(label="置顶", command=lambda: self.move_to_top(item))
        menu.add_command(label="编辑框", command=lambda: self.up_to_entry(item))
        menu.add_command(label="删除", command=lambda: self.delete_item(item))
        menu.tk_popup(event.x_root, event.y_root)


    def on_delete_key(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        self.delete_item(selected[0])
    
    def sync_history_current(self, record, action="delete", history_key=None):
        """
        同步主窗口与 QueryHistoryManager 的状态。
        支持 delete / add，带防循环保护与分组标识。
        """


        # if history_key == 'history3':
        #     return

        if history_key is None:
            history_key = self.current_key

        query = record.get("query")
        if not query:
            return

        # --- 选择目标控件与历史 ---
        if history_key == "history1":
            combo, var, target = self.search_combo1, self.search_var1, self.history1
        elif history_key == "history2":
            combo, var, target = self.search_combo2, self.search_var2, self.history2
        elif history_key == "history3":
            combo, var, target = self.search_combo3, self.search_var3, self.history3
        # --- 修改本地历史数据 ---
        if action == "delete":
            target[:] = [r for r in target if r.get("query") != query]
            if combo:
                combo['values'] = [r.get("query") for r in target]
            if var and var.get() == query:
                var.set("")
        elif action == "add":
            if not any(r.get("query") == query for r in target):
                target.insert(0, record.copy())
            if combo:
                combo['values'] = [r.get("query") for r in target]

        # --- 回调主窗口同步 ---
        if callable(self.sync_history_callback):
            # 防止主窗口在同步时递归触发回调
            if hasattr(self.root, "_suppress_sync") and self.root._suppress_sync:
                return
            try:
                if history_key == "history1":
                    self.sync_history_callback(search_history1=self.history1)
                    # self.sync_history_callback(search_history1=self.history1, current_key = history_key)
                elif history_key == "history2":
                    self.sync_history_callback(search_history2=self.history2)
                    # self.sync_history_callback(search_history2=self.history2, current_key = history_key)
                elif history_key == "history3":
                    self.sync_history_callback(search_history3=self.history3)
                    # self.sync_history_callback(search_history3=self.history3, current_key = history_key)

            except Exception as e:
                logger.info(f"[SYNC ERR] {e}")

        # --- 刷新 UI，但防止误触 switch ---
        suppress_state = getattr(self, "_suppress_switch", False)
        self._suppress_switch = True
        try:
            self.refresh_tree()
        finally:
            self._suppress_switch = suppress_state


    def delete_item(self, iid):
        idx = int(iid) - 1
        if not (0 <= idx < len(self.current_history)):
            return

        record = self.current_history.pop(idx)

        # 精确识别所属分组
        # if self.current_history is self.history2:
        #     history_key = "history2"
        # else:
        #     history_key = "history1"

        history_key = self.current_key

        # 保存完整删除记录（含 note/starred）
        self.deleted_stack.append({
            "record": record.copy(),
            "history_key": history_key,
            "index": idx
        })

        # 🔹 在刷新期间禁止触发 group 切换
        self._suppress_switch = True

        # 🔹 通知主窗口（带 action 和 history_key）
        self.sync_history_current(record, action="delete", history_key=history_key)

        # 🔹 刷新本地 UI
        self.refresh_tree()

        self._suppress_switch = False

        logger.info(f"[DEL] 从 {history_key} 删除 {record.get('query')}")


    def undo_delete(self, event=None):
        if not self.deleted_stack:
            toast_message(self.root, "没有可撤销的记录", 1200)
            return

        last_deleted = self.deleted_stack.pop()
        record = last_deleted["record"]
        history_key = last_deleted["history_key"]
        index = last_deleted["index"]

        # 目标列表
        if history_key == "history1":
            target_history = self.history1
        elif history_key == "history2":
            target_history = self.history2
        elif history_key == "history3":
            target_history = self.history3
        # 防止重复
        if any(r.get("query") == record.get("query") for r in target_history):
            toast_message(self.root, f"已存在：{record.get('query')}", 1200)
            return

        if 0 <= index <= len(target_history):
            target_history.insert(index, record)
        else:
            target_history.insert(0, record)

        # 显式传入 history_key
        self.sync_history_current(record, action="add", history_key=history_key)

        toast_message(self.root, f"已恢复：{record.get('query')}", 1500)

    def up_to_entry(self,iid):
        values = self.tree.item(iid, "values")
        if not values:
            return
        current_query = values[0]
        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == current_query), None)
        if idx is None:
            return
        record = self.current_history[idx]
        self.entry_query.delete(0, tk.END)
        self.entry_query.insert(0, record["query"])


    def refresh_tree(self):
        """
        刷新 Treeview 显示
        - 当前历史 self.current_history 自动同步
        - 根据 record['hit'] 设置 hit 列显示，并设置背景颜色
        """
        # 自动同步当前显示的历史
        # self.current_history = self.history1 if self.current_key == "history1" else self.history2

        # 清空 Treeview
        self.tree.delete(*self.tree.get_children())

        # 配置 tag 颜色
        self.tree.tag_configure("hit", background="#d1ffd1")   # 命中绿色
        self.tree.tag_configure("miss", background="#ffd1d1")  # 未命中红色
        self.tree.tag_configure("normal", background="#ffffff") # 默认白色

        for idx, record in enumerate(self.current_history, start=1):
            star_count = record.get("starred", 0)
            if isinstance(star_count, bool):
                star_count = 1 if star_count else 0
            star_text = "★" * star_count
            note = record.get("note", "")
            query_text = record.get("query", "")

            # hit 列显示
            hit = record.get("hit", None)
            if isinstance(hit, int):
                if hit == 0:
                    hit_text = "❌"
                    tag = "miss"
                elif hit == 1:
                    hit_text = "✅"
                    tag = "hit"
                else:  # hit > 1
                    hit_text = str(hit)
                    tag = "hit"  # 多于1也算命中
            elif hit is True:
                hit_text = "✅"
                tag = "hit"
            elif hit is False:
                hit_text = "❌"
                tag = "miss"
            else:
                hit_text = ""
                tag = "normal"

            # 插入 Treeview
            self.tree.insert("", "end", iid=str(idx),
                             values=(query_text, star_text, note, hit_text),
                             tags=(tag,))


    def clear_hits(self):
        for record in self.current_history:
            record.pop("hit", None)

    def on_test_click(self):
            if callable(self.test_callback):
                self.test_callback(onclick=True)

    def test_code(self, code_data):
        """
        code_data: dict, 当前 code 的行情数据
        返回每条 query 是否命中
        """
        # queries = getattr(self, "history1", []) + getattr(self, "history2", [])
        queries = getattr(self, "current_history", [])
        return test_code_against_queries(code_data, queries)

# toast_message （使用你给定的实现）
def toast_message(master, text, duration=1500):
    """短暂提示信息（浮层，不阻塞）"""
    toast = tk.Toplevel(master)
    toast.overrideredirect(True)
    toast.attributes("-topmost", True)
    label = tk.Label(toast, text=text, bg="black", fg="white", padx=10, pady=1)
    label.pack()
    try:
        master.update_idletasks()
        master_x = master.winfo_rootx()
        master_y = master.winfo_rooty()
        master_w = master.winfo_width()
    except Exception:
        master_x, master_y, master_w = 100, 100, 400
    toast.update_idletasks()
    toast_w = toast.winfo_width()
    toast_h = toast.winfo_height()
    toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
    toast.after(duration, toast.destroy)


# class ColumnSetManager(tk.Toplevel):
#     def __init__(self, master, all_columns, config, on_apply_callback, default_cols, auto_apply_on_init=False):
#         super().__init__(master)
#         self.title("列组合管理器")
#         # 基础尺寸（用于初始化宽度 fallback）
#         # 如果不希望初始显示窗口（隐藏）
#         self.auto_apply_on_init = auto_apply_on_init
#         if self.auto_apply_on_init:
#             self.withdraw()  # 先隐藏窗口

#         self.width = 800
#         self.height = 500
#         self.geometry(f"{self.width}x{self.height}")

#         # 参数
#         self.all_columns = list(all_columns)
#         self.no_filtered = []
#         self.config = config if isinstance(config, dict) else {}
#         self.on_apply_callback = on_apply_callback
#         self.default_cols = list(default_cols)

#         # 状态
#         self.current_set = list(self.config.get("current", self.default_cols.copy()))
#         self.saved_sets = list(self.config.get("sets", []))  # 格式：[{ "name": str, "cols": [...] }, ...]

#         # 存放 checkbutton 的 BooleanVar，防 GC
#         self._chk_vars = {}

#         # 拖拽数据（用于 tag 拖拽）
#         self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}

#         # 防抖 job id
#         self._resize_job = None

#         # 构建 UI
#         self._build_ui()

#         # 延迟首次布局（保证 winfo_width() 可用）
#         self.after(80, self.update_grid)

#         # 绑定窗口 resize（防抖）
#         # self.bind("<Configure>", self._on_resize)

#     def _build_ui(self):
#         # 主容器：左右两栏（左：选择区 + 当前组合；右：已保存组合）
#         self.main = ttk.Frame(self)
#         self.main.pack(fill=tk.BOTH, expand=True)

#         top = ttk.Frame(self.main)
#         top.pack(fill=tk.BOTH, expand=True, padx=6, pady=1)

#         left = ttk.Frame(top)
#         left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

#         right = ttk.Frame(top, width=220)
#         right.pack(side=tk.RIGHT, fill=tk.Y)
#         right.pack_propagate(False)

#         # 搜索栏（放在 left 顶部）
#         search_frame = ttk.Frame(left)
#         search_frame.pack(fill=tk.X, pady=(0,6))
#         ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
#         self.search_var = tk.StringVar()
#         entry = ttk.Entry(search_frame, textvariable=self.search_var)
#         entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,0))
#         entry.bind("<KeyRelease>", lambda e: self._debounced_update())

#         # 列选择区（canvas + scrollable_frame）
#         grid_container = ttk.Frame(left)
#         grid_container.pack(fill=tk.BOTH, expand=True)

#         self.canvas = tk.Canvas(grid_container, height=160)
#         self.vscroll = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
#         self.canvas.configure(yscrollcommand=self.vscroll.set)

#         self.inner_frame = ttk.Frame(self.canvas)  # 放 checkbuttons 的 frame
#         # 当 inner_frame size 改变时，同步调整 canvas scrollregion
#         self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

#         self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")

#         self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
#         self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

#         # 鼠标滚轮在 canvas 上滚动（适配 Windows 与 Linux）
#         self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel(True))
#         self.canvas.bind("<Leave>", lambda e: self._bind_mousewheel(False))

#         # 当前组合横向标签（自动换行 + 拖拽）
#         current_lf = ttk.LabelFrame(left, text="当前组合")
#         current_lf.pack(fill=tk.X, pady=(6,0))
#         self.current_frame = tk.Frame(current_lf, height=60)
#         self.current_frame.pack(fill=tk.X, padx=4, pady=6)
#         # 确保 current_frame 能获取尺寸变化事件
#         self.current_frame.bind("<Configure>", lambda e: self._debounced_refresh_tags())

#         # 右侧：已保存组合列表与管理按钮
#         ttk.Label(right, text="已保存组合").pack(anchor="w", padx=6, pady=(6,0))
#         self.sets_listbox = tk.Listbox(right, exportselection=False)
#         self.sets_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
#         # 单击选中高亮 → 更新当前选中组合名（但不加载）
#         self.sets_listbox.bind("<<ListboxSelect>>", self.on_select_saved_set)

#         self.sets_listbox.bind("<Double-1>", lambda e: self.load_selected_set())

#         sets_btns = ttk.Frame(right)
#         sets_btns.pack(fill=tk.X, padx=6, pady=(0,6))
#         ttk.Button(sets_btns, text="加载", command=self.load_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True)
#         ttk.Button(sets_btns, text="删除", command=self.delete_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

#         self.lbl_current_set = ttk.Label(right, text="当前选中: (无)")
#         self.lbl_current_set.pack(anchor="w", padx=6, pady=(0,4))


#         # 底部按钮（全宽）
#         bottom = ttk.Frame(self)
#         bottom.pack(fill=tk.X, padx=6, pady=6)
#         ttk.Button(bottom, text="保存组合", command=self.save_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X)
#         ttk.Button(bottom, text="应用组合", command=self.apply_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=6)
#         ttk.Button(bottom, text="恢复默认", command=self.restore_default).pack(side=tk.LEFT, expand=True, fill=tk.X)

#         self.bind("<Alt-c>",lambda e:self.open_column_manager_editor())
#         # 填充保存组合列表
#         self.refresh_saved_sets()

class ColumnSetManager(tk.Toplevel):
    def __init__(self, master, all_columns, config, on_apply_callback, default_cols, auto_apply_on_init=False):
        super().__init__(master)
        self.master = master
        self.title("列组合管理器")
        # ---------- 基础尺寸 ----------
        self.width = 800
        self.height = 500
        self.geometry(f"{self.width}x{self.height}")

        # ---------- 参数 ----------
        self.all_columns = list(all_columns)
        self.config = config if isinstance(config, dict) else {}
        self.on_apply_callback = on_apply_callback
        self.default_cols = list(default_cols)
        self.auto_apply_on_init = auto_apply_on_init

        # ---------- 状态 ----------
        self.current_set = list(self.config.get("current", self.default_cols.copy()))
        self.saved_sets = list(self.config.get("sets", []))
        self._chk_vars = {}
        self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
        self._resize_job = None

        # ---------- 构建 UI ----------
        self._build_ui()

        # 延迟首次布局
        self.after(80, self.update_grid)

        # ---------- 自动应用列组合 ----------
        if self.auto_apply_on_init:
            try:
                self.withdraw()  # 先隐藏
                self.set_current_set()  # 调用回调更新列
                # 可选择应用后显示或保持隐藏
                # self.deiconify()
            except Exception as e:
                traceback.print_exc()
                logger.info(f"⚠️ 自动应用列组合失败：{e}")

    def _build_ui(self):
        # ---------- 高 DPI 初始化 ----------
        # try:
        #     from ctypes import windll
        #     windll.shcore.SetProcessDpiAwareness(1)  # Windows 高 DPI 感知
        # except:
        #     pass
        # dpi_scale = self.winfo_fpixels('1i') / 72  # 获取 DPI 缩放比例
        dpi_scale = self.master.scale_factor
        # dpi_scale = get_windows_dpi_scale_factor()
        base_width, base_height = 800, 500
        self.width = int(base_width * dpi_scale)
        self.height = int(base_height * dpi_scale)
        self.geometry(f"{self.width}x{self.height}")

        # ---------- 主容器 ----------
        self.main = ttk.Frame(self)
        self.main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(self.main)
        top.pack(fill=tk.BOTH, expand=True, padx=6, pady=1)

        # 使用 grid 管理左右比例，左 3/4，右 1/4
        top.grid_columnconfigure(0, weight=3)
        top.grid_columnconfigure(1, weight=1)
        top.grid_rowconfigure(0, weight=1)

        # 左侧容器
        left = ttk.Frame(top)
        left.grid(row=0, column=0, sticky="nsew")

        # 右侧容器
        right = ttk.Frame(top)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_propagate(False)

        # ---------- 搜索栏 ----------
        search_frame = ttk.Frame(left)
        search_frame.pack(fill=tk.X, pady=(0,6))
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,0))
        entry.bind("<KeyRelease>", lambda e: self._debounced_update())

        # ---------- 列选择区（Canvas + Scrollable Frame） ----------
        grid_container = ttk.Frame(left)
        grid_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(grid_container)
        self.vscroll = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.inner_frame = ttk.Frame(self.canvas)
        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_mousewheel(False))

        # ---------- 当前组合标签 ----------
        current_lf = ttk.LabelFrame(left, text="当前组合")
        current_lf.pack(fill=tk.X, pady=(6,0))
        self.current_frame = tk.Frame(current_lf)
        self.current_frame.pack(fill=tk.X, padx=4, pady=6)
        self.current_frame.bind("<Configure>", lambda e: self._debounced_refresh_tags())

        # ---------- 右侧：已保存组合列表 ----------
        ttk.Label(right, text="已保存组合").pack(anchor="w", padx=6, pady=(6,0))
        self.sets_listbox = tk.Listbox(right, exportselection=False)
        self.sets_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.sets_listbox.bind("<<ListboxSelect>>", self.on_select_saved_set)
        self.sets_listbox.bind("<Double-1>", lambda e: self.load_selected_set())

        sets_btns = ttk.Frame(right)
        sets_btns.pack(fill=tk.X, padx=6, pady=(0,6))
        ttk.Button(sets_btns, text="加载", command=self.load_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sets_btns, text="删除", command=self.delete_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        self.lbl_current_set = ttk.Label(right, text="当前选中: (无)")
        self.lbl_current_set.pack(anchor="w", padx=6, pady=(0,4))

        # ---------- 底部按钮 ----------
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(bottom, text="保存组合", command=self.save_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(bottom, text="应用组合", command=self.apply_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=6)
        ttk.Button(bottom, text="恢复默认", command=self.restore_default).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ---------- 快捷键 ----------
        self.bind("<Alt-c>", lambda e: self.open_column_manager_editor())
        self.bind("<Escape>", lambda e: self.open_column_manager_editor())

        # ---------- 填充保存组合列表 ----------
        self.refresh_saved_sets()

        # ---------- 自动应用当前列组合 ----------
        if self.auto_apply_on_init:
            try:
                self.set_current_set()
            except Exception as e:
                traceback.print_exc()
                logger.info(f"⚠️ 自动应用列组合失败：{e}")



  
    def _apply_dpi_scaling_Column(self,scale_factor=None):
        """自动计算并设置 Tkinter 的内部 DPI 缩放。"""
        # 获取系统的缩放因子 (例如 2.0)

        if not scale_factor: 
            self.scale_factor = get_windows_dpi_scale_factor()
            scale_factor = self.scale_factor
        else:
            self.scale_factor = scale_factor
        logger.info(f'_apply_dpi_scaling_Column scale_factor : {scale_factor}')

        if scale_factor > 1.0:
            # Tkinter 'scaling' 值 = (系统 DPI / 72 DPI)
            logger.info(f'Column scale_factor apply: {scale_factor} {self.scale_factor}')
            tk_scaling_value = (scale_factor * DEFAULT_DPI) / 72.0 
            # 这一步会放大所有基于像素定义的组件尺寸和默认字体大小
            self.tk.call('tk', 'scaling', tk_scaling_value)

            logger.info(f"✅ Column DPI 自动缩放应用于 {scale_factor}x ({tk_scaling_value})")
            
            # 3. 💥 关键：配置 Treeview 样式以统一处理行高和字体
            style = ttk.Style(self)
            
            # a. 设置行高 (Rowheight)
            BASE_ROW_HEIGHT = 22  # 基础行高像素
            scaled_row_height = int(BASE_ROW_HEIGHT * scale_factor)
            
            # b. 获取缩放后的字体 (可选，但推荐用于清晰度)
            # Tkinter 的 'tk scaling' 已经缩放了默认字体，但显式配置更稳健。
            # 这里我们使用一个基准字体，通常是 'TkDefaultFont'
            default_font = self.default_font
            
            # 使用 ttk.Style 配置所有 Treeview 实例
            # 注意：配置行高必须在 Treeview 元素上完成
            style.configure(
                "Treeview", 
                rowheight=scaled_row_height,
                font=default_font  # 保持使用 Tkinter 已经缩放过的默认字体
            )
            
            # 配置 Heading 字体 (通常需要单独设置，确保列标题也适配)
            style.configure(
                "Treeview.Heading",
                font=default_font
            )
            
            logger.info(f"✅ Column DPI 自动缩放应用于 {scale_factor}x，Treeview 行高设置为 {scaled_row_height}")

    def open_column_manager_editor(self):
        """切换显示/隐藏"""
        if self.state() == "withdrawn":
            # 已隐藏 → 显示
            self.deiconify()
            self.lift()
            self.focus_set()
        else:
            # 已显示 → 隐藏
            self.withdraw()


    # ---------------------------
    # 鼠标滚轮支持（只在 canvas 区生效）
    # ---------------------------
    def _bind_mousewheel(self, bind: bool):
        # Windows: <MouseWheel> with event.delta; Linux: Button-4/5
        if bind:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            self.canvas.bind_all("<Button-4>", self._on_mousewheel)
            self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        else:
            try:
                self.canvas.unbind_all("<MouseWheel>")
                self.canvas.unbind_all("<Button-4>")
                self.canvas.unbind_all("<Button-5>")
            except Exception:
                pass

    def _on_mousewheel(self, event):
        # cross-platform wheel handling
        if event.num == 4:  # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:  # Linux scroll down
            self.canvas.yview_scroll(1, "units")
        else:
            # Windows / Mac
            delta = int(-1*(event.delta/120))
            self.canvas.yview_scroll(delta, "units")

    def _debounced_update(self):
        self.update_grid()

    def _debounced_refresh_tags(self):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(180, self.refresh_current_tags)

    def default_filter(self,c):
        if c in self.current_set:
            return True
        # keywords = ["perc","percent","trade","volume","boll","macd","ma"]
        keywords = ["perc","status","obs","hold","bull","has","lastdu","red","ma"]
        return any(k in c.lower() for k in keywords)

    # ---------------------------
    # 列选择区更新（Checkbuttons 自动排列）
    # ---------------------------
    def update_grid(self):
        # 清空旧的 checkbuttons
        for w in self.inner_frame.winfo_children():
            w.destroy()
        self._chk_vars.clear()

        # filter
        search = (self.search_var.get() or "").lower()
        # logger.info(f'search : {search}')
        if search == "":
            filtered = [c for c in self.all_columns if self.default_filter(c)]
        elif search == "no" or search == "other":
            filtered = [c for c in self.all_columns if not self.default_filter(c)]
        else:
            filtered = [c for c in self.all_columns if search in c.lower()]


        filtered = filtered[:200]  # 可以扩展，但前面限制为 50/200

        # 计算每行列数（使用 canvas 宽度 fallback）
        self.update_idletasks()
        total_width = self.canvas.winfo_width() if self.canvas.winfo_width() > 600 else self.width
        col_w = 100
        cols_per_row = max(3, total_width // col_w - 2)

        # 计算高度（最多显示 max_rows 行）
        rows_needed = (len(filtered) + cols_per_row - 1) // cols_per_row
        max_rows = 4
        row_h = 30
        canvas_h = min(rows_needed, max_rows) * row_h
        self.canvas.config(height=canvas_h)
        logger.info(f'max_rows:{max_rows} rows_needed:{rows_needed} canvas_h:{canvas_h}')
        for i, col in enumerate(filtered):
            var = tk.BooleanVar(value=(col in self.current_set))
            self._chk_vars[col] = var
            chk = ttk.Checkbutton(self.inner_frame, text=col, variable=var,
                                  command=lambda c=col, v=var: self._on_check_toggle(c, v.get()))
            chk.grid(row=i // cols_per_row, column=i % cols_per_row, sticky="w", padx=4, pady=3)

        # 刷新当前组合标签显示
        # logger.info(f'update_grid')
        self.refresh_current_tags()

    def _on_check_toggle(self, col, state):
        if state:
            if col not in self.current_set:
                self.current_set.append(col)
        else:
            if col in self.current_set:
                self.current_set.remove(col)
        # logger.info(f'_on_check_toggle')
        self.refresh_current_tags()

    # ---------------------------
    # 当前组合标签显示 + 拖拽重排
    # ---------------------------
    def refresh_current_tags(self):
        # 清空
        for w in self.current_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # 可能窗口刚弹出，宽度还没算好 -> fallback
        max_w = self.current_frame.winfo_width()
        if not max_w or max_w < 20:
            max_w = self.width - 40

        # 计算每个标签位置并 place
        y = 0
        x = 4
        row_h = 28
        padding = 6

        # 用于存放标签和位置信息
        self._tag_widgets = []

        for idx, col in enumerate(self.current_set):
            lbl = tk.Label(self.current_frame, text=col, bd=1, relief="solid", padx=6, pady=2, bg="#e8e8e8")
            lbl.update_idletasks()
            try:
                w_req = lbl.winfo_reqwidth()
            except tk.TclError:
                w_req = 80
            if x + w_req > max_w - 10:
                # 换行
                y += row_h
                x = 4

            # place at (x,y)
            lbl.place(x=x, y=y)
            # 保存 widget 及位置数据（仅用于拖拽计算）
            self._tag_widgets.append({"widget": lbl, "x": x, "y": y, "w": w_req, "idx": idx})
            # 绑定拖拽事件（闭包捕获 idx）
            lbl.bind("<Button-1>", lambda e, i=idx: self._start_drag(e, i))
            lbl.bind("<B1-Motion>", self._on_drag)
            lbl.bind("<ButtonRelease-1>", self._end_drag)
            x += w_req + padding

        # 更新 frame 高度以容纳所有行
        total_height = y + row_h + 4
        try:
            self.current_frame.config(height=total_height)
            # logger.info(f'total_height:{total_height}')

        except Exception:
            pass

    def _start_drag(self, event, idx):
        """开始拖拽"""
        widget = event.widget
        widget.lift()
        self._drag_data = {
            "widget": widget,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "idx": idx,
        }

        # --- 安全创建提示线 ---
        try:
            if not hasattr(self, "_insert_line") or not self._insert_line.winfo_exists() \
                    or self._insert_line.master != self.current_frame:
                self._insert_line = tk.Frame(self.current_frame, bg="#0078d7", width=2, height=26)
        except Exception:
            self._insert_line = tk.Frame(self.current_frame, bg="#0078d7", width=2, height=26)

        try:
            self._insert_line.place_forget()
        except Exception:
            pass

        logger.info(f"_start_drag {idx}")


    def _on_drag(self, event):
        """拖拽中"""
        lbl = self._drag_data.get("widget")
        if not lbl:
            return

        # --- 移动标签跟随光标 ---
        frame_x = self.current_frame.winfo_rootx()
        frame_y = self.current_frame.winfo_rooty()
        new_x = event.x_root - frame_x - 10
        new_y = event.y_root - frame_y - 8

        try:
            lbl.place(x=new_x, y=new_y)
        except Exception:
            return

        # --- 计算插入位置 ---
        drop_cx = event.x_root - frame_x
        drop_cy = event.y_root - frame_y
        centers = []

        for info in getattr(self, "_tag_widgets", []):
            w = info["widget"]
            if not w.winfo_exists() or w is lbl:
                continue
            cx = w.winfo_x() + info["w"] / 2
            cy = w.winfo_y() + 14  # 行中心
            centers.append((cx, cy, w, info["idx"]))

        if not centers:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place_forget()
            return

        # --- 找最近标签 ---
        centers.sort(key=lambda x: ((x[0] - drop_cx) ** 2 + (x[1] - drop_cy) ** 2))
        nearest_cx, nearest_cy, nearest_widget, nearest_idx = centers[0]

        # 判断插入线位置（在前或在后）
        if drop_cx < nearest_cx:
            x_line = nearest_widget.winfo_x() - 2
            y_line = nearest_widget.winfo_y()
        else:
            x_line = nearest_widget.winfo_x() + nearest_widget.winfo_width() + 2
            y_line = nearest_widget.winfo_y()

        # --- 显示插入提示线 ---
        try:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place(x=x_line, y=y_line)
                self._insert_line.lift()
        except Exception:
            pass


    def _end_drag(self, event):
        """拖拽结束"""
        lbl = self._drag_data.get("widget")
        orig_idx = self._drag_data.get("idx")

        # 隐藏插入线
        try:
            if hasattr(self, "_insert_line") and self._insert_line.winfo_exists():
                self._insert_line.place_forget()
        except Exception:
            pass

        if not lbl or orig_idx is None:
            self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
            return

        # --- 计算拖放位置 ---
        frame_x = self.current_frame.winfo_rootx()
        frame_y = self.current_frame.winfo_rooty()
        drop_cx = event.x_root - frame_x
        drop_cy = event.y_root - frame_y

        centers = []
        for info in getattr(self, "_tag_widgets", []):
            w = info["widget"]
            if not w.winfo_exists() or w is lbl:
                continue
            cx = w.winfo_x() + info["w"] / 2
            cy = w.winfo_y() + 14
            centers.append((cx, cy, info["idx"]))

        if not centers:
            new_idx = 0
        else:
            centers.sort(key=lambda x: ((x[0] - drop_cx) ** 2 + (x[1] - drop_cy) ** 2))
            nearest_cx, nearest_cy, nearest_idx = centers[0]

            if drop_cx < nearest_cx:
                new_idx = nearest_idx
            else:
                new_idx = nearest_idx + 1

            new_idx = max(0, min(len(self.current_set), new_idx))

        # --- 调整顺序 ---
        if new_idx != orig_idx:
            try:
                item = self.current_set.pop(orig_idx)
                if new_idx > orig_idx:
                    new_idx -= 1  # 因 pop 导致右移
                self.current_set.insert(new_idx, item)
            except Exception as e:
                logger.info(f"Reorder error:{e}")

        # logger.info(f"drag: {orig_idx} → {new_idx}")

        # --- 清理 & 刷新 ---
        self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
        self.after(100, self.refresh_current_tags)



    # def _start_drag(self, event, idx):
    #     # 记录拖拽开始
    #     widget = event.widget
    #     widget.lift()
    #     self._drag_data["widget"] = widget
    #     self._drag_data["start_x"] = event.x_root
    #     self._drag_data["start_y"] = event.y_root
    #     # find index of widget in current_set
    #     # safe mapping: find by widget reference in _tag_widgets
    #     for info in getattr(self, "_tag_widgets", []):
    #         if info["widget"] == widget:
    #             self._drag_data["idx"] = info["idx"]
    #             logger.info(f'_start_drag')
    #             break

    # def _on_drag(self, event):
    #     lbl = self._drag_data.get("widget")
    #     if not lbl:
    #         return
    #     # move label with cursor (relative to current_frame)
    #     frame_x = self.current_frame.winfo_rootx()
    #     frame_y = self.current_frame.winfo_rooty()
    #     new_x = event.x_root - frame_x - 10
    #     new_y = event.y_root - frame_y - 8
    #     try:
    #         lbl.place(x=new_x, y=new_y)
    #     except Exception:
    #         pass  # might be destroyed during rapid resize

    # def _end_drag(self, event):
    #     lbl = self._drag_data.get("widget")
    #     orig_idx = self._drag_data.get("idx")
    #     if not lbl or orig_idx is None:
    #         self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
    #         return

    #     # 获取拖动中心点（相对 current_frame）
    #     frame_x = self.current_frame.winfo_rootx()
    #     frame_y = self.current_frame.winfo_rooty()
    #     drop_cx = event.x_root - frame_x
    #     drop_cy = event.y_root - frame_y

    #     # 收集所有其他标签的中心坐标
    #     centers = []
    #     for info in getattr(self, "_tag_widgets", []):
    #         w = info["widget"]
    #         if not w.winfo_exists() or w is lbl:
    #             continue
    #         try:
    #             cx = w.winfo_x() + info["w"]/2
    #             cy = w.winfo_y() + 14  # 行高一半
    #         except Exception:
    #             continue
    #         centers.append((cx, cy, info["idx"]))

    #     if not centers:
    #         new_idx = 0
    #     else:
    #         # 计算拖动点与各标签中心的距离（欧式距离）
    #         centers.sort(key=lambda x: ((x[0]-drop_cx)**2 + (x[1]-drop_cy)**2))
    #         nearest_cx, nearest_cy, nearest_idx = centers[0]

    #         # 判断相对方向决定插在前还是后
    #         if drop_cx < nearest_cx:
    #             new_idx = nearest_idx
    #         else:
    #             new_idx = nearest_idx + 1

    #         # 边界限制
    #         new_idx = max(0, min(len(self.current_set)-1, new_idx))

    #     # 如果有移动，调整顺序
    #     if new_idx != orig_idx:
    #         try:
    #             item = self.current_set.pop(orig_idx)
    #             self.current_set.insert(new_idx, item)
    #         except Exception as e:
    #             logger.info("Reorder error:", e)

    #     # logger.info(f"drag: {orig_idx} -> {new_idx}")

    #     # 重置 & 刷新
    #     self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}
    #     self.after(100, self.refresh_current_tags)


    # ---------------------------
    # 已保存组合管理
    # ---------------------------
    def refresh_saved_sets(self):
        self.sets_listbox.delete(0, tk.END)
        for s in self.saved_sets:
            name = s.get("name", "<noname>")
            self.sets_listbox.insert(tk.END, name)

    def get_centered_window_position(self, parent, win_width, win_height, margin=10):
        # 获取鼠标位置
        mx = parent.winfo_pointerx()
        my = parent.winfo_pointery()

        # 屏幕尺寸
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()

        # 默认右边放置
        x = mx + margin
        y = my - win_height // 2  # 垂直居中鼠标位置

        # 如果右边放不下，改到左边
        if x + win_width > screen_width:
            x = mx - win_width - margin

        # 防止y超出屏幕
        if y + win_height > screen_height:
            y = screen_height - win_height - margin
        if y < 0:
            y = margin

        return x, y

    # def askstring_at_parent(self,parent, title, prompt, initialvalue=""):
    #     # 创建临时窗口
    #     dlg = tk.Toplevel(parent)
    #     dlg.transient(parent)
    #     dlg.title(title)
    #     # ✅ 允许用户自由拉伸
    #     dlg.resizable(True, True)
    #     # 计算位置，靠父窗口右侧居中
    #     win_width, win_height = 300, 120
    #     x, y = self.get_centered_window_position(parent, win_width, win_height)
    #     # dlg.geometry(f"{win_width}x{win_height}+{x}+{y}")
    #     logger.info(f"askstring_at_parent : {int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
    #     dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
    #     result = {"value": None}

    #     tk.Label(dlg, text=prompt).pack(pady=5, padx=5)
    #     entry = tk.Entry(dlg)
    #     entry.pack(pady=5, padx=5, fill="x", expand=True)
    #     entry.insert(0, initialvalue)
    #     entry.focus_set()

    #     def on_ok():
    #         result["value"] = entry.get()
    #         dlg.destroy()

    #     def on_cancel():
    #         dlg.destroy()

    #     frame_btn = tk.Frame(dlg)
    #     frame_btn.pack(pady=5)
    #     tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
    #     tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

    #     dlg.grab_set()
    #     parent.wait_window(dlg)
    #     return result["value"]

    def askstring_at_parent(self, parent, title, prompt, initialvalue=""):

        # 创建临时窗口
        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(True, True)  # ✅ 可自由拉伸

        # --- 智能计算初始大小 ---
        base_width, base_height = 300, 120
        char_width = 10
        text_len = max(len(prompt), len(initialvalue))
        extra_width = min(text_len * char_width, 600)
        win_width = max(base_width, extra_width)
        win_height = base_height + (prompt.count("\n") * 15)  # 多行时稍高

        # --- 居中定位 ---
        x, y = self.get_centered_window_position(parent, win_width, win_height)
        logger.info(f"askstring_at_parent : {int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")
        dlg.geometry(f"{int(win_width)}x{int(win_height)}+{int(x)}{int(y):+d}")

        result = {"value": None}

        # --- 提示文字（自动换行） ---
        lbl = tk.Label(dlg, text=prompt, wraplength=win_width - 40, justify="left", anchor="w")
        lbl.pack(pady=5, padx=5, fill="x")

        # --- 输入框 ---
        entry = tk.Entry(dlg)
        entry.pack(pady=5, padx=5, fill="x", expand=True)
        entry.insert(0, initialvalue)
        entry.focus_set()

        # --- 按钮 ---
        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=5)
        tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
        tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

        # --- ESC 键关闭 ---
        dlg.bind("<Escape>", lambda e: on_cancel())
        dlg.bind("<Return>",lambda e: on_ok())       # 回车确认

        dlg.grab_set()
        parent.wait_window(dlg)
        return result["value"]


    def save_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        # name = simpledialog.askstring("保存组合", "请输入组合名称:")
        # 取当前组合名称（或默认空字符串）
        current_name = getattr(self, "current_set_name", "") or ""
        name = self.askstring_at_parent(self.main,"保存组合", "请输入组合名称:",initialvalue=current_name)

        if not name:
            return
        # 覆盖同名
        for s in self.saved_sets:
            if s.get("name") == name:
                s["cols"] = list(self.current_set)
                toast_message(self, f"组合 {name} 已更新")
                self.refresh_saved_sets()
                return
        self.saved_sets.append({"name": name, "cols": list(self.current_set)})
        self.refresh_saved_sets()
        try:
            # save_display_config 是外部函数（如果定义则调用）
            self.config["current"] = list(self.current_set)
            self.config["sets"] = list(self.saved_sets)
            save_display_config(self.config)
        except Exception:
            pass
        # 回调主视图更新列
        toast_message(self, f"组合 {name} 已保存")

    def on_select_saved_set(self, event):
        sel = self.sets_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        data = self.saved_sets[idx]
        self.current_set_name = data.get("name", "")

        # 可选：在界面上显示当前选择的组合名
        if hasattr(self, "lbl_current_set"):
            self.lbl_current_set.config(text=f"当前选中: {self.current_set_name}")
        else:
            logger.info(f"选中组合: {self.current_set_name}")


    def load_selected_set(self):
        sel = self.sets_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        data = self.saved_sets[idx]
        self.current_set = list(data.get("cols", []))

        # 保存当前组合名称（新增）
        self.current_set_name = data.get("name", "")

        # sync checkboxes (if visible)
        for col, var in self._chk_vars.items():
            var.set(col in self.current_set)
        self.refresh_current_tags()
        # also update grid so checked box matches
        self.update_grid()

    def delete_selected_set(self):
        sel = self.sets_listbox.curselection()
        if not sel:
            toast_message(self, "请选择要删除的组合")
            return
        idx = sel[0]
        name = self.saved_sets[idx].get("name", "")
        # 执行删除
        self.saved_sets.pop(idx)
        self.refresh_saved_sets()
        toast_message(self, f"组合 {name} 已删除")

    # ---------------------------
    # 应用 / 恢复默认
    # ---------------------------

    def set_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        # # 写回 config（如果调用方提供 save_display_config，会被调用）
        # self.config["current"] = list(self.current_set)
        # self.config["sets"] = list(self.saved_sets)
        # try:
        #     # save_display_config 是外部函数（如果定义则调用）
        #     save_display_config(self.config)
        # except Exception:
        #     pass
        # # 回调主视图更新列

        try:
            if callable(self.on_apply_callback):
                self.on_apply_callback(list(self.current_set))
        except Exception:
            pass
        # toast_message(self, "init组合已应用")
        # self.destroy()
        # self.open_column_manager_editor()

    def apply_current_set(self):
        if not self.current_set:
            toast_message(self, "当前组合为空")
            return
        # 写回 config（如果调用方提供 save_display_config，会被调用）
        self.config["current"] = list(self.current_set)
        self.config["sets"] = list(self.saved_sets)
        try:
            # save_display_config 是外部函数（如果定义则调用）
            save_display_config(self.config)
        except Exception:
            pass
        # 回调主视图更新列
        try:
            if callable(self.on_apply_callback):
                self.on_apply_callback(list(self.current_set))
        except Exception:
            pass
        toast_message(self, "组合已应用")
        # self.destroy()
        self.open_column_manager_editor()

    def restore_default(self):
        self.current_set = list(self.default_cols)
        # logger.info(f'restore_default self.default_cols : {self.default_cols}')
        # sync checkboxes
        for col, var in self._chk_vars.items():
            var.set(col in self.current_set)
        self.refresh_current_tags()
        toast_message(self, "已恢复默认组合")


# class RealtimeSignalManager:
#     def __init__(self):
#         # 用字典存储每只股票的状态，避免创建新的 df 列
#         # 格式：{symbol: {'prev_now': float, 'today_high': float, 'today_low': float}}
#         self.state = {}

#     def update_signals(self, df: pd.DataFrame) -> pd.DataFrame:
#         """
#         df: 当次最新数据，包含已存在的 columns
#         返回 df，增加 'signal' 和 'signal_strength' 列
#         """
#         df = df.copy()
#         df['signal_strength'] = 0
#         df['signal'] = ""

#         for i, row in df.iterrows():
#             symbol = row['name']  # 股票标识

#             # 获取或初始化状态
#             if symbol not in self.state:
#                 self.state[symbol] = {
#                     'prev_now': row['now'],
#                     'today_high': row['high'],
#                     'today_low': row['low']
#                 }

#             prev_now = self.state[symbol]['prev_now']
#             today_high = self.state[symbol]['today_high']
#             today_low = self.state[symbol]['today_low']

#             # --- 大趋势 ---
#             trend_up = row['ma51d'] > row['ma10d']
#             price_rise = (row['lastp1d'] > row['lastp2d']) & (row['lastp2d'] > row['lastp3d'])
#             macd_bull = (row['macddif'] > row['macddea']) & (row['macd'] > 0)
#             macd_accel = (row['macdlast1'] > row['macdlast2']) & (row['macdlast2'] > row['macdlast3'])
#             rsi_mid = (row['rsi'] > 45) & (row['rsi'] < 75)
#             rsi_up = row['rsi'] - row['rsi'] if pd.notnull(row['rsi']) else 0
#             kdj_bull = (row['kdj_j'] > row['kdj_k']) & (row['kdj_k'] > row['kdj_d'])
#             kdj_strong = row['kdj_j'] > 60

#             # --- 当日迭代 high/low ---
#             today_high = max(today_high, row['high'])
#             today_low = min(today_low, row['low'])

#             # --- 短线实时 ---
#             morning_gap_up = row['open'] <= row['low'] * 1.001
#             vol_boom_now = row['volume'] > 1  # 可改为短期均量
#             intraday_up = row['now'] > prev_now
#             intraday_high_break = row['now'] > today_high
#             intraday_low_break = row['now'] < today_low

#             # --- 打分 ---
#             score = 0
#             score += trend_up * 2
#             score += price_rise * 1
#             score += macd_bull * 1
#             score += macd_accel * 2
#             score += rsi_mid * 1
#             score += rsi_up * 1
#             score += kdj_bull * 1
#             score += kdj_strong * 1
#             score += morning_gap_up * 2
#             score += intraday_up * 1
#             score += intraday_high_break * 2
#             score += vol_boom_now * 1

#             df.at[i, 'signal_strength'] = score

#             # === 信号等级 ===
#             if score >= 9:
#                 df.at[i, 'signal'] = 'BUY_S'
#             elif score >= 6:
#                 df.at[i, 'signal'] = 'BUY_N'
#             elif score < 6 and row['macd'] < 0:
#                 df.at[i, 'signal'] = 'SELL_WEAK'

#             # 卖出条件
#             sell_cond = (
#                 ((row['macddif'] < row['macddea']) & (row['macd'] < 0)) |
#                 ((row['rsi'] < 45) & (row['kdj_j'] < row['kdj_k'])) |
#                 ((row['now'] < row['ma51d']) & (row['macdlast1'] < row['macdlast2'])) |
#                 intraday_low_break
#             )
#             if sell_cond:
#                 df.at[i, 'signal'] = 'SELL'

#             # --- 更新全局状态 ---
#             self.state[symbol]['prev_now'] = row['now']
#             self.state[symbol]['today_high'] = today_high
#             self.state[symbol]['today_low'] = today_low

#         return df

def safe_prev_signal_array(df):
    """
    生成 prev_signal_arr，确保不会因为 df 异常、空值、结构错误而崩溃。
    """
    # 情况 1：df 为空 → 返回空数组
    if df is None or df.empty:
        return np.array([])

    # 情况 2：没有 prev_signal 列 → 创建空列
    if 'prev_signal' not in df.columns:
        df['prev_signal'] = None

    # 确保列存在后，取值
    raw_vals = df['prev_signal'].tolist()

    safe_vals = []
    for v in raw_vals:

        # 若 v 是 Series / ndarray / list / tuple → 代表数据结构异常
        # 直接视为无信号
        if isinstance(v, (pd.Series, np.ndarray, list, tuple, dict)):
            safe_vals.append(0)
            continue

        # 若 v 是字符串（通常的 BUY_N / BUY_S）
        if isinstance(v, str):
            safe_vals.append(1 if v in ('BUY_N', 'BUY_S') else 0)
            continue

        # 若 v 是 NaN 或 None
        if v is None or (isinstance(v, float) and np.isnan(v)):
            safe_vals.append(0)
            continue

        # 其它情况全部归零
        safe_vals.append(0)

    return np.array(safe_vals)


class RealtimeSignalManager:
    def __init__(self):
        self.state = {}

    import numpy as np
    import pandas as pd

    def update_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = ''
        df['signal_strength'] = 0

        # 保留 code 列为 index
        if 'code' in df.columns:
            df.set_index('code', inplace=True, drop=False)

        # --- 准备状态 ---
        # 如果 self.state 为空，初始化
        for code, row in df.iterrows():
            if code not in self.state:
                self.state[code] = {
                    'prev_now': row['now'],
                    'today_high': row['high'],
                    'today_low': row['low'],
                    'prev_signal': None,
                    'down_streak': 0,
                    'recent_vols': [row['volume']]
                }

        # 转成 NumPy 数组加速
        codes = df['code'].values
        prev_now_arr = np.array([self.state[c]['prev_now'] for c in codes])
        today_high_arr = np.array([self.state[c]['today_high'] for c in codes])
        today_low_arr = np.array([self.state[c]['today_low'] for c in codes])
        down_streak_arr = np.array([self.state[c]['down_streak'] for c in codes])
        recent_vols_list = [self.state[c]['recent_vols'] for c in codes]
        prev_signal_list = [self.state[c]['prev_signal'] for c in codes]

        now_arr = df['now'].values
        high_arr = df['high'].values
        low_arr = df['low'].values
        volume_arr = df['volume'].values
        ma51d = df['ma51d'].values
        ma10d = df['ma10d'].values
        lastp1d = df['lastp1d'].values
        lastp2d = df['lastp2d'].values
        lastp3d = df['lastp3d'].values
        macddif = df['macddif'].values
        macddea = df['macddea'].values
        macd = df['macd'].values
        macdlast1 = df['macdlast1'].values
        macdlast2 = df['macdlast2'].values
        macdlast3 = df['macdlast3'].values
        rsi = df['rsi'].values
        kdj_j = df['kdj_j'].values
        kdj_k = df['kdj_k'].values
        kdj_d = df['kdj_d'].values
        open_arr = df['open'].values

        # --- 更新 high/low ---
        today_high_arr = np.maximum(today_high_arr, high_arr)
        today_low_arr = np.minimum(today_low_arr, low_arr)

        # --- 计算最近 5 根 volume 均值 ---
        avg_vol_arr = np.array([np.mean((recent + [v])[-5:]) for recent, v in zip(recent_vols_list, volume_arr)])
        vol_boom_now = volume_arr > avg_vol_arr

        # --- 大趋势指标 ---
        trend_up = ma51d > ma10d
        price_rise = (lastp1d > lastp2d) & (lastp2d > lastp3d)
        macd_bull = (macddif > macddea) & (macd > 0)
        macd_accel = (macdlast1 > macdlast2) & (macdlast2 > macdlast3)
        rsi_mid = (rsi > 45) & (rsi < 75)
        kdj_bull = (kdj_j > kdj_k) & (kdj_k > kdj_d)
        kdj_strong = kdj_j > 60
        morning_gap_up = open_arr <= low_arr * 1.001
        intraday_up = now_arr > prev_now_arr
        intraday_high_break = now_arr > today_high_arr
        intraday_low_break = now_arr < today_low_arr

        # 连续下跌 streak
        down_streak_arr = np.where(now_arr < prev_now_arr, down_streak_arr + 1, 0)

        # --- 计算 score ---
        score = np.zeros(len(df))
        score += trend_up * 2
        score += price_rise * 1
        score += macd_bull * 1
        score += macd_accel * 2
        score += rsi_mid * 1
        score += np.nan_to_num(rsi - 50) * 0.05
        score += kdj_bull * 1
        score += kdj_strong * 1
        score += morning_gap_up * 2
        score += intraday_up * 1
        score += intraday_high_break * 2
        score += vol_boom_now * 1
        score += ((down_streak_arr >= 2) & (now_arr > prev_now_arr * 1.005)) * 2

        # 前置信号加权
        # prev_signal_arr = np.array([1 if s in ['BUY_N', 'BUY_S'] else 0 for s in prev_signal_list])

        prev_signal_arr = safe_prev_signal_array(df)
        # # 确保 prev_signal_list 一律是列表
        # prev_signal_list = df['prev_signal'].tolist()

        # # 避免 Series、NaN、None 造成问题
        # prev_signal_arr = np.array([
        #     1 if isinstance(s, str) and s in ('BUY_N', 'BUY_S') else 0
        #     for s in prev_signal_list
        # ])


        score += prev_signal_arr

        df['signal_strength'] = score

        # --- 信号等级 ---
        df['signal'] = ''
        df.loc[score >= 9, 'signal'] = 'BUY_S'
        df.loc[(score >= 6) & (score < 9), 'signal'] = 'BUY_N'
        df.loc[(score < 6) & (macd < 0), 'signal'] = 'SELL_WEAK'

        # 卖出条件
        sell_cond = ((macddif < macddea) & (macd < 0)) | ((rsi < 45) & (kdj_j < kdj_k)) | ((now_arr < ma51d) & (macdlast1 < macdlast2)) | intraday_low_break
        df.loc[sell_cond, 'signal'] = 'SELL'

        # --- 更新状态 ---
        for i, code in enumerate(codes):
            s = self.state[code]
            s['prev_now'] = now_arr[i]
            s['today_high'] = today_high_arr[i]
            s['today_low'] = today_low_arr[i]
            s['down_streak'] = down_streak_arr[i]
            recent_vols_list[i].append(volume_arr[i])
            if len(recent_vols_list[i]) > 5:
                recent_vols_list[i] = recent_vols_list[i][-5:]
            s['recent_vols'] = recent_vols_list[i]
            s['prev_signal'] = df.at[code, 'signal']

        return df

    def calc_support_resistance(df):
        """
        根据通达信逻辑计算撑压位（压力）和支撑位
        返回 df，包含 columns: ['pressure', 'support']
        """
        import pandas as pd
        from pandas import Series

        LLV = lambda x, n: x.rolling(n, min_periods=1).min()
        HHV = lambda x, n: x.rolling(n, min_periods=1).max()
        SMA = lambda x, n, m: x.ewm(alpha=m/n, adjust=False).mean()

        # --- 短周期 ---
        RSV13 = (df['close'] - LLV(df['low'], 13)) / (HHV(df['high'], 13) - LLV(df['low'], 13)) * 100
        ARSV = SMA(RSV13, 3, 1)
        AK = SMA(ARSV, 3, 1)
        AD = 3 * ARSV - 2 * AK

        # --- 长周期 ---
        RSV55 = (df['close'] - LLV(df['low'], 55)) / (HHV(df['high'], 55) - LLV(df['low'], 55)) * 100
        ARSV24 = SMA(RSV55, 3, 1)
        AK24 = SMA(ARSV24, 3, 1)
        AD24 = 3 * ARSV24 - 2 * AK24

        # --- CROSS 计算 ---
        cross_up = (AD24 > AD) & (AD24.shift(1) <= AD.shift(1))

        # 最近一次上穿的 high 值
        pressure = []
        last_high = None
        for i in range(len(df)):
            if cross_up.iloc[i]:
                last_high = df['high'].iloc[i]
            pressure.append(last_high)
        df['pressure'] = pressure

        # --- 支撑位 ---
        df['support'] = LLV(df['high'], 30)

        return df


def calc_breakout_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal_strength"] = 0
    df["signal"] = ""

    # === 基础特征 ===
    ma_short = df['ma51d']
    ma_mid = df['ma10d']

    # --- 趋势条件 ---
    cond_trend_up = (df['close'] > ma_short) & (ma_short > ma_mid)
    cond_trend_turn = (df['close'] > ma_short) & (df['ma51d'].diff() > 0)
    cond_price_rise = (df['lastp1d'] > df['lastp2d']) & (df['lastp2d'] > df['lastp3d'])

    # --- MACD 动能 ---
    cond_macd_bull = (df['macddif'] > df['macddea']) & (df['macd'] > 0)
    cond_macd_accel = (df['macdlast1'] > df['macdlast2']) & (df['macdlast2'] > df['macdlast3'])

    # --- RSI 动能 ---
    cond_rsi_mid = (df['rsi'] > 45) & (df['rsi'] < 75)
    cond_rsi_up = df['rsi'].diff() > 2  # RSI加速上升

    # --- KDJ 动量 ---
    cond_kdj_bull = (df['kdj_j'] > df['kdj_k']) & (df['kdj_k'] > df['kdj_d'])
    cond_kdj_strong = (df['kdj_j'] > 60)

    # --- 突破条件 ---
    cond_break_high = df['close'] > df['lasth3d']  # 突破近3日高点
    # cond_break_mid = df['close'] > df['high'].rolling(6).max()
    cond_break_mid = df['close'] > df['max5']

    # --- 成交量放大 ---
    cond_vol_boom = df['volume'] > 1

    # === 打分系统 ===
    score = 0
    score += cond_trend_up * 2
    score += cond_trend_turn * 1
    score += cond_price_rise * 1
    score += cond_macd_bull * 1
    score += cond_macd_accel * 2
    score += cond_rsi_mid * 1
    score += cond_rsi_up * 1
    score += cond_kdj_bull * 1
    score += cond_kdj_strong * 1
    score += cond_break_high * 2
    score += cond_break_mid * 1
    score += cond_vol_boom * 1

    df['signal_strength'] = score

    # === 信号等级 ===
    df.loc[df['signal_strength'] >= 8, 'signal'] = 'BUY_S'   # 强势爆发（主升浪）
    df.loc[(df['signal_strength'] >= 5) & (df['signal_strength'] < 8), 'signal'] = 'BUY_N'  # 底部反弹
    df.loc[(df['signal_strength'] < 5) & (df['macd'] < 0), 'signal'] = 'SELL_WEAK'  # 弱势或衰退

    # === 补充卖出逻辑（防止回落） ===
    sell_cond = (
        ((df['macddif'] < df['macddea']) & (df['macd'] < 0)) |
        ((df['rsi'] < 45) & (df['kdj_j'] < df['kdj_k'])) |
        ((df['close'] < ma_short) & (df['macdlast1'] < df['macdlast2']))
    )
    df.loc[sell_cond, "signal"] = "SELL"

    return df

# 全局管理器实例
signal_manager = RealtimeSignalManager()
# ========== 信号检测函数 ==========
def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    if "code" not in df.columns:
        df["code"] = df.index.astype(str).str.zfill(6)  # 补齐6位  # 如果没有code列，用name占位（最好是实际code）

    df["signal"] = ""
    df["emotion"] = "中性"

    # df = calc_breakout_signals(df)
    df = signal_manager.update_signals(df.copy())


    df.loc[df.get("volume", 0) > 1.2, "emotion"] = "乐观"
    df.loc[df.get("volume", 0) < 0.8, "emotion"] = "悲观"
    return df

    # # --- 保留 code 作为 index ---
    # df = df.set_index('code', drop=False)  # drop=False 保留 code 列

    # # 计算新旧信号
    # df_vect  = signal_manager.update_signals(df.copy())
    # df_orig = signal_manager.update_signals_old(df.copy())

    # # 对齐索引，确保可以逐行比较
    # df_vect = df_vect.sort_index()
    # df_orig = df_orig.sort_index()

    # # --- 比较 signal_strength ---
    # mask_strength = df_vect['signal_strength'] != df_orig['signal_strength']
    # diff_idx_strength = df_vect.index[mask_strength]

    # if len(diff_idx_strength) > 0:
    #     logger.info("signal_strength 不一致，行 code:", list(diff_idx_strength))
    #     logger.info(df_vect.loc[diff_idx_strength, ['name','signal_strength']])
    #     logger.info(df_orig.loc[diff_idx_strength, ['name','signal_strength']])
    # else:
    #     logger.info("signal_strength 一致 ✅")

    # # --- 比较 signal ---
    # mask_signal = df_vect['signal'] != df_orig['signal']
    # diff_idx_signal = df_vect.index[mask_signal]

    # if len(diff_idx_signal) > 0:
    #     logger.info("signal 不一致，行 code:", list(diff_idx_signal))
    #     logger.info(df_vect.loc[diff_idx_signal, ['name','signal']])
    #     logger.info(df_orig.loc[diff_idx_signal, ['name','signal']])
    # else:
    #     logger.info("signal 一致 ✅")



    # # 买入逻辑
    # buy_cond = (
    #     (df["now"] > df["ma5d"]) &
    #     (df["ma5d"] > df["ma10d"]) &
    #     (df["macddif"] > df["macddea"]) &
    #     (df["rsi"] < 70) &
    #     ((df["now"] > df["upperL"]) | (df["now"] > df["upper1"]))
    # )

    # # 卖出逻辑
    # sell_cond = (
    #     (df["now"] < df["ma5d"]) &
    #     (df["macddif"] < df["macddea"]) &
    #     (df["rsi"] > 50) &
    #     (df["now"] < df["lastp1d"])
    # )

    # 示例逻辑：最近收盘价高于均线，MACD金叉，RSI<70，KDJ J > 50 -> BUY
    # buy_cond = (
    #     (df['close'] > df['close'].rolling(5).mean()) &
    #     (df['macddif'] > df['macddea']) &
    #     (df['rsi'] < 70) &
    #     (df['kdj_j'] > 50)
    # )

    # sell_cond = (
    #     (df['close'] < df['close'].rolling(10).mean()) &
    #     (df['macddif'] < df['macddea']) &
    #     (df['rsi'] > 50) &
    #     (df['kdj_j'] < 50)
    # )

    # buy_cond = (
    #     # 趋势共振
    #     (df['close'] > df['ma51d']) &                 # 短期价格在均线之上
    #     (df['close'] > df['ma10d']) &               # 中期趋势向上
    #     (df['lastp1d'] > df['lastp2d']) & (df['lastp2d'] > df['lastp3d']) &  # 连续上涨3日
        
    #     # MACD 共振
    #     (df['macddif'] > df['macddea']) &            # DIF上穿DEA（形成金叉）
    #     (df['macd'] > 0) &                           # MACD柱为正，确认趋势
    #     (df['macdlast1'] > df['macdlast2']) & (df['macdlast2'] > df['macdlast3']) &  # 柱线递增
        
    #     # RSI 动能支持
    #     (df['rsi'] > 40) & (df['rsi'] < 70) &        # 适中区间（非过热）
        
    #     # KDJ 动量突破
    #     (df['kdj_j'] > df['kdj_k']) & (df['kdj_k'] > df['kdj_d']) &  # 多头排列
    #     (df['kdj_j'] > 50) &                         # 动能强于中值
    #     (df['close'] < df['upper'])                  # 尚未过度上涨（未触上轨）
    # )

    # sell_cond = (
    #     # 趋势转弱
    #     (df['close'] < df['ma51d']) |                  # 跌破短期均线
    #     (df['macddif'] < df['macddea']) |             # DIF下穿DEA死叉
    #     ((df['macdlast1'] < df['macdlast2']) & (df['macdlast2'] < df['macdlast3'])) |  # 柱线递减
        
    #     # RSI 过热后回落
    #     (df['rsi'] > 70) |                            # 超买
    #     ((df['rsi'] < 50) & (df['macd'] < 0)) |        # RSI掉头向下
        
    #     # KDJ 死叉或动能衰竭
    #     ((df['kdj_j'] < df['kdj_k']) & (df['kdj_k'] < df['kdj_d'])) |  # 空头排列
    #     (df['kdj_j'] < 30) |                          # 动能偏弱
    #     (df['close'] > df['upper'])                   # 价格触及上轨（可能见顶）
    # )

    # # 初始化信号列
    # df["signal"] = ""

    # # 买入条件：底部爆发 + 动能共振
    # buy_cond = (
    #     # 趋势确认
    #     (df['close'] > df['ma51d']) &
    #     (df['ma51d'] > df['ma10d']) &                      # 均线多头排列
    #     (df['macddif'] > df['macddea']) &
    #     (df['macd'] > 0) &

    #     # 动能爆发
    #     (df['close'] > df['lasth3d']) &                      # 突破近3日高点
    #     ((df['lastp1d'] > df['lastp2d']) & (df['lastp2d'] > df['lastp3d'])) &  # 连涨三日
    #     ((df['macdlast1'] > df['macdlast2']) & (df['macdlast2'] > df['macdlast3'])) &  # 柱线递增
    #     (df['volume'] > df['volume'].rolling(5).mean() * 1.2) &  # 成交放大至少20%

    #     # 动能共振
    #     (df['rsi'] > 45) & (df['rsi'] < 80) &
    #     (df['kdj_j'] > df['kdj_k']) & (df['kdj_k'] > df['kdj_d']) &
    #     (df['kdj_j'] > 60)
    # )

    # # 卖出条件：动能衰竭或假突破回落
    # sell_cond = (
    #     ((df['close'] < df['ma51d']) & (df['macd'] < 0)) |
    #     ((df['macddif'] < df['macddea']) & (df['macd'] < 0)) |
    #     ((df['macdlast1'] < df['macdlast2']) & (df['macdlast2'] < df['macdlast3'])) |
    #     (df['rsi'] > 80) |
    #     ((df['kdj_j'] < df['kdj_k']) & (df['kdj_k'] < df['kdj_d'])) |
    #     (df['kdj_j'] < 40)
    # )

    # df.loc[buy_cond, "signal"] = "BUY"
    # df.loc[sell_cond, "signal"] = "SELL"


    # signals = df[df['signal'].isin(['BUY_STRONG', 'BUY_NORMAL', 'SELL'])]
    # logger.info(signals[['close', 'macd', 'rsi', 'kdj_j', 'signal_strength', 'signal']].tail(10))
    # 情绪判定
    # df.loc[df["vchange"] > 20, "emotion"] = "乐观"
    # df.loc[df["vchange"] < -20, "emotion"] = "悲观"
    # 使用 last6vol 或模拟量比



# def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
#     df = df.copy()
#     if df.empty:
#         return df

#     if "code" not in df.columns:
#         df["code"] = df.index.astype(str).str.zfill(6)  # 补齐6位  # 如果没有code列，用name占位（最好是实际code）
    
#     df["signal"] = ""
#     df["emotion"] = "中性"

#     # ---------- 情绪判断 ----------
#     # 使用 last6vol 或模拟量比
#     df.loc[df.get("last6vol", 0) > 1.2, "emotion"] = "乐观"
#     df.loc[df.get("last6vol", 0) < 0.8, "emotion"] = "悲观"

#     # ---------- 买入信号 ----------
#     buy_cond = (
#         (df.get("open", 0) > df.get("lastp1d", 0)) &
#         (df.get("low", 0) > df.get("lastp1d", 0)) &
#         (df.get("now", 0) > df.get("open", 0))
#     )
#     df.loc[buy_cond, "signal"] = "BUY"

#     # ---------- 卖出信号 ----------
#     sell_cond = (
#         (df.get("open", 0) < df.get("lastp1d", 0)) |
#         (df.get("now", 0) < df.get("open", 0))
#     )
#     df.loc[sell_cond, "signal"] = "SELL"

#     return df



class KLineMonitor(tk.Toplevel):
    def __init__(self, parent, get_df_func, refresh_interval=30,history3=None):
        super().__init__(parent)
        self.master = parent
        self.get_df_func = get_df_func
        self.refresh_interval = refresh_interval
        self.stop_event = threading.Event()
        self.sort_column = None
        self.sort_reverse = False
        self.history3 = history3
        # 点击计数器
        self.click_count = 0
        self.search_filter_by_signal = True
        # 历史信号追踪
        self.last_buy_index = None
        self.last_sell_index = None
        self.buy_history_indices = set()
        self.sell_history_indices = set()
        self.signal_types = ["BUY_S", "BUY_N", "SELL"]
        # 历史信号追踪（根据 signal_types 动态生成）
        # self.last_signal_index = {sig: None for sig in self.signal_types}
        # self.signal_history_indices = {sig: set() for sig in self.signal_types}
        # 筛选栈
        self.filter_stack = []

        self.last_query = ""

        # 缓存数据
        self.df_cache = None

        self.title("K线趋势实时监控")
        self.geometry("760x460")

        # ---- 状态栏 ----
        self.status_frame = tk.Frame(self, bg="#eee")
        self.status_frame.pack(fill="x")

        self.total_label = tk.Label(self.status_frame, text="总数: 0", bg="#eee")
        self.total_label.pack(side="left", padx=5)

        # 动态生成信号统计标签
        self.signal_labels = {}
        for sig in self.signal_types:
            lbl = tk.Label(self.status_frame, text=f"{sig}: 0", bg="#eee", cursor="hand2")
            lbl.pack(side="left", padx=5)
            lbl.bind("<Button-1>", lambda e, s=sig: self.filter_by_signal(s))
            self.signal_labels[sig] = lbl

        # 情绪标签保持不变
        self.emotion_labels = {}
        for emo, color in [("乐观", "green"), ("悲观", "red"), ("中性", "gray")]:
            lbl = tk.Label(self.status_frame, text=f"{emo}: 0", fg=color, cursor="hand2", bg="#eee")
            lbl.pack(side="left", padx=5)
            lbl.bind("<Button-1>", lambda e, em=emo: self.filter_by_emotion(em))
            self.emotion_labels[emo] = lbl

        # 全局显示按钮
        self.global_btn = tk.Button(self.status_frame, text="全局", cursor="hand2", command=self.reset_filters)
        self.global_btn.pack(side="right", padx=5)

        # ---- 表格 + 滚动条 ----
        table_frame = tk.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True)

        # 自定义窄滚动条样式
        style = ttk.Style(self)
        style.configure(
            "Thin.Vertical.TScrollbar",
            troughcolor="#f2f2f2",
            background="#c0c0c0",
            bordercolor="#f2f2f2",
            lightcolor="#f2f2f2",
            darkcolor="#f2f2f2",
            arrowsize=10,
            width=8
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=("code", "name", "now", "percent", "volume", "signal","score","red", "emotion"),
            show="headings",
            height=20
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 垂直滚动条
        vsb = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
            style="Thin.Vertical.TScrollbar"
        )
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)


        for col, text, w in [
            ("code", "代码", 40),
            ("name", "名称", 60),
            ("now", "当前价", 30),
            ("percent", "涨幅",30),
            ("volume", "量比", 30),
            ("signal", "信号", 60),
            ("score", "评分", 30),
            ("red", "连阳", 30),
            ("emotion", "情绪", 60)
        ]:
            # self.tree.heading(col, text=text, command=lambda c=col: self.treeview_sort_columnKLine(c))
            self.tree.heading(col, text=text, command=lambda c=col: self.treeview_sort_columnKLine(c,onclick=True))
            self.tree.column(col, width=w, anchor="center")

        # 高亮配置可以根据 signal_types 动态生成
        self.tree.tag_configure("neutral", background="#f0f0f0")
        for sig in self.signal_types:
            self.tree.tag_configure(sig.lower(), background="#d0f0d0")  # 示例，BUY_STRONG -> buy_strong
        # self.tree.tag_configure("buy", background="#d0f5d0")
        # self.tree.tag_configure("sell", background="#f5d0d0")
        # self.tree.tag_configure("neutral", background="#f0f0f0")
        self.tree.tag_configure("buy_hist", background="#b0f0b0")
        self.tree.tag_configure("sell_hist", background="#f0b0b0")
        self.tree.tag_configure("red_row", foreground="red")        # 涨幅或低点大于前一日
        self.tree.tag_configure("orange_row", foreground="orange")  # 高位或突破
        self.tree.tag_configure("green_row", foreground="green")    # 跌幅明显
        self.tree.tag_configure("blue_row", foreground="#555555")      # 弱势或低于均线低于 ma5d
        self.tree.tag_configure("purple_row", foreground="purple")  # 成交量异常等特殊指标
        self.tree.tag_configure("yellow_row", foreground="yellow")  # 临界或预警
        # 绑定点击和键盘
        self.tree.bind("<Button-1>", self.on_tree_kline_monitor_click)
        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_kline_monitor_right_click)
        self.tree.bind("<Double-1>", self.on_tree_kline_monitor_double_click)

        self.tree.bind("<Up>", self.on_key_select)
        self.tree.bind("<Down>", self.on_key_select)


        # ---- 窗口底部状态栏 ----
        self.query_status_var = tk.StringVar(value="")
        self.query_status_label = tk.Label(
            self,
            textvariable=self.query_status_var,
            anchor="w",
            bg="#f0f0f0",
            fg="blue"
        )
        self.query_status_label.pack(side="bottom", fill="x")


        # ---- 中间表格 ----
        table_frame = tk.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True)


        # --- 搜索框区域 ---
        # tk.Label(self.status_frame, text="查代码:").pack(side="left", padx=(5, 0))
        # self.search_var = tk.StringVar()
        # self.search_entry = tk.Entry(self.status_frame, textvariable=self.search_var, width=10)
        # self.search_entry.pack(side="left", padx=3)

        self.search_var = tk.StringVar()
        self.search_combo3 = ttk.Combobox(self.status_frame, textvariable=self.search_var, values=self.history3(), width=20)
        self.search_combo3.pack(side="left", padx=5, fill="x", expand=True)
        self.search_combo3.bind("<Return>", lambda e: self.search_code_status(onclick=True))
        self.search_combo3.bind("<Button-3>", self.on_kline_monitor_right_click)
        self.search_combo3.bind("<<ComboboxSelected>>", lambda e: self.search_code_status(onclick=True))

        # self.search_combo3.bind("<<ComboboxSelected>>", lambda e: self.apply_search())
        # self.search_var2.trace_add("write", self._on_search_var_change)

        # 搜索按钮
        self.search_btn = tk.Button(
            self.status_frame, text="查询", cursor="hand2", command=lambda: self.search_code_status(onclick=True)
        )
        self.search_btn.pack(side="left", padx=3)

        # # 绑定回车键快速查询
        # self.search_entry.bind("<Return>", lambda e: self.search_code_status())
        # # 绑定右键事件
        # self.search_entry.bind("<Button-3>", self.on_kline_monitor_right_click)


        # EDIT按钮
        self.search_btn2 = tk.Button(
            self.status_frame, text="编辑", cursor="hand2", command=self.edit_code_status)
        self.search_btn2.pack(side="left", padx=3)

        if len(self.history3()) > 0:
            self.search_var.set(self.history3()[0])


        # 启动刷新线程
        threading.Thread(target=self.refresh_loop, daemon=True).start()

        self.protocol("WM_DELETE_WINDOW", self.on_kline_monitor_close)
       
        try:
            self.master.load_window_position(self, "KLineMonitor", default_width=860, default_height=560)
        except Exception:
            self.geometry("760x460")


    def refresh_search_combo3(self):
        """刷新 KLine 搜索框的历史下拉值，并自动更新当前选中项"""
        if hasattr(self, "search_combo3") and self.search_combo3.winfo_exists():
            try:
                # 兼容 self.history3 是函数或直接是列表
                values = self.history3() if callable(self.history3) else self.history3
                values = list(values) if values else []
                
                # 更新下拉框内容
                self.search_combo3["values"] = values

                # 如果存在历史记录，则自动设置第一个值为当前输入框内容
                if values:
                    self.search_var.set(values[0])
                else:
                    self.search_var.set("")
            except Exception as e:
                logger.info(f"[refresh_search_combo3] 刷新失败: {e}")


    def edit_code_status(self):
        # 获取当前第一个历史项（仅示例）
        query = self.history3()[0] if self.history3() else ""
        new_note = askstring_at_parent_single(self, "修改备注", "请输入新的备注：", initialvalue=query)
        if new_note is not None:
            self.search_var.set(new_note)
            logger.info(f'set self.search_var : {new_note}')

            # ✅ 修改底层数据（是引用，直接生效）
            self.history3()[0] = new_note

            # ✅ 刷新 combobox 的 values
            self.search_combo3["values"] = self.history3()

            # ✅ 设置当前显示值
            self.search_combo3.set(new_note)

            self.search_code_status()


    def search_code_status(self,onclick=False):
        """
        在 Treeview 中搜索 code 或使用 query 过滤当前表格数据
        支持表达式: score>80 and percent>5 and volume>2
        """
        query = self.search_var.get().strip()
        if onclick:
            self.search_filter_by_signal = True
        logger.info(f'self.search_filter_by_signal : {self.search_filter_by_signal}')
        if not self.search_filter_by_signal or not query:
            return

        # --- 保存到实例属性（不立即写文件） ---
        self.last_query = query

        # --- 1. 搜索股票代码 ---
        if query.isdigit() and len(query) == 6:
            code = query
            found = False
            for item in self.tree.get_children():
                if self.tree.set(item, "code") == code:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    self.tree.see(item)
                    found = True
                    break
            if not found:
                toast_message(self, f"未找到代码 {code}")
            else:
                try:
                    self.lift()
                    self.focus_force()
                except Exception:
                    pass
            return

        try:

            df_filtered = self.apply_filters()
            toast_message(self, f"共找到 {len(df_filtered)} 条结果")

            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass

        except Exception as e:
            toast_message(self, f"筛选语句错误: {e}")

    def tree_scroll_to_code_kline(self, code):
        """在 Treeview 中自动定位到指定 code 行"""
        if not code or not (code.isdigit() and len(code) == 6):
            return

        try:
            # --- 2. 清空原有选择（可选） ---
            # self.tree.selection_remove(self.tree.selection())
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                # values[0] 通常是 code，如果你的 code 列不是第一列可以传入 index 参数
                if values and str(values[0]) == str(code):
                    self.tree.selection_set(iid)   # 设置选中
                    self.tree.focus(iid)           # 键盘焦点
                    self.tree.see(iid)             # 自动滚动，使其可见
                    return True
            toast_message(self.master, f"{code} is not Found in kline")
        except Exception as e:
            logger.info(f"[tree_scroll_to_code] Error: {e}")
            return False

        return False  # 未找到


    def on_kline_monitor_right_click(self,event):
        try:
            # 获取剪贴板内容
            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        # 插入到光标位置
        # event.widget.insert(tk.INSERT, clipboard_text)
        # 先清空再黏贴
        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)
        self.search_code_status()
    # ---- 点击逻辑 ----
    def on_tree_kline_monitor_click(self, event=None, item_id=None):
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None

            self.click_count += 1
            if self.click_count % 10 == 0:
                logger.info(f"[Monitor] 点击了 {stock_code}")

            if hasattr(self.master, "on_single_click"):
                send_tdx_Key = (getattr(self.master, "select_code", None) != stock_code)
                self.master.select_code = stock_code
                stock_code = str(stock_code).zfill(6)
                if send_tdx_Key and stock_code:
                    self.master.sender.send(stock_code)
        except Exception as e:
            logger.info(f"[Monitor] 点击处理错误: {e}")


    

    def on_tree_kline_monitor_double_click(self, event=None, item_id=None):
        # 通过 code 从 df_all 获取 category 内容
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None
            stock_code = str(stock_code).zfill(6)
            query_str = f'index.str.contains("^{stock_code}")'
            pyperclip.copy(query_str)
            name = values[1] if len(values) > 0 else None
            if hasattr(self.master, "df_all"):
                category_content = self.master.df_all.loc[stock_code, 'category']
            else:
                category_content = "未找到该股票的 category 信息"
            # self.master.show_category_detail(stock_code,name,category_content)
            self.master.plot_following_concepts_pg(stock_code,top_n=1)

        except Exception as e:
            logger.info(f"[Monitor] double_click错误:{e}")
            traceback.print_exc()

    def on_tree_kline_monitor_right_click(self, event=None, item_id=None):
        try:
            if item_id is None and event is not None:
                item_id = self.tree.identify_row(event.y)
            if not item_id:
                return

            self.tree.selection_set(item_id)
            self.tree.focus(item_id)

            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None

            if hasattr(self.master, "push_stock_info"):
                # send_tdx_Key = (getattr(self.master, "select_code", None) != stock_code)
                # self.master.select_code = stock_code
                stock_code = str(stock_code).zfill(6)
                # if send_tdx_Key and stock_code:
                #     self.master.sender.send(stock_code)
                # pyperclip.copy(stock_code)
                if self.master.push_stock_info(stock_code,self.master.df_all.loc[stock_code]):
                    # 如果发送成功，更新状态标签
                    self.master.status_var2.set(f"发送成功: {stock_code}")
                else:
                    # 如果发送失败，更新状态标签
                    self.master.status_var2.set(f"发送失败: {stock_code}")

        except Exception as e:
            logger.info(f"[Monitor] 点击处理错误: {e}")

    # ---- 上下键选择 ----
    def on_key_select(self, event):
        try:
            children = self.tree.get_children()
            if not children:
                return "break"

            sel_items = self.tree.selection()
            if not sel_items:
                item_id = children[0]
            else:
                current_index = children.index(sel_items[0])
                if event.keysym == "Up":
                    item_id = children[max(0, current_index - 1)]
                elif event.keysym == "Down":
                    item_id = children[min(len(children) - 1, current_index + 1)]
                else:
                    return "break"

            self.tree.see(item_id)
            self.on_tree_kline_monitor_click(item_id=item_id)
        except Exception as e:
            logger.info(f"[Monitor] 键盘选择错误:{e}")
        return "break"

    # # ---- 列排序 ----
    def treeview_sort_columnKLine(self, col, reverse=False,onclick=False):
        try:
            # ---- 保存当前滚动位置 ----
            y = self.tree.yview()

            self.sort_column = col
            self.sort_reverse = reverse

            # ---- 提取数据 ----
            data_list = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

            # ---- 排序 ----
            try:
                data_list.sort(key=lambda t: float(t[0]), reverse=reverse)
            except ValueError:
                data_list.sort(reverse=reverse)

            # ---- 重新排列 ----
            for index, (val, k) in enumerate(data_list):
                self.tree.move(k, '', index)

            # ---- 再绑定点击事件 ----
            self.tree.heading(col, command=lambda: self.treeview_sort_columnKLine(col, not reverse,onclick=True))
            # logger.info(f'onclick: {onclick}')
            if onclick:
                self.tree.yview_moveto(0)
            else:
                # ---- 恢复滚动位置 ----
                self.tree.yview_moveto(y[0])


        except Exception as e:
            logger.info(f"[Monitor] 排序错误:{e}")

    # ---- 刷新循环 ----
    def refresh_loop(self):
        # --- 启动时先跑一次数据 ---
        try:
            df = self.get_df_func()
            if df is not None and not df.empty:
                # df = detect_signals(df)
                self.df_cache = df.copy()
                self.after(0, self.apply_filters)
        except Exception as e:
            logger.info(f"[Monitor] 初次更新错误:{e}")

        # --- 循环刷新 ---
        while not self.stop_event.is_set():
            try:
                if  cct.get_work_time():  # 仅工作时间刷新
                    df = self.get_df_func()
                    if df is not None and not df.empty:
                        df = detect_signals(df)
                        self.df_cache = df.copy()
                        self.after(0, self.apply_filters)
                else:
                    # 非工作时间休眠更久，减少CPU消耗
                    time.sleep(10)
            except Exception as e:
                logger.info(f"[Monitor] 更新错误:{e}")
            finally:
                time.sleep(self.refresh_interval)

    def get_row_tags_kline(self, r, idx=None):
        """
        根据一行数据 r 和索引 idx 生成 Treeview tag 列表
        """

        
        tags = []

        sig = str(r.get("signal","") or "")
        # 基本 tag
        if sig.startswith("BUY"):
            tags.append("buy")
        elif sig.startswith("SELL"):
            tags.append("sell")
        else:
            tags.append("neutral")

        # 历史高亮
        if idx is not None:
            for s in self.signal_types:
                if idx in self.signal_history_indices.get(s, set()):
                    tags.append(f"{tags[0]}_hist")  # 保留原 tag 并添加历史标记

        # logger.info(f'get_row_tags_kline: {r}')
        row_tags = get_row_tags(r)
        tags.extend(row_tags) 
        # logger.debug(f'get_row_tags_kline tags: {tags}')

        # 可以在这里继续添加其他颜色逻辑，比如：
        # if r.get("low",0) > r.get("lastp1d",0):
        #     tags.append("red_row")

        return tags


    def process_table_data(self, df):
        """
        处理表格数据，使用滑动平均斜率判断趋势
        """
        processed = []

        # 初始化累积信号和价格历史
        if not hasattr(self, "cumulative_signals"):
            self.cumulative_signals = {}
        if not hasattr(self, "price_history"):
            self.price_history = {}  # {code: deque([...])}
            self.max_history_len = 10

        if not hasattr(self, "signal_history_indices"):
            self.signal_history_indices = {sig: set() for sig in self.signal_types}
            self.last_signal_index = {sig: None for sig in self.signal_types}

        for idx, r in df.iterrows():
            code = r.get("code")
            sig = str(r.get("signal", "") or "")
            now_price = r.get("now", 0)

            # --- 更新价格历史 ---
            if code not in self.price_history:
                self.price_history[code] = deque(maxlen=self.max_history_len)
            self.price_history[code].append(now_price)

            ph = np.array(self.price_history[code])
            trend = "flat"

            # --- 计算趋势：滑动平均斜率 ---
            if len(ph) >= 3:  # 至少3个点
                # 使用最小二乘线性拟合
                x = np.arange(len(ph))
                y = ph
                A = np.vstack([x, np.ones(len(x))]).T
                slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]

                # 根据斜率判断趋势
                if slope > 0.01:  # 阈值可调
                    trend = "up"
                elif slope < -0.01:
                    trend = "down"
                else:
                    trend = "flat"

            # --- 更新累积信号 ---
            if code not in self.cumulative_signals:
                self.cumulative_signals[code] = []

            if sig in self.signal_types:
                if trend == "up":
                    self.cumulative_signals[code].append(sig)
                elif trend == "down" and self.cumulative_signals[code]:
                    try:
                        self.cumulative_signals[code].remove(sig)
                    except ValueError:
                        pass
                # 横盘 trend=="flat" 不变化

                # 更新历史索引
                self.signal_history_indices[sig].add(idx)
                self.last_signal_index[sig] = idx

            # --- 构造显示信号 ---
            count = self.cumulative_signals.get(code, []).count(sig) if sig else 0
            arrow = "↑" if trend=="up" else ("↓" if trend=="down" else "→")
            display_signal = f"{sig} {arrow}{count}" if sig else ""

            tag = self.get_row_tags_kline(r,idx=idx)
            # # tag
            # tag = "neutral"
            # if sig.startswith("BUY"):
            #     tag = "buy"
            # elif sig.startswith("SELL"):
            #     tag = "sell"
            # # 历史高亮
            # for s in self.signal_types:
            #     if idx in self.signal_history_indices.get(s, set()):
            #         tag += "_hist"

            processed.append({
                "code": code,
                "name": r.get("name",""),
                "now": now_price,
                "percent": r.get("percent",0) or r.get("per1d",0),
                "volume": r.get("volume",0),
                "display_signal": display_signal,
                "score": r.get("score",0),
                "red": r.get("red",0),
                "emotion": r.get("emotion",""),
                "tag": tag
            })

        return processed


    def update_table(self, df):
        """
        使用 process_table_data 处理数据，再更新 Treeview
        """
        # 保存选中行
        selected_code = None
        sel_items = self.tree.selection()
        if sel_items:
            values = self.tree.item(sel_items[0], "values")
            if values:
                selected_code = values[0]

        # 处理数据
        processed_data = self.process_table_data(df)

        # 清空表格
        self.tree.delete(*self.tree.get_children())

        # 插入表格
        for row in processed_data:
            # logger.info(f'row["code"] : {row["code"]} row["tag"] : {row["tag"]}')
            self.tree.insert(
                "", tk.END,
                values=(
                    row["code"],
                    row["name"],
                    f"{row['now']:.2f}",
                    f"{row['percent']:.2f}",
                    f"{row['volume']:.1f}",
                    row["display_signal"],
                    f"{row['score']}",
                    f"{row['red']}",
                    row["emotion"]
                ),
                tags=tuple(row["tag"]) 
            )

                # tags=(row["tag"],)
        # 保留排序
        if getattr(self, "sort_column", None):
            self.treeview_sort_columnKLine(self.sort_column, self.sort_reverse)

        # 恢复选中行
        if selected_code:
            for item in self.tree.get_children():
                if self.tree.set(item, "code") == selected_code:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    self.tree.see(item)
                    break

        # 更新状态栏
        total = len(df)
        self.total_label.config(text=f"总数: {total}")

        # 各信号计数
        signal_counts = df["signal"].value_counts().to_dict()
        for sig, lbl in self.signal_labels.items():
            count = signal_counts.get(sig, 0)
            lbl.config(text=f"{sig}: {count}")

        # 情绪统计
        emotion_counts = df["emotion"].value_counts().to_dict()
        for emo, lbl in self.emotion_labels.items():
            lbl.config(text=f"{emo}: {emotion_counts.get(emo, 0)}")

        # 成功查询后
        self.query_status_var.set(f"共找到 {len(df)} 条结果")
    # ---- 筛选 ----
    def filter_by_signal(self, signal):
        self.filter_stack.append({"type":"signal","value":signal})
        self.apply_filters()

    def filter_by_emotion(self, emotion):
        self.filter_stack.append({"type":"emotion","value":emotion})
        self.apply_filters()

    def reset_filters(self):
        self.filter_stack.clear()
        self.search_filter_by_signal = False
        if self.df_cache is not None:
            self.update_table(self.df_cache)

    def apply_filters(self):
        """应用信号/情绪过滤 + 自动 query 查询"""
        if not self.search_filter_by_signal or self.df_cache is None or self.df_cache.empty:
            return

        df = self.df_cache.copy()

        # --- 1️⃣ 先应用 filter_stack 逻辑 ---
        for f in getattr(self, "filter_stack", []):
            if f["type"] == "signal":
                df = df[df["signal"] == f["value"]]
            elif f["type"] == "emotion":
                df = df[df["emotion"] == f["value"]]

        # --- 2️⃣ 然后应用上次查询条件（last_query） ---
        query_text = ""
        # 优先用当前搜索框内容
        if hasattr(self, "search_var") and self.search_var.get().strip():
            query_text = self.search_var.get().strip()
        # 否则使用上次保存的查询条件
        elif hasattr(self, "last_query") and self.last_query:
            query_text = self.last_query.strip()

        if query_text:
            try:
                # --- 2. 表达式过滤 TreeView 当前数据 ---
                # ====== 条件清理 ======
                query = query_text
                if query.count('or') > 0 and query.count('(') > 0:
                    query_search = f"({query})"
                    logger.info(f'apply_filters {query.count("or")} OR query: {query_search} ')
                    query_engine = 'numexpr'
                    # if any('index.' in c.lower() for c in query):
                    if any('index.' in c.lower() for c in query) or ('.str' in query and '|' in query):
                        query_engine = 'python'
                    df = df.query(query_search, engine=query_engine)
                else:

                    bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)
                    # 2️⃣ 替换掉原 query 中的这些部分
                    for bracket in bracket_patterns:
                        query = query.replace(f'and {bracket}', '')

                    conditions = [c.strip() for c in query.split('and')]
                    # logger.info(f'conditions {conditions}')
                    valid_conditions = []
                    removed_conditions = []
                    # logger.info(f'conditions: {conditions} bracket_patterns : {bracket_patterns}')
                    for cond in conditions:
                        cond_clean = cond.lstrip('(').rstrip(')')
                        # cond_clean = ensure_parentheses_balanced(cond_clean)
                        if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 or cond.find('or') >= 0:
                            if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                                ensure_cond = ensure_parentheses_balanced(cond)
                                # logger.info(f'cond : {cond} ensure_cond : {ensure_cond}')
                                valid_conditions.append(ensure_cond)
                                continue

                        # 提取条件中的列名
                        cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

                        # 所有列都必须存在才保留
                        if all(col in df.columns for col in cols_in_cond):
                            valid_conditions.append(cond_clean)
                        else:
                            removed_conditions.append(cond_clean)
                            # logger.info(f"剔除不存在的列条件: {cond_clean}")

                    # 去掉在 bracket_patterns 中出现的内容
                    removed_conditions = [
                        cond for cond in removed_conditions
                        if not any(bp.strip('() ').strip() == cond.strip() for bp in bracket_patterns)
                    ]

                    # 打印剔除条件列表
                    if removed_conditions:
                        # logger.info(f"剔除不存在的列条件: {removed_conditions}")
                        unique_conditions = tuple(sorted(set(removed_conditions)))
                        # 初始化缓存
                        if not hasattr(self, "_printed_removed_conditions"):
                            self._printed_removed_conditions = set()
                        # 只打印新的
                        if unique_conditions not in self._printed_removed_conditions:
                            logger.info(f"剔除不存在的列条件: {unique_conditions}")
                            self._printed_removed_conditions.add(unique_conditions)

                    if not valid_conditions:
                        self.status_var.set("没有可用的查询条件")
                        return
                    # logger.info(f'valid_conditions : {valid_conditions}')
                    # ====== 拼接 final_query 并检查括号 ======
                    final_query = ' and '.join(f"({c})" for c in valid_conditions)
                    # logger.info(f'final_query : {final_query}')
                    if bracket_patterns:
                        final_query += ' and ' + ' and '.join(bracket_patterns)
                    # logger.info(f'final_query : {final_query}')
                    left_count = final_query.count("(")
                    right_count = final_query.count(")")
                    if left_count != right_count:
                        if left_count > right_count:
                            final_query += ")" * (left_count - right_count)
                        elif right_count > left_count:
                            final_query = "(" * (right_count - left_count) + final_query

                    # ====== 决定 engine ======
                    query_engine = 'numexpr'
                    if any('index.' in c.lower() for c in valid_conditions):
                        query_engine = 'python'

                    # # 中文列名兼容映射 使用中文查询时需要
                    # col_map = {
                    #     "评分": "score",
                    #     "涨幅": "percent",
                    #     "量比": "volume",
                    #     "当前价": "now",
                    #     "信号": "signal",
                    #     "情绪": "emotion",
                    # }
                    # expr = query_text
                    # for k, v in col_map.items():
                    #     expr = expr.replace(k, v)
                    expr = final_query
                    # 数字列转换，确保query能正常执行
                    for col in ["score", "percent", "volume", "now"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")

                    if query_text.isdigit() and len(query_text) == 6:
                        # 股票代码精确查找
                        df = df[df["code"] == query_text]
                    else:
                        # pandas 表达式过滤
                        # df = df.query(expr)
                        df = df.query(final_query, engine=query_engine)

            except Exception as e:
                logger.info(f"[apply_filters] 查询错误: {e}")

        # --- 3️⃣ 更新表格 ---
        self.update_table(df)
        return df
 
    # ---- 关闭 ----
    def on_kline_monitor_close(self):
        self.stop_event.set()
        try:
            self.master.save_window_position(self, "KLineMonitor")
        except Exception:
            pass

        # """窗口关闭时保存 last_query"""
        # try:
        #     if getattr(self, "last_query", ""):
        #         import json
        #         with open("last_query.json", "w", encoding="utf-8") as f:
        #             json.dump({"last_query": self.last_query}, f, ensure_ascii=False, indent=2)
        # except Exception as e:
        #     logger.info(f"保存 last_query.json 出错: {e}")

        # self.destroy()
        # if hasattr(self.master, "kline_monitor"):
        #     self.master.kline_monitor = None
        # 隐藏窗口而不是销毁
        # self.withdraw()  
        # 判断是否需要销毁或隐藏
        if getattr(self, "df_cache", None) is None or len(getattr(self.df_cache, "index", [])) == 0:
            # 没有数据 => 直接销毁
            logger.info("[KLineMonitor] 无数据，销毁窗口。")
            try:
                self.destroy()
            except Exception:
                pass
            if hasattr(self.master, "kline_monitor"):
                self.master.kline_monitor = None
        else:
            # 有数据 => 隐藏窗口，保留状态
            logger.info("[KLineMonitor] 有数据，隐藏窗口。")
            try:
                self.withdraw()
            except Exception:
                pass

def test_single_thread():
    import queue
    # 用普通 dict 代替 manager.dict()
    shared_dict = {}
    shared_dict["resample"] = "d"

    # 用 Python 内置 queue 代替 multiprocessing.Queue
    q = queue.Queue()

    # 用一个简单的对象/布尔值模拟 flag
    class Flag:
        def __init__(self, value=True):
            self.value = value
    flag = Flag(True)   # 或者 flag = Flag(False) 看你的测试需求
    log_level = mp.Value('i', LoggerFactory.DEBUG)  # 'i' 表示整数
    detect_calc_support = mp.Value('b', False)  # 'i' 表示整数
    # 直接单线程调用
    fetch_and_process(shared_dict, q, blkname="boll", flag=flag ,log_level=log_level,detect_calc_support=detect_calc_support)


# def parse_args():
#     parser = argparse.ArgumentParser(description="Monitor Init Script")

#     parser.add_argument(
#         "--log",
#         type=str,
#         default="INFO",
#         help="日志等级，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL"
#     )

#     # ✅ 新增布尔开关参数
#     parser.add_argument(
#         "--write_to_hdf",
#         action="store_true",
#         help="执行 write_to_hdf() 并退出"
#     )

#     args, _ = parser.parse_known_args()   # ✅ 忽略 multiprocessing 私有参数
#     return args

# 常用命令示例列表
COMMON_COMMANDS = [
    "tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df('300')",
    "tdd.get_tdx_exp_low_or_high_power('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df_Sina('sina_data')",
    "tdd.h5a.check_tdx_all_df_Sina('get_sina_all_ratio')",
    "write_to_hdf()"
]

# 格式化帮助信息，换行+缩进
help_text = "传递 Python 命令字符串执行，例如:\n" + "\n".join([f"    {cmd}" for cmd in COMMON_COMMANDS])
# import textwrap
# 第一行紧跟说明，后续命令换行并缩进
# # 使用 textwrap 格式化 help 文本
# help_text = "传递 Python 命令字符串执行，例如:\n"
# help_text += textwrap.indent("\n".join(COMMON_COMMANDS), "    ")

def parse_args():
    parser = argparse.ArgumentParser(description="Monitor Init Script")

    parser.add_argument(
        "--log",
        type=str,
        default="INFO",
        help="日志等级，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )

    # 布尔开关参数
    parser.add_argument(
        "--write_to_hdf",
        action="store_true",
        help="执行 write_to_hdf() 并退出"
    )

    # 新增测试开关
    parser.add_argument(
        "--test",
        action="store_true",
        help="执行测试数据流程"
    )

    parser.add_argument(
        "--cmd",
        type=str,
        nargs='?',          # 表示参数可选
        const=COMMON_COMMANDS[0],  # 默认无值时使用第一个常用命令  # 当没有值时使用 const
        default=None,       # 如果完全没传 --cmd, default 才会生效
        help=help_text
        # help="传递 Python 命令字符串执行，例如:\n" + "\n".join(COMMON_COMMANDS)
        # help="传递 Python 命令字符串执行，例如: tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')"
    )

    args, _ = parser.parse_known_args()  # 忽略 multiprocessing 私有参数
    return args

def test_get_tdx():
    """封装测试函数，获取股票历史数据"""
    code = '000002'
    dl = 60
    newdays = 0
    resample = 'd'

    try:
        df = tdd.get_tdx_Exp_day_to_df(code, dl=dl, newdays=newdays, resample=resample)
        if df is not None and not df.empty:
            logger.info(f"成功获取 {code} 的数据，前5行:\n{df.head()}")
        else:
            logger.warning(f"{code} 返回数据为空")

        # df = tdd.get_tdx_exp_low_or_high_power(code, dl=dl, newdays=newdays, resample=resample)
        # if df is not None and not df.empty:
        #     logger.info(f"成功获取 {code} 的数据，前5行:\n{df.head()}")
        # else:
        #     logger.warning(f"{code} 返回数据为空")
    except Exception as e:
        logger.error(f"获取 {code} 数据失败: {e}", exc_info=True)

def write_to_hdf():
    while 1:
        market = cct.cct_raw_input("1Day-Today check Duration Single write all TDXdata append [all,sh,sz,cyb,alla,q,n] :")
        if market != 'q' and market != 'n'  and len(market) != 0:
            if market in ['all', 'sh', 'sz', 'cyb', 'alla']:
                if market != 'all':
                    tdd.Write_market_all_day_mp(market, rewrite=True)
                    break
                else:
                    tdd.Write_market_all_day_mp(market)
                    break
            else:
                print("market is None ")
        else:
            break

    hdf5_wri_append = cct.cct_raw_input("1Day-Today No check Duration Single write Multi-300 append sina to Tdx data to Multi hdf_300[y|n]:")
    if hdf5_wri_append == 'y':
        for inx in tdd.tdx_index_code_list:
            tdd.get_tdx_append_now_df_api_tofile(inx)
        print("Index Wri ok 300", end=' ')
        tdd.Write_sina_to_tdx(tdd.tdx_index_code_list, index=True)
        tdd.Write_sina_to_tdx(market='all')

    hdf5_wri = cct.cct_raw_input("Multi-300 write all Tdx data to Multi hdf_300[rw|y|n]:")
    if hdf5_wri == 'rw':
        tdd.Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300, rewrite=True)
    elif hdf5_wri == 'y':
        tdd.Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300)

    hdf5_wri = cct.cct_raw_input("Multi-900 write all Tdx data to Multi hdf_900[rw|y|n]:")
    if hdf5_wri == 'rw':
        tdd.Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900, rewrite=True)
    elif hdf5_wri == 'y':
        tdd.Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900)


# ------------------ 主程序入口 ------------------ #
if __name__ == "__main__":
    # queue = mp.Queue()
    # p = mp.Process(target=fetch_and_process, args=(queue,))
    # p.daemon = True
    # p.start()
    # app = StockMonitorApp(queue)

    # from multiprocessing import Manager
    # manager = Manager()
    # global_dict = manager.dict()  # 共享字典
    # import ipdb;ipdb.set_trace()

    # logger = init_logging("test.log")

    # logger = init_logging(log_file='monitor_tk.log',redirect_print=True)

    # logger.info("这是 print 输出")
    # logger.info("这是 logger 输出")

    # # 测试异常
    # try:
    #     1 / 0
    # except Exception:
    #     logging.exception("捕获异常")
    
    # 测试未捕获异常
    # 直接触发
    # 1/0
    # 仅在 Windows 上设置启动方法，因为 Unix/Linux 默认是 'fork'，更稳定
    if sys.platform.startswith('win'):
        mp.freeze_support() # Windows 必需
        mp.set_start_method('spawn', force=True) 
        # 'spawn' 是默认的，但显式设置有助于确保一致性。
        # 另一种方法是尝试使用 'forkserver' (如果可用)
        # mp.freeze_support()  # <-- 必须

    args = parse_args()  # 解析命令行参数
    # log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.ERROR)
    log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.INFO)
    # log_level = LoggerFactory.DEBUG

    # 直接用自定义的 init_logging，传入日志等级
    # logger = init_logging(log_file='instock_tk.log', redirect_print=False, level=log_level)
    logger.setLevel(log_level)
    logger.info("程序启动…")    

    # test_single_thread()
    # import ipdb;ipdb.set_trace()

    # if log_level == logging.DEBUG:
    # if logger.isEnabledFor(logging.DEBUG):
    #     logger.debug("当前已开启 DEBUG 模式")
    #     log = LoggerFactory.log
    #     log.setLevel(LoggerFactory.DEBUG)
    #     log.debug("log当前已开启 DEBUG 模式")

    # log.setLevel(LoggerFactory.INFO)
    # log.setLevel(Log.DEBUG)

    # ✅ 命令行触发 write_to_hdf
    if args.test:
        test_get_tdx()
        sys.exit(0)

    # 执行传入命令
    if args.cmd:
        if len(args.cmd) > 5:
            try:
                result = eval(args.cmd)
                print("执行结果:", result)
            except Exception as e:
                logger.error(f"执行命令出错: {args.cmd}\n{traceback.format_exc()}")

        # # 可选：补全关键字或函数名
        # completer = WordCompleter(['get_tdx_Exp_day_to_df', 'quit', 'exit'], ignore_case=True)

        # # 创建 PromptSession 并指定历史文件
        # session = PromptSession(history=FileHistory('.cmd_history'), completer=completer)

        # -------------------------------
        # 动态收集补全列表
        # -------------------------------
        def get_completions():
            completions = list(COMMON_COMMANDS)  # 先把常用命令放到最前面
            # completions = []
            for name, obj in globals().items():
                completions.append(name)
                if hasattr(obj, '__dict__'):
                    # 支持 obj. 子属性补全
                    completions.extend([f"{name}.{attr}" for attr in dir(obj) if not attr.startswith('_')])
            return completions

        # 创建 WordCompleter
        completer = WordCompleter(get_completions(), ignore_case=True, sentence=True)

        # 创建 PromptSession 并指定历史文件
        session = PromptSession(history=FileHistory('.cmd_history'), completer=completer)

        result_stack = []  # 保存历史结果

        HELP_TEXT = """
        调试模式命令:
          :help         显示帮助信息
          :result       查看最新结果
          :history      查看历史结果内容（DataFrame显示前5行）
          :clear        清空历史结果
        退出:
          quit / q / exit / e
        说明:
          最新执行结果总是存放在 `result` 变量中
          所有历史结果都存放在 `result_stack` 列表，可通过索引访问
        """

        def summarize(obj, head_rows=5):
            """根据对象类型返回可读摘要"""
            if isinstance(obj, pd.DataFrame):
                return f"<DataFrame shape={obj.shape}>\n{obj.head(head_rows)}"
            elif isinstance(obj, (list, tuple, set)):
                preview = list(obj)[:head_rows]
                return f"<{type(obj).__name__} len={len(obj)}>\n{preview}"
            elif isinstance(obj, dict):
                preview = dict(list(obj.items())[:head_rows])
                return f"<dict len={len(obj)}>\n{preview}"
            else:
                return repr(obj)

        print("调试模式启动 (输入 ':help' 获取帮助)")

        while True:
            try:
                cmd = session.prompt(">>> ").strip()
                if not cmd:
                    continue

                # 退出命令
                if cmd.lower() in ['quit', 'q', 'exit', 'e']:
                    print("退出调试模式")
                    break

                # 特殊命令
                if cmd.startswith(":"):
                    if cmd == ":help":
                        print(HELP_TEXT)
                    elif cmd == ":result":
                        if result_stack:
                            print(summarize(result_stack[-1]))
                        else:
                            print("没有历史结果")
                    elif cmd == ":history":
                        if result_stack:
                            for i, r in enumerate(result_stack):
                                print(f"[{i}] {summarize(r)}\n{'-'*50}")
                        else:
                            print("没有历史结果")
                    elif cmd == ":clear":
                        result_stack.clear()
                        print("历史结果已清空")
                    else:
                        print("未知命令:", cmd)
                    continue

                # 尝试 eval
                try:
                    temp = eval(cmd, globals(), locals())
                    result_stack.append(temp)   # 保存历史
                    result = result_stack[-1]   # 最新结果
                    globals()['result'] = result  # 注入全局，方便后续操作
                    print(summarize(temp))
                except Exception:
                    try:
                        exec(cmd, globals(), locals())
                        print("执行完成 (exec)")
                    except Exception:
                        print("执行异常:\n", traceback.format_exc())

            except KeyboardInterrupt:
                print("\nKeyboardInterrupt, 输入 'quit' 退出")
            except EOFError:
                print("\nEOF, 退出调试模式")
                break

        # while True:
        #     try:
        #         cmd = session.prompt(">>> ").strip()  # 使用 session.prompt 替代 input
        #         if not cmd:
        #             continue

        #         if cmd.lower() in ['quit', 'q', 'exit', 'e']:
        #             print("退出调试模式")
        #             break

        #         try:
        #             # 尝试 eval 执行表达式
        #             result = eval(cmd, globals(), locals())
        #             print("结果:", len(result))
        #         except Exception:
        #             # 如果 eval 出错，尝试 exec
        #             try:
        #                 result = exec(cmd, globals(), locals())
        #             except Exception:
        #                 print("执行异常:\n", traceback.format_exc())

        #     except KeyboardInterrupt:
        #         print("\n手动中断，退出调试模式")
        #         break

        # import readline
        # import rlcompleter

        # # 启用 Tab 补全和历史记录
        # # readline.parse_and_bind("tab: complete")
        # # 可以选择保存历史文件
        # history_file = ".cmd_history"
        # try:
        #     readline.read_history_file(history_file)
        # except FileNotFoundError:
        #     pass

        # while True:
        #     try:
        #         cmd = input(">>> ").strip()
        #         if not cmd:
        #             continue

        #         if cmd.lower() in ['quit', 'q', 'exit', 'e']:
        #             print("退出调试模式")
        #             break

        #         # 尝试 eval 执行
        #         try:
        #             result = eval(cmd, globals(), locals())
        #             print("结果:", result)
        #         except Exception:
        #             # 如果 eval 出错，尝试 exec（适合赋值或函数定义等）
        #             try:
        #                 exec(cmd, globals(), locals())
        #             except Exception:
        #                 print("执行异常:", traceback.format_exc())

        #     except KeyboardInterrupt:
        #         print("\n手动中断，退出调试模式")
        #         break
        #     finally:
        #         # 保存历史命令
        #         try:
        #             readline.write_history_file(history_file)
        #         except Exception:
        #             pass

        sys.exit(0)        
    # ✅ 命令行触发 write_to_hdf
    if args.write_to_hdf:
        write_to_hdf()
        sys.exit(0)
    app = StockMonitorApp()
    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)

    # monitor_rdp_and_scale(app)
    app.mainloop()
# --- 使用示例 ---
    

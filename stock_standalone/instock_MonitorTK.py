import os
import sys
import subprocess
import socket
import pickle
import struct
import warnings
import queue  # ✅ 全局引入 queue 以便捕获 queue.Empty
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*"
)
import json
import random
import time
import re
import gc
import argparse
import shutil
import traceback
import threading
import multiprocessing as mp
# 🛡️ [PERF] 全局阻断：彻底封杀子进程导入 keyboard 模块，杜绝底层 Hook 线程
if mp.current_process().name != "MainProcess":
    import sys
    sys.modules["keyboard"] = None
from queue import Queue, Empty
from multiprocessing.managers import BaseManager, SyncManager
# class StockManager(SyncManager): pass # 🛡️ [REMOVED] SyncManager is a performance killer. Using local dict instead.
import ctypes
import pyperclip
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union, Callable
import pandas as pd
pd.set_option('display.float_format', '{:.2f}'.format)
import numpy as np
import win32api
import win32file
import win32con
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont, scrolledtext
from tkinter import filedialog,Menu,simpledialog
from concurrent.futures import ThreadPoolExecutor
# import pyqtgraph as pg  # ⚡ 移至局部作用域以降低子进程内存
try:
    from PyQt6 import QtWidgets, QtCore, QtGui
    from PyQt6.QtCore import QTimer, pyqtSignal, QThread, QObject, QEventLoop, Qt
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
except ImportError:
    QtWidgets = QtCore = QtGui = None
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from types import SimpleNamespace
import signal
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx
from JohnsonUtil import johnson_cons as ct
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from logger_utils import LoggerFactory, init_logging, with_log_level
# from stock_live_strategy import StockLiveStrategy
# from realtime_data_service import DataPublisher
StockLiveStrategy = cct.LazyClass('stock_live_strategy', 'StockLiveStrategy')
DataPublisher = cct.LazyClass('realtime_data_service', 'DataPublisher')
DailyPulseEngine = cct.LazyClass('market_pulse_engine', 'DailyPulseEngine')
SignalDashboardPanel = cct.LazyClass('signal_dashboard_panel', 'SignalDashboardPanel')
# DataPublisher is now handled locally in the Main process for resource efficiency
from monitor_utils import (
    load_display_config, save_display_config, save_monitor_list, 
    load_monitor_list, list_archives, archive_file_tools, archive_search_history_list,
    ensure_parentheses_balanced
)
# from data_hub_service import DataHubService
from tdx_utils import (
    clean_bad_columns, cross_process_lock, get_clean_flag_path,
    cleanup_old_clean_flags, clean_expired_tdx_file, is_tdx_clean_done, sanitize,
    start_clipboard_listener
)
from data_utils import (
    calc_compute_volume, calc_indicators, fetch_and_process, send_code_via_pipe,test_opt
)
from gui_utils import (
    bind_mouse_scroll, get_monitor_by_point, rearrange_monitors_per_screen,get_monitor_index_for_window,
    is_window_covered_pg
)
from tk_gui_modules.dpi_mixin import DPIMixin
from strategy_manager import StrategyManager
from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.treeview_mixin import TreeviewMixin
from tk_gui_modules.gui_config import (
    WINDOW_CONFIG_FILE, MONITOR_LIST_FILE, WINDOW_CONFIG_FILE2,
    CONFIG_FILE, SEARCH_HISTORY_FILE,VOICE_ALERT_CONFIG_FILE, ICON_PATH as icon_path
)
from trading_logger import TradingLogger
from dpi_utils import set_process_dpi_awareness, get_windows_dpi_scale_factor
from ext_data_viewer import ExtDataViewer
from sys_utils import get_base_path
from stock_handbook import StockHandbook
from history_manager import QueryHistoryManager
import stock_indicator_help

from stock_logic_utils import get_row_tags,detect_signals,toast_message
from market_state_bus import MarketStateBus, AtomicStateStore # 🚀 [PERF]

from stock_logic_utils import test_code_against_queries,is_generic_concept,check_code
# faulthandler is enabled later after logger is ready

# Integrated Query Engine
try:
    from query_engine_util import query_engine
except ImportError:
    query_engine = None

from db_utils import *
# from kline_monitor import KLineMonitor
# from stock_selection_window import StockSelectionWindow
# from stock_selector import StockSelector
from column_manager import ColumnSetManager
from collections import Counter, OrderedDict, deque
import hashlib

# import trade_visualizer_qt6 as qtviz  # ⚡ 移至局部作用域
from sys_utils import assert_main_thread
import struct, pickle
from queue import Full
from alert_manager import AlertManager,get_alert_manager
from linkage_service import get_link_manager

# 全局单例
logger = init_logging(log_file='instock_tk.log',redirect_print=False) 
if query_engine:
    query_engine.set_logger(logger)
# Windows API 常量
LOGPIXELSX = 88
DEFAULT_DPI = 96.0

if sys.platform.startswith('win'):
    set_process_dpi_awareness()  # 假设设置为 Per-Monitor V2
    # 1. 获取缩放因子
    scale_factor = get_windows_dpi_scale_factor()
    # 2. 设置环境变量（在导入 Qt 之前）
    # 禁用 Qt 自动缩放，改为显式设置缩放因子
    # 打印检查
    logger.info(f"Windows 系统 DPI 缩放因子: {scale_factor}")
    # logger.info(f"已设置 QT_SCALE_FACTOR = {os.environ['QT_SCALE_FACTOR']}")

import faulthandler
faulthandler.enable()
# 🛡️ [DEBUG] 注册 Ctrl+Break 信号，用于在 UI 卡死时通过控制台打印所有线程堆栈
# if sys.platform.startswith('win') and hasattr(signal, 'SIGBREAK'):
#     try:
#         # [🚀 加固] 显式指定 all_threads=True 确保能打印出 UI 主线程和工作线程的所有状态
#         # faulthandler.register(signal.SIGBREAK, all_threads=True, chain=False)
#         # 1. SIGBREAK（可用就用）
#         # signal.signal(signal.SIGBREAK, lambda s, f: faulthandler.dump_traceback())
#         # 2. keyboard 热键（主力）
#         keyboard.add_hotkey(
#                 "ctrl+alt+d",
#                 lambda: faulthandler.dump_traceback()
#             )
#         logger.info("✅ faulthandler SIGBREAK (Ctrl+Break) 注册成功。提示：卡死时在控制台按 Ctrl+Break，输出将显示在标准错误流(stderr)中")
#     except Exception as e:
#         logger.warning(f"⚠️ faulthandler SIGBREAK 注册失败: {e}")


def dump_all():
    print("\n🔥 STACK TRACE DUMP\n")
    faulthandler.dump_traceback(all_threads=True)

# =========================
# Ctrl+Alt+D（最可靠）
# =========================
import multiprocessing as mp
if mp.current_process().name == "MainProcess":
    import keyboard
    keyboard.add_hotkey("ctrl+alt+d", dump_all)



# =========================
# SIGBREAK（仅在主线程 + 安全时）
# =========================
if sys.platform.startswith("win") and hasattr(signal, "SIGBREAK"):
    try:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGBREAK, lambda s, f: dump_all())
            logger.info("✅ SIGBREAK registered")
        else:
            logger.warning("⚠️ SIGBREAK skipped: not main thread")
        # 2. keyboard 热键（主力）
        if mp.current_process().name == "MainProcess":
            import keyboard
            keyboard.add_hotkey(
                    "ctrl+alt+d",
                    lambda: faulthandler.dump_traceback()
                )
    except Exception as e:
        logger.warning(f"⚠️ SIGBREAK register failed: {e}")

# from PyQt6 import QtWidgets, QtCore, QtGui  # ⚡ 移至局部作用域
# from trading_analyzerQt6 import TradingGUI
# from minute_kline_viewer_qt import KlineBackupViewer

# 全局退出计数 (3次 Ctrl+C 自动强制退出)
_exit_ctrl_c_count = 0
_exit_ctrl_c_time = 0
_exit_dialog_active = False # [NEW] 对话框存活标记

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


# def ask_exit():
#     """弹出确认框，询问是否退出"""
#     if messagebox.askyesno("确认退出", "你确定要退出吗？"):
#         root.destroy()
#         sys.exit(0)

# def signal_handler(sig, frame):
#     """捕获 Ctrl+C 信号"""
#     # 弹出确认框
#     ask_exit()


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
pending_alert_cycles = CFG.pending_alert_cycles
st_key_sort = CFG.st_key_sort

saved_width,saved_height = CFG.saved_width,CFG.saved_height

# -------------------- 常量 -------------------- #
MAX_ALERT_POPUP_QUEUE = 300 # [OPTIMIZED] 提升单批次弹窗队列容量，应对大规模并发
MAX_TOTAL_ALERTS = 200       # [OPTIMIZED] 放宽总弹窗上限，应对 148+ 级别瞬时爆发
# --- 信号分级与优先级配置 (Enhanced for Trend Tracking) ---
HIGH_PRIORITY_KEYWORDS = [
    "🚀", "强势结构", "SBC", "🔥", "趋势加速", "[ALPHA]", "[DRAGON]",
    "突破", "启动", "主升", "连阳", "强力反转", "量价齐升", "反包",
    "买入", "加仓", "核心热点", "龙头", "封板",
    "低开高走", "放量突破", "[HIGH]", "高优先级",
    "卖出", "清仓", "止损", "离场", "减仓", "减持", "风险", "跌破", "顶", "EXIT", "SELL" # [RESTORED] 恢复风险信号优先级
]

sort_cols: list[str]
sort_keys: list[str]
sort_cols, sort_keys = ct.get_market_sort_value_key('3 0')
DISPLAY_COLS: list[str] = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,sort_cols[:2])

BASE_DIR = get_base_path()

DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
ARCHIVE_DIR_DATA = os.path.join(ARCHIVE_DIR, "data") # 正确的 archives/data 位置
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR_DATA, exist_ok=True)


if not icon_path:
    logger.critical("MonitorTK.ico 加载失败，程序无法继续运行")

START_INIT = 0


DEFAULT_DISPLAY_COLS = [
    'name', 'grade', 'trade', 'boll', 'dff', 'df2', 'couts',
    'percent', 'per1d', 'perc1d', 'ra', 'ral',
    'topR', 'volume', 'red', 'lastdu4', 'category', 'emotion_status'
]

tip_var_status_flag = mp.Value('b', False)  # boolean

# def ___toast_message(master, text, duration=1500):
#     """短暂提示信息（浮层，不阻塞）"""
#     toast = tk.Toplevel(master)
#     toast.overrideredirect(True)
#     toast.attributes("-topmost", True)
#     label = tk.Label(toast, text=text, bg="black", fg="white", padx=10, pady=1)
#     label.pack()
#     try:
#         master.update_idletasks()
#         master_x = master.winfo_rootx()
#         master_y = master.winfo_rooty()
#         master_w = master.winfo_width()
#     except Exception:
#         master_x, master_y, master_w = 100, 100, 400
#     toast.update_idletasks()
#     toast_w = toast.winfo_width()
#     toast_h = toast.winfo_height()
#     toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
#     toast.after(duration, toast.destroy)


def get_visualizer_path(file_base='trade_visualizer_qt6'):
    """
    返回 trade_visualizer_qt6 的路径：
    - 开发环境 -> .py 文件路径
    - 打包 exe  -> exe 文件路径
    """
    if getattr(sys, 'frozen', False):
        # 打包后的 exe 所在目录
        base_path = os.path.dirname(sys.executable)
        path = os.path.join(base_path, f"{file_base}.exe")
        if os.path.exists(path):
            return path
        else:
            logger.error(f"Visualizer exe not found: {path}")
            return None
    else:
        # 开发环境
        base_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_path, f"{file_base}.py")
        if os.path.exists(path):
            return path
        else:
            logger.error(f"Visualizer script not found: {path}")
            return None

import functools
def send_with_visualizer(func):
    """装饰器：发送股票，同时根据 vis_var 自动打开可视化"""
    @functools.wraps(func)
    def wrapper(self, code, *args, **kwargs):
        if not code:
            return

        # 1️⃣ 调用原 send 方法
        result = func(self, code, *args, **kwargs)

        # 2️⃣ 更新状态（可选）
        if hasattr(self, 'update_send_status'):
            self.update_send_status(code)

        # 3️⃣ 自动启动可视化
        if getattr(self, 'vis_var', None) and self.vis_var.get():
            self.open_visualizer(code)

        return result

    return wrapper


# ============================================================================
# 🛡️ Qt 安全操作上下文管理器 - 防止 pyttsx3 COM 与 Qt GIL 冲突
# ============================================================================
# from contextlib import contextmanager

# @contextmanager
# def qt_safe_operation(app_instance):
#     voice = None
#     voice_paused = False
    
#     try:
#         # 获取语音引擎
#         if hasattr(app_instance, 'live_strategy') and app_instance.live_strategy:
#             voice = getattr(app_instance.live_strategy, '_voice', None)
#             if voice:
#                 # 暂停语音队列
#                 getattr(voice, 'pause', lambda: None)()
#                 voice_paused = True
                
#                 # 等待当前语音安全完成
#                 if hasattr(voice, 'wait_for_safe'):
#                     import time
#                     start = time.time()
#                     while not voice.wait_for_safe(timeout=0.1):
            #  [PHASE 2 FIX] Removed hazardous event pump to enforce thread sovereignty
#                         if time.time() - start > 5.0:
#                             break
#                 else:
            #  [PHASE 2 FIX] Removed hazardous event pump to enforce thread sovereignty
#                     import time
#                     time.sleep(0.05)
        
#         yield

#     finally:
#         if voice_paused and voice:
#             try:
#                 getattr(voice, 'resume', lambda: None)()
#             except Exception as e:
#                 logger.warning(f"Voice resume failed: {e}")



class StockMonitorApp(DPIMixin, WindowMixin, TreeviewMixin, tk.Tk):
    def __init__(self):
        # 🛡️ [RECOVERY] 提升 Windows 定时器精度，减少线程切换时的调度抖动 (解决 0x18 访问冲突的先决条件)
        if sys.platform.startswith('win'):
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
                logger.info("✅ Windows 定时器频率已优化 (1ms)")
            except Exception as e:
                logger.warning(f"⚠️ 优化定时器频率失败: {e}")

        # 🚀 [NEW] Centralized Data Hub Initialization (Multi-Point Protection)
        # Ensure DataHub is ready before any data processing starts
        # self.data_hub = DataHubService.get_instance()
        
        # ⭐ 启动计时 (分层线程池架构 v2 - 工业级)
        self._init_start_time = time.time()
        # 🔷 [ARCH] 分层线程池设计:
        #   pump_executor  (1线程) = 轻量编排: 解包/过滤/排序/调度 → Compute 返回后单点写 UI
        #   compute_executor (N线程) = CPU重计算: 信号检测/策略/情绪评分
        #   compute 线程永远不直接触碰 UI，结果必须回流 pump 后统一写入
        # ⭐ [PERF] 限制计算线程上限为 4，减少 GIL 争抢，确保 UI 响应优先级
        _compute_workers = min(4, getattr(cct, 'livestrategy_max_workers', 4))
        self.pump_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pump")
        self.compute_executor = ThreadPoolExecutor(max_workers=_compute_workers, thread_name_prefix="compute")
        self.executor = self.compute_executor  # 🛡️ 向后兼容别名
        logger.info(f"✅ Layered ThreadPool: pump=1 compute={_compute_workers} (Config: {cct.livestrategy_max_workers})")
        # 🔷 [VERSION] 快照版本号 + inflight 计数器
        self._snapshot_version     = 0
        self._compute_inflight     = 0
        self._compute_max_inflight = max(3, _compute_workers // 2)
        
        # 💥 关键修复: 必须在创建任何窗口(包括 root)之前设置 DPI 感知
        # 否则非客户区(标题栏)无法正确缩放
        try:
            from dpi_utils import set_process_dpi_awareness
            set_process_dpi_awareness()
        except ImportError:
            pass

        # 初始化 tk.Tk()
        super().__init__()
        
        # 初始化退出与任务追踪 system (必须放在最前面)
        self._is_closing = False
        self._after_ids = []
        self._last_dispatch_kick = 0  
        self._dispatch_running = False # ✅ [FIX] 调度运行状态位，防止 Watchdog 重复调度堆积
        self._is_ui_sync_pending = False # 🛡️ [NEW] UI 同步任务待处理标志位
        
        # 💥 关键修正 1：在所有代码执行前，初始化为安全值
        self.main_window = self   
        self.scale_factor = 1.0 
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font_size = self.default_font.cget("size")
        self.default_font_bold = tkfont.nametofont("TkDefaultFont").copy()
        self.default_font_bold.configure(family="Microsoft YaHei", size=10, weight="bold")
        # 在类中注册信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        global duration_sleep_time
        # 💥 关键修正 2：立即执行 DPI 缩放并重新赋值
        if sys.platform.startswith('win'):
            result_scale = self._apply_dpi_scaling()
            if result_scale is not None and isinstance(result_scale, (float, int)):
                self.scale_factor = result_scale


        self.last_dpi_scale = self.scale_factor
        # 3. 接下来是 Qt 初始化
        from PyQt6 import QtWidgets
        if not QtWidgets.QApplication.instance():
            self.app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])

        self.title("Stock Monitor")
        self.initial_w, self.initial_h, self.initial_x, self.initial_y  = self.load_window_position(self, "main_window", default_width=1200, default_height=480)
        self.monitor_windows = {}

        # 判断文件是否存在再加载
        if os.path.exists(icon_path):
            self._schedule_after(1000, lambda: self.iconbitmap(icon_path))

        else:
            logger.error(f"图标文件不存在: {icon_path}")

        self.sortby_col = None
        self.sortby_col_ascend = None
        self.select_code = None
        self.vis_select_code = None
        self.ColumnSetManager = None
        self.ColManagerconfig = None
        self._open_column_manager_job = None

        self._last_visualizer_code = None
        
        # ---------------------------------------------------------
        # 🚀 [ROOT-FIX] 核心稳定性：UI心跳、诊断看门狗、多进程联动中心
        # ---------------------------------------------------------
        # [NEW] 初始化全局 Debug 模式开关，用于控制高成本诊断（如 faulthandler）
        # 优先级：环境变量 > 全局配置 > 命令行日志等级 (-log debug)
        self._debug_mode = (logger.getEffectiveLevel() <= LoggerFactory.DEBUG or 
                            os.getenv("APP_DEBUG", "0") == "1" or 
                            getattr(cct.CFG, "DEBUG", False) 
                            )
        # [ROOT-FIX] 初始化联动代理与防重标志
        self.link_manager = get_link_manager()
        self._last_visualizer_time = 0
        self._last_linkage_data = None 
        self._visualizer_debounce_sec = 0.5
        self._enable_clipboard_linkage = True # [NEW] 初始化剪切板联动标志位，防止 AttributeError

        self._concept_dict_global = {}

        # 刷新开关标志
        self.refresh_enabled = True
        self._app_exiting = threading.Event()  # ⭐ [FIX] 用于控制后台线程退出
        
        self.visualizer_process = None # Track visualizer process
        self.qt_process = None         # [FIX] 初始化 qt_process 避免 send_df AttributeError
        self.viz_conn = None  # ⭐ [FIX] 使用 Pipe 代替 Queue，避免 GIL 崩溃
        self.viz_lifecycle_flag = mp.Value('b', True) # [FIX] 重命名为 viz_lifecycle_flag 确保唯一性
        self._vis_enabled_cache = False  # 🛡️ [NEW] 线程安全的 vis_var 影子变量
        self._send_sync_lock = threading.Lock() # ⭐ [NEW] 实例级执行锁，确保全生命周期只有一个同步循环在跑
        self._df_sync_running = False  # ⭐ [FIX] 初始化同步运行状态位，防止 send_df AttributeError
        self._df_first_send_done = False # ⭐ [FIX] 初始化首发标志
        self._force_full_sync_pending = False # ⭐ [FIX] 初始化强制全量同步标志
        self.sync_version = 0          # ⭐ 数据同步序列号
        self.last_vis_var_status = None 
        self._feedback_listener_thread = None  # 🛡️ [NEW] 线程守卫：防止重复启动监听器
        # 4. 初始化全局状态存储 (代替昂贵的 SyncManager)
        try:
            logger.info("🚀 [PERF] 启用跨进程状态存储 (mp.Manager + mp.Queue)...")
            from multiprocessing import Manager
            self._sync_manager = Manager()
            self.global_dict = self._sync_manager.dict()
            self.global_dict["resample"] = resampleInit
            
            # 🚀 [NEW] 初始化原子状态总线 (P0-3)
            # 用于取代多 Queue 堆积，实现"拉取式" UI 刷新
            from market_state_bus import MarketStateBus
            self.market_bus = MarketStateBus.get_instance()
            
            # 🚀 [NEW] UI 专用原子快照存储 (P0-2)
            self.ui_state_store = AtomicStateStore()
            
            # 🔥 同步初始化 DataPublisher (启动时直接加载)
            self.realtime_service = DataPublisher(high_performance=True)
            self._realtime_service_ready = True
            
            # 🚀 [NEW] 全局初始化赛道探测器
            try:
                from bidding_momentum_detector import BiddingMomentumDetector
                self.racing_detector = BiddingMomentumDetector(
                    realtime_service=self.realtime_service, 
                    lazy_load=True,
                    silent_mode=True
                )
                self.realtime_service.racing_detector = self.racing_detector
                self.racing_detector.ensure_data_ready_async()
                logger.info("✅ BiddingMomentumDetector 已全局就绪并在后台初始化")
            except Exception as rd_e:
                self.racing_detector = None
                logger.error(f"⚠️ BiddingMomentumDetector 初始化失败: {rd_e}")

            logger.info(f"✅ RealtimeDataService (Global) 已就绪 (Main PID: {os.getpid()})")
            
            self._last_ui_heartbeat = time.time()
            self._ui_heartbeat()
            self.after(2000, self._start_watchdog) 
            logger.info("✅ UI Heartbeat & Watchdog (Delayed) initialized.")

        except Exception as e:
            logger.error(f"❌ 状态存储初始化失败: {e}\n{traceback.format_exc()}")
            self.realtime_service = None
            self._realtime_service_ready = False
            self.global_dict = {"resample": resampleInit, 'init_error': str(e)}
        
        # Restore global_values initialization
        self.global_values = cct.GlobalValues(self.global_dict)
        
        # [NEW] 额外监控列表
        if 'extra_monitor_codes' not in self.global_dict:
            self.global_dict['extra_monitor_codes'] = []
        resample = self.global_values.getkey("resample")
        self.global_values.setkey("resample", resample)

        self.blkname = ct.Resample_LABELS_Blk[resample] or "060.blk"
        self.global_values.setkey("blkname", self.blkname)

        self._detailed_analysis_win: Optional[tk.Toplevel] = None
        self.strategy_report_win: Optional[tk.Toplevel] = None
        self._voice_monitor_win: Optional[tk.Toplevel] = None
        self._realtime_monitor_win: Optional[tk.Toplevel] = None
        self._stock_selection_win: Optional[tk.Toplevel] = None
        self.txt_widget = None

        # 🛡️ 动态列订阅管理
        self.mandatory_cols: set[str] = {
            'code', 'name', 'trade', 'high', 'low', 'open', 'ratio', 'volume', 'amount',
            'percent', 'per1d', 'perc1d', 'nclose', 'ma5d', 'ma10d', 'ma20d', 'ma60d',
            'ma51d', 'lastp1d', 'lastp2d', 'lastp3d', 'lastl1d', 'lasto1d', 'lastv1d', 'lasth1d',
            'macddif', 'macddea', 
            'macd', 'macdlast1', 'macdlast2', 'macdlast3', 'rsi', 'kdj_j', 'kdj_k', 
            'kdj_d', 'upper', 'lower', 'max5', 'high4', 'curr_eval', 'trade_signal',
            'now', 'signal', 'signal_strength', 'emotion', 'win', 'sum_perc', 'slope',
            'vol_ratio', 'power_idx', 'category', 'lastdu4',
            'dff', 'dff2', 'Rank', 'buy', 'llastp' # 🛡️ 增加可视化所需的缺失列
        }
        self.update_required_columns()

        # ----------------- 控件框 ----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=1)

        self.st_key_sort = self.global_values.getkey("st_key_sort") or st_key_sort
        
        # 🚀 [NEW] 全局概念看板缓存初始化 (Hotfix for UnboundLocalError)
        self._global_concept_init_data = {}
        self._global_concept_prev_data = {}
        self._concept_data_loaded = False

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
        self._schedule_after(200, lambda: self.update_status_bar_width(pw, left_frame, right_frame))

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


        bind_mouse_scroll(self.tree)


        self.current_cols = ["code"] + DISPLAY_COLS
        # TreeView 列头
        for col in ["code"] + DISPLAY_COLS:
            width = 80 if col=="name" else 60
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, self.sortby_col_ascend))
            self.tree.column(col, width=width, anchor="center", minwidth=50)


        # 双击表头绑定

        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-2>", self.copy_code)
        

        self.df_all = pd.DataFrame()      # 保存 fetch_and_process 返回的完整原始数据
        self.current_df = pd.DataFrame()
        self._df_lock = threading.Lock()  # 🛡️ [NEW] 保护 df_all 并发读写
        self._send_df_wake_event = threading.Event()  # 🛡️ [PERF] 用于非阻塞唤醒 send_df，代替 time.sleep 循环

        # 队列接收子进程数据 (Resolved mp.Queue GIL Crash)
        self.queue = mp.Queue(maxsize=cct.multiprocessingQueue or 10)
        self.signal_bridge_queue = mp.Queue(maxsize=50)  # ⭐ [NEW] 跨进程信号桥接队列
        self.viz_conn = mp.Pipe()           # ⭐ [NEW] 跨进程指令 Pipe (parent_conn, child_conn)

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
        
        # 🚀 [IPC OPTIMIZATION] 统一 IPC 发送队列，防止高频点击产生大量僵尸线程
        import queue as q_lib
        if not hasattr(self, '_ipc_task_queue'):
            self._ipc_task_queue = q_lib.Queue(maxsize=100)
            self._ipc_worker_stop = threading.Event()
            self._ipc_worker_thread = threading.Thread(target=self._ipc_worker_loop, daemon=True, name="MonitorTK_IPC_Worker")
            self._ipc_worker_thread.start()

        #总览概念分析前5板块
        self.concept_top5 = None
        #初始化延迟运行live_strategy
        self._live_strategy_first_run = True
        # ✅ 初始化标注手札
        self.handbook = StockHandbook()
        # ✅ 初始化实时监控策略 (延迟初始化，防止阻塞主窗口显示)
        self.live_strategy = None
        
        self._schedule_after(3000, self._init_live_strategy)
        
        # [NEW] For Market Temperature Sync
        self._last_index_fetch_ts = 0.0
        self._cached_indices_data = []
        self._cached_market_temp = 50.0
        
        # ✅ 初始化 55188 数据更新监听状态
        self.last_ext_data_ts_local = 0
        # self.after(10000, self._check_ext_data_update)
        
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
                logger.info("✅ 性能优化器已强制开启 (增量更新模式)")
            except Exception as e:
                logger.warning(f"⚠️ 性能优化器初始化失败,使用传统模式: {e}")
                self._use_incremental_update = False
        else:
            self._use_incremental_update = True # 强制尝试
            logger.info("ℹ️ 尝试开启增量刷新模式...")

        # ⭐ [NEW] UI 性能优化与防抖
        self._update_pos_timer = None
        self._last_alert_time = 0
        self._alert_count_per_sec = 0
        
        # ⭐ [NEW] 启动后自动打开信号仪表盘 (同步更新前)
        self._schedule_after(500, self.open_live_signal_viewer)

        # 启动后台进程
        self._start_process()

        # 定时检查队列
        self._schedule_after(1000, self.update_tree)

        # ✅ UI 线程任务调度队列 (解决 Qt -> Tkinter 跨线程/GIL 问题)
        self.tk_dispatch_queue = queue.Queue()
        self._is_pumping_events = False # 🚀 [NEW] 重入守卫
        self._process_dispatch_queue()


        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)
        # 📋 启动后台剪贴板监听服务 (包含自动查重逻辑，避免重复发送当前已选中代码)
        self.clipboard_monitor = start_clipboard_listener(
            self.sender, 
            ignore_func=lambda code: code.strip() == str(getattr(self, 'select_code', '')).strip(),
            on_new_code=self._on_clipboard_code_visualizer
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)  
        # self.tree.bind("<Button-1>", self.on_single_click)
        # ✅ 绑定单击事件用于显示股票信息提示框
        # self.tree.bind("<ButtonRelease-1>", self.on_tree_click_for_tooltip)
        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)

        self.bind("<Alt-c>", lambda e:self.open_column_manager())
        self.bind("<Control-slash>", lambda e: self.open_indicator_help())

        # [NEW] 每日复盘入口按钮
        try:
             from market_pulse_viewer import MarketPulseViewer
             self._pulse_viewer_class = MarketPulseViewer
             # [NEW] 存档按钮 (对调至此)
             archive_btn = tk.Button(ctrl_frame, text="存档", 
                                 font=self.default_font, pady=2,
                                 command=self.open_archive_loader)
             archive_btn.pack(side="left", padx=5)
             
             # [NEW] 策略按钮 (对调至此)
             str_btn = tk.Button(ctrl_frame, text="策略", 
                                 fg="blue", font=self.default_font_bold, pady=2,
                                 command=lambda: self.open_strategy_manager())
             str_btn.pack(side="left", padx=5)
        except ImportError as e:
             logger.error(f"Failed to import MarketPulseViewer: {e}")
             self._pulse_viewer_class = None

        self.bind("<Alt-d>", lambda event: self.open_handbook_overview())
        self.bind("<Alt-e>", lambda event: self.open_voice_monitor_manager())
        self.bind("<Alt-g>", lambda event: self.open_trade_report_window())
        self.bind("<Alt-b>", lambda event: self.close_all_alerts())
        self.bind("<Alt-s>", lambda event: self.open_strategy_manager())
        self.bind("<Alt-k>", lambda event: self.open_market_pulse())
        self.bind("<Alt-l>", lambda event: self.open_live_signal_viewer())
        self.bind("<Alt-h>", lambda event: self.send_command_to_visualizer("TOGGLE_HOTLIST"))
        self.bind("<Alt-w>", lambda event: self.open_dna_auditor_top50())
        # 启动周期检测 RDP DPI 变化
        self._pg_default_sort_reverse = True # 默认看涨视角
        self._schedule_after(3000, self._check_dpi_change)
        self.auto_adjust_column = self.dfcf_var.get()
        # self.bind("<Configure>", self.on_resize)
        
        # ⭐ 启动完成计时
        init_elapsed = time.time() - self._init_start_time
        logger.info(f"🚀 程序初始化完成 (总耗时: {init_elapsed:.2f}s)")

        # # 🚀 [NEW] 初始化完成联动：如果 vis 开启，自动打开可视化窗口，避免后续“冷启动”引发 GIL 崩溃
        # if hasattr(self, 'vis_var') and self.vis_var.get():
        #     # # 获取初始化时可能已有的首行代码
        #     # target_code = getattr(self, "select_code", None)
        #     # if not target_code:
        #     #     first_item = self.tree.get_children()
        #     #     if first_item:
        #     #         target_code = self.tree.item(first_item[0], "values")[0]
            
        #     # if target_code:
        #     #     # 延迟 2 秒启动，确保主窗口数据已完成第一轮加载并渲染
        #     #     self._schedule_after(30000, lambda: self.open_visualizer(target_code))
        #     self._schedule_after(45000, lambda: self.open_visualizer('000001'))
            
        if logger.level == LoggerFactory.DEBUG:
            cct.print_timing_summary(top_n=6)

    def _ipc_worker_loop(self):
        """[ROOT-FIX] 核心稳定性：唯一背景线程处理发往 Visualizer 的指令。
        采用“状态驱动”而非“任务驱动”，如果积压了多个更新，只执行最后一次以节省 IO。
        """
        logger.info("🚀 MonitorTK IPC Background Worker started.")
        latest_tasks = {} # 用于存储不同类型的最新指令 {'DF_UPDATE': payload, 'SWITCH_CODE': payload}
        
        while not self._ipc_worker_stop.is_set():
            try:
                # 1. 尽可能清空队列，捕捉最新的状态意图
                got_any = False
                while True:
                    try:
                        # 快速非阻塞弹出所有堆积任务
                        cmd_tuple = self._ipc_task_queue.get_nowait()
                        if cmd_tuple:
                            cmd_type, payload = cmd_tuple
                            latest_tasks[cmd_type] = payload  # 覆盖旧状态，保留最后一次意图
                            got_any = True
                        self._ipc_task_queue.task_done()
                    except Empty:
                        break

                # 2. 如果没获取到新任务，则阻塞等待 0.5s
                if not got_any:
                    try:
                        cmd_tuple = self._ipc_task_queue.get(timeout=0.5)
                        if cmd_tuple:
                            cmd_type, payload = cmd_tuple
                            latest_tasks[cmd_type] = payload
                            got_any = True
                        self._ipc_task_queue.task_done()
                    except Empty:
                        continue

                # 3. 执行当前收集到的所有“最终意图”
                if got_any and latest_tasks:
                    # 检查 Qt 进程存活性
                    if hasattr(self, 'qt_process') and self.qt_process and self.qt_process.is_alive():
                        if hasattr(self, 'viz_conn') and self.viz_conn:
                            conn = self.viz_conn[0]
                            # [FIX] 统一 IPC 协议：直接发送 (cmd_type, payload) 二元组。
                            # 防止 Visualizer 在解包时报 "too many values to unpack (expected 2)"
                            for t_type in list(latest_tasks.keys()):
                                payload = latest_tasks.pop(t_type)
                                try:
                                    conn.send((t_type, payload))
                                except Exception as e:
                                    logger.error(f"Pipe send error [{t_type}]: {e}")
                                    break # 管道可能已断开
                
                time.sleep(0.01) # 微小休眠防止空转

            except Exception as e:
                logger.error(f"IPC Worker Error: {e}\n{traceback.format_exc()}")
                time.sleep(1)

    def _async_viz_send(self, cmd, payload):
        """发送指令到可视化器 (入队不阻塞)"""
        try:
            self._ipc_task_queue.put((cmd, payload), block=False)
        except Full:
            # 如果队列满了，通常意味着可视化器端彻底卡死，清空旧任务优先响应新任务
            try:
                while not self._ipc_task_queue.empty(): self._ipc_task_queue.get_nowait()
                self._ipc_task_queue.put((cmd, payload), block=False)
            except: pass


    def open_dna_auditor_top50(self,limitCode=20):
        """🚀 [DNA-BATCH] 极限审计：支持多选审计，单选则从当前行向下 20 只 (包含选中项)"""
        items = list(self.tree.get_children())
        if not items:
            from tkinter import messagebox
            messagebox.showinfo("提示", "当前列表为空，无法进行审计")
            return
            
        selection = self.tree.selection()
        
        # 🚀 [FIX] 智能检测列索引
        all_cols = list(self.tree["columns"])
        idx_code, idx_name = -1, -1
        for i, col in enumerate(all_cols):
            c_lower = str(col).lower()
            if c_lower in ["code", "代码"]: idx_code = i
            if c_lower in ["name", "名称"]: idx_name = i
        
        if idx_code == -1: idx_code = 0
        if idx_name == -1: idx_name = 1

        target_items = []
        if len(selection) > 1:
            # 多选模式：仅审计选中的 (上限 20)
            target_items = list(selection)[:limitCode]
        elif len(selection) == 1:
            # 单选模式：从选中行开始向下 20 只 (包含本身)
            try:
                start_idx = items.index(selection[0])
            except ValueError:
                start_idx = 0
            target_items = items[start_idx : start_idx + limitCode]
        else:
            # 默认：前 20 只
            target_items = items[:limitCode]
        
        code_to_name = {}
        for it in target_items:
            try:
                vals = self.tree.item(it, 'values')
                if not vals: continue
                c = str(vals[idx_code]).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                
                n = str(vals[idx_name]).strip()
                if n.startswith("🔔"): n = n.replace("🔔", "")
                
                if c and c != "N/A" and len(c) == 6:
                    code_to_name[c] = n
            except Exception:
                continue
        
        if code_to_name:
            # 🚀 [NEW] 检测历史截止日期
            # end_date = None
            # if hasattr(self, 'sector_bidding_panel') and getattr(self.sector_bidding_panel, '_is_history_mode', False):
            #     end_date = getattr(self.sector_bidding_panel, '_history_date', None)
            self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date())
            # self._run_dna_audit_batch(code_to_name, end_date=end_date)

        

    def open_market_pulse(self):
        """Open the Daily Market Pulse Dashboard."""
        if not self._pulse_viewer_class:
            messagebox.showerror("Error", "Market Pulse module missing.")
            return
            
        # Ensure we have strategy loaded
        if not self.live_strategy:
             messagebox.showwarning("Wait", "Strategy initializing... please wait.")
             return
             
        # Check if already open
        if hasattr(self, '_pulse_win') and self._pulse_win and self._pulse_win.winfo_exists():
            self._pulse_win.lift()
            return
            
        self._pulse_win = self._pulse_viewer_class(self, self) # Pass self as master and monitor_app

    def open_live_signal_viewer(self):
        """打开实时信号仪表盘 (Alt+L)"""
        try:
            # 🛡️ Qt6 窗口由 PyQt6 驱动
            if not hasattr(self, "_signal_dashboard_win") or self._signal_dashboard_win is None:
                # 确保 Qt 环境已初始化
                from PyQt6 import QtWidgets
                if not QtWidgets.QApplication.instance():
                    self._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])
                
                # 使用 LazyClass 加载或直接导入
                from signal_dashboard_panel import SignalDashboardPanel
                
                self._signal_dashboard_win = SignalDashboardPanel()
                self._signal_dashboard_win.parent_app = self # ✅ [NEW] 记录主窗口引用
                # ✅ [FIX] 跨线程联动安全：将互操作封装进任务队列，由 Tkinter 主线程执行
                self._signal_dashboard_win.code_clicked.connect(
                    lambda c, n: self.tk_dispatch_queue.put(lambda: self.on_code_click(c))
                )
                
            self._signal_dashboard_win.show()
            self._dashboard_first_sync_done = False # ⚡ 强制触发立即同步数据
            self._signal_dashboard_win.raise_()
            self._signal_dashboard_win.activateWindow()

            toast_message(self, "实时信号仪表盘已启动")
            
        except Exception as e:
            logger.error(f"打开实时信号仪表盘失败: {e}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to open Signal Dashboard: {e}")

    def open_racing_panel(self):
        """打开竞价赛马与节奏监控面板 (Alt+M)"""
        # [🚀 统一防抖保护] 赛马与回测共享冷却时间，避免资源抢占与 GIL 崩溃 (10s 阈值)
        now = time.time()
        last_unified = getattr(self, '_last_racing_backtest_unified_t', 0)
        if now - last_unified < 10.0:
            logger.warning("🏁 [Racing/Backtest] 操作太频繁（统一防抖中），请稍候...")
            toast_message(self, f"🏁 操作太频繁，请等待 {int(10.0 - (now - last_unified))}s")
            return
        self._last_racing_backtest_unified_t = now

        # [🚀 唯一性保护] 确保同时只有一个赛马相关进程 (实盘赛马与回测互斥)
        if hasattr(self, 'backtest_process') and self.backtest_process and self.backtest_process.is_alive():
            logger.warning("🏁 [Racing] 回测进程正在运行中，无法开启实盘赛马。")
            toast_message(self, "🏁 回测进程运行中，请先关闭")
            return

        try:
            # [🚀 鲁棒性增强] 增加对 C++ 侧对象是否存活的实质性判定
            is_alive = False
            if hasattr(self, "_racing_panel_win") and self._racing_panel_win is not None:
                try:
                    self._racing_panel_win.isVisible()
                    is_alive = True
                except RuntimeError:
                    self._racing_panel_win = None

            if not is_alive:
                # 确保 Qt 环境已初始化
                from PyQt6 import QtWidgets
                if not QtWidgets.QApplication.instance():
                    self._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])

                from bidding_racing_panel import BiddingRacingRhythmPanel
                
                # 关键：传入全局唯一的 racing_detector，实现数据下沉复用
                self._racing_panel_win = BiddingRacingRhythmPanel(
                    detector=self.racing_detector,
                    main_app=self,
                    on_code_callback=self.on_code_click
                )
                
                # [NEW] ⚡ 建立双向生命周期闭环：窗口关闭时自动置空引用并触发防抖
                self._racing_panel_win.closed.connect(self._on_racing_panel_closed)
                
                # 跨线程联动安全：双击个股跳转
                self._racing_panel_win.on_code_callback = lambda c: self.tk_dispatch_queue.put(lambda: self.on_code_click(c))

            # [ROOT-FIX] ⚡ 确保赛马探测器数据已加载并立即同步当前快照，防止首屏空洞
            if hasattr(self, 'racing_detector') and self.racing_detector:
                self.racing_detector.ensure_data_ready_async()
                
                # [OPTIMIZED] ⚡ 判定数据新鲜度：如果后台 DataPublisher 已经唤醒了探测器 (data_version > 0)，
                # [🚀 PERFORMANCE OPTIMIZATION] 对冲冷启动数据灌入导致的 2-5s UI 假死
                # 将昂贵的探测器初始化移至后台线程，主界面立即显示并进入“极速同步”状态。
                if getattr(self.racing_detector, 'data_version', 0) == 0:
                    curr_df = getattr(self, 'df_all', None)
                    if curr_df is not None and not curr_df.empty:
                        logger.info("⚡ Racing Panel: Bootstrap initial data for detector in background...")
                        
                        def _bg_bootstrap():
                            try:
                                # 1. 注册代码并预计算评分
                                self.racing_detector.register_codes(curr_df)
                                self.racing_detector.update_scores(force=True)
                                # 2. 通知 UI 线程计算完成，触发首次面板刷新
                                self.after(0, lambda: self._racing_panel_win.update_visuals() if hasattr(self, '_racing_panel_win') and self._racing_panel_win else None)
                                logger.info("✅ Racing Panel: Background bootstrap complete.")
                            except Exception as e:
                                logger.exception(f"❌ Racing Panel: Background bootstrap failed: {e}")

                        threading.Thread(target=_bg_bootstrap, daemon=True, name="RacingBootstrap").start()
                        toast_message(self, "🏁 赛马面板数据后台预热中...")
                else:
                    logger.debug(f"⚡ Racing Panel: Using pre-warmed detector (Version: {self.racing_detector.data_version})")

            self._racing_panel_win.show()
            self._racing_panel_win.raise_()
            self._racing_panel_win.activateWindow()
            self._racing_first_sync_done = False # [NEW] ⚡ 强制触发立即同步大盘温度数据
            toast_message(self, "🏁 竞价赛马监控已启动")

        except Exception as e:
            logger.error(f"打开竞价赛马面板失败: {e}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to open Racing Panel: {e}")

    def open_indicator_help(self):
        """Open the Indicator Help and Search window (Ctrl + /)"""
        stock_indicator_help.show_help(self)


    def _on_racing_panel_closed(self):
        """赛马面板关闭回调：置空引用并刷新防抖计时器"""
        self._racing_panel_win = None
        # 关键：关闭时刻也更新计时器，确保关闭后不能立即启动另一个，等待 OS 释放资源 (10s)
        self._last_racing_backtest_unified_t = time.time()
        logger.info("🏁 [RacingPanel] 窗口已关闭，防抖保护已激活 (10s)")




    def _put_deduped_task(self, key, task_fn):
        """
        [AGGRESSIVE AGGREGATOR] 高性能任务聚合（末尾胜出模式）。
        如果主线程繁忙，新任务会覆盖存储区中的旧任务函数，但确保队列中只有一个触发标记。
        """
        if not hasattr(self, '_task_storage'):
            self._task_storage = {} # 存储每个 key 对应的最新执行函数
        if not hasattr(self, '_pending_task_keys'):
            self._pending_task_keys = set()
            
        # ⭐ 核心：始终更新存储区为“最新”版本（Latest Wins）
        self._task_storage[key] = task_fn

        # 如果对应的触发标记已在队列中，则直接返回，避免队列膨胀
        if key in self._pending_task_keys:
            return 

        self._pending_task_keys.add(key)
        
        def _aggregator_wrapper():
            try:
                # 执行时从存储区取出当前最新的函数
                fn = self._task_storage.pop(key, None)
                self._pending_task_keys.discard(key)
                if fn: fn()
            except Exception as e:
                logger.error(f"Aggregated task [{key}] error: {e}")
        
        _aggregator_wrapper.key = f"agg:[{key}]"
        if hasattr(self, 'tk_dispatch_queue'):
            # 控制队列深度：如果主线程跟不上，且队列过长，则启动丢弃策略
            if self.tk_dispatch_queue.qsize() > 100:
                if key.startswith('extra_'): 
                    self._task_storage.pop(key, None)
                    return
            self.tk_dispatch_queue.put(_aggregator_wrapper)
        else:
            self._schedule_after(0, _aggregator_wrapper)

    def _safe_schedule_dispatch(self, delay=50):
        if getattr(self, "_dispatch_scheduled", False):
            return

        self._dispatch_scheduled = True

        def _run():
            if getattr(self, "_dispatch_running", False):
                self._dispatch_scheduled = False   # ✅ 防止卡死
                return

            self._dispatch_running = True

            try:
                self._process_dispatch_queue()
            except Exception as e:
                logger.error(f"dispatch run error: {e}")
            finally:
                self._dispatch_running = False
                self._dispatch_scheduled = False   # ✅ 必须释放（核心）

        try:
            self.after(delay, _run)
        except Exception as e:
            logger.error(f"schedule fail: {e}")
            self._dispatch_scheduled = False

    def _process_dispatch_queue(self):
        """[STABLE v5] 单心跳 + 时间预算 + 心跳检测 + 防重复调度"""
        import functools
        from collections import Counter
        from queue import Empty
        import time

        if getattr(self, '_is_closing', False) or (
            getattr(self, '_app_exiting', None) and self._app_exiting.is_set()
        ):
            return
        if getattr(self, "_dispatch_running", False):
            return   # ❗ 防止重入

        self._dispatch_running = True

        now = time.perf_counter()
        start_t = now
        processed_count = 0
        next_delay = 50   # 默认节奏（比你之前更稳）

        task_stats = Counter()
        max_single_task = {"name": "None", "dur": 0}

        # UI dispatch 预算 (与 pump_lag 解耦 — 专注主线渲染)
        MAX_TASKS_PER_CYCLE = 8
        TIME_BUDGET_S = 0.020    # 20ms — 保持 UI 可拖动的黄金预算
        SLOW_TASK_WARN_MS = 500  # 慢任务阈值降至 500ms

        try:
            while processed_count < MAX_TASKS_PER_CYCLE:

                # ⛔ 预算检查：留出极小空隙给 OS 其他事件
                if (time.perf_counter() - start_t) > TIME_BUDGET_S:
                    next_delay = 10
                    break

                try:
                    task = self.tk_dispatch_queue.get_nowait()
                except Empty:
                    # 队列空：如果没有活跃任务，延长检查间隔以节省省电
                    next_delay = 150 if processed_count == 0 else 50
                    break
                
                if not callable(task):
                    continue

                # 执行任务
                try:
                    # 1. 获取任务描述名称 (用于性能监控追踪)
                    t_name = getattr(task, 'key', None)
                    if not t_name:
                        t_func = task.func if hasattr(task, 'func') else task
                        t_name = getattr(t_func, '__qualname__', getattr(t_func, '__name__', str(t_func)))
                    
                    if not isinstance(t_name, str): t_name = str(t_name)
                    # 强力清洗：全局剔除冗余类名和闭包标记
                    t_name = t_name.replace("StockMonitorApp.", "").replace(".<locals>", "")

                    task_start = time.perf_counter()
                    try:
                        task()
                    except tk.TclError as te:
                        # 🛡️ [GUARD] 屏蔽由于窗口销毁导致的无效命令报错
                        if "invalid command name" not in str(te):
                            logger.error(f"TclError in Dispatch [{t_name}]: {te}")
                    task_dur = (time.perf_counter() - task_start) * 1000
                    
                    # ⭐ [PERFORMANCE] 监测主线程耗时任务
                    # if task_dur > 500:
                    #     logger.warning(f"⚠️ [UI_BLOCK] Task '{t_name}' took {task_dur:.2f}ms (Budget={TIME_BUDGET_S*1000}ms)")
                    
                    processed_count += 1
                    
                    if " at 0x" in t_name:
                        t_name = t_name.split(" at 0x")[0]
                    if t_name.startswith("<bound method "):
                        t_name = t_name.replace("<bound method ", "").split(" of ")[0]
                    
                    # 限制长度
                    t_name = t_name[:60]
                    
                    # 持久化统计 (跨多次 dispatch 累加)
                    if not hasattr(self, '_cycle_audit'):
                        self._cycle_audit = {'times': {}, 'counts': {}, 'start': time.time()}
                    self._cycle_audit['times'][t_name] = self._cycle_audit['times'].get(t_name, 0) + task_dur
                    self._cycle_audit['counts'][t_name] = self._cycle_audit['counts'].get(t_name, 0) + 1
                    
                    # 统计更新
                    task_stats[t_name] += 1
                    if task_dur > max_single_task['dur']:
                        max_single_task.update({"name": t_name, "dur": task_dur})

                    # 统计慢任务
                    # if task_dur > SLOW_TASK_WARN_MS:
                    #     logger.warning(f"🚨 [UI_BLOCK] 慢任务: {t_name} {task_dur:.1f}ms")

                    # 🚀 [YIELD] 每 5 个任务主动呼吸一次，保持窗口可拖动
                    if processed_count % 5 == 0:
                        self.update_idletasks()
                except Exception as e:
                    logger.exception(f"Dispatch Error: {e}")

            # 积压监控
            remaining = self.tk_dispatch_queue.qsize()
            if remaining > 300:
                logger.warning(f"⚠️ 队列积压: {remaining}")

        except Exception as e:
            logger.error(f"Dispatch error: {e}")

        finally:
            total_time = (time.perf_counter() - start_t) * 1000

            self._dispatch_running = False
            self._last_task_finish_time = time.time()

            # --- [高级功能] 周期性能审计排行 (已改为手动触发，见 show_ui_performance_audit) ---
            
            # 保留原有的单波次严重阻塞报警
            if processed_count > 0 and total_time > 2000:
                logger.warning(f"🕒 Batch Delay: {total_time:.1f}ms | {processed_count} tasks | max: {max_single_task['name']}")


            # =========================
            # ✅ 新版本（稳定）
            # =========================
            def _run():
                self._dispatch_scheduled = False   # 只负责释放调度标记
                try:
                    self._process_dispatch_queue()
                except Exception as e:
                    logger.error(f"dispatch run error: {e}")

            # 只防止“短时间重复调度”
            if not getattr(self, "_dispatch_scheduled", False):
                self._dispatch_scheduled = True
                try:
                    self.after(next_delay, _run)
                except Exception as e:
                    logger.error(f"schedule fail: {e}")
                    self._dispatch_scheduled = False   # ✅ 失败必须释放


    def _schedule_after(self, ms, func, *args, key=None, debounce=True, bind_widget=None):
        """
        【工业融合最终版 v4】
        Qt + Tk 双层防抖 + 安全队列 + 统一task_key

        核心优化：
        - Qt只做“意图过滤”，不做执行清理
        - Tk负责生命周期清理（唯一权威）
        - 去除 safe_call 内 pop（避免竞态）
        - task_key 全局唯一一致
        """

        import time
        import threading
        import queue

        # -------------------------
        # 1. 生命周期保护
        # -------------------------
        if getattr(self, "_is_closing", False):
            return None

        if not hasattr(self, "_after_jobs"):
            self._after_jobs = {}

        if not hasattr(self, "_qt_debounce_map"):
            self._qt_debounce_map = {}

        if not hasattr(self, "_last_task_finish_time"):
            self._last_task_finish_time = time.time()

        # -------------------------
        # 2. queue 初始化
        # -------------------------
        if not hasattr(self, "tk_dispatch_queue"):
            self.tk_dispatch_queue = queue.Queue()

            if hasattr(self, "after"):
                try:
                    self.after(1, self._process_dispatch_queue)
                except:
                    pass

        # -------------------------
        # 3. widget safety
        # -------------------------
        if bind_widget is not None:
            try:
                if not bind_widget.winfo_exists():
                    return None
            except:
                return None

        # -------------------------
        # 4. 统一 task_key（唯一权威）
        # -------------------------
        try:
            task_key = key if key is not None else (func.__qualname__, id(func), len(args))
        except:
            task_key = (str(func), len(args))

        # -------------------------
        # 5. Qt / Worker线程：意图层防抖
        # -------------------------
        if threading.current_thread() is not threading.main_thread():

            # 🚑 [FIX] 分级背压保护：防止极端行情下的内存爆炸
            # 如果主循环来不及消费导致积压超过 2000 项，仅允许关键任务进入。
            try:
                q_size = self.tk_dispatch_queue.qsize()
                if q_size > 300:
                    # 获取识别指纹
                    task_fingerprint = str(key if key is not None else func).lower()
                    
                    # 核心业务名单（select, click, signal, order 等关键链路禁止丢弃）
                    is_critical = any(k in task_fingerprint for k in ("select", "click", "signal", "order", "close"))
                    
                    if not is_critical:
                        if time.time() - getattr(self, '_last_drop_log', 0) > 5:
                            logger.warning(f"🚨 [Soft-Backpressure] 队列积压({q_size})，丢弃低优先级任务: [{task_fingerprint[:50]}]")
                            self._last_drop_log = time.time()
                        return "queue_drop_low_priority"
            except: pass

            # 🚑 [FIX] 协作式限流 Watchdog：
            # 只有在主脉搏【静止】且超过限流步长（50ms）时，才由 Worker 尝试拉起。
            # -------------------------
            # Watchdog（基于心跳，不是 running 状态）
            # -------------------------
            now_t = time.time()
            last = getattr(self, "_last_task_finish_time", 0)

            # 超过 0.5s 没有执行任何任务 → 可能卡死
            # if now_t - last > 5:
            #     if now_t - getattr(self, "_last_dispatch_kick", 0) > 1.0:
            #         self._last_dispatch_kick = now_t
            #         try:
            #             self.after(100, self._process_dispatch_queue)
            #             logger.warning("🧯 Watchdog恢复调度")
            #         except Exception:
            #             pass
            if now_t - last > 5:
                if now_t - getattr(self, "_last_dispatch_kick", 0) > 1.0:
                    self._last_dispatch_kick = now_t
                    logger.warning("🧯 Watchdog恢复调度观察")
                    self._last_task_finish_time = time.time()
                    # try:
                    #     self._safe_schedule_dispatch(100)
                    #     logger.warning("🧯 Watchdog恢复调度")
                    # except Exception:
                    #     pass

            if debounce:
                now = time.time()
                # TTL清理（避免内存增长）
                if len(self._qt_debounce_map) > 5000:
                    self._qt_debounce_map.clear()

                last_time = self._qt_debounce_map.get(task_key)

                if last_time is not None:
                    # 100ms时间窗防抖
                    if now - last_time < 0.1:
                        return "qt_debounce_drop"

                # 写入最新时间
                self._qt_debounce_map[task_key] = now

            def safe_call():
                # ⚠️ 不再做 pop（避免竞态）
                try:
                    if bind_widget is not None:
                        try:
                            if not bind_widget.winfo_exists():
                                return
                        except Exception:
                            return
                    return func(*args)
                except Exception as e:
                    # 🛡️ [BUG FIX] 直接用模块级 logger，不依赖 self.logger
                    logger.error(f"❌ [_schedule_after_v4] Async Task Error [{task_key}]: {e}\n{traceback.format_exc()}")

            safe_call.key = task_key
            self.tk_dispatch_queue.put(safe_call)
            return "redirected"

        # -------------------------
        # 6. Tk执行层 debounce
        # -------------------------
        if debounce:
            old_job = self._after_jobs.get(task_key)
            if old_job:
                try:
                    self.after_cancel(old_job)
                except:
                    pass

        # -------------------------
        # 7. wrapper
        # -------------------------
        def wrapper():
            if getattr(self, "_is_closing", False):
                return

            if bind_widget is not None:
                try:
                    if not bind_widget.winfo_exists():
                        return
                except:
                    return

            try:
                func(*args)
            except Exception as e:
                # 🛡️ [BUG FIX] 直接用模块级 logger，不依赖 self.logger
                logger.error(f"❌ [_schedule_after] after执行异常 [{task_key}]: {e}\n{traceback.format_exc()}")
            finally:
                self._last_task_finish_time = time.time()
                self._after_jobs.pop(task_key, None)

        # -------------------------
        # 8. Tk schedule
        # -------------------------
        try:
            job_id = self.after(ms, wrapper)
            self._after_jobs[task_key] = job_id
            return job_id
        except:
            return None
            

    def _cancel_all_after_jobs(self):
        """取消所有待执行的 Tkinter after 任务（安全版）"""

        self._is_closing = True
        cancelled = 0

        # ---------- 取消 func-index 任务 ----------
        if hasattr(self, "_after_jobs"):
            for job_id in list(self._after_jobs.values()):
                try:
                    self.after_cancel(job_id)
                    cancelled += 1
                except Exception:
                    pass
            self._after_jobs.clear()

        # ---------- 取消历史记录任务 ----------
        if hasattr(self, "_after_ids"):
            for job_id in list(self._after_ids):
                try:
                    self.after_cancel(job_id)
                except Exception:
                    pass
            self._after_ids.clear()

        if cancelled:
            logger.info(f"已取消 {cancelled} 个 Tkinter after 调度任务")

    def signal_handler(self, sig, frame):
        """兼容 POSIX 系统的信号处理。Windows 下已由 native_ctrl_handler 接管，此方法仅作为降级备份"""
        if not cct.isMac(): return
        self.ask_exit()

    def _native_ctrl_handler(self, ctrl_type):
        """[Windows 专用] 底层控制台处理器，运行在独立线程，不受 messagebox 阻塞影响"""
        # [🚀 修复] 仅处理 CTRL_C_EVENT (0)，让 CTRL_BREAK_EVENT (1) 由诊断信号接管，不再弹出确认窗
        if ctrl_type == 0: 
            global _exit_ctrl_c_count, _exit_ctrl_c_time
            now = time.time()
            if now - _exit_ctrl_c_time > 3:
                _exit_ctrl_c_count = 0
            _exit_ctrl_c_count += 1
            _exit_ctrl_c_time = now

            if _exit_ctrl_c_count >= 3:
                print("\n[Native] 检测到连续 3 次 Ctrl+C，正在强制退出程序...")
                os._exit(0)
            else:
                if getattr(self, '_exit_dialog_active', False):
                    print(f"\n[Native] 正在等待确认... 再按 {3 - _exit_ctrl_c_count} 次强制暴力退出")
                else:
                    print(f"\n[Native] KeyboardInterrupt ({_exit_ctrl_c_count}/3), 正在尝试弹出确认窗...")
                    # [🚀 安全触发] 通过 after 将 GUI 请求投递回主线程执行
                    try:
                        self.after(0, self.ask_exit)
                    except:
                        pass
                return True # 表示已处理
        return False
        
    def send_command_to_visualizer(self, cmd_str):
        """
        发送指令到 Visualizer (Port: 26668)
        Format: CODE|{cmd}
        """
        IPC_HOST = '127.0.0.1'
        IPC_PORT = 26668
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((IPC_HOST, IPC_PORT))
            payload = f"CODE|{cmd_str}"
            s.send(payload.encode('utf-8'))
            s.close()
            logger.info(f"Command sent to Visualizer: {cmd_str}")
        except Exception as e:
            logger.error(f"Failed to send command to visualizer: {e}")
            messagebox.showwarning("Connection Error", "无法连接到可视化窗口，请确认它已启动。")

    def ask_exit(self):
        """弹出确认框，询问是否退出"""
        # [🚀 防抖保护] 确保同时只有一个对话框实例存在，防止 Windows 焦点死锁
        if getattr(self, '_exit_dialog_active', False):
            return
            
        self._exit_dialog_active = True
        try:
            if messagebox.askyesno("确认退出", "你确定要退出 StockApp 吗？"):
                self.on_close()
        finally:
            self._exit_dialog_active = False

    # ========== Win32 RegisterHotKey 全局快捷键 ==========
    # 使用系统级 RegisterHotKey API 替代 keyboard 库的低级钩子，
    # 彻底解决长时间运行后 WH_KEYBOARD_LL 被 Windows 自动卸载的问题。
    
    # 热键 ID 常量
    _HOTKEY_ID_BASE = 0xBF00  # 避免与其他程序冲突
    _HOTKEY_MAP = {
        # id_offset: (modifier, vk_code, description)
        0: (win32con.MOD_ALT, 0x42, "Alt+B"),  # B - 关闭所有报警
        1: (win32con.MOD_ALT, 0x45, "Alt+E"),  # E - 语音预警管理
        2: (win32con.MOD_ALT, 0x53, "Alt+S"),  # S - 策略管理
        3: (win32con.MOD_ALT, 0x4B, "Alt+K"),  # K - 每日复盘
        4: (win32con.MOD_ALT, 0x4C, "Alt+L"),  # Q - 实时信号仪表盘
        5: (win32con.MOD_ALT, 0x48, "Alt+H"),  # H - 切换Hotlist
        6: (win32con.MOD_ALT, 0x56, "Alt+V"),  # V - 信号扫描 (Scan)批次轮转
        7: (win32con.MOD_ALT, 0x4D, "Alt+M"),  # M - 竞价赛马监控
    }


    def setup_global_hotkey(self, show_toast=False, mode="GLOBAL"):
        """
        注册快捷键。
        mode: "GLOBAL" (Win32 系统级) 或 "LOCAL" (仅本窗口有效)
        """
        self._hotkey_stop_event = threading.Event()

        # 1. 彻底清理旧钩子/线程
        self._shutdown_global_hotkeys()
        
        # 2. 准备回调逻辑
        hotkey_callbacks = {
            0: lambda: self._schedule_after(0, self.close_all_alerts),
            1: lambda: self._schedule_after(0, self.open_voice_monitor_manager),
            2: lambda: self._schedule_after(0, self.open_strategy_manager),
            3: lambda: self._schedule_after(0, self.open_market_pulse),
            4: lambda: self._schedule_after(0, self.open_live_signal_viewer),
            5: lambda: self._schedule_after(0, lambda: self.send_command_to_visualizer("TOGGLE_HOTLIST")),
            6: lambda: self._schedule_after(0, self._run_live_strategy_process),
            7: lambda: self._schedule_after(0, self.open_racing_panel),
        }
        self._hotkey_callbacks = hotkey_callbacks

        if mode == "GLOBAL":
            # --- Win32 系统级全局热键模式 ---
            self._hotkey_stop_event = threading.Event()

            def _hotkey_thread_func():
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                
                registered_ids = []
                for offset, (mod, vk, desc) in self._HOTKEY_MAP.items():
                    hk_id = self._HOTKEY_ID_BASE + offset
                    if user32.RegisterHotKey(None, hk_id, mod, vk):
                        registered_ids.append(hk_id)
                        logger.info(f"✅ [Hotkey] Win32 全局热键已激活: {desc}")
                    else:
                        logger.warning(f"⚠️ [Hotkey] Win32 注册 {desc} 失败，可能已被占用")

                try:
                    msg = wintypes.MSG()
                    while not self._hotkey_stop_event.is_set():
                        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            if msg.message == 0x0312:  # WM_HOTKEY
                                hk_id = msg.wParam
                                offset = hk_id - self._HOTKEY_ID_BASE
                                cb = self._hotkey_callbacks.get(offset)
                                if cb:
                                    logger.debug(f"🔥 [Hotkey] Win32 Hotkey Triggered: ID={hk_id}")
                                    cb()
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                        else:
                            time.sleep(0.05)
                except Exception as e:
                    logger.error(f"❌ [Hotkey] Win32 线程异常: {e}")
                finally:
                    for hk_id in registered_ids:
                        user32.UnregisterHotKey(None, hk_id)
                    logger.info("[Hotkey] Win32 热键已注销，线程退出")

            self._hotkey_thread = threading.Thread(
                target=_hotkey_thread_func,
                name="GlobalHotkeyThreadWin32",
                daemon=True
            )
            self._hotkey_thread.start()
            if show_toast:
                toast_message(self, "✅ 全局快捷键已重置为系统级 (System-wide)")
        
        else:
            # --- Tkinter 本地窗口快捷键模式 (降级模式) ---
            logger.info("⚡ [Hotkey] 切换到本地窗口快捷键模式...")
            for offset, (_, _, desc) in self._HOTKEY_MAP.items():
                cb = hotkey_callbacks.get(offset)
                if not cb: continue
                
                # 将 Alt+X 转换为 Tk 合法格式 (注意：Alt 首字母必须大写，且字母推荐小写)
                # 例如: "Alt+V" -> "<Alt-v>"
                key_part = desc.split('+')[-1].lower()
                tk_key = f"<Alt-{key_part}>"
                try:
                    self.bind_all(tk_key, lambda e, func=cb: func())
                    logger.debug(f"✅ [Hotkey] 本地快捷键已绑定: {tk_key}")
                except Exception as ex:
                    logger.error(f"❌ [Hotkey] 本地绑定 {tk_key} 失败: {ex}")
            
            if show_toast:
                toast_message(self, "📴 全局快捷键已失效，仅在窗口内生效 (App-wide)")

        if show_toast:
            hotkey_list = "/".join([v[2] for v in self._HOTKEY_MAP.values()])
            self.status_var.set(f"✅ 快捷键已重置: {hotkey_list}")


    def _shutdown_global_hotkeys(self):
        """
        安全关闭热键线程，并在 join 后统一执行 keyboard.unhook_all()。

        关键时序（保证无竞态）：
        1. set stop_event → 旧线程从 wait() 中返回并退出（不调用 unhook）
        2. join 等旧线程彻底死亡
        3. 在本线程（调用方）执行 keyboard.unhook_all()，状态确定干净
        4. 调用方随后可安全启动新线程并 add_hotkey
        """
        if hasattr(self, '_hotkey_stop_event') and self._hotkey_stop_event:
            self._hotkey_stop_event.set()

        # 等待旧线程彻底退出（旧线程不调用 unhook，join 后状态确定）
        if hasattr(self, '_hotkey_thread') and self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_thread.join(timeout=3.0)

        # join 完成后，在调用方统一清理 keyboard 钩子（串行，无竞态）
        try:
            import keyboard
            keyboard.unhook_all()
            logger.debug("[Hotkey] keyboard.unhook_all() 完成（调用方线程）")
        except ImportError:
            pass
        except Exception as e:
            logger.debug("[Hotkey] keyboard.unhook_all 失败 (可忽略): %s", e)

        self._hotkey_thread_id = None
        self._hotkey_stop_event = None
    # === [REMOVED] 已切换至原生 RegisterHotKey 模式，不再需要单独的备用实现 ===
    # =========================================================================


    def on_resize(self, event):
        if event.widget != self:
            return
        # 标记 resize 进行中
        self._is_resizing = True
        if hasattr(self, "_resize_after_id") and self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        # 只有“停下来”才触发真正刷新
        self._resize_after_id = self._schedule_after(
            300,
            self._on_resize_finished
        )

    def _start_feedback_listener(self):
        """
        监听来自可视化器的控制指令（如 REQ_FULL_SYNC）
        使用独立控制管道，短连接，强健容错
        """
        # 🛡️ [FIX] 线程存活校验：防止产生大量冗余监听线程导致 GIL 崩溃
        if hasattr(self, "_feedback_listener_thread") and self._feedback_listener_thread and self._feedback_listener_thread.is_alive():
            # logger.debug("[Pipe] Feedback listener already running. Skipping redundant startup.")
            return

        import win32pipe, win32file, pywintypes, winerror
        import json, threading, time
        from data_utils import PIPE_NAME_TK

        def listener():
            logger.info(f"[Pipe] Feedback listener ready on {PIPE_NAME_TK}")

            # ⚠️ 退出闸门（如果外部没定义，就兜底一个）
            app_exiting = getattr(self, "_app_exiting", None)

            while True:
                # ====== 全局退出判断 ======
                if app_exiting and app_exiting.is_set():
                    break

                pipe = None
                try:
                    pipe = win32pipe.CreateNamedPipe(
                        PIPE_NAME_TK,
                        win32pipe.PIPE_ACCESS_DUPLEX,
                        win32pipe.PIPE_TYPE_MESSAGE |
                        win32pipe.PIPE_READMODE_MESSAGE |
                        win32pipe.PIPE_WAIT,
                        win32pipe.PIPE_UNLIMITED_INSTANCES,
                        65536, 65536,
                        0,
                        None
                    )

                    try:
                        win32pipe.ConnectNamedPipe(pipe, None)
                    except pywintypes.error as e:
                        # ⛔ 正常退出场景（应用关闭 / 对端消失）
                        if app_exiting and app_exiting.is_set():
                            break
                        raise

                    # ====== 已建立连接，开始读取 ======
                    while True:
                        if app_exiting and app_exiting.is_set():
                            break

                        try:
                            res, data = win32file.ReadFile(pipe, 65536)
                        except pywintypes.error as e:
                            # Windows 管道正常断开（不要当异常刷日志）
                            if e.winerror in (winerror.ERROR_BROKEN_PIPE,
                                              winerror.ERROR_NO_DATA,
                                              winerror.ERROR_INVALID_HANDLE):
                                break
                            raise

                        if res != 0 or not data:
                            break

                        msg = data.decode("utf-8", errors="ignore")
                        logger.debug(f"[Pipe] recv: {msg}")

                        try:
                            obj = json.loads(msg)
                        except Exception:
                            obj = None

                        # ================== 原有逻辑：完全保留 ==================

                        if obj and obj.get("cmd") == "REQ_FULL_SYNC":
                            logger.info('[Pipe] Feedback listener cmd REQ_FULL_SYNC')
                            self._force_full_sync_pending = True
                            self._df_first_send_done = False

                        elif obj and obj.get("cmd") == "VIZ_EXIT":
                            logger.debug('[Pipe] Visualizer exited. Cleaning up qt_process state.')
                            self.qt_process = None
                            self.viz_command_queue = None
                            if hasattr(self, 'viz_stop_flag'):
                                self.viz_stop_flag.value = True  # Reset for next launch
                        elif obj and obj.get("cmd") == "ADD_MONITOR":
                            code = obj.get("code")
                            if code:
                                logger.info(f'[Pipe] Feedback listener cmd ADD_MONITOR: {code}')
                                try:
                                    current_list = list(self.global_dict.get('extra_monitor_codes', []))
                                    if code not in current_list:
                                        current_list.append(code)
                                        self.global_dict['extra_monitor_codes'] = current_list
                                        logger.info(f"✅ Added {code} to extra_monitor_codes")
                                        # 同时也触发一次强制全量同步
                                        self._force_full_sync_pending = True
                                except Exception as e:
                                    logger.error(f"Failed to update extra_monitor_codes: {e}")
                        
                        elif obj and obj.get("cmd") == "SET_VOICE_STATE":
                            enabled = obj.get("enabled", True)
                            logger.info(f"[Pipe] Recv SET_VOICE_STATE: {enabled} from {obj.get('source')}")
                            # ⭐ 利用 tk_dispatch_queue 进行跨线程安全的 UI 更新
                            def sync_voice_ui():
                                if hasattr(self, 'voice_var'):
                                    self.voice_var.set(enabled)
                                    # 注意：set() 会触发 trace，但 Checkbutton 的 command 不会自动触发
                                    # 这里显式调用 on_voice_toggle 确保业务逻辑执行
                                    self.on_voice_toggle()
                                    logger.info(f"✅ Main App voice state synced to: {enabled}")
                            
                            self.tk_dispatch_queue.put(sync_voice_ui)

                        elif obj and obj.get("cmd") == "DNA_AUDIT":
                            codes_dict = obj.get("codes", {})
                            end_date = obj.get("end_date")
                            if codes_dict:
                                logger.info(f"[Pipe] Recv DNA_AUDIT for {len(codes_dict)} stocks. EndDate: {end_date}")
                                self.tk_dispatch_queue.put(lambda c=codes_dict, ed=end_date: self._run_dna_audit_batch(c, end_date=ed))

                        elif obj and obj.get("cmd") == "EXEC_MACRO":
                            macro = obj.get("macro")
                            logger.info(f"[Pipe] Recv EXEC_MACRO: {macro}")
                            if macro == "RUN_STRATEGY":
                                self.tk_dispatch_queue.put(self._run_live_strategy_process)
                            elif macro == "SHOW_MARKET_PULSE":
                                self.tk_dispatch_queue.put(self.open_market_pulse)
                            elif macro == "CLOSE_ALERTS":
                                self.tk_dispatch_queue.put(self.close_all_alerts)
                            elif macro == "SHOW_SIGNAL_VIEWER":
                                self.tk_dispatch_queue.put(self.open_live_signal_viewer)
                            elif macro == "SHOW_STRATEGY_MANAGER":
                                self.tk_dispatch_queue.put(self.open_strategy_manager)
                            elif macro == "SHOW_VOICE_MANAGER":
                                self.tk_dispatch_queue.put(self.open_voice_monitor_manager)

                except pywintypes.error as e:
                    # 正常退出错误码 → 静默退出
                    if app_exiting and app_exiting.is_set():
                        break
                    if e.winerror in (winerror.ERROR_BROKEN_PIPE,
                                      winerror.ERROR_NO_DATA,
                                      winerror.ERROR_INVALID_HANDLE):
                        break
                    logger.debug(f"[Pipe] listener error: {e}")
                    time.sleep(1)

                except Exception as e:
                    if app_exiting and app_exiting.is_set():
                        break
                    logger.debug(f"[Pipe] listener error: {e}")
                    time.sleep(1)

                finally:
                    if pipe:
                        try:
                            win32pipe.DisconnectNamedPipe(pipe)
                        except Exception:
                            pass
                        try:
                            win32file.CloseHandle(pipe)
                        except Exception:
                            pass

            logger.info("[Pipe] Feedback listener exited cleanly")

        # ====== 确保主同步线程只启动一次 ======
        if not hasattr(self, "_df_sync_thread") or not self._df_sync_thread.is_alive():
            self._df_sync_running = True
            self._df_sync_thread = threading.Thread(
                target=self.send_df,
                name="DFSyncThread",
                daemon=True
            )
            self._df_sync_thread.start()

        self._feedback_listener_thread = threading.Thread(
            target=listener,
            name="PipeCtrlListener",
            daemon=True
        )
        self._feedback_listener_thread.start()


    def _on_resize_finished(self):
        self._is_resizing = False
        logger.info("[resize] finished, apply")
        # self.refresh_tree()
        # self._refresh_visible_rows()

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

        self._schedule_after(60*1000, self.schedule_15_30_job)

    def run_15_30_task(self):
        """盘后自动任务：包含离线行情存档与所有子面板的持久化"""
        if getattr(self, "_task_running", False):
            return

        # ✅ 每日自动保存 SectorBiddingPanel 历史数据 (高精度密度版)
        # 1. 预先准备数据快照 (提升作用域，确保全局可用)
        try:
            import queue
            wait_q = queue.Queue()
            df_feed = None
            
            if hasattr(self, 'df_all') and not self.df_all.empty:
                df_feed = self.df_all.copy()
                if 'code' not in df_feed.columns and df_feed.index.name == 'code':
                    df_feed = df_feed.reset_index()
            
            if df_feed is None:
                logger.warning("🕒 [15:30 Task] df_all empty at 15:30, aborting save.")
            else:
                def _init_panel_task():
                    """在 UI 线程仅执行轻量化实例化与异步喂数"""
                    try:
                        from sector_bidding_panel import SectorBiddingPanel
                        if not hasattr(self, 'sector_bidding_panel') or self.sector_bidding_panel is None:
                            self.sector_bidding_panel = SectorBiddingPanel(main_window=self)
                            logger.info("📡 [15:30 Task] Standard SectorBiddingPanel instance created on UI thread.")
                        
                        # ⭐ 异步喂数：任务进入面板自带的 _worker 线程并行处理，绝不阻塞 UI
                        self.sector_bidding_panel.on_realtime_data_arrived(df_feed.copy(), force_update=False)  # [THREAD-SAFETY] copy() 防止子线程悬空指针
                    except Exception as ex:
                        logger.error(f"Panel dispatch-init error: {ex}")
                    finally:
                        wait_q.put(True)

                if hasattr(self, "tk_dispatch_queue"):
                    self.tk_dispatch_queue.put(_init_panel_task)
                    try:
                        # a. 等待 UI 实例化任务本身下发完成
                        wait_q.get(timeout=10) 
                        
                        # b. ⭐ [SYNC-DENSITY-CHECK] 核心策略：直到全量指标提取完成且队列清空
                        detector = getattr(self.sector_bidding_panel, 'detector', None)
                        worker_obj = getattr(self.sector_bidding_panel, '_worker', None)
                        if detector and worker_obj:
                            logger.info("📊 [15:30 Task] Monitoring indicator density (waiting for scores)...")
                            sync_start = time.time()
                            target_count = len(df_feed)
                            
                            # 持续检测计算深度：只要得分池还没填满（<90%）或者队列还有数，就继续等
                            # 即使是新面板启动，也会因为这个循环而等待 K 线抓取和评分计算完成
                            while (time.time() - sync_start < 60.0):
                                q_count = worker_obj.df_queue.qsize() if hasattr(worker_obj.df_queue, 'qsize') else 0
                                score_count = len(detector._tick_series)
                                
                                # 成功判定：计算队列为空且已抓取超过 90% 的股票指标
                                if q_count == 0 and score_count >= (target_count * 0.9):
                                    break
                                time.sleep(1.5)
                            
                            # 额外缓冲 3s，确保分值聚合到板块
                            time.sleep(3.0)
                            logger.info(f"⏳ [15:30 Task] EOD calculation sync complete. scores:{len(detector._tick_series)} in {time.time()-sync_start:.1f}s.")
                        else:
                            time.sleep(5.0) 
                    except queue.Empty:
                        logger.warning("🕒 [15:30 Task] SectorBiddingPanel dispatch timeout")
                else:
                    from sector_bidding_panel import SectorBiddingPanel
                    self.sector_bidding_panel = SectorBiddingPanel(main_window=self)

                # --- 此时得分已由工作线程处理完毕，执行高采样率存档 ---
                if hasattr(self, 'sector_bidding_panel') and self.sector_bidding_panel:
                    try:
                        if cct.get_trade_date_status():
                            detector = getattr(self.sector_bidding_panel, 'detector', None)
                            if detector:
                                # 同步极速聚合板块分
                                detector.update_scores()
                                detector.save_persistent_data(force=True)
                                logger.info("✅ [15:30 Task] SectorBiddingPanel 归档圆满完成 (数据已熟透)。")
                    except Exception as e:
                        logger.error(f"❌ [15:30 Task] SectorBiddingPanel 自动保存失败: {e}")

        except Exception as global_e:
            logger.error(f"❌ [15:30 Task] Global Exception in run_15_30_task: {global_e}")

        # --- 其他模块自动保存：LiveStrategy ---
        if hasattr(self, "live_strategy") and self.live_strategy is not None:
            try:
                now_time = cct.get_now_time_int()
                if now_time >= 1500:
                    self.live_strategy._save_monitors()
                    logger.info(f"✅ [15:30 Task] LiveStrategy monitors saved OK at {now_time}")
            except Exception as e:
                logger.warning(f"❌ [15:30 Task] LiveStrategy saving failed: {e}")

        today = cct.get_today('')
        global write_all_day_date
        if write_all_day_date == today:
            logger.info(f'Write_market_all_day_mp 已经完成')
            return
        self._task_running = True
        try:
            if  cct.get_trade_date_status():
                logger.info(f'start Write_market_all_day_mp OK')
                tdd.Write_market_all_day_mp('all')
                logger.info(f'run Write_market_all_day_mp OK')
                CFG = cct.GlobalConfig(conf_ini)
                # cct.GlobalConfig(conf_ini, write_all_day_date=20251205)
                CFG.set_and_save("general", "write_all_day_date", today)
                write_all_day_date = today
            else:
                logger.info(f"today: {today} is trade_date :{cct.get_trade_date_status()} not to Write_market_all_day_mp")

        finally:
            self._task_running = False

    
    def _cleanup_signals_with_feedback(self, days: int):
        """执行信号清理并显示反馈"""
        try:
            from trading_hub import get_trading_hub
            from tkinter import messagebox, scrolledtext
            import tkinter as tk
            
            # 确认对话框
            if not messagebox.askyesno(
                "确认清理", 
                f"确定要清理 {days} 天前的过期或破位信号吗?\n\n"
                f"规则: \n"
                f"1. 超过 {days} 天未入场的跟单信号\n"
                f"2. [NEW] 3天内无中阳启动突破 (涨幅>=4% 且 放量>=1.3 且 突破high4)\n"
                f"3. 当前价格较检测价跌超 7% (不及预期/破位)\n"
                f"4. [NEW] 队列扩容压缩 (全量队列严格限额 100 只)\n"
            ):
                return
            
            # 准备实时价格和行情数据
            price_map = {}
            if hasattr(self, 'df_all') and not self.df_all.empty:
                # [NEW] 扩展为包含完整行情数据的字典，支持"3天内无中阳突破"清理
                for code, row in self.df_all.iterrows():
                    try:
                        price_map[code] = {
                            'price': float(row.get('trade', 0)),
                            'percent': float(row.get('percent', 0)),
                            'volume': float(row.get('volume', 0)),
                            'high4': float(row.get('high4', 0))
                        }
                    except (ValueError, TypeError):
                        # 降级为简单价格
                        price_map[code] = float(row.get('trade', 0))

            # 执行清理
            hub = get_trading_hub()
            results = hub.cleanup_stale_signals(max_days=days, current_prices=price_map)
            
            # 统计总数 (处理结果中既有列表也有整数的情况，如 PURGED_WATCHLIST)
            total_cleaned = sum(v if isinstance(v, int) else len(v) for v in results.values())
            
            if total_cleaned > 0:
                # 构建详细报告
                report = []
                if results.get("CANCEL_SIGNAL"):
                    report.append("【跟单队列 - 不及预期/过期已取消】")
                    report.extend([f" • {item}" for item in results["CANCEL_SIGNAL"]])
                    report.append("")
                
                if results.get("STALE_SIGNAL"):
                    report.append("【长期未动已标记为 STALE】")
                    report.extend([f" • {item}" for item in results["STALE_SIGNAL"]])
                    report.append("")

                if results.get("PURGED_WATCHLIST", 0) > 0:
                    report.append(f"【观察池 - 物理清理】已删除 {results['PURGED_WATCHLIST']} 条过期或冗余记录")

                # 显示详细日志弹窗
                log_win = tk.Toplevel(self)
                log_win.title(f"清理完成 - 共处理 {total_cleaned} 项")
                log_win.geometry("520x450")
                
                txt = scrolledtext.ScrolledText(log_win, wrap=tk.WORD, font=("微软雅黑", 9))
                txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                txt.insert(tk.END, "\n".join(report))
                txt.configure(state='disabled')
                
                # 确定按钮
                btn = tk.Button(log_win, text="确定", command=log_win.destroy, width=12)
                btn.pack(pady=10)
                
                logger.info(f"[UI] 用户手动清理了 {total_cleaned} 个信号/热点 (>{days}天 或 破位)")
            else:
                messagebox.showinfo(
                    "清理完成", 
                    f"没有找到需要清理的信号\n\n"
                    f"所有活动信号都在 {days} 天以内且表现优于预期。"
                )
                logger.info(f"[UI] 用户手动清理: 无需清理的信号 (>{days}天)")
                
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("清理失败", f"清理过程中出现错误:\n{str(e)}")
            logger.error(f"[UI] 信号清理失败: {e}\n{traceback.format_exc()}")
    
    def _force_cleanup_stagnant_signals(self):
        """强制清理全量队列：清理已存在 >=3天 且仍未启动的信号"""
        try:
            from trading_hub import get_trading_hub
            from tkinter import messagebox, scrolledtext
            import tkinter as tk
            
            # 确认对话框
            if not messagebox.askyesno(
                "全量队列强制清理", 
                "确定要对【全量队列】进行强制清理吗?\n\n"
                "清理规则(所有符合以下条件的信号将被取消):\n"
                "• 信号已入队存在 >= 3天\n"
                "• 且未出现中阳启动突破 (或已掉出活跃榜单)\n"
                "• [NEW] 强制压缩：清理后如仍超 100 只，将剔除低优先级记录\n\n"
            ):
                return
            
            # 准备实时价格和行情数据
            price_map = {}
            if hasattr(self, 'df_all') and not self.df_all.empty:
                for code, row in self.df_all.iterrows():
                    try:
                        price_map[code] = {
                            'price': float(row.get('trade', 0)),
                            'percent': float(row.get('percent', 0)),
                            'volume': float(row.get('volume', 0)),
                            'high4': float(row.get('high4', 0))
                        }
                    except (ValueError, TypeError):
                        price_map[code] = float(row.get('trade', 0))

            # 执行清理（max_days=999 禁用常规时间清理，check_breakout=True 开启全量突破检测）
            hub = get_trading_hub()
            results = hub.cleanup_stale_signals(max_days=999, current_prices=price_map, check_breakout=True)
            
            # 统计总数
            total_cleaned = sum(v if isinstance(v, int) else len(v) for v in results.values())
            
            if total_cleaned > 0:
                report = []
                if results.get("CANCEL_SIGNAL"):
                    report.append("【跟单队列 - 强制清理已取消】")
                    report.extend([f" • {item}" for item in results["CANCEL_SIGNAL"]])
                    report.append("")
                
                if results.get("PURGED_WATCHLIST", 0) > 0:
                    report.append(f"【观察池 - 物理清理】已删除 {results['PURGED_WATCHLIST']} 条过期或冗余记录")

                log_win = tk.Toplevel(self)
                log_win.title(f"强制清理完成 - 共处理 {total_cleaned} 项")
                log_win.geometry("520x450")
                
                txt = scrolledtext.ScrolledText(log_win, wrap=tk.WORD, font=("微软雅黑", 9))
                txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
                txt.insert(tk.END, "\n".join(report))
                txt.configure(state='disabled')
                
                btn = tk.Button(log_win, text="确定", command=log_win.destroy, width=12)
                btn.pack(pady=10)
                
                logger.info(f"[UI] 用户执行了全量队列强制清理: 处理 {total_cleaned} 项")
            else:
                messagebox.showinfo("清理完成", "全量扫描完成，未发现符合清理条件的僵尸信号。")
                logger.info(f"[UI] 用户执行全量队列强制清理: 无需清理")
                
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("清理失败", f"强制清理过程中出现错误:\n{str(e)}")
            logger.error(f"[UI] 全量队列强制清理失败: {e}\n{traceback.format_exc()}")

    def wait_all_threads(self, timeout=0.5):
        import threading
        main = threading.current_thread()
        for t in threading.enumerate():
            # ❗ 跳过当前主线程以及所有守护线程 (daemon=True)
            # 守护线程会在 os._exit(0) 时被系统自动回收，无需显式等待
            if t is main or t.daemon:
                continue
            # ❗ 跳过 DummyThread
            if isinstance(t, threading._DummyThread):
                logger.warning(f"[SKIP DummyThread] {t.name}")
                continue
            logger.info(f"[WAIT] Non-daemon thread: {t.name}")
            t.join(timeout)
            if t.is_alive():
                logger.error(f"[STILL ALIVE] {t.name}")

    # --- DPI and Window management moved to Mixins ---
    @with_log_level(LoggerFactory.INFO)
    def on_close(self):
        # 🛡️ [NEW] 退出保险：25秒后如果还没退出，则强行终止进程，防止 GUI 挂起导致僵尸进程
        def failsafe_exit():
            print("\n🚨 [Failsafe] Shutdown timeout reached (25s). Forcing physical exit...")
            import os
            os._exit(0)

        exit_timer = threading.Timer(25.0, failsafe_exit)
        exit_timer.daemon = True
        exit_timer.start()

        try:
            # =========================================================
            # ⭐ STEP 1: 停止动力源 / 设置全局退出标志
            # =========================================================
            try:
                self.stop_refresh()  # 设置 refresh_flag = False，切断主数据刷新循环
            except Exception:
                pass

            self._is_closing = True

            if hasattr(self, '_app_exiting'):
                self._app_exiting.set()  # 通知所有监听线程立即停止

            logger.info("🛑 [on_close] Phase 1: Shutdown initiated (Stop Refresh & Flags)")

            # =========================================================
            # ⭐ STEP 2: 停止 Worker / Thread / Executor / Publisher
            # =========================================================

            # ---------------------------------------------------------
            # 2.1 停止后台数据获取进程 (proc)
            # ---------------------------------------------------------
            if hasattr(self, "proc") and self.proc is not None and self.proc.is_alive():
                print("正在停止后台数据获取进程 (proc)...")
                if hasattr(self, 'refresh_flag'):
                    self.refresh_flag.value = False
                if hasattr(self, 'global_values'):
                    try: self.global_values.setkey('state', 'EXIT')
                    except: pass
                self.proc.join(timeout=3)
                if self.proc.is_alive():
                    self.proc.terminate()
                    self.proc.join(timeout=1)
                if self.proc.is_alive():
                    self.proc.kill()
            self.proc = None

            # ---------------------------------------------------------
            # 2.2 停止线程池
            # ⚠ 顺序极其重要：
            #    executor(调度层) -> pump_executor(中转层) -> compute_executor(计算层)
            # 防止主调度线程向已关闭计算池提交任务导致 RuntimeError
            # ---------------------------------------------------------
            for pool_name in ['executor', 'pump_executor', 'compute_executor']:
                pool = getattr(self, pool_name, None)
                if pool:
                    try:
                        logger.info(f"正在关闭线程池 {pool_name}...")
                        pool.shutdown(
                            wait=False,
                            cancel_futures=True  # 取消尚未执行任务，防止退出尾部继续跑
                        )
                    except Exception as e:
                        logger.debug(f"{pool_name} shutdown error: {e}")

            # ---------------------------------------------------------
            # 2.3 停止策略引擎 / 发送器 / 探测器 / 报警系统
            # ---------------------------------------------------------
            strategy = getattr(self, "live_strategy", None)
            if strategy is not None:
                try:
                    now_time = cct.get_now_time_int()

                    # 收盘后保存 monitor 状态
                    if now_time > 1500:
                        strategy._save_monitors()
                        logger.info("[on_close] strategy._save_monitors SAVE OK")

                    logger.info("正在停止 StockLiveStrategy...")
                    strategy.stop()

                except Exception as e:
                    logger.error(f"Error stopping live_strategy: {e}")

            try:
                from alert_manager import get_alert_manager
                print("正在停止语音报警引擎...")
                get_alert_manager().stop()
            except Exception:
                pass

            if hasattr(self, 'sender') and self.sender:
                try:
                    logger.info("正在停止股票发送器 (StockSender)...")
                    self.sender.close()
                except Exception:
                    pass

            if getattr(self, 'racing_detector', None) is not None:
                try:
                    logger.info("正在停止赛马探测器 (RacingDetector)...")
                    self.racing_detector.stop()
                except Exception:
                    pass

            # ---------------------------------------------------------
            # 2.4 停止系统辅助工具
            # ---------------------------------------------------------
            try:
                self._shutdown_global_hotkeys()
            except Exception:
                pass

            try:
                self._cancel_all_after_jobs()
            except Exception:
                pass

            try:
                self.close_all_alerts()
            except Exception:
                pass

            # ---------------------------------------------------------
            # 2.5 停止 df_all 同步线程
            # ---------------------------------------------------------
            if hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
                print("正在停止 df_all 同步线程...")
                self._df_sync_running = False
                self._df_sync_thread.join(timeout=0.2)
                self._df_sync_thread = None

            # =========================================================
            # ⭐ STEP 2.6: 数据持久化（必须在 Manager 关闭前）
            # =========================================================

            try:
                self.save_ui_states()
            except Exception:
                pass

            try:
                self.save_window_position(self, "main_window")
            except Exception:
                pass

            try:
                if hasattr(self, "_concept_win") and self._concept_win and self._concept_win.winfo_exists():
                    self.save_window_position(self._concept_win, "detail_window")
            except Exception:
                pass

            try:
                if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                    self.save_window_position(self.kline_monitor, "KLineMonitor")
                    self.kline_monitor.on_kline_monitor_close()
            except Exception:
                pass

            try:
                if hasattr(self, "_pg_top10_window_simple"):
                    self.save_all_monitor_windows()
            except Exception:
                pass

            try:
                if hasattr(self, 'query_manager'):
                    self.query_manager.save_search_history()
            except Exception:
                pass

            logger.info("正在执行物理存档...")

            try:

                t_logger = TradingLogger()
                archive_file_tools(
                    t_logger.db_path,
                    "trading_signals",
                    ARCHIVE_DIR,
                    logger
                )

                from trading_hub import get_trading_hub
                hub = get_trading_hub()

                archive_file_tools(
                    hub.signal_db,
                    "signal_strategy",
                    ARCHIVE_DIR,
                    logger
                )

                if hasattr(self, 'handbook'):
                    archive_file_tools(
                        self.handbook.data_file,
                        "stock_handbook",
                        ARCHIVE_DIR,
                        logger
                    )

                archive_file_tools(
                    WINDOW_CONFIG_FILE,
                    "window_config",
                    ARCHIVE_DIR,
                    logger
                )

                archive_file_tools(
                    VOICE_ALERT_CONFIG_FILE,
                    "voice_alert_config",
                    ARCHIVE_DIR,
                    logger
                )

                archive_search_history_list(
                    monitor_list_file=MONITOR_LIST_FILE,
                    search_history_file=SEARCH_HISTORY_FILE,
                    archive_dir=ARCHIVE_DIR,
                    logger=logger
                )

            except Exception as e:
                logger.warning(f"数据存档过程异常: {e}")

            # =========================================================
            # ⭐ STEP 3: 停止所有子进程
            # =========================================================

            # ---------------------------------------------------------
            # 3.1 停止 Qt 可视化子进程
            # ---------------------------------------------------------
            if hasattr(self, 'viz_lifecycle_flag'):
                self.viz_lifecycle_flag.value = False

            qtz_proc = getattr(self, 'qt_process', None)
            if qtz_proc and qtz_proc.is_alive():
                print("正在停止 Qt 可视化子进程 (qt_process)...")
                qtz_proc.join(timeout=0.5)

                if qtz_proc.is_alive():
                    qtz_proc.terminate()

            self.qt_process = None

            # ---------------------------------------------------------
            # 3.2 停止赛马回测进程
            # ---------------------------------------------------------
            if hasattr(self, 'backtest_process') and self.backtest_process and self.backtest_process.is_alive():
                logger.info("正在停止赛马回测进程 (backtest_process)...")

                if hasattr(self, '_backtest_quit_event'):
                    self._backtest_quit_event.set()
                    self.backtest_process.join(timeout=8)

                if self.backtest_process.is_alive():
                    self.backtest_process.terminate()

            self.backtest_process = None

            # ---------------------------------------------------------
            # 3.3 停止 DNA 审计 / 联动系统
            # ---------------------------------------------------------
            try:
                import bidding_racing_panel

                dna_proc = getattr(
                    bidding_racing_panel,
                    '_DNA_AUDIT_PROCESS',
                    None
                )

                if dna_proc and dna_proc.is_alive():
                    logger.info("正在停止 DNA 审计后台进程...")
                    dna_proc.terminate()

                if hasattr(self, 'link_manager'):
                    print("正在停止系统联动进程 (Linkage)...")
                    self.link_manager.stop()

            except Exception:
                pass

            # =========================================================
            # ⭐ STEP 4: 停止 Manager / Queue / Pipe
            # =========================================================

            # ---------------------------------------------------------
            # 4.1 保存 K 线缓存（依赖 Manager）
            # ---------------------------------------------------------
            if hasattr(self, "realtime_service") and self.realtime_service:
                try:
                    logger.info("正在执行 MinuteKlineCache 退出保存...")
                    self.realtime_service.stop()
                    self.realtime_service.save_cache(force=True)
                except Exception:
                    pass

            # ---------------------------------------------------------
            # 4.2 清理 Pipe / Queue / SyncManager
            # ---------------------------------------------------------
            logger.info("正在清理资源管道与 SyncManager...")

            if hasattr(self, 'viz_conn') and self.viz_conn:
                try:
                    self.viz_conn[0].close()
                    self.viz_conn[1].close()
                except Exception:
                    pass

            self.realtime_service = None
            self.global_dict = None
            self.manager_dict = None

            # ---------------------------------------------------------
            # 4.3 关闭 SyncManager
            # ---------------------------------------------------------
            if hasattr(self, '_sync_manager') and self._sync_manager:
                try:
                    logger.info("正在关闭 SyncManager...")
                    self._sync_manager.shutdown()
                except Exception as e:
                    logger.debug(f"SyncManager shutdown error: {e}")
                self._sync_manager = None

            self.queue = None

            # =========================================================
            # ⭐ STEP 5: 关闭所有 Qt UI 资源
            # =========================================================
            try:
                from PyQt6 import QtWidgets

                qt_app = QtWidgets.QApplication.instance()

                if qt_app:
                    logger.info("Phase 5: Cleaning up Qt application windows...")

                    # 关闭核心业务窗口
                    for win_attr in [
                        '_signal_dashboard_win',
                        '_racing_panel_win',
                        'sector_bidding_panel'
                    ]:
                        win = getattr(self, win_attr, None)

                        if win:
                            try:
                                if hasattr(win, '_allow_real_close'):
                                    win._allow_real_close = True

                                win.close()

                            except Exception:
                                pass

                        setattr(self, win_attr, None)

                    # 关闭 PyQt 监控窗口
                    if hasattr(self, "_pg_windows"):
                        for key, win_info in list(self._pg_windows.items()):
                            win = win_info.get("win")

                            if win:
                                try:
                                    win.close()
                                except Exception:
                                    pass

                        self._pg_windows.clear()

                    # 关闭所有顶级 QWidget
                    for widget in qt_app.topLevelWidgets():
                        try:
                            widget.close()
                            widget.deleteLater()
                        except Exception:
                            pass

                    qt_app.closeAllWindows()

            except Exception as e:
                logger.debug(f"Qt UI cleanup error: {e}")

            # =========================================================
            # ⭐ STEP 6: 等待残余线程退出 / 销毁 Tk Root
            # =========================================================
            print("正在销毁主窗口...")

            try:
                self.wait_all_threads(timeout=2.0)
            except Exception:
                pass

            try:
                self.destroy()
            except Exception:
                pass
            
            # ⭐ 关键：成功进入“可控退出路径”，取消 failsafe
            exit_timer.cancel()
            # =========================================================
            # ⭐ STEP 7: 最终清理子进程并物理切断
            # =========================================================
            print("正在最终清理遗留进程...")

            try:
                import psutil
                import os
                import time

                current_process = psutil.Process(os.getpid())
                children = current_process.children(recursive=True)

                if children:
                    print(f"发现遗留子进程，正在强制释放: {[c.pid for c in children]}")

                    for child in children:
                        try:
                            child.kill()
                        except Exception:
                            pass

                    psutil.wait_procs(children, timeout=0.8)
                    time.sleep(0.3)

                try:
                    from JohnsonUtil.LoggerFactory import stopLogger
                    print("程序运行结束，Bye.")
                    stopLogger()
                except Exception:
                    pass

                print("清理完成，正在物理切断进程...")

            finally:
                # ⚠ 永远不要 cancel failsafe
                # 因为如果 destroy()/stopLogger()/psutil 某步卡死
                # 仍需依赖 failsafe 保底物理退出
                import os
                os._exit(0)

        except Exception as e:
            import traceback
            print(f"退出过程发生严重异常: {e}\n{traceback.format_exc()}")

            try:
                self.destroy()
            except Exception:
                pass

            import os
            os._exit(0)


    # 防抖 resize（避免重复刷新）
    # ---------------------------
    def _on_open_column_manager(self):
        if self._open_column_manager_job:
            self.after_cancel(self._open_column_manager_job)
        self._open_column_manager_job = self._schedule_after(1000, self.open_column_manager)

    def open_column_manager(self):
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config(config_file=CONFIG_FILE,default_cols=DEFAULT_DISPLAY_COLS)
                # 创建新窗口
                self.global_dict['keep_all_columns'] = True  # 开启"发现模式": 允许后台获取所有列供用户选择
                self.ColumnSetManager = ColumnSetManager(
                    self,
                    self.df_all.columns,
                    self.ColManagerconfig,
                    self.update_treeview_cols,  # 回调更新函数
                    default_cols=self.current_cols,  # 默认列
                    logger=logger,  # logger
                        )
                # 关闭时清理引用
                self.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.on_close_column_manager)
            else:
                self._schedule_after(1000,self._on_open_column_manager)

    def open_column_manager_init(self):
        def _on_open_column_manager_init():
            if self._open_column_manager_job:
                self.after_cancel(self._open_column_manager_job)
            self._open_column_manager_job = self._schedule_after(1000, self.open_column_manager_init)
        
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config(config_file=CONFIG_FILE,default_cols=DEFAULT_DISPLAY_COLS)
                # 创建新窗口
                if hasattr(self, 'global_dict') and self.global_dict is not None:
                    self.global_dict['keep_all_columns'] = True
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
                self._schedule_after(1000,_on_open_column_manager_init)

    def on_close_column_manager(self):
        if self.ColumnSetManager is not None:
            self.ColumnSetManager.destroy()
            self.ColumnSetManager = None
            self._open_column_manager_job = None
            if hasattr(self, 'global_dict') and self.global_dict is not None:
                 self.global_dict['keep_all_columns'] = True  # 关闭发现模式
            self.update_required_columns() # 恢复按需裁剪

    def update_required_columns(self, refresh_ui=False) -> None:
        """同步当前 UI 和策略所需的列到后台进程"""
        # mandatory_cols动态加载列不要改df_all基础数据col,导致其他出现col确实, update_required_columns 只是用来同步可视化数据,不要改基础数据
        pass
        # try:
        #     if not hasattr(self, 'global_dict') or self.global_dict is None:
        #         return
            
        #     # 这里的 self.current_cols 存储了当前 UI 真正显示的列
        #     current_ui_cols = set(getattr(self, 'current_cols', []))
            
        #     # 使用更严谨的获取方式
        #     mandatory = getattr(self, 'mandatory_cols', set())
        #     required = set(mandatory).union(current_ui_cols)
            
        #     # 更新到 global_dict 供后台进程读取
        #     self.global_dict['required_cols'] = list(required)
        #     logger.debug(f"Dynamic Trimming: Subscribed to {len(required)} columns.")
        # except Exception as e:
        #     logger.error(f"Failed to update required columns: {e}")

    # def tree_scroll_to_code(self, code):
    #     """外部调用：定位特定代码"""
    #     if hasattr(self, 'search_var1'):
    #         self.search_var1.set(code)
    #         self.apply_search()

    def get_stock_code_none(self, reverse=True):
        """
        [NEW] 获取默认分析基准股票代码。
        reverse=True: 寻找领涨标的。
        reverse=False: 寻找领跌标的。
        """
        df_all = self.df_all
        if df_all.empty: return None, 0
        
        # 兼容性处理
        if 'per1d' in df_all.columns and 'percent' in df_all.columns:
            percent_series = np.where((df_all['percent'] == 0) | df_all['percent'].isna(), df_all['per1d'], df_all['percent'])
            percent_series = pd.Series(percent_series, index=df_all.index)
        elif 'per1d' in df_all.columns:
            percent_series = df_all['per1d']
        elif 'percent' in df_all.columns:
            percent_series = df_all['percent']
        else:
            percent_series = pd.Series(0, index=df_all.index)

        final_percent = percent_series
        
        # --- 根据视角选择基准 ---
        if reverse:
            # 模式 1: 看涨热点，优先选涨的最猛的标的
            positive_mask = final_percent > 0
            if positive_mask.any():
                max_idx = final_percent[positive_mask].idxmax()
            else:
                max_idx = final_percent.idxmax() if not final_percent.empty else None
        else:
            # 模式 2: 看跌主流，优先选跌的最猛的标的（捕捉杀跌流动性）
            negative_mask = final_percent < 0
            if negative_mask.any():
                max_idx = final_percent[negative_mask].idxmin() # 找最小值，即最负的
            else:
                max_idx = final_percent.idxmin() if not final_percent.empty else None
                
        percent = final_percent.loc[max_idx] if max_idx is not None else 0
        return max_idx, percent

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


    def get_global_concepts_ranking(self, top_n=10, reverse=True):
        """
        [NEW] 全市场概念热度/跌幅排序，不锚定具体个股。
        相比 get_following_concepts_by_correlation，它更适合做“大盘总览”。
        """
        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            return []
            
        df_all = self.df_all
        
        # 1. 提取涨幅序列
        if 'percent' in df_all.columns and 'per1d' in df_all.columns:
            percent_series = np.where((df_all['percent'] == 0) | df_all['percent'].isna(), df_all['per1d'], df_all['percent'])
            percent_series = pd.Series(percent_series, index=df_all.index)
        else:
            percent_series = df_all.get('percent', df_all.get('per1d', pd.Series(0, index=df_all.index)))

        # 2. 准备基础数据
        required_cols = ['category', 'ma5d', 'ma20d', 'ma60d', 'close']
        available_cols = [c for c in required_cols if c in df_all.columns]
        df_tmp = df_all[available_cols].copy()
        df_tmp['percent'] = percent_series
        
        # 3. 展开概念
        df_tmp['category'] = df_tmp['category'].fillna('').astype(str)
        df_exploded = df_tmp.assign(category=df_tmp['category'].str.split(';')).explode('category')
        df_exploded['category'] = df_exploded['category'].str.strip()
        
        # 过滤无效
        df_exploded = df_exploded[~df_exploded['category'].isin(['', '0', 'nan', 'None'])]
        
        # 预计算趋势
        if 'ma5d' in df_exploded.columns and 'ma60d' in df_exploded.columns:
            df_exploded['is_bullish'] = (df_exploded['ma5d'] > df_exploded['ma20d']) & \
                                        (df_exploded['ma20d'] > df_exploded['ma60d']) & \
                                        (df_exploded['close'] > df_exploded['ma60d'])
        else:
            df_exploded['is_bullish'] = False
            
        # 4. 分组聚合统计
        g = df_exploded.groupby('category')
        # 统计核心指标：均值、总数、趋势占比
        agg_df = g.agg(
            avg_percent=('percent', 'mean'),
            count=('percent', 'size'),
            bullish_ratio=('is_bullish', 'mean')
        )
        
        # 过滤杂音（成员小于 3 的板块通常没代表性）
        agg_df = agg_df[agg_df['count'] >= 3]
        
        # 5. 计算综合得分 (针对总览模式优化的公式)
        # Score = avg_percent * (1 + bullish_ratio)
        # 这样既考虑了当日爆发力，也考虑了板块结构性。
        agg_df['score'] = agg_df['avg_percent'] * (1.0 + agg_df['bullish_ratio'])
        
        # 6. 排序并取 TopN
        # reverse=True: 领涨优先; reverse=False: 领跌优先
        agg_df = agg_df.sort_values('score', ascending=not reverse)
        top_df = agg_df.head(top_n)
        
        results = []
        for name, row in top_df.iterrows():
            # 兼容 get_following_concepts_by_correlation 的返回格式
            results.append((name, round(row['score'], 2), round(row['avg_percent'], 2), 1.0, round(row['bullish_ratio'], 2)))
            
        return results

    def get_following_concepts_by_correlation(self, code, top_n=10, reverse=True):

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
        df_all_orig = self.df_all
        
        # --- ✅ 修正涨幅替代逻辑（无副作用提取） ---
        if 'percent' in df_all_orig.columns and 'per1d' in df_all_orig.columns:
            percent_series = np.where((df_all_orig['percent'] == 0) | df_all_orig['percent'].isna(), df_all_orig['per1d'], df_all_orig['percent'])
            percent_series = pd.Series(percent_series, index=df_all_orig.index)
        elif 'percent' not in df_all_orig.columns and 'per1d' in df_all_orig.columns:
            percent_series = df_all_orig['per1d']
        elif 'percent' in df_all_orig.columns:
            percent_series = df_all_orig['percent']
        else:
            raise ValueError("DataFrame 必须包含 'percent' 或 'per1d' 列")

        # --- 获取目标股票涨幅 ---
        try:
            stock_percent = percent_series.loc[code] if code in percent_series.index else 0
            stock_row = df_all_orig.loc[code] if code in df_all_orig.index else None
        except Exception:
            try:
                stock_row = df_all_orig.loc[code]
                stock_percent = percent_series.loc[code] if code in percent_series.index else 0
            except Exception:
                logger.info(f"[WARN] 未找到 {code} 的数据")
                return []
        # --- 获取股票所属的概念列表 ---
        stock_categories = [
            c.strip() for c in str(stock_row.get('category', '')).split(';') if c.strip()
        ]
        # logger.info(f'stock_categories : {stock_categories}')
        if not stock_categories:
            logger.info(f"[INFO] {code} 无概念数据。")
            return []

        # [OPTIMIZE] 增强热点追踪：引入均线趋势指标（MA5/20/60）
        required_cols = ['category', 'ma5d', 'ma20d', 'ma60d', 'close']
        # 兜底确保列存在
        available_cols = [c for c in required_cols if c in df_all_orig.columns]
        df_tmp = df_all_orig[available_cols].copy()
        df_tmp['percent'] = percent_series
        
        # 1. 拆分并展开 category 列，同时清洗
        df_tmp['category'] = df_tmp['category'].fillna('').astype(str)
        df_exploded = df_tmp.assign(category=df_tmp['category'].str.split(';')).explode('category')
        df_exploded['category'] = df_exploded['category'].str.strip()
        
        # 预计算每只个股的趋势状态
        if 'ma5d' in df_exploded.columns and 'ma60d' in df_exploded.columns:
            # 强势大结构：MA5 > MA20 > MA60 且在 MA60 上
            df_exploded['is_bullish'] = (df_exploded['ma5d'] > df_exploded['ma20d']) & \
                                        (df_exploded['ma20d'] > df_exploded['ma60d']) & \
                                        (df_exploded['close'] > df_exploded['ma60d'])
            # 站在生命线上：Close > MA60
            df_exploded['is_above_60'] = df_exploded['close'] > df_exploded['ma60d']
        else:
            df_exploded['is_bullish'] = False
            df_exploded['is_above_60'] = True # 降级处理
        
        # 2. 快速过滤无效概念 (空字符串、'0' 等)
        df_exploded = df_exploded[
            (df_exploded['category'] != '') & 
            (df_exploded['category'] != '0') & 
            (df_exploded['category'] != 'nan')
        ]
        
        # 3. 按概念分组统计 (包含趋势指标列)
        g = df_exploded.groupby('category')
        counts = g.size()
        # 4. 过滤成员数不足 2 的概念 (过滤杂音)
        valid_mask = counts >= 2
        valid_concept_names = counts[valid_mask].index
        
        concept_dict = {}
        concept_stats = {} # 存储每个板块的趋势统计 (如均线多头占比)
        for name in valid_concept_names:
            grp = g.get_group(name)
            concept_dict[name] = grp['percent'].tolist()
            # 计算趋势占比 (均线多头占比)
            bullish_ratio = grp['is_bullish'].mean() if 'is_bullish' in grp.columns else 0
            above_60_ratio = grp['is_above_60'].mean() if 'is_above_60' in grp.columns else 1.0
            concept_stats[name] = (bullish_ratio, above_60_ratio)

        # --- 按得分排序逻辑继续 ---


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
            
            # 使用传入的代码或选择的最强股作为基准
            effective_base_percent = stock_percent
            follow_ratio = compute_follow_ratio(percents, effective_base_percent)
            
            # 保证 follow_ratio 不会完全导致 score 消失（至少保留 0.5 的底线，确保逆市热点能脱颖而出）
            if follow_ratio < 0.5 and abs(avg_percent) > 2:
                follow_ratio = 0.5
                
            # --- [STRATEGIC] 引入趋势权重算法 ---
            bullish_ratio, above_60_ratio = concept_stats.get(c, (0, 1.0))
            
            # 1. 基础得分 (实时关联度)
            score = avg_percent * follow_ratio
            
            # 2. 趋势加成 (电力、电池等长效热点补偿)
            # 强势结构占比每增加 10%，得分加成 15%
            trend_multiplier = 1.0 + (bullish_ratio * 1.5)
            
            # 3. 破位惩罚 (拦截加速下跌中的反弹骗线)
            # 如果板块内超过 70% 都在 60 日线下，判定为不可持续
            if above_60_ratio < 0.3:
                trend_multiplier *= 0.3 # 剧烈打折
                
            score *= trend_multiplier
            
            # 保留两位小数
            score = round(score, 2)
            avg_percent = round(avg_percent, 2)
            follow_ratio = round(follow_ratio, 2)
            
            concept_score.append((c, score, avg_percent, follow_ratio, bullish_ratio))

        # --- 排序并返回 ---
        # 根据外部传入的 reverse 参数决定：上涨(True)则看领涨，下跌(False)则看跌势最强。
        concept_score.sort(key=lambda x: x[1], reverse=reverse)
        concepts = [c[0] for c in concept_score]
        scores = np.array([c[1] for c in concept_score])
        avg_percents = np.array([c[2] for c in concept_score])
        follow_ratios = np.array([c[3] for c in concept_score])
        bullish_ratios = np.array([c[4] for c in concept_score])
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
        self.concept_top5 = concept_score[:5]
        return concept_score[:10]

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
            market_info = self.market_map.get(market_cn, {"code": marketInit, "blkname": marketblk})
            self.global_values.setkey("market", market_info["code"])
            self.global_values.setkey("blkname", market_info["blkname"])
            self.global_values.setkey("st_key_sort", self.st_key_sort_value.get())
            logger.info(f"选择市场: {market_cn}, code={market_info['code']}, blkname={market_info['blkname']} st_key_sort_value:{self.st_key_sort_value.get()}")

        self.market_combo.bind("<<ComboboxSelected>>", on_market_select)
        
        tk.Label(ctrl_frame, text="stkey:").pack(side="left", padx=2)
        self.st_key_sort_value = tk.StringVar()
        self.st_key_sort_entry = tk.Entry(ctrl_frame, textvariable=self.st_key_sort_value,width=5)
        self.st_key_sort_entry.pack(side="left")
        # 绑定回车键提交
        self.st_key_sort_entry.bind("<Return>", self.on_st_key_sort_enter)
        self.st_key_sort_value.set(self.st_key_sort) 
        
        # --- resample 下拉框 ---
        resampleValues = ["d",'2d','3d', "w", "m"]
        tk.Label(ctrl_frame, text="resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=resampleValues, width=3)
        self.resample_combo.current(resampleValues.index(self.global_values.getkey("resample")))
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        
        # --- [NEW] 窗口位置联动 (Manual Pos Sync) ---
        def save_main_pos():
            if hasattr(self, 'save_window_position'):
                self.save_window_position(self, "main_window")
                toast_message(self, "主窗口位置已保存")

        def load_main_pos():
            if hasattr(self, 'load_window_position'):
                self.load_window_position(self, "main_window")
                self.reload_cfg_value()
                toast_message(self, "主窗口位置与配置已恢复")

        tk.Button(ctrl_frame, text="💾", command=save_main_pos, font=("Segoe UI Symbol", 9), relief="flat", padx=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="🔄", command=load_main_pos, font=("Segoe UI Symbol", 9), relief="flat", padx=2).pack(side="left", padx=2)
        self._last_resample = self.resample_combo.get().strip()

        # ✅ 关键：同步一次状态
        on_market_select()

        # --- 底部搜索框 2 ---
        bottom_search_frame = tk.Frame(self)
        bottom_search_frame.pack(side="bottom", fill="x", pady=1)

        self.search_history1 = []
        self.search_history2 = []
        self.search_history3 = []
        self.search_history4 = []
        self.search_history5 = []
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
        # self.search_combo4.bind("<Button-3>", self.on_right_click_search_var4)

        self.query_manager = QueryHistoryManager(
            self,
            search_var1=self.search_var1,
            search_var2=self.search_var2,
            # search_var4=self.search_var4,
            search_combo1=self.search_combo1,
            search_combo2=self.search_combo2,
            # search_combo4=self.search_combo4,
            history_file=SEARCH_HISTORY_FILE,
            sync_history_callback = self.sync_history_from_QM,
            test_callback=self.on_test_code
        )

        # 从 query_manager 获取历史 (Raw dicts)
        h1, h2, h3, h4 ,h5 = self.query_manager.history1, self.query_manager.history2, self.query_manager.history3, self.query_manager.history4 , self.query_manager.history5

        # [MODIFIED] Enhanced display: "Note (Query)"
        self.search_map1 = {}
        self.search_map2 = {}
        self.search_map4 = {} # 给历史4也准备一个map
        self.search_map5 = {} # 给历史5也准备一个map
        
        self.search_history1 = self._format_history_list(h1, self.search_map1)
        self.search_history2 = self._format_history_list(h2, self.search_map2) 
        self.search_history3 = [r["query"] for r in h3]
        self.search_history4 = self._format_history_list(h4, self.search_map4)
        self.search_history5 = self._format_history_list(h4, self.search_map5)

        # [MODIFIED] Update combobox values with formatted history
        self.search_combo1['values'] = self.search_history1
        self.search_combo2['values'] = self.search_history2
        if hasattr(self, 'search_combo4'):
            self.search_combo4['values'] = self.search_history4
        if hasattr(self, 'search_combo5'):
            self.search_combo5['values'] = self.search_history5
        # Update Combobox values
        self.search_combo1['values'] = self.search_history1
        self.search_combo2['values'] = self.search_history2

        # [NEW] Custom selection handler to map Label -> Query
        def on_combo1_selected(event):
            selection = self.search_combo1.get()
            # real_query = self.search_map1.get(selection, selection)
            # Update variable without triggering trace immediately if possible, 
            # but trace is fine as it calls apply_search
            # self.search_var1.set(real_query) 
            self.apply_search()

        def on_combo2_selected(event):
            selection = self.search_combo2.get()
            # real_query = self.search_map2.get(selection, selection)
            # self.search_var2.set(real_query)
            self.apply_search()

        # Re-bind selection events (override previous lambda)
        self.search_combo1.bind("<<ComboboxSelected>>", on_combo1_selected)
        self.search_combo2.bind("<<ComboboxSelected>>", on_combo2_selected)

        tk.Button(bottom_search_frame, text="搜索", command=lambda: self.apply_search()).pack(side="left", padx=3)
        
        # 🧪 [NEW] 手动触发扫描：每点击一次扫描一批 (由策略引擎内部 RR 游标控制)
        def manual_scan():
            self._run_live_strategy_process()
            toast_message(self, "🚀 手动信号扫描已触发 (按批次轮转)")
            
        tk.Button(bottom_search_frame, text="信号扫描", command=manual_scan, bg="#e3f2fd", cursor="hand2").pack(side="left", padx=3)

        tk.Button(bottom_search_frame, text="清空", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="删除", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="管理", command=lambda: self.open_column_manager()).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="关闭", command=lambda: self.close_all_alerts()).pack(side="left", padx=2)


        # 功能选择下拉框（固定宽度）
        options = ["窗口重排","Query编辑","停止刷新", "启动刷新" , "保存数据", "读取存档", "复盘数据", "实盘数据", "盈亏统计", "交易分析Qt6", "GUI工具", "覆写TDX", "手札总览", "语音预警","重置快捷键", "关闭全局快捷键"]
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            bottom_search_frame, textvariable=self.action_var,
            values=options, state="readonly", width=10
        )
        self.action_combo.set("功能选择")
        
        # [NEW] 回测按钮 - 放在功能选择框前面
        self.backtest_btn = tk.Button(bottom_search_frame, text=" 回测 ", 
                                      fg="#FF4500", font=self.default_font_bold, pady=1,
                                      command=self.open_backtest_replay_dialog)
        self.backtest_btn.pack(side="left", padx=5)

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
            elif action == "覆写TDX":
                self.write_to_blk(append=False)
            elif action == "手札总览":
                self.open_handbook_overview()
            elif action == "语音预警":
                self.open_voice_monitor_manager()
            elif action == "盈亏统计":
                self.open_trade_report_window()
            elif action == "交易分析Qt6":
                self.open_trading_analyzer_qt6()
            elif action == "GUI工具":
                self.open_kline_viewer_qt()
            elif action == "复盘数据":
                self.open_market_pulse()
            elif action == "实盘数据":
                self.persistent_df_all_to_h5()
            elif action == "重置快捷键":
                self.setup_global_hotkey(show_toast=True, mode="GLOBAL")
            elif action == "关闭全局快捷键":
                self.setup_global_hotkey(show_toast=True, mode="LOCAL")


        def on_select(event=None):
            run_action(self.action_combo.get())
            self.action_combo.set("功能选择")

        self.action_combo.bind("<<ComboboxSelected>>", on_select)



        tk.Button(ctrl_frame, text="清空", command=lambda: self.clean_search(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除", command=lambda: self.delete_search_history(2)).pack(side="left", padx=2)
        
        # 为 search_var4/history4 添加 专门的清空/删除按钮 (在 search_combo4 之后)
        # tk.Button(ctrl_frame, text="清空4", command=lambda: self.clean_search(3)).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除4", command=lambda: self.delete_search_history(3)).pack(side="left", padx=2)
        
        tk.Button(ctrl_frame, text="监控", command=lambda: self.KLineMonitor_init(), font=self.default_font_bold, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="选股", command=lambda: self.open_stock_selection_window(), font=self.default_font_bold, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="写入", command=lambda: self.write_to_blk(), font=self.default_font_bold, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="复盘", command=self.open_market_pulse, font=self.default_font_bold, 
                  bg="purple", fg="white", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="审计", command=self.open_dna_auditor_top50, font=self.default_font_bold, 
                  bg="#004d99", fg="white", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="竞价🚀", command=lambda: self.open_sector_bidding_panel(), font=self.default_font_bold, fg="blue", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="赛马🏁", command=lambda: self.open_racing_panel(), font=self.default_font_bold, fg="darkred", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="实时", command=lambda: self.open_realtime_monitor(), font=self.default_font, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="55188", command=lambda: self.open_ext_data_viewer(), font=self.default_font_bold, fg="darkgreen", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="追踪", command=lambda: self.open_live_signal_trace(), font=self.default_font_bold, fg="purple", pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="信号🔥", command=lambda: self.open_live_signal_viewer(), font=self.default_font_bold, fg="red", pady=2).pack(side="left", padx=2)

        if len(self.search_history1) > 0:
            # [MODIFIED] Use the first item, resolving it via map if needed
            first_disp = self.search_history1[0]
            val = self.search_map1.get(first_disp, first_disp)
            self.search_var1.set(val)
            
        if len(self.search_history2) > 0:
            first_disp = self.search_history2[0]
            val = self.search_map2.get(first_disp, first_disp)
            self.search_var2.set(val)


        self.setup_global_hotkey()
        self._schedule_after(1000,lambda :self.load_window_position(self, "main_window", default_width=1200, default_height=480))
        self.open_column_manager_init()

    def open_backtest_replay_dialog(self):
        """弹出赛马回测配置对话框，支持日期选择与时间点跳转 (适配 DPI 缩放与居中)"""
        import tkinter as tk
        from tkinter import ttk, messagebox
        
        try:
            from tkcalendar import DateEntry
            use_calendar = True
        except ImportError:
            use_calendar = False
            logger.warning("tkcalendar not found, falling back to entry.")
            
        dialog = tk.Toplevel(self)
        dialog.title("赛马回测/回放配置")
        
        # 🚀 [FIX] 适配 DPI 缩放：完全基于内容自适应布局
        scale = getattr(self, 'dpi_scale', 1.0)
        dialog.resizable(True, True)
        
        # 居中对齐与锁定
        dialog.transient(self)
        dialog.grab_set()
        
        # 增加内部边距填充
        main_frame = tk.Frame(dialog, padx=int(30*scale), pady=int(25*scale))
        main_frame.pack(fill="both", expand=True)
        
        title_font = (self.default_font.cget("family"), int(13*scale), "bold")
        label_font = (self.default_font.cget("family"), int(10*scale))
        
        # 1. 标题
        tk.Label(main_frame, text="🏁 赛马回放分析系统", font=title_font, fg="#CF6679").pack(pady=(0, int(20*scale)))
        
        # 2. 日期选择
        tk.Label(main_frame, text="📅 选择日期 (YYYY-MM-DD):", font=label_font).pack(anchor="w")
        
        # 🚀 [FIX] 交易日智能判定：如果是交易日则用今天，否则用上个交易日
        if cct.get_trade_date_status():
            default_date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            default_date_str = cct.get_last_trade_date()

        if use_calendar:
            date_entry = DateEntry(main_frame, width=20, background='#333',
                                  foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd',
                                  font=label_font)
            try:
                date_entry.set_date(datetime.strptime(default_date_str, '%Y-%m-%d'))
            except:
                pass
            date_entry.pack(fill="x", pady=(int(8*scale), int(15*scale)))
        else:
            date_entry = tk.Entry(main_frame, font=label_font)
            date_entry.insert(0, default_date_str)
            date_entry.pack(fill="x", pady=(int(8*scale), int(15*scale)))
        
        # 3. 时间选择 (下拉)
        tk.Label(main_frame, text="🕒 启动时间点 (回放起点):", font=label_font).pack(anchor="w")
        time_var = tk.StringVar(value="09:25:00")
        time_values = ["09:15:00", "09:25:00", "09:30:00", "10:00:00", "10:30:00", "11:00:00", "11:30:00", 
                       "13:00:00", "13:30:00", "14:00:00", "14:30:00", "14:45:00"]
        time_combo = ttk.Combobox(main_frame, textvariable=time_var, values=time_values, state="readonly",
                                 font=label_font)
        time_combo.pack(fill="x", pady=(int(8*scale), int(15*scale)))

        # 4. 运行选项 (详细日志与日志等级)
        opts_frame = tk.Frame(main_frame)
        opts_frame.pack(fill="x", expand=True, pady=(int(5*scale), int(20*scale)))

        verbose_var = tk.BooleanVar(value=True)
        verbose_chk = tk.Checkbutton(opts_frame, text=" 📊 详细日志", variable=verbose_var,
                                     font=label_font)
        verbose_chk.pack(side="left")

        tk.Label(opts_frame, text=" | 等级:", font=label_font, fg="#666").pack(side="left")
        log_var = tk.StringVar(value="WARNING") # 🚀 默认 INFO，更适合普通用户
        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        log_combo = ttk.Combobox(opts_frame, textvariable=log_var, values=log_levels, state="readonly",
                                width=8, font=label_font)
        log_combo.pack(side="left", padx=int(5*scale))

        def on_run():
            selected_date = date_entry.get()
            selected_time = time_var.get()
            is_verbose = verbose_var.get()
            selected_log = log_var.get()
            if not re.match(r'\d{4}-\d{2}-\d{2}', selected_date):
                messagebox.showerror("格式错误", "日期格式应为 YYYY-MM-DD\n例如: 2026-04-20")
                return
            dialog.destroy()
            self._run_backtest_replay_process(selected_date, selected_time, is_verbose, selected_log)
            
        run_btn = tk.Button(main_frame, text=" 🚀 启动回放分析 ", bg="#121212", fg="#03DAC6", 
                           font=(self.default_font.cget("family"), int(11*scale), "bold"),
                           relief="groove", pady=int(10*scale),
                           command=on_run)
        run_btn.pack(fill="x")

        # 🚀 [NEW] 强力确保可见性
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        
        req_w = dialog.winfo_reqwidth()
        req_h = dialog.winfo_reqheight()
        
        # 居中逻辑优化
        main_x, main_y = self.winfo_x(), self.winfo_y()
        main_w, main_h = self.winfo_width(), self.winfo_height()
            
        x = main_x + (main_w - req_w) // 2
        y = main_y + (main_h - req_h) // 2
        dialog.geometry(f"{req_w}x{req_h}+{max(0, x)}+{max(0, y)}") # 强制固定宽高一次
        
        # 🚀 [NEW] 支持回车键确认
        dialog.bind("<Return>", lambda e: on_run())

    def _run_backtest_replay_process(self, replay_date, start_time, verbose=True, log_level="ERROR"):
        """独立多进程启动 test_bidding_replay.py，兼容 EXE 打包环境 (高性能透传模式)"""
        # [🚀 统一防抖保护] 赛马与回测共享冷却时间 (10s 阈值)
        now = time.time()
        last_unified = getattr(self, '_last_racing_backtest_unified_t', 0)
        if now - last_unified < 10.0:
            logger.warning("🏁 [Racing/Backtest] 启动太频繁（统一防抖中），请稍候...")
            toast_message(self, f"🏁 启动太频繁，请等待 {int(10.0 - (now - last_unified))}s")
            return
        self._last_racing_backtest_unified_t = now

        # [🚀 唯一性保护] 确保实盘赛马与回测互斥
        is_racing_alive = False
        if hasattr(self, "_racing_panel_win") and self._racing_panel_win is not None:
            try:
                if self._racing_panel_win.isVisible():
                    is_racing_alive = True
            except RuntimeError:
                self._racing_panel_win = None
        
        if is_racing_alive:
            logger.warning("🏁 [Backtest] 实盘赛马面板正在运行，无法启动回测。")
            toast_message(self, "🏁 实盘赛马运行中，请先注意资源占用易触发卡顿，请尽快关闭实盘赛马")
            # return

        # [🚀 唯一性保护] 确保同时只有一个回测进程在运行
        if hasattr(self, 'backtest_process') and self.backtest_process and self.backtest_process.is_alive():
            logger.warning("🏁 [Backtest] 回测进程已在运行中，请勿重复启动。")
            toast_message(self, "🏁 回测进程已在运行中")
            return

        from types import SimpleNamespace
        import test_bidding_replay as replay_module
        from tkinter import messagebox
        
        # 🚀 [OPTIMIZED] 记录启动时间
        launch_start = time.time()
        
        # 构造模拟参数，对齐 test_bidding_replay.py 的 main 函数需求
        # 注意：这里透传了 [log_level, speed, ui, verbose, start, date, resample] 等核心字段
        args_namespace = SimpleNamespace(
            speed=20.0,
            observation=None,
            start=start_time,
            end="15:00:00",
            verbose=verbose,
            resample=self.resample_combo.get() if hasattr(self, 'resample_combo') else 'd',
            codes=None,
            date=replay_date,
            today=False,
            ui=True,
            live=False,
            interval=30,
            log=log_level
        )
        
        # 获取当前主进程持有的行情全量快照，实现秒开 (必须在主线程闭环内获取副本)
        current_df_all = None
        if hasattr(self, 'df_all') and self.df_all is not None:
            try:
                current_df_all = self.df_all.copy()
            except:
                current_df_all = self.df_all
        
        def _launch_task():
            try:
                # [NEW] 注入退出同步事件
                self._backtest_quit_event = mp.Event()
                
                # 🚀 使用 mp.Process 启动，避开 subprocess 的 IO 判定与重复抓取
                self.backtest_process = mp.Process(
                    target=replay_module.main,
                    args=(args_namespace, current_df_all, self._backtest_quit_event),
                    daemon=False
                )
                
                # 🛡️ [FINAL-GUARD] 再次确认主线程环境
                if not threading.current_thread() is threading.main_thread():
                    logger.warning("🏁 [Backtest] Re-dispatching launch to main thread...")
                    self.after(0, _launch_task)
                    return

                self.backtest_process.start()
                
                # [🚀 NEW] 启动存活监视，确保回测进程退出后也能触发统一防抖
                def monitor_backtest_exit(proc):
                    try:
                        proc.join()
                    except: pass
                    self._last_racing_backtest_unified_t = time.time()
                    logger.info("🏁 [Backtest] 进程已物理退出，防抖保护已激活 (10s)")
                
                threading.Thread(target=monitor_backtest_exit, args=(self.backtest_process,), daemon=True).start()

                elapsed = (time.time() - launch_start) * 1000
                msg = f"🏁 已成功拉起回测进程 ({replay_date} {start_time}) | 唤起耗时: {elapsed:.1f}ms"
                logger.info(msg)
                
                if hasattr(self, 'status_var2'):
                    self.after(0, lambda: self.status_var2.set(msg))
                    
            except Exception as e:
                logger.exception(f"Failed to launch backtest via mp.Process: {e}")
                self.after(0, lambda: messagebox.showerror("启动异常", f"回测进程 (mp) 启动失败:\n{str(e)}"))
            finally:
                pass

        # 🚀 [FIX] 彻底根治 Fatal Python error: PyEval_RestoreThread。
        # 禁止在子线程中执行 mp.Process.start()。在 Windows spawn 模式下，子线程 pickling 极易引发 GIL 冲突。
        # 将启动逻辑回退至主线程执行，并通过 after 延时给 UI 留出响应空间。
        self.after(200, _launch_task) # 稍微增加延时，确保 UI 消息 (toast) 已显示
        toast_message(self, "🏁 正在拉起回测引擎，请稍候...")

    def _run_live_strategy_process(self, full_df=None):
        """
        [Helper] 集中封装实盘策略分发逻辑 (信号触发 & 语音报警)
        :param full_df: 输入行情 Dataframe，若为 None 则尝试使用缓存的 self.df_all
        """
        # 1. 数据就绪检查
        if full_df is None:
            full_df = getattr(self, 'df_all', None)
        
        if full_df is None or full_df.empty:
            logger.warning("Strategy process skipped: df_all is empty or None")
            return
            
        # 2. 策略引擎检查
        strategy_engine = getattr(self, 'live_strategy', None)
        if strategy_engine is None:
            logger.warning("Strategy process skipped: live_strategy is None")
            return

        # 3. [ASYNC UPGRADE] 将耗时的策略处理异步化，避免阻塞 UI 线程 (尤其是 manual_scan)
        try:
            # 兼容：从全局配置读取当前周期 (归一化处理，防止 'd' vs 'D')
            cur_res = str(self.global_values.getkey("resample") or 'd').lower().strip()
            cur_concept = getattr(self, 'concept_top5', None)

            # 🛠️ [SNAPSHOT] 对数据进行快照化，防止子线程处理时主线程正在修改引发 RuntimeError: dict changed size during iteration
            # 或者是 Pandas 的 SettingWithCopyWarning
            df_snapshot = full_df.copy()

            if hasattr(self, 'executor') and self.executor:
                # [THROTTLE] 增加分发节流保护，防止前一个分析任务由于卡顿未返回时持续堆积
                if getattr(self, '_is_strategy_running', False):
                    return
                self._is_strategy_running = True
                
                def _wrap_process():
                    try:
                        strategy_engine.process_data(df_snapshot, concept_top5=cur_concept, resample=cur_res)
                    finally:
                        self._is_strategy_running = False

                # 投递到线程池，立即返回，释放 UI 指令
                self.executor.submit(_wrap_process)
            else:
                # 兜底方案 (不推荐)
                strategy_engine.process_data(df_snapshot, concept_top5=cur_concept, resample=cur_res)
            
        except Exception as strategy_err:
            logger.exception(f"Async Strategy submission failed: {strategy_err}")


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


            # 只保留 DataFrame 中存在的列，避免 TclError
            new_columns = [c for c in new_columns if c in self.df_all.columns or c == "code"]

            self.update_treeview_cols(new_columns)


    def on_st_key_sort_enter(self, event):
        sort_val = self.st_key_sort_value.get()
        def diff_and_replace_all(old_cols, new_cols):
            """找出两个列表不同的元素，返回替换规则 (old, new)"""
            replace_rules = []
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    replace_rules.append((old, new))
            return replace_rules

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
            DISPLAY_COLS, diff = update_display_cols_if_diff(DISPLAY_COLS, DISPLAY_COLS_2, self.current_cols[1:])
            if diff:
                logger.info(f'diff : {diff}')
                self.replace_column(*diff,apply_search=False)
    def refresh_data(self):

        """
        手动刷新：更新 resample 全局配置，触发后台进程下一轮 fetch_and_process
        """

        
        if self._last_resample == self.resample_combo.get().strip():
            return
        else:
            if self.vis_var.get() and hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
                self.last_vis_var_status = self.vis_var.get()
                self.vis_var.set(False)
        resample = self.resample_combo.get().strip()
        logger.info(f'set resample : {resample}')
        # cct.GlobalValues().setkey("resample", resample)
        self.global_values.setkey("resample", resample)
        self.blkname = ct.Resample_LABELS_Blk[resample] or "060.blk"
        self.global_values.setkey("blkname", self.blkname)
        self.global_values.setkey("st_key_sort", self.st_key_sort_value.get())
        market_cn = self.market_combo.get()
        market_info = self.market_map.get(market_cn, {"code": marketInit, "blkname": marketblk})
        self.global_values.setkey("market", market_info["code"])
        self.global_values.setkey("blkname", market_info["blkname"])

        self.refresh_flag.value = False
        time.sleep(0.6)
        self.refresh_flag.value = True
        self.status_var.set(f"手动刷新: resample={resample}")


    def _start_process(self):
        self.refresh_flag = mp.Value('b', True)
        self.log_level = mp.Value('i', log_level)  # 'i' 表示整数
        self.detect_calc_support = mp.Value('b', detect_calc_support)  # 'i' 表示整数
        
        self.proc = mp.Process(
            target=fetch_and_process,
            args=(self.global_dict, self.queue, self.blkname, 
                  self.refresh_flag, self.log_level, self.detect_calc_support, 
                  marketInit, marketblk, duration_sleep_time),
            kwargs={
                "status_callback": tip_var_status_flag  # 注意不用括号，传函数
            },
            name="DataFetchProcess",
            daemon=False # 🚀 [FIX] 必须为 False，否则内部无法调用 to_mp_run_async (daemonic processes cannot have children)
        )
        self.proc.start()
        
        # 🚀 [NEW] 启动行情总线监听线程 (P0-3)
        # 职责：将 Queue 中的数据包瞬间转移到 MarketStateBus，释放 Queue 积压
        self._bus_worker_thread = threading.Thread(
            target=self._market_bus_worker_loop,
            name="MarketBusWorker",
            daemon=True
        )
        self._bus_worker_thread.start()
        # logger.info("✅ [PERF] MarketBusWorker thread started.")


    def stop_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False
            logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
            # logger.info(f"DEBUG: stop_refresh called. refresh_flag ID: {id(self.refresh_flag)}")
        self.status_var.set("刷新已停止")

    def start_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = True

    def _market_bus_worker_loop(self):
        """
        [PERF] 行情总线监听循环 (P0-3)
        在后台线程中高速清空 Queue，将全量快照存入 MarketStateBus。
        好处：UI 线程不再负责 get_nowait()，彻底消除 unpickle 引起的主线程卡顿。
        """
        logger.info("📡 MarketBusWorker loop started.")
        while not getattr(self, "_is_closing", False):
            try:
                # 1. 尽可能清空积压，只保留最新的一帧（覆盖式模型）
                latest_p = None
                while not self.queue.empty():
                    try:
                        latest_p = self.queue.get_nowait()
                    except Empty:
                        break
                
                if latest_p:
                    # 2. 发布到行情总线
                    full_df = None
                    df_filtered = None
                    if isinstance(latest_p, dict):
                        full_df = latest_p.get('full_snapshot')
                        df_filtered = latest_p.get('filtered_ui_data')
                    else:
                        full_df = latest_p
                    
                    if full_df is not None:
                        self.market_bus.publish(full_df, df_filtered)
                        # logger.debug("📡 [Bus] Published latest snapshot.")
                
                time.sleep(0.05) # 20Hz 刷新率足够
            except Exception as e:
                logger.error(f"❌ MarketBusWorker Error: {e}")
                time.sleep(1)

            # logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
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
        assert_main_thread("update_tree")
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return
            
        if getattr(self, '_is_closing', False):
            return

        
        
        try:
            if self.refresh_enabled:
                
                # [WATCHDOG] 增强版 Watchdog：区分后台计算与 UI 同步
                is_bg_busy = getattr(self, '_is_processing_tree_data', False)
                is_ui_pending = getattr(self, '_is_ui_sync_pending', False)
                
                if is_bg_busy or is_ui_pending:
                    now = time.time()
                    last_start = getattr(self, '_last_processing_start_time', 0)
                    elapsed = now - last_start
                    
                    if last_start > 0 and elapsed > 30:
                        reason = "Algorithm/BG" if is_bg_busy else "UI/Dispatch"
                        logger.warning(f"⚠️ [DataWatchdog] Detected STUCK ({reason}) for {elapsed:.1f}s. Forcing reset.")
                        self._is_processing_tree_data = False
                        self._is_ui_sync_pending = False # 🛡️ 双重重置
                        self._last_processing_start_time = 0
                    else:
                        # 正常排队中，5秒后再次检查
                        self._schedule_after(5000, self.update_tree)
                        return
                
                latest_df = None

                # 📂 确保 K 线缓存周期性保存 (即便没有新数据进入队列)
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    try:
                        self.realtime_service.save_cache(force=False)
                    except Exception as e:
                        logger.error(f"Periodic cache save check failed: {e}")

                # 🔄 优化：处理队列中的所有数据包，不跳过中间增量（解决“缺斤短两”数据不全问题）
                # 我们逐个分发包到后台 worker 进行策略计算，但只在最后一轮同步 UI
                # 🔄 [PERF] 架构重构：改为从 MarketStateBus "拉取" 最新快照 (Snapshot Pull)
                # 优点：不阻塞 Queue，不处理中间积压包，永远只处理当前最新帧
                bus_data = self.market_bus.get_latest(since_version=getattr(self, '_last_ui_bus_version', 0))
                
                if bus_data:
                    version, full_df, df_filtered, snap_time = bus_data
                    self._last_ui_bus_version = version
                    latest_p = {
                        'full_snapshot': full_df,
                        'filtered_ui_data': df_filtered,
                        'timestamp': snap_time
                    }

                    
                    # ⭐ [RESTORED] 跨进程中转逻辑：在处理数据包之前快速消耗信号
                    try:
                        from signal_bus import get_signal_bus
                        bus = get_signal_bus()
                        if hasattr(self, 'signal_bridge_queue'):
                            bridge_count = 0
                            while not self.signal_bridge_queue.empty():
                                try:
                                    event = self.signal_bridge_queue.get_nowait()
                                    if event:
                                        bus.publish(
                                            event_type=getattr(event, 'event_type', None) or getattr(event, 'type', 'unknown'),
                                            source=f"{getattr(event, 'source', 'unknown')} (bridged)",
                                            payload=getattr(event, 'payload', {}),
                                            signal=getattr(event, 'signal', None)
                                        )
                                        bridge_count += 1
                                    if bridge_count > 100: break
                                except: break
                            if bridge_count > 0:
                                logger.debug(f"📡 [UpdateTree] Bridged {bridge_count} external signals.")
                    except Exception as e:
                        logger.error(f"Signal bridging failed: {e}")

                    # ⭐ [FIX] 捕获当前 UI 的搜索条件，传递给后台进行实时过滤渲染
                    # 避免新行情进入时，主表格自动跳回全量列表，导致用户搜索失效
                    combined_query = getattr(self, '_last_value', "")
                    
                    # 🚀 [PERF] 提交最新的包到 pump_executor (1线程串行，保证快照顺序一致性)
                    latest_pkg = latest_p

                    self._is_processing_tree_data = True
                    self._last_processing_start_time = time.time()
                    
                    # if not hasattr(self, 'executor'):
                    #     from concurrent.futures import ThreadPoolExecutor
                    #     # ⭐ 保持 max_workers=1 确保任务按序执行，但通过跳帧减少排队总数
                    #     self.executor = ThreadPoolExecutor(max_workers=1)
                    
                    # 提交最新的包到 pump_executor (1线程串行，保证快照顺序一致性)
                    # [OPTIMIZE] 检查是否需要强制全量刷新 (例如搜索条件变化或手动触发)
                    force_val = getattr(self, '_force_full_sync_pending', False)
                    if force_val: self._force_full_sync_pending = False # 消费掉
                    
                    self.pump_executor.submit(self._process_tree_data_async, latest_pkg, sync_ui=True, query=combined_query, force=force_val)
                else:
                    # Check if subprocess is still alive
                    if hasattr(self, 'proc') and self.proc is not None:
                        if not self.proc.is_alive():
                            logger.error("🛑 Subprocess fetch_and_process is DEAD. Attempting to restart...")
                            self._start_process()

        except Exception as e:
            logger.error(f"Error starting tree update: {e}", exc_info=True)
            self._is_processing_tree_data = False
        finally:
            # Re-schedule next check
            self._schedule_after(5000, self.update_tree)

    def _process_tree_data_async(self, data_packet, sync_ui=True, query="", force=False):
        """
        [Pump Thread - Lightweight Orchestrator]
        严禁做任何 CPU 重计算。职责: 解包->净化->脏检查->过滤->排序->提交 compute。
        compute 结果由 _on_compute_done->pump 回流->_handle_compute_result 单点写 UI。
        """
        t_pump_start = time.time()
        try:
            # 1. 解包
            if isinstance(data_packet, dict):
                full_df   = data_packet.get('full_snapshot')
                df_raw    = data_packet.get('filtered_ui_data')
                snap_time = data_packet.get('timestamp', t_pump_start)
            else:
                full_df   = data_packet
                df_raw    = data_packet
                snap_time = t_pump_start

            # 2. 代码净化 (轻量)
            def _sanitize(d):
                if d is None: return None
                d = d.copy()
                if d.index.name == 'code': d.index.name = None
                if 'code' not in d.columns:
                    d['code'] = d.index.astype(str)
                if d['code'].dtype == 'object':
                    ext = d['code'].str.extract(r'(\d{6})')[0]
                    if ext.isna().any():
                        ext = ext.fillna(d['code'].str.extract(r'(\d+)')[0])
                    d['code'] = ext.fillna(d['code'])
                return d

            full_df = _sanitize(full_df)
            if full_df is None or full_df.empty:
                return

            # 3. 源数据脏检查 (轻量)
            p_col = next((c for c in ['close', 'trade', 'price', 'now'] if c in full_df.columns), None)
            df_hash = 0
            if p_col:
                n = len(full_df)
                idx = [0, n // 2, n - 1] if n > 2 else list(range(n))
                df_hash = hash(n) ^ hash(full_df[p_col].iloc[idx].sum())
            if not query and not force and getattr(self, '_last_processed_df_hash', -1) == df_hash:
                return
            self._last_processed_df_hash = df_hash

            # 4. 过滤/查询 (轻量)
            if query:
                from query_engine_util import query_engine
                try:
                    df = query_engine.execute(full_df, query)
                except Exception:
                    df = full_df
            else:
                df = _sanitize(df_raw) if df_raw is not None else full_df.copy()

            # 5. 排序 (轻量)
            cur_res = self.global_values.getkey("resample") or 'd'
            if df is not None and not df.empty:
                sort_col = getattr(self, 'sortby_col', None)
                if sort_col and sort_col in df.columns:
                    df = df.sort_values(by=sort_col, ascending=getattr(self, 'sortby_col_ascend', False))
                if 'resample' not in df.columns:
                    df['resample'] = cur_res

            # 6. Pump 延迟诊断
            pump_lag = time.time() - snap_time
            logger.info(f"[PumpLag] {pump_lag:.3f}s")
            if pump_lag > 1.0:
                logger.warning(f"[PumpLag] Slow pump: {pump_lag:.3f}s")

            # 7. Compute 风暴限流 (防止 compute_executor 队列爆炸)
            max_fl = getattr(self, '_compute_max_inflight', 5)
            if getattr(self, '_compute_inflight', 0) >= max_fl:
                logger.warning(f"[ComputeStorm] Backlog {self._compute_inflight}>={max_fl}, dropping")
                return

            # 8. 分配版本号 (进入 compute 前绑定，确保过期判断准确)
            self._snapshot_version = getattr(self, '_snapshot_version', 0) + 1
            version = self._snapshot_version
            self._compute_inflight = getattr(self, '_compute_inflight', 0) + 1

            # 9. 提交 CPU 重计算到 compute_executor
            fut = self.compute_executor.submit(
                self._run_compute_async,
                full_df.copy(),
                df.copy() if df is not None else None,
                sync_ui, cur_res, version, force
            )
            # callback 在 compute 线程执行 — 严禁直接触 UI，必须回流 pump
            fut.add_done_callback(lambda f, v=version, frc=force: self._on_compute_done(f, v, frc))

        except Exception as e:
            logger.exception(f"[Pump] Error in _process_tree_data_async: {e}")
        finally:
            # Pump 阶段完成，释放 processing 标志，允许 update_tree 提交下一帧
            self._is_processing_tree_data = False

    def _run_compute_async(self, full_df, df, sync_ui, cur_res, version, force=False):
        """
        [Compute Thread] CPU 重计算区。严禁直接操作 UI 或调用 _put_deduped_task。
        结果仅通过 return 值传递，由 _on_compute_done->pump->_handle_compute_result 写入 UI。
        """
        try:
            # 信号桥接 (跨进程事件转发到 SignalBus)
            try:
                from signal_bus import get_signal_bus
                bus = get_signal_bus()
                if hasattr(self, 'signal_bridge_queue'):
                    cnt = 0
                    while not self.signal_bridge_queue.empty():
                        try:
                            ev = self.signal_bridge_queue.get_nowait()
                            if ev:
                                bus.publish(
                                    event_type=getattr(ev, 'event_type', None) or getattr(ev, 'type', 'unknown'),
                                    source=f"{getattr(ev, 'source', 'unknown')} (bridged)",
                                    payload=getattr(ev, 'payload', {}),
                                    signal=getattr(ev, 'signal', None)
                                )
                                cnt += 1
                            if cnt > 100: break
                        except Exception: break
            except Exception: pass

            # 1. 情绪评分 (heavy)
            if hasattr(self, 'realtime_service') and self.realtime_service:
                try:
                    self.realtime_service.update_batch(full_df)
                    codes  = full_df['code'].tolist()
                    scores = self.realtime_service.get_emotion_scores(codes)
                    full_df['emotion_status'] = full_df['code'].map(scores).fillna(50).astype(int)
                except Exception as e:
                    logger.error(f"[Compute] Realtime sync error: {e}")

            # 2. 信号检测 (最重的 CPU 操作)
            try:
                full_df = detect_signals(full_df)
            except Exception as e:
                logger.error(f"[Compute] detect_signals failed: {e}")

            # 3. 将 full_df 增强列同步到 df 视图
            if df is not None and not df.empty:
                try:
                    df = full_df.loc[df.index.intersection(full_df.index)].copy()
                except Exception:
                    if 'emotion_status' in full_df.columns:
                        df['emotion_status'] = df['code'].map(
                            full_df.set_index('code')['emotion_status']
                        ).fillna(50)

            # 4. 策略引擎 (fire-and-forget, 内置节流)
            if not full_df.empty:
                self._run_live_strategy_process(full_df)

            return (full_df, df, sync_ui, cur_res, force)

        except Exception as e:
            logger.exception(f"[Compute] v{version} error: {e}")
            return None

    def _on_compute_done(self, fut, version, force=False):
        """
        [Compute Thread Callback] 严禁直接触 UI。
        通过 pump_executor.submit 强制回流，确保 UI 写入永远只有 pump 一个入口。
        """
        try:
            result = fut.result()
        except Exception as e:
            logger.error(f"[Compute] Future failed v{version}: {e}")
            self._compute_inflight = max(0, getattr(self, '_compute_inflight', 1) - 1)
            return

        if result is None:
            self._compute_inflight = max(0, getattr(self, '_compute_inflight', 1) - 1)
            return

        # 强制回流 pump — UI 单入口封口
        self.pump_executor.submit(self._handle_compute_result, result, version, force)

    def _handle_compute_result(self, result, version, force=False):
        """
        [Pump Thread] 版本检查 + 单点写 UI。
        tk_dispatch_queue 的唯一合法写入点。
        refresh_tree UI
        """
        self._compute_inflight = max(0, getattr(self, '_compute_inflight', 1) - 1)

        # [VERSION] Pump 层: 丢弃过期结果 (第一层防护)
        cur_ver = getattr(self, '_snapshot_version', 0)
        if version < cur_ver:
            logger.debug(f"[Version] Drop stale v{version} < v{cur_ver}")
            return

        try:
            full_df, df, sync_ui, cur_res, force_res = result
            # 这里的 force_res 优先级更高
            final_force = force or force_res
        except Exception as e:
            logger.error(f"[Pump] Unpack result failed v{version}: {e}")
            return

        # 单点写 UI (通过 Latest-Wins 聚合器)
        if df is not None:
            def _do_sync():
                # [VERSION] UI 层: 再次校验 (第二层防护)
                if version < getattr(self, '_snapshot_version', 0):
                    return
                self._apply_tree_data_sync(full_df, df if sync_ui else None, cur_res, final_force)
            self._is_ui_sync_pending = True
            self._put_deduped_task("main_ui_sync", _do_sync)
        elif full_df is not None and not full_df.empty:
            def _do_mem_sync():
                if version < getattr(self, '_snapshot_version', 0):
                    return
                self._apply_tree_data_sync(full_df, None, cur_res, final_force)
            self._is_ui_sync_pending = True
            self._put_deduped_task("main_ui_sync", _do_mem_sync)


    def _apply_tree_data_sync(self, full_df, ui_df=None, cur_res='d', force=False):
        """
        Sync step: update internal state and Tkinter UI on the main thread.
        - full_df: 全量市场行情 (用于 Top10/策略/信号追踪)
        - ui_df: 经过当前视图过滤后的数据 (用于主 Treeview 渲染)
        """
        now = time.time()
        has_update = False
        with timed_ctx("apply_tree_data_sync_timed", warn_ms=10000):
            try:
                # 1. [CORE] 更新主内存及其版本 (必须每轮执行)
                # 计算快照 Hash 用于版本校验，若数据完全无变动则跳过后续昂贵的 UI 渲染
                df_hash = 0
                if not full_df.empty:
                    # [OPTIMIZE] 哈希指纹改进：取 5 点价格采样，提高变动检测精度
                    p_col = next((c for c in ['close', 'trade', 'price', 'now'] if c in full_df.columns), None)
                    if p_col:
                        n = len(full_df)
                        sample_idx = [0, n // 4, n // 2, 3 * n // 4, n - 1] if n > 4 else list(range(n))
                        # 使用采样点的值元组计算哈希，比 sum() 更稳健
                        p_val_tuple = tuple(full_df[p_col].iloc[sample_idx].values)
                        df_hash = hash(n) ^ hash(p_val_tuple)
                    else:
                        df_hash = hash(full_df.index.size)
                
                last_hash = getattr(self, '_last_apply_df_hash', -1)
                
                if df_hash != last_hash:
                    has_update = True
                    # [OPTIMIZE] 仅在数据真实变动时，执行一次全量内存整合，提升后续索引速度
                    try:
                        full_df._consolidate_inplace()
                    except Exception: pass
                
                with self._df_lock:
                    self.df_all = full_df
                
                self._data_update_version = getattr(self, "_data_update_version", 0) + 1
                
                # [STABILITY] 极其重要的限流：如果数据毫无变动，且过滤条件未发生变化，且非强制刷新，直接跳回
                current_query = getattr(self, '_last_value', "")
                last_render_query = getattr(self, '_last_render_query', "")
                
                if df_hash == last_hash and current_query == last_render_query and not force:
                    # 30s 兜底保护，防止 UI 状态刷新失效
                    if now - getattr(self, '_last_tree_render_ts', 0) < 30.0:
                        return
                    # 否则进入 30s 兜底刷新
                
                self._last_render_query = current_query
                
                # ⭐ [RESTORE] 激活数据更新标志位 (确保下一步联动恢复能触发)
                if df_hash != last_hash:
                    has_update = True
                
                self._last_apply_df_hash = df_hash

                if hasattr(self, 'selector') and self.selector:
                    self.selector.df_all_realtime = self.df_all
                    self.selector.resample = cur_res

                # 2. [CORE-UI] 刷新主表格 (独立限流 + 忙碌守卫 + 存在校验)
                # ⭐ [OPTIMIZE] 如果 ui_df 为 None (主要见于中间包)，直接跳过耗时 3s 的 Treeview 刷新
                # 如果 ui_df 为空 DataFrame，则执行刷新以清空界面 (解决过滤为空不刷新问题)
                if ui_df is not None:
                    if (now - getattr(self, '_last_tree_render_ts', 0) > 0.5) and not getattr(self, '_is_gui_rendering', False):
                        self._is_gui_rendering = True
                        try:
                            # 1. 刷新主 Treeview (核心任务)
                            self.refresh_tree(ui_df)
                        finally:
                            self._is_gui_rendering = False
                        self._last_tree_render_ts = now
                else:
                    # 虽然不刷表格，也要更新状态条，代表“数据已到达内存”
                    pass
                
                # 将排行榜、板块联动面板、概念统计等非核心/非实时任务放入低频异步调度器
                def _low_freq_sync_tasks():
                    lt_now = time.time()
                    # ⭐ 异步任务同步频次限制在 1.5s 以上
                    if lt_now - getattr(self, '_last_low_freq_ts', 0) > 1.5:
                        self.update_all_top10_windows()
                        
                        # [OPTIMIZE] 将耗时的概念列表统计移至此处异步处理
                        if ui_df is not None and not ui_df.empty:
                            self.update_category_result(ui_df)
                            if hasattr(self, '_concept_detail_win') and self._concept_detail_win.winfo_exists():
                                 self._concept_detail_win.update_data(ui_df)

                        panel = getattr(self, "sector_bidding_panel", None)
                        if panel and panel.isVisible():
                            try:
                                panel.on_realtime_data_arrived(full_df.copy())  # [THREAD-SAFETY] copy() 防止子线程悬空指针
                            except Exception as e:
                                logger.error(f"Panel sync failed: {e}")

                        # ✅ [盘中交易引擎 v2] 直接从 BiddingMomentumDetector 完整注入
                        try:
                            _fc_last = getattr(self, '_focus_ctrl_last_inject', 0)
                            # [THROTTLE] 交易引擎注入间隔限制在 30s，且仅在快照更新时执行
                            if has_update and (lt_now - _fc_last >= duration_sleep_time):
                                from sector_focus_engine import get_focus_controller
                                fc = get_focus_controller()

                                # ① 注入基础行情表 (确保扫描引擎始终有底层数据支持)
                                fc.inject_realtime(full_df)

                                # ② 专家通道：从 BiddingMomentumDetector 注入分析结果 (零拷贝逻辑)
                                _sbp = getattr(self, 'sector_bidding_panel', None)
                                _detector = getattr(_sbp, 'detector', None) if _sbp else None
                                if _detector is not None:
                                    fc.inject_from_detector(_detector)

                                # ② 55188 外部数据（主力/题材/人气）
                                try:
                                    from scraper_55188 import get_cache_df as _55188_cache
                                    _ext_df = _55188_cache()
                                    if _ext_df is not None and not _ext_df.empty:
                                        fc.inject_ext_data(_ext_df)
                                except Exception: pass

                                # ③ 后台 Tick（板块热力确认+买点扫描+决策队列更新）
                                self.executor.submit(fc.tick)
                                self._focus_ctrl_last_inject = lt_now
                        except Exception as _fe:
                            logger.debug(f"[SectorFocusEngine] inject failed: {_fe}")

                        self._last_low_freq_ts = lt_now

                self._put_deduped_task("low_freq_ui_sync", _low_freq_sync_tasks)


                # ⭐ 交易 GUI 同步 (轻量级)
                if hasattr(self, '_trading_gui_qt6') and self._trading_gui_qt6:
                    self._trading_gui_qt6.df_all = self.df_all
                # 4. [HOUSEKEEPING] 窗口恢复与后台任务集中初始化
                if not hasattr(self, "_restore_done"):
                    self._restore_done = True
                    self._schedule_after(2000, self._batch_init_housekeeping)

                # 🧹 周期性手动 GC (根据反馈：按 50 次更新触发一次，降低卡顿)
                if not hasattr(self, '_update_count'): self._update_count = 0
                self._update_count += 1
                if self._update_count % 50 == 0:
                    gc.collect()
                    logger.debug(f"🧹 [GC] Periodical cycle triggered at update #{self._update_count}")
                    
                # [THROTTLE] 策略检查已移至后台分析 worker
    
                # 6. [STATS] 计算全盘统计概览 (增加 3s 级限流)
                if now - getattr(self, '_last_aggregate_ts', 0) > 3.0:
                    self._aggregate_market_dashboard_stats(has_update)
                    self._last_aggregate_ts = now

                # ----------------- 竞价/尾盘异动自动弹窗 ----------------- #
                if has_update:
                    now_hm = cct.get_now_time_int()
                    # 🚀 [MERGED] 整合并扩展自动开启逻辑
                    # 1. 判定时间窗口：09:10 (竞价前夕) 到 15:05 (收盘整理期)
                    # 2. 判定启动防抖：程序运行需超过 20 秒，避免启动初期瞬间弹出导致的卡顿
                    is_auto_window = (915 <= now_hm <= 1505)
                    is_ready_auto = (time.time() - self._init_start_time > 20)
                    
                    if is_auto_window and is_ready_auto and (not hasattr(self, "sector_bidding_panel") or self.sector_bidding_panel is None):
                        from sector_bidding_panel import SectorBiddingPanel
                        if not hasattr(self, "sector_bidding_panel") or self.sector_bidding_panel is None:
                            self.sector_bidding_panel = SectorBiddingPanel(main_window=self)
                            self.sector_bidding_panel.show()
                            if hasattr(self, 'df_all') and not self.df_all.empty:
                                self.sector_bidding_panel.on_realtime_data_arrived(self.df_all.copy(), force_update=True)
                            logger.info("📡 [Sync] 已自动弹出 竞价/尾盘联动监控面板(Tick订阅版)")

            except Exception as e:
                logger.error(f"Error applying tree data: {e}", exc_info=True)
            finally:
                # 🛡️ [CORE] UI 同步完成，彻底释放流水线信号，允许 update_tree 进入下一轮
                self._is_ui_sync_pending = False
                # self._is_processing_tree_data = False # 已在 _process_tree_data_async 的 finally 中处理

                if has_update:
                    if getattr(self, '_last_resample', None) != self.global_values.getkey("resample"):
                        if  hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
                            if hasattr(self, 'df_ui_prev'):
                                del self.df_ui_prev
                            self._last_resample = self.global_values.getkey("resample")
                            self._df_first_send_done = False
                            
                            if getattr(self, 'last_vis_var_status', None) is not None:
                                self.vis_var.set(self.last_vis_var_status)
                                self._vis_enabled_cache = self.last_vis_var_status # 同步至后台缓存
                                self.last_vis_var_status = None
                                logger.info(f"✅ [Restore] has_update triggered restoration to {self.vis_var.get()}")
                    # -------------------------
                    self.status_var2.set(f'queue update: {self.format_next_time()}')
                    logger.debug(f'queue update: {self.format_next_time()}')
                    # 打印性能统计摘要
                    # cct.print_timing_summary()

    def _batch_init_housekeeping(self):
        """[OPTIMIZE] 集中处理后台常驻任务的初始化，减少主线程计时器碎片"""
        self.restore_all_monitor_windows()
        self._schedule_after(3000, self._start_feedback_listener)
        self._schedule_after(8000, self._check_ext_data_update)
        self._schedule_after(28000, self.KLineMonitor_init)
        self._schedule_after(58000, self.schedule_15_30_job)

    def _aggregate_market_dashboard_stats(self, has_update: bool):
        """[EXTRA] 计算全盘统计概览 (上涨/下跌/指数/温度)，通过主线程分步执行或线程池"""
        if getattr(self, '_is_closing', False):
            return
            
        # 预先导入，避免线程内 import 触发 GIL 异常
        try:
            from market_pulse_engine import DailyPulseEngine
            from JSONData import sina_data
        except ImportError:
            return

        try:
            dashboard = getattr(self, '_signal_dashboard_win', None)
            racing = getattr(self, '_racing_panel_win', None)
            now = time.time()
            
            # Throttling: 实时同步每 60 秒一次，或看板/赛马首次打开时强制同步
            trigger_dash = dashboard and not getattr(self, '_dashboard_first_sync_done', False)
            trigger_racing = racing and not getattr(self, '_racing_first_sync_done', False)
            trigger_time = (now - getattr(self, '_last_dashboard_sync_ts', 0) > 60)
            
            if trigger_dash or trigger_racing or trigger_time:
                self._last_dashboard_sync_ts = now
                if dashboard: self._dashboard_first_sync_done = True
                if racing: self._racing_first_sync_done = True
                
                def _async_stats_aggregation():
                    try:
                        from market_pulse_engine import DailyPulseEngine
                        from JSONData import sina_data
                        import numpy as np
                        import traceback
                        
                        df = self.df_all.copy() if hasattr(self, 'df_all') else None
                        if df is None or df.empty: return
                        
                        up_count = down_count = flat_count = vol_down = vol_up = 0
                        vol_up_details = []
                        ready_pct = 0
                        breadth_data = {'up_ratio': 0.5}
                        
                        if 'trade' in df.columns and 'lastp1d' in df.columns:
                            trade, lastp = df['trade'].values, df['lastp1d'].values
                            diff = trade - lastp
                            up_count = int((diff > 0).sum())
                            down_count = int((diff < 0).sum())
                            flat_count = int((diff == 0).sum())

                            if 'vol' in df.columns and 'lastv1d' in df.columns:
                                vol, lastv = df['vol'].values, df['lastv1d'].values
                                with np.errstate(divide='ignore', invalid='ignore'):
                                    vr = np.where(lastv > 0, vol / lastv, 0.0)
                                vol_mask = (vr > 1.5) & (diff > 0)
                                vol_up = int(vol_mask.sum())
                                vol_down = int((vr < 0.8).sum())
                                if vol_mask.any():
                                    sub_df = df[vol_mask].head(30)
                                    for idx, row in sub_df.iterrows():
                                        chg = row.get('ratio', 0)
                                        if chg == 0 and 'trade' in row and 'lastp1d' in row and row['lastp1d'] != 0:
                                            chg = (row['trade'] - row['lastp1d']) / row['lastp1d'] * 100
                                        vol_up_details.append({
                                            "code": str(idx), "name": str(row.get('name', '')),
                                            "change": float(chg), "ratio": float(vr[df.index.get_loc(idx)])
                                        })
                            
                            if 'score' in df.columns:
                                scanned_df = df[df['score'] > 0]
                                if not scanned_df.empty:
                                    sample_count = len(scanned_df)
                                    ready_pct = (scanned_df['score'] > 85).mean() * 100
                                    if sample_count < 20: ready_pct = ready_pct * (sample_count / 20)
                            
                            breadth_data = {'up_ratio': up_count / (up_count + down_count + flat_count) if (up_count + down_count + flat_count) > 0 else 0.5}

                        # 2. 指数行情
                        indices_data = []
                        idx_codes = ["000001", "399001", "399006", "000688"]
                        try:
                            idf = sina_data.Sina().get_stock_list_data(idx_codes, index=True)
                            if idf is not None and not idf.empty:
                                nm_map = {"000001": "上证", "999999": "上证", "399001": "深证", "399006": "创业", "999688": "科创", "999312": "科创"}
                                for c, r in idf.iterrows():
                                    p = round((r.now-r.llastp)/r.llastp*100, 2) if r.llastp > 0 else 0.0
                                    indices_data.append({'name': nm_map.get(str(c), str(c)), 'percent': p})
                                self._cached_indices_data = indices_data
                        except:
                            indices_data = getattr(self, '_cached_indices_data', [])

                        top5 = getattr(self, 'concept_top5', None)
                        sector_heat = 0
                        if top5 is not None:
                            try:
                                if isinstance(top5, list):
                                    pcts = [float(item[1]) for item in top5[:5] if len(item) > 1]
                                elif isinstance(top5, pd.DataFrame):
                                    pcts = top5['percent'].head(5).tolist() if 'percent' in top5.columns else []
                                if pcts: sector_heat = sum(pcts) / len(pcts)
                            except: pass

                        temp, summary = DailyPulseEngine.calculate_professional_temperature(
                            ready_pct=ready_pct, sector_heat=sector_heat, breadth=breadth_data, indices=indices_data
                        )
                        self._cached_market_temp = temp
                        self._cached_market_summary = summary

                        ls_ratio = round(up_count / down_count, 2) if down_count > 0 else float(up_count) if up_count > 0 else 1.0
                        
                        final_stats = {
                            "up": up_count, "down": down_count, "flat": flat_count, "ls_ratio": ls_ratio,
                            "vol_down": vol_down, "vol_up": vol_up, "vol_details": vol_up_details,
                            "temperature": temp, "summary": summary, "indices": indices_data, "breadth": breadth_data
                        }
                        
                        if dashboard:
                            self.tk_dispatch_queue.put(lambda s=final_stats: self._signal_dashboard_win.update_market_stats(s))
                            
                        # [NEW] 将处理好的温度指数数据挂载到竞价赛马监控
                        racing_panel = getattr(self, '_racing_panel_win', None)
                        if racing_panel and hasattr(racing_panel, 'update_market_stats'):
                            self.tk_dispatch_queue.put(lambda s=final_stats: racing_panel.update_market_stats(s))
                        
                        try:
                            # [NEW] 将指数数据注入交易决策引擎，支持逆势策略计算
                            from sector_focus_engine import get_focus_controller
                            ctrl = get_focus_controller()
                            if ctrl:
                                ctrl.inject_market_indices(indices_data)
                                
                            from signal_bus import get_signal_bus, SignalBus
                            get_signal_bus().publish(SignalBus.EVENT_HEARTBEAT, "market_stats", final_stats)
                        except: pass
                        
                    except Exception as e:
                        logger.error(f"Async stats aggregation failed: {e}")
                
                if hasattr(self, 'executor'):
                    self.executor.submit(_async_stats_aggregation)
                else:
                    threading.Thread(target=_async_stats_aggregation, daemon=True).start()
        except:
            pass



    def open_visualizer(self, code, timestamp=None):
        """🚀 [ROOT-FIX] 智能联动：优先现有进程，支持 Socket 兜底，彻底解决切换假死与端口冲突"""
        # 🚀 [FIX] 增加 vis_var 状态检测，全局决定是否允许联动开启/透传
        if hasattr(self, 'vis_var') and not self.vis_var.get():
            return
            
        logger.debug(f"🚀 [Visualizer] Request: {code} (Linkage: {timestamp is not None})")
        if code != getattr(self, 'select_code', None):
            self.select_code = code
        # =========================
        # 0. 基础过滤（UI线程安全）
        # =========================
        if not code:
            return

        now = time.time()
        is_linkage = timestamp is not None

        # [UPGRADE] 只有手动点击才同步触发外部软件联动，后台自动信号增加 2s 防抖保护
        self.sender.send(code, auto=is_linkage)

        # =========================
        # 1. 联动去重（严格）
        # =========================
        if is_linkage:
            link_key = (str(code), str(timestamp))
            if getattr(self, '_last_linkage_data', None) == link_key:
                return
            self._last_linkage_data = link_key

        # =========================
        # 2. 普通选择去重与防抖
        # =========================
        if not is_linkage:
            if self.vis_select_code == code:
                # 如果代码没变，尝试检查周期是否变动
                try:
                    res_cur = self.resample_combo.get()
                    if getattr(self, '_last_resample', None) == res_cur:
                        return
                except: pass
                
            self.vis_select_code = code

            if (self._last_visualizer_code == code and
                (now - self._last_visualizer_time) < getattr(self, '_visualizer_debounce_sec', 0.5)):
                return

            self._last_visualizer_code = code
            self._last_visualizer_time = now

        # =========================
        # 3. UI参数读取（主线程安全）
        # =========================
        resample_now = 'd'
        try:
            resample_now = self.resample_combo.get() if hasattr(self, 'resample_combo') else 'd'
            self._last_resample = resample_now
        except Exception:
            resample_now = 'd'

        # =========================
        # 4. Worker 线程（跨线程 IPC，不阻塞 UI）
        # =========================
        def _worker(code, timestamp, resample):

            def try_queue_send():
                """优先尝试本程序持有的托管进程管道"""
                try:
                    # 检查进程句柄是否存在且存活
                    if hasattr(self, 'qt_process') and self.qt_process and self.qt_process.is_alive():
                        payload = {
                            'code': code,
                            'resample': resample,
                            'timestamp': timestamp
                        }
                        # 使用现有的 _async_viz_send 进入指令队列
                        if is_linkage:
                            self._async_viz_send('TIME_LINK', payload)
                        else:
                            self._async_viz_send('SWITCH_CODE', payload)
                        return True
                except Exception as e:
                    logger.error(f"[IPC][QUEUE] failed: {e}")
                return False

            def try_socket_send():
                """兜底尝试 Socket 通道 (处理外部启动的可视化器或残留进程)"""
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.3) # 极短超时，防止 UI 卡滞感
                        s.connect(('127.0.0.1', 26668)) # 标准监听端口

                        if is_linkage:
                            msg = f"TIME_LINK|{code}|{timestamp}|resample={resample}"
                        else:
                            msg = f"CODE|{code}|resample={resample}"

                        s.send(msg.encode("utf-8"))
                        logger.debug(f"✅ [IPC][SOCKET] Command sent via fallback port 26668: {msg[:40]}...")
                        return True
                except (ConnectionRefusedError, socket.timeout, OSError) as e:
                    logger.debug(f"[IPC][SOCKET] port 26668 connection failed: {e}")
                except Exception as e:
                    logger.error(f"[IPC][SOCKET] unexpected: {e}")
                return False

            try:
                # P1: 尝试托管 Queue
                if try_queue_send():
                    return

                # P2: 尝试独立 Socket
                # 这解决了 "Listening 被占用" 但本程序认为进程已死的情况
                if try_socket_send():
                    return

                # P3: 都不行，启动进程
                logger.info(f"📡 No active visualizer detected via Pipe/Socket. Starting new process for {code}...")
                # 🚀 [FIX] 禁止在子线程中调用 mp.Process.start()。
                # 通过 after(0) 将启动指令调度回主线程执行，彻底根治 Fatal Python error: PyEval_RestoreThread 崩溃。
                self.after(0, lambda: self._start_visualizer_process(code, resample))
                
            except Exception as e:
                logger.error(f"[WORKER] open_visualizer fatal error: {e}")
                traceback.print_exc()

        # 启动后台守护线程
        threading.Thread(
            target=_worker,
            args=(code, timestamp, resample_now),
            daemon=True,
            name="OpenVisWorker"
        ).start()

        # UI 状态提示
        try:
            if hasattr(self, 'status_var2'):
                self.status_var2.set(f"🚀 可视化指令已发出: {code}")
        except: pass

    def _ui_heartbeat(self):
        """[CORRECTION 2] UI线程主心跳，每100ms跳动一次"""
        self._last_ui_heartbeat = time.time()
        if not getattr(self, "_is_closing", False):
            self.after(100, self._ui_heartbeat)

    def _start_watchdog(self):
        """[CORRECTION 2] 独立守护线程检测 UI 假死"""
        def watchdog_loop():
            self._last_ui_heartbeat = time.time()
            already_warned = False
            
            logger.info("📡 Diagnostic Watchdog active (Threshold: 2.0s).")
            while not getattr(self, "_is_closing", False):
                time.sleep(0.5)
                delay = time.time() - getattr(self, "_last_ui_heartbeat", 0)
                
                if delay > 5:
                    if not already_warned:
                        q_size = -1
                        try:
                            if hasattr(self, 'queue') and self.queue:
                                q_size = self.queue.qsize()  # 获取积压深度
                        except: pass
                        
                        logger.warning(f"🚨 [UI_BLOCK] 主线程假死检测! 延迟: {delay:.2f}s | Queue积压: {q_size if q_size >= 0 else 'N/A'}")
                        # 🧬 [NEW] 联动自动画像审计：同步输出最近周期的 Top 10 耗时任务
                        # self.show_ui_performance_audit(reset=False)
                        
                        # 🚀 [PERF] 增加 30s 冷却，防止 dump 本身加剧卡顿
                        last_dump = getattr(self, '_last_watchdog_dump_ts', 0)
                        if time.time() - last_dump > 30:
                            self._dump_ui_stack()
                            self._last_watchdog_dump_ts = time.time()
                            
                        already_warned = True

                else:
                    if already_warned:
                        logger.debug(f"✅ [UI_RECOVER] 主线程已恢复响应. 曾阻塞: {delay:.2f}s")
                    already_warned = False # 恢复后重置标志
            logger.info("📡 Diagnostic Watchdog exited.")
            
        t = threading.Thread(target=watchdog_loop, name="GuardDog", daemon=True)
        t.start()

    def _dump_ui_stack(self):
        """[ENGINEERING] 诊断主线程阻塞。在极端生产环境下，faulthandler 可能会干扰 GIL，需谨慎使用。"""
        # 🛡️ 增加更严苛的触发条件：仅在明确开启深度调试模式时执行堆栈导出
        if not getattr(self, "_debug_mode", False) or not os.environ.get("APP_DEBUG_FULL"):
            return
            
        try:
            import faulthandler
            import io
            # [🚀 NEW] 尝试捕获到缓冲区而非直接 stderr，降低对 C 层 IO 的直接冲击
            output = io.StringIO()
            faulthandler.dump_traceback(file=output)
            logger.warning(f"🧵 [ThreadDump] Detected UI Block Stack:\n{output.getvalue()}")
        except Exception as e:
            logger.error(f"[DumpStack] Failed to dump stack safety: {e}")

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
            send_code_via_pipe(payload, logger=logger)   # 假设你用 multiprocessing.Pipe
            # 或者 self.queue.put(stock_info)  # 如果是队列
            # 或者 send_code_to_other_window(stock_info) # 如果是 WM_COPYDATA
            logger.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            logger.error(f"推送 stock_info 出错: {e} {row}")
            return False

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
            stock_info = self.tree.item(selected_item[0], 'values')
            stock_code = stock_info[0]
            stock_name = stock_info[1]

            send_tdx_Key = (self.select_code != stock_code)
            self.select_code = stock_code

            stock_code = str(stock_code).zfill(6)
            logger.debug(f'stock_code:{stock_code}')
            # logger.info(f"选中股票代码: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                self.open_visualizer(stock_code)

            # if self.voice_var.get():
            if self.tip_var.get():
                # =========================
                # ✅ 构造 fake mouse event
                # =========================
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
                    self.on_tree_click_for_tooltip(fake_event,stock_code,stock_name)

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
        self.tip_var = tk.BooleanVar(value=False)
        self.voice_var = tk.BooleanVar(value=True) # 💥 默认开启语音
        self.realtime_var = tk.BooleanVar(value=True)
        self.vis_var = tk.BooleanVar(value=False)
        # [FIX] 绑定监听以同步影子变量，防止后台线程直接调用 .get() 导致 GIL 崩溃
        self.vis_var.trace_add('write', lambda *args: setattr(self, '_vis_enabled_cache', self.vis_var.get()))
        self.alert_popup_var = tk.BooleanVar(value=True) # 💥 默认开启报警弹窗
        checkbuttons_info = [
            ("Win", self.win_var),
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var),
            ("Tip", self.tip_var),
            ("Real", self.realtime_var),
            ("Vis", self.vis_var)
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

        ttk.Checkbutton(
            frame_right,
            text="Vo",
            variable=self.voice_var,
            command=self.on_voice_toggle
        ).pack(side=tk.LEFT, padx=1)

        ttk.Checkbutton(
            frame_right,
            text="Pop",
            variable=self.alert_popup_var,
            command=self.save_ui_states # 实时保存状态
        ).pack(side=tk.LEFT, padx=1)

        ttk.Button(
            frame_right,
            text="📊", 
            width=3,
            command=lambda: self.open_visualizer(getattr(self, 'select_code', None))
        ).pack(side=tk.LEFT, padx=1)

        # ttk.Button(
        #     frame_right,
        #     text="策略", 
        #     width=5,
        #     command=self.open_strategy_scan
        # ).pack(side=tk.LEFT, padx=1)

        # ttk.Button(
        #     frame_right,
        #     text="竞价🚀",
        #     width=6,
        #     command=self.open_sector_bidding_panel
        # ).pack(side=tk.LEFT, padx=1)

        # Initialize persisted variables that are not bound to main UI buttons immediately
        self.force_d_cycle_var = tk.BooleanVar(value=True)

        # Load persisted states
        self.load_ui_states()
        
        # ⚡ [NEW] 加载完状态后，强制同步一次语音引擎状态 (防止 UI 为 False 但后台引擎默认为 True)
        self.on_voice_toggle()
        
        # Apply strict linkage immediately
        self._schedule_after(100, self.update_linkage_status)

    def open_sector_bidding_panel(self):
        """手动打开竞价/尾盘板块联动监控面板"""
        # [🚀 防抖保护] 避免由于快速重复开关导致的 Qt 资源竞争与 GIL 崩溃 (2s 阈值)
        now = time.time()
        last_action = getattr(self, '_last_sector_bidding_action_t', 0)
        if now - last_action < 2.0:
            logger.warning("📡 [SectorBidding] 操作太频繁（防抖中），请稍候...")
            toast_message(self, "📡 操作太频繁，请稍候...")
            return
        self._last_sector_bidding_action_t = now

        try:
            if not hasattr(self, 'sector_bidding_panel') or self.sector_bidding_panel is None:
                from sector_bidding_panel import SectorBiddingPanel
                self.sector_bidding_panel = SectorBiddingPanel(main_window=self)
                logger.info("📡 手动打开 竞价/尾盘联动监控面板(Tick订阅版)")
            if self.sector_bidding_panel.isVisible():
                self.sector_bidding_panel.raise_()
            else:
                self.sector_bidding_panel.show()
            # 立即推一次数据以初始化订阅
            if hasattr(self, 'df_all') and not self.df_all.empty:
                self.sector_bidding_panel.on_realtime_data_arrived(self.df_all.copy(), force_update=True)  # [THREAD-SAFETY] copy() 防止子线程悬空指针
        except Exception as e:
            logger.error(f"打开竞价监控面板失败: {e}")
            import traceback
            traceback.print_exc()

    def open_strategy_scan(self):
        """一键打开策略扫描"""
        # 1. 确保 Visualizer 启动 (传入当前选中代码或 None)
        code = getattr(self, 'select_code', '000001')
        # 如果未启动则启动，如果已启动则无副作用 (除了 debounce)
        self.open_visualizer(code)

        # 2. 发送扫描指令
        # open_visualizer 会初始化 viz_command_queue
        if hasattr(self, 'viz_conn') and self.viz_conn:
             # [FIX] 🐞 异步发送指令，防止 UI 在 Pipe 缓冲区满时卡死
             threading.Thread(target=lambda: self.viz_conn[0].send(('CMD_SCAN_CONSOLIDATION', {})), daemon=True).start()
             logger.info("Async sent CMD_SCAN_CONSOLIDATION to Visualizer")
             if hasattr(self, 'status_var'):
                self.status_var.set("已发送策略扫描指令...")
             
             # 提示用户
             # toast_message(self, "已触发策略扫描，请查看可视化窗口", duration=2000)

    def load_ui_states(self):
        """加载UI状态"""
        try:
            if not os.path.exists(WINDOW_CONFIG_FILE):
                return
            
            with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            ui_state = config.get('ui_persistence', {})
            if not ui_state:
                return

            # Variable Name -> (Attribute Name, Type Converter)
            vars_config = {
                'win_var': ('win_var', bool),
                'tdx_var': ('tdx_var', bool),
                'ths_var': ('ths_var', bool),
                'dfcf_var': ('dfcf_var', bool),
                'tip_var': ('tip_var', bool),
                'voice_var': ('voice_var', bool),
                'realtime_var': ('realtime_var', bool),
                'vis_var': ('vis_var', bool),
                'force_d_cycle_var': ('force_d_cycle_var', bool),
                'alert_popup_var': ('alert_popup_var', bool),
                'search_var1': ('search_var1', str),
                'search_var2': ('search_var2', str),
                'st_key_sort_value': ('st_key_sort_value', str)
            }
            
            for key, (attr_name, type_func) in vars_config.items():
                if key in ui_state:
                    var = getattr(self, attr_name, None)
                    if var:
                        try:
                            val = type_func(ui_state[key])
                            var.set(val)
                        except Exception as e:
                            logger.warning(f"Failed to load {key}: {e}")

            # [NEW] 恢复主 Treeview 排序列和排序方向
            saved_sort_col = ui_state.get('sortby_col', None)
            saved_sort_asc = ui_state.get('sortby_col_ascend', None)
            if saved_sort_col is not None and saved_sort_asc is not None:
                self.sortby_col = saved_sort_col
                self.sortby_col_ascend = bool(saved_sort_asc)
                logger.info(f"Restored sort state: col={self.sortby_col}, ascending={self.sortby_col_ascend}")

            logger.info(f"UI states loaded: {len(ui_state)} items")

        except Exception as e:
            logger.error(f"Error loading UI states: {e}")

    def save_ui_states(self):
        """保存UI状态"""
        try:
            config = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                try:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except:
                    pass
            
            if 'ui_persistence' not in config:
                config['ui_persistence'] = {}
            
            # Variables to save
            save_list = [
                'win_var', 'tdx_var', 'ths_var', 'dfcf_var', 
                'tip_var', 'voice_var', 'realtime_var', 'vis_var',
                'force_d_cycle_var', 'alert_popup_var', 'search_var1', 'search_var2',
                'st_key_sort_value'
            ]
            
            for name in save_list:
                var = getattr(self, name, None)
                if var:
                    try:
                        config['ui_persistence'][name] = var.get()
                    except:
                        pass

            # [NEW] 保存主 Treeview 排序列和排序方向
            config['ui_persistence']['sortby_col'] = self.sortby_col
            config['ui_persistence']['sortby_col_ascend'] = self.sortby_col_ascend
            logger.info(f"Saving sort state: col={self.sortby_col}, ascending={self.sortby_col_ascend}")

            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            logger.info("UI states saved.")

        except Exception as e:
            logger.error(f"Error saving UI states: {e}")


    # def _on_clipboard_code_visualizer(self, stock_code):
        
    #     self._schedule_after(0, lambda: self._handle_clipboard_code_visualizer(stock_code))
    def _on_clipboard_code_visualizer(self, stock_code):
        try:
            if stock_code == getattr(self, "_last_clip_code", None):
                return
            self._last_clip_code = stock_code

            if self.tk_dispatch_queue.qsize() > 200:
                return

            self.tk_dispatch_queue.put(
                lambda c=stock_code: self._handle_clipboard_code_visualizer(c)
            )

        except Exception as e:
            logger.error(f"enqueue clipboard task error: {e}")

    def _handle_clipboard_code_visualizer(self, stock_code):

        if not hasattr(self, 'vis_var'):
            return

        self.select_code = stock_code

        if self.vis_var.get() and stock_code:
            self.open_visualizer(stock_code)

    # def _handle_clipboard_code_visualizer(self, stock_code):

    #     self.select_code = stock_code

    #     if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
    #         self.open_visualizer(stock_code)

    def link_to_visualizer(self, code, timestamp):
        """🚀 [SIMPLIFIED] 跨工具联动接口：仅传日期"""
        if not code or not timestamp:
            return
        # 🚀 [FIX] 增加 vis_var 状态检测，全局决定是否允许联动开启/透传
        if hasattr(self, 'vis_var') and not self.vis_var.get():
            return
        # ⭐ [THROTTLE] 联动限流：避免 1s 内对同一只股票重复发送联动 (由于 T80 及策略震荡可能触发多次)
        now = time.time()
        throttle_key = f"link_{code}"
        if hasattr(self, '_viz_link_throttle'):
            last_t = self._viz_link_throttle.get(throttle_key, 0)
            if now - last_t < 1.0: # 1秒冷却
                return
        else:
            self._viz_link_throttle = {}
        
        self._viz_link_throttle[throttle_key] = now
        
        # 如果可视化尚未打开，则尝试开启
        if not (hasattr(self, 'qt_process') and self.qt_process and self.qt_process.is_alive()):
                self.open_visualizer(code, timestamp=timestamp)
        else:
            # 已打开，直接通过 IPC 发送联动指令
            self.open_visualizer(code, timestamp=timestamp)

    def start_qt_async(self, code, resample):
        if getattr(self, "_qt_starting", False):
            return

        self._qt_starting = True

        # 🚀 [FIX] 彻底根治 Fatal Python error: PyEval_RestoreThread。
        # 禁止在子线程中执行 mp.Process.start()。
        # 回退至主线程执行，并通过 after 延时给 UI 留出响应空间。
        self.after(200, lambda: self._start_visualizer_process(code, resample))

    def _start_visualizer_process(self, code, resample=None):
        """核心方法：启动 Qt 可视化进程 (支持跨线程调用，自动调度至主线程)"""
        start_t = time.time()
        try:
            # 🛡️ [GUARD] 强制主线程校验，确保 mp.Process.start() 的稳定性
            if not threading.current_thread() is threading.main_thread():
                logger.warning("⚠️ [Visualizer] Detected call from non-main thread. Re-dispatching...")
                self.after(0, lambda: self._start_visualizer_process(code, resample))
                return

            if resample is None:
                resample = self.resample_combo.get() if hasattr(self, 'resample_combo') else 'd'
            
            # 初始化指令 Pipe
            if not hasattr(self, 'viz_conn') or self.viz_conn is None:
                self.viz_conn = mp.Pipe()
            
            # [FIX] 每次启动前强制重置生命周期标志为 True (防止上次退出残留 False)
            if hasattr(self, 'viz_lifecycle_flag'):
                self.viz_lifecycle_flag.value = True
                logger.debug(f"[Visualizer] Resetting viz_lifecycle_flag to True.")
            
            # 启动进程：传入 code|resample, stop_flag, log_level, debug, conn
            initial_payload = f"{code}|resample={resample}"
            
            import_start = time.time()
            import trade_visualizer_qt6 as qtviz
            logger.debug(f"[Visualizer] Import trade_visualizer_qt6 cost {(time.time() - import_start)*1000:.1f}ms")
            
            launch_start = time.time()
            self.qt_process = mp.Process(
                target=qtviz.main, 
                args=(initial_payload, self.viz_lifecycle_flag, self.log_level , False, self.viz_conn[1]), 
                daemon=False
            )
            self.qt_process.start()
            logger.info(f"[Visualizer] Launched QT process cost {(time.time() - launch_start)*1000:.1f}ms for {initial_payload}")
            
            if hasattr(self, '_df_first_send_done'):
                self._df_first_send_done = False
                
            # 启动/确认同步线程
            thread_start = time.time()
            if not hasattr(self, '_df_sync_thread') or not self._df_sync_thread.is_alive():
                self._df_sync_running = True # ⭐ [FIX] 确保在启动线程前设置运行标志
                self._df_sync_thread = threading.Thread(target=self.send_df, daemon=True)
                self._df_sync_thread.start()
                logger.debug(f"[Visualizer] df_sync_thread start cost {(time.time() - thread_start)*1000:.1f}ms")
            
            logger.debug(f"✅ [Visualizer] Full startup sequence finished in {(time.time() - start_t)*1000:.1f}ms")

        except Exception as e:
            logger.error(f"Failed to start Qt visualizer: {e}")
            traceback.print_exc()
        finally:
            # ⚡ [FIX] 无论成功失败，必须重置启动锁，否则下一次启动将永久失效
            self._qt_starting = False

    def send_df(self, initial=True):
        """同步数据推送核心逻辑 (作为类方法，支持跨线程唤醒)"""
        # [THREAD-SAFETY] 确保同一时间只有一个同步实例在跑
        if not self._send_sync_lock.acquire(blocking=False):
            logger.debug("[send_df] Another sync loop is already running. Exiting redundant thread.")
            return
        try:
            ipc_host, ipc_port = '127.0.0.1', 26668
            last_send_time = 0
            min_interval = 0.8  # ✅ [OPTIMIZE] 提高发送间隔到 800ms，减少 GIL 竞争
            max_jitter = 0.2    # 随机抖动
            logger.info(f"[send_df] Thread START, running={getattr(self,'_df_sync_running',False)}")
            count = 0
            self._cold_start = True # ⭐ [NEW] 冷启动标志
            
            while self._df_sync_running:
                vis_enabled = getattr(self, '_vis_enabled_cache', True)
                
                # ⭐ 核心判断：是否需要跳过本轮同步（没开且无强制请求）
                if not vis_enabled and not getattr(self, '_force_full_sync_pending', False):
                    # ⭐ 小步等待 + 可中断（避免长sleep卡响应）
                    for _ in range(10):  # 最多等2秒
                        if getattr(self, '_vis_enabled_cache', True):
                            break
                        time.sleep(0.2)
                    else:
                        continue

                # 📥 [OPTIMIZE] 非工作时间且已完成初始同步，且没有强制同步请求时，则停止自动发送
                if not cct.get_work_time() and getattr(self, '_df_first_send_done', False) \
                and not getattr(self, '_force_full_sync_pending', False):
                    time.sleep(10)
                    continue

                if not hasattr(self, 'df_all') or self.df_all.empty:
                    logger.debug("[send_df] df_all is empty or missing, waiting...")
                    if count < 3:
                        count +=1
                        time.sleep(2)
                        continue
                sent = False  # ⭐ 本轮是否成功发送
                try:
                    now = time.time()
                    
                    # 动态调整发送频率：数据量越大，发送越稀疏，防止 GIL 挤占
                    if not hasattr(self, 'df_all'): 
                        time.sleep(2)
                        continue
                    
                    n_rows = len(self.df_all) if hasattr(self, 'df_all') else 0
                    dynamic_interval = min_interval
                    if n_rows > 3000: dynamic_interval = 2.5
                    if n_rows > 5000: dynamic_interval = 5.0
                    
                    # ⭐ 限流 + 抖动
                    if now - last_send_time < dynamic_interval:
                        time.sleep(1.0) # 小碎步休眠防止 CPU 100%
                        continue
                    
                    last_send_time = time.time()

                    # 🔄 [PERF] 架构重构：send_df 改为从 MarketStateBus 拉取最新全量快照
                    # 彻底消除 send_df 线程在 Queue 上的竞争与主线程锁 (_df_lock) 竞争
                    bus_data = self.market_bus.get_latest(since_version=getattr(self, '_last_vis_bus_version', 0))
                    
                    if bus_data is None:
                        # 检查是否有强制同步请求，如果没有则继续休眠
                        if not getattr(self, '_force_full_sync_pending', False):
                            time.sleep(0.5)
                            continue
                        # 如果有强制同步请求，拉取当前总线最新数据（无论版本）
                        bus_data = (self.market_bus._version, self.market_bus._df_all, self.market_bus._df_filtered, self.market_bus._timestamp)

                    version, df_bus_all, _, snap_time = bus_data
                    self._last_vis_bus_version = version
                    
                    if df_bus_all is None or df_bus_all.empty:
                        time.sleep(0.5)
                        continue

                    # ⚡ [CORE] 采用总线快照进行可视化分发
                    df_ui = df_bus_all
                    df_hash = hash(version) # 使用总线版本作为哈希

                    
                    # 🚀 [FIX 2] 哈希门控：命中直接跳出昂贵的 compare 逻辑
                    if getattr(self, "_df_first_send_done", False) and getattr(self, "_last_send_df_hash", None) == df_hash and not getattr(self, '_force_full_sync_pending', False):
                        # logger.debug("[send_df] Data fingerprint unchanged. Skip sync.")
                        continue

                    # ⚡ [FIX] 处理强制全量同步请求
                    if getattr(self, '_force_full_sync_pending', False):
                        logger.info("[send_df] Executing pending FULL SYNC request")
                        if hasattr(self, 'df_ui_prev'):
                            del self.df_ui_prev
                        self.sync_version = 0
                        self._force_full_sync_pending = False
                        self._cold_start = True # 标记为全量重发
                        
                    self._last_send_df_hash = df_hash
                    mem = 0
                    # --- 🚀 [FIX 3] 增量计算逻辑优化 ---
                    if hasattr(self, 'df_ui_prev') and not self._cold_start:
                        try:
                            with timed_ctx("viz_df_compare", warn_ms=10000):
                                # 仅在已有缓存且不是冷启动时才 compare
                                df_diff = df_ui.compare(self.df_ui_prev, keep_shape=False, keep_equal=False)
                            payload_to_send = df_diff
                            if df_diff.empty:
                                # logger.debug("[send_df] df_diff empty, skip sending this cycle")
                                msg_type = 'DF_DIFF_EMPTY'
                                sent = True
                            else:
                                msg_type = 'UPDATE_DF_DIFF'
                                mem = 0 

                        except ValueError as e:
                            logger.debug(f"[send_df] compare() ValueError: {e}, fallback to UPDATE_DF_ALL")
                            payload_to_send = df_ui
                            mem = 0 
                            msg_type = 'UPDATE_DF_ALL'
                    else:
                        # 冷启动或无缓存时，直接全量
                        payload_to_send = df_ui
                        mem = 0 
                        msg_type = 'UPDATE_DF_ALL'
                        self._cold_start = False # 重置冷启动标志


                    # 更新缓存
                    self.df_ui_prev = df_ui.copy()

                    if 'code' not in df_ui.columns:
                        df_ui = df_ui.reset_index()

                    logger.info(
                        f'df_ui: {msg_type} rows={len(df_ui)} ver={self.sync_version} mem={mem/1024:.1f} KB'
                    )

                    # --- 🎁 封装版本化协议包 ---
                    if msg_type == 'UPDATE_DF_ALL':
                        self.sync_version = 0
                    else:
                        self.sync_version += 1
                        
                    sync_package = {
                        'type': msg_type,
                        'data': payload_to_send,
                        'ver': self.sync_version
                    }

                    # ======================================================
                    if self.viz_conn is not None and self.qt_process is not None and self.qt_process.is_alive() and not sent:
                        try:
                            # ⭐ [STABILITY] Pipe 发送前检查，防止缓冲区满导致此线程永久阻塞
                            # Pipe 并没有直接的 is_full 检查，我们通过非阻塞发送（如果支持）或简单的 conn.poll() 辅助判断
                            # 此处仅做异常截获，确保 send 不会拖垮整个同步循环
                            self.viz_conn[0].send(
                                ('UPDATE_DF_DATA', sync_package)
                            )
                            logger.debug(f"[Pipe] {msg_type} sent (ver={self.sync_version})")
                            sent = True
                        except (EOFError, BrokenPipeError, ConnectionResetError):
                            logger.warning("[Pipe] connection lost, fallback to Socket")
                            self.viz_conn = None
                        except Exception as e:
                            logger.error(f"[Pipe] send failed: {e}")

                    # 诊断：如果有内部进程但没走 Pipe
                    if not sent and self.qt_process is not None and self.qt_process.is_alive():
                        logger.warning(f"[send_df] Internal process alive but Pipe skipped/failed!")

                    # ======================================================
                    # ⭐ 5️⃣ 兜底通道：Socket（仅当 Queue 失败）
                    # ======================================================
                    vis_enabled = getattr(self, '_vis_enabled_cache', True)
                    
                    # 🚀 [THROTTLE] 失败冷却：防止频繁超时重连拖慢循环 (特别是工作时间外)
                    now_ipc = time.time()
                    ipc_cooldown = getattr(self, '_viz_ipc_cooldown_until', 0)
                    
                    if not sent and vis_enabled and now_ipc > ipc_cooldown:
                        try:
                            # 1️⃣ pickle 单独计时
                            with timed_ctx("viz_IPC_pickle", warn_ms=10000):
                                payload = pickle.dumps(('UPDATE_DF_DATA', sync_package),
                                        protocol=pickle.HIGHEST_PROTOCOL)

                            header = struct.pack("!I", len(payload))

                            # 2️⃣ socket 单独计时
                            with timed_ctx("viz_IPC_send", warn_ms=10000):
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                    s.settimeout(0.4) # 缩短超时到 400ms
                                    s.connect((ipc_host, ipc_port))
                                    s.sendall(b"DATA" + header + payload)

                            logger.debug(f"[IPC] {msg_type} sent (ver={self.sync_version})")
                            sent = True
                            self._viz_ipc_fail_count = 0 # 成功清零
                            
                            # 再次提醒：虽然 IPC 发送成功，但如果是内部启动，本应该走 Queue
                            if self.qt_process is not None and self.qt_process.is_alive():
                                logger.info("[send_df] Used IPC fallback for distinct internal process (Queue might be full or broken).")

                        except (socket.timeout, ConnectionError, OSError) as e:
                            # 只有当真正失败时才记录
                            fail_count = getattr(self, '_viz_ipc_fail_count', 0) + 1
                            self._viz_ipc_fail_count = fail_count
                            
                            # 如果连续失败 3 次，开启 10-60 秒的冷却 (非工作时间更久)
                            if fail_count >= 3:
                                cooldown_dur = 60 if not cct.get_work_time() else 10
                                self._viz_ipc_cooldown_until = now_ipc + cooldown_dur
                                logger.info(f"⚠️ [IPC] Failed {fail_count} times, enter {cooldown_dur}s cooldown. (Error: {e})")
                            
                            if not vis_enabled:
                                sent = True

                except Exception:
                    logger.exception("[send_df] unexpected error")
                finally:
                    if sent:
                        cct.print_timing_summary_filter(include_prefix="viz_", top_n=10)
                # ======================================================
                # ⭐ 6️⃣ 状态更新（只在这里）
                # ======================================================
                prev = getattr(self, "_df_first_send_done", False)
                self._df_first_send_done = sent

                # 状态刚从 False → True：立即进入慢速周期
                vis_enabled = getattr(self, '_vis_enabled_cache', True)
                if sent and not prev and vis_enabled:
                    logger.info("[send_df] first successful send")
                
                # send_diff_df_status = hasattr(self, '_last_send_df_hash') and self._last_send_df_hash == df_hash and not getattr(self, '_force_full_sync_pending', False):
                # # 数据指纹一致，且无强制请求，跳过本轮昂贵的比较和发送
                # # logger.debug("[send_df] Data fingerprint unchanged. Skip sync.")
                # # logger.info(f"[send_df] Data fingerprint unchanged. Skip sync. getattr(self, '_force_full_sync_pending', False): {getattr(self, '_force_full_sync_pending', False)}")
                # ======================================================
                # ⭐ 7️⃣ 调度逻辑 (PERF 优化：使用 Event 替代 300次/5分钟 的 GIL 竞争)
                # ======================================================
                sleep_seconds = 300 if sent else 5
                
                # 若外部主动置为 False，退出不等待
                if not self._df_sync_running or not self._df_first_send_done:
                    break
                    
                self._send_df_wake_event.wait(timeout=sleep_seconds)
                self._send_df_wake_event.clear()
        finally:
            self._send_sync_lock.release()
            logger.info("[send_df] Thread EXITED safely.")


    def on_voice_toggle(self):
        val = self.voice_var.get()
        if getattr(self, 'live_strategy', None) is not None:
            self.live_strategy.set_voice_enabled(val)
        else:
            logger.warning(f'live_strategy is None, cannot set voice enabled')
        # 1. 控制本进程 AlertManager
        try:
            am = AlertManager()
            am.voice_enabled = val
            if not val:
                am.stop_current_speech()
            else:
                am.resume_voice()
        except:
            pass

        # 2. 互斥逻辑：打开 Tk 语音 → 通知可视化器关闭其 VoiceProcess
        #    关闭时不通知可视化器（不强制打开可视化器端语音）
        if val:
            try:
                if (hasattr(self, 'viz_conn') and self.viz_conn
                        and hasattr(self, 'qt_process') and self.qt_process
                        and self.qt_process.is_alive()):
                    self.viz_conn[0].send(('VOICE_STATE', {'enabled': False}))
                    logger.info("[IPC] Tk voice ON -> sent VOICE_STATE=False to visualizer")
            except Exception as e:
                logger.debug(f"[IPC] Failed to send VOICE_STATE to visualizer: {e}")

    def reload_cfg_value(self):
        global marketInit, marketblk, scale_offset, resampleInit
        global duration_sleep_time, write_all_day_date, detect_calc_support
        global alert_cooldown, pending_alert_cycles, st_key_sort
        global saved_width, saved_height
        
        # 1. 记录加载前的关键配置值
        check_keys = [
            'marketInit', 'marketblk', 'scale_offset', 'resampleInit',
            'duration_sleep_time', 'detect_calc_support', 'alert_cooldown',
            'pending_alert_cycles', 'st_key_sort', 'write_all_day_date',
            'saved_width', 'saved_height'
        ]
        old_state = {k: globals().get(k) for k in check_keys}

        conf_ini = cct.get_conf_path('global.ini')
        if not conf_ini:
            logger.info("global.ini 加载失败，程序无法继续运行")
            return

        CFG = cct.GlobalConfig(conf_ini)

        # 2. 执行更新
        marketInit = CFG.marketInit
        marketblk = CFG.marketblk
        scale_offset = CFG.scale_offset
        resampleInit = CFG.resampleInit
        duration_sleep_time = CFG.duration_sleep_time
        write_all_day_date = CFG.write_all_day_date
        detect_calc_support = CFG.detect_calc_support
        alert_cooldown = CFG.alert_cooldown
        pending_alert_cycles = CFG.pending_alert_cycles
        st_key_sort = CFG.st_key_sort 
        saved_width, saved_height = CFG.saved_width, CFG.saved_height 

        # 3. 差异化提示
        changes = []
        for k in check_keys:
            new_v = globals().get(k)
            old_v = old_state.get(k)
            if old_v != new_v:
                changes.append(f"• {k}: {old_v} ➜ {new_v}")
        
        if changes:
            msg = "检测到配置项变更:\n" + "\n".join(changes)
            toast_message(self, msg, duration=3500)
            display_msg = msg.replace('\n', ' ')
            logger.warning(f"[CFG-RELOAD] {display_msg}")

            # 4. [NEW] 按需同步到 UI 控件与共享内存 (Conditional Shared State Sync)
            try:
                # 同步 resample 下拉框
                if hasattr(self, 'resample_combo'):
                    self.resample_combo.set(resampleInit)
                
                # 同步 st_key_sort 输入框
                if hasattr(self, 'st_key_sort_value'):
                    self.st_key_sort_value.set(st_key_sort)

                # 同步到共享内存 (global_dict)，确保子进程感知
                if hasattr(self, 'global_values'):
                    self.global_values.setkey("resample", resampleInit)
                
                if hasattr(self, 'global_dict'):
                    self.global_dict["resample"] = resampleInit
                    self.global_dict["market"] = marketInit
                    self.global_dict["sleep"] = int(duration_sleep_time)
                    
                logger.info(f"🔄 [SYNC] 已将变更配置同步至 UI 与共享内存 (resample={resampleInit})")
            except Exception as e:
                logger.error(f"❌ [SYNC] 同步 UI/共享内存失败: {e}")
        else:
            logger.info("配置重载完成，无关键参数变动。")
        
        # 同步频率变动到实时服务(如果已连接)
        if hasattr(self, 'realtime_service') and self.realtime_service:
            try:
                self.realtime_service.set_expected_interval(int(duration_sleep_time))
            except:
                pass

    def update_linkage_status(self):
        global tip_var_status_flag
        # 此处处理 checkbuttons 状态
        if not self.tdx_var.get() or not self.ths_var.get():
            self.sender.reload()
        if  self.dfcf_var.get() != self.auto_adjust_column:
            logger.info(f"DC:{self.dfcf_var.get()} self.auto_adjust_column :{self.auto_adjust_column}")
            self.auto_adjust_column = self.dfcf_var.get()
            # self.apply_search()
            # self.after(50, self.adjust_column_widths)
            self._setup_tree_columns(self.tree,self.current_cols, sort_callback=self.sort_by_column, other={})
            # self.reload_cfg_value()
            if self.live_strategy:
                self.live_strategy.set_alert_cooldown(alert_cooldown)

        if self.live_strategy:
            if self.realtime_var.get():
                if not self.live_strategy.scan_hot_concepts_status:
                    self.live_strategy.set_scan_hot_concepts(status=True)
                    logger.info(f'self.live_strategy.scan_hot_concepts_status is False will be open')
            else:
                if self.live_strategy.scan_hot_concepts_status:
                    self.live_strategy.set_scan_hot_concepts(status=False)
                    logger.info(f'self.live_strategy.scan_hot_concepts_status  will be close')
        # [SAFEGUARD] 监测用户“手动”取消勾选行为：如果勾选断开且没有待恢复任务，才重置标志
        if (not self.vis_var.get()) and getattr(self, "_df_first_send_done", False) \
           and getattr(self, 'last_vis_var_status', None) is None:
            logger.debug(f"[send_df] User manually unchecked vis: resetting first_send_done")
            if hasattr(self, 'df_ui_prev'):
                del self.df_ui_prev
            self._df_first_send_done = False
        # self.update_treeview_cols(self.current_cols)
        tip_var_status_flag.value = self.tip_var.get()

        logger.info(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()} tip_var_status_flag:{tip_var_status_flag.value}")

    def persistent_df_all_to_h5(self):
        """将全量数据持久化到 G 盘共享文件 (HDF5 格式)"""
        if not hasattr(self, 'df_all') or self.df_all.empty:
            toast_message(self, "❌ 数据为空，无法保存")
            return
        
        try:
            today = cct.get_today('')
            h5_path = f"g:\\shared_df_all-{today}.h5"
            
            # [CRITICAL FIX] HDF5 table 格式严禁 mixed-type。
            # 即使原本是 object，如果存在 int/str 混合，to_hdf 就会崩溃。
            # 我们必须强制将这些列转为纯 string。
            save_df = self.df_all.copy()
            for col in save_df.columns:
                if save_df[col].dtype == 'object':
                    save_df[col] = save_df[col].astype(str)
            
            # 采用 table 格式以便查询，启用 blosc 高速压缩
            save_df.to_hdf(h5_path, key='df', mode='w', format='table', complib='blosc', complevel=9)
            
            self.status_var.set(f"✅ 实盘数据已共享: {h5_path}")
            logger.info(f"Persistent df_all to HDF5 success: {h5_path} (Rows: {len(self.df_all)})")
            toast_message(self, "实盘数据持久化成功")
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to persist df_all to HDF5: {err_msg}")
            self.status_var.set(f"❌ 保存失败: {err_msg[:30]}...")
            toast_message(self, f"保存失败: {err_msg[:20]}")


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
            # 更新查询说明
            # self.query_desc_label.config(text=desc)
            self.refresh_tree_with_query(query_dict)

    # 将查询文本解析为 dict（可根据你需求改）
    def parse_query_text(self, text):
        # 简单示例：name=ABC;percent>1
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
                        except Exception as e:
                            logger.error(f"Error in task: {e}")
                    elif val.startswith("<="):
                        try:
                            df_filtered = df_filtered[s.astype(float) <= float(val[2:])]
                            continue
                        except Exception as e:
                            logger.error(f"Error in task: {e}")
                    elif "~" in val:
                        try:
                            low, high = map(float, val.split("~"))
                            df_filtered = df_filtered[s.astype(float).between(low, high)]
                            continue
                        except Exception as e:
                            logger.error(f"Error in task: {e}")
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
        self.refresh_tree(force=True)


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
        # Auto-launch Visualizer if enabled
        if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
            self.open_visualizer(stock_code)

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

            # 再显示出来
            self.detail_win.deiconify()

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
        
        vals = self.tree.item(sel_row, "values")
        if not vals:
            return

        # 获取股票代码和名称
        code = vals[0]
        name = vals[1]
        
        # 根据双击的列执行不同逻辑
        if col_idx == 0:  # code
            self._run_sbc_test_from_tk(code, use_live=True, event=event)
            logger.info(f"Double-click 'code' for Live SBC: {code} ({name})")
        elif col_idx == 1:  # name
            self._run_sbc_test_from_tk(code, use_live=False, event=event)
            logger.info(f"Double-click 'name' for Replay SBC: {code} ({name})")
        else:
            # 其他列保持原有逻辑：查看备注并复制代码
            self.view_stock_remarks(code, name)
            pyperclip.copy(code)
            logger.info(f"Double-click other column for Remarks: {code} ({name})")



    # def on_tree_right_click(self, event):
    #     """右键点击 TreeView 行"""
    #     # 确保选中行
    #     item_id = self.tree.identify_row(event.y)

    #     if item_id:
    #         # 选中该行
    #         self.tree.selection_set(item_id)
    #         self.tree.focus(item_id)
            
    #         # 获取基本信息
    #         values = self.tree.item(item_id, 'values')
    #         stock_code = values[0]
    #         stock_name = values[1] if len(values) > 1 else "未知"
            
    #         # 创建菜单
    #         menu = tk.Menu(self, tearoff=0)
            
    #         menu.add_command(label=f"📝 复制提取信息 ({stock_code})", 
    #                         command=lambda: self.copy_stock_info(stock_code))
                            
    #         menu.add_separator()
            
    #         menu.add_command(label="🧪 测试买卖策略", 
    #                         command=lambda  e=event: self.on_tree_click_for_tooltip(e,stock_code,stock_name,True))
    #                         # command=lambda: self.test_strategy_for_stock(stock_code, stock_name))
    #         menu.add_command(label="🧪 测试Code策略", 
    #                         command=lambda  e=event: check_code(self.df_all,stock_code,self.search_var1.get()))

    #         menu.add_command(label="🏷️ 添加标注备注", 
    #                         command=lambda: self.add_stock_remark(stock_code, stock_name))
            
    #         menu.add_command(label="🔔 加入语音预警",
    #                         command=lambda: self.add_voice_monitor_dialog(stock_code, stock_name))
                            
    #         menu.add_command(label="📖 查看标注手札", 
    #                         command=lambda: self.view_stock_remarks(stock_code, stock_name))
            
    #         menu.add_separator()
            
    #         menu.add_command(label=f"🚀 发送到关联软件", 
    #                         command=lambda: self.original_push_logic(stock_code))
    #         menu.add_command(label="🔍 策略白盒评估...", command=lambda: self.open_strategy_manager(verify_code=stock_code), foreground="blue")
            
    #         menu.add_separator()
    #         menu.add_command(label="🚫 黑名单管理中心", command=self.open_blacklist_manager)
            
    #         # 弹出菜单
    #         menu.post(event.x_root, event.y_root)

    def on_tree_right_click(self, event):
        """右键点击 TreeView 行"""
        item_id = self.tree.identify_row(event.y)

        if not item_id:
            return

        # 如果点击的行不在已选中的行中才清空并选中单行，否则保留多选支持批量操作
        selected_items = self.tree.selection()
        if item_id not in selected_items:
            self.tree.selection_set(item_id)
            selected_items = (item_id,)
            
        self.tree.focus(item_id)

        # 🚀 [FIX] 智能检测列索引
        all_cols = list(self.tree["columns"])
        idx_code, idx_name = -1, -1
        for i, col in enumerate(all_cols):
            c_lower = str(col).lower()
            if c_lower in ["code", "代码"]: idx_code = i
            if c_lower in ["name", "名称"]: idx_name = i
        if idx_code == -1: idx_code = 0
        if idx_name == -1: idx_name = 1

        # 收集选中的代码字典
        code_to_name = {}
        for sid in selected_items:
            try:
                vals = self.tree.item(sid, 'values')
                if not vals: continue
                c = str(vals[idx_code]).zfill(6)
                n = str(vals[idx_name])
                if c and c != "N/A":
                    code_to_name[c] = n
            except Exception:
                continue

        # 用于基础单项操作（兼容旧逻辑）
        try:
            vals = self.tree.item(item_id, 'values')
            stock_code = str(vals[idx_code]).zfill(6)
            stock_name = str(vals[idx_name])
        except Exception:
            stock_code = "000000"
            stock_name = "未知"

        # ================= 主菜单 =================
        menu = tk.Menu(self, tearoff=0)

        # —— 基础功能 ——
        menu.add_command(
            label=f"📝 复制提取信息 ({stock_code})",
            command=lambda: self.copy_stock_info(stock_code)
        )

        menu.add_separator()

        # —— 策略相关 ——
        menu.add_command(
            label="🧪 测试买卖策略",
            command=lambda e=event: self.on_tree_click_for_tooltip(
                e, stock_code, stock_name, True
            )
        )

        menu.add_command(
            label="🧪 测试Code策略",
            command=lambda: check_code(self.df_all, stock_code, self.search_var1.get())
        )

        menu.add_command(
            label="🔍 策略白盒评估...",
            command=lambda: self.open_strategy_manager(verify_code=stock_code),
            foreground="blue"
        )
        
        batch_text = f"🧬 DNA 专项审计... ({len(code_to_name)}只)" if len(code_to_name) > 1 else "🧬 DNA 专项审计..."
        menu.add_command(
            label=batch_text,
            command=lambda: self._run_dna_audit_batch(code_to_name, end_date=self._get_audit_end_date()),
            foreground="purple"
        )

        menu.add_separator()

        # —— SBC 验证策略 ——
        menu.add_command(
            label="🧪 SBC 实时测试",
            command=lambda: self._run_sbc_test_from_tk(stock_code, use_live=True)
        )

        menu.add_command(
            label="🧪 SBC 回放测试",
            command=lambda: self._run_sbc_test_from_tk(stock_code, use_live=False)
        )

        menu.add_separator()

        # —— 标注 & 预警 ——
        menu.add_command(
            label="🏷️ 添加标注备注",
            command=lambda: self.add_stock_remark(stock_code, stock_name)
        )

        menu.add_command(
            label="📖 查看标注手札",
            command=lambda: self.view_stock_remarks(stock_code, stock_name)
        )

        menu.add_command(
            label="🔔 加入语音预警",
            command=lambda: self.add_voice_monitor_dialog(stock_code, stock_name)
        )

        menu.add_separator()

        # —— 外部联动 ——
        menu.add_command(
            label="🚀 发送到关联软件",
            command=lambda: self.original_push_logic(stock_code)
        )

        menu.add_separator()

        # ================= 信号清理子菜单 =================
        cleanup_menu = tk.Menu(menu, tearoff=0)

        cleanup_menu.add_command(
            label="清理1天前信号",
            command=lambda: self._cleanup_signals_with_feedback(1)
        )
        cleanup_menu.add_command(
            label="清理2天前信号",
            command=lambda: self._cleanup_signals_with_feedback(2)
        )
        cleanup_menu.add_command(
            label="清理3天前信号",
            command=lambda: self._cleanup_signals_with_feedback(3)
        )
        cleanup_menu.add_command(
            label="清理5天前信号",
            command=lambda: self._cleanup_signals_with_feedback(5)
        )
        cleanup_menu.add_command(
            label="清理7天前信号",
            command=lambda: self._cleanup_signals_with_feedback(7)
        )
        
        cleanup_menu.add_separator()
        
        cleanup_menu.add_command(
            label="🚨 强制清理全量队列 (3天未启动信号)",
            command=lambda: self._force_cleanup_stagnant_signals()
        )

        menu.add_cascade(label="🧹 信号清理", menu=cleanup_menu)

        menu.add_command(
            label="🔄 刷新",
            command=lambda: self._schedule_after(0, self.update_tree)
        )

        menu.add_separator()

        # —— 其他管理 ——
        menu.add_command(
            label="🚫 黑名单管理中心",
            command=self.open_blacklist_manager
        )

        # 弹出菜单
        menu.post(event.x_root, event.y_root)

    def _get_audit_end_date(self):
        """探测当前主窗口或核心面板的活跃截止日期 [🚀 数据对齐核心]"""
        # 1. 优先从竞价赛马面板提取历史模式状态
        if hasattr(self, 'sector_bidding_panel') and getattr(self.sector_bidding_panel, '_is_history_mode', False):
            t_str = getattr(self.sector_bidding_panel, '_history_date', None)
            if t_str:
                last_td = str(cct.get_last_trade_date()).replace("-", "")
                if t_str < last_td:
                    return t_str
            # return getattr(self.sector_bidding_panel, '_history_date', None)
        # 2. 从策略选股主窗口提取 (如有)
        if hasattr(self, '_stock_selection_win') and getattr(self._stock_selection_win, 'current_date', False):
            t_str = getattr(self._stock_selection_win, 'current_date', None)
            if t_str:
                last_td = str(cct.get_last_trade_date())
                if t_str < last_td:
                    return t_str
        return None

    def _run_dna_audit_batch(self, code_to_name, end_date=None):
        import threading
        from backtest_feature_auditor import audit_multiple_codes, show_dna_audit_report_window
        from tkinter import messagebox
        
        # 🚀 [NEW] 防重入保护
        if getattr(self, '_dna_audit_running', False):
            return
        self._dna_audit_running = True
        
        codes = list(code_to_name.keys())
        if not codes:
            self._dna_audit_running = False
            return
        
        # 弹一个带进度条的提示
        top = tk.Toplevel(self)
        top.withdraw() 
        top.attributes("-alpha", 0.0) 
        top.title("🧬 DNA 审计中...")
        
        # 界面美化
        top.configure(bg='#f8f9fa')
        content_frame = tk.Frame(top, bg='#f8f9fa', padx=15, pady=15)
        content_frame.pack(expand=True, fill='both')
        
        msg_label = tk.Label(content_frame, text=f"正在审计 {len(codes)} 只个股...", 
                           font=("微软雅黑", 9), bg='#f8f9fa', fg='#333')
        msg_label.pack(pady=(0, 10))
        
        # 进度条
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(content_frame, variable=progress_var, maximum=len(codes), mode='determinate', length=280)
        progress_bar.pack(pady=5)
        
        status_label = tk.Label(content_frame, text="初始化中...", font=("微软雅黑", 8), bg='#f8f9fa', fg='#666')
        status_label.pack()
        
        # 初始化展示位置
        w, h = 320, 140
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.attributes("-topmost", True)
        top.deiconify() # 直接显示
        
        def progress_cb(curr, total, msg):
            """跨线程进度回调"""
            def _update():
                try:
                    # 🛡️ [GUARD] 若窗口已被用户关闭，静默退出，防止 TclError: invalid command name
                    if not top.winfo_exists(): return
                    progress_var.set(curr)
                    status_label.config(text=msg)
                    if curr >= total:
                        status_label.config(text="✅ 正在呼出报告...")
                except tk.TclError:
                    pass # 窗体已销毁
                    
            # 🚀 [THREAD-SAFE] 通过 dispatch 队列回传 UI 更新
            if hasattr(self, 'tk_dispatch_queue'):
                self.tk_dispatch_queue.put(_update)

        def run_task():
            try:
                # 调用批量接口
                summaries = audit_multiple_codes(codes, 
                                               end_date=end_date, 
                                               code_to_name=code_to_name,
                                               progress_callback=progress_cb)
                # 切回主线程展示
                def _show_report():
                    if top.winfo_exists():
                        top.destroy()
                    
                    # 🚀 [NEW] 支持窗口复用
                    if hasattr(self, '_dna_audit_win') and self._dna_audit_win and self._dna_audit_win.winfo_exists():
                        logger.info(f"🔄 Reusing main DNA Audit Window for {len(summaries)} stocks")
                        self._dna_audit_win.update_report(summaries, end_date=end_date)
                    else:
                        logger.info(f"🧬 Creating new main DNA Audit Window for {len(summaries)} stocks")
                        self._dna_audit_win = show_dna_audit_report_window(summaries, parent=self, end_date=end_date)
                
                self.after(0, _show_report)
            except Exception as e:
                logger.error(f"DNA Audit failed: {e}")
                self.after(0, lambda: [top.destroy() if top.winfo_exists() else None, messagebox.showerror("DNA 审计出错", str(e), parent=self)])
            finally:
                self._dna_audit_running = False
                
        threading.Thread(target=run_task, daemon=True).start()


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
            f"📈 连阳: {stock_data.get('red', 'N/A')} 🔺\n"
            f"📉 连阴: {stock_data.get('gren', 'N/A')} 🔻\n"
            f"📈 突破布林: {boll}\n"
            f"  signal: {signal_icon} (low<10 & C>5)\n"
            f"  Upper:  {upper:.2f}\n"
            f"  Lower:  {lower:.2f}\n"
            f"🚀 突破: {breakthrough} (high > upper)\n"
            f"💪 强势: {strength} (L1>L2 & H1>H2)"
        )
        return info_text

    def original_push_logic(self, stock_code,select_win=False):
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

    def test_strategy_for_stock(self, code, name):
        """
        测试选中股票的买卖策略并生成分析报告
        用于验证数据完整性和策略决策
        """
        try:
            from intraday_decision_engine import IntradayDecisionEngine
            # 检查数据是否存在
            if code not in self.df_all.index:
                messagebox.showwarning("数据缺失", f"未找到代码 {code} 的数据")
                return
            
            row = self.df_all.loc[code]
            
            # 构建行情数据字典
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            
            # 构建快照数据（使用 df_all 中的正确字段名）
            # lastp1d = 昨日收盘价, lastv1d/2d/3d = 昨日/前日/大前日成交量
            # lasth1d/lastl1d = 昨日最高/最低价, per1d = 昨日涨幅
            snapshot = {
                'last_close': row_dict.get('lastp1d', row_dict.get('settle', 0)),
                'percent': row_dict.get('per1d', row_dict.get('percent', 0)),
                'nclose': row_dict.get('nclose', 0),    # 今日均价
                'lowvol': row_dict.get('lowvol', 0),    # 最近最低价的地量
                'llowvol': row_dict.get('llowvol', 0),  # 三十日内的地量
                'ma20d': row_dict.get('ma20d', 0),      # 二十日线
                'ma5d': row_dict.get('ma5d', 0),        # 五日线
                'hmax': row_dict.get('hmax', 0),        # 30日最高价
                'hmax60': row_dict.get('hmax60', 0),    # 60日最高价
                'low60': row_dict.get('low60', 0),      # 60日最低价
                'low10': row_dict.get('low10', 0),      # 10日最低价
                'high4': row_dict.get('high4', 0),      # 4日最高
                'max5': row_dict.get('max5', 0),        # 5日最高
                'lower': row_dict.get('lower', 0),      # 布林下轨
                'upper1': row_dict.get('upper1', 0),
                'upper2': row_dict.get('upper2', 0),
                'upper3': row_dict.get('upper3', 0),
                'upper4': row_dict.get('upper4', 0),
                'upper5': row_dict.get('upper5', 0),
                'lastl1d': row_dict.get('lastl1d', 0),
                'lastl2d': row_dict.get('lastl2d', 0),
                'lastl3d': row_dict.get('lastl3d', 0),
                'lastl4d': row_dict.get('lastl4d', 0),
                'lastl5d': row_dict.get('lastl5d', 0),
                'lasth1d': row_dict.get('lasth1d', 0),
                'lasth2d': row_dict.get('lasth2d', 0),
                'lasth3d': row_dict.get('lasth3d', 0),
                'lasth4d': row_dict.get('lasth4d', 0),
                'lasth5d': row_dict.get('lasth5d', 0),
                'lastp1d': row_dict.get('lastp1d', 0),
                'lastp2d': row_dict.get('lastp2d', 0),
                'lastp3d': row_dict.get('lastp3d', 0),
                'lastp4d': row_dict.get('lastp4d', 0),
                'lastp5d': row_dict.get('lastp5d', 0),
                'lasto1d': row_dict.get('lasto1d', 0),
                'lasto2d': row_dict.get('lasto2d', 0),
                'lasto3d': row_dict.get('lasto3d', 0),
                'lasto4d': row_dict.get('lasto4d', 0),
                'lasto5d': row_dict.get('lasto5d', 0),
                'highest_since_buy': row_dict.get('high', 0),
                'cost_price': row_dict.get('lastp3d', 0),  # 默认三天前收盘价为成本
                'hvolume': row.get('hv', 0),
                'lvolume': row.get('lv', 0),
            }
            
            # 自动填充 1-15 日的历史 OHLCV 数据
            for i in range(1, 16):
                for suffix in ['p', 'h', 'l', 'o', 'v']:
                    key = f'last{suffix}{i}d'
                    if key in row_dict:
                        snapshot[key] = row_dict[key]
            
            snapshot['win'] = row_dict.get('win', 0)            # 加速连阳
            snapshot['sum_perc'] = row_dict.get('sum_perc', 0)  # 加速连阳涨幅
            snapshot['red'] = row_dict.get('red', 0)            # 五日线上数据
            snapshot['gren'] = row_dict.get('gren', 0)          # 弱势绿柱数据
            snapshot['red'] = snapshot.get('red', 0)  #5日线上日线
            
            # 💥 [NEW] 提取当前仓位阶段及日线数据
            current_phase_obj = "IDLE"
            next_phase_str = "N/A"
            phase_reason = ""
            day_df = pd.DataFrame()
            
            if hasattr(self, 'live_strategy') and self.live_strategy:
                # 1. 获取日线缓存
                cache_key = f"{code}_d"
                day_df = self.live_strategy.daily_history_cache.get(cache_key, pd.DataFrame())
                if day_df.empty:
                    day_df = self.live_strategy.daily_history_cache.get(code, pd.DataFrame())
                
                # 2. 获取当前仓位状态
                monitors = self.live_strategy.get_monitors()
                actual_key = code
                if code not in monitors:
                    for k in monitors.keys():
                        if k.startswith(code):
                            actual_key = k
                            break
                if actual_key in monitors:
                    current_phase_obj = monitors[actual_key].get('trade_phase', "IDLE")

            # 3. 注入快照
            if not day_df.empty:
                snapshot['day_df'] = day_df
                snapshot['td_setup'] = day_df.iloc[-1].get('td_setup', 0)
            snapshot['trade_phase'] = current_phase_obj
            
            # 4. 💥 执行决策评估 (必须在状态机预览之前执行)
            engine = IntradayDecisionEngine()
            result = engine.evaluate(row_dict, snapshot, mode="full")
            
            # 5. 💥 评估状态机变迁预览
            if hasattr(self, 'live_strategy') and self.live_strategy:
                if hasattr(self.live_strategy, 'phase_engine') and self.live_strategy.phase_engine:
                    from position_phase_engine import TradePhase
                    try:
                        c_p_enum = TradePhase(current_phase_obj)
                    except:
                        c_p_enum = TradePhase.IDLE
                    
                    # 模拟注入今日买入标记以便 IDLE -> SCOUT 变迁预览
                    if result.get('action') in ['买入', 'BUY', 'ADD']:
                        snapshot['buy_triggered_today'] = True
                        
                    n_p_enum, phase_reason = self.live_strategy.phase_engine.evaluate_phase(
                        code, row_dict, snapshot, current_phase=c_p_enum
                    )
                    next_phase_str = n_p_enum.value
            
            # 检测数据缺失（使用 df_all 中的正确字段名）
            
            missing_fields = []
            critical_fields = ['trade', 'open', 'high', 'low', 'nclose', 'volume', 
                              'ratio', 'ma5d', 'ma10d', 'lastp1d', 'percent']
            for field in critical_fields:
                val = row_dict.get(field, None)
                if val is None or (isinstance(val, (int, float)) and val == 0):
                    missing_fields.append(field)

            # 构建报告
            report_lines = [
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📊 策略测试报告 - {name} ({code})",
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
                "【核心决策】",
                f"  建议动作: {result['action']}",
                f"  目标仓位: {result['position'] * 100:.0f}%",
                f"  状态变迁: {current_phase_obj} ➔ {next_phase_str}",
                f"  变迁原因: {phase_reason if phase_reason else '维持现状'}",
                f"  内核理由: {result['reason']}",
                "",
            ]
            
            # [NEW] 顶部信号详情 (如果主升浪逻辑返回)
            if not day_df.empty:
                from daily_top_detector import detect_top_signals
                top_info = detect_top_signals(day_df, row_dict)
                td_setup = day_df.iloc[-1].get('td_setup', 0)
                
                report_lines.extend([
                    "【主升/顶部探测】",
                    f"  TD 序列 : {td_setup} (Setup)",
                    f"  顶部评分: {top_info['score']:.2f} ({top_info['action']})",
                ])
                if top_info['signals']:
                    report_lines.append(f"  预警信号: {', '.join(top_info['signals'])}")
                report_lines.append("")
            
            # 决策调试信息（优先显示便于分析）
            debug = result.get('debug', {})
            if debug:
                report_lines.append("【决策调试信息】")
                for key, val in debug.items():
                    if isinstance(val, float):
                        report_lines.append(f"  {key}: {val:.2f}")
                    elif isinstance(val, list):
                        report_lines.append(f"  {key}: {', '.join(map(str, val))}")
                    else:
                        report_lines.append(f"  {key}: {val}")
                report_lines.append("")
            
            # 数据完整性检查
            if missing_fields:
                report_lines.extend([
                    "⚠️ 【数据缺失警告】",
                    f"  缺失字段: {', '.join(missing_fields)}",
                    "  建议: 检查数据源或重新加载",
                    ""
                ])
            else:
                report_lines.extend([
                    "✅ 【数据完整性检查】",
                    "  所有关键字段正常",
                    ""
                ])
            
            # 关键行情数据
            report_lines.extend([
                "【关键行情数据】",
                f"  当前价: {row_dict.get('trade', 'N/A')}",
                f"  开盘价: {row_dict.get('open', 'N/A')}",
                f"  最高价: {row_dict.get('high', 'N/A')}",
                f"  最低价: {row_dict.get('low', 'N/A')}",
                f"  均价:   {row_dict.get('nclose', 'N/A')}",
                f"  昨收:   {snapshot.get('last_close', 'N/A')}",
                "",
                "【技术指标】",
                f"  MA5:    {row_dict.get('ma5d', 'N/A')}",
                f"  MA10:   {row_dict.get('ma10d', 'N/A')}",
                f"  MA20:   {row_dict.get('ma20d', 'N/A')}",
                f"  MACD:   {row_dict.get('macd', 'N/A')}",
                f"  KDJ_J:  {row_dict.get('kdj_j', 'N/A')}",
                "",
                "【量能数据】",
                f"  成交量  : {row_dict.get('volume', 'N/A')}",
                f"  换手率  : {row_dict.get('ratio', 'N/A')}%",
                f"  昨日量  : {snapshot.get('lastv1d', 'N/A')}",
                f"  最近高量: {snapshot.get('hvolume', 'N/A')}",
                f"  最近地量: {snapshot.get('lvolume', 'N/A')}",
            ])
            
            report_text = "\n".join(report_lines)
            
            # 获取当前测试价用于模拟成交
            price = row_dict.get('trade', row_dict.get('now', 0))
            
            # 创建报告窗口
            self._show_strategy_report_window(code, name, report_text, result, price=price)
            
        except Exception as e:
            logger.error(f"Strategy test error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("测试失败", f"策略测试出错: {e}")

    def _show_strategy_report_window(self, code, name, report_text, result, price=0.0):
        """显示策略测试报告窗口 (窗口复用模式 - 优化版)"""
        window_id = '策略测试'
        
        action = result.get('action', '持仓')
        action_color = {
            '买入': '#4CAF50',
            '卖出': '#F44336',
            '止损': '#FF5722',
            '止盈': '#2196F3',
            '持仓': '#9E9E9E'
        }.get(action, '#9E9E9E')

        # 1. 检查窗口是否已存在且未销毁
        if hasattr(self, 'strategy_report_win') and self.strategy_report_win and self.strategy_report_win.winfo_exists():
            win = self.strategy_report_win
            win.title(f"🧪 策略测试 - {name} ({code})")
            win.lift()
            # win.attributes("-topmost", True)
            # win.after(50, lambda: win.attributes("-topmost", False))
            # 如果组件已存在，则直接更新，不销毁也不抢夺焦点
            if hasattr(win, 'txt_widget'):
                win.top_frame.config(bg=action_color)
                win.action_label.config(
                    text=f"建议: {action} | 仓位: {result['position']*100:.0f}%", 
                    bg=action_color
                )
                win.txt_widget.config(state='normal')
                win.txt_widget.delete('1.0', 'end')
                win.txt_widget.insert('1.0', report_text)
                win.txt_widget.config(state='disabled')
                win.report_text = report_text # 更新复制引用的文本
                return
            else:
                # 兜底：清空重建
                for widget in win.winfo_children():
                    widget.destroy()
        else:
            win = tk.Toplevel(self)
            self.strategy_report_win = win
            self.load_window_position(win, window_id, default_width=600, default_height=850)

        win.title(f"🧪 策略测试 - {name} ({code})")
        win.report_text = report_text

        # 2. 构建持久化 UI
        # 顶部状态栏
        win.top_frame = tk.Frame(win, bg=action_color, height=40)
        win.top_frame.pack(fill='x')
        win.top_frame.pack_propagate(False)
        
        win.action_label = tk.Label(win.top_frame, 
                               text=f"建议: {action} | 仓位: {result['position']*100:.0f}%",
                               fg='white', bg=action_color,
                               font=('Microsoft YaHei', 14, 'bold'))
        win.action_label.pack(pady=8)
        
        # 报告文本区域
        txt_frame = tk.Frame(win)
        txt_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(txt_frame)
        win.txt_widget = tk.Text(txt_frame, wrap='word', font=('Consolas', 10), height=20,
                     yscrollcommand=scrollbar.set, padx=10, pady=5)
        scrollbar.config(command=win.txt_widget.yview)
        
        win.txt_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        win.txt_widget.insert('1.0', report_text)
        win.txt_widget.config(state='disabled')
        
        # 底部按钮
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        
        def copy_report():
            win.clipboard_clear()
            win.clipboard_append(win.report_text)
            self.status_var2.set("报告已复制到剪贴板")
        
        tk.Button(btn_frame, text="📋 复制报告", command=copy_report, 
                 width=12).pack(side='left', padx=5)
        
        def run_simulation():
            if not self.live_strategy:
                messagebox.showwarning("警告", "交易引擎未启动")
                return
            
            row = self.df_all.loc[code]
            # 构建行情数据字典
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            
            # 构建快照数据（使用 df_all 中的正确字段名）
            # lastp1d = 昨日收盘价, lastv1d/2d/3d = 昨日/前日/大前日成交量
            # lasth1d/lastl1d = 昨日最高/最低价, per1d = 昨日涨幅
            snapshot = {
                'last_close': row_dict.get('lastp1d', row_dict.get('settle', 0)),
                'percent': row_dict.get('per1d', row_dict.get('percent', 0)),
                'nclose': row_dict.get('nclose', 0),    # 今日均价
                'lowvol': row_dict.get('lowvol', 0),    # 最近最低价的地量
                'llowvol': row_dict.get('llowvol', 0),  # 三十日内的地量
                'ma20d': row_dict.get('ma20d', 0),      # 二十日线
                'ma5d': row_dict.get('ma5d', 0),        # 五日线
                'hmax': row_dict.get('hmax', 0),        # 30日最高价
                'hmax60': row_dict.get('hmax60', 0),    # 60日最高价
                'low60': row_dict.get('low60', 0),      # 60日最低价
                'low10': row_dict.get('low10', 0),      # 10日最低价
                'high4': row_dict.get('high4', 0),      # 4日最高
                'max5': row_dict.get('max5', 0),        # 5日最高
                'lower': row_dict.get('lower', 0),      # 布林下轨
                'upper1': row_dict.get('upper1', 0),
                'upper2': row_dict.get('upper2', 0),
                'upper3': row_dict.get('upper3', 0),
                'upper4': row_dict.get('upper4', 0),
                'upper5': row_dict.get('upper5', 0),
                'lastl1d': row_dict.get('lastl1d', 0),
                'lastl2d': row_dict.get('lastl2d', 0),
                'lastl3d': row_dict.get('lastl3d', 0),
                'lastl4d': row_dict.get('lastl4d', 0),
                'lastl5d': row_dict.get('lastl5d', 0),
                'lasth1d': row_dict.get('lasth1d', 0),
                'lasth2d': row_dict.get('lasth2d', 0),
                'lasth3d': row_dict.get('lasth3d', 0),
                'lasth4d': row_dict.get('lasth4d', 0),
                'lasth5d': row_dict.get('lasth5d', 0),
                'lastp1d': row_dict.get('lastp1d', 0),
                'lastp2d': row_dict.get('lastp2d', 0),
                'lastp3d': row_dict.get('lastp3d', 0),
                'lastp4d': row_dict.get('lastp4d', 0),
                'lastp5d': row_dict.get('lastp5d', 0),
                'lasto1d': row_dict.get('lasto1d', 0),
                'lasto2d': row_dict.get('lasto2d', 0),
                'lasto3d': row_dict.get('lasto3d', 0),
                'lasto4d': row_dict.get('lasto4d', 0),
                'lasto5d': row_dict.get('lasto5d', 0),
                'highest_since_buy': row_dict.get('high', 0),
                'cost_price': row_dict.get('lastp3d', 0),  # 默认三天前收盘价为成本
                'hvolume': row.get('hv', 0),
                'lvolume': row.get('lv', 0),
            }
            # 💥 [NEW] 构建增强理由 (包含 TD/Top 信息)
            day_df = pd.DataFrame()
            
            if hasattr(self, 'live_strategy') and self.live_strategy:
                # 1. 获取日线缓存
                cache_key = f"{code}_d"
                day_df = self.live_strategy.daily_history_cache.get(cache_key, pd.DataFrame())
                if day_df.empty:
                    day_df = self.live_strategy.daily_history_cache.get(code, pd.DataFrame())
                
                # 2. 获取当前仓位状态
                monitors = self.live_strategy.get_monitors()
                actual_key = code
                if code not in monitors:
                    for k in monitors.keys():
                        if k.startswith(code):
                            actual_key = k
                            break
                if actual_key in monitors:
                    current_phase_obj = monitors[actual_key].get('trade_phase', "IDLE")
                    
            enriched_reason = result.get('reason', '')
            if not day_df.empty:
                from daily_top_detector import detect_top_signals
                top_info = detect_top_signals(day_df, row_dict)
                td_setup = day_df.iloc[-1].get('td_setup', 0)
                enriched_reason = f"{enriched_reason} | TD:{td_setup} Top:{top_info['score']}"
                if top_info['signals']:
                    enriched_reason += f" ({'/'.join(top_info['signals'])})"

            # 创建模拟参数设置小窗口
            sim_win = tk.Toplevel(win)
            sim_win.title(f"模拟成交设置 - {name}")
            sim_win_id = '模拟成交设置'
            sim_win.geometry("350x480") 
            sim_win.transient(win)
            sim_win.grab_set()
            self.load_window_position(sim_win, sim_win_id, default_width=350, default_height=480)
            main_frm = tk.Frame(sim_win, padx=20, pady=10)
            main_frm.pack(fill="both", expand=True)
            
            tk.Label(main_frm, text=f"股票: {name} ({code})", font=("Arial", 11, "bold")).pack(pady=(0,5))
            
            # --- 资金与仓位管理 ---
            tk.Label(main_frm, text="模拟可用本金 (元):").pack(anchor="w")
            total_cap_var = tk.DoubleVar(value=100000.0)
            entry_cap = tk.Entry(main_frm, textvariable=total_cap_var)
            entry_cap.pack(fill="x", pady=2)

            # 动作选择
            tk.Label(main_frm, text="成交动作:").pack(anchor="w")
            action_var = tk.StringVar(value=action if action in ['买入', '卖出', '止损', '止盈'] else '买入')
            action_combo = ttk.Combobox(main_frm, textvariable=action_var, values=['买入', '卖出', '止损', '止盈'], state="readonly")
            action_combo.pack(fill="x", pady=2)
            
            # 价格输入
            tk.Label(main_frm, text="成交价格:").pack(anchor="w")
            price_var = tk.DoubleVar(value=round(float(price), 3))
            entry_price = tk.Entry(main_frm, textvariable=price_var)
            entry_price.pack(fill="x", pady=2)

            # 比例快捷键
            ratio_frm = tk.Frame(main_frm)
            ratio_frm.pack(fill="x", pady=5)
            
            def calc_and_set_amount(r):
                try:
                    p = price_var.get()
                    cap = total_cap_var.get()
                    if p > 0:
                        # 简单计算：(总本金 * 比例) / (价格 * (1 + 手续费))
                        qty = int((cap * r) / (p * 1.0003)) // 100 * 100
                        amount_var.set(max(100, qty) if r > 0 else 100)
                except:
                    pass

            tk.Label(main_frm, text="快速仓位比例:").pack(anchor="w")
            btn_box = tk.Frame(main_frm)
            btn_box.pack(fill="x")
            for label, r in [("1/10",0.1), ("1/5",0.2), ("1/3",0.33), ("1/2",0.5), ("全仓",1.0)]:
                tk.Button(btn_box, text=label, command=lambda val=r: calc_and_set_amount(val), font=("Arial", 8)).pack(side="left", padx=1, expand=True, fill="x")
            
            # 数量输入
            tk.Label(main_frm, text="最后成交数量 (股):", font=("Arial", 9, "bold")).pack(anchor="w", pady=(5,0))
            amount_var = tk.IntVar(value=100)
            entry_amount = tk.Entry(main_frm, textvariable=amount_var, bg="#fffde7")
            entry_amount.pack(fill="x", pady=5)
            def on_close(event=None):
                self.save_window_position(sim_win, sim_win_id)
                sim_win.destroy()

            def submit_sim():
                try:
                    s_action = action_var.get()
                    s_price = price_var.get()
                    s_amount = amount_var.get()
                    
                    if s_price <= 0 or s_amount <= 0:
                        raise ValueError("价格和数量必须大于0")
                        
                    confirm_msg = f"确定以价格 {s_price} {s_action} {s_amount}股 [{name}] 吗?"
                    if messagebox.askyesno("模拟交易确认", confirm_msg, parent=sim_win):
                        self.live_strategy.trading_logger.record_trade(
                            code, name, s_action, s_price, s_amount,
                            reason=enriched_reason
                        )
                        messagebox.showinfo("成功", f"模拟成交已记录: {s_action} {name} @ {s_price}", parent=sim_win)
                        on_close()
                except Exception as e:
                    messagebox.showerror("错误", f"输入无效: {e}", parent=sim_win)
                    on_close()
            tk.Button(main_frm, text="🔥 执行模拟成交并记入统计", command=submit_sim, 
                      bg="#ffecb3", font=("Arial", 10, "bold"), pady=10).pack(fill="x", pady=10)
            
            tk.Button(main_frm, text="放弃取消", command=sim_win.destroy).pack(fill="x")
            
            
            sim_win.bind("<Escape>", on_close)
            sim_win.protocol("WM_DELETE_WINDOW", on_close)

        tk.Button(btn_frame, text="🚀 模拟成交设置", command=run_simulation, 
                 bg="#ccff90", fg="#333", font=("Arial", 10, "bold"), width=15).pack(side='left', padx=5)

        tk.Button(btn_frame, text="关闭 (ESC)", command=lambda: on_close(), 
                 width=12).pack(side='left', padx=5)

        def on_close(event=None):
            self.save_window_position(win, window_id)
            win.destroy()
            self.strategy_report_win = None
            
        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)
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

    def _run_sbc_test_from_tk(self, stock_code, use_live=False, event=None):
        """从 TK 界面触发 SBC 信号验证"""
        if not hasattr(self, 'sector_bidding_panel') or not self.sector_bidding_panel:
            # 如果面板还没初始化，尝试动态加载并执行
            try:
                from sector_bidding_panel import SectorBiddingPanel
                self.sector_bidding_panel = SectorBiddingPanel(main_window=self)
                # 面板不需要显示，仅使用其内部的线程管理和 HDF5 锁
            except Exception as e:
                logger.error(f"Failed to load SectorBiddingPanel: {e}")
                import tkinter.messagebox as messagebox
                messagebox.showerror("错误", f"无法加载 SBC 验证模块: {e}")
                return

        # 从 df_all 提取昨日 OHLC 详情，注入参考线
        extra_lines = {}
        if hasattr(self, 'df_all') and stock_code in self.df_all.index:
            try:
                row = self.df_all.loc[stock_code]
                row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                extra_lines = {
                    'last_close': float(row_dict.get('lastp1d', 0)),
                    'last_high':  float(row_dict.get('lasth1d', 0)),
                    'last_low':   float(row_dict.get('lastl1d', 0)),
                    'high4':      float(row_dict.get('high4', 0)),
                    'df_all_row': row_dict  # 完整透传给 verify_sbc_pattern
                }
            except Exception as e:
                logger.warning(f"Failed to extract extra_lines for {stock_code}: {e}")

        # [NEW] 检查 Ctrl/Shift 修饰键，支持多开
        is_multi = False
        if event is not None:
            # Tkinter state: 0x4=Ctrl, 0x1=Shift
            is_multi = bool(event.state & (0x0004 | 0x0001))

        # 调用 PyQt 面板中的测试逻辑 (已重构支持传入 code 和 extra_lines)
        self.sector_bidding_panel._run_sbc_test(use_live, code=stock_code, extra_lines=extra_lines, is_multi=is_multi)
        logger.debug(f"SBC {'Live' if use_live else 'Replay'} test triggered for {stock_code} with extra_lines: {extra_lines}")

    def add_stock_remark(self, code, name):
        """添加备注 - 使用自定义窗口支持多行"""
        try:
            win = tk.Toplevel(self)
            win.title(f"添加备注 - {name} ({code})")
            
            # --- 窗口定位: 右下角在鼠标附近 ---
            w, h = 550, 320
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            pos_x, pos_y = mx - w - 20, my - h - 20
            pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            win.minsize(480, 260)
            # Label
            tk.Label(
                win,
                text="请输入备注/心得 (支持多行/粘贴，Ctrl+Enter保存):"
            ).pack(anchor="w", padx=10, pady=5)

            # Text
            text_area = tk.Text(
                win,
                wrap="word",
                height=6,
                font=("Arial", 10)
            )
            text_area.pack(
                side="top",
                fill="both",
                expand=True,
                padx=10,
                pady=5
            )

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
            btn_frame.pack(side="bottom", fill="x", pady=10)   # ★ 关键
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
            
            # [FIX] 确保新窗口置顶并获得焦点
            win.lift()
            win.focus_force()
            
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
                # txt.config(state="disabled") 
                
                def copy_content():
                    try:
                        win.clipboard_clear()
                        win.clipboard_append(content)
                        messagebox.showinfo("提示", "内容已复制", parent=d_win)
                    except:
                        pass
                def save_edit():
                    new_content = txt.get("1.0", "end-1c").strip()
                    if not new_content:
                        messagebox.showwarning("提示", "内容不能为空", parent=d_win)
                        return

                    # 找到对应 remark
                    for r in self.handbook.get_remarks(code):
                        if r['time'] == time_str:
                            # 假设 handbook 支持 update
                            self.handbook.update_remark(code, r['timestamp'], new_content)
                            break

                    # 同步更新列表显示（只更新概要）
                    short = new_content.replace('\n', ' ')
                    if len(short) > 50:
                        short = short[:50] + "..."
                    tree.item(tree.selection()[0], values=(time_str, short))
                    toast_message(d_win, "成功备注已更新")

                btn_frame = tk.Frame(d_win)
                btn_frame.pack(pady=5)
                tk.Button(btn_frame, text="保存修改", command=lambda: save_edit()).pack(side="left", padx=10)
                tk.Button(btn_frame, text="复制全部", command=copy_content).pack(side="left", padx=10)
                tk.Button(btn_frame, text="关闭 (ESC)", command=d_win.destroy).pack(side="left", padx=10)
            
            remarks = self.handbook.get_remarks(code)
            remark_map = {r['time']: r['content'] for r in remarks}

            def on_double_click(event):
                item = tree.selection()
                if not item:
                    return

                values = tree.item(item[0], "values")
                time_str = values[0]

                full_content = remark_map.get(time_str)

                if full_content:
                    show_detail_window(time_str, full_content, event.x_root, event.y_root)

            tree.bind("<Double-1>", on_double_click)

            def on_double_click_slow(event):
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
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                    self.open_visualizer(stock_code)

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
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                    self.open_visualizer(stock_code)
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
                # txt.config(state="disabled")  # ⭐ [MOD] 允许编辑
                
                def save_edit_all():
                    new_content = txt.get("1.0", "end-1c").strip()
                    if not new_content:
                        messagebox.showwarning("提示", "内容不能为空", parent=d_win)
                        return

                    # 1. 查找对应的备注并更新
                    target_ts = None
                    # 注意：总览列表里可能有同名不同时间的，所以根据 code 和 time_str 定位
                    for r in self.handbook.get_remarks(code):
                        if r['time'] == time_str:
                            target_ts = r['timestamp']
                            break
                    
                    if target_ts:
                        # 更新数据库
                        self.handbook.update_remark(code, target_ts, new_content)
                        
                        # 2. 更新总览列表的 preview
                        short = new_content.replace('\n', ' ')
                        if len(short) > 60:
                            short = short[:60] + "..."
                        
                        item = tree.selection()
                        if item:
                            # 确定选中的确实是当前正在编辑的这一行 (防止用户在编辑时切换了选中项)
                            curr_vals = tree.item(item[0], "values")
                            if curr_vals[0] == time_str and curr_vals[1] == code:
                                tree.item(item[0], values=(time_str, code, name, short))
                        
                        toast_message(d_win, "成功：手札内容已更新")
                        d_win.after(500, d_win.destroy)
                    else:
                        messagebox.showerror("错误", "无法定位原始记录，保存失败", parent=d_win)

                btn_frame = tk.Frame(d_win)
                btn_frame.pack(pady=5)
                
                tk.Button(btn_frame, text="保存修改", command=save_edit_all, bg="#e8f5e9").pack(side="left", padx=10)
                tk.Button(btn_frame, text="退出 (Esc)", command=d_win.destroy).pack(side="left", padx=10)

            def delete_selected_handbook(event=None):

                # 如果没有选中行，尝试选中第一条
                if not tree.selection():
                    children = tree.get_children()
                    if not children:
                        return
                    tree.selection_set(children[0])
                    tree.focus(children[0])
                    tree.see(children[0])
                    tree.focus_set()  # 保证键盘事件生效

                item = tree.selection()
                # if not item:
                #     return

                item_id = item[0]
                values = tree.item(item_id, "values")
                target_code = values[1]
                target_time = values[0]
                target_name = values[2]
                if not messagebox.askyesno(
                    "确认删除",
                    f"确定要删除以下手札吗？\n\n"
                    f"股票：{target_name} ({target_code})\n"
                    f"时间：{target_time}"
                ):
                    return

                try:
                    # 删除前计算下一条
                    next_item = tree.next(item_id) or tree.prev(item_id)

                    # 🔴 真正删除数据
                    ok = self.handbook.delete_remark(target_code, target_time)
                    if not ok:
                        messagebox.showwarning(
                            "删除失败",
                            "未在数据中找到该手札（可能时间不匹配）"
                        )
                        return

                    # UI 删除
                    tree.delete(item_id)

                    toast_message(
                        self,
                        f"已删除手札：{target_name} {target_time}"
                    )

                    # ✅ 修改4：删除后自动选中下一行
                    if next_item and tree.exists(next_item):
                        tree.selection_set(next_item)
                        tree.focus(next_item)
                        tree.see(next_item)
                    else:
                        children = tree.get_children()
                        if children:
                            tree.selection_set(children[0])
                            tree.focus(children[0])
                            tree.see(children[0])

                    win.lift()
                    win.focus_force()
                    tree.focus_set()  # 保证键盘焦点仍在 treeview

                except Exception as e:
                    logger.error(f"delete handbook error: {e}")
                    messagebox.showerror("错误", f"删除失败: {e}")


            tree.bind("<Button-1>", on_handbook_on_click)
            tree.bind("<Button-3>", on_handbook_right_click)
            tree.bind("<Double-1>", on_handbook_double_click)
            tree.bind("<<TreeviewSelect>>", on_handbook_tree_select) 
            # ✅ 新增：Delete 键删除
            tree.bind("<Delete>", delete_selected_handbook)
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
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("提示", "实时监控模块尚未启动")
            return

        # 1. 唯一性检查
        monitors = self.live_strategy.get_monitors()
        existing_key = None
        if code in monitors:
            existing_key = code
        else:
            for k in monitors.keys():
                if k.split('_')[0] == code:
                    existing_key = k
                    break
        
        if existing_key:
            if not messagebox.askyesno("重复提示", f"{name}({code}) 已在监控列表中！\n\n是否继续添加新规则？\n(选'否'则取消)"):
                return

        try:
            win = tk.Toplevel(self)
            win.title(f"添加语音预警 - {name} ({code})")
            window_id = "添加语音预警"
            self.load_window_position(win, window_id, default_width=900, default_height=650)
            # --- 布局 ---
            main_frame = tk.Frame(win)
            main_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            left_frame = tk.Frame(main_frame) 
            left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
            
            right_frame = tk.LabelFrame(main_frame, text="参考数据 (点击自动填入)", width=380)
            right_frame.pack(side="right", fill="both", padx=(10, 0))
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
            
            tk.Label(left_frame, text=f"当前价格: {curr_price:.2f}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
            tk.Label(left_frame, text=f"当前涨幅: {curr_change:.2f}%", font=("Arial", 10), fg="#b71c1c" if curr_change>=0 else "#00695c").pack(pady=5, anchor="w")
            
            tk.Label(left_frame, text="选择监控类型:").pack(anchor="w", pady=(15, 5))
            
            type_var = tk.StringVar(value="price_up")
            e_val_var = tk.StringVar(value=f"{curr_price:.2f}") # 绑定Entry变量
            
            def on_type_change():
                """切换类型时更新默认值"""
                t = type_var.get()
                if t == "change_up":
                     # 切换到涨幅时，填入当前涨幅方便修改，或者清空
                     e_val_var.set(f"{curr_change:.2f}")
                else:
                     # 切换回价格
                     e_val_var.set(f"{curr_price:.2f}")

            types = [("价格突破 (Price >=)", "price_up"), 
                     ("价格跌破 (Price <=)", "price_down"),
                     ("涨幅超过 (Change% >=)", "change_up")]
            
            for text, val in types:
                tk.Radiobutton(left_frame, text=text, variable=type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)
                
            tk.Label(left_frame, text="选择监控周期:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
            
            # 获取当前周期
            current_resample = self.global_values.getkey("resample") or 'd'
            resample_var = tk.StringVar(value=current_resample)
            
            resample_combo = ttk.Combobox(left_frame, textvariable=resample_var, width=10)
            resample_combo['values'] = ['d', 'w', 'm', '30', '60']
            resample_combo.pack(anchor="w", padx=10, pady=2)

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
                        tags = self.get_stock_info_text(code)
                        resample = resample_var.get()
                        self.live_strategy.add_monitor(code, name, rtype, val, tags=tags, resample=resample, create_price=curr_price)
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

            logger.warning("⚠️ RealtimeDataService 加载失败，部分功能可能不可用")

    def on_realtime_service_ready(self, callback: Callable[[], None]) -> None:
        """
        注册回调函数，在 RealtimeDataService 就绪时调用
        如果已就绪则立即执行回调
        """
        if self._realtime_service_ready and self.realtime_service:
            # 已就绪，立即执行
            try:
                callback()
            except Exception as e:
                logger.warning(f"Realtime ready callback failed: {e}")
        else:
            # 尚未就绪，加入队列
            if hasattr(self, '_realtime_ready_callbacks'):
                self._realtime_ready_callbacks.append(callback)
            else:
                self._realtime_ready_callbacks = [callback]

    def _init_live_strategy(self):
        """延迟初始化策略模块"""
        if getattr(self, "live_strategy", None) is not None:
            logger.warning("⚠️ live_strategy already initialized, skip")
            return
        try:
            # 注意：realtime_service 可能还在异步加载中，传入当前值（可能为 None）
            # 稍后在 _on_realtime_service_ready 中会注入
            self.live_strategy = StockLiveStrategy(self,alert_cooldown=alert_cooldown,
                                                   voice_enabled=self.voice_var.get(),
                                                   realtime_service=self.realtime_service)
            # 如果实时服务还没准备好，则注册回调以便后续自动注入
            if not self.realtime_service:
                self.on_realtime_service_ready(lambda: setattr(self.live_strategy, 'realtime_service', self.realtime_service))
                logger.info("StockLiveStrategy 已初始化 (RealtimeDataService 将在就绪时自动注入)")
            else:
                logger.info("RealtimeDataService injected into StockLiveStrategy.")
            
            # 注册报警回调
            self.live_strategy.alert_callback = self._safe_on_voice_alert
            # 注册语音开始播放的回调，用于同步闪烁
            if hasattr(self.live_strategy, '_voice'):
                self.live_strategy._voice.on_speak_start = self.on_voice_speak_start
                self.live_strategy._voice.on_speak_end = self.on_voice_speak_end
            
            # 🚀 [NEW] 注册策略完成回调，实现“数据更新后回调”需求
            if hasattr(self.live_strategy, 'strategy_callback'):
                self.live_strategy.strategy_callback = lambda df: self._schedule_after(0, self.refresh_tree, df)
            
            logger.info("✅ 实时监控策略模块已启动 (已挂载实时刷新回调)")
        except Exception as e:
            logger.error(f"Failed to init live strategy: {e}")

    def _safe_on_voice_alert(self, code, name, msg):
        """
        【唯一入口】策略线程调用此函数，将任务安全投递给主线程
        """
        try:
            # [FIX] 严禁在子线程直接调用 after，改用 dispatch_queue 投递
            if hasattr(self, 'tk_dispatch_queue'):
                task = lambda: self._on_voice_alert_ui(code, name, msg)
                self.tk_dispatch_queue.put(task)
            else:
                # 兼容模式
                self._schedule_after(0, self._on_voice_alert_ui, code, name, msg)
        except Exception:
            pass

    def _on_voice_alert_ui(self, code, name, msg):
        """
        【UI 线程执行】执行真正的逻辑判断和弹窗
        """
        # 1. 快速判断拦截
        alert_var = getattr(self, 'alert_popup_var', None)
        if not alert_var or not alert_var.get():
            logger.debug(f"Alert popup suppressed for {code} ({name}) by user setting.")
            return # 仅在 INFO 级别以上才记录，减少 IO 开销

        # 2. 执行弹窗 (此处已在主线程)
        try:
            self._show_alert_popup(code, name, msg)
        except Exception as e:
            logger.error(f"Popup error: {e}")

    # 废弃 on_voice_alert，或者让它只负责日志记录，不负责逻辑

    # @with_log_level(LoggerFactory.INFO)
    # def on_voice_alert(self, code, name, msg):
    #     """
    #     处理语音报警触发: 弹窗显示股票详情
    #     """
    #     # 如果禁用了弹窗，则只在此处拦截 UI 创建，语音由策略端独立触发
    #     if not getattr(self, 'alert_popup_var', None) or not self.alert_popup_var.get():
    #         logger.info(f"Alert popup suppressed for {code} ({name}) by user setting.")
    #         return
        
    #     self._show_alert_popup(code, name, msg)
    #     # 必须回到主线程操作 GUI
    #     # self._schedule_after(0, lambda: self._show_alert_popup(code, name, msg))

    def open_blacklist_manager(self):
        """打开黑名单管理窗口 (增强版: 逻辑优化 + 布局精简)"""
        if not self.live_strategy:
            messagebox.showinfo("提示", "策略引擎未启动")
            return
            
        win = tk.Toplevel(self)
        win.title("黑名单/已忽略报警管理")
        win.geometry("900x650")
        
        # 窗口位置标识
        window_id = "BlacklistManager"
        
        # 加载位置
        if hasattr(self, 'load_window_position'):
            self.load_window_position(win, window_id, default_width=900, default_height=650)
        else:
            self.center_window(win, 900, 650)
        
        main_frame = ttk.Frame(win, padding=5)
        main_frame.pack(fill="both", expand=True)
        
        # --- [TOP] 综合操作工具栏 ---
        top_bar = ttk.LabelFrame(main_frame, text="操作中心", padding=5)
        top_bar.pack(fill="x", pady=2)
        
        # 1. 筛选区
        ttk.Label(top_bar, text="日期:").pack(side="left", padx=2)
        today_str = datetime.now().strftime('%Y-%m-%d')
        dates = ["全部"]
        db_dates = []
        if hasattr(self.live_strategy, 'trading_logger'):
            db_dates = self.live_strategy.trading_logger.get_blacklist_dates()
            dates.extend(db_dates)
            
        default_val = today_str if today_str in db_dates else "全部"
        date_var = tk.StringVar(value=default_val)
        date_combo = ttk.Combobox(top_bar, textvariable=date_var, values=dates, state="readonly", width=12)
        date_combo.pack(side="left", padx=2)
        
        # 2. 核心操作按钮
        def refresh(event=None):
            for i in tree.get_children():
                tree.delete(i)
            selected_date = date_var.get()
            blacklist = self.live_strategy.get_blacklist(date=selected_date)
            sorted_items = sorted(blacklist.items(), key=lambda x: x[1].get('date', ''), reverse=True)
            for code, info in sorted_items:
                tree.insert("", "end", values=(code, info.get('name', ''), info.get('date', ''), info.get('reason', ''), info.get('hit_count', 0)))
            stats_var.set(f"筛选日期: {selected_date}  |  记录总数: {len(sorted_items)}  |  系统时间: {time.strftime('%H:%M:%S')}")
            
        date_combo.bind("<<ComboboxSelected>>", refresh)
        ttk.Button(top_bar, text="🔍 查询", width=8, command=refresh).pack(side="left", padx=5)
        
        ttk.Separator(top_bar, orient="vertical").pack(side="left", fill="y", padx=10)
        
        def restore_selected():
            sel = tree.selection()
            if not sel: return messagebox.showinfo("提示", "请先选择记录")
            restored = 0
            for item in sel:
                code = tree.item(item, "values")[0]
                if self.live_strategy.remove_from_blacklist(code): 
                    restored += 1
            if restored > 0: 
                refresh()
                messagebox.showinfo("成功", f"已成功恢复 {restored} 只股票的报警信号")
            else:
                messagebox.showwarning("提示", "未能成功恢复，请刷新后重试")

        ttk.Button(top_bar, text="✅ 恢复报警", command=restore_selected).pack(side="left", padx=2)
        
        def delete_permanently():
            sel = tree.selection()
            if not sel: return
            if not messagebox.askyesno("确认", "确定彻底删除选中记录吗？\n(这不仅会删除历史，也会恢复相应股票的实时报警)"): return
            deleted = 0
            for item in sel:
                code = tree.item(item, "values")[0]
                if self.live_strategy.remove_from_blacklist(code):
                    deleted += 1

            if deleted > 0: 
                refresh()
                messagebox.showinfo("完成", f"已物理删除 {deleted} 条黑名单记录")
            else:
                messagebox.showwarning("提示", "删除失败或记录已不存在")

        ttk.Button(top_bar, text="🗑️ 物理删除", command=delete_permanently).pack(side="left", padx=2)

        # 3. 位置同步与关闭
        ttk.Button(top_bar, text="✖ 关闭", command=win.destroy).pack(side="right", padx=2)
        
        def save_pos():
            if hasattr(self, 'save_window_position'):
                self.save_window_position(win, window_id)
                toast_message(self, "位置已保存")
        ttk.Button(top_bar, text="💾 保存位置", command=save_pos).pack(side="right", padx=2)

        def load_pos():
            if hasattr(self, 'load_window_position'): self.load_window_position(win, window_id)
        ttk.Button(top_bar, text="🔄 还原位置", command=load_pos).pack(side="right", padx=2)

        # --- [MIDDLE] 数据表格 ---
        cols = ("code", "name", "date", "reason", "hits")
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=2)
        
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        
        # 排序逻辑定义
        sort_state = {"col": "date", "reverse": True} # 初始按日期倒序
        def tree_sort_column(tv, col, reverse):
            l = [(tv.set(k, col), k) for k in tv.get_children('')]
            # 数字列特殊处理
            if col == 'hits':
                l.sort(key=lambda t: int(t[0] or 0), reverse=reverse)
            else:
                l.sort(reverse=reverse)
            for index, (val, k) in enumerate(l):
                tv.move(k, '', index)
            sort_state["col"] = col
            sort_state["reverse"] = reverse
            # 更新表头显示排序箭头 (可选)
            for c in cols:
                tv.heading(c, text=tv.heading(c)['text'].replace(' ↑','').replace(' ↓',''))
            arrow = ' ↓' if reverse else ' ↑'
            tv.heading(col, text=tv.heading(col)['text'] + arrow, command=lambda: tree_sort_column(tv, col, not reverse))

        for col, head in zip(cols, ["代码", "名称", "加入日期", "忽略原因", "触发次数"]):
            tree.heading(col, text=head, command=lambda _c=col: tree_sort_column(tree, _c, False))
            width = 80 if col in ["code", "hits"] else (100 if col == "name" else (120 if col == "date" else 300))
            tree.column(col, width=width, anchor="center" if col != "reason" else "w")
            
        tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=sb.set); sb.pack(fill="y", side="right")
        
        # --- [BOTTOM] 底部状态信息栏 ---
        status_bar = ttk.Frame(main_frame, relief="sunken", padding=(5, 2))
        status_bar.pack(fill="x", side="bottom")
        stats_var = tk.StringVar(value="正在初始化数据...")
        ttk.Label(status_bar, textvariable=stats_var, font=("Consolas", 9), foreground="#225588").pack(side="left")

        # 联动与生命周期
        def on_select(event=None):
            sel = tree.selection()
            if sel: 
                code = tree.item(sel[0], "values")[0]
                # 触发基础联动
                self.on_code_click(code)
                # 强制触发可视化联动 (无视 select_code 限制)
                if hasattr(self, 'vis_var') and self.vis_var.get():
                    # 临时重置去重缓存以确保响应
                    self.vis_select_code = None 
                    self.open_visualizer(code)

        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<Double-1>", lambda e: on_select()) # 增加双击联动支持
        tree.bind("<Up>", lambda e: win.after(10, on_select))
        tree.bind("<Down>", lambda e: win.after(10, on_select))
        
        def on_win_close():
            if hasattr(self, 'save_window_position'): self.save_window_position(win, window_id)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_win_close)
        
        refresh()

    def flash_taskbar(self):
        """让主窗口任务栏图标闪烁，提示用户焦点"""
        try:
            # 仅在 Windows 有效
            if sys.platform.startswith('win'):
                hwnd = self.winfo_id() 
                # FlashWindow(hwnd, bInvert) - bInvert=True 表示切换激活状态外观
                ctypes.windll.user32.FlashWindow(hwnd, True)
        except Exception as e:
            pass

    def on_voice_speak_start(self, code):
        """[Enhanced] 语音开始播放时的回调，用于触发窗口视觉效果（震动+闪烁）"""
        if not code or getattr(self, '_is_closing', False):
            return

        def sync_task():
            # A. 确保容器存在
            if not hasattr(self, '_voice_start_jobs'):
                self._voice_start_jobs = {}

            # B. 幂等性：如果该代码之前的启动任务还在排队（极端情况），先通过 ID 取消它
            old_job = self._voice_start_jobs.get(str(code))
            if old_job:
                try: self.after_cancel(old_job)
                except: pass

            # C. 定义实际触发视觉效果的子任务
            def trigger_visual():
                if str(code) in self._voice_start_jobs:
                    del self._voice_start_jobs[str(code)]
                self._trigger_alert_visual_effects(str(code), start=True)

            # D. 执行任务栏闪烁
            self.flash_taskbar()

            # E. [DIRECT] 恢复即时播报同步，移除长延时，仅留极短缓冲以适配 Tcl 调度
            self._voice_start_jobs[str(code)] = self._schedule_after(20, trigger_visual)

        try:
            if hasattr(self, 'tk_dispatch_queue'):
                self.tk_dispatch_queue.put(sync_task)
            else:
                self._schedule_after(0, sync_task)
        except Exception:
            pass

        
    # def on_voice_speak_start(self, code):
    #     if not code or getattr(self, '_is_closing', False):
    #         return

    #     def task():
    #         self.flash_taskbar()
    #         self._trigger_alert_visual_effects(str(code), start=True)

    #     if hasattr(self, 'tk_dispatch_queue'):
    #         self.tk_dispatch_queue.put(task)
    #     else:
    #         self._schedule_after(0, task)

    def on_voice_speak_end(self, code):
        """语音播报结束的回调"""
        if not code: return
        # 检查程序是否正在退出
        if getattr(self, '_is_closing', False): return
        
        def sync_stop():
            # ⭐ [FIX] 彻底解决播报完还在晃动的关键：中途撤销尚未触发的启动任务
            if hasattr(self, '_voice_start_jobs'):
                old_job = self._voice_start_jobs.get(str(code))
                if old_job:
                    try: 
                        self.after_cancel(old_job)
                        # logger.debug(f"[Linkage] Cancelled pending start for {code} as it finished early")
                    except: pass
                    del self._voice_start_jobs[str(code)]
            
            # 执行停止震动逻辑
            self._trigger_alert_visual_effects(str(code), start=False)

        try:
            if hasattr(self, 'tk_dispatch_queue'):
                self.tk_dispatch_queue.put(sync_stop)
            else:
                self._schedule_after(0, sync_stop)
        except Exception:
            pass


    def _trigger_alert_visual_effects(self, code, start=True, retry_count=0):
        """根据代码查找窗口并触发视觉效果，并确保窗口可见
        
        Args:
            code: 股票代码
            start: True=开始播报, False=结束播报
            retry_count: 当前重试次数（内部使用）
        """
        win = None
        if not hasattr(self, 'code_to_alert_win'): return
        # ⭐ [RE-INITIALIZED] 联动增强：快速创建逻辑 (Fast-track)
        # A. 优先尝试精确匹配 (Speed Boost)
        search_code = str(code).strip()
        win = self.code_to_alert_win.get(search_code)
        
        if not win:
             # B. 模糊遍历匹配 (处理 .SH/SZ 等情况)
             for k, w in self.code_to_alert_win.items():
                 str_k = str(k).strip()
                 if search_code in str_k or str_k in search_code:
                     if w.winfo_exists():
                         win = w
                         break
             
             # B. [RESTORED] 快速插队创建
             if not win and start:
                 for i, item in enumerate(self._alert_queue):
                     q_code = str(item[0]).strip()
                     if q_code == code or q_code.startswith(code) or code.startswith(q_code):
                         if self._recycle_alert_window(code):
                             logger.info(f"[Linkage] Fast-track UI creation for voice sync: {code}")
                             q_code, q_name, q_msg = self._alert_queue.pop(i)
                             self._create_single_alert_popup(q_code, q_name, q_msg)
                             win = self.code_to_alert_win.get(q_code)
                         break
        
        # C. [NEW] 测试报警支持
        if not win and code == "TEST" and hasattr(self, 'active_alerts') and self.active_alerts:
            for w in reversed(self.active_alerts):
                if w.winfo_exists():
                    win = w
                    break
                      
        if win and win.winfo_exists():
            if start:
                # ⭐ 关键增强：开始播放语音时，确保窗口浮现并置顶
                logger.debug(f"[Linkage] Triggering visual effects for: {win.stock_code if hasattr(win, 'stock_code') else code}")
                try:
                    if not win.winfo_ismapped():
                        win.deiconify()
                    win.lift()
                    win.attributes("-topmost", True)
                    
                    # ⭐ 视觉同步：修改标题提示正在播报
                    if not hasattr(win, '_original_title'):
                        win._original_title = win.title()
                    win.title(f"▶️ 正在播报 - {win._original_title}")
                except:
                    pass
                
                if hasattr(win, 'start_visual_effects'):
                    win.start_visual_effects()
            else:
                # ⭐ 恢复标题
                try:
                    if hasattr(win, '_original_title'):
                        win.title(win._original_title)
                except:
                    pass
                
                if hasattr(win, 'stop_visual_effects'):
                    win.stop_visual_effects()
        elif start:
            # ⭐ [FIX] 窗口可能正在创建中,实现重试机制
            MAX_RETRIES = 12  # 增加到 12 次 (约 2.4 秒)
            RETRY_DELAY_MS = 200  # 增加到 200ms
            
            if retry_count < MAX_RETRIES:
                # 延迟后重试
                logger.debug(f"[Linkage] Window for '{code}' not found, retrying ({retry_count + 1}/{MAX_RETRIES})...")
                self._schedule_after(RETRY_DELAY_MS, lambda: self._trigger_alert_visual_effects(code, start=True, retry_count=retry_count + 1))
            else:
                # 达到最大重试次数,记录警告
                self._mismatch_warned_codes = getattr(self, '_mismatch_warned_codes', set())
                if str(code) not in self._mismatch_warned_codes:
                    # 简化警告信息,只打印窗口数量,避免日志冗余
                    available_count = len(self.code_to_alert_win)
                    logger.debug(f"[Linkage] Mismatch: Voice speaking code '{code}', but no matching alert window found. ({available_count} windows registered)")
                    self._mismatch_warned_codes.add(str(code))

    def _update_alert_positions(self, immediate=False):
        """⭐ [OPTIMIZED] 带有防抖功能的报警弹窗排列"""
        if self._update_pos_timer is not None:
            self.after_cancel(self._update_pos_timer)
            self._update_pos_timer = None
        
        if immediate:
            self._update_alert_positions_real()
        else:
            self._update_pos_timer = self._schedule_after(100, self._update_alert_positions_real)

    def _update_alert_positions_real(self):
        """真正的重新排列逻辑"""
        self._update_pos_timer = None
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
            
        # 定义固定的窗口尺寸和边距
        alert_width, alert_height = 400, 180 
        margin = 10
        taskbar_height = 100 # 避开任务栏高度
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # 根据屏幕宽度计算最大列数
        max_cols = (screen_width - margin) // (alert_width + margin)
        if max_cols < 1: 
            max_cols = 1
        
        # 清理已销毁的窗口
        self.active_alerts = [win for win in self.active_alerts if win.winfo_exists()]

        # 限制最大行数以避免超出屏幕范围
        max_rows = (screen_height - taskbar_height - margin) // (alert_height + margin)
        
        # --- 分离受控窗口和脱离窗口 ---
        managed_alerts = []
        detached_alerts = []
        for win in self.active_alerts:
            # 如果窗口处于“放大”状态，视为脱离网格管控
            if getattr(win, '_is_enlarged', False):
                detached_alerts.append(win)
            else:
                managed_alerts.append(win)
        
        # 1. 布局受控的普通窗口
        for i, win in enumerate(managed_alerts):
            if i >= max_cols * max_rows:
                # 超出显示区域，隐藏窗口
                try:
                    # 只有当窗口当前处于显示状态时才调用 withdraw()
                    if win.winfo_ismapped(): 
                         win.withdraw() 
                except Exception as e:
                    logger.error(f"无法隐藏超出范围的窗口: {e}")
                continue
            
            try:
                col = i % max_cols
                row = i // max_cols
                
                # 从右向左排列
                x = screen_width - (col + 1) * (alert_width + margin)
                y = screen_height - taskbar_height - (row + 1) * (alert_height + margin)
                
                # 使用默认尺寸
                current_width = alert_width
                current_height = alert_height
                
                win.geometry(f"{current_width}x{current_height}+{x}+{y}")
                # ⭐ 关键修复：如果在震动，同步更新震动锚点，防止窗口被拉回左上角/旧位置
                if getattr(win, 'is_shaking', False):
                    win._shake_orig_x = x
                    win._shake_orig_y = y
                    win._shake_orig_wh = f"{current_width}x{current_height}"
                    
                # 确保窗口是可见的（如果之前被隐藏了）
                if not win.winfo_ismapped():
                    win.deiconify() 
            except Exception as e:
                logger.error(f"调整索引 {i} 的警报窗口位置时出错: {e}")

        # 2. 处理脱离的窗口 (仅确保可见和保持尺寸状态，不重置位置)
        for win in detached_alerts:
            try:
                # 确保可见
                if not win.winfo_ismapped():
                    win.deiconify()
                # 位置和尺寸由用户控制，或者由 toggle_size 逻辑控制，此处不干涉
            except Exception as e:
                 logger.error(f"Check detached window error: {e}")

        # *** 层叠效果优化 ***
        # 极限优化：移除 update_idletasks()。
        # 原本是为了立即刷新位置避免视觉闪烁，但在大量弹窗时会导致 UI 线程严重卡顿。
        # Tkinter 事件循环会自动处理 geometry 变更，无需强制同步。
        # self.update_idletasks()

    def _shake_window(self, win, distance=8, interval_ms=60):
        """
        震动窗口效果 - 持续震动直到 win.is_shaking 变为 False
        :param win: 要震动的 Tkinter 窗口实例
        :param distance: 每次晃动的最大像素距离
        :param interval_ms: 两次晃动之间的延迟毫秒数 (越大越温和/慢)
        """
        if not win or not win.winfo_exists():
            return
        
        # 标记正在震动
        win.is_shaking = True
        
        def do_shake():
            # 检查窗口是否存在且是否应继续晃动
            if not win.winfo_exists() or not getattr(win, 'is_shaking', False):
                # 停止晃动时，尝试将窗口恢复到原始位置（如果可能）
                if win.winfo_exists() and not getattr(win, '_is_enlarged', False):
                     try:
                         orig_wh = getattr(win, '_shake_orig_wh', "400x180")
                         orig_x = getattr(win, '_shake_orig_x', win.winfo_x())
                         orig_y = getattr(win, '_shake_orig_y', win.winfo_y())
                         win.geometry(f"{orig_wh}+{orig_x}+{orig_y}")
                     except: 
                         pass
                return
            
            # 计算随机偏移量
            dx = random.randint(-distance, distance)
            dy = random.randint(-distance, distance)
            try:
                # ⭐ [Dynamic Anchor] 使用动态更新的锚点位置（由 _update_alert_positions_real 维护）
                orig_wh = getattr(win, '_shake_orig_wh', "400x180")
                orig_x = getattr(win, '_shake_orig_x', win.winfo_x())
                orig_y = getattr(win, '_shake_orig_y', win.winfo_y())
                win.geometry(f"{orig_wh}+{orig_x + dx}+{orig_y + dy}")
            except: 
                pass
            
            # 安排下一次晃动
            win.after(interval_ms, lambda: do_shake())

        # 捕获初始位置并填充锚点
        try:
            geom = win.geometry()
            # [FIXED] 更加鲁棒的几何信息解析，支持正负坐标
            import re
            m = re.match(r"(\d+x\d+)([+-]-?\d+)([+-]-?\d+)", geom)
            if m:
                win._shake_orig_wh = m.group(1)
                win._shake_orig_x = int(m.group(2))
                win._shake_orig_y = int(m.group(3))
                do_shake()
            else:
                # 备选方案
                win._shake_orig_wh = f"{win.winfo_width()}x{win.winfo_height()}"
                win._shake_orig_x = win.winfo_x()
                win._shake_orig_y = win.winfo_y()
                do_shake()
        except Exception:
            pass


    def close_all_alerts(self, is_manual=False):
        """
        一键批量关闭所有 active alert 窗口。
        新增强制停止当前所有语音播报的联动。
        """
        # 💥 联动核心 1：强制停止当前正在播放的 *任何* 语音
        # 💥 联动核心 1：强制停止当前正在播放的 *任何* 语音
        try:
            mgr = self._get_alert_manager()
            if mgr:
                mgr.stop_current_speech(key=None) # key=None 表示全局硬停止
                # 💥 联动核心 2：立即清空活跃列表，确保后续排队全部跳过
                mgr.sync_active_codes([]) 
        except:
            pass
        
        # 拷贝列表，防止遍历过程中被修改
        active_windows = list(getattr(self, 'active_alerts', []))

        for win in active_windows:
            try:
                # 调用 _close_alert（它内部会处理重复关闭和安全销毁）
                self._close_alert(win, is_manual=is_manual)
            except Exception as e:
                log.error(f"Failed to close alert window {win}: {e}")
        toast_message(self, "已关闭所有报警窗口")

    def _close_alert(self, win, is_manual=False):
        # 如果是自动关闭且窗口处于放大状态，则忽略关闭请求
        if not is_manual and getattr(win, '_is_enlarged', False):
            return

        if hasattr(self, 'active_alerts') and win in self.active_alerts:
            self.active_alerts.remove(win)

        # 防止重复关闭
        if getattr(win, 'is_closing', False):
            return
        win.is_closing = True

        target_code = getattr(win, 'stock_code', None)
        
        # 尝试从映射表查找（用于清理）
        if hasattr(self, 'code_to_alert_win'):
            for c, w in list(self.code_to_alert_win.items()):
                if w is win:
                    if not target_code: target_code = c
                    del self.code_to_alert_win[c]
                    break

        try:
            win.destroy()
        except Exception:
            pass

        # 使用 after_idle 确保 destroy 完成且事件循环已更新
        self.after_idle(self._update_alert_positions)

        if not target_code or not getattr(self, 'live_strategy', None):
            return

        # ✅ [新增] 如果是已经显式删除的监控，则不再执行后续的 snooze 等逻辑
        if getattr(win, '_is_deleted', False):
            logger.debug(f"Monitor for {target_code} was explicitly deleted, skipping snooze/cleanup.")
            return

        # 💥 联动核心 1：只要窗口关闭，就试强制停止播报。
        # 如果是手动点击(is_manual)，则执行全局停止 (key=None)，彻底斩断声音；
        # 如果是自动超时关闭，由于用户未干预，仅尝试停止匹配该代码的播报。

        # 取消 safety timer（如果已经触发）
        if hasattr(win, 'safety_close_timer'):
            self.after_cancel(win.safety_close_timer)
            
        try:
            mgr = self._get_alert_manager()
            if mgr:
                mgr.stop_current_speech(key=None if is_manual else target_code)
            
            # 💥 联动核心 2：同步最新的活跃代码列表，确保后续排队的该代码内容被跳过
            self._schedule_after(10, self._update_voice_active_codes)
        except:
            pass

    def _update_voice_active_codes(self):
        """同步当前屏幕上所有报警窗口的股票代码到语音管理器"""
        try:
            active_windows = list(getattr(self, 'active_alerts', []))
            valid_codes = []
            for w in active_windows:
                if hasattr(w, 'stock_code') and w.winfo_exists():
                    valid_codes.append(str(w.stock_code))
            
            mgr = self._get_alert_manager()
            if mgr:
                mgr.sync_active_codes(valid_codes)
        except:
            pass

        def _post_logic():
            try:
                if is_manual:
                    self.live_strategy.snooze_alert(target_code, cycles=pending_alert_cycles)
                
                v = getattr(self.live_strategy, '_voice', None)
                if v and hasattr(v, 'cancel_for_code'):
                    v.cancel_for_code(target_code)
            except Exception:
                pass

        threading.Thread(target=_post_logic, daemon=True).start()



    def _show_alert_popup(self, code, name, msg):
        """显示报警弹窗 (队列化逐个创建 + 同股去重 + 长度限制)"""
        # ===== 常量定义 (已移至全局) =====
        
        # ===== 初始化弹窗队列 =====
        if not hasattr(self, '_alert_queue'):
            self._alert_queue = []
            self._alert_queue_processing = False
        
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
        if not hasattr(self, 'code_to_alert_win'):
            self.code_to_alert_win = {}
        
        # ===== [MODIFIED] 1. 总报警窗口数量限制与回收策略 =====
        if len(self.active_alerts) >= MAX_TOTAL_ALERTS:
            # 尝试清理已销毁的窗口
            self.active_alerts = [w for w in self.active_alerts if w.winfo_exists()]
            
            if len(self.active_alerts) >= MAX_TOTAL_ALERTS:
                if self._recycle_alert_window(code):
                    logger.debug(f"回收窗口: {code} 窗口已达上限 {MAX_TOTAL_ALERTS}...")
                    # 成功回收了一个窗口，为新信号腾出了空间
                else:
                    return 
        
        # ===== 同股去重：如果已有弹窗，更新消息而非新建 =====
        existing_win = self.code_to_alert_win.get(code)
        if existing_win:
            try:
                if existing_win.winfo_exists():
                    existing_win.title(f"🔔 触发报警 - {name} ({code})")
                    if hasattr(existing_win, 'msg_label'):
                        existing_win.msg_label.config(text=f"⚠️{code} {msg}")
                    existing_win.lift()
                    existing_win.attributes("-topmost", True)
                    existing_win.lift()
                    existing_win.attributes("-topmost", True)
                    # [FIXED] 不在复用时震动，仅在 Voice 回调中震动
                    logger.debug(f"复用已有弹窗并购同步提醒: {code}")
                    return
            except tk.TclError:
                logger.debug(f"检测到已销毁弹窗，清理映射: {code}")
            except Exception as e:
                logger.debug(f"更新已有弹窗失败: {e}")
            
            if code in self.code_to_alert_win:
                del self.code_to_alert_win[code]
        
        # ===== [MODIFIED] 2. 队列长度限制 + 智能丢弃策略 =====
        # 只有队列满时才根据信号质量过滤
        if len(self._alert_queue) >= MAX_ALERT_POPUP_QUEUE:
            # 检查当前信号是否为高质量
            is_high_quality = any(kw in msg for kw in HIGH_PRIORITY_KEYWORDS)
            
            if is_high_quality:
                # 高质量信号：优先丢弃队列中的低质量信号
                dropped = False
                for i in range(len(self._alert_queue) - 1, -1, -1):  # 从后往前找
                    item_msg = self._alert_queue[i][2]
                    if not any(kw in item_msg for kw in HIGH_PRIORITY_KEYWORDS):
                        dropped_item = self._alert_queue.pop(i)
                        logger.info(f"队列满，丢弃低质量请求: {dropped_item[0]} {dropped_item[2][:30]}")
                        dropped = True
                        break
                
                # 如果全是高质量，丢弃最旧的（FIFO）
                if not dropped:
                    oldest = self._alert_queue.pop(0)
                    logger.warning(f"队列满且全高质量，丢弃最旧请求: {oldest[0]} {oldest[2][:30]}")
            else:
                # 低质量信号：队列满时直接丢弃 (注意：这里如果丢弃，会导致 Voice 找不到窗)
                # ⭐ [FIX] 如果启用了语音，即使低质量也入队，确保联动同步
                if hasattr(self, 'live_strategy') and getattr(self.live_strategy, 'voice_enabled', True):
                    logger.debug(f"队列满，但由于语音启用，保留低质量信号以供同步: {code}")
                else:
                    logger.debug(f"队列满，丢弃低质量信号: {code} {msg[:30]}")
                    return 
        
        # ===== [OPTIMIZED] 同股去重优化：累加消息而非直接覆盖 =====
        for item in self._alert_queue:
            if item[0] == code:
                # [FIX] 如果消息不重复，则累加显示，确保不丢失历史过程 (如：突破后触发了买入)
                if msg not in item[2]:
                    item[2] = f"{item[2]}\n{msg}"
                logger.debug(f"队列中已有同股请求，累加消息内容: {code}")
                return
        
        item = [code, name, msg]
        # ⭐ [ENHANCEMENT] 优先级插队逻辑：真趋势信号 (🚀, SBC 等) 优先弹出，不等待杂音队列
        is_priority = any(kw in msg for kw in HIGH_PRIORITY_KEYWORDS)
        if is_priority:
            self._alert_queue.insert(0, item)
            # ⭐ [FIX] 报警溯源增强：将多行消息拆分记录，确保每行都有行号标识
            msg_lines = msg.split('\n')
            logger.info(f"🚀 高价值信号插队置顶: {code} {msg_lines[0]} (队列:{len(self._alert_queue)})")
            for line in msg_lines[1:]:
                if line.strip():
                    logger.info(f"   ∟ {code} 详情: {line.strip()}")
        else:
            self._alert_queue.append(item)
            # ⭐ [FIX] 日志溯源增强：分行摘要，防止长文本换行导致元数据丢失
            msg_snip = msg.split('\n')[0][:50]
            logger.debug(f"弹窗请求加入队列: {code} {msg_snip}... 队列长度: {len(self._alert_queue)}")
        
        # 启动队列处理（如果未运行）
        if not self._alert_queue_processing:
            self._process_alert_queue()
    
    def _process_alert_queue(self):
        """处理弹窗队列，逐个创建窗口（层叠效果 + 可操作）"""
        if not hasattr(self, '_alert_queue') or not self._alert_queue:
            self._alert_queue_processing = False
            return
        
        self._alert_queue_processing = True
        
        try:
            # 取出一个请求
            item = self._alert_queue.pop(0)
            code, name, msg = item
            
            # 创建这个弹窗
            self._create_single_alert_popup(code, name, msg)
            
            # logger.debug(f"已处理一个弹窗，剩余队列: {len(self._alert_queue)}")
            
        except Exception as e:
            logger.error(f"处理弹窗队列异常: {e}")
        finally:
            # [OPTIMIZED] 将处理间隔从 100ms 缩短至 50ms，提升大规模爆发时的弹出响应速度
            if self._alert_queue:
                self._schedule_after(50, self._process_alert_queue)
            else:
                self._alert_queue_processing = False
 
    def _recycle_alert_window(self, new_code):
        """[HELPER] 尝试回收一个旧窗口为新代码腾出空间。返回 True 如果成功或无需回收。"""
        if len(self.active_alerts) < MAX_TOTAL_ALERTS:
            return True
            
        # 尝试清理已销毁的窗口
        self.active_alerts = [w for w in self.active_alerts if w.winfo_exists()]
        if len(self.active_alerts) < MAX_TOTAL_ALERTS:
            return True
            
        # logger.warning(f"总报警窗口已达上限 {MAX_TOTAL_ALERTS}，启用窗口回收逻辑...")
        victim = None
        for w in self.active_alerts:
            try:
                if w.winfo_exists() and not getattr(w, 'is_shaking', False):
                    victim = w
                    break
            except: continue
        
        if victim:
            logger.debug(f"回收旧窗口 {victim.stock_code} 以便为新信号 {new_code} 腾出空间")
            self._close_alert(victim)
            return True
        else:
            logger.warning(f"无法找到可回收窗口，丢弃/跳过信号: {new_code}")
            return False

    def _get_alert_manager(self):
        """获取语音/报警管理器实例，集成自 live_strategy，并增加可视化联动"""
        am = None
        if hasattr(self, 'live_strategy') and self.live_strategy:
            am = getattr(self.live_strategy, '_voice', None)
        
        if am and not getattr(am, '_linked_to_viz', False):
             # 🚀 [FIXED] 恢复并聚合所有播报联动逻辑：视觉提示(震动/闪烁) + 外部可视化联动
             # 避免直接覆盖造成的逻辑丢失
             def wrapped_on_start(code):
                 # 1. 触发本地视觉反馈 (震动、闪烁、任务栏提示)
                 self.on_voice_speak_start(code)
                 # 2. 触发外部可视化联动
                 self._on_alert_speak_visual_link(code)
             
             am.on_speak_start = wrapped_on_start
             am.on_speak_end = self.on_voice_speak_end # 恢复：播报结束后的状态恢复 (恢复标题等)
             am._linked_to_viz = True
             logger.info("[Linkage] AlertManager callbacks aggregated (Visual Effects + IPC).")
        return am

    def _on_alert_speak_visual_link(self, code):
        """🚀 [SIMPLIFIED] 报警联动：仅传日期"""
        if not code: return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.link_to_visualizer(code, timestamp)

    def _async_update_alert_details(self, code, win):
        """[NEW/RESTORE] 后台异步获取板块详情并更新 UI，实现秒出体验"""
        if not win or not win.winfo_exists():
            return

        def _fetch_task():
            try:
                cat_info = "获取中..."
                # 🛡️ 尽早锁定以减少竞争时间
                with self._df_lock:
                    if hasattr(self, 'df_all') and code in self.df_all.index:
                        cat_info = self.df_all.at[code, 'category']
                    else:
                        cat_info = "暂无详细信息"

                # 判定窗口是否依然存活，通过绑定的 after 安全更新 UI
                self._schedule_after(0, _update_ui, cat_info, bind_widget=win)
            except Exception as e:
                logger.error(f"Async detail fetch error for {code}: {e}")

        def _update_ui(info):
            if not win.winfo_exists(): return
            try:
                if hasattr(win, 'text_box'):
                    win.text_box.config(state="normal")
                    win.text_box.delete("1.0", "end")
                    win.text_box.insert("1.0", info)
                    win.text_box.config(state="disabled")
                
                # 更新标识符
                if hasattr(win, 'is_high_priority') and win.is_high_priority:
                     win.configure(highlightbackground="#FFD700", highlightthickness=2)
            except:
                pass

        # 启动后台线程执行耗时的 DF 查询
        threading.Thread(target=_fetch_task, daemon=True).start()
    
    def _create_single_alert_popup(self, code, name, msg):
        """实际创建单个弹窗（从队列调用）"""
        try:
            # 再次检查是否已有弹窗（可能在队列等待期间已创建）
            existing_win = self.code_to_alert_win.get(code)
            if existing_win:
                try:
                    if existing_win.winfo_exists():
                        # ⭐ [FIX] 更新标题和消息
                        existing_win.title(f"🔔 触发报警 - {name} ({code})")
                        if hasattr(existing_win, 'msg_label'):
                            existing_win.msg_label.config(text=f"⚠️{code} {msg}")
                        
                        # ⭐ [FIX] 重新计算优先级并重启提示
                        is_high = any(kw in msg for kw in HIGH_PRIORITY_KEYWORDS)
                        existing_win.is_high_priority = is_high
                        if hasattr(existing_win, 'start_priority_flashing'):
                            existing_win.start_priority_flashing(msg) # 传入新消息
                        
                        existing_win.lift()
                        existing_win.attributes("-topmost", True)
                        # existing_win.update()
                        # [FIXED] 不在复用时震动，仅在 Voice 回调中震动
                        logger.debug(f"复用已有弹窗并购同步提醒: {code}")
                        return
                except:
                    pass
                if code in self.code_to_alert_win:
                    del self.code_to_alert_win[code]
            
            # ===== 直接创建完整弹窗并预计算位置 (防止闪烁) =====
            win = tk.Toplevel(self)
            self.code_to_alert_win[code] = win # ⭐ [CRITICAL] 提前注册，确保震动联动能搜到
            win.stock_code = code # [NEW] 补全核心属性识别
            win.stock_name = name # [NEW] 补全核心属性识别
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            
            # ⭐ [FIX] 预计算初始诞生位置，确保窗口从出现起就位于正确的排序坑位，解决"不停排序"的视觉抖动
            cur_idx = len([w for w in getattr(self, 'active_alerts', []) if w.winfo_exists()])
            alert_w, alert_h = 400, 180
            m_gap = 10
            sc_w = self.winfo_screenwidth()
            sc_h = self.winfo_screenheight()
            m_cols = max(1, (sc_w - m_gap) // (alert_w + m_gap))
            
            c_col = cur_idx % m_cols
            c_row = cur_idx // m_cols
            init_x = sc_w - (c_col + 1) * (alert_w + m_gap)
            init_y = sc_h - 100 - (c_row + 1) * (alert_h + m_gap) # 100 为任务栏避让高度
            
            win.geometry(f"{alert_w}x{alert_h}+{init_x}+{init_y}")
            # 初始化震动锚点，确保即使由于重试机制立即震动，也不会跑偏
            win._shake_orig_x, win._shake_orig_y = init_x, init_y
            win._shake_orig_wh = f"{alert_w}x{alert_h}"
            # ⭐ [ENHANCEMENT] 卖出类信号使用绿色风格
            sell_keywords = ["卖出", "清仓", "止损", "离场", "减仓", "减持", "风险", "高抛"]
            is_sell_signal = any(kw in msg for kw in sell_keywords)
            win.is_sell_signal = is_sell_signal # 挂载标记

            # ⭐ [ENHANCEMENT] 高优先级报警应用金色/淡红背景，增强视觉差异
            is_high = any(kw in msg for kw in HIGH_PRIORITY_KEYWORDS)
            
            if is_sell_signal:
                bg_color = "#F1F8E9"  # 极浅绿背景
                border_color = "#4CAF50" # 绿色边框
                title_bg = "#4CAF50"  # 绿色标题栏
            else:
                bg_color = "#FFF9E6" if is_high else "#fff" # 金边浅黄背景，更柔和但醒目
                border_color = "#FFD700" if is_high else "#ccc" # 纯金边框
                title_bg = "#e57373" # 默认红/粉色标题栏
            
            win.configure(bg=bg_color)
            win.is_high_priority = is_high
            
            # ===== [MODIFIED] 视觉特效逻辑：变色提示优先级，震动同步语音 =====
            def start_priority_flashing(current_msg=None, w=win):
                """高优先级或关键信号的持久颜色提示（不震动）"""
                if not w.winfo_exists(): return
                
                # 如果没传消息，尝试用最新的
                msg_to_check = current_msg if current_msg is not None else msg
                
                # 使用传入的最新消息进行判断
                is_urgent = getattr(w, 'is_high_priority', False) or any(kw in msg_to_check for kw in ["指令", "信号", "强势", "核心", "放量", "持有", "仓位", "突破", "买入", "护航", "主升浪", "卖出", "清仓", "止损", "离场", "减仓", "减持"])
                if not is_urgent: return
                
                # 如果已经开启了闪烁循环，不要重复开启
                if getattr(w, '_priority_flash_active', False):
                    return
                w._priority_flash_active = True
                
                if getattr(w, 'is_sell_signal', False):
                    flash_color = "#ccff90" # 亮浅绿
                    alt_color = "#81c784"   # 柔和绿
                else:
                    flash_color = "#ffff00" # 亮黄色
                    alt_color = "#ffaa00"   # 亮橘色
                def flash_loop(count=0):
                    if not w.winfo_exists(): 
                        w._priority_flash_active = False
                        return
                    # 如果正在播报（震动中），颜色由播报逻辑控制
                    if getattr(w, 'is_shaking', False):
                        w.after(1000, lambda: flash_loop(count))
                        return
                    
                    bg = flash_color if count % 2 == 0 else alt_color
                    try: 
                        w.configure(bg=bg)
                        # ⭐ 移除变大字体和激进颜色，恢复常规显示
                        if hasattr(w, 'msg_label'):
                            w.msg_label.config(fg="red" if count % 2 == 0 else "black")
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                    w.after(600, lambda: flash_loop(count+1))
                
                flash_loop()
            
            # 将方法挂载到窗口对象上以便复用
            win.start_priority_flashing = start_priority_flashing

            def start_visual_effects(w=win):
                """开始播报语音时触发：开启震动 + 强色闪烁"""
                if not w.winfo_exists(): return
                w.lift()
                # [FIX] 防止重复重叠启动震动
                if getattr(w, '_is_already_shaking', False):
                    return
                w.is_shaking = True
                w._is_already_shaking = True
                w.is_flashing = True
                
                # 播报时的视觉反馈：震动 + 亮红背景
                self._shake_window(w, distance=6, interval_ms=80)
                
                if not hasattr(w, '_original_bg'):
                    w._original_bg = w.cget('bg')
                
                def flash_speech(count=0):
                    if not w.winfo_exists() or not getattr(w, 'is_shaking', False):
                        return
                    # [MODIFIED] 卖出信号使用绿色闪烁，买入/普通信号使用红色闪烁
                    if getattr(win, 'is_sell_signal', False):
                        flash_c = "#a5d6a7" # 绿色提示
                    else:
                        flash_c = "#ff5555" # 红色提示
                        
                    bg = flash_c if count % 2 == 0 else w._original_bg
                    try: w.configure(bg=bg)
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                    w.after(250, lambda: flash_speech(count+1))
                
                flash_speech()
            
            def stop_visual_effects(w=win):
                """语音播报结束：停止震动，恢复背景"""
                if not w.winfo_exists(): return
                w.is_shaking = False
                w._is_already_shaking = False
                w.is_flashing = False
                if hasattr(w, '_original_bg'):
                    try: w.configure(bg=w._original_bg)
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                
                # 自动关闭计时器
                if hasattr(w, 'safety_close_timer'):
                    try: self.after_cancel(w.safety_close_timer)
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                
                if not getattr(w, '_is_enlarged', False):
                    delay = max(30, int(alert_cooldown / 2)) * 1000
                    self._schedule_after(delay, lambda: self._close_alert(w))

            win.start_visual_effects = start_visual_effects
            win.stop_visual_effects = stop_visual_effects
            win.is_shaking = False
            win.is_flashing = False
            
            # 立即启动优先级颜色提示（如果需要）
            # self._schedule_after(50, lambda: (start_priority_flashing(w=win), win.update() if win.winfo_exists() else None))
            self._schedule_after(50, lambda: start_priority_flashing(w=win) if win.winfo_exists() else None)

            # 布局管理
            self.active_alerts.append(win)
            self._update_alert_positions()
            # self.code_to_alert_win[code] = win # 已移至上方
            self._schedule_after(10, self._update_voice_active_codes)
            
            # 🚦 [REMOVE SYNC LOCK] 不再在主线程同步拿锁获取 category，统一交由异步 fetch 处理
            category_content = "获取中..."
            # 开启异步获取，秒出窗口
            self._async_update_alert_details(code, win)
            
            # 自动关闭逻辑判断 (是否有语音)
            has_voice = False
            try:
                if hasattr(self, 'live_strategy') and self.live_strategy:
                    if getattr(self.live_strategy, 'voice_enabled', True):
                        mgr = self._get_alert_manager()
                        if mgr and mgr.voice_enabled:
                            has_voice = True
            except:
                pass
            
            if not has_voice:
                delay = max(60, int(alert_cooldown / 2)) * 1000
                self._schedule_after(delay, lambda: self._close_alert(win), bind_widget=win)
            else:
                win.safety_close_timer = self._schedule_after(180000, lambda: self._close_alert(win), bind_widget=win)

            # UI 面板构造
            win._orig_width, win._orig_height = 400, 180
            win._is_enlarged = False
            
            def toggle_size(event=None):
                """双击切换窗口大小：放大2倍 / 缩小回原大小"""
                if not win.winfo_exists():
                    return
                current_time = time.time()
                if current_time - getattr(win, 'last_toggle_time', 0) < 0.8:  # 800ms 冷却时间
                    return "break"
                win.last_toggle_time = current_time
                
                if win._is_enlarged:
                    new_w, new_h = win._orig_width, win._orig_height
                    win._is_enlarged = False
                    # 缩小后恢复自动关闭计时
                    if not has_voice:
                        self._schedule_after(max(60, int(alert_cooldown / 2)) * 1000, lambda: self._close_alert(win))
                    else:
                        win.safety_close_timer = self._schedule_after(180000, lambda: self._close_alert(win))
                else:
                    new_w, new_h = win._orig_width * 2, win._orig_height * 2
                    win._is_enlarged = True
                    win.is_shaking = False
                    if hasattr(win, 'safety_close_timer'):
                        try: self.after_cancel(win.safety_close_timer)
                        except: pass
                
                try:
                    curr_x, curr_y = win.winfo_x(), win.winfo_y()
                    curr_w, curr_h = win.winfo_width(), win.winfo_height()
                    new_x = max(0, min(curr_x + (curr_w - new_w) // 2, win.winfo_screenwidth() - new_w))
                    new_y = max(0, min(curr_y + (curr_h - new_h) // 2, win.winfo_screenheight() - new_h - 50))
                    win.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
                except Exception as e:
                    logger.debug(f"Toggle size error: {e}")
                    win.geometry(f"{new_w}x{new_h}")
                return "break"
            
            win.toggle_size = toggle_size

            # 标题栏 [COLOR_MODIFIED]
            title_bar = tk.Frame(win, bg=title_bg, height=32, cursor="hand2")
            title_bar.pack(fill="x", side="top")
            title_bar.pack_propagate(False)
            
            def stop_shake(event=None):
                win.is_shaking = False
            
            title_label = tk.Label(title_bar, text=f"🔔 {name} ({code})", bg=title_bg, fg="white", font=("Microsoft YaHei", 10, "bold"), anchor="w", padx=8)
            title_label.pack(side="left", fill="x", expand=True)
            
            title_bar.bind("<Double-Button-1>", toggle_size)
            title_label.bind("<Double-Button-1>", toggle_size)
            title_bar.bind("<Enter>", stop_shake)
            title_label.bind("<Enter>", stop_shake)

            # 整合单击和拖拽开始逻辑
            def on_click_start(event):
                win.x, win.y = event.x, event.y
                return "break"
            
            def do_move(event):
                if hasattr(win, 'x'):
                    x, y = win.winfo_x() + event.x - win.x, win.winfo_y() + event.y - win.y
                    win.geometry(f"+{x}+{y}")
                return "break"
            
            title_bar.bind("<Button-1>", on_click_start)
            title_label.bind("<Button-1>", on_click_start)
            title_bar.bind("<B1-Motion>", do_move)
            title_label.bind("<B1-Motion>", do_move)
            
            # 关闭按钮 [COLOR_MODIFIED]
            close_btn = tk.Label(title_bar, text="✖", bg=title_bg, fg="white", font=("Arial", 12, "bold"), cursor="hand2", padx=8)
            close_btn.pack(side="right")
            close_btn.bind("<Button-1>", lambda e: self._close_alert(win, is_manual=True))
            close_btn.bind("<Enter>", lambda e: close_btn.configure(bg="#c62828" if not is_sell_signal else "#2e7d32"))
            close_btn.bind("<Leave>", lambda e: close_btn.configure(bg=title_bg))

            # 内容框架
            frame = tk.Frame(win, bg="#fff", padx=8, pady=5)
            frame.pack(fill="both", expand=True)
            
            # 按钮区
            def delete_monitor():
                if hasattr(self, 'live_strategy'):
                    try:
                        # --- [MODIFIED] 联动黑名单：删除即视为当日忽略 ---
                        if hasattr(self.live_strategy, 'add_to_blacklist'):
                            self.live_strategy.add_to_blacklist(code, name=name, reason="手动删除弹窗报警")
                        else:
                            self.live_strategy.remove_monitor(code)

                        logger.info(f"Deleted alarm rule for {code} and added to blacklist")
                        mgr = self._get_alert_manager()
                        if mgr: mgr.stop_current_speech(key=code)
                        btn_del.config(text="🗑️已忽略", state="disabled")
                        win._is_deleted = True 
                        win.after(1000, lambda: self._close_alert(win, is_manual=True))
                    except Exception as e:
                        logger.error(f"Remove monitor error: {e}")
            
            def send_to_tdx():
                if hasattr(self, 'sender'):
                    try:
                        self.sender.send(code)
                        btn_send.config(text="✅ 已发送", bg="#ccff90")
                        if getattr(self, 'vis_var', None) and self.vis_var.get():
                            self.open_visualizer(code)
                    except Exception as e:
                        logger.error(f"Send stock error: {e}")
            
            btn_frame = tk.Frame(frame, bg="#fff")
            btn_frame.pack(side="bottom", fill="x", pady=5)
            
            btn_send = tk.Button(btn_frame, text="🚀发送", command=send_to_tdx, bg="#e0f7fa", font=("Arial", 10, "bold"), cursor="hand2")
            btn_send.pack(side="left", fill="x", expand=True, padx=5)
            
            btn_del = tk.Button(btn_frame, text="Del", command=delete_monitor, bg="#ffcdd2", cursor="hand2", font=("Arial", 8), width=3)
            btn_del.pack(side="left", padx=2)
            
            tk.Button(btn_frame, text="关闭", command=lambda: self._close_alert(win, is_manual=True), bg="#eee", width=8, pady=2).pack(side="right", padx=5)
            
            # 消息标签 [COLOR_MODIFIED]
            msg_fg = "#2e7d32" if is_sell_signal else "#d32f2f"
            msg_label = tk.Label(frame, text=f"⚠️ {msg}", font=("Microsoft YaHei", 11, "bold"), fg=msg_fg, bg="#fff", wraplength=380, anchor="w", justify="left")
            msg_label.pack(fill="x", pady=2)
            win.msg_label = msg_label
            
            text_box = tk.Text(frame, height=4, font=("Arial", 10), bg="#f5f5f5", relief="flat")
            text_box.pack(fill="both", expand=True, pady=5)
            text_box.insert("1.0", "⌛ 加载详情中...")
            text_box.config(state="disabled")
            win.text_box = text_box # 挂载供异步更新
            
            # 🚀 启动异步详情加载 (回归方案的关键一步)
            self._async_update_alert_details(code, win)
            
            # [REMOVED] 不在创建时震动，仅在 Voice 回调中震动
            
        except Exception as e:
            logger.error(f"Show alert popup error: {e}")


    def open_trade_report_window(self):
        """打开买卖交易盈利计算查看视图"""
        t_logger = TradingLogger()
        
        report_win = tk.Toplevel(self)
        report_win.title("买卖交易盈亏统计报表")
        window_id = "交易盈亏统计报表"
        self.load_window_position(report_win, window_id, default_width=900, default_height=650)
        report_win.focus_force()

        # --- 排序状态 ---
        self._trade_sort_col = None
        self._trade_sort_reverse = False

        # --- 排序函数 ---
        def sort_treeview_column(tv, col, reverse=False):
            l = [(tv.set(k, col), k) for k in tv.get_children('')]
            try:
                # 尝试数值排序
                l.sort(key=lambda x: float(x[0]) if x[0] not in ("--","") else float('-inf'), reverse=reverse)
            except:
                # 文本排序
                l.sort(reverse=reverse)
            for index, (val, k) in enumerate(l):
                tv.move(k, '', index)
            # 保存当前排序状态
            self._trade_sort_col = col
            self._trade_sort_reverse = reverse

        # --- 加载数据 ---
        def load_stats():
            for item in stats_tree.get_children():
                stats_tree.delete(item)
            rows = t_logger.get_db_summary(days=30)
            for day, profit, count in rows:
                stats_tree.insert("", "end", values=(day, f"{profit:.2f}", count))

        def load_details(start_date=None, end_date=None):
            for item in tree.get_children():
                tree.delete(item)
            trades = t_logger.get_trades(start_date=start_date, end_date=end_date)
            for t in trades:
                status = t.get('status', 'CLOSED')
                sell_p = f"{t['sell_price']:.2f}" if t['sell_price'] is not None else "--"
                profit = f"{t['profit']:.2f}" if t['profit'] is not None else "--"
                pnl = f"{t['pnl_pct']*100:.2f}%" if t['pnl_pct'] is not None else "--"
                sell_d = t['sell_date'] if t['sell_date'] else ("Holding" if status == 'OPEN' else "--")
                
                tree.insert("", "end", values=(
                    t['id'], t['code'], t['name'], t['buy_price'], t.get('buy_amount', 0), sell_p, 
                    profit, pnl, sell_d, t['feedback'] or ""
                ))

        def refresh_summary():
            s_date = start_var.get()
            e_date = end_var.get()
            try:
                datetime.strptime(s_date, '%Y-%m-%d')
                datetime.strptime(e_date, '%Y-%m-%d')
            except:
                messagebox.showerror("错误", "日期格式不正确，请使用 YYYY-MM-DD")
                return

            results = t_logger.get_summary()
            profit = results[0] if results and results[0] is not None else 0
            avg_pct = (results[1] if results and results[1] is not None else 0) * 100
            count = results[2] if results and results[2] is not None else 0
            summary_label.config(text=f"累计净利润: {profit:,.2f} | 平均收益率: {avg_pct:.2f}% | 总平仓笔数: {count}")
            
            load_stats()
            load_details(s_date, e_date)

            # 保持上一次排序
            if self._trade_sort_col:
                sort_treeview_column(tree, self._trade_sort_col, self._trade_sort_reverse)

        # --- 删除记录 ---
        def delete_selected_trade(event=None):
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("提醒", "请先选择要删除的记录")
                return

            item_id = selected[0]
            item = tree.item(item_id)
            trade_id = item['values'][0]
            stock_name = item['values'][2]

            # 删除前获取当前行索引
            children = tree.get_children()
            idx = children.index(item_id)
            # 下一行索引
            next_idx = idx if idx < len(children) - 1 else idx - 1

            if not messagebox.askyesno(
                "确认删除",
                f"确定要永久删除 [{stock_name}] (ID:{trade_id}) 的这笔交易记录吗？"
            ):
                return

            try:
                if t_logger.delete_trade(trade_id):
                    toast_message(self, "成功，记录已从数据库物理删除")
                    
                    # 刷新数据
                    refresh_summary()

                    # 刷新后重新获取行
                    new_children = tree.get_children()
                    if new_children:
                        new_idx = max(0, min(next_idx, len(new_children) - 1))
                        tree.selection_set(new_children[new_idx])
                        tree.focus(new_children[new_idx])
                        tree.see(new_children[new_idx])

                    report_win.lift()
                    report_win.focus_force()
                    tree.focus_set()  # 保证键盘焦点在 Treeview

                else:
                    messagebox.showerror("错误", "删除失败")

            except Exception as e:
                logger.error(f"delete trade error: {e}")
                messagebox.showerror("错误", f"删除异常: {e}")

        # def on_trade_report_double_click(event):
        #         item = tree.selection()
        #         if not item: return
        #         values = tree.item(item[0], "values")
        #         # (code, name, rule_type, value, add_time, tags, id)
        #         tags_info = values[5]
        #         if tags_info:
        #              # 弹窗显示完整信息
        #              top = tk.Toplevel(win)
        #              top.title(f"{values[1]}:{values[0]} 详情")
        #              top.geometry("600x400")
        #              # 居中显示的简单逻辑
        #              wx = win.winfo_rootx() + 50
        #              wy = win.winfo_rooty() + 50
        #              top.geometry(f"+{wx}+{wy}")
                     
        #              from tkinter.scrolledtext import ScrolledText
        #              st = ScrolledText(top, font=("Consolas", 10))
        #              st.pack(fill="both", expand=True)
        #              st.insert("end", tags_info)

        def on_trade_report_tree_select(event):
                selected = tree.selection()
                if not selected: return
                item = selected[0]
                values = tree.item(item, "values")
                target_code = values[1]
                name = values[2]
                stock_code = str(target_code).zfill(6)
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                    self.open_visualizer(stock_code)
        def on_trade_report_on_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return

                values = tree.item(item_id, "values")
                code = values[1]
                name = values[2]

                stock_code = str(code).zfill(6)
                if stock_code:
                    # logger.info(f'on_voice_on_click stock_code:{stock_code} name:{name}')
                    self.sender.send(stock_code)
                    # Auto-launch Visualizer if enabled
                    if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                        self.open_visualizer(stock_code)
        # --- 编辑交易 ---
        def edit_selected_trade():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("提醒", "请先选择要编辑的记录")
                return
            
            item = tree.item(selected[0])
            v = item['values']
            trade_id = v[0]
            stock_name = v[2]
            buy_p = float(v[3])
            buy_a = float(v[4])
            sell_p_raw = v[5]
            sell_p = float(sell_p_raw) if sell_p_raw != "--" else None

            edit_win = tk.Toplevel(report_win)
            edit_win.title(f"编辑交易 - {stock_name}")
            window_id_edit = "编辑交易记录"
            self.load_window_position(edit_win, window_id_edit, default_width=300, default_height=400)
            edit_win.transient(report_win)
            edit_win.grab_set()

            def on_close_edit(event=None):
                self.save_window_position(edit_win, window_id_edit)
                edit_win.destroy()
            
            edit_win.bind("<Escape>", on_close_edit)
            edit_win.protocol("WM_DELETE_WINDOW", on_close_edit)

            frm = tk.Frame(edit_win, padx=20, pady=20)
            frm.pack(fill="both", expand=True)

            tk.Label(frm, text=f"交易 ID: {trade_id}", font=("Arial", 9, "bold")).pack(pady=5)
            tk.Label(frm, text="买入价格:").pack(pady=(10,0))
            bp_var = tk.DoubleVar(value=buy_p)
            tk.Entry(frm, textvariable=bp_var).pack(fill="x")
            tk.Label(frm, text="建议成交量 (股):").pack(pady=(10,0))
            ba_var = tk.IntVar(value=buy_a)
            tk.Entry(frm, textvariable=ba_var).pack(fill="x")
            
            sp_var = None
            if sell_p is not None:
                tk.Label(frm, text="卖出价格:").pack(pady=(10,0))
                sp_var = tk.DoubleVar(value=sell_p)
                tk.Entry(frm, textvariable=sp_var).pack(fill="x")
            
            def save_edit():
                try:
                    new_bp = bp_var.get()
                    new_ba = ba_var.get()
                    new_sp = sp_var.get() if sp_var else None
                    if t_logger.manual_update_trade(trade_id, new_bp, new_ba, new_sp):
                        messagebox.showinfo("成功", "修改已保存，系统已自动重算净利润与收益率。")
                        on_close_edit()
                        refresh_summary()
                    else:
                        messagebox.showerror("错误", "数据库更新失败")
                except Exception as e:
                    messagebox.showerror("错误", f"输入无效: {e}")

            tk.Button(frm, text="💾 保存修改", command=save_edit, bg="#ccff90", font=("Arial", 10, "bold"), height=2).pack(pady=30, fill="x")

        # --- 添加反馈 ---
        def add_feedback():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("提醒", "请在明细中选择一笔交易进行反馈")
                return
            
            item = tree.item(selected[0])
            trade_id = item['values'][0]
            stock_name = item['values'][2]
            
            feedback = simpledialog.askstring("策略优化反馈", f"针对 [{stock_name}] 的交易，请告知策略存在的问题或改进建议：")
            if feedback:
                if t_logger.update_trade_feedback(trade_id, feedback):
                    messagebox.showinfo("成功", "感谢反馈，已记录。")
                    refresh_summary()
                else:
                    messagebox.showerror("错误", "反馈保存失败")

        # --- UI 布局 ---
        # 顶部统计
        header_frame = tk.Frame(report_win, relief="groove", borderwidth=1, padx=10, pady=10)
        header_frame.pack(side="top", fill="x")
        
        summary_label = tk.Label(header_frame, text="正在加载统计数据...", font=("Arial", 12, "bold"))
        summary_label.pack(side="left")

        filter_frame = tk.Frame(header_frame)
        filter_frame.pack(side="right")
        tk.Label(filter_frame, text="日期筛选:").pack(side="left", padx=5)
        start_var = tk.StringVar(value=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        tk.Entry(filter_frame, textvariable=start_var, width=12).pack(side="left", padx=2)
        tk.Label(filter_frame, text="至").pack(side="left")
        tk.Entry(filter_frame, textvariable=end_var, width=12).pack(side="left", padx=2)

        # 多日汇总
        stats_frame = tk.LabelFrame(report_win, text="多日盈亏统计 (近30天)", padx=5, pady=5)
        stats_frame.pack(side="top", fill="x", padx=10, pady=5)
        stats_tree = ttk.Treeview(stats_frame, columns=("day", "profit", "count"), show="headings", height=5)
        stats_tree.heading("day", text="日期")
        stats_tree.heading("profit", text="单日利润")
        stats_tree.heading("count", text="成交笔数")
        stats_tree.column("day", width=150, anchor="center")
        stats_tree.column("profit", width=150, anchor="center")
        stats_tree.column("count", width=100, anchor="center")
        stats_tree.pack(fill="x")

        # 底部按钮
        btn_bar = tk.Frame(report_win, pady=10)
        btn_bar.pack(side="bottom", fill="x")
        tk.Button(btn_bar, text="刷新数据", command=refresh_summary, width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="✏️ 手动修正", command=edit_selected_trade, width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="🗑️ 删除记录", command=delete_selected_trade, fg="red", width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="问题反馈/优化策略", command=add_feedback, bg="#ffcccc", width=20).pack(side="right", padx=20)

        # 中部明细列表
        list_frame = tk.LabelFrame(report_win, text="交易明细记录", padx=5, pady=5)
        list_frame.pack(side="top", fill="both", expand=True, padx=10, pady=5)

        cols = ("id", "code", "name", "buy_price", "amount", "sell_price", "profit", "pnl_pct", "sell_date", "feedback")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.capitalize(), command=lambda _c=c: sort_treeview_column(tree, _c, reverse=not getattr(self, "_trade_sort_reverse", False)))
            tree.column(c, width=80, anchor="center")
        tree.column("id", width=40, anchor="center")
        tree.column("name", width=100)
        tree.column("feedback", width=200, anchor="w")
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Delete 键绑定
        tree.bind("<Delete>", delete_selected_trade)
        tree.bind("<Button-1>", on_trade_report_on_click)
        tree.bind("<<TreeviewSelect>>", on_trade_report_tree_select) 
        # 关闭事件
        def on_close(event=None):
            self.save_window_position(report_win, window_id)
            report_win.destroy()
        report_win.bind("<Escape>", on_close)
        report_win.protocol("WM_DELETE_WINDOW", on_close)

        # 初始加载
        refresh_summary()

    def open_trading_analyzer_qt6(self):
        """[COMPAT] 打开 Qt6 版本的交易分析工具 (兼容 PyInstaller 打包)"""
        from PyQt6 import QtWidgets
        from trading_analyzerQt6 import TradingGUI
        import sys
        import threading

        try:
            # 防止重复创建
            if getattr(self, "_trading_gui_qt6", None) is not None:
                self._trading_gui_qt6.show()
                self._trading_gui_qt6.raise_()
                self._trading_gui_qt6.activateWindow()
                return

            # --- 初始化 QApplication（全局唯一） ---
            app = QtWidgets.QApplication.instance()
            if app is None:
                self._qt_app = QtWidgets.QApplication([])  # ❗避免 sys.argv 干扰 Tk

            # --- 创建 Qt 窗口（在 Tk 线程中） ---
            # on_tree_scroll_to_code=self.tree_scroll_to_code,

            self._trading_gui_qt6 = TradingGUI(
                on_code_callback=self.on_code_click,
                main_app=self,
                selector=getattr(self, 'selector', None),
                live_strategy=getattr(self, 'live_strategy', None),
                df_all=getattr(self, 'df_all', None)
            )

            self._trading_gui_qt6.show()
            self._trading_gui_qt6.raise_()
            self._trading_gui_qt6.activateWindow()

            # --- 提示 ---
            toast_message(self, "交易分析工具(Qt6) 已就绪")

        except Exception as e:
            logger.error(f"Failed to open TradingGUI Qt6: {e}")
            messagebox.showerror("错误", f"启动 Qt6 分析工具失败: {e}")

    def open_kline_viewer_qt(self):
        """打开 Qt 版本的 K 线缓存查看器"""
        from PyQt6 import QtWidgets
        from minute_kline_viewer_qt import KlineBackupViewer
        try:
            # 🛡️ 使用 Qt 安全操作上下文管理器，避免 pyttsx3 COM 与 Qt GIL 冲突
            if not hasattr(self, "_kline_viewer_qt") or self._kline_viewer_qt is None:
                # 确保 Qt 环境已初始化
                if not QtWidgets.QApplication.instance():
                    self._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])
                
                # 获取 last6vol 用于归一化
                last6vol_map = {}
                if hasattr(self, 'df_all') and not self.df_all.empty and 'last6vol' in self.df_all.columns:
                    last6vol_map = self.df_all['last6vol'].to_dict()

                # 连接双击代码到 TDX 联动，并传入实时服务代理
                self._kline_viewer_qt = KlineBackupViewer(
                    on_code_callback=self.on_code_click,
                    service_proxy=self.realtime_service,
                    last6vol_map=last6vol_map,
                    main_app=self
                )
            
            self._kline_viewer_qt.show()
            self._kline_viewer_qt.raise_()
            self._kline_viewer_qt.activateWindow()
            
            toast_message(self, "K线查看器 (Qt) 已启动")
        except Exception as e:
            logger.error(f"Failed to open KlineBackupViewer: {e}")
            messagebox.showerror("错误", f"启动 GUI 查看器失败: {e}")

    def open_strategy_backtest_view(self):
        """预留：打开策略复盘与AI优化建议视图"""
        messagebox.showinfo("敬请期待", "复盘功能正在开发中，将结合您的反馈进行模型微调。")

    def open_strategy_manager(self, verify_code=None):
        """打开策略白盒管理器"""
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("提示", "实时监控模块尚未启动，请稍后再试")
            return

        # 窗口复用
        if hasattr(self, '_strategy_manager_win') and self._strategy_manager_win and self._strategy_manager_win.winfo_exists():
            self._strategy_manager_win.deiconify()
            self._strategy_manager_win.lift()
            self._strategy_manager_win.focus_force()
            if verify_code:
                self._strategy_manager_win.notebook.select(self._strategy_manager_win.tab_verify)
                self._strategy_manager_win.set_verify_code(verify_code)
            return

        try:
            # 传入 realtime_service (如果有)
            rt_service = getattr(self, 'realtime_service', None)
            win = StrategyManager(self, self.live_strategy, realtime_service=rt_service, query_manager=self.query_manager)
            self._strategy_manager_win = win
            
            if verify_code:
                win.notebook.select(win.tab_verify)
                win.set_verify_code(verify_code)
                
        except Exception as e:
            logger.error(f"Failed to open StrategyManager: {e}")
            messagebox.showerror("错误", f"启动策略管理器失败: {e}")

    def add_voice_monitor_dialog_quick(self, code, name):
        """
        弹出对话框添加语音监控 (由外部调用，如 MarketPulseViewer)
        校验唯一性：如果已存在则提示合并或拒绝
        """
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("提示", "实时监控模块尚未启动")
            return

        # 1. 唯一性检查
        monitors = self.live_strategy.get_monitors()
        # 兼容 key 为 code 或 code_resample 的情况
        existing_key = None
        if code in monitors:
            existing_key = code
        else:
            # 检查是否有带后缀的 key
            for k in monitors.keys():
                if k.split('_')[0] == code:
                    existing_key = k
                    break
        
        if existing_key:
            if not messagebox.askyesno("重复提示", f"{name}({code}) 已在监控列表中！\n\n是否继续添加新规则？\n(选'否'则取消)"):
                return
            # 选'是'则继续弹出添加规则框，视为追加规则

        # 2. 弹出简易规则输入框
        dlg = tk.Toplevel(self)
        dlg.title(f"添加监控: {name}")
        dlg.geometry("300x220")
        self.load_window_position(dlg, "AddVoiceMonitorDlg", default_width=300, default_height=220)
        
        tk.Label(dlg, text=f"代码: {code}   名称: {name}", font=("Arial", 10, "bold")).pack(pady=10)
        
        tk.Label(dlg, text="预警规则:").pack(anchor="w", padx=20)
        
        # 规则类型
        type_var = tk.StringVar(value="price_up")
        # price_up, price_down, change_up
        f_type = tk.Frame(dlg)
        f_type.pack(fill="x", padx=20, pady=5)
        ttk.Combobox(f_type, textvariable=type_var, values=["price_up", "price_down", "change_up"], state="readonly", width=15).pack(side="left")
        
        # 阈值
        tk.Label(dlg, text="阈值 (价格/涨幅%):").pack(anchor="w", padx=20)
        e_val = tk.Entry(dlg)
        e_val.pack(fill="x", padx=20, pady=5)
        
        # 默认填入当前价 * 1.01 (方便演示)
        curr_price = 0
        if hasattr(self, 'df_all') and code in self.df_all.index:
             curr_price = float(self.df_all.loc[code].get('trade', 0))
        if curr_price > 0:
            e_val.insert(0, f"{curr_price * 1.01:.2f}")

        def on_confirm():
            val_str = e_val.get().strip()
            if not val_str:
                return
            try:
                val = float(val_str)
                # 调用 Strategy 添加
                res = self.live_strategy.add_monitor(code, name, type_var.get(), val, tags="manual", create_price=curr_price)
                toast_message(self, f"已添加监控: {name}")
                dlg.destroy()
                
                # 如果管理窗口开着，刷新它
                if hasattr(self, '_voice_monitor_win') and self._voice_monitor_win and self._voice_monitor_win.winfo_exists():
                    if hasattr(self._voice_monitor_win, 'refresh_list'):
                        self._voice_monitor_win.refresh_list()
                        
            except ValueError:
                messagebox.showerror("错误", "阈值必须是数字")

        tk.Button(dlg, text="确定添加", command=on_confirm, bg="#ccffcc").pack(pady=15)

    def open_voice_monitor_manager(self):
        """语音预警管理窗口 (支持窗口复用)"""

        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("提示", "实时监控模块尚未启动，请稍后再试")
            return

        # ✅ 窗口复用逻辑
        if self._voice_monitor_win and self._voice_monitor_win.winfo_exists():
            self._voice_monitor_win.deiconify()
            self._voice_monitor_win.lift()
            self._voice_monitor_win.focus_force()
            return

        try:
            win = tk.Toplevel(self)
            self._voice_monitor_win = win
            win.title("语音预警管理")
            window_id = "语音预警管理"
            self.load_window_position(win, window_id, default_width=800, default_height=500)
            # --- 顶部操作区域 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text="🔔 实时语音监控列表", font=("Arial", 12, "bold")).pack(side="left")
            
            total_label = tk.Label(
                top_frame,
                text="总条目: 0",
                anchor="w",
                padx=10,
                font=("微软雅黑", 9)
            )
            total_label.pack(side="left")

            # --- [NEW] Cycle Toggle ---
            if not hasattr(self, 'force_d_cycle_var'):
                # Should have been initialized in init_checkbuttons, but safety fallback
                self.force_d_cycle_var = tk.BooleanVar(value=True) 

            tk.Checkbutton(
                top_frame,
                text="强制(d)周期",
                variable=self.force_d_cycle_var,
                indicatoron=0,           # Toggle button style
                width=12,                # Wider click target
                selectcolor="#b2dfdb",   # Light green when checked
                command=lambda: logger.info(f"Cycle Toggle Changed: {self.force_d_cycle_var.get()}")
            ).pack(side="left", padx=10)
            
            tk.Button(top_frame, text="开启自动交易", command=lambda: self.live_strategy.start_auto_trading_loop(force=True, concept_top5=getattr(self, 'concept_top5', None)), bg="#fff9c4").pack(side="right", padx=5)
            tk.Button(top_frame, text="清理恢复持仓", command=lambda: batch_clear_recovered(), bg="#ffcdd2").pack(side="right", padx=5)
            def on_repair_sync():
                if messagebox.askyesno("数据修复", "将进行以下操作：\n1. 根据创建时间从历史行情回补缺失的‘加入价’\n2. 确保所有预警规则已同步到数据库\n\n是否立即开始?"):
                    res = self.live_strategy.sync_and_repair_monitors()
                    if "error" in res:
                        messagebox.showerror("错误", f"修复过程中出现错误: {res['error']}")
                    else:
                        msg = f"✅ 数据对齐完成!\n\n- 价格回补: {res['repair_count']} 只\n- 数据库同步: {res['sync_count']} 条\n- 总条目: {res['total']}"
                        if res['errors']:
                            msg += f"\n\n注意: 有 {len(res['errors'])} 项同步异常，请检查日志。"
                        messagebox.showinfo("成功", msg)
                        load_data()

            tk.Button(top_frame, text="数据同步修复", command=on_repair_sync, bg="#c8e6c9").pack(side="right", padx=5)
            tk.Button(top_frame, text="测试报警音", command=lambda: self.live_strategy.test_alert(), bg="#e0f7fa").pack(side="right", padx=5)
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 列表区域 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 显示 ID 是为了方便管理 (code + rule_index)
            columns = ("code", "name", "resample", "rule_type", "value", "create_price", "curr_price", "pnl", "rank", "add_time", "tags", "id")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            # 刷新统计函数
            def refresh_stats():
                total = len(tree.get_children())
                # selected = len(tree.selection())
                total_label.config(text=f"总条目: {total}")
                # selected_label.config(text=f"已选中: {selected}")

            

            def treeview_sort_column(tv, col, reverse):
                # 记录当前排序状态
                tv.current_sort_col = col
                tv.current_sort_reverse = reverse
                
                l = [(tv.set(k, col), k) for k in tv.get_children('')]
                
                # 智能数值排序:尝试转换为数值,失败则按字符串排序
                def sort_key(item):
                    val = item[0]
                    if val in ('', '-', '--', 'N/A', None):
                        return (1, 0)  # 空值排在最后
                    try:
                        # 尝试转换为数值 (处理百分比和符号)
                        clean_val = str(val).replace('%', '').replace('+', '')
                        return (0, float(clean_val))
                    except (ValueError, TypeError):
                        # 无法转换,按字符串排序
                        return (0, str(val).lower())
                
                l.sort(key=sort_key, reverse=reverse)

                for index, (val, k) in enumerate(l):
                    tv.move(k, '', index)

                tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))


            tree.heading("code", text="代码", command=lambda: treeview_sort_column(tree, "code", False))
            tree.heading("name", text="名称", command=lambda: treeview_sort_column(tree, "name", False))
            tree.heading("resample", text="周期", command=lambda: treeview_sort_column(tree, "resample", False))
            tree.heading("rule_type", text="规则类型", command=lambda: treeview_sort_column(tree, "rule_type", False))
            tree.heading("value", text="阈值", command=lambda: treeview_sort_column(tree, "value", False))
            tree.heading("create_price", text="加入价", command=lambda: treeview_sort_column(tree, "create_price", False))
            tree.heading("curr_price", text="现价", command=lambda: treeview_sort_column(tree, "curr_price", False))
            tree.heading("pnl", text="盈亏%", command=lambda: treeview_sort_column(tree, "pnl", False))
            tree.heading("rank", text="Rank", command=lambda: treeview_sort_column(tree, "rank", False))
            tree.heading("add_time", text="时间", command=lambda: treeview_sort_column(tree, "add_time", False))
            tree.heading("tags", text="简介", command=lambda: treeview_sort_column(tree, "tags", False))
            tree.heading("id", text="ID (Code_Idx)")
            
            tree.column("code", width=50, anchor="center")
            tree.column("name", width=80, anchor="center")
            tree.column("resample", width=50, anchor="center")
            tree.column("rule_type", width=80, anchor="center")
            tree.column("value", width=60, anchor="center")
            tree.column("create_price", width=60, anchor="center")
            tree.column("curr_price", width=60, anchor="center")
            tree.column("pnl", width=60, anchor="center")
            tree.column("rank", width=50, anchor="center")
            tree.column("add_time", width=100, anchor="center")
            tree.column("tags", width=120, anchor="center")
            tree.column("id", width=0, stretch=False) # 隐藏 ID 列

            def show_tags_detail(values):
                code, name = values[0], values[1]
                tags_info = values[len(values) -2]

                top = tk.Toplevel(win)
                top.title(f"{name}:{code} 详情")
                top.geometry("600x400")
                top.lift()
                top.focus_force()
                top.attributes("-topmost", True)
                top.after(100, lambda: top.attributes("-topmost", False))
                # 简单居中
                wx = win.winfo_rootx() + 50
                wy = win.winfo_rooty() + 50
                top.geometry(f"+{wx}+{wy}")

                from tkinter.scrolledtext import ScrolledText
                st = ScrolledText(top, font=("Consolas", 10))
                st.pack(fill="both", expand=True)
                st.insert("end", tags_info)
                def close_top(event=None):
                    top.destroy()

                top.bind("<Escape>", close_top)
                top.protocol("WM_DELETE_WINDOW", close_top)

            def on_voice_tree_double_click(event):
                region = tree.identify_region(event.x, event.y)
                if region != "cell":
                    return

                column = tree.identify_column(event.x)  # '#1', '#2', ...
                col_idx = int(column[1:]) - 1           # 转为 0-based

                item = tree.identify_row(event.y)
                if not item:
                    return

                values = tree.item(item, "values")

                TAGS_COL_INDEX = 10  # tags 在 values 中的索引

                if col_idx == TAGS_COL_INDEX:
                    tags_info = values[TAGS_COL_INDEX]
                    if tags_info:
                        show_tags_detail(values)
                else:
                    edit_selected(item, values)

                def on_motion(event):
                    region = tree.identify_region(event.x, event.y)
                    if region == "cell":
                        col = int(tree.identify_column(event.x)[1:]) - 1
                        if col == TAGS_COL_INDEX:
                            tree.configure(cursor="hand2")
                            return
                    tree.configure(cursor="")
                tree.bind("<Motion>", on_motion)


            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            def load_data():
                """加载数据到列表"""
                for item in tree.get_children():
                    tree.delete(item)
                    
                monitors = self.live_strategy.get_monitors()
                for key, data in monitors.items():
                    # Extract pure code from composite key (e.g., "002131_d" -> "002131")
                    pure_code = data.get('code') or key.split('_')[0]
                    name = data['name']
                    rules = data['rules']
                    resample = data.get('resample', 'd')
                    add_time = data.get('created_time', '')
                    tags = data.get('tags', '')
                    create_price = data.get('create_price', 0.0)
                    
                    curr_price = 0.0
                    rank = 0
                    pnl_str = "--"
                    if hasattr(self, 'df_all') and not self.df_all.empty and pure_code in self.df_all.index:
                         row_data = self.df_all.loc[pure_code]
                         rank = row_data.get('Rank', 0)
                         curr_price = float(row_data.get('trade', 0))
                         if create_price > 0 and curr_price > 0:
                             pnl = (curr_price - create_price) / create_price * 100
                             pnl_str = f"{pnl:+.2f}%"

                    if not rules:
                        # 对于没有规则的股票，显示一行占位，方便管理
                        uid = f"{key}_none"
                        tree.insert("", "end", values=(pure_code, name, resample, "⚠️(未设规则)", "-", f"{create_price:.2f}", f"{curr_price:.2f}", pnl_str, rank, add_time, tags, uid))
                    else:
                        for idx, rule in enumerate(rules):
                            rtype_map = {
                                "price_up": "价格突破 >=",
                                "price_down": "价格跌破 <=",
                                "change_up": "涨幅超过 >="
                            }
                            display_type = rtype_map.get(rule['type'], rule['type'])
                            # unique id uses composite key for proper reference
                            uid = f"{key}_{idx}"
                            # ✅ 格式化数值展示，价格/阈值保留2位小数
                            try:
                                val_formatted = f"{float(rule['value']):.2f}"
                            except:
                                val_formatted = rule['value']
                            tree.insert("", "end", values=(pure_code, name, resample, display_type, val_formatted, f"{create_price:.2f}", f"{curr_price:.2f}", pnl_str, rank, add_time, tags, uid))
                
                # 💥 关键：数据加载后更新统计标签
                refresh_stats()
                
                # ✅ 恢复排序状态
                if hasattr(tree, 'current_sort_col'):
                    treeview_sort_column(tree, tree.current_sort_col, tree.current_sort_reverse)

            load_data()
            win.refresh_list = load_data
            self._voice_monitor_win = win

            # --- 动态添加 "策略选股" 按钮 (New) ---
            tk.Button(top_frame, text="策略选股...", command=self.open_stock_selection_window, bg="#fff9c4", font=("Arial", 9, "bold")).pack(side="right", padx=5)

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

            def batch_clear_recovered():
                """一键清理所有 recovered_holding 标记的监控并平仓记录"""
                monitors = self.live_strategy.get_monitors()
                to_remove = [code for code, data in monitors.items() if data.get('tags') == "recovered_holding"]
                
                if not to_remove:
                    messagebox.showinfo("提示", "未发现带有 'recovered_holding' 标签的监控项", parent=win)
                    return
                
                if not messagebox.askyesno("确认操作", f"确定要清理这 {len(to_remove)} 只恢复持仓股吗？\n这将自动在交易日志中记录已卖出并移除监控。", parent=win):
                    return
                
                count = 0
                for code in to_remove:
                    data = monitors.get(code)
                    name = data.get('name', '')
                    # 尝试获取当前价
                    price = 0.0
                    if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                        price = float(self.df_all.loc[code].get('trade', 0))
                    
                    # 执行平仓记录
                    self.live_strategy.close_position_if_any(code, price, name)
                    # 移除监控
                    self.live_strategy.remove_monitor(code)
                    count += 1
                
                messagebox.showinfo("成功", f"已成功清理并记录 {count} 只持仓股", parent=win)
                load_data()

            def delete_selected(event=None):
                selected = tree.selection()
                if not selected:
                    return

                # 取第一个选中项（支持连续快速删除）
                item = selected[0]
                values = tree.item(item, "values")
                # Column order: code(0), name(1), resample(2), rule_type(3), value(4), rank(5), add_time(6), tags(7), id(8)
                code = values[0]  # Pure code (e.g., "002131")
                resample = values[2]  # Period (e.g., "d", "w")
                uid = values[8]  # id column
                
                # Construct composite key from code + resample
                composite_key = f"{code}_{resample}"
                
                # Extract rule index from uid (format: "{composite_key}_{idx}" or "{composite_key}_none")
                suffix = uid.rsplit('_', 1)[-1] if '_' in uid else "none"

                # 调整删除逻辑
                if self.live_strategy:
                    # ✅ [新增] 删除前检查持仓并提示
                    is_holding = False
                    if hasattr(self, 'live_strategy') and hasattr(self.live_strategy, 'trading_logger'):
                        try:
                            trades = self.live_strategy.trading_logger.get_trades()
                            is_holding = any(t['code'].zfill(6) == code.zfill(6) and t['status'] == 'OPEN' for t in trades)
                        except Exception as e:
                            logger.error(f"Error in task: {e}")
                    
                    if is_holding:
                        # 💥 [优化] 提示语更明确：移除监控 = 停止跟踪 = 需要处理持仓
                        ans = messagebox.askyesnocancel(
                            "持仓确认", 
                            f"检测到 {values[1]}({code}) 尚有在册持仓！\n\n移除监控将导致该持仓不再被实时跟踪，且为了防止自动恢复，系统将必须强制关闭该持仓记录。\n\n是否同时并在交易日志中标记为[卖出平仓]？\n\n'是' - 标记平仓并移除监控\n'否' - 仅标记移除(不再跟踪)但保留日志闭环\n'取消' - 放弃操作", 
                            parent=win
                        )
                        if ans is None: return # 取消
                        if ans is True: # 是 - 正常平仓逻辑(用当前价)
                            price = 0.0
                            if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                                price = float(self.df_all.loc[code].get('trade', 0))
                            self.live_strategy.close_position_if_any(code, price, values[1])

                    if suffix == "none":
                        self.live_strategy.remove_monitor(composite_key)
                    else:
                        try:
                            idx = int(suffix)
                            self.live_strategy.remove_rule(composite_key, idx)
                        except Exception:
                            pass

                    # 💥 联动核心：彻底清理该品种的所有浮动报警窗口与余波语音
                    try:
                        # 1. 查找并关闭 UI 报警窗
                        if hasattr(self, 'code_to_alert_win') and code in self.code_to_alert_win:
                            awin = self.code_to_alert_win[code]
                            if awin.winfo_exists():
                                self._close_alert(awin, is_manual=True)
                        elif hasattr(self, 'active_alerts'):
                            # 托底查找
                            for awin in list(self.active_alerts):
                                if getattr(awin, 'stock_code', None) == code:
                                    self._close_alert(awin, is_manual=True)
                        
                        # 2. 强制同步一次活跃代码列表 (确保 cancel 队列和Existence检查立即生效)
                        if hasattr(self, '_update_voice_active_codes'):
                            self._update_voice_active_codes()
                    except Exception as linkage_e:
                        logger.debug(f"Linkage cleanup failed for {code}: {linkage_e}")

                # --- 记录删除行的索引 ---
                children = list(tree.get_children())
                try:
                    del_idx = children.index(item)
                except ValueError:
                    del_idx = 0

                # 为了防止索引错乱，删除后必须全量刷新
                load_data()
                
                # --- 设置删除标志位，防止触发 on_voice_tree_select ---
                self._is_deleting = True
                try:
                     # tree.delete(item) # 已经由 load_data() 刷新
                     
                     # 选中下一行 (尝试在刷新后的 tree 中找原位置)
                     children = tree.get_children()
                     if children:
                         if del_idx >= len(children):
                             del_idx = len(children) - 1
                         next_item = children[del_idx]
                         tree.selection_set(next_item)
                         tree.focus(next_item)
                         tree.see(next_item)
                finally:
                     # 必须确保 UI 事件循环处理完毕后再重置标志位
                     # 使用 after_idle 确保本次事件栈清空
                     tree.after_idle(lambda: setattr(self, '_is_deleting', False))


            def on_voice_tree_select(event):
                # 检查删除标志位
                if getattr(self, '_is_deleting', False):
                    return

                selected = tree.selection()
                if not selected: return
                item = selected[0]
                values = tree.item(item, "values")
                target_code = values[0]
                name = values[1]
                stock_code = str(target_code).zfill(6)
                add_time = str(values[9])[:10] if len(values) > 9 else None
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                    self.open_visualizer(stock_code, timestamp=add_time)

            def on_voice_right_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return
                
                # 设置选中项，以便 visually 确认右键点的是哪行
                tree.selection_set(item_id)
                values = tree.item(item_id, "values")
                
                # Column order: code(0), name(1), ..., add_time(9), ...
                stock_code = str(values[0]).zfill(6)
                stock_name = values[1]
                add_time = str(values[9])[:10] if len(values) > 9 else None
                
                menu = tk.Menu(win, tearoff=0)
                
                # 1. 核心联动 (携带时间)
                menu.add_command(label=f"🔭 可视化联动 [{stock_code}]", 
                                command=lambda: self.open_visualizer(stock_code, timestamp=add_time),
                                font=("Arial", 9, "bold"))
                
                # 2. DNA 审计
                def do_dna_audit():
                    codes_dict = {stock_code: stock_name}
                    # 获取该行之后的所有代码，模拟常用的“顺延审计”逻辑
                    all_ids = tree.get_children()
                    try:
                        start_idx = all_ids.index(item_id)
                        for next_item in all_ids[start_idx+1 : start_idx+11]: # 顺延 10 只
                            v = tree.item(next_item, "values")
                            if v and len(v) > 1:
                                codes_dict[str(v[0]).zfill(6)] = v[1]
                    except: pass
                    
                    if hasattr(self, '_run_dna_audit_batch'):
                        self._run_dna_audit_batch(codes_dict)
                    else:
                        messagebox.showinfo("提示", "DNA 审计功能在当前模式下不可用")

                menu.add_command(label="🧬 DNA 专项审计...", command=do_dna_audit, foreground="purple")
                
                menu.add_separator()
                
                # 3. 基础操作
                menu.add_command(label="✏️ 修改阈值 (Edit)", command=lambda: edit_selected(item_id, values))
                menu.add_command(label="🗑️ 删除规则 (Del)", command=lambda: delete_selected(), foreground="red")
                
                menu.add_separator()
                
                # 4. 其他
                menu.add_command(label="🎯 滚动到主表", command=lambda: self.tree_scroll_to_code(stock_code))
                menu.add_command(label="🚀 发送到关联软件", command=lambda: self.original_push_logic(stock_code))
                menu.add_command(label="📋 复制代码", command=lambda: [self.clipboard_clear(), self.clipboard_append(stock_code)])

                menu.post(event.x_root, event.y_root)
                
            def on_voice_on_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return

                values = tree.item(item_id, "values")
                code = values[0]
                name = values[1]

                stock_code = str(code).zfill(6)
                add_time = values[9] if len(values) > 9 else None
                if stock_code:
                    # logger.info(f'on_voice_on_click stock_code:{stock_code} name:{name}')
                    self.sender.send(stock_code)
                    # Auto-launch Visualizer if enabled
                    if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                        self.open_visualizer(stock_code, timestamp=add_time)

            def edit_selected(item=None, values=None):
                 if values is None:
                    selected = tree.selection()
                    if not selected:
                        return
                    item = selected[0]
                    values = tree.item(item, "values")
                 # Column order: code(0), name(1), resample(2), rule_type(3), value(4), create_price(5), curr_price(6), pnl(7), rank(8), add_time(9), tags(10), id(11)
                 code = values[0]  # Pure code
                 name = values[1]
                 resample = values[2]  # Period
                 old_val = values[4]  # value is at index 4
                 uid = values[11]  # id is at index 11
                 
                 # Construct composite key from code + resample
                 composite_key = f"{code}_{resample}"
                 
                 # Extract rule index from uid suffix
                 suffix = uid.rsplit('_', 1)[-1] if '_' in uid else "none"
                 
                 if suffix == "none":
                     idx = -1
                 else:
                     try:
                         idx = int(suffix)
                     except:
                         idx = -1
                 
                 current_type = "price_up"
                 monitors = self.live_strategy.get_monitors()
                 if composite_key in monitors:
                     rules = monitors[composite_key]['rules']
                     if idx >= 0 and idx < len(rules):
                         current_type = rules[idx]['type']

                 edit_win = tk.Toplevel(win)
                 edit_win.title(f"编辑规则 - {name}")
                 edit_win_id = "编辑规则"
                 self.load_window_position(edit_win, edit_win_id, default_width=900, default_height=600)
                 edit_win.minsize(800, 500)

                 main_frame = tk.Frame(edit_win)
                 main_frame.pack(fill="both", expand=True, padx=10, pady=10)

                 main_frame.grid_rowconfigure(0, weight=1)
                 main_frame.grid_columnconfigure(0, weight=3)
                 main_frame.grid_columnconfigure(1, weight=2)

                 left_frame = tk.Frame(main_frame)
                 left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

                 right_frame = tk.LabelFrame(
                     main_frame,
                     text="参考数据 (点击自动填入)",
                     width=350
                 )
                 right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
                 right_frame.grid_propagate(False)


                 # --- 左侧 ---
                 curr_price = 0.0
                 curr_change = 0.0
                 row_data = None
                 if code in self.df_all.index:
                    row_data = self.df_all.loc[code]
                    try:
                        curr_price = float(row_data.get('trade', 0))
                        curr_change = float(row_data.get('changepercent', 0))
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                 
                 tk.Label(left_frame, text=f"当前价格: {curr_price:.2f}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
                 # tk.Label(left_frame, text=f"当前涨幅: {curr_change:.2f}%", font=("Arial", 10)).pack(pady=5, anchor="w")

                 tk.Label(left_frame, text="规则类型:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
                 
                 new_type_var = tk.StringVar(value=current_type)
                 # ✅ 格式化显示旧阈值
                 try:
                     old_val_fmt = f"{float(old_val):.2f}"
                 except:
                     old_val_fmt = str(old_val)
                 val_var = tk.StringVar(value=old_val_fmt)

                 def on_type_change():
                    # 切换默认值
                    t = new_type_var.get()
                    if t == "change_up":
                         val_var.set(f"{curr_change:.2f}")
                    else:
                         val_var.set(f"{curr_price:.2f}")

                 types = [("价格突破 (Price >=)", "price_up"), 
                          ("价格跌破 (Price <=)", "price_down"),
                          ("涨幅超过 (Change% >=)", "change_up")]
                 
                 for text, val in types:
                     tk.Radiobutton(left_frame, text=text, variable=new_type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)

                 tk.Label(left_frame, text="触发阈值:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
                 
                 # 阈值输入区域 (包含 +/- 按钮)
                 val_frame = tk.Frame(left_frame)
                 val_frame.pack(fill="x", padx=5, pady=5)

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
                 # ESC / 关闭
                 def on_close(event=None):
                     # update_window_position(window_id)
                     self.save_window_position(edit_win, edit_win_id)
                     edit_win.destroy()
                 
                 # 🔑 关键：挂到 Toplevel 对象上
                 edit_win.on_close = on_close
                 def confirm_edit(event=None):
                     try:
                         val = float(e_new.get())
                         new_type = new_type_var.get()
                         
                         if self.live_strategy:
                             if idx >= 0:
                                 self.live_strategy.update_rule(code, idx, new_type, val)
                             else:
                                 # 新增规则 (原来的占位行)
                                 self.live_strategy.add_monitor(code, name, new_type, val, create_price=curr_price)
                         
                         load_data()
                         edit_win.on_close()
                     except ValueError:
                         messagebox.showerror("错误", "无效数字", parent=edit_win)

                 edit_win.bind("<Escape>", on_close)
                 edit_win.protocol("WM_DELETE_WINDOW", on_close)
                 edit_win.bind("<Return>", confirm_edit)
                 
                 btn_frame = tk.Frame(edit_win)
                 btn_frame.pack(pady=10, side="bottom", fill="x", padx=10)
                 tk.Button(btn_frame, text="保存 (Enter)", command=confirm_edit, bg="#ccff90", height=2).pack(side="left", fill="x", expand=True, padx=5)
                 tk.Button(btn_frame, text="取消 (Esc)", command=on_close, height=2).pack(side="left", fill="x", expand=True, padx=5)

            tk.Button(btn_frame, text="✏️ 修改阈值", command=edit_selected).pack(side="left", padx=10)
            tk.Button(btn_frame, text="🗑️ 删除规则 (Del)", command=delete_selected, fg="red").pack(side="left", padx=10)
            def manual_refresh():
                if self.live_strategy:
                    # 💥 强制从 JSON/DB 重新加载，捕捉后台平仓等外部变更
                    self.live_strategy.load_monitors()
                load_data()
                toast_message(self, "监控列表已刷新")

            tk.Button(btn_frame, text="刷新列表", command=manual_refresh).pack(side="left", padx=10)

            # 绑定选中事件
            tree.bind("<<TreeviewSelect>>", lambda e: refresh_stats())
            # 初始刷新
            refresh_stats()

            tree.bind("<Button-1>", on_voice_on_click)
            tree.bind("<Button-3>", on_voice_right_click)
            # 双击编辑
            # tree.bind("<Double-1>", lambda e: edit_selected())
            tree.bind("<Double-1>", on_voice_tree_double_click)
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

            # --- 策略模拟测试 ---
            def test_selected_strategy():
                selected = tree.selection()
                if not selected:
                    messagebox.showinfo("提示", "请先选择一条规则")
                    return
                
                item = selected[0]
                values = tree.item(item, "values")
                code = values[0]
                name = values[1] 
                
                # 调用主界面的策略测试逻辑，进行信号确认与模拟交易入口
                self.test_strategy_for_stock(code, name)

            tk.Button(top_frame, text="🧪 模拟策略交易", command=test_selected_strategy, bg="#e3f2fd", font=("Arial", 10, "bold")).pack(side="right", padx=5)
            
            # [NEW] Popup Toggle in Voice Manager
            tk.Checkbutton(
                top_frame,
                text="弹窗 (Pop)",
                variable=self.alert_popup_var,
                indicatoron=0,           # Toggle button style
                width=10,
                selectcolor="#ffccbc",   # Light orange when checked
                command=self.save_ui_states # Save state immediately
            ).pack(side="right", padx=5)
            
        except Exception as e:
            logger.error(f"Voice Monitor Manager Error: {e}")
            messagebox.showerror("错误", f"打开管理窗口失败: {e}")

    def open_live_signal_trace(self):
        """打开实时信号历史轨迹查询窗口 (PyQt6)"""

        try:
            # 🛠️ 窗口复用与失效重放
            if hasattr(self, '_live_signal_viewer') and self._live_signal_viewer is not None:
                try:
                    # 检查窗口是否仍然有效且未被析构
                    self._live_signal_viewer.show()
                    self._live_signal_viewer.raise_()
                    self._live_signal_viewer.activateWindow()
                    self._live_signal_viewer.refresh_data() # 自动刷新
                    return
                except Exception:
                    # 引用失效(如跨框架句柄异常)，重置引用以允许重新创建
                    self._live_signal_viewer = None
            else:
                from live_signal_viewer import LiveSignalViewer
                # 🚀 按照 KlineBackupViewer 模式进行对齐初始化
                # 使用 self.on_code_click 作为唯一联动入口，解决 tree_scroll_to_code 带来的 GIL 锁问题
                self._live_signal_viewer = LiveSignalViewer(
                    on_select_callback=self.on_code_click, # 核心对齐：统一代码点击联动
                    sender=getattr(self, 'sender', None),
                    main_app=self,                         # 借鉴架构对齐
                )
                
                self._live_signal_viewer.show()
                self._live_signal_viewer.raise_()
                self._live_signal_viewer.activateWindow()
                
                logger.info("LiveSignalViewer initialized with stable linkage.")
                toast_message(self, "实时信号查询已启动")
            
        except Exception as e:
            logger.error(f"Failed to open LiveSignalViewer: {e}\n{traceback.format_exc()}")
            messagebox.showerror("错误", f"启动信号查询窗口失败: {e}")

    def open_stock_selection_window(self):
        from stock_selection_window import StockSelectionWindow
        from stock_selector import StockSelector
        """打开策略选股与人工复核窗口 (支持窗口复用)"""
        # 1. 确保 selector存在且数据最新
        try:
            if not hasattr(self, 'selector') or self.selector is None:
                self.selector = StockSelector(df=getattr(self, 'df_all', None))
            else:
                # ✅ 关键：更新已有 selector 的数据引用，确保 MarketPulse 也能看到最新数据
                if hasattr(self, 'df_all') and not self.df_all.empty:
                    self.selector.df_all_realtime = self.df_all
                    self.selector.resample = self.global_values.getkey("resample") or 'd'
        except Exception as e:
            logger.error(f"StockSelector 初始化/更新失败: {e}")
            self.selector = None

        # 2. 窗口复用逻辑
        if self._stock_selection_win and self._stock_selection_win.winfo_exists():
            try:
                # ✅ 更新窗口内部引用 (防止 strategy 重启后引用失效)
                self._stock_selection_win.live_strategy = getattr(self, 'live_strategy', None)
                self._stock_selection_win.selector = self.selector
                
                # ✅ 强制刷新数据 (force=True 重新跑筛选)
                self._stock_selection_win.load_data(force=True)
                
                self._stock_selection_win.deiconify()
                self._stock_selection_win.lift()
                self._stock_selection_win.focus_force()
                return
            except Exception as e:
                logger.warning(f"复用选股窗口异常: {e}")

        # 3. 新建窗口
        try:
            self._stock_selection_win = StockSelectionWindow(self, getattr(self, 'live_strategy', None), self.selector)
            
        except Exception as e:
            logger.error(f"打开选股窗口失败: {e}")
            messagebox.showerror("错误", f"打开选股窗口失败: {e}")
            
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
            self._search_after_id = self._schedule_after(200, refresh_buttons)

        all_cols = [c for c in self.df_all.columns if default_filter(c)]
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

            logger.info(f'replace_column get_scaled_value:{self.get_scaled_value()}')
            self._setup_tree_columns(self.tree,new_columns, sort_callback=self.sort_by_column, other={})
            self.adjust_column_widths()
            # 重新加载数据
            if apply_search:
                self.apply_search()
            else:
                # 重新加载数据
                self.tree.after(100, lambda: self.refresh_tree(self.df_all, force=True))

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

        self._setup_tree_columns(tree,cols_to_show, sort_callback=sort_func, other={})


        # logger.info(f"[Tree Reset] applied cols={list(tree['columns'])}")

    def tree_scroll_to_code(self, code, select_win=False, vis=False):
        """外部调用：定位特定代码 (Thread-Safe via LinkageManagerProxy)"""
        if not code:
            return False

        # [ROOT-FIX] 1. 立即非阻塞投递联动指令 (多进程处理 TDX/剪切板)
        if vis:
            self.sender.send(code)
                
        def _ui_action():
            try:
                # 2. [GUI] 同步启动可视化器进程/指令 (主线程安全)
                if vis and hasattr(self, 'vis_var') and self.vis_var.get():
                    self.open_visualizer(code)

                # 3. [GUI] 树视图滚动定位
                found = False
                for iid in self.tree.get_children():
                    values = self.tree.item(iid, "values")
                    if values and str(values[0]) == str(code):
                        self.tree.selection_set(iid)
                        self.tree.focus(iid)
                        self.tree.see(iid)
                        found = True
                        break
                
                if select_win:
                    self.original_push_logic(code)

            except Exception as e:
                logger.error(f"tree_scroll_to_code error: {e}")

        # 4. 派发到 UI 线程执行 GUI 任务
        self._schedule_after(0, _ui_action)
        return True
        
    # def on_tree_click_for_tooltip(self, event,stock_code=None,stock_name=None,is_manual=False):
    #     """处理树视图点击事件，延迟显示提示框"""
    #     logger.debug(f"[Tooltip] 点击事件触发: x={event.x}, y={event.y}")
    #     if not is_manual and not self.tip_var.get():
    #         return
    #     # 取消之前的定时器
    #     if getattr(self, '_tooltip_timer', None):
    #         try:
    #             self.after_cancel(self._tooltip_timer)
    #         except Exception:
    #             pass
    #         self._tooltip_timer = None

    #     # 销毁之前的提示框
    #     if getattr(self, '_current_tooltip', None):
    #         try:
    #             self._current_tooltip.destroy()
    #         except Exception:
    #             pass
    #         self._current_tooltip = None

    #     if stock_code is None:
    #         # 获取点击的行
    #         item = self.tree.identify_row(event.y)
    #         if not item:
    #             logger.debug("[Tooltip] 未点击到有效行")
    #             return

    #         # 获取股票代码
    #         values = self.tree.item(item, 'values')
    #         if not values:
    #             logger.debug("[Tooltip] 行没有数据")
    #             return
    #         stock_code = str(values[0])  # code在第一列
    #         stock_name = str(values[1])  # code在第二列
            
    #     else:
    #         stock_code = stock_code
    #     self.test_strategy_for_stock(stock_code, stock_name)
    #     # x_root, y_root = event.x_root, event.y_root  # 保存坐标
    #     logger.debug(f"[Tooltip] 获取到代码: {stock_code}, 设置0.2秒定时器")

    #     # 设置0.2秒延迟定时器
    #     self._tooltip_timer = self._schedule_after(200, lambda e=event:self.show_stock_tooltip(stock_code, e))


    # def show_stock_tooltip(self, code, event):
    #     """显示股票信息提示框，支持位置保存/加载"""
    #     logger.debug(f"[Tooltip] show_stock_tooltip 被调用: code={code}")

    #     # 清理定时器引用
    #     self._tooltip_timer = None

    #     # 从 df_all 获取股票数据
    #     if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
    #         logger.debug("[Tooltip] df_all 为空或不存在")
    #         return

    #     # 清理代码前缀
    #     code_clean = code.strip()
    #     for icon in ['🔴', '🟢', '📊', '⚠️']:
    #         code_clean = code_clean.replace(icon, '').strip()

    #     if code_clean not in self.df_all.index:
    #         logger.debug(f"[Tooltip] 代码 {code_clean} 不在 df_all.index 中")
    #         return

    #     stock_data = self.df_all.loc[code_clean]
    #     stock_name = stock_data.get('name', code_clean) if hasattr(stock_data, 'get') else code_clean

    #     logger.debug(f"[Tooltip] 找到股票数据，准备创建提示框")

    #     # 关闭已存在的 tooltip
    #     if hasattr(self, '_current_tooltip') and self._current_tooltip:
    #         try:
    #             self._current_tooltip.destroy()
    #         except:
    #             pass

    #     # 创建 Toplevel 窗口（带边框，可拖拽）
    #     window_id = "stock_tooltip"
    #     win = tk.Toplevel(self)
    #     win.title(f"📊 {stock_name} ({code_clean})")
    #     win.configure(bg='#FFF8E7')
    #     win.resizable(True, True)
        
    #     # 加载保存的位置，或使用默认位置
    #     self.load_window_position(win, window_id, default_width=280, default_height=320)
    #     self._current_tooltip = win

    #     # ESC / 关闭时保存位置
    #     def on_close(event=None):
    #         self.save_window_position(win, window_id)
    #         win.destroy()
    #         self._current_tooltip = None
        
    #     win.bind("<Escape>", on_close)
    #     win.protocol("WM_DELETE_WINDOW", on_close)

    #     # 获取多行文本和对应颜色
    #     lines, colors = self._format_stock_info(stock_data)

    #     # 创建 Text 控件（无滚动条，用鼠标滚轮滚动）
    #     frame = tk.Frame(win, bg='#FFF8E7')
    #     frame.pack(fill='both', expand=True, padx=5, pady=5)
        
    #     text_widget = tk.Text(
    #         frame,
    #         bg='#FFF8E7',
    #         bd=0,
    #         padx=8,
    #         pady=6,
    #         wrap='word',
    #         font=("Microsoft YaHei", 9)
    #     )
    #     text_widget.pack(fill='both', expand=True)
        
    #     # 绑定鼠标滚轮滚动
    #     def on_mousewheel(event):
    #         text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
    #     text_widget.bind("<MouseWheel>", on_mousewheel)
    #     frame.bind("<MouseWheel>", on_mousewheel)

    #     for i, (line, color) in enumerate(zip(lines, colors)):
    #         tag_name = f"line_{i}"
    #         text_widget.insert(tk.END, line + "\n", tag_name)
    #         text_widget.tag_config(tag_name, foreground=color, font=("Microsoft YaHei", 9))

    #         # 检查 signal 行，单独设置图标颜色和大小
    #         if "signal:" in line:
    #             icon_index = line.find("👍")
    #             if icon_index == -1:
    #                 icon_index = line.find("🚀")
    #             if icon_index == -1:
    #                 icon_index = line.find("☀️")

    #             if icon_index != -1:
    #                 start = f"{i+1}.{icon_index}"
    #                 end = f"{i+1}.{icon_index+2}"
    #                 text_widget.tag_add(f"icon_{i}", start, end)
    #                 text_widget.tag_config(f"icon_{i}", foreground="#FF6600", font=("Microsoft YaHei", 12, "bold"))

    #     text_widget.config(state=tk.DISABLED)

    #     # 底部关闭按钮
    #     btn_frame = tk.Frame(win, bg='#FFF8E7')
    #     btn_frame.pack(fill='x', pady=3)
    #     tk.Button(btn_frame, text="关闭 (ESC)", command=on_close, width=10).pack()

    #     logger.debug(f"[Tooltip] 提示框已创建")

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
            f"📈 连阳: {stock_data.get('red', 'N/A')} 🔺",
            f"📉 连阴: {stock_data.get('gren', 'N/A')} 🔻",
            f"📈 突破布林: {boll}",
            f"  signal: {signal_icon} (low<10 & C>5)",
            f"  Upper:  {stock_data.get('upper', 'N/A'):.2f}",
            f"  Lower:  {stock_data.get('lower', 'N/A'):.2f}",
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
            'green',         # 连阴
            'orange',      # 布林带标题
            'orange',      # Upper
            'orange',      # Middle
            'orange',      # Lower
            'purple',      # 突破
            'purple',      # 强势
        ]

        return lines, colors


    def on_tree_click_for_tooltip(self, event, stock_code=None, stock_name=None, is_manual=False):
        if not is_manual and not self.tip_var.get(): return

        # 1. 取消舊任務 (核心防抖)
        if getattr(self, '_tooltip_timer', None):
            try:
                self.after_cancel(self._tooltip_timer)
            except Exception as e:
                logger.error(f"Error in task: {e}")
            self._tooltip_timer = None

        # 2. 獲取代碼 (解析當前點擊的股票)
        if stock_code is None:
            item = self.tree.identify_row(event.y)
            if not item: return
            values = self.tree.item(item, 'values')
            if not values: return
            stock_code, stock_name = str(values[0]), str(values[1])

        # 3. 定義打包任務 (包含計算 + 顯示)
        def do_heavy_work():
            # 只有當 200ms 內沒有新操作時，這兩行才會執行一次
            self.test_strategy_for_stock(stock_code, stock_name)
            self.show_stock_tooltip(stock_code, event)
            self._tooltip_timer = None # 執行完清空標記

        # 4. 使用你的安全調度器發送任務
        self._tooltip_timer = self._schedule_after(200, do_heavy_work)
        logger.debug(f"[Tooltip] 設置完整防抖 (200ms): {stock_code}")



    def show_stock_tooltip(self, code, event):
        """顯示股票信息提示框，支持窗口復用"""
        logger.debug(f"[Tooltip] show_stock_tooltip 調用: code={code}")
        self._tooltip_timer = None

        # 1. 獲取數據與清理代碼 (保持原樣)
        if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty: return
        code_clean = code.strip()
        for icon in ['🔴', '🟢', '📊', '⚠️']: code_clean = code_clean.replace(icon, '').strip()
        
        if code_clean not in self.df_all.index: return
        stock_data = self.df_all.loc[code_clean]
        stock_name = stock_data.get('name', code_clean)

        # 2. 【復用邏輯】檢查窗口是否存在
        win_exists = False
        if hasattr(self, '_current_tooltip') and self._current_tooltip:
            try:
                if self._current_tooltip.winfo_exists():
                    win = self._current_tooltip
                    
                    # 💡 關鍵：無論是最小化還是隱藏(withdrawn)，都必須執行 deiconify() 才能重新顯示
                    if win.state() != "normal":
                        win.deiconify()
                    
                    win.lift()      # 提到最前方
                    win_exists = True
            except Exception as e:
                logger.error(f"[Tooltip] 檢查窗口狀態出錯: {e}")
                win_exists = False

        if not win_exists:
            # 只有不存在時才創建新窗口
            win = tk.Toplevel(self)
            self._current_tooltip = win
            win.configure(bg='#FFF8E7')
            # 初始化時加載位置
            self.load_window_position(win, "stock_tooltip", default_width=280, default_height=320)
            
            # 定義隱藏函數 (替代原本的關閉)
            def on_hide(event=None):
                self.save_window_position(win, "stock_tooltip")
                win.withdraw() # 隱藏而不是銷毀
            
            win.bind("<Escape>", on_hide)
            win.protocol("WM_DELETE_WINDOW", on_hide)
            
            # 創建內部控件 (只在第一次創建時建立引用)
            win.frame = tk.Frame(win, bg='#FFF8E7')
            win.frame.pack(fill='both', expand=True, padx=5, pady=5)
            win.text_widget = tk.Text(win.frame, bg='#FFF8E7', bd=0, padx=8, pady=6, wrap='word', font=("Microsoft YaHei", 9))
            win.text_widget.pack(fill='both', expand=True)
            
            # 綁定滾輪
            win.text_widget.bind("<MouseWheel>", lambda e: win.text_widget.yview_scroll(int(-1*(e.delta/120)), "units"))
        else:
            win = self._current_tooltip

        # 3. 【內容更新】刷新標題與文本
        win.title(f"📊 {stock_name} ({code_clean})")
        
        # 開啟編輯權限
        win.text_widget.config(state=tk.NORMAL)
        win.text_widget.delete('1.0', tk.END) # 清空舊內容

        lines, colors = self._format_stock_info(stock_data)
        for i, (line, color) in enumerate(zip(lines, colors)):
            tag_name = f"line_{i}"
            win.text_widget.insert(tk.END, line + "\n", tag_name)
            win.text_widget.tag_config(tag_name, foreground=color, font=("Microsoft YaHei", 9))
            
            # 處理 Signal 圖標 (保持原樣邏輯)
            if "signal:" in line:
                for icon in ["👍", "🚀", "☀️"]:
                    idx = line.find(icon)
                    if idx != -1:
                        start, end = f"{i+1}.{idx}", f"{i+1}.{idx+2}"
                        win.text_widget.tag_add(f"icon_{i}", start, end)
                        win.text_widget.tag_config(f"icon_{i}", foreground="#FF6600", font=("Microsoft YaHei", 12, "bold"))

        win.text_widget.config(state=tk.DISABLED) # 重新鎖定
        logger.debug(f"[Tooltip] 提示框內容已更新: {code_clean}")



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
            self.refresh_tree(force=True)
            
            logger.info(f"✅ 特征颜色显示已{'开启' if enable_colors else '关闭'}")
        except Exception as e:
            logger.error(f"❌ 切换特征颜色失败: {e}")

    def refresh_tree(self, df=None, force=False):
        """刷新 TreeView，保证列和数据严格对齐。 (高性能版：强制节流)"""
        start_time = time.time()

        # ⚡ [OPTIMIZATION] 针对大列表 (5000+行) 强制节流，防止主线程被刷新操作占满导致卡死
        if not hasattr(self, '_last_tree_refresh_time'):
            self._last_tree_refresh_time = 0
            
        n_rows_current = len(df) if df is not None else (len(self.current_df) if hasattr(self, 'current_df') else 0)
        
        # 若非强制模式，大数据量下限制刷新频率 (3000行以上每3s刷新，5000行以上每8s刷新)
        throttle_interval = 2.0  # 默认 2s
        if n_rows_current > 5000:
            throttle_interval = 8.0
        elif n_rows_current > 2000:
            throttle_interval = 4.0
            
        if not force and (start_time - self._last_tree_refresh_time < throttle_interval):
            return
            
        self._last_tree_refresh_time = start_time
        
        if df is None:
            df = self.current_df.copy() if hasattr(self, 'current_df') else None

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

        # ⚡ UI 渲染指纹防抖：仅在数据变化或强制刷新时执行
        # 定义状态指纹：包含代码列表、列配置以及核心数值的采样 Hash
        # code_hash 决定了行数和顺序
        code_hash = hash(tuple(df['code'].astype(str).values)) if 'code' in df.columns else hash(len(df))
        cols_hash = hash(tuple(self.current_cols))
        
        # 数值 Hash (采样): 决定了单元格内容是否有变
        p_col = next((c for c in ['trade', 'percent', 'price', 'now'] if c in df.columns), None)
        df_val_hash = 0
        if p_col:
            n = len(df)
            samples = [0, n//4, n//2, 3*n//4, n-1] if n > 4 else list(range(n))
            df_val_hash = hash(tuple(df[p_col].iloc[samples].values))
            
        current_fingerprint = (code_hash, cols_hash, df_val_hash)

        # 触发判断：非强制刷新时，如果指纹一致则跳过
        if not force:
            if hasattr(self, '_last_refresh_fingerprint') and self._last_refresh_fingerprint == current_fingerprint:
                # 盘中通过 _apply_tree_data_sync 的 30s 兜底，此处指纹一致直接返回
                return
        
        self._last_real_refresh_ts = time.time()
        
        self._last_refresh_fingerprint = current_fingerprint
        # df = df.copy()  # ⚡ 移除 redundant copy()

        # 确保 code 列存在并为字符串（便于显示）
        if 'code' not in df.columns:
            df.insert(0, 'code', df.index.astype(str))

        # 要显示的列顺序
        cols_to_show = [c for c in self.current_cols if c in df.columns]
        
        # ✅ 使用增量更新机制
        if self._use_incremental_update and hasattr(self, 'tree_updater'):
            try:
                # 更新列配置（如果列发生变化）
                if tuple(self.tree_updater.columns) != tuple(cols_to_show):
                    diff_cols = set(self.tree_updater.columns) ^ set(cols_to_show)
                    self.tree_updater.columns = cols_to_show
                    logger.info(f"[TreeUpdater] 列配置变更: {len(cols_to_show)}列 (差异示例: {list(diff_cols)[:3]})")
                
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
                if stats.get("total_count", 0) % 10 == 0:  # ⚡ 使用total_count
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
        
        # 调整列宽 (⚡ [OPTIMIZE] 降低调整频率，仅在列变动或每20次刷新时调整)
        if not hasattr(self, "_last_adjust_cols") or self._last_adjust_cols != self.current_cols or getattr(self, "_update_count", 0) % 20 == 0:
            self.adjust_column_widths()
            self._last_adjust_cols = list(self.current_cols)
        logger.debug(f'refresh_tree_finish')
        # 更新状态栏
        self.update_status()
    
    def _refresh_tree_traditional(self, df, cols_to_show):
        """传统的全量刷新方式(作为增量更新的备用方案)"""
        cols = self.tree["displaycolumns"]
        self.tree["displaycolumns"] = ()

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
                        'category': row.get('category', ''),
                        'price': row.get('trade', row.get('close', 0)),
                        'high4': row.get('high4', 0),
                        'max5': row.get('max5', 0),
                        'max10': row.get('max10', 0),
                        'hmax': row.get('hmax', 0),
                        'hmax60': row.get('hmax60', 0),
                        'low4': row.get('low4', 0),
                        'low10': row.get('low10', 0),
                        'low60': row.get('low60', 0),
                        'lmin': row.get('lmin', 0),
                        'min5': row.get('min5', 0),
                        'cmean': row.get('cmean', 0),
                        'hv': row.get('hv', 0),
                        'lv': row.get('lv', 0),
                        'llowvol': row.get('llowvol', 0),
                        'lastdu4': row.get('lastdu4', 0),
                        # [NEW] 补全趋势识别关键字段
                        'ma5d': row.get('ma5d', 0),
                        'ma20d': row.get('ma20d', 0),
                        'ma60d': row.get('ma60d', 0)
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

        self.tree["displaycolumns"] = cols
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
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return  # 已销毁，直接返回
            
        scaled_val = self.get_scaled_value()
        
        # ⚡ 性能优化项: 如果数据量太大，不执行这种极其耗时的全表列宽自动计算
        if hasattr(self, 'current_df') and len(self.current_df) > 100:
            # 仅采样前 50 行和最后 20 行进行计算，足以覆盖大多数情况
            df_sample = pd.concat([self.current_df.head(50), self.current_df.tail(20)])
        else:
            df_sample = self.current_df if hasattr(self, 'current_df') else pd.DataFrame()

        cols = list(self.tree["columns"])

        # 遍历显示列并设置合适宽度
        for col in cols:
            # 跳过不存在于 df 的列
            if df_sample.empty or col not in df_sample.columns:
                # 仍要确保列有最小宽度
                self.tree.column(col, width=int(50 * scaled_val))
                continue
            
            # ⚡ 性能优化的计算方式：获取采样列值转换为字符串列表计算最大长度
            try:
                s_values = df_sample[col].astype(str).values
                max_len = max(len(col), max([len(x) for x in s_values]) if len(s_values) > 0 else 0)
            except Exception:
                max_len = len(col)
                
            # 基础集约化：7像素/字符，最小宽45
            width = int(min(max(max_len * 7, int(45 * scaled_val)), 350))

            if col == 'name':
                width = int(getattr(self, "_name_col_width", 120 * self.scale_factor))
            elif col == 'code':
                # 代码列 6 位，80 像素足够
                width = int(80 * self.scale_factor)
            elif col in ['ra', 'ral', 'win', 'red', 'kind', 'fib', 'fibl', 'op']:
                # 极窄技术指标列
                width = int(45 * self.scale_factor)

            self.tree.column(col, width=int(width))
        logger.debug(f'adjust_column_widths optimized done (rows:{len(df_sample)}) :{len(cols)}')
    # ----------------- 排序 ----------------- #
    def sort_by_column(self, col, reverse):
        if col not in self.current_df.columns:
            return
        self.select_code = None
        self.sortby_col =  col
        self.sortby_col_ascend = not reverse
        logger.debug(f'self.sortby_col_ascend: {self.sortby_col_ascend}')
        if col in ['code']:
            df_sorted = self.current_df.reset_index(drop=True).sort_values(
                by=col, key=lambda s: s.astype(str), ascending=not reverse)

        elif pd.api.types.is_numeric_dtype(self.current_df[col]):
            df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        elif col == 'name' and getattr(self, '_use_feature_marking', False) and hasattr(self, 'feature_marker'):
            # ✅ 名称排序支持图标优先级（与选股窗口逻辑一致）
            # 生成带图标的辅助排序序列
            def _name_icon_key(row):
                row_data = {
                    'percent': row.get('percent', 0),
                    'volume': row.get('volume', 0),
                    'category': row.get('category', ''),
                    'price': row.get('price', row.get('trade', 0)),
                    'high4': row.get('high4', 0),
                    'max5': row.get('max5', 0),
                    'max10': row.get('max10', 0),
                    'hmax': row.get('hmax', 0),
                    'hmax60': row.get('hmax60', 0),
                    'low4': row.get('low4', 0),
                    'low10': row.get('low10', 0),
                    'low60': row.get('low60', 0),
                    'lmin': row.get('lmin', 0),
                    'min5': row.get('min5', 0),
                    'cmean': row.get('cmean', 0),
                    'hv': row.get('hv', 0),
                    'lv': row.get('lv', 0),
                    'llowvol': row.get('llowvol', 0),
                    'lastdu4': row.get('lastdu4', 0)
                }
                icon = self.feature_marker.get_icon_for_row(row_data)
                return f"{icon} {row['name']}" if icon else row['name']
            
            sort_aux = self.current_df.apply(_name_icon_key, axis=1)
            df_sorted = self.current_df.sort_values(by=col, key=lambda _: sort_aux, ascending=not reverse)
        else:
            df_sorted = self.current_df.sort_values(by=col, key=lambda s: s.astype(str), ascending=not reverse)

        self.refresh_tree(df_sorted, force=True)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))
        self.tree.yview_moveto(0)


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

    # def _on_search_var_change(self, *_):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     # [FIX] 当 val1 为空时，不应该仅用 val2 触发搜索
    #     # 因为清空 val1 通常意味着用户想要查看全部数据
    #     if not val1:
    #         # 如果有挂起的搜索任务，取消它
    #         if self._search_job:
    #             self.after_cancel(self._search_job)
    #             self._search_job = None
    #         # 清除上次值，避免后续误判
    #         if hasattr(self, "_last_value"):
    #             self._last_value = ""
    #         return  # 不触发搜索

    #     # 构建原始查询语句 (统一使用 parts 逻辑与 apply_search 保持对齐，决定 _last_value 是否相等)
    #     parts = []
    #     if val1: parts.append(f"({val1})")
    #     if val2: parts.append(f"({val2})")
    #     query = " and ".join(parts)

    #     # 如果新值和上次一样，就不触发
    #     if hasattr(self, "_last_value") and self._last_value == query:
    #         return
    #     self._last_value = query

    #     if self._search_job:
    #         self.after_cancel(self._search_job)
    #     self._search_job = self._schedule_after(3000, self.apply_search)  # 3000ms后执行


    def _on_search_var_change(self, *_):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        # 构建 query
        parts = [v for v in (val1, val2) if v]
        query = " and ".join(f"({p})" for p in parts)

        # 如果 query 没变，不触发搜索，也不重置 after
        if getattr(self, "_last_value", None) == query:
            return

        # 更新 _last_value
        self._last_value = query

        # 取消之前的搜索任务
        if getattr(self, "_search_job", None):
            self.after_cancel(self._search_job)
        
        # 3 秒后触发 apply_search
        self._search_job = self._schedule_after(3000, self.apply_search)

    def _format_history_list(self, history_list, mapping_dict):
        """Helper to format history items with notes and update mapping"""
        display_list = []
        mapping_dict.clear() # Reset mapping when re-formatting entire list
        for item in history_list:
            if isinstance(item, dict):
                q = item.get("query", "")
                note = item.get("note", "")
            else:
                q = str(item)
                note = ""
            
            if not q: continue
            
            label = f"{note} ({q})" if note else q
            display_list.append(label)
            mapping_dict[label] = q
        return display_list

    def sync_history_from_QM(self, **kwargs):
        """当 QueryHistoryManager 内部变动（添加、使用、编辑、删除）时回调同步到主窗口"""
        self.query_manager.clear_hits()
        source = kwargs.get("source", "")
        selected_query = kwargs.get("selected_query")

        # ⚙️ 统一处理 history1 ~ history4
        configs = [
            ("search_history1", "search_history1", "search_combo1", "search_map1"),
            ("search_history2", "search_history2", "search_combo2", "search_map2"),
            ("search_history3", "search_history3", "search_combo3", None),
            ("search_history4", "search_history4", "search_combo4", "search_map4"),
            ("search_history5", "search_history5", "search_combo5", "search_map5"),
        ]

        for arg_key, attr_name, combo_name, map_name in configs:
            if arg_key in kwargs:
                raw_h = kwargs[arg_key]
                # 🛡️ 强制检查：防止历史记录交叉引用
                others = [getattr(self.query_manager, f"history{i}") for i in range(1, 5) if f"history{i}" != arg_key[-8:]]
                if any(raw_h is other for other in others):
                    logger.warning(f"⚠️ sync_history_from_QM 检出交叉引用 ({arg_key})，已跳过同步")
                    continue

                # 格式化并更新本地列表
                if map_name:
                    mapping = getattr(self, map_name, {})
                    formatted = self._format_history_list(raw_h, mapping)
                    setattr(self, attr_name, formatted)
                else:
                    # history3 等简单列表
                    setattr(self, attr_name, [r["query"] for r in raw_h])

                # 更新 UI Combobox
                if hasattr(self, combo_name):
                    combo = getattr(self, combo_name)
                    # 检查 combo 是否还是有效的 (尤其是 history3 可能在 KLineMonitor 中)
                    if hasattr(combo, 'winfo_exists') and combo.winfo_exists():
                        combo['values'] = getattr(self, attr_name)
                    elif combo_name == "search_combo3":
                        # history3 特殊处理：KLineMonitor 联动
                        if hasattr(self, "kline_monitor") and getattr(self.kline_monitor, "winfo_exists", lambda: False)():
                            try:
                                self.kline_monitor.refresh_search_combo3()
                                if source == "use" and selected_query:
                                    self.kline_monitor.search_var.set(selected_query)
                                    self.kline_monitor.search_code_status(onclick=True)
                            except Exception as e:
                                logger.debug(f"KLineMonitor sync failed: {e}")

                # 如果是"使用"动作，且当前历史匹配，同步 Var 以触发 apply_search
                if source == "use" and selected_query and arg_key == self.query_manager.current_key:
                    var_name = f"search_var{arg_key[-1]}"
                    if hasattr(self, var_name):
                        getattr(self, var_name).set(selected_query)
                        # 如果是 history4，手动触发一次搜索
                        if arg_key == "history4":
                            self.apply_search()
        
        # ✅ 子窗口同步：转发给策略白盒管理窗口
        if hasattr(self, "_strategy_manager_win") and self._strategy_manager_win and getattr(self._strategy_manager_win, "winfo_exists", lambda: False)():
            try:
                self._strategy_manager_win._on_history_sync(**kwargs)
            except Exception as e:
                logger.debug(f"StrategyManager forward sync failed: {e}")

    def sync_history(self, val, search_history, combo, history_attr, current_key):
        # [MODIFIED] Helper to get search map
        search_map = {}
        if history_attr == 'history1' and hasattr(self, 'search_map1'):
            search_map = self.search_map1
        elif history_attr == 'history2' and hasattr(self, 'search_map2'):
            search_map = self.search_map2

        # [MODIFIED] Reconstruct display label if note exists (for BOTH edited and new paths)
        display_val = val
        history_data = getattr(self.query_manager, history_attr, [])
        # 'val' passed here is usually the raw query (e.g. from the entry box or edit result)
        found_item = next((item for item in history_data if item.get("query") == val), None)
        
        if found_item and found_item.get("note"):
            note = found_item["note"]
            display_val = f"{note} ({val})"
            # Update map
            search_map[display_val] = val

        # ⚙️ 检查是否是刚编辑过的 query
        edited_pair = getattr(self.query_manager, "_just_edited_query", None)
        if edited_pair:
            old_query, new_query = edited_pair
            # 清除标记，防止影响下次
            self.query_manager._just_edited_query = None
            
            # Logic: If val matches new_query, we replace old_query with new formatted val
            if val == new_query:
                # Remove old_query (raw or formatted)
                to_remove_old = None
                if old_query in search_history:
                    to_remove_old = old_query
                elif search_map:
                    for item in search_history:
                        if search_map.get(item) == old_query:
                            to_remove_old = item
                            break
                
                if to_remove_old:
                    search_history.remove(to_remove_old)
                
                # Check if new formatted val is already there (unlikely if we just edited to it, but possible)
                if display_val not in search_history:
                    search_history.insert(0, display_val)

            elif val == old_query:
                 # 若 val 仍是旧的，直接跳过同步 (should not happen if logic is correct upstream)
                return
        else:
            # [MODIFIED] Remove existing item if it matches val (raw or formatted)
            to_remove = None
            if display_val in search_history:
                to_remove = display_val
            elif val in search_history:
                to_remove = val
            elif search_map:
                # Check if val is the raw query for any formatted item
                for item in search_history:
                    if search_map.get(item) == val:
                        to_remove = item
                        break
            
            if to_remove:
                search_history.remove(to_remove)
            
            search_history.insert(0, display_val)
            # if len(search_history) > 20:
            #     search_history[:] = search_history[:20]
        combo['values'] = search_history
        try:
            # Entry shows raw val, list shows formatted display_val
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
            # [MODIFIED] Resolve display label to raw query
            raw_q = search_map.get(q, q) if search_map else q
            
            if raw_q in existing_queries:
                # 保留原来的 note / starred
                new_history.append(existing_queries[raw_q])
            else:
                # 新建
                # if hasattr(self, "_last_value") and self._last_value.find(q) >=0:
                #     continue
                new_history.append({"query": raw_q, "starred":  0, "note": ""})

        setattr(self.query_manager, history_attr, new_history)

        if self.query_manager.current_key == current_key:
            self.query_manager.current_history = new_history
            self.query_manager.refresh_tree()

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
            current_categories =  list(top5.keys())  #保持顺序

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

    def on_code_click(self, code, date=None):
        """点击异动窗口中的股票代码 - 线程安全异步版"""
        if not code: return
        
        def _async_logic():
            try:
                if code != getattr(self, 'select_code', None):
                    self.select_code = code
                    logger.debug(f"select_code activated: {code} Date: {date}")
                    self.sender.send(code)
                    # 联动 Visualizer (如果启用)
                    if hasattr(self, 'vis_var') and self.vis_var.get():
                        self.open_visualizer(code, timestamp=date)
            except Exception as e:
                logger.error(f"Error in on_code_click async logic: {e}")

        # 🚀 [CORE FIX] 无论调用者是谁，都切回主线程并延迟 10ms 执行，防止 UI 死锁
        self._schedule_after(10, _async_logic)
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
        # === 有新增或消失 ===
        if added or removed:
            if added:
                tk.Label(scroll_frame, text="🆕 新增概念", font=self.default_font, fg="green").pack(anchor="w", pady=(0, 5))
                for c in added:
                    tk.Label(scroll_frame, text=c, fg="blue", font=self.default_font_bold).pack(anchor="w", padx=5)
                    stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)[:limit]  # 只取前 limit
                    for code, name, percent, volume in stocks:
                        rank = 0
                        if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                            val = self.df_all.loc[code].get('Rank', 0)
                            rank = int(val) if pd.notna(val) else 0
                        lbl = tk.Label(scroll_frame, text=f"  {code} {name} R:{rank:<4} {percent:>6.2f}% {volume}",
                                       fg="black", cursor="hand2", anchor="w", takefocus=True)    # ⭐ 必须
                        lbl.pack(anchor="w", padx=6)
                        lbl._code = code
                        lbl._concept = c
                        idx = len(self._label_widgets)
                        lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                        lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
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
                    rank = 0
                    if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                         val = self.df_all.loc[code].get('Rank', 0)
                         rank = int(val) if pd.notna(val) else 0
                    lbl = tk.Label(scroll_frame, text=f"  {code} {name} R:{rank:<4} {percent:>6.2f}% {volume}",
                                   fg="gray", cursor="hand2", anchor="w",takefocus=True)    # ⭐ 必须
                    lbl.pack(anchor="w", padx=6)
                    lbl._code = code
                    lbl._concept = c
                    idx = len(self._label_widgets)
                    lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                    lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
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
        else:
            allowed = r'\-\(\)'
            pattern = rf'[\u4e00-\u9fa5]+[A-Za-z0-9{allowed}（）]*'
            matches = re.findall(r'[\u4e00-\u9fa5]+[A-Za-z0-9\-\(\)（）]*', clipboard_text)
            if matches:
                # clipboard_text = f'category.str.contains("^{matches[0]}")'
                clipboard_text = f'category.str.contains("{matches[0]}")'

        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)

        # # 直接更新 _last_value，防止防抖再触发
        # val1 = self.search_var1.get().strip()
        # val2 = self.search_var2.get().strip()
        # parts = [v for v in (val1, val2) if v]
        # query = " and ".join(f"({p})" for p in parts)
        # self._last_value = query

        # # 立即执行搜索
        # self.apply_search()

    def on_right_click_search_var4(self, event):
        """search_var4 的右键快捷键，逻辑同 var2"""
        self.on_right_click_search_var2(event)


    def _on_label_on_code_click(self, code,idx):
        self._update_selection_top10(idx)
        """点击异动窗口中的股票代码"""
        self.select_code = code

        # ✅ 可改为打开详情逻辑，比如：
        self.sender.send(code)
        # Auto-launch Visualizer if enabled
        if hasattr(self, 'vis_var') and self.vis_var.get() and code:
            self.open_visualizer(code)
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
        if self.select_code == code:
            return
        stock_code = code
        self.select_code = code
        self.sender.send(code)
        # Auto-launch Visualizer if enabled
        if hasattr(self, 'vis_var') and self.vis_var.get() and code:
            self.open_visualizer(code)

        pyperclip.copy(code)
        if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
            # 如果发送成功，更新状态标签
            self.status_var2.set(f"发送成功: {stock_code}")
        else:
            # 如果发送失败，更新状态标签
            self.status_var2.set(f"发送失败: {stock_code}")

        self.tree_scroll_to_code(code)

    def _on_label_double_click_top10(self, code, idx):
        """
        双击股票标签时，显示该股票所属概念详情。
        如果 _label_widgets 不存在或 concept_name 获取失败，
        则自动使用 code 计算该股票所属强势概念并显示详情。
        """
        try:
            # ---------------- 原逻辑 ----------------
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
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                self.open_visualizer(code)

    def _bind_copy_expr(self, win):
        """绑定或重新绑定复制表达式按钮"""
        btn_frame = getattr(win, "_btn_frame", None)
        if btn_frame is None: return
        # 销毁旧按钮
        if hasattr(win, "_btn_copy_expr") and win._btn_copy_expr.winfo_exists():
            win._btn_copy_expr.destroy()
        def _copy_expr():
            concept = getattr(win, "_concept_name","未知概念")
            # q = f'category.str.contains("{concept}", na=False)'
            q = concept
            pyperclip.copy(q)
            self._schedule_after(100, lambda: toast_message(self,f"已复制筛选条件：{q}"))
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
        if threading.current_thread() != threading.main_thread():
            logger.error("❌ UI函数在子线程执行！已拦截")
            return
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

        unique_code = f"{concept_name or ''}_"
        # --- 检查是否已有相同 code 的窗口 ---
        for k, v in self._pg_top10_window_simple.items():
            if v.get("code") == unique_code and v.get("win") is not None and v.get("win").winfo_exists():
                # 已存在，显示并根据需要聚焦
                win_exist = v["win"]
                # logger.info(f'已存在，显示TK:{unique_code} (focus_force={focus_force})')
                win_exist.deiconify()      # 如果窗口最小化了，恢复
                
                if focus_force:
                    win_exist.lift()           # 提到最前
                    win_exist.focus_force()    # 获得焦点
                    win_exist.attributes("-topmost", True)
                    # 临时置顶后恢复，防止永久遮挡
                    win_exist.after(100, lambda: win_exist.attributes("-topmost", False))
                else:
                    # 不强制聚焦，仅提升层级确保可见
                    win_exist.lift()
                
                if hasattr(win_exist, "_tree_top10"):
                    try:
                        children = win_exist._tree_top10.get_children()
                        if children:
                            win_exist._tree_top10.selection_set(children[0])
                            # win_exist._tree_top10.focus_set()
                    except Exception:
                        pass
                return  # 不创建新窗口

        # --- 新窗口 ---
        win = tk.Toplevel(self)
        win.title(f"{concept_name} 概念前10放量上涨股")
        # win.minsize(460, 320)
        real_width = int(saved_width * self.scale_factor)
        real_height = int(saved_height * self.scale_factor)
        win.minsize(real_width, real_height)
        
        # 🚀 [NEW] 加载历史位置
        window_name = f"concept_top10_window-{unique_code}"
        self.load_window_position(win, window_name, default_width=saved_width, default_height=saved_height)

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

        # --- 布局优化：先放置底部控制栏，确保其在窗口缩小时不被遮挡 ---
        btn_frame = tk.Frame(win)
        btn_frame.pack(side="bottom", fill="x", pady=2)
        win._btn_frame = btn_frame

        # 主体 Treeview 容器
        frame = tk.Frame(win)
        frame.pack(side="top", fill="both", expand=True, padx=2, pady=1)

        columns = ("code", "name", "rank", "percent", "dff", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=3)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        col_texts = {"code":"代码","name":"名称","rank":"Rank","percent":"涨幅(%)","dff":"dff","volume":"成交量","red":"连阳","win":"主升"}
        limit_col = ['volume','red','win','dff']
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            width = 80 if col in ["name","code"] else (30 if col in limit_col else 50)
            tree.column(col, anchor="center", width=width)

        # 保存引用，独立窗口不复用 _concept_top10_win
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="#ff3b30")     # 强红：涨幅或低点大于前一日
        win._tree_top10.tag_configure("orange_row", foreground="#ff8c00")  # 深橙：高位或突破
        win._tree_top10.tag_configure("green_row", foreground="#00c853")   # 亮绿：跌幅明显
        win._tree_top10.tag_configure("blue_row", foreground="#444444")    # 深灰：弱势或低于均线 (ma5d)
        win._tree_top10.tag_configure("purple_row", foreground="#a855f7")  # 亮紫：成交量异常
        win._tree_top10.tag_configure("yellow_row", foreground="#ffd400")  # 金黄：临界或预警ag_configure("yellow_row", foreground="yellow")  # 临界或预警

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
            self.load_window_position(win, window_name, default_width=290, default_height=160)
        except Exception:
            win.geometry("290x160")

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
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                    self.open_visualizer(code)
            # 高亮
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                self._schedule_after(20, lambda: select_row_by_item(sel[0]))

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

        win._chk_auto = None # 已在 init 逻辑前移中处理
        # --- 自动更新控制栏 ---
        ctrl_frame = tk.Frame(btn_frame)
        ctrl_frame.pack(side="left", padx=6)

        # 🚀 [NEW] 添加精简“审计”按钮
        def _do_concept_audit():
            items = tree.get_children()
            if not items: return
            c_dict = {str(tree.item(i, 'values')[0]).zfill(6): str(tree.item(i, 'values')[1]) for i in items}
            if c_dict: self._run_dna_audit_batch(c_dict)

        btn_audit = tk.Button(ctrl_frame, text="🧬审计", command=_do_concept_audit)
        btn_audit.pack(side="left", padx=2)

        chk_auto = tk.BooleanVar(value=True)  # 默认开启自动更新
        chk_btn = tk.Checkbutton(ctrl_frame, text="", variable=chk_auto, takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=4, takefocus=False)
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
                # q = f'category.str.contains("{concept}", na=False)'
                q = concept
                pyperclip.copy(q)
                self._schedule_after(100, lambda: toast_message(self,f"已复制筛选条件：{q}"))
            btn = tk.Button(btn_frame, text="复制", command=_copy_expr)
            btn.pack(side="left", padx=4)
            win._btn_copy_expr = btn

        _bind_copy_expr(win)

        # --- 状态栏 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        # [UPGRADE] 使用 sunken 样式增强状态栏“生效”感
        lbl_status = tk.Label(btn_frame, text=f" {visible_count}/{total_count} 只", 
                              anchor="e", fg="#555", font=self.default_font,
                              relief="sunken", bd=1)
        lbl_status.pack(side="right", padx=(4, 2), ipadx=4)
        win._status_label_top10 = lbl_status

        # --- [REMOVED] Individual timers removed to prevent freezing.
        # Updates are now centralized in _apply_tree_data_sync -> update_all_top10_windows

        def on_close():
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
            if hasattr(self, '_concept_top10_win') and self._concept_top10_win == win:
                self._concept_top10_win = None

        win.on_close = on_close
        win.protocol("WM_DELETE_WINDOW", on_close)
        win.bind("<Escape>", lambda e: on_close())  # ESC关闭窗口

        # 填充数据
        self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
        if focus_force:
            # logger.info(f'新创建，focus_force聚焦并显示TK:{unique_code}')
            win.transient(self)              # 关联主窗口
            win.attributes("-topmost", True) # 临时置顶
            win.deiconify()
            win.lift()
            win.focus_force()    # 获得焦点
            if hasattr(win, "tree"):
                win.tree.selection_set(win.tree.get_children()[0])
                win.tree.focus_set()
        else:
            # 不强制聚焦，仅确保窗口可见
            win.deiconify()
            win.lift()


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
            self._schedule_after(500, do_focus)
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
            self._schedule_after(100, lambda: toast_message(self,f"概念【{concept_name}】暂无匹配股票"))
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

        columns = ("code", "name", "rank", "percent", "dff", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量"}
        col_texts = {"code":"代码","name":"名称","rank":"Rank","percent":"涨幅(%)","dff":"dff","volume":"成交量","red":"连阳","win":"主升"}
        limit_col = ['volume','red','win','dff']
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            # width = 80 if col == "name" else (40 if col == "rank" else 60)
            width = 80 if col in ["name","code"] else (30 if col in limit_col else 40)
            tree.column(col, anchor="center", width=width)

        # 保存引用
        win._content_frame_top10 = frame
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="#ff3b30")     # 强红：涨幅或低点大于前一日
        win._tree_top10.tag_configure("orange_row", foreground="#ff8c00")  # 深橙：高位或突破
        win._tree_top10.tag_configure("green_row", foreground="#00c853")   # 亮绿：跌幅明显
        win._tree_top10.tag_configure("blue_row", foreground="#444444")    # 深灰：弱势或低于均线 (ma5d)
        win._tree_top10.tag_configure("purple_row", foreground="#a855f7")  # 亮紫：成交量异常
        win._tree_top10.tag_configure("yellow_row", foreground="#ffd400")  # 金黄：临界或预警

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
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                    self.open_visualizer(code)
            # 高亮
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                self._schedule_after(20, lambda: select_row_by_item(sel[0]))

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

        # 🚀 [NEW] 添加精简“审计”按钮
        def _do_concept_audit_full():
            items = tree.get_children()
            if not items: return
            c_dict = {str(tree.item(i, 'values')[0]).zfill(6): str(tree.item(i, 'values')[1]) for i in items}
            if c_dict: self._run_dna_audit_batch(c_dict)

        btn_audit = tk.Button(ctrl_frame, text="🧬审计", command=_do_concept_audit_full)
        btn_audit.pack(side="left", padx=2)

        chk_auto = tk.BooleanVar(value=True)  # 默认开启自动更新
        chk_btn = tk.Checkbutton(ctrl_frame, text="", variable=chk_auto, takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=4, takefocus=False)
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
        # --- 在创建窗口或复用窗口后调用 ---
        self._bind_copy_expr(win)

        # --- 状态栏 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        lbl_status = tk.Label(btn_frame, text=f"显示 {visible_count}/{total_count} 只", anchor="e",
                              fg="#555", font=self.default_font)
        lbl_status.pack(side="right", padx=8)
        win._status_label_top10 = lbl_status

        # --- [REMOVED] Individual timers removed for performance.
        # Updates are now centralized.


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
        self._focus_top10_tree(win)

    def _call_concept_top10_win_no_focus(self, code, concept_name):
        """
        [FIX] 打开或复用 Top10 窗口，但不强制夺取焦点。
        供 Qt 线程通过队列调用，避免抢占 Qt 窗口焦点。
        """
        if code is None:
            return
        
        # 内部会调用 deiconify / lift, 但我们尽量不再额外 force_focus
        self.show_concept_top10_window(concept_name, code=code, bring_monitor_status=False)
        
        if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
            win = self._concept_top10_win
            
            # --- 更新标题 ---
            try:
                win.title(f"{concept_name} 概念前10放量上涨股")
            except:
                pass

            # --- 仅做最小化恢复，不强制置顶/聚焦 ---
            try:
                if win.state() == "iconic":
                    win.deiconify()
                # [REMOVED] win.lift(), win.focus_force(), win.attributes("-topmost")
            except Exception as e:
                logger.info(f"窗口状态检查失败(no_focus)： {e}")

            # --- 恢复 Canvas 滚动位置 (不调用 focus_set) ---
            if hasattr(win, "_canvas_top10"):
                try:
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    # [REMOVED] canvas.focus_set()
                    canvas.yview_moveto(yview[0])
                except:
                    pass

    def update_all_top10_windows(self):
        """强制刷新所有当前打开的 Concept Top10 窗口数据"""
        # 1. 刷新独立窗口字典
        if hasattr(self, "_pg_top10_window_simple"):
            for k, v in list(self._pg_top10_window_simple.items()):
                    win = v.get("win")
                    # 检查是否开启了自动刷新
                    if win and win.winfo_exists() and getattr(win, "_chk_auto", None) and win._chk_auto.get():
                        concept_name = getattr(win, "_concept_name", None)
                        if concept_name:
                            self._fill_concept_top10_content(win, concept_name)

        # 2. 刷新复用窗口
        if hasattr(self, "_concept_top10_win"):
            win = self._concept_top10_win
            # 检查是否开启了自动刷新
            if win and win.winfo_exists() and getattr(win, "_chk_auto", None) and win._chk_auto.get():
                concept_name = getattr(win, "_concept_name", None)
                if concept_name:
                    self._fill_concept_top10_content(win, concept_name)
        logger.debug(f'update_all_top10_windows_finish')

    def _fill_concept_top10_content(self, win, concept_name, df_concept=None, code=None, limit=50):
        """
        填充概念Top10内容到Treeview（支持实时刷新）。
        - df_concept: 可选，若为 None 则从 self.df_all 获取
        - code: 打开窗口或刷新时优先选中的股票 code
        - limit: 显示前 N 条
        """
        # ⭐ [OPTIMIZE] 智能重绘过滤：
        # 1. 如果窗口不可见且已有数据，则跳过刷新以节省 CPU。
        # 2. 如果窗口不可见但当前数据为空 (首次打开)，则强制刷新一次。
        tree = win._tree_top10
        has_items = len(tree.get_children()) > 0
        if not win.winfo_viewable() and has_items:
            return


        # 如果 df_concept 为 None，则从 self.df_all 动态获取
        if df_concept is None:
            # ✅ [OPTIMIZE] 缓存板块筛选索引，避免高频 str.contains 重复扫描
            pure_name = concept_name.split('(')[0]
            if not hasattr(self, "_concept_index_cache"): self._concept_index_cache = {}
            
            # 使用 concept 名称 + df_all 的长度和第一个代码作为缓存键 (粗略判断数据源是否变化)
            current_data_key = (len(self.df_all), self.df_all.index[0] if not self.df_all.empty else None)
            cache_entry = self._concept_index_cache.get(pure_name)
            
            if cache_entry and cache_entry['key'] == current_data_key:
                df_concept = self.df_all.loc[cache_entry['indices']]
            else:
                df_concept = self.df_all[self.df_all['category'].str.contains(pure_name, na=False)]
                self._concept_index_cache[pure_name] = {
                    'key': current_data_key,
                    'indices': df_concept.index
                }
            
        df_hash = hash(tuple(df_concept.index)) + hash(len(df_concept))
        # 增加数据版本的检测，确保价格等数值变化也能触发更新
        data_version = getattr(self, "_data_update_version", 0)
        
        if getattr(win, "_last_fill_hash", None) == df_hash and \
           getattr(win, "_last_fill_version", -1) == data_version:
            return
            
        win._last_fill_hash = df_hash
        win._last_fill_version = data_version
        
        # 只有在哈希变化时才清空旧行并重绘
        tree.delete(*tree.get_children())

        # 排序状态获取
        win._top10_sort_state = getattr(win, "_top10_sort_state", {"col": "percent", "asc": False})
        sort_col, ascending = win._top10_sort_state["col"], win._top10_sort_state["asc"]
        
        # 准备显示数据
        df_display = df_concept.sort_values(sort_col, ascending=ascending).head(limit) if sort_col in df_concept.columns else df_concept.head(limit)
        
        tree._full_df = df_concept.copy()
        tree._display_limit = limit
        tree.config(height=min(10, len(df_display)) if len(df_display) > 0 else 5)
        
        # 批量插入 (使用 itertuples 提升速度)
        code_to_iid = {}
        for idx, row in enumerate(df_display.itertuples()):
            code_row = row.Index
            iid = str(idx)
            # Row data (from itertuples namedtuple 'Pandas')
            row_dict = row._asdict()
            
            # 获取最新的实时行情
            latest_row = self.df_all.loc[code_row] if code_row in self.df_all.index else pd.Series(row_dict)
            if isinstance(latest_row, pd.DataFrame):
                latest_row = latest_row.iloc[0]
                
            percent = latest_row.get("percent", row_dict.get("percent", 0))
            # === 行条件判断 ===
            row_tags = get_row_tags(latest_row)

            if pd.isna(percent) or percent == 0:
                percent = latest_row.get("per1d", row_dict.get("per1d", 0))

            rank_val = latest_row.get("Rank", row_dict.get("Rank", 0))
            rank_str = str(int(rank_val)) if pd.notna(rank_val) else "0"

            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    code_row,
                    latest_row.get("name", row_dict.get("name", "")),
                    rank_str,
                    f"{percent:.2f}",
                    f"{latest_row.get('dff', row_dict.get('dff', 0)):.1f}",
                    f"{latest_row.get('volume', row_dict.get('volume', 0)):.1f}",
                    latest_row.get("red", row_dict.get("red", 0)),
                    latest_row.get("win", row_dict.get("win", 0)),
                ),
                tags=tuple(row_tags)
            )
            code_to_iid[code_row] = iid

        # --- 更新状态栏数量 ---
        if hasattr(win, "_status_label_top10") and win._status_label_top10.winfo_exists():
            visible_count = len(df_display[df_display["percent"] > 2])
            total_count = len(df_concept)
            win._status_label_top10.config(text=f"显示 {visible_count}/{total_count} 只")

        # --- 默认选中逻辑 ---
        children = list(tree.get_children())
        if children:
            # 优先使用窗口当前选中 code，其次使用传入 code
            target_code = getattr(win, "select_code", None) or code
            target_iid = code_to_iid.get(target_code, children[0])

            tree.selection_set(target_iid)
            tree.focus(target_iid)
            # # 强制刷新 Treeview 渲染，再滚动
            def scroll_and_highlight():
                try:
                    if tree.winfo_exists() and tree.exists(target_iid):
                        tree.see(target_iid)
                        self._highlight_tree_selection(tree, target_iid)
                except Exception as e:
                    # 静默处理：项可能在 50ms 延迟期间被删除或刷新
                    pass

            win.after(50, scroll_and_highlight)
            # 更新窗口索引和选中 code
            win._selected_index = children.index(target_iid)
            win.select_code = tree.item(target_iid, "values")[0]

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

        # map 'rank' to 'Rank' or ensure 'rank' exists for sorting
        if col == "rank":
            if "rank" not in tree._full_df.columns and "Rank" in tree._full_df.columns:
                 tree._full_df["rank"] = tree._full_df["Rank"]
            
            if "rank" in tree._full_df.columns:
                # 确保 rank 列为数值型，便于正确排序
                tree._full_df["rank"] = pd.to_numeric(tree._full_df["rank"], errors='coerce').fillna(9999)
        
        # 再次检查列是否存在（防止其他列名不对的情况）
        if col not in tree._full_df.columns:
            logger.warning(f"Sort column '{col}' not found in DataFrame columns: {tree._full_df.columns.tolist()}")
            return

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

            rank_val = row.get("Rank", 0)
            rank_str = str(int(rank_val)) if pd.notna(rank_val) else "0"

            tree.insert("", "end", iid=iid,
                        values=(code_row, row["name"], rank_str, f"{percent:.2f}", f"{row.get('dff',0):.1f}", f"{row.get('volume',0):.1f}", f"{row.get('red',0)}", f"{row.get('win',0)}"),tags=tuple(tags_for_row))

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

        # 高亮选中行，同时保留原有颜色标签（如 red_row）
        self._highlight_tree_selection(tree, item)

        # 设置 selection / focus 让键盘上下键能继续用
        tree.selection_set(item)
        tree.focus(item)

        # 获取 code 并执行逻辑
        code = tree.item(item, "values")[0]
        self._on_label_right_click_top10(code, int(item))

    

    def plot_top10_concepts_pg(self, top_n=10):
        """用 pyqtgraph 绘制 Top10 热点概念"""
        import pyqtgraph as pg
        from PyQt6 import QtWidgets, QtCore, QtGui 
        if not hasattr(self, "_pg_windows"):
            self._pg_windows = {}
            self._pg_data_hash = {}

    def plot_following_concepts_pg(self, code=None, top_n=10):
        import pyqtgraph as pg
        from PyQt6 import QtWidgets, QtCore, QtGui 
        if not hasattr(self, "_pg_windows"):
            self._pg_windows = {}
            self._pg_data_hash = {}

        # --- 获取股票数据 ---
        # [PERSISTENT] 使用全局默认排序视角 (True=看涨, False=看跌)
        def_reverse = getattr(self, "_pg_default_sort_reverse", True)
        
        if code is None or code == "总览":
            # get_global_concepts_ranking
            tcode, _ = self.get_stock_code_none(reverse=def_reverse)
            top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n, reverse=def_reverse)
            code = "总览"
            name = "All"
            unique_code = f"{code or ''}_{top_n or ''}"
            logger.info(f'concepts_pg concepts : {top_concepts[0]} unique_code: {unique_code} ')
        else:
            top_concepts = self.get_following_concepts_by_correlation(code, top_n=top_n, reverse=def_reverse)
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
        bullish_ratios = np.array([c[4] for c in top_concepts]) if len(top_concepts) > 0 and len(top_concepts[0]) > 4 else np.zeros(len(top_concepts))
        data_hash = hashlib.md5(str(concepts[:3]).encode()).hexdigest()

        # logger.info(f'concepts : {concepts} unique_code: {unique_code} ')
        # --- 创建主窗口 ---
        win = QtWidgets.QWidget()
        win.setWindowTitle(f"{code} 概念分析Top{top_n}")
        layout = QtWidgets.QVBoxLayout(win)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.dpi_scale =  1

        # 控制栏
        ctrl_layout = QtWidgets.QHBoxLayout()
        chk_auto = QtWidgets.QCheckBox("自动更新")
        spin_interval = QtWidgets.QSpinBox()
        spin_interval.setRange(5, 300)
        spin_interval.setValue(duration_sleep_time)
        spin_interval.setSuffix(" 秒")
        
        # ✅ [NEW] 添加排序切换按钮
        # 默认降序 (True): 展示领涨/最强概念
        # 升序 (False): 展示领跌/最弱概念
        def_reverse = getattr(self, "_pg_default_sort_reverse", True)
        win._sort_reverse = def_reverse
        btn_sort = QtWidgets.QPushButton("当前: 看涨(最强)" if def_reverse else "当前: 看跌(最弱)")
        btn_sort.setFixedWidth(120)
        
        def toggle_sort():
            new_val = not win._sort_reverse
            win._sort_reverse = new_val
            # 同步到全局默认 (解决重开变回看涨的问题)
            self._pg_default_sort_reverse = new_val
            
            btn_sort.setText("当前: 看涨(最强)" if new_val else "当前: 看跌(最弱)")
            logger.info(f"[UI] 用户切换排序方式: {'看涨' if new_val else '看跌'}, 正在强制刷新...")
            # 立即触发强制刷新
            self._refresh_pg_window(code, top_n, force=True)
            
        btn_sort.clicked.connect(toggle_sort)
        
        ctrl_layout.addWidget(chk_auto)
        ctrl_layout.addWidget(spin_interval)
        ctrl_layout.addWidget(btn_sort)
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
        # [OPTIMIZE] 适配 A 股红涨绿跌色彩逻辑
        brushes = []
        max_abs = max(np.abs(scores).max(), 1)
        for s in scores:
            if s >= 0:
                # 红色 (涨): 强度随数值增加
                intensity = int(min(255, 150 + (s/max_abs)*105))
                brushes.append(pg.mkBrush((intensity, 50, 50, 200)))
            else:
                # 绿色 (跌): 强度随跌幅增加
                intensity = int(min(255, 120 + (abs(s)/max_abs)*135))
                brushes.append(pg.mkBrush((40, intensity, 40, 200)))
        bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
        plot.addItem(bars)


        font = QtWidgets.QApplication.font()
        font_size = font.pointSize()
        self._font_size = font_size
        logger.info(f"concepts_pg 默认字体大小: {font_size}")
        texts = []
        max_abs_score = max(np.abs(scores).max(), 1)
        for i, (avg, score) in enumerate(zip(avg_percents, scores)):
            # [OPTIMIZE] 内容精简 + HTML 颜色 (白色增强对比度)
            # anchor: (0, 0.5) 是左对齐, (1, 0.5) 是右对齐
            # 若 score 为负, 文字应在柱子左侧, 故使用右对齐 anchor
            cur_anchor = (1, 0.5) if score < 0 else (0, 0.5)
            # 偏移量取最大绝对值的 2%
            offset = 0.02 * max_abs_score
            cur_pos = score - offset if score < 0 else score + offset
            
            # [OPTIMIZE] 显示趋势强度 [B XX%]
            b_ratio = bullish_ratios[i] if i < len(bullish_ratios) else 0
            b_tag = f" <span style='color: #FFD700;'>[B{int(b_ratio*100)}%]</span>" if b_ratio > 0 else ""
            
            text_val = f"<span style='color: white; font-weight: bold;'>{avg:+.2f}%{b_tag}</span>"
            text = pg.TextItem(html=text_val, anchor=cur_anchor)
            text.setPos(cur_pos, y[i])
            plot.addItem(text)
            texts.append(text)
            # logger.info(f"[DEBUG] : avg={avg:.2f}, score={score:.2f}")

        plot.getAxis('left').setTicks([list(zip(y, concepts))])


        # from PyQt5.QtCore import QPoint
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
            try:
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
                    self.tk_dispatch_queue.put(lambda: self.on_monitor_window_focus_pg(unique_code))

                    if 0 <= idx < len(concepts):
                        current_idx["value"] = idx
                        highlight_bar(idx)

                        if event.button() == QtCore.Qt.MouseButton.LeftButton:
                            def _action():
                                # [FIX] 使用不抢焦点的版本
                                self._call_concept_top10_win_no_focus(code, concepts[idx])
                                # 确保在 Tkinter 更新后，强制唤起 Qt 窗口并赋予焦点
                                win.raise_()
                                win.activateWindow()
                                win.setFocus()
                            self.tk_dispatch_queue.put(_action)

                        elif event.button() == QtCore.Qt.MouseButton.RightButton:
                            concept_text = concepts[idx]
                            clipboard = QtWidgets.QApplication.clipboard()
                            # copy_concept_text = f'category.str.contains("{concept_text}")'
                            copy_concept_text = concept_text
                            clipboard.setText(copy_concept_text)

                            from PyQt6.QtCore import QPoint
                            pos = event.screenPos()
                            pos_int = QPoint(int(pos.x()), int(pos.y()))
                            QtWidgets.QToolTip.showText(pos_int, f"已复制: {copy_concept_text}", win)
                        # ⭐ 未处理的按键继续向下传播
                        event.ignore()
            except Exception as e:
                logger.exception(f"Fatal Error in mouse_click: {e}")
                import traceback
                traceback.print_exc()

        plot.scene().sigMouseClicked.connect(mouse_click)

        # --- 鼠标悬停 tooltip ---
        def show_tooltip(event):
            try:
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
            except Exception as e:
                pass


        plot.scene().sigMouseMoved.connect(show_tooltip)

        # --- 键盘事件 ---
        # 必须显式设置 FocusPolicy 才能接收键盘事件
        win.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        
        def key_event(event):
            try:
                key = event.key()
                data = plot._data_ref  # ✅ 动态读取最新数据
                concepts = data.get("concepts", [])
                
                if key == QtCore.Qt.Key.Key_R:
                    self.tk_dispatch_queue.put(lambda: self.plot_following_concepts_pg(code, top_n))
                    event.accept()

                elif key in (QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_Escape):
                    QtCore.QTimer.singleShot(0, win.close)
                    event.accept()

                elif key == QtCore.Qt.Key.Key_Up:
                    current_idx["value"] = max(0, current_idx["value"] - 1)
                    highlight_bar(current_idx["value"])
                    def _key_action_up():
                        # [FIX] 使用不抢焦点的版本
                        self._call_concept_top10_win_no_focus(code, concepts[current_idx["value"]])
                        win.raise_()
                        win.activateWindow()
                        win.setFocus()
                    self.tk_dispatch_queue.put(_key_action_up)
                    event.accept()

                elif key == QtCore.Qt.Key.Key_Down:
                    current_idx["value"] = min(len(concepts) - 1, current_idx["value"] + 1)
                    highlight_bar(current_idx["value"])
                    def _key_action_down():
                        # [FIX] 使用不抢焦点的版本
                        self._call_concept_top10_win_no_focus(code, concepts[current_idx["value"]])
                        win.raise_()
                        win.activateWindow()
                        win.setFocus()
                    self.tk_dispatch_queue.put(_key_action_down)
                    event.accept()

                elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    idx = current_idx["value"]
                    if 0 <= idx < len(concepts):
                        # [FIX] 使用队列处理 Enter 键，保持 focus 在 Qt 窗口
                        def _key_action_enter():
                             self._call_concept_top10_win_no_focus(code, concepts[idx])
                             win.raise_()
                             win.activateWindow()
                             win.setFocus()
                        self.tk_dispatch_queue.put(_key_action_enter)
                    event.accept()
                # ⭐ 未处理的按键继续向下传播
                event.ignore()
            except Exception as e:
                logger.exception(f"Fatal Error in key_event: {e}")
                import traceback
                traceback.print_exc()

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

                # [OPTIMIZE] 动态更新标注逻辑 (适配负值且精简内容)
                max_abs_score = max(np.abs(scores).max(), 1)
                
                # 精简内容: 仅显示 avg 涨跌箭头与数值
                text_html = f"<span style='color: white; font-weight: bold;'>{arrow_avg} {avg:+.2f}%</span>"
                text.setHtml(text_html)

                # 动态锚点与偏移
                cur_anchor = (1, 0.5) if score < 0 else (0, 0.5)
                offset = 0.02 * max_abs_score
                cur_x = (score - offset if score < 0 else score + offset) * self.dpi_scale
                
                text.setPos(cur_x, y[i] * self.dpi_scale)
                text.setAnchor(cur_anchor)
            plot.update()

        # 定时轮询 DPI / 屏幕变化
        prev_screen = None
        prev_dpi = None
        base_fontsize = None


        def check_screen():
            nonlocal prev_screen, prev_dpi ,base_fontsize
            window_handle = win.windowHandle()
            if window_handle and window_handle.screen():
                screen = window_handle.screen()
            else:
                screen = self.app.primaryScreen()
            self._dpi_now = screen.logicalDotsPerInch()

            if prev_screen or  prev_dpi:
                if screen != prev_screen or self._dpi_now  != prev_dpi:
                    logger.info(f'dpi_now :{self._dpi_now } prev_dpi :{prev_dpi}')
                    prev_screen, prev_dpi = screen, self._dpi_now

                    font = self.app.font()
                    self.dpi_scale =  1.5 if self._dpi_now / 96 > 1.5 else self._dpi_now / 96
                    font.setPointSize(int(base_font_size * self.dpi_scale))
                    self.app.setFont(font)

            else:
                font = self.app.font()
                self.dpi_scale =  1.5 if self._dpi_now / 96 > 1.5 else self._dpi_now / 96
                font.setPointSize(int(self.base_font_size  * self.dpi_scale))
                self.app.setFont(font)
                logger.info(f'_dpi_now : {self._dpi_now} fontsize: {font.pointSize()} ratio :  {(self._dpi_now  / 96)}')

                logger.info(f'self._font_size init: {self._font_size}')
                prev_screen, prev_dpi = screen, self._dpi_now 

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
                        "follow_ratios": np.array([follow_ratios[i]]),
                        "bullish_ratios": np.array([bullish_ratios[i]]) # [NEW] 初始存储趋势占比
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
                        "follow_ratios": np.array([follow_ratios[i]]),
                        "bullish_ratios": np.array([bullish_ratios[i]]) # [NEW]
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


    def update_single_pg_bar(self, win, score, avg, concept, color):
        import pyqtgraph as pg
        from PyQt6 import QtWidgets, QtCore, QtGui
    def update_pg_plot(self, w_dict, code, top_n, concepts, scores, avg_percents, follow_ratios, bullish_ratios, force=False):
        """
        更新 PyQtGraph 条形图窗口（NoSQL 多 concept 版本），保证排序对齐：
        1. 每个 concept 独立保存初始分数和上次刷新分数。
        2. 绘制主 BarGraphItem 显示当前分数。
        3. 绘制增量条（相对于初始分数）。
        4. 增量条正增量绿色，负增量红色，文字箭头显示方向。
        5. 支持增量条闪烁。
        6. 自动恢复当天已有数据（NoSQL 存储）。
        """
        import pyqtgraph as pg
        from PyQt6 import QtWidgets, QtGui, QtCore
        try:

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

            # --- 窗口初始化各自 concept 数据 (三级缓存机制：窗口缓存 -> 全局缓存 -> 初始化) ---
            for i, c_name in enumerate(concepts):
                base_data = None
                prev_data = None
                
                # 索引安全保护
                try:
                    curr_score = scores[i]
                    curr_avg = avg_percents[i]
                    curr_follow = follow_ratios[i]
                    curr_bullish = bullish_ratios[i] if i < len(bullish_ratios) else 0
                except (IndexError, KeyError):
                    continue

                # 1. 获取/初始化初始基准 (Initial Benchmark)
                if c_name in win._init_prev_concepts_data:
                    base_data = win._init_prev_concepts_data[c_name]
                else:
                    global_init = getattr(self, "_global_concept_init_data", {})
                    base_data = global_init.get(c_name)
                    if base_data is None:
                        base_data = {
                            "concepts": [c_name],
                            "avg_percents": np.array([curr_avg]),
                            "scores": np.array([curr_score]),
                            "follow_ratios": np.array([curr_follow]),
                            "bullish_ratios": np.array([curr_bullish])
                        }
                        global_init[c_name] = base_data
                    win._init_prev_concepts_data[c_name] = base_data

                # 2. 获取/初始化实时备份 (Previous Data)
                if c_name in win._prev_concepts_data:
                    prev_data = win._prev_concepts_data[c_name]
                else:
                    global_prev = getattr(self, "_global_concept_prev_data", {})
                    prev_data = global_prev.get(c_name)
                    if prev_data is None:
                        prev_data = {
                            "concepts": [c_name],
                            "avg_percents": np.array([curr_avg]),
                            "scores": np.array([curr_score]),
                            "follow_ratios": np.array([curr_follow]),
                            "bullish_ratios": np.array([curr_bullish])
                        }
                        global_prev[c_name] = prev_data
                    win._prev_concepts_data[c_name] = prev_data

            # --- 检查是否需要刷新（数据完全一致时跳过） ---
            data_changed = force  # 如果是强制刷新，直接设为 True
            if force:
                logger.info("[DEBUG] 收到强制刷新指令，准备执行 UI 重绘 ✅")
            else:
                for i, c_name in enumerate(concepts):
                    prev_data = win._prev_concepts_data.get(c_name)
                    if prev_data is None:
                        data_changed = True
                        break
                    
                    # 越界安全比对
                    curr_bullish = bullish_ratios[i] if i < len(bullish_ratios) else 0
                    
                    if (abs(prev_data["avg_percents"][0] - avg_percents[i]) > 1e-6 or
                        abs(prev_data["scores"][0] - scores[i]) > 1e-6 or
                        abs(prev_data.get("bullish_ratios", [0])[0] - curr_bullish) > 1e-6):
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
            # [OPTIMIZE] 适配 A 股红涨绿跌色彩逻辑
            brushes = []
            max_abs_score = max(np.abs(scores).max(), 1)
            for s in scores:
                if s >= 0:
                    intensity = int(min(255, 150 + (s/max_abs_score)*105))
                    brushes.append(pg.mkBrush((intensity, 40, 40, 180))) # 红色 (涨)
                else:
                    intensity = int(min(255, 120 + (abs(s)/max_abs_score)*135))
                    brushes.append(pg.mkBrush((40, intensity, 40, 180))) # 绿色 (跌)
            
            main_bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
            plot.addItem(main_bars)
            # 确保横轴范围包含 0 且自适应（处理负值）
            plot.enableAutoRange(axis='x', enable=True)
            w_dict["bars"] = main_bars

            # --- 绘制增量条 ---
            delta_bars_list = []
            for i, c_name in enumerate(concepts):
                score = scores[i]
                base_score = win._init_prev_concepts_data[c_name]["scores"][0]
                delta = score - base_score

                if abs(delta) < 1e-6:
                    delta_bars_list.append(None)
                    continue

                color = (255, 50, 50, 150) if delta > 0 else (50, 255, 50, 150) # 红涨绿跌
                x0 = base_score if delta > 0 else score
                bar = pg.BarGraphItem(x0=x0, y=[y[i]], height=0.6, width=[abs(delta)], brushes=[pg.mkBrush(color)])
                plot.addItem(bar)
                delta_bars_list.append(bar)
            w_dict["delta_bars"] = delta_bars_list
            # logger.info(f'texts: {texts}')
            # --- 更新文字显示（顺序保持和 y 对齐） ---
            for i, text in enumerate(texts):
                score = scores[i]
                delta = score - win._init_prev_concepts_data[concepts[i]]["scores"][0]
                arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")

                # [OPTIMIZE] 标注精简 + 趋势增强 [B XX%]
                b_ratio = bullish_ratios[i] if i < len(bullish_ratios) else 0
                b_tag = f" <span style='color: #FF69B4; font-weight: bold;'>[B{int(b_ratio*100)}%]</span>" if b_ratio > 0 else ""
                
                text_html = f"<span style='color: white; font-size: 9pt; font-weight: bold;'>{arrow}{abs(delta):.1f} | {avg_percents[i]:+.2f}%{b_tag}</span>"
                text.setHtml(text_html)

                # 动态布局：正值向右看齐, 负值向左看齐 (解决遮挡问题)
                cur_anchor = (1, 0.5) if score < 0 else (0, 0.5)
                # 偏移量取最大绝对值的 2%
                offset = 0.02 * max_abs_score
                cur_x = (score - offset if score < 0 else score + offset) * self.dpi_scale
                
                text.setPos(cur_x, y[i] * self.dpi_scale)
                text.setAnchor(cur_anchor)

            plot.getAxis('left').setTicks([list(zip(y, concepts))])



            plot._data_ref["concepts"] = concepts
            plot._data_ref["scores"] = scores
            plot._data_ref["avg_percents"] = avg_percents
            plot._data_ref["follow_ratios"] = follow_ratios
            plot._data_ref["bullish_ratios"] = bullish_ratios
            plot._data_ref["bars"] = main_bars
            plot._data_ref["brushes"] = brushes


            # --- 保存当前刷新数据 ---
            for i, c_name in enumerate(concepts):
                win._prev_concepts_data[c_name] = {
                    "concepts": [c_name],
                    "avg_percents": np.array([avg_percents[i]]),
                    "scores": np.array([scores[i]]),
                    "follow_ratios": np.array([follow_ratios[i]]),
                    "bullish_ratios": np.array([bullish_ratios[i]]) # [NEW] 存储趋势占比
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

        except Exception as e:
            logger.exception(f"Fatal Error in update_pg_plot: {e}")
            import traceback
            traceback.print_exc()


    # --- 定时刷新 ---
    def _refresh_pg_window(self, code, top_n, force=False):
        try:
            unique_code = f"{code or ''}_{top_n or ''}"
            if unique_code not in self._pg_windows:
                return
            if not force and not cct.get_work_time():  # 仅非强制刷新时才受工作时间限制
                return

            logger.info(f'unique_code : {unique_code}')
            w_dict = self._pg_windows[unique_code]
            win = w_dict["win"]

            # --- 获取最新概念数据 ---
            sort_reverse = getattr(win, "_sort_reverse", True)
            logger.info(f"[UI_SYNC] 正在为 {code} 刷新数据, 排序方向: {'降序(看涨)' if sort_reverse else '升序(看跌)'}")
            
            if (code == "总览" or code is None or code == ""):
                tcode, _ = self.get_stock_code_none(reverse=sort_reverse)
                top_concepts_sorted = self.get_following_concepts_by_correlation(tcode, top_n=top_n, reverse=sort_reverse)
            else:
                top_concepts_sorted = self.get_following_concepts_by_correlation(code, top_n=top_n, reverse=sort_reverse)

            if not top_concepts_sorted:
                logger.info(f"[Auto] 无法刷新 {code} 数据为空")
                return

            concepts = [c[0] for c in top_concepts_sorted]
            scores = np.array([c[1] for c in top_concepts_sorted])
            avg_percents = np.array([c[2] for c in top_concepts_sorted])
            follow_ratios = np.array([c[3] for c in top_concepts_sorted])
            bullish_ratios = np.array([c[4] for c in top_concepts_sorted]) if len(top_concepts_sorted) > 0 and len(top_concepts_sorted[0]) > 4 else np.zeros(len(top_concepts_sorted))

            # --- 校验概念列表是否为空 ---
            if len(concepts) == 0:
                 return

            # --- 判断概念顺序是否变化 ---
            old_concepts = w_dict.get("_concepts", [])
            concept_changed = old_concepts != concepts
            # --- 调试输出 ---
            # logger.info(f'_refresh_pg_window top_concepts_sorted : {top_concepts_sorted} unique_code: {unique_code} ')
            logger.info(f'更新图形: {unique_code} : {concepts}')
            # --- 更新图形 ---
            self.update_pg_plot(w_dict, code, top_n, concepts, scores, avg_percents, follow_ratios, bullish_ratios, force=force)

            logger.info(f"[Auto] 已自动刷新 {code}")

        except Exception as e:
            logger.exception(f"Fatal Error in _refresh_pg_window: {e}")
            import traceback
            traceback.print_exc()


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
            # text = f'category.str.contains("{concepts.strip()}")'
            text = concepts.strip()
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
        self.tree_scroll_to_code(code)
        
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
        """[REFACTORED] 使用通用 PandasQueryEngine 执行搜索过滤"""
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()
        
        # 解析映射标签（如果有）
        if hasattr(self, 'search_map1'):
            val1 = self.search_map1.get(val1, val1)
        if hasattr(self, 'search_map2'):
            val2 = self.search_map2.get(val2, val2)

        if not val1 and not val2:
            self.status_var.set("搜索框为空")
            return

        self.query_manager.clear_hits()
        
        # 组合查询条件
        parts = []
        if val1: parts.append(f"({val1})")
        if val2: parts.append(f"({val2})")
        combined_query = " and ".join(parts)
        self._last_value = combined_query

        # 1. 更新搜索历史
        try:
            if val1:
                self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")
            if val2:
                self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")
        except Exception as ex:
            logger.exception("更新搜索历史时出错: %s", ex)

        # 2. 数据有效性检查
        if self.df_all.empty:
            self.status_var.set("当前数据为空")
            return

        # 3. 执行查询 (全面移向新引擎)
        if not query_engine:
            logger.error("PandasQueryEngine not found! Using legacy fallback.")
            try:
                df_filtered = self.df_all.query(combined_query, engine='python')
            except Exception as e:
                self.status_var.set(f"查询失败: {e}")
                return
        else:
            # 执行强大且具备 SQL 映射、向量化降级的查询
            try:
                df_filtered = query_engine.execute(self.df_all, combined_query)
            except Exception as e:
                logger.exception(f"Query Engine Critical Crash: {e} | Query: {combined_query}")
                self.status_var.set(f"❌ 引擎故障: {str(e)[:15]}")
                return

        # 4. 结果处理与 UI 更新
        if df_filtered.empty or (len(df_filtered) == len(self.df_all) and combined_query):
            if df_filtered.empty:
                self.status_var.set("❌ 无匹配结果")
                return
            else:
                # 获取引擎内部的具体错误信息
                err_info = query_engine.last_error if query_engine else "未知查询错误"
                # 记录详细日志便于调试
                logger.warning(f"Query Logic Error: {err_info} | Query: {combined_query}")
                # 精简错误提示，防止撑开状态栏
                short_err = (err_info[:25] + "...") if len(err_info) > 25 else err_info
                self.status_var.set(f"⚠️ 语法错误: {short_err}")
                return
        
        # 优化状态栏显示：匹配数/总数 | 查询缩略
        rows_all = len(self.df_all)
        rows_hit = len(df_filtered)
        # disp_query = combined_query[:30].replace('\n', ' ')
        # self.status_var.set(f"✨ 匹配:{rows_hit}/{rows_all} | Q:{disp_query}...")
        # self.status_var2.set("")
        
        # 异步刷新 Treeview 提高响应性
        self._schedule_after(10, lambda: self.refresh_tree(df_filtered, force=True))
        
        if df_filtered.empty:
            return
        self.on_test_code()
        self.auto_refresh_detail_window()
        self.update_category_result(df_filtered)
        if not hasattr(self, "_start_init_show_concept_detail_window"):
            # 已经创建过，直接显示
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
                results = check_code(self.df_all,code,self.search_var1.get())
            else:
                if onclick:
                    df_code = self.df_all.loc[self.df_all.index == code]
                    results = check_code(self.df_all,code,self.search_var1.get())
                    # logger.info(f'check_code: {results}')
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
        """清空指定搜索框内容 (1=bottom, 2=middle/ctrl, 3=history4/ctrl_new)"""
        if which == 1:
            self.search_var1.set("")
        elif which == 2:
            self.search_var2.set("")
        # elif which == 3:
        #     self.search_var4.set("")

        self.select_code = None
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.refresh_tree(self.df_all, force=True)
        resample = self.resample_combo.get()
        # self.status_var.set(f"搜索框 {which} 已清空")
        # self.status_var.set(f"Row 结果 {len(self.current_df)} 行 | resample: {resample} ")
        #清空query_manager-entry_query
        # self.query_manager.entry_query.delete(0, tk.END)

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
        # elif which == 3:
        #     history = self.search_history4
        #     combo = self.search_combo4
        #     var = self.search_var4
        #     key = "history4"

        target = entry or var.get().strip()
        if not target:
            self.status_var.set(f"搜索框 {which} 内容为空，无可删除项")
            return

        # [MODIFIED] Determine search map
        search_map = {}
        if which == 1 and hasattr(self, 'search_map1'):
            search_map = self.search_map1
        elif which == 2 and hasattr(self, 'search_map2'):
            search_map = self.search_map2

        # Find item to remove (raw or formatted)
        item_to_remove = None
        if target in history:
            item_to_remove = target
        elif search_map:
            for item in history:
                if search_map.get(item) == target:
                    item_to_remove = item
                    break
        
        if item_to_remove:
            # 从主窗口 history 移除
            history.remove(item_to_remove)
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
        from kline_monitor import KLineMonitor
        # logger.info("启动K线监控...")

        # # 仅初始化一次监控对象
        # if not hasattr(self, "kline_monitor"):
        #     self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=10)
        # else:
        #     logger.info("监控已在运行中。")
        # logger.info("启动K线监控...")
        if not hasattr(self, "kline_monitor") or not getattr(self.kline_monitor, "winfo_exists", lambda: False)():
            self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=duration_sleep_time,history3=lambda: self.search_history3,logger=logger)
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
                # self.kline_monitor.focus_force()
                self._schedule_after(500, self.kline_monitor.focus_force)
        logger.info("启动K线监控OK...")
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
            initial_monitor_list = load_monitor_list(monitor_list_file=archive_file)
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
            if not sel: return
            vals = tree.item(sel[0], "values")
            if not vals: return
            code = str(vals[0]).zfill(6)
            # 🚀 [ASYNC] 延迟 10ms 执行，确保当前行选择动作先释放主循环
            self._schedule_after(10, lambda: self.on_code_click(code))

        def on_single_click(event):
            row_id = tree.identify_row(event.y)
            if not row_id: return
            vals = tree.item(row_id, "values")
            if not vals: return
            code = str(vals[0]).zfill(6)
            # 🚀 [ASYNC] 延迟 10ms 执行
            self._schedule_after(10, lambda: self.on_code_click(code))

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

                    # 创建窗口 (取消 focus_force=True 以免干扰主流程)
                    win = self.show_concept_top10_window_simple(concept_name, code=code, auto_update=True, interval=30, focus_force=False)

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

    def open_detailed_analysis(self):
        """打开详细系统分析窗口 (支持窗口复用与自动恢复位置)
        
        该窗口独立于 open_realtime_monitor 窗口，关闭实时监控窗口时不会一并关闭。
        """
        if hasattr(self, '_detailed_analysis_win') and self._detailed_analysis_win and self._detailed_analysis_win.winfo_exists():
            self._detailed_analysis_win.lift()
            self._detailed_analysis_win.focus_force()
            return

        analysis_win = tk.Toplevel(self)  # 父窗口为主窗口，而非 log_win
        self._detailed_analysis_win = analysis_win
        analysis_win.title("Realtime System Analysis (PID: %d)" % os.getpid())
        
        # 使用 WindowMixin 加载位置
        window_id = "SystemAnalysis"
        if hasattr(self, 'load_window_position'):
            self.load_window_position(analysis_win, window_id, default_width=700, default_height=280)
        else:
            analysis_win.geometry("700x280")
        
        # Add scrollbar to text area
        atext_frame = tk.Frame(analysis_win)
        atext_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        analysis_text = tk.Text(atext_frame, font=("Consolas", 10), wrap="none")
        as_vsb = tk.Scrollbar(atext_frame, orient="vertical", command=analysis_text.yview)
        as_hsb = tk.Scrollbar(atext_frame, orient="horizontal", command=analysis_text.xview)
        analysis_text.configure(yscrollcommand=as_vsb.set, xscrollcommand=as_hsb.set)
        
        as_vsb.pack(side="right", fill="y")
        as_hsb.pack(side="bottom", fill="x")
        analysis_text.pack(side="left", fill="both", expand=True)
        
        def refresh_analysis():
            if not analysis_win.winfo_exists():
                return
            
            try:
                import psutil
                current_process = psutil.Process()
                children = current_process.children(recursive=True)
                
                report = [
                    f"=== System Resource Report ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===",
                    f"OS: {sys.platform} | Main PID: {current_process.pid}",
                    "-" * 60
                ]
                
                # Process breakdown
                procs = [(current_process, "Main UI Window")]
                for c in children:
                    try:
                        cmdline = " ".join(c.cmdline())
                        role = "Sub-Process"
                        if "resource_tracker" in cmdline: role = "Resource Tracker"
                        elif "multiprocessing.managers" in cmdline: role = "SyncManager (Proxy Server)"
                        elif "fetch_and_process" in cmdline or any("data_utils" in arg for arg in c.cmdline()): role = "Data Fetcher Process"
                        procs.append((c, role))
                    except: continue
                    
                total_rss = 0
                total_uss = 0
                total_commit = 0
                for p, role in procs:
                    try:
                        full_info = p.memory_full_info()
                        rss = full_info.rss / 1024 / 1024
                        uss = full_info.uss / 1024 / 1024  # Private Working Set
                        # 'private' in memory_full_info on Windows is the Commit Size (Total Requested)
                        commit = full_info.private / 1024 / 1024
                        
                        cpu = p.cpu_percent(interval=None)
                        p_name = p.name()
                        report.append(f"PID: {p.pid:<6} | {p_name:<10} | {uss:>6.1f} MB (RAM) | {rss:>6.1f} MB (Shared) | {cpu:>4.1f}% | {role:<20}")
                        total_rss += rss
                        total_uss += uss
                        total_commit += commit
                    except: report.append(f"PID: {p.pid:<6} | Failed to read process info")
                
                report.append("-" * 75)
                report.append(f"TASK MANAGER ESTIMATE (ACTIVE RAM): {total_uss:.1f} MB")
                report.append(f"TOTAL PHYSICAL RESIDENT (RSS):     {total_rss:.1f} MB")
                report.append(f"SYSTEM COMMIT MEMORY (REQUESTED):  {total_commit:.1f} MB")
                report.append("\nℹ️ Note: 'RAM' is primary memory. 'Requested' (~1.5GB) is virtual reserved space.")
                report.append("=" * 75)
                
                # Service Statistics
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    try:
                        svc_status = self.realtime_service.get_status()
                        report.append("=== Realtime Data Service (DataPublisher) Statistics ===")
                        report.append(f"Performance Mode: {'HIGH (4h)' if svc_status.get('high_performance_mode') else 'NORMAL (2h)'}")
                        report.append(f"Auto-Downgrade:   {'Enabled' if svc_status.get('auto_switch') else 'Disabled'}")
                        report.append(f"Service Guard:    Threshold {svc_status.get('mem_threshold_mb',0)}MB / {svc_status.get('node_threshold',0)} nodes")
                        report.append("-" * 40)
                        report.append(f"Cached Stocks:    {svc_status.get('total_stocks', 0):,}")
                        report.append(f"Total Segments:   {svc_status.get('total_nodes', 0):,}")
                        report.append(f"K-line Data:      {svc_status.get('kline_nodes', 0):,} nodes")
                        report.append(f"Emotion Data:     {svc_status.get('emotion_nodes', 0):,} nodes")
                        report.append(f"Queue/Pipe Depth: {svc_status.get('queue_depth', 0)}")
                        report.append(f"Last Loop Delay:  {svc_status.get('expected_interval', 0)}s")
                    except Exception as e:
                        report.append(f"Failed to fetch service stats: {e}")
                
                analysis_text.delete(1.0, tk.END)
                analysis_text.insert(tk.END, "\n".join(report))
            except Exception as e:
                analysis_text.insert(tk.END, f"\nFatal Error in Analysis: {e}")
            
            analysis_win.after(5000, refresh_analysis)  # Update every 5s
        
        def on_analysis_close():
            if hasattr(self, 'save_window_position'):
                try:
                    self.save_window_position(analysis_win, "SystemAnalysis")
                except Exception as e:
                    logger.error(f"Save analysis window pos error: {e}")
            self._detailed_analysis_win = None
            analysis_win.destroy()

        analysis_win.protocol("WM_DELETE_WINDOW", on_analysis_close)
        analysis_win.bind("<Escape>", lambda e: on_analysis_close())
        refresh_analysis()

    def show_ui_performance_audit(self, reset=True):
        """展示 UI 线程性能审计排行 (由监控窗口手动触发)"""
        try:
            if not hasattr(self, '_cycle_audit') or not self._cycle_audit['times']:
                logger.info("ℹ️ 尚无活跃的 UI 性能统计数据。")
                return
            
            now_t = time.time()
            elapsed = now_t - self._cycle_audit['start']
            
            # 对耗时进行排行 (手动查看时展示前 10 名)
            top_tasks = sorted(self._cycle_audit['times'].items(), key=lambda x: x[1], reverse=True)[:10]
            if not top_tasks:
                logger.info(f"ℹ️ 过去 {elapsed:.1f}s 内无 UI 任务记录。")
                return

            lines = [f"📊 [UI 线程画像回顾] 统计周期: {elapsed:.1f}s (Top 10)"]
            for name, dur in top_tasks:
                count = self._cycle_audit['counts'].get(name, 1)
                avg = dur / count
                lines.append(f"  - {name:<40} : {dur:>7.1f}ms / {count:>4d}次 (均值 {avg:>5.1f}ms)")
            
            logger.warning("\n".join(lines))
            
            if reset:
                # 重置计数器，开始新一轮画像
                self._cycle_audit = {'times': {}, 'counts': {}, 'start': now_t}
                logger.info("✅ 性能统计数据已重置。")
        except Exception as e:
            logger.error(f"❌ 性能审计展示失败: {e}")

    def open_realtime_monitor(self):
        """打开实时数据服务监控窗口 (支持窗口复用)"""
        if hasattr(self, '_realtime_monitor_win') and self._realtime_monitor_win and self._realtime_monitor_win.winfo_exists():
            self._realtime_monitor_win.lift()
            self._realtime_monitor_win.focus_force()
            return

        try:
            log_win = tk.Toplevel(self)
            self._realtime_monitor_win = log_win
            log_win.title("Realtime Data Service Monitor")
            
            # 使用 WindowMixin 加载位置
            window_id = "RealtimeData"
            if hasattr(self, 'load_window_position'):
                self.load_window_position(log_win, window_id, default_width=300, default_height=300)
            else:
                log_win.geometry("300x300")
            
            # Control frame
            btn_frame = tk.Frame(log_win)
            btn_frame.pack(fill="x", padx=5, pady=2)
            
            log_messages: deque[str] = deque(maxlen=20)  # Store last 20 log entries
            log_messages.append(f"[{time.strftime('%H:%M:%S')}] Monitor Started.")

            def add_log(msg: str):
                log_messages.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

            def toggle_pause():
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    try:
                        status = self.realtime_service.get_status()
                        current_paused = status.get('paused', False)
                        new_state = not current_paused
                        self.realtime_service.set_paused(new_state)
                        action = "Paused" if new_state else "Resumed"
                        add_log(f"Service {action} manually.")
                    except Exception as e:
                        logger.error(f"Toggle pause failed: {e}")

            def manual_reset():
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    if messagebox.askyesno("Confirm Reset", "Are you sure you want to reset the Realtime Service state?\nThis will clear all cached K-lines and emotions."):
                        try:
                            self.realtime_service.reset_state()
                            add_log("Service state RESET manually.")
                        except Exception as e:
                            logger.error(f"Manual reset failed: {e}")
                            add_log(f"Reset FAILED: {e}")

            pause_btn = tk.Button(btn_frame, text="Pause Service", command=toggle_pause, font=("Microsoft YaHei", 9))
            pause_btn.pack(side="left", padx=5)

            reset_btn = tk.Button(btn_frame, text="↺ Reset State", command=manual_reset, font=("Microsoft YaHei", 9), bg="#eeeeee")
            reset_btn.pack(side="left", padx=5)

            analysis_btn = tk.Button(btn_frame, text="📊 Detailed Analysis", command=self.open_detailed_analysis, font=("Microsoft YaHei", 9, "bold"), fg="blue")
            analysis_btn.pack(side="left", padx=5)

            # Performance controls frame
            perf_frame = tk.Frame(log_win)
            perf_frame.pack(fill="x", padx=5, pady=2)

            def toggle_perf_mode():
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    try:
                        status = self.realtime_service.get_status()
                        is_hp = status.get('high_performance_mode', True)
                        new_hp = not is_hp
                        self.realtime_service.set_high_performance(new_hp)
                        add_log(f"Mode switched to {'HighPerf' if new_hp else 'Legacy'}")
                    except Exception as e:
                        logger.error(f"Toggle perf mode failed: {e}")

            perf_btn = tk.Button(perf_frame, text="Toggle Performance", command=toggle_perf_mode, font=("Microsoft YaHei", 9))
            perf_btn.pack(side="left", padx=5)

            auto_var = tk.BooleanVar(value=True)
            def on_auto_switch():
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    self.realtime_service.set_auto_switch(auto_var.get())

            auto_chk = tk.Checkbutton(perf_frame, text=f"Auto Guard(Clip at {self.realtime_service.mem_threshold_mb}MB)", variable=auto_var, command=on_auto_switch, font=("Microsoft YaHei", 9))
            auto_chk.pack(side="left", padx=5)

            # --- [NEW] UI 性能审计按钮 ---
            audit_btn = tk.Button(perf_frame, text="🔍 UI Audit", command=lambda: self.show_ui_performance_audit(reset=True), 
                                 font=("Microsoft YaHei", 9, "bold"), fg="#d35400", bg="#fdf2e9")
            audit_btn.pack(side="left", padx=10)

            # Simple text area for status and logs
            text_area = tk.Text(log_win, font=("Consolas", 10), bg="#f0f0f0")
            text_area.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 定义关闭回调
            def on_close():
                if hasattr(self, 'save_window_position'):
                    try:
                        self.save_window_position(log_win, window_id)
                    except Exception as e:
                        logger.error(f"Error in task: {e}")
                self._realtime_monitor_win = None
                log_win.destroy()

            log_win.protocol("WM_DELETE_WINDOW", on_close)
            
            def update_status():
                if not log_win.winfo_exists():
                    return
                    
                status = {}
                if hasattr(self, 'realtime_service') and self.realtime_service:
                    try:
                        status = self.realtime_service.get_status()
                    except Exception as e:
                        status = {"error": f"IPC Communication Failed: {e}"}
                
                # Format Output
                uptime = status.get('uptime_seconds', 0)
                uptime_val = int(uptime) if isinstance(uptime, (int, float)) else 0
                uptime_str = f"{uptime_val // 3600:02d}:{(uptime_val % 3600) // 60:02d}:{uptime_val % 60:02d}"
                
                is_paused = status.get('paused', False)
                status_text = "PAUSED" if is_paused else "RUNNING"
                
                msg = f"=== Realtime Service Status ===\n"
                msg += f"Status         : {status_text}\n"
                msg += f"Pid            : {status.get('pid', 'N/A')}\n"
                msg += f"Uptime         : {uptime_str}\n"
                msg += f"Memory Usage   : {status.get('memory_usage', 'N/A')}\n"
                msg += f"CPU Usage      : {status.get('cpu_usage', 0):.1f}%\n"
                msg += f"update_count   : {status.get('update_count', 0)}\n"
                msg += f"total_rows_processed: {status.get('total_rows_processed', 0)}\n"

                msg += "-" * 35 + "\n"
                msg += f"Stocks Cached        : {status.get('klines_cached', 0)}\n"
                msg += f"high_performance_mode: {status.get('high_performance_mode', 0)}\n"
                msg += f"total_nodes          : {status.get('total_nodes', 0)}\n"
                msg += f"avg_nodes_per_stock  : {status.get('avg_nodes_per_stock', 0):.2f}\n"
                msg += f"subscribers          : {status.get('subscribers', 0)}\n"
                msg += f"target_hours         : {status.get('target_hours', 0)}\n"
                msg += f"mem_threshold        : {status.get('mem_threshold', 0)}\n"
                msg += f"cache_history_limit  : {status.get('cache_history_limit', 0)}\n"
                msg += f"last_update          : {status.get('last_update', 0)}\n"
                msg += f"server_time          : {cct.get_unixtime_to_time(status.get('server_time', 0))}\n"
                # "avg_interval_sec": int(avg_interval),
                # "expected_interval": self.expected_interval,
                # "history_coverage_minutes": int(history_sec / 60),
                # "emotions_tracked": len(self.emotion_tracker.scores),
                # "auto_switch": self.auto_switch_enabled,
                # "node_threshold": self.node_threshold,
                # "node_capacity_pct": (total_nodes / self.node_threshold * 100) if self.node_threshold else 0,
                # "max_batch_time_ms": int(self.max_batch_time * 1000),
                # "last_batch_time_ms": int(self.last_batch_time * 1000),
                # "processing_speed_row_per_sec": int(avg_speed),
                if "error" in status:
                    msg += f"\n[!] ERROR: {status['error']}\n"
                
                msg += "\n" + "="*10 + " RECENT LOGS " + "="*10 + "\n"
                msg += "\n".join(list(log_messages))
                
                text_area.delete("1.0", tk.END)
                text_area.insert("1.0", msg)
                log_win.after(5000, update_status) 
                
            update_status()
            
        except Exception as e:
            logger.error(f"Failed to open realtime monitor: {e}")

    def open_ext_data_viewer(self, auto_update=False):
        """打开/复用 55188 外部数据查看器"""
        if hasattr(self, '_ext_data_viewer_win') and self._ext_data_viewer_win and self._ext_data_viewer_win.winfo_exists():
            if not auto_update:
                self._ext_data_viewer_win.lift()
                self._ext_data_viewer_win.focus_force()
        else:
            self._ext_data_viewer_win = ExtDataViewer(self)
            
        if self.realtime_service:
            try:
                # 优先直接从服务拉取最新全量数据
                ext_status = self.realtime_service.get_55188_data()
                if ext_status and 'df' in ext_status:
                    df_ext = ext_status['df']
                    self._ext_data_viewer_win.update_data(df_ext)
                    # 同时同步给策略模块，确保一致性
                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.ext_data_55188 = df_ext
                        self.live_strategy.last_ext_update_ts = ext_status.get('last_update', 0)
                
                if auto_update:
                    logger.debug("55188 Data auto-pop/refresh triggered.")
            except Exception as e:
                logger.error(f"Update ExtDataViewer failed: {e}")

    def _check_ext_data_update(self):
        """周期性检查 55188 外部数据是否有更新，触发 UI 同步或弹窗"""
        try:
            if self.realtime_service:
                # 即使没有主行情更新，也尝试同步外部数据
                time_start_55188 = time.time()
                ext_status = self.realtime_service.get_55188_data()
                # retry = 0
                # while not ext_status and retry < 5:
                #     time.sleep(0.2)  # 等 200ms
                #     ext_status = self.realtime_service.get_55188_data()
                #     retry += 1
                if ext_status and 'df' in ext_status:
                    df_ext = ext_status['df']
                    remote_ts = ext_status.get('last_update', 0)
                    try:
                        remote_ts = int(remote_ts)  # 确保是整数
                    except (ValueError, TypeError):
                        remote_ts = 0  # 异常情况当作未更新处理
                    # 同步给策略模块
                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.ext_data_55188 = df_ext
                        self.live_strategy.last_ext_update_ts = remote_ts
                    
                    if remote_ts > self.last_ext_data_ts_local:
                        # local_time = datetime.datetime.fromtimestamp(int(ts))
                        # local_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
                        local_time = cct.get_unixtime_to_time(int(remote_ts))
                        logger.info(f"🆕 Detected 55188 data update (ts={local_time}) use time: {remote_ts-time_start_55188:.2f}. Syncing UI...")
                        self.last_ext_data_ts_local = remote_ts
                        
                        if hasattr(self, '_ext_data_viewer_win') and self._ext_data_viewer_win.winfo_exists():
                            self._ext_data_viewer_win.update_data(df_ext)
                        else:
                            # 数据更新且窗口未打开时，触发自动弹窗
                            self.open_ext_data_viewer(auto_update=True)
        except Exception as e:
            logger.debug(f"[_check_ext_data_update] error: {e}")
        finally:
            self._schedule_after(duration_sleep_time*1000, self._check_ext_data_update)

    def open_archive_loader(self):
        """打开存档选择窗口"""
        win = tk.Toplevel(self)
        win.title("加载历史监控数据")
        win.geometry("400x300")
        window_id = "历史监控数据"   # <<< 每个窗口一个唯一 ID
        # self.get_centered_window_position(win, window_id)
        self.load_window_position(win, window_id, default_width=400, default_height=300)
        files = list_archives(archive_dir=ARCHIVE_DIR,prefix='monitor_category_list')
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

    # ----------------- 状态栏 ----------------- #
    def update_status(self):
        cnt = len(self.current_df)
        # blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        # search = self.search_entry.get()
        search = self.search_var1.get()
         # 对查询语句进行脱敏预处理 (剥离注释、赋值等)
        eff_query = query_engine._preprocess_query(search) if query_engine else search
        disp_query = eff_query[:120].replace('\n', ' ').strip()
        self.status_var.set(f"Rows: {cnt} | blkname: {self.blkname} | resample: {resample} | st: {self.st_key_sort} | search: {disp_query}")


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
                self.refresh_tree(df, force=True)
                idx =file_path.find('monitor')
                status_txt = file_path[idx:]
                # logger.info(f'status_txt:{status_txt}')
                self.status_var2.set(f"已加载数据: {status_txt}")
            except Exception as e:
                logger.error(f"加载 CSV 失败: {e}")


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
            logger.debug(f'win: {win} main_win: {main_win} type: {type(main_win)}')

            if is_window_covered_pg(win, main_win):
                # 若被最小化，恢复
                logger.debug(f'v.get("code"): {v.get("code")}')
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
                                    
# --- DPI and Config methods moved to Mixins ---
# --- Duplicate window methods removed ---

# KLineMonitor class moved to kline_monitor.py

def test_single_thread(single=True, test_strategy=False, resample=None,log_level=LoggerFactory.DEBUG):
    """
    单线程测试函数。
    :param single: 是否单次执行（默认 True，执行一次后返回）
    :param test_strategy: 是否同时测试 StockLiveStrategy
    :param resample: 指定回测/测试的周期 (e.g., 'd', 'w', 'm')，如果不指定则使用全局默认值
    """
    import queue
    # 用普通 dict 代替 manager.dict()
    global marketInit,resampleInit
    shared_dict = {}
    shared_dict["resample"] = resample if resample is not None else resampleInit
    shared_dict["market"] = marketInit

    # 用 Python 内置 queue 代替 multiprocessing.Queue
    q = queue.Queue()

    # 用一个简单的对象/布尔值模拟 flag
    class Flag:
        def __init__(self, value=True):
            self.value = value
    flag = Flag(True)   # 或者 flag = Flag(False) 看你的测试需求
    log_level = mp.Value('i', log_level)  # 'i' 表示整数
    detect_calc_support = mp.Value('b', False)  # 'i' 表示整数
    # 直接单线程调用
    df = fetch_and_process(shared_dict, q, blkname="boll", flag=flag ,log_level=log_level,detect_calc_support_var=detect_calc_support,single=single)
    
    if test_strategy and df is not None and not df.empty:
        print(f"===== 测试 StockLiveStrategy =====")
        print(f"DataFrame shape: {df.shape}")
        
        # 创建模拟 master 对象
        class MockMaster:
            def __init__(self):
                self.df_all = df
                self.voice_var = type('obj', (object,), {'get': lambda self: False})()
                self.realtime_service = None
            
            def after(self, ms, func, *args):
                """模拟 TK after 方法 - 直接执行"""
                func(*args)
        
        mock_master = MockMaster()
        
        try:
            # 使用与 _init_live_strategy 相同的参数
            strategy = StockLiveStrategy(
                mock_master,
                alert_cooldown=alert_cooldown,
                voice_enabled=False,
                realtime_service=None
            )
            print(f"✅ StockLiveStrategy 初始化成功")
            
            # 测试 _check_strategies
            print(f"测试 _check_strategies...")
            strategy._check_strategies(df, resample='d')
            print(f"✅ _check_strategies 执行成功")
            
        except Exception as e:
            print(f"❌ StockLiveStrategy 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    return df

def test_main_process_params():
    """
    使用与主进程完全相同的参数进行单线程测试。
    模拟 _start_process 中的调用方式。
    """
    import queue
    global marketInit, marketblk, duration_sleep_time, resampleInit
    
    # 获取全局变量或使用默认值
    try:
        _log_level = log_level
    except NameError:
        _log_level = LoggerFactory.DEBUG
    
    try:
        _detect_calc_support = detect_calc_support
    except NameError:
        _detect_calc_support = False
    
    print("===== 测试主进程参数 =====")
    print(f"marketInit: {marketInit}")
    print(f"marketblk: {marketblk}")
    print(f"duration_sleep_time: {duration_sleep_time}")
    print(f"log_level: {_log_level}")
    print(f"detect_calc_support: {_detect_calc_support}")
    
    # 模拟 self.global_dict（与主进程一致）
    shared_dict = {}
    shared_dict["resample"] = resampleInit
    shared_dict["market"] = marketInit
    
    # 模拟 self.queue
    q = queue.Queue()
    
    # 模拟 self.blkname
    blkname = "boll"
    
    # 模拟 self.refresh_flag, self.log_level, self.detect_calc_support
    # 使用 mp.Value 与主进程一致
    refresh_flag = mp.Value('b', True)
    log_level_var = mp.Value('i', _log_level)
    detect_calc_support_var = mp.Value('b', _detect_calc_support)
    
    print(f"\n调用 fetch_and_process (与主进程参数一致)...")
    
    try:
        # 与主进程调用方式完全一致
        df = fetch_and_process(
            shared_dict, 
            q, 
            blkname, 
            refresh_flag, 
            log_level_var, 
            detect_calc_support_var, 
            marketInit, 
            marketblk, 
            duration_sleep_time,
            status_callback=tip_var_status_flag,  # 与主进程 kwargs 一致
            single=True  # 单次执行，不循环
        )
        
        if df is not None and not df.empty:
            print(f"✅ fetch_and_process 成功, DataFrame shape: {df.shape}")
            return df
        else:
            print(f"⚠️ fetch_and_process 返回空 DataFrame")
            return None
            
    except Exception as e:
        print(f"❌ fetch_and_process 失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# 常用命令示例列表
COMMON_COMMANDS = [
    "tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df('300')",
    "tdd.get_tdx_exp_low_or_high_power('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df_Sina('sina_data')",
    "tdd.h5a.check_tdx_all_df_Sina('get_sina_all_ratio')",
    "write_to_hdf()",
    "write_market_index_to_df()",
    "test_opt(top_all,resample='d',code='002151')"
]

# 格式化帮助信息，换行+缩进
help_text = "传递 Python 命令字符串执行，例如:\n" + "\n".join([f"    {cmd}" for cmd in COMMON_COMMANDS])
def parse_args():
    parser = argparse.ArgumentParser(description="Monitor Init Script")

    parser.add_argument(
        "-log",
        type=str,
        default=str(cct.loglevel).upper(),
        help="日志等级，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )

    # 布尔开关参数
    parser.add_argument(
        "-write_to_hdf",
        action="store_true",
        help="执行 write_to_hdf() 并退出"
    )
    # TDX开关参数
    parser.add_argument(
        "-write_today_tdx",
        action="store_true",
        help="执行 write_today_tdx() 并退出"
    )
    # 布尔开关参数
    parser.add_argument(
        "-test_single",
        action="store_true",
        help="执行 test_single_thread() 并退出"
    )
    # 新增测试开关
    parser.add_argument(
        "-test",
        action="store_true",
        help="执行测试数据流程"
    )

    # 新增 K线重采样周期启动参数
    parser.add_argument(
        "-resample",
        type=str,
        choices=['2d', '3d', 'w', 'm', 'd'],
        default=None,
        help="K线重采样周期，可选：2d, 3d, w, m, d (默认从配置文件读取)"
    )

    parser.add_argument(
        "-cmd",
        type=str,
        nargs='?',          # 表示参数可选
        const=COMMON_COMMANDS[0],  # 默认无值时使用第一个常用命令  # 当没有值时使用 const
        default=None,       # 如果完全没传 --cmd, default 才会生效
        help=help_text
        # help="传递 Python 命令字符串执行，例如:\n" + "\n".join(COMMON_COMMANDS)
        # help="传递 Python 命令字符串执行，例如: tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')"
    )
    
    # 数据库修复参数
    # 数据库修复参数
    parser.add_argument(
        "-repair-db",
        "--repair-db",
        dest="repair_db",
        nargs='?',
        const='signal_strategy.db',  # 不带参数时使用默认值
        default=None,  # 完全不使用该参数时为 None
        help="修复指定的数据库文件。默认修复 signal_strategy.db。用法: -repair-db [数据库路径]"
    )
    
    # 清理非交易时段信号参数
    parser.add_argument(
        "-cleanup-signals",
        "--cleanup-signals",
        dest="cleanup_signals",
        nargs='?',
        const='signal_strategy.db',  # 不带参数时默认清理信号数据库
        default=None,  # 完全不使用该参数时为 None
        help="清理数据库中非交易时段的信号记录。默认清理 signal_strategy.db。使用 'all' 清理所有数据库。用法: -cleanup-signals [signal_strategy.db|trading_signals.db|all]"
    )
    
    # 数据库重复记录清理 (一股一仓排重)
    parser.add_argument(
        "-dedup",
        "--dedup",
        action="store_true",
        help="清理 follow_queue 数据库中的冗余重复活跃记录 (执行一次性排重)"
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
    except Exception as e:
        logger.error(f"获取 {code} 数据失败: {e}", exc_info=True)

def write_today_tdx():
    global write_all_day_date
    today = cct.get_today('')
    if write_all_day_date == today:
        logger.info(f'Write_market_all_day_mp 已经完成')
        return
    try:
        if  cct.get_trade_date_status():
            logger.info(f'start Write_market_all_day_mp OK')
            tdd.Write_market_all_day_mp('all')
            logger.info(f'run Write_market_all_day_mp OK')
            CFG = cct.GlobalConfig(conf_ini)
            # cct.GlobalConfig(conf_ini, write_all_day_date=20251205)
            CFG.set_and_save("general", "write_all_day_date", today)
        else:
            logger.info(f"today: {today} is trade_date :{cct.get_trade_date_status()} not to Write_market_all_day_mp")
    finally:
        # self._task_running = False
        pass
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



LOCK_FILE = cct.get_ramdisk_path("stock_app.lock")

def ensure_single_instance_fileLock():
    import msvcrt
    import sys
    import os
    global lock_fp
    lock_fp = open(LOCK_FILE, "w")

    try:
        msvcrt.locking(lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("Already running")
        sys.exit(0)

def ensure_single_instance():
    import win32event, win32api, winerror

    mutex = win32event.CreateMutex(None, False, "Global\\StockMonitorAppMutex")

    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None

    return mutex

# ------------------ 主程序入口 ------------------ #
if __name__ == "__main__":
    # 测试未捕获异常
    # 直接触发
    # 1/0
    # 仅在 Windows 上设置启动方法，因为 Unix/Linux 默认是 'fork'，更稳定

    import multiprocessing as mp
    import os

    if sys.platform.startswith('win'):
        mp.freeze_support() # Windows 必需
        # 1️⃣ 必须最先
        # 2️⃣ set_start_method 只允许执行一次
        try:
            mp.set_start_method('spawn', force=True)
        except RuntimeError:
            pass
        # 'spawn' 是默认的，但显式设置有助于确保一致性。
        # 另一种方法是尝试使用 'forkserver' (如果可用)
        # mp.freeze_support()  # <-- 必须

    if mp.current_process().name != "MainProcess" and mp.parent_process() is not None:
        # 子进程，什么都不做
        print(f'mp.current_process().name: {mp.current_process().name} != MainProcess')
        print("PID:", os.getpid(), "Process:", mp.current_process().name)
        sys.exit(0)
    else:
        # # 3️⃣ 单例锁（必须最早）
        # mutex = ensure_single_instance()
        # if mutex is None:
        #     print(f"Already running:{mutex}")
        #     sys.exit(0)

        # # 3️⃣ 单例(文件锁）
        # ensure_single_instance_fileLock()

        print(f'mp.current_process().name: {mp.current_process().name} == MainProcess')
        print("PID:", os.getpid(), "Process:", mp.current_process().name)



    args = parse_args()  # 解析命令行参数

    # ✅ 启动使用命令行参数覆盖默认初始化 (if provided)
    if getattr(args, 'resample', None):
        resampleInit = args.resample
        logger.info(f"🚀 [INIT] 使用命令行参数覆盖 resample 周期: {resampleInit}")

    _exit_ctrl_c_count = 0
    _exit_ctrl_c_time = 0
    # ✅ 命令行触发数据库修复 - 必须在最开始检查,避免初始化其他组件
    if args.repair_db is not None:
        from db_repair_tool import DatabaseRepairTool
        
        # 如果是相对路径,转换为绝对路径
        target_db = args.repair_db
        if not os.path.isabs(target_db):
            target_db = os.path.join(BASE_DIR, target_db)
        
        print(f"开始修复数据库: {target_db}")
        tool = DatabaseRepairTool(target_db)
        success = tool.run()
        
        if success:
            print("数据库修复完成!")
            sys.exit(0)
        else:
            print("数据库修复失败!")
            sys.exit(1)
    
    # ✅ 命令行触发清理非交易时段信号
    if args.cleanup_signals is not None:
        from cleanup_non_trading_signals import (
            clean_live_signal_history,
            clean_signal_message,
            backup_database
        )
        
        # 确定要处理的数据库列表
        db_files = []
        
        if args.cleanup_signals.lower() == 'all':
            db_files = ['trading_signals.db', 'signal_strategy.db']
            print("清理所有数据库中的非交易时段信号...")
        elif args.cleanup_signals in ['signal_strategy.db', 'trading_signals.db']:
            db_files = [args.cleanup_signals]
            print(f"清理 {args.cleanup_signals} 中的非交易时段信号...")
        else:
            # 如果是相对路径,转换为绝对路径
            target_db = args.cleanup_signals
            if not os.path.isabs(target_db):
                target_db = os.path.join(BASE_DIR, target_db)
            db_files = [target_db]
            print(f"清理 {target_db} 中的非交易时段信号...")
        
        # 处理每个数据库
        total_deleted = 0
        
        for db_file in db_files:
            # 确定数据库绝对路径
            if not os.path.isabs(db_file):
                db_path = os.path.join(BASE_DIR, db_file)
            else:
                db_path = db_file
            
            if not os.path.exists(db_path):
                print(f"⚠️ 数据库文件不存在,跳过: {db_file}")
                continue
            
            print(f"\n{'='*60}")
            print(f"开始处理数据库: {db_file}")
            print(f"{'='*60}")
            
            # 备份数据库
            try:
                backup_path = backup_database(str(db_path))
                print(f"✅ 数据库已备份至: {backup_path}")
            except Exception as e:
                print(f"❌ 备份失败: {e}")
                print("是否继续清理? (y/n)")
                response = input().strip().lower()
                if response != 'y':
                    continue
            
            # 清理 live_signal_history 表 (在 trading_signals.db 中)
            if 'trading_signals' in db_file:
                try:
                    total, deleted = clean_live_signal_history(str(db_path), dry_run=False)
                    total_deleted += deleted
                    print(f"✅ live_signal_history: 总记录 {total}, 删除 {deleted} 条非交易时段记录")
                except Exception as e:
                    print(f"❌ 清理 live_signal_history 失败: {e}")
            
            # 清理 signal_message 表 (在 signal_strategy.db 中)
            if 'signal_strategy' in db_file:
                try:
                    total, deleted = clean_signal_message(str(db_path), dry_run=False)
                    total_deleted += deleted
                    print(f"✅ signal_message: 总记录 {total}, 删除 {deleted} 条非交易时段记录")
                except Exception as e:
                    print(f"❌ 清理 signal_message 失败: {e}")
        
        # 总结
        print(f"\n{'='*60}")
        print(f"✅ [清理完成] 共删除 {total_deleted} 条非交易时段记录")
        print(f"{'='*60}")
        sys.exit(0)
        
    # ✅ 命令行触发数据库去重清理 (一股一仓排重)
    if getattr(args, 'dedup', False):
        from trading_hub import get_trading_hub
        print("\n正在启动数据库排重清理 (Deduplication Cleanup)...")
        hub = get_trading_hub()
        res = hub.cleanup_duplicates()
        if res['found_dupes'] > 0:
            print(f"✅ 处理完成: 发现 {res['found_dupes']} 只重复代码，清理了 {res['cancelled_count']} 条冗余记录。")
        else:
            print("✅ 检查完成: 数据库中不存在活跃的重复记录。")
        sys.exit(0)

    # 🚀 [AUTO] 启动时自动执行轻量级排重 (确保系统健壮性)
    try:
        from trading_hub import get_trading_hub
        hub = get_trading_hub()
        hub.cleanup_duplicates()
    except Exception as e:
        logger.error(f"Auto deduplication failed on startup: {e}")

    
    # log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.ERROR)
    log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.INFO)
    # log_level = LoggerFactory.DEBUG
    # 直接用自定义的 init_logging，传入日志等级
    # logger = init_logging(log_file='instock_tk.log', redirect_print=False, level=log_level)
    logger.setLevel(log_level)
    logger.info("程序启动…")    

    # ✅ 命令行触发 write_to_hdf
    if args.test:
        test_get_tdx()
        sys.exit(0)

    # 执行传入命令
    if args.cmd:
        if len(args.cmd) > 5:
            try:
                from data_utils import *
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
        top_all = test_single_thread(single=True)
        queries = [
            {
                "name": "main_rule",
                "expr": "(vol > 1e8 or volume > 2) and (open <= nlow or (open > lasth1d and low >= lastp1d)) "
                        "and close > lastp1d and a1_v > 10 and percent > 3 and close > nclose and win > 2"
            }
        ]
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
                now = time.time()
                if now - _exit_ctrl_c_time > 3:
                    _exit_ctrl_c_count = 0
                    
                _exit_ctrl_c_count += 1
                _exit_ctrl_c_time = now

                if _exit_ctrl_c_count >= 3:
                    print("\n检测到连续 3 次 Ctrl+C，正在强制退出程序...")
                    os._exit(0)
                else:
                    print(f"\nKeyboardInterrupt ({_exit_ctrl_c_count}/3), 输入 'quit' 退出")
            except EOFError:
                print("\nEOF, 退出调试模式")
                break

        sys.exit(0)        
    # ✅ 命令行触发 write_to_hdf
    if args.write_to_hdf:
        write_to_hdf()
        sys.exit(0)
    if args.write_today_tdx:
        write_today_tdx()
        sys.exit(0)
    if args.test_single:
        logger.info(f'b fetch_and_process')
        test_single_thread()
        sys.exit(0)
    
    app = StockMonitorApp()
    
    # [🚀 增强] 初始化全局退出计数器，用于 KeyboardInterrupt 暴力退出控制
    _exit_ctrl_c_count = 0
    _exit_ctrl_c_time = 0

    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)

    # ✅ 注册 Windows 原生控制台处理器，确保在弹窗阻塞时也能响应 Ctrl+C
    if not cct.isMac():
        import win32api
        win32api.SetConsoleCtrlHandler(app._native_ctrl_handler, True)

    try:
        app.mainloop()
    except KeyboardInterrupt:
        # 额外防护：Ctrl+C 在某些情况下仍可能抛异常
        now = time.time()
        if now - _exit_ctrl_c_time > 3:
            _exit_ctrl_c_count = 0
            
        _exit_ctrl_c_count += 1
        _exit_ctrl_c_time = now

        if _exit_ctrl_c_count >= 3:
            print("\n检测到连续 3 次 Ctrl+C，正在强制退出程序...")
            os._exit(0)
        else:
            app.ask_exit()
            _exit_ctrl_c_count = 0

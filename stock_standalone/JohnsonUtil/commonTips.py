# -*- encoding: utf-8 -*-

import argparse
import datetime
import os
import platform
import re
import sys
import gc
sys.path.append("..")
import time
import random
# from compiler.ast import flatten  #py2
import collections.abc              #py3

from multiprocessing.pool import ThreadPool
from multiprocessing import cpu_count

import pandas as pd
# import trollius as asyncio
# from trollius.coroutines import From
import asyncio
import argparse
from typing import Optional, List, Dict, Union, Any, Tuple, Callable


from JohnsonUtil.prettytable import PrettyTable
from JohnsonUtil import johnson_cons as ct
# from JohnsonUtil import inStockDb as inDb

import traceback
import socket
from configobj import ConfigObj
import importlib
from JohnsonUtil import LoggerFactory
log = LoggerFactory.getLogger()
from tqdm import tqdm
from tqdm.contrib.concurrent import process_map

import numpy as np
import subprocess
import a_trade_calendar
# from py_mini_racer import py_mini_racer
from textwrap import fill
from JohnsonUtil.prettytable import ALL as ALL
# from functools import partial
import functools
from multiprocessing import Pool

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib.request import urlopen, Request

import urllib.error
import requests
requests.adapters.DEFAULT_RETRIES = 0
# sys.path.append("..")
# sys.path.append("..")
# print sys.path
# from JSONData import tdx_data_Day as tdd
global initGlobalValue
global last_trade_date,is_trade_date_today

import ctypes
import shutil
from collections import defaultdict

_TIMING_STATS = defaultdict(list)

class timed_ctx:
    def __init__(self, name, warn_ms=None, log_debug=True,logger=log):
        """
        :param name: 统计名称
        :param warn_ms: 超过该时间则 warning（None 表示不报警）
        :param log_debug: 是否输出 debug 日志
        """
        self.name = name
        self.warn_ms = warn_ms
        self.log_debug = log_debug
        self.logger = logger or log   # ✅ 关键修复点

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        cost_ms = (time.perf_counter() - self.start) * 1000

        # 1️⃣ 汇总统计（一定保留）
        _TIMING_STATS[self.name].append(cost_ms)

        # 2️⃣ 实时日志（可控）
        if self.warn_ms is not None and cost_ms >= self.warn_ms:
            self.logger.warning(f"[SLOW] {self.name} cost={cost_ms:.2f} ms")
        elif self.log_debug:
            self.logger.debug(f"[TIME] {self.name} cost={cost_ms:.2f} ms")

#使用方式:1普通监控（不刷日志）
# with timed_ctx("combine_dataFrame"):
#     df = combine_dataFrame(df1, df2)
# 2:重点怀疑对象（慢就报警）
# with timed_ctx("TDX last df load", warn_ms=1000):
#     df_last = get_append_lastp_to_df(...)
# 3:fetch_and_process 末尾输出汇总
def dump_timing_stats(top=10,logger=log):
    items = sorted(
        ((k, sum(v), len(v)) for k, v in _TIMING_STATS.items()),
        key=lambda x: x[1],
        reverse=True
    )

    logger.info("==== Timing Summary ====")
    for name, total_ms, cnt in items[:top]:
        logger.info(
            f"{name:<30} total={total_ms/1000:.2f}s count={cnt} avg={total_ms/cnt:.1f}ms"
        )

#使用方式2:
# @timed_block("fetch_and_process", warn_ms=1000)
# def fetch_and_process(...):

def print_timing_summary(top_n=5, unit="ms"):
    """
    汇总 _TIMING_STATS 并打印 top_n 慢函数
    :param top_n: 显示前 top_n 个慢函数
    :param unit: 时间单位 'ms' 或 's'
    """
    summary = []

    # 遍历所有统计项
    for name, times in _TIMING_STATS.items():
        if not times:
            continue
        arr = np.array(times)
        if unit == "ms":
            arr_display = arr
        else:  # 秒
            arr_display = arr / 1000.0

        summary.append({
            "name": name,
            "count": len(times),
            "mean": np.mean(arr_display),
            "max": np.max(arr_display),
            "p95": np.percentile(arr_display, 95)
        })

    # 按平均耗时排序
    summary_sorted = sorted(summary, key=lambda x: x["mean"], reverse=True)

    print(f"\n{'Function':40} {'count':>6} {'mean':>10} {'max':>10} {'p95':>10}")
    print("-"*80)
    for item in summary_sorted[:top_n]:
        print(f"{item['name'][:40]:40} {item['count']:6d} "
              f"{item['mean']:10.2f} {item['max']:10.2f} {item['p95']:10.2f}")

# 使用示例
# 在程序任意位置调用
# print_timing_summary(top_n=5, unit="ms")
# --- Win32 API 用于获取 EXE 原始路径 (仅限 Windows) ---
def _get_win32_exe_path() -> str:
    """
    使用 Win32 API 获取当前进程的主模块路径。
    这在 Nuitka/PyInstaller 的 Onefile 模式下能可靠地返回原始 EXE 路径。
    """
    # 假设是 32767 字符的路径长度是足够的
    MAX_PATH_LENGTH: int = 32767 
    buffer = ctypes.create_unicode_buffer(MAX_PATH_LENGTH)
    
    # 调用 GetModuleFileNameW(HMODULE hModule, LPWSTR lpFilename, DWORD nSize)
    # 传递 NULL 作为 hModule 获取当前进程的可执行文件路径
    ctypes.windll.kernel32.GetModuleFileNameW(
        None, buffer, MAX_PATH_LENGTH
    )
    return os.path.dirname(os.path.abspath(buffer.value))


def get_base_path() -> str:
    """
    获取程序基准路径。在 Windows 打包环境 (Nuitka/PyInstaller) 中，
    使用 Win32 API 优先获取真实的 EXE 目录。
    """
    
    # 检查是否为 Python 解释器运行
    is_interpreter: bool = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
    # 1. 普通 Python 脚本模式
    if is_interpreter and not getattr(sys, "frozen", False):
        # 只有当它是 python.exe 运行 且 没有 frozen 标志时，才进入脚本模式
        try:
            # 此时 __file__ 是可靠的
            path: str = os.path.dirname(os.path.abspath(__file__))
            log.info(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
            return path
        except NameError:
             pass # 忽略交互模式
    
    # 2. Windows 打包模式 (Nuitka/PyInstaller EXE 模式)
    # 只要不是解释器运行，或者 sys.frozen 被设置，我们就认为是打包模式
    if sys.platform.startswith('win'):
        try:
            # 无论是否 Onefile，Win32 API 都会返回真实 EXE 路径
            real_path: str = _get_win32_exe_path()
            
            # 核心：确保我们返回的是 EXE 的真实目录
            if real_path != os.path.dirname(os.path.abspath(sys.executable)):
                 # 这是一个强烈信号：sys.executable 被欺骗了 (例如 Nuitka Onefile 启动器)，
                 # 或者程序被从其他地方调用，我们信任 Win32 API。
                 log.info(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
                 return real_path
            
            # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
            if not is_interpreter:
                 log.info(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
                 return real_path

        except Exception:
            pass 

    # 3. 最终回退（适用于所有打包模式，包括 Linux/macOS）
    if getattr(sys, "frozen", False) or not is_interpreter:
        path = os.path.dirname(os.path.abspath(sys.executable))
        log.info(f"[DEBUG] Path Mode: Final Fallback. Path: {path}")
        return path

    # 4. 极端脚本回退
    log.info(f"[DEBUG] Path Mode: Final Script Fallback.")
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def get_base_path_simple() -> str:
    """获取程序运行目录，兼容 PyInstaller / Nuitka / 普通脚本 (简化版)"""
    if getattr(sys, "frozen", False):
        # PyInstaller
        if hasattr(sys, "_MEIPASS"):
            return os.path.dirname(sys.executable)
        else:
            # Nuitka 或其他冻结工具
            return os.path.dirname(sys.executable)
    else:
        # 普通脚本
        return os.path.dirname(os.path.abspath(__file__))



def timed_block(name=None, warn_ms=500, log_level=LoggerFactory.INFO,logger=log):
    """
    自动耗时统计装饰器
    :param name: 模块名称（默认函数名）
    :param warn_ms: 超过多少毫秒报警
    """
    def decorator(func):
        tag = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                cost_ms = (time.perf_counter() - start) * 1000
                if cost_ms >= warn_ms:
                    logger.warning(f"[SLOW] {tag} cost={cost_ms:.2f} ms")
                else:
                    logger.log(log_level, f"[TIME] {tag} cost={cost_ms:.2f} ms")
        return wrapper
    return decorator

#使用方式:
# @timed_block("fetch_and_process", warn_ms=1000)
# def fetch_and_process(...):

#mode 2 统一是否 py and nui
# ----------------------------
# 基础路径获取
# ----------------------------
# def get_base_path():
#     """获取程序运行目录，兼容 PyInstaller / Nuitka / 普通脚本"""
#     if getattr(sys, "frozen", False):
#         return os.path.dirname(sys.executable)
#     else:
#         return os.path.dirname(os.path.abspath(__file__))


# # ----------------------------
# # 全局资源释放函数
# # ----------------------------
# def release_resource(rel_path, out_dir=None):
#     """
#     将内置资源释放到运行目录指定文件夹
#     rel_path: 内置资源相对路径（如 'JohnsonUtil/global.ini'）
#     out_dir: 释放目标目录，默认 EXE 所在目录
#     """
#     if out_dir is None:
#         out_dir = get_base_path()

#     target_path = os.path.join(out_dir, os.path.basename(rel_path))

#     # 文件已存在直接返回
#     if os.path.exists(target_path):
#         return target_path

#     # 获取源文件路径
#     if getattr(sys, "frozen", False):
#         src_base = getattr(sys, "_MEIPASS", None)
#         if src_base:
#             src_path = os.path.join(src_base, rel_path)
#         else:
#             src_path = os.path.join(out_dir, rel_path)
#     else:
#         src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)

#     if not os.path.exists(src_path):
#         log.error(f"资源缺失: {src_path}")
#         return None

#     try:
#         shutil.copy(src_path, target_path)
#         log.info(f"资源释放成功: {target_path}")
#         return target_path
#     except Exception as e:
#         log.exception(f"资源释放失败: {e}")
#         return None


# # ----------------------------
# # 统一配置资源管理
# # ----------------------------
# RESOURCE_REGISTRY = {
#     # '资源名': '相对路径'
#     'global_ini': 'JohnsonUtil/global.ini',
#     'stock_codes': 'JohnsonUtil/JSONData/stock_codes.conf',
#     'count_ini': 'JohnsonUtil/JSONData/count.ini',
#     'wencai_excel': 'JohnsonUtil/wencai/同花顺板块行业.xlsx',
#     # 可继续添加新资源
# }

# def get_resource(name):
#     """
#     获取资源文件路径，自动释放到运行目录
#     """
#     rel_path = RESOURCE_REGISTRY.get(name)
#     if not rel_path:
#         log.error(f"资源未注册: {name}")
#         return None
#     return release_resource(rel_path)
# global_ini_path = get_resource('global_ini')
# stock_codes_path = get_resource('stock_codes')
# wencai_path = get_resource('wencai_excel')


#mode 1 no test py and nui
# def get_resource_file(rel_path, out_name=None, base_dir=None):
#     """
#     从内置资源释放文件到 EXE 同目录或 base_dir

#     rel_path:   内置资源相对路径
#     out_name:   释放目标文件名
#     base_dir:   释放目录，默认 EXE 所在目录
#     """
#     if base_dir is None:
#         base_dir = get_base_path()

#     if out_name is None:
#         out_name = os.path.basename(rel_path)

#     target_path = os.path.join(base_dir, out_name)

#     # 文件已存在
#     if os.path.exists(target_path):
#         return target_path

#     # 确定源文件路径
#     if getattr(sys, "frozen", False):
#         # PyInstaller MEIPASS
#         src = getattr(sys, "_MEIPASS", None)
#         if src:
#             src = os.path.join(src, rel_path)
#         else:
#             # Nuitka: 直接从相对目录获取
#             src = os.path.join(base_dir, rel_path)
#     else:
#         # 普通脚本
#         src = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)

#     if not os.path.exists(src):
#         log.error(f"内置资源缺失: {src}")
#         return None

#     try:
#         shutil.copy(src, target_path)
#         log.info(f"释放资源: {target_path}")
#         return target_path
#     except Exception as e:
#         log.exception(f"释放资源失败: {e}")
#         return None


# def get_conf_path(fname, rel_path=None, base_dir=None):
#     """
#     获取配置文件路径，优先使用运行目录已有文件，否则释放内置资源
#     """
#     if base_dir is None:
#         base_dir = get_base_path()

#     target_path = os.path.join(base_dir, fname)

#     if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
#         log.info(f"使用本地配置: {target_path}")
#         return target_path

#     if rel_path is None:
#         rel_path = os.path.join("JohnsonUtil", fname)

#     cfg_file = get_resource_file(rel_path=rel_path, out_name=fname, base_dir=base_dir)

#     if cfg_file and os.path.exists(cfg_file) and os.path.getsize(cfg_file) > 0:
#         log.info(f"使用内置释放配置: {cfg_file}")
#         return cfg_file

#     log.error(f"获取配置文件失败: {fname}")
#     return None

def get_resource_file(rel_path: str, out_name: Optional[str] = None, BASE_DIR: Optional[str] = None, spec: Any = None) -> Optional[str]:
    """
    从 PyInstaller 内置资源释放文件到 EXE 同目录

    rel_path:   打包资源的相对路径
    out_name:   释放目标文件名
    """

    if BASE_DIR is None:
        BASE_DIR = get_base_path()

    if out_name is None:
        out_name = os.path.basename(rel_path)

    target_path = os.path.join(BASE_DIR, out_name)
    log.info(f"target_path配置文件: {target_path}")
    
    # 已存在 → 直接返回
    if os.path.exists(target_path):
        return target_path

    # 从 MEIPASS 复制
    base = getattr(sys, "_MEIPASS", ".") if getattr(sys, "frozen", False) else os.path.abspath(".")
    src = os.path.join(base, rel_path)

    if not os.path.exists(src):
        src = os.path.join(BASE_DIR, rel_path)
        if os.path.exists(src):
            log.info(f"BASE_DIR/rel_path资源: {src}")
            return src
        elif rel_path.find('JohnsonUtil') >= 0:
            src = os.path.join(get_base_path(), rel_path.replace('JohnsonUtil/',''))
            if os.path.exists(src):
                return src
        log.error(f"内置资源缺失: {src}")
        return None

    try:
        shutil.copy(src, target_path)
        log.info(f"释放配置文件: {target_path}")
        return target_path
    except Exception as e:
        log.exception(f"释放资源失败: {e}")
        return None


# --------------------------------------
# STOCK_CODE_PATH 专用逻辑
# --------------------------------------
BASE_DIR = get_base_path()

def get_conf_path(fname: str, rel_path: Optional[str] = None) -> Optional[str]:
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
            log.info(f"使用本地配置: {default_path}")
            return default_path
        else:
            log.warning("配置文件存在但为空，将尝试重新释放")

    if rel_path is None:
        rel_path = f"JohnsonUtil{os.sep}{fname}"
    # --- 2. 释放默认资源 ---
    cfg_file = get_resource_file(
        rel_path=rel_path,
        out_name=fname,
        BASE_DIR=BASE_DIR
    )

    # --- 3. 校验释放结果 ---
    if not cfg_file:
        log.error(f"获取 {fname} 失败（释放阶段）")
        return None

    if not os.path.exists(cfg_file):
        log.error(f"释放后文件仍不存在: {cfg_file}")
        return None

    if os.path.getsize(cfg_file) == 0:
        log.error(f"配置文件为空: {cfg_file}")
        return None

    log.info(f"使用内置释放配置: {cfg_file}")
    return cfg_file

def get_resource_file1(rel_path, out_name=None):
    """
    将打包资源从 _MEIPASS 释放到 EXE 目录
    优先读取 EXE 外部版本
    """

    # exe 运行目录
    exe_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath("."))

    if out_name is None:
        out_name = os.path.basename(rel_path)

    target = os.path.join(exe_dir, out_name)

    # 已存在 ⇒ 直接用（支持用户更新）
    if os.path.exists(target):
        return target

    # 不存在 ⇒ 从 _MEIPASS 复制
    base = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.abspath(".")
    bundled = os.path.join(base, rel_path)

    if not os.path.exists(bundled):
        raise RuntimeError(f"内置资源缺失: {bundled}")

    shutil.copy(bundled, target)

    return target


_global_dict = {}
# initGlobalValue = 0
# clean_terminal = ["Python Launcher", 'Johnson — -bash', 'Johnson — python']
# writecode = "cct.write_to_blocknew(block_path, dd.index.tolist())"
# perdall = "df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(ct.compute_lastdays))]][:1]"
# perdallc = "df[df.columns[(df.columns >= 'perc1d') & (df.columns <= 'perc%sd'%(ct.compute_lastdays))]][:1]"
# perdalla = "df[df.columns[ ((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(ct.compute_lastdays))) | ((df.columns >= 'du1d') & (df.columns <= 'du%sd'%(ct.compute_lastdays)))]][:1]"
# perdallu = "df[df.columns[ ((df.columns >= 'du1d') & (df.columns <= 'du%sd'%(ct.compute_lastdays)))]][:1]"
# root_path=['D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\','/Users/Johnson/Documents/Quant/pyQuant3/stock']
# dfcf_path = 'D:\\MacTools\\WinTools\\eastmoney\\swc8\\config\\User\\6327113578970854\\StockwayStock.ini'

# win10Lengend = r'D:\Quant\new_tdx2'
# # win10Lengend = r'D:\Program\gfzq'
# win10Lixin = r'C:\zd_zszq'
# win10Triton = r'D:\MacTools\WinTools\new_tdx2'
# #东兴
# win10pazq = r'D:\MacTools\WinTools\new_tdx2'
# win10dxzq = r'D:\MacTools\WinTools\zd_dxzq'

# win7rootAsus = r'D:\Program Files\gfzq'
# win7rootXunji = r'E:\DOC\Parallels\WinTools\zd_pazq'
# win7rootList = [win10Triton,win10Lixin, win7rootAsus, win7rootXunji, win10Lengend]
# macroot = r'/Users/Johnson/Documents/Johnson/WinTools/new_tdx2'
# macroot_vm = r'/Volumes/VMware Shared Folders/MacTools/WinTools/new_tdx'
# xproot = r'E:\DOC\Parallels\WinTools\zd_pazq'

import configparser
from pathlib import Path
# from config.loader import GlobalConfig

# class GlobalConfigOnly_read:
#     def __init__(self, cfg_file=None):
#         if not cfg_file:
#             cfg_file = Path(__file__).parent / "global.ini"

#         self.cfg_file = Path(cfg_file)

#         # 禁用 % 插值
#         # self.cfg = configparser.ConfigParser(interpolation=None)
#         self.cfg = configparser.ConfigParser(
#             interpolation=None,
#             inline_comment_prefixes=("#", ";")
#         )

#         self.cfg.read(self.cfg_file, encoding="utf-8")

#         self.init_value = self.cfg.getint("general", "initGlobalValue")
#         self.marketInit = self.cfg.get("general", "marketInit")
#         self.marketblk = self.cfg.get("general", "marketblk")
#         self.scale_offset = self.cfg.get("general", "scale_offset")
#         self.resampleInit = self.cfg.get("general", "resampleInit")
#         self.write_all_day_date = self.cfg.get("general", "write_all_day_date")
#         self.duration_sleep_time = self.cfg.getint("general", "duration_sleep_time")

#         # 处理 saved_width_height
#         try:
#             if "x" in saved_wh_str:
#                 self.saved_width, self.saved_height = map(int, saved_wh_str.split("x"))
#             elif "," in saved_wh_str:
#                 self.saved_width, self.saved_height = map(int, saved_wh_str.split(","))
#             else:
#                 self.saved_width, self.saved_height = 260, 180
#         except Exception:
#             self.saved_width, self.saved_height = 260, 180

#         self.clean_terminal = self._split(
#             self.cfg.get("terminal", "clean_terminal", fallback="")
#         )

#         self.expressions = dict(self.cfg.items("expressions"))
#         self.paths = dict(self.cfg.items("path"))

#     def _split(self, s):
#         return [x.strip() for x in s.split(",") if x.strip()]

#     def get_expr(self, name):
#         return self.expressions.get(name)

#     def get_path(self, key):
#         return self.paths.get(key)

#     def __repr__(self):
#         return f"<GlobalConfig {self.cfg_file}>"


class GlobalConfig:
    def __init__(self, cfg_file=None, **updates):
        if not cfg_file:
            cfg_file = Path(__file__).parent / "global.ini"

        self.cfg_file = Path(cfg_file)
        self.cfg = configparser.ConfigParser(
            interpolation=None,
            inline_comment_prefixes=("#", ";")
        )
        self.cfg.read(self.cfg_file, encoding="utf-8")

        # ---- 读取原有参数（带 fallback 回写功能） ----
        self.init_value = self.get_with_writeback("general", "initGlobalValue", fallback=0, value_type="int")
        self.marketInit = self.get_with_writeback("general", "marketInit", fallback="all")
        self.marketblk = self.get_with_writeback("general", "marketblk", fallback="063.blk")
        self.scale_offset = self.get_with_writeback("general", "scale_offset", fallback="-0.45")
        self.resampleInit = self.get_with_writeback("general", "resampleInit", fallback="d")
        self.write_all_day_date = self.get_with_writeback("general", "write_all_day_date", fallback="20251208")
        self.detect_calc_support = self.get_with_writeback("general", "detect_calc_support", fallback=False, value_type="bool")
        self.duration_sleep_time = self.get_with_writeback("general", "duration_sleep_time", fallback=120, value_type="int")
        self.compute_lastdays = self.get_with_writeback("general", "compute_lastdays", fallback=5, value_type="int")
        self.alert_cooldown = self.get_with_writeback("general", "alert_cooldown", fallback=120, value_type="int")
        self.sina_limit_time = self.get_with_writeback("general", "sina_limit_time", fallback=30, value_type="int")
        self.sina_dd_limit_time = self.get_with_writeback("general", "sina_dd_limit_time", fallback=1200, value_type="int")
        self.stop_loss_pct = self.get_with_writeback("general", "stop_loss_pct", fallback=0.05, value_type="float")
        self.take_profit_pct = self.get_with_writeback("general", "take_profit_pct", fallback=0.10, value_type="float")
        self.trailing_stop_pct = self.get_with_writeback("general", "trailing_stop_pct", fallback=0.03, value_type="float")
        self.max_single_stock_ratio = self.get_with_writeback("general", "max_single_stock_ratio", fallback=0.3, value_type="float")
        self.min_position_ratio = self.get_with_writeback("general", "min_position_ratio", fallback=0.05, value_type="float")
        self.risk_duration_threshold = self.get_with_writeback("general", "risk_duration_threshold", fallback=300, value_type="int")
        self.pending_alert_cycles = self.get_with_writeback("general", "pending_alert_cycles", fallback=10, value_type="int")
        self.st_key_sort = self.get_with_writeback("general", "st_key_sort", fallback="2 1", value_type="str")
        self.code_startswith = self.get_with_writeback("general", "code_startswith", fallback='"6", "30", "00", "688", "43", "83", "87", "92"', value_type="tuple_str")
        self.winlimit = self.get_with_writeback("general", "winlimit", fallback=1, value_type="int")
        self.loglevel = self.get_with_writeback("general", "loglevel", fallback='INFO', value_type="str")
        self.cleanRAMdiskTemp = self.get_with_writeback("general", "cleanRAMdiskTemp", fallback='True', value_type="str")
        self.sina_dd_limit_day = self.get_with_writeback("general", "sina_dd_limit_day", fallback='0', value_type="str")

        saved_wh_str = self.get_with_writeback("general", "saved_width_height", fallback="230x160")
        try:
            if "x" in saved_wh_str:
                self.saved_width, self.saved_height = map(int, saved_wh_str.split("x"))
            elif "," in saved_wh_str:
                self.saved_width, self.saved_height = map(int, saved_wh_str.split(","))
            else:
                self.saved_width, self.saved_height = 260, 180
        except Exception:
            self.saved_width, self.saved_height = 260, 180

        self.clean_terminal = self._split(
            self.get_with_writeback("terminal", "clean_terminal", fallback="")
        )

        self.expressions = dict(self.cfg.items("expressions")) if self.cfg.has_section("expressions") else {}
        self.paths = dict(self.cfg.items("path")) if self.cfg.has_section("path") else {}

        # ---- 支持构造时直接写入 ----
        if updates:
            for key, value in updates.items():
                self.set_value("general", key, value)
            self.save()

    # ===================== 新增 get_with_writeback =====================

    def get_with_writeback(self, section: str, option: str, fallback: Any, value_type: str = "str") -> Any:
        """
        读取配置项，如果不存在则写入 fallback 并返回 fallback

        value_type 支持：
            - "str"
            - "int"
            - "float"
            - "bool"
            - "tuple_str"   # ('6','30') 或 6,30
        """

        # ===== 1. 确保 section 存在（绝对安全）=====
        if not self.cfg.has_section(section):
            self.cfg.add_section(section)

        # ===== 2. option 不存在：写回 fallback =====
        if not self.cfg.has_option(section, option):
            try:
                if value_type == "bool":
                    val_str = "True" if bool(fallback) else "False"
                else:
                    val_str = str(fallback)

                self.cfg.set(section, option, val_str)
                self.save()
            except Exception:
                # 写配置失败也不能影响程序运行
                pass

            return fallback

        # ===== 3. option 已存在：读取 raw =====
        try:
            raw = self.cfg.get(section, option)
        except Exception:
            return fallback

        # ===== 4. 按类型安全解析 =====
        try:
            if value_type == "int":
                return int(raw)

            elif value_type == "float":
                return float(raw)

            elif value_type == "bool":
                return str(raw).strip().lower() in ("1", "true", "yes", "on")

            # ===== tuple_str（重点增强）=====
            elif value_type == "tuple_str":
                raw = str(raw).strip()

                # 4.1 兼容老格式：('6','30','00')
                if raw.startswith("("):
                    try:
                        value = ast.literal_eval(raw)
                        if isinstance(value, (list, tuple)):
                            return tuple(str(x) for x in value)
                    except Exception:
                        pass

                # 4.2 新推荐格式：6,30,00,688
                parts = [
                    s.strip()
                    for s in raw.replace("'", "").replace('"', "").split(",")
                    if s.strip()
                ]
                if parts:
                    return tuple(parts)

                raise ValueError("empty tuple_str")

            # ===== 默认字符串 =====
            else:
                return raw

        except Exception:
            # ===== 5. 所有异常统一兜底 fallback =====
            if value_type == "tuple_str":
                if isinstance(fallback, (list, tuple)):
                    return tuple(str(x) for x in fallback)
                if isinstance(fallback, str):
                    return tuple(
                        s.strip()
                        for s in fallback.strip("()")
                        .replace("'", "")
                        .replace('"', "")
                        .split(",")
                        if s.strip()
                    )
                return ()

            return fallback
    # =====================================================================

    def _split(self, s):
        return [x.strip() for x in s.split(",") if x.strip()]

    def get_expr(self, name):
        return self.expressions.get(name)

    def get_path(self, key):
        return self.paths.get(key)

    # ===================== ✅ 写配置 API =====================
    def set_value(self, section, key, value):
        """设置配置项(内存中)"""
        if not self.cfg.has_section(section):
            self.cfg.add_section(section)
        self.cfg.set(section, key, str(value))
        # 如果是 general 区域，顺便更新实例字段
        if section == "general":
            setattr(self, key, value)

    def save(self):
        """写回 ini 文件"""
        with open(self.cfg_file, "w", encoding="utf-8") as f:
            self.cfg.write(f)

    def set_and_save(self, section, key, value):
        """一步完成 set + save"""
        self.set_value(section, key, value)
        self.save()
        log.info(f"使用内置save: {section} {key} {value} ok")
    # ========================================================

    def __repr__(self):
        return f"<GlobalConfig {self.cfg_file}>"



conf_ini= get_conf_path('global.ini')
if not conf_ini:
    log.critical("global.ini 加载失败，程序无法继续运行")

CFG = GlobalConfig(conf_ini)

initGlobalValue: int = CFG.init_value
clean_terminal: List[str] = CFG.clean_terminal

root_path: List[Optional[str]] = [
    CFG.get_path("root_path_windows"),
    CFG.get_path("root_path_mac"),
]

dfcf_path: Optional[str] = CFG.get_path("dfcf_path")

win10Lengend: Optional[str] = CFG.get_path("win10lengend")
win10Lixin: Optional[str] = CFG.get_path("win10lixin")
win10Triton: Optional[str] = CFG.get_path("win10triton")
win10pazq: Optional[str] = CFG.get_path("win10pazq")
win10dxzq: Optional[str] = CFG.get_path("win10dxzq")

win7rootAsus: Optional[str] = CFG.get_path("win7rootasus")
win7rootXunji: Optional[str] = CFG.get_path("win7rootxunji")
win7rootList: List[Optional[str]] = [win10Triton, win10Lixin, win7rootAsus, win7rootXunji, win10Lengend]
macroot: Optional[str] = CFG.get_path("macroot")
macroot_vm: Optional[str] = CFG.get_path("macroot_vm")
xproot: Optional[str] = CFG.get_path("xproot")
tdx_all_df_path: Optional[str] = CFG.get_path("tdx_all_df_path")
compute_lastdays: int = CFG.compute_lastdays
sina_limit_time: int = CFG.sina_limit_time
sina_dd_limit_time: int = CFG.sina_dd_limit_time
stop_loss_pct: float = CFG.stop_loss_pct
take_profit_pct: float = CFG.take_profit_pct
trailing_stop_pct: float = CFG.trailing_stop_pct
max_single_stock_ratio: float = CFG.max_single_stock_ratio
min_position_ratio: float = CFG.min_position_ratio
risk_duration_threshold: int = CFG.risk_duration_threshold
code_startswith: str = CFG.code_startswith
winlimit: int = CFG.winlimit
loglevel: str = CFG.loglevel
cleanRAMdiskTemp: str = CFG.cleanRAMdiskTemp
# log.info(f'code_startswith: {code_startswith}')
def get_os_path_sep() -> str:
    return os.path.sep

    
evalcmdfpath = r'./sina_pandasSelectCmd.txt'.replace('\\',get_os_path_sep())

# import multiprocessing
# from multiprocessing import Manager
# import threading

# class GlobalValues_mp:
#     _instance = None
#     _lock = threading.Lock()  # 确保多线程安全

#     def __new__(cls, ext_dict=None, use_manager=True):
#         with cls._lock:
#             if cls._instance is None:
#                 cls._instance = super().__new__(cls)
#                 cls._local_fallback = {}
#                 cls._use_manager = use_manager
#                 if use_manager:
#                     cls._manager = Manager()
#                     cls._global_dict = cls._manager.dict(ext_dict or {})
#                 else:
#                     cls._global_dict = ext_dict or {}
#             elif ext_dict is not None:
#                 # 支持重新注入共享字典
#                 if cls._use_manager:
#                     cls._global_dict.clear()
#                     cls._global_dict.update(ext_dict)
#                 else:
#                     cls._global_dict = ext_dict
#             return cls._instance

#     def getkey(self, key, default=None):
#         try:
#             value = self._global_dict.get(key, default)
#             self._local_fallback[key] = value
#             return value
#         except (BrokenPipeError, EOFError, OSError):
#             # 管道异常时尝试回退到本地
#             log.warning(f"getkey fallback for key={key}")
#             return self._local_fallback.get(key, default)

#     def setkey(self, key, value):
#         try:
#             self._global_dict[key] = value
#         except (BrokenPipeError, EOFError, OSError) as e:
#             log.error(f"setkey 管道断开: {e}, key={key}, value={value}")
#         finally:
#             self._local_fallback[key] = value

#     def getkey_status(self, key):
#         try:
#             exists = key in self._global_dict
#             if exists:
#                 self._local_fallback[key] = self._global_dict[key]
#             return exists
#         except (BrokenPipeError, EOFError, OSError):
#             return key in self._local_fallback

#     def getlist(self):
#         try:
#             keys = list(self._global_dict.keys())
#             for k in keys:
#                 self._local_fallback[k] = self._global_dict[k]
#             return keys
#         except (BrokenPipeError, EOFError, OSError):
#             return list(self._local_fallback.keys())

#     def rebuild_manager(self, ext_dict=None):
#         """在 Manager 崩掉或管道断开后，可以重新创建共享字典"""
#         with self._lock:
#             if self._use_manager:
#                 log.info("Rebuilding Manager shared dict...")
#                 self._manager = Manager()
#                 self._global_dict = self._manager.dict(ext_dict or self._local_fallback)


class GlobalValues:
    _instance: Optional['GlobalValues'] = None
    _global_dict: Dict[str, Any]
    _local_fallback: Dict[str, Any]

    def __new__(cls, ext_dict: Optional[Dict[str, Any]] = None) -> 'GlobalValues':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._global_dict = ext_dict if ext_dict is not None else {}
        elif ext_dict is not None:
            cls._global_dict = ext_dict
        cls._local_fallback = {}  # 本地兜底字典
        return cls._instance

    def getkey(self, key: str, default: Any = None) -> Any:
        """
        获取 key，优先从全局共享字典获取，失败则回退到本地字典
        """
        try:
            value = self._global_dict.get(key, default)
            # 成功获取时，同步更新本地 fallback
            self._local_fallback[key] = value
            return value
        except (BrokenPipeError, EOFError, OSError):
            # 管道断开时，从本地 fallback 获取
            return self._local_fallback.get(key, default)

    def setkey(self, key: str, value: Any) -> None:
        """
        设置 key，保证本地 fallback 始终更新
        """
        try:
            self._global_dict[key] = value
        except (BrokenPipeError, EOFError, OSError) as e:
            log.error(f"setkey 管道断开: {e}, key={key}, value={value}")
        finally:
            # 无论共享字典是否可用，本地字典都更新
            self._local_fallback[key] = value

    def getkey_status(self, key: str) -> bool:
        """
        检查 key 是否存在，优先共享字典
        """
        try:
            exists: bool = key in self._global_dict
            # 同步 fallback
            if exists:
                self._local_fallback[key] = self._global_dict[key]
            return exists
        except (BrokenPipeError, EOFError, OSError):
            return key in self._local_fallback

    def getlist(self) -> List[str]:
        """
        返回所有 key 列表，优先共享字典
        """
        try:
            keys: List[str] = list(self._global_dict.keys())
            # 同步 fallback
            for k in keys:
                self._local_fallback[k] = self._global_dict[k]
            return keys
        except (BrokenPipeError, EOFError, OSError):
            return list(self._local_fallback.keys())

class GlobalValues_noLocal:
    _instance = None

    def __new__(cls, ext_dict=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._global_dict = ext_dict or {}
        elif ext_dict is not None:
            cls._global_dict = ext_dict
        cls._local_fallback = {}   # 本地兜底字典
        return cls._instance

    def getkey(self, key, default=None):
        try:
            return self._global_dict.get(key, default)
        except (BrokenPipeError, EOFError, OSError):
            # 管道断开时，返回默认值，避免子进程报错
            # 你也可以这里写日志
            return default
        # return self._global_dict.get(key, default)

    def setkey(self, key, value):
        try:
            self._global_dict[key] = value
        except (BrokenPipeError, EOFError, OSError) as e:
            # 这里可以记录日志，说明 Manager 已经失效
            log.error(f"setkey 管道断开: {e}, key={key}, value={value}")
            # 可以选择丢弃，或者用本地 dict 兜底
            self._local_fallback[key] = value
        # self._global_dict[key] = value

    def getkey_status(self, key):
        return key in self._global_dict

    def getlist(self):
        try:
            return list(self._global_dict.keys())
        except (BrokenPipeError, EOFError, OSError):
            return list(self._local_fallback.keys())

def format_for_print(df,header=True,widths=False,showCount=False,width=0,table=False,limit_show=20):

    # alist = [x for x in set(df.columns.tolist())]
    # cat_col = ['涨停原因类别','category']
    try:
        cat_col = ['category']
        for col in cat_col:
            if col == '涨停原因类别':
                sep_ = '+'
            else:
                sep_ = ';'

            if col in df.columns and len(df) > 1:
                df[col]=df[col].apply(lambda x:str(x).replace('\r','').replace('\n',''))
                log.debug(f'topSort:{counterCategory(df,col,table=True)}')
                topSort=counterCategory(df,col,table=True).split()
                topSort.reverse()
                top_dic={}
                for x in topSort:
                    top_dic[x.split(sep_)[0]]=x
                    # top_dic[x.split(':')[0]]=x.replace(':','')
                # top_key = [x.split(':')[0] for x in topSort]
                # top_value = [x.replace(':','') for x in topSort]
                # sorted_top_dic = dict(sorted(top_dic.items(), key=lambda item: item[1], reverse=False))
                for idx in df.index[:limit_show]:
                    log.debug(f'idx:{idx} idx df.loc[idx][col]: {df.loc[idx][col]}')
                    ca_list = df.loc[idx][col].split(sep_)
                    ca_listB = ca_list.copy()
                    for key in top_dic:
                        if key in ca_list:
                            if ca_listB.index(key) != 0:
                                element_to_move = ca_listB.pop(ca_listB.index(key))
                                ca_listB.insert(0, top_dic[key])

                    if ca_listB !=  ca_list:
                        ca_listC=[('' if c.find(sep_) > 0 else ' ')+c for c in ca_listB]
                        # ca_listD= [x for x in ca_listC if x.find(':') > 0]
                        # list_to_str = "".join([for x in ca_listB if x.find(':') else x+''])
                        list_to_str = "".join(ca_listC)
                        df.loc[idx,col]=list_to_str

        # if 'category' in df.columns and len(df) > 0:
        #     df['category']=df['category'].apply(lambda x:str(x).replace('\r','').replace('\n',''))
        #     topSort=counterCategory(df,'category',table=True).split()
        #     topSort.reverse()
        #     top_dic={}
        #     for x in topSort:
        #         top_dic[x.split(':')[0]]=x
        #         # top_dic[x.split(':')[0]]=x.replace(':','')
        #     # top_key = [x.split(':')[0] for x in topSort]
        #     # top_value = [x.replace(':','') for x in topSort]
        #     # sorted_top_dic = dict(sorted(top_dic.items(), key=lambda item: item[1], reverse=False))
        #     for idx in df.index:
        #         ca_list = df.loc[idx].category.split(';')
        #         ca_listB = ca_list.copy()
        #         for key in top_dic:
        #             if key in ca_list:
        #                 if ca_listB.index(key) != 0:
        #                     element_to_move = ca_listB.pop(ca_listB.index(key))
        #                     ca_listB.insert(0, top_dic[key])

        #         if ca_listB !=  ca_list:
        #             ca_listC=[('' if c.find(':') > 0 else ' ')+c for c in ca_listB]
        #             # ca_listD= [x for x in ca_listC if x.find(':') > 0]
        #             # list_to_str = "".join([for x in ca_listB if x.find(':') else x+''])
        #             list_to_str = "".join(ca_listC)
        #             df.loc[idx,'category']=list_to_str
        else:
            log.info('df is None')
        alist = df.columns.tolist()
        if 'category' in df.columns:
            df['category'] = df['category'].apply(lambda x:str(x)[:16])
        if header:

            table = PrettyTable([''] + alist )
        else:
            table = PrettyTable(field_names=[''] + alist,header=False)

        for row in df[:limit_show].itertuples():  
            if width > 0:
                # col = df.columns.tolist()
                # co_count = len(df.columns)
                # row_str =f'{str(row.Index)},'
                # row_str =f'{str(row.Index)},'
                # # row_str = ''
                # for idx in range(0,len(row)-1):
                #     print(f'idx:{row[idx]}')
                #     # row_str +=f'{str(getattr(row,col[idx]))},'
                #     row_str +=f'{row[idx]},'
                # # row_str +='%s,'%(fill(str(getattr(row,col[-1])).replace(',',';').replace('，',';'),width=width))
                # row_str +='%s,'%(fill(str(row[-1]).replace(',',';').replace('，',';'),width=width))
                # # log.info(f'row_str:{row_str}')
                # # print(row_str.split(','))
                # table.add_row(row_str.split(','))

                row_str = f''
                for idx in range(0,len(row)-1):
                    row_str+=f'row[{idx}],'
                row_str+=f'fill(str(row[-1]),width=width)'
                log.debug(f'row_str:{row_str}')
                table.add_row(eval(row_str))

            else:
                table.add_row(row)

        if not widths:
            # print(f'showCount:{showCount}')
            if showCount:
                count = f'Count:{len(df)}'
                table = str(table)
                table = table + f'\n{count}'
                if table:
                    if 'category' in df.columns:
                        topSort=counterCategory(df,'category',table=table)
                        table = table + f'\n{topSort}'
            return str(table)
        else:
            if isinstance(widths,list):
                table.set_widths(widths)
                # table.get_string()
                # print table.get_widths()
                return str(table)
        return str(table),table.get_widths()

    except Exception as ex:
        # print("Exception on code: {}".format(code)+ os.linesep + traceback.format_exc())
        # return Exception("Exception on format_for_print {}".format(len(df))+ os.linesep + traceback.format_exc())    
        msg = "Exception on format_for_print {}".format(len(df))+ os.linesep + traceback.format_exc()
        log.error(msg)
        return Exception(msg)

def format_replce_list(lst, old='volume', new='maxp'):
        lst_n = [new if x==old else x for x in lst]
        return lst_n


def list_replace(lst, old=1, new=10):
    """replace list elements (inplace)"""
    i = -1
    try:
        while True:
            i = lst.index(old, i + 1)
            lst[i] = new
    except ValueError:
        pass


def format_for_print_show(df,columns_format=None,showCount=False,col=None,table=False,noformat=False):
    if columns_format is None:
        columns_format = ct.Monitor_format_trade
    if col is not None and col not in columns_format:
        # columns_format.remove('volume')
        # columns_format.append(col)
        columns_format = format_replce_list(columns_format,old='volume',new=col)
    # if showCount:
    #     # print(f'Count:{len(df)}')
    #     count_string = (f'Count:{len(df)}')
    #     table = format_for_print(df.loc[:, columns_format],count=count_string)
    # else:
    if noformat:
        # table = format_for_print(df,showCount=showCount,table=table,limit_show=50)
        table = format_for_print(df.loc[:, columns_format],showCount=showCount,table=table,limit_show=50)
    else:
        table = format_for_print(df.loc[:, columns_format],showCount=showCount,table=table,limit_show=50)
    return table

def format_for_print2(df):
    table = PrettyTable(list(df.columns))
    for row in df.itertuples():
        table.add_row(row[1:])
    return (table)


hk_js_decode = """
function d(t) {
    var e, i, n, r, a, o, s, l = (arguments,
            864e5), u = 7657, c = [], h = [], d = ~(3 << 30), f = 1 << 30,
        p = [0, 3, 5, 6, 9, 10, 12, 15, 17, 18, 20, 23, 24, 27, 29, 30], m = Math, g = function () {
            var l, u;
            for (l = 0; 64 > l; l++)
                h[l] = m.pow(2, l),
                26 > l && (c[l] = v(l + 65),
                    c[l + 26] = v(l + 97),
                10 > l && (c[l + 52] = v(l + 48)));
            for (c.push("+", "/"),
                     c = c.join(""),
                     i = t.split(""),
                     n = i.length,
                     l = 0; n > l; l++)
                i[l] = c.indexOf(i[l]);
            return r = {},
                e = o = 0,
                a = {},
                u = w([12, 6]),
                s = 63 ^ u[1],
            {
                _1479: T,
                _136: _,
                _200: S,
                _139: k,
                _197: _mi_run
            }["_" + u[0]] || function () {
                return []
            }
        }, v = String.fromCharCode, b = function (t) {
            return t === {}._
        }, N = function () {
            var t, e;
            for (t = y(),
                     e = 1; ;) {
                if (!y())
                    return e * (2 * t - 1);
                e++
            }
        }, y = function () {
            var t;
            return e >= n ? 0 : (t = i[e] & 1 << o,
                o++,
            o >= 6 && (o -= 6,
                e++),
                !!t)
        }, w = function (t, r, a) {
            var s, l, u, c, d;
            for (l = [],
                     u = 0,
                 r || (r = []),
                 a || (a = []),
                     s = 0; s < t.length; s++)
                if (c = t[s],
                    u = 0,
                    c) {
                    if (e >= n)
                        return l;
                    if (t[s] <= 0)
                        u = 0;
                    else if (t[s] <= 30) {
                        for (; d = 6 - o,
                                   d = c > d ? d : c,
                                   u |= (i[e] >> o & (1 << d) - 1) << t[s] - c,
                                   o += d,
                               o >= 6 && (o -= 6,
                                   e++),
                                   c -= d,
                                   !(0 >= c);)
                            ;
                        r[s] && u >= h[t[s] - 1] && (u -= h[t[s]])
                    } else
                        u = w([30, t[s] - 30], [0, r[s]]),
                        a[s] || (u = u[0] + u[1] * h[30]);
                    l[s] = u
                } else
                    l[s] = 0;
            return l
        }, x = function (t) {
            var e, i, n;
            for (t > 1 && (e = 0),
                     e = 0; t > e; e++)
                r.d++,
                    n = r.d % 7,
                (3 == n || 4 == n) && (r.d += 5 - n);
            return i = new Date,
                i.setTime((u + r.d) * l),
                i
        }, S = function () {
            var t, i, a, o, l;
            if (s >= 1)
                return [];
            for (r.d = w([18], [1])[0] - 1,
                     a = w([3, 3, 30, 6]),
                     r.p = a[0],
                     r.ld = a[1],
                     r.cd = a[2],
                     r.c = a[3],
                     r.m = m.pow(10, r.p),
                     r.pc = r.cd / r.m,
                     i = [],
                     t = 0; o = {
                d: 1
            },
                 y() && (a = w([3])[0],
                     0 == a ? o.d = w([6])[0] : 1 == a ? (r.d = w([18])[0],
                         o.d = 0) : o.d = a),
                     l = {
                         day: x(o.d)
                     },
                 y() && (r.ld += N()),
                     a = w([3 * r.ld], [1]),
                     r.cd += a[0],
                     l.close = r.cd / r.m,
                     i.push(l),
                 !(e >= n) && (e != n - 1 || 63 & (r.c ^ t + 1)); t++)
                ;
            return i[0].prevclose = r.pc,
                i
        }, _ = function () {
            var t, i, a, o, l, u, c, h, d, f, p;
            if (s > 2)
                return [];
            for (c = [],
                     d = {
                         v: "volume",
                         p: "price",
                         a: "avg_price"
                     },
                     r.d = w([18], [1])[0] - 1,
                     h = {
                         day: x(1)
                     },
                     a = w(1 > s ? [3, 3, 4, 1, 1, 1, 5] : [4, 4, 4, 1, 1, 1, 3]),
                     t = 0; 7 > t; t++)
                r[["la", "lp", "lv", "tv", "rv", "zv", "pp"][t]] = a[t];
            for (r.m = m.pow(10, r.pp),
                     s >= 1 ? (a = w([3, 3]),
                         r.c = a[0],
                         a = a[1]) : (a = 5,
                         r.c = 2),
                     r.pc = w([6 * a])[0],
                     h.pc = r.pc / r.m,
                     r.cp = r.pc,
                     r.da = 0,
                     r.sa = r.sv = 0,
                     t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
                for (l = {},
                         o = {},
                         f = r.tv ? y() : 1,
                         i = 0; 3 > i; i++)
                    if (p = ["v", "p", "a"][i],
                    (f ? y() : 0) && (a = N(),
                        r["l" + p] += a),
                        u = "v" == p && r.rv ? y() : 1,
                        a = w([3 * r["l" + p] + ("v" == p ? 7 * u : 0)], [!!i])[0] * (u ? 1 : 100),
                        o[p] = a,
                    "v" == p) {
                        if (!(l[d[p]] = a) && (s > 1 || 241 > t) && (r.zv ? !y() : 1)) {
                            o.p = 0;
                            break
                        }
                    } else
                        "a" == p && (r.da = (1 > s ? 0 : r.da) + o.a);
                r.sv += o.v,
                    l[d.p] = (r.cp += o.p) / r.m,
                    r.sa += o.v * r.cp,
                    l[d.a] = b(o.a) ? t ? c[t - 1][d.a] : l[d.p] : r.sv ? ((m.floor((r.sa * (2e3 / r.m) + r.sv) / r.sv) >> 1) + r.da) / 1e3 : l[d.p] + r.da / 1e3,
                    c.push(l)
            }
            return c[0].date = h.day,
                c[0].prevclose = h.pc,
                c
        }, T = function () {
            var t, e, i, n, a, o, l;
            if (s >= 1)
                return [];
            for (r.lv = 0,
                     r.ld = 0,
                     r.cd = 0,
                     r.cv = [0, 0],
                     r.p = w([6])[0],
                     r.d = w([18], [1])[0] - 1,
                     r.m = m.pow(10, r.p),
                     a = w([3, 3]),
                     r.md = a[0],
                     r.mv = a[1],
                     t = []; a = w([6]),
                     a.length;) {
                if (i = {
                    c: a[0]
                },
                    n = {},
                    i.d = 1,
                32 & i.c)
                    for (; ;) {
                        if (a = w([6])[0],
                        63 == (16 | a)) {
                            l = 16 & a ? "x" : "u",
                                a = w([3, 3]),
                                i[l + "_d"] = a[0] + r.md,
                                i[l + "_v"] = a[1] + r.mv;
                            break
                        }
                        if (32 & a) {
                            o = 8 & a ? "d" : "v",
                                l = 16 & a ? "x" : "u",
                                i[l + "_" + o] = (7 & a) + r["m" + o];
                            break
                        }
                        if (o = 15 & a,
                            0 == o ? i.d = w([6])[0] : 1 == o ? (r.d = o = w([18])[0],
                                i.d = 0) : i.d = o,
                            !(16 & a))
                            break
                    }
                n.date = x(i.d);
                for (o in {
                    v: 0,
                    d: 0
                })
                    b(i["x_" + o]) || (r["l" + o] = i["x_" + o]),
                    b(i["u_" + o]) && (i["u_" + o] = r["l" + o]);
                for (i.l_l = [i.u_d, i.u_d, i.u_d, i.u_d, i.u_v],
                         l = p[15 & i.c],
                     1 & i.u_v && (l = 31 - l),
                     16 & i.c && (i.l_l[4] += 2),
                         e = 0; 5 > e; e++)
                    l & 1 << 4 - e && i.l_l[e]++,
                        i.l_l[e] *= 3;
                i.d_v = w(i.l_l, [1, 0, 0, 1, 1], [0, 0, 0, 0, 1]),
                    o = r.cd + i.d_v[0],
                    n.open = o / r.m,
                    n.high = (o + i.d_v[1]) / r.m,
                    n.low = (o - i.d_v[2]) / r.m,
                    n.close = (o + i.d_v[3]) / r.m,
                    a = i.d_v[4],
                "number" == typeof a && (a = [a, a >= 0 ? 0 : -1]),
                    r.cd = o + i.d_v[3],
                    l = r.cv[0] + a[0],
                    r.cv = [l & d, r.cv[1] + a[1] + !!((r.cv[0] & d) + (a[0] & d) & f)],
                    n.volume = (r.cv[0] & f - 1) + r.cv[1] * f,
                    t.push(n)
            }
            return t
        }, k = function () {
            var t, e, i, n;
            if (s > 1)
                return [];
            for (r.l = 0,
                     n = -1,
                     r.d = w([18])[0] - 1,
                     i = w([18])[0]; r.d < i;)
                e = x(1),
                    0 >= n ? (y() && (r.l += N()),
                        n = w([3 * r.l], [0])[0] + 1,
                    t || (t = [e],
                        n--)) : t.push(e),
                    n--;
            return t
        };
    return _mi_run = function () {
        var t, i, a, o;
        if (s >= 1)
            return [];
        for (r.f = w([6])[0],
                 r.c = w([6])[0],
                 a = [],
                 r.dv = [],
                 r.dl = [],
                 t = 0; t < r.f; t++)
            r.dv[t] = 0,
                r.dl[t] = 0;
        for (t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
            for (o = [],
                     i = 0; i < r.f; i++)
                y() && (r.dl[i] += N()),
                    r.dv[i] += w([3 * r.dl[i]], [1])[0],
                    o[i] = r.dv[i];
            a.push(o)
        }
        return a
    }
        ,
        g()()
}
"""

# def tool_trade_date_hist_sina() -> pd.DataFrame:
#     """
#     交易日历-历史数据
#     https://finance.sina.com.cn/realstock/company/klc_td_sh.txt
#     :return: 交易日历
#     :rtype: pandas.DataFrame
#     """
#     url = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"
#     r = requests.get(url)
#     js_code = py_mini_racer.MiniRacer()
#     js_code.eval(hk_js_decode)
#     dict_list = js_code.call(
#         "d", r.text.split("=")[1].split(";")[0].replace('"', "")
#     )  # 执行js解密代码
#     temp_df = pd.DataFrame(dict_list)
#     temp_df.columns = ["trade_date"]
#     temp_df["trade_date"] = pd.to_datetime(temp_df["trade_date"]).dt.date
#     temp_list = temp_df["trade_date"].to_list()
#     temp_list.append(datetime.date(1992, 5, 4))  # 是交易日但是交易日历缺失该日期
#     temp_list.sort()
#     temp_df = pd.DataFrame(temp_list, columns=["trade_date"])
#     return temp_df

# def fetch_stocks_trade_date():
#     try:
#         data = tool_trade_date_hist_sina()
#         if data is None or len(data.index) == 0:
#             return None
#         # data_date = set(data['trade_date'].values.tolist())
#         data_date = (data['trade_date'].values.tolist())
#         return data_date
#     except Exception as e:
#         print(f"stockfetch.fetch_stocks_trade_date处理异常：{e}")
#     return None

# def is_trade_date_old(date=datetime.date.today()):
#     trade_status = GlobalValues().getkey('is_trade_date')
#     if trade_status is None:
#         trade_date = fetch_stocks_trade_date()
#         if trade_date is None:
#             return None
#         if date in trade_date:
#             return True
#         else:
#             return False
#     else:
#         return trade_status
def read_ini(inifile: str = 'filter.ini', setrule: Optional[str] = None, category: str = 'General', filterkey: str = 'filter_rule') -> Optional[str]:
    from configobj import ConfigObj
    baser: str = getcwd().split('stock')[0]
    base: str = baser + 'stock' + path_sep
    config_file_path: str = base + inifile
    setrule = setrule.strip() if setrule is not None else None
    rule: Optional[str] = None
    if not os.path.exists(config_file_path):
        # Define the path for the config file
        # --- Writing a config file ---
        config = ConfigObj()
        config.filename = config_file_path

        # Add sections and options
        if category == 'General':
            config[category] = {}
            rule = "top_all.query('boll >=fibl > 1 and red > 1 and close > lastp2d and high > upper')"
            config[category][filterkey] = rule
        else:
            config[category] = {}
            rule = None
            config[category][filterkey] = rule
        # config['General']['version'] = '1.0.0'

        # config['Database'] = {}
        # config['Database']['host'] = 'localhost'
        # config['Database']['port'] = '5432'
        # config['Database']['username'] = 'admin'
        # config['Database']['password'] = 'secure_pass'

        # # Add a section with list values and a root-level option
        # config['Features'] = {}
        # config['Features']['enabled_modules'] = ['logging', 'analytics', 'reporting']
        # config['debug_mode'] = 'True' # Root-level option

        # Write the config object to the file
        config.write()
        print(f'config[{category}][{filterkey}] : {rule}')
        print(f"Config file '{config_file_path}' created successfully.")

    else:
        # --- Reading a config file ---
        read_config = ConfigObj(config_file_path)
        # Access values like a dictionary
        if category in read_config.keys():
            if filterkey in read_config[category].keys():
                rule = read_config[category][filterkey]
                print(f'read_config[{category}][{filterkey}] :  {rule}')
            else:
                read_config[category][filterkey] = {}
                rule = 'None'
                read_config[category][filterkey] = rule
                read_config.write()
                print(f'read_config[{category}][{filterkey}] :  {rule}')

        else:
            read_config[category] = {}
            rule = 'None'
            read_config[category][filterkey] = rule
            read_config.write()
            print(f'read_config[{category}][{filterkey}] :  {rule}')
            # print(f"Config file '{config_file_path}' init None")
        # db_host = read_config['Database']['host']
        # enabled_modules = read_config['Features']['enabled_modules']
        # debug_mode = read_config['debug_mode']

        # print(f"\nRead from config file:")
        # print(f"Application Name: {app_name}")
        # print(f"Database Host: {db_host}")
        # print(f"Enabled Modules: {enabled_modules}")
        # print(f"Debug Mode: {debug_mode}")
        if setrule is not None and setrule != 'default':
            read_config[category][filterkey] = setrule
            if rule is not None and rule != 'None':
                read_config[category][f'{filterkey}{get_today("")}'] = rule
            # --- Updating a config file ---
            # read_config['General']['version'] = '1.0.1'
            # read_config['Database']['password'] = 'new_secure_pass'
            read_config.write()
            print(f'config[{category}][{filterkey}] : {setrule}')
            print(f"Config file '{config_file_path}' updated successfully.")
    
    if rule is not None and (rule.find('top_all') >= 0 or rule.find('top_temp') >= 0):
        rule = rule.replace('top_all.query', '').replace('top_temp.query', '')
    if rule == 'None':
        rule = None
    if setrule == 'default':
        rule = (f' category:{category} key:{read_config[category].keys()}\n{read_config[category][filterkey]}')
    return rule

def is_trade_date(date: Union[datetime.date, str] = datetime.date.today()) -> Any:
    trade_status: Any = None
    if isinstance(date, datetime.date):
        date_str: str = date.strftime('%Y-%m-%d')
        if date_str == get_today():
            trade_status = GlobalValues().getkey('is_trade_date')
        date = date_str
    if trade_status is None:
        trade_status = get_day_istrade_date(date)
        GlobalValues().setkey('is_trade_date', trade_status)
    return trade_status



def get_last_trade_date(dt=None):
    if dt is None:
        dt = datetime.date.today().strftime('%Y-%m-%d')
    return(a_trade_calendar.get_pre_trade_date(dt))

def get_lastdays_trade_date(days=1, base_date=None):
    """
    days = 1 -> 上一个交易日
    days = 2 -> 上两个交易日
    """
    days = int(days)
    if days < 1:
        raise ValueError("days must be >= 1")

    if base_date is None:
        base_date = datetime.date.today().strftime('%Y-%m-%d')

    dt = base_date

    for _ in range(days):
        dt = a_trade_calendar.get_pre_trade_date(dt)

    return dt



def get_day_istrade_date(dt: Optional[Union[datetime.date, str]] = None) -> bool:
    # 2025
    sep: str = '-'
    if dt is None:
        TODAY: datetime.date = datetime.date.today()
        fstr: str = "%Y" + sep + "%m" + sep + "%d"
        dt = TODAY.strftime(fstr)
    else:
        if isinstance(dt, datetime.date):
            dt = dt.strftime('%Y-%m-%d')
    is_trade_date: bool = a_trade_calendar.is_trade_date(dt)

    return is_trade_date


# is_trade_date_today = get_day_istrade_date()
# last_trade_date = get_last_trade_date()


def check_file_exist(filepath):
    filestatus=False
    if os.path.exists(filepath):
        filestatus = True
    return filestatus


def getcwd() -> str:
    dirname, filename = os.path.split(os.path.abspath(sys.argv[0]))
    return dirname

def get_sys_system() -> str:
    return platform.system()

def isMac() -> bool:
    if get_sys_system().find('Darwin') == 0:
        return True
    else:
        return False

def get_run_path_stock(fp=None):
    # path ='c:\\users\\johnson\\anaconda2\\envs\\pytorch_gpu\\lib\\site-packages'
    # root_path='D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\'
    path = getcwd()
    alist = path.split('stock')
    # if len(alist) > 0:
    if len(alist) > 0 and path.find('stock') >=0:
        path = alist[0]
        # os_sep=get_os_path_sep()
        if fp is not None:
            path = path + fp
        log.debug("info:%s getcwd:%s"%(alist[0],path))
    else:
        if isMac():
            path  = root_path[1].split('stock')[0]
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        else:
            path  = root_path[0].split('stock')[0]
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        log.debug("error:%s cwd:%s"%(alist[0],path))
    return path


def get_run_path_tdx(fp=None):
    # path ='c:\\users\\johnson\\anaconda2\\envs\\pytorch_gpu\\lib\\site-packages'
    # root_path='D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\'
    path = getcwd()
    log.debug(f'tdx_all_df_path {path}')
    alist = path.split('stock')
    # if len(alist) > 0:
    if len(alist) > 0 and path.find('stock') >=0:
        path = alist[0]
        # os_sep=get_os_path_sep()
        if fp is not None:
            # path = path + fp + '.h5'
            path  =  os.path.join(path, fp + '.h5')
            if not check_file_exist(path):
                log.error(f'path not find : {path}')
                # path = tdx_all_df_path + os.sep + fp + '.h5'
                path = os.path.join(tdx_all_df_path, fp + '.h5')
                log.debug(f'tdx_all_df_path: {tdx_all_df_path} os.sep: {os.sep} path: {path}')
                if not check_file_exist(path):
                    log.error(f'path not find tdx_all_df_path : {path} os.sep:{os.sep}')
                else:
                    log.info(f'path find in tdx_all_df_path : {path} os.sep:{os.sep}')

        log.debug("info:%s getcwd:%s"%(alist[0],path))
    else:
        if isMac():
            # path  = root_path[1].split('stock')[0] + fp + '.h5'
            path  =  os.path.join(root_path[1].split('stock')[0], fp + '.h5')

            if not check_file_exist(path):
                log.error(f'path not find : {path}')
        else:
            # path  = root_path[0].split('stock')[0] + fp + '.h5'
            path  =  os.path.join(root_path[0].split('stock')[0], fp + '.h5')
            if not check_file_exist(path):
                log.error(f'path not find1 : {path}')
                # path = tdx_all_df_path + os.sep + fp + '.h5'
                path = os.path.join(tdx_all_df_path, fp + '.h5')
                log.debug(f'tdx_all_df_path: {tdx_all_df_path} path: {path}')
                if not check_file_exist(path):
                    log.error(f'path not find tdx_all_df_path : {path}')
                else:
                    log.info(f'path find in tdx_all_df_path : {path}')
        log.debug("error:%s cwd:%s"%(alist[0],path))
    return path


tdx_hd5_name = r'tdx_all_df_%s' % (300)
tdx_hd5_path = get_run_path_tdx(tdx_hd5_name)

# win10_ramdisk_root = r'R:'
# mac_ramdisk_root = r'/Volumes/RamDisk'
# ramdisk_rootList = [win10_ramdisk_root, mac_ramdisk_root]
ramdisk_rootList = LoggerFactory.ramdisk_rootList
path_sep = os.path.sep




def get_now_basedir(root_list=[macroot,macroot_vm]):
    basedir=''
    for mpath in root_list:
        if os.path.exists(mpath):
            basedir = mpath
            break
    return basedir


def get_tdx_dir():
    os_sys = get_sys_system()
    os_platform = get_sys_platform()
    if os_sys.find('Darwin') == 0:
        log.info("DarwinFind:%s" % os_sys)
        macbase=get_now_basedir()
        basedir = macbase.replace('/', path_sep).replace('\\', path_sep)
        log.info("Mac:%s" % os_platform)

    elif os_sys.find('Win') == 0:
        log.info("Windows:%s" % os_sys)
        if os_platform.find('XP') == 0:
            log.info("XP:%s" % os_platform)
            basedir = xproot.replace('/', path_sep).replace('\\', path_sep)  # 如果你的安装路径不同,请改这里
        else:
            log.info("Win7O:%s" % os_platform)
            for root in win7rootList:
                basedir = root.replace('/', path_sep).replace('\\', path_sep)  # 如果你的安装路径不同,请改这里
                if os.path.exists(basedir):
                    log.info("%s : path:%s" % (os_platform, basedir))
                    break
    if not os.path.exists(basedir):
        log.error("basedir not exists")
    return basedir


def get_sys_platform() -> str:
    return platform.platform()




def get_os_system():
    os_sys = get_sys_system()
    os_platform = get_sys_platform()
    if os_sys.find('Darwin') == 0:
        # log.info("Mac:%s" % os_platform)
        return 'mac'
    elif os_sys.find('Win') == 0:
        # log.info("Windows:%s" % os_sys)
        if os_platform.find('10'):
            return 'win10'

    elif os_sys.find('Win') == 0:
        # log.info("Windows:%s" % os_sys)
        if os_platform.find('XP'):
            return 'winXP'
    else:
        return 'other'

# if get_os_system().find('win') >= 0:
    # import win_unicode_console
#     # https://github.com/Drekin/win-unicode-console
#     win_unicode_console.enable(use_readline_hook=False)

def set_default_encode(code='utf-8'):
        # import sys
        importlib.reload(sys)
        sys.setdefaultencoding(code)
        print((sys.getdefaultencoding()))
        print((sys.stdin.encoding,sys.stdout.encoding))
        


# reload(sys)
# sys.setdefaultencoding('utf8')
# reload(sys)
# sys.setdefaultencoding('cp936')


          
def isDigit(x):
    #re def isdigit()
    try:
        if str(x) == 'nan' or x is None:
            return False
        else:
            float(x)
            return True
    except ValueError:
        return False

def get_ramdisk_dir() -> Optional[str]:
    os_platform: str = get_sys_platform()
    basedir: Optional[str] = None
    for root in ramdisk_rootList:
        basedir = root.replace('/', path_sep).replace('\\', path_sep)
        if os.path.exists(basedir):
            log.info("%s : path:%s" % (os_platform, basedir))
            break
    return basedir

RamBaseDir = get_ramdisk_dir()


def get_ramdisk_path(filename: str, lock: bool = False) -> Optional[str]:
    if filename:
        basedir: Optional[str] = RamBaseDir
        if basedir is None or not os.path.isdir(basedir):
            log.error("ramdisk Root Err:%s" % (basedir))
            return None

        if not os.path.exists(basedir):
            log.error("basedir not exists")
            return None

        if not lock:
            if not filename.endswith('h5'):
                filename = filename + '.h5'
        else:
            if filename.endswith('h5'):
                filename = filename.replace('h5', 'lock')
            else:
                filename = filename + '.lock'

        if filename.find(basedir) >= 0:
            log.info("file:%s" % (filename))
            return filename

        file_path = basedir + path_sep + filename
        # for root in win7rootList:
        #     basedir = root.replace('/', path_sep).replace('\\',path_sep)  # 如果你的安装路径不同,请改这里
        #     if os.path.exists(basedir):
        #         log.info("%s : path:%s" % (os_platform,basedir))
        #         break
    return file_path
# get_ramdisk_path('/Volumes/RamDisk/top_now.h5')


scriptcount = '''tell application "Terminal"
    --activate
    get the count of window
end tell
'''

scriptname = '''tell application "Terminal"
    --activate
    %s the name of window %s
end tell
'''


# title:sina_Market-DurationDn.py
# target rect1:(106, 586, 1433, 998) rect2:(106, 586, 1433, 998)
# title:sina_Market-DurationCXDN.py
# target rect1:(94, 313, 1421, 673) rect2:(94, 313, 1421, 673)
# title:sina_Market-DurationSH.py
# title:sina_Market-DurationUP.py
# target rect1:(676, 579, 1996, 1017) rect2:(676, 579, 1996, 1017)
# title:sina_Monitor-Market-LH.py
# target rect1:(588, 343, 1936, 735) rect2:(588, 343, 1936, 735)
# title:sina_Monitor-Market.py
# title:sina_Monitor.py
# target rect1:(259, 0, 1698, 439) rect2:(259, 0, 1698, 439)
# title:singleAnalyseUtil.py
# target rect1:(1036, 29, 1936, 389) rect2:(1036, 29, 1936, 389)
# title:LinePower.py
# target rect1:(123, 235, 1023, 595) rect2:(123, 235, 1023, 595)
# title:sina_Market-DurationDnUP.py
# title:instock_Monitor.py
# target rect1:(229, 72, 1589, 508) rect2:(229, 72, 1589, 508)


terminal_positionKey4K = {'sina_Market-DurationDn.py': '106, 586,1400,440',
                        'sina_Market-DurationCXDN.py': '94, 313,1400,440',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Market-DurationUP.py': '676, 579,1400,440',
                        'sina_Monitor-Market-LH.py': '588, 343,1400,440',
                        'sina_Monitor-Market.py': '19, 179,1400,440',
                        'sina_Monitor.py': '259, 0,1400, 520',
                        'singleAnalyseUtil.py': '1036, 29,920,360',
                        'LinePower.py': '123, 235,760, 420', 
                        'sina_Market-DurationDnUP.py': '41, 362,1400,440',
                        'instock_Monitor.py':'229, 72,1360,440',
                        'chantdxpower.py':'155, 167, 1200, 480',}



terminal_positionKey1K_triton = {'sina_Market-DurationDn.py': '48, 506,1356,438',
                        'sina_Market-DurationCXDN.py': '13, 310,1356,438',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Monitor-Market-LH.py': '567, 286,1356,407',
                        'sina_Monitor-Market.py': '140, 63,1400,440',
                        'sina_Monitor.py': '109, 20, 1356, 520',
                        'singleAnalyseUtil.py': '1046, 20,897,359',
                        'LinePower.py': '9, 216, 761,407',
                        'instock_MonitorTK.py': '8,638,761,407',
                        'sina_Market-DurationDnUP.py': '602,518,1352,464',
                        'sina_Market-DurationUP.py': '48, 506,1353,438',
                        'instock_Monitor.py':'32, 86,1400, 359',
                        'chantdxpower.py':'86, 128, 649,407',
                        'ths-tdx-web.py':'70, 200, 159,27',
                        'pywin32_mouse.py':'70, 200, 159,27',
                        'filter_resample_Monitor.py':'549, 244,1356,520'}

terminal_positionKey_triton = {'sina_Market-DurationDn.py': '48, 506,1356,438',
                        'sina_Market-DurationCXDN.py': '13, 310,1356,438',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Monitor-Market-LH.py': '567, 286,1356,407',
                        'sina_Monitor-Market.py': '140, 63,1400,440',
                        'sina_Monitor.py': '109, 20, 1356, 520',
                        'singleAnalyseUtil.py': '1046, 20,897,359',
                        'LinePower.py': '9, 216, 761,407',
                        'instock_MonitorTK.py': '8,638,761,407',
                        'sina_Market-DurationDnUP.py': '602,518,1352,464',
                        'sina_Market-DurationUP.py': '48, 506,1353,438',
                        'instock_Monitor.py':'32, 86,1400, 359',
                        'chantdxpower.py':'86, 128, 649,407',
                        'ths-tdx-web.py':'70, 200, 159,27',
                        'pywin32_mouse.py':'70, 200, 159,27',
                        'filter_resample_Monitor.py':'549, 244,1356,520'}



terminal_positionKey2K_R9000P = {'sina_Market-DurationDn.py': '-13, 601,1400,440',
                        'sina_Market-DurationCXDN.py': '-6, 311,1400,440',
                        'sina_Market-DurationSH.py': '-29, 623,1400,440',
                        'sina_Market-DurationUP.py': '445, 503,1400,440',
                        'sina_Monitor-Market-LH.py': '521, 332,1400,420',
                        'sina_Monitor-Market.py': '271, 39,1400,440',
                        'sina_Monitor.py': '108, 1, 1400, 560',
                        'chantdxpower.py': '53, 66,800,420', 
                        'singleAnalyseUtil.py': '673, 0,880,360',
                        'LinePower.py': '6, 216,800,420', 
                        'sina_Market-DurationDnUP.py': '41, 362,1400,480' ,}


''' R9000P 2.5K
title:sina_Market-DurationDn.py
target rect1:(6, 434, 1406, 874) rect2:(6, 434, 1406, 874)
target rect1:(-13, 601, 1387, 1041) rect2:(-13, 601, 1387, 1041)
title:sina_Monitor-Market-LH.py
target rect1:(666, 338, 2067, 758) rect2:(666, 338, 2067, 758)
title:sina_Monitor-Market.py
title:LinePower.py
title:sina_Monitor.py
target rect1:(271, 39, 1671, 479) rect2:(271, 39, 1671, 479)
title:singleAnalyseUtil.py
target rect1:(833, 666, 1713, 1026) rect2:(833, 666, 1713, 1026)
title:sina_Market-DurationCXDN.py
target rect1:(31, 301 1445, 688) rect2:(45, 248, 1445, 688)
title:sina_Market-DurationUp.py
target rect1:(92, 142, 1492, 582) rect2:(92, 142, 1492, 582)
'''



# title:sina_Market-DurationDn.py
# target rect1:(-4, 718, 1396, 1178) rect2:(-4, 718, 1396, 1178)
# title:sina_Monitor-Market-LH.py
# target rect1:(-25600, -25600, -25441, -25573) rect2:(-25600, -25600, -25441, -25573)
# title:sina_Monitor-Market.py
# title:LinePower.py
# title:sina_Monitor.py
# target rect1:(140, 63, 1540, 523) rect2:(140, 63, 1540, 523)
# title:singleAnalyseUtil.py
# target rect1:(554, 406, 1563, 799) rect2:(554, 406, 1563, 799)
# title:sina_Market-DurationCXDN.py
# target rect1:(40, 253, 1440, 713) rect2:(40, 253, 1440, 713)
# title:sina_Market-DurationUp.py
# target rect1:(91, 149, 1491, 609) rect2:(91, 149, 1491, 609)

# terminal_positionKey = {'sina_Market-DurationDn.py': '8, 801',
#                         'sina_Market-DurationCXDN.py': '79, 734',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '451, 703',
#                         'sina_Monitor-Market-LH.py': '666, 338',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '205, 659',
#                         'singleAnalyseUtil.py': '328, 594',
#                         'LinePower.py': '6, 216', 
#                         'sina_Market-DurationDnUP.py': '6, 434,1400,440' ,}

# terminal_positionKey_all = {'sina_Market-DurationDn.py': '654, 680',
#                         'sina_Market-DurationCXDN.py': '-16, 54',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '-22, 89',
#                         'sina_Monitor-Market-LH.py': '666, 338',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '28, 23',
#                         'singleAnalyseUtil.py': '1095, 23',
#                         'LinePower.py': '6, 216',
#                         'sina_Market-DurationDnUP.py': '6, 434,1400,440' ,}


# terminal_positionKeyMac2021_OLD = {'sina_Market-DurationDn.py': '186, 506',
#                         'sina_Market-DurationCXDN.py': '39, 126',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '0, 394',
#                         'sina_Monitor-Market-LH.py': '184, 239',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '116, 58',
#                         'singleAnalyseUtil.py': '594, 23',
#                         'LinePower.py': '6, 216', }

terminal_positionKeyMac2021 = {'sina_Market-DurationDn.py': '541, 530',
                        'sina_Market-DurationCXDN.py': '0, 194',
                        'sina_Market-DurationSH.py': '-29, 623',
                        'sina_Monitor-Market-LH.py': '184, 239',
                        'sina_Market-DurationUP.py': '-13, 406',
                        'sina_Market-DurationDnUP.py' :'171, 361',
                        'sina_Monitor-Market.py': '19, 179',
                        'sina_Monitor.py': '60, 53',
                        'instock_Monitor.py':'18, 119',
                        'singleAnalyseUtil.py': '630, 23',
                        'LinePower.py': '1, 216', }

"""
('sina_Market-DurationDn.py', '541, 530\n')
('sina_Monitor.py', '213, 46\n')
('singleAnalyseUtil.py', '630, 23\n')
('sina_Market-DurationCXDN.py', '-30, 85\n')
('sina_Market-DurationUp.py', '-21, 418\n')
('sina_Market-DurationUp.py', '-21, 418\n')

"""

# terminal_positionKeyMac = {'sina_Market-DurationDn.py': '216, 490',
#                         'sina_Market-DurationCXDN.py': '-16, 54',
#                         'sina_Market-DurationSH.py': '-29, 623',
#                         'sina_Market-DurationUp.py': '-22, 89',
#                         'sina_Monitor-Market-LH.py': '184, 239',
#                         'sina_Monitor-Market.py': '19, 179',
#                         'sina_Monitor.py': '28, 23',
#                         'singleAnalyseUtil.py': '594, 23',
#                         'LinePower.py': '6, 216', }

terminal_positionKey_VM = {'sina_Market-DurationDn.py': '342, 397',
                        'sina_Market-DurationCXDN.py': '84, 222',
                        'sina_Market-DurationSH.py': '-29, 623',
                        'sina_Market-DurationUp.py': '-12, 383',
                        'sina_Monitor-Market-LH.py': '666, 338',
                        'sina_Monitor-Market.py': '19, 179',
                        'sina_Monitor.py': '8, 30',
                        'singleAnalyseUtil.py': '615, 23',
                        'LinePower.py': '6, 216', }

# terminal_positionKey_triton = {'sina_Market-DurationDn.py': '47, 410, 1400, 460',
#                         'sina_Market-DurationCXDN.py': '23, 634,1400,460',
#                         'sina_Market-DurationSH.py': '-29, 623,1400,460',
#                         'sina_Market-DurationUp.py': '330, 464,1400,460',
#                         'sina_Monitor-Market-LH.py': '603, 501, 1400, 420',
#                         'sina_Monitor-Market.py': '19, 179,1400,460',
#                         'sina_Monitor.py': '87, 489,1400,460',
#                         'singleAnalyseUtil.py': '1074, 694,880,360',
#                         'LinePower.py': '1031, 682,800,420',
#                         'instock_Monitor.py':'24, 260,1360,440',}




def get_system_postionKey():
    basedir = get_now_basedir()
    import socket
    hostname = socket.gethostname() 
        # monitors = monitors if len(monitors) > 0 else False
        
    if basedir.find('vm') >= 0:
        positionKey = terminal_positionKey_VM
    elif get_os_system() == 'mac':
        positionKey = terminal_positionKeyMac2021
        # positionKey = cct.terminal_positionKeyMac
    else:
        positionKey = terminal_positionKey4K
        # positionKey = cct.terminal_positionKey1K_triton
    if not isMac():
        if hostname.find('R900') >=0:
            positionKey = terminal_positionKey2K_R9000P
        else:
            ScreenHeight,ScreenWidth = get_screen_resolution()
            if ScreenWidth == '3840':
                positionKey = terminal_positionKey4K
            else:
                positionKey = terminal_positionKey1K_triton

    return positionKey


    
# terminal_positionKey = terminal_positionKey_VM

script_set_position = '''tell application "Terminal"
    --activate
    %s position of window %s to {%s}
end tell
'''

closeterminalw = '''osascript -e 'tell application "Terminal" to close windows %s' '''

scriptquit = '''tell application "Python Launcher" to quit'''


def get_terminal_Position(cmd=None, position=None, close=False, retry=False):
    """[summary]

    [description]

    Keyword Arguments:
        cmd {[type]} -- [description] (default: {None})
        position {[type]} -- [description] (default: {None})
        close {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """

    if (GlobalValues().getkey('Position') is not None ):
        log.info("Position:%s"%(GlobalValues().getkey('Position')))
        # log.info("Position is locate")
        return 0
    # else:
    #     GlobalValues().setkey('Position',1)

    win_count = 0
    if get_os_system() == 'mac':
        def cct_doScript(scriptn):
            proc = subprocess.Popen(['osascript', '-'],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            stdout_output = proc.communicate(scriptn.encode('utf8'))[0]
            # print stdout_output, type(proc)
            return stdout_output.decode('utf-8')

        if cmd is not None and cmd.find("Python Launcher") >= 0:
            cct_doScript(cmd)
            return win_count

        count = cct_doScript(scriptcount)
        if position is None:
            close_list = []
            if int(count) > 0 and cmd is not None:
                log.info("count:%s" % (count))
                for n in range(1, int(count) + 1):
                    title = cct_doScript(scriptname % ('get', str(object=n)))
                    # log.info("count n:%s title:%s" % (n, title))

                    if title.lower().find(cmd.lower()) >= 0:

                        log.info("WinFind:%s get_title:%s " % (n, title))
                        win_count += 1
                        # print "get:%s"%(n)
                        # position=cct_doScript(script_get_position % ('get', str(n)))
                        if close:
                            close_list.append(n)
                            log.info("close:%s %s" % (n, cmd))
                            # os.system(closeterminalw % (n))
                            # break
                    else:
                        if close:
                            log.info("Title notFind:%s title:%s Cmd:%s" % (n, title.replace('\n', ''), cmd.lower()))
            if len(close_list) > 0:
                if not retry and len(close_list) > 1:
                    sleep(5)
                    get_terminal_Position(cmd=cmd, position=position, close=close, retry=True)
                else:
                    for n in close_list:
                        os.system(closeterminalw % (close_list[0]))
                        log.error("close:%s %s" % (n, cmd))

        else:
            # sleep(1, catch=True)
            position = position.split(os.sep)[-1]
            log.info("position Argv:%s" % (position))
            positionKey = get_system_postionKey()
            if int(count) > 0:
                if position in list(positionKey.keys()):
                    log.info("count:%s" % (count))
                    for n in range(1, int(count) + 1):
                        title = cct_doScript(scriptname % ('get', str(object=n)))
                        if title.lower().find(position.lower()) >= 0:
                            log.info("title find:%s po:%s" % (title, positionKey[position]))
                            position = cct_doScript(script_set_position % ('set', str(n), positionKey[position]))
                            break
                        else:
                            log.info("title not find:%s po:%s" % (title, position))
                else:
                    log.info("Keys not position:%s" % (position))
    return win_count

# get_terminal_Position(cmd=scriptquit, position=None, close=False)
# get_terminal_Position('Johnson — -bash', close=True)
log.info("close Python Launcher")


# from numba.decorators import autojit


def run_numba(func):
    funct = autojit(lambda: func)
    return funct


def get_work_path(base, dpath, fname):

    # baser = os.getcwd().split(base)[0]
    baser = getcwd().split(base)[0]
    base = baser + base + path_sep + dpath + path_sep
    filepath = base + fname
    return filepath


def get_rzrq_code(market='all'):

    baser = getcwd().split('stock')[0]
    base = baser + 'stock' + path_sep + 'JohnsonUtil' + path_sep
    szrz = base + 'szrzrq.csv'
    shrz = base + 'shrzrq.csv'
    if market in ['all', 'sz', 'sh']:
        dfsz = pd.read_csv(szrz, dtype={'code': str}, encoding='gbk')
        if market == 'sz':
            return dfsz
        dfsh = pd.read_csv(shrz, dtype={'code': str}, encoding='gbk')
        dfsh = dfsh.loc[:, ['code', 'name']]
        if market == 'sh':
            return dfsh
        dd = pd.concat([dfsz,dfsh], ignore_index=True)
    elif market == 'cx':
        cxzx = base + 'cxgzx.csv'
        dfot = pd.read_csv(cxzx, dtype={'code': str}, sep='\t', encoding='gbk')
        dd = dfot.loc[:, ['code', 'name']]
    else:
        cxzx = base + market + '.csv'
        dfot = pd.read_csv(cxzx, dtype={'code': str}, sep='\t', encoding='gbk')
        dd = dfot.loc[:, ['code', 'name']]
    print("rz:%s" % (len(dd)), end=' ')
    return dd


def get_tushare_market(market='zxb', renew=False, days=5):
    def tusharewrite_to_csv(market, filename, days):
        import tushare as ts
        if market == 'zxb':
            df = ts.get_sme_classified()
        elif market == 'captops':
            df = ts.cap_tops(days).loc[:, ['code', 'name']]
            if days != 10:
                initda = days * 2
                df2 = ts.inst_tops(initda).loc[:, ['code', 'name']]
                df = pd.concat([df,df2])
                df.drop_duplicates('code', inplace=True)
        else:
            log.warn('market not found')
            return pd.DataFrame()
        if len(df) > 0:
            df = df.set_index('code')
        else:
            log.warn("get error")
        df.to_csv(filename, encoding='gbk')
        log.warn("update %s :%s" % (market, len(df))),
        df.reset_index(inplace=True)
        return df

    baser = getcwd().split('stock')[0]
    base = baser + 'stock' + path_sep + 'JohnsonUtil' + path_sep
    filepath = base + market + '.csv'
    if os.path.exists(filepath):
        if renew and creation_date_duration(filepath) > 0:
            df = tusharewrite_to_csv(market, filepath, days)
        else:
            df = pd.read_csv(filepath, dtype={'code': str}, encoding='gbk')
            # df = pd.read_csv(filepath,dtype={'code':str})
            if len(df) == 0:
                df = tusharewrite_to_csv(market, filepath, days)
    else:
        df = tusharewrite_to_csv(market, filepath, days)

    return df

sina_doc = """sina_Johnson.

Usage:
  sina_xxx.py
  sina_xxx.py [-d <debug>]

Options:
  -h --help     Show this screen.
  -d <debug>    [default: error].
"""

sina_doc_old = """sina_Johnson.

Usage:
  sina_cxdn.py
  sina_cxdn.py --debug
  sina_cxdn.py --de <debug>

Options:
  -h --help     Show this screen.
  --debug       Debug [default: error].
  --de=<debug>    [default: error].
"""
# --info    info [default:False].


def sys_default_utf8(default_encoding='utf-8'):
    #import sys
    #    default_encoding = 'utf-8'
    if sys.getdefaultencoding() != default_encoding:
        importlib.reload(sys)
        sys.setdefaultencoding(default_encoding)

sys_default_utf8()


def get_tdx_dir_blocknew():
    blocknew_path = get_tdx_dir() + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep)
    return blocknew_path

def get_tdx_dir_blocknew_dxzq(block_path):

    blocknew_path = get_tdx_dir_blocknew()
    if block_path.find(blocknew_path) > -1:
        blkname = block_path.split('\\')[-1]
        blocknew_path = win10dxzq + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep) + blkname
    else:
        log.error("not find blkname{block_path}")
    return blocknew_path



def get_screen_resolution():
    proc = subprocess.Popen(['powershell', 'Get-WmiObject win32_desktopmonitor;'], stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    res = proc.communicate()
    # monitorsName = re.findall('(?s)\r\nName\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorsName = re.findall('\r\nName\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorScreenWidth = re.findall('\r\nScreenWidth\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # monitorScreenHeight = re.findall('\r\nScreenHeight\s+:\s(.*?)\r\n', res[0].decode("gbk"))
    # for screenWidth in monitorScreenWidth:
    #     # if screenWidth == '3840':
    #     if isDigit(screenWidth):
    #         return screenWidth
    # return 0
    
    # if len(res) > 10:
    #     ScreenHeight,ScreenWidth = re.findall('\r\nScreenHeight\s+:\s(.*?)\r\nScreenWidth\s+:\s(.*?)\r\n', res[0].decode("gbk"))[-1]
    # else:
    if len(res) > 10:
        ScreenHeight, ScreenWidth = re.findall(
            r'\r\nScreenHeight\s+:\s(.*?)\r\nScreenWidth\s+:\s(.*?)\r\n',
            res[0].decode("gbk")
        )[-1]
    else:
        ScreenHeight,ScreenWidth = '1080','1920'
    return ScreenHeight,ScreenWidth 


def check_chinese(checkstr):
    status = re.match('[ \\u4e00 -\\u9fa5]+', checkstr) == None
    return status
# def whichEncode(text):
#   text0 = text[0]
#   try:
#     text0.decode('utf8')
#   except Exception, e:
#     if "unexpected end of data" in str(e):
#       return "utf8"
#     elif "invalid start byte" in str(e):
#       return "gbk_gb2312"
#     elif "ascii" in str(e):
#       return "Unicode"
#   return "utf8"



from chardet import detect
# get file encoding type
def get_encoding_type(file):
    with open(file, 'rb') as f:
        rawdata = f.read()
    return detect(rawdata)['encoding']

# open(current_file, 'r', encoding = get_encoding_type, errors='ignore')
# str = unicode(str, errors='replace')
# or
# str = unicode(str, errors='ignore')

# I had same problem with UnicodeDecodeError and i solved it with this line.
# Don't know if is the best way but it worked for me.
# str = str.decode('unicode_escape').encode('utf-8')




def getCoding(strInput):
    '''
    获取编码格式
    '''
    if isinstance(strInput, str):
        return "unicode"
    try:
        strInput.decode("utf8")
        return 'utf8'
    except:
        pass
    try:
        strInput.decode("gbk")
        return 'gbk'
    except:
        pass
    try:
        strInput.decode("utf16")
        return 'utf16'
    except:
        pass


def tran2UTF8(strInput):
    '''
    转化为utf8格式
    '''
    strCodingFmt = getCoding(strInput)
    if strCodingFmt == "utf8":
        return strInput
    elif strCodingFmt == "unicode":
        return strInput.encode("utf8")
    elif strCodingFmt == "gbk":
        return strInput.decode("gbk").encode("utf8")


def tran2GBK(strInput):
    '''
    转化为gbk格式
    '''
    strCodingFmt = getCoding(strInput)
    if strCodingFmt == "gbk":
        return strInput
    elif strCodingFmt == "unicode":
        return strInput.encode("gbk")
    elif strCodingFmt == "utf8":
        return strInput.decode("utf8").encode("gbk")

def get_file_size(path_to_file):
    # filesize = os.path.getsize(path_to_file) / 1000 / 1000
    if os.path.exists(path_to_file):
        filesize = os.path.getsize(path_to_file)
    else:
        filesize = 0
    return filesize





def creation_date_duration(path_to_file: str) -> int:
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if os.path.exists(path_to_file):
        dt = os.path.getmtime(path_to_file)
        dtm = datetime.date.fromtimestamp(dt)
        today = datetime.date.today()
        duration: int = (today - dtm).days
    else:
        duration = 0
    return duration

def filepath_datetime(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    # if platform.system() == 'Windows':
    #     return os.path.getctime(path_to_file)
    # else:
    #     stat = os.stat(path_to_file)
    #     try:
    #         return stat.st_birthtime
    #     except AttributeError:
    #         # We're probably on Linux. No easy way to get creation dates here,
    #         # so we'll settle for when its content was last modified.
    #         return stat.st_mtime
    if os.path.exists(path_to_file):
        dt = os.path.getmtime(path_to_file)
        dtm = datetime.date.fromtimestamp(dt)
    else:
        dtm = datetime.datetime.now().timestamp()
    return dtm


if not isMac():
    import win32api,win32gui
import _thread

def get_window_pos(targetTitle):  
    hWndList = []  
    win32gui.EnumWindows(lambda hWnd, param: param.append(hWnd), hWndList)  
    for hwnd in hWndList:
        clsname = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd)
        if (title.find(targetTitle) >= 0):    #调整目标窗口到坐标(600,300),大小设置为(600,600)
            rect1 = win32gui.GetWindowRect(hwnd)
            # rect2 = get_window_rect(hwnd)
            # rect2 = rect1
            # print("targetTitle:%s rect1:%s rect2:%s"%(title,rect1,rect1))
            print(("target rect1:%s rect2:%s"%(rect1,rect1)))
            # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
            # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
            # win32gui.MoveWindow(hwnd,1026, 699, 900, 360,True)  #108,19

def reset_window_pos(targetTitle,posx=1026,posy=699,width=900,height=360,classsname='ConsoleWindowClass'):

    hWndList = []  
    win32gui.EnumWindows(lambda hWnd, param: param.append(hWnd), hWndList)
    status=0  
    # time.sleep(0.2)
    try:
        for hwnd in hWndList:
            clsname = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            # log.error("title:%s"%(title))
            if (clsname == classsname  and title.find(targetTitle) == 0):    #调整目标窗口到坐标(600,300),大小设置为(600,600)
                rect1 = win32gui.GetWindowRect(hwnd)
                # rect2 = get_window_rect(hwnd)
                # log.debug("targetTitle:%s rect1:%s rect2:%s"%(title,rect1,rect1))
                # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
                # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 330,678,600,600, win32con.SWP_SHOWWINDOW)
                win32gui.MoveWindow(hwnd,int(posx), int(posy), int(width), int(height),True)  #108,19
                status +=1

    except Exception as e:
        print(f'Exception:{e}')
    finally:
        pass

def set_ctrl_handler():
    # os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'
    # def doSaneThing(sig, func=None):
    # '''忽略所有KeyCtrl'''
    # return True
    # win32api.SetConsoleCtrlHandler(doSaneThing, 1)

    def handler(dwCtrlType, hook_sigint=_thread.interrupt_main):
        print(("ctrl:%s" % (dwCtrlType)))
        if dwCtrlType == 0:  # CTRL_C_EVENT
            # hook_sigint()
            # raise KeyboardInterrupt("CTRL-C!")
            return 1  # don't chain to the next handler
        return 0  # chain to the next handler
    win32api.SetConsoleCtrlHandler(handler, 1)

def set_clear_logtime(time_t=1):
    h5_fname = 'sina_MultiIndex_data'
    h5_table = 'all' + '_' + str(sina_limit_time)
    fname = 'sina_logtime'
    logtime = get_config_value_ramfile(fname)
    write_t = get_config_value_ramfile(fname,currvalue=time_t,xtype='time',update=True)


#将字典里的键全部由大写转换为小写
def capital_to_lower(dict_info):
    new_dict = {}
    for i, j in list(dict_info.items()):
        new_dict[i.lower()] = j
    return new_dict

    # before_dict = {'ABC': 'python', 'DEF': 'java', 'GHI': 'c', 'JKL': 'go'}
    # print capital_to_lower(before_dict)

#将字典里的键全部由小写转换为大写

def lower_to_capital(dict_info):
    new_dict = {}
    for i, j in list(dict_info.items()):
        new_dict[i.upper()] = j
    return new_dict


def set_console(width=80, height=15, color=3, title=None, closeTerminal=True):
    # mode con cp select=936
    # os.system("mode con: cols=%s lines=%s"%(width,height))
    # print os.path.splitext(sys.argv[0])
    if title is None:
        # title= (os.path.basename(sys.argv[0]))
        filename = (os.path.basename(sys.argv[0]))
        log.debug(f'filename:{filename}')
    elif isinstance(title, list):
        filename = (os.path.basename(sys.argv[0]))
        for cname in title:
            # print cname
            filename = filename + ' ' + str(cname)
            log.debug(f'filename:{filename}')
            # print filename
    else:
        filename = (os.path.basename(sys.argv[0])) + ' ' + title
        log.debug(f'filename:{filename}')

    if isMac():
        # os.system('printf "\033]0;%s\007"'%(filename))
        if title is None:
            # os.system('printf "\e[8;%s;%st"' % (height, width))
            os.system(r'printf "\e[8;%s;%st"' % (height, width))
        # printf "\033]0;%s sin ZL: 356.8 To:183 D:3 Sh: 1.73%  Vr:3282.4-3339.7-2.6%  MR: 4.3 ZL: 356.8\007"
        filename = filename.replace('%', '!')
        os.system('printf "\033]0;%s\007"' % (filename))
    else:
        # os.system('title=%s' % sys.argv[0])
        os.system('title=%s' % filename)
        log.debug(f'filename:{filename}')
        # win32MoveCom.reset_window_pos(title,width=width,height=height)
        # os.system("mode con cols=%s lines=25"%(width))   #windowsfg
        # os.system("mode con cols=%s lines=%s"%(width,height))   #windowsfg
        # os.system("mode con cols=120 lines=2000"%(width,height))   #windowsfg
        # os.system('mode %s,%s'%(width,height))
    # printf "\033]0;My Window title\007”
    # os.system('color %s'%color)
    # set_ctrl_handler()

    # if (GlobalValues().getkey('Position') is not None ):
    #     print("Position:%s"%(cct.GlobalValues().getkey('Position')))
    #     log.info("Position is locate")
    #     return 0
    # else:
    #     GlobalValues().setkey('Position',1)

    if closeTerminal and (GlobalValues().getkey('Position') is None):
        GlobalValues().setkey('Position',1)

        # get_terminal_Position(cmd=scriptquit, position=None, close=False)
        if isMac():
            get_terminal_Position(position=filename)
        else:
            
            title= (os.path.basename(sys.argv[0]))
            positionKey=capital_to_lower(get_system_postionKey())
            # positionKey=capital_to_lower(terminal_positionKey1K_triton)
            log.debug(f'positionKey:{positionKey}')
            if title.lower() in list(positionKey.keys()) or title.replace('exe','py').lower() in list(positionKey.keys()):
                # log.error("title.lower() in positionKey.keys()")
                log.debug(f'title:{title.lower()}')
                if title.lower() in list(positionKey.keys()) or title.replace('exe','py').lower() in list(positionKey.keys()):
                    if title.find('.exe') >=0:
                        pos=positionKey[title.replace('exe','py').lower()].split(',')
                    else:
                        pos=positionKey[title.lower()].split(',') 
                else:
                    pos= '254, 674,1400,420'.split(',')
                    log.error("pos is none")
                log.info("pos:%s title:%s Position:%s"%(pos,title,GlobalValues().getkey('Position')))
                # cct.get_window_pos('sina_Market-DurationUp.py')
                # cct.reset_window_pos(key,pos[0],pos[1],pos[2],pos[3])

                status=reset_window_pos(title,pos[0],pos[1],pos[2],pos[3])
                log.debug("reset_window_pos-status:%s"%(status))
            else:
                log.error("%s not in terminal_positionKey_triton"%(title))
        # (os.path.basename(sys.argv[0]))
        # get_terminal_Position(clean_terminal[1], close=True)
    # else:
        # log.error("closeTerminal:%s title:%s Position:%s"%(closeTerminal,title,GlobalValues().getkey('Position')))

def timeit_time(cmd, num=5):
    import timeit
    time_it = timeit.timeit(lambda: (cmd), number=num)
    print(("timeit:%s" % time_it))


def get_delay_time():
    delay_time = 8000
    return delay_time


def cct_raw_input(sts):
    # print sts
    if sys.getrecursionlimit() < 2000:
        sys.setrecursionlimit(2000)
    if GlobalValues().getkey('Except_count') is None:
        GlobalValues().setkey('Except_count', 0)
        log.info("recursionlimit:%s"%(sys.getrecursionlimit()))

    st = ''
    time_s = time.time()
    count_Except = GlobalValues().getkey('Except_count')
    try:
        # if get_os_system().find('win') >= 0:
            # win_unicode_console.disable()
        # https://stackoverflow.com/questions/11068581/python-raw-input-odd-behavior-with-accents-containing-strings
        # st = win_unicode_console.raw_input.raw_input(sts)
        st = input(sts)
        # issubclass(KeyboardInterrupt, BaseException)
    # except (KeyboardInterrupt, BaseException) as e:
    except (KeyboardInterrupt, BaseException) as e:
        # inputerr = cct_raw_input(" Break: ")
        # if inputerr == 'e' or inputerr == 'q':
        #     sys.exit(0)
        # # raise Exception('raw interrupt')
        # if inputerr is not None and len(inputerr) > 0:
        #     return inputerr
        # else:
        #     return ''
        # count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            count_Except = count_Except + 1
            GlobalValues().setkey('Except_count', count_Except)
            # sys.exit()
            # print "cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except)
            # st = cct_raw_input(sts)
        else:
            # print "cct_ExceptionError:%s count:%s" % (e, count_Except)
            log.error("count_Except > 2")
            GlobalValues().setkey('Except_count', 0)
            # if get_os_system().find('win') >= 0:
            #     win_unicode_console.enable(use_readline_hook=False)
            # raise KeyboardInterrupt()
            sys.exit()

    except (IOError, EOFError, Exception) as e:
        # count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            count_Except = count_Except + 1
            GlobalValues().setkey('Except_count', count_Except)
            # sys.exit()
            # print "cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except)
            # st = cct_raw_input(sts)
        else:
            print("cct_ExceptionError:%s count:%s" % (e, count_Except))
            log.error("cct_ExceptionError:%s count:%s" % (e, count_Except))
            sys.exit()
    # except ValueError as e:
    #     raise Exception('Invalid Exception: {}'.format(e)) from None
    # if get_os_system().find('win') >= 0:
        # win_unicode_console.enable(use_readline_hook=False)
    t1 = time.time() - time_s
    if t1 < 0.2 and count_Except is not None and count_Except < 3:
        time.sleep(0.2)
        count_Except = count_Except + 1
        GlobalValues().setkey('Except_count', count_Except)
        st = 'no Input'
    time.sleep(0.1)
    return st.strip()

# eval_rule = "[elem for elem in dir() if not elem.startswith('_') and not elem.startswith('ti')]"
# eval_rule = "[elem for elem in dir() if not elem.startswith('_')]"
eval_rule = "[elem for elem in dir() if elem.startswith('top') or elem.startswith('block') or elem.startswith('du') ]"



#MacOS arrow keys history auto complete
if isMac():
    import readline
    import rlcompleter, readline
    # readline.set_completer(completer.complete)
    readline.parse_and_bind('tab:complete')


class MyCompleter(object):  # Custom completer

    def __init__(self, options):
        self.options = sorted(options)

    def complete(self, text, state):
        if state == 0:  # on first trigger, build possible matches
            if text:  # cache matches (entries that start with entered text)
                # self.matches = [s for s in self.options
                #                     if s and s.startswith(text)]
                self.matches = [s for s in self.options
                                if text in s]
            else:  # no text entered, all matches possible
                self.matches = self.options[:]

        # return match indexed by state
        try:
            return self.matches[state]
        except IndexError:
            return None


def cct_eval(cmd):
    try:
        st = eval(cmd)
    except (Exception) as e:
        st = ''
        print(e)
    return st

GlobalValues().setkey('Except_count', 0)

def custom_sleep(sleep=5):

    time_set = sleep  # 计时设定时间
    SYSJ = None  # 剩余时间
    start_time = time.time()
    while True:
        t1 = time.time() - start_time  # 计时时间间隔
        SYSJ = time_set - t1  # 剩余时间
        # print("t1:%s du:%s"%(t1,SYSJ))
        # m, s = divmod(SYSJ, 60)  # 获取分， 秒
        # h, m = divmod(m, 60)  # 获取小时，分
        if SYSJ > 0:
            pass
            # print("%02d:%02d:%02d" % (h, m, s))  #正常打印
            # print("\r%02d:%02d:%02d" % (h, m, s),end="")  # 每次把光标定位到行首，打印
        else:
            # print(u"\n计时结束")
            break
    # print "start:%s"%(time.time()-start_time)
# custom_sleep(0.5)

def sleep(timet, catch=True):
    times = time.time()
    log.info('sleep:%s'%(timet))
    loop_status = 1
    try:
        # log.info("range(int(timet) * 2):%s"%(range(int(timet) * 2)))
        # for _ in range(int(timet) * 2):
        count_s = 0
        while loop_status:
            loop_status = 0
            time.sleep(0.2)
            # custom_sleep(0.5)
            t1 = time.time() - times
            duration = t1 - timet
            if duration >= 0 :
                break
            else:
                count_s +=1
                loop_status = 1
                # if count_s%10 == 0:
                #     log.info("sleep10:%s"%(int(time.time() - times) - int(timet))) 
            # log.info('sleeptime:%s'%(int(time.time() - times)))
        log.info('break sleeptime:%s'%(int(time.time() - times)))
    except (KeyboardInterrupt) as e:
        # raise KeyboardInterrupt("CTRL-C!")
        # print "Catch KeyboardInterrupt"
        if catch:
            raise KeyboardInterrupt("Sleep Time")
        else:
            print("KeyboardInterrupt Sleep Time")

    except (IOError, EOFError, Exception) as e:
        count_Except = GlobalValues().getkey('Except_count')
        if count_Except is not None and count_Except < 3:
            GlobalValues().setkey('Except_count', count_Except + 1)
            print("cct_raw_input:ExceptionError:%s count:%s" % (e, count_Except))
        else:
            print("cct_ExceptionError:%s count:%s" % (e, count_Except))
            # sys.exit(0)

    finally:
        log.info('cct_Exception finally loop_status:%s'%(loop_status))
        # raise Exception("code is None")
    # print time.time()-times


def sleeprandom(timet):
    now_t = get_now_time_int()
    if now_t > 915 and now_t < 926:
        sleeptime = random.randint(int(10 / 3), 5)
    else:
        sleeptime = random.randint(int(timet / 3), int(timet))
    if get_work_duration():
        print("Error2sleep:%s" % (sleeptime))
        sleep(sleeptime, False)
    else:
        sleep(sleeptime)


def get_cpu_count():
    return cpu_count()



def day8_to_day10(start, sep='-'):
    if start:
        start = str(start)
        if len(start) == 8:
            if start.find(':') < 0:
                start = start[:4] + sep + start[4:6] + sep + start[6:]
    return start


def get_time_to_date(times, format='%H:%M'):
    # time.gmtime(times) 世界时间
    # time.localtime(times) 本地时间
    return time.strftime(format, time.localtime(times))


def get_today(sep: str = '-') -> str:
    TODAY: datetime.date = datetime.date.today()
    fstr: str = "%Y" + sep + "%m" + sep + "%d"
    today: str = TODAY.strftime(fstr)
    return today

    # from dateutil import rrule

    # def workdays(start, end, holidays=0, days_off=None):
    # start=datetime.datetime.strptime(start,'%Y-%m-%d')
    # end=datetime.datetime.strptime(end,'%Y-%m-%d')
    # if days_off is None:
    # days_off = 0, 6
    # workdays = [x for x in range(7) if x not in days_off]
    # print workdays
    # days = rrule.rrule(rrule.DAILY, start, until=end, byweekday=workdays)
    # return days
    # return days.count() - holidays


def get_work_day_status() -> bool:
    today = datetime.datetime.today().date()
    day_n = int(today.strftime("%w"))

    if day_n > 0 and day_n < 6:
        return True
    else:
        return False
    # return str(today)
def get_work_day_idx() -> int:
    today = datetime.datetime.today().date()
    day_n: int = int(today.strftime("%w"))
    # if 0 < day_n < 6:
    #     return day_n
    # else:
    #     return 5
    return day_n

    # # today = datetime.datetime.today().date() + datetime.timedelta(-days)
    # if days is None:
    #     return days
    # dt = GlobalValues().getkey(f'last_tddate-{days}')
    # if dt is None:
    #     today = datetime.date.today()
    #     if days == 1:
    #     # dt = today + datetime.timedelta(days-1)
    #         dt = today.strftime('%Y-%m-%d')
    #         dt = get_last_trade_date(dt)
    #         GlobalValues().setkey(f'last_tddate-{days}',dt)
    #         log.debug(f'setkey:last_tddate-{days} : {dt}')
    #     else:
    #         # dt = (today + datetime.timedelta(-(days-1))).strftime('%Y-%m-%d')
    #         # # dt = datetime.date.today().strftime('%Y-%m-%d')
    #         # dt = get_last_trade_date(dt)
    #         dt = get_lastdays_trade_date(days)
    #         GlobalValues().setkey(f'last_tddate-{days}',dt)
    #         log.debug(f'setkey:last_tddate-{days} : {dt}')
    
def last_tddate(days=1):
    return get_lastdays_trade_date(days)

# def last_tddate(days=1):
#     # today = datetime.datetime.today().date() + datetime.timedelta(-days)
#     if days is None:
#         return days
#     today = datetime.datetime.today().date()
#     log.debug("today:%s " % (today))
#     # return str(today)

#     def get_work_day(today):
#         day_n = int(today.strftime("%w"))
#         if day_n == 0:
#             lastd = today + datetime.timedelta(-2)
#             log.debug("0:%s" % lastd)
#         elif day_n == 1:
#             lastd = today + datetime.timedelta(-3)
#             log.debug("1:%s" % lastd)
#         else:
#             lastd = today + datetime.timedelta(-1)
#             log.debug("2-6:%s" % lastd)
#         # is_trade_date()
#         return lastd
#         # if days==0:
#         # return str(lasd)
#     lastday = today
#     for x in range(int(days)):
#         # print x
#         lastday = get_work_day(today)
#         today = lastday
#     return str(lastday)

'''
oday = lasd - datetime.timedelta(days)
day_n = int(oday.strftime("%w"))
# print oday,day_n
if day_n == 0:
    # print day_last_week(-2)
    return str(datetime.datetime.today().date() + datetime.timedelta(-2))
elif day_n == 6:
    return str(datetime.datetime.today().date() + datetime.timedelta(-1))
else:
    return str(oday)
'''

# def is_holiday(date):
#     if isinstance(date, str):
#         date = datetime.datetime.strptime(date, '%Y-%m-%d')
#     today=int(date.strftime("%w"))
#     if today > 0 and today < 6 and date not in holiday:
#         return False
#     else:
#         return True


def day_last_days(daynow,last=-1):
    return str(datetime.datetime.strptime(daynow, '%Y-%m-%d').date() + datetime.timedelta(last))

def day_last_week(days=-7):
    lasty = datetime.datetime.today().date() + datetime.timedelta(days)
    return str(lasty)


def is_holiday(date):
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, '%Y-%m-%d')
    today = int(date.strftime("%w"))
    if today > 0 and today < 6 and date not in holiday:
        return False
    else:
        return True


def testdf(df):
    if df is not None and len(df) > 0:
        pass
    else:
        pass


def testdf2(df):
    if df is not None and not df.empty:
        pass
    else:
        pass

def parse_date_safe(date_str):
    if not date_str:
        return None

    if isinstance(date_str, int):
        date_str = str(date_str)

    date_str = str(date_str).strip().replace("/", "-")

    fmts = ("%Y-%m-%d", "%Y%m%d")

    for fmt in fmts:
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"无法识别的日期格式: {date_str}")

def get_trade_day_distance(datastr, endday=None):
    """
    交易日“间隔数”
    上一个交易日 -> 今天 = 1
    """
    if not datastr:
        return None

    datastr = str(datastr)
    if len(datastr) < 8:
        return None

    start = parse_date_safe(datastr)
    if start is None:
        return None

    if endday:
        end = parse_date_safe(day8_to_day10(endday))
    else:
        end = parse_date_safe(get_today())

    if start >= end:
        return 0

    cnt = a_trade_calendar.get_trade_count(
        start.strftime('%Y-%m-%d'),
        end.strftime('%Y-%m-%d')
    )

    # 关键：点位数 → 间隔数
    return max(cnt - 1, 0)



def get_today_duration(datastr, endday=None, tdx=False):
    """
    计算 datastr 到参考日期的自然日差

    datastr : str | int
        支持 YYYYMMDD / YYYY-MM-DD
    endday : str | None
        指定结束日期（YYYYMMDD / YYYY-MM-DD）
    tdx : bool
        是否启用 TDX 行情未收盘规则
    """
    if datastr is None:
        return None

    datastr = str(datastr)
    if len(datastr) < 8:
        return None

    # 起始日期
    last_day = parse_date_safe(datastr)
    if last_day is None:
        return None

    # 结束日期
    if endday:
        today = parse_date_safe(day8_to_day10(endday))
    else:
        today = datetime.date.today()

        if tdx:
            is_trade_today = get_day_istrade_date()
            last_trade_date = get_last_trade_date()

            # TDX：未收盘 or 非交易日，且 datastr 是最近交易日
            if datastr == last_trade_date:
                if (is_trade_today and get_now_time_int() < 1500) or not is_trade_today:
                    return 0

    return (today - last_day).days


def get_today_duration_old(datastr, endday=None, tdx=False):
    if isinstance(datastr, int):
        datastr = str(datastr)

    if datastr and len(datastr) > 6:

        if endday:
            today = parse_date_safe(day8_to_day10(endday))
        else:
            is_trade_date_today = get_day_istrade_date()
            last_trade_date = get_last_trade_date()

            if tdx and (
                (is_trade_date_today and get_now_time_int() < 1500)
                or not is_trade_date_today
            ) and datastr == last_trade_date:
                return 0
            else:
                today = datetime.date.today()

        # ✅ 统一用安全解析
        last_day = parse_date_safe(datastr)

        duration_day = int((today - last_day).days)

    else:
        duration_day = None

    return duration_day


# def get_today_duration(datastr, endday=None,tdx=False):
#     if isinstance(datastr, int):
#         datastr = str(datastr)
#     if datastr is not None and len(datastr) > 6:
#         if endday:
#             today = datetime.datetime.strptime(day8_to_day10(endday), '%Y-%m-%d').date()
#         else:
#             is_trade_date_today = get_day_istrade_date()
#             last_trade_date = get_last_trade_date()
#             if tdx and ((is_trade_date_today and get_now_time_int() < 1500) or not is_trade_date_today) and datastr == last_trade_date:
#                 return 0 
#                 # today = last_trade_date
#             else:
#                 today = datetime.date.today()
#         # if get_os_system() == 'mac':
#         #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
#         #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
#         # else:
#         #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
#         #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
#         last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        
#         duration_day = int((today - last_day).days)
#     else:
#         duration_day = None
#     return (duration_day)


def get_now_time():
    # now = time.time()
    # now = time.localtime()
    # # d_time=time.strftime("%Y-%m-%d %H:%M:%S",now)
    # d_time = time.strftime("%H:%M", now)
    d_time = datetime.datetime.now().strftime("%H:%M")

    return d_time


def get_now_time_int() -> int:
    now_t: str = datetime.datetime.now().strftime("%H%M")
    return int(now_t)

def str2bool(s):
    return str(s).lower() in ("true", "1", "yes")

def get_work_time(now_t: Optional[int] = None) -> bool:
    if not get_trade_date_status():
        return False
    if now_t is None:
        now_t = get_now_time_int()
    if not get_work_day_status():
        return False
    if (now_t > 1132 and now_t < 1300) or now_t < 915 or now_t > 1502:
        return False
    else:
        return True
        return True

def get_work_time_duration():
    if not get_trade_date_status():
        return False
    now_t = get_now_time_int()
    if  now_t < 915 or now_t > 1502:
        return False
    else:
        return True


def get_work_hdf_status():
    now_t = str(get_now_time()).replace(':', '')
    now_t = int(now_t)
    if not get_work_day_status():
        return False
    # if (now_t > 1130 and now_t < 1300) or now_t < 915 or now_t > 1502:
    if 915 < now_t < 1502:
        # return False
        return True
    return False


def get_work_duration():
    int_time = get_now_time_int()
    # now_t = int(now_t)
    if  get_trade_date_status() and ((700 < int_time < 915) or (1132 < int_time < 1300)):
        # if (int_time > 830 and int_time < 915) or (int_time > 1130 and int_time < 1300) or (int_time > 1500 and int_time < 1510):
        # return False
        return True
    else:
        return False

    # initx = 3.5
    # stepx = 0.5
    # init = 0
    # initAll = 10
    # now = time.localtime()
    # ymd = time.strftime("%Y:%m:%d:", now)
    # hm1 = '09:30'
    # hm2 = '13:00'
    # all_work_time = 14400
    # d1 = datetime.datetime.now()
    # now_t = int(datetime.datetime.now().strftime("%H%M"))
    # # d2 = datetime.datetime.strptime('201510111011','%Y%M%d%H%M')
    # if now_t > 915 and now_t <= 930:
    #     d2 = datetime.datetime.strptime(ymd + '09:29', '%Y:%m:%d:%H:%M')
    #     d1 = datetime.datetime.strptime(ymd + '09:30', '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 1
    #     ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 930 and now_t <= 1000:
    #     d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 1
    #     ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1000 and now_t <= 1030:
    #     d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 2
    #     ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1030 and now_t <= 1100:
    #     d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 3
    #     ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1100 and now_t <= 1130:
    #     d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 4
    #     ratio_t = round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1130 and now_t < 1300:
    #     init += 4
    #     ratio_t = 0.5 / (initx + init * stepx) * initAll
    # elif now_t >= 1500 or now_t < 930:
    #     ratio_t = 1.0
    # elif now_t > 1300 and now_t <= 1330:
    #     d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 5
    #     ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1330 and now_t <= 1400:
    #     d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 6
    #     ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    # elif now_t > 1400 and now_t <= 1430:
    #     d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     init += 7
    #     ratio_t = round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    # else:
    #     d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
    #     ds = float((d1 - d2).seconds)
    #     ratio_t = round((ds + 7200) / all_work_time, 3)


    # if now is None:
    #     now = dt.datetime.now()

def get_work_time_ratio(resample='d'):
    now = datetime.datetime.now()

    # ---------- 交易日判断 ----------
    today = pd.Timestamp(now.date())

    if not is_trade_date(today) == "True":
        # 非交易日 → 回退到最近一个交易日
        today -= pd.tseries.offsets.BDay(1)
        passed_ratio = 1.0
    else:
        # ---------- 日内进度 ----------
        t = now.time()
        minutes = t.hour * 60 + t.minute

        segments = [
            (9*60+30, 10*60, 0.25),
            (10*60, 11*60, 0.50),
            (11*60, 11*60+30, 0.60),
            (13*60, 14*60, 0.78),
            (14*60, 15*60, 1.00),
        ]

        prev_ratio = 0.0
        passed_ratio = 0.0

        for start, end, ratio in segments:
            if minutes <= start:
                passed_ratio = prev_ratio
                break
            elif start < minutes <= end:
                p = (minutes - start) / (end - start)
                passed_ratio = prev_ratio + (ratio - prev_ratio) * p
                break
            prev_ratio = ratio
        else:
            passed_ratio = 1.0

        passed_ratio = max(passed_ratio, 0.05)

    # ---------- resample 处理 ----------
    if resample == 'd':
        return passed_ratio

    # ---------- 周交易日计算 ----------
    start_week = today - pd.Timedelta(days=today.weekday())
    week_days = pd.bdate_range(start_week, today)
    week_idx = len(week_days)        # 今天是第几个交易日
    week_total = 5

    # ---------- 月交易日计算 ----------
    month_start = today.replace(day=1)
    month_all = pd.bdate_range(
        month_start,
        (month_start + pd.offsets.MonthEnd())
    )
    month_idx = len(pd.bdate_range(month_start, today))
    month_total = len(month_all)

    # ---------- 周期比例计算 ----------
    if resample == '3d':
        ratio = ((min(week_idx - 1, 2)) + passed_ratio) / 3

    elif resample == 'w':
        ratio = ((week_idx - 1) + passed_ratio) / week_total

    elif resample == 'm':
        ratio = ((month_idx - 1) + passed_ratio) / month_total

    else:
        ratio = passed_ratio

    return min(max(round(float(ratio),6), 0.01), 1.0)

def get_work_time_ratio_noworkday(resample='d'):
    now = datetime.datetime.now()
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

    ratio_t = passed_ratio
    # work_day = get_work_day_idx() 
    # work_day = work_day-3 if work_day > 2 else work_day
    if resample == '3d':
        ratio_t /= 3 
    elif resample == 'w':
        ratio_t /= 5 
    elif resample == 'm':
        ratio_t /= 20

    return ratio_t


def decode_bytes_type(data):
    if isinstance(data,bytes):
        try:
            data = data.decode('utf8')
        except:
            data = data.decode('gbk')
    return data


    
global ReqErrorCount
ReqErrorCount = 1
def get_url_data_R(url, timeout=15,headers=None):
    if headers is None:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Connection': 'keep-alive'}
    req = Request(url, headers=headers)
    req.keep_alive = False
    try:
        fp = urlopen(req, timeout=timeout)
        data = fp.read()
        fp.close()
    except (socket.timeout, socket.error) as e:
        data = ''
        log.error('socket timed out error:%s - URL %s ' % (e, url))
        if str(e).find('HTTP Error 456') >= 0:
            sleeprandom(10)
            return data
        sleeprandom(30)
        return data
    except Exception as e:
        data = ''
        log.error('url Exception Error:%s - URL %s ' % (e, url))
        sleep(30)
    if isinstance(data,bytes):
        try:
            data = data.decode('utf8')
        except:
            data = data.decode('gbk')
    return data

def get_url_data_requests(url, timeout=30, headers=None, retry=3):
    """
    使用 requests 获取 URL 内容，支持自定义 headers、超时和重试
    """
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0'
        }

    for attempt in range(retry):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            log.error(f'Attempt {attempt+1}/{retry} - requests error: {e} URL: {url}')
            # 递增等待时间
            time.sleep(3 + attempt * 3)
    return ''

# def get_url_data_requests(url, timeout=30, retry=3):
#     headers = {
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0'
#     }
#     for attempt in range(retry):
#         try:
#             r = requests.get(url, headers=headers, timeout=timeout)
#             r.raise_for_status()
#             return r.text
#         except requests.exceptions.RequestException as e:
#             log.error(f'Attempt {attempt+1} - requests error: {e}')
#             time.sleep(5 + attempt * 5)
#     return ''

def urlopen_with_retry(url, max_retries=3, initial_delay=1):
    """
    Opens a URL with retry logic and exponential backoff.
    """
    for attempt in range(max_retries):
        try:
            response = urlopen(url, timeout=10) # Set a timeout
            return response
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Max retries reached for {url}.")
                raise # Re-raise the last exception if all retries fail

    # # Usage example
    # try:
    #     data = urlopen_with_retry("http://www.example.com")
    #     print("Successfully opened URL.")
    #     # Process data
    #     # ...
    # except Exception as e:
    #     print(f"Failed to open URL after retries: {e}")

def get_url_data(url, retry_count=2, pause=0.05, timeout=30, headers=None):
    #    headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6'}
    # sina'Referer':'http://vip.stock.finance.sina.com.cn'

    if headers is None:
        # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
        #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        #            'Connection': 'keep-alive'}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Connection': 'keep-alive'}
    # else:

    #     headers = dict({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #                'Connection': 'keep-alive'},**headers)

    global ReqErrorCount
    # requests.adapters.DEFAULT_RETRIES = 5 # 增加重连次数
    s = requests.session()
    s.encoding = 'gbk'
    s.keep_alive = False # 关闭多余连接
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            data = s.get(url, headers=headers, timeout=timeout,allow_redirects=False)
        except (socket.timeout, socket.error) as e:
            data = ''
            log.error('socket timed out error:%s - URL %s ' % (e, url))
            if str(e).find('HTTP Error 456') >= 0:
                return data
            if ReqErrorCount < 3:
                ReqErrorCount +=1
                sleeprandom(60)
            else:
                break
        except Exception as e:
            log.error('url Exception Error:%s - URL %s ' % (e, url))
            if ReqErrorCount < 3:
                ReqErrorCount +=1
                sleeprandom(60)
            else:
                break
        else:
            log.info('Access successful.')
        # print data.text
        # fp = urlopen(req, timeout=5)
        # data = fp.read()
        # fp.close()
        # print data.encoding
            return data.text
    #     else:
    #         return df
    print("url:%s" % (url))
    return ''
    # raise IOError(ct.NETWORK_URL_ERROR_MSG)


def get_div_list(ls, n):
    # if isinstance(codeList, list) or isinstance(codeList, set) or
    # isinstance(codeList, tuple) or isinstance(codeList, pd.Series):

    if not isinstance(ls, list) or not isinstance(n, int):
        return []
    ls_len = len(ls)
    if n <= 0 or 0 == ls_len:
        return []
    if n > ls_len:
        return ls
    elif n == ls_len:
        return [[i] for i in ls]
    else:
        # j = (ls_len / n) + 1
        j = int((ls_len / n))
        k = ls_len % n
        # print "K:",k
        ls_return = []
        z = 0
        for i in range(0, (int(n) - 1) * j, j):
            if z < k:
                # if i==0:
                #     z+=1
                #     ls_return.append(ls[i+z*1-1:i+j+z*1])
                #     print i+z*1-1,i+j+z*1
                # else:
                z += 1
                ls_return.append(ls[i + z * 1 - 1:i + j + z * 1])
                # print i+z*1-1,i+j+z*1
            else:
                ls_return.append(ls[i + k:i + j + k])
                # print i+k,i + j+k
        # print (n - 1) * j+k,len(ls)
        ls_return.append(ls[(n - 1) * j + k:])
        return ls_return




def flatten(x):
    result = []
    for el in x:
        if isinstance(x, collections.abc.Iterable) and not isinstance(el, str):
            result.extend(flatten(el))
        else:
            result.append(el)
    return result

def to_asyncio_run_py2(urllist, cmd):
    results = []

    # print "asyncio",
    @asyncio.coroutine
    def get_loop_cmd(cmd, url_s):
        loop = asyncio.get_event_loop()
        result = yield From(loop.run_in_executor(None, cmd, url_s))
        results.append(result)

    threads = []
    for url_s in urllist:
        threads.append(get_loop_cmd(cmd, url_s))
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.wait(threads))
    return results

def to_asyncio_run_310(urllist, cmd):
    results = []

    async def sync_to_async(val):
        return val

    async def get_loop_cmd(cmd, url_s):
        loop = asyncio.get_event_loop()
        # result = yield From(loop.run_in_executor(None, cmd, url_s))
        # result = await cmd(url_s)
        result = await sync_to_async(cmd(url_s))
        results.append(result)

        # response = await aiohttp.get(self.sina_stock_api + self.stock_list[index])
        # response.encoding = self.encoding
        # data = await response.text()

    threads = []
    for url_s in urllist:
        threads.append(get_loop_cmd(cmd, url_s))
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.wait(threads))
    return results

def to_asyncio_run(urllist, cmd):
    async def _runner():
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(None, cmd, url)
            for url in urllist
        ]
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        return asyncio.create_task(_runner())
    else:
        return loop.run_until_complete(_runner())


def to_mp_run(cmd, urllist):
    # n_t=time.time()
    print("mp:%s" % len(urllist), end=' ')

    pool = ThreadPool(cpu_count())
    # pool = ThreadPool(2)
    # pool = ThreadPool(4)
    print(cpu_count())
    # pool = multiprocessing.Pool(processes=8)
    # for code in codes:
    #     results=pool.apply_async(sl.get_multiday_ave_compare_silent_noreal,(code,60))
    # result=[]
    # results = pool.map(cmd, urllist)
    results = []
    for y in tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqpm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols):
        results.append(y)
    # for code in urllist:
    # result.append(pool.apply_async(cmd,(code,)))

    pool.close()
    pool.join()
    results = flatten(results)
    # print "time:MP", (time.time() - n_t)
    return results


def imap_tqdm(function, iterable, processes, chunksize=20, desc=None, disable=False, **kwargs):
    """
    Run a function in parallel with a tqdm progress bar and an arbitrary number of arguments.
    Results are always ordered and the performance should be the same as of Pool.map.
    :param function: The function that should be parallelized.
    :param iterable: The iterable passed to the function.
    :param processes: The number of processes used for the parallelization.
    :param chunksize: The iterable is based on the chunk size chopped into chunks and submitted to the process pool as separate tasks.
    :param desc: The description displayed by tqdm in the progress bar.
    :param disable: Disables the tqdm progress bar.
    :param kwargs: Any additional arguments that should be passed to the function.
    """ 
    if kwargs:
        function_wrapper = functools.partial(_wrapper, function=function, **kwargs)
    else:
        function_wrapper = functools.partial(_wrapper, function=function)

    results = [None] * len(iterable)
    # results = []
    with ThreadPool(processes=processes) as p:
        # with tqdm(desc=desc, total=len(iterable), disable=disable) as pbar:
        with tqdm(desc=desc, total=len(iterable), disable=disable,mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols) as pbar:
            for i, result in p.imap_unordered(function_wrapper, enumerate(iterable), chunksize=chunksize):
                results[i] = result
                # results.append(result)
                pbar.update()

    return results


def _wrapper(enum_iterable, function, **kwargs):
    i = enum_iterable[0]
    result = function(enum_iterable[1], **kwargs)
    return i, result



def get_func_name(func):
    """
    获取函数名称，对 functools.partial 对象自动获取原始函数名。
    """
    while isinstance(func, functools.partial):
        func = func.func
    return getattr(func, '__name__', str(func))

def format_func_call(func, *args, **kwargs):
    """
    将函数调用转换成可读字符串。
    支持 functools.partial，将 partial 内的参数也包含。
    """
    # 解析 functools.partial
    while isinstance(func, functools.partial):
        # 累积 partial 的 args 和 kwargs
        partial_args = getattr(func, 'args', ())
        partial_kwargs = getattr(func, 'keywords', {}) or {}
        args = partial_args + args
        # partial 的 kwargs 与外部 kwargs 合并，外部优先
        combined_kwargs = {**partial_kwargs, **kwargs}
        kwargs = combined_kwargs
        func = func.func

    func_name = getattr(func, '__name__', str(func))
    
    args_str = ", ".join(repr(a) for a in args)
    kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    all_args = ", ".join(filter(None, [args_str, kwargs_str]))

    return f"{func_name}({all_args})"

    
# def to_mp_run_async_gpt(cmd, urllist, *args, **kwargs):
def to_mp_run_async(cmd, urllist, *args, **kwargs):
    #gpt
    t0 = time.time()

    logger = log
    old_level = logger.level 

    # 1. 禁用 tqdm 监控 (防止进度条线程报错)
    try:
        tqdm.monitor_interval = 0
    except:
        pass
        
    result = []
    errors = []

    urllist = list(set(urllist))
    data_count = len(urllist)
    if data_count == 0:
        return []

    pool_count = min(int(cpu_count() // 1.3), max(4, data_count // 50)) #9
    # pool_count = min(cpu_count() // 2 + 1, max(4, data_count // 50)) #5
    log.info(f"Cpu_count: {pool_count}")
    # 少量任务直接单进程，最稳
    # if data_count <= 200:
    #     log.debug(f'code: {urllist}')
    #     for c in tqdm(urllist, desc="mp_run_async-Running", ncols=getattr(ct, 'ncols', 80)):
    #         try:
    #             r = cmd(c, **kwargs)
    #             if r is not None and (not hasattr(r, 'empty') or not r.empty):
    #                 result.append(r)
    #         except Exception as e:
    #             errors.append((c, type(e).__name__, str(e)))
    if data_count <= 200:
        log.debug(f'code: {urllist}')
        for c in tqdm(urllist, desc="mp_run_async-Running", ncols=getattr(ct, 'ncols', 80)):
            try:
                r = cmd(c, **kwargs)
                if r is None:
                    continue
                # 1️⃣ 子进程返回的 dict 错误
                elif isinstance(r, dict) and r.get("__error__"):
                    errors.append((r["code"], r["exc_type"], r["exc_msg"]))
                # 2️⃣ DataFrame 错误通过 attrs
                elif hasattr(r, 'attrs') and '__error__' in r.attrs:
                    err_info = r.attrs['__error__']
                    errors.append((err_info['code'], err_info['exc_type'], err_info['exc_msg']))
                # 3️⃣ 有效 DataFrame
                elif not hasattr(r, 'empty') or not r.empty:
                    result.append(r)

            except Exception as e:
                # 这里捕获 cmd 函数本身异常
                errors.append((c, type(e).__name__, str(e)))
    else:
        # cpu_used = cpu_count() // 2 + 1 #7
        # pool_count7 = min(max(1, data_count // 100), cpu_used)   #7
        # pool_count7 = min(cpu_count() // 2 + 1, max(4, data_count // 60)) #7
        # log.info(f'count:{data_count} pool_count:{pool_count} pool_count5: {pool_count5} pool_count4:{pool_count4}')
        log.info(f'count:{data_count} pool_count:{pool_count}')
        func = functools.partial(cmd, **kwargs)
        worker = functools.partial(process_file_exc, func)
        try:
            # --- 关键：在多进程运行期间，只允许 WARNING 以上级别的日志进入管道 ---
            # 这样可以极大减少管道通信负担，避免结束时管道破裂
            logger.setLevel(LoggerFactory.WARNING) 
            with Pool(processes=pool_count) as pool:
                for r in tqdm(
                    pool.imap_unordered(worker, urllist, chunksize=10),
                    total=data_count,
                    unit='it', 
                    mininterval=ct.tqdm_mininterval,
                    unit_scale=True,
                    desc="Running_MP",
                    ncols=getattr(ct, 'ncols', 80),
                ):
                    # if r is None:
                    #     continue

                    # if isinstance(r, dict) and r.get("__error__"):
                    #     errors.append(
                    #         (r["code"], r["exc_type"], r["exc_msg"])
                    #     )
                    #     continue

                    # if not hasattr(r, 'empty') or not r.empty:
                    #     result.append(r)

                    # r 是子进程返回
                    if r is None:
                        continue

                    # 1️⃣ 判断 r 是否是 dict 错误
                    elif isinstance(r, dict) and r.get("__error__"):
                        errors.append((r["code"], r["exc_type"], r["exc_msg"]))

                    # 2️⃣ 判断 r 是否是 pd.DataFrame 的错误标记
                    elif hasattr(r, 'attrs') and '__error__' in r.attrs:
                        err_info = r.attrs['__error__']
                        errors.append((err_info['code'], err_info['exc_type'], err_info['exc_msg']))

                    # 3️⃣ 否则 r 是正常 DataFrame
                    elif not hasattr(r, 'empty') or not r.empty:
                        result.append(r)

            # 执行完后立即恢复原始日志等级
            logger.setLevel(old_level)

            # # 过滤结果，解决 IndexError
            # result = [r for r in results if r is not None and (not hasattr(r, 'empty') or not r.empty)]
            
        except (BrokenPipeError, EOFError):
            logger.setLevel(old_level)
            log.error(f"MP Error: {e}")
            # 即使报错，results 变量里通常已经拿到了 100% 的数据
            # if 'results' in locals():
            #     result = [r for r in results if r is not None and (not hasattr(r, 'empty') or not r.empty)]
        except Exception as e:
            logger.setLevel(old_level)
            log.error(f"MP Error: {e}")

    # 主进程统一记录错误（安全）
    for code, etype, emsg in errors:
        log.error("Worker failed | code=%s | %s: %s", code, etype, emsg)

    log.info(
        "Cpu_count: {%d} Time: %.2fs | Total OK: %d | Errors: %d",
        pool_count,
        time.time() - t0,
        len(result),
        len(errors),
    )
    return result

def process_file_exc(func=None, code=None):
    try:
        return func(code)
    except Exception as ex:
        # 子进程只返回轻量错误信息，禁止 logging / traceback
        return {
            "__error__": True,
            "code": code,
            "exc_type": type(ex).__name__,
            "exc_msg": str(ex),
        }

# def process_file_exc_last(func=None, code=None):
#     try:
#         # 尝试执行函数
#         return func(code) 
#     except Exception as ex:
#         msg = f"Exception on code:{code} " + os.linesep + traceback.format_exc()
#         runcmd = format_func_call(func, code)
#         # 在工作进程中记录详细错误
#         log.error(f'Work process failed: msg:{msg} \n runcmd:{runcmd}')
#         # log.error(f'Work process failed: msg:{msg}')
#         # 返回 None 或一个特定的失败标记
#         return None # 不要返回 Exception 对象

error_codes = []

# def to_mp_run_async_newOK(cmd, urllist, *args, **kwargs):
#     #G Flash 
#     result = []  
#     time_s = time.time()
    
#     # 1. 禁用 tqdm 监控 (防止进度条线程报错)
#     try:
#         tqdm.monitor_interval = 0
#     except:
#         pass
    
#     # 2. 获取根日志记录器，临时屏蔽 INFO 级别的日志传输
#     # 这一步是解决 BrokenPipeError: WinError 109 的核心
#     logger = log
#     old_level = logger.level 

#     urllist = list(set(urllist))
#     data_count = len(urllist)
#     if data_count == 0: return []

#     if data_count > 200:
#         cpu_used = int(cpu_count() / 2) + 1
#         pool_count = min(max(1, int(data_count / 100)), cpu_used)
        
#         func = functools.partial(cmd, **kwargs)
#         partialfunc = functools.partial(process_file_exc, func)

#         try:
#             # --- 关键：在多进程运行期间，只允许 WARNING 以上级别的日志进入管道 ---
#             # 这样可以极大减少管道通信负担，避免结束时管道破裂
#             logger.setLevel(LoggerFactory.WARNING) 
#             # process_map(partialfunc,
#             #             urllist, 
#             #             unit='%',
#             #             mininterval=ct.tqdm_mininterval,
#             #             unit_scale=True,
#             #             ncols=ct.ncols ,
#             #             total=data_count,
#             #             max_workers=pool_count)
#             results = process_map(
#                 partialfunc, 
#                 urllist, 
#                 unit='it', 
#                 mininterval=ct.tqdm_mininterval,
#                 unit_scale=True,
#                 total=data_count,
#                 max_workers=pool_count,
#                 chunksize=10,        # 增大块大小，减少通信频次
#                 #miniters=1,
#                 ncols=getattr(ct, 'ncols', 80),
#                 desc="Running_MP"
#             )
            
#             # --- 在这里添加 GC 清理 ---
#             # 此时 results 已拿到，子进程已基本退出，强制清理内存和句柄
#             gc.collect() 
#             # -----------------------
#             # 执行完后立即恢复原始日志等级
#             logger.setLevel(old_level)

#             # 过滤结果，解决 IndexError
#             result = [r for r in results if r is not None and (not hasattr(r, 'empty') or not r.empty)]
            
#         except (BrokenPipeError, EOFError):
#             logger.setLevel(old_level)
#             # 即使报错，results 变量里通常已经拿到了 100% 的数据
#             if 'results' in locals():
#                 result = [r for r in results if r is not None and (not hasattr(r, 'empty') or not r.empty)]
#         except Exception as e:
#             logger.setLevel(old_level)
#             log.error(f"MP Error: {e}")
#     else:
#         # 数量少时不走多进程，最稳定
#         result = [cmd(c, **kwargs) for c in urllist if c]
#         result = [r for r in result if r is not None and (not hasattr(r, 'empty') or not r.empty)]

#     log.info(f"Cpu_count: {pool_count} Time: {round(time.time()-time_s, 2)}s | Total: {len(result)}")
#     return result

# https://stackoverflow.com/questions/68065937/how-to-show-progress-bar-tqdm-while-using-multiprocessing-in-python
def to_mp_run_async_me_ok(cmd, urllist, *args,**kwargs):
# def to_mp_run_async(cmd, urllist, *args,**kwargs):
    result = []  
    time_s = time.time()
    # func = partial(cmd, **kwargs)
    # module = importlib.import_module(cmd)
    # https://stackoverflow.com/questions/72766345/attributeerror-cant-pickle-local-object-in-multiprocessing
    urllist = list(set(urllist))
    data_count =len(urllist)
    global error_codes
    cpu_used = int(cpu_count()/2)  + 1
    pool_count = min(int(cpu_count() // 1.3), max(4, data_count // 50)) #9
    if data_count > 200:
        if int(round(data_count/100,0)) < 2:
            cpu_co = 1
        else:
            cpu_co = int(round(data_count/100,0))
        # cpu_used = int(cpu_count()) - 2
        # pool_count = min(cpu_count(), max(4, data_count // 50)) #5
        # pool_count = min(cpu_count() // 2 + 1, max(4, data_count // 80)) #4
        # pool_count = (cpu_used) if cpu_co > (cpu_used) else cpu_co
        log.info(f'count:{data_count} pool_count:{pool_count} cpu_co:{cpu_used}')
        # pool_count = (cpu_count()-2) if cpu_co > (cpu_count()-2) else cpu_co
        if  cpu_co > 1 and 1300 < get_now_time_int() < 1500:
            pool_count = int(cpu_count() / 2) + 1
            # pool_count = int(cpu_count()) - 3
        if len(kwargs) > 0 :
                # pool = ThreadPool(12)
                log.debug(f'cmd:{cmd} kwargs:{kwargs}')
                func = functools.partial(cmd, **kwargs)
                partialfunc = functools.partial(process_file_exc, func)
                old_level = log.level 
                log.setLevel(LoggerFactory.WARNING) 
                def log_idx_none(idx, code, count_all, result_count):
                    global error_codes
                    error_codes.append(code)

                    # 每 30 条输出一次
                    if len(error_codes) % 30 == 0:
                        log.error(f"idx is None, codes: {error_codes[-30:]}, CountAll: {count_all}, resultCount: {result_count}")
                        error_codes = []
                try:
                    progress_bar = tqdm(total=data_count)
                    log.debug(f'data_count:{data_count},mininterval:{ct.tqdm_mininterval},ncols={ct.ncols}')
                    # 核心修复：防止监控线程在 Windows 管道关闭时抛出 EOFError
                    # tqdm.monitor_interval = 0
                    # from multiprocessing import Manager
                    # manager = Manager()
                    # shared_list = manager.list()
                    # https://stackoverflow.com/questions/67957266/python-tqdm-process-map-append-list-shared-between-processes

                    # tqdm.monitor_interval = 0
                    # results = process_map(partialfunc, urllist, unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count,max_workers=pool_count,chunksize=20,miniters=10)
                    results = process_map(partialfunc, urllist, unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,chunksize=10,ncols=ct.ncols , total=data_count,max_workers=pool_count)
                    result = []
                    # for data in results:
                    #     if isinstance(data, Exception):
                    #         print("Got exception: {}".format(data))
                    #     else:
                    #         # print("Got OK result: {}".format(result))
                    #         if len(data) > 10:
                    #             result.append(data)
                    #         else:
                    #             log.error(f'data is None,last code:{result[-1].code}')
                    
                    # index_counts = len(results[0].index) if len(results[0]) > 10 else len(results[1].index)
                    # --- 在这里添加 GC 清理 ---
                    # 此时 results 已拿到，子进程已基本退出，强制清理内存和句柄
                    gc.collect() 
                    # -----------------------
                    # 执行完后立即恢复原始日志等级
                    log.setLevel(old_level)

                    try:
                        # index_counts = len(results[0].index) if len(results[0]) > 10 else len(results[1].index)
                        valid_results = [r for r in results if r is not None and not isinstance(r, Exception)]
                        if valid_results:
                            index_counts = len(valid_results[0].index)
                        else:
                            index_counts = 0
                    except Exception:
                        index_counts = 0  # 或 log.error(...)
                    log.debug(f'index_counts:{index_counts}')

                    # for idx, data in enumerate(results):
                    #     if isinstance(data, Exception):
                    #         print("Got exception: {}".format(data))
                    #     else:
                    #         # print("Got OK result: {}".format(result))
                    #         # if len(data) > 0 and len(data.index) == index_counts:
                    #         if len(data) > 0:
                    #             result.append(data)
                    #         else:
                    #             # log.error(f'idx:{idx} is None,last code:{result[-1].code} resultCount:{len(result)}')
                    #             # log.error(f'idx:{idx} is None, code: {urllist[idx]} CountAll:{data_count} resultCount:{len(result)}')
                    #             log_idx_none(idx, urllist[idx], data_count, len(result))

                    for idx, data in enumerate(results):
                        if data is None: # 检查失败标记
                            # 失败信息已在工作进程中记录，这里只需记录哪个 code 失败了
                            log_idx_none(idx, urllist[idx], data_count, len(result))
                        else:
                            # 处理成功结果
                            result.append(data)

                    # result = list(set(result))
                    # 最后剩余不足 30 条，也输出一次
                    if len(error_codes) % 30 != 0:
                        log.error(f"idx is None, codes: {error_codes[-(len(error_codes)%30):]}")
                        error_codes = []
                    log.debug(f'result:{len(result)}')
                except (BrokenPipeError, EOFError):
                    log.setLevel(old_level)
                    # 即使报错，results 变量里通常已经拿到了 100% 的数据
                    if 'results' in locals():
                        result = [r for r in results if r is not None and (not hasattr(r, 'empty') or not r.empty)]  
                except Exception as e:
                    log.setLevel(old_level)
                    log.error("except:%s"%(e))
                    # traceback.print_exc()
                    msg = traceback.format_exc()
                    log.error(msg)
                    # log.error("except:results%s"%(results[-1]))
                    # import ipdb;ipdb.set_trace()
                    results=[]
                    urllist = error_codes
                    for code in urllist:
                        log.info(f"error_codes code:{code},count:{data_count} idx:{urllist.index(code)}", end=' ')
                        # log_idx_none(urllist.index(code), code, data_count, len(result))
                        res=cmd(code,**kwargs)
                        log.info("error_codes status:%s\t"%(len(res)), end=' ')
                        results.append(res)
                    result=results
                
                
        else:
            try:
                with Pool(processes=pool_count) as pool:
                    data_count=len(urllist)
                    progress_bar = tqdm(total=data_count)
                    # print("mapping ...")
                    # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                    results = tqdm(pool.imap_unordered(cmd, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                    # print("running ...")
                    result=tuple(results)  # fetch the lazy results
                    # print("done")
            except Exception as e:
                log.error("except:%s"%(e))


    else:
        if len(kwargs) > 0 :
            pool = ThreadPool(1)
            func = functools.partial(cmd, **kwargs)
            # TDXE:40.63  cpu 1    cpu_count() 107.14
            # for y in tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=5):
            # results = pool.map(func, urllist)
            try:
                results = pool.map(func, urllist)
            except Exception as e:
                log.error("except:%s"%(e))
        else:
            pool = ThreadPool(int(cpu_count())/ 2 - 1 if int(cpu_count()) > 2 else 2)
            for code in urllist:
                try:
                    # result = pool.apply_async(cmd, (code,) + args).get()
                    results.append(pool.apply_async(cmd, (code,) + args).get())
                except Exception as e:
                    log.error("except:%s code:%s"%(e,code))
        pool.close()
        pool.join()
        result=results
    log.info(f"Cpu_count: {pool_count} Time: {round(time.time()-time_s, 2)}s | Total OK: {len(result)} | Errors: {len(error_codes)}")
    return result

'''
                try:
                    with Pool(processes=pool_count) as pool:
                        data_count=len(urllist)
                        progress_bar = tqdm(total=data_count)
                        # print("mapping ...")

                        log.debug(f'data_count:{data_count},mininterval:{ct.tqdm_mininterval},ncols={ct.ncols}')
                        # tqdm(pool.imap_unordered(func, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(urllist),ncols=ct.ncols)
                        print(f"{os.getpid()=}")
                        # results = tqdm(pool.imap_unordered(partialfunc, urllist),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count)
                        
                        # from tqdm.contrib.concurrent import process_map
                        # tqdm.monitor_interval = 0
                        # results = process_map(partialfunc, urllist, unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,ncols=ct.ncols , total=data_count,max_workers=pool_count)

                        # print("running ...")
                        # result = tuple(results)  # fetch the lazy results
                        result = []
                        for data in results:
                            if isinstance(data, Exception):
                                print("Got exception: {}".format(data))
                            else:
                                # print("Got OK result: {}".format(result))
                                result.append(data)

                        pool.close()
                        pool.join()
'''
                    #debug:
                    # results=[]
                    # for code in urllist:
                    #     print("code:%s "%(code), end=' ')
                    #     res=cmd(code,**kwargs)
                    #     print("status:%s\t"%(len(res)), end=' ')
                    #     results.append(res)
                    # result=results



def f_print(lens, datastr, type=None):
    data = ('{0:%s}' % (lens)).format(str(datastr))
    if type is not None:
        if type == 'f':
            return float(data)
    else:
        return data


def read_last_lines(filename, lines=1):
    # print the last line(s) of a text file
    """
    Argument filename is the name of the file to print.
    Argument lines is the number of lines to print from last.
    """
    block_size = 1024
    block = ''
    nl_count = 0
    start = 0
    fsock = open(filename, 'rb')
    try:
        # seek to end
        fsock.seek(0, 2)
        # get seek position
        curpos = fsock.tell()
        # print curpos
        while (curpos > 0):  # while not BOF
            # seek ahead block_size+the length of last read block
            curpos -= (block_size + len(block))
            if curpos < 0:
                curpos = 0
            
            # except:'gbk' codec can't decode byte 0xc5 in position 1021:
            # tdx 4107: len(codeList) > 150: 

            fsock.seek(curpos)
            # read to end
            block = fsock.read()
            if isinstance(block,bytes):
                block = block.decode(errors="ignore")
            nl_count = block.count('\n') - block.count('\n\n')
            # nl_count_err = block.count('\n\n')
            # nl_count = nl_count - nl_count_err

            # if read enough(more)
            if nl_count >= lines:
                break
        # get the exact start position
        for n in range(nl_count - lines):
            start = block.find('\n', start) + 1
    finally:
        fsock.close()
    return block[start:]


def _write_to_csv(df, filename, indexCode='code'):
    TODAY = datetime.date.today()
    CURRENTDAY = TODAY.strftime('%Y-%m-%d')
    #     reload(sys)
    #     sys.setdefaultencoding( "gbk" )
    df = df.drop_duplicates(indexCode)
    # df = df.set_index(indexCode)
    # print df[['code','name']]
    df.to_csv(CURRENTDAY + '-' + filename + '.csv',
              encoding='gbk', index=False)  # 选择保存
    print(("write csv:%s" % (CURRENTDAY + '-' + filename + '.csv')))
    # df.to_csv(filename, encoding='gbk', index=False)


def code_to_tdxblk(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 6:
            return ''
        else:
            # return '1%s' % code if code[:1] in ['5', '6'] else '0%s' % code
            if  code[:1] in ['5', '6']:
                code = '1%s' % code
            elif  code[:2] in ['43','83','87','92']:
                # startswith('43','83','87','92')
                code = '2%s' % code
            else:
                code = '0%s' % code
            return code


def tdxblk_to_code(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 7:
            return ''
        else:
            return code[1:] if code[:1] in ['1', '0'] else code

def code_to_symbol_dfcf(code):
    """
        生成symbol代码标志
    """
    # if code in ct.INDEX_LABELS:
    #     return ct.INDEX_LIST_TDX[code]
    # else:
    if len(code) != 6:
        return ''
    else:
        return '1.%s' % code if code[:1] in ['5', '6', '9'] else '0.%s' % code


def code_to_index(code):
    if not code.startswith('999') or not code.startswith('399'):
        if code[:1] in ['5', '6', '9']:
            code2 = '999999'
        elif code[:1] in ['3']:
            code2 = '399006'
        else:
            code2 = '399001'
    return code2


def code_to_symbol(code: str) -> str:
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST_TDX[code]
    else:
        if len(code) != 6:
            return ''
        else:
            if code[:1] in ['5', '6']:
                code = 'sh%s' % code
            elif code[:2] in ['43', '83', '87', '92']:
                code = 'bj%s' % code
            else:
                code = 'sz%s' % code
            return code

def code_to_symbol_ths(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST_TDX[code]
    else:
        if len(code) != 6:
            return ''
        else:
            if  code[:1] in ['5', '6', '9']:
                code = '%s.SH' % code
            # elif  code[:1] in ['8']:
            elif  code[:2] in ['43','83','87','92']:
                code = '%s.BJ' % code
            else:
                code = '%s.SZ' % code
            return code
            # return '%s.SH' % code if code[:1] in ['5', '6', '9'] else '%s.SZ' % code

def symbol_to_code(symbol):
    """
        生成symbol代码标志
    """
    if symbol in ct.INDEX_LABELS:
        return ct.INDEX_LIST[symbol]
    else:
        if len(symbol) != 8:
            return ''
        else:
            # return re.findall('(\d+)', symbol)[0]
            return re.findall(r'(\d+)', symbol)[0]


def code_to_tdx_blk(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 6:
            return ''
        else:
            if  code[:1] in ['5', '6']:
                code = '1%s' % code
            elif  code[:2] in ['43','83','87','92']:
                # startswith('43','83','87','92')
                code = '2%s' % code
            else:
                code = '0%s' % code
            return code
            # return '1%s' % code if code[:1] in ['5', '6'] else '0%s' % code


def get_config_value(fname, classtype, currvalue=0, limitvalue=1, xtype='limit', read=False):
    conf_ini = fname
    currvalue = int(float(currvalue))
    if os.path.exists(conf_ini):
        # log.info("file ok:%s"%conf_ini)
        config = ConfigObj(conf_ini, encoding='UTF8')
        if not read:
            if classtype in list(config.keys()) and xtype in config[classtype].keys():
                if int(float(config[classtype][xtype])) > currvalue:
                    ratio = float(config[classtype][xtype]) / limitvalue
                    if ratio < 1.2:
                        log.info("f_size:%s < read_limit:%s ratio:%0.2f" % (currvalue, config[classtype][xtype], ratio))
                    else:
                        config[classtype][xtype] = limitvalue
                        config.write()
                        log.info("f_size:%s < read_limit:%s ratio < 2 ratio:%0.2f" % (currvalue, config[classtype][xtype], ratio))
                        
                else:

                    log.info("file:%s f_size:%s > read_limit:%s" % (fname, currvalue, config[classtype][xtype][:5]))
                    config[classtype][xtype] = limitvalue
                    config.write()
                    return True
            else:
                # log.error("no type:%s f_size:%s" % (classtype, currvalue))
                config[classtype] = {}
                config[classtype][xtype] = limitvalue
                config.write()
        else:
            if classtype in list(config.keys()) and xtype in config[classtype].keys():
                return config[classtype][xtype]
            else:
                return None
    else:
        config = ConfigObj(conf_ini, encoding='UTF8')
        config[classtype] = {}
        config[classtype][xtype] = limitvalue
        config.write()
    return False


def get_config_value_ramfile(fname: str, currvalue: Any = 0, xtype: str = 'time', update: bool = False, cfgfile: str = 'h5config.txt', readonly: bool = False, int_time: bool = False) -> Any:
    classtype: str = fname
    conf_ini: str = get_ramdisk_dir() + os.path.sep + cfgfile
    if xtype == 'trade_date':
        if os.path.exists(conf_ini):
            config = ConfigObj(conf_ini, encoding='UTF8')

            if classtype in list(config.keys()):
                if xtype in list(config[classtype].keys()):
                    save_date = config[classtype]['date']
                else:
                    save_date = None
            else:
                save_date = None

            if save_date is not None:
                if save_date != get_today() or update:
                    trade_status = is_trade_date()
                    if trade_status is not None or trade_status != 'None':
                        if 'rewrite' in list(config[classtype].keys()):
                            rewrite = int(config[classtype]['rewrite']) + 1
                        else:
                            rewrite = 1
                        config[classtype] = {}
                        config[classtype][xtype] = trade_status
                        config[classtype]['date'] = get_today()
                        config[classtype]['rewrite'] = rewrite
                        config.write()
            else:
                config[classtype] = {}
                config[classtype][xtype] = is_trade_date()
                config[classtype]['date'] = get_today()
                config[classtype]['rewrite'] = 1
                config.write()
        else:
            config = ConfigObj(conf_ini, encoding='UTF8')
            config[classtype] = {}
            config[classtype][xtype] = is_trade_date()
            config[classtype]['date'] = get_today()
            config[classtype]['rewrite'] = 1
                # time.strftime("%H:%M:%S",time.localtime(now))
            config.write()

        return config[classtype][xtype]    

    else:

        currvalue = int(currvalue)
        if os.path.exists(conf_ini):
            config = ConfigObj(conf_ini, encoding='UTF8')

            if not classtype in list(config.keys()):
                if not readonly:
                    config[classtype] = {}
                    config[classtype][xtype] = currvalue
                    config.write()


            elif readonly:
                if xtype in config[classtype].keys() and xtype == 'time':
                    save_value = int(config[classtype][xtype])
                else:
                    save_value = int(currvalue)
                    config[classtype][xtype] = save_value
                    config.write()
                if int_time:
                    return int(time.strftime("%H:%M:%S",time.localtime(save_value))[:6].replace(':',''))
                else:
                    return int(save_value)

            elif not update:
                if classtype in list(config.keys()):
                    if not xtype in list(config[classtype].keys()):
                        config[classtype][xtype] = currvalue
                        config.write()
                        if xtype == 'time':
                            return 1
                    else:
                        if xtype == 'time' and currvalue != 0:
                            time_dif = currvalue - float(config[classtype][xtype])
                        else:
                            time_dif = int(config[classtype][xtype])
                        if int_time:
                            return int(time.strftime("%H:%M:%S",time.localtime(time_dif))[:6].replace(':',''))
                        else:
                            return time_dif

                else:
                    config[classtype] = {}
                    config[classtype][xtype] = 0
                    config.write()
            elif not xtype in config[classtype].keys():
                if update:
                    config[classtype][xtype] = currvalue
                    if xtype == 'time':
                        config[classtype]['otime'] = time.strftime("%H:%M:%S",time.localtime(currvalue))
                    config.write()

            else:
                if xtype == 'time':
                    save_value = float(config[classtype][xtype])
                else:
                    save_value = int(config[classtype][xtype])
                if save_value != currvalue:
                    config[classtype][xtype] = currvalue
                    if xtype == 'time':
                        config[classtype]['otime'] = time.strftime("%H:%M:%S",time.localtime(currvalue))
                    config.write()
        else:
            config = ConfigObj(conf_ini, encoding='UTF8')
            config[classtype] = {}
            config[classtype][xtype] = currvalue
            if xtype == 'time':
                config[classtype]['otime'] = currvalue
                # time.strftime("%H:%M:%S",time.localtime(now))
            config.write()
        return int(currvalue)


def get_config_value_wencai(fname, classtype, currvalue=0, xtype='limit', update=False):
    conf_ini = fname
    # print fname
    currvalue = int(currvalue)
    if os.path.exists(conf_ini):
        config = ConfigObj(conf_ini, encoding='UTF8')
        if not update:
            if classtype in list(config.keys()):
                if not xtype in list(config[classtype].keys()):
                    config[classtype][xtype] = currvalue
                    config.write()
                    if xtype == 'time':
                        return 1
                else:
                    if xtype == 'time' and currvalue != 0:
                        time_dif = currvalue - float(config[classtype][xtype])
                    else:
                        time_dif = int(config[classtype][xtype])
                    return time_dif

            else:
                config[classtype] = {}
                config[classtype][xtype] = 0
                config.write()
        else:
            if xtype == 'time':
                save_value = float(config[classtype][xtype])
            else:
                save_value = int(config[classtype][xtype])
            if save_value != currvalue:
                config[classtype][xtype] = currvalue
                config.write()
    else:
        config = ConfigObj(conf_ini, encoding='UTF8')
        config[classtype] = {}
        config[classtype][xtype] = currvalue
        config.write()
    return int(currvalue)


def to_bool(value: Any) -> bool:
    """
    将输入转换为布尔值：
    - 如果已经是 bool，直接返回
    - 如果是字符串 'True' / 'False'（大小写敏感或忽略大小写），转换为对应布尔值
    - 其它类型返回 False
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v: str = value.strip().lower()
        if v == "true":
            return True
        elif v == "false":
            return False
    # 其它情况默认 False
    return False


def get_trade_date_status() -> bool:
    trade_date: Optional[str] = GlobalValues().getkey('trade_date')
    trade_status: Any = GlobalValues().getkey('is_trade_date')
    if trade_status is None:
        trade_status = get_config_value_ramfile(fname='is_trade_date', currvalue=get_day_istrade_date(), xtype='trade_date')
        if trade_status is None or trade_status == 'None':
            trade_status = get_config_value_ramfile(fname='is_trade_date', currvalue=get_day_istrade_date(), xtype='trade_date', update=True)
        GlobalValues().setkey('is_trade_date', trade_status)
        GlobalValues().setkey('trade_date', get_today())
    if trade_date is not None:
        if trade_date != get_today():
            trade_status = get_config_value_ramfile(fname='is_trade_date', currvalue=get_day_istrade_date(), xtype='trade_date')
            GlobalValues().setkey('is_trade_date', trade_status)
            GlobalValues().setkey('trade_date', get_today())
    return to_bool(trade_status)
# wencai_count = cct.get_config_value_wencai(config_ini,fname,1,update=True)

def get_index_fibl(default=1):
    # import sys
    # sys.path.append("..")
    # from JSONData import powerCompute as pct
    # df = pct.powerCompute_df(['999999','399006','399001'], days=0, dtype='d', end=None, dl=10, talib=True, filter='y',index=True)
    # df = tdd.get_tdx_exp_all_LastDF_DL(
    #             ['999999','399006','399001'], dt=10)

    # if len(df) >0 and 'fibl' in df.columns:
    #     # fibl = int(df.fibl.max())
    #     # fibl = int(df.cumin.max())
    #     fibl = int(df.fibl.max())
    #     fibl = fibl if 4 > fibl > 1 else default
    #     # fibl = fibl if 3 >= fibl >= 1 else 1
    #     # return abs(fibl)
    # else:
    #     fibl = 1
    # # cct.GlobalValues()
    # GlobalValues().setkey('cuminfibl', fibl)
    # GlobalValues().setkey('indexfibl', int(df.fibl.min()))
    # return abs(fibl)
    return default

from collections import Counter,OrderedDict
def counterCategory(df: pd.DataFrame, col: str = 'category', table: bool = False, limit: int = 30) -> Union[Counter, str]:
    topSort: Union[Counter, str] = []
    if len(df) > 0:
        categoryl: list[Any] = df[col][:limit].tolist()
        dicSort: list[str] = []
        for i in categoryl:
            if isinstance(i, str):
                if col == 'category':
                    dicSort.extend(i.split(';'))
                else:
                    dicSort.extend(i.split('+'))
                
        topSort = Counter(dicSort)
        if not table:
            top5: OrderedDict[str, int] = OrderedDict(topSort.most_common(5))
            for i in list(top5.keys()):
                if len(i) > 2:
                    print(f'{i}:{top5[i]}', end=' ')
            print('')
        else:
            table_row: str = f''
            top5: OrderedDict[str, int] = OrderedDict(topSort.most_common(5))
            for i in list(top5.keys()):
                if len(i) > 2:
                    table_row += f'{i}:{top5[i]} '
            table_row += '\n'
            topSort = table_row 
    return topSort

# def write_to_dfcfnew(p_name=dfcf_path):
#     pass
def write_to_blkdfcf(codel: Union[list[str], str], conf_ini: str = dfcf_path, blk: str = 'inboll1', append: bool = True) -> None:
    import configparser
    if not isMac():
        if not os.path.exists(conf_ini):
            log.error('file is not exists:%s'%(conf_ini))
        else:
            cf: configparser.ConfigParser = configparser.ConfigParser()  # 实例化 ConfigParser 对象
            # cf.read("test.ini")
            cf.read(conf_ini,encoding='UTF-16')
            # cf.read(conf_ini,encoding='GB2312')
            # return all section
            secs: list[str] = cf.sections()
            # print('sections:', secs, type(secs))

            opts: list[str] = cf.options("\\SelfSelect")  # 获取db section下的 options，返回list
            # print('options:', opts, type(opts))
            # 获取db section 下的所有键值对，返回list 如下，每个list元素为键值对元组
            kvs: list[tuple[str, str]] = cf.items("\\SelfSelect")
            # print('db:', dict(kvs).keys())
            # read by type
            truer: str = cf.get("\\SelfSelect", blk)
            # print('truer:',truer)
            truer_n: str = truer
            idx: int = 0

            if isinstance(codel, list):
                for co in codel:
                    if code_to_symbol_dfcf(co) not in truer:
                        idx+=1
                        # print(idx)
                        truer_n = code_to_symbol_dfcf(co)+','+truer_n
                    # else:
                    #     print("no change co")
                        # truer_n = truer
            else:
                if code_to_symbol_dfcf(codel) not in truer:
                        idx+=1
                        truer_n = code_to_symbol_dfcf(codel)+','+truer
                # else:
                #     print("no change co")
                        # truer_n = truer
                        
            print("%s add:%s"%(blk,idx))
            cf.set("\\SelfSelect", blk, truer_n)
            # print('instock:',cf.get("\\SelfSelect", "instock"))
            cf.write(open(conf_ini,"w",encoding='UTF-16'))

def read_unicode_file(file_path: str) -> list[str]:
    with open(file_path, 'r', encoding='utf-8') as file:
        contents: list[str] = file.readlines()
        return contents

def write_unicode_file(file_path: str, contents: Union[list[str], str]) -> None:
    with open(file_path, 'w', encoding='utf-8') as file:
        if isinstance(contents, str):
            file.write(contents)
        else:
            file.writelines(contents)

def write_evalcmd2file(file_path: str, content: str) -> bool:
    content = content.strip()
    if not os.path.exists(file_path):
        write_unicode_file(file_path,content+'\n')
        # with open("history_data.json", "w+", encoding="utf-8") as f:
        #     f.write("[]")
    else:
        contents: list[str] = read_unicode_file(file_path)
        if len(content) > 0 and content+'\n' not in contents:
            contents.append(content+'\n')
        write_unicode_file(file_path, contents)
    return True

def write_to_blocknew(p_name, data, append=True, doubleFile=False, keep_last=None,dfcf=False,reappend=True):
    # fname=p_name
    # writename=r'D:\MacTools\WinTools\zd_dxzq\T0002'
    write_to_blocknew_2025(p_name, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)
    if not isMac():
        blocknew_path=get_tdx_dir_blocknew_dxzq(p_name)
        write_to_blocknew_2025(blocknew_path, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)   
    else:
        # blocknew_path=p_name.replace('new_tdx','new_tdx2')
        blocknew_path=p_name.replace('new_tdx2','new_tdx')
        write_to_blocknew_2025(blocknew_path, data, append=append, doubleFile=doubleFile, keep_last=keep_last,dfcf=dfcf,reappend=reappend)   

def write_to_blocknew_2025(p_name, data, append=True, doubleFile=False, keep_last=None,dfcf=False,reappend=True):
    if keep_last is None:
        keep_last = ct.keep_lastnum
    # index_list = ['1999999','47#IFL0',  '0159915', '27#HSI']
    index_list = ['1999999', '0399001', '0159915','2899050','1588000','1880884','1880885','1880818','1880774']
    # index_list = ['1999999', '0399001', '0159915','2899050','1588000','1880884','1880885','1880818','1880774']
    # index_list = ['1999999','47#IFL0', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '27#HSI',  '0399006']
    # index_list = ['1999999','0399001','47#IFL0', '27#HSI',  '0159915']
    # index_list = ['0399001', '1999999', '0159915']
    # index_list = ['1999999', '27#HSI',  '0159915']

    def writeBlocknew(p_name, data, append=True,keep_last=keep_last,reappend=True):
        flist=[]
        if append:
            fout = open(p_name, 'rb+')
            # fout = open(p_name)
            flist_t = fout.readlines()
            # flist_t = file(p_name, mode='rb+', buffering=None)
            # flist = []
            # errstatus=False
            

            for code in flist_t:
                if isinstance(code,bytes):
                    code = code.decode()
                if len(code) <= 6 or len(code) > 12:
                    continue
                if not code.endswith('\r\n'):
                    if len(code) <= 6:
                        # errstatus = True
                        continue
                    else:
                        # errstatus = True
                        code = code + '\r\n'
                flist.append(code)
            for co in index_list:
                inx = (co) + '\r\n'
                if inx not in flist:
                    flist.insert(index_list.index(co), inx)
            # if errstatus:
            # fout.close()
            # fout = open(p_name, 'wb+')
            # for code in flist:
            #     fout.write(code)

            # if not str(flist[-1]).endswith('\r\n'):
                # print "File:%s end not %s"%(p_name[-7:],str(flist[-1]))
            # print "flist", flist
        else:
            if int(keep_last) > 0:
                fout = open(p_name, 'rb+')
                flist_t = fout.readlines()
            else:
                flist_t = []
            # flist_t = file(p_name, mode='rb+', buffering=None)
            if len(flist_t) > 4:
                # errstatus=False
                for code in flist_t:
                    if isinstance(code,bytes):
                        code = code.decode()
                    if not code.endswith('\r\n'):
                        if len(code) <= 6:
                            # errstatus = True
                            continue
                        else:
                            # errstatus = True
                            code = code + '\r\n'
                    flist.append(code)
                # if errstatus:
                if int(keep_last) > 0:
                    fout.close()
                # if p_name.find('066.blk') > 0:
                #     writecount = ct.writeblockbakNum
                # else:
                #     writecount = 9

                writecount = keep_last
                flist = flist[:writecount]

                for co in index_list:
                    inx = (co) + '\r\n'
                    if inx not in flist:
                        flist.insert(index_list.index(co), inx)
                # print flist
                # fout = open(p_name, 'wb+')
                # for code in flist:
                #     fout.write(code)
            else:
                # fout = open(p_name, 'wb+')
                # index_list.reverse()
                for i in index_list:
                    raw = (i) + '\r\n'
                    flist.append(raw)

        counts = 0
        idx = 0
        for i in data:
            # print type(i)
            # if append and len(flist) > 0:
            #     raw = code_to_tdxblk(i).strip() + '\r\n'
            #     if len(raw) > 8 and not raw in flist:
            #         fout.write(raw)
            # else:
            raw = code_to_tdxblk(i) + '\r\n'
            if len(raw) > 8:
                if not raw in flist:
                    if idx == 0 and counts == 0:
                        idx +=1
                        raw2 = code_to_tdxblk('562530') + '\r\n'
                        if not raw2 in flist:
                            flist.append(raw2)
                        else:
                            flist.remove(raw2)
                            flist.append(raw2)
                    counts += 1
                    flist.append(raw)
                else:
                    #if exist will remove and append
                    if reappend:
                        if idx == 0:
                            idx +=1
                            raw2 = code_to_tdxblk('562530') + '\r\n'
                            if not raw2 in flist:
                                flist.append(raw2)
                            else:
                                flist.remove(raw2)
                                flist.append(raw2)

                        flist.remove(raw)
                        flist.append(raw)

        fout = open(p_name, 'wb+')
        for code in flist:
            if not isinstance(code,bytes):
                code = code.encode()
            fout.write(code)
                # raw = pack('IfffffII', t, i[2], i[3], i[4], i[5], i[6], i[7], i[8])
        fout.flush()
        fout.close()
        # if p_name.find('066.blk') >= 0:
        if counts == 0:
            if len(data) == 0:
                log.error("counts and data is None:%s"%(p_name))
            else:
                print(("counts:0 data:%s :%s"%(len(data),p_name)))
        else:
            print("all write to %s:%s" % (p_name, counts))

    blockNew = get_tdx_dir_blocknew() + 'zxg.blk'
    blockNewStart = get_tdx_dir_blocknew() + '077.blk'
    # writeBlocknew(blockNew, data)
    p_data = ['zxg', '069', '068', '067', '061']
    if len(p_name) < 5:
        if p_name in p_data:
            p_name = get_tdx_dir_blocknew() + p_name + '.blk'
            print("p_name:%s" % (p_name))
        else:
            print('p_name is not ok')
            return None

    if p_name.find('061.blk') > 0 or p_name.find('062.blk') > 0 or p_name.find('063.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data, append=True,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to :%s:%s"%(p_name,len(data))
    elif p_name.find('064.blk') > 0:
        writeBlocknew(p_name, data, append,reappend=reappend)
        if doubleFile:
            writeBlocknew(blockNew, data, append=True,keep_last=9,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    elif p_name.find('068.blk') > 0 or p_name.find('069.blk') > 0:

        writeBlocknew(p_name, data, append,reappend=reappend)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

    else:
        writeBlocknew(p_name, data, append,reappend=reappend)
        if doubleFile:
            writeBlocknew(blockNew, data,append=True,reappend=reappend)
            # writeBlocknew(blockNewStart, data, append=True)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    if dfcf:
        write_to_blkdfcf(data)

def write_to_blocknewOld(p_name, data, append=True, doubleFile=True, keep_last=None):
    if keep_last is None:
        keep_last = ct.keep_lastnum
    # index_list = ['1999999','47#IFL0',  '0159915', '27#HSI']
    index_list = ['1999999', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '0399001', '0159915']
    # index_list = ['1999999','47#IFL0', '27#HSI',  '0399006']
    # index_list = ['1999999','0399001','47#IFL0', '27#HSI',  '0159915']
    # index_list = ['0399001', '1999999', '0159915']
    # index_list = ['1999999', '27#HSI',  '0159915']

    def writeBlocknew__(p_name, data, append=True,keep_last=keep_last):
        if append:
            fout = open(p_name, 'rb+')
            # fout = open(p_name)
            flist_t = fout.readlines()
            # flist_t = file(p_name, mode='rb+', buffering=None)
            flist = []
            # errstatus=False
            for code in flist_t:
                if isinstance(code,bytes):
                    code = code.decode()
                if len(code) <= 6 or len(code) > 12:
                    continue
                if not code.endswith('\r\n'):
                    if len(code) <= 6:
                        # errstatus = True
                        continue
                    else:
                        # errstatus = True
                        code = code + '\r\n'
                flist.append(code)
            for co in index_list:
                inx = (co) + '\r\n'
                if inx not in flist:
                    flist.insert(index_list.index(co), inx)
            # if errstatus:
            fout.close()
            fout = open(p_name, 'wb+')
            for code in flist:
                if not isinstance(code,bytes):
                    code = code.encode()
                fout.write(code)

            # if not str(flist[-1]).endswith('\r\n'):
                # print "File:%s end not %s"%(p_name[-7:],str(flist[-1]))
            # print "flist", flist
        else:
            if int(keep_last) > 0:
                fout = open(p_name, 'rb+')
                flist_t = fout.readlines()
                flist = []
            else:
                flist_t = []
                flist = []
            # flist_t = file(p_name, mode='rb+', buffering=None)
            if len(flist_t) > 4:
                # errstatus=False
                for code in flist_t:
                    if isinstance(code,bytes):
                        code = code.decode()
                    if not code.endswith('\r\n'):
                        if len(code) <= 6:
                            # errstatus = True
                            continue
                        else:
                            # errstatus = True
                            code = code + '\r\n'
                    flist.append(code)
                # if errstatus:
                if int(keep_last) > 0:
                    fout.close()
                # if p_name.find('066.blk') > 0:
                #     writecount = ct.writeblockbakNum
                # else:
                #     writecount = 9

                writecount = keep_last
                flist = flist[:writecount]

                for co in index_list:
                    inx = (co) + '\r\n'
                    if inx not in flist:
                        flist.insert(index_list.index(co), inx)
                # print flist
                fout = open(p_name, 'wb+')
                for code in flist:
                    if not isinstance(code,bytes):
                        code = code.encode()
                    fout.write(code)
            else:
                fout = open(p_name, 'wb+')
                # index_list.reverse()
                for i in index_list:
                    raw = (i) + '\r\n'
                    if not isinstance(raw,bytes):
                        raw = raw.encode()
                    fout.write(raw)

        counts = 0
        for i in data:
            # print type(i)
            # if append and len(flist) > 0:
            #     raw = code_to_tdxblk(i).strip() + '\r\n'
            #     if len(raw) > 8 and not raw in flist:
            #         fout.write(raw)
            # else:
            raw = code_to_tdxblk(i) + '\r\n'
            if len(raw) > 8 and not raw in flist:
                counts += 1
                if not isinstance(raw,bytes):
                    raw = raw.encode()
                fout.write(raw)
                # raw = pack('IfffffII', t, i[2], i[3], i[4], i[5], i[6], i[7], i[8])
        fout.flush()
        fout.close()
        # if p_name.find('066.blk') >= 0:
        if counts == 0:
            if len(data) == 0:
                log.error("counts and data is None:%s"%(p_name))
            else:
                print(("counts:0 data:%s :%s"%(len(data),p_name)))
        else:
            print("all write to %s:%s" % (p_name, counts))

    blockNew = get_tdx_dir_blocknew() + 'zxg.blk'
    blockNewStart = get_tdx_dir_blocknew() + '077.blk'
    # writeBlocknew(blockNew, data)
    p_data = ['zxg', '069', '068', '067', '061']
    if len(p_name) < 5:
        if p_name in p_data:
            p_name = get_tdx_dir_blocknew() + p_name + '.blk'
            print("p_name:%s" % (p_name))
        else:
            print('p_name is not ok')
            return None

    if p_name.find('061.blk') > 0 or p_name.find('062.blk') > 0 or p_name.find('063.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data)
            writeBlocknew(blockNewStart, data, append)
        # print "write to :%s:%s"%(p_name,len(data))
    elif p_name.find('064.blk') > 0:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data, append,keep_last=12)
            writeBlocknew(blockNewStart, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))
    elif p_name.find('068.blk') > 0 or p_name.find('069.blk') > 0:

        writeBlocknew(p_name, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

    else:
        writeBlocknew(p_name, data, append)
        if doubleFile:
            writeBlocknew(blockNew, data)
            # writeBlocknew(blockNewStart, data[:ct.writeCount - 1])
            writeBlocknew(blockNewStart, data, append)
        # print "write to append:%s :%s :%s"%(append,p_name,len(data))

def prepare_df_for_hdf5(df, verbose=False):
    if df is None or df.empty:
        return df

    start_mem = df.memory_usage().sum() / 1024 ** 2

    # -----------------------------
    # 1. 处理 categorical 列
    # -----------------------------
    for col in df.select_dtypes('category'):
        # 如果会填充 0，则先确保类别包含 0
        if 0 not in df[col].cat.categories:
            df[col] = df[col].cat.add_categories([0])

    # -----------------------------
    # 2. 处理 object 列
    # -----------------------------

    # for col in df.select_dtypes('object'):
    #     # if col == 'MainU':
    #     #     # 转掩码
    #     #     df[col] = df[col].apply(
    #     #         lambda x: sum(1 << int(i) for i in str(x).split(',') if i.isdigit()) if pd.notna(x) and x != '0' else 0
    #     #     ).astype('int32')
    #     if col == 'status':
    #         df[col] = df[col].astype('category')
    #     elif col == 'hangye':
    #         df[col] = df[col].replace(0, '未知').astype('category')
    #     elif col == 'date':
    #         df[col] = pd.to_datetime(df[col], errors='coerce')
    #     else:
    #         # 混合类型列统一转字符串
    #         df[col] = df[col].astype(str)
    for col in ['status', 'MainU', 'date', 'category', 'hangye']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '0')

    # -----------------------------
    # 3. 数值列瘦身
    # -----------------------------
    numerics = ["int8","int16","int32","int64","float16","float32","float64"]
    for col in df.select_dtypes(include=numerics).columns:
        col_type = df[col].dtype
        c_min = df[col].min()
        c_max = df[col].max()
        if str(col_type)[:3] == 'int':
            if c_min >= np.iinfo(np.int8).min and c_max <= np.iinfo(np.int8).max:
                df[col] = df[col].astype(np.int8)
            elif c_min >= np.iinfo(np.int16).min and c_max <= np.iinfo(np.int16).max:
                df[col] = df[col].astype(np.int16)
            elif c_min >= np.iinfo(np.int32).min and c_max <= np.iinfo(np.int32).max:
                df[col] = df[col].astype(np.int32)
            else:
                df[col] = df[col].astype(np.int64)
        else:  # float
            if c_min >= np.finfo(np.float16).min and c_max <= np.finfo(np.float16).max:
                df[col] = df[col].astype(np.float16).round(2)
            elif c_min >= np.finfo(np.float32).min and c_max <= np.finfo(np.float32).max:
                df[col] = df[col].astype(np.float32).round(2)
            else:
                df[col] = df[col].astype(np.float64).round(2)

    # -----------------------------
    # 4. 填充缺失值
    # -----------------------------
    for col in df.columns:
        if pd.api.types.is_categorical_dtype(df[col]):
            # categorical 填充 0 或 '未知' 必须在类别中已存在
            if 0 in df[col].cat.categories:
                df[col] = df[col].fillna(0)
            else:
                df[col] = df[col].fillna(df[col].mode().iloc[0])
        elif pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].fillna(0)
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].fillna(pd.Timestamp('1970-01-01'))
        else:
            df[col] = df[col].fillna('')

    end_mem = df.memory_usage().sum() / 1024 ** 2
    if verbose:
        log.info(f"Memory usage reduced from {start_mem:.2f} MB to {end_mem:.2f} MB "
                 f"({100 * (start_mem - end_mem) / start_mem:.1f}% reduction)")

    return df

# @timed_block("reduce_memory_usage", warn_ms=1000)
def reduce_memory_usage(df, verbose=False):
    numerics = ["int8", "int16", "int32", "int64", "float16", "float32", "float64"]
    if df is not None:
        start_mem = df.memory_usage().sum() / 1024 ** 2
        for col in df.columns:
            col_type = df[col].dtypes
            if isinstance(df.index, pd.MultiIndex) and col in ['volume','vol'] and col_type in numerics and str(col_type)[:3] == "int":
                df[col] = df[col].astype(np.int64)
            elif col_type in numerics:
                c_min = df[col].min()
                c_max = df[col].max()
                if str(col_type)[:3] == "int":
                    if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                        df[col] = df[col].astype(np.int8)
                    elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                        df[col] = df[col].astype(np.int16)
                    elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                        df[col] = df[col].astype(np.int32)
                    elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                        df[col] = df[col].astype(np.int64)
                else:
                    if (
                        c_min > np.finfo(np.float16).min
                        and c_max < np.finfo(np.float16).max
                    ):
                        df[col] = df[col].astype(np.float16)
                        df[col] = df[col].apply(lambda x:round(x,2))
                    elif (
                        c_min > np.finfo(np.float32).min
                        and c_max < np.finfo(np.float32).max
                    ):
                        df[col] = df[col].astype(np.float32)
                        df[col] = df[col].apply(lambda x:round(x,2))

                    else:
                        df[col] = df[col].astype(np.float64)
                        df[col] = df[col].apply(lambda x:round(x,2))
                        
        end_mem = df.memory_usage().sum() / 1024 ** 2
        if verbose:
            print(
                "Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
                    end_mem, 100 * (start_mem - end_mem) / start_mem
                )
            )
        else:
            log.debug(
                "Mem. usage decreased to {:.2f} Mb ({:.1f}% reduction)".format(
                    end_mem, 100 * (start_mem - end_mem) / start_mem
                )
            )
    return df

def df_memory_usage(df, verbose=False):
    end_mem = df.memory_usage().sum() / 1024 ** 2
    log.info(
                "Mem. usage decreased to {:.2f} Mb ".format(
                    end_mem
                )
            )
    return df
# def read_to_indb(days=20,duplicated=False):
#     df = inDb.selectlastDays(days)

#     if not duplicated :
#         df['couts']=df.groupby(['code'])['code'].transform('count')
#         df=df.sort_values(by='couts',ascending=0)
#         df=df.drop_duplicates('code')

#     return (df)

def read_to_blocknew(p_name):
    index_list = ['1999999', '0399001', '47#IFL0', '27#HSI',  '0159915']

    def read_block(p_name):
        fout = open(p_name, 'rb')
        # fout = open(p_name)
        flist_t = fout.readlines()
        flist = []
        for code in flist_t:
            if isinstance(code,bytes):
                code = code.decode()
            if len(code) <= 6 or len(code) > 12:
                continue
            if code.endswith('\r\n'):
                if len(code) <= 6 or code in index_list:
                    # errstatus = True
                    continue
                else:
                    code = code.replace('\r\n', '')
                    if code not in index_list:
                        code = tdxblk_to_code(code)
            else:
                continue
            if len(code) == 6 and code not in index_list:
                flist.append(code)
        fout.close()
        return flist

    if not p_name.endswith("blk"):
        blockNew = get_tdx_dir_blocknew() + p_name + '.blk'
        if not os.path.exists(blockNew):
            log.error("path error:%s" % (blockNew))
    else:
        blockNew = get_tdx_dir_blocknew() + p_name

    if os.path.exists(blockNew):
        codelist = read_block(blockNew)
    else:
        codelist = []
    # blockNewStart = get_tdx_dir_blocknew() + '066.blk'
    # writeBlocknew(blockNew, data)
    # p_data = ['zxg', '069', '068', '067', '061']
    return codelist


def getFibonacci(num, days=None):
    res = [0, 1]
    a = 0
    b = 1
    for i in range(0, num):
        if i == a + b:
            res.append(i)
            a, b = b, a + b
    if days is None:
        return res
    else:
        fib = days
        for x in res:
            if days <= x:
                fib = x
                break
        return fib

# def getFibonacciCount(num,days):
    # fibl = getFibonacci(num)
    # fib = days
    # for x in fibl:
        # if days < x:
        # fib = x
        # break
    # return fib


# def varname(p):
#     import inspect
#     for line in inspect.getframeinfo(inspect.currentframe().f_back)[3]:
#         m = re.search(r'\bvarname\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', line)
#         if m:
#             return m.group(1)


# def varnamestr(obj, namespace=globals()):
#     # namestr(a, globals())
#     if isinstance(namespace, dict):
#         n_list = [name for name in namespace if namespace[name] is obj]
#     else:
#         log.error("namespce not dict")
#         return None
#         # n_list = [name for name in namespace if id(name) == id(obj)]

#     for n in n_list:
#         if n.startswith('_'):
#             continue
#         else:
#             return n
#     return None

# multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'sum', 'open': 'first'}
# multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'sum', 'open': 'first'}

#20240301
multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'last', 'open': 'first'}

def using_Grouper_eval(df, freq='5T', col='low', closed='right', label='right'):
    func = {}
    if col == 'all':
        for k in df.columns:
            if k in list(multiIndex_func.keys()):
                if k == 'close':
                    func[k] = 'first'
                else:
                    func[k] = multiIndex_func[k]

    elif isinstance(col, list):
        for k in col:
            if k in list(multiIndex_func.keys()):
                func[k] = multiIndex_func[k]
    else:
        if col in list(multiIndex_func.keys()):
            func[col] = multiIndex_func[col]
    level_values = df.index.get_level_values
    return eval("(df.groupby([level_values(i) for i in [0]]+[pd.Grouper(freq=freq, level=-1,closed='%s',label='%s')]).agg(%s))" % (closed, label, func))


# def using_Grouper(df, freq='5T', col='low', closed='right', label='right'):
def using_Grouper(df, freq='5T', col='low', closed='right', label='right'):
    func = {}
    if col == 'all':
        for k in df.columns:
            if k in list(multiIndex_func.keys()):
                if k == 'close':
                    func[k] = 'last'
                else:
                    func[k] = multiIndex_func[k]

    elif isinstance(col, list):
        for k in col:
            if k in list(multiIndex_func.keys()):
                func[k] = multiIndex_func[k]
    else:
        if col in list(multiIndex_func.keys()):
            func[col] = multiIndex_func[col]
    level_values = df.index.get_level_values
    return (df.groupby([level_values(i) for i in [0]] + [pd.Grouper(freq=freq, level=-1, closed=closed, label=label)]).agg(func))

def fix_start_end_datetime_for_index(df, start, end, index='ticktime', datev=None):
    """
    Auto-complete start and end datetimes based on MultiIndex date level.
    Return as pd.Timestamp
    """
    lvl = df.index.get_level_values(index)
    if len(lvl) == 0:
        today = pd.Timestamp.now().normalize()
        base_date = today.strftime('%Y-%m-%d')
    else:
        base_date = str(lvl[-1])[:10]

    def to_timestamp(t):
        if t is None:
            return None
        t = str(t)
        if len(t) <= 8:  # only HH:MM:SS
            t = f"{base_date} {t}"
        return pd.Timestamp(t)

    start_ts = to_timestamp(start)
    end_ts   = to_timestamp(end)
    return start_ts, end_ts


def select_multiIndex_index_fast(df, index='ticktime', start=None, end=None, datev=None, code=None):
    """
    极速版 MultiIndex 时间/代码筛选 (兼容 Timestamp 类型 index)
    
    参数:
        df      : MultiIndex DataFrame，index 为 ['code', 'ticktime']
        index   : 用于筛选的 level 名称，默认 'ticktime'
        start   : 起始时间，可以是 'HH:MM:SS' 或完整日期时间字符串
        end     : 结束时间，可以是 'HH:MM:SS' 或完整日期时间字符串
        datev   : 可选日期，用于补全 start/end
        code    : 可选股票代码，直接筛选 code level

    返回:
        筛选后的 DataFrame
    """
    if df is None or df.empty:
        return df

    lvl = df.index.get_level_values(index)

    # -------- 补齐 start/end 时间，兼容 Timestamp --------
    def fix_datetime(t):
        if t is None:
            return None
        t = str(t)
        if len(t) <= 10:  # 只有时间部分
            # 用第一行日期补齐
            base_date = str(lvl[0])[:10]
            t = f"{base_date} {t}"
        return pd.Timestamp(t)

    start_ts = fix_datetime(start)
    end_ts   = fix_datetime(end)
    # print(f'start_ts : {start_ts} end_ts : {end_ts}')
    # import ipdb;ipdb.set_trace()

    # -------- code level 快速过滤 --------
    if code is not None:
        df = df.xs(code, level="code", drop_level=False)

    lvl = df.index.get_level_values(index)

    # -------- 时间区间过滤 --------
    if start_ts is not None and end_ts is not None:
        mask = (lvl >= start_ts) & (lvl <= end_ts)
        return df[mask]
    elif start_ts is not None:
        mask = lvl >= start_ts
        return df[mask]
    elif end_ts is not None:
        mask = lvl <= end_ts
        return df[mask]

    return df



# def select_multiIndex_index(df, index='ticktime', start=None, end=None, datev=None, code=None):
#     # df = df[df.index.duplicated()]

#     # df = df.drop_duplicates('volume')
#     print(df.index)
#     print(type(df.index.get_level_values("ticktime")[0]))

#     if len(str(df.index.get_level_values(1)[-1])) > 10:
#         index_date = str(df.index.get_level_values(1)[-1])[:10]
#     else:
#         index_date = None
#     if index != 'date' and code is None:
#         if start is not None and len(start) < 10:
#             if datev is None:
#                 if index_date != None:
#                     start = index_date + ' ' + start
#                 else:
#                     start = get_today() + ' ' + start
#             else:
#                 start = day8_to_day10(datev) + ' ' + start
#             if end is None:
#                 end = start
#         else:
#             if end is None:
#                 end = start
#         if end is not None and len(end) < 10:
#             if datev is None:
#                 if index_date != None:
#                     end = index_date + ' ' + end
#                 else:
#                     end = get_today() + ' ' + end
#                 if start is None:
#                     start = get_today(sep='-') + ' ' + '09:25:00'
#             else:
#                 end = day8_to_day10(datev) + ' ' + end
#                 if start is None:
#                     start = day8_to_day10(datev) + ' ' + '09:25:00'
#         else:
#             if start is None:
#                 if end is None:
#                     if index_date != None:
#                         start = index_date + ' ' + '09:25:00'
#                         end = index_date + ' ' + '09:45:00'
#                         log.error("start and end is None to 930 and 945")
#                     else:
#                         start = get_today(sep='-') + ' ' + '09:25:00'
#                         end = get_today(sep='-') + ' ' + '09:45:00'
#                         log.error("start and end is None to 930 and 945")
#                 else:
#                     start = end
#     else:
#         start = day8_to_day10(start)
#         end = day8_to_day10(end)

#     if code is not None:
#         if start is None:
#             if index_date != None:
#                 start = index_date + ' ' + '09:24:30'
#             else:
#                 start = get_today(sep='-') + ' ' + '09:24:30'
#         else:
#             start = day8_to_day10(start) + ' ' + '09:24:30'
#         # df = df[(df.index.get_level_values('code') == code) & (df.index.get_level_values(index) > start)]
#         df = df[(df.index.get_level_values('code') == code)]

#     if start is None and end is not None:
#         df = df[(df.index.get_level_values(index) <= end)]
#     elif start is not None and end is None:
#         df = df[(df.index.get_level_values(index) >= start)]
#     elif start is not None and end is not None:
#         idx = df.index.get_level_values(index)[0] if len(df.index.get_level_values(index)) > 0 else 0
#         idx_end = pd.Timestamp(end) if index == 'ticktime' else end
#         log.info("idx:%s idx<=end:%s" % (idx, idx <= idx_end))
#         if idx <= idx_end:
#             df = df[(df.index.get_level_values(index) >= start) & (df.index.get_level_values(index) <= end)]
#         else:
#             df = df[(df.index.get_level_values(index) >= start)]
#     else:
#         log.info("start end is None")
#     return df


def from_list_to_dict(col: Union[List[str], Dict[str, str], str], func_dict: Dict[str, str]) -> Dict[str, str]:
    func: Dict[str, str] = {}
    if isinstance(col, list):
        for k in col:
            if k in list(func_dict.keys()):
                func[k] = func_dict[k]
    elif isinstance(col, dict):
        func = col
    else:
        if col in list(func_dict.keys()):
            func[col] = func_dict[col]
    return func


# def get_limit_multiIndex_Row_fast(df, col=None, index='ticktime', start=None, end='10:00:00'):

#     if df is None or df.empty:
#         log.error("df is None or empty")
#         return df

#     # 1. 使用 xs(slice) 在 MultiIndex 上按时间过滤（最快）
#     try:
#         df_slice = df.xs(slice(start, end), level=index, drop_level=False)
#     except:
#         return df.iloc[0:0]  # 返回空集，无报错

#     if df_slice.empty:
#         return df_slice

#     # 2. 如果未指定 col，则直接返回原切片
#     if col is None:
#         return df_slice

#     # 3. 获取每个 code 的最后一条记录
#     df_last = df_slice.groupby(level=0).last()

#     # 4. 重命名列（使用 multiIndex_func 映射）
#     func = from_list_to_dict(col, multiIndex_func)
#     df_last = df_last.rename(columns=func)

#     # 5. 返回指定字段
#     now_cols = list(func.values())

#     return df_last[now_cols]

def fast_multiIndex_agg(df, func_map=None):
    """
    MultiIndex 快速聚合（按 code 聚合 ticktime）
    
    Args:
        df (pd.DataFrame): MultiIndex DataFrame, index=['code','ticktime']
        func_map (dict): 聚合映射，例如:
            {'close':'mean', 'low':'min', 'high':'max', 'volume':'last', 'open':'first'}
    
    Returns:
        pd.DataFrame: 聚合后的 DataFrame, index=code
    """
    if df is None or df.empty:
        return df
    
    if func_map is None:
        func_map = {'close':'mean', 'low':'min', 'high':'max', 'volume':'last', 'open':'first'}
    
    # 只保留需要的列
    selected_cols = [c for c in func_map.keys() if c in df.columns]
    df_sel = df[selected_cols]
    
    # 分别处理 last/first 列，其他列用 agg
    last_first_cols = {k:v for k,v in func_map.items() if v in ['last','first']}
    other_cols = {k:v for k,v in func_map.items() if v not in ['last','first']}
    
    agg_result = {}
    
    # 处理 last/first
    for col, agg_type in last_first_cols.items():
        if agg_type == 'last':
            agg_result[col] = df_sel.groupby(level=0, sort=False)[col].nth(-1)
        elif agg_type == 'first':
            agg_result[col] = df_sel.groupby(level=0, sort=False)[col].nth(0)
    
    # 处理其他聚合
    if other_cols:
        df_other = df_sel[list(other_cols.keys())].groupby(level=0, sort=False).agg(other_cols)
        for c in df_other.columns:
            agg_result[c] = df_other[c]
    
    # 合并结果
    result = pd.DataFrame(agg_result)
    return result


def get_limit_multiIndex_Row(df, col=None, index='ticktime', start=None, end='10:00:00'):
    """[summary]

    [description]

    Arguments:
        df {[type]} -- [description]

    Keyword Arguments:
        col {[type]} -- [description] (default: {None})
        index {str} -- [description] (default: {'ticktime'})
        start {[type]} -- [description] (default: {None})
        end {str} -- [description] (default: {'10:00:00'})

    Returns:
        [type] -- [description]
    """
    if df is not None:
        # df = select_multiIndex_index(df, index=index, start=start, end=end)
        df = select_multiIndex_index_fast(df, index=index, start=start, end=end)

    else:
        log.error("df is None")
    # if col is not None:
    #     func = from_list_to_dict(col, multiIndex_func)
    #     # func = {
    #     #     'close': 'mean',
    #     #     'low': 'min',
    #     #     'high': 'max',
    #     #     'volume': 'last',
    #     #     'open': 'first'
    #     # }
    #     df = df.groupby(level=[0]).agg(func)
    # else:
    #     log.info('col is None')

    if col is not None:
        func = from_list_to_dict(col, multiIndex_func)
        # 使用快速聚合替代原来的 groupby+agg
        df = fast_multiIndex_agg(df, func_map=func)
    else:
        log.info('col is None')
    # import ipdb;ipdb.set_trace()
    
    return df



def get_limit_multiIndex_freq(df, freq='5T', col='low', index='ticktime', start='09:25:00', end='10:00:00', code=None):
    # quotes = cct.get_limit_multiIndex_freq(h5, freq=resample.upper(), col='all', start=start, end=end, code=code)
    # isinstance(spp.all_10.index[:1], pd.core.index.MultiIndex)
    if df is not None:
        if start is None:
            start = '09:25:00'
        dd = select_multiIndex_index_fast(df, index=index, start=start, end=end, code=code)
        if code is not None:
            df = dd.copy()
            df['open'] =  dd['close']
            df['high'] =  dd['close']
            df['low'] =  dd['close']
        else:
            df = dd.copy()
    else:
        log.error("df is None")
    # print df.loc['600007',['close','ticktime']]
    if freq is not None and col is not None:
        if col == 'all':
            vol0 = df.volume[0]
            df['volume'] = df.volume - df.volume.shift(1)
            df['volume'][0] = vol0
            # vol0 = df.loc[:, 'volume'][0]
            # df.loc[:,'volume'] = df.volume - df.volume.shift(1)
            # df.loc[:, 'volume'][0] = vol0
        df = using_Grouper(df, freq=freq, col=col)
        # print df.loc['600007',['close','low','high','ticktime']]
    else:
        log.info('freq is None')
    # df = select_multiIndex_index(df, index=index, start=start, end=end)
    # if col == 'close':
        # df.rename(columns={'close': 'low'}, inplace=True)
    return df


def get_stock_tdx_period_to_type(stock_data, type='w'):
    period_type = type
    stock_data.index = pd.to_datetime(stock_data.index)
    period_stock_data = stock_data.resample(period_type).last()
    # 周数据的每日change连续相乘
    # period_stock_data['percent']=stock_data['percent'].resample(period_type,how=lambda x:(x+1.0).prod()-1.0)
    # 周数据open等于第一日
    period_stock_data['open'] = stock_data['open'].resample(period_type).first()
    # 周high等于Max high
    period_stock_data['high'] = stock_data['high'].resample(period_type).max()
    period_stock_data['low'] = stock_data['low'].resample(period_type).min()
    # volume等于所有数据和
    period_stock_data['amount'] = stock_data['amount'].resample(period_type).sum()
    period_stock_data['vol'] = stock_data['vol'].resample(period_type).sum()
    # 计算周线turnover,【traded_market_value】 流通市值【market_value】 总市值【turnover】 换手率，成交量/流通股本
    # period_stock_data['turnover']=period_stock_data['vol']/(period_stock_data['traded_market_value'])/period_stock_data['close']
    # 去除无交易纪录
    period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data.reset_index(inplace=True)
    return period_stock_data


def MoniterArgmain():

    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
                        help='DateType')
    parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
                        help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
                        help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
                        help='find duration low')
    return parser

# def writeArgmainParser(args,defaul_all=30):
#     # from ConfigParser import ConfigParser
#     # import shlex
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument('code', type=str, nargs='?', help='w or a or all')
#     parser.add_argument('dl', nargs='?', type=str, help='1,5,10',default=ct.writeCount)
#     parser.add_argument('end', nargs='?', type=str, help='1,5,10',default=None)
#     arg_t = parser.parse_args(args)
#     if arg_t.dl == 'all':
#         # print arg_t.dl
#         arg_t.dl = defaul_all
#     # print arg_t.dl
#     return arg_t

def writeArgmain_block():
    # from ConfigParser import ConfigParser
    # import shlex
    parser = argparse.ArgumentParser()
    parser.add_argument('code', type=str, nargs='?', help='w or a or all')
    parser.add_argument('dl', nargs='?', type=str, help='1,5,10', default=ct.writeCount)
    parser.add_argument('blk', nargs='?', type=str, help='064,065', default=None)
    return parser

def writeArgmain():
    # from ConfigParser import ConfigParser
    # import shlex
    parser = argparse.ArgumentParser()
    parser.add_argument('code', type=str, nargs='?', help='w or a or all')
    parser.add_argument('dl', nargs='?', type=str, help='1,5,10', default=ct.writeCount)
    parser.add_argument('end', nargs='?', type=str, help='1,5,10', default=None)
    # if parser.code == 'all':
    #     print parser.dl
    # parser.add_argument('end', nargs='?', type=str, help='20160101')
    # parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
    #                     help='DateType')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['f', 'b'], default='f',
    #                     help='Price Forward or back')
    # parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['high', 'low', 'close'], default='low',
    #                     help='price type')
    # parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
    #                     help='find duration low')
    # parser.add_argument('-l', action="store", dest="dl", type=int, default=None,
    #                     help='dl')
    # parser.add_argument('-dl', action="store", dest="days", type=int, default=1,
    #                     help='days')
    # parser.add_argument('-m', action="store", dest="mpl", type=str, default='y',
    #                     help='mpl show')
    return parser


def DurationArgmain():
    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    # parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    # parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
    #                     help='DateType')
    # parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
    #                     help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
    # help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='n',
                        help='filter low')
    return parser

# def RawMenuArgmain():
#     raw = 'status:[go(g),clear(c),[d 20150101 [l|h]|[y|n|pn|py],quit(q),W(a),sh]:'
#     raw_input_menu=raw+"\n\tNow : %s"+"\n\t1:Sort By Percent\t2:Sort By DFF\t3:Sort By OPRa\t\n\t4:Sort By Ra \t\t5:Sort by Counts\nplease input:"
#     return raw_input_menu


def LineArgmain():
    # from ConfigParser import ConfigParser
    # import shlex
    # parser = argparse.ArgumentParser()
    # parser.add_argument('-s', '--start', type=int, dest='start',
    # help='Start date', required=True)
    # parser.add_argument('-e', '--end', type=int, dest='end',
    # help='End date', required=True)
    # parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
    # help='Enable debug info')
    # parser.add_argument('foo', type=int, choices=xrange(5, 10))
    # args = parser.parse_args()
    # print args.square**2
    parser = argparse.ArgumentParser()
    # parser = argparse.ArgumentParser(description='LinearRegression Show')
    parser.add_argument('code', type=str, nargs='?', help='999999')
    parser.add_argument('start', nargs='?', type=str, help='20150612')
    # parser.add_argument('e', nargs='?',action="store", dest="end", type=str, help='end')
    parser.add_argument('end', nargs='?', type=str, help='20160101')
    parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['d', 'w', 'm'], default='d',
                        help='DateType')
    parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['f', 'b'], default='f',
                        help='Price Forward or back')
    # parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low','open','close'], default='close',
    parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['high', 'low', 'close'], default='close',
                        help='type')
    parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='y',
                        help='find duration low')
    # parser.add_argument('-help',type=str,help='Price Forward or back')
    # args = parser.parse_args()
    # args=parser.parse_args(input)
    # parser = parseArgmain()
    # args = parser.parse_args(num_input.split())

    # def getArgs():
    # parse=argparse.ArgumentParser()
    # parse.add_argument('-u',type=str)
    # parse.add_argument('-d',type=str)
    # parse.add_argument('-o',type=str)
    # args=parse.parse_args()
    # return vars(args)
    # if args.verbose:
    # logger.setLevel(logging.DEBUG)
    # else:
    # logger.setLevel(logging.ERROR)
    return parser


# def negate_boolean_list(negate_list, idx=1):
#     cout_all = len(negate_list)
#     if idx < cout_all:
#         sort_negate_l = [key ^ 1 for key in negate_list[:idx]]
#         sort_negate_l.extend(negate_list[idx:])
#     else:
#         sort_negate_l = [key ^ 1 for key in negate_list]

#     return sort_negate_l


def sort_by_value(df, column='dff', file=None, count=5, num=5, asc=0):
    """[summary]

    [description]

    Arguments:
        df {dataframe} -- [description]

    Keyword Arguments:
        column {str} -- [description] (default: 'dff' or ['dff',])
        file {[type]} -- [description] (default: {069})
        count {number} -- [description] (default: {5})
        num {number} -- [description] (default: {5})
        asc {number} -- [description] (default: {1} or [0,1])

    Returns:
        [type] -- [description]
    """
    if not isinstance(column, list):
        dd = df.sort_values(by=[column], ascending=[asc])
    else:
        dd = df.sort_values(by=column, ascending=asc)
    if file is None:
        if num > 0:
            print(dd.iloc[0:num, 0:10])
            print(dd.iloc[0:num, 31:40])
            print(dd.iloc[0:num, -15:-4])
        else:
            print(dd.iloc[num::, 0:10])
            print(dd.iloc[0:num, 31:40])
            print(dd.iloc[num::, -15:-4])
        return dd
    else:
        if str(count) == 'all':
            write_to_blocknew(file, dd.index.tolist(), append=True)
        else:
            write_to_blocknew(file, dd.index.tolist()[:int(count)], append=True)
        print("file:%s" % (file))


def get_col_in_columns(df, idx_value, key):
    """[summary]

    [description]

    Arguments:
        df {[type]} -- [description]
        idx_value {[type]} -- [perc%sd]
        key {[type]} -- [9]

    Returns:
        [type] -- [description]
    """
    idx_k = 1
    # for inx in range(int(key) - 1, 1, -1): stock_filter
    for inx in range(int(key), 1, -1):
        if idx_value % inx in df.columns:
            idx_k = inx
            break
    return idx_k


def get_diff_dratio(mainlist, sublist):
    dif_co = list(set(mainlist) & set(sublist))
    dratio = round((float(len(sublist)) - float(len(dif_co))) / float(len(sublist)), 2)
    log.info("dratio all:%s :%s %0.2f" % (len(sublist), len(sublist) - len(dif_co), dratio))
    return dratio


# def func_compute_percd(c, lp, lc, lh, ll, nh, nl,llp):
def func_compute_percd(close, lastp, op, lasth, lastl, nowh, nowl):
    initc = 0
    down_zero, down_dn, percent_l = 0, 0, 2
    # da, down_zero, down_dn, percent_l = 1, 0, 0, 2
    initc = 1 if (c - lc) / lc * 100 >= 1 else down_dn
    # n_p = (c - lc) / lc * 100
    # n_hp = nh - lh
    # n_lp = nl - ll
    # if n_p >= 0:
    #     if n_p > percent_l and n_hp > 0:
    #         initc += 2
    #     else:
    #         initc += 1
    #     if lp > 0 and n_lp > 0:
    #         initc += 1
    # else:
    #     if n_p < -percent_l and n_hp < 0:
    #         initc -= 2
    #     else:
    #         initc -= 1
    #     if lp < 0 and n_lp < 0:
    #         initc -= 1
    return initc



# import numba as nb
# @numba.jit(nopython=True)
# @nb.autojit
def func_compute_percd2020( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']

    initc = 0
    if  0 < lastclose < 1000 and lasthigh != 1.0 and lastlow != 1.0 and lasthigh != 0 and lastlow != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        if open >= lastclose and close == high and close > ma5:
            initc +=3
            if close > ma5:
                if close < ma5*1.1:
                    initc +=3*vol_du
                elif close < ma5*1.2:
                    initc +=2*vol_du
                else:
                    initc+=2

        elif percent > 2 and low > lastlow and high > lasthigh:
            initc +=2

        elif percent > 2 and close_du > 9 and vol_du > 2:
            initc += 1*vol_du
        elif percent > 2 :
            initc +=1
        elif open > ma5 and open > ma10 :
            initc +=0.1
            if  vol_du < 0.6:
                initc +=0.1
        elif percent < -2 and low < lastlow and high < lasthigh:
            initc -=1
        elif percent < -5:
            initc -=2
        elif close < ma5 and close < ma10:
            initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=1


    return initc
def get_col_market_value_df(df,col,market_value):
    if int(market_value) < 10:
        re_str = "%s[1-%s]d$"%(col,market_value)
        temp = df.filter(regex=re_str, axis=1)
        # temp =df.loc[:,df.columns.str.contains( "%s[1-%s]d$"%(col,market_value),regex= True)]
        # temp =df.loc[:,df.columns.str.contains( "%s[1-%s]d$"%(col,market_value),regex= True)]
    else:
        if int(market_value) <= ct.compute_lastdays:
                _remainder = int(market_value)%10
        else:
            _remainder = int(ct.compute_lastdays)%10
        # df.loc[:,df.columns.str.contains( "%s[0-9][0-%s]d$"%(col,_remainder),regex= True)][:1]
        # temp =df.loc[:,df.columns.str.contains( "%s([1-9]|1[0-%s])d$"%(col,_remainder),regex= True)]
        re_str = "%s([1-9]|1[0-%s])d$"%(col,_remainder)
        temp = df.filter(regex=re_str, axis=1)
        # temp =df.loc[:,df.columns.str.contains(re_str,regex= True)]

    return temp

def func_compute_percd2024( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None,high4=None,max5=None,hmax=None,lastdu4=None,code=None):
    initc = 0
    percent_idx = 2
    vol_du_idx = 1.2
    close_du = 0
    vol_du = 0
    top_max_up = 10

    if np.isnan(lastclose):
        percent = round((close - open)/open*100,1)
        lastp = 0
    else:
        percent = round((close - lastclose)/lastclose*100,1)
        lastp = round((lastclose - lastopen)/lastclose*100,1)

    if  low > 0 and  lastclose > 0 and lastvol > 0 and lasthigh > 1.0 and lastlow > 1.0 and lasthigh > 0 and lastlow > 0:
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        # if idate == "2022-11-28":

        if (percent > percent_idx and low > lastlow and (close_du > percent_idx or vol_du > vol_du_idx)) or (high > lasthigh and (low > lastlow and close > ma5) ):
            initc +=1
            # if  close_du > 5:
            #     initc +=0.1
        # elif percent < -percent_idx or (percent < 0 and close_du > 3):
        elif percent < -percent_idx:
            initc -=1
            # if close > open:
            #     #下跌中继,或者止跌信号
            #     initc +=3
            # if  close_du > 5:
            #     initc -=0.1

        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=percent
        else:
            initc -=percent

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None

    if  np.isnan(lastclose):
        if percent > 3 and close > ma5 and high > ma10:
            initc +=2
    else:

        if close > lasthigh:
            initc +=0.1
            # if  ma5 > ma10:
            #     initc +=0.1
            # else:
            #     initc -=0.11
        elif close < lastlow:
            initc -=0.1

        if low > lastlow:
            initc +=0.1
            if high >lasthigh:
                initc +=0.1
                
        if high > lasthigh and close > lasthigh and percent > 3 and ma5 > ma10:

            if lastp < -2:
                initc +=12
            else:
                initc +=2
            if (open >= low or (open >lastclose and close > lasthigh)) and close >= high*0.92:
                initc +=2
                if lastclose >= lasthigh*0.98 or lastclose > (lasthigh + lastlow)/2:
                    initc +=2
                    if close_du > 5 and vol_du > 0.8 and vol_du < 2.2:
                        initc +=5
            elif low > lasthigh:
                initc +=2
            elif close == high:
                initc +=1

            if hmax is not None and high >= hmax:
                # if idate == '300093':
                #     import ipdb;ipdb.set_trace()

                if high4 is not None and max5 is not None:
                    if hmax > high4 and high4 > max5:
                        initc +=10
                else:
                    initc +=3

            if high4 is not None and (high >= high4 or (get_work_time_duration() and high >high4)):

                if lastdu4 is not None:
                    if lastdu4 <= 1.12:
                        initc +=3
                    elif lastdu4 > 1.12 and lastdu4 <= 1.21:
                        initc +=2
                    elif lastdu4 > 1.21 and lastdu4 <= 1.31:
                        initc +=2
                    elif lastdu4 > 1.31 and lastdu4 <= 1.5:
                        initc +=2
                    else:
                        initc +=1

                if max5 is not None and high >= max5:
                    initc +=2
                    # if hmax is not None and close > hmax:
                    #     initc +=3
                    #     lastMax = max(high4,max5,hmax)
                    #     if close >= lastMax and lastclose < lastMax or (not get_work_time_duration() and high >=lastMax):
                    #         if lastdu4 is not None:
                    #             if lastdu4 <= 1.05:
                    #                 initc +=10
                    #             elif lastdu4 > 1.05 and lastdu4 <= 1.1:
                    #                 initc +=8
                    #             elif lastdu4 > 1.1 and lastdu4 <= 1.2:
                    #                 initc +=5
                    #             elif lastdu4 > 1.2 and lastdu4 <= 1.3:
                    #                 initc +=3
                    #             else:
                    #                 initc +=2
                    #         else:
                    #             initc +=1
                    #     else:
                    #         initc +=3
                    #     if close == high:
                    #         initc +=2
                    #     elif close >=high*0.99:
                    #         initc +=2

            # if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
            if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
                initc +=percent
                if high4 is not None and hmax is not None:
                    lastMax = max(high4,max5,hmax)
                    if lasthigh >= lastMax:
                        # initc += 5 + abs(lastp)
                        initc += 2 + abs(lastp)
                    if lastMax==hmax and high4 > max5 and high4 < hmax:
                        initc += 1

    if GlobalValues().getkey('percdf') is not None:
        # if code == '601857':
        #     import ipdb;ipdb.set_trace()
        if code in GlobalValues().getkey('percdf').index:
            lastdf = GlobalValues().getkey('percdf').loc[code]
            if percent > 2:
                if lastdf.lasth1d < lastdf.lasth2d < lastdf.lasth3d:
                    if close > lastdf.lasth1d:
                        initc += 3
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 2
                            
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 2
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 2
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 3
                elif lastdf.lasth2d < lastdf.lasth3d < lastdf.lasth4d:
                    if close > lastdf.lasth1d > lastdf.lasth2d:
                        initc += 2
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 2
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 2
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 2
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 2
                                     
                elif lastdf.lasth1d > lastdf.lasth2d > lastdf.lasth3d and lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02 :
                    initc += 3
                    if lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02:
                        initc += 2

        # else:
        #     log.info("check lowest in percdf:%s"%(code))
            # print("lowest:%s"%(code),end=' ')

    return round(initc,1)



def func_compute_percd2021_vectorized(dd):
    """
    向量化计算股票综合评分，逻辑对应 func_compute_percd2021
    假设 df 中包含以下列：
    ['open', 'close', 'high', 'low', 'last_open', 'last_close', 'last_high', 'last_low',
     'ma5d', 'ma10d', 'vol', 'last_vol', 'upper', 'high4', 'max5', 'hmax', 'lastdu4', 'code']
    """

    df = dd.copy()
    df['last_open']  = df['open'].shift(1)
    df['last_close'] = df['close'].shift(1)
    df['last_high']  = df['high'].shift(1)
    df['last_low']   = df['low'].shift(1)
    df['last_vol']   = df['vol'].shift(1)
    score = pd.Series(0.0, index=df.index)

    # 基础数据
    percent_change = (df['close'] - df['last_close']) / df['last_close'] * 100
    vol_ratio = df['vol'] / df['last_vol']
    valid_mask = (~df['last_close'].isna()) & (df['last_close'] != 0) & (~df['last_vol'].isna()) & (df['last_vol'] != 0)
    score.loc[~valid_mask] = 0.0

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    mask_outer = valid_mask & (df['high'] > df['high4']) & (percent_change > 5) & (df['last_close'] < df['high4'])
    mask_inner = mask_outer & (df['high'] >= df['open']) & (df['open'] > df['last_close']) & \
                 (df['close'] > df['last_close']) & (df['close'] >= df['high']*0.99) & \
                 ((df['high'] < df['hmax']) | (df['last_high'] < df['hmax']))

    # 市场前缀加分
    for prefix, high_score, low_score in [('6',25,20), ('0',25,20), ('3',35,20), ('688',35,18), ('8',35,18)]:
        mask = mask_inner & df['code'].astype(str).str.startswith(prefix)
        score.loc[mask & (percent_change >= 5)] += high_score
        score.loc[mask & (percent_change < 5)] += low_score

    mask_other = mask_inner & ~(df['code'].astype(str).str.startswith(('6','0','3','688','8')))
    score.loc[mask_other] += 15.0

    # 外层非高开高走安全启动加分
    score.loc[mask_outer] += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    score.loc[valid_mask & (df['close'] > df['last_close'])] += 1.0
    score.loc[valid_mask & (df['high'] > df['last_high'])] += 1.0
    score.loc[valid_mask & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (vol_ratio > 2) & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (df['low'] > df['last_low'])] += 1.0
    score.loc[valid_mask & (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['open'] > df['last_high']) & (df['close'] > df['open']) &
              (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['close'] >= df['upper'])] += 5.0
    score.loc[valid_mask & (1.0 < vol_ratio) & (vol_ratio < 2.0)] += 2.0
    score.loc[valid_mask & (df['high'] > df['high4'])] += 3.0
    score.loc[valid_mask & (percent_change > 3) & (df['close'] >= df['high']*0.95) &
              (df['high'] > df['max5']) & (df['high'] > df['high4'])] += 5.0
    score.loc[valid_mask & (df['hmax'].notna()) & (df['high'] >= df['hmax'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high']) & (df['close'] > df['open'])] += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    mask_low_open = valid_mask & (df['open'] == df['low'])
    score.loc[mask_low_open & (df['open'] < df['last_close']) & (df['open'] >= df['ma5d']) & (df['close'] > df['open'])] += 15.0
    score.loc[mask_low_open & (df['close'] > df['open'])] += 8.0
    score.loc[mask_low_open & (vol_ratio > 2)] += 5.0
    score.loc[valid_mask & (percent_change > 5)] += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    score.loc[valid_mask & (df['close'] < df['last_close'])] -= 1.0
    score.loc[valid_mask & (df['low'] < df['last_low'])] -= 3.0
    score.loc[valid_mask & (df['close'] < df['last_close']) & (df['vol'] > df['last_vol'])] -= 8.0
    score.loc[valid_mask & (df['last_close'] >= df['ma5d']) & (df['close'] < df['ma5d'])] -= 5.0
    score.loc[valid_mask & (df['last_close'] >= df['ma10d']) & (df['close'] < df['ma10d'])] -= 8.0
    score.loc[valid_mask & (df['open'] > df['close'])] -= 5.0
    score.loc[valid_mask & (df['open'] > df['close']) & ((df['close'] < df['ma5d']) | (df['close'] < df['ma10d']))] -= 5.0
    score.loc[valid_mask & (df['open'] == df['high'])] -= 10.0
    score.loc[valid_mask & (percent_change < -5)] -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    mask_du4_1 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] <= 15)
    mask_du4_2 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] > 15) & (df['lastdu4'] <= 40)
    score.loc[mask_du4_1] += 30
    score.loc[mask_du4_2] += 18

    return score

def func_compute_percd2021(open, close, high, low,
                           last_open, last_close, last_high, last_low,
                           ma5, ma10, now_vol, last_vol,
                           upper, high4, max5, hmax,
                           lastdu4, code, idate=None):
    init_c = 0.0
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    if high > high4 and percent_change > 5 and last_close < high4:
        if high >= open > last_close and close > last_close and close >= high*0.99 and (high < hmax or last_high < hmax):
            if str(code).startswith(('6','0')):
                if percent_change >= 5:
                    init_c += 25.0
                else:
                    init_c += 20.0
            elif str(code).startswith('3'):
                if percent_change >= 6:
                    init_c += 35.0
                else:
                    init_c += 20.0
            elif str(code).startswith(('688','8')):
                if percent_change >= 5:
                    init_c += 35.0
                else:
                    init_c += 20.0
            else:
                init_c += 15.0
            if vol_ratio < 2:
                init_c += 15.0
            else:
                init_c += 2.0
        else:
            init_c += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1.0
    if high > last_high:
        init_c += 1.0
    if close >= high*0.998:
        init_c += 5.0
        if vol_ratio > 2:
            init_c += 5.0
    if low > last_low:
        init_c += 1.0
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    if high > high4:
        init_c += 3.0
    if percent_change > 3 and close >= high * 0.95 and high > max5 and high > high4:
        init_c += 5.0
    if hmax is not None and high >= hmax:
        init_c += 20.0
    if low > last_high:
        init_c += 20.0
        if close > open:
            init_c += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0
        if close > open:
            init_c += 8.0
        if vol_ratio > 2:
            init_c += 5.0
    if percent_change > 5:
        init_c += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1.0
    if low < last_low:
        init_c -= 3.0
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
    if open == high:
        init_c -= 10.0
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 15:
            init_c += 30
        elif 15 < lastdu4 <=40:
            init_c += 18

    return init_c

def func_compute_percd2021_google(open, close, high, low, last_open, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, high4, max5, hmax, lastdu4, code, idate=None):
    """
    根据一系列股票交易行为计算综合得分。

    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_open (float): 昨日开盘价 (虽然未使用，但参数保留以匹配顺序)
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        hmax (float): 历史最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
        idate (str): 日期 (可选)

    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）
    if close == high:
        init_c += 5.0
        if vol_ratio > 2: # 配合放量涨停给更高分
            init_c += 5.0

    # 最低价大于前日最低价
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
        
    # 成交量温和上涨
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破
    if hmax is not None and high >= hmax:
        init_c += 20.0 # 突破历史高点给最高分

    # 每日高开高走，无价格重叠 (low > last_high)
    if low > last_high:
        init_c += 20.0 # 强势跳空，权重最高
        if close > open:
            init_c += 5.0
            
    # 开盘价就是最低价 (open == low) 加分
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0 # 低开高走且开盘在 ma5 之上，强启动
        elif close > open:
            init_c += 8.0 # 只要是开盘即最低的上涨，都加分
        if vol_ratio > 2: # 配合放量再加分
            init_c += 5.0
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 8.0
    
    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）
    if low < last_low:
        init_c -= 3.0
        
    # 放量下跌（下跌且成交量大于昨日）
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0 # 权重更高
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0

    # 高开低走 (open > close) 减分
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
            
    # 开盘价就是最高价 (open == high) 减分
    if open == high:
        init_c -= 10.0 # 当天走势疲弱，最高分时减分
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 原始代码中关于 lastdu4 的逻辑 (保持不变)
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c
    
def func_compute_percd2021_nogoogle( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,high4=None,max5=None,hmax=None,lastdu4=None,code=None,idate=None):
    initc = 0
    percent_idx = 2
    vol_du_idx = 1.2
    close_du = 0
    vol_du = 0
    top_max_up = 10
    if np.isnan(lastclose) or lastclose == 0:
        return 0
    if np.isnan(lastclose):
        percent = round((close - open)/open*100,1)
        lastp = 0
    else:
        percent = round((close - lastclose)/lastclose*100,1)
        lastp = round((lastclose - lastopen)/lastclose*100,1)

        
    if  low > 0 and  lastclose > 0 and lastvol > 0 and lasthigh > 1.0 and lastlow > 1.0 and lasthigh > 0 and lastlow > 0:
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        # if idate == "2022-11-28":

        if (percent > percent_idx and low > lastlow and (close_du > percent_idx or vol_du > vol_du_idx)) or (high > lasthigh and (low > lastlow and close > ma5) ):
            initc +=1
            # if  close_du > 5:
            #     initc +=0.1
        # elif percent < -percent_idx or (percent < 0 and close_du > 3):
        elif percent < -percent_idx:
            initc -=1
            # if close > open:
            #     #下跌中继,或者止跌信号
            #     initc +=3
            # if  close_du > 5:
            #     initc -=0.1

        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=percent
        else:
            initc -=percent

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None

    if  np.isnan(lastclose):
        if percent > 3 and close > ma5 and high > ma10:
            initc +=2
    else:

        if close > lasthigh:
            initc +=0.1
            # if  ma5 > ma10:
            #     initc +=0.1
            # else:
            #     initc -=0.11
        elif close < lastlow:
            initc -=0.1

        if low > lastlow:
            initc +=0.1
            if high >lasthigh:
                initc +=0.1
                
        if high > lasthigh and close > lasthigh and percent > 3 and ma5 > ma10:

            if lastp < -2:
                initc +=12
            else:
                initc +=2
            if (open >= low or (open >lastclose and close > lasthigh)) and close >= high*0.92:
                initc +=2
                if lastclose >= lasthigh*0.98 or lastclose > (lasthigh + lastlow)/2:
                    initc +=2
                    if close_du > 5 and vol_du > 0.8 and vol_du < 2.2:
                        initc +=5
            elif low > lasthigh:
                initc +=2
            elif close == high:
                initc +=1

            if hmax is not None and high >= hmax:
                # if idate == '300093':
                #     import ipdb;ipdb.set_trace()

                if high4 is not None and max5 is not None:
                    if hmax > high4 and high4 > max5:
                        initc +=10
                else:
                    initc +=3

            if high4 is not None and (high >= high4 or (get_work_time_duration() and high >high4)):

                if lastdu4 is not None:
                    if lastdu4 <= 1.12:
                        initc +=10
                    elif lastdu4 > 1.12 and lastdu4 <= 1.21:
                        initc +=8
                    elif lastdu4 > 1.21 and lastdu4 <= 1.31:
                        initc +=5
                    elif lastdu4 > 1.31 and lastdu4 <= 1.5:
                        initc +=3
                    else:
                        initc +=2

                if max5 is not None and high >= max5:
                    initc +=5
                    # if hmax is not None and close > hmax:
                    #     initc +=3
                    #     lastMax = max(high4,max5,hmax)
                    #     if close >= lastMax and lastclose < lastMax or (not get_work_time_duration() and high >=lastMax):
                    #         if lastdu4 is not None:
                    #             if lastdu4 <= 1.05:
                    #                 initc +=10
                    #             elif lastdu4 > 1.05 and lastdu4 <= 1.1:
                    #                 initc +=8
                    #             elif lastdu4 > 1.1 and lastdu4 <= 1.2:
                    #                 initc +=5
                    #             elif lastdu4 > 1.2 and lastdu4 <= 1.3:
                    #                 initc +=3
                    #             else:
                    #                 initc +=2
                    #         else:
                    #             initc +=1
                    #     else:
                    #         initc +=3
                    #     if close == high:
                    #         initc +=2
                    #     elif close >=high*0.99:
                    #         initc +=2

            # if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
            if (lastclose <= upper and high >= upper) | ( ((lastclose >= upper) | (lastp >= 5))):
                initc +=percent
                if high4 is not None and hmax is not None:
                    lastMax = max(high4,max5,hmax)
                    if lasthigh >= lastMax:
                        initc += 5 + abs(lastp)
                    if lastMax==hmax and high4 > max5 and high4 < hmax:
                        initc += 5

    if GlobalValues().getkey('percdf') is not None:
        # if code == '601857':
        #     import ipdb;ipdb.set_trace()
        if code in GlobalValues().getkey('percdf').index:
            lastdf = GlobalValues().getkey('percdf').loc[code]
            # if code == '920445':
            #     print(f'{code}lastdf:{lastdf.T}')
            # if isinstance(lastdf,pd.DataFrame):
            #     lastdf = lastdf.reset_index().drop_duplicates('code').set_index('code')
            #     log.error(f'code:{code} count:{lastdf.shape}')
            if percent > 2 and len(lastdf) > 0 and  isinstance(lastdf,pd.Series):
                if lastdf.lasth1d < lastdf.lasth2d < lastdf.lasth3d:
                    if close > lastdf.lasth1d:
                        initc += 30
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 30
                            
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 30
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 30
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 50
                elif lastdf.lasth2d < lastdf.lasth3d < lastdf.lasth4d:
                    if close > lastdf.lasth1d > lastdf.lasth2d:
                        initc += 25
                        if lastdf.lasth3d < lastdf.lasth4d:
                            initc += 30
                            if lastdf.lasth4d < lastdf.lasth5d:
                                initc += 30
                                if lastdf.lasth5d < lastdf.lasth6d:
                                    initc += 30
                    if low < lastdf.ma51d and high > lastdf.ma51d:
                        initc += 50
                                     
                elif lastdf.lasth1d > lastdf.lasth2d > lastdf.lasth3d and lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02 :
                    initc += 50
                    if lastdf.ma51d < lastdf.lastl1d < lastdf.ma51d*1.02:
                        initc += 30
            else:
                log.warn(f'lastdf is None :{code}')
        # else:
        #     log.info("check lowest in percdf:%s"%(code))
            # print("lowest:%s"%(code),end=' ')

    return round(initc,1)

def WriteCountFilter_cct(df, op='op', writecount=5, end=None, duration=10):
    codel = []
    # market_value = cct.GlobalValues().getkey('market_value')
    # market_key = cct.GlobalValues().getkey('market_key')
    # if market_key == '2':
    #     market_value_perd = int(market_value) * 10
    if str(writecount) != 'all' and isDigit(writecount):
        if end is None and int(writecount) > 0:
            # if int(writecount) < 101 and len(df) > 0 and 'percent' in df.columns:
            if int(writecount) < 101 and len(df) > 0:
                codel = df.index[:int(writecount)].tolist()
                # market_value = cct.GlobalValues().getkey('market_value')
                # market_key = cct.GlobalValues().getkey('market_key')
                # if market_key == '2':
                #     # market_value_perd = int(market_value) * 9.8
                #     market_value_perd = 9.8
                #     dd=df[ df['per%sd'%(market_value)] > market_value_perd ]
                #     df_list=dd.index.tolist()
                #     for co in df_list:
                #         if co not in codel:
                #             codel.append(co)
            else:
                if len(str(writecount)) >= 4:
                    codel.append(str(writecount).zfill(6))
                else:
                    print("writeCount DF is None or Wri:%s" % (writecount))
        else:
            if end is None:
                writecount = int(writecount)
                if writecount > 0:
                    writecount -= 1
                codel.append(df.index.tolist()[writecount])
            else:
                writecount, end = int(writecount), int(end)

                if writecount > end:
                    writecount, end = end, writecount
                if end < -1:
                    end += 1
                    codel = df.index.tolist()[writecount:end]
                elif end == -1:
                    codel = df.index.tolist()[writecount::]
                else:
                    if writecount > 0 and end > 0:
                        writecount -= 1
                        end -= 1
                    codel = df.index.tolist()[writecount:end]
    else:
        if df is not None and len(df) > 0:
            codel = df.index.tolist()
    return codel

Resample_top = {'d':'top_all','3d':'top_all_3d',
                      'w':'top_all_w','m':'top_all_m'}
                      
def re_find_chinese(cmd):
    re_words = re.compile(u"[\u4e00-\u9fa5]+")
    result = re.findall(re_words, cmd)
    return result

def evalcmd(dir_mo,workstatus=True,Market_Values=None,top_temp=pd.DataFrame(),block_path=None,orderby='percent',top_all=None,top_all_3d=None,top_all_w=None,top_all_m=None,resample='d',noformat=False):
    end = True
    import readline
    import rlcompleter
    # readline.set_completer(cct.MyCompleter(dir_mo).complete)
    for top_key in Resample_top.keys():
        top = eval(Resample_top[top_key])
        if top is not None and len(top) > 0 and 'lastp1d' in top.columns:
            if  top.dff[0] == 0 or top.close[0] == top.lastp1d[0]:
                top['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),top['buy'].values, top['df2'].values)))
                top['percent'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),top['buy'].values, top['lastp2d'].values)))
            if  top.volume[0] > 100 and top.volume[-1] > 100:
                if top_key == 'd':
                    ratio_t = 1 
                elif top_key == '3d':
                    ratio_t = 1.5 
                elif top_key == 'w':
                    ratio_t = 2.5 
                elif top_key == 'm':
                    ratio_t = 10
                top['volume'] = (list(map(lambda x, y: round(x / y*ratio_t, 1), top['volume'].values, top.last6vol.values)))
            if 'b1_v' not in top.columns:
                top = combine_dataFrame(top, top_temp.loc[:,['b1_v','a1_v']], col=None, compare=None, append=False)
    readline.parse_and_bind('tab:complete')
    tempdf=[]
    while end:
        # cmd = (cct.cct_raw_input(" ".join(dir_mo)+": "))
        cmd = (cct_raw_input(": ")).strip()
        if len(top_temp) == 0:
            workstatus = False
            top_temp = top_all
        code=ct.codeQuery if workstatus else ct.codeQuery_work_false
        index_status = False
        if len(cmd) == 0:
            # code='最近两周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
            # code='周线2连阳,最近三周振幅大于10,日K收盘价大于5日线,今日涨幅排序'
            # code='日K,4连阳以上,4天涨幅排序,今天阳线'
            # code={"4周新高" : "top_temp.query('close > high4 and lastp1d < hmax and low > lastl1d and lastl1d < ma51d and close >lastp2d')",\
            #       "5周新高" : "top_temp.query('close > max5 and lastp1d < hmax and low > lastl1d and lastl1d < ma51d and close >lastp2d')",\
            #       "K线2连阳"   : "top_temp.query('close > lastp1d and  lastp1d > lastp2d and close >ma51d')",\
            #       "K线连阳"    : "top_temp.query('high > lasth1d and  lasth1d > lasth2d and low >=ma51d')",\
            #       "K线反包"    : "top_temp.query('close > lastp1d and  lastp1d < lastp2d and close >ma51d')"}
            index_status = True
            for idx in range(len(code.keys())):
                id_key = list(code.keys())[idx]
                print("%s: %s %s"%(idx+1,id_key,code[id_key]))
            # for key in code.keys():
            #     print("%s: %s"%(key,code[key]))

            # list(code.keys())
            initkey= list(code.keys())[ct.initkey]
            print(f"index:{ct.initkey+1}:{initkey}: {code[initkey]}")
            # cmd=code[initkey]
            GlobalValues().setkey('tempdf',code[initkey])
            cmd=ct.codeQuery_show_cct(initkey,Market_Values,workstatus,orderby)
            # print(" ".join(list(code.keys())))
        elif len(cmd) <= 2 and cmd.isdigit() and int(cmd) < len(code.keys())+1:
            # idx = int(cmd)+1 if int(cmd) == 0 else int(cmd)
            index_status = True
            idx = int(cmd) - 1
            # print(f"idx:{idx}")
            initkey =  list(code.keys())[idx]
            print(f"\n{initkey}: {code[initkey]}")
            # cmd = code[idxkey]
            GlobalValues().setkey('tempdf',code[initkey])
            if code[initkey].find('filter') > 0:
                cmd = code[initkey]
            else:
                cmd=ct.codeQuery_show_cct(initkey,Market_Values,workstatus,orderby)
        # cmd = (cct.cct_raw_input(dir_mo.append(":")))
        # if cmd == 'e' or cmd == 'q' or len(cmd) == 0:
        if cmd == 'e' or cmd == 'q':
            break
        elif cmd.startswith('w') or cmd.startswith('a') or cmd.startswith('rw') or cmd.startswith('ra'):
            if not cmd.startswith('r') and GlobalValues().getkey('tempdf') is not None:
                tempdf = eval(GlobalValues().getkey('tempdf')).sort_values(orderby, ascending=False)
            else:
                checkcmd = 'q'
                if cmd.startswith('rw') or cmd.startswith('ra'):
                    historyLen=readline.get_current_history_length()
                    idx=1
                    while 1:
                        cmd2 = readline.get_history_item(historyLen-idx)
                        if cmd2 is None:
                            break
                        elif len(cmd2) < 20:
                            idx+=1
                            continue
                        print(f'cmd : {cmd2}',end=' ')
                        checkcmd=cct_raw_input(" is OK ? Y or N or q:")
                        if checkcmd == 'y' or checkcmd == 'q' or idx > historyLen-2:
                            break
                        else:
                            idx+=1

                    if  checkcmd == 'q':
                        print(f'checkcmd:{cmd} quit')
                        continue
                    elif  checkcmd == 'y':
                        # hdf_wri = cct_raw_input("to write Y or N:")
                        # if hdf_wri == 'y':
                        cmdlist=cmd.split()
                        if cmd.startswith('rw'):
                            cmd_ = 'w '
                        else:
                            cmd_ = 'a '

                        cmd2_list = cmd2.split()
                        if len(cmd2_list) > 1:
                            orderby_t = cmd2_list[-1]
                            # if orderby_t in list(dir(top_temp)):
                            if orderby_t in top_temp.columns:
                                orderby = orderby_t
                                # doubleCmd = True
                                cmd2 = cmd2[:cmd2.rfind(orderby_t)]
                            elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                                # doubleCmd = True
                                cmd2 = cmd2[:cmd2.rfind(orderby_t)]

                        tempdf = eval(cmd2).sort_values(orderby, ascending=False)
                        if isinstance(tempdf,pd.DataFrame):
                            GlobalValues().setkey('tempdf',cmd2)

                        if len(cmdlist) > 1:
                            # ' '.join([aa.split()[i] for i in range(1,len(aa.split()))])
                            log.debug(f'cmd:{cmd}')
                            cmd =cmd_ + ' '.join([cmd.split()[i] for i in range(1,len(cmd.split()))])
                            print(f'cmd:{cmd}')
                        else:
                            cmd = cmd_
                    else:
                        print("return shell")
                        continue
                else:
                    continue
                    
            if len(tempdf) >  0:
                args = writeArgmain_block().parse_args(cmd.split())
                codew = WriteCountFilter_cct(
                    tempdf, 'ra', writecount=args.dl)
                if args.blk is not None:
                    block_path = get_tdx_dir_blocknew() + f'{args.blk}.blk'
                if args.code == 'a':
                    write_to_blocknew(block_path, codew)
                    # sl.write_to_blocknew(all_diffpath, codew)
                else:
                    # codew = stf.WriteCountFilter(top_temp)
                    write_to_blocknew(block_path, codew, append=False,keep_last=0)
                    # sl.write_to_blocknew(all_diffpath, codew, False)
                print("wri ok:%s" % block_path)
                sleeprandom(ct.duration_sleep_time / 10)
            else:
                print(f'tempdf is None cmd:{cmd}')
            
        elif len(cmd) == 0:
            continue
        else:
            try:
                if cmd.startswith('tempdf'):
                    if GlobalValues().getkey('tempdf') is not None:
                        tempdf = eval(GlobalValues().getkey('tempdf')).sort_values(orderby, ascending=False)
                        # print((eval(cmd)))

                if not cmd.find(' =') < 0:
                    # cmd = ct.codeQuery_show_single(cmd,Market_Values,orderby='percent')
                    # import ipdb;ipdb.set_trace()
                    # print(cmd)
                    # exec(cmd)
                    exec(cmd)
                elif  cmd.find('filter') > 0:
                    print((eval(cmd))) 
                else:
                    
                    doubleCmd=False
                    log.debug(f'cmd.split():{cmd}')
                    cmd_list = cmd.split()
                    # if len(cmd_list) > 1:
                    #     orderby_t = cmd_list[-1]
                    #     # if orderby_t in list(dir(top_temp)):
                    #     if orderby_t in top_temp.columns:
                    #         orderby = orderby_t
                    #         # doubleCmd = True
                    #         cmd = cmd[:cmd.rfind(orderby_t)]
                    #     elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                    #         # doubleCmd = True
                    #         cmd = cmd[:cmd.rfind(orderby_t)]
                    re_words = re.compile(u"[\u4e00-\u9fa5]+")
                    if len(cmd_list) == 1 and len(re.findall(re_words, cmd)) > 0:
                        cmd = f'top_all {cmd}'
                        cmd_list = cmd.split()
                    category_search = False

                    if len(cmd_list) > 1 and cmd.find('category') < 0:
                        orderby_t = cmd_list[-1]
                        if len(re.findall(re_words, orderby_t)) > 0:
                            category_search = True
                            search_key = f'category.str.contains("{cmd_list[-1]}")'
                            if cmd.find('query') < 0:
                                cmd = f"{cmd_list[0]}.query('close > 0') {orderby_t}"
                            cmd = cmd[:cmd.rfind(orderby_t)].replace("')",f" and {search_key}')")
                            print(f'cmd: {cmd}')
                        else: 
                            if orderby_t in top_temp.columns:
                                orderby = orderby_t
                                # doubleCmd = True
                                cmd = cmd[:cmd.rfind(orderby_t)]
                            elif re.findall(r'^[a-z\d]*', orderby_t)[0] == orderby_t:
                                # doubleCmd = True
                                cmd = cmd[:cmd.rfind(orderby_t)]

                    if category_search:
                        check_all = cmd.split('.')[-3]
                        check_s = re.findall(r'^[a-zA-Z\d]*', check_all)[0]
                    else:
                        check_all = cmd.split('.')[-1]
                        check_s = re.findall(r'^[a-zA-Z\d]*', check_all)[0]

                    # if (cmd.startswith('tempdf') or cmd.startswith('top_temp')) and  cmd.find('sort') < 0:
                    

                    if (cmd.find('.loc') > 0 and cmd.find(':') > 0) or (cmd.find('.loc') < 0 and (cmd.startswith('tempdf') or cmd.startswith('top_temp') or cmd.startswith('top_all'))) and  check_s not in top_temp.columns:
                        if orderby not in ['topR','percent']and orderby in top_temp.columns:
                            top_temp[orderby] = top_temp[orderby].astype(int)
                            top_all[orderby] = top_all[orderby].astype(int)
                            
                        if (cmd.startswith('tempdf') or cmd.startswith('top_temp') or cmd.startswith('top_all')) and  check_s not in top_temp.columns:
                            # if cmd.split('.')[-1] not in list(dir(top_temp)) and cmd.find('format_for_print_show') < 0:
                            if (check_s == 'query' or  check_s not in list(dir(top_temp))) and cmd.find('format_for_print_show') < 0:
                            
                                tempdf = eval(cmd)
                                if isinstance(tempdf,pd.DataFrame):
                                    GlobalValues().setkey('tempdf',cmd)
                                if cmd.find('query') > 0:
                                    if doubleCmd:
                                        write_evalcmd2file(evalcmdfpath,cmd+orderby_t)
                                    else:
                                        write_evalcmd2file(evalcmdfpath,cmd)
                                try:
                                    cmd = ct.codeQuery_show_single(cmd,Market_Values,orderby=orderby,noformat=noformat)
                                except Exception as e:
                                    print("Exception:", e)
                                    traceback.print_exc()
                                    # raise e
                        elif  check_s  != orderby and cmd.find('sort_values') < 0 and (check_s  in list(dir(top_temp)) or check_s in top_temp.columns) :
                            cut_tail = cmd.split('.')[-1]
                            # cmd_head = cmd.replace(cut_tail,'')
                            cmd_head = cmd[:cmd.rfind(cut_tail)]
                            cmd = f"{cmd_head}sort_values('{orderby}', ascending=False).{cut_tail}"  

                    print((eval(cmd))) 
                if index_status:
                    idx = 0
                    cut_d = 7
                    for idx_k in range(len(code.keys())):
                        id_key = list(code.keys())[idx_k]
                        idx+=1
                        if idx >cut_d and idx%cut_d == 1:
                            # print("\t\t",end='')
                            print("%s:%s "%(idx_k+1,id_key))
                        else:
                            print("%s:%s "%(idx_k+1,id_key),end="")
                        # if idx%4 == 0:
                        #     print(f'\\')
                    print(f"\n{initkey}: {code[initkey]}")

                print('')
            except Exception as e:
                print(e)
                # evalcmd(dir_mo)
                # break


def func_compute_percd2021_2022mod( open, close,high, low,lastopen, lastclose,lasthigh, lastlow, ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']

    initc = 0
    if  0 < lastclose < 1000 and lasthigh != 1.0 and lastlow != 1.0 and lasthigh != 0 and lastlow != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastclose)/lastclose*100,1)
        # now_du = round((high - low)/low*100,1)
        close_du = round((high - low)/low*100,1)
        # last_du = round((lasthigh - lastlow)/lastlow*100,1)
        # volratio = round((nowvol / lastvol),1)
        vol_du = round((nowvol)/lastvol,1)

        if percent > 1:
            initc +=1
            if  close_du > 5:
                initc +=0.1
        elif percent < -1:
            initc -=1
            if  close_du > 5:
                initc -=0.1
                
        # if percent >0 and open >= lastclose and close == high and close > ma5:
        #     initc +=1
        #     if close > ma5:
        #         if close < ma5*1.1:
        #             initc +=3*vol_du
        #         elif close < ma5*1.2:
        #             initc +=2*vol_du
        #         else:
        #             initc+=2

        # elif percent > 3 and low >= lastlow and high > lasthigh:
        #     initc +=2

        # elif percent > 3 and close_du > 9 and vol_du > 2:
        #     initc += 1*vol_du
        # elif percent > 2 :
        #     initc +=1
        # elif percent > 0  and open > ma5 and open > ma10 :
        #     initc +=1
        #     if  vol_du < 0.6:
        #         initc +=0.1
        # elif low < lastlow and high < lasthigh:
        #     initc -=1
        # elif percent < -5 and low < lastlow:
        #     initc -=2
        # elif percent < 0 and close < ma5 and close < ma10:
        #     initc -=0.51
        # else:
            # initc -=1
    elif  np.isnan(lastclose) :
        if close > open:
            initc +=1

    # open, close,high, low,lastopen, lastclose,lasthigh, lastlow, 
    # ma5,ma10,nowvol=None,lastvol=None,upper=None,idate=None
    if close > ma5:
        initc +=0.1
        if  ma5 > ma10:
            initc +=0.1
        else:
            initc -=0.11
    else:
        initc -=0.1

    return initc

# import numba as nb
# @numba.jit(nopython=True)
# @nb.autojit
def func_compute_percd2(close, lastp, op, lastopen,lasth, lastl, nowh, nowl,nowvol=None,lastvol=None,upper=None,hmax=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    # df['vol'],df['vol'].shift(1),df['upper']
    initc = 0
    if 0 < lastp < 1000 and lasth != 1.0 and lastl != 1.0 and lasth != 0 and lastl != 0:
#        close = round(close, 1)
#        lastp = round(lastp, 1)
#        op = round(op, 1)
#        lastopen = round(lastopen, 1)
#        lasth = round(lasth, 1)
#        lastl = round(lastl, 1)
        percent = round((close - lastp)/lastp*100,1)
        now_du = round((nowh - nowl)/nowl*100,1)
        last_du = round((lasth - lastl)/lastl*100,1)
        volratio = round((nowvol / lastvol),1)
        if volratio > 1.1:
            initc +=1
            if last_du > 2 or now_du >3:
                if percent > 0.8:
                    initc +=1
                # if percent > 5 or (nowvol / lastvol) > 1.5:
                #     initc +=1
                # if percent > 8 and (nowvol / lastvol) > 1.2:
                #     initc +=1
                if percent < -2 and volratio > 1.2:
                    initc -=1
                if nowh >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            if volratio >1.5:
                initc +=1
#            else:
#                if lastp > lastopen and close > op:
#                    initc +=1

        else:
            if last_du > 2 or now_du > 3:
                if percent > 2:
                    initc +=1
#                elif -2 < percent < 1:
#                    initc -=1
#                elif percent < -2:
#                    initc -=1
                if close >= lasth or nowh >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if nowl >= op and close > op:
                    initc +=2
                else:
                    initc +=1



        if nowl == op or (op > lastp and nowl > lastp):
            initc +=1
            if lastopen >= lastl:
                initc +=1
            if  nowh > lasth:
                initc +=1
                # if nowh == close:
                #     initc +=1

        if  op > lastp or nowl > lastp:
                initc +=1

        if ((close - lastp)/lastp*100 >= 0):
            if op > lastp:
                initc +=1
                # if nowh == nowl:
                #     initc +=1
                if nowl > lastp:
                    initc +=1
                    if nowl > lasth:
                        initc +=1

                if close > nowh * ct.changeRatio:
                    initc +=1
                    # if lastp == lasth:
                    #     initc +=1

                if (close >= op):
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if (nowl >= lastl):
                            initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                initc +=1
                if op >= nowl*0.995:
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if close > nowh * ct.changeRatio:
                            initc +=1
                            if (nowl >= lastl):
                                initc +=1

        else:
            if op < lastp:
                if (close >= op):
                    if  nowl > lastl:
                        initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                if (close < op):
                    if (nowh < lasth):
                        initc -=1
                    if  nowl < lastl:
                        initc -=1
                else:
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            if nowh < lastp:
                initc -=1
                if nowh < lastl:
                    initc -=1

        if hmax is not None:
            if cumin is not None:
                if volratio > 4:
                    if cumin < 2:
                        initc += 8
                    elif cumin > 5:
                        initc -= 2
                elif lastopen >= lastl:
                    # initc +=1
                    # if op >= nowl:
                    #     initc +=1
                    if nowh >= hmax:
                        initc +=2
            # if lastopen >= lastl:
            #     initc +=1
            #     if op >= nowl:
            #         initc +=1
            # if nowh >= hmax:
            #     initc +=1

    return initc

def func_compute_percdS(close, lastp, op, lastopen,lasth, lastl, nowh, nowl,nowvol=None,lastvol=1,hmax=None,cumin=None):
    # down_zero, down_dn, percent_l = 0, 0, 2
     # (1 if ( ((c >= op) and ((c - lc)/lc*100 >= 0)) or (c >= op and c >=m5a) ) else down_dn)
    initc = 0
    if lasth != 1.0 and lastl != 1.0 and lasth != 0 and lastl != 0:
        close = round(close, 1)
        lastp = round(lastp, 1)
        op = round(op, 1)
        lastopen = round(lastopen, 1)
        lasth = round(lasth, 1)
        lastl = round(lastl, 1)
        percent = round((close - lastp)/lastp*100,1)
        now_du = round((nowh - nowl)/nowl*100,1)
        last_du = round((lasth - lastl)/lastl*100,1)
        volratio = round((nowvol / lastvol),1)
        if volratio > 1.1:
            if last_du > 3 or now_du >3:
                if percent > 2:
                    initc +=1
                # if percent > 5 or (nowvol / lastvol) > 1.5:
                #     initc +=1
                # if percent > 8 and (nowvol / lastvol) > 1.2:
                #     initc +=1
                if percent < -2 and volratio > 1.2:
                    initc -=1
                if close >= lasth*0.98:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if lastp > lastopen and close > op:
                    initc +=1

        else:
            if last_du > 3 or now_du > 3:
                if percent > 2:
                    initc +=1
                elif -2 < percent < 1:
                    initc -=1
                elif percent < -2:
                    initc -=2
                if close >= lasth:
                    initc +=1
                    if close >= nowh*0.98:
                        initc +=1
            else:
                if lastp > lastopen and close > op:
                    initc +=1



        if nowl == op or (op > lastp and nowl > lastp):
            initc +=1
            if lastopen >= lastl:
                initc +=1
            if  nowh > lasth:
                initc +=1
                # if nowh == close:
                #     initc +=1

        if  op > lastp or nowl > lastp:
                initc +=1

        if ((close - lastp)/lastp*100 >= 0):
            if op > lastp:
                initc +=1
                # if nowh == nowl:
                #     initc +=1
                if nowl > lastp:
                    initc +=1
                    if nowl > lasth:
                        initc +=1

                if close > nowh * ct.changeRatio:
                    initc +=1
                    # if lastp == lasth:
                    #     initc +=1

                if (close >= op):
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if (nowl >= lastl):
                            initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                initc +=1
                if op >= nowl*0.995:
                    initc +=1
                    if (nowh > lasth):
                        initc +=1
                        if close > nowh * ct.changeRatio:
                            initc +=1
                            if (nowl >= lastl):
                                initc +=1

        else:
            if op < lastp:
                if (close >= op):
                    if  nowl > lastl:
                        initc +=1
                else:
                    initc -=1
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            else:
                if (close < op):
                    if (nowh < lasth):
                        initc -=1
                    if  nowl < lastl:
                        initc -=1
                else:
                    if (nowh < lasth):
                        initc -=1
                        if  nowl < lastl:
                            initc -=1
            if nowh < lastp:
                initc -=1
                if nowh < lastl:
                    initc -=1

        if hmax is not None:
            if cumin is not None:
                if volratio > 4:
                    if cumin < 2:
                        initc += 8
                    elif cumin > 5:
                        initc -= 2
                elif lastopen >= lastl:
                    # initc +=1
                    # if op >= nowl:
                    #     initc +=1
                    if nowh >= hmax:
                        initc +=11
            # if lastopen >= lastl:
            #     initc +=1
            #     if op >= nowl:
            #         initc +=1
            # if nowh >= hmax:
            #     initc +=1

    return initc


def select_dataFrame_isNull(df):
    is_null = df.isnull().stack()[lambda x: x].index.tolist() 
    return(is_null)

# @timed_block("combine_dataFrame", warn_ms=1000)
def combine_dataFrame(maindf: Union[pd.DataFrame, pd.Series], subdf: Union[pd.DataFrame, pd.Series], col: Optional[str] = None, compare: Optional[str] = None, append: bool = False, clean: bool = True) -> pd.DataFrame:
    '''

    Function: combine_dataFrame

    Summary: 合并DF,Clean:True Clean Maindf else Clean Subdf

    Examples: @
    Attributes: 

        @param (maindf):maindf

        @param (subdf):subdf

        @param (col) default=None: InsertHere

        @param (compare) default=None: InsertHere

        @param (append) default=False: InsertHere

        @param (clean) default=True: InsertHere

    Returns: Maindf

    '''
    times = time.time()
    if maindf is None or len(maindf) < 1:
        log.error(f'maindf is None:{maindf}')
        return maindf
    if subdf is  None or len(subdf) == 0:
        return maindf

    if (isinstance(maindf,pd.Series)):
        maindf = maindf.to_frame()
    if (isinstance(subdf,pd.Series)):
        subdf = subdf.to_frame()
    maindf_co = maindf.columns
    subdf_co = subdf.columns
    maindf = maindf.fillna(0)
    subdf = subdf.fillna(0)
    if not append:

        if 'code' in maindf.columns:
            maindf = maindf.set_index('code')
        if 'code' in subdf.columns:
            subdf = subdf.set_index('code')

        no_index = maindf.drop([inx for inx in maindf.index if inx not in subdf.index], axis=0)
        drop_sub_col = [col for col in no_index.columns if col in subdf.columns]
        #比较主从的col,两边都有的需要清理一个
        if clean:
            #Clean True时清理maindf的旧数据
            no_index = no_index.drop(drop_sub_col, axis=1)
        else:
            #Clean False时清理subdf columns的数据
            subdf = subdf.drop(drop_sub_col, axis=1)
        if len(subdf.columns) > 0:
            no_index = no_index.merge(subdf, left_index=True, right_index=True, how='left')
            maindf = maindf.drop([inx for inx in maindf.index if inx in subdf.index], axis=0)
            maindf = pd.concat([maindf, no_index], axis=0)
    else:
        maindf = maindf.drop([col for col in maindf.index if col in subdf.index], axis=0)
        co_mod = maindf.dtypes[(maindf.dtypes == int) & (list(maindf.dtypes.keys()) != 'ldate') & (list(maindf.dtypes.keys()) != 'kind')]

        for co_t in list(co_mod.keys()):
            if co_t in subdf.columns:
                if maindf.dtypes[co_t] != subdf.dtypes[co_t]:
                    subdf[co_t] = subdf[co_t].astype(maindf.dtypes[co_t])
            else:
                if append:
                    subdf[co_t] = 0
                    subdf[co_t] = subdf[co_t].astype(maindf.dtypes[co_t])
                    
        maindf = pd.concat([maindf, subdf], axis=0)
        maindf = maindf.fillna(-2)
        if not 'code' in maindf.columns:
            if not maindf.index.name == 'code':
                maindf.index.name = 'code'
        maindf.reset_index(inplace=True)
        maindf.drop_duplicates('code', inplace=True)
        maindf.set_index('code', inplace=True)
    log.info("combine df :%0.2f" % (time.time() - times))
    if append:
        dif_co = list(set(maindf_co) - set(subdf_co))
    return maindf

get_config_value_ramfile(fname='is_trade_date',update=True,currvalue=get_day_istrade_date(),xtype='trade_date')

if __name__ == '__main__':

    '''
    def readHdf5(fpath, root=None):
        store = pd.HDFStore(fpath, "r")
        print(store.keys())
        if root is None:
            root = store.keys()[0].replace("/", "")
        df = store[root]
        df = apply_col_toint(df)
        store.close()
        return df
    def apply_col_toint(df, col=None):
        if col is None:
            co2int = ['boll', 'op', 'ratio', 'fib', 'fibl', 'df2']
        # co2int.extend([co for co in df.columns.tolist()
        #                if co.startswith('perc') and co.endswith('d')])
            co2int.extend(['top10', 'topR'])
        else:
            co2int = col
        co2int = [inx for inx in co2int if inx in df.columns]

        for co in co2int:
            df[co] = df[co].astype(int)

        return df

    sina_MultiD_path = "G:\\sina_MultiIndex_data.h5"
    h5 = readHdf5(sina_MultiD_path)
    print(sina_MultiD_path)
    h5.shape
    # h5[:1]
    code_muti = '600519'
    # h5.loc[code_muti][:2]

    freq = 'D'
    startime = '09:25:00'
    endtime = '15:01:00'

    time_ratio = get_work_time_ratio()
    time_ratio
    run_col = ['close', 'volume']
    mdf = get_limit_multiIndex_freq(
        h5, freq=freq.upper(),
    col=run_col, start=startime, end=endtime, code=None)
    mdf.shape
    '''
    # rzrq['all']='nan'
    # print(get_last_trade_date('2025-06-01'))
    print(f'get_work_time() : {get_work_time()}')
    st_key_sort='3 0 f'
    print(ct.get_market_sort_value_key(st_key_sort))
    print(get_run_path_tdx('all_300'))
    import ipdb;ipdb.set_trace()
    query_rule = read_ini(inifile='filter.ini',category='sina_Monitor')
    print(get_today(''))
    get_lastdays_trade_date(1)
    print(f'get_work_day_idx:{get_work_day_idx()}')
    print(get_tdx_dir_blocknew_dxzq(r'D:\MacTools\WinTools\new_tdx2\T0002\blocknew\090.blk'))
    print(f'is_trade_date():{is_trade_date()}')
    print(f'is_trade_date:{is_trade_date_today}')
    print(isDigit('nan None'))
    print("指数的贡献度:",isDigit('指数的贡献度'))

    GlobalValues()
    GlobalValues().setkey('key', 'GlobalValuesvalue')
    print(GlobalValues().getlist())
    
    # print(read_to_indb())
    print(f'get_trade_date_status : {get_trade_date_status()}')
    print(f'get_day_istrade_date : {get_day_istrade_date()}')
    print(f"get_config_value_ramfile : {get_config_value_ramfile(fname='is_trade_date',update=True,currvalue=get_day_istrade_date(),xtype='trade_date')}")
    import ipdb;ipdb.set_trace()

    print(code_to_symbol_ths('000002'))
    print(get_index_fibl())
    GlobalValues()
    GlobalValues().setkey('key', 'GlobalValuesvalue')
    print(get_work_time())
    print(get_now_time_int())
    print(get_work_duration())
    print((random.randint(0, 30)))
    print(GlobalValues().getkey('key', defValue=None))
    print(get_run_path_tdx('aa'))
    print(get_ramdisk_path(tdx_hd5_name))
    print(get_today(sep='-'))
    from docopt import docopt
    log = LoggerFactory.log
    args = docopt(sina_doc, version='sina_cxdn')
    # print args,args['-d']
    if args['-d'] == 'debug':
        log_level = LoggerFactory.DEBUG
    elif args['-d'] == 'info':
        log_level = LoggerFactory.INFO
    else:
        log_level = LoggerFactory.ERROR
    # log_level = LoggerFactory.DEBUG if args['-d']  else LoggerFactory.ERROR

    # log_level = LoggerFactory.DEBUG
    # log.setLevel(log_level)
    # print tdxblk_to_code('1399001')
    print(tdxblk_to_code('0399001'))
    print(read_to_blocknew('066'))
    # get_terminal_Position(cmd=scriptquit, position=None, close=False)
    # get_terminal_Position('Johnson —', close=True)
    get_terminal_Position(clean_terminal[2], close=True)
    get_terminal_Position(clean_terminal[1], close=True)
    log.info("close Python Launcher")
    s_time = time.time()
    print("last:", last_tddate(2))
    print(get_work_day_status())
    print(get_terminal_Position(cmd='DurationDN.py', position=None, close=False))
    print(get_terminal_Position(cmd='Johnson@', position=None, close=False))
    print(get_terminal_Position(cmd=clean_terminal[1], position=None, close=False))
    print("t:%0.2f" % (time.time() - s_time))
    print(get_ramdisk_path('a', lock=False))
    # print get_work_time_ratio()
    # print typeday8_to_day10(None)
    # write_to_blocknew('abc', ['300380','601998'], append=True)
    print(get_now_time_int())
    print(get_work_duration())
    print(get_today_duration('2017-01-01', '20170504'))
    # print get_tushare_market(market='captops', renew=True,days=10).shape
    # print get_rzrq_code()[:3]
    # times =1483686638.0
    # print get_time_to_date(times, format='%Y-%m-%d')

    # for x in range(1,120,5):
    #     times=time.time()
    #     print sleep(x)
    #     print time.time()-times
    print(get_work_time_ratio())
    print(getCoding('啊中国'.encode("utf16")))
    print(get_today_duration('2017-01-06'))
    print(get_work_day_status())
    import sys
    sys.exit(0)
    print(get_rzrq_code('cxgzx')[:3])
    print(get_rzrq_code('cx')[:3])
    print(get_now_time())
    print(get_work_time_ratio())
    print(get_work_day_status())
    print(last_tddate(days=3))
    for x in range(0, 4, 1):
        print(x)
        print(last_tddate(x))
        # print last_tddate(2)
    print(get_os_system())
    set_console()
    set_console(title=['G', 'dT'])
    input("a")
    # print System.IO.Path
    # print workdays('2010-01-01','2010-05-01')

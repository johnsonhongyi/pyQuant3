import os
import sys
import requests
import pandas as pd
from pandas import HDFStore
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
import json
from datetime import datetime, timedelta
from ctypes import wintypes
import ctypes
import shutil
import configparser
from pathlib import Path
from tkcalendar import DateEntry
import psutil
import re
import win32gui
import win32process
import win32api
import win32con
import threading
import concurrent.futures
import pyperclip
import random
import queue
import importlib.util
import win32pipe, win32file
import a_trade_calendar
from filelock import FileLock, Timeout
# 全局变量
monitor_windows = {}  # 存储监控窗口实例

WINDOW_GEOMETRIES = {}
WINDOWS_BY_ID = {}
save_timer = None


alerts_rules = {}       # {code: [ {field, op, value}, ... ]}
alerts_enabled = {}   # 每个股票的报警开关状态
alerts_buffer = []      # 临时报警缓存
alerts_history = []
alert_window = None
alert_tree = None
alert_moniter_bring_front = False
# 报警中心排序记录
alert_sort_column = None
alert_sort_reverse = False

root = None
stock_tree = None
context_menu = None
code_entry = None  # 添加全局 Entry 变量

realdatadf = pd.DataFrame()  # 存储股票异动数据的DataFrame
last_updated_time = None # 记录上次更新时间
realdatadf_lock = threading.Lock() # 为 loaddf 创建一个全局锁
update_interval_minutes = 10
start_init = 0
scheduled_task = None
viewdf = pd.DataFrame()
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
result_queue = queue.Queue()
today_tdx_df = pd.DataFrame()

# 停止信号
stop_event = threading.Event()
worker_thread = None   # 保存后台线程
after_tasks = {}
screen_width = 0
screen_height = 0

ALERT_COOLDOWN = 5 * 60  # 冷却时间，单位秒
last_alert_times = {}  # 记录每个股票每条规则上次报警时间
sina_data_last_updated_time = None
sina_data_df = None
pytables_status = None
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
date_entry = None
codelist = []
ths_code=[]
send_stock_code = None
PIPE_NAME = r"\\.\pipe\my_named_pipe"

# 保存每个 stock_code/item_id 的刷新状态
refresh_registry = {}  # {(tree, window_info, item_id): {"after_id": None}}
# 控制更新节流
UPDATE_INTERVAL = 30  # 秒，更新UI最小间隔
last_update_time = 0
message_cache = []  # 缓存队列

import argparse
import logging
from logging.handlers import RotatingFileHandler
class LoggerWriter:
    """将 print 输出重定向到 logger"""
    def __init__(self, level_func):
        self.level_func = level_func
        self._is_logging = False  # 防止递归

    def write(self, message):
        if not message.strip():
            return
        if self._is_logging:
            return
        try:
            self._is_logging = True
            for line in message.rstrip().splitlines():
                self.level_func(line)
        finally:
            self._is_logging = False

    def flush(self):
        pass

def init_logging(log_file="appTk.log", level=logging.INFO, redirect_print=True,show_detail=True):
    """初始化全局日志"""
    # logger\.info\((?!f)  查找没有f  loggger.info(
    # logger\.info\((?!f)[^,)]*,\s*\w+    查找没有f 加,
    #   ^(?!\s*#).*?logger\.info\((?!f)[^,)]*,\s*\w+   查找没有f 加, 排除#
    logger = logging.getLogger("MonitorDFCF")
    logger.setLevel(level)

    if not logger.handlers:
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
        if show_detail:
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s")
            ch_formatter = logging.Formatter("[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s");
        else:
            formatter = logging.Formatter("(%(funcName)s:%(lineno)s): %(message)s")
            ch_formatter = logging.Formatter("(%(funcName)s:%(lineno)s): %(message)s");
        
        # handler.setFormatter(handler_logformat)
        # ch.setFormatter(ch_formatter)
        # logger.addHandler(ch)
        # logger.addHandler(handler)

        # fh = logging.FileHandler(log_file, encoding="utf-8")
        # ✅ 使用 RotatingFileHandler：超过 1MB 自动轮转
        fh = RotatingFileHandler(
            log_file, 
            maxBytes= 5 * 1024 * 1024,  # 1MB
            backupCount=3,         # 最多保留3个历史日志
            encoding="utf-8"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

    logger.propagate = False

    # ⚠️ 调试时禁用 print 重定向
    if redirect_print:
        sys.stdout = LoggerWriter(logger.info)
        sys.stderr = LoggerWriter(logger.error)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("未捕获异常:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logger.info("日志初始化完成")
    return logger

logger = init_logging(log_file='monitor_dfcf.log',redirect_print=False)

def pipe_server(update_callback):
    """
    命名管道服务器线程
    """
    pipe = win32pipe.CreateNamedPipe(
        PIPE_NAME,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        win32pipe.PIPE_UNLIMITED_INSTANCES,
        65536, 65536, 0, None
    )
    logger.info("管道服务器启动，等待连接...")

    while True:
        win32pipe.ConnectNamedPipe(pipe, None)
        try:
            while True:
                err, data = win32file.ReadFile(pipe, 65536)
                # logger.info(f'err : {err} data :{data}')
                # if err == 0 and data:
                #     code = data.decode("utf-8")
                #     update_callback(code)
                # else:
                #     # logger.info(f'err : {err} data :{data}')
                #     break
                # 1. 解码字符串
                # 1. bytes -> str
                text = data.decode("utf-8")  # 注意这里 decode
                # 2. str -> dict
                try:
                    stock_info = json.loads(text)
                except json.JSONDecodeError:
                    stock_info = text  # 如果不是 JSON 就原样使用
                # 3. 调用回调（异动联动 search）
                update_callback(stock_info)
        except Exception as e:
            # logger.info("读取数据异常:", e)
            pass
        finally:
            # logger.info("DisconnectNamedPipe:")
            win32pipe.DisconnectNamedPipe(pipe)

# def get_base_path():
#     """
#     获取程序基准路径：
#     - PyInstaller 单文件/多文件 exe
#     - Nuitka 单文件/多文件 exe
#     - 普通 Python 脚本
#     """
#     # 1️⃣ PyInstaller 单文件 exe（存在 _MEIPASS）
#     if hasattr(sys, "_MEIPASS"):
#         # 返回 exe 解压目录（单文件模式），配置文件在 exe 同目录可能需要相对路径调整
#         logger.info(f'_MEIPASS  os.path.dirname(os.path.abspath(sys.executable): {os.path.dirname(os.path.abspath(sys.executable))}')
#         return os.path.dirname(os.path.abspath(sys.executable))

#     # 2️⃣ Nuitka 打包 exe（单文件或多文件）
#     elif getattr(sys, "frozen", False):
#         # sys.argv[0] 指向运行时 exe
#         exe_path = os.path.abspath(sys.argv[0])

#         # 单文件模式解压在临时目录，需要返回原始 exe 所在目录
#         # 可通过环境变量 TEMP 或者 exe 旁边的文件夹判断
#         temp_dir = os.environ.get("TEMP", "")
#         logger.info(f'temp_dir : {temp_dir}')
#         logger.info(f'os.path.commonpath([exe_path, temp_dir]) : {os.path.commonpath([exe_path, temp_dir])}')
#         logger.info(f'frozen os.path.dirname(os.path.realpath(sys.executable)): {os.path.dirname(os.path.realpath(sys.executable))}')
#         logger.info(f'frozen os.path.dirname(exe_path) : {os.path.dirname(exe_path)}')
#         if temp_dir and os.path.commonpath([exe_path, temp_dir]) == temp_dir:
#             # 单文件 exe，返回当前脚本所在目录（用户原始目录）
#             logger.info(f'frozen os.path.dirname(os.path.realpath(sys.executable)): {os.path.dirname(os.path.realpath(sys.executable))}')
#             return os.path.dirname(os.path.realpath(sys.executable))
#         else:
#             # 多文件 exe，直接返回 exe 所在目录
#             logger.info(f' os.path.dirname(exe_path) : { os.path.dirname(exe_path)}')
#             return os.path.dirname(exe_path)

#     # 3️⃣ 普通 Python 脚本
#     else:
#         logger.info(f'else os.path.dirname(os.path.abspath(__file__)) : {os.path.dirname(os.path.abspath(__file__))}')
#         return os.path.dirname(os.path.abspath(__file__))


# --- Win32 API 用于获取 EXE 原始路径 (仅限 Windows) ---
def _get_win32_exe_path():
    """
    使用 Win32 API 获取当前进程的主模块路径。
    这在 Nuitka/PyInstaller 的 Onefile 模式下能可靠地返回原始 EXE 路径。
    """
    # 假设是 32767 字符的路径长度是足够的
    MAX_PATH_LENGTH = 32767 
    buffer = ctypes.create_unicode_buffer(MAX_PATH_LENGTH)
    
    # 调用 GetModuleFileNameW(HMODULE hModule, LPWSTR lpFilename, DWORD nSize)
    # 传递 NULL 作为 hModule 获取当前进程的可执行文件路径
    ctypes.windll.kernel32.GetModuleFileNameW(
        None, buffer, MAX_PATH_LENGTH
    )
    return os.path.dirname(os.path.abspath(buffer.value))

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
            real_path = _get_win32_exe_path()
            
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

# logger.info(f'_get_win32_exe_path() : {_get_win32_exe_path()}')

# --- 使用示例 ---
# base_dir = get_base_path()
# config_path = os.path.join(base_dir, "conf.ini") 
# # 确保 conf.ini 放在你的原始 .py 脚本所在的目录

# def get_base_path():
#     """
#     プログラム実行時のベースパスを取得する。
#     PyInstallerでexe化された場合でも、実行ファイルのディレクトリを返す。
#     """
#     if getattr(sys, 'frozen', False):
#         # PyInstallerでexe化された場合
#         return os.path.dirname(os.path.abspath(sys.executable))
#     else:
#         # 通常の.pyファイルとして実行された場合
#         return os.path.dirname(os.path.abspath(__file__))


class SafeHDFStore(HDFStore):
    """
    精简只读版本的 SafeHDFStore：
    - 自动等待锁文件释放，避免读取冲突
    - 不做写入和压缩操作
    """
    def __init__(self, fname, mode='r', **kwargs):
        self.fname = fname
        self.mode = mode
        self._lock = self.fname + ".lock"
        logger.info(f'self._lock : {self._lock}')
        self._flock = None
        self.countlock = 0

        # 如果文件不存在，直接报错
        if not os.path.exists(self.fname):
            raise FileNotFoundError(f"HDF5 file not found: {self.fname}")

        # 等待锁释放
        if mode == 'r':
            self._wait_for_lock()

        # 调用父类初始化
        super().__init__(self.fname, mode='r', **kwargs)

    # ===== 锁等待 =====
    def _wait_for_lock(self):
        wait_count = 0
        while os.path.exists(self._lock):
            wait_count += 1
            logger.info(f"锁文件存在，读操作等待中... 已等待 {wait_count} 秒")
            time.sleep(1)
        logger.info("锁已释放，读操作继续。")

    # ===== 上下文管理 =====
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)



BASE_DIR = get_base_path()
code_file_name= os.path.join(BASE_DIR, "code_ths_other.json")
MONITOR_LIST_FILE =  os.path.join(BASE_DIR, "monitor_list.json")
CONFIG_FILE =  os.path.join(BASE_DIR, "window_config.json")
ALERTS_FILE =  os.path.join(BASE_DIR, "alerts.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)
def check_hdf5():
    # 检查 tables 是否可用
    global pytables_status
    # 检查 PyTables
    tables_available = importlib.util.find_spec("tables") is not None
    if not tables_available:
        logger.info("缺少 PyTables，HDFStore 功能将被禁用。")

    # 检查 MKL
    mkl_available = False
    pytables_status = True

    def detect_blas_backend():
        import numpy.__config__ as np_config
        config = {}
        for name in dir(np_config):
            if name.endswith("_info"):
                try:
                    value = getattr(np_config, name)
                    if value and "NOT AVAILABLE" not in str(value):
                        config[name] = value
                except Exception:
                    pass
        
        if any("mkl" in k.lower() for k in config.keys()):
            return "MKL"
        elif any("openblas" in k.lower() for k in config.keys()):
            return "OpenBLAS"
        elif any("blis" in k.lower() for k in config.keys()):
            return "BLIS"
        else:
            return "Unknown"

    # def list_blas_libraries():
    #     import numpy as np
    #     blas_libraries = []
    #     # 遍历 numpy.__config__ 的所有属性
    #     for attr in dir(np.__config__):
    #         if attr.endswith("_info"):
    #             try:
    #                 info = getattr(np.__config__, attr)
    #                 if isinstance(info, dict) and "libraries" in info:
    #                     blas_libraries.extend(info["libraries"])
    #             except Exception:
    #                 pass
    #     return blas_libraries

    # logger.info("BLAS/LAPACK libraries:", list_blas_libraries())
    # def check_blas():
    #     import numpy as np
    #     import ctypes.util 
    #     # for name in list(np.__config__.blas_opt_info.get("libraries", [])):
    #     #     logger.info("BLAS library:", name)

    #     # 进一步检查动态库
    #     for dll in ctypes.util.find_library("mkl_rt"), ctypes.util.find_library("openblas"):
    #         logger.info("Found DLL:", dll)
    # check_blas()


    if detect_blas_backend() == 'Unknown':
        logger.info("MKL 不可用，NumPy 可能会慢一些，但程序仍可运行。")
        # pytables_status = False
    # 使用条件判断执行后续代码
    if tables_available and mkl_available:
        pytables_status = True
    else:
        logger.info("跳过 HDFStore 操作")
    logger.info(f"BLAS backend:{detect_blas_backend()} pytables_status:{pytables_status}")


def get_ths_code():
    global ths_code,code_file_name
    if os.path.exists(code_file_name):
        logger.info(f"{code_file_name} exists, loading...")
        with open(code_file_name, "r", encoding="utf-8") as f:
            codelist = json.load(f)['stock']
            # ths_code = [co for co in codelist if co.startswith('60')]
            ths_code = [co for co in codelist]
        logger.info(f"Loaded:{len(ths_code)}")
    else:
        logger.info(f"{code_file_name} not found, creating...")
        data = {"stock": ths_code}
        with open(code_file_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

def load_code_file(filename):
    """读取 JSON 文件，没有则返回默认结构"""
    if not os.path.exists(filename):
        return {"stock": []}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 文件损坏也恢复默认
        return {"stock": []}


def save_code_file(store, filename):
    """写回 JSON 文件"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=4)


def add_code_to_file(code):
    """
    1. 读取文件
    2. 添加 code （自动去重）
    3. 保存文件
    """

    global ths_code,code_file_name
    filename = code_file_name
    store = load_code_file(filename)

    # 保证结构正确
    if "stock" not in store:
        store["stock"] = []

    if code not in store["stock"]:
        store["stock"].append(code)
        save_code_file(store, filename)
        get_ths_code()
        return True  # 成功添加
    else:
        return False  # 已存在，不写入

def get_monitors_info():
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

    monitors = []

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
        return 1  # 继续枚举

    MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int,
                                         ctypes.c_ulong,
                                         ctypes.c_ulong,
                                         ctypes.POINTER(RECT),
                                         ctypes.c_double)

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(monitor_enum_proc), 0)

    # 组合桌面
    if monitors:
        all_left = min(m['left'] for m in monitors)
        all_top = min(m['top'] for m in monitors)
        all_right = max(m['right'] for m in monitors)
        all_bottom = max(m['bottom'] for m in monitors)
        combined = {
            "left": all_left,
            "top": all_top,
            "right": all_right,
            "bottom": all_bottom,
            "width": all_right - all_left,
            "height": all_bottom - all_top
        }
    else:
        combined = None

    return combined['width'],combined['height']



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


# 使用示例
screen_width,screen_height, = get_monitors_info()
logger.info(f'screen_width:{screen_width} {screen_height}')
def schedule_task(name, delay_ms, func, *args):
    """带唯一名称的任务调度（重复调度会覆盖旧任务）"""
    global root
    # 如果已存在同名任务 -> 先取消
    if name in after_tasks:
        root.after_cancel(after_tasks[name]["id"])
        after_tasks.pop(name, None)

    # def wrapper():
    #     try:
    #         func(*args)
    #     finally:
    #         # 执行完后清理
    #         after_tasks.pop(name, None)
    def wrapper():
        try:
            func(*args)
        except Exception as e:
            logger.info(f"❌ 任务 {name} 执行异常:", e)
            import traceback; traceback.print_exc()
        finally:
            after_tasks.pop(name, None)

    task_id = root.after(delay_ms, wrapper)
    after_tasks[name] = {
        "id": task_id,
        "created": time.time(),
        "delay": delay_ms,
        "target": time.time() + delay_ms / 1000.0,
        "func": func,
        "args": args
    }
    return task_id

def cancel_task(name):
    if name in after_tasks:
        root.after_cancel(after_tasks[name]["id"])
        logger.info(f"任务 {name} 已取消")
        after_tasks.pop(name, None)

def show_tasks():
    logger.info("当前任务列表:")
    for name, info in after_tasks.items():
        logger.info(
            f"  Name={name}, ID={info['id']}, "
            f"目标时间={time.strftime('%H:%M:%S', time.localtime(info['target']))}, "
            f"函数={info['func'].__name__}"
        )
        remaining = max(0, info["target"] - time.time())
        logger.info(f"  Name={name}, ID={info['id']}, 剩余={remaining:.1f}s, 目标时间={...}")

    # root.after(2000, show_tasks)

# --------------------
# 启动线程
# --------------------
def start_worker(worker_task,param=None):
    global worker_thread, stop_event
    if worker_thread is not None and worker_thread.is_alive():
        logger.info("Worker running, stopping first...")
        # stop_worker(lambda: actually_start_worker(param))  # 停止完成后再启动
        stop_worker(lambda: actually_start_worker(worker_task,param))  # 停止完成后再启动
    else:
        actually_start_worker(worker_task,param)

def actually_start_worker(worker_task,param=None):
    global worker_thread, stop_event
    stop_event.clear()
    worker_thread = threading.Thread(target=worker_task, args=(param,), daemon=True)
    worker_thread.start()
    logger.info("Worker started!")
    check_worker_done()
    return worker_task

def check_worker_done():
    #检查任务结束更新视图
    global worker_thread,realdatadf
    if worker_thread and worker_thread.is_alive():
        root.after(2000, check_worker_done)  # 200ms 后再检查
    else:
        logger.info("Worker finished!")
        populate_treeview(realdatadf)  # 在主线程安全更新 UI

# --------------------
# 停止线程
# --------------------
def stop_worker(callback=None):
    """
    停止线程，并在停止完成后执行 callback（可启动新任务）
    """
    global worker_thread, stop_event
    if worker_thread is None or not worker_thread.is_alive():
        if callback:
            callback()
        return

    stop_event.set()  # 通知线程退出
    time.sleep(0.2)

    # 使用 after 定时检查线程状态，不阻塞 GUI
    def check_stop():
        global worker_thread
        if worker_thread is not None and worker_thread.is_alive():
            root.after(100, check_stop)  # 每100ms检查一次
        else:
            logger.info("Worker stopped")
            worker_thread = None
            stop_event.clear()
            if callback:
                callback()

    check_stop()




def get_pids(pname):
    # logger.info(pname)
    # find AutoHotkeyU64.exe
    pids = []
    for proc in psutil.process_iter():
        if pname in proc.name():
            pids.append(proc.pid)
    # logger.info(pids)
    return pids


def get_handles(pid):
    def callback(hwnd, handles):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)

            if found_pid == pid:
                handles.append(hwnd)
            return True

    handles = []
    win32gui.EnumWindows(callback, handles)
    return handles


def get_handle(pname):
    #not find AutoHotkeyU64.exe ths-tdx-web.py
    hwnd = 0
    pids = get_pids(pname)
    for pid in pids:
        handles = get_handles(pid)
        # logger.info(handles)
        for hwnd in handles:
            if IsWindowVisible(hwnd):
                return hwnd
    return hwnd


def get_pids_values(pname):
    # logger.info(pname)
    # find AutoHotkeyU64.exe
    pids = 0
    for proc in psutil.process_iter():
        if pname in proc.name():
            # pids.append(proc.pid)
            pids = proc.pid
    # logger.info(pids)
    return pids


def find_window_by_title_safe(target_title: str):
    # find ths-tdx-web.py
    """
    通过对目标标题使用 re.escape()，安全地查找包含空格和括号的窗口。
    """
    found_windows = []
    # findhwnd = 0
    # 使用 re.escape() 自动转义所有特殊字符
    escaped_title = re.escape(target_title)
    # 使用正则表达式匹配，并忽略大小写
    title_pattern = re.compile(escaped_title, re.IGNORECASE)

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            # 使用编译后的模式进行搜索
            if title_pattern.search(window_title):
                found_windows.append((hwnd, window_title))
    win32gui.EnumWindows(enum_handler, None)
    return found_windows


FAGE_READWRITE = 0x04  # 偏移地址：0x04的意思就是：在空间上偏移4个内存单元
PROCESS_ALL_ACCESS = 0x001F0FFF
VIRTUAL_MEN = (0x1000 | 0x2000)

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

def check_pid(pname,srcpid):
    pid = get_pids(pname)
    return pid == srcpid

def check_pids_all():
    # ['mainfree.exe','hexin.exe']
    tdxpname='tdxw.exe'
    thspname='hexin.exe'
    dfcfpname='mainfree.exe'
    global tdx_pid, ths_pid,dfcf_pid
    if not check_pid(tdxpname,tdx_pid):
        tdx_pid = get_pids(tdxpname)
        logger.info(f'tdx_pid:{tdx_pid}')
        find_tdx_window()
    if not check_pid(dfcfpname,dfcf_pid):
        global dfcf_process_hwnd
        dfcf_pid = get_pids('mainfree.exe')
        logger.info(f'dfcf_pid:{dfcf_pid}')
        dfcf_process_hwnd = get_handle('mainfree.exe')
    if not check_pid(thspname,ths_pid):
        global ths_process_hwnd,ths_prc_hwnd
        ths_pid = get_pids(thspname)
        logger.info(f'ths_pid:{ths_pid}')
        find_ths_window()

def ths_prc_hwnd(procname='hexin.exe'):
    global ths_process_hwnd
    pl = psutil.pids()
    for pid in pl:
        try:
            # 进程id 获取进程名 转化为小写
            if psutil.Process(pid).name().lower() == 'hexin.exe':
                # isinstance() 函数来判断一个对象是否是一个已知的类型 pid 是 int类型
                if isinstance(pid, int):
                    # 打开一个已存在的进程对象hexin.exe，并返回进程的句柄
                    ths_process_hwnd = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, int(pid))  # 申请内存所在的进程句柄
                    return ths_process_hwnd
        except psutil.NoSuchProcess:  # Catch the error caused by the process no longer existing
            logger.info(f"NoSuchProcess with pid: {pid}")
            # pass  # Ignore it
        else:
            pass
    return ths_process_hwnd

def bytes_16(dec_num, code):

    ascii_char = chr(dec_num)  # 将整数转换为对应的ASCII字符
    codex = ascii_char + str(code)
    # 将Python字符串转换为bytes类型
    bytes_codex = codex.encode('ascii', 'ignore')
    return bytes_codex

def ths_convert_code(code):

    # 上海，深圳股票判断;
    if str(code)[0] == '6':
        # 将16进制数转换为整数
        dec_num = int('11', 16)
        if code in ths_code:
            dec_num = 0x16
        bytes_codex = bytes_16(dec_num, code)
    # 11开头的可转债
    elif str(code).startswith('11'):
        # 将16进制数转换为整数
        dec_num = int('13', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('12'):
        # 将16进制数转换为整数
        dec_num = int('23', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('15'):
        # 将16进制数转换为整数
        dec_num = int('24', 16)
        bytes_codex = bytes_16(dec_num, code)

    elif str(code).startswith('90'):
        # 将16进制数转换为整数
        dec_num = int('12', 16)
        bytes_codex = bytes_16(dec_num, code)
    elif str(code).startswith('20'):
        # 将16进制数转换为整数
        dec_num = int('22', 16)
        bytes_codex = bytes_16(dec_num, code)
    else:
        # 将16进制数转换为整数
        dec_num = int('21', 16)
        bytes_codex = bytes_16(dec_num, code)

    return bytes_codex

def send_code_clipboard(stock_code,retry=True):
    global dfcf_process_hwnd,ahk_process_hwnd,thsweb_process_hwnd
    status = "未找到DC"
    if  dfcf_process_hwnd != 0 and (ahk_process_hwnd != 0 or thsweb_process_hwnd !=0):
        status = f" DC-> 成功"
        logger.info(f"已找到DFCF: {dfcf_process_hwnd} 发送成功")
        pyperclip.copy(stock_code)
        logger.info(f"hwnd:{dfcf_process_hwnd} Stock code {stock_code} copied to clipboard!")
    else:
        if retry:
            dfcf_process_hwnd = get_handle('mainfree.exe')
            ahk_process_hwnd = get_pids_values('AutoHotkey')
            result = find_window_by_title_safe('ths-tdx-web.py')
            if len(result) > 0:
                thsweb_process_hwnd,window_title = result[0]
            status = send_code_clipboard(stock_code,retry=False)

    return status

def send_code_message(code,retry=True):
    global ths_window_handle
    global ths_process_hwnd
    # # 同花顺进程句柄
    # ths_process_hwnd = ths_prc_hwnd()
    # # 用kerne132.VirtualAllocEx在目标进程开辟内存空间(用于存放数据)
    # 在指定进程的虚拟地址空间中保留、提交或更改内存区域的状态。 函数将它分配的内存初始化为零。
    status = "未找到THS"

    if ths_process_hwnd != 0 and ths_window_handle != 0:
        status = f"THS-> 成功"
        argv_address = kernel32.VirtualAllocEx(ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
        bytes_str = ths_convert_code(code)
        # 用kerne132.WriteProcessMemory在目标进程内存空间写入数据
        kernel32.WriteProcessMemory(ths_process_hwnd, argv_address, bytes_str, 7, None)
    # # 同花顺窗口句柄
        logger.info(f"已找到THS: {ths_window_handle} process: {ths_process_hwnd} 发送成功 bytes_str:{bytes_str}")
        # ths_window_handle = get_handle(exe)
        result = win32api.SendMessage(ths_window_handle, int(1168), 0, argv_address)
    else:
        if retry:
            find_ths_window()
            status = send_code_message(code,retry=False)
    return status

# 导入通达信联动代码中的相关类和函数
# from 通达信联动代码 import TdxStockSenderApp, HistoryRecord
# 定义所需的Windows API函数和类型
user32 = ctypes.windll.user32

# 定义回调函数类型
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_void_p)

# 定义所需的Windows API函数
EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
EnumWindows.restype = ctypes.c_bool

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

GetClassNameW = user32.GetClassNameW
GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetClassNameW.restype = ctypes.c_int

# PostMessageW = user32.PostMessageW
# PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
# PostMessageW.restype = ctypes.c_int

# RegisterWindowMessageW = user32.RegisterWindowMessageW
# RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
# RegisterWindowMessageW.restype = ctypes.c_uint

# 全局变量，用于存储通达信窗口句柄
tdx_window_handle = 0
ths_window_handle = 0
ths_process_hwnd = 0
dfcf_process_hwnd = 0
tdx_pid = 0
dfcf_pid = 0
ths_pid = 0
thsweb_process_hwnd = 0
ahk_process_hwnd = 0
# 這個變數將用於存放載入的DataFrame
loaded_df = None
date_write_is_processed = False



def minutes_to_time(target_int):
    """
    target_int: 整数，HHMM格式，例如 1300 表示 13:00
    返回当前时间距离目标时间的分钟数（正数表示还没到，负数表示已过）
    """
    now = datetime.now()
    target_hour = target_int // 100
    target_minute = target_int % 100
    target_time = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=target_hour, minutes=target_minute)

    delta = target_time - now
    return delta.total_seconds() / 60  # 分钟数（浮点）
    

# 示例
# logger.info(minutes_to_time(1300))


def get_now_time_int():
    now_t = datetime.now().strftime("%H%M")
    return int(now_t)

def get_now_time_int_sec():
    now_t = datetime.now().strftime("%H:%M:%S")
    return (now_t)


def get_last_weekday_before_out(target_date=datetime.today().date()):
    """
    获取指定日期之前的最后一个工作日。
    """
    one_day = timedelta(days=1)
    # 从目标日期开始，向前回溯一天
    current_date = target_date - one_day
    
    # 持续向前回溯，直到找到一个工作日（周一至周五）
    # weekday() 返回 0（周一）到 6（周日）
    while current_date.weekday() >= 5: # 5是周六，6是周日
        current_date -= one_day
    
    return current_date.strftime("%Y-%m-%d")

def get_next_trade_date(dt=None):
    if dt is None:
        dt = datetime.today().date().strftime('%Y-%m-%d')
    return(a_trade_calendar.get_next_trade_date(dt))

def get_last_weekday_before(dt=None):
    if dt is None:
        dt = datetime.today().date().strftime('%Y-%m-%d')
    return(a_trade_calendar.get_pre_trade_date(dt))

def get_day_is_trade_day():
    sep='-'
    TODAY = datetime.today().date()
    fstr = "%Y" + sep + "%m" + sep + "%d"
    dt = TODAY.strftime(fstr)    
    is_trade_date = a_trade_calendar.is_trade_date(dt)
    return(is_trade_date)
    # day_n = int(today.strftime("%w"))
    # if day_n > 0 and day_n < 6:
    #     return True
    # else:
    #     return False

def get_trade_date_status(dt=None):
    sep='-'
    if dt is None:
        TODAY = datetime.today().date()
        fstr = "%Y" + sep + "%m" + sep + "%d"
        dt = TODAY.strftime(fstr)
    else:
        if isinstance(dt, datetime.date):
            dt = dt.strftime('%Y-%m-%d')
    is_trade_date = a_trade_calendar.is_trade_date(dt)

    return(is_trade_date)


def get_work_time(now_t = None):
    # if not get_day_is_trade_day():
    if not get_trade_date_status():
        return False
    if now_t == None:
        now_t = get_now_time_int()
    if (now_t > 1131 and now_t < 1300) or now_t < 915 or now_t > 1502:
        return False
    else:
        return True



def find_ths_window(exe='hexin.exe'):
    global ths_window_handle
    global ths_process_hwnd
    # global ths_pid
    # ths_pid = get_pids('hexin.exe')
    # 同花顺进程句柄
    ths_process_hwnd = ths_prc_hwnd()
    # 用kerne132.VirtualAllocEx在目标进程开辟内存空间(用于存放数据)
    # 在指定进程的虚拟地址空间中保留、提交或更改内存区域的状态。 函数将它分配的内存初始化为零。

    # argv_address = kernel32.VirtualAllocEx(ths_process_hwnd, 0, 8, VIRTUAL_MEN, FAGE_READWRITE)
    # bytes_str = ths_convert_code(code)
    # # 用kerne132.WriteProcessMemory在目标进程内存空间写入数据
    # kernel32.WriteProcessMemory(ths_process_hwnd, argv_address, bytes_str, 7, None)

    # 同花顺窗口句柄
    ths_window_handle = get_handle(exe)
    if ths_process_hwnd != 0 and ths_window_handle != 0:
        status = True
    else:
        status = False
    return status

def find_tdx_window():
    """查找通达信窗口"""
    # global tdx_window_handle,tdx_pid
    global tdx_window_handle
    # tdx_pid = get_pids('tdxw.exe')
    def enum_windows_callback(hwnd, lparam):
        global tdx_window_handle

        # 获取窗口标题
        title_buffer = ctypes.create_unicode_buffer(256)
        GetWindowTextW(hwnd, title_buffer, 255)
        window_title = title_buffer.value

        # 获取窗口类名
        class_buffer = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, class_buffer, 255)
        window_class = class_buffer.value

        # 查找通达信窗口类名
        if "TdxW_MainFrame_Class" in window_class:
            tdx_window_handle = hwnd
            return False  # 找到后停止枚举

        return True

    # 将Python函数转换为C回调函数
    enum_proc = WNDENUMPROC(enum_windows_callback)

    # 重置通达信窗口句柄
    tdx_window_handle = 0

    # 枚举所有窗口
    EnumWindows(enum_proc, 0)

    if tdx_window_handle != 0:
        status = f"已找到通达信窗口，句柄: {tdx_window_handle}"
    else:
        status = "未找到通达信窗口，请确保通达信已打开"
    root.title(f"股票异动数据监控 + 通达信联动 - {status}")


def generate_stock_code(stock_code):
    """根据股票代码的第一位数字生成对应的代码"""
    if not stock_code:
        return None

    first_char = stock_code[0]

    if first_char in ['6','5']:
        return f"7{stock_code}"

    elif first_char in ['0','3','1']:
        
        return f"6{stock_code}"
    else:
        
        return f"4{stock_code}"

def send_to_tdx(stock_code):
    """发送股票代码到通达信"""
    global send_stock_code
    if send_stock_code and send_stock_code == stock_code:
        return
    else:
        send_stock_code = stock_code
        
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    if not tdx_state and not ths_state and not dfcf_state:
        root.title(f"股票异动数据监控")
    else:

        if len(stock_code.split()) == 2:
            stock_code,stock_name = stock_code.split()
        elif not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            # messagebox.showerror("错误", "请输入有效的6位股票代码:{stock_code}")
            logger.info(f"请输入有效的6位股票代码:{stock_code}")
            toast_message(root,f"请输入有效的6位股票代码:{stock_code}")
            return

        # 生成股票代码
        generated_code = generate_stock_code(stock_code)

        # 更新状态
        root.title(f"股票异动数据监控 + 通达信联动 - 正在发送...")

        # 在新线程中执行发送操作，避免UI卡顿
        threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()


def broadcast_stock_code(stock_code,message_type='stock'):
    if isinstance(stock_code, dict):
        stock_code = stock_code['content']
        stock_code = stock_code.strip()
    if len(stock_code) == 6:
        codex = int(stock_code)
        if str(message_type) == 'stock':
            if str(stock_code)[0] in ['0','3','1']:
                codex = '6' + str(stock_code)
            elif str(stock_code)[0] in ['6','5']:
                codex = '7' + str(stock_code)
            # elif str(stock_code)[0] == '9':
            #     codex = '2' + str(stock_code)
            else:
                codex = '4' + str(stock_code)
        else:
            codex = int(stock_code)
        UWM_STOCK = win32api.RegisterWindowMessage('stock')
        logger.info(f'{win32con.HWND_BROADCAST},{UWM_STOCK,str(codex)}')
        #系统广播
        status=win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)

def _send_to_tdx_thread(stock_code, generated_code,retry=True):
    """在线程中执行发送操作"""
    global tdx_window_handle
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    status = '成功'
    thsstatus = '成功'
    dfcfstatus = '成功'
    try:
        if tdx_state:
            # 发送消息
            broadcast_stock_code(stock_code)
            status = "发送成功"
        if ths_state:
            thsstatus = send_code_message(stock_code)
            logger.info(f"THS send Message posted:{thsstatus}")
            # root.after(3, _update_ui_after_send, status)
            status = f'{status} : {thsstatus}' 
        if dfcf_state:
            dfcfstatus = send_code_clipboard(stock_code)
            logger.info(f"DC Paste:{dfcfstatus}")
            if ths_state:
                status = f'{status} : {thsstatus} : {dfcfstatus}'
            else: 
                status = f'{status} : {dfcfstatus}' 

    except Exception as e:
        status = f"发送失败: {str(e)}"

    # 在主线程中更新UI
    root.after(0, _update_ui_after_send, status)

def _update_ui_after_send(status):
    """在发送操作完成后更新UI"""
    # 更新状态
    root.title(f"股票异动数据监控 + 通达信联动 - {status}")

#init map
symbol_map = {
    "火箭发射": "8201",
    "快速反弹": "8202",
    "大笔买入": "8193",
    "封涨停板": "4",
    "打开跌停板": "32",
    "有大买盘": "64",
    "竞价上涨": "8207",
    "高开5日线": "8209",
    "向上缺口": "8211",
    "60日新高": "8213",
    "60日大幅上涨": "8215",
    "加速下跌": "8204",
    "高台跳水": "8203",
    "大笔卖出": "8194",
    "封跌停板": "8",
    "打开涨停板": "16",
    "有大卖盘": "128",
    "竞价下跌": "8208",
    "低开5日线": "8210",
    "向下缺口": "8212",
    "60日新低": "8214",
    "60日大幅下跌": "8216",
}

# #获取全部数据
# def get_dfcf_all_data():

#     # if not (get_day_is_trade_day() and get_now_time_int() > 1505):
#     url = "https://push2ex.eastmoney.com/getAllStockChanges?"

#     reversed_symbol_map = {v: k for k, v in symbol_map.items()}

#     params = {
#         'ut': '7eea3edcaed734bea9cbfc24409ed989',
#         'pageindex': '0',
#         'pagesize': '50000',
#         'dpt': 'wzchanges',
#         '_': int(time.time() * 1000)
#     }

#     df = pd.DataFrame()

#     for sel_type in symbol_map:

#         params['type'] = symbol_map[sel_type]
    
#         try:
#             response = requests.get(url, params=params, timeout=15)
#             response.raise_for_status()
#             data_json = response.json()
            
#             if not data_json.get('data') or not data_json['data'].get('allstock'):
#                 messagebox.showinfo("提示", "未获取到数据")
#                 return pd.DataFrame()
            
#             temp_df = pd.DataFrame(data_json["data"]["allstock"])
#             if 'tm' not in temp_df.columns:
#                 return pd.DataFrame()
            
#             temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
#             temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
#             temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            
#             temp_df["板块"] = temp_df["板块"].astype(str).map(
#                 lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
#             )

#             temp_df = temp_df.sort_values(by="时间", ascending=False)
#             df = pd.concat([df, temp_df], axis=0)

#         except requests.exceptions.Timeout:
#             messagebox.showerror("错误", "请求超时")
#             return pd.DataFrame()
#         except requests.exceptions.RequestException as e:
#             messagebox.showerror("错误", f"网络错误: {str(e)}")
#             return pd.DataFrame()
#         except Exception as e:
#             messagebox.showerror("错误", f"数据处理错误: {str(e)}")
#             return pd.DataFrame()

#     return df

def start_async_save(df=None):
    """启动一个新线程来保存DataFrame"""
    # 创建并启动新线程
    # logger.info("正在启动save_dataframe后台保存任务...")
    # # save_thread = executor.submit(save_dataframe)
    # save_thread = threading.Thread(target=save_dataframe)
    # save_thread.start()
    """后台线程保存 DataFrame"""
    logger.info("正在启动 save_dataframe 后台保存任务...")
    
    def save_wrapper():
        try:
            save_dataframe()  # 确保 save_dataframe 内部可以安全在后台线程运行
        except Exception as e:
            logger.info(f"保存出错:{e}")
    
    save_thread = threading.Thread(target=save_wrapper, daemon=True)
    save_thread.start()
    # save_wrapper()


def schedule_daily_archive(root, hour=15, minute=5, archive_file=None):
    """每日固定时间执行存档任务，仅工作日"""
    
    def archive_func():
        logger.info(f'archive_func datetime.now() : {datetime.now()}')
        start_async_save()
        # start_async_save_dataframe()

    def next_archive_time():
        """计算下一次存档时间，跳过周末"""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 如果已经过今天目标时间或今天是周末，则找下一个工作日
        while target <= now or target.weekday() >= 5:  # 5=周六,6=周日
            target =  get_next_weekday_time(hour, minute)
            # target += timedelta(days=1)
            # target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target

    def check_and_schedule():
        now = datetime.now()
        next_time = next_archive_time()
        delay = (next_time - now).total_seconds() * 1000  # 毫秒
        logger.info(f"下一次存档时间: {next_time}, 延迟 {int(delay)} ms")
        root.after(int(delay), run_archive)

    def run_archive():
        archive_func()
        # 执行完成后再次调度下一次
        check_and_schedule()

    # 启动时检查文件是否存在，不存在立即存档（仅工作日）
    # if not os.path.exists(archive_file) and datetime.datetime.now().weekday() < 5:
    #     archive_func()
    archive_func()

    # 第一次调度
    check_and_schedule()

# --- 儲存 DataFrame 的函數 ---
def save_dataframe(df=None):
    """獲取選取的日期，並將 DataFrame 儲存為以該日期命名的檔案。"""
    global date_write_is_processed
    global loaded_df,start_init
    if not get_day_is_trade_day():
        date_str = get_last_weekday_before()
    else:
        date_str = get_today()
    # filename = f"datacsv\\dfcf_{date_str}.csv.bz2"
    filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
    # --- 核心檢查邏輯 ---
    if get_now_time_int() > 1505 and  os.path.exists(filename):
        logger.info(f' workday:{date_str} {filename} exists,return')
        return

    init_start_time = time.time()
    while not start_init:
        now_time = get_now_time_int()
        is_trade_day = get_day_is_trade_day()
        work_time = get_work_time()

        # 条件判断
        in_trade_session = is_trade_day and 930 < now_time < 1505
        is_non_trade_day_with_file = (not is_trade_day) and os.path.exists(filename)

        if work_time or in_trade_session or is_non_trade_day_with_file:
            logger.info("条件满足，不执行 save_dataframe...")
            return

        # 等待逻辑
        count_time = int(time.time() - init_start_time)
        if is_trade_day and count_time < 90:
            logger.info(f'count_time : {count_time}，等待初始化完成...')
            time.sleep(5)
        else:
            break
    logger.info(f'start_init:{start_init}  will to save')    
    toast_message(None,f'start_init:{start_init} will to save')    
    try:
        # 1. 從 DateEntry 獲取日期物件
        # selected_date_obj = date_entry.get_date()
        # 2. 格式化日期為字串
        # 例如: 2025-09-03
        # date_str = selected_date_obj.strftime("%Y-%m-%d")
        # date_str = get_last_weekday_before()
        logger.info(f'save date_str : {date_str}')
        
        # 3. 建立檔名（這裡儲存為 CSV）
        # selected_type  = type_var.get()
        filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
        date_write_is_processed = True
        
        # --- 核心檢查邏輯 ---
        if os.path.exists(filename):
            logger.info(f"文件 '{filename}' 已存在，放棄寫入。")
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
        else:
            global realdatadf_lock
            logger.info(f'realdatadf_lock:{realdatadf_lock}')
            time.sleep(6)
            all_df = get_stock_changes_background()
            all_df.loc[:,'代码'] = all_df["代码"].astype(str).str.zfill(6)
            # 4. 儲存 DataFrame
            all_df.to_csv(filename, index=False, encoding='utf-8-sig', compression="bz2") 
            # messagebox.showinfo("成功", f"文件已儲存為: {filename}")
            logger.info(f"文件已儲存為: {filename}")
            toast_message(None,f"文件已儲存為: {filename}")
            loaded_df = all_df
        loaded_df.loc[:, "代码"] = loaded_df["代码"].astype(str).str.zfill(6)  # 改写简单赋值

        return loaded_df

    except Exception as e:
        messagebox.showerror("錯誤", f"save_data儲存文件時發生錯誤: {e}")
        logger.info(f"save_data儲存文件時發生錯誤: {e}")
        logger.info(f"save_data儲存文件時發生錯誤: {loaded_df[:5]}")



# 使用之前定义的解析函数
def parse_related_info(row):
    """
    根據異動類型解析「相關信息」欄位，並返回一個包含 (漲幅, 價格, 量) 的元組。
    """
    related_info = row['相关信息']
    stock_type = row['板块']
    
    try:
        # 將字串轉換為浮點數列表
        values = [float(v.strip()) for v in related_info.split(',')]
    except (ValueError, IndexError):
        return None, None, None
    
    漲幅 = None
    價格 = None
    量 = None
    
    if stock_type in ['火箭发射', '快速反弹', '60日大幅上涨', '高台跳水', '竞价下跌']:
        # 這幾種類型通常漲跌幅和價格在前面
        if len(values) >= 3:
            漲幅 = round(values[0] * 100, 1) # 漲跌幅在索引 0
            價格 = values[1]                # 價格在索引 1
            量 = 0.0
    elif stock_type in ['大笔买入', '有大买盘', '有大卖盘']:
        # 這幾種類型交易量在前面，漲跌幅在中間
        if len(values) >= 4:
            漲幅 = round(values[2] * 100, 1) # 漲跌幅在索引 2
            價格 = values[1]                # 價格在索引 1
            量_原始 = values[0]
            # 量 = round(量_原始 / 100 / 10000, 2) # 將股數轉換為萬手
            量 = round(量_原始 / 100 / 1000, 1) # 將股數轉換為千手
    elif stock_type in ['封涨停板', '60日新高']:
        # 這幾種類型價格在前，漲跌幅在最後
        if len(values) >= 4:
            漲幅 = round(values[3] * 100, 1) # 漲跌幅在索引 3
            價格 = values[0]                # 價格在索引 0
            量_原始 = values[1]
            # 量 = round(量_原始 / 100 / 10000, 2) # 將股數轉換為萬手
            量 = round(量_原始 / 100 / 1000, 1) # 將股數轉換為千手
    elif stock_type in ['打开涨停板']:
        # 漲跌幅在最後，價格在前面
        if len(values) >= 2:
            漲幅 = round(values[1] * 100, 1) # 漲跌幅在索引 1
            價格 = values[0]                # 價格在索引 0
            量 = 0.0
    elif stock_type in ['60日新高']:
        # 根據您提供的錯誤數據，60日新高似乎有另一種格式
        if len(values) >= 3:
            漲幅 = round(values[2] * 100, 1) # 漲幅在索引 2
            價格 = values[1]                # 價格在索引 1
            量 = 0.0
    else:
        # 其他未知的異動類型，返回 None
        return None, None, None
        
    return 漲幅, 價格, 量

def process_full_dataframe(df):
    """
    處理原始 DataFrame，解析相關信息並計算出現次數。
    """
    # 步驟1: 應用解析函數並擴展列
    # df = df[["时间", "代码", "名称", "板块", "相关信息"]]
    if df is not None and not df.empty:
        df = df.copy()
        parsed_data = df.apply(parse_related_info, axis=1, result_type='expand')
        df[['涨幅', '价格', '量']] = parsed_data

        # 步驟2: 使用 fillna(0.0) 填充 NaN 值
        df.loc[:,['涨幅', '价格', '量']] = df[['涨幅', '价格', '量']].astype(float).fillna(0.0)

        # 步驟3: 計算每個“代码”出現的次數
        # df['count'] = df.groupby('代码')['代码'].transform('count')
        df.loc[:, 'count'] = df.groupby('代码')['代码'].transform('count')
        df = df[['时间', '代码', '名称','count', '板块','相关信息', '涨幅', '价格', '量']]
    return df

        
def get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    global realdatadf, last_updated_time,symbol_map
    current_time = datetime.now()
    url = "https://push2ex.eastmoney.com/getAllStockChanges?"
    reversed_symbol_map = {v: k for k, v in symbol_map.items()}
    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': int(time.time() * 1000)
    }

    if selected_type:
        if selected_type in symbol_map:
            params['type'] = symbol_map[selected_type]
        else:
            messagebox.showerror("错误", f"无效的异动类型: {selected_type}")
            return pd.DataFrame()
    else:
        params['type'] = ','.join(symbol_map.values())
    
    try:
        global loaded_df
        global date_write_is_processed

        if loaded_df is None:

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data_json = response.json()
            
            if not data_json.get('data') or not data_json['data'].get('allstock'):
                logger.info("提示", "未获取到数据")
                return pd.DataFrame()
            
            temp_df = pd.DataFrame(data_json["data"]["allstock"])
            if 'tm' not in temp_df.columns:
                return pd.DataFrame()
            
            # temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            # temp_df["tm"] = temp_df["tm"].apply(lambda x: pd.to_datetime(x, format="%H%M%S", errors='coerce').time() if pd.notna(x) else pd.NaT)
            # temp_df["tm"] = temp_df["tm"].astype(object)
            # 转换时间字段
            # temp_df.loc[:, "tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            # temp_df.loc["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors="coerce").dt.time
            # 1. 计算新的 'tm' 列
            new_tm_series = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors="coerce").dt.time
            # 2. 使用 assign 将计算结果添加到 DataFrame 中
            temp_df = temp_df.assign(tm=new_tm_series)

            temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
            temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            # temp_df["板块"] = temp_df["板块"].astype(str).map(
            #     lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            # ).astype(str)  # 或 .astype(object)
            # temp_df.loc[:, "板块"] = temp_df["板块"].astype(str).map(
            #     lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            # ).astype(str) 
            # 推荐修改方案：使用 .assign()
            temp_df = temp_df.assign(
                板块=temp_df["板块"]
                .astype(str)
                .map(lambda x: reversed_symbol_map.get(x, f"未知类型({x})"))
                .astype(str)
            )

            # 或者使用 lambda 表达式，让代码更清晰：
            # temp_df = temp_df.assign(
            #     板块=lambda df: df["板块"]
            #     .astype(str)
            #     .map(lambda x: reversed_symbol_map.get(x, f"未知类型({x})"))
            #     .astype(str)
            # )

            temp_df = temp_df.sort_values(by="时间", ascending=False)
        else:
            temp_df = loaded_df
        temp_df = filter_stocks(temp_df,selected_type)
        
        if stock_code:
            stock_code = stock_code.zfill(6)
            temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]
        return temp_df
        
    except requests.exceptions.Timeout:
        # messagebox.showerror("错误", "请求超时")
        toast_message(None, "请求超时")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        # messagebox.showerror("错误", f"网络错误: {str(e)}")
        logger.info(f"网络错误: {str(e)}")
        toast_message(None, f"网络错误: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        # messagebox.showerror("错误", f"数据处理错误: {str(e)}")
        toast_message(None,f"数据处理错误: {str(e)}")
        return pd.DataFrame()


def filter_stocks(df,selected_type):
    """过滤股票数据，排除8开头的股票、名称带*的股票、ST股票"""
    if df.empty:
        return df
    
    # 排除8开头的股票
    df = df[~df["代码"].astype(str).str.startswith('8')]

    if selected_type is not None and not selected_type == '':
        df = df[df['板块'] == selected_type]
    if '时间' in df.columns and len(df) > 0:
        df = df.sort_values(by="时间", ascending=False)

    # 排除名称中带*的股票
    # df = df[~df["名称"].str.contains('\\*')]
    # 排除ST股票
    # df = df[~df["名称"].str.startswith('ST')]
    return df

def get_today(sep='-'):
    TODAY = datetime.today().date()
    fstr = "%Y" + sep + "%m" + sep + "%d"
    today = TODAY.strftime(fstr)
    return today

def populate_treeview(data=None):
    """填充表格数据"""
    global viewdf

    tree.delete(*tree.get_children())
    if data is None:
        data = get_stock_changes()

    if '涨幅' not in data.columns:
        data = process_full_dataframe(data)

    viewdf = data.copy()
    uniq_state =uniq_var.get()
    if data is not None and not data.empty and uniq_state:
        data = data.drop_duplicates(subset=['代码'])

    if data is not None and not data.empty:
        if 'count'  not in data.columns:
            data['count'] = data.groupby('代码')['代码'].transform('count')
        fast_insert(tree,data)
    else:
        status_var.set("无数据")
        tree.insert("", "end", values=("无数据", "", "", "", ""))

def check_string_type(s: str) -> str:
    if not s:  # 空字符串
        return False
    if re.fullmatch(r"[A-Za-z]+", s):
        return True
    elif all('\u4e00' <= ch <= '\u9fff' for ch in s):
        # return "only chinese"
        return True
    elif any('\u4e00' <= ch <= '\u9fff' for ch in s) and re.search(r"[A-Za-z]", s):
        # return "mixed"
        return True
    else:
        return False

def contains_chinese(s: str) -> bool:
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)

def is_all_chinese(s: str) -> bool:
    return all('\u4e00' <= ch <= '\u9fff' for ch in s)

last_searched_code = None
last_clear_time = 0   # 记录上一次点击清空按钮的时间

def clear_code_entry():
    """清空搜索框并执行搜索"""
    # 获取 code_entry 内容并记录（确保是6位数字）
    global last_searched_code,last_clear_time

    now = time.time()

    # -----------------------------
    # 1. 连续两次点击小于 2 秒 → 重置全局 code
    # -----------------------------
    if last_searched_code and now - last_clear_time < 1:
        logger.info("连续双击清空按钮，重置 last_searched_code = None")
        last_searched_code = None
    
    last_clear_time = now  # 更新上一次清空时间

    code = code_entry.get().strip()
    # selected_type = type_var.get()
    # logger.info(f"记录的代码: {code} selected_type:{selected_type}")

    # if not code and last_searched_code:
    #     logger.info(f"clear记录的代码: {last_searched_code}")
    #     last_searched_code = None
    
    # 清空搜索框内容并执行搜索
    code_entry.delete(0, tk.END)
    search_by_code()  # 调用搜索函数

# def scroll_to_code_in_treeview(monitor_tree,stock_code):
#     """Helper function to scroll to a specific stock code in the treeview"""
#     for item in monitor_tree.get_children():
#         values = monitor_tree.item(item, 'values')
#         if values and values[1] == stock_code:
#             monitor_tree.selection_set(item)
#             monitor_tree.yview_scroll(1, 'units')  # Scroll to the selected row
#             break

def scroll_to_code_in_treeview(monitor_tree, stock_code):
    """Helper function to scroll to a specific stock code in the treeview"""
    for item in monitor_tree.get_children():
        values = monitor_tree.item(item, 'values')
        if values and values[1] == stock_code:
            monitor_tree.selection_set(item)
            monitor_tree.focus(item)
            monitor_tree.see(item)   # 确保该行滚动到可见
            break

def search_by_code(event=None,onclick=False):
    """按代码搜索"""
    global last_searched_code
    code = code_entry.get().strip()
    selected_type = type_var.get()

    if code.isdigit():  # 输入是数字
        if len(code) == 6:
            data = _get_stock_changes(stock_code=code)
        else:
            # 其他长度也可以模糊匹配
            df = _get_stock_changes()
            data = df[df["代码"].str.match(rf"^({code})")]

    # elif last_searched_code:  # If no code is entered, use the last searched code
    #     search_by_type() 

    else:
        # 非数字，模糊匹配名称
        if check_string_type(code):
            df = _get_stock_changes()
            data = df[df["名称"].str.contains(code, case=False, na=False)]

    logger.info(f"将记录的代码: {code} onclick:{onclick}")

    if onclick and code.isdigit() and len(code) == 6:
        last_searched_code = code
        logger.info(f"onclick: {onclick} 记录的代码: {code}")

    if code:
        status_var.set(f"搜索代码: {code}")
        populate_treeview(data)
        
    else:
        search_by_type()  # 如果没有 code，则按类型搜索
        # 如果有找到 code，滚动到该条目
        # if onclick:


        # if last_searched_code:
        #     scroll_to_code_in_treeview(tree,last_searched_code)


            # for item in monitor_tree.get_children():
            #     if monitor_tree.item(item, "values")[1] == last_searched_code:
            #         monitor_tree.see(item)
            #         break



def search_by_code_old(event=None):
    """按代码搜索"""
    code = code_entry.get().strip()
    selected_type = type_var.get()

    if code.isdigit():  # 输入是数字
        if len(code) == 6:
            data = _get_stock_changes(stock_code=code)
        else:
            # 其他长度也可以模糊匹配
            df = _get_stock_changes()
            # data = df[df["代码"].str.contains(code)]
            data = df[df["代码"].str.match(rf"^({code})")]

    else:
        # 非数字，模糊匹配名称
        if check_string_type(code):
            df = _get_stock_changes()
            data = df[df["名称"].str.contains(code, case=False, na=False)]


    if code:
        status_var.set(f"搜索代码: {code}")
        populate_treeview(data)
    else:
        search_by_type()

def search_by_type():
    """按异动类型搜索"""
    global last_searched_code
    selected_type = type_var.get()
    code_entry.delete(0, tk.END)

    status_var.set(f"加载{selected_type if selected_type else '所有'}异动数据")
    data = _get_stock_changes(selected_type=selected_type)
    populate_treeview(data)
    if last_searched_code:
        scroll_to_code_in_treeview(tree,last_searched_code)

def refresh_data():
    """刷新数据"""

    global loaded_df,viewdf,realdatadf,start_init,scheduled_task
    global date_write_is_processed,worker_thread,last_updated_time
    # logger.info(loaded_df is not None , loaded_df is not None and not loaded_df.empty,start_init)
    if loaded_df is not None and not loaded_df.empty:
        date_write_is_processed = False
        if date_entry.winfo_exists():
            try:
                date_entry.set_date(get_today())
            except Exception as e:
                logger.info(f"还不能设置:{e}")
        if scheduled_task:
            root.after_cancel(scheduled_task)
            time.sleep(0.1)
        show_tasks()
        loaded_df = None
        start_init = 0
        viewdf = pd.DataFrame()
        realdatadf = pd.DataFrame()
        logger.info('start refresh_data get_stock_changes_background')
        start_worker(schedule_worktime_task,tree)
        last_updated_time = None

    status_var.set("刷新中...")
    current_type = type_var.get()
    current_code = code_entry.get().strip()
    
    if current_code:
        search_by_code()
    else:
        search_by_type()
    
    tree.focus_set()

def on_tree_select(event):
    """处理表格行选择事件"""
    global last_searched_code
    selected_item = tree.selection()
    if selected_item:
        stock_info = tree.item(selected_item, 'values')
        stock_code = stock_info[1]
        stock_code = stock_code.zfill(6)

        # 1. 推送代码到输入框
        if last_searched_code is None or  last_searched_code != stock_code:
            send_to_tdx(stock_code)
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)
            # 2. 更新其他数据（示例）
            logger.info(f"选中股票代码: {stock_code}")
        time.sleep(0.1)

def on_code_entry_change(event=None):
    """处理代码输入框变化事件"""
    code = code_entry.get().strip()
    if len(code) == 6:  # 仅当输入长度等于6时触发联动
         # _get_stock_changes(stock_code=code)
        send_to_tdx(code)

# 1. 定义一个全局变量来存储最近的事件对象
last_event = None

def right_click_paste(event):
    global last_event
    last_event = event
    try:
        text = root.clipboard_get()   # 从系统剪贴板获取内容
    except tk.TclError:
        return  # 剪贴板为空或不是文本
    
    match = re.search(r"\d{6}", text)
    if match:
        stock_code = match.group(0)
        code_entry.delete(0, tk.END)       # 清空输入框
        code_entry.insert(0, stock_code)   # 插入股票代码
        # 如果需要自动回车，可以模拟触发回车事件
        code_entry.event_generate("<Return>")
    else:
        # 如果没有匹配，就按正常粘贴
        code_entry.event_generate("<<Paste>>")

def delete_selected_records():
    """删除选中的记录"""
    selected_items = tree.selection()
    if selected_items:
        if messagebox.askyesno("确认", "确定要删除选中的记录吗？"):
            for item in selected_items:
                tree.delete(item)
            status_var.set(f"已删除 {len(selected_items)} 条记录")
    else:
        messagebox.showinfo("提示", "请先选择要删除的记录")


def on_date_selected(event):
    """处理日期选择事件"""
    selected_date = date_entry.get()
    logger.info(f"选择了日期: {selected_date}")
    global loaded_df,last_updated_time
    
    try:
        # 1. 獲取日期並建立檔名
        selected_date_obj = date_entry.get_date()
        date_str = selected_date_obj.strftime("%Y-%m-%d")
        selected_type  = type_var.get()
        filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
        logger.info(f"嘗試載入文件: {filename}")

        # 2. 檢查檔案是否存在
        if os.path.exists(filename):
            stop_worker()
            last_updated_time = None
            # 檔案存在，載入到 DataFrame
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
            # loaded_df['代码'] = loaded_df['代码'].apply(lambda x:str(x))
            loaded_df.loc[:, "代码"] = loaded_df["代码"].astype(str).str.zfill(6)  # 改写简单赋值
            # 這裡可以根據需要更新 Treeview 或其他UI
            populate_treeview(loaded_df)
            
            # messagebox.showinfo("成功", f"文件 '{filename}' 已成功載入。")
            
        else:
            # 檔案不存在
            messagebox.showinfo("文件不存在", f"文件 '{filename}' 不存在，請檢查。")
            
    except Exception as e:
        messagebox.showerror("錯誤", f"載入文件時發生錯誤: {e}")
        logger.info(f"載入文件時發生錯誤: {e}")

def update_linkage_status():
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    if not tdx_state:
        global tdx_window_handle
        tdx_window_handle = 0
    if not ths_state:
        global ths_process_hwnd,ths_window_handle
        ths_process_hwnd = 0
        ths_window_handle = 0
    if not dfcf_state:
        global dfcf_process_hwnd
        dfcf_process_hwnd = 0
    if uniq_var.get() or not uniq_var.get():
        show_tasks()
    logger.info(f"TDX: {tdx_var.get()}, THS: {ths_var.get()}, DC: {dfcf_var.get()}, Uniq: {uniq_var.get()},Sub: {sub_var.get()} ,Win, {win_var.get()}")

def daily_task():
    """
    这个函数包含了你希望每天执行的逻辑。
    """
    logger.info(f"daily_task每日定时任务执行了！当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # save_dataframe()
    show_tasks()
    for name, info in after_tasks.items():
        if 'worksaveday_task' == name:
            logger.info('worksaveday_task is running ,return')
            return
    start_async_save()
    # start_async_save_dataframe()
    # 在这里添加你的具体任务，例如：

# ui_queue = queue.Queue()      # UI 更新队列
# data_queue = queue.Queue()    # 后台线程数据队列

# def process_ui_queue():
#     while not ui_queue.empty():
#         func = ui_queue.get()
#         func()
#     root.after(100, process_ui_queue)  # 每 100ms 处理一次

# def process_data_queue():
#     while not data_queue.empty():
#         df = data_queue.get()
#         # df 就是后台线程生成的 realdatadf，可以安全存档
#         date_str = date_entry.get_date()
#         filename = f"datacsv/dfcf_{date_str}.csv.bz2"
#         logger.info(f'start save date: {df.shape} filename : {filename}')
#         df.to_csv(filename, index=False, encoding='utf-8-sig', compression='bz2')
#         toast_message(None, f"文件已存儲: {filename}")
#         logger.info( f"文件已存儲: {filename}")
#     # 继续轮询
#     root.after(500, process_data_queue)

# def start_async_save_dataframe():
#     """后台线程安全保存 DataFrame，UI 不阻塞"""
#     def worker():
#         global date_write_is_processed, loaded_df, start_init

#         # 获取今天/最后交易日日期
#         if not get_day_is_trade_day():
#             date_str = get_last_weekday_before()
#         else:
#             date_str = get_today()
#         filename = os.path.join(BASE_DIR, "datacsv", f"dfcf_{date_str}.csv.bz2")

#         # 核心检查逻辑
#         if get_now_time_int() > 1505 and os.path.exists(filename):
#             logger.info(f'workday:{date_str} {filename} exists, return')
#             return

#         init_start_time = time.time()
#         while not start_init:
#             now_time = get_now_time_int()
#             is_trade_day = get_day_is_trade_day()
#             work_time = get_work_time()
#             in_trade_session = is_trade_day and 930 < now_time < 1505
#             is_non_trade_day_with_file = (not is_trade_day) and os.path.exists(filename)

#             if work_time or in_trade_session or is_non_trade_day_with_file:
#                 logger.info("条件满足，不执行 save_dataframe...")
#                 return

#             count_time = int(time.time() - init_start_time)
#             if is_trade_day and count_time < 90:
#                 logger.info(f'count_time : {count_time}，等待初始化完成...')
#                 time.sleep(5)
#             else:
#                 break

#         logger.info(f'start_init:{start_init} will to save')
#         # root.after(0, lambda: toast_message(None, f'start_init:{start_init} will to save'))
#         ui_queue.put(lambda: toast_message(None, f'start_init:{start_init} will to save'))


#         try:
#             # ✅ UI 访问部分，先在主线程安全获取
#             # selected_date_obj = date_entry.get_date()
#             # selected_type_val = type_var.get()
#             # date_str = selected_date_obj.strftime("%Y-%m-%d")

#             date_str = get_last_weekday_before()
#             filename = os.path.join(BASE_DIR, "datacsv", f"dfcf_{date_str}.csv.bz2")
#             date_write_is_processed = True

#             # 后台耗时任务
#             if os.path.exists(filename):
#                 logger.info(f"文件 '{filename}' 已存在，加载...")
#                 loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
#             else:
#                 # 模拟耗时等待
#                 time.sleep(6)
#                 logger.info(f"文件 '{filename}' 不存在，init to save...")
#                 all_df = get_stock_changes_background()
#                 all_df['代码'] = all_df["代码"].astype(str).str.zfill(6)
#                 # 保存 CSV
#                 if all_df and not all_df.empty:
#                     logger.info(' data_queue.put(all_df) : {all_df.shape}')
#                     data_queue.put(all_df)
#                 else:
#                     ui_queue.put(lambda: toast_message(None, f'df is None'))

#                 # all_df.to_csv(filename, index=False, encoding='utf-8-sig', compression="bz2")
#                 loaded_df = all_df
#                 # UI 提示
#                 msg = f"文件已儲存為: {filename}"
#                 ui_queue.put(lambda: toast_message(None, msg))
#                 logger.info(f"文件已儲存為: {filename}")

#             loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)

#         except Exception as e:
#             # 异常 UI 提示必须在主线程
#             # root.after(0, lambda: messagebox.showerror("錯誤", f"save_data儲存文件時發生錯誤: {e}"))
#             msg = f"save_data儲存文件時發生錯誤: {e}"
#             ui_queue.put(lambda: toast_message(None, msg))
#             # ui_queue.put(lambda: toast_message(None, f"save_data儲存文件時發生錯誤: {e}"))

#             logger.info(f"save_data儲存文件時發生錯誤: {e}")

#     # 启动后台线程
#     threading.Thread(target=worker, daemon=True).start()


def get_next_weekday_time(target_hour, target_minute):
    """
    获取下一次交易日的指定时间
    """
    now = datetime.now()
    
    # 今天的目标时间
    target_time_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 获取今天的日期字符串
    today_str = now.date().strftime('%Y-%m-%d')

    # 判断今天是否是交易日
    try:
        next_trade_str = a_trade_calendar.get_next_trade_date(today_str)
        # next_trade_str = a_trade_calendar.get_next_trade_date(today_str)
    except Exception:
        # 如果今天不在交易日历中，则获取下一个交易日
        next_trade_str = a_trade_calendar.get_next_trade_date(today_str)

    # 如果今天是交易日且还没到目标时间，则使用今天
    if (get_trade_date_status() or today_str == next_trade_str) and now < target_time_today:
        return target_time_today
    
    # 否则获取下一个交易日
    # next_day_str = a_trade_calendar.get_next_trade_date(today_str)
    next_day = datetime.strptime(next_trade_str, '%Y-%m-%d')
    
    # 返回下一交易日的目标时间
    next_trade_time = next_day.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    return next_trade_time


def get_next_trade_time_mod_notest(target_hour, target_minute):
    """
    获取下一个交易日的指定时间（未来时间）
    """
    now = datetime.now()
    today_str = now.date().strftime('%Y-%m-%d')
    
    # 今天的目标时间
    target_time_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    try:
        next_trade_str = a_trade_calendar.get_next_trade_date(today_str)
    except Exception:
        # 异常直接取今天之后的下一交易日
        next_trade_str = today_str  # 防止报错
    
    # 如果今天是交易日且还没到目标时间
    if get_trade_date_status() and now < target_time_today:
        return target_time_today
    
    # 否则使用下一个交易日
    next_day = datetime.strptime(next_trade_str, '%Y-%m-%d')
    next_trade_time = next_day.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 确保 next_trade_time > now，如果出现意外，顺延一天
    if next_trade_time <= now:
        next_trade_time += timedelta(days=1)
        while not is_trade_day(next_trade_time):
            next_trade_time += timedelta(days=1)
    
    return next_trade_time


def get_next_weekday_time_out(target_hour, target_minute):
    """
    计算下一次在工作日的指定时间。
    """
    now = datetime.now()
    
    # 获取今天在工作日内的目标时间
    target_time_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 如果今天已经过了目标时间，或者今天是周末，则从明天开始寻找下一个工作日
    if now >= target_time_today or now.weekday() >= 5: # 5是周六，6是周日
        next_day = now + timedelta(days=1)
    else:
        # 如果今天没过目标时间且是工作日，就在今天执行
        return target_time_today

    # 循环直到找到下一个工作日
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)

    # 结合找到的日期和目标时间
    next_weekday_time = next_day.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    return next_weekday_time

def check_readldf_exist():
    # selected_date_obj = date_entry.get_date()
    # # 2. 格式化日期為字串
    # # 例如: 2025-09-03
    # date_str = selected_date_obj.strftime("%Y-%m-%d")
    global loaded_df,realdatadf,date_entry,start_init
    date_str = get_today()

    if not get_day_is_trade_day() or (get_day_is_trade_day() and (get_now_time_int() < 923)):
        if  not get_day_is_trade_day() or (get_day_is_trade_day() and (get_now_time_int() >1530  or get_now_time_int() < 923)):
            date_str = get_last_weekday_before()
    # 3. 建立檔名（這裡儲存為 CSV）
    selected_type  = type_var.get()
    filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
    # --- 核心檢查邏輯 ---
    if (not get_day_is_trade_day() or (get_day_is_trade_day() and (get_now_time_int() >1505  or get_now_time_int() < 923))) and  os.path.exists(filename):
        if date_entry.winfo_exists():
            try:
                date_entry.set_date(date_str)
            except Exception as e:
                logger.info(f"还不能设置: {e}")
        logger.info(f"文件 '{filename}' 已存在，放棄寫入,已加载")
        loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
        # loaded_df["代码"] = loaded_df["代码"].astype(object)
        # loaded_df.loc[:, '代码'] = loaded_df['代码'].astype(str).str.zfill(6)
        # 推荐写法：使用字符串作为列名
        loaded_df = loaded_df.assign(
            代码 = loaded_df["代码"].astype(str).str.zfill(6)
        )
        realdatadf = loaded_df
        return True
    else:
        # start_async_save()
        if not get_day_is_trade_day(): 
            if date_entry.winfo_exists():
                try:
                    date_entry.set_date(date_str)
                except Exception as e:
                    logger.info(f"还不能设置:{e}")

        return False

def schedule_get_ths_code_task():
    """
    每隔5分钟执行一次的任务。
    """
    
    current_time = datetime.now().strftime("%H:%M:%S")
    logger.info(f"自动更新任务get_ths_code执行于: {current_time}")
    # 在这里添加你的具体任务逻辑

    save_thread = threading.Thread(target=get_ths_code)
    save_thread.start()
    # 5分钟后再次调用此函数
    # root.after(3 * 60 * 1000, schedule_checkpid_task)
    schedule_task('get_ths_code_task',5 * 60 * 1000,schedule_get_ths_code_task)

def schedule_checkpid_task():
    """
    每隔5分钟执行一次的任务。
    """
    
    current_time = datetime.now().strftime("%H:%M:%S")
    logger.info(f"自动更新任务checkpid_task执行于: {current_time}")
    # 在这里添加你的具体任务逻辑

    save_thread = threading.Thread(target=check_pids_all)
    save_thread.start()
    # 5分钟后再次调用此函数
    # root.after(3 * 60 * 1000, schedule_checkpid_task)
    schedule_task('checkpid_task',3 * 60 * 1000,lambda: schedule_checkpid_task)

# def daily_init_src():
#     global realdatadf, loaded_df, viewdf, date_write_is_processed, start_init, last_updated_time
#     realdatadf = pd.DataFrame()
#     loaded_df = None
#     viewdf = pd.DataFrame()
#     date_write_is_processed = False
#     start_init = 0
#     last_updated_time = None
#     if date_entry.winfo_exists():
#         try:
#             date_entry.set_date(get_today())
#         except Exception as e:
#             logger.info("还不能设置日期:", e)
#     logger.info("已执行每日开盘初始化")

#     global last_update_time, message_cache
#     # global refresh_registry
#     # # 保存每个 stock_code/item_id 的刷新状态
#     # refresh_registry = {}  # {(tree, window_info, item_id): {"after_id": None}}

#     # 控制更新节流
#     UPDATE_INTERVAL = 30  # 秒，更新UI最小间隔
#     last_update_time = 0
#     message_cache = []  # 缓存队列
#     #加入队列检测
#     process_queue(root)

#     # 自动注册下一天任务
#     schedule_daily_init(root)

# def daily_init():
#     """每日开盘初始化，重启所有监控窗口刷新"""
#     global realdatadf, loaded_df, viewdf
#     global date_write_is_processed, start_init, last_updated_time
#     global last_update_time, message_cache, refresh_registry, result_queue
#     global monitor_windows
#     global root
#     logger.info("🔄 [daily_init] 每日开盘初始化开始...")

#     # --- 1️⃣ 重置状态变量 ---
#     realdatadf = pd.DataFrame()
#     loaded_df = None
#     viewdf = pd.DataFrame()
#     date_write_is_processed = False
#     start_init = 0
#     last_updated_time = None

#     last_update_time = 0
#     message_cache = []
#     refresh_registry = {}
#     # refresh_registry.clear()
#     result_queue = queue.Queue()  # 清空旧队列

#     # --- 2️⃣ 恢复日期选择框 ---
#     if date_entry.winfo_exists():
#         try:
#             date_entry.set_date(get_today())
#         except Exception as e:
#             logger.info(f"[daily_init] 日期控件未就绪: {e}")

#     # --- 3️⃣ 启动主消息队列 ---
#     process_queue(root)

#     # --- 4️⃣ 重新启动所有监控窗口的刷新任务 ---
#     if monitor_windows:
#         for stock_code, window_info in monitor_windows.items():
#             win = window_info.get("toplevel")
#             tree = window_info.get("monitor_tree")
#             stock_info = window_info.get("stock_info")
#             logger.info(f'stock_info:{stock_info}')
#             if not win or not tree:
#                 logger.info(f'stock_info :{stock_info} not win not tree')
#                 continue
#             if not win.winfo_exists():
#                 logger.info(f'stock_info :{stock_info} not win.winfo_exists')
#                 continue
#             try:
#                 item_id = stock_info[0] if stock_info else stock_code
#                 refresh_stock_data(window_info, tree, item_id)
#                 logger.info(f"✅ [daily_init] 已重启监控任务: {stock_code}")
#             except Exception as e:
#                 logger.info(f"⚠️ [daily_init] 任务重启失败 {stock_code}: {e}")
#     else:
#         logger.info("⚠️ [daily_init] 没有检测到监控窗口，跳过刷新任务")

#     logger.info("✅ [daily_init] 每日初始化完成，监控刷新系统已恢复")

#     # --- 5️⃣ 安排下一次自动初始化 ---
#     schedule_daily_init(root)

# def daily_init(*args, **kwargs):
#     """每日开盘初始化，重启所有监控窗口刷新"""
#     global realdatadf, loaded_df, viewdf
#     global date_write_is_processed, start_init, last_updated_time
#     global last_update_time, message_cache, refresh_registry, result_queue
#     global monitor_windows
#     global root

#     logger.info(f"🔄 [daily_init] 每日初始化任务启动成功 (args接收={args if args else '无'})")

#     try:
#         # --- 1️⃣ 重置状态变量 ---
#         realdatadf = pd.DataFrame()
#         loaded_df = None
#         viewdf = pd.DataFrame()
#         date_write_is_processed = False
#         start_init = 0
#         last_updated_time = None
#         last_update_time = 0
#         message_cache = []
#         refresh_registry = {}
#         result_queue = queue.Queue()  # 清空旧队列

#         # --- 2️⃣ 恢复日期选择框 ---
#         try:
#             if date_entry.winfo_exists():
#                 date_entry.set_date(get_today())
#         except Exception as e:
#             logger.info(f"⚠️ [daily_init] 日期控件未就绪: {e}")

#         # --- 3️⃣ 启动主消息队列 ---
#         try:
#             process_queue(root)
#             logger.info("🟢 [daily_init] 已启动消息队列")
#         except Exception as e:
#             logger.info(f"❌ [daily_init] 启动消息队列失败: {e}")
#             import traceback
#             traceback.print_exc()

#         # --- 4️⃣ 重启所有监控窗口刷新任务 ---
#         if monitor_windows:
#             for stock_code, window_info in monitor_windows.items():
#                 try:
#                     win = window_info.get("toplevel")
#                     tree = window_info.get("monitor_tree")
#                     stock_info = window_info.get("stock_info")
#                     if not win or not tree or not win.winfo_exists():
#                         logger.info(f"⚠️ [daily_init] 跳过无效窗口: {stock_code}")
#                         continue
#                     item_id = stock_info[0] if stock_info else stock_code
#                     refresh_stock_data(window_info, tree, item_id)
#                     logger.info(f"✅ [daily_init] 已重启监控任务: {stock_code}")
#                 except Exception as e:
#                     logger.info(f"❌ [daily_init] 任务重启失败 {stock_code}: {e}")
#                     import traceback
#                     traceback.print_exc()
#         else:
#             logger.info("⚠️ [daily_init] 没有检测到监控窗口，跳过刷新任务")

#         logger.info("✅ [daily_init] 每日初始化完成，监控刷新系统已恢复")

#     except Exception as e:
#         logger.info(f"❌ [daily_init] 主流程异常: {e}")
#         import traceback
#         traceback.print_exc()

#     finally:
#         # --- 5️⃣ 安排下一次自动初始化 ---
#         try:
#             schedule_daily_init(root)
#             logger.info("🕒 [daily_init] 已安排下一次每日初始化任务")
#         except Exception as e:
#             logger.info(f"❌ [daily_init] 安排下一次任务失败: {e}")
#             import traceback
#             traceback.print_exc()


def run_daily_init_steps_two():
    # --- 3️⃣ 启动主消息队列 ---
    global message_cache, refresh_registry, result_queue
    global monitor_windows

    message_cache = []
    refresh_registry = {}
    result_queue = queue.Queue()
    process_queue(root)
    logger.info("✅ [daily_init] 核心初始化步骤run_daily_init_steps_two")


    # --- 4️⃣ 重启所有监控窗口 ---
    if monitor_windows:
        for stock_code, window_info in monitor_windows.items():
            try:
                win = window_info.get("toplevel")
                tree = window_info.get("monitor_tree")
                stock_info = window_info.get("stock_info")

                if not win or not tree or not win.winfo_exists():
                    logger.info(f"⚠️ [daily_init] 跳过无效窗口: {stock_code}")
                    continue

                item_id = stock_info[0] if stock_info else stock_code
                refresh_stock_data(window_info, tree, item_id)
                logger.info(f"✅ [daily_init] 已重启监控任务: {stock_code}")

            except Exception as e:
                logger.info(f"❌ [daily_init] 子窗口刷新失败 {stock_code}: {e}")
                import traceback
                traceback.print_exc()
    else:
        logger.info("⚠️ [daily_init] 无监控窗口，跳过刷新")
    logger.info("⚠️ [daily_init] monitor_windows 完成")


def run_daily_init_steps():
    """执行每日初始化的核心步骤（便于重试调用）"""
    global realdatadf, loaded_df, viewdf,today_tdx_df
    global date_write_is_processed, start_init, last_updated_time
    global last_update_time

    logger.info("🔄 [daily_init] 开始执行核心初始化步骤")

    # --- 1️⃣ 重置状态变量 ---
    realdatadf = pd.DataFrame()
    loaded_df = None
    viewdf = pd.DataFrame()
    date_write_is_processed = False
    start_init = 0
    last_updated_time = None
    last_update_time = 0
    today_tdx_df = pd.DataFrame()
    # --- 2️⃣ 恢复日期控件 ---
    try:
        if date_entry.winfo_exists():
            date_entry.set_date(get_today())
    except Exception as e:
        logger.info(f"⚠️ [daily_init] 日期控件未就绪: {e}")


    logger.info("✅ [daily_init] 核心初始化步骤执行完毕")
    root.after(13*60*1000,run_daily_init_steps_two)
    logger.info("✅ [daily_init] 核心初始化步骤5分钟后run_daily_init_steps_two")
    
def daily_init(*args, **kwargs):
    global root

    logger.info(f"🕒 [daily_init] 每日初始化任务启动 (args={args if args else '无'})")

    try:
        # 执行核心初始化步骤
        run_daily_init_steps()

    except Exception as e:
        logger.info(f"❌ [daily_init] 初始化异常: {e}")
        import traceback
        traceback.print_exc()

        # ⬇⬇⬇ 关键点：5 分钟后自动重试 daily_init ⬇⬇⬇
        logger.info("⏳ [daily_init] 5 分钟后将自动重试初始化...")
        root.after(5 * 60 * 1000, lambda: daily_init("retry"))

    finally:
        # 即使出错也要安排下一天的正常 schedule
        try:
            schedule_daily_init(root)
            logger.info("📅 [daily_init] 已安排下一次每日初始化")
        except Exception as e:
            # import traceback
            # traceback.print_exception(type(e), e, e.__traceback__)
            logger.exception("❌ [daily_init] 安排下一次初始化失败（堆栈如下）")
        # except Exception as e:
        #     logger.info(f"❌ [daily_init] 安排下一次初始化失败: {e}")
        #     import traceback
        #     traceback.print_exc()



# # 保存上次的任务ID
_scheduled_task_id = None

def schedule_daily_init(root):
    """
    每日定时初始化任务：
    - 若已有定时任务，取消旧的，仅保留最后一次注册。
    - 执行时间为每天 9:20（若当前时间已过，则安排到下一工作日）
    """
    global _scheduled_task_id

    now = datetime.now()
    today_925 = now.replace(hour=9, minute=20, second=0, microsecond=0)
    # today_925 = now.replace(hour=11, minute=28, second=0, microsecond=0)
    if now > today_925:
        today_925 = get_next_weekday_time(9, 20)

    delay_ms = int((today_925 - now).total_seconds() * 1000)

    # # --- 防重复：若存在旧任务，先取消 ---
    # if _scheduled_task_id is not None:
    #     try:
    #         root.after_cancel(_scheduled_task_id)
    #         logger.info("🧹 已取消旧的定时任务，准备注册新任务。")
    #     except Exception as e:
    #         logger.info("⚠️ 取消旧任务失败:", e)

    # --- 注册新任务 ---
    def scheduled_task():
        try:
            logger.info(f"🕒 [schedule_daily_init] 开始执行每日初始化任务: {datetime.now():%H:%M:%S}")
            start_worker(daily_init)
            # start_worker(lambda: daily_init())  # ✅ 显式调用，不传 root
        except Exception as e:
            logger.info(f"❌ [schedule_daily_init] 执行每日任务异常: {e}")
            import traceback
            traceback.print_exc()
        else:
            logger.info(f"✅ [schedule_daily_init] 任务执行完毕: {datetime.now():%H:%M:%S}")
        finally:
            logger.info("🔁 [schedule_daily_init] 准备注册下一次任务")
            schedule_daily_init(root)

    # _scheduled_task_id = schedule_task('daily_init',delay_ms,lambda: scheduled_task())
    _scheduled_task_id = schedule_task('daily_init', delay_ms, scheduled_task)

    logger.info(f"✅ 已注册每日开盘初始化任务: {today_925.strftime('%Y-%m-%d %H:%M')[5:]} (任务ID={_scheduled_task_id})")
    # _scheduled_process_queue_task_id = root.after(delay_ms, lambda: process_queue(root))
    delay_ms_queue = delay_ms+30000
    _scheduled_process_queue_task_id = schedule_task('process_queue',delay_ms_queue,lambda: process_queue(root))
    # logger.info(f"✅ 已注册每日开盘初始化任务: {today_925.strftime('%Y-%m-%d %H:%M')[5:]} (任务ID={_scheduled_process_queue_task_id})")
    logger.info(f"✅ 已注册每日queue_task初始化任务: {format_next_time(delay_ms_queue)} (任务ID={_scheduled_process_queue_task_id})")
    # --- 状态显示 ---
    try:
        status_label3.config(text=f"日初始化: {today_925.strftime('%Y-%m-%d %H:%M')[5:]}")
    except Exception:
        pass

def schedule_daily_init_debug(root, interval_minutes=5):
    """
    每 interval_minutes 分钟执行一次 daily_init，用于测试循环是否正常。
    - 执行 daily_init 后自动安排下一次执行。
    """
    global _scheduled_task_id

    delay_ms = interval_minutes * 60 * 1000  # 每 interval_minutes 分钟

    def scheduled_task():
        try:
            logger.info(f"🕒 [schedule_daily_init] 开始执行每日初始化任务: {datetime.now():%H:%M:%S}")
            start_worker(daily_init)
            # start_worker(lambda: daily_init())  # ✅ 显式调用，不传 root
        except Exception as e:
            logger.info(f"❌ [schedule_daily_init] 执行每日任务异常: {e}")
            import traceback
            traceback.print_exc()
        else:
            logger.info(f"✅ [schedule_daily_init] 任务执行完毕: {datetime.now():%H:%M:%S}")
        finally:
            logger.info("🔁 [schedule_daily_init] 准备注册下一次任务")
            schedule_daily_init(root)


    # ✅ 注册任务
    _scheduled_task_id = schedule_task('daily_init', delay_ms, scheduled_task)
    logger.info(f"✅ 已注册 {interval_minutes} 分钟循环任务: 下次执行 {format_next_time(delay_ms)} (任务ID={_scheduled_task_id})")

    # ✅ 注册延迟30秒的队列任务
    delay_ms_queue = delay_ms + 30000
    _scheduled_process_queue_task_id = schedule_task('process_queue', delay_ms_queue, lambda: process_queue(root))
    logger.info(f"✅ 已注册 queue_task 延迟任务: {format_next_time(delay_ms_queue)} (任务ID={_scheduled_process_queue_task_id})")

    # ✅ 更新UI状态
    try:
        status_label3.config(text=f"下次初始化: {format_next_time(delay_ms)}")
    except Exception:
        pass


# def schedule_daily_init(root):
#     """
#     每日定时初始化任务：
#     - 若已有同名任务，则自动覆盖
#     - 执行时间为每天 9:20（若当前时间已过，则安排到下一工作日）
#     """
#     global _scheduled_task_id

#     now = datetime.now()
#     today_925 = now.replace(hour=9, minute=20, second=0, microsecond=0)
#     if now > today_925:
#         today_925 = get_next_weekday_time(9, 20)

#     delay_ms = int((today_925 - now).total_seconds() * 1000)

#     def scheduled_task():
#         try:
#             logger.info(f"🕒 [schedule_daily_init] 开始执行每日初始化任务: {datetime.now():%H:%M:%S}")
#             start_worker(daily_init)
#         except Exception as e:
#             logger.info(f"❌ [schedule_daily_init] 执行每日任务异常: {e}")
#             import traceback
#             traceback.print_exc()
#         finally:
#             # 再次注册下一次
#             schedule_daily_init(root)

#     # ✅ 注册主任务
#     _scheduled_task_id = schedule_task('daily_init', delay_ms, scheduled_task)
#     logger.info(f"✅ 已注册每日开盘初始化任务: {today_925.strftime('%Y-%m-%d %H:%M')[5:]} (任务ID={_scheduled_task_id})")

#     # ✅ 注册延迟30秒的队列任务
#     delay_ms_queue = delay_ms + 30000
#     _scheduled_process_queue_task_id = schedule_task('process_queue', delay_ms_queue, lambda: process_queue(root))
#     logger.info(f"✅ 已注册每日queue_task初始化任务: {format_next_time(delay_ms_queue)} (任务ID={_scheduled_process_queue_task_id})")

#     # ✅ 更新UI状态
#     try:
#         status_label3.config(text=f"日初始化: {today_925.strftime('%m-%d %H:%M')}")
#     except Exception:
#         pass


# update_queue = queue.Queue()

# def background_worker():
#     while True:
#         df = get_stock_changes_background()
#         update_queue.put(df)
#         time.sleep(update_interval_minutes * 60)

# def process_updates():
#     try:
#         while True:
#             df = update_queue.get_nowait()
#             update_tree(df)
#     except queue.Empty:
#         pass
#     root.after(500, process_updates)



def schedule_worktime_task(tree,update_interval_minutes=update_interval_minutes):
    """
    每隔5分钟执行一次的任务。
    """
    global start_init,loaded_df,scheduled_task,last_updated_time
    next_execution_time = get_next_weekday_time(9, 25)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    # if get_day_is_trade_day() and 924 < get_now_time_int() < 930:
    #     loaded_df = None

    # 使用 root.after() 调度任务，在回调函数中使用 lambda 包装，
    # 确保在任务完成后再次调用自身进行重新调度。
    if loaded_df is None and (get_day_is_trade_day() or start_init == 0):
        if get_work_time() or 1130 < get_now_time_int() < 1300:
            current_time = datetime.now().strftime("%H:%M:%S")
            logger.info(f"bg更新任务get_stock_changes_background执行于: {current_time}")
            # 在这里添加你的具体任务逻辑
            status_label3.config(text=f"bg更新在{current_time[:-3]}执行")
            scheduled_task = actually_start_worker(get_stock_changes_background)
            # 5分钟后再次调用此函数
            schedule_task('worktime_task',5 * 60 * 1000,lambda: schedule_worktime_task(tree))
        else:
            # status_label3.config(text=f"更新在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
            status_label3.config(text=f"bg延迟在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
            schedule_task('worktime_task',delay_ms,lambda: schedule_worktime_task(tree))
    else:
        logger.info(f"下一次background任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")
        logger.info(f"自动更新任务get_stock_changes_background执行于:在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
        status_label3.config(text=f"日更新{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}")
        schedule_task('worktime_task',delay_ms,lambda: schedule_worktime_task(tree))


# def schedule_workday_task(root, target_hour, target_minute):
#     """
#     调度任务在下一个工作日的指定时间执行。
#     """
#     next_execution_time = get_next_weekday_time(target_hour, target_minute)
#     now = datetime.now()
#     delay_ms = int((next_execution_time - now).total_seconds() * 1000)
#     logger.info(f"下一次保存任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")

#     status_label2.config(text=f"存档-{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}")
#     schedule_task('worksaveday_task',delay_ms,lambda: [daily_task(), schedule_workday_task(root, target_hour, target_minute)])

def schedule_workday_task(root, target_hour, target_minute, immediate=False):
    """
    调度任务在下一个工作日的指定时间执行。
    """
    next_execution_time = get_next_weekday_time(target_hour, target_minute)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    if immediate:
        next_execution_time = now + timedelta(seconds=30)
        delay_ms = 30 * 1000

    logger.info(f"workday_task下一次保存任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")
    
    status_label2.config(text=f"存档-{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}")
    
    # 调度任务，执行 daily_task 后再次安排下一个工作日任务
    schedule_task(
        'worksaveday_task',
        delay_ms,
        lambda: [daily_task(), schedule_workday_task(root, target_hour, target_minute)]
    )




def rearrange_monitor_windows_grid():
    """一键自动网格排列所有监控窗口"""
    global monitor_windows

    if not monitor_windows:
        return

    # 获取屏幕大小
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # 起始位置
    start_x, start_y = 50, 50
    margin_x, margin_y = 5, 5  # 窗口间隔

    # 当前放置位置
    x, y = start_x, start_y
    max_col_width = 0  # 记录当前列的最大宽度

    for idx, (code, win_info) in enumerate(monitor_windows.items()):
        win = win_info.get("toplevel")
        if win and win.winfo_exists():
            try:
                # 获取窗口的实际宽高
                win.update_idletasks()
                w = win.winfo_width() or 300
                h = win.winfo_height() or 250

                # 判断是否超出屏幕高度，换列
                if y + h + margin_y > screen_height:
                    x += max_col_width + margin_x  # 向右移动
                    y = start_y                   # 回到顶端
                    max_col_width = 0             # 重置列宽

                # 移动窗口
                win.geometry(f"+{x}+{y}")

                # 更新位置
                y += h + margin_y
                max_col_width = max(max_col_width, w)

            except Exception as e:
                logger.info(f"移动窗口失败 {code}: {e}")


        # margin_x = 30
        # margin_y = 5

        # if align == "left":
        #     current_x = l + 50
        # elif align == "right":
        #     current_x = r - 50
        # else:
        #     raise ValueError("align 参数必须是 'left' 或 'right'")

        # current_y = t + 50
        # max_col_width = 0
        # max_row_height = 0
# 1️⃣ 左上角横向优先排列（normal）
def layout_from_left_top(windows, l, t, r, b, margin_x=10, margin_y=5):
    """
    左上角开始，横向优先，满宽换行
    """
    current_x = l + margin_x
    current_y = t + margin_y
    max_row_height = 0

    for win_info in windows:
        win = win_info["toplevel"]
        if not win.winfo_exists():
            continue

        w = win.winfo_width()
        h = win.winfo_height()

        # 换行
        if current_x + w + margin_x > r:
            current_x = l + margin_x
            current_y += max_row_height + margin_y
            max_row_height = 0

        win.geometry(f"{w}x{h}+{current_x}+{current_y}")
        win.configure(bg="SystemButtonFace")

        current_x += w + margin_x
        max_row_height = max(max_row_height, h)
# 2️⃣ 右下角横向优先排列（alter）
def layout_from_right_bottom(windows, l, t, r, b, margin_x=10, margin_y=5):
    """
    右下角开始，横向优先（向左），满宽换行（向上）
    """
    current_x = r - margin_x
    current_y = b - margin_y
    max_row_height = 0

    for win_info in windows:
        win = win_info["toplevel"]
        if not win.winfo_exists():
            continue

        w = win.winfo_width()
        h = win.winfo_height()

        # 换行（向上）
        if current_x - w - margin_x < l:
            current_x = r - margin_x
            current_y -= max_row_height + margin_y
            max_row_height = 0

        win.geometry(f"{w}x{h}+{current_x - w}+{current_y - h}")
        win.configure(bg="red")

        if not hasattr(win, "_alter_tdx"):
            win._alter_tdx = True

        current_x -= w + margin_x
        max_row_height = max(max_row_height, h)

def get_work_area():
    SPI_GETWORKAREA = 0x0030
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
    )
    return rect.left, rect.top, rect.right, rect.bottom

def _get_monitor_rect(m):
    """
    返回物理屏幕区域 (l, t, r, b)
    兼容:
      - (l, t, r, b)
      - {"monitor": (...), "work": (...)}
    """
    if isinstance(m, dict):
        return m.get("monitor", m.get("work"))
    return m


def _get_work_rect(m):
    """
    返回可用工作区 (l, t, r, b)
    若无 work，则退化为物理屏幕
    """
    if isinstance(m, dict):
        return m.get("work", m.get("monitor"))
    return m

def get_bottom_taskbar_height():
    """返回底部任务栏高度，如果任务栏在底部，否则返回0"""
    SPI_GETWORKAREA = 48
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    screen_height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
    taskbar_height = screen_height - rect.bottom
    taskbar_height = taskbar_height*2 if taskbar_height < 50 else taskbar_height
    logger.info(f"⚠ taskbar_height: {taskbar_height} screen_height:{screen_height} rect.bottom:{rect.bottom}")
    return max(taskbar_height, 0)

def rearrange_monitors_per_screen(align="left", sort_by="create_time", layout="horizontal"):
    """
    多屏幕窗口重排（自动换行 + 屏幕内排序）

    - 无 _alter_tdx：左上角排列（使用工作区）
    - 有 _alter_tdx：右下角反向排列（使用工作区，避开任务栏）
    """

    if not MONITORS:
        init_monitors()

    # 取监控窗口
    windows = [
        info for info in monitor_windows.values()
        if "toplevel" in info
    ]

    # 分组
    group_alter = []
    group_normal = []
    for info in windows:
        win = info["toplevel"]
        if hasattr(win, "_alter_tdx"):
            group_alter.append(info)
        else:
            group_normal.append(info)

    # 排序
    if sort_by == "create_time":
        key_func = lambda w: w["stock_info"][-1]
    else:
        key_func = lambda w: w.get("title", "")

    group_normal.sort(key=key_func, reverse=True)
    group_alter.sort(key=key_func, reverse=True)

    # 按物理屏幕分组
    screen_groups = {i: [] for i in range(len(MONITORS))}

    for win_info in group_normal + group_alter:
        win = win_info["toplevel"]
        try:
            win.update_idletasks()
            x, y = win.winfo_x(), win.winfo_y()

            for idx, m in enumerate(MONITORS):
                l, t, r, b = _get_monitor_rect(m)
                if l <= x < r and t <= y < b:
                    screen_groups[idx].append(win_info)
                    break

        except Exception as e:
            logger.info(f"⚠ 获取窗口位置失败: {e}")

    # 遍历每个屏幕
    for idx, group in screen_groups.items():
        if not group:
            continue

        # ✅ 关键修复：统一通过 helper 取工作区
        work_l, work_t, work_r, work_b = _get_work_rect(MONITORS[idx])

        margin_x, margin_y = 10, 5

        normal_group = [
            w for w in group
            if not hasattr(w["toplevel"], "_alter_tdx")
        ]
        alter_group = [
            w for w in group
            if hasattr(w["toplevel"], "_alter_tdx")
        ]

        # ======================
        # 左上角排列（normal）
        # ======================
        current_x = work_l + margin_x
        current_y = work_t + margin_y
        max_row_height = 0

        for win_info in normal_group:
            win = win_info["toplevel"]
            try:
                win.update_idletasks()
                w, h = win.winfo_width(), win.winfo_height()

                if layout == "horizontal" and current_x + w + margin_x > work_r:
                    current_x = work_l + margin_x
                    current_y += max_row_height + margin_y
                    max_row_height = 0

                win.geometry(f"{w}x{h}+{current_x}+{current_y}")
                win.configure(bg="SystemButtonFace")

                current_x += w + margin_x
                max_row_height = max(max_row_height, h)

            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")

        # 右下角排列（alter_group）
        taskbar_height_bottom = get_bottom_taskbar_height()
        current_x = work_r - margin_x
        current_y = work_b - margin_y - taskbar_height_bottom  # 自动上移避开底部任务栏
        max_row_height = 0

        for win_info in alter_group:
            win = win_info["toplevel"]
            try:
                win.update_idletasks()
                w, h = win.winfo_width(), win.winfo_height()

                # 横向优先，向左排列
                if current_x - w - margin_x < work_l:
                    current_x = work_r - margin_x
                    current_y -= max_row_height + margin_y
                    max_row_height = 0

                # 防止越过顶部
                if current_y - h < work_t:
                    break

                win.geometry(f"{w}x{h}+{current_x - w}+{current_y - h}")
                win.configure(bg="red")
                win._alter_tdx = True

                current_x -= w + margin_x
                max_row_height = max(max_row_height, h)

            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")


def rearrange_monitors_per_screen_no_bar(align="left", sort_by="create_time", layout="horizontal"):
    """
    多屏幕窗口重排（自动换列/换行 + 左右对齐 + 屏幕内排序）
    
    有 _alter_tdx 的窗口从右下角开始反向排列，背景红色
    无 _alter_tdx 的窗口从左上角开始排列，背景默认
    """
    if not MONITORS:
        init_monitors()

    # 取监控窗口列表
    windows = [info for info in monitor_windows.values() if "toplevel" in info]

    # 分组：有 _alter_tdx / 无 _alter_tdx
    group_alter = []
    group_normal = []
    for info in windows:
        win = info["toplevel"]
        if hasattr(win, "_alter_tdx"):
            group_alter.append(info)
        else:
            group_normal.append(info)

    # 排序
    key_func = lambda w: w["stock_info"][-1] if sort_by == "create_time" else w.get("title", "")
    group_alter.sort(key=key_func, reverse=True)
    group_normal.sort(key=key_func, reverse=True)

    # 屏幕分组
    screen_groups = {i: [] for i in range(len(MONITORS))}
    for win_info in group_normal + group_alter:  # 先正常窗口再 alter
        win = win_info["toplevel"]
        try:
            x, y = win.winfo_x(), win.winfo_y()
            for idx, (l, t, r, b) in enumerate(MONITORS):
                if l <= x < r and t <= y < b:
                    screen_groups[idx].append(win_info)
                    break
        except Exception as e:
            logger.info(f"⚠ 获取窗口位置失败: {e}")

    # 遍历屏幕
    for idx, group in screen_groups.items():
        if not group:
            continue

        l, t, r, b = MONITORS[idx]
        screen_width = r - l
        screen_height = b - t
        margin_x, margin_y = 10, 5

        # 分开有 _alter_tdx 和无 _alter_tdx
        normal_group = [w for w in group if not hasattr(w["toplevel"], "_alter_tdx")]
        alter_group = [w for w in group if hasattr(w["toplevel"], "_alter_tdx")]

        # 左上角排列 normal_group
        current_x = l + margin_x
        current_y = t + margin_y
        max_row_height = 0
        for win_info in normal_group:
            win = win_info["toplevel"]
            try:
                w, h = win.winfo_width(), win.winfo_height()
                # 换行逻辑
                if layout == "horizontal" and current_x + w + margin_x > r:
                    current_x = l + margin_x
                    current_y += max_row_height + margin_y
                    max_row_height = 0
                win.geometry(f"{w}x{h}+{current_x}+{current_y}")
                win.configure(bg="SystemButtonFace")  # 默认背景
                current_x += w + margin_x
                max_row_height = max(max_row_height, h)
            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")

        
        # 右下角排列 alter_group 横向优先
        current_x = r - margin_x
        current_y = b - margin_y
        max_row_height = 0

        for win_info in alter_group:
            win = win_info["toplevel"]
            try:
                w, h = win.winfo_width(), win.winfo_height()

                # 横向优先排列：右向左
                if current_x - w - margin_x < l:
                    # 换行向上
                    current_x = r - margin_x
                    current_y -= max_row_height + margin_y
                    max_row_height = 0

                win.geometry(f"{w}x{h}+{current_x - w}+{current_y - h}")
                win.configure(bg="red")  # alter 窗口背景红色
                if not hasattr(win, "_alter_tdx"):
                    win._alter_tdx = True

                # 更新位置
                current_x -= w + margin_x
                max_row_height = max(max_row_height, h)

            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")

def rearrange_monitors_per_screen_noaltertdx(align="left", sort_by="create_time", layout="horizontal"):
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
    windows = [info for info in monitor_windows.values() if "toplevel" in info]


    # ----------- 新增支持 createtime 排序 ----------
    if sort_by == "create_time":
        windows.sort(key=lambda w: w["stock_info"][-1], reverse=True)
    elif sort_by == "title":
        windows.sort(key=lambda w: w.get("title", ""))
    else:
        # 默认按 id 排序
        windows.sort(key=lambda w: w.get("id", 0))

    # 按屏幕分组
    screen_groups = {i: [] for i in range(len(MONITORS))}
    for win_info in windows:
        win = win_info["toplevel"]
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
            win = win_info["toplevel"]
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


def rearrange_monitors_per_screen_vertical(align="left", sort_by="id"):
    """
    多屏幕窗口重排（自动换列 + 左右对齐 + 屏幕内排序）
    
    align: "left" 或 "right" 控制对齐方向
    sort_by: "id" 或 "title" 窗口排序依据
    """
    if not MONITORS:
        init_monitors()

    #转换stock_info to dict for info.get("id", 0)
    def stock_info_to_dict(stock_info):
        stock_code, stock_name, *rest = stock_info
        return {
            "id": stock_code,
            "name": stock_name,
            "data": rest
        }

    # 取监控窗口列表
    windows = [info for info in monitor_windows.values() if "toplevel" in info]

    # 按屏幕分组
    screen_groups = {i: [] for i in range(len(MONITORS))}
    for win_info in windows:
        win = win_info["toplevel"]
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
            # group.sort(key=lambda info: info.get("id", 0))
            group.sort(key=lambda info:  info['stock_info'][0]) 
        elif sort_by == "title":
            # group.sort(key=lambda info: info.get("title", ""))
            group.sort(key=lambda info:  info['stock_info'][1]) 
        else:
            pass  # 保持原顺序

        l, t, r, b = MONITORS[idx]
        screen_height = b - t

        margin_y = 5
        col_margin_x = 30  # 列间隔

        if align == "left":
            current_x = l + 50
        elif align == "right":
            current_x = r - 50
        else:
            raise ValueError("align 参数必须是 'left' 或 'right'")

        current_y = t + 50
        max_col_width = 0

        for win_info in group:
            win = win_info["toplevel"]
            try:
                w = win.winfo_width()
                h = win.winfo_height()

                if align == "right" and max_col_width == 0:
                    current_x -= w

                # 超出屏幕高度 -> 换列
                if current_y + h + margin_y > b:
                    if align == "left":
                        current_x += max_col_width + col_margin_x
                    else:
                        current_x -= max_col_width + col_margin_x
                    current_y = t + 50
                    max_col_width = 0
                    if align == "right":
                        current_x -= w

                win.geometry(f"{w}x{h}+{current_x}+{current_y}")
                current_y += h + margin_y
                max_col_width = max(max_col_width, w)

            except Exception as e:
                logger.info(f"⚠ 窗口排列失败: {e}")


#  窗口重排,出现一列一直排问题
# def rearrange_monitors_per_screen():
#     """基于窗口所在屏幕，重新垂直排列 monitor_windows 里的所有窗口"""
#     if not MONITORS:
#         init_monitors()

#     # 取监控窗口列表
#     windows = [info["toplevel"] for info in monitor_windows.values() if "toplevel" in info]

#     # 按屏幕分组
#     screen_groups = {i: [] for i in range(len(MONITORS))}
#     for win in windows:
#         try:
#             x, y = win.winfo_x(), win.winfo_y()
#             for idx, (l, t, r, b) in enumerate(MONITORS):
#                 if l <= x < r and t <= y < b:
#                     screen_groups[idx].append(win)
#                     break
#         except Exception as e:
#             logger.info(f"⚠ 获取窗口位置失败: {e}")

#     # 每个屏幕内重新排列
#     for idx, group in screen_groups.items():
#         if not group:
#             continue
#         l, t, r, b = MONITORS[idx]
#         current_x = l + 50  # 左上角偏移 50
#         current_y = t + 50  # 左上角偏移 50
#         margin_x = 5
#         for win in group:
#             try:
#                 w = win.winfo_width()
#                 h = win.winfo_height()
#                 win.geometry(f"{w}x{h}+{current_x}+{current_y}")
#                 current_y += h + margin_x  # 窗口间隔
#             except Exception as e:
#                 logger.info(f"⚠ 窗口排列失败: {e}")

MAX_KEEP = 15  # 每个前缀只保留最近 15 个文件

def archive_file(src_file, prefix):
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

# def archive_file(src_file, prefix):
#     """
#     通用备份函数
#     src_file: 需要备份的文件路径，如 "alerts.json"
#     prefix  : 文件名前缀，如 "alerts", "monitor_list"
#     """

#     if not os.path.exists(src_file):
#         logger.info(f"⚠ {src_file} 不存在，跳过存档")
#         return

#     try:
#         with open(src_file, "r", encoding="utf-8") as f:
#             content = f.read().strip()
#     except Exception as e:
#         logger.info(f"⚠ 无法读取 {src_file}: {e}")
#         return

#     if not content or content in ("[]", "{}", ""):
#         logger.info(f"⚠ {src_file} 内容为空，跳过存档")
#         return

#     # 确保存档目录存在
#     os.makedirs(ARCHIVE_DIR, exist_ok=True)

#     # 找到同 prefix 的最近一个存档文件
#     files = sorted(
#         [f for f in os.listdir(ARCHIVE_DIR) if f.startswith(prefix + "_")],
#         reverse=True
#     )

#     if files:
#         last_file = os.path.join(ARCHIVE_DIR, files[0])
#         try:
#             with open(last_file, "r", encoding="utf-8") as f:
#                 last_content = f.read().strip()
#             # 完全一致 → 不备份
#             if content == last_content:
#                 logger.info(f"⚠ {src_file} 与上一次 {prefix} 存档相同，跳过存档")
#                 return
#         except Exception as e:
#             logger.info(f"⚠ 无法读取最近存档: {e}")

#     # --- 生成存档文件名 ---
#     today = datetime.now().strftime("%Y-%m-%d")
#     filename = f"{prefix}_{today}.json"
#     dest = os.path.join(ARCHIVE_DIR, filename)

#     # 如果同一天已有 → 加时间戳
#     if os.path.exists(dest):
#         timestamp = datetime.now().strftime("%H%M%S")
#         filename = f"{prefix}_{today}_{timestamp}.json"
#         dest = os.path.join(ARCHIVE_DIR, filename)

#     shutil.copy2(src_file, dest)
#     # logger.info(f"✅ 已归档：{dest}")
#     rel_path = os.path.relpath(dest)
#     logger.info(f"✅ 已归档：{rel_path}")



def archive_alerts_single():
    """归档 alerts.json，避免空内容或重复备份"""

    if not os.path.exists(ALERTS_FILE):
        logger.info("⚠ alerts.json 不存在，跳过归档")
        return

    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取 alerts.json: {e}")
        return

    # 内容为空或无效
    if not content or content in ("[]", "{}", ""):
        logger.info("⚠ alerts.json 内容为空，跳过归档")
        return

    # 确保目录存在
    os.makedirs(ALERTS_ARCHIVE_DIR, exist_ok=True)

    # 最近一个存档是否相同
    files = sorted(os.listdir(ALERTS_ARCHIVE_DIR), reverse=True)
    if files:
        last_file = os.path.join(ALERTS_ARCHIVE_DIR, files[0])
        try:
            with open(last_file, "r", encoding="utf-8") as f:
                last_content = f.read().strip()
            if content == last_content:
                logger.info("⚠ 内容和上次存档一致，跳过归档")
                return
        except Exception as e:
            logger.info(f"⚠ 无法读取最近存档: {e}")

    # 生成存档文件名
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"alerts_{today}.json"
    dest = os.path.join(ALERTS_ARCHIVE_DIR, filename)

    # 当天已存在 → 加时间戳
    if os.path.exists(dest):
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"alerts_{today}_{timestamp}.json"
        dest = os.path.join(ALERTS_ARCHIVE_DIR, filename)

    # 执行复制
    shutil.copy2(ALERTS_FILE, dest)
    logger.info(f"✅ 已归档 alerts.json 到: {dest}")


def archive_monitor_list_single():
    """归档监控文件，避免空或重复存档"""

    if not os.path.exists(MONITOR_LIST_FILE):
        logger.info("⚠ monitor_list.json 不存在，跳过归档")
        return

    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.info(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        logger.info("⚠ monitor_list.json 内容为空，跳过归档")
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
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"monitor_list_{today}.json"
    dest = os.path.join(ARCHIVE_DIR, filename)

    # 如果当天已有存档，加时间戳避免覆盖
    if os.path.exists(dest):
        filename = f"monitor_list_{today}.json"
        dest = os.path.join(ARCHIVE_DIR, filename)

    # 复制文件
    shutil.copy2(MONITOR_LIST_FILE, dest)
    logger.info(f"✅ 已归档监控文件: {dest}")


def archive_monitor_list():
    logger.info(f'monitor_list.json archive')
    archive_file("monitor_list.json", "monitor_list")
    logger.info(f'alerts.json archive')
    archive_file("alerts.json", "alerts")
    # archive_file("rules.json", "rules")


def list_archives():
    """列出所有存档文件"""
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith("monitor_list_") and f.endswith(".json")],
        reverse=True
    )
    return files


def load_archive(selected_file,readfile=False):
    """加载选中的存档文件并刷新监控"""
    archive_file = os.path.join(ARCHIVE_DIR, selected_file)
    if not os.path.exists(archive_file):
        messagebox.showerror("错误", "存档文件不存在")
        return
    if readfile:
        initial_monitor_list = load_monitor_list(MONITOR_LIST_FILE=archive_file)
        logger.info('readfile:{archive_file}')
        return initial_monitor_list
    # 关闭所有已有监控窗口
    for code, info in list(monitor_windows.items()):
        try:
            if "toplevel" in info and info["toplevel"].winfo_exists():
                info["toplevel"].destroy()
        except Exception as e:
            logger.info(f"关闭窗口 {code} 失败: {e}")
    monitor_windows.clear()

    # 覆盖当前的监控文件
    shutil.copy2(archive_file, MONITOR_LIST_FILE)
    # messagebox.showinfo("成功", f"已加载存档: {selected_file}")
    toast_message(None,f"成功已加载存档: {selected_file}")

    # 重新加载监控数据
    initial_monitor_list = load_monitor_list()
    if initial_monitor_list:
        for stock_info in initial_monitor_list:
            if isinstance(stock_info, list) and stock_info:
                stock_code = stock_info[0]
                if stock_code not in monitor_windows:
                    monitor_win = create_monitor_window(stock_info)
                    monitor_windows[stock_code] = monitor_win

                    # load_window_position(monitor_win)
            elif isinstance(stock_info, str):
                stock_code = stock_info
                # 重新构造 stock_info，以便 create_monitor_window 使用
                # 注意：这里需要你自行获取完整信息或根据需要调整逻辑
                if stock_code not in monitor_windows:
                    monitor_win = create_monitor_window([stock_code, "未知", "未知", 0, 0])
                    monitor_windows[stock_code] = monitor_win



def open_archive_loader_old():
    """打开存档选择窗口"""
    win = tk.Toplevel(root)
    win.title("加载历史监控数据")
    win.geometry("400x300")
    window_id = "历史监控数据"   # <<< 每个窗口一个唯一 ID
    update_position_window(win, window_id)

    files = list_archives()
    if not files:
        tk.Label(win, text="没有历史存档文件").pack(pady=20)
        return

    # 下拉框选择
    selected_file = tk.StringVar(value=files[0])
    combo = ttk.Combobox(win, textvariable=selected_file, values=files, state="readonly")
    combo.pack(pady=10)

    # 加载按钮
    ttk.Button(win, text="加载", command=lambda: load_archive(selected_file.get())).pack(pady=5)
    ttk.Button(win, text="显示", command=lambda: open_archive_view_window(selected_file.get())).pack(pady=5)
    # 按 Esc 关闭窗口

    win.bind("<Escape>", lambda event: win.destroy())
    win.after(60*1000,  lambda  event:win.destroy())


def open_archive_loader():
    """打开存档选择窗口"""
    win = tk.Toplevel(root)
    win.title("加载历史监控数据")
    win.geometry("400x300")
    window_id = "历史监控数据"   # <<< 每个窗口一个唯一 ID
    update_position_window(win, window_id)

    files = list_archives()
    if not files:
        tk.Label(win, text="没有历史存档文件").pack(pady=20)
        return

    selected_file = tk.StringVar(value=files[0])
    combo = ttk.Combobox(win, textvariable=selected_file, values=files, state="readonly")
    combo.pack(pady=10)

    # 加载按钮
    ttk.Button(win, text="加载", command=lambda: load_archive(selected_file.get())).pack(pady=5)
    ttk.Button(win, text="显示", command=lambda: open_archive_view_window(selected_file.get())).pack(pady=5)
    def on_close(event=None):
        """
        统一关闭函数，ESC 和右上角 × 都能使用
        """
        # 在这里可以加任何关闭前的逻辑，比如保存数据或确认
        # if messagebox.askokcancel("关闭窗口", "确认要关闭吗？"):
        update_window_position(window_id)
        win.destroy()

    win.bind("<Escape>", on_close)
    win.protocol("WM_DELETE_WINDOW", lambda: on_close())
    win.after(60*1000, lambda: win.destroy())   # 自动关闭


def open_archive_view_window(filename):
    """
    从 filename 读取存档数据并显示。
    仅显示：code, name, v3, v4, v5, time
    """

    try:
        data_list = load_archive(filename,readfile=True)
    except Exception as e:
        messagebox.showerror("读取失败", f"读取 {filename} 时发生错误:\n{e}")
        return

    if not data_list:
        messagebox.showwarning("无数据", f"{filename} 中没有可显示的数据。")
        return

    win = tk.Toplevel(root)
    win.title(f"存档预览 — {filename}")
    win.geometry("400x350")
    window_id = "存档预览"   # <<< 每个窗口一个唯一 ID
    update_position_window(win, window_id)
    # update_window_position(window_id)  #保存位置在close

    # 只保留需要的列
    columns = ["code", "name", "percent", "price", "volume", "time"]
    col_names = {
        "code": "代码",
        "name": "名称",
        "percent": "percent",
        "price": "price",
        "volume": "volume",
        "time": "时间"
    }

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

    # 设置列标题
    # for col in columns:
    #     tree.heading(col, text=col_names[col], command=lambda c=col: sort_column_archive_view(tree, c, False))
    #     tree.column(col, width=60, anchor="center")
    for c in columns:
        if c in ( "time", "name"):
            width = 60 if c in ("条件", "规则名") else 60
            # tree.heading(c, text=c)
            tree.heading(c, text=c, anchor="center", 
                             command=lambda _c=c: sort_column_archive_view(tree, _c, False))
            tree.column(c, width=width, anchor="w" if c in ("条件", "规则名") else "center")
        else:
            # width = 220 if c in ("条件", "规则名") else 800
            # tree.heading(c, text=c)
            tree.heading(c, text=c, anchor="center", 
                             command=lambda _c=c: sort_column_archive_view(tree, _c, False))
            # tree.column(c, width=width, anchor="w" if c in ("条件", "规则名") else "center")
            tree.column(c, width=50 if c == "code" else 30, anchor="w" if c == "条件" else "center")

    # 插入数据
    for row in data_list:
        # 映射到新的列顺序
        # row 格式：code, name, v1, v2, v3, v4, v5, time
        new_row = [row[0], row[1], row[4], row[5], row[6], row[7]]
        tree.insert("", "end", values=new_row)

    # ===========================================================
    # 整合功能事件区域
    # ===========================================================

    def on_tree_select(event):
        """处理 Treeview 的选择事件"""
        tree_widget = event.widget
        selected_item = tree_widget.selection()
        if not selected_item:
            return

        stock_info = tree_widget.item(selected_item, 'values')
        if not stock_info:
            return

        stock_code = str(stock_info[0]).zfill(6)
        send_to_tdx(stock_code)

        logger.info(f"选中股票代码: {stock_code}")
        time.sleep(0.1)

    def on_single_click(event):
        """单击选中行立即发送到 TDX"""
        tree_widget = event.widget
        row_id = tree_widget.identify_row(event.y)
        if not row_id:
            return

        vals = tree_widget.item(row_id, "values")
        if not vals:
            return

        code = str(vals[0]).zfill(6)
        send_to_tdx(code)

    # 绑定事件
    # tree.bind("<Button-3>", show_menu)             # 右键菜单
    # tree.bind("<Double-1>", on_double_click_edit)  # 双击编辑
    tree.bind("<<TreeviewSelect>>", on_tree_select) # 选择事件
    tree.bind("<Button-1>", on_single_click)        # 单击事件
    win.lift()
    def on_close(event=None):
        """
        统一关闭函数，ESC 和右上角 × 都能使用
        """
        # 在这里可以加任何关闭前的逻辑，比如保存数据或确认
        # if messagebox.askokcancel("关闭窗口", "确认要关闭吗？"):
        update_window_position(window_id)
        win.destroy()

    win.bind("<Escape>", on_close)
    win.protocol("WM_DELETE_WINDOW", lambda: on_close())
    # --- 🔥 默认按时间倒序排序（最新在上） ---
    win.after(10, lambda: sort_column_archive_view(tree, "time", True))  # True = 倒序

def sort_column_archive_view(tree, col, reverse):
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
    tree.heading(col, command=lambda: sort_column_archive_view(tree, col, not reverse))


# # --- 数据持久化函数 ---
# def save_monitor_list():
#     """保存当前的监控股票列表到文件"""
#     monitor_list = [win['stock_info'] for win in monitor_windows.values()]
#     mo_list = []
#     if len(monitor_list) > 0:
#         for m in monitor_list:
#             stock_code = m[0]
#             if stock_code:
#                 stock_code = stock_code.zfill(6)

#             if  not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
#                 logger.info(f"错误请输入有效的6位股票代码:{m}")
#                 continue
#             mo_list.append(m)

#     else:
#         logger.info('no window find')

    # # 写入文件
    # with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
    #     json.dump(mo_list, f, ensure_ascii=False, indent=2)
#     logger.info(f"监控列表已保存到 {MONITOR_LIST_FILE}")

#     archive_monitor_list()

# def load_monitor_list():
#     """从文件加载监控股票列表"""
#     if os.path.exists(MONITOR_LIST_FILE):
#         with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
#             try:
#                 loaded_list = json.load(f)
#                 # 确保加载的数据是列表，并且包含列表/元组
#                 if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
#                     return [list(item) for item in loaded_list]
#                 return []
#             except (json.JSONDecodeError, TypeError):
#                 return []
#     return []

# --- 数据持久化函数 ---
# def save_monitor_list():
#     """保存当前的监控股票列表到文件"""
#     monitor_list = [win['stock_info'] for win in monitor_windows.values()]
#     mo_list = []
#     if len(monitor_list) > 0:
#         for m in monitor_list:
#             stock_code = m[0]
#             if stock_code:
#                 stock_code = stock_code.zfill(6)

#             # 检查合法股票代码
#             if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
#                 logger.info(f"错误请输入有效的6位股票代码: {m}")
#                 continue
#             import ipdb;ipdb.set_trace()

#             # ✅ 确保结构升级：带 create_time
#             if len(m) < 8:
#                 create_time = datetime.now().strftime("%Y-%m-%d %H")
#                 m.append(create_time)
#             mo_list.append(m)
#     else:
#         logger.info('no window find')

#     # 写入文件
#     with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
#         json.dump(mo_list, f, ensure_ascii=False, indent=2)
#     logger.info(f"监控列表已保存到 {MONITOR_LIST_FILE}")

#     archive_monitor_list()

def save_monitor_list():
    """保存当前的监控股票列表到文件"""
    monitor_list = [win['stock_info'] for win in monitor_windows.values()]
    mo_list = []

    if monitor_list:
        for m in monitor_list:
            stock_code = m[0]
            if stock_code:
                stock_code = stock_code.zfill(6)

            # 检查合法股票代码
            if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
                logger.info(f"错误请输入有效的6位股票代码: {m}")
                continue

            # ❗ 关键：使用拷贝，不修改原始 m
            new_m = m.copy()

            # 补齐 create_time 字段
            if len(new_m) < 8:
                create_time = datetime.now().strftime("%Y-%m-%d %H")
                new_m.append(create_time)

            mo_list.append(new_m)
    else:
        logger.info('no window find')

    # 写入文件
    # with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
    #     json.dump(mo_list, f, ensure_ascii=False, indent=None)

    with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
        f.write('[\n' + ',\n'.join('  ' + json.dumps(item, ensure_ascii=False) for item in mo_list) + '\n]\n')


    logger.info(f"监控列表已保存到 {MONITOR_LIST_FILE}")

    archive_monitor_list()


# def load_monitor_list():
#     """
#     从文件加载监控股票列表（自动升级旧结构）。
#     确保返回值总是 List[List]，且每条记录至少包含8个字段（含 create_time）。
#     """
#     if not os.path.exists(MONITOR_LIST_FILE):
#         return []

#     # 读取原始文件
#     try:
#         with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
#             loaded_raw = json.load(f)
#     except (json.JSONDecodeError, TypeError, OSError) as e:
#         logger.info(f"⚠️ 读取监控列表失败: {e}")
#         return []

#     if not isinstance(loaded_raw, list):
#         logger.info("⚠️ 文件内容不是列表，已忽略。")
#         return []

#     upgraded = []
#     changed = False
#     now_str = datetime.now().strftime("%Y-%m-%d %H")

#     for idx, item in enumerate(loaded_raw):
#         # 只接受 list/tuple
#         if not isinstance(item, (list, tuple)):
#             logger.info(f"⚠️ 跳过无效记录 index={idx}: {item!r}")
#             continue

#         row = list(item)

#         # 若缺失 create_time，则补充
#         if len(row) < 8:
#             row.append(now_str)
#             changed = True
#             logger.info(f"升级监控记录: code={row[0] if row else 'UNKNOWN'} -> 添加 create_time={now_str}")

#         upgraded.append(row)

#     # ✅ 如果有变更，写回文件
#     if changed:
#         try:
#             with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
#                 json.dump(upgraded, f, ensure_ascii=False, indent=2)
#             logger.info(f"已自动升级并回写文件: {MONITOR_LIST_FILE}")
#         except OSError as e:
#             logger.info(f"⚠️ 写入文件失败: {e}")

#     # ✅ 如果没有任何升级发生，就返回规范化后的 loaded_raw
#     # （保证外部调用返回的是 list[list]）
#     return upgraded if changed else [list(item) for item in loaded_raw if isinstance(item, (list, tuple))]

def load_monitor_list(MONITOR_LIST_FILE=MONITOR_LIST_FILE):
    """
    从文件加载监控股票列表，并自动修复结构。
    规则：
    - 每条记录必须是长度≥7。
    - 第 8 个字段（索引 7）固定为 create_time。
    - 若存在多余的时间字段（索引>7），自动删除。
    - 若缺失 create_time，自动补齐。
    """
    if not os.path.exists(MONITOR_LIST_FILE):
        return []

    # 读取文件
    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            loaded_raw = json.load(f)
    except Exception as e:
        logger.info(f"⚠️ 读取监控列表失败: {e}")
        return []

    if not isinstance(loaded_raw, list):
        logger.info("⚠️ 文件内容不是列表，忽略。")
        return []

    upgraded = []
    changed = False
    now_str = datetime.now().strftime("%Y-%m-%d %H")

    for idx, item in enumerate(loaded_raw):
        if not isinstance(item, (list, tuple)):
            logger.info(f"⚠️ 跳过无效记录 index={idx}: {item!r}")
            continue

        row = list(item)
        original_len = len(row)

        # ----------------------------
        # ① 若长度 < 7，本身就是损坏数据，跳过（代码、名称等都不完整）
        # ----------------------------
        if original_len < 7:
            logger.info(f"⚠️ 跳过损坏记录 index={idx}: {row}")
            continue

        # ----------------------------
        # ② 处理 create_time 字段
        # ----------------------------
        if original_len == 7:
            # 缺少 create_time → 补上
            row.append(now_str)
            changed = True
            logger.info(f"升级记录 index={idx}: 添加 create_time={now_str}")

        elif original_len > 8:
            # 多余字段，只保留前 8 个
            extra = row[8:]
            row = row[:8]
            changed = True
            logger.info(f"修剪记录 index={idx}: 移除多余字段 {extra}")

        else:
            # 恰好 8 项，正常
            pass

        upgraded.append(row)

    # ----------------------------
    # ③ 若有修改 → 写回文件
    # ----------------------------
    if changed:
        try:
            with open(MONITOR_LIST_FILE, "w", encoding="utf-8") as f:
                json.dump(upgraded, f, ensure_ascii=False, indent=2)
            logger.info(f"✔ 已自动修复并写回文件: {MONITOR_LIST_FILE}")
        except Exception as e:
            logger.info(f"⚠️ 写入文件失败: {e}")

    # 返回规范化结果
    return upgraded



def get_stock_changes_background(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes,initwork=False):
    """
    获取股票异动数据，根据时间间隔判断是否从API获取。
    Args:
        selected_type (str): 板块类型。
        stock_code (str): 股票代码。
        update_interval_minutes (int): 更新周期（分钟）。
    """
    global realdatadf, last_updated_time
    global loaded_df,start_init
    global date_write_is_processed
    global viewdf,stop_event,date_entry
    current_time = datetime.now()
    start_time=time.time()
    need_update = (
        loaded_df is None
        or realdatadf.empty
        or get_work_time()
        or (not date_write_is_processed and get_now_time_int() > 1505)
    )


    # if loaded_df is None  and (realdatadf.empty or get_work_time() or (not date_write_is_processed and get_now_time_int() > 1505)):
    if need_update:
        with realdatadf_lock:
            # 检查是否需要从API获取数据
            if last_updated_time is None or current_time - last_updated_time >= timedelta(minutes=update_interval_minutes):
                # logger.info(last_updated_time is None , last_updated_time is None or current_time - last_updated_time , timedelta(minutes=update_interval_minutes))
                logger.info(f"时间间隔已到，正在从API获取新数据...")
                last_updated_time = current_time
                # 模拟从 Eastmoney API 获取数据
                time.sleep(0.2)
                for symbol in symbol_map.keys():
                    # 构造模拟数据
                    # 假设每次调用都返回一些新的和一些旧的数据
                    if not initwork and stop_event.is_set():
                        logger.info(f'backgroundworker线程停止运行')
                        last_updated_time = None
                        realdatadf = pd.DataFrame()
                        break
                    old_data = realdatadf.copy()
                    temp_df = get_stock_changes(selected_type=symbol)
                    if len(temp_df) < 10:
                        continue
                    realdatadf = pd.concat([realdatadf, temp_df], ignore_index=True)
                    
                    # 去除重复数据，保留最新的数据
                    realdatadf.drop_duplicates(subset=['时间','代码', '板块'], keep='last', inplace=True)
                    logger.info(f"为 ({symbol}) 获取了新的异动数据，并更新了 realdatadf, start_init:{start_init}")
                    if start_init == 0:
                        toast_message(None,f"为 ({symbol}) 获取了新的异动数据，并更新了 realdatadf")
                    time.sleep(5)
                logger.info(f"time:{int(time.time() - start_time)}全部更新 获取了新的异动数据，并更新了realdatadf:{len(realdatadf)}")
                if start_init == 0:
                    toast_message(None,f"time:{time.time() - start_time}全部更新 获取了新的异动数据，并更新了realdatadf:{len(realdatadf)}")
                logger.info(f"realdatadf 已更新:{time.strftime('%H:%M:%S')} {len(realdatadf)}")
            else:
                logger.info(f"{current_time - last_updated_time}:未到更新时间，返回内存realdatadf数据。")
    if start_init == 0:
        time.sleep(6)
        refresh_cout = 0
        start_init = 1
    return realdatadf

def get_stock_changes_time(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes):
    """
    获取股票异动数据，根据时间间隔判断是否从API获取。
    """
    global realdatadf, last_updated_time
    global loaded_df
    global date_write_is_processed
    
    current_time = datetime.now()
    start_time=time.time()
    if loaded_df is None  and (len(realdatadf) == 0 or get_work_time() or (not date_write_is_processed and get_now_time_int() > 1505)):
        if len(realdatadf) > 0 and (selected_type is not None or selected_type != ''):
            temp_df = filter_stocks(realdatadf,selected_type)
            if stock_code:
                stock_code = stock_code.zfill(6)
                temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]

        elif selected_type is not None and selected_type != '' or stock_code is not None or  realdatadf.empty:
            temp_df = get_stock_changes(selected_type=selected_type)

        else:
            if not realdatadf.empty:
                temp_df = realdatadf
            else:
                temp_df = get_stock_changes()

        if not get_work_time() and (get_now_time_int() >1530  or get_now_time_int() < 923):
            temp_df = get_stock_changes(selected_type=selected_type)
    else:
        temp_df = get_stock_changes(selected_type=selected_type, stock_code=stock_code)

    return temp_df

# def get_stock_changes_time(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes):
#     global realdatadf, loaded_df, last_updated_time, date_write_is_processed

#     now_int = get_now_time_int()

#     # ---------- 第一阶段：交易前、初始化时，必须强制获取 ----------
#     if not get_work_time():  # 非交易时间
#         return get_stock_changes(selected_type=selected_type, stock_code=stock_code)

#     # ---------- 第二阶段：交易进行中 ----------
#     # loaded_df 未初始化 → 必须强制获取
#     if loaded_df is None:
#         return get_stock_changes(selected_type=selected_type, stock_code=stock_code)

#     # ---------- 第三阶段：普通更新逻辑 ----------
#     if stock_code:
#         stock_code = stock_code.zfill(6)

#     return get_stock_changes(selected_type=selected_type, stock_code=stock_code)


# def _get_tdx_data_df(stock_code=None):
#     global sina_data_last_updated_time,sina_data_df
#     global pytables_status,today_tdx_df
#     basedir = "G:" + os.sep
#     ptype='low'
#     resample='d'
#     dl = 70
#     filter='y'
#     fname = os.path.join(basedir, "tdx_last_df.h5")             # 原始 HDF5
#     table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'
#     # table = "all"
#     current_time = datetime.now()
#     # tdx_df = None
#     if pytables_status and today_tdx_df.isEmpty() :
#         today_tdx_df = read_hdf_table(fname,table)
#         sina_data_df = sina_data_df + today_tdx_df.loc('high4')
#     return today_tdx_df
# --- Win32 API 用于获取 EXE 原始路径 (仅限 Windows) ---


# def _get_win32_exe_path():
#     """
#     使用 Win32 API 获取当前进程的主模块路径。
#     这在 Nuitka/PyInstaller 的 Onefile 模式下能可靠地返回原始 EXE 路径。
#     """
#     # 假设是 32767 字符的路径长度是足够的
#     MAX_PATH_LENGTH = 32767 
#     buffer = ctypes.create_unicode_buffer(MAX_PATH_LENGTH)
    
#     # 调用 GetModuleFileNameW(HMODULE hModule, LPWSTR lpFilename, DWORD nSize)
#     # 传递 NULL 作为 hModule 获取当前进程的可执行文件路径
#     ctypes.windll.kernel32.GetModuleFileNameW(
#         None, buffer, MAX_PATH_LENGTH
#     )
#     return os.path.dirname(os.path.abspath(buffer.value))


# def get_base_path(log=logger):
#     """
#     获取程序基准路径。在 Windows 打包环境 (Nuitka/PyInstaller) 中，
#     使用 Win32 API 优先获取真实的 EXE 目录。
#     """
    
#     # 检查是否为 Python 解释器运行
#     is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
#     # 1. 普通 Python 脚本模式
#     if is_interpreter and not getattr(sys, "frozen", False):
#         # 只有当它是 python.exe 运行 且 没有 frozen 标志时，才进入脚本模式
#         try:
#             # 此时 __file__ 是可靠的
#             path = os.path.dirname(os.path.abspath(__file__))
#             log.info(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
#             return path
#         except NameError:
#              pass # 忽略交互模式
    
#     # 2. Windows 打包模式 (Nuitka/PyInstaller EXE 模式)
#     # 只要不是解释器运行，或者 sys.frozen 被设置，我们就认为是打包模式
#     if sys.platform.startswith('win'):
#         try:
#             # 无论是否 Onefile，Win32 API 都会返回真实 EXE 路径
#             real_path = _get_win32_exe_path()
            
#             # 核心：确保我们返回的是 EXE 的真实目录
#             if real_path != os.path.dirname(os.path.abspath(sys.executable)):
#                  # 这是一个强烈信号：sys.executable 被欺骗了 (例如 Nuitka Onefile 启动器)，
#                  # 或者程序被从其他地方调用，我们信任 Win32 API。
#                  log.info(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
#                  return real_path
            
#             # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
#             if not is_interpreter:
#                  log.info(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
#                  return real_path

#         except Exception:
#             pass 

#     # 3. 最终回退（适用于所有打包模式，包括 Linux/macOS）
#     if getattr(sys, "frozen", False) or not is_interpreter:
#         path = os.path.dirname(os.path.abspath(sys.executable))
#         log.info(f"[DEBUG] Path Mode: Final Fallback. Path: {path}")
#         return path

#     # 4. 极端脚本回退
#     log.info(f"[DEBUG] Path Mode: Final Script Fallback.")
#     return os.path.dirname(os.path.abspath(sys.argv[0]))


# logger.info(f'_get_win32_exe_path() : {_get_win32_exe_path()}')
#print(f'_get_win32_exe_path() : {_get_win32_exe_path()}')
#print(f'get_base_path() : {get_base_path()}')

def get_resource_file(rel_path, out_name=None,BASE_DIR=None,spec=None,log=logger):
    """
    从 PyInstaller 内置资源释放文件到 EXE 同目录

    rel_path:   打包资源的相对路径
    out_name:   释放目标文件名
    """


    if BASE_DIR is None:
        BASE_DIR = get_base_path()
        # log.info(f"BASE_DIR配置文件: {BASE_DIR}")

    if out_name is None:
        out_name = os.path.basename(rel_path)

    # BASE_DIR = os.path.dirname(
    #     sys.executable if getattr(sys, "frozen", False)
    #     else os.path.abspath(__file__)    # ✅ 修复点
    # )
    target_path = os.path.join(BASE_DIR, out_name)
    log.info(f"target_path配置文件: {target_path}")

    # 已存在 → 直接返回
    if os.path.exists(target_path):
        return target_path

    # 从 MEIPASS 复制
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.abspath(".")
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

def get_conf_path(fname,rel_path=None,log=logger):
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
        rel_path=f"{fname}"
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
        self.duration_sleep_time = self.get_with_writeback("general", "duration_sleep_time", fallback=60, value_type="int")
        self.compute_lastdays = self.get_with_writeback("general", "compute_lastdays", fallback=5, value_type="int")
        self.win10_ramdisk  = self.get_with_writeback("general", "win10_ramdisk", fallback='G:', value_type="str")
        self.filterclose  = self.get_with_writeback("general", "filterclose", fallback='close', value_type="str")
        self.filterhigh4  = self.get_with_writeback("general", "filterhigh4", fallback='high4', value_type="str")

        saved_wh_str = self.get_with_writeback("general", "saved_width_height", fallback="260x180")
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
    def get_with_writeback(self, section, option, fallback, value_type="str"):
        """
        读取配置，如果不存在则写入 fallback 到 ini
        value_type: "str", "int", "float", "bool"
        """
        if not self.cfg.has_option(section, option):
            # 写回默认值
            if value_type == "bool":
                val_str = "True" if fallback else "False"
            else:
                val_str = str(fallback)
            if not self.cfg.has_section(section):
                self.cfg.add_section(section)
            self.cfg.set(section, option, val_str)
            self.save()
            return fallback
        else:
            # 已存在，按类型返回
            if value_type == "int":
                return self.cfg.getint(section, option)
            elif value_type == "float":
                return self.cfg.getfloat(section, option)
            elif value_type == "bool":
                return self.cfg.getboolean(section, option)
            else:
                return self.cfg.get(section, option)
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
        logger.info(f"使用内置save: {section} {key} {value} ok")
    # ========================================================

    def __repr__(self):
        return f"<GlobalConfig {self.cfg_file}>"


conf_ini= get_conf_path('globalYD.ini')
if not conf_ini:
    logger.critical("globalYD.ini 加载失败，程序无法继续运行")

CFG = GlobalConfig(conf_ini)

initGlobalValue = CFG.init_value
clean_terminal = CFG.clean_terminal
win10_ramdisk = CFG.win10_ramdisk
filterclose = CFG.filterclose
filterhigh4 = CFG.filterhigh4

# root_path = [
#     CFG.get_path("root_path_windows"),
#     CFG.get_path("root_path_mac"),
# ]

def _get_tdx_data_df(stock_code=None):
    global sina_data_last_updated_time, sina_data_df
    global pytables_status, today_tdx_df

    basedir = win10_ramdisk + os.sep
    ptype = 'low'
    resample = 'd'
    dl = 70
    filter = 'y'

    fname = os.path.join(basedir, "tdx_last_df.h5")
    table = f"{ptype}_{resample}_{dl}_{filter}_all"

    # ① 读取 TDX 数据（只读一次）
    if pytables_status and (today_tdx_df is None or today_tdx_df.empty):
        today_tdx_df = read_hdf_table(fname, table)
    
    if today_tdx_df is None or today_tdx_df.empty:
        return today_tdx_df

    # # ② 只取 high4 列
    # if 'high4' not in today_tdx_df.columns:
    #     return today_tdx_df

    # high4_df = today_tdx_df[['high4']]

    # # ③ 合并到 sina_data_df
    # if sina_data_df is not None and not sina_data_df.empty:
    #     sina_data_df = sina_data_df.join(high4_df, how='left')
    # else:
    #     sina_data_df = high4_df.copy()

    # # ④ 可选：只返回指定股票
    # if stock_code:
    #     stock_code = stock_code.zfill(6)
    #     if stock_code in today_tdx_df.index:
    #         return today_tdx_df.loc[[stock_code]]

    return today_tdx_df


def _get_sina_data_realtime(stock_code=None):
    global sina_data_last_updated_time,sina_data_df
    global pytables_status
    basedir = win10_ramdisk + os.sep
    fname = os.path.join(basedir, "sina_data.h5")    
    logger.debug(f'win10_ramdisk fname:{fname}')
    table = "all"
    current_time = datetime.now()
    df = None
    if pytables_status:
        if sina_data_last_updated_time is None or current_time - sina_data_last_updated_time >= timedelta(minutes=3):
            sina_data_last_updated_time = datetime.now()
            logger.info(f'sina_data_last_updated_time:{sina_data_last_updated_time}  current_time: {current_time} sina_data_last_updated_time: {sina_data_last_updated_time}')
            sina_data = read_hdf_table(fname,table)
            if sina_data is not None and not sina_data.empty:
                sina_data_df = sina_data.copy()
                if stock_code is not None:
                    df = sina_data.loc[stock_code]
                else:
                    df = sina_data
        else:
            if sina_data_df is not None and not sina_data_df.empty:
                if stock_code is not None:
                    if stock_code in sina_data_df.index:
                        df = sina_data_df.loc[stock_code]
                    else:
                        logger.info(f'stock_code: {stock_code} not in sina_data')
                        df = None
                else:
                    df = sina_data_df

    return df

# def _get_stock_changes(selected_type=None, stock_code=None):
#     """获取股票异动数据"""
#     global realdatadf,loaded_df
#     global last_updated_time
#     current_time = datetime.now()

#     if loaded_df is None:
#         temp_df = get_stock_changes_time(selected_type=selected_type)
#     else:
#         temp_df = loaded_df.copy()

#     temp_df = filter_stocks(temp_df,selected_type)
    
#     if stock_code:
#         stock_code = stock_code.zfill(6)
#         temp_df = temp_df[temp_df['代码'].astype(str).str.zfill(6) == str(stock_code)]
#     return temp_df
 
def _get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据（带安全检查）"""
    global realdatadf, loaded_df
    global last_updated_time

    # === 1) 数据源 ===
    if loaded_df is None:
        temp_df = get_stock_changes_time(selected_type=selected_type)
    else:
        temp_df = loaded_df.copy()

    # === 2) 空/None 直接返回空 DF ===
    if temp_df is None:
        logger.warning("_get_stock_changes: 数据为 None，返回空 DataFrame")
        return pd.DataFrame()

    if not isinstance(temp_df, pd.DataFrame):
        logger.error(f"_get_stock_changes: 数据类型异常 {type(temp_df)}，返回空 DF")
        return pd.DataFrame()

    if temp_df.empty:
        logger.info("_get_stock_changes: 数据为空，返回空 DataFrame")
        return temp_df

    # === 3) 必须包含 '代码' 字段 ===
    if '代码' not in temp_df.columns:
        logger.error("_get_stock_changes: 缺少字段 '代码'，返回空 DataFrame")
        return pd.DataFrame()

    # === 4) 执行过滤 ===
    temp_df = filter_stocks(temp_df, selected_type)

    if temp_df.empty:
        return temp_df

    # === 5) 按代码过滤 ===
    if stock_code:
        stock_code = str(stock_code).zfill(6)

        temp_df = temp_df[
            temp_df['代码']
            .astype(str)
            .str.zfill(6)
            == stock_code
        ]

    return temp_df
       
    

def fast_insert(tree, dataframe):
    if dataframe is not None and not dataframe.empty:
        # 批量插入
        if 'count' in dataframe.columns and dataframe[dataframe['count'] > 0].empty:
            logger.info(f'fast_insert:count retry process_full_dataframe:{dataframe[:1]}')
            dataframe = process_full_dataframe(dataframe) 

        dataframe = dataframe[['时间', '代码', '名称','count', '板块', '涨幅', '价格', '量']]
        for row in dataframe.itertuples(index=False, name=None):
            values = list(row)
            tree.tk.call(tree, "insert", "", "end", "-values", values)

        if dataframe is not None:
            status_var.set(f"已加载 {len(dataframe)} 条记录 | 更新于: {time.strftime('%H:%M:%S')}")
        else:
            status_var.set("无数据")
            tree.insert("", "end", values=("无数据", "", "", "", ""))
        # 强制刷新一次
        tree.update_idletasks()



def refresh_stock_data(window_info, tree, item_id,debug=False):
    """提交后台任务"""
    stock_code = window_info['stock_info'][0]
    def task():
        try:
            data = _get_stock_changes(None, stock_code)  # 你的数据获取函数
            if debug:
                logger.info(f"refresh_stock_data data : {data}")
            result_queue.put(("data", data, tree, window_info, item_id))
        except Exception as e:
            result_queue.put(("error", e, tree, window_info, item_id))
    threading.Thread(target=task, daemon=True).start()

# def handle_error(payload, tree, window_info, item_id):
#     """处理后台线程或消息队列中的错误"""
#     import traceback
#     logger.info(f"⚠️ 异步任务出错:{payload}")
#     traceback.print_exc()

# def handle_error(payload, tree, window_info, item_id):
#     """处理后台线程或消息队列中的错误"""

#     logger.info(f"⚠️ 异步任务出错: {payload}")

#     # ---- 1) payload 是真正的异常 ----
#     if isinstance(payload, BaseException):
#         logger.error("异常类型: %s", type(payload).__name__)
#         traceback.print_exception(type(payload), payload, payload.__traceback__)
#         return

#     # ---- 2) payload 不是异常，打印详细结构 ----
#     logger.error("⚠️ payload 不是异常对象，类型: %s", type(payload))
#     logger.error("⚠️ payload 内容: %r", payload)

#     # ---- 3) 如果是 dict，检查是否有 'error' 等字段 ----
#     if isinstance(payload, dict):
#         for key in ("error", "exception", "msg", "message"):
#             if key in payload:
#                 logger.error("⚠️ payload 内含错误信息字段 %s: %r", key, payload[key])

def handle_error(payload, tree, window_info, item_id):
    """处理后台线程或消息队列中的错误（更强壮版本）"""

    logger.info(f"⚠️ 异步任务出错: {payload!r}")

    # ===== ① payload 是真正的异常对象 =====
    if isinstance(payload, BaseException):
        logger.error("异常类型: %s", type(payload).__name__)
        traceback.print_exception(type(payload), payload, payload.__traceback__)
        return

    # ===== ② payload 不是异常对象 =====
    logger.error("⚠️ payload 不是异常对象，类型: %s", type(payload))
    logger.error("⚠️ payload 内容: %r", payload)

    # ===== ③ payload 是 dict → 尝试提取内部错误 =====
    if isinstance(payload, dict):
        error_fields = ["error", "exception", "exc", "msg", "message", "detail"]
        for key in error_fields:
            if key in payload:
                logger.error("⚠️ payload[%s] = %r", key, payload[key])

                # 如果内部字段本身是异常 → 打印 traceback
                inner = payload[key]
                if isinstance(inner, BaseException):
                    logger.error("⚠️ payload[%s] 是异常对象 → 打印详细 traceback", key)
                    traceback.print_exception(type(inner), inner, inner.__traceback__)
                return




def process_queue(window):
    global last_update_time, message_cache
    global refresh_registry
    # 1. 收集队列中所有消息
    while True:
        try:
            msg = result_queue.get_nowait()
            message_cache.append(msg)
        except queue.Empty:
            break

    now = time.time()
    # 2. 如果达到更新间隔，批量处理缓存
    if message_cache and (now - last_update_time >= UPDATE_INTERVAL):
        for msg_type, payload, tree, window_info, item_id in message_cache:
            if msg_type == "data":
                update_monitor_tree(payload, tree, window_info, item_id)
            elif msg_type == "error":
                handle_error(payload, tree, window_info, item_id)

        message_cache.clear()
        last_update_time = now

    # 3. 定时再次轮询
    # logger.info(f'process_queue:0.5S')
    window.after(500, lambda: process_queue(window))  # 0.5秒轮询一次队列


def parse_datetime(dt_str):
    """
    自动识别带日期或仅时分秒的字符串
    """
    try:
        # 尝试完整日期时间
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # 尝试仅时分秒，返回今天日期拼接
            today = datetime.today().strftime("%Y-%m-%d")
            return datetime.strptime(f"{today} {dt_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError(f"无法解析时间: {dt_str}")

def format_time(dt_str):
    """
    解析日期时间或仅时间字符串，统一返回 H:M:S 格式
    """

    dt_str = str(dt_str)
    try:
        # 尝试完整日期时间
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # 尝试仅时分秒
        dt = datetime.strptime(dt_str, "%H:%M:%S")
    return dt.strftime("%H:%M:%S")


def insert_placeholder(tree, text="loading"):
    tree.delete(*tree.get_children())
    tree.insert("", "end", values=(text, "", "", "", ""))


# ---------------------------
# 主线程 UI 更新函数
# ---------------------------
def update_monitor_tree(data, tree, window_info, item_id):
    """更新子窗口的 Treeview"""
    global start_init,refresh_registry

    stock_info = window_info['stock_info']
    stock_code, stock_name, *rest = stock_info
    window = window_info['toplevel']


    def update_latest_row(new_row):
        children = tree.get_children()
        # 删除占位符行
        # 将 new_row 全部转成字符串，确保与 Treeview 的 values 类型一致
        new_row_str = tuple(str(x) for x in new_row)
        for item in children:
            vals = tree.item(item, "values")
            if vals and vals[0] in ("加载ing...", "loading"):  # 可根据占位符调整
                tree.delete(item)
        # 插入到最上面一行
        # Tree 有值，检查第一行是否相同
        first = tree.get_children()
        if first:
            first_values = tree.item(first[0], "values")
            if tuple(first_values) == new_row_str:
                return  # 重复则不插入
        tree.insert("", 0, values=new_row)

    def schedule_next(delay_ms, key, tree, window_info, item_id):
        now = time.time()
        reg = refresh_registry.setdefault(key, {"after_id": None, "execute_at": 0})

        # 如果已有任务且还没到期，直接返回
        if reg["execute_at"] > now:
            return

        execute_at = now + delay_ms / 1000
        reg["execute_at"] = execute_at

        # 取消旧任务
        if reg["after_id"]:
            try:
                tree.after_cancel(reg["after_id"])
            except Exception:
                pass

        # 安排下一次刷新
        def task():
            try:
                refresh_stock_data(window_info, tree, item_id)
            finally:
                reg["after_id"] = None
                reg["execute_at"] = 0

        reg["after_id"] = tree.after(delay_ms, task)


    if not window or not window.winfo_exists():
        return  # 窗口已关闭

    key = (id(tree), id(window_info), item_id)
     # 如果已经有刷新任务在调度中，就不再创建新的
    if key not in refresh_registry:
        refresh_registry[key] = {"after_id": None , "execute_at": 0 }
        schedule_next(1000,key, tree, window_info, item_id)

    now = datetime.now()
    next_execution_time = get_next_weekday_time(9, 25)
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)
    dd  = _get_sina_data_realtime(stock_code)
    price,percent,amount = 0,0,0
    if dd is not None:
        price = dd.close
        percent = round((dd.close - dd.llastp) / dd.llastp *100,1)
        amount = round(dd.turnover/100/10000/100,1)
        # logger.info(f'line 2910 sina_data:{stock_code}, {price},{percent},{amount}')


    if data is not None and not data.empty:
        # 只保留当前股票

        data = data[data['代码'] == stock_code].set_index('时间').reset_index()
        if '涨幅' not in data.columns:
            data = process_full_dataframe(data)
        if not get_work_time():
            if dd is not None:
                logger.info(f'line 2921 sina_data:{stock_code}, {price},{percent},{amount}')
                check_alert(stock_code, price,percent,amount)
            else:
                _data = data[data['量'] > 0 ]
                if _data is not None and not _data.empty:   
                    check_alert(stock_code, _data[:1]['价格'].values[0], _data[:1]['涨幅'].values[0], _data[:1]['量'].values[0])
        else:
            if dd is not None:
                # logger.info(f'line 2929 sina_data:{stock_code}, {price},{percent},{amount}')
                check_alert(stock_code, price,percent,amount)
            else:
                check_alert(stock_code, data[:1]['价格'].values[0], data[:1]['涨幅'].values[0], data[:1]['量'].values[0])
        
        data = data[['时间', '板块', '涨幅', '价格', '量']]
        tree.delete(*tree.get_children())
        for _, row in data.iterrows():
            tree.insert("", "end", values=list(row))

        if dd is not None:
            # stime = str(dd.ticktime)
            # dt = datetime.strptime(stime, "%Y-%m-%d %H:%M:%S")
            # time_str = dt.strftime("%H:%M:%S")
            time_str = format_time(dd.ticktime)
            row = [time_str,"新浪" , percent ,price,amount]
            update_latest_row(row)
        # 随机间隔再次刷新
        # wait_time = int(random.uniform(30000, 60000))
        # window.after(wait_time, lambda: refresh_stock_data(window_info, tree, item_id))

    else:
        # pass
        # 如果没有数据，清空并短间隔重试
        # tree.delete(*tree.get_children())
        # # 添加占位行，保证双击逻辑可以找到 item
        # tree.insert(
        #     "", "end",
        #     values=("加载中...", "", "", "", "")
        # )
        insert_placeholder(tree)

    
    if get_work_time() or (get_day_is_trade_day() and 1130 < get_now_time_int() < 1300):
        # logger.info(f'start flush_alerts')
        if  not 1130 < get_now_time_int() < 1300:
            delay_ms = 30000
            schedule_next(delay_ms,key, tree, window_info, item_id)
            logger.debug(f'update_monitor_tree 交易时段刷新 {stock_code} {stock_name} :{format_next_time(delay_ms)}')
            status_label2.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
            # status_var.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
        else:
            delay_ms =  int(minutes_to_time(1300)) * 60 * 1000
            # logger.info(f'update_monitor_tree next_update:{next_time} Min')
            schedule_next(delay_ms,key, tree, window_info, item_id)
            logger.info(f'update_monitor_tree 非交易刷新 {stock_code} {stock_name} :{format_next_time(delay_ms)}')
            status_label2.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
            # status_var.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
    else:
        logger.info(f'update_monitor_tree 次日刷新 {stock_code} {stock_name} :{format_next_time(delay_ms)}')
        schedule_next(delay_ms,key, tree, window_info, item_id)
        status_label2.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
        # status_var.config(text=f"monitor刷新 {format_next_time(delay_ms)}")
            # window.after(delay_ms, lambda: refresh_stock_data(window_info, tree, item_id))

# --- 主窗口逻辑 ---  (lag)
def add_selected_stock():
    """添加选中的股票到监控窗口"""
    try:
        selected_item = tree.selection()
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[1]
            stock_name = stock_info[2]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)

            logger.info(f"选中监控股票代码: {stock_code}")
        else:
            messagebox.showwarning("警告", "请选择一个股票代码。")
            return


        if stock_code in monitor_windows.keys():
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        monitor_win = create_monitor_window(stock_info)
        monitor_windows[stock_code] = monitor_win

    except IndexError:
        messagebox.showwarning("警告", "请选择一个股票代码。")

def add_code_to_file_tree():
    try:
        selected_item = tree.selection()
        if not selected_item:
            toast_message(root, "未选中任何股票")
            return

        stock_info = tree.item(selected_item, "values")
        if not stock_info:
            toast_message(root, "无法获取选中行数据")
            return

        # 假设 tree 列顺序：[时间, 代码, 名称, ...]
        stock_code = str(stock_info[1]).strip().zfill(6)
        stock_name = str(stock_info[2]).strip()

        added = add_code_to_file(stock_code)

        if added:
            toast_message(root, f"已添加: {stock_code} {stock_name}")
        else:
            toast_message(root, f"已存在: {stock_code} {stock_name}")

    except Exception as e:
        toast_message(root, f"添加失败: {e}")
        logger.exception("add_code_to_file_tree 失败")


# --- 主窗口逻辑 ---  (lag)
def add_selected_stock_popup_window():
    """添加选中的股票到监控窗口"""
    try:
        selected_item = tree.selection()
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[1]
            stock_name = stock_info[2]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)

            logger.info(f"选中监控股票代码: {stock_code}")
        else:
            messagebox.showwarning("警告", "请选择一个股票代码。")
            return


        if stock_code in monitor_windows.keys():
            messagebox.showwarning("警告", f"{stock_code} 的监控窗口已打开。")
            return

        monitor_win = create_popup_window(stock_info)

    except IndexError:
        messagebox.showwarning("警告", "请选择一个股票代码。")

# def show_context_menu(event):
#     """显示右键菜单"""
#     try:
#         item = tree.identify_row(event.y)
#         if item:
#             tree.selection_set(item)
#             context_menu.post(event.x_root, event.y_root)
#     except Exception:
#         pass

def show_context_menu(event):
    """显示右键菜单"""
    parent_win = event.widget.winfo_toplevel()
    try:
        item = tree.identify_row(event.y)
        if not item:
            return

        tree.selection_set(item)
        values = tree.item(item, "values")  # ✅ 修正这里
        if not values:
            return

        stock_code, stock_name = values[1], values[2]  # 代码、名称
        stock_info = values[1:]

        context_menu = tk.Menu(root, tearoff=0)
        context_menu.add_command(label="添加到监控", command=add_selected_stock)
        context_menu.add_command(label="打开报警中心", command=open_alert_center)
        context_menu.add_command(label="添加报警规则",
            command=lambda: open_alert_editor(stock_code,new=True, stock_info=stock_info,parent_win=parent_win,
                x_root=event.x_root,
                y_root=event.y_root))
        context_menu.add_command( label="编辑报警规则",
            command=lambda: open_alert_editor(stock_code,new=False, stock_info=stock_info,parent_win=parent_win,
                x_root=event.x_root,
                y_root=event.y_root))
        context_menu.add_command(label="添加异常Code", command=add_code_to_file_tree)


        context_menu.post(event.x_root, event.y_root)
    except Exception as e:
        logger.info(f"[右键菜单异常] {e}")

_last_time_on_monitor_double_click = 0
def on_monitor_double_click(event, stock_code,manual=False):
# def on_monitor_double_click(stock_code, tree=None, event=None):
    global _last_time_on_monitor_double_click

    # if tree is None:
    #     if event is not None:
    #         tree = event.widget
    #     else:
    #         raise ValueError("必须提供 tree 或 event")

    monitor_tree = event.widget
    if not isinstance(monitor_tree, ttk.Treeview):
        return
    now = time.time()
    if now - _last_time_on_monitor_double_click < 0.1:  # 50ms 防抖
        return
    _last_time_on_monitor_double_click = now
    # items = monitor_tree.get_children()
    needs_update = False
    for item in monitor_tree.get_children():
        vals = monitor_tree.item(item, "values")
        # vals 为 None 或空，或者第一列是 "加载ing..." / "loading"
        if not vals or len(vals) == 0 or vals[0] in ("加载ing...", "loading"):
            needs_update = True
            break

    logger.info(f'stock_code: {stock_code} needs_update :{needs_update} 加载ing')
    def fetch_and_insert(stock_code, monitor_tree):
        # 获取股票涨跌数据
        data = _get_stock_changes(stock_code=stock_code)
        # 删除占位符行
        def clean_placeholder():
            children = monitor_tree.get_children()
            for item in children:
                vals = monitor_tree.item(item, "values")
                if vals and vals[0] in ("加载ing...", "loading"):  # 可根据占位符调整
                    monitor_tree.delete(item)
        # 插入到最上面一行，保证列数一致
        # def update_latest_row_double_click(new_row):
        #     clean_placeholder()
        #     n_cols = len(monitor_tree["columns"])
        #     # 截断或补空，保证长度与列一致
        #     new_row = list(new_row)[:n_cols] + [""] * max(0, n_cols - len(new_row))
        #     monitor_tree.insert("", 0, values=new_row)
        def update_latest_row_double_click(new_row):
            clean_placeholder()
            # 将 new_row 全部转成字符串，确保与 Treeview 的 values 类型一致
            new_row_str = tuple(str(x) for x in new_row)
            # Tree 有值，检查第一行是否相同
            first = monitor_tree.get_children()
            if first:
                first_values = monitor_tree.item(first[0], "values")
                # logger.info(f'first_values: {tuple(first_values)}  new_row: {tuple(new_row)}')
                # logger.info(f'== {tuple(first_values) == new_row_str }')
                if tuple(first_values) == new_row_str:
                    return  # 重复则不插入

            n_cols = len(monitor_tree["columns"])
            new_row = list(new_row)[:n_cols] + [""] * max(0, n_cols - len(new_row))

            monitor_tree.insert("", 0, values=new_row)
        clean_placeholder()
        # 处理 DataFrame 并插入现有数据
        if data is not None and not data.empty:
            # 只保留当前股票
            data = data[data['代码'] == stock_code].set_index('时间').reset_index()
            if '涨幅' not in data.columns:
                data = process_full_dataframe(data)
            data = data[['时间', '板块', '涨幅', '价格', '量']]
            # 保留默认列顺序
            cols = ['时间', '板块', '涨幅', '价格', '量']
            for col in cols:
                if col not in data.columns:
                    data[col] = ""  # 缺失列补空

            data = data[cols]  # 按顺序
            n_cols = len(monitor_tree["columns"])
            for _, row in data.iterrows():
                values = list(row)[:n_cols] + [""] * max(0, n_cols - len(row))
                monitor_tree.insert("", "end", values=values)

        # 获取新浪实时数据
        dd = _get_sina_data_realtime(stock_code)
        if dd is not None:
            price = dd.close
            percent = round((dd.close - dd.llastp) / dd.llastp * 100, 1)
            amount = round(dd.turnover / 100 / 10000 / 100, 1)
            logger.info(f'double_click get sina_data: {stock_code}, {price}, {percent}, {amount}')
            check_alert(stock_code, price, percent, amount)
            time_str = format_time(dd.ticktime)
            alert_row = [time_str, "新浪", percent, price, amount]
            update_latest_row_double_click(alert_row)

    def fetch_and_insert_only(stock_code, monitor_tree):
        # 删除占位符行
        # def clean_placeholder():
        #     children = monitor_tree.get_children()
        #     for item in children:
        #         vals = monitor_tree.item(item, "values")
        #         if vals and vals[0] in ("加载ing...", "loading"):  # 可根据占位符调整
        #             monitor_tree.delete(item)
        def clean_last_placeholder():
            children = monitor_tree.get_children()
            if not children:
                return
            last_item = children[-1]
            vals = monitor_tree.item(last_item, "values")
            if vals and vals[0] in ("加载ing...", "loading"):
                monitor_tree.delete(last_item)

        def update_latest_row_double_click(new_row):
            clean_last_placeholder()
            # 将 new_row 全部转成字符串，确保与 Treeview 的 values 类型一致
            new_row_str = tuple(str(x) for x in new_row)
            # Tree 有值，检查第一行是否相同
            first = monitor_tree.get_children()
            if first:
                first_values = monitor_tree.item(first[0], "values")
                # logger.info(f'first_values: {tuple(first_values)}  new_row: {tuple(new_row)}')
                # logger.info(f'== {tuple(first_values) == new_row_str }')
                if tuple(first_values) == new_row_str:
                    return  # 重复则不插入

            n_cols = len(monitor_tree["columns"])
            new_row = list(new_row)[:n_cols] + [""] * max(0, n_cols - len(new_row))
            monitor_tree.insert("", 0, values=new_row)

        # clean_placeholder()
        clean_last_placeholder()
        # 获取新浪实时数据
        dd = _get_sina_data_realtime(stock_code)
        if dd is not None:
            price = dd.close
            percent = round((dd.close - dd.llastp) / dd.llastp * 100, 1)
            amount = round(dd.turnover / 100 / 10000 / 100, 1)
            logger.info(f'double_click get sina_data: {stock_code}, {price}, {percent}, {amount}')
            check_alert(stock_code, price, percent, amount)
            time_str = format_time(dd.ticktime)
            alert_row = [time_str, "新浪", percent, price, amount]
            update_latest_row_double_click(alert_row)

    if needs_update:
        threading.Thread(target=fetch_and_insert,args=(stock_code, monitor_tree), daemon=True).start()
    elif manual:
        threading.Thread(target=fetch_and_insert_only,args=(stock_code, monitor_tree), daemon=True).start()

    update_code_entry(stock_code)

        # 异步刷新
        # def fetch_and_insert():
        #     data = _get_stock_changes(stock_code=stock_code)

        #     def update_latest_row(new_row):
        #         children = monitor_tree.get_children()
        #         # 删除占位符行
        #         for item in children:
        #             vals = monitor_tree.item(item, "values")
        #             if vals and vals[0] in ("加载ing...", "loading"):  # 可根据占位符调整
        #                 monitor_tree.delete(item)
        #         # 插入到最上面一行
        #         monitor_tree.insert("", 0, values=new_row)

        #     if data is not None and not data.empty:
        #         # 只保留当前股票
        #         data = data[data['代码'] == stock_code].set_index('时间').reset_index()
        #         if '涨幅' not in data.columns:
        #             data = process_full_dataframe(data)
        #         data = data[['时间', '板块', '涨幅', '价格', '量']]
        #         monitor_tree.delete(*tree.get_children())
        #         for _, row in data.iterrows():
        #             monitor_tree.insert("", "end", values=list(row))
        #     dd  = _get_sina_data_realtime(stock_code)

        #     if dd is not None:
        #         price = dd.close
        #         percent = round((dd.close - dd.llastp) / dd.llastp *100,1)
        #         amount = round(dd.turnover/100/10000/100,1)
        #         logger.info(f'double_click get sina_data:{stock_code}, {price},{percent},{amount}')
        #         check_alert(stock_code, price,percent,amount)
        #         time_str = format_time(dd.ticktime)
        #         row = [time_str,"新浪" , percent ,price,amount]
        #         update_latest_row(row)
        # threading.Thread(target=fetch_and_insert, daemon=True).start()

    # update_code_entry(stock_code)



def update_code_entry(stock_code):
    """更新主窗口的 Entry"""
    global code_entry
    logger.info(f'update_code_entry:{stock_code}')
    if not stock_code  or not stock_code.isdigit():
        logger.info(f"code_entry错误请输入有效的6位股票代码:{stock_code}")
        return
    if stock_code:
        stock_code = stock_code.zfill(6)
        selected_item = tree.selection()
        send_to_tdx(stock_code)
    code_entry.delete(0, tk.END)
    code_entry.insert(0, stock_code)

# 设置一个变量来追踪每列的排序方向
sort_directions = {}

def load_df_to_treeview(tree, dataframe):
    """
    将 DataFrame 的内容加载到 Treeview 中。
    """
    # 清空旧数据
    tree.delete(*tree.get_children())
    fast_insert(tree,dataframe)


def safe_drop_down(date_entry):
    # 只在没有弹出日历时才下拉
    logger.info( hasattr(date_entry, "_top_cal") , not date_entry._top_cal.winfo_exists())
    if  hasattr(date_entry, "_top_cal") or not date_entry._top_cal.winfo_exists():
        date_entry.drop_down()
        # 调整日历位置到 DateEntry 下方
        logger.info('没有下拉,正在打开')
        x = date_entry.winfo_rootx()
        y = date_entry.winfo_rooty() + date_entry.winfo_height()
        date_entry._top_cal.geometry(f"+{x}+{y}")


def on_monitor_window_focus(event):
    """
    当任意窗口获得焦点时，协调两个窗口到最前。
    """

    sub_state = sub_var.get()
    if sub_state:
        bring_monitor_to_front(event)

def on_window_focus(event):
    """
    当任意窗口获得焦点时，协调两个窗口到最前。
    """
    sub_state = sub_var.get()
    if sub_state:
        bring_both_to_front(root)
    global alert_window
    if get_work_time()  and alert_window and alert_window.winfo_exists():
        # logger.info(f'bring_both_to_front alert_window')
        alert_window.lift()
        alert_window.attributes('-topmost', 1)
        alert_window.attributes('-topmost', 0)


is_already_triggered = False

def bring_both_to_front(main_window):
    if main_window and main_window.winfo_exists():
        logger.info(f'bring_both_to_front main')
        main_window.lift()
        main_window.attributes('-topmost', 1)
        main_window.attributes('-topmost', 0)
    monitor_list = [win['toplevel'] for win in monitor_windows.values()]

    # for win_info in list(monitor_windows.values()):

    #     if  win_info['toplevel'] and win_info['toplevel'].winfo_exists():
    #         win_info['toplevel'].lift()
    #         win_info['toplevel'].attributes('-topmost', 1)
    #         win_info['toplevel'].attributes('-topmost', 0)
    for win_id, win_info in monitor_windows.items():
        toplevel = win_info.get('toplevel')
        if toplevel and toplevel.winfo_exists():
            # 使用自定义标记记录是否已经在前台
            if not win_info.get('is_lifted', False):
                toplevel.lift()
                toplevel.attributes('-topmost', 1)
                toplevel.attributes('-topmost', 0)
                win_info['is_lifted'] = True  # 标记已提升
            else:
                # 窗口已经在前台，不再刷新
                pass



def get_monitor_index_for_window(window):
    """根据窗口位置找到所属显示器索引"""
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
        

# 整体提升
# def bring_monitor_windows_to_front():
#     """
#     提升所有 monitor_windows 中的窗口到前台，
#     只有第一次不在前台时才会 lift，避免重复刷新。
#     """
#     for win_id, win_info in list(monitor_windows.items()):
#         toplevel = win_info.get('toplevel')
#         if toplevel and toplevel.winfo_exists():
#             # 如果窗口被最小化，则恢复
#             if toplevel.state() == 'iconic':  # 'iconic' 表示最小化
#                 toplevel.deiconify()
#                 win_info['is_lifted'] = False  # 重置状态，让窗口被提升

#             # 检查是否已经提升过
#             if not win_info.get('is_lifted', False):
#                 toplevel.lift()
#                 # 通过 topmost 确保窗口置顶一次，然后恢复普通状态
#                 toplevel.attributes('-topmost', 1)
#                 toplevel.attributes('-topmost', 0)
#                 win_info['is_lifted'] = True

# monitor_windows = {
#     'win1': {'toplevel': win1_toplevel, 'is_lifted': False},
#     'win2': {'toplevel': win2_toplevel, 'is_lifted': False},
# }

# def on_close_window(win_id):
#     win_info = monitor_windows.get(win_id)
#     if win_info:
#         win_info['toplevel'].destroy()
#         del monitor_windows[win_id]



def bring_monitor_to_front(active_window):
    """
    将 active_window 所在显示器上的窗口提升到前台，
    只在未提升过或被最小化时执行，避免闪烁。
    """
    target_monitor = get_monitor_index_for_window(active_window)

    for win_id, win_info in monitor_windows.items():
        toplevel = win_info.get("toplevel")
        if not (toplevel and toplevel.winfo_exists()):
            continue

        monitor_idx = get_monitor_index_for_window(toplevel)
        if monitor_idx != target_monitor:
            continue  # 只处理同一个显示器的窗口

        # 如果窗口被最小化，则恢复并重置标记
        if toplevel.state() == "iconic":
            toplevel.deiconify()
            win_info["is_lifted"] = False

        # 只有未提升过的才执行 lift
        if not win_info.get("is_lifted", False):
            toplevel.lift()
            toplevel.attributes("-topmost", 1)
            toplevel.attributes("-topmost", 0)
            win_info["is_lifted"] = True

# def reset_lift_flags():
#     """
#     定时检测窗口状态，如果窗口失去焦点或被最小化，
#     自动清除 is_lifted 标记，以便下次 bring_windows_to_front 能生效。
#     """
#     for win_id, win_info in monitor_windows.items():
#         toplevel = win_info.get("toplevel")
#         if not (toplevel and toplevel.winfo_exists()):
#             continue

#         # 如果窗口不是最前的 或 被最小化，就重置标记
#         # logger.info(f'{win_id} toplevel.state() :{toplevel.state()} is_lifted : {win_info.keys()}')
#         if toplevel.state() == "iconic" or not toplevel.focus_displayof():
#             win_info["is_lifted"] = False

#     # 每 2 秒检测一次
#     root.after(2000, reset_lift_flags)

def reset_lift_flags():
    """
    定时检测窗口状态，如果窗口失去焦点或被最小化，
    自动清除 is_lifted 标记，以便下次 bring_windows_to_front 能生效。
    """
    for win_id, win_info in monitor_windows.items():
        toplevel = win_info.get("toplevel")

        # --- 窗口已销毁 ---
        if not (toplevel and toplevel.winfo_exists()):
            continue

        # --- 安全检测焦点 ---
        focused = False
        try:
            focused = bool(toplevel.focus_displayof())
        except Exception:
            # popdown 等子控件已销毁时会进入这里
            focused = False

        # --- 最小化 或 未聚焦 → 清除标记 ---
        if toplevel.state() == "iconic" or not focused:
            win_info["is_lifted"] = False

    # 每 2 秒检测一次
    root.after(2000, reset_lift_flags)


# # 在主程序初始化时调用一次
# reset_lift_flags()

def bring_monitor_to_front_old(active_window):
    """只把和 active_window 在同一屏幕的窗口带到前面"""
    # uniq_state =uniq_var.get()
    # dfcf_state = dfcf_var.get()
    sub_state = sub_var.get()
    global alert_moniter_bring_front
    #没有监控中心是开启多窗口级联
    #修改为默认不联动,
    if sub_state and not alert_moniter_bring_front :
        target_monitor = get_monitor_index_for_window(active_window)

        for win_info in monitor_windows.values():
            win = win_info.get("toplevel")
            if win and win.winfo_exists():
                monitor_idx = get_monitor_index_for_window(win)
                if monitor_idx == target_monitor:
                    win.lift()
                    win.attributes("-topmost", 1)
                    win.attributes("-topmost", 0)

        # for win_id, win_info in monitor_windows.items():
        #     toplevel = win_info.get('toplevel')
        #     if toplevel and toplevel.winfo_exists():
        #         # 使用自定义标记记录是否已经在前台
        #         if not win_info.get('is_lifted', False):
        #             toplevel.lift()
        #             toplevel.attributes('-topmost', 1)
        #             toplevel.attributes('-topmost', 0)
        #             win_info['is_lifted'] = True  # 标记已提升
        #         else:
        #             # 窗口已经在前台，不再刷新
        #             pass


    # else:
    #     if root and root.winfo_exists():
    #         logger.info(f'bring_both_to_front root')
    #         root.lift()
    #         root.attributes('-topmost', 1)
    #         root.attributes('-topmost', 0)

def sort_treeview(tree, col, reverse):
    """
    点击列标题时，对Treeview的内容进行排序。
    """
    global viewdf
    data = viewdf.copy()
    uniq_state =uniq_var.get()
    if data is not None and not data.empty and uniq_state:
        data = data.drop_duplicates(subset=['代码'])

    if col == '异动类型':
        col = "板块"
    # 获取当前排序方向，如果未设置则默认为 False (升序)
    reverse_sort = sort_directions.get(col, False)
    
    # --- 核心逻辑修改部分 ---
    if col == '时间':
        # 如果点击的是“时间”列，强制按增序排序（reverse=False）
        data.sort_values(by=col, ascending=not reverse_sort, inplace=True)
        # 强制更新排序方向为 True，以便下一次点击时为降序
        sort_directions[col] = not reverse_sort
    else:
        # 其他列正常切换排序方向
        data.sort_values(by=[col,'时间'], ascending=[not reverse_sort,True], inplace=True)
        # 更新排序方向
        sort_directions[col] = not reverse_sort

    # if '相关信息'  in data.columns:
    #     data.drop(columns=['相关信息'], inplace=True)
    # 重新加载排序后的 DataFrame 到 Treeview
    if 'count'  not in data.columns:
        data = process_full_dataframe(data)
        data['count'] = data.groupby('代码')['代码'].transform('count')
    load_df_to_treeview(tree, data)
    # populate_treeview(data)


def load_window_positions():
    """从配置文件加载所有窗口的位置。"""
    global WINDOW_GEOMETRIES
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                WINDOW_GEOMETRIES = json.load(f)
                logger.info("所有窗口配置已加载。")
            except (json.JSONDecodeError, FileNotFoundError):
                logger.info("配置文件损坏或不存在，使用默认窗口位置。")
    else:
        logger.info("未找到配置文件，使用默认位置。")

def save_window_positions():
    """将所有窗口的位置和大小保存到配置文件。"""
    global WINDOW_GEOMETRIES, save_timer
    if save_timer:
        save_timer.cancel()
    # 确保文件写入在程序退出前完成
    # save_monitor_list()
    logger.info(f'save:{WINDOW_GEOMETRIES}')
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(WINDOW_GEOMETRIES, f)
        logger.info("所有窗口配置已保存。")
    except IOError as e:
        logger.info(f"写入配置文件时出错: {e}")

def schedule_save_positions():
    """安排一个延迟保存，避免过于频繁的写入。"""
    global save_timer
    if save_timer:
        save_timer.cancel()
    logger.info(f'save_monitor_list,schedule_save_positions save')
    save_timer = threading.Timer(0, save_monitor_list) # 延迟1秒保存
    save_timer = threading.Timer(1, save_window_positions) # 延迟1秒保存
    save_timer.start()

def update_window_position(window_id):
    """更新单个窗口的位置到全局字典。"""
    window = WINDOWS_BY_ID.get(window_id)
    if window and window.winfo_exists():
        WINDOW_GEOMETRIES[window_id] = window.geometry()




def on_close_alert_monitor(window):
    """处理子窗口关闭事件"""
    global alert_moniter_bring_front,alert_window,alert_tree
    alert_moniter_bring_front = False
    if alert_window and alert_window.winfo_exists():
        update_window_position("alert_center")  # 保存位置

    try:
        if window and window.winfo_exists():
            window.destroy()
            # 立即处理待办事件，避免半销毁导致的白屏
            try:
                window.update_idletasks()
            except tk.TclError:
                # 某些平台上 destroy 后调用 update 可能抛错，忽略它
                pass
    except tk.TclError:
        # 只捕获 tkinter 相关错误
        pass
    finally:
        alert_window = None
        alert_tree = None


def on_close_monitor(window_info):
    """处理子窗口关闭事件"""

    stock_info = window_info['stock_info']
    stock_code = stock_info[0] # 使用 stock_info 中的第一个元素作为股票代码
    window = window_info['toplevel']
    if stock_code in monitor_windows.keys():
        del monitor_windows[stock_code]

    if window.winfo_exists() and stock_code in WINDOWS_BY_ID.keys() :
        del WINDOWS_BY_ID[stock_code]
        if stock_code in WINDOW_GEOMETRIES.keys():
            del WINDOW_GEOMETRIES[stock_code]
        window.destroy()

def on_closing(window, window_id):
    """在窗口关闭时调用。"""
    
    # save_alerts()
    # 1. 停止后台线程
    executor.shutdown(wait=False)  # 或 wait=True，根据线程安全性
    stop_worker()
    time.sleep(1)
    # 2. 保存监控列表和窗口位置（建议放线程里异步保存）
    try:
        save_monitor_list()
        for win_id in list(WINDOWS_BY_ID.keys()):
            win = WINDOWS_BY_ID.get(window_id)
            if hasattr(win, "_after_id"):
                win.after_cancel(win._after_id)
            update_window_position(win_id) # 确保保存最后的配置
        save_window_positions()
    except Exception as e:
        logger.info(f"保存失败:{e}")
    
    # 3. 取消定时器
    if hasattr(window, "_after_id"):
        window.after_cancel(window._after_id)
    
    # 4. 销毁窗口并移除记录
    if window.winfo_exists():
        del WINDOWS_BY_ID[window_id]
        window.destroy()
    
    # 5. 退出主循环
    root.quit()


# def on_closing(window, window_id):
#     """在窗口关闭时调用。"""
#     # executor.shutdown(wait=False)
#     executor.shutdown(wait=True)

#     save_monitor_list() # 确保在主程序关闭时保存列表
#     for win_id in WINDOWS_BY_ID.keys():
#         # logger.info(f'win_id:{win_id}')
#         win = WINDOWS_BY_ID.get(window_id)
#         if hasattr(win, "_after_id"):
#             win.after_cancel(win._after_id)
#         update_window_position(win_id) # 确保保存最后的配置

#     if hasattr(window, "_after_id"):
#         window.after_cancel(window._after_id)

#     if window.winfo_exists():
#         del WINDOWS_BY_ID[window_id]
#         window.destroy()

#     save_window_positions()
#     root.quit()

def init_screen_size(root):
    global screen_width, screen_height
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()


# def update_position_window(window, window_id, is_main=False):
#     """创建一个新窗口，并加载其位置（自动平铺）"""
#     global WINDOWS_BY_ID, WINDOW_GEOMETRIES, NEXT_OFFSET, OFFSET_STEP, screen_width, screen_height
#     WINDOWS_BY_ID[window_id] = window

#     if window_id in WINDOW_GEOMETRIES.keys():
#         # 有历史配置，直接使用
#         wsize = WINDOW_GEOMETRIES[window_id].split('+')
#         if len(wsize) == 3:
#             subw_width = int(wsize[1])
#             subw_height = int(wsize[2])
#             if subw_width > screen_width or subw_height > screen_height:
#                 place_new_window(window, window_id)
#             else:
#                 window.geometry(WINDOW_GEOMETRIES[window_id])
#         else:
#             place_new_window(window, window_id)
#     else:
#         # 没有配置，使用默认 + 自动平铺
#         place_new_window(window, window_id)

#     # window.bind("<Configure>", lambda event: update_window_position(window_id))
#     return window

def update_position_window(window, window_id, is_main=False):
    """创建一个新窗口，并加载其位置（自动平铺）"""
    global WINDOWS_BY_ID, WINDOW_GEOMETRIES, screen_width, screen_height
    WINDOWS_BY_ID[window_id] = window

    if window_id in WINDOW_GEOMETRIES:
        # 有历史配置，解析并限制到屏幕内
        geom = WINDOW_GEOMETRIES[window_id]
        # if window_id == 'alert_center':
        #     logger.info(f'alert_center geom : {geom}')
        try:
            size_part, x_part, y_part = geom.split('+')
            width, height = map(int, size_part.split('x'))
            x, y = int(x_part), int(y_part)
        except Exception:
            # 格式异常则使用默认放置
            place_new_window(window, window_id)
        else:
            # 限制在可见屏幕内
            monitors = MONITORS or [(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))]
            x, y = clamp_window_to_screens(x, y, width, height, monitors)
            window.geometry(f"{width}x{height}+{x}+{y}")
    else:
        # 没有配置，使用默认 + 自动平铺
        place_new_window(window, window_id)

    return window

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

# # 双屏幕,上屏新建
# def init_monitors():
#     """扫描所有显示器并缓存信息（使用可用区域，避开任务栏）"""
#     global MONITORS
#     monitors = get_all_monitors()  # 原来的函数
#     if not monitors:
#         left, top, right, bottom = get_monitor_workarea()
#         MONITORS = [(left, top, right, bottom)]
#     else:
#         # 对每个 monitor 也可计算可用区域
#         MONITORS = []
#         for mon in monitors:
#             # mon = (x, y, width, height)
#             mx, my, mw, mh = mon
#             MONITORS.append((mx, my, mx+mw, my+mh))
#     logger.info(f"✅ Detected {len(MONITORS)} monitor(s).")

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

def clamp_window_to_screens(x, y, w, h, monitors):
    """保证窗口在可见显示器范围内"""
    for left, top, right, bottom in monitors:
        if left <= x < right and top <= y < bottom:
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            return x, y
    # 如果完全不在任何显示器内，放到主屏幕左上角
    x, y = monitors[0][0], monitors[0][1]
    return x, y

# -----------------------------
# 修改 place_new_window 使用全局缓存
# -----------------------------
# def place_new_window(window, window_id, win_width=300, win_height=160, margin=10):
#     """放置窗口，如果已有存储位置就用，否则垂直平铺"""
#     global WINDOW_GEOMETRIES, WINDOWS_BY_ID, MONITORS
#     WINDOWS_BY_ID[window_id] = window  # 必须保留

#     monitors = MONITORS  # 使用全局缓存

#     if window_id in WINDOW_GEOMETRIES:
#         # 使用已有存储位置
#         geom = WINDOW_GEOMETRIES[window_id]
#         try:
#             _, x_part, y_part = geom.split('+')
#             x, y = int(x_part), int(y_part)
#         except Exception:
#             x, y = 100, 100
#         # 校正窗口位置到可见屏幕
#         x, y = clamp_window_to_screens(x, y, win_width, win_height, monitors)
#         WINDOWS_BY_ID[window_id] = window
#         window.geometry(f"{win_width}x{win_height}+{x}+{y}")
#     else:
#         # 垂直平铺
#         used_positions = []
#         for w in WINDOWS_BY_ID.values():
#             try:
#                 geom = w.geometry()
#                 parts = geom.split('+')
#                 if len(parts) == 3:
#                     used_positions.append((int(parts[1]), int(parts[2])))
#             except:
#                 continue

#         # 从主显示器左上角开始
#         left, top, right, bottom = monitors[0]
#         x, y = left + margin, top + margin
#         step_y = win_height + margin
#         step_x = win_width + margin
#         max_y = bottom - win_height - margin

#         while (x, y) in used_positions:
#             y += step_y
#             if y > max_y:
#                 y = top + margin
#                 x += step_x
#                 if x + win_width > right:
#                     x = left + margin

#         window.geometry(f"{win_width}x{win_height}+{x}+{y}")

def rects_overlap(r1, r2):
    """判断两个矩形是否重叠"""
    x1, y1, x2, y2 = r1
    a1, b1, a2, b2 = r2
    return not (x2 <= a1 or a2 <= x1 or y2 <= b1 or b2 <= y1)


def get_physical_resolution():
    """
    获取主显示器物理分辨率 (width, height)
    """
    try:
        monitors = win32api.EnumDisplayMonitors()
        if monitors:
            info = win32api.GetMonitorInfo(monitors[0][0])
            left, top, right, bottom = info["Monitor"]
            return right - left, bottom - top
    except Exception as e:
        logger.info(f"⚠️ 无法获取物理分辨率:{e}")
    return win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def print_tk_dpi_detail(root, scale_factor_holder):
    """
    打印 Tk 实际缩放和物理分辨率比较，返回逻辑与物理宽度。
    """
    # Tk 获取的逻辑分辨率（受系统缩放影响）
    logical_width = root.winfo_screenwidth()
    logical_height = root.winfo_screenheight()

    # 系统实际物理分辨率
    physical_width, physical_height = get_physical_resolution()

    # 当前缩放比（系统层面缩放因子）
    scale = round(physical_width / logical_width, 2)

    if abs(scale - scale_factor_holder["scale"]) > 0.01:
        logger.info("──────────────────────────────")
        logger.info(f"物理分辨率: {physical_width}×{physical_height}")
        logger.info(f"逻辑分辨率: {logical_width}×{logical_height}")
        logger.info(f"系统缩放比: {scale:.2f}×（物理/逻辑）")
        logger.info(f"上次记录: {scale_factor_holder['scale']}")
        scale_factor_holder["scale"] = scale
    # logger.info(f"物理分辨率: {physical_width}×{physical_height}")
    # logger.info(f"逻辑分辨率: {logical_width}×{logical_height}")
    # logger.info(f"系统缩放比: {scale:.2f}×（物理/逻辑）")
    return physical_width, logical_width


def check_dpi_change(root, scale_factor_holder, last_dpi_holder):
    """
    定期检测 DPI/缩放变化（5 秒），并自动应用 Tk scaling。
    """
    physical_width, logical_width = print_tk_dpi_detail(root, scale_factor_holder)

    current_scale = scale_factor_holder["scale"]

    # 检测缩放变化
    if abs(current_scale - last_dpi_holder["scale"]) > 0.05:
        logger.info(f"[缩放变化检测] 从 {last_dpi_holder['scale']:.2f} → {current_scale:.2f}")
        # root.tk.call('tk', 'scaling', current_scale)
        init_monitors()
        last_dpi_holder["scale"] = current_scale

    # 5 秒后继续检测
    root.after(5000, lambda: check_dpi_change(root, scale_factor_holder, last_dpi_holder))


def start_dpi_monitor(root):
    """
    启动 DPI / 缩放监测，基于真实物理分辨率。
    """
    scale_holder = {"scale": 1.0}
    last_holder = {"scale": 1.0}
    check_dpi_change(root, scale_holder, last_holder)
    return scale_holder

def place_new_window(window, window_id, win_width=300, win_height=160, margin=2):
    """放置窗口：避免重叠 + 在所属屏幕内自动排列"""
    global WINDOW_GEOMETRIES, WINDOWS_BY_ID, MONITORS
    WINDOWS_BY_ID[window_id] = window

    monitors = MONITORS or [(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))]

    # if window_id in WINDOW_GEOMETRIES:
    #     # 使用已存储位置
    #     geom = WINDOW_GEOMETRIES[window_id]
    #     try:
    #         _, x_part, y_part = geom.split('+')
    #         x, y = int(x_part), int(y_part)
    #     except Exception:
    #         x, y = 100, 100
    #     x, y = clamp_window_to_screens(x, y, win_width, win_height, monitors)
    #     window.geometry(f"{win_width}x{win_height}+{x}+{y}")
    #     return

    # 如果已有历史 geometry
    if window_id in WINDOW_GEOMETRIES:
        geom = WINDOW_GEOMETRIES[window_id]
        try:
            size_part, x_part, y_part = geom.split('+')
            w_width, w_height = map(int, size_part.split('x'))
            x, y = int(x_part), int(y_part)
        except Exception:
            x, y = 100, 100
            w_width, w_height = win_width, win_height

        # 只调整超出屏幕的窗口
        x, y = clamp_window_to_screens(x, y, w_width, w_height, monitors)
        window.geometry(f"{w_width}x{w_height}+{x}+{y}")
        return

    # -------------------
    # 自动排列逻辑
    # -------------------
    # 1. 获取所有已占用的矩形
    used_rects = []
    for w in WINDOWS_BY_ID.values():
        try:
            geom = w.geometry()  # e.g. "300x160+100+200"
            size_part, x_part, y_part = geom.split('+')
            w_width, w_height = map(int, size_part.split('x'))
            x, y = int(x_part), int(y_part)
            used_rects.append((x, y, x + w_width, y + w_height))
        except:
            continue

    # 2. 默认放主屏幕（第一个）
    left, top, right, bottom = monitors[0]
    step_x, step_y = win_width + margin, win_height + margin
    max_x, max_y = right - win_width - margin, bottom - win_height - margin

    # 3. 尝试所有候选位置
    y = top + margin
    while y <= max_y:
        x = left + margin
        while x <= max_x:
            new_rect = (x, y, x + win_width, y + win_height)
            if not any(rects_overlap(new_rect, r) for r in used_rects):
                # 找到不重叠的位置
                window.geometry(f"{win_width}x{win_height}+{x}+{y}")
                return
            x += step_x
        y += step_y

    # 4. 如果全满，放在主屏幕左上角（兜底）
    window.geometry(f"{win_width}x{win_height}+{left+margin}+{top+margin}")


# import win32api
#窗口重排2
# def get_screen_bounds(hwnd):
#     """获取窗口所在屏幕的边界 (left, top, right, bottom)。"""
#     # 获取窗口矩形
#     rect = hwnd.winfo_geometry()  # "WxH+X+Y"
#     w, h, x, y = parse_geometry(rect)
#     center_x, center_y = x + w // 2, y + h // 2

#     # 遍历所有显示器，找到包含该点的屏幕
#     monitors = win32api.EnumDisplayMonitors()
#     for monitor in monitors:
#         (mx1, my1, mx2, my2) = monitor[2]
#         if mx1 <= center_x <= mx2 and my1 <= center_y <= my2:
#             return (mx1, my1, mx2, my2)

#     # 默认返回主屏幕
#     return win32api.GetSystemMetrics(0), 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


# def parse_geometry(geom_str):
#     """解析 Tk geometry: WxH+X+Y -> (w, h, x, y)"""
#     wh, xy = geom_str.split("+", 1)
#     w, h = map(int, wh.split("x"))
#     x, y = map(int, xy.split("+"))
#     return w, h, x, y


# def rearrange_windows_in_screens(windows, margin=10, col_width=400, row_height=300):
#     """
#     只在窗口所在的屏幕内重排窗口。
#     windows: {id: tk_window}
#     """
#     # 1. 按屏幕分组
#     screen_groups = {}
#     for win_id, win in windows.items():
#         bounds = get_screen_bounds(win)
#         screen_groups.setdefault(bounds, []).append(win)

#     # 2. 每个屏幕内独立重排
#     for bounds, group in screen_groups.items():
#         left, top, right, bottom = bounds
#         screen_w, screen_h = right - left, bottom - top

#         x, y = left + margin, top + margin
#         max_height_in_col = 0

#         for win in group:
#             w, h, _, _ = parse_geometry(win.winfo_geometry())

#             # 如果超出屏幕高度，换列
#             if y + h + margin > bottom:
#                 x += col_width + margin
#                 y = top + margin

#             win.geometry(f"{w}x{h}+{x}+{y}")
#             y += h + margin


# def create_monitor_window_notime(stock_info):
#     # stock_info 可能缺失部分数据
#     global monitor_windows
#     if stock_info[0].find(':') > 0 and len(stock_info) > 4:
#         stock_info = stock_info[1:]

#     # 默认值
#     default_values = {
#         "percent": 0.0,
#         "price": 0.0,
#         "vol": 0
#     }

#     try:
#         stock_code, stock_name, *rest = stock_info
#     except ValueError:
#         stock_code, stock_name = stock_info[0], stock_info[1]
#         rest = []

#     # 填充缺失数据
#     percent = rest[3] if len(rest) >= 4 else default_values["percent"]
#     price   = rest[4] if len(rest) >= 5 else default_values["price"]
#     vol     = rest[5] if len(rest) >= 6 else default_values["vol"]

#     # 构造 stock_info 完整列表
#     stock_info = [stock_code, stock_name, 0, 0 ,  percent , price ,vol]

#     monitor_win = tk.Toplevel(root)
#     monitor_win.resizable(True, True)
#     monitor_win.title(f"监控: {stock_name} ({stock_code})")

#     # === 警报开关 ===

#     alerts_enabled[stock_code] = tk.IntVar(value=1)
#     cb = tk.Checkbutton(monitor_win, text="报警开启", variable=alerts_enabled[stock_code])
#     cb.pack(anchor='w', padx=5, pady=5)

#     # 样式
#     style = ttk.Style()
#     style.configure('Thin.Vertical.TScrollbar', arrowsize=8)

#     tree_frame = ttk.Frame(monitor_win)
#     tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)


#     columns = ('时间', '异动类型', '涨幅', '价格', '量')
#     monitor_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
#     vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=monitor_tree.yview, style='Thin.Vertical.TScrollbar')
#     monitor_tree.configure(yscrollcommand=vsb.set)
#     vsb.pack(side=tk.RIGHT, fill=tk.Y)
#     monitor_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

#     for col in columns:
#         monitor_tree.heading(col, text=col)
#         if col in ['涨幅', '量']:
#             monitor_tree.column(col, width=30, anchor=tk.CENTER, minwidth=20)
#         elif col in ['异动类型']:
#             monitor_tree.column(col, width=60, anchor=tk.CENTER, minwidth=40)
#         else:
#             monitor_tree.column(col, width=40, anchor=tk.CENTER, minwidth=30)

#     monitor_tree.tag_configure("alert", background="yellow", foreground="red")
#     item_id = monitor_tree.insert("", "end", values=("加载ing...", "", "", "", ""))


#     # === 右键菜单加报警规则 ===
#     # def show_menu(event, stock_info):
#     #     menu = tk.Menu(monitor_win, tearoff=0)
#     #     menu.add_command(label="设置报警规则", command=lambda : open_alert_editor(stock_info))
#     #     menu.post(event.x_root, event.y_root)
#     def show_menu(event,stock_info):
#         """
#         在Treeview上處理右鍵點擊事件的函式。
#         """

#         # sel = alert_tree.selection()
#         # if not sel: return
#         # vals = alert_tree.item(sel[0], "values")
#         # code = vals[1]
#         # 1. 根據右鍵點擊的座標，找出對應的Treeview項目
#         parent_win = event.widget.winfo_toplevel()
#         iid = monitor_tree.identify_row(event.y)
        
#         # 2. 如果點擊在某個項目上
#         if iid:
#             # 3. 確保點擊的項目被選中
#             monitor_tree.selection_set(iid)
#             # 4. 取得當前選中的項目ID（此時它應該是iid）
#             selected_item_id = monitor_tree.selection()[0]
            
#             # # 5. 獲取該項目的值，例如股票代號
#             stock_info = monitor_tree.item(selected_item_id, "values")
#             # stock_code = item_values[0] # 假設股票代號是第一欄
#             # stock_info = stock_info[1:]
#             # logger.info(f'stock_info:{stock_info}')

#             if len(stock_info) == 5:
#                 _ ,_ , percent, price , vol = stock_info
#                 stock_info =  (stock_code,stock_name,0,0 , percent, price , vol) 
#             else:
#                 stock_info = (stock_code,) + stock_info[1:]
#             # 6. 建立右鍵選單
#             # logger.info(f'stock_info:{stock_info}')
#             menu = tk.Menu(root, tearoff=0)
            
#             # 7. 动态地為選單命令綁定函式和參數
#             menu.add_command(label="設定警報規則", command=lambda: open_alert_editor(stock_info,parent_win=parent_win,
#                 x_root=event.x_root,
#                 y_root=event.y_root))
#             # 8. 顯示選單
#             menu.post(event.x_root, event.y_root)
#         else:
#             # 如果點擊在空白處，清除選中狀態
#             # tree.selection_remove(tree.selection())
#             menu = tk.Menu(monitor_win, tearoff=0)
#             menu.add_command(label="設定警報規則", command=lambda: open_alert_editor(stock_infoparent_win=parent_win,
#                 x_root=event.x_root,
#                 y_root=event.y_root))
#             menu.post(event.x_root, event.y_root)


#     # === 保存窗口信息到全局字典 ===
#     monitor_windows[stock_code] = {
#         'toplevel': monitor_win,
#         'monitor_tree': monitor_tree,
#         'stock_info': stock_info  # 新增这一行
#     }

#     window_info = {'stock_info': stock_info, 'toplevel': monitor_win}

#     place_new_window(monitor_win, stock_code)
#     refresh_stock_data(window_info, monitor_tree, item_id)
#     monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
#     monitor_win.bind("<FocusIn>", lambda e, w=monitor_win: on_monitor_window_focus(w))
#     monitor_win.bind("<Button-1>", lambda event: update_code_entry(stock_code))
#     monitor_win.bind("<Double-1>", lambda event, code=stock_code: on_monitor_double_click(event,stock_code))
#     monitor_win.bind("<Button-3>", lambda event: show_menu(event, stock_info))
    
#     return window_info


def normalize_stock_info1(stock_info):
    """
    规范化 stock_info 结构，最终格式为 8 项：
    [code, name, 0, 0, percent, price, vol, create_time]
    """

    # ============================================
    # ① 修复你说的 Bug：某些 stock_info 前缀带 index:xxx
    # ============================================
    if isinstance(stock_info[0], str) and ":" in stock_info[0] and len(stock_info) > 4:
        stock_info = stock_info[1:]

    # ============================================
    # ② 拆解基本字段
    # ============================================
    try:
        stock_code, stock_name, *rest = stock_info
    except ValueError:
        stock_code = stock_info[0]
        stock_name = stock_info[1] if len(stock_info) > 1 else ""
        rest = []

    # 旧数据中的时间字段可能在 rest 中任何位置
    old_time = None
    for v in rest:
        if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v.strip()):
            old_time = v.strip()
            break

    # ============================================
    # ③ 自动生成其余字段
    # ============================================
    default_values = {"percent": 0.0, "price": 0.0, "vol": 0}

    percent = rest[0] if len(rest) >= 1 else default_values["percent"]
    price   = rest[1] if len(rest) >= 2 else default_values["price"]
    vol     = rest[2] if len(rest) >= 3 else default_values["vol"]

    # ============================================
    # ④ 修复 create_time：保持旧的，不重复生成
    # ============================================
    if old_time:
        create_time = old_time  # 使用旧时间
    else:
        create_time = datetime.now().strftime("%Y-%m-%d %H")  # 新时间

    # ============================================
    # ⑤ 生成最终 8 项结构
    # ============================================
    return [stock_code, stock_name, 0, 0, percent, price, vol, create_time]

def normalize_stock_info2(stock_info):
    # 如果有带 ':' 的前缀就移除
    if stock_info[0].find(':') > 0 and len(stock_info) > 4:
        stock_info = stock_info[1:]

    # 统一确保长度至少 2
    stock_code = stock_info[0]
    stock_name = stock_info[1]

    # 默认值
    percent = 0.0
    price   = 0.0
    vol     = 0

    # 剩余部分
    rest = stock_info[2:]

    # ---- 判断最后一项是否是 create_time ----
    create_time = None
    if rest and isinstance(rest[-1], str) and len(rest[-1]) >= 10:
        # 是时间
        create_time = rest[-1]
        rest = rest[:-1]

    # ---- 按顺序提取 percent / price / vol ----
    if len(rest) >= 1: percent = rest[0]
    if len(rest) >= 2: price   = rest[1]
    if len(rest) >= 3: vol     = rest[2]

    # ---- 创建时间缺失就生成 ----
    if not create_time:
        create_time = datetime.now().strftime("%Y-%m-%d %H")

    # ---- 最终统一结构（6 项）----
    return [stock_code, stock_name, percent, price, vol, create_time]


def create_monitor_window(stock_info):
    global monitor_windows

    if stock_info[0].find(':') > 0 and len(stock_info) > 4:
        stock_info = stock_info[1:]


    # === 创建时间 ===
    create_time = datetime.now().strftime("%Y-%m-%d %H")
    # 默认值
    default_values = {"percent": 0.0, "price": 0.0, "vol": 0,'create_time':create_time}

    try:
        stock_code, stock_name, *rest = stock_info
    except ValueError:
        stock_code, stock_name = stock_info[0], stock_info[1]
        rest = []

    percent = rest[2] if len(rest) >= 3 else default_values["percent"]
    price   = rest[3] if len(rest) >= 4 else default_values["price"]
    vol     = rest[4] if len(rest) >= 5 else default_values["vol"]
    c_time     = rest[5] if len(rest) >= 6 else default_values["create_time"]
    # # 构造完整 stock_info
    # stock_info = [stock_code, stock_name, 0, 0, percent, price, vol,c_time]
    # ✅ 构造带时间的 stock_info（升级结构）
    stock_info = [stock_code, stock_name, 0, 0, percent, price, vol, c_time]

    # === 创建窗口 ===
    monitor_win = tk.Toplevel(root)
    monitor_win.resizable(True, True)
    monitor_win.title(f"监控: {stock_name} ({stock_code})")

    # === 顶部信息栏 ===
    top_frame = ttk.Frame(monitor_win)
    top_frame.pack(fill=tk.X, padx=5, pady=5)

    # 报警开关
    alerts_enabled[stock_code] = tk.IntVar(value=1)
    cb = tk.Checkbutton(top_frame, text="报警开启", variable=alerts_enabled[stock_code])
    cb.pack(side=tk.LEFT, anchor='w')

    # 添加：创建时间标签
    lbl_time = ttk.Label(top_frame, text=f"创建时间: {c_time}", foreground="gray")
    lbl_time.pack(side=tk.LEFT, padx=10)


    # === 样式 ===
    style = ttk.Style()
    style.configure('Thin.Vertical.TScrollbar', arrowsize=8)

    tree_frame = ttk.Frame(monitor_win)
    tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

    columns = ('时间', '异动类型', '涨幅', '价格', '量')
    monitor_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=monitor_tree.yview, style='Thin.Vertical.TScrollbar')
    monitor_tree.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    monitor_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

    for col in columns:
        monitor_tree.heading(col, text=col)
        if col in ['涨幅', '量']:
            monitor_tree.column(col, width=30, anchor=tk.CENTER, minwidth=20)
        elif col in ['异动类型']:
            monitor_tree.column(col, width=60, anchor=tk.CENTER, minwidth=40)
        else:
            monitor_tree.column(col, width=40, anchor=tk.CENTER, minwidth=30)

    monitor_tree.tag_configure("alert", background="yellow", foreground="red")
    item_id = monitor_tree.insert("", "end", values=("加载ing...", "", "", "", ""))

    # === 右键菜单 ===
    def show_menu(event, stock_info):
        parent_win = event.widget.winfo_toplevel()
        iid = monitor_tree.identify_row(event.y)
        if iid:
            monitor_tree.selection_set(iid)
            selected_item_id = monitor_tree.selection()[0]
            item_values = monitor_tree.item(selected_item_id, "values")

            if len(item_values) == 5:
                _, _, percent, price, vol = item_values
                si = (stock_code, stock_name, 0, 0, percent, price, vol)
            else:
                si = (stock_code,) + item_values[1:]

            menu = tk.Menu(root, tearoff=0)
            menu.add_command(label="设置报警规则",
                             command=lambda: open_alert_editor(si,
                                 parent_win=parent_win,
                                 x_root=event.x_root,
                                 y_root=event.y_root))
            menu.post(event.x_root, event.y_root)
        else:
            menu = tk.Menu(monitor_win, tearoff=0)
            menu.add_command(label="设置报警规则",
                             command=lambda: open_alert_editor(stock_info,
                                 parent_win=parent_win,
                                 x_root=event.x_root,
                                 y_root=event.y_root))
            menu.post(event.x_root, event.y_root)

    # === 保存窗口信息 ===
    window_info = {
        'stock_info': stock_info,
        'toplevel': monitor_win,
        'monitor_tree': monitor_tree,
    }

    monitor_windows[stock_code] = {
        'toplevel': monitor_win,
        'monitor_tree': monitor_tree,
        'stock_info': stock_info,
    }


    # === 手动刷新函数（带日志） ===
    def refresh_manual(stock_code):
        try:
           start = time.time()
           logger.info(f"MonitorDFCF: 手动刷新触发 -> {stock_code}")

           refresh_stock_data(window_info, monitor_tree, item_id,True)
           # 手动触发双击逻辑（给一个虚拟 event）
           fake_event = type("FakeEvent", (), {"widget": monitor_tree})()
           on_monitor_double_click(fake_event, stock_code,manual=True)
           # used = (time.time() - start) * 1000
           # logger.info(f"MonitorDFCF: 手动刷新完成 -> {stock_code}, 耗时 {used:.1f} ms")

        except Exception as e:
           logger.error(f"MonitorDFCF: 手动刷新异常 -> {stock_code}: {e}", exc_info=True)

    # === 🔄 刷新按钮 ===
    btn_refresh = ttk.Button(
        top_frame,
        text="刷新",
        command=lambda code=stock_code: refresh_manual(code)
    )
    btn_refresh.pack(side=tk.LEFT, padx=10)

    # === 注册事件 ===
    place_new_window(monitor_win, stock_code)
    refresh_stock_data(window_info, monitor_tree, item_id)
    monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
    monitor_win.bind("<FocusIn>", lambda e, w=monitor_win: on_monitor_window_focus(w))
    monitor_tree.bind("<Button-1>", lambda event: update_code_entry(stock_code))
    monitor_tree.bind("<Double-1>", lambda event, code=stock_code: on_monitor_double_click(event, stock_code))
    monitor_win.bind("<Button-3>", lambda event: show_menu(event, stock_info))

    return window_info


# ------------------------
# 报警规则加载/保存
# ------------------------
# def load_alerts():
#     global alerts_rules
#     try:
#         with open(ALERTS_FILE, "r") as f:
#             alerts_rules = json.load(f)
#     except:
#         alerts_rules = {}

# def save_alerts():
#     with open(ALERTS_FILE, "w") as f:
#         json.dump(alerts_rules, f, indent=2, ensure_ascii=False)


# def update_meta_info(alert_rules, code, price=None, percent=None, vol=None):
#     """
#     自动更新指定股票的 meta 信息（如价格、涨幅、成交量等），
#     并计算涨幅变化 delta_percent。
#     兼容旧格式（list → dict）。
#     """
#     if code not in alert_rules:
#         logger.info(f"⚠️ 未找到代码 {code} 的监控规则，跳过更新")
#         return alert_rules

#     entry = alert_rules[code]
#     now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # --- 兼容旧格式（list → dict） ---
#     if isinstance(entry, list):
#         entry = {
#             "meta": {
#                 "created_at": now_str,
#                 "updated_at": now_str,
#                 "created_price": price,
#                 "created_percent": percent,
#                 "created_vol": vol,
#                 "updated_price": price,
#                 "updated_percent": percent,
#                 "updated_vol": vol,
#                 "delta_percent": 0.0,
#             },
#             "rules": entry,
#         }
#         alert_rules[code] = entry
#         return alert_rules

#     # --- 已是新版结构 ---
#     meta = entry.get("meta", {})

#     # 初始化 created 值
#     if meta.get("created_price") is None:
#         meta["created_price"] = price
#         meta["created_percent"] = percent
#         meta["created_vol"] = vol
#         meta["created_at"] = now_str

#     # 更新 updated 值
#     meta["updated_price"] = price
#     meta["updated_percent"] = percent
#     meta["updated_vol"] = vol
#     meta["updated_at"] = now_str

#     # --- 计算涨幅变化 ---
#     try:
#         if meta.get("created_percent") is not None and percent is not None:
#             meta["delta_percent"] = round(percent - meta["created_percent"], 2)
#     except Exception:
#         meta["delta_percent"] = None

#     entry["meta"] = meta
#     alert_rules[code] = entry
#     return alert_rules




def upgrade_alert_rules(data):
    """将旧版 list 结构升级为新版带 meta 的结构"""
    from datetime import datetime
    # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d")
    new_data = {}
    for code, rules in data.items():
        if isinstance(rules, list):
            # 尝试取价格/涨幅/量
            price = next((r["value"] for r in rules if r["field"]=="价格"), 0)
            percent = next((r["value"] for r in rules if r["field"]=="涨幅"), 0)
            vol = next((r["value"] for r in rules if r["field"]=="量"), 0)
            new_data[code] = {
                "meta": {
                    "created_at": now,
                    "updated_at": now,
                    "created_price": price,
                    "created_percent": percent,
                    "created_vol": vol,
                    "updated_price": price,
                    "updated_percent": percent,
                    "updated_vol": vol,
                },
                "rules": rules
            }
        else:
            # 已经是新版，直接保留
            new_data[code] = rules
    return new_data

# def load_alerts():
#     """加载报警规则文件，若为旧格式则自动升级"""
#     global alerts_rules

#     if not os.path.exists(ALERTS_FILE):
#         alerts_rules = {}
#         return

#     try:
#         with open(ALERTS_FILE, "r", encoding="utf-8") as f:
#             data = json.load(f)
#     except UnicodeDecodeError:
#         # 尝试 gbk 编码
#         with open(ALERTS_FILE, "r", encoding="gbk") as f:
#             data = json.load(f)
#     except Exception as e:
#         logger.info(f"❌ 读取报警规则失败: {e}")
#         alerts_rules = {}
#         return

#     # 检测是否需要升级
#     needs_upgrade = any(isinstance(v, list) for v in data.values())
#     if needs_upgrade:
#         logger.info("⚙️ 检测到旧版报警规则格式，正在升级...")
#         data = upgrade_alert_rules(data)
#         with open(ALERTS_FILE, "w", encoding="utf-8") as f:
#             json.dump(data, f, indent=2, ensure_ascii=False)
#         logger.info("✅ 报警规则文件已自动升级为新版结构。")

#     alerts_rules = data

def load_alerts():
    """加载报警规则文件，若为旧格式则自动升级，同时补齐 meta 时间和创建字段"""
    global alerts_rules

    if not os.path.exists(ALERTS_FILE):
        alerts_rules = {}
        return

    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except UnicodeDecodeError:
        with open(ALERTS_FILE, "r", encoding="gbk") as f:
            data = json.load(f)
    except Exception as e:
        logger.info(f"❌ 读取报警规则失败: {e}")
        alerts_rules = {}
        return

    # 升级旧版 list 格式
    needs_upgrade = any(isinstance(v, list) for v in data.values())
    if needs_upgrade:
        logger.info("⚙️ 检测到旧版报警规则格式，正在升级...")
        data = upgrade_alert_rules(data)
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("✅ 报警规则文件已自动升级为新版结构。")

    # ------------------ 补齐 meta ------------------
    for code, item in data.items():
        if isinstance(item, dict) and "rules" in item:
            meta = item.get("meta", {})

            # 补齐时间
            created_at = meta.get("created_at")
            updated_at = meta.get("updated_at")
            if not created_at and updated_at:
                meta["created_at"] = updated_at
            if not updated_at and created_at:
                meta["updated_at"] = created_at

            # 补齐价格/涨幅/量
            for field in ["price", "percent", "vol"]:
                created_key = f"created_{field}"
                updated_key = f"updated_{field}"
                if created_key not in meta or meta[created_key] is None:
                    if updated_key in meta:
                        meta[created_key] = meta[updated_key]
                if updated_key not in meta or meta[updated_key] is None:
                    if created_key in meta:
                        meta[updated_key] = meta[created_key]

            item["meta"] = meta
            data[code] = item

    alerts_rules = data



def save_alerts():
    """保存报警规则"""
    try:
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts_rules, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.info(f"❌ 保存报警规则失败: {e}")
# ------------------------
# 报警添加/刷新
# ------------------------
# ============ 高亮函数 ============
# def highlight_window(win, times=10, delay=300):
#     """让窗口闪烁提示"""
#     def _flash(count):
#         if not win.winfo_exists():
#             return
#         color = "red" if count % 2 == 0 else "SystemButtonFace"
#         win.configure(bg=color)
#         if count < times:
#             win.after(delay, _flash, count + 1)
#         else:
#             win.configure(bg="SystemButtonFace")  # 恢复默认
#     _flash(0)

def highlight_window_nobg(win, times=10, delay=300, interval=60_000):
    """
    让窗口闪烁提示，并提前到最前端
    win: 要闪烁的窗口对象
    times: 每次闪烁次数
    delay: 每次闪烁间隔(ms)
    interval: 间隔多久再次闪烁(ms)，默认30秒
    """
    def _flash(count):
        if not win.winfo_exists():
            return
        # 每次闪烁前把窗口提前
        if count == 0:
            win.lift()
            win.attributes("-topmost", True)
            win.after(1, lambda: win.attributes("-topmost", False))  # 立即取消 topmost 保持正常交互

        color = "red" if count % 2 == 0 else "SystemButtonFace"
        win.configure(bg=color)

        if count < times:
            win.after(delay, _flash, count + 1)
        else:
            win.configure(bg="SystemButtonFace")
            # 30秒后再次触发闪烁
            win.after(interval, _flash, 0)
    _flash(0)

# def highlight_window(win, times=10, delay=300, interval=60_000,alter_tdx=False):
#     """
#     让窗口闪烁提示，并提前到最前端
#     win: 要闪烁的窗口对象
#     times: 每次闪烁次数
#     delay: 每次闪烁间隔(ms)
#     interval: 间隔多久再次闪烁(ms)，默认60秒
#     """
#     def _flash(count):
#         if not win.winfo_exists():
#             return
#         # 每次闪烁前把窗口提前
#         if count == 0:
#             win.lift()
#             if alter_tdx:
#                 win.attributes("-topmost", True)
#                 win.after(1, lambda: win.attributes("-topmost", False))  # 立即取消 topmost 保持正常交互

#         color = "red" if count % 2 == 0 else "SystemButtonFace"
#         win.configure(bg=color)

#         if count < times:
#             win.after(delay, _flash, count + 1)
#         else:
#             # 🔴 闪烁结束后保持红色
#             if alter_tdx:
#                 win.configure(bg="red")
#                 if not hasattr(win, "_alter_tdx"):
#                     win._alter_tdx = True
#                 # 如果有 Treeview，也修改背景为红色
#                 # if hasattr(win, "monitor_tree") and win.monitor_tree.winfo_exists():
#                 #     style = ttk.Style()
#                 #     style.configure("Red.Treeview", background="red", fieldbackground="red")
#                 #     win.monitor_tree.configure(style="Red.Treeview")
#             else:
#                 if not hasattr(win, "_alter_tdx"):
#                     win.configure(bg="SystemButtonFace")
#             # 30秒后再次触发闪烁
#             win.after(interval, _flash, 0)

#     _flash(0)

def highlight_window(win, times=10, delay=300, interval=60_000, alter_tdx=False):
    """
    让窗口闪烁提示，并提前到最前端
    """
    # 提前标记 alter_tdx 属性
    if alter_tdx and not hasattr(win, "_alter_tdx"):
        win._alter_tdx = True

    def _flash(count):
        if not win.winfo_exists():
            return
        if count == 0:
            win.lift()
            if alter_tdx:
                win.attributes("-topmost", True)
                win.after(1, lambda: win.attributes("-topmost", False))

        # 闪烁颜色
        color = "red" if alter_tdx else ("red" if count % 2 == 0 else "SystemButtonFace")
        win.configure(bg=color)

        if count < times:
            win.after(delay, _flash, count + 1)
        else:
            # 闪烁结束后
            if alter_tdx:
                win.configure(bg="red")
                # 如果有 Treeview，也修改背景为红色
                # if hasattr(win, "monitor_tree") and win.monitor_tree.winfo_exists():
                #     style = ttk.Style()
                #     style.configure("Red.Treeview", background="red", fieldbackground="red")
                #     win.monitor_tree.configure(style="Red.Treeview")
            else:
                if not hasattr(win, "_alter_tdx"):
                    win.configure(bg="SystemButtonFace")

            # 间隔再次触发 无限闪屏
            # win.after(interval, _flash, 0)

    _flash(0)



def flash_title(win, code, name):
    """窗口标题加上 ⚠ 提示"""
    if not win.winfo_exists():
        return
    win.title(f"⚠监控: {name} ({code})")
    # 5 秒后恢复
    win.after(5000, lambda: win.title(f"监控: {name} ({code})"))

# def get_toast_parent(stock_code=None):
#     """
#     返回一个现有监控窗口作为 toast 的 parent。
#     如果指定 stock_code，优先返回对应窗口；
#     否则返回任意已打开的监控窗口。
#     如果没有监控窗口，返回 None。
#     """
#     # 如果指定股票代码，找对应窗口
#     if stock_code:
#         win = monitor_windows.get(stock_code)
#         if win:
#             return win['toplevel']

#     # 否则找任意窗口
#     for win in monitor_windows.values():
#         return win['toplevel']  # 返回第一个

#     # 没有任何窗口
#     return None

# import tkinter as tk
# import threading

def toast_message2(parent=None, text="", duration=2000, bg="#333", fg="#fff"):
    """
    在主窗口右下角显示一条提示信息，自动淡出。
    parent: 可以是已有监控窗口或 root，如果为 None，会尝试使用已有 Toplevel，否则用 root。
    """
    global root, monitor_windows

    def _show():
        nonlocal parent
        # 如果没有传入 parent，尝试使用任意已打开的 Toplevel 监控窗口
        if parent is None:
            # parent = next((win for win in monitor_windows.values() if isinstance(win, tk.Toplevel)), None)
            parent_win = next((win['toplevel'] for win in monitor_windows.values() if isinstance(win.get('toplevel'), tk.Toplevel)), None)
            logger.info(parent_win)
        # 如果仍然没有 parent，则使用 root
        if parent is None:
            # parent = root
            parent = tk.Tk()
            parent.withdraw()

        # 创建 toast 窗口
        win = tk.Toplevel(parent)
        win.overrideredirect(True)
        win.config(bg=bg)

        # 文本标签
        label = tk.Label(win, text=text, bg=bg, fg=fg, font=("Microsoft YaHei", 11))
        label.pack(ipadx=15, ipady=8)

        # 放在 parent 窗口右下角
        parent.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() - win.winfo_reqwidth() - 20
        y = parent.winfo_y() + parent.winfo_height() - win.winfo_reqheight() - 40
        win.geometry(f"+{x}+{y}")

        # 窗口置顶
        win.attributes("-topmost", True)
        win.update()
        win.attributes("-topmost", False)

        # 自动淡出
        def fade(alpha=1.0):
            if alpha <= 0:
                win.destroy()
            else:
                win.attributes("-alpha", alpha)
                win.after(50, fade, alpha - 0.05)

        win.after(duration, fade)

    # 线程安全：后台线程调用时用 root.after 调回主线程
    if threading.current_thread() == threading.main_thread():
        _show()
    else:
        root.after(0, _show)


def toast_message(parent=None, text="", duration=2000, bg="#333", fg="#fff"):
    """在主窗口右下角显示一条提示信息，自动淡出"""
    # 如果仍然没有 parent，则使用 root
    if parent is None:
        # parent = root
        parent = tk.Tk()
        parent.withdraw()
    win = tk.Toplevel(parent)
    win.overrideredirect(True)
    win.config(bg=bg)

    # 文本标签
    label = tk.Label(win, text=text, bg=bg, fg=fg, font=("Microsoft YaHei", 11))
    label.pack(ipadx=15, ipady=8)

    # 放在主窗口右下角
    parent.update_idletasks()
    x = parent.winfo_x() + parent.winfo_width() - win.winfo_reqwidth() - 20
    y = parent.winfo_y() + parent.winfo_height() - win.winfo_reqheight() - 40
    win.geometry(f"+{x}+{y}")

    # 窗口置顶
    win.attributes("-topmost", True)
    win.update()
    win.attributes("-topmost", False)

    # 自动淡出（用 after 循环，主线程安全）
    def fade(alpha=1.0):
        if alpha <= 0:
            win.destroy()
        else:
            win.attributes("-alpha", alpha)
            win.after(50, fade, alpha - 0.05)

    # 延迟 duration 毫秒后开始淡出
    win.after(duration, fade)


def auto_close_message(title, message, timeout=2000):
    """显示提示窗口，timeout 毫秒后自动关闭"""
    win = tk.Toplevel()
    win.title(title)
    win.geometry("250x100+500+300")  # 可调整大小和位置
    win.resizable(False, False)
    tk.Label(win, text=message, padx=20, pady=20).pack(expand=True)

    # timeout 毫秒后关闭窗口
    win.after(timeout, win.destroy)

    # 窗口置顶
    win.attributes("-topmost", True)
    win.update()
    win.attributes("-topmost", False)


def open_editor_from_combobox(selected_code):
    """
    从 Combobox 获取选定的股票代码，并打开报警编辑器。
    """

    # 检查是否选择了有效的股票代码
    if selected_code:
        # 如果 Combobox 的值是 (代码, 名称) 形式的元组，需要提取代码
        if isinstance(selected_code, (list, tuple)) or len(selected_code.split()) == 2:
            code_to_edit = selected_code[0]
        # 如果 Combobox 的值已经是字符串代码
        else:
            code_to_edit = selected_code

        open_alert_editor(code_to_edit)
    else:
        # 提示用户选择一个股票代码
        auto_close_message("提示", "请先选择一个股票代码。")


def init_alert_window():
    width, height = 620,360
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    return width, height, x, y


default_deltas = {
    "价格": 1,   # 价格变动 0.1 元触发
    "涨幅": 1,   # 涨幅变动 0.2% 触发
    "量": 100      # 成交量增加 100 手触发
}


# def get_centered_window_position(win_width, win_height, x_root=None, y_root=None, parent_win=None):
#     """
#     计算窗口显示位置，优先考虑右键位置，其次父窗口，最后居中屏幕。
    
#     Args:
#         win_width (int): 窗口宽度
#         win_height (int): 窗口高度
#         x_root (int, optional): 鼠标点击 x 坐标
#         y_root (int, optional): 鼠标点击 y 坐标
#         parent_win (tk.Widget, optional): 父窗口对象

#     Returns:
#         tuple: (x, y) 窗口左上角位置
#     """
#     screen_width, screen_height = get_monitors_info()

#     # 默认居中
#     x = (screen_width - win_width) // 2
#     y = (screen_height - win_height) // 2

#     # --- 鼠标右键位置优先 ---
#     if x_root is not None and y_root is not None:
#         x, y = x_root, y_root
#         # 如果鼠标右侧空间不足，窗口翻到左侧
#         if x + win_width > screen_width:
#             x = max(0, x_root - win_width)

#     # --- 父窗口位置 ---
#     elif parent_win is not None:
#         parent_win.update_idletasks()
#         px, py = parent_win.winfo_x(), parent_win.winfo_y()
#         pw, ph = parent_win.winfo_width(), parent_win.winfo_height()

#         if px <= 1 or py <= 1:  # 父窗口未渲染，回退到居中
#             x = (screen_width - win_width) // 2
#             y = (screen_height - win_height) // 2
#         else:
#             x = px + pw // 2 - win_width // 2
#             y = py + ph // 2 - win_height // 2

#     # --- 边界检查 ---
#     x = max(0, min(x, screen_width - win_width))
#     y = max(0, min(y, screen_height - win_height))
#     logger.info(x,y)
#     return x, y

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

def get_centered_window_position(win_width, win_height, x_root=None, y_root=None, parent_win=None):
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
    logger.info(f'{x},{y}')
    return x, y

def open_rules_overview_sort_column(tv, col, reverse):
    l = [(tv.set(k, col), k) for k in tv.get_children('')]
    # 获取当前排序方向，如果未设置则默认为 False (升序)
    reverse_sort = sort_directions.get(col, False)
    try:
        # 尝试按数字排序
        l.sort(key=lambda t: float(t[0].replace(',', '')), reverse=not reverse_sort)
        sort_directions[col] = not reverse_sort
    except ValueError:
        # 按字符串排序
        l.sort(reverse=not reverse_sort)
        sort_directions[col] = not reverse_sort
    # 重排 Treeview
    for index, (_, k) in enumerate(l):
        tv.move(k, '', index)
    
    # 再次绑定列头点击事件，实现切换升序/降序
    tv.heading(col, command=lambda _col=col: open_rules_overview_sort_column(tv, _col, not reverse))

# # 存储每列的排序状态
# sort_states = {}

# def open_rules_overview_sort_column(tv, col, reverse):

#     reverse = sort_states.get(col, False)  # 获取当前列的排序状态
#     l = [(tv.set(k, col), k) for k in tv.get_children('')]
    
#     try:
#         # 尝试按数字排序
#         l.sort(key=lambda t: float(str(t[0]).replace(',', '')), reverse=reverse)
#     except ValueError:
#         # 按字符串排序
#         l.sort(reverse=reverse)
    
#     # 重排 Treeview
#     for index, (_, k) in enumerate(l):
#         tv.move(k, '', index)
    
#     # 切换下一次点击的排序状态
#     sort_states[col] = not reverse

#     # 再次绑定列头点击事件
#     tv.heading(col, command=lambda: open_rules_overview_sort_column(tv, col))

def open_rules_overview(parent_win=None):
    """查看所有已存档的报警规则"""
    global sina_data_df

    # 使用局部变量 aw_rules
    aw_rules = tk.Toplevel(parent_win or root)
    aw_rules.title("报警规则总览")
    aw_rules.withdraw()  # 先隐藏，避免闪到默认(50,50)


    frame = ttk.Frame(aw_rules)
    frame.pack(expand=True, fill="both")

    win_width, win_height = 700, 400
    x, y = get_centered_window_position(win_width, win_height, parent_win=parent_win)
    aw_rules.geometry(f"{win_width}x{win_height}+{x}+{y}")

    # 再显示出来
    aw_rules.deiconify()

    # 关键点：设置模态和焦点
    aw_rules.transient(parent_win)   # 父窗口关系
    # aw_rules.grab_set()              # 模态，阻止父窗口操作
    # aw_rules.focus_force()           # 强制获得焦点
    aw_rules.lift()                  # 提升到顶层

    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    # cols = ("代码", "名称", "规则名", "条件", "启用状态")
    # tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
    # scrollbar.config(command=tree.yview)

    # for c in cols:
    #     tree.heading(c, text=c)
    #     tree.column(c, width=220 if c == "条件" else 60, anchor="w" if c == "条件" else "center")
    # tree.pack(expand=True, fill="both")

    cols = ("代码", "名称", "规则名", "条件", "启用状态", "创建时间", "更新时间")
    tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
    scrollbar.config(command=tree.yview)

    for c in cols:
        if c in ( "创建时间", "更新时间"):
            width = 100 if c in ("条件", "规则名") else 100
            # tree.heading(c, text=c)
            tree.heading(c, text=c, anchor="center", 
                             command=lambda _c=c: open_rules_overview_sort_column(tree, _c, False))
            tree.column(c, width=width, anchor="w" if c in ("条件", "规则名") else "center")
        else:
            # width = 220 if c in ("条件", "规则名") else 800
            # tree.heading(c, text=c)
            tree.heading(c, text=c, anchor="center", 
                             command=lambda _c=c: open_rules_overview_sort_column(tree, _c, False))
            # tree.column(c, width=width, anchor="w" if c in ("条件", "规则名") else "center")
            tree.column(c, width=220 if c == "条件" else 60, anchor="w" if c == "条件" else "center")
    tree.pack(expand=True, fill="both")
    scrollbar.config(command=tree.yview)

    # 读取规则文件
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            alerts_rules_file = json.load(f)
    except:
        alerts_rules_file = {}

    tree.delete(*tree.get_children())

    # # 遍历规则，兼容旧版 list 和新版 dict

    # def iter_alerts(alerts):
    #     if isinstance(alerts, dict):
    #         for code, data in alerts.items():
    #             if isinstance(data, list):  # 旧版
    #                 yield code, data
    #             elif isinstance(data, dict):  # 新版
    #                 yield code, data.get("rules", [])
    #     elif isinstance(alerts, list):
    #         for item in alerts:
    #             code = item.get("stock_code", "UNKNOWN")
    #             rules = item.get("rules", [item])
    #             yield code, rules


    def iter_alerts(alerts):
        if isinstance(alerts, dict):
            for code, data in alerts.items():
                if isinstance(data, list):  # 旧版
                    yield code, data, {}
                elif isinstance(data, dict):  # 新版
                    yield code, data.get("rules", []), data.get("meta", {})
        elif isinstance(alerts, list):
            for item in alerts:
                code = item.get("stock_code", "UNKNOWN")
                rules = item.get("rules", [item])
                meta = item.get("meta", {})
                yield code, rules, meta


    # 遍历规则，兼容旧版 list 和新版 dict
    # for code, rule_list in iter_alerts(alerts_rules_file):
    for code, rule_list, meta in iter_alerts(alerts_rules_file):
        created_time_raw = meta.get("created_at", meta.get("updated_at", ""))
        updated_time_raw = meta.get("updated_at", meta.get("created_at", ""))

        # 转为 datetime 对象，再格式化为 "YYYY-MM-DD HH:MM"
        def format_time(t_str):
            try:
                dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d:%H")
            except:
                return t_str  # 若格式不对，则原样返回
        created_time = format_time(created_time_raw)
        updated_time = format_time(updated_time_raw)

        if sina_data_df is not None and not sina_data_df.empty:
            stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
        else:
            stock_name = monitor_windows.get(code, {}).get("stock_info", ["", "未知"])[1]

        if isinstance(rule_list, dict) and "rules" in rule_list:
            # meta = rule_list.get("meta", {})
            rules = rule_list.get("rules", [])
        else:
            # meta = {}
            rules = rule_list

        conditions = []
        enabled_states = []
        # created_times = []
        # updated_times = []

        # 只显示开启状态的规则名
        rule_names = []
        for rule in rules:
            field = rule.get("field")
            if field in ("价格", "量", "涨幅"):
                op = rule.get("op", "")
                value = rule.get("value", "")
                conditions.append(f"{field} {op} {value}")
                enabled = rule.get("enabled", False)
                enabled_states.append("开" if enabled else "关")
                # created_times.append(created_time)
                # updated_times.append(updated_time)
                if enabled:
                    rule_names.append(field)  # 仅加入已开启字段

        tree.insert("", "end", values=(
            code,
            stock_name,
            ", ".join(rule_names),                       # ✅ 显示已开启规则名
            ", ".join(conditions),
            "开" if all(e == "开" for e in enabled_states) else "关" if all(e=="关" for e in enabled_states) else "部分开",
            created_time,           # ✅ 直接使用字符串
            updated_time            # ✅ 直接使用字符串
        ))

            # ", ".join(created_time),
            # ", ".join(updated_time)

    # for code, rule_list in iter_alerts(alerts_rules_file):
    # # for code, rule_list in alerts_rules_file.items():
    #     # 安全取股票名称
    #     if sina_data_df is not None and not sina_data_df.empty:
    #         stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
    #     else:
    #         stock_name = monitor_windows.get(code, {}).get("stock_info", ["", "未知"])[1]

    #     # 提取规则名（只取字段名）
    #     rule_names = [rule.get("field", "") for rule in rule_list if rule.get("field") in ("价格", "量")]

    #     # 构造条件字符串
    #     conditions = []
    #     enabled_states = []
    #     for rule in rule_list:
    #         field = rule.get("field")
    #         if field in ("价格", "量", "涨幅"):
    #             op = rule.get("op", "")
    #             value = rule.get("value", "")
    #             conditions.append(f"{field} {op} {value}")
    #             enabled_states.append("开" if rule.get("enabled", False) else "关")

    #     if all(e == "开" for e in enabled_states):
    #         enabled_state = "开"
    #     elif all(e == "关" for e in enabled_states):
    #         enabled_state = "关"
    #     else:
    #         enabled_state = "部分开"

    #     # 插入 Treeview
    #     tree.insert("", "end", values=(
    #         code,
    #         stock_name,
    #         ", ".join(rule_names),
    #         ", ".join(conditions),
    #         enabled_state
    #     ))

    # 右键菜单
    def show_menu(event):
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        code = vals[0]
        menu = tk.Menu(aw_rules, tearoff=0)
        menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code, parent_win=aw_rules))
        menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True, parent_win=aw_rules))
        menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code))
        menu.post(event.x_root, event.y_root)

    def on_double_click_edit(event):
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        code = vals[0]
        open_alert_editor(code, parent_win=aw_rules)

    def on_tree_select(event):
        """处理表格行选择事件"""
        tree = event.widget
        # logger.info(f"事件来源: {tree}")
        selected_item = tree.selection()
        # logger.info(f'selected_item : {selected_item}')
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[0]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            # code_entry.delete(0, tk.END)
            # code_entry.insert(0, stock_code)
            
            # 2. 更新其他数据（示例）
            logger.info(f"选中股票代码: {stock_code}")
            time.sleep(0.1)
    
    def on_single_click(event):
        global code_entry
        # tree = event.widget
        tree = event.widget

        row_id = tree.identify_row(event.y)
        if not row_id:
            return
        vals = tree.item(row_id, "values")
        code = vals[0]
        name = vals[1]
        # logger.info(f'on_single_click sel : {row_id} vals : {vals}')
        send_to_tdx(code)
        # code_entry.delete(0, tk.END)
        # code_entry.insert(0, code)


    tree.bind("<Button-3>", show_menu)
    tree.bind("<Double-1>", on_double_click_edit)
    tree.bind("<<TreeviewSelect>>", on_tree_select)
    tree.bind("<Button-1>", on_single_click)
    # Esc 只关闭当前窗口
    aw_rules.bind("<Escape>", lambda event, w=aw_rules: w.destroy())

    return aw_rules




# ------------------------
# 报警中心窗口
# ------------------------
def alert_treeview_sort_column(col, reverse=False):
    global alert_tree, alert_sort_column, alert_sort_reverse

    try:
        # 记录排序规则
        alert_sort_column = col
        alert_sort_reverse = reverse

        # 取值并排序
        data_list = [(alert_tree.set(k, col), k) for k in alert_tree.get_children('')]

        # 数字优先排序
        try:
            data_list.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            data_list.sort(key=lambda t: t[0], reverse=reverse)

        # 移动排序后的行
        for index, (_, k) in enumerate(data_list):
            alert_tree.move(k, '', index)

        # 更新表头点击回调
        alert_tree.heading(col, command=lambda: alert_treeview_sort_column(col, not reverse))

        # 排序后固定滚动到顶部
        alert_tree.after(10, lambda: alert_tree.yview_moveto(0))

    except Exception as e:
        print(f"[Alert] 排序失败: {e}")

def open_alert_center():
    global alert_window, alert_tree
    global alert_moniter_bring_front,sina_data_df

    if alert_window and isinstance(alert_window, tk.Toplevel) and alert_window.winfo_exists():
        alert_window.lift()
        return



    alert_moniter_bring_front = True
    stock_code, stock_name, stock_info = None, None, None
    selected_item = tree.selection()
    if selected_item:
        vals = tree.item(selected_item, 'values')
        if len(vals) >= 2:
            stock_code = vals[1]
            stock_name = vals[2]
            stock_info = vals[1:]

    # 改用局部变量 aw_win
    aw_win = tk.Toplevel(root)
    aw_win.title("报警中心")
    aw_win.withdraw()  # 先隐藏，避免闪到默认(50,50)
    # aw_win.geometry("720x300")
    # 🔹 使用和 monitor 一样的自动记忆位置函数
    window_id = "alert_center"   # <<< 每个窗口一个唯一 ID

    update_position_window(aw_win, window_id)

    # 关键点：设置模态和焦点
    # aw_win.transient(root)   # 父窗口关系
    # aw_win.grab_set()              # 模态，阻止父窗口操作
    # aw_win.focus_force()           # 强制获得焦点
    aw_win.lift()                  # 提升到顶层

    # win_width, win_height = 720 , 300
    # x, y = get_centered_window_position_center(win_width, win_height, parent_win=root)
    # aw_win.geometry(f"{win_width}x{win_height}+{x}+{y}")
    # 再显示出来
    aw_win.deiconify()
    # 保持全局变量引用
    alert_window = aw_win

    
    # 上方快速规则入口
    top_frame = ttk.Frame(aw_win)
    top_frame.pack(fill="x", padx=5, pady=5)
    tk.Label(top_frame, text="股票代码:").pack(side="left")

    # 股票选择 Combobox 初始化
    stock_var = tk.StringVar()
    vlist = list(monitor_windows.keys())
    # bug 
    # stock_list_for_combo = [f"{co} {monitor_windows[co]['stock_info'][1]}" for co in vlist]
    stock_list_for_combo = []
    for co in vlist:
        info = monitor_windows.get(co)
        if not info:
            logger.info(f"[DEBUG] monitor_windows 没有 entry: {co}")
            stock_list_for_combo.append(f"{co} 无数据")
            continue

        stock_info = info.get("stock_info")
        if not stock_info or len(stock_info) < 2:
            logger.info(f"[DEBUG] monitor_windows[{co}] 缺少 stock_info: {info}")
            stock_list_for_combo.append(f"{co} 未初始化")
            continue

        stock_list_for_combo.append(f"{co} {stock_info[1]}")


    #1:
    # stock_list_for_combo = [
    #     f"{co} {monitor_windows.get(co, {}).get('stock_info',[None,'未知'])[1]}"
    #     for co in vlist
    # ]

    #2
    # stock_list_for_combo = []
    # for co in vlist:
    #     info = monitor_windows.get(co, {}).get("stock_info", None)
    #     if info and len(info) > 1:
    #         stock_list_for_combo.append(f"{co} {info[1]}")
    #     else:
    #         # 如果缺失，显示 code + "未知"
    #         stock_list_for_combo.append(f"{co} 未知")

    if stock_code and stock_code not in monitor_windows.keys():
        stock_list_for_combo.append(f"{stock_code} {stock_name}")
    stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=15)
    if stock_code:
        stock_var.set(f"{stock_code} {stock_name}")
    elif stock_list_for_combo:
        stock_var.set(stock_list_for_combo[0])
    stock_entry.pack(side="left", padx=5)

    # 按钮和规则管理
    tk.Button(top_frame, text="添加/编辑规则", command=lambda sv=stock_var: open_alert_editor(sv.get())).pack(side="left", padx=5)
    tk.Button(top_frame, text="规则管理", command=lambda w=aw_win: open_rules_overview(parent_win=w)).pack(side="left", padx=5)

    # 报警列表
    frame = ttk.Frame(aw_win)
    frame.pack(expand=True, fill="both")
    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    # cols = ("时间", "代码", "名称", "触发值", "规则", "变化量")
    cols = ("时间", "代码", "名称","次数",  "触发值", "规则", "变化量")
    alert_tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
    scrollbar.config(command=alert_tree.yview)
    for c in cols:
        alert_tree.heading(c, text=c, command=lambda col=c: alert_treeview_sort_column(col, False))
        if c == '触发值':
            alert_tree.column(c, width=160, anchor="center")
        elif c == '规则':
            alert_tree.column(c, width=100, anchor="center")
        else:
            alert_tree.column(c, width=30, anchor="center")
    alert_tree.pack(expand=True, fill="both")
    global after_id

    def reset_timer(event=None):
        """重置倒计时"""
        global after_id
        if after_id is not None:
            # logger.info(f'after_id : {after_id}')
            aw_win.after_cancel(after_id)
        # 重新启动 120 秒倒计时
        after_id = aw_win.after(120*1000, lambda w=aw_win: on_close_alert_monitor(w))
        logger.info("Timer reset due to user action")

    def on_tree_select(event):
        """处理表格行选择事件"""
        tree = event.widget
        # logger.info(f"事件来源: {tree}")
        selected_item = tree.selection()
        # logger.info(f'selected_item : {selected_item}')
        if selected_item:
            stock_info = tree.item(selected_item, 'values')
            stock_code = stock_info[1]
            stock_code = stock_code.zfill(6)
            send_to_tdx(stock_code)

            # 1. 推送代码到输入框
            code_entry.delete(0, tk.END)
            code_entry.insert(0, stock_code)
            
            # 2. 更新其他数据（示例）
            logger.info(f"选中股票代码: {stock_code}")
            time.sleep(0.1)
    
    def on_single_click_alert_center(event):
        global code_entry
        row_id = alert_tree.identify_row(event.y)
        if not row_id:
            return
        vals = alert_tree.item(row_id, "values")
        code = vals[1]
        name = vals[2]
        # logger.info(f'on_single_click sel : {row_id} vals : {vals}')
        send_to_tdx(code)
        code_entry.delete(0, tk.END)
        code_entry.insert(0, code)
        reset_timer()

    # 双击报警 → 聚焦监控窗口
    def on_double_click(event):
        global code_entry
        sel = alert_tree.selection()
        if not sel: return
        vals = alert_tree.item(sel[0], "values")
        code = vals[1]
        name = vals[2]
        # logger.info(f'on_double_click sel : {sel} vals : {vals}')
        send_to_tdx(code)
        code_entry.delete(0, tk.END)
        code_entry.insert(0, code)


        if code in monitor_windows.keys():
            win = monitor_windows[code]['toplevel']
        else:
            percent,price, vol = 0.0 , 0.0 , 0
            if sina_data_df is not None and not sina_data_df.empty:
                stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
                dd = sina_data_df.loc[code]
                if dd is not None:
                    price = dd.close
                    percent = round((dd.close - dd.llastp) / dd.llastp *100,1)
                    vol = round(dd.turnover/100/10000/100,1)
                    logger.info(f'监控窗口:{stock_code}, {price},{percent},{vol}')
                stock_info = [code, name, 0, 0, percent,price, vol]
            else:
                stock_info = [code, name, 0, 0, 0.0, 0.0, 0]
            win = create_monitor_window(stock_info)['toplevel']

        if win and win.winfo_exists():
            win.lift()
            win.attributes("-topmost", 1)
            win.attributes("-topmost", 0)
            highlight_window(win)


    # 右键菜单 → 编辑 / 新增 / 删除规则
    def show_menu(event):
        sel = alert_tree.selection()
        if not sel: return
        vals = alert_tree.item(sel[0], "values")
        code = vals[1]
        menu = tk.Menu(aw_win, tearoff=0)
        menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code, parent_win=aw_win, x_root=event.x_root, y_root=event.y_root))
        menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True, parent_win=aw_win, x_root=event.x_root, y_root=event.y_root))
        menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code))
        menu.post(event.x_root, event.y_root)

    alert_tree.bind("<<TreeviewSelect>>", on_tree_select)
    alert_tree.bind("<Double-1>", on_double_click)
    alert_tree.bind("<Button-3>", show_menu)
    alert_tree.bind("<Button-1>", on_single_click_alert_center)

    # Esc 只关闭当前 aw_win，不影响父窗口
    aw_win.bind("<Escape>", lambda e, w=aw_win: on_close_alert_monitor(w))
    aw_win.protocol("WM_DELETE_WINDOW", lambda w=aw_win: on_close_alert_monitor(w))
    # aw_win.after(120*1000,  lambda  w=aw_win: on_close_alert_monitor(w))
    # 启动初始倒计时
    after_id = aw_win.after(120*1000, lambda w=aw_win: on_close_alert_monitor(w))
    # 强制渲染
    aw_win.update_idletasks()
    aw_win.after(100, refresh_alert_center)

# def open_rules_overview_src(parent_win=None):
#     """查看所有已存档的报警规则"""
#     global sina_data_df
#     rules_win = tk.Toplevel(parent_win or root)
#     rules_win.title("报警规则总览")
#     # rules_win.geometry("680x400")

#     frame = ttk.Frame(rules_win)
#     frame.pack(expand=True, fill="both")

#     win_width, win_height = 680, 400
#     x, y = get_centered_window_position(win_width, win_height, x_root=None, y_root=None, parent_win=parent_win)
#     rules_win.geometry(f"{win_width}x{win_height}+{x}+{y}")


#     scrollbar = ttk.Scrollbar(frame)
#     scrollbar.pack(side="right", fill="y")

#     cols = ("代码", "名称", "规则名", "条件", "启用状态")
#     tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
#     scrollbar.config(command=tree.yview)

#     for c in cols:
#         tree.heading(c, text=c)
#         if c == "条件":
#             tree.column(c, width=180, anchor="w")
#         else:
#             tree.column(c, width=80, anchor="center")
#     tree.pack(expand=True, fill="both")


#     try:
#         with open(ALERTS_FILE, "r") as f:
#             alerts_rules_file = json.load(f)
#     except:
#         alerts_rules_file = []
#     # 填充数据

#     cols = ("代码", "名称", "规则名", "条件", "启用状态")
#     tree.delete(*tree.get_children())

#     for code, rule_list in alerts_rules_file.items():
#         # 安全取股票名称
#         if sina_data_df is not None and not sina_data_df.empty:
#             stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
#         else:
#             stock_name = monitor_windows.get(code, {}).get("stock_info", ["", "未知"])[1]

#         # 提取规则名（只取字段名）
#         rule_names = [rule.get("field", "") for rule in rule_list if rule.get("field") in ("价格", "量")]

#         # 构造条件字符串
#         conditions = []
#         enabled_states = []
#         for rule in rule_list:
#             field = rule.get("field")
#             if field in ("价格", "量" ,"涨幅"):
#                 op = rule.get("op", "")
#                 value = rule.get("value", "")
#                 conditions.append(f"{field} {op} {value}")
#                 enabled_states.append("开" if rule.get("enabled", False) else "关")

#         # 合并同一股票的启用状态，如果不一致可以显示“部分开”或者取第一个
#         if all(e == "开" for e in enabled_states):
#             enabled_state = "开"
#         elif all(e == "关" for e in enabled_states):
#             enabled_state = "关"
#         else:
#             enabled_state = "部分开"

#         # 插入 Treeview
#         tree.insert("", "end", values=(
#             code,
#             stock_name,
#             ", ".join(rule_names),      # 规则名合并
#             ", ".join(conditions),      # 条件合并
#             enabled_state
#         ))


#     # 右键菜单
#     def show_menu(event):
#         sel = tree.selection()
#         if not sel:
#             return
#         vals = tree.item(sel[0], "values")
#         code = vals[0]
#         menu = tk.Menu(rules_win, tearoff=0)
#         menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code, parent_win=rules_win))
#         menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True, parent_win=rules_win))
#         menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code, parent_win=rules_win))
#         menu.post(event.x_root, event.y_root)

#     def on_double_click_edit(event): 
#         sel = tree.selection()
#         if not sel:
#             return
#         vals = tree.item(sel[0], "values")
#         code = vals[0]
#         open_alert_editor(code,parent_win=rules_win)
#     tree.bind("<Button-3>", show_menu)
#     tree.bind("<Double-1>", on_double_click_edit)
#     rules_win.bind("<Escape>", lambda event: rules_win.destroy())

# def open_alert_center_src():
#     global alert_window, alert_tree
#     global alert_moniter_bring_front
#     if alert_window and alert_window.winfo_exists():
#         alert_window.lift()
#         return
#     alert_moniter_bring_front = True
#     stock_code,stock_name, stock_info = None, None,None
#     selected_item = tree.selection()
#     if selected_item:
#         vals = tree.item(selected_item, 'values')
#         if len(vals) >= 2:
#             stock_code = vals[1]
#             stock_name = vals[2]
#             stock_info = vals[1:]



#     alert_window = tk.Toplevel(root)
#     alert_window.title("报警中心")
#     # alert_window.geometry("720x360")
#     # # 获取之前保存的位置，如果没有则居中
#     # # pos = load_alert_window_position()  # 返回 (x, y, w, h) 或 None
#     # # if pos is None:
#     # #     w, h, x, y = init_alert_window()
#     # # else:
#     # #     x, y, w, h = pos
#     # w, h, x, y = init_alert_window()
#     # alert_window.geometry(f"{w}x{h}+{x}+{y}")
#     win_width, win_height = 720 , 360
#     x, y = get_centered_window_position(win_width, win_height, x_root=None, y_root=None, parent_win=root)
#     alert_window.geometry(f"{win_width}x{win_height}+{x}+{y}")



#     # 上方快速规则入口
#     top_frame = ttk.Frame(alert_window)
#     top_frame.pack(fill="x", padx=5, pady=5)

#     tk.Label(top_frame, text="股票代码:").pack(side="left")

#     # stock_var = tk.StringVar()
#     # vlist = list(monitor_windows.keys())

#     # stock_list_for_combo  = [tuple(monitor_windows[co]['stock_info'][:2])  for co in vlist]
#     # if stock_code and stock_code not in monitor_windows.keys():
#     #     stock_list_for_combo.append((stock_code,stock_name))
#     #     stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=10)
#     # else:
#     #     stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=10)

#     # def show_context_menu(event, stock_code):
#     #     parent_win = event.widget.winfo_toplevel()
#     #     menu = tk.Menu(parent_win, tearoff=0)
#     #     menu.add_command(
#     #         label="添加/编辑规则",
#     #         command=lambda: open_alert_editor(stock_code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root)
#     #     )
#     #     menu.post(event.x_root, event.y_root)

#     # -------------------------
#     # 股票选择 Combobox 初始化
#     # -------------------------
#     stock_var = tk.StringVar()
#     vlist = list(monitor_windows.keys())

#     # 统一 values 为字符串 "code name"
#     stock_list_for_combo = [f"{co} {monitor_windows[co]['stock_info'][1]}" for co in vlist]

#     # 如果选中的股票不在监控窗口中，加入列表
#     if stock_code and stock_code not in monitor_windows.keys():
#         stock_list_for_combo.append(f"{stock_code} {stock_name}")

#     # 创建 Combobox，限制宽度避免拉伸
#     stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=15)

#     # 设置初始值
#     if stock_code:
#         stock_var.set(f"{stock_code} {stock_name}")
#     elif stock_list_for_combo:
#         stock_var.set(stock_list_for_combo[0])  # 默认选第一个

#     stock_entry.pack(side="left", padx=5)

#     # 右键菜单或双击触发编辑规则
#     def show_context_menu(event):
#         selected = stock_var.get()
#         if not selected:
#             return
#         # 取 code 部分（前6-7位数字）
#         code = selected.split()[0]
#         parent_win = event.widget.winfo_toplevel()
#         menu = tk.Menu(parent_win, tearoff=0)
#         menu.add_command(
#             label="添加/编辑规则",
#             command=lambda: open_alert_editor(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root)
#         )
#         menu.post(event.x_root, event.y_root)

#     # stock_entry.bind("<Button-3>", show_context_menu)

#     tk.Button(top_frame, text="添加/编辑规则", command=lambda: open_alert_editor(stock_var.get())).pack(side="left", padx=5)
#     tk.Button(top_frame, text="规则管理", command=lambda: open_rules_overview(alert_window)).pack(side="left", padx=5)
#     # 报警列表
#     frame = ttk.Frame(alert_window)
#     frame.pack(expand=True, fill="both")

#     scrollbar = ttk.Scrollbar(frame)
#     scrollbar.pack(side="right", fill="y")

#     cols = ("时间", "代码", "名称", "触发值", "规则", "变化量")

#     alert_tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
#     scrollbar.config(command=alert_tree.yview)

#     for c in cols:
#         alert_tree.heading(c, text=c)
#         if c == '触发值':
#             alert_tree.column(c, width=120 , anchor="center")
#         elif c == '规则':
#             alert_tree.column(c, width=100 , anchor="center")
#         else:
#             alert_tree.column(c, width=40, anchor="center")
#     alert_tree.pack(expand=True, fill="both")



#     # 双击报警 → 聚焦监控窗口
#     def on_double_click(event):
#         global code_entry
#         sel = alert_tree.selection()
#         if not sel:
#             return

#         vals = alert_tree.item(sel[0], "values")
#         code = vals[1]
#         name = vals[2]

#         # 先发送 TDX 查询
#         send_to_tdx(code)
#         code_entry.delete(0, tk.END)
#         code_entry.insert(0, code)

#         if code in monitor_windows.keys():
#             win = monitor_windows[code]['toplevel']
        # else:
        #     # 构造 stock_info 填充默认值
        #     percent,price, vol = 0.0 , 0.0 , 0
        #     if sina_data_df is not None and not sina_data_df.empty:
        #         stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
        #         dd = sina_data_df.loc[code]
        #         if dd is not None:
        #             price = dd.close
        #             percent = round((dd.close - dd.llastp) / dd.llastp *100,1)
        #             amount = round(dd.turnover/100/10000/100,1)
        #             logger.info(f'监控窗口:{stock_code}, {price},{percent},{amount}')
        #         stock_info = [code, name, 0, 0, percent,price, amount]
        #     else:
        #         stock_info = [code, name, 0, 0, 0.0, 0.0, 0]
        #     window_info = create_monitor_window(stock_info)
        #     win = window_info['toplevel']

#         if win and win.winfo_exists():
#             win.lift()
#             win.attributes("-topmost", 1)
#             win.attributes("-topmost", 0)
#             highlight_window(win)


#     alert_tree.bind("<Double-1>", on_double_click)

#     # 右键菜单 → 编辑 / 新增 / 删除规则
#     def show_menu(event):
#         sel = alert_tree.selection()
#         parent_win = event.widget.winfo_toplevel()
#         if not sel: return
#         vals = alert_tree.item(sel[0], "values")
#         code = vals[1]
#         menu = tk.Menu(alert_window, tearoff=0)
#         menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
#         menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
#         menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
#         menu.post(event.x_root, event.y_root)
#     alert_tree.bind("<Button-3>", show_menu)
#     # 按 Esc 关闭窗口
#     alert_window.bind("<Escape>", lambda  event: on_close_alert_monitor(alert_window))
#     # 1小时后自动关闭（3600*1000 毫秒）
#     alert_window.protocol("WM_DELETE_WINDOW", lambda event: on_close_alert_monitor(alert_window))
#     # alert_window.after(120*1000,  lambda  event:on_close_alert_monitor(alert_window))

#     # 强制渲染一次，避免白屏
#     alert_window.update_idletasks()

#     # 延迟刷新（100ms 后执行，避免卡初始化）
#     alert_window.after(100, refresh_alert_center)


def get_alert_status(stock_code):
    rules = alerts_rules.get(stock_code, [])
    if not rules:
        return "未设计"  # 没有设计报警
    if any(rule.get("enabled", False) for rule in rules):
        return "开启"
    return "关闭"


def calc_alert_window_position(win_width, win_height, x_root=None, y_root=None, parent_win=None):
    """
    根据鼠标/父窗口位置，计算报警窗口在多屏环境下的显示位置
    """
    # 默认取主屏
    screen = get_monitor_by_point(0, 0)
    x = screen["left"] + (screen["width"] - win_width) // 2
    y = screen["top"] + (screen["height"] - win_height) // 2

    # --- 鼠标右键优先 ---
    if x_root is not None and y_root is not None:
        screen = get_monitor_by_point(x_root, y_root)
        x = x_root
        y = y_root
        if x + win_width > screen["right"]:
            x = max(screen["left"], x_root - win_width)
        if y + win_height > screen["bottom"]:
            y = max(screen["top"], y_root - win_height)

    # --- 父窗口位置 ---
    elif parent_win is not None:
        parent_win.update_idletasks()
        px = parent_win.winfo_x()
        py = parent_win.winfo_y()
        pw = parent_win.winfo_width()
        ph = parent_win.winfo_height()

        screen = get_monitor_by_point(px, py)
        if px <= 1 or py <= 1:  # 未渲染时 fallback
            x = screen["left"] + (screen["width"] - win_width) // 2
            y = screen["top"] + (screen["height"] - win_height) // 2
        else:
            x = px + pw // 2 - win_width // 2
            y = py + ph // 2 - win_height // 2

    # --- 边界检查 ---
    if x + win_width > screen["right"]:
        x = screen["right"] - win_width
    if y + win_height > screen["bottom"]:
        y = screen["bottom"] - win_height
    if x < screen["left"]:
        x = screen["left"]
    if y < screen["top"]:
        y = screen["top"]

    return x, y



def ensure_alert_rules(code, price, percent, vol, alerts_rules, alerts_history, default_deltas, new=False, master=None):
    """
    确保股票监控规则存在（新版结构支持 meta 信息）
    """
    # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d")
    existing = alerts_rules.get(code, None)

    # 🟢 如果是旧格式（list）
    if isinstance(existing, list):
        rules = existing
        meta = {
            "created_at": now,
            "updated_at": now,
            "created_price": float(price),
            "created_percent": float(percent),
            "created_vol": float(vol),
            "updated_price": float(price),
            "updated_percent": float(percent),
            "updated_vol": float(vol)
        }
    # 🟢 新格式（dict，包含meta和rules）
    elif isinstance(existing, dict):
        rules = existing.get("rules", [])
        meta = existing.get("meta", {})
        meta.setdefault("created_at", now)
        meta.setdefault("created_price", float(price))
        meta.setdefault("created_percent", float(percent))
        meta.setdefault("created_vol", float(vol))
    else:
        rules, meta = [], {
            "created_at": now,
            "updated_at": now,
            "created_price": float(price),
            "created_percent": float(percent),
            "created_vol": float(vol),
            "updated_price": float(price),
            "updated_percent": float(percent),
            "updated_vol": float(vol)
        }

    # ========== 🟡 情况1：请求新建或重置 ==========
    if new:
        reset = True
        if rules:  # 仅在已有规则时才弹窗确认
            msg = f"是否重置股票 {code} 的监控规则？\n（将恢复为仅价格开启的默认配置）"
            reset = messagebox.askyesno("确认重置规则", msg, parent=master)

        if reset:
            rules = [
                {"field": "价格", "op": ">=", "value": float(price), "enabled": True,  "delta": default_deltas["价格"]},
                {"field": "涨幅", "op": ">=", "value": float(percent), "enabled": False, "delta": default_deltas["涨幅"]},
                {"field": "量",   "op": ">=", "value": float(vol),    "enabled": False, "delta": default_deltas["量"]},
            ]
            meta.update({
                "created_at": now,
                "updated_at": now,
                "created_price": float(price),
                "created_percent": float(percent),
                "created_vol": float(vol),
                "updated_price": float(price),
                "updated_percent": float(percent),
                "updated_vol": float(vol)
            })
            alerts_rules[code] = {"meta": meta, "rules": rules}
            return rules

    # ========== 🟢 情况2：没有旧规则 ==========
    if not rules:
        rules = [
            {"field": "价格", "op": ">=", "value": float(price), "enabled": True,  "delta": default_deltas["价格"]},
            {"field": "涨幅", "op": ">=", "value": float(percent), "enabled": False, "delta": default_deltas["涨幅"]},
            {"field": "量",   "op": ">=", "value": float(vol),    "enabled": False, "delta": default_deltas["量"]},
        ]
        alerts_rules[code] = {"meta": meta, "rules": rules}
        return rules

    # ========== 🟢 情况3：已有规则，仅更新值 ==========
    for rule in rules:
        f = rule["field"]
        if f == "价格":
            rule["value"] = float(price)
            rule["delta"] = default_deltas["价格"]
        elif f == "涨幅":
            rule["value"] = float(percent)
            rule["delta"] = default_deltas["涨幅"]
        elif f == "量":
            rule["value"] = float(vol)
            rule["delta"] = default_deltas["量"]

    meta.update({
        "updated_at": now,
        "updated_price": float(price),
        "updated_percent": float(percent),
        "updated_vol": float(vol)
    })

    alerts_rules[code] = {"meta": meta, "rules": rules}
    return rules

def parse_stock_list(info):
    """
    安全解析 stock_info：
    格式：[code, name, x, x, percent, price, vol, ...]
    并将 '', None 自动转换成 0
    """
    
    def safe_num(v):
        """把 '', ' ', None 转成 0，并确保能转成 float"""
        if v is None or v == '' or v == ' ':
            return 0
        try:
            return float(v)
        except:
            return 0

    code = info[0]
    name = info[1]

    percent = safe_num(info[4] if len(info) > 4 else 0)
    price   = safe_num(info[5] if len(info) > 5 else 0)
    vol     = safe_num(info[6] if len(info) > 6 else 0)

    return code, name, percent, price, vol



def open_alert_editor(stock_code, new=False,stock_info=None,parent_win=None, x_root=None, y_root=None):
    global alerts_rules,alert_window
    # ------------------ 数据处理 ------------------
    # 简化数据获取，使其能正常运行
    # --- 1. 准备规则 ---
    # orig_rules = alerts_rules.get(code, [])
    global sina_data_df
    orig_rules = alerts_rules.copy()

    price, percent, vol = 5.0, 1.0, 1
    if new and stock_info is not None:
        if stock_code in alerts_rules.keys():
            del alerts_rules[stock_code]
        logger.info(f'stock_info:{stock_info}')
        code, name, *_ , percent,price, vol = stock_info
        if price < 0.1:
            # 优先从 sina_data_df 获取最新行情
            if sina_data_df is not None and not sina_data_df.empty and code in sina_data_df.index:
                # stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
                dd = sina_data_df.loc[code]
                price = dd.close
                percent = round((dd.close - dd.llastp) / dd.llastp * 100, 1)
                vol = round(dd.turnover / 100 / 10000 / 100, 1)
            # 如果 sina_data_df 无数据，则从 monitor_windows 获取已有 stock_info
            elif code in monitor_windows:
                stock_info = monitor_windows[code].get('stock_info', [code, name, 0, 0, 0.0, 0.0, 0])
                _, _, _, _, percent, price, vol = stock_info
            # 如果都没有，使用默认值
        # code, name, *_ , percent,price, vol = stock_info

    elif not stock_code == '':
        try:
            # logger.info(f'2:{stock_info[-3]}')
            if stock_info is not None:
                code, name, *_ , percent,price, vol = stock_info
            # 如果 stock_code 是字符串，格式 "CODE NAME"
            elif not isinstance(stock_code, (list, tuple)) and len(stock_code.split()) == 2:
                code, name = stock_code.split()
                # percent, price, vol = 0.0, 0.0, 0

                # 优先从 sina_data_df 获取最新行情
                if sina_data_df is not None and not sina_data_df.empty and code in sina_data_df.index:
                    # stock_name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
                    dd = sina_data_df.loc[code]
                    price = dd.close
                    percent = round((dd.close - dd.llastp) / dd.llastp * 100, 1)
                    vol = round(dd.turnover / 100 / 10000 / 100, 1)

                # 如果 sina_data_df 无数据，则从 monitor_windows 获取已有 stock_info
                elif code in monitor_windows:
                    stock_info = monitor_windows[code].get('stock_info', [code, name, 0, 0, 0.0, 0.0, 0])
                    _, _, _, _, percent, price, vol = stock_info

                # 如果都没有，使用默认值
                else:
                    # stock_name = name
                    percent, price, vol = 0.0, 0.0, 0

            elif isinstance(stock_code, (list, tuple)) and len(stock_code) == 5:
                code, _ , percent,price, vol = stock_code
                logger.info(f'price : {price},percent:{percent}, vol:{vol}')

            elif isinstance(stock_code, (list, tuple)) and len(stock_code) >= 7:
                code, name, percent, price, vol = parse_stock_list(stock_code)
            else:
                code = stock_code
                stock_info = monitor_windows.get(code, {}).get('stock_info', [code, 0, 0, 0, 1, 5, 1])
                code, name, percent, price, vol = parse_stock_list(stock_info)
                if percent == 0 or price == 0:
                    if code in monitor_windows.keys():
                        stock_info = monitor_windows.get(code, {}).get('stock_info', [code, 0, 0, 0, 1, 5, 1])
                        _, _, _, _, percent,price, vol = stock_info
            if float(vol) == 0.0:
                vol = 0.8
        except (ValueError, IndexError):
            # 处理可能的解包错误
            code = stock_code
    else:
        toast_message(alert_window, "请先选择一个股票代码。")
        return
    # -------------------------------------------------------------
    logger.info(f'code: {code}')
    send_to_tdx(code)


    if parent_win is None:
        parent_win = root  # 默认主窗口


    editor = tk.Toplevel(root)
    editor.title(f"设置报警规则 -{name} {code}")
    editor.withdraw()  # 先隐藏，避免闪到默认(50,50)

    # 关键点：设置模态和焦点
    # editor.transient(parent_win)   # 父窗口关系
    # editor.grab_set()              # 模态，阻止父窗口操作
    # editor.focus_force()           # 强制获得焦点
    editor.lift()                  # 提升到顶层

    win_width, win_height = 500, 300
    x, y = get_centered_window_position_center(win_width, win_height, parent_win=parent_win)
    editor.geometry(f"{win_width}x{win_height}+{x}+{y}")
    # screen_width, screen_height = get_monitors_info()
    # 再显示出来
    editor.deiconify()

    editor.geometry(f"{win_width}x{win_height}+{x}+{y}")
    editor.title(f"设置报警规则 - {name} {code}")


    # 统一风格
    style = ttk.Style()
    style.configure("TButton", padding=5)
    style.configure("TLabel", padding=5)

    # rules = alerts_rules.get(code)
    rule_entry = alerts_rules.get(code, {})
    if isinstance(rule_entry, dict):
        rules = rule_entry.get("rules", [])
    else:
        rules = rule_entry or []


    # if not rules or new:
    #     # 若没有已有规则，创建默认新规则：
    #     rules = [
    #         {"field": "价格", "op": ">=", "value": float(price), "enabled": True,  "delta": default_deltas["价格"]},
    #         {"field": "涨幅", "op": ">=", "value": float(percent),"enabled": False, "delta": default_deltas["涨幅"]},
    #         {"field": "量",   "op": ">=", "value": float(vol),    "enabled": False, "delta": default_deltas["量"]},
    #     ]
    #     alerts_rules[code] = rules

    if not rules or new:
        # now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_str = datetime.now().strftime("%Y-%m-%d")
        # 创建默认规则
        rules = [
            {"field": "价格", "op": ">=", "value": float(price), "enabled": True,  "delta": default_deltas["价格"]},
            {"field": "涨幅", "op": ">=", "value": float(percent),"enabled": False, "delta": default_deltas["涨幅"]},
            {"field": "量",   "op": ">=", "value": float(vol),    "enabled": False, "delta": default_deltas["量"]},
        ]
        # 新版格式：同时添加 meta
        alerts_rules[code] = {
            "meta": {
                "created_at": now_str,
                "updated_at": now_str,
                "created_price": float(price),
                "created_percent": float(percent),
                "created_vol": float(vol),
                "updated_price": float(price),
                "updated_percent": float(percent),
                "updated_vol": float(vol)
            },
            "rules": rules
        }



    # 创建一个 Frame 来容纳规则列表
    rules_frame = ttk.Frame(editor, padding=10)
    rules_frame.pack(fill=tk.BOTH, expand=True)

    entries = []

    def validate_float(P):
        if P == "":  # 允许空
            return True
        # 允许类似 "-", "2.", "-3."
        P = P.replace("．", ".")  # 替换全角点
        try:
            float(P)
            return True
        except ValueError:
            return False

    vcmd = rules_frame.register(validate_float)

    def make_adjust_fn(val_var, pct):
        return lambda: val_var.set(round(val_var.get() * (1 + pct), 2))

    def add_rule(field="价格", op=">=", value=0.0, enabled=True, delta=1):
        if delta is None:
            delta = default_deltas.get(field, 0.5)

        row = len(entries)

        # 启用/禁用
        enabled_var = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(rules_frame, variable=enabled_var).grid(row=row, column=0, padx=2)

        # 字段选择
        field_var = tk.StringVar(value=field)
        ttk.Combobox(rules_frame, textvariable=field_var,
                     values=["价格", "涨幅", "量"], width=10).grid(row=row, column=1, padx=2)

        # 操作符选择
        op_var = tk.StringVar(value=op)
        ttk.Combobox(rules_frame, textvariable=op_var,
                     values=[">=", "<="], width=5).grid(row=row, column=2, padx=2)



        # 值输入
        val_var = tk.DoubleVar(value=value)
        # val_var = tk.StringVar(value=value)
        ttk.Spinbox(rules_frame, textvariable=val_var, from_=-100, to=100,
                    increment=0.1, width=10,validate="key",validatecommand=(vcmd, "%P")).grid(row=row, column=3, padx=2)


        def get_limit_price(stock_code, last_close):
            """
            stock_code: '600001', '300123', '688888'
            last_close: 昨日收盘价
            返回 (涨停价, 跌停价)
            """
            code = str(stock_code)
            pct_up = 0.1  # 默认 10%
            
            if code.startswith('688') or code.startswith('8'):  # 科创板 / 8开头
                pct_up = 0.2
            elif code.startswith('300'):  # 创业板
                pct_up = 0.1
            elif code.startswith('430'):  # 北交所
                pct_up = 0.3

            # 计算涨跌停
            limit_up = round(last_close * (1 + pct_up), 2)
            limit_down = round(last_close * (1 - pct_up), 2)
            return limit_up, limit_down


        # 根据字段设置按钮文本和增量
        if field_var.get() == "价格":
            plus_delta, minus_delta = 0.01, -0.01  # 百分比
            plus_text, minus_text = "+1%", "-1%"
        elif field_var.get() == "涨幅":
            plus_delta, minus_delta = 1, -1
            plus_text, minus_text = "+1", "-1"
        elif field_var.get() == "量":
            plus_delta, minus_delta = 0.5, -0.5
            plus_text, minus_text = "+0.5", "-0.5"

        # 调整函数
        def make_adjust_fn(val_var, delta, is_percent=False):
            def fn():
                try:
                    val = float(val_var.get())
                    if is_percent:
                        val = round(val * (1 + delta), 2)
                    else:
                        val = round(val + delta, 2)
                    val_var.set(val)
                except:
                    pass
            return fn

        # 创建按钮
        ttk.Button(rules_frame, text=minus_text, width=5,
                   command=make_adjust_fn(val_var, minus_delta, field_var.get()=="价格")).grid(row=row, column=4)
        ttk.Button(rules_frame, text=plus_text, width=5,
                   command=make_adjust_fn(val_var, plus_delta, field_var.get()=="价格")).grid(row=row, column=5)

        # delta 输入
        delta_var = tk.DoubleVar(value=delta)
        # delta_var = tk.StringVar(value=delta)
        ttk.Spinbox(rules_frame, textvariable=delta_var, from_=-10.01, to=100,
                    increment=0.1, width=8,validate="key",validatecommand=(vcmd, "%P")).grid(row=row, column=6, padx=5)

        entries.append({
            "field_var": field_var,
            "op_var": op_var,
            "val_var": val_var,
            "enabled_var": enabled_var,
            "delta_var": delta_var
        })

    # 保存时同步到每条规则
    # def save_rule():
    #     new_rules = []
    #     for entry in entries:
    #         new_rules.append({
    #             "field": entry["field_var"].get(),
    #             "op": entry["op_var"].get(),
    #             "value": entry["val_var"].get(),
    #             "enabled":entry["enabled_var"].get(),
    #             "delta": entry["delta_var"].get()
    #         })
    #     alerts_rules[code] = new_rules
    #     save_alerts()
    #     toast_message(alert_window, f"{code} 报警规则已保存")
    #     editor.destroy()
    def save_rule():
        new_rules = []
        for entry in entries:
            new_rules.append({
                "field": entry["field_var"].get(),
                "op": entry["op_var"].get(),
                "value": entry["val_var"].get(),
                "enabled": entry["enabled_var"].get(),
                "delta": entry["delta_var"].get()
            })

        # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.now().strftime("%Y-%m-%d")
        meta = {
            "updated_at": now,
            "updated_price": float(price),
            "updated_percent": float(percent),
            "updated_vol": float(vol)
        }

        existing = alerts_rules.get(code, {})
        if isinstance(existing, dict) and "meta" in existing:
            meta = {**existing["meta"], **meta}

        alerts_rules[code] = {"meta": meta, "rules": new_rules}
        save_alerts()
        toast_message(alert_window, f"{code} 报警规则已保存")
        editor.destroy()


    def del_rule():

        if code in alerts_rules.keys():
            logger.info(f"删除规则: {alerts_rules[code]}")
            del alerts_rules[code]

        # 删除 entries 里的控件（逐一销毁 UI）
        for entry in entries:
            for widget in entry.get("widgets", []):  # widgets 存放该行的 Spinbox/Button/Checkbutton 等
                widget.destroy()
        entries.clear()
        save_alerts()
        toast_message(alert_window, f"{code} 所有规则已删除")
        # 关闭规则编辑窗口
        editor.destroy()
    # 渲染已有规则
    for rule in rules:
        add_rule(
            field=rule.get("field", "价格"),
            op=rule.get("op", ">="),
            value=rule.get("value", 0.0),
            enabled=rule.get("enabled", True),
            delta=rule.get("delta", default_deltas.get(rule.get("field", "价格"), 0.5))
        )

    def cancel_rule():
        global alerts_rules
        alerts_rules = orig_rules
        editor.destroy()
    # 控制按钮区域

    button_frame = ttk.Frame(editor, padding=(10, 5))
    button_frame.pack(fill=tk.X)
    
    ttk.Button(button_frame, text="保存", command=save_rule).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="添加规则", command=lambda: add_rule()).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="删除规则", command=lambda: del_rule()).pack(side=tk.RIGHT, padx=5)
    ttk.Button(button_frame, text="取消", command=lambda: cancel_rule()).pack(side=tk.RIGHT, padx=5)
    editor.protocol("WM_DELETE_WINDOW", lambda: cancel_rule())
    # 按 Esc 关闭窗口
    editor.bind("<Escape>", lambda event: cancel_rule())

    return editor

def refresh_alert_rules_ui(stock_code):
    """
    刷新监控中心规则显示，并在每条规则旁边添加开关，
    控制报警启用状态
    """
    rules = alerts_rules.get(stock_code, [])
    # 先清空树
    for item in alert_tree.get_children():
        alert_tree.delete(item)

    for i, rule in enumerate(rules):
        # 创建 BooleanVar 与 rule['enabled'] 绑定
        var = BooleanVar(value=rule.get('enabled', True))

        # 切换开关时更新 rule['enabled']
        def toggle_rule(var=var, rule=rule):
            rule['enabled'] = var.get()
            logger.info(f"{rule['field']} 开关状态: {rule['enabled']}")

        # 在 Treeview 中插入规则信息
        alert_tree.insert("", "end", iid=f"{stock_code}_{i}",
                          values=(rule['field'], rule['op'], rule['value']))

        # 在 Treeview 指定列添加 Checkbutton 控件
        chk = Checkbutton(alert_tree, variable=var, command=toggle_rule)
        # 假设 column=3 是开关列
        alert_tree.window_create(f"{stock_code}_{i}", column=3, window=chk)


def get_rules(code):
    r = alerts_rules.get(code)
    if not r:
        return []
    if isinstance(r, dict) and "rules" in r:
        return r["rules"]
    elif isinstance(r, list):
        return r
    return []
# -----------------------------
# 检查单只股票是否触发报警
# -----------------------------
# 全局 set，存放所有已经插入过的警报（防止重复插入）
inserted_alert_keys = set()

def check_alert(stock_code, price, change, volume, name=None):
    """
    检查股票是否触发报警规则，并使用冷却机制。
    delta 用于判断最小变化量触发报警。
    """
    global alerts_rules, alerts_history, alerts_buffer, monitor_windows, last_alert_times
    global inserted_alert_keys,ALERT_COOLDOWN
    if stock_code not in alerts_rules.keys():
        return  # 无规则直接返回

    # 有监控窗口才检查开关
    if stock_code in alerts_enabled and not alerts_enabled[stock_code].get():
        return

    if name is None:
        name = monitor_windows.get(stock_code, {}).get('stock_info', [stock_code, ''])[1]

    val_map = {'价格': price, '涨幅': change, '量': volume}
    
    # for rule in alerts_rules[stock_code]:
    for rule in get_rules(stock_code):
        if not rule.get('enabled', True):
            continue

        field = rule['field']
        val = val_map.get(field)
        if val is None:
            continue  # 数据缺失就跳过

        # 计算变化量 delta
        last_val_key = (stock_code, field)
        last_val = last_alert_times.get(last_val_key, {}).get('last_val', None)
        delta_threshold = rule.get('delta', 0)

        # 如果有上一次的值，检查变化量
        if last_val is not None:
            if abs(val - last_val) < delta_threshold:
                continue  # 未达到变化量阈值，不触发

        # 计算触发状态
        triggered = (rule['op'] == '>=' and val >= rule['value']) or (rule['op'] == '<=' and val <= rule['value'])
        status_text = f"{field} {rule['op']} {rule['value']}"

        key = (stock_code, field, rule['op'], rule['value'])
        now = datetime.now()
        last_time = last_alert_times.get(key, {}).get('time')

        # 冷却判断
        if last_time and (now - last_time).total_seconds() < ALERT_COOLDOWN:
            # alerts_buffer.append({
            #     'time': now.strftime('%H:%M:%S'),
            #     'stock_code': stock_code,
            #     'name': name,
            #     'field': field,
            #     'value': val,
            #     'delta': abs(val - last_val) if last_val is not None else 0,
            #     'status': status_text,
            #     'rule': rule
            # })
            continue

        if triggered:
            # 生成唯一键用于去重（你也可以加 name、delta 等）
            unique_key = f"{now.strftime('%H:%M:%S')}-{stock_code}-{status_text}"

            # --- 如果之前已经插入过，不再插入 ---
            if unique_key in inserted_alert_keys:
                continue  
            # logger.info(f'unique_key: {unique_key}')
            # --- 标记为已插入 ---
            inserted_alert_keys.add(unique_key)

            # 记录报警时间和最新值
            last_alert_times[key] = {'time': now, 'last_val': val}
            last_alert_times[last_val_key] = {'time': now, 'last_val': val}

            alert_entry = {
                'time': now.strftime('%H:%M:%S'),
                'stock_code': stock_code,
                'name': name,
                'field': field,
                'value': val,
                'delta': abs(val - last_val) if last_val is not None else 0,
                'status': status_text,
                'rule': rule
            }

            alerts_history.append(alert_entry)
            alerts_buffer.append(alert_entry)

            # 高亮监控窗口
            if stock_code in monitor_windows:
                win = monitor_windows[stock_code]['toplevel']
                flash_title(win, stock_code, name)
                highlight_window(win)


# -----------------------------
# 刷新报警中心
# -----------------------------
# def refresh_alert_center():
#     global alert_window, alert_tree, alerts_history
#     if not alert_window or not alert_window.winfo_exists() or alert_tree is None:
#         return

#     alert_tree.delete(*alert_tree.get_children())
#     alert_tree.tag_configure("triggered", background="yellow", foreground="red")
#     alert_tree.tag_configure("not_triggered", background="white", foreground="black")

#     # 保持最新在最后一行（alerts_history append -> 最新在末尾）
#     rows = alerts_history[-200:]
#     logger.info(f'rows: {row}')
#     last_iid = None
#     base_counter = len(alerts_history)  # 用作 iid 前缀的一部分，保证在多次刷新时不会重复

#     for idx, alert in enumerate(rows):
#         field = alert.get("field", "")
#         value = alert.get("value", "")
#         rule = alert.get("rule", {}) or {}
#         delta = rule.get("delta", "")
#         op = rule.get("op", "")
#         rule_value = rule.get("value", "")

#         triggered = False
#         try:
#             if op == ">=" and value >= rule_value:
#                 triggered = True
#             elif op == "<=" and value <= rule_value:
#                 triggered = True
#         except Exception:
#             triggered = False

#         status = "触发" if triggered else "未触发"
#         vals = (
#             alert.get('time', ''),
#             alert.get('stock_code', ''),
#             alert.get('name', ''),
#             f"{field}{op}{rule_value} → {status}",
#             f"现值 {value}",
#             f"变化量 {delta}"
#         )
#         tag = "triggered" if triggered else "not_triggered"

#         # 生成唯一 iid（可换成 stock_code+time 等更语义化的 id）
#         iid = f"alert_{base_counter}_{idx}"
#         logger.info(f'iid= {iid}, values={vals}, tags={tag}')
#         alert_tree.insert("", "end", iid=iid, values=vals, tags=(tag,))
#         last_iid = iid

#     # 强制渲染完成
#     try:
#         alert_window.update_idletasks()
#     except Exception:
#         pass

#     # 在下一个事件循环再选中最后一行（确保任何可能的排序/回调已执行）
#     def _select_last():
#         try:
#             children = alert_tree.get_children()
#             if not children:
#                 return

#             # 如果 last_iid 在 children 中，用它；否则退回到 children[-1]
#             target = last_iid if (last_iid and last_iid in children) else children[-1]

#             # 先清除旧选择，然后设置选中、焦点并滚动到可见
#             try:
#                 alert_tree.selection_remove(alert_tree.selection())
#             except Exception:
#                 pass
#             alert_tree.selection_set(target)
#             alert_tree.focus(target)
#             alert_tree.see(target)

#             # **（可选）调试输出，确认选中行与显示一致**
#             # logger.info("SELECTED IID:", target, "VALUES:", alert_tree.item(target).get("values"))
#         except Exception:
#             pass

#     try:
#         alert_window.after(0, _select_last)
#     except Exception:
#         _select_last()

def refresh_alert_center():
    global alert_window, alert_tree, alerts_history, alerts_rules, sina_data_df, monitor_windows
    if not alert_window or not alert_window.winfo_exists() or alert_tree is None:
        return

    # 清空并设置 tag
    alert_tree.delete(*alert_tree.get_children())
    alert_tree.tag_configure("triggered", background="yellow", foreground="red")
    alert_tree.tag_configure("not_triggered", background="white", foreground="black")

    # 取最近若干条记录（按时间倒序），按股票分组，保留每个股票的最近记录序列
    recent = alerts_history[-500:]
    
    # # 取最近 500 条记录
    # recent_raw = alerts_history[-500:]
    # # 去重
    # seen_keys = set()
    # recent = []
    # for alert in recent_raw:
    #     unique_key = f"{alert['time']}-{alert['stock_code']}-{alert.get('status', '')}"
    #     if unique_key not in seen_keys:
    #         seen_keys.add(unique_key)
    #         recent.append(alert)

    grouped = {}
    for alert in reversed(recent):
        code = alert.get("stock_code", "")
        if not code:
            continue
        grouped.setdefault(code, []).append(alert)

    # ---- 按报警次数排序（次数多的排前） ----
    sorted_items = sorted(grouped.items(), key=lambda kv: len(kv[1]), reverse=True)

    # for code, alerts in grouped.items():
    for code, alerts in sorted_items:
        # 股票名称（优先用 sina_data_df）
        if sina_data_df is not None and not sina_data_df.empty:
            name = sina_data_df.get("name", pd.Series(dtype=object)).get(code, "未知")
        else:
            name = monitor_windows.get(code, {}).get("stock_info", ["", "未知"])[1]

        # 取该股的规则列表（可能为空）
        # rule_list = alerts_rules.get(code, [])
        rule_list = alerts_rules.get(code, {}).get("rules", [])
        if not rule_list:
            continue

        # --- 提取每个字段的最近现值（只保留第一次出现，即最近一次） ---
        latest_values = {}
        for alert in alerts:
            f = alert.get("field", "")
            if f and f not in latest_values:
                latest_values[f] = alert.get("value", "")

        # --- 构造“规则”列（阈值/操作，三合一） ---
        conds = []
        get_rules(stock_code)
        for rule in rule_list:
            field = rule.get("field", "")
            if field in ("价格", "涨幅", "量"):
                op = rule.get("op", "")
                value = rule.get("value", "")
                conds.append(f"{field}{op}{value}")
        rule_str = ", ".join(conds) if conds else "无规则"

        val_parts = []
        triggered = False
        for rule in rule_list:
            field = rule.get("field", "")
            if field not in ("价格", "涨幅", "量"):
                continue

            # 获取该字段最新值
            cur = None
            for alert in alerts:
                if alert.get("field") == field:
                    cur = alert.get("value")
                    break
            if cur is None:
                continue

            try:
                curf = float(cur)
                cur_s = f"{curf:.1f}"
            except Exception:
                cur_s = str(cur)
                curf = None

            # 判定是否触发
            rule_enabled = rule.get("enabled", False)
            try:
                if rule_enabled and curf is not None:
                    rv = float(rule.get("value", float("nan")))
                    op = rule.get("op", "")
                    is_triggered = (
                        (op == ">=" and curf >= rv) or
                        (op == "<=" and curf <= rv)
                    )
                    if is_triggered:
                        triggered = True
                        val_parts.append(f"{field}{cur_s}")  # 只显示触发的值
            except Exception:
                continue

        val_str = ", ".join(val_parts) if val_parts else ""

        # --- 启用状态（开 / 部分开 / 关） ---
        enabled_state = (
            "开" if all(rule.get("enabled", False) for rule in rule_list)
            else "部分开" if any(rule.get("enabled", False) for rule in rule_list)
            else "关"
        )

        # 使用该股票最近一条记录的时间作为时间列（若没有可为空）
        time_txt = alerts[0].get("time", "")

        # 插入一行：时间, 代码, 名称, 规则(三合一), 触发值(三合一精简), 启用状态
        alert_count = len(alerts)
        # logger.info(f'alerts:{alerts}')
        vals = (
            time_txt,
            code,
            name,
            alert_count,   # 新列
            rule_str,
            val_str,
            enabled_state
        )
        tag = "triggered" if triggered else "not_triggered"
        alert_tree.insert("", "end", values=vals, tags=(tag,))

    # 选中第一行以便展示
    if alert_tree.get_children():
        first_item = alert_tree.get_children()[0]
        alert_tree.selection_set(first_item)
        alert_tree.focus(first_item)

    alert_window.update_idletasks()


# def refresh_alert_center_old_ok():
#     global alert_window, alert_tree, alerts_history
#     if not alert_window or not alert_window.winfo_exists() or alert_tree is None:
#         return

#     alert_tree.delete(*alert_tree.get_children())
#     alert_tree.tag_configure("triggered", background="yellow", foreground="red")
#     alert_tree.tag_configure("not_triggered", background="white", foreground="black")

#     # 确保最新在最后一行
#     rows = list(reversed(alerts_history[-200:]))

#     for alert in rows:
#         field = alert.get("field", "")
#         value = alert.get("value", 0)
#         rule = alert.get("rule", {}) or {}
#         delta = rule.get("delta", "")
#         op = rule.get("op", "")
#         rule_value = rule.get("value", "")

#         triggered = False
#         try:
#             if op == ">=" and value >= rule_value:
#                 triggered = True
#             elif op == "<=" and value <= rule_value:
#                 triggered = True
#         except Exception:
#             triggered = False

#         status = "触发" if triggered else "未触发"
#         vals = (
#             alert.get('time', ''),
#             alert.get('stock_code', ''),
#             alert.get('name', ''),
#             f"{field}{op}{rule_value} → {status}",
#             f"现值 {value}",
#             f"变化量 {delta}"
#         )
#         tag = "triggered" if triggered else "not_triggered"
#         alert_tree.insert("", "end", values=vals, tags=(tag,))

#     if alert_tree.get_children():
#         first_item = alert_tree.get_children()[0]
#         alert_tree.selection_set(first_item)
#         alert_tree.focus(first_item)

#     alert_window.update_idletasks()

    # children = alert_tree.get_children()
    # if children:
    #     last_item = children[-1]  # 真正的最后一行
    #     def _select_last():
    #         try:
    #             alert_tree.selection_set(last_item)
    #             alert_tree.focus(last_item)
    #             alert_tree.see(last_item)
    #         except Exception:
    #             pass
    #     # 延迟 50ms，保证滚动条和行索引同步
    #     alert_window.after(0, _select_last)


flushing = False    # 全局变量，防止多次执行
# 全局 set，存放所有已经插入过的警报（防止重复插入）
# 全局：
# inserted_alert_keys = set()
# flushing = False

def flush_alerts():
    """定时刷新报警缓冲区，将 alerts_buffer 写入 alerts_history，然后用 refresh_alert_center 刷新 Treeview"""
    global alerts_buffer, alerts_history, alert_tree
    global flushing, inserted_alert_keys

    if flushing:
        return
    flushing = True

    try:
        # 计算下次执行时间
        next_execution_time = get_next_weekday_time(9, 20)
        now = datetime.now()
        delay_ms = int((next_execution_time - now).total_seconds() * 1000)

        if alerts_buffer:
            # 打开窗口（不要在这里创建新的 tree）
            open_alert_center()

            # ---- 本批次去重 ----
            batch_seen = set()
            unique_alerts = []
            for alert in alerts_buffer:
                # 使用和 check_alert 保持一致的唯一键（time-stock-status 或 stock-status）
                # 用 alert['time']（报警时间字符串）更稳；如果你想按同一分钟合并，也可改为只用 stock+status
                unique_key = f"{alert.get('time','')}-{alert.get('stock_code','')}-{alert.get('status','')}"
                if unique_key in batch_seen:
                    continue
                batch_seen.add(unique_key)

                # 若你还想避免跨批次重复（长期重复），可以检查 inserted_alert_keys
                if unique_key in inserted_alert_keys:
                    # 已插入过（历史中），跳过
                    continue

                # 标记为已见（长期去重集合）
                inserted_alert_keys.add(unique_key)

                unique_alerts.append(alert)

            # ---- 将去重后的 alerts 写入历史（不直接插入 Treeview）----
            for alert in unique_alerts:
                alerts_history.append(alert)

            # 清空缓冲
            alerts_buffer = []

            # ---- 由 refresh_alert_center 统一负责刷新 Treeview（聚合/计数/排序） ----
            try:
                refresh_alert_center()
            except Exception as e:
                logger.exception(f"刷新报警中心失败: {e}")

        # 安排下次执行
        if (get_day_is_trade_day() and get_now_time_int() < 1505) or get_work_time():
            root.after(30000, flush_alerts)
        else:
            root.after(delay_ms, flush_alerts)

    finally:
        flushing = False

# def flush_alerts():
#     """定时刷新报警缓冲区，将 alerts_buffer 写入报警中心"""
#     global alerts_buffer, alerts_history,alert_tree
#     global flushing,inserted_alert_keys

#     if flushing:
#         return  # 正在执行，不重复触发
#     flushing = True

#     try:
#         next_execution_time = get_next_weekday_time(9, 20)
#         now = datetime.now()
#         delay_ms = int((next_execution_time - now).total_seconds() * 1000)

#         # 打开窗口（必须确保不会重复创建 tree）
#         if alerts_buffer:

#             open_alert_center()  # 只打开，不创建新的 treeview

#             for alert in alerts_buffer:
#                 if alert_tree:
#                     delta = alert.get('rule', {}).get('delta', 0)
#                     tag = "triggered" if "触发" in alert.get("status", "") else "not_triggered"

#                     vals = (
#                         alert['time'],
#                         alert['stock_code'],
#                         alert['name'],
#                         alert['status'],
#                         f"现值 {alert.get('value', '')}",
#                         f"变化量 {delta}"
#                     )
#                     alert_tree.insert("", "end", values=vals, tags=(tag,))
#                 # 生成唯一键用于去重（你也可以加 name、delta 等）
#                 unique_key = f"{alert['time']}-{alert['stock_code']}-{alert['status']}"

#                 # --- 如果之前已经插入过，不再插入 ---
#                 if unique_key in inserted_alert_keys:
#                     continue  
#                 # logger.info(f'unique_key: {unique_key}')
#                 # --- 标记为已插入 ---
#                 alerts_history.append(alert)

#             alerts_buffer = []

#         # 下次调度
#         if (get_day_is_trade_day() and get_now_time_int() < 1505) or get_work_time():
#             root.after(30000, flush_alerts)
#         else:
#             root.after(delay_ms, flush_alerts)
#     finally:
#         flushing = False

def get_latest_valid_data(df):
    # 确保时间字段是可排序的
    df = df.copy()
    if "时间" in df.columns:
        df["时间"] = pd.to_datetime(df["时间"], format="%H:%M:%S", errors="coerce")

        # 过滤掉无效数据（价格=0 且 涨幅=0 且 量=0 的行）
        df_valid = df[~((df["价格"] == 0) & (df["涨幅"] == 0) & (df["量"] == 0))]

        # 每个股票取最后一条有效数据
        latest_df = df_valid.sort_values("时间").groupby("代码").tail(1)
        return latest_df
    else:
        return pd.dataframe()

def format_next_time(delay_ms):
    """把 root.after 的延迟时间转换成 %H:%M 格式"""
    delay_sec = delay_ms / 1000
    target_time = datetime.now() + timedelta(seconds=delay_sec)
    return target_time.strftime("%H:%M")

def trigger_monitor_flash(win_dict, flash_times=6, interval=300):
    """
    对 monitor 窗口执行闪屏报警
    """
    win = win_dict.get('toplevel')
    if not win or not win.winfo_exists():
        return
    # def _flash(count=0):
    #     if not win.winfo_exists() or count >= flash_times:
    #         try:
    #             win.configure(bg="SystemButtonFace")
    #         except Exception:
    #             pass
    #         return

    #     try:
    #         bg = win.cget("bg")
    #         win.configure(bg="red" if bg != "red" else "SystemButtonFace")
    #     except Exception:
    #         return

    #     win.after(interval, _flash, count + 1)
    logger.info(f'highlight_window : {win_dict.get("stock_info")[0]}')
    highlight_window(win,alter_tdx=True)
    # _flash()


def check_monitor_break_high4(monitor_windows: dict,df: pd.DataFrame,logger):
    """
    从 monitor_windows 中读取 stock_code
    判断 close > high4
    触发对应 monitor 窗口闪屏报警
    """

    if df is None or df.empty:
        return

    for win in monitor_windows.values():
        info = win.get("stock_info")
        if not info:
            continue

        stock_code = info[0]
        if not stock_code:
            continue

        stock_code = stock_code.zfill(6)

        if stock_code not in df.index:
            continue

        row = df.loc[stock_code]

        close = row.get(filterclose)
        high4 = row.get(filterhigh4)

        if close is None or high4 is None:
            logger.error(f'stock_code_close : {close} high4:{high4}')
            continue
        # logger.info(f'stock_code_close : {close} high4:{high4}')

        if close > high4:
            logger.info(
                f"[MONITOR_ALERT] {stock_code} close={close} > high4={high4}"
            )
            trigger_monitor_flash(win)


def refresh_all_stock_data():
    # 假设 get_all_stock_data 返回 DataFrame 或 dict
    global loaded_df,realdatadf
    global alerts_buffer,start_init,alerts_rules 
    next_execution_time = get_next_weekday_time(9, 20)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)
    sina_realtime_status = False
    df = _get_sina_data_realtime()
    
    if df is not None and not df.empty:
        data = df
        sina_realtime_status = True
        _tdx_df = _get_tdx_data_df()
        # ② 只取 high4 列
        if 'high4' not in _tdx_df.columns:
            logger.error(f'high4 not in _tdx_df count:{len(_tdx_df)}')

        else:
            high4_df = _tdx_df[['high4']]
            # ③ 合并到 sina_data_df
            if data is not None and not data.empty:
                data = data.join(high4_df, how='left')
        check_monitor_break_high4(monitor_windows=monitor_windows,df=data, logger=logger)
        for stock_code, row in data.iterrows():
            if stock_code  in alerts_rules.keys():
                price = row.close
                name = row['name']
                percent = round((row.close - row.llastp) / row.llastp *100,1)
                amount = round(row.turnover/100/10000/100,1)
                logger.debug(f'sina_data-check_alert:{stock_code} {name}')
                check_alert(stock_code, price, percent, amount , name)

    elif loaded_df is not None and not loaded_df.empty:
        data = loaded_df.copy()  # 每只股票：code, price, change, volume
    elif realdatadf is not None and not realdatadf.empty:
        data = realdatadf.copy()
    else:
        data = _get_stock_changes()
        if data is not None and not data.empty:
            if '涨幅' not in data.columns:
                data = process_full_dataframe(data)
            data = get_latest_valid_data(data)
            for _, row in data.iterrows():
                stock_code = row["代码"]
                if stock_code  in alerts_rules.keys():
                    # if stock_code == '603083':
                    #     import ipdb;ipdb.set_trace()
                    name = row["名称"]
                    price = row["价格"]
                    change = row["涨幅"]
                    volume = row["量"]
                    # 调用你的报警检查
                    if not sina_realtime_status:
                        check_alert(stock_code, price, change, volume,name)

    # 刷新报警中心显示
    flush_alerts()
    # 10 分钟后再次执行

    if get_work_time() or (get_day_is_trade_day() and 1130 < get_now_time_int() < 1300):
        if not 1130 < get_now_time_int() < 1300:
            delay_ms = 60 * 1000
            root.after(delay_ms, refresh_all_stock_data)
            status_label2.config(text=f"alert刷新 {format_next_time(delay_ms)}")
        else:
            delay_ms = int(minutes_to_time(1300)) * 60 * 1000  # 单位：秒
            root.after(delay_ms , refresh_all_stock_data)
            status_label2.config(text=f"午休刷新 {format_next_time(delay_ms)}")
    else:
        root.after(delay_ms, refresh_all_stock_data)
        status_label2.config(text=f"非交易刷新 {format_next_time(delay_ms)}")


    # if (get_day_is_trade_day() and get_now_time_int() < 1505) or get_work_time() or (start_init == 0 ):
    #     root.after(60*1000, refresh_all_stock_data)
    # else:
    #     root.after(delay_ms, refresh_all_stock_data)

# def refresh_alert_centerlist():
#     """刷新报警中心UI"""
#     global alerts_buffer, alert_center_listbox

#     if not alert_center_listbox:
#         return

#     alert_center_listbox.delete(0, tk.END)

#     for alert in alerts_buffer[-100:]:  # 只显示最近 100 条
#         time_str = alert.get('time', '')
#         code = alert.get('stock_code', '')
#         name = alert.get('name', '')
        
#         # ✅ 优先用 status 字段（规则 + 当前值 + 触发/未触发）
#         status = alert.get('status')
#         if not status:
#             # 兼容旧数据
#             field = alert.get('field', '')
#             op = alert.get('rule', {}).get('op', '')
#             value = alert.get('rule', {}).get('value', '')
#             cur_val = alert.get('value', '')
#             if field and op and value != '':
#                 status = f"{field}{op}{value} (当前 {cur_val})"
#             else:
#                 status = "未知规则"

#         display_text = f"[{time_str}] {code} {name} → {status}"
#         alert_center_listbox.insert(tk.END, display_text)


# ------------------------
# 状态存储
# ------------------------
last_status = {}   # {(code, field, op): bool}
last_values = {}   # {(code, field, op): float}

def check_condition(code, field, op, threshold, current_val, delta):
    """
    判断是否触发报警
    - 阈值跨越触发
    - 持续满足但变化超过 delta 时触发
    """
    key = (code, field, op)

    satisfied = eval(f"{current_val} {op} {threshold}")
    prev = last_status.get(key, False)
    last_status[key] = satisfied

    if satisfied and not prev:
        last_values[key] = current_val
        return True

    if satisfied and prev:
        last_val = last_values.get(key, threshold)
        if abs(current_val - last_val) >= delta:
            last_values[key] = current_val
            return True

    return False



def delete_alert_rule(code):
    global alerts_rules
    if code in alerts_rules.keys():
        del alerts_rules[code]
        save_alerts()
        # messagebox.showinfo("删除规则", f"{code} 的规则已删除")
        toast_message(None, f"{code} 所有规则已删除")

def bind_hotkeys(root):
    """绑定快捷键"""
    root.bind("<F6>", lambda e: rearrange_monitors_per_screen())
    logger.info("✅ 已绑定 F6：一键重排列窗口")


def read_hdf_table(fname, key='all', columns=None, timeout=10):
    """
    精简读取 PyTables HDF5 文件的表格数据，只读，返回 DataFrame，带文件锁。

    Parameters
    ----------
    fname : str
        HDF5 文件路径
    key : str
        表名（HDF5 group key）
    columns : list, optional
        指定列读取，默认读取全部
    timeout : int
        文件锁超时时间（秒）
    
    Returns
    -------
    pd.DataFrame
        表格数据
    """

    def safe_load_table(store, table_name, chunk_size=1000,MultiIndex=False,complib='blosc'):
        """
        尝试读取 HDF5 table，如果读取失败，则逐块读取。
        返回 DataFrame。
        """
        try:
            # 直接读取整个 table
            df = store[table_name]
            df = df[~df.index.duplicated(keep='first')]
            return df
        except tables.exceptions.HDF5ExtError as e:
            log.error(f"{table_name} read error: {e}, attempting chunked read...")
            # 逐块读取
            dfs = []
            start = 0
            while True:
                try:
                    storer = store.get_storer(table_name)
                    if not storer.is_table:
                        raise RuntimeError(f"{table_name} is not a table format")
                    df_chunk = store.select(table_name, start=start, stop=start+chunk_size)
                    if df_chunk.empty:
                        break
                    dfs.append(df_chunk)
                    start += chunk_size
                except tables.exceptions.HDF5ExtError:
                    # 跳过损坏块
                    logger.error(f"Skipping corrupted chunk {start}-{start+chunk_size}")
                    start += chunk_size
            if dfs:
                df = pd.concat(dfs)
                df = df[~df.index.duplicated(keep='first')]
                # rebuild_table(store, table_name, df, MultiIndex=MultiIndex, complib=complib)
                return df
            else:
                logger.error(f"All chunks of {table_name} are corrupted")
                return pd.DataFrame()

    def rebuild_table(store, table_name, new_df,MultiIndex=False,complib='blosc'):
        """
        删除旧 table 并重建
        """
        # with SafeHDFStore(fname, mode='a') as store:
        if '/' + table_name in store.keys():
            log.error(f"Removing corrupted table {table_name}")
            store.remove(table_name)
        if not new_df.empty:
            # store.put(table_name, new_df, format='table',complib=complib, data_columns=True)
            if not MultiIndex:
                store.put(table_name, new_df, format='table', append=False, complib=complib, data_columns=True)
            else:
                store.put(table_name, new_df, format='table', index=False, complib=complib, data_columns=True, append=False)
            store.flush()

    # if not key.startswith('/'):
    #     key = '/' + key

    lock_path = fname + ".lock"
    lock = FileLock(lock_path, timeout=timeout)
    df = None
    try:
        with lock:
            # 使用 pandas 只读方式打开 HDF5
            with pd.HDFStore(fname, mode='r') as store:
                if store is not None:
                    logger.debug(f"fname: {(fname)} keys:{store.keys()}")
                    print(f"fname: {(fname)} keys:{store.keys()}")
                    if '/' + key in list(store.keys()):
                        df = safe_load_table(store, key, chunk_size=5000,MultiIndex=False,complib='blosc')
                        if df.empty:
                            log.info(f"{key} : table is corrupted, will rebuild after fetching new data")
                # if key not in h5.keys():
                #     logger.info(f"表不存在: {key}")
                #     return None
                # df = h5[key]
                # if columns is not None:
                #     df = df[columns]
                        return df

    except Timeout:
        logger.info(f"HDF 文件被占用，获取锁超时: {fname}")
    except FileNotFoundError:
        logger.info(f"文件不存在: {fname}")
    except KeyError:
        logger.info(f"表不存在: {key}")
    except Exception as e:
        logger.info(f"HDF 读取出错: {e}")
    finally:
        return df

# def read_hdf_table(fname, key='all', columns=None):
#     """
#     精简读取 PyTables HDF5 文件的表格数据，只读，返回 DataFrame。
    
#     Parameters
#     ----------
#     fname : str
#         HDF5 文件路径
#     key : str
#         表名（HDF5 group key）
#     columns : list, optional
#         指定列读取，默认读取全部
    
#     Returns
#     -------
#     pd.DataFrame
#         表格数据
#     """

#     # 自动确保 key 以 '/'
#     if not key.startswith('/'):
#         key = '/' + key

#     try:
#         _lock = fname + ".lock"
#         with SafeHDFStore(fname, mode='r') as h5:
#             if h5 is None:
#                 logger.info(f"HDF文件无法读取（锁定或不存在）: {fname}")
#                 return None
#             if key not in h5.keys():
#                 logger.info(f"表不存在: {key}")
#                 return None
#             df = h5[key]  # 读取整个表
#             if columns is not None:
#                 df = df[columns]

#             return df

#     except FileNotFoundError:
#         logger.info(f"文件不存在: {fname}")
#         return None
#     except KeyError:
#         logger.info(f"表不存在: {key}")
#         return None
#     except Exception as e:
#         logger.info(f"HDF读取出错: {e}")
#         return None

def parse_args():
    parser = argparse.ArgumentParser(description="Monitor Init Script")
    parser.add_argument(
        "--log",
        type=str,
        default="INFO",
        help="日志等级，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    return parser.parse_args()

def setup_logger(level_name: str):
    level = getattr(logging, level_name.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("app.log", encoding="utf-8")
        ]
    )

# logger = init_logging(log_file='monitor_dfcf.log',redirect_print=True)
# # logger = init_logging(log_file='monitor_dfcf.log',redirect_print=False)
if __name__ == "__main__":
    # args = parse_args()
    # setup_logger(args.log)


    # parser = argparse.ArgumentParser()
    # parser.add_argument("--log", default="INFO", help="日志等级 DEBUG/INFO/WARNING/ERROR")
    # args = parser.parse_args()

    # # 转换等级
    # level = getattr(logging, args.log.upper(), logging.INFO)

    # # 使用你自定义的 init_logging
    # logger = init_logging(log_file='monitor_dfcf.log', redirect_print=False, level=level)


    args = parse_args()  # 解析命令行参数
    level = getattr(logging, args.log.upper(), logging.INFO)

    # 直接用自定义的 init_logging，传入日志等级
    # logger = init_logging(log_file='monitor_dfcf.log', redirect_print=False, level=level)
    logger.setLevel(level)
    

    logger.info("程序启动…")

    check_hdf5()
    init_monitors()
    root = tk.Tk()
    root.title("股票异动数据监控")
    root.geometry("750x550")
    root.minsize(300,400)    # 设置最小尺寸限制

    root.resizable(True, True)

    # 配置样式
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Treeview", 
        background="white", 
        foreground="black", 
        rowheight=25,
        fieldbackground="white",
        font=('Microsoft YaHei', 9)
    )
    style.configure("Treeview.Heading", 
        font=('Microsoft YaHei', 10, 'bold'),
        background="#4a6984",
        foreground="white",
        relief="flat"
    )
    style.map("Treeview", background=[('selected', '#3478bf')])

    style.configure('TCombobox', arrowsize=16)




    # Toolbar
    toolbar = tk.Frame(root, bg="#f0f0f0", padx=2, pady=2)
    toolbar.pack(fill=tk.X)

    # Left frame: Refresh + Date
    frame_left = tk.Frame(toolbar, bg="#f0f0f0")
    frame_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

    refresh_btn = tk.Button(frame_left, text="↻ Refresh", command=refresh_data,
                            font=('Microsoft YaHei', 10), bg="#5b9bd5", fg="white",
                            padx=5, pady=2, relief="flat")
    refresh_btn.pack(side=tk.LEFT, padx=2)

    date_label = tk.Label(frame_left, text="Date:", font=('Microsoft YaHei', 10), bg="#f0f0f0")
    date_label.pack(side=tk.LEFT, padx=2)

    date_entry = DateEntry(frame_left, width=12, background='darkblue', foreground='white', borderwidth=1,
                           font=('Microsoft YaHei', 10))
    date_entry.pack(side=tk.LEFT, padx=2)
    date_entry.bind("<<DateEntrySelected>>", on_date_selected)

    # Right frame: Checkbuttons
    frame_right = tk.Frame(toolbar, bg="#f0f0f0")
    frame_right.pack(side=tk.RIGHT, padx=2, pady=2)

    # Variables
    tdx_var = tk.BooleanVar(value=True)
    ths_var = tk.BooleanVar(value=True)
    dfcf_var = tk.BooleanVar(value=False)
    uniq_var = tk.BooleanVar(value=False)
    sub_var = tk.BooleanVar(value=False)
    win_var = tk.BooleanVar(value=False)
    checkbuttons_info = [
        ("TDX", tdx_var),
        ("THS", ths_var),
        ("DC", dfcf_var),
        ("Uniq", uniq_var),
        ("Sub", sub_var),
        ("Win", win_var)
    ]

    for text, var in checkbuttons_info:
        cb = tk.Checkbutton(frame_right, text=text, variable=var, command=update_linkage_status,
                            bg="#f0f0f0", font=('Microsoft YaHei', 9),
                            padx=0, pady=0,  # 内部填充设为0
                            bd=0, highlightthickness=0)  # 边框也设为0
        cb.pack(side=tk.LEFT, padx=1)  # 外部间距减小到1像素
    # Frame
    type_frame = tk.LabelFrame(root, text="异动类型选择", font=('Microsoft YaHei', 9),
                               padx=3, pady=3, bg="#f9f9f9")
    type_frame.pack(fill=tk.X,padx=3, pady=3)

    # stock_types list
    stock_types = [
        "火箭发射","高开5日线","向上缺口","封涨停板", "60日新高", "快速反弹",   
        "大笔买入","竞价上涨",  "60日大幅上涨", "有大买盘","加速下跌", "打开跌停板", 
        "高台跳水", "大笔卖出", "封跌停板", "打开涨停板", "有大卖盘", "竞价下跌", 
        "低开5日线", "向下缺口", "60日新低", "60日大幅下跌"
    ]



    # Radio variable
    type_var = tk.StringVar(value="")

    radio_container = tk.Frame(type_frame, bg="#f9f9f9")
    radio_container.pack(fill=tk.BOTH, expand=True)

    # Store buttons
    buttons = []
    for stock_type in stock_types:
        btn = tk.Radiobutton(
            radio_container, 
            text=stock_type, 
            variable=type_var, 
            value=stock_type,
            command=search_by_type,
            font=('Microsoft YaHei', 8),
            bg="#f9f9f9",
            activebackground="#e6f3ff",
            padx=5, pady=2
        )
        buttons.append(btn)

    # 初始显示，避免初始化宽度问题
    for i, btn in enumerate(buttons):
        btn.grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)


    width = radio_container.winfo_width()
    if width <= 1:
        cols = 5  # 初始化时默认5列
    else:
        # 估算每个按钮的宽度，包括 padx
        btn_width = 110  
        # 计算列数，约束最少5列，最多10列
        cols = width // btn_width
        # logger.info(f'cols:{cols}')
        if cols < 5:
            cols = 5
        elif cols > 11:
            cols = 11

    # 清空布局
    for btn in buttons:
        btn.grid_forget()

    # 重新布局
    for i, btn in enumerate(buttons):
        row, col = divmod(i, cols)
        btn.grid(row=row, column=col, sticky=tk.W, padx=5, pady=3)

    # 列权重
    for c in range(cols):
        radio_container.grid_columnconfigure(c, weight=1)
            
    # # 创建搜索框和按钮
    search_frame = tk.Frame(root, bg="#f0f0f0", padx=10, pady=10)
    search_frame.pack(fill=tk.X, padx=10)

    tk.Label(search_frame, text="股票代码搜索:", font=('Microsoft YaHei', 9), 
            bg="#f0f0f0").pack(side=tk.LEFT, padx=(0, 5))

    code_entry = tk.Entry(search_frame, width=10, font=('Microsoft YaHei', 9))
    code_entry.pack(side=tk.LEFT, padx=5)
    code_entry.bind("<KeyRelease>", on_code_entry_change)
    code_entry.bind("<Return>", search_by_code)
    code_entry.bind("<Button-3>", right_click_paste)

    search_btn = tk.Button(search_frame, text="搜索", command=lambda: search_by_code(onclick=True), 
                          font=('Microsoft YaHei', 9), bg="#5b9bd5", fg="white",
                          padx=12, pady=2, relief="flat")
    search_btn.pack(side=tk.LEFT, padx=2)

    clear_btn = tk.Button(search_frame, text="清空", 
                         command=clear_code_entry,
                         font=('Microsoft YaHei', 9), 
                         padx=2, pady=2)
    clear_btn.pack(side=tk.LEFT, padx=2)
    clear_btn = tk.Button(search_frame, text="清除", 
                         command=lambda: [type_var.set(""), search_by_type()],
                         font=('Microsoft YaHei', 9), 
                         padx=2, pady=2)
    clear_btn.pack(side=tk.RIGHT, padx=2)

    btn_rearrange = tk.Button(search_frame, text="重排", command=rearrange_monitors_per_screen,font=('Microsoft YaHei', 9), 
                         padx=2, pady=2)
    btn_rearrange.pack(side=tk.RIGHT,pady=2)

    archive_loader_btn=tk.Button(search_frame, text="存档", command=open_archive_loader,font=('Microsoft YaHei', 9), 
                         padx=2, pady=2)
    archive_loader_btn.pack(side=tk.RIGHT,pady=2)

    


    # 创建Treeview组件和滚动条
    columns = ('时间', '代码', '名称','count', '异动类型', '涨幅', '价格', '量')
    tree_frame = tk.Frame(root)
    tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    for col in columns:
        tree.heading(col, text=col, command=lambda c=col: sort_treeview(tree, c, False))
        # if col in ['涨幅', '价格', '量','count']:
        if col in ['涨幅', '量','count']:
            tree.column(col, width=30, anchor=tk.CENTER, minwidth=20)
        elif col in ['价格']:
            tree.column(col, width=40, anchor=tk.CENTER, minwidth=30)
        elif col in ['异动类型']:
            tree.column(col, width=100, anchor=tk.CENTER, minwidth=60)
        else:
            tree.column(col, width=60, anchor=tk.CENTER, minwidth=30)
        # tree.column(col, width=120, anchor=tk.CENTER)


    # 布局
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    tree_frame.grid_rowconfigure(0, weight=1)
    tree_frame.grid_columnconfigure(0, weight=1)

    # 绑定选择事件
    tree.bind("<<TreeviewSelect>>", on_tree_select)



    # 添加键盘快捷键
    root.bind("<F5>", lambda event: refresh_data())
    root.bind("<Control-r>", lambda event: refresh_data())

    # 设置你希望任务每天执行的时间（例如：每天 23:00）
    target_hour = 15
    target_minute = 5


    # 底部容器
    bottom_frame = tk.Frame(root, bg="#f0f0f0")
    bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

    # 左边状态栏
    left_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
    left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

    status_var = tk.StringVar(value="Ready | Waiting...")
    status_label1 = tk.Label(left_frame, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W, bg="#f0f0f0", padx=5, pady=2)
    status_label1.pack(fill=tk.X, expand=True)

    # 右边任务状态
    right_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
    right_frame.pack(side=tk.RIGHT)

    status_label2 = tk.Label(right_frame, text=f"Daily task at {target_hour:02d}:{target_minute:02d}", font=('Microsoft YaHei', 10), bg="#f0f0f0")
    status_label2.pack(side=tk.LEFT, padx=5)

    status_label3 = tk.Label(right_frame, text="Update every 5 minutes", font=('Microsoft YaHei', 10), bg="#f0f0f0")
    status_label3.pack(side=tk.LEFT, padx=5)

    # 初始加载数据
    root.after(100, lambda: populate_treeview())

    load_alerts()

    # 保存上次打开的股票和时间
    last_open_times = {}
    # 保存已经打开的编辑窗口引用
    open_editors = {}

    def update_gui(stock_info):
        global last_open_times, open_editors

        if not isinstance(stock_info, dict):
            return

        code = stock_info.get("code")
        if not code:
            return

        name = stock_info.get("name")
        percent = stock_info.get("percent")
        price = stock_info.get("price")
        vol = stock_info.get("volume")
        high = stock_info.get("high", None)
        lastp1d = stock_info.get("lastp1d", None)
        stock_tuple = (code, name, high, lastp1d, percent, price, vol)
        logger.info(f"stock_code : {code} name : {name} percent : {percent} price : {price} vol : {vol}")

        # --- ① 检查防抖（1秒内不重复打开） ---
        now = time.time()
        last_time = last_open_times.get(code, 0)
        if now - last_time < 1.0:
            logger.info(f"[防抖] 阻止重复打开: {code}")
            return
        last_open_times[code] = now

        # --- ② 检查是否已有打开窗口 ---
        if code in open_editors:
            win = open_editors[code]
            if win and win.winfo_exists():
                try:
                    win.lift()
                    win.focus_force()
                    logger.info(f"[提示] 已存在编辑窗口，聚焦: {code}")
                except Exception as e:
                    logger.info(f"[警告] 聚焦失败: {e}")
                return
            else:
                # 如果记录存在但窗口已关闭，则清理
                open_editors.pop(code, None)

        # --- ③ 打开新编辑窗口 ---
        code_entry.delete(0, tk.END)
        code_entry.insert(0, code)
        search_by_code()

        win = open_alert_editor(code, new=True, stock_info=stock_tuple, parent_win=root)

        # --- ④ 保存窗口引用 ---
        if win and hasattr(win, "winfo_exists"):
            open_editors[code] = win

            # 当窗口关闭时自动清除记录
            def _on_close(c=code, w=win):
                if c in open_editors:
                    open_editors.pop(c, None)
                try:
                    w.destroy()
                except Exception:
                    pass

            win.protocol("WM_DELETE_WINDOW", _on_close)

    # # 定义回调函数，用于线程安全更新 GUI
    # def update_gui(stock_info):
    #     # label_main.config(text=f"已接收: {code}")
    #     # label_last.config(text=f"最后接收: {code}")
    #     # 1. 推送代码到输入框
    #     # logger.info(f'code : {stock_info}')
    #     # search_by_code()
    #     # if stock_info and stock_info is not None:
    #     global last_open_times
    #     if not isinstance(stock_info, dict):
    #         return

    #     code = stock_info.get("code")
    #     name = stock_info.get("name")
    #     percent = stock_info.get("percent")
    #     price = stock_info.get("price")
    #     vol = stock_info.get("volume")
    #     # 补齐 7 列
    #     high = stock_info.get("high", None)
    #     lastp1d = stock_info.get("lastp1d", None)
    #     stock_tuple = (code, name, high, lastp1d, percent, price, vol)
    #     logger.info(f'stock_code : {stock_code} name : {name} percent : {percent} price : {price} vol : {vol}')

    #     # --- 防抖逻辑 ---
    #     now = time.time()
    #     last_time = last_open_times.get(code, 0)
    #     if now - last_time < 3.0:  # 小于1秒不再重复打开
    #         logger.info(f"[防抖] 已阻止重复打开编辑器: {code}")
    #         return
    #     last_open_times[code] = now
    #     # 更新输入框
    #     code_entry.delete(0, tk.END)
    #     code_entry.insert(0, code)
    #     search_by_code()
    #     # code_entry.event_generate("<Return>")
    #     # 打开编辑器
    #     open_alert_editor(stock_code,new=True, stock_info=stock_tuple,parent_win=root)


    # 启动命名管道服务器线程
    t = threading.Thread(target=pipe_server, args=(lambda code: root.after(0, lambda: update_gui(code)),), daemon=True)
    t.start()

    # if get_now_time_int() > 1530 and not date_write_is_processed:
    #     start_async_save()

    tree.bind("<Button-3>", show_context_menu)

    context_menu = tk.Menu(root, tearoff=0)
    context_menu.add_command(label="添加到监控", command=add_selected_stock)
    context_menu.add_command(label="打开报警中心", command=lambda: open_alert_center())


    #初始化窗口位置
    load_window_positions()
    update_position_window(root,"main")

    process_queue(root)

    # 自动加载并开启监控窗口
    initial_monitor_list = load_monitor_list()
    if initial_monitor_list:
        for stock_info in initial_monitor_list:
            if isinstance(stock_info, list) and stock_info:
                stock_code = stock_info[0]
                if stock_code not in monitor_windows:
                    monitor_win = create_monitor_window(stock_info)
                    monitor_windows[stock_code] = monitor_win
            elif isinstance(stock_info, str):
                stock_code = stock_info
                # 重新构造 stock_info，以便 create_monitor_window 使用
                # 注意：这里需要你自行获取完整信息或根据需要调整逻辑
                if stock_code not in monitor_windows:
                    monitor_win = create_monitor_window([stock_code, "未知", "未知", 0, 0])
                    monitor_windows[stock_code] = monitor_win

    # 主线程启动后
    # root.after(1000, process_ui_queue)
    # root.after(5000, process_data_queue)

    # 假设点击按钮触发后台保存
    #quene 模式
    # start_async_save_dataframe()

    root.after(10000, flush_alerts)

    # 首次调用任务，启动定时循环
    check_file_status = check_readldf_exist()
    if not check_file_status:
        schedule_workday_task(root, target_hour, target_minute,immediate=True)
    else:
        # 启动定时任务调度
        schedule_workday_task(root, target_hour, target_minute)

    schedule_worktime_task(tree)

    #重复了schedule_workday_task
    schedule_daily_archive(root, hour=15, minute=5, archive_file=None)

    # 启动定时任务调度
    schedule_get_ths_code_task()

    #每日定时初始化
    schedule_daily_init(root)


    # 在主程序初始化时调用一次
    reset_lift_flags()

    refresh_all_stock_data()
    bind_hotkeys(root)

    start_dpi_monitor(root)

    root.bind("<FocusIn>", on_window_focus, add="+")
    # root.bind("<Configure>", lambda event: update_window_position("main"))
    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, "main"))
    root.mainloop()

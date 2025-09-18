import os
import sys
import requests
import pandas as pd
from pandas import HDFStore
import tkinter as tk
import shutil
from tkinter import ttk, messagebox, filedialog
import time
import json
from datetime import datetime, timedelta
from ctypes import wintypes
import ctypes
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

def get_base_path():
    """
    プログラム実行時のベースパスを取得する。
    PyInstallerでexe化された場合でも、実行ファイルのディレクトリを返す。
    """
    if getattr(sys, 'frozen', False):
        # PyInstallerでexe化された場合
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 通常の.pyファイルとして実行された場合
        return os.path.dirname(os.path.abspath(__file__))


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
            print(f"锁文件存在，读操作等待中... 已等待 {wait_count} 秒")
            time.sleep(1)
        print("锁已释放，读操作继续。")

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
        print("缺少 PyTables，HDFStore 功能将被禁用。")

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

    # print("BLAS/LAPACK libraries:", list_blas_libraries())
    # def check_blas():
    #     import numpy as np
    #     import ctypes.util 
    #     # for name in list(np.__config__.blas_opt_info.get("libraries", [])):
    #     #     print("BLAS library:", name)

    #     # 进一步检查动态库
    #     for dll in ctypes.util.find_library("mkl_rt"), ctypes.util.find_library("openblas"):
    #         print("Found DLL:", dll)
    # check_blas()


    if detect_blas_backend() == 'Unknown':
        print("MKL 不可用，NumPy 可能会慢一些，但程序仍可运行。")
        # pytables_status = False
    # 使用条件判断执行后续代码
    if tables_available and mkl_available:
        pytables_status = True
    else:
        print("跳过 HDFStore 操作")
    print(f"BLAS backend:{detect_blas_backend()} pytables_status:{pytables_status}")


def get_ths_code():
    global ths_code,code_file_name
    if os.path.exists(code_file_name):
        print(f"{code_file_name} exists, loading...")
        with open(code_file_name, "r", encoding="utf-8") as f:
            codelist = json.load(f)['stock']
            # ths_code = [co for co in codelist if co.startswith('60')]
            ths_code = [co for co in codelist]
        print("Loaded:", len(ths_code))
    else:
        print(f"{code_file_name} not found, creating...")
        data = {"stock": ths_code}
        with open(code_file_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

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
print(screen_width,screen_height)
def schedule_task(name, delay_ms, func, *args):
    """带唯一名称的任务调度（重复调度会覆盖旧任务）"""

    # 如果已存在同名任务 -> 先取消
    if name in after_tasks:
        root.after_cancel(after_tasks[name]["id"])
        after_tasks.pop(name, None)

    def wrapper():
        try:
            func(*args)
        finally:
            # 执行完后清理
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
        print(f"任务 {name} 已取消")
        after_tasks.pop(name, None)

def show_tasks():
    print("当前任务列表:")
    for name, info in after_tasks.items():
        print(
            f"  Name={name}, ID={info['id']}, "
            f"目标时间={time.strftime('%H:%M:%S', time.localtime(info['target']))}, "
            f"函数={info['func'].__name__}"
        )
    # root.after(2000, show_tasks)

# --------------------
# 启动线程
# --------------------
def start_worker(worker_task,param=None):
    global worker_thread, stop_event
    if worker_thread is not None and worker_thread.is_alive():
        print("Worker running, stopping first...")
        # stop_worker(lambda: actually_start_worker(param))  # 停止完成后再启动
        stop_worker(lambda: actually_start_worker(worker_task,param))  # 停止完成后再启动
    else:
        actually_start_worker(worker_task,param)

def actually_start_worker(worker_task,param=None):
    global worker_thread, stop_event
    stop_event.clear()
    worker_thread = threading.Thread(target=worker_task, args=(param,), daemon=True)
    worker_thread.start()
    print("Worker started!")
    check_worker_done()
    return worker_task

def check_worker_done():
    #检查任务结束更新视图
    global worker_thread,realdatadf
    if worker_thread.is_alive():
        root.after(2000, check_worker_done)  # 200ms 后再检查
    else:
        print("Worker finished!")
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
            print("Worker stopped")
            worker_thread = None
            stop_event.clear()
            if callback:
                callback()

    check_stop()




def get_pids(pname):
    # print(pname)
    # find AutoHotkeyU64.exe
    pids = []
    for proc in psutil.process_iter():
        if pname in proc.name():
            pids.append(proc.pid)
    # print(pids)
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
        # print(handles)
        for hwnd in handles:
            if IsWindowVisible(hwnd):
                return hwnd
    return hwnd


def get_pids_values(pname):
    # print(pname)
    # find AutoHotkeyU64.exe
    pids = 0
    for proc in psutil.process_iter():
        if pname in proc.name():
            # pids.append(proc.pid)
            pids = proc.pid
    # print(pids)
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
        print(f'tdx_pid:{tdx_pid}')
        find_tdx_window()
    if not check_pid(dfcfpname,dfcf_pid):
        global dfcf_process_hwnd
        dfcf_pid = get_pids('mainfree.exe')
        print(f'dfcf_pid:{dfcf_pid}')
        dfcf_process_hwnd = get_handle('mainfree.exe')
    if not check_pid(thspname,ths_pid):
        global ths_process_hwnd,ths_prc_hwnd
        ths_pid = get_pids(thspname)
        print(f'ths_pid:{ths_pid}')
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
            print(f"NoSuchProcess with pid: {pid}")
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
        print(f"已找到DFCF: {dfcf_process_hwnd} 发送成功")
        pyperclip.copy(stock_code)
        print(f"hwnd:{dfcf_process_hwnd} Stock code {stock_code} copied to clipboard!")
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
        print(f"已找到THS: {ths_window_handle} process: {ths_process_hwnd} 发送成功 bytes_str:{bytes_str}")
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

PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
PostMessageW.restype = ctypes.c_int

RegisterWindowMessageW = user32.RegisterWindowMessageW
RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
RegisterWindowMessageW.restype = ctypes.c_uint

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
print(minutes_to_time(1300))


def get_now_time_int():
    now_t = datetime.now().strftime("%H%M")
    return int(now_t)

def get_now_time_int_sec():
    now_t = datetime.now().strftime("%H:%M:%S")
    return (now_t)


def get_last_weekday_before(target_date=datetime.today().date()):
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

def get_day_is_trade_day(today=datetime.today().date()):
    day_n = int(today.strftime("%w"))
    if day_n > 0 and day_n < 6:
        return True
    else:
        return False

def get_work_time(now_t = None):

    if not get_day_is_trade_day():
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
    tdx_state = tdx_var.get()
    ths_state = ths_var.get()
    dfcf_state = dfcf_var.get()
    if not tdx_state and not ths_state and not dfcf_state:
        root.title(f"股票异动数据监控")
    else:

        if len(stock_code.split()) == 2:
            stock_code,stock_name = stock_code.split()
        elif not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
            messagebox.showerror("错误", "请输入有效的6位股票代码")
            return

        # 生成股票代码
        generated_code = generate_stock_code(stock_code)

        # 更新状态
        root.title(f"股票异动数据监控 + 通达信联动 - 正在发送...")

        # 在新线程中执行发送操作，避免UI卡顿
        threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()


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

            # 获取通达信注册消息代码
            UWM_STOCK = RegisterWindowMessageW("Stock")

            # 发送消息
            if tdx_window_handle != 0:
                # 尝试将生成的代码转换为整数
                try:
                    message_code = int(generated_code)
                except ValueError:
                    message_code = 0

                # 发送消息
                status = PostMessageW(tdx_window_handle, UWM_STOCK, message_code, 2)
                if status:
                    print("TDX Message posted successfully.")
                else:
                    # PostMessageW returns 0 on failure.
                    print("Failed to post message.")
                    if retry:
                        find_tdx_window()
                        _send_to_tdx_thread(stock_code, generated_code,retry=False)

                # 更新状态
                status = "发送成功"
            else:
                status = "未找到通达信窗口，请确保通达信已打开"
                if retry:
                    find_tdx_window()
                    _send_to_tdx_thread(stock_code, generated_code,retry=False)
            # root.after(0, _update_ui_after_send, status)
        if ths_state:
            thsstatus = send_code_message(stock_code)
            print(f"THS send Message posted:{thsstatus}")
            # root.after(3, _update_ui_after_send, status)
            status = f'{status} : {thsstatus}' 
        if dfcf_state:
            dfcfstatus = send_code_clipboard(stock_code)
            print(f"DC Paste:{dfcfstatus}")
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

#获取全部数据
def get_dfcf_all_data():

    # if not (get_day_is_trade_day() and get_now_time_int() > 1505):
    url = "https://push2ex.eastmoney.com/getAllStockChanges?"

    reversed_symbol_map = {v: k for k, v in symbol_map.items()}

    params = {
        'ut': '7eea3edcaed734bea9cbfc24409ed989',
        'pageindex': '0',
        'pagesize': '50000',
        'dpt': 'wzchanges',
        '_': int(time.time() * 1000)
    }

    df = pd.DataFrame()

    for sel_type in symbol_map:

        params['type'] = symbol_map[sel_type]
    
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data_json = response.json()
            
            if not data_json.get('data') or not data_json['data'].get('allstock'):
                messagebox.showinfo("提示", "未获取到数据")
                return pd.DataFrame()
            
            temp_df = pd.DataFrame(data_json["data"]["allstock"])
            if 'tm' not in temp_df.columns:
                return pd.DataFrame()
            
            temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
            temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            
            temp_df["板块"] = temp_df["板块"].astype(str).map(
                lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            )

            temp_df = temp_df.sort_values(by="时间", ascending=False)
            df = pd.concat([df, temp_df], axis=0)

        except requests.exceptions.Timeout:
            messagebox.showerror("错误", "请求超时")
            return pd.DataFrame()
        except requests.exceptions.RequestException as e:
            messagebox.showerror("错误", f"网络错误: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            messagebox.showerror("错误", f"数据处理错误: {str(e)}")
            return pd.DataFrame()

    return df

def start_async_save(df=None):
    """启动一个新线程来保存DataFrame"""
    # 创建并启动新线程
    # print("正在启动save_dataframe后台保存任务...")
    # # save_thread = executor.submit(save_dataframe)
    # save_thread = threading.Thread(target=save_dataframe)
    # save_thread.start()
    """后台线程保存 DataFrame"""
    print("正在启动 save_dataframe 后台保存任务...")
    
    def save_wrapper():
        try:
            save_dataframe()  # 确保 save_dataframe 内部可以安全在后台线程运行
        except Exception as e:
            print("保存出错:", e)
    
    save_thread = threading.Thread(target=save_wrapper, daemon=True)
    save_thread.start()


def schedule_daily_archive(root, hour=15, minute=5, archive_file=None):
    """每日固定时间执行存档任务，仅工作日"""
    
    def archive_func():
        start_async_save()

    def next_archive_time():
        """计算下一次存档时间，跳过周末"""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 如果已经过今天目标时间或今天是周末，则找下一个工作日
        while target <= now or target.weekday() >= 5:  # 5=周六,6=周日
            target += timedelta(days=1)
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target

    def check_and_schedule():
        now = datetime.now()
        next_time = next_archive_time()
        delay = (next_time - now).total_seconds() * 1000  # 毫秒
        print(f"下一次存档时间: {next_time}, 延迟 {int(delay)} ms")
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
        print(f' workday:{date_str} {filename} exists,return')
        return
    while not start_init:
        if  get_work_time() or (not get_day_is_trade_day() and os.path.exists(filename)) or (930 < get_now_time_int() < 1505):
            # print("not workday don't run  save_dataframe...")
            print("get_work_time don't run  save_dataframe...")
            return
        time.sleep(5)
        print('wait init background 完成...')
    print(f'start_init:{start_init} will to save')    
    toast_message(root,f'start_init:{start_init} will to save')    
    try:
        # 1. 從 DateEntry 獲取日期物件
        selected_date_obj = date_entry.get_date()
        # 2. 格式化日期為字串
        # 例如: 2025-09-03
        date_str = selected_date_obj.strftime("%Y-%m-%d")
        
        # 3. 建立檔名（這裡儲存為 CSV）
        selected_type  = type_var.get()
        filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
        date_write_is_processed = True
        
        # --- 核心檢查邏輯 ---
        if os.path.exists(filename):
            print(f"文件 '{filename}' 已存在，放棄寫入。")
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
        else:
            global realdatadf_lock
            print(f'realdatadf_lock:{realdatadf_lock}')
            time.sleep(6)
            all_df = get_stock_changes_background()
            all_df['代码'] = all_df["代码"].astype(str).str.zfill(6)
            # 4. 儲存 DataFrame
            all_df.to_csv(filename, index=False, encoding='utf-8-sig', compression="bz2") 
            # messagebox.showinfo("成功", f"文件已儲存為: {filename}")
            print(f"文件已儲存為: {filename}")
            toast_message(root,f"文件已儲存為: {filename}")
            loaded_df = all_df
        loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)

        return loaded_df

    except Exception as e:
        messagebox.showerror("錯誤", f"save_data儲存文件時發生錯誤: {e}")
        print(f"save_data儲存文件時發生錯誤: {e}")



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
        df[['涨幅', '价格', '量']] = df[['涨幅', '价格', '量']].fillna(0.0)

        # 步驟3: 計算每個“代码”出現的次數
        df['count'] = df.groupby('代码')['代码'].transform('count')

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
                print("提示", "未获取到数据")
                return pd.DataFrame()
            
            temp_df = pd.DataFrame(data_json["data"]["allstock"])
            if 'tm' not in temp_df.columns:
                return pd.DataFrame()
            
            temp_df["tm"] = pd.to_datetime(temp_df["tm"], format="%H%M%S", errors='coerce').dt.time
            temp_df.columns = ["时间", "代码", "_", "名称", "板块", "相关信息"]
            temp_df = temp_df[["时间", "代码", "名称", "板块", "相关信息"]]
            temp_df["板块"] = temp_df["板块"].astype(str).map(
                lambda x: reversed_symbol_map.get(x, f"未知类型({x})")
            )
            temp_df = temp_df.sort_values(by="时间", ascending=False)
        else:
            temp_df = loaded_df
        temp_df = filter_stocks(temp_df,selected_type)
        
        if stock_code:
            stock_code = stock_code.zfill(6)
            temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]
        return temp_df
        
    except requests.exceptions.Timeout:
        messagebox.showerror("错误", "请求超时")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        messagebox.showerror("错误", f"网络错误: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        messagebox.showerror("错误", f"数据处理错误: {str(e)}")
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

def search_by_code(event=None):
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
    selected_type = type_var.get()
    code_entry.delete(0, tk.END)

    status_var.set(f"加载{selected_type if selected_type else '所有'}异动数据")
    data = _get_stock_changes(selected_type=selected_type)
    populate_treeview(data)

def refresh_data():
    """刷新数据"""

    global loaded_df,viewdf,realdatadf,start_init,scheduled_task
    global date_write_is_processed,worker_thread,last_updated_time

    if loaded_df is not None and not loaded_df.empty:
        if start_init > 0:
            if date_entry.winfo_exists():
                try:
                    date_entry.set_date(get_today())
                except Exception as e:
                    print("还不能设置:", e)
        if scheduled_task:
            root.after_cancel(scheduled_task)
            time.sleep(0.2)
        show_tasks()
        loaded_df = None
        start_init = 0
        viewdf = pd.DataFrame()
        realdatadf = pd.DataFrame()
        print('start refresh_data get_stock_changes_background')
        start_worker(schedule_worktime_task(tree))
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

    selected_item = tree.selection()
    if selected_item:
        stock_info = tree.item(selected_item, 'values')
        stock_code = stock_info[1]
        stock_code = stock_code.zfill(6)
        send_to_tdx(stock_code)

        # 1. 推送代码到输入框
        code_entry.delete(0, tk.END)
        code_entry.insert(0, stock_code)
        
        # 2. 更新其他数据（示例）
        print(f"选中股票代码: {stock_code}")
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
    print(f"选择了日期: {selected_date}")
    global loaded_df,last_updated_time
    
    try:
        # 1. 獲取日期並建立檔名
        selected_date_obj = date_entry.get_date()
        date_str = selected_date_obj.strftime("%Y-%m-%d")
        selected_type  = type_var.get()
        filename =  os.path.join(BASE_DIR, "datacsv",f"dfcf_{date_str}.csv.bz2")
        print(f"嘗試載入文件: {filename}")

        # 2. 檢查檔案是否存在
        if os.path.exists(filename):
            stop_worker()
            last_updated_time = None
            # 檔案存在，載入到 DataFrame
            loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
            # loaded_df['代码'] = loaded_df['代码'].apply(lambda x:str(x))
            loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)
            # 這裡可以根據需要更新 Treeview 或其他UI
            populate_treeview(loaded_df)
            
            # messagebox.showinfo("成功", f"文件 '{filename}' 已成功載入。")
            
        else:
            # 檔案不存在
            messagebox.showinfo("文件不存在", f"文件 '{filename}' 不存在，請檢查。")
            
    except Exception as e:
        messagebox.showerror("錯誤", f"載入文件時發生錯誤: {e}")
        print(f"載入文件時發生錯誤: {e}")

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
    print(f"TDX: {tdx_var.get()}, THS: {ths_var.get()}, DC: {dfcf_var.get()}, Uniq: {uniq_var.get()},Sub: {sub_var.get()}")

def daily_task():
    """
    这个函数包含了你希望每天执行的逻辑。
    """
    print(f"每日定时任务执行了！当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # save_dataframe()
    start_async_save()
    # 在这里添加你的具体任务，例如：



def get_next_weekday_time(target_hour, target_minute):
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
        if start_init > 0 and date_entry.winfo_exists():
            try:
                date_entry.set_date(date_str)
            except Exception as e:
                print("还不能设置:", e)
        print(f"文件 '{filename}' 已存在，放棄寫入,已加载")
        loaded_df = pd.read_csv(filename, encoding='utf-8-sig', compression="bz2")
        loaded_df['代码'] = loaded_df["代码"].astype(str).str.zfill(6)
        realdatadf = loaded_df
        return True
    else:
        return False

def schedule_get_ths_code_task():
    """
    每隔5分钟执行一次的任务。
    """
    
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"自动更新任务get_ths_code执行于: {current_time}")
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
    print(f"自动更新任务checkpid_task执行于: {current_time}")
    # 在这里添加你的具体任务逻辑

    save_thread = threading.Thread(target=check_pids_all)
    save_thread.start()
    # 5分钟后再次调用此函数
    # root.after(3 * 60 * 1000, schedule_checkpid_task)
    schedule_task('checkpid_task',3 * 60 * 1000,lambda: schedule_checkpid_task)




def schedule_worktime_task(tree,update_interval_minutes=update_interval_minutes):
    """
    每隔5分钟执行一次的任务。
    """
    global start_init,loaded_df,scheduled_task,last_updated_time
    next_execution_time = get_next_weekday_time(9, 25)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    if get_day_is_trade_day() and 922 < get_now_time_int() < 932:
        loaded_df = None

    # 使用 root.after() 调度任务，在回调函数中使用 lambda 包装，
    # 确保在任务完成后再次调用自身进行重新调度。
    if loaded_df is None and (get_day_is_trade_day() or start_init == 0):
        if get_work_time() or 1130 < get_now_time_int() < 1300 or start_init == 0:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"自动更新任务get_stock_changes_background执行于: {current_time}")
            # 在这里添加你的具体任务逻辑
            status_label3.config(text=f"更新在{current_time[:-3]}执行")
            scheduled_task = actually_start_worker(get_stock_changes_background)
            # 5分钟后再次调用此函数
            schedule_task('worktime_task',5 * 60 * 1000,lambda: schedule_worktime_task(tree))
        else:
            # status_label3.config(text=f"更新在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
            status_label3.config(text=f"延迟在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
            schedule_task('worktime_task',delay_ms,lambda: schedule_worktime_task(tree))
    else:
        # if get_work_time() :
        #     status_label3.config(text=f"更新在{current_time[:-3]}执行")
        #     scheduled_task = actually_start_worker(get_stock_changes_background)
        #     # 5分钟后再次调用此函数
        #     schedule_task('worktime_task',5 * 60 * 1000,lambda: schedule_worktime_task(tree))
        # else:
        print(f"下一次background任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")
        print(f"自动更新任务get_stock_changes_background执行于:在{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}执行")
        status_label3.config(text=f"日更新{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}")
        schedule_task('worktime_task',delay_ms,lambda: schedule_worktime_task(tree))


def schedule_workday_task(root, target_hour, target_minute):
    """
    调度任务在下一个工作日的指定时间执行。
    """
    next_execution_time = get_next_weekday_time(target_hour, target_minute)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)
    print(f"下一次保存任务将在 {next_execution_time.strftime('%Y-%m-%d %H:%M:%S')} 执行，还有 {delay_ms // 1000} 秒。")

    status_label2.config(text=f"存档-{next_execution_time.strftime('%Y-%m-%d %H:%M')[5:]}")
    schedule_task('worksaveday_task',delay_ms,lambda: [daily_task(), schedule_workday_task(root, target_hour, target_minute)])


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
                print(f"移动窗口失败 {code}: {e}")


def rearrange_monitors_per_screen(align="left", sort_by="id"):
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
            print(f"⚠ 获取窗口位置失败: {e}")

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
                print(f"⚠ 窗口排列失败: {e}")


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
#             print(f"⚠ 获取窗口位置失败: {e}")

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
#                 print(f"⚠ 窗口排列失败: {e}")




def archive_monitor_list():
    """归档监控文件，避免空或重复存档"""

    if not os.path.exists(MONITOR_LIST_FILE):
        print("⚠ monitor_list.json 不存在，跳过归档")
        return

    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        print("⚠ monitor_list.json 内容为空，跳过归档")
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
                print("⚠ 内容与上一次存档相同，跳过归档")
                return
        except Exception as e:
            print(f"⚠ 无法读取最近存档: {e}")

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
    print(f"✅ 已归档监控文件: {dest}")


def list_archives():
    """列出所有存档文件"""
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith("monitor_list_") and f.endswith(".json")],
        reverse=True
    )
    return files


def load_archive(selected_file):
    """加载选中的存档文件并刷新监控"""
    archive_file = os.path.join(ARCHIVE_DIR, selected_file)
    if not os.path.exists(archive_file):
        messagebox.showerror("错误", "存档文件不存在")
        return

    # 关闭所有已有监控窗口
    for code, info in list(monitor_windows.items()):
        try:
            if "toplevel" in info and info["toplevel"].winfo_exists():
                info["toplevel"].destroy()
        except Exception as e:
            print(f"关闭窗口 {code} 失败: {e}")
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



def open_archive_loader():
    """打开存档选择窗口"""
    win = tk.Toplevel(root)
    win.title("加载历史监控数据")
    win.geometry("400x300")

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
    # 按 Esc 关闭窗口
    win.bind("<Escape>", lambda : win.destroy())
    win.after(6*1000,  lambda  :win.destroy())

# --- 数据持久化函数 ---
def save_monitor_list():
    """保存当前的监控股票列表到文件"""
    monitor_list = [win['stock_info'] for win in monitor_windows.values()]
    mo_list = []
    if len(monitor_list) > 0:
        for m in monitor_list:
            stock_code = m[0]
            if stock_code:
                stock_code = stock_code.zfill(6)

            if  not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
                print(f"错误请输入有效的6位股票代码:{m}")
                continue
            mo_list.append(m)

    else:
        print('no window find')

    with open(MONITOR_LIST_FILE, "w") as f:
            json.dump(mo_list, f)
    print(f"监控列表已保存到 {MONITOR_LIST_FILE}")

    archive_monitor_list()

def load_monitor_list():
    """从文件加载监控股票列表"""
    if os.path.exists(MONITOR_LIST_FILE):
        with open(MONITOR_LIST_FILE, "r") as f:
            try:
                loaded_list = json.load(f)
                # 确保加载的数据是列表，并且包含列表/元组
                if isinstance(loaded_list, list) and all(isinstance(item, (list, tuple)) for item in loaded_list):
                    return [list(item) for item in loaded_list]
                return []
            except (json.JSONDecodeError, TypeError):
                return []
    return []

def get_stock_changes_background(selected_type=None, stock_code=None, update_interval_minutes=update_interval_minutes):
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
    
    if get_day_is_trade_day() and 922 < get_now_time_int() < 932:
        realdatadf = pd.DataFrame()
        loaded_df = None
        viewdf = pd.DataFrame()
        if start_init > 0:
            if date_entry.winfo_exists():
                try:
                    date_entry.set_date(get_today())
                except Exception as e:
                    print("还不能设置:", e)
        start_init = 0
        last_updated_time = 0

    # 使用 with realdatadf_lock 确保只有一个线程可以进入此关键区域
    if loaded_df is None  and (len(realdatadf) == 0 or get_work_time() or (not date_write_is_processed and get_now_time_int() > 1505)):
        with realdatadf_lock:

            # 检查是否需要从API获取数据
            if last_updated_time is None or current_time - last_updated_time >= timedelta(minutes=update_interval_minutes):
                print(f"时间间隔已到，正在从API获取新数据...")
                last_updated_time = current_time
                # 模拟从 Eastmoney API 获取数据
                time.sleep(0.2)
                for symbol in symbol_map.keys():
                    # 构造模拟数据
                    # 假设每次调用都返回一些新的和一些旧的数据
                    if stop_event.is_set():
                        print(f'backgroundworker线程停止运行')
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
                    print(f"为 ({symbol}) 获取了新的异动数据，并更新了 realdatadf")
                    if start_init == 0:
                        toast_message(root,f"为 ({symbol}) 获取了新的异动数据，并更新了 realdatadf")
                    time.sleep(5)
                print(f"time:{time.time() - start_time}全部更新 获取了新的异动数据，并更新了realdatadf:{len(realdatadf)}")
                if start_init == 0:
                    toast_message(root,f"time:{time.time() - start_time}全部更新 获取了新的异动数据，并更新了realdatadf:{len(realdatadf)}")
                print(f"realdatadf 已更新:{time.strftime('%H:%M:%S')} {len(realdatadf)}")
            else:
                print(f"{current_time - last_updated_time}:未到更新时间，返回内存realdatadf数据。")
    if start_init == 0:
        time.sleep(6)
        start_init = 1
    # if not get_work_time() and get_now_time_int() > 1505:
    #     start_async_save()
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
            temp_df = realdatadf
        if not get_work_time() and (get_now_time_int() >1530  or get_now_time_int() < 923):
            temp_df = get_stock_changes(selected_type=selected_type)
    else:
        temp_df = get_stock_changes(selected_type=selected_type, stock_code=stock_code)

    return temp_df



def _get_sina_data_realtime(stock_code=None):
    global sina_data_last_updated_time,sina_data_df
    global pytables_status
    basedir = "G:" + os.sep
    fname = os.path.join(basedir, "sina_data.h5")             # 原始 HDF5
    table = "all"
    current_time = datetime.now()
    df = None
    if pytables_status:
        if sina_data_last_updated_time is None or current_time - sina_data_last_updated_time >= timedelta(minutes=3):
            sina_data = read_hdf_table(fname,table)
            if sina_data is not None and not sina_data.empty:
                sina_data_last_updated_time = current_time
                sina_data_df = sina_data.copy()
                if stock_code is not None:
                    df = sina_data.loc[stock_code]
                else:
                    df = sina_data
        else:
            if sina_data_df is not None and not sina_data_df.empty:
                if stock_code is not None:
                    df = sina_data_df.loc[stock_code]
                else:
                    df = sina_data_df

    return df
    # return None

def _get_stock_changes(selected_type=None, stock_code=None):
    """获取股票异动数据"""
    global realdatadf,loaded_df
    global last_updated_time
    current_time = datetime.now()

    if loaded_df is None:
        temp_df = get_stock_changes_time(selected_type=selected_type)
    else:
        temp_df = loaded_df.copy()

    temp_df = filter_stocks(temp_df,selected_type)
    
    if stock_code:
        stock_code = stock_code.zfill(6)
        temp_df = temp_df[temp_df["代码"].astype(str).str.zfill(6) == str(stock_code)]
    return temp_df
        
    

def fast_insert(tree, dataframe):
    if dataframe is not None and not dataframe.empty:
        # 批量插入
        if 'count' in dataframe.columns and dataframe[dataframe['count'] > 0].empty:
            print(f'fast_insert:count retry process_full_dataframe:{dataframe[:1]}')
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



def refresh_stock_data(window_info, tree, item_id):
    """提交后台任务"""
    stock_code = window_info['stock_info'][0]
    def task():
        try:
            data = _get_stock_changes(None, stock_code)  # 你的数据获取函数
            result_queue.put(("data", data, tree, window_info, item_id))
        except Exception as e:
            result_queue.put(("error", e, tree, window_info, item_id))
    threading.Thread(target=task, daemon=True).start()

# 控制更新节流
UPDATE_INTERVAL = 30  # 秒，更新UI最小间隔
last_update_time = 0
message_cache = []  # 缓存队列

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
    # print(f'process_queue:0.5S')
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

# 保存每个 stock_code/item_id 的刷新状态
refresh_registry = {}  # {(tree, window_info, item_id): {"after_id": None}}
# ---------------------------
# 主线程 UI 更新函数
# ---------------------------
def update_monitor_tree(data, tree, window_info, item_id):
    """更新子窗口的 Treeview"""
    global start_init,refresh_registry

    stock_info = window_info['stock_info']
    stock_code, stock_name, *rest = stock_info
    window = window_info['toplevel']

    # print(refresh_registry.keys())
    # 如果已经有 active after，说明下一次刷新已经安排好了，直接返回
    # if refresh_registry[key]["after_id"] is not None:
    #     return

    # def schedule_next(delay_ms):
    #     # 如果已有定时器，取消它（防止重复）
    #     if refresh_registry[key]["after_id"]:
    #         # tree.after_cancel(refresh_registry[key]["after_id"])
    #         try:
    #             tree.after_cancel(refresh_registry[key]["after_id"])
    #         except Exception:
    #             pass  # 任务可能已执行完或被取消
    #         refresh_registry[key]["after_id"] = None
    #     # 启动下一次刷新
    #     refresh_registry[key]["after_id"] = tree.after(delay_ms, lambda: refresh_stock_data(window_info, tree, item_id))

    # 更新最新一行
    # def update_latest_row(new_row):
    #     children = tree.get_children()
    #     if children:
    #         # 获取最后一行的 item id
    #         # last_item = children[-1]
    #         # tree.item(last_item, values=new_row)
    #          # 插入到最上面一行
    #         tree.insert("", 0, values=new_row) 
    #     else:
    #         tree.insert("", tk.END, values=new_row)

    def update_latest_row(new_row):
        children = tree.get_children()
        # 删除占位符行
        for item in children:
            vals = tree.item(item, "values")
            if vals and vals[0] in ("加载ing...", "loading"):  # 可根据占位符调整
                tree.delete(item)
        # 插入到最上面一行
        tree.insert("", 0, values=new_row)

    # def update_latest_row(new_row):
    #     children = monitor_tree.get_children()
    #     # 删除占位符行（模糊匹配 "加载" 或 "loading"）
    #     for item in children:
    #         vals = monitor_tree.item(item, "values")
    #         if vals and vals[0] and any(s.lower() in str(vals[0]).lower() for s in ("加载ing...", "loading")):
    #             monitor_tree.delete(item)
    #     # 插入到最上面一行
    #     monitor_tree.insert("", 0, values=new_row)

    def schedule_next(delay_ms,key, tree, window_info, item_id):
        now = time.time()
        
        # 如果已有任务且还没到期，直接返回
        if refresh_registry[key]["execute_at"] > now:
            # print('refresh_registry not run time')
            return
        execute_at = now + delay_ms / 1000  # 转为秒
        dt=datetime.fromtimestamp(execute_at).strftime("%Y-%m-%d %H:%M:%S")
        # print(f"[{item_id}] {stock_code} 更新刷新任务，安排下一次执行:{dt}")
        refresh_registry[key]["execute_at"] = execute_at
        # 取消旧任务（可能已经执行完也没关系）
        if refresh_registry[key]["after_id"]:
            try:
                tree.after_cancel(refresh_registry[key]["after_id"])
            except Exception:
                pass

        # 安排下一次刷新
        def task():
            try:
                refresh_stock_data(window_info, tree, item_id)
            finally:
                # 执行完成后清理状态
                refresh_registry[key]["after_id"] = None
                refresh_registry[key]["execute_at"] = 0

        refresh_registry[key]["after_id"] = tree.after(delay_ms, task)




    # print(f'update_monitor_tree:{stock_code} {stock_name} {price},{percent},{amount} {get_now_time_int_sec()} ')
    if not window or not window.winfo_exists():
        return  # 窗口已关闭

    key = (id(tree), id(window_info), item_id)
     # 如果已经有刷新任务在调度中，就不再创建新的
    if key not in refresh_registry:
        refresh_registry[key] = {"after_id": None , "execute_at": 0 }

    now = datetime.now()
    next_execution_time = get_next_weekday_time(9, 25)
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)
    dd  = _get_sina_data_realtime(stock_code)
    price,percent,amount = 0,0,0
    if dd is not None:
        price = dd.close
        percent = round((dd.close - dd.llastp) / dd.llastp *100,1)
        amount = round(dd.turnover/100/10000/100,1)
        print(f'sina_data:{stock_code}, {price},{percent},{amount}')


    if data is not None and not data.empty:
        # 只保留当前股票

        data = data[data['代码'] == stock_code].set_index('时间').reset_index()
        if '涨幅' not in data.columns:
            data = process_full_dataframe(data)
        if not get_work_time():
            if dd is not None:
                print(f'sina_data:{stock_code}, {price},{percent},{amount}')
                check_alert(stock_code, price,percent,amount)
            else:
                _data = data[data['量'] > 0 ]
                if _data is not None and not _data.empty:   
                    check_alert(stock_code, _data[:1]['价格'].values[0], _data[:1]['涨幅'].values[0], _data[:1]['量'].values[0])
        else:
            if dd is not None:
                print(f'sina_data:{stock_code}, {price},{percent},{amount}')
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
        pass
        # 如果没有数据，清空并短间隔重试
        # tree.delete(*tree.get_children())

    if  get_work_time() :
        # print(f'start flush_alerts')
        if  not 1130 < get_now_time_int() < 1300:
            # print(f'update_monitor_tree worktime next_update:{30} S')
            # tree.after(30000, lambda: refresh_stock_data(window_info, tree, item_id))
            schedule_next(30000,key, tree, window_info, item_id)
        else:
            next_time =  int(minutes_to_time(1300)) 
            # print(f'update_monitor_tree next_update:{next_time} Min')
            schedule_next(next_time*1000,key, tree, window_info, item_id)
    else:
        print(f'update_monitor_tree next_update:{next_execution_time}')
        schedule_next(delay_ms,key, tree, window_info, item_id)
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

            print(f"选中监控股票代码: {stock_code}")
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

            print(f"选中监控股票代码: {stock_code}")
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

        context_menu.post(event.x_root, event.y_root)
    except Exception as e:
        print(f"[右键菜单异常] {e}")


def on_monitor_double_click(event, stock_code):
    # exists = any(monitor_tree.item(item, "values") == stock_code for item in items)
    monitor_tree = event.widget
    # items = monitor_tree.get_children()
    needs_update = False
    for item in monitor_tree.get_children():
        vals = monitor_tree.item(item, "values")
        # vals 为 None 或空，或者第一列是 "加载ing..." / "loading"
        if not vals or len(vals) == 0 or vals[0] in ("加载ing...", "loading"):
            needs_update = True
            break

    print(f'stock_code: {stock_code} needs_update :{needs_update} 加载ing')
    if needs_update:
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
            def update_latest_row(new_row):
                clean_placeholder()
                n_cols = len(monitor_tree["columns"])
                # 截断或补空，保证长度与列一致
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
                print(f'double_click get sina_data: {stock_code}, {price}, {percent}, {amount}')
                check_alert(stock_code, price, percent, amount)
                time_str = format_time(dd.ticktime)
                alert_row = [time_str, "新浪", percent, price, amount]
                update_latest_row(alert_row)
        threading.Thread(target=fetch_and_insert,args=(stock_code, monitor_tree), daemon=True).start()
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
        #         print(f'double_click get sina_data:{stock_code}, {price},{percent},{amount}')
        #         check_alert(stock_code, price,percent,amount)
        #         time_str = format_time(dd.ticktime)
        #         row = [time_str,"新浪" , percent ,price,amount]
        #         update_latest_row(row)
        # threading.Thread(target=fetch_and_insert, daemon=True).start()

    # update_code_entry(stock_code)



def update_code_entry(stock_code):
    """更新主窗口的 Entry"""
    global code_entry
    print('update_code_entry:',stock_code)
    if not stock_code  or not stock_code.isdigit():
        print(f"code_entry错误请输入有效的6位股票代码:{stock_code}")
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
    print( hasattr(date_entry, "_top_cal") , not date_entry._top_cal.winfo_exists())
    if  hasattr(date_entry, "_top_cal") or not date_entry._top_cal.winfo_exists():
        date_entry.drop_down()
        # 调整日历位置到 DateEntry 下方
        print('没有下拉,正在打开')
        x = date_entry.winfo_rootx()
        y = date_entry.winfo_rooty() + date_entry.winfo_height()
        date_entry._top_cal.geometry(f"+{x}+{y}")


def on_monitor_window_focus(event):
    """
    当任意窗口获得焦点时，协调两个窗口到最前。
    """
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
        # print(f'bring_both_to_front alert_window')
        alert_window.lift()
        alert_window.attributes('-topmost', 1)
        alert_window.attributes('-topmost', 0)


is_already_triggered = False

def bring_both_to_front(main_window):
    if main_window and main_window.winfo_exists():
        print(f'bring_both_to_front main')
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

def reset_lift_flags():
    """
    定时检测窗口状态，如果窗口失去焦点或被最小化，
    自动清除 is_lifted 标记，以便下次 bring_windows_to_front 能生效。
    """
    for win_id, win_info in monitor_windows.items():
        toplevel = win_info.get("toplevel")
        if not (toplevel and toplevel.winfo_exists()):
            continue

        # 如果窗口不是最前的 或 被最小化，就重置标记
        # print(f'{win_id} toplevel.state() :{toplevel.state()} is_lifted : {win_info.keys()}')
        if toplevel.state() == "iconic" or not toplevel.focus_displayof():
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
    #         print(f'bring_both_to_front root')
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
                print("所有窗口配置已加载。")
            except (json.JSONDecodeError, FileNotFoundError):
                print("配置文件损坏或不存在，使用默认窗口位置。")
    else:
        print("未找到配置文件，使用默认位置。")

def save_window_positions():
    """将所有窗口的位置和大小保存到配置文件。"""
    global WINDOW_GEOMETRIES, save_timer
    if save_timer:
        save_timer.cancel()
    # 确保文件写入在程序退出前完成
    # save_monitor_list()
    print(f'save:{WINDOW_GEOMETRIES}')
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(WINDOW_GEOMETRIES, f)
        print("所有窗口配置已保存。")
    except IOError as e:
        print(f"写入配置文件时出错: {e}")

def schedule_save_positions():
    """安排一个延迟保存，避免过于频繁的写入。"""
    global save_timer
    if save_timer:
        save_timer.cancel()
    print('save_monitor_list,schedule_save_positions save')
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


    # try:
    #     if win and win.winfo_exists():
    #             win.destroy()
    #     except:
    #         pass
    #     alert_window = None

    # if window and window.winfo_exists():
    #     window.destroy()
    #     window.update_idletasks()  # 让销毁立即生效
    # alert_window = None

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
    
    # 1. 停止后台线程
    executor.shutdown(wait=False)  # 或 wait=True，根据线程安全性
    
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
        print("保存失败:", e)
    
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
#         # print(f'win_id:{win_id}')
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


def update_position_window(window, window_id, is_main=False):
    """创建一个新窗口，并加载其位置（自动平铺）"""
    global WINDOWS_BY_ID, WINDOW_GEOMETRIES, NEXT_OFFSET, OFFSET_STEP, screen_width, screen_height
    WINDOWS_BY_ID[window_id] = window

    if window_id in WINDOW_GEOMETRIES.keys():
        # 有历史配置，直接使用
        wsize = WINDOW_GEOMETRIES[window_id].split('+')
        if len(wsize) == 3:
            subw_width = int(wsize[1])
            subw_height = int(wsize[2])
            if subw_width > screen_width or subw_height > screen_height:
                place_new_window(window, window_id)
            else:
                window.geometry(WINDOW_GEOMETRIES[window_id])
        else:
            place_new_window(window, window_id)
    else:
        # 没有配置，使用默认 + 自动平铺
        place_new_window(window, window_id)

    # window.bind("<Configure>", lambda event: update_window_position(window_id))
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

# 双屏幕,上屏新建

def init_monitors():
    """扫描所有显示器并缓存信息"""
    global MONITORS
    MONITORS = get_all_monitors()
    if not MONITORS:
        # 至少保留主屏幕
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        MONITORS = [(0, 0, screen_width, screen_height)]
    print(f"✅ Detected {len(MONITORS)} monitor(s).")

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

def place_new_window(window, window_id, win_width=300, win_height=160, margin=5):
    """放置窗口：避免重叠 + 在所属屏幕内自动排列"""
    global WINDOW_GEOMETRIES, WINDOWS_BY_ID, MONITORS
    WINDOWS_BY_ID[window_id] = window

    monitors = MONITORS or [(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))]

    if window_id in WINDOW_GEOMETRIES:
        # 使用已存储位置
        geom = WINDOW_GEOMETRIES[window_id]
        try:
            _, x_part, y_part = geom.split('+')
            x, y = int(x_part), int(y_part)
        except Exception:
            x, y = 100, 100
        x, y = clamp_window_to_screens(x, y, win_width, win_height, monitors)
        window.geometry(f"{win_width}x{win_height}+{x}+{y}")
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


def create_monitor_window(stock_info):
    # stock_info 可能缺失部分数据
    if stock_info[0].find(':') > 0 and len(stock_info) > 4:
        stock_info = stock_info[1:]

    # 默认值
    default_values = {
        "percent": 0.0,
        "price": 0.0,
        "vol": 0
    }

    try:
        stock_code, stock_name, *rest = stock_info
    except ValueError:
        stock_code, stock_name = stock_info[0], stock_info[1]
        rest = []

    # 填充缺失数据
    percent = rest[3] if len(rest) >= 4 else default_values["percent"]
    price   = rest[4] if len(rest) >= 5 else default_values["price"]
    vol     = rest[5] if len(rest) >= 6 else default_values["vol"]

    # 构造 stock_info 完整列表
    stock_info = [stock_code, stock_name, 0, 0 ,  percent , price ,vol]

    monitor_win = tk.Toplevel(root)
    monitor_win.resizable(True, True)
    monitor_win.title(f"监控: {stock_name} ({stock_code})")

    # === 警报开关 ===

    alerts_enabled[stock_code] = tk.IntVar(value=1)
    cb = tk.Checkbutton(monitor_win, text="报警开启", variable=alerts_enabled[stock_code])
    cb.pack(anchor='w', padx=5, pady=5)

    # 样式
    style = ttk.Style()
    style.configure('Thin.Vertical.TScrollbar', arrowsize=8)

    tree_frame = ttk.Frame(monitor_win)
    tree_frame.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

    window_info = {'stock_info': stock_info, 'toplevel': monitor_win}
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

    place_new_window(monitor_win, stock_code)
    refresh_stock_data(window_info, monitor_tree, item_id)

    monitor_win.protocol("WM_DELETE_WINDOW", lambda: on_close_monitor(window_info))
    monitor_win.bind("<FocusIn>", lambda e, w=monitor_win: on_monitor_window_focus(w))
    monitor_win.bind("<Button-1>", lambda event: update_code_entry(stock_code))
    monitor_win.bind("<Double-1>", lambda event, code=stock_code: on_monitor_double_click(event,stock_code))

    # === 右键菜单加报警规则 ===
    # def show_menu(event, stock_info):
    #     menu = tk.Menu(monitor_win, tearoff=0)
    #     menu.add_command(label="设置报警规则", command=lambda : open_alert_editor(stock_info))
    #     menu.post(event.x_root, event.y_root)
    def show_menu(event,stock_info):
        """
        在Treeview上處理右鍵點擊事件的函式。
        """

        # sel = alert_tree.selection()
        # if not sel: return
        # vals = alert_tree.item(sel[0], "values")
        # code = vals[1]
        # 1. 根據右鍵點擊的座標，找出對應的Treeview項目
        parent_win = event.widget.winfo_toplevel()
        iid = monitor_tree.identify_row(event.y)
        
        # 2. 如果點擊在某個項目上
        if iid:
            # 3. 確保點擊的項目被選中
            monitor_tree.selection_set(iid)
            # 4. 取得當前選中的項目ID（此時它應該是iid）
            selected_item_id = monitor_tree.selection()[0]
            
            # # 5. 獲取該項目的值，例如股票代號
            stock_info = monitor_tree.item(selected_item_id, "values")
            # stock_code = item_values[0] # 假設股票代號是第一欄
            # stock_info = stock_info[1:]
            # print(f'stock_info:{stock_info}')

            if len(stock_info) == 5:
                _ ,_ , percent, price , vol = stock_info
                stock_info =  (stock_code,stock_name,0,0 , percent, price , vol) 
            else:
                stock_info = (stock_code,) + stock_info[1:]
            # 6. 建立右鍵選單
            print(f'stock_info:{stock_info}')
            menu = tk.Menu(root, tearoff=0)
            
            # 7. 动态地為選單命令綁定函式和參數
            menu.add_command(label="設定警報規則", command=lambda: open_alert_editor(stock_info,parent_win=parent_win,
                x_root=event.x_root,
                y_root=event.y_root))
            # 8. 顯示選單
            menu.post(event.x_root, event.y_root)
        else:
            # 如果點擊在空白處，清除選中狀態
            # tree.selection_remove(tree.selection())
            menu = tk.Menu(monitor_win, tearoff=0)
            menu.add_command(label="設定警報規則", command=lambda: open_alert_editor(stock_infoparent_win=parent_win,
                x_root=event.x_root,
                y_root=event.y_root))
            menu.post(event.x_root, event.y_root)

    monitor_win.bind("<Button-3>", lambda event: show_menu(event, stock_info))

    # === 保存窗口信息到全局字典 ===
    monitor_windows[stock_code] = {
        'toplevel': monitor_win,
        'monitor_tree': monitor_tree
    }

    return window_info


# ------------------------
# 报警规则加载/保存
# ------------------------
def load_alerts():
    global alerts_rules
    try:
        with open(ALERTS_FILE, "r") as f:
            alerts_rules = json.load(f)
    except:
        alerts_rules = {}

def save_alerts():
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts_rules, f, indent=2, ensure_ascii=False)

# ------------------------
# 报警添加/刷新
# ------------------------
# ============ 高亮函数 ============
def highlight_window(win, times=10, delay=300):
    """让窗口闪烁提示"""
    def _flash(count):
        if not win.winfo_exists():
            return
        color = "red" if count % 2 == 0 else "SystemButtonFace"
        win.configure(bg=color)
        if count < times:
            win.after(delay, _flash, count + 1)
        else:
            win.configure(bg="SystemButtonFace")  # 恢复默认
    _flash(0)

def flash_title(win, code, name):
    """窗口标题加上 ⚠ 提示"""
    if not win.winfo_exists():
        return
    win.title(f"⚠监控: {name} ({code})")
    # 5 秒后恢复
    win.after(5000, lambda: win.title(f"监控: {name} ({code})"))

def toast_message(parent=None, text="", duration=2000, bg="#333", fg="#fff"):
    """在主窗口右下角显示一条提示信息，自动淡出"""
    if parent is None:
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

# def toast_message(parent=None, text="", duration=2000, bg="#333", fg="#fff"):
#     """在主窗口右下角显示一条提示信息，自动淡出"""
#     # 创建顶层窗口
#     if parent is None:
#         parent = tk.Tk()
#         parent.withdraw()
#     win = tk.Toplevel(parent)
#     win.overrideredirect(True)  # 去掉边框
#     win.config(bg=bg)

#     # 文本标签
#     label = tk.Label(win, text=text, bg=bg, fg=fg, font=("Microsoft YaHei", 11))
#     label.pack(ipadx=15, ipady=8)

#     # 放在主窗口右下角
#     parent.update_idletasks()
#     x = parent.winfo_x() + parent.winfo_width() - win.winfo_reqwidth() - 20
#     y = parent.winfo_y() + parent.winfo_height() - win.winfo_reqheight() - 40
#     win.geometry(f"+{x}+{y}")

#     # 窗口置顶
#     win.attributes("-topmost", True)
#     win.update()
#     win.attributes("-topmost", False)

#     # 自动淡出
#     def fade_out():
#         alpha = 1.0
#         while alpha > 0:
#             alpha -= 0.05
#             win.attributes("-alpha", alpha)
#             win.update()
#             win.after(50)
#         win.destroy()

#     win.after(duration, lambda: threading.Thread(target=fade_out).start())


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
    "价格": 0.1,   # 价格变动 0.1 元触发
    "涨幅": 0.2,   # 涨幅变动 0.2% 触发
    "量": 100      # 成交量增加 100 手触发
}

# ------------------------
# 报警中心窗口
# ------------------------
def open_alert_center():
    global alert_window, alert_tree
    global alert_moniter_bring_front
    alert_moniter_bring_front = True
    stock_code,stock_name, stock_info = None, None,None
    selected_item = tree.selection()
    if selected_item:
        vals = tree.item(selected_item, 'values')
        if len(vals) >= 2:
            stock_code = vals[1]
            stock_name = vals[2]
            stock_info = vals[1:]

    if alert_window and alert_window.winfo_exists():
        alert_window.lift()
        return

    alert_window = tk.Toplevel(root)
    alert_window.title("报警中心")
    alert_window.geometry("720x360")
    # 获取之前保存的位置，如果没有则居中
    # pos = load_alert_window_position()  # 返回 (x, y, w, h) 或 None
    # if pos is None:
    #     w, h, x, y = init_alert_window()
    # else:
    #     x, y, w, h = pos
    w, h, x, y = init_alert_window()

    alert_window.geometry(f"{w}x{h}+{x}+{y}")
    # 上方快速规则入口
    top_frame = ttk.Frame(alert_window)
    top_frame.pack(fill="x", padx=5, pady=5)

    tk.Label(top_frame, text="股票代码:").pack(side="left")

    # stock_var = tk.StringVar()
    # vlist = list(monitor_windows.keys())

    # stock_list_for_combo  = [tuple(monitor_windows[co]['stock_info'][:2])  for co in vlist]
    # if stock_code and stock_code not in monitor_windows.keys():
    #     stock_list_for_combo.append((stock_code,stock_name))
    #     stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=10)
    # else:
    #     stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=10)

    # def show_context_menu(event, stock_code):
    #     parent_win = event.widget.winfo_toplevel()
    #     menu = tk.Menu(parent_win, tearoff=0)
    #     menu.add_command(
    #         label="添加/编辑规则",
    #         command=lambda: open_alert_editor(stock_code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root)
    #     )
    #     menu.post(event.x_root, event.y_root)

    # -------------------------
    # 股票选择 Combobox 初始化
    # -------------------------
    stock_var = tk.StringVar()
    vlist = list(monitor_windows.keys())

    # 统一 values 为字符串 "code name"
    stock_list_for_combo = [f"{co} {monitor_windows[co]['stock_info'][1]}" for co in vlist]

    # 如果选中的股票不在监控窗口中，加入列表
    if stock_code and stock_code not in monitor_windows.keys():
        stock_list_for_combo.append(f"{stock_code} {stock_name}")

    # 创建 Combobox，限制宽度避免拉伸
    stock_entry = ttk.Combobox(top_frame, textvariable=stock_var, values=stock_list_for_combo, width=15)

    # 设置初始值
    if stock_code:
        stock_var.set(f"{stock_code} {stock_name}")
    elif stock_list_for_combo:
        stock_var.set(stock_list_for_combo[0])  # 默认选第一个

    stock_entry.pack(side="left", padx=5)

    # 右键菜单或双击触发编辑规则
    def show_context_menu(event):
        selected = stock_var.get()
        if not selected:
            return
        # 取 code 部分（前6-7位数字）
        code = selected.split()[0]
        parent_win = event.widget.winfo_toplevel()
        menu = tk.Menu(parent_win, tearoff=0)
        menu.add_command(
            label="添加/编辑规则",
            command=lambda: open_alert_editor(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root)
        )
        menu.post(event.x_root, event.y_root)

    # stock_entry.bind("<Button-3>", show_context_menu)

    tk.Button(top_frame, text="添加/编辑规则", command=lambda: open_alert_editor(stock_var.get())).pack(side="left", padx=5)

    # 报警列表
    frame = ttk.Frame(alert_window)
    frame.pack(expand=True, fill="both")

    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    cols = ("时间", "代码", "名称", "触发值", "规则", "变化量")

    alert_tree = ttk.Treeview(frame, columns=cols, show="headings", yscrollcommand=scrollbar.set)
    scrollbar.config(command=alert_tree.yview)

    for c in cols:
        alert_tree.heading(c, text=c)
        if c == '触发值':
            alert_tree.column(c, width=120 , anchor="center")
        elif c == '规则':
            alert_tree.column(c, width=100 , anchor="center")
        else:
            alert_tree.column(c, width=40, anchor="center")
    alert_tree.pack(expand=True, fill="both")



    # 双击报警 → 聚焦监控窗口
    def on_double_click(event):
        global code_entry
        sel = alert_tree.selection()
        if not sel:
            return

        vals = alert_tree.item(sel[0], "values")
        code = vals[1]
        name = vals[2]

        # 先发送 TDX 查询
        send_to_tdx(code)
        code_entry.delete(0, tk.END)
        code_entry.insert(0, code)

        if code in monitor_windows.keys():
            win = monitor_windows[code]['toplevel']
        else:
            # 构造 stock_info 填充默认值
            stock_info = [code, name, 0, 0, 0.0, 0.0, 0]
            window_info = create_monitor_window(stock_info)
            win = window_info['toplevel']

        if win and win.winfo_exists():
            win.lift()
            win.attributes("-topmost", 1)
            win.attributes("-topmost", 0)
            highlight_window(win)


    alert_tree.bind("<Double-1>", on_double_click)

    # 右键菜单 → 编辑 / 新增 / 删除规则
    def show_menu(event):
        sel = alert_tree.selection()
        parent_win = event.widget.winfo_toplevel()
        if not sel: return
        vals = alert_tree.item(sel[0], "values")
        code = vals[1]
        menu = tk.Menu(alert_window, tearoff=0)
        menu.add_command(label="编辑规则", command=lambda: open_alert_editor(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
        menu.add_command(label="新增规则", command=lambda: open_alert_editor(code, new=True, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
        menu.add_command(label="删除规则", command=lambda: delete_alert_rule(code, parent_win=parent_win, x_root=event.x_root, y_root=event.y_root))
        menu.post(event.x_root, event.y_root)
    alert_tree.bind("<Button-3>", show_menu)
    # 按 Esc 关闭窗口
    alert_window.bind("<Escape>", lambda  : on_close_alert_monitor(alert_window))
    # 1小时后自动关闭（3600*1000 毫秒）
    alert_window.protocol("WM_DELETE_WINDOW", lambda: on_close_alert_monitor(alert_window))
    alert_window.after(25*1000,  lambda  :on_close_alert_monitor(alert_window))
    # 强制渲染一次，避免白屏
    alert_window.update_idletasks()

    # 延迟刷新（100ms 后执行，避免卡初始化）
    alert_window.after(100, refresh_alert_center)


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

def open_alert_editor(stock_code, new=False,stock_info=None,parent_win=None, x_root=None, y_root=None):
    global alerts_rules,alert_window
    # ------------------ 数据处理 ------------------
    # 简化数据获取，使其能正常运行
    # --- 1. 准备规则 ---
    # orig_rules = alerts_rules.get(code, [])
    orig_rules = alerts_rules.copy()

    price, percent, vol = 5.0, 1.0, 1
    if new and stock_info is not None:
        if stock_code in alerts_rules:
            del alerts_rules[stock_code]
        # print(f'stock_info:{stock_info}')
        code, name, *_ , percent,price, vol = stock_info

    elif not stock_code == '':
        try:
            if stock_info is not None:
                code, name, *_ , percent,price, vol = stock_info
            elif not isinstance(stock_code, (list, tuple)) and len(stock_code.split()) == 2:
                code,name = stock_code.split()
                if code in monitor_windows.keys():
                    stock_info = monitor_windows.get(code, {}).get('stock_info', [code, 0, 0, 0, 1, 5, 1])
                    _, _, _, _, percent,price, vol = stock_info
                    print(f'price : {price},percent:{percent}, vol:{vol}')
            elif isinstance(stock_code, (list, tuple)) and len(stock_code) == 5:
                code, _ , percent,price, vol = stock_code
                print(f'price : {price},percent:{percent}, vol:{vol}')

            elif isinstance(stock_code, (list, tuple)) and len(stock_code) >= 7:
                code, name, *_ , percent,price, vol = stock_code
            else:
                code = stock_code
                stock_info = monitor_windows.get(code, {}).get('stock_info', [code, 0, 0, 0, 1, 5, 1])
                code, name, _, _, percent,price,vol = stock_info
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
    send_to_tdx(code)


    if parent_win is None:
        parent_win = root  # 默认主窗口


    editor = tk.Toplevel(root)
    editor.title(f"设置报警规则 -{name} {code}")
    # editor.geometry("500x300")
    # 固定窗口尺寸
    win_width, win_height = 500, 300
    # # 1. 如果右键事件传入，优先使用鼠标位置
    # if event is not None:
    #     x = event.x_root
    #     y = event.y_root
    # else:
    #     # 2. 否则在父窗口附近
    #     parent_x = parent_window.winfo_x()
    #     parent_y = parent_window.winfo_y()
    #     parent_w = parent_window.winfo_width()
    #     parent_h = parent_window.winfo_height()
    #     x = parent_x + parent_w // 3
    #     y = parent_y + parent_h // 3

    # # 3. 获取屏幕尺寸
    # screen_w = editor.winfo_screenwidth()
    # screen_h = editor.winfo_screenheight()

    # # 4. 避免窗口超出屏幕
    # if x + width > screen_w:
    #     x = screen_w - width - 10
    # if y + height > screen_h:
    #     y = screen_h - height - 10

    # editor.geometry(f"{width}x{height}+{x}+{y}")

    # screen_width, screen_height = get_monitors_info()

    # # 默认位置：屏幕中心
    # x = (screen_width - win_width) // 2
    # y = (screen_height - win_height) // 2

    # # 优先使用右键位置
    # if x_root is not None and y_root is not None:
    #     x = x_root
    #     y = y_root
    # # 如果 parent_win 传入，则在父窗口右下角附近打开
    # elif parent_win is not None:
    #     parent_win.update_idletasks()
    #     px = parent_win.winfo_x()
    #     py = parent_win.winfo_y()
    #     pw = parent_win.winfo_width()
    #     ph = parent_win.winfo_height()
    #     x = px + pw // 2 - win_width // 2
    #     y = py + ph // 2 - win_height // 2

    # # 超出屏幕边界自动调整
    # if x + win_width > screen_width:
    #     x = screen_width - win_width
    # if y + win_height > screen_height:
    #     y = screen_height - win_height
    # if x < 0:
    #     x = 0
    # if y < 0:
    #     y = 0

    screen_width, screen_height = get_monitors_info()

    # 默认位置：屏幕中心
    x = (screen_width - win_width) // 2
    y = (screen_height - win_height) // 2
    print(f'x :{x} y: {y}')
    # 优先使用右键位置
    if x_root is not None and y_root is not None:
        x = x_root
        y = y_root

        # 如果鼠标右侧空间不足，窗口翻到左侧
        if x + win_width > screen_width:
            x = max(0, x_root - win_width)
        print(f'x :{x} y: {y}')
    # 如果 parent_win 传入，则在父窗口右下角附近打开
    elif parent_win is not None:
        parent_win.update_idletasks()
        px = parent_win.winfo_x()
        py = parent_win.winfo_y()
        pw = parent_win.winfo_width()
        ph = parent_win.winfo_height()
        # x = px + pw // 2 - win_width // 2
        # y = py + ph // 2 - win_height // 2
        if px <= 1 or py <= 1:  # 未渲染
            x = (screen_width - win_width) // 2
            y = (screen_height - win_height) // 2
        else:
            x = px + pw//2 - win_width//2
            y = py + ph//2 - win_height//2
        print(f'x :{x} y: {y}')

    # 超出屏幕边界自动调整
    if x + win_width > screen_width:
        x = screen_width - win_width
    if y + win_height > screen_height:
        y = screen_height - win_height
    if x < 0:
        x = 0
    if y < 0:
        y = 0

    print(f'x :{x} y: {y}')

    x , y = calc_alert_window_position(win_width, win_height, x_root=x_root, y_root=y_root, parent_win=parent_win)

    print(f'calc_alert_window_position x :{x} y: {y}')

    #    # 防止超出屏幕
    # x = max(0, min(x, screen_width - win_width))
    # y = max(0, min(y, screen_height - win_height))

    editor.geometry(f"{win_width}x{win_height}+{x}+{y}")
    editor.title(f"设置报警规则 - {name} {code}")

    editor.focus_force()
    editor.grab_set()

    # 统一风格
    style = ttk.Style()
    style.configure("TButton", padding=5)
    style.configure("TLabel", padding=5)

    rules = alerts_rules.get(code, [])

    if not rules or new:
        # 检查历史报警
        has_alert_history = any(a['stock_code'] == code for a in alerts_history)
        
        rules = [
            {"field": "价格", "op": ">=", "value": float(price), "enabled": not has_alert_history, "delta": default_deltas["价格"]},
            {"field": "涨幅", "op": ">=", "value": float(percent), "enabled": not has_alert_history, "delta": default_deltas["涨幅"]},
            {"field": "量", "op": ">=", "value": float(vol), "enabled": not has_alert_history, "delta": default_deltas["量"]},
        ]
        alerts_rules[code] = rules

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
        # if re.match(r"^-?\d*\.?\d*$", P):
        #     return True
        # return False

    vcmd = rules_frame.register(validate_float)

    def make_adjust_fn(val_var, pct):
        return lambda: val_var.set(round(val_var.get() * (1 + pct), 2))

    def add_rule(field="价格", op=">=", value=0.0, enabled=True, delta=None):
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

        # # 调整按钮逻辑
        # def make_adjust_fn(var):
        #     def _inc():
        #         try:
        #             val = float(var.get())
        #         except:
        #             val = 0.0
        #         if field_var.get() == "价格":
        #             var.set(round(val * 1.01, 2))  # 价格按 1% 增加
        #         elif field_var.get() == "涨幅":
        #             var.set(round(val + 1, 2))     # 涨幅 +1
        #         elif field_var.get() == "量":
        #             var.set(round(val + 0.5, 2))   # 量 +0.5
        #     return _inc

        # def make_adjust_fn_minus(var):
        #     def _dec():
        #         try:
        #             val = float(var.get())
        #         except:
        #             val = 0.0
        #         if field_var.get() == "价格":
        #             var.set(round(val * 0.99, 2))  # 价格按 1% 减少
        #         elif field_var.get() == "涨幅":
        #             var.set(round(val - 1, 2))     # 涨幅 -1
        #         elif field_var.get() == "量":
        #             var.set(round(val - 0.5, 2))   # 量 -0.5
        #     return _dec

        # ttk.Button(rules_frame, text="-", command=make_adjust_fn_minus(val_var), width=4).grid(row=row, column=4)
        # ttk.Button(rules_frame, text="+", command=make_adjust_fn(val_var), width=4).grid(row=row, column=5)

        '''
        # 根据字段决定调整幅度
        if field == "量":
            step = 0.5
            text_minus = "-0.5"
            text_plus = "+0.5"
        elif field == "涨幅":
            step = 0.1
            text_minus = "-0.1"
            text_plus = "+0.1"
        else:  # 默认价格
            step = 0.01  # 1%
            text_minus = "-1%"
            text_plus = "+1%"

        # 百分比/步进调整按钮
        ttk.Button(rules_frame, text=text_minus, command=make_adjust_fn(val_var, -step), width=4).grid(row=row, column=4)
        ttk.Button(rules_frame, text=text_plus,  command=make_adjust_fn(val_var, step),  width=4).grid(row=row, column=5)
        '''
        # # 百分比调整按钮
        # ttk.Button(rules_frame, text="-1%", command=make_adjust_fn(val_var, -0.02), width=4).grid(row=row, column=4)
        # ttk.Button(rules_frame, text="+1%", command=make_adjust_fn(val_var, 0.02), width=4).grid(row=row, column=5)

        # delta 输入
        delta_var = tk.DoubleVar(value=delta)
        # delta_var = tk.StringVar(value=delta)
        ttk.Spinbox(rules_frame, textvariable=delta_var, from_=-10.01, to=100,
                    increment=0.1, width=8,validate="key",validatecommand=(vcmd, "%P")).grid(row=row, column=6, padx=5)
        # ttk.Entry(rules_frame, textvariable=delta_var, width=10,validate="key", validatecommand=(vcmd, "%P")).grid(row=row, column=3, padx=2)

        entries.append({
            "field_var": field_var,
            "op_var": op_var,
            "val_var": val_var,
            "enabled_var": enabled_var,
            "delta_var": delta_var
        })

    # 保存时同步到每条规则
    def save_rule():
        new_rules = []
        for entry in entries:
            new_rules.append({
                "field": entry["field_var"].get(),
                "op": entry["op_var"].get(),
                "value": entry["val_var"].get(),
                "enabled":entry["enabled_var"].get(),
                "delta": entry["delta_var"].get()
            })
        alerts_rules[code] = new_rules
        save_alerts()
        toast_message(alert_window, f"{code} 报警规则已保存")
        editor.destroy()

    def del_rule():

        if code in alerts_rules:
            print(f"删除规则: {alerts_rules[code]}")
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
        # print(f'alerts_rules:{alerts_rules.get(code, [])} orig_rules:{orig_rules.get(code, [])}')
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
    # alert_window.protocol("WM_DELETE_WINDOW", lambda: on_close_alert_monitor(alert_window))


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
            print(f"{rule['field']} 开关状态: {rule['enabled']}")

        # 在 Treeview 中插入规则信息
        alert_tree.insert("", "end", iid=f"{stock_code}_{i}",
                          values=(rule['field'], rule['op'], rule['value']))

        # 在 Treeview 指定列添加 Checkbutton 控件
        chk = Checkbutton(alert_tree, variable=var, command=toggle_rule)
        # 假设 column=3 是开关列
        alert_tree.window_create(f"{stock_code}_{i}", column=3, window=chk)


# -----------------------------
# 检查单只股票是否触发报警
# -----------------------------
def check_alert(stock_code, price, change, volume, name=None):
    """
    检查股票是否触发报警规则，并使用冷却机制。
    delta 用于判断最小变化量触发报警。
    """
    global alerts_rules, alerts_history, alerts_buffer, monitor_windows, last_alert_times

    if stock_code not in alerts_rules:
        return  # 无规则直接返回

    # 有监控窗口才检查开关
    if stock_code in alerts_enabled and not alerts_enabled[stock_code].get():
        return

    if name is None:
        name = monitor_windows.get(stock_code, {}).get('stock_info', [stock_code, ''])[1]

    val_map = {'价格': price, '涨幅': change, '量': volume}

    for rule in alerts_rules[stock_code]:
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
            alerts_buffer.append({
                'time': now.strftime('%H:%M:%S'),
                'stock_code': stock_code,
                'name': name,
                'field': field,
                'value': val,
                'delta': abs(val - last_val) if last_val is not None else 0,
                'status': status_text,
                'rule': rule
            })
            continue

        if triggered:
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
def refresh_alert_center():
    global alert_window, alert_tree, alerts_history

    if not alert_window or not alert_window.winfo_exists() or alert_tree is None:
        return

    alert_tree.delete(*alert_tree.get_children())
    alert_tree.tag_configure("triggered", background="yellow", foreground="red")
    alert_tree.tag_configure("not_triggered", background="white", foreground="black")

    for alert in alerts_history[-200:]:
        field = alert.get("field", "")
        value = alert.get("value", "")
        rule = alert.get("rule", {})
        delta = rule.get("delta", "")
        op = rule.get("op", "")
        rule_value = rule.get("value", "")

        # 判断是否触发
        triggered = False
        if op == ">=" and value >= rule_value:
            triggered = True
        elif op == "<=" and value <= rule_value:
            triggered = True

        status = "触发" if triggered else "未触发"
        vals = (
            alert['time'],
            alert['stock_code'],
            alert['name'],
            f"{field}{op}{rule_value} → {status}",
            f"现值 {value}",
            f"变化量 {delta}"
        )
        tag = "triggered" if triggered else "not_triggered"
        alert_tree.insert("", "end", values=vals, tags=(tag,))

def flush_alerts():
    """定时刷新报警缓冲区，将 alerts_buffer 写入报警中心"""
    global alerts_buffer, alerts_history

    next_execution_time = get_next_weekday_time(9, 20)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)

    if alerts_buffer:
        open_alert_center()
        for alert in alerts_buffer:
            if alert_tree:
                # 使用 delta 显示
                delta =  alert.get('rule', {}).get('delta', 0)
                tag = "triggered" if "触发" in alert.get("status", "") else "not_triggered"
                vals = (
                    alert['time'],
                    alert['stock_code'],
                    alert['name'],
                    alert['status'],          # 原状态描述
                    f"现值 {alert.get('value', '')}",
                    f"变化量 {delta}"          # 新增 delta 显示
                )
                alert_tree.insert("", "end", values=vals, tags=(tag,))
            # 将 alert 写入历史
            alerts_history.append(alert)
        alerts_buffer = []

    # 决定下一次 flush 间隔
    if (get_day_is_trade_day() and get_now_time_int() < 1505) or get_work_time():
        root.after(30000, flush_alerts)  # 30 秒刷新
    else:
        root.after(delay_ms, flush_alerts)

def get_latest_valid_data(df):
    # 确保时间字段是可排序的
    df = df.copy()
    df["时间"] = pd.to_datetime(df["时间"], format="%H:%M:%S", errors="coerce")

    # 过滤掉无效数据（价格=0 且 涨幅=0 且 量=0 的行）
    df_valid = df[~((df["价格"] == 0) & (df["涨幅"] == 0) & (df["量"] == 0))]

    # 每个股票取最后一条有效数据
    latest_df = df_valid.sort_values("时间").groupby("代码").tail(1)
    return latest_df

def refresh_all_stock_data():
    # 假设 get_all_stock_data 返回 DataFrame 或 dict
    global loaded_df,realdatadf
    global alerts_buffer,start_init,alerts_rules 
    next_execution_time = get_next_weekday_time(9, 20)
    now = datetime.now()
    delay_ms = int((next_execution_time - now).total_seconds() * 1000)
    sina_realtime_status = False
    df = _get_sina_data_realtime()
    if df is not None and not not df.empty:
        data = df
        sina_realtime_status = True
        for stock_code, row in data.iterrows():
            if stock_code  in alerts_rules:
                price = row.close
                name = row['name']
                percent = round((row.close - row.llastp) / row.llastp *100,1)
                amount = round(row.turnover/100/10000/100,1)
                print(f'sina_data-check_alert:{stock_code} {name}')
                check_alert(stock_code, price, percent, amount , name)

    elif loaded_df is not None and not loaded_df.empty:
        data = loaded_df.copy()  # 每只股票：code, price, change, volume
    elif realdatadf is not None and not realdatadf.empty:
        data = realdatadf.copy()
    else:
        data = _get_stock_changes()

        if '涨幅' not in data.columns:
            data = process_full_dataframe(data)
        data = get_latest_valid_data(data)
        for _, row in data.iterrows():
            stock_code = row["代码"]
            if stock_code  in alerts_rules:
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
    if  get_work_time() :
        # print(f'start flush_alerts')
        if  not 1130 < get_now_time_int() < 1300:
            root.after(60*1000, refresh_all_stock_data)
        else:
            next_time =  int(minutes_to_time(1300)) 
            print(f'refresh_all_stock_data next_update:{next_time} Min')
            root.after(next_time*1000, refresh_all_stock_data)

    else:
        print(f'refresh_all_stock_data next_update work:{delay_ms/1000/60/60} hour')
        root.after(delay_ms, refresh_all_stock_data)

    # if (get_day_is_trade_day() and get_now_time_int() < 1505) or get_work_time() or (start_init == 0 ):
    #     root.after(60*1000, refresh_all_stock_data)
    # else:
    #     root.after(delay_ms, refresh_all_stock_data)

def refresh_alert_centerlist():
    """刷新报警中心UI"""
    global alerts_buffer, alert_center_listbox

    if not alert_center_listbox:
        return

    alert_center_listbox.delete(0, tk.END)

    for alert in alerts_buffer[-100:]:  # 只显示最近 100 条
        time_str = alert.get('time', '')
        code = alert.get('stock_code', '')
        name = alert.get('name', '')
        
        # ✅ 优先用 status 字段（规则 + 当前值 + 触发/未触发）
        status = alert.get('status')
        if not status:
            # 兼容旧数据
            field = alert.get('field', '')
            op = alert.get('rule', {}).get('op', '')
            value = alert.get('rule', {}).get('value', '')
            cur_val = alert.get('value', '')
            if field and op and value != '':
                status = f"{field}{op}{value} (当前 {cur_val})"
            else:
                status = "未知规则"

        display_text = f"[{time_str}] {code} {name} → {status}"
        alert_center_listbox.insert(tk.END, display_text)


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
    if code in alerts_rules:
        del alerts_rules[code]
        save_alerts()
        messagebox.showinfo("删除规则", f"{code} 的规则已删除")

def bind_hotkeys(root):
    """绑定快捷键"""
    root.bind("<F6>", lambda e: rearrange_monitors_per_screen())
    print("✅ 已绑定 F6：一键重排列窗口")


def read_hdf_table(fname, key='all', columns=None):
    """
    精简读取 PyTables HDF5 文件的表格数据，只读，返回 DataFrame。
    
    Parameters
    ----------
    fname : str
        HDF5 文件路径
    key : str
        表名（HDF5 group key）
    columns : list, optional
        指定列读取，默认读取全部
    
    Returns
    -------
    pd.DataFrame
        表格数据
    """
    # try:
    #     df = pd.read_hdf(fname, key=key, columns=columns)
    #     return df
    # except FileNotFoundError:
    #     print(f"文件不存在: {fname}")
    #     return None
    # except KeyError:
    #     print(f"表不存在: {key}")
    #     return None
    # except Exception as e:
    #     print(f"HDF读取出错: {e}")
    #     return None

    # 自动确保 key 以 '/'
    if not key.startswith('/'):
        key = '/' + key

    try:
        with SafeHDFStore(fname, mode='r') as h5:
            if h5 is None:
                print(f"HDF文件无法读取（锁定或不存在）: {fname}")
                return None
            if key not in h5.keys():
                print(f"表不存在: {key}")
                return None
            df = h5[key]  # 读取整个表
            if columns is not None:
                df = df[columns]

            # 如果需要转换 ticktime
            # if convert_ticktime and 'ticktime' in df.columns:
            #     df = df.copy()
            #     df['ticktime'] = df['ticktime'].apply(
            #         lambda x: int(x.strftime('%H%M%S')) if isinstance(x, pd.Timestamp) else x
            #     )

            return df

    except FileNotFoundError:
        print(f"文件不存在: {fname}")
        return None
    except KeyError:
        print(f"表不存在: {key}")
        return None
    except Exception as e:
        print(f"HDF读取出错: {e}")
        return None


#check hdf status
check_hdf5()

init_monitors()
root = tk.Tk()
root.title("股票异动数据监控")
root.geometry("750x550")
root.minsize(500,500)    # 设置最小尺寸限制

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
ths_var = tk.BooleanVar(value=False)
dfcf_var = tk.BooleanVar(value=False)
uniq_var = tk.BooleanVar(value=False)
sub_var = tk.BooleanVar(value=False)

checkbuttons_info = [
    ("TDX", tdx_var),
    ("THS", ths_var),
    ("DC", dfcf_var),
    ("Uniq", uniq_var),
    ("Sub", sub_var)
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
    # print(f'cols:{cols}')
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
        
# 创建搜索框和按钮
search_frame = tk.Frame(root, bg="#f0f0f0", padx=10, pady=10)
search_frame.pack(fill=tk.X, padx=10)

tk.Label(search_frame, text="股票代码搜索:", font=('Microsoft YaHei', 9), 
        bg="#f0f0f0").pack(side=tk.LEFT, padx=(0, 5))

code_entry = tk.Entry(search_frame, width=10, font=('Microsoft YaHei', 9))
code_entry.pack(side=tk.LEFT, padx=5)
code_entry.bind("<KeyRelease>", on_code_entry_change)
code_entry.bind("<Return>", search_by_code)
code_entry.bind("<Button-3>", right_click_paste)

search_btn = tk.Button(search_frame, text="搜索", command=search_by_code, 
                      font=('Microsoft YaHei', 9), bg="#5b9bd5", fg="white",
                      padx=12, pady=2, relief="flat")
search_btn.pack(side=tk.LEFT, padx=2)

clear_btn = tk.Button(search_frame, text="清空", 
                     command=lambda: [code_entry.delete(0, tk.END), search_by_code()],
                     font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
clear_btn.pack(side=tk.LEFT, padx=2)
clear_btn = tk.Button(search_frame, text="清除筛选", 
                     command=lambda: [type_var.set(""), search_by_type()],
                     font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
clear_btn.pack(side=tk.LEFT, padx=2)

btn_rearrange = tk.Button(search_frame, text="窗口重排", command=rearrange_monitors_per_screen,font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
btn_rearrange.pack(side=tk.RIGHT,pady=2)

archive_loader_btn=tk.Button(search_frame, text="存档", command=open_archive_loader,font=('Microsoft YaHei', 9), 
                     padx=10, pady=2)
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
# 启动定时任务调度
schedule_workday_task(root, target_hour, target_minute)

# 首次调用任务，启动定时循环
check_readldf_exist()

schedule_worktime_task(tree)

# 启动定时任务调度
schedule_get_ths_code_task()

# if get_now_time_int() > 1530 and not date_write_is_processed:
#     start_async_save()
schedule_daily_archive(root, hour=15, minute=5, archive_file=None)

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

root.after(10000, flush_alerts)
# 在主程序初始化时调用一次
reset_lift_flags()

refresh_all_stock_data()
bind_hotkeys(root)

root.bind("<FocusIn>", on_window_focus, add="+")
# root.bind("<Configure>", lambda event: update_window_position("main"))
root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, "main"))
root.mainloop()

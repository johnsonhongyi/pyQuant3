import os
import sys
import subprocess
import socket
import pickle
import struct
import warnings
import queue  # 鉁?鍏ㄥ眬寮曞叆 queue 浠ヤ究鎹曡幏 queue.Empty
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
from multiprocessing.managers import BaseManager, SyncManager
class StockManager(SyncManager): pass
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
from tkinter import ttk, messagebox, font as tkfont
from tkinter import filedialog,Menu,simpledialog
import pyqtgraph as pg
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
from JSONData import stockFilter as stf
from logger_utils import LoggerFactory, init_logging, with_log_level
from JohnsonUtil.LoggerFactory import stopLogger # fix logging BrokenPipeError on exit
from stock_live_strategy import StockLiveStrategy
from realtime_data_service import DataPublisher
# DataPublisher is now handled locally in the Main process for resource efficiency
from monitor_utils import (
    load_display_config, save_display_config, save_monitor_list, 
    load_monitor_list, list_archives, archive_file_tools, archive_search_history_list,
    ensure_parentheses_balanced
)
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

from stock_logic_utils import get_row_tags,detect_signals,toast_message
from stock_logic_utils import test_code_against_queries,is_generic_concept,check_code

from db_utils import *
from kline_monitor import KLineMonitor
from stock_selection_window import StockSelectionWindow
from stock_selector import StockSelector
from column_manager import ColumnSetManager
from collections import Counter, OrderedDict, deque
import hashlib
import keyboard  # pip install keyboard
import trade_visualizer_qt6 as qtviz  # 浣犵殑 Qt GUI 妯″潡
from alert_manager import get_alert_manager
from sys_utils import assert_main_thread
import struct, pickle
from queue import Full
from alert_manager import AlertManager

# 鍏ㄥ眬鍗曚緥
logger = init_logging(log_file='instock_tk.log',redirect_print=False) 
# Windows API 甯搁噺
LOGPIXELSX = 88
DEFAULT_DPI = 96.0

if sys.platform.startswith('win'):
    set_process_dpi_awareness()  # 鍋囪璁剧疆涓?Per-Monitor V2
    # 1. 鑾峰彇缂╂斁鍥犲瓙
    scale_factor = get_windows_dpi_scale_factor()
    # 2. 璁剧疆鐜鍙橀噺锛堝湪瀵煎叆 Qt 涔嬪墠锛?    # 绂佺敤 Qt 鑷姩缂╂斁锛屾敼涓烘樉寮忚缃缉鏀惧洜瀛?    # 鎵撳嵃妫€鏌?    logger.info(f"Windows 绯荤粺 DPI 缂╂斁鍥犲瓙: {scale_factor}")
    # logger.info(f"宸茶缃?QT_SCALE_FACTOR = {os.environ['QT_SCALE_FACTOR']}")

from PyQt6 import QtWidgets, QtCore, QtGui
from trading_analyzerQt6 import TradingGUI
from minute_kline_viewer_qt import KlineBackupViewer

# 鉁?鎬ц兘浼樺寲妯″潡瀵煎叆
try:
    from performance_optimizer import (
        TreeviewIncrementalUpdater,
        DataFrameCache,
        PerformanceMonitor,
        optimize_dataframe_operations
    )
    PERFORMANCE_OPTIMIZER_AVAILABLE = True
    logger.info("鉁?鎬ц兘浼樺寲妯″潡宸插姞杞?)
except ImportError as e:
    PERFORMANCE_OPTIMIZER_AVAILABLE = False
    logger.warning(f"鈿狅笍 鎬ц兘浼樺寲妯″潡鏈壘鍒?灏嗕娇鐢ㄤ紶缁熷埛鏂版柟寮? {e}")

# 鉁?鑲＄エ鐗瑰緛鏍囪妯″潡瀵煎叆
try:
    from stock_feature_marker import StockFeatureMarker
    FEATURE_MARKER_AVAILABLE = True
    logger.info("鉁?鑲＄エ鐗瑰緛鏍囪妯″潡宸插姞杞?)
except ImportError as e:
    FEATURE_MARKER_AVAILABLE = False
    logger.warning(f"鈿狅笍 鑲＄エ鐗瑰緛鏍囪妯″潡鏈壘鍒? {e}")


# def ask_exit():
#     """寮瑰嚭纭妗嗭紝璇㈤棶鏄惁閫€鍑?""
#     if messagebox.askyesno("纭閫€鍑?, "浣犵‘瀹氳閫€鍑哄悧锛?):
#         root.destroy()
#         sys.exit(0)

# def signal_handler(sig, frame):
#     """鎹曡幏 Ctrl+C 淇″彿"""
#     # 寮瑰嚭纭妗?#     ask_exit()


conf_ini= cct.get_conf_path('global.ini')
if not conf_ini:
    print("global.ini 鍔犺浇澶辫触锛岀▼搴忔棤娉曠户缁繍琛?)

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

# -------------------- 甯搁噺 -------------------- #
sort_cols: list[str]
sort_keys: list[str]
sort_cols, sort_keys = ct.get_market_sort_value_key('3 0')
DISPLAY_COLS: list[str] = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,sort_cols[:2])

BASE_DIR = get_base_path()

DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)


if not icon_path:
    logger.critical("MonitorTK.ico 鍔犺浇澶辫触锛岀▼搴忔棤娉曠户缁繍琛?)

START_INIT = 0


DEFAULT_DISPLAY_COLS = [
    'name', 'trade', 'boll', 'dff', 'df2', 'couts',
    'percent', 'per1d', 'perc1d', 'ra', 'ral',
    'topR', 'volume', 'red', 'lastdu4', 'category', 'emotion_status'
]

tip_var_status_flag = mp.Value('b', False)  # boolean

from alerts_manager import AlertManager, open_alert_center, set_global_manager, check_alert
def ___toast_message(master, text, duration=1500):
    """鐭殏鎻愮ず淇℃伅锛堟诞灞傦紝涓嶉樆濉烇級"""
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


def get_visualizer_path(file_base='trade_visualizer_qt6'):
    """
    杩斿洖 trade_visualizer_qt6 鐨勮矾寰勶細
    - 寮€鍙戠幆澧?-> .py 鏂囦欢璺緞
    - 鎵撳寘 exe  -> exe 鏂囦欢璺緞
    """
    if getattr(sys, 'frozen', False):
        # 鎵撳寘鍚庣殑 exe 鎵€鍦ㄧ洰褰?        base_path = os.path.dirname(sys.executable)
        path = os.path.join(base_path, f"{file_base}.exe")
        if os.path.exists(path):
            return path
        else:
            logger.error(f"Visualizer exe not found: {path}")
            return None
    else:
        # 寮€鍙戠幆澧?        base_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_path, f"{file_base}.py")
        if os.path.exists(path):
            return path
        else:
            logger.error(f"Visualizer script not found: {path}")
            return None

import functools
def send_with_visualizer(func):
    """瑁呴グ鍣細鍙戦€佽偂绁紝鍚屾椂鏍规嵁 vis_var 鑷姩鎵撳紑鍙鍖?""
    @functools.wraps(func)
    def wrapper(self, code, *args, **kwargs):
        if not code:
            return

        # 1锔忊儯 璋冪敤鍘?send 鏂规硶
        result = func(self, code, *args, **kwargs)

        # 2锔忊儯 鏇存柊鐘舵€侊紙鍙€夛級
        if hasattr(self, 'update_send_status'):
            self.update_send_status(code)

        # 3锔忊儯 鑷姩鍚姩鍙鍖?        if getattr(self, 'vis_var', None) and self.vis_var.get():
            self.open_visualizer(code)

        return result

    return wrapper


# ============================================================================
# 馃洝锔?Qt 瀹夊叏鎿嶄綔涓婁笅鏂囩鐞嗗櫒 - 闃叉 pyttsx3 COM 涓?Qt GIL 鍐茬獊
# ============================================================================
# from contextlib import contextmanager

# @contextmanager
# def qt_safe_operation(app_instance):
#     voice = None
#     voice_paused = False
    
#     try:
#         # 鑾峰彇璇煶寮曟搸
#         if hasattr(app_instance, 'live_strategy') and app_instance.live_strategy:
#             voice = getattr(app_instance.live_strategy, '_voice', None)
#             if voice:
#                 # 鏆傚仠璇煶闃熷垪
#                 getattr(voice, 'pause', lambda: None)()
#                 voice_paused = True
                
#                 # 绛夊緟褰撳墠璇煶瀹夊叏瀹屾垚
#                 if hasattr(voice, 'wait_for_safe'):
#                     import time
#                     start = time.time()
#                     while not voice.wait_for_safe(timeout=0.1):
#                         QtWidgets.QApplication.processEvents()
#                         if time.time() - start > 5.0:
#                             break
#                 else:
#                     QtWidgets.QApplication.processEvents()
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
        # 猸?鍚姩璁℃椂
        self._init_start_time = time.time()
        
        # 馃挜 鍏抽敭淇: 蹇呴』鍦ㄥ垱寤轰换浣曠獥鍙?鍖呮嫭 root)涔嬪墠璁剧疆 DPI 鎰熺煡
        # 鍚﹀垯闈炲鎴峰尯(鏍囬鏍?鏃犳硶姝ｇ‘缂╂斁
        try:
            from dpi_utils import set_process_dpi_awareness
            set_process_dpi_awareness()
        except ImportError:
            pass

        # 鍒濆鍖?tk.Tk()
        super().__init__()
        
        # 馃挜 鍏抽敭淇 1锛氬湪鎵€鏈変唬鐮佹墽琛屽墠锛屽垵濮嬪寲涓哄畨鍏ㄥ€?        self.main_window = self   
        self.scale_factor = 1.0 
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font_size = self.default_font.cget("size")
        self.default_font_bold = tkfont.nametofont("TkDefaultFont").copy()
        self.default_font_bold.configure(family="Microsoft YaHei", size=10, weight="bold")
        # 鍦ㄧ被涓敞鍐屼俊鍙峰鐞?        signal.signal(signal.SIGINT, self.signal_handler)
        global duration_sleep_time
        # 馃挜 鍏抽敭淇 2锛氱珛鍗虫墽琛?DPI 缂╂斁骞堕噸鏂拌祴鍊?        if sys.platform.startswith('win'):
            result_scale = self._apply_dpi_scaling()
            if result_scale is not None and isinstance(result_scale, (float, int)):
                self.scale_factor = result_scale


        self.last_dpi_scale = self.scale_factor
        # 3. 鎺ヤ笅鏉ユ槸 Qt 鍒濆鍖栵紝瀹冧笉搴旇褰卞搷 self.scale_factor
        if not QtWidgets.QApplication.instance():
            self.app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])

        self.title("Stock Monitor")
        self.initial_w, self.initial_h, self.initial_x, self.initial_y  = self.load_window_position(self, "main_window", default_width=1200, default_height=480)
        self.monitor_windows = {}

        # 鍒ゆ柇鏂囦欢鏄惁瀛樺湪鍐嶅姞杞?        if os.path.exists(icon_path):
            self.after(1000, lambda: self.iconbitmap(icon_path))

        else:
            logger.error(f"鍥炬爣鏂囦欢涓嶅瓨鍦? {icon_path}")

        self.sortby_col = None
        self.sortby_col_ascend = None
        self.select_code = None
        self.vis_select_code = None
        self.ColumnSetManager = None
        self.ColManagerconfig = None
        self._open_column_manager_job = None

        self._last_visualizer_code = None
        self._last_visualizer_time = 0
        self._visualizer_debounce_sec = 0.5  # 闃叉姈 0.5 绉?
        self._concept_dict_global = {}

        # 鍒锋柊寮€鍏虫爣蹇?        self.refresh_enabled = True
        self._app_exiting = threading.Event()  # 猸?[FIX] 鐢ㄤ簬鎺у埗鍚庡彴绾跨▼閫€鍑?        
        self.visualizer_process = None # Track visualizer process
        self.qt_process = None         # [FIX] 鍒濆鍖?qt_process 閬垮厤 send_df AttributeError
        self.viz_command_queue = None  # 猸?[FIX] 鎻愬墠鍒濆鍖栭槦鍒楋紝渚?send_df 浣跨敤
        self.viz_lifecycle_flag = mp.Value('b', True) # [FIX] 閲嶅懡鍚嶄负 viz_lifecycle_flag 纭繚鍞竴鎬?        self.sync_version = 0          # 猸?鏁版嵁鍚屾搴忓垪鍙?        self.last_vis_var_status = None 
        # 4. 鍒濆鍖?Realtime Data Service (寮傛鍔犺浇浠ュ姞蹇惎鍔?
        try:
            # 鍚姩 Manager 浠呯敤浜庡悓姝ヨ缃?(global_dict)
            logger.info("姝ｅ湪鍚姩 StockManager (SyncManager) 鐢ㄤ簬鐘舵€佸叡浜?..")
            self.manager = StockManager()
            self.manager.start()
            
            self.global_dict = self.manager.dict()
            self.global_dict["resample"] = resampleInit
            
            # 馃敟 鍚屾鍒濆鍖?DataPublisher (鍚姩鏃剁洿鎺ュ姞杞?
            self.realtime_service = DataPublisher(high_performance=False)
            self._realtime_service_ready = True
            logger.info(f"鉁?RealtimeDataService (Local) 宸插氨缁?(Main PID: {os.getpid()})")

        except Exception as e:
            logger.error(f"鉂?SyncManager 鍒濆鍖栧け璐? {e}\n{traceback.format_exc()}")
            self.realtime_service = None
            self._realtime_service_ready = False
            self.manager = mp.Manager()
            self.global_dict = self.manager.dict()
            self.global_dict["resample"] = resampleInit
            self.global_dict['init_error'] = str(e)
        # Restore global_values initialization
        self.global_values = cct.GlobalValues(self.global_dict)
        
        # [NEW] 棰濆鐩戞帶鍒楄〃锛岀敤浜庣儹鐐瑰疄鏃跺埛鏂?        if 'extra_monitor_codes' not in self.global_dict:
            self.global_dict['extra_monitor_codes'] = []
        resample = self.global_values.getkey("resample")
        logger.info(f'app init getkey resample:{self.global_values.getkey("resample")}')
        self.global_values.setkey("resample", resample)

        self.blkname = ct.Resample_LABELS_Blk[resample] or "060.blk"
        self.global_values.setkey("blkname", self.blkname)

        self._detailed_analysis_win: Optional[tk.Toplevel] = None
        self.strategy_report_win: Optional[tk.Toplevel] = None
        self._voice_monitor_win: Optional[tk.Toplevel] = None
        self._realtime_monitor_win: Optional[tk.Toplevel] = None
        self._stock_selection_win: Optional[tk.Toplevel] = None
        self.txt_widget = None

        # 馃洝锔?鍔ㄦ€佸垪璁㈤槄绠＄悊
        self.mandatory_cols: set[str] = {
            'code', 'name', 'trade', 'high', 'low', 'open', 'ratio', 'volume', 'amount',
            'percent', 'per1d', 'perc1d', 'nclose', 'ma5d', 'ma10d', 'ma20d', 'ma60d',
            'ma51d', 'lastp1d', 'lastp2d', 'lastp3d', 'lastl1d', 'lasto1d', 'lastv1d', 'lasth1d',
            'macddif', 'macddea', 
            'macd', 'macdlast1', 'macdlast2', 'macdlast3', 'rsi', 'kdj_j', 'kdj_k', 
            'kdj_d', 'upper', 'lower', 'max5', 'high4', 'curr_eval', 'trade_signal',
            'now', 'signal', 'signal_strength', 'emotion', 'win', 'sum_perc', 'slope',
            'vol_ratio', 'power_idx', 'category', 'lastdu4',
            'dff', 'dff2', 'Rank', 'buy', 'llastp' # 馃洝锔?澧炲姞鍙鍖栨墍闇€鐨勭己澶卞垪
        }
        self.update_required_columns()

        # ----------------- 鎺т欢妗?----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=1)

        self.st_key_sort = self.global_values.getkey("st_key_sort") or st_key_sort

        # ====== 搴曢儴鐘舵€佹爮 ======
        status_frame = tk.Frame(self, relief="sunken", bd=1)
        status_frame.pack(side="bottom", fill="x")

        # 浣跨敤 PanedWindow 姘村钩鍒嗗壊锛屾敮鎸佹嫋鍔?        pw = tk.PanedWindow(status_frame, orient=tk.HORIZONTAL, sashrelief="sunken", sashwidth=4)
        pw.pack(fill="x", expand=True)

        # 宸︿晶鐘舵€佷俊鎭?        left_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var = tk.StringVar()
        status_label_left = tk.Label(
            left_frame, textvariable=self.status_var, anchor="w", padx=10, pady=1
        )
        status_label_left.pack(fill="x", expand=True)

        # 鍙充晶鐘舵€佷俊鎭?        right_frame = tk.Frame(pw, bg="#f0f0f0")
        self.status_var2 = tk.StringVar()
        status_label_right = tk.Label(
            right_frame, textvariable=self.status_var2, anchor="e", padx=10, pady=1
        )
        status_label_right.pack(fill="x", expand=True)

        # 娣诲姞宸﹀彸闈㈡澘 鐘舵€佹爮
        # 鍔ㄦ€佽皟鏁村搴?        self.update_status_bar_width(pw, left_frame, right_frame)

        # 寤舵椂鏇存柊鐘舵€佹爮瀹藉害
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


        bind_mouse_scroll(self.tree)


        self.current_cols = ["code"] + DISPLAY_COLS
        # TreeView 鍒楀ご
        for col in ["code"] + DISPLAY_COLS:
            width = 80 if col=="name" else 60
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, self.sortby_col_ascend))
            self.tree.column(col, width=width, anchor="center", minwidth=50)


        # 鍙屽嚮琛ㄥご缁戝畾

        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-2>", self.copy_code)
        

        self.df_all = pd.DataFrame()      # 淇濆瓨 fetch_and_process 杩斿洖鐨勫畬鏁村師濮嬫暟鎹?        self.current_df = pd.DataFrame()

        # 闃熷垪鎺ユ敹瀛愯繘绋嬫暟鎹?        self.queue = mp.Queue()

        # UI 鏋勫缓
        self._build_ui(ctrl_frame)

        # checkbuttons 椤堕儴鍙充晶
        self.init_checkbuttons(ctrl_frame)

        # 鉁?鑲＄エ鐗瑰緛鏍囪鍣ㄥ垵濮嬪寲锛堝繀椤诲湪鎬ц兘浼樺寲鍣ㄤ箣鍓嶏級
        if FEATURE_MARKER_AVAILABLE:
            try:
                # 浣跨敤win_var鎺у埗棰滆壊鏄剧ず锛堝鏋渨in_var瀛樺湪锛?                enable_colors = not self.win_var.get() if hasattr(self, 'win_var') else True
                self.feature_marker = StockFeatureMarker(self.tree, enable_colors=enable_colors)
                self._use_feature_marking = True
                logger.info(f"鉁?鑲＄エ鐗瑰緛鏍囪鍣ㄥ凡鍒濆鍖?(棰滆壊鏄剧ず: {enable_colors})")
            except Exception as e:
                logger.warning(f"鈿狅笍 鑲＄エ鐗瑰緛鏍囪鍣ㄥ垵濮嬪寲澶辫触: {e}")
                self._use_feature_marking = False
        else:
            self._use_feature_marking = False
        
        #鎬昏姒傚康鍒嗘瀽鍓?鏉垮潡
        self.concept_top5 = None
        #鍒濆鍖栧欢杩熻繍琛宭ive_strategy
        self._live_strategy_first_run = True
        # 鉁?鍒濆鍖栨爣娉ㄦ墜鏈?        self.handbook = StockHandbook()
        # 鉁?鍒濆鍖栧疄鏃剁洃鎺х瓥鐣?(寤惰繜鍒濆鍖栵紝闃叉闃诲涓荤獥鍙ｆ樉绀?
        self.live_strategy = None
        self.after(3000, self._init_live_strategy)
        
        # 鉁?鍒濆鍖?55188 鏁版嵁鏇存柊鐩戝惉鐘舵€?        self.last_ext_data_ts_local = 0
        # self.after(10000, self._check_ext_data_update)
        
        # 鉁?鎬ц兘浼樺寲鍣ㄥ垵濮嬪寲
        if PERFORMANCE_OPTIMIZER_AVAILABLE:
            try:
                # 浼犲叆feature_marker浠ユ敮鎸佺壒寰佹爣璁?                feature_marker_instance = None
                if FEATURE_MARKER_AVAILABLE and hasattr(self, 'feature_marker'):
                    feature_marker_instance = self.feature_marker
                
                self.tree_updater = TreeviewIncrementalUpdater(
                    self.tree, 
                    self.current_cols,
                    feature_marker=feature_marker_instance
                )
                self.df_cache = DataFrameCache(ttl=5)  # 5绉掔紦瀛?                self.perf_monitor = PerformanceMonitor("TreeUpdate")
                self._use_incremental_update = True
                logger.info("鉁?鎬ц兘浼樺寲鍣ㄥ凡鍒濆鍖?(澧為噺鏇存柊妯″紡)")
            except Exception as e:
                logger.warning(f"鈿狅笍 鎬ц兘浼樺寲鍣ㄥ垵濮嬪寲澶辫触,浣跨敤浼犵粺妯″紡: {e}")
                self._use_incremental_update = False
        else:
            self._use_incremental_update = False
            logger.info("鈩癸笍 浣跨敤浼犵粺鍒锋柊妯″紡")
        
        # 鍚姩鍚庡彴杩涚▼
        self._start_process()

        # 瀹氭椂妫€鏌ラ槦鍒?        self.after(1000, self.update_tree)

        # 鉁?UI 绾跨▼浠诲姟璋冨害闃熷垪 (瑙ｅ喅 Qt -> Tkinter 璺ㄧ嚎绋?GIL 闂)
        self.tk_dispatch_queue = queue.Queue()
        self._process_dispatch_queue()


        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)
        # 馃搵 鍚姩鍚庡彴鍓创鏉跨洃鍚湇鍔?(鍖呭惈鑷姩鏌ラ噸閫昏緫锛岄伩鍏嶉噸澶嶅彂閫佸綋鍓嶅凡閫変腑浠ｇ爜)
        self.clipboard_monitor = start_clipboard_listener(
            self.sender, 
            ignore_func=lambda code: code == getattr(self, 'select_code', None)
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)  
        # self.tree.bind("<Button-1>", self.on_single_click)
        # 鉁?缁戝畾鍗曞嚮浜嬩欢鐢ㄤ簬鏄剧ず鑲＄エ淇℃伅鎻愮ず妗?        # self.tree.bind("<ButtonRelease-1>", self.on_tree_click_for_tooltip)
        # 缁戝畾鍙抽敭鐐瑰嚮浜嬩欢
        self.tree.bind("<Button-3>", self.on_tree_right_click)

        self.bind("<Alt-c>", lambda e:self.open_column_manager())

        # [NEW] 姣忔棩澶嶇洏鍏ュ彛鎸夐挳
        try:
             from market_pulse_viewer import MarketPulseViewer
             self._pulse_viewer_class = MarketPulseViewer
             pulse_btn = tk.Button(ctrl_frame, text="姣忔棩澶嶇洏", 
                                 bg="purple", fg="white", 
                                 font=self.default_font_bold,
                                 command=self.open_market_pulse)
             pulse_btn.pack(side="left", padx=5)
        except ImportError as e:
             logger.error(f"Failed to import MarketPulseViewer: {e}")
             self._pulse_viewer_class = None

        self.bind("<Alt-d>", lambda event: self.open_handbook_overview())
        self.bind("<Alt-e>", lambda event: self.open_voice_monitor_manager())
        self.bind("<Alt-g>", lambda event: self.open_trade_report_window())
        self.bind("<Alt-b>", lambda event: self.close_all_alerts())
        self.bind("<Alt-s>", lambda event: self.open_strategy_manager())
        self.bind("<Alt-k>", lambda event: self.open_market_pulse())
        # 鍚姩鍛ㄦ湡妫€娴?RDP DPI 鍙樺寲
        self.after(3000, self._check_dpi_change)
        self.auto_adjust_column = self.dfcf_var.get()
        # self.bind("<Configure>", self.on_resize)
        
        # 猸?鍚姩瀹屾垚璁℃椂
        init_elapsed = time.time() - self._init_start_time
        logger.info(f"馃殌 绋嬪簭鍒濆鍖栧畬鎴?(鎬昏€楁椂: {init_elapsed:.2f}s)")
        if logger.level == LoggerFactory.DEBUG:
            cct.print_timing_summary(top_n=6)

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

    def _process_dispatch_queue(self):
        """
        [FIX] 涓撻棬澶勭悊浠?Qt 鍥炶皟鎴栧叾浠栭潪涓荤嚎绋嬪彂鏉ョ殑 Tkinter 浠诲姟銆?        閬垮厤鐩存帴鍦?Qt 绾跨▼璋冪敤 Tkinter (self.after 涔熶笉琛?銆?        """
        try:
            while True:
                # 闈為樆濉炶幏鍙栦换鍔?                task = self.tk_dispatch_queue.get_nowait()
                if callable(task):
                    try:
                        task()
                    except Exception as e:
                        logger.error(f"Error executing dispatched task: {e}\n{traceback.format_exc()}")
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Error in dispatch queue processing: {e}")
        finally:
            # 100ms 鍚庡啀娆℃鏌?            self.after(100, self._process_dispatch_queue)


    def signal_handler(self, sig, frame):
        """鎹曡幏 Ctrl+C 淇″彿"""
        self.ask_exit()
        
    def send_command_to_visualizer(self, cmd_str):
        """
        鍙戦€佹寚浠ゅ埌 Visualizer (Port: 26668)
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
            messagebox.showwarning("Connection Error", "鏃犳硶杩炴帴鍒板彲瑙嗗寲绐楀彛锛岃纭瀹冨凡鍚姩銆?)

    def ask_exit(self):
        """寮瑰嚭纭妗嗭紝璇㈤棶鏄惁閫€鍑?""
        if messagebox.askyesno("纭閫€鍑?, "浣犵‘瀹氳閫€鍑?StockApp 鍚楋紵"):
            self.on_close()
    # 鍦ㄥ垵濮嬪寲 UI 鎴栧悗鍙扮嚎绋嬮噷
    def setup_global_hotkey(self):
        """
        娉ㄥ唽绯荤粺鍏ㄥ眬蹇嵎閿?Alt+B锛岃皟鐢?close_all_alerts
        """
        def _on_hotkey_close_all_alerts():
            # 蹇呴』閫氳繃 Tkinter 鐨?after 璋冪敤锛屼繚璇佸湪涓荤嚎绋嬫墽琛?            self.after(0, self.close_all_alerts)

        def _on_hotkey_voice_monitor_manager():
            # 蹇呴』閫氳繃 Tkinter 鐨?after 璋冪敤锛屼繚璇佸湪涓荤嚎绋嬫墽琛?            self.after(0, self.open_voice_monitor_manager)
        def _on_hotkey_trategy_manager():
            # 蹇呴』閫氳繃 Tkinter 鐨?after 璋冪敤锛屼繚璇佸湪涓荤嚎绋嬫墽琛?            self.after(0, self.open_strategy_manager)
        def _on_hotkey_open_market_pulser():
            # 蹇呴』閫氳繃 Tkinter 鐨?after 璋冪敤锛屼繚璇佸湪涓荤嚎绋嬫墽琛?            self.after(0, self.open_market_pulse)
            
        # 娉ㄥ唽绯荤粺鍏ㄥ眬蹇嵎閿?        keyboard.add_hotkey('alt+b', _on_hotkey_close_all_alerts)
        keyboard.add_hotkey('alt+e', _on_hotkey_voice_monitor_manager)
        keyboard.add_hotkey('alt+s', _on_hotkey_trategy_manager)
        keyboard.add_hotkey('alt+k', _on_hotkey_open_market_pulser)
        # [NEW] Alt+H to toggle Hotlist
        keyboard.add_hotkey('alt+h', lambda: self.after(0, lambda: self.send_command_to_visualizer("TOGGLE_HOTLIST")))

    def on_resize(self, event):
        if event.widget != self:
            return
        # 鏍囪 resize 杩涜涓?        self._is_resizing = True
        if hasattr(self, "_resize_after_id") and self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        # 鍙湁鈥滃仠涓嬫潵鈥濇墠瑙﹀彂鐪熸鍒锋柊
        self._resize_after_id = self.after(
            300,
            self._on_resize_finished
        )

    # def listener():
    #     logger.info(f"[Pipe] Feedback listener ready on {PIPE_NAME_TK}")

    #     while True:
    #         pipe = None
    #         try:
    #             pipe = win32pipe.CreateNamedPipe(
    #                 PIPE_NAME_TK,
    #                 win32pipe.PIPE_ACCESS_DUPLEX,
    #                 win32pipe.PIPE_TYPE_MESSAGE |
    #                 win32pipe.PIPE_READMODE_MESSAGE |
    #                 win32pipe.PIPE_WAIT,
    #                 win32pipe.PIPE_UNLIMITED_INSTANCES,
    #                 65536, 65536,
    #                 0,
    #                 None
    #             )

    #             win32pipe.ConnectNamedPipe(pipe, None)

    #             while True:
    #                 res, data = win32file.ReadFile(pipe, 65536)
    #                 if res != 0 or not data:
    #                     break

    #                 msg = data.decode("utf-8")
    #                 logger.info(f"[Pipe] recv: {msg}")

    #                 try:
    #                     obj = json.loads(msg)
    #                 except Exception:
    #                     obj = None

    #                 if obj and obj.get("cmd") == "REQ_FULL_SYNC":
    #                     logger.info(f'[Pipe] Feedback listener cmd REQ_FULL_SYNC')
    #                     self._force_full_sync_pending = True
    #                     self._df_first_send_done = False
                    
    #                 elif obj and obj.get("cmd") == "VIZ_EXIT":
    #                     logger.info(f'[Pipe] Visualizer exited. Cleaning up qt_process state.')
    #                     self.qt_process = None
    #                     self.viz_command_queue = None
    #                     if hasattr(self, 'viz_stop_flag'):
    #                         self.viz_stop_flag.value = True # Reset for next launch
                    
    #                 elif obj and obj.get("cmd") == "ADD_MONITOR":
    #                     code = obj.get("code")
    #                     if code:
    #                         logger.info(f'[Pipe] Feedback listener cmd ADD_MONITOR: {code}')
    #                         try:
    #                             current_list = list(self.global_dict.get('extra_monitor_codes', []))
    #                             if code not in current_list:
    #                                 current_list.append(code)
    #                                 self.global_dict['extra_monitor_codes'] = current_list
    #                                 logger.info(f"鉁?Added {code} to extra_monitor_codes")
    #                                 # 鍚屾椂涔熻Е鍙戜竴娆″己鍒跺叏閲忓悓姝ワ紝纭繚鏂颁唬鐮佽兘椋為€熷嚭鐜板湪鍙鍖栧櫒涓?    #                                 self._force_full_sync_pending = True
    #                         except Exception as e:
    #                             logger.error(f"Failed to update extra_monitor_codes: {e}")

    #         except Exception as e:
    #             logger.debug(f"[Pipe] listener error: {e}")
    #             time.sleep(1)

    #         finally:
    #             if pipe:
    #                 win32pipe.DisconnectNamedPipe(pipe)
    #                 win32file.CloseHandle(pipe)

    def _start_feedback_listener(self):
        """
        鐩戝惉鏉ヨ嚜鍙鍖栧櫒鐨勬帶鍒舵寚浠わ紙濡?REQ_FULL_SYNC锛?        浣跨敤鐙珛鎺у埗绠￠亾锛岀煭杩炴帴锛屽己鍋ュ閿?        """
        import win32pipe, win32file, pywintypes, winerror
        import json, threading, time
        from data_utils import PIPE_NAME_TK

        def listener():
            logger.info(f"[Pipe] Feedback listener ready on {PIPE_NAME_TK}")

            # 鈿狅笍 閫€鍑洪椄闂紙濡傛灉澶栭儴娌″畾涔夛紝灏卞厹搴曚竴涓級
            app_exiting = getattr(self, "_app_exiting", None)

            while True:
                # ====== 鍏ㄥ眬閫€鍑哄垽鏂?======
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
                        # 鉀?姝ｅ父閫€鍑哄満鏅紙搴旂敤鍏抽棴 / 瀵圭娑堝け锛?                        if app_exiting and app_exiting.is_set():
                            break
                        raise

                    # ====== 宸插缓绔嬭繛鎺ワ紝寮€濮嬭鍙?======
                    while True:
                        if app_exiting and app_exiting.is_set():
                            break

                        try:
                            res, data = win32file.ReadFile(pipe, 65536)
                        except pywintypes.error as e:
                            # Windows 绠￠亾姝ｅ父鏂紑锛堜笉瑕佸綋寮傚父鍒锋棩蹇楋級
                            if e.winerror in (winerror.ERROR_BROKEN_PIPE,
                                              winerror.ERROR_NO_DATA,
                                              winerror.ERROR_INVALID_HANDLE):
                                break
                            raise

                        if res != 0 or not data:
                            break

                        msg = data.decode("utf-8", errors="ignore")
                        logger.info(f"[Pipe] recv: {msg}")

                        try:
                            obj = json.loads(msg)
                        except Exception:
                            obj = None

                        # ================== 鍘熸湁閫昏緫锛氬畬鍏ㄤ繚鐣?==================

                        if obj and obj.get("cmd") == "REQ_FULL_SYNC":
                            logger.info('[Pipe] Feedback listener cmd REQ_FULL_SYNC')
                            self._force_full_sync_pending = True
                            self._df_first_send_done = False

                        elif obj and obj.get("cmd") == "VIZ_EXIT":
                            logger.info('[Pipe] Visualizer exited. Cleaning up qt_process state.')
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
                                        logger.info(f"鉁?Added {code} to extra_monitor_codes")
                                        # 鍚屾椂涔熻Е鍙戜竴娆″己鍒跺叏閲忓悓姝?                                        self._force_full_sync_pending = True
                                except Exception as e:
                                    logger.error(f"Failed to update extra_monitor_codes: {e}")

                except pywintypes.error as e:
                    # 姝ｅ父閫€鍑洪敊璇爜 鈫?闈欓粯閫€鍑?                    if app_exiting and app_exiting.is_set():
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

        # ====== 纭繚涓诲悓姝ョ嚎绋嬪彧鍚姩涓€娆?======
        if not hasattr(self, "_df_sync_thread") or not self._df_sync_thread.is_alive():
            self._df_sync_running = True
            self._df_sync_thread = threading.Thread(
                target=self.send_df,
                name="DFSyncThread",
                daemon=True
            )
            self._df_sync_thread.start()

        # ====== 鍚姩鎺у埗鐩戝惉绾跨▼ ======
        threading.Thread(
            target=listener,
            name="PipeCtrlListener",
            daemon=True
        ).start()


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
            logger.info("schedule_15_30_job锛屽紑濮媉last_run_date...")
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

        # 鉁?姣忔棩閲嶇疆瀹炴椂鏈嶅姟鐘舵€?        # if self.realtime_service:
        #     try:
        #         self.realtime_service.reset_state()
        #         logger.info("鉁?RealtimeService daily reset triggered.")
        #     except Exception as e:
        #         logger.error(f"鉂?RealtimeService reset failed: {e}")

        if hasattr(self, "live_strategy"):
            try:
                # 鎻愬彇绐楀彛鍚嶇О鐢ㄤ簬淇濆瓨浣嶇疆
                # unique_code 鏍煎紡涓?"concept_name_code" 鎴?"concept_name"
                now_time = cct.get_now_time_int()
                if now_time > 1500:
                    self.live_strategy._save_monitors()
                    logger.info(f"[on_close] self.live_strategy._save_monitors SAVE OK")
                else:
                    logger.info(f"[on_close] now:{now_time} 鏈埌鏀剁洏鏃堕棿 鏈繘琛宊save_monitors SAVE")

            except Exception as e:
                logger.warning(f"[on_close] self.live_strategy._save_monitors 澶辫触: {e}")

        today = cct.get_today('')
        if write_all_day_date == today:
            logger.info(f'Write_market_all_day_mp 宸茬粡瀹屾垚')
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
            else:
                logger.info(f"today: {today} is trade_date :{cct.get_trade_date_status()} not to Write_market_all_day_mp")

        finally:
            self._task_running = False

    # --- DPI and Window management moved to Mixins ---
    @with_log_level(LoggerFactory.INFO)
    def on_close(self):
        try:
            # 璁剧疆閫€鍑烘爣蹇楋紝闃绘鍚庡彴绾跨▼璋冪敤 Tkinter 鏂规硶
            if hasattr(self, '_app_exiting'):
                self._app_exiting.set()  # 猸?[FIX] 绔嬪嵆閫氱煡鎵€鏈夌洃鍚嚎绋嬮€€鍑?            self._is_closing = True
            self.close_all_alerts()
            # 0.1 绔嬪嵆鍏抽棴鎵€鏈夋姤璀﹀脊绐楋紙鍋滄闇囧姩/闂儊寰幆锛?            if hasattr(self, 'active_alerts'):
                for win in list(self.active_alerts):
                    try:
                        win.is_shaking = False
                        win.is_flashing = False
                        if win.winfo_exists():
                            win.destroy()
                    except Exception:
                        pass
                self.active_alerts.clear()
            
            # 淇濆瓨 UI 鐘舵€?            self.save_ui_states()

            if hasattr(self, 'code_to_alert_win'):
                self.code_to_alert_win.clear()
            
            logger.info("绋嬪簭姝ｅ湪閫€鍑猴紝鎵ц淇濆瓨涓庢竻鐞?..")
            self.vis_var.set(False)
            # 1. 淇濆瓨棰勮瑙勫垯
            if hasattr(self, 'alert_manager'):
                self.alert_manager.save_all()
                logger.info("棰勮瑙勫垯宸蹭繚瀛?)
                
            # 2. 瀛樻。浜ゆ槗鏃ュ織 (TradingLogger)
            try:
                t_logger = TradingLogger()
                archive_file_tools(t_logger.db_path, "trading_signals", ARCHIVE_DIR, logger)
            except Exception as e:
                logger.warning(f"浜ゆ槗鏃ュ織瀛樻。澶辫触: {e}")
            
            # 3. 瀛樻。鎵嬫湱
            if hasattr(self, 'handbook'):
                try:
                    archive_file_tools(self.handbook.data_file, "stock_handbook", ARCHIVE_DIR, logger)
                except Exception as e:
                    logger.warning(f"鎵嬫湱瀛樻。澶辫触: {e}")
                    
            try:
                archive_file_tools(VOICE_ALERT_CONFIG_FILE, "voice_alert_config", ARCHIVE_DIR, logger)
            except Exception as e:
                logger.warning(f"鎵嬫湱瀛樻。澶辫触: {e}")

            # 4. 濡傛灉 concept 绐楀彛瀛樺湪锛屼篃淇濆瓨浣嶇疆骞堕殣钘?            if hasattr(self, "_concept_win") and self._concept_win:
                if self._concept_win.winfo_exists():
                    self.save_window_position(self._concept_win, "detail_window")
                    self._concept_win.destroy()
            
            # 5. 濡傛灉 KLineMonitor 瀛樺湪涓旇繕娌￠攢姣侊紝淇濆瓨浣嶇疆
            if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                try:
                    self.save_window_position(self.kline_monitor, "KLineMonitor")
                    self.kline_monitor.on_kline_monitor_close()
                    self.kline_monitor.destroy()
                except Exception:
                    pass

            # 6. 淇濆瓨骞跺叧闂墍鏈?monitor_windows锛堟蹇靛墠10绐楀彛锛?            if hasattr(self, "live_strategy"):
                try:
                    now_time = cct.get_now_time_int()
                    if now_time > 1500:
                        self.live_strategy._save_monitors()
                        logger.info(f"[on_close] self.live_strategy._save_monitors SAVE OK")
                    else:
                        logger.info(f"[on_close] now:{now_time} 涓嶅埌鏀剁洏鏃堕棿 鏈繘琛宊save_monitors SAVE OK")
                except Exception as e:
                    logger.warning(f"[on_close] self.live_strategy._save_monitors 澶辫触: {e}")
                
                # 6.5 鍋滄绛栫暐寮曟搸鍚庡彴浠诲姟 (鍖呭惈璇煶绾跨▼鍜岀嚎绋嬫睜)
                try:
                    self.live_strategy.stop()
                except Exception as e:
                    logger.warning(f"[on_close] self.live_strategy.stop 澶辫触: {e}")


            # 7. 鍏抽棴鎵€鏈?concept top10 绐楀彛 (Tkinter 鐗?
            if hasattr(self, "_pg_top10_window_simple"):
                try:
                    self.save_all_monitor_windows()
                    for key, win_info in list(self._pg_top10_window_simple.items()):
                        win = win_info.get("win")
                        if win and win.winfo_exists():
                            try:
                                if hasattr(win, "on_close") and callable(win.on_close):
                                    win.on_close()
                                else:
                                    win.destroy()
                            except Exception as e:
                                logger.info(f"鍏抽棴绐楀彛 {key} 鍑洪敊: {e}")
                    self._pg_top10_window_simple.clear()
                except Exception as e:
                    logger.warning(f"鍏抽棴 TK 鐩戞帶绐楀彛寮傚父: {e}")

            # 8. 鍏抽棴鎵€鏈夌洃瑙嗙獥鍙?(PyQt 鐗?
            if hasattr(self, "_pg_windows"):
                try:
                    for key, win_info in list(self._pg_windows.items()):
                        win = win_info.get("win")
                        if win is not None:
                            try:
                                if hasattr(win, "on_close") and callable(win.on_close):
                                    win.on_close()
                                else:
                                    win.close()
                            except Exception as e:
                                logger.info(f"鍏抽棴 Qt 绐楀彛 {key} 鍑洪敊: {e}")
                    self._pg_windows.clear()
                except Exception as e:
                    logger.warning(f"鍏抽棴 Qt 鐩戞帶绐楀彛寮傚父: {e}")

            # 9. 淇濆瓨涓荤獥鍙ｄ綅缃笌鎼滅储璁板綍
            self.save_window_position(self, "main_window")
            if hasattr(self, 'query_manager'):
                self.query_manager.save_search_history()
            
            try:
                archive_search_history_list(
                    monitor_list_file=MONITOR_LIST_FILE, 
                    search_history_file=SEARCH_HISTORY_FILE, 
                    archive_dir=ARCHIVE_DIR, 
                    logger=logger
                )
            except Exception as e:
                logger.warning(f"鎼滅储鍘嗗彶褰掓。澶辫触: {e}")

            # 10. 鍋滄鍚庡彴杩涚▼涓庣鐞嗗櫒 (鍏抽敭椤哄簭锛氬厛鍋滆繘绋嬶紝鍐嶅仠绠＄悊鍣?
            self.stop_refresh()
            # if getattr(self, 'qt_process', None):
            #     self.qt_process.join(timeout=2)
            #     if self.qt_process  and self.qt_process.is_alive():
            #         logger.info("姝ｅ湪鍋滄鍚庡彴qt_process杩涚▼...")
            #         self.qt_process.terminate()
            #         self.qt_process.join()
            #         self.qt_process = None
            # ===== 3. 鍋滄帀鍚庡彴绾跨▼ =====
            if hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
                logger.info("姝ｅ湪鍋滄 df_all 鍚屾绾跨▼...")
                # 绾跨▼鏄?daemon=True, 浼氶殢涓荤嚎绋嬮€€鍑猴紝涔熷彲璁剧疆鏍囧織 self._df_sync_flag = False 鏉ヤ紭闆呴€€鍑?                # self._df_sync_flag = False
                self._df_sync_running = False
                self._df_sync_thread.join(timeout=2)
                if self.viz_command_queue:
                    self.viz_command_queue = None
                self._df_sync_thread = None

            # 鍏堝仠姝?Qt 瀛愯繘绋?            # 鍏堝仠姝?Qt 瀛愯繘绋?[FIX: Race Condition safe]
            qtz_proc = getattr(self, 'qt_process', None)
            if qtz_proc is not None:
                try:
                    if qtz_proc.is_alive():
                        # 璁剧疆 stop_flag 璁?Qt 瀛愯繘绋嬪惊鐜€€鍑?                        if hasattr(self, 'viz_lifecycle_flag'):
                            self.viz_lifecycle_flag.value = False
                            logger.info("Setting viz_lifecycle_flag to False (App Exit)")
                        
                        # 鍏煎鏃т唬鐮?(濡傛灉鏈?
                        if hasattr(self, 'stop_flag'):
                            self.stop_flag.value = False

                        qtz_proc.join(timeout=2)
                        if qtz_proc.is_alive():
                            qtz_proc.terminate()
                            qtz_proc.join()
                except Exception as e:
                    logger.error(f"Error stopping qt_process: {e}")
                
                self.qt_process = None
              
            if hasattr(self, "proc") and self.proc.is_alive():
                logger.info("姝ｅ湪鍋滄鍚庡彴鏁版嵁鎵弿杩涚▼...")
                self.proc.join(timeout=1)
                if self.proc.is_alive():
                    self.proc.terminate()
                    logger.info("鍚庡彴杩涚▼宸插己鍒剁粓姝?)
                else:
                    logger.info("鍚庡彴杩涚▼宸插畨鍏ㄩ€€鍑?)

            # 11. 鍋滄鏃ュ織涓庨攢姣?            try:
                # 鏄惧紡鍋滄鏃ュ織鐩戝惉绾跨▼锛岄槻姝?BrokenPipeError
                # 鏀惧湪 manager.shutdown 涔嬪墠鏇村畨鍏紝闃叉 manager 鍏抽棴绠￠亾瀵艰嚧 listener 宕╂簝
                stopLogger() 
            except Exception: 
                pass

            if hasattr(self, "manager"):
                try:
                    # 10.5 閫€鍑哄墠寮哄埗淇濆瓨 K 绾胯褰曪紝纭繚鏁版嵁娓呮礂鎴愭灉鎸佷箙鍖?                    if hasattr(self, "realtime_service") and self.realtime_service:
                        logger.info("姝ｅ湪鎵ц MinuteKlineCache 閫€鍑轰繚瀛?..")
                        self.realtime_service.save_cache(force=True)

                    # 鏂紑浠ｇ悊寮曠敤锛岄槻姝?shutdown 鏃剁殑 BrokenPipe
                    self.realtime_service = None
                    self.global_dict = None
                    self.manager.shutdown()
                    # logger.info("SyncManager 宸插畨鍏ㄥ叧闂?) # Logger 宸插仠锛屾澶勪笉鍐嶅啓鏃ュ織
                except Exception:
                    pass

            self.destroy()
            logger.info("绋嬪簭姝ｅ父閫€鍑哄畬鎴?) # 姝ゆ潯鍙兘涓嶄細鏄剧ず锛屽洜涓?Listener 宸插仠姝?            
        except Exception as e:
            logger.error(f"閫€鍑鸿繃绋嬪彂鐢熶弗閲嶅紓甯? {e}\n{traceback.format_exc()}")
            try:
                self.destroy()
            except:
                pass


    # 闃叉姈 resize锛堥伩鍏嶉噸澶嶅埛鏂帮級
    # ---------------------------
    def _on_open_column_manager(self):
        if self._open_column_manager_job:
            self.after_cancel(self._open_column_manager_job)
        self._open_column_manager_job = self.after(1000, self.open_column_manager)

    def open_column_manager(self):
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config(config_file=CONFIG_FILE,default_cols=DEFAULT_DISPLAY_COLS)
                # 鍒涘缓鏂扮獥鍙?                self.global_dict['keep_all_columns'] = True  # 寮€鍚?鍙戠幇妯″紡": 鍏佽鍚庡彴鑾峰彇鎵€鏈夊垪渚涚敤鎴烽€夋嫨
                self.ColumnSetManager = ColumnSetManager(
                    self,
                    self.df_all.columns,
                    self.ColManagerconfig,
                    self.update_treeview_cols,  # 鍥炶皟鏇存柊鍑芥暟
                    default_cols=self.current_cols,  # 榛樿鍒?                    logger=logger,  # logger
                        )
                # 鍏抽棴鏃舵竻鐞嗗紩鐢?                self.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.on_close_column_manager)
            else:
                self.after(1000,self._on_open_column_manager)

    def open_column_manager_init(self):
        def _on_open_column_manager_init():
            if self._open_column_manager_job:
                self.after_cancel(self._open_column_manager_job)
            self._open_column_manager_job = self.after(1000, self.open_column_manager_init)
        
        if self.ColumnSetManager is not None and self.ColumnSetManager.winfo_exists():
            self.ColumnSetManager.open_column_manager_editor()
        else:
            if not self.df_all.empty:
                self.ColManagerconfig = load_display_config(config_file=CONFIG_FILE,default_cols=DEFAULT_DISPLAY_COLS)
                # 鍒涘缓鏂扮獥鍙?                if hasattr(self, 'global_dict') and self.global_dict is not None:
                    self.global_dict['keep_all_columns'] = True
                self.ColumnSetManager = ColumnSetManager(
                    self,
                    self.df_all.columns,
                    self.ColManagerconfig,
                    self.update_treeview_cols,  # 鍥炶皟鏇存柊鍑芥暟
                    default_cols=self.current_cols,  # 榛樿鍒?                    auto_apply_on_init=True     #   鉁?鍒濆鍖栬嚜鍔ㄦ墽琛?apply_current_set()
                        )
                # 鍏抽棴鏃舵竻鐞嗗紩鐢?                self.ColumnSetManager.protocol("WM_DELETE_WINDOW", self.on_close_column_manager)
                # DISPLAY_COLS = self.current_cols
            else:
                self.after(1000,_on_open_column_manager_init)

    def on_close_column_manager(self):
        if self.ColumnSetManager is not None:
            self.ColumnSetManager.destroy()
            self.ColumnSetManager = None
            self._open_column_manager_job = None
            if hasattr(self, 'global_dict') and self.global_dict is not None:
                 self.global_dict['keep_all_columns'] = True  # 鍏抽棴鍙戠幇妯″紡
            self.update_required_columns() # 鎭㈠鎸夐渶瑁佸壀

    def update_required_columns(self, refresh_ui=False) -> None:
        """鍚屾褰撳墠 UI 鍜岀瓥鐣ユ墍闇€鐨勫垪鍒板悗鍙拌繘绋?""
        # mandatory_cols鍔ㄦ€佸姞杞藉垪涓嶈鏀筪f_all鍩虹鏁版嵁col,瀵艰嚧鍏朵粬鍑虹幇col纭疄, update_required_columns 鍙槸鐢ㄦ潵鍚屾鍙鍖栨暟鎹?涓嶈鏀瑰熀纭€鏁版嵁
        pass
        # try:
        #     if not hasattr(self, 'global_dict') or self.global_dict is None:
        #         return
            
        #     # 杩欓噷鐨?self.current_cols 瀛樺偍浜嗗綋鍓?UI 鐪熸鏄剧ず鐨勫垪
        #     current_ui_cols = set(getattr(self, 'current_cols', []))
            
        #     # 浣跨敤鏇翠弗璋ㄧ殑鑾峰彇鏂瑰紡
        #     mandatory = getattr(self, 'mandatory_cols', set())
        #     required = set(mandatory).union(current_ui_cols)
            
        #     # 鏇存柊鍒?global_dict 渚涘悗鍙拌繘绋嬭鍙?        #     self.global_dict['required_cols'] = list(required)
        #     logger.debug(f"Dynamic Trimming: Subscribed to {len(required)} columns.")
        # except Exception as e:
        #     logger.error(f"Failed to update required columns: {e}")

    # def tree_scroll_to_code(self, code):
    #     """澶栭儴璋冪敤锛氬畾浣嶇壒瀹氫唬鐮?""
    #     if hasattr(self, 'search_var1'):
    #         self.search_var1.set(code)
    #         self.apply_search()

    def get_stock_code_none(self, code=None):
        df_all = self.df_all.copy()

        # --- 濡傛灉娌℃湁 percent 鍒楋紝鐢?per1d 琛ュ厖 ---
        if 'percent' not in df_all.columns and 'per1d' in df_all.columns:
            df_all['percent'] = df_all['per1d']
        elif 'percent' in df_all.columns and 'per1d' in df_all.columns:
            # 浼樺厛浣跨敤闈炵┖涓旈潪0鐨刾ercent锛屽惁鍒欑敤per1d
            df_all['percent'] = df_all.apply(
                lambda r: r['per1d'] if pd.isna(r['percent']) or r['percent'] == 0 else r['percent'],
                axis=1
            )

        # --- 鍒ゆ柇鏄惁闇€瑕佺敤 per1d 鏇挎崲 ---
        zero_ratio = (df_all['percent'] == 0).sum() / len(df_all)
        extreme_ratio = ((df_all['percent'] >= 100) | (df_all['percent'] <= -100)).mean()

        # 濡傛灉鍋滅墝鍗犳瘮楂?鎴?鏈?卤100% 鐨勫紓甯革紝浣跨敤 per1d
        use_per1d = (zero_ratio > 0.5 or extreme_ratio > 0.01) and 'per1d' in df_all.columns

        if use_per1d:
            df_all['percent'] = df_all['per1d']

        # --- 澶勭悊 code ---
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
        鍏ㄥ眬鍒濆鍖栨蹇垫暟鎹?        force_reset: True 琛ㄧず寮哄埗閲嶆柊鍔犺浇褰撳ぉ鏁版嵁
        """
        today = datetime.now().date()
        
        # 鍒ゆ柇鏄惁闇€瑕侀噸缃?        need_reset = force_reset or not hasattr(self, "_concept_data_loaded") or getattr(self, "_concept_data_date", None) != today

        if need_reset:
            self._concept_data_loaded = True
            self._concept_data_date = today

            # 璇诲彇褰撳ぉ鎵€鏈?concept 鏁版嵁
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
                # 鍒濆鍖?base_data
                if c_name not in self._global_concept_init_data:
                    # 鍏ㄥ眬娌℃湁鏁版嵁锛屽垵濮嬪寲鍩虹鏁版嵁
                    base_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_init_data[c_name] = base_data
                    # logger.info("[DEBUG] 宸插垵濮嬫蹇垫暟鎹?_init_prev_concepts_data)")
        else:
            for i, c_name in enumerate(concepts):
                # 鍒濆鍖?prev_data
                if c_name not in self._global_concept_prev_data:
                    prev_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_prev_data[c_name] = prev_data
                    # logger.info("[DEBUG] 宸插垵濮嬫蹇垫暟鎹?_init_prev_concepts_data)")
            logger.debug(f"[init_global_concept_data] 鏂板 prev_data: {concepts[0]}")


    def get_following_concepts_by_correlation(self, code, top_n=10):
        def compute_follow_ratio(percents, stock_percent):
            """
            percents: 姒傚康鍐呮墍鏈夎偂绁ㄦ定骞呭垪琛?            stock_percent: 鐩爣鑲＄エ鎴栧ぇ鐩樻定骞?            """
            percents = np.array(percents)
            stock_sign = np.sign(stock_percent)
            stock_sign = 1 if stock_sign > 0 else (-1 if stock_sign < 0 else 0)
            # 姒傚康鍐呮瘡鍙偂绁ㄦ槸鍚﹁窡闅?            follow_flags = np.sign(percents) == stock_sign
            return follow_flags.sum() / len(percents)
        # logger.info(f"by_correlation [Debug] df_all_hash={df_hash(self.df_all)} len={len(self.df_all)} time={datetime.now():%H:%M:%S}")
        df_all = self.df_all.copy()
        # --- 鉁?淇娑ㄥ箙鏇夸唬閫昏緫 ---
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
            raise ValueError("DataFrame 蹇呴』鍖呭惈 'percent' 鎴?'per1d' 鍒?)

        # --- 鑾峰彇鐩爣鑲＄エ娑ㄥ箙 ---
        try:
            stock_percent = df_all.loc[code, 'percent']
            stock_row = df_all.loc[code]
        except Exception:
            try:
                stock_row = df_all.loc[code]
                stock_percent = stock_row['percent']
            except Exception:
                logger.info(f"[WARN] 鏈壘鍒?{code} 鐨勬暟鎹?)
                return []
        # --- 鑾峰彇鑲＄エ鎵€灞炵殑姒傚康鍒楄〃 ---
        # stock_row = df_all.loc[code]
        stock_categories = [
            c.strip() for c in str(stock_row.get('category', '')).split(';') if c.strip()
        ]
        # logger.info(f'stock_categories : {stock_categories}')
        if not stock_categories:
            logger.info(f"[INFO] {code} 鏃犳蹇垫暟鎹€?)
            return []

        concept_dict = {}
        for idx, row in df_all.iterrows():
            # 鎷嗗垎姒傚康锛屽幓鎺夌┖瀛楃涓叉垨 '0'
            categories = [
                c.strip() for c in str(row.get('category', '')).split(';') 
                if c.strip() and c.strip() != '0'
            ]
            for c in categories:
                concept_dict.setdefault(c, []).append(row['percent'])

        # --- 涓㈠純鎴愬憳灏戜簬 4 鐨勬蹇?---
        concept_dict = {k: v for k, v in concept_dict.items() if len(v) >= 4}


        # --- top_n==1 鏃讹紝鍙繚鐣欒偂绁ㄦ墍灞炴蹇?---
        if top_n == 1:
            concept_dict = {c: concept_dict[c] for c in stock_categories if c in concept_dict}
            # logger.info(f'top_n == 1 stock_categories : {stock_categories}  concept_dict:{concept_dict}')
        # --- 璁＄畻姒傚康寮哄害 ---
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

        # --- 鎺掑簭骞惰繑鍥?---
        concept_score.sort(key=lambda x: x[1], reverse=True)
        concepts = [c[0] for c in concept_score]
        scores = np.array([c[1] for c in concept_score])
        avg_percents = np.array([c[2] for c in concept_score])
        follow_ratios = np.array([c[3] for c in concept_score])
        # 浠呭湪宸ヤ綔鏃?9:25 鍚庣涓€娆″埛鏂版椂閲嶇疆
        now = datetime.now()
        now_t = int(now.strftime("%H%M"))
        today = now.date()

        force_reset = False

        # 妫€鏌ユ槸鍚﹁法澶╋紝璺ㄥぉ灏遍噸缃樁娈垫爣璁?        if getattr(self, "_concept_data_date", None) != today:
            self._concept_data_date = today
            self._concept_first_phase_done = False
            self._concept_second_phase_done = False

        # 绗竴闃舵锛?:15~9:24瑙﹀彂涓€娆?        if cct.get_trade_date_status() and (915 <= now_t <= 924) and not getattr(self, "_concept_first_phase_done", False):
            self._concept_first_phase_done = True
            force_reset = True
            logger.info(f"{today} 瑙﹀彂 9:15~9:24 绗竴闃舵鍒锋柊")

        # 绗簩闃舵锛?:25 鍚庤Е鍙戜竴娆?        elif cct.get_trade_date_status() and (now_t >= 925) and not getattr(self, "_concept_second_phase_done", False):
            self._concept_second_phase_done = True
            force_reset = True
            logger.info(f"{today} 瑙﹀彂 9:25 绗簩闃舵鍏ㄥ眬閲嶇疆")

        self.init_global_concept_data(concept_score, avg_percents, scores, follow_ratios, force_reset)

        # logger.info(f'concept_score[:10]:{concept_score[:10]}')
        self.concept_top5 = concept_score[:5]
        return concept_score[:10]



    def open_alert_editorAuto(self, stock_info, new_rule=False):
        code = stock_info.get("code")
        name = stock_info.get("name")
        price = stock_info.get("price", 0.0)
        change = stock_info.get("change", 0.0)
        volume = stock_info.get("volume", 0)

        # 濡傛灉鏄柊寤鸿鍒欙紝妫€鏌ユ槸鍚﹀凡鏈夊巻鍙叉姤璀?        rules = self.alert_manager.get_rules(code)
        if new_rule or not rules:
            rules = [
                {"field": "浠锋牸", "op": ">=", "value": price, "enabled": True, "delta": 1},
                {"field": "娑ㄥ箙", "op": ">=", "value": change, "enabled": True, "delta": 1},
                {"field": "閲?, "op": ">=", "value": volume, "enabled": True, "delta": 100}
            ]
            self.alert_manager.set_rules(code, rules)

        # 鍒涘缓 Toplevel 缂栬緫绐楀彛锛岃嚜鍔ㄥ～鍏呰鍒?        editor = tk.Toplevel(self)
        editor.title(f"璁剧疆鎶ヨ瑙勫垯 - {name} {code}")
        editor.geometry("500x300")
        editor.focus_force()
        editor.grab_set()

        # 鍒涘缓瑙勫垯 Frame 骞舵覆鏌?rules
        # ...锛堣繖閲屽彲浠ュ鐢ㄤ綘鐜版湁 add_rule銆佷繚瀛?鍒犻櫎鎸夐挳閫昏緫锛?

    def open_alert_editor(parent, stock_info=None, new_rule=True):
        """
        鎵撳紑鎶ヨ瑙勫垯缂栬緫绐楀彛
        :param parent: 涓荤獥鍙?        :param stock_info: 閫変腑鐨勮偂绁ㄤ俊鎭?(tuple/list)锛屾瘮濡?(code, name, price, ...)
        :param new_rule: True=鏂板缓瑙勫垯锛孎alse=缂栬緫瑙勫垯
        """
        win = tk.Toplevel(parent)
        win.title("鏂板缓鎶ヨ瑙勫垯" if new_rule else "缂栬緫鎶ヨ瑙勫垯")
        win.geometry("400x300")

        # 濡傛灉 stock_info 鏈夊唴瀹癸紝鍦ㄦ爣棰橀噷鏄剧ず
        stock_str = ""
        if stock_info:
            try:
                code, name = stock_info[0], stock_info[1]
                stock_str = f"{code} {name}"
            except Exception:
                stock_str = str(stock_info)
        if stock_str:
            # tk.Label(win, text=f"鑲＄エ: {stock_str}", font=("Arial", 12, "bold")).pack(pady=1)
            tk.Label(win, text=f"鑲＄エ: {stock_str}", font=self.default_font_bold).pack(pady=1)

        # 鎶ヨ鏉′欢杈撳叆鍖?        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(frame, text="鏉′欢绫诲瀷:").grid(row=0, column=0, sticky="w")
        cond_type_var = tk.StringVar(value="浠锋牸澶т簬")
        cond_type_entry = ttk.Combobox(frame, textvariable=cond_type_var,
                                       values=["浠锋牸澶т簬", "浠锋牸灏忎簬", "娑ㄥ箙瓒呰繃", "璺屽箙瓒呰繃"], state="readonly")
        cond_type_entry.grid(row=0, column=1, sticky="ew")

        tk.Label(frame, text="闃堝€?").grid(row=1, column=0, sticky="w")
        threshold_var = tk.StringVar(value="")
        threshold_entry = tk.Entry(frame, textvariable=threshold_var)
        threshold_entry.grid(row=1, column=1, sticky="ew")

        # 淇濆瓨鎸夐挳
        def save_rule():
            rule = {
                "stock": stock_str,
                "cond_type": cond_type_var.get(),
                "threshold": threshold_var.get()
            }
            logger.info(f"淇濆瓨鎶ヨ瑙勫垯: {rule}")
            stock_code = rule.get("stock")  # 鎴栬€呬粠 UI 閲岃幏鍙栭€変腑鐨勮偂绁ㄤ唬鐮?            logger.info(f'stock_code:{stock_code}')
            parent.alert_manager.save_rule(stock_code['name'],rule)  # 淇濆瓨鍒?AlertManager
            messagebox.showinfo("鎴愬姛", "瑙勫垯宸蹭繚瀛?)
            win.destroy()

        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="淇濆瓨", command=save_rule).pack(side="left", padx=5)
        tk.Button(btn_frame, text="鍙栨秷", command=win.destroy).pack(side="left", padx=5)

    def _build_ui(self, ctrl_frame):

        # Market 涓嬫媺鑿滃崟
        tk.Label(ctrl_frame, text="Market:").pack(side="left", padx=2)

        # 鏄剧ず涓枃 鈫?鍐呴儴 code + blkname
        self.market_map = {
            "鍏ㄩ儴": {"code": "all", "blkname": "061.blk"},
            "涓婅瘉": {"code": "sh",  "blkname": "062.blk"},
            "娣辫瘉": {"code": "sz",  "blkname": "066.blk"},
            "鍒涗笟鏉?: {"code": "cyb", "blkname": "063.blk"},
            "绉戝垱鏉?: {"code": "kcb", "blkname": "064.blk"},
            "鍖楄瘉": {"code": "bj",  "blkname": "065.blk"},
            "indb": {"code": "indb",  "blkname": "066.blk"},
        }

        self.market_combo = ttk.Combobox(
            ctrl_frame,
            values=list(self.market_map.keys()),  # 鏄剧ず涓枃
            width=8,
            state="readonly"
        )

        values = list(self.market_map.keys())

        # 鏍规嵁 code 鎵?index
        idx = next(
            (i for i, k in enumerate(values)
             if self.market_map[k]["code"] == marketInit),
            0   # 鎵句笉鍒板垯鍥為€€鍒?"鍏ㄩ儴"
        )

        self.market_combo.current(idx)  # 榛樿 "鍏ㄩ儴"
        self.market_combo.pack(side="left", padx=5)

        # 缁戝畾閫夋嫨浜嬩欢锛屽瓨鍏?GlobalValues
        def on_market_select(event=None):
            market_cn = self.market_combo.get()
            market_info = self.market_map.get(market_cn, {"code": marketInit, "blkname": marketblk})
            self.global_values.setkey("market", market_info["code"])
            self.global_values.setkey("blkname", market_info["blkname"])
            self.global_values.setkey("st_key_sort", self.st_key_sort_value.get())
            logger.info(f"閫夋嫨甯傚満: {market_cn}, code={market_info['code']}, blkname={market_info['blkname']} st_key_sort_value:{self.st_key_sort_value.get()}")

        self.market_combo.bind("<<ComboboxSelected>>", on_market_select)
        
        tk.Label(ctrl_frame, text="stkey:").pack(side="left", padx=2)
        self.st_key_sort_value = tk.StringVar()
        self.st_key_sort_entry = tk.Entry(ctrl_frame, textvariable=self.st_key_sort_value,width=5)
        self.st_key_sort_entry.pack(side="left")
        # 缁戝畾鍥炶溅閿彁浜?        self.st_key_sort_entry.bind("<Return>", self.on_st_key_sort_enter)
        self.st_key_sort_value.set(self.st_key_sort) 
        
        # --- resample 涓嬫媺妗?---
        resampleValues = ["d",'3d', "w", "m"]
        tk.Label(ctrl_frame, text="resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=resampleValues, width=3)
        self.resample_combo.current(resampleValues.index(self.global_values.getkey("resample")))
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())
        self._last_resample = self.resample_combo.get().strip()
        # 鍦ㄥ垵濮嬪寲鏃讹紙StockMonitorApp.__init__锛夊垱寤哄苟娉ㄥ唽锛?        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=logger)
        set_global_manager(self.alert_manager)  

        # 鉁?鍏抽敭锛氬悓姝ヤ竴娆＄姸鎬?        on_market_select()

        # --- 搴曢儴鎼滅储妗?2 ---
        bottom_search_frame = tk.Frame(self)
        bottom_search_frame.pack(side="bottom", fill="x", pady=1)

        self.search_history1 = []
        self.search_history2 = []
        self.search_history3 = []
        self.search_history4 = []
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

        self.search_history1, self.search_history2, self.search_history3, self.search_history4, *_ = self.query_manager.load_search_history()


        # 浠?query_manager 鑾峰彇鍘嗗彶
        h1, h2, h3, h4 = self.query_manager.history1, self.query_manager.history2, self.query_manager.history3, self.query_manager.history4

        # [MODIFIED] Enhanced display: "Note (Query)"
        self.search_map1 = {}
        self.search_map2 = {}
        
        self.search_history1 = self._format_history_list(h1, self.search_map1)
        self.search_history2 = self._format_history_list(h2, self.search_map2) 
        self.search_history3 = [r["query"] for r in h3] # Keep simple for others if unused
        self.search_history4 = [r["query"] for r in h4]

        # [MODIFIED] Update combobox values with formatted history
        self.search_combo1['values'] = self.search_history1
        self.search_combo2['values'] = self.search_history2
        # self.search_combo4['values'] = self.search_history4

        # Update Combobox values
        self.search_combo1['values'] = self.search_history1
        self.search_combo2['values'] = self.search_history2

        # [NEW] Custom selection handler to map Label -> Query
        def on_combo1_selected(event):
            selection = self.search_combo1.get()
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

        tk.Button(bottom_search_frame, text="鎼滅储", command=lambda: self.apply_search()).pack(side="left", padx=3)
        tk.Button(bottom_search_frame, text="娓呯┖", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="鍒犻櫎", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="绠＄悊", command=lambda: self.open_column_manager()).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="鍏抽棴", command=lambda: self.close_all_alerts()).pack(side="left", padx=2)


        # 鍔熻兘閫夋嫨涓嬫媺妗嗭紙鍥哄畾瀹藉害锛?        options = ["绐楀彛閲嶆帓","Query缂栬緫","鍋滄鍒锋柊", "鍚姩鍒锋柊" , "淇濆瓨鏁版嵁", "璇诲彇瀛樻。", "鎶ヨ涓績","澶嶇洏鏁版嵁", "鐩堜簭缁熻", "浜ゆ槗鍒嗘瀽Qt6", "GUI宸ュ叿", "瑕嗗啓TDX", "鎵嬫湱鎬昏", "璇煶棰勮"]
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            bottom_search_frame, textvariable=self.action_var,
            values=options, state="readonly", width=10
        )
        self.action_combo.set("鍔熻兘閫夋嫨")
        self.action_combo.pack(side="left", padx=10, pady=1, ipady=1)

        def run_action(action):

            if action == "绐楀彛閲嶆帓":
                rearrange_monitors_per_screen(align="left", sort_by="id", layout="horizontal",monitor_list=self._pg_top10_window_simple, win_var=self.win_var)
            elif action == "Query缂栬緫":
                self.query_manager.open_editor()  # 鎵撳紑 QueryHistoryManager 缂栬緫绐楀彛
            elif action == "鍋滄鍒锋柊":
                self.stop_refresh()
            elif action == "鍚姩鍒锋柊":
                self.start_refresh()
            elif action == "淇濆瓨鏁版嵁":
                self.save_data_to_csv()
            elif action == "璇诲彇瀛樻。":
                self.load_data_from_csv()
            elif action == "鎶ヨ涓績":
                open_alert_center(self)
            elif action == "瑕嗗啓TDX":
                self.write_to_blk(append=False)
            elif action == "鎵嬫湱鎬昏":
                self.open_handbook_overview()
            elif action == "璇煶棰勮":
                self.open_voice_monitor_manager()
            elif action == "鐩堜簭缁熻":
                self.open_trade_report_window()
            elif action == "浜ゆ槗鍒嗘瀽Qt6":
                self.open_trading_analyzer_qt6()
            elif action == "GUI宸ュ叿":
                self.open_kline_viewer_qt()
            elif action == "澶嶇洏鏁版嵁":
                self.open_market_pulse()
                # self.open_strategy_backtest_view()


        def on_select(event=None):
            run_action(self.action_combo.get())
            self.action_combo.set("鍔熻兘閫夋嫨")

        self.action_combo.bind("<<ComboboxSelected>>", on_select)



        tk.Button(ctrl_frame, text="娓呯┖", command=lambda: self.clean_search(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="鍒犻櫎", command=lambda: self.delete_search_history(2)).pack(side="left", padx=2)
        
        # 涓?search_var4/history4 娣诲姞 涓撻棬鐨勬竻绌?鍒犻櫎鎸夐挳 (鍦?search_combo4 涔嬪悗)
        # tk.Button(ctrl_frame, text="娓呯┖4", command=lambda: self.clean_search(3)).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="鍒犻櫎4", command=lambda: self.delete_search_history(3)).pack(side="left", padx=2)
        
        tk.Button(ctrl_frame, text="鐩戞帶", command=lambda: self.KLineMonitor_init()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="閫夎偂", command=lambda: self.open_stock_selection_window()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="鍐欏叆", command=lambda: self.write_to_blk()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="瀛樻。", command=lambda: self.open_archive_loader(), font=self.default_font, padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="绛栫暐", command=lambda: self.open_strategy_manager(), font=self.default_font_bold, fg="blue", padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="瀹炴椂", command=lambda: self.open_realtime_monitor(), font=self.default_font, padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="55188", command=lambda: self.open_ext_data_viewer(), font=self.default_font_bold, fg="darkgreen", padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="杩借釜", command=lambda: self.open_live_signal_viewer(), font=self.default_font_bold, fg="purple", padx=2, pady=2).pack(side="left", padx=2)

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
        self.after(1000,lambda :self.load_window_position(self, "main_window", default_width=1200, default_height=480))
        self.open_column_manager_init()

    def replace_st_key_sort_col(self, old_col, new_col):
        """鏇挎崲鏄剧ず鍒楀苟鍒锋柊琛ㄦ牸"""
        if old_col in self.current_cols and new_col not in self.current_cols:
            logger.info(f'old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}')
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 鍘绘帀閲嶅鍒?            new_columns = []
            for col in ["code"] + self.current_cols:
                if col not in new_columns:
                    new_columns.append(col)


            # 鍙繚鐣?DataFrame 涓瓨鍦ㄧ殑鍒楋紝閬垮厤 TclError
            new_columns = [c for c in new_columns if c in self.df_all.columns or c == "code"]

            self.update_treeview_cols(new_columns)


    def on_st_key_sort_enter(self, event):
        sort_val = self.st_key_sort_value.get()
        def diff_and_replace_all(old_cols, new_cols):
            """鎵惧嚭涓や釜鍒楄〃涓嶅悓鐨勫厓绱狅紝杩斿洖鏇挎崲瑙勫垯 (old, new)"""
            replace_rules = []
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    replace_rules.append((old, new))
            return replace_rules

        def first_diff(old_cols, new_cols, current_cols):
            """
            鎵惧嚭 old_cols 涓?new_cols 鐨勭涓€涓笉鍚岄」锛?            涓?old 鍦?current_cols 涓瓨鍦ㄣ€?            杩斿洖 (old, new)锛岃嫢鏃犲垯杩斿洖 None銆?            """
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    if old in current_cols:
                        logger.info(f"鉁?鍙浛鎹㈠垪瀵? ({old}, {new})")
                        return old, new
                    else:
                        logger.info(f"鈿狅笍 {old} 涓嶅湪 current_cols 涓紝璺宠繃...")
            logger.info("鈿狅笍 鏈壘鍒板彲鏇挎崲鐨勫樊寮傚垪銆?)
            return None


        def update_display_cols_if_diff(display_cols, display_cols_2, current_cols):
            """
            妫€娴嬪苟鑷姩鏇存柊 display_cols锛屽鏋滃彂鐜版湁鍖归厤宸紓鍒欐浛鎹€?            杩斿洖 (鏂扮殑 display_cols, diff)
            """
            diff = first_diff(display_cols, display_cols_2, current_cols)
            if diff:
                old, new = diff
                # 鏇挎崲绗竴涓尮閰嶇殑 old 涓?new
                updated_cols = [new if c == old else c for c in display_cols]
                logger.info(f"馃煝 宸叉洿鏂?DISPLAY_COLS: 鏇挎崲 {old} 鈫?{new}")
                return updated_cols, diff
            else:
                logger.info("馃敻 鏃犲彲鏇存柊鐨勫垪銆?)
                return display_cols, None



        global DISPLAY_COLS 

        if sort_val:
            sort_val = sort_val.strip()
            self.global_values.setkey("st_key_sort", sort_val)
            self.status_var.set(f"璁剧疆 st_key_sort : {sort_val}")
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
        鎵嬪姩鍒锋柊锛氭洿鏂?resample 鍏ㄥ眬閰嶇疆锛岃Е鍙戝悗鍙拌繘绋嬩笅涓€杞?fetch_and_process
        """

        
        if self._last_resample == self.resample_combo.get().strip():
            return
        else:
            if self.vis_var.get() and hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
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
        self.status_var.set(f"鎵嬪姩鍒锋柊: resample={resample}")


    def _start_process(self):
        self.refresh_flag = mp.Value('b', True)
        self.log_level = mp.Value('i', log_level)  # 'i' 琛ㄧず鏁存暟
        self.detect_calc_support = mp.Value('b', detect_calc_support)  # 'i' 琛ㄧず鏁存暟
        # self.proc = mp.Process(target=fetch_and_process, args=(self.queue,))
        # def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
        #                       flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
        #                       marketInit: str = "all", marketblk: str = "boll",
        #                       duration_sleep_time: int = 5, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
        
        # self.proc = mp.Process(target=fetch_and_process, args=(self.global_dict,self.queue, self.blkname , self.refresh_flag,self.log_level, self.detect_calc_support,marketInit,marketblk,duration_sleep_time))
        self.proc = mp.Process(
            target=fetch_and_process,
            args=(self.global_dict, self.queue, self.blkname, 
                  self.refresh_flag, self.log_level, self.detect_calc_support, 
                  marketInit, marketblk, duration_sleep_time),
            kwargs={
                "status_callback": tip_var_status_flag  # 娉ㄦ剰涓嶇敤鎷彿锛屼紶鍑芥暟
            }
        )
        # self.proc.daemon = True
        self.proc.daemon = False 
        self.proc.start()

    def stop_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False
            logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
            # logger.info(f"DEBUG: stop_refresh called. refresh_flag ID: {id(self.refresh_flag)}")
        self.status_var.set("鍒锋柊宸插仠姝?)

    def start_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = True
            logger.info(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("鍒锋柊宸插惎鍔?)

    def format_next_time(self,delay_ms=None):
        """鎶?root.after 鐨勫欢杩熸椂闂磋浆鎹㈡垚 %H:%M 鏍煎紡"""
        if delay_ms == None:
            target_time = datetime.now()
        else:
            delay_sec = delay_ms / 1000
            target_time = datetime.now() + timedelta(seconds=delay_sec)
        return target_time.strftime("%H:%M")
    # ----------------- 鏁版嵁鍒锋柊 ----------------- #
    def update_tree(self):
        assert_main_thread("update_tree")
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return  # 宸查攢姣侊紝鐩存帴杩斿洖
        try:
            if self.refresh_enabled:  # 鉁?鍙湪鍚敤鏃跺埛鏂?                has_update = False
                _last_df = pd.DataFrame()
                while not self.queue.empty():
                    df = self.queue.get_nowait()
                    # 馃攲 鍦ㄤ富杩涚▼鍚屾鏇存柊 DataPublisher
                    if hasattr(self, 'realtime_service') and self.realtime_service:
                        try:
                            self.realtime_service.update_batch(df)
                        except Exception as e:
                            logger.error(f"Main process realtime update error: {e}")
                    # logger.info(f'df:{df[:1]}')
                    if self.sortby_col is not None:
                        logger.info(f'update_tree sortby_col : {self.sortby_col} sortby_col_ascend : {self.sortby_col_ascend}')
                        df = df.sort_values(by=self.sortby_col, ascending=self.sortby_col_ascend)
                    if not _last_df.empty:
                        try:
                            _df_diff = df.compare(_last_df, keep_shape=False, keep_equal=False)
                            # 濡傛灉娌℃湁鍙樺寲琛岋紝灏辫烦杩囨湰杞?                        except ValueError as e:
                            # debug 杈撳嚭绱㈠紩鍜屽垪鐨勪笉涓€鑷?                            logger.debug(f"[df] compare() ValueError: {e}")
                    else:
                        _last_df = df.copy()
                        _df_diff = _last_df
                    if not _df_diff.empty and df is not None and not df.empty:
                        time_s = time.time()
                        df = detect_signals(df)
                        # Phase 4: Inject resample info for UI display
                        cur_res = self.global_values.getkey("resample") or 'd'
                        if 'resample' not in df.columns:
                            df['resample'] = cur_res
                            
                        self.df_all = df.copy()
                        _last_df = df.copy()
                        has_update = True
                        
                        # 鉁?Sync data to selector if exists (for MarketPulse / SelectionWindow)
                        if hasattr(self, 'selector') and self.selector:
                            self.selector.df_all_realtime = self.df_all
                            self.selector.resample = cur_res

                        logger.info(f'detect_signals duration time:{time.time()-time_s:.2f}')
                        # logger.info(f"self.queue [Debug] df_all_hash={df_hash(self.df_all)} len={len(self.df_all)} time={datetime.now():%H:%M:%S}")
                        
                        # 鉁?浠呭湪绗竴娆¤幏鍙?df_all 鍚庢仮澶嶇洃鎺х獥鍙?                        if not hasattr(self, "_restore_done"):
                            self._restore_done = True
                            logger.info("棣栨鏁版嵁鍔犺浇瀹屾垚锛屽紑濮嬫仮澶嶇洃鎺х獥鍙?..")
                            self.after(2*1000,self.restore_all_monitor_windows)
                            logger.info("棣栨鏁版嵁鍔犺浇瀹屾垚锛屽紑濮?5188鐩戞帶...")
                            self.after(10*1000, self._check_ext_data_update)
                            logger.info("棣栨鏁版嵁鍔犺浇瀹屾垚锛屽欢杩熷紑鍚疜LineMonitor...")
                            self.after(30*1000, self.KLineMonitor_init)
                            self.after(60*1000, self.schedule_15_30_job)

                        if self.search_var1.get() or self.search_var2.get():
                            self.apply_search()
                        else:
                            self.refresh_tree(self.df_all)
                        
                        # 鉁?寮哄埗鍚屾鍒锋柊鎵€鏈夊凡鎵撳紑鐨?Top10 绐楀彛
                        self.update_all_top10_windows()
                            
                # --- 娉ㄥ叆: 瀹炴椂绛栫暐妫€鏌?(绉诲嚭寰幆锛屽彧鍦ㄦ湁鏇存柊鏃舵墽琛屼竴娆? ---
                # if not self.tip_var.get() and has_update and hasattr(self, 'live_strategy'):
                if has_update and hasattr(self, 'live_strategy'):
                    self.after(2000, self._start_feedback_listener)
                    if not (915 < cct.get_now_time_int() < 920):
                        # self.after(90 * 1000, lambda: self.live_strategy.process_data(self.df_all))
                        if self._live_strategy_first_run:
                            # 绗竴娆★細寤惰繜鎵ц
                            self._live_strategy_first_run = False
                            # res = self.global_values.getkey("resample")
                            # [FIX] Voice Alert Management cycle is 'd'. Ensure we check 'd' alerts even if UI is '3d'.
                            target_res = 'd'
                            # If toggle exists and is unchecked, use actual current resample
                            if hasattr(self, 'force_d_cycle_var') and not self.force_d_cycle_var.get():
                                target_res = self.global_values.getkey("resample")

                            self.after(15 * 1000,lambda: self.live_strategy.process_data(self.df_all, concept_top5=getattr(self, 'concept_top5', None), resample=target_res))
                        else:
                            # 鍚庣画锛氱珛鍗虫墽琛?                            # res = self.global_values.getkey("resample")
                            target_res = 'd'
                            # If toggle exists and is unchecked, use actual current resample
                            if hasattr(self, 'force_d_cycle_var') and not self.force_d_cycle_var.get():
                                target_res = self.global_values.getkey("resample")

                            self.live_strategy.process_data(self.df_all, concept_top5=getattr(self, 'concept_top5', None), resample=target_res)
                    
                if has_update:
                    if self._last_resample != self.global_values.getkey("resample"):
                        if  hasattr(self, '_df_sync_thread') and self._df_sync_thread.is_alive():
                            logger.debug(f'[send_df] resample:{self._last_resample} to {self.global_values.getkey("resample")} change force full send init df_first_send_done to False now:{self._df_first_send_done}')
                            if hasattr(self, 'df_ui_prev'):
                                del self.df_ui_prev  # 鍒犻櫎缂撳瓨锛屾ā鎷熷垵濮嬪寲
                            self._last_resample = self.global_values.getkey("resample")
                            if self.viz_command_queue:
                                self.viz_command_queue = None
                            self._df_first_send_done = False
                            # self.vis_var.set(True)
                    # -------------------------
                    self.status_var2.set(f'queue update: {self.format_next_time()}')

        except Exception as e:
            logger.error(f"Error updating tree: {e}", exc_info=True)
        finally:
            self.after(1000, self.update_tree)

    def push_stock_info(self,stock_code, row):
        """
        浠?self.df_all 鐨勪竴琛屾暟鎹彁鍙?stock_info 骞舵帹閫?        """
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
            # 杞负 JSON 瀛楃涓?            payload = json.dumps(stock_info, ensure_ascii=False)

            # ---- 鏍规嵁浼犺緭鏂瑰紡閫夋嫨 ----
            # 濡傛灉鐢?WM_COPYDATA锛岄渶瑕?encode 鎴?bytes 鍐嶄紶
            # if hasattr(self, "send_wm_copydata"):
            #     self.send_wm_copydata(payload.encode("utf-8"))

            # 濡傛灉鐢?Pipe / Queue锛屽彲浠ョ洿鎺ヤ紶 str
            # elif hasattr(self, "pipe"):
            #     self.pipe.send(payload)


            # 鎺ㄩ€佺粰寮傚姩鑱斿姩锛堢敤绠￠亾/娑堟伅锛?            send_code_via_pipe(payload, logger=logger)   # 鍋囪浣犵敤 multiprocessing.Pipe
            # 鎴栬€?self.queue.put(stock_info)  # 濡傛灉鏄槦鍒?            # 鎴栬€?send_code_to_other_window(stock_info) # 濡傛灉鏄?WM_COPYDATA
            logger.info(f"鎺ㄩ€? {stock_info}")
            return True
        except Exception as e:
            logger.error(f"鎺ㄩ€?stock_info 鍑洪敊: {e} {row}")
            return False


    def open_alert_rule_new(self):
        """鏂板缓鎶ヨ瑙勫垯"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            auto_close_message("鎻愮ず", "璇峰厛閫夋嫨涓€涓偂绁紒")
            return
        
        # new_rule=True 琛ㄧず鍒涘缓鏂拌鍒?        self.open_alert_editor(stock_info=stock_info, new_rule=True)

    def open_alert_rule_edit(self):
        """缂栬緫鎶ヨ瑙勫垯"""
        stock_info = getattr(self, "selected_stock_info", None)

        if not stock_info:
            messagebox.showwarning("鎻愮ず", "璇峰厛閫夋嫨涓€鍙偂绁?)
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
        # 鍋囪浣犵殑 tree 鍒楁槸 (code, name, price, 鈥?
        stock_info = {
            "code": values[0],
            "name": values[1] if len(values) > 1 else "",
            "extra": values  # 淇濈暀鏁磋
        }
        self.selected_stock_info = stock_info

        if selected_item:
            stock_info = self.tree.item(selected_item, 'values')
            stock_code = stock_info[0]
            stock_name = stock_info[1]

            send_tdx_Key = (self.select_code != stock_code)
            self.select_code = stock_code

            stock_code = str(stock_code).zfill(6)
            logger.debug(f'stock_code:{stock_code}')
            # logger.info(f"閫変腑鑲＄エ浠ｇ爜: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                self.open_visualizer(stock_code)

            # if self.voice_var.get():
            if self.tip_var.get():
                # =========================
                # 鉁?鏋勯€?fake mouse event
                # =========================
                try:
                    # ==========================
                    # 鉁?鏋勯€犳ā鎷?event
                    # ==========================

                    x_root = getattr(self, "event_x_root", None)
                    y_root = getattr(self, "event_y_root", None)

                    # 娌℃湁榧犳爣鍧愭爣灏遍€€鍥炲埌琛屼腑蹇?                    if x_root is None or y_root is None:
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

                    # 鉁?澶嶇敤 Tooltip 鍏ュ彛
                    self.on_tree_click_for_tooltip(fake_event,stock_code,stock_name)

                except Exception as e:
                    logger.warning(f"Tooltip select trigger failed: {e}")

    def update_send_status(self, status_dict):
        # 鏇存柊鐘舵€佹爮
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        # self.status_var.set(status_text)
        # logger.info(status_text)

    def scale_size(self,base_size):
        """鏍规嵁 DPI 缂╂斁杩斿洖灏哄"""
        scale = get_windows_dpi_scale_factor()
        return int(base_size * scale)
    

    def init_checkbuttons(self, parent_frame):
        # 淇濇寔 Tk.Frame 涓嶅彉锛屽洜涓哄畠鏄鍣?        frame_right = tk.Frame(parent_frame, bg="#f0f0f0") 
        frame_right.pack(side=tk.RIGHT, padx=2, pady=1)

        self.win_var = tk.BooleanVar(value=False)
        # 鉁?缁戝畾win_var鍙樺寲鍥炶皟锛屽疄鏃跺垏鎹㈢壒寰侀鑹叉樉绀?        self.win_var.trace_add('write', lambda *args: self.toggle_feature_colors())
        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=True)
        self.dfcf_var = tk.BooleanVar(value=False)
        self.tip_var = tk.BooleanVar(value=False)
        self.voice_var = tk.BooleanVar(value=True) # 馃挜 榛樿寮€鍚闊?        self.realtime_var = tk.BooleanVar(value=True)
        self.vis_var = tk.BooleanVar(value=False)
        checkbuttons_info = [
            ("Win", self.win_var),
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var),
            ("Tip", self.tip_var),
            ("Real", self.realtime_var),
            ("Vis", self.vis_var)
        ]
        
        # 馃挜 淇锛氫娇鐢?ttk.Checkbutton 鏇夸唬 tk.Checkbutton
        for text, var in checkbuttons_info:
            cb = ttk.Checkbutton(
                frame_right, 
                text=text, 
                variable=var, 
                command=self.update_linkage_status,
                # 馃挜 娉ㄦ剰锛歵tk 缁勪欢涓嶅啀浣跨敤 bg, font 绛夌洿鎺ュ弬鏁?                # bg="#f0f0f0", 
                # font=('Microsoft YaHei', 9), # 瀛椾綋搴旇閫氳繃 Style 缁熶竴璁剧疆
                # padx=0, pady=0, bd=0, highlightthickness=0
            )
            cb.pack(side=tk.LEFT, padx=1)

        ttk.Checkbutton(
            frame_right,
            text="Vo",
            variable=self.voice_var,
            command=self.on_voice_toggle
        ).pack(side=tk.LEFT, padx=1)

        ttk.Button(
            frame_right,
            text="馃搳", 
            width=3,
            command=lambda: self.open_visualizer(getattr(self, 'select_code', None))
        ).pack(side=tk.LEFT, padx=1)

        ttk.Button(
            frame_right,
            text="绛栫暐", 
            width=5,
            command=self.open_strategy_scan
        ).pack(side=tk.LEFT, padx=1)

        # Initialize persisted variables that are not bound to main UI buttons immediately
        self.force_d_cycle_var = tk.BooleanVar(value=True)

        # Load persisted states
        self.load_ui_states()
        
        # Apply strict linkage immediately
        self.after(100, self.update_linkage_status)



    def open_strategy_scan(self):
        """涓€閿墦寮€绛栫暐鎵弿"""
        # 1. 纭繚 Visualizer 鍚姩 (浼犲叆褰撳墠閫変腑浠ｇ爜鎴?None)
        code = getattr(self, 'select_code', '000001')
        # 濡傛灉鏈惎鍔ㄥ垯鍚姩锛屽鏋滃凡鍚姩鍒欐棤鍓綔鐢?(闄や簡 debounce)
        self.open_visualizer(code)

        # 2. 鍙戦€佹壂鎻忔寚浠?        # open_visualizer 浼氬垵濮嬪寲 viz_command_queue
        if hasattr(self, 'viz_command_queue') and self.viz_command_queue:
             self.viz_command_queue.put(('CMD_SCAN_CONSOLIDATION', {}))
             logger.info("Sent CMD_SCAN_CONSOLIDATION to Visualizer")
             if hasattr(self, 'status_var'):
                self.status_var.set("宸插彂閫佺瓥鐣ユ壂鎻忔寚浠?..")
             
             # 鎻愮ず鐢ㄦ埛
             # toast_message(self, "宸茶Е鍙戠瓥鐣ユ壂鎻忥紝璇锋煡鐪嬪彲瑙嗗寲绐楀彛", duration=2000)

    def load_ui_states(self):
        """鍔犺浇UI鐘舵€?""
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

            logger.info(f"UI states loaded: {len(ui_state)} items")

        except Exception as e:
            logger.error(f"Error loading UI states: {e}")

    def save_ui_states(self):
        """淇濆瓨UI鐘舵€?""
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
                'force_d_cycle_var', 'search_var1', 'search_var2',
                'st_key_sort_value'
            ]
            
            for name in save_list:
                var = getattr(self, name, None)
                if var:
                    try:
                        config['ui_persistence'][name] = var.get()
                    except:
                        pass

            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            logger.info("UI states saved.")

        except Exception as e:
            logger.error(f"Error saving UI states: {e}")

    def open_visualizer(self, code):

        if not code and self._last_resample != self.global_values.getkey("resample"):
            return

        if self.vis_select_code == code:
            return
        else:
            self.vis_select_code = code
        now = time.time()
        # 闃叉姈锛氬悓涓€ code 鍦?0.5 绉掑唴涓嶉噸澶嶅彂閫?        if self._last_visualizer_code == code and (now - self._last_visualizer_time) < self._visualizer_debounce_sec:
            return

        self._last_visualizer_code = code
        self._last_visualizer_time = now

        if not hasattr(self, 'qt_process'):
            self.qt_process = None

        # ===== 鍒濆鍖栧拰瀹氭椂绾跨▼ =====
        self._df_sync_running = True

        ipc_host, ipc_port = '127.0.0.1', 26668
        sent = False

        real_time_cols = list(cct.real_time_cols) if hasattr(cct, 'real_time_cols') else []
        strategy_cols = ['last_action', 'last_reason', 'shadow_info', 'market_win_rate', 'loss_streak', 'vwap_bias']
        # 馃洝锔?纭繚鏍稿績瀛楁濮嬬粓鍖呭惈锛屽嵆浣跨敤鎴烽厤缃腑缂哄け
        required_visualizer_cols = ['code', 'name', 'percent', 'dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']
        
        # 浣跨敤鍘婚噸鐨勬柟寮忓悎骞跺垪
        ui_cols = []
        has_percent = any(c.lower() == 'percent' for c in real_time_cols)
        source_cols = real_time_cols if len(real_time_cols) > 4 and has_percent else required_visualizer_cols
        for c in (source_cols + required_visualizer_cols + strategy_cols):
            if c not in ui_cols:
                ui_cols.append(c)

        # --- 0锔忊儯 鑾峰彇褰撳墠鍛ㄦ湡鍙傛暟 ---
        resample = self.resample_combo.get() if hasattr(self, 'resample_combo') else 'd'

        sent = False
        
        # --- 1锔忊儯 浼樺厛妫€鏌ュ唴閮ㄨ繘绋嬫槸鍚﹀瓨娲伙紝浣跨敤 Queue 閫氫俊 (鏈€蹇? ---
        if self.qt_process is not None and self.qt_process.is_alive():
             try:
                 if self.viz_command_queue is not None:
                     self.viz_command_queue.put(('SWITCH_CODE', {'code': code, 'resample': resample}))
                     logger.info(f"Queue: Sent SWITCH_CODE {code} with resample={resample}")
                     sent = True
                     # 浜や簰鎻愮ず
                     if hasattr(self, 'status_bar'):
                         self.status_bar.config(text=f"姝ｅ湪鍒囨崲鍙鍖? {code} ...")
                         self.update_idletasks()
             except Exception as e:
                 logger.error(f"Queue send failed: {e}")

        # --- 2锔忊儯 濡傛灉鍐呴儴闃熷垪娌″彂閫?鍙兘鏄閮ㄨ繘绋嬫垨闃熷垪閿?锛屽皾璇?Socket ---
        if not sent:
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(0.5) # 缂╃煭瓒呮椂锛岄伩鍏嶇晫闈㈠崱椤?                client_socket.connect((ipc_host, ipc_port))
                # 鍙戦€佹牸寮? CODE|浠ｇ爜|key1=val1|key2=val2
                ipc_msg = f"CODE|{code}|resample={resample}"
                client_socket.send(ipc_msg.encode('utf-8'))
                client_socket.close()
                logger.debug(f"Socket: Sent {ipc_msg} to visualizer")
                sent = True
            except (ConnectionRefusedError, OSError):
                pass
            except Exception as e:
                logger.warning(f"Socket connection check failed: {e}")

        # --- 3锔忊儯 鍚姩 Qt 鍙鍖栬繘绋嬶紙濡傛灉鏃㈡病娲荤潃涔熸病浜哄惉锛?---
        if not sent:
            try:
                # 鍙湁褰撹繘绋嬬‘瀹炰笉瀛樺湪鎴栧凡姝绘椂鎵嶅惎鍔?                if self.qt_process is None or not self.qt_process.is_alive():
                    # 鍒濆鍖栨寚浠ら槦鍒?                    if self.viz_command_queue is None:
                        self.viz_command_queue = mp.Queue()
                    
                    # [FIX] 姣忔鍚姩鍓嶅己鍒堕噸缃敓鍛藉懆鏈熸爣蹇椾负 True (闃叉涓婃閫€鍑烘畫鐣?False)
                    if hasattr(self, 'viz_lifecycle_flag'):
                        self.viz_lifecycle_flag.value = True
                        logger.info(f"[Visualizer] Resetting viz_lifecycle_flag to True. Addr: {id(self.viz_lifecycle_flag)}")
                    
                    # 鍚姩杩涚▼锛氫紶鍏?code|resample, stop_flag, log_level, debug, queue
                    # load_stock_by_code handles the | split automatically
                    initial_payload = f"{code}|resample={resample}"
                    self.qt_process = mp.Process(
                        target=qtviz.main, 
                        # [FIX] 浣跨敤 viz_lifecycle_flag
                        # args=(initial_payload, self.viz_lifecycle_flag, self.log_level , False, self.viz_command_queue), 
                        # debug info
                        args=(initial_payload, self.viz_lifecycle_flag, self.log_level , False, self.viz_command_queue), 
                        daemon=False
                    )
                    self.qt_process.start()
                    print(f"Launched QT GUI process via Queue for {initial_payload}")
                    time.sleep(1)  # 缁?Qt 鍒濆鍖栨椂闂?                    if hasattr(self, '_df_first_send_done'):
                        self._df_first_send_done = False
                else:
                     # 鐞嗚涓婁笉搴旇璧板埌杩欓噷锛屽洜涓哄墠闈㈡鏌ヨ繃 alive 骞跺皾璇曚簡 queue
                     # 浣嗕互闃蹭竾涓€ queue 澶辫触浜嗕絾杩涚▼杩樻椿鐫€... 杩樻槸灏濊瘯 queue 鍚?                     if self.viz_command_queue is not None:
                         self.viz_command_queue.put(('SWITCH_CODE', {'code': code, 'resample': resample}))
            except Exception as e:
                logger.error(f"Failed to start Qt visualizer: {e}")
                traceback.print_exc()
                return

            if not hasattr(self, '_df_first_send_done'):
                self._df_first_send_done = False

            if not hasattr(self, '_df_first_send_done'):
                self._df_first_send_done = False
            
        # 鍚姩鍚屾绾跨▼锛堝彧鍚姩涓€娆★級
        if not hasattr(self, '_df_sync_thread') or not self._df_sync_thread.is_alive():
            self._df_sync_thread = threading.Thread(target=self.send_df, daemon=True)
            self._df_sync_thread.start()

    def send_df(self, initial=True):
        """鍚屾鏁版嵁鎺ㄩ€佹牳蹇冮€昏緫 (浣滀负绫绘柟娉曪紝鏀寔璺ㄧ嚎绋嬪敜閱?"""
        ipc_host, ipc_port = '127.0.0.1', 26668
        last_send_time = 0
        min_interval = 0.2  # 鏈€灏忓彂閫侀棿闅?200ms
        max_jitter = 0.1    # 闅忔満鎶栧姩 0~100ms
        logger.info(f"[send_df] Thread START, running={getattr(self,'_df_sync_running',False)}")
        count = 0
        while self._df_sync_running:
            if not hasattr(self, 'df_all') or self.df_all.empty:
                logger.debug("[send_df] df_all is empty or missing, waiting...")
                if count < 3:
                    count +=1
                    time.sleep(2)
                    continue
            sent = False  # 猸?鏈疆鏄惁鎴愬姛鍙戦€?            try:
                now = time.time()
                # 猸?闄愭祦 + 鎶栧姩
                if now - last_send_time < min_interval:
                    time.sleep(min_interval - (now - last_send_time) + random.uniform(0, max_jitter))
                last_send_time = time.time()

                # 鈿?[FIX] 澶勭悊鏉ヨ嚜 Pipe 鐨勫己鍒跺叏閲忓悓姝ヨ姹傦紙绾跨▼瀹夊叏鏂瑰紡锛?                if getattr(self, '_force_full_sync_pending', False):
                    logger.info("[send_df] Executing pending FULL SYNC request")
                    if hasattr(self, 'df_ui_prev'):
                        del self.df_ui_prev
                    self.sync_version = 0
                    self._force_full_sync_pending = False

                df_ui = self.df_all.copy()
                # --- 璁＄畻澧為噺 ---
                if hasattr(self, 'df_ui_prev'):
                    # df_diff = df_ui.compare(self.df_ui_prev, keep_shape=True, keep_equal=False)
                    # df_diff = df_ui.compare(self.df_ui_prev, keep_shape=False, keep_equal=False)
                    try:
                        df_diff = df_ui.compare(self.df_ui_prev, keep_shape=False, keep_equal=False)
                        # 濡傛灉娌℃湁鍙樺寲琛岋紝灏辫烦杩囨湰杞?                        if df_diff.empty:
                            logger.debug("[send_df] df_diff empty, skip sending this cycle")
                            sent = True
                        else:
                            msg_type = 'UPDATE_DF_DIFF'
                            payload_to_send = df_diff
                            # --- 3锔忊儯 鍐呭瓨鏃ュ織 ---
                            mem = df_diff.memory_usage(deep=True).sum()

                    except ValueError as e:
                        # debug 杈撳嚭绱㈠紩鍜屽垪鐨勪笉涓€鑷?                        prev_cols = set(self.df_ui_prev.columns) if hasattr(self, 'df_ui_prev') else set()
                        curr_cols = set(df_ui.columns)
                        prev_idx = set(self.df_ui_prev.index) if hasattr(self, 'df_ui_prev') else set()
                        curr_idx = set(df_ui.index)

                        logger.debug(f"[send_df] compare() ValueError: {e}")
                        logger.debug(f"[send_df] columns prev={list(prev_cols)[:5]}, curr={list(curr_cols)[:5]}")
                        logger.debug(f"[send_df] index prev={list(prev_idx)[:5]}, curr={list(curr_idx)[:5]}")

                        # 涓轰簡涓嶄腑鏂紝鍙互鐩存帴鎶婂叏閲忓綋浣?diff
                        payload_to_send = df_ui
                        # --- 3锔忊儯 鍐呭瓨鏃ュ織 ---
                        mem = df_ui.memory_usage(deep=True).sum()
                        msg_type = 'UPDATE_DF_ALL'

                else:
                    payload_to_send = df_ui
                    # --- 3锔忊儯 鍐呭瓨鏃ュ織 ---
                    mem = df_ui.memory_usage(deep=True).sum()
                    msg_type = 'UPDATE_DF_ALL'

                # 鏇存柊缂撳瓨
                self.df_ui_prev = df_ui.copy()

                if 'code' not in df_ui.columns:
                    df_ui = df_ui.reset_index()

                logger.info(
                    f'df_ui: {msg_type} rows={len(df_ui)} ver={self.sync_version} mem={mem/1024:.1f} KB'
                )

                # --- 馃巵 灏佽鐗堟湰鍖栧崗璁寘 ---
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
                # 猸?4锔忊儯 涓婚€氶亾锛歈ueue (浼樺厛)
                # ======================================================
                used_queue = False
                # 鍏抽敭淇锛氬繀椤绘鏌?qt_process.is_alive()銆?                # 濡傛灉鍐呰仈杩涚▼鍏抽棴锛孮ueue 瀵硅薄铏藉湪浣嗘棤浜鸿鍙栵紝浼氬鑷存暟鎹爢绉笖澶栭儴 IPC 鏃犳硶鐢熸晥銆?                # 鍙湁杩涚▼娲荤潃锛孮ueue 閫氫俊鎵嶆湁鎰忎箟銆?                if self.viz_command_queue is not None and self.qt_process is not None and self.qt_process.is_alive() and not sent:
                    try:
                        with timed_ctx(f"viz_queue_put[{len(df_ui)}]", warn_ms=300):
                            self.viz_command_queue.put_nowait(
                                ('UPDATE_DF_DATA', sync_package)
                            )
                        logger.debug(f"[Queue] {msg_type} sent (ver={self.sync_version})")
                        sent = True
                        used_queue = True

                    except Full:
                        logger.warning("[Queue] full, fallback to IPC")

                    except Exception as e:
                        logger.exception(f"[Queue] send failed: {e}")

                # 璇婃柇锛氬鏋滄湁鍐呴儴杩涚▼浣嗘病璧?Queue
                if not sent and self.qt_process is not None and self.qt_process.is_alive():
                     logger.warning(f"[send_df] Internal process alive but Queue skipped/failed! queue_obj={self.viz_command_queue is not None}")

                # ======================================================
                # 猸?5锔忊儯 鍏滃簳閫氶亾锛歋ocket锛堜粎褰?Queue 澶辫触锛?                # ======================================================
                if not sent:
                    try:
                        # 1锔忊儯 pickle 鍗曠嫭璁℃椂
                        with timed_ctx("viz_IPC_pickle", warn_ms=300):
                            payload = pickle.dumps(('UPDATE_DF_DATA', sync_package),
                                     protocol=pickle.HIGHEST_PROTOCOL)

                        header = struct.pack("!I", len(payload))

                        # 2锔忊儯 socket 鍗曠嫭璁℃椂
                        with timed_ctx("viz_IPC_send", warn_ms=300):
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(1.0)
                                s.connect((ipc_host, ipc_port))
                                s.sendall(b"DATA" + header + payload)

                        logger.debug(f"[IPC] {msg_type} sent (ver={self.sync_version})")
                        sent = True
                        
                        # 鍐嶆鎻愰啋锛氳櫧鐒?IPC 鍙戦€佹垚鍔燂紝浣嗗鏋滄槸鍐呴儴鍚姩锛屾湰搴旇璧?Queue
                        if self.qt_process is not None and self.qt_process.is_alive():
                            logger.info("[send_df] Used IPC fallback for distinct internal process (Queue might be full or broken).")

                    except Exception as e:
                        # 鍙湁褰撶湡姝ｅけ璐ユ椂鎵?Warning锛岄伩鍏嶆病鏈?Visualizer 鏃剁殑鍣煶
                        # logger.warning(f"[IPC] send failed: {e}")
                        pass
                        if not self.vis_var.get():
                            # self._df_first_send_done = True
                            sent = True

            except Exception:
                logger.exception("[send_df] unexpected error")
            finally:
                if sent:
                    cct.print_timing_summary_filter(include_prefix="viz_", top_n=10)
            # ======================================================
            # 猸?6锔忊儯 鐘舵€佹洿鏂帮紙鍙湪杩欓噷锛?            # ======================================================
            prev = getattr(self, "_df_first_send_done", False)
            self._df_first_send_done = sent

            # 鐘舵€佸垰浠?False 鈫?True锛氱珛鍗宠繘鍏ユ參閫熷懆鏈?            if sent and not prev and self.vis_var.get():
                logger.info("[send_df] first successful send")

            # ======================================================
            # 猸?7锔忊儯 璋冨害閫昏緫
            # ======================================================
            sleep_seconds = 300 if sent else 5
            for _ in range(sleep_seconds):
                if not self._df_sync_running or not self._df_first_send_done:
                    break
                time.sleep(1)


    def on_voice_toggle(self):
        val = self.voice_var.get()
        self.live_strategy.set_voice_enabled(val)
        if not val:
            # 濡傛灉鍏抽棴璇煶锛岀珛鍗冲仠姝㈠綋鍓嶆挱鏀?            try:
                AlertManager().stop_current_speech()
            except:
                pass

    def reload_cfg_value(self):
        global marketInit,marketblk,scale_offset,resampleInit
        global duration_sleep_time,write_all_day_date,detect_calc_support
        conf_ini= cct.get_conf_path('global.ini')
        if not conf_ini:
            logger.info("global.ini 鍔犺浇澶辫触锛岀▼搴忔棤娉曠户缁繍琛?)

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
        logger.info(f"reload cfg marketInit : {marketInit} marketblk: {marketblk} \
            scale_offset: {scale_offset} saved_width:{saved_width},{saved_height} \
            duration_sleep_time:{duration_sleep_time} \
            detect_calc_support:{detect_calc_support} \
            alert_cooldown:{alert_cooldown}\
            pending_alert_cycles:{pending_alert_cycles} st_key_sort:{st_key_sort}")
        
        # 鍚屾棰戠巼鍙樺姩鍒板疄鏃舵湇鍔?濡傛灉宸茶繛鎺?
        if hasattr(self, 'realtime_service') and self.realtime_service:
            try:
                self.realtime_service.set_expected_interval(int(duration_sleep_time))
            except:
                pass

    def update_linkage_status(self):
        global tip_var_status_flag
        # 姝ゅ澶勭悊 checkbuttons 鐘舵€?        if not self.tdx_var.get() or not self.ths_var.get():
            self.sender.reload()
        if  self.dfcf_var.get() != self.auto_adjust_column:
            logger.info(f"DC:{self.dfcf_var.get()} self.auto_adjust_column :{self.auto_adjust_column}")
            self.auto_adjust_column = self.dfcf_var.get()
            # self.apply_search()
            # self.after(50, self.adjust_column_widths)
            self._setup_tree_columns(self.tree,self.current_cols, sort_callback=self.sort_by_column, other={})
            self.reload_cfg_value()
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
        if (not self.vis_var.get()) and getattr(self, "_df_first_send_done", False):
            # logger.debug(f'change _df_first_send_done:{self._df_first_send_done}')
            logger.debug(f"[send_df] force full send: deleting df_ui_prev, _df_first_send_done={self._df_first_send_done}")
            if hasattr(self, 'df_ui_prev'):
                del self.df_ui_prev  # 鍒犻櫎缂撳瓨锛屾ā鎷熷垵濮嬪寲

            self._df_first_send_done = False
        # self.update_treeview_cols(self.current_cols)
        tip_var_status_flag.value = self.tip_var.get()

        logger.info(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()} tip_var_status_flag:{tip_var_status_flag.value}")


    # 閫夋嫨鍘嗗彶鏌ヨ
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
            # 鏇存柊鏌ヨ璇存槑
            # self.query_desc_label.config(text=desc)
            self.refresh_tree_with_query(query_dict)

    # 灏嗘煡璇㈡枃鏈В鏋愪负 dict锛堝彲鏍规嵁浣犻渶姹傛敼锛?    def parse_query_text(self, text):
        # 绠€鍗曠ず渚嬶細name=ABC;percent>1
        query_dict = {}
        for cond in text.split(";"):
            cond = cond.strip()
            if not cond:
                continue
            # name%涓俊 -> key=name, val=%涓俊
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

        # 鏋勯€?query_dict
        query_dict = self.parse_query_text(query_text)

        # 淇濆瓨鍒板巻鍙?        desc = query_text
        self.query_history.append({'query': query_dict, 'desc': desc})

        # 鏇存柊涓嬫媺妗?        self.query_combo['values'] = [q['desc'] for q in self.query_history]
        if self.query_history:
            self.query_combo.current(len(self.query_history) - 1)

        # 鎵ц鍒锋柊
        self.refresh_tree_with_query(query_dict)
        self.query_desc_label.config(text=desc)


    def refresh_tree_with_query(self, query_dict):
        if not hasattr(self, 'temp_df'):
            return
        df = self.temp_df.copy()

        # 鏀寔鑼冨洿鏌ヨ鍜岀瓑鍊兼煡璇?        for col, cond in query_dict.items():
            if col not in df.columns:
                continue
            if isinstance(cond, str):
                cond = cond.strip()
                if '~' in cond:  # 鍖洪棿鏌ヨ 5~15
                    try:
                        low, high = map(float, cond.split('~'))
                        df = df[(df[col] >= low) & (df[col] <= high)]
                    except:
                        pass
                elif cond.startswith(('>', '<', '>=', '<=', '==')):
                    df = df.query(f"{col}{cond}")
                else:  # 妯＄硦鍖归厤 like
                    df = df[df[col].astype(str).str.contains(cond)]
            else:
                df = df[df[col]==cond]

        # 淇濈暀 DISPLAY_COLS
        display_df = df[DISPLAY_COLS]
        self.tree.delete(*self.tree.get_children())
        for idx, row in display_df.iterrows():
            self.tree.insert("", "end", values=[row[col] for col in DISPLAY_COLS])

    def refresh_tree_with_query2(self, query_dict=None):
        """
        鍒锋柊 TreeView 骞舵敮鎸侀珮绾ф煡璇?        query_dict: dict, key=鍒楀悕, value=鏌ヨ鏉′欢
        """
        if self.df_all.empty:
            return

        # 1. 鍘熷鏁版嵁淇濈暀
        df_raw = self.df_all.copy()

        # 2. 澶勭悊鏌ヨ
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

        # 3. 鏋勯€犳樉绀?DataFrame
        # 浠呬繚鐣?DISPLAY_COLS锛屽鏋?DISPLAY_COLS 涓垪涓嶅湪 df_all 涓紝濉厖绌哄€?        df_display = pd.DataFrame(index=df_filtered.index)
        for col in DISPLAY_COLS:
            if col in df_filtered.columns:
                df_display[col] = df_filtered[col]
            else:
                df_display[col] = ""

        self.current_df = df_display
        self.refresh_tree(force=True)


    def filter_and_refresh_tree(self, query_dict):
        """
        楂樼骇杩囨护 TreeView 鏄剧ず

        query_dict = {
            'name': '%涓?',        # 妯＄硦鍖归厤
            '娑ㄥ箙': '>=2',         # 鏁板€煎尮閰?            '閲?: '10~100'         # 鑼冨洿鍖归厤
        }
        """
        if self.df_all.empty:
            return

        df_filtered = self.df_all.copy()

        for col, val in query_dict.items():
            if col not in df_filtered.columns:
                continue

            s = df_filtered[col]

            # 鏁板€艰寖鍥存垨姣旇緝绗﹀彿
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
                    # 绮剧‘鍖归厤
                    df_filtered = df_filtered[s == val]
            else:
                # 鏁板€肩簿纭尮閰?                df_filtered = df_filtered[s == val]

        # 淇濈暀鍘熷鏈煡璇㈠垪鏁版嵁锛屾€诲垪鏁颁笉鍙?        self.current_df = self.df_all.loc[df_filtered.index].copy()
        self.refresh_tree()


    def open_column_selector(self, col_index):
        """寮瑰嚭妯帓绐楀彛閫夋嫨鏂扮殑鍒楀悕"""
        if self.current_df is None or self.current_df.empty:
            return

        # 鍒涘缓寮瑰嚭绐楀彛
        win = tk.Toplevel(self)
        win.title("閫夋嫨鍒?)
        win.geometry("800x400")  # 鍙皟澶у皬
        win.transient(self)

        # 婊氬姩鏉?+ 鐢诲竷 + frame锛岄伩鍏嶅垪澶鏀句笉涓?        canvas = tk.Canvas(win)
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

        # 褰撳墠鎵€鏈夊垪
        all_cols = list(self.current_df.columns)

        def on_select(col_name):
            # 鏇挎崲 Treeview 鐨勫垪
            if 0 <= col_index < len(DISPLAY_COLS):
                DISPLAY_COLS[col_index] = col_name
                self.refresh_tree(self.current_df)
            win.destroy()

        # 鐢熸垚鎸夐挳锛堟í鎺掞紝鑷姩鎹㈣锛?        for i, col in enumerate(all_cols):
            btn = tk.Button(scroll_frame, text=col, width=15,
                            command=lambda c=col: on_select(c))
            btn.grid(row=i // 5, column=i % 5, padx=5, pady=5, sticky="w")

        win.grab_set()  # 妯℃€?
    def on_single_click(self, event=None, values=None):
        """
        缁熶竴澶勭悊 alert_tree 鐨勫崟鍑诲拰鍙屽嚮
        event: Tkinter浜嬩欢瀵硅薄锛圱reeview鐐瑰嚮锛?        values: 鍙€夛紝鐩存帴浼犲叆琛屾暟鎹紙鏉ヨ嚜 KLineMonitor锛?        """
        # 濡傛灉娌℃湁 values锛屽氨浠?event 閲屽彇
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

        # 鍋囪浣犵殑 tree 鍒楁槸 (code, name, price, 鈥?
        stock_info = {
            "code": values[0],
            "name": values[1] if len(values) > 1 else "",
            "extra": values  # 淇濈暀鏁磋
        }
        self.selected_stock_info = stock_info

        stock_code = values[0]

        send_tdx_Key = (getattr(self, "select_code", None) != stock_code)
        self.select_code = stock_code
        if event:   # 鍙湪鐪熷疄榧犳爣瑙﹀彂鏃朵繚瀛?            self.event_x_root = event.x_root
            self.event_y_root = event.y_root
        self.on_tree_click_for_tooltip(event)

        stock_code = str(stock_code).zfill(6)
        logger.info(f'stock_code:{stock_code}')
        # logger.info(f"閫変腑鑲＄エ浠ｇ爜: {stock_code}")

        if send_tdx_Key and stock_code:
            self.sender.send(stock_code)
        # Auto-launch Visualizer if enabled
        if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
            self.open_visualizer(stock_code)

    def is_window_covered_by_main(self, win):
        """
        鍒ゆ柇 win 鏄惁瀹屽叏鍦ㄤ富绐楀彛 self 鑼冨洿鍐咃紙鍙兘琚伄鎸★級
        杩斿洖 True 琛ㄧず琚鐩?        """
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
            """鍏抽棴鏃舵竻绌哄紩鐢?""
            try:
                self.save_window_position(self.detail_win, "detail_win_Category")
            except Exception:
                pass
            if self.detail_win and self.detail_win.winfo_exists():
                self.detail_win.destroy()
            self.detail_win = None
            self.txt_widget = None

        if self.detail_win and self.detail_win.winfo_exists():
            # 宸插瓨鍦?鈫?鏇存柊鍐呭
            self.detail_win.title(f"{code} {name} - Category Details")
            self.txt_widget.config(state="normal")
            self.txt_widget.delete("1.0", tk.END)
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")

            # # 妫€鏌ョ獥鍙ｆ槸鍚︽渶灏忓寲鎴栬閬尅
            state = self.detail_win.state()
            # if state == "iconic":  # 鏈€灏忓寲
            if (state == "iconic" or self.is_window_covered_by_main(self.detail_win)):
                self.detail_win.deiconify()  # 鎭㈠
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
            # 绗竴娆″垱寤?
            self.detail_win = tk.Toplevel(self)
            self.detail_win.title(f"{code} {name} - Category Details")
            # 鍏堝己鍒剁粯鍒朵竴娆?            # self.detail_win.update_idletasks()
            self.detail_win.withdraw()  # 鍏堥殣钘忥紝閬垮厤闂埌榛樿(50,50)

            self.load_window_position(self.detail_win, "detail_win_Category", default_width=400, default_height=200)

            # 鍐嶆樉绀哄嚭鏉?            self.detail_win.deiconify()

            self.txt_widget = tk.Text(self.detail_win, wrap="word", font=self.default_font)
            self.txt_widget.pack(expand=True, fill="both")
            self.txt_widget.insert("1.0", category_content)
            self.txt_widget.config(state="disabled")
            self.detail_win.lift()

            # 鍙抽敭鑿滃崟
            menu = tk.Menu(self.detail_win, tearoff=0)
            menu.add_command(label="澶嶅埗", command=lambda: self.detail_win.clipboard_append(self.txt_widget.selection_get()))
            menu.add_command(label="鍏ㄩ€?, command=lambda: self.txt_widget.tag_add("sel", "1.0", "end"))

            def show_context_menu(event):
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

            self.txt_widget.bind("<Button-3>", show_context_menu)
            # ESC 鍏抽棴
            self.detail_win.bind("<Escape>", lambda e: on_close())
            # 鐐圭獥鍙ｅ彸涓婅 脳 鍏抽棴
            self.detail_win.protocol("WM_DELETE_WINDOW", on_close)

            # 鍒濇鍒涘缓鎵嶅己鍒跺墠缃?            self.detail_win.focus_force()
            self.detail_win.lift()

    def on_double_click(self, event):
        # logger.info(f'on_double_click')
        sel_row = self.tree.identify_row(event.y)
        sel_col = self.tree.identify_column(event.x)

        if not sel_row or not sel_col:
            return

        # 鍒楃储寮?        col_idx = int(sel_col.replace("#", "")) - 1
        col_name = 'category'  # 杩欓噷鍋囪鍙湁 category 鍒楅渶瑕佸脊绐?
        vals = self.tree.item(sel_row, "values")
        if not vals:
            return

        # 鑾峰彇鑲＄エ浠ｇ爜
        code = vals[0]
        name = vals[1]

        # 閫氳繃 code 浠?df_all 鑾峰彇 category 鍐呭
        try:
            category_content = self.df_all.loc[code, 'category']
        except KeyError:
            category_content = "鏈壘鍒拌鑲＄エ鐨?category 淇℃伅"

        # self.show_category_detail(code,name,category_content)
        self.view_stock_remarks(code, name)
        pyperclip.copy(code)



    def on_tree_right_click(self, event):
        """鍙抽敭鐐瑰嚮 TreeView 琛?""
        # 纭繚閫変腑琛?        item_id = self.tree.identify_row(event.y)

        if item_id:
            # 閫変腑璇ヨ
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            
            # 鑾峰彇鍩烘湰淇℃伅
            values = self.tree.item(item_id, 'values')
            stock_code = values[0]
            stock_name = values[1] if len(values) > 1 else "鏈煡"
            
            # 鍒涘缓鑿滃崟
            menu = tk.Menu(self, tearoff=0)
            
            menu.add_command(label=f"馃摑 澶嶅埗鎻愬彇淇℃伅 ({stock_code})", 
                            command=lambda: self.copy_stock_info(stock_code))
                            
            menu.add_separator()
            
            menu.add_command(label="馃И 娴嬭瘯涔板崠绛栫暐", 
                            command=lambda  e=event: self.on_tree_click_for_tooltip(e,stock_code,stock_name,True))
                            # command=lambda: self.test_strategy_for_stock(stock_code, stock_name))
            menu.add_command(label="馃И 娴嬭瘯Code绛栫暐", 
                            command=lambda  e=event: check_code(self.df_all,stock_code,self.search_var1.get()))

            menu.add_command(label="馃彿锔?娣诲姞鏍囨敞澶囨敞", 
                            command=lambda: self.add_stock_remark(stock_code, stock_name))
            
            menu.add_command(label="馃敂 鍔犲叆璇煶棰勮",
                            command=lambda: self.add_voice_monitor_dialog(stock_code, stock_name))
                            
            menu.add_command(label="馃摉 鏌ョ湅鏍囨敞鎵嬫湱", 
                            command=lambda: self.view_stock_remarks(stock_code, stock_name))
            
            menu.add_separator()
            
            menu.add_command(label=f"馃殌 鍙戦€佸埌鍏宠仈杞欢", 
                            command=lambda: self.original_push_logic(stock_code))
            menu.add_command(label="馃攳 绛栫暐鐧界洅璇勪及...", command=lambda: self.open_strategy_manager(verify_code=stock_code), foreground="blue")
            
            # 寮瑰嚭鑿滃崟
            menu.post(event.x_root, event.y_root)

    def get_stock_info_text(self, code):
        """鑾峰彇鏍煎紡鍖栫殑鑲＄エ淇℃伅鏂囨湰"""
        if code not in self.df_all.index:
            return None
            
        stock_data = self.df_all.loc[code]
        
        # 璁＄畻/鑾峰彇瀛楁
        name = stock_data.get('name', 'N/A')
        close = stock_data.get('trade', 'N/A')
        
        # 璁＄畻 Boll
        upper = stock_data.get('upper', 'N/A')
        lower = stock_data.get('lower', 'N/A')
        
        # 鍒ゆ柇閫昏緫
        try:
            high = float(stock_data.get('high', 0))
            low = float(stock_data.get('low', 0))
            c_close = float(close) if close != 'N/A' else 0
            c_upper = float(upper) if upper != 'N/A' else 0
            c_lower = float(lower) if lower != 'N/A' else 0
            
            boll = "Yes" if high > c_upper else "No"
            breakthrough = "Yes" if high > c_upper else "No"
            
            # 淇″彿鍥炬爣閫昏緫
            signal_val = stock_data.get('signal', '')
            signal_icon = "馃敶" if signal_val else "鈿?
            
            # 寮哄娍鍒ゆ柇 (L1>L2 & H1>H2 杩欑闇€瑕佸巻鍙叉暟鎹紝杩欓噷绠€鍖?
            strength = "Check Graph" 
            
        except Exception:
            boll = "CalcError"
            breakthrough = "Unknown"
            signal_icon = "?"
            strength = "Unknown"

        # 鏋勫缓鏂囨湰
        info_text = (
            f"銆恵code}銆憑name}:{close}\n"
            f"{'鈹€' * 20}\n"
            f"馃搳 鎹㈡墜鐜? {stock_data.get('ratio', 'N/A')}\n"
            f"馃搳 鎴愪氦閲? {stock_data.get('volume', 'N/A')}\n"
            f"馃搱 杩為槼: {stock_data.get('red', 'N/A')} 馃敽\n"
            f"馃搲 杩為槾: {stock_data.get('gren', 'N/A')} 馃敾\n"
            f"馃搱 绐佺牬甯冩灄: {boll}\n"
            f"  signal: {signal_icon} (low<10 & C>5)\n"
            f"  Upper:  {upper:.2f}\n"
            f"  Lower:  {lower:.2f}\n"
            f"馃殌 绐佺牬: {breakthrough} (high > upper)\n"
            f"馃挭 寮哄娍: {strength} (L1>L2 & H1>H2)"
        )
        return info_text

    def original_push_logic(self, stock_code,select_win=False):
        """鍘熸湁鐨勬帹閫侀€昏緫 + 鑷姩娣诲姞鎵嬫湱"""
        try:
            # 1. 灏濊瘯鑾峰彇浠锋牸鍜屼俊鎭紝鐢ㄤ簬鑷姩娣诲姞澶囨敞
            close_price = "N/A"
            info_text = ""
            if stock_code in self.df_all.index:
                close_price = self.df_all.loc[stock_code].get('trade', 'N/A')
                info_text = self.get_stock_info_text(stock_code)

            # 2. 鎵ц鍘熸湁鎺ㄩ€?            if self.push_stock_info(stock_code, self.df_all.loc[stock_code] if stock_code in self.df_all.index else None):
                 self.status_var2.set(f"鍙戦€佹垚鍔? {stock_code}")
                 
                 # 3. 濡傛灉鍙戦€佹垚鍔燂紝鑷姩娣诲姞鎵嬫湱
                 if info_text:
                     # 鏋勯€犲娉ㄥ唴瀹?                     remark_content = f"娣诲姞Close:{close_price}\n{info_text}"
                     self.handbook.add_remark(stock_code, remark_content)
                     logger.info(f"宸茶嚜鍔ㄦ坊鍔犳墜鏈? {stock_code}")
                     
                     # 鍙€夛細涔熷鍒跺埌鍓创鏉匡紝鏂逛究绮樿创
                     pyperclip.copy(remark_content)

            else:
                 self.status_var2.set(f"鍙戦€佸け璐? {stock_code}")

        except Exception as e:
            logger.error(f"Push logic error: {e}")

    def test_strategy_for_stock(self, code, name):
        """
        娴嬭瘯閫変腑鑲＄エ鐨勪拱鍗栫瓥鐣ュ苟鐢熸垚鍒嗘瀽鎶ュ憡
        鐢ㄤ簬楠岃瘉鏁版嵁瀹屾暣鎬у拰绛栫暐鍐崇瓥
        """
        try:
            from intraday_decision_engine import IntradayDecisionEngine
            # 妫€鏌ユ暟鎹槸鍚﹀瓨鍦?            if code not in self.df_all.index:
                messagebox.showwarning("鏁版嵁缂哄け", f"鏈壘鍒颁唬鐮?{code} 鐨勬暟鎹?)
                return
            
            row = self.df_all.loc[code]
            
            # 鏋勫缓琛屾儏鏁版嵁瀛楀吀
            row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
            
            # 鏋勫缓蹇収鏁版嵁锛堜娇鐢?df_all 涓殑姝ｇ‘瀛楁鍚嶏級
            # lastp1d = 鏄ㄦ棩鏀剁洏浠? lastv1d/2d/3d = 鏄ㄦ棩/鍓嶆棩/澶у墠鏃ユ垚浜ら噺
            # lasth1d/lastl1d = 鏄ㄦ棩鏈€楂?鏈€浣庝环, per1d = 鏄ㄦ棩娑ㄥ箙
            snapshot = {
                'last_close': row_dict.get('lastp1d', row_dict.get('settle', 0)),
                'percent': row_dict.get('per1d', row_dict.get('percent', 0)),
                'nclose': row_dict.get('nclose', 0),    # 浠婃棩鍧囦环
                'lowvol': row_dict.get('lowvol', 0),    # 鏈€杩戞渶浣庝环鐨勫湴閲?                'llowvol': row_dict.get('llowvol', 0),  # 涓夊崄鏃ュ唴鐨勫湴閲?                'ma20d': row_dict.get('ma20d', 0),      # 浜屽崄鏃ョ嚎
                'ma5d': row_dict.get('ma5d', 0),        # 浜旀棩绾?                'hmax': row_dict.get('hmax', 0),        # 30鏃ユ渶楂樹环
                'hmax60': row_dict.get('hmax60', 0),    # 60鏃ユ渶楂樹环
                'low60': row_dict.get('low60', 0),      # 60鏃ユ渶浣庝环
                'low10': row_dict.get('low10', 0),      # 10鏃ユ渶浣庝环
                'high4': row_dict.get('high4', 0),      # 4鏃ユ渶楂?                'max5': row_dict.get('max5', 0),        # 5鏃ユ渶楂?                'lower': row_dict.get('lower', 0),      # 甯冩灄涓嬭建
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
                'cost_price': row_dict.get('lastp3d', 0),  # 榛樿涓夊ぉ鍓嶆敹鐩樹环涓烘垚鏈?                'hvolume': row.get('hv', 0),
                'lvolume': row.get('lv', 0),
            }
            
            # 鑷姩濉厖 1-15 鏃ョ殑鍘嗗彶 OHLCV 鏁版嵁
            for i in range(1, 16):
                for suffix in ['p', 'h', 'l', 'o', 'v']:
                    key = f'last{suffix}{i}d'
                    if key in row_dict:
                        snapshot[key] = row_dict[key]
            
            # 鐗规畩鍒悕鏄犲皠浠ュ吋瀹规棫浠ｇ爜
            snapshot['lastv1d'] = snapshot.get('lastv1d', 0)
            snapshot['lastv2d'] = snapshot.get('lastv2d', 0)
            snapshot['lastv3d'] = snapshot.get('lastv3d', 0)
            snapshot['lasth1d'] = snapshot.get('lasth1d', 0)
            snapshot['lastl1d'] = snapshot.get('lastl1d', 0)
            snapshot['win'] = snapshot.get('win', 0)            # 鍔犻€熻繛闃?            snapshot['sum_perc'] = snapshot.get('sum_perc', 0)  # 鍔犻€熻繛闃虫定骞?            snapshot['red'] = snapshot.get('red', 0)            # 浜旀棩绾夸笂鏁版嵁
            snapshot['gren'] = snapshot.get('gren', 0)          # 寮卞娍缁挎煴鏁版嵁
            snapshot['red'] = snapshot.get('red', 0)  #5鏃ョ嚎涓婃棩绾?            
            # 鍒涘缓鍐崇瓥寮曟搸瀹炰緥
            engine = IntradayDecisionEngine()
            
            # 鎵ц璇勪及
            result = engine.evaluate(row_dict, snapshot, mode="full")
            
            # 妫€娴嬫暟鎹己澶憋紙浣跨敤 df_all 涓殑姝ｇ‘瀛楁鍚嶏級
            missing_fields = []
            critical_fields = ['trade', 'open', 'high', 'low', 'nclose', 'volume', 
                              'ratio', 'ma5d', 'ma10d', 'lastp1d', 'percent']
            for field in critical_fields:
                val = row_dict.get(field, None)
                if val is None or (isinstance(val, (int, float)) and val == 0):
                    missing_fields.append(field)
            
            # 鏋勫缓鎶ュ憡
            report_lines = [
                f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣",
                f"馃搳 绛栫暐娴嬭瘯鎶ュ憡 - {name} ({code})",
                f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣",
                "",
                "銆愬喅绛栫粨鏋溿€?,
                f"  鍔ㄤ綔: {result['action']}",
                f"  浠撲綅: {result['position'] * 100:.0f}%",
                f"  鍘熷洜: {result['reason']}",
                "",
            ]
            
            # 鍐崇瓥璋冭瘯淇℃伅锛堜紭鍏堟樉绀轰究浜庡垎鏋愶級
            debug = result.get('debug', {})
            if debug:
                report_lines.append("銆愬喅绛栬皟璇曚俊鎭€?)
                for key, val in debug.items():
                    if isinstance(val, float):
                        report_lines.append(f"  {key}: {val:.2f}")
                    elif isinstance(val, list):
                        report_lines.append(f"  {key}: {', '.join(map(str, val))}")
                    else:
                        report_lines.append(f"  {key}: {val}")
                report_lines.append("")
            
            # 鏁版嵁瀹屾暣鎬ф鏌?            if missing_fields:
                report_lines.extend([
                    "鈿狅笍 銆愭暟鎹己澶辫鍛娿€?,
                    f"  缂哄け瀛楁: {', '.join(missing_fields)}",
                    "  寤鸿: 妫€鏌ユ暟鎹簮鎴栭噸鏂板姞杞?,
                    ""
                ])
            else:
                report_lines.extend([
                    "鉁?銆愭暟鎹畬鏁存€ф鏌ャ€?,
                    "  鎵€鏈夊叧閿瓧娈垫甯?,
                    ""
                ])
            
            # 鍏抽敭琛屾儏鏁版嵁
            report_lines.extend([
                "銆愬叧閿鎯呮暟鎹€?,
                f"  褰撳墠浠? {row_dict.get('trade', 'N/A')}",
                f"  寮€鐩樹环: {row_dict.get('open', 'N/A')}",
                f"  鏈€楂樹环: {row_dict.get('high', 'N/A')}",
                f"  鏈€浣庝环: {row_dict.get('low', 'N/A')}",
                f"  鍧囦环:   {row_dict.get('nclose', 'N/A')}",
                f"  鏄ㄦ敹:   {snapshot.get('last_close', 'N/A')}",
                "",
                "銆愭妧鏈寚鏍囥€?,
                f"  MA5:    {row_dict.get('ma5d', 'N/A')}",
                f"  MA10:   {row_dict.get('ma10d', 'N/A')}",
                f"  MA20:   {row_dict.get('ma20d', 'N/A')}",
                f"  MACD:   {row_dict.get('macd', 'N/A')}",
                f"  KDJ_J:  {row_dict.get('kdj_j', 'N/A')}",
                "",
                "銆愰噺鑳芥暟鎹€?,
                f"  鎴愪氦閲? : {row_dict.get('volume', 'N/A')}",
                f"  鎹㈡墜鐜? : {row_dict.get('ratio', 'N/A')}%",
                f"  鏄ㄦ棩閲? : {snapshot.get('lastv1d', 'N/A')}",
                f"  鏈€杩戦珮閲? {snapshot.get('hvolume', 'N/A')}",
                f"  鏈€杩戝湴閲? {snapshot.get('lvolume', 'N/A')}",
            ])
            
            report_text = "\n".join(report_lines)
            
            # 鑾峰彇褰撳墠娴嬭瘯浠风敤浜庢ā鎷熸垚浜?            price = row_dict.get('trade', row_dict.get('now', 0))
            
            # 鍒涘缓鎶ュ憡绐楀彛
            self._show_strategy_report_window(code, name, report_text, result, price=price)
            
        except Exception as e:
            logger.error(f"Strategy test error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("娴嬭瘯澶辫触", f"绛栫暐娴嬭瘯鍑洪敊: {e}")

    def _show_strategy_report_window(self, code, name, report_text, result, price=0.0):
        """鏄剧ず绛栫暐娴嬭瘯鎶ュ憡绐楀彛 (绐楀彛澶嶇敤妯″紡 - 浼樺寲鐗?"""
        window_id = '绛栫暐娴嬭瘯'
        
        action = result.get('action', '鎸佷粨')
        action_color = {
            '涔板叆': '#4CAF50',
            '鍗栧嚭': '#F44336',
            '姝㈡崯': '#FF5722',
            '姝㈢泩': '#2196F3',
            '鎸佷粨': '#9E9E9E'
        }.get(action, '#9E9E9E')

        # 1. 妫€鏌ョ獥鍙ｆ槸鍚﹀凡瀛樺湪涓旀湭閿€姣?        if hasattr(self, 'strategy_report_win') and self.strategy_report_win and self.strategy_report_win.winfo_exists():
            win = self.strategy_report_win
            win.title(f"馃И 绛栫暐娴嬭瘯 - {name} ({code})")
            win.lift()
            win.attributes("-topmost", True)
            win.after(50, lambda: win.attributes("-topmost", False))
            # 濡傛灉缁勪欢宸插瓨鍦紝鍒欑洿鎺ユ洿鏂帮紝涓嶉攢姣佷篃涓嶆姠澶虹劍鐐?            if hasattr(win, 'txt_widget'):
                win.top_frame.config(bg=action_color)
                win.action_label.config(
                    text=f"寤鸿: {action} | 浠撲綅: {result['position']*100:.0f}%", 
                    bg=action_color
                )
                win.txt_widget.config(state='normal')
                win.txt_widget.delete('1.0', 'end')
                win.txt_widget.insert('1.0', report_text)
                win.txt_widget.config(state='disabled')
                win.report_text = report_text # 鏇存柊澶嶅埗寮曠敤鐨勬枃鏈?                return
            else:
                # 鍏滃簳锛氭竻绌洪噸寤?                for widget in win.winfo_children():
                    widget.destroy()
        else:
            win = tk.Toplevel(self)
            self.strategy_report_win = win
            self.load_window_position(win, window_id, default_width=600, default_height=850)

        win.title(f"馃И 绛栫暐娴嬭瘯 - {name} ({code})")
        win.report_text = report_text

        # 2. 鏋勫缓鎸佷箙鍖?UI
        # 椤堕儴鐘舵€佹爮
        win.top_frame = tk.Frame(win, bg=action_color, height=40)
        win.top_frame.pack(fill='x')
        win.top_frame.pack_propagate(False)
        
        win.action_label = tk.Label(win.top_frame, 
                               text=f"寤鸿: {action} | 浠撲綅: {result['position']*100:.0f}%",
                               fg='white', bg=action_color,
                               font=('Microsoft YaHei', 14, 'bold'))
        win.action_label.pack(pady=8)
        
        # 鎶ュ憡鏂囨湰鍖哄煙
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
        
        # 搴曢儴鎸夐挳
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        
        def copy_report():
            win.clipboard_clear()
            win.clipboard_append(win.report_text)
            self.status_var2.set("鎶ュ憡宸插鍒跺埌鍓创鏉?)
        
        tk.Button(btn_frame, text="馃搵 澶嶅埗鎶ュ憡", command=copy_report, 
                 width=12).pack(side='left', padx=5)
        
        def run_simulation():
            if not self.live_strategy:
                messagebox.showwarning("璀﹀憡", "浜ゆ槗寮曟搸鏈惎鍔?)
                return
            
            # 鍒涘缓妯℃嫙鍙傛暟璁剧疆灏忕獥鍙?            sim_win = tk.Toplevel(win)
            sim_win.title(f"妯℃嫙鎴愪氦璁剧疆 - {name}")
            sim_win_id = '妯℃嫙鎴愪氦璁剧疆'
            sim_win.geometry("350x480") # 绋嶅井璋冨ぇ涓€鐐归€傚簲鏂版帶浠?            sim_win.transient(win)
            sim_win.grab_set()
            self.load_window_position(sim_win, sim_win_id, default_width=350, default_height=480)
            main_frm = tk.Frame(sim_win, padx=20, pady=10)
            main_frm.pack(fill="both", expand=True)
            
            tk.Label(main_frm, text=f"鑲＄エ: {name} ({code})", font=("Arial", 11, "bold")).pack(pady=(0,5))
            
            # --- 璧勯噾涓庝粨浣嶇鐞?---
            tk.Label(main_frm, text="妯℃嫙鍙敤鏈噾 (鍏?:").pack(anchor="w")
            total_cap_var = tk.DoubleVar(value=100000.0)
            entry_cap = tk.Entry(main_frm, textvariable=total_cap_var)
            entry_cap.pack(fill="x", pady=2)

            # 鍔ㄤ綔閫夋嫨
            tk.Label(main_frm, text="鎴愪氦鍔ㄤ綔:").pack(anchor="w")
            action_var = tk.StringVar(value=action if action in ['涔板叆', '鍗栧嚭', '姝㈡崯', '姝㈢泩'] else '涔板叆')
            action_combo = ttk.Combobox(main_frm, textvariable=action_var, values=['涔板叆', '鍗栧嚭', '姝㈡崯', '姝㈢泩'], state="readonly")
            action_combo.pack(fill="x", pady=2)
            
            # 浠锋牸杈撳叆
            tk.Label(main_frm, text="鎴愪氦浠锋牸:").pack(anchor="w")
            price_var = tk.DoubleVar(value=round(float(price), 3))
            entry_price = tk.Entry(main_frm, textvariable=price_var)
            entry_price.pack(fill="x", pady=2)

            # 姣斾緥蹇嵎閿?            ratio_frm = tk.Frame(main_frm)
            ratio_frm.pack(fill="x", pady=5)
            
            def calc_and_set_amount(r):
                try:
                    p = price_var.get()
                    cap = total_cap_var.get()
                    if p > 0:
                        # 绠€鍗曡绠楋細(鎬绘湰閲?* 姣斾緥) / (浠锋牸 * (1 + 鎵嬬画璐?)
                        qty = int((cap * r) / (p * 1.0003)) // 100 * 100
                        amount_var.set(max(100, qty) if r > 0 else 100)
                except:
                    pass

            tk.Label(main_frm, text="蹇€熶粨浣嶆瘮渚?").pack(anchor="w")
            btn_box = tk.Frame(main_frm)
            btn_box.pack(fill="x")
            for label, r in [("1/10",0.1), ("1/5",0.2), ("1/3",0.33), ("1/2",0.5), ("鍏ㄤ粨",1.0)]:
                tk.Button(btn_box, text=label, command=lambda val=r: calc_and_set_amount(val), font=("Arial", 8)).pack(side="left", padx=1, expand=True, fill="x")
            
            # 鏁伴噺杈撳叆
            tk.Label(main_frm, text="鏈€鍚庢垚浜ゆ暟閲?(鑲?:", font=("Arial", 9, "bold")).pack(anchor="w", pady=(5,0))
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
                        raise ValueError("浠锋牸鍜屾暟閲忓繀椤诲ぇ浜?")
                        
                    confirm_msg = f"纭畾浠ヤ环鏍?{s_price} {s_action} {s_amount}鑲?[{name}] 鍚?"
                    if messagebox.askyesno("妯℃嫙浜ゆ槗纭", confirm_msg, parent=sim_win):
                        self.live_strategy.trading_logger.record_trade(
                            code, name, s_action, s_price, s_amount
                        )
                        messagebox.showinfo("鎴愬姛", f"妯℃嫙鎴愪氦宸茶褰? {s_action} {name} @ {s_price}", parent=sim_win)
                        on_close()
                except Exception as e:
                    messagebox.showerror("閿欒", f"杈撳叆鏃犳晥: {e}", parent=sim_win)
                    on_close()
            tk.Button(main_frm, text="馃敟 鎵ц妯℃嫙鎴愪氦骞惰鍏ョ粺璁?, command=submit_sim, 
                      bg="#ffecb3", font=("Arial", 10, "bold"), pady=10).pack(fill="x", pady=10)
            
            tk.Button(main_frm, text="鏀惧純鍙栨秷", command=sim_win.destroy).pack(fill="x")
            
            
            sim_win.bind("<Escape>", on_close)
            sim_win.protocol("WM_DELETE_WINDOW", on_close)

        tk.Button(btn_frame, text="馃殌 妯℃嫙鎴愪氦璁剧疆", command=run_simulation, 
                 bg="#ccff90", fg="#333", font=("Arial", 10, "bold"), width=15).pack(side='left', padx=5)

        tk.Button(btn_frame, text="鍏抽棴 (ESC)", command=lambda: on_close(), 
                 width=12).pack(side='left', padx=5)

        def on_close(event=None):
            self.save_window_position(win, window_id)
            win.destroy()
            self.strategy_report_win = None
            
        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)
    def copy_stock_info(self, code):
        """鎻愬彇骞跺鍒舵牸寮忓寲淇℃伅"""
        try:
            info_text = self.get_stock_info_text(code)
            if not info_text:
                messagebox.showwarning("鏁版嵁缂哄け", f"鏈壘鍒颁唬鐮?{code} 鐨勫畬鏁存暟鎹?)
                return

            pyperclip.copy(info_text)
            
            # 鑾峰彇鍚嶇О鐢ㄤ簬鎻愮ず
            name = "鏈煡"
            if code in self.df_all.index:
                name = self.df_all.loc[code].get('name', '鏈煡')
                
            self.status_var2.set(f"宸插鍒?{name} 淇℃伅")
            
        except Exception as e:
            logger.error(f"Copy Info Error: {e}")
            messagebox.showerror("閿欒", f"鎻愬彇淇℃伅澶辫触: {e}")

    def add_stock_remark(self, code, name):
        """娣诲姞澶囨敞 - 浣跨敤鑷畾涔夌獥鍙ｆ敮鎸佸琛?""
        try:
            win = tk.Toplevel(self)
            win.title(f"娣诲姞澶囨敞 - {name} ({code})")
            
            # --- 绐楀彛瀹氫綅: 鍙充笅瑙掑湪榧犳爣闄勮繎 ---
            w, h = 550, 320
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            pos_x, pos_y = mx - w - 20, my - h - 20
            pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            win.minsize(480, 260)
            # Label
            tk.Label(
                win,
                text="璇疯緭鍏ュ娉?蹇冨緱 (鏀寔澶氳/绮樿创锛孋trl+Enter淇濆瓨):"
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
            
            # --- 1. 鍙抽敭鑿滃崟 (鏀寔绮樿创) ---
            def show_text_menu(event):
                menu = tk.Menu(win, tearoff=0)
                menu.add_command(label="鍓垏", command=lambda: text_area.event_generate("<<Cut>>"))
                menu.add_command(label="澶嶅埗", command=lambda: text_area.event_generate("<<Copy>>"))
                menu.add_command(label="绮樿创", command=lambda: text_area.event_generate("<<Paste>>"))
                menu.add_separator()
                menu.add_command(label="鍏ㄩ€?, command=lambda: text_area.tag_add("sel", "1.0", "end"))
                menu.post(event.x_root, event.y_root)

            text_area.bind("<Button-3>", show_text_menu)

            # --- 淇濆瓨閫昏緫 ---
            def save(event=None):
                content = text_area.get("1.0", "end-1c").strip()
                if content:
                    self.handbook.add_remark(code, content)
                    messagebox.showinfo("鎴愬姛", "澶囨敞宸叉坊鍔?, parent=win)
                    win.destroy()
                else:
                    win.destroy()  # 绌哄唴瀹圭洿鎺ュ叧闂?                    
            def cancel(event=None):
                save()
                win.destroy()
                return "break"
            
            # --- 2. 蹇嵎閿粦瀹?---
            # 鍥炶溅鑷姩淇濆瓨 (Ctrl+Enter)
            text_area.bind("<Control-Return>", save)
            
            win.bind("<Escape>", cancel)

            btn_frame = tk.Frame(win)
            btn_frame.pack(side="bottom", fill="x", pady=10)   # 鈽?鍏抽敭
            tk.Button(btn_frame, text="淇濆瓨 (Ctrl+Enter)", width=15, command=save, bg="#e1f5fe").pack(side="left", padx=10)
            tk.Button(btn_frame, text="鍙栨秷 (ESC)", width=10, command=cancel).pack(side="left", padx=10)
        except Exception as e:
            logger.error(f"Add remark error: {e}")

    def view_stock_remarks(self, code, name):
        """鏌ョ湅澶囨敞鎵嬫湱绐楀彛"""
        try:
            win = tk.Toplevel(self)
            win.title(f"鏍囨敞鎵嬫湱 - {name} ({code})")
            
            # --- 绐楀彛瀹氫綅 ---
            w, h = 600, 500
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            pos_x, pos_y = mx - w - 20, my - h - 20
            pos_x, pos_y = max(0, pos_x), max(0, pos_y)
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            
            # ESC 鍏抽棴
            def close_view_win(event=None):
                win.destroy()
                return "break"
            win.bind("<Escape>", close_view_win)
            
            # ... UI 鏋勫缓 ...
            # --- 椤堕儴淇℃伅鍖哄煙 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text=f"銆恵code}銆憑name}", font=("Microsoft YaHei", 14, "bold"), fg="#333").pack(anchor="w")
            
            category_info = "鏆傛棤鏉垮潡淇℃伅"
            if code in self.df_all.index:
                row = self.df_all.loc[code]
                cats = row.get('category', '')
                if cats:
                    category_info = f"鏉垮潡: {cats}"
            
            msg = tk.Message(top_frame, text=category_info, width=560, font=("Arial", 10), fg="#666") 
            msg.pack(anchor="w", fill="x", pady=2)

            tk.Label(top_frame, text="馃挕 鍙屽嚮鏌ョ湅 / 鍙抽敭鍒犻櫎 / ESC鍏抽棴", fg="gray", font=("Arial", 9)).pack(anchor="e")

            # --- 鍒楄〃鍖哄煙 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            columns = ("time", "content")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            tree.heading("time", text="鏃堕棿")
            tree.heading("content", text="鍐呭姒傝")
            tree.column("time", width=140, anchor="center", stretch=False)
            tree.column("content", width=400, anchor="w")
            
            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            # 鍔犺浇鏁版嵁
            remarks = self.handbook.get_remarks(code)
            for r in remarks:
                raw_content = r['content']
                display_content = raw_content.replace('\n', ' ')
                if len(display_content) > 50:
                    display_content = display_content[:50] + "..."
                tree.insert("", "end", values=(r['time'], display_content))
            
            # --- 璇︽儏寮圭獥 ---
            def show_detail_window(time_str, content, click_x=None, click_y=None):
                d_win = tk.Toplevel(win)
                d_win.title(f"鎵嬫湱璇︽儏 - {time_str}")
                
                dw, dh = 600, 450
                if click_x is None:
                    click_x = d_win.winfo_pointerx()
                    click_y = d_win.winfo_pointery()
                
                dx, dy = click_x - dw - 20, click_y - dh - 20
                dx, dy = max(0, dx), max(0, dy)
                d_win.geometry(f"{dw}x{dh}+{dx}+{dy}")
                
                # ESC 鍏抽棴璇︽儏
                def close_detail_win(event=None):
                    d_win.destroy()
                    return "break" # 闃绘浜嬩欢浼犳挱
                d_win.bind("<Escape>", close_detail_win)
                
                # 璁句负 Topmost 骞惰幏鍙栫劍鐐癸紝闃叉璇Е搴曞眰
                d_win.attributes("-topmost", True)
                d_win.focus_force()
                d_win.grab_set() # 妯℃€佺獥鍙ｏ紝寮哄埗鐒︾偣鐩村埌鍏抽棴
                
                tk.Label(d_win, text=f"璁板綍鏃堕棿: {time_str}", font=("Arial", 10, "bold"), fg="#004d40").pack(pady=5, anchor="w", padx=10)
                
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
                        messagebox.showinfo("鎻愮ず", "鍐呭宸插鍒?, parent=d_win)
                    except:
                        pass
                def save_edit():
                    new_content = txt.get("1.0", "end-1c").strip()
                    if not new_content:
                        messagebox.showwarning("鎻愮ず", "鍐呭涓嶈兘涓虹┖", parent=d_win)
                        return

                    # 鎵惧埌瀵瑰簲 remark
                    for r in self.handbook.get_remarks(code):
                        if r['time'] == time_str:
                            # 鍋囪 handbook 鏀寔 update
                            self.handbook.update_remark(code, r['timestamp'], new_content)
                            break

                    # 鍚屾鏇存柊鍒楄〃鏄剧ず锛堝彧鏇存柊姒傝锛?                    short = new_content.replace('\n', ' ')
                    if len(short) > 50:
                        short = short[:50] + "..."
                    tree.item(tree.selection()[0], values=(time_str, short))
                    toast_message(d_win, "鎴愬姛澶囨敞宸叉洿鏂?)

                btn_frame = tk.Frame(d_win)
                btn_frame.pack(pady=5)
                tk.Button(btn_frame, text="淇濆瓨淇敼", command=lambda: save_edit()).pack(side="left", padx=10)
                tk.Button(btn_frame, text="澶嶅埗鍏ㄩ儴", command=copy_content).pack(side="left", padx=10)
                tk.Button(btn_frame, text="鍏抽棴 (ESC)", command=d_win.destroy).pack(side="left", padx=10)
                
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

            # 鍙抽敭鍒犻櫎
            def on_rmk_right_click(event):
                item = tree.identify_row(event.y)
                if item:
                    tree.selection_set(item)
                    menu = tk.Menu(win, tearoff=0)
                    menu.add_command(label="鍒犻櫎姝ゆ潯", command=lambda: delete_current(item))
                    menu.post(event.x_root, event.y_root)
                    
            def delete_current(item):
                values = tree.item(item, "values")
                time_str = values[0]
                confirm = messagebox.askyesno("纭", "纭畾鍒犻櫎杩欐潯澶囨敞鍚?", parent=win)
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
            messagebox.showerror("Error", f"寮€鍚墜鏈け璐? {e}")

    def open_handbook_overview(self):
        """鎵嬫湱鎬昏绐楀彛"""
        try:
            win = tk.Toplevel(self)
            win.title("鎵嬫湱鎬昏")
            # --- 绐楀彛瀹氫綅 ---
            w, h = 900, 600
            # 灞呬腑鏄剧ず
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            pos_x = (sw - w) // 2
            pos_y = (sh - h) // 2
            win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            
            # ESC 鍏抽棴
            win.bind("<Escape>", lambda e: win.destroy())
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 椤堕儴婊ら暅/鎿嶄綔鍖哄煙 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text="馃攳 蹇€熸祻瑙堟墍鏈夋墜鏈?, font=("Arial", 12, "bold")).pack(side="left")
            
            # --- 鍒楄〃鍖哄煙 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            columns = ("time", "code", "name", "content")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            # 鎺掑簭鐘舵€?            self._hb_sort_col = None
            self._hb_sort_reverse = False

            def treeview_sort_column(col):
                """閫氱敤鎺掑簭鍑芥暟"""
                l = [(tree.set(k, col), k) for k in tree.get_children('')]
                
                # 绠€鍗曞€兼瘮杈?                l.sort(reverse=self._hb_sort_reverse)
                self._hb_sort_reverse = not self._hb_sort_reverse  # 鍙嶈浆

                for index, (val, k) in enumerate(l):
                    tree.move(k, '', index)
                    
                # 鏇存柊琛ㄥご鏄剧ず (鍙€?
                for c in columns:
                     tree.heading(c, text=c.capitalize()) # 閲嶇疆
                
                arrow = "鈫? if self._hb_sort_reverse else "鈫?
                tree.heading(col, text=f"{col.capitalize()} {arrow}")

            tree.heading("time", text="鏃堕棿", command=lambda: treeview_sort_column("time"))
            tree.heading("code", text="浠ｇ爜", command=lambda: treeview_sort_column("code"))
            tree.heading("name", text="鍚嶇О", command=lambda: treeview_sort_column("name"))
            tree.heading("content", text="鍐呭姒傝", command=lambda: treeview_sort_column("content"))
            
            tree.column("time", width=160, anchor="center")
            tree.column("code", width=100, anchor="center")
            tree.column("name", width=120, anchor="center")
            tree.column("content", width=500, anchor="w")
            
            vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            tree.configure(yscroll=vsb.set)
            
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            
            # --- 鍔犺浇鏁版嵁 ---
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
            
            # 榛樿鎸夋椂闂村€掑簭
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
                # toast_message(self, f"stock_code: {stock_code} 宸插鍒?)
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
            # --- 鍙屽嚮浜嬩欢 (澶嶇敤涔嬪墠鐨?detail window) ---
            def on_handbook_double_click(event):
                item = tree.selection()
                if not item: return
                values = tree.item(item[0], "values")
                # values: (time, code, name, content_preview)
                
                target_code = values[1]
                target_time = values[0]
                target_name = values[2]
                
                # 鍐嶆鏌ユ壘瀹屾暣鍐呭 (鏁堢巼绋嶄綆浣嗙畝鍗?
                full_content = ""
                rmks = self.handbook.get_remarks(target_code)
                for r in rmks:
                    if r['time'] == target_time:
                        full_content = r['content']
                        break
                
                if full_content:
                    # 璋冪敤涔嬪墠瀹氫箟鐨?show_detail_window ?
                    # 鐢变簬浣滅敤鍩熼棶棰橈紝鏈€濂芥槸鎶?show_detail_window 鎻愬嚭鏉ュ彉鎴愮被鏂规硶锛?                    # 鎴栬€呰繖閲屽啀澶嶅埗涓€浠界畝鍗曠殑銆備负閬垮厤閲嶅浠ｇ爜锛岃繖閲岀畝鍗曞疄鐜颁竴涓€?                    # logger.info(f'on_handbook_double_click stock_code:{target_code} name:{target_name}')
                    show_simple_detail(target_time, target_code, values[2], full_content, event.x_root, event.y_root)

            def show_simple_detail(time_str, code, name, content, cx, cy):
                d_win = tk.Toplevel(win)
                d_win.title(f"鎵嬫湱璇︽儏 - {name}({code})")
                d_win.attributes("-topmost", True)
                
                dw, dh = 600, 450
                dx, dy = cx - dw - 20, cy - dh - 20
                dx, dy = max(0, dx), max(0, dy)
                d_win.geometry(f"{dw}x{dh}+{dx}+{dy}")
                
                d_win.bind("<Escape>", lambda e: d_win.destroy())
                d_win.focus_force()
                d_win.grab_set()

                tk.Label(d_win, text=f"鑲＄エ: {name} ({code})   鏃堕棿: {time_str}", font=("Arial", 10, "bold"), fg="#004d40").pack(pady=5, anchor="w", padx=10)
                
                txt_frame = tk.Frame(d_win)
                txt_frame.pack(fill="both", expand=True, padx=10, pady=5)
                
                txt_scroll = ttk.Scrollbar(txt_frame)
                txt = tk.Text(txt_frame, wrap="word", font=("Arial", 11), yscrollcommand=txt_scroll.set, padx=5, pady=5)
                txt_scroll.config(command=txt.yview)
                
                txt.pack(side="left", fill="both", expand=True)
                txt_scroll.pack(side="right", fill="y")
                
                txt.insert("1.0", content)
                txt.config(state="disabled") 
                
                tk.Button(d_win, text="鍏抽棴 (ESC)", command=d_win.destroy).pack(pady=5)

            def delete_selected_handbook(event=None):

                # 濡傛灉娌℃湁閫変腑琛岋紝灏濊瘯閫変腑绗竴鏉?                if not tree.selection():
                    children = tree.get_children()
                    if not children:
                        return
                    tree.selection_set(children[0])
                    tree.focus(children[0])
                    tree.see(children[0])
                    tree.focus_set()  # 淇濊瘉閿洏浜嬩欢鐢熸晥

                item = tree.selection()
                # if not item:
                #     return

                item_id = item[0]
                values = tree.item(item_id, "values")
                target_code = values[1]
                target_time = values[0]
                target_name = values[2]
                if not messagebox.askyesno(
                    "纭鍒犻櫎",
                    f"纭畾瑕佸垹闄や互涓嬫墜鏈悧锛焅n\n"
                    f"鑲＄エ锛歿target_name} ({target_code})\n"
                    f"鏃堕棿锛歿target_time}"
                ):
                    return

                try:
                    # 鍒犻櫎鍓嶈绠椾笅涓€鏉?                    next_item = tree.next(item_id) or tree.prev(item_id)

                    # 馃敶 鐪熸鍒犻櫎鏁版嵁
                    ok = self.handbook.delete_remark(target_code, target_time)
                    if not ok:
                        messagebox.showwarning(
                            "鍒犻櫎澶辫触",
                            "鏈湪鏁版嵁涓壘鍒拌鎵嬫湱锛堝彲鑳芥椂闂翠笉鍖归厤锛?
                        )
                        return

                    # UI 鍒犻櫎
                    tree.delete(item_id)

                    toast_message(
                        self,
                        f"宸插垹闄ゆ墜鏈細{target_name} {target_time}"
                    )

                    # 鉁?淇敼4锛氬垹闄ゅ悗鑷姩閫変腑涓嬩竴琛?                    if next_item and tree.exists(next_item):
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
                    tree.focus_set()  # 淇濊瘉閿洏鐒︾偣浠嶅湪 treeview

                except Exception as e:
                    logger.error(f"delete handbook error: {e}")
                    messagebox.showerror("閿欒", f"鍒犻櫎澶辫触: {e}")


            tree.bind("<Button-1>", on_handbook_on_click)
            tree.bind("<Button-3>", on_handbook_right_click)
            tree.bind("<Double-1>", on_handbook_double_click)
            tree.bind("<<TreeviewSelect>>", on_handbook_tree_select) 
            # 鉁?鏂板锛欴elete 閿垹闄?            tree.bind("<Delete>", delete_selected_handbook)
        except Exception as e:
            logger.error(f"Handbook Overview Error: {e}")
            messagebox.showerror("閿欒", f"鎵撳紑鎬昏澶辫触: {e}")

    def _create_monitor_ref_panel(self, parent, row_data, curr_price, set_callback):
        """鍒涘缓鐩戞帶鍙傝€冩暟鎹潰鏉?""
        if row_data is None:
            tk.Label(parent, text="鏃犺缁嗘暟鎹?, fg="#999").pack(pady=20)
            return

        def create_clickable_info(p, label, value, value_type="price"):
            f = tk.Frame(p)
            f.pack(fill="x", pady=2)
            
            lbl_name = tk.Label(f, text=f"{label}:", width=10, anchor="w", fg="#666")
            lbl_name.pack(side="left")
            
            # 浠锋牸瀵规瘮閫昏緫
            val_str = f"{value}"
            arrow = ""
            arrow_fg = ""
            
            if isinstance(value, float):
                val_str = f"{value:.2f}"
                if value_type == "price" and curr_price > 0 and value > 0:
                    if value > curr_price:
                        arrow =  "馃煡 "
                        # arrow = "馃敶 "

                        arrow_fg = "green"
                    elif value < curr_price:
                        arrow =  "馃煩 "
                        # arrow = "馃煝 "
                        arrow_fg = "red"
            
            # 濡傛灉鏈夌澶达紝鍏堟樉绀虹澶?            if arrow:
                tk.Label(f, text=arrow, fg=arrow_fg, font=("Arial", 10, "bold")).pack(side="left")
            
            lbl_val = tk.Label(f, text=val_str, fg="blue", cursor="hand2", font=("Arial", 10, "underline"))
            lbl_val.pack(side="left")
            
            def on_click(e):
                set_callback(val_str, value_type, value)
                # Flash effect
                lbl_val.config(fg="red")
                parent.after(200, lambda: lbl_val.config(fg="blue"))
                
            lbl_val.bind("<Button-1>", on_click)
            
        # 鎸囨爣鍒楄〃
        metrics = [
            ("MA5", row_data.get('ma5d', 0), "price"),
            ("MA10", row_data.get('ma10d', 0), "price"),
            ("MA20", row_data.get('ma20d', 0), "price"),
            ("MA30", row_data.get('ma30d', 0), "price"),
            ("MA60", row_data.get('ma60d', 0), "price"),
            ("鍘嬪姏浣?, row_data.get('support_next', 0), "price"),
            ("鏀拺浣?, row_data.get('support_today', 0), "price"),
            ("涓婅建", row_data.get('upper', 0), "price"),
            ("涓嬭建", row_data.get('lower', 0), "price"),
            ("鏄ㄦ敹", row_data.get('lastp1d', 0), "price"),
            ("寮€鐩?, row_data.get('open', 0), "price"),
            ("鏈€楂?, row_data.get('high', 0), "price"),
            ("鏈€浣?, row_data.get('low', 0), "price"),
            ("娑ㄥ仠浠?, row_data.get('high_limit', 0), "price"),
            ("璺屽仠浠?, row_data.get('low_limit', 0), "price"),
        ]
        
        # 娑ㄥ箙绫?        if 'per1d' in row_data:
            metrics.append(("鏄ㄦ棩娑ㄥ箙%", row_data['per1d'], "percent"))
        if 'per2d' in row_data:
            metrics.append(("鍓嶆棩娑ㄥ箙%", row_data['per2d'], "percent"))
            
        for label, val, vtype in metrics:
            try:
                if val is None: continue
                v = float(val)
                if abs(v) > 0.001: # 杩囨护0鍊?                    create_clickable_info(parent, label, v, vtype)
            except:
                pass

    def add_voice_monitor_dialog(self, code, name):
        """
        寮瑰嚭娣诲姞棰勮鐩戞帶鐨勫璇濇 (浼樺寲鐗?
        """
        try:
            win = tk.Toplevel(self)
            win.title(f"娣诲姞璇煶棰勮 - {name} ({code})")
            window_id = "娣诲姞璇煶棰勮"
            self.load_window_position(win, window_id, default_width=900, default_height=650)
            # --- 甯冨眬 ---
            main_frame = tk.Frame(win)
            main_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            left_frame = tk.Frame(main_frame) 
            left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
            
            right_frame = tk.LabelFrame(main_frame, text="鍙傝€冩暟鎹?(鐐瑰嚮鑷姩濉叆)", width=380)
            right_frame.pack(side="right", fill="both", padx=(10, 0))
            # --- 宸︿晶锛氳緭鍏ュ尯鍩?---
            
            # 鑾峰彇褰撳墠鏁版嵁
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
            
            tk.Label(left_frame, text=f"褰撳墠浠锋牸: {curr_price:.2f}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
            tk.Label(left_frame, text=f"褰撳墠娑ㄥ箙: {curr_change:.2f}%", font=("Arial", 10), fg="#b71c1c" if curr_change>=0 else "#00695c").pack(pady=5, anchor="w")
            
            tk.Label(left_frame, text="閫夋嫨鐩戞帶绫诲瀷:").pack(anchor="w", pady=(15, 5))
            
            type_var = tk.StringVar(value="price_up")
            e_val_var = tk.StringVar(value=f"{curr_price:.2f}") # 缁戝畾Entry鍙橀噺
            
            def on_type_change():
                """鍒囨崲绫诲瀷鏃舵洿鏂伴粯璁ゅ€?""
                t = type_var.get()
                if t == "change_up":
                     # 鍒囨崲鍒版定骞呮椂锛屽～鍏ュ綋鍓嶆定骞呮柟渚夸慨鏀癸紝鎴栬€呮竻绌?                     e_val_var.set(f"{curr_change:.2f}")
                else:
                     # 鍒囨崲鍥炰环鏍?                     e_val_var.set(f"{curr_price:.2f}")

            types = [("浠锋牸绐佺牬 (Price >=)", "price_up"), 
                     ("浠锋牸璺岀牬 (Price <=)", "price_down"),
                     ("娑ㄥ箙瓒呰繃 (Change% >=)", "change_up")]
            
            for text, val in types:
                tk.Radiobutton(left_frame, text=text, variable=type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)
                
            tk.Label(left_frame, text="閫夋嫨鐩戞帶鍛ㄦ湡:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
            
            # 鑾峰彇褰撳墠鍛ㄦ湡
            current_resample = self.global_values.getkey("resample") or 'd'
            resample_var = tk.StringVar(value=current_resample)
            
            resample_combo = ttk.Combobox(left_frame, textvariable=resample_var, width=10)
            resample_combo['values'] = ['d', 'w', 'm', '30', '60']
            resample_combo.pack(anchor="w", padx=10, pady=2)

            tk.Label(left_frame, text="瑙﹀彂闃堝€?", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))
            
            # 闃堝€艰緭鍏ュ尯鍩?(鍖呭惈 +/- 鎸夐挳)
            val_frame = tk.Frame(left_frame)
            val_frame.pack(fill="x", padx=10, pady=5)
            
            e_val = tk.Entry(val_frame, textvariable=e_val_var, font=("Arial", 12))
            e_val.pack(side="left", fill="x", expand=True)
            e_val.focus() # 鑱氱劍
            
            def adjust_val(pct):
                try:
                    current_val = float(e_val_var.get())
                    # 濡傛灉鏄环鏍硷紝鎸夋瘮渚嬭皟鏁?                    # 濡傛灉鏄定骞?灏忎簬20閫氬父瑙嗕负娑ㄥ箙)锛岀洿鎺ュ姞鍑忔暟鍊?
                    # 鎸夌収鐢ㄦ埛闇€姹?"1%澧炲姞鎴栧噺灏?锛屽鏋滄槸浠锋牸閫氬父鎸囦环鏍?* 1.01
                    # 濡傛灉鏄定骞呯被鍨嬶紝閫氬父鎸囨定骞?+ 1
                    
                    t = type_var.get()
                    if t == "change_up":
                         # 娑ㄥ箙鐩存帴鍔犲噺 1 (鍗曚綅%)
                         new_val = current_val + pct
                    else:
                         # 浠锋牸鎸夌櫨鍒嗘瘮璋冩暣
                         new_val = current_val * (1 + pct/100)
                    
                    e_val_var.set(f"{new_val:.2f}")
                except ValueError:
                    pass

            # 鎸夐挳
            tk.Button(val_frame, text="-1%", width=4, command=lambda: adjust_val(-1)).pack(side="left", padx=2)
            tk.Button(val_frame, text="+1%", width=4, command=lambda: adjust_val(1)).pack(side="left", padx=2)

            # --- 鍙充晶锛氭暟鎹弬鑰冮潰鏉?---
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

            # --- 搴曢儴鎸夐挳 ---
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
                        # 鑷姩鍏抽棴锛屼笉鍐嶅脊绐楃‘璁わ紝鎻愬崌鏁堢巼 (鎴栬€呯敤 toast)
                        # messagebox.showinfo("鎴愬姛", f"宸叉坊鍔犵洃鎺? {name} {rtype} {val}", parent=win)
                        logger.info(f"Monitor added: {name} {rtype} {val}")
                        on_close()   # 鉁?姝ｇ‘
                    else:
                        messagebox.showerror("閿欒", "瀹炴椂鐩戞帶妯″潡鏈垵濮嬪寲", parent=win)
                except ValueError:
                    messagebox.showerror("閿欒", "璇疯緭鍏ユ湁鏁堢殑鏁板瓧", parent=win)
            # ESC / 鍏抽棴
            def on_close(event=None):
                # update_window_position(window_id)
                self.save_window_position(win, window_id)
                win.destroy()

            win.bind("<Escape>", on_close)
            win.protocol("WM_DELETE_WINDOW", on_close)
            win.bind("<Return>", confirm)
            tk.Button(btn_frame, text="纭娣诲姞 (Enter)", command=confirm, bg="#ccff90", height=2).pack(side="left", fill="x", expand=True, padx=5)
            tk.Button(btn_frame, text="鍙栨秷 (Esc)", command=on_close, height=2).pack(side="left", fill="x", expand=True, padx=5)
            
        except Exception as e:
            logger.error(f"Add monitor dialog error: {e}")
            messagebox.showerror("Error", f"寮€鍚洃鎺у璇濇澶辫触: {e}")

    def _init_realtime_service_async(self):
        """
        馃殌 寮傛鍒濆鍖?RealtimeDataService (DataPublisher)
        鍦ㄥ悗鍙扮嚎绋嬩腑鍔犺浇 MinuteKlineCache锛岄伩鍏嶉樆濉?UI 鏄剧ず
        """
        def _load_in_thread():
            try:
                start_time = time.time()
                service = DataPublisher(high_performance=False)
                elapsed = time.time() - start_time
                # 浣跨敤 after 瀹夊叏鍦版洿鏂颁富绾跨▼鐘舵€?                self.after(0, lambda: self._on_realtime_service_ready(service, elapsed))
            except Exception as e:
                logger.error(f"鉂?RealtimeDataService 寮傛鍒濆鍖栧け璐? {e}\n{traceback.format_exc()}")
                self.after(0, lambda: self._on_realtime_service_ready(None, 0))

        # 鍦ㄥ悗鍙扮嚎绋嬩腑鍔犺浇
        loader_thread = threading.Thread(target=_load_in_thread, daemon=True, name="RealtimeServiceLoader")
        loader_thread.start()
        logger.info("馃攧 寮€濮嬪悗鍙板姞杞?RealtimeDataService...")

    def _on_realtime_service_ready(self, service, elapsed):
        """澶勭悊 RealtimeDataService 鍔犺浇瀹屾垚"""
        self.realtime_service = service
        self._realtime_service_ready = service is not None
        
        if service:
            logger.info(f"鉁?RealtimeDataService (Local) 宸插氨缁?(鑰楁椂: {elapsed:.2f}s)")
            # 濡傛灉 live_strategy 宸茬粡鍒濆鍖栵紝娉ㄥ叆 realtime_service
            if hasattr(self, 'live_strategy') and self.live_strategy:
                self.live_strategy.realtime_service = service
                logger.info("RealtimeDataService 宸叉敞鍏ュ埌宸插垵濮嬪寲鐨?StockLiveStrategy")
            
            # 濡傛灉绛栫暐鐧界洅绐楀彛宸叉墦寮€锛屾敞鍏?realtime_service
            if hasattr(self, '_strategy_manager_win') and self._strategy_manager_win:
                try:
                    if self._strategy_manager_win.winfo_exists():
                        self._strategy_manager_win.realtime_service = service
                        logger.info("RealtimeDataService 宸叉敞鍏ュ埌宸叉墦寮€鐨?StrategyManager")
                except:
                    pass
            
            # 馃敂 鎵ц鎵€鏈夌瓑寰呬腑鐨勫洖璋?            if hasattr(self, '_realtime_ready_callbacks'):
                for callback in self._realtime_ready_callbacks:
                    try:
                        callback()
                    except Exception as cb_e:
                        logger.warning(f"Realtime ready callback failed: {cb_e}")
                self._realtime_ready_callbacks.clear()
                logger.debug(f"宸叉墽琛?{len(self._realtime_ready_callbacks)} 涓瓑寰呭洖璋?)
        else:
            logger.warning("鈿狅笍 RealtimeDataService 鍔犺浇澶辫触锛岄儴鍒嗗姛鑳藉彲鑳戒笉鍙敤")

    def on_realtime_service_ready(self, callback: Callable[[], None]) -> None:
        """
        娉ㄥ唽鍥炶皟鍑芥暟锛屽湪 RealtimeDataService 灏辩华鏃惰皟鐢?        濡傛灉宸插氨缁垯绔嬪嵆鎵ц鍥炶皟
        """
        if self._realtime_service_ready and self.realtime_service:
            # 宸插氨缁紝绔嬪嵆鎵ц
            try:
                callback()
            except Exception as e:
                logger.warning(f"Realtime ready callback failed: {e}")
        else:
            # 灏氭湭灏辩华锛屽姞鍏ラ槦鍒?            if hasattr(self, '_realtime_ready_callbacks'):
                self._realtime_ready_callbacks.append(callback)
            else:
                self._realtime_ready_callbacks = [callback]

    def _init_live_strategy(self):
        """寤惰繜鍒濆鍖栫瓥鐣ユā鍧?""
        try:
            # 娉ㄦ剰锛歳ealtime_service 鍙兘杩樺湪寮傛鍔犺浇涓紝浼犲叆褰撳墠鍊硷紙鍙兘涓?None锛?            # 绋嶅悗鍦?_on_realtime_service_ready 涓細娉ㄥ叆
            self.live_strategy = StockLiveStrategy(self,alert_cooldown=alert_cooldown,
                                                   voice_enabled=self.voice_var.get(),
                                                   realtime_service=self.realtime_service)
            
            if self.realtime_service:
                logger.info("RealtimeDataService injected into StockLiveStrategy.")
            else:
                logger.info("StockLiveStrategy 宸插垵濮嬪寲 (RealtimeDataService 绋嶅悗娉ㄥ叆)")
            
            # 娉ㄥ唽鎶ヨ鍥炶皟
            self.live_strategy.set_alert_callback(self.on_voice_alert)
            # 娉ㄥ唽璇煶寮€濮嬫挱鏀剧殑鍥炶皟锛岀敤浜庡悓姝ラ棯鐑?            if hasattr(self.live_strategy, '_voice'):
                self.live_strategy._voice.on_speak_start = self.on_voice_speak_start
                self.live_strategy._voice.on_speak_end = self.on_voice_speak_end
            
            logger.info("鉁?瀹炴椂鐩戞帶绛栫暐妯″潡宸插惎鍔?)
        except Exception as e:
            logger.error(f"Failed to init live strategy: {e}")

    # def on_voice_alert(self, code, name, msg):
    #     """
    #     澶勭悊璇煶鎶ヨ瑙﹀彂: 寮圭獥鏄剧ず鑲＄エ璇︽儏 - 绾跨▼瀹夊叏鐗堟湰
    #     """
    #     # 绾跨▼瀹夊叏:閬垮厤鍦ㄥ悗鍙扮嚎绋嬩腑璋冪敤 Tkinter
    #     try:
    #         if threading.current_thread() is threading.main_thread():
    #             self._show_alert_popup(code, name, msg)
    #         else:
    #             # 鍚庡彴绾跨▼:蹇界暐,閬垮厤 GIL 闂
    #             pass
    #     except Exception as e:
    #         # 闈欓粯澶辫触
    #         pass

    # def on_voice_speak_start(self, code):
    #     """璇煶寮€濮嬫挱鎶ユ椂鐨勫洖璋?(鍦ㄥ悗鍙扮嚎绋嬭皟鐢? - 绾跨▼瀹夊叏鐗堟湰"""
    #     if not code: 
    #         return
    #     # 浣跨敤绾跨▼瀹夊叏鐨勬柟寮忚皟搴﹀埌涓荤嚎绋?    #     try:
    #         # 妫€鏌ユ槸鍚﹀湪涓荤嚎绋?    #         if threading.current_thread() is threading.main_thread():
    #             self._trigger_alert_visual_effects(code, start=True)
    #         else:
    #             # 鍚庡彴绾跨▼:涓嶇洿鎺ヨ皟鐢?after,鑰屾槸閫氳繃浜嬩欢鏍囧織
    #             # 閬垮厤 GIL 闂,绠€鍗曞拷鐣ユ垨浣跨敤鍏朵粬鏈哄埗
    #             pass
    #     except Exception as e:
    #         # 闈欓粯澶辫触,閬垮厤宕╂簝
    #         pass

    # def on_voice_speak_end(self, code):
    #     """璇煶鎾姤缁撴潫鐨勫洖璋?- 绾跨▼瀹夊叏鐗堟湰"""
    #     if not code: 
    #         return
    #     try:
    #         if threading.current_thread() is threading.main_thread():
    #             self._trigger_alert_visual_effects(code, start=False)
    #         else:
    #             # 鍚庡彴绾跨▼:绠€鍗曞拷鐣?    #             pass
    #     except Exception as e:
    #         pass

    def on_voice_alert(self, code, name, msg):
        """
        澶勭悊璇煶鎶ヨ瑙﹀彂: 寮圭獥鏄剧ず鑲＄エ璇︽儏
        """
        # 蹇呴』鍥炲埌涓荤嚎绋嬫搷浣?GUI
        self.after(0, lambda: self._show_alert_popup(code, name, msg))

    def on_voice_speak_start(self, code):
        """璇煶鎾姤寮€濮嬬殑鍥炶皟"""
        if not code: return
        # 妫€鏌ョ▼搴忔槸鍚︽鍦ㄩ€€鍑?        if getattr(self, '_is_closing', False): return
        # 璋冨害鍒颁富绾跨▼鎵ц闂儊鍜岄渿鍔?        try:
            self.after(0, lambda: self._trigger_alert_visual_effects(code, start=True))
        except RuntimeError:
            pass  # 涓诲惊鐜凡鍋滄锛屽拷鐣?
    def on_voice_speak_end(self, code):
        """璇煶鎾姤缁撴潫鐨勫洖璋?""
        if not code: return
        # 妫€鏌ョ▼搴忔槸鍚︽鍦ㄩ€€鍑?        if getattr(self, '_is_closing', False): return
        try:
            self.after(0, lambda: self._trigger_alert_visual_effects(code, start=False))
        except RuntimeError:
            pass  # 涓诲惊鐜凡鍋滄锛屽拷鐣?

    def _trigger_alert_visual_effects(self, code, start=True):
        """鏍规嵁浠ｇ爜鏌ユ壘绐楀彛骞惰Е鍙戣瑙夋晥鏋?""
        if not hasattr(self, 'code_to_alert_win'): return
        win = self.code_to_alert_win.get(code)
        if win and win.winfo_exists():
            if start:
                if hasattr(win, 'start_visual_effects'):
                    win.start_visual_effects()
            else:
                if hasattr(win, 'stop_visual_effects'):
                    win.stop_visual_effects()

    def _update_alert_positions(self):
        """
        閲嶆柊鎺掑垪鎵€鏈夋姤璀﹀脊绐椼€?        浼樺寲鐐癸細浣跨敤 update_idletasks 纭繚鎵€鏈夌獥鍙ｄ綅缃悓鏃跺埛鏂帮紝鍑忓皯鍒濆鍖栨椂鐨勮瑙夐棯鐑併€?        淇敼鐐癸細宸叉斁澶х殑绐楀彛锛坃is_enlarged锛夎劚绂昏嚜鍔ㄧ綉鏍煎竷灞€锛屼繚鐣欑敤鎴锋嫋鎷藉悗鐨勪綅缃€?        """
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
            
        # 瀹氫箟鍥哄畾鐨勭獥鍙ｅ昂瀵稿拰杈硅窛
        alert_width, alert_height = 400, 180 
        margin = 10
        taskbar_height = 100 # 閬垮紑浠诲姟鏍忛珮搴?        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # 鏍规嵁灞忓箷瀹藉害璁＄畻鏈€澶у垪鏁?        max_cols = (screen_width - margin) // (alert_width + margin)
        if max_cols < 1: 
            max_cols = 1
        
        # 娓呯悊宸查攢姣佺殑绐楀彛
        self.active_alerts = [win for win in self.active_alerts if win.winfo_exists()]

        # 闄愬埗鏈€澶ц鏁颁互閬垮厤瓒呭嚭灞忓箷鑼冨洿
        max_rows = (screen_height - taskbar_height - margin) // (alert_height + margin)
        
        # --- 鍒嗙鍙楁帶绐楀彛鍜岃劚绂荤獥鍙?---
        managed_alerts = []
        detached_alerts = []
        for win in self.active_alerts:
            # 濡傛灉绐楀彛澶勪簬鈥滄斁澶р€濈姸鎬侊紝瑙嗕负鑴辩缃戞牸绠℃帶
            if getattr(win, '_is_enlarged', False):
                detached_alerts.append(win)
            else:
                managed_alerts.append(win)
        
        # 1. 甯冨眬鍙楁帶鐨勬櫘閫氱獥鍙?        for i, win in enumerate(managed_alerts):
            if i >= max_cols * max_rows:
                # 瓒呭嚭鏄剧ず鍖哄煙锛岄殣钘忕獥鍙?                try:
                    # 鍙湁褰撶獥鍙ｅ綋鍓嶅浜庢樉绀虹姸鎬佹椂鎵嶈皟鐢?withdraw()
                    if win.winfo_ismapped(): 
                         win.withdraw() 
                except Exception as e:
                    logger.error(f"鏃犳硶闅愯棌瓒呭嚭鑼冨洿鐨勭獥鍙? {e}")
                continue
            
            try:
                col = i % max_cols
                row = i // max_cols
                
                # 浠庡彸鍚戝乏鎺掑垪
                x = screen_width - (col + 1) * (alert_width + margin)
                y = screen_height - taskbar_height - (row + 1) * (alert_height + margin)
                
                # 浣跨敤榛樿灏哄
                current_width = alert_width
                current_height = alert_height
                
                win.geometry(f"{current_width}x{current_height}+{x}+{y}")
                # 纭繚绐楀彛鏄彲瑙佺殑锛堝鏋滀箣鍓嶈闅愯棌浜嗭級
                if not win.winfo_ismapped():
                    win.deiconify() 
            except Exception as e:
                logger.error(f"璋冩暣绱㈠紩 {i} 鐨勮鎶ョ獥鍙ｄ綅缃椂鍑洪敊: {e}")

        # 2. 澶勭悊鑴辩鐨勭獥鍙?(浠呯‘淇濆彲瑙佸拰淇濇寔灏哄鐘舵€侊紝涓嶉噸缃綅缃?
        for win in detached_alerts:
            try:
                # 纭繚鍙
                if not win.winfo_ismapped():
                    win.deiconify()
                # 浣嶇疆鍜屽昂瀵哥敱鐢ㄦ埛鎺у埗锛屾垨鑰呯敱 toggle_size 閫昏緫鎺у埗锛屾澶勪笉骞叉秹
            except Exception as e:
                 logger.error(f"Check detached window error: {e}")

        # *** 灞傚彔鏁堟灉浼樺寲 ***
        # 鏋侀檺浼樺寲锛氱Щ闄?update_idletasks()銆?        # 鍘熸湰鏄负浜嗙珛鍗冲埛鏂颁綅缃伩鍏嶈瑙夐棯鐑侊紝浣嗗湪澶ч噺寮圭獥鏃朵細瀵艰嚧 UI 绾跨▼涓ラ噸鍗￠】銆?        # Tkinter 浜嬩欢寰幆浼氳嚜鍔ㄥ鐞?geometry 鍙樻洿锛屾棤闇€寮哄埗鍚屾銆?        # self.update_idletasks()

    def _shake_window(self, win, distance=8, interval_ms=60):
        """
        闇囧姩绐楀彛鏁堟灉 - 鎸佺画闇囧姩鐩村埌 win.is_shaking 鍙樹负 False
        :param win: 瑕侀渿鍔ㄧ殑 Tkinter 绐楀彛瀹炰緥
        :param distance: 姣忔鏅冨姩鐨勬渶澶у儚绱犺窛绂?        :param interval_ms: 涓ゆ鏅冨姩涔嬮棿鐨勫欢杩熸绉掓暟 (瓒婂ぇ瓒婃俯鍜?鎱?
        """
        if not win or not win.winfo_exists():
            return
        
        # 鏍囪姝ｅ湪闇囧姩
        win.is_shaking = True
        
        # 鑾峰彇褰撳墠鍑犱綍淇℃伅锛堜笉浣跨敤 update_idletasks 閬垮厤闃诲锛?        # [淇] 蹇呴』纭繚绐楀彛鍑犱綍淇℃伅宸叉洿鏂帮紝鍚﹀垯 geometry() 杩斿洖 1x1 瀵艰嚧閿欎綅
        try:
            win.update_idletasks()
        except:
            pass

        def do_shake(orig_wh, orig_x, orig_y):
            # 妫€鏌ョ獥鍙ｆ槸鍚﹀瓨鍦ㄤ笖鏄惁搴旂户缁檭鍔?            if not win.winfo_exists() or not getattr(win, 'is_shaking', False):
                # 鍋滄鏅冨姩鏃讹紝灏濊瘯灏嗙獥鍙ｆ仮澶嶅埌鍘熷浣嶇疆锛堝鏋滃彲鑳斤級
                # 鍏抽敭淇锛氬鏋滅獥鍙ｅ凡琚弻鍑绘斁澶э紝鍒欑粷涓嶆仮澶嶅埌鏃х殑 orig_wh
                if win.winfo_exists() and not getattr(win, '_is_enlarged', False):
                     try:
                         win.geometry(f"{orig_wh}+{orig_x}+{orig_y}")
                     except: 
                         pass
                return
            
            # 璁＄畻闅忔満鍋忕Щ閲?            dx = random.randint(-distance, distance)
            dy = random.randint(-distance, distance)
            try:
                # 搴旂敤鏂扮殑浣嶇疆
                win.geometry(f"{orig_wh}+{orig_x + dx}+{orig_y + dy}")
            except: 
                pass
            
            # 瀹夋帓涓嬩竴娆℃檭鍔ㄣ€備娇鐢ㄦ柊鐨?interval_ms 鍙傛暟鎺у埗棰戠巼銆?            win.after(interval_ms, lambda: do_shake(orig_wh, orig_x, orig_y))

        # 鎹曡幏鍒濆浣嶇疆
        try:
            geom = win.geometry()
            parts = geom.split('+')
            if len(parts) == 3:
                wh = parts[0]
                x = int(parts[1])
                y = int(parts[2])
                do_shake(wh, x, y)
        except:
            # 濡傛灉鑾峰彇鍑犱綍淇℃伅澶辫触锛屽垯涓嶆墽琛屾檭鍔?            pass


    def close_all_alerts(self, is_manual=False):
        """
        涓€閿壒閲忓叧闂墍鏈?active alert 绐楀彛銆?        鏂板寮哄埗鍋滄褰撳墠鎵€鏈夎闊虫挱鎶ョ殑鑱斿姩銆?        """
        # 馃挜 鑱斿姩鏍稿績 1锛氬己鍒跺仠姝㈠綋鍓嶆鍦ㄦ挱鏀剧殑 *浠讳綍* 璇煶
        # 馃挜 鑱斿姩鏍稿績 1锛氬己鍒跺仠姝㈠綋鍓嶆鍦ㄦ挱鏀剧殑 *浠讳綍* 璇煶
        try:
            mgr = self._get_alert_manager()
            if mgr:
                mgr.stop_current_speech(key=None) # key=None 琛ㄧず鍏ㄥ眬纭仠姝?                # 馃挜 鑱斿姩鏍稿績 2锛氱珛鍗虫竻绌烘椿璺冨垪琛紝纭繚鍚庣画鎺掗槦鍏ㄩ儴璺宠繃
                mgr.sync_active_codes([]) 
        except:
            pass
        
        # 鎷疯礉鍒楄〃锛岄槻姝㈤亶鍘嗚繃绋嬩腑琚慨鏀?        active_windows = list(getattr(self, 'active_alerts', []))

        for win in active_windows:
            try:
                # 璋冪敤 _close_alert锛堝畠鍐呴儴浼氬鐞嗛噸澶嶅叧闂拰瀹夊叏閿€姣侊級
                self._close_alert(win, is_manual=is_manual)
            except Exception as e:
                log.error(f"Failed to close alert window {win}: {e}")
        toast_message(self, "宸插叧闂墍鏈夋姤璀︾獥鍙?)

    def _close_alert(self, win, is_manual=False):
        # 濡傛灉鏄嚜鍔ㄥ叧闂笖绐楀彛澶勪簬鏀惧ぇ鐘舵€侊紝鍒欏拷鐣ュ叧闂姹?        if not is_manual and getattr(win, '_is_enlarged', False):
            return

        if hasattr(self, 'active_alerts') and win in self.active_alerts:
            self.active_alerts.remove(win)

        # 闃叉閲嶅鍏抽棴
        if getattr(win, 'is_closing', False):
            return
        win.is_closing = True

        target_code = getattr(win, 'stock_code', None)
        
        # 灏濊瘯浠庢槧灏勮〃鏌ユ壘锛堢敤浜庢竻鐞嗭級
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

        # 浣跨敤 after_idle 纭繚 destroy 瀹屾垚涓斾簨浠跺惊鐜凡鏇存柊
        self.after_idle(self._update_alert_positions)

        if not target_code or not getattr(self, 'live_strategy', None):
            return

        # 鉁?[鏂板] 濡傛灉鏄凡缁忔樉寮忓垹闄ょ殑鐩戞帶锛屽垯涓嶅啀鎵ц鍚庣画鐨?snooze 绛夐€昏緫
        if getattr(win, '_is_deleted', False):
            logger.debug(f"Monitor for {target_code} was explicitly deleted, skipping snooze/cleanup.")
            return

        # 馃挜 鑱斿姩鏍稿績 1锛氬彧瑕佺獥鍙ｅ叧闂紝灏辫瘯寮哄埗鍋滄鎾姤銆?        # 濡傛灉鏄墜鍔ㄧ偣鍑?is_manual)锛屽垯鎵ц鍏ㄥ眬鍋滄 (key=None)锛屽交搴曟柀鏂０闊筹紱
        # 濡傛灉鏄嚜鍔ㄨ秴鏃跺叧闂紝鐢变簬鐢ㄦ埛鏈共棰勶紝浠呭皾璇曞仠姝㈠尮閰嶈浠ｇ爜鐨勬挱鎶ャ€?
        # 鍙栨秷 safety timer锛堝鏋滃凡缁忚Е鍙戯級
        if hasattr(win, 'safety_close_timer'):
            self.after_cancel(win.safety_close_timer)
            
        try:
            mgr = self._get_alert_manager()
            if mgr:
                mgr.stop_current_speech(key=None if is_manual else target_code)
            
            # 馃挜 鑱斿姩鏍稿績 2锛氬悓姝ユ渶鏂扮殑娲昏穬浠ｇ爜鍒楄〃锛岀‘淇濆悗缁帓闃熺殑璇ヤ唬鐮佸唴瀹硅璺宠繃
            self.after(10, self._update_voice_active_codes)
        except:
            pass

    def _update_voice_active_codes(self):
        """鍚屾褰撳墠灞忓箷涓婃墍鏈夋姤璀︾獥鍙ｇ殑鑲＄エ浠ｇ爜鍒拌闊崇鐞嗗櫒"""
        try:
            active_windows = list(getattr(self, 'active_alerts', []))
            valid_codes = []
            for w in active_windows:
                # # 鍙栨秷 safety timer锛堝鏋滃凡缁忚Е鍙戯級
                # if hasattr(w, 'safety_close_timer'):
                #     self.after_cancel(w.safety_close_timer)
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



    # def _close_alert_old(self, win, is_manual=False):
    #     """鍏抽棴寮圭獥骞跺埛鏂板竷灞€锛屽苟鍋滄鍏宠仈鐨勮闊虫姤璀︼紙鍐荤粨鍏嶇柅鐗堬級"""

    #     # =========================
    #     # 1锔忊儯 UI 鐘舵€佺珛鍗虫竻鐞嗭紙鍙仛鍐呭瓨鎿嶄綔锛?    #     # =========================
    #     if hasattr(self, 'active_alerts') and win in self.active_alerts:
    #         self.active_alerts.remove(win)

    #     target_code = None
    #     if hasattr(self, 'code_to_alert_win'):
    #         for c, w in list(self.code_to_alert_win.items()):
    #             if w is win:
    #                 target_code = c
    #                 del self.code_to_alert_win[c]
    #                 break

    #     # =========================
    #     # 2锔忊儯 绔嬪嵆閿€姣佺獥鍙ｏ紙涓嶇瓑寰呬换浣曠瓥鐣?/ 璇煶锛?    #     # =========================
    #     try:
    #         win.destroy()
    #     except Exception:
    #         pass

    #     # =========================
    #     # 3锔忊儯 寤惰繜 UI 閲嶆帓锛堝悓鍑芥暟鍐呭畬鎴愶級
    #     # =========================
    #     self.after(50, self._update_alert_positions)

    #     # =========================
    #     # 4锔忊儯 寤惰繜澶勭悊绛栫暐 / 璇煶锛堝叧閿級
    #     #    鈿狅笍 浠嶇劧鍦ㄦ湰鍑芥暟鍐咃紝涓嶆媶閫昏緫
    #     # =========================
    #     if not target_code or not getattr(self, 'live_strategy', None):
    #         return

    #     def _post_logic():
    #         # ---- 鎵嬪姩鍏抽棴锛氬彧鍋氬欢杩熷啀鎶?----
    #         if is_manual:
    #             try:
    #                 self.live_strategy.snooze_alert(
    #                     target_code,
    #                     cycles=pending_alert_cycles
    #                 )
    #             except Exception:
    #                 pass

    #         # ---- 鏃犺鎵嬪姩 / 鑷姩锛岄兘蹇呴』 cancel 褰撳墠璇煶 ----
    #         v = getattr(self.live_strategy, '_voice', None)
    #         if v and hasattr(v, 'cancel_for_code'):
    #             try:
    #                 v.cancel_for_code(target_code)
    #             except Exception:
    #                 pass

    #     # 鈿狅笍 鏍稿績锛氶€昏緫浠嶅湪 _close_alert锛屼絾涓嶉樆濉?Tk
    #     self.after(10, _post_logic)


    # def _close_alert_old(self, win, is_manual=False):
    #     """鍏抽棴寮圭獥骞跺埛鏂板竷灞€锛屽苟鍋滄鍏宠仈鐨勮闊虫姤璀?""
    #        #鍋跺彂鍏抽棴鏃秛i鍏ㄩ儴鍗℃
    #     # ===== [淇敼鐐?1] =====
    #     # 鍏抽棴鏃讹紝绔嬪嵆浠?active_alerts 绉婚櫎锛堥伩鍏嶅悗缁竷灞€鍜屽紩鐢ㄩ敊璇級
    #     if hasattr(self, 'active_alerts') and win in self.active_alerts:
    #         self.active_alerts.remove(win)

    #     # ===== [淇敼鐐?2] =====
    #     # 缁熶竴鍦ㄨ繖閲屾竻鐞?code -> window 鏄犲皠锛屽苟鑾峰彇 target_code
    #     target_code = None
    #     if hasattr(self, 'code_to_alert_win'):
    #         for c, w in list(self.code_to_alert_win.items()):
    #             if w is win:
    #                 target_code = c
    #                 del self.code_to_alert_win[c]
    #                 break

    #     # ===== [淇敼鐐?3] =====
    #     # 璇煶 / 绛栫暐澶勭悊閫昏緫缁熶竴鏀惧湪涓€涓潡涓紝閬垮厤鍒嗘敮閬楁紡
    #     if target_code and getattr(self, 'live_strategy', None):

    #         # ===== [淇敼鐐?3.1] =====
    #         # 鎵嬪姩鍏抽棴锛氬彧璐熻矗鈥滃欢杩熷啀鎶モ€濓紝涓嶈礋璐ｅ仠褰撳墠璇煶
    #         if is_manual:
    #             self.live_strategy.snooze_alert(
    #                 target_code,
    #                 cycles=pending_alert_cycles
    #             )

    #         # ===== [淇敼鐐?3.2 - 鍏抽敭淇鐐筣 =====
    #         # 鏃犺鎵嬪姩 / 鑷姩鍏抽棴锛岄兘蹇呴』绔嬪嵆 cancel 褰撳墠璇煶
    #         # 锛堣繖鏄?new 鐗堟湰鍑洪棶棰樼殑鏍瑰洜锛?    #         v = getattr(self.live_strategy, '_voice', None)
    #         if v and hasattr(v, 'cancel_for_code'):
    #             v.cancel_for_code(target_code)

    #     # ===== [淇敼鐐?4] =====
    #     # 鍦ㄦ墍鏈夌姸鎬佹竻鐞嗗畬鎴愬悗锛屽啀閿€姣佺獥鍙?    #     win.destroy()

    #     # ===== [淇敼鐐?5] =====
    #     # 绔嬪嵆閲嶆帓寮圭獥浣嶇疆锛堜笉浣跨敤 after锛岄伩鍏嶉『搴忛敊涔憋級
    #     self._update_alert_positions()



    def _show_alert_popup(self, code, name, msg):
        """鏄剧ず鎶ヨ寮圭獥 (闃熷垪鍖栭€愪釜鍒涘缓 + 鍚岃偂鍘婚噸)"""
        # ===== 鍒濆鍖栧脊绐楅槦鍒?=====
        if not hasattr(self, '_alert_queue'):
            self._alert_queue = []
            self._alert_queue_processing = False
        
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
        if not hasattr(self, 'code_to_alert_win'):
            self.code_to_alert_win = {}
        
        # ===== 鍚岃偂鍘婚噸锛氬鏋滃凡鏈夊脊绐楋紝鏇存柊娑堟伅鑰岄潪鏂板缓 =====
        existing_win = self.code_to_alert_win.get(code)
        if existing_win:
            try:
                if existing_win.winfo_exists():
                    existing_win.title(f"馃敂 瑙﹀彂鎶ヨ - {name} ({code})")
                    if hasattr(existing_win, 'msg_label'):
                        existing_win.msg_label.config(text=f"鈿狅笍{code} {msg}")
                    existing_win.lift()
                    existing_win.attributes("-topmost", True)
                    if hasattr(existing_win, 'start_visual_effects'):
                        existing_win.start_visual_effects()
                    logger.debug(f"澶嶇敤宸叉湁寮圭獥: {code}")
                    return
            except tk.TclError:
                logger.debug(f"妫€娴嬪埌宸查攢姣佸脊绐楋紝娓呯悊鏄犲皠: {code}")
            except Exception as e:
                logger.debug(f"鏇存柊宸叉湁寮圭獥澶辫触: {e}")
            
            if code in self.code_to_alert_win:
                del self.code_to_alert_win[code]
        
        # ===== 鍔犲叆闃熷垪锛岄伩鍏嶅悓鏃跺垱寤哄ぇ閲忕獥鍙?=====
        # 妫€鏌ラ槦鍒椾腑鏄惁宸叉湁鍚岃偂璇锋眰
        for item in self._alert_queue:
            if item[0] == code:
                # 鏇存柊闃熷垪涓殑娑堟伅
                item[1] = name
                item[2] = msg
                logger.debug(f"闃熷垪涓凡鏈夊悓鑲¤姹傦紝鏇存柊娑堟伅: {code}")
                return
        
        self._alert_queue.append([code, name, msg])
        logger.debug(f"寮圭獥璇锋眰鍔犲叆闃熷垪: {code}, 闃熷垪闀垮害: {len(self._alert_queue)}")
        
        # 鍚姩闃熷垪澶勭悊锛堝鏋滄湭杩愯锛?        if not self._alert_queue_processing:
            self._process_alert_queue()
    
    def _process_alert_queue(self):
        """澶勭悊寮圭獥闃熷垪锛岄€愪釜鍒涘缓绐楀彛锛堝眰鍙犳晥鏋?+ 鍙搷浣滐級"""
        if not hasattr(self, '_alert_queue') or not self._alert_queue:
            self._alert_queue_processing = False
            return
        
        self._alert_queue_processing = True
        
        try:
            # 鍙栧嚭涓€涓姹?            item = self._alert_queue.pop(0)
            code, name, msg = item
            
            # 鍒涘缓杩欎釜寮圭獥
            self._create_single_alert_popup(code, name, msg)
            
            # logger.debug(f"宸插鐞嗕竴涓脊绐楋紝鍓╀綑闃熷垪: {len(self._alert_queue)}")
            
        except Exception as e:
            logger.error(f"澶勭悊寮圭獥闃熷垪寮傚父: {e}")
        finally:
            # 鏋侀檺浼樺寲锛氱缉鐭鐞嗛棿闅旓紝浠?100ms -> 16ms (绾?0fps)锛屽姞蹇脊鍑洪€熷害浣嗕繚鐣?event loop 鍛煎惛绌洪棿
            # [鍥炴粴] 鐢ㄦ埛鍙嶉澶揩瀵艰嚧鈥滃钩閾衡€濇劅锛屾仮澶嶅埌 100ms 浠ヤ繚鎸佲€滃眰绾р€濆脊鍑烘劅
            if self._alert_queue:
                self.after(100, self._process_alert_queue)
            else:
                self._alert_queue_processing = False

    def _get_alert_manager(self):
        """鑾峰彇缂撳瓨鐨?AlertManager 瀹炰緥锛岄伩鍏嶉噸澶嶅鍏ュ拰瀹炰緥鍖?""
        if not hasattr(self, '_cached_alert_manager'):
            try:
                self._cached_alert_manager = get_alert_manager()
            except ImportError:
                self._cached_alert_manager = None
        return self._cached_alert_manager
    
    def _create_single_alert_popup(self, code, name, msg):
        """瀹為檯鍒涘缓鍗曚釜寮圭獥锛堜粠闃熷垪璋冪敤锛?""
        try:
            # 鍐嶆妫€鏌ユ槸鍚﹀凡鏈夊脊绐楋紙鍙兘鍦ㄩ槦鍒楃瓑寰呮湡闂村凡鍒涘缓锛?            existing_win = self.code_to_alert_win.get(code)
            if existing_win:
                try:
                    if existing_win.winfo_exists():
                        existing_win.title(f"馃敂 瑙﹀彂鎶ヨ - {name} ({code})")
                        if hasattr(existing_win, 'msg_label'):
                            existing_win.msg_label.config(text=f"鈿狅笍{code} {msg}")
                        existing_win.lift()
                        return
                except:
                    pass
                if code in self.code_to_alert_win:
                    del self.code_to_alert_win[code]
            
            # ===== 鐩存帴鍒涘缓瀹屾暣寮圭獥锛堥槦鍒楁帶鍒堕€熷害锛屾棤闇€鍒嗘锛?=====
            win = tk.Toplevel(self)
            win.overrideredirect(True)  # 绉婚櫎绯荤粺鏍囬鏍忥紝浣跨敤鑷畾涔夋爣棰樻爮
            win.attributes("-topmost", True)
            win.geometry("400x180")
            win.configure(bg="#fff")
            win.stock_code = code # 猸?鍏抽敭锛氬皢浠ｇ爜缁戝畾鍒扮獥鍙ｏ紝纭繚閿€姣佹椂鑳界簿鍑嗘壘鍒?            
            # 妫€娴嬫槸鍚︿负楂樹紭鍏堢骇淇″彿锛堟秷鎭腑鍖呭惈 [HIGH]锛?            win.is_high_priority = "[HIGH]" in msg or "楂樹紭鍏堢骇" in msg
            
            # 璁板綍骞跺畾浣嶏紙鐩存帴璋冪敤锛屼繚鎸佸眰鍙犳晥鏋滐級
            self.active_alerts.append(win)
            self._update_alert_positions()
            
            # 猸?鑱斿姩澧炲己锛氭洿鏂版椿璺冨垪琛?            self.after(10, self._update_voice_active_codes)
            
            # 鍏抽棴鍥炶皟
            win.protocol("WM_DELETE_WINDOW", lambda: self._close_alert(win, is_manual=True))
            
            # 鏄犲皠璁板綍
            if not hasattr(self, 'code_to_alert_win'):
                self.code_to_alert_win = {}
            self.code_to_alert_win[code] = win
            
            # 鑾峰彇 category content
            category_content = "鏆傛棤璇︾粏淇℃伅"
            if code in self.df_all.index:
                category_content = self.df_all.loc[code].get('category', '')
            
            # 鑷姩鍏抽棴閫昏緫
            has_voice = False
            try:
                if hasattr(self, 'live_strategy') and self.live_strategy:
                    if not getattr(self.live_strategy, 'voice_enabled', True):
                        has_voice = False
                    else:
                        try:
                            # 浼樺寲锛氫娇鐢ㄧ紦瀛樼殑 manager锛屼笖閬垮厤 process.is_alive() 绛夊彲鑳借€楁椂鐨勬鏌?                            mgr = self._get_alert_manager()
                            if mgr and mgr.voice_enabled:
                                # 绠€鍖栨鏌ワ紝鍙湅闃熷垪闀垮害锛岄伩鍏嶆繁鍏?process 鐘舵€?                                q_size = mgr.voice_queue.qsize() if hasattr(mgr, 'voice_queue') else 0
                                if q_size < 30:
                                    has_voice = True
                        except:
                            has_voice = False
            except Exception as e:
                logger.debug(f"voice detect failed: {e}")
            
            def _get_alert_close_delay_ms():
                seconds = max(60, int(alert_cooldown / 2))
                return seconds * 1000
            
            delay_ms = _get_alert_close_delay_ms()
            if not has_voice:
                self.after(delay_ms, lambda: self._close_alert(win))
            else:
                win.safety_close_timer = self.after(180000, lambda: self._close_alert(win))
            
            # 闂儊鏁堟灉
            def flash(count=0):
                if not win.winfo_exists() or not getattr(win, 'is_flashing', False):
                    if win.winfo_exists(): win.configure(bg="#fff")
                    return
                bg = "#ffcdd2" if count % 2 == 0 else "#ffebee"
                win.configure(bg=bg)
                win.after(500, lambda: flash(count+1))
            
            def start_effects():
                if getattr(win, 'is_flashing', False): return
                win.is_flashing = True
                flash()
                # 楂樹紭鍏堢骇淇″彿瑙﹀彂闇囧姩鏁堟灉
                if getattr(win, 'is_high_priority', False):
                    self._shake_window(win, distance=5, interval_ms=150)
            
            def stop_effects():
                win.is_flashing = False
                win.is_shaking = False
                if hasattr(win, 'safety_close_timer'):
                    try: self.after_cancel(win.safety_close_timer)
                    except: pass
                
                # 鍙湁鍦ㄦ湭鏀惧ぇ鐘舵€佷笅锛屾墠瀹夋帓鑷姩鍏抽棴
                if not getattr(win, '_is_enlarged', False):
                    self.after(int(alert_cooldown/2)*1000, lambda: self._close_alert(win))
            
            win.start_visual_effects = start_effects
            win.stop_visual_effects = stop_effects
            win.is_flashing = False
            win.is_shaking = False
            
            # ===== 鍙屽嚮鏀惧ぇ/缂╁皬鍔熻兘 =====
            # 鍘熷灏哄
            win._orig_width = 400
            win._orig_height = 180
            win._is_enlarged = False
            
            def toggle_size(event=None):
                """鍙屽嚮鍒囨崲绐楀彛澶у皬锛氭斁澶?鍊?/ 缂╁皬鍥炲師澶у皬"""
                if not win.winfo_exists():
                    return
                
                # 闃叉姈鍔ㄥ鐞嗭細闃叉鐭椂闂村唴閲嶅瑙﹀彂锛堜緥濡備簨浠跺啋娉℃垨鑰呯敤鎴锋墜鎶栵級
                current_time = time.time()
                last_time = getattr(win, 'last_toggle_time', 0)
                if current_time - last_time < 0.8:  # 800ms 鍐峰嵈鏃堕棿
                    return "break"
                win.last_toggle_time = current_time

                
                if win._is_enlarged:
                    # 缂╁皬鍥炲師澶у皬
                    new_w = win._orig_width
                    new_h = win._orig_height
                    win._is_enlarged = False
                    
                    # 缂╁皬鍚庢仮澶嶈嚜鍔ㄥ叧闂鏃?(閲嶆柊寮€濮嬪€掕鏃?
                    if not has_voice:
                        win.safety_close_timer = self.after(delay_ms, lambda: self._close_alert(win))
                    else:
                        win.safety_close_timer = self.after(180000, lambda: self._close_alert(win))
                else:
                    # 鏀惧ぇ2鍊?                    new_w = win._orig_width * 2
                    new_h = win._orig_height * 2
                    win._is_enlarged = True
                    
                    # 鏀惧ぇ鏃讹細鍋滄闇囧姩锛屾殏鍋滆嚜鍔ㄥ叧闂?                    win.is_shaking = False
                    if hasattr(win, 'safety_close_timer'):
                        try: self.after_cancel(win.safety_close_timer)
                        except: pass
                
                # 鑾峰彇褰撳墠浣嶇疆锛屼繚鎸佺獥鍙ｄ腑蹇冧笉鍙?                try:
                    curr_x = win.winfo_x()
                    curr_y = win.winfo_y()
                    curr_w = win.winfo_width()
                    curr_h = win.winfo_height()
                    
                    # 璁＄畻鏂颁綅缃紝浣跨獥鍙ｄ腑蹇冧繚鎸佷笉鍙?                    new_x = curr_x + (curr_w - new_w) // 2
                    new_y = curr_y + (curr_h - new_h) // 2
                    
                    # 纭繚涓嶈秴鍑哄睆骞曡竟鐣?                    screen_w = win.winfo_screenwidth()
                    screen_h = win.winfo_screenheight()
                    new_x = max(0, min(new_x, screen_w - new_w))
                    new_y = max(0, min(new_y, screen_h - new_h - 50))  # 50 涓轰换鍔℃爮
                    
                    win.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
                except Exception as e:
                    logger.debug(f"Toggle size error: {e}")
                    win.geometry(f"{new_w}x{new_h}")
                
                # 闃绘浜嬩欢鍐掓场锛岄槻姝?Label 鍜?Frame 閲嶅瑙﹀彂
                return "break"
            
            win.toggle_size = toggle_size
            
            # 缁戝畾鏍囬鏍忓弻鍑讳簨浠讹紙浣跨敤椤堕儴妯℃嫙鏍囬鏍忥級
            title_bar = tk.Frame(win, bg="#e57373", height=32, cursor="hand2")
            title_bar.pack(fill="x", side="top")
            title_bar.pack_propagate(False)
            
            def stop_shake(event=None):
                """榧犳爣鎮仠鍋滄闇囧姩锛屾柟渚跨瀯鍑嗚繘琛屽弻鍑?""
                # 寮哄埗鍋滄闇囧姩
                win.is_shaking = False
            
            title_label = tk.Label(
                title_bar, 
                text=f"馃敂 {name} ({code})", 
                bg="#e57373", 
                fg="white",
                font=("Microsoft YaHei", 10, "bold"),
                anchor="w",
                padx=8
            )
            title_label.pack(side="left", fill="x", expand=True)
            
            title_bar.bind("<Double-Button-1>", toggle_size)
            title_label.bind("<Double-Button-1>", toggle_size)
            
            # 浣跨敤榧犳爣鎮仠鍋滄闇囧姩 (瑙ｅ喅鍗曞嚮姝т箟)
            title_bar.bind("<Enter>", stop_shake)
            title_label.bind("<Enter>", stop_shake)
            
            # 鏁村悎鍗曞嚮鍜屾嫋鎷藉紑濮嬮€昏緫
            def on_click_start(event):
                # 1. 鍋滄闇囧姩 (宸叉敼涓?Hover 瑙﹀彂)
                # stop_shake() 
                # 2. 璁板綍鎷栨嫿璧峰鍧愭爣
                win.x = event.x
                win.y = event.y
                return "break"
            
            def do_move(event):
                if not hasattr(win, 'x'): return
                deltax = event.x - win.x
                deltay = event.y - win.y
                x = win.winfo_x() + deltax
                y = win.winfo_y() + deltay
                win.geometry(f"+{x}+{y}")
                return "break"
            
            # 浣跨敤 Button-1 缁熶竴鍝嶅簲鐐瑰嚮鍜屾嫋鎷藉紑濮?            title_bar.bind("<Button-1>", on_click_start)
            title_label.bind("<Button-1>", on_click_start)
            title_bar.bind("<B1-Motion>", do_move)
            title_label.bind("<B1-Motion>", do_move)
            
            # 鍏抽棴鎸夐挳锛堝湪鏍囬鏍忓彸渚э級
            close_btn = tk.Label(
                title_bar,
                text="鉁?,
                bg="#e57373",
                fg="white",
                font=("Arial", 12, "bold"),
                cursor="hand2",
                padx=8
            )
            close_btn.pack(side="right")
            close_btn.bind("<Button-1>", lambda e: self._close_alert(win, is_manual=True))
            close_btn.bind("<Enter>", lambda e: close_btn.configure(bg="#c62828"))
            close_btn.bind("<Leave>", lambda e: close_btn.configure(bg="#e57373"))
            
            # 鍙屽嚮鏍囬鏍忓垏鎹㈠ぇ灏?            title_bar.bind("<Double-Button-1>", toggle_size)
            title_label.bind("<Double-Button-1>", toggle_size)
            
            # 鏀寔鎷栧姩绐楀彛
            def start_drag(event):
                win._drag_start_x = event.x
                win._drag_start_y = event.y
            
            def do_drag(event):
                if hasattr(win, '_drag_start_x'):
                    x = win.winfo_x() + (event.x - win._drag_start_x)
                    y = win.winfo_y() + (event.y - win._drag_start_y)
                    win.geometry(f"+{x}+{y}")
            
            title_bar.bind("<Button-1>", start_drag)
            title_bar.bind("<B1-Motion>", do_drag)
            title_label.bind("<Button-1>", start_drag)
            title_label.bind("<B1-Motion>", do_drag)
            
            # 鍐呭妗嗘灦锛堝噺灏弍adding锛屼俊鎭洿绱у噾锛?            frame = tk.Frame(win, bg="#fff", padx=8, pady=5)
            frame.pack(fill="both", expand=True)
            
            # 鎸夐挳鍖?            def delete_monitor():
                if hasattr(self, 'live_strategy'):
                    try:
                        self.live_strategy.remove_monitor(code)
                        logger.info(f"Deleted alarm rule for {code}")
                        
                        # 馃挜 鍚屾鍋滄褰撳墠璇煶鎾姤
                        try:
                            mgr = self._get_alert_manager()
                            if mgr: mgr.stop_current_speech()
                        except:
                            pass

                        btn_del.config(text="馃棏锔忓凡鍒犻櫎", state="disabled")
                        # 鉁?[鏂板] 鏍囪涓哄凡鍒犻櫎锛岄槻姝?_close_alert 涓殑 snooze 閫昏緫鐢熸晥
                        win._is_deleted = True 
                        win.after(1000, lambda: self._close_alert(win, is_manual=True))
                    except Exception as e:
                        logger.error(f"Remove monitor error: {e}")
            
            def send_to_tdx():
                if hasattr(self, 'sender'):
                    try:
                        self.sender.send(code)
                        btn_send.config(text="鉁?宸插彂閫?, bg="#ccff90")
                        if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                            self.open_visualizer(code)
                    except Exception as e:
                        logger.error(f"Send stock error: {e}")
            
            btn_frame = tk.Frame(frame, bg="#fff")
            btn_frame.pack(side="bottom", fill="x", pady=5)
            
            btn_send = tk.Button(btn_frame, text="馃殌鍙戦€?, command=send_to_tdx, bg="#e0f7fa", font=("Arial", 10, "bold"), cursor="hand2")
            btn_send.pack(side="left", fill="x", expand=True, padx=5)
            
            btn_del = tk.Button(btn_frame, text="Del", command=delete_monitor, bg="#ffcdd2", cursor="hand2", font=("Arial", 8), width=3)
            btn_del.pack(side="left", padx=2)
            
            tk.Button(btn_frame, text="鍏抽棴", command=lambda: self._close_alert(win, is_manual=True), bg="#eee", width=8, pady=2).pack(side="right", padx=5)
            
            # 娑堟伅鏍囩锛堢Щ闄ら噸澶嶇殑鑲＄エ浠ｇ爜锛屾爣棰樻爮宸叉湁锛?            msg_label = tk.Label(frame, text=f"鈿狅笍 {msg}", font=("Microsoft YaHei", 11, "bold"), fg="#d32f2f", bg="#fff", wraplength=380, anchor="w", justify="left")
            msg_label.pack(fill="x", pady=2)
            win.msg_label = msg_label
            
            # 璇︽儏鏂囨湰
            text_box = tk.Text(frame, height=4, font=("Arial", 10), bg="#f5f5f5", relief="flat")
            text_box.pack(fill="both", expand=True, pady=5)
            text_box.insert("1.0", category_content)
            text_box.config(state="disabled")
            
            # 寮傛鍚姩瑙嗚鏁堟灉锛堜笉闃诲浜嬩欢寰幆锛?            # [淇] 鍏堝己鍒跺埛鏂拌绐楀彛(闈炲叏灞€)鐨?geometry锛岀‘淇?start_visual_effects 鑳借鍒版纭綅缃?            self.after(20, lambda: (win.update_idletasks() if win.winfo_exists() else None, win.start_visual_effects()))
            
        except Exception as e:
            logger.error(f"Show alert popup error: {e}")


    def open_trade_report_window(self):
        """鎵撳紑涔板崠浜ゆ槗鐩堝埄璁＄畻鏌ョ湅瑙嗗浘"""
        t_logger = TradingLogger()
        
        report_win = tk.Toplevel(self)
        report_win.title("涔板崠浜ゆ槗鐩堜簭缁熻鎶ヨ〃")
        window_id = "浜ゆ槗鐩堜簭缁熻鎶ヨ〃"
        self.load_window_position(report_win, window_id, default_width=900, default_height=650)
        report_win.focus_force()

        # --- 鎺掑簭鐘舵€?---
        self._trade_sort_col = None
        self._trade_sort_reverse = False

        # --- 鎺掑簭鍑芥暟 ---
        def sort_treeview_column(tv, col, reverse=False):
            l = [(tv.set(k, col), k) for k in tv.get_children('')]
            try:
                # 灏濊瘯鏁板€兼帓搴?                l.sort(key=lambda x: float(x[0]) if x[0] not in ("--","") else float('-inf'), reverse=reverse)
            except:
                # 鏂囨湰鎺掑簭
                l.sort(reverse=reverse)
            for index, (val, k) in enumerate(l):
                tv.move(k, '', index)
            # 淇濆瓨褰撳墠鎺掑簭鐘舵€?            self._trade_sort_col = col
            self._trade_sort_reverse = reverse

        # --- 鍔犺浇鏁版嵁 ---
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
                messagebox.showerror("閿欒", "鏃ユ湡鏍煎紡涓嶆纭紝璇蜂娇鐢?YYYY-MM-DD")
                return

            results = t_logger.get_summary()
            profit = results[0] if results and results[0] is not None else 0
            avg_pct = (results[1] if results and results[1] is not None else 0) * 100
            count = results[2] if results and results[2] is not None else 0
            summary_label.config(text=f"绱鍑€鍒╂鼎: {profit:,.2f} | 骞冲潎鏀剁泭鐜? {avg_pct:.2f}% | 鎬诲钩浠撶瑪鏁? {count}")
            
            load_stats()
            load_details(s_date, e_date)

            # 淇濇寔涓婁竴娆℃帓搴?            if self._trade_sort_col:
                sort_treeview_column(tree, self._trade_sort_col, self._trade_sort_reverse)

        # --- 鍒犻櫎璁板綍 ---
        def delete_selected_trade(event=None):
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("鎻愰啋", "璇峰厛閫夋嫨瑕佸垹闄ょ殑璁板綍")
                return

            item_id = selected[0]
            item = tree.item(item_id)
            trade_id = item['values'][0]
            stock_name = item['values'][2]

            # 鍒犻櫎鍓嶈幏鍙栧綋鍓嶈绱㈠紩
            children = tree.get_children()
            idx = children.index(item_id)
            # 涓嬩竴琛岀储寮?            next_idx = idx if idx < len(children) - 1 else idx - 1

            if not messagebox.askyesno(
                "纭鍒犻櫎",
                f"纭畾瑕佹案涔呭垹闄?[{stock_name}] (ID:{trade_id}) 鐨勮繖绗斾氦鏄撹褰曞悧锛?
            ):
                return

            try:
                if t_logger.delete_trade(trade_id):
                    toast_message(self, "鎴愬姛锛岃褰曞凡浠庢暟鎹簱鐗╃悊鍒犻櫎")
                    
                    # 鍒锋柊鏁版嵁
                    refresh_summary()

                    # 鍒锋柊鍚庨噸鏂拌幏鍙栬
                    new_children = tree.get_children()
                    if new_children:
                        new_idx = max(0, min(next_idx, len(new_children) - 1))
                        tree.selection_set(new_children[new_idx])
                        tree.focus(new_children[new_idx])
                        tree.see(new_children[new_idx])

                    report_win.lift()
                    report_win.focus_force()
                    tree.focus_set()  # 淇濊瘉閿洏鐒︾偣鍦?Treeview

                else:
                    messagebox.showerror("閿欒", "鍒犻櫎澶辫触")

            except Exception as e:
                logger.error(f"delete trade error: {e}")
                messagebox.showerror("閿欒", f"鍒犻櫎寮傚父: {e}")

        # def on_trade_report_double_click(event):
        #         item = tree.selection()
        #         if not item: return
        #         values = tree.item(item[0], "values")
        #         # (code, name, rule_type, value, add_time, tags, id)
        #         tags_info = values[5]
        #         if tags_info:
        #              # 寮圭獥鏄剧ず瀹屾暣淇℃伅
        #              top = tk.Toplevel(win)
        #              top.title(f"{values[1]}:{values[0]} 璇︽儏")
        #              top.geometry("600x400")
        #              # 灞呬腑鏄剧ず鐨勭畝鍗曢€昏緫
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
        # --- 缂栬緫浜ゆ槗 ---
        def edit_selected_trade():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("鎻愰啋", "璇峰厛閫夋嫨瑕佺紪杈戠殑璁板綍")
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
            edit_win.title(f"缂栬緫浜ゆ槗 - {stock_name}")
            window_id_edit = "缂栬緫浜ゆ槗璁板綍"
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

            tk.Label(frm, text=f"浜ゆ槗 ID: {trade_id}", font=("Arial", 9, "bold")).pack(pady=5)
            tk.Label(frm, text="涔板叆浠锋牸:").pack(pady=(10,0))
            bp_var = tk.DoubleVar(value=buy_p)
            tk.Entry(frm, textvariable=bp_var).pack(fill="x")
            tk.Label(frm, text="寤鸿鎴愪氦閲?(鑲?:").pack(pady=(10,0))
            ba_var = tk.IntVar(value=buy_a)
            tk.Entry(frm, textvariable=ba_var).pack(fill="x")
            
            sp_var = None
            if sell_p is not None:
                tk.Label(frm, text="鍗栧嚭浠锋牸:").pack(pady=(10,0))
                sp_var = tk.DoubleVar(value=sell_p)
                tk.Entry(frm, textvariable=sp_var).pack(fill="x")
            
            def save_edit():
                try:
                    new_bp = bp_var.get()
                    new_ba = ba_var.get()
                    new_sp = sp_var.get() if sp_var else None
                    if t_logger.manual_update_trade(trade_id, new_bp, new_ba, new_sp):
                        messagebox.showinfo("鎴愬姛", "淇敼宸蹭繚瀛橈紝绯荤粺宸茶嚜鍔ㄩ噸绠楀噣鍒╂鼎涓庢敹鐩婄巼銆?)
                        on_close_edit()
                        refresh_summary()
                    else:
                        messagebox.showerror("閿欒", "鏁版嵁搴撴洿鏂板け璐?)
                except Exception as e:
                    messagebox.showerror("閿欒", f"杈撳叆鏃犳晥: {e}")

            tk.Button(frm, text="馃捑 淇濆瓨淇敼", command=save_edit, bg="#ccff90", font=("Arial", 10, "bold"), height=2).pack(pady=30, fill="x")

        # --- 娣诲姞鍙嶉 ---
        def add_feedback():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("鎻愰啋", "璇峰湪鏄庣粏涓€夋嫨涓€绗斾氦鏄撹繘琛屽弽棣?)
                return
            
            item = tree.item(selected[0])
            trade_id = item['values'][0]
            stock_name = item['values'][2]
            
            feedback = simpledialog.askstring("绛栫暐浼樺寲鍙嶉", f"閽堝 [{stock_name}] 鐨勪氦鏄擄紝璇峰憡鐭ョ瓥鐣ュ瓨鍦ㄧ殑闂鎴栨敼杩涘缓璁細")
            if feedback:
                if t_logger.update_trade_feedback(trade_id, feedback):
                    messagebox.showinfo("鎴愬姛", "鎰熻阿鍙嶉锛屽凡璁板綍銆?)
                    refresh_summary()
                else:
                    messagebox.showerror("閿欒", "鍙嶉淇濆瓨澶辫触")

        # --- UI 甯冨眬 ---
        # 椤堕儴缁熻
        header_frame = tk.Frame(report_win, relief="groove", borderwidth=1, padx=10, pady=10)
        header_frame.pack(side="top", fill="x")
        
        summary_label = tk.Label(header_frame, text="姝ｅ湪鍔犺浇缁熻鏁版嵁...", font=("Arial", 12, "bold"))
        summary_label.pack(side="left")

        filter_frame = tk.Frame(header_frame)
        filter_frame.pack(side="right")
        tk.Label(filter_frame, text="鏃ユ湡绛涢€?").pack(side="left", padx=5)
        start_var = tk.StringVar(value=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'))
        tk.Entry(filter_frame, textvariable=start_var, width=12).pack(side="left", padx=2)
        tk.Label(filter_frame, text="鑷?).pack(side="left")
        tk.Entry(filter_frame, textvariable=end_var, width=12).pack(side="left", padx=2)

        # 澶氭棩姹囨€?        stats_frame = tk.LabelFrame(report_win, text="澶氭棩鐩堜簭缁熻 (杩?0澶?", padx=5, pady=5)
        stats_frame.pack(side="top", fill="x", padx=10, pady=5)
        stats_tree = ttk.Treeview(stats_frame, columns=("day", "profit", "count"), show="headings", height=5)
        stats_tree.heading("day", text="鏃ユ湡")
        stats_tree.heading("profit", text="鍗曟棩鍒╂鼎")
        stats_tree.heading("count", text="鎴愪氦绗旀暟")
        stats_tree.column("day", width=150, anchor="center")
        stats_tree.column("profit", width=150, anchor="center")
        stats_tree.column("count", width=100, anchor="center")
        stats_tree.pack(fill="x")

        # 搴曢儴鎸夐挳
        btn_bar = tk.Frame(report_win, pady=10)
        btn_bar.pack(side="bottom", fill="x")
        tk.Button(btn_bar, text="鍒锋柊鏁版嵁", command=refresh_summary, width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="鉁忥笍 鎵嬪姩淇", command=edit_selected_trade, width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="馃棏锔?鍒犻櫎璁板綍", command=delete_selected_trade, fg="red", width=12).pack(side="left", padx=10)
        tk.Button(btn_bar, text="闂鍙嶉/浼樺寲绛栫暐", command=add_feedback, bg="#ffcccc", width=20).pack(side="right", padx=20)

        # 涓儴鏄庣粏鍒楄〃
        list_frame = tk.LabelFrame(report_win, text="浜ゆ槗鏄庣粏璁板綍", padx=5, pady=5)
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

        # Delete 閿粦瀹?        tree.bind("<Delete>", delete_selected_trade)
        tree.bind("<Button-1>", on_trade_report_on_click)
        tree.bind("<<TreeviewSelect>>", on_trade_report_tree_select) 
        # 鍏抽棴浜嬩欢
        def on_close(event=None):
            self.save_window_position(report_win, window_id)
            report_win.destroy()
        report_win.bind("<Escape>", on_close)
        report_win.protocol("WM_DELETE_WINDOW", on_close)

        # 鍒濆鍔犺浇
        refresh_summary()


    def open_trading_analyzer_qt6(self):
        """鎵撳紑 Qt6 鐗堟湰鐨勪氦鏄撳垎鏋愬伐鍏?""
        try:
            # 馃洝锔?浣跨敤 Qt 瀹夊叏鎿嶄綔涓婁笅鏂囩鐞嗗櫒锛岄伩鍏?pyttsx3 COM 涓?Qt GIL 鍐茬獊
            if not hasattr(self, "_trading_gui_qt6") or self._trading_gui_qt6 is None:
                # 纭繚 Qt 鐜宸插垵濮嬪寲
                if not QtWidgets.QApplication.instance():
                    self._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])
                
                self._trading_gui_qt6 = TradingGUI(
                    sender=self.sender,
                    on_tree_scroll_to_code=self.tree_scroll_to_code,
                    selector=getattr(self, 'selector', None),
                    live_strategy=getattr(self, 'live_strategy', None)
                )
                
            self._trading_gui_qt6.show()
            self._trading_gui_qt6.raise_()
            self._trading_gui_qt6.activateWindow()
            
            toast_message(self, "浜ゆ槗鍒嗘瀽宸ュ叿(Qt6) 宸插惎鍔?)
        except Exception as e:
            logger.error(f"Failed to open TradingGUI Qt6: {e}")
            messagebox.showerror("閿欒", f"鍚姩 Qt6 鍒嗘瀽宸ュ叿澶辫触: {e}")

    def open_kline_viewer_qt(self):
        """鎵撳紑 Qt 鐗堟湰鐨?K 绾跨紦瀛樻煡鐪嬪櫒"""
        try:
            # 馃洝锔?浣跨敤 Qt 瀹夊叏鎿嶄綔涓婁笅鏂囩鐞嗗櫒锛岄伩鍏?pyttsx3 COM 涓?Qt GIL 鍐茬獊
            if not hasattr(self, "_kline_viewer_qt") or self._kline_viewer_qt is None:
                # 纭繚 Qt 鐜宸插垵濮嬪寲
                if not QtWidgets.QApplication.instance():
                    self._qt_app = QtWidgets.QApplication(sys.argv) if hasattr(sys, 'argv') else QtWidgets.QApplication([])
                
                # 鑾峰彇 last6vol 鐢ㄤ簬褰掍竴鍖?                last6vol_map = {}
                if hasattr(self, 'df_all') and not self.df_all.empty and 'last6vol' in self.df_all.columns:
                    last6vol_map = self.df_all['last6vol'].to_dict()

                # 杩炴帴鍙屽嚮浠ｇ爜鍒?TDX 鑱斿姩锛屽苟浼犲叆瀹炴椂鏈嶅姟浠ｇ悊
                self._kline_viewer_qt = KlineBackupViewer(
                    on_code_callback=self.on_code_click,
                    service_proxy=self.realtime_service,
                    last6vol_map=last6vol_map,
                    main_app=self
                )
            
            # 澶勭悊 Qt 浜嬩欢浠ョ‘淇濈獥鍙ｆ纭樉绀?            QtWidgets.QApplication.processEvents()
                
            self._kline_viewer_qt.show()
            self._kline_viewer_qt.raise_()
            self._kline_viewer_qt.activateWindow()
            
            toast_message(self, "K绾挎煡鐪嬪櫒 (Qt) 宸插惎鍔?)
        except Exception as e:
            logger.error(f"Failed to open KlineBackupViewer: {e}")
            messagebox.showerror("閿欒", f"鍚姩 GUI 鏌ョ湅鍣ㄥけ璐? {e}")

    def open_strategy_backtest_view(self):
        """棰勭暀锛氭墦寮€绛栫暐澶嶇洏涓嶢I浼樺寲寤鸿瑙嗗浘"""
        messagebox.showinfo("鏁鏈熷緟", "澶嶇洏鍔熻兘姝ｅ湪寮€鍙戜腑锛屽皢缁撳悎鎮ㄧ殑鍙嶉杩涜妯″瀷寰皟銆?)

    def open_strategy_manager(self, verify_code=None):
        """鎵撳紑绛栫暐鐧界洅绠＄悊鍣?""
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("鎻愮ず", "瀹炴椂鐩戞帶妯″潡灏氭湭鍚姩锛岃绋嶅悗鍐嶈瘯")
            return

        # 绐楀彛澶嶇敤
        if hasattr(self, '_strategy_manager_win') and self._strategy_manager_win and self._strategy_manager_win.winfo_exists():
            self._strategy_manager_win.deiconify()
            self._strategy_manager_win.lift()
            self._strategy_manager_win.focus_force()
            if verify_code:
                self._strategy_manager_win.notebook.select(self._strategy_manager_win.tab_verify)
                self._strategy_manager_win.set_verify_code(verify_code)
            return

        try:
            # 浼犲叆 realtime_service (濡傛灉鏈?
            rt_service = getattr(self, 'realtime_service', None)
            win = StrategyManager(self, self.live_strategy, realtime_service=rt_service, query_manager=self.query_manager)
            self._strategy_manager_win = win
            
            if verify_code:
                win.notebook.select(win.tab_verify)
                win.set_verify_code(verify_code)
                
        except Exception as e:
            logger.error(f"Failed to open StrategyManager: {e}")
            messagebox.showerror("閿欒", f"鍚姩绛栫暐绠＄悊鍣ㄥけ璐? {e}")

    def add_voice_monitor_dialog(self, code, name):
        """
        寮瑰嚭瀵硅瘽妗嗘坊鍔犺闊崇洃鎺?(鐢卞閮ㄨ皟鐢紝濡?MarketPulseViewer)
        鏍￠獙鍞竴鎬э細濡傛灉宸插瓨鍦ㄥ垯鎻愮ず鍚堝苟鎴栨嫆缁?        """
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("鎻愮ず", "瀹炴椂鐩戞帶妯″潡灏氭湭鍚姩")
            return

        # 1. 鍞竴鎬ф鏌?        monitors = self.live_strategy.get_monitors()
        # 鍏煎 key 涓?code 鎴?code_resample 鐨勬儏鍐?        existing_key = None
        if code in monitors:
            existing_key = code
        else:
            # 妫€鏌ユ槸鍚︽湁甯﹀悗缂€鐨?key
            for k in monitors.keys():
                if k.split('_')[0] == code:
                    existing_key = k
                    break
        
        if existing_key:
            if not messagebox.askyesno("閲嶅鎻愮ず", f"{name}({code}) 宸插湪鐩戞帶鍒楄〃涓紒\n\n鏄惁缁х画娣诲姞鏂拌鍒欙紵\n(閫?鍚?鍒欏彇娑?"):
                return
            # 閫?鏄?鍒欑户缁脊鍑烘坊鍔犺鍒欐锛岃涓鸿拷鍔犺鍒?
        # 2. 寮瑰嚭绠€鏄撹鍒欒緭鍏ユ
        dlg = tk.Toplevel(self)
        dlg.title(f"娣诲姞鐩戞帶: {name}")
        dlg.geometry("300x220")
        self.load_window_position(dlg, "AddVoiceMonitorDlg", default_width=300, default_height=220)
        
        tk.Label(dlg, text=f"浠ｇ爜: {code}   鍚嶇О: {name}", font=("Arial", 10, "bold")).pack(pady=10)
        
        tk.Label(dlg, text="棰勮瑙勫垯:").pack(anchor="w", padx=20)
        
        # 瑙勫垯绫诲瀷
        type_var = tk.StringVar(value="price_up")
        # price_up, price_down, change_up
        f_type = tk.Frame(dlg)
        f_type.pack(fill="x", padx=20, pady=5)
        ttk.Combobox(f_type, textvariable=type_var, values=["price_up", "price_down", "change_up"], state="readonly", width=15).pack(side="left")
        
        # 闃堝€?        tk.Label(dlg, text="闃堝€?(浠锋牸/娑ㄥ箙%):").pack(anchor="w", padx=20)
        e_val = tk.Entry(dlg)
        e_val.pack(fill="x", padx=20, pady=5)
        
        # 榛樿濉叆褰撳墠浠?* 1.01 (鏂逛究婕旂ず)
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
                # 璋冪敤 Strategy 娣诲姞
                res = self.live_strategy.add_monitor(code, name, type_var.get(), val, tags="manual", create_price=curr_price)
                toast_message(self, f"宸叉坊鍔犵洃鎺? {name}")
                dlg.destroy()
                
                # 濡傛灉绠＄悊绐楀彛寮€鐫€锛屽埛鏂板畠
                if hasattr(self, '_voice_monitor_win') and self._voice_monitor_win and self._voice_monitor_win.winfo_exists():
                    if hasattr(self._voice_monitor_win, 'refresh_list'):
                        self._voice_monitor_win.refresh_list()
                        
            except ValueError:
                messagebox.showerror("閿欒", "闃堝€煎繀椤绘槸鏁板瓧")

        tk.Button(dlg, text="纭畾娣诲姞", command=on_confirm, bg="#ccffcc").pack(pady=15)

    def open_voice_monitor_manager(self):
        """璇煶棰勮绠＄悊绐楀彛 (鏀寔绐楀彛澶嶇敤)"""

        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            messagebox.showwarning("鎻愮ず", "瀹炴椂鐩戞帶妯″潡灏氭湭鍚姩锛岃绋嶅悗鍐嶈瘯")
            return

        # 鉁?绐楀彛澶嶇敤閫昏緫
        if self._voice_monitor_win and self._voice_monitor_win.winfo_exists():
            self._voice_monitor_win.deiconify()
            self._voice_monitor_win.lift()
            self._voice_monitor_win.focus_force()
            return

        try:
            win = tk.Toplevel(self)
            self._voice_monitor_win = win
            win.title("璇煶棰勮绠＄悊")
            window_id = "璇煶棰勮绠＄悊"
            # --- 绐楀彛瀹氫綅 ---
            # w, h = 800, 500
            # sw = self.winfo_screenwidth()
            # sh = self.winfo_screenheight()
            # pos_x = (sw - w) // 2
            # pos_y = (sh - h) // 2
            # win.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
            # win.bind("<Escape>", lambda e: win.destroy())
            self.load_window_position(win, window_id, default_width=800, default_height=500)
            # --- 椤堕儴鎿嶄綔鍖哄煙 ---
            top_frame = tk.Frame(win)
            top_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(top_frame, text="馃敂 瀹炴椂璇煶鐩戞帶鍒楄〃", font=("Arial", 12, "bold")).pack(side="left")
            
            total_label = tk.Label(
                top_frame,
                text="鎬绘潯鐩? 0",
                anchor="w",
                padx=10,
                font=("寰蒋闆呴粦", 9)
            )
            total_label.pack(side="left")

            # --- [NEW] Cycle Toggle ---
            if not hasattr(self, 'force_d_cycle_var'):
                # Should have been initialized in init_checkbuttons, but safety fallback
                self.force_d_cycle_var = tk.BooleanVar(value=True) 

            tk.Checkbutton(
                top_frame,
                text="寮哄埗(d)鍛ㄦ湡",
                variable=self.force_d_cycle_var,
                indicatoron=0,           # Toggle button style
                width=12,                # Wider click target
                selectcolor="#b2dfdb",   # Light green when checked
                command=lambda: logger.info(f"Cycle Toggle Changed: {self.force_d_cycle_var.get()}")
            ).pack(side="left", padx=10)
            
            tk.Button(top_frame, text="寮€鍚嚜鍔ㄤ氦鏄?, command=lambda: self.live_strategy.start_auto_trading_loop(force=True, concept_top5=getattr(self, 'concept_top5', None)), bg="#fff9c4").pack(side="right", padx=5)
            tk.Button(top_frame, text="娓呯悊鎭㈠鎸佷粨", command=lambda: batch_clear_recovered(), bg="#ffcdd2").pack(side="right", padx=5)
            def on_repair_sync():
                if messagebox.askyesno("鏁版嵁淇", "灏嗚繘琛屼互涓嬫搷浣滐細\n1. 鏍规嵁鍒涘缓鏃堕棿浠庡巻鍙茶鎯呭洖琛ョ己澶辩殑鈥樺姞鍏ヤ环鈥橽n2. 纭繚鎵€鏈夐璀﹁鍒欏凡鍚屾鍒版暟鎹簱\n\n鏄惁绔嬪嵆寮€濮?"):
                    res = self.live_strategy.sync_and_repair_monitors()
                    if "error" in res:
                        messagebox.showerror("閿欒", f"淇杩囩▼涓嚭鐜伴敊璇? {res['error']}")
                    else:
                        msg = f"鉁?鏁版嵁瀵归綈瀹屾垚!\n\n- 浠锋牸鍥炶ˉ: {res['repair_count']} 鍙猏n- 鏁版嵁搴撳悓姝? {res['sync_count']} 鏉n- 鎬绘潯鐩? {res['total']}"
                        if res['errors']:
                            msg += f"\n\n娉ㄦ剰: 鏈?{len(res['errors'])} 椤瑰悓姝ュ紓甯革紝璇锋鏌ユ棩蹇椼€?
                        messagebox.showinfo("鎴愬姛", msg)
                        load_data()

            tk.Button(top_frame, text="鏁版嵁鍚屾淇", command=on_repair_sync, bg="#c8e6c9").pack(side="right", padx=5)
            tk.Button(top_frame, text="娴嬭瘯鎶ヨ闊?, command=lambda: self.live_strategy.test_alert(), bg="#e0f7fa").pack(side="right", padx=5)
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 鍒楄〃鍖哄煙 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 鏄剧ず ID 鏄负浜嗘柟渚跨鐞?(code + rule_index)
            columns = ("code", "name", "resample", "rule_type", "value", "create_price", "curr_price", "pnl", "rank", "add_time", "tags", "id")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            # 4. 搴曢儴鐘舵€佹爮鐢ㄤ簬鏄剧ず璁℃暟
            # --- 搴曢儴缁熻鎬昏 ---
            # status_frame = tk.Frame(win, relief="sunken", bd=1)
            # status_frame.pack(side="bottom", fill="x")

            # total_label = tk.Label(status_frame, text="鎬绘潯鐩? 0", anchor="w", padx=10, font=("寰蒋闆呴粦", 9))
            # total_label.pack(side="left")


            # 鍒锋柊缁熻鍑芥暟
            def refresh_stats():
                total = len(tree.get_children())
                # selected = len(tree.selection())
                total_label.config(text=f"鎬绘潯鐩? {total}")
                # selected_label.config(text=f"宸查€変腑: {selected}")

            

            def treeview_sort_column(tv, col, reverse):
                l = [(tv.set(k, col), k) for k in tv.get_children('')]
                
                # 鏅鸿兘鏁板€兼帓搴?灏濊瘯杞崲涓烘暟鍊?澶辫触鍒欐寜瀛楃涓叉帓搴?                def sort_key(item):
                    val = item[0]
                    if val in ('', '-', '--', 'N/A', None):
                        return (1, 0)  # 绌哄€兼帓鍦ㄦ渶鍚?                    try:
                        # 灏濊瘯杞崲涓烘暟鍊?(澶勭悊鐧惧垎姣斿拰绗﹀彿)
                        clean_val = str(val).replace('%', '').replace('+', '')
                        return (0, float(clean_val))
                    except (ValueError, TypeError):
                        # 鏃犳硶杞崲,鎸夊瓧绗︿覆鎺掑簭
                        return (0, str(val).lower())
                
                l.sort(key=sort_key, reverse=reverse)

                for index, (val, k) in enumerate(l):
                    tv.move(k, '', index)

                tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))


            tree.heading("code", text="浠ｇ爜", command=lambda: treeview_sort_column(tree, "code", False))
            tree.heading("name", text="鍚嶇О", command=lambda: treeview_sort_column(tree, "name", False))
            tree.heading("resample", text="鍛ㄦ湡", command=lambda: treeview_sort_column(tree, "resample", False))
            tree.heading("rule_type", text="瑙勫垯绫诲瀷", command=lambda: treeview_sort_column(tree, "rule_type", False))
            tree.heading("value", text="闃堝€?, command=lambda: treeview_sort_column(tree, "value", False))
            tree.heading("create_price", text="鍔犲叆浠?, command=lambda: treeview_sort_column(tree, "create_price", False))
            tree.heading("curr_price", text="鐜颁环", command=lambda: treeview_sort_column(tree, "curr_price", False))
            tree.heading("pnl", text="鐩堜簭%", command=lambda: treeview_sort_column(tree, "pnl", False))
            tree.heading("rank", text="Rank", command=lambda: treeview_sort_column(tree, "rank", False))
            tree.heading("add_time", text="鏃堕棿", command=lambda: treeview_sort_column(tree, "add_time", False))
            tree.heading("tags", text="绠€浠?, command=lambda: treeview_sort_column(tree, "tags", False))
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
            tree.column("id", width=0, stretch=False) # 闅愯棌 ID 鍒?
            def show_tags_detail(values):
                code, name = values[0], values[1]
                tags_info = values[len(values) -2]

                top = tk.Toplevel(win)
                top.title(f"{name}:{code} 璇︽儏")
                top.geometry("600x400")
                top.lift()
                top.focus_force()
                top.attributes("-topmost", True)
                top.after(100, lambda: top.attributes("-topmost", False))
                # 绠€鍗曞眳涓?                wx = win.winfo_rootx() + 50
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
                col_idx = int(column[1:]) - 1           # 杞负 0-based

                item = tree.identify_row(event.y)
                if not item:
                    return

                values = tree.item(item, "values")

                TAGS_COL_INDEX = 10  # tags 鍦?values 涓殑绱㈠紩

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
                """鍔犺浇鏁版嵁鍒板垪琛?""
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
                        # 瀵逛簬娌℃湁瑙勫垯鐨勮偂绁紝鏄剧ず涓€琛屽崰浣嶏紝鏂逛究绠＄悊
                        uid = f"{key}_none"
                        tree.insert("", "end", values=(pure_code, name, resample, "鈿狅笍(鏈瑙勫垯)", "-", f"{create_price:.2f}", f"{curr_price:.2f}", pnl_str, rank, add_time, tags, uid))
                    else:
                        for idx, rule in enumerate(rules):
                            rtype_map = {
                                "price_up": "浠锋牸绐佺牬 >=",
                                "price_down": "浠锋牸璺岀牬 <=",
                                "change_up": "娑ㄥ箙瓒呰繃 >="
                            }
                            display_type = rtype_map.get(rule['type'], rule['type'])
                            # unique id uses composite key for proper reference
                            uid = f"{key}_{idx}"
                            # 鉁?鏍煎紡鍖栨暟鍊煎睍绀猴紝浠锋牸/闃堝€间繚鐣?浣嶅皬鏁?                            try:
                                val_formatted = f"{float(rule['value']):.2f}"
                            except:
                                val_formatted = rule['value']
                            tree.insert("", "end", values=(pure_code, name, resample, display_type, val_formatted, f"{create_price:.2f}", f"{curr_price:.2f}", pnl_str, rank, add_time, tags, uid))
                
                # 馃挜 鍏抽敭锛氭暟鎹姞杞藉悗鏇存柊缁熻鏍囩
                refresh_stats()

            load_data()
            win.refresh_list = load_data
            self._voice_monitor_win = win

            # --- 鍔ㄦ€佹坊鍔?"绛栫暐閫夎偂" 鎸夐挳 (New) ---
            tk.Button(top_frame, text="绛栫暐閫夎偂...", command=self.open_stock_selection_window, bg="#fff9c4", font=("Arial", 9, "bold")).pack(side="right", padx=5)

            # --- 搴曢儴鎸夐挳 ---
            btn_frame = tk.Frame(win)

            btn_frame.pack(pady=10)
            
            def add_new():
                # 寮瑰嚭涓€涓畝鍗曠殑杈撳叆妗嗭紝鎴栬€呭鐢?add_voice_monitor_dialog
                # 浣?add_voice_monitor_dialog 闇€瑕?code, name 鍙傛暟
                # 杩欓噷鍙互鍋氫竴涓洿閫氱敤鐨勬坊鍔犲璇濇
                
                add_win = tk.Toplevel(win)
                add_win.title("娣诲姞鏂扮洃鎺?)
                wx, wy = win.winfo_x() + 100, win.winfo_y() + 100
                add_win.geometry(f"300x250+{wx}+{wy}")
                
                tk.Label(add_win, text="鑲＄エ浠ｇ爜:").pack(anchor="w", padx=20, pady=5)
                e_code = tk.Entry(add_win)
                e_code.pack(fill="x", padx=20)
                
                # 鐩戞帶绫诲瀷绛夊鐢ㄤ箣鍓嶇殑閫昏緫
                # ... 涓虹畝鍖栵紝杩欓噷寤鸿鐢ㄦ埛鍏堝湪涓荤晫闈㈠彸閿坊鍔狅紝杩欓噷涓昏鍋氱鐞?                # 鎴栬€呰皟鐢ㄤ箣鍓嶇殑 dialog锛屼絾瑕佸厛鎵嬪姩杈撳叆 code 鑾峰彇 name
                pass
                
                # 绠€鍖栧疄鐜帮細鎻愮ず鐢ㄦ埛鍘讳富鐣岄潰娣诲姞
                messagebox.showinfo("鎻愮ず", "璇峰湪涓荤晫闈㈣偂绁ㄥ垪琛ㄥ彸閿偣鍑昏偂绁ㄦ坊鍔犵洃鎺?, parent=add_win)
                add_win.destroy()

            def batch_clear_recovered():
                """涓€閿竻鐞嗘墍鏈?recovered_holding 鏍囪鐨勭洃鎺у苟骞充粨璁板綍"""
                monitors = self.live_strategy.get_monitors()
                to_remove = [code for code, data in monitors.items() if data.get('tags') == "recovered_holding"]
                
                if not to_remove:
                    messagebox.showinfo("鎻愮ず", "鏈彂鐜板甫鏈?'recovered_holding' 鏍囩鐨勭洃鎺ч」", parent=win)
                    return
                
                if not messagebox.askyesno("纭鎿嶄綔", f"纭畾瑕佹竻鐞嗚繖 {len(to_remove)} 鍙仮澶嶆寔浠撹偂鍚楋紵\n杩欏皢鑷姩鍦ㄤ氦鏄撴棩蹇椾腑璁板綍宸插崠鍑哄苟绉婚櫎鐩戞帶銆?, parent=win):
                    return
                
                count = 0
                for code in to_remove:
                    data = monitors.get(code)
                    name = data.get('name', '')
                    # 灏濊瘯鑾峰彇褰撳墠浠?                    price = 0.0
                    if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                        price = float(self.df_all.loc[code].get('trade', 0))
                    
                    # 鎵ц骞充粨璁板綍
                    self.live_strategy.close_position_if_any(code, price, name)
                    # 绉婚櫎鐩戞帶
                    self.live_strategy.remove_monitor(code)
                    count += 1
                
                messagebox.showinfo("鎴愬姛", f"宸叉垚鍔熸竻鐞嗗苟璁板綍 {count} 鍙寔浠撹偂", parent=win)
                load_data()

            def delete_selected(event=None):
                selected = tree.selection()
                if not selected:
                    return

                # 鍙栫涓€涓€変腑椤癸紙鏀寔杩炵画蹇€熷垹闄わ級
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

                # 璋冩暣鍒犻櫎閫昏緫
                if self.live_strategy:
                    # 鉁?[鏂板] 鍒犻櫎鍓嶆鏌ユ寔浠撳苟鎻愮ず
                    is_holding = False
                    if hasattr(self, 'live_strategy') and hasattr(self.live_strategy, 'trading_logger'):
                        try:
                            trades = self.live_strategy.trading_logger.get_trades()
                            is_holding = any(t['code'].zfill(6) == code.zfill(6) and t['status'] == 'OPEN' for t in trades)
                        except: pass
                    
                    if is_holding:
                        # 馃挜 [浼樺寲] 鎻愮ず璇洿鏄庣‘锛氱Щ闄ょ洃鎺?= 鍋滄璺熻釜 = 闇€瑕佸鐞嗘寔浠?                        ans = messagebox.askyesnocancel(
                            "鎸佷粨纭", 
                            f"妫€娴嬪埌 {values[1]}({code}) 灏氭湁鍦ㄥ唽鎸佷粨锛乗n\n绉婚櫎鐩戞帶灏嗗鑷磋鎸佷粨涓嶅啀琚疄鏃惰窡韪紝涓斾负浜嗛槻姝㈣嚜鍔ㄦ仮澶嶏紝绯荤粺灏嗗繀椤诲己鍒跺叧闂鎸佷粨璁板綍銆俓n\n鏄惁鍚屾椂骞跺湪浜ゆ槗鏃ュ織涓爣璁颁负[鍗栧嚭骞充粨]锛焅n\n'鏄? - 鏍囪骞充粨骞剁Щ闄ょ洃鎺n'鍚? - 浠呮爣璁扮Щ闄?涓嶅啀璺熻釜)浣嗕繚鐣欐棩蹇楅棴鐜痋n'鍙栨秷' - 鏀惧純鎿嶄綔", 
                            parent=win
                        )
                        if ans is None: return # 鍙栨秷
                        if ans is True: # 鏄?- 姝ｅ父骞充粨閫昏緫(鐢ㄥ綋鍓嶄环)
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

                    # 馃挜 鑱斿姩鏍稿績锛氬交搴曟竻鐞嗚鍝佺鐨勬墍鏈夋诞鍔ㄦ姤璀︾獥鍙ｄ笌浣欐尝璇煶
                    try:
                        # 1. 鏌ユ壘骞跺叧闂?UI 鎶ヨ绐?                        if hasattr(self, 'code_to_alert_win') and code in self.code_to_alert_win:
                            awin = self.code_to_alert_win[code]
                            if awin.winfo_exists():
                                self._close_alert(awin, is_manual=True)
                        elif hasattr(self, 'active_alerts'):
                            # 鎵樺簳鏌ユ壘
                            for awin in list(self.active_alerts):
                                if getattr(awin, 'stock_code', None) == code:
                                    self._close_alert(awin, is_manual=True)
                        
                        # 2. 寮哄埗鍚屾涓€娆℃椿璺冧唬鐮佸垪琛?(纭繚 cancel 闃熷垪鍜孍xistence妫€鏌ョ珛鍗崇敓鏁?
                        if hasattr(self, '_update_voice_active_codes'):
                            self._update_voice_active_codes()
                    except Exception as linkage_e:
                        logger.debug(f"Linkage cleanup failed for {code}: {linkage_e}")

                # --- 璁板綍鍒犻櫎琛岀殑绱㈠紩 ---
                children = list(tree.get_children())
                try:
                    del_idx = children.index(item)
                except ValueError:
                    del_idx = 0

                # 涓轰簡闃叉绱㈠紩閿欎贡锛屽垹闄ゅ悗蹇呴』鍏ㄩ噺鍒锋柊
                load_data()
                
                # --- 璁剧疆鍒犻櫎鏍囧織浣嶏紝闃叉瑙﹀彂 on_voice_tree_select ---
                self._is_deleting = True
                try:
                     # tree.delete(item) # 宸茬粡鐢?load_data() 鍒锋柊
                     
                     # 閫変腑涓嬩竴琛?(灏濊瘯鍦ㄥ埛鏂板悗鐨?tree 涓壘鍘熶綅缃?
                     children = tree.get_children()
                     if children:
                         if del_idx >= len(children):
                             del_idx = len(children) - 1
                         next_item = children[del_idx]
                         tree.selection_set(next_item)
                         tree.focus(next_item)
                         tree.see(next_item)
                finally:
                     # 蹇呴』纭繚 UI 浜嬩欢寰幆澶勭悊瀹屾瘯鍚庡啀閲嶇疆鏍囧織浣?                     # 浣跨敤 after_idle 纭繚鏈浜嬩欢鏍堟竻绌?                     tree.after_idle(lambda: setattr(self, '_is_deleting', False))


            # def delete_selected(event=None):
            #     selected = tree.selection()
            #     if not selected:
            #         return
                
            #     # if not messagebox.askyesno("纭", "纭畾鍒犻櫎閫変腑鐨勮鍒欏悧?", parent=win):
            #     #     return

            #     # 杩欓噷鐩存帴鍒狅紝涓轰簡椤烘墜锛屽彲浠ヤ笉寮逛簩娆＄‘璁わ紝鎴栬€呬粎鍦?list 閫変腑鏃跺脊
            #     # if not messagebox.askyesno("鍒犻櫎纭", "纭畾鍒犻櫎閫変腑椤?", parent=win):
            #     #     return

            #     for item in selected:
            #          values = tree.item(item, "values")
            #          code = values[0]
            #          uid = values[6]
            #          # 鐢变簬 uid 鏄?'code_idx'锛屼絾濡傛灉鍒犻櫎浜嗗墠闈㈢殑锛屽悗闈㈢殑 idx 浼氬彉
            #          # 鏈€绋冲Ε鐨勬槸锛氬€掑簭鍒犻櫎锛屾垨鑰呴噸鏂板姞杞姐€?            #          # 鎴戜滑鐨勭晫闈㈡槸鍗曢€夎繕鏄閫夛紵Treeview 榛樿澶氶€夈€?            #          # 绠€鍗曞鐞嗭細鍙鐞嗙涓€涓?            #          # 绠€鍗曞鐞嗭細鍙鐞嗙涓€涓?            #          # 澶勭悊鐗规畩鏍囪 'code_none'
            #          if self.live_strategy:
            #              if uid.endswith('_none'):
            #                  # 濡傛灉娌℃湁瑙勫垯锛屽垹闄ゆ搷浣滃嵆绉婚櫎璇ョ洃鎺ч」
            #                  self.live_strategy.remove_monitor(code)
            #              else:
            #                  try:
            #                      idx = int(uid.split('_')[1])
            #                      self.live_strategy.remove_rule(code, idx)
            #                  except:
            #                      pass
            #          break # 浠呭垹涓€涓紝闃叉绱㈠紩閿欎贡
                
            #     load_data()

            def on_voice_tree_select(event):
                # 妫€鏌ュ垹闄ゆ爣蹇椾綅
                if getattr(self, '_is_deleting', False):
                    return

                selected = tree.selection()
                if not selected: return
                item = selected[0]
                values = tree.item(item, "values")
                target_code = values[0]
                name = values[1]
                stock_code = str(target_code).zfill(6)
                # logger.info(f'on_handbook_on_click stock_code:{stock_code} name:{target_name}')
                self.sender.send(stock_code)
                # Auto-launch Visualizer if enabled
                if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                    self.open_visualizer(stock_code)

            def on_voice_right_click(event):
                item_id = tree.identify_row(event.y)
                if not item_id:
                    return
                values = tree.item(item_id, "values")
                # values: (time, code, name, content_preview)
                target_code = values[0]
                stock_code = str(target_code).zfill(6)
                # pyperclip.copy(stock_code)
                # toast_message(self, f"stock_code: {stock_code} 宸插鍒?)
                self.tree_scroll_to_code(stock_code)
                self.original_push_logic(stock_code)
                
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
                    # Auto-launch Visualizer if enabled
                    if hasattr(self, 'vis_var') and self.vis_var.get() and stock_code:
                        self.open_visualizer(stock_code)

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
                 # logger.info(f'on_voice_edit_selected stock_code:{code} name:{name}')
                 
                 current_type = "price_up"
                 monitors = self.live_strategy.get_monitors()
                 if composite_key in monitors:
                     rules = monitors[composite_key]['rules']
                     if idx >= 0 and idx < len(rules):
                         current_type = rules[idx]['type']

                 # 寮瑰嚭缂栬緫妗?(UI 涓?Add 淇濇寔涓€鑷?
                 # edit_win = tk.Toplevel(win)
                 # edit_win.title(f"缂栬緫瑙勫垯 - {name}")
                 # edit_win_id = "缂栬緫瑙勫垯"
                 # self.load_window_position(edit_win, edit_win_id, default_width=900, default_height=600)

                 # main_frame = tk.Frame(edit_win)
                 # main_frame.pack(fill="both", expand=True, padx=10, pady=10)
                 
                 # left_frame = tk.Frame(main_frame) 
                 # left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
                 
                 # right_frame = tk.LabelFrame(main_frame, text="鍙傝€冩暟鎹?(鐐瑰嚮鑷姩濉叆)", width=450)
                 # right_frame.pack(side="right", fill="both", padx=(10, 0))
                 # # right_frame.pack_propagate(False)

                 edit_win = tk.Toplevel(win)
                 edit_win.title(f"缂栬緫瑙勫垯 - {name}")
                 edit_win_id = "缂栬緫瑙勫垯"
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
                     text="鍙傝€冩暟鎹?(鐐瑰嚮鑷姩濉叆)",
                     width=350
                 )
                 right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
                 right_frame.grid_propagate(False)
                 # right_frame.minsize(350, 200)


                 # --- 宸︿晶 ---
                 curr_price = 0.0
                 curr_change = 0.0
                 row_data = None
                 if code in self.df_all.index:
                    row_data = self.df_all.loc[code]
                    try:
                        curr_price = float(row_data.get('trade', 0))
                        curr_change = float(row_data.get('changepercent', 0))
                    except: pass
                 
                 tk.Label(left_frame, text=f"褰撳墠浠锋牸: {curr_price:.2f}", font=("Arial", 12, "bold"), fg="#1a237e").pack(pady=10, anchor="w")
                 # tk.Label(left_frame, text=f"褰撳墠娑ㄥ箙: {curr_change:.2f}%", font=("Arial", 10)).pack(pady=5, anchor="w")

                 tk.Label(left_frame, text="瑙勫垯绫诲瀷:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
                 
                 new_type_var = tk.StringVar(value=current_type)
                 # 鉁?鏍煎紡鍖栨樉绀烘棫闃堝€?                 try:
                     old_val_fmt = f"{float(old_val):.2f}"
                 except:
                     old_val_fmt = str(old_val)
                 val_var = tk.StringVar(value=old_val_fmt)

                 def on_type_change():
                    # 鍒囨崲榛樿鍊?                    t = new_type_var.get()
                    if t == "change_up":
                         val_var.set(f"{curr_change:.2f}")
                    else:
                         val_var.set(f"{curr_price:.2f}")

                 types = [("浠锋牸绐佺牬 (Price >=)", "price_up"), 
                          ("浠锋牸璺岀牬 (Price <=)", "price_down"),
                          ("娑ㄥ箙瓒呰繃 (Change% >=)", "change_up")]
                 
                 for text, val in types:
                     tk.Radiobutton(left_frame, text=text, variable=new_type_var, value=val, command=on_type_change).pack(anchor="w", padx=10, pady=2)

                 tk.Label(left_frame, text="瑙﹀彂闃堝€?", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
                 
                 # 闃堝€艰緭鍏ュ尯鍩?(鍖呭惈 +/- 鎸夐挳)
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
                 
                 # --- 鍙充晶鍙傝€冮潰鏉?---
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
                 # ESC / 鍏抽棴
                 def on_close(event=None):
                     # update_window_position(window_id)
                     self.save_window_position(edit_win, edit_win_id)
                     edit_win.destroy()
                 
                 # 馃攽 鍏抽敭锛氭寕鍒?Toplevel 瀵硅薄涓?                 edit_win.on_close = on_close
                 def confirm_edit(event=None):
                     try:
                         val = float(e_new.get())
                         new_type = new_type_var.get()
                         
                         if self.live_strategy:
                             if idx >= 0:
                                 self.live_strategy.update_rule(code, idx, new_type, val)
                             else:
                                 # 鏂板瑙勫垯 (鍘熸潵鐨勫崰浣嶈)
                                 self.live_strategy.add_monitor(code, name, new_type, val, create_price=curr_price)
                         
                         load_data()
                         edit_win.on_close()
                     except ValueError:
                         messagebox.showerror("閿欒", "鏃犳晥鏁板瓧", parent=edit_win)

                 edit_win.bind("<Escape>", on_close)
                 edit_win.protocol("WM_DELETE_WINDOW", on_close)
                 edit_win.bind("<Return>", confirm_edit)
                 
                 btn_frame = tk.Frame(edit_win)
                 btn_frame.pack(pady=10, side="bottom", fill="x", padx=10)
                 tk.Button(btn_frame, text="淇濆瓨 (Enter)", command=confirm_edit, bg="#ccff90", height=2).pack(side="left", fill="x", expand=True, padx=5)
                 tk.Button(btn_frame, text="鍙栨秷 (Esc)", command=on_close, height=2).pack(side="left", fill="x", expand=True, padx=5)

            tk.Button(btn_frame, text="鉁忥笍 淇敼闃堝€?, command=edit_selected).pack(side="left", padx=10)
            tk.Button(btn_frame, text="馃棏锔?鍒犻櫎瑙勫垯 (Del)", command=delete_selected, fg="red").pack(side="left", padx=10)
            def manual_refresh():
                if self.live_strategy:
                    # 馃挜 寮哄埗浠?JSON/DB 閲嶆柊鍔犺浇锛屾崟鎹夊悗鍙板钩浠撶瓑澶栭儴鍙樻洿
                    self.live_strategy.load_monitors()
                load_data()
                toast_message(self, "鐩戞帶鍒楄〃宸插埛鏂?)

            tk.Button(btn_frame, text="鍒锋柊鍒楄〃", command=manual_refresh).pack(side="left", padx=10)

            # 缁戝畾閫変腑浜嬩欢
            tree.bind("<<TreeviewSelect>>", lambda e: refresh_stats())
            # 鍒濆鍒锋柊
            refresh_stats()

            tree.bind("<Button-1>", on_voice_on_click)
            tree.bind("<Button-3>", on_voice_right_click)
            # 鍙屽嚮缂栬緫
            # tree.bind("<Double-1>", lambda e: edit_selected())
            tree.bind("<Double-1>", on_voice_tree_double_click)
            tree.bind("<<TreeviewSelect>>", on_voice_tree_select) 
            # 鎸?Delete 閿垹闄?            tree.bind("<Delete>", delete_selected)
            # ESC / 鍏抽棴
            def on_close(event=None):
                # update_window_position(window_id)
                self.save_window_position(win, window_id)
                win.destroy()

            win.bind("<Escape>", on_close)
            win.protocol("WM_DELETE_WINDOW", on_close)

            # --- 绛栫暐妯℃嫙娴嬭瘯 ---
            def test_selected_strategy():
                selected = tree.selection()
                if not selected:
                    messagebox.showinfo("鎻愮ず", "璇峰厛閫夋嫨涓€鏉¤鍒?)
                    return
                
                item = selected[0]
                values = tree.item(item, "values")
                code = values[0]
                name = values[1] 
                
                # 璋冪敤涓荤晫闈㈢殑绛栫暐娴嬭瘯閫昏緫锛岃繘琛屼俊鍙风‘璁や笌妯℃嫙浜ゆ槗鍏ュ彛
                self.test_strategy_for_stock(code, name)

            tk.Button(top_frame, text="馃И 妯℃嫙绛栫暐浜ゆ槗", command=test_selected_strategy, bg="#e3f2fd", font=("Arial", 10, "bold")).pack(side="right", padx=5)
            
        except Exception as e:
            logger.error(f"Voice Monitor Manager Error: {e}")
            messagebox.showerror("閿欒", f"鎵撳紑绠＄悊绐楀彛澶辫触: {e}")

    def open_live_signal_viewer(self):
        """鎵撳紑瀹炴椂淇″彿鍘嗗彶鏌ヨ绐楀彛 (PyQt6)"""
        if hasattr(self, '_live_signal_viewer') and self._live_signal_viewer is not None:
            try:
                # 妫€鏌ョ獥鍙ｆ槸鍚︿粛鐒舵湁鏁?                self._live_signal_viewer.show()
                self._live_signal_viewer.raise_()
                self._live_signal_viewer.activateWindow()
                self._live_signal_viewer.refresh_data() # 鑷姩鍒锋柊
                return
            except Exception:
                self._live_signal_viewer = None

        try:
            from live_signal_viewer import LiveSignalViewer
            
            # 鍥炶皟鍑芥暟锛氳仈鍔ㄤ富鐣岄潰 (閲囩敤 tree_scroll_to_code 妯″紡锛屼笌 trading_analyzer 涓€鑷?
            def on_select(code, name,select_win=False,vis=True):
                try:
                    # 浣跨敤绾跨▼瀹夊叏鐨?tree_scroll_to_code
                    # select_win=True 浼氳Е鍙?TDX 鎺ㄩ€佸拰鎵嬫湱璁板綍
                    # vis=True 浼氬悓姝ヨ仈鍔?K 绾垮彲瑙嗗寲锛屼笌鐢ㄦ埛鏈熸湜鐨勪竴鑷?                    self.tree_scroll_to_code(code, select_win=select_win, vis=vis)
                    logger.debug(f"LiveSignalViewer linked: {code} {name}")
                except Exception as e:
                    logger.error(f"LiveSignalViewer linkage error: {e}")

            self._live_signal_viewer = LiveSignalViewer(on_select_callback=on_select, sender=getattr(self, 'sender', None))
            self._live_signal_viewer.show()
            logger.info("LiveSignalViewer opened.")
        except Exception as e:
            logger.error(f"Failed to open LiveSignalViewer: {e}")
            from tkinter import messagebox
            messagebox.showerror("閿欒", f"鎵撳紑瀹炴椂淇″彿鏌ヨ绐楀彛澶辫触: {e}")

    def open_stock_selection_window(self):
        """鎵撳紑绛栫暐閫夎偂涓庝汉宸ュ鏍哥獥鍙?(鏀寔绐楀彛澶嶇敤)"""
        # 1. 纭繚 selector瀛樺湪涓旀暟鎹渶鏂?        try:
            if not hasattr(self, 'selector') or self.selector is None:
                self.selector = StockSelector(df=getattr(self, 'df_all', None))
            else:
                # 鉁?鍏抽敭锛氭洿鏂板凡鏈?selector 鐨勬暟鎹紩鐢紝纭繚 MarketPulse 涔熻兘鐪嬪埌鏈€鏂版暟鎹?                if hasattr(self, 'df_all') and not self.df_all.empty:
                    self.selector.df_all_realtime = self.df_all
                    self.selector.resample = self.global_values.getkey("resample") or 'd'
        except Exception as e:
            logger.error(f"StockSelector 鍒濆鍖?鏇存柊澶辫触: {e}")
            self.selector = None

        # 2. 绐楀彛澶嶇敤閫昏緫
        if self._stock_selection_win and self._stock_selection_win.winfo_exists():
            try:
                # 鉁?鏇存柊绐楀彛鍐呴儴寮曠敤 (闃叉 strategy 閲嶅惎鍚庡紩鐢ㄥけ鏁?
                self._stock_selection_win.live_strategy = getattr(self, 'live_strategy', None)
                self._stock_selection_win.selector = self.selector
                
                # 鉁?寮哄埗鍒锋柊鏁版嵁 (force=True 閲嶆柊璺戠瓫閫?
                self._stock_selection_win.load_data(force=True)
                
                self._stock_selection_win.deiconify()
                self._stock_selection_win.lift()
                self._stock_selection_win.focus_force()
                return
            except Exception as e:
                logger.warning(f"澶嶇敤閫夎偂绐楀彛寮傚父: {e}")

        # 3. 鏂板缓绐楀彛
        try:
            self._stock_selection_win = StockSelectionWindow(self, getattr(self, 'live_strategy', None), self.selector)
            
        except Exception as e:
            logger.error(f"鎵撳紑閫夎偂绐楀彛澶辫触: {e}")
            messagebox.showerror("閿欒", f"鎵撳紑閫夎偂绐楀彛澶辫触: {e}")
            
    def copy_code(self,event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            code = tree.item(item_id, "values")[0]  # 鍋囪绗竴鍒楁槸 code
            pyperclip.copy(code)
            logger.info(f"宸插鍒? {code}")

    def on_tree_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            # 鍙屽嚮琛ㄥご閫昏緫
            self.on_tree_header_double_click(event)
        elif region == "cell":
            # 鍙屽嚮琛岄€昏緫
            self.on_double_click(event)

    def on_tree_header_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":  # 纭鐐瑰嚮鍦ㄨ〃澶?            col = self.tree.identify_column(event.x)
            col_index = int(col.replace("#", "")) - 1
            if 0 <= col_index < len(self.tree["columns"]):
                col_name = self.tree["columns"][col_index]
                self.show_column_menu(col_name,event)  # 寮瑰嚭鍒楅€夋嫨鑿滃崟


    def show_column_menu(self, col, event):
        """
        鍙抽敭寮瑰嚭閫夋嫨鍒楄彍鍗曘€?        col: 褰撳墠鍒?        event: 榧犳爣浜嬩欢锛岀敤浜庤幏鍙栨寚閽堜綅缃?        """

        # 濡傛灉鏄?code 鍒楋紝鐩存帴杩斿洖
        if col == "code" or col in ("#1", "code"):  # 鐪嬩綘鐨勫垪 id 瀹氫箟鏂瑰紡
            return

        if not hasattr(self, "_menu_frame"):
            self._menu_frame = None  # 闃叉閲嶅寮瑰嚭

        # 闃叉澶氭閲嶅寮瑰嚭
        if self._menu_frame and self._menu_frame.winfo_exists():
            self._menu_frame.destroy()


        # 鍒涘缓椤剁骇 Frame锛岀敤浜庢壙杞芥寜閽?        menu_frame = tk.Toplevel(self)
        menu_frame.overrideredirect(True)  # 鍘绘帀鏍囬鏍?        # menu_frame.lift()                  # 猬咃笍 鎶婄獥鍙ｇ疆椤?        # menu_frame.attributes("-topmost", True)  # 猬咃笍 纭繚涓嶈閬尅

        self._menu_frame = menu_frame
        # 娣诲姞涓€涓悳绱㈡
        search_var = tk.StringVar()
        search_entry = ttk.Entry(menu_frame, textvariable=search_var)
        search_entry.pack(fill="x", padx=4, pady=1)

        # 甯冨眬鎸夐挳 Frame
        btn_frame = ttk.Frame(menu_frame)
        btn_frame.pack(fill="both", expand=True)

        # 榧犳爣鐐瑰嚮鐨勭粷瀵瑰潗鏍?        x_root, y_root = event.x_root, event.y_root

        # 绛夊緟 Tk 娓叉煋瀹屾瘯锛屾墠鑳借幏鍙栧疄闄呭楂?        # menu_frame.update_idletasks()
        # menu_frame.update()  
        win_w = 300
        win_h = 300
       
        # 灞忓箷杈圭晫淇濇姢
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # 榛樿浠ラ紶鏍囧彸涓婅涓哄弬鑰?        x = x_root - win_w
        y = y_root

        # 鍒ゆ柇宸︿晶/鍙充晶鏄剧ず閫昏緫
        if x < screen_w / 2:  # 宸﹀崐灞忥紝鍚戝彸灞曞紑
            x = x_root
        else:  # 鍙冲崐灞忥紝鍚戝乏灞曞紑
            x = x_root - win_w

        # 杈圭晫妫€娴?        if x < 0:
            x = 0
        if x + win_w > screen_w:
            x = screen_w - win_w
        if y + win_h > screen_h:
            y = screen_h - win_h
        if y < 0:
            y = 0

        # 璁剧疆鑿滃崟绐楀彛浣嶇疆
        menu_frame.geometry(f"+{x}+{y}")

        def refresh_buttons():
            for w in btn_frame.winfo_children():
                w.destroy()
            kw = search_var.get().lower()

            # 鎼滅储鍖归厤鎵€鏈夊垪锛屼絾鎺掗櫎宸茬粡鍦?current_cols 鐨?            if kw:
                filtered = [c for c in self.df_all.columns if kw in c.lower() and c not in self.current_cols]
            else:
                # 榛樿鏄剧ず绗﹀悎榛樿瑙勫垯涓斾笉鍦?current_cols
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

        # 闃叉姈鏈哄埗
        def on_search_changed(*args):
            if hasattr(self, "_search_after_id"):
                self.after_cancel(self._search_after_id)
            self._search_after_id = self.after(200, refresh_buttons)

        all_cols = [c for c in self.df_all.columns if default_filter(c)]
        search_var.trace_add("write", on_search_changed)

        # 鍒濇濉厖
        refresh_buttons()

        # 鐐瑰嚮鍏朵粬鍦版柟鍏抽棴鑿滃崟
        def close_menu(event=None):
            if menu_frame.winfo_exists():
                menu_frame.destroy()

        menu_frame.bind("<FocusOut>", close_menu)
        menu_frame.focus_force()

    def replace_column(self, old_col, new_col,apply_search=True):
        """鏇挎崲鏄剧ず鍒楀苟鍒锋柊琛ㄦ牸"""

        if old_col in self.current_cols:
            idx = self.current_cols.index(old_col)
            self.current_cols[idx] = new_col

            # 馃敼 2. 鏆傛椂娓呯┖鍒楋紝閬垮厤 Invalid column index 娈嬬暀
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()

            # 馃敼 3. 閲嶆柊閰嶇疆鍒?            new_columns = tuple(self.current_cols)
            self.tree["columns"] = new_columns
            self.tree["displaycolumns"] = new_columns
            self.tree.configure(show="headings")

            logger.info(f'replace_column get_scaled_value:{self.get_scaled_value()}')
            self._setup_tree_columns(self.tree,new_columns, sort_callback=self.sort_by_column, other={})
            self.adjust_column_widths()
            # 閲嶆柊鍔犺浇鏁版嵁
            if apply_search:
                self.apply_search()
            else:
                # 閲嶆柊鍔犺浇鏁版嵁
                self.tree.after(100, lambda: self.refresh_tree(self.df_all, force=True))

    def restore_tree_selection(tree, code: str, col_index: int = 0):
        """
        鎭㈠ Treeview 鐨勯€変腑鍜岀劍鐐逛綅缃?
        :param tree: ttk.Treeview 瀵硅薄
        :param code: 瑕佸尮閰嶇殑鍊?        :param col_index: values 涓敤浜庡尮閰嶇殑鍒楃储寮曪紙榛樿绗?0 鍒楋級
        """
        if not code:
            return False

        for iid in tree.get_children():
            values = tree.item(iid, "values")
            if values and len(values) > col_index and values[col_index] == code:
                tree.selection_set(iid)  # 閫変腑
                tree.focus(iid)          # 鐒︾偣鎭㈠锛屼繚璇侀敭鐩樹笂涓嬪彲鐢?                tree.see(iid)            # 婊氬姩鍒板彲瑙?                return True
        return False


    def reset_tree_columns(self,tree, cols_to_show, sort_func=None):
        """
        瀹夊叏鍦伴噸鏂伴厤缃?Treeview 鐨勫垪瀹氫箟锛岄槻姝?TclError: Invalid column index
        鍙傛暟锛?            tree        - Tkinter Treeview 瀹炰緥
            cols_to_show - 鏂扮殑鍒楀悕鍒楄〃锛坙ist/tuple锛?            sort_func   - 鎺掑簭鍥炶皟鍑芥暟锛屽舰濡?lambda col, reverse: ...
        """

        current_cols = list(tree["columns"])
        if current_cols == list(cols_to_show):
            return  # 鏃犻渶鏇存柊

        # logger.info(f"[Tree Reset] old_cols={current_cols}, new_cols={cols_to_show}")

        # 1锔忊儯 娓呯┖鏃у垪閰嶇疆
        for col in current_cols:
            try:
                tree.heading(col, text="")
                tree.column(col, width=0)
            except Exception as e:
                logger.info(f"clear col err: {col}, {e}")

        # 2锔忊儯 娓呯┖鍒楀畾涔夛紝纭繚鍐呴儴绱㈠紩骞插噣
        tree["columns"] = ()
        tree.update_idletasks()

        # 3锔忊儯 閲嶆柊璁剧疆鍒楀畾涔?        tree.config(columns=cols_to_show)
        tree.configure(show="headings")
        tree["displaycolumns"] = cols_to_show
        tree.update_idletasks()

        # 4锔忊儯 涓烘瘡涓垪閲嶆柊璁剧疆 heading / column
        logger.info(f'reset_tree_columns self.scale_factor :{self.scale_factor} col_scaled:{self.get_scaled_value()}')

        self._setup_tree_columns(tree,cols_to_show, sort_callback=sort_func, other={})


        # logger.info(f"[Tree Reset] applied cols={list(tree['columns'])}")

    def tree_scroll_to_code(self, code, select_win=False, vis=False):
        """澶栭儴璋冪敤锛氬畾浣嶇壒瀹氫唬鐮?(Thread-Safe via Queue)"""
        if not code:
            return True

        def _ui_action():
            try:
                if vis and hasattr(self, 'vis_var') and self.vis_var.get():
                    self.open_visualizer(code)
                
                found = False
                for iid in self.tree.get_children():
                    values = self.tree.item(iid, "values")
                    if values and str(values[0]) == str(code):
                        self.tree.selection_set(iid)
                        self.tree.focus(iid)
                        self.tree.see(iid)
                        found = True
                        break
                
                if not found:
                    pass
                    # toast_message(self, f"{code} not in list")
                
                if select_win:
                    self.original_push_logic(code)

            except Exception as e:
                logger.error(f"tree_scroll_to_code error: {e}")

        if hasattr(self, "tk_dispatch_queue"):
             self.tk_dispatch_queue.put(_ui_action)
        else:
             self.after(0, _ui_action)
        
        return True
    def on_tree_click_for_tooltip(self, event,stock_code=None,stock_name=None,is_manual=False):
        """澶勭悊鏍戣鍥剧偣鍑讳簨浠讹紝寤惰繜鏄剧ず鎻愮ず妗?""
        logger.debug(f"[Tooltip] 鐐瑰嚮浜嬩欢瑙﹀彂: x={event.x}, y={event.y}")
        if not is_manual and not self.tip_var.get():
            return
        # 鍙栨秷涔嬪墠鐨勫畾鏃跺櫒
        if getattr(self, '_tooltip_timer', None):
            try:
                self.after_cancel(self._tooltip_timer)
            except Exception:
                pass
            self._tooltip_timer = None

        # 閿€姣佷箣鍓嶇殑鎻愮ず妗?        if getattr(self, '_current_tooltip', None):
            try:
                self._current_tooltip.destroy()
            except Exception:
                pass
            self._current_tooltip = None

        if stock_code is None:
            # 鑾峰彇鐐瑰嚮鐨勮
            item = self.tree.identify_row(event.y)
            if not item:
                logger.debug("[Tooltip] 鏈偣鍑诲埌鏈夋晥琛?)
                return

            # 鑾峰彇鑲＄エ浠ｇ爜
            values = self.tree.item(item, 'values')
            if not values:
                logger.debug("[Tooltip] 琛屾病鏈夋暟鎹?)
                return
            stock_code = str(values[0])  # code鍦ㄧ涓€鍒?            stock_name = str(values[1])  # code鍦ㄧ浜屽垪
            
        else:
            stock_code = stock_code
        self.test_strategy_for_stock(stock_code, stock_name)
        # x_root, y_root = event.x_root, event.y_root  # 淇濆瓨鍧愭爣
        logger.debug(f"[Tooltip] 鑾峰彇鍒颁唬鐮? {stock_code}, 璁剧疆0.2绉掑畾鏃跺櫒")

        # 璁剧疆0.2绉掑欢杩熷畾鏃跺櫒
        self._tooltip_timer = self.after(200, lambda e=event:self.show_stock_tooltip(stock_code, e))


    def show_stock_tooltip(self, code, event):
        """鏄剧ず鑲＄エ淇℃伅鎻愮ず妗嗭紝鏀寔浣嶇疆淇濆瓨/鍔犺浇"""
        logger.debug(f"[Tooltip] show_stock_tooltip 琚皟鐢? code={code}")

        # 娓呯悊瀹氭椂鍣ㄥ紩鐢?        self._tooltip_timer = None

        # 浠?df_all 鑾峰彇鑲＄エ鏁版嵁
        if not hasattr(self, 'df_all') or self.df_all is None or self.df_all.empty:
            logger.debug("[Tooltip] df_all 涓虹┖鎴栦笉瀛樺湪")
            return

        # 娓呯悊浠ｇ爜鍓嶇紑
        code_clean = code.strip()
        for icon in ['馃敶', '馃煝', '馃搳', '鈿狅笍']:
            code_clean = code_clean.replace(icon, '').strip()

        if code_clean not in self.df_all.index:
            logger.debug(f"[Tooltip] 浠ｇ爜 {code_clean} 涓嶅湪 df_all.index 涓?)
            return

        stock_data = self.df_all.loc[code_clean]
        stock_name = stock_data.get('name', code_clean) if hasattr(stock_data, 'get') else code_clean

        logger.debug(f"[Tooltip] 鎵惧埌鑲＄エ鏁版嵁锛屽噯澶囧垱寤烘彁绀烘")

        # 鍏抽棴宸插瓨鍦ㄧ殑 tooltip
        if hasattr(self, '_current_tooltip') and self._current_tooltip:
            try:
                self._current_tooltip.destroy()
            except:
                pass

        # 鍒涘缓 Toplevel 绐楀彛锛堝甫杈规锛屽彲鎷栨嫿锛?        window_id = "stock_tooltip"
        win = tk.Toplevel(self)
        win.title(f"馃搳 {stock_name} ({code_clean})")
        win.configure(bg='#FFF8E7')
        win.resizable(True, True)
        
        # 鍔犺浇淇濆瓨鐨勪綅缃紝鎴栦娇鐢ㄩ粯璁や綅缃?        self.load_window_position(win, window_id, default_width=280, default_height=320)
        self._current_tooltip = win

        # ESC / 鍏抽棴鏃朵繚瀛樹綅缃?        def on_close(event=None):
            self.save_window_position(win, window_id)
            win.destroy()
            self._current_tooltip = None
        
        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)

        # 鑾峰彇澶氳鏂囨湰鍜屽搴旈鑹?        lines, colors = self._format_stock_info(stock_data)

        # 鍒涘缓 Text 鎺т欢锛堟棤婊氬姩鏉★紝鐢ㄩ紶鏍囨粴杞粴鍔級
        frame = tk.Frame(win, bg='#FFF8E7')
        frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        text_widget = tk.Text(
            frame,
            bg='#FFF8E7',
            bd=0,
            padx=8,
            pady=6,
            wrap='word',
            font=("Microsoft YaHei", 9)
        )
        text_widget.pack(fill='both', expand=True)
        
        # 缁戝畾榧犳爣婊氳疆婊氬姩
        def on_mousewheel(event):
            text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        text_widget.bind("<MouseWheel>", on_mousewheel)
        frame.bind("<MouseWheel>", on_mousewheel)

        for i, (line, color) in enumerate(zip(lines, colors)):
            tag_name = f"line_{i}"
            text_widget.insert(tk.END, line + "\n", tag_name)
            text_widget.tag_config(tag_name, foreground=color, font=("Microsoft YaHei", 9))

            # 妫€鏌?signal 琛岋紝鍗曠嫭璁剧疆鍥炬爣棰滆壊鍜屽ぇ灏?            if "signal:" in line:
                icon_index = line.find("馃憤")
                if icon_index == -1:
                    icon_index = line.find("馃殌")
                if icon_index == -1:
                    icon_index = line.find("鈽€锔?)

                if icon_index != -1:
                    start = f"{i+1}.{icon_index}"
                    end = f"{i+1}.{icon_index+2}"
                    text_widget.tag_add(f"icon_{i}", start, end)
                    text_widget.tag_config(f"icon_{i}", foreground="#FF6600", font=("Microsoft YaHei", 12, "bold"))

        text_widget.config(state=tk.DISABLED)

        # 搴曢儴鍏抽棴鎸夐挳
        btn_frame = tk.Frame(win, bg='#FFF8E7')
        btn_frame.pack(fill='x', pady=3)
        tk.Button(btn_frame, text="鍏抽棴 (ESC)", command=on_close, width=10).pack()

        logger.debug(f"[Tooltip] 鎻愮ず妗嗗凡鍒涘缓")

    def _format_stock_info(self, stock_data):
        """鏍煎紡鍖栬偂绁ㄤ俊鎭负鏄剧ず鏂囨湰锛屽苟杩斿洖棰滆壊鏍囩"""
        code = stock_data.name
        name = stock_data.get('name', '鏈煡')

        close = stock_data.get('close', 0)
        low = stock_data.get('low', 0)
        high = stock_data.get('high', 0)
        boll = stock_data.get('boll', 0)
        upper = stock_data.get('upper', 0)
        upper1 = stock_data.get('upper1', 0)  # 鍋囪鏈?upper1
        upper2 = stock_data.get('upper2', 0)  # 鍋囪鏈?upper1
        high4 = stock_data.get('high4', 0)
        ma5d = stock_data.get('ma5d', 0)
        ma10d = stock_data.get('ma10d', 0)

        lastl1d = stock_data.get('lastl1d', 0)
        lastl2d = stock_data.get('lastl2d', 0)
        lasth1d = stock_data.get('lasth1d', 0)
        lasth2d = stock_data.get('lasth2d', 0)

        # 榛樿鏃犱俊鍙?        signal_icon = ""

        # 鏉′欢鍒ゆ柇椤哄簭寰堥噸瑕侊紝浠庡急鍒板己
        try:
            if close > ma5d and low < ma10d:
                signal_icon = "馃憤"  # 鍙嶆娊
                if close > high4:
                    signal_icon = "馃殌"  # 绐佺牬楂樼偣
                    if close > upper1:
                        signal_icon = "鈽€锔?  # 瓒呰秺涓婅建
            elif close >= lasth1d > lasth2d:
                signal_icon = "馃殌"  # 绐佺牬楂樼偣
                if close > upper2:
                    signal_icon = "鈽€锔?  # 瓒呰秺涓婅建
        except Exception as e:
            if close > ma5d and low < ma5d:
                signal_icon = "馃憤"  # 鍙嶆娊
                if close > high4:
                    signal_icon = "馃殌"  # 绐佺牬楂樼偣
                    if close > upper1:
                        signal_icon = "鈽€锔?  # 瓒呰秺涓婅建
            elif close >= lasth1d > lasth2d:
                signal_icon = "馃殌"  # 绐佺牬楂樼偣
                if close > upper2:
                    signal_icon = "鈽€锔?  # 瓒呰秺涓婅建
        finally:
            pass

        # 璁＄畻绐佺牬鍜屽己鍔?        breakthrough = "鉁? if high > upper else "鉁?
        strength = "鉁? if (lastl1d > lastl2d and lasth1d > lasth2d) else "鉁?

        lines = [
            f"銆恵code}銆憑name}:{close}",
            "鈹€" * 20,
            f"馃搳 鎹㈡墜鐜? {stock_data.get('ratio', 'N/A')}",
            f"馃搳 鎴愪氦閲? {stock_data.get('volume', 'N/A')}",
            f"馃搱 杩為槼: {stock_data.get('red', 'N/A')} 馃敽",
            f"馃搲 杩為槾: {stock_data.get('gren', 'N/A')} 馃敾",
            f"馃搱 绐佺牬甯冩灄: {boll}",
            f"  signal: {signal_icon} (low<10 & C>5)",
            f"  Upper:  {stock_data.get('upper', 'N/A'):.2f}",
            f"  Lower:  {stock_data.get('lower', 'N/A'):.2f}",
            f"馃殌 绐佺牬: {breakthrough} (high > upper)",
            f"馃挭 寮哄娍: {strength} (L1>L2 & H1>H2)",
        ]

        # 瀹氫箟姣忚棰滆壊
        colors = [
            'blue',        # 鑲＄エ浠ｇ爜
            'black',       # 鍒嗗壊绾?            'red',       # 鎹㈡墜鐜?            'green',       # 鎴愪氦閲?            'red',         # 杩為槼
            'green',         # 杩為槾
            'orange',      # 甯冩灄甯︽爣棰?            'orange',      # Upper
            'orange',      # Middle
            'orange',      # Lower
            'purple',      # 绐佺牬
            'purple',      # 寮哄娍
        ]

        return lines, colors


    def toggle_feature_colors(self):
        """
        鍒囨崲鐗瑰緛棰滆壊鏄剧ず鐘舵€侊紙鍝嶅簲win_var鍙樺寲锛?        瀹炴椂鏇存柊棰滆壊鏄剧ず骞跺埛鏂扮晫闈?        """


        if not hasattr(self, 'feature_marker') or not hasattr(self, 'win_var'):
            return
        
        try:
            # 鑾峰彇win_var褰撳墠鐘舵€?            enable_colors = not self.win_var.get()
            
            # 鏇存柊feature_marker鐨勯鑹叉樉绀虹姸鎬?            self.feature_marker.set_enable_colors(enable_colors)
            logger.debug(f"self.feature_marker : {hasattr(self, 'feature_marker')}")
            # 绔嬪嵆鍒锋柊鏄剧ず浠ュ簲鐢ㄦ柊鐨勯鑹茬姸鎬?            self.refresh_tree()
            
            logger.info(f"鉁?鐗瑰緛棰滆壊鏄剧ず宸瞷'寮€鍚? if enable_colors else '鍏抽棴'}")
        except Exception as e:
            logger.error(f"鉂?鍒囨崲鐗瑰緛棰滆壊澶辫触: {e}")

    def refresh_tree(self, df=None, force=False):
        """鍒锋柊 TreeView锛屼繚璇佸垪鍜屾暟鎹弗鏍煎榻愩€?""
        start_time = time.time()
        
        if df is None:
            df = self.current_df.copy()

        # 鑻?df 涓虹┖锛屾洿鏂扮姸鎬佸苟杩斿洖
        if df is None or df.empty:
            self.current_df = pd.DataFrame() if df is None else df
            
            # 鉁?浣跨敤澧為噺鏇存柊娓呯┖
            if self._use_incremental_update and hasattr(self, 'tree_updater'):
                self.tree_updater.update(pd.DataFrame(), force_full=True)
            else:
                # 浼犵粺鏂瑰紡娓呯┖
                for iid in self.tree.get_children():
                    self.tree.delete(iid)
            
            self.update_status()
            return

        # 鈿?闈炰氦鏄撴椂闂翠紭鍖栵細浠呭湪鏁版嵁鎴栧垪閰嶇疆鐪熸鍙樺寲鏃跺埛鏂?        # 浜ゆ槗鏃堕棿锛?:15-11:30, 13:00-15:00
        now_time = cct.get_now_time_int()
        is_trading_time = cct.get_trade_date_status() and ((915 <= now_time <= 1130) or (1300 <= now_time <= 1500))
        
        # 瀹氫箟鐘舵€佹寚绾癸細鍖呭惈浠ｇ爜鍝堝笇銆佸垪閰嶇疆鍝堝笇
        # code_hash = hash(tuple(tuple(sorted(df['code'].astype(str).values)))) if 'code' in df.columns else hash(len(df))

        code_hash = hash(tuple(df['code'].astype(str).values)) if 'code' in df.columns else hash(len(df))
        cols_hash = hash(tuple(self.current_cols))
        current_fingerprint = (code_hash, cols_hash)

        if not is_trading_time and not force:
            if hasattr(self, '_last_refresh_fingerprint') and self._last_refresh_fingerprint == current_fingerprint:
                # 闈炰氦鏄撴椂闂翠笖鐘舵€佹棤鍙樺寲锛岃烦杩囦互鑺傜渷 CPU
                return
        
        self._last_refresh_fingerprint = current_fingerprint

        df = df.copy()

        # 纭繚 code 鍒楀瓨鍦ㄥ苟涓哄瓧绗︿覆锛堜究浜庢樉绀猴級
        if 'code' not in df.columns:
            df.insert(0, 'code', df.index.astype(str))

        # 瑕佹樉绀虹殑鍒楅『搴?        cols_to_show = [c for c in self.current_cols if c in df.columns]
        
        # 鉁?浣跨敤澧為噺鏇存柊鏈哄埗
        if self._use_incremental_update and hasattr(self, 'tree_updater'):
            try:
                # 鏇存柊鍒楅厤缃紙濡傛灉鍒楀彂鐢熷彉鍖栵級
                if self.tree_updater.columns != cols_to_show:
                    self.tree_updater.columns = cols_to_show
                    logger.info(f"[TreeUpdater] 鍒楅厤缃凡鏇存柊: {len(cols_to_show)}鍒?)
                
                # 鉁?妫€娴嬫槸鍚﹀彧鏄帓搴忥紙鏁版嵁鐩稿悓浣嗛『搴忎笉鍚岋級
                # 濡傛灉鏄帓搴忔搷浣滐紝寮哄埗鍏ㄩ噺鍒锋柊浠ョ‘淇濋『搴忔纭?                force_full = False
                if hasattr(self, '_last_df_codes'):
                    current_codes = df['code'].astype(str).tolist()
                    # 濡傛灉code闆嗗悎鐩稿悓浣嗛『搴忎笉鍚岋紝璇存槑鏄帓搴忔搷浣?                    if set(current_codes) == set(self._last_df_codes) and current_codes != self._last_df_codes:
                        force_full = True
                        logger.debug(f"[TreeUpdater] 妫€娴嬪埌鎺掑簭鎿嶄綔锛屾墽琛屽叏閲忓埛鏂?)
                
                # 淇濆瓨褰撳墠鐨刢ode鍒楄〃鐢ㄤ簬涓嬫姣旇緝
                self._last_df_codes = df['code'].astype(str).tolist()
                
                # 鎵ц澧為噺鏇存柊
                added, updated, deleted = self.tree_updater.update(df[cols_to_show], force_full=force_full)
                
                # 鎭㈠閫変腑鐘舵€?                if self.select_code:
                    self.tree_updater.restore_selection(self.select_code)
                
                # 璁板綍鎬ц兘
                duration = time.time() - start_time
                self.perf_monitor.record(duration)
                
                # 姣?0娆℃洿鏂版墦鍗颁竴娆℃€ц兘鎶ュ憡
                stats = self.perf_monitor.get_stats()
                if stats.get("total_count", 0) % 10 == 0:  # 鈿?浣跨敤total_count
                    logger.info(self.perf_monitor.report())
                
            except Exception as e:
                logger.error(f"[TreeUpdater] 澧為噺鏇存柊澶辫触,鍥為€€鍒板叏閲忓埛鏂? {e}")
                # 鍥為€€鍒颁紶缁熸柟寮?                self._refresh_tree_traditional(df, cols_to_show)
        else:
            # 浣跨敤浼犵粺鏂瑰紡鍒锋柊
            self._refresh_tree_traditional(df, cols_to_show)

        # 鉁?鍙屽嚮琛ㄥご缁戝畾 - 闇€瑕佷繚鐣欎互鏀寔鍒楃粍鍚堢鐞嗗櫒
        # 杩欎釜缁戝畾涓嶄細骞叉壈鎺掑簭,鍥犱负on_tree_double_click浼氬尯鍒唄eading鍜宑ell鍖哄煙
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        # 淇濆瓨瀹屾暣鏁版嵁
        self.current_df = df
        
        # 璋冩暣鍒楀
        self.adjust_column_widths()
        
        # 鏇存柊鐘舵€佹爮
        self.update_status()
    
    def _refresh_tree_traditional(self, df, cols_to_show):
        """浼犵粺鐨勫叏閲忓埛鏂版柟寮?浣滀负澧為噺鏇存柊鐨勫鐢ㄦ柟妗?"""
        cols = self.tree["displaycolumns"]
        self.tree["displaycolumns"] = ()

        # 娓呯┖鎵€鏈夎
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        
        # 閲嶆柊鎻掑叆鎵€鏈夎
        for idx, row in df.iterrows():
            values = [row.get(col, "") for col in cols_to_show]
            
            # 鉁?濡傛灉鍚敤浜嗙壒寰佹爣璁?鍦╪ame鍒楀墠娣诲姞鍥炬爣
            if self._use_feature_marking and hasattr(self, 'feature_marker'):
                try:
                    # 鍑嗗琛屾暟鎹敤浜庣壒寰佹娴?                    row_data = {
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
                    
                    # 鑾峰彇鍥炬爣
                    icon = self.feature_marker.get_icon_for_row(row_data)
                    if icon:
                        # 鍦╪ame鍒楀墠娣诲姞鍥炬爣(鍋囪name鍦ㄧ2鍒?index 1)
                        name_idx = cols_to_show.index('name') if 'name' in cols_to_show else -1
                        if name_idx >= 0 and name_idx < len(values):
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception as e:
                    logger.debug(f"娣诲姞鍥炬爣澶辫触: {e}")
            
            # 鎻掑叆琛?            iid = self.tree.insert("", "end", values=values)
            
            # 鉁?搴旂敤棰滆壊鏍囪
            if self._use_feature_marking and hasattr(self, 'feature_marker'):
                try:
                    row_data = {
                        'percent': row.get('percent', 0),
                        'volume': row.get('volume', 0),
                        'category': row.get('category', '')
                    }
                    # 鑾峰彇骞跺簲鐢ㄦ爣绛?涓嶆坊鍔犲浘鏍?鍥犱负宸茬粡鍦╲alues涓坊鍔犱簡)
                    tags = self.feature_marker.get_tags_for_row(row_data)
                    if tags:
                        self.tree.item(iid, tags=tuple(tags))
                except Exception as e:
                    logger.debug(f"搴旂敤棰滆壊鏍囪澶辫触: {e}")

        self.tree["displaycolumns"] = cols
        # 鎭㈠閫変腑鐘舵€?        if self.select_code:
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                if values and values[0] == self.select_code:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    break


    def adjust_column_widths(self):
        """鏍规嵁褰撳墠 self.current_df 鍜?tree 鐨勫垪璋冩暣鍒楀锛堝彧浣滅敤鍦?display 鐨勫垪锛?""
        # cols = list(self.tree["displaycolumns"]) if self.tree["displaycolumns"] else list(self.tree["columns"])
        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return  # 宸查攢姣侊紝鐩存帴杩斿洖
        cols = list(self.tree["columns"])

        # 閬嶅巻鏄剧ず鍒楀苟璁剧疆鍚堥€傚搴?        for col in cols:
            # 璺宠繃涓嶅瓨鍦ㄤ簬 df 鐨勫垪
            if col not in self.current_df.columns:
                # 浠嶈纭繚鍒楁湁鏈€灏忓搴?                self.tree.column(col, width=int(50*self.get_scaled_value()))
                continue
            # # 璁＄畻鍒椾腑鏈€澶у瓧绗︿覆闀垮害
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            # 鍩虹闆嗙害鍖栵細7鍍忕礌/瀛楃锛屾渶灏忓45
            width = int(min(max(max_len * 7, int(45 * self.get_scaled_value())), 350))

            if col == 'name':
                width = int(getattr(self, "_name_col_width", 120 * self.scale_factor))
            elif col == 'code':
                # 浠ｇ爜鍒?6 浣嶏紝80 鍍忕礌瓒冲
                width = int(80 * self.scale_factor)
            elif col in ['ra', 'ral', 'win', 'red', 'kind', 'fib', 'fibl', 'op']:
                # 鏋佺獎鎶€鏈寚鏍囧垪
                width = int(45 * self.scale_factor)

            self.tree.column(col, width=int(width))
        logger.debug(f'adjust_column_widths done :{len(cols)}')
    # ----------------- 鎺掑簭 ----------------- #
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
            # 鉁?鍚嶇О鎺掑簭鏀寔鍥炬爣浼樺厛绾э紙涓庨€夎偂绐楀彛閫昏緫涓€鑷达級
            # 鐢熸垚甯﹀浘鏍囩殑杈呭姪鎺掑簭搴忓垪
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

        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))
        self.tree.yview_moveto(0)


    def process_query_test(query: str):
        """
        鎻愬彇 query 涓?`and (...)` 鐨勯儴鍒嗭紝鍓旈櫎鍚庡啀鎷兼帴鍥炲幓
        """

        # 1锔忊儯 鎻愬彇鎵€鏈?`and (...)` 鐨勬嫭鍙锋潯浠?        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2锔忊儯 鍓旈櫎鍘熷 query 閲岀殑杩欎簺鏉′欢
        new_query = query
        for bracket in bracket_patterns:
            new_query = new_query.replace(f'and {bracket}', '')

        # 3锔忊儯 淇濈暀鍓旈櫎鐨勬嫭鍙锋潯浠讹紙鍚庨潰鍙崟鐙鐞嗭紝姣斿鍒嗙被鏉′欢锛?        removed_conditions = bracket_patterns

        # 4锔忊儯 绀轰緥锛氭妸鏉′欢鎷兼帴鍥炲幓
        if removed_conditions:
            final_query = f"{new_query} and " + " and ".join(removed_conditions)
        else:
            final_query = new_query

        return new_query.strip(), removed_conditions, final_query.strip()


        # 馃攳 娴嬭瘯
        query = '(lastp1d > ma51d  and lasth1d > lasth2d  > lasth3d and lastl1d > lastl2d > lastl3d and (high > high4 or high > upper)) and (category.str.contains("鍥烘€佺數姹?))'

        new_query, removed, final_query = process_query(query)

        logger.info(f"鍘绘帀鍚庣殑 query: {new_query}")
        logger.info(f"鎻愬彇鍑虹殑鏉′欢: {removed}")
        logger.info(f"鎷兼帴鍚庣殑 final_query:{final_query}")

    def _on_search_var_change(self, *_):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()

        # [FIX] 褰?val1 涓虹┖鏃讹紝涓嶅簲璇ヤ粎鐢?val2 瑙﹀彂鎼滅储
        # 鍥犱负娓呯┖ val1 閫氬父鎰忓懗鐫€鐢ㄦ埛鎯宠鏌ョ湅鍏ㄩ儴鏁版嵁
        if not val1:
            # 濡傛灉鏈夋寕璧风殑鎼滅储浠诲姟锛屽彇娑堝畠
            if self._search_job:
                self.after_cancel(self._search_job)
                self._search_job = None
            # 娓呴櫎涓婃鍊硷紝閬垮厤鍚庣画璇垽
            if hasattr(self, "_last_value"):
                self._last_value = ""
            return  # 涓嶈Е鍙戞悳绱?
        # 鏋勫缓鍘熷鏌ヨ璇彞
        if val1 and val2:
            query = f"({val1}) and ({val2})"
        else:
            query = val1

        # 濡傛灉鏂板€煎拰涓婃涓€鏍凤紝灏变笉瑙﹀彂
        if hasattr(self, "_last_value") and self._last_value == query:
            return
        self._last_value = query

        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(3000, self.apply_search)  # 3000ms鍚庢墽琛?
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
        self.query_manager.clear_hits()
        source = kwargs.get("source", "")
        selected_query = kwargs.get("selected_query")

        if "search_history1" in kwargs:
            h1 = kwargs["search_history1"]
            if h1 is self.query_manager.history2:
                logger.info("[璀﹀憡] sync_history_from_QM 鏀跺埌閿欒寮曠敤锛坔istory2锛夆啋 瑕嗙洊 history1 琚樆姝?)
            else:
                self.search_history1 = self._format_history_list(h1, self.search_map1)
                if hasattr(self, 'search_combo1'):
                    self.search_combo1['values'] = self.search_history1

        if "search_history2" in kwargs:
            h2 = kwargs["search_history2"]
            if h2 is self.query_manager.history1:
                logger.info("[璀﹀憡] sync_history_from_QM 鏀跺埌閿欒寮曠敤锛坔istory1锛夆啋 瑕嗙洊 history2 琚樆姝?)
            else:
                self.search_history2 = self._format_history_list(h2, self.search_map2)
                if hasattr(self, 'search_combo2'):
                    self.search_combo2['values'] = self.search_history2
        if "search_history3" in kwargs:
            h3 = kwargs["search_history3"]
            if h3 is self.query_manager.history1 or h3 is self.query_manager.history2:
                logger.info("[璀﹀憡] sync_history_from_QM 鏀跺埌閿欒寮曠敤锛坔istory1/2锛夆啋 瑕嗙洊 history3 琚樆姝?)

            else:
                if hasattr(self, "search_history3") and isinstance(self.search_history3, list):
                    self.search_history3.clear()
                    self.search_history3.extend([r["query"] for r in list(h3)])
                else:
                    self.search_history3 = [r["query"] for r in list(h3)]
                
                if hasattr(self, "kline_monitor") and getattr(self.kline_monitor, "winfo_exists", lambda: False)():
                    try:
                        self.kline_monitor.refresh_search_combo3()
                        # 濡傛灉鏄弻鍑昏仈鍔紝寮哄埗鎵ц涓€娆℃煡璇互搴旂敤杩囨护鍣?                        if source == "use" and selected_query:
                            self.kline_monitor.search_var.set(selected_query)
                            self.kline_monitor.search_code_status(onclick=True)
                    except Exception as e:
                        logger.info(f"[璀﹀憡] 鍒锋柊 KLineMonitor ComboBox 澶辫触: {e}")

        if "search_history4" in kwargs:
            h4 = kwargs["search_history4"]
            self.search_history4 = [r["query"] for r in list(h4)]
            if hasattr(self, 'search_combo4'):
                self.search_combo4['values'] = self.search_history4
                if source == "use" and selected_query:
                    self.search_var4.set(selected_query)
                    self.apply_search()
        
        # 鉁?瀛愮獥鍙ｅ悓姝ワ細杞彂缁欑瓥鐣ョ櫧鐩掔鐞嗙獥鍙?        if hasattr(self, "_strategy_manager_win") and self._strategy_manager_win and getattr(self._strategy_manager_win, "winfo_exists", lambda: False)():
            try:
                self._strategy_manager_win._on_history_sync(**kwargs)
            except Exception as e:
                logger.info(f"[璀﹀憡] 杞彂鍚屾鍒?StrategyManager 澶辫触: {e}")

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

        # 鈿欙笍 妫€鏌ユ槸鍚︽槸鍒氱紪杈戣繃鐨?query
        edited_pair = getattr(self.query_manager, "_just_edited_query", None)
        if edited_pair:
            old_query, new_query = edited_pair
            # 娓呴櫎鏍囪锛岄槻姝㈠奖鍝嶄笅娆?            self.query_manager._just_edited_query = None
            
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
                 # 鑻?val 浠嶆槸鏃х殑锛岀洿鎺ヨ烦杩囧悓姝?(should not happen if logic is correct upstream)
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
        # 鈿狅笍 澧為噺鍚屾鍒?QueryHistoryManager
        # ----------------------
        history = getattr(self.query_manager, history_attr)
        existing_queries = {r["query"]: r for r in history}
        # logger.info(f'val: {val} {val in existing_queries}')
        new_history = []
        for q in search_history:
            # [MODIFIED] Resolve display label to raw query
            raw_q = search_map.get(q, q) if search_map else q
            
            if raw_q in existing_queries:
                # 淇濈暀鍘熸潵鐨?note / starred
                new_history.append(existing_queries[raw_q])
            else:
                # 鏂板缓
                # if hasattr(self, "_last_value") and self._last_value.find(q) >=0:
                #     continue
                new_history.append({"query": raw_q, "starred":  0, "note": ""})

        setattr(self.query_manager, history_attr, new_history)

        if self.query_manager.current_key == current_key:
            self.query_manager.current_history = new_history
            self.query_manager.refresh_tree()

    def update_category_result(self, df_filtered):
        """缁熻姒傚康寮傚姩锛屽湪涓荤獥鍙ｄ笂鏂规樉绀烘憳瑕?""
        try:
            if df_filtered is None or df_filtered.empty:
                logger.info("[update_category_result] df_filtered is empty")
                return

            # --- 缁熻褰撳墠姒傚康 ---
            cat_dict = {}  # {concept: [codes]}
            all_cats = []  # 鐢ㄤ簬缁熻鍑虹幇娆℃暟
            topN = df_filtered.head(50)

            for code, row in topN.iterrows():
                if isinstance(row.get("category"), str):
                    cats = [c.strip() for c in row["category"].replace("锛?, ";").replace("+", ";").split(";") if c.strip()]
                    for ca in cats:
                        # 杩囨护娉涙蹇?                        if is_generic_concept(ca):
                            continue
                        all_cats.append(ca)
                        # 娣诲姞鍏朵粬淇℃伅鍒板厓缁勯噷锛屾瘮濡?(code, name, percent, volume)
                        percent = row.get("percent")
                        if pd.isna(percent) or percent == 0:
                            percent = row.get("per1d", 0)
                        cat_dict.setdefault(ca, []).append((
                            code,
                            row.get("name", ""),
                            # row.get("percent", 0) or row.get("per1d", 0),
                            percent,
                            row.get("volume", 0)
                            # 濡傛灉杩樻湁鍏朵粬鍒楋紝鍙互缁х画鍔? row.get("鍏朵粬鍒?)
                        ))

            if not all_cats:
                logger.info("[update_category_result] No concepts found in filtered data")
                return

            # --- 缁熻鍑虹幇娆℃暟 ---
            counter = Counter(all_cats)
            top5 = OrderedDict(counter.most_common(5))

            display_text = "  ".join([f"{k}:{v}" for k, v in top5.items()])
            current_categories =  list(top5.keys())  #淇濇寔椤哄簭

            # --- 鏍囩鍒濆鍖?---
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
                self.lbl_category_result.config(text=f"褰撳墠姒傚康锛歿display_text}")
                return

            # --- 瀵规瘮涓婃缁撴灉 ---
            old_categories = getattr(self, "_last_categories", set())
            added = [c for c in current_categories if c not in old_categories]
            removed = [c for c in old_categories if c not in current_categories]


            if added or removed:
                diff_texts = []
                if added:
                    diff_texts.append(f"馃啎 鏂板锛歿'銆?.join(sorted(added))}")
                if removed:
                    diff_texts.append(f"鉂?娑堝け锛歿'銆?.join(sorted(removed))}")
                diff_summary = "  ".join(diff_texts)
                self.lbl_category_result.config(text=f"姒傚康寮傚姩锛歿diff_summary}", fg="red")

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
                self.lbl_category_result.config(text=f"褰撳墠姒傚康锛歿display_text}", fg="green")

            # 淇濆瓨鐘舵€?            self._last_categories = current_categories
            self._last_cat_dict = cat_dict

        except Exception as e:
            logger.error(f"[update_category_result] 鏇存柊姒傚康淇℃伅鍑洪敊: {e}", exc_info=True)

    def on_code_click(self, code):
        """鐐瑰嚮寮傚姩绐楀彛涓殑鑲＄エ浠ｇ爜"""
        if code != self.select_code:
            self.select_code = code
            logger.info(f"select_code: {code}")
            # 鉁?鍙敼涓烘墦寮€璇︽儏閫昏緫锛屾瘮濡傦細
            # if hasattr(self, "show_stock_detail"):
            #     self.show_stock_detail(code)
            self.sender.send(code)
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                self.open_visualizer(code)
    # --- 绫诲唴閮ㄦ柟娉?---
    def show_concept_detail_window(self):
        """寮瑰嚭璇︾粏姒傚康寮傚姩绐楀彛锛堝鐢?鑷姩鍒锋柊+閿洏/婊氳疆+楂樹寒锛?""
        if not hasattr(self, "_last_categories"):
            return
        # code, name = self.get_stock_code_none()
        self.plot_following_concepts_pg()
        # --- 妫€鏌ョ獥鍙ｆ槸鍚﹀凡瀛樺湪 ---
        if getattr(self, "_concept_win", None):
            try:
                if self._concept_win.winfo_exists():
                    win = self._concept_win
                    win.deiconify()
                    win.lift()
                    # 浠呮竻鐞嗘棫鍐呭鍖猴紝涓嶉攢姣佺獥鍙ｇ粨鏋?                    for widget in win._content_frame.winfo_children():
                        widget.destroy()
                    self.update_concept_detail_content()
                    return
                else:
                    self._concept_win = None
            except Exception:
                self._concept_win = None

        win = tk.Toplevel(self)
        self._concept_win = win
        win.title("姒傚康寮傚姩璇︽儏")
        self.load_window_position(win, "detail_window", default_width=220, default_height=400)
        #灏?win 璁句负 鐖剁獥鍙ｇ殑涓存椂绐楀彛
        # 鍦?Windows 涓婅〃鐜颁负 娌℃湁鍗曠嫭浠诲姟鏍忓浘鏍?        # 甯哥敤浜?宸ュ叿绐楀彛 / 寮圭獥
        # win.transient(self)

        # --- 涓籉rame + Canvas + 婊氬姩 ---
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

        # --- 榧犳爣婊氳疆 ---
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

        # --- 淇濆瓨寮曠敤 ---
        win._canvas = canvas
        win._content_frame = scroll_frame
        win._unbind_mousewheel = unbind_mousewheel

        # --- 閿洏婊氬姩涓庨珮浜垵濮嬪寲 ---
        self._label_widgets = []
        self._selected_index = 0

        # 閿洏浜嬩欢鍙湪婊氬姩鍖哄煙鏈夋晥
        canvas.bind("<Up>", self._on_key)
        canvas.bind("<Down>", self._on_key)
        canvas.bind("<Prior>", self._on_key)
        canvas.bind("<Next>", self._on_key)
        # 鑾峰彇鐒︾偣
        canvas.focus_set()
        # --- 鍏抽棴绐楀彛 ---
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
        # --- 鍒濆鍐呭 ---
        self.update_concept_detail_content()
        def _keep_focus(event):
            """闃叉鐒︾偣涓㈠け"""
            if self._concept_win._content_frame and self._concept_win._content_frame.winfo_exists():
                self._concept_win._content_frame.focus_set()

        # 鍦ㄥ垵濮嬪寲涓粦瀹氫竴娆?        canvas.bind("<FocusOut>", _keep_focus)
        # win.bind("<FocusIn>", lambda e, w=win: self.on_monitor_window_focus(w))
        # 鍒濆鍖栨椂缁戝畾
        win.bind("<Button-1>", lambda e, w=win: self.on_monitor_window_focus(w))

    def update_concept_detail_content(self, limit=5):
        """鍒锋柊姒傚康璇︽儏绐楀彛鍐呭锛堝悗鍙板彲璋冪敤锛?""
        if not hasattr(self, "_concept_win") or not self._concept_win:
            return
        if not self._concept_win.winfo_exists():
            self._concept_win = None
            return

        scroll_frame = self._concept_win._content_frame
        canvas = self._concept_win._canvas

        # 娓呯┖鏃у唴瀹?        for widget in scroll_frame.winfo_children():
            widget.destroy()
        self._label_widgets = []

        # --- 鏁版嵁閫昏緫 ---
        current_categories = getattr(self, "_last_categories", [])
        prev_categories = getattr(self, "_prev_categories", [])
        cat_dict = getattr(self, "_last_cat_dict", {})

        added = [c for c in current_categories if c not in prev_categories]
        removed = [c for c in prev_categories if c not in current_categories]
        # === 鏈夋柊澧炴垨娑堝け ===
        if added or removed:
            if added:
                tk.Label(scroll_frame, text="馃啎 鏂板姒傚康", font=self.default_font, fg="green").pack(anchor="w", pady=(0, 5))
                for c in added:
                    tk.Label(scroll_frame, text=c, fg="blue", font=self.default_font_bold).pack(anchor="w", padx=5)
                    stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)[:limit]  # 鍙彇鍓?limit
                    for code, name, percent, volume in stocks:
                        rank = 0
                        if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                            val = self.df_all.loc[code].get('Rank', 0)
                            rank = int(val) if pd.notna(val) else 0
                        lbl = tk.Label(scroll_frame, text=f"  {code} {name} R:{rank:<4} {percent:>6.2f}% {volume}",
                                       fg="black", cursor="hand2", anchor="w", takefocus=True)    # 猸?蹇呴』
                        lbl.pack(anchor="w", padx=6)
                        lbl._code = code
                        lbl._concept = c
                        idx = len(self._label_widgets)
                        lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                        lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                        lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))
                        self._label_widgets.append(lbl)

            if removed:
                tk.Label(scroll_frame, text="鉂?娑堝け姒傚康", font=self.default_font_bold, fg="red").pack(anchor="w", pady=(10, 5))
                for c in removed:
                    tk.Label(scroll_frame, text=c, fg="gray", font=self.default_font_bold).pack(anchor="w", padx=5)

        else:
            tk.Label(scroll_frame, text="馃搳 褰撳墠鍓?姒傚康", font=self.default_font_bold, fg="blue").pack(anchor="w", pady=(0, 5))
            for c in current_categories[:5]:
                tk.Label(scroll_frame, text=c, fg="black", font=self.default_font_bold).pack(anchor="w", padx=5)
                stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)[:limit]  # 鍙彇鍓?limit
                for code, name, percent, volume in stocks:
                    rank = 0
                    if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                         val = self.df_all.loc[code].get('Rank', 0)
                         rank = int(val) if pd.notna(val) else 0
                    lbl = tk.Label(scroll_frame, text=f"  {code} {name} R:{rank:<4} {percent:>6.2f}% {volume}",
                                   fg="gray", cursor="hand2", anchor="w",takefocus=True)    # 猸?蹇呴』
                    lbl.pack(anchor="w", padx=6)
                    lbl._code = code
                    lbl._concept = c
                    idx = len(self._label_widgets)
                    lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                    lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                    lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))
                    self._label_widgets.append(lbl)

        # --- 榛樿閫変腑绗竴鏉?---
        if self._label_widgets:
            self._selected_index = 0
            self._label_widgets[0].configure(bg="lightblue")

        # --- 婊氬姩鍒伴《閮?---
        canvas.yview_moveto(0)

        # --- 鏇存柊鐘舵€?---
        self._prev_categories = list(current_categories)



    # --- 绫诲唴閮ㄦ柟娉曪細閫夋嫨鍜岀偣鍑?---
    def _update_selection(self, idx):
        """鏇存柊閫変腑楂樹寒骞舵粴鍔?""
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

            # 婊氬姩 Canvas 浣垮綋鍓?Label 鍙
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
        """鐐瑰嚮鏍囩浜嬩欢"""
        self._update_selection(idx)
        self.on_code_click(code)
        # 纭繚閿洏浜嬩欢浠嶇粦瀹氭湁鏁?
        if hasattr(self._concept_win, "_canvas"):
            canvas = self._concept_win._canvas
            yview = canvas.yview()  # 淇濆瓨褰撳墠婊氬姩鏉′綅缃?            self._concept_win._canvas.focus_set()
            canvas.yview_moveto(yview[0])  # 鎭㈠鍘熶綅缃?
    def on_right_click_search_var2(self,event):
        try:
            # 鑾峰彇鍓创鏉垮唴瀹?            clipboard_text = event.widget.clipboard_get()
        except tk.TclError:
            return
        # 鎻掑叆鍒板厜鏍囦綅缃?        # event.widget.insert(tk.INSERT, clipboard_text)
        # 鍏堟竻绌哄啀榛忚创
        if clipboard_text.isdigit() and len(clipboard_text) == 6:
            clipboard_text = f'index.str.contains("^{clipboard_text}")'
        else:
            allowed = r'\-\(\)'
            pattern = rf'[\u4e00-\u9fa5]+[A-Za-z0-9{allowed}锛堬級]*'
            matches = re.findall(r'[\u4e00-\u9fa5]+[A-Za-z0-9\-\(\)锛堬級]*', clipboard_text)
            if matches:
                clipboard_text = f'category.str.contains("^{matches[0]}")'

        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)

    def on_right_click_search_var4(self, event):
        """search_var4 鐨勫彸閿揩鎹烽敭锛岄€昏緫鍚?var2"""
        self.on_right_click_search_var2(event)


    def _on_label_on_code_click(self, code,idx):
        self._update_selection_top10(idx)
        """鐐瑰嚮寮傚姩绐楀彛涓殑鑲＄エ浠ｇ爜"""
        self.select_code = code

        # 鉁?鍙敼涓烘墦寮€璇︽儏閫昏緫锛屾瘮濡傦細
        self.sender.send(code)
        # Auto-launch Visualizer if enabled
        if hasattr(self, 'vis_var') and self.vis_var.get() and code:
            self.open_visualizer(code)
        if hasattr(self._concept_top10_win, "_canvas_top10"):
            canvas = self._concept_top10_win._canvas_top10
            yview = canvas.yview()  # 淇濆瓨褰撳墠婊氬姩鏉′綅缃?            self._concept_top10_win._canvas_top10.focus_set()
            canvas.yview_moveto(yview[0])  # 鎭㈠鍘熶綅缃?

    def _on_key_top10(self, event):
        """閿洏涓婁笅/鍒嗛〉婊氬姩锛堜粎Top10绐楀彛鐢級"""
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

        # 鐐瑰嚮琛屼负锛堝彲澶嶇敤 on_code_click锛?        lbl = self._top10_label_widgets[idx]
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
            # 濡傛灉鍙戦€佹垚鍔燂紝鏇存柊鐘舵€佹爣绛?            self.status_var2.set(f"鍙戦€佹垚鍔? {stock_code}")
        else:
            # 濡傛灉鍙戦€佸け璐ワ紝鏇存柊鐘舵€佹爣绛?            self.status_var2.set(f"鍙戦€佸け璐? {stock_code}")

        self.tree_scroll_to_code(code)

    def _on_label_double_click_top10(self, code, idx):
        """
        鍙屽嚮鑲＄エ鏍囩鏃讹紝鏄剧ず璇ヨ偂绁ㄦ墍灞炴蹇佃鎯呫€?        濡傛灉 _label_widgets 涓嶅瓨鍦ㄦ垨 concept_name 鑾峰彇澶辫触锛?        鍒欒嚜鍔ㄤ娇鐢?code 璁＄畻璇ヨ偂绁ㄦ墍灞炲己鍔挎蹇靛苟鏄剧ず璇︽儏銆?        """
        try:
            # ---------------- 鍘熼€昏緫 ----------------
            concept_name = None

            # ---------------- 鍥為€€閫昏緫 ----------------
            if not concept_name:
                # logger.info(f"[Info] 鏈粠 _label_widgets 鑾峰彇鍒版蹇碉紝灏濊瘯閫氳繃 {code} 鑷姩璇嗗埆寮哄娍姒傚康銆?)
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"鑷姩璇嗗埆寮哄娍姒傚康锛歿concept_name}")
                    else:
                        messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                        return
                except Exception as e:
                    logger.info(f"[Error] 鍥為€€鑾峰彇姒傚康澶辫触锛歿e}")
                    traceback.print_exc()
                    messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                    return

            # ---------------- 缁樺浘閫昏緫 ----------------
            self.plot_following_concepts_pg(code,top_n=1)

            # ---------------- 鎵撳紑/澶嶇敤 Top10 绐楀彛 ----------------
            self.show_concept_top10_window_simple(concept_name,code=code)

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 鏇存柊鏍囬 ---
                win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)

                # --- 妫€鏌ョ獥鍙ｇ姸鎬?---
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
                    logger.info(f"绐楀彛鐘舵€佹鏌ュけ璐ワ細{e}")

                # --- 鎭㈠ Canvas 婊氬姩浣嶇疆 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

        except Exception as e:
            logger.info(f"鑾峰彇姒傚康璇︽儏澶辫触锛歿e}")
            traceback.print_exc()

    def _update_selection_top10(self, idx):
        """鏇存柊 Top10 绐楀彛閫変腑楂樹寒骞舵粴鍔?""
        if not hasattr(self, "_concept_top10_win") or not self._concept_top10_win:
            return

        win = self._concept_top10_win
        canvas = win._canvas_top10
        scroll_frame = win._content_frame_top10

        normal_bg = win.cget("bg")
        highlight_bg = "lightblue"

        # 娓呴櫎鎵€鏈夐珮浜?        for rf in self._top10_label_widgets:
            if isinstance(rf, list):
                for ch in rf:
                    ch.configure(bg=normal_bg)
            else:
                for ch in rf.winfo_children():
                    ch.configure(bg=normal_bg)

        # 楂樹寒閫変腑
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

            # 婊氬姩 Canvas 浣垮綋鍓?Label 鍙
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

            # 鍙戦€佹秷鎭?            self.sender.send(code)
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                self.open_visualizer(code)

    def _bind_copy_expr(self, win):
        """缁戝畾鎴栭噸鏂扮粦瀹氬鍒惰〃杈惧紡鎸夐挳"""
        btn_frame = getattr(win, "_btn_frame", None)
        if btn_frame is None: return
        # 閿€姣佹棫鎸夐挳
        if hasattr(win, "_btn_copy_expr") and win._btn_copy_expr.winfo_exists():
            win._btn_copy_expr.destroy()
        def _copy_expr():
            concept = getattr(win, "_concept_name","鏈煡姒傚康")
            # q = f'category.str.contains("{concept}", na=False)'
            q = concept
            pyperclip.copy(q)
            self.after(100, lambda: toast_message(self,f"宸插鍒剁瓫閫夋潯浠讹細{q}"))
        btn = tk.Button(btn_frame, text="澶嶅埗", command=_copy_expr)
        btn.pack(side="left", padx=4)
        win._btn_copy_expr = btn

   
    def show_concept_top10_window_simple(self, concept_name, code=None, auto_update=True, interval=30,stock_name=None,focus_force=False):
        """
        鏄剧ず鎸囧畾姒傚康鐨勫墠10鏀鹃噺涓婃定鑲★紝涓嶅鐢ㄥ凡鏈夌獥鍙ｏ紝绠€鍗曠嫭绔嬪垱寤?        鍙傛暟锛?            concept_name: 姒傚康鍚嶇О
            code: 鑲＄エ浠ｇ爜锛屽彲閫?            auto_update: 鏄惁鑷姩鍒锋柊
            interval: 鍒锋柊闂撮殧锛堢锛?            stock_name: 鑲＄エ鍚嶇О锛堝彲閫夛級
        """

        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            toast_message(self, "df_all 鏁版嵁涓虹┖锛屾棤娉曠瓫閫夋蹇佃偂绁?)
            return

        try:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        except Exception as e:
            toast_message(self, f"绛涢€夎〃杈惧紡閿欒: {e}")
            return

        if df_concept.empty:
            toast_message(self, f"姒傚康銆恵concept_name}銆戞殏鏃犲尮閰嶈偂绁?)
            return

        if not hasattr(self, "_pg_top10_window_simple"):
            self._pg_top10_window_simple = {}

        unique_code = f"{concept_name or ''}_"
        # --- 妫€鏌ユ槸鍚﹀凡鏈夌浉鍚?code 鐨勭獥鍙?---
        for k, v in self._pg_top10_window_simple.items():
            if v.get("code") == unique_code and v.get("win") is not None and v.get("win").winfo_exists():
                # 宸插瓨鍦紝鑱氱劍骞舵樉绀篢K
                logger.info(f'宸插瓨鍦紝鑱氱劍骞舵樉绀篢K:{unique_code}')
                v["win"].deiconify()      # 濡傛灉绐楀彛鏈€灏忓寲浜嗭紝鎭㈠
                v["win"].lift()           # 鎻愬埌鏈€鍓?                v["win"].focus_force()    # 鑾峰緱鐒︾偣
                if hasattr(v["win"], "_tree_top10"):
                    v["win"]._tree_top10.selection_set(v["win"]._tree_top10.get_children()[0])  # 閫変腑绗竴琛岋紙鍙€夛級
                    v["win"]._tree_top10.focus_set() # 鑾峰緱鐒︾偣
                v["win"].attributes("-topmost", True)
                v["win"].after(100, lambda: v["win"].attributes("-topmost", False))
                return  # 涓嶅垱寤烘柊绐楀彛

        # --- 鏂扮獥鍙?---
        win = tk.Toplevel(self)
        win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)
        # win.minsize(460, 320)
        real_width = int(saved_width * self.scale_factor)
        real_height = int(saved_height * self.scale_factor)
        win.minsize(real_width, real_height)
        # 缂撳瓨绐楀彛
        # --- 濡傛灉浼犱簡code浣嗘病浼爏tock_name锛屽垯浠巗elf.df_all鏌ユ壘 ---
        if code and not stock_name:
            try:
                if hasattr(self, "df_all") and code in self.df_all.index:
                    stock_name = self.df_all.loc[code, "name"]
                elif hasattr(self, "df_all") and "code" in self.df_all.columns:
                    match = self.df_all[self.df_all["code"].astype(str) == str(code)]
                    if not match.empty:
                        stock_name = match.iloc[0]["name"]
            except Exception as e:
                logger.info(f"鏌ユ壘鑲＄エ鍚嶇О鍑洪敊: {e}")

        # 纭繚鏍煎紡鍖?        code = str(code).zfill(6) if code else ""
        stock_name = stock_name or "鏈懡鍚?

        self._pg_top10_window_simple[unique_code] = {
            "win": win,
            "toplevel": win,
            "code": f"{concept_name or ''}_{code or ''}",
            "stock_info": [ code , stock_name, concept_name]   # 杩欓噷淇濆瓨鑲＄エ璇︾粏淇℃伅
        }

        # 杩欓噷鍙互缁х画濉厖绐楀彛鍐呭

        # 涓讳綋 Treeview
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        columns = ("code", "name", "rank", "percent", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        col_texts = {"code":"浠ｇ爜","name":"鍚嶇О","rank":"Rank","percent":"娑ㄥ箙(%)","volume":"鎴愪氦閲?,"red":"杩為槼","win":"涓诲崌"}
        limit_col = ['volume','red','win']
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            width = 80 if col == ["name","code"] else (30 if col in limit_col else 50)
            tree.column(col, anchor="center", width=width)

        # 淇濆瓨寮曠敤锛岀嫭绔嬬獥鍙ｄ笉澶嶇敤 _concept_top10_win
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="red")        # 娑ㄥ箙鎴栦綆鐐瑰ぇ浜庡墠涓€鏃?        win._tree_top10.tag_configure("orange_row", foreground="orange")  # 楂樹綅鎴栫獊鐮?        win._tree_top10.tag_configure("green_row", foreground="green")    # 璺屽箙鏄庢樉
        win._tree_top10.tag_configure("blue_row", foreground="#555555")      # 寮卞娍鎴栦綆浜庡潎绾夸綆浜?ma5d
        win._tree_top10.tag_configure("purple_row", foreground="purple")  # 鎴愪氦閲忓紓甯哥瓑鐗规畩鎸囨爣
        win._tree_top10.tag_configure("yellow_row", foreground="yellow")  # 涓寸晫鎴栭璀?
        win._concept_name = concept_name
        # 鍦ㄥ垱寤虹獥鍙ｆ椂淇濆瓨瀹氭椂鍣?id
        win._auto_refresh_id = None
        # 鍒濆鍖栫獥鍙ｇ姸鎬侊紙鏀惧湪鍒涘缓 win 鍚庯級
        win._selected_index = 0
        win.select_code = None
        win.is_refreshing = False

        # 浣跨敤 unique_code 鏋勯€犲敮涓€鐨勭獥鍙ｄ繚瀛樺悕
        window_name = f"concept_top10_window-{unique_code}"
        try:
            self.load_window_position(win, window_name, default_width=420, default_height=340)
        except Exception:
            win.geometry("420x340")

        # 榧犳爣婊氳疆鎮仠婊氬姩
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


        # 鍙屽嚮 / 鍙抽敭
        tree.bind("<Double-1>", lambda e: self._on_tree_double_click_newTop10(tree))
        tree.bind("<Button-3>", lambda e: self._on_tree_right_click_newTop10(tree, e))

        self.monitor_windows[unique_code] = {
                'toplevel': win,
                'monitor_tree': tree,
                'stock_info': code  # 鏂板杩欎竴琛?            }
        # -------------------
        # 榧犳爣鐐瑰嚮缁熶竴澶勭悊
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
            # 楂樹寒
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                select_row_by_item(sel[0])

        tree.bind("<<TreeviewSelect>>", on_click)

        # -------------------
        # 閿洏鎿嶄綔
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
            return "break"  # 鉂?闃绘 Treeview 榛樿涓婁笅閿Щ鍔?
        # 缁戝畾閿簨浠跺埌 tree锛堟垨 win锛夛紝纭繚 tree 鏈夌劍鐐?
        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)
        tree.bind("<Prior>", on_key)
        tree.bind("<Next>", on_key)
        tree.bind("<Return>", on_key)
        tree.focus_set()

        # --- 鎸夐挳鍜屾帶鍒舵爮鍖哄煙 ---
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=4)
        win._btn_frame = btn_frame  # 淇濆瓨寮曠敤锛屾柟渚垮鐢?        # --- 鑷姩鏇存柊鎺у埗鏍?---
        ctrl_frame = tk.Frame(btn_frame)
        ctrl_frame.pack(side="left", padx=6)

        chk_auto = tk.BooleanVar(value=True)  # 榛樿寮€鍚嚜鍔ㄦ洿鏂?        chk_btn = tk.Checkbutton(ctrl_frame, text="鑷姩鏇存柊", variable=chk_auto,takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=5,takefocus=False)
        spin_interval.delete(0, "end")
        spin_interval.insert(0, duration_sleep_time)  # 榛樿30绉?        spin_interval.pack(side="left")
        tk.Label(ctrl_frame, text="绉?).pack(side="left")
        spin_interval.configure(takefocus=0)
        chk_btn.configure(takefocus=0)
        # 淇濆瓨寮曠敤鍒扮獥鍙ｏ紝鏂逛究澶嶇敤
        win._chk_auto = chk_auto
        win._spin_interval = spin_interval
        
        # --- 鍦ㄥ垱寤虹獥鍙ｆ垨澶嶇敤绐楀彛鍚庤皟鐢?---
        # self._bind_copy_expr(win)
        def _bind_copy_expr(win):
            """缁戝畾鎴栭噸鏂扮粦瀹氬鍒惰〃杈惧紡鎸夐挳"""
            btn_frame = getattr(win, "_btn_frame", None)
            if btn_frame is None: return
            # 閿€姣佹棫鎸夐挳
            if hasattr(win, "_btn_copy_expr") and win._btn_copy_expr.winfo_exists():
                win._btn_copy_expr.destroy()
            def _copy_expr():
                concept = getattr(win, "_concept_name","鏈煡姒傚康")
                # q = f'category.str.contains("{concept}", na=False)'
                q = concept
                pyperclip.copy(q)
                self.after(100, lambda: toast_message(self,f"宸插鍒剁瓫閫夋潯浠讹細{q}"))
            btn = tk.Button(btn_frame, text="澶嶅埗", command=_copy_expr)
            btn.pack(side="left", padx=4)
            win._btn_copy_expr = btn

        _bind_copy_expr(win)

        # --- 鐘舵€佹爮 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        lbl_status = tk.Label(btn_frame, text=f"鏄剧ず {visible_count}/{total_count} 鍙?, anchor="e",
                              fg="#555", font=self.default_font)
        lbl_status.pack(side="right", padx=8)
        win._status_label_top10 = lbl_status

        def auto_refresh():
            if not win.winfo_exists():
                # 绐楀彛宸茬粡鍏抽棴锛屽彇娑堝畾鏃跺櫒
                if getattr(win, "_auto_refresh_id", None):
                    win.after_cancel(win._auto_refresh_id)
                    win._auto_refresh_id = None
                return

            if chk_auto.get():
                # 浠呭伐浣滄椂闂村埛鏂?                if not cct.get_work_time():
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
                        logger.info(f"[WARN] 鑷姩鍒锋柊澶辫触: {e}")

            # 瀹夊叏鍦伴噸鏂版敞鍐屼笅涓€娆″埛鏂?            win._auto_refresh_id = win.after(int(spin_interval.get()) * 1000, auto_refresh)

        # 鍚姩寰幆
        auto_refresh()

        def _on_close():
            try:
                window_name = f"concept_top10_window-{unique_code}"
                self.save_window_position(win, window_name)
            except Exception:
                pass

            # 鍙栨秷鑷姩鍒锋柊
            if getattr(win, "_auto_refresh_id", None):
                win.after_cancel(win._auto_refresh_id)
                win._auto_refresh_id = None

            unbind_mousewheel()
            # 鉁?瀹夊叏鍒犻櫎 _pg_top10_window_simple 涓搴旈」
            try:
                # 鐢ㄥ瓧鍏告帹瀵兼壘鍒板搴旈敭
                for k, v in list(self._pg_top10_window_simple.items()):
                    if v.get("win") == win:
                        del self._pg_top10_window_simple[k]
                        break
            except Exception as e:
                logger.info(f"娓呯悊 _pg_top10_window_simple 鍑洪敊: {e}")

            win.destroy()
            self._concept_top10_win = None



        win.protocol("WM_DELETE_WINDOW", _on_close)
        win.bind("<Escape>", lambda e: _on_close())  # ESC鍏抽棴绐楀彛
        # 濉厖鏁版嵁
        self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
        if focus_force:
            logger.info(f'宸插瓨鍦紝focus_force鑱氱劍骞舵樉绀篢K:{unique_code}')
            win.transient(self)              # 鍏宠仈涓荤獥鍙ｏ紙闈炲父鍏抽敭锛?            win.attributes("-topmost", True) # 涓存椂缃《
            win.deiconify()                  # 纭繚涓嶆槸鏈€灏忓寲
            win.lift()
            win.focus_force()    # 鑾峰緱鐒︾偣
            if hasattr(win, "tree"):
                tree.selection_set(tree.get_children()[0])  # 閫変腑绗竴琛岋紙鍙€夛級
                tree.focus_set()


            # 寤惰繜婵€娲荤劍鐐癸紙缁曡繃 Windows 闄愬埗锛?            # win.after(50, lambda: (
            #     win._tree_top10.focus_set()   # 鑾峰緱鐒︾偣focus_set(),
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

            # 绛?UI / after / PG timer 鍏ㄩ儴绋冲畾涓嬫潵
            win.after(500, do_focus)
        except Exception as e:
            logger.info(f"鑱氱劍 Top10 Tree 澶辫触: {e}")

    def show_concept_top10_window(self, concept_name, code=None, auto_update=True, interval=30,bring_monitor_status=True):
        """
        鏄剧ず鎸囧畾姒傚康鐨勫墠10鏀鹃噺涓婃定鑲★紙Treeview 楂樻€ц兘鐗堬紝瀹屽叏鏇夸唬 Canvas 鐗堟湰锛?        auto_update: 鏄惁鑷姩鍒锋柊
        interval: 鑷姩鍒锋柊闂撮殧绉?        """
        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            toast_message(self, "df_all 鏁版嵁涓虹┖锛屾棤娉曠瓫閫夋蹇佃偂绁?)
            return

        query_expr = f'category.str.contains("{concept_name}", na=False)'
        try:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        except Exception as e:
            toast_message(self,  f"绛涢€夎〃杈惧紡閿欒: {query_expr}\n{e}")
            return

        if df_concept.empty:
            logger.info(f"姒傚康銆恵concept_name}銆戞殏鏃犲尮閰嶈偂绁?)
            self.after(100, lambda: toast_message(self,f"姒傚康銆恵concept_name}銆戞殏鏃犲尮閰嶈偂绁?))
            return

        # --- 澶嶇敤绐楀彛 ---
        try:
            if getattr(self, "_concept_top10_win", None) and self._concept_top10_win.winfo_exists():
                win = self._concept_top10_win
                win.deiconify()
                win.lift()
                win._concept_name = concept_name  # 鏇存柊姒傚康鍚?                if hasattr(win, "_chk_auto") and hasattr(win, "_spin_interval"):
                    # 澶嶇敤宸叉湁鎺т欢锛屾仮澶嶅€?                    chk_auto = win._chk_auto
                    spin_interval = win._spin_interval
                # 閲嶆柊缁戝畾澶嶅埗鎸夐挳
                # self._bind_copy_expr(win)

                self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
                return

        except Exception:
            self._concept_top10_win = None

        # --- 鏂扮獥鍙?---
        win = tk.Toplevel(self)
        self._concept_top10_win = win
        win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)
        # win.attributes('-toolwindow', True)  # 鍘绘帀鏈€澶у寲/鏈€灏忓寲鎸夐挳锛屽彧鐣欏叧闂寜閽?        win._concept_name = concept_name
        real_width = int(saved_width * self.scale_factor)
        real_height = int(saved_height * self.scale_factor)
        win.minsize(real_width, real_height)
        # win.minsize(460, 320)
        # 鍦ㄥ垱寤虹獥鍙ｆ椂淇濆瓨瀹氭椂鍣?id
        win._auto_refresh_id = None
        # 鍒濆鍖栫獥鍙ｇ姸鎬侊紙鏀惧湪鍒涘缓 win 鍚庯級
        win._selected_index = 0
        win.select_code = None
        win.is_refreshing = False

        try:
            self.load_window_position(win, "concept_top10_window", default_width=520, default_height=420)
        except Exception:
            win.geometry("520x420")

        # --- Treeview 涓讳綋 ---
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        columns = ("code", "name", "rank", "percent", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # col_texts = {"code":"浠ｇ爜","name":"鍚嶇О","percent":"娑ㄥ箙(%)","volume":"鎴愪氦閲?}
        col_texts = {"code":"浠ｇ爜","name":"鍚嶇О","rank":"Rank","percent":"娑ㄥ箙(%)","volume":"鎴愪氦閲?,"red":"杩為槼","win":"涓诲崌"}
        limit_col = ['volume','red','win']
        for col in columns:
            tree.heading(col, text=col_texts[col], anchor="center",
                         command=lambda c=col: self._sort_treeview_column_newTop10(tree, c, False))
            # width = 80 if col == "name" else (40 if col == "rank" else 60)
            width = 80 if col == ["name","code"] else (30 if col in limit_col else 40)
            tree.column(col, anchor="center", width=width)

        # 淇濆瓨寮曠敤
        win._content_frame_top10 = frame
        win._tree_top10 = tree
        win._tree_top10.tag_configure("red_row", foreground="red")        # 娑ㄥ箙鎴栦綆鐐瑰ぇ浜庡墠涓€鏃?        win._tree_top10.tag_configure("orange_row", foreground="orange")  # 楂樹綅鎴栫獊鐮?        win._tree_top10.tag_configure("green_row", foreground="green")    # 璺屽箙鏄庢樉
        win._tree_top10.tag_configure("blue_row", foreground="#555555")      # 寮卞娍鎴栦綆浜庡潎绾夸綆浜?ma5d
        win._tree_top10.tag_configure("purple_row", foreground="purple")  # 鎴愪氦閲忓紓甯哥瓑鐗规畩鎸囨爣
        win._tree_top10.tag_configure("yellow_row", foreground="yellow")  # 涓寸晫鎴栭璀?
        # 榧犳爣婊氳疆鎮仠婊氬姩
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

        # 鍙屽嚮 / 鍙抽敭
        tree.bind("<Double-1>", lambda e: self._on_tree_double_click_newTop10(tree))
        tree.bind("<Button-3>", lambda e: self._on_tree_right_click_newTop10(tree, e))

        # unique_code = f"{code or ''}_{top_n or ''}"
        unique_code = f"{concept_name or ''}_{code or ''}"
        self.monitor_windows[unique_code] = {
                'toplevel': win,
                'monitor_tree': tree,
                'stock_info': code  # 鏂板杩欎竴琛?            }

        # -------------------
        # 榧犳爣鐐瑰嚮缁熶竴澶勭悊
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
            # 楂樹寒
            self._highlight_tree_selection(tree, item)

        def on_click(event):
            if win.is_refreshing:
                return
            sel = tree.selection()
            if sel:
                select_row_by_item(sel[0])

        tree.bind("<<TreeviewSelect>>", on_click)

        # -------------------
        # 閿洏鎿嶄綔
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

            return "break"  # 鉂?闃绘 Treeview 榛樿涓婁笅閿Щ鍔?

        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)
        tree.bind("<Prior>", on_key)
        tree.bind("<Next>", on_key)
        tree.bind("<Return>", on_key)
        tree.bind("<FocusIn>", lambda e: tree.focus_set())
        # tree.focus_set()

        # --- 鎸夐挳鍜屾帶鍒舵爮鍖哄煙 ---
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill="x", pady=4)
        win._btn_frame = btn_frame  # 淇濆瓨寮曠敤锛屾柟渚垮鐢?        # --- 鑷姩鏇存柊鎺у埗鏍?---
        ctrl_frame = tk.Frame(btn_frame)
        ctrl_frame.pack(side="left", padx=6)

        chk_auto = tk.BooleanVar(value=True)  # 榛樿寮€鍚嚜鍔ㄦ洿鏂?        chk_btn = tk.Checkbutton(ctrl_frame, text="鑷姩鏇存柊", variable=chk_auto,takefocus=False)
        chk_btn.pack(side="left")

        spin_interval = tk.Spinbox(ctrl_frame, from_=5, to=300, width=5,takefocus=False)
        spin_interval.delete(0, "end")
        spin_interval.insert(0, duration_sleep_time)  # 榛樿30绉?        spin_interval.pack(side="left")
        tk.Label(ctrl_frame, text="绉?).pack(side="left")
        spin_interval.configure(takefocus=0)
        chk_btn.configure(takefocus=0)
        # 淇濆瓨寮曠敤鍒扮獥鍙ｏ紝鏂逛究澶嶇敤
        win._chk_auto = chk_auto
        win._spin_interval = spin_interval
        # # --- 澶嶅埗琛ㄨ揪寮忔寜閽?---
        # --- 鍦ㄥ垱寤虹獥鍙ｆ垨澶嶇敤绐楀彛鍚庤皟鐢?---
        self._bind_copy_expr(win)

        # --- 鐘舵€佹爮 ---
        visible_count = len(df_concept[df_concept["percent"] > 2])
        total_count = len(df_concept)
        lbl_status = tk.Label(btn_frame, text=f"鏄剧ず {visible_count}/{total_count} 鍙?, anchor="e",
                              fg="#555", font=self.default_font)
        lbl_status.pack(side="right", padx=8)
        win._status_label_top10 = lbl_status

        def auto_refresh():
            if not win.winfo_exists():
                # 绐楀彛宸茬粡鍏抽棴锛屽彇娑堝畾鏃跺櫒
                if getattr(win, "_auto_refresh_id", None):
                    win.after_cancel(win._auto_refresh_id)
                    win._auto_refresh_id = None
                return

            if chk_auto.get():
                # 浠呭伐浣滄椂闂村埛鏂?                if not cct.get_work_time():
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
                        logger.info(f"[WARN] 鑷姩鍒锋柊澶辫触: {e}")

            # 瀹夊叏鍦伴噸鏂版敞鍐屼笅涓€娆″埛鏂?            win._auto_refresh_id = win.after(int(spin_interval.get()) * 1000, auto_refresh)

        # 鍚姩寰幆
        auto_refresh()


        def _on_close():
            try:
                self.save_window_position(win, "concept_top10_window")
            except Exception:
                pass

            # 鍙栨秷鑷姩鍒锋柊
            if getattr(win, "_auto_refresh_id", None):
                win.after_cancel(win._auto_refresh_id)
                win._auto_refresh_id = None

            unbind_mousewheel()
            win.destroy()
            self._concept_top10_win = None
        def window_focus_bring_monitor_status(win):
            if bring_monitor_status:
                self.on_monitor_window_focus(win)
                # win.lift()           # 鎻愬墠鏄剧ず
                # win.focus_force()    # 鑱氱劍
                # win.attributes("-topmost", True)
                # win.after(100, lambda: win.attributes("-topmost", False))
        
        win.bind("<Button-1>", lambda e, w=win: window_focus_bring_monitor_status(w))
        win.protocol("WM_DELETE_WINDOW", _on_close)
        # 濉厖鏁版嵁
        self._fill_concept_top10_content(win, concept_name, df_concept, code=code)
        # 绐楀彛宸插垱寤?/ 宸插鐢?        self._focus_top10_tree(win)

    def _call_concept_top10_win_no_focus(self, code, concept_name):
        """
        [FIX] 鎵撳紑鎴栧鐢?Top10 绐楀彛锛屼絾涓嶅己鍒跺ず鍙栫劍鐐广€?        渚?Qt 绾跨▼閫氳繃闃熷垪璋冪敤锛岄伩鍏嶆姠鍗?Qt 绐楀彛鐒︾偣銆?        """
        if code is None:
            return
        
        # 鍐呴儴浼氳皟鐢?deiconify / lift, 浣嗘垜浠敖閲忎笉鍐嶉澶?force_focus
        self.show_concept_top10_window(concept_name, code=code, bring_monitor_status=False)
        
        if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
            win = self._concept_top10_win
            
            # --- 鏇存柊鏍囬 ---
            try:
                win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)
            except:
                pass

            # --- 浠呭仛鏈€灏忓寲鎭㈠锛屼笉寮哄埗缃《/鑱氱劍 ---
            try:
                if win.state() == "iconic":
                    win.deiconify()
                # [REMOVED] win.lift(), win.focus_force(), win.attributes("-topmost")
            except Exception as e:
                logger.info(f"绐楀彛鐘舵€佹鏌ュけ璐?no_focus)锛?{e}")

            # --- 鎭㈠ Canvas 婊氬姩浣嶇疆 (涓嶈皟鐢?focus_set) ---
            if hasattr(win, "_canvas_top10"):
                try:
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    # [REMOVED] canvas.focus_set()
                    canvas.yview_moveto(yview[0])
                except:
                    pass

    def update_all_top10_windows(self):
        """寮哄埗鍒锋柊鎵€鏈夊綋鍓嶆墦寮€鐨?Concept Top10 绐楀彛鏁版嵁"""
        # 1. 鍒锋柊鐙珛绐楀彛瀛楀吀
        if hasattr(self, "_pg_top10_window_simple"):
            for k, v in list(self._pg_top10_window_simple.items()):
                win = v.get("win")
                if win and win.winfo_exists():
                    concept_name = getattr(win, "_concept_name", None)
                    if concept_name:
                        self._fill_concept_top10_content(win, concept_name)

        # 2. 鍒锋柊澶嶇敤绐楀彛
        if hasattr(self, "_concept_top10_win") and self._concept_top10_win and self._concept_top10_win.winfo_exists():
            concept_name = getattr(self._concept_top10_win, "_concept_name", None)
            if concept_name:
                self._fill_concept_top10_content(self._concept_top10_win, concept_name)

    def _fill_concept_top10_content(self, win, concept_name, df_concept=None, code=None, limit=50):
        """
        濉厖姒傚康Top10鍐呭鍒癟reeview锛堟敮鎸佸疄鏃跺埛鏂帮級銆?        - df_concept: 鍙€夛紝鑻ヤ负 None 鍒欎粠 self.df_all 鑾峰彇
        - code: 鎵撳紑绐楀彛鎴栧埛鏂版椂浼樺厛閫変腑鐨勮偂绁?code
        - limit: 鏄剧ず鍓?N 鏉?        """
        tree = win._tree_top10

        # # 鉁?鍏堢‘淇?tag 閰嶇疆鍙仛涓€娆?        # if not getattr(tree, "_tag_inited", False):
        #     tree.tag_configure("red_row", foreground="red")        # 娑ㄥ箙鎴栦綆鐐瑰ぇ浜庡墠涓€鏃?        #     tree.tag_configure("green_row", foreground="green")    # 璺屽箙鏄庢樉
        #     tree.tag_configure("orange_row", foreground="orange")  # 楂樹綅鎴栫獊鐮?        #     #tree.tag_configure("blue_row", foreground="#555555")    # 鐏拌壊寮卞娍鎴栦綆浜庡潎绾? 鈥減urple鈥濈传鑹层€佲€渕agenta鈥濆搧绾?娲嬬孩 娣辩伆锛?555555锛?        #     #tree.tag_configure("purple_row", foreground="purple")  # 寮卞娍 / 浣庝簬 ma5d
        #     tree.tag_configure("purple_row", foreground="purple")  # 鎴愪氦閲忓紓甯哥瓑鐗规畩鎸囨爣
        #     tree.tag_configure("yellow_row", foreground="yellow")  # 涓寸晫鎴栭璀︿复鐣?/ 浣庝簬 ma20d
        #     tree._tag_inited = True


        # 娓呯┖鏃ц
        tree.delete(*tree.get_children())

        # 濡傛灉 df_concept 涓?None锛屽垯浠?self.df_all 鍔ㄦ€佽幏鍙?        if df_concept is None:
            df_concept = self.df_all[self.df_all['category'].str.contains(concept_name.split('(')[0], na=False)]
        if df_concept.empty:
            return

        # 鎺掑簭鐘舵€?        win._top10_sort_state = getattr(win, "_top10_sort_state", {"col": "percent", "asc": False})
        sort_col = win._top10_sort_state["col"]
        ascending = win._top10_sort_state["asc"]
        if sort_col in df_concept.columns:
            df_concept = df_concept.sort_values(sort_col, ascending=ascending)

        # 闄愬埗鏄剧ず鍓?N 鏉?        df_display = df_concept.head(limit).copy()
        tree._full_df = df_concept.copy()
        tree._display_limit = limit
        tree.config(height=5)
        # 鎻掑叆 Treeview 骞跺缓绔?code -> iid 鏄犲皠
        code_to_iid = {}
        for idx, (code_row, row) in enumerate(df_display.iterrows()):
            iid = str(idx)
            latest_row = self.df_all.loc[code_row] if code_row in self.df_all.index else row
            percent = latest_row.get("percent")
            # === 琛屾潯浠跺垽鏂?===
            # row_tags = []
            row_tags = get_row_tags(latest_row)

            if pd.isna(percent) or percent == 0:
                percent = latest_row.get("per1d", row.get("per1d", 0))

            rank_val = latest_row.get("Rank", row.get("Rank", 0))
            rank_str = str(int(rank_val)) if pd.notna(rank_val) else "0"

            tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    code_row,
                    latest_row.get("name", row.get("name", "")),
                    rank_str,
                    f"{percent:.2f}",
                    f"{latest_row.get('volume', row.get('volume', 0)):.1f}",
                    latest_row.get("red", row.get("red", 0)),
                    latest_row.get("win", row.get("win", 0)),
                ),
                tags=tuple(row_tags)
            )


            code_to_iid[code_row] = iid

        # --- 鏇存柊鐘舵€佹爮鏁伴噺 ---
        if hasattr(win, "_status_label_top10") and win._status_label_top10.winfo_exists():
            visible_count = len(df_display[df_display["percent"] > 2])
            total_count = len(df_concept)
            win._status_label_top10.config(text=f"鏄剧ず {visible_count}/{total_count} 鍙?)

        # --- 榛樿閫変腑閫昏緫 ---
        children = list(tree.get_children())
        if children:
            # 浼樺厛浣跨敤绐楀彛褰撳墠閫変腑 code锛屽叾娆′娇鐢ㄤ紶鍏?code
            target_code = getattr(win, "select_code", None) or code
            target_iid = code_to_iid.get(target_code, children[0])

            tree.selection_set(target_iid)
            tree.focus(target_iid)
            # # 寮哄埗鍒锋柊 Treeview 娓叉煋锛屽啀婊氬姩
            win.update_idletasks()      # 纭繚 Treeview 宸叉覆鏌?            # tree.see(target_iid)

            # 寤惰繜婊氬姩 + 楂樹寒
            # def scroll_and_highlight():
            #     tree.see(target_iid)
            #     self._highlight_tree_selection(tree, target_iid)
            def scroll_and_highlight():
                tree.see(target_iid)
                self._highlight_tree_selection(tree, target_iid)
                # # 楂樹寒鍚庝繚鎸佺孩鑹茶
                # for iid in tree.get_children():
                #     tags = tree.item(iid, "tags")
                #     if "red_row" in tags:
                #         tree.item(iid, tags=tags)  # 寮哄埗鍒锋柊鏍囩


            win.after(50, scroll_and_highlight)
            # 鏇存柊绐楀彛绱㈠紩鍜岄€変腑 code
            win._selected_index = children.index(target_iid)
            win.select_code = tree.item(target_iid, "values")[0]

            # 楂樹寒
            # self._highlight_tree_selection(tree, target_iid)

        # --- 鏇存柊鐘舵€佹爮 ---
        if hasattr(win, "_status_label_top10"):
            visible_count = len(df_display)
            total_count = len(df_concept)
            win._status_label_top10.config(text=f"鏄剧ず {visible_count}/{total_count} 鍙?)
            win._status_label_top10.pack(side="bottom", fill="x", pady=(0, 4))

        win.update_idletasks()


    def _setup_tree_bindings_newTop10(self, tree):
        """
        缁?Treeview 缁戝畾浜嬩欢锛堝崟鍑汇€佸弻鍑汇€佸彸閿€侀敭鐩樹笂涓嬶級
        """
        # 宸﹂敭鍗曞嚮閫変腑琛?        def on_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                tree.focus(item)

        # 鍙屽嚮鎵撳紑
        def on_double_click(event):
            item = tree.focus()
            if item:
                code = tree.item(item, "values")[0]
                self._on_label_double_click_top10(code, int(item))

        # 鍙抽敭鑿滃崟
        def on_right_click(event):
            item = tree.identify_row(event.y)
            if item:
                tree.selection_set(item)
                tree.focus(item)
                code = tree.item(item, "values")[0]
                self._on_label_right_click_top10(code, int(item))

        # 閿洏涓婁笅绉诲姩閫変腑椤?        def on_key(event):
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

        # 缁戝畾浜嬩欢
        tree.bind("<Button-1>", on_click)
        tree.bind("<Double-Button-1>", on_double_click)
        tree.bind("<Button-3>", on_right_click)
        tree.bind("<Up>", on_key)
        tree.bind("<Down>", on_key)

        # 璁?Treeview 鑳借幏寰楃劍鐐癸紙鎸夐敭浜嬩欢鎵嶆湁鏁堬級
        tree.focus_set()
        tree.bind("<FocusIn>", lambda e: tree.focus_set())


    # def _highlight_tree_selection(self, tree, item):
    #     """
    #     Treeview 楂樹寒閫変腑琛岋紙鑳屾櫙钃濊壊锛屽叾浠栨竻闄わ級
    #     """
    #     for iid in tree.get_children():
    #         tree.item(iid, tags=())
    #     tree.item(item, tags=("selected",))
    #     tree.tag_configure("selected", background="#d0e0ff")

    def _highlight_tree_selection(self, tree, item):
        """
        Treeview 楂樹寒閫変腑琛岋紙鑳屾櫙钃濊壊锛屽叾浠栨竻闄わ紝浣嗕繚鐣?red_row锛?        """
        for iid in tree.get_children():
            tags = list(tree.item(iid, "tags"))
            if "selected" in tags:
                tags.remove("selected")  # 绉婚櫎鏃х殑 selected
            tree.item(iid, tags=tuple(tags))

        # 缁欐柊閫変腑琛屾坊鍔?selected
        tags = list(tree.item(item, "tags"))
        if "selected" not in tags:
            tags.append("selected")
        tree.item(item, tags=tuple(tags))

        tree.tag_configure("selected", background="#d0e0ff")


    def _sort_treeview_column_newTop10(self, tree, col, reverse=None):

        if not hasattr(tree, "_full_df") or tree._full_df.empty:
            logger.info("[WARN] Treeview _full_df 涓虹┖")
            return

        # 鍒濆鍖栨帓搴忕姸鎬?        if not hasattr(tree, "_sort_state"):
            tree._sort_state = {}

        # 鍒囨崲鎺掑簭椤哄簭
        if reverse is None:
            reverse = not tree._sort_state.get(col, False)
        tree._sort_state[col] = not reverse

        # map 'rank' to 'Rank' or ensure 'rank' exists for sorting
        if col == "rank":
            if "rank" not in tree._full_df.columns and "Rank" in tree._full_df.columns:
                 tree._full_df["rank"] = tree._full_df["Rank"]
            
            if "rank" in tree._full_df.columns:
                # 纭繚 rank 鍒椾负鏁板€煎瀷锛屼究浜庢纭帓搴?                tree._full_df["rank"] = pd.to_numeric(tree._full_df["rank"], errors='coerce').fillna(9999)
        
        # 鍐嶆妫€鏌ュ垪鏄惁瀛樺湪锛堥槻姝㈠叾浠栧垪鍚嶄笉瀵圭殑鎯呭喌锛?        if col not in tree._full_df.columns:
            logger.warning(f"Sort column '{col}' not found in DataFrame columns: {tree._full_df.columns.tolist()}")
            return

        # 鎺掑簭瀹屾暣鏁版嵁
        df_sorted = tree._full_df.sort_values(col, ascending=not reverse)

        # 璋冭瘯淇℃伅
        # logger.info(f"[DEBUG] Sorting column: {col}, ascending: {not reverse}, total rows: {len(df_sorted)}")

        # 濉厖鍓?limit 鏉?        limit = getattr(tree, "_display_limit", 50)
        df_display = df_sorted.head(limit)
        # logger.info(f"[DEBUG] Displaying top {limit} rows after sort")

        tree.delete(*tree.get_children())
        for idx, (code_row, row) in enumerate(df_display.iterrows()):
            iid = str(code_row)  # 浣跨敤鍘?DataFrame index 鎴栬偂绁?code 淇濊瘉鍞竴
            tags_for_row = get_row_tags(row)  # 鎴?get_row_tags_kline(row, idx)
            percent = row.get("percent")
            if pd.isna(percent) or percent == 0:
                percent = row.get("per1d")

            rank_val = row.get("Rank", 0)
            rank_str = str(int(rank_val)) if pd.notna(rank_val) else "0"

            tree.insert("", "end", iid=iid,
                        values=(code_row, row["name"], rank_str, f"{percent:.2f}", f"{row.get('volume',0):.1f}", f"{row.get('red',0)}", f"{row.get('win',0)}"),tags=tuple(tags_for_row))

        # 淇濈暀閫変腑鐘舵€?        if hasattr(tree, "_selected_index") and tree.get_children():
            sel_iid = str(getattr(tree, "_selected_index", tree.get_children()[0]))
            if sel_iid in tree.get_children():
                tree.selection_set(sel_iid)
                tree.focus(sel_iid)
                tree.see(sel_iid)


        # 鏇存柊heading command
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

        # 娓呴櫎鏃х殑 tag 楂樹寒
        for iid in tree.get_children():
            tree.item(iid, tags=())

        # 璁剧疆閫変腑琛?tag
        tree.item(item, tags=("selected",))
        tree.tag_configure("selected", background="#d0e0ff")

        # 璁剧疆 selection / focus 璁╅敭鐩樹笂涓嬮敭鑳界户缁敤
        tree.selection_set(item)
        tree.focus(item)

        # 鑾峰彇 code 骞舵墽琛岄€昏緫
        code = tree.item(item, "values")[0]
        self._on_label_right_click_top10(code, int(item))

    

    def plot_following_concepts_pg(self, code=None, top_n=10):

        if not hasattr(self, "_pg_windows"):
            self._pg_windows = {}
            self._pg_data_hash = {}

        # --- 鑾峰彇鑲＄エ鏁版嵁 ---
        if code is None or code == "鎬昏":
            tcode, _ = self.get_stock_code_none()
            top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n)
            code = "鎬昏"
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
            logger.info("鏈壘鍒扮浉鍏虫蹇?)
            return

        unique_code = f"{code or ''}_{top_n or ''}"


        # --- 妫€鏌ユ槸鍚﹀凡鏈夌浉鍚?code 鐨勭獥鍙?---
        for k, v in self._pg_windows.items():
            win = v.get("win")
            try:
                if v.get("code") == unique_code and v.get("win") is not None:
                    # 宸插瓨鍦紝鑱氱劍骞舵樉绀?(PyQt)
                    win.show()               # 濡傛灉绐楀彛琚渶灏忓寲鎴栭殣钘?                    win.raise_()             # 鎻愬埌鏈€鍓?                    win.activateWindow()     # 鑾峰緱鐒︾偣
                    return  # 涓嶅垱寤烘柊绐楀彛
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
        # --- 鍒涘缓涓荤獥鍙?---
        win = QtWidgets.QWidget()
        win.setWindowTitle(f"{code} 姒傚康鍒嗘瀽Top{top_n}")
        layout = QtWidgets.QVBoxLayout(win)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.dpi_scale =  1

        # 鎺у埗鏍?        ctrl_layout = QtWidgets.QHBoxLayout()
        chk_auto = QtWidgets.QCheckBox("鑷姩鏇存柊")
        spin_interval = QtWidgets.QSpinBox()
        spin_interval.setRange(5, 300)
        spin_interval.setValue(duration_sleep_time)
        spin_interval.setSuffix(" 绉?)
        ctrl_layout.addWidget(chk_auto)
        ctrl_layout.addWidget(spin_interval)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # 缁樺浘鍖哄煙
        pg_widget = pg.GraphicsLayoutWidget()
        pg_widget.setContentsMargins(0, 0, 0, 0)
        pg_widget.ci.layout.setContentsMargins(0, 0, 0, 0)
        pg_widget.ci.layout.setSpacing(0)
        layout.addWidget(pg_widget)

        plot = pg_widget.addPlot()
        plot.setContentsMargins(0, 0, 0, 0)
        plot.invertY(True)
        plot.setLabel('bottom', '缁煎悎寰楀垎 (score)')
        plot.setLabel('left', '姒傚康')

        y = np.arange(len(concepts))
        color_map = pg.colormap.get('CET-R1')
        brushes = [pg.mkBrush(color_map.map(s)) for s in scores]
        bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
        plot.addItem(bars)


        font = QtWidgets.QApplication.font()
        font_size = font.pointSize()
        self._font_size = font_size
        logger.info(f"concepts_pg 榛樿瀛椾綋澶у皬: {font_size}")

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


        # from PyQt5.QtCore import QPoint
        # 绂佺敤鍙抽敭鑿滃崟
        plot.setMenuEnabled(False)  # 鉁?鍏抽敭
        current_idx = {"value": 0}  # 鐢?dict 淇濇寔鍙彉寮曠敤

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
            """楂樹寒褰撳墠閫変腑鐨?bar锛堝姩鎬佽鍙?plot._data_ref锛?""
            data = plot._data_ref
            concepts = data.get("concepts", [])
            bars = data.get("bars", None)        # 浣犻渶瑕佹妸 BarGraphItem 涔熷瓨鍒?plot._data_ref
            brushes = data.get("brushes", None)  # 鍚岀悊锛屽瓨榛樿棰滆壊鍒楄〃

            if bars is None or brushes is None:
                return
            if not (0 <= index < len(concepts)):
                return

            # 鎭㈠鎵€鏈?bar 鐨?brush
            bars.setOpts(brushes=brushes)

            # 楂樹寒褰撳墠閫変腑椤?            highlight_brushes = brushes.copy()
            highlight_brushes[index] = pg.mkBrush((255, 255, 0, 180))  # 榛勮壊楂樹寒
            bars.setOpts(brushes=highlight_brushes)
            plot.update()

        # --- 榧犳爣鐐瑰嚮浜嬩欢 ---
        def mouse_click(event):
            try:
                if plot.sceneBoundingRect().contains(event.scenePos()):
                    vb = plot.vb
                    mouse_point = vb.mapSceneToView(event.scenePos())
                    idx = int(round(mouse_point.y()))

                    # 鉁?鍔ㄦ€佽鍙栨渶鏂版暟鎹?                    data = plot._data_ref
                    concepts = data.get("concepts", [])
                    # 鑾峰彇 plot 瀵瑰簲鐨勯《灞傜獥鍙?                    # 璋冪敤浣犵殑鑱氱劍鍑芥暟锛屽苟浼犲叆 win
                    unique_code = data.get("code", '')
                    self.tk_dispatch_queue.put(lambda: self.on_monitor_window_focus_pg(unique_code))

                    if 0 <= idx < len(concepts):
                        current_idx["value"] = idx
                        highlight_bar(idx)

                        if event.button() == QtCore.Qt.MouseButton.LeftButton:
                            def _action():
                                # [FIX] 浣跨敤涓嶆姠鐒︾偣鐨勭増鏈?                                self._call_concept_top10_win_no_focus(code, concepts[idx])
                                # 纭繚鍦?Tkinter 鏇存柊鍚庯紝寮哄埗鍞よ捣 Qt 绐楀彛骞惰祴浜堢劍鐐?                                win.raise_()
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
                            QtWidgets.QToolTip.showText(pos_int, f"宸插鍒? {copy_concept_text}", win)
                        # 猸?鏈鐞嗙殑鎸夐敭缁х画鍚戜笅浼犳挱
                        event.ignore()
            except Exception as e:
                logger.exception(f"Fatal Error in mouse_click: {e}")
                import traceback
                traceback.print_exc()

        plot.scene().sigMouseClicked.connect(mouse_click)

        # --- 榧犳爣鎮仠 tooltip ---
        def show_tooltip(event):
            try:
                pos = event
                vb = plot.vb
                if plot.sceneBoundingRect().contains(pos):
                    mouse_point = vb.mapSceneToView(pos)
                    idx = int(round(mouse_point.y()))

                    # 鉁?鍔ㄦ€佽鍙栨渶鏂版暟鎹?                    data = plot._data_ref
                    concepts = data.get("concepts", [])
                    scores = data.get("scores", [])
                    avg_percents = data.get("avg_percents", [])
                    follow_ratios = data.get("follow_ratios", [])

                    if 0 <= idx < len(concepts):
                        msg = (f"姒傚康: {concepts[idx]}\n"
                               f"骞冲潎娑ㄥ箙: {avg_percents[idx]:.2f}%\n"
                               f"璺熼殢鎸囨暟: {follow_ratios[idx]:.2f}\n"
                               f"缁煎悎寰楀垎: {scores[idx]:.2f}")
                        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), msg, win)
            except Exception as e:
                pass


        plot.scene().sigMouseMoved.connect(show_tooltip)

        # --- 閿洏浜嬩欢 ---
        # 蹇呴』鏄惧紡璁剧疆 FocusPolicy 鎵嶈兘鎺ユ敹閿洏浜嬩欢
        win.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        
        def key_event(event):
            try:
                key = event.key()
                data = plot._data_ref  # 鉁?鍔ㄦ€佽鍙栨渶鏂版暟鎹?                concepts = data.get("concepts", [])
                
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
                        # [FIX] 浣跨敤涓嶆姠鐒︾偣鐨勭増鏈?                        self._call_concept_top10_win_no_focus(code, concepts[current_idx["value"]])
                        win.raise_()
                        win.activateWindow()
                        win.setFocus()
                    self.tk_dispatch_queue.put(_key_action_up)
                    event.accept()

                elif key == QtCore.Qt.Key.Key_Down:
                    current_idx["value"] = min(len(concepts) - 1, current_idx["value"] + 1)
                    highlight_bar(current_idx["value"])
                    def _key_action_down():
                        # [FIX] 浣跨敤涓嶆姠鐒︾偣鐨勭増鏈?                        self._call_concept_top10_win_no_focus(code, concepts[current_idx["value"]])
                        win.raise_()
                        win.activateWindow()
                        win.setFocus()
                    self.tk_dispatch_queue.put(_key_action_down)
                    event.accept()

                elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    idx = current_idx["value"]
                    if 0 <= idx < len(concepts):
                        # [FIX] 浣跨敤闃熷垪澶勭悊 Enter 閿紝淇濇寔 focus 鍦?Qt 绐楀彛
                        def _key_action_enter():
                             self._call_concept_top10_win_no_focus(code, concepts[idx])
                             win.raise_()
                             win.activateWindow()
                             win.setFocus()
                        self.tk_dispatch_queue.put(_key_action_enter)
                    event.accept()
                # 猸?鏈鐞嗙殑鎸夐敭缁х画鍚戜笅浼犳挱
                event.ignore()
            except Exception as e:
                logger.exception(f"Fatal Error in key_event: {e}")
                import traceback
                traceback.print_exc()

        win.keyPressEvent = key_event

        # --- 灞忓箷/DPI 鍒囨崲閲嶅畾浣嶆枃鏈?---
        def reposition_texts1():
            app_font = QtWidgets.QApplication.font()
            family = app_font.family()
            logger.info(f"reposition_texts 榛樿瀛椾綋澶у皬: {self._font_size}")
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
                # 骞冲潎娑ㄥ箙绠ご
                diff_avg = avg - prev_data["avg_percents"][i] if i < len(prev_data["avg_percents"]) else avg
                arrow_avg = "鈫? if diff_avg > 0 else ("鈫? if diff_avg < 0 else "鈫?)

                # 缁煎悎寰楀垎绠ご
                diff_score = score - prev_data["scores"][i] if i < len(prev_data["scores"]) else score
                arrow_score = "鈫? if diff_score > 0 else ("鈫? if diff_score < 0 else "鈫?)

                # 鏇存柊鏂囧瓧鍐呭
                text.setText(f"avg:{arrow_avg} {avg:.2f}%\nscore:{arrow_score} {score:.2f}")

                # 鉁?瀹夊叏鍦拌缃瓧浣撳ぇ灏忥紙涓嶈皟鐢?text.font()锛?                text.setFont(QtGui.QFont("Microsoft YaHei", self._font_size))

                # 鏇存柊鍧愭爣
                x = (scores[i] + 0.03 * max_score) * self.dpi_scale
                y_pos = y[i] * self.dpi_scale
                text.setPos(x, y_pos)
                # 璁剧疆浣嶇疆
                # text.setPos(score + 0.03 * max_score, y[i])
                text.setAnchor((0, 0.5))  # 鍨傜洿灞呬腑
            plot.update()

        # 瀹氭椂杞 DPI / 灞忓箷鍙樺寲
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

        # 鍏抽棴浜嬩欢
        def on_close(evt):
            timer.stop()
            # 閬嶅巻绐楀彛娑夊強鐨?concept锛屽彧淇濆瓨鑷繁鎷ユ湁鐨勬蹇垫暟鎹?
            for concept_name in concepts:
                base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
                prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)
                if base_data or prev_data:
                    save_concept_pg_data(win, concept_name)  # 宸叉敼鍐欎负瀹夊叏鍗曟蹇典繚瀛?
            self.save_window_position_qt(win, f"姒傚康鍒嗘瀽Top{top_n}")
            self._pg_windows.pop(unique_code, None)
            self._pg_data_hash.pop(code, None)
            evt.accept()


        win.closeEvent = on_close

        
        self._pg_data_hash[code] = data_hash

        self.load_window_position_qt(win, f"姒傚康鍒嗘瀽Top{top_n}")

        win.show()


        # --- 鍒濆鍖栧 concept 鏁版嵁瀹瑰櫒 ---
        if not hasattr(win, "_init_prev_concepts_data"):
            win._init_prev_concepts_data = {}  # 姣忎釜 concept_name 瀵瑰簲鍒濆鏁版嵁
        if not hasattr(win, "_prev_concepts_data"):
            win._prev_concepts_data = {}       # 姣忎釜 concept_name 瀵瑰簲涓婃鍒锋柊鏁版嵁

        # # --- 绐楀彛鍒濆鍖栧悇鑷?concept 鏁版嵁 ---
        for i, c_name in enumerate(concepts):
            # 鍒濆鍖?base_data
            if c_name not in win._init_prev_concepts_data:
                base_data = self._global_concept_init_data.get(c_name)
                if base_data is None:
                    # 鍏ㄥ眬娌℃湁鏁版嵁锛屽垵濮嬪寲鍩虹鏁版嵁
                    base_data = {
                        "concepts": [c_name],
                        "avg_percents": np.array([avg_percents[i]]),
                        "scores": np.array([scores[i]]),
                        "follow_ratios": np.array([follow_ratios[i]])
                    }
                    self._global_concept_init_data[c_name] = base_data
                win._init_prev_concepts_data[c_name] = base_data
                # logger.info("[DEBUG] 宸插垵濮嬫蹇垫暟鎹?_init_prev_concepts_data)")
            # 鍒濆鍖?prev_data
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

        # 鑷姩鍒锋柊
        timer = QtCore.QTimer(win)
        timer.timeout.connect(lambda: self._refresh_pg_window(code, top_n))

        # 缂撳瓨绐楀彛
        self._pg_windows[unique_code] = {
            "win": win, "plot": plot, "bars": bars, "texts": texts, "code" : unique_code,
            "timer": timer, "chk_auto": chk_auto, "spin": spin_interval, "_concepts": concepts
        } 
            # "_scores" : scores,"_avg_percents" :avg_percents ,"_follow_ratios" : follow_ratios

        # if code == "鎬昏" and name == "All":
        chk_auto.setChecked(True)
        timer.start(spin_interval.value() * 1000)
        chk_auto.toggled.connect(lambda state: timer.start(spin_interval.value() * 1000) if state else timer.stop())
        spin_interval.valueChanged.connect(lambda v: timer.start(v * 1000) if chk_auto.isChecked() else None)


    def update_pg_plot(self, w_dict, concepts, scores, avg_percents, follow_ratios):
        """
        鏇存柊 PyQtGraph 鏉″舰鍥剧獥鍙ｏ紙NoSQL 澶?concept 鐗堟湰锛夛紝淇濊瘉鎺掑簭瀵归綈锛?        1. 姣忎釜 concept 鐙珛淇濆瓨鍒濆鍒嗘暟鍜屼笂娆″埛鏂板垎鏁般€?        2. 缁樺埗涓?BarGraphItem 鏄剧ず褰撳墠鍒嗘暟銆?        3. 缁樺埗澧為噺鏉★紙鐩稿浜庡垵濮嬪垎鏁帮級銆?        4. 澧為噺鏉℃澧為噺缁胯壊锛岃礋澧為噺绾㈣壊锛屾枃瀛楃澶存樉绀烘柟鍚戙€?        5. 鏀寔澧為噺鏉￠棯鐑併€?        6. 鑷姩鎭㈠褰撳ぉ宸叉湁鏁版嵁锛圢oSQL 瀛樺偍锛夈€?        """
        try:

            # === 馃З 璋冭瘯淇℃伅 ===
            def quick_hash(arr):
                try:
                    if isinstance(arr, (list, tuple, np.ndarray)):
                        s = ",".join(map(str, arr[:10]))
                        return hashlib.md5(s.encode()).hexdigest()[:8]
                    return str(type(arr))
                except Exception as e:
                    return f"err:{e}"

            logger.info(
                f"[DEBUG {datetime.now():%H:%M:%S}] update_pg_plot 璋冪敤 "
                f"姒傚康鏁?{len(concepts)} thread={threading.current_thread().name} "
                f"hash_concepts={quick_hash(concepts)} hash_scores={quick_hash(scores)}"
            )

            win = w_dict["win"]
            plot = w_dict["plot"]
            texts = w_dict["texts"]

            now = datetime.now()
            now_t = int(now.strftime("%H%M"))
            today = now.date()

            force_reset = False

            # 妫€鏌ユ槸鍚﹁法澶╋紝璺ㄥぉ灏遍噸缃樁娈垫爣璁?            if getattr(self, "_concept_data_date", None) != today:
                win._concept_data_date = today
                win._concept_first_phase_done = False
                win._concept_second_phase_done = False

            # 绗竴闃舵锛?:15~9:24瑙﹀彂涓€娆?            if cct.get_trade_date_status() and (915 <= now_t <= 924) and not getattr(self, "_concept_first_phase_done", False):
                win._concept_first_phase_done = True
                force_reset = True
                logger.info(f"{today} 瑙﹀彂 9:15~9:24 绗竴闃舵鍒锋柊")

            # 绗簩闃舵锛?:25 鍚庤Е鍙戜竴娆?            elif cct.get_trade_date_status() and (now_t >= 925) and not getattr(self, "_concept_second_phase_done", False):
                win._concept_second_phase_done = True
                force_reset = True
                logger.info(f"{today} 瑙﹀彂 9:25 绗簩闃舵鍏ㄥ眬閲嶇疆")

            # --- 鍒濆鍖栧 concept 鏁版嵁瀹瑰櫒 ---
            if not hasattr(win, "_init_prev_concepts_data") or force_reset:
                win._init_prev_concepts_data = {}
            if not hasattr(win, "_prev_concepts_data") or force_reset:
                win._prev_concepts_data = {}

            # --- 鍏ㄥ眬涓€娆″姞杞藉綋澶╂暟鎹?---
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

            # --- 绐楀彛鍒濆鍖栧悇鑷?concept 鏁版嵁 ---
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

            # --- 妫€鏌ユ槸鍚﹂渶瑕佸埛鏂帮紙鏁版嵁瀹屽叏涓€鑷存椂璺宠繃锛?---
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
                logger.info("[DEBUG] 鏁版嵁鏈彉鍖栵紝璺宠繃鍒锋柊 鉁?)
                return

            y = np.arange(len(concepts))
            max_score = max(scores) if len(scores) > 0 else 1

            # --- 娓呴櫎鏃?BarGraphItem ---
            for item in plot.items[:]:
                if isinstance(item, pg.BarGraphItem):
                    plot.removeItem(item)

            # --- 鎸夋柊椤哄簭鐢熸垚 y 杞?---
            y = np.arange(len(concepts))
            max_score = max(scores) if len(scores) > 0 else 1

            # --- 涓?BarGraphItem锛堜娇鐢ㄦ帓搴忓悗鐨?scores 鍜?y锛?---
            color_map = pg.colormap.get('CET-R1')
            brushes = [pg.mkBrush(color_map.map(s)) for s in scores]
            main_bars = pg.BarGraphItem(x0=np.zeros(len(y)), y=y, height=0.6, width=scores, brushes=brushes)
            plot.addItem(main_bars)
            w_dict["bars"] = main_bars

            # --- 缁樺埗澧為噺鏉?---
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
            # --- 鏇存柊鏂囧瓧鏄剧ず锛堥『搴忎繚鎸佸拰 y 瀵归綈锛?---
            app_font = QtWidgets.QApplication.font()
            font_family = app_font.family()
            for i, text in enumerate(texts):
                score = scores[i]
                delta = score - win._init_prev_concepts_data[concepts[i]]["scores"][0]

                if delta > 0:
                    arrow = "鈫?
                    color = "green"
                elif delta < 0:
                    arrow = "鈫?
                    color = "red"
                else:
                    arrow = "鈫?
                    color = "gray"

                text.setText(f"{arrow}{delta:.1f} score:{score:.2f}\navg:{avg_percents[i]:.2f}%")
                text.setColor(QtGui.QColor(color))
                text.setPos(score + 0.03 * max_score, y[i])
                text.setAnchor((0, 0.5))

            plot.getAxis('left').setTicks([list(zip(y, concepts))])



            plot._data_ref["concepts"] = concepts
            plot._data_ref["scores"] = scores
            plot._data_ref["avg_percents"] = avg_percents
            plot._data_ref["follow_ratios"] = follow_ratios
            plot._data_ref["bars"] = main_bars
            plot._data_ref["brushes"] = brushes


            # --- 淇濆瓨褰撳墠鍒锋柊鏁版嵁 ---
            for i, c_name in enumerate(concepts):
                win._prev_concepts_data[c_name] = {
                    "concepts": [c_name],
                    "avg_percents": np.array([avg_percents[i]]),
                    "scores": np.array([scores[i]]),
                    "follow_ratios": np.array([follow_ratios[i]])
                }

            # --- 澧為噺鏉￠棯鐑?---
            if not hasattr(win, "_flash_timer"):
                win._flash_state = True
                win._flash_timer = QtCore.QTimer(win)

                def flash_delta():
                    for bar in w_dict["delta_bars"]:
                        if bar is not None:
                            bar.setVisible(win._flash_state)
                    win._flash_state = not win._flash_state

                win._flash_timer.timeout.connect(flash_delta)
                win._flash_timer.start(30000)  # 30 绉掗棯鐑佷竴娆?
        except Exception as e:
            logger.exception(f"Fatal Error in update_pg_plot: {e}")
            import traceback
            traceback.print_exc()


    # --- 瀹氭椂鍒锋柊 ---
    def _refresh_pg_window(self, code, top_n):
        try:
            unique_code = f"{code or ''}_{top_n or ''}"
            if unique_code not in self._pg_windows:
                return
            if not cct.get_work_time():  # 浠呭伐浣滄椂闂村埛鏂?                return

            logger.info(f'unique_code : {unique_code}')
            w_dict = self._pg_windows[unique_code]
            win = w_dict["win"]

            # --- 鑾峰彇鏈€鏂版蹇垫暟鎹?---
            if code == "鎬昏":
                tcode, _ = self.get_stock_code_none()
                top_concepts = self.get_following_concepts_by_correlation(tcode, top_n=top_n)
                unique_code = f"{code or ''}_{top_n or ''}"
                # logger.info(f'_refresh_pg_window concepts : {top_concepts} unique_code: {unique_code} ')
            else:
                top_concepts = self.get_following_concepts_by_correlation(code, top_n=top_n)

            if not top_concepts:
                logger.info(f"[Auto] 鏃犳硶鍒锋柊 {code} 鏁版嵁涓虹┖")
                return

            # --- 瀵规蹇垫寜 score 闄嶅簭鎺掑簭 ---
            top_concepts_sorted = sorted(top_concepts, key=lambda x: x[1], reverse=True)

            concepts = [c[0] for c in top_concepts_sorted]
            scores = np.array([c[1] for c in top_concepts_sorted])
            avg_percents = np.array([c[2] for c in top_concepts_sorted])
            follow_ratios = np.array([c[3] for c in top_concepts_sorted])

            # --- 鍒ゆ柇姒傚康椤哄簭鏄惁鍙樺寲 ---
            old_concepts = w_dict.get("_concepts", [])
            concept_changed = old_concepts != concepts
            # --- 璋冭瘯杈撳嚭 ---
            # logger.info(f'_refresh_pg_window top_concepts_sorted : {top_concepts_sorted} unique_code: {unique_code} ')
            logger.info(f'鏇存柊鍥惧舰: {unique_code} : {concepts}')
            # --- 鏇存柊鍥惧舰 ---
            self.update_pg_plot(w_dict, concepts, scores, avg_percents, follow_ratios)

            logger.info(f"[Auto] 宸茶嚜鍔ㄥ埛鏂?{code}")

        except Exception as e:
            logger.exception(f"Fatal Error in _refresh_pg_window: {e}")
            import traceback
            traceback.print_exc()


    def _call_concept_top10_win(self,code,concept_name):
        # 鎵撳紑鎴栧鐢?Top10 绐楀彛
        if code is None:
            return
        self.show_concept_top10_window(concept_name,code=code,bring_monitor_status=False)
        if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
            win = self._concept_top10_win

            # --- 鏇存柊鏍囬 ---
            win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)

            # --- 妫€鏌ョ獥鍙ｇ姸鎬?---
            try:
                state = win.state()

                # 鏈€灏忓寲鎴栬涓荤獥鍙ｉ伄鎸?                if state == "iconic" or self.is_window_covered_by_main(win):
                    win.deiconify()      # 鎭㈠绐楀彛
                    win.lift()           # 鎻愬墠鏄剧ず
                    win.focus_force()    # 鑱氱劍
                    win.attributes("-topmost", True)
                    win.after(100, lambda: win.attributes("-topmost", False))
                else:
                    # 娌¤閬尅浣嗘湭鑱氱劍
                    if not win.focus_displayof():
                        win.lift()
                        win.focus_force()

            except Exception as e:
                logger.info(f"绐楀彛鐘舵€佹鏌ュけ璐ワ細 {e}")

            # --- 鎭㈠ Canvas 婊氬姩浣嶇疆 ---
            if hasattr(win, "_canvas_top10"):
                canvas = win._canvas_top10
                yview = canvas.yview()
                canvas.focus_set()
                canvas.yview_moveto(yview[0])

    def _on_label_double_click(self, code, idx):
        """
        鍙屽嚮鑲＄エ鏍囩鏃讹紝鏄剧ず璇ヨ偂绁ㄦ墍灞炴蹇佃鎯呫€?        濡傛灉 _label_widgets 涓嶅瓨鍦ㄦ垨 concept_name 鑾峰彇澶辫触锛?        鍒欒嚜鍔ㄤ娇鐢?code 璁＄畻璇ヨ偂绁ㄦ墍灞炲己鍔挎蹇靛苟鏄剧ず璇︽儏銆?        """
        try:

            # ---------------- 鍘熼€昏緫 ----------------
            if hasattr(self, "_label_widgets"):
                try:
                    concept_name = getattr(self._label_widgets[idx], "_concept", None)
                except Exception:
                    concept_name = None

            # ---------------- 鍥為€€閫昏緫 ----------------
            if not concept_name:
                # logger.info(f"[Info] 鏈粠 _label_widgets 鑾峰彇鍒版蹇碉紝灏濊瘯閫氳繃 {code} 鑷姩璇嗗埆寮哄娍姒傚康銆?)
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"鑷姩璇嗗埆寮哄娍姒傚康锛歿concept_name}")
                    else:
                        messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                        return
                except Exception as e:
                    logger.info(f"[Error] 鍥為€€鑾峰彇姒傚康澶辫触锛歿e}")
                    traceback.print_exc()
                    messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                    return

            # ---------------- 缁樺浘閫昏緫 ----------------
            self.plot_following_concepts_pg(code,top_n=1)
            # ---------------- 鎵撳紑/澶嶇敤 Top10 绐楀彛 ----------------
            self.show_concept_top10_window(concept_name,code=code)

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 鏇存柊鏍囬 ---
                win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)

                # --- 妫€鏌ョ獥鍙ｇ姸鎬?---
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
                    logger.info(f"绐楀彛鐘舵€佹鏌ュけ璐ワ細 {e}")

                # --- 鎭㈠ Canvas 婊氬姩浣嶇疆 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

        except Exception as e:
            logger.info(f"鑾峰彇姒傚康璇︽儏澶辫触锛歿e}")
            traceback.print_exc()


    def _on_label_double_click_debug(self, code, idx):
        """
        鍙屽嚮鑲＄エ鏍囩鏃讹紝鏄剧ず璇ヨ偂绁ㄦ墍灞炴蹇佃鎯呫€?        濡傛灉 _label_widgets 涓嶅瓨鍦ㄦ垨 concept_name 鑾峰彇澶辫触锛?        鍒欒嚜鍔ㄤ娇鐢?code 璁＄畻璇ヨ偂绁ㄦ墍灞炲己鍔挎蹇靛苟鏄剧ず璇︽儏銆?        """
        try:
            t0 = time.time()
            concept_name = None

            # ---------------- 鍘熼€昏緫 ----------------
            if hasattr(self, "_label_widgets"):
                t1 = time.time()
                logger.info(f"[DEBUG] 寮€濮嬭闂?_label_widgets锛宭en={len(self._label_widgets)}")
                try:
                    concept_name = getattr(self._label_widgets[idx], "_concept", None)
                except Exception as e:
                    logger.info(f"[DEBUG] 鑾峰彇 _concept 澶辫触 idx={idx}: {e}")
                t2 = time.time()
                logger.info(f"[DEBUG] _label_widgets 璁块棶鑰楁椂: {(t2-t1)*1000:.2f} ms")

            # ---------------- 鍥為€€閫昏緫 ----------------
            if not concept_name:
                t3 = time.time()
                logger.info(f"[DEBUG] 鍥為€€閫昏緫寮€濮嬶紝閫氳繃 code={code} 鑾峰彇姒傚康")
                try:
                    top_concepts = self.get_following_concepts_by_correlation(code, top_n=1)
                    if top_concepts:
                        concept_name = top_concepts[0][0]
                        logger.info(f"[DEBUG] 鑷姩璇嗗埆寮哄娍姒傚康锛歿concept_name}")
                    else:
                        messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                        return
                except Exception as e:
                    logger.info(f"[ERROR] 鍥為€€鑾峰彇姒傚康澶辫触锛歿e}")
                    traceback.print_exc()
                    messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                    return
                t4 = time.time()
                logger.info(f"[DEBUG] 鍥為€€閫昏緫鑰楁椂: {(t4-t3)*1000:.2f} ms")

            # ---------------- 缁樺浘閫昏緫 ----------------
            t5 = time.time()
            self.plot_following_concepts_pg(code, top_n=1)
            t6 = time.time()
            logger.info(f"[DEBUG] 缁樺浘鑰楁椂: {(t6-t5)*1000:.2f} ms")

            # ---------------- 鎵撳紑/澶嶇敤 Top10 绐楀彛 ----------------
            t7 = time.time()
            self.show_concept_top10_window(concept_name,code=code)
            t8 = time.time()
            logger.info(f"[DEBUG] show_concept_top10_window 鑰楁椂: {(t8-t7)*1000:.2f} ms")

            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                win = self._concept_top10_win

                # --- 鏇存柊鏍囬 ---
                win.title(f"{concept_name} 姒傚康鍓?0鏀鹃噺涓婃定鑲?)

                # --- 妫€鏌ョ獥鍙ｇ姸鎬?---
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
                    logger.info(f"绐楀彛鐘舵€佹鏌ュけ璐ワ細{e}")

                # --- 鎭㈠ Canvas 婊氬姩浣嶇疆 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

            t9 = time.time()
            logger.info(f"[DEBUG] _on_label_double_click 鎬昏€楁椂: {(t9-t0)*1000:.2f} ms")

        except Exception as e:
            logger.info(f"鑾峰彇姒傚康璇︽儏澶辫触锛歿e}")
            traceback.print_exc()



    def _on_label_double_click_copy(self, code, idx):
        """
        鍙屽嚮鑲＄エ鏍囩鏃讹紝鏄剧ず璇ヨ偂绁ㄧ殑姒傚康璇︽儏
        """
        try:
            # 鍋囪 self.get_concept_by_code(code) 鍙繑鍥炶鑲＄エ鎵€灞炴蹇靛垪琛?
            # --- 璋冪敤 on_code_click ---
            concepts = getattr(self._label_widgets[idx], "_concept", None)
            # if concepts:
            #     self.on_code_click(code)
            if not concepts:
                messagebox.showinfo("姒傚康璇︽儏", f"{code} 鏆傛棤姒傚康鏁版嵁")
                return

            # text = "\n".join(concepts)
            # text = f'category.str.contains("{concepts.strip()}")'
            text = concepts.strip()
            pyperclip.copy(text)
            logger.info(f"宸插鍒? {text}")
            # messagebox.showinfo("姒傚康璇︽儏", f"{code} 鎵€灞炴蹇碉細\n{text}")
        except Exception as e:
            logger.info(f"鑾峰彇姒傚康璇︽儏澶辫触锛歿e}")


    def _on_label_right_click(self,code ,idx):
        self._update_selection(idx)
        stock_code = code
        pyperclip.copy(code)
        if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
            # 濡傛灉鍙戦€佹垚鍔燂紝鏇存柊鐘舵€佹爣绛?            self.status_var2.set(f"鍙戦€佹垚鍔? {stock_code}")
        else:
            # 濡傛灉鍙戦€佸け璐ワ紝鏇存柊鐘舵€佹爣绛?            self.status_var2.set(f"鍙戦€佸け璐? {stock_code}")
        self.tree_scroll_to_code(code)
        
    def _on_key(self, event):
        """閿洏涓婁笅/鍒嗛〉婊氬姩"""
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
        # --- 璋冪敤 on_code_click ---
        code = getattr(self._label_widgets[idx], "_code", None)
        if code:
            self.on_code_click(code)

    def auto_refresh_detail_window(self):
        # ... 閫昏緫鏇存柊 _last_categories / _last_cat_dict ...
        if getattr(self, "_concept_win", None) and self._concept_win.winfo_exists():
            self.update_concept_detail_content()


    def open_stock_detail(self, code):
        """鐐瑰嚮姒傚康绐楀彛涓偂绁ㄤ唬鐮佸脊鍑鸿鎯?""
        win = tk.Toplevel(self)
        win.title(f"鑲＄エ璇︽儏 - {code}")
        win.geometry("400x300")
        tk.Label(win, text=f"姝ｅ湪鍔犺浇涓偂 {code} ...", font=self.default_font_bold).pack(pady=10)

        # 濡傛灉鏈?df_filtered 鏁版嵁锛屽彲浠ユ樉绀鸿缁嗚鎯?        if hasattr(self, "_last_cat_dict"):
            for c, lst in self._last_cat_dict.items():
                for row_code, name in lst:
                    if row_code == code:
                        tk.Label(win, text=f"{row_code} {name}", font=self.default_font).pack(anchor="w", padx=10)
                        # 鍙互鍔犳洿澶氬瓧娈碉紝濡?trade銆佹定骞呯瓑

    def apply_search(self):
        val1 = self.search_var1.get().strip()
        val2 = self.search_var2.get().strip()
        
        # [MODIFIED] Resolve display labels back to raw queries if maps exist
        if hasattr(self, 'search_map1'):
            val1 = self.search_map1.get(val1, val1)
        if hasattr(self, 'search_map2'):
            val2 = self.search_map2.get(val2, val2)

        # val4 = self.search_var4.get().strip()

        if not val1 and not val2:
            self.status_var.set("鎼滅储妗嗕负绌?)
            return

        self.query_manager.clear_hits()
        
        # 缁勫悎鏌ヨ鏉′欢
        parts = []
        if val1: parts.append(f"({val1})")
        if val2: parts.append(f"({val2})")
        # if val4: parts.append(f"({val4})")
        
        query = " and ".join(parts)
        self._last_value = query

        try:
            # 馃敼 鍚屾鎵€鏈夋悳绱㈡鐨勫巻鍙?            if val1:
                self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")
            if val2:
                self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")
            # if val4:
            #     self.sync_history(val4, self.search_history4, self.search_combo4, "history4", "history4")
        except Exception as ex:
            logger.exception("鏇存柊鎼滅储鍘嗗彶鏃跺嚭閿? %s", ex)

        # ================= 鏁版嵁涓虹┖妫€鏌?=================
        if self.df_all.empty:
            self.status_var.set("褰撳墠鏁版嵁涓虹┖")
            return

        # ====== 鏉′欢娓呯悊 ======
        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2锔忊儯 鏇挎崲鎺夊師 query 涓殑杩欎簺閮ㄥ垎
        for bracket in bracket_patterns:
            query = query.replace(f'and {bracket}', '')

        conditions = [c.strip() for c in query.split('and')]
        # logger.info(f'conditions {conditions}')
        valid_conditions = []
        removed_conditions = []
        for cond in conditions:
            cond_clean = cond.lstrip('(').rstrip(')')
            if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 or cond.find('or') >= 0:
                if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                    ensure_cond = ensure_parentheses_balanced(cond)
                    valid_conditions.append(ensure_cond)
                    continue

            # 鎻愬彇鏉′欢涓殑鍒楀悕
            cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

            # 鎵€鏈夊垪閮藉繀椤诲瓨鍦ㄦ墠淇濈暀
            if all(col in self.df_all.columns for col in cols_in_cond):
                valid_conditions.append(cond_clean)
            else:
                removed_conditions.append(cond_clean)

        # 鍘绘帀鍦?bracket_patterns 涓嚭鐜扮殑鍐呭
        removed_conditions = [
            cond for cond in removed_conditions
            if not any(bp.strip('() ').strip() == cond.strip() for bp in bracket_patterns)
        ]

        # 鎵撳嵃鍓旈櫎鏉′欢鍒楄〃
        if removed_conditions:
            # # logger.info(f"鍓旈櫎涓嶅瓨鍦ㄧ殑鍒楁潯浠? {removed_conditions}")
            unique_conditions = tuple(sorted(set(removed_conditions)))
            # 鍒濆鍖栫紦瀛?            if not hasattr(self, "_printed_removed_conditions"):
                self._printed_removed_conditions = set()
            # 鍙墦鍗版柊鐨?            if unique_conditions not in self._printed_removed_conditions:
                logger.info(f"鍓旈櫎涓嶅瓨鍦ㄧ殑鍒楁潯浠? {unique_conditions}")
                self._printed_removed_conditions.add(unique_conditions)

        if not valid_conditions:
            self.status_var.set("娌℃湁鍙敤鐨勬煡璇㈡潯浠?)
            return
        # logger.info(f'valid_conditions : {valid_conditions}')
        # ====== 鎷兼帴 final_query 骞舵鏌ユ嫭鍙?======
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

        # ====== 鍐冲畾 engine ======
        df_filtered = pd.DataFrame()
        query_engine = 'numexpr'
        # if any('index.' in c.lower() for c in valid_conditions):
        #     query_engine = 'python'
        # 1锔忊儯 index 鏉′欢 鈫?python
        if any('index.' in c.lower() for c in valid_conditions):
            query_engine = 'python'
        
        # 2锔忊儯 瀛楃涓叉潯浠?鈫?绂佹杩?query
        STR_OPS = ('.str.', 'contains(', 'startswith(', 'endswith(')
        has_str_op = any(any(op in c.lower() for op in STR_OPS) for c in valid_conditions)

        if has_str_op:
            query_engine = 'python'   # 鍗充究 python锛屼篃涓嶈兘鏀捐繘 query

        # ====== 鏁版嵁杩囨护 ======
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
                self.status_var.set(f"缁撴灉 {len(df_filtered)}琛?| 鎼滅储: {val1} and {val2}")
            else:
                # 妫€鏌?category 鍒楁槸鍚﹀瓨鍦?                if 'category' in self.df_all.columns:
                    # 寮哄埗杞崲涓哄瓧绗︿覆锛岄伩鍏?str.contains 鎶ラ敊
                    if not pd.api.types.is_string_dtype(self.df_all['category']):
                        self.df_all['category'] = self.df_all['category'].astype('string')
                        # self.df_all['category'] = self.df_all['category'].astype(str).str.strip()
                        # self.df_all['category'] = self.df_all['category'].astype(str)
                        # 鍙€夛細鍘绘帀鍓嶅悗绌烘牸
                        # self.df_all['category'] = self.df_all['category'].str.strip()
                df_filtered = self.df_all.query(final_query, engine=query_engine)

                # 鍋囪 df 鏄綘鎻愪緵鐨勬定骞呮琛ㄦ牸
                # result = counterCategory(df_filtered, 'category', limit=50, table=True)
                # self._Categoryresult = result
                # self.query_manager.entry_query.set(self._Categoryresult)
                self.after(500, lambda: self.refresh_tree(df_filtered, force=True))
                # 鎵撳嵃鍓旈櫎鏉′欢鍒楄〃
                if removed_conditions:
                    # logger.info(f"[鍓旈櫎鐨勬潯浠跺垪琛╙ {removed_conditions}")
                    # 鏄剧ず鍒扮姸鎬佹爮
                    self.status_var2.set(f"宸插墧闄ゆ潯浠? {', '.join(removed_conditions)}")
                    self.status_var.set(f"缁撴灉 {len(df_filtered)}琛?| 鎼滅储: {final_query}")
                else:
                    self.status_var2.set('')
                    self.status_var.set(f"缁撴灉 {len(df_filtered)}琛?| 鎼滅储: {final_query}")
                logger.debug(f'final_query: {final_query}')
        except Exception as e:
            traceback.print_exc()
            logger.error(f"final_query: {final_query} query_check: {([c for c in self.df_all.columns if not c.isidentifier()])}")
            logger.error(f"Query error: {e}")
            self.status_var.set(f"鏌ヨ閿欒: {e}")
        if df_filtered.empty:
            return
        self.on_test_code()
        self.auto_refresh_detail_window()
        self.update_category_result(df_filtered)
        if not hasattr(self, "_start_init_show_concept_detail_window"):
            # 宸茬粡鍒涘缓杩囷紝鐩存帴鏄剧ず
            self.show_concept_detail_window()
            self._start_init_show_concept_detail_window = True

    def on_test_code(self,onclick=False):
        # if self.query_manager.current_key == 'history2':
        #     return
        code = self.query_manager.entry_query.get().strip()
        result = getattr(self, "_Categoryresult", "")
        # if not code:
        #     toast_message(self, "璇疯緭鍏ヨ偂绁ㄤ唬鐮?)
        #     return
        # 鍒ゆ柇鏄惁涓?6 浣嶆暟瀛?        # if not (code.isdigit() and len(code) == 6):

        if code and code == result:
            df_code = self.df_all
        elif code and not (code.isdigit() and len(code) == 6):
            # toast_message(self, "璇疯緭鍏?浣嶆暟瀛楄偂绁ㄤ唬鐮?)
            # return
            df_code = self.df_all
        elif code and code.isdigit() and len(code) == 6:
            # 鍒濆鍖栦笂娆￠€変腑鐨?code
            if not hasattr(self, "_select_on_test_code"):
                self._select_on_test_code = None

            # 鍒ゆ柇鏄惁涓烘柊鐨?code
            if self._select_on_test_code != code:
                # 鏇存柊缂撳瓨锛屽苟绛涢€夊搴旇
                self._select_on_test_code = code
                df_code = self.df_all.loc[self.df_all.index == code]
                results = check_code(self.df_all,code,self.search_var1.get())
            else:
                if onclick:
                    df_code = self.df_all.loc[self.df_all.index == code]
                    results = check_code(self.df_all,code,self.search_var1.get())
                    logger.info(f'check_code: {results}')
                    self.tree_scroll_to_code(code)
                    if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                        self.kline_monitor.tree_scroll_to_code_kline(code)
                # 杩炵画閫夋嫨鐩稿悓 code锛屽垯鏄剧ず鍏ㄩ儴
                else:
                    df_code = self.df_all
        else:
            df_code = self.df_all

        results = self.query_manager.test_code(df_code)

        # 鏇存柊褰撳墠鍘嗗彶鐨勫懡涓粨鏋?        for i, r in enumerate(results):
            if i < len(self.query_manager.current_history):
                self.query_manager.current_history[i]["hit"] = r["hit"]

        self.query_manager.refresh_tree()
        # toast_message(self, f"{code} 娴嬭瘯瀹屾垚锛屽叡 {len(results)} 鏉¤鍒?)



    def clean_search(self, which):
        """娓呯┖鎸囧畾鎼滅储妗嗗唴瀹?(1=bottom, 2=middle/ctrl, 3=history4/ctrl_new)"""
        if which == 1:
            self.search_var1.set("")
        elif which == 2:
            self.search_var2.set("")
        # elif which == 3:
        #     self.search_var4.set("")

        self.select_code = None
        self.sortby_col = None
        self.sortby_col_ascend = None
        self.refresh_tree(self.df_all)
        resample = self.resample_combo.get()
        # self.status_var.set(f"鎼滅储妗?{which} 宸叉竻绌?)
        # self.status_var.set(f"Row 缁撴灉 {len(self.current_df)} 琛?| resample: {resample} ")
        #娓呯┖query_manager-entry_query
        # self.query_manager.entry_query.delete(0, tk.END)

    def delete_search_history(self, which, entry=None):
        """
        鍒犻櫎鎸囧畾鎼滅储妗嗙殑鍘嗗彶鏉＄洰
        which = 1 -> 椤堕儴鎼滅储妗?        which = 2 -> 搴曢儴鎼滅储妗?        entry: 鎸囧畾瑕佸垹闄ょ殑鏉＄洰锛屽鏋滀负绌哄垯鐢ㄦ悳绱㈡褰撳墠鍐呭
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
            self.status_var.set(f"鎼滅储妗?{which} 鍐呭涓虹┖锛屾棤鍙垹闄ら」")
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
            # 浠庝富绐楀彛 history 绉婚櫎
            history.remove(item_to_remove)
            combo['values'] = history
            if var.get() == target:
                var.set("")

            # 浠?QueryHistoryManager 绉婚櫎锛堜繚鐣?note/starred锛?            manager_history = getattr(self.query_manager, key, [])
            manager_history = [r for r in manager_history if r["query"] != target]
            setattr(self.query_manager, key, manager_history)

            # 濡傛灉褰撳墠瑙嗗浘姝ｅ湪鏄剧ず杩欎釜鍘嗗彶锛屽埛鏂?            if self.query_manager.current_key == key:
                self.query_manager.current_history = manager_history
                self.query_manager.refresh_tree()

            # 淇濆瓨
            # self.query_manager.save_search_history()

            self.status_var.set(f"鎼滅储妗?{which} 宸插垹闄ゅ巻鍙? {target}")
        else:
            self.status_var.set(f"鎼滅储妗?{which} 鍘嗗彶涓病鏈? {target}")

    def KLineMonitor_init(self):
        # logger.info("鍚姩K绾跨洃鎺?..")

        # # 浠呭垵濮嬪寲涓€娆＄洃鎺у璞?        # if not hasattr(self, "kline_monitor"):
        #     self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=10)
        # else:
        #     logger.info("鐩戞帶宸插湪杩愯涓€?)
        logger.info("鍚姩K绾跨洃鎺?..")
        if not hasattr(self, "kline_monitor") or not getattr(self.kline_monitor, "winfo_exists", lambda: False)():
            self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=duration_sleep_time,history3=lambda: self.search_history3,logger=logger)
            # self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=15,history3=self.search_history3)
        else:
            logger.info("鐩戞帶宸插湪杩愯涓€?)
            # 鍓嶇疆绐楀彛
            # self.kline_monitor.lift()                # 鎻愬崌绐楀彛灞傜骇
            # self.kline_monitor.attributes('-topmost', True)  # 鏆傛椂缃《
            # self.kline_monitor.focus_force()         # 鑾峰彇鐒︾偣
            # self.kline_monitor.attributes('-topmost', False) # 鍙栨秷缃《

            if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                # 宸茬粡鍒涘缓杩囷紝鐩存帴鏄剧ず
                self.kline_monitor.deiconify()
                self.kline_monitor.lift()
                self.kline_monitor.focus_force()

        # 鍦ㄨ繖閲屽彲浠ュ惎鍔ㄤ綘鐨勫疄鏃剁洃鎺ч€昏緫锛屼緥濡?
        # 1. 璋冪敤鑾峰彇鏁版嵁鐨勭嚎绋?        # 2. 璁＄畻MACD/BOLL/EMA绛夋寚鏍?        # 3. 杈撳嚭涔板崠鐐规彁绀恒€佸己寮变俊鍙?        # 4. 瀹氭湡鍒锋柊UI 鎴?鎺у埗鍙拌緭鍑?    def sort_column_archive_view(self,tree, col, reverse):
        """鏀寔鍒楁帓搴忥紝鍖呮嫭鏃ユ湡瀛楃涓叉帓搴忋€?""
        data = [(tree.set(k, col), k) for k in tree.get_children("")]

        # 鏃堕棿鍒楃壒娈婂鐞?        if col == "time":
            data.sort(key=lambda t: datetime.strptime(t[0], "%Y-%m-%d %H"), reverse=reverse)

        else:
            # 灏濊瘯鏁板瓧鎺掑簭
            try:
                data.sort(key=lambda t: float(t[0]), reverse=reverse)
            except:
                data.sort(key=lambda t: t[0], reverse=reverse)

        # 閲嶆帓
        for index, item in enumerate(data):
            tree.move(item[1], "", index)

        # 涓嬫鐐瑰嚮鍙嶅悜
        tree.heading(col, command=lambda: self.sort_column_archive_view(tree, col, not reverse))

    def load_archive(self,selected_file,readfile=True):
        """鍔犺浇閫変腑鐨勫瓨妗ｆ枃浠跺苟鍒锋柊鐩戞帶"""
        archive_file = os.path.join(ARCHIVE_DIR, selected_file)
        if not os.path.exists(archive_file):
            messagebox.showerror("閿欒", "瀛樻。鏂囦欢涓嶅瓨鍦?)
            return
        if readfile:
            initial_monitor_list = load_monitor_list(monitor_list_file=archive_file)
            logger.info('readfile:{archive_file}')
            return initial_monitor_list

    def open_archive_view_window(self, filename):
        """
        浠?filename 璇诲彇瀛樻。鏁版嵁骞舵樉绀?        鏁版嵁鏍煎紡锛歔code, name, tag, time]
        """

        try:
            data_list = self.load_archive(filename, readfile=True)

        except Exception as e:
            messagebox.showerror("璇诲彇澶辫触", f"璇诲彇 {filename} 鏃跺彂鐢熼敊璇?\n{e}")
            return

        if not data_list:
            messagebox.showwarning("鏃犳暟鎹?, f"{filename} 涓病鏈夊彲鏄剧ず鐨勬暟鎹€?)
            return

        win = tk.Toplevel(self)
        win.title(f"瀛樻。棰勮 鈥?{filename}")
        win.geometry("600x480")

        window_id = "瀛樻。棰勮"

        columns = ["code", "name", "tag", "time"]
        col_names = {
            "code": "浠ｇ爜",
            "name": "鍚嶇О",
            "tag":  "姒傚康",
            "time": "鏃堕棿"
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

        # === 鍒楄缃?===
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

        # === 鎻掑叆鏁版嵁 ===
        for row in data_list:
            # row: [code, name, tag, time]
            tree.insert("", "end", values=row)

        # === 琛岄€夋嫨閫昏緫 ===
        def on_tree_select(event):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            if not vals:
                return
            code = str(vals[0]).zfill(6)
            self.sender.send(code)
            # Auto-launch Visualizer if enabled
            if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                self.open_visualizer(code)

        def on_single_click(event):
            row_id = tree.identify_row(event.y)
            if not row_id:
                return
            vals = tree.item(row_id, "values")
            if not vals:
                return
            code = str(vals[0]).zfill(6)
            self.sender.send(code)
            if hasattr(self, 'vis_var') and self.vis_var.get() and code:
                self.open_visualizer(code)

        def on_double_click(event):
            item = tree.focus()
            if item:
                # code = tree.item(item, "values")[0]
                m = tree.item(item, "values")
                # self._on_label_double_click_top10(code)
                try:
                    code = m[0]
                    stock_name = m[1] if len(m) > 1 else ""
                    concept_name = m[2] if len(m) > 2 else ""   # 瑙嗕綘鐨?stock_info 缁撴瀯鑰屽畾
                    create_time = m[3] if len(m) > 3 else "" 
                    # 鍞竴key
                    # unique_code = f"{concept_name or ''}_{code or ''}"
                    unique_code = f"{concept_name or ''}_"

                    # 鍒涘缓绐楀彛
                    win = self.show_concept_top10_window_simple(concept_name, code=code, auto_update=True, interval=30,focus_force=True)

                    # 娉ㄥ唽鍥炵洃鎺у瓧鍏?                    self._pg_top10_window_simple[unique_code] = {
                        "win": win,
                        "code": unique_code,
                        "stock_info": m
                    }
                    logger.info(f"鎭㈠绐楀彛 {unique_code}: {concept_name} - {stock_name} ({code}) [{create_time}]")
                except Exception as e:
                    logger.info(f"鎭㈠绐楀彛澶辫触: {m}, 閿欒: {e}")

        tree.bind("<<TreeviewSelect>>", on_tree_select)
        tree.bind("<Button-1>", on_single_click)
        tree.bind("<Double-Button-1>", on_double_click)

        # ESC / 鍏抽棴
        def on_close(event=None):
            # update_window_position(window_id)
            self.save_window_position(win, window_id)
            win.destroy()

        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)

        # 榛樿鎸夋椂闂村€掑簭
        win.after(10, lambda: self.sort_column_archive_view(tree, "time", True))

    def open_detailed_analysis(self):
        """鎵撳紑璇︾粏绯荤粺鍒嗘瀽绐楀彛 (鏀寔绐楀彛澶嶇敤涓庤嚜鍔ㄦ仮澶嶄綅缃?
        
        璇ョ獥鍙ｇ嫭绔嬩簬 open_realtime_monitor 绐楀彛锛屽叧闂疄鏃剁洃鎺х獥鍙ｆ椂涓嶄細涓€骞跺叧闂€?        """
        if hasattr(self, '_detailed_analysis_win') and self._detailed_analysis_win and self._detailed_analysis_win.winfo_exists():
            self._detailed_analysis_win.lift()
            self._detailed_analysis_win.focus_force()
            return

        analysis_win = tk.Toplevel(self)  # 鐖剁獥鍙ｄ负涓荤獥鍙ｏ紝鑰岄潪 log_win
        self._detailed_analysis_win = analysis_win
        analysis_win.title("Realtime System Analysis (PID: %d)" % os.getpid())
        
        # 浣跨敤 WindowMixin 鍔犺浇浣嶇疆
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
                report.append("\n鈩癸笍 Note: 'RAM' is primary memory. 'Requested' (~1.5GB) is virtual reserved space.")
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

    def open_realtime_monitor(self):
        """鎵撳紑瀹炴椂鏁版嵁鏈嶅姟鐩戞帶绐楀彛 (鏀寔绐楀彛澶嶇敤)"""
        if hasattr(self, '_realtime_monitor_win') and self._realtime_monitor_win and self._realtime_monitor_win.winfo_exists():
            self._realtime_monitor_win.lift()
            self._realtime_monitor_win.focus_force()
            return

        try:
            log_win = tk.Toplevel(self)
            self._realtime_monitor_win = log_win
            log_win.title("Realtime Data Service Monitor")
            
            # 浣跨敤 WindowMixin 鍔犺浇浣嶇疆
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

            reset_btn = tk.Button(btn_frame, text="鈫?Reset State", command=manual_reset, font=("Microsoft YaHei", 9), bg="#eeeeee")
            reset_btn.pack(side="left", padx=5)

            analysis_btn = tk.Button(btn_frame, text="馃搳 Detailed Analysis", command=self.open_detailed_analysis, font=("Microsoft YaHei", 9, "bold"), fg="blue")
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

            # Simple text area for status and logs
            text_area = tk.Text(log_win, font=("Consolas", 10), bg="#f0f0f0")
            text_area.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 瀹氫箟鍏抽棴鍥炶皟
            def on_close():
                if hasattr(self, 'save_window_position'):
                    try:
                        self.save_window_position(log_win, window_id)
                    except: pass
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
        """鎵撳紑/澶嶇敤 55188 澶栭儴鏁版嵁鏌ョ湅鍣?""
        if hasattr(self, '_ext_data_viewer_win') and self._ext_data_viewer_win and self._ext_data_viewer_win.winfo_exists():
            if not auto_update:
                self._ext_data_viewer_win.lift()
                self._ext_data_viewer_win.focus_force()
        else:
            self._ext_data_viewer_win = ExtDataViewer(self)
            
        if self.realtime_service:
            try:
                # 浼樺厛鐩存帴浠庢湇鍔℃媺鍙栨渶鏂板叏閲忔暟鎹?                ext_status = self.realtime_service.get_55188_data()
                if ext_status and 'df' in ext_status:
                    df_ext = ext_status['df']
                    self._ext_data_viewer_win.update_data(df_ext)
                    # 鍚屾椂鍚屾缁欑瓥鐣ユā鍧楋紝纭繚涓€鑷存€?                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.ext_data_55188 = df_ext
                        self.live_strategy.last_ext_update_ts = ext_status.get('last_update', 0)
                
                if auto_update:
                    logger.debug("55188 Data auto-pop/refresh triggered.")
            except Exception as e:
                logger.error(f"Update ExtDataViewer failed: {e}")

    def _check_ext_data_update(self):
        """鍛ㄦ湡鎬ф鏌?55188 澶栭儴鏁版嵁鏄惁鏈夋洿鏂帮紝瑙﹀彂 UI 鍚屾鎴栧脊绐?""
        try:
            if self.realtime_service:
                # 鍗充娇娌℃湁涓昏鎯呮洿鏂帮紝涔熷皾璇曞悓姝ュ閮ㄦ暟鎹?                time_start_55188 = time.time()
                ext_status = self.realtime_service.get_55188_data()
                # retry = 0
                # while not ext_status and retry < 5:
                #     time.sleep(0.2)  # 绛?200ms
                #     ext_status = self.realtime_service.get_55188_data()
                #     retry += 1
                if ext_status and 'df' in ext_status:
                    df_ext = ext_status['df']
                    remote_ts = ext_status.get('last_update', 0)
                    try:
                        remote_ts = int(remote_ts)  # 纭繚鏄暣鏁?                    except (ValueError, TypeError):
                        remote_ts = 0  # 寮傚父鎯呭喌褰撲綔鏈洿鏂板鐞?                    # 鍚屾缁欑瓥鐣ユā鍧?                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.ext_data_55188 = df_ext
                        self.live_strategy.last_ext_update_ts = remote_ts
                    
                    if remote_ts > self.last_ext_data_ts_local:
                        # local_time = datetime.datetime.fromtimestamp(int(ts))
                        # local_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
                        local_time = cct.get_unixtime_to_time(int(ts))
                        logger.info(f"馃啎 Detected 55188 data update (ts={local_time}) use time: {remote_ts-time_start_55188:.2f}. Syncing UI...")
                        self.last_ext_data_ts_local = remote_ts
                        
                        if hasattr(self, '_ext_data_viewer_win') and self._ext_data_viewer_win.winfo_exists():
                            self._ext_data_viewer_win.update_data(df_ext)
                        else:
                            # 鏁版嵁鏇存柊涓旂獥鍙ｆ湭鎵撳紑鏃讹紝瑙﹀彂鑷姩寮圭獥
                            self.open_ext_data_viewer(auto_update=True)
        except Exception as e:
            logger.debug(f"[_check_ext_data_update] error: {e}")
        finally:
            self.after(duration_sleep_time*1000, self._check_ext_data_update)

    def open_archive_loader(self):
        """鎵撳紑瀛樻。閫夋嫨绐楀彛"""
        win = tk.Toplevel(self)
        win.title("鍔犺浇鍘嗗彶鐩戞帶鏁版嵁")
        win.geometry("400x300")
        window_id = "鍘嗗彶鐩戞帶鏁版嵁"   # <<< 姣忎釜绐楀彛涓€涓敮涓€ ID
        # self.get_centered_window_position(win, window_id)
        self.load_window_position(win, window_id, default_width=400, default_height=300)
        files = list_archives(archive_dir=ARCHIVE_DIR,prefix='monitor_category_list')
        if not files:
            tk.Label(win, text="娌℃湁鍘嗗彶瀛樻。鏂囦欢").pack(pady=20)
            return

        selected_file = tk.StringVar(value=files[0])
        combo = ttk.Combobox(win, textvariable=selected_file, values=files, state="readonly")
        combo.pack(pady=10)

        # 鍔犺浇鎸夐挳
        # ttk.Button(win, text="鍔犺浇", command=lambda: load_archive(selected_file.get())).pack(pady=5)
        ttk.Button(win, text="鏄剧ず", command=lambda: self.open_archive_view_window(selected_file.get())).pack(pady=5)

        def on_close(event=None):
            """
            缁熶竴鍏抽棴鍑芥暟锛孍SC 鍜屽彸涓婅 脳 閮借兘浣跨敤
            """
            # 鍦ㄨ繖閲屽彲浠ュ姞浠讳綍鍏抽棴鍓嶇殑閫昏緫锛屾瘮濡備繚瀛樻暟鎹垨纭
            # if messagebox.askokcancel("鍏抽棴绐楀彛", "纭瑕佸叧闂悧锛?):
            # update_window_position(window_id)
            self.save_window_position(win, window_id)
            win.destroy()

        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", lambda: on_close())
        win.after(60*1000, lambda: on_close())   # 鑷姩鍏抽棴

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

    # ----------------- 鐘舵€佹爮 ----------------- #
    def update_status(self):
        cnt = len(self.current_df)
        # blk = self.blk_label.cget("text")
        resample = self.resample_combo.get()
        # search = self.search_entry.get()
        search = self.search_var1.get()
        self.status_var.set(f"Rows: {cnt} | blkname: {self.blkname} | resample: {resample} | st: {self.st_key_sort} | search: {search}")


    def save_data_to_csv(self):
        """淇濆瓨褰撳墠 DataFrame 鍒?CSV 鏂囦欢锛屽苟鑷姩甯︿笂褰撳墠 query 鐨?note"""
        if self.current_df.empty:
            return

        resample_type = self.resample_combo.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        # 鑾峰彇褰撳墠閫変腑鐨?query锛堜紭鍏堜粠 active combo锛?        current_query = ""
        try:
            if hasattr(self, "search_combo1") and self.search_combo1 and self.search_combo1.get():
                current_query = self.search_combo1.get().strip()
            elif hasattr(self, "search_combo2") and self.search_combo2 and self.search_combo2.get():
                current_query = self.search_combo2.get().strip()
        except Exception:
            pass

        note = ""

        try:
            # 閬嶅巻涓や釜鍘嗗彶锛屾煡鎵惧尮閰嶇殑 query
            for hist_list in [getattr(self.query_manager, "history1", []),
                              getattr(self.query_manager, "history2", [])]:
                for record in self.query_manager.history1:
                    if record.get("query") == current_query:
                        note = record.get("note", "")
                        break
                if note:
                    break
        except Exception as e:
            logger.info(f"[save_data_to_csv] 鑾峰彇 note 澶辫触: {e}")
            
        # 澶勭悊 note
        if note:
            note = re.sub(r'[\\/*?:"<>|]', "_", note.strip())

        # 鎷兼帴鏂囦欢鍚?        file_name = os.path.join(
            DARACSV_DIR,
            f"monitor_{resample_type}_{timestamp}{'_' + note if note else ''}.csv"
        )

        # 淇濆瓨 CSV
        self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")

        # 鐘舵€佹爮鎻愮ず
        idx = file_name.find("monitor")
        status_txt = file_name[idx:]
        self.status_var2.set(f"宸蹭繚瀛樻暟鎹埌 {status_txt}")
        logger.info(f"[save_data_to_csv] 鏂囦欢宸蹭繚瀛? {file_name}")


    def load_data_from_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            try:
                df = pd.read_csv(file_path, index_col=0)
                # 濡傛灉 CSV 鏈韩宸茬粡鏈?code 鍒楋紝涓嶈鍐嶆彃鍏?                if 'code' in df.columns:
                    df = df.copy()
                #鍋滄鍒锋柊
                self.stop_refresh()
                self.df_all = df
                self.refresh_tree(df)
                idx =file_path.find('monitor')
                status_txt = file_path[idx:]
                # logger.info(f'status_txt:{status_txt}')
                self.status_var2.set(f"宸插姞杞芥暟鎹? {status_txt}")
            except Exception as e:
                logger.error(f"鍔犺浇 CSV 澶辫触: {e}")


    def is_window_visible_on_top(self,tk_window):
        """鍒ゆ柇 Tk 绐楀彛鏄惁浠嶅湪鏈€鍓嶅眰"""
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

            # 濡傛灉绐楀彛琚渶灏忓寲锛屽垯鎭㈠
            if toplevel.state() == "iconic":
                toplevel.deiconify()
                win_info["is_lifted"] = False

            # 妫€鏌ユ槸鍚︾湡鐨勮繕鍦ㄦ渶鍓嶅眰
            if not self.is_window_visible_on_top(toplevel):
                win_info["is_lifted"] = False

            # 鎻愬崌閫昏緫
            if not win_info.get("is_lifted", False):
                toplevel.lift()
                toplevel.attributes("-topmost", 1)
                toplevel.attributes("-topmost", 0)
                win_info["is_lifted"] = True


    def bring_monitor_to_front_pg(self, active_code):
        """浠呭湪褰撳墠 PG 绐楀彛琚富绐楀彛閬尅鏃舵墠鎻愬崌"""
        # main_win = self.main_window     # 涓荤獥鍙?        main_win = self.main_window     # 涓荤獥鍙?        if main_win is None:
            return

        for k, v in self._pg_windows.items():
            win = v.get("win")
            if win is None:
                continue

            if v.get("code") == active_code:
                continue  # 涓嶅鐞嗗綋鍓嶆椿鍔ㄧ獥鍙?
            # 鍒ゆ柇鏄惁琚伄鎸?            logger.info(f'win: {win} main_win: {main_win} type: {type(main_win)}')

            if is_window_covered_pg(win, main_win):
                # 鑻ヨ鏈€灏忓寲锛屾仮澶?                logger.info(f'v.get("code"): {v.get("code")}')
                if win.isMinimized():
                    win.showNormal()

                # 杞婚噺鎻愬崌 鈫?涓嶆姠鐒︾偣
                win.raise_()
                win.activateWindow()


    def on_monitor_window_focus_pg(self,active_windows):
        """
        褰撲换鎰忕獥鍙ｈ幏寰楃劍鐐规椂锛屽崗璋冧袱涓獥鍙ｅ埌鏈€鍓嶃€?        """

        win_state = self.win_var.get()
        if win_state:
            self.bring_monitor_to_front_pg(active_windows)

    def on_monitor_window_focus(self,active_windows):
        """
        褰撲换鎰忕獥鍙ｈ幏寰楃劍鐐规椂锛屽崗璋冧袱涓獥鍙ｅ埌鏈€鍓嶃€?        """
        win_state = self.win_var.get()
        if win_state:
            self.bring_monitor_to_front(active_windows)
            self.bring_monitor_to_front_pg(active_windows)
        else:
           for win_id, win_info in self.monitor_windows.items():
               toplevel = win_info.get("toplevel")
               if not (toplevel and toplevel.winfo_exists()):
                   continue

               # 鎻愬崌閫昏緫
               if  win_info.get("is_lifted", True):
                   win_info["is_lifted"] = False
                                    
# --- DPI and Config methods moved to Mixins ---
# --- Duplicate window methods removed ---

# KLineMonitor class moved to kline_monitor.py

def test_single_thread(single=True, test_strategy=False):
    """
    鍗曠嚎绋嬫祴璇曞嚱鏁般€?    :param single: 鏄惁鍗曟鎵ц锛堥粯璁?True锛屾墽琛屼竴娆″悗杩斿洖锛?    :param test_strategy: 鏄惁鍚屾椂娴嬭瘯 StockLiveStrategy
    """
    import queue
    # 鐢ㄦ櫘閫?dict 浠ｆ浛 manager.dict()
    global marketInit,resampleInit
    shared_dict = {}
    shared_dict["resample"] = resampleInit
    shared_dict["market"] = marketInit

    # 鐢?Python 鍐呯疆 queue 浠ｆ浛 multiprocessing.Queue
    q = queue.Queue()

    # 鐢ㄤ竴涓畝鍗曠殑瀵硅薄/甯冨皵鍊兼ā鎷?flag
    class Flag:
        def __init__(self, value=True):
            self.value = value
    flag = Flag(True)   # 鎴栬€?flag = Flag(False) 鐪嬩綘鐨勬祴璇曢渶姹?    log_level = mp.Value('i', LoggerFactory.DEBUG)  # 'i' 琛ㄧず鏁存暟
    detect_calc_support = mp.Value('b', False)  # 'i' 琛ㄧず鏁存暟
    # 鐩存帴鍗曠嚎绋嬭皟鐢?    df = fetch_and_process(shared_dict, q, blkname="boll", flag=flag ,log_level=log_level,detect_calc_support_var=detect_calc_support,single=single)
    
    if test_strategy and df is not None and not df.empty:
        print(f"===== 娴嬭瘯 StockLiveStrategy =====")
        print(f"DataFrame shape: {df.shape}")
        
        # 鍒涘缓妯℃嫙 master 瀵硅薄
        class MockMaster:
            def __init__(self):
                self.df_all = df
                self.voice_var = type('obj', (object,), {'get': lambda self: False})()
                self.realtime_service = None
            
            def after(self, ms, func, *args):
                """妯℃嫙 TK after 鏂规硶 - 鐩存帴鎵ц"""
                func(*args)
        
        mock_master = MockMaster()
        
        try:
            # 浣跨敤涓?_init_live_strategy 鐩稿悓鐨勫弬鏁?            strategy = StockLiveStrategy(
                mock_master,
                alert_cooldown=alert_cooldown,
                voice_enabled=False,
                realtime_service=None
            )
            print(f"鉁?StockLiveStrategy 鍒濆鍖栨垚鍔?)
            
            # 娴嬭瘯 _check_strategies
            print(f"娴嬭瘯 _check_strategies...")
            strategy._check_strategies(df, resample='d')
            print(f"鉁?_check_strategies 鎵ц鎴愬姛")
            
        except Exception as e:
            print(f"鉂?StockLiveStrategy 娴嬭瘯澶辫触: {e}")
            import traceback
            traceback.print_exc()
    
    return df

def test_main_process_params():
    """
    浣跨敤涓庝富杩涚▼瀹屽叏鐩稿悓鐨勫弬鏁拌繘琛屽崟绾跨▼娴嬭瘯銆?    妯℃嫙 _start_process 涓殑璋冪敤鏂瑰紡銆?    """
    import queue
    global marketInit, marketblk, duration_sleep_time, resampleInit
    
    # 鑾峰彇鍏ㄥ眬鍙橀噺鎴栦娇鐢ㄩ粯璁ゅ€?    try:
        _log_level = log_level
    except NameError:
        _log_level = LoggerFactory.DEBUG
    
    try:
        _detect_calc_support = detect_calc_support
    except NameError:
        _detect_calc_support = False
    
    print("===== 娴嬭瘯涓昏繘绋嬪弬鏁?=====")
    print(f"marketInit: {marketInit}")
    print(f"marketblk: {marketblk}")
    print(f"duration_sleep_time: {duration_sleep_time}")
    print(f"log_level: {_log_level}")
    print(f"detect_calc_support: {_detect_calc_support}")
    
    # 妯℃嫙 self.global_dict锛堜笌涓昏繘绋嬩竴鑷达級
    shared_dict = {}
    shared_dict["resample"] = resampleInit
    shared_dict["market"] = marketInit
    
    # 妯℃嫙 self.queue
    q = queue.Queue()
    
    # 妯℃嫙 self.blkname
    blkname = "boll"
    
    # 妯℃嫙 self.refresh_flag, self.log_level, self.detect_calc_support
    # 浣跨敤 mp.Value 涓庝富杩涚▼涓€鑷?    refresh_flag = mp.Value('b', True)
    log_level_var = mp.Value('i', _log_level)
    detect_calc_support_var = mp.Value('b', _detect_calc_support)
    
    print(f"\n璋冪敤 fetch_and_process (涓庝富杩涚▼鍙傛暟涓€鑷?...")
    
    try:
        # 涓庝富杩涚▼璋冪敤鏂瑰紡瀹屽叏涓€鑷?        df = fetch_and_process(
            shared_dict, 
            q, 
            blkname, 
            refresh_flag, 
            log_level_var, 
            detect_calc_support_var, 
            marketInit, 
            marketblk, 
            duration_sleep_time,
            status_callback=tip_var_status_flag,  # 涓庝富杩涚▼ kwargs 涓€鑷?            single=True  # 鍗曟鎵ц锛屼笉寰幆
        )
        
        if df is not None and not df.empty:
            print(f"鉁?fetch_and_process 鎴愬姛, DataFrame shape: {df.shape}")
            return df
        else:
            print(f"鈿狅笍 fetch_and_process 杩斿洖绌?DataFrame")
            return None
            
    except Exception as e:
        print(f"鉂?fetch_and_process 澶辫触: {e}")
        import traceback
        traceback.print_exc()
        return None

# 甯哥敤鍛戒护绀轰緥鍒楄〃
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

# 鏍煎紡鍖栧府鍔╀俊鎭紝鎹㈣+缂╄繘
help_text = "浼犻€?Python 鍛戒护瀛楃涓叉墽琛岋紝渚嬪:\n" + "\n".join([f"    {cmd}" for cmd in COMMON_COMMANDS])
def parse_args():
    parser = argparse.ArgumentParser(description="Monitor Init Script")

    parser.add_argument(
        "-log",
        type=str,
        default=str(cct.loglevel).upper(),
        help="鏃ュ織绛夌骇锛屽彲閫夛細DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )

    # 甯冨皵寮€鍏冲弬鏁?    parser.add_argument(
        "-write_to_hdf",
        action="store_true",
        help="鎵ц write_to_hdf() 骞堕€€鍑?
    )
    # TDX寮€鍏冲弬鏁?    parser.add_argument(
        "-write_today_tdx",
        action="store_true",
        help="鎵ц write_today_tdx() 骞堕€€鍑?
    )
    # 甯冨皵寮€鍏冲弬鏁?    parser.add_argument(
        "-test_single",
        action="store_true",
        help="鎵ц test_single_thread() 骞堕€€鍑?
    )
    # 鏂板娴嬭瘯寮€鍏?    parser.add_argument(
        "-test",
        action="store_true",
        help="鎵ц娴嬭瘯鏁版嵁娴佺▼"
    )

    parser.add_argument(
        "-cmd",
        type=str,
        nargs='?',          # 琛ㄧず鍙傛暟鍙€?        const=COMMON_COMMANDS[0],  # 榛樿鏃犲€兼椂浣跨敤绗竴涓父鐢ㄥ懡浠? # 褰撴病鏈夊€兼椂浣跨敤 const
        default=None,       # 濡傛灉瀹屽叏娌′紶 --cmd, default 鎵嶄細鐢熸晥
        help=help_text
        # help="浼犻€?Python 鍛戒护瀛楃涓叉墽琛岋紝渚嬪:\n" + "\n".join(COMMON_COMMANDS)
        # help="浼犻€?Python 鍛戒护瀛楃涓叉墽琛岋紝渚嬪: tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')"
    )

    args, _ = parser.parse_known_args()  # 蹇界暐 multiprocessing 绉佹湁鍙傛暟
    return args

def test_get_tdx():
    """灏佽娴嬭瘯鍑芥暟锛岃幏鍙栬偂绁ㄥ巻鍙叉暟鎹?""
    code = '000002'
    dl = 60
    newdays = 0
    resample = 'd'

    try:
        df = tdd.get_tdx_Exp_day_to_df(code, dl=dl, newdays=newdays, resample=resample)
        if df is not None and not df.empty:
            logger.info(f"鎴愬姛鑾峰彇 {code} 鐨勬暟鎹紝鍓?琛?\n{df.head()}")
        else:
            logger.warning(f"{code} 杩斿洖鏁版嵁涓虹┖")
    except Exception as e:
        logger.error(f"鑾峰彇 {code} 鏁版嵁澶辫触: {e}", exc_info=True)

def write_today_tdx():
    global write_all_day_date
    today = cct.get_today('')
    if write_all_day_date == today:
        logger.info(f'Write_market_all_day_mp 宸茬粡瀹屾垚')
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


# ------------------ 涓荤▼搴忓叆鍙?------------------ #
if __name__ == "__main__":
    # queue = mp.Queue()
    # p = mp.Process(target=fetch_and_process, args=(queue,))
    # p.daemon = True
    # p.start()
    # app = StockMonitorApp(queue)

    # from multiprocessing import Manager
    # manager = Manager()
    # global_dict = manager.dict()  # 鍏变韩瀛楀吀
    # import ipdb;ipdb.set_trace()

    # logger = init_logging("test.log")

    # logger = init_logging(log_file='monitor_tk.log',redirect_print=True)

    # logger.info("杩欐槸 print 杈撳嚭")
    # logger.info("杩欐槸 logger 杈撳嚭")

    # # 娴嬭瘯寮傚父
    # try:
    #     1 / 0
    # except Exception:
    #     logging.exception("鎹曡幏寮傚父")
    
    # 娴嬭瘯鏈崟鑾峰紓甯?    # 鐩存帴瑙﹀彂
    # 1/0
    # 浠呭湪 Windows 涓婅缃惎鍔ㄦ柟娉曪紝鍥犱负 Unix/Linux 榛樿鏄?'fork'锛屾洿绋冲畾
    if sys.platform.startswith('win'):
        mp.freeze_support() # Windows 蹇呴渶
        mp.set_start_method('spawn', force=True)
        # 'spawn' 鏄粯璁ょ殑锛屼絾鏄惧紡璁剧疆鏈夊姪浜庣‘淇濅竴鑷存€с€?        # 鍙︿竴绉嶆柟娉曟槸灏濊瘯浣跨敤 'forkserver' (濡傛灉鍙敤)
        # mp.freeze_support()  # <-- 蹇呴』

    args = parse_args()  # 瑙ｆ瀽鍛戒护琛屽弬鏁?    # log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.ERROR)
    log_level = getattr(LoggerFactory, args.log.upper(), LoggerFactory.INFO)
    # log_level = LoggerFactory.DEBUG

    # 鐩存帴鐢ㄨ嚜瀹氫箟鐨?init_logging锛屼紶鍏ユ棩蹇楃瓑绾?    # logger = init_logging(log_file='instock_tk.log', redirect_print=False, level=log_level)
    logger.setLevel(log_level)
    logger.info("绋嬪簭鍚姩鈥?)    

    # test_single_thread()
    # import ipdb;ipdb.set_trace()

    # if log_level == logging.DEBUG:
    # if logger.isEnabledFor(logging.DEBUG):
    #     logger.debug("褰撳墠宸插紑鍚?DEBUG 妯″紡")
    #     log = LoggerFactory.log
    #     log.setLevel(LoggerFactory.DEBUG)
    #     log.debug("log褰撳墠宸插紑鍚?DEBUG 妯″紡")

    # log.setLevel(LoggerFactory.INFO)
    # log.setLevel(Log.DEBUG)

    # 鉁?鍛戒护琛岃Е鍙?write_to_hdf
    if args.test:
        test_get_tdx()
        sys.exit(0)

    # 鎵ц浼犲叆鍛戒护
    if args.cmd:
        if len(args.cmd) > 5:
            try:
                from data_utils import *
                result = eval(args.cmd)
                print("鎵ц缁撴灉:", result)
            except Exception as e:
                logger.error(f"鎵ц鍛戒护鍑洪敊: {args.cmd}\n{traceback.format_exc()}")

        # # 鍙€夛細琛ュ叏鍏抽敭瀛楁垨鍑芥暟鍚?        # completer = WordCompleter(['get_tdx_Exp_day_to_df', 'quit', 'exit'], ignore_case=True)

        # # 鍒涘缓 PromptSession 骞舵寚瀹氬巻鍙叉枃浠?        # session = PromptSession(history=FileHistory('.cmd_history'), completer=completer)

        # -------------------------------
        # 鍔ㄦ€佹敹闆嗚ˉ鍏ㄥ垪琛?        # -------------------------------
        def get_completions():
            completions = list(COMMON_COMMANDS)  # 鍏堟妸甯哥敤鍛戒护鏀惧埌鏈€鍓嶉潰
            # completions = []
            for name, obj in globals().items():
                completions.append(name)
                if hasattr(obj, '__dict__'):
                    # 鏀寔 obj. 瀛愬睘鎬цˉ鍏?                    completions.extend([f"{name}.{attr}" for attr in dir(obj) if not attr.startswith('_')])
            return completions

        # 鍒涘缓 WordCompleter
        completer = WordCompleter(get_completions(), ignore_case=True, sentence=True)

        # 鍒涘缓 PromptSession 骞舵寚瀹氬巻鍙叉枃浠?        session = PromptSession(history=FileHistory('.cmd_history'), completer=completer)

        result_stack = []  # 淇濆瓨鍘嗗彶缁撴灉

        HELP_TEXT = """
        璋冭瘯妯″紡鍛戒护:
          :help         鏄剧ず甯姪淇℃伅
          :result       鏌ョ湅鏈€鏂扮粨鏋?          :history      鏌ョ湅鍘嗗彶缁撴灉鍐呭锛圖ataFrame鏄剧ず鍓?琛岋級
          :clear        娓呯┖鍘嗗彶缁撴灉
        閫€鍑?
          quit / q / exit / e
        璇存槑:
          鏈€鏂版墽琛岀粨鏋滄€绘槸瀛樻斁鍦?`result` 鍙橀噺涓?          鎵€鏈夊巻鍙茬粨鏋滈兘瀛樻斁鍦?`result_stack` 鍒楄〃锛屽彲閫氳繃绱㈠紩璁块棶
        """

        def summarize(obj, head_rows=5):
            """鏍规嵁瀵硅薄绫诲瀷杩斿洖鍙鎽樿"""
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

        print("璋冭瘯妯″紡鍚姩 (杈撳叆 ':help' 鑾峰彇甯姪)")
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

                # 閫€鍑哄懡浠?                if cmd.lower() in ['quit', 'q', 'exit', 'e']:
                    print("閫€鍑鸿皟璇曟ā寮?)
                    break

                # 鐗规畩鍛戒护
                if cmd.startswith(":"):
                    if cmd == ":help":
                        print(HELP_TEXT)
                    elif cmd == ":result":
                        if result_stack:
                            print(summarize(result_stack[-1]))
                        else:
                            print("娌℃湁鍘嗗彶缁撴灉")
                    elif cmd == ":history":
                        if result_stack:
                            for i, r in enumerate(result_stack):
                                print(f"[{i}] {summarize(r)}\n{'-'*50}")
                        else:
                            print("娌℃湁鍘嗗彶缁撴灉")
                    elif cmd == ":clear":
                        result_stack.clear()
                        print("鍘嗗彶缁撴灉宸叉竻绌?)
                    else:
                        print("鏈煡鍛戒护:", cmd)
                    continue

                # 灏濊瘯 eval
                try:
                    temp = eval(cmd, globals(), locals())
                    result_stack.append(temp)   # 淇濆瓨鍘嗗彶
                    result = result_stack[-1]   # 鏈€鏂扮粨鏋?                    globals()['result'] = result  # 娉ㄥ叆鍏ㄥ眬锛屾柟渚垮悗缁搷浣?                    print(summarize(temp))
                except Exception:
                    try:
                        exec(cmd, globals(), locals())
                        print("鎵ц瀹屾垚 (exec)")
                    except Exception:
                        print("鎵ц寮傚父:\n", traceback.format_exc())

            except KeyboardInterrupt:
                print("\nKeyboardInterrupt, 杈撳叆 'quit' 閫€鍑?)
            except EOFError:
                print("\nEOF, 閫€鍑鸿皟璇曟ā寮?)
                break

        sys.exit(0)        
    # 鉁?鍛戒护琛岃Е鍙?write_to_hdf
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
    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)

    app.mainloop()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # 棰濆闃叉姢锛欳trl+C 鍦ㄦ煇浜涙儏鍐典笅浠嶅彲鑳芥姏寮傚父
        app.ask_exit()

import os
import sys
import warnings
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*"
)
import json
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

from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from logger_utils import LoggerFactory, init_logging
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
    bind_mouse_scroll, get_monitor_by_point, rearrange_monitors_per_screen,get_monitor_index_for_window
)
from tk_gui_modules.dpi_mixin import DPIMixin
from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.treeview_mixin import TreeviewMixin
from tk_gui_modules.gui_config import (
    WINDOW_CONFIG_FILE, MONITOR_LIST_FILE, WINDOW_CONFIG_FILE2,
    CONFIG_FILE, SEARCH_HISTORY_FILE, ICON_PATH as icon_path
)
from trading_logger import TradingLogger
from dpi_utils import set_process_dpi_awareness, get_windows_dpi_scale_factor
from ext_data_viewer import ExtDataViewer
from sys_utils import get_base_path
from stock_handbook import StockHandbook
from history_manager import QueryHistoryManager

from stock_logic_utils import get_row_tags,detect_signals,toast_message
from stock_logic_utils import test_code_against_queries,is_generic_concept

from db_utils import *
from kline_monitor import KLineMonitor
from stock_selection_window import StockSelectionWindow
from stock_selector import StockSelector
from column_manager import ColumnSetManager
from collections import Counter, OrderedDict, deque
import hashlib

# 全局单例
logger = init_logging(log_file='instock_tk.log',redirect_print=False) 
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

from PyQt6 import QtWidgets, QtCore, QtGui
from trading_analyzerQt6 import TradingGUI

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
    logger.critical("MonitorTK.ico 加载失败，程序无法继续运行")

START_INIT = 0


DEFAULT_DISPLAY_COLS = [
    'name', 'trade', 'boll', 'dff', 'df2', 'couts',
    'percent', 'per1d', 'perc1d', 'ra', 'ral',
    'topR', 'volume', 'red', 'lastdu4', 'category'
]

from alerts_manager import AlertManager, open_alert_center, set_global_manager, check_alert
def ___toast_message(master, text, duration=1500):
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

class StockMonitorApp(DPIMixin, WindowMixin, TreeviewMixin, tk.Tk):
    def __init__(self):
        # 初始化 tk.Tk()
        super().__init__()
        
        # 💥 关键修正 1：在所有代码执行前，初始化为安全值
        self.main_window = self   
        self.scale_factor = 1.0 
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_font_size = self.default_font.cget("size")
        self.default_font_bold = tkfont.nametofont("TkDefaultFont").copy()
        self.default_font_bold.configure(family="Microsoft YaHei", size=10, weight="bold")

        global duration_sleep_time
        # 💥 关键修正 2：立即执行 DPI 缩放并重新赋值
        if sys.platform.startswith('win'):
            result_scale = self._apply_dpi_scaling()
            if result_scale is not None and isinstance(result_scale, (float, int)):
                self.scale_factor = result_scale


        self.last_dpi_scale = self.scale_factor
        # 3. 接下来是 Qt 初始化，它不应该影响 self.scale_factor
        if not QtWidgets.QApplication.instance():
            self.app = pg.mkQApp()

        self.title("Stock Monitor")
        self.initial_w, self.initial_h, self.initial_x, self.initial_y  = self.load_window_position(self, "main_window", default_width=1200, default_height=480)
        self.monitor_windows = {}

        # 判断文件是否存在再加载
        if os.path.exists(icon_path):
            self.after(1000, lambda: self.iconbitmap(icon_path))

        else:
            logger.error(f"图标文件不存在: {icon_path}")

        self.sortby_col = None
        self.sortby_col_ascend = None
        self.select_code = None
        self.ColumnSetManager = None
        self.ColManagerconfig = None
        self._open_column_manager_job = None

        self._concept_dict_global = {}

        # 刷新开关标志
        self.refresh_enabled = True
        # ✅ 初始化实时监控策略 (延迟初始化，防止阻塞主窗口显示)
        self.live_strategy = None
        self.after(3000, self._init_live_strategy)
        
        # 4. 初始化 Realtime Data Service
        try:
            # 启动 Manager 仅用于同步设置 (global_dict)
            logger.info("正在启动 StockManager (SyncManager) 用于状态共享...")
            self.manager = StockManager()
            self.manager.start()
            
            self.global_dict = self.manager.dict()
            self.global_dict["resample"] = resampleInit
            
            # 🔥 直接在主进程实例化 DataPublisher 以减少跨进程开销和内存占用
            # 这样避免了在 SyncManager 进程中维护一个庞大的数据对象副本
            self.realtime_service = DataPublisher(high_performance=False)
            logger.info(f"✅ RealtimeDataService (Local) 已就绪 (Main PID: {os.getpid()})")

        except Exception as e:
            logger.error(f"❌ RealtimeDataService 初始化失败: {e}\n{traceback.format_exc()}")
            self.realtime_service = None
            self.manager = mp.Manager()
            self.global_dict = self.manager.dict()
            self.global_dict["resample"] = resampleInit
            self.global_dict['init_error'] = str(e)
        # Restore global_values initialization
        self.global_values = cct.GlobalValues(self.global_dict)
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
        self.select_code = None

        # 🛡️ 动态列订阅管理
        self.mandatory_cols: set[str] = {
            'code', 'name', 'trade', 'high', 'low', 'open', 'ratio', 'volume', 'amount',
            'percent', 'per1d', 'perc1d', 'nclose', 'ma5d', 'ma10d', 'ma20d', 'ma60d',
            'ma51d', 'lastp1d', 'lastp2d', 'lastp3d', 'lastl1d', 'lasto1d', 'lastv1d', 'lasth1d',
            'macddif', 'macddea', 
            'macd', 'macdlast1', 'macdlast2', 'macdlast3', 'rsi', 'kdj_j', 'kdj_k', 
            'kdj_d', 'upper', 'lower', 'max5', 'high4', 'curr_eval', 'trade_signal',
            'now', 'signal', 'signal_strength', 'emotion', 'win', 'sum_perc', 'slope',
            'vol_ratio', 'power_idx', 'category', 'lastdu4'
        }
        self.update_required_columns()

        # ----------------- 控件框 ----------------- #
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", padx=5, pady=1)

        self.st_key_sort = self.global_values.getkey("st_key_sort") or st_key_sort

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
        
        #总览概念分析前5板块
        self.concept_top5 = None
        #初始化延迟运行live_strategy
        self._live_strategy_first_run = True
        # ✅ 初始化标注手札
        self.handbook = StockHandbook()
        # ✅ 初始化实时监控策略 (延迟初始化，防止阻塞主窗口显示)
        self.live_strategy = None
        self.after(3000, self._init_live_strategy)
        
        # ✅ 初始化 55188 数据更新监听状态
        self.last_ext_data_ts_local = 0
        self.after(10000, self._check_ext_data_update)
        
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
        # 📋 启动后台剪贴板监听服务 (包含自动查重逻辑，避免重复发送当前已选中代码)
        self.clipboard_monitor = start_clipboard_listener(
            self.sender, 
            ignore_func=lambda code: code == getattr(self, 'select_code', None)
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)  
        # self.tree.bind("<Button-1>", self.on_single_click)
        # ✅ 绑定单击事件用于显示股票信息提示框
        # self.tree.bind("<ButtonRelease-1>", self.on_tree_click_for_tooltip)
        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)

        self.bind("<Alt-c>", lambda e:self.open_column_manager())
        self.bind("<Alt-d>", lambda event: self.open_handbook_overview())
        self.bind("<Alt-e>", lambda event: self.open_voice_monitor_manager())
        self.bind("<Alt-g>", lambda event: self.open_trade_report_window())
        # 启动周期检测 RDP DPI 变化
        self.after(3000, self._check_dpi_change)
        self.auto_adjust_column = self.dfcf_var.get()
        # self.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        if event.widget != self:
            return
        # 标记 resize 进行中
        self._is_resizing = True
        if hasattr(self, "_resize_after_id") and self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        # 只有“停下来”才触发真正刷新
        self._resize_after_id = self.after(
            300,
            self._on_resize_finished
        )
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

        self.after(60*1000, self.schedule_15_30_job)

    # worker
    def run_15_30_task(self):
        if getattr(self, "_task_running", False):
            return

        # ✅ 每日重置实时服务状态
        # if self.realtime_service:
        #     try:
        #         self.realtime_service.reset_state()
        #         logger.info("✅ RealtimeService daily reset triggered.")
        #     except Exception as e:
        #         logger.error(f"❌ RealtimeService reset failed: {e}")

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
    def on_close(self):
        try:
            logger.info("程序正在退出，执行保存与清理...")
            
            # 1. 保存预警规则
            if hasattr(self, 'alert_manager'):
                self.alert_manager.save_all()
                logger.info("预警规则已保存")
                
            # 2. 存档交易日志 (TradingLogger)
            try:
                t_logger = TradingLogger()
                archive_file_tools(t_logger.db_path, "trading_signals", ARCHIVE_DIR, logger)
            except Exception as e:
                logger.warning(f"交易日志存档失败: {e}")
            
            # 3. 存档手札
            if hasattr(self, 'handbook'):
                try:
                    archive_file_tools(self.handbook.data_file, "stock_handbook", ARCHIVE_DIR, logger)
                except Exception as e:
                    logger.warning(f"手札存档失败: {e}")

            # 4. 如果 concept 窗口存在，也保存位置并隐藏
            if hasattr(self, "_concept_win") and self._concept_win:
                if self._concept_win.winfo_exists():
                    self.save_window_position(self._concept_win, "detail_window")
                    self._concept_win.destroy()
            
            # 5. 如果 KLineMonitor 存在且还没销毁，保存位置
            if hasattr(self, "kline_monitor") and self.kline_monitor and self.kline_monitor.winfo_exists():
                try:
                    self.save_window_position(self.kline_monitor, "KLineMonitor")
                    self.kline_monitor.on_kline_monitor_close()
                    self.kline_monitor.destroy()
                except Exception:
                    pass

            # 6. 保存并关闭所有 monitor_windows（概念前10窗口）
            if hasattr(self, "live_strategy"):
                try:
                    now_time = cct.get_now_time_int()
                    if now_time > 1500:
                        self.live_strategy._save_monitors()
                        logger.info(f"[on_close] self.live_strategy._save_monitors SAVE OK")
                    else:
                        logger.info(f"[on_close] now:{now_time} 不到收盘时间 未进行_save_monitors SAVE OK")
                except Exception as e:
                    logger.warning(f"[on_close] self.live_strategy._save_monitors 失败: {e}")

            # 7. 关闭所有 concept top10 窗口 (Tkinter 版)
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
                                logger.info(f"关闭窗口 {key} 出错: {e}")
                    self._pg_top10_window_simple.clear()
                except Exception as e:
                    logger.warning(f"关闭 TK 监控窗口异常: {e}")

            # 8. 关闭所有监视窗口 (PyQt 版)
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
                                logger.info(f"关闭 Qt 窗口 {key} 出错: {e}")
                    self._pg_windows.clear()
                except Exception as e:
                    logger.warning(f"关闭 Qt 监控窗口异常: {e}")

            # 9. 保存主窗口位置与搜索记录
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
                logger.warning(f"搜索历史归档失败: {e}")

            # 10. 停止后台进程与管理器 (关键顺序：先停进程，再停管理器)
            self.stop_refresh()
            
            if hasattr(self, "proc") and self.proc.is_alive():
                logger.info("正在停止后台数据扫描进程...")
                self.proc.join(timeout=1.5)
                if self.proc.is_alive():
                    self.proc.terminate()
                    logger.info("后台进程已强制终止")
                else:
                    logger.info("后台进程已安全退出")

            if hasattr(self, "manager"):
                try:
                    # 断开代理引用，防止 shutdown 时的 BrokenPipe
                    self.realtime_service = None
                    self.global_dict = None
                    self.manager.shutdown()
                    logger.info("SyncManager 已安全关闭")
                except Exception as e:
                    # Windows 下退出时常有管道异常，此处捕获不抛出
                    logger.debug(f"SyncManager shutdown suppressed exception: {e}")

            # 11. 最后销毁主窗口
            self.destroy()
            logger.info("程序正常退出完成")
            
        except Exception as e:
            logger.error(f"退出过程发生严重异常: {e}\n{traceback.format_exc()}")
            try:
                self.destroy()
            except:
                pass


    # 防抖 resize（避免重复刷新）
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
                self.after(1000,_on_open_column_manager_init)

    def on_close_column_manager(self):
        if self.ColumnSetManager is not None:
            self.ColumnSetManager.destroy()
            self.ColumnSetManager = None
            self._open_column_manager_job = None
            if hasattr(self, 'global_dict') and self.global_dict is not None:
                 self.global_dict['keep_all_columns'] = False  # 关闭发现模式
            self.update_required_columns() # 恢复按需裁剪

    def update_required_columns(self, refresh_ui=False) -> None:
        """同步当前 UI 和策略所需的列到后台进程"""
        try:
            if not refresh_ui or not hasattr(self, 'global_dict') or self.global_dict is None:
                return
            
            # 这里的 self.current_cols 存储了当前 UI 真正显示的列
            current_ui_cols = set(getattr(self, 'current_cols', []))
            
            # 使用更严谨的获取方式
            mandatory = getattr(self, 'mandatory_cols', set())
            required = set(mandatory).union(current_ui_cols)
            
            # 更新到 global_dict 供后台进程读取
            self.global_dict['required_cols'] = list(required)
            logger.debug(f"Dynamic Trimming: Subscribed to {len(required)} columns.")
        except Exception as e:
            logger.error(f"Failed to update required columns: {e}")

    def tree_scroll_to_code(self, code):
        """外部调用：定位特定代码"""
        if hasattr(self, 'search_var1'):
            self.search_var1.set(code)
            self.apply_search()

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
            stock_percent = df_all.loc[code, 'percent']
            stock_row = df_all.loc[code]
        except Exception:
            try:
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
        self.concept_top5 = concept_score[:5]
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
        resampleValues = ["d",'3d', "w", "m"]
        tk.Label(ctrl_frame, text="resample:").pack(side="left")
        self.resample_combo = ttk.Combobox(ctrl_frame, values=resampleValues, width=3)
        self.resample_combo.current(resampleValues.index(self.global_values.getkey("resample")))
        self.resample_combo.pack(side="left", padx=5)
        self.resample_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_data())

        # 在初始化时（StockMonitorApp.__init__）创建并注册：
        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=logger)
        set_global_manager(self.alert_manager)  

        # ✅ 关键：同步一次状态
        on_market_select()

        # --- 底部搜索框 2 ---
        bottom_search_frame = tk.Frame(self)
        bottom_search_frame.pack(side="bottom", fill="x", pady=1)

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

        self.search_history1, self.search_history2,self.search_history3 = self.query_manager.load_search_history()

        # 从 query_manager 获取历史
        h1, h2, h3 = self.query_manager.history1, self.query_manager.history2, self.query_manager.history3

        # 提取 query 字段用于下拉框
        self.search_history1 = [r["query"] for r in h1]
        self.search_history2 = [r["query"] for r in h2]   
        self.search_history3 = [r["query"] for r in h3]

        tk.Button(bottom_search_frame, text="搜索", command=lambda: self.apply_search()).pack(side="left", padx=3)
        tk.Button(bottom_search_frame, text="清空", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="删除", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="管理", command=lambda: self.open_column_manager()).pack(side="left", padx=2)


        # 功能选择下拉框（固定宽度）
        options = ["窗口重排","Query编辑","停止刷新", "启动刷新" , "保存数据", "读取存档", "报警中心","复盘数据", "盈亏统计", "交易分析Qt6", "覆写TDX", "手札总览", "语音预警"]
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
            elif action == "盈亏统计":
                self.open_trade_report_window()
            elif action == "交易分析Qt6":
                self.open_trading_analyzer_qt6()
            elif action == "复盘数据":
                self.open_strategy_backtest_view()


        def on_select(event=None):
            run_action(self.action_combo.get())
            self.action_combo.set("功能选择")

        self.action_combo.bind("<<ComboboxSelected>>", on_select)



        tk.Button(ctrl_frame, text="清空", command=lambda: self.clean_search(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="删除", command=lambda: self.delete_search_history(2)).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="监控", command=lambda: self.KLineMonitor_init()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="选股", command=lambda: self.open_stock_selection_window()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="写入", command=lambda: self.write_to_blk()).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="存档", command=lambda: self.open_archive_loader(), font=('Microsoft YaHei', 9), padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="实时", command=lambda: self.open_realtime_monitor(), font=('Microsoft YaHei', 9), padx=2, pady=2).pack(side="left", padx=2)
        tk.Button(ctrl_frame, text="55188数据", command=lambda: self.open_ext_data_viewer(), font=('Microsoft YaHei', 9, 'bold'), fg="darkgreen", padx=2, pady=2).pack(side="left", padx=2)

        if len(self.search_history1) > 0:
            self.search_var1.set(self.search_history1[0])
        if len(self.search_history2) > 0:
            self.search_var2.set(self.search_history2[0])

        self.open_column_manager_init()

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
        # self.proc = mp.Process(target=fetch_and_process, args=(self.queue,))
        # def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
        #                       flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
        #                       marketInit: str = "all", marketblk: str = "boll",
        #                       duration_sleep_time: int = 5, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
        self.proc = mp.Process(target=fetch_and_process, args=(self.global_dict,self.queue, self.blkname , self.refresh_flag,self.log_level, self.detect_calc_support,marketInit,marketblk,duration_sleep_time))
        # self.proc.daemon = True
        self.proc.daemon = False 
        self.proc.start()

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
                    # 🔌 在主进程同步更新 DataPublisher
                    if hasattr(self, 'realtime_service') and self.realtime_service:
                        try:
                            self.realtime_service.update_batch(df)
                        except Exception as e:
                            logger.error(f"Main process realtime update error: {e}")
                    

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
                # if not self.tip_var.get() and has_update and hasattr(self, 'live_strategy'):
                if has_update and hasattr(self, 'live_strategy'):
                    if not (915 < cct.get_now_time_int() < 920):
                        # self.after(90 * 1000, lambda: self.live_strategy.process_data(self.df_all))
                        if self._live_strategy_first_run:
                            # 第一次：延迟执行
                            self._live_strategy_first_run = False
                            self.after(15 * 1000,lambda: self.live_strategy.process_data(self.df_all, concept_top5=getattr(self, 'concept_top5', None)))
                        else:
                            # 后续：立即执行
                            self.live_strategy.process_data(self.df_all, concept_top5=getattr(self, 'concept_top5', None))

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
            send_code_via_pipe(payload, logger=logger)   # 假设你用 multiprocessing.Pipe
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
            stock_name = stock_info[1]

            send_tdx_Key = (self.select_code != stock_code)
            self.select_code = stock_code

            stock_code = str(stock_code).zfill(6)
            logger.info(f'stock_code:{stock_code}')
            # logger.info(f"选中股票代码: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)

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
        self.voice_var = tk.BooleanVar(value=False)
        checkbuttons_info = [
            ("Win", self.win_var),
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var),
            ("Tip", self.tip_var)
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

    def on_voice_toggle(self):
        self.live_strategy.set_voice_enabled(self.voice_var.get())

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
        pending_alert_cycles = CFG.pending_alert_cycles
        st_key_sort = CFG.st_key_sort 
        saved_width,saved_height = CFG.saved_width,CFG.saved_height 
        logger.info(f"reload cfg marketInit : {marketInit} marketblk: {marketblk} \
            scale_offset: {scale_offset} saved_width:{saved_width},{saved_height} \
            duration_sleep_time:{duration_sleep_time} \
            detect_calc_support:{detect_calc_support} \
            alert_cooldown:{alert_cooldown}\
            pending_alert_cycles:{pending_alert_cycles} st_key_sort:{st_key_sort}")
        
        # 同步频率变动到实时服务(如果已连接)
        if hasattr(self, 'realtime_service') and self.realtime_service:
            try:
                self.realtime_service.set_expected_interval(int(duration_sleep_time))
            except:
                pass

    def update_linkage_status(self):
        # 此处处理 checkbuttons 状态
        if not self.tdx_var.get() or not self.ths_var.get():
            self.sender.reload()
        if  self.dfcf_var.get() != self.auto_adjust_column:
            logger.info(f"DC:{self.dfcf_var.get()} self.auto_adjust_column :{self.auto_adjust_column}")
            self.auto_adjust_column = self.dfcf_var.get()
            # self.apply_search()
            # self.after(50, self.adjust_column_widths)
            self._setup_tree_columns(self.tree,self.current_cols, sort_callback=self.sort_by_column, other={})
            self.reload_cfg_value()
            self.live_strategy.set_alert_cooldown(alert_cooldown)
            # self.update_treeview_cols(self.current_cols)

        logger.info(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()}")


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

        # self.show_category_detail(code,name,category_content)
        self.view_stock_remarks(code, name)
        pyperclip.copy(code)



    def on_tree_right_click(self, event):
        """右键点击 TreeView 行"""
        # 确保选中行
        item_id = self.tree.identify_row(event.y)

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
            
            menu.add_command(label="🧪 测试买卖策略", 
                            command=lambda: self.test_strategy_for_stock(stock_code, stock_name))
            
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
            f"📈 连阳: {stock_data.get('red', 'N/A')} 🔺\n"
            f"📉 连阴: {stock_data.get('gren', 'N/A')} 🔻\n"
            f"📈 突破布林: {boll}\n"
            f"  signal: {signal_icon} (low<10 & C>5)\n"
            f"  Upper:  {upper}\n"
            f"  Lower:  {lower}\n"
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
            
            # 特殊别名映射以兼容旧代码
            snapshot['lastv1d'] = snapshot.get('lastv1d', 0)
            snapshot['lastv2d'] = snapshot.get('lastv2d', 0)
            snapshot['lastv3d'] = snapshot.get('lastv3d', 0)
            snapshot['lasth1d'] = snapshot.get('lasth1d', 0)
            snapshot['lastl1d'] = snapshot.get('lastl1d', 0)
            snapshot['win'] = snapshot.get('win', 0)            # 加速连阳
            snapshot['sum_perc'] = snapshot.get('sum_perc', 0)  # 加速连阳涨幅
            snapshot['red'] = snapshot.get('red', 0)            # 五日线上数据
            snapshot['gren'] = snapshot.get('gren', 0)          # 弱势绿柱数据
            snapshot['red'] = snapshot.get('red', 0)  #5日线上日线
            
            # 创建决策引擎实例
            engine = IntradayDecisionEngine()
            
            # 执行评估
            result = engine.evaluate(row_dict, snapshot, mode="full")
            
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
                "【决策结果】",
                f"  动作: {result['action']}",
                f"  仓位: {result['position'] * 100:.0f}%",
                f"  原因: {result['reason']}",
                "",
            ]
            
            # 决策调试信息（优先显示便于分析）
            debug = result.get('debug', {})
            if debug:
                report_lines.append("【决策调试信息】")
                for key, val in debug.items():
                    if isinstance(val, float):
                        report_lines.append(f"  {key}: {val:.4f}")
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
                f"  成交量: {row_dict.get('volume', 'N/A')}",
                f"  换手率: {row_dict.get('ratio', 'N/A')}%",
                f"  昨日量: {snapshot.get('lastv1d', 'N/A')}",
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
            win.attributes("-topmost", True)
            win.after(50, lambda: win.attributes("-topmost", False))
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
            
            # 创建模拟参数设置小窗口
            sim_win = tk.Toplevel(win)
            sim_win.title(f"模拟成交设置 - {name}")
            sim_win_id = '模拟成交设置'
            sim_win.geometry("350x480") # 稍微调大一点适应新控件
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
                            code, name, s_action, s_price, s_amount
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
                        tags = self.get_stock_info_text(code)
                        self.live_strategy.add_monitor(code, name, rtype, val, tags=tags)
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
            self.live_strategy = StockLiveStrategy(alert_cooldown=alert_cooldown,
                                                   voice_enabled=self.voice_var.get(),
                                                   realtime_service=self.realtime_service)
            
            logger.info("RealtimeDataService injected into StockLiveStrategy.")
            
            # 注册报警回调
            self.live_strategy.set_alert_callback(self.on_voice_alert)
            # 注册语音开始播放的回调，用于同步闪烁
            if hasattr(self.live_strategy, '_voice'):
                self.live_strategy._voice.on_speak_start = self.on_voice_speak_start
                self.live_strategy._voice.on_speak_end = self.on_voice_speak_end
            
            logger.info("✅ 实时监控策略模块已启动")
        except Exception as e:
            logger.error(f"Failed to init live strategy: {e}")

    # def on_voice_alert(self, code, name, msg):
    #     """
    #     处理语音报警触发: 弹窗显示股票详情 - 线程安全版本
    #     """
    #     # 线程安全:避免在后台线程中调用 Tkinter
    #     try:
    #         import threading
    #         if threading.current_thread() is threading.main_thread():
    #             self._show_alert_popup(code, name, msg)
    #         else:
    #             # 后台线程:忽略,避免 GIL 问题
    #             pass
    #     except Exception as e:
    #         # 静默失败
    #         pass

    # def on_voice_speak_start(self, code):
    #     """语音开始播报时的回调 (在后台线程调用) - 线程安全版本"""
    #     if not code: 
    #         return
    #     # 使用线程安全的方式调度到主线程
    #     try:
    #         # 检查是否在主线程
    #         import threading
    #         if threading.current_thread() is threading.main_thread():
    #             self._trigger_alert_visual_effects(code, start=True)
    #         else:
    #             # 后台线程:不直接调用 after,而是通过事件标志
    #             # 避免 GIL 问题,简单忽略或使用其他机制
    #             pass
    #     except Exception as e:
    #         # 静默失败,避免崩溃
    #         pass

    # def on_voice_speak_end(self, code):
    #     """语音播报结束的回调 - 线程安全版本"""
    #     if not code: 
    #         return
    #     try:
    #         import threading
    #         if threading.current_thread() is threading.main_thread():
    #             self._trigger_alert_visual_effects(code, start=False)
    #         else:
    #             # 后台线程:简单忽略
    #             pass
    #     except Exception as e:
    #         pass

    def on_voice_alert(self, code, name, msg):
        """
        处理语音报警触发: 弹窗显示股票详情
        """
        # 必须回到主线程操作 GUI
        self.after(0, lambda: self._show_alert_popup(code, name, msg))

    def on_voice_speak_start(self, code):
        """语音开始播报时的回调 (在后台线程调用)"""
        if not code: return
        # 调度到主线程执行闪烁和震动
        self.after(0, lambda: self._trigger_alert_visual_effects(code, start=True))

    def on_voice_speak_end(self, code):
        """语音播报结束的回调"""
        if not code: return
        self.after(0, lambda: self._trigger_alert_visual_effects(code, start=False))


    def _trigger_alert_visual_effects(self, code, start=True):
        """根据代码查找窗口并触发视觉效果"""
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
        重新排列所有报警弹窗。
        优化点：使用 update_idletasks 确保所有窗口位置同时刷新，减少初始化时的视觉闪烁。
        """
        if not hasattr(self, 'active_alerts'):
            self.active_alerts = []
            
        # 定义固定的窗口尺寸和边距
        alert_width, alert_height = 400, 260 
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
        
        for i, win in enumerate(self.active_alerts):
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
                
                x = screen_width - (col + 1) * (alert_width + margin)
                y = screen_height - taskbar_height - (row + 1) * (alert_height + margin)
                
                win.geometry(f"{alert_width}x{alert_height}+{x}+{y}")
                # 确保窗口是可见的（如果之前被隐藏了）
                if not win.winfo_ismapped():
                    win.deiconify() 
            except Exception as e:
                logger.error(f"调整索引 {i} 的警报窗口位置时出错: {e}")

        # *** 关键优化 ***
        # 强制 Tkinter 立即处理所有待定的 geometry() 更新。
        # 这使得所有窗口的位置变化在视觉上是同步的，消除了逐个移动的闪烁感。
        self.update_idletasks()

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

        # 💥 关键点：在获取几何信息前强制更新 UI 布局
        win.update_idletasks()

        def do_shake(orig_wh, orig_x, orig_y):
            # 检查窗口是否存在且是否应继续晃动
            if not win.winfo_exists() or not getattr(win, 'is_shaking', False):
                # 停止晃动时，尝试将窗口恢复到原始位置（如果可能）
                if win.winfo_exists():
                     try:
                         win.geometry(f"{orig_wh}+{orig_x}+{orig_y}")
                     except: 
                         pass
                return
            
            import random
            # 计算随机偏移量
            dx = random.randint(-distance, distance)
            dy = random.randint(-distance, distance)
            try:
                # 应用新的位置
                win.geometry(f"{orig_wh}+{orig_x + dx}+{orig_y + dy}")
            except: 
                pass
            
            # 安排下一次晃动。使用新的 interval_ms 参数控制频率。
            win.after(interval_ms, lambda: do_shake(orig_wh, orig_x, orig_y))

        # 捕获初始位置
        try:
            geom = win.geometry()
            parts = geom.split('+')
            if len(parts) == 3:
                wh = parts[0]
                x = int(parts[1])
                y = int(parts[2])
                do_shake(wh, x, y)
        except:
            # 如果获取几何信息失败，则不执行晃动
            pass

    # def _update_alert_positions_bug(self):
    #     """重新排列所有报警弹窗"""
    #     if not hasattr(self, 'active_alerts'):
    #         self.active_alerts = []
            
    #     # Right-Bottom origin
    #     w, h = 400, 260 # 稍微增高
    #     margin = 10
    #     taskbar = 100 # 避开任务栏
    #     sw = self.winfo_screenwidth()
    #     sh = self.winfo_screenheight()
        
    #     # Max columns that fit
    #     max_cols = (sw - 100) // (w + margin)
    #     if max_cols < 1: max_cols = 1
        
    #     # 清理已销毁的窗口
    #     self.active_alerts = [win for win in self.active_alerts if win.winfo_exists()]

    #     for i, win in enumerate(self.active_alerts):
    #         try:
    #             col = i % max_cols
    #             row = i // max_cols
                
    #             # 从右向左排列
    #             x = sw - (col + 1) * (w + margin)
    #             y = sh - taskbar - (row + 1) * (h + margin)
                
    #             win.geometry(f"{w}x{h}+{x}+{y}")
    #         except Exception as e:
    #             logger.error(f"Resize alert error: {e}")

    # def _shake_window(self, win, distance=8):
    #     """
    #     震动窗口效果 - 持续震动直到 win.is_shaking 变为 False
    #     """
    #     if not win or not win.winfo_exists():
    #         return
        
    #     # 标记正在震动
    #     win.is_shaking = True

    #     # 💥 关键点：在获取几何信息前强制更新 UI 布局
    #     win.update_idletasks()

    #     def do_shake(orig_wh, orig_x, orig_y):
    #         if not win.winfo_exists() or not getattr(win, 'is_shaking', False):
    #             if win.winfo_exists():
    #                  try:
    #                      win.geometry(f"{orig_wh}+{orig_x}+{orig_y}")
    #                  except: pass
    #             return
            
    #         import random
    #         dx = random.randint(-distance, distance)
    #         dy = random.randint(-distance, distance)
    #         try:
    #             win.geometry(f"{orig_wh}+{orig_x + dx}+{orig_y + dy}")
    #         except: pass
            
    #         win.after(40, lambda: do_shake(orig_wh, orig_x, orig_y))

    #     # 捕获初始位置
    #     try:
    #         geom = win.geometry()
    #         parts = geom.split('+')
    #         if len(parts) == 3:
    #             wh = parts[0]
    #             x = int(parts[1])
    #             y = int(parts[2])
    #             do_shake(wh, x, y)
    #     except:
    #         pass

    # def _close_alert_src(self, win, is_manual=False):
    #     """关闭弹窗并刷新布局，并停止关联的语音报警"""
    #     if hasattr(self, 'active_alerts') and win in self.active_alerts:
    #         self.active_alerts.remove(win)
        
    #     # 清理映射并获取关联代码
    #     target_code = None
    #     if hasattr(self, 'code_to_alert_win'):
    #         for c, w in list(self.code_to_alert_win.items()):
    #             if w == win:
    #                 target_code = c
    #                 del self.code_to_alert_win[c]
    #                 break

    #     # 停止该代码的语音播报 (以便立即播放队列中的下一个)
    #     if target_code and hasattr(self, 'live_strategy') and self.live_strategy:
    #          # 如果是手动关闭，则延迟 10 个周期再报
    #          if is_manual:
    #              self.live_strategy.snooze_alert(target_code, cycles=pending_alert_cycles)

    #          v = getattr(self.live_strategy, '_voice', None)
    #          if v and hasattr(v, 'cancel_for_code'):
    #              v.cancel_for_code(target_code)

    #     win.destroy()
    #     # self.after(50, self._update_alert_positions)
    #     # 5. 立即調用重排佈局 (不需要 after() 延遲)
    #     self._update_alert_positions()

    def _close_alert(self, win, is_manual=False):
        """关闭弹窗并刷新布局，并停止关联的语音报警"""

        # ===== [修改点 1] =====
        # 关闭时，立即从 active_alerts 移除（避免后续布局和引用错误）
        if hasattr(self, 'active_alerts') and win in self.active_alerts:
            self.active_alerts.remove(win)

        # ===== [修改点 2] =====
        # 统一在这里清理 code -> window 映射，并获取 target_code
        target_code = None
        if hasattr(self, 'code_to_alert_win'):
            for c, w in list(self.code_to_alert_win.items()):
                if w is win:
                    target_code = c
                    del self.code_to_alert_win[c]
                    break

        # ===== [修改点 3] =====
        # 语音 / 策略处理逻辑统一放在一个块中，避免分支遗漏
        if target_code and getattr(self, 'live_strategy', None):

            # ===== [修改点 3.1] =====
            # 手动关闭：只负责“延迟再报”，不负责停当前语音
            if is_manual:
                self.live_strategy.snooze_alert(
                    target_code,
                    cycles=pending_alert_cycles
                )

            # ===== [修改点 3.2 - 关键修复点] =====
            # 无论手动 / 自动关闭，都必须立即 cancel 当前语音
            # （这是 new 版本出问题的根因）
            v = getattr(self.live_strategy, '_voice', None)
            if v and hasattr(v, 'cancel_for_code'):
                v.cancel_for_code(target_code)

        # ===== [修改点 4] =====
        # 在所有状态清理完成后，再销毁窗口
        win.destroy()

        # ===== [修改点 5] =====
        # 立即重排弹窗位置（不使用 after，避免顺序错乱）
        self._update_alert_positions()



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
            
            # 关闭回调 (手动关闭，设为 True)
            win.protocol("WM_DELETE_WINDOW", lambda: self._close_alert(win, is_manual=True))
            
            # 自动关闭逻辑：
            # 如果语音功能有效，则等待播报结束后才开始计时关闭；
            # 否则立即开始计时，以防窗口无限堆积。
            has_voice = False
            # try:
            #     if hasattr(self, 'live_strategy') and self.live_strategy:
            #         v = getattr(self.live_strategy, '_voice', None)
            #         if v and v._thread and v._thread.is_alive():
            #             # 检查队列容量，如果由于队列满而未加入，则视为无语音同步
            #             if v.queue.qsize() < 10: 
            #                 has_voice = True
            # except: pass
            try:
                if hasattr(self, 'live_strategy') and self.live_strategy:
                    # ✅ 关键：语音开关
                    if not getattr(self.live_strategy, 'voice_enabled', True):
                        has_voice = False
                    else:
                        v = getattr(self.live_strategy, '_voice', None)
                        if (
                            v
                            and v._thread
                            and v._thread.is_alive()
                            and v.queue.qsize() < 10
                        ):
                            has_voice = True
            except Exception as e:
                logger.debug(f"voice detect failed: {e}")

            # 【新增】自动关闭时间兜底
            def _get_alert_close_delay_ms():
                seconds = max(60, int(alert_cooldown / 2))
                return seconds * 1000

            delay_ms = _get_alert_close_delay_ms()

            if not has_voice:
                self.after(delay_ms, lambda: self._close_alert(win))
            else:
                # 安全兜底：如果因为某种原因没触发回调（如语音引擎卡死），3分钟后强制关闭
                win.safety_close_timer = self.after(180000, lambda: self._close_alert(win))
            
            # 闪烁与震动效果 (持续性同步)
            def flash(count=0):
                if not win.winfo_exists() or not getattr(win, 'is_flashing', False):
                    if win.winfo_exists(): win.configure(bg="#fff")
                    return
                bg = "#ffcdd2" if count % 2 == 0 else "#ffebee"
                win.configure(bg=bg)
                win.after(500, lambda: flash(count+1)) # 这里的 500 是闪烁频率（毫秒），数值越大闪得越慢
            
            # 定义供外部触发的方法
            def start_effects():
                if getattr(win, 'is_flashing', False): return # 防止重复触发
                win.is_flashing = True
                flash()
                self._shake_window(win, distance=8,interval_ms=60) # 稍微加大震动幅度
            
            def stop_effects():
                win.is_flashing = False
                win.is_shaking = False
                # 播报结束，启动正常的倒计时关闭 (30-60秒)
                # 如果有安全倒计时，先取消它
                if hasattr(win, 'safety_close_timer'):
                    try: self.after_cancel(win.safety_close_timer)
                    except: pass
                
                self.after(int(alert_cooldown/2)*1000, lambda: self._close_alert(win))
            
            win.start_visual_effects = start_effects
            win.stop_visual_effects = stop_effects
            win.is_flashing = False
            win.is_shaking = False

            # 记录映射用于同步播放
            if not hasattr(self, 'code_to_alert_win'):
                self.code_to_alert_win = {}
            self.code_to_alert_win[code] = win

            # 如果当前没有在排队，或者想立刻由于新窗口弹出而提醒，可以先闪一下（可选）
            # 这里我们遵从用户要求：播放到哪个提示，闪屏哪个窗口
            # 所以我们不在这里主动调用 flash()，而是等 on_voice_speak_start 回调触发
            
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
            
            tk.Button(btn_frame, text="关闭", command=lambda: self._close_alert(win, is_manual=True), bg="#eee").pack(side="right", padx=5)

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
                sell_p = f"{t['sell_price']:.3f}" if t['sell_price'] is not None else "--"
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
        """打开 Qt6 版本的交易分析工具"""
        try:
            if not hasattr(self, "_trading_gui_qt6") or self._trading_gui_qt6 is None:
                # 确保 Qt 环境已初始化
                if not QtWidgets.QApplication.instance():
                    _ = pg.mkQApp()
                
                self._trading_gui_qt6 = TradingGUI(sender=self.sender,on_tree_scroll_to_code=self.tree_scroll_to_code)
                
            self._trading_gui_qt6.show()
            self._trading_gui_qt6.raise_()
            self._trading_gui_qt6.activateWindow()
            toast_message(self, "交易分析工具(Qt6) 已启动")
        except Exception as e:
            logger.error(f"Failed to open TradingGUI Qt6: {e}")
            messagebox.showerror("错误", f"启动 Qt6 分析工具失败: {e}")

    def open_strategy_backtest_view(self):
        """预留：打开策略复盘与AI优化建议视图"""
        messagebox.showinfo("敬请期待", "复盘功能正在开发中，将结合您的反馈进行模型微调。")

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
            
            tk.Button(top_frame, text="开启自动交易", command=lambda: self.live_strategy.start_auto_trading_loop(force=True, concept_top5=getattr(self, 'concept_top5', None)), bg="#fff9c4").pack(side="right", padx=5)
            tk.Button(top_frame, text="测试报警音", command=lambda: self.live_strategy.test_alert(), bg="#e0f7fa").pack(side="right", padx=5)
            win.lift()
            win.focus_force()
            win.attributes("-topmost", True)
            win.after(100, lambda: win.attributes("-topmost", False))
            # --- 列表区域 ---
            list_frame = tk.Frame(win)
            list_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 显示 ID 是为了方便管理 (code + rule_index)
            columns = ("code", "name", "rule_type", "value", "add_time", "tags", "id")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
            
            def treeview_sort_column(tv, col, reverse):
                l = [(tv.set(k, col), k) for k in tv.get_children('')]
                try:
                    l.sort(key=lambda t: float(t[0]), reverse=reverse)
                except ValueError:
                    l.sort(reverse=reverse)

                for index, (val, k) in enumerate(l):
                    tv.move(k, '', index)

                tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))

            tree.heading("code", text="代码", command=lambda: treeview_sort_column(tree, "code", False))
            tree.heading("name", text="名称", command=lambda: treeview_sort_column(tree, "name", False))
            tree.heading("rule_type", text="规则类型", command=lambda: treeview_sort_column(tree, "rule_type", False))
            tree.heading("value", text="阈值", command=lambda: treeview_sort_column(tree, "value", False))
            tree.heading("add_time", text="时间", command=lambda: treeview_sort_column(tree, "add_time", False))
            tree.heading("tags", text="简介", command=lambda: treeview_sort_column(tree, "tags", False))
            tree.heading("id", text="ID (Code_Idx)")
            
            tree.column("code", width=80, anchor="center")
            tree.column("name", width=100, anchor="center")
            tree.column("rule_type", width=150, anchor="center")
            tree.column("value", width=100, anchor="center")
            tree.column("add_time", width=140, anchor="center")
            tree.column("tags", width=50, anchor="center")
            tree.column("id", width=0, stretch=False) # 隐藏 ID 列

            def show_tags_detail(values):
                code, name = values[0], values[1]
                tags_info = values[5]

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

                TAGS_COL_INDEX = 5  # tags 在 values 中的索引

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
                for code, data in monitors.items():
                    name = data['name']
                    rules = data['rules']
                    add_time = data.get('created_time', '')
                    tags = data.get('tags', '')
                    
                    if not rules:
                        # 对于没有规则的股票，显示一行占位，方便管理
                        uid = f"{code}_none"
                        tree.insert("", "end", values=(code, name, "⚠️(未设规则)", "-", add_time, tags, uid))
                    else:
                        for idx, rule in enumerate(rules):
                            rtype_map = {
                                "price_up": "价格突破 >=",
                                "price_down": "价格跌破 <=",
                                "change_up": "涨幅超过 >="
                            }
                            display_type = rtype_map.get(rule['type'], rule['type'])
                            # unique id
                            uid = f"{code}_{idx}"
                            tree.insert("", "end", values=(code, name, display_type, rule['value'], add_time, tags, uid))

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
                     uid = values[6]
                     # 由于 uid 是 'code_idx'，但如果删除了前面的，后面的 idx 会变
                     # 最稳妥的是：倒序删除，或者重新加载。
                     # 我们的界面是单选还是多选？Treeview 默认多选。
                     # 简单处理：只处理第一个
                     # 简单处理：只处理第一个
                     # 处理特殊标记 'code_none'
                     if self.live_strategy:
                         if uid.endswith('_none'):
                             # 如果没有规则，删除操作即移除该监控项
                             self.live_strategy.remove_monitor(code)
                         else:
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

            def edit_selected(item=None, values=None):
                 if values is None:
                    selected = tree.selection()
                    if not selected:
                        return
                    item = selected[0]
                    values = tree.item(item, "values")
                 code = values[0]
                 name = values[1]
                 old_val = values[3]
                 uid = values[6]
                 if uid.endswith('_none'):
                     idx = -1
                 else:
                     try:
                         idx = int(uid.split('_')[1])
                     except:
                         idx = -1
                 # logger.info(f'on_voice_edit_selected stock_code:{code} name:{name}')
                 
                 current_type = "price_up"
                 monitors = self.live_strategy.get_monitors()
                 if code in monitors:
                     rules = monitors[code]['rules']
                     if idx < len(rules):
                         current_type = rules[idx]['type']

                 # 弹出编辑框 (UI 与 Add 保持一致)
                 # edit_win = tk.Toplevel(win)
                 # edit_win.title(f"编辑规则 - {name}")
                 # edit_win_id = "编辑规则"
                 # self.load_window_position(edit_win, edit_win_id, default_width=900, default_height=600)

                 # main_frame = tk.Frame(edit_win)
                 # main_frame.pack(fill="both", expand=True, padx=10, pady=10)
                 
                 # left_frame = tk.Frame(main_frame) 
                 # left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
                 
                 # right_frame = tk.LabelFrame(main_frame, text="参考数据 (点击自动填入)", width=450)
                 # right_frame.pack(side="right", fill="both", padx=(10, 0))
                 # # right_frame.pack_propagate(False)

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
                 # right_frame.minsize(350, 200)


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

                 tk.Label(left_frame, text="规则类型:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))
                 
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
                                 self.live_strategy.add_monitor(code, name, new_type, val)
                         
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
            tk.Button(btn_frame, text="刷新列表", command=load_data).pack(side="left", padx=10)
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
            
        except Exception as e:
            logger.error(f"Voice Monitor Manager Error: {e}")
            messagebox.showerror("错误", f"打开管理窗口失败: {e}")

    def open_stock_selection_window(self):
        """打开策略选股与人工复核窗口 (支持窗口复用)"""
        # ✅ 确保策略模块已尝试初始化
        if not hasattr(self, 'live_strategy') or self.live_strategy is None:
            # 尝试提前初始化 selector
            if not hasattr(self, 'selector'):
                try:
                    self.selector = StockSelector(df=getattr(self, 'df_all', None))
                except Exception as e:
                    logger.error(f"StockSelector 初始化失败: {e}")
                    self.selector = None
        
        # ✅ 窗口复用逻辑
        if self._stock_selection_win and self._stock_selection_win.winfo_exists():
            try:
                self._stock_selection_win.deiconify()
                self._stock_selection_win.lift()
                self._stock_selection_win.focus_force()
                return
            except Exception:
                pass

        try:
            # 实例化选择器 (如果还没有)
            if not hasattr(self, 'selector') or self.selector is None:
                self.selector = StockSelector(df=getattr(self, 'df_all', None))
            
            # 打开窗口
            self._stock_selection_win = StockSelectionWindow(self, self.live_strategy, self.selector)
            
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
            self._search_after_id = self.after(200, refresh_buttons)

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

        self._setup_tree_columns(tree,cols_to_show, sort_callback=sort_func, other={})


        # logger.info(f"[Tree Reset] applied cols={list(tree['columns'])}")


    def tree_scroll_to_code(self, code,select_win=False):
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
            if select_win:
                self.original_push_logic(code)
        except Exception as e:
            logger.info(f"[tree_scroll_to_code] Error: {e}")
            return False

        return False  # 未找到


    def on_tree_click_for_tooltip(self, event,stock_code=None,stock_name=None):
        """处理树视图点击事件，延迟显示提示框"""
        logger.debug(f"[Tooltip] 点击事件触发: x={event.x}, y={event.y}")
        if not self.tip_var.get():
            return
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
            stock_code = str(values[0])  # code在第一列
            stock_name = str(values[1])  # code在第二列
            
        else:
            stock_code = stock_code
        self.test_strategy_for_stock(stock_code, stock_name)
        # x_root, y_root = event.x_root, event.y_root  # 保存坐标
        logger.debug(f"[Tooltip] 获取到代码: {stock_code}, 设置0.2秒定时器")

        # 设置0.2秒延迟定时器
        self._tooltip_timer = self.after(200, lambda e=event:self.show_stock_tooltip(stock_code, e))


    def show_stock_tooltip(self, code, event):
        """显示股票信息提示框，支持位置保存/加载"""
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
        stock_name = stock_data.get('name', code_clean) if hasattr(stock_data, 'get') else code_clean

        logger.debug(f"[Tooltip] 找到股票数据，准备创建提示框")

        # 关闭已存在的 tooltip
        if hasattr(self, '_current_tooltip') and self._current_tooltip:
            try:
                self._current_tooltip.destroy()
            except:
                pass

        # 创建 Toplevel 窗口（带边框，可拖拽）
        window_id = "stock_tooltip"
        win = tk.Toplevel(self)
        win.title(f"📊 {stock_name} ({code_clean})")
        win.configure(bg='#FFF8E7')
        win.resizable(True, True)
        
        # 加载保存的位置，或使用默认位置
        self.load_window_position(win, window_id, default_width=280, default_height=320)
        self._current_tooltip = win

        # ESC / 关闭时保存位置
        def on_close(event=None):
            self.save_window_position(win, window_id)
            win.destroy()
            self._current_tooltip = None
        
        win.bind("<Escape>", on_close)
        win.protocol("WM_DELETE_WINDOW", on_close)

        # 获取多行文本和对应颜色
        lines, colors = self._format_stock_info(stock_data)

        # 创建 Text 控件（无滚动条，用鼠标滚轮滚动）
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
        
        # 绑定鼠标滚轮滚动
        def on_mousewheel(event):
            text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        text_widget.bind("<MouseWheel>", on_mousewheel)
        frame.bind("<MouseWheel>", on_mousewheel)

        for i, (line, color) in enumerate(zip(lines, colors)):
            tag_name = f"line_{i}"
            text_widget.insert(tk.END, line + "\n", tag_name)
            text_widget.tag_config(tag_name, foreground=color, font=("Microsoft YaHei", 9))

            # 检查 signal 行，单独设置图标颜色和大小
            if "signal:" in line:
                icon_index = line.find("👍")
                if icon_index == -1:
                    icon_index = line.find("🚀")
                if icon_index == -1:
                    icon_index = line.find("☀️")

                if icon_index != -1:
                    start = f"{i+1}.{icon_index}"
                    end = f"{i+1}.{icon_index+2}"
                    text_widget.tag_add(f"icon_{i}", start, end)
                    text_widget.tag_config(f"icon_{i}", foreground="#FF6600", font=("Microsoft YaHei", 12, "bold"))

        text_widget.config(state=tk.DISABLED)

        # 底部关闭按钮
        btn_frame = tk.Frame(win, bg='#FFF8E7')
        btn_frame.pack(fill='x', pady=3)
        tk.Button(btn_frame, text="关闭 (ESC)", command=on_close, width=10).pack()

        logger.debug(f"[Tooltip] 提示框已创建")

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
            'green',         # 连阴
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
            # 基础集约化：7像素/字符，最小宽45
            width = int(min(max(max_len * 7, int(45 * self.get_scaled_value())), 350))

            if col == 'name':
                width = int(getattr(self, "_name_col_width", 120 * self.scale_factor))
            elif col == 'code':
                # 代码列 6 位，80 像素足够
                width = int(80 * self.scale_factor)
            elif col in ['ra', 'ral', 'win', 'red', 'kind', 'fib', 'fibl', 'op']:
                # 极窄技术指标列
                width = int(45 * self.scale_factor)

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
                clipboard_text = f'category.str.contains("^{matches[0]}")'

        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)


    def _on_label_on_code_click(self, code,idx):
        self._update_selection_top10(idx)
        """点击异动窗口中的股票代码"""
        self.select_code = code

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

        # 主体 Treeview
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        columns = ("code", "name", "percent", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量","red":"连阳","win":"主升"}
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

        columns = ("code", "name", "percent", "volume","red","win")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量"}
        col_texts = {"code":"代码","name":"名称","percent":"涨幅(%)","volume":"成交量","red":"连阳","win":"主升"}
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
                    latest_row.get("win", row.get("win", 0)),
                ),
                tags=tuple(row_tags)
            )


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
                        values=(code_row, row["name"], f"{percent:.2f}", f"{row.get('volume',0):.1f}", f"{row.get('red',0)}", f"{row.get('win',0)}"),tags=tuple(tags_for_row))

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

        self.dpi_scale =  1

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

                    if event.button() == QtCore.Qt.MouseButton.LeftButton:
                        self._call_concept_top10_win(code, concepts[idx])
                        win.raise_()
                        win.activateWindow()

                    elif event.button() == QtCore.Qt.MouseButton.RightButton:
                        concept_text = concepts[idx]
                        clipboard = QtWidgets.QApplication.clipboard()
                        copy_concept_text = f'category.str.contains("{concept_text}")'
                        clipboard.setText(copy_concept_text)

                        from PyQt6.QtCore import QPoint
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
            
            if key == QtCore.Qt.Key.Key_R:
                self.plot_following_concepts_pg(code, top_n)
                event.accept()

            elif key in (QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_Escape):
                QtCore.QTimer.singleShot(0, win.close)
                event.accept()

            elif key == QtCore.Qt.Key.Key_Up:
                current_idx["value"] = max(0, current_idx["value"] - 1)
                highlight_bar(current_idx["value"])
                self._call_concept_top10_win(code, concepts[current_idx["value"]])
                win.raise_()
                win.activateWindow()
                event.accept()

            elif key == QtCore.Qt.Key.Key_Down:
                current_idx["value"] = min(len(concepts) - 1, current_idx["value"] + 1)
                highlight_bar(current_idx["value"])
                self._call_concept_top10_win(code, concepts[current_idx["value"]])
                win.raise_()
                win.activateWindow()
                event.accept()

            elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
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
        # --- 调试输出 ---
        # logger.info(f'_refresh_pg_window top_concepts_sorted : {top_concepts_sorted} unique_code: {unique_code} ')
        logger.info(f'更新图形: {unique_code} : {concepts}')
        # --- 更新图形 ---
        self.update_pg_plot(w_dict, concepts, scores, avg_percents, follow_ratios)

        logger.info(f"[Auto] 已自动刷新 {code}")


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

        # ====== 条件清理 ======
        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2️⃣ 替换掉原 query 中的这些部分
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

            # 提取条件中的列名
            cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

            # 所有列都必须存在才保留
            if all(col in self.df_all.columns for col in cols_in_cond):
                valid_conditions.append(cond_clean)
            else:
                removed_conditions.append(cond_clean)

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
        # if any('index.' in c.lower() for c in valid_conditions):
        #     query_engine = 'python'
        # 1️⃣ index 条件 → python
        if any('index.' in c.lower() for c in valid_conditions):
            query_engine = 'python'
        
        # 2️⃣ 字符串条件 → 禁止进 query
        STR_OPS = ('.str.', 'contains(', 'startswith(', 'endswith(')
        has_str_op = any(any(op in c.lower() for op in STR_OPS) for c in valid_conditions)

        if has_str_op:
            query_engine = 'python'   # 即便 python，也不能放进 query

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
                        self.df_all['category'] = self.df_all['category'].astype('string')
                        # self.df_all['category'] = self.df_all['category'].astype(str).str.strip()
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
            logger.error(f"final_query: {final_query} query_check: {([c for c in self.df_all.columns if not c.isidentifier()])}")
            logger.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")
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

            auto_chk = tk.Checkbutton(perf_frame, text="Auto Guard(Clip at 500MB)", variable=auto_var, command=on_auto_switch, font=("Microsoft YaHei", 9))
            auto_chk.pack(side="left", padx=5)

            # Simple text area for status and logs
            text_area = tk.Text(log_win, font=("Consolas", 10), bg="#f0f0f0")
            text_area.pack(fill="both", expand=True, padx=5, pady=5)
            
            # 定义关闭回调
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
                msg += f"Uptime         : {uptime_str}\n"
                msg += f"Memory Usage   : {status.get('memory_usage', 'N/A')}\n"
                msg += f"CPU Usage      : {status.get('cpu_usage', 0):.1f}%\n"
                msg += "-" * 35 + "\n"
                msg += f"Stocks Cached  : {status.get('klines_cached', 0)}\n"
                
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
                if ext_status and 'df' in ext_status:
                    df_ext = ext_status['df']
                    remote_ts = ext_status.get('last_update', 0)
                    
                    # 同步给策略模块
                    if hasattr(self, 'live_strategy') and self.live_strategy:
                        self.live_strategy.ext_data_55188 = df_ext
                        self.live_strategy.last_ext_update_ts = remote_ts
                    
                    if remote_ts > self.last_ext_data_ts_local:
                        local_time = datetime.datetime.fromtimestamp(int(ts))
                        local_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
                        duration_time = time_start_55188
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
            self.after(duration_sleep_time*1000, self._check_ext_data_update)

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
        self.status_var.set(f"Rows: {cnt} | blkname: {self.blkname} | resample: {resample} | st: {self.st_key_sort} | search: {search}")


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
                                    
# --- DPI and Config methods moved to Mixins ---
# --- Duplicate window methods removed ---

# KLineMonitor class moved to kline_monitor.py

def test_single_thread():
    import queue
    # 用普通 dict 代替 manager.dict()
    global marketInit,resampleInit
    shared_dict = {}
    shared_dict["resample"] = resampleInit
    shared_dict["market"] = marketInit

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
    fetch_and_process(shared_dict, q, blkname="boll", flag=flag ,log_level=log_level,detect_calc_support_var=detect_calc_support)

# 常用命令示例列表
COMMON_COMMANDS = [
    "tdd.get_tdx_Exp_day_to_df('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df('300')",
    "tdd.get_tdx_exp_low_or_high_power('000002', dl=60, newdays=0, resample='d')",
    "tdd.h5a.check_tdx_all_df_Sina('sina_data')",
    "tdd.h5a.check_tdx_all_df_Sina('get_sina_all_ratio')",
    "write_to_hdf()",
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
    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)

    app.mainloop()
    

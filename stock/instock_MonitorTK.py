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
import pandas as pd
import re
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd
import win32pipe, win32file
from datetime import datetime, timedelta
import shutil
import ctypes
import platform
from screeninfo import get_monitors
import pyperclip  # 用于复制到剪贴板
log = LoggerFactory.log
# log.setLevel(log_level)
# log.setLevel(LoggerFactory.DEBUG)
# log.setLevel(LoggerFactory.INFO)
# -------------------- 常量 -------------------- #
sort_cols, sort_keys = ct.get_market_sort_value_key('3 0')
DISPLAY_COLS = ct.get_Duration_format_Values(
    ct.Monitor_format_trade,sort_cols[:2])
# print(f'DISPLAY_COLS : {DISPLAY_COLS}')
# DISPLAY_COLS = ct.get_Duration_format_Values(
# ct.Monitor_format_trade,
#     ['name','trade','boll','dff','df2','couts','percent','volume','category']
# )

# ct_MonitorMarket_Values=ct.get_Duration_format_Values(
#                     ct.Monitor_format_trade, market_sort_value[:2])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DARACSV_DIR = os.path.join(BASE_DIR, "datacsv")
WINDOW_CONFIG_FILE = os.path.join(BASE_DIR, "window_config.json")
SEARCH_HISTORY_FILE = os.path.join(DARACSV_DIR, "search_history.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archives")
icon_path = os.path.join(BASE_DIR, "MonitorTK.ico")
# icon_path = os.path.join(BASE_DIR, "MonitorTK.png")
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(DARACSV_DIR, exist_ok=True)
START_INIT = 0
# st_key_sort = '3 0'


CONFIG_FILE = "display_cols.json"
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

# # -----------------------------
# # 初始化显示器信息（程序启动时调用一次）
# # -----------------------------
# MONITORS = []  # 全局缓存



# # # 双屏幕,上屏新建
# # def init_monitors():
# #     """扫描所有显示器并缓存信息（使用可用区域，避开任务栏）"""
# #     global MONITORS
# #     monitors = get_all_monitors()  # 原来的函数
# #     if not monitors:
# #         left, top, right, bottom = get_monitor_workarea()
# #         MONITORS = [(left, top, right, bottom)]
# #     else:
# #         # 对每个 monitor 也可计算可用区域
# #         MONITORS = []
# #         for mon in monitors:
# #             # mon = (x, y, width, height)
# #             mx, my, mw, mh = mon
# #             MONITORS.append((mx, my, mx+mw, my+mh))
# #     print(f"✅ Detected {len(MONITORS)} monitor(s).")

# def get_all_monitors():
#     """返回所有显示器的边界列表 [(left, top, right, bottom), ...]"""
#     monitors = []
#     for handle_tuple in win32api.EnumDisplayMonitors():
#         info = win32api.GetMonitorInfo(handle_tuple[0])
#         monitors.append(info["Monitor"])  # (left, top, right, bottom)
#     return monitors

# def init_monitors():
#     """扫描所有显示器并缓存信息"""
#     global MONITORS
#     MONITORS = get_all_monitors()
#     if not MONITORS:
#         # 至少保留主屏幕
#         screen_width = win32api.GetSystemMetrics(0)
#         screen_height = win32api.GetSystemMetrics(1)
#         MONITORS = [(0, 0, screen_width, screen_height)]
#     print(f"✅ Detected {len(MONITORS)} monitor(s).")


# init_monitors()

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
def clamp_window_to_screens(x, y, w, h):
    """
    保证窗口 (x, y, w, h) 位于可见的显示器范围内。
    - 自动检测所有显示器
    - 若不在任何显示器内，则放主屏左上角
    - 自动修正超出边界的情况
    """
    # 获取所有显示器信息
    monitors = []
    try:
        for handle_tuple in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(handle_tuple[0])
            monitors.append(info["Monitor"])  # (left, top, right, bottom)
    except Exception:
        pass

    # 如果检测不到，默认用主屏幕
    if not monitors:
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        monitors = [(0, 0, screen_width, screen_height)]

    # 检查窗口位置是否在任何显示器内
    for left, top, right, bottom in monitors:
        if left <= x < right and top <= y < bottom:
            # 修正窗口不要超出边界
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            print(f"✅ clamp_window_to_screens: 命中屏幕 ({left},{top},{right},{bottom}) -> ({x},{y})")
            return x, y

    # 完全不在屏幕内 -> 放主屏左上角
    left, top, right, bottom = monitors[0]
    print(f"⚠️ clamp_window_to_screens: 未命中屏幕，放主屏 (465, 442)")
    return (465, 442)



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
#             print(f"✅ 命中屏幕 ({left},{top},{right},{bottom}) DPI={dpi_scale:.2f} → ({new_x},{new_y})")
#             return new_x, new_y

#     print(f"⚠️ 未命中任何屏幕，使用默认位置 {default_pos}")
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

    if not isinstance(df_code, pd.DataFrame) or df_code.empty:
        print("df_code : empty or invalid")
        return

    results = []
    ignore_keywords = {"and", "or", "not", "True", "False", "None"}

    for q in queries:
        expr = q.get("query", "")
        # hit = False
        hit_count = 0
        try:
            # 用 DataFrame.query() 执行逻辑表达式
            missing_cols = [col for col in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expr)
                            if col not in df_code.columns and col not in ignore_keywords]
            if missing_cols:
                print(f"缺少字段: {missing_cols}")
                continue
                
            df_hit = df_code.query(expr)
            # 命中条件：返回非空
            # hit = not df_hit.empty
            hit_count = len(df_hit)
        except Exception as e:
            print(f"[ERROR] 执行 query 出错: {expr}, {e}")
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


import datetime as dt

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
        now = dt.datetime.now()
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



# ------------------ 后台数据进程 ------------------ #
def fetch_and_process(shared_dict,queue, blkname="boll", flag=None):
    global START_INIT
    g_values = cct.GlobalValues(shared_dict)  # 主进程唯一实例
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", "all")        # all / sh / cyb / kcb / bj
    blkname = g_values.getkey("blkname", "061.blk")  # 对应的 blk 文件
    print(f"当前选择市场: {market}, blkname={blkname}")
    st_key_sort =  g_values.getkey("st_key_sort", "3 0") 
    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(st_key_sort)
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    print(f"init resample: {resample} flag.value : {flag.value}")
    while True:
        # print(f'resample : new : {g_values.getkey("resample")} last : {resample} st : {g_values.getkey("st_key_sort")}')
        # if flag is not None and not flag.value:   # 停止刷新
        # print(f'worktime : {cct.get_work_time()} {not cct.get_work_time()} , START_INIT : {START_INIT}')
        time_s = time.time()
        if not flag.value:   # 停止刷新
               time.sleep(1)
               # print(f'flag.value : {flag.value} 停止更新')
               continue
        elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
            print(f'resample : new : {g_values.getkey("resample")} last : {resample} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
            # print(f'market : new : {g_values.getkey("market")} last : {market} ')
            top_all = pd.DataFrame()
            lastpTDX_DF = pd.DataFrame()
        elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
            # print(f'st_key_sort : new : {g_values.getkey("st_key_sort")} last : {st_key_sort} ')
            st_key_sort = g_values.getkey("st_key_sort")
        elif START_INIT > 0 and (not cct.get_work_time()):
                # print(f'not worktime and work_duration')
                for _ in range(5):
                    if not flag.value: break
                    time.sleep(1)
                continue
        else:
            print(f'start work : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')
        try:
            # resample = cct.GlobalValues().getkey("resample") or "d"
            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", "all")        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", "061.blk")  # 对应的 blk 文件
            print(f"resample: {resample} flag.value : {flag.value} blkname :{blkname} market : {market}")
            top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                log.debug("no data fetched")
                print("top_now.empty no data fetched")
                time.sleep(ct.duration_sleep_time)
                continue

            if top_all.empty:
                if lastpTDX_DF.empty:
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl= ct.Resample_LABELS_Days[resample], resample=resample)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            print(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
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
            # print(f'DISPLAY_COLS:{DISPLAY_COLS}')
            # print(f'col: {top_temp.columns.values}')
            # top_temp = top_temp.loc[:, DISPLAY_COLS]
            print(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape}')
            queue.put(top_temp)
            gc.collect()
            print(f'now: {cct.get_now_time_int()} time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{ct.duration_sleep_time} resample:{resample}')
            # time.sleep(ct.duration_sleep_time)
            for _ in range(ct.duration_sleep_time*2):
                if not flag.value: break
                time.sleep(0.5)
            START_INIT = 1
            # log.debug(f'fetch_and_process timesleep:{ct.duration_sleep_time} resample:{resample}')
        except Exception as e:
            log.error(f"Error in background process: {e}", exc_info=True)
            time.sleep(ct.duration_sleep_time / 2)

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
    print(f'ratio_t: {round(ratio_t,2)}')
    top_all['volume'] = list(
        map(lambda x, y: round(x / y / ratio_t, 1),
            top_all['volume'].values,
            top_all.last6vol.values)
    )
    now_time = cct.get_now_time_int()
    if  cct.get_trade_date_status():    
        if 'lastbuy' in top_all.columns:
            if 915 < now_time < 930:
                top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            elif 926 < now_time < 1455:
                top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            else:
                top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
        else:
            top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    else:
        top_all['dff'] = ((top_all['buy'] - top_all['df2']) / top_all['df2'] * 100).round(1)

    return top_all.sort_values(by=['dff','percent','volume','ratio','couts'], ascending=[0,0,0,1,1])

# ------------------ 指标计算 ------------------ #
# def calc_indicators(top_all, resample):
#     if cct.get_trade_date_status():
#         for co in ['boll', 'df2']:
#             top_all[co] = list(
#                 map(lambda x, y, m, z: z + (1 if (x > y) else 0),
#                     top_all.close.values,
#                     top_all.upper.values,
#                     top_all.llastp.values,
#                     top_all[co].values)
#             )


#     def calc_virtual_volume_ratio(current_vol, avg_vol):
#         est_volume, passed_ratio, vol_ratio = estimate_virtual_volume_simple(
#             current_vol, avg_vol, now=None
#         )
#         return round(vol_ratio, 1)  # 返回虚拟量比（如 1.3 表示今日预计量是均量的1.3倍）
#     # --- 计算实时虚拟成交量 ---
#     ratio_t = cct.get_work_time_ratio(resample=resample)  # 已开市时间比例（如 0.35）
#     # 如果当前为交易中，则将 volume 转换为预估全天成交量
#     # 更新 DataFrame 中的 volume 列为“虚拟量比”
#     top_all["volume"] = list(
#         map(calc_virtual_volume_ratio,
#             top_all["volume"].values,
#             top_all["last6vol"].values)
#     )

#     # --- 与均量比 ---
#     top_all['volume'] = list(
#         map(lambda x, y: round(x / y / ratio_t, 1),
#             top_all['volume'].values,
#             top_all.last6vol.values)
#     )

#     # --- 差值计算 ---
#     now_time = cct.get_now_time_int()
#     if cct.get_trade_date_status():
#         if 'lastbuy' in top_all.columns:
#             if 915 < now_time < 930:
#                 top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
#                 top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
#             elif 926 < now_time < 1455:
#                 top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
#                 top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
#             else:
#                 top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
#                 top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
#         else:
#             top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
#     else:
#         top_all['dff'] = ((top_all['buy'] - top_all['df2']) / top_all['df2'] * 100).round(1)

#     # --- 排序 ---
#     return top_all.sort_values(by=['dff', 'percent', 'volume', 'ratio', 'couts'], ascending=[0, 0, 0, 1, 1])



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
            # print(f'handle : {handle}')
            win32file.WriteFile(handle, code.encode("utf-8"))
            win32file.CloseHandle(handle)
            return True
        except Exception as e:
            print("发送失败，重试中...", e)
            time.sleep(0.5)
    return False

def list_archives():
    """列出所有存档文件"""
    files = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith("search_history") and f.endswith(".json")],
        reverse=True
    )
    return files


def archive_search_history_list(MONITOR_LIST_FILE=SEARCH_HISTORY_FILE,ARCHIVE_DIR=ARCHIVE_DIR):
    """归档监控文件，避免空或重复存档"""

    if not os.path.exists(MONITOR_LIST_FILE):
        print("⚠ search_history.json 不存在，跳过归档")
        return

    try:
        with open(MONITOR_LIST_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        print(f"⚠ 无法读取监控文件: {e}")
        return

    if not content or content in ("[]", "{}"):
        print("⚠ search_history.json 内容为空，跳过归档")
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
    print(f"✅ 已归档监控文件: {dest}")
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
        super().__init__()
        # self.queue = queue
        self.title("Stock Monitor")
        self.load_window_position(self, "main_window")
        self.iconbitmap(icon_path)  # Windows 下 .ico 文件
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

        # 刷新开关标志
        self.refresh_enabled = True
        from multiprocessing import Manager
        self.manager = Manager()
        self.global_dict = self.manager.dict()  # 共享字典
        self.global_dict["resample"] = 'w'
        self.global_values = cct.GlobalValues(self.global_dict)
        resample = self.global_values.getkey("resample")
        print(f'app init getkey resample:{self.global_values.getkey("resample")}')
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

        # self.lbl_category_result = tk.Label(self, text="", fg="green", anchor="w")
        # self.lbl_category_result.pack(fill="x", padx=5, pady=(0, 4))


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
        pw.add(left_frame, minsize=100, width=850)
        pw.add(right_frame, minsize=100, width=150)


        # 设置初始 6:4 比例
        # self.update_idletasks()           # 先刷新窗口获取宽度
        # total_width = pw.winfo_width()
        # pw.sash_place(0, int(total_width * 0.6), 0)

        # 初始化内容
        # self.status_var_left.set("Ready")
        # self.status_var_right.set("Rows: 0")

        # # 底部容器
        # bottom_frame = tk.Frame(self, bg="#f0f0f0")
        # bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # # 左边状态栏
        # left_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
        # left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # self.status_var = tk.StringVar()
        # self.status_label1 = tk.Label(left_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, bg="#f0f0f0", padx=10, pady=2)
        # self.status_label1.pack(fill=tk.X)

        # # 右边任务状态
        # right_frame = tk.Frame(bottom_frame, bg="#f0f0f0")
        # right_frame.pack(side=tk.RIGHT)

        # self.status_var2 = tk.StringVar()
        # self.status_label2 = tk.Label(right_frame, textvariable=self.status_var2, relief=tk.SUNKEN, anchor=tk.W, bg="#f0f0f0", padx=10, pady=2)
        # self.status_label2.pack(fill=tk.X, expand=True)




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
            self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
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
        # 启动后台进程
        self._start_process()

        # 定时检查队列
        self.after(1000, self.update_tree)



        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=self.update_send_status)




        # # ========== 右键菜单 ==========
        # self.tree_menu = tk.Menu(self, tearoff=0)
        # self.tree_menu.add_command(label="打开报警中心", command=lambda: open_alert_center(self))
        # self.tree_menu.add_command(label="新建报警规则", command=self.open_alert_rule_new)
        # self.tree_menu.add_command(label="编辑报警规则", command=self.open_alert_rule_edit)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Tree selection event
        # self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)  
        self.tree.bind("<Button-1>", self.on_single_click)

        # 绑定右键点击事件
        self.tree.bind("<Button-3>", self.on_tree_right_click)


        self.bind("<Alt-c>", lambda e:self.open_column_manager())

        # 绑定双击事件
        # self.tree.bind("<Double-1>", self.on_double_click)

    def bind_treeview_column_resize(self):
        def on_column_release(event):
            # # 获取当前列宽
            # col_widths = {col: self.tree.column(col)["width"] for col in self.tree["columns"]}
            # print("当前列宽：", col_widths)

            # # 如果需要，可以单独保存name列宽
            # if "name" in col_widths:
            #     self._name_col_width = col_widths["name"]
            #     print("name列宽更新为:", self._name_col_width)

            # 只记录 name 列宽
            if "name" in self.tree["columns"]:
                self._name_col_width = self.tree.column("name")["width"]
                # print("name列宽更新为:", self._name_col_width)

        self.tree.bind("<ButtonRelease-1>", on_column_release)


    def update_treeview_cols(self, new_cols):
        try:
            # 1. 合法列
            valid_cols = [c for c in new_cols if c in self.df_all.columns]
            if 'code' not in valid_cols:
                valid_cols = ["code"] + valid_cols

            # 相同就跳过
            if valid_cols == self.current_cols:
                return

            self.current_cols = valid_cols

            # 2. 暂时清空列
            self.tree["displaycolumns"] = ()
            self.tree["columns"] = ()
            self.tree.update_idletasks()

            # 3. 重新配置列
            cols = tuple(self.current_cols)
            self.tree["columns"] = cols
            self.tree["displaycolumns"] = cols
            self.tree.configure(show="headings")

            # 4. 设置列宽
            if not hasattr(self, "_name_col_width"):
                self._name_col_width = 60  # 初始name列宽

            # for col in cols:
            #     self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
            #     if col == "name":
            #         # 固定name列宽
            #         self.tree.column(col, width=self._name_col_width, anchor="center", minwidth=50, stretch=False)
            #     else:
            #         # 其他列自动宽度
            #         self.tree.column(col, width=60, anchor="center", minwidth=50, stretch=True)

            co2int = ['ra','ral','fib','fibl','op', 'ratio','top10','ra']
            co2width = ['boll','kind','red']   
            for col in cols:
                self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))

                if col == "name":
                    width = getattr(self, "_name_col_width", 120)  # 使用记录的 name 宽度
                    minwidth = 50
                    self.tree.column(col, width=self._name_col_width, anchor="center", minwidth=minwidth, stretch=False)
                elif col in co2int:
                    width = 60  # 数字列宽度可小
                    minwidth = 20
                    self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)
                elif col in co2width:
                    width = 60  # 数字列宽度可小
                    minwidth = 30
                    self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)
                else:
                    width = 80
                    minwidth = 50
                    self.tree.column(col, width=width, anchor="center", minwidth=minwidth, stretch=True)


            # 5. 延迟刷新
            self.tree.after(100, self.refresh_tree)
            self.tree.after(500, self.bind_treeview_column_resize)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("更新 Treeview 列失败：", e)


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
    #         print("更新 Treeview 列失败：", e)



    # def update_treeview_cols(self, new_cols):
    #     try:
    #         # 🔹 1. 保证 new_cols 合法：必须存在于 df_all.columns 中
    #         valid_cols = [c for c in new_cols if c in self.df_all.columns]
    #         if 'code' not in valid_cols:
    #             valid_cols = ["code"] + valid_cols

    #         # 如果完全相同就跳过
    #         if valid_cols == self.current_cols:
    #             return

    #         # print(f"[update_treeview_cols] current={self.current_cols}, new={valid_cols}")

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
    #         print("更新 Treeview 列失败：", e)


    


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
            tk.Label(win, text=f"股票: {stock_str}", font=("Arial", 12, "bold")).pack(pady=1)

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
            log.info(f"保存报警规则: {rule}")
            stock_code = rule.get("stock")  # 或者从 UI 里获取选中的股票代码
            print(f'stock_code:{stock_code}')
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
            "创业板": {"code": "cyb", "blkname": "063.blk"},
            "科创板": {"code": "kcb", "blkname": "064.blk"},
            "北证": {"code": "bj",  "blkname": "065.blk"},
        }

        self.market_combo = ttk.Combobox(
            ctrl_frame,
            values=list(self.market_map.keys()),  # 显示中文
            width=8,
            state="readonly"
        )
        self.market_combo.current(0)  # 默认 "全部"
        self.market_combo.pack(side="left", padx=5)

        # 绑定选择事件，存入 GlobalValues
        def on_market_select(event=None):
            market_cn = self.market_combo.get()
            market_info = self.market_map.get(market_cn, {"code": "all", "blkname": "061.blk"})
            self.global_values.setkey("market", market_info["code"])
            self.global_values.setkey("blkname", market_info["blkname"])
            print(f"选择市场: {market_cn}, code={market_info['code']}, blkname={market_info['blkname']}")

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
        self.alert_manager = AlertManager(storage_dir=DARACSV_DIR, logger=log)
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

        # self.search_history1, self.search_history2 = self.load_search_history()
        self.search_history1, self.search_history2 = self.query_manager.load_search_history()

        # 从 query_manager 获取历史
        h1, h2 = self.query_manager.history1, self.query_manager.history2

        # 提取 query 字段用于下拉框
        self.search_history1 = [r["query"] for r in h1]
        self.search_history2 = [r["query"] for r in h2]   

        # 其他功能按钮
        # tk.Button(ctrl_frame, text="清空", command=self.clean_search).pack(side="left", padx=2)
        # tk.Button(ctrl_frame, text="删除历史", command=self.delete_search_history).pack(side="left", padx=2)

        tk.Button(bottom_search_frame, text="搜索", command=lambda: self.apply_search()).pack(side="left", padx=3)
        tk.Button(bottom_search_frame, text="清空", command=lambda: self.clean_search(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="删除", command=lambda: self.delete_search_history(1)).pack(side="left", padx=2)
        tk.Button(bottom_search_frame, text="管理", command=lambda: self.open_column_manager()).pack(side="left", padx=2)


        # 功能选择下拉框（固定宽度）
        options = ["Query编辑","停止刷新", "启动刷新" , "保存数据", "读取存档", "报警中心","覆写TDX"]
        self.action_var = tk.StringVar()
        self.action_combo = ttk.Combobox(
            bottom_search_frame, textvariable=self.action_var,
            values=options, state="readonly", width=10
        )
        self.action_combo.set("功能选择")
        self.action_combo.pack(side="left", padx=10, pady=1, ipady=1)

        def run_action(action):

            if action == "Query编辑":
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
    #         print(f"diff : ({old_col}, {new_col})")
    #         print(f"old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}")

    #         # 🧩 Step 1. 数据检查
    #         if self.df_all is None or self.df_all.empty:
    #             print("⚠️ df_all 为空，无法替换列。")
    #             return
    #         if new_col not in self.df_all.columns:
    #             print(f"⚠️ 新列 {new_col} 不存在于 df_all.columns，跳过。")
    #             return

    #         # 🧩 Step 2. 获取 Tree 当前列
    #         current_tree_cols = list(self.tree["columns"])

    #         # old_col 不在当前 tree，直接跳过
    #         if old_col not in current_tree_cols:
    #             print(f"⚠️ {old_col} 不在 TreeView columns：{current_tree_cols}")
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
    #             print(f"⚠️ {old_col} 不在 current_cols，追加新列 {new_col}")
    #             if new_col not in self.current_cols:
    #                 self.current_cols.append(new_col)

    #         # 🧩 Step 5. 过滤无效列（仅保留 df_all 中存在的）
    #         self.current_cols = [c for c in self.current_cols if c in self.df_all.columns]

    #         # 🧩 Step 6. 调用安全更新函数
    #         self.update_treeview_cols(self.current_cols)

    #         print(f"✅ 替换完成：{old_col} → {new_col}")
    #     except Exception as e:
    #         import traceback
    #         traceback.print_exc()
    #         print(f"❌ 替换列时出错：{e}")


    def replace_st_key_sort_col(self, old_col, new_col):
        """替换显示列并刷新表格"""
        if old_col in self.current_cols and new_col not in self.current_cols:
            print(f'old_col : {old_col} new_col {new_col} self.current_cols : {self.current_cols}')
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
            #         print(f"⚠️ Treeview 没有列 {col}，跳过")
            # # 重新加载数据
            # self.refresh_tree(self.df_all)


    def on_st_key_sort_enter(self, event):
        sort_val = self.st_key_sort_value.get()
        # try:
        #     nums = list(map(int, sort_val.strip().split()))
        #     if len(nums) != 2:
        #         raise ValueError
        # except:
        #     print("输入格式错误，例如：'3 0'")
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

        def first_diff(old_cols, new_cols):
            for old, new in zip(old_cols, new_cols):
                if old != new:
                    return old, new
            return None

        if sort_val:
            # global DISPLAY_COLS
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
            # print(f'DISPLAY_COLS : {DISPLAY_COLS}')
            # print(f'DISPLAY_COLS_2 : {DISPLAY_COLS_2}')
            diff = first_diff(self.current_cols[1:], DISPLAY_COLS_2)
            if diff:
                print(f'diff : {diff}')
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
        print(f'set resample : {resample}')
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
        # self.proc = mp.Process(target=fetch_and_process, args=(self.queue,))
        self.proc = mp.Process(target=fetch_and_process, args=(self.global_dict,self.queue, "boll", self.refresh_flag))
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
            print(f'refresh_flag.value : {self.refresh_flag.value}')
        self.status_var.set("刷新已停止")

    def start_refresh(self):
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = True
            print(f'refresh_flag.value : {self.refresh_flag.value}')
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
        try:
            if self.refresh_enabled:  # ✅ 只在启用时刷新
                while not self.queue.empty():
                    df = self.queue.get_nowait()
                    # print(f'df:{df[:1]}')
                    if self.sortby_col is not None:
                        print(f'update_tree sortby_col : {self.sortby_col} sortby_col_ascend : {self.sortby_col_ascend}')
                        df = df.sort_values(by=self.sortby_col, ascending=self.sortby_col_ascend)
                    self.df_all = df.copy()
                    if self.search_var1.get() or self.search_var2.get():
                        self.apply_search()
                    else:
                        self.refresh_tree(df)
                    self.status_var2.set(f'queue update: {self.format_next_time()}')
        except Exception as e:
            log.error(f"Error updating tree: {e}", exc_info=True)
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
            log.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            log.error(f"推送 stock_info 出错: {e} {row}")
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
            log.info(f'stock_code:{stock_code}')
            # print(f"选中股票代码: {stock_code}")
            if send_tdx_Key and stock_code:
                self.sender.send(stock_code)


    def update_send_status(self, status_dict):
        # 更新状态栏
        status_text = f"TDX: {status_dict['TDX']} | THS: {status_dict['THS']} | DC: {status_dict['DC']}"
        # self.status_var.set(status_text)
        # print(status_text)

    # ----------------- Checkbuttons ----------------- #
    def init_checkbuttons(self, parent_frame):
        frame_right = tk.Frame(parent_frame, bg="#f0f0f0")
        frame_right.pack(side=tk.RIGHT, padx=2, pady=1)

        self.tdx_var = tk.BooleanVar(value=True)
        self.ths_var = tk.BooleanVar(value=True)
        self.dfcf_var = tk.BooleanVar(value=False)
        # self.uniq_var = tk.BooleanVar(value=False)
        # self.sub_var = tk.BooleanVar(value=False)
        # ("Uniq", self.uniq_var),
        # ("Sub", self.sub_var)

        checkbuttons_info = [
            ("TDX", self.tdx_var),
            ("THS", self.ths_var),
            ("DC", self.dfcf_var),
        ]
        for text, var in checkbuttons_info:
            cb = tk.Checkbutton(frame_right, text=text, variable=var, command=self.update_linkage_status,
                                bg="#f0f0f0", font=('Microsoft YaHei', 9),
                                padx=0, pady=0, bd=0, highlightthickness=0)
            cb.pack(side=tk.LEFT, padx=1)

    def update_linkage_status(self):
        # 此处处理 checkbuttons 状态
        if not self.tdx_var.get() or self.ths_var.get() or self.dfcf_var.get():
            self.sender.reload()
        print(f"TDX:{self.tdx_var.get()}, THS:{self.ths_var.get()}, DC:{self.dfcf_var.get()}")

    # def refresh_tree(self, df):
    #     for i in self.tree.get_children():
    #         self.tree.delete(i)
    #     log.debug(f'refresh_tree df:{df[:2]}')
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
    #     print(f'query_dict:{query_dict}')
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
    #     #         log.error(f"自动搜索过滤错误: {e}")

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

        print(f"[定位] x={x}, y={y}, screen={screen}")
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
        # print(x,y)
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
    #         log.info(f'stock_code:{stock_code}')
    #         # print(f"选中股票代码: {stock_code}")
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

        stock_code = str(stock_code).zfill(6)
        log.info(f'stock_code:{stock_code}')
        # print(f"选中股票代码: {stock_code}")

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

            win_width, win_height = 400, 200
            x, y = self.get_centered_window_position(win_width, win_height, parent_win=self)
            self.detail_win.geometry(f"{win_width}x{win_height}+{x}+{y}")
            # 再显示出来
            self.detail_win.deiconify()

            # print(
            #     f"位置: ({self.detail_win.winfo_x()}, {self.detail_win.winfo_y()}), "
            #     f"大小: {self.detail_win.winfo_width()}x{self.detail_win.winfo_height()}"
            # )
            # print("geometry:", self.detail_win.geometry())
            # 字体设置
            font_style = tkfont.Font(family="微软雅黑", size=12)
            self.txt_widget = tk.Text(self.detail_win, wrap="word", font=font_style)
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
        # print(f'on_double_click')
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
            stock_info = self.tree.item(item_id, 'values')
            stock_code = stock_info[0]
            if self.push_stock_info(stock_code,self.df_all.loc[stock_code]):
                # 如果发送成功，更新状态标签
                self.status_var2.set(f"发送成功: {stock_code}")
            else:
                # 如果发送失败，更新状态标签
                self.status_var2.set(f"发送失败: {stock_code}")

    def copy_code(self,event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            code = tree.item(item_id, "values")[0]  # 假设第一列是 code
            pyperclip.copy(code)
            print(f"已复制: {code}")

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

        # print(f"[DEBUG] event.x={event.x}, window_w={window_w}, win_w={win_w}, win_h={win_h}, pos=({x},{y})")

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
        # print(f'allcoulumns : {self.df_all.columns.values}')
        # print(f'all_cols : {all_cols}')
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

            # 重新设置表头
            for col in new_columns:
                # self.tree.heading(col, text=col, anchor="center", command=lambda _col=col: self.sort_by_column(_col, False))
                width = 80 if col == "name" else 60
                self.tree.heading(col, text=col, command=lambda _col=col: self.sort_by_column(_col, False))
                self.tree.column(col, width=width, anchor="center", minwidth=50)

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

        # print(f"[Tree Reset] old_cols={current_cols}, new_cols={cols_to_show}")

        # 1️⃣ 清空旧列配置
        for col in current_cols:
            try:
                tree.heading(col, text="")
                tree.column(col, width=0)
            except Exception as e:
                print(f"clear col err: {col}, {e}")

        # 2️⃣ 清空列定义，确保内部索引干净
        tree["columns"] = ()
        tree.update_idletasks()

        # 3️⃣ 重新设置列定义
        tree.config(columns=cols_to_show)
        tree.configure(show="headings")
        tree["displaycolumns"] = cols_to_show
        tree.update_idletasks()

        # 4️⃣ 为每个列重新设置 heading / column
        for col in cols_to_show:
            if sort_func:
                tree.heading(col, text=col, command=lambda _c=col: sort_func(_c, False))
            else:
                tree.heading(col, text=col)
            width = 80 if col == "name" else 60
            tree.column(col, width=width, anchor="center", minwidth=50)

        # print(f"[Tree Reset] applied cols={list(tree['columns'])}")


    def refresh_tree(self, df=None):
        """刷新 TreeView，保证列和数据严格对齐。"""
        if df is None:
            df = self.current_df.copy()
        # 清空
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        # 若 df 为空，更新状态并返回
        if df is None or df.empty:
            # self.current_df = df
            self.current_df = pd.DataFrame() if df is None else df
            self.update_status()
            return

        df = df.copy()

        # 确保 code 列存在并为字符串（便于显示）
        if 'code' not in df.columns:
            # 将 index 转成字符串放到 code 列
            df.insert(0, 'code', df.index.astype(str))

        # 要显示的列顺序（把 DISPLAY_COLS 的顺序保持一致）
        # cols_to_show = ['code'] + [c for c in DISPLAY_COLS if c != 'code']
        cols_to_show = [c for c in self.current_cols if c in df.columns]
        # print(f'cols_to_show : {cols_to_show}')
        self.after_idle(lambda: self.reset_tree_columns(self.tree, cols_to_show, self.sort_by_column))

        # 插入数据严格按 cols_to_show
        for _, row in df.iterrows():
            values = [row.get(col, "") for col in cols_to_show]
            self.tree.insert("", "end", values=values)

        # # 如果 Treeview 的 columns 与我们想要的不一致，则重新配置
        # current_cols = list(self.tree["columns"])
        # print(f'cols_to_show : {cols_to_show}')
        # print(f'current_cols : {current_cols}')
        # if current_cols != cols_to_show:
        #     # 关键：更新 columns，确保使用 list/tuple（不要使用 numpy array）
        #     self.tree.config(columns=cols_to_show)
        #     # 强制只显示 headings（隐藏 #0），并设置 displaycolumns 显示顺序
        #     self.tree.configure(show='headings')
        #     self.tree["displaycolumns"] = cols_to_show

        #     # 清理旧的 heading/column 配置，然后为每列重新设置 heading 和 column
        #     for col in cols_to_show:
        #         # 用默认参数避免 lambda 闭包问题
        #         self.tree.heading(col, text=col, command=lambda _c=col: self.sort_by_column(_c, False))
        #         # 初始宽度，可以根据需要调整
        #         width = 120 if col == "name" else 80
        #         self.tree.column(col, width=width, anchor="center", minwidth=50)

        # 4. 恢复选中
        if self.select_code:
            # print(f'select_code: {self.select_code}')
            for iid in self.tree.get_children():
                values = self.tree.item(iid, "values")
                if values and values[0] == self.select_code:
                    self.tree.selection_set(iid)   # 选中（替代 add）
                    self.tree.focus(iid)           # 恢复键盘焦点
                    self.tree.see(iid)             # 滚动到可见位置
                    break

        # 双击表头绑定
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        # 保存完整数据（方便后续 query / 显示切换）
        self.current_df = df
        # 调整列宽
        self.adjust_column_widths()
        # 更新状态栏
        self.update_status()


    def adjust_column_widths(self):
        """根据当前 self.current_df 和 tree 的列调整列宽（只作用在 display 的列）"""
        # cols = list(self.tree["displaycolumns"]) if self.tree["displaycolumns"] else list(self.tree["columns"])
        cols = list(self.tree["columns"])
        # 遍历显示列并设置合适宽度
        for col in cols:
            # 跳过不存在于 df 的列
            if col not in self.current_df.columns:
                # 仍要确保列有最小宽度
                self.tree.column(col, width=50)
                continue
            # 计算列中最大字符串长度
            try:
                max_len = max([len(str(x)) for x in self.current_df[col].fillna("").values] + [len(col)])
            except Exception:
                max_len = len(col)
            width = min(max(max_len * 8, 60), 300)  # 经验值：每字符约8像素，可调整
            if col == 'name':
                # width = int(width * 2)
                width = int(width * 1.5)
                # print(f'col width: {width}')
                # print(f'col : {col} width: {width}')
            self.tree.column(col, width=width)

    # ----------------- 排序 ----------------- #
    def sort_by_column(self, col, reverse):
        if col in ['code'] or col not in self.current_df.columns:
            return
        self.select_code = None
        self.sortby_col =  col
        self.sortby_col_ascend = not reverse
        # df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        if pd.api.types.is_numeric_dtype(self.current_df[col]):
            df_sorted = self.current_df.sort_values(by=col, ascending=not reverse)
        else:
            df_sorted = self.current_df.sort_values(by=col, key=lambda s: s.astype(str), ascending=not reverse)

        self.refresh_tree(df_sorted)
        self.tree.heading(col, command=lambda: self.sort_by_column(col, not reverse))
        self.tree.yview_moveto(0)

    # import re

    def process_query(query: str):
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

        print("去掉后的 query:", new_query)
        print("提取出的条件:", removed)
        print("拼接后的 final_query:", final_query)

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

    def sync_history_from_QM(self, search_history1=None, search_history2=None):
        self.query_manager.clear_hits()
        if search_history1 is not None:
            if search_history1 is self.query_manager.history2:
                print("[警告] sync_history_from_QM 收到错误引用（history2）→ 覆盖 history1 被阻止")
                return
            self.search_history1 = [r["query"] for r in list(search_history1)]

        if search_history2 is not None:
            if search_history2 is self.query_manager.history1:
                print("[警告] sync_history_from_QM 收到错误引用（history1）→ 覆盖 history2 被阻止")
                return
            self.search_history2 = [r["query"] for r in list(search_history2)]


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
        # print(f'val: {val} {val in existing_queries}')
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
        if df_filtered is None or df_filtered.empty:
            return

        # # --- 统计当前概念 ---
        # cat_dict = {}  # {concept: [codes]}
        # topN = df_filtered.head(50)
        # for code, row in topN.iterrows():
        #     if isinstance(row.get("category"), str):
        #         cats = [c.strip() for c in row["category"].replace("；", ";").replace("+", ";").split(";") if c.strip()]
        #         for ca in cats:
        #             cat_dict.setdefault(ca, []).append((code, row.get("name", "")))

        # current_categories = set(cat_dict.keys())
        # display_text = "、".join(sorted(current_categories))[:200]  # 限制显示长度

        # # --- 统计当前概念 ---
        # cat_dict = {}  # {concept: [codes]}
        # all_cats = []  # 用于统计出现次数
        # topN = df_filtered.head(50)
        # for code, row in topN.iterrows():
        #     if isinstance(row.get("category"), str):
        #         cats = [c.strip() for c in row["category"].replace("；", ";").replace("+", ";").split(";") if c.strip()]
        #         for ca in cats:
        #             all_cats.append(ca)
        #             cat_dict.setdefault(ca, []).append((code, row.get("name", "")))

        # # --- 统计出现次数 ---
        # counter = Counter(all_cats)
        # top5 = OrderedDict(counter.most_common(5))


        # --- 统计当前概念 ---
        cat_dict = {}  # {concept: [codes]}
        all_cats = []  # 用于统计出现次数
        topN = df_filtered.head(50)

        # for code, row in topN.iterrows():
        #     if isinstance(row.get("category"), str):
        #         cats = [c.strip() for c in row["category"].replace("；", ";").replace("+", ";").split(";") if c.strip()]
        #         for ca in cats:
        #             # 过滤泛概念
        #             if is_generic_concept(ca):
        #                 continue
        #             all_cats.append(ca)
        #             cat_dict.setdefault(ca, []).append((code, row.get("name", "")))


        for code, row in topN.iterrows():
            if isinstance(row.get("category"), str):
                cats = [c.strip() for c in row["category"].replace("；", ";").replace("+", ";").split(";") if c.strip()]
                for ca in cats:
                    # 过滤泛概念
                    if is_generic_concept(ca):
                        continue
                    all_cats.append(ca)
                    # 添加其他信息到元组里，比如 (code, name, percent, volume)
                    cat_dict.setdefault(ca, []).append((
                        code,
                        row.get("name", ""),
                        row.get("percent", 0) or row.get("per1d", 0),
                        row.get("volume", 0)
                        # 如果还有其他列，可以继续加: row.get("其他列")
                    ))


        # --- 统计出现次数 ---
        counter = Counter(all_cats)
        top5 = OrderedDict(counter.most_common(5))

        display_text = "  ".join([f"{k}:{v}" for k, v in top5.items()])
        # print(f'display_text : {display_text}  list(top5.keys()) : { list(top5.keys()) }')
        # 取前5个类别
        # current_categories = set(top5.keys())
        current_categories =  list(top5.keys())  #保持顺序

        # --- 标签初始化 ---
        if not hasattr(self, "lbl_category_result"):
            self.lbl_category_result = tk.Label(
                self,
                text="",
                font=("微软雅黑", 10, "bold"),
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

    def on_code_click(self, code):
        """点击异动窗口中的股票代码"""
        if code != self.select_code:
            self.select_code = code
            print(f"select_code: {code}")
            # ✅ 可改为打开详情逻辑，比如：
            # if hasattr(self, "show_stock_detail"):
            #     self.show_stock_detail(code)
            self.sender.send(code)

    # old single
    # def _show_concept_detail_window_Good(self):
    #     """弹出详细概念异动窗口（支持复用、滚轮、自动刷新、显示当前前5）"""
    #     if not hasattr(self, "_last_categories"):
    #         return

    #     # --- 检查并重建窗口 ---
    #     if getattr(self, "_concept_win", None):
    #         try:
    #             if self._concept_win.winfo_exists():
    #                 win = self._concept_win
    #                 win.deiconify()
    #                 win.lift()
    #                 for widget in win.winfo_children():
    #                     widget.destroy()
    #             else:
    #                 win = tk.Toplevel(self)
    #                 self._concept_win = win
    #         except Exception:
    #             win = tk.Toplevel(self)
    #             self._concept_win = win
    #     else:
    #         win = tk.Toplevel(self)
    #         self._concept_win = win

    #     win.title("概念异动详情")
    #     self.load_window_position(win, "detail_window", default_width=220, default_height=400)
    #     win.transient(self)

    #     # --- 主Frame + Canvas ---
    #     frame = tk.Frame(win)
    #     frame.pack(fill="both", expand=True, padx=10, pady=10)

    #     canvas = tk.Canvas(frame, highlightthickness=0)
    #     scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    #     scroll_frame = tk.Frame(canvas)

    #     canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    #     canvas.configure(yscrollcommand=scrollbar.set)

    #     scroll_frame.bind(
    #         "<Configure>",
    #         lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    #     )

    #     canvas.pack(side="left", fill="both", expand=True)
    #     scrollbar.pack(side="right", fill="y")

    #     # --- 局部绑定滚轮（防止关闭后异常） ---
    #     def on_mousewheel(event):
    #         canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    #     def bind_mousewheel(event):
    #         canvas.bind_all("<MouseWheel>", on_mousewheel)
    #         canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
    #         canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

    #     def unbind_mousewheel(event=None):
    #         try:
    #             canvas.unbind_all("<MouseWheel>")
    #             canvas.unbind_all("<Button-4>")
    #             canvas.unbind_all("<Button-5>")
    #         except Exception:
    #             pass

    #     canvas.bind("<Enter>", bind_mousewheel)
    #     canvas.bind("<Leave>", unbind_mousewheel)

    #     # --- 关闭事件 ---
    #     def on_close_detail_window():
    #         self.save_window_position(win, "detail_window")
    #         unbind_mousewheel()  # 关闭前解绑防止残留
    #         try:
    #             win.grab_release()
    #         except:
    #             pass
    #         win.destroy()
    #         self._concept_win = None

    #     win.protocol("WM_DELETE_WINDOW", on_close_detail_window)

    #     # --- 数据逻辑 ---
    #     current_categories = getattr(self, "_last_categories", [])
    #     prev_categories = getattr(self, "_prev_categories", [])
    #     cat_dict = getattr(self, "_last_cat_dict", {})

    #     added = [c for c in current_categories if c not in prev_categories]
    #     removed = [c for c in prev_categories if c not in current_categories]

    #     # === 有新增或消失 ===
    #     if added or removed:
    #         if added:
    #             tk.Label(scroll_frame, text="🆕 新增概念", font=("微软雅黑", 11, "bold"), fg="green").pack(anchor="w", pady=(0, 5))
    #             for c in added:
    #                 tk.Label(scroll_frame, text=c, fg="blue", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)
    #                 for code, name in cat_dict.get(c, []):
    #                     lbl = tk.Label(scroll_frame, text=f"  {code} {name}", fg="black", cursor="hand2")
    #                     lbl.pack(anchor="w", padx=6)
    #                     lbl.bind("<Button-1>", lambda e, cd=code: self.on_code_click(cd))

    #         if removed:
    #             tk.Label(scroll_frame, text="❌ 消失概念", font=("微软雅黑", 11, "bold"), fg="red").pack(anchor="w", pady=(10, 5))
    #             for c in removed:
    #                 tk.Label(scroll_frame, text=c, fg="gray", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)
    #     else:
    #         # === 无新增/消失时，显示当前前5 ===
    #         tk.Label(scroll_frame, text="📊 当前前5概念", font=("微软雅黑", 11, "bold"), fg="blue").pack(anchor="w", pady=(0, 5))
    #         for c in current_categories:
    #             tk.Label(scroll_frame, text=c, fg="black", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)
    #             for code, name in cat_dict.get(c, []):
    #                 lbl = tk.Label(scroll_frame, text=f"  {code} {name}", fg="gray", cursor="hand2")
    #                 lbl.pack(anchor="w", padx=6)
    #                 lbl.bind("<Button-1>", lambda e, cd=code: self.on_code_click(cd))

    #     # --- 更新状态 ---
    #     self._prev_categories = list(current_categories)



    # --- 类内部方法 ---
    def show_concept_detail_window(self):
        """弹出详细概念异动窗口（复用+自动刷新+键盘/滚轮+高亮）"""
        if not hasattr(self, "_last_categories"):
            return

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
        win.transient(self)

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

        # --- 键盘事件绑定 ---
        # canvas.bind_all("<Up>", lambda e: self._on_key(e))
        # canvas.bind_all("<Down>", lambda e: self._on_key(e))
        # canvas.bind_all("<Prior>", lambda e: self._on_key(e))
        # canvas.bind_all("<Next>", lambda e: self._on_key(e))
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

    def update_concept_detail_content(self):
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
                tk.Label(scroll_frame, text="🆕 新增概念", font=("微软雅黑", 11, "bold"), fg="green").pack(anchor="w", pady=(0, 5))
                for c in added:
                    tk.Label(scroll_frame, text=c, fg="blue", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)
                    stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)
                    for code, name, percent, volume in stocks:
                        lbl = tk.Label(scroll_frame, text=f"  {code} {name} {percent:.2f}% {volume}",
                                       fg="black", cursor="hand2", anchor="w")
                        lbl.pack(anchor="w", padx=6)
                        lbl._code = code  # 保存对应 code
                        lbl._concept = c  # 绑定当前概念
                        idx = len(self._label_widgets)
                        lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                        lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                        lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))  # ✅ 新增双击事件
                        self._label_widgets.append(lbl)

            if removed:
                tk.Label(scroll_frame, text="❌ 消失概念", font=("微软雅黑", 11, "bold"), fg="red").pack(anchor="w", pady=(10, 5))
                for c in removed:
                    tk.Label(scroll_frame, text=c, fg="gray", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)

        else:
            tk.Label(scroll_frame, text="📊 当前前5概念", font=("微软雅黑", 11, "bold"), fg="blue").pack(anchor="w", pady=(0, 5))
            for c in current_categories[:5]:
                tk.Label(scroll_frame, text=c, fg="black", font=("微软雅黑", 10, "bold")).pack(anchor="w", padx=5)
                stocks = sorted(cat_dict.get(c, []), key=lambda x: x[2], reverse=True)
                for code, name, percent, volume in stocks:
                    lbl = tk.Label(scroll_frame, text=f"  {code} {name} {percent:.2f}% {volume}",
                                   fg="gray", cursor="hand2", anchor="w")
                    lbl.pack(anchor="w", padx=6)
                    lbl._code = code  # 保存对应 code
                    lbl._concept = c  # 绑定当前概念
                    idx = len(self._label_widgets)
                    lbl.bind("<Button-1>", lambda e, cd=code, i=idx: self._on_label_click(cd, i))
                    lbl.bind("<Button-3>", lambda e, cd=code, i=idx: self._on_label_right_click(cd, i))
                    lbl.bind("<Double-Button-1>", lambda e, cd=code, i=idx: self._on_label_double_click(cd, i))  # ✅ 新增双击事件

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
        event.widget.delete(0, tk.END)
        event.widget.insert(0, clipboard_text)
        # self.on_test_click()


    def _on_label_on_code_click(self, code,idx):
        self._update_selection_top10(idx)
        """点击异动窗口中的股票代码"""
        self.select_code = code
        # print(f"select_code: {code}")
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

    # def _update_selection_top10(self, idx):
    #     """更新Top10窗口的高亮状态"""
    #     for i, lbl in enumerate(self._top10_label_widgets):
    #         lbl.configure(bg="lightblue" if i == idx else "SystemButtonFace")

    def _update_selection_top10(self, idx):
        """更新 Top10 窗口选中高亮并滚动"""
        if not hasattr(self, "_concept_top10_win") or not self._concept_top10_win:
            return
        win = self._concept_top10_win
        canvas = win._canvas_top10
        scroll_frame = win._content_frame_top10

        # 清除所有高亮
        for lbl in self._top10_label_widgets:
            lbl.configure(bg=win.cget("bg"))

        # 高亮选中
        if 0 <= idx < len(self._top10_label_widgets):
            lbl = self._top10_label_widgets[idx]
            self._top10_selected_index = idx
            lbl.configure(bg="lightblue")
            self._concept_top10_selected_index = idx

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


    def show_concept_top10_window(self, concept_name):
        """
        显示指定概念的前10放量上涨股（复用窗口；支持滚轮/键盘/点击）
        """
        # import tkinter as tk
        # from tkinter import ttk, messagebox

        if not hasattr(self, "df_all") or self.df_all is None or self.df_all.empty:
            messagebox.showwarning("数据错误", "df_all 数据为空，无法筛选概念股票")
            return

        query_expr = f'category.str.contains("{concept_name}", na=False)'

        try:
            df_concept = self.df_all.query(query_expr)
        except Exception as e:
            messagebox.showerror("筛选错误", f"筛选表达式错误: {query_expr}\n{e}")
            return

        if df_concept.empty:
            messagebox.showinfo("概念详情", f"概念【{concept_name}】暂无匹配股票")
            return

        df_concept = df_concept.copy()
        if "percent" in df_concept.columns and "volume" in df_concept.columns:
            # df_concept = df_concept[df_concept["percent"] >= 0]
            df_top = df_concept[df_concept["percent"] > 0]
            df_concept = df_top if not df_top.empty else df_concept[df_concept["per1d"] >= 0]

            df_concept = df_concept.sort_values("volume", ascending=False).head(10)
        else:
            messagebox.showinfo("概念详情", "df_all 缺少 'percent' 或 'volume' 列")
            return

        # --- 复用 ---
        try:
            if getattr(self, "_concept_top10_win", None) and self._concept_top10_win.winfo_exists():
                win = self._concept_top10_win
                win.deiconify()
                win.lift()
                for w in win._content_frame_top10.winfo_children():
                    w.destroy()
                self._fill_concept_top10_content(win, concept_name, df_concept)
                win._canvas_top10.yview_moveto(0)
                win._content_frame_top10.focus_set()
                return
        except Exception:
            self._concept_top10_win = None

        # --- 新建窗口 ---
        win = tk.Toplevel(self)
        self._concept_top10_win = win
        win.title(f"{concept_name} 概念前10放量上涨股")
        try:
            self.load_window_position(win, "concept_top10_window", default_width=300, default_height=320)
        except Exception:
            win.geometry("300x320")

        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True)

        # Canvas + Scrollbar
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        # 使用 grid 布局保证 scrollbar 永远可见
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # 让 frame 自适应
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # 内部滚动内容
        scroll_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scroll_frame.bind("<Configure>", on_frame_configure)

        def _on_mousewheel(event):
            delta = 0
            if hasattr(event, 'delta'):
                delta = int(-1 * (event.delta / 120))  # Windows / Mac
            elif event.num == 4:  # Linux 向上
                delta = -1
            elif event.num == 5:  # Linux 向下
                delta = 1
            canvas.yview_scroll(delta, "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)   # Windows / Mac
        canvas.bind("<Button-4>", _on_mousewheel)     # Linux
        canvas.bind("<Button-5>", _on_mousewheel)     # Linux

        # # --- 鼠标滚轮 ---
        # # def _on_mousewheel(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        def _bind_scroll(): canvas.bind("<MouseWheel>", _on_mousewheel)
        def _unbind_scroll(): canvas.unbind("<MouseWheel>")

        # scroll_frame.bind("<Enter>", lambda e: _bind_scroll())
        # scroll_frame.bind("<Leave>", lambda e: _unbind_scroll())

        # ✅ 改成独立引用
        win._canvas_top10 = canvas
        win._content_frame_top10 = scroll_frame
        win._unbind_mousewheel_top10 = _unbind_scroll

        canvas.bind("<Up>", self._on_key_top10)
        canvas.bind("<Down>", self._on_key_top10)
        canvas.bind("<Prior>", self._on_key_top10)
        canvas.bind("<Next>", self._on_key_top10)
        win.after_idle(lambda: canvas.focus_set())

        # 填充内容
        self._fill_concept_top10_content(win, concept_name, df_concept)

        # 关闭事件
        def _on_close():
            try:
                self.save_window_position(win, "concept_top10_window")
            except Exception:
                pass
            _unbind_scroll()
            win.destroy()
            self._concept_top10_win = None
            self._canvas_top10 = None

        win.protocol("WM_DELETE_WINDOW", _on_close)

    def _fill_concept_top10_content(self, win, concept_name, df_concept):
        """
        在概念Top10窗口中填充内容（安全引用独立）
        """
        # import tkinter as tk
        # from tkinter import messagebox

        frame = win._content_frame_top10

        tk.Label(
            frame,
            text=f"📈 {concept_name} 概念前10放量上涨股",
            font=("微软雅黑", 11, "bold"),
            fg="blue"
        ).pack(anchor="w", pady=(0, 8))

        self._top10_label_widgets = []
        self._top10_selected_index = 0

        for idx, (code, row) in enumerate(df_concept.iterrows()):
            # code = row.get("code", "")
            name = row.get("name", "")
            # percent = row.get("percent", 0)
            percent = row.get("percent", 0) or row.get("per1d", 0)
            volume = row.get("volume", 0)

            text = f"{code}  {name:<6}  涨幅:{percent:.2f}%  量:{volume:.2f}"

            lbl = tk.Label(frame, text=text, anchor="w", font=("微软雅黑", 9), cursor="hand2")
            lbl.pack(anchor="w", padx=8, pady=2, fill="x")
            lbl._code = code
            lbl._concept = concept_name
            lbl.bind("<Button-1>", lambda e, c=code, i=idx: self._on_label_on_code_click(c, i))
            lbl.bind("<Double-Button-1>", lambda e, c=code, i=idx: self._on_label_double_click(c, i))
            lbl.bind("<Button-3>", lambda e, c=code, i=idx: self._on_label_right_click(c, i))
            self._top10_label_widgets.append(lbl)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill="x", pady=6)
        def _copy_expr():
            import pyperclip
            q = f'category.str.contains("{concept_name}", na=False)'
            pyperclip.copy(q)
            # messagebox.showinfo("已复制", f"筛选条件：\n{q}")
            toast_message(self,f"已复制筛选条件：{q}")
        tk.Button(btn_frame, text="复制筛选表达式", command=_copy_expr).pack(side="left", padx=6)

        if self._top10_label_widgets:
            self._top10_label_widgets[0].configure(bg="lightblue")

        try:
            win._canvas_top10.yview_moveto(0)
            frame.focus_set()
        except Exception:
            pass


    # def _on_label_double_click(self, code, idx):
    #     """
    #     双击股票标签时，显示该股票所属概念详情（复用 show_concept_detail_window）
    #     """
    #     try:
    #         concept_name = getattr(self._label_widgets[idx], "_concept", None)
    #         if not concept_name:
    #             messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
    #             return

    #         self.show_concept_top10_window(concept_name)
    #         # --- 提升窗口层级 & 聚焦 ---
    #         if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
    #             win = self._concept_top10_win
    #             win.lift()          # 🔹 提到最前
    #             win.focus_force()   # 🔹 把键盘焦点给它
    #             win.attributes('-topmost', True)   # 🔹 临时置顶
    #             win.after(300, lambda: win.attributes('-topmost', False))  # 🔹 避免永久置顶

    #             if hasattr(win, "_canvas_top10"):
    #                 canvas = win._canvas_top10
    #                 yview = canvas.yview()
    #                 canvas.focus_set()
    #                 canvas.yview_moveto(yview[0])  # 恢复滚动位置

    #     except Exception as e:
    #         print("获取概念详情失败：", e)

    def _on_label_double_click(self, code, idx):
        """
        双击股票标签时，显示该股票所属概念详情（复用 show_concept_detail_window）
        """
        try:
            concept_name = getattr(self._label_widgets[idx], "_concept", None)
            if not concept_name:
                messagebox.showinfo("概念详情", f"{code} 暂无概念数据")
                return

            # 打开或复用 Top10 窗口
            self.show_concept_top10_window(concept_name)

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
                    print("窗口状态检查失败：", e)

                # --- 恢复 Canvas 滚动位置 ---
                if hasattr(win, "_canvas_top10"):
                    canvas = win._canvas_top10
                    yview = canvas.yview()
                    canvas.focus_set()
                    canvas.yview_moveto(yview[0])

        except Exception as e:
            print("获取概念详情失败：", e)




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
            print(f"已复制: {text}")
            # messagebox.showinfo("概念详情", f"{code} 所属概念：\n{text}")
        except Exception as e:
            print("获取概念详情失败：", e)


    def _on_label_right_click(self,code ,idx):
        self._update_selection(idx)
        stock_code = code
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
        tk.Label(win, text=f"正在加载个股 {code} ...", font=("微软雅黑", 12, "bold")).pack(pady=10)

        # 如果有 df_filtered 数据，可以显示详细行情
        if hasattr(self, "_last_cat_dict"):
            for c, lst in self._last_cat_dict.items():
                for row_code, name in lst:
                    if row_code == code:
                        tk.Label(win, text=f"{row_code} {name}", font=("微软雅黑", 11)).pack(anchor="w", padx=10)
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

        # try:
        #     key = self.query_manager.current_key
        #     if key == "history1" and val1:
        #         self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")
        #     elif key == "history2" and val2:
        #         self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")
        # except Exception as ex:
        #     log.exception("更新搜索历史时出错: %s", ex)
        try:
            # 🔹 同步两个搜索框的历史，不依赖 current_key
            if val1:
                self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")
            if val2:
                self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")
        except Exception as ex:
            log.exception("更新搜索历史时出错: %s", ex)

        # ================= 数据为空检查 =================
        if self.df_all.empty:
            self.status_var.set("当前数据为空")
            return

        # ====== 条件清理 ======
        import re

        bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

        # 2️⃣ 替换掉原 query 中的这些部分
        for bracket in bracket_patterns:
            query = query.replace(f'and {bracket}', '')

        # print("修改后的 query:", query)
        # print("提取出来的括号条件:", bracket_patterns)

        # 3️⃣ 后续可以在拼接 final_query 时再组合回去
        # 例如:
        # final_query = ' and '.join(valid_conditions)
        # final_query += ' and ' + ' and '.join(bracket_patterns)


        conditions = [c.strip() for c in query.split('and')]
        valid_conditions = []
        removed_conditions = []
        print(f'conditions: {conditions} bracket_patterns : {bracket_patterns}')
        for cond in conditions:
            cond_clean = cond.lstrip('(').rstrip(')')

            # index 条件特殊保留
            # if 'index.' in cond_clean.lower():
            #     valid_conditions.append(cond_clean)
            #     continue

            # index 或 str 操作条件特殊保留
            # if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 :
                # if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
            if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0 or cond.find('or') >= 0:
                if not any(bp.strip('() ').strip() == cond_clean for bp in bracket_patterns):
                    valid_conditions.append(cond_clean)
                    continue

            # 提取条件中的列名
            cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

            # 所有列都必须存在才保留
            if all(col in self.df_all.columns for col in cols_in_cond):
                valid_conditions.append(cond_clean)
            else:
                removed_conditions.append(cond_clean)
                log.info(f"剔除不存在的列条件: {cond_clean}")

        # 去掉在 bracket_patterns 中出现的内容
        removed_conditions = [
            cond for cond in removed_conditions
            if not any(bp.strip('() ').strip() == cond.strip() for bp in bracket_patterns)
        ]

        # print(filtered_removed)
        # removed_conditions = filtered_removed
        # 打印剔除条件列表
        if removed_conditions:
            print(f"[剔除的条件列表] {removed_conditions}")

        if not valid_conditions:
            self.status_var.set("没有可用的查询条件")
            return
        # print(f'valid_conditions : {valid_conditions}')
        # ====== 拼接 final_query 并检查括号 ======
        final_query = ' and '.join(f"({c})" for c in valid_conditions)
        # print(f'final_query : {final_query}')
        if bracket_patterns:
            final_query += ' and ' + ' and '.join(bracket_patterns)
        # print(f'final_query : {final_query}')
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
        # ====== 数据过滤 ======
        try:

            # if val1.count('or') > 0 and val1.count('(') > 0:
            #     if val2 :
            #         query_search = f"({val1}) and {val2}"
            #         print(f'query: {query_search} ')

            #     else:
            #         query_search = f"({val1})"
            #         print(f'query: {query_search} ')

            #     df_filtered = self.df_all.query(query_search, engine=query_engine)
            #     self.refresh_tree(df_filtered)
            #     self.status_var2.set('')
            #     self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {val1} and {val2}")
            # else:
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

            self.refresh_tree(df_filtered)
            # 打印剔除条件列表
            if removed_conditions:
                # print(f"[剔除的条件列表] {removed_conditions}")
                # 显示到状态栏
                self.status_var2.set(f"已剔除条件: {', '.join(removed_conditions)}")
                self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
            else:
                self.status_var2.set('')
                self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
            print(f'final_query: {final_query}')
        except Exception as e:
            log.error(f"Query error: {e}")
            self.status_var.set(f"查询错误: {e}")

        self.on_test_code()
        self.auto_refresh_detail_window()
        self.update_category_result(df_filtered)
        # if df_filtered is not None and not df_filtered.empty:
        #     result = counterCategory(df_filtered, 'category', limit=50, table=True)
        #     self._Categoryresult = result
        #     if self.query_manager.editor_frame.winfo_ismapped():
        #             # ✅ 编辑器已打开 → 显示在输入框中
        #             self.query_manager.entry_query.delete(0, tk.END)
        #             self.query_manager.entry_query.insert(0, self._Categoryresult)
        #     else:
        #         # ✅ 编辑器未打开 → 显示在主窗口标题或标签
        #         if hasattr(self, "lbl_category_result"):
        #             # 如果已经有标签则更新文字
        #             self.lbl_category_result.config(text=self._Categoryresult)
        #         else:
        #             # 否则创建一个新的标签显示统计
        #             self.lbl_category_result = tk.Label(
        #                 self.main_frame, text=self._Categoryresult,
        #                 font=("Consolas", 10), fg="green", anchor="w", justify="left"
        #             )
        #             self.lbl_category_result.pack(fill="x", padx=5, pady=(2, 4))

    # def apply_search1(self):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     if not val1 and not val2:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # 构建原始查询语句
    #     if val1 and val2:
    #         query = f"({val1}) and ({val2})"
    #     elif val1:
    #         query = val1
    #     else:
    #         query = val2

    #     # 如果新值和上次一样，就不触发
    #     # if hasattr(self, "_last_value") and self._last_value == query:
    #     #     return
    #     self._last_value = query

    #     try:
    #         if val1:
    #             self.sync_history(val1, self.search_history1, self.search_combo1, "history1", "history1")

    #         if val2:
    #             self.sync_history(val2, self.search_history2, self.search_combo2, "history2", "history2")

    #         # 一次性保存
    #         # self.query_manager.save_search_history()

    #     except Exception as ex:
    #         log.exception("更新搜索历史时出错: %s", ex)

    #     # ================= 数据为空检查 =================
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     # ====== 条件清理 ======
    #     import re

    #     bracket_patterns = re.findall(r'\s+and\s+(\([^\(\)]*\))', query)

    #     # 2️⃣ 替换掉原 query 中的这些部分
    #     for bracket in bracket_patterns:
    #         query = query.replace(f'and {bracket}', '')

    #     # print("修改后的 query:", query)
    #     # print("提取出来的括号条件:", bracket_patterns)

    #     # 3️⃣ 后续可以在拼接 final_query 时再组合回去
    #     # 例如:
    #     # final_query = ' and '.join(valid_conditions)
    #     # final_query += ' and ' + ' and '.join(bracket_patterns)


    #     conditions = [c.strip() for c in query.split('and')]
    #     valid_conditions = []
    #     removed_conditions = []

    #     for cond in conditions:
    #         cond_clean = cond.lstrip('(').rstrip(')')

    #         # index 条件特殊保留
    #         # if 'index.' in cond_clean.lower():
    #         #     valid_conditions.append(cond_clean)
    #         #     continue

    #         # index 或 str 操作条件特殊保留
    #         if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower() or cond.find('==') >= 0:
    #             valid_conditions.append(cond_clean)
    #             continue


    #         # 提取条件中的列名
    #         cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

    #         # 所有列都必须存在才保留
    #         if all(col in self.df_all.columns for col in cols_in_cond):
    #             valid_conditions.append(cond_clean)
    #         else:
    #             removed_conditions.append(cond_clean)
    #             log.info(f"剔除不存在的列条件: {cond_clean}")

    #     # 打印剔除条件列表
    #     if removed_conditions:
    #         print(f"[剔除的条件列表] {removed_conditions}")

    #     if not valid_conditions:
    #         self.status_var.set("没有可用的查询条件")
    #         return

    #     # ====== 拼接 final_query 并检查括号 ======
    #     final_query = ' and '.join(f"({c})" for c in valid_conditions)
    #     # print(f'final_query : {final_query}')
    #     if bracket_patterns:
    #         final_query += ' and ' + ' and '.join(bracket_patterns)
    #     # print(f'final_query : {final_query}')
    #     left_count = final_query.count("(")
    #     right_count = final_query.count(")")
    #     if left_count != right_count:
    #         if left_count > right_count:
    #             final_query += ")" * (left_count - right_count)
    #         elif right_count > left_count:
    #             final_query = "(" * (right_count - left_count) + final_query

    #     # ====== 决定 engine ======
    #     query_engine = 'numexpr'
    #     if any('index.' in c.lower() for c in valid_conditions):
    #         query_engine = 'python'

    #     # ====== 数据过滤 ======
    #     try:
    #         if val1.count('or') > 0 and val1.count('(') > 0:
    #             if val2 :
    #                 query_search = f"({val1}) and {val2}"
    #                 print(f'query: {query_search} ')

    #             else:
    #                 query_search = f"({val1})"
    #                 print(f'query: {query_search} ')
    #             df_filtered = self.df_all.query(query_search, engine=query_engine)
    #             self.refresh_tree(df_filtered)
    #             self.status_var2.set('')
    #             self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {val1} and {val2}")
    #         else:
    #             # 检查 category 列是否存在
    #             if 'category' in self.df_all.columns:
    #                 # 强制转换为字符串，避免 str.contains 报错
    #                 if not pd.api.types.is_string_dtype(self.df_all['category']):
    #                     self.df_all['category'] = self.df_all['category'].astype(str).str.strip()
    #                     # self.df_all['category'] = self.df_all['category'].astype(str)
    #                     # 可选：去掉前后空格
    #                     # self.df_all['category'] = self.df_all['category'].str.strip()
    #             df_filtered = self.df_all.query(final_query, engine=query_engine)
    #             self.refresh_tree(df_filtered)
    #             # 打印剔除条件列表
    #             if removed_conditions:
    #                 print(f"[剔除的条件列表] {removed_conditions}")
    #                 # 显示到状态栏
    #                 self.status_var2.set(f"已剔除条件: {', '.join(removed_conditions)}")
    #                 self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
    #             else:
    #                 self.status_var2.set('')
    #                 self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
    #             print(f'final_query: {final_query}')
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")


    # def apply_search_no_or(self):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     if not val1 and not val2:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # 构建原始查询语句
    #     if val1 and val2:
    #         query = f"({val1}) and ({val2})"
    #     elif val1:
    #         query = val1
    #     else:
    #         query = val2

    #     try:
    #         # 顶部搜索框
    #         if val1:
    #             if val1 in self.search_history1:
    #                 self.search_history1.remove(val1)
    #             self.search_history1.insert(0, val1)
    #             if len(self.search_history1) > 20:
    #                 self.search_history1[:] = self.search_history1[:20]
    #             self.search_combo1['values'] = self.search_history1
    #             try:
    #                 self.search_combo1.set(val1)
    #             except Exception:
    #                 pass

    #         # 底部搜索框
    #         if val2:
    #             if val2 in self.search_history2:
    #                 self.search_history2.remove(val2)
    #             self.search_history2.insert(0, val2)
    #             if len(self.search_history2) > 20:
    #                 self.search_history2[:] = self.search_history2[:20]
    #             self.search_combo2['values'] = self.search_history2
    #             try:
    #                 self.search_combo2.set(val2)
    #             except Exception:
    #                 pass

    #         # 一次性保存
    #         self.save_search_history()
    #     except Exception as ex:
    #         log.exception("更新搜索历史时出错: %s", ex)

    #     # ================= 数据为空检查 =================
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     # ====== 条件清理 ======
    #     import re
    #     conditions = [c.strip() for c in query.split('and')]
    #     valid_conditions = []
    #     removed_conditions = []

    #     for cond in conditions:
    #         cond_clean = cond.lstrip('(').rstrip(')')

    #         # index 条件特殊保留
    #         # if 'index.' in cond_clean.lower():
    #         #     valid_conditions.append(cond_clean)
    #         #     continue

    #         # index 或 str 操作条件特殊保留
    #         if 'index.' in cond_clean.lower() or '.str.' in cond_clean.lower():
    #             valid_conditions.append(cond_clean)
    #             continue


    #         # 提取条件中的列名
    #         cols_in_cond = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cond_clean)

    #         # 所有列都必须存在才保留
    #         if all(col in self.df_all.columns for col in cols_in_cond):
    #             valid_conditions.append(cond_clean)
    #         else:
    #             removed_conditions.append(cond_clean)
    #             log.info(f"剔除不存在的列条件: {cond_clean}")

    #     # 打印剔除条件列表
    #     if removed_conditions:
    #         print(f"[剔除的条件列表] {removed_conditions}")

    #     if not valid_conditions:
    #         self.status_var.set("没有可用的查询条件")
    #         return

    #     # ====== 拼接 final_query 并检查括号 ======
    #     final_query = ' and '.join(f"({c})" for c in valid_conditions)

    #     left_count = final_query.count("(")
    #     right_count = final_query.count(")")
    #     if left_count != right_count:
    #         if left_count > right_count:
    #             final_query += ")" * (left_count - right_count)
    #         elif right_count > left_count:
    #             final_query = "(" * (right_count - left_count) + final_query

    #     # ====== 决定 engine ======
    #     query_engine = 'numexpr'
    #     if any('index.' in c.lower() for c in valid_conditions):
    #         query_engine = 'python'

    #     # ====== 数据过滤 ======
    #     try:
    #         # 检查 category 列是否存在
    #         if 'category' in self.df_all.columns:
    #             # 强制转换为字符串，避免 str.contains 报错
    #             if not pd.api.types.is_string_dtype(self.df_all['category']):
    #                 self.df_all['category'] = self.df_all['category'].astype(str).str.strip()
    #                 # self.df_all['category'] = self.df_all['category'].astype(str)
    #                 # 可选：去掉前后空格
    #                 # self.df_all['category'] = self.df_all['category'].str.strip()
    #         df_filtered = self.df_all.query(final_query, engine=query_engine)
    #         self.refresh_tree(df_filtered)
    #         # 打印剔除条件列表
    #         if removed_conditions:
    #             print(f"[剔除的条件列表] {removed_conditions}")
    #             # 显示到状态栏
    #             self.status_var2.set(f"已剔除条件: {', '.join(removed_conditions)}")
    #             self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
    #         else:
    #             self.status_var2.set('')
    #             self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {final_query}")
    #         print(f'final_query: {final_query}')
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")




    # def apply_search_python(self):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     if not val1 and not val2:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # 构建查询语句
    #     if val1 and val2:
    #         query = f"({val1}) and ({val2})"
    #     elif val1:
    #         query = val1
    #     else:
    #         query = val2

    #     # 更新第一个搜索历史
    #     if val1:
    #         if val1 not in self.search_history1:
    #             self.search_history1.insert(0, val1)
    #             if len(self.search_history1) > 20:
    #                 self.search_history1 = self.search_history1[:20]
    #         else:
    #             self.search_history1.remove(val1)
    #             self.search_history1.insert(0, val1)
    #         self.search_combo1['values'] = self.search_history1
    #         self.save_search_history()

    #     # 更新第二个搜索历史
    #     if val2:
    #         if val2 not in self.search_history2:
    #             self.search_history2.insert(0, val2)
    #             if len(self.search_history2) > 20:
    #                 self.search_history2 = self.search_history2[:20]
    #         else:
    #             self.search_history2.remove(val2)
    #             self.search_history2.insert(0, val2)
    #         self.search_combo2['values'] = self.search_history2
    #         self.save_search_history()

    #     # 数据过滤与刷新
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         # 判断 query 是否涉及 index
    #         if 'index.' in query.lower():
    #             df_filtered = self.df_all.query(query, engine='python')
    #         else:
    #             df_filtered = self.df_all.query(query)  # 默认 engine

    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"结果 {len(df_filtered)}行 | 搜索: {query}")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")

    # --- 搜索逻辑 ---
    # 搜索逻辑：支持双搜索框 & 独立历史
    # def apply_search_nopython(self):
    #     val1 = self.search_var1.get().strip()
    #     val2 = self.search_var2.get().strip()

    #     if not val1 and not val2:
    #         self.status_var.set("搜索框为空")
    #         return

    #     # 构建查询语句
    #     if val1 and val2:
    #         query = f"({val1}) and ({val2})"
    #     elif val1:
    #         query = val1
    #     else:
    #         query = val2

    #     # 更新第一个搜索历史
    #     if val1:
    #         if val1 not in self.search_history1:
    #             self.search_history1.insert(0, val1)
    #             if len(self.search_history1) > 20:
    #                 self.search_history1 = self.search_history1[:20]
    #         else:
    #             self.search_history1.remove(val1)
    #             self.search_history1.insert(0, val1)
    #         self.search_combo1['values'] = self.search_history1
    #         self.save_search_history()

    #     # 更新第二个搜索历史
    #     if val2:
    #         if val2 not in self.search_history2:
    #             self.search_history2.insert(0, val2)
    #             if len(self.search_history2) > 20:
    #                 self.search_history2 = self.search_history2[:20]
    #         else:
    #             self.search_history2.remove(val2)
    #             self.search_history2.insert(0, val2)
    #         self.search_combo2['values'] = self.search_history2
    #         self.save_search_history()

    #     # 数据过滤与刷新
    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.df_all.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"结果 {len(df_filtered)}行| 搜索: {query}")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")

    # def apply_search_start(self):
    #     query = self.search_var.get().strip()
    #     if not query:
    #         self.status_var.set("搜索框为空")
    #         return

    #     if query not in self.search_history:
    #         self.search_history.insert(0, query)
    #         if len(self.search_history) > 20:  # 最多保存20条
    #             self.search_history = self.search_history[:20]
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()  # 保存到文件
    #     else:
    #         self.search_history.remove(query)  # リストから既存のクエリを削除する
    #         self.search_history.insert(0, query) # リストの先頭にクエリを挿入する
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()


    #     if self.df_all.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.df_all.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"结果 {len(df_filtered)}行| 搜索: {query}  ")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")


    # def apply_search_src(self):
    #     query = self.search_var.get().strip()
    #     if not query:
    #         self.status_var.set("搜索框为空")
    #         return

    #     if query not in self.search_history:
    #         self.search_history.insert(0, query)
    #         if len(self.search_history) > 20:  # 最多保存20条
    #             self.search_history = self.search_history[:20]
    #         self.search_combo['values'] = self.search_history
    #         self.save_search_history()  # 保存到文件

    #     if self.current_df.empty:
    #         self.status_var.set("当前数据为空")
    #         return

    #     try:
    #         df_filtered = self.current_df.query(query)
    #         self.refresh_tree(df_filtered)
    #         self.status_var.set(f"搜索: {query} | 结果 {len(df_filtered)} 行")
    #     except Exception as e:
    #         log.error(f"Query error: {e}")
    #         self.status_var.set(f"查询错误: {e}")

    # def on_test_code(self):
    #     code = self.query_manager.entry_query.get().strip()
    #     # code = self.entry_code.get().strip()
    #     import ipdb;ipdb.set_trace()

    #     if code and len(code) == 6:
    #         # df_code = self.df_all.loc[code]  # 自己实现获取行情数据
    #         df_code = self.df_all.loc[[code]]  # 自己实现获取行情数据 dataframe
    #         results = self.query_manager.test_code(df_code)
            
    #         # 刷新 Treeview 显示
    #         for i in self.tree.get_children():
    #             self.tree.delete(i)
    #         for r in results:
    #             self.tree.insert("", tk.END, values=(r["query"], r["note"], r["starred"], "✅" if r["hit"] else ""))

    # def on_test_code(self):
    #     # code = self.code_entry.get().strip()
    #     code = self.query_manager.entry_query.get().strip()
    #     if not code:
    #         toast_message(self, "请输入股票代码")
    #         return

    #     df_code = self.df_all.loc[[code]]  # 一定是 DataFrame（query 才能工作）
    #     results = self.query_manager.test_code(df_code)

    #     # 更新 current_history 的命中状态
    #     for i, r in enumerate(results):
    #         if i < len(self.query_manager.current_history):
    #             self.query_manager.current_history[i]["hit"] = r["hit"]

    #     # 刷新 Treeview
    #     self.query_manager.refresh_tree()
    #     toast_message(self, f"{code} 测试完成，共 {len(results)} 条规则")

    def on_test_code(self):
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
            df_code = self.df_all.loc[[code]]
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
        else:
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
        print("启动K线监控...")

        # # 仅初始化一次监控对象
        # if not hasattr(self, "kline_monitor"):
        #     self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=10)
        # else:
        #     print("监控已在运行中。")

        print("启动K线监控...")
        if not hasattr(self, "kline_monitor") or not getattr(self.kline_monitor, "winfo_exists", lambda: False)():
            self.kline_monitor = KLineMonitor(self, lambda: self.df_all, refresh_interval=10)
        else:
            print("监控已在运行中。")
        # 在这里可以启动你的实时监控逻辑，例如:
        # 1. 调用获取数据的线程
        # 2. 计算MACD/BOLL/EMA等指标
        # 3. 输出买卖点提示、强弱信号
        # 4. 定期刷新UI 或 控制台输出


    def write_to_blk(self,append=True):
        if self.current_df.empty:
            return
        # codew=stf.WriteCountFilter(top_temp, writecount=args.dl)
        codew = self.current_df.index.tolist()
        # codew = self.current_df.index.tolist()[:50]
        block_path = tdd.get_tdx_dir_blocknew() + self.blkname
        cct.write_to_blocknew(block_path, codew,append=append,doubleFile=False,keep_last=0,dfcf=False,reappend=True)
        print("wri ok:%s" % block_path)
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
    #             log.error(f"Query error: {e}")

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
    #             log.debug(f'df:{df[:2]}')
    #             self.refresh_tree(df)
    #     except Exception as e:
    #         log.error(f"Error updating tree: {e}", exc_info=True)
    #     finally:
    #         self.after(1000, self.update_tree)

    # ----------------- 数据存档 ----------------- #
    # def save_data_to_csv(self):
    #     if self.current_df.empty:
    #         return
    #     import datetime
    #     file_name = os.path.join(DARACSV_DIR, f"monitor_{self.resample_combo.get()}_{time.strftime('%Y%m%d_%H%M')}.csv")
    #     self.current_df.to_csv(file_name, index=True, encoding="utf-8-sig")
    #     idx =file_name.find('monitor')
    #     status_txt = file_name[idx:]
    #     self.status_var2.set(f"已保存数据到 {status_txt}")

    def save_data_to_csv(self):
        """保存当前 DataFrame 到 CSV 文件，并自动带上当前 query 的 note"""
        if self.current_df.empty:
            return

        import os, re, time
        from datetime import datetime

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
            print(f"[save_data_to_csv] 获取 note 失败: {e}")
            
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
        print(f"[save_data_to_csv] 文件已保存: {file_name}")


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
                # print(f'status_txt:{status_txt}')
                self.status_var2.set(f"已加载数据: {status_txt}")
            except Exception as e:
                log.error(f"加载 CSV 失败: {e}")

    # ----------------- 窗口位置记忆 ----------------- #
    # def save_window_position(self):
    #     pos = {"x": self.winfo_x(), "y": self.winfo_y(), "width": self.winfo_width(), "height": self.winfo_height()}
    #     try:
    #         with open(WINDOW_CONFIG_FILE, "w", encoding="utf-8") as f:
    #             json.dump(pos, f, ensure_ascii=False, indent=2)
    #     except Exception as e:
    #         log.error(f"保存窗口位置失败: {e}")

    # def load_window_position(self):
    #     if os.path.exists(WINDOW_CONFIG_FILE):
    #         try:
    #             with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
    #                 pos = json.load(f)
    #                 # x,y = self.get_centered_window_position(self, pos['width'], pos['height'])
    #                 x,y = clamp_window_to_screens(pos['x'],pos['y'], pos['width'], pos['height'])
    #                 # x,y = self.get_centered_window_position(pos['x'],pos['y'], pos['width'], pos['height'])
    #                 # self.geometry(f"{pos['width']}x{pos['height']}+{pos['x']}+{pos['y']}")
    #                 self.geometry(f"{pos['width']}x{pos['height']}+{x}+{y}")
    #         except Exception as e:
    #             log.error(f"读取窗口位置失败: {e}")


    def save_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE):
        """保存指定窗口位置到统一配置文件"""
        pos = {
            "x": win.winfo_x(),
            "y": win.winfo_y(),
            "width": win.winfo_width(),
            "height": win.winfo_height()
        }

        data = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                log.error(f"读取窗口配置失败: {e}")

        data[window_name] = pos

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存窗口位置失败: {e}")


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


    def load_window_position(self,win, window_name, file_path=WINDOW_CONFIG_FILE, default_width=500, default_height=500):
        """从统一配置文件加载窗口位置"""
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if window_name in data:
                        pos = data[window_name]
                        x, y = clamp_window_to_screens(pos['x'], pos['y'], pos['width'], pos['height'])
                        win.geometry(f"{pos['width']}x{pos['height']}+{x}+{y}")
                        return
            except Exception as e:
                log.error(f"读取窗口位置失败: {e}")
        # 默认居中
        self.center_window(win, default_width, default_height)


    def on_close(self):
        self.alert_manager.save_all()
        # self.save_window_position()
        # 3. 如果 concept 窗口存在，也保存位置并隐藏
        if hasattr(self, "_concept_win") and self._concept_win:
            if self._concept_win.winfo_exists():
                self.save_window_position(self._concept_win, "detail_window")
                self._concept_win.destroy()
                
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
        #     print(f'manager.shutdown : {e}')
        self.destroy()

# class QueryHistoryManager(tk.Frame):
#     def __init__(self, master, search_var1, search_var2, search_combo1, search_combo2, history_file):
#         super().__init__(master)  
class QueryHistoryManager:
    def __init__(self, root=None,search_var1=None, search_var2=None, search_combo1=None,search_combo2=None,auto_run=False,history_file="query_history.json",sync_history_callback=None,test_callback=None):
        """
        root=None 时不创建窗口，只管理数据
        auto_run=True 时直接打开编辑窗口
        """
        self.root = root
        self.history_file = history_file
        self.search_var1 = search_var1
        self.search_var2 = search_var2
        self.his_limit = 30
        self.search_combo1 = search_combo1
        self.search_combo2 = search_combo2
        self.deleted_stack = []  # 保存被删除的 query 记录

        self.sync_history_callback = sync_history_callback
        self.test_callback = test_callback
        # 读取历史
        self.history1, self.history2 = self.load_search_history()
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
        self.combo_group = ttk.Combobox(frame_input, values=["history1", "history2"], state="readonly", width=10)
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
        self.root.bind("<Alt-e>", lambda event: self.open_editor())
        # 为每列绑定排序
        for col in ("query", "star", "note","hit"):
            self.tree.heading(col, text=col.capitalize(), command=lambda _col=col: self.treeview_sort_column(self.tree, _col))
        # # --- 操作按钮 ---
        # frame_btn = tk.Frame(self.editor_frame)
        # frame_btn.pack(fill="x", padx=5, pady=5)
        # tk.Button(frame_btn, text="保存文件", command=self.save_search_history).pack(side="left", padx=5)

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

   
    # add test_code bug
    # def save_search_history(self):
    #     """保存到文件，合并编辑的 N 条到历史顶部，保留最多 MAX_HISTORY 条"""
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
    #             """统一字段格式，确保 starred 为 int，note 存在"""
    #             normalized = []
    #             for r in history:
    #                 if not isinstance(r, dict):
    #                     continue
    #                 q = r.get("query", "")
    #                 starred = r.get("starred", 0)
    #                 note = r.get("note", "")

    #                 # 布尔 → 整数，非法类型 → 0
    #                 if isinstance(starred, bool):
    #                     starred = 1 if starred else 0
    #                 elif not isinstance(starred, int):
    #                     starred = 0

    #                 normalized.append({
    #                     "query": q,
    #                     "starred": starred,
    #                     "note": note
    #                 })
    #             return normalized

    #         def merge_history(current, old):
    #             """合并：current 优先，后补 old 去重"""
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
    #         all_data = {"history1": [], "history2": []}
    #         if os.path.exists(self.history_file):
    #             with open(self.history_file, "r", encoding="utf-8") as f:
    #                 try:
    #                     loaded_data = json.load(f)
    #                     h1_old = dedup(loaded_data.get("history1", []))
    #                     h2_old = dedup(loaded_data.get("history2", []))
    #                     all_data["history1"] = h1_old[self.his_limit:] if len(h1_old) > self.his_limit else []
    #                     all_data["history2"] = h2_old[self.his_limit:] if len(h2_old) > self.his_limit else []
    #                 except json.JSONDecodeError:
    #                     pass

    #         # ---------- 合并并规范 ----------
    #         self.history1 = normalize_history(self.history1)
    #         self.history2 = normalize_history(self.history2)
    #         all_data["history1"] = normalize_history(merge_history(self.history1, all_data.get("history1", [])))
    #         all_data["history2"] = normalize_history(merge_history(self.history2, all_data.get("history2", [])))

    #         # ---------- 写回文件 ----------
    #         with open(self.history_file, "w", encoding="utf-8") as f:
    #             json.dump(all_data, f, ensure_ascii=False, indent=2)

    #         print(f"✅ 搜索历史已保存 (共 {len(all_data['history1'])}/{len(all_data['history2'])})，starred 已统一为整数")

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
            old_data = {"history1": [], "history2": []}
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    try:
                        loaded_data = json.load(f)
                        old_data["history1"] = dedup(loaded_data.get("history1", []))
                        old_data["history2"] = dedup(loaded_data.get("history2", []))
                    except json.JSONDecodeError:
                        pass

            # ---------- 规范当前历史 ----------
            self.history1 = normalize_history(self.history1)
            self.history2 = normalize_history(self.history2)

            # ---------- 合并历史 ----------
            merged_data = {
                "history1": normalize_history(merge_history(self.history1, old_data.get("history1", []))),
                "history2": normalize_history(merge_history(self.history2, old_data.get("history2", []))),
            }

            # ---------- 检测变动量 ----------
            def changes_count(old_list, new_list):
                old_set = {r['query'] for r in old_list}
                new_set = {r['query'] for r in new_list}
                return len(new_set - old_set) + len(old_set - new_set)

            delta1 = changes_count(old_data.get("history1", []), merged_data["history1"])
            delta2 = changes_count(old_data.get("history2", []), merged_data["history2"])

            if delta1 + delta2 >= confirm_threshold:
                if not messagebox.askyesno(
                    "确认保存",
                    f"搜索历史发生较大变动（{delta1 + delta2} 条），是否继续保存？"
                ):
                    print("❌ 用户取消保存搜索历史")
                    return

            # ---------- 写回文件 ----------
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)

            print(f"✅ 搜索历史已保存 "
                  f"(history1: {len(merged_data['history1'])} 条 / "
                  f"history2: {len(merged_data['history2'])} 条)，starred 已统一为整数")

        except Exception as e:
            messagebox.showerror("错误", f"保存搜索历史失败: {e}")


    def load_search_history(self):
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
                    print("✅ 已自动升级 search_history.json 的 starred 字段为整数格式")

            except Exception as e:
                messagebox.showerror("错误", f"加载搜索历史失败: {e}")

        return h1, h2


    # def load_search_history_starred(self):
    #     """从文件加载，只取最后20条作为当前编辑数据"""
    #     h1, h2 = [], []
    #     if os.path.exists(self.history_file):
    #         try:
    #             with open(self.history_file, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #                 # 全量历史，去重
    #                 raw_h1 = [self._normalize_record(r) for r in data.get("history1", [])]
    #                 raw_h2 = [self._normalize_record(r) for r in data.get("history2", [])]

    #                 def dedup(history):
    #                     seen = set()
    #                     result = []
    #                     for r in history:
    #                         q = r.get("query", "")
    #                         if q not in seen:
    #                             seen.add(q)
    #                             result.append(r)
    #                     return result

    #                 raw_h1 = dedup(raw_h1)
    #                 raw_h2 = dedup(raw_h2)
    #                 # 只取最后 20 条作为可编辑区域
    #                 # h1 = raw_h1[-20:] if len(raw_h1) > 20 else raw_h1
    #                 # h2 = raw_h2[-20:] if len(raw_h2) > 20 else raw_h2
    #                 h1 = raw_h1[:self.his_limit] if len(raw_h1) > self.his_limit else raw_h1
    #                 h2 = raw_h2[:self.his_limit] if len(raw_h2) > self.his_limit else raw_h2

    #         except Exception as e:
    #             messagebox.showerror("错误", f"加载搜索历史失败: {e}")

    #     return h1, h2

    # # ========== 数据存取 ==========
    # def save_search_history1(self):
    #     """保存到文件，自动按 query 去重"""
    #     try:
    #         # 去重
    #         def dedup(history):
    #             seen = set()
    #             result = []
    #             for r in history:
    #                 q = r.get("query") if isinstance(r, dict) else str(r)
    #                 if q not in seen:
    #                     seen.add(q)
    #                     result.append(r)
    #             return result

    #         self.history1 = dedup(self.history1)
    #         self.history2 = dedup(self.history2)

    #         data = {
    #             "history1": self.history1,
    #             "history2": self.history2
    #         }
    #         with open(self.history_file, "w", encoding="utf-8") as f:
    #             json.dump(data, f, ensure_ascii=False, indent=2)
    #     except Exception as e:
    #         messagebox.showerror("错误", f"保存搜索历史失败: {e}")


    # def load_search_history1(self):
    #     """从文件加载并去重"""
    #     h1, h2 = [], []
    #     if os.path.exists(self.history_file):
    #         try:
    #             with open(self.history_file, "r", encoding="utf-8") as f:
    #                 data = json.load(f)
    #                 h1 = [self._normalize_record(r) for r in data.get("history1", [])]
    #                 h2 = [self._normalize_record(r) for r in data.get("history2", [])]

    #             # 按 query 去重
    #             def dedup(history):
    #                 seen = set()
    #                 result = []
    #                 for r in history:
    #                     q = r.get("query", "")
    #                     if q not in seen:
    #                         seen.add(q)
    #                         result.append(r)
    #                 return result

    #             h1 = dedup(h1)
    #             h2 = dedup(h2)

    #         except Exception as e:
    #             messagebox.showerror("错误", f"加载搜索历史失败: {e}")
    #     return h1, h2


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

    # # ========== 功能 ==========
    # def switch_group(self, event=None):
    #     sel = self.combo_group.get()
    #     if sel == "history1":
    #         self.current_history = self.history1
    #         self.current_key = "history1"
    #     else:
    #         self.current_history = self.history2
    #         self.current_key = "history2"
    #     self.refresh_tree()

    def switch_group(self, event=None):
        self.clear_hits()
        if getattr(self, "_suppress_switch", False):
            return

        sel = self.combo_group.get()
        if sel == "history1":
            self.current_history = self.history1
            self.current_key = "history1"
        else:
            self.current_history = self.history2
            self.current_key = "history2"

        print(f"[SWITCH] 当前分组切换到：{sel}")
        self.refresh_tree()


    # def add_query(self):
    #     query = self.entry_query.get().strip()
    #     if not query:
    #         messagebox.showwarning("提示", "请输入 Query")
    #         return
    #     self.current_history.insert(0, {"query": query, "starred":  0, "note": ""})
    #     self.refresh_tree()
    #     self.entry_query.delete(0, tk.END)
    #     self.save_search_history()

    def edit_query(self, iid):
        values = self.tree.item(iid, "values")
        if not values:
            return
        current_query = values[0]

        idx = next((i for i, r in enumerate(self.current_history) if r.get("query") == current_query), None)
        if idx is None:
            return

        record = self.current_history[idx]
        new_query = self.askstring_at_parent(self.root, "修改 Query", "请输入新的 Query：", initialvalue=record.get("query", ""))
        if new_query and new_query.strip():
            new_query = new_query.strip()
            old_query = record["query"]
            # record["query"] = new_query
            if self.current_key == "history1":
                self.history1[idx]["query"] = new_query
                # values = list(self.search_combo1["values"])
                # # 更新下拉项：删除旧值，插入新值到最前
                # if old_query in values:
                #     values.remove(old_query)
                # if new_query not in values:
                #     values.insert(0, new_query)
                #     if self.search_var1.get() == old_query:
                #         self.search_var1.set(new_query)
                # self.search_combo1["values"] = values

            else:
                self.history2[idx]["query"] = new_query
                # values = list(self.search_combo2["values"])
                # if old_query in values:
                #     values.remove(old_query)
                # if new_query not in values:
                #     values.insert(0, new_query)
                #     if self.search_var2.get() == old_query:
                #         self.search_var2.set(new_query)
                # self.search_combo2["values"] = values
            # ✅ 设置全局标志（主窗口 sync_history 会读取）
            self._just_edited_query = (old_query, new_query)
            # print(f'record2 : {record}')
            # self.sync_history_current(record)
            self.refresh_tree()
            if self.current_key == "history1":
                self.use_query(new_query)
            # self.save_search_history()


    # def add_query(self):
    #     query = self.entry_query.get().strip()
    #     if not query:
    #         messagebox.showwarning("提示", "请输入 Query")
    #         return

    #     # 确定当前操作的是哪一个历史区
    #     target_history = self.current_history
    #     if target_history is None:
    #         messagebox.showwarning("提示", "未找到当前历史记录区")
    #         return

    #     # 查重：是否已存在相同 query
    #     existing = next((item for item in target_history if item["query"] == query), None)

    #     if existing:
    #         # 如果已有星标或备注，则仅置顶，不覆盖
    #         if existing.get("starred", 0) > 0 or existing.get("note", "").strip():
    #             target_history.remove(existing)
    #             target_history.insert(0, existing)
    #         else:
    #             # 没有星标/备注，替换为新的记录
    #             target_history.remove(existing)
    #             target_history.insert(0, {"query": query, "starred": 0, "note": ""})
    #     else:
    #         # 新增记录
    #         target_history.insert(0, {"query": query, "starred": 0, "note": ""})

    #     # 限制最大条数（根据区分 history1 / history2）
    #     if target_history is self.history1:
    #         self.history1 = self.history1[:self.MAX_HISTORY]
    #     elif target_history is self.history2:
    #         self.history2 = self.history2[:self.MAX_HISTORY]

    #     # 刷新 TreeView
    #     self.refresh_tree()

    #     # 自动保存更新
    #     self.save_search_history()

    def add_query(self):
        query = self.entry_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入 Query")
            return

        # 判断是否为 6 位数字
        if (query.isdigit() or len(query) == 6):
            toast_message(self.root, "股票代码仅测试使用")
            return

        # # 查重：如果已存在，先删除旧的
        # existing = next((item for item in self.current_history if item["query"] == query), None)
        # if existing:
        #     self.current_history.remove(existing)

        # # 插入到顶部
        # self.current_history.insert(0, {"query": query, "starred":  0, "note": ""})

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
        else:  # history2
            self.history2 = self.current_history

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


    # def on_click_star(self, event):
    #     region = self.tree.identify("region", event.x, event.y)
    #     if region != "cell":
    #         return
    #     col = self.tree.identify_column(event.x)
    #     if col != "#2":
    #         return
    #     row_id = self.tree.identify_row(event.y)
    #     if not row_id:
    #         return
    #     idx = int(row_id) - 1
    #     if 0 <= idx < len(self.current_history):
    #         self.current_history[idx]["starred"] = not self.current_history[idx]["starred"]
    #         self.refresh_tree()
    #         # self.save_search_history()

    # def on_double_click(self, event):
    #     region = self.tree.identify("region", event.x, event.y)
    #     if region != "cell":
    #         return
    #     col = self.tree.identify_column(event.x)
    #     row_id = self.tree.identify_row(event.y)
    #     if not row_id:
    #         return
    #     idx = int(row_id) - 1
    #     record = self.current_history[idx]

    #     if col == "#1":
    #         new_q = simpledialog.askstring("修改 Query", "请输入新的 Query：", initialvalue=record["query"])
    #         if new_q is not None and new_q.strip():
    #             record["query"] = new_q.strip()
    #             self.refresh_tree()
    #             self.save_search_history()
    #     elif col == "#3":
    #         new_note = simpledialog.askstring("修改备注", "请输入新的备注：", initialvalue=record["note"])
    #         if new_note is not None:
    #             record["note"] = new_note
    #             self.refresh_tree()
    #             self.save_search_history()

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
            print(f"[WARN] 获取显示器信息失败: {e}")

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
            print(f"✅ 命中屏幕 ({left},{top},{right},{bottom}) scale={scale:.2f} → ({x},{y})")
        else:
            # 未命中任何屏幕则居中主屏
            main_left, main_top, main_right, main_bottom = monitors[0]
            x = main_left + (main_right - main_left - win_width) // 2
            y = main_top + (main_bottom - main_top - win_height) // 2
            print(f"⚠️ 未命中屏幕, 使用主屏居中 scale={scale:.2f} → ({x},{y})")

        return int(x), int(y)


    def askstring_at_parent(self,parent, title, prompt, initialvalue=""):
        # 创建临时窗口
        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(False, False)

        # 计算位置，靠父窗口右侧居中
        char_width = 6
        min_width = 400
        max_width = 1000
        win_width = max(min_width, min(len(initialvalue) * char_width + 50, max_width))
        win_height = 120
        # win_width, win_height = 520, 120
        x, y = self.get_centered_window_position_query(parent, win_width, win_height)
        # monitors = MONITORS or [(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))]
        # x, y = clamp_window_to_screens(x, y, width, height, monitors)
        # print(f'len(initialvalue) : {len(initialvalue)} win_width : {win_width} , x : {x} ,y : {y}')
        print(f"askstring_at_parent {win_width}x{win_height}+{x}+{y}")
        dlg.geometry(f"{win_width}x{win_height}+{x}+{y}")

        result = {"value": None}

        tk.Label(dlg, text=prompt).pack(pady=1, padx=5)
        entry = tk.Entry(dlg)
        entry.pack(pady=1, padx=5, fill="x", expand=True)
        entry.insert(0, initialvalue)
        entry.lift()
        entry.focus_set()

        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=1)
        tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
        tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

        # ✅ 新增：按 ESC 关闭对话框
        dlg.bind("<Escape>", lambda e: on_cancel())

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
                else:
                    self.history2[idx]["note"] = new_note
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
        else:  # history2
            self.search_var2.set(query)
            # self.history2 = self.current_history
            if query not in self.search_combo2["values"]:
                values = list(self.search_combo2["values"])
                values.insert(0, query)
                self.search_combo2["values"] = values


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

    '''
    def sync_history_current(self, record, action="delete"):
        """
        同步主窗口的历史列表
        action: "delete" 删除记录（默认） | "add" 恢复记录（undo）
        """
        query = record.get("query")
        if not query:
            return

        if self.current_key == "history1":
            if action == "delete":
                # 删除记录
                self.history1 = [r for r in self.history1 if r["query"] != query]
            elif action == "add":
                # 撤销删除 → 恢复记录
                if not any(r["query"] == query for r in self.history1):
                    self.history1.insert(0, record)  # 插到最前面
            # 更新下拉列表
            self.search_combo1["values"] = [r["query"] for r in self.history1]
            # 清除输入框中刚被删掉的项
            if action == "delete" and self.search_var1.get() == query:
                self.search_var1.set("")
            if action == "add" and self.search_var1.get() == query:
                self.search_var1.set(query)
            # 回调同步给主窗口
            try:
                if callable(self.sync_history_callback):
                    self.sync_history_callback(self.history1)
            except Exception:
                pass

        else:  # history2
            if action == "delete":
                self.history2 = [r for r in self.history2 if r["query"] != query]
            elif action == "add":
                if not any(r["query"] == query for r in self.history2):
                    self.history2.insert(0, record)
            self.search_combo2["values"] = [r["query"] for r in self.history2]
            if action == "delete" and self.search_var2.get() == query:
                self.search_var2.set("")
            if action == "add" and self.search_var1.get() == query:
                self.search_var1.set(query)
            try:
                if callable(self.sync_history_callback):
                    self.sync_history_callback(self.history2)
            except Exception:
                pass

        self.refresh_tree()

    def delete_item(self, iid):
        """删除选中项并保存到撤销栈"""
        idx = int(iid) - 1
        if not (0 <= idx < len(self.current_history)):
            return

        # 取出被删除的记录
        record = self.current_history.pop(idx)

        # 保存到撤销栈（支持 Ctrl+Z 恢复）
        self.deleted_stack.append({
            "record": record,
            "history_key": self.current_key,
            "index": idx
        })

        # 限制撤销栈大小（可选）
        if len(self.deleted_stack) > 20:
            self.deleted_stack.pop(0)

        # 同步到全局（主程序保存、写入文件等）
        self.sync_history_current(record)
        # 刷新界面
        self.refresh_tree()

    def undo_delete(self, event=None):
        if not self.deleted_stack:
            toast_message(self.root,"没有可撤销的删除记录")
            return

        last_deleted = self.deleted_stack.pop()
        record = last_deleted["record"]
        history_key = last_deleted["history_key"]
        index = last_deleted["index"]

        if history_key == "history1":
            target_history = self.history1
        else:
            target_history = self.history2

        # ✅ 插入原来的完整记录（包括 note / starred）
        if 0 <= index <= len(target_history):
            target_history.insert(index, record)
        else:
            target_history.insert(0, record)

        # ✅ 同步回主窗口
        self.sync_history_current(record, action="add")

        # messagebox.showinfo("提示", f"已恢复删除的 Query：{record.get('query', '')}")
        toast_message(self.root ,f"已恢复删除的 Query：{record.get('query', '')}")

    '''
    
    def sync_history_current(self, record, action="delete", history_key=None):
        """
        同步主窗口与 QueryHistoryManager 的状态。
        支持 delete / add，带防循环保护与分组标识。
        """
        if history_key is None:
            history_key = self.current_key

        query = record.get("query")
        if not query:
            return

        # --- 选择目标控件与历史 ---
        if history_key == "history1":
            combo, var, target = self.search_combo1, self.search_var1, self.history1
        else:
            combo, var, target = self.search_combo2, self.search_var2, self.history2

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
                else:
                    self.sync_history_callback(search_history2=self.history2)
            except Exception as e:
                print(f"[SYNC ERR] {e}")

        # --- 刷新 UI，但防止误触 switch ---
        suppress_state = getattr(self, "_suppress_switch", False)
        self._suppress_switch = True
        try:
            self.refresh_tree()
        finally:
            self._suppress_switch = suppress_state

    # def sync_history_current(self, record, action="delete", history_key=None):
    #     """
    #     同步主窗口的 ComboBox 与数据结构
    #     record: 被操作的记录 dict
    #     action: "delete" 或 "add"
    #     history_key: "history1" 或 "history2"（如果为 None，则使用 self.current_key 作为后备）
    #     """
    #     if history_key is None:
    #         history_key = self.current_key

    #     query = record.get("query")
    #     if not query:
    #         return

    #     if history_key == "history1":
    #         combo = self.search_combo1
    #         var = self.search_var1
    #         target = self.history1
    #     else:
    #         combo = self.search_combo2
    #         var = self.search_var2
    #         target = self.history2

    #     if action == "delete":
    #         # 删除：从目标历史和下拉框移除
    #         target[:] = [r for r in target if r.get("query") != query]
    #         combo['values'] = [r.get("query") for r in target]
    #         if var.get() == query:
    #             var.set("")
    #     elif action == "add":
    #         # 恢复：插入完整记录（保留 note/starred）
    #         if not any(r.get("query") == query for r in target):
    #             target.insert(0, record.copy())
    #         combo['values'] = [r.get("query") for r in target]

    #     # callback：同步回主窗口 / 外层
    #     try:
    #         if callable(self.sync_history_callback):
    #             # 仍然传回单个 list（兼容现有接收方）
    #             self.sync_history_callback(target)
    #     except Exception:
    #         pass

    #     # 刷新 Treeview
    #     self.refresh_tree()

    # def delete_item(self, iid):
    #     idx = int(iid) - 1
    #     if 0 <= idx < len(self.current_history):
    #         record = self.current_history.pop(idx)

    #         # 保存完整删除记录（带 note/starred）
    #         self.deleted_stack.append({
    #             "record": record.copy(),
    #             "history_key": self.current_key,
    #             "index": idx
    #         })

    #         # 传入 history_key，避免依赖 self.current_key（更稳）
    #         self.sync_history_current(record, action="delete", history_key=self.current_key)

    def delete_item(self, iid):
        idx = int(iid) - 1
        if not (0 <= idx < len(self.current_history)):
            return

        record = self.current_history.pop(idx)

        # 精确识别所属分组
        if self.current_history is self.history2:
            history_key = "history2"
        else:
            history_key = "history1"

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

        print(f"[DEL] 从 {history_key} 删除 {record.get('query')}")


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
        else:
            target_history = self.history2

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

    # def move_to_top(self, iid):
    #     idx = int(iid) - 1
    #     if 0 <= idx < len(self.current_history):
    #         record = self.current_history.pop(idx)
    #         self.current_history.insert(0, record)

    #         # 同步主窗口 history
    #         if self.current_key == "history1":
    #             # self.history1 = [r for r in self.history1 if r["query"] != record["query"]]
    #             # self.history1.insert(0, record)
    #             self.history1 = record
    #             self.search_combo1['values'] = [r["query"] for r in self.history1]
    #             self.search_var1.set(self.search_combo1['values'][0])
    #         else:
    #             # self.history2 = [r for r in self.history2 if r["query"] != record["query"]]
    #             # self.history2.insert(0, record)
    #             self.history2 = record
    #             self.search_combo2['values'] = [r["query"] for r in self.history2]
    #             self.search_var2.set(self.search_combo2['values'][0])
    #         self.refresh_tree()



    # def refresh_tree_sr(self):
    #     # # 自动同步当前显示的历史
    #     if self.current_key == "history1":
    #         self.current_history = self.history1
    #     else:
    #         # self.current_history = [{"query": q, "starred":  0, "note": ""} for q in self.history2]
    #         self.current_history = self.history2
    #     # 清空Treeview
    #     for i in self.tree.get_children():
    #         self.tree.delete(i)
        
    #     # 填充Treeview
    #     for idx, record in enumerate(self.current_history, start=1):
    #         #单星
    #         # star = "⭐" if record.get("starred") else ""

    #         # 原来：star_text = "★" if rec.get("starred") else ""
    #         star_count = record.get("starred", 0)
    #         if isinstance(star_count, bool):
    #             star_count = 1 if star_count else 0
    #         star_text = "★" * star_count

    #         note = record.get("note", "")
    #         self.tree.insert("", "end", iid=str(idx), values=(record.get("query", ""), star_text, note))


    # def refresh_tree_hit(self):
    #     """
    #     刷新 Treeview 显示
    #     - 当前历史 self.current_history 自动同步
    #     - 根据 record['hit'] 添加符号 ✅/❌ 并设置背景颜色
    #     """
    #     # 自动同步当前显示的历史
    #     if self.current_key == "history1":
    #         self.current_history = self.history1
    #     else:
    #         self.current_history = self.history2

    #     # 清空 Treeview
    #     self.tree.delete(*self.tree.get_children())

    #     # 配置 tag 颜色
    #     self.tree.tag_configure("hit", background="#d1ffd1")   # 命中绿色
    #     self.tree.tag_configure("miss", background="#ffd1d1")  # 未命中红色
    #     self.tree.tag_configure("normal", background="#ffffff") # 默认白色

    #     for idx, record in enumerate(self.current_history, start=1):
    #         star_count = record.get("starred", 0)
    #         if isinstance(star_count, bool):
    #             star_count = 1 if star_count else 0
    #         star_text = "★" * star_count
    #         note = record.get("note", "")
    #         query_text = record.get("query", "")

    #         # ✅ 显示时添加命中/未命中符号，但不修改原始 record
    #         display_query = query_text
    #         hit = record.get("hit", None)
    #         if hit is True:
    #             display_query = "✅ " + query_text
    #             tag = "hit"
    #         elif hit is False:
    #             display_query = "❌ " + query_text
    #             tag = "miss"
    #         else:
    #             tag = "normal"

    #         # 插入 Treeview
    #         self.tree.insert("", "end", iid=str(idx),
    #                          values=(display_query, star_text, note),
    #                          tags=(tag,))

    def refresh_tree(self):
        """
        刷新 Treeview 显示
        - 当前历史 self.current_history 自动同步
        - 根据 record['hit'] 设置 hit 列显示，并设置背景颜色
        """
        # 自动同步当前显示的历史
        self.current_history = self.history1 if self.current_key == "history1" else self.history2

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
                self.test_callback()

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


class ColumnSetManager(tk.Toplevel):
    def __init__(self, master, all_columns, config, on_apply_callback, default_cols, auto_apply_on_init=False):
        super().__init__(master)
        self.title("列组合管理器")
        # 基础尺寸（用于初始化宽度 fallback）
        # 如果不希望初始显示窗口（隐藏）
        self.auto_apply_on_init = auto_apply_on_init
        if self.auto_apply_on_init:
            self.withdraw()  # 先隐藏窗口

        self.width = 800
        self.height = 500
        self.geometry(f"{self.width}x{self.height}")

        # 参数
        self.all_columns = list(all_columns)
        self.no_filtered = []
        self.config = config if isinstance(config, dict) else {}
        self.on_apply_callback = on_apply_callback
        self.default_cols = list(default_cols)

        # 状态
        self.current_set = list(self.config.get("current", self.default_cols.copy()))
        self.saved_sets = list(self.config.get("sets", []))  # 格式：[{ "name": str, "cols": [...] }, ...]

        # 存放 checkbutton 的 BooleanVar，防 GC
        self._chk_vars = {}

        # 拖拽数据（用于 tag 拖拽）
        self._drag_data = {"widget": None, "start_x": 0, "start_y": 0, "idx": None}

        # 防抖 job id
        self._resize_job = None

        # 构建 UI
        self._build_ui()

        # 延迟首次布局（保证 winfo_width() 可用）
        self.after(80, self.update_grid)

        # 绑定窗口 resize（防抖）
        # self.bind("<Configure>", self._on_resize)

    def _build_ui(self):
        # 主容器：左右两栏（左：选择区 + 当前组合；右：已保存组合）
        self.main = ttk.Frame(self)
        self.main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(self.main)
        top.pack(fill=tk.BOTH, expand=True, padx=6, pady=1)

        left = ttk.Frame(top)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(top, width=220)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        # 搜索栏（放在 left 顶部）
        search_frame = ttk.Frame(left)
        search_frame.pack(fill=tk.X, pady=(0,6))
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.search_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,0))
        entry.bind("<KeyRelease>", lambda e: self._debounced_update())

        # 列选择区（canvas + scrollable_frame）
        grid_container = ttk.Frame(left)
        grid_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(grid_container, height=160)
        self.vscroll = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.inner_frame = ttk.Frame(self.canvas)  # 放 checkbuttons 的 frame
        # 当 inner_frame size 改变时，同步调整 canvas scrollregion
        self.inner_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0,0), window=self.inner_frame, anchor="nw")

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮在 canvas 上滚动（适配 Windows 与 Linux）
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_mousewheel(False))

        # 当前组合横向标签（自动换行 + 拖拽）
        current_lf = ttk.LabelFrame(left, text="当前组合")
        current_lf.pack(fill=tk.X, pady=(6,0))
        self.current_frame = tk.Frame(current_lf, height=60)
        self.current_frame.pack(fill=tk.X, padx=4, pady=6)
        # 确保 current_frame 能获取尺寸变化事件
        self.current_frame.bind("<Configure>", lambda e: self._debounced_refresh_tags())

        # 右侧：已保存组合列表与管理按钮
        ttk.Label(right, text="已保存组合").pack(anchor="w", padx=6, pady=(6,0))
        self.sets_listbox = tk.Listbox(right, exportselection=False)
        self.sets_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        # 单击选中高亮 → 更新当前选中组合名（但不加载）
        self.sets_listbox.bind("<<ListboxSelect>>", self.on_select_saved_set)

        self.sets_listbox.bind("<Double-1>", lambda e: self.load_selected_set())

        sets_btns = ttk.Frame(right)
        sets_btns.pack(fill=tk.X, padx=6, pady=(0,6))
        ttk.Button(sets_btns, text="加载", command=self.load_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sets_btns, text="删除", command=self.delete_selected_set).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        self.lbl_current_set = ttk.Label(right, text="当前选中: (无)")
        self.lbl_current_set.pack(anchor="w", padx=6, pady=(0,4))


        # 底部按钮（全宽）
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(bottom, text="保存组合", command=self.save_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(bottom, text="应用组合", command=self.apply_current_set).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=6)
        ttk.Button(bottom, text="恢复默认", command=self.restore_default).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.bind("<Alt-c>",lambda e:self.open_column_manager_editor())
        # 填充保存组合列表
        self.refresh_saved_sets()


        # 初始化后自动应用当前列组合（不会弹出窗口）
        if self.auto_apply_on_init:
            try:
                self.set_current_set()
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("⚠️ 自动应用列组合失败：", e)

    # def open_column_manager_editor(self):
    #     """在已有 root 上打开编辑窗口"""
    #     #应用于frame
    #     if  hasattr(self, "main"):
    #         if self.winfo_ismapped():
    #             self.pack_forget()  # 隐藏
    #         else:
    #             self.pack(fill="both", expand=True)  # 仅显示，不移动位置

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

    # def init_column_manager_editor(self):
    #     """切换显示/隐藏"""
    #     if self.state() == "withdrawn":
    #         # 已隐藏 → 显示
    #         # self.deiconify()
    #         # self.lift()
    #         # self.focus_set()
    #         pass
    #     else:
    #         # 已显示 → 隐藏
    #         self.withdraw()

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

    # ---------------------------
    # 防抖 resize（避免重复刷新）
    # ---------------------------
    # def _on_resize(self, event):
    #     if self._resize_job:
    #         self.after_cancel(self._resize_job)
    #     self._resize_job = self.after(120, self._debounced_update)

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
        # print(f'search : {search}')
        if search == "":
            filtered = [c for c in self.all_columns if self.default_filter(c)]
        elif search == "no" or search == "other":
            filtered = [c for c in self.all_columns if not self.default_filter(c)]
        else:
            filtered = [c for c in self.all_columns if search in c.lower()]

        # no_filtered = [c for c in self.all_columns if not self.default_filter(c)]
        # if no_filtered != self.no_filtered:
        #     self.no_filtered = no_filtered
        #     print(f'no_filtered : {no_filtered}')

        # filtered = [c for c in self.all_columns if search in c.lower()]

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

        for i, col in enumerate(filtered):
            var = tk.BooleanVar(value=(col in self.current_set))
            self._chk_vars[col] = var
            chk = ttk.Checkbutton(self.inner_frame, text=col, variable=var,
                                  command=lambda c=col, v=var: self._on_check_toggle(c, v.get()))
            chk.grid(row=i // cols_per_row, column=i % cols_per_row, sticky="w", padx=4, pady=3)

        # 刷新当前组合标签显示
        # print(f'update_grid')
        self.refresh_current_tags()

    def _on_check_toggle(self, col, state):
        if state:
            if col not in self.current_set:
                self.current_set.append(col)
        else:
            if col in self.current_set:
                self.current_set.remove(col)
        # print(f'_on_check_toggle')
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
            # print(f'total_height:{total_height}')

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

        print(f"_start_drag {idx}")


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
                print("Reorder error:", e)

        # print(f"drag: {orig_idx} → {new_idx}")

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
    #             print(f'_start_drag')
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
    #             print("Reorder error:", e)

    #     # print(f"drag: {orig_idx} -> {new_idx}")

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

    def askstring_at_parent(self,parent, title, prompt, initialvalue=""):
        # 创建临时窗口
        dlg = tk.Toplevel(parent)
        dlg.transient(parent)
        dlg.title(title)
        dlg.resizable(False, False)

        # 计算位置，靠父窗口右侧居中
        win_width, win_height = 300, 120
        x, y = self.get_centered_window_position(parent, win_width, win_height)
        dlg.geometry(f"{win_width}x{win_height}+{x}+{y}")

        result = {"value": None}

        tk.Label(dlg, text=prompt).pack(pady=5, padx=5)
        entry = tk.Entry(dlg)
        entry.pack(pady=5, padx=5, fill="x", expand=True)
        entry.insert(0, initialvalue)
        entry.focus_set()

        def on_ok():
            result["value"] = entry.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        frame_btn = tk.Frame(dlg)
        frame_btn.pack(pady=5)
        tk.Button(frame_btn, text="确定", width=10, command=on_ok).pack(side="left", padx=5)
        tk.Button(frame_btn, text="取消", width=10, command=on_cancel).pack(side="left", padx=5)

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
            print(f"选中组合: {self.current_set_name}")


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
        # print(f'restore_default self.default_cols : {self.default_cols}')
        # sync checkboxes
        for col, var in self._chk_vars.items():
            var.set(col in self.current_set)
        self.refresh_current_tags()
        toast_message(self, "已恢复默认组合")

# ========== 信号检测函数 ==========
def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty:
        return df

    if "code" not in df.columns:
        df["code"] = df.index.astype(str).str.zfill(6)  # 补齐6位  # 如果没有code列，用name占位（最好是实际code）

    df["signal"] = ""
    df["emotion"] = "中性"

    # 买入逻辑
    buy_cond = (
        (df["now"] > df["ma5d"]) &
        (df["ma5d"] > df["ma10d"]) &
        (df["macddif"] > df["macddea"]) &
        (df["rsi"] < 70) &
        ((df["now"] > df["upperL"]) | (df["now"] > df["upper1"]))
    )

    # 卖出逻辑
    sell_cond = (
        (df["now"] < df["ma10d"]) &
        (df["macddif"] < df["macddea"]) &
        (df["rsi"] > 50) &
        (df["now"] < df["upperL"])
    )

    df.loc[buy_cond, "signal"] = "BUY"
    df.loc[sell_cond, "signal"] = "SELL"

    # 情绪判定
    df.loc[df["vchange"] > 20, "emotion"] = "乐观"
    df.loc[df["vchange"] < -20, "emotion"] = "悲观"

    return df



class KLineMonitor(tk.Toplevel):
    def __init__(self, parent, get_df_func, refresh_interval=3):
        """
        parent: 主窗口实例（例如 MainWindow）
        get_df_func: 返回最新DataFrame的函数（例如 lambda: self.df_all）
        """
        super().__init__(parent)
        self.master = parent     # ✅ 保存主窗口引用，便于回调
        self.get_df_func = get_df_func
        self.refresh_interval = refresh_interval
        self.stop_event = threading.Event()

        self.title("K线趋势实时监控")
        self.geometry("720x420")

        # ---- 状态栏 ----
        self.status_label = tk.Label(self, text="监控中...", bg="#eee")
        self.status_label.pack(fill="x")

        # ---- 表格设置 ----
        self.tree = ttk.Treeview(self, columns=("code", "name", "now", "signal", "emotion"),
                                 show="headings", height=20)
        self.tree.pack(fill=tk.BOTH, expand=True)

        for col, text, w in [
            ("code", "代码", 80),
            ("name", "名称", 150),
            ("now", "当前价", 80),
            ("signal", "信号", 80),
            ("emotion", "情绪", 100)
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="center")


        self.tree.tag_configure("buy", background="#d0f5d0")    # 绿色
        self.tree.tag_configure("sell", background="#f5d0d0")   # 红色
        self.tree.tag_configure("neutral", background="#f0f0f0")# 灰色

        # ---- 绑定点击事件 ----
        self.tree.bind("<Button-1>", self.on_tree_click)

        # ---- 启动监控线程 ----
        threading.Thread(target=self.refresh_loop, daemon=True).start()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_tree_click(self, event):
        """表格单击事件（可回调主窗口）"""
        try:
            item_id = self.tree.identify_row(event.y)
            if not item_id:
                return
            values = self.tree.item(item_id, "values")
            stock_code = values[0] if len(values) > 0 else None

            print(f"[Monitor] 点击了 {stock_code}")

            # ✅ 如果主窗口有 on_single_click 方法，则调用它
            if hasattr(self.master, "on_single_click"):
                # self.master.on_single_click(name)
                send_tdx_Key = (getattr(self.master, "select_code", None) != stock_code)
                self.master.select_code = stock_code

                stock_code = str(stock_code).zfill(6)
                # print(f"选中股票代码: {stock_code}")

                if send_tdx_Key and stock_code:
                    self.master.sender.send(stock_code)
        except Exception as e:
            print(f"[Monitor] 点击处理错误: {e}")

    def refresh_loop(self):
        """后台刷新循环"""
        while not self.stop_event.is_set():
            try:
                df = self.get_df_func()
                if df is not None and not df.empty:
                    df = detect_signals(df)
                    self.after(0, lambda d=df: self.update_table(d))
            except Exception as e:
                print("[Monitor] 更新错误:", e)
            time.sleep(self.refresh_interval)

    def update_table(self, df):
        """更新表格内容"""
        self.tree.delete(*self.tree.get_children())
        for _, r in df.iterrows():
            tag = "neutral"
            if r["signal"] == "BUY":
                tag = "buy"
            elif r["signal"] == "SELL":
                tag = "sell"
            self.tree.insert(
                "", tk.END,
                values=(r.get("code", ""), r.get("name", ""), f"{r.get('now', 0):.2f}", r.get("signal", ""), r.get("emotion", "")),
                tags=(tag,)
            )

    def on_close(self):
        self.stop_event.set()
        self.destroy()
        if hasattr(self.master, "kline_monitor"):
            self.master.kline_monitor = None


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

    # 直接单线程调用
    fetch_and_process(shared_dict, q, blkname="boll", flag=flag)



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
    # test_single_thread()
    # import ipdb;ipdb.set_trace()


    app = StockMonitorApp()
    if cct.isMac():
        width, height = 100, 32
        cct.set_console(width, height)
    else:
        width, height = 100, 32
        cct.set_console(width, height)
    app.mainloop()

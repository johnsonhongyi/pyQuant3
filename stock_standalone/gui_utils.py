# -*- coding:utf-8 -*-
import sys
import os
import ctypes
import platform
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

try:
    import win32api
except ImportError:
    win32api = None

from JohnsonUtil import LoggerFactory
from typing import Any, Optional, Union, List, Tuple

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.GUI")

# 全局缓存显示器信息
MONITORS: List[Tuple[int, int, int, int]] = []

def bind_mouse_scroll(widget: tk.Widget, speed: int = 3) -> None:
    """支持 Alt/Shift + 滚轮及直接水平滚动的通用鼠标滚轮绑定"""
    system = platform.system()

    def on_vertical_scroll(event):
        widget.yview_scroll(-int(event.delta / 120) * speed, "units")

    def on_horizontal_scroll(event):
        widget.xview_scroll(-int(event.delta / 120) * speed, "units")

    if system == "Windows":
        widget.bind("<MouseWheel>", on_vertical_scroll)
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

def enable_native_horizontal_scroll(tree: ttk.Treeview, speed: int = 5) -> None:
    """为 Treeview 添加跨平台水平滚动支持"""
    def on_shift_wheel(event):
        delta = -1 if event.delta > 0 else 1
        tree.xview_scroll(delta * speed, "units")
        return "break"

    tree.bind("<Shift-MouseWheel>", on_shift_wheel)
    if platform.system() != "Windows":
        def on_button_scroll(event):
            if event.num == 6:
                tree.xview_scroll(-speed, "units")
            elif event.num == 7:
                tree.xview_scroll(speed, "units")
            return "break"
        tree.bind("<Button-6>", on_button_scroll)
        tree.bind("<Button-7>", on_button_scroll)

def get_monitor_index_for_window(window: tk.Toplevel) -> int:
    """根据窗口位置找到所属显示器索引"""
    global MONITORS
    if not MONITORS:
        _ = init_monitors()
    try:
        x = window.winfo_rootx()
        y = window.winfo_rooty()
        for i, (left, top, right, bottom) in enumerate(MONITORS):
            if left <= x < right and top <= y < bottom:
                return i
    except:
        pass
    return 0

class RECT(ctypes.Structure):
    _fields_: list[tuple[str, type[ctypes.c_long]]] = [
        ("left", ctypes.c_long), ("top", ctypes.c_long), 
        ("right", ctypes.c_long), ("bottom", ctypes.c_long)
    ]

class MONITORINFO(ctypes.Structure):
    _fields_: list[tuple[str, type[ctypes.c_long]]] = [
        ("cbSize", ctypes.c_long), ("rcMonitor", RECT), 
        ("rcWork", RECT), ("dwFlags", ctypes.c_long)
    ]

def get_monitor_by_point(x: int, y: int) -> dict[str, int]:
    """返回包含坐标(x,y)的屏幕信息字典 (Windows 专用)"""
    if platform.system() != "Windows":
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}
    
    monitors: list[dict[str, int]] = []

    def monitor_enum_proc(hMonitor: int, hdcMonitor: int, lprcMonitor: ctypes.POINTER(RECT), dwData: float) -> int:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        rc = info.rcMonitor
        monitors.append({
            "left": rc.left, "top": rc.top, "right": rc.right, "bottom": rc.bottom,
            "width": rc.right - rc.left, "height": rc.bottom - rc.top
        })
        return 1

    MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(RECT), ctypes.c_double)
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(monitor_enum_proc), 0)

    for m in monitors:
        if m['left'] <= x < m['right'] and m['top'] <= y < m['bottom']:
            return m
    return monitors[0] if monitors else {"left": 0, "top": 0, "width": 1920, "height": 1080}

def get_all_monitors() -> List[Tuple[int, int, int, int]]:
    """返回所有显示器的边界列表 [(left, top, right, bottom), ...]"""
    if not win32api:
        return []
    monitors = []
    for handle_tuple in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(handle_tuple[0])
        monitors.append(info["Monitor"])
    return monitors

def init_monitors() -> List[Tuple[int, int, int, int]]:
    """扫描所有显示器并缓存信息"""
    global MONITORS
    MONITORS = get_all_monitors()
    if not MONITORS and win32api:
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        MONITORS = [(0, 0, screen_width, screen_height)]
    return MONITORS

def tk_geometry_to_rect(tk_win: Union[tk.Tk, tk.Toplevel]) -> Tuple[int, int, int, int]:
    """把 Tk geometry 字符串转换为 QRect 或简单坐标"""
    geom = tk_win.geometry()
    try:
        size_pos = geom.split("+")
        w_h = size_pos[0].split("x")
        return int(size_pos[1]), int(size_pos[2]), int(w_h[0]), int(w_h[1])
    except:
        return 0, 0, 0, 0

def is_window_covered_pg(win_pg: Union[tk.Tk, tk.Toplevel], win_main: Union[tk.Tk, tk.Toplevel], cover_ratio: float = 0.4) -> bool:
    """判断窗口是否被另一个窗口覆盖超过一定比例"""
    try:
        x1, y1, w1, h1 = tk_geometry_to_rect(win_pg)
        x2, y2, w2, h2 = tk_geometry_to_rect(win_main)
        
        inter_left = max(x1, x2)
        inter_top = max(y1, y2)
        inter_right = min(x1 + w1, x2 + w2)
        inter_bottom = min(y1 + h1, y2 + h2)
        
        if inter_right > inter_left and inter_bottom > inter_top:
            inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
            pg_area = w1 * h1
            return (inter_area / pg_area) > cover_ratio
    except:
        pass
    return False

def clamp_window_to_screens(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    """保证窗口落在可见显示器范围内，避免越界或消失"""
    global MONITORS
    if not MONITORS:
        init_monitors()
    monitors = MONITORS or [(0, 0, 1920, 1080)]
    
    # 逻辑判断：只要窗口左上角在任意屏幕内，就根据该屏幕 clamp
    for left, top, right, bottom in monitors:
        if left <= x < right and top <= y < bottom:
            x = max(left, min(x, right - w))
            y = max(top, min(y, bottom - h))
            return x, y
            
    # 如果左上角不在任何屏幕，寻找最近屏幕或默认回主屏
    left, top, right, bottom = monitors[0]
    return left + 100, top + 100

def get_centered_window_position_mainWin(parent: Union[tk.Tk, tk.Toplevel], win_width: int, win_height: int, x_root: Optional[int] = None, y_root: Optional[int] = None, parent_win: Optional[Union[tk.Tk, tk.Toplevel]] = None) -> Tuple[int, int]:
    """计算相对于父窗口居中的位置"""
    if x_root is None:
        if parent_win:
            x_root, y_root = parent_win.winfo_rootx(), parent_win.winfo_rooty()
            pw, ph = parent_win.winfo_width(), parent_win.winfo_height()
        else:
            x_root, y_root = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        
        x = x_root + (pw - win_width) // 2
        y = y_root + (ph - win_height) // 2
    else:
        x, y = x_root, y_root
        
    return clamp_window_to_screens(x, y, win_width, win_height)

# def askstring_at_parent_single(parent: Union[tk.Tk, tk.Toplevel], title: str, prompt: str, initialvalue: str = "") -> Optional[str]:
#     """在父窗口位置弹出的自定义输入框"""
#     result = {"value": None}
#     dlg = tk.Toplevel(parent)
#     dlg.title(title)
    
#     lbl = tk.Label(dlg, text=prompt)
#     lbl.pack(pady=5, padx=10)
    
#     entry = tk.Entry(dlg, width=40)
#     entry.pack(pady=5, padx=10)
#     entry.insert(0, initialvalue)
#     entry.select_range(0, tk.END)
#     entry.focus_set()

#     def on_ok(event=None):
#         result["value"] = entry.get()
#         dlg.destroy()

#     def on_cancel(event=None):
#         dlg.destroy()

#     btn_frame = tk.Frame(dlg)
#     btn_frame.pack(pady=10)
#     tk.Button(btn_frame, text="确定", command=on_ok, width=10).pack(side="left", padx=5)
#     tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side="left", padx=5)
    
#     dlg.bind("<Return>", on_ok)
#     dlg.bind("<Escape>", on_cancel)
    
#     # 居中
#     dlg.update_idletasks()
#     w, h = dlg.winfo_width(), dlg.winfo_height()
#     x, y = get_centered_window_position_mainWin(parent, w, h)
#     dlg.geometry(f"+{x}+{y}")
    
#     dlg.grab_set()
#     parent.wait_window(dlg)
#     return result["value"]

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

# def askstring_at_parent_single(parent, title, prompt, initialvalue=""):
def askstring_at_parent_single(parent: Union[tk.Tk, tk.Toplevel], title: str, prompt: str, initialvalue: str = "") -> Optional[str]:
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

def rearrange_monitors_per_screen(align: str = "left", sort_by: str = "id", layout: str = "horizontal", monitor_list: Optional[dict] = None, win_var: Optional[tk.BooleanVar] = None) -> None:
    """
    多屏幕窗口重排（自动换列/换行 + 左右对齐 + 屏幕内排序）
    
    align: "left" 或 "right" 控制对齐方向
    sort_by: "id" 或 "title" 窗口排序依据
    layout: "vertical" -> 竖排 (上下叠加，满高换列)
            "horizontal" -> 横排 (左右并排，满宽换行)
    """
    global MONITORS
    if not MONITORS:
        init_monitors()

    if monitor_list is None:
        return

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

        margin_x = 10   
        margin_y = 5    

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
                win_state = win_var.get() if win_var else False
                if layout == "vertical" or win_state:
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
                        
                        max_row_height = h
                    else:
                        max_row_height = max(max_row_height, h)

                    win.geometry(f"{w}x{h}+{current_x}+{current_y}")
                    if align == "left":
                        current_x += w + margin_x
                    else:
                        current_x -= (w + margin_x)
            except Exception as e:
                logger.error(f"Rearrange error: {e}")

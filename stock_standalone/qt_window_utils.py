# -*- coding: utf-8 -*-
"""
Qt Window Utilities for cross-process window management on Windows.
Provides tiling, side-by-side placement, and window discovery.
"""

import os
import sys
import time
import ctypes
from typing import List, Tuple, Optional, Dict

try:
    import win32gui
    import win32con
    import win32api
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger("WinManager")

# Window titles/partial strings to recognize as part of the app
APP_WINDOW_TITLES = [
    "PyQuant",
    "Sector Bidding",
    "SBC Pattern",
    "StandaloneKlineChart",
    "Stock Chart",
    "MonitorTK",
    "监控",           # Generic monitoring title
    "Replay",         # Replay windows
    "Visualizer",
    "Bidding"
]

SBC_PREFIX = "SBC Pattern - "

def get_window_rect_dwm(hwnd):
    """Get accurate window bounds including DWM shadows/offsets."""
    if not HAS_WIN32: return None
    try:
        from ctypes.wintypes import RECT, HWND, DWORD
        f = ctypes.windll.dwmapi.DwmGetWindowAttribute
        rect = RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        f(HWND(hwnd), DWORD(DWMWA_EXTENDED_FRAME_BOUNDS), ctypes.byref(rect), ctypes.sizeof(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return win32gui.GetWindowRect(hwnd)

def find_app_hwnds() -> List[Dict]:
    """Find all open windows belonging to the PyQuant ecosystem."""
    if not HAS_WIN32: return []
    
    found_windows = []
    
    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        
        title = win32gui.GetWindowText(hwnd)
        if not title: return

        # Debug: check all visible windows if needed
        # logger.debug(f"Checking window: {title}")

        if any(pt.lower() in title.lower() for pt in APP_WINDOW_TITLES):
            rect = get_window_rect_dwm(hwnd)
            if rect:
                found_windows.append({
                    'hwnd': hwnd,
                    'title': title,
                    'rect': rect,
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                })
                logger.debug(f"Found app window: {title} (HWND: {hwnd})")

    win32gui.EnumWindows(enum_callback, None)
    return found_windows

def tile_all_windows(monitor_index: int = 0):
    """
    Standard tiling: resizes ALL app windows to fit a grid.
    Refined: Now defaults to rearrange_sbc_windows if only SBC windows are target.
    """
    if not HAS_WIN32: return
    
    hwnds_info = find_app_hwnds()
    # If we have SBC windows, prioritize the specialized layout
    sbc_windows = [w for w in hwnds_info if w['title'].startswith(SBC_PREFIX)]
    if sbc_windows:
        rearrange_sbc_windows(monitor_index)
        # If there are OTHER windows, we could tile them too, but typically 
        # the user just wants the active data windows arranged.
        return

    if not hwnds_info:
        logger.info("No app windows found to tile.")
        return

    # ... rest of original generic tiling logic ...
    wa_left, wa_top, wa_right, wa_bottom, wa_w, wa_h = get_monitor_work_area(monitor_index)
    n = len(hwnds_info)
    cols = int(n**0.5) or 1
    rows = (n + cols - 1) // cols
    cell_w, cell_h = wa_w // cols, wa_h // rows

    for i, info in enumerate(hwnds_info):
        row, col = i // cols, i % cols
        x, y = wa_left + col * cell_w, wa_top + row * cell_h
        win32gui.MoveWindow(info['hwnd'], x, y, cell_w, cell_h, True)
    logger.info(f"Tiled {n} windows in {rows}x{cols} grid.")

def get_monitor_work_area(monitor_index: int = 0):
    try:
        monitors = win32api.EnumDisplayMonitors()
        m_idx = min(monitor_index, len(monitors)-1)
        m_info = win32api.GetMonitorInfo(monitors[m_idx][0])
        wa = m_info['Work'] # (left, top, right, bottom)
        return wa[0], wa[1], wa[2], wa[3], wa[2]-wa[0], wa[3]-wa[1]
    except:
        return 0, 0, 1920, 1080, 1920, 1080

def rearrange_sbc_windows(monitor_index: int = 0):
    """
    Specialized rearrangement for SBC Pattern windows:
    1. Filter ONLY "SBC Pattern - " windows.
    2. KEEP original window sizes.
    3. Tile them side-by-side, wrapping to next row if they exceed screen width.
    """
    if not HAS_WIN32: return
    
    all_windows = find_app_hwnds()
    sbc_windows = [w for w in all_windows if w['title'].startswith(SBC_PREFIX)]
    
    if not sbc_windows:
        logger.info("No SBC Pattern windows found to rearrange.")
        # Fallback to general tiling if no SBC windows found but others exist
        return

    # Use current monitor or monitor of the first SBC window
    try:
        monitor = win32api.MonitorFromWindow(sbc_windows[0]['hwnd'], win32con.MONITOR_DEFAULTTONEAREST)
        m_info = win32api.GetMonitorInfo(monitor)
        wa = m_info['Work']
    except:
        wa_left, wa_top, wa_right, wa_bottom, wa_w, wa_h = get_monitor_work_area(monitor_index)
        wa = (wa_left, wa_top, wa_right, wa_bottom)

    wa_l, wa_t, wa_r, wa_b = wa
    curr_x, curr_y = wa_l, wa_t
    max_row_h = 0
    padding = 2

    for info in sbc_windows:
        w, h = info['width'], info['height']
        
        # Wrap to next row if it exceeds work area width
        if curr_x + w > wa_r and curr_x > wa_l:
            curr_x = wa_l
            curr_y += max_row_h
            max_row_h = 0
            
        # Stop if we exceed work area height
        if curr_y + h > wa_b:
            logger.warning(f"Window {info['title']} exceeds screen height, stopping placement.")
            break
            
        # [CRITICAL] Move window but KEEP size
        win32gui.MoveWindow(info['hwnd'], curr_x, curr_y, w, h, True)
        
        # Update cursor and row tracking
        curr_x += w + padding
        max_row_h = max(max_row_h, h + padding)

    logger.info(f"Rearranged {len(sbc_windows)} SBC windows without resizing.")

def place_next_to(hwnd_child: int, parent_title_part: str = "Sector Bidding Panel"):
    """Place a window immediately to the right of a 'parent' window."""
    if not HAS_WIN32: return
    
    hwnds_info = find_app_hwnds()
    parent_info = None
    for info in hwnds_info:
        if parent_title_part.lower() in info['title'].lower() and info['hwnd'] != hwnd_child:
            parent_info = info
            break
            
    if not parent_info:
        return

    p_left, p_top, p_right, p_bottom = parent_info['rect']
    
    # Get child current size
    rect_c = get_window_rect_dwm(hwnd_child)
    if not rect_c: return
    c_w = rect_c[2] - rect_c[0]
    c_h = rect_c[3] - rect_c[1]

    # Target: To the right of parent
    new_x = p_right + 5
    new_y = p_top
    
    # Check if it fits on screen
    try:
        monitor = win32api.MonitorFromWindow(parent_info['hwnd'], win32con.MONITOR_DEFAULTTONEAREST)
        m_info = win32api.GetMonitorInfo(monitor)
        wa = m_info['Work']
        
        if new_x + c_w > wa[2]:
            # Try placing below
            new_x = p_left
            new_y = p_bottom + 5
            
        if new_y + c_h > wa[3]:
            # Fallback to overlap but offset
            new_x = p_left + 30
            new_y = p_top + 30
    except:
        pass

    win32gui.MoveWindow(hwnd_child, new_x, new_y, c_w, c_h, True)
    logger.debug(f"Placed window {hwnd_child} next to {parent_info['title']}")

if __name__ == "__main__":
    # Test tiling
    time.sleep(1)
    tile_all_windows()

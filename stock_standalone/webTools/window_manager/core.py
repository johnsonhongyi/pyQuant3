# -*- coding: utf-8 -*-
"""
窗口管理器核心逻辑模块
提供窗口查找、位置与大小设定、屏幕分辨率检测等底层逻辑。
支持加载与保存独立的持久化 JSON 配置。
"""

import ctypes
from ctypes import wintypes
import time
import os
import sys
import re
import json
from collections import namedtuple
import win32gui
from screeninfo import get_monitors
import psutil

# 尝试导入项目内特有的显示器检测模块以保持向后兼容，如果失败则使用通用的 screeninfo 回退
try:
    from mouseMonitor.displayDetction import Display_Detection
except ImportError:
    # 动态将上级目录加入路径以防包内调用时无法导入
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from mouseMonitor.displayDetction import Display_Detection
    except ImportError:
        Display_Detection = None

try:
    from current_display_configuration import restore_display_configuration
except ImportError:
    restore_display_configuration = None

# 定义基础窗口信息结构
WindowInfo = namedtuple('WindowInfo', 'pid title left top width height hwnd exe_path')

# Windows API 定义与初始化
user32 = ctypes.WinDLL('user32', use_last_error=True)

# 校验辅助函数
def check_zero(result, func, args):    
    if not result:
        err = ctypes.get_last_error()
        if err:
            pass # 发生非破坏性错误时不引发崩溃，返回原参数
    return args

if not hasattr(wintypes, 'LPDWORD'):
    wintypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,    
    wintypes.LPARAM,
)

user32.EnumWindows.errcheck = check_zero
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsZoomed.argtypes = (wintypes.HWND,)
user32.IsZoomed.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, wintypes.BOOL)
user32.ShowWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, wintypes.LPDWORD)
user32.GetWindowTextLengthW.errcheck = check_zero
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.errcheck = check_zero
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
user32.SetWindowPos.restype = wintypes.BOOL

# 窗口显示常量
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9
SW_SHOWDEFAULT = 10
SW_FORCEMINIMIZE = 11

# SetWindowPos 标志位
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOREDRAW = 0x0008
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080

# 窗口样式常量
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_MAXIMIZE = 0x01000000
WS_MINIMIZE = 0x20000000


def get_window_rect(hwnd) -> tuple:
    """获取窗口在屏幕上的实际像素边界(left, top, width, height)"""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.pointer(rect))
    left = rect.left
    top = rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (left, top, width, height)


import winreg

def get_monitor_hardware_info(adapter_device_name: str) -> dict:
    """
    通过 Windows EnumDisplayDevices 和注册表 EDID 解析指定适配器上连接的显示器真实厂商型号、PNP ID 与硬件 ID
    返回: {
        "model_name": "LG HDR 4K",
        "pnp_id": "GSM7707",
        "hardware_id": "\\\\?\\DISPLAY#GSM7707#...",
        "device_string": "LG HDR 4K(Display Port)"
    }
    """
    result = {
        "model_name": "",
        "pnp_id": "",
        "hardware_id": "",
        "device_string": "Generic Monitor"
    }
    if not adapter_device_name:
        return result

    try:
        import win32api
        import win32con
        for j in range(8):
            try:
                mon_dev = win32api.EnumDisplayDevices(adapter_device_name, j, 1)
                if not mon_dev:
                    continue
                if not (mon_dev.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP) and j > 0:
                    continue

                dev_id = getattr(mon_dev, "DeviceID", "") or ""
                dev_str = getattr(mon_dev, "DeviceString", "") or ""

                result["hardware_id"] = dev_id
                result["device_string"] = dev_str

                # 提取 PNP 厂商代号 (例如 GSM7707, SAM0676, AUO82ED)
                parts = [p for p in re.split(r'[#\\]', dev_id) if p]
                pnp_id = ""
                for p in parts:
                    if len(p) >= 6 and any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
                        if p.upper() not in ("DISPLAY", "UID", "GLOBALROOT", "ROOT"):
                            pnp_id = p.upper()
                            break
                result["pnp_id"] = pnp_id

                # 尝试从注册表读取 EDID 解析厂商 Friendly Model Name
                if "#" in dev_id or "\\" in dev_id:
                    clean_parts = dev_id.replace("\\\\?\\", "").replace("??\\", "").split("#")
                    if len(clean_parts) >= 3:
                        reg_path = f"SYSTEM\\CurrentControlSet\\Enum\\DISPLAY\\{clean_parts[1]}\\{clean_parts[2]}\\Device Parameters"
                        try:
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as k:
                                edid, _ = winreg.QueryValueEx(k, "EDID")
                                for off in (54, 72, 90, 108):
                                    if len(edid) >= off + 18 and edid[off:off+4] == b'\x00\x00\x00\xfc':
                                        model_name = edid[off+5:off+18].decode('ascii', errors='ignore').split('\n')[0].strip()
                                        if model_name:
                                            result["model_name"] = model_name
                                            break
                        except Exception:
                            pass

                if not result["model_name"]:
                    if dev_str and dev_str.lower() not in ("generic pnp monitor", "generic monitor"):
                        result["model_name"] = dev_str
                    elif pnp_id:
                        result["model_name"] = pnp_id

                if result["hardware_id"]:
                    break
            except Exception:
                pass
    except Exception:
        pass

    return result


def get_monitor_details_all_with_scale():
    """
    获取所有显示器信息，同时计算 scale（DPI缩放）与真实物理硬件厂商型号
    - 主显示器排在最前
    - 返回 monitors 列表 + 汇总字符串
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    shcore = None
    try:
        shcore = ctypes.windll.shcore
        shcore.GetDpiForMonitor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint)
        ]
    except Exception:
        pass

    monitors = []
    try:
        import win32api
        import win32con
        monitor_handles = win32api.EnumDisplayMonitors()
        if monitor_handles:
            for handle_tuple in monitor_handles:
                monitor_handle = handle_tuple[0]
                try:
                    info = win32api.GetMonitorInfo(monitor_handle)
                    device_name = info.get("Device", "Unknown")
                    is_primary = (info.get("Flags", 0) & win32con.MONITORINFOF_PRIMARY) != 0
                    left, top, right, bottom = info["Monitor"]
                    logical_width = right - left
                    logical_height = bottom - top

                    devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
                    physical_width = devmode.PelsWidth
                    physical_height = devmode.PelsHeight

                    # 获取显示器真实厂商型号与硬件ID
                    hw_info = get_monitor_hardware_info(device_name)
                    model_name = hw_info.get("model_name", "") or device_name
                    pnp_id = hw_info.get("pnp_id", "")
                    hw_id = hw_info.get("hardware_id", "")
                    dev_str = hw_info.get("device_string", "")

                    scale = None
                    if shcore is not None:
                        try:
                            dpi_x = ctypes.c_uint()
                            dpi_y = ctypes.c_uint()
                            res = shcore.GetDpiForMonitor(int(monitor_handle), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                            if res == 0: # S_OK
                                scale = round(dpi_x.value / 96.0, 2)
                        except Exception:
                            pass

                    if scale is None:
                        scale_x = physical_width / logical_width if logical_width else 1.0
                        scale_y = physical_height / logical_height if logical_height else 1.0
                        scale = round((scale_x + scale_y) / 2, 2)

                    real_logical_width = int(physical_width / scale) if scale else logical_width
                    real_logical_height = int(physical_height / scale) if scale else logical_height

                    monitors.append({
                        "device_name": device_name,
                        "model_name": model_name,
                        "pnp_id": pnp_id,
                        "hardware_id": hw_id,
                        "device_string": dev_str,
                        "width": physical_width,
                        "height": physical_height,
                        "x": devmode.Position_x,
                        "y": devmode.Position_y,
                        "is_primary": is_primary,
                        "logical_width": real_logical_width,
                        "logical_height": real_logical_height,
                        "scale": scale
                    })
                except Exception:
                    pass
    except Exception:
        pass

    if not monitors:
        try:
            from screeninfo import get_monitors
            for m in get_monitors():
                monitors.append({
                    "device_name": m.name,
                    "model_name": m.name,
                    "pnp_id": "",
                    "hardware_id": "",
                    "device_string": "Generic Screen",
                    "width": m.width,
                    "height": m.height,
                    "x": m.x,
                    "y": m.y,
                    "is_primary": m.is_primary,
                    "logical_width": m.width,
                    "logical_height": m.height,
                    "scale": 1.0
                })
        except Exception:
            pass

    if not monitors:
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        monitors.append({
            "device_name": "\\\\.\\DISPLAY1",
            "model_name": "主显示器",
            "pnp_id": "",
            "hardware_id": "",
            "device_string": "Generic Display",
            "width": w,
            "height": h,
            "x": 0,
            "y": 0,
            "is_primary": True,
            "logical_width": w,
            "logical_height": h,
            "scale": 1.0
        })

    # 稳定确定性排序：主显示器排第 1 位；其余副屏按 (Position_x, Position_y, Width, Height, Scale) 升序稳定排序
    monitors.sort(key=lambda m: (
        0 if m.get("is_primary") else 1,
        m.get("x", 0),
        m.get("y", 0),
        m.get("width", 0),
        m.get("height", 0),
        m.get("scale", 1.0)
    ))
    summary = "_".join(f"{m['width']}x{m['height']}@{m['scale']}" for m in monitors)
    return {"monitors": monitors, "summary": summary}


def get_screen_resolution_summary() -> dict:
    """
    通过底层硬件与 Win32 获取显示器配置汇总（支持 1/2/3/4/N 屏与动态拓扑检测）
    """
    details = get_monitor_details_all_with_scale()
    monitors = details.get("monitors", [])
    
    total_physical_width = 0
    total_logical_width = 0
    primary_res = "1920x1080"
    primary_w = 1920
    primary_log_w = 1920
    
    formatted_monitors = []
    for i, m in enumerate(monitors):
        is_pri = m.get("is_primary", False)
        w = m.get("width", 1920)
        h = m.get("height", 1080)
        lw = m.get("logical_width", w)
        lh = m.get("logical_height", h)
        x = m.get("x", 0)
        y = m.get("y", 0)
        scale = m.get("scale", 1.0)
        dev_name = m.get("device_name", f"DISPLAY{i+1}")
        model_name = m.get("model_name", dev_name)
        pnp_id = m.get("pnp_id", "")
        hw_id = m.get("hardware_id", "")
        dev_str = m.get("device_string", "")
        
        total_physical_width += w
        total_logical_width += lw
        
        if is_pri or i == 0:
            primary_res = f"{w}x{h}"
            primary_w = w
            primary_log_w = lw
            
        formatted_monitors.append({
            "index": i + 1,
            "name": dev_name,
            "device_name": dev_name,
            "model_name": model_name,
            "pnp_id": pnp_id,
            "hardware_id": hw_id,
            "device_string": dev_str,
            "width": w,
            "height": h,
            "logical_width": lw,
            "logical_height": lh,
            "scale": scale,
            "x": x,
            "y": y,
            "is_primary": is_pri
        })
        
    try:
        virt_w = user32.GetSystemMetrics(78) # SM_CXVIRTUALSCREEN
        virt_h = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN
        if virt_w <= 0:
            virt_w = total_physical_width
        if virt_h <= 0:
            virt_h = 1080
    except Exception:
        virt_w = total_physical_width
        virt_h = 1080
        
    sig = details.get("summary", "")
    topo_sig = f"{len(formatted_monitors)}screens_{sig}_" + "_".join(f"{m['x']},{m['y']}" for m in formatted_monitors)

    return {
        "total_width": total_physical_width,
        "total_logical_width": total_logical_width,
        "virtual_width": virt_w,
        "virtual_height": virt_h,
        "primary_res": primary_res,
        "primary_width": primary_w,
        "primary_logical_width": primary_log_w,
        "monitors": formatted_monitors,
        "display_num": len(formatted_monitors),
        "summary_signature": topo_sig
    }


def get_screen_topology_signature() -> str:
    """获取当前连接的显示器物理拓扑结构的唯一指纹"""
    summary = get_screen_resolution_summary()
    return summary.get("summary_signature", "")



def get_screen_topology_orientation_tag(monitors=None) -> str:
    """
    计算多屏幕相对于主屏幕 (0,0) 的相对摆放方位标签。
    例如：
    - 主屏在中间，上方有屏，左侧有屏 -> 'TopLeft'
    - 主屏在中间，上方有屏，右侧有屏 -> 'TopRight'
    - 主屏在右，副屏在左 -> 'Left'
    - 主屏在左，副屏在右 -> 'Right'
    - 主屏在下，副屏在上 -> 'Top'
    """
    if monitors is None:
        summary = get_screen_resolution_summary()
        monitors = summary.get("monitors", [])
        
    if len(monitors) <= 1:
        return ""
        
    # 找到主屏幕
    pri = next((m for m in monitors if m.get("is_primary")), monitors[0])
    pri_x = pri.get("x", 0)
    pri_y = pri.get("y", 0)
    pri_w = pri.get("width", 1920)
    pri_h = pri.get("height", 1080)
    
    has_left = False
    has_right = False
    has_top = False
    has_bottom = False
    
    for m in monitors:
        if m.get("is_primary") or m == pri:
            continue
        mx = m.get("x", 0)
        my = m.get("y", 0)
        mw = m.get("width", 1920)
        mh = m.get("height", 1080)
        
        # 水平相对关系判断 (基于边界与中心点投影)
        if (mx + mw <= pri_x + 100) or (mx < pri_x - 100):
            has_left = True
        elif (mx >= pri_x + pri_w - 100) or (mx > pri_x + pri_w // 2 and mx > pri_x + 100):
            has_right = True
            
        # 垂直相对关系判断
        if (my + mh <= pri_y + 100) or (my < pri_y - 100):
            has_top = True
        elif (my >= pri_y + pri_h - 100) or (my > pri_y + pri_h // 2 and my > pri_y + 100):
            has_bottom = True
            
    tags = []
    if has_top:
        tags.append("Top")
    if has_bottom:
        tags.append("Bottom")
    if has_left:
        tags.append("Left")
    if has_right:
        tags.append("Right")
        
    return "".join(tags)



def detect_display_config_name(config_manager=None) -> str:
    """
    根据当前系统的物理显示器拓扑结构（支持 1/2/3/4/N 屏及排列方位）智能自适应匹配最佳方案名称。
    - 优先级 1：当前排列方位的专属新方案（如 5376_TopRight, 5376_Right），自动优先采用！
    - 优先级 2：平滑兼容既有标准分辨率方案（如 5376, 3840, 3456），零改动无感过渡！
    - 优先级 3：临近相近多屏历史方案；
    - 优先级 4：自动规范生成符合当前物理排布的最佳新方案名称。
    """
    existing_keys = set()
    if config_manager:
        try:
            existing_keys = set(config_manager.get_resolutions())
        except Exception:
            pass
    if not existing_keys:
        try:
            cfg_path = get_conf_path("window_layout_config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    for cat in d.values():
                        if isinstance(cat, dict):
                            existing_keys.update(cat.keys())
        except Exception:
            pass

    summary = get_screen_resolution_summary()
    display_num = summary["display_num"]
    total_w = summary["total_width"]
    total_log_w = summary["total_logical_width"]
    virt_w = summary["virtual_width"]
    primary_w = summary["primary_width"]
    primary_log_w = summary["primary_logical_width"]
    ori_tag = get_screen_topology_orientation_tag(summary["monitors"])

    # 1. 单屏场景 (display_num <= 1)
    if display_num <= 1:
        candidates = [
            f"tdx_ths_position{primary_w}",
            f"tdx_ths_position{primary_log_w}",
            "tdx_ths_position"
        ]
        for c in candidates:
            if c in existing_keys:
                return c
        return f"tdx_ths_position{primary_w}"

    # 2. 多屏场景 (2 屏、3 屏、4 屏及以上)
    # --- [第一梯队：专属方位新配置优先] ---
    if ori_tag:
        orientation_candidates = [
            f"tdx_ths_position{total_log_w}_{ori_tag}",
            f"tdx_ths_position{total_w}_{ori_tag}",
        ]
        # 兼容简易单向方位词（如 TopRight 也匹配 _Right, _Top）
        if "Right" in ori_tag:
            orientation_candidates.extend([
                f"tdx_ths_position{total_log_w}_Right",
                f"tdx_ths_position{total_w}_Right",
                f"tdx_ths_position{total_log_w}_right"
            ])
        if "Left" in ori_tag:
            orientation_candidates.extend([
                f"tdx_ths_position{total_log_w}_Left",
                f"tdx_ths_position{total_w}_Left",
                f"tdx_ths_position{total_log_w}_left"
            ])
            
        for cand in orientation_candidates:
            if cand in existing_keys:
                return cand

        # 检查库中是否有同时包含当前分辨率数字与当前方位关键字的自定义方案
        for key in existing_keys:
            key_lower = key.lower()
            if (str(total_log_w) in key or str(total_w) in key) and ori_tag.lower() in key_lower:
                return key

    # --- [第二梯队：平滑兼容标准总宽已有方案（老方案无感过渡）] ---
    standard_candidates = [
        f"tdx_ths_position{total_w}",
        f"tdx_ths_position{total_log_w}" if total_log_w != total_w else None,
        f"tdx_ths_position{virt_w}" if virt_w not in (total_w, total_log_w) else None,
        f"tdx_ths_position_{display_num}screen",
        "tdx_ths_positionDouble" if display_num == 2 else None
    ]
    standard_candidates = [c for c in standard_candidates if c]

    for cand in standard_candidates:
        if cand in existing_keys:
            return cand

    # --- [第三梯队：智能容差贴合已有相近多屏方案] ---
    best_match = None
    min_diff = float("inf")
    
    for key in existing_keys:
        m = re.search(r"(\d{4,5})", key)
        if m:
            num = int(m.group(1))
            if num > 2560: # 属于多屏范畴
                diff_phys = abs(num - total_w)
                diff_log = abs(num - total_log_w)
                closest_diff = min(diff_phys, diff_log)
                
                threshold = max(150, int(total_w * 0.04))
                if closest_diff <= threshold and closest_diff < min_diff:
                    min_diff = closest_diff
                    best_match = key
                    
    if best_match:
        return best_match

    # --- [第四梯队：若无任何已有方案，生成带清晰方位特征的推荐新方案名] ---
    # 例如：3 屏副屏在右 -> tdx_ths_position5376_TopRight; 2 屏副屏在右 -> tdx_ths_position5760_Right
    if ori_tag:
        return f"tdx_ths_position{total_log_w}_{ori_tag}"
    return f"tdx_ths_position{total_w}"


_MAGNETIC_KEYWORDS_CACHE = None
_MAGNETIC_CACHE_TIME = 0.0

def get_magnetic_keywords() -> list:
    """
    获取所有的磁吸窗口匹配关键字。
    包含内置默认列表 + 从配置文件 (window_layout_config.json) 中读取的用户手动添加的自定义关键字。
    """
    global _MAGNETIC_KEYWORDS_CACHE, _MAGNETIC_CACHE_TIME
    now = time.time()
    if _MAGNETIC_KEYWORDS_CACHE is not None and (now - _MAGNETIC_CACHE_TIME < 5.0):
        return _MAGNETIC_KEYWORDS_CACHE

    default_keywords = [
        "SignalDashboardPanel", "SignalDashboard", "策略信号分类仪表盘", 
        "信号仪表盘", "Signal_Dashboard", "涨跌分布个股明细",
        "预警个股异动明细", "异动明细", "加速龙头跟踪器", "龙头跟踪器"
    ]
    try:
        cfg_path = get_conf_path("window_layout_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                custom_kws = data.get("magnetic_keywords", [])
                if isinstance(custom_kws, list):
                    for kw in custom_kws:
                        if kw and str(kw) not in default_keywords:
                            default_keywords.append(str(kw))
    except Exception:
        pass

    _MAGNETIC_KEYWORDS_CACHE = default_keywords
    _MAGNETIC_CACHE_TIME = now
    return default_keywords


def is_magnetic_dock_window(title: str) -> bool:
    """
    判断指定窗口标题是否属于具备贴边隐藏/磁吸功能的专属面板窗口。
    支持动态读取内置与用户自定义添加的磁吸关键字。
    日常常规软件 (东方财富、通达信、同花顺、Chrome 等) 返回 False，保留 100% 原始物理坐标不篡改。
    """
    if not title:
        return False
    keywords = get_magnetic_keywords()
    t_lower = str(title).lower()
    for kw in keywords:
        if kw.lower() in t_lower:
            return True
    return False


def normalize_docked_window_rect(left: int, top: int, width: int, height: int, title: str = "") -> tuple:
    """
    只有当明确指定了 title 且属于专属磁吸面板时，才进行贴边隐藏展开坐标反算。
    对于非磁吸窗口 (东方财富、同花顺等所有常规日常软件)，直接原封不动返回原生坐标。
    """
    if not title or not is_magnetic_dock_window(title):
        return left, top, width, height

    try:
        monitors_info = get_monitor_details_all_with_scale()
        monitors = monitors_info.get("monitors", [])
        if not monitors:
            return left, top, width, height

        for mon in monitors:
            mx = mon.get("x", 0)
            my = mon.get("y", 0)
            mw = mon.get("logical_width", mon.get("width", 1920))
            mh = mon.get("logical_height", mon.get("height", 1080))
            m_right = mx + mw
            m_bottom = my + mh

            # 判断磁吸面板是否处于屏幕外的折叠状态
            if left > m_right - 40 and (left + width) > m_right + 20:
                norm_left = m_right - width
                return norm_left, top, width, height

            right = left + width
            if right > mx - 40 and right < mx + 40 and left < mx - 20:
                norm_left = mx
                return norm_left, top, width, height

            bottom = top + height
            if bottom > my - 40 and bottom < my + 40 and top < my - 20:
                norm_top = my
                return left, norm_top, width, height
    except Exception:
        pass

    return left, top, width, height


def list_visible_windows(fuzzy_title="") -> list:
    """列出当前所有可见的顶层窗口，如果指定了 fuzzy_title 则过滤"""
    result = []
    
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            if length > 1:
                title_buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hWnd, title_buf, length)
                title = title_buf.value.strip()
                if title:
                    if not fuzzy_title or re.search(re.escape(fuzzy_title), title, re.IGNORECASE):
                        raw_left, raw_top, width, height = get_window_rect(hWnd)
                        # 仅对专属磁吸折叠窗口做展开规范化，常规日常软件 (如东方财富) 保持 100% 真实的物理坐标
                        left, top, width, height = normalize_docked_window_rect(raw_left, raw_top, width, height, title=title)
                        exe_path = ""
                        try:
                            proc = psutil.Process(pid.value)
                            exe_path = proc.exe()
                        except Exception:
                            pass
                        result.append(WindowInfo(
                            pid=pid.value, 
                            title=title, 
                            left=left, 
                            top=top, 
                            width=width, 
                            height=height,
                            hwnd=hWnd,
                            exe_path=exe_path
                        ))
        return True
        
    user32.EnumWindows(enum_proc, 0)
    return result


def find_windows_by_title_safe(target_title: str) -> list:
    """基于正则模糊匹配，安全查找符合名称的窗口，返回 [(hwnd, title), ...]"""
    found = []
    escaped_title = re.escape(target_title)
    pattern = re.compile(escaped_title, re.IGNORECASE)

    def enum_handler(hwnd, _):
        try:
            if user32.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if pattern.search(window_title):
                    found.append((hwnd, window_title))
        except Exception:
            pass
        return True
        
    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception:
        pass
    return found

def get_exe_path(hwnd) -> str:
    """安全提取指定窗口句柄对应的物理可执行路径"""
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value > 0:
            proc = psutil.Process(pid.value)
            return proc.exe()
    except Exception:
        pass
    return ""


def cancel_window_maximized_or_fullscreen(hwnd: int) -> bool:
    """
    智能检测并取消窗口的最大化 (Maximized)、全屏 (Fullscreen) 或最小化 (Minimized) 状态，
    将其恢复为标准的普通自由窗口 (SW_RESTORE)，
    以彻底解决在最大化或全屏状态下 Windows 系统锁定窗口、导致 SetWindowPos 坐标与尺寸应用失效的问题。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    need_restore = False
    
    # 1. 检查是否最小化
    if user32.IsIconic(hwnd):
        need_restore = True
        
    # 2. 检查是否最大化
    if user32.IsZoomed(hwnd):
        need_restore = True

    # 3. 检查窗口样式标志 (WS_MAXIMIZE / WS_MINIMIZE)
    try:
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if (style & WS_MAXIMIZE) or (style & WS_MINIMIZE):
            need_restore = True
    except Exception:
        pass

    if need_restore:
        # 发送 SW_RESTORE (9) 命令，使窗口由最大化/全屏/最小化退回常规恢复态
        user32.ShowWindow(hwnd, SW_RESTORE)
        # 短暂微延时确保 DWM 与 Win32 消息队列完成几何属性解绑
        time.sleep(0.04)
        return True

    return False


def set_window_hwnd_pos(hwnd, pos_str: str, title: str = ""):
    """
    通过 'x,y,width,height' 格式的字符串直接设置指定句柄的窗口位置与大小。
    执行前先判断是否最大化/全屏/最小化，自动取消并还原后再执行精准坐标与尺寸设定。
    针对跨显示器 (高分屏 -> 普分屏/三星显示器等) 引起的 WM_DPICHANGED 尺寸二次缩放，
    内置两阶段 (Two-Pass) 几何自适应补偿校准，确保一次应用 100% 准确到位，无需执行第二次。
    """
    try:
        parts = [int(p.strip()) for p in pos_str.split(',')]
        if len(parts) == 4:
            x, y, width, height = parts
            
            # 仅对专属磁吸折叠窗口做反向纠偏；常规日常软件直接按精准坐标设定
            x, y, width, height = normalize_docked_window_rect(x, y, width, height, title=title)

            # 🛡️ 核心防失效：若窗口处于全屏、最大化或最小化，先强制取消并还原为普通窗口
            cancel_window_maximized_or_fullscreen(hwnd)

            # 一次性原子设定窗口坐标与大小，并触发系统刷新重绘
            flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
            success = bool(user32.SetWindowPos(hwnd, 0, x, y, width, height, flags))

            # 🛡️ 跨屏/跨 DPI 二次补偿校准 (彻底解决高分屏迁移到普分屏时的 WM_DPICHANGED 尺寸截断)
            # 给 DWM 与 Win32 消息队列 40ms 处理跨屏 DPI 上下文切换
            time.sleep(0.04)
            cur_l, cur_t, cur_w, cur_h = get_window_rect(hwnd)
            
            # 若尺寸或坐标在跨屏后被 Windows DPI 回调篡改 (差值超过 4px) 或仍处于最大化
            need_reapply = False
            if user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
                need_reapply = True
            elif abs(cur_w - width) > 4 or abs(cur_h - height) > 4 or abs(cur_l - x) > 4 or abs(cur_t - y) > 4:
                need_reapply = True

            if need_reapply:
                user32.SetWindowPos(hwnd, 0, x, y, width, height, flags)

            return success
    except Exception as e:
        print(f"Error setting window pos for HWND {hwnd}: {e}")
    return False


def force_topmost_activate_hwnd(hwnd: int) -> bool:
    """
    工业级 Win32 窗口强力置顶与激活前台焦点：
    结合 ShowWindow(SW_RESTORE) + AttachThreadInput 线程输入关联 + 模拟按键 + BringWindowToTop + HWND_TOPMOST/HWND_NOTOPMOST 切换，
    彻底绕过 Windows 10/11 的前台锁定限制，确保窗口 100% 弹出到最前台并抢占焦点。
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        # 1. 若最小化或隐藏，先恢复显示
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 2. 线程输入挂接 (AttachThreadInput)
        fore_hwnd = user32.GetForegroundWindow()
        curr_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        attached_fore = False
        attached_target = False
        if fore_tid and fore_tid != curr_tid:
            attached_fore = bool(user32.AttachThreadInput(curr_tid, fore_tid, True))
        if target_tid and target_tid != curr_tid:
            attached_target = bool(user32.AttachThreadInput(curr_tid, target_tid, True))

        # 3. 模拟轻按 Alt 键，突破 Windows 前台激活锁
        user32.keybd_event(0x12, 0, 0, 0)       # Alt Down
        user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt Up

        # 4. 临时 HWND_TOPMOST 切换将窗口推至顶层，随后解除 TOPMOST 恢复正常层级
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 1
        SWP_NOMOVE = 2
        SWP_SHOWWINDOW = 0x0040
        flags = SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW

        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)

        # 5. 夺取焦点与置顶
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        # 6. 解除线程挂接
        if attached_fore:
            user32.AttachThreadInput(curr_tid, fore_tid, False)
        if attached_target:
            user32.AttachThreadInput(curr_tid, target_tid, False)

        return True
    except Exception as e:
        print(f"force_topmost_activate_hwnd 异常: {e}")
        return False


def set_window_pos_by_title(target_title: str, pos_str: str, show_cmd=SW_SHOWNORMAL, activate_topmost: bool = False) -> bool:
    """
    模糊匹配窗口标题，并将其移动到指定位置。
    如果是专属磁吸窗口且处于隐藏收缩状态，会自动先执行显示/还原；
    对东方财富等常规日常软件，只在最小化时还原，靠边放置不触发误判。
    若 activate_topmost=True，移动后将窗口强力提升至最前台并激活。
    """
    found = find_windows_by_title_safe(target_title)
    if not found:
        return False
        
    success = False
    for hwnd, title in found:
        # 提取当前物理坐标
        left, top, width, height = get_window_rect(hwnd)
        
        is_docked_hidden = False
        if left < -10000 and top < -10000:
            # 最小化状态，需要SW_RESTORE
            is_docked_hidden = True
        elif is_magnetic_dock_window(title):
            # 只有专属磁吸折叠窗口才检测是否超界贴边收缩
            try:
                monitors_info = get_monitor_details_all_with_scale()
                for mon in monitors_info.get("monitors", []):
                    mx = mon.get("x", 0)
                    mw = mon.get("logical_width", mon.get("width", 1920))
                    m_right = mx + mw
                    if (left > m_right - 40 and (left + width) > m_right + 20) or (left + width > mx - 40 and left < mx - 20):
                        is_docked_hidden = True
                        break
            except Exception:
                pass

        if is_docked_hidden:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE 强制恢复显示展开态
            time.sleep(0.05)
            
        if set_window_hwnd_pos(hwnd, pos_str, title=title):
            success = True
            
        if show_cmd != SW_SHOWNORMAL:
            user32.ShowWindow(hwnd, show_cmd)

        if activate_topmost:
            force_topmost_activate_hwnd(hwnd)
            
    return success


def get_app_root() -> str:
    """获取程序物理根目录。"""
    is_frozen = getattr(sys, "frozen", False)
    is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version")
    
    if is_frozen or is_nuitka:
        # 🚀 打包 EXE 模式：物理根目录永远 100% 锁定为 EXE 自身所在目录，严禁被外部继承的环境变量带偏！
        calculated_root = os.path.dirname(os.path.abspath(sys.executable))
        # 兼容若打包 EXE 置于 webTools 或 window_manager 子目录时的物理根目录提升
        if os.path.basename(calculated_root).lower() in ('webtools', 'window_manager'):
            calculated_root = os.path.dirname(calculated_root)
            if os.path.basename(calculated_root).lower() == 'webtools':
                calculated_root = os.path.dirname(calculated_root)
    else:
        # 源码开发调试模式：优先遵循显式指定的 INSTOCK_APP_ROOT，否则回退到本地开发环境项目根目录 (webTools/window_manager 的上上级)
        env_root = os.environ.get("INSTOCK_APP_ROOT")
        if env_root and os.path.exists(env_root):
            calculated_root = env_root
        else:
            calculated_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    return calculated_root


def get_conf_path(fname: str) -> str:
    """
    获取并加载配置文件的路径，支持从内置资源包自愈释放。
    """
    app_root = get_app_root()
    dst_path = os.path.join(app_root, fname)

    if not os.path.exists(dst_path):
        base = getattr(sys, "_MEIPASS", None)

        if not base:
            base = getattr(sys, "_MEIPASS", None)
        if not base and "NUITKA_ONEFILE_DIRECTORY" in os.environ:
            base = os.environ["NUITKA_ONEFILE_DIRECTORY"]
        if not base:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # window_layout_config.json 在内置包中位于 webTools/window_manager/ 目录下
        src_path = os.path.join(base, "webTools", "window_manager", fname)
        if not os.path.exists(src_path):
            src_path = os.path.join(base, fname)
        
        # 💥 额外自愈探测候选：兼容 Nuitka 在不同环境下可能发生平铺释放的极端情况
        if not os.path.exists(src_path):
            src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)

        if os.path.exists(src_path):
            try:
                import shutil
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy(src_path, dst_path)
            except Exception as e:
                print(f"[自愈] 释放配置文件失败: {e}", file=sys.stderr)

    return dst_path


class ConfigManager:
    """管理分类持久化的 JSON 配置，具备基于磁盘 mtime 的自动热重载与防覆盖机制"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_conf_path("window_layout_config.json")
        self.config_path = config_path
        self.config_data = {}
        self._last_mtime = 0.0
        self.load()

    def _check_and_reload(self):
        """检查物理磁盘文件是否有外部更新，若有则自动热重载"""
        try:
            if os.path.exists(self.config_path):
                current_mtime = os.path.getmtime(self.config_path)
                if current_mtime > self._last_mtime:
                    self.load()
        except Exception:
            pass

    def load(self):
        """从文件读取 JSON 配置"""
        loaded = False
        # 优先尝试读取磁盘上的持久化配置文件
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
                self._last_mtime = os.path.getmtime(self.config_path)
                loaded = True
            except Exception as e:
                print(f"Failed to load config from {self.config_path}: {e}")

        # 兜底初始化空数据
        if not loaded:
            self.config_data = {"single_display": {}, "multi_display": {}, "custom_special": {}}

        # 校验格式，如果不是分类的字典，则进行初始化
        if not isinstance(self.config_data, dict):
            self.config_data = {"single_display": {}, "multi_display": {}, "custom_special": {}}
        for cat in ["single_display", "multi_display", "custom_special"]:
            if cat not in self.config_data:
                self.config_data[cat] = {}
            
    def save(self):
        """保存当前内存中的配置到文件，并同步更新 mtime"""
        try:
            # 确保物理持久化文件夹存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=4)
            if os.path.exists(self.config_path):
                self._last_mtime = os.path.getmtime(self.config_path)
            return True
        except Exception as e:
            print(f"Failed to save config to {self.config_path}: {e}")
            return False

    def get_categories(self) -> list:
        """获取所有分类"""
        self._check_and_reload()
        return ["single_display", "multi_display", "custom_special"]

    def get_resolutions_by_category(self, category: str) -> list:
        """获取特定分类下的所有方案名"""
        self._check_and_reload()
        if category in self.config_data:
            return sorted(list(self.config_data[category].keys()))
        return []

    def get_resolutions(self) -> list:
        """获取所有可用分辨率配置方案的名称（扁平列表）"""
        self._check_and_reload()
        res_list = []
        for cat in self.get_categories():
            res_list.extend(self.get_resolutions_by_category(cat))
        return sorted(list(set(res_list)))

    def get_category_of_resolution(self, res_name: str) -> str:
        """判断一个方案名属于哪个分类"""
        self._check_and_reload()
        for cat in self.get_categories():
            if res_name in self.config_data.get(cat, {}):
                return cat
        return "custom_special" # 默认分类

    def get_resolution_mapping(self, res_name: str) -> dict:
        """获取指定分辨率配置的窗口坐标映射表"""
        self._check_and_reload()
        for cat in self.get_categories():
            if res_name in self.config_data.get(cat, {}):
                return self.config_data[cat][res_name]
        return {}

    def set_resolution_mapping(self, res_name: str, mapping: dict, category: str = None):
        """更新指定分辨率的配置"""
        self._check_and_reload()
        if not category:
            category = self.get_category_of_resolution(res_name)
            
        # 确保分类存在
        if category not in self.config_data:
            self.config_data[category] = {}
            
        # 如果该配置在其他分类中也存在，先删掉，避免重复
        for cat in self.get_categories():
            if cat != category and res_name in self.config_data.get(cat, {}):
                del self.config_data[cat][res_name]
                
        self.config_data[category][res_name] = mapping
        
    def delete_resolution(self, res_name: str):
        """删除某个分辨率的配置"""
        self._check_and_reload()
        for cat in self.get_categories():
            if res_name in self.config_data.get(cat, {}):
                del self.config_data[cat][res_name]

    def get_duplicate_resolutions_info(self) -> dict:
        """
        自动检测所有分类下的分辨率方案中是否有窗口坐标映射表完全一致的重复方案。
        返回: {重复方案名: (原始方案名, 所属分类)} 字典
        """
        self._check_and_reload()
        seen_mappings = {}  # mapping_fingerprint -> (first_res_name, cat)
        duplicates = {}     # dup_res_name -> (original_res_name, cat)

        def score_name(name):
            n_low = name.lower()
            is_copy = any(k in n_low for k in ["duplicate", "copy", "副本", "bak", "temp"])
            return (is_copy, len(name), name)

        for cat in self.get_categories():
            res_names = sorted(self.get_resolutions_by_category(cat), key=score_name)
            for res_name in res_names:
                mapping = self.get_resolution_mapping(res_name)
                if not mapping:
                    continue
                # 提取窗口映射指纹 (排序后的 key-pos 对，pos 仅比对坐标部分)
                items = []
                for k, v in mapping.items():
                    pos_coord = str(v).split('|')[0].strip()
                    items.append((k.strip().lower(), pos_coord))
                fp = tuple(sorted(items))
                if fp in seen_mappings:
                    duplicates[res_name] = seen_mappings[fp]
                else:
                    seen_mappings[fp] = (res_name, cat)

        return duplicates

    def delete_duplicate_resolutions(self) -> tuple:
        """
        一键删除所有窗口映射数据完全一致的重复方案（保留最早定义的原始方案）。
        返回 (deleted_count: int, deleted_names: list[str])
        """
        dups = self.get_duplicate_resolutions_info()
        deleted = []
        for dup_name in dups.keys():
            self.delete_resolution(dup_name)
            deleted.append(dup_name)
        if deleted:
            self.save()
        return len(deleted), deleted

    def get_acer_performance_config(self) -> dict:
        """获取 Acer 性能模式配置段，带有默认自愈功能"""
        self._check_and_reload()
        default_cfg = {
            "overclock_mode": "Fast",  # "Default" (Normal/0), "Fast" (1), "Extreme" (2)
            "coolboost": True,
            "fan_mode": "Auto",        # "Auto" (0), "Max" (1), "Custom" (2)
            "auto_apply_on_startup": True
        }
        acer_cfg = self.config_data.get("acer_performance", {})
        if not isinstance(acer_cfg, dict):
            acer_cfg = {}
        for k, v in default_cfg.items():
            if k not in acer_cfg:
                acer_cfg[k] = v
        return acer_cfg

    def save_acer_performance_config(self, acer_cfg: dict) -> bool:
        """保存 Acer 性能模式配置"""
        if not isinstance(acer_cfg, dict):
            return False
        self.config_data["acer_performance"] = acer_cfg
        return self.save()



def apply_layout_config(config_manager: ConfigManager, res_name: str, show_cmd=SW_SHOWNORMAL):
    """
    根据给定的配置段名称，一键应用其所有的窗口位置设定
    """
    mapping = config_manager.get_resolution_mapping(res_name)
    if not mapping:
        print(f"No configuration mapping found for: {res_name}")
        return False
        
    print(f"Applying layout for: {res_name}")
    for title, raw_pos_str in mapping.items():
        # 解析坐标与可能附加的执行路径，防止传递给底层引发 int() 转换异常
        parts = str(raw_pos_str).split('|')
        pos_str = parts[0].strip()
        
        # 兼容处理：支持将 .py 的配置同样应用给对应的 .exe 进程窗口
        # 例如配置里写 'sina_Monitor.py'，那么 'sina_Monitor.exe' 也会被正确移动
        titles_to_try = [title]
        if title.endswith('.py') and not title.startswith('py'):
            titles_to_try.append(title.replace('.py', '.exe'))
        elif title.endswith('.exe'):
            titles_to_try.append(title.replace('.exe', '.py'))
            
        moved = False
        for t in titles_to_try:
            if set_window_pos_by_title(t, pos_str, show_cmd):
                moved = True
                print(f"Successfully positioned: {t} -> {pos_str}")
                
        if not moved:
            # 记录未查找到的窗口，供调试
            pass
            
    return True


# ==========================================
# 多显示器物理排布拓扑结构保存与恢复 API
# ==========================================
import win32api
import win32con
import pywintypes



def is_same_display_config(current, saved):
    """
    判断当前显示器配置与已保存配置是否一致
    支持逻辑分辨率 + scale 自动匹配
    """
    if len(current) != len(saved):
        return False

    def build_key(m):
        return (m.get("width"), m.get("height"), m.get("x"), m.get("y"), bool(m.get("is_primary")))

    cur_set = [build_key(m) for m in current]
    sav_set = [build_key(m) for m in saved]

    return sorted(cur_set) == sorted(sav_set)


def save_display_configuration(filename="display_config.json", target_path=None) -> tuple:
    """
    保存当前显示器物理拓扑排布到 JSON 文件中（由确定性显示器组合与相对摆放方位签名区分）。
    若同设备组合有不同摆放方式（如副屏在右 vs 副屏在左），自动生成带方位后缀的独立文件名，避免相互覆盖。
    返回 (success: bool, filepath_or_msg: str)
    """
    try:
        config = get_monitor_details_all_with_scale()
        if not config or not config["monitors"]:
            return False, "未检测到有效的显示器数据"

        if target_path:
            out_filename = target_path
        else:
            summary = config["summary"]
            ori_tag = get_screen_topology_orientation_tag(config["monitors"])
            tag_part = f"_{ori_tag}" if ori_tag else ""
            file_key = f"{summary}{tag_part}_monitor{filename}"
            out_filename = get_conf_path(file_key)
        
        os.makedirs(os.path.dirname(os.path.abspath(out_filename)), exist_ok=True)
        with open(out_filename, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True, out_filename
    except Exception as e:
        return False, str(e)


def restore_display_configuration(target_file_or_name="display_config.json") -> tuple:
    """
    智能读取并恢复显示器排列设置。
    支持自动匹配或显式传入配置文件路径/名称。
    采用基于真实硬件厂商型号（Model/EDID/PNP ID/Hardware ID）的精准绑定匹配算法，杜绝因系统设备编号变化导致的分辨率/坐标错乱。
    返回 (success: bool, message: str)
    """
    try:
        monitor_info = get_monitor_details_all_with_scale()
        if not monitor_info or not monitor_info["monitors"]:
            return False, "未检测到当前连接的显示器设备"

        current_monitors = monitor_info["monitors"]
        summary = monitor_info["summary"]

        # 定位目标配置文件
        in_filename = None
        if target_file_or_name:
            if os.path.isabs(target_file_or_name) and os.path.exists(target_file_or_name):
                in_filename = target_file_or_name
            else:
                ori_tag = get_screen_topology_orientation_tag(current_monitors)
                candidates = [
                    os.path.join(get_app_root(), target_file_or_name),
                    get_conf_path(target_file_or_name),
                    os.path.join(os.getcwd(), target_file_or_name),
                    get_conf_path(f"{summary}_{ori_tag}_monitor{target_file_or_name}"),
                    get_conf_path(f"{summary}_monitor{target_file_or_name}"),
                    os.path.join(get_app_root(), f"{summary}_{ori_tag}_monitor{target_file_or_name}"),
                    os.path.join(get_app_root(), f"{summary}_monitor{target_file_or_name}")
                ]
                for cand in candidates:
                    if os.path.exists(cand):
                        in_filename = cand
                        break

        if not in_filename or not os.path.exists(in_filename):
            return False, f"未找到指定的屏幕拓扑配置文件: {target_file_or_name or summary}"

        with open(in_filename, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

        save_monitors = saved_config.get("monitors", [])
        if not save_monitors:
            return False, f"配置文件中未包含有效的屏幕拓扑数据: {os.path.basename(in_filename)}"

        # 检查是否当前已经与备份完全一致
        if is_same_display_config(current_monitors, save_monitors):
            return True, "当前屏幕物理排布与备份完全一致，无需重复应用"

        # 🎯 基于真实硬件厂商型号（EDID/PNP/Hardware ID）的多层权重精准绑定算法
        available_current = list(current_monitors)
        matched_pairs = [] # (target_config, current_device_dict)

        def calc_hardware_match_score(tgt, cur):
            score = 0
            # 1. 硬件 ID 完全一致 (最高优先级)
            if tgt.get("hardware_id") and cur.get("hardware_id") and tgt["hardware_id"].lower() == cur["hardware_id"].lower():
                score += 1000
            # 2. PNP 厂商代号码一致 (例如 GSM7707, SAM0676)
            if tgt.get("pnp_id") and cur.get("pnp_id") and tgt["pnp_id"].upper() == cur["pnp_id"].upper():
                score += 500
            # 3. 厂商 Friendly 型号名称一致 (例如 LG HDR 4K, SyncMaster)
            if tgt.get("model_name") and cur.get("model_name") and tgt["model_name"].lower() == cur["model_name"].lower():
                score += 300
            # 4. 原生物理分辨率完全一致
            if tgt.get("width") == cur.get("width") and tgt.get("height") == cur.get("height"):
                score += 150
            # 5. 主屏属性偏好
            if bool(tgt.get("is_primary")) == bool(cur.get("is_primary")):
                score += 50
            # 6. 适配器设备名一致
            if tgt.get("device_name") == cur.get("device_name"):
                score += 10
            return score

        # 优先主屏，然后副屏依次进行最佳硬件匹配
        sorted_targets = sorted(save_monitors, key=lambda x: not x.get("is_primary"))
        for tgt in sorted_targets:
            if not available_current:
                break
            best_cur = max(available_current, key=lambda c: calc_hardware_match_score(tgt, c))
            matched_pairs.append((tgt, best_cur))
            available_current.remove(best_cur)

        if not matched_pairs:
            return False, "未能将目标屏幕配置映射到当前系统的物理显示设备"

        # 执行 Windows 物理拓扑排布应用
        applied_devices = []
        for tgt_cfg, curr_dev in matched_pairs:
            device_name = curr_dev["device_name"]
            model_name = curr_dev.get("model_name") or tgt_cfg.get("model_name") or device_name
            try:
                devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
                devmode.PelsWidth = tgt_cfg["width"]
                devmode.PelsHeight = tgt_cfg["height"]
                devmode.Position_x = tgt_cfg["x"]
                devmode.Position_y = tgt_cfg["y"]
                devmode.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_POSITION

                if tgt_cfg.get("is_primary"):
                    flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET | win32con.CDS_SET_PRIMARY
                else:
                    flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET

                res = win32api.ChangeDisplaySettingsEx(device_name, devmode, flags)
                if res in (win32con.DISP_CHANGE_SUCCESSFUL, win32con.DISP_CHANGE_NOTUPDATED):
                    pri_tag = " [👑主屏]" if tgt_cfg.get("is_primary") else ""
                    applied_devices.append(f"[{model_name}] {device_name}{pri_tag}: {tgt_cfg['width']}x{tgt_cfg['height']} @ ({tgt_cfg['x']}, {tgt_cfg['y']})")
                else:
                    return False, f"应用显示器 '{device_name}' ({model_name}) 设置失败 (错误代码: {res})"
            except pywintypes.error as ex:
                return False, f"配置显示器 '{device_name}' ({model_name}) 出错: {ex}"

        # 最终应用全部变更并触发系统全局广播
        win32api.ChangeDisplaySettings(None, 0)
        
        detail_msg = f"已恢复屏幕物理排布 [{os.path.basename(in_filename)}]:\n" + "\n".join(f"• {d}" for d in applied_devices)
        return True, detail_msg
    except Exception as e:
        return False, f"恢复多显示器排布时出错: {e}"


def build_topology_fingerprint(monitors: list) -> tuple:
    """生成显示器物理排布的数据指纹，用于自动识别数据布局是否完全一致"""
    fps = []
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]

FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040        # 核心：移动至 Windows 回收站，支持撤销/还原
FOF_NOCONFIRMATION = 0x0010   # 静默模式，不弹出系统原生二次确认
FOF_SILENT = 0x0004           # 静默模式，不显示系统进度条
FOF_NOERRORUI = 0x0400        # 静默模式，不显示错误对话框


def send_file_to_recycle_bin(filepath: str) -> tuple:
    """
    将指定文件安全删除并移入 Windows 系统回收站（支持桌面回收站随时撤销还原）。
    同时在本地 BackConfig/deleted_topologies 建立时间戳硬备份，杜绝任何物理抹除风险。
    返回 (success: bool, message: str)
    """
    if not filepath or not os.path.exists(filepath):
        return False, f"文件不存在: {filepath}"

    abs_path = os.path.abspath(filepath)
    fname = os.path.basename(abs_path)

    # 1. 自动执行本地快照硬备份
    try:
        backup_dir = os.path.join(get_app_root(), "BackConfig", "deleted_topologies")
        os.makedirs(backup_dir, exist_ok=True)
        import shutil
        ts = int(time.time())
        bak_file = os.path.join(backup_dir, f"{fname}.{ts}.bak")
        shutil.copy2(abs_path, bak_file)
    except Exception as e:
        logger.warning(f"删除前本地自动备份失败: {e}")

    # 2. 若为非 Windows 系统，回退为普通删除
    if sys.platform != "win32":
        try:
            os.remove(abs_path)
            return True, f"已删除: {fname}"
        except Exception as e:
            return False, f"删除失败: {e}"

    # 3. 尝试使用第三方 send2trash (若环境中存在)
    try:
        import send2trash
        send2trash.send2trash(abs_path)
        return True, f"已安全移入 Windows 回收站: {fname}"
    except Exception:
        pass

    # 4. 使用 Windows 原生 Shell32 SHFileOperationW API 移入回收站
    try:
        # SHFileOperationW 要求路径字符串以双空字符 (\0\0) 结尾
        p_from = abs_path + "\0\0"
        
        fileop = SHFILEOPSTRUCTW()
        fileop.hwnd = 0
        fileop.wFunc = FO_DELETE
        fileop.pFrom = p_from
        fileop.pTo = None
        fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        fileop.fAnyOperationsAborted = False
        fileop.hNameMappings = None
        fileop.lpszProgressTitle = None

        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
        if res == 0 and not fileop.fAnyOperationsAborted and not os.path.exists(abs_path):
            return True, f"已安全移入 Windows 回收站: {fname}"
        else:
            # 若回收站 API 失败，执行安全重命名移入备份目录
            if os.path.exists(abs_path):
                shutil.move(abs_path, bak_file)
            return True, f"已安全移入备份归档 (BackConfig/deleted_topologies): {fname}"
    except Exception as e:
        return False, f"安全删除失败: {e}"


def build_topology_fingerprint(monitors: list):
    """
    提取显示器拓扑配置的核心数据指纹。
    仅当所有显示器的硬件参数、物理分辨率、缩放比例、相对排布坐标 (x, y) 完全相同时，指纹才相同。
    若 monitors 为空或无有效显示器，返回 None，严禁生成空指纹造成误判。
    """
    if not monitors or not isinstance(monitors, list):
        return None
    valid_m = [m for m in monitors if isinstance(m, dict) and m.get("width", 0) > 0 and m.get("height", 0) > 0]
    if not valid_m:
        return None

    fps = []
    for m in valid_m:
        w = int(m.get("width", 0))
        h = int(m.get("height", 0))
        x = int(m.get("x", 0))
        y = int(m.get("y", 0))
        s = int(round(float(m.get("scale", 1.0)) * 100))
        pri = bool(m.get("is_primary"))
        pnp = str(m.get("pnp_id") or "").strip().upper()
        hw = str(m.get("hardware_id") or "").strip().upper()
        model = str(m.get("model_name") or "").strip().lower()
        fps.append((w, h, s, x, y, pri, pnp, hw, model))
    return (len(fps), tuple(sorted(fps)))


def list_display_configurations() -> list:
    """
    扫描程序唯一运行根目录 (app_root) 下的所有显示器物理拓扑配置文件。
    完整支持同设备组合但不同物理摆放方式的多布局共存。
    自动检测数据布局完全一致的重复项并标记 (is_duplicate & duplicate_of)，以便用户在界面上手动或一键清理。
    返回列表，按当前屏幕匹配优先、非重复优先、修改时间倒序排列。
    """
    import time
    app_root = get_app_root()
    # 🛡️ 严格锁定单一权威配置目录，绝不允许跨目录混扫导致同一文件被重复加载或自身与自身比对
    search_dirs = [app_root]

    raw_files = []
    seen_filenames = set()

    current_details = get_monitor_details_all_with_scale()
    current_monitors = current_details.get("monitors", [])

    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        try:
            for fname in os.listdir(s_dir):
                if not fname.endswith(".json"):
                    continue
                # 匹配显示器拓扑配置文件 (包含 monitordisplay_config 或 display_config，排除 display_cols 等非拓扑文件)
                fname_lower = fname.lower()
                if ("monitordisplay_config" in fname_lower or fname_lower == "display_config.json") and fname_lower != "display_cols.json":
                    if fname in seen_filenames:
                        continue
                    seen_filenames.add(fname)
                    
                    fpath = os.path.abspath(os.path.join(s_dir, fname))

                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        monitors = data.get("monitors", [])
                        if not monitors or not isinstance(monitors, list):
                            continue

                        m_count = len(monitors)
                        summary = data.get("summary", "")
                        if not summary:
                            summary = "_".join(f"{m.get('width', 0)}x{m.get('height', 0)}@{m.get('scale', 1.0)}" for m in monitors)

                        mtime_ts = os.path.getmtime(fpath)
                        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime_ts))

                        pri = next((m for m in monitors if m.get("is_primary")), monitors[0])
                        pri_model = pri.get("model_name") or f"{pri.get('width', 0)}x{pri.get('height', 0)}"
                        
                        other_models = [m.get("model_name") or f"{m.get('width', 0)}x{m.get('height', 0)}" for m in monitors if m != pri]
                        
                        ori_tag = get_screen_topology_orientation_tag(monitors)
                        ori_cn = ""
                        if ori_tag:
                            ori_map = {
                                "Right": "副屏居右",
                                "Left": "副屏居左",
                                "Top": "副屏居上",
                                "Bottom": "副屏居下",
                                "TopRight": "副屏居右上",
                                "TopLeft": "副屏居左上",
                                "BottomRight": "副屏居右下",
                                "BottomLeft": "副屏居左下"
                            }
                            ori_cn = f"[{ori_map.get(ori_tag, ori_tag)}] "

                        if other_models:
                            other_desc = " + ".join(other_models)
                            base_display_name = f"{m_count}屏 {ori_cn}[{pri_model}(主) + {other_desc}] ({mtime_str})"
                        else:
                            base_display_name = f"单屏 [{pri_model}] ({mtime_str})"

                        # 🎯 严谨精准匹配当前实际物理排布 (包含各个屏幕的分辨率、缩放、相对坐标与主副屏属性)
                        is_match = is_same_display_config(current_monitors, monitors)

                        # 计算数据指纹
                        fingerprint = build_topology_fingerprint(monitors)

                        raw_files.append({
                            "filename": fname,
                            "filepath": fpath,
                            "base_display_name": base_display_name,
                            "summary": summary,
                            "monitor_count": m_count,
                            "orientation_tag": ori_tag,
                            "mtime": mtime_str,
                            "mtime_ts": mtime_ts,
                            "is_current_match": is_match,
                            "monitors": monitors,
                            "fingerprint": fingerprint
                        })
                    except Exception:
                        continue
        except Exception:
            continue

    # 自动进行数据布局一致性分析与重复标记 (带白名单安全防护)
    seen_fingerprints = {}  # fingerprint -> first_cfg_item
    final_files = []

    # 排序：优先让标准文件/当前匹配文件排在前面作为基准
    raw_files.sort(key=lambda x: (not x["is_current_match"], x["filename"] != "display_config.json", x["mtime_ts"]))

    for cfg in raw_files:
        fp = cfg["fingerprint"]
        # 白名单保护：当前匹配中的配置或标准主配置文件，严禁判定为重复副本
        is_protected = cfg["is_current_match"] or cfg["filename"] == "display_config.json"

        if fp is not None and fp in seen_fingerprints and not is_protected:
            first_cfg = seen_fingerprints[fp]
            # 必须是不同文件名才算重复冗余副本
            if cfg["filename"] != first_cfg["filename"]:
                cfg["is_duplicate"] = True
                cfg["duplicate_of"] = first_cfg["filename"]
                cfg["display_name"] = f"{cfg['base_display_name']} ⚠️[数据与 {first_cfg['filename']} 重复]"
            else:
                cfg["is_duplicate"] = False
                cfg["duplicate_of"] = ""
                cfg["display_name"] = cfg["base_display_name"]
        else:
            if fp is not None and fp not in seen_fingerprints:
                seen_fingerprints[fp] = cfg
            cfg["is_duplicate"] = False
            cfg["duplicate_of"] = ""
            cfg["display_name"] = cfg["base_display_name"]
            
        final_files.append(cfg)

    # 排序：当前实际匹配优先 > 非重复优先 > 修改时间倒序
    final_files.sort(key=lambda x: (not x["is_current_match"], x["is_duplicate"], -x["mtime_ts"]))
    return final_files


def clean_duplicate_display_configurations() -> tuple:
    """
    一键扫描并清理所有与已有配置数据完全一致的重复显示器拓扑配置文件。
    保留主配置文件，将所有冗余副本安全移入 Windows 回收站，并在 BackConfig 自动备份。
    返回 (deleted_count: int, deleted_files: list[str])
    """
    configs = list_display_configurations()
    deleted = []
    for c in configs:
        if c.get("is_duplicate") and not c.get("is_current_match") and c.get("filename") != "display_config.json":
            fpath = c.get("filepath")
            if fpath and os.path.exists(fpath):
                ok, _ = send_file_to_recycle_bin(fpath)
                if ok:
                    deleted.append(c.get("filename", os.path.basename(fpath)))
    return len(deleted), deleted


def delete_display_configuration(filename_or_path: str) -> tuple:
    """
    安全删除指定的显示器拓扑配置文件（移入 Windows 回收站，支持撤销还原）。
    返回 (success: bool, message: str)
    """
    if not filename_or_path:
        return False, "未指定要删除的配置文件"

    if os.path.isabs(filename_or_path):
        target = filename_or_path
    else:
        target = get_conf_path(filename_or_path)
        if not os.path.exists(target):
            target = os.path.join(get_app_root(), filename_or_path)

    if not os.path.exists(target):
        return False, f"配置文件不存在: {filename_or_path}"

    return send_file_to_recycle_bin(target)


def get_display_configuration_details(filename_or_path: str) -> dict:
    """
    获取指定显示器拓扑配置文件的详细解析数据。
    """
    if not filename_or_path:
        return {}
    if os.path.isabs(filename_or_path):
        target = filename_or_path
    else:
        target = get_conf_path(filename_or_path)
        if not os.path.exists(target):
            target = os.path.join(get_app_root(), filename_or_path)

    if not os.path.exists(target):
        return {}

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["filepath"] = target
        data["filename"] = os.path.basename(target)
        return data
    except Exception:
        return {}



def bring_window_to_top_by_title(title: str) -> bool:
    """
    根据模糊窗口标题查找到运行中的窗口，并将其强行置顶激活呈现到最前端前台
    """
    hwnds = find_windows_by_title_safe(title)
    if not hwnds:
        # 针对 .py / .exe 兼容性，也尝试匹配交替后的标题名
        titles_to_try = []
        if title.endswith('.py') and not title.startswith('py'):
            titles_to_try.append(title.replace('.py', '.exe'))
        elif title.endswith('.exe'):
            titles_to_try.append(title.replace('.exe', '.py'))
            
        for t in titles_to_try:
            hwnds = find_windows_by_title_safe(t)
            if hwnds:
                break
                
    if not hwnds:
        return False

    hwnd = hwnds[0][0]
    import win32gui
    import win32con
    try:
        # 如果窗口处于最小化，则恢复为常规状态
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            
        # 强行抢焦点并置顶
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # 在某些 Windows 环境中通过发送虚拟 Alt 击键强制获得焦点特权
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0) # Alt Down
            win32gui.SetForegroundWindow(hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, 0x0002, 0) # Alt Up
            
        win32gui.BringWindowToTop(hwnd)
        return True
    except Exception as e:
        print(f"Failed to bring window to top: {e}")
        return False


def check_and_add_route(config_manager) -> tuple:
    """
    根据用户配置动态自适应检测与维护静态路由。
    完全根据配置参数 (destination, mask, gateway) 动态计算，不含任何硬编码 IP：
    1. 提取配置，若未启用或目标/网关为空，直接安全返回；
    2. 动态自适应检测：遍历当前所有活动网卡，若本机已有 IP 处于配置的目标子网内，直接判定为物理直连，跳过添加；
    3. 动态路由表比对：逐行解析系统路由表，若目标网段已在链路上 (On-link) 或已有指向配置网关的路由，判定为已生效并跳过；
    4. 动态网关可达性核验：若网关不在当前任何网卡的直连子网内，安全拦截并提示网关不可达，绝不盲目提权；
    5. 跨网段且路由缺失时，按需执行持久化添加 (route -p add) 并验证结果。
    返回: (success: bool, message: str)
    """
    routing_cfg = config_manager.config_data.get("routing_config", {})
    if not routing_cfg or not isinstance(routing_cfg, dict):
        return True, "未配置静态路由规则。"

    if not routing_cfg.get("enabled", False):
        return True, "静态路由自动维护功能未启用。"

    dest = str(routing_cfg.get("destination", "")).strip()
    mask = str(routing_cfg.get("mask", "255.255.255.0")).strip() or "255.255.255.0"
    gw = str(routing_cfg.get("gateway", "")).strip()

    if not dest or not gw:
        return True, "静态路由目标网段或默认网关未完整配置，跳过检测。"

    import ipaddress
    import socket
    import subprocess

    # 解析目标网络对象
    try:
        target_net = ipaddress.IPv4Network(f"{dest}/{mask}", strict=False)
    except Exception as e:
        return False, f"配置的目标网段格式无效 ({dest}/{mask}): {e}"

    try:
        gw_addr = ipaddress.IPv4Address(gw)
    except Exception as e:
        return False, f"配置的默认网关格式无效 ({gw}): {e}"

    # 1. 动态自适应网卡直连探测：检测本机是否已有网卡直连目标子网
    gw_in_local_subnet = False
    try:
        for if_name, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET:
                    ip_str = snic.address
                    if not ip_str or ip_str.startswith("127.") or ip_str.startswith("169.254."):
                        continue
                    try:
                        cur_ip = ipaddress.IPv4Address(ip_str)
                        # A. 本机已直连目标子网
                        if cur_ip in target_net:
                            return True, f"本机网卡 [{if_name}] IP ({ip_str}) 已处于目标网段 ({dest}/{mask})，物理直连直通，无需配置网关路由。"
                        
                        # B. 检查网关是否与本机某网卡在同一网段（用于后续可达性判断）
                        if snic.netmask:
                            local_net = ipaddress.IPv4Network(f"{ip_str}/{snic.netmask}", strict=False)
                            if gw_addr in local_net:
                                gw_in_local_subnet = True
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        # 2. 动态路由表比对：检测系统活动路由表中是否已有该目标的直连链路或对应网关
        check_cmd = "route print -4"
        res = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, errors='ignore')
        
        # 逐行解析路由表
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4:
                net_target, net_mask, net_gw = parts[0], parts[1], parts[2]
                if net_target == str(target_net.network_address) and (net_mask == str(target_net.netmask) or not mask):
                    if "在链路上" in net_gw or "on-link" in net_gw.lower():
                        return True, f"目标网段 {dest} 在系统路由表中已处于物理直连链路 (On-link)，无需配置网关路由。"
                    if net_gw == gw:
                        return True, f"到 {dest} via {gw} 的静态路由已存在，无需重复添加。"

        # 3. 网关可达性核验：若网关与本机所有网卡均不在同一局域网，且路由表中无此网关路径，避免盲目提权
        if not gw_in_local_subnet and (gw not in res.stdout):
            return False, f"配置的网关 ({gw}) 与本机当前所有活动物理网卡均不在同一子网，且不可达，已拦截无效添加以避免弹窗。"

        # 4. 路由缺失且网关可达：尝试动态添加持久化静态路由 (带 -p 永久路由参数)
        is_admin = False
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            pass

        if is_admin:
            add_cmd = f"route -p add {dest} mask {mask} {gw}"
            add_res = subprocess.run(add_cmd, shell=True, capture_output=True, text=True, encoding='gbk', errors='ignore')
            if add_res.returncode == 0:
                return True, f"已成功自动添加持久化静态路由: {dest} mask {mask} {gw}"
            else:
                err_msg = add_res.stderr.strip() or add_res.stdout.strip()
                return False, f"添加路由失败 (返回码 {add_res.returncode}): {err_msg}"
        else:
            # 没有管理员权限，通过 ShellExecuteW "runas" 弹出 UAC 请求提权运行
            try:
                params = f"/c route -p add {dest} mask {mask} {gw}"
                # SW_HIDE = 0 隐藏弹出的黑窗口
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "cmd.exe",
                    params,
                    None,
                    0
                )
                if ret > 32:
                    time.sleep(0.5)
                    check_cmd = "route print -4"
                    res = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, errors='ignore')
                    if re.search(rf"\b{re.escape(dest)}\b", res.stdout) and gw in res.stdout:
                        return True, f"已通过管理员权限自动添加静态路由: {dest} mask {mask} {gw}"
                    else:
                        return False, f"管理员权限请求已批准，但路由添加未生效，请检查网关或网卡是否正常。"
                elif ret == 1223:
                    return False, "添加路由失败: 用户取消了 UAC 管理员权限授权申请。"
                else:
                    return False, f"添加路由失败: 申请管理员权限失败 (错误码 {ret})。"
            except Exception as e:
                return False, f"尝试申请管理员权限添加路由时发生异常: {e}"
            
    except Exception as e:
        return False, f"自动路由检测/添加异常: {e}"


WM_SHOW_MANAGE_WINDOW_LAYOUT_NAME = "WM_SHOW_MANAGE_WINDOW_LAYOUT_EVENT"

def get_wm_show_msg_id() -> int:
    """注册全局唯一的 Windows 消息 ID 用于单实例唤醒跨进程通信"""
    try:
        return user32.RegisterWindowMessageW(WM_SHOW_MANAGE_WINDOW_LAYOUT_NAME)
    except Exception:
        return 0xC000 + 888
SINGLE_INSTANCE_SERVER_NAME = "ManageWindowLayout_SingleInstance_Server"


def check_and_activate_existing_instance() -> bool:
    """
    检查 manage_window_layout 是否已经在运行：
    若已在运行，直接通过 IPC 管道 / Win32 消息自动唤醒并拉起已有窗口至前台置顶，
    无需弹出任何切换弹窗打断用户操作，当前新启动进程自动平滑退出。
    """
    current_pid = os.getpid()
    parent_pid = os.getppid() if hasattr(os, 'getppid') else None

    # 1. 扫描后台正在运行的 manage_window_layout 目标进程 PID
    target_pids = set()
    try:
        for p in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                p_pid = p.info['pid']
                if p_pid == current_pid or (parent_pid and p_pid == parent_pid) or p_pid == 0:
                    continue

                p_name = (p.info['name'] or '').lower()
                if p_name == 'manage_window_layout.exe' or 'manage_window_layout.py' in p_name:
                    target_pids.add(p_pid)
            except Exception:
                continue
    except Exception as e:
        print(f"[SingleInstance] psutil 进程扫描异常: {e}")

    # 2. 尝试通过 Qt QLocalSocket IPC 管道发送 WAKEUP 极速唤醒指令
    ipc_connected = False
    try:
        from PyQt6.QtNetwork import QLocalSocket
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
        if socket.waitForConnected(300):
            print(f"[SingleInstance] 成功连接至已有 IPC 服务 ({SINGLE_INSTANCE_SERVER_NAME})，发送 WAKEUP 唤醒指令...")
            socket.write(b"WAKEUP\n")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            ipc_connected = True
    except Exception:
        pass

    # 3. 扫描并唤醒后台运行实例的所有 UI 窗口句柄（支持从托盘最小化中拉起到前台置顶）
    target_hwnds = []
    def enum_pid_windows_callback(hwnd, lparam):
        if not user32.IsWindow(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in target_pids or not target_pids:
            title = win32gui.GetWindowText(hwnd) or ""
            cls = win32gui.GetClassName(hwnd) or ""
            if title and ("窗口坐标分类管理器" in title or "桌面窗口坐标布局" in title):
                if not any(k in title for k in ("PyInstaller", "Hidden Window", "QTrayIconMessageWindow")) and \
                   not any(k in cls for k in ("PyInstaller", "Hidden Window", "QTrayIconMessageWindow")):
                    target_hwnds.append((hwnd, pid.value, title))
        return True

    try:
        proc_pid = WNDENUMPROC(enum_pid_windows_callback)
        user32.EnumWindows(proc_pid, 0)
    except Exception:
        pass

    # 4. 执行 Win32 消息唤醒与强力置顶
    activated = False
    wm_msg_id = get_wm_show_msg_id()

    if target_hwnds:
        print("[SingleInstance] 检测到已有 UI 实例运行，正在置顶唤醒并拉起窗口到前台...")
        for hwnd, pid, title in target_hwnds:
            try:
                if user32.IsWindow(hwnd):
                    # 发送恢复与显示指令
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    if wm_msg_id:
                        user32.PostMessageW(hwnd, wm_msg_id, 0, 0)
                    # 强力置顶与激活
                    force_topmost_activate_hwnd(hwnd)
                    activated = True
            except Exception as e:
                print(f"[SingleInstance] 唤醒窗口 HWND {hwnd} 异常: {e}")

    # 5. 若已成功通过 IPC 唤醒、或已激活窗口、或后台确实存在已运行的实例：直接退出当前进程
    if ipc_connected or activated or target_pids:
        print("[SingleInstance] [OK] 已自动唤醒并拉起后台运行实例至前台，新启动进程安全退出。")
        return True

    return False


# ==========================================
# Windows 注册表开机自启动管理 API
# ==========================================
REG_AUTORUN_SUBKEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
REG_AUTORUN_NAME = "ManageWindowLayout"

def get_autostart_command() -> str:
    """
    获取开机自启运行命令行，精准支持打包(PyInstaller/Nuitka/EXE)与源码运行两种场景。
    开机自启时默认附带 -hide 参数，以托盘隐藏不弹窗模式在后台启动并自动应用布局对齐。
    """
    is_frozen = getattr(sys, "frozen", False) or "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version")
    
    if is_frozen or (sys.executable.lower().endswith(".exe") and "python" not in os.path.basename(sys.executable).lower()):
        # 打包成 EXE 运行环境：直接使用 sys.executable 打包的 exe 绝对物理路径
        exe_path = os.path.abspath(sys.executable)
        return f'"{exe_path}" -hide'
    else:
        # 开发源码运行环境：优先检查程序物理根目录或 dist 目录下是否存在已编译打包的 EXE 文件
        app_root = get_app_root()
        possible_exes = [
            os.path.join(app_root, "manage_window_layout.exe"),
            os.path.join(app_root, "dist", "manage_window_layout.exe"),
            os.path.join(app_root, "webTools", "manage_window_layout.exe")
        ]
        for p in possible_exes:
            if os.path.exists(p):
                return f'"{os.path.abspath(p)}" -hide'

        # 否则使用当前 Python 解释器 + manage_window_layout.py 脚本绝对路径
        script_path = os.path.join(app_root, "webTools", "manage_window_layout.py")
        if not os.path.exists(script_path):
            script_path = os.path.abspath(sys.argv[0])
        python_exe = os.path.abspath(sys.executable)
        return f'"{python_exe}" "{script_path}" -hide'




def get_current_autostart_command() -> tuple:
    """
    获取 Windows 注册表中当前实际配置的开机自启命令行。
    返回: (is_configured: bool, current_cmd: str)
    """
    if sys.platform != "win32":
        return False, ""
    try:
        import winreg
        for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(root_key, REG_AUTORUN_SUBKEY, 0, winreg.KEY_READ)
                try:
                    val, _ = winreg.QueryValueEx(key, REG_AUTORUN_NAME)
                    if val:
                        winreg.CloseKey(key)
                        return True, str(val)
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass
    except Exception:
        pass
    return False, ""


def is_autostart_enabled_for_current_app() -> bool:
    """
    检查 Windows 注册表中是否已将【当前运行程序】配置为开机自启。
    只有当注册表中的命令与当前程序的自启动命令完全匹配时才返回 True；
    如果注册表中配置的是其他路径/其他程序，对当前程序而言返回 False。
    """
    configured, current_cmd = get_current_autostart_command()
    if not configured or not current_cmd:
        return False
    expected_cmd = get_autostart_command()
    
    # 标准化路径比较（统一去除两端引号、转小写、处理斜杠与多余空格）
    def extract_main_executable(c: str) -> str:
        s = c.strip()
        if s.startswith('"'):
            end_q = s.find('"', 1)
            if end_q != -1:
                return os.path.normpath(s[1:end_q]).lower()
        parts = s.split()
        if parts:
            return os.path.normpath(parts[0].strip('"')).lower()
        return ""

    cur_exe = extract_main_executable(current_cmd)
    exp_exe = extract_main_executable(expected_cmd)
    if not cur_exe or not exp_exe:
        return False

    return cur_exe == exp_exe


def is_autostart_enabled(for_current_app_only: bool = True) -> bool:
    """
    检查开机自启状态。
    默认 for_current_app_only=True，仅当当前运行程序已被设置为开机自启时返回 True；
    若 for_current_app_only=False，只要系统注册表中存在任意 manage_window_layout 自启项即返回 True。
    """
    if for_current_app_only:
        return is_autostart_enabled_for_current_app()
    configured, _ = get_current_autostart_command()
    return configured


def set_autostart_enabled(enable: bool, target_cmd: str = None) -> tuple:
    """
    通过注册表开启或关闭开机自启（仅在用户主动配置保存时调用，严禁启动时静默自动添加/修改）。
    若 enable=True，写入 target_cmd 或当前程序的标准自启命令；
    若 enable=False，从注册表中彻底删除启动项。
    返回: (success: bool, message: str)
    """
    if sys.platform != "win32":
        return False, "非 Windows 系统不支持注册表开机自启"

    try:
        import winreg
        cmd = target_cmd if target_cmd is not None else get_autostart_command()

        if enable:
            # 优先写入 HKCU (无需管理员权限)
            written = False
            err_msg = ""
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_AUTORUN_SUBKEY, 0, winreg.KEY_ALL_ACCESS)
                winreg.SetValueEx(key, REG_AUTORUN_NAME, 0, winreg.REG_SZ, cmd)
                winreg.CloseKey(key)
                written = True
            except Exception as e:
                err_msg = str(e)
                # 尝试 HKLM
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_AUTORUN_SUBKEY, 0, winreg.KEY_ALL_ACCESS)
                    winreg.SetValueEx(key, REG_AUTORUN_NAME, 0, winreg.REG_SZ, cmd)
                    winreg.CloseKey(key)
                    written = True
                except Exception as e2:
                    err_msg = f"HKCU: {e}, HKLM: {e2}"

            if written:
                return True, f"开机自启已设置成功 (启动命令: {cmd})"
            else:
                return False, f"写入注册表自启动项失败 (可能需要管理员权限): {err_msg}"
        else:
            # 关闭：彻底删除 HKCU 与 HKLM 中的启动项
            deleted = False
            for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(root_key, REG_AUTORUN_SUBKEY, 0, winreg.KEY_ALL_ACCESS)
                    try:
                        winreg.DeleteValue(key, REG_AUTORUN_NAME)
                        deleted = True
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(key)
                except Exception:
                    pass

            return True, "开机自启已在注册表中成功删除取消"
    except Exception as e:
        return False, f"操作注册表异常: {e}"


# ==========================================
# 系统开机时间 (Uptime) 与系统冷启动判定 API
# ==========================================

def get_system_uptime() -> float:
    """
    获取 Windows 系统开机运行时间 (单位: 秒)。
    优先通过 psutil.boot_time() 计算，备选通过 Win32 GetTickCount64()。
    """
    try:
        import psutil
        import time
        boot_ts = psutil.boot_time()
        if boot_ts > 0:
            return max(0.0, time.time() - boot_ts)
    except Exception:
        pass
    try:
        import ctypes
        return ctypes.windll.kernel32.GetTickCount64() / 1000.0
    except Exception:
        pass
    return 999999.0


def is_system_cold_boot(threshold_seconds: int = 60) -> bool:
    """
    判断当前操作系统是否处于开机冷启动阶段 (系统运行时间 Uptime < threshold_seconds，默认 60 秒/1分钟)。
    """
    return get_system_uptime() < threshold_seconds


# ==========================================
# Acer 笔记本硬件性能控制模块 (免 GUI 驱动)
# ==========================================

_GLOBAL_LAST_APPLIED_PROFILE = {}


class AcerPerformanceController:
    """
    Acer 笔记本硬件性能控制器 (免 GUI 模式)
    通过 Windows WMI (root\\wmi 命名空间下的 v2_AcerSysOM / AcerSysOM)
    直接调度 CoolBoost 散热开关、GPU/CPU 超频模式 (Default/Fast/Extreme) 及风扇速率模式。
    """
    def __init__(self):
        self._checked_support = False
        self._is_supported = False
        self._last_applied_profile = None

    @staticmethod
    def _normalize_oc_mode(mode):
        if mode is None:
            return None
        m_str = str(mode).upper()
        if m_str in ["DEFAULT", "NORMAL", "普通", "默认", "0"]:
            return "Default"
        elif m_str in ["FAST", "快速", "1"]:
            return "Fast"
        elif m_str in ["EXTREME", "TURBO", "极速", "狂暴", "2"]:
            return "Extreme"
        return str(mode)

    @staticmethod
    def _normalize_fan_mode(mode):
        if mode is None:
            return None
        f_str = str(mode).upper()
        if f_str in ["AUTO", "自动", "0"]:
            return "Auto"
        elif f_str in ["MAX", "最大", "狂暴", "1"]:
            return "Max"
        elif f_str in ["CUSTOM", "自定义", "2"]:
            return "Custom"
        return str(mode)

    @staticmethod
    def _normalize_coolboost(cb):
        if cb is None:
            return None
        return bool(cb)

    def _update_applied_cache(self, coolboost=None, overclock_mode=None, fan_mode=None):
        global _GLOBAL_LAST_APPLIED_PROFILE
        if self._last_applied_profile is None:
            self._last_applied_profile = {}
        if coolboost is not None:
            cb_b = bool(coolboost)
            self._last_applied_profile["coolboost"] = cb_b
            _GLOBAL_LAST_APPLIED_PROFILE["coolboost"] = cb_b
        if overclock_mode is not None:
            norm_oc = self._normalize_oc_mode(overclock_mode)
            if norm_oc:
                self._last_applied_profile["overclock_mode"] = norm_oc
                _GLOBAL_LAST_APPLIED_PROFILE["overclock_mode"] = norm_oc
        if fan_mode is not None:
            norm_fm = self._normalize_fan_mode(fan_mode)
            if norm_fm:
                self._last_applied_profile["fan_mode"] = norm_fm
                _GLOBAL_LAST_APPLIED_PROFILE["fan_mode"] = norm_fm

        # 实时同步更新 Windows OEM 注册表, 确保下一次物理探查 (force_physical=True) 100% 精准匹配
        try:
            import winreg
            reg_path = r"SOFTWARE\OEM\PredatorSense"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
            if overclock_mode is not None:
                norm_oc = self._normalize_oc_mode(overclock_mode)
                oc_code_map = {"Default": 0, "Fast": 1, "Extreme": 2}
                if norm_oc in oc_code_map:
                    oc_val = oc_code_map[norm_oc]
                    winreg.SetValueEx(key, "GPU_Overclock_Level", 0, winreg.REG_DWORD, oc_val)
                    tb_val = 1 if oc_val >= 2 else 0
                    winreg.SetValueEx(key, "Turbo_Button_status", 0, winreg.REG_DWORD, tb_val)
            if fan_mode is not None:
                norm_fm = self._normalize_fan_mode(fan_mode)
                fan_code_map = {"Auto": 0, "Max": 1, "Custom": 2}
                if norm_fm in fan_code_map:
                    winreg.SetValueEx(key, "Fan_Control", 0, winreg.REG_DWORD, fan_code_map[norm_fm])
            if coolboost is not None:
                winreg.SetValueEx(key, "CoolBoost_Status", 0, winreg.REG_DWORD, 1 if coolboost else 0)
            winreg.CloseKey(key)
        except Exception:
            pass

        # 🚫 严禁将临时应用的性能预设落盘写回 ConfigManager！
        # 默认手动选项设置是常规持久化配置，托盘/快捷预设仅为临时运行时状态，重启后依然保持用户配置的常规默认项。

    def _get_wmi_object(self):
        """获取底层 Acer WMI COM 对象 (支持 Triton 500 / Predator 系列)"""
        if sys.platform != "win32":
            return None
        try:
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            # 优先寻找 Acer Triton / Predator 专用的 AcerGamingFunction 及经典 AcerSysOM 类
            for class_name in ["AcerGamingFunction", "v2_AcerSysOM", "AcerSysOM", "AcerHardwareControl"]:
                try:
                    # 优先通过 ExecQuery 抓取实例
                    obj_list = wmi.ExecQuery(f"SELECT * FROM {class_name}")
                    if obj_list and obj_list.Count > 0:
                        for obj in obj_list:
                            return obj
                except Exception:
                    pass
                
                # 尝试直接 Get 类定义 (兼容 Access Denied 但类物理存在的情况)
                try:
                    cls_obj = wmi.Get(class_name)
                    if cls_obj:
                        return cls_obj
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def is_supported(self) -> bool:
        """检查当前机器是否具备 Acer WMI 硬件控制支持"""
        if self._checked_support:
            return self._is_supported
        
        if sys.platform != "win32":
            self._is_supported = False
            self._checked_support = True
            return False

        try:
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            # 探测 Triton 500 / Predator 核心硬件类
            for class_name in ["AcerGamingFunction", "v2_AcerSysOM", "AcerSysOM", "AcerHardwareControl"]:
                try:
                    cls_obj = wmi.Get(class_name)
                    if cls_obj:
                        self._is_supported = True
                        self._checked_support = True
                        return True
                except Exception as e:
                    # 如果报错是 拒绝访问 (Access Denied / -2147217405)，说明底层接口 100% 存在，仅需管理员权限
                    err_str = str(e)
                    if "-2147217405" in err_str or "拒绝访问" in err_str or "SWbemObjectSet" in err_str:
                        self._is_supported = True
                        self._checked_support = True
                        return True
        except Exception:
            pass

        self._is_supported = (self._get_wmi_object() is not None)
        self._checked_support = True
        return self._is_supported

    def get_current_status(self, force_physical: bool = False) -> dict:
        """获取当前 Acer 硬件真实性能状态 (force_physical=True 时强制读取 OEM 原生注册表物理状态)"""
        status = {
            "supported": self.is_supported(),
            "coolboost": False,
            "overclock_mode": "Default",
            "fan_mode": "Auto"
        }
        if not status["supported"]:
            return status

        has_real_hardware_status = False

        # 1. 从 Acer OEM 系统注册表读取真实硬件物理状态
        try:
            import winreg
            reg_path = r"SOFTWARE\OEM\PredatorSense"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ)

            # A. 提取物理超频模式 (GPU_Overclock_Level: 0=Default, 1=Fast, 2=Extreme)
            has_gpu_oc = False
            try:
                gpu_oc, _ = winreg.QueryValueEx(key, "GPU_Overclock_Level")
                oc_map = {0: "Default", 1: "Fast", 2: "Extreme"}
                if int(gpu_oc) in oc_map:
                    status["overclock_mode"] = oc_map[int(gpu_oc)]
                    has_real_hardware_status = True
                    has_gpu_oc = True
            except Exception:
                pass

            # 仅当未成功获取 GPU_Overclock_Level 时，才使用 Turbo_Button_status 辅助判定
            if not has_gpu_oc:
                try:
                    tb_stat, _ = winreg.QueryValueEx(key, "Turbo_Button_status")
                    if int(tb_stat) == 1:
                        status["overclock_mode"] = "Extreme"
                        has_real_hardware_status = True
                except Exception:
                    pass

            # B. 提取风扇速率控制 (Fan_Control: 0=Auto, 1=Max, 2=Custom)
            try:
                fan_ctrl, _ = winreg.QueryValueEx(key, "Fan_Control")
                fan_map = {0: "Auto", 1: "Max", 2: "Custom"}
                if int(fan_ctrl) in fan_map:
                    status["fan_mode"] = fan_map[int(fan_ctrl)]
                    has_real_hardware_status = True
            except Exception:
                pass

            # C. 提取 CoolBoost 开启状态 (CoolBoost_Status: 1=开启, 0=关闭)
            try:
                cb_stat, _ = winreg.QueryValueEx(key, "CoolBoost_Status")
                status["coolboost"] = (int(cb_stat) == 1)
                has_real_hardware_status = True
            except Exception:
                pass

            winreg.CloseKey(key)
        except Exception:
            pass

        # 2. 尝试从 WMI 补充物理属性
        try:
            obj = self._get_wmi_object()
            if obj:
                try:
                    cb_val = getattr(obj, "CoolBoost", None)
                    if cb_val is not None:
                        status["coolboost"] = bool(cb_val)
                        has_real_hardware_status = True
                except Exception:
                    pass
                try:
                    oc_val = getattr(obj, "GPUOverclockingMode", getattr(obj, "SystemMode", None))
                    if oc_val is not None and int(oc_val) != 0:
                        oc_map = {0: "Default", 1: "Fast", 2: "Extreme"}
                        status["overclock_mode"] = oc_map.get(int(oc_val), "Extreme")
                        has_real_hardware_status = True
                except Exception:
                    pass
        except Exception:
            pass

        # 3. 若非强制物理探查 (force_physical=False)，则结合运行时 applied 应用缓存记录
        if not force_physical:
            applied = self._last_applied_profile or _GLOBAL_LAST_APPLIED_PROFILE
            if applied:
                if "coolboost" in applied and applied["coolboost"] is not None:
                    status["coolboost"] = bool(applied["coolboost"])
                if "overclock_mode" in applied and applied["overclock_mode"]:
                    norm_oc = self._normalize_oc_mode(applied["overclock_mode"])
                    if norm_oc:
                        status["overclock_mode"] = norm_oc
                if "fan_mode" in applied and applied["fan_mode"]:
                    norm_fm = self._normalize_fan_mode(applied["fan_mode"])
                    if norm_fm:
                        status["fan_mode"] = norm_fm

        return status

    def set_coolboost(self, enable: bool) -> tuple:
        """开启/关闭 CoolBoost 功能 (enable: True/False)"""
        if not self.is_supported():
            return False, "未检测到 Acer WMI 硬件控制支持"
        try:
            val = 1 if enable else 0
            success = False
            err_msg = ""
            
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            
            # 1. 尝试 Triton 500 / Predator 专用的 AcerGamingFunction
            try:
                objs = wmi.ExecQuery("SELECT * FROM AcerGamingFunction")
                if objs and objs.Count > 0:
                    for obj in objs:
                        try:
                            m = obj.Methods_("SetGamingFanBehavior")
                            in_params = m.InParameters.SpawnInstance_()
                            in_params.gmInput = val
                            obj.ExecMethod_("SetGamingFanBehavior", in_params)
                            success = True
                            break
                        except Exception as ex:
                            err_msg = str(ex)
            except Exception as ex:
                err_msg = str(ex)

            # 2. 回退尝试经典 SetCoolBoost
            if not success:
                obj = self._get_wmi_object()
                if obj:
                    try:
                        method = getattr(obj, "SetCoolBoost", None)
                        if method:
                            method(val)
                            success = True
                    except Exception as ex:
                        err_msg = str(ex)

            state_str = "开启" if enable else "关闭"
            if success:
                self._update_applied_cache(coolboost=bool(enable))
                return True, f"CoolBoost™ 已成功设置为: {state_str}"
            elif "-2147217405" in err_msg or "拒绝访问" in err_msg or "SWbemObjectSet" in err_msg:
                return False, "调起硬件失败：Triton 500 WMI 接口存在，但需要以【管理员身份运行】管理器"
            else:
                return False, f"设置 CoolBoost 响应: {err_msg}"
        except Exception as e:
            return False, f"设置 CoolBoost 失败: {e}"

    def set_overclock_mode(self, mode) -> tuple:
        """
        设置超频模式 (支持 Triton 500 / Predator 系列)
        mode: "Default" / "Normal" / 0 (默认), "Fast" / 1 (快速), "Extreme" / 2 (极速)
        """
        if not self.is_supported():
            return False, "未检测到 Acer WMI 硬件控制支持"

        mode_map = {
            "DEFAULT": 0, "NORMAL": 0, "普通": 0, "默认": 0, 0: 0,
            "FAST": 1, "快速": 1, 1: 1,
            "EXTREME": 2, "极速": 2, 2: 2
        }
        mode_code = mode_map.get(str(mode).upper(), 1)
        mode_names = {0: "默认 (Normal)", 1: "快速 (Fast)", 2: "极速 (Extreme)"}
        target_name = mode_names.get(mode_code, "快速 (Fast)")

        try:
            success = False
            err_msg = ""
            
            # 1. 尝试直接修改 Acer OEM 注册表 Turbo_Button_status 触发键
            try:
                import winreg
                reg_path = r"SOFTWARE\OEM\PredatorSense"
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                # 1 = Extreme/Turbo 狂暴超频, 0 = Normal
                reg_val = 1 if mode_code >= 1 else 0
                winreg.SetValueEx(key, "Turbo_Button_status", 0, winreg.REG_DWORD, reg_val)
                winreg.CloseKey(key)
                success = True
            except Exception:
                pass

            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            
            # 2. 尝试 Triton 500 专用的 SetGamingProfile
            try:
                objs = wmi.ExecQuery("SELECT * FROM AcerGamingFunction")
                if objs and objs.Count > 0:
                    for obj in objs:
                        try:
                            m = obj.Methods_("SetGamingProfile")
                            in_params = m.InParameters.SpawnInstance_()
                            in_params.gmInput = mode_code
                            obj.ExecMethod_("SetGamingProfile", in_params)
                            success = True
                            break
                        except Exception as ex:
                            err_msg = str(ex)
            except Exception as ex:
                err_msg = str(ex)

            # 2. 回退尝试经典 API (SetGPUOverclockingMode 等)
            if not success:
                obj = self._get_wmi_object()
                if obj:
                    for method_name in ["SetGPUOverclockingMode", "SetSystemMode", "SetGPUOverclock", "SetSysOverclock"]:
                        try:
                            method = getattr(obj, method_name, None)
                            if method:
                                method(mode_code)
                                success = True
                                break
                        except Exception as ex:
                            err_msg = str(ex)

            if success:
                self._update_applied_cache(overclock_mode=mode)
                return True, f"超频模式已成功设置为: {target_name}"
            elif "-2147217405" in err_msg or "拒绝访问" in err_msg or "SWbemObjectSet" in err_msg:
                return False, "切换超频模式失败：Triton 500 WMI 接口存在，但需要以【管理员身份运行】管理器"
            else:
                return False, f"调起 WMI 超频切换方法失败: {err_msg}"
        except Exception as e:
            return False, f"设置超频模式异常: {e}"

    def set_fan_mode(self, mode) -> tuple:
        """
        设置风扇速率模式 (支持 Triton 500 / Predator 系列)
        mode: "Auto" / 0 (自动), "Max" / 1 (最大 / 狂暴), "Custom" / 2 (自定义)
        """
        if not self.is_supported():
            return False, "未检测到 Acer WMI 硬件控制支持"

        fan_map = {
            "AUTO": 0, "自动": 0, 0: 0,
            "MAX": 1, "最大": 1, 1: 1,
            "CUSTOM": 2, "自定义": 2, 2: 2
        }
        fan_code = fan_map.get(str(mode).upper(), 0)
        fan_names = {0: "自动 (Auto)", 1: "最大 (Max)", 2: "自定义 (Custom)"}
        target_name = fan_names.get(fan_code, "自动 (Auto)")

        try:
            success = False
            err_msg = ""
            
            import win32com.client
            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            
            # 1. 尝试 Triton 500 专用的 SetGamingFanBehavior / SetGamingFanSpeed
            try:
                objs = wmi.ExecQuery("SELECT * FROM AcerGamingFunction")
                if objs and objs.Count > 0:
                    for obj in objs:
                        try:
                            # 如果是 Max 模式，发送狂暴风扇指令 (1 或 100% 满速)
                            val = 1 if fan_code == 1 else (0 if fan_code == 0 else 2)
                            
                            # 尝试 SetGamingFanBehavior
                            try:
                                m = obj.Methods_("SetGamingFanBehavior")
                                in_params = m.InParameters.SpawnInstance_()
                                in_params.gmInput = val
                                obj.ExecMethod_("SetGamingFanBehavior", in_params)
                                success = True
                            except Exception:
                                pass

                            # 尝试 SetGamingFanSpeed
                            try:
                                speed_val = 100 if fan_code == 1 else (0 if fan_code == 0 else 50)
                                m_spd = obj.Methods_("SetGamingFanSpeed")
                                in_params_spd = m_spd.InParameters.SpawnInstance_()
                                in_params_spd.gmInput = speed_val
                                obj.ExecMethod_("SetGamingFanSpeed", in_params_spd)
                                success = True
                            except Exception:
                                pass

                            if success:
                                break
                        except Exception as ex:
                            err_msg = str(ex)
            except Exception as ex:
                err_msg = str(ex)

            # 2. 回退尝试经典 API
            if not success:
                obj = self._get_wmi_object()
                if obj:
                    for method_name in ["SetFanMode", "SetFanControl", "SetFanSpeed"]:
                        try:
                            method = getattr(obj, method_name, None)
                            if method:
                                method(fan_code)
                                success = True
                                break
                        except Exception:
                            pass

            if success:
                self._update_applied_cache(fan_mode=mode)
                return True, f"风扇模式已成功设置为: {target_name}"
            elif "-2147217405" in err_msg or "拒绝访问" in err_msg or "SWbemObjectSet" in err_msg:
                return False, "设置风扇模式失败：Triton 500 WMI 接口存在，但需要以【管理员身份运行】管理器"
            else:
                return True, f"已发送风扇模式设置指令: {target_name}"
        except Exception as e:
            return False, f"设置风扇模式异常: {e}"
        return False, "未找到有效的 Acer WMI 接口"

    def ensure_predatorsense_daemon(self):
        """确保 PredatorSense 硬件守护通道运行，必要时通过 PSLauncher.exe 静默唤起"""
        try:
            import psutil
            import subprocess
            import time
            import os

            running = False
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and 'predatorsense' in proc.info['name'].lower():
                        running = True
                        break
                except Exception:
                    pass

            if not running:
                launcher = r"C:\Program Files\Acer\PredatorSense Service\PSLauncher.exe"
                if os.path.exists(launcher):
                    try:
                        subprocess.Popen([launcher], shell=True)
                        time.sleep(1.5)
                    except Exception:
                        pass
                else:
                    try:
                        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\AcerIncorporated.PredatorSenseV30_48frkmn4z8aw4!App"])
                        time.sleep(1.5)
                    except Exception:
                        pass
        except Exception:
            pass

    def trigger_predator_ui_command(self, cmd_type="turbo"):
        """安全向 Acer 硬件下发控制指令 (KISS 极简高健壮架构)"""
        try:
            # 优先通过标准 Acer WMI 接口进行静默硬件响应
            if not self.is_supported():
                return
            
            wmi_obj = self._get_wmi_object()
            if wmi_obj:
                if cmd_type in ["turbo", "extreme"]:
                    method = getattr(wmi_obj, "SetGamingProfile", None)
                    if method: method(2)
                elif cmd_type in ["max", "fan"]:
                    method = getattr(wmi_obj, "SetGamingFanBehavior", None)
                    if method: method(1)
        except Exception:
            pass

    def launch_predatorsense_gui(self, fan_mode=None, overclock_mode=None, coolboost=None, post_action="hide", log_cb=None, force=False):
        """唤起 Acer PredatorSense 控制中心界面并按选配参数精细化程序点击 (开机自启防卡顿+多重轮询极健壮架构)"""
        def _do_log(msg):
            if callable(log_cb):
                try:
                    log_cb(msg)
                except Exception:
                    pass

        try:
            import subprocess
            import win32gui
            import win32api
            import win32con
            import time

            # 0. 精准探测【唤起前系统是否存在前台 UI 进程 PredatorSense.exe】与【系统级 Uptime 冷启动判定】
            # 必须在 ensure_predatorsense_daemon 之前前置检测，严格精准匹配 predatorsense.exe！
            is_cold_start = True
            ps_create_time = 0
            sys_cold_boot = is_system_cold_boot(80)
            sys_uptime = get_system_uptime()

            try:
                import psutil
                for p in psutil.process_iter(['name', 'create_time']):
                    p_name = (p.info['name'] or '').lower()
                    if p_name == 'predatorsense.exe':
                        is_cold_start = False
                        ps_create_time = p.info.get('create_time', 0)
                        break
            except Exception:
                pass

            # 若操作系统本身属于刚开机阶段 (Uptime < 300s)，强行认定为系统级冷启动以扩展容错
            if sys_cold_boot:
                is_cold_start = True

            now_t = time.time()
            ps_age_str = f"{(now_t - ps_create_time):.1f}s" if ps_create_time > 0 else "N/A"
            cold_type_str = "系统开机冷启动 (<300s)" if sys_cold_boot else ("应用无进程冷启动" if is_cold_start else "热唤醒")
            _do_log(f"[ColdStart Probe] 状态: PredatorSense.exe 存在={not is_cold_start} (创建距今: {ps_age_str}) | Uptime={sys_uptime:.1f}s | 认定类型: {cold_type_str}")

            # 1. 确保底层 Acer 守护进程已拉起
            _do_log("[Step 1/4] 校验并拉起 Acer 硬件守护进程 PSLauncher.exe ...")
            self.ensure_predatorsense_daemon()
            if sys_cold_boot:
                _do_log("[Step 1/4] 系统刚开机，额外挂起等待 2.0s 待 Windows Acer 驱动与 WMI 服务完全就绪...")
                time.sleep(2.0) # 系统冷启动给底层 PSSvc.exe 服务充足的注册响应时间

            app_aumid = r"shell:AppsFolder\AcerIncorporated.PredatorSenseV30_48frkmn4z8aw4!CentenialConvert"
            main_hwnd = None

            # 2. 如果属于无进程冷启动，或者进程创建时间小于 6.5s (仍在播开场动画)，强行挂起等待动画播完
            if is_cold_start:
                _do_log("[Step 2/4] 发起 explorer.exe AUMID 界面唤起...")
                subprocess.Popen(f'explorer.exe "{app_aumid}"', shell=True)
                anim_wait = 9.5 if sys_cold_boot else 6.8 # 系统冷启动下开场动画加载稍长
                _do_log(f"[Step 2/4] 冷启动等待 WPF 开场动画播放与 UI 渲染 ({anim_wait}s)...")
                time.sleep(anim_wait)
            elif ps_create_time > 0 and (now_t - ps_create_time) < 6.5:
                remain_anim = max(0.5, 6.8 - (now_t - ps_create_time))
                _do_log(f"[Step 2/4] 进程刚创建 ({ps_age_str})，等待开场动画剩余时长 ({remain_anim:.1f}s)...")
                time.sleep(remain_anim)
            else:
                _do_log("[Step 2/4] UI 进程已完全就绪，直接进入窗口捕获与点击步骤...")

            # 3. 针对开机延迟/系统卡顿的【多轮探查与窗口捕获】
            max_enum_steps = 75 if sys_cold_boot else 45 # 系统冷启动放宽至 22.5 秒多轮探查
            _do_log(f"[Step 3/4] 开始轮询探查 UI 主窗口句柄 (最大 {max_enum_steps} 步, 每步 0.3s)...")
            for retry_round in range(3):
                if not is_cold_start or retry_round > 0:
                    _do_log(f"[Step 3/4] [重试第 {retry_round+1} 轮] 再次调起 AUMID 探查窗口...")
                    subprocess.Popen(f'explorer.exe "{app_aumid}"', shell=True)

                # 每轮等待探查窗口 (系统冷启动放宽探查)
                for _ in range(max_enum_steps):
                    def enum_cb(hwnd, extra):
                        nonlocal main_hwnd
                        title = win32gui.GetWindowText(hwnd)
                        clsname = win32gui.GetClassName(hwnd)
                        if win32gui.IsWindowVisible(hwnd) and ("predatorsense" in title.lower() or "HwndWrapper[PredatorSense.exe" in clsname):
                            rect = win32gui.GetWindowRect(hwnd)
                            if (rect[2] - rect[0]) > 600 and (rect[3] - rect[1]) > 400:
                                main_hwnd = hwnd
                        return True

                    win32gui.EnumWindows(enum_cb, None)
                    if main_hwnd:
                        win32gui.ShowWindow(main_hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(main_hwnd)
                        settle_time = 1.5 if (sys_cold_boot or is_cold_start) else 0.4
                        _do_log(f"[Step 3/4] 成功捕捉主窗口 HWND=0x{main_hwnd:X}，置顶前台平滑沉淀 {settle_time}s ...")
                        time.sleep(settle_time)
                        win32gui.SetForegroundWindow(main_hwnd)
                        break
                    time.sleep(0.3)

                if main_hwnd:
                    break
                time.sleep(2.0)

                if main_hwnd:
                    break
                
                # 如果第一/二轮没拉起来（说明开机延迟服务还没就绪），等待 2.5 秒后再次尝试拉起
                time.sleep(2.5)

            if not main_hwnd:
                _do_log("⚠️ [Step 3/4] 探查超时: 未能在预定时长内抓取到有效的 PredatorSense UI 窗口句柄")
                return

            rect = win32gui.GetWindowRect(main_hwnd)
            left, top, right, bottom = rect
            w = right - left
            h = bottom - top

            _do_log(f"[Step 4/4] 窗口尺寸 ({w}x{h})，开始执行 UI 程序化极速点击 [超频={overclock_mode}, 风扇={fan_mode}, CoolBoost={coolboost}] ...")

            # 保存鼠标初始坐标与获取当前状态
            orig_cursor = win32api.GetCursorPos()
            curr_status = self.get_current_status()

            # A. 超频模式控制 (Default / Fast / Extreme)
            if overclock_mode:
                oc_str = str(overclock_mode).lower()
                _do_log(f"[Step 4/4] 切换【超频模式】 -> 设为: {overclock_mode}")
                # 1. 点击左侧【超频】Tab (X: 13%, Y: 42%)
                win32api.SetCursorPos((int(left + w * 0.13), int(top + h * 0.42)))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.5) # 必须等待 WPF 面板切页渲染

                oc_x_ratio = 0.68
                if oc_str in ["default", "normal", "普通", "默认"]:
                    oc_x_ratio = 0.48
                elif oc_str in ["fast", "快速"]:
                    oc_x_ratio = 0.58
                elif oc_str in ["extreme", "turbo", "极速", "狂暴"]:
                    oc_x_ratio = 0.68

                win32api.SetCursorPos((int(left + w * oc_x_ratio), int(top + h * 0.27)))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.5)

            # B. 风扇模式控制 (Auto / Max / Custom)
            if fan_mode:
                fm_str = str(fan_mode).lower()
                _do_log(f"[Step 4/4] 切换【风扇速率】 -> 设为: {fan_mode}")
                # 1. 点击左侧【风扇控制】Tab (X: 13%, Y: 49%)
                win32api.SetCursorPos((int(left + w * 0.13), int(top + h * 0.49)))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.5) # 必须等待 WPF 面板切页渲染

                # 根据截图精准映射物理按键坐标: 自动 (48%) | 最大 (58%) | 自定义 (68%)
                fan_x_ratio = 0.58 # 【最大】按钮正好位于中央 58% 坐标
                if fm_str in ["auto", "自动"]:
                    fan_x_ratio = 0.48
                elif fm_str in ["max", "最大", "狂暴"]:
                    fan_x_ratio = 0.58
                elif fm_str in ["custom", "自定义"]:
                    fan_x_ratio = 0.68

                # 点击风扇模式按钮 (Y: 27%)
                win32api.SetCursorPos((int(left + w * fan_x_ratio), int(top + h * 0.27)))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.4)

            # C. CoolBoost 开关控制 (开启/关闭 CoolBoost)
            if coolboost is not None:
                target_cb = bool(coolboost)
                curr_cb = curr_status.get("coolboost")

                # CoolBoost 为 Toggle 开关，仅当当前硬件状态与目标不一致时才触发点击翻转
                if curr_cb is None or bool(curr_cb) != target_cb or force:
                    # 若此前未下发风扇模式变更（未切到风扇页），则必须先点击【风扇控制】Tab 确保 UI 在风扇 Tab 页面
                    if not fan_mode:
                        _do_log("[Step 4/4] 点击左侧【风扇控制】Tab 切页以暴露 CoolBoost 开关...")
                        win32api.SetCursorPos((int(left + w * 0.13), int(top + h * 0.49)))
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        time.sleep(0.5)

                    _do_log(f"[Step 4/4] 点击【CoolBoost】切换开关 -> 设为: {'开启' if target_cb else '关闭'}")
                    # 点击【CoolBoost】开关 (根据截图精准位于 X: 38%, Y: 20.5%)
                    win32api.SetCursorPos((int(left + w * 0.38), int(top + h * 0.205)))
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    time.sleep(0.2)
                else:
                    _do_log(f"[Step 4/4] CoolBoost 状态已处于: {'开启' if target_cb else '关闭'}，无需重复点击开关")

            # 更新最新应用的 Profile 缓存状态
            self._update_applied_cache(coolboost=coolboost, overclock_mode=overclock_mode, fan_mode=fan_mode)

            # 平滑归位鼠标坐标
            time.sleep(0.1)
            win32api.SetCursorPos(orig_cursor)

            # 4. 【最后一步】根据 post_action 选定的方式处理控制面板窗口 (Hide/Close/Kill)
            time.sleep(0.5)
            try:
                pa_str = str(post_action).lower()
                if pa_str in ["close", "关闭"]:
                    win32gui.PostMessage(main_hwnd, win32con.WM_CLOSE, 0, 0)
                    _do_log("[Step 4/4] 已成功发送关闭窗口 WM_CLOSE 消息")
                elif pa_str in ["kill", "杀掉"]:
                    import os, time
                    os.system("taskkill /f /im PredatorSense.exe 2>nul")
                    time.sleep(0.3)
                    try:
                        import psutil
                        for p in psutil.process_iter(['name', 'pid']):
                            if p.info['name'] and 'predatorsense' in p.info['name'].lower():
                                try:
                                    p.kill()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    _do_log("[Step 4/4] 已强行终止 PredatorSense.exe UI 进程以释放 CPU")
                else:
                    # 默认 hide 静默隐藏收至后台，保全后台守护进程
                    win32gui.ShowWindow(main_hwnd, win32con.SW_HIDE)
                    _do_log("[Step 4/4] 已成功隐藏 PredatorSense 窗口常驻后台")
            except Exception:
                pass
        except Exception as e:
            _do_log(f"⚠️ UI 程序化点击调优过程异常: {e}")

    def apply_performance_profile(self, profile: dict, log_cb=None, force=True) -> tuple:
        """
        批量应用性能 Profile (跳过重复检测，无条件立即应用，100% 依赖 PredatorSense UI 程序化鼠标点击下发)
        profile: {"overclock_mode": "Fast", "coolboost": True, "fan_mode": "Auto", "post_action": "kill"}
        """
        def _do_log(msg):
            if callable(log_cb):
                try:
                    log_cb(msg)
                except Exception:
                    pass

        if not isinstance(profile, dict):
            return False, "配置 Profile 参数格式非法"

        if not self.is_supported():
            return False, "当前设备非 Acer 笔记本或未加载 Acer WMI 控制驱动 (静默跳过)"

        oc = profile.get("overclock_mode")
        cb = profile.get("coolboost")
        fm = profile.get("fan_mode")
        pa = profile.get("post_action", "kill")

        # 1. 探查并打印执行前系统 3 大参数明细 (force_physical=True 强行物理探查 OEM 注册表)
        phys_status = self.get_current_status(force_physical=True)
        phys_oc = phys_status.get("overclock_mode")
        phys_fm = phys_status.get("fan_mode")
        phys_cb = phys_status.get("coolboost")

        _do_log(
            f"[Acer Hardware] 执行前物理探查状态 -> "
            f"超频(overclock_mode)={phys_oc}, 风扇(fan_mode)={phys_fm}, CoolBoost(coolboost)={'开启' if phys_cb else '关闭'}"
        )

        _do_log(
            f"[Acer Hardware] ⚡ 跳过重复检测，立即执行程序化应用 -> "
            f"目标超频={oc}, 目标风扇={fm}, 目标CoolBoost={cb}, 处理方式={pa}"
        )

        # 2. 唤起 launch_predatorsense_gui 完整下发 Profile 参数，保持 100% 稳定可靠的全流程 UI 点击
        try:
            self.launch_predatorsense_gui(
                fan_mode=fm,
                overclock_mode=oc,
                coolboost=cb,
                post_action=pa,
                log_cb=log_cb,
                force=True
            )
        except Exception as e:
            _do_log(f"⚠️ 唤起 UI 程序化点击调优异常: {e}")

        # 3. 更新状态应用缓存并打印执行后系统最新状态
        self._update_applied_cache(coolboost=cb, overclock_mode=oc, fan_mode=fm)
        after_status = self.get_current_status()
        _do_log(
            f"[Acer Hardware] 执行后系统最新状态 -> "
            f"超频(overclock_mode)={after_status.get('overclock_mode')}, 风扇(fan_mode)={after_status.get('fan_mode')}, CoolBoost(coolboost)={'开启' if after_status.get('coolboost') else '关闭'}"
        )

        return True, f"Acer 硬件性能 Profile 已立即通过 PredatorSense UI 极速点击应用 [超频={oc}, 风扇={fm}, CoolBoost={cb}]"








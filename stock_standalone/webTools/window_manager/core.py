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


def get_window_rect(hwnd) -> tuple:
    """获取窗口在屏幕上的实际像素边界(left, top, width, height)"""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.pointer(rect))
    left = rect.left
    top = rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (left, top, width, height)


def get_screen_resolution_summary() -> dict:
    """
    通过 screeninfo 及 win32 获取显示器配置汇总
    返回结构: { "total_width": int, "primary_res": str, "monitors": list, "display_num": int }
    """
    summary = {
        "total_width": 0,
        "primary_res": "1920x1080",
        "monitors": [],
        "display_num": 0
    }
    
    try:
        monitors = get_monitors()
        summary["display_num"] = len(monitors)
        for i, m in enumerate(monitors):
            summary["monitors"].append({
                "index": i + 1,
                "name": m.name,
                "width": m.width,
                "height": m.height,
                "x": m.x,
                "y": m.y,
                "is_primary": m.is_primary
            })
            summary["total_width"] += m.width
            if m.is_primary:
                summary["primary_res"] = f"{m.width}x{m.height}"
    except Exception as e:
        # 回退：如果没有屏幕信息或读取出错
        summary["display_num"] = 1
        summary["total_width"] = user32.GetSystemMetrics(0) # SM_CXSCREEN
        summary["primary_res"] = f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}"
        summary["monitors"].append({
            "index": 1,
            "name": "Primary",
            "width": user32.GetSystemMetrics(0),
            "height": user32.GetSystemMetrics(1),
            "x": 0,
            "y": 0,
            "is_primary": True
        })
    return summary


def detect_display_config_name() -> str:
    """
    使用内置与外部逻辑探测出当前系统应匹配的配置名(如: tdx_ths_position1920)
    """
    if Display_Detection is not None:
        try:
            displaySet = Display_Detection()
            displayNum = displaySet[0]
            displayMainRes = displaySet[1][0]
            
            # 获取当前系统的物理 DPI 缩放比例
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
                ctypes.windll.user32.ReleaseDC(0, hdc)
                scale = dpi_x / 96.0
            except Exception:
                scale = 1.0

            if displayNum > 1:
                displayRes = 0 
                for i in range(1, displayNum + 1):
                    val = displaySet[i][0]
                    # displaySet[2] 为主屏幕，受 DPI 缩放影响，因此在高 DPI-aware 进程下需要缩放折合
                    if i == 2 and scale > 1.0:
                        val = int(val / scale)
                    displayRes += val
                
                if 3800 < displayRes < 4700:
                    displayRes = 4644
                elif displayRes >= 4700:
                    displayRes = 5376
                return f'tdx_ths_position{displayRes}'
            else:
                # 单屏也支持逻辑像素折合，使 UI 与 CLI 保持一致
                if scale > 1.0:
                    displayMainRes = int(displayMainRes / scale)
                return f'tdx_ths_position{displayMainRes}'
        except Exception:
            pass

    # 无法调用 Display_Detection 时的原生回退逻辑
    summary = get_screen_resolution_summary()
    if summary["display_num"] > 1:
        # 双屏/多屏
        total_w = summary["total_width"]
        if 3800 < total_w < 4700:
            total_w = 4644
        elif total_w > 4700:
            total_w = 5376
        # 如果总宽度不是典型值，可默认回退到 Double 或者是总宽度
        if total_w in [4644, 5376]:
            return f'tdx_ths_position{total_w}'
        else:
            return 'tdx_ths_positionDouble'
    else:
        # 单屏
        mon = summary["monitors"][0] if summary["monitors"] else None
        res_w = mon["width"] if mon else 1920
        # 兼容一些非标 DPI 的主分辨率名称
        return f'tdx_ths_position{res_w}'


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
                        left, top, width, height = get_window_rect(hWnd)
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
        if user32.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            if pattern.search(window_title):
                found.append((hwnd, window_title))
        return True
        
    win32gui.EnumWindows(enum_handler, None)
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


def set_window_hwnd_pos(hwnd, pos_str: str):
    """
    通过 'x,y,width,height' 格式的字符串直接设置指定句柄的窗口位置与大小
    """
    try:
        parts = [int(p.strip()) for p in pos_str.split(',')]
        if len(parts) == 4:
            x, y, width, height = parts
            # 先重置为普通窗口，以防窗口处于最小化或最大化状态导致无法移动
            # 并移动位置
            ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1) # SWP_NOSIZE = 1
            # 设定窗口大小
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 2) # SWP_NOMOVE = 2
            return True
    except Exception as e:
        print(f"Error setting window pos for HWND {hwnd}: {e}")
    return False


def set_window_pos_by_title(target_title: str, pos_str: str, show_cmd=SW_SHOWNORMAL) -> bool:
    """
    模糊匹配窗口标题，并将其移动到指定位置。
    如果窗口处于最小化状态，则会自动执行 show_cmd 还原窗口。
    """
    found = find_windows_by_title_safe(target_title)
    if not found:
        return False
        
    success = False
    for hwnd, title in found:
        # 检测窗口是否被隐藏或最小化
        left, top, width, height = get_window_rect(hwnd)
        if left < -10000 and top < -10000:
            user32.ShowWindow(hwnd, show_cmd)
            time.sleep(0.1)
            
        if set_window_hwnd_pos(hwnd, pos_str):
            success = True
            
        if show_cmd != SW_SHOWNORMAL:
            user32.ShowWindow(hwnd, show_cmd)
            
    return success


def get_app_root() -> str:
    """获取程序物理根目录。独立于 sys_utils，避免加载无关依赖。"""
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        return env_root

    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        calculated_root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 对应本地开发环境项目根目录 (webTools/window_manager 的上上级)
        calculated_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    os.environ["INSTOCK_APP_ROOT"] = calculated_root
    return calculated_root


def get_conf_path(fname: str) -> str:
    """
    获取并加载配置文件的路径，支持从内置资源包自愈释放。
    """
    app_root = get_app_root()
    dst_path = os.path.join(app_root, fname)

    if not os.path.exists(dst_path):
        # 找到内置释放目录
        base = getattr(sys, "_MEIPASS", None)
        if not base and "NUITKA_ONEFILE_DIRECTORY" in os.environ:
            base = os.environ["NUITKA_ONEFILE_DIRECTORY"]
        if not base:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # window_layout_config.json 在内置包中位于 webTools/window_manager/ 目录下
        src_path = os.path.join(base, "webTools", "window_manager", fname)
        if not os.path.exists(src_path):
            src_path = os.path.join(base, fname)

        if os.path.exists(src_path):
            try:
                import shutil
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy(src_path, dst_path)
            except Exception as e:
                print(f"[自愈] 释放配置文件失败: {e}", file=sys.stderr)

    return dst_path


class ConfigManager:
    """管理分类持久化的 JSON 配置"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_conf_path("window_layout_config.json")
        self.config_path = config_path
        self.config_data = {}
        self.load()

    def load(self):
        """从文件读取 JSON 配置"""
        loaded = False
        # 优先尝试读取磁盘上的持久化配置文件
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config_data = json.load(f)
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
        """保存当前内存中的配置到文件"""
        try:
            # 确保物理持久化文件夹存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Failed to save config to {self.config_path}: {e}")
            return False

    def get_categories(self) -> list:
        """获取所有分类"""
        return ["single_display", "multi_display", "custom_special"]

    def get_resolutions_by_category(self, category: str) -> list:
        """获取特定分类下的所有方案名"""
        if category in self.config_data:
            return sorted(list(self.config_data[category].keys()))
        return []

    def get_resolutions(self) -> list:
        """获取所有可用分辨率配置方案的名称（扁平列表）"""
        res_list = []
        for cat in self.get_categories():
            res_list.extend(self.get_resolutions_by_category(cat))
        return sorted(list(set(res_list)))

    def get_category_of_resolution(self, res_name: str) -> str:
        """判断一个方案名属于哪个分类"""
        for cat in self.get_categories():
            if res_name in self.config_data[cat]:
                return cat
        return "custom_special" # 默认分类

    def get_resolution_mapping(self, res_name: str) -> dict:
        """获取指定分辨率配置的窗口坐标映射表"""
        for cat in self.get_categories():
            if res_name in self.config_data.get(cat, {}):
                return self.config_data[cat][res_name]
        return {}

    def set_resolution_mapping(self, res_name: str, mapping: dict, category: str = None):
        """更新指定分辨率的配置"""
        if not category:
            category = self.get_category_of_resolution(res_name)
            
        # 确保分类存在
        if category not in self.config_data:
            self.config_data[category] = {}
            
        # 如果该配置在其他分类中也存在，先删掉，避免重复
        for cat in self.get_categories():
            if cat != category and res_name in self.config_data[cat]:
                del self.config_data[cat][res_name]
                
        self.config_data[category][res_name] = mapping
        
    def delete_resolution(self, res_name: str):
        """删除某个分辨率的配置"""
        for cat in self.get_categories():
            if res_name in self.config_data.get(cat, {}):
                del self.config_data[cat][res_name]


def apply_layout_config(config_manager: ConfigManager, res_name: str, show_cmd=SW_SHOWNORMAL):
    """
    根据给定的配置段名称，一键应用其所有的窗口位置设定
    """
    mapping = config_manager.get_resolution_mapping(res_name)
    if not mapping:
        print(f"No configuration mapping found for: {res_name}")
        return False
        
    print(f"Applying layout for: {res_name}")
    for title, pos_str in mapping.items():
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

def get_monitor_details_all_with_scale():
    """
    获取所有显示器信息，同时计算 scale（DPI缩放）
    - 主显示器排在最前
    - 返回 monitors 列表 + 汇总字符串
    """
    # 强制设置进程级 DPI 意识，保证逻辑和物理分辨率检测结果在命令行与 UI 模式下完全对齐一致
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # 尝试加载 GetDpiForMonitor 获取底层真实的物理缩放率
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

    monitor_handles = win32api.EnumDisplayMonitors()
    if not monitor_handles:
        return {"monitors": [], "summary": "0"}

    monitors = []
    for handle_tuple in monitor_handles:
        monitor_handle = handle_tuple[0]

        # 逻辑分辨率（系统显示逻辑）
        try:
            info = win32api.GetMonitorInfo(monitor_handle)
            device_name = info.get("Device", "Unknown")
            is_primary = (info.get("Flags", 0) & win32con.MONITORINFOF_PRIMARY) != 0
            left, top, right, bottom = info["Monitor"]
            logical_width = right - left
            logical_height = bottom - top

            # 物理分辨率（实际设置）
            devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
            physical_width = devmode.PelsWidth
            physical_height = devmode.PelsHeight

            # 优先使用 GetDpiForMonitor 获取真实的物理 DPI 缩放值
            scale = None
            if shcore is not None:
                try:
                    dpi_x = ctypes.c_uint()
                    dpi_y = ctypes.c_uint()
                    # 0 代表 MDT_EFFECTIVE_DPI
                    res = shcore.GetDpiForMonitor(int(monitor_handle), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                    if res == 0: # S_OK
                        scale = round(dpi_x.value / 96.0, 2)
                except Exception:
                    pass

            # Fallback 策略：如果 API 获取失败，则采用逻辑/物理分辨率估算
            if scale is None:
                scale_x = physical_width / logical_width if logical_width else 1.0
                scale_y = physical_height / logical_height if logical_height else 1.0
                scale = round((scale_x + scale_y) / 2, 2)

            # 在高 DPI 意识进程中，GetMonitorInfo 得到的 logical_width 可能退化成物理像素。
            # 为了反映操作系统实际缩放的逻辑分辨率，在这里根据真实 scale 进行修正折算。
            real_logical_width = int(physical_width / scale) if scale else logical_width
            real_logical_height = int(physical_height / scale) if scale else logical_height

            monitors.append({
                "device_name": device_name,
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

    # 主显示器排前
    monitors.sort(key=lambda x: not x["is_primary"])

    # 汇总字符串，用于区分不同显示器组合下的持久化文件命名
    summary = "_".join(f"{m['width']}x{m['height']}@{m['scale']}" for m in monitors)
    return {"monitors": monitors, "summary": summary}


def is_same_display_config(current, saved):
    """
    判断当前显示器配置与已保存配置是否一致
    支持逻辑分辨率 + scale 自动匹配
    """
    if len(current) != len(saved):
        return False

    def build_key(m):
        return m.get("device_name") or (m.get("logical_width"), m.get("logical_height"), m.get("scale"))

    cur_map = {build_key(m): m for m in current}
    sav_map = {build_key(m): m for m in saved}

    if cur_map.keys() != sav_map.keys():
        return False

    fields = ("width", "height", "x", "y", "is_primary", "scale", "logical_width", "logical_height")
    for key, cur in cur_map.items():
        if key not in sav_map:
            return False
        sav = sav_map[key]
        for f in fields:
            if cur.get(f) != sav.get(f):
                return False
    return True


def save_display_configuration(filename="display_config.json") -> tuple:
    """
    保存当前显示器物理拓扑排布到 JSON 文件中（由显示器组合签名区分）
    """
    try:
        config = get_monitor_details_all_with_scale()
        if not config or not config["monitors"]:
            return False, "未检测到有效的显示器数据"

        summary = config["summary"]
        file_key = f"{summary}_monitor{filename}"
        
        out_filename = get_conf_path(file_key)
        
        with open(out_filename, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True, out_filename
    except Exception as e:
        return False, str(e)


def restore_display_configuration(filename="display_config.json") -> tuple:
    """
    读取并恢复显示器排列设置。
    """
    try:
        monitor_info = get_monitor_details_all_with_scale()
        if not monitor_info or not monitor_info["monitors"]:
            return False, "未检测到当前连接的显示器"

        summary = monitor_info["summary"]
        current_monitors = monitor_info["monitors"]
        file_key = f"{summary}_monitor{filename}"
        
        in_filename = get_conf_path(file_key)

        if not os.path.exists(in_filename):
            # 自动保存当前作为默认
            save_display_configuration(filename)
            return False, f"未找到屏幕组合备份: {in_filename}，已将当前排布存为默认备份"

        with open(in_filename, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

        save_monitors = saved_config["monitors"]
        if is_same_display_config(current_monitors, save_monitors):
            return True, "当前屏幕物理排布与备份完全一致，跳过恢复"

        # 执行 Windows 物理拓扑与排布坐标更改
        for monitor in save_monitors:
            device_name = monitor["device_name"]
            try:
                devmode = win32api.EnumDisplaySettings(device_name, win32con.ENUM_CURRENT_SETTINGS)
                devmode.PelsWidth = monitor["width"]
                devmode.PelsHeight = monitor["height"]
                devmode.Position_x = monitor["x"]
                devmode.Position_y = monitor["y"]

                if monitor["is_primary"]:
                    flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET | win32con.CDS_SET_PRIMARY
                else:
                    flags = win32con.CDS_UPDATEREGISTRY | win32con.CDS_NORESET

                win32api.ChangeDisplaySettingsEx(device_name, devmode, flags)
            except pywintypes.error as ex:
                return False, f"设置显示器 '{device_name}' 排布失败: {ex}"

        # 最终应用全部变更并触发系统广播
        win32api.ChangeDisplaySettings(None, 0)
        return True, f"已恢复多屏幕排布，配置包: {in_filename}"
    except Exception as e:
        return False, f"恢复多显示器排布时出错: {e}"


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

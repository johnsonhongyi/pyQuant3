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


def detect_display_config_name(config_manager=None) -> str:
    """
    使用内置与外部逻辑探测出当前系统应匹配的配置名(如: tdx_ths_position1920, tdx_ths_position3840)
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

    if Display_Detection is not None:
        try:
            displaySet = Display_Detection()
            displayNum = displaySet[0]
            displayMainRes = displaySet[1][0]
            rawMainRes = displayMainRes
            
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
                    if i == 2 and scale > 1.0:
                        val = int(val / scale)
                    displayRes += val
                
                if 3800 < displayRes < 4700:
                    displayRes = 4644
                elif displayRes >= 4700:
                    displayRes = 5376
                target_key = f'tdx_ths_position{displayRes}'
                return target_key
            else:
                # 优先匹配无缩放折合的物理分辨率名称（如 3840 对应 tdx_ths_position3840）
                raw_key = f'tdx_ths_position{rawMainRes}'
                if raw_key in existing_keys:
                    return raw_key
                
                # 如果没有精确物理方案，再尝试逻辑像素折合
                if scale > 1.0:
                    scaled_res = int(displayMainRes / scale)
                    scaled_key = f'tdx_ths_position{scaled_res}'
                    if scaled_key in existing_keys:
                        return scaled_key
                return raw_key
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
        if total_w in [4644, 5376]:
            return f'tdx_ths_position{total_w}'
        else:
            return 'tdx_ths_positionDouble'
    else:
        # 单屏
        mon = summary["monitors"][0] if summary["monitors"] else None
        res_w = mon["width"] if mon else 1920
        raw_key = f'tdx_ths_position{res_w}'
        if raw_key in existing_keys or not existing_keys:
            return raw_key
        return f'tdx_ths_position{res_w}'


def normalize_docked_window_rect(left: int, top: int, width: int, height: int) -> tuple:
    """
    检查窗口矩形是否处于磁吸贴边隐藏折叠状态。
    如果是折叠隐藏状态（大部分在屏幕外，只露出一小条感应边框），自动反向推算出其展开时的标准正常矩形 (left, top, width, height)。
    """
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

            # 判断当前窗口大部分是否处于这个显示器的边缘折叠
            # 1. 右侧贴边隐藏 (left 贴近右边界，大部分在屏幕外)
            if left > m_right - 50 and left < m_right + 50:
                right = left + width
                if right > m_right:
                    norm_left = m_right - width
                    return norm_left, top, width, height

            # 2. 左侧贴边隐藏 (right 贴近左边界，大部分在屏幕外)
            right = left + width
            if right > mx - 50 and right < mx + 50:
                if left < mx:
                    norm_left = mx
                    return norm_left, top, width, height

            # 3. 顶部贴边隐藏 (bottom 贴近上边界，大部分在屏幕外)
            bottom = top + height
            if bottom > my - 50 and bottom < my + 50:
                if top < my:
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
                        # 核心修复：如果是磁吸贴边隐藏窗口，自动反向推算出其展开状态时的真实 Geometry
                        left, top, width, height = normalize_docked_window_rect(raw_left, raw_top, width, height)
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
            
            # 核心自适应：反向推算与自动纠偏！如果传入的 pos_str 本身是记录的侧边折叠隐藏超界坐标 (如 1915)，
            # 自动将其归一化为磁吸前的正常显示物理坐标 (如 1320)，彻底杜绝应用布局时把窗口扔进屏幕外悬空！
            x, y, width, height = normalize_docked_window_rect(x, y, width, height)

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
    如果窗口处于最小化或磁吸隐藏状态，会自动先执行显示/还原，确保应用布局到磁吸前的正常位置，之后允许窗口自发触发磁吸。
    """
    found = find_windows_by_title_safe(target_title)
    if not found:
        return False
        
    success = False
    for hwnd, title in found:
        # 提取当前物理坐标
        left, top, width, height = get_window_rect(hwnd)
        
        # 1. 检测窗口是否处于最小化 (left/top < -10000) 或 贴边折叠隐藏状态 (主体超界到屏幕外侧)
        is_docked_hidden = False
        if left < -10000 and top < -10000:
            is_docked_hidden = True
        else:
            try:
                monitors_info = get_monitor_details_all_with_scale()
                for mon in monitors_info.get("monitors", []):
                    mx = mon.get("x", 0)
                    mw = mon.get("logical_width", mon.get("width", 1920))
                    m_right = mx + mw
                    if (left > m_right - 40 and left < m_right + 50) or (left + width > mx - 50 and left + width < mx + 40):
                        is_docked_hidden = True
                        break
            except Exception:
                pass

        if is_docked_hidden:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE 强制恢复显示展开态
            time.sleep(0.05)
            
        if set_window_hwnd_pos(hwnd, pos_str):
            success = True
            
        if show_cmd != SW_SHOWNORMAL:
            user32.ShowWindow(hwnd, show_cmd)
            
    return success


def get_app_root() -> str:
    """获取程序物理根目录。"""

    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        return env_root

    is_frozen = getattr(sys, "frozen", False)
    is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version")
    
    if is_frozen or is_nuitka:
        calculated_root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 对应本地开发环境项目根目录 (webTools/window_manager 的上上级)
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


def check_and_add_route(config_manager) -> tuple:
    """
    检查并自动添加静态路由配置。
    返回 (success: bool, message: str)
    """
    routing_cfg = config_manager.config_data.get("routing_config")
    if not routing_cfg:
        # 默认值初始化
        routing_cfg = {
            "enabled": True,
            "destination": "192.168.50.0",
            "mask": "255.255.255.0",
            "gateway": "192.168.1.2"
        }
        config_manager.config_data["routing_config"] = routing_cfg
        config_manager.save()

    if not routing_cfg.get("enabled", True):
        return True, "自动路由功能未启用。"

    dest = routing_cfg.get("destination", "192.168.50.0")
    mask = routing_cfg.get("mask", "255.255.255.0")
    gw = routing_cfg.get("gateway", "192.168.1.2")

    import subprocess
    try:
        # 在 Windows 上，检测是否存在该网段的路由
        check_cmd = "route print -4"
        res = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, errors='ignore')
        
        # 精确正则匹配网络目标和网关，以防误判
        pattern = rf"\b{re.escape(dest)}\b"
        if re.search(pattern, res.stdout):
            if gw in res.stdout:
                return True, f"到 {dest} via {gw} 的静态路由已存在，无需添加。"
                
        # 路由不存在或网关不同，尝试添加。首先检测当前是否已具有管理员权限
        is_admin = False
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            pass

        if is_admin:
            add_cmd = f"route add {dest} mask {mask} {gw}"
            add_res = subprocess.run(add_cmd, shell=True, capture_output=True, text=True, encoding='gbk', errors='ignore')
            if add_res.returncode == 0:
                return True, f"已成功自动添加静态路由: {dest} mask {mask} {gw}"
            else:
                err_msg = add_res.stderr.strip() or add_res.stdout.strip()
                return False, f"添加路由失败 (返回码 {add_res.returncode}): {err_msg}"
        else:
            # 没有管理员权限，通过 ShellExecuteW "runas" 弹出 UAC 请求提权运行
            try:
                params = f"/c route add {dest} mask {mask} {gw}"
                # SW_HIDE = 0 隐藏弹出的黑窗口
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "cmd.exe",
                    params,
                    None,
                    0
                )
                # ShellExecuteW 成功返回值大于 32
                if ret > 32:
                    # 稍微等待 0.5s 让系统完成路由表写入，然后重新用 route print 检测
                    time.sleep(0.5)
                    check_cmd = "route print -4"
                    res = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, errors='ignore')
                    if re.search(pattern, res.stdout) and gw in res.stdout:
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
    检查 manage_window_layout.exe 或 manage_window_layout.py 是否已经在运行。
    如果已经运行，通过 QLocalSocket 管道发送 WAKEUP 消息并结合 Win32 接口唤醒已有窗口到前台显示，并返回 True（指示调用方退出）；
    如果未在运行，返回 False（指示可以继续正常启动新实例）。
    """
    current_pid = os.getpid()
    parent_pid = os.getppid() if hasattr(os, 'getppid') else None
    ipc_connected = False

    # 1. 尝试使用 Qt 的 QLocalSocket 连接已存主 UI 的 IPC 本地命名管道服务
    try:
        from PyQt6.QtNetwork import QLocalSocket
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
        if socket.waitForConnected(300):
            print("[SingleInstance] 成功连接至已有实例的 IPC 服务，发送 WAKEUP 指令...")
            socket.write(b"WAKEUP\n")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            ipc_connected = True
    except Exception as e:
        print(f"[SingleInstance] QLocalSocket IPC 握手异常: {e}")

    target_hwnds = []

    # 2. 枚举桌面所有窗口，寻找目标标题的 HWND 句柄
    def enum_windows_callback(hwnd, lparam):
        if not user32.IsWindow(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == current_pid or (parent_pid and pid.value == parent_pid) or pid.value == 0:
            return True

        try:
            title = win32gui.GetWindowText(hwnd)
            if title:
                if "窗口坐标分类管理器" in title or "桌面窗口坐标布局" in title:
                    target_hwnds.append((hwnd, pid.value, title))
        except Exception:
            pass
        return True

    try:
        proc = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(proc, 0)
    except Exception as e:
        print(f"[SingleInstance] EnumWindows 扫描异常: {e}")

    # 3. 扫描后台进程是否存在已存的 manage_window_layout 实例
    other_pids = set()

    if not target_hwnds:
        try:
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    p_pid = p.info['pid']
                    if p_pid == current_pid or (parent_pid and p_pid == parent_pid) or p_pid == 0:
                        continue

                    p_name = (p.info['name'] or '').lower()
                    cmd_str = ''
                    try:
                        p_cmdline = p.cmdline() or []
                        cmd_str = ' '.join(p_cmdline).lower()
                    except Exception:
                        pass

                    is_target_proc = False
                    if p_name == 'manage_window_layout.exe':
                        is_target_proc = True
                    elif 'manage_window_layout.py' in cmd_str:
                        is_target_proc = True

                    if is_target_proc:
                        other_pids.add(p_pid)
                except Exception:
                    continue
        except Exception as e:
            print(f"[SingleInstance] psutil 进程扫描异常: {e}")

        if other_pids:
            def enum_pid_windows_callback(hwnd, lparam):
                if not user32.IsWindow(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in other_pids:
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        target_hwnds.append((hwnd, pid.value, title))
                return True

            try:
                proc_pid = WNDENUMPROC(enum_pid_windows_callback)
                user32.EnumWindows(proc_pid, 0)
            except Exception:
                pass

    # 4. 如果成功通过 IPC 连接或找到了真实运行中的 UI 窗口句柄
    activated = False
    wm_msg_id = get_wm_show_msg_id()

    if target_hwnds:
        print("[SingleInstance] 检测到 manage_window_layout 已有 UI 实例运行，正在唤醒并拉起窗口到前台...")
        for hwnd, pid, title in target_hwnds:
            try:
                if user32.IsWindow(hwnd):
                    # 通过 Win32 API 广播/发送唤醒注册消息
                    if wm_msg_id:
                        user32.PostMessageW(hwnd, wm_msg_id, 0, 0)

                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    else:
                        user32.ShowWindow(hwnd, 5)  # SW_SHOW

                    user32.keybd_event(0x12, 0, 0, 0)  # Alt down
                    user32.SetForegroundWindow(hwnd)
                    user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt up
                    user32.BringWindowToTop(hwnd)
                    activated = True
            except Exception as e:
                print(f"[SingleInstance] 唤醒窗口 HWND {hwnd} 异常: {e}")

    # 仅当成功通过 IPC 唤醒 或 成功拉起前台 UI 窗口时，才指示调用方退出；避免无界面的僵尸进程死锁导致闪退
    if ipc_connected or activated:
        print("[SingleInstance] 成功唤醒已有主 UI 实例，阻止重复启动新实例。")
        return True

    return False





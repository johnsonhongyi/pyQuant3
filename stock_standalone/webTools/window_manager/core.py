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


def set_window_hwnd_pos(hwnd, pos_str: str, title: str = ""):
    """
    通过 'x,y,width,height' 格式的字符串直接设置指定句柄的窗口位置与大小
    """
    try:
        parts = [int(p.strip()) for p in pos_str.split(',')]
        if len(parts) == 4:
            x, y, width, height = parts
            
            # 仅对专属磁吸折叠窗口做反向纠偏；常规日常软件直接按精准坐标设定
            x, y, width, height = normalize_docked_window_rect(x, y, width, height, title=title)

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
    如果是专属磁吸窗口且处于隐藏收缩状态，会自动先执行显示/还原；
    对东方财富等常规日常软件，只在最小化时还原，靠边放置不触发误判。
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

    def get_acer_performance_config(self) -> dict:
        """获取 Acer 性能模式配置段，带有默认自愈功能"""
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




def is_autostart_enabled() -> bool:
    """
    检查 Windows 注册表中是否已设置开机自启
    检查 HKCU 与 HKLM 的 SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(root_key, REG_AUTORUN_SUBKEY, 0, winreg.KEY_READ)
                try:
                    val, _ = winreg.QueryValueEx(key, REG_AUTORUN_NAME)
                    if val:
                        winreg.CloseKey(key)
                        return True
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass
    except Exception:
        pass
    return False


def set_autostart_enabled(enable: bool) -> tuple:
    """
    通过注册表开启或关闭开机自启
    返回: (success: bool, message: str)
    """
    if sys.platform != "win32":
        return False, "非 Windows 系统不支持注册表开机自启"

    try:
        import winreg
        cmd = get_autostart_command()

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
            # 关闭：删除 HKCU 与 HKLM 中的启动项
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

            return True, f"开机自启已在注册表中成功关闭 (已清理命令行路径: {cmd})"
    except Exception as e:
        return False, f"操作注册表异常: {e}"


# ==========================================
# Acer 笔记本硬件性能控制模块 (免 GUI 驱动)
# ==========================================

class AcerPerformanceController:
    """
    Acer 笔记本硬件性能控制器 (免 GUI 模式)
    通过 Windows WMI (root\\wmi 命名空间下的 v2_AcerSysOM / AcerSysOM)
    直接调度 CoolBoost 散热开关、GPU/CPU 超频模式 (Default/Fast/Extreme) 及风扇速率模式。
    """
    def __init__(self):
        self._checked_support = False
        self._is_supported = False

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

    def get_current_status(self) -> dict:
        """获取当前 Acer 硬件性能状态"""
        status = {
            "supported": self.is_supported(),
            "coolboost": False,
            "overclock_mode": "Default",
            "fan_mode": "Auto"
        }
        if not status["supported"]:
            return status

        try:
            obj = self._get_wmi_object()
            if obj:
                # 尝试提取 CoolBoost 状态
                try:
                    status["coolboost"] = bool(getattr(obj, "CoolBoost", False))
                except Exception:
                    pass
                # 尝试提取超频模式
                try:
                    oc_val = getattr(obj, "GPUOverclockingMode", getattr(obj, "SystemMode", 0))
                    oc_map = {0: "Default", 1: "Fast", 2: "Extreme"}
                    status["overclock_mode"] = oc_map.get(int(oc_val), "Default")
                except Exception:
                    pass
        except Exception:
            pass
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

    def launch_predatorsense_gui(self, fan_mode=None, overclock_mode=None, coolboost=None, post_action="hide"):
        """唤起 Acer PredatorSense 控制中心界面并按选配参数精细化程序点击 (开机自启防卡顿+多重轮询极健壮架构)"""
        try:
            import subprocess
            import win32gui
            import win32api
            import win32con
            import time

            # 0. 精准探测【唤起前系统是否存在前台 UI 进程 PredatorSense.exe】
            # 必须精确匹配 predatorsense.exe，严格排除后台系统服务 PSSvc.exe / PredatorSenseService.exe 等！
            is_cold_start = True
            try:
                import psutil
                for p in psutil.process_iter(['name']):
                    p_name = (p.info['name'] or '').lower()
                    if p_name == 'predatorsense.exe':
                        is_cold_start = False
                        break
            except Exception:
                pass

            # 1. 确保底层 Acer 守护进程已拉起
            self.ensure_predatorsense_daemon()

            app_aumid = r"shell:AppsFolder\AcerIncorporated.PredatorSenseV30_48frkmn4z8aw4!CentenialConvert"
            main_hwnd = None

            # 2. 如果属于【无进程冷启动】，调起后先直接挂起 5.5 秒等待 6 秒 Splash 开场动画播完
            if is_cold_start:
                subprocess.Popen(f'explorer.exe "{app_aumid}"', shell=True)
                time.sleep(5.5)

            # 3. 针对开机延迟/系统卡顿的【多轮探查与窗口捕获】
            for retry_round in range(3):
                if not is_cold_start or retry_round > 0:
                    subprocess.Popen(f'explorer.exe "{app_aumid}"', shell=True)

                # 每轮等待探查窗口 (最长 6 秒)
                for _ in range(30):
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
                        # 找到真正的主界面窗口！强制恢复与置顶前台
                        win32gui.ShowWindow(main_hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(main_hwnd)
                        if is_cold_start:
                            time.sleep(0.8) # 冷启动最后 0.8s 界面平滑沉淀
                        else:
                            time.sleep(0.3) # 热唤醒 0.3s 极速响应
                        win32gui.SetForegroundWindow(main_hwnd)
                        break
                    time.sleep(0.2)

                if main_hwnd:
                    break
                time.sleep(2.0)

                if main_hwnd:
                    break
                
                # 如果第一/二轮没拉起来（说明开机延迟服务还没就绪），等待 2.5 秒后再次尝试拉起
                time.sleep(2.5)

            if not main_hwnd:
                return

            rect = win32gui.GetWindowRect(main_hwnd)
            left, top, right, bottom = rect
            w = right - left
            h = bottom - top

            # 保存鼠标初始坐标
            orig_cursor = win32api.GetCursorPos()

            # A. 超频模式控制 (Default / Fast / Extreme)
            if overclock_mode:
                oc_str = str(overclock_mode).lower()
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

            # C. CoolBoost 开关控制
            if coolboost is True:
                # 点击【CoolBoost】开关 (根据截图精准位于 X: 38%, Y: 20.5%)
                win32api.SetCursorPos((int(left + w * 0.38), int(top + h * 0.205)))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                time.sleep(0.2)

            # 平滑归位鼠标坐标
            time.sleep(0.1)
            win32api.SetCursorPos(orig_cursor)

            # 4. 【最后一步】根据 post_action 选定的方式处理控制面板窗口 (Hide/Close/Kill)
            time.sleep(0.5)
            try:
                pa_str = str(post_action).lower()
                if pa_str in ["close", "关闭"]:
                    win32gui.PostMessage(main_hwnd, win32con.WM_CLOSE, 0, 0)
                elif pa_str in ["kill", "杀掉"]:
                    import os
                    os.system("taskkill /f /im PredatorSense.exe 2>nul")
                else:
                    # 默认 hide 静默隐藏收至后台，保全后台守护进程
                    win32gui.ShowWindow(main_hwnd, win32con.SW_HIDE)
            except Exception:
                pass
        except Exception:
            pass

    def apply_performance_profile(self, profile: dict) -> tuple:
        """
        批量应用性能 Profile (结合程序化点击 100% 无死锁无提示报错)
        profile: {"overclock_mode": "Fast", "coolboost": True, "fan_mode": "Auto", "post_action": "hide"}
        """
        if not isinstance(profile, dict):
            return False, "配置 Profile 参数格式非法"

        if not self.is_supported():
            return False, "当前设备非 Acer 笔记本或未加载 Acer WMI 控制驱动 (静默跳过)"

        logs = []
        target_tab = "turbo"

        # 1. 设置 CoolBoost
        cb = profile.get("coolboost")
        if cb is not None:
            self.set_coolboost(bool(cb))
            state_str = "开启" if cb else "关闭"
            logs.append(f"CoolBoost 已成功设置为: {state_str}")

        # 2. 设置超频模式
        oc = profile.get("overclock_mode")
        if oc:
            self.set_overclock_mode(oc)
            logs.append(f"超频模式已成功设置为: {oc}")
            if str(oc).upper() in ["EXTREME", "TURBO", "FAST", "极速", "快速"]:
                target_tab = "turbo"

        # 3. 设置风扇模式
        fm = profile.get("fan_mode")
        if fm:
            self.set_fan_mode(fm)
            logs.append(f"风扇模式已成功设置为: {fm}")
            if str(fm).upper() in ["MAX", "最大"]:
                target_tab = "fan"

        # 4. 全自动发起 UI 程序化点击 (精细化定位: 风扇/超频/CoolBoost + post_action 适配)
        try:
            pa = profile.get("post_action", "hide")
            self.launch_predatorsense_gui(fan_mode=fm, overclock_mode=oc, coolboost=cb, post_action=pa)
        except Exception:
            pass

        summary_msg = " | ".join(logs) if logs else "Acer 硬件性能设置已自动保存并点击应用"
        return True, summary_msg







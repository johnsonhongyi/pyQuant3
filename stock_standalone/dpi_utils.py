# -*- coding:utf-8 -*-
import os
import sys
import ctypes
from JohnsonUtil import LoggerFactory

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.DPI")

def set_process_dpi_awareness():
    """启用进程的 DPI 感知 (Windows)"""
    try:
        if sys.platform == "win32":
            # 对 Windows 10+ 启用 Per-Monitor DPI 感知
            # ERROR_ACCESS_DENIED (5) usually means awareness is already set (e.g. by Qt6)
            try:
                # 优先 Per-Monitor V2 (-4)，失败(已被设置/旧系统)再回退 shcore
                try:
                    if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                        logger.info("[DPI] 已启用 Per-Monitor V2")
                        return
                except Exception:
                    pass
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                logger.info("[DPI] 已启用 Per-Monitor DPI Aware")
            except OSError as e:
                if e.winerror == 5:
                    logger.info("[DPI] Awareness already set (manifest/其他模块已设置)，跳过。")
                else:
                    raise
    except Exception as e:
        logger.info(f"[DPI] 启用失败: {e}")

# def set_process_dpi_awareness():
#     """启用进程的 DPI 感知 (Windows)"""
#     try:
#         if sys.platform != "win32":
#             return

#         # 判断 PyQt 版本
#         pyqt_version = None
#         try:
#             import PyQt6
#             pyqt_version = 6
#         except ImportError:
#             try:
#                 import PyQt5
#                 pyqt_version = 5
#             except ImportError:
#                 pyqt_version = None

#         if pyqt_version == 5:
#             # PyQt5 下启用 Per-Monitor DPI Awareness
#             import ctypes
#             ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE = 2
#             logger.info("[DPI] PyQt5: 已启用 Per-Monitor DPI Aware")
#         elif pyqt_version == 6:
#             # PyQt6 默认已经启用 Per-Monitor-V2
#             logger.info("[DPI] PyQt6: 默认 Per-Monitor-V2，跳过设置")
#         else:
#             logger.warning("[DPI] 未检测到 PyQt5/6，跳过 DPI 设置")
#     except Exception as e:
#         logger.exception(f"[DPI] 启用 DPI 感知失败: {e}")

def set_process_dpi_awareness_Close():
    """禁用进程的 DPI 感知"""
    if sys.platform.startswith('win'):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(0)
        except:
            pass 
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '0'
        os.environ['QT_QPA_PLATFORM'] = 'windows:dpiawareness=0' 

def is_rdp_session():
    """检测当前是否通过远程桌面 (RDP) 连接"""
    if sys.platform != "win32":
        return False
    SM_REMOTESESSION = 0x1000
    return bool(ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION))

def scale_tk_window_for_rdp(root, scale_factor=1.5):
    """在 RDP 环境下自动放大 Tk 窗口尺寸"""
    if is_rdp_session():
        w = int(root.winfo_width() * scale_factor)
        h = int(root.winfo_height() * scale_factor)
        root.geometry(f"{w}x{h}")
        logger.info(f"[RDP] 已按 {scale_factor} 缩放 Tk 窗口: {w}x{h}")

def monitor_rdp_and_scale(win, interval_ms=3000, scale_factor=1.5):
    """间歇性检测 RDP 状态并调整缩放"""
    if not hasattr(win, "_last_rdp_state"):
        win._last_rdp_state = is_rdp_session()

    current_state = is_rdp_session()
    if current_state != win._last_rdp_state:
        win._last_rdp_state = current_state
        if current_state:
            logger.info(f"[RDP] 检测到远程登录，放大 Tk 窗口 scale={scale_factor}")
            try:
                win.tk.call('tk', 'scaling', scale_factor)
                w = int(win.winfo_width() * scale_factor)
                h = int(win.winfo_height() * scale_factor)
                win.geometry(f"{w}x{h}")
            except Exception as e:
                logger.info(f"[RDP] 调整窗口缩放失败: {e}")
        else:
            logger.info("[RDP] 返回本地会话，恢复默认缩放")
            try:
                win.tk.call('tk', 'scaling', 1.0)
                w = int(win.winfo_width() / scale_factor)
                h = int(win.winfo_height() / scale_factor)
                win.geometry(f"{w}x{h}")
            except Exception as e:
                logger.info(f"[RDP] 恢复窗口缩放失败: {e}")
    win.after(interval_ms, lambda: monitor_rdp_and_scale(win, interval_ms, scale_factor))

def get_window_dpi_scale(window):
    """获取指定窗口的 DPI 缩放比例"""
    try:
        user32 = ctypes.windll.user32
        hwnd = window.winfo_id()
        # Tk 的 winfo_id 是客户区子窗口，取顶层窗口更准确
        top = user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
        dpi = user32.GetDpiForWindow(top)
        try:
            # 优先取窗口所在显示器的有效 DPI（RDP/多屏切换时更及时）
            mon = user32.MonitorFromWindow(top, 2)  # MONITOR_DEFAULTTONEAREST
            dx, dy = ctypes.c_uint(0), ctypes.c_uint(0)
            if mon and ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value:
                dpi = dx.value
        except Exception:
            pass
        return (dpi or 96) / 96.0
    except Exception:
        return 1.0

def get_current_window_scale(tk_obj):
    """获取当前 Tk 窗口的 DPI 和缩放因子"""
    try:
        hwnd = tk_obj.winfo_id()
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        scale = round(dpi / 96, 2)
        return dpi, scale
    except Exception:
        return 96, 1.0

def get_windows_dpi_scale_factor():
    """获取 Windows 系统的 DPI 缩放因子"""
    try:
        LOGPIXELSX = 88
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        dc = user32.GetDC(0)
        dpi = gdi32.GetDeviceCaps(dc, LOGPIXELSX)
        user32.ReleaseDC(0, dc)
        scale = dpi / 96.0
        if scale == 1.0 and is_rdp_session():
            return 2.0
        return scale
    except Exception:
        return 1.0

def get_dpi_awareness_info(window=None):
    """诊断当前进程 DPI 感知模式及各 DPI 数值。

    awareness: unaware / system / per_monitor / per_monitor_v2 / unknown
    若为 unaware/system，Windows 将一直返回登录/启动时的 DPI，RDP 改分辨率无法被检测。
    """
    info = {"awareness": "unknown", "system_dpi": None, "window_dpi": None, "monitor_dpi": None,
            "rdp": False, "screen": None}
    if sys.platform != "win32":
        return info
    try:
        user32 = ctypes.windll.user32
        info["rdp"] = is_rdp_session()
        info["screen"] = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        try:
            val = ctypes.c_int(-1)
            if ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(val)) == 0:
                info["awareness"] = {0: "unaware", 1: "system", 2: "per_monitor"}.get(val.value, "unknown")
        except Exception:
            pass
        try:
            ctx = user32.GetThreadDpiAwarenessContext()
            ctx_v2 = ctypes.c_void_p(-4)
            if user32.AreDpiAwarenessContextsEqual(ctypes.c_void_p(ctx), ctx_v2):
                info["awareness"] = "per_monitor_v2"
        except Exception:
            pass
        try:
            info["system_dpi"] = user32.GetDpiForSystem()
        except Exception:
            pass
        if window is not None:
            info["window_dpi"] = int(round(get_window_dpi_scale(window) * 96))
            try:
                top = user32.GetAncestor(window.winfo_id(), 2) or window.winfo_id()
                info["window_dpi_raw"] = user32.GetDpiForWindow(top)
            except Exception:
                pass
    except Exception as e:
        info["error"] = str(e)
    return info


def log_dpi_awareness(tag="", window=None):
    """把 DPI 感知诊断写入日志，返回 info 字典。"""
    info = get_dpi_awareness_info(window)
    level_ok = info.get("awareness") in ("per_monitor", "per_monitor_v2")
    msg = f"[DPI诊断]{tag} {info}"
    if level_ok:
        logger.info(msg)
    else:
        logger.warning(msg + " ⚠ 非 Per-Monitor 感知: 运行期无法检测 RDP DPI/分辨率变化，请检查 exe manifest 或先于 Tk 的 SetProcessDpiAwareness 调用")
    return info

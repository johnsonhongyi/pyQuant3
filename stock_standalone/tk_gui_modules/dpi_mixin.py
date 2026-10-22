# -*- coding:utf-8 -*-
from logger_utils import LoggerFactory
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Optional, Union, Protocol, runtime_checkable, TYPE_CHECKING
import logging
import ctypes
from JohnsonUtil import commonTips as cct
from dpi_utils import get_current_window_scale, get_window_dpi_scale, log_dpi_awareness

try:
    from PyQt6 import QtWidgets, QtCore, QtGui
    PYQT6_AVAILABLE = True
except ImportError:
    try:
        from PyQt5 import QtWidgets, QtCore, QtGui
        PYQT6_AVAILABLE = True
    except ImportError:
        QtWidgets = Any # type: ignore
        QtCore = Any # type: ignore
        QtGui = Any # type: ignore
        PYQT6_AVAILABLE = False

PYQT5_AVAILABLE = PYQT6_AVAILABLE

logger = LoggerFactory.getLogger("instock_TK.DPI")


def _virtual_screen_sig() -> tuple:
    """虚拟桌面 (x, y, w, h)；用于检测远程改分辨率/多屏变化。"""
    try:
        gm = ctypes.windll.user32.GetSystemMetrics
        return (gm(76), gm(77), gm(78), gm(79))
    except Exception:
        return (0, 0, 0, 0)

@runtime_checkable
class DPIAppProtocol(Protocol):
    """Protocol for StockMonitorApp to satisfy Pylance attribute checks in DPIMixin."""
    scale_factor: float
    last_dpi_scale: float
    _dpi_base: dict[str, Any]
    _pg_windows: dict[str, Any]
    _concept_win: Optional[tk.Toplevel]
    kline_monitor: Optional[Any]
    monitor_windows: dict[str, Any]
    default_font: tkfont.Font
    default_font_bold: tkfont.Font
    default_font_size: int
    tree: ttk.Treeview
    def after(self, ms: int, func: Optional[Any] = None, *args: Any) -> str: ...
    def winfo_fpixels(self, distance: str) -> float: ...
    def winfo_screenwidth(self) -> int: ...
    def winfo_screenheight(self) -> int: ...
    def winfo_screenmmwidth(self) -> int: ...
    def winfo_screenmmheight(self) -> int: ...
    def winfo_width(self) -> int: ...
    def winfo_height(self) -> int: ...
    def winfo_id(self) -> int: ...
    def geometry(self, new_geom: Optional[str] = None) -> str: ...
    def tk_call(self, *args: Any) -> Any: ...

class DPIMixin:
    """Handles DPI scaling and window resizing for Tkinter and PyQt5."""
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        scale_factor: float
        last_dpi_scale: float
        _dpi_base: dict[str, Any]
        _pg_windows: dict[str, Any]
        _concept_win: Optional[tk.Toplevel]
        kline_monitor: Optional[Any]
        monitor_windows: dict[str, Any]
        default_font: tkfont.Font
        default_font_bold: tkfont.Font
        default_font_size: int
        tree: ttk.Treeview
        def after(self, ms: int, func: Optional[Any] = None, *args: Any) -> str: ...
        def winfo_fpixels(self, distance: str) -> float: ...
        def winfo_screenwidth(self) -> int: ...
        def winfo_screenheight(self) -> int: ...
        def winfo_screenmmwidth(self) -> int: ...
        def winfo_screenmmheight(self) -> int: ...
        def winfo_width(self) -> int: ...
        def winfo_height(self) -> int: ...
        def winfo_id(self) -> int: ...
        def geometry(self, new_geom: Optional[str] = None) -> str: ...

    def print_tk_dpi_detail(self) -> tuple[int, int]:
        px_per_inch = self.winfo_fpixels('1i')
        width_px = self.winfo_screenwidth()
        height_px = self.winfo_screenheight()
        width_in = self.winfo_screenmmwidth() / 25.4
        height_in = self.winfo_screenmmheight() / 25.4
        screen_dpi = round(width_px / width_in / 96, 2)
        dpi, scale = get_current_window_scale(self) # type: ignore
        print("当前显示器 DPI:", dpi)
        print("缩放倍率:", scale)
        return (width_px, height_px)

    def _check_dpi_change(self) -> None:
        """定期检测 DPI / 分辨率变化（RDP 登录、远程改分辨率、拖到不同 DPI 显示器）。"""
        try:
            self._dpi_poll_once()
        except Exception as e:
            logger.warning(f"[DPI] 轮询异常(已降级继续): {e}")
        # 1.5 秒轮询一次: 仅两次轻量 ctypes 调用，开销可忽略
        if hasattr(self, '_schedule_after'):
            self._schedule_after(1500, self._check_dpi_change)
        else:
            self.after(1500, self._check_dpi_change)

    def _dpi_poll_once(self) -> None:
        scale = get_window_dpi_scale(self)  # type: ignore
        last = getattr(self, 'last_dpi_scale', 1.0) or 1.0
        try:
            state = self.state()  # type: ignore
        except Exception:
            state = 'normal'
        w, h = self.winfo_width(), self.winfo_height()
        sig = _virtual_screen_sig()

        if abs(scale - last) > 0.05:
            logger.info(f"[DPI变化检测] 从 {last:.2f} → {scale:.2f} screen={sig}")
            log_dpi_awareness(" on_change", self)
            base_wh = getattr(self, '_dpi_last_wh', None) or (w, h)
            self._apply_scale_dpi_change(scale, base_wh)
            self.on_dpi_changed_qt(scale)
            self.last_dpi_scale = scale
            self._dpi_last_wh = None
            self._dpi_screen_sig = sig
            return

        if state == 'normal' and w > 1 and h > 1:
            self._dpi_last_wh = (w, h)  # 变化前的最后一次稳定尺寸，作为缩放基准
        prev_sig = getattr(self, '_dpi_screen_sig', None)
        self._dpi_screen_sig = sig
        if prev_sig is not None and prev_sig != sig and state == 'normal':
            logger.info(f"[DPI] 屏幕几何变化 {prev_sig} → {sig}，窗口收敛进可视区")
            self._clamp_window_to_screen(self)

    def _clamp_window_to_screen(self, win: Any) -> None:
        """把窗口尺寸与位置限制在虚拟桌面内，避免分辨率变化后窗口越界/不可见。"""
        try:
            vx, vy, vw, vh = _virtual_screen_sig()
            if vw <= 0 or vh <= 0:
                return
            win.update_idletasks()
            w, h = win.winfo_width(), win.winfo_height()
            x, y = win.winfo_x(), win.winfo_y()
            nw, nh = min(w, vw - 20), min(h, vh - 60)
            nx = max(vx, min(x, vx + vw - nw))
            ny = max(vy, min(y, vy + vh - nh - 40))
            if (nw, nh, nx, ny) != (w, h, x, y):
                win.geometry(f"{nw}x{nh}+{nx}+{ny}")
        except Exception as e:
            logger.debug(f"[DPI] clamp 失败: {e}")

    @staticmethod
    def _scale_tree_columns(tree: Any, ratio: float) -> None:
        try:
            for c in tree['columns']:
                cur = int(tree.column(c, 'width'))
                tree.column(c, width=max(10, int(round(cur * ratio))))
        except Exception as e:
            logger.debug(f"[DPI] 列宽缩放失败: {e}")

    def get_qt_window_scale_base(self, win: Any) -> tuple[float, float]:
        if not PYQT5_AVAILABLE:
            return 96.0, 1.0
        try:
            handle = win.windowHandle()
            if handle is None:
                return 96.0, 1.0
            screen = handle.screen()
            scale = screen.devicePixelRatio()
            dpi = screen.logicalDotsPerInch()
            return float(dpi), float(scale)
        except Exception as e:
            logger.warning(f"获取 Qt 窗口缩放失败: {e}")
            return 96.0, 1.0

    def get_qt_window_scale(self, win: Any) -> float:
        if not PYQT5_AVAILABLE:
            return 1.0
        try:
            handle = win.windowHandle()
            if handle is None:
                return 1.0
            screen = handle.screen()
            logical_dpi = screen.logicalDotsPerInch()
            physical_dpi = logical_dpi * screen.devicePixelRatio()
            scale = physical_dpi / 96.0
            return float(scale)
        except Exception as e:
            logger.warning(f"获取 Qt 窗口缩放失败: {e}")
            return 1.0

    def on_dpi_changed_qt(self, new_scale: float) -> None:
        """DPI 变化通知 Qt 窗口。

        Qt6 自身为 Per-Monitor 感知，窗口/字体由 Qt 内部随屏幕 DPI 重算；
        此处不再二次缩放(会叠加放大)，也不再因异常删除 _pg_windows 记录，仅清理已销毁窗口。
        """
        try:
            for k, v in list(getattr(self, "_pg_windows", {}).items()):
                win = v.get("win")
                try:
                    if win is not None:
                        win.isVisible()  # 仅探测 C++ 对象是否存活
                        win.update()
                except RuntimeError:
                    getattr(self, "_pg_windows").pop(k, None)
                    logger.info(f'[DPI] pg win 已销毁，移除记录: {k}')
        except Exception as e:
            logger.info(f"[DPI] Qt 通知失败: {e}")

    def scale_single_window(self, window: Any, scale_factor: float) -> None:
        width = window.winfo_width()
        height = window.winfo_height()
        window.geometry(f"{int(width*scale_factor)}x{int(height*scale_factor)}")

        for child in window.winfo_children():
            if isinstance(child, (tk.Label, tk.Entry)):
                font = tkfont.nametofont(child.cget("font"))
                font.configure(size=int(font.cget("size") * scale_factor))
                child.configure(font=font)

        if isinstance(window, ttk.Treeview):
            style = ttk.Style(window)
            style.configure("Treeview", rowheight=int(22 * scale_factor))

    def scale_tk_window(self, window: Any, scale_factor: float, name: str, old_scale: Optional[float] = None) -> None:
        """对单个 Tk 子窗口做 DPI 缩放（字体由 tk scaling 全局处理，这里只处理尺寸/列宽）。"""
        applied = getattr(window, "_dpi_applied", None) or old_scale or scale_factor
        ratio = scale_factor / applied if applied else 1.0
        window._dpi_applied = scale_factor
        if abs(ratio - 1.0) < 0.01:
            return
        try:
            if window.state() == 'normal':
                w, h = window.winfo_width(), window.winfo_height()
                x, y = window.winfo_x(), window.winfo_y()
                window.geometry(f"{max(100, int(w * ratio))}x{max(80, int(h * ratio))}+{x}+{y}")
                self._clamp_window_to_screen(window)
        except Exception as e:
            logger.debug(f"[DPI] {name} 尺寸缩放失败: {e}")
        if hasattr(window, "tree"):
            self._scale_tree_columns(window.tree, ratio)
        logger.info(f"[DPI] {name} 缩放 {applied:.2f} → {scale_factor:.2f}")

    def scale_refesh_windows(self, scale_factor: float, old_scale: Optional[float] = None) -> None:
        if hasattr(self, "_concept_win") and self._concept_win:
            if self._concept_win.winfo_exists():
                self.scale_tk_window(self._concept_win, scale_factor, "_concept_win", old_scale)

        if hasattr(self, "kline_monitor") and self.kline_monitor and hasattr(self.kline_monitor, 'winfo_exists') and self.kline_monitor.winfo_exists():
            try:
                self.scale_tk_window(self.kline_monitor, scale_factor, "kline_monitor", old_scale)
            except Exception:
                pass

        if hasattr(self, "monitor_windows") and self.monitor_windows:
            windows_dict = getattr(self, "monitor_windows")
            for unique_code, win_info in list(windows_dict.items()):
                win = win_info.get('toplevel')
                if win and win.winfo_exists():
                    try:
                        self.scale_tk_window(win, scale_factor, unique_code, old_scale)
                    except Exception as e:
                        logger.warning(f"scale_tk_window {unique_code} 失败: {e}")
        logger.info('scale_refesh_win done')

    def _apply_scale_dpi_change(self, scale_factor: float, base_wh: Optional[tuple] = None) -> None:
        """DPI 变化时重设 Tk 全局缩放(含缩小方向)、行高、列宽、窗口尺寸，并收敛进屏幕。"""
        old_scale = getattr(self, 'scale_factor', 1.0) or 1.0
        try:
            ratio = scale_factor / old_scale
            # 1) 全局 tk scaling: 所有以 pt 计的字体随之重算(不再手工二次改字号)
            self.tk.call('tk', 'scaling', (scale_factor * 96.0) / 72.0)  # type: ignore
            # 2) Treeview 行高
            try:
                ttk.Style(self).configure("Treeview", rowheight=int(22 * scale_factor))
            except Exception as e:
                logger.warning(f"[DPI变化] 设置 Treeview 行高失败: {e}")
            # 3) 主表列宽
            if hasattr(self, "tree") and abs(ratio - 1.0) >= 0.01:
                self._scale_tree_columns(self.tree, ratio)
            # 4) 主窗口尺寸(基于变化前稳定尺寸)，最大化状态交给系统
            try:
                if self.state() == 'normal':  # type: ignore
                    bw, bh = base_wh or (self.winfo_width(), self.winfo_height())
                    x, y = self.winfo_x(), self.winfo_y()
                    self.geometry(f"{int(bw * ratio)}x{int(bh * ratio)}+{x}+{y}")
                    self._clamp_window_to_screen(self)
            except Exception as e:
                logger.warning(f"[DPI变化] 主窗口缩放失败: {e}")
            self.scale_factor = scale_factor
            # 5) 子窗口
            self.scale_refesh_windows(scale_factor, old_scale)
            logger.info(f"[DPI变化] ✅ DPI同步完成 Tk @ {scale_factor:.2f}x (ratio={ratio:.3f})")
        except Exception as e:
            logger.error(f"[DPI变化] ❌ DPI同步失败: {e}", exc_info=True)
        finally:
            self.scale_factor = scale_factor

    def _apply_dpi_scaling(self, scale_factor: Optional[float] = None) -> float:
        """自动计算并设置 Tkinter 的内部 DPI 缩放（含 <=1.0，保证放大后可缩回）。"""
        if scale_factor is None:
            self.scale_factor = get_window_dpi_scale(self)  # type: ignore
            scale_factor = self.scale_factor
        else:
            self.scale_factor = scale_factor
        try:
            self.tk.call('tk', 'scaling', (scale_factor * 96.0) / 72.0)  # type: ignore
            ttk.Style(self).configure('Treeview', rowheight=int(22 * scale_factor))  # type: ignore
        except Exception as e_rowinit:
            logger.warning(f"[初始化缩放] 设置失败: {e_rowinit}")
        return scale_factor

    def get_scaled_value(self) -> float:
        """获取当前缩放比例"""
        return float(getattr(self, 'scale_factor', 1.0))

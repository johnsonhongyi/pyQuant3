# -*- coding:utf-8 -*-
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Optional, Union, Protocol, runtime_checkable, TYPE_CHECKING
import logging
from JohnsonUtil import commonTips as cct
from dpi_utils import get_current_window_scale, get_window_dpi_scale

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

logger = logging.getLogger("instock_TK.DPI")

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
        """定期检测 DPI 是否变化（例如 RDP 登录）"""
        scale = get_window_dpi_scale(self) # type: ignore
        current_scale = scale
        if abs(current_scale - getattr(self, 'last_dpi_scale', 1.0)) > 0.05:
            logger.info(f"{cct.get_now_time_int()}  current_scale:{current_scale}")
            logger.info(f"[DPI变化检测] 从 {getattr(self, 'last_dpi_scale', 1.0):.2f} → {current_scale:.2f}")
            self._apply_scale_dpi_change(current_scale)
            self.on_dpi_changed_qt(current_scale)
            self.last_dpi_scale = current_scale

        # 每 5 秒检测一次
        self.after(5000, self._check_dpi_change)

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
        """RDP 或 DPI 变化时自动缩放窗口"""
        try:
            if hasattr(self, "_pg_windows"):
                for k, v in list(getattr(self, "_pg_windows").items()):
                    win = v.get("win")
                    try:
                        if win is not None:
                            win_qt_scale = self.get_qt_window_scale(win)
                            if win_qt_scale == new_scale:
                                geom = win.geometry()
                                width, height = geom.width(), geom.height()
                                base = getattr(self, "_dpi_base", {"scale": 1.0})
                                scale_ratio = new_scale / base["scale"]
                                new_w = int(width * scale_ratio)
                                new_h = int(height * scale_ratio)
                                win.resize(new_w, new_h)
                                code = v.get("code", "N/A")
                                logger.info(f"[DPI] code={code} 窗口自动放大到 {new_scale:.2f} 倍-> {scale_ratio:.2f}倍 ({new_w}x{new_h})")
                                if PYQT5_AVAILABLE:
                                    for child in win.findChildren(QtWidgets.QWidget):
                                        font = child.font()
                                        font.setPointSizeF(font.pointSizeF() * scale_ratio)
                                        child.setFont(font)
                    except Exception as e:
                        logger.info(f'e:{e} pg win is None will remove:{v.get("win")}')
                        del getattr(self, "_pg_windows")[k]
        except Exception as e:
            logger.info(f"[DPI] 自动缩放失败: {e}")

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

    def scale_tk_window(self, window: Any, scale_factor: float, name: str) -> None:
        """对单个 Tk 窗口进行 DPI 缩放"""
        if not hasattr(window, "_dpi_base"):
            base_tree_colwidths = []
            if hasattr(window, 'tree'):
                base_tree_colwidths = [window.tree.column(c)['width'] for c in window.tree['columns']]
            window._dpi_base = {
                "width": window.winfo_width(),
                "height": window.winfo_height(),
                "font_size": getattr(self, 'default_font_size', 10),
                "tree_rowheight": 22,
                "tree_colwidths": base_tree_colwidths,
                "scale": get_window_dpi_scale(window)
            }
            logger.info(f"[DPI] {name} 初始化基准值: {window._dpi_base['scale']} 窗口 {window._dpi_base['width']}x{window._dpi_base['height']}")
            return

        base = window._dpi_base
        base_scale_factor = base["scale"]
        font_size = base["font_size"]
        rowheight = base["tree_rowheight"]

        if abs(scale_factor - base_scale_factor) < 0.01:
            return
        
        logger.info(f"[DPI] {name} font_size: {font_size} rowheight:{rowheight} 变化: {base_scale_factor} to {scale_factor}")
        
        def scale_widgets(parent: Any, f_size: int) -> None:
            for child in parent.winfo_children():
                try:
                    f_old = tkfont.nametofont(child.cget("font"))
                    f_new = tkfont.Font(family=f_old.cget("family"), size=f_size, weight=f_old.cget("weight"), slant=f_old.cget("slant"))
                    child.configure(font=f_new)
                except Exception:
                    pass
                scale_widgets(child, f_size)

        scale_widgets(window, font_size)

        if hasattr(window, "tree"):
            style = ttk.Style(window)
            style_name = f"{window.winfo_id()}.Treeview"
            style.configure(style_name, rowheight=rowheight)
            window.tree.configure(style=style_name)

    def scale_refesh_windows(self, scale_factor: float) -> None:
        if hasattr(self, "_concept_win") and self._concept_win:
            if self._concept_win.winfo_exists():
                self.scale_tk_window(self._concept_win, scale_factor, name="_concept_win")
        
        if hasattr(self, "kline_monitor") and self.kline_monitor and hasattr(self.kline_monitor, 'winfo_exists') and self.kline_monitor.winfo_exists():
            try:
                self.scale_tk_window(self.kline_monitor, scale_factor, name="kline_monitor")
            except Exception:
                pass

        if hasattr(self, "monitor_windows") and self.monitor_windows:
            windows_dict = getattr(self, "monitor_windows")
            for unique_code, win_info in list(windows_dict.items()):
                win = win_info.get('toplevel')
                if win and win.winfo_exists():
                    try:
                        self.scale_tk_window(win, scale_factor, name=unique_code)
                    except Exception as e:
                        logger.warning(f"scale_tk_window {unique_code} 失败: {e}")
        logger.info(f'scale_refesh_win done')

    def _apply_scale_dpi_change(self, scale_factor: float) -> None:
        """当 DPI 变化时，同步缩放 Tk + Qt"""
        try:
            if not hasattr(self, "_dpi_base"):
                base_tree_colwidths = []
                if hasattr(self, 'tree'):
                    base_tree_colwidths = [self.tree.column(c)['width'] for c in self.tree['columns']]
                self._dpi_base = {
                    "width": self.winfo_width(),
                    "height": self.winfo_height(),
                    "font_size": self.default_font.cget("size"),
                    "tree_rowheight": 22,
                    "tree_colwidths": base_tree_colwidths,
                    "scale": getattr(self, 'scale_factor', 1.0)
                }
                logger.info(f"[DPI] 初始化基准值Main: 窗口 {self._dpi_base['width']}x{self._dpi_base['height']}")

            base = self._dpi_base
            font_size = base["font_size"]
            scale_ratio = scale_factor / base["scale"]

            width = self.winfo_width()
            height = self.winfo_height()
            new_w = int(width * scale_factor / (getattr(self, 'scale_factor', 1.0) or 1.0))
            new_h = int(height * scale_factor / (getattr(self, 'scale_factor', 1.0) or 1.0))
            self.geometry(f"{new_w}x{new_h}")

            old_scale = getattr(self, 'scale_factor', 1.0) or 1.0
            if abs(scale_factor - old_scale) < 0.01:
                return

            self.scale_factor = scale_factor
            new_size = max(9, round(font_size * scale_ratio))

            font_names = ["TkDefaultFont", "TkTextFont", "TkFixedFont", "TkHeadingFont", "TkMenuFont"]
            for name in font_names:
                try:
                    f = tkfont.nametofont(name)
                    f.configure(size=new_size)
                except Exception:
                    pass

            self.default_font.configure(size=new_size)
            self.default_font_bold.configure(size=new_size)

            if hasattr(self, "tree"):
                try:
                    style = ttk.Style(self)
                    style.configure("Treeview", rowheight=int(22 * scale_factor))
                except Exception as e:
                    logger.warning(f"[DPI变化] 设置 Treeview 行高失败: {e}")

            self.on_dpi_changed_qt(scale_factor)
            logger.info(f"[DPI变化] ✅ DPI同步完成 Tk+Qt @ {scale_factor:.2f}x")

        except Exception as e:
            logger.error(f"[DPI变化] ❌ DPI同步失败: {e}", exc_info=True)
        finally:
            self.scale_factor = scale_factor

    def _apply_dpi_scaling(self, scale_factor: Optional[float] = None) -> float:
        """自动计算并设置 Tkinter 的内部 DPI 缩放。"""
        if scale_factor is None: 
            self.scale_factor = get_window_dpi_scale(self) # type: ignore
            scale_factor = self.scale_factor
        else:
            self.scale_factor = scale_factor
        
        if scale_factor > 1.0:
            tk_scaling_value = (scale_factor * 96.0) / 72.0 
            self.tk.call('tk', 'scaling', tk_scaling_value) # type: ignore
            try:
                style = ttk.Style(self) # type: ignore
                scaled_row_height = int(22 * scale_factor)
                style.configure('Treeview', rowheight=scaled_row_height)
            except Exception as e_rowinit:
                logger.warning(f"[初始化缩放] 设置 Treeview 行高失败: {e_rowinit}")
        return scale_factor

    def get_scaled_value(self) -> float:
        """获取当前缩放比例"""
        return float(getattr(self, 'scale_factor', 1.0))

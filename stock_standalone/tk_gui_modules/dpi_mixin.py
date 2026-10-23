# -*- coding:utf-8 -*-
from logger_utils import LoggerFactory
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Optional, Union, Protocol, runtime_checkable, TYPE_CHECKING
import logging
import ctypes
import sys
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

# 设计基准常量 (96 DPI / 100% 缩放下的标准物理尺寸)
BASE_DPI = 96.0
BASE_POINT_SIZE = 9
BASE_ROW_HEIGHT = 22

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
    """Handles DPI scaling and window resizing for Tkinter and PyQt6/5.
    
    核心底层架构设计：
    1. 真实单一 DPI 源：绝不虚标 RDP，严格遵循 Windows 物理与会话 DPI。
    2. tk scaling 单一控制：tk scaling = (DPI / 72.0)，由 Tk 自动将标准 point (9pt) 换算为屏幕物理像素，
       绝不人为将 font.size 乘以 scale_factor（彻底根绝平方级字体爆炸与文字挤压重叠）。
    3. 全样式 Treeview 行高同步：覆盖 Treeview、Fast.Treeview、Heading。
    4. 全子窗口递归列宽与几何自适应：穿透递归所有 Toplevel 及其内嵌 Treeview。
    """
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

    @staticmethod
    def _compute_safe_rowheight(scale_factor: float = 1.0) -> int:
        """根据当前字体度量 linespace 动态计算安全行高，上下预留呼吸空间，彻底杜绝文字粘连。"""
        try:
            f = tkfont.nametofont("TkDefaultFont")
            linespace = f.metrics("linespace")
        except Exception:
            linespace = 14
        return max(18, linespace + 5, int(round(BASE_ROW_HEIGHT * scale_factor)))

    def _reset_named_fonts(self) -> None:
        """安全保护全局字体，不粗暴覆盖系统根据 DPI 计算出的物理像素大小。"""
        pass

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
        # 1.5 秒轮询一次: 两次轻量底层 API，开销极低
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

        # 检测 DPI 缩放改变
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
        
        # 检测屏幕分辨率几何改变（例如 RDP 调整了分辨率但 DPI 没变）
        prev_sig = getattr(self, '_dpi_screen_sig', None)
        self._dpi_screen_sig = sig
        if prev_sig is not None and prev_sig != sig and state == 'normal':
            logger.info(f"[DPI] 屏幕几何变化 {prev_sig} → {sig}，窗口收敛进可视区")
            self._clamp_window_to_screen(self)
            self._clamp_all_toplevels()

        # 轻量巡检：捕获在高 DPI 下新动态弹出的未适配子窗口 (1.5s 周期内自动对齐)
        if scale > 1.05 and state == 'normal':
            self._adapt_unregistered_toplevels(scale)

    def _clamp_window_to_screen(self, win: Any) -> None:
        """把窗口尺寸与位置限制在虚拟桌面内，避免分辨率变小后窗口越界或完全不可见。"""
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

    def _adapt_unregistered_toplevels(self, current_scale: float) -> None:
        """巡检并自动适配所有新打开尚未缩放的子窗口，杜绝窄列文字重叠。"""
        for win in self._get_all_toplevel_windows():
            if getattr(win, "_dpi_applied", None) is None:
                try:
                    title = getattr(win, "title", lambda: "SubWindow")()
                    # 若窗口已经由 load_window_position 明确恢复了持久化 geometry，直接标记已对齐，绝不二次放大自身尺寸
                    if getattr(win, "_persisted_window_name", None) is not None:
                        win._dpi_applied = current_scale
                        for tv in self._find_all_treeviews(win):
                            self._scale_treeview_widget(tv, current_scale)
                        continue
                    self.scale_tk_window(win, current_scale, title)
                    logger.info(f"[DPI] 新建子窗口自动对齐当前 DPI @ {current_scale:.2f}x: {title}")
                except Exception as e:
                    logger.debug(f"[DPI] 自动对齐子窗口异常: {e}")

    def _clamp_all_toplevels(self) -> None:
        """把所有弹出的子窗口都收敛进屏幕可视区。"""
        for win in self._get_all_toplevel_windows():
            try:
                self._clamp_window_to_screen(win)
            except Exception:
                pass

    @staticmethod
    def _find_all_treeviews(widget: Any) -> list:
        """通用递归寻找某窗口或容器内部的所有 ttk.Treeview 实例。"""
        trees = []
        try:
            def _walk(w: Any) -> None:
                if isinstance(w, ttk.Treeview):
                    trees.append(w)
                if hasattr(w, "winfo_children"):
                    for c in w.winfo_children():
                        _walk(c)
            _walk(widget)
        except Exception:
            pass
        return trees

    def _scale_treeview_widget(self, tree: ttk.Treeview, ratio: float) -> None:
        """按缩放比率平滑调整 Treeview 的所有列宽，保持视觉比例完美一致。"""
        if abs(ratio - 1.0) < 0.01:
            return
        try:
            for c in tree['columns']:
                cur_w = int(tree.column(c, 'width'))
                new_w = max(20, int(round(cur_w * ratio)))
                tree.column(c, width=new_w)
        except Exception as e:
            logger.debug(f"[DPI] Treeview 列宽自适应失败: {e}")

    def _get_all_toplevel_windows(self) -> list:
        """获取当前存在的所有 Tkinter Toplevel 顶层子窗口。"""
        wins = []
        try:
            for child in self.winfo_children():
                if isinstance(child, tk.Toplevel) and child.winfo_exists():
                    wins.append(child)
            # 兼容通过特定字典缓存的独立窗口
            if hasattr(self, "_pg_top10_window_simple"):
                for v in list(getattr(self, "_pg_top10_window_simple", {}).values()):
                    w = v.get("win")
                    if w and hasattr(w, "winfo_exists") and w.winfo_exists() and w not in wins:
                        wins.append(w)
            if hasattr(self, "_concept_top10_win") and self._concept_top10_win:
                if self._concept_top10_win.winfo_exists() and self._concept_top10_win not in wins:
                    wins.append(self._concept_top10_win)
        except Exception as e:
            logger.debug(f"[DPI] 收集 Toplevel 异常: {e}")
        return wins

    def on_dpi_changed_qt(self, new_scale: float) -> None:
        """DPI 变化通知 Qt 窗口。
        
        Qt6 自身具备原生 Per-Monitor-V2 高 DPI 矢量渲染，控件与图元由 Qt 内部自动重算。
        此处仅做活跃性检查与销毁记录清理，绝不进行重复的物理缩放。
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

    def scale_tk_window(self, window: Any, scale_factor: float, name: str, old_scale: Optional[float] = None, ratio: Optional[float] = None) -> None:
        """对单个 Tk 子窗口做 DPI 缩放（尺寸与内部所有 Treeview 列宽同步调整）。"""
        applied = getattr(window, "_dpi_applied", None)
        is_persisted = getattr(window, "_persisted_window_name", None) is not None
        if is_persisted and applied is not None:
            # 关键：已由配置文件精确恢复几何的窗口拥有绝对权威，禁止外部后台调用篡改窗口几何
            return
        if applied is None:
            ratio = scale_factor / 1.0
        elif ratio is None:
            ratio = scale_factor / applied if applied else 1.0
        window._dpi_applied = scale_factor
        
        # 调整窗口自身尺寸 (先让窗口尺寸生效，防止 Treeview 列宽被挤压)
        try:
            if window.state() == 'normal':
                w, h = window.winfo_width(), window.winfo_height()
                x, y = window.winfo_x(), window.winfo_y()
                # 只有真正发生跨 DPI 动态切换，或者完全新建且未受持久化配置保护的窗口才缩放自身几何
                should_scale_geom = (applied is not None and abs(ratio - 1.0) >= 0.01) or (applied is None and not is_persisted and abs(ratio - 1.0) >= 0.01)
                if should_scale_geom:
                    window.geometry(f"{max(120, int(w * ratio))}x{max(80, int(h * ratio))}+{x}+{y}")
                window.update_idletasks()
                self._clamp_window_to_screen(window)
        except Exception as e:
            logger.debug(f"[DPI] {name} 尺寸缩放失败: {e}")

        # 调整窗口内所有的 Treeview 列宽
        for tv in self._find_all_treeviews(window):
            self._scale_treeview_widget(tv, ratio)

    def scale_refesh_windows(self, scale_factor: float, old_scale: Optional[float] = None) -> None:
        """刷新所有已打开的子窗口。"""
        all_tops = self._get_all_toplevel_windows()
        old = old_scale or getattr(self, 'scale_factor', 1.0) or 1.0
        ratio = scale_factor / old if old else 1.0
        for idx, win in enumerate(all_tops):
            try:
                title = getattr(win, "title", lambda: f"Top-{idx}")()
                self.scale_tk_window(win, scale_factor, title, old, ratio)
            except Exception as e:
                logger.warning(f"[DPI] 刷新子窗口 {win} 失败: {e}")
        logger.info(f'[DPI] scale_refesh_windows 完成, 共刷新 {len(all_tops)} 个子窗口 (ratio={ratio:.3f})')

    def _apply_scale_dpi_change(self, scale_factor: float, base_wh: Optional[tuple] = None) -> None:
        """DPI 变化时重设 Tk 全局缩放、行高、列宽、窗口尺寸，并收敛进屏幕。"""
        old_scale = getattr(self, 'scale_factor', 1.0) or 1.0
        try:
            ratio = scale_factor / old_scale
            
            # 1) 保护字体：重置全局命名字体为设计标准磅数 (9pt)，坚决不手工改 size
            self._reset_named_fonts()

            # 2) 设置全局 tk scaling (像素/点)
            # 96 DPI -> 1.3333; 120 DPI -> 1.6667; 144 DPI -> 2.0; 192 DPI -> 2.6667
            tk_scaling = (scale_factor * BASE_DPI) / 72.0
            self.tk.call('tk', 'scaling', tk_scaling)  # type: ignore

            # 3) 同步所有 Treeview 样式的行高
            try:
                style = ttk.Style(self)
                row_h = self._compute_safe_rowheight(scale_factor)
                for s_name in ("Treeview", "Fast.Treeview", "Treeview.Heading", "Heading"):
                    try:
                        style.configure(s_name, rowheight=row_h)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[DPI变化] 设置 Treeview 行高失败: {e}")

            # 4) 主窗口尺寸自适应 (先调整窗口几何，确保内部容器空间扩展)
            try:
                if self.state() == 'normal':  # type: ignore
                    bw, bh = base_wh or (self.winfo_width(), self.winfo_height())
                    x, y = self.winfo_x(), self.winfo_y()
                    if abs(ratio - 1.0) >= 0.01:
                        self.geometry(f"{int(bw * ratio)}x{int(bh * ratio)}+{x}+{y}")
                    self.update_idletasks()
                    self._clamp_window_to_screen(self)
            except Exception as e:
                logger.warning(f"[DPI变化] 主窗口缩放失败: {e}")

            # 5) 主表列宽自适应
            if hasattr(self, "tree"):
                self._scale_treeview_widget(self.tree, ratio)

            self.scale_factor = scale_factor

            # 6) 同步刷新所有已打开的子窗口 (包括所有概念 Top10、分时买卖、监控弹窗)
            self.scale_refesh_windows(scale_factor, old_scale)
            logger.info(f"[DPI变化] ✅ DPI同步完成 Tk @ {scale_factor:.2f}x (ratio={ratio:.3f})")
        except Exception as e:
            logger.error(f"[DPI变化] ❌ DPI同步失败: {e}", exc_info=True)
        finally:
            self.scale_factor = scale_factor

    def _apply_dpi_scaling(self, scale_factor: Optional[float] = None) -> float:
        """初始化时自动计算并设置 Tkinter 的内部 DPI 缩放。"""
        if scale_factor is None:
            self.scale_factor = get_window_dpi_scale(self)  # type: ignore
            scale_factor = self.scale_factor
        else:
            self.scale_factor = scale_factor
        self.last_dpi_scale = scale_factor
        
        try:
            # 保护并标准化字体为 9pt
            self._reset_named_fonts()
            # 设置 Tk 缩放
            tk_scaling = (scale_factor * BASE_DPI) / 72.0
            self.tk.call('tk', 'scaling', tk_scaling)  # type: ignore
            
            # 设置各 Treeview 样式行高
            style = ttk.Style(self)  # type: ignore
            row_h = self._compute_safe_rowheight(scale_factor)
            for s_name in ("Treeview", "Fast.Treeview", "Treeview.Heading", "Heading"):
                try:
                    style.configure(s_name, rowheight=row_h)
                except Exception:
                    pass
        except Exception as e_rowinit:
            logger.warning(f"[初始化缩放] 设置失败: {e_rowinit}")
        return scale_factor

    def get_scaled_value(self) -> float:
        """获取当前缩放比例"""
        return float(getattr(self, 'scale_factor', 1.0))

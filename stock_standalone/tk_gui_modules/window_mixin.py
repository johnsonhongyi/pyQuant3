import os
import sys
import logging
import json
from typing import Any, Optional, Union, Protocol, runtime_checkable, TYPE_CHECKING
import tkinter as tk

try:
    from PyQt5 import QtWidgets, QtCore
    PYQT5_AVAILABLE = True
except ImportError:
    QtWidgets = Any # type: ignore
    QtCore = Any # type: ignore
    PYQT5_AVAILABLE = False

from monitor_utils import save_monitor_list, load_monitor_list
from gui_utils import clamp_window_to_screens
from dpi_utils import get_windows_dpi_scale_factor
from .gui_config import WINDOW_CONFIG_FILE, MONITOR_LIST_FILE

logger = logging.getLogger("instock_TK.Window")

@runtime_checkable
class WindowAppProtocol(Protocol):
    """Protocol for StockMonitorApp to satisfy Pylance attribute checks."""
    scale_factor: float
    _pg_top10_window_simple: dict[str, Any]
    _pg_windows: dict[str, Any]
    initial_x: int
    initial_y: int
    initial_w: int
    initial_h: int
    def show_concept_top10_window_simple(self, concept_name: str, code: str = "", auto_update: bool = True, interval: int = 30) -> Union[tk.Toplevel, Any]: ...
    def winfo_screenwidth(self) -> int: ...
    def winfo_screenheight(self) -> int: ...
    def winfo_width(self) -> int: ...
    def winfo_height(self) -> int: ...
    def geometry(self, new_geom: Optional[str] = None) -> str: ...
    def update_idletasks(self) -> None: ...
    def destroy(self) -> None: ...
    def withdraw(self) -> None: ...
    def deiconify(self) -> None: ...
    def lift(self, aboveThis: Optional[Any] = None) -> None: ...
    def focus_set(self) -> None: ...
    def state(self, newstate: Optional[str] = None) -> str: ...

class WindowMixin:
    """Handles window persistence, positioning, and geometry correction."""
    if TYPE_CHECKING:
        # This tells Pylance that in this mixin, 'self' will have attributes from the Protocol
        def __getattr__(self, name: str) -> Any: ...
        scale_factor: float
        _pg_top10_window_simple: dict[str, Any]
        _pg_windows: dict[str, Any]
        initial_x: int
        initial_y: int
        initial_w: int
        initial_h: int
        def show_concept_top10_window_simple(self, concept_name: str, code: str = "", auto_update: bool = True, interval: int = 30) -> Union[tk.Toplevel, Any]: ...
        def winfo_screenwidth(self) -> int: ...
        def winfo_screenheight(self) -> int: ...
        def winfo_width(self) -> int: ...
        def winfo_height(self) -> int: ...
        def geometry(self, new_geom: Optional[str] = None) -> str: ...
        def update_idletasks(self) -> None: ...
        def destroy(self) -> None: ...
        def stop_refresh(self) -> None: ...

    def _get_dpi_scale_factor(self) -> float:
        """获取当前 DPI 缩放因子（统一处理）"""
        try:
            scale = getattr(self, 'scale_factor', 1.0)
            if not isinstance(scale, (int, float)) or scale <= 0:
                scale = 1.0
            return float(scale)
        except Exception as e:
            logger.warning(f"[_get_dpi_scale_factor] 获取缩放失败，使用默认值: {e}")
            return 1.0

    def _get_config_file_path(self, base_file_path: str, scale: float) -> str:
        """根据缩放因子获取配置文件路径（统一处理）"""
        if scale > 1.5:
            base, filename = os.path.split(base_file_path)
            if "window_config.json" in filename:
                return os.path.join(base, f"scale{int(scale)}_window_config.json")
            return os.path.join(base, f"scale{int(scale)}_{filename}")
        return base_file_path

    def load_window_position(self, win: Union[tk.Tk, tk.Toplevel], window_name: str, file_path: Optional[str] = None, 
                             default_width: int = 500, default_height: int = 500, offset_step: int = 100) -> tuple[int, int, Optional[int], Optional[int]]:
        """从统一配置文件加载窗口位置（自动按当前 DPI 缩放）"""
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
            
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()
            
            # 获取正确的配置文件路径
            config_file_path = self._get_config_file_path(file_path, scale)

            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if window_name in data:
                    pos = data[window_name]
                    width = int(pos["width"] * scale)
                    height = int(pos["height"] * scale)
                    x = int(pos["x"] * scale)
                    y = int(pos["y"] * scale)

                    # 处理叠加窗口的偏移
                    if window_name == 'concept_top10_window_simple' and hasattr(self, "_pg_top10_window_simple"):
                        active_windows = self._pg_top10_window_simple.values()
                        for aw_info in active_windows:
                            aw = aw_info.get("win")
                            if aw and aw.winfo_exists() and aw != win:
                                if aw.winfo_x() == x and aw.winfo_y() == y:
                                    x += offset_step
                                    y += offset_step

                    # 限制在屏幕范围内
                    x, y = clamp_window_to_screens(x, y, width, height)
                    win.geometry(f"{width}x{height}+{x}+{y}")
                    logger.debug(f"[load_window_position] 加载 {window_name}: {width}x{height} {x}+{y}")
                    return width, height, x, y

            # 默认居中
            self.center_window(win, int(default_width * scale), int(default_height * scale))
            return int(default_width * scale), int(default_height * scale), None, None
            
        except Exception as e:
            logger.error(f"[load_window_position] 失败: {e}")
            self.center_window(win, int(default_width * self._get_dpi_scale_factor()), int(default_height * self._get_dpi_scale_factor()))
            return default_width, default_height, None, None

    def save_window_position(self, win: Union[tk.Tk, tk.Toplevel], window_name: str, file_path: Optional[str] = None) -> None:
        """保存窗口位置到统一配置文件（自动移除当前 DPI 缩放）"""
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
            
        try:
            win.update_idletasks()
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()

            geom = win.geometry().split('+')
            size = geom[0].split('x')
            width = int(int(size[0]) / scale)
            height = int(int(size[1]) / scale)
            x = int(int(geom[1]) / scale)
            y = int(int(geom[2]) / scale)

            pos = {"x": x, "y": y, "width": width, "height": height}
            config_file_path = self._get_config_file_path(file_path, scale)

            data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.error(f"[save_window_position] 读取失败: {e}")

            data[window_name] = pos
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"[save_window_position] 已保存 {window_name}: {pos}")
        except Exception as e:
            logger.error(f"[save_window_position] 失败: {e}")

    def load_window_position_qt(self, win: Any, window_name: str, file_path: Optional[str] = None, 
                                default_width: int = 500, default_height: int = 500, offset_step: int = 100) -> tuple[int, int, Optional[int], Optional[int]]:
        """从统一配置文件加载 PyQt 窗口位置"""
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
            
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()

            x: Optional[int] = None
            y: Optional[int] = None
            width = default_width
            height = default_height

            config_file_path = self._get_config_file_path(file_path, scale)

            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if window_name in data:
                    pos = data[window_name]
                    width = int(pos.get("width", default_width) * scale)
                    height = int(pos.get("height", default_height) * scale)
                    x = int(pos.get("x", 0) * scale)
                    y = int(pos.get("y", 0) * scale)

                    x, y = clamp_window_to_screens(x, y, width, height)
                    logger.debug(f"[load_window_position_qt] 加载 {window_name}: {width}x{height} {x}+{y}")

            if x is None or y is None:
                if PYQT5_AVAILABLE:
                    screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
                    x = (screen.width() - width) // 2
                    y = (screen.height() - height) // 2
                else:
                    x, y = 100, 100

            if x is not None and y is not None:
                if hasattr(self, "_pg_windows"):
                    active_windows = [w["win"] for w in self._pg_windows.values() if w.get("win") and w["win"] != win]
                    for aw in active_windows:
                        if aw.x() == x and aw.y() == y:
                            x += offset_step
                            y += offset_step

            win.setGeometry(x, y, width, height)
            return width, height, x, y
        except Exception as e:
            logger.error(f"[load_window_position_qt] 失败: {e}")
            return default_width, default_height, None, None

    def save_window_position_qt(self, win: Any, window_name: str, file_path: Optional[str] = None) -> None:
        """保存 PyQt 窗口 position"""
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
            
        try:
            window_name = str(window_name)
            scale = self._get_dpi_scale_factor()

            geom = win.geometry()
            width = max(130, min(int(geom.width() / scale), 500))
            height = max(150, min(int(geom.height() / scale), 450))
            pos = {
                "x": int(geom.x() / scale),
                "y": int(geom.y() / scale),
                "width": width,
                "height": height
            }

            config_file_path = self._get_config_file_path(file_path, scale)

            data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.error(f"[save_window_position_qt] 读取失败: {e}")

            data[window_name] = pos
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"[save_window_position_qt] 已保存 {window_name}: {pos}")
        except Exception as e:
            logger.error(f"[save_window_position_qt] 失败: {e}")

    def center_window(self, win: Union[tk.Tk, tk.Toplevel], width: int, height: int) -> None:
        """将指定窗口居中显示"""
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")

    def update_status_bar_width(self, pw: tk.PanedWindow, left_frame: tk.Frame, right_frame: tk.Frame) -> None:
        """ 根据 DPI 缩放调整左右面板的宽度比例 """
        sf = self._get_dpi_scale_factor()
        left_width = int(900 * sf)
        right_width = int(100 * sf)

        pw.forget(left_frame)
        pw.forget(right_frame)

        pw.add(left_frame, minsize=100, width=left_width)
        pw.add(right_frame, minsize=100, width=right_width)

    def correct_window_geometry(self) -> None:
        """在 Qt 初始化后运行，修复 Tkinter 窗口的位置错乱问题。"""
        if not all(hasattr(self, attr) for attr in ['initial_x', 'initial_y', 'initial_w', 'initial_h']):
            return

        if sys.platform.startswith('win'):
            sf = self._get_dpi_scale_factor()
            
            target_x = int(getattr(self, 'initial_x', 0) * sf)
            target_y = int(getattr(self, 'initial_y', 0) * sf)
            
            screen_width_phys = self.winfo_screenwidth()
            screen_height_phys = self.winfo_screenheight()
            
            current_w = self.winfo_width()
            current_h = self.winfo_height()
            
            target_x = max(0, min(target_x, screen_width_phys - current_w))
            target_y = max(0, min(target_y, screen_height_phys - current_h))

            self.geometry(f'{current_w}x{current_h}+{target_x}+{target_y}')
            logger.info(f"✅ Tkinter 窗口几何信息已重定位到 ({target_x},{target_y}) 物理像素。")
        else:
            self.geometry(self.geometry())


    def save_all_monitor_windows(self) -> None:
        """保存当前所有监控窗口"""
        try:
            if hasattr(self, "_pg_top10_window_simple"):
                save_monitor_list(MONITOR_LIST_FILE, getattr(self, "_pg_top10_window_simple"), logger)
        except Exception as e:
            logger.info(f"保存监控列表失败: {e}")

    def restore_all_monitor_windows(self) -> None:
        """启动时从文件恢复窗口"""
        monitor_data = load_monitor_list(MONITOR_LIST_FILE)
        if not monitor_data:
            logger.info("无监控窗口记录。")
            return

        logger.info(f"正在恢复 {len(monitor_data)} 个监控窗口...")
        for m in monitor_data:
            try:
                code = m[0]
                concept_name = m[2] if len(m) > 2 else "" 
                
                # 创建窗口
                if hasattr(self, 'show_concept_top10_window_simple'):
                    win = self.show_concept_top10_window_simple(concept_name, code=code, auto_update=True, interval=30)

                    # 注册回监控字典
                    if hasattr(self, "_pg_top10_window_simple"):
                        unique_code = f"{concept_name or ''}_"
                        getattr(self, "_pg_top10_window_simple")[unique_code] = {
                            "win": win,
                            "code": unique_code,
                            "stock_info": m
                        }
                        logger.info(f"恢复窗口 {unique_code}: {concept_name} ({code})")
            except Exception as e:
                logger.info(f"恢复窗口失败: {m}, 错误: {e}")

import os
import sys
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
from JohnsonUtil import LoggerFactory
# logger = LoggerFactory.getLogger("instock_TK.Window")
logger = LoggerFactory.getLogger("instock_TK.Window")

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

    def load_window_position(self, win: Any, window_name: str, file_path: Optional[str] = None, 
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
                    try:
                        setattr(win, '_persisted_window_name', window_name)
                    except Exception:
                        pass
                    logger.debug(f"[load_window_position] 加载 {window_name}: {width}x{height} {x}+{y}")
                    return width, height, x, y

            # 默认居中
            self.center_window(win, int(default_width * scale), int(default_height * scale))
            try:
                setattr(win, '_persisted_window_name', window_name)
            except Exception:
                pass
            return int(default_width * scale), int(default_height * scale), None, None
            
        except Exception as e:
            logger.error(f"[load_window_position] 失败: {e}")
            self.center_window(win, int(default_width * self._get_dpi_scale_factor()), int(default_height * self._get_dpi_scale_factor()))
            return default_width, default_height, None, None

    def save_window_position(self, win: Any, window_name: str, file_path: Optional[str] = None) -> None:
        """保存窗口位置到统一配置文件（自动移除当前 DPI 缩放）"""
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
            
        try:
            win.update_idletasks()
            window_name = str(window_name)
            try:
                setattr(win, '_persisted_window_name', window_name)
            except Exception:
                pass
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
            tmp_file = config_file_path + ".tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

                os.replace(tmp_file, config_file_path)
                logger.debug(f"[save_window_position] 已原子保存 {window_name}: {pos}")
            except Exception as e:
                logger.error(f"[save_window_position] 原子保存失败: {e}")
                if os.path.exists(tmp_file): os.remove(tmp_file)


            logger.debug(f"[save_window_position] 已保存 {window_name}: {pos}")
        except Exception as e:
            logger.error(f"[save_window_position] 失败: {e}")

    def collect_all_open_windows(self) -> dict[str, Any]:
        """
        全面收集当前所有打开并关联的 Tk 根窗口、Toplevel 子窗口、监控窗口及关联 Qt 窗口。
        返回字典: {window_name: window_object}
        """
        windows: dict[str, Any] = {}

        # 1. 主窗口 (self)
        try:
            if hasattr(self, 'winfo_exists') and self.winfo_exists():
                windows["main_window"] = self
                try:
                    setattr(self, '_persisted_window_name', "main_window")
                except Exception:
                    pass
        except Exception:
            pass

        # 2. 监控窗口字典 (_pg_top10_window_simple)
        if hasattr(self, "_pg_top10_window_simple") and isinstance(self._pg_top10_window_simple, dict):
            for k, v in list(self._pg_top10_window_simple.items()):
                if isinstance(v, dict):
                    win = v.get("win")
                    if win and hasattr(win, "winfo_exists") and win.winfo_exists():
                        win_key = f"concept_top10_window-{k}"
                        windows[win_key] = win
                        try:
                            setattr(win, '_persisted_window_name', win_key)
                        except Exception:
                            pass

        # 3. 明确属性引用的子窗口
        attr_mappings = [
            ("_concept_win", "detail_window"),
            ("detail_win", "detail_win_Category"),
            ("kline_monitor", "KLineMonitor"),
            ("_detailed_analysis_win", "SystemAnalysis"),
            ("strategy_report_win", "StrategyReport"),
            ("_voice_monitor_win", "VoiceMonitor"),
            ("_realtime_monitor_win", "RealtimeMonitor"),
            ("_stock_selection_win", "StockSelection"),
            ("_multi_period_tester_win", "MultiPeriodTester"),
        ]
        for attr_name, default_key in attr_mappings:
            if hasattr(self, attr_name):
                sub_win = getattr(self, attr_name, None)
                if sub_win and hasattr(sub_win, "winfo_exists") and sub_win.winfo_exists():
                    actual_key = getattr(sub_win, '_persisted_window_name', None) or default_key
                    windows[actual_key] = sub_win
                    try:
                        setattr(sub_win, '_persisted_window_name', actual_key)
                    except Exception:
                        pass

        # 4. 递归/遍历 winfo_children() 发现的所有 Toplevel 顶级子窗口
        try:
            def _scan_children(parent: Any) -> None:
                if not hasattr(parent, 'winfo_children'):
                    return
                for child in parent.winfo_children():
                    if isinstance(child, tk.Toplevel) and child.winfo_exists():
                        # 检查是否已收录
                        if child not in windows.values():
                            key = getattr(child, '_persisted_window_name', None) or getattr(child, '_window_name', None) or getattr(child, '_window_id', None)
                            if not key:
                                try:
                                    t = child.title().strip() if hasattr(child, 'title') else ""
                                    if t:
                                        safe_t = "".join(c for c in t if c.isalnum() or c in ('_', '-', ' ')).strip()
                                        key = f"top_window_{safe_t}" if safe_t else f"top_window_{id(child)}"
                                    else:
                                        key = f"top_window_{id(child)}"
                                except Exception:
                                    key = f"top_window_{id(child)}"

                            final_key = key
                            counter = 1
                            while final_key in windows and windows[final_key] != child:
                                final_key = f"{key}_{counter}"
                                counter += 1

                            windows[final_key] = child
                            try:
                                setattr(child, '_persisted_window_name', final_key)
                            except Exception:
                                pass

                            _scan_children(child)

            if hasattr(self, 'winfo_children'):
                _scan_children(self)
        except Exception as e:
            logger.warning(f"[collect_all_open_windows] 遍历 winfo_children 异常: {e}")

        # 5. 关联的 PyQt 窗口 (_pg_windows)
        if hasattr(self, "_pg_windows") and isinstance(self._pg_windows, dict):
            for k, v in list(self._pg_windows.items()):
                if isinstance(v, dict):
                    qwin = v.get("win")
                    if qwin and ((hasattr(qwin, "isVisible") and qwin.isVisible()) or hasattr(qwin, "geometry")):
                        win_key = f"pg_qt_window_{k}"
                        windows[win_key] = qwin
                        try:
                            setattr(qwin, '_persisted_window_name', win_key)
                        except Exception:
                            pass

        return windows

    def get_snapshot_slots_info(self, file_path: Optional[str] = None) -> dict[int, dict[str, Any]]:
        """
        获取 3 个手动快照槽位的标记信息（年月日、保存时间、持久化窗口数量等）。
        返回: {1: {...}, 2: {...}, 3: {...}}
        """
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE

        scale = self._get_dpi_scale_factor()
        config_file_path = self._get_config_file_path(file_path, scale)

        data = {}
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"[get_snapshot_slots_info] 读取失败: {e}")

        slots_info: dict[int, dict[str, Any]] = {}
        for slot in (1, 2, 3):
            key = f"manual_snapshot_{slot}"
            snapshot = data.get(key)
            # 如果 slot 1 没有单独键，但有兼容的 manual_snapshot 且未标注 slot 或 slot==1
            if not snapshot and slot == 1 and "manual_snapshot" in data:
                compat_snap = data["manual_snapshot"]
                if isinstance(compat_snap, dict) and "windows" in compat_snap:
                    snapshot = compat_snap

            if isinstance(snapshot, dict) and "windows" in snapshot:
                date_ymd = snapshot.get("date_ymd", "")
                if not date_ymd:
                    time_str = str(snapshot.get("time_str", ""))
                    date_ymd = time_str[:10] if len(time_str) >= 10 else ""
                win_count = len(snapshot.get("windows", {}))
                mon_count = len(snapshot.get("monitor_list", []))
                slots_info[slot] = {
                    "slot": slot,
                    "exists": True,
                    "date_ymd": date_ymd,
                    "window_count": win_count,
                    "monitor_count": mon_count,
                    "summary": f"{date_ymd} ({win_count}个窗口)" if date_ymd else f"({win_count}个窗口)",
                    "label": f"槽位 {slot}: {date_ymd} ({win_count}窗)" if date_ymd else f"槽位 {slot}: ({win_count}窗)"
                }
            else:
                slots_info[slot] = {
                    "slot": slot,
                    "exists": False,
                    "date_ymd": "",
                    "window_count": 0,
                    "monitor_count": 0,
                    "summary": "空 / 未保存",
                    "label": f"槽位 {slot}: [空 / 未保存]"
                }

        return slots_info

    def save_all_windows_snapshot(self, slot: int = 1, snapshot_key: Optional[str] = None, file_path: Optional[str] = None) -> dict[str, Any]:
        """
        手动保存快照：全面持久化当前所有打开并关联的 Tk 窗口（及关联 PyQt 窗口）位置、几何与监控业务数据。
        支持 3 个槽位 (slot=1, 2, 3)，标记信息仅选用年月日（如 2026-08-31）及持久化窗口数量。
        """
        import time
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE

        if snapshot_key is None:
            slot = max(1, min(3, int(slot)))
            snapshot_key = f"manual_snapshot_{slot}"
        else:
            slot = 1

        scale = self._get_dpi_scale_factor()
        config_file_path = self._get_config_file_path(file_path, scale)

        all_windows = self.collect_all_open_windows()
        snapshot_windows_pos: dict[str, Any] = {}

        # 1. 抓取所有窗口位置几何信息（DPI 物理归一化）
        for win_name, win in all_windows.items():
            try:
                if hasattr(win, 'winfo_geometry') or (hasattr(win, 'geometry') and not hasattr(win, 'windowHandle')):
                    if hasattr(win, 'update_idletasks'):
                        win.update_idletasks()
                    geom = win.geometry().split('+')
                    size = geom[0].split('x')
                    w = int(int(size[0]) / scale)
                    h = int(int(size[1]) / scale)
                    x = int(int(geom[1]) / scale)
                    y = int(int(geom[2]) / scale)
                    snapshot_windows_pos[win_name] = {
                        "x": x, "y": y, "width": w, "height": h, "type": "tk"
                    }
                elif hasattr(win, 'geometry'):
                    geom = win.geometry()
                    w = int(geom.width() / scale)
                    h = int(geom.height() / scale)
                    x = int(geom.x() / scale)
                    y = int(geom.y() / scale)
                    snapshot_windows_pos[win_name] = {
                        "x": x, "y": y, "width": w, "height": h, "type": "qt"
                    }
            except Exception as ex:
                logger.warning(f"[save_all_windows_snapshot] 提取窗口 {win_name} 位置异常: {ex}")

        # 2. 收集业务数据快照（监控列表）
        monitor_list_data: list[Any] = []
        if hasattr(self, "_pg_top10_window_simple") and isinstance(self._pg_top10_window_simple, dict):
            try:
                self.save_all_monitor_windows()
                for k, v in self._pg_top10_window_simple.items():
                    if isinstance(v, dict) and "stock_info" in v:
                        monitor_list_data.append(v["stock_info"])
            except Exception as ex:
                logger.warning(f"[save_all_windows_snapshot] 保存监控列表元数据异常: {ex}")

        # 3. 收集 UI 状态
        try:
            if hasattr(self, 'save_ui_states'):
                self.save_ui_states()
        except Exception:
            pass

        try:
            if hasattr(self, 'query_manager'):
                self.query_manager.save_search_history(confirm_threshold=9999)
        except Exception:
            pass

        # 4. 构建快照结构（仅记录年月日与持久化窗口数量）
        now_time = time.time()
        date_ymd = time.strftime("%Y-%m-%d", time.localtime(now_time))
        total_wins = len(snapshot_windows_pos)
        tag_label = f"{date_ymd} ({total_wins}个窗口)"

        snapshot_payload = {
            "slot": slot,
            "timestamp": now_time,
            "date_ymd": date_ymd,
            "tag_label": tag_label,
            "total_windows": total_wins,
            "scale": scale,
            "windows": snapshot_windows_pos,
            "monitor_list": monitor_list_data
        }

        # 5. 原子安全写盘
        try:
            data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    logger.error(f"[save_all_windows_snapshot] 读取原配置失败: {e}")

            # 存储指定槽位
            data[snapshot_key] = snapshot_payload
            # 同步更新通用槽 manual_snapshot
            data["manual_snapshot"] = snapshot_payload
            data["last_snapshot_slot"] = slot

            # 兼容老版本键与独立 _manual 键
            if "main_window" in snapshot_windows_pos:
                data["main_window_manual"] = {
                    k: v for k, v in snapshot_windows_pos["main_window"].items() if k in ("x", "y", "width", "height")
                }
            for wname, pos_dict in snapshot_windows_pos.items():
                data[f"{wname}_manual"] = {
                    k: v for k, v in pos_dict.items() if k in ("x", "y", "width", "height")
                }

            tmp_file = config_file_path + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_file, config_file_path)

            logger.info(f"✅ [save_all_windows_snapshot] 成功保存全量快照(槽位{slot}): {tag_label}, {len(monitor_list_data)} 条监控列表项")
        except Exception as e:
            logger.error(f"❌ [save_all_windows_snapshot] 写盘失败: {e}")
            if 'tmp_file' in locals() and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

        return {
            "success": True,
            "slot": slot,
            "date_ymd": date_ymd,
            "tag_label": tag_label,
            "total_windows": total_wins,
            "window_names": list(snapshot_windows_pos.keys()),
            "monitor_count": len(monitor_list_data),
            "snapshot_data": snapshot_payload
        }

    def restore_all_windows_snapshot(self, slot: Optional[int] = None, snapshot_key: Optional[str] = None, file_path: Optional[str] = None) -> tuple[int, list[str]]:
        """
        恢复手动快照：恢复全部手动保存快照持久化的所有打开窗口位置，自适应当前屏幕与 DPI。
        支持从指定槽位 (slot=1, 2, 3) 恢复。
        返回: (成功恢复窗口数, 成功恢复窗口名称列表)
        """
        if file_path is None:
            file_path = WINDOW_CONFIG_FILE

        scale = self._get_dpi_scale_factor()
        config_file_path = self._get_config_file_path(file_path, scale)

        if not os.path.exists(config_file_path):
            logger.warning(f"[restore_all_windows_snapshot] 配置文件不存在: {config_file_path}")
            return 0, []

        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[restore_all_windows_snapshot] 读取配置文件失败: {e}")
            return 0, []

        # 确定快照 key
        if snapshot_key is None:
            if slot is not None:
                slot = max(1, min(3, int(slot)))
                snapshot_key = f"manual_snapshot_{slot}"
            else:
                snapshot_key = "manual_snapshot"

        # 检查快照
        snapshot = data.get(snapshot_key)
        # 如果特定槽位没找到但查找的是默认槽位，尝试获取最近槽位
        if not snapshot and snapshot_key == "manual_snapshot":
            last_slot = data.get("last_snapshot_slot", 1)
            snapshot = data.get(f"manual_snapshot_{last_slot}") or data.get("manual_snapshot_1")

        saved_windows_pos: dict[str, Any] = {}

        if isinstance(snapshot, dict) and "windows" in snapshot:
            saved_windows_pos = snapshot["windows"]
        else:
            # 兼容回退机制：若无 manual_snapshot 节点，尝试从所有以 _manual 结尾的键恢复
            for k, v in data.items():
                if k.endswith("_manual") and isinstance(v, dict):
                    base_k = k[:-7]
                    saved_windows_pos[base_k] = v

        if not saved_windows_pos:
            logger.warning(f"[restore_all_windows_snapshot] 槽位 {snapshot_key} 尚无快照数据")
            return 0, []

        # 收集当前已打开的所有窗口
        current_open_windows = self.collect_all_open_windows()
        restored_names: list[str] = []

        # 1. 恢复主窗口 (优先处理)
        if "main_window" in current_open_windows and "main_window" in saved_windows_pos:
            try:
                pos = saved_windows_pos["main_window"]
                main_win = current_open_windows["main_window"]
                w = int(pos.get("width", 1200) * scale)
                h = int(pos.get("height", 480) * scale)
                x = int(pos.get("x", 100) * scale)
                y = int(pos.get("y", 100) * scale)
                x, y = clamp_window_to_screens(x, y, w, h)
                main_win.geometry(f"{w}x{h}+{x}+{y}")
                if hasattr(main_win, 'update_idletasks'):
                    main_win.update_idletasks()
                restored_names.append("main_window")
                logger.debug(f"[restore_all_windows_snapshot] 主窗口已恢复: {w}x{h}+{x}+{y}")
            except Exception as e:
                logger.warning(f"[restore_all_windows_snapshot] 恢复主窗口异常: {e}")

        # 2. 遍历当前已打开的其他窗口进行精准恢复
        for win_name, win in current_open_windows.items():
            if win_name == "main_window":
                continue

            # 在快照中查找匹配项
            pos = saved_windows_pos.get(win_name)
            if not pos:
                for k, v in saved_windows_pos.items():
                    if k == win_name or k.endswith(win_name) or win_name.endswith(k):
                        pos = v
                        break

            if pos and isinstance(pos, dict):
                try:
                    w = int(pos.get("width", 500) * scale)
                    h = int(pos.get("height", 400) * scale)
                    x = int(pos.get("x", 100) * scale)
                    y = int(pos.get("y", 100) * scale)

                    # 防止换屏越界
                    x, y = clamp_window_to_screens(x, y, w, h)

                    if hasattr(win, 'winfo_geometry') or (hasattr(win, 'geometry') and not hasattr(win, 'windowHandle')):
                        win.geometry(f"{w}x{h}+{x}+{y}")
                        if hasattr(win, 'update_idletasks'):
                            win.update_idletasks()
                    elif hasattr(win, 'setGeometry'):
                        win.setGeometry(x, y, w, h)

                    restored_names.append(win_name)
                    logger.debug(f"[restore_all_windows_snapshot] 窗口 {win_name} 已恢复: {w}x{h}+{x}+{y}")
                except Exception as e:
                    logger.warning(f"[restore_all_windows_snapshot] 恢复窗口 {win_name} 异常: {e}")

        slot_label = f" (槽位{snapshot.get('slot', '')})" if isinstance(snapshot, dict) and "slot" in snapshot else ""
        logger.info(f"✅ [restore_all_windows_snapshot] 全量快照恢复完成{slot_label}: 共 {len(restored_names)} 个窗口已归位")
        return len(restored_names), restored_names

    def _get_available_geometry_qt(self, window=None):
        """
        安全获取 Qt 可用屏幕几何，适用于多屏和 Tk 多进程环境。
        返回 QRect 或 None
        """
        app = None
        screen = None

        # 1️⃣ 尝试获取 QApplication 实例（先检查）
        try:
            from PyQt6 import QtWidgets
            app = QtWidgets.QApplication.instance()
        except Exception:
            app = None

        # 2️⃣ 优先使用窗口所属 screen（最可靠）
        if window is not None:
            try:
                wh = window.windowHandle()
                if wh is not None and wh.screen() is not None:
                    screen = wh.screen()
            except Exception:
                screen = None

        # 3️⃣ 回退 primaryScreen（允许为 None）
        if screen is None and app is not None:
            try:
                primary = app.primaryScreen()
                if primary is not None:
                    screen = primary
            except Exception:
                screen = None

        # 4️⃣ 最终兜底
        if screen is not None:
            return screen.availableGeometry()

        return None


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
                    logger.debug(f"[load_window_position_qt] 加载 {config_file_path} {window_name}: {width}x{height} {x}+{y}")

            if x is None or y is None:
                geo = self._get_available_geometry_qt(win)
                if geo is not None:
                    x = (geo.width() - width) // 2
                    y = (geo.height() - height) // 2
                else:
                    # ⭐ 永远不会崩的兜底
                    x, y = 100, 100
                # if PYQT5_AVAILABLE:
                #     screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
                #     x = (screen.width() - width) // 2
                #     y = (screen.height() - height) // 2
                # else:
                #     x, y = 100, 100

            

            if x is not None and y is not None:
                if hasattr(self, "_pg_windows"):
                    active_windows = [w["win"] for w in self._pg_windows.values() if w.get("win") and w["win"] != win]
                    for aw in active_windows:
                        if aw.x() == x and aw.y() == y:
                            x += offset_step
                            y += offset_step

            # [SAFE-GUARD] 避免因设定尺寸小于窗口物理最小尺寸(MinimumSizeHint/MinimumSize)导致的 Qt 警告与高频 setGeometry 刷屏
            try:
                if hasattr(win, "minimumSizeHint"):
                    min_hint = win.minimumSizeHint()
                    if min_hint.isValid():
                        if min_hint.width() > 0:
                            width = max(width, min_hint.width())
                        if min_hint.height() > 0:
                            height = max(height, min_hint.height())
                if hasattr(win, "minimumSize"):
                    min_size = win.minimumSize()
                    if min_size.width() > 0:
                        width = max(width, min_size.width())
                    if min_size.height() > 0:
                        height = max(height, min_size.height())
            except Exception as ex:
                logger.debug(f"[load_window_position_qt] 最小尺寸防御检查忽略: {ex}")

            win.setGeometry(x, y, width, height)
            try:
                setattr(win, '_persisted_window_name', window_name)
            except Exception:
                pass
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
            try:
                setattr(win, '_persisted_window_name', window_name)
            except Exception:
                pass
            scale = self._get_dpi_scale_factor()

            geom = win.geometry()
            width = max(130, int(geom.width() / scale))
            height = max(150, int(geom.height() / scale))
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
                    logger.error(f"[save_window_position_qt] {config_file_path} 读取失败: {e}")

            data[window_name] = pos
            tmp_file = config_file_path + ".tmp"
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

                os.replace(tmp_file, config_file_path)
                logger.debug(f"[save_window_position_qt] 已原子保存 {window_name}: {pos}")
            except Exception as e:
                logger.error(f"[save_window_position_qt] 原子保存失败: {e}")
                if os.path.exists(tmp_file): os.remove(tmp_file)


            logger.debug(f"[save_window_position_qt] {config_file_path} 已保存 {window_name}: {pos}")
        except Exception as e:
            logger.error(f"[save_window_position_qt] {file_path} 失败: {e}")

    def save_window_position_qt_visual(self, win: Any, window_name: str, file_path: Optional[str] = None) -> None:
        """保存 PyQt 窗口 position (防抖 5s)"""
        import time
        
        # [NEW] 防抖逻辑
        if not hasattr(self, "_window_save_debounce"):
            self._window_save_debounce = {}
            
        current_time = time.time()
        last_time = self._window_save_debounce.get(window_name, 0)
        
        if current_time - last_time < 5:
            # logger.debug(f"[save_window_position_qt_visual] Debounced {window_name} (skipped)")
            return

        self._window_save_debounce[window_name] = current_time

        if file_path is None:
            file_path = WINDOW_CONFIG_FILE
        try:
            window_name = str(window_name)
            try:
                setattr(win, '_persisted_window_name', window_name)
            except Exception:
                pass
            scale = self._get_dpi_scale_factor()

            geom = win.geometry()
            # width = max(130, min(int(geom.width() / scale), 500))
            # height = max(150, min(int(geom.height() / scale), 450))
            width = int(geom.width() / scale)
            height = int(geom.height() / scale)
            pos = {
                "x": int(geom.x() / scale),
                "y": int(geom.y() / scale),
                "width": width,
                "height": height
            }

            config_file_path = self._get_config_file_path(file_path, scale)

            # [OPTIMIZE] 读取现有数据,检查是否有变化
            data = {}
            data_changed = True  # 默认认为数据有变化
            
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # 检查该窗口的位置数据是否发生变化
                    if window_name in data:
                        old_pos = data[window_name]
                        # 比较所有字段
                        if (old_pos.get('x') == pos['x'] and 
                            old_pos.get('y') == pos['y'] and 
                            old_pos.get('width') == pos['width'] and 
                            old_pos.get('height') == pos['height']):
                            data_changed = False
                            
                except Exception as e:
                    logger.error(f"[save_window_position_qt] {config_file_path} 读取失败: {e}")

            # [OPTIMIZE] 只有数据变化时才写盘
            # [OPTIMIZE] 只有数据变化时才写盘
            if data_changed:
                data[window_name] = pos
                tmp_file = config_file_path + ".tmp"
                try:
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                    os.replace(tmp_file, config_file_path)
                    logger.debug(f"[save_window_position_qt] {config_file_path} 已原子保存 {window_name}: {pos}")
                except Exception as e:
                    logger.error(f"[save_window_position_qt] 原子写入失败: {e}")
                    if os.path.exists(tmp_file): os.remove(tmp_file)
            else:

                logger.debug(f"[save_window_position_qt] {config_file_path} 跳过保存 {window_name}: 数据未变化")
                
        except Exception as e:
            logger.error(f"[save_window_position_qt] 失败: {e}")


    def center_window(self, win: Any, width: int, height: int) -> None:
        """将指定窗口居中显示"""
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")

    def update_status_bar_width(self, pw: Any, left_frame: Any, right_frame: Any) -> None:
        """ 根据 DPI 缩放调整左右面板的宽度比例，使用 paneconfig 避免重新构造 """
        sf = self._get_dpi_scale_factor()
        left_width = int(900 * sf)
        right_width = int(100 * sf)
        
        try:
            # 检查面板是否已添加
            panes = pw.panes()
            if str(left_frame) in panes and str(right_frame) in panes:
                # 已存在则仅更新宽度和最小宽度
                pw.paneconfig(left_frame, minsize=int(100 * sf), width=left_width)
                pw.paneconfig(right_frame, minsize=int(100 * sf), width=right_width)
            else:
                # 不存在则添加
                pw.add(left_frame, minsize=int(100 * sf), width=left_width)
                pw.add(right_frame, minsize=int(100 * sf), width=right_width)
        except Exception as e:
            logger.warning(f"[update_status_bar_width] 更新状态栏宽度失败: {e}")
            # 降级方案：传统的 forget/add
            try:
                pw.forget(left_frame)
                pw.forget(right_frame)
                pw.add(left_frame, minsize=100, width=left_width)
                pw.add(right_frame, minsize=100, width=right_width)
            except:
                pass

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

        logger.debug(f"正在恢复 {len(monitor_data)} 个监控窗口...")
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
                        logger.debug(f"恢复窗口 {unique_code}: {concept_name} ({code})")
            except Exception as e:
                logger.info(f"恢复窗口失败: {m}, 错误: {e}")

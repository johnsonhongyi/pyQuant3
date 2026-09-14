# -*- coding: utf-8 -*-
"""
ATS Window Manager (多窗口独立快照管理与多显示器防覆盖引擎)
对齐 Tkinter 3 槽位快照体系，全面支持：
1. 3 个独立槽位 (slot 1, 2, 3) 覆盖保存与元信息追踪 (年月日、时间戳、窗口数量)
2. 全量 ATS 窗口状态物理持久化至 window_config.json
3. 多显示器切换边界智能校准 (Screen Clamping)，彻底消除拔插副屏/换屏导致的窗口被覆盖和越界消失
4. 恢复时级联错峰展开 (Cascade Anti-Overlap) 与前台置顶唤醒 (showNormal, raise_, activateWindow)
"""

import os
import json
import time
from typing import Any, Optional, Tuple, Dict, List

from PyQt6.QtWidgets import QApplication, QWidget, QDialog, QMainWindow, QMenu
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer
from PyQt6.QtGui import QAction

from sys_utils import get_app_root, get_conf_path
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("ATS.WindowManager")


def _safe_isdeleted(obj: Any) -> bool:
    """安全检查 Qt C++ 底层对象是否已被销毁 (防御普通对象与 Mock 场景)"""
    if obj is None:
        return True
    try:
        from PyQt6.sip import isdeleted, simplewrapper
        if isinstance(obj, simplewrapper):
            return isdeleted(obj)
    except Exception:
        pass
    return False


class ATSWindowManager:
    """ATS 多窗口独立快照管理器 (单例)"""
    _instance: Optional["ATSWindowManager"] = None

    @classmethod
    def get_instance(cls) -> "ATSWindowManager":
        if cls._instance is None:
            cls._instance = ATSWindowManager()
        return cls._instance

    def __init__(self):
        self._config_file = self._resolve_config_file()

    def _resolve_config_file(self) -> str:
        """获取 window_config.json 物理路径"""
        base_dir = get_app_root()
        path = get_conf_path("window_config.json", base_dir)
        if not path:
            path = os.path.join(base_dir, "window_config.json")
        return str(path)

    def _get_dpi_scale_config_files(self) -> List[str]:
        """获取当前以及高分屏 DPI 缩放下的对应配置文件列表"""
        files = [self._config_file]
        base, filename = os.path.split(self._config_file)
        scale2_path = os.path.join(base, "scale2_window_config.json")
        if scale2_path not in files:
            files.append(scale2_path)
        return files

    def get_snapshot_slots_info(self) -> Dict[int, Dict[str, Any]]:
        """
        获取 3 个手动快照槽位的标记信息（年月日、保存时间、持久化窗口数量等）。
        返回: {1: {...}, 2: {...}, 3: {...}}
        """
        data = {}
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"[get_snapshot_slots_info] 读取失败: {e}")

        slots_info: Dict[int, Dict[str, Any]] = {}
        for slot in (1, 2, 3):
            # 优先读取 ATS 专属槽位，其次兼容回退到通用 manual_snapshot 槽位
            key = f"ats_manual_snapshot_{slot}"
            snapshot = data.get(key)
            if not snapshot:
                tk_key = f"manual_snapshot_{slot}"
                snapshot = data.get(tk_key)
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
                slots_info[slot] = {
                    "slot": slot,
                    "exists": True,
                    "date_ymd": date_ymd,
                    "window_count": win_count,
                    "summary": f"{date_ymd} ({win_count}个窗口)" if date_ymd else f"({win_count}个窗口)",
                    "label": f"槽位 {slot}: {date_ymd} ({win_count}个窗口)" if date_ymd else f"槽位 {slot}: ({win_count}个窗口)"
                }
            else:
                slots_info[slot] = {
                    "slot": slot,
                    "exists": False,
                    "date_ymd": "",
                    "window_count": 0,
                    "summary": "空 / 未保存",
                    "label": f"槽位 {slot}: [空 / 未保存]"
                }

        return slots_info

    def get_snapshot_tooltip_text(self, action_prefix: str = "📍 手动保存全量快照") -> str:
        """生成鼠标悬停 ToolTip 提示文本（对齐 Tk 体验）"""
        try:
            slots = self.get_snapshot_slots_info()
            lines = [f"{action_prefix}（提供3个保存位置）："]
            for s in (1, 2, 3):
                info = slots.get(s, {})
                if info.get("exists"):
                    lines.append(f"  • 槽位 {s}: {info.get('date_ymd', '')} ({info.get('window_count', 0)}个窗口)")
                else:
                    lines.append(f"  • 槽位 {s}: [空 / 未保存]")
            lines.append("（点击弹出选择菜单）")
            return "\n".join(lines)
        except Exception:
            return f"{action_prefix}（提供3个保存位置，点击选择）"

    def collect_all_ats_windows(self, main_window: Optional[Any] = None) -> Dict[str, Any]:
        """
        全量收集当前所有打开且有效的 ATS 顶级窗口、监控看板与详情弹窗。
        返回: {window_key: window_instance}
        """
        windows: Dict[str, Any] = {}

        # 1. 主窗口
        if main_window is not None and not _safe_isdeleted(main_window):
            windows["ats_main_window"] = main_window
        else:
            app = QApplication.instance()
            if app and hasattr(app, "main_window") and app.main_window and not _safe_isdeleted(app.main_window):
                windows["ats_main_window"] = app.main_window

        mw = windows.get("ats_main_window")

        # 2. 收集主窗口引用的各个独立子看板
        if mw:
            # 2.1 龙头中枢监控
            dmd = getattr(mw, "dragon_monitor_dialog", None)
            if dmd and not _safe_isdeleted(dmd) and (dmd.isVisible() or getattr(dmd, "is_hidden_state", False)):
                windows["dragon_leader_monitor_dialog"] = dmd

            # 2.2 每日涨停与天梯看板
            zt = getattr(mw, "daily_limit_up_dialog", None)
            if zt and not _safe_isdeleted(zt) and (zt.isVisible() or getattr(zt, "is_hidden_state", False)):
                windows["daily_limit_up_dialog"] = zt

            # 2.3 Top 3 强势板块跟单榜
            hot = getattr(mw, "hot_sector_dialog", None)
            if hot and not _safe_isdeleted(hot) and (hot.isVisible() or getattr(hot, "is_hidden_state", False)):
                windows["hot_sector_leaderboard_dialog"] = hot

            # 2.4 个股多维全景详情弹窗
            detail = getattr(mw, "_detail_dialog", None)
            if detail and not _safe_isdeleted(detail) and detail.isVisible():
                windows["stock_detail_dialog"] = detail

            # 2.5 板块成分股明细弹窗
            sdetail = getattr(mw, "_sector_detail_dialog", None)
            if sdetail and not _safe_isdeleted(sdetail) and sdetail.isVisible():
                windows["sector_detail_dialog"] = sdetail

            # 2.6 板块轮动深挖工作台
            miner = getattr(mw, "_sector_rotation_miner_win", None)
            if miner and not _safe_isdeleted(miner) and miner.isVisible():
                windows["sector_rotation_miner_dialog"] = miner

            # 2.7 涨跌分布个股明细窗口列表
            dist_chart = getattr(mw, "dist_chart", None)
            if dist_chart and hasattr(dist_chart, "_active_dialogs"):
                for idx, d in enumerate(dist_chart._active_dialogs):
                    if d and not _safe_isdeleted(d) and (d.isVisible() or getattr(d, "is_hidden_state", False)):
                        windows[f"distribution_detail_dialog_{idx}"] = d

        # 3. 模块级单例独立窗口
        # 3.1 全球外盘看板
        try:
            from ats.ui import global_market_dialog as gmd
            if hasattr(gmd, "_dialog_instance") and gmd._dialog_instance and not _safe_isdeleted(gmd._dialog_instance):
                if gmd._dialog_instance.isVisible():
                    windows["global_market_dialog"] = gmd._dialog_instance
        except Exception:
            pass

        # 3.2 多周期联动策略筛选器
        try:
            from ats.ui import multi_period_dialog as mpd
            if hasattr(mpd, "_dialog_instance") and mpd._dialog_instance and not _safe_isdeleted(mpd._dialog_instance):
                if mpd._dialog_instance.isVisible():
                    windows["multi_period_dialog"] = mpd._dialog_instance
        except Exception:
            pass

        # 3.3 SBC 独立分时走势图窗口列表
        try:
            from ats.ui import intraday_strategy_dialog as isd
            if hasattr(isd, "_active_sbc_windows") and isinstance(isd._active_sbc_windows, dict):
                for code, win in isd._active_sbc_windows.items():
                    if win and not _safe_isdeleted(win) and win.isVisible():
                        windows[f"sbc_dialog_{code}"] = win
        except Exception:
            pass

        # 4. 全局扫描 topLevelWidgets，查漏补缺任意其他未注册的可见顶层独立窗口
        try:
            for w in QApplication.topLevelWidgets():
                if not w or _safe_isdeleted(w) or not w.isWindow() or not w.isVisible():
                    continue
                # 排除系统菜单、悬浮提示框等无标题栏弹层
                w_type = w.windowType()
                if w_type in (Qt.WindowType.ToolTip, Qt.WindowType.Popup):
                    continue
                if w in windows.values():
                    continue

                obj_name = w.objectName()
                cls_name = w.__class__.__name__
                if not obj_name:
                    obj_name = cls_name
                key = f"qt_win_{obj_name}_{id(w)}"
                windows[key] = w
        except Exception as e:
            logger.warning(f"[collect_all_ats_windows] 扫描 topLevelWidgets 异常: {e}")

        return windows

    def save_snapshot(self, slot: int = 1, main_window: Optional[Any] = None) -> Dict[str, Any]:
        """
        手动保存快照：全面持久化当前所有打开并关联的 ATS 窗口位置、几何与显示器分布状态。
        支持 3 个槽位 (slot=1, 2, 3)，原子写盘。
        """
        slot = max(1, min(3, int(slot)))
        snapshot_key = f"ats_manual_snapshot_{slot}"

        windows = self.collect_all_ats_windows(main_window)
        windows_pos: Dict[str, Any] = {}

        for win_name, win in windows.items():
            try:
                geom = win.geometry()
                pos_item = {
                    "x": int(geom.x()),
                    "y": int(geom.y()),
                    "width": int(geom.width()),
                    "height": int(geom.height()),
                    "is_maximized": bool(win.isMaximized()) if hasattr(win, "isMaximized") and callable(win.isMaximized) else False,
                    "is_open": True,
                }
                # 记录折叠与置顶附加状态 (防御普通对象与 Mock)
                hidden_st = getattr(win, "is_hidden_state", None)
                if isinstance(hidden_st, bool):
                    pos_item["is_hidden_state"] = hidden_st
                ontop_st = getattr(win, "stays_on_top", None)
                if isinstance(ontop_st, bool):
                    pos_item["stays_on_top"] = ontop_st

                # 记录个股或板块特征标识
                sel_code = getattr(win, "selected_code", None)
                if isinstance(sel_code, (str, int)):
                    pos_item["code"] = str(sel_code)
                else:
                    c = getattr(win, "code", None)
                    if isinstance(c, (str, int)):
                        pos_item["code"] = str(c)

                sec_name = getattr(win, "sector_name", None)
                if isinstance(sec_name, str):
                    pos_item["sector_name"] = sec_name

                windows_pos[win_name] = pos_item
            except Exception as ex:
                logger.warning(f"[save_snapshot] 提取窗口 {win_name} 位置异常: {ex}")

        # 记录屏幕拓扑结构快照
        screens_info = []
        try:
            for s in QApplication.screens():
                g = s.geometry()
                ag = s.availableGeometry()
                screens_info.append({
                    "name": s.name(),
                    "x": g.x(), "y": g.y(), "width": g.width(), "height": g.height(),
                    "avail_x": ag.x(), "avail_y": ag.y(), "avail_w": ag.width(), "avail_h": ag.height(),
                    "dpr": s.devicePixelRatio()
                })
        except Exception:
            pass

        now_time = time.time()
        date_ymd = time.strftime("%Y-%m-%d", time.localtime(now_time))
        total_wins = len(windows_pos)
        tag_label = f"{date_ymd} ({total_wins}个窗口)"

        snapshot_payload = {
            "slot": slot,
            "timestamp": now_time,
            "date_ymd": date_ymd,
            "tag_label": tag_label,
            "total_windows": total_wins,
            "screens": screens_info,
            "windows": windows_pos
        }

        # 原子写入所有配置文件（同时同步 scale2 保持高分屏互通）
        target_files = self._get_dpi_scale_config_files()
        write_success = False

        for cfg_file in target_files:
            try:
                data = {}
                if os.path.exists(cfg_file):
                    try:
                        with open(cfg_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception as e:
                        logger.error(f"[save_snapshot] 读取原配置失败: {e}")

                data[snapshot_key] = snapshot_payload
                data["ats_last_snapshot_slot"] = slot

                # 同步更新主窗口与各个子窗口的常规记忆键
                for wname, pinfo in windows_pos.items():
                    data[f"{wname}_manual_{slot}"] = {
                        k: v for k, v in pinfo.items() if k in ("x", "y", "width", "height", "is_open")
                    }
                    data[wname] = {
                        k: v for k, v in pinfo.items() if k in ("x", "y", "width", "height", "is_open")
                    }

                tmp_file = cfg_file + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                os.replace(tmp_file, cfg_file)
                write_success = True
                logger.info(f"✅ [save_snapshot] 成功保存全量快照(槽位{slot})到 {cfg_file}: {tag_label}")
            except Exception as e:
                logger.error(f"❌ [save_snapshot] 写盘失败 ({cfg_file}): {e}")

        return {
            "success": write_success,
            "slot": slot,
            "date_ymd": date_ymd,
            "tag_label": tag_label,
            "total_windows": total_wins,
            "window_names": list(windows_pos.keys()),
            "snapshot_data": snapshot_payload
        }

    def clamp_to_screens_qt(self, x: int, y: int, w: int, h: int, cascade_idx: int = 0) -> Tuple[int, int, int, int]:
        """
        在 Qt 逻辑坐标系下校验多显示器边界，杜绝跨屏切换、拔插副屏或高分屏缩放导致的窗口越界、消失或被死死覆盖。
        1. 若窗口中心所在的屏幕依然存在，则安全 clamp 在该屏幕的 availableGeometry 内；
        2. 若窗口原本所在的副屏已断开，则智能回退到主屏幕，并应用错峰展开 (Cascade Anti-Overlap)，
           使每个窗口的标题栏与边缘露出一角，彻底杜绝所有窗口以相同坐标死死覆盖在主窗口正中心！
        """
        screens = QApplication.screens()
        if not screens:
            return x, y, max(300, w), max(200, h)

        cx = x + w // 2
        cy = y + h // 2
        target_scr = None

        # 检查中心点是否落在某个连接屏幕的 geometry 内
        for scr in screens:
            if scr.geometry().contains(QPoint(cx, cy)):
                target_scr = scr
                break

        # 如果中心点未落在任何屏幕上，尝试计算重叠面积最大的屏幕
        if target_scr is None:
            win_rect = QRect(x, y, w, h)
            best_overlap = 0
            for scr in screens:
                overlap_rect = scr.geometry().intersected(win_rect)
                area = overlap_rect.width() * overlap_rect.height()
                if area > best_overlap:
                    best_overlap = area
                    target_scr = scr

        if target_scr is not None:
            # 屏幕存在：在目标屏幕可用区域内严格校准 (规避任务栏)
            avail = target_scr.availableGeometry()
            rw = max(300, min(w, avail.width()))
            rh = max(200, min(h, avail.height()))
            rx = max(avail.left(), min(x, avail.right() - rw))
            ry = max(avail.top(), min(y, avail.bottom() - rh))
            return rx, ry, rw, rh
        else:
            # 屏幕已断开 (副屏被拔掉/切换单屏)：回退到主屏并应用防覆盖错峰展开 (Cascade Anti-Overlap)
            prim_scr = QApplication.primaryScreen() or screens[0]
            avail = prim_scr.availableGeometry()
            rw = max(300, min(w, avail.width()))
            rh = max(200, min(h, avail.height()))

            max_offset_x = max(30, avail.width() - rw)
            max_offset_y = max(30, avail.height() - rh)
            offset_x = (cascade_idx * 30) % max_offset_x
            offset_y = (cascade_idx * 30) % max_offset_y

            base_x = avail.left() + 40 + offset_x
            base_y = avail.top() + 40 + offset_y
            rx = max(avail.left(), min(base_x, avail.right() - rw))
            ry = max(avail.top(), min(base_y, avail.bottom() - rh))
            return rx, ry, rw, rh

    def restore_snapshot(self, slot: int = 1, main_window: Optional[Any] = None) -> Tuple[int, List[str]]:
        """
        恢复手动快照：恢复全部手动保存快照持久化的所有打开窗口位置，自适应当前屏幕与 DPI。
        解决切换显示器时的被覆盖问题，消除重叠并置顶唤醒。
        返回: (成功恢复窗口数, 成功恢复窗口名称列表)
        """
        slot = max(1, min(3, int(slot)))
        snapshot_key = f"ats_manual_snapshot_{slot}"

        data = {}
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"[restore_snapshot] 读取配置文件失败: {e}")
                return 0, []

        snapshot = data.get(snapshot_key)
        if not snapshot:
            snapshot = data.get(f"manual_snapshot_{slot}")

        if not isinstance(snapshot, dict) or "windows" not in snapshot:
            logger.warning(f"[restore_snapshot] 槽位 {slot} 尚无有效快照数据")
            return 0, []

        saved_windows_pos: Dict[str, Any] = snapshot["windows"]
        if not saved_windows_pos:
            return 0, []

        # 收集当前已打开的所有窗口
        current_windows = self.collect_all_ats_windows(main_window)
        restored_names: List[str] = []
        mw = current_windows.get("ats_main_window")

        # 1. 优先恢复主窗口 (优先处理主窗口，作为底层基准)
        if "ats_main_window" in current_windows and "ats_main_window" in saved_windows_pos:
            try:
                pos = saved_windows_pos["ats_main_window"]
                main_win = current_windows["ats_main_window"]
                x = pos.get("x", 50)
                y = pos.get("y", 50)
                w = pos.get("width", 1440)
                h = pos.get("height", 900)
                rx, ry, rw, rh = self.clamp_to_screens_qt(x, y, w, h, cascade_idx=0)
                if pos.get("is_maximized", False):
                    main_win.showMaximized()
                else:
                    main_win.showNormal()
                    main_win.setGeometry(rx, ry, rw, rh)
                restored_names.append("ats_main_window")
                logger.debug(f"[restore_snapshot] 主窗口已精准归位: {rw}x{rh}+{rx}+{ry}")
            except Exception as e:
                logger.warning(f"[restore_snapshot] 恢复主窗口异常: {e}")

        # 2. 遍历恢复其余子窗口 (按序号应用错峰展开，彻底消除覆盖)
        cascade_counter = 1
        for win_name, pos in saved_windows_pos.items():
            if win_name == "ats_main_window":
                continue

            target_win = current_windows.get(win_name)

            # 如果当前未打开该窗口，但快照中记录了它为打开状态，尝试通过主窗口方法唤起
            if target_win is None and mw and pos.get("is_open", False):
                try:
                    if win_name == "dragon_leader_monitor_dialog" and hasattr(mw, "open_dragon_monitor"):
                        mw.open_dragon_monitor(cold_start=True)
                        target_win = getattr(mw, "dragon_monitor_dialog", None)
                    elif win_name == "daily_limit_up_dialog" and hasattr(mw, "open_daily_limit_up_analyzer"):
                        mw.open_daily_limit_up_analyzer(cold_start=True)
                        target_win = getattr(mw, "daily_limit_up_dialog", None)
                    elif win_name == "hot_sector_leaderboard_dialog" and hasattr(mw, "open_hot_sector_leaderboard"):
                        mw.open_hot_sector_leaderboard(cold_start=True)
                        target_win = getattr(mw, "hot_sector_dialog", None)
                    elif win_name == "sector_rotation_miner_dialog" and hasattr(mw, "open_sector_rotation_miner"):
                        mw.open_sector_rotation_miner()
                        target_win = getattr(mw, "_sector_rotation_miner_win", None)
                    elif win_name == "global_market_dialog" and hasattr(mw, "open_global_market_dialog"):
                        mw.open_global_market_dialog()
                        from ats.ui import global_market_dialog as gmd
                        target_win = getattr(gmd, "_dialog_instance", None)
                    elif win_name == "multi_period_dialog" and hasattr(mw, "open_multi_period_tester"):
                        mw.open_multi_period_tester()
                        from ats.ui import multi_period_dialog as mpd
                        target_win = getattr(mpd, "_dialog_instance", None)
                except Exception as ex_open:
                    logger.warning(f"[restore_snapshot] 自动唤醒窗口 {win_name} 失败: {ex_open}")

            if target_win is not None:
                try:
                    x = pos.get("x", 100)
                    y = pos.get("y", 100)
                    w = pos.get("width", 800)
                    h = pos.get("height", 600)
                    rx, ry, rw, rh = self.clamp_to_screens_qt(x, y, w, h, cascade_idx=cascade_counter)
                    cascade_counter += 1

                    if hasattr(target_win, "isMaximized") and pos.get("is_maximized", False):
                        target_win.showMaximized()
                    else:
                        if hasattr(target_win, "showNormal"):
                            target_win.showNormal()
                        elif hasattr(target_win, "show"):
                            target_win.show()
                        target_win.setGeometry(rx, ry, rw, rh)

                    # 若该窗口具备折叠/吸附状态属性，同步恢复
                    if hasattr(target_win, "normal_geometry"):
                        setattr(target_win, "normal_geometry", QRect(rx, ry, rw, rh))
                    if hasattr(target_win, "stays_on_top") and "stays_on_top" in pos:
                        setattr(target_win, "stays_on_top", pos["stays_on_top"])

                    # 前台置顶唤醒，清除被覆盖状态
                    if hasattr(target_win, "raise_"):
                        target_win.raise_()
                    if hasattr(target_win, "activateWindow"):
                        target_win.activateWindow()

                    restored_names.append(win_name)
                    logger.debug(f"[restore_snapshot] 窗口 {win_name} 已归位: {rw}x{rh}+{rx}+{ry}")
                except Exception as e:
                    logger.warning(f"[restore_snapshot] 恢复窗口 {win_name} 异常: {e}")

        slot_label = f" (槽位{slot})"
        logger.info(f"✅ [restore_snapshot] 快照恢复完成{slot_label}: 共 {len(restored_names)} 个窗口已归位，覆盖消除")
        return len(restored_names), restored_names

    def build_save_menu(self, parent_widget: QWidget, on_slot_selected_cb) -> QMenu:
        """构建保存快照弹出菜单（100% 对齐图 1）"""
        slots_info = self.get_snapshot_slots_info()
        menu = QMenu(parent_widget)
        self._apply_menu_style(menu)

        # 标题项 (禁用不可选)
        header_act = menu.addAction("📍 选择要保存快照的位置 (覆盖保存):")
        header_act.setEnabled(False)
        menu.addSeparator()

        for s in (1, 2, 3):
            info = slots_info.get(s, {})
            if info.get("exists"):
                label = f"📌 槽位 {s}: {info.get('date_ymd', '')} ({info.get('window_count', 0)}个窗口)"
            else:
                label = f"⚪ 槽位 {s}: [空 / 点击保存]"
            act = menu.addAction(label)
            act.triggered.connect(lambda checked=False, slot=s: on_slot_selected_cb(slot))

        return menu

    def build_restore_menu(self, parent_widget: QWidget, on_slot_selected_cb) -> QMenu:
        """构建恢复快照弹出菜单（100% 对齐图 1）"""
        slots_info = self.get_snapshot_slots_info()
        menu = QMenu(parent_widget)
        self._apply_menu_style(menu)

        # 标题项 (禁用不可选)
        header_act = menu.addAction("🔧 选择要恢复的快照位置:")
        header_act.setEnabled(False)
        menu.addSeparator()

        for s in (1, 2, 3):
            info = slots_info.get(s, {})
            if info.get("exists"):
                label = f"🟢 槽位 {s}: {info.get('date_ymd', '')} ({info.get('window_count', 0)}个窗口)"
                act = menu.addAction(label)
                act.triggered.connect(lambda checked=False, slot=s: on_slot_selected_cb(slot))
            else:
                label = f"⚪ 槽位 {s}: [空 / 未保存]"
                act = menu.addAction(label)
                act.setEnabled(False)

        return menu

    def _apply_menu_style(self, menu: QMenu):
        """应用与 ATS 现代暗黑科技风统一的菜单样式"""
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                color: #dcdce6;
                border: 1px solid #3d3d52;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-size: 9.5pt;
            }
            QMenu::item:selected {
                background-color: #2b354d;
                color: #70b8ff;
            }
            QMenu::item:disabled {
                color: #636378;
                font-size: 9pt;
            }
            QMenu::separator {
                height: 1px;
                background: #2f2f40;
                margin: 4px 6px;
            }
        """)

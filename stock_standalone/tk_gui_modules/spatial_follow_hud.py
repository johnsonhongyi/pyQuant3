# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import os
import time
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from tk_gui_modules.window_mixin import WindowMixin
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("instock_TK.SpatialFollowHUD")
from sys_utils import get_app_root

class DictWrapper:
    """
    零拷贝 O(1) 字典包装器：将 detector 返回的原始 dict 无缝包装为对象，
    无损复用 HUD 中已有的 `.property` 渲染逻辑。
    支持可选的 fallback 备用对象以自动融合主力净占、共振密度等全量极客指标。
    """
    def __init__(self, data: dict, fallback_obj: Any = None):
        self._data = data
        self._fallback = fallback_obj

    def __getattr__(self, name: str) -> Any:
        # 特殊字段物理映射对齐
        if name == 'name':
            return self._data.get('sector', '') or (self._fallback.name if self._fallback else '')
        if name == 'heat_score':
            return self._data.get('score', 0.0) or (self._fallback.heat_score if self._fallback else 0.0)
        if name == 'volume_ratio':
            return self._data.get('volume_ratio', 1.0) or (self._fallback.volume_ratio if self._fallback else 1.0)
        if name == 'follower_detail':
            # 物理映射转换：将 detector 返回的原始 'followers' 字典列表，映射并包装为 follower_detail
            return self._data.get('followers', []) or (self._fallback.follower_detail if self._fallback else [])
        if name == 'leader_code':
            # 🚀 [ROOT-FIX] 关键映射对齐：竞价探测器底层的龙头代码字段是 'leader'，在此无缝映射并对准
            return self._data.get('leader', '') or (self._fallback.leader_code if self._fallback else '')
        if name == 'leader_name':
            return self._data.get('leader_name', '') or (self._fallback.leader_name if self._fallback else '')
        if name == 'leader_change_pct':
            return self._data.get('leader_pct', 0.0) or (self._fallback.leader_change_pct if self._fallback else 0.0)
        if name == 'leader_vwap':
            # 在 active_sectors 里面，它的当前价格存在 'leader_price' 键中
            return self._data.get('leader_price', 0.0) or (self._fallback.leader_vwap if self._fallback else 0.0)
        if name == 'leader_pct_diff':
            return self._data.get('leader_pct_diff', 0.0) or (self._fallback.leader_pct_diff if self._fallback else 0.0)
        if name == 'zt_count':
            val = self._data.get('zt_count', None)
            if val is None or val == 0:
                # ⚡ [HEALING-SHIELD] 二次自愈防护：从跟随股和龙头列表中动态数出今日真实涨停数！
                try:
                    from bidding_momentum_detector import get_limit_up_threshold
                    zt_count = 0
                    
                    # 1. 检查龙头是否涨停
                    leader_code = self._data.get('leader', '')
                    leader_pct = self._data.get('leader_pct', 0.0)
                    if leader_code and leader_pct >= get_limit_up_threshold(leader_code):
                        zt_count += 1
                        
                    # 2. 检查跟随个股是否涨停
                    followers = self._data.get('followers', [])
                    for f in followers:
                        f_code = f.get('code')
                        f_pct = f.get('pct', 0.0)
                        if f_code and f_pct >= get_limit_up_threshold(f_code):
                            zt_count += 1
                    
                    val = zt_count
                except Exception:
                    val = 0
            
            return val or (self._fallback.zt_count if self._fallback else 0)
        if name == 'score_accel':
            # 🚀 [Tactical Alignment] 把 score_accel 爆发加速映射为最敏感的“板块当下涨跌热度”数据！
            return self.heat_score
        
        # 兼容属性读取
        val = self._data.get(name, None)
        
        # 🚀 [NEW] 纵深融合：如果 detector 原始数据中没有该字段或值为 0/0.0，尝试从 fallback 补齐
        if (val is None or val == 0 or val == 0.0) and self._fallback:
            try:
                f_val = getattr(self._fallback, name, None)
                if f_val is not None and f_val != 0 and f_val != 0.0:
                    val = f_val
            except Exception:
                pass
                
        if val is None:
            # 兜底返回 0 或是对应默认值，防止外部渲染 float 报错
            if name in ['bidding_score', 'score_accel', 'zhuli_ratio', 'follow_ratio', 
                        'leader_change_pct', 'leader_pct_diff', 'leader_dff', 'leader_vwap']:
                return 0.0
            if name in ['surge_density', 'zt_count']:
                return 0
            if name in ['leader_name', 'leader_code']:
                return "--"
        return val

    def __getitem__(self, key: str) -> Any:
        val = self._data.get(key, None)
        if val is None and self._fallback:
            try:
                val = self._fallback[key]
            except:
                pass
        return val

class SpatialFollowHUD(QtWidgets.QDialog, WindowMixin):
    """
    SpatialFollowHUD - 盘中实时板块跟单可视化微型指挥所 (Persistent Glassmorphism HUD)
    
    采用高反差 Cyberpunk 暗黑科技玻璃拟态风格，支持纯键盘“盲操”：
    - Up/Down 方向键: 在龙头与三大跟风股之间瞬间循环切换跟单目标并联动主窗
    - Return/Enter 键: 瞬间触发所选个股的跟进决策，并投递至交易内核 (高保真跟单)
    - Esc 键: 手动收起/隐藏
    """
    
    order_submitted = pyqtSignal(str, str, float)  # (代码, 动作, 比例)

    def _get_active_detector(self) -> Optional[Any]:
        """[SSOT] 获取主窗口当前活跃运行且真正有打分数据的 BiddingMomentumDetector 实例"""
        if not self.main_app:
            return None
            
        # 1. 尝试从已开启的竞价面板实例中提取真正跑打分计算的权威 detector
        panel = getattr(self.main_app, 'sector_bidding_panel', None)
        panel_detector = None
        if panel and hasattr(panel, 'detector') and panel.detector:
            panel_detector = panel.detector
            
        # 2. 尝试直接从主窗口属性获取
        main_detector = getattr(self.main_app, 'racing_detector', None)
        
        # 3. 比对并挑选真正有计算数据的活跃实例
        if panel_detector and main_detector:
            # 如果两个都有，优先挑选有打分数据的（即 active_sectors 字典不为空的）
            try:
                with panel_detector._lock:
                    panel_has_data = len(panel_detector.active_sectors) > 0
            except:
                panel_has_data = False
                
            try:
                with main_detector._lock:
                    main_has_data = len(main_detector.active_sectors) > 0
            except:
                main_has_data = False
                
            if panel_has_data and not main_has_data:
                return panel_detector
            if main_has_data and not panel_has_data:
                return main_detector
            # 如果都有数据，优先返回 panel_detector，因为竞价面板是前台活跃计算体
            return panel_detector
            
        if panel_detector:
            return panel_detector
            
        if main_detector:
            return main_detector
            
        return None

    def __init__(self, parent: QtWidgets.QWidget | None = None, main_app: Any = None, on_code_callback: Any = None) -> None:
        super().__init__(parent)
        self.main_app = main_app
        self.on_code_callback = on_code_callback
        self.setWindowTitle("⚡ 实时板块突破跟单指挥所")
        
        # 1. 读写持久化置顶参数
        self.stays_on_top = self._load_stays_on_top()
        
        # 2. 设置置顶、无边框、工具窗口属性 (防任务栏侵占)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.sector_name: str = ""
        self.selected_index: int = 0  # 0: 龙头, 1: 跟风1, 2: 跟风2, 3: 跟风3
        self._nav_direction: Optional[str] = None  # 🚀 [NEW] 键盘方向键瀑布流导航方向标记 ('up' 或 'down')
        self.candidate_stocks: List[Dict[str, Any]] = []  # 缓存当前的备选股票列表
        self.sector_heat_value: float = 50.0
        
        # 拖拽相关
        self._drag_pos = QtCore.QPoint()
        
        self._init_ui()
        
        # 💾 [PERSISTENCE] 从物理持久化文件中自动加载并高精度还原上次手动拉扯保存的黄金列宽配置
        self._load_column_widths()
        
        self._setup_timer()
        
        # 🚀 [NEW] 设置强焦点策略以完美捕获键盘方向键按键切换事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 恢复上次窗口坐标与尺寸 (Persist window state)
        self.load_window_position_qt(self, "SpatialFollowHUD", default_width=500, default_height=520)
        
        # 🚀 [NEW] DWM 防抖不透明度应用定时器，彻底根除高频刷新及句柄重建时的 UpdateLayeredWindowIndirect 报错
        self._opacity_debounce_timer = QtCore.QTimer(self)
        self._opacity_debounce_timer.setSingleShot(True)
        self._opacity_debounce_timer.timeout.connect(self._execute_opacity_apply)
        self._target_opacity: float = 1.0
        
        # 🚀 [NEW] 物理初始化置顶半透明状态与亮度滑块显隐，一启动便延时 100ms 对齐，防句柄未就绪警告
        QtCore.QTimer.singleShot(100, self._apply_opacity_ui_state)
        
        # 🛡️ [BOOT-LOCK] 引入开机防抖锁，冷启动 1.5 秒内，正是排版引擎自适应重绘与首次 show 动荡期。
        # 此期间禁止一切被动 resize 触发存盘，彻底秒杀首次显示时由于 Layout 自适应导致列宽文件被覆盖损毁的大 Bug！
        self._boot_locked = True
        QtCore.QTimer.singleShot(1500, lambda: setattr(self, '_boot_locked', False))

    def _load_stays_on_top(self) -> bool:
        """从 window_config.json 加载置顶状态"""
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("SpatialFollowHUD_stays_on_top", True)
        except Exception as e:
            logger.error(f"Failed to load stays_on_top config: {e}")
        return True

    def _save_stays_on_top(self, stays: bool) -> None:
        """保存置顶状态至 window_config.json"""
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            data = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["SpatialFollowHUD_stays_on_top"] = stays
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save stays_on_top config: {e}")

    def _load_auto_track(self) -> bool:
        """从 window_config.json 加载自动追踪状态"""
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("SpatialFollowHUD_auto_track", True)
        except Exception as e:
            logger.error(f"Failed to load auto_track config: {e}")
        return True

    def _save_auto_track(self, track: bool) -> None:
        """保存自动追踪状态至 window_config.json"""
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            data = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["SpatialFollowHUD_auto_track"] = track
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save auto_track config: {e}")

    def _on_auto_track_toggled(self, state: int) -> None:
        """切换自动追踪模式时的响应"""
        is_checked = self.chk_auto_track.isChecked()
        self._save_auto_track(is_checked)
        logger.debug(f"🏇 [HUD Racing Mode] Auto-tracking toggled to: {is_checked}")
        if is_checked:
            # 立即触发一次自动拉取
            self.update_hud_data(self.sector_name)

    def _toggle_stays_on_top(self) -> None:
        """切换置顶状态"""
        self._switching_flags = True  # ⭐ [SILENT-LOCK] 开启切换置顶静默锁，阻断隐式 hideEvent 误触发存盘覆盖！
        try:
            self.stays_on_top = not self.stays_on_top
            self._save_stays_on_top(self.stays_on_top)
            self._update_pin_button_style()
            
            # 动态切换 stays-on-top 标志并重绘激活
            flags = self.windowFlags()
            if self.stays_on_top:
                flags |= Qt.WindowType.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()
            
            # 🚀 [NEW] 延时 250ms 异步应用透明度状态，给 OS Win32 句柄与 High-DPI 重建留出稳定时间，根除 UpdateLayeredWindow 警告
            QtCore.QTimer.singleShot(250, self._apply_opacity_ui_state)
            
            logger.debug(f"📌 [HUD stays-on-top] Changed to: {self.stays_on_top}")
        finally:
            self._switching_flags = False  # ⭐ [SILENT-LOCK] 确保置顶修改后解除静默锁

    def _update_pin_button_style(self) -> None:
        """根据置顶状态更新 Pin 按钮外观"""
        if not hasattr(self, 'btn_pin'):
            return
        if self.stays_on_top:
            self.btn_pin.setText("📌")
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #00f0ff;
                    border: 1px solid rgba(0, 240, 255, 0.6);
                    border-radius: 10px;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 240, 255, 0.2);
                    border-color: #00f0ff;
                }
            """)
        else:
            self.btn_pin.setText("🔓")
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: rgba(224, 230, 237, 0.5);
                    border: 1px solid rgba(224, 230, 237, 0.25);
                    border-radius: 10px;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: rgba(224, 230, 237, 0.15);
                    color: #ffffff;
                    border-color: #ffffff;
                }
            """)

    def _get_stock_name(self, code: str, default_name: str = "") -> str:
        """
        高保真个股真名自愈解析器，通过多源(实时、候选、主表及HDF5本地库) O(1) 物理查表，
        物理根治 "个股_代码" placeholder 乱象。
        """
        if not code:
            return default_name
            
        code_clean = str(code).strip()
        for icon in ['🔴', '🟢', '📊', '⚠️']:
            code_clean = code_clean.replace(icon, '').strip()
        code_clean = code_clean.zfill(6)
        
        # 0. 检查 default_name 是否已经是真实汉字名称
        df_name = str(default_name).strip()
        for icon in ['🔴', '🟢', '📊', '⚠️']:
            df_name = df_name.replace(icon, '').strip()
        if df_name and not df_name.startswith("个股_") and not df_name.isdigit() and df_name != code_clean:
            return df_name
            
        # 1. 优先从主程序的 selector 实时数据表加载
        if self.main_app:
            selector = getattr(self.main_app, 'selector', None)
            if selector and hasattr(selector, 'df_all_realtime'):
                rt = selector.df_all_realtime
                if rt is not None and not rt.empty and 'name' in rt.columns:
                    if rt.index.name == 'code' and code_clean in rt.index:
                        v = str(rt.loc[code_clean, 'name'])
                        if v and not v.startswith("个股_") and not v.isdigit():
                            return v
                    elif 'code' in rt.columns:
                        matched = rt[rt['code'].astype(str).str.zfill(6) == code_clean]
                        if not matched.empty:
                            v = str(matched.iloc[0]['name'])
                            if v and not v.startswith("个股_") and not v.isdigit():
                                return v
                                
            # 2. 从 df_full_candidates 加载
            df_fc = getattr(self.main_app, 'df_full_candidates', None)
            if df_fc is not None and not df_fc.empty and 'name' in df_fc.columns:
                if df_fc.index.name == 'code' and code_clean in df_fc.index:
                    v = str(df_fc.loc[code_clean, 'name'])
                    if v and not v.startswith("个股_") and not v.isdigit():
                        return v
                elif 'code' in df_fc.columns:
                    matched = df_fc[df_fc['code'].astype(str).str.zfill(6) == code_clean]
                    if not matched.empty:
                        v = str(matched.iloc[0]['name'])
                        if v and not v.startswith("个股_") and not v.isdigit():
                            return v
                            
            # 3. 从 df_candidates 加载
            df_c = getattr(self.main_app, 'df_candidates', None)
            if df_c is not None and not df_c.empty and 'name' in df_c.columns:
                if df_c.index.name == 'code' and code_clean in df_c.index:
                    v = str(df_c.loc[code_clean, 'name'])
                    if v and not v.startswith("个股_") and not v.isdigit():
                        return v
                elif 'code' in df_c.columns:
                    matched = df_c[df_c['code'].astype(str).str.zfill(6) == code_clean]
                    if not matched.empty:
                        v = str(matched.iloc[0]['name'])
                        if v and not v.startswith("个股_") and not v.isdigit():
                            return v
                            
            # 4. 从 master.df_all 加载
            master = getattr(self.main_app, 'master', None)
            if master and hasattr(master, 'df_all'):
                m_all = master.df_all
                if m_all is not None and not m_all.empty and 'name' in m_all.columns:
                    if m_all.index.name == 'code' and code_clean in m_all.index:
                        v = str(m_all.loc[code_clean, 'name'])
                        if v and not v.startswith("个股_") and not v.isdigit():
                            return v
                    elif 'code' in m_all.columns:
                        matched = m_all[m_all['code'].astype(str).str.zfill(6) == code_clean]
                        if not matched.empty:
                            v = str(matched.iloc[0]['name'])
                            if v and not v.startswith("个股_") and not v.isdigit():
                                return v
                                
        # 5. Fallback 物理降级从 top_all.h5 检索
        try:
            import pandas as pd
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for path in [r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(get_app_root(), 'top_all.h5')]:
                if os.path.exists(path):
                    df_top = pd.read_hdf(path, 'top_all')
                    if not df_top.empty and 'name' in df_top.columns:
                        if df_top.index.name == 'code' and code_clean in df_top.index:
                            v = str(df_top.loc[code_clean, 'name'])
                            if v and not v.startswith("个股_") and not v.isdigit():
                                return v
                        elif 'code' in df_top.columns:
                            matched = df_top[df_top['code'].astype(str).str.zfill(6) == code_clean]
                            if not matched.empty:
                                v = str(matched.iloc[0]['name'])
                                if v and not v.startswith("个股_") and not v.isdigit():
                                    return v
                    break
        except Exception:
            pass
            
        return default_name

    def _trigger_linkage(self, code: str) -> None:
        """向主窗口 / 可视化终端投递联动信号 (使用官方最规范现成联动通道与 tk_dispatch_queue 派发)"""
        if not code:
            return
            
        # ⭐ [DIRTY-CHECK] 强脏检查阻断：如果当前联动的股票与上次完全相同，直接拦截返回，杜绝定时刷新和列表重绘导致的高频重复联动与界面闪烁！
        if getattr(self, '_last_linkage_code', None) == code:
            return
        self._last_linkage_code = code

        if self.main_app and self.on_code_callback:
            try:
                if hasattr(self.main_app, 'tk_dispatch_queue'):
                    if self.main_app and getattr(self.main_app, "_vis_enabled_cache", False):
                        if hasattr(self.main_app, 'open_visualizer'):
                            self.main_app.tk_dispatch_queue.put(lambda: self.main_app.open_visualizer(str(code)))
                    self.main_app.tk_dispatch_queue.put(lambda: self.on_code_callback(str(code)))
                else:
                    self.on_code_callback(str(code))
            except Exception as e:
                logger.error(f"HUD trigger_linkage error: {e}")

    def _on_hot_sector_clicked(self) -> None:
        """备选热门板块点击响应"""
        if self._is_switching_btn:
            return
        sender = self.sender()
        if not sender:
            return
        idx = sender.property("sector_index")
        
        self._is_switching_btn = True
        try:
            for i, btn in enumerate(self.hot_btns):
                btn.setChecked(i == idx)
                
            if hasattr(self, '_current_top5_sectors') and idx < len(self._current_top5_sectors):
                sname = self._current_top5_sectors[idx]
                if sname:
                    logger.debug(f"👉 [HUD Hot Selector Click] 手动切换查看 Top {idx+1} 板块: {sname}")
                    # 手动点击时，暂时切为手动锁定模式以提供流畅操作，不再用自动追踪覆盖
                    if hasattr(self, 'chk_auto_track') and self.chk_auto_track.isChecked():
                        self.chk_auto_track.setChecked(False)
                    self.update_hud_data(sname, force_render_sector=sname)
        finally:
            self._is_switching_btn = False

    def _on_leader_label_clicked(self, event: QtGui.QMouseEvent) -> None:
        """点击统治龙头标签触发主窗口/K线可视化联动"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.candidate_stocks:
                for idx, cand in enumerate(self.candidate_stocks):
                    if cand.get("is_leader"):
                        self.selected_index = idx
                        self._update_highlight_border()
                        self._trigger_linkage(cand["code"])
                        logger.debug(f"👑 [HUD Leader Label] Clicked and triggered linkage: {cand['name']}({cand['code']})")
                        break
            event.accept()

    def _init_ui(self) -> None:
        # 暗黑玻璃拟态主框架
        self.main_frame = QtWidgets.QFrame(self)
        self.main_frame.setObjectName("HUDMainFrame")
        self.main_frame.setStyleSheet("""
            QFrame#HUDMainFrame {
                background-color: rgba(15, 20, 26, 0.94);
                border: 2px solid rgba(0, 240, 255, 0.45);
                border-radius: 14px;
            }
            QLabel {
                color: #e0e6ed;
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 11px;
            }
            QTableWidget {
                background: transparent;
                border: none;
                gridline-color: rgba(0, 240, 255, 0.15);
                color: #e0e6ed;
                font-family: 'Segoe UI', 'Microsoft YaHei';
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: rgba(57, 255, 20, 0.18);
                color: #39ff14;
                font-weight: bold;
            }
            QHeaderView::section {
                background-color: rgba(20, 30, 40, 0.7);
                color: #00f0ff;
                padding: 4px;
                border: 1px solid rgba(0, 240, 255, 0.2);
                font-size: 10px;
                font-weight: bold;
            }
        """)
        
        # 精致的霓虹呼吸阴影 (Cyan Drop Shadow)
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setColor(QtGui.QColor(0, 240, 255, 110))
        shadow.setOffset(0, 0)
        self.main_frame.setGraphicsEffect(shadow)

        layout = QtWidgets.QVBoxLayout(self.main_frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # ── 标题拖拽区域 ──
        title_layout = QtWidgets.QHBoxLayout()
        self.lbl_title = QtWidgets.QLabel("🛸 REAL-TIME SECTOR FOLLOW HUD", self)
        self.lbl_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #00f0ff; letter-spacing: 1px;")
        
        # 拖拽手柄图标提示
        self.lbl_drag_hint = QtWidgets.QLabel("⚓ [拖动]", self)
        self.lbl_drag_hint.setStyleSheet("color: rgba(0, 240, 255, 0.5); font-size: 9px;")
        
        # 精致置顶 Lock / Pin 按钮
        self.btn_pin = QtWidgets.QPushButton(self)
        self.btn_pin.setFixedSize(20, 20)
        self.btn_pin.setToolTip("切换置顶 / 🔓不置顶")
        self.btn_pin.clicked.connect(self._toggle_stays_on_top)
        self._update_pin_button_style()
        
        # 精致的“🔄 刷新”按钮
        self.btn_sync = QtWidgets.QPushButton("🔄 刷新", self)
        self.btn_sync.setFixedSize(48, 20)
        self.btn_sync.setToolTip("强制与竞价面板进行物理数据同步与深度自愈诊断")
        self.btn_sync.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #00f0ff;
                border: 1px solid rgba(0, 240, 255, 0.4);
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.25);
                border-color: #00f0ff;
            }
        """)
        self.btn_sync.clicked.connect(self._on_sync_clicked)
        
        # 精致关闭按钮
        self.btn_close = QtWidgets.QPushButton("✕", self)
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(0, 240, 255, 0.7);
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 10px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 7, 58, 0.3);
                color: #ff073a;
                border-color: #ff073a;
            }
        """)
        self.btn_close.clicked.connect(self.hide)
        
        # 🚀 [NEW] 精致不透明度滑块调节容器 (仅在 stays_on_top 开启时动态展现，可极客自定义透明亮度)
        self.opacity_container = QtWidgets.QWidget(self)
        opacity_layout = QtWidgets.QHBoxLayout(self.opacity_container)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(2)
        
        lbl_opacity_hint = QtWidgets.QLabel("👻亮度:", self)
        lbl_opacity_hint.setStyleSheet("color: rgba(0, 240, 255, 0.65); font-size: 9px; font-weight: bold;")
        
        self.slider_opacity = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
        self.slider_opacity.setRange(30, 100)
        self.slider_opacity.setFixedWidth(50)
        self.slider_opacity.setFixedHeight(12)
        self.slider_opacity.setToolTip("开启置顶时，调节 HUD 的半透明比例 (30% - 100%)\n方便您盲操时隔窗观察下层分时走势图！")
        self.slider_opacity.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid rgba(0, 240, 255, 0.2);
                height: 3px;
                background: rgba(30, 41, 59, 0.6);
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #00f0ff;
                width: 6px;
                height: 6px;
                margin: -2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal:hover {
                background: #39ff14;
            }
        """)
        
        self.lbl_opacity_val = QtWidgets.QLabel("100%", self)
        self.lbl_opacity_val.setStyleSheet("color: #00f0ff; font-size: 9px; font-weight: bold; min-width: 22px;")
        
        opacity_layout.addWidget(lbl_opacity_hint)
        opacity_layout.addWidget(self.slider_opacity)
        opacity_layout.addWidget(self.lbl_opacity_val)
        
        # 恢复持久化不透明度值
        self.opacity_pct = self._load_opacity_config()
        self.slider_opacity.setValue(self.opacity_pct)
        self.lbl_opacity_val.setText(f"{self.opacity_pct}%")
        self.slider_opacity.valueChanged.connect(self._on_opacity_slider_changed)
        
        title_layout.addWidget(self.lbl_title)
        title_layout.addStretch()
        title_layout.addWidget(self.lbl_drag_hint)
        title_layout.addWidget(self.btn_sync)
        title_layout.addWidget(self.opacity_container)
        title_layout.addWidget(self.btn_pin)
        title_layout.addWidget(self.btn_close)
        layout.addLayout(title_layout)

        # ── 第一维度：板块全景 (Sector Panorama) ──
        panorama_group = QtWidgets.QGroupBox(self)
        panorama_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid rgba(0, 240, 255, 0.25);
                border-radius: 8px;
                margin-top: 6px;
                padding-top: 4px;
            }
        """)
        pano_layout = QtWidgets.QVBoxLayout(panorama_group)
        pano_layout.setContentsMargins(8, 8, 8, 8)
        
        header_layout = QtWidgets.QHBoxLayout()
        self.lbl_sector_name = QtWidgets.QLabel("等待板块突破信号...", self)
        self.lbl_sector_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        
        self.lbl_sector_badge = QtWidgets.QLabel("📡 监听中", self)
        self.lbl_sector_badge.setStyleSheet("""
            QLabel {
                font-weight: bold;
                padding: 1px 6px;
                border: 1px solid #00f0ff;
                border-radius: 4px;
                color: #00f0ff;
                background-color: rgba(0, 240, 255, 0.1);
                font-size: 10px;
            }
        """)
        
        # [NEW] 竞技赛马模式：自动追踪最强板块复选框 (Racing Mode CheckBox)
        self.chk_auto_track = QtWidgets.QCheckBox("🏇 竞技追踪", self)
        self.chk_auto_track.setToolTip("开启时：HUD自动对准全场综合热度第1的爆发风口\n关闭时：手动锁定在您点击选中的板块")
        self.chk_auto_track.setChecked(self._load_auto_track())
        self.chk_auto_track.setStyleSheet("""
            QCheckBox {
                color: #39ff14;
                font-size: 10px;
                font-weight: bold;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
                border: 1px solid rgba(57, 255, 20, 0.5);
                border-radius: 3px;
                background: transparent;
            }
            QCheckBox::indicator:checked {
                background-color: #39ff14;
                image: url(none);
            }
            QCheckBox::indicator:hover {
                border-color: #39ff14;
            }
        """)
        self.chk_auto_track.stateChanged.connect(self._on_auto_track_toggled)
        
        header_layout.addWidget(self.lbl_sector_name)
        header_layout.addWidget(self.lbl_sector_badge)
        header_layout.addWidget(self.chk_auto_track)
        header_layout.addStretch()
        self.lbl_update_time = QtWidgets.QLabel("", self)
        self.lbl_update_time.setStyleSheet("color: #888888; font-size: 9px;")
        header_layout.addWidget(self.lbl_update_time)
        pano_layout.addLayout(header_layout)
        
        # [NEW] 热门风口候选导航栏 (Top 5 Hot Sectors Shortcut)
        self.hot_btns = []
        self._current_top5_sectors = []
        self._is_switching_btn = False  # 防止信号重入
        
        hot_layout = QtWidgets.QHBoxLayout()
        hot_layout.setSpacing(4)
        hot_layout.setContentsMargins(0, 2, 0, 2)
        
        lbl_hint = QtWidgets.QLabel("🔥 候选:", self)
        lbl_hint.setStyleSheet("color: rgba(0, 240, 255, 0.75); font-size: 10px; font-weight: bold;")
        hot_layout.addWidget(lbl_hint)
        
        for idx in range(5):
            btn = QtWidgets.QPushButton("⏳ 等待行情...", self)
            btn.setCheckable(True)
            btn.setProperty("sector_index", idx)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 41, 59, 0.6);
                    border: 1px solid rgba(0, 240, 255, 0.25);
                    border-radius: 4px;
                    color: #cbd5e1;
                    padding: 2px 6px;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: rgba(0, 240, 255, 0.2);
                    border-color: #00f0ff;
                    color: #00f0ff;
                }
                QPushButton:hover {
                    border-color: #39ff14;
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(self._on_hot_sector_clicked)
            hot_layout.addWidget(btn)
            self.hot_btns.append(btn)
            
        pano_layout.addLayout(hot_layout)

        # 核心指标网格
        pano_grid = QtWidgets.QGridLayout()
        pano_grid.setSpacing(6)
        
        self.lbl_heat = QtWidgets.QLabel("🔥 综合热度: <b>N/A</b>", self)
        self.lbl_bidding = QtWidgets.QLabel("⏱️ 竞价评分: <b>N/A</b>", self)
        self.lbl_density = QtWidgets.QLabel("📈 共振密度: <b>N/A</b>", self)
        self.lbl_accel = QtWidgets.QLabel("⚡ 爆发加速: <b>N/A</b>", self)
        
        self.lbl_zt_count = QtWidgets.QLabel("🚪 涨停家数: <b>N/A</b>", self)
        self.lbl_zhuli = QtWidgets.QLabel("💰 主力净占: <b>N/A</b>", self)
        self.lbl_vol_ratio = QtWidgets.QLabel("📊 板块量比: <b>N/A</b>", self)
        self.lbl_follow = QtWidgets.QLabel("👥 跟涨比例: <b>N/A</b>", self)

        pano_grid.addWidget(self.lbl_heat, 0, 0)
        pano_grid.addWidget(self.lbl_bidding, 0, 1)
        pano_grid.addWidget(self.lbl_density, 0, 2)
        pano_grid.addWidget(self.lbl_accel, 0, 3)
        
        pano_grid.addWidget(self.lbl_zt_count, 1, 0)
        pano_grid.addWidget(self.lbl_zhuli, 1, 1)
        pano_grid.addWidget(self.lbl_vol_ratio, 1, 2)
        pano_grid.addWidget(self.lbl_follow, 1, 3)
        
        pano_layout.addLayout(pano_grid)
        layout.addWidget(panorama_group)

        # ── 第二维度：最强龙头表现 (Leader Performance) ──
        leader_group = QtWidgets.QGroupBox(self)
        leader_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid rgba(57, 255, 20, 0.25);
                border-radius: 8px;
                margin-top: 6px;
                padding-top: 4px;
            }
        """)
        leader_layout = QtWidgets.QVBoxLayout(leader_group)
        leader_layout.setContentsMargins(8, 8, 8, 8)
        
        leader_title = QtWidgets.QLabel("👑 最强统治龙头 (Rank #1)", self)
        leader_title.setStyleSheet("font-weight: bold; color: #39ff14; font-size: 10px;")
        leader_layout.addWidget(leader_title)
        
        leader_info_layout = QtWidgets.QHBoxLayout()
        self.lbl_leader_name = QtWidgets.QLabel("暂无龙头", self)
        self.lbl_leader_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        self.lbl_leader_name.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
        self.lbl_leader_name.mousePressEvent = self._on_leader_label_clicked
        
        self.lbl_leader_pct = QtWidgets.QLabel("0.00%", self)
        self.lbl_leader_pct.setStyleSheet("font-size: 13px; font-weight: bold; color: #888888;")
        
        self.lbl_leader_pct_diff = QtWidgets.QLabel("变动: 0.00%", self)
        self.lbl_leader_pct_diff.setStyleSheet("color: #888888;")
        
        self.lbl_leader_dff = QtWidgets.QLabel("背离: 0.0", self)
        self.lbl_leader_dff.setStyleSheet("color: #888888;")
        
        self.lbl_leader_vwap = QtWidgets.QLabel("均线: 0.00", self)
        self.lbl_leader_vwap.setStyleSheet("color: #888888;")
        
        leader_info_layout.addWidget(self.lbl_leader_name)
        leader_info_layout.addWidget(self.lbl_leader_pct)
        leader_info_layout.addSpacing(10)
        leader_info_layout.addWidget(self.lbl_leader_pct_diff)
        leader_info_layout.addWidget(self.lbl_leader_dff)
        leader_info_layout.addWidget(self.lbl_leader_vwap)
        leader_info_layout.addStretch()
        
        leader_layout.addLayout(leader_info_layout)
        layout.addWidget(leader_group)

        # ── 第三维度：跟风梯队明细 (Top 3 Followers) ──
        followers_group = QtWidgets.QGroupBox(self)
        followers_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid rgba(255, 0, 127, 0.25);
                border-radius: 8px;
                margin-top: 6px;
                padding-top: 4px;
            }
        """)
        f_layout = QtWidgets.QVBoxLayout(followers_group)
        f_layout.setContentsMargins(6, 6, 6, 6)
        
        f_title = QtWidgets.QLabel("🥈 爆发跟风排头兵 (Top Followers)", self)
        f_title.setStyleSheet("font-weight: bold; color: #ff007f; font-size: 10px;")
        f_layout.addWidget(f_title)
        
        # 允许纵向扩展并且有滚动条的表格展示跟风股 (拆分为 7 列，现价与涨幅分开)
        self.table = QtWidgets.QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(["代码/名称", "现价", "涨幅", "周期变幅", "跟涨T值", "背离DFF", "形态特征"])
        
        # 优化列宽模式：前六列分配自适应精准宽度，最后一列形态特征使用 Stretch 占满剩余空间
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.Stretch) # 形态特征拉伸
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked) # 连接表头综合排序
        
        # 🚀 [ROOT-FIX] 绑定列宽变动即时保存信号，拉拽后微秒级自动物理写盘，防异常强退丢失
        self.table.horizontalHeader().sectionResized.connect(self._on_section_resized)
        
        # 恢复物理持久化列宽
        self._load_column_widths()
        
        self.table.horizontalHeader().setFixedHeight(22)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(100)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 允许键盘/鼠标在表格上自然捕获焦点并翻页
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.currentCellChanged.connect(self._on_table_current_cell_changed)
        f_layout.addWidget(self.table)
        
        layout.addWidget(followers_group)

        # ── 第四维度：指令控制中枢 (Decision Kernel) ──
        cmd_group = QtWidgets.QGroupBox(self)
        cmd_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid rgba(0, 240, 255, 0.3);
                border-radius: 8px;
                margin-top: 4px;
                padding-top: 4px;
                background-color: rgba(20, 25, 35, 0.7);
            }
        """)
        cmd_layout = QtWidgets.QVBoxLayout(cmd_group)
        cmd_layout.setContentsMargins(10, 8, 10, 8)
        cmd_layout.setSpacing(8)

        # 运行状态及跟单尺寸
        state_layout = QtWidgets.QHBoxLayout()
        self.lbl_mode_title = QtWidgets.QLabel("⚙️ 交易内核模式:", self)
        self.lbl_mode_badge = QtWidgets.QLabel("OBSERVE", self)
        self.lbl_mode_badge.setStyleSheet("""
            font-weight: bold; 
            padding: 2px 6px; 
            border: 1px solid #888; 
            border-radius: 3px; 
            color: #A0A0A5; 
            background-color: #1A1A1F;
        """)
        
        state_layout.addWidget(self.lbl_mode_title)
        state_layout.addWidget(self.lbl_mode_badge)
        state_layout.addStretch()
        
        # 尺寸滑块
        self.slider_size = QtWidgets.QSlider(Qt.Orientation.Horizontal, self)
        self.slider_size.setMinimum(1)
        self.slider_size.setMaximum(100)
        self.slider_size.setValue(10)
        self.slider_size.setFixedWidth(120)
        self.slider_size.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider_size.valueChanged.connect(self._on_slider_changed)
        
        self.lbl_size_val = QtWidgets.QLabel("跟单仓位: <b>10%</b>", self)
        self.lbl_size_val.setStyleSheet("color: #00f0ff; min-width: 80px;")
        
        state_layout.addWidget(self.lbl_size_val)
        state_layout.addWidget(self.slider_size)
        cmd_layout.addLayout(state_layout)

        # 核心跟单动作面板
        self.follow_frame = QtWidgets.QFrame(self)
        self.follow_frame.setObjectName("FollowFrame")
        self.follow_frame.setStyleSheet("""
            QFrame#FollowFrame {
                background-color: rgba(57, 255, 20, 0.08);
                border: 1px dashed rgba(57, 255, 20, 0.4);
                border-radius: 6px;
            }
        """)
        ff_layout = QtWidgets.QVBoxLayout(self.follow_frame)
        ff_layout.setContentsMargins(8, 6, 8, 6)
        
        self.lbl_follow_target = QtWidgets.QLabel("🎯 当前键盘锁定目标: [暂无选择]", self)
        self.lbl_follow_target.setStyleSheet("font-size: 12px; font-weight: bold; color: #39ff14;")
        self.lbl_follow_reason = QtWidgets.QLabel("考量: 等待有效突破形态触发", self)
        self.lbl_follow_reason.setStyleSheet("color: #a0a5b0; font-size: 10px;")
        
        ff_layout.addWidget(self.lbl_follow_target)
        ff_layout.addWidget(self.lbl_follow_reason)
        cmd_layout.addWidget(self.follow_frame)

        # 一键确认跟单大按钮 (Neon Styled)
        self.btn_submit = QtWidgets.QPushButton("⚡ 确认一键跟单 (Return / Enter)", self)
        self.btn_submit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_submit.setStyleSheet("""
            QPushButton {
                background-color: rgba(57, 255, 20, 0.2);
                color: #39ff14;
                border: 2px solid #39ff14;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: rgba(57, 255, 20, 0.35);
                border-color: #00FF66;
            }
            QPushButton:pressed {
                background-color: rgba(57, 255, 20, 0.5);
            }
        """)
        self.btn_submit.clicked.connect(self._on_submit_clicked)
        cmd_layout.addWidget(self.btn_submit)

        layout.addWidget(cmd_group)
        
        # ── 5. 设置自适应布局包裹 ──
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_frame)
        
        # ── 6. 精致的无边框缩放 Grip ──
        self.sizegrip = QtWidgets.QSizeGrip(self)
        self.sizegrip.setStyleSheet("QSizeGrip { image: none; background: transparent; }")

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'sizegrip'):
            self.sizegrip.move(self.width() - self.sizegrip.width() - 4, self.height() - self.sizegrip.height() - 4)

    def _setup_timer(self) -> None:
        """主界面的定时脏刷新计时器（高灵敏度 1.0s 封顶）"""
        self.timer = QtCore.QTimer(self)
        
        try:
            from JohnsonUtil import commonTips as cct
            if hasattr(cct, 'CFG') and hasattr(cct.CFG, 'duration_sleep_time'):
                sleep_time = float(cct.CFG.duration_sleep_time)
            elif hasattr(cct, 'duration_sleep_time'):
                sleep_time = float(cct.duration_sleep_time)
            else:
                sleep_time = 5.0
        except Exception:
            sleep_time = 5.0
            
        # [HIGH-FREQUENCY DECOUPLE] 限制最高 1000ms 刷新率，防止被 180s 养老周期冻结
        interval_ms = max(500, min(1000, int(sleep_time * 1000)))
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._on_timer_refresh)
        self.timer.start()
        logger.debug(f"🛸 [HUD] 脏刷新定时器高频启动: {interval_ms} ms (对齐 CFG/Capped at 1.0s)")

    def _on_slider_changed(self, val: int) -> None:
        self.lbl_size_val.setText(f"跟单仓位: <b>{val}%</b>")

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        """支持鼠标直接点击跟风表格切换目标，并强力触发系统联动"""
        self.table.setFocus()  # 🌟 鼠标点击时，强力夺回键盘焦点，使键盘翻页立即生效
        self.selected_index = row + 1
        self._update_highlight_border()
        
        # 🚀 [NEW] 捕获被点击行的股票代码并触发系统联动
        item = self.table.item(row, 0)
        if item:
            code = item.data(Qt.ItemDataRole.UserRole)
            if not code:
                # Fallback: 从 f"{name}\n({code})" 文本中提取 6 位数字代码
                import re
                txt = item.text()
                match = re.search(r'\((\d{6})\)', txt)
                if match:
                    code = match.group(1)
            if code:
                self._trigger_linkage(code)

    def _on_table_current_cell_changed(self, currentRow: int, currentColumn: int, previousRow: int, previousColumn: int) -> None:
        """表格键盘/鼠标行切换响应，即时向主窗口投递联动信号"""
        if currentRow < 0:
            return
            
        # ⭐ [SILENT-LOCK] 物理静默防抖：如果正在重绘表格或正在切换列宽状态，强力拦截选择变更事件，杜绝非用户主观触发的重复刷新！
        if getattr(self, '_rendering_table', False) or getattr(self, '_loading_widths', False) or getattr(self, '_switching_flags', False):
            return

        self.selected_index = currentRow + 1
        self._update_highlight_border()
        
        item = self.table.item(currentRow, 0)
        if item:
            code = item.data(Qt.ItemDataRole.UserRole)
            if not code:
                import re
                txt = item.text()
                match = re.search(r'\((\d{6})\)', txt)
                if match:
                    code = match.group(1)
            if code:
                self._trigger_linkage(code)

    def update_hud_data(self, sector_name: str, signal_item: Optional[Any] = None, force_render_sector: Optional[str] = None) -> None:
        """
        [CORE] 拉取并更新 HUD 上的全部四维度数据
        - 由 main thread 或 QTimer 消息驱动，无多进程竞态风险
        - 实时对准底层最新竞价热度，提供 3 大备选快速优化导航
        """
        # 🛡️ [THREAD-SAFETY] 纵深防御：如果在非主线程中调用，强制使用 QTimer 派发至主线程执行，防止 GIL/Qt 冲突崩溃
        from PyQt6.QtCore import QThread, QCoreApplication
        app = QCoreApplication.instance()
        if app and QThread.currentThread() != app.thread():
            logger.debug(f"🛸 [HUD Thread-Safety] update_hud_data called from background thread, routing to main thread via QTimer...")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.update_hud_data(sector_name, signal_item, force_render_sector))
            return

        self.lbl_update_time.setText(datetime.now().strftime("%H:%M:%S"))
        
        # ⭐ [STATE-MEMORY] 记录刷新前被锁定的股票代码，以便在刷新后智能恢复选择状态，彻底杜绝无谓的重置为龙头bug！
        prev_locked_code = None
        if hasattr(self, 'candidate_stocks') and self.candidate_stocks and 0 <= self.selected_index < len(self.candidate_stocks):
            prev_locked_code = self.candidate_stocks[self.selected_index]["code"]

        # 🚀 [NEW] 空风口输入时，自动执行冷启动自愈寻址定位
        if not sector_name:
            detector = self._get_active_detector()
            if detector:
                try:
                    active_list = detector.get_active_sectors()
                    if active_list:
                        sector_name = active_list[0].get('sector', '')
                except Exception:
                    pass
            if not sector_name:
                try:
                    from sector_focus_engine import get_focus_controller
                    fc_init = get_focus_controller()
                    if fc_init:
                        hot_sectors_init = fc_init.sector_map.get_hot_sectors(1)
                        if hot_sectors_init:
                            sector_name = hot_sectors_init[0].name
                except Exception:
                    pass

        # 🚀 [NEW] 板块切换状态感知与竞技追踪自动降级自愈 (防止手动/外部切换板块时自动追踪强行拉回覆盖)
        if sector_name and self.sector_name and sector_name != self.sector_name:
            if hasattr(self, 'chk_auto_track') and self.chk_auto_track.isChecked():
                logger.debug(f"🔄 [HUD State Align] 外部/手动主动切换板块 {self.sector_name} -> {sector_name}，自动暂停 🏇 竞技追踪状态")
                self.chk_auto_track.setChecked(False)

        # 1. [SSOT] 获取主窗口当前活跃运行的 BiddingMomentumDetector 实例
        detector = self._get_active_detector()
        
        # 🚀 [NEW] 无效静态板块自愈重定位逻辑：
        # 如果当前传入的 sector_name 不在竞价探测器的活跃风口中，且竞价探测器已经有活跃打分结果，
        # 我们自动将 sector_name 重定位为当前最强的活跃风口，物理根治“冷启动白屏/静态过期数据”的痛点！
        if detector:
            try:
                with detector._lock:
                    has_active = len(detector.active_sectors) > 0
                    is_valid = sector_name in detector.active_sectors if sector_name else False
                
                if has_active and (not sector_name or not is_valid):
                    active_list = detector.get_active_sectors()
                    if active_list:
                        old_name = sector_name
                        sector_name = active_list[0].get('sector', '')
                        logger.debug(f"🔮 [HUD Self-Healing] Sector '{old_name}' not active in Bidding Detector. Auto self-healed and locked to strongest active wind: '{sector_name}'")
            except Exception as e:
                logger.warning(f"⚠️ [HUD Self-Healing] Failed to perform sector self-healing: {e}")

        hot_sectors = []

        if detector:
            try:
                # 从权威 Bidding 探测器中直接获取最鲜活的活跃风口
                active_list = detector.get_active_sectors()
                if active_list:
                    # 🚀 [NEW] 提前拉取 FocusController 备用字典以补齐这 5 个板块的属性
                    fc_loader = None
                    try:
                        from sector_focus_engine import get_focus_controller
                        fc_loader = get_focus_controller()
                    except:
                        pass
                    
                    # 使用 DictWrapper 零拷贝包装为对象，并自动融合 FocusController 备用属性，保留前 5 个最强风口
                    hot_sectors = []
                    for d in active_list[:5]:
                        sec_name = d.get('sector', '')
                        fc_sec = fc_loader.sector_map.get_sector_heat(sec_name) if (fc_loader and sec_name) else None
                        hot_sectors.append(DictWrapper(d, fallback_obj=fc_sec))
                        
                    logger.debug(f"📡 [HUD SSOT] Successfully read {len(hot_sectors)} sectors from active BiddingMomentumDetector.")
            except Exception as e:
                logger.warning(f"⚠️ [HUD SSOT] Failed to read from detector: {e}")

        # Fallback to Focus Controller
        if not hot_sectors:
            from sector_focus_engine import get_focus_controller
            fc = get_focus_controller()
            if fc:
                try:
                    hot_sectors = fc.sector_map.get_hot_sectors(5)
                except Exception as e:
                    logger.warning(f"Failed to get hot sectors from FocusController: {e}")

        self._current_top5_sectors = [s.name for s in hot_sectors]
        
        # 实时更新 5 个热门风口候选导航按钮的字样与可视度
        self._is_switching_btn = True
        try:
            for i, btn in enumerate(self.hot_btns):
                if i < len(hot_sectors):
                    sh_btn = hot_sectors[i]
                    btn.setText(f"{i+1}. {sh_btn.name[:4]} ({sh_btn.heat_score:.1f})")
                    btn.setVisible(True)
                else:
                    btn.setVisible(False)
        finally:
            self._is_switching_btn = False

        # 🚀 [NEW] 决定本次渲染的目标板块名称
        if force_render_sector:
            # 按钮手动强制触发
            sector_name = force_render_sector
            self._is_switching_btn = True
            try:
                for i, s_name in enumerate(self._current_top5_sectors):
                    self.hot_btns[i].setChecked(s_name == sector_name)
            finally:
                self._is_switching_btn = False
        else:
            # 常规定时刷新或外部主动推送
            if hasattr(self, 'chk_auto_track') and self.chk_auto_track.isChecked():
                # 🏇 开启自动追踪模式：自动锁定热度第 1 板块并强制高亮第 1 按钮
                self._is_switching_btn = True
                try:
                    for i in range(len(self.hot_btns)):
                        self.hot_btns[i].setChecked(i == 0)
                finally:
                    self._is_switching_btn = False

                if hot_sectors:
                    new_sec = hot_sectors[0].name
                    if new_sec != self.sector_name and self.sector_name != "":
                        ldr_code = hot_sectors[0].leader_code
                        if ldr_code:
                            self._trigger_linkage(ldr_code)
                            logger.debug(f"⚡ [HUD Racing Drift] 风口轮动至: {new_sec}，自动切换至新龙头: {hot_sectors[0].leader_name}({ldr_code})")
                    sector_name = new_sec
            else:
                # 🔒 手动锁定模式：根据所选名称同步高亮候选按钮
                self._is_switching_btn = True
                try:
                    for i, s_name in enumerate(self._current_top5_sectors):
                        self.hot_btns[i].setChecked(s_name == sector_name)
                finally:
                    self._is_switching_btn = False

        self.sector_name = sector_name
            
        # 🚀 [NEW] 数据纵深融合：拉取 FocusController 中关于该板块的全量极客指标作为备用
        fc_detail = None
        try:
            from sector_focus_engine import get_focus_controller
            fc = get_focus_controller()
            if fc:
                fc_detail = fc.sector_map.get_sector_heat(sector_name)
        except Exception as e:
            logger.warning(f"⚠️ [HUD Data Fusion] Failed to load detail from FocusController: {e}")

        sh = None
        if detector:
            try:
                with detector._lock:
                    raw_dict = detector.active_sectors.get(sector_name)
                if raw_dict:
                    sh = DictWrapper(raw_dict, fallback_obj=fc_detail)
            except Exception as e:
                logger.warning(f"⚠️ [HUD SSOT] Failed to read sector {sector_name} from detector: {e}")

        # Fallback to Focus Controller
        if not sh:
            from sector_focus_engine import get_focus_controller
            fc = get_focus_controller()
            if fc:
                try:
                    sh = fc.sector_map.get_sector_heat(sector_name)
                except Exception as e:
                    logger.warning(f"Failed to get sector heat for {sector_name}: {e}")

        # 🚀 [NEW] 终极冷启动与非活跃板块自愈实体构建器
        if not sh:
            logger.debug(f"🔮 [HUD Self-Healing] Sector '{sector_name}' has no active heatmap data. Generating zero-lock self-healing wrapper...")
            dummy_data = {
                'sector': sector_name if sector_name else "板块观察",
                'score': 0.0,
                'volume_ratio': 1.0,
                'followers': [],
                'leader': '--',
                'leader_name': '等待推送',
                'leader_pct': 0.0,
                'leader_price': 0.0,
                'leader_pct_diff': 0.0,
                'zt_count': 0
            }
            if hasattr(self, '_last_linkage_code') and self._last_linkage_code:
                dummy_data['leader'] = self._last_linkage_code
                dummy_data['leader_name'] = '联动锁定'
                from sector_focus_engine import get_focus_controller
                fc = get_focus_controller()
                if fc and fc._df_realtime is not None and self._last_linkage_code in fc._df_realtime.index:
                    dummy_data['leader_name'] = str(fc._df_realtime.loc[self._last_linkage_code, 'name'])
                    dummy_data['leader_pct'] = float(fc._df_realtime.loc[self._last_linkage_code, 'percent'])
                    dummy_data['leader_price'] = float(fc._df_realtime.loc[self._last_linkage_code, 'price'])
            sh = DictWrapper(dummy_data, fallback_obj=fc_detail)

        if not sh:
            self.lbl_sector_name.setText(f"📡 监听: {sector_name}")
            return
            
        self.sector_heat_value = sh.heat_score
            
        # ── 维度 1: 板块全图 ──
        self.lbl_sector_name.setText(f"🪐 {sh.name}")
        
        stype = sh.sector_type or "📊 跟踪"
        self.lbl_sector_badge.setText(stype)
        badge_style = "font-weight: bold; padding: 1px 6px; border-radius: 4px; font-size: 10px; "
        if "强攻" in stype or "🔥" in stype:
            badge_style += "border: 1px solid #ff007f; color: #ff007f; background-color: rgba(255, 0, 127, 0.1);"
        elif "反转" in stype or "🔄" in stype:
            badge_style += "border: 1px solid #ffcc00; color: #ffcc00; background-color: rgba(255, 204, 0, 0.1);"
        elif "蓄势" in stype or "♨️" in stype:
            badge_style += "border: 1px solid #00f0ff; color: #00f0ff; background-color: rgba(0, 240, 255, 0.1);"
        else:
            badge_style += "border: 1px solid #e0e6ed; color: #e0e6ed; background-color: rgba(224, 230, 237, 0.1);"
        self.lbl_sector_badge.setStyleSheet(badge_style)
        
        self.lbl_heat.setText(f"🔥 综合热度: <b style='color:#00f0ff;'>{sh.heat_score:.1f}</b>")
        self.lbl_bidding.setText(f"⏱️ 竞价评分: <b style='color:#ffcc00;'>{sh.bidding_score:.2f}</b>")
        self.lbl_density.setText(f"📈 共振密度: <b style='color:#39ff14;'>{sh.surge_density}</b>")
        self.lbl_accel.setText(f"accel 爆发加速: <b style='color:#ff007f;'>{sh.score_accel:+.2f}</b>")
        
        self.lbl_zt_count.setText(f"🚪 涨停家数: <b>{sh.zt_count} 只</b>")
        
        zl_color = "#39ff14" if sh.zhuli_ratio >= 0 else "#ff073a"
        self.lbl_zhuli.setText(f"💰 主力净占: <b style='color:{zl_color};'>{sh.zhuli_ratio:+.1f}%</b>")
        self.lbl_vol_ratio.setText(f"📊 板块量比: <b>{sh.volume_ratio:.2f}</b>")
        self.lbl_follow.setText(f"👥 跟涨比例: <b>{sh.follow_ratio * 100:.0f}%</b>")

        # ── 维度 2: 龙头表现 ──
        leader_code = sh.leader_code
        leader_name = self._get_stock_name(leader_code, sh.leader_name)
        leader_change_pct = float(sh.leader_change_pct or 0.0)
        leader_pct_diff = float(sh.leader_pct_diff or 0.0)
        leader_dff = float(sh.leader_dff or 0.0)
        leader_vwap = float(sh.leader_vwap or 0.0)
        leader_now_price = 0.0
        
        # 1-3号位跟风股 -> 升级为基于阿尔法爆发因子的多维智能优选筛选器！
        raw_followers = sh.follower_detail if hasattr(sh, 'follower_detail') and sh.follower_detail else []
        
        # 过滤掉和龙头相同的股票，避免重复
        valid_followers = [f for f in raw_followers if f.get('code') != sh.leader_code]

        # [🚀 OPTIMIZE] 完美消灭 GUI 线程锁等待！在排序前仅一次性进锁，把龙头和所有跟风个股需要的 Tick 快照批量提取出来
        tick_snaps = {}
        leader_snap = {}
        if detector and hasattr(detector, 'tick_series'):
            try:
                # 收集所有需要提取的跟风股代码
                extract_codes = [f.get('code', '') for f in valid_followers if f.get('code')]
                with detector._lock:
                    # 1. 批量提取跟风股数据
                    for ec in extract_codes:
                        ts = detector.tick_series.get(ec)
                        if ts:
                            tick_snaps[ec] = {
                                'score': float(getattr(ts, 'score', 0.0) or 0.0),
                                'momentum_score': float(getattr(ts, 'momentum_score', 0.0) or 0.0),
                                'score_accel': float(getattr(ts, 'score_accel', 0.0) or 0.0),
                                'volume_ratio': float(getattr(ts, 'volume_ratio', 1.0) or 1.0),
                                'zhuli_ratio': float(getattr(ts, 'zhuli_ratio', 0.0) or 0.0),
                            }
                    # 2. 提取最强龙头数据
                    if leader_code:
                        ts = detector.tick_series.get(leader_code)
                        if ts:
                            leader_snap = {
                                'now_price': float(getattr(ts, 'now_price', 0.0) or 0.0),
                                'last_close': float(getattr(ts, 'last_close', 0.0) or 0.0),
                                'pct_diff': float(getattr(ts, 'pct_diff', 0.0) or 0.0),
                                'dff': float(getattr(ts, 'dff', 0.0) or 0.0),
                                'ma20': float(getattr(ts, 'ma20', 0.0) or 0.0),
                            }
            except Exception as e:
                logger.error(f"[HUD] Failed to snapshot tick data: {e}")

        # 使用已提取的龙头快照
        if leader_snap:
            leader_now_price = leader_snap['now_price']
            if leader_snap['last_close'] > 0:
                leader_change_pct = ((leader_now_price - leader_snap['last_close']) / leader_snap['last_close']) * 100.0
            leader_pct_diff = leader_snap['pct_diff']
            leader_dff = leader_snap['dff']
            leader_vwap = leader_snap['ma20'] or leader_now_price

        # 动态对齐百分比颜色
        leader_pct_color = "#39ff14" if leader_change_pct >= 0 else "#ff073a"
        self.lbl_leader_name.setText(f"🐉 {leader_name} ({leader_code})")
        self.lbl_leader_pct.setText(f"{leader_change_pct:+.2f}%")
        self.lbl_leader_pct_diff.setText(f"变动: <span style='color:{leader_pct_color};'>{leader_pct_diff:+.2f}%</span>")
        self.lbl_leader_dff.setText(f"背离: <b>{leader_dff:+.2f}</b>")
        self.lbl_leader_vwap.setText(f"均线: <b>{leader_vwap:.2f}</b>")

        # ── 维度 3: 跟风明细 ──
        self.candidate_stocks.clear()
        
        # 0号位永远预留给最强统治龙头
        self.candidate_stocks.append({
            "code": leader_code,
            "name": leader_name,
            "price": leader_now_price if leader_now_price > 0 else leader_vwap, # 优先使用最新的 Tick 现价
            "pct": leader_change_pct,
            "pct_diff": leader_pct_diff,
            "dff": leader_dff,
            "t_factor": 10.0, # 最强统治级别
            "reason": "🚀 最强统治龙头股 (AES 99分)",
            "is_leader": True
        })
        
        # 1-3号位跟风股 -> 升级为基于阿尔法爆发因子的多维智能优选筛选器！
        raw_followers = sh.follower_detail if hasattr(sh, 'follower_detail') and sh.follower_detail else []
        
        # 过滤掉和龙头相同的股票，避免重复
        valid_followers = [f for f in raw_followers if f.get('code') != sh.leader_code]
        
        # 📡 [SSOT] 获取当前权威活体打分器以拉取每个跟风股最新的 Tick 级量能与资金异动指标
        detector = self._get_active_detector()

        # 结合实盘物理打分器的高维度有价值强势股智能评估筛选器 (AES)
        def compute_alpha_explosion_score(f):
            code = f.get('code', '')
            
            # 1. 提取基础因子
            t_val = float(f.get('t_factor', 0.0) or 0.0)
            diff_val = float(f.get('pct_diff', 0.0) or 0.0)
            dff_val = abs(float(f.get('dff', 0.0) or 0.0))
            pct_val = float(f.get('pct', 0.0) or 0.0)
            
            # 2. [🚀 ZERO-LOCK] 从本地浅拷贝快照中直读指标，完全零锁、零阻塞！
            ts_snap = tick_snaps.get(code, {})
            now_score = ts_snap.get('score', 0.0)
            momentum_score = ts_snap.get('momentum_score', 0.0)
            accel = ts_snap.get('score_accel', 0.0)
            vol_ratio = ts_snap.get('volume_ratio', 1.0)
            zhuli = ts_snap.get('zhuli_ratio', 0.0)

            # 3. 强势股阿尔法爆发评估得分 (Alpha Explosion Score, AES) 算法核心
            # A. 个股当下爆发核心得分权重 - 满分 35 分
            score_part = min(35.0, now_score * 0.35)
            
            # B. 动能得分与抢筹加速度权重 - 满分 15 分
            accel_bonus = max(0.0, accel * 8.0)  # 正加速强力加成
            m_part = min(15.0, (momentum_score * 0.1) + accel_bonus)
            
            # C. 爆发跟涨共振强度 (T值) - 满分 20 分
            t_part = min(20.0, t_val * 2.0)
            
            # D. 主力大单流向与净占比 - 满分 10 分
            zhuli_part = min(10.0, max(-15.0, zhuli * 15.0))
            
            # E. 爆量突破加成 (量能异动) - 满分 10 分
            vol_part = 0.0
            if vol_ratio >= 2.2:
                vol_part = 10.0
            elif vol_ratio >= 1.5:
                vol_part = 6.0
            elif vol_ratio >= 1.1:
                vol_part = 3.0
                
            # F. 黄金买入介入区间加成 (控阈：防止封死涨停买不进，或者没动无价值) - 满分 15 分
            zone_part = 0.0
            # 开盘/重置点以来变幅在 [1.5%, 7.5%] 之间，是散户和操盘手最易介入套利的黄金加速期！
            if 1.5 <= diff_val <= 7.5:
                zone_part = 15.0
            elif 0.5 <= diff_val < 1.5:
                zone_part = 7.0
            elif diff_val > 9.5 or pct_val > 9.7:
                # 已经封板或者快涨停了，保留折中加分
                zone_part = 5.0
            elif diff_val < -1.5:
                # 跟风大跌，极大概率趋势走坏，扣分防御
                zone_part = -10.0
 
            # G. 形态学模式匹配强加成
            pattern_bonus = 0.0
            hint = str(f.get('pattern_hint', '') or '').lower()
            if any(k in hint for k in ["突破", "共振", "起爆", "强势", "主升", "冲锋", "封板"]):
                pattern_bonus = 5.0
            elif "准备" in hint or "新高" in hint:
                pattern_bonus = 2.0
 
            # 综合 AES 总得分计算
            aes = score_part + m_part + t_part + zhuli_part + vol_part + zone_part + pattern_bonus
            
            # 挂载计算好的指标回 dict 中，方便渲染时读取展示有深度的数据
            f['_aes'] = aes
            f['_now_score'] = now_score
            f['_accel'] = accel
            f['_vol_ratio'] = vol_ratio
            f['_zhuli'] = zhuli
            
            return aes
            
        # 根据科学量化的 AES 爆发强度进行降序排列并筛选出前 4 只最具确定性的优质排头兵个股
        valid_followers.sort(key=compute_alpha_explosion_score, reverse=True)
        selected_followers = valid_followers[:4]
        
        for f in selected_followers:
            code = f.get('code', '')
            name = self._get_stock_name(code, f.get('name', '跟风兵'))
            price = f.get('price', 0.0)
            pct = f.get('pct', 0.0)
            pct_diff = f.get('pct_diff', 0.0)
            t_factor = f.get('t_factor', 0.0)
            dff = f.get('dff', 0.0)
            hint = f.get('pattern_hint', '突破确认')
            
            # 提取真实量化评估指标
            now_score = f.get('_now_score', 0.0)
            accel = f.get('_accel', 0.0)
            vol_ratio = f.get('_vol_ratio', 1.0)
            zhuli = f.get('_zhuli', 0.0)
            
            # 动态根据实盘量化指标生成极具分析说服力的强势爆发诊断标签
            diag_tag = hint
            if accel > 0.25 and vol_ratio >= 1.5:
                diag_tag = f"🚀 爆量抢筹加速 ({now_score:.0f}分)"
            elif now_score >= 80 and zhuli >= 0.2:
                diag_tag = f"💰 资金抱团主升 ({now_score:.0f}分)"
            elif 1.8 <= pct_diff <= 6.8 and accel > 0.08:
                diag_tag = f"🎯 黄金介入区间 (量比{vol_ratio:.1f})"
            elif vol_ratio >= 2.0:
                diag_tag = f"📊 资金暴风突破 (加速{accel:+.2f})"
            elif pct >= 9.6:
                diag_tag = f"🐉 封板临界冲锋 ({now_score:.0f}分)"
            elif now_score >= 85:
                diag_tag = f"⚡ 核心超能爆发 ({now_score:.0f}分)"
                
            self.candidate_stocks.append({
                "code": code,
                "name": name,
                "price": price,
                "pct": pct,
                "pct_diff": pct_diff,
                "dff": dff,
                "t_factor": t_factor,
                "reason": diag_tag,
                "is_leader": False
            })
            
        # 🚀 [ROOT-FIX] 自动重应用用户当前的排序状态，杜绝高频刷新时排序闪退变回默认状态
        sort_col = getattr(self, '_sort_column', -1)
        if sort_col != -1:
            key_map = {
                0: lambda x: x["code"],
                1: lambda x: x["price"],
                2: lambda x: x["pct"],
                3: lambda x: x["pct_diff"],
                4: lambda x: x["t_factor"],
                5: lambda x: x["dff"],
                6: lambda x: x["reason"]
            }
            sort_key = key_map.get(sort_col, None)
            if sort_key and len(self.candidate_stocks) > 2:
                leader = self.candidate_stocks[0]
                followers = self.candidate_stocks[1:]
                is_reverse = (getattr(self, '_sort_order', 'desc') == 'desc')
                followers.sort(key=sort_key, reverse=is_reverse)
                self.candidate_stocks = [leader] + followers

        # 物理局部渲染表格内容 (现价与涨幅拆分为 2 列)
        self._render_table_only()

        # ── 维度 4: 指令控制中枢 ──
        # 同步交易内核的运行模式及 HSL 色度徽章
        try:
            from trading_kernel.kernel_service import get_kernel_service
            kernel = get_kernel_service()
            mode = kernel.mode
        except Exception:
            mode = "OBSERVE"
            
        self.lbl_mode_badge.setText(mode)
        mode_style = "font-weight: bold; padding: 2px 6px; border-radius: 3px; font-size: 10px; "
        if mode == "LIVE_AUTO":
            mode_style += "border: 1px solid #39ff14; color: #39ff14; background-color: rgba(57, 255, 20, 0.12);"
        elif mode == "CONFIRM":
            mode_style += "border: 1px solid #ffcc00; color: #ffcc00; background-color: rgba(255, 204, 0, 0.12);"
        elif mode == "PAPER":
            mode_style += "border: 1px solid #00f0ff; color: #00f0ff; background-color: rgba(0, 240, 255, 0.12);"
        else:
            mode_style += "border: 1px solid #888; color: #A0A0A5; background-color: #1A1A1F;"
        self.lbl_mode_badge.setStyleSheet(mode_style)
        
        # 优先恢复用户前一次手动锁定/浏览的股票代码，保持选择状态
        found_prev = False
        if prev_locked_code:
            for s_idx, cand in enumerate(self.candidate_stocks):
                if cand["code"] == prev_locked_code:
                    self.selected_index = s_idx
                    found_prev = True
                    break

        if not found_prev:
            if signal_item and hasattr(signal_item, 'code'):
                # 如果是具体信号触发，优先高亮匹配的个股代码
                for s_idx, cand in enumerate(self.candidate_stocks):
                    if cand["code"] == signal_item.code:
                        self.selected_index = s_idx
                        break
            else:
                # 🚀 [NAV-EXPLORATION] 根据键盘翻页方向决定候选个股高亮位置，达成无缝的瀑布流盯盘体验
                nav_dir = getattr(self, '_nav_direction', None)
                if nav_dir == "down":
                    # 下翻：自动选中跟风排头兵的第一行 (即 candidate_stocks 中的 index 1，对应 table row 0)
                    if len(self.candidate_stocks) > 1:
                        self.selected_index = 1
                    else:
                        self.selected_index = 0
                    # 强力锁定表格焦点，支持连续键盘盲操
                    self.table.setFocus()
                elif nav_dir == "up":
                    # 上翻：自动从跟风排头兵的最后一行开始 (即 candidate_stocks 中的最后一个元素，对应 table 的最后一行)
                    if len(self.candidate_stocks) > 1:
                        self.selected_index = len(self.candidate_stocks) - 1
                    else:
                        self.selected_index = 0
                    # 强力锁定表格焦点，支持连续键盘盲操
                    self.table.setFocus()
                else:
                    # 其它鼠标点击/定时刷新等情况，默认锁定第 0 列（龙头）
                    self.selected_index = 0
                
                # 立即重置导航方向，防后续刷新干扰
                self._nav_direction = None

        self._update_highlight_border()

    def _update_highlight_border(self) -> None:
        """更新锁定高亮边框和文案"""
        if not self.candidate_stocks or self.selected_index >= len(self.candidate_stocks):
            return
            
        selected = self.candidate_stocks[self.selected_index]
        code = selected["code"]
        name = selected["name"]
        is_ldr = selected["is_leader"]
        
        role = "🐉 最强领领涨龙头" if is_ldr else f"🥈 爆发跟风排头兵 #{self.selected_index}"
        
        self.lbl_follow_target.setText(f"🎯 锁定跟单: {name} ({code}) [{role}]")
        
        # ── 💡 盘前诊断计划注入 (Daily Trade Plan Overlay) ──
        diagnose_data = {}
        try:
            import os
            import json
            try:
                from sys_utils import get_app_root
                base_dir = get_app_root()
            except Exception:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            diagnose_file = os.path.join(base_dir, "logs", "premarket_diagnose.json")
            if os.path.exists(diagnose_file):
                with open(diagnose_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    diagnose_data = {item["code"]: item for item in raw_data if "code" in item}
        except Exception as e:
            logger.error(f"HUD failed to load pre-market diagnose: {e}")

        # 清理代码中的修饰符，确保精确匹配
        code_clean = code.strip()
        for icon in ['🔴', '🟢', '📊', '⚠️']:
            code_clean = code_clean.replace(icon, '').strip()

        plan_desc = ""
        if code_clean in diagnose_data:
            plan = diagnose_data[code_clean]
            suggest_action = plan.get("action_cn", plan.get("suggest_action", "保持观察"))
            hard_stop = plan.get("hard_stop", 0.0)
            reason = plan.get("reason", "")
            branch_cn = plan.get("branch_cn", plan.get("active_branch", "常规趋势"))
            
            # 使用醒目的颜色高亮操作建议
            color_map = {
                "买入建仓": "#FF3333",
                "建仓": "#FF3333",
                "补仓": "#FFFF33",
                "做T回补": "#FFFF33",
                "回补": "#FFFF33",
                "分批大止盈": "#33FF33",
                "大止盈": "#33FF33",
                "止损": "#FF3399",
                "保持观察": "#A0A5B0",
                "观察": "#A0A5B0"
            }
            act_color = color_map.get(suggest_action, "#00f0ff")
            
            stop_str = f"防守:{hard_stop:.2f}" if hard_stop > 0 else "防守:无"
            plan_desc = f"【今日计划】<font color='{act_color}'><b>{suggest_action}</b></font> ({stop_str}) | 分支: {branch_cn} | {reason}"
        else:
            plan_desc = f"考量逻辑: {selected['reason']} | 量价背离DFF={selected['dff']:.2f}"
            
        self.lbl_follow_reason.setText(plan_desc)
        
        # 板块锁定视觉框动态着色 (龙头用绿色，跟风用亮粉)
        accent_color = "#39ff14" if is_ldr else "#ff007f"
        self.follow_frame.setStyleSheet(f"""
            QFrame#FollowFrame {{
                background-color: rgba({57 if is_ldr else 255}, {255 if is_ldr else 0}, {20 if is_ldr else 127}, 0.08);
                border: 2px solid {accent_color};
                border-radius: 8px;
            }}
        """)
        
        self.btn_submit.setText(f"⚡ 确认跟单 【{name} ({code})】(Return / Enter)")
        self.btn_submit.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba({57 if is_ldr else 255}, {255 if is_ldr else 0}, {20 if is_ldr else 127}, 0.2);
                color: {accent_color};
                border: 2px solid {accent_color};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: rgba({57 if is_ldr else 255}, {255 if is_ldr else 0}, {20 if is_ldr else 127}, 0.35);
                border-color: {"#00FF66" if is_ldr else "#FF3399"};
            }}
        """)
        
        # 同步更新表格行选中状态 (如果选中跟风，高亮显示；如果选中龙头，取消表格选中)
        if self.selected_index > 0:
            self.table.selectRow(self.selected_index - 1)
        else:
            self.table.clearSelection()

    def _on_timer_refresh(self) -> None:
        """主窗口定时脏重绘"""
        if not self.isVisible():
            return
            
        target_sector = self.sector_name
        if not target_sector:
            # [COLD-START AUTO-LOCK] 冷启动或空状态下，尝试锁定当前强度第 1 的风口
            detector = self._get_active_detector()
            if detector:
                try:
                    active_list = detector.get_active_sectors()
                    if active_list:
                        target_sector = active_list[0].get('sector', '')
                except Exception as e:
                    logger.warning(f"⚠️ [HUD Timer Auto-Lock] Failed to resolve active sectors: {e}")
            
            if not target_sector:
                try:
                    from sector_focus_engine import get_focus_controller
                    fc = get_focus_controller()
                    if fc:
                        hot_sectors = fc.sector_map.get_hot_sectors(1)
                        if hot_sectors:
                            target_sector = hot_sectors[0].name
                except Exception as e:
                    logger.warning(f"⚠️ [HUD Timer Auto-Lock] Failed fallback resolver: {e}")
                        
        if target_sector:
            self.update_hud_data(target_sector)

    def _on_submit_clicked(self) -> None:
        """物理触发下单跟单"""
        if not self.candidate_stocks or self.selected_index >= len(self.candidate_stocks):
            return
            
        selected = self.candidate_stocks[self.selected_index]
        code = selected["code"]
        name = selected["name"]
        size_pct = self.slider_size.value() / 100.0
        price = selected.get("price", 0.0)
        if price <= 0.0:
            # 尝试通过 get_focus_controller 补齐价格
            try:
                import pandas as pd
                from sector_focus_engine import get_focus_controller
                fc = get_focus_controller()
                if fc and fc._df_realtime is not None and code in fc._df_realtime.index:
                    row = fc._df_realtime.loc[code]
                    # 极其健壮：支持 trade, price, nclose, last_close 容错并防止 nan
                    for col in ['trade', 'price', 'nclose', 'last_close']:
                        if col in fc._df_realtime.columns:
                            val = row[col]
                            if not pd.isna(val):
                                try:
                                    f_val = float(val)
                                    if f_val > 0.0:
                                        price = f_val
                                        break
                                except (ValueError, TypeError):
                                    pass
            except Exception as e:
                logger.warning(f"⚠️ [SpatialHUD] 补齐价格时捕获意外异常: {e}")
                
        # 1. 弹出消息闪屏气泡或者状态提示
        logger.warning(f"🛒 [SpatialHUD] 触发一键跟单动作: {name}({code}) size_pct={size_pct:.2%}")
        
        # 2. 构造 Standardized Decision Signal 并递交至交易内核
        try:
            from trading_kernel.kernel_service import get_kernel_service
            kernel = get_kernel_service()
            
            item = {
                "code": code,
                "name": name,
                "price": price if price > 0 else 1.0,
                "current_price": price if price > 0 else 1.0,
                "suggest_price": price if price > 0 else 1.0,
                "volume": 100000,
                "pct": selected.get("pct", 0.0),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "SECTOR_FOCUS",
                "signal_type": "HOT_FOLLOW" if self.selected_index > 0 else "BREAKOUT",
                "priority": 95.0,  # 极其强烈的跟单意愿
                "sector_heat": self.sector_heat_value,
                "pct_diff": selected.get("pct_diff", 0.0),
                "dff": selected.get("dff", 0.0),
                "size_pct": size_pct,  # 支持操盘手滑块微调的仓位比例
            }
            
            # 同步投递执行 (如果是 CONFIRM 模式会顺滑地呼出 Confirmation Bubble 气泡)
            res = kernel.evaluate_decision_item(item, write_journal=True)
            
            # 如果是 OBSERVE 模式，提供高保真影子跟单成功提示，允许将决策记盘
            if kernel.mode == "OBSERVE":
                QtWidgets.QMessageBox.information(
                    self,
                    "🎉 影子跟单已记录",
                    f"当前交易内核处于 OBSERVE (旁路观察) 模式下。\n跟单决策已作为影子流水成功写入 trace 日志，可用于后续复盘与回测！\n个股: {name}({code})\n仓位: {size_pct:.1%}"
                )
                return
            
            if res.get("kernel_executed"):
                QtWidgets.QMessageBox.information(
                    self,
                    "🎉 跟单成功",
                    f"一键跟单委托物理投递成功！\n个股: {name}({code})\n仓位: {size_pct:.1%}\n委托编号: {res.get('kernel_order_id')}"
                )
            else:
                reject_code = res.get("kernel_reject_code", "UNKNOWN")
                QtWidgets.QMessageBox.warning(
                    self,
                    "❌ 跟单被拒",
                    f"跟单委托被交易内核或风控卡口拒绝！\n拒绝码: {reject_code}"
                )
                
        except Exception as e:
            logger.error(f"[SpatialHUD] submit follow order failed: {e}")
            QtWidgets.QMessageBox.critical(self, "💥 系统异常", f"跟单提交失败，内核异常: {e}")

    # ── 强健的键盘驱动盲操设计 (Up/Down/Left/Right/Return/Esc) ──
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """
        统一高精度键盘事件接管：
        1. Esc / Space: 隐藏窗口
        2. Return / Enter: 一键委托下单
        3. Left / Right / Up / Down: 自适应瀑布流板块切换与个股轮动
        """
        key = event.key()
        
        # 1. 盲操快捷功能键
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Space):
            self.hide()
            event.accept()
            return
            
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_submit_clicked()
            event.accept()
            return
            
        # 2. 板块/跟风瀑布流轮动逻辑
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            # 判定是否有候选板块数据
            if not hasattr(self, '_current_top5_sectors') or not self._current_top5_sectors:
                super().keyPressEvent(event)
                return

            # 找到当前选中的候选板块索引
            curr_idx = 0
            for i, btn in enumerate(self.hot_btns):
                if btn.isChecked():
                    curr_idx = i
                    break

            # 处理 Up/Down 对跟风明细表边界触发判定
            new_idx = curr_idx
            if key == Qt.Key.Key_Up:
                if self.table.hasFocus():
                    # 如果表格有焦点，只有在首行（currentRow == 0）按 Up 时，才触发上翻前一板块
                    if self.table.rowCount() > 0 and self.table.currentRow() > 0:
                        # 尚有行可上移，交还给基类/表格原生滚动处理
                        super().keyPressEvent(event)
                        return
                    # 触及顶端边界，设定上翻标记并执行板块切换
                    self._nav_direction = "up"
                else:
                    # 表格未获焦点，默认直接上翻上一板块并落入新板块的首行
                    self._nav_direction = "down"

                new_idx = (curr_idx - 1) % len(self._current_top5_sectors)

            elif key == Qt.Key.Key_Down:
                if self.table.hasFocus():
                    # 如果表格有焦点，只有在尾行（currentRow == rowCount - 1）按 Down 时，才触发下翻后一板块
                    if self.table.rowCount() > 0 and self.table.currentRow() < self.table.rowCount() - 1:
                        # 尚有行可下移，交还给基类/表格原生滚动处理
                        super().keyPressEvent(event)
                        return
                    # 触及底端边界，设定下翻标记并执行板块切换
                    self._nav_direction = "down"
                else:
                    # 表格未获焦点，默认下翻下一板块并落入新板块的首行
                    self._nav_direction = "down"

                new_idx = (curr_idx + 1) % len(self._current_top5_sectors)

            elif key == Qt.Key.Key_Left:
                # 键盘向左：强力切换至前一板块，并默认落入新板块的第一行
                self._nav_direction = "down"
                new_idx = (curr_idx - 1) % len(self._current_top5_sectors)

            elif key == Qt.Key.Key_Right:
                # 键盘向右：强力切换至后一板块，并默认落入新板块的第一行
                self._nav_direction = "down"
                new_idx = (curr_idx + 1) % len(self._current_top5_sectors)

            # 执行板块切换
            if new_idx != curr_idx and new_idx < len(self.hot_btns):
                btn = self.hot_btns[new_idx]
                if btn.isVisible():
                    # logger.info(f"⌨️ [HUD Keyboard Select] Key {key} pressed -> Waterfall Cycle Select Sector Hot {new_idx+1} ({self._nav_direction})")
                    btn.click()
            event.accept()
            return

        super().keyPressEvent(event)

    # ── 无边框精致拖拽支持 (Standard Smooth Win32 Dragging) ──
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """支持鼠标滚轮滚动循环切换 5 个候选板块，同时精准隔离跟风个股明细表防冲突"""
        # 1. 判定是否有候选板块数据
        if not hasattr(self, '_current_top5_sectors') or not self._current_top5_sectors:
            super().wheelEvent(event)
            return

        # 🚀 [ROOT-FIX] 滚轮焦点物理防冲突：如果在跟风表格 (self.table) 上滚动，将事件原封不动分发给表格，拒绝误触板块轮动！
        child = self.childAt(event.position().toPoint())
        if child:
            p = child
            is_in_table = False
            while p:
                if p == self.table:
                    is_in_table = True
                    break
                p = p.parent()
            if is_in_table:
                # 处于表格内部，流转回 Qt 事件默认路由，让表格自然垂直滚动
                super().wheelEvent(event)
                return

        # 2. 找到当前选中的候选板块索引
        curr_idx = 0
        for i, btn in enumerate(self.hot_btns):
            if btn.isChecked():
                curr_idx = i
                break

        # 3. 获取滚动增量判定方向
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        # 滚轮向上滚动 -> 切换到前一个候选板块；滚轮向下滚动 -> 切换到后一个
        if delta > 0:
            new_idx = (curr_idx - 1) % len(self._current_top5_sectors)
        else:
            new_idx = (curr_idx + 1) % len(self._current_top5_sectors)

        event.accept()

        # 4. 触发物理按钮模拟点击切换，达成物理闭环
        if new_idx != curr_idx and new_idx < len(self.hot_btns):
            btn = self.hot_btns[new_idx]
            if btn.isVisible():
                logger.debug(f"🖱️ [HUD Wheel Select] Wheel scrolled -> Cycle Select Candidate Hot {new_idx+1}")
                btn.click()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # 在退出/隐藏时物理持久化列宽和窗口坐标
        self._save_column_widths()
        self.save_window_position_qt_visual(self, "SpatialFollowHUD")
        super().closeEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._save_column_widths()
        self.save_window_position_qt_visual(self, "SpatialFollowHUD")
        super().hideEvent(event)

    def _on_sync_clicked(self) -> None:
        """物理强制同步与深度自愈诊断入口"""
        logger.debug("🔄 [HUD Sync] User physically triggered custom sync button.")
        
        # 1. 物理诊断探测器链
        detector = self._get_active_detector()
        panel = getattr(self.main_app, 'sector_bidding_panel', None)
        main_det = getattr(self.main_app, 'racing_detector', None)
        
        logger.debug(f"🔍 [HUD Diagnostics] MainApp: {type(self.main_app)}")
        logger.debug(f"🔍 [HUD Diagnostics] MainApp.racing_detector: {main_det} (active_sectors len: {len(main_det.active_sectors) if main_det and hasattr(main_det, 'active_sectors') else 'N/A'})")
        logger.debug(f"🔍 [HUD Diagnostics] MainApp.sector_bidding_panel: {panel}")
        logger.debug(f"🔍 [HUD Diagnostics] MainApp.sector_bidding_panel.detector: {panel.detector if panel and hasattr(panel, 'detector') else None} (active_sectors len: {len(panel.detector.active_sectors) if panel and hasattr(panel, 'detector') and panel.detector and hasattr(panel.detector, 'active_sectors') else 'N/A'})")
        logger.debug(f"🔍 [HUD Diagnostics] SSOT Resolved Detector: {detector}")
        
        # 2. 强力刷新数据
        self.update_hud_data(self.sector_name, force_render_sector=self.sector_name if self.sector_name else None)
        
        # 3. 弹出精致 Toast 提示
        try:
            from tk_gui_modules.gui_utils import toast_message
            if self.sector_name:
                toast_message(self.main_app, f"🔄 HUD 数据同步成功: 📍{self.sector_name}")
            else:
                toast_message(self.main_app, "🔄 HUD 数据同步成功，监听中")
        except:
            pass

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """重写开启显示事件：每次打开 HUD 时自动执行深度物理数据同步与自愈"""
        super().showEvent(event)
        logger.debug("🛸 [HUD ShowEvent] HUD window opened, forcing active sector data synchronization...")
        self.update_hud_data(self.sector_name)
        
        # 🚀 [ROOT-FIX] 强力恢复并应用置顶配置，采用防递归安全标记，彻底抵御任何外来重置干扰
        current_flags = self.windowFlags()
        has_stays_on_top = bool(current_flags & Qt.WindowType.WindowStaysOnTopHint)
        if has_stays_on_top != getattr(self, 'stays_on_top', True):
            logger.warning(f"🛸 [HUD ShowEvent] StaysOnTop mismatch detected (actual: {has_stays_on_top}, expected: {self.stays_on_top}). Force correcting flags...")
            if self.stays_on_top:
                current_flags |= Qt.WindowType.WindowStaysOnTopHint
            else:
                current_flags &= ~Qt.WindowType.WindowStaysOnTopHint
            self.setWindowFlags(current_flags)
            self.show()
            
        # 🚀 [NEW] 在显示时延时 250ms 异步物理校准半透明比例，防止 DWM 图层重构时出现 Win32 参数错误警告
        QtCore.QTimer.singleShot(250, self._apply_opacity_ui_state)

    def _on_section_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        """用户手动拖拽列宽释放后的即时存盘槽 (升级为 10 秒防抖延迟模式)"""
        # 忽略 Stretch 最后一列的自动重算，防无限信号循环
        if logical_index == 6:
            return
        if getattr(self, '_loading_widths', False) or getattr(self, '_switching_flags', False) or getattr(self, '_boot_locked', True):
            return
        if not self.isVisible():
            return
            
        # ⭐ [DEBOUNCE] 手动拖拽调整后延迟 10 秒写入，防抖并彻底避免各种内部排版信号高频乱写入损坏文件
        if not hasattr(self, '_save_timer') or self._save_timer is None:
            self._save_timer = QtCore.QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(self._save_column_widths)
        else:
            self._save_timer.stop()
            
        self._save_timer.start(10000)  # 10,000 毫秒 = 10 秒延迟

    def _save_column_widths(self) -> None:
        """物理持久化排头兵表格当前列宽数据"""
        if getattr(self, '_loading_widths', False) or getattr(self, '_switching_flags', False) or getattr(self, '_boot_locked', True):
            return
            
        # ⭐ [DEBOUNCE] 强制关闭定时器，确保一次写盘周期完成，不重复执行
        if hasattr(self, '_save_timer') and self._save_timer is not None:
            self._save_timer.stop()
            
        try:
            import json
            import os
            # 获取 7 列的当前宽度
            widths = [self.table.columnWidth(i) for i in range(7)]
            
            # ⭐ [QUIET-GATE] 纵深高阶物理数据校验：
            # 如果有任何一列宽度为 0 或者是负数，或者总长度不为7，这说明表格当前处于隐式销毁、重建、隐藏或未渲染状态。
            # 这时的列宽是由于底层窗口变化引起的虚假数据，我们微秒级直接阻断拦截，杜绝写入损坏的列宽文件！
            if len(widths) != 7 or any(w <= 0 for w in widths):
                logger.warning(f"⚠️ [HUD Column Persistence] Gated abnormal column widths (saving blocked): {widths}")
                return
                
            # 确保 logs 目录存在
            os.makedirs("logs", exist_ok=True)
            with open("logs/hud_column_widths.json", "w", encoding="utf-8") as f:
                json.dump({"widths": widths}, f, indent=4)
            logger.debug(f"💾 [HUD Column Persistence] Saved column widths: {widths}")
        except Exception as e:
            logger.warning(f"⚠️ [HUD Column Persistence] Failed to save column widths: {e}")

    def _load_column_widths(self) -> None:
        """从物理持久化文件中自动加载并还原表格列宽，支持新旧版本长度自愈兼容与超紧凑保护"""
        self._loading_widths = True  # ⭐ [SILENT-LOCK] 开启加载静默锁，阻断反向触发 resized 的自动存盘覆盖！
        
        # 🚀 [Tactical Layout] 预设超紧凑、无滚动条的黄金比例默认与上限边界
        default_compact = [86, 53, 64, 60, 46, 57]
        max_bounds = [90, 60, 70, 70, 60, 65]
        
        try:
            import json
            import os
            path = "logs/hud_column_widths.json"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                widths = data.get("widths", [])
                if widths:
                    limit_len = min(len(widths), 7)
                    for i in range(limit_len):
                        # 如果是最后一列，我们仍保持为 Stretch 填充，跳过手动设置以防破环拉伸
                        if i == 6:
                            continue
                        # ⚡ [QUIET-GATE] 上限门槛保护：确保还原列宽时自发对齐至超紧凑黄金上限，防止撑破 UI 挤出滚动条
                        target_w = min(int(widths[i]), max_bounds[i])
                        self.table.setColumnWidth(i, target_w)
                    # logger.info(f"💾 [HUD Column Persistence] Successfully restored column widths with compact guard up to {limit_len} columns: {widths[:limit_len]}")
                    return
        except Exception as e:
            logger.warning(f"⚠️ [HUD Column Persistence] Failed to load column widths: {e}")
        finally:
            self._loading_widths = False  # ⭐ [SILENT-LOCK] 无论如何确保解除静默锁
            
        # 7 列兜底默认初始超紧凑黄金宽度比例
        self.table.setColumnWidth(0, default_compact[0])  # 代码/名称
        self.table.setColumnWidth(1, default_compact[1])  # 现价
        self.table.setColumnWidth(2, default_compact[2])  # 涨幅
        self.table.setColumnWidth(3, default_compact[3])  # 周期变幅
        self.table.setColumnWidth(4, default_compact[4])  # 跟涨T值
        self.table.setColumnWidth(5, default_compact[5])  # 背离DFF

    def _render_table_only(self) -> None:
        """物理局部渲染跟风表格，纯 Python 驱动，支持无抖动重绘"""
        self._rendering_table = True
        try:
            # candidate_stocks[0] 是龙头股，跟风股表格只渲染 candidate_stocks[1:]
            followers = self.candidate_stocks[1:]
            self.table.setRowCount(len(followers))
            
            for idx, f in enumerate(followers):
                code = f["code"]
                name = f["name"]
                price = f["price"]
                pct = f["pct"]
                pct_diff = f["pct_diff"]
                t_factor = f["t_factor"]
                dff = f["dff"]
                hint = f["reason"]
                
                # 0. 代码/名称
                item_name = QtWidgets.QTableWidgetItem(f"{name}\n({code})")
                item_name.setData(Qt.ItemDataRole.UserRole, code)
                item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 1. 现价
                item_price = QtWidgets.QTableWidgetItem(f"{price:.2f}")
                item_price.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 2. 涨幅
                pct_color = "#39ff14" if pct >= 0 else "#ff073a"
                item_pct = QtWidgets.QTableWidgetItem(f"{pct:+.2f}%")
                item_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_pct.setForeground(QtGui.QColor(pct_color))
                
                # 3. 周期变幅
                diff_color = "#39ff14" if pct_diff >= 0 else "#ff073a"
                item_diff = QtWidgets.QTableWidgetItem(f"{pct_diff:+.2f}%")
                item_diff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_diff.setForeground(QtGui.QColor(diff_color))
                
                # 4. 跟涨T值
                item_t = QtWidgets.QTableWidgetItem(f"{t_factor:.1f}")
                item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 5. 背离DFF
                item_dff = QtWidgets.QTableWidgetItem(f"{dff:+.2f}")
                item_dff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # 6. 形态特征
                item_hint = QtWidgets.QTableWidgetItem(hint)
                item_hint.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_hint.setForeground(QtGui.QColor("#ff007f" if "突破" in hint else "#00f0ff"))
                
                self.table.setItem(idx, 0, item_name)
                self.table.setItem(idx, 1, item_price)
                self.table.setItem(idx, 2, item_pct)
                self.table.setItem(idx, 3, item_diff)
                self.table.setItem(idx, 4, item_t)
                self.table.setItem(idx, 5, item_dff)
                self.table.setItem(idx, 6, item_hint)
        finally:
            self._rendering_table = False

    def _on_header_clicked(self, logical_index: int) -> None:
        """纯 Python 驱动的高灵敏度表头综合排序"""
        if not hasattr(self, '_sort_column'):
            self._sort_column = -1
            self._sort_order = 'desc' # 默认降序
            
        # 翻转排序方向
        if self._sort_column == logical_index:
            self._sort_order = 'asc' if self._sort_order == 'desc' else 'desc'
        else:
            self._sort_column = logical_index
            self._sort_order = 'desc' # 新列默认降序
            
        # 根据 logical_index 选择排序键
        key_map = {
            0: lambda x: x["code"],
            1: lambda x: x["price"],
            2: lambda x: x["pct"],
            3: lambda x: x["pct_diff"],
            4: lambda x: x["t_factor"],
            5: lambda x: x["dff"],
            6: lambda x: x["reason"]
        }
        
        sort_key = key_map.get(logical_index, None)
        if not sort_key or len(self.candidate_stocks) <= 2:
            return # 无法排序或无活跃跟风股
            
        # 物理隔离龙头股 (0号位固定不动)，只对后面的跟风股进行综合排序
        leader = self.candidate_stocks[0]
        followers = self.candidate_stocks[1:]
        
        is_reverse = (self._sort_order == 'desc')
        followers.sort(key=sort_key, reverse=is_reverse)
        
        # 重新拼接并刷新渲染表格
        self.candidate_stocks = [leader] + followers
        self._render_table_only()

    def _load_opacity_config(self) -> int:
        """从 window_config.json 读取不透明度百分比，默认置顶时为 75%"""
        import os
        import json
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("SpatialFollowHUD_opacity", 75)
        except Exception as e:
            logger.error(f"Failed to load opacity config: {e}")
        return 75

    def _save_opacity_config(self, opacity: int) -> None:
        """保存不透明度百分比至 window_config.json"""
        import os
        import json
        from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
        try:
            data = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["SpatialFollowHUD_opacity"] = opacity
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save opacity config: {e}")

    def _safe_set_opacity(self, opacity: float) -> None:
        """安全修改目标不透明度，并触发 250ms 防抖倒计时以杜绝 DWM 刷新冲突"""
        self._target_opacity = opacity
        self._opacity_debounce_timer.start(250)

    def _execute_opacity_apply(self) -> None:
        """物理执行不透明度设置，由防抖定时器统一调用，绝对句柄平滑对齐，彻底消噪"""
        if not self.isVisible():
            return
        try:
            self.setWindowOpacity(self._target_opacity)
            logger.debug(f"👻 [DWM-OPACITY] Applied physical window opacity: {self._target_opacity:.2%}")
        except Exception as e:
            logger.error(f"Failed to set window opacity: {e}")

    def _on_opacity_slider_changed(self, value: int) -> None:
        """不透明度滑块拖拽响应"""
        self.opacity_pct = value
        self.lbl_opacity_val.setText(f"{value}%")
        self._save_opacity_config(value)
        
        # 只有在开启置顶模式下才让半透明生效，非置顶一律强行恢复 1.0 (100%)
        if self.stays_on_top:
            self._safe_set_opacity(value / 100.0)
            logger.debug(f"👻 [HUD Opacity] Requested opacity change: {value}%")

    def _apply_opacity_ui_state(self) -> None:
        """物理根据置顶状态应用半透明状态机与容器显隐"""
        if not hasattr(self, 'opacity_container'):
            return
        if self.stays_on_top:
            # 开启置顶 -> 自动展现亮度滑块，并物理应用半透明
            self.opacity_container.setVisible(True)
            self._safe_set_opacity(self.opacity_pct / 100.0)
        else:
            # 关闭置顶 -> 自动隐藏亮度滑块，并物理恢复全不透明
            self.opacity_container.setVisible(False)
            self._safe_set_opacity(1.0)

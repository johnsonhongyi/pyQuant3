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

class SpatialFollowHUD(QtWidgets.QDialog, WindowMixin):
    """
    SpatialFollowHUD - 盘中实时板块跟单可视化微型指挥所 (Persistent Glassmorphism HUD)
    
    采用高反差 Cyberpunk 暗黑科技玻璃拟态风格，支持纯键盘“盲操”：
    - Up/Down 方向键: 在龙头与三大跟风股之间瞬间循环切换跟单目标并联动主窗
    - Return/Enter 键: 瞬间触发所选个股的跟进决策，并投递至交易内核 (高保真跟单)
    - Esc 键: 手动收起/隐藏
    """
    
    order_submitted = pyqtSignal(str, str, float)  # (代码, 动作, 比例)

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
        self.candidate_stocks: List[Dict[str, Any]] = []  # 缓存当前的备选股票列表
        self.sector_heat_value: float = 50.0
        
        # 拖拽相关
        self._drag_pos = QtCore.QPoint()
        
        self._init_ui()
        self._setup_timer()
        
        # 恢复上次窗口坐标与尺寸 (Persist window state)
        self.load_window_position_qt(self, "SpatialFollowHUD", default_width=500, default_height=520)

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
        logger.info(f"🏇 [HUD Racing Mode] Auto-tracking toggled to: {is_checked}")
        if is_checked:
            # 立即触发一次自动拉取
            self.update_hud_data(self.sector_name)

    def _toggle_stays_on_top(self) -> None:
        """切换置顶状态"""
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
        logger.info(f"📌 [HUD stays-on-top] Changed to: {self.stays_on_top}")

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

    def _trigger_linkage(self, code: str) -> None:
        """向主窗口 / 可视化终端投递联动信号 (使用官方最规范现成联动通道与 tk_dispatch_queue 派发)"""
        if not code:
            return
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
                
            if hasattr(self, '_current_top3_sectors') and idx < len(self._current_top3_sectors):
                sname = self._current_top3_sectors[idx]
                if sname:
                    logger.info(f"👉 [HUD Hot Selector Click] 手动切换查看 Top {idx+1} 板块: {sname}")
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
                        logger.info(f"👑 [HUD Leader Label] Clicked and triggered linkage: {cand['name']}({cand['code']})")
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
        
        title_layout.addWidget(self.lbl_title)
        title_layout.addStretch()
        title_layout.addWidget(self.lbl_drag_hint)
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
        
        # [NEW] 热门风口候选导航栏 (Top 3 Hot Sectors Shortcut)
        self.hot_btns = []
        self._current_top3_sectors = []
        self._is_switching_btn = False  # 防止信号重入
        
        hot_layout = QtWidgets.QHBoxLayout()
        hot_layout.setSpacing(4)
        hot_layout.setContentsMargins(0, 2, 0, 2)
        
        lbl_hint = QtWidgets.QLabel("🔥 候选:", self)
        lbl_hint.setStyleSheet("color: rgba(0, 240, 255, 0.75); font-size: 10px; font-weight: bold;")
        hot_layout.addWidget(lbl_hint)
        
        for idx in range(3):
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
        
        # 允许纵向扩展并且有滚动条的表格展示跟风股
        self.table = QtWidgets.QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["代码/名称", "现价(涨幅)", "周期变幅", "跟涨T值", "背离DFF", "形态特征"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
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
                box-shadow: 0 0 10px #39ff14;
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
        """主界面的定时脏刷新计时器（自适应对齐 cct.duration_sleep_time）"""
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
            
        # 至少 500ms，防止极端配制下的零或负值导致 UI 线程卡死
        interval_ms = max(500, int(sleep_time * 1000))
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._on_timer_refresh)
        self.timer.start()
        logger.info(f"🛸 [HUD] 脏刷新定时器已对齐 cct.duration_sleep_time: {interval_ms} ms")

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
        
        # 1. 获取全局引擎单例
        from sector_focus_engine import get_focus_controller
        fc = get_focus_controller()
        if not fc:
            return

        # 🚀 [NEW] 实时捕获当前综合热度前 3 的核心活跃风口
        hot_sectors = fc.sector_map.get_hot_sectors(3)
        self._current_top3_sectors = [s.name for s in hot_sectors]
        
        # 实时更新 3 个热门风口候选导航按钮的字样与可视度
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
                for i, s_name in enumerate(self._current_top3_sectors):
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
                            logger.info(f"⚡ [HUD Racing Drift] 风口轮动至: {new_sec}，自动切换至新龙头: {hot_sectors[0].leader_name}({ldr_code})")
                    sector_name = new_sec
            else:
                # 🔒 手动锁定模式：根据所选名称同步高亮候选按钮
                self._is_switching_btn = True
                try:
                    for i, s_name in enumerate(self._current_top3_sectors):
                        self.hot_btns[i].setChecked(s_name == sector_name)
                finally:
                    self._is_switching_btn = False

        self.sector_name = sector_name
            
        sh = fc.sector_map.get_sector_heat(sector_name)
        if not sh:
            self.lbl_sector_name.setText(f"📡 监听: {sector_name}")
            return
            
        self.sector_heat_value = sh.heat_score
            
        # ── 维度 1: 板块全图 ──
        self.lbl_sector_name.setText(f"🪐 {sh.name}")
        
        stype = sh.sector_type or "📊 跟踪"
        self.lbl_sector_badge.setText(stype)
        # 根据板块类型动态着色
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
        leader_pct_color = "#39ff14" if sh.leader_change_pct >= 0 else "#ff073a"
        self.lbl_leader_name.setText(f"🐉 {sh.leader_name} ({sh.leader_code})")
        self.lbl_leader_pct.setText(f"{sh.leader_change_pct:+.2f}%")
        self.lbl_leader_pct_diff.setText(f"变动: <span style='color:{leader_pct_color};'>{sh.leader_pct_diff:+.2f}%</span>")
        self.lbl_leader_dff.setText(f"背离: <b>{sh.leader_dff:+.2f}</b>")
        self.lbl_leader_vwap.setText(f"均线: <b>{sh.leader_vwap:.2f}</b>")

        # ── 维度 3: 跟风明细 ──
        self.candidate_stocks.clear()
        
        # 0号位永远预留给龙头
        self.candidate_stocks.append({
            "code": sh.leader_code,
            "name": sh.leader_name,
            "price": sh.leader_vwap, # 默认为最新价
            "pct": sh.leader_change_pct,
            "pct_diff": sh.leader_pct_diff,
            "dff": sh.leader_dff,
            "t_factor": 10.0, # 默认最高强度
            "reason": "最强统治地位龙头股",
            "is_leader": True
        })
        
        # 1-3号位跟风股
        followers = sh.follower_detail[:3]
        self.table.setRowCount(len(followers))
        
        for idx, f in enumerate(followers):
            code = f.get('code', '')
            name = f.get('name', '跟风兵')
            price = f.get('price', 0.0)
            pct = f.get('pct', 0.0)
            pct_diff = f.get('pct_diff', 0.0)
            t_factor = f.get('t_factor', 0.0)
            dff = f.get('dff', 0.0)
            hint = f.get('pattern_hint', '突破确认')
            
            self.candidate_stocks.append({
                "code": code,
                "name": name,
                "price": price,
                "pct": pct,
                "pct_diff": pct_diff,
                "dff": dff,
                "t_factor": t_factor,
                "reason": hint,
                "is_leader": False
            })
            
            # 渲染表格行
            item_name = QtWidgets.QTableWidgetItem(f"{name}\n({code})")
            item_name.setData(Qt.ItemDataRole.UserRole, code)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            pct_color = "#39ff14" if pct >= 0 else "#ff073a"
            item_pct = QtWidgets.QTableWidgetItem(f"{price:.2f}\n({pct:+.1f}%)")
            item_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_pct.setForeground(QtGui.QColor(pct_color))
            
            diff_color = "#39ff14" if pct_diff >= 0 else "#ff073a"
            item_diff = QtWidgets.QTableWidgetItem(f"{pct_diff:+.2f}%")
            item_diff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_diff.setForeground(QtGui.QColor(diff_color))
            
            item_t = QtWidgets.QTableWidgetItem(f"{t_factor:.1f}")
            item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_dff = QtWidgets.QTableWidgetItem(f"{dff:+.2f}")
            item_dff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_hint = QtWidgets.QTableWidgetItem(hint)
            item_hint.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_hint.setForeground(QtGui.QColor("#ff007f" if "突破" in hint else "#00f0ff"))
            
            self.table.setItem(idx, 0, item_name)
            self.table.setItem(idx, 1, item_pct)
            self.table.setItem(idx, 2, item_diff)
            self.table.setItem(idx, 3, item_t)
            self.table.setItem(idx, 4, item_dff)
            self.table.setItem(idx, 5, item_hint)

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
        
        # 默认选中锁定设置
        if signal_item and hasattr(signal_item, 'code'):
            # 如果是具体信号触发，优先高亮匹配的个股代码
            for s_idx, cand in enumerate(self.candidate_stocks):
                if cand["code"] == signal_item.code:
                    self.selected_index = s_idx
                    break
        else:
            # 否则默认锁定龙头
            if self.selected_index >= len(self.candidate_stocks):
                self.selected_index = 0

        self._update_highlight_border()

    def _update_highlight_border(self) -> None:
        """更新锁定高亮边框和文案"""
        if not self.candidate_stocks or self.selected_index >= len(self.candidate_stocks):
            return
            
        selected = self.candidate_stocks[self.selected_index]
        code = selected["code"]
        name = selected["name"]
        is_ldr = selected["is_leader"]
        
        role = "🐉 最强领涨龙头" if is_ldr else f"🥈 爆发跟风排头兵 #{self.selected_index}"
        
        self.lbl_follow_target.setText(f"🎯 锁定跟单: {name} ({code}) [{role}]")
        self.lbl_follow_reason.setText(f"考量逻辑: {selected['reason']} | 量价背离DFF={selected['dff']:.2f}")
        
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
        if self.isVisible() and self.sector_name:
            self.update_hud_data(self.sector_name)

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
            from sector_focus_engine import get_focus_controller
            fc = get_focus_controller()
            if fc and fc._df_realtime is not None and code in fc._df_realtime.index:
                price = float(fc._df_realtime.loc[code, 'price'])
                
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

    # ── 强健的键盘驱动盲操设计 (Up/Down/Return/Esc) ──
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        
        # Up 键向上移动循环锁定目标
        if key == Qt.Key.Key_Up:
            if self.candidate_stocks:
                self.selected_index = (self.selected_index - 1) % len(self.candidate_stocks)
                self._update_highlight_border()
                # [LINKAGE] 联动切换主窗口/K线可视化图表
                selected = self.candidate_stocks[self.selected_index]
                self._trigger_linkage(selected["code"])
            event.accept()
            return
            
        # Down 键向下移动循环锁定目标
        elif key == Qt.Key.Key_Down:
            if self.candidate_stocks:
                self.selected_index = (self.selected_index + 1) % len(self.candidate_stocks)
                self._update_highlight_border()
                # [LINKAGE] 联动切换主窗口/K线可视化图表
                selected = self.candidate_stocks[self.selected_index]
                self._trigger_linkage(selected["code"])
            event.accept()
            return
            
        # Return / Enter 键一键触发跟单
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_submit_clicked()
            event.accept()
            return
            
        # Esc 键隐藏/隐藏
        elif key == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
            
        # 空格键：在 HUD 获得焦点时，允许隐藏 (和主窗 toggle 一致)
        elif key == Qt.Key.Key_Space:
            self.hide()
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

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # 在退出/隐藏时持久化当前窗口坐标 (DPI-aware save)
        self.save_window_position_qt_visual(self, "SpatialFollowHUD")
        super().closeEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self.save_window_position_qt_visual(self, "SpatialFollowHUD")
        super().hideEvent(event)

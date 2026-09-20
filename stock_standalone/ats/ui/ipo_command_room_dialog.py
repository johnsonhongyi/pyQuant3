# -*- coding: utf-8 -*-
"""
ats/ui/ipo_command_room_dialog.py
-----------------------------------
新股次新股集中交易指挥室 (IPO Fleet Command Room Dialog)
核心能力与交互对齐：
1. 【非模态独立伴侣窗口】：不阻塞主窗口，自由停靠副屏；
2. 【点击与上下联动】：单击或方向键切行，直接联动检测工具主表格定位高亮并联动通达信；
3. 【双击 / 空格调出 SBC】：秒级调出 10d VWAP 走势；
4. 【F / 回车联动通达信】：全系统统一习惯；
5. 【完整右键功能】：定位主看板、调出 SBC、单只执行决议、复制股票代码、加自选；
6. 【掌握全数据】：全池赛马天梯、持仓组合盈亏与待执行指令清单。
"""

import sys
import os
import time
import math
import logging
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QMessageBox, QFrame, QCheckBox, QMenu, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QColor, QFont, QAction, QKeySequence

from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOOrderDirective, IPOTradingPosition
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal
from ats.alert_notifier import AlertNotifier
from ats.ui.styles import (
    setup_header_persistence, auto_fit_columns_once,
    load_config_node, save_config_node, save_config_nodes,
    NumericTableWidgetItem
)

logger = logging.getLogger("IPOCommandRoomDialog")

# 集中交易全局战术角色对应标准中文映射字典
ROLE_CN_MAP = {
    "LEADER": "🥇 领头羊",
    "VANGUARD": "🥈 梯队前锋",
    "SECONDARY_BUY": "👑 次级买点",
    "RESONANCE_BUY": "⚡ 共振加速",
    "BASE_PREORDER": "🎯 筑底预埋",
    "SWING_PREORDER": "🔭 通道突破",
    "FOLLOWER": "🥉 后排跟风",
    "CLIMAX_EXIT": "🚨 高潮平仓",
    "PANIC_DEFENSE": "🛡️ 全局避险",
    "STOP_LOSS": "⛔ 买错立斩",
    "CLIMAX_DEFENSE": "🌋 高潮避险",
}

# 实盘持仓状态对应中文映射字典
POS_STATUS_CN_MAP = {
    "HOLDING": "🟢 持仓中",
    "CLOSED": "⚪ 已平仓",
    "STOP_LOSS": "⛔ 止损清仓",
    "PROFIT_EXIT": "💰 止盈锁定",
}


class IPOCommandRoomTableWidget(QTableWidget):
    """
    【指挥室高响应专用表格】
    - 原生拦截 Up / Down / PageUp / PageDown，切行时防抖联动主检测工具与外部通达信；
    - 支持 Space (空格) 调出 SBC 走势图；
    - 支持 F 键 / 回车联动通达信；
    - 全面支持点击表头升序/降序数值智能排序；
    - 接入全系统统一标准的列宽自由拖拽与跨会话自动持久化体系 (setup_persistence)；
    - 支持一键自适应列宽与一键恢复默认列宽。
    """
    def __init__(self, parent_cmd_room=None):
        super().__init__(parent_cmd_room)
        self.cmd_room = parent_cmd_room
        self.setMouseTracking(True)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self._config_key: Optional[str] = None
        self._default_widths: Optional[List[int]] = None

    def sortItems(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        """【排序同步守卫】：执行排序前同步设置表头 Indicator，保证升降序箭头正确更新"""
        if self.horizontalHeader() is not None:
            self.horizontalHeader().setSortIndicator(column, order)
        super().sortItems(column, order)

    def setup_persistence(self, config_key: str, default_widths: Optional[List[int]] = None, max_widths=None):
        """接入全系统统一标准持久化体系，表头全列 Interactive 自由拖拽且防抖自动落盘"""
        self._config_key = config_key
        self._default_widths = default_widths
        setup_header_persistence(
            self,
            config_key=config_key,
            default_widths=default_widths,
            max_widths=max_widths
        )

    def save_column_widths(self):
        """显式触发列宽状态落盘"""
        if hasattr(self, "save_header_state"):
            self.save_header_state()

    def restore_column_widths(self):
        """显式触发列宽状态恢复"""
        if hasattr(self, "restore_header_state"):
            self.restore_header_state()

    def reset_default_widths(self):
        """重置为默认列宽并持久化"""
        if not self._default_widths:
            return
        header = self.horizontalHeader()
        header.blockSignals(True)
        for col, width in enumerate(self._default_widths):
            if col < self.columnCount():
                self.setColumnWidth(col, width)
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.blockSignals(False)
        self.save_column_widths()

    def auto_fit_columns(self):
        """一键自适应列宽，并保持 Interactive 自由拖拽与持久化"""
        self.resizeColumnsToContents()
        header = self.horizontalHeader()
        header.blockSignals(True)
        for col in range(self.columnCount()):
            curr_w = max(self.columnWidth(col), 48)
            self.setColumnWidth(col, curr_w)
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.blockSignals(False)
        self.save_column_widths()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            super().keyPressEvent(event)
            curr = self.currentRow()
            if curr >= 0 and self.cmd_room:
                self.cmd_room._trigger_linkage_for_table_row(self, curr, force=False)
            event.accept()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F):
            curr = self.currentRow()
            if curr >= 0 and self.cmd_room:
                self.cmd_room._trigger_linkage_for_table_row(self, curr, force=True)
            event.accept()
            return
        elif key == Qt.Key.Key_Space:
            curr = self.currentRow()
            if curr >= 0 and self.cmd_room:
                code = self.cmd_room._extract_code_from_table(self, curr)
                if code:
                    self.cmd_room._open_sbc_for_code(code)
            event.accept()
            return
        super().keyPressEvent(event)


class IPOCommandRoomDialog(QDialog):
    """新股次新股集中交易总指挥室 (非模态独立伴侣窗口)"""

    def __init__(self, parent_detector_dialog=None):
        # 传入 None 作为父对象，实现真正独立的非模态伴侣窗口，支持自由悬浮与副屏看盘
        super().__init__(None)
        self.detector_dialog = parent_detector_dialog

        self.setWindowTitle("🚢 新股次新集中交易指挥室 (山外有山·全局统筹调度中心)")
        self.setMinimumSize(1080, 660)
        self.resize(1180, 720)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d0e15;
                color: #ffffff;
            }
            QLabel {
                color: #e2e2e5;
                font-size: 8.5pt;
            }
            QGroupBox {
                border: 1px solid #232536;
                border-radius: 4px;
                margin-top: 8px;
                font-weight: bold;
                color: #00e5ff;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #1a1c29;
                border: 1px solid #33374d;
                border-radius: 3px;
                color: #ffffff;
                font-size: 8.5pt;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #26293d;
                border-color: #00e5ff;
            }
            /* 极窄模式表格：深色网格分割线、交替背景色与高对比选中态 */
            QTableWidget {
                background-color: #10121d;
                alternate-background-color: #131522;
                border: 1px solid #232536;
                gridline-color: #1d1f2e;
                color: #ffffff;
                font-size: 8.5pt;
                selection-background-color: #26334d;
                selection-color: #ffffff;
            }
            /* 极窄模式表头：明确的垂直右边框与下边框分隔线 */
            QHeaderView {
                background-color: #161826;
                border: none;
            }
            QHeaderView::section {
                background-color: #161826;
                color: #9aa0a6;
                border: none;
                border-right: 1px solid #232536;
                border-bottom: 1px solid #232536;
                padding: 2px 4px;
                font-weight: bold;
                font-size: 8.5pt;
            }
            QTableCornerButton::section {
                background-color: #161826;
                border: 1px solid #232536;
            }
            /* 极窄模式滚动条：8px深色极窄滑块，彻底消除原生白色粗条与撕裂 */
            QScrollBar:vertical {
                border: none;
                background-color: #0f1018;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #2c2e3e;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #404358;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                background-color: #0f1018;
                height: 8px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background-color: #2c2e3e;
                min-width: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #404358;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            /* 极窄模式分割条：彻底消灭 Windows 原生亮白手柄，采用暗黑科技微光配色 */
            QSplitter::handle {
                background-color: #1c1e2d;
                border: none;
            }
            QSplitter::handle:horizontal {
                width: 2px;
            }
            QSplitter::handle:vertical {
                height: 2px;
            }
            QSplitter::handle:hover {
                background-color: #00e5ff;
            }
            QSplitter::handle:pressed {
                background-color: #00b0ff;
            }
        """)

        self.trading_center = IPOTradingCenter.get_instance()
        self._last_linkage_code = ""

        # 视图模式控制：持仓（ACTIVE / CLOSED），指令（PENDING / HISTORY）
        self._pos_view_mode = "ACTIVE"
        self._orders_view_mode = "PENDING"
        self._current_closed_positions_list: List[Dict[str, Any]] = []
        self._current_signal_logs_list: List[Dict[str, Any]] = []
        self._voice_enabled = load_config_node("ipo_cmd_voice_enabled", True)

        # 联动防抖定时器 (20ms)
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._pending_code = ""
        self._linkage_timer.timeout.connect(self._fire_debounced_linkage)
        # 顶部领头羊标签点击联动 - 存储当前龙头代码
        self._top_leader_code: str = ""

        self._init_ui()
        self._load_dialog_state()
        self.refresh_data()

        # 1.5秒自动刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(1500)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # ── 1. 顶部总资产与舰队战情概览胶囊卡片 ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.lbl_capital = QLabel("💰 总资金: -- | 可用: --")
        self.lbl_capital.setStyleSheet("background-color: #181b28; border: 1px solid #2f344d; border-radius: 4px; padding: 4px 10px; color: #ffd700; font-weight: bold;")
        top_bar.addWidget(self.lbl_capital)

        self.lbl_positions = QLabel("📊 持仓: 0 只 (0.0%仓)")
        self.lbl_positions.setStyleSheet("background-color: #181b28; border: 1px solid #2f344d; border-radius: 4px; padding: 4px 10px; color: #00ff88; font-weight: bold;")
        top_bar.addWidget(self.lbl_positions)

        self.lbl_leader = QLabel("🥇 爆款领头羊: --")
        self.lbl_leader.setStyleSheet("background-color: #261a14; border: 1px solid #5a351e; border-radius: 4px; padding: 4px 10px; color: #ffaa00; font-weight: bold;")
        # 【领头羊点击联动】手型指针提示可点击，installEventFilter 零侵入拦截鼠标事件
        self.lbl_leader.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_leader.setToolTip("🖱️ 单击：定位龙头股并高亮选中 | 联动通达信")
        self.lbl_leader.installEventFilter(self)
        top_bar.addWidget(self.lbl_leader)

        top_bar.addStretch()

        # 全仓轮动模式开关
        self.chk_rotation = QCheckBox("🔄 全仓轮动模式")
        self.chk_rotation.setStyleSheet("color: #ffd700; font-weight: bold;")
        self.chk_rotation.setToolTip("开启全仓轮动模式 (100% 仓位动态腾挪接力新龙头，弃弱留强高效轮转)")
        self.chk_rotation.setChecked(self.trading_center.enable_full_rotation)
        self.chk_rotation.toggled.connect(self._on_rotation_toggled)
        top_bar.addWidget(self.chk_rotation)

        # 语音报警状态开关
        self.btn_voice = QPushButton("🔊 语音告警: 开" if self._voice_enabled else "🔈 语音告警: 关")
        self.btn_voice.setToolTip("开启或关闭语音播报与异动通知")
        self.btn_voice.clicked.connect(self._on_toggle_voice)
        top_bar.addWidget(self.btn_voice)

        self.chk_auto_trade = QCheckBox("🤖 全自动跟随交易")
        self.chk_auto_trade.setStyleSheet("color: #00ff88; font-weight: bold;")
        self.chk_auto_trade.setChecked(self.trading_center.auto_follow_trading)
        self.chk_auto_trade.toggled.connect(self._on_auto_trade_toggled)
        top_bar.addWidget(self.chk_auto_trade)

        btn_exec_all = QPushButton("⚡ 一键执行决议")
        btn_exec_all.setStyleSheet("background-color: #4a2800; border-color: #ff9900; color: #ffaa00; font-weight: bold;")
        btn_exec_all.clicked.connect(self._on_exec_all_clicked)
        top_bar.addWidget(btn_exec_all)

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.refresh_data)
        top_bar.addWidget(btn_refresh)

        root_layout.addLayout(top_bar)

        # ── 2. 中部主分割区 (左侧赛马天梯，右侧持仓与指令) ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)

        # 左侧：全池赛马天梯与山外有山仲裁
        grp_rank = QGroupBox("🏆 全池横向赛马排位天梯 (掌握全数据·山外有山)")
        v_rank = QVBoxLayout(grp_rank)
        v_rank.setContentsMargins(4, 4, 4, 4)

        self.tbl_rank = IPOCommandRoomTableWidget(self)
        self.tbl_rank.setColumnCount(8)
        self.tbl_rank.setHorizontalHeaderLabels(["排名", "代码", "名称", "现价", "动能分", "启动时点", "角色", "集中仲裁与山外有山决议"])
        self.tbl_rank.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rank.horizontalHeader().setStretchLastSection(True)
        self.tbl_rank.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_rank.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bind_table_interactions(self.tbl_rank)
        self.tbl_rank.setup_persistence(
            "ipo_cmd_rank_table_header_v2",
            default_widths=[38, 56, 75, 56, 68, 76, 80, 260]
        )
        v_rank.addWidget(self.tbl_rank)
        self.splitter.addWidget(grp_rank)

        # 右侧：持仓组合与待执行指令
        right_panel = QWidget()
        v_right = QVBoxLayout(right_panel)
        v_right.setContentsMargins(0, 0, 0, 0)
        v_right.setSpacing(6)

        # 右上方：持仓组合与历史战绩
        self.grp_pos = QGroupBox("💼 实盘持仓组合与复盘 (买错跌破 VWAP 0.6% 立即出局斩仓)")
        v_pos = QVBoxLayout(self.grp_pos)
        v_pos.setContentsMargins(4, 4, 4, 4)
        v_pos.setSpacing(4)

        # 持仓卡片切换栏 (🟢 活跃持仓 vs 📜 历史平仓战绩)
        h_pos_tabs = QHBoxLayout()
        h_pos_tabs.setSpacing(4)
        self.btn_pos_active = QPushButton("🟢 活跃持仓 (0)")
        self.btn_pos_active.setCheckable(True)
        self.btn_pos_active.setChecked(True)
        self.btn_pos_active.setStyleSheet("font-weight: bold; color: #00ff88; background-color: #1a2a22; border-color: #00ff88;")
        self.btn_pos_active.clicked.connect(lambda: self._set_pos_view_mode("ACTIVE"))
        h_pos_tabs.addWidget(self.btn_pos_active)

        self.btn_pos_closed = QPushButton("📜 历史平仓战绩 (0)")
        self.btn_pos_closed.setCheckable(True)
        self.btn_pos_closed.setChecked(False)
        self.btn_pos_closed.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
        self.btn_pos_closed.clicked.connect(lambda: self._set_pos_view_mode("CLOSED"))
        h_pos_tabs.addWidget(self.btn_pos_closed)
        h_pos_tabs.addStretch()
        v_pos.addLayout(h_pos_tabs)

        self.tbl_pos = IPOCommandRoomTableWidget(self)
        self.tbl_pos.setColumnCount(7)
        self.tbl_pos.setHorizontalHeaderLabels(["代码", "名称", "股数", "成本价", "现价", "浮盈%", "状态"])
        self.tbl_pos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_pos.horizontalHeader().setStretchLastSection(True)
        self.tbl_pos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_pos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bind_table_interactions(self.tbl_pos)
        self.tbl_pos.setup_persistence(
            "ipo_cmd_pos_table_header_v2",
            default_widths=[56, 75, 56, 58, 58, 65, 80]
        )
        v_pos.addWidget(self.tbl_pos)
        v_right.addWidget(self.grp_pos, 2)

        # 右下方：待执行指令与信号迭代日志
        self.grp_orders = QGroupBox("📋 集中交易调度与信号迭代日志 (弃弱换马 / 领头羊进击 / 买错立斩)")
        v_orders = QVBoxLayout(self.grp_orders)
        v_orders.setContentsMargins(4, 4, 4, 4)
        v_orders.setSpacing(4)

        # 指令卡片切换栏 (⏳ 待执行指令 vs 📋 历史信号日志)
        h_orders_tabs = QHBoxLayout()
        h_orders_tabs.setSpacing(4)
        self.btn_orders_pending = QPushButton("⏳ 待执行指令 (0)")
        self.btn_orders_pending.setCheckable(True)
        self.btn_orders_pending.setChecked(True)
        self.btn_orders_pending.setStyleSheet("font-weight: bold; color: #00e5ff; background-color: #14242e; border-color: #00e5ff;")
        self.btn_orders_pending.clicked.connect(lambda: self._set_orders_view_mode("PENDING"))
        h_orders_tabs.addWidget(self.btn_orders_pending)

        self.btn_orders_history = QPushButton("📋 历史信号日志 (0)")
        self.btn_orders_history.setCheckable(True)
        self.btn_orders_history.setChecked(False)
        self.btn_orders_history.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
        self.btn_orders_history.clicked.connect(lambda: self._set_orders_view_mode("HISTORY"))
        h_orders_tabs.addWidget(self.btn_orders_history)
        h_orders_tabs.addStretch()
        v_orders.addLayout(h_orders_tabs)

        self.tbl_orders = IPOCommandRoomTableWidget(self)
        self.tbl_orders.setColumnCount(6)
        self.tbl_orders.setHorizontalHeaderLabels(["动作", "代码", "标的", "价格", "建议仓位", "决议依据理由"])
        self.tbl_orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_orders.horizontalHeader().setStretchLastSection(True)
        self.tbl_orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bind_table_interactions(self.tbl_orders)
        self.tbl_orders.setup_persistence(
            "ipo_cmd_orders_table_header_v2",
            default_widths=[75, 56, 75, 58, 68, 220]
        )
        v_orders.addWidget(self.tbl_orders)
        v_right.addWidget(self.grp_orders, 3)

        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 3)
        root_layout.addWidget(self.splitter)

        # ── 3. 底部操作栏 ──
        bottom_bar = QHBoxLayout()
        lbl_tip = QLabel(
            "💡 [联动操盘法则] 单击行或方向键 [↑/↓]: 直接联动检测工具并聚焦定位 code | "
            "[空格 / 双击]: 调出 SBC 走势 | [F / 回车]: 联动通达信看盘 | [右键]: 专业操作菜单"
        )
        lbl_tip.setStyleSheet("color: #8f93a8; font-size: 8.5pt;")
        bottom_bar.addWidget(lbl_tip)
        bottom_bar.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.hide)
        bottom_bar.addWidget(btn_close)
        root_layout.addLayout(bottom_bar)

    def _bind_table_interactions(self, table: QTableWidget):
        """为表格绑定全套点击、切行、双击与右键菜单交互"""
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self._show_context_menu(table, pos))
        table.cellClicked.connect(lambda r, c: self._on_table_cell_clicked(table, r))
        table.currentCellChanged.connect(lambda cur_r, cur_c, prev_r, prev_c: self._on_table_current_cell_changed(table, cur_r, prev_r))
        table.cellDoubleClicked.connect(lambda r, c: self._on_table_double_clicked(table, r, c))

    def _extract_code_from_table(self, table: QTableWidget, row: int) -> str:
        """从表格行中智能提取 6 位股票代码"""
        if row < 0 or row >= table.rowCount():
            return ""
        # 1. 优先根据表头精确查找 "代码" 列
        for c in range(table.columnCount()):
            h_item = table.horizontalHeaderItem(c)
            if h_item and "代码" in h_item.text():
                it = table.item(row, c)
                if it and it.text().strip():
                    clean = "".join(ch for ch in it.text().strip() if ch.isdigit()).zfill(6)
                    if len(clean) == 6:
                        return clean
        # 2. 兜底策略：遍历所有列，排除含 ":" 的时间戳，寻找 6 位数字代码
        for c in range(table.columnCount()):
            it = table.item(row, c)
            if it and it.text().strip():
                txt = it.text().strip()
                if ":" in txt:
                    continue
                clean = "".join(ch for ch in txt if ch.isdigit()).zfill(6)
                if len(clean) == 6 and clean.startswith(("0", "3", "6", "8", "4", "9")):
                    return clean
        return ""

    def _extract_name_from_table(self, table: QTableWidget, row: int) -> str:
        """从表格行中智能提取股票名称"""
        if row < 0 or row >= table.rowCount():
            return ""
        # 1. 优先根据表头查找 "名称" 或 "标的" 列
        for c in range(table.columnCount()):
            h_item = table.horizontalHeaderItem(c)
            if h_item and ("名称" in h_item.text() or "标的" in h_item.text()):
                it = table.item(row, c)
                if it and it.text().strip():
                    txt = it.text().strip()
                    if not txt.isdigit():
                        return txt
        # 2. 兜底策略
        for c in range(table.columnCount()):
            it = table.item(row, c)
            if it and it.text().strip():
                txt = it.text().strip()
                if not txt.isdigit() and ":" not in txt and len(txt) <= 10:
                    return txt
        return ""

    def _on_table_cell_clicked(self, table: QTableWidget, row: int):
        """鼠标单击行：直接联动检测工具中的 code 进行直接操作，并联动通达信"""
        self._trigger_linkage_for_table_row(table, row, force=False)

    def _on_table_current_cell_changed(self, table: QTableWidget, cur_r: int, prev_r: int):
        """键盘方向键移动行切换高亮：平滑联动"""
        if cur_r < 0 or cur_r == prev_r:
            return
        self._trigger_linkage_for_table_row(table, cur_r, force=False)

    def _open_arbitration_detail_for_row(self, table: QTableWidget, row: int):
        """【🎯 集中仲裁极速详情窗】：从单例复用池秒级调出/刷新详情窗 (支持平仓战绩与信号迭代日志)"""
        code = self._extract_code_from_table(table, row)
        if not code:
            return

        closed_pos_item = None
        signal_log_item = None

        if table is self.tbl_pos and self._pos_view_mode == "CLOSED":
            if 0 <= row < len(self._current_closed_positions_list):
                closed_pos_item = self._current_closed_positions_list[row]

        if table is self.tbl_orders and self._orders_view_mode == "HISTORY":
            if 0 <= row < len(self._current_signal_logs_list):
                signal_log_item = self._current_signal_logs_list[row]

        sig = self.trading_center._reports_cache.get(code)
        if sig is None:
            for s in self.trading_center._ranked_cache:
                if s.code == code:
                    sig = s
                    break
        directive = None
        for d in self.trading_center.get_pending_directives():
            if d.code == code:
                directive = d
                break
        try:
            from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog
            IPOArbitrationDetailDialog.show_or_update(
                code, signal_obj=sig, directive_obj=directive,
                closed_pos=closed_pos_item, log_item=signal_log_item,
                parent=self
            )
        except Exception as e:
            logger.error(f"调出集中仲裁透视详情窗异常: {e}")

    def _on_table_double_clicked(self, table: QTableWidget, row: int, col: int = -1):
        """
        双击单元格智能分发：
        - 若处于历史平仓战绩模式或历史信号日志模式：直接秒级调出全流程复盘详情窗；
        - 若双击集中仲裁/决议/理由/角色列：秒级调出/复用集中仲裁详情窗 (极速模式)；
        - 若双击其它列 (代码/名称/现价等)：秒级调出 SBC 10d VWAP 走势图。
        """
        code = self._extract_code_from_table(table, row)
        if not code:
            return

        # 操盘手复盘诉求：在历史平仓战绩或信号迭代日志模式下，双击整行任意列直接看详细复盘
        if table is self.tbl_pos and self._pos_view_mode == "CLOSED":
            self._open_arbitration_detail_for_row(table, row)
            return

        if table is self.tbl_orders and self._orders_view_mode == "HISTORY":
            self._open_arbitration_detail_for_row(table, row)
            return

        is_arbitration_col = False
        if table is self.tbl_rank and col in (6, 7):  # 角色 或 集中仲裁与山外有山决议
            is_arbitration_col = True
        elif table is self.tbl_orders and col in (0, 5):  # 动作 或 决议依据理由
            is_arbitration_col = True

        if is_arbitration_col:
            self._open_arbitration_detail_for_row(table, row)
        else:
            self._open_sbc_for_code(code)

    def _trigger_linkage_for_table_row(self, table: QTableWidget, row: int, force: bool = False):
        """统一防抖联动分发入口"""
        code = self._extract_code_from_table(table, row)
        if not code:
            return
        if not force and code == self._last_linkage_code:
            return
        self._pending_code = code
        self._linkage_timer.start(20)

    def _fire_debounced_linkage(self):
        """20ms 防抖落地联动：同步主检测工具 code 焦点与通达信"""
        code = self._pending_code
        if not code or code == self._last_linkage_code:
            return
        self._last_linkage_code = code

        # 1. 核心联动：直接联动主检测工具中的 code 进行直接操作 (滚动居中、高亮选中该行)
        if self.detector_dialog and hasattr(self.detector_dialog, "select_and_focus_code"):
            try:
                self.detector_dialog.select_and_focus_code(code, trigger_linkage=False)
            except Exception as e:
                logger.debug(f"联动主检测工具异常: {e}")

        # 2. 联动通达信/同花顺终端
        self._broadcast_link_external(code)

    def _broadcast_link_external(self, code: str):
        """联动外部通达信/同花顺终端"""
        try:
            from linkage_service import get_link_manager
            lm = get_link_manager()
            if lm:
                clean_c = "".join(c for c in str(code) if c.isdigit()).zfill(6)
                lm.push(clean_c, flags={'tdx': True, 'ths': True, 'dfcf': False}, auto=False)
        except Exception as e:
            logger.debug(f"[IPOCommandRoom] 外部联动异常: {e}")

    def _open_sbc_for_code(self, code: str):
        """调出 SBC 10d VWAP 走势图"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            dlg = open_sbc_chart_dialog(code=code, period_mode="10d")
            if dlg:
                dlg.show()
                dlg.raise_()
                dlg.activateWindow()
        except Exception as e:
            logger.error(f"打开 SBC 走势图异常: {e}")

    def _show_context_menu(self, table: QTableWidget, pos):
        """【右键专业功能菜单】对齐检测工具核心功能"""
        item = table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code = self._extract_code_from_table(table, row)
        name = self._extract_name_from_table(table, row)
        if not code:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 22px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #00e5ff;
            }
        """)

        # 0. 集中仲裁与决议透视详情窗 (极速复用模式)
        act_detail = menu.addAction(f"🎯 查看集中仲裁与山外有山决议详情 ({code} {name})")
        act_detail.triggered.connect(lambda: self._open_arbitration_detail_for_row(table, row))
        menu.addSeparator()

        # 1. SBC 走势图
        act_sbc = menu.addAction(f"📈 调出 SBC 10d 走势图 (空格 / 双击)")
        act_sbc.triggered.connect(lambda: self._open_sbc_for_code(code))

        # 2. 定位到主检测工具
        act_locate = menu.addAction(f"🔍 在检测工具中高亮并聚焦 ({code} {name})")
        act_locate.triggered.connect(lambda: self._fire_debounced_linkage_force(code))

        # 3. 联动通达信看盘
        act_tdx = menu.addAction(f"📡 联动通达信看盘 (F / 回车)")
        act_tdx.triggered.connect(lambda: self._broadcast_link_external(code))

        menu.addSeparator()

        # 4. 单只立即执行决议 (精准执行)
        # 寻找该标的是否有待执行指令
        target_directive = None
        for d in self.trading_center.get_pending_directives():
            if d.code == code:
                target_directive = d
                break
        
        if target_directive:
            act_exec_single = menu.addAction(f"⚡ 立即执行该股决议: [{target_directive.action}] {target_directive.name}")
            act_exec_single.triggered.connect(lambda: self._execute_single_directive(target_directive))
        else:
            # 若已持仓，提供一键平仓选项
            pos_dict = self.trading_center._positions.get(code)
            if pos_dict and pos_dict.shares > 0:
                act_close_single = menu.addAction(f"⛔ 立即平仓此持仓 ({name} {pos_dict.shares}股)")
                act_close_single.triggered.connect(lambda: self._close_single_position(code, name))

        menu.addSeparator()

        # 5. 复制股票代码
        act_copy = menu.addAction(f"📋 复制股票代码: {code}")
        def _copy_c():
            cb = QApplication.clipboard()
            if cb:
                cb.setText(code)
        act_copy.triggered.connect(_copy_c)

        # 6. 复制详情
        desc_info = ""
        it_desc = table.item(row, table.columnCount() - 1)
        if it_desc:
            desc_info = it_desc.text().strip()
        act_copy_all = menu.addAction(f"📋 复制名称与决议详情")
        def _copy_all():
            cb = QApplication.clipboard()
            if cb:
                cb.setText(f"{code} {name} | {desc_info}")
        act_copy_all.triggered.connect(_copy_all)

        menu.addSeparator()

        # 7. 列宽自适应与恢复默认 (对齐系统级体验)
        act_fit_cols = menu.addAction("📐 一键自适应列宽 (当前视口)")
        act_fit_cols.triggered.connect(lambda: table.auto_fit_columns() if hasattr(table, "auto_fit_columns") else None)

        act_reset_cols = menu.addAction("🔄 恢复默认列宽布局")
        act_reset_cols.triggered.connect(lambda: table.reset_default_widths() if hasattr(table, "reset_default_widths") else None)

        menu.exec(table.mapToGlobal(pos))

    def _load_dialog_state(self):
        """恢复指挥室窗口尺寸、位置与 Splitter 左右分割比例"""
        try:
            geo = load_config_node("ipo_cmd_dialog_geometry")
            if geo and isinstance(geo, dict):
                self.setGeometry(
                    geo.get("x", 100),
                    geo.get("y", 100),
                    geo.get("width", 1180),
                    geo.get("height", 720)
                )
            split_hex = load_config_node("ipo_cmd_splitter_state")
            if split_hex and isinstance(split_hex, str) and hasattr(self, "splitter"):
                from PyQt6.QtCore import QByteArray
                self.splitter.restoreState(QByteArray.fromHex(split_hex.encode("utf-8")))
                self.splitter.setHandleWidth(2)
        except Exception as e:
            logger.debug(f"恢复指挥室窗口状态异常: {e}")

    def _save_dialog_state(self):
        """集中物理原子落盘保存窗口几何、Splitter 比例与各表格列宽"""
        try:
            nodes = {
                "ipo_cmd_dialog_geometry": {
                    "x": self.x(),
                    "y": self.y(),
                    "width": self.width(),
                    "height": self.height()
                }
            }
            if hasattr(self, "splitter") and self.splitter:
                nodes["ipo_cmd_splitter_state"] = self.splitter.saveState().toHex().data().decode("utf-8")
            save_config_nodes(nodes)

            # 显式触发三个表格列宽立即物理落盘 (杜绝防抖延时丢失)
            if hasattr(self, "tbl_rank") and hasattr(self.tbl_rank, "save_column_widths"):
                self.tbl_rank.save_column_widths()
            if hasattr(self, "tbl_pos") and hasattr(self.tbl_pos, "save_column_widths"):
                self.tbl_pos.save_column_widths()
            if hasattr(self, "tbl_orders") and hasattr(self.tbl_orders, "save_column_widths"):
                self.tbl_orders.save_column_widths()
        except Exception as e:
            logger.debug(f"保存指挥室窗口状态异常: {e}")

    def closeEvent(self, event):
        self._save_dialog_state()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._save_dialog_state()
        super().hideEvent(event)

    def _fire_debounced_linkage_force(self, code: str):
        """强制定位并激活主检测工具"""
        if self.detector_dialog and hasattr(self.detector_dialog, "select_and_focus_code"):
            self.detector_dialog.select_and_focus_code(code, trigger_linkage=True)
            self.detector_dialog.raise_()
            self.detector_dialog.activateWindow()

    def _execute_single_directive(self, directive: IPOOrderDirective):
        """执行单只决议"""
        success = self.trading_center.execute_directive(directive)
        if success:
            QMessageBox.information(self, "执行成功", f"标的 [{directive.name}({directive.code})] 决议已成功执行！")
            self.refresh_data()

    def _close_single_position(self, code: str, name: str):
        """平仓单只持仓"""
        pos = self.trading_center._positions.get(code)
        if not pos or pos.shares <= 0:
            return
        d = IPOOrderDirective(
            action="SELL", code=code, name=name, price=pos.current_price or pos.cost_price,
            shares=pos.shares, size_pct=0.0, urgency="CRITICAL", reason="操盘手手动在指挥室执行平仓"
        )
        self.trading_center.execute_directive(d)
        QMessageBox.information(self, "已平仓", f"标的 [{name}({code})] 已成功平仓！资金已回笼。")
        self.refresh_data()

    def _on_auto_trade_toggled(self, checked: bool):
        self.trading_center.set_auto_follow_trading(checked)

    def _on_rotation_toggled(self, checked: bool):
        """切换全仓轮动模式 (100% 动态接力换马)"""
        self.trading_center.set_full_rotation_enabled(checked)
        msg = "已开启【全仓轮动模式】！优先 100% 满仓动态换马接力新龙头。" if checked else "已恢复常规阶梯仓位模式。"
        self.chk_rotation.setToolTip(msg)
        self.refresh_data()

    def _on_toggle_voice(self):
        """开启/关闭语音与 Toast 提示"""
        self._voice_enabled = not self._voice_enabled
        save_config_node("ipo_cmd_voice_enabled", self._voice_enabled)
        AlertNotifier.get_instance().voice_enabled = self._voice_enabled
        self.btn_voice.setText("🔊 语音告警: 开" if self._voice_enabled else "🔈 语音告警: 关")

    def _set_pos_view_mode(self, mode: str):
        """切换持仓面板视图：ACTIVE (活跃持仓) / CLOSED (历史平仓战绩)"""
        self._user_selected_pos_mode = True
        if self._pos_view_mode == mode:
            return
        self._pos_view_mode = mode
        if mode == "ACTIVE":
            self.btn_pos_active.setChecked(True)
            self.btn_pos_active.setStyleSheet("font-weight: bold; color: #00ff88; background-color: #1a2a22; border-color: #00ff88;")
            self.btn_pos_closed.setChecked(False)
            self.btn_pos_closed.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
            self.tbl_pos.setColumnCount(7)
            self.tbl_pos.setHorizontalHeaderLabels(["代码", "名称", "股数", "成本价", "现价", "浮盈%", "状态"])
            self.grp_pos.setTitle("💼 舰队实盘持仓组合 (买错跌破 VWAP 0.6% 立即出局斩仓)")
        else:
            self.btn_pos_closed.setChecked(True)
            self.btn_pos_closed.setStyleSheet("font-weight: bold; color: #ffd700; background-color: #2a2614; border-color: #ffd700;")
            self.btn_pos_active.setChecked(False)
            self.btn_pos_active.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
            self.tbl_pos.setColumnCount(7)
            self.tbl_pos.setHorizontalHeaderLabels(["代码", "名称", "平仓日", "成本价", "平仓价", "实际盈亏%", "离场原因与复盘"])
            self.grp_pos.setTitle("📜 舰队历史平仓战绩回溯 (双击行调出完整迭代复盘)")
        self.refresh_data()

    def _set_orders_view_mode(self, mode: str):
        """切换指令面板视图：PENDING (待执行指令) / HISTORY (历史信号日志)"""
        if self._orders_view_mode == mode:
            return
        self._orders_view_mode = mode
        if mode == "PENDING":
            self.btn_orders_pending.setChecked(True)
            self.btn_orders_pending.setStyleSheet("font-weight: bold; color: #00e5ff; background-color: #14242e; border-color: #00e5ff;")
            self.btn_orders_history.setChecked(False)
            self.btn_orders_history.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
            self.tbl_orders.setColumnCount(6)
            self.tbl_orders.setHorizontalHeaderLabels(["动作", "代码", "标的", "价格", "建议仓位", "决议依据理由"])
            self.grp_orders.setTitle("📋 集中交易调度待执行指令清单 (弃弱换马 / 领头羊进击 / 买错立斩)")
        else:
            self.btn_orders_history.setChecked(True)
            self.btn_orders_history.setStyleSheet("font-weight: bold; color: #ffaa00; background-color: #2a2014; border-color: #ffaa00;")
            self.btn_orders_pending.setChecked(False)
            self.btn_orders_pending.setStyleSheet("font-weight: bold; color: #9aa0a6; background-color: #141620; border-color: #2b2e42;")
            self.tbl_orders.setColumnCount(6)
            self.tbl_orders.setHorizontalHeaderLabels(["时间", "级别", "动作", "代码", "标的", "迭代说明与决议依据"])
            self.grp_orders.setTitle("📋 集中交易历史信号与迭代日志 (双击行调出产生快照)")
        self.refresh_data()

    def locate_stock_in_table(self, code: str, auto_popup: bool = True, reason: str = ""):
        """
        【🎯 直达定位响应机制】：当点击通知 Toast 或外部直达请求时，唤醒置顶并高亮聚焦该行
        """
        if auto_popup:
            self.show()
            self.raise_()
            self.activateWindow()

        clean_code = "".join(ch for ch in str(code) if ch.isdigit()).zfill(6)
        if not clean_code:
            return

        # 1. 先在赛马天梯表里找
        for r in range(self.tbl_rank.rowCount()):
            c = self._extract_code_from_table(self.tbl_rank, r)
            if c == clean_code:
                self.tbl_rank.setCurrentCell(r, 0)
                it = self.tbl_rank.item(r, 0)
                if it:
                    self.tbl_rank.scrollToItem(it)
                self._trigger_linkage_for_table_row(self.tbl_rank, r, force=True)
                return

        # 2. 再在持仓表里找
        for r in range(self.tbl_pos.rowCount()):
            c = self._extract_code_from_table(self.tbl_pos, r)
            if c == clean_code:
                self.tbl_pos.setCurrentCell(r, 0)
                it = self.tbl_pos.item(r, 0)
                if it:
                    self.tbl_pos.scrollToItem(it)
                self._trigger_linkage_for_table_row(self.tbl_pos, r, force=True)
                return

        # 3. 在待执行指令 / 日志表里找
        for r in range(self.tbl_orders.rowCount()):
            c = self._extract_code_from_table(self.tbl_orders, r)
            if c == clean_code:
                self.tbl_orders.setCurrentCell(r, 0)
                it = self.tbl_orders.item(r, 0)
                if it:
                    self.tbl_orders.scrollToItem(it)
                self._trigger_linkage_for_table_row(self.tbl_orders, r, force=True)
                return

    def _on_exec_all_clicked(self):
        count = self.trading_center.execute_all_pending_directives()
        if count > 0:
            QMessageBox.information(self, "执行成功", f"成功执行 {count} 条集中交易决议！已更新持仓与资金账户。")
        else:
            QMessageBox.information(self, "提示", "当前没有待执行的交易指令。")
        self.refresh_data()

    def refresh_data(self):
        """刷新指挥室全部战情数据 (支持角色中文映射、双模式切换与数值精确排序)"""
        summary = self.trading_center.get_fleet_summary()
        self.lbl_capital.setText(f"💰 总资金: {summary['total_capital']/10000:.1f}万 | 可用: {summary['available_cash']/10000:.1f}万")
        self.lbl_positions.setText(f"📊 持仓: {summary['holding_count']} 只 ({summary['fleet_weight_pct']}%仓)")
        self.lbl_leader.setText(f"🥇 爆款领头羊: {summary['top_leader_name']} ({summary['top_leader_score']}分)")
        # 同步存储龙头代码，供点击联动使用
        self._top_leader_code = summary.get("top_leader", "")

        # 同步全仓轮动勾选状态
        if hasattr(self, "chk_rotation"):
            self.chk_rotation.blockSignals(True)
            self.chk_rotation.setChecked(self.trading_center.enable_full_rotation)
            self.chk_rotation.blockSignals(False)

        # ── 1. 刷新赛马天梯 (角色中文映射 + 支持点击表头数值排序) ──
        hv_rank = self.tbl_rank.horizontalHeader()
        sort_col_rank = hv_rank.sortIndicatorSection() if hv_rank.isSortIndicatorShown() else -1
        sort_order_rank = hv_rank.sortIndicatorOrder() if hv_rank.isSortIndicatorShown() else Qt.SortOrder.AscendingOrder

        ranked = getattr(self.trading_center, "_ranked_cache", [])
        # 【防刷新光标润动修复】用当前选中行的代码来恢复选中，而不是行号，避免排序后行号失效导致光标乱跳
        prev_code = ""
        prev_row = self.tbl_rank.currentRow()
        if prev_row >= 0:
            prev_code = self._extract_code_from_table(self.tbl_rank, prev_row)

        manual_set = set()
        if hasattr(self, "detector_dialog") and self.detector_dialog and hasattr(self.detector_dialog, "manual_codes"):
            manual_set = set(self.detector_dialog.manual_codes)

        self.tbl_rank.setSortingEnabled(False)
        self.tbl_rank.setRowCount(len(ranked))
        for r, sig in enumerate(ranked):
            is_manual = (sig.code in manual_set)
            # 排名 (数值排序)
            self.tbl_rank.setItem(r, 0, NumericTableWidgetItem(str(sig.horse_race_rank), raw_val=int(sig.horse_race_rank)))
            # 代码 (纯数字数值比较，手工标的金色加粗高亮)
            clean_digits = "".join(ch for ch in sig.code if ch.isdigit())
            code_num = int(clean_digits) if clean_digits else 999999
            code_it = NumericTableWidgetItem(sig.code, raw_val=code_num)
            if is_manual:
                code_it.setForeground(QColor("#ffd700"))
                f = code_it.font()
                f.setBold(True)
                code_it.setFont(f)
                code_it.setToolTip(f"【📌 操盘手手工添加标的】{sig.code} {sig.name}")
            self.tbl_rank.setItem(r, 1, code_it)
            # 名称 (标记显示在 name 上，专属 📌 标记与金色高亮)
            name_it = QTableWidgetItem(f"📌 {sig.name}" if is_manual else sig.name)
            if is_manual:
                name_it.setForeground(QColor("#ffd700"))
                f = name_it.font()
                f.setBold(True)
                name_it.setFont(f)
                name_it.setToolTip(f"【📌 操盘手手工添加标的】{sig.code} {sig.name} (置顶优先监控)")
            self.tbl_rank.setItem(r, 2, name_it)
            # 现价 (高精度浮点数排序)
            price_val = float(sig.price) if sig.price > 0 else 0.0
            self.tbl_rank.setItem(r, 3, NumericTableWidgetItem(f"{sig.price:.2f}" if sig.price > 0 else "--", raw_val=price_val))
            # 动能分 (数值排序)
            self.tbl_rank.setItem(r, 4, NumericTableWidgetItem(f"{sig.horse_race_score:.0f}", raw_val=float(sig.horse_race_score)))
            # 启动时点 (时间文本排序)
            self.tbl_rank.setItem(r, 5, QTableWidgetItem(sig.launch_time_str or "--"))
            
            # 角色 (精准映射为标准中文)
            role_raw = sig.global_fleet_role or "--"
            role_cn = ROLE_CN_MAP.get(role_raw, role_raw)
            role_it = QTableWidgetItem(role_cn)
            if role_raw == "LEADER":
                role_it.setForeground(QColor("#ffaa00"))
            elif role_raw == "VANGUARD":
                role_it.setForeground(QColor("#00e5ff"))
            elif role_raw == "RESONANCE_BUY":
                role_it.setForeground(QColor("#00ff88"))
            elif role_raw == "BASE_PREORDER":
                role_it.setForeground(QColor("#00e5ff"))
            elif role_raw == "SWING_PREORDER":
                role_it.setForeground(QColor("#00e5ff"))
            elif role_raw == "STOP_LOSS":
                role_it.setForeground(QColor("#ff4444"))
            elif role_raw == "PANIC_DEFENSE":
                role_it.setForeground(QColor("#ff7733"))
            elif role_raw == "CLIMAX_EXIT":
                role_it.setForeground(QColor("#ff3333"))
            elif role_raw == "CLIMAX_DEFENSE":
                role_it.setForeground(QColor("#ffaa33"))
            elif role_raw == "FOLLOWER":
                role_it.setForeground(QColor("#8f93a8"))
            self.tbl_rank.setItem(r, 6, role_it)

            # 决议依据
            desc_str = sig.global_arbitration_desc or sig.signal_desc
            desc_it = QTableWidgetItem(desc_str)
            if "领头羊" in desc_str or "首发吸筹" in desc_str or "共振加速" in desc_str or "筑底预埋" in desc_str or "通道突破" in desc_str:
                desc_it.setForeground(QColor("#00ff88"))
            elif "买错" in desc_str or "平仓" in desc_str or "止损" in desc_str:
                desc_it.setForeground(QColor("#ff5555"))
            elif "山外有山" in desc_str:
                desc_it.setForeground(QColor("#8f93a8"))
            elif "全局避险" in desc_str:
                desc_it.setForeground(QColor("#ff7733"))
            self.tbl_rank.setItem(r, 7, desc_it)

        self.tbl_rank.setSortingEnabled(True)
        if sort_col_rank >= 0:
            self.tbl_rank.sortItems(sort_col_rank, sort_order_rank)

        # 【防刷新光标润动】刷新后断开信号再恢复选中，防止数据刷新撤销用户的浏览选中
        self.tbl_rank.blockSignals(True)
        if prev_code:
            # 按代码重新定位选中行（排序后行号可能变）
            for r in range(self.tbl_rank.rowCount()):
                if self._extract_code_from_table(self.tbl_rank, r) == prev_code:
                    self.tbl_rank.setCurrentCell(r, 0)
                    break
        elif not self.tbl_rank.selectedItems() and 0 <= prev_row < self.tbl_rank.rowCount():
            self.tbl_rank.setCurrentCell(prev_row, 0)
        self.tbl_rank.blockSignals(False)

        # ── 2. 刷新实盘持仓组合或历史平仓战绩 ──
        holdings = summary.get("holding_details", [])
        closed_positions = self.trading_center.get_closed_positions()
        self._current_closed_positions_list = list(reversed(closed_positions))

        self.btn_pos_active.setText(f"🟢 活跃持仓 ({len(holdings)})")
        self.btn_pos_closed.setText(f"📜 历史平仓战绩 ({len(self._current_closed_positions_list)})")

        # 智能避免空白：若当前无活跃持仓但有历史战绩，且用户未主动切换，自适应切换展示历史战绩
        if len(holdings) == 0 and len(self._current_closed_positions_list) > 0 and self._pos_view_mode == "ACTIVE" and not getattr(self, "_user_selected_pos_mode", False):
            self._set_pos_view_mode("CLOSED")
            self._user_selected_pos_mode = False  # 保持自适应标记
            return

        hv_pos = self.tbl_pos.horizontalHeader()
        sort_col_pos = hv_pos.sortIndicatorSection() if hv_pos.isSortIndicatorShown() else -1
        sort_order_pos = hv_pos.sortIndicatorOrder() if hv_pos.isSortIndicatorShown() else Qt.SortOrder.AscendingOrder

        self.tbl_pos.setSortingEnabled(False)
        if self._pos_view_mode == "ACTIVE":
            self.tbl_pos.setRowCount(len(holdings))
            for r, pos in enumerate(holdings):
                code_num = int(pos["code"]) if pos["code"].isdigit() else 999999
                self.tbl_pos.setItem(r, 0, NumericTableWidgetItem(pos["code"], raw_val=code_num))
                self.tbl_pos.setItem(r, 1, QTableWidgetItem(pos["name"]))
                self.tbl_pos.setItem(r, 2, NumericTableWidgetItem(str(pos["shares"]), raw_val=int(pos["shares"])))
                self.tbl_pos.setItem(r, 3, NumericTableWidgetItem(f"{pos['cost']:.2f}", raw_val=float(pos['cost'])))
                self.tbl_pos.setItem(r, 4, NumericTableWidgetItem(f"{pos['now']:.2f}", raw_val=float(pos['now'])))
                
                pnl_val = float(pos['pnl_pct'])
                pnl_it = NumericTableWidgetItem(f"{pnl_val:+.2f}%", raw_val=pnl_val)
                pnl_it.setForeground(QColor("#ff4444") if pnl_val > 0 else QColor("#00ff88"))
                self.tbl_pos.setItem(r, 5, pnl_it)
                
                status_raw = pos["status"]
                status_cn = POS_STATUS_CN_MAP.get(status_raw, status_raw)
                self.tbl_pos.setItem(r, 6, QTableWidgetItem(status_cn))
        else:
            # 历史平仓战绩模式
            self.tbl_pos.setRowCount(len(self._current_closed_positions_list))
            for r, c_pos in enumerate(self._current_closed_positions_list):
                c_code = c_pos.get("code", "")
                code_num = int(c_code) if c_code.isdigit() else 999999
                self.tbl_pos.setItem(r, 0, NumericTableWidgetItem(c_code, raw_val=code_num))
                self.tbl_pos.setItem(r, 1, QTableWidgetItem(c_pos.get("name", "--")))
                self.tbl_pos.setItem(r, 2, QTableWidgetItem(c_pos.get("exit_date", "--")))
                cost_p = float(c_pos.get("cost_price", 0.0))
                exit_p = float(c_pos.get("exit_price", 0.0))
                self.tbl_pos.setItem(r, 3, NumericTableWidgetItem(f"{cost_p:.2f}", raw_val=cost_p))
                self.tbl_pos.setItem(r, 4, NumericTableWidgetItem(f"{exit_p:.2f}", raw_val=exit_p))
                
                realized_pnl = float(c_pos.get("realized_pnl_pct", 0.0))
                pnl_it = NumericTableWidgetItem(f"{realized_pnl:+.2f}%", raw_val=realized_pnl)
                pnl_it.setForeground(QColor("#ff4444") if realized_pnl > 0 else QColor("#00ff88"))
                self.tbl_pos.setItem(r, 5, pnl_it)
                self.tbl_pos.setItem(r, 6, QTableWidgetItem(c_pos.get("exit_reason", "--")))

        self.tbl_pos.setSortingEnabled(True)
        if sort_col_pos >= 0:
            self.tbl_pos.sortItems(sort_col_pos, sort_order_pos)

        # ── 3. 刷新待执行指令清单或历史信号日志 ──
        directives = self.trading_center.get_pending_directives()
        signal_logs = self.trading_center.get_signal_iteration_log()
        self._current_signal_logs_list = list(reversed(signal_logs))

        self.btn_orders_pending.setText(f"⏳ 待执行指令 ({len(directives)})")
        self.btn_orders_history.setText(f"📋 历史信号日志 ({len(self._current_signal_logs_list)})")

        hv_orders = self.tbl_orders.horizontalHeader()
        sort_col_orders = hv_orders.sortIndicatorSection() if hv_orders.isSortIndicatorShown() else -1
        sort_order_orders = hv_orders.sortIndicatorOrder() if hv_orders.isSortIndicatorShown() else Qt.SortOrder.AscendingOrder

        self.tbl_orders.setSortingEnabled(False)
        if self._orders_view_mode == "PENDING":
            self.tbl_orders.setRowCount(len(directives))
            for r, d in enumerate(directives):
                act_str = d.action
                plan = getattr(d, "trade_plan", None)
                if plan and getattr(plan, "suggested_action", ""):
                    act_str = plan.suggested_action
                act_it = QTableWidgetItem(act_str)
                if act_str in ("BUY", "BUY_CONFIRM", "FULL_ROTATION_SWAP"):
                    act_it.setForeground(QColor("#00ff88"))
                elif act_str in ("BUY_SCOUT",):
                    act_it.setForeground(QColor("#00e5ff"))
                elif act_str in ("SELL", "EXIT_ALL", "SWITCH_SWAP"):
                    act_it.setForeground(QColor("#ff5555"))
                self.tbl_orders.setItem(r, 0, act_it)
                code_num = int(d.code) if d.code.isdigit() else 999999
                self.tbl_orders.setItem(r, 1, NumericTableWidgetItem(d.code, raw_val=code_num))
                self.tbl_orders.setItem(r, 2, QTableWidgetItem(d.name))
                self.tbl_orders.setItem(r, 3, NumericTableWidgetItem(f"{d.price:.2f}", raw_val=float(d.price)))
                self.tbl_orders.setItem(r, 4, NumericTableWidgetItem(f"{d.size_pct:.0f}%", raw_val=float(d.size_pct)))

                reason_disp = d.reason
                if plan:
                    qg = getattr(d, "quality_grade", "") or "S"
                    reason_disp = f"[{qg}级 {plan.strategy_tag}] 网格:{plan.buy_zone_lower:.2f}~{plan.buy_zone_upper:.2f} 止损:{plan.higher_low_stop:.2f} | {d.reason}"
                it_reason = QTableWidgetItem(reason_disp)
                if plan:
                    it_reason.setToolTip(
                        f"【TradePlan 不可变交易计划】\n"
                        f"• 建议动作: {act_str}\n"
                        f"• 触发价: {plan.trigger_price:.2f}元\n"
                        f"• 买入网格: {plan.buy_zone_lower:.2f} ~ {plan.buy_zone_upper:.2f}元\n"
                        f"• 抬高底防守止损: {plan.higher_low_stop:.2f}元\n"
                        f"• 大底失效作废: {plan.base_low_invalid:.2f}元\n"
                        f"• 目标1(中轨): {plan.target_1_channel_mid:.2f}元 | 目标2: {plan.target_2_breakout_high:.2f}元\n"
                        f"----------------------------------------\n"
                        f"{d.reason}"
                    )
                self.tbl_orders.setItem(r, 5, it_reason)
        else:
            # 历史信号日志模式
            self.tbl_orders.setRowCount(len(self._current_signal_logs_list))
            for r, s_log in enumerate(self._current_signal_logs_list):
                # 优先用 time_str（可读时间字符串），如不存在再尝试转换 timestamp float
                ts_str = s_log.get("time_str", "")
                if not ts_str:
                    ts_raw = s_log.get("timestamp", "")
                    try:
                        import time as _time
                        ts_str = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(float(ts_raw)))
                    except Exception:
                        ts_str = str(ts_raw)
                if " " in ts_str:
                    ts_str = ts_str.split(" ", 1)[1]  # 仅保留时分秒更紧凑
                self.tbl_orders.setItem(r, 0, QTableWidgetItem(ts_str))
                tier_str = s_log.get("signal_tier", "S")
                tier_it = QTableWidgetItem(tier_str)
                if "SSS" in tier_str:
                    tier_it.setForeground(QColor("#ffd700"))
                elif "S" in tier_str:
                    tier_it.setForeground(QColor("#00ff88"))
                elif "A" in tier_str:
                    tier_it.setForeground(QColor("#00e5ff"))
                else:
                    tier_it.setForeground(QColor("#ff5555"))
                self.tbl_orders.setItem(r, 1, tier_it)

                act_it = QTableWidgetItem(s_log.get("action", "--"))
                if s_log.get("action") in ("BUY", "FULL_ROTATION_SWAP"):
                    act_it.setForeground(QColor("#00ff88"))
                elif s_log.get("action") in ("SELL", "STOP_LOSS"):
                    act_it.setForeground(QColor("#ff5555"))
                self.tbl_orders.setItem(r, 2, act_it)

                s_code = s_log.get("code", "")
                code_num = int(s_code) if s_code.isdigit() else 999999
                self.tbl_orders.setItem(r, 3, NumericTableWidgetItem(s_code, raw_val=code_num))
                self.tbl_orders.setItem(r, 4, QTableWidgetItem(s_log.get("name", "--")))
                self.tbl_orders.setItem(r, 5, QTableWidgetItem(s_log.get("reason", "--")))

        self.tbl_orders.setSortingEnabled(True)
        if sort_col_orders >= 0:
            self.tbl_orders.sortItems(sort_col_orders, sort_order_orders)

    def eventFilter(self, obj, event):
        """【领头羊标签点击联动】拦截 lbl_leader 鼠标点击，定位龙头股并联动通达信"""
        if obj is getattr(self, "lbl_leader", None):
            if event.type() == QEvent.Type.MouseButtonPress:
                code = getattr(self, "_top_leader_code", "")
                if code and code != "--":
                    # 直接利用现有联动机制：在赛马天梯表中定位该股并触发联动
                    self._last_linkage_code = ""  # 清除防抖去重，强制执行
                    self._pending_code = code
                    self._linkage_timer.start(10)
                    # 同时在赛马天梯表中定位高亮
                    for r in range(self.tbl_rank.rowCount()):
                        if self._extract_code_from_table(self.tbl_rank, r) == code:
                            self.tbl_rank.blockSignals(True)
                            self.tbl_rank.setCurrentCell(r, 0)
                            self.tbl_rank.scrollToItem(self.tbl_rank.item(r, 0))
                            self.tbl_rank.blockSignals(False)
                            break
                return True
        return super().eventFilter(obj, event)

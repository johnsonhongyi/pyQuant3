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
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QAction, QKeySequence

from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOOrderDirective, IPOTradingPosition
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal
from ats.ui.styles import (
    setup_header_persistence, auto_fit_columns_once,
    load_config_node, save_config_node, save_config_nodes
)

logger = logging.getLogger("IPOCommandRoomDialog")


class IPOCommandRoomTableWidget(QTableWidget):
    """
    【指挥室高响应专用表格】
    - 原生拦截 Up / Down / PageUp / PageDown，切行时防抖联动主检测工具与外部通达信；
    - 支持 Space (空格) 调出 SBC 走势图；
    - 支持 F 键 / 回车联动通达信；
    - 接入全系统统一标准的列宽自由拖拽与跨会话自动持久化体系 (setup_persistence)；
    - 支持一键自适应列宽与一键恢复默认列宽。
    """
    def __init__(self, parent_cmd_room=None):
        super().__init__(parent_cmd_room)
        self.cmd_room = parent_cmd_room
        self.setMouseTracking(True)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._config_key: Optional[str] = None
        self._default_widths: Optional[List[int]] = None

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
                background-color: #0e0f17;
                color: #ffffff;
            }
            QLabel {
                color: #e2e2e5;
                font-size: 9pt;
            }
            QGroupBox {
                border: 1px solid #282a3a;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #00e5ff;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #1e202f;
                border: 1px solid #3d4158;
                border-radius: 4px;
                color: #ffffff;
                font-size: 9pt;
                padding: 5px 14px;
            }
            QPushButton:hover {
                background-color: #2b2e44;
                border-color: #00e5ff;
            }
            QTableWidget {
                background-color: #12141f;
                border: 1px solid #232636;
                gridline-color: #1a1c29;
                color: #ffffff;
                font-size: 8.5pt;
                selection-background-color: #26334d;
            }
            QHeaderView::section {
                background-color: #181a29;
                color: #8f93a8;
                border: none;
                border-bottom: 1px solid #2a2d40;
                padding: 4px 6px;
                font-weight: bold;
            }
        """)

        self.trading_center = IPOTradingCenter.get_instance()
        self._last_linkage_code = ""

        # 联动防抖定时器 (20ms)
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._pending_code = ""
        self._linkage_timer.timeout.connect(self._fire_debounced_linkage)

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
        top_bar.addWidget(self.lbl_leader)

        top_bar.addStretch()

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
        self.splitter.setHandleWidth(4)

        # 左侧：全池赛马天梯与山外有山仲裁
        grp_rank = QGroupBox("🏆 全池横向赛马排位天梯 (掌握全数据·山外有山)")
        v_rank = QVBoxLayout(grp_rank)
        v_rank.setContentsMargins(6, 6, 6, 6)

        self.tbl_rank = IPOCommandRoomTableWidget(self)
        self.tbl_rank.setColumnCount(8)
        self.tbl_rank.setHorizontalHeaderLabels(["排名", "代码", "名称", "现价", "动能分", "启动时点", "角色", "集中仲裁与山外有山决议"])
        self.tbl_rank.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rank.horizontalHeader().setStretchLastSection(True)
        self.tbl_rank.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_rank.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_rank.verticalHeader().setVisible(False)
        self._bind_table_interactions(self.tbl_rank)
        # 接入持久化与精心调校的默认列宽 (动能分 70px, 启动时点 78px 彻底杜绝文字截断)
        self.tbl_rank.setup_persistence(
            "ipo_cmd_rank_table_header_v1",
            default_widths=[45, 58, 78, 58, 70, 78, 85, 280]
        )
        v_rank.addWidget(self.tbl_rank)
        self.splitter.addWidget(grp_rank)

        # 右侧：持仓组合与待执行指令
        right_panel = QWidget()
        v_right = QVBoxLayout(right_panel)
        v_right.setContentsMargins(0, 0, 0, 0)
        v_right.setSpacing(6)

        # 右上方：持仓组合
        grp_pos = QGroupBox("💼 舰队实盘持仓组合 (买错跌破 VWAP 0.6% 立即出局斩仓)")
        v_pos = QVBoxLayout(grp_pos)
        v_pos.setContentsMargins(6, 6, 6, 6)

        self.tbl_pos = IPOCommandRoomTableWidget(self)
        self.tbl_pos.setColumnCount(7)
        self.tbl_pos.setHorizontalHeaderLabels(["代码", "名称", "股数", "成本价", "现价", "浮盈%", "状态"])
        self.tbl_pos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_pos.horizontalHeader().setStretchLastSection(True)
        self.tbl_pos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_pos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_pos.verticalHeader().setVisible(False)
        self._bind_table_interactions(self.tbl_pos)
        self.tbl_pos.setup_persistence(
            "ipo_cmd_pos_table_header_v1",
            default_widths=[58, 78, 60, 62, 62, 68, 85]
        )
        v_pos.addWidget(self.tbl_pos)
        v_right.addWidget(grp_pos, 2)

        # 右下方：待执行指令清单
        grp_orders = QGroupBox("📋 集中交易调度待执行指令清单 (弃弱换马 / 领头羊进击 / 买错立斩)")
        v_orders = QVBoxLayout(grp_orders)
        v_orders.setContentsMargins(6, 6, 6, 6)

        self.tbl_orders = IPOCommandRoomTableWidget(self)
        self.tbl_orders.setColumnCount(6)
        self.tbl_orders.setHorizontalHeaderLabels(["动作", "代码", "标的", "价格", "建议仓位", "决议依据理由"])
        self.tbl_orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_orders.horizontalHeader().setStretchLastSection(True)
        self.tbl_orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_orders.verticalHeader().setVisible(False)
        self._bind_table_interactions(self.tbl_orders)
        self.tbl_orders.setup_persistence(
            "ipo_cmd_orders_table_header_v1",
            default_widths=[75, 58, 78, 60, 70, 240]
        )
        v_orders.addWidget(self.tbl_orders)
        v_right.addWidget(grp_orders, 3)

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
        table.cellDoubleClicked.connect(lambda r, c: self._on_table_double_clicked(table, r))

    def _extract_code_from_table(self, table: QTableWidget, row: int) -> str:
        """从表格行中智能提取 6 位股票代码"""
        if row < 0 or row >= table.rowCount():
            return ""
        # 寻找包含 6 位连续数字的单元格 (通常在第 0 或第 1 列)
        for c in (1, 0, 2):
            it = table.item(row, c)
            if it and it.text().strip():
                clean = "".join(ch for ch in it.text().strip() if ch.isdigit()).zfill(6)
                if len(clean) == 6:
                    return clean
        return ""

    def _extract_name_from_table(self, table: QTableWidget, row: int) -> str:
        """从表格行中智能提取股票名称"""
        if row < 0 or row >= table.rowCount():
            return ""
        for c in (2, 1):
            it = table.item(row, c)
            if it and it.text().strip():
                txt = it.text().strip()
                if not txt.isdigit():
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

    def _on_table_double_clicked(self, table: QTableWidget, row: int):
        """双击行：秒级调出 SBC 10d VWAP 走势图"""
        code = self._extract_code_from_table(table, row)
        if code:
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

    def _on_exec_all_clicked(self):
        count = self.trading_center.execute_all_pending_directives()
        if count > 0:
            QMessageBox.information(self, "执行成功", f"成功执行 {count} 条集中交易决议！已更新持仓与资金账户。")
        else:
            QMessageBox.information(self, "提示", "当前没有待执行的交易指令。")
        self.refresh_data()

    def refresh_data(self):
        """刷新指挥室全部战情数据"""
        summary = self.trading_center.get_fleet_summary()
        self.lbl_capital.setText(f"💰 总资金: {summary['total_capital']/10000:.1f}万 | 可用: {summary['available_cash']/10000:.1f}万")
        self.lbl_positions.setText(f"📊 持仓: {summary['holding_count']} 只 ({summary['fleet_weight_pct']}%仓)")
        self.lbl_leader.setText(f"🥇 爆款领头羊: {summary['top_leader_name']} ({summary['top_leader_score']}分)")

        # 1. 刷新赛马天梯 (平滑更新，记住当前选中)
        ranked = getattr(self.trading_center, "_ranked_cache", [])
        prev_row = self.tbl_rank.currentRow()
        self.tbl_rank.setRowCount(len(ranked))
        for r, sig in enumerate(ranked):
            self.tbl_rank.setItem(r, 0, QTableWidgetItem(str(sig.horse_race_rank)))
            self.tbl_rank.setItem(r, 1, QTableWidgetItem(sig.code))
            self.tbl_rank.setItem(r, 2, QTableWidgetItem(sig.name))
            self.tbl_rank.setItem(r, 3, QTableWidgetItem(f"{sig.price:.2f}" if sig.price > 0 else "--"))
            self.tbl_rank.setItem(r, 4, QTableWidgetItem(f"{sig.horse_race_score:.0f}"))
            self.tbl_rank.setItem(r, 5, QTableWidgetItem(sig.launch_time_str or "--"))
            
            role_it = QTableWidgetItem(sig.global_fleet_role or "--")
            if sig.global_fleet_role == "LEADER":
                role_it.setForeground(QColor("#ffaa00"))
            elif sig.global_fleet_role == "VANGUARD":
                role_it.setForeground(QColor("#00e5ff"))
            elif sig.global_fleet_role == "STOP_LOSS":
                role_it.setForeground(QColor("#ff4444"))
            elif sig.global_fleet_role == "PANIC_DEFENSE":
                role_it.setForeground(QColor("#ff7733"))
            self.tbl_rank.setItem(r, 6, role_it)

            desc_str = sig.global_arbitration_desc or sig.signal_desc
            desc_it = QTableWidgetItem(desc_str)
            if "领头羊" in desc_str or "首发吸筹" in desc_str:
                desc_it.setForeground(QColor("#00ff88"))
            elif "买错" in desc_str or "平仓" in desc_str:
                desc_it.setForeground(QColor("#ff5555"))
            elif "山外有山" in desc_str:
                desc_it.setForeground(QColor("#8f93a8"))
            elif "全局避险" in desc_str:
                desc_it.setForeground(QColor("#ff7733"))
            self.tbl_rank.setItem(r, 7, desc_it)

        if 0 <= prev_row < self.tbl_rank.rowCount() and not self.tbl_rank.selectedItems():
            self.tbl_rank.setCurrentCell(prev_row, 0)

        # 2. 刷新持仓组合
        holdings = summary.get("holding_details", [])
        self.tbl_pos.setRowCount(len(holdings))
        for r, pos in enumerate(holdings):
            self.tbl_pos.setItem(r, 0, QTableWidgetItem(pos["code"]))
            self.tbl_pos.setItem(r, 1, QTableWidgetItem(pos["name"]))
            self.tbl_pos.setItem(r, 2, QTableWidgetItem(str(pos["shares"])))
            self.tbl_pos.setItem(r, 3, QTableWidgetItem(f"{pos['cost']:.2f}"))
            self.tbl_pos.setItem(r, 4, QTableWidgetItem(f"{pos['now']:.2f}"))
            
            pnl_it = QTableWidgetItem(f"{pos['pnl_pct']:+.2f}%")
            pnl_it.setForeground(QColor("#ff4444") if pos['pnl_pct'] > 0 else QColor("#00ff88"))
            self.tbl_pos.setItem(r, 5, pnl_it)
            self.tbl_pos.setItem(r, 6, QTableWidgetItem(pos["status"]))

        # 3. 刷新待执行指令
        directives = self.trading_center.get_pending_directives()
        self.tbl_orders.setRowCount(len(directives))
        for r, d in enumerate(directives):
            act_it = QTableWidgetItem(d.action)
            if d.action == "BUY":
                act_it.setForeground(QColor("#00ff88"))
            elif d.action in ("SELL", "SWITCH_SWAP"):
                act_it.setForeground(QColor("#ff5555"))
            self.tbl_orders.setItem(r, 0, act_it)
            self.tbl_orders.setItem(r, 1, QTableWidgetItem(d.code))
            self.tbl_orders.setItem(r, 2, QTableWidgetItem(d.name))
            self.tbl_orders.setItem(r, 3, QTableWidgetItem(f"{d.price:.2f}"))
            self.tbl_orders.setItem(r, 4, QTableWidgetItem(f"{d.size_pct:.0f}%"))
            self.tbl_orders.setItem(r, 5, QTableWidgetItem(d.reason))

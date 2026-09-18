# -*- coding: utf-8 -*-
"""
ats/ui/ipo_command_room_dialog.py
-----------------------------------
新股次新股集中交易指挥室 (IPO Fleet Command Room Dialog)
核心功能：
1. 掌握全数据：展示全池守护标的赛马排位天梯与“山外有山”仲裁；
2. 持续交易总指挥：持仓盈亏追踪、最大回撤风控、账户资金调度；
3. 执行闭环：待执行订单清单呈现、一键批量执行决议、全自动跟随交易开关。
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
    QMessageBox, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOOrderDirective, IPOTradingPosition
from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal

logger = logging.getLogger("IPOCommandRoomDialog")


class IPOCommandRoomDialog(QDialog):
    """新股次新股集中交易总指挥室弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚢 新股次新集中交易指挥室 (山外有山·全局统筹调度中心)")
        self.setMinimumSize(1060, 640)
        self.resize(1120, 700)
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
        self._init_ui()
        self.refresh_data()

        # 1.5秒定时刷新
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
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # 左侧：全池赛马天梯与山外有山仲裁
        grp_rank = QGroupBox("🏆 全池横向赛马排位天梯 (掌握全数据·山外有山)")
        v_rank = QVBoxLayout(grp_rank)
        v_rank.setContentsMargins(6, 6, 6, 6)

        self.tbl_rank = QTableWidget()
        self.tbl_rank.setColumnCount(8)
        self.tbl_rank.setHorizontalHeaderLabels(["排名", "代码", "名称", "现价", "动能分", "启动时点", "角色", "集中仲裁与山外有山决议"])
        self.tbl_rank.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rank.horizontalHeader().setStretchLastSection(True)
        self.tbl_rank.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_rank.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_rank.verticalHeader().setVisible(False)
        self.tbl_rank.setColumnWidth(0, 45)
        self.tbl_rank.setColumnWidth(1, 55)
        self.tbl_rank.setColumnWidth(2, 75)
        self.tbl_rank.setColumnWidth(3, 55)
        self.tbl_rank.setColumnWidth(4, 55)
        self.tbl_rank.setColumnWidth(5, 65)
        self.tbl_rank.setColumnWidth(6, 65)
        v_rank.addWidget(self.tbl_rank)
        splitter.addWidget(grp_rank)

        # 右侧：持仓组合与待执行指令
        right_panel = QWidget()
        v_right = QVBoxLayout(right_panel)
        v_right.setContentsMargins(0, 0, 0, 0)
        v_right.setSpacing(6)

        # 右上方：持仓组合
        grp_pos = QGroupBox("💼 舰队实盘持仓组合 (买错跌破 VWAP 0.6% 立即出局斩仓)")
        v_pos = QVBoxLayout(grp_pos)
        v_pos.setContentsMargins(6, 6, 6, 6)

        self.tbl_pos = QTableWidget()
        self.tbl_pos.setColumnCount(7)
        self.tbl_pos.setHorizontalHeaderLabels(["代码", "名称", "股数", "成本价", "现价", "浮盈%", "状态"])
        self.tbl_pos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_pos.horizontalHeader().setStretchLastSection(True)
        self.tbl_pos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_pos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_pos.verticalHeader().setVisible(False)
        self.tbl_pos.setColumnWidth(0, 55)
        self.tbl_pos.setColumnWidth(1, 75)
        self.tbl_pos.setColumnWidth(2, 55)
        self.tbl_pos.setColumnWidth(3, 60)
        self.tbl_pos.setColumnWidth(4, 60)
        self.tbl_pos.setColumnWidth(5, 60)
        v_pos.addWidget(self.tbl_pos)
        v_right.addWidget(grp_pos, 2)

        # 右下方：待执行指令清单
        grp_orders = QGroupBox("📋 集中交易调度待执行指令清单 (弃弱换马 / 领头羊进击 / 买错立斩)")
        v_orders = QVBoxLayout(grp_orders)
        v_orders.setContentsMargins(6, 6, 6, 6)

        self.tbl_orders = QTableWidget()
        self.tbl_orders.setColumnCount(6)
        self.tbl_orders.setHorizontalHeaderLabels(["动作", "代码", "标的", "价格", "建议仓位", "决议依据理由"])
        self.tbl_orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_orders.horizontalHeader().setStretchLastSection(True)
        self.tbl_orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_orders.verticalHeader().setVisible(False)
        self.tbl_orders.setColumnWidth(0, 75)
        self.tbl_orders.setColumnWidth(1, 55)
        self.tbl_orders.setColumnWidth(2, 75)
        self.tbl_orders.setColumnWidth(3, 55)
        self.tbl_orders.setColumnWidth(4, 65)
        v_orders.addWidget(self.tbl_orders)
        v_right.addWidget(grp_orders, 3)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 3)
        root_layout.addWidget(splitter)

        # ── 3. 底部操作栏 ──
        bottom_bar = QHBoxLayout()
        lbl_tip = QLabel("💡 集中交易铁律: 资金有限只重仓领头羊 | 山外有山杜绝盲目跟风 | 买错破 VWAP 0.6% 坚决出局斩仓 | 极端高潮清仓锁定暴利")
        lbl_tip.setStyleSheet("color: #8f93a8; font-size: 8.5pt;")
        bottom_bar.addWidget(lbl_tip)
        bottom_bar.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)
        root_layout.addLayout(bottom_bar)

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

        # 1. 刷新赛马天梯
        ranked = getattr(self.trading_center, "_ranked_cache", [])
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
            self.tbl_rank.setItem(r, 6, role_it)

            desc_str = sig.global_arbitration_desc or sig.signal_desc
            desc_it = QTableWidgetItem(desc_str)
            if "领头羊" in desc_str or "首发吸筹" in desc_str:
                desc_it.setForeground(QColor("#00ff88"))
            elif "买错" in desc_str or "平仓" in desc_str:
                desc_it.setForeground(QColor("#ff5555"))
            elif "山外有山" in desc_str:
                desc_it.setForeground(QColor("#8f93a8"))
            self.tbl_rank.setItem(r, 7, desc_it)

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

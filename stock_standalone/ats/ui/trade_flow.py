# -*- coding: utf-8 -*-
"""
ATS Trade Flow, Position, and Backtest Panel Widgets
Contains widgets for:
- TradeFlowTable: Historical and live order/execution logs.
- PositionPanel: Active holdings and portfolio allocation.
- BacktestReportPanel: Backtest statistics and performance cards.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QGridLayout, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN

class TradeFlowTable(QWidget):
    """
    Table widget displaying transaction histories and orders.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_flow()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "时间", "代码", "名称", "方向", "成交价", "成交数量", "成交金额", "策略来源"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

    def load_mock_flow(self):
        # time, code, name, action, price, qty, amount, strategy
        mock_data = [
            ("09:31:05", "300750", "宁德时代", "买入", "185.50", "800", "148,400", "早盘低开拉升突破"),
            ("09:35:12", "600111", "北方稀土", "买入", "19.25", "5,000", "96,250", "大级别支撑企稳"),
            ("10:15:30", "000001", "平安银行", "卖出", "10.45", "10,000", "104,500", "破位均线保护离场"),
            ("14:45:00", "600030", "中信证券", "买入", "20.15", "5,000", "100,750", "板块异动共振买入")
        ]
        self.update_flow_list(mock_data)

    def update_flow_list(self, flow_list):
        self.table.setRowCount(0)
        self.table.setRowCount(len(flow_list))
        for row, data in enumerate(flow_list):
            for col, text in enumerate(data):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                if col == 3: # Action (Buy/Sell)
                    if "买" in str(text) or "BUY" in str(text) or "ADD" in str(text):
                        item.setForeground(QColor(COLOR_UP))
                        font = self.table.font()
                        font.setBold(True)
                        item.setFont(font)
                    else:
                        item.setForeground(QColor(COLOR_DOWN))
                        font = self.table.font()
                        font.setBold(True)
                        item.setFont(font)
                
                self.table.setItem(row, col, item)


class PositionPanel(QWidget):
    """
    Panel displaying active holdings, cash, and total assets.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_positions()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Portfolio Summary Header
        self.summary_widget = QWidget()
        self.summary_widget.setStyleSheet("background-color: #1a1a24; border: 1px solid #2e2e36; border-radius: 6px;")
        summary_layout = QHBoxLayout(self.summary_widget)
        summary_layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_total_assets = QLabel("总资产: 1,000,000.00")
        self.lbl_total_assets.setStyleSheet("font-weight: bold; font-size: 13pt; color: #ffffff;")
        self.lbl_total_assets.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_cash = QLabel("可用资金: 1,000,000.00")
        self.lbl_cash.setStyleSheet("font-weight: bold; font-size: 12pt; color: #aad4ff;")
        
        self.lbl_pnl = QLabel("总盈亏: +0.00 (+0.00%)")
        self.lbl_pnl.setStyleSheet("font-weight: bold; font-size: 12pt; color: #e2e2e5;")

        summary_layout.addWidget(self.lbl_total_assets)
        summary_layout.addSpacing(30)
        summary_layout.addWidget(self.lbl_cash)
        summary_layout.addSpacing(30)
        summary_layout.addWidget(self.lbl_pnl)
        summary_layout.addStretch()
        
        layout.addWidget(self.summary_widget)

        # Holdings Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "持仓股数", "成本价", "当前价", "市值", "盈亏比例", "占仓比"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

    def load_mock_positions(self):
        # code, name, qty, cost, price, market_val, pnl, alloc
        mock_data = [
            ("600030", "中信证券", "5,000", "20.15", "20.25", "101,250", "+0.50%", "10.0%"),
            ("300750", "宁德时代", "800", "185.50", "189.20", "151,360", "+2.00%", "15.0%"),
        ]
        self.update_positions(mock_data, cash=747390.0, total_assets=1000000.0)

    def update_positions(self, positions_list, cash=1000000.0, total_assets=1000000.0):
        self.lbl_total_assets.setText(f"总资产: {total_assets:,.2f}")
        self.lbl_cash.setText(f"可用资金: {cash:,.2f}")
        
        daily_pnl = total_assets - 1000000.0
        pct = (daily_pnl / 1000000.0) * 100
        if daily_pnl > 0:
            self.lbl_pnl.setText(f"总盈亏: +{daily_pnl:,.2f} (+{pct:.2f}%)")
            self.lbl_pnl.setStyleSheet("font-weight: bold; font-size: 12pt; color: #ff4444;")
        elif daily_pnl < 0:
            self.lbl_pnl.setText(f"总盈亏: -{abs(daily_pnl):,.2f} ({pct:.2f}%)")
            self.lbl_pnl.setStyleSheet("font-weight: bold; font-size: 12pt; color: #33cc5a;")
        else:
            self.lbl_pnl.setText(f"总盈亏: +0.00 (0.00%)")
            self.lbl_pnl.setStyleSheet("font-weight: bold; font-size: 12pt; color: #e2e2e5;")

        self.table.setRowCount(0)
        self.table.setRowCount(len(positions_list))
        for row, data in enumerate(positions_list):
            for col, text in enumerate(data):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                if col == 6: # PnL
                    if str(text).startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    else:
                        item.setForeground(QColor(COLOR_DOWN))
                elif col == 7: # Allocation
                    item.setFont(self._get_bold_font())
                    item.setForeground(QColor(COLOR_INFO))
                    
                self.table.setItem(row, col, item)

    def _get_bold_font(self):
        font = self.table.font()
        font.setBold(True)
        return font


class BacktestReportPanel(QWidget):
    """
    Panel providing backtesting run options and detailed analytical reports.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value_labels = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Control Row
        control_row = QHBoxLayout()
        self.btn_run_backtest = QPushButton("🚀 执行历史信号回测 (Run Backtest)")
        self.btn_run_backtest.setStyleSheet("background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 6px 15px;")
        control_row.addWidget(self.btn_run_backtest)
        
        self.lbl_status = QLabel("状态: 准备就绪 (24x7 自动回测模块已加载)")
        self.lbl_status.setStyleSheet("color: #aad4ff; font-style: italic;")
        control_row.addWidget(self.lbl_status)
        control_row.addStretch()
        layout.addLayout(control_row)

        # Statistics Cards Layout
        stats_layout = QGridLayout()
        stats_layout.setSpacing(10)

        # Stat cards definition
        cards_def = {
            "总交易次数": ("Total Trades", "420", "#ffffff"),
            "策略胜率": ("Win Rate", "62.4%", COLOR_UP),
            "平均盈利/亏损": ("Profit Factor", "1.82", COLOR_ACCENT),
            "最大回撤": ("Max Drawdown", "-5.2%", COLOR_DOWN),
            "凯利建议仓位": ("Kelly Allocation", "15.0%", COLOR_INFO),
            "持有期衰减": ("Decay Half-life", "4 天", COLOR_WARN),
        }

        for idx, (title, (label, val, color)) in enumerate(cards_def.items()):
            row = idx // 3
            col = idx % 3

            card = QWidget()
            card.setStyleSheet("background-color: #1a1a24; border: 1px solid #2e2e36; border-radius: 6px;")
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(10, 10, 10, 10)
            
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #8e8e93; font-size: 10pt;")
            
            lbl_val = QLabel(val)
            lbl_val.setStyleSheet(f"font-weight: bold; font-size: 18pt; color: {color};")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.value_labels[title] = lbl_val
            
            lbl_subtitle = QLabel(label)
            lbl_subtitle.setStyleSheet("color: #55555e; font-size: 8pt;")
            lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignRight)

            card_lay.addWidget(lbl_title)
            card_lay.addWidget(lbl_val)
            card_lay.addWidget(lbl_subtitle)
            
            stats_layout.addWidget(card, row, col)

        layout.addLayout(stats_layout)
        
        # Bottom Tip
        tip = QLabel("💡 提示: 自治回测引擎在后台读取历史 HDF5 分时数据库对信号进行多周期测算，只用于生成策略盈亏报告，不自动修改实盘参数。")
        tip.setStyleSheet("color: #8e8e93; font-style: italic; font-size: 9pt;")
        layout.addWidget(tip)

    def update_stats(self, stats_dict):
        for key, val in stats_dict.items():
            if key in self.value_labels:
                self.value_labels[key].setText(str(val))

# -*- coding: utf-8 -*-
"""
ATS Trade Flow, Position, and Backtest Panel Widgets
Contains widgets for:
- TradeFlowTable: Historical and live order/execution logs.
- PositionPanel: Active holdings and portfolio allocation.
- BacktestReportPanel: Backtest statistics and performance cards.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QLabel, QGridLayout,
    QPushButton, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN, auto_fit_columns_once, NumericTableWidgetItem
from ats.ui.base_table import BaseATSTableWidget

class TradeFlowTable(QWidget):
    """
    Table widget displaying transaction histories and orders with pagination and real-time PnL tracking.
    """
    stock_clicked = pyqtSignal(str, str) # code, name (for linkage)
    stock_double_clicked = pyqtSignal(str, str, dict) # code, name, context_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_flow_list = []
        self._current_page = 1
        self._page_size = 100
        self._init_ui()
        self.load_mock_flow()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # 1. 交易流水表格 (9列，包含距今涨跌)
        self.table = BaseATSTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "时间", "代码", "名称", "方向", "成交价", "成交数量", "成交金额", "距今涨跌", "策略来源"
        ])
        self.table.setup_persistence(
            config_key="ats_trade_flow_table_state_v2",
            default_widths=[95, 80, 90, 75, 85, 85, 95, 95, 220],
            max_widths={8: 350}
        )
        self.table.setAlternatingRowColors(True)
        self.table.stock_activated.connect(self.stock_clicked.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table, 1)

        # 2. 分页控制工具栏 (默认 100 条/页)
        self.pagination_widget = QWidget()
        self.pagination_widget.setStyleSheet("""
            QWidget {
                background-color: #14141d;
                border: 1px solid #232330;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #1f1f2e;
                color: #e0e0e0;
                border: 1px solid #333348;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #2b2b40;
                color: #38bdf8;
                border-color: #38bdf8;
            }
            QPushButton:disabled {
                background-color: #161620;
                color: #555566;
                border-color: #222230;
            }
            QComboBox, QSpinBox {
                background-color: #1a1a26;
                color: #38bdf8;
                border: 1px solid #333348;
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 8.5pt;
            }
            QLabel {
                border: none;
                background: transparent;
                color: #a0a0b8;
                font-size: 8.5pt;
            }
        """)
        pag_layout = QHBoxLayout(self.pagination_widget)
        pag_layout.setContentsMargins(8, 3, 8, 3)
        pag_layout.setSpacing(6)

        self.btn_first = QPushButton("⏮ 首页")
        self.btn_first.clicked.connect(self._go_first_page)
        pag_layout.addWidget(self.btn_first)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.clicked.connect(self._go_prev_page)
        pag_layout.addWidget(self.btn_prev)

        self.lbl_page_info = QLabel("第 1 / 1 页 (共 0 条)")
        self.lbl_page_info.setStyleSheet("font-weight: bold; color: #ffd700;")
        pag_layout.addWidget(self.lbl_page_info)

        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.clicked.connect(self._go_next_page)
        pag_layout.addWidget(self.btn_next)

        self.btn_last = QPushButton("末页 ⏭")
        self.btn_last.clicked.connect(self._go_last_page)
        pag_layout.addWidget(self.btn_last)

        pag_layout.addSpacing(10)

        # 每页条数下拉框
        lbl_size = QLabel("每页显示:")
        pag_layout.addWidget(lbl_size)
        self.combo_page_size = QComboBox()
        self.combo_page_size.addItems(["50 条/页", "100 条/页 (默认)", "200 条/页", "500 条/页", "全部显示"])
        self.combo_page_size.setCurrentIndex(1) # 默认 100 条
        self.combo_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        pag_layout.addWidget(self.combo_page_size)

        pag_layout.addSpacing(10)

        # 快速跳页
        lbl_jump = QLabel("跳转至:")
        pag_layout.addWidget(lbl_jump)
        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.setValue(1)
        pag_layout.addWidget(self.spin_page)

        self.btn_go = QPushButton("GO")
        self.btn_go.clicked.connect(self._go_spin_page)
        pag_layout.addWidget(self.btn_go)

        pag_layout.addStretch()
        layout.addWidget(self.pagination_widget)

    def load_mock_flow(self):
        # time, code, name, action, price, qty, amount, since_pct, strategy
        mock_data = [
            ("09:31:05", "300750", "宁德时代", "买入", "185.50", "800", "148,400", "+2.50%", "早盘低开拉升突破"),
            ("09:35:12", "600111", "北方稀土", "买入", "19.25", "5,000", "96,250", "+1.20%", "大级别支撑企稳"),
            ("10:15:30", "000001", "平安银行", "卖出", "10.45", "10,000", "104,500", "-0.80%", "破位均线保护离场"),
            ("14:45:00", "600030", "中信证券", "买入", "20.15", "5,000", "100,750", "+0.65%", "板块异动共振买入")
        ]
        self.update_flow_list(mock_data)

    def update_flow_list(self, flow_list):
        """接收全量流水列表并重置/渲染分页视图"""
        self._all_flow_list = list(flow_list) if flow_list else []
        self._update_pagination_ui()
        self._render_current_page()

    def update_realtime_prices(self, current_df):
        """实时行情推送时原位更新当前页可见行的距今涨跌幅"""
        if current_df is None or current_df.empty:
            return
        self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 1)
            price_item = self.table.item(row, 4)
            pnl_item = self.table.item(row, 7)
            if not code_item or not price_item or not pnl_item:
                continue
            code = code_item.text().strip()
            if code in current_df.index:
                try:
                    trade_p = float(price_item.text().replace(',', ''))
                    if trade_p > 0:
                        row_cur = current_df.loc[code]
                        now_p = float(row_cur.get('trade', row_cur.get('close', 0.0)))
                        if now_p > 0:
                            diff_pct = ((now_p - trade_p) / trade_p) * 100
                            pnl_str = f"{diff_pct:+.2f}%"
                            pnl_item.setText(pnl_str)
                            if diff_pct > 0:
                                pnl_item.setForeground(QColor(COLOR_UP))
                            elif diff_pct < 0:
                                pnl_item.setForeground(QColor(COLOR_DOWN))
                            else:
                                pnl_item.setForeground(QColor("#a0a0b8"))
                except Exception:
                    pass
        self.table.setSortingEnabled(True)

    def _get_total_pages(self) -> int:
        if self._page_size <= 0 or not self._all_flow_list:
            return 1
        return max(1, (len(self._all_flow_list) + self._page_size - 1) // self._page_size)

    def _update_pagination_ui(self):
        total_pages = self._get_total_pages()
        total_count = len(self._all_flow_list)

        if self._current_page > total_pages:
            self._current_page = total_pages
        if self._current_page < 1:
            self._current_page = 1

        self.lbl_page_info.setText(f"第 {self._current_page} / {total_pages} 页 (共 {total_count:,} 条)")
        self.btn_first.setEnabled(self._current_page > 1)
        self.btn_prev.setEnabled(self._current_page > 1)
        self.btn_next.setEnabled(self._current_page < total_pages)
        self.btn_last.setEnabled(self._current_page < total_pages)

        self.spin_page.blockSignals(True)
        self.spin_page.setMaximum(total_pages)
        self.spin_page.setValue(self._current_page)
        self.spin_page.blockSignals(False)

    def _render_current_page(self):
        """渲染当前页切片数据到 QTableWidget"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if not self._all_flow_list:
            self.table.setSortingEnabled(True)
            return

        if self._page_size <= 0:
            page_data = self._all_flow_list
        else:
            start_idx = (self._current_page - 1) * self._page_size
            end_idx = start_idx + self._page_size
            page_data = self._all_flow_list[start_idx:end_idx]

        self.table.setRowCount(len(page_data))
        for row, data in enumerate(page_data):
            # 兼容 8 列或 9 列数据格式
            row_items = list(data)
            if len(row_items) == 8:
                # 插入默认距今涨跌幅占位
                row_items.insert(7, "+0.00%")

            for col, text in enumerate(row_items[:9]):
                item = NumericTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 3: # 方向 (买入/卖出)
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
                elif col == 7: # 距今涨跌
                    txt_str = str(text).strip()
                    if txt_str.startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    elif txt_str.startswith("-"):
                        item.setForeground(QColor(COLOR_DOWN))
                    else:
                        item.setForeground(QColor("#a0a0b8"))

                self.table.setItem(row, col, item)

        auto_fit_columns_once(self.table, "ats_trade_flow_table_state_v2", max_widths={8: 350})
        self.table.setSortingEnabled(True)

    def _go_first_page(self):
        if self._current_page != 1:
            self._current_page = 1
            self._update_pagination_ui()
            self._render_current_page()

    def _go_prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._update_pagination_ui()
            self._render_current_page()

    def _go_next_page(self):
        if self._current_page < self._get_total_pages():
            self._current_page += 1
            self._update_pagination_ui()
            self._render_current_page()

    def _go_last_page(self):
        total_p = self._get_total_pages()
        if self._current_page != total_p:
            self._current_page = total_p
            self._update_pagination_ui()
            self._render_current_page()

    def _go_spin_page(self):
        target = self.spin_page.value()
        if target != self._current_page and 1 <= target <= self._get_total_pages():
            self._current_page = target
            self._update_pagination_ui()
            self._render_current_page()

    def _on_page_size_changed(self, index):
        sizes = [50, 100, 200, 500, -1]
        if 0 <= index < len(sizes):
            self._page_size = sizes[index]
            self._current_page = 1
            self._update_pagination_ui()
            self._render_current_page()

    def _on_cell_double_clicked(self, row, col):
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and name_item:
            code = code_item.text()
            name = name_item.text()
            time_str = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
            action = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            price = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
            qty = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
            amount = self.table.item(row, 6).text() if self.table.item(row, 6) else ""
            pnl_since = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
            strategy = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            context_info = {
                'position': '交易流水 (Trade Flow)',
                'reason': f"触发策略: {strategy}",
                'status': f"成交流水: 于 {time_str} 执行【{action}】{qty}股 | 成交价: {price} | 成交总额: {amount}元 | 距今涨跌: {pnl_since}"
            }
            self.stock_double_clicked.emit(code, name, context_info)


class PositionPanel(QWidget):
    """
    Panel displaying active holdings, cash, and total assets.
    """
    stock_clicked = pyqtSignal(str, str) # code, name (for linkage)
    stock_double_clicked = pyqtSignal(str, str, dict) # code, name, context_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_positions()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Portfolio Summary Header
        self.summary_widget = QWidget()
        self.summary_widget.setStyleSheet("background-color: #1a1a24; border: 1px solid #2e2e36; border-radius: 6px;")
        summary_layout = QHBoxLayout(self.summary_widget)
        summary_layout.setContentsMargins(10, 5, 10, 5)
        
        self.lbl_total_assets = QLabel("总资产: 1,000,000.00")
        self.lbl_total_assets.setStyleSheet("font-weight: bold; font-size: 10pt; color: #ffffff;")
        self.lbl_total_assets.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.lbl_cash = QLabel("可用资金: 1,000,000.00")
        self.lbl_cash.setStyleSheet("font-weight: bold; font-size: 10pt; color: #aad4ff;")
        
        self.lbl_pnl = QLabel("总盈亏: +0.00 (+0.00%)")
        self.lbl_pnl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #e2e2e5;")

        summary_layout.addWidget(self.lbl_total_assets)
        summary_layout.addSpacing(10)
        summary_layout.addWidget(self.lbl_cash)
        summary_layout.addSpacing(10)
        summary_layout.addWidget(self.lbl_pnl)
        summary_layout.addStretch()
        
        layout.addWidget(self.summary_widget)

        # Holdings Table
        self.table = BaseATSTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "持仓股数", "成本价", "当前价", "市值", "盈亏比例", "占仓比"
        ])
        self.table.setup_persistence(
            config_key="ats_position_table_state",
            default_widths=[80, 90, 90, 90, 90, 100, 100, 80]
        )
        self.table.setAlternatingRowColors(True)
        self.table.stock_activated.connect(self.stock_clicked.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
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

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(positions_list))
        for row, data in enumerate(positions_list):
            for col, text in enumerate(data):
                item = NumericTableWidgetItem(str(text))
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
        auto_fit_columns_once(self.table, "ats_position_table_state")
        self.table.setSortingEnabled(True)

    def _get_bold_font(self):
        font = self.table.font()
        font.setBold(True)
        return font

    def _on_cell_double_clicked(self, row, col):
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item:
            code = code_item.text()
            name = name_item.text()
            qty = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            cost = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            price = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
            market_val = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
            pnl = self.table.item(row, 6).text() if self.table.item(row, 6) else ""
            alloc = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
            context_info = {
                'position': '当前持仓 (Holdings Panel)',
                'reason': f"实盘配置占仓比: {alloc}",
                'status': f"当前持仓: {qty} 股 | 成本价: {cost}元 | 当前价: {price}元 | 市值: {market_val}元 | 持仓盈亏: {pnl}"
            }
            self.stock_double_clicked.emit(code, name, context_info)


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

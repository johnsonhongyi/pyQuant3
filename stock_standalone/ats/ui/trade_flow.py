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
        self._sort_col = 0
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._init_ui()
        self.load_real_trades()

    def load_real_trades(self):
        """从 TradeGateway 与 SQLite (signal_strategy.db) 实时加载真实的交易与一键挂单流水"""
        try:
            from trade_gateway import TradeGateway, DB_FILE
            from db_utils import SQLiteConnectionManager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS mock_trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT, time TEXT, code TEXT, name TEXT, sector TEXT,
                    action TEXT, price REAL, shares INTEGER, amount REAL,
                    reason TEXT, strategy_tag TEXT, pnl_pct REAL DEFAULT 0.0,
                    is_simulated INTEGER DEFAULT 0
                )
            """)
            conn.commit()
            
            c.execute("""
                SELECT time, code, name, action, price, shares, amount, pnl_pct, strategy_tag, date
                FROM mock_trade_log
                ORDER BY id DESC
            """)
            rows = c.fetchall()
            c.close()

            if rows:
                self._all_flow_list = []
                for r in rows:
                    t_str = f"{r[9]} {r[0]}" if r[9] else r[0]
                    code_str = str(r[1]).zfill(6)
                    name_str = str(r[2])
                    action_str = "买入" if r[3] == "BUY" else ("卖出" if r[3] == "SELL" else str(r[3]))
                    p_val = float(r[4])
                    qty_val = int(r[5])
                    amt_val = float(r[6])
                    pnl_val = float(r[7]) if r[7] is not None else 0.0
                    pnl_str = f"{pnl_val:+.2f}%" if abs(pnl_val) > 0.001 else "0.00%"
                    strat_str = str(r[8]) if r[8] else "👑 空间真龙·一键挂单"
                    
                    self._all_flow_list.append([
                        t_str, code_str, name_str, action_str,
                        f"{p_val:.2f}", str(qty_val), f"{amt_val:.2f}",
                        pnl_str, strat_str
                    ])
            else:
                # 若暂无数据库流水，从 TradeGateway 内存获取
                gw_logs = TradeGateway.get_instance().get_today_log()
                if gw_logs:
                    self._all_flow_list = []
                    for item in reversed(gw_logs):
                        self._all_flow_list.append([
                            item.get('time', '--'),
                            str(item.get('code', '')).zfill(6),
                            item.get('name', '--'),
                            "买入" if item.get('action') == "BUY" else "卖出",
                            f"{float(item.get('price', 0)):.2f}",
                            str(item.get('shares', 0)),
                            f"{float(item.get('amount', 0)):.2f}",
                            f"{float(item.get('pnl_pct', 0)):+.2f}%",
                            item.get('reason', '👑 空间真龙·一键挂单')
                        ])
                else:
                    self.load_mock_flow()
        except Exception:
            self.load_mock_flow()

        self._sort_flow_list()
        self.table.horizontalHeader().setSortIndicator(self._sort_col, self._sort_order)
        self._update_pagination_ui()
        self._render_current_page()

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
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self.table, 1)

        # 键盘上下键防抖定时器 (60ms)
        from PyQt6.QtCore import QTimer
        self._link_timer = QTimer(self)
        self._link_timer.setSingleShot(True)
        self._link_timer.timeout.connect(self._do_broadcast_link)

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

    def _extract_sort_key(self, row, col):
        """提取行数据的排序键，支持时间、浮点数、整数、百分比和字符串自适应转换"""
        if not row or col >= len(row):
            return ""
        val = str(row[col]).strip()
        if not val or val in ("--", "nan", "None"):
            return -999999999.0 if col in (4, 5, 6, 7) else ""

        if col == 0:  # 时间/日期时间
            return val
        elif col in (4, 6):  # 成交价 / 成交金额
            try:
                return float(val.replace(',', '').replace('￥', ''))
            except ValueError:
                return 0.0
        elif col == 5:  # 成交数量
            try:
                return int(val.replace(',', ''))
            except ValueError:
                return 0
        elif col == 7:  # 距今涨跌幅 (+2.50%)
            try:
                return float(val.replace('%', '').replace('+', ''))
            except ValueError:
                return 0.0
        else:
            return val

    def _sort_flow_list(self):
        """对全量流水列表进行稳定原地排序"""
        if not self._all_flow_list:
            return
        reverse = (self._sort_order == Qt.SortOrder.DescendingOrder)
        self._all_flow_list.sort(key=lambda r: self._extract_sort_key(r, self._sort_col), reverse=reverse)

    def _on_header_clicked(self, col: int):
        """用户点击表头时切换排序方向并对全量流水重排"""
        if self._sort_col == col:
            self._sort_order = (
                Qt.SortOrder.AscendingOrder
                if self._sort_order == Qt.SortOrder.DescendingOrder
                else Qt.SortOrder.DescendingOrder
            )
        else:
            self._sort_col = col
            self._sort_order = Qt.SortOrder.DescendingOrder  # 新点击列默认降序

        self.table.horizontalHeader().setSortIndicator(self._sort_col, self._sort_order)
        self._sort_flow_list()
        self._render_current_page()

    def update_flow_list(self, flow_list):
        """接收全量流水列表并重置/渲染分页视图"""
        self._all_flow_list = list(flow_list) if flow_list else []
        self._sort_flow_list()
        self.table.horizontalHeader().setSortIndicator(self._sort_col, self._sort_order)
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

    def _on_cell_clicked(self, row, col):
        """鼠标单击单元格即时触发联动"""
        if row < 0 or row >= self.table.rowCount():
            return
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if not code_item:
            return
        code = code_item.text().strip().zfill(6)
        name = name_item.text().strip() if name_item else code
        self._pending_link = (code, name)
        self._do_broadcast_link()

    def _on_current_cell_changed(self, curr_row, curr_col, prev_row, prev_col):
        """键盘上下键 (↑ / ↓) 移动选定行时触发 60ms 防抖联动"""
        if curr_row < 0 or curr_row >= self.table.rowCount():
            return
        code_item = self.table.item(curr_row, 1)
        name_item = self.table.item(curr_row, 2)
        if not code_item:
            return
        code = code_item.text().strip().zfill(6)
        name = name_item.text().strip() if name_item else code
        self._pending_link = (code, name)
        self._link_timer.start(60)

    def _do_broadcast_link(self):
        """执行广播联动"""
        if not hasattr(self, '_pending_link') or not self._pending_link:
            return
        code, name = self._pending_link
        self.stock_clicked.emit(code, name)
        self._broadcast_link_stock(code, name)

    def _broadcast_link_stock(self, code: str, name: str = ""):
        """物理直连广播到通达信/同花顺与全局主窗口"""
        try:
            from linkage_service import get_link_manager
            if get_link_manager:
                get_link_manager().push(code, flags={'tdx': True, 'ths': True, 'dfcf': False})
        except Exception:
            pass
        try:
            from ats.ui.main_window import ATSMainWindow
            if hasattr(ATSMainWindow, '_instance') and ATSMainWindow._instance:
                ATSMainWindow._instance.link_stock(code, name)
        except Exception:
            pass

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
            self._broadcast_link_stock(code, name)


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


from PyQt6.QtWidgets import QDialog, QApplication

class TradeFlowDialog(QDialog):
    """
    今日交易流水与订单日志独立窗口 (Trade Flow Dialog)
    真正的独立顶层窗口，支持位置持久化、Esc 键关闭、表头点击排序与实时刷新。
    """
    def __init__(self, parent=None):
        # 强制设置为独立 Window，避免嵌入在父窗口中变成子控件
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle("📋 ATS 今日交易流水日志 (Trade Flow & Execution Logs)")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        from ats.ui.styles import apply_dark_theme
        apply_dark_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部工具栏
        top_bar = QHBoxLayout()
        lbl_title = QLabel("⚡ 今日实盘/模拟一键挂单与委托流水明细 (点击表头可多字段排序)")
        lbl_title.setStyleSheet("font-size: 10pt; font-weight: bold; color: #00ffcc;")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()

        btn_refresh = QPushButton("🔄 刷新流水")
        btn_refresh.setStyleSheet("background-color: #1a2a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 4px 10px;")
        btn_refresh.clicked.connect(self.refresh_data)
        top_bar.addWidget(btn_refresh)

        btn_close = QPushButton("❌ 关闭")
        btn_close.setStyleSheet("background-color: #2a1a1a; color: #ff5555; font-weight: bold; border: 1px solid #ff5555; border-radius: 4px; padding: 4px 10px;")
        btn_close.clicked.connect(self.close)
        top_bar.addWidget(btn_close)

        layout.addLayout(top_bar)

        # 流水表格
        self.flow_table = TradeFlowTable(self)
        layout.addWidget(self.flow_table, 1)

        self._restore_geometry()

    def refresh_data(self):
        self.flow_table.load_real_trades()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        event.accept()

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    def _save_geometry(self):
        """持久化保存窗口位置与尺寸"""
        try:
            import json, os
            from sys_utils import get_app_root
            cfg_file = os.path.join(get_app_root(), "window_config.json")
            data = {}
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["trade_flow_geometry"] = {
                "x": self.x(), "y": self.y(),
                "w": self.width(), "h": self.height()
            }
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _restore_geometry(self):
        """恢复窗口位置与尺寸，并进行屏幕边界防护"""
        try:
            import json, os
            from sys_utils import get_app_root
            cfg_file = os.path.join(get_app_root(), "window_config.json")
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                geo = data.get("trade_flow_geometry")
                if geo and isinstance(geo, dict):
                    x = int(geo.get("x", 100))
                    y = int(geo.get("y", 100))
                    w = int(geo.get("w", 980))
                    h = int(geo.get("h", 560))
                    app = QApplication.instance()
                    if app:
                        screen = app.primaryScreen().geometry()
                        if 0 <= x < screen.width() - 50 and 0 <= y < screen.height() - 50:
                            self.setGeometry(x, y, max(600, w), max(350, h))
                            return
        except Exception:
            pass
        self.resize(980, 560)


_TRADE_FLOW_WIN = None
def open_trade_flow_dialog(parent=None):
    global _TRADE_FLOW_WIN
    if _TRADE_FLOW_WIN is None or not _TRADE_FLOW_WIN.isVisible():
        _TRADE_FLOW_WIN = TradeFlowDialog()
    _TRADE_FLOW_WIN.show()
    _TRADE_FLOW_WIN.raise_()
    _TRADE_FLOW_WIN.activateWindow()
    _TRADE_FLOW_WIN.refresh_data()
    return _TRADE_FLOW_WIN

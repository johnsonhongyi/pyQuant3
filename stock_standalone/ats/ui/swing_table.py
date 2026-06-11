# -*- coding: utf-8 -*-
"""
ATS Swing State Table Widget
Tracks the status of stocks in the MA20 pullback lifecycle.
Lifecycle stages: 回踩中 (Pulling back), 回踩企稳 (Pullback stabilized), 持股中 (Holding), 已平仓 (Closed).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHeaderView, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_WARN, COLOR_INFO, COLOR_ACCENT, auto_fit_columns_once, NumericTableWidgetItem
from ats.ui.base_table import BaseATSTableWidget

class SwingStateTable(QWidget):
    stock_clicked = pyqtSignal(str, str) # code, name (for linkage)
    stock_double_clicked = pyqtSignal(str, str, dict) # code, name, context_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel("📉 大级别 MA20d 回调跟踪器 (Swing Pullback Tracker)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 12pt;")
        header.addWidget(title)
        header.addStretch()
        
        btn_refresh = QPushButton("🔄 刷新状态")
        btn_refresh.clicked.connect(self.load_mock_data)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        # Table
        self.table = BaseATSTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "股票代码", "股票名称", "当前价格", "波段状态", "MA20 偏离度", "连板数", "推荐仓位", "推荐理由"
        ])
        
        # Table configuration using base widget's persistence
        self.table.setup_persistence(
            config_key="ats_swing_table_state",
            default_widths=[90, 100, 90, 110, 110, 90, 100, 250],
            max_widths={7: 350}
        )
        
        self.table.setAlternatingRowColors(True)
        self.table.stock_activated.connect(self.stock_clicked.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        layout.addWidget(self.table)

    def load_mock_data(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        # Mock data: code, name, price, state, ma20_dist, limit_ups, position, reason
        mock_data = [
            ("600519", "贵州茅台", "1650.00", "回踩中", "-0.85%", "0", "0%", "日线缩量向20日均线靠拢"),
            ("002415", "海康威视", "32.40", "回踩企稳", "+0.15%", "1", "15%", "MA20强支撑处出现十字星K线"),
            ("300750", "宁德时代", "185.50", "持股中", "+3.20%", "0", "20%", "回踩确认后阳线收回，多头排列"),
            ("600111", "北方稀土", "19.25", "持股中", "+4.85%", "2", "30%", "放量冲出平台，强势上涨波段"),
            ("000001", "平安银行", "10.45", "已平仓", "-1.50%", "0", "0%", "跌破20日均线离场信号触发"),
            ("002594", "比亚迪", "245.00", "回踩企稳", "+0.05%", "0", "10%", "前期大涨后回踩MA20量能极度萎缩")
        ]

        self.table.setRowCount(len(mock_data))
        for row_idx, row_data in enumerate(mock_data):
            for col_idx, text in enumerate(row_data):
                item = NumericTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Dynamic cell styling based on state/pct
                if col_idx == 3: # State column
                    if text == "回踩中":
                        item.setForeground(QColor(COLOR_WARN))
                    elif text == "回踩企稳":
                        item.setForeground(QColor(COLOR_INFO))
                        item.setFont(self._get_bold_font())
                    elif text == "持股中":
                        item.setForeground(QColor(COLOR_ACCENT))
                        item.setFont(self._get_bold_font())
                    elif text == "已平仓":
                        item.setForeground(QColor(COLOR_DOWN))
                
                elif col_idx == 4: # MA20 deviation
                    if text.startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    else:
                        item.setForeground(QColor(COLOR_DOWN))
 
                elif col_idx == 6: # Position
                    if text != "0%":
                        item.setForeground(QColor(COLOR_ACCENT))
                        item.setFont(self._get_bold_font())
                
                self.table.setItem(row_idx, col_idx, item)
        auto_fit_columns_once(self.table, "ats_swing_table_state", max_widths={7: 350})
        self.table.setSortingEnabled(True)

    def update_data_list(self, data_list):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(data_list))
        for row_idx, row_data in enumerate(data_list):
            for col_idx, text in enumerate(row_data):
                item = NumericTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Dynamic cell styling based on state/pct
                if col_idx == 3: # State column
                    if text == "回踩中":
                        item.setForeground(QColor(COLOR_WARN))
                    elif text == "回踩企稳":
                        item.setForeground(QColor(COLOR_INFO))
                        item.setFont(self._get_bold_font())
                    elif text == "持股中":
                        item.setForeground(QColor(COLOR_ACCENT))
                        item.setFont(self._get_bold_font())
                    elif text == "已平仓":
                        item.setForeground(QColor(COLOR_DOWN))
                
                elif col_idx == 4: # MA20 deviation
                    if str(text).startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    elif str(text).startswith("-"):
                        item.setForeground(QColor(COLOR_DOWN))

                elif col_idx == 6: # Position
                    if str(text) != "0%":
                        item.setForeground(QColor(COLOR_ACCENT))
                        item.setFont(self._get_bold_font())
                
                self.table.setItem(row_idx, col_idx, item)
        auto_fit_columns_once(self.table, "ats_swing_table_state", max_widths={7: 350})
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
            state = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            ma20_dist = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
            limit_ups = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
            pos = self.table.item(row, 6).text() if self.table.item(row, 6) else ""
            reason = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
            context_info = {
                'position': '波段回调跟踪器 (Swing Pullback Tracker)',
                'reason': reason,
                'status': f"MA20偏离: {ma20_dist} | 连板/新高天数: {limit_ups} | 推荐仓位: {pos} | 当前状态: {state}"
            }
            self.stock_double_clicked.emit(code, name, context_info)

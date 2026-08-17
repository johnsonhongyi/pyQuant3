# -*- coding: utf-8 -*-
"""
ATS Favorite Panel ("⭐ 重点关注" 专属 Tab 页面)
一键直达重点关注股票、最近强势标的及底层全量监控特征。

核心功能:
1. 阶段一 (冷启动/无 IPC 推送): 读取 GlobalFavoriteManager + 本地缓存，秒级展示基础关注清单。
2. 阶段二 (收到 IPC 实盘推送): 实时高密更新价格、涨幅、波段状态、MA20 偏离度、DFF、Rank 等底层监控列。
3. 提供双击图表联动、右键发送异动联动与关注管理。
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import datetime
import time

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, setup_header_persistence, NumericTableWidgetItem



def get_ats_extra_cols():
    """获取 ats_col 排除已有固定列后的自定义追加列"""
    try:
        from JohnsonUtil import commonTips as cct
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']
    
    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'trade', 'state', 'deviation', 
        'limit_ups', 'position', 'first_seen', 'priority', 'dff', 'rank', 
        'dff2', 'dff3', 'rs', 'resonance', 'reason'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_ats_table_headers(extra_cols=None):
    """组合 ATS 表格列名：前15列基础列 + 动态自定义列 + 最后一列推荐理由"""
    if extra_cols is None:
        extra_cols = get_ats_extra_cols()
    try:
        from JohnsonUtil import commonTips as cct
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
        
    base_pre = [
        "股票代码", "股票名称", "当前价格", "波段状态", "MA20 偏离度", "连板数", "推荐仓位", 
        "首次发现", "优先级", "DFF", "Rank", "DFF2", "DFF3", "大盘偏离", "大盘共振"
    ]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    base_post = ["推荐理由"]
    return base_pre + extra_headers + base_post


class FavoritePanel(QWidget):
    """⭐ 重点关注(基础重点) 专属看板页"""
    
    stock_selected = pyqtSignal(str, str, dict) # code, name, context_info
    dragon_monitor_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extra_cols = get_ats_extra_cols()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header bar
        header = QHBoxLayout()
        title = QLabel("⭐ 重点关注 (基础重点与底层监控)")
        title.setStyleSheet("font-weight: bold; color: #ffd700; font-size: 11pt;")
        header.addWidget(title)
        
        self.count_label = QLabel("共 0 只标的")
        self.count_label.setStyleSheet("color: #888888; font-size: 9pt;")
        header.addWidget(self.count_label)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("过滤重点代码/名称...")
        self.search_input.setMaximumWidth(160)
        self.search_input.setStyleSheet("background-color: #1a1a22; border: 1px solid #333; border-radius: 4px; padding: 2px 5px;")
        self.search_input.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_input)

        layout.addLayout(header)

        # BaseATSTableWidget
        self.table = BaseATSTableWidget(self)
        headers = get_ats_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        default_widths = [90, 100, 90, 110, 110, 90, 100, 110, 75, 60, 50, 60, 60, 75, 75] + [70] * len(self.extra_cols) + [250]
        self.table.setup_persistence(
            config_key="ats_swing_table_state_v2",
            default_widths=default_widths,
            max_widths={len(headers) - 1: 350}
        )

        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.table)

    def _on_double_clicked(self, item):
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip().replace("⭐ ", "") if name_item else ""
            self.stock_selected.emit(code, name, {})

    def _on_search_changed(self, text):
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            code_str = code_item.text().lower() if code_item else ""
            name_str = name_item.text().lower() if name_item else ""
            match = (not text) or (text in code_str) or (text in name_str)
            self.table.setRowHidden(row, not match)

    def update_favorite_rows(self, rows):
        """更新重点关注看板表格 (双缓冲平滑覆盖，杜绝更新前清空导致的闪烁/清0)
        
        Args:
            rows: list of tuples (code, name, price, state, deviation, limit_ups, position,
                                  first_seen, priority, dff, rank, dff2, dff3, rs, resonance, *extra_vals, reason)
        """
        if rows is None:
            return

        current_extra = get_ats_extra_cols()
        if not hasattr(self, 'extra_cols') or self.extra_cols != current_extra:
            self.extra_cols = current_extra
            headers = get_ats_table_headers(self.extra_cols)
            if self.table.columnCount() != len(headers):
                self.table.setColumnCount(len(headers))
                self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        sort_col = header.sortIndicatorSection() if (header and header.isSortIndicatorShown()) else -1
        sort_order = header.sortIndicatorOrder() if header else Qt.SortOrder.AscendingOrder

        self.table.setSortingEnabled(False)
        self.count_label.setText(f"共 {len(rows)} 只重点标的")

        if not rows:
            if self.table.rowCount() > 0:
                self.table.setRowCount(0)
            return

        def _parse_num_val(row_item, col_idx):
            if col_idx >= len(row_item):
                return 0.0
            val_str = str(row_item[col_idx]).strip()
            import re
            clean_str = val_str.replace(',', '').replace('%', '').replace('￥', '').replace('$', '')
            m = re.search(r'[-+]?\d*\.?\d+', clean_str)
            if m:
                try:
                    return float(m.group())
                except ValueError:
                    pass
            return 0.0

        sorted_rows = sorted(rows, key=lambda x: (-_parse_num_val(x, 8), _parse_num_val(x, 4), str(x[0]).strip()))

        if self.table.rowCount() != len(sorted_rows):
            self.table.setRowCount(len(sorted_rows))

        num_extra = len(self.extra_cols)
        total_cols = 16 + num_extra
        reason_col_idx = total_cols - 1

        for row_idx, row_data in enumerate(sorted_rows):
            code = str(row_data[0])
            name = str(row_data[1])
            price = str(row_data[2])
            state = str(row_data[3])
            dev_str = str(row_data[4])
            limit_ups = str(row_data[5])
            position = str(row_data[6])
            first_seen = str(row_data[7])
            priority = str(row_data[8])
            dff = str(row_data[9])
            rank = str(row_data[10])
            dff2 = str(row_data[11])
            dff3 = str(row_data[12])
            rs_val = str(row_data[13])
            resonance = str(row_data[14])
            
            # 动态列提取
            extra_vals = []
            if len(row_data) > 16:
                # 传入了动态列数据: 结构为 15基础 + N动态 + 1理由
                extra_vals = [str(row_data[15 + i]) for i in range(num_extra) if 15 + i < len(row_data) - 1]
            while len(extra_vals) < num_extra:
                extra_vals.append("--")
                
            reason = str(row_data[-1]) if len(row_data) > 15 else "重点关注追踪"

            display_name = f"⭐ {name}"
            col_values = [
                code, display_name, price, state, dev_str, limit_ups, position,
                first_seen, priority, dff, rank, dff2, dff3, rs_val, resonance,
                *extra_vals, reason
            ]

            for col_idx, val in enumerate(col_values):
                if col_idx >= self.table.columnCount():
                    break
                item = NumericTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx not in (1, reason_col_idx) else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

                # Highlight entire row for favorite
                item.setBackground(QColor("#1F2D1F"))

                # Standard color coding
                if col_idx == 0:
                    item.setForeground(QColor("#00FF88"))
                    item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif col_idx == 1:
                    item.setForeground(QColor("#FFD700"))
                    item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif col_idx == 3:  # 波段状态
                    if "企稳" in state or "买入" in state:
                        item.setForeground(QColor("#00FF88"))
                        item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                    elif "持股" in state:
                        item.setForeground(QColor("#00E5FF"))
                    elif "破位" in state or "弱" in state:
                        item.setForeground(QColor("#FF4444"))
                    else:
                        item.setForeground(QColor("#E2E2E5"))
                elif col_idx == 4:  # MA20 偏离
                    if dev_str.startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    elif dev_str.startswith("-"):
                        item.setForeground(QColor(COLOR_DOWN))
                elif col_idx == 8:  # 优先级
                    item.setForeground(QColor("#00FF88"))
                    item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif col_idx == 14:  # 逆势共振
                    if "逆市" in resonance or "共振" in resonance:
                        item.setForeground(QColor("#FFD700"))
                        item.setFont(QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
                elif 15 <= col_idx < 15 + num_extra:  # 动态自定义列
                    if str(val).startswith("+"):
                        item.setForeground(QColor(COLOR_UP))
                    elif str(val).startswith("-"):
                        item.setForeground(QColor(COLOR_DOWN))
                    else:
                        item.setForeground(QColor("#E2E2E5"))

                self.table.setItem(row_idx, col_idx, item)

        self.table.setSortingEnabled(True)
        if sort_col >= 0:
            self.table.sortItems(sort_col, sort_order)

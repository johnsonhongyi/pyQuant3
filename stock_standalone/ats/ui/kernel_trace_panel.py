# -*- coding: utf-8 -*-
"""
ATS Kernel Trace Log Viewer Panel
Displays real-time logs from logs/trading_kernel_trace.jsonl.
"""

import os
import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import NumericTableWidgetItem, COLOR_UP, COLOR_DOWN, COLOR_INFO, auto_fit_columns_once
from sys_utils import get_app_root

class KernelTracePanel(QWidget):
    """
    Panel displaying the live decision and signal trace from the trading kernel.
    """
    stock_clicked = pyqtSignal(str, str) # code, name (for linkage)
    stock_double_clicked = pyqtSignal(str, str, dict) # code, name, context_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_trace_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        self.table = BaseATSTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "时间", "代码", "名称", "信号类型", "内核决策", "置信度", "参考价", "状态", "决策依据"
        ])
        
        # persistence configuration
        self.table.setup_persistence(
            config_key="ats_kernel_trace_table_state",
            default_widths=[140, 70, 80, 110, 80, 80, 80, 70, 250],
            max_widths={8: 400}
        )
        self.table.setAlternatingRowColors(True)
        self.table.stock_activated.connect(self.stock_clicked.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

    def load_trace_logs(self):
        base = get_app_root()
        path = os.path.join(base, "logs", "trading_kernel_trace.jsonl")
        if not os.path.exists(path):
            return

        try:
            # Read all lines safely
            lines = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        lines.append(line.strip())
            
            # Show latest first
            lines.reverse()
            # Limit to 150 items for performance
            lines = lines[:150]

            rows_data = []
            for line in lines:
                try:
                    data = json.loads(line)
                    # 1. Parse time
                    timestamp = data.get("journal_ts") or data.get("timestamp") or ""
                    if "T" in timestamp:
                        timestamp = timestamp.replace("T", " ")
                    
                    # 2. Code & Name
                    signal_data = data.get("signal", {})
                    intent_data = data.get("intent", {})
                    code = signal_data.get("code") or intent_data.get("code") or ""
                    name = signal_data.get("name") or ""
                    
                    # 3. Signal Type
                    sig_type = signal_data.get("signal_type") or ""
                    
                    # 4. Kernel Action / Decision
                    kernel_result = data.get("kernel_result", {})
                    action = kernel_result.get("kernel_action") or intent_data.get("action") or "HOLD"
                    action_cn = "买入" if action == "BUY" else ("卖出" if action == "SELL" else "观察")
                    
                    # 5. Confidence
                    conf = kernel_result.get("kernel_confidence") or intent_data.get("confidence") or 0.0
                    conf_str = f"{conf:.2%}" if isinstance(conf, float) else str(conf)
                    
                    # 6. Price
                    price = signal_data.get("price") or intent_data.get("price") or 0.0
                    price_str = f"{price:.2f}" if price else "0.00"
                    
                    # 7. State
                    state = kernel_result.get("kernel_state") or data.get("trace", {}).get("state") or ""
                    
                    # 8. Reason
                    reason = signal_data.get("features", {}).get("raw_reason") or intent_data.get("reason", {}).get("raw_reason") or ""
                    if not reason and intent_data.get("reason"):
                        reason = str(intent_data.get("reason"))
                    
                    # 9. Context dict for double-click inspection
                    context = {
                        'position': '交易内核跟踪 (Kernel Trace)',
                        'reason': f"信号: {sig_type} | 触发依据: {reason}",
                        'status': f"内核决策: 【{action_cn}】 | 置信度: {conf_str} | 运行状态: {state}"
                    }
                    
                    rows_data.append((
                        timestamp, code, name, sig_type, action_cn, conf_str, price_str, state, reason, context
                    ))
                except Exception:
                    pass
                    
            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows_data))
            
            for row_idx, r in enumerate(rows_data):
                context_dict = r[-1]
                for col_idx in range(9):
                    val = r[col_idx]
                    item = NumericTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx != 8 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    item.setData(Qt.ItemDataRole.UserRole, context_dict)
                    
                    # Highlight actions
                    if col_idx == 4:
                        if "买" in val or "BUY" in val:
                            item.setForeground(QColor(COLOR_UP))
                            font = self.table.font()
                            font.setBold(True)
                            item.setFont(font)
                        elif "卖" in val or "SELL" in val:
                            item.setForeground(QColor(COLOR_DOWN))
                            font = self.table.font()
                            font.setBold(True)
                            item.setFont(font)
                    
                    self.table.setItem(row_idx, col_idx, item)
            
            auto_fit_columns_once(self.table, "ats_kernel_trace_table_state", max_widths={8: 400})
            self.table.setSortingEnabled(True)
        except Exception as e:
            print(f"[KernelTracePanel] Error loading trace logs: {e}")

    def _on_cell_double_clicked(self, row, col):
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and name_item:
            code = code_item.text()
            name = name_item.text()
            item = self.table.item(row, col)
            context_info = item.data(Qt.ItemDataRole.UserRole) if item else {}
            self.stock_double_clicked.emit(code, name, context_info)

# -*- coding: utf-8 -*-
"""
ATS Sector Detail Dialog
Displays all constituent stocks of a given sector from the bidding session data.
"""

import os
import json
import zlib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ats.ui.styles import NumericTableWidgetItem, setup_header_persistence
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct

class ATSSectorDetailDialog(QDialog):
    def __init__(self, sector_name, linkage_cb, double_click_cb=None, parent=None):
        super().__init__(parent)
        self.sector_name = sector_name
        self.linkage_cb = linkage_cb
        self.double_click_cb = double_click_cb
        
        self.setWindowTitle(f"🔥 {sector_name} 板块明细 (Real-time Sector Details)")
        self.resize(750, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #121214;
                color: #e2e2e5;
            }
            QTableWidget {
                background-color: #18181c;
                alternate-background-color: #1c1c22;
                color: #e2e2e5;
                gridline-color: #2e2e36;
                border: 1px solid #2e2e36;
            }
            QHeaderView::section {
                background-color: #1c1c22;
                color: #888899;
                font-weight: bold;
                border: 1px solid #2e2e36;
                padding: 2px 4px;
            }
            QTableWidget::item:selected {
                background-color: #2a3a4a;
                color: #00ff88;
            }
        """)
        self._init_ui()
        self.load_data()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Title block
        header = QHBoxLayout()
        self.title_lbl = QLabel(f"板块名称: {self.sector_name}")
        self.title_lbl.setStyleSheet("font-size: 13pt; font-weight: bold; color: #00ff88;")
        header.addWidget(self.title_lbl)
        header.addStretch()
        
        self.score_lbl = QLabel("强度得分: --")
        self.score_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ff9900;")
        header.addWidget(self.score_lbl)
        layout.addLayout(header)
        
        # Stats info
        self.stats_lbl = QLabel("成员数: 0 | 领涨股: --")
        self.stats_lbl.setStyleSheet("font-size: 10pt; color: #aad4ff;")
        layout.addWidget(self.stats_lbl)
        
        # Table of members
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "得分", "类型", "涨幅", "起点", "DFF", "形态提示"
        ])
        
        # Set headers left align and vertical center
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # Connect signals
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.currentItemChanged.connect(self.on_current_item_changed)
        
        layout.addWidget(self.table)
        
        # Close button block
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
    def load_data(self):
        # Fetch sector data from bidding_session_data
        path = None
        try:
            ram_path = cct.get_ramdisk_path("bidding_session_data.json.gz")
            if ram_path and os.path.exists(ram_path):
                path = ram_path
        except Exception:
            pass
            
        if not path:
            try:
                base = get_app_root()
                fallback_path = os.path.abspath(os.path.join(base, "snapshots", "bidding_session_data.json.gz"))
                if os.path.exists(fallback_path):
                    path = fallback_path
            except Exception:
                pass
                
        if not path or not os.path.exists(path):
            self.stats_lbl.setText("❌ 未找到实盘竞价会话数据")
            return
            
        try:
            with open(path, 'rb') as f:
                raw_data = f.read()
            json_str = zlib.decompress(raw_data).decode('utf-8')
            data = json.loads(json_str)
            sector_data = data.get('sector_data', {})
            sec_info = sector_data.get(self.sector_name)
            
            if not sec_info:
                self.stats_lbl.setText("❌ 当前板块暂无成分股明细特征")
                return
                
            # Resolve name using parent's get_stock_name if empty
            get_name_fn = None
            p = self.parent()
            while p:
                if hasattr(p, 'get_stock_name'):
                    get_name_fn = p.get_stock_name
                    break
                p = p.parent()

            score = sec_info.get('score', 0.0)
            self.score_lbl.setText(f"强度得分: {score:.1f}")
            
            leader_code = sec_info.get('leader', '')
            leader_name = sec_info.get('leader_name', '')
            if not leader_name and get_name_fn:
                leader_name = get_name_fn(leader_code)
            if not leader_name or leader_name == "未知":
                leader_name = sec_info.get('leader_name') or leader_code
                
            leader_pct = sec_info.get('leader_pct', 0.0)
            leader_dff = sec_info.get('leader_dff') or sec_info.get('leader_pct_diff') or 0.0
            leader_score = sec_info.get('leader_score', 0.0)
            
            followers = sec_info.get('followers', [])
            self.stats_lbl.setText(f"成员数: {len(followers) + (1 if leader_code else 0)} | 领涨龙头: {leader_name} ({leader_code})")
            
            # Combine leader and followers into rows list
            rows = []
            if leader_code:
                rows.append({
                    'code': leader_code,
                    'name': leader_name,
                    'score': leader_score,
                    'type': '👑 龙头',
                    'pct': leader_pct,
                    'start_pct': leader_pct - leader_dff,
                    'dff': leader_dff,
                    'pattern': '领涨先锋'
                })
                
            for fol in followers:
                f_code = fol.get('code')
                if f_code == leader_code:
                    continue
                f_name = fol.get('name', '')
                if not f_name and get_name_fn:
                    f_name = get_name_fn(f_code)
                if not f_name or f_name == "未知":
                    f_name = fol.get('name') or f_code
                f_pct = fol.get('pct', 0.0)
                f_dff = fol.get('dff') or fol.get('pct_diff') or 0.0
                rows.append({
                    'code': f_code,
                    'name': f_name,
                    'score': fol.get('score', 0.0),
                    'type': '跟涨',
                    'pct': f_pct,
                    'start_pct': f_pct - f_dff,
                    'dff': f_dff,
                    'pattern': fol.get('pattern_hint', '')
                })
                
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(rows))
            
            for row_idx, r in enumerate(rows):
                # 0. Code
                code_item = QTableWidgetItem(str(r['code']))
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 0, code_item)
                
                # 1. Name
                name_item = QTableWidgetItem(str(r['name']))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 1, name_item)
                
                # 2. Score
                score_item = NumericTableWidgetItem(f"{r['score']:.1f}")
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 2, score_item)
                
                # 3. Type
                type_item = QTableWidgetItem(str(r['type']))
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if '👑' in r['type']:
                    type_item.setForeground(QColor("#ffcc00")) # gold
                self.table.setItem(row_idx, 3, type_item)
                
                # 4. Pct
                pct_val = r['pct']
                pct_str = f"{pct_val:+.2f}%"
                pct_item = NumericTableWidgetItem(pct_str)
                pct_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if pct_val > 0.001:
                    pct_item.setForeground(QColor("#ff4444"))
                elif pct_val < -0.001:
                    pct_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 4, pct_item)
                
                # 5. Start Pct
                start_val = r['start_pct']
                start_str = f"{start_val:+.2f}%"
                start_item = NumericTableWidgetItem(start_str)
                start_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if start_val > 0.001:
                    start_item.setForeground(QColor("#ff4444"))
                elif start_val < -0.001:
                    start_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 5, start_item)
                
                # 6. DFF
                dff_val = r['dff']
                dff_str = f"{dff_val:+.2f}%"
                dff_item = NumericTableWidgetItem(dff_str)
                dff_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff_val > 0.001:
                    dff_item.setForeground(QColor("#ff4444"))
                elif dff_val < -0.001:
                    dff_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 6, dff_item)
                
                # 7. Pattern
                pat_item = QTableWidgetItem(str(r['pattern'] or '--'))
                pat_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 7, pat_item)
                
            self.table.setSortingEnabled(True)
            self.table.resizeColumnsToContents()
            
            # Setup columns minimum widths or interactive persistence
            setup_header_persistence(self.table, f"ats_sector_detail_table_{self.sector_name}")
            
        except Exception as e:
            print(f"Error loading sector detail rows: {e}")
            self.stats_lbl.setText(f"❌ 加载出错: {e}")
            
    def on_item_clicked(self, item):
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.linkage_cb:
            self.linkage_cb(code_item.text(), name_item.text())
            
    def on_current_item_changed(self, current, previous):
        if current and self.linkage_cb:
            row = current.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                self.linkage_cb(code_item.text(), name_item.text())
                
    def on_item_double_clicked(self, item):
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.double_click_cb:
            self.double_click_cb(code_item.text(), name_item.text())

    def closeEvent(self, event):
        # Save header state of the table
        if hasattr(self.table, 'save_column_widths'):
            try:
                self.table.save_column_widths()
            except Exception:
                pass
        super().closeEvent(event)

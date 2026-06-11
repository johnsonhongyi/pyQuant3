# -*- coding: utf-8 -*-
"""
ATS Sector Heatmap Widget
Provides a visual grid of sector momentum scores.
Colors range dynamically based on intensity of momentum.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QHBoxLayout, QPushButton, QComboBox, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import numpy as np

class SectorHeatmapWidget(QWidget):
    sector_selected = pyqtSignal(str) # sector name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_sectors()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header controls
        header = QHBoxLayout()
        title = QLabel("🔥 行业板块强度热力图 (Sector Momentum)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 12pt;")
        header.addWidget(title)
        header.addStretch()

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["按强度得分降序", "按涨跌幅降序", "按活跃成员数降序"])
        self.sort_combo.currentIndexChanged.connect(self.sort_sectors)
        header.addWidget(self.sort_combo)
        
        layout.addLayout(header)

        # Scroll Area for Heatmap Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #121214; border: 1px solid #2e2e36;")
        
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #121214;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(6)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

    def load_mock_sectors(self):
        # Name, Score (0-100), Change %, Active Count
        self.sectors = [
            ("半导体", 85.5, "+3.45%", 12),
            ("光伏设备", 72.3, "+2.10%", 8),
            ("国防军工", 68.0, "+1.85%", 6),
            ("计算机设备", 62.1, "+0.95%", 15),
            ("证券", 55.4, "+0.45%", 11),
            ("白酒", 48.2, "-0.20%", 5),
            ("医疗器械", 42.0, "-0.80%", 9),
            ("银行", 38.5, "-1.15%", 10),
            ("煤炭开采", 25.4, "-2.40%", 4),
            ("房地产开发", 18.0, "-3.20%", 7),
            ("通信设备", 75.0, "+2.80%", 9),
            ("中药", 50.0, "+0.00%", 8),
        ]
        self.render_grid()

    def get_color_for_score(self, pct_str):
        try:
            val = float(pct_str.replace("%", ""))
        except:
            val = 0.0
        
        # Color mapping:
        # High positive -> bright crimson red
        # Zero -> dark charcoal/grey
        # High negative -> bright cyber green
        if val > 0:
            intensity = min(int(val * 50), 180) # scale factor
            return f"background-color: rgb({70 + intensity}, 18, 28); border: 1px solid #ff4444;"
        elif val < 0:
            intensity = min(int(abs(val) * 50), 180)
            return f"background-color: rgb(12, {50 + intensity}, 28); border: 1px solid #33cc5a;"
        else:
            return "background-color: #222228; border: 1px solid #3e3e4a;"

    def render_grid(self):
        # Clear layout first
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)

        cols = 4  # 4 columns grid
        for idx, (name, score, pct, count) in enumerate(self.sectors):
            row = idx // cols
            col = idx % cols

            # Card Widget
            card = QPushButton()
            card.setMinimumSize(120, 80)
            
            # Label overlay
            style = self.get_color_for_score(pct)
            card.setStyleSheet(f"""
                QPushButton {{
                    {style}
                    border-radius: 6px;
                    color: white;
                    text-align: center;
                }}
                QPushButton:hover {{
                    border: 2.5px solid #ffffff;
                }}
            """)
            
            # Rich text formatting inside card (HTML is supported on QLabel, but for QPushButton we just set text or layouts)
            # We can use a layout inside the button or a custom widget. Let's place a layout inside card!
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 5, 5, 5)
            card_layout.setSpacing(2)
            
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-weight: bold; color: #ffffff; background: transparent; font-size: 11pt;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            info_lbl = QLabel(f"分: {score} | {pct}")
            info_lbl.setStyleSheet("color: #e2e2e5; background: transparent; font-size: 9pt;")
            info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            count_lbl = QLabel(f"活跃数: {count}")
            count_lbl.setStyleSheet("color: #aad4ff; background: transparent; font-size: 8pt; font-style: italic;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            card_layout.addWidget(name_lbl)
            card_layout.addWidget(info_lbl)
            card_layout.addWidget(count_lbl)
            
            # Connect action
            card.clicked.connect(lambda checked, n=name: self.sector_selected.emit(n))
            self.grid_layout.addWidget(card, row, col)

    def sort_sectors(self, index):
        if index == 0: # By score desc
            self.sectors.sort(key=lambda x: x[1], reverse=True)
        elif index == 1: # By percent desc
            self.sectors.sort(key=lambda x: float(x[2].replace("%", "")), reverse=True)
        elif index == 2: # By active count desc
            self.sectors.sort(key=lambda x: x[3], reverse=True)
        self.render_grid()

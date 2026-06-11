# -*- coding: utf-8 -*-
"""
ATS Universe Widget
Visualizes the multi-tier stock universe pools: Radar, Watchlist, and Trading.
Provides a tree structure with real-time mockup data.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO

class UniverseTreeWidget(QWidget):
    # Signal emitted when a stock is double clicked or clicked
    stock_selected = pyqtSignal(str, str) # code, name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.load_mock_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Title / Search Bar
        header_layout = QHBoxLayout()
        title_label = QLabel("🌌 策略股票池 (Multi-Tier Universe)")
        title_label.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 12pt;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索代码/名称...")
        self.search_input.setMaximumWidth(150)
        self.search_input.setStyleSheet("background-color: #1a1a22; border: 1px solid #333; border-radius: 4px; padding: 2px 5px;")
        self.search_input.textChanged.connect(self.filter_tree)
        header_layout.addWidget(self.search_input)
        layout.addLayout(header_layout)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["代码/名称", "最新价/涨幅", "筛选机制/持仓", "核心特征/追踪状态"])
        self.tree.setColumnCount(4)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 120)
        
        # Style header
        self.tree.header().setStretchLastSection(True)
        
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        layout.addWidget(self.tree)

    def load_mock_data(self):
        self.tree.clear()

        # 1. Radar Pool
        self.radar_root = QTreeWidgetItem(self.tree)
        self.radar_root.setText(0, "🌌 候选雷达池 (Radar Pool)")
        self.radar_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        
        radar_items = [
            ("600519", "贵州茅台", "1650.00", "+1.25%", "MA20强支撑", "回踩20日均线企稳中"),
            ("002415", "海康威视", "32.40", "+0.85%", "波段吸筹", "缩量小幅震荡企稳"),
            ("300059", "东方财富", "15.75", "-1.20%", "高频超买回落", "放量跌破均线观察中"),
            ("601318", "中国平安", "45.10", "+2.10%", "机构持仓异动", "拉升拉回布林中轨"),
            ("000333", "美的集团", "62.30", "-0.40%", "大消费弱回调", "缩量回踩布林下轨")
        ]
        
        for code, name, price, pct, strategy, desc in radar_items:
            item = QTreeWidgetItem(self.radar_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            # Apply color based on percent sign
            if pct.startswith("+"):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))

        # 2. Watchlist Pool
        self.watch_root = QTreeWidgetItem(self.tree)
        self.watch_root.setText(0, "📌 精选观察池 (Watchlist Pool)")
        self.watch_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole, "root")

        watch_items = [
            ("300750", "宁德时代", "185.50", "+3.80%", "MA20企稳突破", "黄金早盘爆量拉升"),
            ("600111", "北方稀土", "19.25", "+4.95%", "资源股复苏", "低开拉升冲破VWAP"),
            ("002594", "比亚迪", "245.00", "+2.50%", "新能源车风口", "日线收敛三角形突破")
        ]

        for code, name, price, pct, strategy, desc in watch_items:
            item = QTreeWidgetItem(self.watch_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if pct.startswith("+"):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))

        # 3. Trading Pool
        self.trade_root = QTreeWidgetItem(self.tree)
        self.trade_root.setText(0, "💰 实盘交易池 (Trading Pool)")
        self.trade_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole, "root")

        trade_items = [
            ("600030", "中信证券", "20.15", "+1.10%", "持仓中 (15%)", "基准+1.20% | 跟踪持股中"),
            ("000001", "平安银行", "10.45", "-0.95%", "持仓中 (10%)", "跌破VWAP警示 | 冷却防守")
        ]

        for code, name, price, pct, strategy, desc in trade_items:
            item = QTreeWidgetItem(self.trade_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if pct.startswith("+"):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))

        self.tree.expandAll()

    def update_pools(self, radar_list, watch_list, trade_list):
        self.tree.clear()

        # 1. Radar Pool
        self.radar_root = QTreeWidgetItem(self.tree)
        self.radar_root.setText(0, f"🌌 候选雷达池 (Radar Pool) ({len(radar_list)})")
        self.radar_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        for code, name, price, pct, strategy, desc in radar_list:
            item = QTreeWidgetItem(self.radar_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))

        # 2. Watchlist Pool
        self.watch_root = QTreeWidgetItem(self.tree)
        self.watch_root.setText(0, f"📌 精选观察池 (Watchlist Pool) ({len(watch_list)})")
        self.watch_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        for code, name, price, pct, strategy, desc in watch_list:
            item = QTreeWidgetItem(self.watch_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))

        # 3. Trading Pool
        self.trade_root = QTreeWidgetItem(self.tree)
        self.trade_root.setText(0, f"💰 实盘交易池 (Trading Pool) ({len(trade_list)})")
        self.trade_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        for code, name, price, pct, strategy, desc in trade_list:
            item = QTreeWidgetItem(self.trade_root)
            item.setText(0, f"{code} {name}")
            item.setText(1, f"{price} ({pct})")
            item.setText(2, strategy)
            item.setText(3, desc)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(1, QColor(COLOR_UP))
            else:
                item.setForeground(1, QColor(COLOR_DOWN))
        
        self.tree.expandAll()

    def _on_item_double_clicked(self, item, column):
        code = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.data(1, Qt.ItemDataRole.UserRole)
        if code and code != "root":
            self.stock_selected.emit(code, name)

    def filter_tree(self, text):
        # Simplistic filtering of items
        text = text.lower()
        if not text:
            # Show all
            for i in range(self.tree.topLevelItemCount()):
                root = self.tree.topLevelItem(i)
                root.setHidden(False)
                for j in range(root.childCount()):
                    root.child(j).setHidden(False)
            return

        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            root_visible = False
            for j in range(root.childCount()):
                child = root.child(j)
                txt = child.text(0).lower() + child.text(2).lower() + child.text(3).lower()
                if text in txt:
                    child.setHidden(False)
                    root_visible = True
                else:
                    child.setHidden(True)
            root.setHidden(not root_visible)

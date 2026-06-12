# -*- coding: utf-8 -*-
"""
ATS Universe Widget
Visualizes the multi-tier stock universe pools: Radar, Watchlist, and Trading.
Provides a tree structure with real-time mockup data.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, setup_header_persistence, auto_fit_columns_once

class UniverseTreeItem(QTreeWidgetItem):
    def __lt__(self, other):
        tree = self.treeWidget()
        if not tree:
            return super().__lt__(other)
            
        column = tree.sortColumn()
        
        # Determine if either is a root node
        is_self_root = self.parent() is None
        is_other_root = other.parent() is None
        
        if is_self_root or is_other_root:
            if is_self_root and is_other_root:
                w1 = self.data(0, Qt.ItemDataRole.UserRole + 1)
                w2 = other.data(0, Qt.ItemDataRole.UserRole + 1)
                w1 = w1 if w1 is not None else 0
                w2 = w2 if w2 is not None else 0
                
                # Keep root category nodes in static order: Radar (1) < Watchlist (2) < Trading (3)
                order = tree.header().sortIndicatorOrder()
                if order == Qt.SortOrder.DescendingOrder:
                    return w1 > w2
                else:
                    return w1 < w2
            return is_self_root
            
        # Compare child stock rows based on the selected column
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            c1 = self.data(0, Qt.ItemDataRole.UserRole)
            c2 = other.data(0, Qt.ItemDataRole.UserRole)
            is_fav1 = c1 in fav_mgr.get_favorite_stocks() if c1 else False
            is_fav2 = c2 in fav_mgr.get_favorite_stocks() if c2 else False
            
            if is_fav1 != is_fav2:
                order = tree.header().sortIndicatorOrder()
                if order == Qt.SortOrder.DescendingOrder:
                    return is_fav1 < is_fav2
                else:
                    return is_fav1 > is_fav2
        except Exception:
            pass
            
        t1 = self.text(column)
        t2 = other.text(column)
        
        import re
        
        # Helper to extract first float number
        def extract_float(s):
            match = re.search(r'[-+]?\d*\.?\d+', s)
            if match:
                try:
                    return float(match.group())
                except:
                    pass
            return None

        if column == 0:
            # Code sorting
            try:
                v1 = int(t1.strip())
                v2 = int(t2.strip())
                return v1 < v2
            except:
                return t1 < t2
        elif column == 1:
            # Name sorting
            return t1 < t2
        elif column == 2:
            # Price sorting
            v1 = extract_float(t1)
            v2 = extract_float(t2)
            if v1 is not None and v2 is not None:
                return v1 < v2
            return t1 < t2
        elif column == 3:
            # Percent sorting
            v1 = extract_float(t1)
            v2 = extract_float(t2)
            if v1 is not None and v2 is not None:
                return v1 < v2
            return t1 < t2
        elif column == 4:
            # Description / Status sorting
            return t1 < t2
        elif column == 5:
            # Strategy / Position sorting: check for percentage e.g. "(15%)"
            pos_re = r'\((\d+)%\)'
            p1_match = re.search(pos_re, t1)
            p2_match = re.search(pos_re, t2)
            p1_val = float(p1_match.group(1)) if p1_match else None
            p2_val = float(p2_match.group(1)) if p2_match else None
            if p1_val is not None and p2_val is not None:
                return p1_val < p2_val
            elif p1_val is not None:
                return True
            elif p2_val is not None:
                return False
            return t1 < t2
        else:
            return t1 < t2


class UniverseTreeWidget(QWidget):
    # Signal emitted when a stock is double clicked or clicked
    stock_selected = pyqtSignal(str, str, dict) # code, name, context_info
    stock_clicked = pyqtSignal(str, str)        # code, name (for linkage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_mock_active = False
        self._init_ui()
        self.load_mock_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Title / Search Bar
        header_layout = QHBoxLayout()
        title_label = QLabel("策略股票池 (Multi-Tier Universe)")
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
        self.tree.setHeaderLabels(["代码", "名称", "现价", "涨幅", "核心特征/追踪状态", "筛选机制/持仓"])
        self.tree.setColumnCount(6)
        self.tree.setAlternatingRowColors(True)
        
        # 1. 物理极限压缩缩进，解决“左边留空导致挤压显示位置”的视觉缺陷
        self.tree.setIndentation(5)
        
        # 2. 启用表头点击自定义排序
        self.tree.setSortingEnabled(True)
        
        setup_header_persistence(
            self.tree,
            config_key="ats_universe_tree_state",
            default_widths=[75, 90, 75, 75, 200, 120]
        )
        
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.tree)

    def load_mock_data(self):
        self._is_mock_active = True
        self.tree.setSortingEnabled(False)
        self.tree.clear()

        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        # 1. Radar Pool
        radar_items = [
            ("600519", "贵州茅台", "1650.00", "+1.25%", "MA20强支撑", "回踩20日均线企稳中"),
            ("002415", "海康威视", "32.40", "+0.85%", "波段吸筹", "缩量小幅震荡企稳"),
            ("300059", "东方财富", "15.75", "-1.20%", "高频超买回落", "放量跌破均线观察中"),
            ("601318", "中国平安", "45.10", "+2.10%", "机构持仓异动", "拉升拉回布林中轨"),
            ("000333", "美的集团", "62.30", "-0.40%", "大消费弱回调", "缩量回踩布林下轨")
        ]
        self.radar_root = UniverseTreeItem(self.tree)
        self.radar_root.setText(0, f"候选雷达池 (Radar Pool) ({len(radar_items)})")
        self.radar_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole + 1, 1) # Radar Pool weight
        
        for code, name, price, pct, strategy, desc in radar_items:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.radar_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+"):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))

        # 2. Watchlist Pool
        watch_items = [
            ("300750", "宁德时代", "185.50", "+3.80%", "MA20企稳突破", "黄金早盘爆量拉升"),
            ("600111", "北方稀土", "19.25", "+4.95%", "资源股复苏", "低开拉升冲破VWAP"),
            ("002594", "比亚迪", "245.00", "+2.50%", "新能源车风口", "日线收敛三角形突破")
        ]
        self.watch_root = UniverseTreeItem(self.tree)
        self.watch_root.setText(0, f"精选观察池 (Watchlist Pool) ({len(watch_items)})")
        self.watch_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole + 1, 2) # Watchlist weight

        for code, name, price, pct, strategy, desc in watch_items:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.watch_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+"):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))

        # 3. Trading Pool
        trade_items = [
            ("600030", "中信证券", "20.15", "+1.10%", "持仓中 (15%)", "基准+1.20% | 跟踪持股中"),
            ("000001", "平安银行", "10.45", "-0.95%", "持仓中 (10%)", "跌破VWAP警示 | 冷却防守")
        ]
        self.trade_root = UniverseTreeItem(self.tree)
        self.trade_root.setText(0, f"实盘交易池 (Trading Pool) ({len(trade_items)})")
        self.trade_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole + 1, 3) # Trading Pool weight

        for code, name, price, pct, strategy, desc in trade_items:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.trade_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+"):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))

        self.tree.expandAll()
        auto_fit_columns_once(self.tree, "ats_universe_tree_state")
        self.tree.setSortingEnabled(True)

    def update_pools(self, radar_list, watch_list, trade_list):
        self._is_mock_active = False
        self.tree.setSortingEnabled(False)
        self.tree.clear()

        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        # 1. Radar Pool
        self.radar_root = UniverseTreeItem(self.tree)
        self.radar_root.setText(0, f"候选雷达池 (Radar Pool) ({len(radar_list)})")
        self.radar_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.radar_root.setData(0, Qt.ItemDataRole.UserRole + 1, 1)
        for code, name, price, pct, strategy, desc in radar_list:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.radar_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))

        # 2. Watchlist Pool
        self.watch_root = UniverseTreeItem(self.tree)
        self.watch_root.setText(0, f"精选观察池 (Watchlist Pool) ({len(watch_list)})")
        self.watch_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.watch_root.setData(0, Qt.ItemDataRole.UserRole + 1, 2)
        for code, name, price, pct, strategy, desc in watch_list:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.watch_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))

        # 3. Trading Pool
        self.trade_root = UniverseTreeItem(self.tree)
        self.trade_root.setText(0, f"实盘交易池 (Trading Pool) ({len(trade_list)})")
        self.trade_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.trade_root.setData(0, Qt.ItemDataRole.UserRole + 1, 3)
        for code, name, price, pct, strategy, desc in trade_list:
            is_fav = code in fav_stocks
            item = UniverseTreeItem(self.trade_root)
            item.setText(0, code)
            item.setText(1, f"⭐ {name}" if is_fav else name)
            item.setText(2, price)
            item.setText(3, pct)
            item.setText(4, desc)
            item.setText(5, strategy)
            item.setData(0, Qt.ItemDataRole.UserRole, code)
            item.setData(1, Qt.ItemDataRole.UserRole, name)
            if is_fav:
                for col in range(6):
                    item.setBackground(col, QColor("#1A2A1A"))
                item.setForeground(0, QColor("#00FF88"))
                item.setForeground(1, QColor("#00FF88"))
                item.setForeground(2, QColor("#e2e2e5"))
                item.setForeground(4, QColor("#e2e2e5"))
                item.setForeground(5, QColor("#e2e2e5"))
            
            # Respect A-share red/green convention for percentage column
            if pct.startswith("+") or pct.startswith("0") or pct.startswith(" "):
                item.setForeground(3, QColor(COLOR_UP))
            else:
                item.setForeground(3, QColor(COLOR_DOWN))
        
        self.tree.expandAll()
        auto_fit_columns_once(self.tree, "ats_universe_tree_state")
        self.tree.setSortingEnabled(True)

    def _on_item_clicked(self, item, column):
        code = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.data(1, Qt.ItemDataRole.UserRole)
        if code and code != "root":
            self.stock_clicked.emit(code, name)

    def _on_current_item_changed(self, current, previous):
        if current:
            code = current.data(0, Qt.ItemDataRole.UserRole)
            name = current.data(1, Qt.ItemDataRole.UserRole)
            if code and code != "root":
                self.stock_clicked.emit(code, name)

    def _on_item_double_clicked(self, item, column):
        code = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.data(1, Qt.ItemDataRole.UserRole)
        if code and code != "root":
            parent_name = item.parent().text(0) if item.parent() else "未知股票池"
            if "雷达" in parent_name:
                pool_clean = "候选雷达池 (Radar Pool)"
            elif "精选" in parent_name:
                pool_clean = "精选观察池 (Watchlist Pool)"
            elif "实盘" in parent_name:
                pool_clean = "实盘交易池 (Trading Pool)"
            else:
                pool_clean = parent_name
                
            strategy = item.text(5)
            desc = item.text(4)
            context_info = {
                'position': f'策略股票池 -> {pool_clean}',
                'reason': strategy,
                'status': desc
            }
            self.stock_selected.emit(code, name, context_info)

    def filter_tree(self, text):
        text = text.lower()
        if not text:
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
                txt = "".join([child.text(col).lower() for col in range(6)])
                if text in txt:
                    child.setHidden(False)
                    root_visible = True
                else:
                    child.setHidden(True)
            root.setHidden(not root_visible)

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        code = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.data(1, Qt.ItemDataRole.UserRole)
        if not code or code == "root":
            return
            
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        from global_favorites import GlobalFavoriteManager
        
        fav_mgr = GlobalFavoriteManager()
        is_fav = str(code).strip() in fav_mgr.get_favorite_stocks()
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #ffffff;
            }
        """)
        
        copy_action = QAction(f"📋 复制股票代码 {code} ({name})", self)
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(code))
        menu.addAction(copy_action)
        
        menu.addSeparator()
        
        if is_fav:
            fav_action = QAction(f"❌ 取消重点关注 {code}", self)
        else:
            fav_action = QAction(f"⭐ 设为重点关注 {code}", self)
        fav_action.triggered.connect(lambda: self._toggle_favorite(code))
        menu.addAction(fav_action)
        
        menu.exec(self.tree.mapToGlobal(pos))

    def _toggle_favorite(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_stock(str(code).strip())
        except Exception as e:
            print(f"[Universe] Toggle favorite stock error: {e}")

    def _copy_to_clipboard(self, text):
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(str(text).strip())
        except Exception as e:
            print(f"[Universe] Clipboard copy failed: {e}")

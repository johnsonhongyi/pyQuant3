# -*- coding: utf-8 -*-
"""
ATS Universe Widget
Visualizes the multi-tier stock universe pools: Radar, Watchlist, and Trading.
Provides a tree structure with real-time mockup data.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QHBoxLayout, QPushButton, QLabel, QLineEdit, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QPoint
from PyQt6.QtGui import QColor, QFont
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, setup_header_persistence, auto_fit_columns_once
from ats.ui.ats_window_manager import ATSWindowManager
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)

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
        
        import math, re
        
        # Helper to extract clean float number (handles NaN, --, none safely)
        def extract_float(s):
            if not s:
                return None
            s_clean = str(s).strip()
            if s_clean in ('-', '--', 'nan', 'NaN', '+nan%', '-nan%', 'None', ''):
                return None
            match = re.search(r'[-+]?\d*\.?\d+', s_clean)
            if match:
                try:
                    val = float(match.group())
                    if not math.isnan(val):
                        return val
                except Exception:
                    pass
            return None

        order = tree.header().sortIndicatorOrder() if tree.header() else Qt.SortOrder.AscendingOrder
        is_desc = (order == Qt.SortOrder.DescendingOrder)

        # 辅助比较函数：无论升序还是降序，空值/NaN 始终稳定沉底到最后
        def compare_nums(n1, n2, default_str_comp=True):
            if n1 is None and n2 is None:
                return t1 < t2 if default_str_comp else False
            if n1 is None:
                # self 是空值/NaN: 若降序，返回 True 让其在反转后排在底部；若升序，返回 False 让其排在底部
                return True if is_desc else False
            if n2 is None:
                # other 是空值/NaN: 
                return False if is_desc else True
            if n1 != n2:
                return n1 < n2
            return t1 < t2 if default_str_comp else False

        if column == 0:
            # Code sorting
            c1_clean = ''.join(c for c in str(t1) if c.isdigit())
            c2_clean = ''.join(c for c in str(t2) if c.isdigit())
            if c1_clean and c2_clean:
                try:
                    v1 = int(c1_clean)
                    v2 = int(c2_clean)
                    if v1 != v2:
                        return v1 < v2
                except Exception:
                    pass
            return t1 < t2
        elif column == 1:
            # Name sorting
            return t1 < t2
        elif column in (2, 3):
            # Price (2) / Percent (3) sorting
            v1 = extract_float(t1)
            v2 = extract_float(t2)
            return compare_nums(v1, v2, default_str_comp=True)
        elif column == 4:
            # Description / Status sorting
            return t1 < t2
        elif column == 5:
            # Strategy / Position sorting: check for percentage e.g. "(15%)"
            pos_re = r'\((\d+)%\)'
            p1_match = re.search(pos_re, t1)
            p2_match = re.search(pos_re, t2)
            p1_val = float(p1_match.group(1)) if p1_match else extract_float(t1)
            p2_val = float(p2_match.group(1)) if p2_match else extract_float(t2)
            return compare_nums(p1_val, p2_val, default_str_comp=True)
        else:
            return t1 < t2


class UniverseTreeWidget(QWidget):
    # Signal emitted when a stock is double clicked or clicked
    stock_selected = pyqtSignal(str, str, dict) # code, name, context_info
    stock_clicked = pyqtSignal(str, str)        # code, name (for linkage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window_manager = ATSWindowManager.get_instance()
        self._is_mock_active = False
        self._init_ui()
        self.load_mock_data()

    def minimumSizeHint(self):
        # 允许左侧面板极度自由向左压缩调整，彻底杜绝 QSplitter 锁死卡顿
        return QSize(50, 50)

    def _init_ui(self):
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Title / Search Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)

        # 📈 【SBC Launcher 独立持仓盯盘】左侧核心入口：专门盯持仓盘，支持二次点击统一关闭保存
        self.btn_run_sbc = QPushButton("📈 盯盘")
        self.btn_run_sbc.setStyleSheet("""
            QPushButton {
                background-color: #1a2e22;
                border: 1px solid #00ff88;
                border-radius: 4px;
                color: #00ff88;
                font-weight: bold;
                font-size: 8.5pt;
                min-width: 44px;
                max-width: 52px;
                min-height: 23px;
                max-height: 23px;
                padding: 1px 3px;
            }
            QPushButton:hover {
                background-color: #244633;
                border-color: #00ffaa;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0f1c15;
            }
        """)
        self.btn_run_sbc.setToolTip("📈 [SBC Launcher] 独立持仓盯盘启动器 (单击: 启动盯盘 | 二次点击: 统一保存并关闭)")
        self.btn_run_sbc.clicked.connect(self._on_launch_run_sbc_clicked)
        self.btn_run_sbc.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_run_sbc.customContextMenuRequested.connect(self._popup_run_sbc_menu)
        header_layout.addWidget(self.btn_run_sbc)
        header_layout.addStretch()
        
        # --- 窗口位置手动快照（提供3个保存位置，全面持久化所有打开关联窗口，防多屏覆盖）---
        btn_qss = """
            QPushButton {
                background-color: #1a1a24;
                color: #e2e2ec;
                border: 1px solid #3a3a4e;
                border-radius: 4px;
                font-size: 10pt;
                font-family: "Segoe UI Emoji", "Segoe UI Symbol", "Segoe UI", sans-serif;
                min-width: 25px;
                max-width: 25px;
                min-height: 23px;
                max-height: 23px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #2a2a3b;
                border-color: #5c6b84;
                color: #60a5fa;
            }
            QPushButton:pressed {
                background-color: #12121a;
                border-color: #3b82f6;
            }
        """
        self.btn_save_pos = QPushButton("📍")
        self.btn_save_pos.setStyleSheet(btn_qss)
        self.btn_save_pos.setToolTip(self.window_manager.get_snapshot_tooltip_text("📍 手动保存全量快照"))
        self.btn_save_pos.clicked.connect(self._popup_save_slots_menu)
        header_layout.addWidget(self.btn_save_pos)

        self.btn_restore_pos = QPushButton("🔧")
        self.btn_restore_pos.setStyleSheet(btn_qss)
        self.btn_restore_pos.setToolTip(self.window_manager.get_snapshot_tooltip_text("🔧 恢复手动快照位置"))
        self.btn_restore_pos.clicked.connect(self._popup_restore_slots_menu)
        header_layout.addWidget(self.btn_restore_pos)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索代码/名称...")
        self.search_input.setMaximumWidth(130)
        self.search_input.setMinimumWidth(0)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.search_input.setStyleSheet("background-color: #1a1a22; border: 1px solid #333; border-radius: 4px; padding: 2px 5px;")
        self.search_input.textChanged.connect(self.filter_tree)
        header_layout.addWidget(self.search_input)
        layout.addLayout(header_layout)

        # Tree Widget
        self.tree = QTreeWidget()
        self.tree.setMinimumWidth(0)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setHeaderLabels(["代码", "名称", "现价", "涨幅", "核心特征/追踪状态", "筛选机制/持仓"])
        self.tree.setColumnCount(6)
        self.tree.setAlternatingRowColors(True)

        # 视口深暗黑底色设置，确保局部重绘与列宽调整时干净擦除旧图元，杜绝重影与白闪
        self.tree.viewport().setStyleSheet("background-color: #121218; border: none;")
        self.tree.setStyleSheet("QTreeWidget { background-color: #121218; border: none; }")
        
        # 1. 物理极限压缩缩进，解决“左边留空导致挤压显示位置”的视觉缺陷
        self.tree.setIndentation(5)
        
        # 2. 启用表头点击自定义排序
        self.tree.setSortingEnabled(True)
        
        setup_header_persistence(
            self.tree,
            config_key="ats_universe_tree_state",
            default_widths=[75, 90, 75, 75, 200, 120]
        )
        
        # 3. 挂载持久化方法与防抖保存
        self.tree.save_header_state = self.save_header_state
        self.tree.restore_header_state = self.restore_header_state
        self._header_save_timer = QTimer(self)
        self._header_save_timer.setSingleShot(True)
        self._header_save_timer.setInterval(500)
        self._header_save_timer.timeout.connect(self.save_header_state)
        self.tree.header().sectionResized.connect(self._on_section_resized)

        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.tree)

        # 恢复先前持久化的列宽
        QTimer.singleShot(100, self.restore_header_state)

    def _on_section_resized(self, logicalIndex, oldSize, newSize):
        if getattr(self, '_is_restoring_header', False):
            return
        if hasattr(self, '_header_save_timer'):
            self._header_save_timer.start(500)

    def save_header_state(self):
        try:
            from ats.ui.styles import save_config_node
            col_widths = [self.tree.columnWidth(c) for c in range(self.tree.columnCount())]
            save_config_node("ats_universe_tree_widths", col_widths)
            if self.tree.header():
                state_hex = self.tree.header().saveState().toHex().data().decode("utf-8")
                save_config_node("ats_universe_tree_state", state_hex)
        except Exception as e:
            logger.debug(f"保存策略股票池列宽异常: {e}")

    def restore_header_state(self):
        self._is_restoring_header = True
        try:
            from ats.ui.styles import load_config_node
            widths = load_config_node("ats_universe_tree_widths")
            # 💡 强制保底最小安全列宽 (代码>=72, 名称>=88, 现价>=68, 涨幅>=68, 彻底防止截断)
            min_col_widths = [72, 88, 68, 68, 120, 100]
            if widths and isinstance(widths, list):
                self.tree.header().blockSignals(True)
                for c, w in enumerate(widths):
                    if c < self.tree.columnCount():
                        min_w = min_col_widths[c] if c < len(min_col_widths) else 50
                        safe_w = max(min_w, int(w))
                        self.tree.setColumnWidth(c, safe_w)
                self.tree.header().blockSignals(False)
            else:
                self.tree.header().blockSignals(True)
                for c, min_w in enumerate(min_col_widths):
                    if c < self.tree.columnCount():
                        self.tree.setColumnWidth(c, min_w)
                self.tree.header().blockSignals(False)
        except Exception as e:
            logger.debug(f"恢复策略股票池列宽异常: {e}")
        finally:
            self._is_restoring_header = False

    # ==========================================
    # 窗口位置独立快照管理 (对齐 Tk 3 槽位交互)
    # ==========================================
    def _popup_save_slots_menu(self):
        """弹出保存快照槽位选择菜单 (提供 3 个位置)"""
        try:
            self._update_snapshot_tooltips()
            menu = self.window_manager.build_save_menu(self, self._on_save_slot_selected)
            if hasattr(self, "btn_save_pos") and self.btn_save_pos:
                menu.exec(self.btn_save_pos.mapToGlobal(QPoint(0, self.btn_save_pos.height() + 2)))
        except Exception as e:
            logger.warning(f"弹出保存快照菜单异常: {e}")
            self._on_save_slot_selected(1)

    def _popup_restore_slots_menu(self):
        """弹出恢复快照槽位选择菜单 (提供 3 个位置)"""
        try:
            self._update_snapshot_tooltips()
            menu = self.window_manager.build_restore_menu(self, self._on_restore_slot_selected)
            if hasattr(self, "btn_restore_pos") and self.btn_restore_pos:
                menu.exec(self.btn_restore_pos.mapToGlobal(QPoint(0, self.btn_restore_pos.height() + 2)))
        except Exception as e:
            logger.warning(f"弹出恢复快照菜单异常: {e}")
            self._on_restore_slot_selected(1)

    def _on_save_slot_selected(self, slot: int):
        """执行保存快照到指定槽位 (1, 2, 3)"""
        try:
            mw = self.window()
            res = self.window_manager.save_snapshot(slot=slot, main_window=mw)
            total = res.get("total_windows", 0)
            ymd = res.get("date_ymd", "")
            self._update_snapshot_tooltips()
            msg = f"📍 槽位 {slot} 快照已保存: {ymd} (共{total}个窗口已锁定)"
            self._notify_status(msg)
        except Exception as e:
            logger.error(f"[UniverseTreeWidget] 槽位 {slot} 快照保存失败: {e}")

    def _on_restore_slot_selected(self, slot: int):
        """从指定槽位 (1, 2, 3) 恢复快照"""
        try:
            mw = self.window()
            count, restored_list = self.window_manager.restore_snapshot(slot=slot, main_window=mw)
            slots = self.window_manager.get_snapshot_slots_info()
            ymd = slots.get(slot, {}).get("date_ymd", "")
            date_info = f" [{ymd}]" if ymd else ""
            if count > 0:
                msg = f"🔧 槽位 {slot} 快照已恢复{date_info}: 共{count}个窗口已精准归位，覆盖消除"
            else:
                msg = f"⚠️ 槽位 {slot} 尚无有效快照，请先保存"
            self._notify_status(msg)
        except Exception as e:
            logger.error(f"[UniverseTreeWidget] 槽位 {slot} 恢复失败: {e}")

    def _update_snapshot_tooltips(self):
        """动态刷新按钮 ToolTip 提示"""
        try:
            if hasattr(self, "btn_save_pos") and self.btn_save_pos:
                self.btn_save_pos.setToolTip(self.window_manager.get_snapshot_tooltip_text("📍 手动保存全量快照"))
            if hasattr(self, "btn_restore_pos") and self.btn_restore_pos:
                self.btn_restore_pos.setToolTip(self.window_manager.get_snapshot_tooltip_text("🔧 恢复手动快照位置"))
        except Exception:
            pass

    def _notify_status(self, msg: str):
        """统一向主窗口状态栏输出操作反馈"""
        try:
            mw = self.window()
            if hasattr(mw, "status_bar") and mw.status_bar:
                mw.status_bar.showMessage(msg, 6000)
            elif hasattr(mw, "statusBar") and callable(mw.statusBar):
                sb = mw.statusBar()
                if sb:
                    sb.showMessage(msg, 6000)
        except Exception:
            pass
        logger.info(msg)

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
        if not getattr(self, '_has_restored_widths_once', False):
            self._has_restored_widths_once = True
            self.restore_header_state()
        self.tree.setSortingEnabled(True)

    def _update_stock_item(self, item, code, name, price, pct, strategy, desc, is_fav):
        """原地更新单个股票项，实施 Dirty Check，消除无效的 setText / 属性重设与闪烁"""
        disp_name = f"⭐ {name}" if is_fav else name
        col_texts = [code, disp_name, str(price), str(pct), str(desc), str(strategy)]
        for col, txt in enumerate(col_texts):
            if item.text(col) != txt:
                item.setText(col, txt)

        if item.data(0, Qt.ItemDataRole.UserRole) != code:
            item.setData(0, Qt.ItemDataRole.UserRole, code)
        if item.data(1, Qt.ItemDataRole.UserRole) != name:
            item.setData(1, Qt.ItemDataRole.UserRole, name)

        if is_fav:
            bg_fav = QColor("#1A2A1A")
            for col in range(6):
                item.setBackground(col, bg_fav)
            item.setForeground(0, QColor("#00FF88"))
            item.setForeground(1, QColor("#00FF88"))
            item.setForeground(2, QColor("#e2e2e5"))
            item.setForeground(4, QColor("#e2e2e5"))
            item.setForeground(5, QColor("#e2e2e5"))
        else:
            trans_brush = QColor(0, 0, 0, 0)
            def_fg = QColor("#e2e2e5")
            for col in range(6):
                item.setBackground(col, trans_brush)
                if col not in (3, 5):
                    item.setForeground(col, def_fg)

        # 时段标签颜色高亮 (Strategy column) — 早期信号用更醒目的颜色
        strategy_str = str(strategy)
        if '🔔' in strategy_str or '竞价' in strategy_str:
            item.setForeground(5, QColor("#FF4444"))  # 竞价信号: 亮红
            item.setFont(5, QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
        elif '🥇' in strategy_str or '黄金' in strategy_str:
            item.setForeground(5, QColor("#FFD700"))  # 黄金早盘: 金色
            item.setFont(5, QFont("Microsoft YaHei", -1, QFont.Weight.Bold))
        elif '🥈' in strategy_str:
            item.setForeground(5, QColor("#C0C0C0"))  # 盘中跟进: 银色
        elif not is_fav:
            item.setForeground(5, QColor("#888888"))  # 午后/其他: 灰色

        # Respect A-share red/green convention for percentage column
        pct_str = str(pct)
        if pct_str.startswith("+") or pct_str.startswith("0") or pct_str.startswith(" "):
            item.setForeground(3, QColor(COLOR_UP))
        else:
            item.setForeground(3, QColor(COLOR_DOWN))

    def _sync_pool_subtree(self, root, title_prefix, stock_list, fav_stocks):
        """增量比对并同步子树节点，保留已有节点并仅更新差异 (In-Place Diff Sync)"""
        target_title = f"{title_prefix} ({len(stock_list)})"
        if root.text(0) != target_title:
            root.setText(0, target_title)

        existing_items = {}
        for i in range(root.childCount()):
            child = root.child(i)
            c = child.data(0, Qt.ItemDataRole.UserRole)
            if c:
                existing_items[c] = child

        new_codes = set()
        for entry in stock_list:
            if entry and len(entry) >= 6:
                new_codes.add(entry[0])

        # 1. 安全移除已不在新数据中的标的 (倒序遍历)
        for i in reversed(range(root.childCount())):
            child = root.child(i)
            c = child.data(0, Qt.ItemDataRole.UserRole)
            if c not in new_codes:
                root.removeChild(child)

        # 2. 原地复用或新增子节点
        for code, name, price, pct, strategy, desc in stock_list:
            is_fav = code in fav_stocks
            item = existing_items.get(code)
            if item is None or item.treeWidget() is None:
                item = UniverseTreeItem(root)
            self._update_stock_item(item, code, name, price, pct, strategy, desc, is_fav)

    def update_pools(self, radar_list, watch_list, trade_list):
        self._is_mock_active = False

        try:
            # 记录滚动条原位与当前选中的股票代码
            vbar = self.tree.verticalScrollBar()
            scroll_pos = vbar.value() if vbar else 0
            selected_code = None
            curr_item = self.tree.currentItem()
            if curr_item:
                selected_code = curr_item.data(0, Qt.ItemDataRole.UserRole)

            # 🛡️ [排序状态记忆]
            sort_col = self.tree.sortColumn()
            sort_order = self.tree.header().sortIndicatorOrder() if self.tree.header() else Qt.SortOrder.DescendingOrder
            if sort_col < 0:
                sort_col = 3  # 默认按涨跌幅列排序
                sort_order = Qt.SortOrder.DescendingOrder

            self.tree.setSortingEnabled(False)

            try:
                from global_favorites import GlobalFavoriteManager
                fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            except Exception:
                fav_stocks = set()

            # 确保三级池根节点常驻存在，绝不重复 clear 销毁
            is_initial = False
            if not hasattr(self, 'radar_root') or self.radar_root is None or self.radar_root.treeWidget() is None:
                self.tree.clear()
                self.radar_root = UniverseTreeItem(self.tree)
                self.radar_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                self.radar_root.setData(0, Qt.ItemDataRole.UserRole, "root")
                self.radar_root.setData(0, Qt.ItemDataRole.UserRole + 1, 1)

                self.watch_root = UniverseTreeItem(self.tree)
                self.watch_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                self.watch_root.setData(0, Qt.ItemDataRole.UserRole, "root")
                self.watch_root.setData(0, Qt.ItemDataRole.UserRole + 1, 2)

                self.trade_root = UniverseTreeItem(self.tree)
                self.trade_root.setFont(0, QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
                self.trade_root.setData(0, Qt.ItemDataRole.UserRole, "root")
                self.trade_root.setData(0, Qt.ItemDataRole.UserRole + 1, 3)
                is_initial = True

            # 增量原地更新各池数据 (In-Place Diff Sync)
            self._sync_pool_subtree(self.radar_root, "候选雷达池 (Radar Pool)", radar_list, fav_stocks)
            self._sync_pool_subtree(self.watch_root, "精选观察池 (Watchlist Pool)", watch_list, fav_stocks)
            self._sync_pool_subtree(self.trade_root, "实盘交易池 (Trading Pool)", trade_list, fav_stocks)

            # 仅在初次构建时展开全部；后续平滑更新绝不强行 expandAll，保持用户的折叠与浏览状态
            if is_initial:
                self.tree.expandAll()

            if not getattr(self, '_has_restored_widths_once', False):
                self._has_restored_widths_once = True
                self.restore_header_state()

            # 🛡️ [排序状态恢复]
            self.tree.setSortingEnabled(True)
            if sort_col >= 0:
                self.tree.sortByColumn(sort_col, sort_order)

            # 恢复选中的标的节点
            if selected_code and selected_code != "root":
                found = False
                for root in (self.radar_root, self.watch_root, self.trade_root):
                    for i in range(root.childCount()):
                        child = root.child(i)
                        if child.data(0, Qt.ItemDataRole.UserRole) == selected_code:
                            self.tree.setCurrentItem(child)
                            found = True
                            break
                    if found:
                        break

            # 锁定滚动条位置，彻底杜绝视口跳动与抖动
            if vbar and vbar.value() != scroll_pos:
                vbar.setValue(scroll_pos)
        finally:
            pass

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

        # 📈 调出 SBC 实盘走势
        sbc_action = QAction(f"📈 调出 【{name} ({code})】 SBC 实盘走势", self)
        sbc_action.triggered.connect(lambda: self._open_sbc_chart(code, name))
        menu.addAction(sbc_action)

        # 🚀 调出分时阶梯独立盯盘
        ladder_action = QAction(f"🚀 调出 【{name} ({code})】 分时阶梯独立盯盘", self)
        ladder_action.triggered.connect(lambda: self._open_ladder_window(code, name))
        menu.addAction(ladder_action)

        # 🎯 运行 60f 通道策略测算 (TDX直连)
        eval_action = QAction(f"🎯 运行 【{name}】 60f 通道底部反转测算 (TDX直连)", self)
        eval_action.triggered.connect(lambda: self._run_60f_channel_eval(code, name))
        menu.addAction(eval_action)

        menu.addSeparator()

        # ⚡ 发送到异动联动
        from ats.ui.base_table import send_to_linkage
        linkage_action = QAction(f"⚡ 发送到异动联动 {code}", self)
        linkage_action.triggered.connect(lambda: send_to_linkage(code, name, self))
        menu.addAction(linkage_action)
        
        menu.addSeparator()
        
        if is_fav:
            fav_action = QAction(f"❌ 取消重点关注 {code}", self)
        else:
            fav_action = QAction(f"⭐ 设为重点关注 {code}", self)
        fav_action.triggered.connect(lambda: self._toggle_favorite(code))
        menu.addAction(fav_action)
        
        menu.exec(self.tree.mapToGlobal(pos))

    def _on_launch_run_sbc_clicked(self):
        """【📈 SBC Launcher 持仓盯盘】首次点击调起独立进程，二次点击弹出统一关闭并保存菜单"""
        try:
            from ats.ui.sbc_launcher import SBCProcessManager
            mgr = SBCProcessManager.get_instance()

            if mgr.is_launcher_running():
                # 二次点击：弹出统一关闭保存或激活菜单
                self._popup_launcher_running_menu()
            else:
                # 首次点击：调起独立进程盯持仓
                proc = mgr.launch_holdings_watcher()
                if proc:
                    self._update_launcher_btn_state(running=True)
                    self._notify_status("📈 [SBC Launcher] 已成功调起持仓盯盘独立进程")
        except Exception as e:
            logger.error(f"[UniverseWidget] 调起持仓盯盘异常: {e}", exc_info=True)

    def _update_launcher_btn_state(self, running: bool):
        """动态更新盯盘按钮文本与发光视觉状态"""
        if not hasattr(self, 'btn_run_sbc') or not self.btn_run_sbc:
            return
        if running:
            self.btn_run_sbc.setText("📈 盯盘中")
            self.btn_run_sbc.setStyleSheet("""
                QPushButton {
                    background-color: #0d3824;
                    border: 1.5px solid #00ff88;
                    border-radius: 4px;
                    color: #00ff88;
                    font-weight: bold;
                    font-size: 8.5pt;
                    min-width: 48px;
                    max-width: 56px;
                    min-height: 23px;
                    max-height: 23px;
                    padding: 1px 3px;
                }
                QPushButton:hover {
                    background-color: #1a4d33;
                    border-color: #38bdf8;
                    color: #ffffff;
                }
            """)
        else:
            self.btn_run_sbc.setText("📈 盯盘")
            self.btn_run_sbc.setStyleSheet("""
                QPushButton {
                    background-color: #1a2e22;
                    border: 1px solid #00ff88;
                    border-radius: 4px;
                    color: #00ff88;
                    font-weight: bold;
                    font-size: 8.5pt;
                    min-width: 44px;
                    max-width: 52px;
                    min-height: 23px;
                    max-height: 23px;
                    padding: 1px 3px;
                }
                QPushButton:hover {
                    background-color: #244633;
                    border-color: #00ffaa;
                    color: #ffffff;
                }
            """)

    def _append_snapshots_menu(self, menu):
        """在下拉菜单中追加最近 3 组历史快照子菜单，供操盘手直选恢复与切换"""
        try:
            import run_sbc
            from ats.ui.sbc_launcher import SBCProcessManager
            mgr = SBCProcessManager.get_instance()

            snapshots = run_sbc.get_launcher_history_snapshots()
            menu_snap = menu.addMenu("📂 历史快照恢复 (最近3组)")
            menu_snap.setStyleSheet("""
                QMenu {
                    background-color: #1a1a24;
                    border: 1px solid #2e2e36;
                    color: #e2e2e5;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 18px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #2c2c35;
                    color: #38bdf8;
                }
            """)

            if not snapshots:
                act_none = menu_snap.addAction("📂 暂无历史快照数据")
                act_none.setEnabled(False)
                return

            for i, snap in enumerate(snapshots[:3]):
                snap_idx = i + 1
                t_str = snap.get("time", "")
                t_show = t_str.split(" ")[1] if " " in t_str else (t_str or "历史")
                codes = snap.get("codes", [])
                code_summary = ", ".join(codes[:4])
                if len(codes) > 4:
                    code_summary += f"... 等{len(codes)}只"
                else:
                    code_summary += f" ({len(codes)}只)"

                label = f"📌 快照 {snap_idx} [{t_show}]: {code_summary}"
                if snap_idx == 1:
                    label = f"📌 快照 1 (最新 [{t_show}]): {code_summary}"

                act = menu_snap.addAction(label)
                def _make_trigger(idx, c_list):
                    def _do_switch():
                        logger.info(f"[UniverseWidget] 操盘手点击加载历史快照 {idx}: {c_list}")
                        proc = mgr.launch_holdings_watcher(snapshot_idx=idx)
                        self._update_launcher_btn_state(running=True)
                        self._notify_status(f"📈 [SBC Launcher] 已成功恢复历史快照 {idx} ({len(c_list)} 只标的) 并平铺重排")
                    return _do_switch

                act.triggered.connect(_make_trigger(snap_idx, codes))
        except Exception as err:
            logger.warning(f"[UniverseWidget] 构造历史快照菜单异常: {err}")

    def _popup_launcher_running_menu(self):
        """二次点击已在运行的 [SBC Launcher] 时弹出统一关闭保存与操作菜单"""
        from PyQt6.QtWidgets import QMenu
        from ats.ui.sbc_launcher import SBCProcessManager
        mgr = SBCProcessManager.get_instance()

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
                font-weight: bold;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #00ff88;
            }
        """)

        act_close = menu.addAction("🛑 统一关闭并保存所有盯盘窗口 (持久化)")
        def _do_close():
            mgr.close_launcher_process()
            self._update_launcher_btn_state(running=False)
            self._notify_status("🛑 [SBC Launcher] 盯盘窗口已统一关闭并完成独立持久化保存。")
        act_close.triggered.connect(_do_close)

        act_activate = menu.addAction("🪟 置顶激活所有已打开的盯盘窗口")
        act_activate.triggered.connect(mgr.activate_launcher_windows)

        act_restart = menu.addAction("🔄 重新读取最新持仓并重开盯盘")
        def _do_restart():
            mgr.close_launcher_process()
            mgr.launch_holdings_watcher()
            self._update_launcher_btn_state(running=True)
            self._notify_status("🔄 [SBC Launcher] 已重新读取最新持仓并启动盯盘。")
        act_restart.triggered.connect(_do_restart)

        menu.addSeparator()
        self._append_snapshots_menu(menu)

        btn = getattr(self, "btn_run_sbc", None)
        pos = btn.mapToGlobal(QPoint(0, btn.height() + 2)) if btn else self.mapToGlobal(QPoint(0, 0))
        menu.exec(pos)

    def _popup_run_sbc_menu(self, pos):
        """📈 SBC 快捷操作右键菜单"""
        from PyQt6.QtWidgets import QMenu
        from ats.ui.sbc_launcher import SBCProcessManager
        mgr = SBCProcessManager.get_instance()

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
                color: #00ff88;
            }
        """)

        # 1. 启动或统一关闭持仓盯盘
        if mgr.is_launcher_running():
            act_toggle = menu.addAction("🛑 统一关闭并保存所有盯盘窗口 (持久化)")
            def _do_close_toggle():
                mgr.close_launcher_process()
                self._update_launcher_btn_state(running=False)
                self._notify_status("🛑 [SBC Launcher] 盯盘窗口已统一关闭并保存。")
            act_toggle.triggered.connect(_do_close_toggle)
        else:
            act_toggle = menu.addAction("📈 启动独立持仓盯盘 (run_sbc.py)")
            def _do_launch_toggle():
                mgr.launch_holdings_watcher()
                self._update_launcher_btn_state(running=True)
                self._notify_status("📈 [SBC Launcher] 已成功启动持仓盯盘。")
            act_toggle.triggered.connect(_do_launch_toggle)

        menu.addSeparator()
        self._append_snapshots_menu(menu)
        menu.addSeparator()

        # 2. 若有选中标的，单独打开选中标的
        cur_item = self.tree.currentItem() if hasattr(self, 'tree') and self.tree else None
        if cur_item:
            c_text = cur_item.text(0).strip()
            n_text = cur_item.text(1).strip()
            digits = "".join(filter(str.isdigit, c_text))
            if len(digits) >= 6 and digits != "000000":
                code_sel = digits[:6]
                act_sel = menu.addAction(f"📈 调出当前选中标的【{n_text} ({code_sel})】SBC 分时走势")
                act_sel.triggered.connect(lambda: self._open_sbc_chart(code_sel, n_text))

        # 3. 平铺重排
        act_rearrange = menu.addAction("🪟 一键平铺重排所有 SBC 窗口 (Q)")
        def _do_rearrange():
            from ats.ui.intraday_strategy_dialog import rearrange_all_sbc_windows
            rearrange_all_sbc_windows(parent_win=self.window())
        act_rearrange.triggered.connect(_do_rearrange)

        btn = getattr(self, "btn_run_sbc", None)
        global_pos = btn.mapToGlobal(pos) if btn else self.mapToGlobal(pos)
        menu.exec(global_pos)

    def _open_sbc_chart(self, code, name):
        """调出 SBC 实盘走势窗口 (统一 ATS 内部原生窗口，确保同源重排与管理)"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self.window(), code, period_mode="10d")
        except Exception as e:
            logger.error(f"[Universe] 调出 SBC 窗口失败: {e}")

    def _open_ladder_window(self, code, name):
        """调出分时阶梯独立盯盘主窗口"""
        try:
            from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow
            win = PinzhunLadderStandaloneWindow(code=code, name=name, parent=self.window())
            win.show()
        except Exception as e:
            logger.error(f"[Universe] 调出分时阶梯窗口失败: {e}")

    def _run_60f_channel_eval(self, code, name):
        """单股直连 TDX 进行 60f 通道底部反转策略测算"""
        try:
            from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
            from PyQt6.QtWidgets import QMessageBox
            strategy = ChannelBottomReversalStrategy()
            res = strategy.evaluate_stock_tdx(code)
            if res.get("is_matched", False):
                msg = (
                    f"🎉 【{name} ({code})】 命中 60f 通道底部反转突破形态！\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 形态评分: {res.get('score', 0)} 分\n"
                    f"🎯 建议介入价: {res.get('entry_price', 0.0):.2f} 元\n"
                    f"🛡️ 止损保护位: {res.get('stop_loss', 0.0):.2f} 元\n"
                    f"🚀 第一目标位: {res.get('target_price_1', 0.0):.2f} 元\n"
                    f"💎 第二目标位: {res.get('target_price_2', 0.0):.2f} 元\n"
                    f"📉 通道下倾角: {res.get('channel_slope_deg', 0.0):+.1f}°\n"
                    f"💧 底部缩量比: {res.get('volume_shrink_pct', 0.0):.1f}%\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 逻辑解析:\n{res.get('reason', '')}"
                )
                QMessageBox.information(self, f"60f 通道策略诊断 - {name}", msg)
            else:
                msg = (
                    f"⚠️ 【{name} ({code})】 未触发 60f 通道底部反转信号\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔍 未满足原因: {res.get('reason', '不满足形态条件')}\n"
                    f"📉 通道斜率: {res.get('channel_slope_deg', 0.0):+.1f}°\n"
                    f"最低波谷: {res.get('lowest_low', 0.0):.2f} 元\n"
                    f"整理高点: {res.get('base_high', 0.0):.2f} 元\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                QMessageBox.information(self, f"60f 通道策略诊断 - {name}", msg)
        except Exception as e:
            logger.error(f"[Universe] 60f 通道测算异常: {e}")

    def _toggle_favorite(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_stock(str(code).strip())
            self.refresh_favorites_display()
            win = self.window()
            if win and hasattr(win, '_safe_favorites_changed'):
                win._safe_favorites_changed()
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

    def refresh_favorites_display(self):
        """[0ms 轻量刷新] 原位刷新树节点重点关注 ⭐ 标识与背景样式，绝不摧毁重建节点"""
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                item = root.child(j)
                code = item.data(0, Qt.ItemDataRole.UserRole)
                if not code or code == "root":
                    continue
                code_str = str(code).strip()
                name = item.data(1, Qt.ItemDataRole.UserRole) or item.text(1)
                is_fav = code_str in fav_stocks
                clean_name = str(name).replace("⭐ ", "").replace("⭐", "").replace("★ ", "").replace("★", "").strip()
                new_name_text = f"⭐ {clean_name}" if is_fav else clean_name
                if item.text(1) != new_name_text:
                    item.setText(1, new_name_text)

                if is_fav:
                    for col in range(6):
                        item.setBackground(col, QColor("#1A2A1A"))
                    item.setForeground(0, QColor("#00FF88"))
                    item.setForeground(1, QColor("#00FF88"))
                else:
                    for col in range(6):
                        item.setData(col, Qt.ItemDataRole.BackgroundRole, None)
                    item.setForeground(0, QColor("#e2e2e5"))
                    item.setForeground(1, QColor("#e2e2e5"))


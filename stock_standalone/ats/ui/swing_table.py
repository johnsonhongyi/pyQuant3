# -*- coding: utf-8 -*-
"""
ATS Swing State Table Widget
Tracks the status of stocks in the MA20 pullback lifecycle.
Lifecycle stages: 回踩中 (Pulling back), 回踩企稳 (Pullback stabilized), 持股中 (Holding), 已平仓 (Closed).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHeaderView, QLabel, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import os
import json
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_WARN, COLOR_ACCENT, setup_header_persistence, auto_fit_columns_once, NumericTableWidgetItem, load_config_node, save_config_node, parse_bool_config
from ats.ui.base_table import BaseATSTableWidget
from ats.ui.favorite_panel import get_ats_extra_cols, get_ats_table_headers

FONT_BOLD = QFont("Microsoft YaHei", -1, QFont.Weight.Bold)
COLOR_GREEN = QColor("#00FF88")
COLOR_GOLD = QColor("#FFD700")
COLOR_CORAL = QColor("#FF7F50")
COLOR_RED = QColor("#FF3333")
COLOR_BRIGHT_RED = QColor("#FF4444")
COLOR_GRAY = QColor("#e2e2e5")
COLOR_FAV_BG = QColor("#1A2A1A")
COLOR_DEFAULT_BG = QColor("#121214")
COLOR_UP_Q = QColor(COLOR_UP)
COLOR_DOWN_Q = QColor(COLOR_DOWN)
COLOR_WARN_Q = QColor(COLOR_WARN)
COLOR_INFO_Q = QColor(COLOR_INFO)
COLOR_ACCENT_Q = QColor(COLOR_ACCENT)

PERSIST_KEY_SWING_FILTER = "ats_swing_tab_filter_enabled"


class SwingStateTable(QWidget):
    stock_clicked = pyqtSignal(str, str) # code, name (for linkage)
    stock_double_clicked = pyqtSignal(str, str, dict) # code, name, context_info
    dragon_monitor_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_mock_active = False
        self.extra_cols = get_ats_extra_cols()
        
        # 🎯 策略过滤持久化开关 (专属独立持久化，默认关闭)
        saved_filter = load_config_node(PERSIST_KEY_SWING_FILTER, load_config_node("ats_tab_filter_enabled", False))
        self.filter_enabled = parse_bool_config(saved_filter, default=False)
        
        self._init_ui()
        self.load_mock_data()

    def toggle_filter_state(self):
        """切换策略公式过滤状态并专属独立持久化"""
        self.filter_enabled = not self.filter_enabled
        save_config_node(PERSIST_KEY_SWING_FILTER, bool(self.filter_enabled))
        self._update_filter_button_ui()
        self.table.setUpdatesEnabled(True)
        self._apply_favorite_filter()

    def _update_filter_button_ui(self):
        """更新策略过滤按钮的高亮与状态文案"""
        if getattr(self, 'filter_enabled', False):
            self.btn_toggle_filter.setText("🎯 策略过滤 (开)")
            self.btn_toggle_filter.setStyleSheet("""
                QPushButton {
                    background-color: #1a3322;
                    color: #00ff88;
                    font-weight: bold;
                    border: 1.5px solid #00ff88;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #00ff88;
                    color: #000000;
                }
            """)
            self.btn_toggle_filter.setToolTip("当前状态：【已开启】根据主窗口策略公式过滤当前列表 (点击可关闭)")
        else:
            self.btn_toggle_filter.setText("🎯 策略过滤 (关)")
            self.btn_toggle_filter.setStyleSheet("""
                QPushButton {
                    background-color: #222228;
                    color: #888888;
                    font-weight: bold;
                    border: 1px solid #44444f;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #33333d;
                    color: #ffffff;
                    border-color: #777788;
                }
            """)
            self.btn_toggle_filter.setToolTip("当前状态：【已关闭】展示全部标的 (点击开启根据策略公式过滤)")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel("📉 大级别 MA20d 回调跟踪器")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 12pt;")
        header.addWidget(title)
        header.addStretch()

        # 🎯 策略过滤持久化开关按钮
        self.btn_toggle_filter = QPushButton()
        self._update_filter_button_ui()
        self.btn_toggle_filter.clicked.connect(self.toggle_filter_state)
        header.addWidget(self.btn_toggle_filter)
        header.addSpacing(6)
        
        from PyQt6.QtWidgets import QCheckBox
        self.chk_favorite_show = QCheckBox("⭐ 重点")
        self.chk_favorite_show.setChecked(self._load_show_favorite_config())  # 重点默认打开，并自动持久化
        self.chk_favorite_show.setStyleSheet("""
            QCheckBox { color: #ffd700; font-weight: bold; font-size: 9.5pt; margin-right: 5px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
        """)
        self.chk_favorite_show.stateChanged.connect(self._on_favorite_checkbox_changed)
        header.addWidget(self.chk_favorite_show)
        header.addSpacing(6)

        self.btn_dragon = QPushButton("🐉 监控加速龙头")
        self.btn_dragon.setStyleSheet("""
            QPushButton { background-color: #2a1b1b; color: #ff5555; font-weight: bold; border: 1px solid #ff5555; border-radius: 3px; padding: 2px 6px; }
            QPushButton:hover { background-color: #ff5555; color: #000000; }
        """)
        self.btn_dragon.clicked.connect(self.dragon_monitor_requested.emit)
        header.addWidget(self.btn_dragon)
        header.addSpacing(10)
        
        self.btn_refresh = QPushButton("🔄 刷新状态")
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # Table
        self.table = BaseATSTableWidget()
        headers = get_ats_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        default_widths = [90, 100, 90, 110, 110, 90, 100, 110, 75, 60, 50, 60, 60, 75, 75] + [70] * len(self.extra_cols) + [250]
        self.table.setup_persistence(
            config_key="ats_swing_table_state_v2",
            default_widths=default_widths,
            max_widths={len(headers) - 1: 350}
        )
        
        self.table.setAlternatingRowColors(True)
        self.table.stock_activated.connect(self.stock_clicked.emit)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        layout.addWidget(self.table)

    def load_mock_data(self):
        self._is_mock_active = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        # Mock data: code, name, price, state, ma20_dist, limit_ups, position, first_seen, priority, dff, rank, dff2, dff3, relative_strength, resonance, reason
        mock_data = [
            ("600519", "贵州茅台", "1650.00", "回踩中", "-0.85%", "0", "0%", "🥈 盘中跟进 [10:15]", "75.5", "1.2", "15", "0.8", "0.5", "+0.35%", "同步整理", "日线缩量向20日均线靠拢"),
            ("002415", "海康威视", "32.40", "回踩企稳", "+0.15%", "1", "15%", "🔔 竞价先手 [09:25]", "92.0", "2.5", "8", "1.5", "1.0", "+1.25%", "逆市抗跌", "MA20强支撑处出现十字星K线"),
            ("300750", "宁德时代", "185.50", "持股中", "+3.20%", "0", "20%", "🥇 黄金早盘 [09:35]", "88.5", "4.2", "3", "2.8", "2.1", "+4.50%", "大盘共振", "回踩确认后阳线收回，多头排列"),
            ("600111", "北方稀土", "19.25", "持股中", "+4.85%", "2", "30%", "🥇 黄金早盘 [09:42]", "84.2", "5.5", "1", "3.5", "2.8", "+6.20%", "大盘共振", "放量冲出平台，强势上涨波段"),
            ("000001", "平安银行", "10.45", "已平仓", "-1.50%", "0", "0%", "🥈 盘中跟进 [11:10]", "45.0", "-1.0", "88", "-0.5", "-0.8", "-1.20%", "同步走弱", "跌破20日均线离场信号触发"),
            ("002594", "比亚迪", "245.00", "回踩企稳", "+0.05%", "0", "10%", "🔔 竞价先手 [09:20]", "95.5", "1.8", "12", "1.2", "0.9", "+0.80%", "同步整理", "前期大涨后回踩MA20量能极度萎缩")
        ]

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_stocks = fav_mgr.get_favorite_stocks()
        mock_data = sorted(mock_data, key=lambda x: (str(x[0]).strip() not in fav_stocks, str(x[0]).strip()))

        num_extra = len(self.extra_cols)
        self.table.setRowCount(len(mock_data))
        for row_idx, row_data in enumerate(mock_data):
            code = str(row_data[0]).strip()
            is_fav = code in fav_stocks
            
            # 补齐动态列与理由结构
            row_items = list(row_data[:15]) + ["--"] * num_extra + [row_data[15] if len(row_data) > 15 else ""]
            
            for col_idx, text in enumerate(row_items):
                if col_idx >= self.table.columnCount():
                    break
                if col_idx == 1 and is_fav:
                    if not str(text).startswith("⭐"):
                        text = f"⭐ {text}"
                
                item = NumericTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                if is_fav:
                    item.setBackground(COLOR_FAV_BG)
                
                # Dynamic cell styling based on state/pct
                if col_idx in (0, 1): # Code and Name
                    if is_fav:
                        item.setForeground(COLOR_GREEN)
                    else:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 3: # State column
                    if text == "回踩中":
                        item.setForeground(COLOR_WARN_Q)
                    elif text == "回踩企稳":
                        item.setForeground(COLOR_INFO_Q)
                        item.setFont(FONT_BOLD)
                    elif text == "持股中":
                        item.setForeground(COLOR_ACCENT_Q)
                        item.setFont(FONT_BOLD)
                    elif text == "已平仓":
                        item.setForeground(COLOR_DOWN_Q)
                elif col_idx == 4: # MA20 deviation
                    if str(text).startswith("+"):
                        item.setForeground(COLOR_UP_Q)
                    else:
                        item.setForeground(COLOR_DOWN_Q)
                elif col_idx == 6: # Position
                    if text != "0%":
                        item.setForeground(COLOR_ACCENT_Q)
                        item.setFont(FONT_BOLD)
                elif col_idx == 7: # 首次发现 (时段时间)
                    strategy_str = str(text)
                    if '🔔' in strategy_str or '竞价' in strategy_str:
                        item.setForeground(COLOR_BRIGHT_RED)
                        item.setFont(FONT_BOLD)
                    elif '🥇' in strategy_str or '黄金' in strategy_str:
                        item.setForeground(COLOR_GOLD)
                        item.setFont(FONT_BOLD)
                elif col_idx == 8: # 优先级评分
                    item.setForeground(COLOR_ACCENT_Q)
                    item.setFont(FONT_BOLD)
                elif col_idx in (9, 11, 12): # DFF, DFF2, DFF3
                    try:
                        val = float(text)
                        if val > 0:
                            item.setForeground(COLOR_UP_Q)
                        elif val < 0:
                            item.setForeground(COLOR_DOWN_Q)
                        else:
                            item.setForeground(COLOR_GRAY)
                    except ValueError:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 13: # 大盘偏离
                    try:
                        clean_text = text.replace("%", "").replace("+", "")
                        val = float(clean_text)
                        if val > 0:
                            item.setForeground(COLOR_UP_Q)
                            if val > 2.0:
                                item.setFont(FONT_BOLD)
                        elif val < 0:
                            item.setForeground(COLOR_DOWN_Q)
                        else:
                            item.setForeground(COLOR_GRAY)
                    except ValueError:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 14: # 大盘共振
                    if text == "逆市抗跌":
                        item.setForeground(COLOR_CORAL)
                        item.setFont(FONT_BOLD)
                    elif text == "大盘共振":
                        item.setForeground(COLOR_RED)
                        item.setFont(FONT_BOLD)
                    elif text == "同步走弱":
                        item.setForeground(COLOR_DOWN_Q)
                    else:
                        item.setForeground(COLOR_GRAY)
                elif 15 <= col_idx < 15 + num_extra:  # 动态自定义列
                    if str(text).startswith("+"):
                        item.setForeground(COLOR_UP_Q)
                    elif str(text).startswith("-"):
                        item.setForeground(COLOR_DOWN_Q)
                    else:
                        item.setForeground(COLOR_GRAY)
                else:
                    item.setForeground(COLOR_GRAY)
                
                self.table.setItem(row_idx, col_idx, item)
        auto_fit_columns_once(self.table, "ats_swing_table_state_v2", max_widths={self.table.columnCount() - 1: 350})
        self.table.setSortingEnabled(True)

    def update_data_list(self, data_list):
        if data_list is None:
            return

        current_extra = get_ats_extra_cols()
        if not hasattr(self, 'extra_cols') or self.extra_cols != current_extra:
            self.extra_cols = current_extra
            headers = get_ats_table_headers(self.extra_cols)
            if self.table.columnCount() != len(headers):
                self.table.setColumnCount(len(headers))
                self.table.setHorizontalHeaderLabels(headers)

        self._is_mock_active = False
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        
        if not data_list:
            if self.table.rowCount() > 0:
                self.table.setRowCount(0)
            return

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        fav_stocks = fav_mgr.get_favorite_stocks()
        sorted_list = sorted(data_list, key=lambda x: (str(x[0]).strip() not in fav_stocks, str(x[0]).strip()))
        
        if self.table.rowCount() != len(sorted_list):
            self.table.setRowCount(len(sorted_list))

        num_extra = len(self.extra_cols)

        for row_idx, row_data in enumerate(sorted_list):
            code = str(row_data[0]).strip()
            is_fav = code in fav_stocks
            
            for col_idx, text in enumerate(row_data):
                if col_idx >= self.table.columnCount():
                    break
                if col_idx == 1 and is_fav:
                    if not str(text).startswith("⭐"):
                        text = f"⭐ {text}"
                        
                # ⚡ [In-Place 复用] 优先复用已有 NumericTableWidgetItem，杜绝 20000+ 对象重复内存分配与 GC 卡顿
                item = self.table.item(row_idx, col_idx)
                if item is None:
                    item = NumericTableWidgetItem(str(text))
                    self.table.setItem(row_idx, col_idx, item)
                else:
                    item.setText(str(text))
                    item.setData(Qt.ItemDataRole.UserRole, str(text))

                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                if is_fav:
                    item.setBackground(COLOR_FAV_BG)
                else:
                    item.setBackground(COLOR_DEFAULT_BG)
                
                # Dynamic cell styling based on state/pct, preserving it for favorite stocks too
                if col_idx in (0, 1): # Code and Name
                    if is_fav:
                        item.setForeground(COLOR_GREEN)
                    else:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 3: # State column
                    if text == "回踩中":
                        item.setForeground(COLOR_WARN_Q)
                    elif text == "回踩企稳":
                        item.setForeground(COLOR_INFO_Q)
                        item.setFont(FONT_BOLD)
                    elif text == "持股中":
                        item.setForeground(COLOR_ACCENT_Q)
                        item.setFont(FONT_BOLD)
                    elif text == "已平仓":
                        item.setForeground(COLOR_DOWN_Q)
                elif col_idx == 4: # MA20 deviation
                    if str(text).startswith("+"):
                        item.setForeground(COLOR_UP_Q)
                    elif str(text).startswith("-"):
                        item.setForeground(COLOR_DOWN_Q)
                elif col_idx == 6: # Position
                    if str(text) != "0%":
                        item.setForeground(COLOR_ACCENT_Q)
                        item.setFont(FONT_BOLD)
                elif col_idx == 7: # 首次发现
                    strategy_str = str(text)
                    if '🔔' in strategy_str or '竞价' in strategy_str:
                        item.setForeground(COLOR_BRIGHT_RED)
                        item.setFont(FONT_BOLD)
                    elif '🥇' in strategy_str or '黄金' in strategy_str:
                        item.setForeground(COLOR_GOLD)
                        item.setFont(FONT_BOLD)
                elif col_idx == 8: # 优先级评分
                    item.setForeground(COLOR_ACCENT_Q)
                    item.setFont(FONT_BOLD)
                elif col_idx in (9, 11, 12): # DFF, DFF2, DFF3
                    try:
                        val = float(text)
                        if val > 0:
                            item.setForeground(COLOR_UP_Q)
                        elif val < 0:
                            item.setForeground(COLOR_DOWN_Q)
                        else:
                            item.setForeground(COLOR_GRAY)
                    except ValueError:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 13: # 大盘偏离 (Relative Strength)
                    try:
                        clean_text = text.replace("%", "").replace("+", "")
                        val = float(clean_text)
                        if val > 0:
                            item.setForeground(COLOR_UP_Q)
                            if val > 2.0:
                                item.setFont(FONT_BOLD)
                        elif val < 0:
                            item.setForeground(COLOR_DOWN_Q)
                        else:
                            item.setForeground(COLOR_GRAY)
                    except ValueError:
                        item.setForeground(COLOR_GRAY)
                elif col_idx == 14: # 大盘共振 (Resonance)
                    if text == "逆市抗跌":
                        item.setForeground(COLOR_CORAL)
                        item.setFont(FONT_BOLD)
                    elif text == "大盘共振":
                        item.setForeground(COLOR_RED)
                        item.setFont(FONT_BOLD)
                    elif text == "同步走弱":
                        item.setForeground(COLOR_DOWN_Q)
                    else:
                        item.setForeground(COLOR_GRAY)
                elif 15 <= col_idx < 15 + num_extra:  # 动态自定义列
                    if str(text).startswith("+"):
                        item.setForeground(COLOR_UP_Q)
                    elif str(text).startswith("-"):
                        item.setForeground(COLOR_DOWN_Q)
                    else:
                        item.setForeground(COLOR_GRAY)
                else:
                    item.setForeground(COLOR_GRAY)
                
        auto_fit_columns_once(self.table, "ats_swing_table_state_v2", max_widths={self.table.columnCount() - 1: 350})
        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)
        self._apply_favorite_filter()

    def _load_show_favorite_config(self):
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("ats_swing_show_favorite_option", True)
        except Exception:
            pass
        return True

    def _save_show_favorite_config(self, val):
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            data = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["ats_swing_show_favorite_option"] = bool(val)
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SwingStateTable] Save show_favorite config error: {e}")

    def _on_favorite_checkbox_changed(self, state):
        is_checked = (state == 2 or state is True or state == Qt.CheckState.Checked.value)
        self._save_show_favorite_config(is_checked)
        self.table.setUpdatesEnabled(True)
        self._apply_favorite_filter()

    def _get_parent_mw(self):
        """稳健获取持有 filtered_codes_set 的主窗口实例"""
        mw = getattr(self, 'main_window', None)
        if mw and hasattr(mw, 'filtered_codes_set'):
            return mw
        p = getattr(self, 'parent', lambda: None)()
        if p and hasattr(p, 'filtered_codes_set'):
            return p
        if hasattr(self, 'window'):
            w = self.window()
            if w and w is not self and hasattr(w, 'filtered_codes_set'):
                return w
        from PyQt6.QtWidgets import QApplication
        for tw in QApplication.topLevelWidgets():
            if hasattr(tw, 'filtered_codes_set'):
                return tw
        return None

    def _apply_favorite_filter(self):
        show_fav = getattr(self, 'chk_favorite_show', None) and self.chk_favorite_show.isChecked()
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        parent_mw = self._get_parent_mw()
        fset = None
        if getattr(self, 'filter_enabled', False) and parent_mw is not None:
            fset = getattr(parent_mw, 'filtered_codes_set', None)
            if fset is None:
                fset = set()

        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            code_str = code_item.text().strip() if code_item else ""
            name_str = name_item.text().strip() if name_item else ""

            is_fav = (code_str in fav_stocks) or ("⭐" in name_str) or ("★" in name_str)
            # 若关闭重点 (show_fav 为 False)，则隐藏重点关注标的，仅展示纯回调跟踪标的；若开启重点，则一同包含展示
            fav_hidden = (not show_fav and is_fav)
            filter_hidden = (fset is not None) and (code_str.zfill(6) not in fset)
            
            self.table.setRowHidden(row, fav_hidden or filter_hidden)

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
            first_seen = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
            priority = self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            dff = self.table.item(row, 9).text() if self.table.item(row, 9) else ""
            rank = self.table.item(row, 10).text() if self.table.item(row, 10) else ""
            dff2 = self.table.item(row, 11).text() if self.table.item(row, 11) else ""
            dff3 = self.table.item(row, 12).text() if self.table.item(row, 12) else ""
            rs = self.table.item(row, 13).text() if self.table.item(row, 13) else ""
            resonance = self.table.item(row, 14).text() if self.table.item(row, 14) else ""
            reason = self.table.item(row, 15).text() if self.table.item(row, 15) else ""
            context_info = {
                'position': '波段回调跟踪器 (Swing Pullback Tracker)',
                'reason': reason,
                'status': f"MA20偏离: {ma20_dist} | 连板数: {limit_ups} | 首次发现: {first_seen} | 优先级: {priority} | DFF: {dff} | Rank: {rank} | 大盘偏离: {rs} | 共振: {resonance}"
            }
            self.stock_double_clicked.emit(code, name, context_info)

    def refresh_favorites_display(self):
        """[0ms 轻量刷新] 原位刷新表格行重点关注 ⭐ 标识、背景色与行显显隐筛选"""
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            fav_stocks = set()

        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if not code_item or not name_item:
                continue
            code_str = code_item.text().strip()
            name_str = name_item.text().strip()
            is_fav = code_str in fav_stocks
            clean_name = name_str.replace("⭐ ", "").replace("⭐", "").replace("★ ", "").replace("★", "").strip()
            
            new_name = f"⭐ {clean_name}" if is_fav else clean_name
            if name_item.text() != new_name:
                name_item.setText(new_name)

            if is_fav:
                for col in range(self.table.columnCount()):
                    it = self.table.item(row, col)
                    if it:
                        it.setBackground(QColor("#1A2A1A"))
                code_item.setForeground(COLOR_GREEN)
                name_item.setForeground(COLOR_GREEN)
            else:
                for col in range(self.table.columnCount()):
                    it = self.table.item(row, col)
                    if it:
                        it.setData(Qt.ItemDataRole.BackgroundRole, None)
                code_item.setForeground(COLOR_GRAY)
                name_item.setForeground(COLOR_GRAY)

        self.table.setUpdatesEnabled(True)
        self._apply_favorite_filter()


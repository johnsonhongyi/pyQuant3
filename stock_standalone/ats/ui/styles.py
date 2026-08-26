# -*- coding: utf-8 -*-
"""
ATS v2 QSS Stylesheet and Palette definitions.
Provides a premium dark mode, glassmorphism-inspired theme for the Qt6 terminal.
"""

DARK_THEME_QSS = """
/* Global Style */
QWidget {
    background-color: #121214;
    color: #e2e2e5;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 9pt;
}

/* GroupBox styling */
QGroupBox {
    border: 1px solid #2e2e36;
    border-radius: 6px;
    margin-top: 1.2em;
    font-weight: bold;
    color: #aad4ff;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
}

/* Table and Tree Views */
QHeaderView::section {
    background-color: #1a1a1f;
    color: #aad4ff;
    padding: 2px 4px;
    border: 1px solid #2e2e36;
    font-weight: bold;
}
QTableWidget, QTreeView, QTreeWidget, QTableView {
    background-color: #18181c;
    alternate-background-color: #1f1f24;
    border: 1px solid #2e2e36;
    gridline-color: #2e2e36;
    selection-background-color: #1e334d;
}
QTableCornerButton::section {
    background-color: #1a1a1f;
    border: 1px solid #2e2e36;
}

/* TabWidget */
QTabWidget::pane {
    border: 1px solid #2e2e36;
    background-color: #18181c;
    top: -1px;
}
QTabBar::tab {
    background-color: #1a1a1f;
    color: #888899;
    border: 1px solid #2e2e36;
    border-bottom: none;
    padding: 6px 12px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #18181c;
    color: #00ff88;
    font-weight: bold;
    border-bottom: 2px solid #00ff88;
}
QTabBar::tab:hover {
    color: #ffffff;
    background-color: #23232a;
}

/* ScrollBar styling */
QScrollBar:vertical {
    border: none;
    background-color: #121214;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #2e2e36;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background-color: #3e3e4a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* PushButtons */
QPushButton {
    background-color: #222228;
    border: 1px solid #3e3e4a;
    color: #e2e2e5;
    padding: 5px 12px;
    border-radius: 4px;
    min-width: 60px;
}
QPushButton:hover {
    background-color: #2c2c35;
    border-color: #aad4ff;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #18181c;
}

/* ComboBox */
QComboBox {
    background-color: #1c1c22;
    border: 1px solid #3e3e4a;
    border-radius: 4px;
    padding: 4px;
    min-width: 80px;
}
QComboBox:hover {
    border-color: #aad4ff;
}
QComboBox QAbstractItemView {
    background-color: #1c1c22;
    border: 1px solid #3e3e4a;
    selection-background-color: #1e334d;
    selection-color: #ffffff;
}

/* CheckBox */
QCheckBox {
    spacing: 5px;
    color: #e2e2e5;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator:unchecked {
    border: 1px solid #3e3e4a;
    background-color: #1c1c22;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    border: 1px solid #00ff88;
    background-color: #1c1c22;
    image: url(dummy_checked); /* Fallback to styled marker if not found */
    border-radius: 3px;
}

/* ToolBar styling */
QToolBar {
    background-color: #1a1a1f;
    border-bottom: 1px solid #2e2e36;
    spacing: 6px;
    padding: 4px;
}

/* Status Bar */
QStatusBar {
    background-color: #1a1a1f;
    border-top: 1px solid #2e2e36;
    color: #ff9900;
    font-weight: bold;
}
"""

COLOR_UP = "#ff4444"       # A-Share Up (Red)
COLOR_DOWN = "#33cc5a"     # A-Share Down (Green)
COLOR_STABLE = "#8e8e93"   # Stable (Grey)
COLOR_ACCENT = "#00ff88"   # Cyber Green / Active
COLOR_WARN = "#ff9900"     # Warning (Orange)
COLOR_INFO = "#aad4ff"     # Light Blue / Cyan


import math
import re
import threading
from typing import Any, Optional, Union, List, Dict
CONFIG_FILE_LOCK = threading.RLock()

from PyQt6.QtWidgets import (
    QTableWidgetItem, QStyledItemDelegate, QStyleOptionViewItem, QStyle, 
    QApplication, QTabWidget, QToolButton, QTabBar
)
from PyQt6.QtCore import Qt, QModelIndex, QObject, QEvent
from PyQt6.QtGui import QColor, QPalette, QBrush

class ColorPreservingItemDelegate(QStyledItemDelegate):
    """
    量化金融终端专属 Delegate：
    当表格行被点击/选中 (Selected) 时，高亮背景正常呈现 (暗深蓝 #1e334d 或指定高亮背景)，
    但单元格自身的文字前景色 (红/绿/金/白/灰等) 100% 得到保留与保真渲染，绝不被白色/浅蓝覆盖！
    行为与左侧策略股票池 (QTreeWidget) 保持完全一致！
    """
    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex):
        super().initStyleOption(option, index)
        fg_data = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg_data is not None:
            brush = fg_data if isinstance(fg_data, QBrush) else QBrush(QColor(fg_data))
            # 无论是否处于 Selected / Focused 状态，文本前景色均锁定为 item 显式指定的颜色
            option.palette.setBrush(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText, brush)
            option.palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, brush)
            option.palette.setBrush(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, brush)
            option.palette.setBrush(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, brush)
            option.palette.setBrush(QPalette.ColorGroup.Normal, QPalette.ColorRole.Text, brush)
            option.palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, brush)


class NumericTableWidgetItem(QTableWidgetItem):
    """
    量化金融终端增强型支持数值、日期与文本混合排序的表格项：
    1. 自动感知表头排序方向 (AscendingOrder / DescendingOrder)；
    2. 支持重点关注 (is_pinned=True) 置顶特权：无论升序降序，置顶行永远稳居表格最前，且置顶区内部与非置顶区内部均严格按所选列排序；
    3. 无论升序还是降序，有数据的单元格永远优先展示，无数据占位符 ('--', '', NaN, None) 永远沉底在区域最下方；
    4. 优先基于 UserRole 高精度浮点值与原始类型比较 (O(1))，支持千分位、百分比、正负号等混合文本解析；
    5. 智能区分日期 (YYYY-MM-DD) 与分类文本 (如 '前5日(C)')，杜绝正则误提取数字。
    """
    def __init__(self, value: Any = None, is_pinned: bool = False, raw_val: Any = None, pin_rank: int = 999):
        self.is_pinned = is_pinned or (pin_rank < 999)
        self.pin_rank = pin_rank if pin_rank < 999 else (0 if is_pinned else 999)
        self._raw_value = raw_val if raw_val is not None else value
        
        display_str = "--" if value is None else str(value)
        super().__init__(display_str)
        
        if raw_val is not None:
            self.setData(Qt.ItemDataRole.UserRole, raw_val)
        elif isinstance(value, (int, float)) and not (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
            self.setData(Qt.ItemDataRole.UserRole, value)
            self._raw_value = value
        else:
            self._reparse_raw_value(display_str)

    def setText(self, atext: str):
        super().setText(atext)
        # 文本变更时重新解析并更新，杜绝复用 Item 时的历史脏数据残留
        self._reparse_raw_value(atext)

    def set_raw_value(self, raw_val: Any):
        """显式绑定真实数值/原始数据"""
        self._raw_value = raw_val
        if raw_val is not None and not (isinstance(raw_val, float) and (math.isnan(raw_val) or math.isinf(raw_val))):
            self.setData(Qt.ItemDataRole.UserRole, raw_val)
        else:
            self.setData(Qt.ItemDataRole.UserRole, None)

    def set_pin_status(self, is_pinned: bool, pin_rank: int = 999):
        """设置置顶状态与梯队"""
        self.is_pinned = is_pinned or (pin_rank < 999)
        self.pin_rank = pin_rank if pin_rank < 999 else (0 if is_pinned else 999)

    def _reparse_raw_value(self, text_val: str):
        t = str(text_val).strip()
        t_clean = t.replace('⭐', '').replace('★', '').replace('🐉', '').replace('🔥', '').replace('⚡', '').replace('❄️', '').replace('💎', '').replace('👑', '').strip()
        if not t_clean or t_clean in ("-", "--", "---", "null", "None", "nan", "NaN", "N/A", "未分类", "暂无") or t_clean.lower() in ("nan", "none", "null", "n/a"):
            self._raw_value = None
            self.setData(Qt.ItemDataRole.UserRole, None)
            return

        # 检查是否为日期格式 (YYYY-MM-DD 或 YYYY/MM/DD)
        if len(t_clean) == 10 and (t_clean[4] in ('-', '/') and t_clean[7] in ('-', '/')):
            self._raw_value = t_clean
            self.setData(Qt.ItemDataRole.UserRole, t_clean)
            return

        # 尝试提取纯数值 (支持百分比、千分位、正负号)
        clean_num_str = t_clean.replace(',', '').replace('%', '').replace('+', '').replace('￥', '').replace('$', '').strip()
        if '(' in clean_num_str and not any(k in t_clean for k in ("前5日", "首日", "次新", "待上市", "N", "C")):
            clean_num_str = clean_num_str.split('(')[0].strip()

        try:
            val = float(clean_num_str)
            if not (math.isnan(val) or math.isinf(val)) and abs(val) < 99999900:
                self._raw_value = val
                self.setData(Qt.ItemDataRole.UserRole, val)
                return
        except (ValueError, TypeError):
            pass

        self._raw_value = t_clean
        self.setData(Qt.ItemDataRole.UserRole, t_clean)

    def _is_empty(self) -> bool:
        """判定当前单元格是否为无数据/缺失值占位符"""
        t = self.text().strip()
        t_clean = t.replace('⭐', '').replace('★', '').replace('🐉', '').replace('🔥', '').replace('⚡', '').replace('❄️', '').replace('💎', '').replace('👑', '').strip()
        if not t_clean or t_clean in ("-", "--", "---", "null", "None", "N/A", "未分类", "暂无", "nan", "NaN") or t_clean.lower() in ("nan", "none", "null", "n/a"):
            return True

        u = self.data(Qt.ItemDataRole.UserRole)
        if u is not None and isinstance(u, (int, float)):
            if math.isnan(u) or math.isinf(u) or abs(u) >= 99999900:
                return True
            return False

        if hasattr(self, '_raw_value') and isinstance(self._raw_value, (int, float)):
            if math.isnan(self._raw_value) or math.isinf(self._raw_value) or abs(self._raw_value) >= 99999900:
                return True
            return False

        return False

    def _get_sort_val(self, target=None):
        """提取用于精准比较的数值或规范化文本"""
        item = target if target is not None else self
        if hasattr(item, '_is_empty') and item._is_empty():
            return None

        # 1. 优先使用 UserRole
        u = item.data(Qt.ItemDataRole.UserRole)
        if u is not None:
            if isinstance(u, (int, float)):
                if not (math.isnan(u) or math.isinf(u)) and abs(u) < 99999900:
                    return float(u)
                return None
            return u

        # 2. 检查 _raw_value
        if hasattr(item, '_raw_value') and item._raw_value is not None:
            rv = item._raw_value
            if isinstance(rv, (int, float)):
                if not (math.isnan(rv) or math.isinf(rv)) and abs(rv) < 99999900:
                    return float(rv)
                return None
            return rv

        # 3. 解析文本
        t = item.text().strip()
        if not t or t in ("-", "--", "---", "null", "None", "N/A", "未分类", "暂无") or t.lower() in ("nan", "none", "null", "n/a"):
            return None

        clean_t = t.replace(',', '').replace('%', '').replace('+', '').replace('￥', '').replace('$', '').strip()
        try:
            f = float(clean_t)
            if not (math.isnan(f) or math.isinf(f)) and abs(f) < 99999900:
                return f
        except Exception:
            pass

        return t

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)

        # 检查所属表格的表头排序方向
        is_descending = False
        t = self.tableWidget() or (other.tableWidget() if isinstance(other, QTableWidgetItem) else None)
        if t is not None:
            header = t.horizontalHeader()
            if header is not None and hasattr(header, 'sortIndicatorOrder'):
                is_descending = (header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder)

        pinned_self = getattr(self, 'is_pinned', False)
        pinned_other = getattr(other, 'is_pinned', False)

        # 1. 置顶梯队 pin_rank 控制 (小 rank 永远排在前面，0: 今日事件 > 1: 重点关注 > 999: 普通项)
        r1 = getattr(self, 'pin_rank', (0 if getattr(self, 'is_pinned', False) else 999))
        r2 = getattr(other, 'pin_rank', (0 if getattr(other, 'is_pinned', False) else 999))

        if r1 != r2:
            if is_descending:
                # 降序模式下：排在前面的项判定为“更大” => self < other 为 (r1 > r2)
                return r1 > r2
            else:
                # 升序模式下：排在前面的项判定为“更小” => self < other 为 (r1 < r2)
                return r1 < r2

        # 2. 空值/缺失值沉底控制 (空值永远沉底在各自区域的最下方)
        empty_self = self._is_empty() if hasattr(self, '_is_empty') else (not self.text().strip() or self.text().strip() in ("-", "--", "---", "null", "None", "N/A"))
        empty_other = other._is_empty() if hasattr(other, '_is_empty') else (not other.text().strip() or other.text().strip() in ("-", "--", "---", "null", "None", "N/A"))

        if empty_self != empty_other:
            if is_descending:
                # 降序模式下：空值判定为“更小” => empty < non_empty 为 True (沉底)
                return empty_self
            else:
                # 升序模式下：空值判定为“更大” => empty < non_empty 为 False (沉底)
                return not empty_self

        # 两者都是空值：保持文本字典序
        if empty_self and empty_other:
            return self.text() < other.text()

        # 3. 提取排序值进行比较
        v1 = self._get_sort_val(self)
        v2 = self._get_sort_val(other) if hasattr(other, '_get_sort_val') else self._get_sort_val(other)

        if v1 is not None and v2 is not None:
            # 类型一致比较 (数值 vs 数值, 字符串 vs 字符串)
            if type(v1) == type(v2):
                if v1 != v2:
                    return v1 < v2
                return self.text() < other.text()
            elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                if v1 != v2:
                    return v1 < v2
                return self.text() < other.text()
            else:
                # 混合类型：转为字符串比较
                s1 = str(v1)
                s2 = str(v2)
                if s1 != s2:
                    return s1 < s2
                return self.text() < other.text()

        return self.text() < other.text()


class PinnedNumericTableWidgetItem(NumericTableWidgetItem):
    """
    带优先置顶 (Pinned) 感知与 pin_rank 次序保护的 QTableWidgetItem。
    完全继承统一的 NumericTableWidgetItem 高性能多梯队排序引擎。
    """
    def __init__(self, text: Any, is_pinned: bool = False, pin_rank: int = 999, header_view=None, raw_val: Any = None):
        super().__init__(value=text, is_pinned=is_pinned, raw_val=raw_val, pin_rank=pin_rank)
        self.header_view = header_view


from PyQt6.QtCore import QObject, QEvent

class ShowEventFilter(QObject):
    def __init__(self, target, restore_callback=None):
        super().__init__(target)
        self.target = target
        self.restore_callback = restore_callback
        
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Paint):
            self.target._has_been_visible = True
            if self.restore_callback and not getattr(self.target, "_has_been_restored", False):
                self.target._has_been_restored = True
                self.restore_callback()
        return False


def auto_fit_columns_once(table_or_tree, config_key, max_widths=None):
    """
    Auto-adjusts columns to contents only once (when data is first loaded),
    but only if no saved state exists in window_config.json.
    """
    import os
    import json
    from sys_utils import get_app_root, get_conf_path
    from PyQt6.QtWidgets import QApplication
    
    # If we are currently changing font size, do not auto-adjust
    app = QApplication.instance()
    if app and getattr(app, "_is_updating_font", False):
        return
        
    # If already auto-adjusted in this session, skip
    if getattr(table_or_tree, "_auto_adjusted", False):
        return

    # If there is a saved configuration state for this table/tree, do not auto-adjust
    # because we want to respect the user's saved manual adjustments!
    config_path = get_conf_path("window_config.json", get_app_root())
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                if config_key in config_data:
                    table_or_tree._auto_adjusted = True
                    return
        except Exception:
            pass

    # Block signals to prevent triggering saveState while we auto-adjust
    header = table_or_tree.horizontalHeader() if hasattr(table_or_tree, "horizontalHeader") else table_or_tree.header()
    if header:
        header.blockSignals(True)

    # Perform auto-fit
    if hasattr(table_or_tree, "resizeColumnsToContents"):
        table_or_tree.resizeColumnsToContents()
    else:
        # For QTreeWidget, resizeColumnToContents for each column
        for col in range(table_or_tree.columnCount()):
            table_or_tree.resizeColumnToContents(col)

    # Apply digital/numeric column extra narrow spacing and maximum width limits
    col_count = table_or_tree.columnCount()
    for col in range(col_count):
        header_text = ""
        if hasattr(table_or_tree, "horizontalHeaderItem"):
            item = table_or_tree.horizontalHeaderItem(col)
            if item:
                header_text = item.text()
        elif hasattr(table_or_tree, "headerItem"):
            item = table_or_tree.headerItem()
            if item:
                header_text = item.text(col)

        is_numeric = any(k in header_text for k in ["代码", "价格", "价", "数量", "股", "额", "市值", "盈亏", "偏离", "比例", "占仓", "连板", "序号"])
        
        curr_w = table_or_tree.columnWidth(col)
        if is_numeric:
            # For numeric columns, make them tight: fit content tightly (reduce default padding)
            table_or_tree.setColumnWidth(col, max(55, curr_w - 6))
        
        # Apply max widths if specified
        if max_widths and col in max_widths:
            max_w = max_widths[col]
            if table_or_tree.columnWidth(col) > max_w:
                table_or_tree.setColumnWidth(col, max_w)

    if header:
        header.blockSignals(False)

    table_or_tree._auto_adjusted = True


def apply_dark_theme(widget):
    """为指定 Widget/Dialog 应用与 ATS 100% 绝对一致的极致暗黑高质主题 QSS"""
    if widget:
        widget.setStyleSheet(DARK_THEME_QSS)


def setup_header_persistence(table_or_tree, config_key, default_widths=None, max_widths=None):
    """
    为 QTableWidget 或 QTreeWidget 的水平 header 绑定跨会话自动保存与恢复状态，
    并实现列宽合理拉伸与最大宽度限制。
    """
    import json
    import os
    from PyQt6.QtCore import QByteArray, QTimer
    from PyQt6.QtWidgets import QHeaderView
    from sys_utils import get_app_root, get_conf_path

    # Global/Module level timer dictionary reference
    global _save_timers
    if '_save_timers' not in globals():
        globals()['_save_timers'] = {}

    header = table_or_tree.horizontalHeader() if hasattr(table_or_tree, "horizontalHeader") else table_or_tree.header()
    if not header:
        return

    # Enable interactive resizing for all columns
    col_count = table_or_tree.columnCount()
    header.blockSignals(True)
    for col in range(col_count):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
    header.blockSignals(False)

    table_or_tree._is_restoring_header = True

    def save_action():
        if getattr(table_or_tree, "_is_restoring_header", False) is True:
            return
        if getattr(table_or_tree, "_has_been_visible", False) is False:
            return
        try:
            state_hex = header.saveState().toHex().data().decode("utf-8")
            save_config_node(config_key, state_hex)
        except RuntimeError:
            pass
        except Exception as e:
            if "has been deleted" not in str(e):
                print(f"[HeaderPersistence] Failed to save state for {config_key}: {e}")

    def apply_max_width_limits():
        if max_widths:
            header.blockSignals(True)
            for col, max_w in max_widths.items():
                if col < col_count:
                    curr_w = table_or_tree.columnWidth(col)
                    if curr_w > max_w:
                        table_or_tree.setColumnWidth(col, max_w)
            header.blockSignals(False)

    def restore_action():
        table_or_tree._is_restoring_header = True
        restored = False
        try:
            state_hex = load_config_node(config_key)
            if state_hex and isinstance(state_hex, str):
                header.blockSignals(True)
                header.restoreState(QByteArray.fromHex(state_hex.encode("utf-8")))
                header.blockSignals(False)
                restored = True
        except Exception as e:
            print(f"[HeaderPersistence] Failed to restore state for {config_key}: {e}")

        # 无论是否恢复成功，强制把所有列设回 Interactive 拖拽模式，防止 restoreState 恢复了历史配置中其他非交互的 resizeMode
        header.blockSignals(True)
        for col in range(col_count):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.blockSignals(False)

        if not restored:
            if default_widths:
                header.blockSignals(True)
                if isinstance(default_widths, dict):
                    for col, width in default_widths.items():
                        col_idx = None
                        if isinstance(col, int):
                            col_idx = col
                        elif isinstance(col, str):
                            if col.isdigit():
                                col_idx = int(col)
                            else:
                                for i in range(col_count):
                                    item = table_or_tree.horizontalHeaderItem(i) if hasattr(table_or_tree, "horizontalHeaderItem") else None
                                    if item and item.text() == col:
                                        col_idx = i
                                        break
                        if col_idx is not None and col_idx < col_count:
                            table_or_tree.setColumnWidth(col_idx, width)
                elif isinstance(default_widths, list):
                    for col, width in enumerate(default_widths):
                        if col < col_count:
                            table_or_tree.setColumnWidth(col, width)
                header.blockSignals(False)

        apply_max_width_limits()
        table_or_tree._is_restoring_header = False

    table_or_tree.save_header_state = save_action
    table_or_tree.restore_header_state = restore_action

    table_or_tree._has_been_visible = table_or_tree.isVisible()
    table_or_tree._has_been_restored = False
    
    event_filter = ShowEventFilter(table_or_tree, restore_action)
    table_or_tree.installEventFilter(event_filter)
    table_or_tree._show_event_filter = event_filter

    if table_or_tree._has_been_visible:
        table_or_tree._has_been_restored = True
        restore_action()
    else:
        apply_max_width_limits()
        table_or_tree._is_restoring_header = False

    def on_section_resized(logical_index, old_size, new_size):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and getattr(app, "_is_updating_font", False):
            return
        # 若当前正处于初始化/恢复过程，强行剥离 sectionResized 的落盘响应，防止重置配置！
        if getattr(table_or_tree, "_is_restoring_header", False) is True:
            return

        table_or_tree._has_been_visible = True
        if max_widths and logical_index in max_widths:
            max_w = max_widths[logical_index]
            if new_size > max_w:
                header.blockSignals(True)
                table_or_tree.setColumnWidth(logical_index, max_w)
                header.blockSignals(False)

        old_timer = globals()['_save_timers'].get(config_key)
        if old_timer is not None:
            try:
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(old_timer):
                        old_timer.stop()
                except ImportError:
                    old_timer.stop()
            except RuntimeError:
                pass
            globals()['_save_timers'].pop(config_key, None)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(1000)
        timer.timeout.connect(save_action)
        globals()['_save_timers'][config_key] = timer
        timer.start()

    header.sectionResized.connect(on_section_resized)


    # Protect callback reference from garbage collection
    if not hasattr(table_or_tree, "_persistence_callbacks"):
        table_or_tree._persistence_callbacks = {}
    table_or_tree._persistence_callbacks[config_key] = on_section_resized


def parse_bool_config(val, default: bool = False) -> bool:
    """稳健解析各类配置值为布尔值 (支持 bool, str, int 等)"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    val_str = str(val).strip().lower()
    if val_str in ("true", "1", "yes", "on"):
        return True
    if val_str in ("false", "0", "no", "off", ""):
        return False
    return default


def load_config_node(key: str, default=None):
    """线程安全从 window_config.json 读取指定 key 的持久化数据，具备 Windows 文件并发重试退避"""
    import os
    import json
    import time
    from sys_utils import get_app_root, get_conf_path
    
    cfg_path = get_conf_path("window_config.json", get_app_root())
    
    for attempt in range(5):
        try:
            with CONFIG_FILE_LOCK:
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict) and key in data:
                        return data[key]
            return default
        except (PermissionError, OSError, json.JSONDecodeError):
            # 遇到 Windows 瞬时文件锁竞争或正在原子替换，微休眠退避后重试
            time.sleep(0.03 * (attempt + 1))
        except Exception as ex:
            if attempt == 4:
                print(f"[ConfigHelper] 读取节点 {key} 异常: {ex}")
            time.sleep(0.03)
    return default


def save_config_nodes(key_val_dict: dict) -> bool:
    """线程安全将多个 key-value 增量物理原子落盘保存至 window_config.json
    具备重试与防覆盖保护，绝不使用空字典覆盖已有物理配置，兼容 Windows 文件锁。
    """
    if not key_val_dict or not isinstance(key_val_dict, dict):
        return False

    import os
    import json
    import time
    import tempfile
    from sys_utils import get_app_root, get_conf_path

    cfg_path = get_conf_path("window_config.json", get_app_root())
    
    with CONFIG_FILE_LOCK:
        for attempt in range(5):
            data = {}
            file_existed_and_valid = False
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                            file_existed_and_valid = True
                except Exception:
                    time.sleep(0.03 * (attempt + 1))
                    continue
            else:
                file_existed_and_valid = True

            # 如果文件存在但读取解析失败，避免直接用 {} 抹掉整盘配置，在第 3 次重试失败前不盲目覆写
            if not file_existed_and_valid and os.path.exists(cfg_path) and os.path.getsize(cfg_path) > 0 and attempt < 3:
                time.sleep(0.03 * (attempt + 1))
                continue

            # 增量合并字典
            for k, v in key_val_dict.items():
                data[k] = v

            tmp_path = None
            try:
                temp_dir = os.path.dirname(cfg_path) or "."
                fd, tmp_path = tempfile.mkstemp(dir=temp_dir, prefix="win_cfg_", suffix=".tmp", text=True)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # Windows 下 os.replace 遇到并发读时重试
                replaced = False
                for rep_attempt in range(3):
                    try:
                        os.replace(tmp_path, cfg_path)
                        replaced = True
                        break
                    except (PermissionError, OSError):
                        time.sleep(0.03)
                if replaced:
                    return True
            except Exception:
                pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
            time.sleep(0.03 * (attempt + 1))

    print(f"[ConfigHelper] 警告: 写入节点 {list(key_val_dict.keys())} 失败")
    return False


def save_config_node(key: str, val) -> bool:
    """线程安全将指定 key 物理原子落盘保存至 window_config.json (基于 safe save_config_nodes)"""
    return save_config_nodes({key: val})


class TabDirectSwitchEventFilter(QObject):
    """
    当 QTabWidget 的 QTabBar 因空间狭小出现左右滚动箭头 (QToolButton) 或鼠标在 TabBar 上滚动时，
    直接在 Tab 之间切换页面，而不是仅仅微调滚动像素，极大提升用户体验。
    """
    def __init__(self, tab_widget: QTabWidget):
        super().__init__(tab_widget)
        self.tab_widget = tab_widget
        self._installed_buttons = set()
        tb = self.tab_widget.tabBar()
        if tb:
            tb.installEventFilter(self)
            self._scan_and_install_buttons()

    def _scan_and_install_buttons(self):
        tb = self.tab_widget.tabBar()
        if not tb:
            return
        from PyQt6.QtWidgets import QToolButton
        for btn in tb.findChildren(QToolButton):
            if btn not in self._installed_buttons:
                btn.installEventFilter(self)
                self._installed_buttons.add(btn)

    def eventFilter(self, obj, event):
        from PyQt6.QtWidgets import QToolButton, QTabBar
        from PyQt6.QtCore import QEvent, Qt
        
        # 1. 动态监听新生成的子按钮或尺寸变化
        if event.type() in (QEvent.Type.ChildAdded, QEvent.Type.Show, QEvent.Type.Resize):
            self._scan_and_install_buttons()

        # 2. 滚轮在 TabBar 上直接循环切页
        if isinstance(obj, QTabBar) and event.type() == QEvent.Type.Wheel:
            count = self.tab_widget.count()
            if count > 1:
                cur = self.tab_widget.currentIndex()
                if event.angleDelta().y() < 0:
                    self.tab_widget.setCurrentIndex((cur + 1) % count)
                else:
                    self.tab_widget.setCurrentIndex((cur - 1 + count) % count)
                return True

        # 3. 拦截 QToolButton 点击并直接切页
        if isinstance(obj, QToolButton) and event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            if event.type() == QEvent.Type.MouseButtonRelease:
                count = self.tab_widget.count()
                if count > 1:
                    cur = self.tab_widget.currentIndex()
                    arrow = obj.arrowType()
                    if arrow == Qt.ArrowType.LeftArrow:
                        self.tab_widget.setCurrentIndex((cur - 1 + count) % count)
                    elif arrow == Qt.ArrowType.RightArrow:
                        self.tab_widget.setCurrentIndex((cur + 1) % count)
                    else:
                        tb = self.tab_widget.tabBar()
                        btns = sorted([b for b in tb.findChildren(QToolButton) if b.isVisible()], key=lambda x: x.x())
                        if btns and obj == btns[0]:
                            self.tab_widget.setCurrentIndex((cur - 1 + count) % count)
                        else:
                            self.tab_widget.setCurrentIndex((cur + 1) % count)
            return True
            
        return super().eventFilter(obj, event)


def enable_tab_direct_switch(tab_widget: QTabWidget) -> TabDirectSwitchEventFilter:
    """为指定 QTabWidget 开启箭头点击与滚轮直接切换 Tab 的事件过滤器"""
    flt = TabDirectSwitchEventFilter(tab_widget)
    setattr(tab_widget, "_tab_direct_switch_filter", flt)
    return flt


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
QTableWidget, QTreeView, QTreeWidget {
    background-color: #18181c;
    alternate-background-color: #1f1f24;
    border: 1px solid #2e2e36;
    gridline-color: #2e2e36;
    selection-background-color: #2a3a4a;
    selection-color: #00ff88;
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
    selection-background-color: #2a3a4a;
    selection-color: #00ff88;
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


import threading
from typing import Any, Optional, Union, List, Dict
CONFIG_FILE_LOCK = threading.RLock()

from PyQt6.QtWidgets import QTableWidgetItem

class NumericTableWidgetItem(QTableWidgetItem):
    """
    增强型支持数值与文本混合排序的表格项：
    1. 自动感知表头排序方向 (AscendingOrder / DescendingOrder)；
    2. 无论升序还是降序，有数据的单元格永远优先展示（升序从小到大，降序从大到小），无数据占位符 ('--', '', NaN, None) 永远沉底在表格最下方；
    3. 支持 UserRole 高精度浮点值、千分位、百分比、正负号、括号后缀等混合文本的鲁棒解析。
    """
    def __init__(self, value: Any = None):
        self._raw_value = value
        if value is None:
            super().__init__("--")
        elif isinstance(value, (int, float)):
            super().__init__(str(value))
        else:
            super().__init__(str(value))
            try:
                text = str(value).replace(',', '').replace('%', '').replace('+', '').replace('￥', '').replace('$', '').strip()
                if '(' in text:
                    text = text.split('(')[0].strip()
                if text and text not in ("-", "--", "---", "null", "None", "nan", "N/A", "未分类", "暂无"):
                    self._raw_value = float(text)
            except (ValueError, TypeError):
                self._raw_value = value

    def _is_empty(self) -> bool:
        """判定当前单元格是否为无数据/缺失值占位符"""
        import math
        from PyQt6.QtCore import Qt
        u = self.data(Qt.ItemDataRole.UserRole)
        if u is not None:
            try:
                f = float(u)
                if not (math.isnan(f) or math.isinf(f)):
                    if abs(f) >= 99999900:  # 兼容历史极值占位符
                        return True
                    return False
            except (ValueError, TypeError):
                pass
        if hasattr(self, '_raw_value') and isinstance(self._raw_value, (int, float)):
            if not (math.isnan(self._raw_value) or math.isinf(self._raw_value)):
                if abs(self._raw_value) >= 99999900:
                    return True
                return False
        t = self.text().strip()
        if not t or t in ("-", "--", "---", "null", "None", "N/A", "未分类", "暂无") or t.lower() in ("nan", "none", "null"):
            return True
        return False

    def _get_numeric_value(self, item=None):
        """提取单元格的真实数值，若为纯文本或空值则返回 None"""
        import math, re
        from PyQt6.QtCore import Qt
        target = item if item is not None else self
        if hasattr(target, '_is_empty') and target._is_empty():
            return None

        # 1. 优先使用 UserRole
        u = target.data(Qt.ItemDataRole.UserRole)
        if u is not None:
            try:
                f = float(u)
                if not (math.isnan(f) or math.isinf(f)):
                    if abs(f) >= 99999900:
                        return None
                    return f
            except (ValueError, TypeError):
                pass

        # 2. 检查 _raw_value
        if hasattr(target, '_raw_value') and isinstance(target._raw_value, (int, float)):
            if not (math.isnan(target._raw_value) or math.isinf(target._raw_value)):
                if abs(target._raw_value) >= 99999900:
                    return None
                return float(target._raw_value)

        # 3. 解析文本
        t = target.text().strip()
        if not t or t in ("-", "--", "---", "null", "None", "N/A", "未分类", "暂无") or t.lower() in ("nan", "none", "null"):
            return None

        clean_t = t.replace(',', '').replace('%', '').replace('+', '').replace('￥', '').replace('$', '').replace('板', '').replace('分', '').strip()
        if '(' in clean_t:
            clean_t = clean_t.split('(')[0].strip()
        num_re = r'[-+]?\d*\.?\d+'
        m = re.search(num_re, clean_t)
        if m:
            try:
                v = float(m.group())
                if not (math.isnan(v) or math.isinf(v)):
                    if abs(v) >= 99999900:
                        return None
                    return v
            except Exception:
                pass
        return None

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)

        from PyQt6.QtCore import Qt

        # 检查所属表格的表头排序方向
        is_descending = False
        t = self.tableWidget() or (other.tableWidget() if isinstance(other, QTableWidgetItem) else None)
        if t is not None:
            header = t.horizontalHeader()
            if header is not None and hasattr(header, 'sortIndicatorOrder'):
                is_descending = (header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder)

        empty_self = self._is_empty() if hasattr(self, '_is_empty') else (not self.text().strip() or self.text().strip() in ("-", "--", "---", "null", "None", "N/A"))
        empty_other = other._is_empty() if hasattr(other, '_is_empty') else (not other.text().strip() or other.text().strip() in ("-", "--", "---", "null", "None", "N/A"))

        # 核心规则：有数据的单元格永远优先于无数据单元格（无数据永远沉底在最下方）
        if empty_self != empty_other:
            if is_descending:
                # 降序模式 (高到低)：有数据项必须大于无数据项 => self < other 返回 False (即 self 在 other 前面)
                return empty_self
            else:
                # 升序模式 (低到高)：有数据项必须小于无数据项 => self < other 返回 True (即 self 在 other 前面)
                return not empty_self

        # 两者都无数据：保持文本字典序
        if empty_self and empty_other:
            return self.text() < other.text()

        # 两者都有数据：优先进行高精度数值比较
        v1 = self._get_numeric_value()
        v2 = other._get_numeric_value() if hasattr(other, '_get_numeric_value') else self._get_numeric_value(other)

        if v1 is not None and v2 is not None:
            if v1 != v2:
                return v1 < v2
            return self.text() < other.text()

        # 其中之一或两者为非数值文本：按字符串字典序比较
        return self.text() < other.text()


class PinnedNumericTableWidgetItem(NumericTableWidgetItem):
    """
    带优先置顶 (Pinned) 感知与内部排序保护的 QTableWidgetItem。
    使得包含此 Item 的表格在开启 setSortingEnabled(True) 且 Header 触发排序时，
    置顶行 (is_pinned=True) 绝对永远排序停留在表格的最顶端 (Row 0, Row 1...)。
    """
    def __init__(self, text, is_pinned=False, pin_rank=999, header_view=None):
        super().__init__(text)
        self.is_pinned = is_pinned
        self.pin_rank = pin_rank
        self.header_view = header_view

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)

        other_pinned = getattr(other, 'is_pinned', False)
        other_rank = getattr(other, 'pin_rank', 999)

        # 检查所属 Header 的当前排序方向 (AscendingOrder 或 DescendingOrder)
        is_descending = False
        if self.header_view and hasattr(self.header_view, 'sortIndicatorOrder'):
            from PyQt6.QtCore import Qt
            is_descending = (self.header_view.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder)

        # 1. 一个置顶，一个普通
        if self.is_pinned != other_pinned:
            if is_descending:
                # 在降序模式下 (0号位最大)：置顶行必须 "大于" 普通行 (self > other => self < other 返回 False)
                return not self.is_pinned
            else:
                # 在升序模式下 (0号位最小)：置顶行必须 "小于" 普通行 (self < other => self < other 返回 True)
                return self.is_pinned

        # 2. 两个都是置顶行：按照 pin_rank (0 > 1 > 2...)
        if self.is_pinned and other_pinned:
            if is_descending:
                return self.pin_rank > other_rank
            else:
                return self.pin_rank < other_rank

        # 3. 两个都是普通行：调用 NumericTableWidgetItem 的标准数值/文本比较
        return super().__lt__(other)


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


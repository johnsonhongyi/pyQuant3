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
CONFIG_FILE_LOCK = threading.RLock()

from PyQt6.QtWidgets import QTableWidgetItem

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
            
        t1 = self.text().strip()
        t2 = other.text().strip()
        
        # Treat placeholders as empty, ensuring they always go to the bottom of the table
        is_empty1 = not t1 or t1 in ("-", "--", "nan", "NaN")
        is_empty2 = not t2 or t2 in ("-", "--", "nan", "NaN")
        
        if is_empty1 and is_empty2:
            return False
        if is_empty1:
            return False
        if is_empty2:
            return True
            
        import re
        # Clean commas (e.g. 100,000 -> 100000) and percentage signs/currency symbols
        clean_t1 = t1.replace(',', '').replace('%', '').replace('￥', '').replace('$', '')
        clean_t2 = t2.replace(',', '').replace('%', '').replace('￥', '').replace('$', '')
        
        # Regex to find the first numeric float/int (handles negative/positive signs)
        num_re = r'[-+]?\d*\.?\d+'
        m1 = re.search(num_re, clean_t1)
        m2 = re.search(num_re, clean_t2)
        
        if m1 and m2:
            try:
                v1 = float(m1.group())
                v2 = float(m2.group())
                if v1 != v2:
                    return v1 < v2
            except ValueError:
                pass
        return t1 < t2


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
    for col in range(col_count):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

    config_path = get_conf_path("window_config.json", get_app_root())

    def save_action():
        if getattr(table_or_tree, "_has_been_visible", False) is False:
            # Skip saving if the widget has never been shown/rendered in this session,
            # to prevent overwriting with default (uninitialized) column widths.
            return
        try:
            state_hex = header.saveState().toHex().data().decode("utf-8")
            with CONFIG_FILE_LOCK:
                config_data = {}
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                    except:
                        pass
                config_data[config_key] = state_hex
                tmp_path = config_path + f".tmp_{config_key}"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, config_path)
        except Exception as e:
            print(f"[HeaderPersistence] Failed to save state for {config_key}: {e}")

    table_or_tree.save_header_state = save_action

    def apply_max_width_limits():
        if max_widths:
            for col, max_w in max_widths.items():
                if col < col_count:
                    curr_w = table_or_tree.columnWidth(col)
                    if curr_w > max_w:
                        header.blockSignals(True)
                        table_or_tree.setColumnWidth(col, max_w)
                        header.blockSignals(False)

    def restore_action():
        restored = False
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    state_hex = config_data.get(config_key)
                    if state_hex:
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
                        if col < col_count:
                            table_or_tree.setColumnWidth(col, width)
                elif isinstance(default_widths, list):
                    for col, width in enumerate(default_widths):
                        if col < col_count:
                            table_or_tree.setColumnWidth(col, width)
                header.blockSignals(False)

        apply_max_width_limits()

    # Initialize _has_been_visible and _has_been_restored based on current visibility state
    table_or_tree._has_been_visible = table_or_tree.isVisible()
    table_or_tree._has_been_restored = False
    
    # Install event filter to set visible flag when shown/painted, and trigger restore
    event_filter = ShowEventFilter(table_or_tree, restore_action)
    table_or_tree.installEventFilter(event_filter)
    table_or_tree._show_event_filter = event_filter  # protect from GC

    # If it is already visible initially, restore immediately
    if table_or_tree._has_been_visible:
        table_or_tree._has_been_restored = True
        restore_action()
    else:
        # If not visible yet, still apply max width limits to default sizes initially
        apply_max_width_limits()

    def on_section_resized(logical_index, old_size, new_size):
        table_or_tree._has_been_visible = True
        if max_widths and logical_index in max_widths:
            max_w = max_widths[logical_index]
            if new_size > max_w:
                header.blockSignals(True)
                table_or_tree.setColumnWidth(logical_index, max_w)
                header.blockSignals(False)

        timer = globals()['_save_timers'].get(config_key)
        if timer is not None:
            timer.stop()

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

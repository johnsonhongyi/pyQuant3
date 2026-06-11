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
    padding: 5px;
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

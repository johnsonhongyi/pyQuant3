# -*- coding: utf-8 -*-
"""
BaseATSTableWidget - ATS Base Table Class
Abstracts common table features: column resizing persistence, up/down arrow keyboard linkage,
right-click context menu, and fast item population.
"""

import os
import json
import threading
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QMenu, QApplication
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QByteArray
from PyQt6.QtGui import QColor, QFont, QBrush, QAction
from ats.ui.styles import NumericTableWidgetItem, auto_fit_columns_once, setup_header_persistence, CONFIG_FILE_LOCK
from sys_utils import get_app_root, get_conf_path

class BaseATSTableWidget(QTableWidget):
    """
    ATS Base Table Widget.
    Encapsulates:
    - Interactive column adjustments & persistence (using QHeaderView state & window_config.json)
    - Row selection change linkage (keyboard Up/Down keys navigation)
    - Mouse click linkage
    - Right-click "Copy stock code" context menu
    - Custom NumericTableWidgetItem support for sorting
    """
    stock_activated = pyqtSignal(str, str) # code, name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_updating = False
        self._config_key = None
        self._max_widths = None
        
        # Default styling matching high-end dark theme
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Connect signals
        self.itemClicked.connect(self._on_item_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
    def setup_persistence(self, config_key, default_widths=None, max_widths=None):
        
        setup_header_persistence(
            self,
            config_key=config_key,
            default_widths=default_widths,
            max_widths=max_widths
        )

    def _get_code_name_cols(self):
        code_col = 0
        name_col = 1
        for col in range(self.columnCount()):
            item = self.horizontalHeaderItem(col)
            if item:
                text = item.text()
                if "代码" in text or "code" in text.lower():
                    code_col = col
                elif "名称" in text or "name" in text.lower():
                    name_col = col
        return code_col, name_col

    def _on_item_clicked(self, item):
        if item and not self._is_updating:
            self._trigger_linkage(item.row())

    def _on_selection_changed(self):
        if self._is_updating:
            return
        selected_items = self.selectedItems()
        if not selected_items:
            return
        row = selected_items[0].row()
        self._trigger_linkage(row)

    def _trigger_linkage(self, row):
        code_col, name_col = self._get_code_name_cols()
        code_item = self.item(row, code_col)
        name_item = self.item(row, name_col)
        if code_item and name_item:
            code = code_item.text().strip()
            name = name_item.text().strip()
            if code and code != "N/A":
                self.stock_activated.emit(code, name)

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_col, name_col = self._get_code_name_cols()
        code_item = self.item(row, code_col)
        name_item = self.item(row, name_col)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else ""
        
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
        
        copy_label = f"📋 复制股票代码 {code}"
        if name:
            copy_label += f" ({name})"
        copy_action = QAction(copy_label, self)
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(code))
        menu.addAction(copy_action)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text):
        try:
            QApplication.clipboard().setText(text)
        except Exception as e:
            print(f"[BaseATSTableWidget] Clipboard copy failed: {e}")

    def save_column_widths(self):
        if hasattr(self, 'save_header_state'):
            self.save_header_state()

    def set_cell_value(self, row, col, text, color=None, is_numeric=False, bold=False, align=Qt.AlignmentFlag.AlignCenter):
        if is_numeric:
            item = NumericTableWidgetItem(str(text))
        else:
            item = QTableWidgetItem(str(text))
            
        item.setTextAlignment(align)
        if color:
            item.setForeground(QBrush(QColor(color)))
        if bold:
            font = self.font()
            font.setBold(True)
            item.setFont(font)
        self.setItem(row, col, item)

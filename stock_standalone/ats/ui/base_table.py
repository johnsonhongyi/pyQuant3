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

def send_to_linkage(code, name=None, parent_widget=None):
    """
    发送到异动联动功能 (named pipe)
    """
    try:
        from data_utils import send_code_via_pipe
        import json
        import pandas as pd
        from JohnsonUtil import LoggerFactory
        local_logger = LoggerFactory.getLogger()
        
        # Clean stock code to digits
        stock_code = "".join(c for c in str(code) if c.isdigit())
        if not stock_code:
            return False
        stock_code = stock_code.zfill(6)
        
        # Fallbacks
        stock_name = name if name else ""
        high_val = "0.0"
        lastp1d_val = "0.0"
        percent_val = 0.0
        price_val = 0.0
        volume_val = 0
        
        # Try to find current_df
        current_df = None
        if parent_widget:
            if hasattr(parent_widget, "current_df") and parent_widget.current_df is not None:
                current_df = parent_widget.current_df
            elif hasattr(parent_widget, "table") and hasattr(parent_widget.table, "current_df") and parent_widget.table.current_df is not None:
                current_df = parent_widget.table.current_df
            else:
                win = parent_widget.window()
                if win and hasattr(win, "current_df") and win.current_df is not None:
                    current_df = win.current_df
                    
        if current_df is not None:
            try:
                if stock_code in current_df.index:
                    row = current_df.loc[stock_code]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    # Map fields safely
                    stock_name = str(row.get("name", stock_name))
                    high_val = str(row.get("high", "0.0"))
                    lastp1d_val = str(row.get("lastp1d", row.get("llastp", "0.0")))
                    percent_val = float(row.get("percent", row.get("dff", 0.0)))
                    price_val = float(row.get("close", row.get("now", row.get("buy", 0.0))))
                    volume_val = int(row.get("volume", row.get("vol", 0)))
            except Exception as e:
                local_logger.error(f"[send_to_linkage] current_df extraction error: {e}")
                
        stock_info = {
            "code": str(stock_code),
            "name": str(stock_name),
            "high": str(high_val),
            "lastp1d": str(lastp1d_val),
            "percent": float(percent_val),
            "price": float(price_val),
            "volume": int(volume_val)
        }
        payload = json.dumps(stock_info, ensure_ascii=False)
        send_code_via_pipe(payload, logger=local_logger)
        local_logger.info(f"推送异动联动: {stock_info}")
        return True
    except Exception as e:
        try:
            from JohnsonUtil import LoggerFactory
            LoggerFactory.getLogger().error(f"发送到异动联动出错: {e}")
        except Exception:
            print(f"发送到异动联动出错: {e}")
        return False


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
        # Cache column indices to avoid O(N) header scans on every click
        self._code_col_cached = 0
        self._name_col_cached = 1
        self._col_cache_valid = False
        # Track last emitted code to prevent double-fire from click+selection signals
        self._last_emitted_code = ""
        # Debounce timer: collapses rapid keyboard-repeat navigation into a single signal.
        # 20ms is imperceptible for single clicks but still merges key-repeat bursts.
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._linkage_timer.setInterval(20)  # 20ms — imperceptible for clicks, effective for key-repeat
        self._pending_linkage_row = -1
        self._linkage_timer.timeout.connect(self._fire_linkage_debounced)
        
        # Default styling matching high-end dark theme
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)  # ⚡ 开启 Shift 多选与 Ctrl 点选
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # 默认单元格禁止编辑
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Use only currentCellChanged (covers both mouse click and keyboard navigation)
        # This single signal replaces itemClicked + itemSelectionChanged (which caused double-fire lag)
        self.currentCellChanged.connect(self._on_current_cell_changed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
    def setup_persistence(self, config_key, default_widths=None, max_widths=None):
        
        setup_header_persistence(
            self,
            config_key=config_key,
            default_widths=default_widths,
            max_widths=max_widths
        )

    def get_selected_stock_pairs(self) -> list:
        """
        获取当前表格中用户选中的所有标的 [(code, name), ...]
        - 若用户按 Shift/Ctrl 多选了多行，返回所选多行；
        - 若用户未选择任何行，则返回表格中所有未隐藏的有效行。
        """
        code_col, name_col = self._get_code_name_cols()
        selected_rows = sorted(list(set(idx.row() for idx in self.selectedIndexes())))
        
        pairs = []
        if len(selected_rows) > 1:
            for r in selected_rows:
                if not self.isRowHidden(r):
                    it_c = self.item(r, code_col)
                    it_n = self.item(r, name_col)
                    c = it_c.text().strip() if it_c else ""
                    n = it_n.text().strip().replace("⭐ ", "").replace("🐉 ", "") if it_n else ""
                    if c:
                        pairs.append((c, n))
            if pairs:
                return pairs

        # 降级：未多选时，提取表格中当前全部可见行
        for r in range(self.rowCount()):
            if not self.isRowHidden(r):
                it_c = self.item(r, code_col)
                it_n = self.item(r, name_col)
                c = it_c.text().strip() if it_c else ""
                n = it_n.text().strip().replace("⭐ ", "").replace("🐉 ", "") if it_n else ""
                if c:
                    pairs.append((c, n))
        return pairs

    def _get_code_name_cols(self):
        """Return (code_col, name_col) with cache to avoid O(N) header scan on every interaction."""
        if self._col_cache_valid:
            return self._code_col_cached, self._name_col_cached
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
        self._code_col_cached = code_col
        self._name_col_cached = name_col
        self._col_cache_valid = True
        return code_col, name_col

    def setColumnCount(self, count):
        """Invalidate column cache when column count changes."""
        self._col_cache_valid = False
        super().setColumnCount(count)

    def setHorizontalHeaderLabels(self, labels):
        """Invalidate column cache when headers are reset."""
        self._col_cache_valid = False
        super().setHorizontalHeaderLabels(labels)

    def _on_current_cell_changed(self, currentRow, currentColumn, previousRow, previousColumn):
        """Single entry point for both mouse click and keyboard navigation."""
        if self._is_updating or currentRow < 0:
            return
        # Only re-queue if row actually changed
        if currentRow == self._pending_linkage_row:
            return
        self._pending_linkage_row = currentRow
        # Restart debounce timer to coalesce rapid navigation
        self._linkage_timer.start()

    def _fire_linkage_debounced(self):
        row = self._pending_linkage_row
        if row < 0 or self._is_updating:
            return
        code_col, name_col = self._get_code_name_cols()
        code_item = self.item(row, code_col)
        name_item = self.item(row, name_col)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            if code and code != "N/A" and code != self._last_emitted_code:
                self._last_emitted_code = code
                self.stock_activated.emit(code, name)

    def _trigger_linkage(self, row):
        """Legacy compatibility method – routes through the debounce path."""
        self._pending_linkage_row = row
        self._linkage_timer.start()

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
        
        # Clean code to handle prefixes like ⭐
        code_clean = "".join(c for c in code if c.isalnum())
        if not code_clean:
            return
            
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        from global_favorites import GlobalFavoriteManager
        
        fav_mgr = GlobalFavoriteManager()
        is_fav = code_clean in fav_mgr.get_favorite_stocks()
        
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
        
        copy_label = f"📋 复制股票代码 {code_clean}"
        if name:
            copy_label += f" ({name})"
        copy_action = QAction(copy_label, self)
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(code_clean))
        menu.addAction(copy_action)
        
        menu.addSeparator()
        
        # ⚡ 发送到异动联动
        linkage_action = QAction(f"⚡ 发送到异动联动 {code_clean}", self)
        linkage_action.triggered.connect(lambda: send_to_linkage(code_clean, name, self))
        menu.addAction(linkage_action)
        
        # 📈 使用 SBC 打开独立分时图
        sbc_action = QAction(f"📈 使用 SBC 打开独立分时图 ({code_clean})", self)
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code_clean)
        sbc_action.triggered.connect(_open_sbc)
        menu.addAction(sbc_action)

        menu.addSeparator()
        
        if is_fav:
            fav_action = QAction(f"❌ 取消重点关注 {code_clean}", self)
        else:
            fav_action = QAction(f"⭐ 设为重点关注 {code_clean}", self)
        fav_action.triggered.connect(lambda: self._toggle_favorite(code_clean))
        menu.addAction(fav_action)

        menu.addSeparator()

        # ✏️ 右键编辑单元格选项
        edit_action = QAction(f"✏️ 编辑当前单元格内容", self)
        edit_action.triggered.connect(lambda: self._edit_current_cell(item))
        menu.addAction(edit_action)

        # ↔️ 右键一键自适应全列宽选项
        fit_action = QAction("↔️ 一键自适应全列宽", self)
        fit_action.triggered.connect(self.auto_fit_columns)
        menu.addAction(fit_action)

        menu.exec(self.viewport().mapToGlobal(pos))

    def auto_fit_columns(self, min_col_width: int = 75, extra_padding: int = 18):
        """按列单元格真实文本长度自适应调整全列宽度"""
        self.resizeColumnsToContents()
        for col in range(self.columnCount()):
            w = self.columnWidth(col)
            self.setColumnWidth(col, max(w + extra_padding, min_col_width))
        if hasattr(self, 'save_header_state'):
            self.save_header_state()

    def _edit_current_cell(self, item):
        """右键弹出编辑当前单元格内容窗口并自适应列宽"""
        if not item:
            return
        from PyQt6.QtWidgets import QInputDialog
        current_text = item.text()
        new_text, ok = QInputDialog.getText(
            self,
            "✏️ 编辑单元格内容",
            f"修改第 {item.row()+1} 行第 {item.column()+1} 列内容:",
            text=current_text
        )
        if ok and new_text is not None:
            item.setText(new_text.strip())
            self.auto_fit_columns()

    def _toggle_favorite(self, code):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_stock(str(code).strip())
        except Exception as e:
            print(f"[BaseATSTable] Toggle favorite stock error: {e}")

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

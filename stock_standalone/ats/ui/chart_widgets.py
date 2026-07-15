# -*- coding: utf-8 -*-
"""
ATS Chart Widgets
Provides high-performance charts using pyqtgraph.
Includes:
- DistributionBarChart: Stock return distributions (-10% to +10%)
- EquityCurveChart: Backtest equity curve.
"""

import os
import json
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, 
    QPushButton, QFrame, QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QByteArray
from PyQt6.QtGui import QBrush, QColor
import pyqtgraph as pg
import numpy as np
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except:
        pass
    try:
        return float(val)
    except:
        return default


class DistributionDetailsDialog(QDialog, WindowMixin):
    """
    Detailed A-share stock list dialog for a specific return bucket in the distribution chart.
    Self-adapts window position, size, stays-on-top, and column widths.
    """
    code_clicked = pyqtSignal(str, str) # Emitted when double-clicked or selected (linkage)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("📊 涨跌分布个股明细")
        self.setMinimumWidth(650)
        self._is_updating = False
        
        # 1. Load stays-on-top parameter
        self.stays_on_top = self._load_stays_on_top()
        
        # 2. Window flags (Use Window type instead of Tool/Dialog so it can go behind parent)
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags &= ~Qt.WindowType.Tool
        flags |= Qt.WindowType.Window
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        
        # Load window position and size
        self.load_window_position_qt(self, "distribution_details_dialog", default_width=750, default_height=550)
        self._is_updating = True
        self.setStyleSheet("QDialog { background-color: #1a1e2b; color: #ffffff; }")
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # Header frame
        header_frame = QFrame()
        header_lay = QHBoxLayout(header_frame)
        header_lay.setContentsMargins(0, 0, 0, 0)
        
        self.header_label = QLabel("📊 涨跌分布个股明细 | 双击行联动")
        self.header_label.setStyleSheet("color: #00FFCC; font-size: 13px; font-weight: bold; padding-left: 5px;")
        header_lay.addWidget(self.header_label)
        
        header_lay.addStretch()
        
        # Stays on top checkbox
        self.chk_on_top = QCheckBox("置顶")
        self.chk_on_top.setStyleSheet("""
            QCheckBox { color: #00FFCC; font-size: 9pt; font-weight: bold; }
            QCheckBox::indicator { width: 12px; height: 12px; }
        """)
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.stateChanged.connect(self._on_stays_on_top_toggled)
        header_lay.addWidget(self.chk_on_top)
        header_lay.addSpacing(10)
        
        # DNA Audit button
        self.btn_dna_audit = QPushButton("🧬 DNA审计")
        self.btn_dna_audit.setFixedWidth(85)
        self.btn_dna_audit.setStyleSheet("""
            QPushButton { background: #333; color: #fff; border: 1px solid #555; border-radius: 3px; font-size: 8pt; font-weight: bold; height: 20px; }
            QPushButton:hover { background: #444; border-color: #00ff88; }
        """)
        self.btn_dna_audit.clicked.connect(self._run_dna_audit_selected)
        header_lay.addWidget(self.btn_dna_audit)
        
        layout.addWidget(header_frame)
        
        # Table
        self.cols = ["代码", "名称", "涨幅%", "现价", "量比", "DFF", "DFF2", "DFF3", "所属板块"]
        self.table = QTableWidget(0, len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_header.setFixedHeight(28)
        h_header.sortIndicatorChanged.connect(lambda: self.table.scrollToTop())
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d121f;
                color: #ffffff;
                gridline-color: #2a2d42;
                border: none;
            }
            QHeaderView {
                background-color: #1a1c2c;
                border: none;
            }
            QHeaderView::section {
                background-color: #1a1c2c;
                color: #888;
                padding: 4px;
                border: 0.5px solid #2a2d42;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #2a2d42;
                color: #00ff88;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 100);
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 100);
                min-width: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
        
        # Column widths default settings
        self.table.setColumnWidth(0, 70)   # 代码
        self.table.setColumnWidth(1, 80)   # 名称
        self.table.setColumnWidth(2, 75)   # 涨幅
        self.table.setColumnWidth(3, 65)   # 现价
        self.table.setColumnWidth(4, 65)   # 量比
        self.table.setColumnWidth(5, 60)   # DFF
        self.table.setColumnWidth(6, 60)   # DFF2
        self.table.setColumnWidth(7, 60)   # DFF3
        h_header.setStretchLastSection(True)
        
        # Setup column widths and persistence using setup_header_persistence
        from ats.ui.styles import setup_header_persistence
        default_widths = {
            0: 70,  # 代码
            1: 80,  # 名称
            2: 75,  # 涨幅
            3: 65,  # 现价
            4: 65,  # 量比
            5: 60,  # DFF
            6: 60,  # DFF2
            7: 60,  # DFF3
            8: 120  # 所属板块
        }
        setup_header_persistence(self.table, "distribution_details_header_v1", default_widths=default_widths)

        # Connect signals
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.currentItemChanged.connect(self._on_current_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        self.setLayout(layout)
        
        # End initialization lock protection
        QTimer.singleShot(200, lambda: setattr(self, '_is_updating', False))

    def _get_main_app(self):
        # Traverse up parents or check QApplication instance
        curr = self.parent()
        while curr:
            if hasattr(curr, 'link_stock') or hasattr(curr, 'on_stock_clicked'):
                return curr
            curr = curr.parent()
        
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if hasattr(widget, 'link_stock') or hasattr(widget, 'on_stock_clicked'):
                    return widget
        return None

    def _save_window_states(self) -> None:
        try:
            # Use WindowMixin's DPI-aware save method
            self.save_window_position_qt(self, "distribution_details_dialog")
            
            # Append stays_on_top
            config_file = WINDOW_CONFIG_FILE
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except:
                        pass
                if "distribution_details_dialog" not in data:
                    data["distribution_details_dialog"] = {}
                data["distribution_details_dialog"]["stays_on_top"] = self.stays_on_top
                
                tmp = config_file + f".tmp_dist_states_{id(self)}"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                os.replace(tmp, config_file)
        except Exception as e:
            print(f"[DistributionDetailsDialog] Error saving window states: {e}")

    def _load_stays_on_top(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        dialog_config = data.get("distribution_details_dialog", {})
                        if "stays_on_top" in dialog_config:
                            return dialog_config["stays_on_top"]
        except Exception:
            pass
        return False

    def _on_stays_on_top_toggled(self, state):
        self.stays_on_top = self.chk_on_top.isChecked()
        flags = self.windowFlags()
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def closeEvent(self, event):
        self._save_window_states()
        event.accept()

    def hideEvent(self, event):
        self._save_window_states()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.layout():
            self.layout().activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            self.layout().setGeometry(self.rect())

    def _link_current_row(self, row):
        if getattr(self, '_is_updating', False):
            return
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item:
            code = code_item.text()
            name = name_item.text()
            self.code_clicked.emit(code, name)
            
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'link_stock'):
                main_app.link_stock(code, name)

    def _on_item_clicked(self, item):
        if item:
            self._link_current_row(item.row())

    def _on_current_item_changed(self, current, previous):
        if current:
            self._link_current_row(current.row())

    def _on_item_double_clicked(self, item):
        if item:
            row = item.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                code = code_item.text()
                name = name_item.text()
                
                main_app = self._get_main_app()
                if main_app:
                    if hasattr(main_app, 'link_stock'):
                        main_app.link_stock(code, name)
                    if hasattr(main_app, 'on_stock_clicked'):
                        main_app.on_stock_clicked(code, name)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return
        
        row = item.row()
        raw_code = self.table.item(row, 0).text()
        code = "".join(c for c in raw_code if c.isalnum())
        name = self.table.item(row, 1).text()
        
        # Clean star prefix from name if present
        name_clean = name
        if name_clean.startswith("⭐ "):
            name_clean = name_clean[2:]
        elif name_clean.startswith("⭐"):
            name_clean = name_clean[1:]
            
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        from global_favorites import GlobalFavoriteManager
        
        fav_mgr = GlobalFavoriteManager()
        is_fav = code in fav_mgr.get_favorite_stocks()
        
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
        
        # Link action
        link_act = menu.addAction(f"⚡ 选中联动 ({code})")
        link_act.triggered.connect(lambda: self.code_clicked.emit(code, name_clean))
        
        menu.addSeparator()
        
        # Copy actions
        copy_code = menu.addAction("复制代码")
        copy_code.triggered.connect(lambda: QApplication.clipboard().setText(code))
        copy_name = menu.addAction("复制名称")
        copy_name.triggered.connect(lambda: QApplication.clipboard().setText(name_clean))
        
        menu.addSeparator()
        
        # Favorite action
        if is_fav:
            fav_act = menu.addAction(f"❌ 取消重点关注 {code}")
        else:
            fav_act = menu.addAction(f"⭐ 设为重点关注 {code}")
        fav_act.triggered.connect(lambda: self._toggle_favorite(row, code, name_clean))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_favorite(self, row, code, name_clean):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_stock(code)
            self.refresh_favorites_display()
        except Exception as e:
            print(f"[DistributionDetailsDialog] Toggle favorite error: {e}")

    def refresh_favorites_display(self):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_stocks = fav_mgr.get_favorite_stocks()
            
            self.table.setSortingEnabled(False)
            for row in range(self.table.rowCount()):
                code_item = self.table.item(row, 0)
                name_item = self.table.item(row, 1)
                if not code_item or not name_item:
                    continue
                raw_code = code_item.text()
                code = "".join(c for c in raw_code if c.isalnum())
                
                is_fav = code in fav_stocks
                
                # Update code foreground
                if is_fav:
                    code_item.setForeground(QBrush(QColor("#00FF88")))
                else:
                    code_item.setForeground(QBrush(QColor("#00ff00" if code.startswith(('60', '00')) else "#00bfff")))
                
                # Update name text & foreground
                raw_name = name_item.text()
                name_clean = raw_name
                if name_clean.startswith("⭐ "):
                    name_clean = name_clean[2:]
                elif name_clean.startswith("⭐"):
                    name_clean = name_clean[1:]
                
                new_name_text = f"⭐ {name_clean}" if is_fav else name_clean
                if raw_name != new_name_text:
                    name_item.setText(new_name_text)
                    
                if is_fav:
                    name_item.setForeground(QBrush(QColor("#00FF88")))
                else:
                    name_item.setForeground(QBrush(QColor("#ffffff")))
                
                # Update row backgrounds
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item:
                        if is_fav:
                            item.setBackground(QBrush(QColor("#1A2A1A")))
                        else:
                            item.setBackground(QBrush())
                            
            self.table.setSortingEnabled(True)
        except Exception as e:
            print(f"[DistributionDetailsDialog] Error refreshing favorites display: {e}")


    def _run_dna_audit_selected(self):
        items = []
        for r in range(self.table.rowCount()):
            c_it = self.table.item(r, 0)
            n_it = self.table.item(r, 1)
            if c_it and n_it:
                items.append((c_it.text(), n_it.text()))
        if not items: return
        
        sel_rows = sorted(list(set(i.row() for i in self.table.selectedItems())))
        target_items = []
        if len(sel_rows) > 1:
            for r in sel_rows[:50]:
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            for r in range(start, min(start + 20, self.table.rowCount())):
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
        else:
            for r in range(min(20, self.table.rowCount())):
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
                
        code_to_name = {c: n for c, n in target_items if c and c != "N/A"}
        if code_to_name:
            main_app = getattr(self.parent(), 'parent_app', None)
            if not main_app: main_app = getattr(self.window(), 'parent_app', None)
            if not main_app: main_app = getattr(QApplication.instance(), 'parent_app', None)
            
            if main_app and hasattr(main_app, '_run_dna_audit_batch'):
                if hasattr(main_app, 'tk_dispatch_queue'):
                    _cn = dict(code_to_name)
                    main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
                else:
                    main_app._run_dna_audit_batch(code_to_name)
            else:
                if hasattr(self.window(), '_run_dna_audit_batch'):
                    self.window()._run_dna_audit_batch(code_to_name)
                else:
                    print("No access to main monitor app for DNA audit:", code_to_name)

    def update_data(self, df_filtered):
        self._is_updating = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        try:
            if df_filtered is None or df_filtered.empty:
                return
                
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_stocks = fav_mgr.get_favorite_stocks()
            
            self.table.setRowCount(len(df_filtered))
            for i, (code, row) in enumerate(df_filtered.iterrows()):
                name = str(row.get('name', '--'))
                pct = safe_float(row.get('percent', 0.0))
                price = safe_float(row.get('close', row.get('trade', 0.0)))
                ratio = safe_float(row.get('volume_ratio', row.get('ratio', 1.0)))
                dff = safe_float(row.get('dff', 0.0))
                dff2 = safe_float(row.get('dff2', 0.0))
                dff3 = safe_float(row.get('dff3', 0.0))
                sector = str(row.get('category', row.get('sector', '--')))
                
                is_fav = code in fav_stocks
                if is_fav:
                    if not name.startswith("⭐"):
                        name = f"⭐ {name}"
                
                # 0: 代码
                c_item = QTableWidgetItem(code)
                if is_fav:
                    c_item.setForeground(QBrush(QColor("#00FF88")))
                else:
                    c_item.setForeground(QBrush(QColor("#00ff00" if code.startswith(('60', '00')) else "#00bfff")))
                c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 0, c_item)
                
                # 1: 名称
                n_item = QTableWidgetItem(name)
                n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_fav:
                    n_item.setForeground(QBrush(QColor("#00FF88")))
                self.table.setItem(i, 1, n_item)
                
                # 2: 涨幅%
                ch_item = NumericTableWidgetItem(pct)
                ch_item.setText(f"{pct:+.2f}%")
                ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if pct > 0: ch_item.setForeground(QBrush(QColor("#ff4444")))
                elif pct < 0: ch_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 2, ch_item)
                
                # 3: 现价
                p_item = NumericTableWidgetItem(price)
                p_item.setText(f"{price:.2f}")
                p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                p_item.setForeground(QBrush(QColor("#ffffff")))
                self.table.setItem(i, 3, p_item)
                
                # 4: 量比
                r_item = NumericTableWidgetItem(ratio)
                r_item.setText(f"{ratio:.2f}")
                r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                r_item.setForeground(QBrush(QColor("#ffff00")))
                self.table.setItem(i, 4, r_item)
                
                # 5: DFF
                d_item = NumericTableWidgetItem(dff)
                d_item.setText(f"{dff:+.2f}")
                d_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if dff > 0: d_item.setForeground(QBrush(QColor("#ff4444")))
                elif dff < 0: d_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 5, d_item)
                
                # 6: DFF2
                d2_item = NumericTableWidgetItem(dff2)
                d2_item.setText(f"{dff2:+.2f}")
                d2_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if dff2 > 0: d2_item.setForeground(QBrush(QColor("#ff4444")))
                elif dff2 < 0: d2_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 6, d2_item)
                
                # 7: DFF3
                d3_item = NumericTableWidgetItem(dff3)
                d3_item.setText(f"{dff3:+.2f}")
                d3_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if dff3 > 0: d3_item.setForeground(QBrush(QColor("#ff4444")))
                elif dff3 < 0: d3_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 7, d3_item)
                
                # 8: 所属板块
                sec_item = QTableWidgetItem(sector)
                sec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 8, sec_item)
                
                if is_fav:
                    for item in (c_item, n_item, ch_item, p_item, r_item, d_item, d2_item, d3_item, sec_item):
                        item.setBackground(QBrush(QColor("#1A2A1A")))
                
        finally:
            # Auto fit columns once if no custom widths saved
            from ats.ui.styles import auto_fit_columns_once
            auto_fit_columns_once(self.table, "distribution_details_header_v1")
            
            self.table.setSortingEnabled(True)
            self._is_updating = False


class DistributionBarChart(QWidget):
    """
    Shows stock return distributions (e.g., A-Share stock count by return buckets).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_df = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        self.title = QLabel("📊 今日全市场个股涨跌幅分布 (Distribution)")
        self.title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 11pt;")
        layout.addWidget(self.title)

        # 增加一个显示市场温度与统计信息的 label
        self.stats_label = QLabel("🔥 市场温度: -- | 🔺 上涨: -- 家 | 🔻 下跌: -- 家 | 平盘: -- 家 | 均幅: --%")
        self.stats_label.setStyleSheet("color: #e2e2e5; font-size: 9.5pt; font-weight: bold;")
        self.stats_label.setWordWrap(True) # 启用自动换行，防止因为单行太宽导致窗口无法收缩
        layout.addWidget(self.stats_label)

        # Create Plot Widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#121214")
        self.plot_widget.showGrid(x=False, y=True, alpha=0.2)
        
        # Disable interactive scaling on X axis to make it static if needed
        self.plot_widget.setMouseEnabled(x=False, y=True)
        layout.addWidget(self.plot_widget)

        # Mock distribution data: A-share returns buckets
        # Buckets: <-8%, -8%~-6%, -6%~-4%, -4%~-2%, -2%~0%, 0%~2%, 2%~4%, 4%~6%, 6%~8%, >8%
        self.x_labels = ["<-8%", "-7%", "-5%", "-3%", "-1%", "+1%", "+3%", "+5%", "+7%", ">+8%"]
        x = np.arange(len(self.x_labels))
        y = np.array([25, 45, 120, 310, 890, 1150, 480, 210, 95, 62])  # mock stock count
        self.current_counts = list(y)

        # Set custom x-axis ticks
        ax = self.plot_widget.getAxis('bottom')
        ticks = [list(zip(x, self.x_labels))]
        ax.setTicks(ticks)

        # Color the bars based on direction
        # Negative buckets get green, positive get red
        colors = []
        for val in x:
            if val < 5:  # negative buckets
                colors.append('#33cc5a') # Green
            else:
                colors.append('#ff4444') # Red

        # Draw bars
        bg = pg.BarGraphItem(x=x, height=y, width=0.6, brushes=colors, pens=[pg.mkPen(c) for c in colors])
        self.plot_widget.addItem(bg)
        
        # Add labels and styling
        self.plot_widget.setLabel('left', '股数')
        self.plot_widget.setYRange(0, 1300)

        # 绑定鼠标移动事件与多层双击事件以防止被 ViewBox 拦截
        self.plot_widget.scene().sigMouseMoved.connect(self.on_mouse_moved)
        self.plot_widget.mouseDoubleClickEvent = lambda evt: self.on_plot_double_clicked(evt)
        if self.plot_widget.viewport():
            self.plot_widget.viewport().mouseDoubleClickEvent = lambda evt: self.on_plot_double_clicked(evt)
            
        vb = self.plot_widget.plotItem.vb
        if vb:
            orig_double_click = vb.mouseDoubleClickEvent
            def new_double_click(evt):
                try:
                    scene_pos = evt.scenePos()
                    mouse_point = vb.mapSceneToView(scene_pos)
                    x_val = mouse_point.x()
                    idx = int(round(x_val))
                    if 0 <= idx < 10 and abs(x_val - idx) <= 0.35:
                        self.open_details_dialog(idx)
                        evt.accept()
                        return
                except Exception as e:
                    print(f"[DistributionBarChart] Double click intercept error: {e}")
                if orig_double_click:
                    orig_double_click(evt)
            vb.mouseDoubleClickEvent = new_double_click

    def on_mouse_moved(self, evt):
        try:
            pos = evt
            if self.plot_widget.sceneBoundingRect().contains(pos):
                mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
                x_val = mouse_point.x()
                
                # 判断在哪个柱子 (x 范围 0 到 9，因为 width=0.6，所以柱子区间是 [idx-0.35, idx+0.35])
                idx = int(round(x_val))
                if 0 <= idx < 10 and hasattr(self, 'current_counts') and self.current_counts:
                    if abs(x_val - idx) <= 0.35:
                        count = self.current_counts[idx]
                        
                        bucket_desc = [
                            "跌幅超 8% (<-8%)",
                            "跌幅 6% 至 8% (-8% ~ -6%)",
                            "跌幅 4% 至 6% (-6% ~ -4%)",
                            "跌幅 2% 至 4% (-4% ~ -2%)",
                            "跌幅 0% 至 2% (-2% ~ 0%)",
                            "涨幅 0% 至 2% (0% ~ +2%)",
                            "涨幅 2% 至 4% (+2% ~ +4%)",
                            "涨幅 4% 至 6% (+4% ~ +6%)",
                            "涨幅 6% 至 8% (+6% ~ +8%)",
                            "涨幅超 8% (>+8%)"
                        ]
                        
                        desc = bucket_desc[idx]
                        total = sum(self.current_counts)
                        pct_str = f"{(count / total * 100.0):.1f}%" if total > 0 else "0.0%"
                        
                        from PyQt6.QtWidgets import QToolTip
                        global_pos = self.plot_widget.mapToGlobal(pos.toPoint())
                        
                        tip_text = f"📊 {desc}\n只数: {count} 只\n全市场占比: {pct_str}"
                        QToolTip.showText(global_pos, tip_text, self.plot_widget)
                        return
            
            from PyQt6.QtWidgets import QToolTip
            QToolTip.hideText()
        except Exception:
            pass

    def on_plot_double_clicked(self, evt):
        try:
            if hasattr(evt, 'scenePos'):
                scene_pos = evt.scenePos()
            else:
                pos_f = evt.position() if hasattr(evt, 'position') else evt.pos()
                pos = pos_f.toPoint() if hasattr(pos_f, 'toPoint') else pos_f
                scene_pos = self.plot_widget.mapToScene(pos)
                
            mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(scene_pos)
            x_val = mouse_point.x()
            
            # Check which column was double-clicked
            idx = int(round(x_val))
            if 0 <= idx < 10:
                if abs(x_val - idx) <= 0.35:
                    self.open_details_dialog(idx)
                    evt.accept()
        except Exception as e:
            print(f"[DistributionBarChart] Double click error: {e}")

    def open_details_dialog(self, idx):
        if not hasattr(self, 'current_df') or self.current_df is None or self.current_df.empty:
            return
        
        df_filtered = self._filter_df_by_bucket(self.current_df, idx)
        if df_filtered is None or df_filtered.empty:
            return
            
        # parent=None: allows dialog to go behind the main window (OS window manager
        # always keeps child windows in front of their parent on Windows).
        # We keep a strong Python reference in _active_dialogs to prevent GC deletion,
        # and monitor main window destroyed signal to close dialogs when ATS exits.
        dialog = DistributionDetailsDialog(None)
        dialog.update_data(df_filtered)
        
        bucket_names = [
            "跌幅超 8% (<-8%)",
            "跌幅 6% 至 8% (-8% ~ -6%)",
            "跌幅 4% 至 6% (-6% ~ -4%)",
            "跌幅 2% 至 4% (-4% ~ -2%)",
            "跌幅 0% 至 2% (-2% ~ 0%)",
            "涨幅 0% 至 2% (0% ~ +2%)",
            "涨幅 2% 至 4% (+2% ~ +4%)",
            "涨幅 4% 至 6% (+4% ~ +6%)",
            "涨幅 6% 至 8% (+6% ~ +8%)",
            "涨幅超 8% (>+8%)"
        ]
        title = f"📊 涨跌分布个股明细 | {bucket_names[idx]} (共 {len(df_filtered)} 只)"
        dialog.setWindowTitle(title)
        dialog.header_label.setText(f"📊 涨跌分布 ({bucket_names[idx]}) | 双击行切换/联动")
        
        dialog.show()
        
        if not hasattr(self, '_active_dialogs'):
            self._active_dialogs = []
            # Connect to main window's destroyed signal (only once) so that when
            # ATS main window closes, all orphaned detail dialogs are also closed.
            main_win = self.window()
            if main_win and main_win is not self:
                try:
                    main_win.destroyed.connect(self._close_all_dialogs)
                except Exception:
                    pass
            
        # Clean up any deleted/closed dialogs safely
        from PyQt6.sip import isdeleted
        active_dialogs = []
        for d in self._active_dialogs:
            try:
                if not isdeleted(d) and d.isVisible():
                    active_dialogs.append(d)
            except Exception:
                pass
        self._active_dialogs = active_dialogs
        self._active_dialogs.append(dialog)

    def _close_all_dialogs(self):
        """Close all open detail dialogs (called when main window is destroyed)."""
        from PyQt6.sip import isdeleted
        for d in getattr(self, '_active_dialogs', []):
            try:
                if not isdeleted(d):
                    d.close()
            except Exception:
                pass
        self._active_dialogs = []

    def _filter_df_by_bucket(self, df, idx):
        if df is None or df.empty or 'percent' not in df.columns:
            return None
        pcts = df['percent']
        if idx == 0:
            return df[pcts <= -8]
        elif idx == 1:
            return df[(pcts > -8) & (pcts <= -6)]
        elif idx == 2:
            return df[(pcts > -6) & (pcts <= -4)]
        elif idx == 3:
            return df[(pcts > -4) & (pcts <= -2)]
        elif idx == 4:
            return df[(pcts > -2) & (pcts <= 0)]
        elif idx == 5:
            return df[(pcts > 0) & (pcts <= 2)]
        elif idx == 6:
            return df[(pcts > 2) & (pcts <= 4)]
        elif idx == 7:
            return df[(pcts > 4) & (pcts <= 6)]
        elif idx == 8:
            return df[(pcts > 6) & (pcts <= 8)]
        elif idx == 9:
            return df[pcts > 8]
        return None

    def update_data(self, bucket_counts, stats_dict=None, df_all=None):
        """
        Expects a list of 10 values representing the counts for each bucket.
        """
        self.current_df = df_all
        if len(bucket_counts) != 10:
            return
        self.current_counts = list(bucket_counts)
        self.plot_widget.clear()
        x = np.arange(10)
        y = np.array(bucket_counts)
        
        # 重新设置 x 轴以防 PlotWidget.clear() 误清
        ax = self.plot_widget.getAxis('bottom')
        ticks = [list(zip(x, self.x_labels))]
        ax.setTicks(ticks)
        
        colors = []
        for val in x:
            if val < 5:
                colors.append('#33cc5a')
            else:
                colors.append('#ff4444')

        bg = pg.BarGraphItem(x=x, height=y, width=0.6, brushes=colors, pens=[pg.mkPen(c) for c in colors])
        self.plot_widget.addItem(bg)
        self.plot_widget.setYRange(0, max(bucket_counts) * 1.1)

        # 刷新统计与温度
        if stats_dict:
            temp = stats_dict.get("temp", 0.0)
            up = stats_dict.get("up", 0)
            down = stats_dict.get("down", 0)
            flat = stats_dict.get("flat", 0)
            avg = stats_dict.get("avg", 0.0)
            self.stats_label.setText(
                f"🔥 市场温度: {temp:.1f}℃ | 🔺 上涨: {up} 家 | 🔻 下跌: {down} 家 | 平盘: {flat} 家 | 均幅: {avg:+.2f}%"
            )


class EquityCurveChart(QWidget):
    """
    Plots cumulative returns / equity curves.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        title = QLabel("📈 策略收益率曲线 (Cumulative Returns)")
        title.setStyleSheet("font-weight: bold; color: #aad4ff; font-size: 11pt;")
        layout.addWidget(title)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#121214")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.plot_widget)

        # Draw mock equity curve
        self.draw_mock_curve()

    def draw_mock_curve(self):
        self.plot_widget.clear()
        
        # Cumulative strategy equity vs benchmark (e.g. CSI 300)
        days = 60
        x = np.arange(days)
        
        # Random walk for strategy (drift upward)
        np.random.seed(42)
        strat_returns = np.random.normal(0.0015, 0.012, days)
        strat_equity = np.cumprod(1 + strat_returns) * 100
        
        # Random walk for benchmark (drift sideways)
        bench_returns = np.random.normal(0.0002, 0.014, days)
        bench_equity = np.cumprod(1 + bench_returns) * 100

        # Plot curves
        self.strat_line = self.plot_widget.plot(x, strat_equity, pen=pg.mkPen('#00ff88', width=2.5), name="ATS 自治策略")
        self.bench_line = self.plot_widget.plot(x, bench_equity, pen=pg.mkPen('#8e8e93', width=1.5, style=Qt.PenStyle.DashLine), name="沪深300")
        
        self.plot_widget.setLabel('left', '资产净值', units='元')
        self.plot_widget.setLabel('bottom', '交易日数')
        
        # Add legend
        self.legend = self.plot_widget.addLegend(offset=(20, 20))
        self.legend.addItem(self.strat_line, "ATS 自治策略")
        self.legend.addItem(self.bench_line, "沪深300指数")

    def update_curve(self, x, strat_equity, bench_equity=None):
        self.plot_widget.clear()
        
        # Safely re-create legend
        try:
            self.plot_widget.legend.close()
        except Exception:
            pass
            
        self.legend = self.plot_widget.addLegend(offset=(20, 20))
        
        self.strat_line = self.plot_widget.plot(x, strat_equity, pen=pg.mkPen('#00ff88', width=2.5))
        self.legend.addItem(self.strat_line, "ATS 自治策略")
        
        if bench_equity is not None:
            self.bench_line = self.plot_widget.plot(x, bench_equity, pen=pg.mkPen('#8e8e93', width=1.5, style=Qt.PenStyle.DashLine))
            self.legend.addItem(self.bench_line, "沪深300")

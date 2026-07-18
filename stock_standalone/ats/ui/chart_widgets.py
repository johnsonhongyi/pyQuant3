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
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QByteArray, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QRect
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
    
    def __init__(self, bucket_idx=0, parent=None):
        super().__init__(parent)
        self.bucket_idx = bucket_idx
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
        self.load_window_position_qt(self, f"distribution_details_dialog_{bucket_idx}", default_width=750, default_height=550)
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
        
        # 3. 磁吸与隐藏状态初始化
        self.anchor_edge = None
        self.is_hidden_state = False
        self.normal_geometry = None
        self.hover_ticks = 0
        self.leave_ticks = 0
        self._in_snap_action = False
        self.anim_group = None
        self._is_dragging = False
        self._last_show_time = 0.0
        self._has_hovered_since_show = False
        self._is_auto_popping = False
        
        # 悬停与离开监控定时器
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)
        self.hover_timer.start()
        
        # 拖拽结束防抖定时器
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(200)
        self.snap_timer.timeout.connect(self._detect_and_snap)

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

    def _save_window_states(self, is_open=None) -> None:
        try:
            scale = self._get_dpi_scale_factor()
            # 如果处于隐藏状态，我们保存 normal_geometry，否则保存当前 geometry
            geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
            width = max(130, int(geom.width() / scale))
            height = max(150, int(geom.height() / scale))
            x = int(geom.x() / scale)
            y = int(geom.y() / scale)
            
            if is_open is None:
                is_open = self.isVisible()
                
            config_file = WINDOW_CONFIG_FILE
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except:
                        pass
                
                # 保存为每个 bucket 独立的项
                key = f"distribution_details_dialog_{self.bucket_idx}"
                data[key] = {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "stays_on_top": self.stays_on_top,
                    "anchor_edge": self.anchor_edge,
                    "is_hidden_state": self.is_hidden_state,
                    "bucket_idx": self.bucket_idx,
                    "is_open": is_open
                }
                
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
                        key = f"distribution_details_dialog_{getattr(self, 'bucket_idx', 0)}"
                        dialog_config = data.get(key, {})
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

    def start_slide_animation(self, target_rect, target_opacity, duration=250, is_snap_feedback=False):
        """
        统一的滑动与透明度动画控制器，提供流畅的 QQ 窗口滑动和呼吸反馈效果
        """
        if hasattr(self, 'anim_group') and self.anim_group is not None:
            try:
                if self.anim_group.state() == QParallelAnimationGroup.State.Running:
                    self.anim_group.stop()
            except Exception:
                pass
                
        self.anim_group = QParallelAnimationGroup(self)
        
        # 1. 窗口位置大小动画 (Geometry)
        self.geom_anim = QPropertyAnimation(self, b"geometry")
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_rect)
        if is_snap_feedback:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        # 2. 窗口不透明度动画 (Opacity)
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(target_opacity)
        if is_snap_feedback:
            self.opacity_anim.setKeyValueAt(0.5, 0.4)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        
        self._in_snap_action = True
        
        def on_finished():
            self._in_snap_action = False
            if self.is_hidden_state:
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(1.0)
            self._save_window_states(is_open=True)
                
        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        if self.is_hidden_state:
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start()
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35  # 磁吸检测门槛像素
        
        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()
        
        # 排除底边（即任务栏所在方向，通常不磁吸底边）。我们磁吸顶边、左边、右边。
        if abs(win_geo.top() - screen_geo.top()) < margin:
            edge = "top"
            target_y = screen_geo.top()
            snapped = True
        elif abs(win_geo.left() - screen_geo.left()) < margin:
            edge = "left"
            target_x = screen_geo.left()
            snapped = True
        elif abs(win_geo.right() - screen_geo.right()) < margin:
            edge = "right"
            target_x = screen_geo.right() - win_geo.width()
            snapped = True
            
        self._is_dragging = False
        if snapped:
            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            self.start_slide_animation(self.normal_geometry, 1.0, duration=250, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None

    def hide_to_edge(self):
        if not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        w = self.normal_geometry.width()
        h = self.normal_geometry.height()
        x = self.normal_geometry.x()
        y = self.normal_geometry.y()
        
        strip_size = 5  # 隐藏后在屏幕内留出的极窄感应/观察条像素宽度
        
        if self.anchor_edge == "left":
            target_x = screen_geo.left() - w + strip_size
            target_y = y
        elif self.anchor_edge == "right":
            target_x = screen_geo.right() - strip_size
            target_y = y
        elif self.anchor_edge == "top":
            target_x = x
            target_y = screen_geo.top() - h + strip_size
        else:
            return
            
        self.is_hidden_state = True
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=300)

    def show_normal_position(self):
        if self.is_hidden_state and self.normal_geometry:
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            
            self.is_hidden_state = False
            import time
            self._last_show_time = time.time()
            self._has_hovered_since_show = False
            self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
        
        self.show()
        self.raise_()
        self.activateWindow()

    def _check_hover(self):
        if not self.isVisible():
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return
            
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        in_window = self.frameGeometry().contains(mouse_pos)
        
        if in_window:
            self._has_hovered_since_show = True
            
        if self.is_hidden_state:
            if in_window:
                self.hover_ticks += 1
                if self.hover_ticks >= 2:  # 100ms * 2 = 200ms 停留防误触
                    self.show_normal_position()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0
        else:
            if self.anchor_edge is not None:
                if not in_window:
                    if not getattr(self, '_has_hovered_since_show', False):
                        self.leave_ticks = 0
                        return
                    import time
                    if time.time() - getattr(self, '_last_show_time', 0.0) < 1.2:
                        self.leave_ticks = 0
                        return
                        
                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:  # 100ms * 4 = 400ms 离开防抖
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            # 拖拽时立即重置磁吸边缘，避免拖动过程中鼠标离开导致的强行缩回
            self.anchor_edge = None
            self.snap_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

    def closeEvent(self, event):
        self.hover_timer.stop()
        self.snap_timer.stop()
        
        main_app = self._get_main_app()
        is_app_exiting = False
        if main_app:
            if not main_app.isVisible() or getattr(main_app, '_is_exiting', False):
                is_app_exiting = True
                
        if is_app_exiting:
            self._save_window_states(is_open=True)
        else:
            self._save_window_states(is_open=False)
            
        event.accept()

    def hideEvent(self, event):
        main_app = self._get_main_app()
        is_app_exiting = False
        if main_app:
            if not main_app.isVisible() or getattr(main_app, '_is_exiting', False):
                is_app_exiting = True
                
        if is_app_exiting:
            self._save_window_states(is_open=True)
        else:
            self._save_window_states(is_open=False)
            
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.layout():
            self.layout().activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            self.layout().setGeometry(self.rect())
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()
    def link_stock(self, code, name=None):
        """Linkage method called by sub-dialogs like DNA audit window."""
        if not name:
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'get_stock_name'):
                name = main_app.get_stock_name(code)
            else:
                name = ""
        self.code_clicked.emit(code, name)
        main_app = self._get_main_app()
        if main_app and hasattr(main_app, 'link_stock'):
            main_app.link_stock(code, name)

    def diagnose_stock_strategy(self, code):
        """Forward diagnostic requests from DNA audit window to main application."""
        main_app = self._get_main_app()
        if not main_app:
            return
        if hasattr(main_app, 'diagnose_stock_strategy'):
            main_app.diagnose_stock_strategy(code)
            return
        diag_edit = getattr(main_app, 'diag_edit', None) or getattr(main_app, 'diag_entry', None)
        if diag_edit:
            if hasattr(diag_edit, 'setText'):
                diag_edit.setText(code)
            else:
                try:
                    diag_edit.delete(0, 'end')
                    diag_edit.insert(0, code)
                except:
                    pass
            if hasattr(main_app, 'diagnose_stock_strategy'):
                main_app.diagnose_stock_strategy(code)

    def _link_current_row(self, row):
        if getattr(self, '_is_updating', False) or getattr(self, '_is_auto_popping', False):
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
        
        # ⚡ 发送到异动联动
        from ats.ui.base_table import send_to_linkage
        linkage_act = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        linkage_act.triggered.connect(lambda: send_to_linkage(code, name_clean, self))
        
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
                    # 🚀 [NEW] Packaged PyQt6 Fallback
                    try:
                        from backtest_feature_auditor import audit_multiple_codes
                        from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
                        from PyQt6.QtCore import Qt
                        from PyQt6.QtWidgets import QMessageBox
                        
                        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                        QApplication.processEvents()
                        
                        summaries = audit_multiple_codes(
                            list(code_to_name.keys()),
                            end_date=None,
                            code_to_name=code_to_name,
                            progress_callback=None,
                            resample='d'
                        )
                        if summaries:
                            self._dna_audit_win = QtDnaAuditReportWindow(summaries, parent=self.window(), end_date=None, resample='d')
                            self._dna_audit_win.show()
                        else:
                            QMessageBox.warning(self, "DNA 审计", "没有产生审计数据或结论。")
                    except Exception as e:
                        print("No access to main monitor app for DNA audit and local fallback failed:", code_to_name, e)
                    finally:
                        QApplication.restoreOverrideCursor()

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
        # 冷启动时，延迟一小会儿，在主 UI 呈现后自动拉起历史记录的明细窗口
        QTimer.singleShot(800, lambda: self._restore_details_dialog_if_saved(cold_start=True))

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

    def open_details_dialog(self, idx, restore_state=None, cold_start=False):
        # 1. 查找去重，防止双击或恢复时重复创建相同的区间窗口
        from PyQt6.sip import isdeleted
        for d in getattr(self, '_active_dialogs', []):
            try:
                if d and not isdeleted(d) and getattr(d, 'bucket_idx', None) == idx:
                    if hasattr(d, 'show_normal_position'):
                        d.show_normal_position()
                    else:
                        d.show()
                        d.raise_()
                        d.activateWindow()
                    return
            except Exception:
                pass

        df_filtered = None
        if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            df_filtered = self._filter_df_by_bucket(self.current_df, idx)
        
        # 如果是非冷启动，且没有有效数据，直接返回不创建
        if not cold_start and (df_filtered is None or df_filtered.empty):
            return
            
        # parent=None: allows dialog to go behind the main window (OS window manager
        # always keeps child windows in front of their parent on Windows).
        # We keep a strong Python reference in _active_dialogs to prevent GC deletion,
        # and monitor main window destroyed signal to close dialogs when ATS exits.
        dialog = DistributionDetailsDialog(idx, None)
        if df_filtered is not None and not df_filtered.empty:
            dialog.update_data(df_filtered)
        else:
            dialog.table.setRowCount(0)
            if idx == 999:
                dialog.header_label.setText("🔍 过滤数据查看 | ⏳ 正在等待数据或公式输入...")
            else:
                dialog.header_label.setText("📊 涨跌分布个股明细 | ⏳ 正在等待数据同步...")
        
        if idx == 999:
            main_win = self.window()
            combo_text = ""
            if main_win and hasattr(main_win, 'query_combo'):
                combo_text = main_win.query_combo.currentText().strip()
            q_expr = main_win.query_expr if (main_win and hasattr(main_win, 'query_expr')) else ""
            if not combo_text:
                combo_text = q_expr
                
            match_count = len(df_filtered) if df_filtered is not None else 0
            if "  |  " in combo_text:
                parts = [p.strip() for p in combo_text.split("  |  ")]
                notes_and_hits = parts[:-1]
                formula = parts[-1]
                short_formula = formula[:18] + "..." if len(formula) > 22 else formula
                display_text = f"{' | '.join(notes_and_hits)} | {short_formula}"
            else:
                display_text = combo_text[:28] + "..." if len(combo_text) > 32 else combo_text
                
            title = f"🔍 过滤数据查看 | {display_text} (共 {match_count} 只)"
            dialog.setWindowTitle(title)
            if df_filtered is not None and not df_filtered.empty:
                dialog.header_label.setText(f"🔍 过滤数据查看 | {display_text}")
        else:
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
            title = f"📊 涨跌分布个股明细 | {bucket_names[idx]} (共 {len(df_filtered) if df_filtered is not None else 0} 只)"
            dialog.setWindowTitle(title)
            if df_filtered is not None and not df_filtered.empty:
                dialog.header_label.setText(f"📊 涨跌分布 ({bucket_names[idx]}) | 双击行切换/联动")
        
        # 如果有保存的磁吸和隐藏状态，在 show 前进行恢复
        if restore_state:
            try:
                scale = dialog._get_dpi_scale_factor()
                # 恢复位置和大小
                rx = int(restore_state.get("x", 100) * scale)
                ry = int(restore_state.get("y", 100) * scale)
                rw = int(restore_state.get("width", 750) * scale)
                rh = int(restore_state.get("height", 550) * scale)
                
                # 限制坐标在可用屏幕范围内，防止移出屏幕
                from gui_utils import clamp_window_to_screens
                rx, ry = clamp_window_to_screens(rx, ry, rw, rh)
                
                # 恢复 normal_geometry
                dialog.normal_geometry = QRect(rx, ry, rw, rh)
                dialog.anchor_edge = restore_state.get("anchor_edge")
                
                # 恢复隐藏状态
                is_hidden = restore_state.get("is_hidden_state", False)
                if is_hidden and dialog.anchor_edge:
                    dialog.is_hidden_state = True
                    # 计算收缩隐藏后的临时坐标
                    strip_size = 5
                    screen = dialog.screen() or QApplication.primaryScreen()
                    screen_geo = screen.availableGeometry()
                    
                    if dialog.anchor_edge == "left":
                        hx = screen_geo.left() - rw + strip_size
                        hy = ry
                    elif dialog.anchor_edge == "right":
                        hx = screen_geo.right() - strip_size
                        hy = ry
                    elif dialog.anchor_edge == "top":
                        hx = rx
                        hy = screen_geo.top() - rh + strip_size
                    else:
                        hx, hy = rx, ry
                        dialog.is_hidden_state = False
                        
                    dialog.setGeometry(hx, hy, rw, rh)
                    dialog.setWindowOpacity(0.35)
                else:
                    dialog.setGeometry(rx, ry, rw, rh)
                    dialog.setWindowOpacity(1.0)
            except Exception as e:
                print(f"[DistributionBarChart] Error restoring window geometry: {e}")
                
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
                if not isdeleted(d):
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

    def _restore_details_dialog_if_saved(self, cold_start=False):
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                
                # 遍历恢复 10 个涨跌区间以及 999 公式过滤窗口
                for idx in list(range(10)) + [999]:
                    key = f"distribution_details_dialog_{idx}"
                    config = data.get(key, {})
                    if config.get("is_open", False):
                        self.open_details_dialog(idx, restore_state=config, cold_start=cold_start)
        except Exception as e:
            print(f"[DistributionBarChart] Restore details dialog error: {e}")

    def _filter_df_by_bucket(self, df, idx):
        if df is None or df.empty or 'percent' not in df.columns:
            return None
            
        if idx == 999:
            query_expr = ""
            main_win = self.window()
            if main_win and hasattr(main_win, 'query_expr'):
                query_expr = main_win.query_expr
            if not query_expr:
                return pd.DataFrame()
                
            try:
                from stock_logic_utils import query_engine
                test_df = df.copy()
                mapping = {
                    '价格': 'close', '最新价': 'close', '现价': 'close', 
                    '涨幅': 'pct', 
                    '量': 'volume', '成交量': 'volume',
                    '成交额': 'turnover',
                    '最高': 'high', '最低': 'low', '开盘': 'open',
                    '板块': 'category', '异动类型': 'category', 'hy': 'category'
                }
                for cn, en in mapping.items():
                    if cn in test_df.columns and en not in test_df.columns:
                        test_df[en] = test_df[cn]
                if 'close' in test_df.columns:
                    for col in ['open', 'high', 'low']:
                        if col not in test_df.columns:
                            test_df[col] = test_df['close']
                            
                res = query_engine.execute(test_df, query_expr)
                if isinstance(res, pd.DataFrame):
                    return df.loc[df.index.intersection(res.index)]
                elif isinstance(res, (pd.Series, np.ndarray, list)):
                    if len(res) == len(df):
                        return df[res]
                return pd.DataFrame()
            except Exception as e:
                print(f"[_filter_df_by_bucket] Error evaluating query_expr: {e}")
                return pd.DataFrame()
                
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
        
        # 1. 广播数据更新到所有当前活跃/已经打开的明细窗口！
        from PyQt6.sip import isdeleted
        for d in getattr(self, '_active_dialogs', []):
            try:
                if d and not isdeleted(d) and hasattr(d, 'bucket_idx'):
                    df_filtered = self._filter_df_by_bucket(df_all, d.bucket_idx)
                    if df_filtered is not None:
                        d.update_data(df_filtered)
                        if d.bucket_idx == 999:
                            main_win = self.window()
                            combo_text = ""
                            if main_win and hasattr(main_win, 'query_combo'):
                                combo_text = main_win.query_combo.currentText().strip()
                            q_expr = main_win.query_expr if (main_win and hasattr(main_win, 'query_expr')) else ""
                            if not combo_text:
                                combo_text = q_expr
                                
                            match_count = len(df_filtered)
                            if "  |  " in combo_text:
                                parts = [p.strip() for p in combo_text.split("  |  ")]
                                notes_and_hits = parts[:-1]
                                formula = parts[-1]
                                short_formula = formula[:18] + "..." if len(formula) > 22 else formula
                                display_text = f"{' | '.join(notes_and_hits)} | {short_formula}"
                            else:
                                display_text = combo_text[:28] + "..." if len(combo_text) > 32 else combo_text
                                
                            title = f"🔍 过滤数据查看 | {display_text} (共 {match_count} 只)"
                            d.setWindowTitle(title)
                            d.header_label.setText(f"🔍 过滤数据查看 | {display_text}")
                        else:
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
                            title = f"📊 涨跌分布个股明细 | {bucket_names[d.bucket_idx]} (共 {len(df_filtered)} 只)"
                            d.setWindowTitle(title)
                            d.header_label.setText(f"📊 涨跌分布 ({bucket_names[d.bucket_idx]}) | 双击行切换/联动")
            except Exception as e:
                print(f"[DistributionBarChart] Broadcast update error: {e}")
                
        self._details_restored = True
            
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

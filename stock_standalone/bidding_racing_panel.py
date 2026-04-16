# -*- coding: utf-8 -*-
import math
import os
import json
import time
import datetime
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGraphicsDropShadowEffect,QPushButton,
    QMenu, QApplication, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QPointF, QSize, QTimer, QByteArray
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QConicalGradient, 
    QLinearGradient, QRadialGradient, QPolygon, QPainterPath
)

from tk_gui_modules.qt_table_utils import EnhancedTableWidget, NumericTableWidgetItem
from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger(name=__name__, level=LoggerFactory.WARNING)

# --- [🚀 极致性能] 模块级内存缓存，减少磁盘 I/O ---
_RACING_UI_STATE = {}

def _get_racing_config():
    """极速获取配置 (内存优先)"""
    global _RACING_UI_STATE
    if not _RACING_UI_STATE:
        try:
            from JohnsonUtil import commonTips as cct
            config_path = os.path.join(cct.get_base_path(), "bidding_racing_ui_state_v3.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    _RACING_UI_STATE = json.load(f)
        except: pass
    return _RACING_UI_STATE

def _save_racing_config(updates: Dict[str, Any]):
    """增量保存配置到内存，并同步到磁盘"""
    global _RACING_UI_STATE
    conf = _get_racing_config()
    conf.update(updates)
    try:
        from JohnsonUtil import commonTips as cct
        config_path = os.path.join(cct.get_base_path(), "bidding_racing_ui_state_v3.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False, indent=2)
    except: pass

class RacingPieWidget(QWidget):
    """
    高性能交互式饼图 - 赛马场分类筛选指挥台
    """
    category_selected = pyqtSignal(str) # 筛选信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.data = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 100}
        self.colors = {
            "龙头": QColor("#FF2D55"),  # 活力红
            "确核": QColor("#FF9500"),  # 橙色
            "跟涨": QColor("#5856D6"),  # 紫色
            "静默": QColor("#2C2C2E")   # 暗浅灰
        }
        self.selected_category = None
        self._hover_category = None
        self._angles_cache = {} 
        self._grad_cache = {} 
        self._animation_angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.start(200) 
        
    def _update_animation(self):
        if self.data.get("静默", 0) >= 99 or self.selected_category:
             return
        self._animation_angle = (self._animation_angle + 2) % 360 
        self.update()

    def set_data(self, distribution: Dict[str, int]):
        if self.data != distribution:
            self.data = distribution
            self.update()

    def _get_grad(self, color):
        key = color.name()
        if key not in self._grad_cache:
            grad = QConicalGradient(QPointF(0, 0), 270)
            grad.setColorAt(0, color)
            grad.setColorAt(1, color.lighter(130))
            self._grad_cache[key] = grad
        return self._grad_cache[key]

    def _get_hit_category(self, pos: QPoint):
        rect = self.rect()
        center = rect.center()
        dist = math.sqrt((pos.x() - center.x())**2 + (pos.y() - center.y())**2)
        side = min(rect.width(), rect.height()) - 40
        if dist < side * 0.3: return "ALL"
        if dist > side * 0.5: return None
        
        angle = math.degrees(math.atan2(-(pos.y() - center.y()), pos.x() - center.x()))
        if angle < 0: angle += 360
        
        for cat, (start, span) in self._angles_cache.items():
            real_start = (start / 16) % 360
            real_span = (span / 16)
            if real_span < 0:
                a_end = real_start
                a_start = real_start + real_span
            else:
                a_start = real_start
                a_end = real_start + real_span
                
            hit = False
            if a_start < 0:
                if angle >= (a_start + 360) or angle <= a_end: hit = True
            elif a_end > 360:
                if angle >= a_start or angle <= (a_end - 360): hit = True
            else:
                if a_start <= angle <= a_end: hit = True
            if hit: return cat
        return None

    def mousePressEvent(self, event):
        cat = self._get_hit_category(event.pos())
        if cat:
            self.selected_category = cat if cat != "ALL" else None
            self.category_selected.emit(cat)
            self.update()

    def mouseMoveEvent(self, event):
        old_hover = self._hover_category
        self._hover_category = self._get_hit_category(event.pos())
        if old_hover != self._hover_category:
            self.update()
            if self._hover_category and self._hover_category != "ALL":
                from PyQt6.QtWidgets import QToolTip
                count = self.data.get(self._hover_category, 0)
                total = sum(self.data.values()) or 1
                percent = count / total * 100
                QToolTip.showText(event.globalPosition().toPoint(), f"<b>{self._hover_category}</b><br/>数量: {count} 只<br/>占比: {percent:.1f}%")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        side = min(rect.width(), rect.height()) - 40
        center = rect.center()
        pie_rect = QRect((rect.width()-side)//2, (rect.height()-side)//2, side, side)
        
        total = sum(self.data.values())
        if total == 0: total = 1
        
        start_angle = 90 * 16
        self._angles_cache = {}
        
        glow = QRadialGradient(QPointF(center), side/2)
        glow.setColorAt(1.0, QColor(255, 255, 255, 5))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(pie_rect.adjusted(-5, -5, 5, 5))

        for label, val in self.data.items():
            if val == 0: continue
            span_angle = -int((val / total) * 360 * 16)
            self._angles_cache[label] = (start_angle, span_angle)
            
            color = self.colors.get(label, Qt.GlobalColor.gray)
            if self.selected_category == label:
                color = color.lighter(130)
                draw_rect = pie_rect.adjusted(-2, -2, 2, 2)
            elif self._hover_category == label:
                color = color.lighter(115)
                draw_rect = pie_rect
            else:
                draw_rect = pie_rect

            grad = self._get_grad(color)
            grad.setCenter(QPointF(center))
            grad.setAngle(270 - self._animation_angle)
            
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            painter.drawPie(draw_rect, start_angle, span_angle)
            start_angle += span_angle

        inner_side = side * 0.6
        inner_rect = QRect((rect.width()-inner_side)//2, (rect.height()-inner_side)//2, inner_side, inner_side)
        inner_grad = QLinearGradient(QPointF(inner_rect.topLeft()), QPointF(inner_rect.bottomRight()))
        inner_grad.setColorAt(0, QColor(30, 30, 35, 255))
        inner_grad.setColorAt(1, QColor(5, 5, 8, 255))
        painter.setBrush(inner_grad)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawEllipse(inner_rect)
        
        painter.setPen(Qt.GlobalColor.white)
        font = QFont("Microsoft YaHei", 11)
        font.setBold(True)
        painter.setFont(font)
        
        if self.selected_category:
            title = f"筛选: {self.selected_category}"
            count_txt = f"{self.data.get(self.selected_category, 0)} 只"
        else:
            title = "赛马分布"
            count_txt = f"总量: {sum(self.data.values())}"
            
        painter.drawText(inner_rect.adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter, title)
        font.setPointSize(9); font.setBold(False); painter.setFont(font)
        painter.drawText(inner_rect.adjusted(0, 15, 0, 15), Qt.AlignmentFlag.AlignCenter, count_txt)

class SectorDetailDialog(QDialog, WindowMixin):
    """板块成分股详情弹窗 - 结构与领军个股一致"""
    def __init__(self, sector_name, detector, linkage_cb, parent=None):
        super().__init__(parent)
        # 必须最先赋值
        self.detector = detector
        self.linkage_cb = linkage_cb
        self.sector_name = sector_name
        
        self.setWindowTitle(f"🔭 板块详情: {sector_name}")
        self.resize(800, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setStyleSheet("background-color: #000; color: #EEE;")

        # 记忆位置
        self.load_window_position_qt(self, "SectorDetail_Unified")
        
        self.setUpdatesEnabled(False)
        self._sort_col = 2 # 默认排序: 结构分
        self._sort_order = Qt.SortOrder.DescendingOrder
        
        # [NEW] 启动保护锁，防止初始化时的自动布局覆盖用户保存的列宽
        self._boot_lock = True
        
        self._init_ui()
        
        # 延迟恢复表头状态 (确保窗口布局已初步完成)
        QTimer.singleShot(150, self._restore_header_state)
        
        # 1秒后解除保护锁
        QTimer.singleShot(1000, self._release_boot_lock)
        
        # 启动定时刷新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(500) 
        self.refresh_data()
        self.setUpdatesEnabled(True)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title_lbl = QLabel(f"🔥 {self.sector_name} - 领军个股明细")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #00FFCC; margin-bottom: 5px;")
        layout.addWidget(title_lbl)
        
        self.table = EnhancedTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF"])
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #000; alternate-background-color: #111; color: #FFF; gridline-color: #222; outline: none; }
            QHeaderView::section { background-color: #222; color: #BBB; padding: 4px; border: 1px solid #333; }
        """)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(90)
        
        self.table.code_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="sector_dialog_link"))
        self.table.code_double_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="sector_dialog_double"))
        
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.horizontalHeader().sectionResized.connect(self._save_header_state)
        
        # 右键菜单支持
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        layout.addWidget(self.table)
        
        hint = QLabel("💡 单击或双击个股联动主图分析")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(hint)

    def refresh_data(self):
        if not hasattr(self, 'detector') or not self.detector: return
        
        members = self.detector.sector_map.get(self.sector_name, set())
        if not members: return
        
        with self.detector._lock:
            data_list = []
            for code in members:
                ts = self.detector._tick_series.get(code)
                if ts: data_list.append(ts)
            
            # 排序逻辑
            col_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'pct_diff', 6:'pct_diff'}
            attr = col_attr_map.get(self._sort_col, 'score')
            is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
            data_list.sort(key=lambda x: (getattr(x, attr, 0) if attr != 'pct_diff' else (x.current_pct - x.pct_diff)), reverse=is_rev)
            
            display_list = data_list[:100]
            flattened = []
            for ts in display_list:
                flattened.append((
                    ts.code, ts.name, ts.score, 
                    getattr(ts, 'signal_count', 0),
                    ts.current_pct,
                    ts.current_pct - ts.pct_diff,
                    ts.pct_diff
                ))
        self._render_table(flattened)

    def _render_table(self, data):
        if self.table.rowCount() != len(data):
            self.table.setRowCount(len(data))
        for i, row in enumerate(data):
            code, name, score, sig, pct, start_pct, dff = row
            self._update_dialog_cell(i, 0, code)
            self._update_dialog_cell(i, 1, name)
            self._update_dialog_cell(i, 2, f"{score:.1f}", QColor("#FFD700"))
            sig_txt = str(sig) if sig > 0 else ""
            self._update_dialog_cell(i, 3, sig_txt, QColor("#00FFCC"), Qt.AlignmentFlag.AlignCenter)
            c_pct = QColor("#FF4444") if pct > 0 else (QColor("#44CC44") if pct < 0 else Qt.GlobalColor.white)
            self._update_dialog_cell(i, 4, f"{pct:+.2f}%", c_pct)
            c_start = QColor("#FF4444") if start_pct > 0 else (QColor("#44CC44") if start_pct < 0 else Qt.GlobalColor.white)
            self._update_dialog_cell(i, 5, f"{start_pct:+.2f}%", c_start)
            c_dff = QColor("#FF4444") if dff > 0 else (QColor("#44CC44") if dff < 0 else Qt.GlobalColor.white)
            self._update_dialog_cell(i, 6, f"{dff:+.2f}%", c_dff)

    def _update_dialog_cell(self, row, col, text, color=None, align=None):
        it = self.table.item(row, col)
        if not it:
            from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
            it = NumericTableWidgetItem(text)
            if color: it.setForeground(color)
            if align: it.setTextAlignment(align)
            self.table.setItem(row, col, it)
        else:
            if it.text() != text:
                it.setText(text)
                if color: it.setForeground(color)

    def _release_boot_lock(self):
        self._boot_lock = False
        logger.debug("🔓 [Detail] 初始化保护已解除，开始监听用户列宽调整")

    def _save_header_state(self):
        """保存明细表各列宽度 (内存优先)"""
        # 如果处于启动保护期，不保存 (防止覆盖已恢复的值)
        if hasattr(self, '_boot_lock') and self._boot_lock:
            return 
            
        try:
            widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
            # 过滤掉全为 0 的异常状态（通常发生在窗口关闭瞬间）
            if sum(widths) < 100: return
            
            _save_racing_config({"detail_column_widths": widths})
            logger.debug(f"💾 [Detail] 已保存列宽配置: {widths}")
        except: pass

    def _restore_header_state(self):
        """恢复明细表各列宽度 (内存优先)"""
        try:
            conf = _get_racing_config()
            widths = conf.get("detail_column_widths")
            if widths and len(widths) == self.table.columnCount():
                self.table.horizontalHeader().blockSignals(True)
                for i, w in enumerate(widths):
                    if w > 10: self.table.setColumnWidth(i, w)
                self.table.horizontalHeader().blockSignals(False)
                logger.debug(f"✅ [Detail] 成功还原 {self.sector_name} 列表宽度")
        except: pass

    def _on_context_menu(self, pos):
        """明细表右键菜单"""
        item = self.table.itemAt(pos)
        if not item: return
        row = item.row()
        code = self.table.item(row, 0).text()
        name = self.table.item(row, 1).text()
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #005BB7; }")
        
        act_viz = menu.addAction(f"📊 联动可视化 ({name})")
        act_viz.triggered.connect(lambda: self.linkage_cb(code, name, source="sector_dialog_context"))
        
        menu.addSeparator()
        act_copy = menu.addAction("📋 复制代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_header_clicked(self, logical_index):
        if self._sort_col == logical_index:
            self._sort_order = Qt.SortOrder.AscendingOrder if self._sort_order == Qt.SortOrder.DescendingOrder else Qt.SortOrder.DescendingOrder
        else:
            self._sort_col = logical_index
            self._sort_order = Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(logical_index, self._sort_order)
        self.refresh_data()

    def closeEvent(self, event):
        self._save_header_state()
        self.save_window_position_qt_visual(self, "SectorDetail_Unified")
        super().closeEvent(event)

class RacingTimeline(QFrame):
    """
    带刻度与状态标识的赛马时间轴
    """
    time_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet("background-color: #1C1C1E; border-radius: 10px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        
        self.label = QLabel("🚩 竞技进度: 09:25:00")
        self.label.setStyleSheet("color: #00FFCC; font-weight: bold;")
        layout.addWidget(self.label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 330)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #333;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #111, stop:1 #333);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qradialgradient(spread:pad, cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #00FFCC, stop:1 #0088AA);
                border: 2px solid #FFF;
                width: 18px;
                height: 18px;
                margin: -7px 0;
                border-radius: 9px;
            }
        """)
        self.slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.slider)
        
        ticks_layout = QHBoxLayout()
        for t in ["09:25", "10:30", "11:30", "13:00", "14:00", "15:00"]:
            lbl = QLabel(t)
            lbl.setStyleSheet("color: #666; font-size: 10px;")
            ticks_layout.addWidget(lbl)
            if t != "15:00": ticks_layout.addStretch()
        layout.addLayout(ticks_layout)

    def _on_value_changed(self, val):
        h = 9 + val // 60
        m = 25 + val % 60
        if m >= 60:
            h += m // 60
            m = m % 60
        time_str = f"{h:02d}:{m:02d}:00"
        self.label.setText(f"🚩 竞技进度: {time_str}")
        self.time_changed.emit(time_str)

    def set_time(self, time_str: str):
        self.label.setText(f"🚩 竞技进度: {time_str}")
        try:
            parts = time_str.split(':')
            h, m = int(parts[0]), int(parts[1])
            total_m = (h - 9) * 60 + (m - 25)
            self.slider.blockSignals(True)
            self.slider.setValue(max(0, total_m))
            self.slider.blockSignals(False)
        except: pass

class BiddingRacingRhythmPanel(QWidget, WindowMixin):
    """
    竞价赛马节奏主面板
    """
    closed = pyqtSignal()

    def __init__(self, detector=None, parent=None, main_app=None, on_code_callback=None, sender=None):
        super().__init__(parent)
        self.detector = detector
        self.main_app = main_app
        self.on_code_callback = on_code_callback
        
        if sender:
            self.sender = sender
        elif not main_app:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.sender = StockSender(tdx_var=True, ths_var=False, dfcf_var=False)
            except Exception as e:
                print(f"Standalone StockSender init failed: {e}")
                self.sender = None
        else:
            self.sender = None
            
        self._select_code = "" 
        
        self.setWindowTitle("🏁 竞价赛马与节奏监控")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("background-color: #000000; color: white;")
        
        self._last_data_version = -1
        self._last_rendered_time = 0
        self._last_ui_update_ts = 0 
        self._is_rendering = False
        self._table_highlights = {}
        
        self._sort_col = 2 
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._sort_col_sector = 1 # 默认按强度得分排序
        self._sort_order_sector = Qt.SortOrder.DescendingOrder
        
        self._reset_cycle_mins = 60 # 默认 60 分钟重置一次基准
        self._last_anchor_reset_data_ts = 0
        self._anchor_history = [] 
        
        self._UI_CACHE = {
            "COLOR_GOLD": QColor("#FFD700"),
            "COLOR_RED": QColor("#FF4444"),
            "COLOR_GREEN": QColor("#44CC44"),
            "COLOR_CYAN": QColor("#00FFCC"),
            "COLOR_BLUE": QColor("#00CCFF"),
            "COLOR_CORAL": QColor("#FF2D55"),
            "COLOR_TRANSPARENT": QColor(0, 0, 0, 0),
            "COLOR_FLASH_BASE": QColor(255, 215, 0),
            "FONT_FOLLOWERS": QFont("Segoe UI", 9)
        }
        
        self._init_ui()
        
        self.stock_table.setSortingEnabled(False)
        self.sector_table.setSortingEnabled(False)
        
        self.load_window_position_qt(self, "BiddingRacingRhythmPanel", default_width=1000, default_height=700)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_visuals)
        self.refresh_timer.start(100)
        
        QTimer.singleShot(5000, self._check_auto_anchor)
        QTimer.singleShot(200, self._restore_ui_state)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # [🚀 极限合并] 顶层综合控制条
        top_bar = QFrame()
        top_bar.setFixedHeight(90)
        top_bar.setStyleSheet("background-color: #1C1C1E; border-radius: 12px; border: 1px solid #2C2C2E;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 5, 15, 5)
        top_bar_layout.setSpacing(20)
        
        # 左侧: 进度时间轴 (保持原有逻辑，嵌套在布局中)
        self.timeline = RacingTimeline()
        self.timeline.setStyleSheet("background: transparent; border: none;")
        top_bar_layout.addWidget(self.timeline, stretch=7)
        
        # 右侧: 切片周期控制组
        cycle_group = QFrame()
        cycle_group.setFixedWidth(240)
        cycle_group.setStyleSheet("background-color: #262629; border-radius: 8px; border: 1px solid #3A3A3C;")
        cycle_layout = QVBoxLayout(cycle_group)
        cycle_layout.setContentsMargins(10, 8, 10, 8)
        cycle_layout.setSpacing(5)
        
        # 周期标题与显示
        self.cycle_label = QLabel(f"📊 起点参考周期: {self._reset_cycle_mins}m")
        self.cycle_label.setStyleSheet("color: #FFD700; font-weight: bold; font-family: 'Segoe UI'; font-size: 11px;")
        self.cycle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cycle_layout.addWidget(self.cycle_label)
        
        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # 减 10m
        self.btn_minus = QPushButton("-10m")
        self.btn_minus.setFixedSize(45, 26)
        self.btn_minus.setStyleSheet("""
            QPushButton { background: #3A3A3C; color: #BBB; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #48484A; color: white; }
        """)
        self.btn_minus.clicked.connect(lambda: self._adjust_cycle(-10))
        btn_layout.addWidget(self.btn_minus)
        
        # 加 10m
        self.btn_plus = QPushButton("+10m")
        self.btn_plus.setFixedSize(45, 26)
        self.btn_plus.setStyleSheet("""
            QPushButton { background: #3A3A3C; color: #BBB; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #48484A; color: white; }
        """)
        self.btn_plus.clicked.connect(lambda: self._adjust_cycle(10))
        btn_layout.addWidget(self.btn_plus)
        
        # 立即重置按钮 (醒目红色)
        self.reset_btn = QPushButton("🔄 即时重置")
        self.reset_btn.setFixedSize(65, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton { background: #FF2D55; color: white; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #FF375F; border: 1px solid white; }
        """)
        self.reset_btn.clicked.connect(self._manual_reset_anchors)
        btn_layout.addWidget(self.reset_btn)
        
        cycle_layout.addLayout(btn_layout)
        top_bar_layout.addWidget(cycle_group)
        
        main_layout.addWidget(top_bar)
        
        center_layout = QHBoxLayout()
        center_layout.setSpacing(20)
        
        self.pie_widget = RacingPieWidget()
        self.pie_widget.category_selected.connect(self._on_pie_filter)
        center_layout.addWidget(self.pie_widget, stretch=4)
        
        rank_frame = QFrame()
        rank_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        rank_layout = QVBoxLayout(rank_frame)
        
        title_lbl = QLabel("🏆 当下领军个股 (Top 10)")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFD700; padding: 10px;")
        rank_layout.addWidget(title_lbl)
        
        self.stock_table = EnhancedTableWidget(0, 7)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF"])
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(80) 
        header.setMinimumSectionSize(30)
        self.stock_table.setColumnWidth(0, 65)
        self.stock_table.setColumnWidth(1, 75)
        
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #005BB7; 
                selection-color: white;
                outline: none;
            }
            QTableWidget::item:selected { background-color: #005BB7; }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; color: #BBB; }
        """)
        
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stock_table.setSortingEnabled(False)
        header.sectionClicked.connect(lambda idx: self._on_header_clicked("stock", idx))
        rank_layout.addWidget(self.stock_table)
        center_layout.addWidget(rank_frame, stretch=6)
        main_layout.addLayout(center_layout, stretch=7)
        
        bottom_frame = QFrame()
        bottom_frame.setFixedHeight(220)
        bottom_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        bottom_lay = QVBoxLayout(bottom_frame)
        
        sec_title_lay = QHBoxLayout()
        sec_title = QLabel("🔥 最强板块赛道")
        sec_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00FFCC; padding: 5px;")
        sec_title_lay.addWidget(sec_title)
        
        sec_title_lay.addSpacing(15)
        self.history_layout = QHBoxLayout()
        self.history_layout.setSpacing(6)
        sec_title_lay.addLayout(self.history_layout)
        sec_title_lay.addStretch()
        
        bottom_lay.addLayout(sec_title_lay)
        
        self.sector_table = EnhancedTableWidget(0, 7)
        self.sector_table.setHorizontalHeaderLabels(["板块名称", "强度得分", "领涨龙头", "龙头涨幅", "起点涨幅", "龙头DFF", "联动详情"])
        s_header = self.sector_table.horizontalHeader()
        s_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        s_header.setMinimumSectionSize(30)
        s_header.setDefaultSectionSize(100)
        self.sector_table.setColumnWidth(0, 80)
        self.sector_table.setColumnWidth(2, 110)
        
        self.sector_table.setAlternatingRowColors(True)
        self.sector_table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #005BB7; 
                selection-color: white;
                outline: none;
            }
            QTableWidget::item:selected { background-color: #005BB7; }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; color: #BBB; }
        """)
        
        self.sector_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sector_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sector_table.setSortingEnabled(False)
        s_header.sectionClicked.connect(lambda idx: self._on_header_clicked("sector", idx))
        bottom_lay.addWidget(self.sector_table)
        main_layout.addWidget(bottom_frame, stretch=3)

        self.stock_table.code_clicked.connect(self._on_stock_clicked)
        self.stock_table.code_double_clicked.connect(self._on_stock_double_clicked)
        
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self._on_stock_context_menu)
        
        self.stock_table.currentCellChanged.connect(self._on_stock_key_nav)

        self.sector_table.cellClicked.connect(self._on_sector_clicked)
        self.sector_table.cellDoubleClicked.connect(self._on_sector_double_clicked)
        self.sector_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sector_table.customContextMenuRequested.connect(self._on_sector_context_menu)

        self.sector_table.currentCellChanged.connect(
            lambda r, c, pr, pc: self._on_sector_clicked(r, c)
        )

        self.stock_table.horizontalHeader().sectionResized.connect(self._save_ui_state)
        self.sector_table.horizontalHeader().sectionResized.connect(self._save_ui_state)


    def closeEvent(self, event):
        try:
            self._save_ui_state()
            self.save_window_position_qt_visual(self, "BiddingRacingRhythmPanel")
        except: pass
        self.closed.emit()
        super().closeEvent(event)

    def _save_ui_state(self):
        try:
            updates = {
                "stock_header": self.stock_table.horizontalHeader().saveState().toHex().data().decode(),
                "sector_header": self.sector_table.horizontalHeader().saveState().toHex().data().decode(),
                "reset_cycle_mins": self._reset_cycle_mins
            }
            _save_racing_config(updates)
        except Exception as e:
            logger.debug(f"Save UI state failed: {e}")

    def _restore_ui_state(self):
        try:
            conf = _get_racing_config()
            if not conf:
                self.stock_table.resizeColumnsToContents()
                self.sector_table.resizeColumnsToContents()
                return

            if "reset_cycle_mins" in conf:
                self._reset_cycle_mins = conf["reset_cycle_mins"]
                if hasattr(self, 'cycle_label'):
                    self.cycle_label.setText(f"📊 起点参考周期: {self._reset_cycle_mins}m")
            
            if "stock_header" in conf:
                self.stock_table.horizontalHeader().restoreState(QByteArray.fromHex(conf["stock_header"].encode()))
            else:
                self.stock_table.resizeColumnsToContents()
                
            if "sector_header" in conf:
                self.sector_table.horizontalHeader().restoreState(QByteArray.fromHex(conf["sector_header"].encode()))
            else:
                self.sector_table.resizeColumnsToContents()
        except Exception as e:
            logger.debug(f"Restore UI state failed: {e}")
            self.stock_table.resizeColumnsToContents()
            self.sector_table.resizeColumnsToContents()

    def _on_pie_filter(self, category):
        if category == "ALL":
            self.pie_widget.selected_category = None
        else:
            self.pie_widget.selected_category = category
        self.update_visuals()

    def _on_stock_clicked(self, code, name):
        self._execute_linkage(code, name)

    def _on_stock_double_clicked(self, code, name):
        self._execute_linkage(code, name, source="racing_double_click")

    def _on_stock_key_nav(self, row, col, prev_row, prev_col):
        """处理个股表键盘导航联动"""
        if row < 0 or row == prev_row: return
        code_item = self.stock_table.item(row, 0)
        name_item = self.stock_table.item(row, 1)
        if code_item and name_item:
            self._on_stock_clicked(code_item.text(), name_item.text())

    def _on_stock_context_menu(self, pos):
        """个股表右键菜单"""
        item = self.stock_table.itemAt(pos)
        if not item: return
        row = item.row()
        code = self.stock_table.item(row, 0).text()
        name = self.stock_table.item(row, 1).text()
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #005BB7; }")
        
        act_viz = menu.addAction(f"📊 联动可视化 ({name})")
        act_viz.triggered.connect(lambda: self._execute_linkage(code, name, source="racing_context_viz"))
        
        menu.addSeparator()
        act_copy = menu.addAction("📋 复制代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.stock_table.viewport().mapToGlobal(pos))

    def _on_sector_context_menu(self, pos):
        """板块表右键菜单"""
        item = self.sector_table.itemAt(pos)
        if not item: return
        row = item.row()
        leader_item = self.sector_table.item(row, 2)
        if not leader_item: return
        
        import re
        text = leader_item.text()
        match = re.search(r'\((\d{6})\)', text)
        if match:
            code = match.group(1)
            name = text.split("(")[0].strip()
            
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #005BB7; }")
            
            act_viz = menu.addAction(f"📊 联动可视化 (龙头: {name})")
            act_viz.triggered.connect(lambda: self._execute_linkage(code, name, source="racing_sector_context_viz"))
            
            menu.exec(self.sector_table.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event):
        """支持 Enter 键快速触发联动"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.stock_table.hasFocus():
                row = self.stock_table.currentRow()
                if row >= 0:
                    code = self.stock_table.item(row, 0).text()
                    name = self.stock_table.item(row, 1).text()
                    self._execute_linkage(code, name, source="racing_key_enter")
                    return
            elif self.sector_table.hasFocus():
                row = self.sector_table.currentRow()
                if row >= 0:
                    self._on_sector_clicked(row, 0)
                    return
        super().keyPressEvent(event)

    def _on_sector_clicked(self, row, col):
        """单击联动板块龙头"""
        item = self.sector_table.item(row, 2)
        if item:
            import re
            text = item.text()
            match = re.search(r'\((\d{6})\)', text)
            if match:
                code = match.group(1)
                name = text.split("(")[0].strip()
                self._execute_linkage(code, name, source="racing_sector_link")

    def _on_sector_double_clicked(self, row, col):
        """双击打开板块领军个股详情弹窗"""
        item = self.sector_table.item(row, 0) # 板块名称列
        if not item: return
        sec_name = item.text()
        
        dialog = SectorDetailDialog(sec_name, self.detector, self._execute_linkage, parent=self)
        dialog.show()

    def _on_header_clicked(self, table_type, logical_index):
        if table_type == "stock":
            if self._sort_col == logical_index:
                self._sort_order = Qt.SortOrder.AscendingOrder if self._sort_order == Qt.SortOrder.DescendingOrder else Qt.SortOrder.DescendingOrder
            else:
                self._sort_col = logical_index
                self._sort_order = Qt.SortOrder.DescendingOrder
            self.stock_table.horizontalHeader().setSortIndicator(logical_index, self._sort_order)
            self.stock_table.scrollToTop()
        else: # sector
            if self._sort_col_sector == logical_index:
                self._sort_order_sector = Qt.SortOrder.AscendingOrder if self._sort_order_sector == Qt.SortOrder.DescendingOrder else Qt.SortOrder.DescendingOrder
            else:
                self._sort_col_sector = logical_index
                self._sort_order_sector = Qt.SortOrder.DescendingOrder
            self.sector_table.horizontalHeader().setSortIndicator(logical_index, self._sort_order_sector)
            self.sector_table.scrollToTop()
        
        # 强制触发重绘，即使数据版本未变 (解决点击表头排序无反应的问题)
        self._last_data_version = -1 
        self.update_visuals()
        self._save_ui_state()

    def _on_cycle_changed(self, val):
        self._reset_cycle_mins = val
        if hasattr(self, 'cycle_label'):
            self.cycle_label.setText(f"📊 起点参考周期: {val}m")
        self._save_ui_state()

    def _adjust_cycle(self, offset):
        new_val = max(5, min(240, self._reset_cycle_mins + offset))
        self._on_cycle_changed(new_val)

    def _manual_reset_anchors(self):
        """[IMMEDIATE] 瞬间重置 DFF 与起点涨幅 (上下同步) - 修复死锁"""
        if self.detector:
            # 1. 首先调用 Detector 内部带锁的方法 (内部会申请并释放锁)
            self.detector.reset_observation_anchors()
            
            # 2. 然后再申请锁来进行手动内存操作，避免重入死锁
            with self.detector._lock:
                for ts in self.detector._tick_series.values():
                    ts.pct_diff = 0.0
                    ts.price_diff = 0.0
                for sec in self.detector.active_sectors.values():
                    sec['leader_pct_diff'] = 0.0
            
            # 3. 记录历史快照
            snap = self._create_anchor_snapshot()
            if snap: self._add_to_history(snap)

            curr_time = getattr(self.detector, 'last_data_ts', 0)
            if curr_time == 0: curr_time = time.time()
            
            self._last_anchor_reset_data_ts = curr_time
            self._last_data_version = -1 
            self.update_visuals()
            logger.info("⚡ [Panel] 已完成即时全局基准重置并存入历史。")
            
    def _check_auto_anchor(self):
        """[EMERGENCY] 5秒后兜底检查是否捕捉到起点"""
        if not self._anchor_history and self.detector:
            snap = self._create_anchor_snapshot()
            if snap and len(snap["anchors"]) > 10:
                self._add_to_history(snap)
                self._apply_history_anchor(0)
                logger.info(f"🚩 [Panel] 兜底逻辑成功捕捉并自动应用初始起点 ({len(snap['anchors'])} 只)。")

    def _create_anchor_snapshot(self):
        """记录当前所有个股的价格锚点快照"""
        if not self.detector: return None
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        if curr_time == 0: curr_time = time.time()
        with self.detector._lock:
            # [关键] 记录当前成交价作为快照基准
            anchors = {code: ts.current_price for code, ts in self.detector._tick_series.items() if ts.current_price > 0}
            return {"ts": curr_time, "anchors": anchors}

    def _add_to_history(self, snapshot):
        if not snapshot: return
        self._anchor_history.append(snapshot)
        if len(self._anchor_history) > 6:
            self._anchor_history.pop(0)
        self._refresh_history_buttons()

    def _refresh_history_buttons(self):
        # 清空现有按钮
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 重新生成按钮
        for i, snap in enumerate(self._anchor_history):
            t_str = datetime.datetime.fromtimestamp(snap["ts"]).strftime("%H:%M")
            btn = QPushButton(f"📍 起点{i+1}({t_str})")
            btn.setFixedSize(82, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { 
                    background: #1C1C1E; color: #00FFCC; border: 1px solid #333; 
                    border-radius: 3px; font-size: 9px; font-family: 'Segoe UI';
                }
                QPushButton:hover { background: #2C2C2E; border: 1px solid #00FFCC; color: white; }
            """)
            btn.clicked.connect(lambda checked, idx=i: self._apply_history_anchor(idx))
            self.history_layout.addWidget(btn)

    def _apply_history_anchor(self, idx):
        """恢复历史锚点"""
        if idx >= len(self._anchor_history): return
        snap = self._anchor_history[idx]
        if self.detector:
            with self.detector._lock:
                # 1. 恢复价格锚点
                for code, price in snap["anchors"].items():
                    if code in self.detector._tick_series:
                        ts = self.detector._tick_series[code]
                        ts.price_anchor = price
                        # [IMMEDIATE] 瞬间重算 pct_diff，确保 UI 瞬间看到变化
                        if ts.last_close > 0:
                            ts.pct_diff = (ts.current_price - ts.price_anchor) / ts.last_close * 100.0
                        else:
                            ts.pct_diff = 0.0
                
                # 2. 同步更新板块数据中的龙头 DFF，确保上下表一致
                for sec_name, sec_data in self.detector.active_sectors.items():
                    leader_code = sec_data.get('leader_code')
                    if leader_code and leader_code in self.detector._tick_series:
                        l_ts = self.detector._tick_series[leader_code]
                        sec_data['leader_pct_diff'] = l_ts.pct_diff
            
            # 3. 重置自动刷新计时器
            self._last_anchor_reset_data_ts = getattr(self.detector, 'last_data_ts', time.time())
            self._last_data_version = -1
            self.update_visuals()
            logger.info(f"♻️ [Panel] 已恢复至历史起点 {idx+1} ({datetime.datetime.fromtimestamp(snap['ts']).strftime('%H:%M:%S')})")

    def _execute_linkage(self, code, name="", source="racing_panel"):
        if not code or self._select_code == str(code):
            return
        self._select_code = str(code)
        if self.sender:
            try:
                self.sender.send(str(code))
            except Exception: pass
        
        if self.main_app and self.on_code_callback:
            try:
                if hasattr(self.main_app, 'tk_dispatch_queue'):
                    if getattr(self.main_app, "_vis_enabled_cache", False):
                        if hasattr(self.main_app, 'open_visualizer'):
                            self.main_app.tk_dispatch_queue.put(lambda: self.main_app.open_visualizer(str(code)))
                    self.main_app.tk_dispatch_queue.put(lambda: self.on_code_callback(str(code)))
                else:
                    self.on_code_callback(str(code))
            except Exception: pass

    def update_visuals(self):
        if not self.detector: return
        if self._is_rendering: return
        
        # [NEW] 自动捕捉首个起点 (仅在历史为空时执行一次，优先于版本检查)
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        if curr_time > 0 and not self._anchor_history:
            snap = self._create_anchor_snapshot()
            if snap and len(snap["anchors"]) > 0:
                self._add_to_history(snap)
                self._apply_history_anchor(0)
                logger.debug(f"🚩 [Panel] 捕获并激活全天首个起点 ({len(snap['anchors'])} 只个股)。")

        now = time.time()
        if now - self._last_ui_update_ts < 0.1:
            if self._table_highlights: self._refresh_fading_only() 
            return
        self._last_ui_update_ts = now
        curr_ver = getattr(self.detector, 'data_version', 0)
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        
        # [NEW] 周期性自动重置基准锚点
        if curr_time > 0:
            if self._last_anchor_reset_data_ts == 0:
                self._last_anchor_reset_data_ts = curr_time
            
            interval_sec = self._reset_cycle_mins * 60
            if curr_time - self._last_anchor_reset_data_ts > interval_sec:
                logger.info(f"⏰ [Panel] 到达基准重置周期 ({self._reset_cycle_mins} min), 正在执行全局锚点刷新...")
                self.detector.reset_observation_anchors()
                self._last_anchor_reset_data_ts = curr_time
                curr_ver = -1 # 强制后续刷新

        if curr_ver == self._last_data_version and curr_time == getattr(self, "_last_rendered_time", 0):
            if self._table_highlights: self._refresh_fading_only()
            return
        self._is_rendering = True
        try:
            with self.detector._lock:
                raw_ts_list = list(self.detector._tick_series.values())
                active_sectors = list(self.detector.active_sectors.values())
            
            # --- 2. [WORK-ZONE] 锁外分析计算 ---
            # [🚀 优化6] 视图数据扁平化 (Idx: 0:code, 1:name, 2:score, 3:sig, 4:pct, 5:diff, 6:dff)
            active_ts = [ts for ts in raw_ts_list if ts.score > 0.5 or ts.current_pct != 0]
            dist = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 0}
            
            # [NEW] 角色判定函数，用于分布统计与过滤
            def get_role(ts):
                is_leader = (ts.market_role == "主帅" or (ts.score > 60 and ts.first_breakout_ts > 0))
                if is_leader: return "龙头"
                is_confirmed = any(word in ts.pattern_hint for word in ["确认", "突破", "确核", "V反", "SBC"])
                if is_confirmed: return "确核"
                if ts.score > getattr(self.detector, 'score_threshold', 1.0): return "跟涨"
                return "静默"

            filtered_ts = []
            sel_cat = self.pie_widget.selected_category
            for ts in active_ts:
                role = get_role(ts)
                dist[role] += 1
                if not sel_cat or role == sel_cat:
                    filtered_ts.append(ts)
            
            def flatten_ts(ts):
                return (ts.code, ts.name, ts.score, ts.signal_count, ts.current_pct, ts.pct_diff, ts.dff)

            self.stock_table.setUpdatesEnabled(False)
            self.sector_table.setUpdatesEnabled(False)
            try:
                if getattr(self, "_last_dist", None) != dist:
                    self.pie_widget.set_data(dist)
                    self._last_dist = dist.copy()
                
                selected_row = self.stock_table.currentRow()
                selected_item = self.stock_table.item(selected_row, 0)
                selected_code = selected_item.text() if selected_item else ""
                scroll_pos = self.stock_table.verticalScrollBar().value()
                
                sec_row = self.sector_table.currentRow()
                sec_item = self.sector_table.item(sec_row, 0)
                sec_name = sec_item.text() if sec_item else ""
                sec_scroll = self.sector_table.verticalScrollBar().value()

                # --- [🚀 优化2] 手动排序逻辑 ---
                sort_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'pct_diff', 6:'dff'}
                s_attr = sort_attr_map.get(self._sort_col, 'score')
                is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
                
                # 执行排行榜处理 (基于过滤后的结果)
                sorted_raw = sorted(filtered_ts, key=lambda x: (getattr(x, s_attr), x.code), reverse=is_rev)[:10]
                flattened_ts = [flatten_ts(ts) for ts in sorted_raw]
                
                self.stock_table.blockSignals(True)
                self.sector_table.blockSignals(True)
                self._update_table_optimized(self.stock_table, flattened_ts)
                
                sort_attr_map_sector = {0:'sector', 1:'score', 2:'leader_name', 3:'leader_pct', 4:'leader_start_pct', 5:'leader_pct_diff'}
                s_attr_sec = sort_attr_map_sector.get(self._sort_col_sector, 'score')
                is_rev_sec = (self._sort_order_sector == Qt.SortOrder.DescendingOrder)
                
                # [🚀 优化] 板块表手动排序逻辑
                def get_sec_val(sec, attr):
                    if attr == 'leader_start_pct':
                        return sec.get('leader_pct', 0) - sec.get('leader_pct_diff', 0)
                    return sec.get(attr, 0)

                # 全量排序结果
                all_sorted_sectors = sorted(
                    active_sectors, 
                    key=lambda x: (get_sec_val(x, s_attr_sec), x.get('sector', '')), 
                    reverse=is_rev_sec
                )

                # [🚀 极致去重] 龙头代码+名称 双重去重逻辑
                unique_leader_sectors = []
                seen_leaders = set()
                for sec in all_sorted_sectors:
                    # 提取并标准化代码和名称
                    l_code = str(sec.get('leader', '')).strip()
                    l_name = str(sec.get('leader_name', '')).strip()
                    
                    # 生成唯一标识符：代码优先，名称补充
                    l_id = l_code if (l_code and l_code != 'None') else l_name
                    
                    if l_id:
                        if l_id in seen_leaders:
                            continue
                        seen_leaders.add(l_id)
                    
                    unique_leader_sectors.append(sec)
                    if len(unique_leader_sectors) >= 10:
                        break

                self._update_sector_table_optimized(self.sector_table, unique_leader_sectors)
                
                if selected_code:
                    for r in range(self.stock_table.rowCount()):
                        it = self.stock_table.item(r, 0)
                        if it and it.text() == selected_code:
                            if self.stock_table.currentRow() != r: self.stock_table.setCurrentCell(r, 0)
                            break
                if sec_name:
                    for r in range(self.sector_table.rowCount()):
                        it = self.sector_table.item(r, 0)
                        if it and it.text() == sec_name:
                            if self.sector_table.currentRow() != r: self.sector_table.setCurrentCell(r, 0)
                            break
                if abs(self.stock_table.verticalScrollBar().value() - scroll_pos) > 1:
                    self.stock_table.verticalScrollBar().setValue(scroll_pos)
                if abs(self.sector_table.verticalScrollBar().value() - sec_scroll) > 1:
                    self.sector_table.verticalScrollBar().setValue(sec_scroll)
            finally:
                self.stock_table.blockSignals(False)
                self.sector_table.blockSignals(False)
                self.stock_table.setUpdatesEnabled(True)
                self.sector_table.setUpdatesEnabled(True)
            self._last_data_version = curr_ver
            self._last_rendered_time = curr_time
        except Exception as e:
            import traceback
            logger.error(f"❌ [RacingPanel] Update Error: {e}\n{traceback.format_exc()}")
        finally:
            self._is_rendering = False



    def _update_cell(self, table, row, col, text, color=None, align=None, is_numeric=True):
        it = table.item(row, col)
        if not it:
            it = NumericTableWidgetItem(text) if is_numeric else QTableWidgetItem(text)
            if color: it.setForeground(color)
            if align: it.setTextAlignment(align)
            table.setItem(row, col, it)
            return True
        if it.text() != text:
             it.setText(text)
             if color: it.setForeground(color)
             return True 
        return False

    def _update_table_optimized(self, table, flattened_data):
        is_first_init = table.rowCount() == 0
        if table.rowCount() != len(flattened_data):
            table.setRowCount(len(flattened_data))
        for i, row_data in enumerate(flattened_data):
            code, name, score, sig, pct, diff, dff = row_data
            self._update_cell(table, i, 0, code, is_numeric=False)
            self._update_cell(table, i, 1, name, is_numeric=False)
            score_txt = str(round(score, 1))
            if self._update_cell(table, i, 2, score_txt, self._UI_CACHE["COLOR_GOLD"]):
                if not is_first_init: self._table_highlights[("stock", code, 2)] = time.time()
            self._apply_flash_effect(table.item(i, 2), ("stock", code, 2))
            sig_txt = f"{sig}" if sig > 0 else ""
            if self._update_cell(table, i, 3, sig_txt, self._UI_CACHE["COLOR_CYAN"], Qt.AlignmentFlag.AlignCenter):
                if not is_first_init: self._table_highlights[("stock", code, 3)] = time.time()
            self._apply_flash_effect(table.item(i, 3), ("stock", code, 3))
            pct_text = f"{pct:+.2f}%"
            c_pct = self._UI_CACHE["COLOR_RED"] if pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 4, pct_text, c_pct):
                if not is_first_init: self._table_highlights[("stock", code, 4)] = time.time()
            self._apply_flash_effect(table.item(i, 4), ("stock", code, 4))
            # 6. DFF (强制使用切片涨幅 diff, 确保锚点变动时 UI 100% 同步)
            dff_txt = f"{diff:+.2f}%"
            c_dff = self._UI_CACHE["COLOR_RED"] if diff > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if diff < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 6, dff_txt, c_dff):
                if not is_first_init: self._table_highlights[("stock", code, 6)] = time.time()
            self._apply_flash_effect(table.item(i, 6), ("stock", code, 6))
            
            # 使用本次切片的 diff 来反推当时起点的涨幅
            l_start_pct = pct - diff
            start_txt = f"{l_start_pct:+.2f}%"
            c_start = self._UI_CACHE["COLOR_RED"] if l_start_pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_start_pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 5, start_txt, c_start):
                if not is_first_init: self._table_highlights[("stock", code, 5)] = time.time()
            self._apply_flash_effect(table.item(i, 5), ("stock", code, 5))

    def _update_sector_table_optimized(self, table, sectors):
        """[PERF] 板块表极限渲染优化"""
        is_first_init = table.rowCount() == 0
        if table.rowCount() != len(sectors):
            table.setRowCount(len(sectors))
            
        for i, sec in enumerate(sectors):
            s_name = sec.get('sector', '未知')
            self._update_cell(table, i, 0, s_name, is_numeric=False)
            
            # 1. 强度得分
            score = round(sec.get('score', 0), 1)
            if self._update_cell(table, i, 1, str(score), self._UI_CACHE["COLOR_CYAN"]):
                if not is_first_init: self._table_highlights[("sector", s_name, 1)] = time.time()
            self._apply_flash_effect(table.item(i, 1), ("sector", s_name, 1))
                
            # 2. 领涨龙头
            l_total_pct = sec.get('leader_pct', 0.0)
            l_dff = sec.get('leader_pct_diff', 0.0)
            l_start_pct = l_total_pct - l_dff
            leader_display = f"{sec.get('leader_name')} ({sec.get('leader')})"
            self._update_cell(table, i, 2, leader_display, is_numeric=False)
                
            # 3. 龙头总涨幅
            l_pct_text = f"{l_total_pct:+.2f}%"
            c_pct = self._UI_CACHE["COLOR_RED"] if l_total_pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_total_pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 3, l_pct_text, c_pct):
                if not is_first_init: self._table_highlights[("sector", s_name, 3)] = time.time()
            self._apply_flash_effect(table.item(i, 3), ("sector", s_name, 3))
            
            # 4. 起点涨幅
            start_txt = f"{l_start_pct:+.2f}%"
            c_start = self._UI_CACHE["COLOR_RED"] if l_start_pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_start_pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 4, start_txt, c_start):
                if not is_first_init: self._table_highlights[("sector", s_name, 4)] = time.time()
            self._apply_flash_effect(table.item(i, 4), ("sector", s_name, 4))

            # 5. 龙头DFF
            dff_txt = f"{l_dff:+.2f}%"
            c_dff = self._UI_CACHE["COLOR_RED"] if l_dff > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_dff < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 5, dff_txt, c_dff):
                if not is_first_init: self._table_highlights[("sector", s_name, 5)] = time.time()
            self._apply_flash_effect(table.item(i, 5), ("sector", s_name, 5))

            # 6. 联动详情
            followers = sec.get('followers', [])
            f_txt = ",".join([f"{f['name']}({f['pct']:+.1f}%)" for f in followers[:3]])
            if self._update_cell(table, i, 6, f_txt, is_numeric=False):
                if not is_first_init: self._table_highlights[("sector", s_name, 6)] = time.time()
            self._apply_flash_effect(table.item(i, 6), ("sector", s_name, 6))

    def _refresh_fading_only(self):
        if not self._table_highlights: return
        for key in list(self._table_highlights.keys()):
            table_type, group_id, col = key
            table = self.stock_table if table_type == "stock" else self.sector_table
            found_row = -1
            for r in range(table.rowCount()):
                it0 = table.item(r, 0)
                if it0 and it0.text() == group_id:
                    found_row = r
                    break
            if found_row != -1:
                item = table.item(found_row, col)
                if item: self._apply_flash_effect(item, key)
            else: self._table_highlights.pop(key, None)

    def _apply_flash_effect(self, item, key):
        if item is None: return
        now = time.time()
        last_t = self._table_highlights.get(key, 0)
        if last_t == 0:
            item.setBackground(QColor(0, 0, 0, 0))
            return
        diff = now - last_t
        if diff < 0.6: 
            alpha = int(max(0, (0.6 - diff) / 0.6) * 60)
            item.setBackground(QColor(255, 215, 0, alpha))
        else:
            item.setBackground(QColor(0, 0, 0, 0))
            self._table_highlights.pop(key, None)

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = BiddingRacingRhythmPanel()
    window.show()
    sys.exit(app.exec())

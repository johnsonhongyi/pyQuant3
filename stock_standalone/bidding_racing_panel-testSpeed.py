# -*- coding: utf-8 -*-
import math
import os
import json
import time
import datetime
import heapq
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
    QFrame, QTableView, QHeaderView,
    QAbstractItemView, QPushButton,
    QMenu, QApplication, QDialog
)
from queue import Queue, Empty
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QPointF, QSize, QTimer, QByteArray, QAbstractTableModel, QThread
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QConicalGradient, 
    QLinearGradient, QRadialGradient, QPolygon, QPainterPath
)
from operator import itemgetter

from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger(name=__name__, level=LoggerFactory.WARNING)

# ==============================================================================
# [🚀 架构级优化] 高性能数据模型与视图
# ==============================================================================

class FastRacingModel(QAbstractTableModel):
    """
    极致性能模型 - 零 Object 创建，直接驱动视图。
    """
    def __init__(self, headers, ui_cache, parent=None):
        super().__init__(parent)
        self._headers = headers
        self._data = [] # List of tuples
        self._display_cache = [] # List[List[str]] 预格式化缓存
        self._cache = ui_cache
        self._highlights = {} # (obj_id, col) -> start_time
        self._last_data_map = {} # (obj_id, col) -> val
        self._last_update_ts = 0
        
        # 预定义有效 Role 集合，拒绝无效请求
        self._valid_roles = {
            Qt.ItemDataRole.DisplayRole, 
            Qt.ItemDataRole.ForegroundRole, 
            Qt.ItemDataRole.BackgroundRole, 
            Qt.ItemDataRole.TextAlignmentRole
        }

    def rowCount(self, parent=None): return len(self._data)
    def columnCount(self, parent=None): return len(self._headers)

    def update_data(self, new_data, obj_type="stock", current_ts=None):
        """[🚀 极致优化] 行级脏更新 + 二维缓存"""
        is_init = len(self._data) == 0
        now = current_ts or time.time()
        self._last_update_ts = now
        
        dirty_rows = set()
        watch_cols = [2, 3, 4, 5, 6] 
        col_count = len(self._headers)

        # 1. 脏检查与行级差异追踪
        for row_idx, row_data in enumerate(new_data):
            obj_id = row_data[0]
            row_is_dirty = False
            for col in watch_cols:
                if col >= len(row_data): continue
                val = row_data[col]
                key = (obj_id, col)
                if key in self._last_data_map:
                    if self._last_data_map[key] != val:
                        if not is_init: self._highlights[key] = now
                        self._last_data_map[key] = val
                        row_is_dirty = True
                else:
                    self._last_data_map[key] = val
                    row_is_dirty = True
            
            if row_is_dirty:
                dirty_rows.add(row_idx)

        # 2. 增量刷新策略 - [🚀 关键优化] 在 Top 10 列表，全量 Range 更新比逐行 emit 快得多
        if len(new_data) == len(self._data) and not is_init:
            self._data = new_data
            if dirty_rows:
                # 合并为单一区间信号，减少 Qt 内部 layout 消耗
                self.dataChanged.emit(self.index(0, 0), self.index(len(new_data)-1, col_count-1))
        else:
            self.beginResetModel()
            self._data = new_data
            self.endResetModel()
            
        # 3. 定期清理
        if len(self._highlights) > 1000:
            expired_keys = [k for k, t in self._highlights.items() if now - t > 1.0]
            for k in expired_keys: self._highlights.pop(k, None)
            
        return len(dirty_rows) > 0

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        # [🚀 极致优化] 拦截无效 Role 请求
        if role not in self._valid_roles: return None
        if not index.isValid(): return None
        
        row, col = index.row(), index.column()
        if row >= len(self._data): return None
        item = self._data[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return item[col] # 直接返回预格式化值
            
        if role == Qt.ItemDataRole.ForegroundRole:
            if col in [4, 5, 6]:
                txt = item[col]
                if '-' in txt: return self._cache["COLOR_GREEN"]
                if '+' in txt: return self._cache["COLOR_RED"]
                return Qt.GlobalColor.white
            if col == 2: return self._cache["COLOR_GOLD"]
            if col == 3: return self._cache["COLOR_CYAN"]
            return Qt.GlobalColor.white

        if role == Qt.ItemDataRole.BackgroundRole:
            # 高频逻辑：检查高亮动画
            key = (item[0], col)
            if key in self._highlights:
                diff = self._last_update_ts - self._highlights[key]
                if diff < 0.6:
                    idx = int(diff * 100)
                    if idx < 61: return self._cache["FLASH_GRADIENTS"][idx]
                else:
                    self._highlights.pop(key, None)
            return self._cache["COLOR_TRANSPARENT"]

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col >= 2 and col <= 6: return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

class FastRacingView(QTableView):
    """高性能组件视角，模拟 EnhancedTableWidget 的交互"""
    code_clicked = pyqtSignal(str, str)
    code_double_clicked = pyqtSignal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setMouseTracking(True)
        
        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)
        
    def _on_clicked(self, index):
        model = self.model()
        if not model: return
        row = index.row()
        # 默认 0 位代码，1 位名称
        data = model._data[row]
        self.code_clicked.emit(str(data[0]), str(data[1]))
        
    def _on_double_clicked(self, index):
        model = self.model()
        if not model: return
        row = index.row()
        data = model._data[row]
        self.code_double_clicked.emit(str(data[0]), str(data[1]))

    def scrollToTop(self):
        self.verticalScrollBar().setValue(0)

    def trigger_highlight_repaints(self):
        """[🚀 批量渲染] 废弃循环 visualRect，直接触发统一局部重绘"""
        model = self.model()
        if model and model._highlights:
            self.viewport().update()

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
        
        self.table = FastRacingView()
        
        # [🚀 优化] 从父窗口继承 UI 缓存，避免重复创建 QColor 对象
        p = self.parent()
        ui_cache = getattr(p, '_UI_CACHE', None) if p else None
        if not ui_cache:
            ui_cache = {"COLOR_GOLD": QColor("#FFD700"), "COLOR_RED": QColor("#FF4444"), "COLOR_GREEN": QColor("#44CC44"), "COLOR_CYAN": QColor("#00FFCC"), "COLOR_TRANSPARENT": QColor(0,0,0,0)}
            
        self.model_data = FastRacingModel(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF"], ui_cache)
        self.table.setModel(self.model_data)
        
        self.table.setStyleSheet("""
            QTableView { background-color: #000; alternate-background-color: #111; color: #FFF; gridline-color: #222; outline: none; border: none; }
            QHeaderView::section { background-color: #222; color: #BBB; padding: 4px; border: 1px solid #333; }
        """)
        
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
            # 锁内仅获取引用快照
            member_ts_list = [self.detector._tick_series.get(c) for c in members if c in self.detector._tick_series]
        
        # 锁外执行排序与扁平化，避免阻塞主引擎
        col_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'pct_diff', 6:'pct_diff'}
        attr = col_attr_map.get(self._sort_col, 'score')
        is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
        
        member_ts_list.sort(key=lambda x: (getattr(x, attr, 0) if attr != 'pct_diff' else (x.current_pct - x.pct_diff)), reverse=is_rev)
        
        display_list = member_ts_list[:100]
        formatted = []
        for ts in display_list:
            # [🚀 极致优化] 预格式化所有单元格
            formatted.append((
                ts.code, ts.name, 
                f"{ts.score:.1f}", 
                str(getattr(ts, 'signal_count', 0)) if getattr(ts, 'signal_count', 0) > 0 else "",
                f"{ts.current_pct:+.2f}%",
                f"{(ts.current_pct - ts.pct_diff):+.2f}%",
                f"{ts.pct_diff:+.2f}%"
            ))
        self.model_data.update_data(formatted, obj_type="stock")

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
        idx = self.table.indexAt(pos)
        if not idx.isValid(): return
        row = idx.row()
        data = self.model_data._data[row]
        code, name = data[0], data[1]
        
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
        
        # [🚀 架构级优化] 计算与渲染分离
        self._latest_data_packet = None # 原子引用，避免 Queue 的抖动
        self.loader_thread = None
        
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
        # 预缓存 60 个 Alpha 阶梯的金色高亮，避免 data() 内部实时创建对象
        self._UI_CACHE["FLASH_GRADIENTS"] = [QColor(255, 215, 0, int((1.0 - i/60) * 80)) for i in range(61)]
        self._UI_CACHE_READY = True
        
        self._init_ui()
        
        self.sector_table.setSortingEnabled(False)
        
        # 启动后台数据生产者
        self._start_loader_thread()
        
        self.load_window_position_qt(self, "BiddingRacingRhythmPanel", default_width=1000, default_height=700)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_visuals)
        self.refresh_timer.start(300) # 300ms 平滑帧率
        
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
        
        self.stock_table = FastRacingView()
        self.stock_model = FastRacingModel(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF"], self._UI_CACHE)
        self.stock_table.setModel(self.stock_model)
        
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(80) 
        header.setMinimumSectionSize(30)
        self.stock_table.setColumnWidth(0, 65)
        self.stock_table.setColumnWidth(1, 75)
        
        self.stock_table.setStyleSheet("""
            QTableView {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #005BB7; 
                selection-color: white;
                outline: none;
                border: none;
            }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; color: #BBB; }
        """)
        
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
        
        self.sector_table = FastRacingView()
        self.sector_model = FastRacingModel(["板块名称", "强度得分", "领涨龙头", "龙头涨幅", "起点涨幅", "龙头DFF", "联动详情"], self._UI_CACHE)
        self.sector_table.setModel(self.sector_model)
        
        s_header = self.sector_table.horizontalHeader()
        s_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        s_header.setMinimumSectionSize(30)
        s_header.setDefaultSectionSize(100)
        self.sector_table.setColumnWidth(0, 80)
        self.sector_table.setColumnWidth(2, 110)
        
        self.sector_table.setStyleSheet("""
            QTableView {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #005BB7; 
                selection-color: white;
                outline: none;
                border: none;
            }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; color: #BBB; }
        """)
        
        s_header.sectionClicked.connect(lambda idx: self._on_header_clicked("sector", idx))
        bottom_lay.addWidget(self.sector_table)
        main_layout.addWidget(bottom_frame, stretch=3)

        self.stock_table.code_clicked.connect(self._on_stock_clicked)
        self.stock_table.code_double_clicked.connect(self._on_stock_double_clicked)
        
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self._on_stock_context_menu)
        
        self.stock_table.selectionModel().currentChanged.connect(
            lambda curr, prev: self._on_stock_key_nav(curr.row(), curr.column(), prev.row(), prev.column())
        )

        self.sector_table.clicked.connect(lambda idx: self._on_sector_clicked(idx.row(), idx.column()))
        self.sector_table.doubleClicked.connect(lambda idx: self._on_sector_double_clicked(idx.row(), idx.column()))
        self.sector_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sector_table.customContextMenuRequested.connect(self._on_sector_context_menu)

        self.sector_table.selectionModel().currentChanged.connect(
            lambda curr, prev: self._on_sector_clicked(curr.row(), curr.column())
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
        data = self.stock_model._data[row]
        self._on_stock_clicked(str(data[0]), str(data[1]))

    def _on_stock_context_menu(self, pos):
        """个股表右键菜单"""
        idx = self.stock_table.indexAt(pos)
        if not idx.isValid(): return
        row = idx.row()
        data = self.stock_model._data[row]
        code, name = data[0], data[1]
        
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
        idx = self.sector_table.indexAt(pos)
        if not idx.isValid(): return
        row = idx.row()
        data = self.sector_model._data[row]
        # data[2] 是 leader_display "Name (Code)"
        text = str(data[2])
        
        import re
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
                idx = self.stock_table.currentIndex()
                if idx.isValid():
                    row = idx.row()
                    data = self.stock_model._data[row]
                    self._execute_linkage(str(data[0]), str(data[1]), source="racing_key_enter")
                    return
            elif self.sector_table.hasFocus():
                idx = self.sector_table.currentIndex()
                if idx.isValid():
                    self._on_sector_clicked(idx.row(), idx.column())
                    return
        super().keyPressEvent(event)

    def _on_sector_clicked(self, row, col):
        """单击联动板块龙头"""
        if row < 0 or row >= len(self.sector_model._data): return
        data = self.sector_model._data[row]
        text = str(data[2]) # leader_display
        import re
        match = re.search(r'\((\d{6})\)', text)
        if match:
            code = match.group(1)
            name = text.split("(")[0].strip()
            self._execute_linkage(code, name, source="racing_sector_link")

    def _on_sector_double_clicked(self, row, col):
        """双击打开板块领军个股详情弹窗"""
        if row < 0 or row >= len(self.sector_model._data): return
        sec_name = str(self.sector_model._data[row][0])
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
            self.refresh_timer.start(100) # 激活时强制高频
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
    def _start_loader_thread(self):
        """主线程只负责展示，脏活累活全部丢给后台计算线程"""
        from threading import Thread
        class DataLoader(Thread):
            def __init__(self, panel):
                super().__init__(daemon=True)
                self.panel = panel
                self.running = True
                
            def run(self):
                last_ver = -1
                while self.running:
                    try:
                        det = self.panel.detector
                        if not det: 
                            time.sleep(0.5); continue
                        
                        curr_ver = getattr(det, 'data_version', 0)
                        if curr_ver == last_ver:
                            time.sleep(0.1); continue
                        
                        # 核心计算：锁内快照，锁外分析
                        with det._lock:
                            ticker_values = list(det._tick_series.values())
                            active_sectors = [sec.copy() for sec in det.active_sectors.values()]
                        
                        now = time.time()
                        dist = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 0}
                        filtered_snap = []
                        sel_cat = self.panel.pie_widget.selected_category
                        score_threshold = getattr(det, 'score_threshold', 1.0)
                        
                        # [🚀 计算移出主线程]
                        for ts in ticker_values:
                            score = ts.score
                            pct = ts.current_pct
                            role_hint = ts.pattern_hint
                            role_mark = ts.market_role
                            first_ts = ts.first_breakout_ts
                            
                            is_leader = (role_mark == "主帅" or (score > 60 and first_ts > 0))
                            if is_leader: role = "龙头"
                            elif any(word in role_hint for word in ["确认", "突破", "确核", "V反", "SBC"]): role = "确核"
                            elif score > score_threshold: role = "跟涨"
                            else: role = "静默"
                            
                            dist[role] += 1
                            if not sel_cat or role == sel_cat:
                                if score > 0.5 or pct != 0:
                                    filtered_snap.append((ts.code, ts.name, score, ts.signal_count, pct, pct - ts.pct_diff, ts.pct_diff))
                        
                        # 排序 & 预格式化
                        s_idx = {0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:6}.get(self.panel._sort_col, 2)
                        kf = itemgetter(s_idx, 0)
                        is_rev = (self.panel._sort_order == Qt.SortOrder.DescendingOrder)
                        
                        top_stocks = heapq.nlargest(10, filtered_snap, key=kf) if is_rev else heapq.nsmallest(10, filtered_snap, key=kf)
                        formatted_stocks = [
                            (x[0], x[1], f"{x[2]:.1f}", str(x[3]) if x[3]>0 else "", f"{x[4]:+.2f}%", f"{x[5]:+.2f}%", f"{x[6]:+.2f}%")
                            for x in top_stocks
                        ]
                        
                        # 板块数据生成 (同理移出)
                        s_idx_sec = {0:'sector', 1:'score', 2:'leader_name', 3:'leader_pct', 4:'leader_start_pct', 5:'leader_pct_diff'}.get(self.panel._sort_col_sector, 'score')
                        is_rev_sec = (self.panel._sort_order_sector == Qt.SortOrder.DescendingOrder)
                        
                        def get_sec_val(sec, attr):
                            if attr == 'leader_start_pct': return sec.get('leader_pct', 0) - sec.get('leader_pct_diff', 0)
                            return sec.get(attr, 0)

                        all_sorted_sectors = sorted(active_sectors, key=lambda x: (get_sec_val(x, s_idx_sec), x.get('sector', '')), reverse=is_rev_sec)
                        unique_sectors = []
                        seen_leaders = set()
                        for sec in all_sorted_sectors:
                            l_id = str(sec.get('leader', '')).strip() or str(sec.get('leader_name', '')).strip()
                            if l_id:
                                if l_id in seen_leaders: continue
                                seen_leaders.add(l_id)
                            
                            l_pct, l_dff = sec.get('leader_pct', 0.0), sec.get('leader_pct_diff', 0.0)
                            f_txt = ",".join([f"{f['name']}({f['pct']:+.1f}%)" for f in sec.get('followers', [])[:3]])
                            
                            unique_sectors.append((
                                sec.get('sector', '未知'), str(sec.get('score', 0)), f"{sec.get('leader_name')} ({sec.get('leader')})",
                                f"{l_pct:+.2f}%", f"{(l_pct - l_dff):+.2f}%", f"{l_dff:+.2f}%", f_txt
                            ))
                            if len(unique_sectors) >= 10: break
                        
                        # 保存到“最新包”引用
                        packet = {
                            "ver": curr_ver,
                            "ts": getattr(det, 'last_data_ts', now),
                            "dist": dist,
                            "stocks": formatted_stocks,
                            "sectors": unique_sectors
                        }
                        self.panel._latest_data_packet = packet
                        last_ver = curr_ver
                    except Exception as e:
                        logger.error(f"❌ [LoaderThread] Error: {e}")
                        time.sleep(1)
        
        self.loader_thread = DataLoader(self)
        self.loader_thread.start()

    def update_visuals(self):
        """[🚀 极致响应] 主线程只做：数据快照展示，完全解脱交互"""
        packet = self._latest_data_packet
        if packet is None: return
        
        # [1] 检查是否有新包
        if packet["ver"] != self._last_data_version:
            # 更新分布饼图
            if getattr(self, "_last_dist", None) != packet["dist"]:
                self.pie_widget.set_data(packet["dist"])
                self._last_dist = packet["dist"].copy()
            
            # 投递到模型
            self.stock_model.update_data(packet["stocks"], current_ts=time.time())
            self.sector_model.update_data(packet["sectors"], current_ts=time.time())
            
            self._last_data_version = packet["ver"]
            self._last_rendered_time = packet["ts"]
        else:
            # [2] 维持高亮重绘
            if len(self.stock_model._highlights) > 0 or len(self.sector_model._highlights) > 0:
                self.stock_table.trigger_highlight_repaints()
                self.sector_table.trigger_highlight_repaints()

    def closeEvent(self, event):
        if self.loader_thread:
            self.loader_thread.running = False
        self._save_ui_state()
        self.save_window_position_qt(self, "BiddingRacingRhythmPanel")
        super().closeEvent(event)



    # [🚀 架构重构] 已废弃旧版 QTableWidget 直接更新方法，逻辑已迁往 Model::update_data

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = BiddingRacingRhythmPanel()
    window.show()
    sys.exit(app.exec())

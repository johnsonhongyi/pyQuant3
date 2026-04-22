# -*- coding: utf-8 -*-
import math
import os
import json
import time
import datetime
import re
import traceback
import threading
import gzip
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGraphicsDropShadowEffect, QPushButton,
    QMenu, QApplication, QDialog, QSplitter, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QPointF, QSize, QTimer, QByteArray
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QConicalGradient, 
    QLinearGradient, QRadialGradient, QPolygon, QPainterPath
)

from tk_gui_modules.qt_table_utils import EnhancedTableWidget, NumericTableWidgetItem

class LabeledStockItem(QTableWidgetItem):
    """支持信号优先级排序的表格项 - 确保 ⚡ 和 🔔 能够被排在最前面 (权重越大越靠前)"""
    def __init__(self, text, sort_prio=0):
        super().__init__(text)
        self.sort_prio = sort_prio # 2:⚡, 1:🔔, 0:普通

    def __lt__(self, other):
        try:
            if hasattr(other, 'sort_prio'):
                if self.sort_prio != other.sort_prio:
                    # Qt 排序: Ascending 时调用 __lt__，由于我们要 Descending 时 ⚡ 在前，
                    # 那么 Ascending 时 ⚡ 应该在后，即 ⚡(2) > 普通(0)
                    return self.sort_prio < other.sort_prio
            return super().__lt__(other)
        except: return super().__lt__(other)

from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory, commonTips as cct
from alert_manager import get_alert_manager
logger = LoggerFactory.getLogger(name=__name__, level=LoggerFactory.WARNING)

GLOBAL_SCROLLBAR_STYLE = """
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 4px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #3A3A3C;
    min-height: 20px;
    border-radius: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    border: none;
    background: transparent;
    height: 4px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #3A3A3C;
    min-width: 20px;
    border-radius: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #555555;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""


# [🚀 DNA 统一分发] 模块级分发中枢：兼容 Tkinter 宿统与 Standalone Qt 进程
def dispatch_dna_audit(code_to_name, parent_widget=None):
    """
    DNA 审计分发中枢：支持 Tkinter 宿主分发与独立 Qt 进程降级启动
    """
    if not code_to_name:
        return
    
    # 1. 寻找主程序的 tk_dispatch_queue (Tkinter 环境)
    main_app = None
    p = parent_widget
    while p:
        if hasattr(p, 'main_app'):
            main_app = getattr(p, 'main_app', None)
            if main_app: break
        p = p.parent()
    
    if main_app and hasattr(main_app, 'tk_dispatch_queue') and hasattr(main_app, '_run_dna_audit_batch'):
        # 委托给主程序的 Tkinter 线程执行，脱离 Qt 循环
        main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(code_to_name))
        return
        
    # 2. 降级方案：如果是独立 Qt 进程运行 (Standalone Mode)
    logger.warning(f"📍 [Racing] 启动 DNA 降级审计 (Standalone) - 共 {len(code_to_name)} 只个股")
    
    def _standalone_worker():
        try:
            import tkinter as tk
            # 延迟导入，防止启动阶段 IO 负担
            from backtest_feature_auditor import audit_multiple_codes, show_dna_audit_report_window
            
            # 创建独立的 Tk root 并隐藏
            root = tk.Tk()
            root.withdraw()
            
            codes = list(code_to_name.keys())
            # 独立审计不传 end_date，默认使用最新数据
            summaries = audit_multiple_codes(codes, code_to_name=code_to_name)
            
            if summaries:
                # 显示报告窗口。注意：由于是独立线程，需要在这里阻塞 loop
                show_dna_audit_report_window(summaries, parent=root)
                root.mainloop()
            else:
                logger.error("❌ [Racing] 降级审计失败：未返回任何基因摘要")
                root.destroy()
        except Exception as e:
            logger.error(f"❌ [Racing] 降级审计崩溃: {e}")
            import traceback
            traceback.print_exc()

    # 启动守护线程执行审计，防止阻塞 PyQt6 UI
    t = threading.Thread(target=_standalone_worker, daemon=True)
    t.start()

# [🚀 极致性能] 模块级配置持久化 (GZIP + JSON)
def _get_racing_config_path():
    """获取标准化的绝对路径，确保集成与独立模式路径对齐"""
    try:
        base_dir = cct.get_base_path()
        path = os.path.join(base_dir, "snapshots", "bidding_racing_ui_state_v3.json.gz")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
    except:
        return "snapshots/bidding_racing_ui_state_v3.json.gz"

RACING_CONFIG_LOCK = threading.Lock() 

def _get_racing_config():
    """读取全局持久化配置"""
    path = _get_racing_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode('utf-8'))
    except Exception:
        return {}

def _save_racing_config(conf: dict):
    """保存配置并合并历史记录 - [🔒 线程安全版]"""
    path = _get_racing_config_path()
    with RACING_CONFIG_LOCK:
        try:
            old_conf = _get_racing_config()
            for k, v in conf.items():
                old_conf[k] = v
            with gzip.open(path, "wb") as f:
                f.write(json.dumps(old_conf).encode('utf-8'))
        except Exception as e:
            logger.error(f"❌ [RacingConfig] Save Failed: {e}")
        except Exception as e:
            logger.error(f"❌ [RacingConfig] Save Failed: {e}")

def get_racing_role(ts):
    is_leader = (ts.market_role == "主帅" or (ts.score > 60 and ts.first_breakout_ts > 0))
    if is_leader: return "龙头"
    is_confirmed = any(word in ts.pattern_hint for word in ["确认", "突破", "确核", "V反", "SBC"])
    if is_confirmed: return "确核"
    # [🚀 门槛下调] 只要有涨跌幅，就算作“跟涨”，确保饼图有颜色
    if ts.score > 0.5 or abs(ts.current_pct) > 0.01: return "跟涨"
    return "静默"


class RacingPieWidget(QWidget):
    """
    高性能交互式饼图 - 赛马场分类筛选指挥台
    """
    category_selected = pyqtSignal(str) # 筛选信号
    category_double_clicked = pyqtSignal(str) # 双击信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self.setMouseTracking(True)
        self.data = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 100}
        self.colors = {
            "龙头": QColor("#FF3B30"),  # 苹果红 (更有力)
            "确核": QColor("#FF9500"),  # 橙色
            "跟涨": QColor("#5856D6"),  # 紫色
            "静默": QColor("#3A3A3C")   # 稍亮一点的深灰，防止背景融合
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

    def mouseDoubleClickEvent(self, event):
        cat = self._get_hit_category(event.pos())
        if cat and cat != "ALL":
            self.category_double_clicked.emit(cat)

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
            # 强化边界感，确保 100% 占比时也能看到一个完整的圆环
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
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
        self.resize(850, 520)
        # [🚀 视觉升级] 移除嵌入式半透明感，锁定专业实色深幕
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setStyleSheet("""
            QWidget { background-color: #060608; color: #E0E0E0; font-family: 'Segoe UI', 'Microsoft YaHei'; }
            QDialog { border: 1px solid #333; }
        """)

        # 记忆位置
        # self.load_window_position_qt(self, "SectorDetail_Unified")
        
        self.setUpdatesEnabled(False)
        self._sort_col = 2 # 默认排序: 结构分
        self._sort_order = Qt.SortOrder.DescendingOrder
        
        # [NEW] 启动保护锁，防止初始化时的自动布局覆盖用户保存的列宽
        self._boot_lock = True
        self._is_height_doubled = False # [NEW] 高度翻倍状态位
        self._show_reason = False       # [NEW] 形态详情/理由显示标志 (默认关闭)
        
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

    def get_ui_state(self):
        """导出窗口状态用于统一管理"""
        try:
            return {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "column_widths": [self.table.columnWidth(i) for i in range(self.table.columnCount())],
                "show_reason": self._show_reason
            }
        except:
            return None

    def apply_ui_state(self, state, _retry_ts=None):
        """应用外部恢复的状态（带启动保护锁 + 超时兜底）"""
        if not state:
            return
        
        self._show_reason = state.get("show_reason", False)
        if hasattr(self, 'table'):
            self.table.setColumnHidden(7, not self._show_reason)

        # 初始化首次时间戳
        if _retry_ts is None:
            _retry_ts = time.time()

        try:
            # --- 启动保护锁 ---
            if hasattr(self, '_boot_lock') and self._boot_lock:
                # 超时 3 秒强制执行
                if time.time() - _retry_ts < 3:
                    QTimer.singleShot(
                        100, 
                        lambda: self.apply_ui_state(state, _retry_ts)
                    )
                    return
                # 超时后继续执行（兜底）
                # print("[UI_STATE] boot lock timeout, force apply")

            # --- 恢复 geometry ---
            if "geometry" in state:
                self.restoreGeometry(
                    QByteArray.fromHex(state["geometry"].encode())
                )

            # --- 恢复列宽 ---
            widths = state.get("column_widths")
            if widths and len(widths) == self.table.columnCount():
                header = self.table.horizontalHeader()
                header.blockSignals(True)
                try:
                    for i, w in enumerate(widths):
                        if w > 10:
                            self.table.setColumnWidth(i, w)
                finally:
                    header.blockSignals(False)

        except Exception as e:
            # 建议至少打日志，裸 except 很危险
            print(f"[UI_STATE] apply failed: {e}")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # [🚀 标题栏交互增强] 创建可交互标题区域
        self.header_frame = QFrame()
        self.header_frame.setObjectName("header_frame")
        self.header_frame.setStyleSheet("""
            QFrame#header_frame { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1A1E, stop:1 #060608); border-bottom: 2px solid #222; }
        """)
        self.header_frame.mouseDoubleClickEvent = lambda e: self._on_header_double_click(e)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(10)
        
        self.title_lbl = QLabel(f"🔥 {self.sector_name} - 个股明细")
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #00FFCC; letter-spacing: 1px;")
        header_layout.addWidget(self.title_lbl)
        
        header_layout.addStretch()
        
        self.btn_toggle_reason = QPushButton("理由: 关")
        self.btn_toggle_reason.setCheckable(True)
        self.btn_toggle_reason.setChecked(self._show_reason)
        self.btn_toggle_reason.setText("理由: 开" if self._show_reason else "理由: 关")
        self.btn_toggle_reason.setStyleSheet("""
            QPushButton { background-color: #333; color: #AAA; border: 1px solid #555; padding: 4px 8px; border-radius: 4px; font-size: 11px; }
            QPushButton:checked { background-color: #005BB7; color: white; border: 1px solid #00FFCC; }
            QPushButton:hover { border: 1px solid white; }
        """)
        self.btn_toggle_reason.clicked.connect(self._toggle_reason_column)
        header_layout.addWidget(self.btn_toggle_reason)

        self.btn_dna = QPushButton("🚀 DNA审计")
        self.btn_dna.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; padding: 4px 8px; border-radius: 4px; font-size: 11px;")
        self.btn_dna.clicked.connect(self._run_dna_audit_top20)
        header_layout.addWidget(self.btn_dna)
        
        layout.addWidget(self.header_frame)
        
        self.table = EnhancedTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF", "形态详情"])
        if self.table.horizontalHeaderItem(6):
            self.table.horizontalHeaderItem(6).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # [NEW] 形态详情列控制
        self.table.setColumnHidden(7, not self._show_reason)
        if self._show_reason:
            self.table.setColumnWidth(7, 180)

        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #060608; alternate-background-color: #0C0C10; color: #EEE; gridline-color: #1A1A1A; outline: none; border: none; }
            QHeaderView::section { background-color: #1A1A1E; color: #AAA; padding: 6px; border: none; border-right: 1px solid #222; border-bottom: 1px solid #222; font-weight: bold; }
            QTableWidget::item:selected { background-color: #004488; }
        """ + GLOBAL_SCROLLBAR_STYLE)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(90)
        
        self.table.code_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="sector_dialog_link"))
        self.table.code_double_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="sector_dialog_double"))
        
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # [统一管理] 停用实时列宽保存，由主面板统一落盘
        # self.table.horizontalHeader().sectionResized.connect(self._save_header_state)
        # 右键菜单支持 - [🚀 直出一层] 禁用基类默认菜单干扰
        self.table._enable_default_menu = False
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        layout.addWidget(self.table)
        

        
        # [🚀 新增] 底部统计信息栏
        self.status_lbl = QLabel("统计: --")
        self.status_lbl.setStyleSheet("color: #AAA; font-size: 11px; padding: 2px; background-color: #111; border-top: 1px solid #333;")
        layout.addWidget(self.status_lbl)

    def _on_header_double_click(self, event):
        """[🚀 交互增强] 双击标题栏高度翻倍/恢复"""
        if not self._is_height_doubled:
            # 记录当前高度并翻倍
            self._original_height_snap = self.height()
            screen_h = QApplication.primaryScreen().availableGeometry().height()
            # 计算翻倍后的高度，但不超过屏幕高度
            target_h = min(self._original_height_snap * 2, screen_h - 100)
            self.resize(self.width(), target_h)
            self._is_height_doubled = True
            logger.debug(f"📐 [Detail] {self.sector_name} 高度已翻倍至 {target_h}")
        else:
            # 恢复高度
            h = getattr(self, '_original_height_snap', 500)
            self.resize(self.width(), h)
            self._is_height_doubled = False
            logger.debug(f"📐 [Detail] {self.sector_name} 高度已恢复至 {h}")

    def _get_synthetic_score(self, ts):
        """[🚀 性能加速版] 动态合成显示分数"""
        try:
            # 优先尝试直接访问，消除 getattr 的字典查找开销
            main_score = ts.score
            if main_score < 0.01:
                activity_score = (getattr(ts, 'signal_count', 0) * 1.5) + (abs(ts.current_pct) * 0.2)
                return max(activity_score, getattr(ts, 'momentum_score', 0) * 0.05)
            return main_score
        except AttributeError:
            return 0.0

    def refresh_data(self):
        # [🚀 极速视口过滤] 如果窗口不可见，拒绝执行昂贵的重绘逻辑
        if not self.isVisible(): 
            return

        # [🚀 动态寻踪] 若当前探测器丢失，尝试从父面板动态“夺取”最新引用
        if not getattr(self, 'detector', None):
            if self.parent() and hasattr(self.parent(), 'detector'):
                self.detector = self.parent().detector
                
        if not self.detector:
            self.status_lbl.setText("❌ 探测器连接丢失，等待主程序响应...")
            return

        # --- [⚡ 报警专用逻辑] 优先级最高，用于处理虚拟板块 ---
        if self.sector_name == "🔔 实时报警":
            # [FIX] 从 active_sectors 直接获取已注册成员，确保与看板数据绝对对齐
            sec_dict = self.detector.active_sectors.get(self.sector_name, {})
            followers = sec_dict.get('followers', [])
            members = [f['code'] for f in followers]
            if not members:
                # 兜底：尝试从 AlertManager 获取（仅作实盘回退）
                members = get_alert_manager().get_alerted_codes()
            
            if not members:
                self.status_lbl.setText("ℹ️ 当前会话暂无报警品种...")
                self.table.setRowCount(0)
                return
            members = set(members)
        else:
            # [🚀 暴力自愈逻辑] 若映射表缺失，全量扫描并强制回写（彻底解决同步孤岛）
            members = self.detector.sector_map.get(self.sector_name)
            if not members:
                new_members = set()
                target_name = self.sector_name.strip()
                with self.detector._lock:
                    for code, ts in self.detector._tick_series.items():
                        # [🚀 多维字段匹配 + 复杂正则切分] 对齐主面板推导逻辑
                        cat_val = str(getattr(ts, 'category', '')) + " " + str(getattr(ts, 'block', ''))
                        if not cat_val or len(cat_val) < 2: continue
                        
                        # 使用正则表达式进行切分对比
                        cats = [c.strip() for c in re.split(r'[;；,，/\- ]', cat_val) if c.strip()]
                        if target_name in cats: 
                            new_members.add(code)
                
                if new_members:
                    self.detector.sector_map[self.sector_name] = new_members
                    members = new_members
                    # logger.info(f"✅ [Detail] '{self.sector_name}' 自愈成功，注入 {len(members)} 个成员")
                else:
                    self.status_lbl.setText(f"❌ '{self.sector_name}' 成员库仍处于冷启动状态...")
                    return
            
            # [🚀 新增] 更新标题栏强度得分
            sec_score = self.detector.active_sectors.get(self.sector_name, {}).get('score', 0.0)
            self.title_lbl.setText(f"{self.sector_name} - 明细 ({sec_score:.1f})")

        render_start_t = time.time()
        
        # [🚀 极致性能] 非阻塞锁：后台正在进行重算时，UI 层拒绝等待直接返回
        if not self.detector._lock.acquire(blocking=False): return
            
        try:
            data_list = [self.detector._tick_series[c] for c in members if c in self.detector._tick_series]
        finally:
            self.detector._lock.release()
            
        if not data_list:
            # [🚀 极速提示] 即使无数据也不白屏，显示占位
            self.table.setRowCount(0)
            self.status_lbl.setText(f"⚠️ '{self.sector_name}' 当前暂无活跃成分股行情")
            return

        # --- [🔒 锁外计算] 排序与统计全部移到临界区外执行，降低 GIL 竞争 ---
        col_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'start_pct', 6:'pct_diff'}
        attr = col_attr_map.get(self._sort_col, 'score')
        is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
        
        # 获取 SBC 注册表 (用于排序优先级判定)
        tracker = None
        if self.detector and self.detector.realtime_service:
            tracker = getattr(self.detector.realtime_service, 'emotion_tracker', None)
        sbc_registry = getattr(tracker, '_sbc_signals_registry', {}) if tracker else {}
        # 预计算合成评分 (用于锁外高性能排序)
        score_cache = {ts.code: self._get_synthetic_score(ts) for ts in data_list}

        def get_sort_key(ts):
            # [🚀 优先级排序增强] ⚡(2) > 🔔(1) > 无(0)
            has_alert = get_alert_manager().is_alerted(ts.code)
            has_sbc = ts.code in sbc_registry
            prio = 2 if has_sbc else (1 if has_alert else 0)
            
            if attr == 'start_pct': val = ts.current_pct - ts.pct_diff
            elif attr == 'pct_diff': val = ts.pct_diff
            elif attr == 'score': val = score_cache.get(ts.code, 0)
            else: val = getattr(ts, attr, 0)
            
            if attr == 'name':
                return (prio, val, ts.code)
            return (val, ts.code)
        
        data_list.sort(key=get_sort_key, reverse=is_rev)
        
        display_list = data_list[:100]
        flattened = []
        for ts in display_list:
            # [自适应节流] 只有在打开显示开关时才进行昂贵的理由提取
            reason = ""
            if self._show_reason:
                if ts.code in sbc_registry: reason = sbc_registry[ts.code].get('desc', '')
                if not reason: reason = getattr(ts, 'pattern_hint', "")

            flattened.append((
                ts.code, ts.name, score_cache.get(ts.code, 0), 
                getattr(ts, 'signal_count', 0),
                ts.current_pct,
                ts.current_pct - ts.pct_diff,
                ts.pct_diff,
                reason
            ))

        total = len(data_list)
        up = sum(1 for x in data_list if x.current_pct > 0)
        down = sum(1 for x in data_list if x.current_pct < 0)
        avg_pct = sum(x.current_pct for x in data_list) / total if total > 0 else 0
        
        stats_text = (
            f"📊 共 {total} 只 | 涨跌: <span style='color:#FF4444;'>{up}</span>/<span style='color:#44CC44;'>{down}</span> | "
            f"🏁 均涨: <span style='color:{'#FF4444' if avg_pct >= 0 else '#44CC44'};'>{avg_pct:+.2f}%</span> | "
            f"📡 同步: {datetime.datetime.now().strftime('%H:%M:%S')}"
        )
        self.status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.status_lbl.setText(stats_text)

        self._render_table(flattened)

    def _render_table(self, data):
        if self.table.rowCount() != len(data):
            self.table.setRowCount(len(data))
        for i, row in enumerate(data):
            code, name, score, sig, pct, start_pct, dff, reason = row
            # code, name, score, sig, pct, start_pct, dff, reason = row
            
            # [⚡ 报警核验]
            is_alerted = get_alert_manager().is_alerted(code)
            bg_c = QColor("#4B0082") if is_alerted else None
            txt_c = QColor("#FFFFFF") if is_alerted else None
            d_name = f"🔔{name}" if is_alerted else name

            self._update_dialog_cell(i, 0, code, color=txt_c, bg_color=bg_c)
            self._update_dialog_cell(i, 1, d_name, color=txt_c, bg_color=bg_c)
            self._update_dialog_cell(i, 2, f"{score:.1f}", QColor("#FFD700") if not is_alerted else txt_c, bg_color=bg_c)
            sig_txt = str(sig) if sig > 0 else ""
            self._update_dialog_cell(i, 3, sig_txt, QColor("#00FFCC") if not is_alerted else txt_c, Qt.AlignmentFlag.AlignCenter, bg_color=bg_c)
            
            c_pct = QColor("#FF4444") if pct > 0 else (QColor("#44CC44") if pct < 0 else Qt.GlobalColor.white)
            if is_alerted: c_pct = txt_c
            self._update_dialog_cell(i, 4, f"{pct:+.2f}%", c_pct, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)
            
            c_start = QColor("#FF4444") if start_pct > 0 else (QColor("#44CC44") if start_pct < 0 else Qt.GlobalColor.white)
            if is_alerted: c_start = txt_c
            self._update_dialog_cell(i, 5, f"{start_pct:+.2f}%", c_start, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)
            
            c_dff = QColor("#FF4444") if dff > 0 else (QColor("#44CC44") if dff < 0 else Qt.GlobalColor.white)
            if is_alerted: c_dff = txt_c
            self._update_dialog_cell(i, 6, f"{dff:+.2f}%", c_dff, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)

            # [自适应渲染] 只有在列可见时才更新单元格内容
            if self._show_reason:
                c_reason = QColor("#00FFCC") if ("🚀" in reason or "🔥" in reason) else QColor("#AAAAAA")
                if is_alerted: c_reason = txt_c
                self._update_dialog_cell(i, 7, reason, c_reason, bg_color=bg_c)

    def _update_dialog_cell(self, row, col, text, color=None, align=None, bg_color=None):
        it = self.table.item(row, col)
        if not it:
            from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
            it = NumericTableWidgetItem(text)
            if color: it.setForeground(color)
            if bg_color: it.setBackground(bg_color)
            if align: it.setTextAlignment(align)
            self.table.setItem(row, col, it)
        else:
            if it.text() != text:
                it.setText(text)
            if color:
                it.setForeground(color)
            if bg_color:
                it.setBackground(bg_color)
            elif it.background().color().alpha() != 0:
                it.setBackground(QColor(0,0,0,0))

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
            
            # [🚀 增强] 将窗口位置也存入内存快照
            geom = self.saveGeometry().toHex().data().decode()
            _save_racing_config({
                "detail_column_widths": widths,
                "detail_geometry": geom
            })
            logger.debug(f"💾 [Detail] 已保存内存状态与列宽快照")
        except: pass

    def _restore_header_state(self):
        """恢复明细表各列宽度 (内存优先)"""
        try:
            conf = _get_racing_config()
            # 优先还原几何位置
            if "detail_geometry" in conf:
                self.restoreGeometry(QByteArray.fromHex(conf["detail_geometry"].encode()))
                
            widths = conf.get("detail_column_widths")
            if widths and len(widths) == self.table.columnCount():
                self.table.horizontalHeader().blockSignals(True)
                for i, w in enumerate(widths):
                    if w > 10: self.table.setColumnWidth(i, w)
                self.table.horizontalHeader().blockSignals(False)
                logger.debug(f"✅ [Detail] 成功还原 {self.sector_name} 内存状态")
        except: pass

    def _on_context_menu(self, pos):
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
        
        # [NEW] 形态详情开关
        act_toggle_reason = menu.addAction(f"{'👁️ 隐藏' if self._show_reason else '👁️ 显示'} 形态详情")
        act_toggle_reason.triggered.connect(self._toggle_reason_column)

        menu.addSeparator()
        
        # 穿透到主面板执行
        act_sector = menu.addAction(f"🚀 关联最强板块详情")
        if self.parent() and hasattr(self.parent(), '_show_strongest_sector'):
            act_sector.triggered.connect(lambda: self.parent()._show_strongest_sector(code))

        menu.addSeparator()
        
        selected_rows = set([it.row() for it in self.table.selectedItems()])
        title_dna = f"🚀 执行 DNA 审计 ({len(selected_rows)}只...)" if len(selected_rows) > 1 else f"🚀 执行 DNA 审计 ({name})"
        act_dna = menu.addAction(title_dna)
        act_dna.triggered.connect(self._run_dna_audit_top20)

        menu.addSeparator()
        
        # # [NEW] 重置活跃功能
        # selected_rows = sorted(list(set([it.row() for it in self.table.selectedItems()])))
        # if not selected_rows: selected_rows = [row]
        
        # title_reset = f"🔄 重置活跃 ({len(selected_rows)}只)" if len(selected_rows) > 1 else f"🔄 重置活跃 ({name})"
        # act_reset = menu.addAction(title_reset)
        # act_reset.triggered.connect(lambda: self._reset_stock_active(selected_rows))
        
        # [🚀 全局重置] 用户明确要求：重置活跃是全局重置，不是针对单个
        act_reset = menu.addAction("🔄 重置全局活跃")
        act_reset.triggered.connect(self._reset_stock_active)

        menu.addSeparator()
        act_copy = menu.addAction("📋 复制代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_reason_column(self):
        """切换理由列的可见性 - 实时同步至全局"""
        new_val = not self._show_reason
        if hasattr(self.parent(), '_set_global_show_reason'):
            self.parent()._set_global_show_reason(new_val)
        else:
            self.apply_show_reason_manual(new_val)

    def apply_show_reason_manual(self, val):
        """供主面板调用的手动状态同步"""
        self._show_reason = val
        self.table.setColumnHidden(7, not val)
        if val:
            self.table.setColumnWidth(7, 180)
            
        # 同步更新 UI 按钮状态
        if hasattr(self, 'btn_toggle_reason'):
            self.btn_toggle_reason.blockSignals(True)
            self.btn_toggle_reason.setChecked(val)
            self.btn_toggle_reason.setText("理由: 开" if val else "理由: 关")
            self.btn_toggle_reason.blockSignals(False)
            
        # 通知主面板保存状态
        if hasattr(self.parent(), '_save_ui_state'):
            self.parent()._save_ui_state()

        # 即时通知主面板保存状态
        if hasattr(self.parent(), '_save_ui_state'):
            self.parent()._save_ui_state()
        elif self.parent() and hasattr(self.parent().parent(), '_save_ui_state'):
            self.parent().parent()._save_ui_state()

    def _reset_stock_active(self, selected_rows=None):
        """手动全量重置活跃计数 - 修改为全局重置以响应用户需求"""
        if hasattr(self, 'detector') and self.detector:
            # [🚀 深度重置] 调用 Detector 的全局重置逻辑
            self.detector.reset_observation_anchors()
            
            # [🚀 深度重置] 同时也清空报警历史，防止列表无限堆积 (响应用户 "越来越多了" 的痛点)
            # get_alert_manager().clear_alert_history()
            
            self.detector.data_version += 1
            logger.info("🔄 [Detail] 用户通过详情窗触发了全局个股活跃计数与报警历史重置")
            
            self.refresh_data()
            # 尝试通过父对象触发主界面刷新
            if hasattr(self.parent(), 'update_visuals'):
                self.parent().update_visuals()
            elif self.parent() and hasattr(self.parent().parent(), 'update_visuals'):
                self.parent().parent().update_visuals()

    def _on_header_clicked(self, logical_index):
        if self._sort_col == logical_index:
            self._sort_order = Qt.SortOrder.AscendingOrder if self._sort_order == Qt.SortOrder.DescendingOrder else Qt.SortOrder.DescendingOrder
        else:
            self._sort_col = logical_index
            self._sort_order = Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(logical_index, self._sort_order)
        self.refresh_data()

    def closeEvent(self, event):
        # [统一管理] 不再独立存档，由主面板 closeEvent 统一调用状态导出
        self._save_header_state()
        # self.save_window_position_qt_visual(self, "SectorDetail_Unified")
        super().closeEvent(event)

    def _run_dna_audit_top20(self):
        """🚀 [DNA-BATCH] 极限审计：选取最高20只 (包含选定项)，或者按多选触发"""
        row_count = self.table.rowCount()
        if row_count == 0:
            return
            
        selected_items = self.table.selectedItems()
        selected_rows = sorted(list(set([item.row() for item in selected_items])))
        
        if len(selected_rows) > 1:
            target_rows = selected_rows[:50]
        elif len(selected_rows) == 1:
            start_idx = selected_rows[0]
            target_rows = range(start_idx, min(start_idx + 20, row_count))
        else:
            target_rows = range(min(20, row_count))
            
        code_to_name = {}
        for row in target_rows:
            if row >= row_count: break
            c_item = self.table.item(row, 0)
            n_item = self.table.item(row, 1)
            if c_item:
                c = str(c_item.text()).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                
                n = str(n_item.text()).strip() if n_item else ""
                if n.startswith("🔔"): n = n.replace("🔔", "")
                
                if c and c != "N/A" and len(c) == 6:
                    code_to_name[c] = n
                    
        if code_to_name:
            dispatch_dna_audit(code_to_name, parent_widget=self)

class CategoryDetailDialog(QDialog, WindowMixin):
    """饼图分类成分股详情弹窗 - 结构与板块详情一致"""
    def __init__(self, category_name, detector, linkage_cb, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.linkage_cb = linkage_cb
        self.category_name = category_name
        
        self.setWindowTitle(f"🔭 赛马详情: {category_name}")
        # [✨ 面板高度调整] 默认显示前30左右的高度
        self.resize(800, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setStyleSheet("background-color: #000; color: #EEE;")

        # 记忆位置
        self.load_window_position_qt(self, f"CategoryDetail_{category_name}")
        
        self.setUpdatesEnabled(False)
        self._sort_col = 2 # 默认排序: 结构分
        self._sort_order = Qt.SortOrder.DescendingOrder
        
        self._boot_lock = True
        self._is_height_doubled = False
        self._show_reason = False
        
        self._init_ui()
        QTimer.singleShot(150, self._restore_header_state)
        QTimer.singleShot(1000, self._release_boot_lock)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(500) 
        self.refresh_data()
        self.setUpdatesEnabled(True)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # [🚀 标题栏交互增强] 创建可交互标题区域
        self.header_frame = QFrame()
        self.header_frame.setObjectName("header_frame")
        self.header_frame.mouseDoubleClickEvent = lambda e: self._on_header_double_click(e)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 5)
        header_layout.setSpacing(10)
        
        title_lbl = QLabel(f"🔥 {self.category_name} - 个股明细")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #00FFCC;")
        header_layout.addWidget(title_lbl)
        
        self.btn_toggle_reason = QPushButton("理由: 关")
        self.btn_toggle_reason.setCheckable(True)
        self.btn_toggle_reason.setChecked(self._show_reason)
        self.btn_toggle_reason.setText("理由: 开" if self._show_reason else "理由: 关")
        self.btn_toggle_reason.setStyleSheet("""
            QPushButton { background-color: #222; color: #AAA; border: 1px solid #444; padding: 4px 10px; border-radius: 4px; font-size: 11px; }
            QPushButton:checked { background-color: #005BB7; color: white; border: 1px solid #00FFCC; }
            QPushButton:hover { border: 1px solid white; }
        """)
        self.btn_toggle_reason.clicked.connect(self._toggle_reason_column)
        header_layout.addWidget(self.btn_toggle_reason)

        self.btn_dna = QPushButton("🚀 DNA审计")
        self.btn_dna.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; padding: 4px 8px; border-radius: 4px;")
        self.btn_dna.clicked.connect(self._run_dna_audit_top20)
        header_layout.addWidget(self.btn_dna)
        
        layout.addWidget(self.header_frame)
        
        self.table = EnhancedTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF", "形态详情"])
        if self.table.horizontalHeaderItem(6):
            self.table.horizontalHeaderItem(6).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # [NEW] 形态详情列默认隐藏
        self.table.setColumnHidden(7, not self._show_reason)
        if self._show_reason:
            self.table.setColumnWidth(7, 180)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget { background-color: #000; alternate-background-color: #111; color: #FFF; gridline-color: #222; outline: none; }
            QHeaderView::section { background-color: #222; color: #BBB; padding: 4px; border: 1px solid #333; }
        """ + GLOBAL_SCROLLBAR_STYLE)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(90)
        
        self.table.code_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="category_dialog_link"))
        self.table.code_double_clicked.connect(lambda c, n: self.linkage_cb(c, n, source="category_dialog_double"))
        
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        # [统一管理] 停用实时列宽保存
        # self.table.horizontalHeader().sectionResized.connect(self._save_header_state)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # [🚀 直出一层] 禁用基类默认菜单干扰
        self.table._enable_default_menu = False
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        layout.addWidget(self.table)
        

        
        # [🚀 新增] 底部统计信息栏
        self.status_lbl = QLabel("统计: --")
        self.status_lbl.setStyleSheet("color: #AAA; font-size: 11px; padding: 2px; background-color: #111; border-top: 1px solid #333;")
        layout.addWidget(self.status_lbl)

    def _on_header_double_click(self, event):
        """[🚀 交互增强] 双击标题栏高度翻倍/恢复"""
        if not self._is_height_doubled:
            self._original_height_snap = self.height()
            screen_h = QApplication.primaryScreen().availableGeometry().height()
            target_h = min(self._original_height_snap * 2, screen_h - 100)
            self.resize(self.width(), target_h)
            self._is_height_doubled = True
            logger.debug(f"📐 [Detail] {self.category_name} 高度已翻倍至 {target_h}")
        else:
            h = getattr(self, '_original_height_snap', 800)
            self.resize(self.width(), h)
            self._is_height_doubled = False
            logger.debug(f"📐 [Detail] {self.category_name} 高度已恢复至 {h}")

    def _get_synthetic_score(self, ts):
        try:
            main_score = ts.score
            if main_score < 0.01:
                activity_score = (getattr(ts, 'signal_count', 0) * 1.5) + (abs(ts.current_pct) * 0.2)
                return max(activity_score, getattr(ts, 'momentum_score', 0) * 0.05)
            return main_score
        except AttributeError:
            return 0.0

    def refresh_data(self):
        # [🚀 极速视口过滤] 只有在可见状态下才参与绘制，防止多窗口堆叠导致的 CPU 溢出
        if not self.isVisible(): 
            return

        if not hasattr(self, 'detector') or not self.detector: return
        
        if not self.detector._lock.acquire(blocking=False): return
        try:
            data_list = []
            for ts in self.detector._tick_series.values():
                # [FIX] 虚拟板块逻辑适配：分析报警状态
                is_alerted = get_alert_manager().is_alerted(ts.code)
                # [NEW] 补全回测模式下的信号感知：检查 SBC 注册表
                if not is_alerted and self.detector.realtime_service and self.detector.realtime_service.emotion_tracker:
                    reg = getattr(self.detector.realtime_service.emotion_tracker, '_sbc_signals_registry', {})
                    if ts.code in reg: is_alerted = True

                role = get_racing_role(ts)
                if role == self.category_name or (self.category_name == "🔔 实时报警" and is_alerted):
                    data_list.append(ts)
            
            if not data_list:
                if self.table.rowCount() > 0: self.table.setRowCount(0)
                return
        finally:
            self.detector._lock.release()

        # [🔒 锁外计算]
        col_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'start_pct', 6:'pct_diff'}
        attr = col_attr_map.get(self._sort_col, 'score')
        is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
        
        score_cache = {ts.code: self._get_synthetic_score(ts) for ts in data_list}
        
        def get_sort_key(ts):
            # [🚀 优先级排序增强] ⚡(2) > 🔔(1) > 无(0)
            # 获取 SBC 注册表
            reg = {}
            if self.detector and self.detector.realtime_service and self.detector.realtime_service.emotion_tracker:
                 reg = getattr(self.detector.realtime_service.emotion_tracker, '_sbc_signals_registry', {})
            
            has_alert = get_alert_manager().is_alerted(ts.code)
            has_sbc = ts.code in reg
            prio = 2 if has_sbc else (1 if has_alert else 0)
            
            if attr == 'start_pct': val = ts.current_pct - ts.pct_diff
            elif attr == 'pct_diff': val = ts.pct_diff
            elif attr == 'score': val = score_cache.get(ts.code, 0)
            else: val = getattr(ts, attr, 0)
            
            if attr == 'name':
                return (prio, val, ts.code)
            return (val, ts.code)

        data_list.sort(key=get_sort_key, reverse=is_rev)
        
        flattened = []
        for ts in data_list[:300]:
            # [自适应节流] 只有在打开显示开关时才进行昂贵的理由提取
            reason = ""
            if self._show_reason:
                if self.detector and self.detector.realtime_service and self.detector.realtime_service.emotion_tracker:
                    reg = getattr(self.detector.realtime_service.emotion_tracker, '_sbc_signals_registry', {})
                    if ts.code in reg: 
                        reason = reg[ts.code].get('desc', '')
                if not reason: 
                    reason = getattr(ts, 'pattern_hint', "")

            flattened.append((ts.code, ts.name, score_cache.get(ts.code, 0), 
                             getattr(ts, 'signal_count', 0),
                             ts.current_pct,
                             ts.current_pct - ts.pct_diff,
                             ts.pct_diff,
                             reason))
        avg_pct = sum(x.current_pct for x in data_list) / len(data_list)
        stats_text = (f"📊 统计: 共 {len(data_list)} 只 | "
                      f"🏁 均幅: <span style='color:{'#FF4444' if avg_pct >= 0 else '#44CC44'};'>{avg_pct:+.2f}%</span>")
        self.status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.status_lbl.setText(stats_text)

        self._render_table(flattened)

    def _render_table(self, data):
        if self.table.rowCount() != len(data):
            self.table.setRowCount(len(data))
        for i, row in enumerate(data):
            code, name, score, sig, pct, start_pct, dff, reason = row
            # code, name, score, sig, pct, start_pct, dff, reason = row
            
            # [⚡ 报警核验]
            is_alerted = get_alert_manager().is_alerted(code)
            bg_c = QColor("#4B0082") if is_alerted else None
            txt_c = QColor("#FFFFFF") if is_alerted else None
            d_name = f"🔔{name}" if is_alerted else name

            self._update_dialog_cell(i, 0, code, color=txt_c, bg_color=bg_c)
            self._update_dialog_cell(i, 1, d_name, color=txt_c, bg_color=bg_c)
            self._update_dialog_cell(i, 2, f"{score:.1f}", QColor("#FFD700") if not is_alerted else txt_c, bg_color=bg_c)
            sig_txt = str(sig) if sig > 0 else ""
            self._update_dialog_cell(i, 3, sig_txt, QColor("#00FFCC") if not is_alerted else txt_c, Qt.AlignmentFlag.AlignCenter, bg_color=bg_c)
            
            c_pct = QColor("#FF4444") if pct > 0 else (QColor("#44CC44") if pct < 0 else Qt.GlobalColor.white)
            if is_alerted: c_pct = txt_c
            self._update_dialog_cell(i, 4, f"{pct:+.2f}%", c_pct, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)
            
            c_start = QColor("#FF4444") if start_pct > 0 else (QColor("#44CC44") if start_pct < 0 else Qt.GlobalColor.white)
            if is_alerted: c_start = txt_c
            self._update_dialog_cell(i, 5, f"{start_pct:+.2f}%", c_start, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)
            
            c_dff = QColor("#FF4444") if dff > 0 else (QColor("#44CC44") if dff < 0 else Qt.GlobalColor.white)
            if is_alerted: c_dff = txt_c
            self._update_dialog_cell(i, 6, f"{dff:+.2f}%", c_dff, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_c)

            # [自适应渲染] 只有在列可见时才更新单元格内容
            if self._show_reason:
                c_reason = QColor("#00FFCC") if ("🚀" in reason or "🔥" in reason) else QColor("#AAAAAA")
                if is_alerted: c_reason = txt_c
                self._update_dialog_cell(i, 7, reason, c_reason, bg_color=bg_c)

    def _update_dialog_cell(self, row, col, text, color=None, align=None, bg_color=None):
        it = self.table.item(row, col)
        if not it:
            from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
            it = NumericTableWidgetItem(text)
            if color: it.setForeground(color)
            if bg_color: it.setBackground(bg_color)
            if align: it.setTextAlignment(align)
            self.table.setItem(row, col, it)
        else:
            if it.text() != text:
                it.setText(text)
            if color:
                it.setForeground(color)
            if bg_color:
                it.setBackground(bg_color)
            elif it.background().color().alpha() != 0:
                it.setBackground(QColor(0,0,0,0))

    def _release_boot_lock(self):
        self._boot_lock = False

    def get_ui_state(self):
        return {
            "show_reason": self._show_reason
        }

    def apply_ui_state(self, state):
        if not state: return
        self._show_reason = state.get("show_reason", False)
        if hasattr(self, 'table'):
            self.table.setColumnHidden(7, not self._show_reason)

    def _save_header_state(self):
        if hasattr(self, '_boot_lock') and self._boot_lock:
            return 
        try:
            widths = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
            if sum(widths) < 100: return
            geom = self.saveGeometry().toHex().data().decode()
            _save_racing_config({
                f"cat_detail_widths_{self.category_name}": widths,
                f"cat_detail_geometry_{self.category_name}": geom
            })
        except: pass

    def _restore_header_state(self):
        try:
            conf = _get_racing_config()
            geom_key = f"cat_detail_geometry_{self.category_name}"
            if geom_key in conf:
                self.restoreGeometry(QByteArray.fromHex(conf[geom_key].encode()))
                
            widths = conf.get(f"cat_detail_widths_{self.category_name}")
            if widths and len(widths) == self.table.columnCount():
                self.table.horizontalHeader().blockSignals(True)
                for i, w in enumerate(widths):
                    if w > 10: self.table.setColumnWidth(i, w)
                self.table.horizontalHeader().blockSignals(False)
        except: pass

    def _on_context_menu(self, pos):
        """分类/明细表右键菜单 - 扁平化直出"""
        item = self.table.itemAt(pos)
        if not item: return
        row = item.row()
        code = self.table.item(row, 0).text()
        name = self.table.item(row, 1).text()
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #005BB7; }")
        
        act_viz = menu.addAction(f"📊 联动可视化 ({name})")
        act_viz.triggered.connect(lambda: self.linkage_cb(code, name, source="category_dialog_context"))
        
        menu.addSeparator()
        
        # [NEW] 形态详情开关
        act_toggle_reason = menu.addAction(f"{'👁️ 隐藏' if self._show_reason else '👁️ 显示'} 形态详情")
        act_toggle_reason.triggered.connect(self._toggle_reason_column)

        menu.addSeparator()
        
        menu.addSeparator()
        
        # [NEW] 形态详情开关
        act_toggle_reason = menu.addAction(f"{'👁️ 隐藏' if self._show_reason else '👁️ 显示'} 形态详情")
        act_toggle_reason.triggered.connect(self._toggle_reason_column)

        menu.addSeparator()
        
        # 穿透到主面板执行
        act_sector = menu.addAction(f"🚀 关联最强板块详情")
        if self.parent() and hasattr(self.parent(), '_show_strongest_sector'):
            act_sector.triggered.connect(lambda: self.parent()._show_strongest_sector(code))

        menu.addSeparator()
        
        selected_rows = set([it.row() for it in self.table.selectedItems()])
        title_dna = f"🚀 执行 DNA 审计 ({len(selected_rows)}只...)" if len(selected_rows) > 1 else f"🚀 执行 DNA 审计 ({name})"
        act_dna = menu.addAction(title_dna)
        act_dna.triggered.connect(self._run_dna_audit_top20)

        menu.addSeparator()

        # [NEW] 重置活跃功能
        selected_rows = sorted(list(set([it.row() for it in self.table.selectedItems()])))
        if not selected_rows: selected_rows = [row]
        
        title_reset = f"🔄 重置活跃 ({len(selected_rows)}只)" if len(selected_rows) > 1 else f"🔄 重置活跃 ({name})"
        act_reset = menu.addAction(title_reset)
        act_reset.triggered.connect(lambda: self._reset_stock_active(selected_rows))

        menu.addSeparator()
        act_copy = menu.addAction("📋 复制代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _toggle_reason_column(self):
        """切换理由列的可见性 - 实时同步至全局"""
        new_val = not self._show_reason
        # 委托给主面板进行全局管理
        if hasattr(self.parent(), '_set_global_show_reason'):
            self.parent()._set_global_show_reason(new_val)
        else:
            self.apply_show_reason_manual(new_val)

    def apply_show_reason_manual(self, val):
        """供主面板调用的手动状态同步"""
        self._show_reason = val
        self.table.setColumnHidden(7, not val)
        if val:
            self.table.setColumnWidth(7, 180)

        # 同步更新 UI 按钮状态
        if hasattr(self, 'btn_toggle_reason'):
            self.btn_toggle_reason.blockSignals(True)
            self.btn_toggle_reason.setChecked(val)
            self.btn_toggle_reason.setText("理由: 开" if val else "理由: 关")
            self.btn_toggle_reason.blockSignals(False)

        # 通知主面板保存状态
        if hasattr(self.parent(), '_save_ui_state'):
            self.parent()._save_ui_state()

    def _reset_stock_active(self, selected_rows: list):
        """手动重置选中个股的活跃计数"""
        if not self.detector: return
        codes = []
        for r in selected_rows:
            c_item = self.table.item(r, 0)
            if c_item:
                c = str(c_item.text()).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                if c and len(c) == 6:
                    codes.append(c)
        if codes:
            self.detector.reset_stock_active(codes)
            logger.info(f"🔄 [Detail] 用户重置了 {len(codes)} 只个股的活跃计数")
            self.refresh_data()

    def _on_header_clicked(self, logical_index):
        if self._sort_col == logical_index:
            self._sort_order = Qt.SortOrder.AscendingOrder if self._sort_order == Qt.SortOrder.DescendingOrder else Qt.SortOrder.DescendingOrder
        else:
            self._sort_col = logical_index
            self._sort_order = Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(logical_index, self._sort_order)
        self.refresh_data()

    def closeEvent(self, event):
        # [统一管理] 不再独立存档
        self._save_header_state()
        super().closeEvent(event)

    def _run_dna_audit_top20(self):
        """🚀 [DNA-BATCH] 极限审计：选取最高20只 (包含选定项)，或者按多选触发"""
        row_count = self.table.rowCount()
        if row_count == 0:
            return
            
        selected_items = self.table.selectedItems()
        selected_rows = sorted(list(set([item.row() for item in selected_items])))
        
        if len(selected_rows) > 1:
            target_rows = selected_rows[:50]
        elif len(selected_rows) == 1:
            start_idx = selected_rows[0]
            target_rows = range(start_idx, min(start_idx + 20, row_count))
        else:
            target_rows = range(min(20, row_count))
            
        code_to_name = {}
        for row in target_rows:
            if row >= row_count: break
            c_item = self.table.item(row, 0)
            n_item = self.table.item(row, 1)
            if c_item:
                c = str(c_item.text()).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                
                n = str(n_item.text()).strip() if n_item else ""
                if n.startswith("🔔"): n = n.replace("🔔", "")

                if c and c != "N/A" and len(c) == 6:
                    code_to_name[c] = n
                    
        if code_to_name:
            dispatch_dna_audit(code_to_name, parent_widget=self)


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
        
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel("🚩 竞技进度: 09:25:00")
        self.label.setStyleSheet("color: #00FFCC; font-weight: bold;")
        top_layout.addWidget(self.label)
        
        top_layout.addStretch()
        
        self.stats_label = QLabel('🌡 温度: <span style="color:#FFF;">--℃</span> &nbsp;&nbsp;|&nbsp;&nbsp; 📈 涨: <span style="color:#FF4444;">--</span> 跌: <span style="color:#44CC44;">--</span> &nbsp;&nbsp;|&nbsp;&nbsp; 上证: <span style="color:#FFF;">--</span>')
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)
        self.stats_label.setStyleSheet("color: #AAA; font-size: 11px;")
        top_layout.addWidget(self.stats_label)
        
        layout.addLayout(top_layout)
        
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
        """[🚀 安全加固] 更新进度时间，增加对被销毁对象的保护"""
        try:
            # 捕获 C++ 对象已删除的情况 (在回放模式下关闭窗口时常见)
            self.label.setText(f"🚩 竞技进度: {time_str}")
            
            parts = time_str.split(':')
            h, m = int(parts[0]), int(parts[1])
            total_m = (h - 9) * 60 + (m - 25)
            self.slider.blockSignals(True)
            self.slider.setValue(max(0, total_m))
            self.slider.blockSignals(False)
        except (RuntimeError, AttributeError):
            # 忽略 "wrapped C/C++ object of type QLabel has been deleted"
            pass
        except Exception:
            pass

    def update_market_stats(self, stats: dict):
        try:
            temp = stats.get("temperature", 0.0)
            up = stats.get("up", 0)
            down = stats.get("down", 0)
            
            if temp >= 60: t_c = "#FF4444"
            elif temp <= 30: t_c = "#44CC44"
            else: t_c = "#FFD700"
                
            sh_pct = "--"
            sh_c = "#FFF"
            for idx in stats.get("indices", []):
                if idx.get("name") in ["上证", "000001", "999999"]:
                    p = idx.get("percent", 0.0)
                    sh_pct = f"{p:+.2f}%"
                    sh_c = "#FF4444" if p > 0 else ("#44CC44" if p < 0 else "#FFF")
                    break
            
            self.stats_label.setText(
                f'🌡 温度: <span style="color:{t_c}; font-weight:bold;">{temp:.1f}℃</span> &nbsp;&nbsp;|&nbsp;&nbsp; '
                f'📈 涨: <span style="color:#FF4444; font-weight:bold;">{up}</span> '
                f'跌: <span style="color:#44CC44; font-weight:bold;">{down}</span> &nbsp;&nbsp;|&nbsp;&nbsp; '
                f'上证: <span style="color:{sh_c}; font-weight:bold;">{sh_pct}</span>'
            )
        except Exception: pass


class BiddingRacingRhythmPanel(QWidget, WindowMixin):
    """
    竞价赛马节奏主面板
    """
    closed = pyqtSignal()
    data_updated = pyqtSignal() # [NEW] 数据刷新信号，驱动详情窗同步更新

    def __init__(self, detector=None, parent=None, main_app=None, on_code_callback=None, sender=None):
        super().__init__(parent)
        self.detector = detector
        self.main_app = main_app
        self.on_code_callback = on_code_callback
        self._anchor_history = [] 
        self._last_anchor_reset_data_ts = 0
        self._last_data_version = -1
        self._is_rendering = False
        self._is_loading = False 
        self._table_highlights = {} 
        self._pending_auto_restore_idx = -1
        self._auto_restore_pending = False
        self._auto_capture_today_first = False
        self._first_boot_render = True # [NEW] 启动强制首次渲染标记
        self._startup_time = time.time()
        self._detail_dialogs = {} # [NEW] 追踪活跃的明细窗体实例
        self._current_anchor_ts = 0 # [NEW] 追踪当前正在使用的锚点时间戳
        self._ui_ready = False
        self._sector_history = []  # [🚀 板块回溯]
        self._is_updating_history = False
        self._sector_score_anchors = {} # [🚀 新增] 面板级板块评分锚点，防止被 Detector 重刷丢失
        self._global_show_reason = False # [NEW] 全局形态详情控制位


        if sender:
            self.stock_sender = sender
        elif not main_app:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.stock_sender = StockSender(tdx_var=True, ths_var=False, dfcf_var=False)
            except Exception as e:
                self.stock_sender = None
        else:
            self.stock_sender = None
            
        self._select_code = "" 
        
        self.setWindowTitle("🏁 竞价赛马与节奏监控")
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #000000; color: white;")
        
        self._last_rendered_time = 0
        self._last_ui_update_ts = 0 
        self._table_highlights = {}
        
        self._sort_col = 2 
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._sort_col_sector = 1 
        self._sort_order_sector = Qt.SortOrder.DescendingOrder
        self._reset_cycle_mins = 60 
        
        self._UI_CACHE = {
            "COLOR_GOLD": QColor("#FFD700"),
            "COLOR_RED": QColor("#FF4444"),
            "COLOR_GREEN": QColor("#44CC44"),
            "COLOR_CYAN": QColor("#00FFCC"),
            "COLOR_BLUE": QColor("#00CCFF"),
            "COLOR_CORAL": QColor("#FF2D55"),
            "COLOR_TRANSPARENT": QColor(0, 0, 0, 0),
            "COLOR_FLASH_BASE": QColor(255, 215, 0),
            "FONT_FOLLOWERS": QFont("Segoe UI", 9),
            "COLOR_ALERT_BG": QColor("#4B0082"), # Indigo/Deep Purple
            "COLOR_ALERT_TEXT": QColor("#FFFFFF")
        }
        
        self._init_ui()
        QTimer.singleShot(500,self._restore_ui_state)
        
        self.stock_table.setSortingEnabled(False)
        self.sector_table.setSortingEnabled(False)
        
        self.load_window_position_qt(self, "BiddingRacingRhythmPanel", default_width=1000, default_height=700)
        
        # ✅ [生命周期管理] 显式设置关闭即销毁，确保 TK 同步引用为空
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_visuals)
        self.refresh_timer.start(200) # [⚡ 性能均衡] 5FPS 既能满足实时感，又能大幅降低 CPU 负载
        
        QTimer.singleShot(5000, self._check_auto_anchor)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        top_bar = QFrame()
        top_bar.setFixedHeight(90)
        top_bar.setStyleSheet("background-color: #1C1C1E; border-radius: 12px; border: 1px solid #2C2C2E;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 5, 15, 5)
        top_bar_layout.setSpacing(20)
        
        self.timeline = RacingTimeline()
        self.timeline.setStyleSheet("background: transparent; border: none;")
        top_bar_layout.addWidget(self.timeline, stretch=7)
        
        cycle_group = QFrame()
        cycle_group.setFixedWidth(240)
        cycle_group.setStyleSheet("background-color: #262629; border-radius: 8px; border: 1px solid #3A3A3C;")
        cycle_layout = QVBoxLayout(cycle_group)
        cycle_layout.setContentsMargins(8, 8, 8, 8)
        cycle_layout.setSpacing(6)
        
        # [🚀 布局优化] 第一行：减号 + 周期标签 + 加号
        header_row = QHBoxLayout()
        header_row.setSpacing(2)
        
        self.btn_minus = QPushButton("-10m")
        self.btn_minus.setFixedSize(45, 26)
        self.btn_minus.setStyleSheet("""
            QPushButton { background: #3A3A3C; color: #BBB; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #48484A; color: white; }
        """)
        self.btn_minus.clicked.connect(lambda: self._adjust_cycle(-10))
        header_row.addWidget(self.btn_minus)
        
        self.cycle_label = QLabel(f"📊 起点参考周期: {self._reset_cycle_mins}m")
        self.cycle_label.setStyleSheet("color: #FFD700; font-weight: bold; font-family: 'Segoe UI'; font-size: 11px;")
        self.cycle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.cycle_label, stretch=1)
        
        self.btn_plus = QPushButton("+10m")
        self.btn_plus.setFixedSize(45, 26)
        self.btn_plus.setStyleSheet("""
            QPushButton { background: #3A3A3C; color: #BBB; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #48484A; color: white; }
        """)
        self.btn_plus.clicked.connect(lambda: self._adjust_cycle(10))
        header_row.addWidget(self.btn_plus)
        
        cycle_layout.addLayout(header_row)
        
        # [🚀 布局优化] 第二行：功能按键大集合
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.reset_btn = QPushButton("🔄 即时重置")
        self.reset_btn.setFixedSize(75, 26)
        self.reset_btn.setStyleSheet("""
            QPushButton { background: #FF2D55; color: white; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #FF375F; border: 1px solid white; }
        """)
        self.reset_btn.clicked.connect(self._manual_reset_anchors)
        btn_layout.addWidget(self.reset_btn)

        self.btn_show_alerts = QPushButton("🔔 报警关注")
        self.btn_show_alerts.setFixedSize(85, 26)
        self.btn_show_alerts.setStyleSheet("""
            QPushButton { 
                background: #4B0082; color: #FFD700; border: 1px solid #FFD700; 
                border-radius: 4px; font-weight: bold; font-size: 11px; 
            }
            QPushButton:hover { background: #8B0000; color: white; border: 1px solid white; }
        """)
        self.btn_show_alerts.clicked.connect(self._on_show_alerts_clicked)
        btn_layout.addWidget(self.btn_show_alerts)

        btn_layout.addStretch()

        self.btn_arrange = QPushButton("📏 整理")
        self.btn_arrange.setFixedSize(65, 26)
        self.btn_arrange.setStyleSheet("""
            QPushButton { background: #3A3A3C; color: #00FFCC; border: 1px solid #00FFCC; border-radius: 4px; font-weight: bold; font-size: 10px; }
            QPushButton:hover { background: #00FFCC; color: black; }
        """)
        self.btn_arrange.clicked.connect(self._arrange_detail_windows)
        btn_layout.addWidget(self.btn_arrange)
        
        cycle_layout.addLayout(btn_layout)
        top_bar_layout.addWidget(cycle_group)
        
        main_layout.addWidget(top_bar)
        
        center_layout = QHBoxLayout()
        center_layout.setSpacing(20)
        
        # [🚀 板块回溯] 饼图区域增加历史下拉菜单
        pie_container = QWidget()
        pie_vbox = QVBoxLayout(pie_container)
        pie_vbox.setContentsMargins(0, 0, 0, 0)
        pie_vbox.setSpacing(6)
        
        history_lay = QHBoxLayout()
        history_title = QLabel("🚀 板块回溯")
        history_title.setStyleSheet("color: #00FFCC; font-size: 11px; font-weight: bold;")
        history_lay.addWidget(history_title)
        
        self.combo_sector_history = QComboBox()
        self.combo_sector_history.setStyleSheet("""
            QComboBox { background-color: #2C2C2E; color: #FFF; border: 1px solid #444; border-radius: 4px; padding: 2px 8px; font-size: 11px; min-height: 24px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2C2C2E; color: #FFF; selection-background-color: #005BB7; outline: none; }
        """)
        self.combo_sector_history.currentIndexChanged.connect(self._on_history_combo_changed)
        history_lay.addWidget(self.combo_sector_history, stretch=1)
        
        self.btn_del_history = QPushButton("❌")
        self.btn_del_history.setFixedSize(24, 24)
        self.btn_del_history.setToolTip("删除选中回溯条目 (Delete History Item)")
        self.btn_del_history.setStyleSheet("background-color: #2C2C2E; color: #FF4444; border: 1px solid #444; border-radius: 4px; font-weight: bold;")
        self.btn_del_history.clicked.connect(self._on_delete_history_clicked)
        history_lay.addWidget(self.btn_del_history)

        pie_vbox.addLayout(history_lay)
        
        # [NEW] 🧬 SBC 基因报警实时统计卡片 (放在饼图上方，极其醒目)
        self.card_sbc_stats = QPushButton("🧬 实时基因报警: 0")
        self.card_sbc_stats.setFixedSize(160, 32)
        self.card_sbc_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.card_sbc_stats.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card_sbc_stats.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4B0082, stop:1 #800080); 
                color: #00FFCC; border: 1px solid #FFD700; border-radius: 6px; 
                font-weight: bold; font-size: 11px; text-align: center;
            }
            QPushButton:hover { background: #9400D3; border: 1px solid white; color: white; }
        """)
        # 点击直接打开虚拟板块详情窗
        self.card_sbc_stats.clicked.connect(lambda: self._on_category_double_clicked("🔔 实时报警"))
        # 右键重置功能
        self.card_sbc_stats.customContextMenuRequested.connect(self._on_sbc_stats_context_menu)
        pie_vbox.addWidget(self.card_sbc_stats, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.pie_widget = RacingPieWidget()
        self.pie_widget.category_selected.connect(self._on_pie_filter)
        self.pie_widget.category_double_clicked.connect(self._on_category_double_clicked)
        pie_vbox.addWidget(self.pie_widget, stretch=1)
        
        center_layout.addWidget(pie_container, stretch=4)
        
        rank_frame = QFrame()
        rank_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        rank_layout = QVBoxLayout(rank_frame)
        
        title_lbl = QLabel("🏆 当下领军个股 (Top 20)")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFD700; padding: 10px;")
        rank_layout.addWidget(title_lbl)
        
        self.stock_table = EnhancedTableWidget(0, 8)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "活跃", "涨幅", "起点", "DFF", "形态"])
        self.stock_table.setColumnHidden(7, True) # 默认隐藏
        if self.stock_table.horizontalHeaderItem(6):
            self.stock_table.horizontalHeaderItem(6).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(80) 
        header.setMinimumSectionSize(30)
        self.stock_table.setColumnWidth(0, 65)
        self.stock_table.setColumnWidth(1, 75)
        # self.stock_table.horizontalHeader().sectionResized.connect(self._save_ui_state) # 移动到 _init_ui 末尾，防止初始化时 AttributeError
        
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
        """ + GLOBAL_SCROLLBAR_STYLE)
        
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stock_table.setSortingEnabled(False)
        header.sectionClicked.connect(lambda idx: self._on_header_clicked("stock", idx))
        rank_layout.addWidget(self.stock_table)
        center_layout.addWidget(rank_frame, stretch=6)
        
        # [🚀 可调整高度] 引入垂直分栏器，让用户可以上下拖动调整板块视图高度
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setStyleSheet("QSplitter::handle { background: #333; }")
        
        center_container = QWidget()
        center_container.setLayout(center_layout)
        self.main_splitter.addWidget(center_container)
        
        bottom_frame = QFrame()
        # bottom_frame.setFixedHeight(220) # 取消定死高度
        bottom_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        bottom_lay = QVBoxLayout(bottom_frame)
        
        sec_title_lay = QHBoxLayout()
        sec_title_lay.setContentsMargins(10, 5, 10, 5)
        
        sec_title = QLabel("🔥 最强板块赛道")
        sec_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00FFCC;")
        sec_title_lay.addWidget(sec_title)
        
        self.history_layout = QHBoxLayout()
        self.history_layout.setSpacing(10)
        sec_title_lay.addLayout(self.history_layout)
        sec_title_lay.addStretch(1)
        
        bottom_lay.addLayout(sec_title_lay)
        
        self.sector_table = EnhancedTableWidget(0, 8)
        self.sector_table.setHorizontalHeaderLabels(["板块名称", "强度得分", "涨跌", "领涨龙头", "龙头涨幅", "起点涨幅", "龙头DFF", "联动详情"])
        s_header = self.sector_table.horizontalHeader()
        s_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # [🚀 实时持久化] 当列宽变动时，即时记录
        # self.sector_table.horizontalHeader().sectionResized.connect(self._save_ui_state) # 移动到 _init_ui 末尾
        
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
        """ + GLOBAL_SCROLLBAR_STYLE)
        
        self.sector_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sector_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sector_table.setSortingEnabled(False)
        s_header.sectionClicked.connect(lambda idx: self._on_header_clicked("sector", idx))
        bottom_lay.addWidget(self.sector_table)
        self.main_splitter.addWidget(bottom_frame)
        
        # 设置默认比例 (7:3)
        self.main_splitter.setStretchFactor(0, 7)
        self.main_splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(self.main_splitter)

        self.stock_table.code_clicked.connect(self._on_stock_clicked)
        self.stock_table.code_double_clicked.connect(self._on_stock_double_clicked)
        
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # [🚀 直出一层] 禁用基类默认菜单干扰
        self.stock_table._enable_default_menu = False
        self.stock_table.customContextMenuRequested.connect(self._on_stock_context_menu)
        
        self.stock_table.currentCellChanged.connect(self._on_stock_key_nav)

        self.sector_table.cellDoubleClicked.connect(self._on_sector_double_clicked)
        self.sector_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # [🚀 直出一层] 禁用基类默认菜单干扰
        self.sector_table._enable_default_menu = False
        self.sector_table.customContextMenuRequested.connect(self._on_sector_context_menu)

        self.sector_table.currentCellChanged.connect(
            lambda r, c, pr, pc: self._on_sector_clicked(r, c)
        )
        
        # [🚀 最终关联] 确保所有组件初始化完成后才开启持久化监听
        # self.stock_table.horizontalHeader().sectionResized.connect(self._save_ui_state)
        # self.sector_table.horizontalHeader().sectionResized.connect(self._save_ui_state)


    def _on_pie_filter(self, category):
        if category == "ALL":
            self.pie_widget.selected_category = None
        else:
            self.pie_widget.selected_category = category
        self.update_visuals()

    def _on_category_double_clicked(self, category):
        # [🚀 置顶去重] 如果已打开，则置顶
        dlg_key = f"category:{category}"
        if dlg_key in self._detail_dialogs:
            dlg = self._detail_dialogs[dlg_key]
            try:
                dlg.show(); dlg.raise_(); dlg.activateWindow()
                return
            except: pass
            
        # [🚀 深度优化] parent 设为 None 避免样式干扰
        dialog = CategoryDetailDialog(category, self.detector, self._execute_linkage, parent=self)
        # [NEW] 实时同步全局形态详情开关
        if hasattr(self, '_global_show_reason') and hasattr(dialog, 'apply_show_reason_manual'):
            dialog._show_reason = self._global_show_reason # 先设置，防止 _init_ui 之后状态不统一
            dialog.apply_show_reason_manual(self._global_show_reason)

        dialog.finished.connect(lambda: self._detail_dialogs.pop(dlg_key, None))
        # [🚀 极速联动] 挂载主面板刷新信号
        self.data_updated.connect(dialog.refresh_data)
        self._detail_dialogs[dlg_key] = dialog
        dialog.show()

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

        act_sector = menu.addAction(f"🚀 关联最强板块详情")
        act_sector.triggered.connect(lambda: self._show_strongest_sector(code))

        menu.addSeparator()
        
        # DNA 审计支持
        selected_rows = sorted(list(set([it.row() for it in self.stock_table.selectedItems()])))
        title_dna = f"🚀 执行 DNA 审计 ({len(selected_rows)}只...)" if len(selected_rows) > 1 else f"🚀 执行 DNA 审计 ({name})"
        act_dna = menu.addAction(title_dna)
        act_dna.triggered.connect(self._run_dna_audit_batch)

        menu.addSeparator()
        
        # # [NEW] 重置活跃功能
        # selected_rows = sorted(list(set([it.row() for it in self.stock_table.selectedItems()])))
        # if not selected_rows: selected_rows = [row]
        
        # title_reset = f"🔄 重置活跃 ({len(selected_rows)}只)" if len(selected_rows) > 1 else f"🔄 重置活跃 ({name})"
        # act_reset = menu.addAction(title_reset)
        # act_reset.triggered.connect(lambda: self._reset_stock_active(selected_rows))

        # [🚀 全局重置] 用户明确要求：重置活跃是全局重置，不是针对单个
        act_reset = menu.addAction("🔄 重置全局活跃")
        act_reset.triggered.connect(self._reset_stock_active)
        
        menu.addSeparator()
        act_copy = menu.addAction("📋 复制代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.stock_table.viewport().mapToGlobal(pos))

    def _reset_stock_active(self, selected_rows: list):
        """[NEW] 手动重置选中个股的活跃计数"""
        if not hasattr(self, 'detector') or not self.detector:
            return
            
        codes = []
        for r in selected_rows:
            c_item = self.stock_table.item(r, 0)
            if c_item:
                c = str(c_item.text()).strip()
                import re
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                if c and len(c) == 6:
                    codes.append(c)
        
        if codes:
            self.detector.reset_stock_active(codes)
            logger.info(f"🔄 [RacingPanel] 用户手动重置了 {len(codes)} 只个股的活跃计数")
            # 立即触发一次 UI 刷新（通过版本号间接或直接刷新）
            self.update_visuals()

    def _on_sector_context_menu(self, pos):
        """板块表右键菜单"""
        item = self.sector_table.itemAt(pos)
        if not item: return
        row = item.row()
        leader_item = self.sector_table.item(row, 3)
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
        item = self.sector_table.item(row, 3)
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
        self._open_sector_detail(sec_name)

    def _open_sector_detail(self, sec_name):
        """打开/置顶指定的板块详情弹窗"""
        if not sec_name: return
        
        # [🚀 板块回溯] 将打开的板块记入历史栈，确保回溯功能有效
        self._add_to_sector_history(sec_name)
        
        dlg_key = f"sector:{sec_name}"
        if dlg_key in self._detail_dialogs:
            dlg = self._detail_dialogs[dlg_key]
            try:
                dlg.show(); dlg.raise_(); dlg.activateWindow()
                return
            except: pass
            
        dialog = SectorDetailDialog(sec_name, self.detector, self._execute_linkage, parent=self)
        # [NEW] 实时同步全局形态详情开关
        if hasattr(self, '_global_show_reason') and hasattr(dialog, 'apply_show_reason_manual'):
            dialog.apply_show_reason_manual(self._global_show_reason)

        dialog.finished.connect(lambda: self._detail_dialogs.pop(dlg_key, None))
        # [🚀 极速联动] 挂载主面板刷新信号
        self.data_updated.connect(dialog.refresh_data)
        self._detail_dialogs[dlg_key] = dialog
        dialog.show()

    def _on_history_combo_changed(self, index):
        """[🚀 板块回溯] 下拉列表选中事件"""
        if self._is_updating_history or index < 0: return
        
        # 提取板块名 (从 "[Score] Name Date" 中剥离)
        text = self.combo_sector_history.itemText(index)
        if "]" in text:
            # 提取 ] 之后的部分，并尝试剥离末尾的日期 (如 0420)
            content = text.split("]", 1)[1].strip()
            # 如果末尾是 4 位数字日期，则截断
            parts = content.rsplit(" ", 1)
            if len(parts) > 1 and parts[1].isdigit() and len(parts[1]) == 4:
                sec_name = parts[0].strip()
            else:
                sec_name = content
        else:
            sec_name = text.strip()
            
        if sec_name in self._sector_history:
            self._open_sector_detail(sec_name)

    def _add_to_sector_history(self, sec_name):
        """[🚀 板块回溯] 维护历史栈，去重且限额"""
        if not sec_name: return
        if sec_name in self._sector_history:
            self._sector_history.remove(sec_name)
        
        self._sector_history.insert(0, sec_name)
        self._sector_history = self._sector_history[:15] # 最多保留 15 个
        
        self._refresh_history_combo()

    def _on_delete_history_clicked(self):
        """[🚀 板块回溯] 用户点击删除按钮，移除当前选中的历史记录项"""
        idx = self.combo_sector_history.currentIndex()
        if idx < 0: # 无选中项
            return
            
        text = self.combo_sector_history.itemText(idx)
        # --- [🚀 同步解析逻辑] 必须与跳转逻辑完全一致，支持剥离评分前缀和日期后缀 ---
        try:
            if "]" in text:
                content = text.split("]", 1)[1].strip()
                # 剥离 MMDD 格式的 4 位数字日期后缀
                parts = content.rsplit(" ", 1)
                if len(parts) > 1 and parts[1].isdigit() and len(parts[1]) == 4:
                    sec_name = parts[0].strip()
                else:
                    sec_name = content
            elif "(" in text:
                sec_name = text.split("(", 1)[0].strip()
            else:
                sec_name = text.split("@")[0].strip() if "@" in text else text.strip()
        except Exception:
            sec_name = text.strip()

        if sec_name in self._sector_history:
            self._sector_history.remove(sec_name)
            logger.info(f"🗑️ [History] 已从回溯历史中移除板块: {sec_name}")
            self._refresh_history_combo()
            self._save_ui_state() # 即时存盘，防止退出异常丢失操作成果

    def _refresh_history_combo(self):
        """[🚀 板块回溯] 完全重刷下拉框列表 (默认按评分大小排序显示，存储顺序不变)"""
        if not hasattr(self, 'combo_sector_history'): return
        self._is_updating_history = True
        try:
            # 记住当前选中的板块名
            current_sec = ""
            idx = self.combo_sector_history.currentIndex()
            if idx > 0:
                old_text = self.combo_sector_history.currentText()
                if "]" in old_text:
                    content = old_text.split("]", 1)[1].strip()
                    parts = content.rsplit(" ", 1)
                    current_sec = parts[0].strip() if (len(parts) > 1 and parts[1].isdigit() and len(parts[1]) == 4) else content
                else:
                    current_sec = old_text.strip()

            self.combo_sector_history.clear()
            # [USER REQUEST] 移除占位文本，默认显示最强制板块
            
            # --- [核心排序逻辑] 默认按评分大小排序显示，但底层 _sector_history 保持 MRU 顺序 ---
            temp_list = []
            for sec in self._sector_history:
                # [🚀 深度防护] 增加 detector 非空校验，防止初始化未完成时崩溃
                score = 0.0
                if self.detector and hasattr(self.detector, 'active_sectors'):
                    score = self.detector.active_sectors.get(sec, {}).get('score', 0.0)
                temp_list.append((score, sec))
            
            # 按评分降序排列
            temp_list.sort(key=lambda x: x[0], reverse=True)
            
            today_str = datetime.datetime.now().strftime("%m%d")
            for score, sec in temp_list:
                # 格式: [评分] 板块名 0420
                self.combo_sector_history.addItem(f"[{score:4.1f}] {sec} {today_str}")
            
            # 恢复之前的选中状态或默认选中第一名
            if current_sec:
                found = False
                for i in range(self.combo_sector_history.count()):
                    text = self.combo_sector_history.itemText(i)
                    if "]" in text:
                        content = text.split("]", 1)[1].strip()
                        parts = content.rsplit(" ", 1)
                        sn = parts[0].strip() if (len(parts) > 1 and parts[1].isdigit() and len(parts[1]) == 4) else content
                        if sn == current_sec:
                            self.combo_sector_history.setCurrentIndex(i)
                            found = True
                            break
                if not found and self.combo_sector_history.count() > 0:
                    self.combo_sector_history.setCurrentIndex(0)
            elif self.combo_sector_history.count() > 0:
                self.combo_sector_history.setCurrentIndex(0) # 默认最强

        finally:
            self._is_updating_history = False

    def _show_strongest_sector(self, code):
        """由个股代码查探并弹出其最强（在榜）的板块详情"""
        ts = self.detector._tick_series.get(code)
        if not ts or not ts.category: return
        
        import re
        cats = [c.strip() for c in re.split(r'[;；,，/ \\-]', str(ts.category)) if c.strip()]
        if not cats: return
        
        strongest_sector = None
        max_score = -999.0
        
        with self.detector._lock:
            active_sec = self.detector.active_sectors
            for cat in cats:
                if cat in active_sec:
                    score = active_sec[cat].get('score', 0.0)
                    if score > max_score:
                        max_score = score
                        strongest_sector = cat
        
        # 兜底：如果都没有上榜，取第一个
        if not strongest_sector:
            strongest_sector = cats[0]
            
        self._open_sector_detail(strongest_sector)

    def _run_dna_audit_batch(self):
        """[DNA-BATCH] 同步个股表选区送审"""
        row_count = self.stock_table.rowCount()
        if row_count == 0: return
        
        selected_items = self.stock_table.selectedItems()
        selected_rows = sorted(list(set([item.row() for item in selected_items])))
        
        if len(selected_rows) > 1:
            target_rows = selected_rows[:50]
        elif len(selected_rows) == 1:
            start_idx = selected_rows[0]
            target_rows = range(start_idx, min(start_idx + 20, row_count))
        else:
            target_rows = range(min(20, row_count))
            
        code_to_name = {}
        for row in target_rows:
            if row >= row_count: break
            c_item = self.stock_table.item(row, 0)
            n_item = self.stock_table.item(row, 1)
            if c_item:
                c = str(c_item.text()).strip()
                c = re.sub(r'[^\d]', '', c)
                if len(c) < 6 and c.isdigit(): c = c.zfill(6)
                
                n = str(n_item.text()).strip() if n_item else ""
                if n.startswith("🔔"): n = n.replace("🔔", "")

                if c and c != "N/A" and len(c) == 6:
                    code_to_name[c] = n
                    
        if code_to_name:
            dispatch_dna_audit(code_to_name, parent_widget=self)

    def _on_show_alerts_clicked(self):
        """专用按钮打开报警个股追踪窗口"""
        sec_name = "🔔 实时报警"
        dlg_key = f"sector:{sec_name}"
        if dlg_key in self._detail_dialogs:
            dlg = self._detail_dialogs[dlg_key]
            try:
                dlg.show(); dlg.raise_(); dlg.activateWindow()
                return
            except: pass
            
        dialog = SectorDetailDialog(sec_name, self.detector, self._execute_linkage, parent=self)
        dialog.finished.connect(lambda: self._detail_dialogs.pop(dlg_key, None))
        self.data_updated.connect(dialog.refresh_data)
        self._detail_dialogs[dlg_key] = dialog
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
        
        self._last_data_version = -1 
        self.update_visuals()

    def _on_sbc_stats_context_menu(self, pos):
        """基因报警卡片的右键菜单 - 提供重置功能"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #8B0000; }")
        
        act_reset = menu.addAction("🔄 重置基因报警数据")
        act_reset.triggered.connect(self._reset_sbc_signals)
        
        menu.exec(self.card_sbc_stats.mapToGlobal(pos))

    def _reset_sbc_signals(self):
        """手动清理所有基因报警相关的实时统计与历史"""
        if self.detector:
            # 1. 清理 Tracker 内部注册表 (SBC 信号)
            if self.detector.realtime_service and hasattr(self.detector.realtime_service, 'emotion_tracker'):
                tracker = self.detector.realtime_service.emotion_tracker
                if tracker:
                    tracker.clear()
            
            # 2. 同步清理 AlertManager 全局历史 (防止侧边栏逻辑冲突)
            get_alert_manager().clear_alert_history()
            
            # 3. 强制触发 UI 刷新 (包含所有已开启的明细窗口)
            self.detector.data_version += 1
            self.data_updated.emit()
            self.update_visuals()
            logger.info("⚡ [RacingPanel] 用户手动重置了所有基因报警数据 (SBC Registry & Alert History)")

    def _on_cycle_changed(self, val):
        self._reset_cycle_mins = val
        if hasattr(self, 'cycle_label'):
            self.cycle_label.setText(f"📊 起点参考周期: {val}m")

    def _adjust_cycle(self, offset):
        new_val = max(5, min(240, self._reset_cycle_mins + offset))
        self._on_cycle_changed(new_val)

    def _manual_reset_anchors(self):
        """[IMMEDIATE] 瞬间重置活跃数、DFF 与起点涨幅 (上下同步) - 修复死锁"""
        if self.detector:
            # [🚀 深度重置] 调用 Detector 全量重置逻辑 (包含活跃数、赛马稳定性、价格锚点等)
            self.detector.reset_observation_anchors()
            
            # [🚀 深度同步] 后置同步板块级锚点状态
            with self.detector._lock:
                for sec_name, sec in self.detector.active_sectors.items():
                    sec['leader_pct_diff'] = 0.0
                    score_val = sec.get('score', 0.0)
                    sec['score_anchor'] = score_val
                    self._sector_score_anchors[sec_name] = score_val # 同步至面板级锚点库
            
            # [🚀 深度重置] 同时也清空报警历史 (USER-FIX: 即时重置也重置活跃，确保全系统清爽)
            # get_alert_manager().clear_alert_history()
            # self.data_updated.emit()

            snap = self._create_anchor_snapshot(allow_system_time=True)
            if snap: 
                self._add_to_history(snap, force=True)
                self._current_anchor_ts = snap.get("ts", 0) # [NEW] 手动重置后立即设为当前锚点
                self._refresh_history_buttons()

            curr_time = getattr(self.detector, 'last_data_ts', 0)
            if curr_time == 0: curr_time = time.time()
            
            self._last_anchor_reset_data_ts = curr_time
            self._last_data_version = -1 
            self.update_visuals()
            logger.info("🔄 [Panel] 用户触发了全局即时重置：活跃数、均线稳定性及报警历史已清零")
            
    def _check_auto_anchor(self):
        """[🚀 启动静默模式] 仅捕捉不写盘"""
        if not self._anchor_history and self.detector:
            snap = self._create_anchor_snapshot()
            if snap and len(snap.get("c", [])) > 10:
                self._add_to_history(snap)
                self._apply_history_anchor(0)

    def _create_anchor_snapshot(self, allow_system_time=False):
        """记录当前所有个股的价格锚点快照 - [🚀 精准行情时间模式]"""
        if not self.detector: return None
        
        # 优先使用行情时间，如果尚未到开盘时间/无数据，则根据标志决定是否回退系统时间
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        
        # [🚀 精准化] 如果实盘还没开始（ts=0），正常逻辑该返回 None，但手动重置需要个时间戳
        if curr_time <= 0:
            if not allow_system_time:
                return None
            curr_time = time.time()
            
        with self.detector._lock:
            codes, prices = [], []
            for code, ts in self.detector._tick_series.items():
                if ts.current_price > 0:
                    codes.append(str(code))
                    prices.append(round(float(ts.current_price), 2))
            
            if not codes: return None # 无有效价格

            # [🚀 板块得分同步持久化] 记录当前所有活跃板块的即时力度得分
            sector_scores = {}
            for sec_name, sec_data in self.detector.active_sectors.items():
                sector_scores[sec_name] = round(float(sec_data.get('score', 0.0)), 1)

            return {
                "ts": float(curr_time), 
                "c": codes,   
                "p": prices,
                "ss": sector_scores # [NEW] Sector Scores Snapshot
            }

    def _add_to_history(self, snapshot, force=False):
        if not snapshot: return
        
        # [🚀 极限排序与去重] 确保时间轴顺序且不重复
        now_ts = snapshot.get('ts', 0)
        
        # 30秒内不重复捕捉相同起点的防护 (手动重置除外)
        if self._anchor_history and not force:
            last_ts = self._anchor_history[-1].get('ts', 0)
            if abs(now_ts - last_ts) < 30:
                logger.debug("🛡️ [Panel] 忽略 30 秒内的重复起点捕捉回调。")
                return

        self._anchor_history.append(snapshot)
        # 始终按时间排序
        self._anchor_history.sort(key=lambda x: x.get('ts', 0))
        
        # 保持 8 个槽位
        if len(self._anchor_history) > 8:
            self._anchor_history.pop(0)
            
        self._refresh_history_buttons()
        # [NEW] 立即持久化
        self._save_ui_state()

    def _refresh_history_buttons(self):
        try:
            # 清空现有按钮
            while self.history_layout.count():
                item = self.history_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            count = len(self._anchor_history)
            # 重新生成按钮
            for i, snap in enumerate(self._anchor_history):
                ts_val = snap.get("ts", 0)
                dt = datetime.datetime.fromtimestamp(ts_val)
                t_str = dt.strftime("%H:%M")
                d_str = dt.strftime("%d") # 0406->06, 0420->20
                btn = QPushButton(f"📍 {d_str} {t_str}")
                btn.setFixedSize(94, 26)
                btn.setMinimumWidth(94)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # [🚀 极简主题] 
                is_current = (abs(ts_val - self._current_anchor_ts) < 1.0)
                if is_current:
                    btn.setStyleSheet("""
                        QPushButton { 
                            background: #008B8B; color: white; border: 2px solid #00FFCC; 
                            border-radius: 4px; font-size: 11px; font-weight: bold;
                        }
                        QPushButton:hover { background: #00AAAA; color: white; border: 2px solid #55FFDD; }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton { 
                            background: #1C1C1E; color: #00FFCC; border: 1px solid #00FFCC; 
                            border-radius: 4px; font-size: 11px; font-weight: bold;
                        }
                        QPushButton:hover { background: #2C2C2E; color: white; border: 1px solid #55FFDD; }
                    """)
                btn.clicked.connect(lambda checked, idx=i: self._apply_history_anchor(idx))
                
                # [🚀 新增] 右键删除支持
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, idx=i: self._on_anchor_context_menu(pos, idx))
                
                self.history_layout.addWidget(btn)
                btn.show()
                
            # [🚀 几何诊断] 确保布局及时刷新
            self.history_layout.update()
        except Exception as e:
            logger.error(f"❌ [Panel] RefreshButtons Error: {e}")

    def _on_anchor_context_menu(self, pos, idx):
        """处理锚点按钮的右键删除菜单"""
        if idx >= len(self._anchor_history): return
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2C2C2E; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #FF2D55; }")
        
        act_del = menu.addAction("🗑️ 删除此起点")
        act_del.triggered.connect(lambda: self._remove_anchor(idx))
        
        menu.addSeparator()
        act_clear = menu.addAction("💣 清空所有起点")
        act_clear.triggered.connect(self._clear_all_anchors)
        
        target_btn = self.sender()
        if isinstance(target_btn, QPushButton):
            menu.exec(target_btn.mapToGlobal(pos))

    def _remove_anchor(self, idx):
        if 0 <= idx < len(self._anchor_history):
            snap = self._anchor_history.pop(idx)
            if abs(snap.get("ts", 0) - self._current_anchor_ts) < 1.0:
                 self._current_anchor_ts = 0
            self._refresh_history_buttons()
            self._save_ui_state()
            logger.info(f"🗑️ [Panel] 已删除历史起点 {idx+1}")

    def _clear_all_anchors(self):
        self._anchor_history = []
        self._current_anchor_ts = 0
        self._refresh_history_buttons()
        self._save_ui_state()
        logger.info("💣 [Panel] 已清空所有历史起点")

    def _apply_history_anchor(self, idx):
        """恢复历史锚点 - 兼容列式压缩协议"""
        if idx >= len(self._anchor_history): return False
        snap = self._anchor_history[idx]
        self._current_anchor_ts = snap.get("ts", 0) # [NEW] 记录当前应用的锚点
        self._refresh_history_buttons() # [NEW] 触发按钮重绘高亮
        
        # [🚀 极限解压] 兼容 Columnar (c, p) 与 Dict (anchors) 两种格式
        if "c" in snap and "p" in snap:
            anchors_map = dict(zip(snap["c"], snap["p"]))
        else:
            anchors_map = snap.get("anchors", {})
        
        applied_count = 0
        if self.detector:
            with self.detector._lock:
                # 检查 Detector 是否已经就绪
                if not self.detector._tick_series:
                    return False

                # 1. 恢复价格锚点
                for code, price in anchors_map.items():
                    if code in self.detector._tick_series:
                        ts = self.detector._tick_series[code]
                        ts.price_anchor = price
                        applied_count += 1
                        # [IMMEDIATE] 瞬间重算 pct_diff，确保 UI 瞬间看到变化
                        if ts.last_close > 0:
                            ts.pct_diff = (ts.current_price - ts.price_anchor) / ts.last_close * 100.0
                        else:
                            ts.pct_diff = 0.0
                
                # 2. 同步更新板块数据中的龙头 DFF 与评分锚点
                ss_map = snap.get("ss", {})
                self._sector_score_anchors.update(ss_map) # [🚀 核心补强] 恢复面板级评分锚点缓存
                
                for sec_name, sec_data in self.detector.active_sectors.items():
                    # A. 恢复评分锚点 (优先从面板缓存读取)
                    sec_data['score_anchor'] = self._sector_score_anchors.get(sec_name, sec_data.get('score', 0.0))
                    
                    # B. 同步龙头 DFF
                    leader_code = sec_data.get('leader') # [FIX] 统一使用 leader 键名
                    if leader_code and leader_code in self.detector._tick_series:
                        l_ts = self.detector._tick_series[leader_code]
                        sec_data['leader_pct_diff'] = l_ts.pct_diff
            
            # 3. 重置自动刷新计时器与节流阀，确保 UI 瞬间 100% 重绘
            self._last_anchor_reset_data_ts = getattr(self.detector, 'last_data_ts', time.time())
            self._last_ui_update_ts = 0      # 绕过 100ms 刷新限制
            self._last_data_version = -1     # 绕过数据版本缓存
            self._last_rendered_time = 0     # 绕过时间戳缓存
            
            # 4. [🚀 视觉增强] 为所有受影响的列预设高亮，产生即时刷新感
            now = time.time()
            for code in anchors_map.keys():
                self._table_highlights[("stock", code, 5)] = now # 起点
                self._table_highlights[("stock", code, 6)] = now # DFF
            
            self.update_visuals()
            logger.info(f"♻️ [Panel] 已恢复至历史起点 {idx+1} ({datetime.datetime.fromtimestamp(snap['ts']).strftime('%H:%M:%S')})，生效个股: {applied_count}。")
            return applied_count > 0
        return False

    def closeEvent(self, event):
        """[⭐ 统一管理] 退出时执行原子联行保存"""
        # 1. 强制执行一次安全的原子持久化
        try:
            self._save_ui_state(force=True)
        except: pass
        
        # 2. 批量静默关闭子窗
        for child in list(self._detail_dialogs.values()):
            try:
                if not child.isHidden():
                    child.close()
            except: pass
        # 2️⃣ 强制处理一次事件队列（关键）
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()


        self.save_window_position_qt(self, "BiddingRacingRhythmPanel")
        
        # ✅ 通知外部引用失效（关键：确保 TK 应用层感知对象已销毁）
        if hasattr(self, "main_app") and self.main_app:
            try:
                self.main_app._racing_panel_win = None
            except: pass
            
        # ✅ 发射关闭信号
        self.closed.emit()
        
        # ✅ 关键：允许 Qt 删除对象
        self.deleteLater()
        super().closeEvent(event)

    def _save_ui_state(self,force=False):
        """[🚀 物理存盘执行体] 防抖 + 去重 + 生命周期保护（增强版）"""

        # ==============================
        # 0️⃣ 初始化期禁止写入（核心防护）
        # ==============================
        if not getattr(self, "_ui_ready", False):
            return

        # ==============================
        # 1️⃣ 基础生存期保护（防 Qt 崩溃）
        # ==============================
        try:
            if (not hasattr(self, 'stock_table') or 
                not self.stock_table or 
                self.stock_table.isHidden()):
                return
        except RuntimeError:
            return

        # ==============================
        # 2️⃣ 时间防抖（硬限流，防止高频触发）
        # ==============================
        import time
        now = time.time()
        last_ts = getattr(self, "_last_save_ts", 0)

        # 300ms 内不允许重复写
        if not force and now - last_ts < 0.3:
            logger.debug(f"💾 [RacingPanel] 原子未存档 last_ts={last_ts}, now={now}, diff={now-last_ts}")
            return
        self._last_save_ts = now

        try:
            # ==============================
            # 3️⃣ 采集主表状态
            # ==============================
            state_stock = self.stock_table.horizontalHeader().saveState().toHex().data().decode()
            state_sector = self.sector_table.horizontalHeader().saveState().toHex().data().decode()

            # ==============================
            # 4️⃣ 采集详情窗口状态
            # ==============================
            open_windows = []
            for key, dlg in list(self._detail_dialogs.items()):
                try:
                    if not dlg.isHidden() and hasattr(dlg, 'get_ui_state'):
                        state = dlg.get_ui_state()
                        if state:
                            # 更安全的 key 解析
                            if ":" in key:
                                type_str, name = key.split(":", 1)
                            else:
                                type_str, name = "unknown", key

                            state.update({"type": type_str, "name": name})
                            open_windows.append(state)
                except Exception as e:
                    logger.debug(f"[UIState] detail save failed: {e}")

            # ==============================
            # 5️⃣ 构建配置
            # ==============================
            conf = {
                "header_stock": state_stock,
                "header_sector": state_sector,
                "splitter_main": self.main_splitter.saveState().toHex().data().decode(),
                "history": self._anchor_history[-20:],
                "current_anchor_ts": self._current_anchor_ts,
                "reset_cycle": self._reset_cycle_mins,
                "sector_history": self._sector_history,
                "window_geometry": self.saveGeometry().toHex().data().decode(),
                "open_details_v2": open_windows,
                "global_show_reason": self._global_show_reason
            }

            # ==============================
            # 6️⃣ hash 去重（关键优化）
            # ==============================
            import json, hashlib
            conf_str = json.dumps(conf, sort_keys=True)
            new_hash = hashlib.md5(conf_str.encode()).hexdigest()

            if getattr(self, "_last_save_hash", None) == new_hash:
                return

            self._last_save_hash = new_hash

            # ==============================
            # 7️⃣ 原子写入
            # ==============================
            _save_racing_config(conf)

            logger.info(f"💾 [RacingPanel] 原子存档完成 ({len(open_windows)} 窗口)")

        except Exception as e:
            logger.debug(f"⚠️ [RacingPanel] Save Ignored: {e}")

    def _restore_ui_state(self):
        """[🚀 状态还原] 恢复全量布局与历史"""
        try:
            conf = _get_racing_config()
            if not conf: return
            
            # 0. 恢复全局显示状态
            self._global_show_reason = conf.get("global_show_reason", False)
            self.stock_table.setColumnHidden(7, not self._global_show_reason)
            if self._global_show_reason: self.stock_table.setColumnWidth(7, 120)

            # 1. 恢复列宽与排序状态 (Header States)
            if "header_stock" in conf:
                self.stock_table.horizontalHeader().restoreState(QByteArray.fromHex(conf["header_stock"].encode()))
            if "header_sector" in conf:
                self.sector_table.horizontalHeader().restoreState(QByteArray.fromHex(conf["header_sector"].encode()))
            
            # 2. 恢复重置周期
            self._reset_cycle_mins = conf.get("reset_cycle", 60)
            self.cycle_label.setText(f"📊 起点参考周期: {self._reset_cycle_mins}m")
            
            # 3. 恢复历史锚点并渲染按钮
            hist = conf.get("history", [])
            self._current_anchor_ts = conf.get("current_anchor_ts", 0) # [NEW] 恢复当前选中状态
            if hist:
                self._anchor_history = hist
                self._refresh_history_buttons()
                logger.info(f"✅ [RacingPanel] 已恢复 {len(hist)} 个历史起点。")

            # [🚀 板块回溯] 恢复历史列表
            if "sector_history" in conf:
                self._sector_history = conf["sector_history"]
                self._refresh_history_combo()
                if self.combo_sector_history.count() > 0:
                    self.combo_sector_history.setCurrentIndex(0) # 默认显示最新的

            # 4. 恢复主窗口几何尺寸与分栏器布局
            if "window_geometry" in conf:
                self.restoreGeometry(QByteArray.fromHex(conf["window_geometry"].encode()))
            if "splitter_main" in conf:
                self.main_splitter.restoreState(QByteArray.fromHex(conf["splitter_main"].encode()))
                
            # 5. [🚀 自动恢复 V2] 批量重开所有未关闭的明细窗口并还原其内部布局
            open_list = conf.get("open_details_v2", [])
            for win_info in open_list:
                try:
                    w_type = win_info.get("type")
                    w_name = win_info.get("name")
                    if not w_type or not w_name: continue
                    
                    if w_type == "sector":
                        dlg_key = f"sector:{w_name}"
                        dialog = SectorDetailDialog(w_name, self.detector, self._execute_linkage, parent=self)
                    elif w_type == "category":
                        dlg_key = f"category:{w_name}"
                        dialog = CategoryDetailDialog(w_name, self.detector, self._execute_linkage, parent=self)
                    else:
                        continue
                        
                    dialog.finished.connect(lambda k=dlg_key: self._detail_dialogs.pop(k, None))
                    # [🚀 极速联动] 重启即挂载信号
                    self.data_updated.connect(dialog.refresh_data)
                    self._detail_dialogs[dlg_key] = dialog
                    
                    # 关键补丁：先显示窗口，再应用位置，确保 OS 接受布局变更
                    dialog.show()
                    dialog.apply_ui_state(win_info)
                    # [🚀 即时触发] 尝试首次渲染
                    dialog.refresh_data()
                except Exception as e:
                    logger.warning(f"⚠️ [RacingPanel] Restore Child Window '{w_name}' failed: {e}")
            
            if open_list:
                logger.info(f"🚀 [RacingPanel] 已通过原子协议恢复 {len(open_list)} 个详情窗口。")
                # [🚀 深度补丁] 增加非空与属性校验，防止启动过快导致的 NoneType 崩溃
                if self.detector and hasattr(self.detector, '_tick_series'):
                     if len(self.detector._tick_series) > 0:
                        QTimer.singleShot(800, self.data_updated.emit)
        except Exception as e:
            logger.error(f"⚠️ [RacingPanel] Restore UI State Error: {e}")
        finally:
            self._ui_ready = True

    def _arrange_detail_windows(self):
        """[🚀 垂直联排优化] 极限收缩 + 磁吸叠层 + 阶梯分栏(优先对齐主窗)"""
        # [🚀 针对主窗口] 点击整理时同步校准主表领军个股视图列宽
        if getattr(self, '_global_show_reason', False):
            if hasattr(self, 'stock_table'):
                header = self.stock_table.horizontalHeader()
                header.blockSignals(True)
                try:
                    # [🚀 极致紧凑版] 前置列尽可能压缩，为形态理由留出空间
                    self.stock_table.setColumnWidth(0, 62)   # 代码
                    self.stock_table.setColumnWidth(1, 72)   # 名称
                    self.stock_table.setColumnWidth(2, 35)   # 结构分
                    self.stock_table.setColumnWidth(3, 35)   # 活跃
                    self.stock_table.setColumnWidth(4, 62)   # 涨幅
                    self.stock_table.setColumnWidth(5, 62)   # 起点
                    self.stock_table.setColumnWidth(6, 62)   # DFF
                    if not self.stock_table.isColumnHidden(7):
                        self.stock_table.setColumnWidth(7, 120) # 保持原样 180
                finally:
                    header.blockSignals(False)
        else:
            # [🚀 标准紧凑版] 无理由列时，适当放开其他列宽
            if hasattr(self, 'stock_table'):
                header = self.stock_table.horizontalHeader()
                header.blockSignals(True)
                try:
                    self.stock_table.setColumnWidth(0, 62)   # 代码
                    self.stock_table.setColumnWidth(1, 80)   # 名称
                    self.stock_table.setColumnWidth(2, 62)   # 结构分
                    self.stock_table.setColumnWidth(3, 62)   # 活跃
                    self.stock_table.setColumnWidth(4, 70)   # 涨幅
                    self.stock_table.setColumnWidth(5, 70)   # 起点
                    self.stock_table.setColumnWidth(6, 62)   # DFF
                    # 隐藏理由列或保持 0
                    if not self.stock_table.isColumnHidden(7):
                        self.stock_table.setColumnWidth(7, 0)
                finally:
                    header.blockSignals(False)
        dlgs = [dlg for dlg in self._detail_dialogs.values() if not dlg.isHidden()]
        if not dlgs: 
            logger.info("ℹ️ [Panel] 当前没有打开的详情窗口。")
            return
        
        main_geo = self.frameGeometry()
        screen_geo = self.screen().availableGeometry()
        
        # [✨ 规格决策]
        # min_h 设为 210px，确保能稳稳看到4行数据
        min_h = 210
        title_bar_h = 32
        
        # 初始策略：优先高度对齐主窗口，如果窗口非常多(超过3列)，则释放到屏幕高度
        num_per_main_col = max(1, main_geo.height() // min_h)
        if len(dlgs) > num_per_main_col * 3:
            # 只有“超多”时才考虑上下铺满屏幕
            limit_y_bottom = screen_geo.bottom()
            col_base_y = screen_geo.top()
            target_h = max(min_h, screen_geo.height() // (len(dlgs) // 3 + 1))
        else:
            # 优先在主窗口的高度范围内铺
            limit_y_bottom = main_geo.bottom()
            col_base_y = main_geo.top()
            target_h = main_geo.height() // num_per_main_col

        # [✨ 磁吸起点]
        # -6px 抵消第一列与主窗口之间的隐形边框，留出1px缝隙防止压死
        col_x = main_geo.right() - 6
        curr_y = col_base_y
        padding = 1 # 极微小间距，保留磁吸感同时防止压盖
        max_w_in_col = 0
        
        for i, dlg in enumerate(dlgs):
            # [🚀 极速整理算法] 挂起更新并阻止信号，防止整理期间的 UI 假死
            dlg.setUpdatesEnabled(False)
            header = dlg.table.horizontalHeader()
            header.blockSignals(True)
            header.setStretchLastSection(False)
            
            # [🚀 零测绘开销] 放弃耗时的自适应测绘，直接应用主表同款高度紧凑布局
            # 0:代码(62), 1:名称(72), 2:得分(35), 3:活跃(35), 4:涨幅(62), 5:起点(62), 6:DFF(62) -> 总计 390
            fixed_cols_w = [62, 72, 35, 35, 62, 62, 62]
            for col, w in enumerate(fixed_cols_w):
                if col < dlg.table.columnCount():
                    header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                    dlg.table.setColumnWidth(col, w)
            
            # [🚀 理由列固定策略]
            reason_w = 0
            if getattr(self, '_global_show_reason', False) and dlg.table.columnCount() > 7:
                header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
                dlg.table.setColumnWidth(7, 120)
                reason_w = 120
            else:
                if dlg.table.columnCount() > 7:
                    dlg.table.setColumnWidth(7, 0)
            
            # [🚀 结果计算] 窗口宽度 = 基础列宽(390) + 理由列(0/120) + 边距冗余(35)
            target_w = 390 + reason_w + 35
            
            header.blockSignals(False)
            # 空间防护
            if col_x > screen_geo.right() - target_w:
                col_x = max(screen_geo.left(), screen_geo.right() - target_w - 4)
                
            dlg.resize(target_w, target_h)
            dlg.setUpdatesEnabled(True)

            dlg_w = dlg.width()
            dlg_h = dlg.height()
            
            final_x = min(col_x, screen_geo.right() - dlg_w)
            final_y = min(curr_y, screen_geo.bottom() - dlg_h)
            
            dlg.move(final_x, final_y)
            dlg.activateWindow()
            
            # 下一个位置(垂直垂直叠层)
            curr_y += target_h
            
        # [✨ 倒序 Z-Order 叠层] 压盖标题栏
        for dlg in reversed(dlgs):
            dlg.raise_()
        
        logger.info(f"📐 [Panel] 已完成 {len(dlgs)} 个详情窗口的阶梯式分栏(磁吸微调)联排。")

    def _set_global_show_reason(self, val):
        """全局形态详情开关同步 - 被子弹窗调用"""
        self._global_show_reason = val
        # 同步主界面个股列表
        self.stock_table.setColumnHidden(7, not val)
        if val: self.stock_table.setColumnWidth(7, 120)
        
        for dlg in self._detail_dialogs.values():
            if hasattr(dlg, 'apply_show_reason_manual'):
                dlg.apply_show_reason_manual(val)
        # 强制保存一次 UI 状态
        self._save_ui_state()

    def _get_synthetic_score(self, ts):
        """[🚀 性能加速版] 动态合成显示分数"""
        try:
            main_score = ts.score
            if main_score < 0.01:
                activity_score = (getattr(ts, 'signal_count', 0) * 1.5) + (abs(ts.current_pct) * 0.2)
                return max(activity_score, getattr(ts, 'momentum_score', 0) * 0.05)
            return main_score
        except AttributeError:
            return 0.0

    def _execute_linkage(self, code, name="", source="racing_panel"):
        if not code or self._select_code == str(code):
            return
        self._select_code = str(code)
        if self.stock_sender:
            try:
                self.stock_sender.send(str(code))
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

    def update_market_stats(self, stats: dict):
        """接收外部传输的系统级全盘温度及涨跌并渲染到顶部时间组件上"""
        if hasattr(self, 'timeline'):
            self.timeline.update_market_stats(stats)

    def update_visuals(self):
        if not self.detector: return
        if self._is_rendering: return
        
        # --- [⚡ 核心生命周期：心跳驱动自启动逻辑] ---
        with self.detector._lock:
            has_data = len(self.detector._tick_series) > 0
            
        if has_data:
            # A. 恢复今日已有历史
            if self._auto_restore_pending:
                self._auto_restore_pending = False
                last_idx = len(self._anchor_history) - 1
                if self._apply_history_anchor(last_idx):
                    logger.info(f"🚀 [Panel] 行情心跳到达，成功同步今日历史起点 ({last_idx+1})。")
                else:
                    logger.debug("⚠️ [Panel] 行情到达但尝试恢复历史失败。")
            
            # B. 启动时自动捕捉首个新起点 (如果历史为空或日期更迭)
            elif self._auto_capture_today_first:
                self._auto_capture_today_first = False # 仅执行一次
                if not self._anchor_history:
                    snap = self._create_anchor_snapshot()
                    # 确保个股数足够
                    if snap and len(snap.get("c", [])) > 10:
                        self._add_to_history(snap)
                        self._apply_history_anchor(0)
                        logger.info("✨ [Panel] 启动观测到首波行情，已自动创建并激活今日首个起点。")
            
            # C. 处理之前的待处理强制恢复任务 (用户点击驱动)
            if self._pending_auto_restore_idx >= 0:
                idx = self._pending_auto_restore_idx
                self._pending_auto_restore_idx = -1 
                self._apply_history_anchor(idx)

        # [NEW] 自动捕捉首个起点 (仅在历史为空时执行一次，优先于版本检查)
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        if curr_time > 0 and not self._anchor_history:
            snap = self._create_anchor_snapshot()
            # [🚀 极限压缩] 使用 'c' 列表长度判定
            if snap and len(snap.get("c", [])) > 0:
                self._add_to_history(snap)
                self._apply_history_anchor(0)
                logger.debug(f"🚩 [Panel] 捕获并激活全天首个起点 ({len(snap['c'])} 只个股)。")

        now = time.time()
        if now - self._last_ui_update_ts < 0.1:
            if self._table_highlights: self._refresh_fading_only() 
            return
        self._last_ui_update_ts = now
        
        # [NEW] 🧬 更新 🧬 SBC 基因报警实时统计
        if hasattr(self, 'card_sbc_stats') and self.detector and self.detector.realtime_service:
            tracker = getattr(self.detector.realtime_service, 'emotion_tracker', None)
            if tracker:
                reg = getattr(tracker, '_sbc_signals_registry', {})
                sbc_count = len(reg)
                self.card_sbc_stats.setText(f"🧬 实时基因报警: {sbc_count}")
                # 如果有报警，使用更醒目的边框亮色
                if sbc_count > 0:
                    self.card_sbc_stats.setStyleSheet("""
                        QPushButton { 
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8B0000, stop:1 #FF4500); 
                            color: white; border: 2px solid #FFD700; border-radius: 6px; 
                            font-weight: bold; font-size: 11px; text-align: center;
                        }
                        QPushButton:hover { background: #FF0000; border: 2px solid white; }
                    """)
                else:
                    self.card_sbc_stats.setStyleSheet("""
                        QPushButton { 
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4B0082, stop:1 #800080); 
                            color: #00FFCC; border: 1px solid #444; border-radius: 6px; 
                            font-weight: bold; font-size: 11px; text-align: center;
                        }
                        QPushButton:hover { background: #9400D3; border: 1px solid white; color: white; }
                    """)

        curr_ver = getattr(self.detector, 'data_version', 0)
        curr_time = getattr(self.detector, 'last_data_ts', 0)
        
        # [NEW] 同步赛马竞技进度时间轴
        if curr_time > 0 and hasattr(self, 'timeline'):
            t_str = datetime.datetime.fromtimestamp(curr_time).strftime("%H:%M:00")
            self.timeline.set_time(t_str)
            
        # [🚀 标准化时间判定] 使用标准 cct 函数判定交易日与交易时间
        time_hhmm = 0
        if curr_time > 0:
            try:
                # 转换 Unix 时间戳为 HHMM 格式以适配 cct.get_work_time
                time_hhmm = int(datetime.datetime.fromtimestamp(curr_time).strftime("%H%M"))
            except:
                pass
            
        # [NEW] 周期性自动重置基准锚点
        if curr_time > 0 and time_hhmm > 0:
            if self._last_anchor_reset_data_ts == 0:
                self._last_anchor_reset_data_ts = curr_time
            
            interval_sec = self._reset_cycle_mins * 60
            if curr_time - self._last_anchor_reset_data_ts > interval_sec:
                # [FIX] 使用系统标准函数：判断是否为交易时间且为交易日
                is_trading_time = cct.get_work_time(time_hhmm) and cct.get_trade_date_status()
                
                if is_trading_time:
                    logger.info(f"⏰ [Panel] 到达基准重置周期 ({self._reset_cycle_mins} min), 正在自动录入起点快照并执行刷新...")
                    self._manual_reset_anchors()
                    curr_ver = -1 # 强制后续刷新
                else:
                    # 如果不在交易时间，仅平移重置参考点，避免开盘瞬发触发
                    self._last_anchor_reset_data_ts = curr_time

        # [🚀 优化与边界保护] 同步 cct 阈值修复时间判定逻辑
        is_break = (1130 <= time_hhmm < 1300)
        is_closing = (time_hhmm >= 1505 or (0 < time_hhmm < 915) or is_break)
        
        # 旁路判定：正常跳过渲染的条件
        skip_optimization = (curr_ver == self._last_data_version and curr_time == getattr(self, "_last_rendered_time", 0))
        
        # [🚀 启动保护] 如果是首次启动，无论如何都要跑一遍流程
        if self._first_boot_render:
            is_closing = True # 借用 is_closing 强制通过
            self._first_boot_render = False
            logger.info("🎬 [Panel] Bootstrap: Initial rendering process triggered.")

        if skip_optimization and not is_closing:
            # [🚀 极速联动补齐] 哪怕跳过渲染逻辑，也要检测子窗同步心跳。
            # 强行确保窗口持有正确的 detector 引用
            for dlg in self._detail_dialogs.values():
                if not dlg.isHidden():
                    if getattr(dlg, 'detector', None) != self.detector:
                        dlg.detector = self.detector

            if time.time() % 3.0 < 0.2:
                self.data_updated.emit()
            if self._table_highlights: self._refresh_fading_only()
            return
        
        self._is_rendering = True
        try:
            with self.detector._lock:
                raw_ts_list = list(self.detector._tick_series.values())
                # [🚀 核心对齐] 获取实时数据的副本并注入面板级锚点，防止被 Detector 异步重写导致涨跌数据归零
                active_sectors = []
                for sec_name, sec_dict in self.detector.active_sectors.items():
                    sd = sec_dict.copy()
                    sd['score_anchor'] = self._sector_score_anchors.get(sec_name, sd.get('score', 0.0))
                    active_sectors.append(sd)

            
            # --- [🚀 兜底逻辑] 如果 Detector 处于冷启动(HDF5缺失)，UI 层反向聚合板块 ---
            # 修复：即便 active_sectors 不为空，如果数据极少（例如只有不到3个板块），也尝试从现有个股中补充
            if (not active_sectors or len(active_sectors) < 3) and raw_ts_list:
                temp_sectors = {}
                # 为了加速，仅循环 raw_ts_list
                for ts in raw_ts_list:
                    # 只要有板块信息且不是空数据
                    if not ts.category or (ts.current_pct == 0 and ts.score < 0.1): continue
                    # 容错处理：多种分隔符支持
                    cats = [c.strip() for c in re.split(r'[;；,，/\- ]', str(ts.category)) if c.strip()]
                    for cat in cats:
                        if cat not in temp_sectors:
                            temp_sectors[cat] = {
                                'sector': cat, 'score': 0.0, 'leader': '', 
                                'leader_name': '', 'leader_pct': -100.0, 
                                'leader_pct_diff': 0.0,  
                                'score_anchor': self._sector_score_anchors.get(cat, 0.0), # [🚀 修复] 聚合模式下的锚点对齐
                                'count': 0,
                                'followers': [] 
                            }
                        s = temp_sectors[cat]
                        s['count'] += 1
                        
                        # [🚀 分数反推] 简单启发式得分：个股数权重 + 领涨表现
                        # 使得 结构分 不再显示为 0.0
                        ts_contrib = 1.0 + (ts.current_pct / 5.0) if ts.current_pct > 0 else 0.5
                        s['score'] += ts_contrib
                        
                        # 记录所有个股用于后续挑选联动详情
                        s['followers'].append({'name': ts.name, 'pct': ts.current_pct})
                        
                        if ts.current_pct > s['leader_pct']:
                            s['leader_pct'] = ts.current_pct
                            s['leader_name'] = ts.name
                            s['leader'] = ts.code
                            s['leader_pct_diff'] = ts.pct_diff # [FIX] 同步记录龙头的 DFF
                
                # 合并现有的和推算的，并对联动详情排序
                existing_names = {s.get('sector') for s in active_sectors}
                for s_name, s_data in temp_sectors.items():
                    if s_name not in existing_names:
                         # [🚀 评分公式重构] 防止大板块直接 99.9 饱和
                         # 基础分 = log2(个股数) * 12 + 龙头系数
                         import math
                         base_score = math.log2(max(1, s_data['count'])) * 12
                         perf_score = max(0, s_data['leader_pct']) * 2.5
                         s_data['score'] = round(min(base_score + perf_score, 98.5), 1)
                         
                         # 联动详情：排除龙头本身，取前3名非龙头
                         l_code = s_data['leader']
                         f_list = [f for f in s_data['followers'] if f['name'] != s_data['leader_name']]
                         f_list.sort(key=lambda x: x['pct'], reverse=True)
                         s_data['followers'] = f_list[:3]
                         active_sectors.append(s_data)
                
            # --- [🚀 极致同步] 无论数据来源，实时校准板块龙头的最新行情 (Pct / DFF) ---
            for sec in active_sectors:
                leader_code = sec.get('leader')
                if leader_code and leader_code in self.detector._tick_series:
                    l_ts = self.detector._tick_series[leader_code]
                    sec['leader_pct'] = l_ts.current_pct
                    sec['leader_name'] = l_ts.name
                    # [🚀 极速重算] 确保 DFF 在应用锚点后立即刷新，不依赖后台周期
                    if l_ts.price_anchor > 0 and l_ts.last_close > 0:
                        sec['leader_pct_diff'] = ((l_ts.current_price - l_ts.price_anchor) / l_ts.last_close) * 100
                    else:
                        sec['leader_pct_diff'] = 0.0

            # --- 2. [WORK-ZONE] 锁外分析计算 ---
            # 宽放个股显示阈值，确保午盘休息时不仅能看到之前的龙头，也能看到活跃个股
            active_ts = [ts for ts in raw_ts_list if abs(ts.current_pct) > 0.001 or ts.score > 0.05 or ts.momentum_score > 0]
            dist = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 0}
            
            filtered_ts = []
            sel_cat = self.pie_widget.selected_category
            for ts in active_ts:
                role = get_racing_role(ts)
                dist[role] += 1
                if not sel_cat or role == sel_cat:
                    filtered_ts.append(ts)

            # [🚀 性能优化] 预计算所有过滤后个股的合成评分，避免在排序循环中重复计算
            score_cache = {ts.code: self._get_synthetic_score(ts) for ts in filtered_ts}
            
            def flatten_ts(ts):
                # [🚀 结构分展示优化] 统一调用合成评分公式 (命中缓存)
                display_score = score_cache.get(ts.code, 0)
                
                # [NEW] SBC 信号标记
                is_sbc_active = False
                if self.detector and self.detector.realtime_service and self.detector.realtime_service.emotion_tracker:
                    is_sbc_active = ts.code in getattr(self.detector.realtime_service.emotion_tracker, '_sbc_signals_registry', {})

                # [全局自适应] 理由采集
                reason = ""
                if self._global_show_reason:
                    if self.detector and self.detector.realtime_service and self.detector.realtime_service.emotion_tracker:
                        reg = getattr(self.detector.realtime_service.emotion_tracker, '_sbc_signals_registry', {})
                        if ts.code in reg: reason = reg[ts.code].get('desc', '')
                    if not reason: reason = getattr(ts, 'pattern_hint', "")

                return (ts.code, ts.name, round(display_score, 1), ts.signal_count, ts.current_pct, ts.pct_diff, ts.dff, is_sbc_active, reason)

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

                # --- [🚀 优化2] 手动排序逻辑 (对齐全局与本地) ---
                sort_attr_map = {0:'code', 1:'name', 2:'score', 3:'signal_count', 4:'current_pct', 5:'start_pct', 6:'pct_diff'}
                s_attr = sort_attr_map.get(self._sort_col, 'score')
                is_rev = (self._sort_order == Qt.SortOrder.DescendingOrder)
                
                # 执行前提取 SBC 注册表用于排序判定
                tracker = None
                if self.detector and self.detector.realtime_service:
                    tracker = getattr(self.detector.realtime_service, 'emotion_tracker', None)
                sbc_registry = getattr(tracker, '_sbc_signals_registry', {}) if tracker else {}

                # 执行排行榜处理 (基于过滤后的结果，增加稳定性排序)
                def get_stock_sort_key(ts):
                    # [🚀 排序优先级增强] ⚡(2) > 🔔(1) > 普通(0)
                    has_alert = get_alert_manager().is_alerted(ts.code)
                    has_sbc = ts.code in sbc_registry
                    prio = 2 if has_sbc else (1 if has_alert else 0)
                    
                    if s_attr == 'start_pct':
                        val = ts.current_pct - ts.pct_diff
                    elif s_attr == 'pct_diff':
                        val = ts.pct_diff
                    elif s_attr == 'score':
                        val = score_cache.get(ts.code, 0)
                    else:
                        val = getattr(ts, s_attr, 0)
                    
                    if s_attr == 'name':
                        # 确保图标个股在默认降序(Descending)时聚类在顶部
                        return (prio, val, ts.code)
                    return (val, ts.code)
                
                sorted_raw = sorted(filtered_ts, key=get_stock_sort_key, reverse=is_rev)[:20]
                flattened_ts = [flatten_ts(ts) for ts in sorted_raw]
                
                self.stock_table.blockSignals(True)
                self.sector_table.blockSignals(True)
                self._update_table_optimized(self.stock_table, flattened_ts)
                
                sort_attr_map_sector = {0:'sector', 1:'score', 2:'score_diff', 3:'leader_name', 4:'leader_pct', 5:'leader_start_pct', 6:'leader_pct_diff'}
                s_attr_sec = sort_attr_map_sector.get(self._sort_col_sector, 'score')
                is_rev_sec = (self._sort_order_sector == Qt.SortOrder.DescendingOrder)
                
                # [🚀 优化] 板块表手动排序逻辑 (对齐 DFF 与起点逻辑)
                def get_sec_val(sec, attr):
                    if attr == 'leader_start_pct':
                        return sec.get('leader_pct', 0) - sec.get('leader_pct_diff', 0)
                    if attr == 'score_diff':
                        return sec.get('score', 0) - sec.get('score_anchor', sec.get('score', 0))
                    return sec.get(attr, 0)

                # 全量排序结果
                all_sorted_sectors = sorted(
                    active_sectors, 
                    key=lambda x: (get_sec_val(x, s_attr_sec), x.get('sector', '')), 
                    reverse=is_rev_sec
                )

                # [🚀 标注建议] 移除强力的龙头去重逻辑，防止强核心驱动下其他强势概念被隐藏
                unique_leader_sectors = []
                for sec in all_sorted_sectors:
                    unique_leader_sectors.append(sec)
                    if len(unique_leader_sectors) >= 20:
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
            # [🚀 极速联动] 主面板渲染结束，通知详情窗同步刷新
            self.data_updated.emit()
            
            # [🚀 板块回溯] 定时更新下拉列表中板块的实时得分 (非重绘，仅更新文本)
            if hasattr(self, 'combo_sector_history') and not self._is_updating_history:
                self._is_updating_history = True
                try:
                    today_str = datetime.datetime.now().strftime("%m%d")
                    for i in range(self.combo_sector_history.count()): 
                        old_text = self.combo_sector_history.itemText(i)
                        if "]" in old_text:
                            # 提取板块名 (剥离评分前缀和日期后缀)
                            content = old_text.split("]", 1)[1].strip()
                            parts = content.rsplit(" ", 1)
                            sn = parts[0].strip() if (len(parts) > 1 and parts[1].isdigit() and len(parts[1]) == 4) else content
                            
                            # 获取最新评分
                            sc = self.detector.active_sectors.get(sn, {}).get('score', 0.0)
                            nw = f"[{sc:4.1f}] {sn} {today_str}"
                            if old_text != nw:
                                self.combo_sector_history.setItemText(i, nw)
                finally:
                    self._is_updating_history = False
        except Exception as e:
            import traceback
            logger.error(f"❌ [RacingPanel] Update Error: {e}\n{traceback.format_exc()}")
        finally:
            self._is_rendering = False



    def _update_cell(self, table, row, col, text, color=None, align=None, is_numeric=True, bg_color=None, sort_prio=None):
        it = table.item(row, col)
        if not it:
            if sort_prio is not None:
                it = LabeledStockItem(text, sort_prio) # 专门处理带图标排序
            else:
                it = NumericTableWidgetItem(text) if is_numeric else QTableWidgetItem(text)
            
            if color: it.setForeground(color)
            if bg_color: it.setBackground(bg_color)
            if align: it.setTextAlignment(align)
            table.setItem(row, col, it)
            return True
            
        changed = False
        if it.text() != text:
             it.setText(text)
             changed = True
        
        # [NEW] 同步更新排序优先级
        if sort_prio is not None and hasattr(it, 'sort_prio') and it.sort_prio != sort_prio:
            it.sort_prio = sort_prio
            changed = True
        if color and it.foreground().color() != color:
             it.setForeground(color)
             changed = True
        if bg_color and it.background().color() != bg_color:
             it.setBackground(bg_color)
             changed = True
        return changed

    def _update_table_optimized(self, table, flattened_data):
        is_first_init = table.rowCount() == 0
        if table.rowCount() != len(flattened_data):
            table.setRowCount(len(flattened_data))
        for i, row_data in enumerate(flattened_data):
            code, name, score, sig, pct, diff, dff, is_sbc_active, reason = row_data
            
            # [⚡ 报警核验] 针对命中报警或有 SBC 信号的个股应用高对比度
            is_generic_alert = get_alert_manager().is_alerted(code)
            is_alerted = is_generic_alert or is_sbc_active
            bg_c = self._UI_CACHE["COLOR_ALERT_BG"] if is_alerted else None
            txt_c = self._UI_CACHE["COLOR_ALERT_TEXT"] if is_alerted else None
            
            # [NEW] SBC 系统标记：⚡在前, 🔔在中, 代码列保持纯净 (权重越大越靠前)
            # 排序优先级: ⚡(2) > 🔔(1) > 普通(0)
            display_code = code
            display_name = name
            sort_p = 0
            
            if is_generic_alert:
                display_name = f"🔔{display_name}"
                sort_p = 1
            if is_sbc_active:
                display_name = f"⚡{display_name}"
                sort_p = 2

            self._update_cell(table, i, 0, display_code, color=txt_c, is_numeric=False, bg_color=bg_c)
            self._update_cell(table, i, 1, display_name, color=txt_c, is_numeric=False, bg_color=bg_c, sort_prio=sort_p)
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
            if self._update_cell(table, i, 6, dff_txt, self._UI_CACHE["COLOR_RED"] if diff > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if diff < -0.001 else Qt.GlobalColor.white)):
                if not is_first_init: self._table_highlights[("stock", code, 6)] = time.time()
            self._apply_flash_effect(table.item(i, 6), ("stock", code, 6))

            # [全局自适应] 第 7 列：形态理由
            if self._global_show_reason:
                c_reason = self._UI_CACHE["COLOR_CYAN"] if ("🚀" in reason or "🔥" in reason) else QColor("#AAAAAA")
                if is_alerted: c_reason = self._UI_CACHE["COLOR_ALERT_TEXT"]
                self._update_cell(table, i, 7, str(reason), c_reason, bg_color=bg_c)
            
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
            if self._update_cell(table, i, 1, str(score), self._UI_CACHE["COLOR_GOLD"]):
                if not is_first_init: self._table_highlights[("sector", s_name, 1)] = time.time()
            self._apply_flash_effect(table.item(i, 1), ("sector", s_name, 1))

            # 2. 得分增量 (展示相对于锚点的强度增量)
            score_anchor = sec.get('score_anchor', score)
            score_diff = score - score_anchor
            diff_txt = f"{score_diff:+.1f}"
            c_diff = self._UI_CACHE["COLOR_RED"] if score_diff > 0.05 else (self._UI_CACHE["COLOR_GREEN"] if score_diff < -0.05 else Qt.GlobalColor.white)
            
            if self._update_cell(table, i, 2, diff_txt, c_diff):
                if not is_first_init: self._table_highlights[("sector", s_name, 2)] = time.time()
            self._apply_flash_effect(table.item(i, 2), ("sector", s_name, 2))
                
            # 3. 领涨龙头
            l_total_pct = sec.get('leader_pct', 0.0)
            l_dff = sec.get('leader_pct_diff', 0.0)
            l_start_pct = l_total_pct - l_dff
            leader_display = f"{sec.get('leader_name')} ({sec.get('leader')})"
            self._update_cell(table, i, 3, leader_display, is_numeric=False)
                
            # 4. 龙头总涨幅
            l_pct_text = f"{l_total_pct:+.2f}%"
            c_pct = self._UI_CACHE["COLOR_RED"] if l_total_pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_total_pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 4, l_pct_text, c_pct):
                if not is_first_init: self._table_highlights[("sector", s_name, 4)] = time.time()
            self._apply_flash_effect(table.item(i, 4), ("sector", s_name, 4))
            
            # 5. 起点涨幅
            start_txt = f"{l_start_pct:+.2f}%"
            c_start = self._UI_CACHE["COLOR_RED"] if l_start_pct > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_start_pct < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 5, start_txt, c_start):
                if not is_first_init: self._table_highlights[("sector", s_name, 5)] = time.time()
            self._apply_flash_effect(table.item(i, 5), ("sector", s_name, 5))

            # 6. 龙头DFF (纯净显示)
            dff_txt = f"{l_dff:+.2f}%"
            c_dff = self._UI_CACHE["COLOR_RED"] if l_dff > 0.001 else (self._UI_CACHE["COLOR_GREEN"] if l_dff < -0.001 else Qt.GlobalColor.white)
            if self._update_cell(table, i, 6, dff_txt, c_dff):
                if not is_first_init: self._table_highlights[("sector", s_name, 6)] = time.time()
            self._apply_flash_effect(table.item(i, 6), ("sector", s_name, 6))

            # 7. 联动详情
            followers = sec.get('followers', [])
            f_items = []
            for f in followers[:3]:
                # [FIX] 名称空缺治理：若 f['name'] 为空，则从探测器回填，否则回退到代码
                f_name = f.get('name') or ""
                if not f_name:
                    ts_ref = self.detector._tick_series.get(f.get('code'))
                    if ts_ref: f_name = ts_ref.name
                if not f_name: f_name = f.get('code', "")
                f_items.append(f"{f_name}({f['pct']:+.1f}%)")
            
            f_txt = ",".join(f_items)
            if self._update_cell(table, i, 7, f_txt, is_numeric=False):
                if not is_first_init: self._table_highlights[("sector", s_name, 7)] = time.time()
            self._apply_flash_effect(table.item(i, 7), ("sector", s_name, 7))

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

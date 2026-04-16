# -*- coding: utf-8 -*-
import math
import os
import json
from typing import Dict, List, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QPointF, QSize, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QConicalGradient, 
    QLinearGradient, QRadialGradient, QPolygon, QPainterPath
)

from tk_gui_modules.qt_table_utils import EnhancedTableWidget, NumericTableWidgetItem
from tk_gui_modules.window_mixin import WindowMixin
from signal_bus import SignalBus
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger(name=__name__, level=LoggerFactory.WARNING)
# logger.setLevel(LoggerFactory.ERROR)
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
        self._angles_cache = {} # 缓存每个扇区的角度范围用于点击识别
        self._animation_angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.start(50)
    def _update_animation(self):
        # 如果数据全是静默(没有赛马)，或者已被选中分类，则停止旋转以节省 CPU 且防晃眼
        if self.data.get("静默", 0) >= 99 or self.selected_category:
             return
        self._animation_angle = (self._animation_angle + 1) % 360
        self.update()

    def set_data(self, distribution: Dict[str, int]):
        self.data = distribution
        self.update()

    def _get_hit_category(self, pos: QPoint):
        """核心碰撞检测：将鼠标坐标转换为极坐标位置判断分类"""
        rect = self.rect()
        center = rect.center()
        # 排除圆心区域（点击圆心清除过滤）
        dist = math.sqrt((pos.x() - center.x())**2 + (pos.y() - center.y())**2)
        side = min(rect.width(), rect.height()) - 40
        if dist < side * 0.3: return "ALL"
        if dist > side * 0.5: return None
        
        # 计算角度 (Qt 角度系统：0在3点钟，逆时针)
        angle = math.degrees(math.atan2(-(pos.y() - center.y()), pos.x() - center.x()))
        if angle < 0: angle += 360
        
        for cat, (start, span) in self._angles_cache.items():
            # 内部存储的是 Qt drawPie 系统的角度 (90=顶部, span<0=顺时针)
            real_start = (start / 16) % 360
            real_span = (span / 16)
            
            # 转换为 [0, 360] 逆时针等效
            if real_span < 0: # 顺时针
                a_end = real_start
                a_start = real_start + real_span
            else:
                a_start = real_start
                a_end = real_start + real_span
                
            # 处理跨0点情况
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
        
        start_angle = 90 * 16 # 从顶部开始
        self._angles_cache = {}
        
        # 绘制背景
        glow = QRadialGradient(QPointF(center), side/2)
        glow.setColorAt(1.0, QColor(255, 255, 255, 5))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(pie_rect.adjusted(-5, -5, 5, 5))

        # 绘制扇区
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

            grad = QConicalGradient(QPointF(center), 270)
            grad.setColorAt(0, color)
            grad.setColorAt(1, color.lighter(130))
            
            painter.setBrush(grad)
            painter.setPen(QPen(QColor(0, 0, 0, 150), 1))
            painter.drawPie(draw_rect, start_angle, span_angle)
            start_angle += span_angle

        # 圆环中心
        inner_side = side * 0.6
        inner_rect = QRect((rect.width()-inner_side)//2, (rect.height()-inner_side)//2, inner_side, inner_side)
        inner_grad = QLinearGradient(QPointF(inner_rect.topLeft()), QPointF(inner_rect.bottomRight()))
        inner_grad.setColorAt(0, QColor(30, 30, 35, 255))
        inner_grad.setColorAt(1, QColor(5, 5, 8, 255))
        painter.setBrush(inner_grad)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawEllipse(inner_rect)
        
        # 文字
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
        self.slider.setRange(0, 330) # 09:15 to 15:00 is approx 330 mins (ignoring noon gap for simplicity in slider)
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
        
        # 刻度层
        ticks_layout = QHBoxLayout()
        for t in ["09:25", "10:30", "11:30", "13:00", "14:00", "15:00"]:
            lbl = QLabel(t)
            lbl.setStyleSheet("color: #666; font-size: 10px;")
            ticks_layout.addWidget(lbl)
            if t != "15:00": ticks_layout.addStretch()
        layout.addLayout(ticks_layout)

    def _on_value_changed(self, val):
        # 转换为 HH:MM:SS
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
        
        # [NEW] 自适应独立启动模式：如果没有传入联动对象，则自主初始化
        if sender:
            self.sender = sender
        elif not main_app:
            try:
                from JohnsonUtil.stock_sender import StockSender
                # 默认开启 tdx 联动，不弹框提示
                self.sender = StockSender(tdx_var=True, ths_var=False, dfcf_var=False)
            except Exception as e:
                print(f"Standalone StockSender init failed: {e}")
                self.sender = None
        else:
            self.sender = None
            
        self._select_code = "" # 状态缓存，防抖
        
        self.setWindowTitle("🏁 竞价赛马与节奏监控")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("background-color: #000000; color: white;")
        
        self._last_data_version = -1
        self._is_rendering = False
        self._init_ui()
        
        # 加载窗口位置
        self.load_window_position_qt(self, "BiddingRacingRhythmPanel", default_width=1000, default_height=700)
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_visuals)
        self.refresh_timer.start(500)
        
        # 恢复表格布局状态
        QTimer.singleShot(200, self._restore_ui_state)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 1. 顶部时间轴
        self.timeline = RacingTimeline()
        main_layout.addWidget(self.timeline)
        
        # 2. 中间核心可视化层
        center_layout = QHBoxLayout()
        center_layout.setSpacing(20)
        
        # 左侧饼图
        self.pie_widget = RacingPieWidget()
        self.pie_widget.category_selected.connect(self._on_pie_filter)
        center_layout.addWidget(self.pie_widget, stretch=4)
        
        # 右侧个股排行
        rank_frame = QFrame()
        rank_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        rank_layout = QVBoxLayout(rank_frame)
        
        title_lbl = QLabel("🏆 当下领军个股 (Top 10)")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFD700; padding: 10px;")
        rank_layout.addWidget(title_lbl)
        
        self.stock_table = EnhancedTableWidget(0, 6)
        self.stock_table.setHorizontalHeaderLabels(["代码", "名称", "结构分", "涨跌", "起点", "DFF"])
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(80) 
        header.setMinimumSectionSize(30)
        self.stock_table.setColumnWidth(0, 65)
        self.stock_table.setColumnWidth(1, 75)
        
        # [THEME] 沉浸式暗黑主题：屏蔽刺眼的白条
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #333;
            }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; }
        """)
        
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stock_table.setSortingEnabled(True)
        header.sortIndicatorChanged.connect(lambda: self.stock_table.scrollToTop())
        
        # 绑定状态保存
        header.sectionResized.connect(self._save_ui_state)
        header.sortIndicatorChanged.connect(self._save_ui_state)
        
        rank_layout.addWidget(self.stock_table)
        
        center_layout.addWidget(rank_frame, stretch=6)
        
        main_layout.addLayout(center_layout, stretch=7)
        
        # 3. 底部板块热力
        bottom_frame = QFrame()
        bottom_frame.setFixedHeight(220)
        bottom_frame.setStyleSheet("background-color: #1C1C1E; border-radius: 12px;")
        bottom_lay = QVBoxLayout(bottom_frame)
        
        sec_title = QLabel("🔥 最强板块赛道")
        sec_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00FFCC; padding: 5px;")
        bottom_lay.addWidget(sec_title)
        
        self.sector_table = EnhancedTableWidget(0, 7)
        self.sector_table.setHorizontalHeaderLabels(["板块名称", "强度得分", "领涨龙头", "龙头涨幅", "起点涨幅", "龙头DFF", "联动详情"])
        s_header = self.sector_table.horizontalHeader()
        s_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        s_header.setMinimumSectionSize(30)
        s_header.setDefaultSectionSize(100)
        self.sector_table.setColumnWidth(0, 80)
        self.sector_table.setColumnWidth(2, 110)
        
        # [THEME] 沉浸式暗黑主题：深灰色隔行
        self.sector_table.setAlternatingRowColors(True)
        self.sector_table.setStyleSheet("""
            QTableWidget {
                background-color: #000000;
                alternate-background-color: #121214;
                gridline-color: #222;
                color: white;
                selection-background-color: #333;
            }
            QHeaderView::section { padding: 4px; background-color: #2C2C2E; font-size: 11px; }
        """)
        
        self.sector_table.setSortingEnabled(True)
        s_header.sortIndicatorChanged.connect(lambda: self.sector_table.scrollToTop())
        
        # 绑定状态保存
        s_header.sectionResized.connect(self._save_ui_state)
        s_header.sortIndicatorChanged.connect(self._save_ui_state)
        
        bottom_lay.addWidget(self.sector_table)
        
        main_layout.addWidget(bottom_frame, stretch=3)

        # 4. [NEW] 信号连接：双重联动 (MainWindow 可视化 + 通达信)
        self.stock_table.code_clicked.connect(self._on_stock_clicked)
        self.stock_table.code_double_clicked.connect(self._on_stock_double_clicked)
        
        self.sector_table.cellClicked.connect(self._on_sector_clicked)
        
        # 内部总线
        self._signal_bus = SignalBus()

    def closeEvent(self, event):
        """窗口关闭时保存位置并清理"""
        try:
            self._save_ui_state()
            self.save_window_position_qt_visual(self, "BiddingRacingRhythmPanel")
        except: pass
        self.closed.emit()
        super().closeEvent(event)

    def _save_ui_state(self):
        """[FIXED] 保存表格列宽与排序状态 (直接操作 JSON)"""
        try:
            from JohnsonUtil import commonTips as cct
            config_path = os.path.join(cct.get_base_path(), "bidding_racing_ui_state_v2.json")
            state = {
                "stock_header": self.stock_table.horizontalHeader().saveState().toHex().data().decode(),
                "sector_header": self.sector_table.horizontalHeader().saveState().toHex().data().decode()
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Save UI state failed: {e}")

    def _restore_ui_state(self):
        """[FIXED] 恢复表格列宽与排序状态 (直接操作 JSON)"""
        try:
            from JohnsonUtil import commonTips as cct
            from PyQt6.QtCore import QByteArray
            config_path = os.path.join(cct.get_base_path(), "bidding_racing_ui_state_v2.json")
            if not os.path.exists(config_path):
                self.stock_table.resizeColumnsToContents()
                self.sector_table.resizeColumnsToContents()
                return

            with open(config_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            if state.get("stock_header"):
                self.stock_table.horizontalHeader().restoreState(QByteArray.fromHex(state["stock_header"].encode()))
            else:
                self.stock_table.resizeColumnsToContents()
                
            if state.get("sector_header"):
                self.sector_table.horizontalHeader().restoreState(QByteArray.fromHex(state["sector_header"].encode()))
            else:
                self.sector_table.resizeColumnsToContents()
        except Exception as e:
            logger.debug(f"Restore UI state failed: {e}")
            self.stock_table.resizeColumnsToContents()
            self.sector_table.resizeColumnsToContents()

    def _on_pie_filter(self, category):
        """饼图点击过滤回调"""
        if category == "ALL":
            self.pie_widget.selected_category = None
        else:
            self.pie_widget.selected_category = category
        self.update_visuals() # 立即触发强制重绘

    def _on_stock_clicked(self, code, name):
        """左键/单击联动"""
        self._execute_linkage(code, name)

    def _on_stock_double_clicked(self, code, name):
        """双击联动：执行深度分发逻辑"""
        self._execute_linkage(code, name, source="racing_double_click")

    def _on_sector_clicked(self, row, col):
        """点击板块联动龙头"""
        item = self.sector_table.item(row, 2) # 龙头所在列 (已还原为名称(代码))
        if item:
            import re
            text = item.text()
            match = re.search(r'\((\d{6})\)', text)
            if match:
                code = match.group(1)
                name = text.split("(")[0].strip()
                self._execute_linkage(code, name, source="racing_sector_link")

    def _execute_linkage(self, code, name="", source="racing_panel"):
        """
        跨进程/跨组件联动核心逻辑
        借鉴自 TradingAnalyzerQt6: 通过 main 传递则优先使用 main 的调度队列
        """
        if not code or self._select_code == str(code):
            return
            
        # 🛡️ 记录当前选中，确保状态同步
        self._select_code = str(code)

        # 1. IPC 管道分发 (StockSender / Pipe)
        if self.sender:
            try:
                # 统一发送给 StockSender，它会自动处理 TDX/THS/DFCF 联动
                self.sender.send(str(code))
            except Exception:
                pass
        
        # 2. 主框架回调与线程安全派遣 (Tkinter GUI 兼容)
        if self.main_app and self.on_code_callback:
            try:
                if hasattr(self.main_app, 'tk_dispatch_queue'):
                    # 如果主程序支持可视化，则同步开启/跳图
                    if getattr(self.main_app, "_vis_enabled_cache", False):
                        if hasattr(self.main_app, 'open_visualizer'):
                            self.main_app.tk_dispatch_queue.put(lambda: self.main_app.open_visualizer(str(code)))
                    
                    # 执行回调
                    self.main_app.tk_dispatch_queue.put(lambda: self.on_code_callback(str(code)))
                else:
                    self.on_code_callback(str(code))
            except Exception:
                pass

        # 3. 内部 SignalBus 广播 (Standalone 模式或 QT 监控器联动)
        if hasattr(self, '_signal_bus'):
            try:
                self._signal_bus.publish("change_stock", {"code": code, "name": name, "source": source})
            except: pass

    def update_visuals(self):
        """
        高性能刷新逻辑：锁外处理 + 增量渲染
        """
        if not self.detector or self._is_rendering: return
        
        # [REFINED] 双重校验：数据版本 + 最后推送的时间戳
        curr_ver = getattr(self.detector, 'data_version', 0)
        curr_time = getattr(self.detector, 'last_update_time', "")
        
        if curr_ver == self._last_data_version and curr_time == getattr(self, "_last_rendered_time", ""):
            return
            
        self._is_rendering = True
        self._last_data_version = curr_ver
        self._last_rendered_time = curr_time
        try:
            # --- 1. [LOCK-ZONE] 极速数据快照 ---
            with self.detector._lock:
                # 仅在锁内进行最基础的字典/列表拷贝
                raw_ts_list = list(self.detector._tick_series.values())
                active_sectors = list(self.detector.active_sectors.values())
            
            # --- 2. [WORK-ZONE] 锁外分析计算 ---
            # 计算饼图分布
            active_ts = [ts for ts in raw_ts_list if ts.score > 0.5 or ts.current_pct != 0]
            dist = {"龙头": 0, "确核": 0, "跟涨": 0, "静默": 0}
            
            for ts in active_ts:
                is_leader = (ts.market_role == "主帅" or (ts.score > 60 and ts.first_breakout_ts > 0))
                is_confirmed = any(word in ts.pattern_hint for word in ["确认", "突破", "确核", "V反", "SBC"])
                if is_leader: dist["龙头"] += 1
                elif is_confirmed: dist["确核"] += 1
                elif ts.score > getattr(self.detector, 'score_threshold', 1.0): dist["跟涨"] += 1
                else: dist["静默"] += 1
            
            dist["静默"] += max(0, 50 - len(active_ts))
            
            # 计算个股排行
            raw_ts_list = [ts for ts in raw_ts_list if ts.now_price > 0]
            
            # [FILTER] 如果有饼图筛选，则过滤个股列表
            if self.pie_widget.selected_category:
                cat = self.pie_widget.selected_category
                if cat == "龙头":
                    raw_ts_list = [ts for ts in raw_ts_list if (ts.market_role == "主帅" or (ts.score > 60 and ts.first_breakout_ts > 0))]
                elif cat == "确核":
                    raw_ts_list = [ts for ts in raw_ts_list if any(word in ts.pattern_hint for word in ["确认", "突破", "确核", "V反", "SBC"])]
                elif cat == "跟涨":
                    raw_ts_list = [ts for ts in raw_ts_list if ts.score > getattr(self.detector, 'score_threshold', 1.0) and ts.score <= 60]
                elif cat == "静默":
                    raw_ts_list = [ts for ts in raw_ts_list if ts.score <= getattr(self.detector, 'score_threshold', 1.0)]

            sorted_ts = sorted(raw_ts_list, key=lambda x: x.score, reverse=True)[:10]
            
            # 计算板块排行
            sorted_sectors = sorted(active_sectors, key=lambda x: x.get('score', 0), reverse=True)[:5]

            # --- 3. [UI-ZONE] 增量渲染更新 ---
            self.pie_widget.set_data(dist)
            
            # [LOCK] 更新期间临时关闭排序，防止 Qt Item 冲突与闪烁
            self.stock_table.setSortingEnabled(False)
            self.sector_table.setSortingEnabled(False)
            
            try:
                self._update_table_optimized(self.stock_table, sorted_ts)
                self._update_sector_table_optimized(self.sector_table, sorted_sectors)
            finally:
                self.stock_table.setSortingEnabled(True)
                self.sector_table.setSortingEnabled(True)
            
            self._last_data_version = curr_ver
                
        except Exception as e:
            pass # 抑制渲染中的并发异常
        finally:
            self._is_rendering = False

    def _update_table_optimized(self, table, data_list):
        """行重用优化渲染：个股表 (对齐 6 列)"""
        # [ROBUSTNESS] 外部传入前已确保去重，这里直接渲染
        if table.rowCount() != len(data_list):
            table.setRowCount(len(data_list))
            
        for i, ts in enumerate(data_list):
            # 0. 代码
            code_text = ts.code
            if not table.item(i, 0) or table.item(i, 0).text() != code_text:
                table.setItem(i, 0, QTableWidgetItem(code_text))
            
            # 1. 名称
            name_text = ts.name
            if not table.item(i, 1) or table.item(i, 1).text() != name_text:
                table.setItem(i, 1, QTableWidgetItem(name_text))
                
            # 2. 结构分 (金色)
            score_val = round(ts.score, 1)
            score_txt = str(score_val)
            if not table.item(i, 2) or table.item(i, 2).text() != score_txt:
                it_score = NumericTableWidgetItem(score_txt)
                it_score.setForeground(QColor("#FFD700"))
                table.setItem(i, 2, it_score)
                
            # 3. 总涨跌
            pct_val = ts.current_pct
            pct_text = f"{pct_val:+.2f}%"
            if not table.item(i, 3) or table.item(i, 3).text() != pct_text:
                it_pct = NumericTableWidgetItem(pct_text)
                if pct_val > 0: it_pct.setForeground(QColor("#FF4444"))
                elif pct_val < 0: it_pct.setForeground(QColor("#44CC44"))
                table.setItem(i, 3, it_pct)

            # --- [CALC] 关键动能指标 ---
            # 优先级：pct_diff -> dff -> 0.0
            l_dff = getattr(ts, 'pct_diff', getattr(ts, 'dff', 0.0))
            l_start_pct = pct_val - l_dff

            # 4. 起点涨幅 (天蓝色)
            start_txt = f"{l_start_pct:+.2f}%"
            if not table.item(i, 4) or table.item(i, 4).text() != start_txt:
                it_start = NumericTableWidgetItem(start_txt)
                it_start.setForeground(QColor("#00CCFF"))
                table.setItem(i, 4, it_start)

            # 5. DFF (冲刺位 - 珊瑚红)
            dff_txt = f"{l_dff:+.2f}%"
            if not table.item(i, 5) or table.item(i, 5).text() != dff_txt:
                it_dff = NumericTableWidgetItem(dff_txt)
                it_dff.setForeground(QColor("#FF2D55"))
                table.setItem(i, 5, it_dff)

    def _update_sector_table_optimized(self, table, sectors):
        """行重用优化渲染：板块表 (对齐 7 列交互)"""
        if table.rowCount() != len(sectors):
            table.setRowCount(len(sectors))
            
        for i, sec in enumerate(sectors):
            # 0. 板块名称
            s_name = sec.get('sector', '未知')
            if not table.item(i, 0) or table.item(i, 0).text() != s_name:
                table.setItem(i, 0, QTableWidgetItem(s_name))
            
            # 1. 强度得分
            score = round(sec.get('score', 0), 1)
            score_txt = str(score)
            if not table.item(i, 1) or table.item(i, 1).text() != score_txt:
                it_score = NumericTableWidgetItem(score_txt)
                it_score.setForeground(QColor("#00FFCC"))
                table.setItem(i, 1, it_score)
                
            # 计算核心指标
            l_total_pct = sec.get('leader_pct', 0.0)
            l_dff = sec.get('leader_pct_diff', 0.0)
            l_start_pct = l_total_pct - l_dff

            # 2. 领涨龙头 (纯净模式修复联动)
            leader_display = f"{sec.get('leader_name')} ({sec.get('leader')})"
            if not table.item(i, 2) or table.item(i, 2).text() != leader_display:
                table.setItem(i, 2, QTableWidgetItem(leader_display))
                
            # 3. 龙头总涨幅
            l_pct_text = f"{l_total_pct:+.2f}%"
            if not table.item(i, 3) or table.item(i, 3).text() != l_pct_text:
                it_total = NumericTableWidgetItem(l_pct_text)
                if l_total_pct > 0: it_total.setForeground(QColor("#FF4444"))
                elif l_total_pct < 0: it_total.setForeground(QColor("#44CC44"))
                table.setItem(i, 3, it_total)

            # 4. 起点涨幅 (NEW 独立列)
            start_txt = f"{l_start_pct:+.2f}%"
            if not table.item(i, 4) or table.item(i, 4).text() != start_txt:
                it_start = NumericTableWidgetItem(start_txt)
                it_start.setForeground(QColor("#00CCFF")) # 天蓝色代表基准
                table.setItem(i, 4, it_start)

            # 5. 龙头DFF (冲刺力度)
            dff_txt = f"{l_dff:+.2f}%"
            if not table.item(i, 5) or table.item(i, 5).text() != dff_txt:
                it_dff = NumericTableWidgetItem(dff_txt)
                it_dff.setForeground(QColor("#FF2D55")) # 珊瑚红代表动能
                table.setItem(i, 5, it_dff)
                
            # 6. 联动详情
            followers = sec.get('followers', [])
            f_txt = ",".join([f"{f['name']}({f['pct']:+.1f}%)" for f in followers[:3]])
            if not table.item(i, 6) or table.item(i, 6).text() != f_txt:
                it_f = QTableWidgetItem(f_txt)
                it_f.setFont(QFont("Segoe UI", 9))
                table.setItem(i, 6, it_f)

if __name__ == "__main__":
    # Test stub
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = BiddingRacingRhythmPanel()
    window.show()
    sys.exit(app.exec())

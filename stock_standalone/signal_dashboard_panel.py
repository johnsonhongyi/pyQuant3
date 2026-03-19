# -*- coding: utf-8 -*-
"""
SignalDashboardPanel - 策略信号分类仪表盘
聚合实时信号，提供市场温度计、板块热力统计及分类过滤功能。
支持个股信号聚合、样式持久化与时间排序。
"""
import logging
from datetime import datetime
from typing import Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget,
    QFrame, QPushButton, QApplication, QDialog, QTextEdit, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QByteArray
from PyQt6.QtGui import QColor, QFont, QBrush

from tk_gui_modules.window_mixin import WindowMixin
from signal_bus import get_signal_bus, SignalBus, BusEvent
from JohnsonUtil import commonTips as cct

class VolumeDetailsDialog(QDialog):
    """持久化的放量详情弹窗"""
    code_clicked = pyqtSignal(str, str) # 信号联动 (代码, 名称)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔥 今日异动放量个股 (Top 30)")
        self.resize(450, 600)
        self.setMinimumWidth(380)
        self._is_updating = False # 更新标志
        
        # 窗口内置布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 头部说明
        header = QLabel("点击代码可联动查看分时图 (双击行亦可)")
        header.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(header)
        
        # 表格展示
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "涨幅%", "量比"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True) # ✅ 启用排序
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1a1a1a;
                color: #ddd;
                gridline-color: #333;
                border: none;
            }
            QHeaderView::section {
                background-color: #252525;
                color: #aaa;
                padding: 4px;
                border: 0.5px solid #333;
            }
            QTableWidget::item:selected {
                background-color: #333;
            }
        """)
        
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed) # ✅ 支持键盘上下键联动
        layout.addWidget(self.table)
        
        # 底部关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.hide) # 点击关闭只是隐藏
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
    def _on_item_clicked(self, item):
        if item:
            row = item.row()
            code = self.table.item(row, 0).text()
            name = self.table.item(row, 1).text()
            self.code_clicked.emit(code, name)
            
    def _on_selection_changed(self):
        """处理键盘上下键选择变化"""
        if self._is_updating: return
        items = self.table.selectedItems()
        if items:
            # 取得选中行的 Item
            row = items[0].row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                self.code_clicked.emit(code_item.text(), name_item.text())
            
    def update_data(self, details_list: List[dict]):
        """刷新数据内容"""
        self._is_updating = True
        self.table.setSortingEnabled(False) # 写入数据时关闭排序避免错位
        self.table.setRowCount(0)
        if not details_list: 
            self.table.setSortingEnabled(True)
            self._is_updating = False
            return
        
        self.table.setRowCount(len(details_list))
        for i, item in enumerate(details_list):
            code = item.get("code", "")
            name = item.get("name", "")
            change = item.get("change", 0.0)
            ratio = item.get("ratio", 0.0)
            
            # 代码 (亮色)
            c_item = QTableWidgetItem(code)
            c_item.setForeground(QBrush(QColor("#00ff00" if code.startswith(('60', '00')) else "#00bfff")))
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, c_item)
            
            # 名称
            n_item = QTableWidgetItem(name)
            n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, n_item)
            
            # 涨幅 (注意：NumericTableWidgetItem 会处理排序，展示带格式文字)
            ch_item = NumericTableWidgetItem(change)
            ch_item.setText(f"{change:+.2f}%")
            ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if change > 0: ch_item.setForeground(QBrush(QColor("#ff4444")))
            elif change < 0: ch_item.setForeground(QBrush(QColor("#44ff44")))
            self.table.setItem(i, 2, ch_item)
            
            # 量比 (亮黄)
            r_item = NumericTableWidgetItem(ratio)
            r_item.setText(f"{ratio:.2f}")
            r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            r_item.setForeground(QBrush(QColor("#ffff00")))
            self.table.setItem(i, 3, r_item)
            
        self.table.setSortingEnabled(True) # 恢复自适应排序
        self._is_updating = False

logger = logging.getLogger(__name__)

# 定义信号分类
CATEGORY_MAP = {
    "跟单信号": ["跟单", "FOLLOW", "enter_queue", "WATCHING", "VALIDATED", "就绪", "入场"],
    "突破加速": ["BREAKOUT_STAR", "Fast-Track", "momentum", "breakout", "strong_auction_open", "master_momentum", "high_sideways_break", "突破"],
    "卖点预警": ["SELL", "EXIT", "top_signal", "high_drop", "bull_trap_exit", "momentum_failure", "风险", "破位"],
    "结构破位": ["SBC-Breakdown", "跌破MA10", "跌破MA5", "结构派发", "破位", "momentum_failure"],
    "买入机会": ["BREAKOUT_STAR", "ma60反转启动", "BUY", "bottom_signal", "instant_pullback", "open_is_low", "low_open_high_walk", "open_is_low_volume", "nlow_is_low_volume", "low_open_breakout", "bear_trap_reversal", "early_momentum_buy"]
}

class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格项"""
    def __init__(self, value):
        if isinstance(value, (int, float)):
            super().__init__(str(value))
            self._value = value
        else:
            super().__init__(str(value))
            try:
                self._value = float(value)
            except (ValueError, TypeError):
                self._value = value

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            try:
                return self._value < other._value
            except (TypeError, ValueError):
                return super().__lt__(other)
        return super().__lt__(other)

class SignalDetailDialog(QDialog):
    """信号详情弹出框"""
    def __init__(self, code, name, pattern, detail, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"信号详情 - {code} {name}")
        self.setMinimumSize(500, 300)
        layout = QVBoxLayout(self)
        
        info_label = QLabel(f"<b>股票:</b> {code} {name} | <b>信号:</b> {pattern}")
        info_label.setStyleSheet("font-size: 11pt;")
        layout.addWidget(info_label)
        
        detail_edit = QTextEdit()
        detail_edit.setPlainText(detail)
        detail_edit.setReadOnly(True)
        detail_edit.setStyleSheet("background-color: #1a1c2c; color: #ffffff; font-family: 'Consolas'; font-size: 11pt;")
        layout.addWidget(detail_edit)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedHeight(35)
        layout.addWidget(close_btn)

class SignalDashboardPanel(QWidget, WindowMixin):
    """
    策略信号分类仪表盘
    """
    code_clicked = pyqtSignal(str, str)
    sig_bus_event = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 策略信号仪表盘")
        self.setMinimumSize(400, 300)
        
        # 数据缓存
        self._all_events: List[BusEvent] = []
        self._stock_stats: Dict[str, Dict] = {} 
        self._sector_heat: Dict[str, int] = {}  
        
        self._stats_counters = {
            "follow": 0, "breakout": 0, "risk": 0, "breakdown": 0, "bull": 0, "bear": 0
        }
        
        self._vol_dialog = VolumeDetailsDialog(self)
        # 异动个股窗口联动信号连接
        self._vol_dialog.code_clicked.connect(self._on_vol_code_clicked)
        
        self.setWindowFlags(Qt.WindowType.Window)
        self._event_buffer: List[BusEvent] = []
        self._is_updating_ui = False
        
        self._init_ui()
        self.load_window_position_qt(self, "signal_dashboard_panel", default_width=1100, default_height=750)
        self._restore_ui_state()
        self._setup_bus_connection()
        
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats_display)
        self._stats_timer.start(2000)
        
        self.sig_bus_event.connect(self._safe_process_event)
        
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._process_batch_signals)
        self._batch_timer.start(3000) 
        
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}

    def stop(self):
        if hasattr(self, '_stats_timer') and self._stats_timer: self._stats_timer.stop()
        if hasattr(self, '_batch_timer') and self._batch_timer: self._batch_timer.stop()
        if hasattr(self, '_search_timer') and self._search_timer: self._search_timer.stop()
        try:
            bus = get_signal_bus()
            bus.unsubscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_RISK, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
        except: pass
        self._event_buffer.clear()
        
    def closeEvent(self, event):
        self.save_window_position_qt_visual(self, "signal_dashboard_panel")
        self._save_ui_state()
        self.stop()
        event.accept()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        self.header = QFrame()
        self.header.setMinimumHeight(60)
        self.header.setStyleSheet("QFrame { background-color: #1a1c2c; border: 1px solid #333; border-radius: 6px; } QLabel { color: #ddd; }")
        header_layout = QHBoxLayout(self.header)
        
        temp_frame = QFrame()
        temp_frame.setStyleSheet("background: transparent; border: none;")
        temp_lay = QVBoxLayout(temp_frame)
        self.temp_label = QLabel("市场温度: --")
        self.temp_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.market_breadth_label = QLabel("📊 上涨:-- 下跌:--")
        self.vol_stat_label = QLabel("🚀 放量:--")
        self.vol_stat_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_stat_label.mousePressEvent = self._on_market_breadth_clicked 
        self.ls_ratio_label = QLabel("多空比: --")
        
        temp_lay.addWidget(self.temp_label)
        temp_lay.addWidget(self.market_breadth_label)
        temp_lay.addWidget(self.vol_stat_label)
        temp_lay.addWidget(self.ls_ratio_label)
        header_layout.addWidget(temp_frame)
        
        header_layout.addSpacing(30)
        self.cards = {}
        for key, name, color in [("follow", "跟单信号", "#FFD700"), ("breakout", "突破加速", "#FF4500"), ("risk", "风险卖出", "#00FA9A"), ("breakdown", "结构破位", "#87CEFA")]:
            card = QFrame()
            card.setMinimumWidth(60)
            card.setMaximumWidth(200)
            card.setStyleSheet(f"QFrame {{ border: 1px solid {color}44; border-radius: 8px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {color}11, stop:1 {color}22); }}")
            c_lay = QVBoxLayout(card)
            n_lbl = QLabel(name)
            n_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n_lbl.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: bold; border: none; background: transparent;")
            v_lbl = QLabel("0")
            v_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: #ffffff; border: none; background: transparent;")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(n_lbl)
            c_lay.addWidget(v_lbl)
            header_layout.addWidget(card)
            self.cards[key] = v_lbl
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda e, k=key: self._on_card_clicked(k)
            
        header_layout.addStretch()
        sector_frame = QFrame()
        sector_frame.setMinimumWidth(100)
        sector_frame.setMaximumWidth(350)
        sector_frame.setStyleSheet("background: transparent; border: none;")
        sector_lay = QVBoxLayout(sector_frame)
        h_lbl = QLabel("🔥 热门板块")
        h_lbl.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 10pt;")
        sector_lay.addWidget(h_lbl)
        self.hot_sectors_label = QLabel("等待数据...")
        self.hot_sectors_label.setWordWrap(True)
        self.hot_sectors_label.setStyleSheet("color: #00FFCC; font-family: 'Consolas'; font-size: 10pt; background: transparent;")
        self.hot_sectors_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hot_sectors_label.mousePressEvent = self._on_hot_sectors_clicked
        sector_lay.addWidget(self.hot_sectors_label)
        header_layout.addWidget(sector_frame)
        layout.addWidget(self.header)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; background: #0d121f; } QTabBar::tab { background: #1a1c2c; color: #888; padding: 8px 20px; border: 1px solid #333; } QTabBar::tab:selected { background: #2a2d42; color: #fff; border-bottom-color: #00ff88; }")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码/名称...")
        self.search_input.setFixedWidth(180)
        self.search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.customContextMenuRequested.connect(self._on_search_context_menu)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.tabs.setCornerWidget(self.search_input, Qt.Corner.TopRightCorner)
        self.tables: Dict[str, QTableWidget] = {}
        for tab_name in ["全部信号", "跟单信号", "突破加速", "卖点预警", "结构破位", "买入机会"]:
            table = self._create_signal_table()
            self.tables[tab_name] = table
            self.tabs.addTab(table, tab_name)
        self.tabs.currentChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
        layout.addWidget(self.tabs)
        self.status_bar = QLabel("就绪")
        layout.addWidget(self.status_bar)
        self.last_update_label = QLabel("--:--:--")
        layout.addWidget(self.last_update_label)

    def _create_signal_table(self) -> QTableWidget:
        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels(["时间", "评级", "代码", "名称", "形态/信号", "详情", "次数", "得分"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        return table

    def _setup_bus_connection(self):
        bus = get_signal_bus()
        bus.subscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_RISK, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
        history = bus.get_history(limit=200)
        for event in history: self._process_event(event, update_ui=False)
        self._refresh_all_tables()

    def _on_heartbeat_received(self, event: BusEvent):
        QTimer.singleShot(0, lambda: self._update_last_sync_time())
        if event.source == "market_stats" and isinstance(event.payload, dict):
            QTimer.singleShot(0, lambda: self.update_market_stats(event.payload))

    def _update_last_sync_time(self):
        self.last_update_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')} (实时)")

    def _on_signal_received(self, event: BusEvent):
        self.sig_bus_event.emit(event)

    def _safe_process_event(self, event: BusEvent):
        if isinstance(event, BusEvent): self._event_buffer.append(event)

    def _process_batch_signals(self):
        if not self._event_buffer: return
        MAX_PER_BATCH = 10
        events_to_process = self._event_buffer[:MAX_PER_BATCH]
        del self._event_buffer[:MAX_PER_BATCH]
        self._is_updating_ui = True
        try:
            for event in events_to_process: self._process_event(event, update_ui=self.isVisible())
            self._update_last_sync_time()
            self.status_bar.setText(f"就绪 | 统计采样: 最近 {len(self._all_events)} 条信号")
        except: pass
        finally: self._is_updating_ui = False

    def _categorize_and_count(self, event: BusEvent, increment: bool = True):
        delta = 1 if increment else -1
        payload = event.payload
        p = str(payload.get('pattern', payload.get('subtype', ''))).lower()
        d = str(payload.get('detail', payload.get('message', ''))).lower()
        if not hasattr(event, '_cached_cats'):
            cats = set()
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["突破加速"]): cats.add("breakout")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["卖点预警"]): cats.add("risk")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["结构破位"]): cats.add("breakdown")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["跟单信号"]): cats.add("follow")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["买入机会"]): cats.add("bull")
            event._cached_cats = cats
        for cat in event._cached_cats:
            if cat in self._stats_counters: self._stats_counters[cat] += delta
        if "breakout" in event._cached_cats: self._stats_counters["bull"] += delta
        if "risk" in event._cached_cats or "breakdown" in event._cached_cats: self._stats_counters["bear"] += delta

    def _process_event(self, event: BusEvent, update_ui=True):
        self._all_events.append(event)
        self._categorize_and_count(event, increment=True)
        if len(self._all_events) > 1000:
            self._categorize_and_count(self._all_events.pop(0), increment=False)
        payload = event.payload
        code = payload.get('code', '')
        if not (isinstance(code, str) and code.isdigit() and len(code) == 6): return
        sector = payload.get('sector', '其它')
        if sector: self._sector_heat[sector] = self._sector_heat.get(sector, 0) + 1
        if code not in self._stock_stats: self._stock_stats[code] = {"count": 0, "name": payload.get('name', '')}
        self._stock_stats[code]["count"] += 1
        if update_ui: self._append_to_tables(event)

    def _append_to_tables(self, event: BusEvent):
        payload = event.payload
        code, name = payload.get('code', ''), payload.get('name', '')
        pattern = payload.get('pattern', payload.get('subtype', 'ALERT'))
        detail = payload.get('detail', payload.get('message', ''))
        import pandas as pd
        score = payload.get('score', 0.0)
        if pd.isna(score) or score is None:
            score = 0.0
            
        grade = str(payload.get('grade', '') or '')
        time_str = event.timestamp.strftime("%H:%M:%S")
        count = self._stock_stats.get(code, {}).get("count", 1)
        self._insert_row(self.tables["全部信号"], time_str, code, name, pattern, detail, count, score, grade)
        for cat, patterns in CATEGORY_MAP.items():
            if any(p.lower() in pattern.lower() or p.lower() in detail.lower() for p in patterns):
                self._insert_row(self.tables[cat], time_str, code, name, pattern, detail, count, score, grade)

    def _get_item_color(self, pattern, detail):
        if "SELL" in pattern or "风险" in detail: return QColor("#00FF00")
        if "BUY" in pattern or "突破" in detail or any(kw in detail for kw in ["上涨", "反转", "抢筹"]): return QColor("#FF4444")
        if "跟单" in detail: return QColor("#FFD700")
        return QColor("#ffffff")

    def _insert_row(self, table, time_str, code, name, pattern, detail, count, score, grade=''):
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        try:
            existing_row = -1
            for r in range(min(50, table.rowCount())):
                item = table.item(r, 2)
                if item and item.text() == code:
                    existing_row = r
                    break
            if existing_row >= 0: table.removeRow(existing_row)
            table.insertRow(0)
            
            # 评级设色
            grade_item = QTableWidgetItem(grade)
            grade_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if grade == 'S': 
                grade_item.setForeground(QBrush(QColor("#FF1493")))
                f = grade_item.font(); f.setBold(True); grade_item.setFont(f)
            elif grade == 'A': 
                grade_item.setForeground(QBrush(QColor("#FF8C00")))
                f = grade_item.font(); f.setBold(True); grade_item.setFont(f)

            table.setItem(0, 0, QTableWidgetItem(time_str))
            table.setItem(0, 1, grade_item)
            table.setItem(0, 2, QTableWidgetItem(code))
            table.setItem(0, 3, QTableWidgetItem(name))
            table.setItem(0, 4, QTableWidgetItem(pattern))
            table.setItem(0, 5, QTableWidgetItem(detail))
            table.setItem(0, 6, NumericTableWidgetItem(str(count)))
            table.setItem(0, 7, NumericTableWidgetItem(str(int(score))))
            
            search_text = self.search_input.text().strip().lower()
            if search_text and not any(search_text in str(table.item(0, i).text()).lower() for i in [0, 2, 3, 4, 5] if table.item(0, i)):
                table.setRowHidden(0, True)
            color = self._get_item_color(pattern, detail)
            for i in [0, 2, 3, 4, 5, 6, 7]:
                it = table.item(0, i)
                if it: it.setForeground(color)
            self._flash_row(table, 0)
            if table.rowCount() > 500: table.removeRow(table.rowCount() - 1)
        finally: table.setSortingEnabled(was_sorting)

    def _flash_row(self, table, row):
        try:
            items = [table.item(row, i) for i in range(table.columnCount())]
            if not items or not items[0]: return
            for item in items:
                if item: item.setBackground(QBrush(QColor(255, 255, 0, 60)))
            
            def reset_bg():
                for it in items:
                    try:
                        if it: it.setBackground(QBrush(QColor(0, 0, 0, 0)))
                    except RuntimeError:
                        pass # Item was deleted from C++ side
            QTimer.singleShot(800, reset_bg)
        except: pass

    def _refresh_all_tables(self):
        for table in self.tables.values(): table.setRowCount(0)
        for event in self._all_events: self._append_to_tables(event)

    def _update_stats_display(self):
        total = len(self._all_events)
        if total == 0: return
        self.cards["follow"].setText(str(self._stats_counters["follow"]))
        self.cards["breakout"].setText(str(self._stats_counters["breakout"]))
        self.cards["risk"].setText(str(self._stats_counters["risk"]))
        self.cards["breakdown"].setText(str(self._stats_counters["breakdown"]))
        ratio = self._stats_counters["bull"] / max(1, self._stats_counters["bear"])
        self.ls_ratio_label.setText(f"多空比: {ratio:.2f}")
        temp = "冷清"
        if ratio > 2.0: temp = "活跃"
        if ratio > 5.0: temp = "狂热"
        if ratio < 0.5: temp = "低迷"
        self.temp_label.setText(f"市场温度: {temp} (采样{total})")
        sorted_sectors = sorted(self._sector_heat.items(), key=lambda x: x[1], reverse=True)
        top_3 = [f"{s}: {c}" for s, c in sorted_sectors[:3]]
        self.hot_sectors_label.setText(" | ".join(top_3) if top_3 else "暂无数据")

    def update_market_stats(self, stats: dict):
        try:
            self._market_stats.update(stats)
            if hasattr(self, '_vol_dialog') and self._vol_dialog.isVisible(): self._vol_dialog.update_data(stats.get("vol_details", []))
            self.market_breadth_label.setText(f"📊 上涨:{stats.get('up', 0)} 下跌:{stats.get('down', 0)}")
            self.vol_stat_label.setText(f"🚀 放量:{stats.get('vol_up', 0)}")
            self.last_update_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")
        except: pass

    def _on_card_clicked(self, key):
        mapping = {"follow": "全部信号", "breakout": "突破加速", "risk": "卖点预警", "breakdown": "结构破位"}
        tab_name = mapping.get(key)
        if tab_name:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    break

    def _on_market_breadth_clicked(self, event):
        self._vol_dialog.update_data(self._market_stats.get("vol_details", []))
        self._vol_dialog.show()

    def _on_vol_code_clicked(self, code, name):
        """处理异动放量窗口代码点击联动"""
        # 1. 触发仪表盘对外的主联动信号 (代码与名称)
        self.code_clicked.emit(code, name)
        # 2. 发送内部总线事件，以便总线相关组件也能同步
        self.sig_bus_event.emit(BusEvent(SignalBus.EVENT_PATTERN, datetime.now(), "VolDialog", {"code": code, "name": name}))

    def _on_hot_sectors_clicked(self, event):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        menu = QMenu(self)
        for s in self.hot_sectors_label.text().split(" | "):
            if ":" in s:
                name = s.split(":")[0].strip()
                action = QAction(f"查看 {name} 详情", self)
                action.triggered.connect(lambda checked, n=name: self._filter_by_sector(n))
                menu.addAction(action)
        menu.exec(self.hot_sectors_label.mapToGlobal(QPoint(0, 20)))

    def _filter_by_sector(self, sector_name):
        self.tabs.setCurrentIndex(0)
        self.status_bar.setText(f"当前筛选板块: {sector_name}")

    def _on_cell_clicked(self, row, col):
        table = self.sender()
        code_item, name_item = table.item(row, 2), table.item(row, 3)
        if code_item and name_item: self.code_clicked.emit(code_item.text(), name_item.text())

    # def _on_cell_double_clicked(self, row, col):
    #     table = self.sender()
    #     it_code, it_name = table.item(row, 1), table.item(row, 2)
    #     if not it_code or not it_name: return
    #     code, name = it_code.text().strip(), it_name.text().strip()
    #     clipboard = QApplication.clipboard()
    #     header = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
    #     if header == "代码": clipboard.setText(code)
    #     elif header == "名称": clipboard.setText(name)
    #     elif header in ("形态", "信号"): clipboard.setText(table.item(row, col).text())
    #     elif header == "详情":
    #         detail = table.item(row, col).text()
    #         # clipboard.setText(detail)
    #         SignalDetailDialog(code, name, table.item(row, 3).text(), detail, self).exec()
    #         return
    #     else: clipboard.setText(code)
    #     self.status_bar.setText(f"📋 已复制: {clipboard.text()}")
    #     self.code_clicked.emit(code, name)

    def _on_cell_double_clicked(self, row, col):
        table = self.sender()
        it_code = table.item(row, 2)
        it_name = table.item(row, 3)
        it_current = table.item(row, col)
        
        if not it_code or not it_name or not it_current: 
            return
            
        code = it_code.text().strip()
        name = it_name.text().strip()
        current_text = it_current.text().strip()
        
        clipboard = QApplication.clipboard()
        header = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""

        if header == "详情":
            # 仅弹窗，不执行复制逻辑
            # 假设第4列是日期或时间，对应你代码中的 table.item(row, 4)
            time_str = table.item(row, 4).text() if table.item(row, 4) else ""
            dialog = SignalDetailDialog(code, name, time_str, current_text, self)
            dialog.exec()
            # 如果弹窗时也要通知其他组件，可以在这里也 emit
            self.code_clicked.emit(code, name) 
            return 

        # --- 复制逻辑 ---
        if header == "代码":
            clipboard.setText(code)
        elif header == "名称":
            clipboard.setText(name)
        elif header in ("形态", "信号"):
            clipboard.setText(current_text)
        else:
            clipboard.setText(code)

        self.status_bar.setText(f"📋 已复制: {clipboard.text()}")
        self.code_clicked.emit(code, name)

    def _on_search_text_changed(self, text):
        if not hasattr(self, '_search_timer'):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._apply_filter)
        self._search_timer.start(200)

    def _apply_filter(self):
        search_text = self.search_input.text().strip().lower()
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget): return
        for row in range(table.rowCount()):
            match = any(search_text in str(table.item(row, i).text()).lower() for i in [0, 2, 3, 4, 5] if table.item(row, i))
            table.setRowHidden(row, not match)

    def _on_search_context_menu(self, pos):
        QTimer.singleShot(30, lambda: self.search_input.setText(QApplication.clipboard().text().strip()))

    def _on_selection_changed(self):
        if getattr(self, '_is_updating_ui', False): return
        table = self.sender()
        items = table.selectedItems()
        if items: self.code_clicked.emit(table.item(items[0].row(), 2).text(), table.item(items[0].row(), 3).text())

    def _save_ui_state(self):
        try:
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            state = self.tables["全部信号"].horizontalHeader().saveState().toHex().data().decode()
            import json, os
            path = self._get_config_file_path(WINDOW_CONFIG_FILE, self._get_dpi_scale_factor())
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: data = json.load(f)
            data["signal_dashboard_ui_state"] = {'header': state}
            with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def _restore_ui_state(self):
        try:
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            path = self._get_config_file_path(WINDOW_CONFIG_FILE, self._get_dpi_scale_factor())
            import json, os
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                state = data.get("signal_dashboard_ui_state", {}).get('header')
                if state:
                    val = QByteArray.fromHex(state.encode())
                    for t in self.tables.values(): t.horizontalHeader().restoreState(val)
        except: pass

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SignalDashboardPanel()
    window.show()
    sys.exit(app.exec())

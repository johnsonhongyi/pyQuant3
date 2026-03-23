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
    QFrame, QPushButton, QApplication, QDialog, QTextEdit, QLineEdit,
    QProgressBar, QGridLayout, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QByteArray
import threading
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
    "跟单信号": ["跟单", "FOLLOW", "enter_queue", "WATCHING", "VALIDATED", "就绪", "入场", "BREAKOUT_STAR", "起跳新星", "low_open_pinbar", "rising_structure", "Pinbar", "结构改善"],
    "突破加速": ["BREAKOUT_STAR", "Fast-Track", "momentum", "breakout", "strong_auction_open", "master_momentum", "high_sideways_break", "突破", "SBC-Breakout", "🚀强势结构", "🔥趋势加速", "跟单"],
    "卖点预警": ["SELL", "EXIT", "top_signal", "high_drop", "bull_trap_exit", "momentum_failure", "风险", "警告"],
    "结构破位": ["SBC-Breakdown", "跌破MA10", "跌破MA5", "结构派发", "破位", "momentum_failure", "⚠️结构破位"],
    "买入机会": ["BREAKOUT_STAR", "ma60反转启动", "BUY", "bottom_signal", "instant_pullback", "open_is_low", "low_open_high_walk", "open_is_low_volume", "nlow_is_low_volume", "low_open_breakout", "bear_trap_reversal", "early_momentum_buy"]
}

# 信号类型中文化与聚合映射
SIGNAL_TYPE_MAP = {
    "ALL": "全部信号",
    "Fast-Track": "极速跟单",
    "MOMENTUM": "强势动能",
    "SBC-Breakout": "结构突破",
    "SBC-Breakdown": "结构破位",
    "BREAKOUT_STAR": "起跳新星",
    "PATTERN": "形态异动",
    "ALERT": "预警信号"
}

SIGNAL_TYPE_KEYWORDS = {
    "Fast-Track": ["Fast-Track", "跟单", "Pinbar", "结构改善", "起跳新星"],
    "MOMENTUM": ["MOMENTUM", "超级动能", "动能", "加速"],
    "SBC-Breakout": ["SBC-Breakout", "突破", "强势结构", "趋势加速", "突破"],
    "SBC-Breakdown": ["SBC-Breakdown", "破位", "结构破位", "跌破", "风险", "破位"],
    "BREAKOUT_STAR": ["BREAKOUT_STAR", "起跳新星"],
    "PATTERN": ["PATTERN", "形态", "信号"],
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
        # --- 1. 数据结构初始化 ---
        self._all_events: List[BusEvent] = []
        self._stock_stats: Dict[str, Dict] = {} 
        self._sector_heat: Dict[str, int] = {}  
        self._stats_counters = {
            "follow": 0, "breakout": 0, "risk": 0, "breakdown": 0, "bull": 0, "bear": 0
        }
        self._signal_type_counts = {k: 0 for k in SIGNAL_TYPE_MAP.keys()}
        self._signal_type_counts["ALL"] = 0
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        self._is_updating_ui = False
        self._table_update_buffer: List[BusEvent] = [] # [NEW] UI 更新缓冲
        self._data_lock = threading.Lock() # ⭐ [NEW] 线程锁保护共享数据
        
        # --- 2. 组件与窗口初始化 ---
        self._vol_dialog = VolumeDetailsDialog(self)
        self._vol_dialog.code_clicked.connect(self._on_vol_code_clicked)
        self.setWindowFlags(Qt.WindowType.Window)
        
        # --- 3. UI 渲染 (依赖上述数据结构) ---
        self._init_ui()
        self.load_window_position_qt(self, "signal_dashboard_panel", default_width=1100, default_height=750)
        self._restore_ui_state()
        
        # --- 4. 定时器与总线连接 ---
        self._setup_bus_connection()
        # ⭐ [FIX] 显式指定 QueuedConnection，确保跨线程信号在 GUI 线程处理
        self.sig_bus_event.connect(self._safe_process_event, Qt.ConnectionType.QueuedConnection)
        
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats_display)
        self._stats_timer.start(2000)
        
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._process_batch_signals)
        self._batch_timer.start(3000)

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
        self._table_update_buffer.clear()
        
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
        
        # [NEW] 市场温度进度条
        self.temp_bar = QProgressBar()
        self.temp_bar.setRange(0, 100)
        self.temp_bar.setValue(50)
        self.temp_bar.setTextVisible(False)
        self.temp_bar.setFixedHeight(8)
        self.temp_bar.setMinimumWidth(120)
        self.temp_bar.setStyleSheet("""
            QProgressBar {
                background-color: #333;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5bc0de, stop:0.5 #f0ad4e, stop:1 #d9534f);
                border-radius: 4px;
            }
        """)
        temp_lay.addWidget(self.temp_bar)
        
        self.market_breadth_label = QLabel("📊 上涨:-- 下跌:--")
        self.vol_stat_label = QLabel("🚀 放量:--")
        self.vol_stat_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_stat_label.mousePressEvent = self._on_market_breadth_clicked 
        self.ls_ratio_label = QLabel("多空比: --")
        
        temp_lay.addWidget(self.market_breadth_label)
        temp_lay.addWidget(self.vol_stat_label)
        temp_lay.addWidget(self.ls_ratio_label)
        header_layout.addWidget(temp_frame)
        
        # [NEW] 增加点击联动详情
        temp_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        temp_frame.mousePressEvent = self._on_market_temp_clicked

        header_layout.addSpacing(20)
        
        # [NEW] 指数网格显示
        self.index_frame = QFrame()
        self.index_frame.setMinimumWidth(150)
        self.index_frame.setStyleSheet("background: #111; border: 0.5px solid #444; border-radius: 5px; padding: 2px;")
        idx_grid = QGridLayout(self.index_frame)
        idx_grid.setContentsMargins(5, 5, 5, 5)
        idx_grid.setSpacing(5)
        
        self.idx_labels = {}
        indices_list = [("sh000001", "上证"), ("sz399001", "深证"), ("sz399006", "创业"), ("sh000688", "科创")]
        for i, (code, name) in enumerate(indices_list):
            nl = QLabel(f"{name}")
            nl.setStyleSheet("color: #aaa; font-size: 9pt;")
            vl = QLabel("--%")
            vl.setStyleSheet("color: #ddd; font-family: 'Consolas'; font-size: 10pt; font-weight: bold;")
            idx_grid.addWidget(nl, i, 0)
            idx_grid.addWidget(vl, i, 1)
            self.idx_labels[name] = vl
            
        header_layout.addWidget(self.index_frame)
        
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
        self.search_input.setFixedWidth(150)
        self.search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.customContextMenuRequested.connect(self._on_search_context_menu)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        
        # [NEW] 信号类型下拉过滤
        self.type_filter = QComboBox()
        self.type_filter.setFixedWidth(130)
        self.type_filter.setStyleSheet("QComboBox { background: #1a1c2c; color: #fff; border: 1px solid #333; padding: 2px 5px; } QComboBox QAbstractItemView { background: #1a1c2c; color: #fff; selection-background-color: #2a2d42; }")
        self._refresh_type_filter_items()
        self.type_filter.currentTextChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
        
        # 搜索与过滤容器
        search_lay = QHBoxLayout()
        search_lay.setContentsMargins(5, 5, 5, 5)
        search_lay.addWidget(self.type_filter)
        search_lay.addWidget(self.search_input)
        
        # [NEW] 重置按钮
        self.reset_btn = QPushButton("♻️ 重置")
        self.reset_btn.setFixedWidth(70)
        self.reset_btn.setStyleSheet("QPushButton { background: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 3px; font-weight: bold; } QPushButton:hover { background: #444; color: #fff; border-color: #666; }")
        self.reset_btn.clicked.connect(self._reset_signals)
        search_lay.addWidget(self.reset_btn)
        
        # 组装右上角控制区域 (类型过滤 + 搜索 + 重置)
        corner_widget = QWidget()
        corner_lay = QHBoxLayout(corner_widget)
        corner_lay.setContentsMargins(0, 0, 10, 0)
        corner_lay.setSpacing(8)
        corner_lay.addWidget(self.type_filter)
        corner_lay.addWidget(self.search_input)
        corner_lay.addWidget(self.reset_btn)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        self.tables: Dict[str, QTableWidget] = {}
        for tab_name in ["全部信号", "跟单信号", "突破加速", "卖点预警", "结构破位", "买入机会"]:
            table = self._create_signal_table()
            self.tables[tab_name] = table
            self.tabs.addTab(table, tab_name)
        self.tabs.currentChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
        layout.addWidget(self.tabs)
        
        # --- 底部状态栏布局优化 ---
        self.status_container = QFrame()
        self.status_container.setStyleSheet("QFrame { background-color: #1a1c2c; border-top: 1px solid #333; } QLabel { color: #888; font-size: 9pt; }")
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(10, 2, 10, 2)
        status_layout.setSpacing(15)

        self.status_label = QLabel("就绪")
        self.last_update_label = QLabel("--:--:--")
        self.stats_info_label = QLabel("跟单: 0 | 突破: 0 | 风险: 0 | 破位: 0 | 全部: 0")
        self.stats_info_label.setStyleSheet("color: #00ff88; font-family: 'Consolas';")

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.last_update_label)
        status_layout.addStretch()
        status_layout.addWidget(self.stats_info_label)

        layout.addWidget(self.status_container)
        
    def _refresh_type_filter_items(self):
        """刷新下拉框项目（带计数）"""
        current_text = self.type_filter.currentText()
        # 提取分类名称 (不含括号)
        current_cat = current_text.split(' (')[0] if ' (' in current_text else current_text
        
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        for eng_key, ch_name in SIGNAL_TYPE_MAP.items():
            count = self._signal_type_counts.get(eng_key, 0)
            item_text = f"{ch_name} ({count})" if eng_key != "ALL" else f"{ch_name} ({self._signal_type_counts['ALL']})"
            self.type_filter.addItem(item_text, eng_key)
            if ch_name == current_cat:
                self.type_filter.setCurrentText(item_text)
        self.type_filter.blockSignals(False)

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

        # [NEW] 统计信号类型用于下拉框
        raw_type = str(payload.get('pattern', payload.get('subtype', 'ALERT')))
        matched_type = "ALERT"
        for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
            if any(kw.lower() in raw_type.lower() for kw in keywords):
                matched_type = eng_key
                break
        
        self._signal_type_counts[matched_type] = max(0, self._signal_type_counts.get(matched_type, 0) + delta)
        self._signal_type_counts["ALL"] = max(0, self._signal_type_counts["ALL"] + delta)
        
        # 实时触发下拉框更新 (节流)
        if increment: 
            QTimer.singleShot(100, self._refresh_type_filter_items)

    def _safe_process_event(self, event: BusEvent):
        """线程安全地接管总线事件，先更新内存统计，再将 UI 更新推入缓冲"""
        try:
            # 1. 立即更新内存统计与计数 (满足实时性)
            self._process_event(event, update_ui=False)
            
            # 2. 推入 UI 更新缓冲 (满足稳定性)
            with self._data_lock: # ⭐ [FIX] 使用锁保护缓冲区写入
                self._table_update_buffer.append(event)
            
            # 3. 如果是高优信号，缩短批次等待，尽快显示 (可选)
            # if event.payload.get('is_high_priority'): QTimer.singleShot(500, self._process_batch_signals)
        except Exception as e:
            logger.error(f"Error in _safe_process_event: {e}")

    def _process_batch_signals(self):
        """批量处理 UI 更新，确保滚动条稳定"""
        if not self._table_update_buffer:
            return
            
        with self._data_lock: # ⭐ [FIX] 使用锁保护缓冲区读取
            events_to_process = self._table_update_buffer[:]
            self._table_update_buffer.clear()
        
        # 记录当前各表格的滚动状态
        scroll_states = {}
        for name, table in self.tables.items():
            scroll_states[name] = {
                'value': table.verticalScrollBar().value(),
                'at_top': table.verticalScrollBar().value() == 0,
                'selected': [(r.topRow(), r.bottomRow()) for r in table.selectedRanges()]
            }
        
        # 批量插入
        self._is_updating_ui = True
        try:
            for event in events_to_process: # 按到达顺序插入到第0行，最终批次中最新的在最前
                self._append_to_tables(event)
        finally:
            self._is_updating_ui = False
            
        # 恢复/修正滚动位置
        for name, table in self.tables.items():
            state = scroll_states.get(name)
            if not state: continue
            
            # 如果之前不在顶部，向下偏移新插入的行数以保持视图静止
            if not state['at_top']:
                new_val = state['value'] + len(events_to_process)
                table.verticalScrollBar().setValue(new_val)
            
            # 恢复选择 (如有必要，这里简单回放，也可增加偏移量逻辑)
            # for (top, bottom) in state['selected']:
            #     table.setRangeSelected(QTableWidgetSelectionRange(top + len(events_to_process), ..., ...), True)

    def _process_event(self, event: BusEvent, update_ui=True):
        payload = event.payload
        code = payload.get('code', '')
        # 🛡️ [GUARD] 必须有有效的股票代码才处理，防止空信号进入列表
        if not (isinstance(code, str) and code.isdigit() and len(code) == 6): return
        
        self._all_events.append(event)
        self._categorize_and_count(event, increment=True)
        if len(self._all_events) > 1000:
            self._categorize_and_count(self._all_events.pop(0), increment=False)
        
        sector = payload.get('sector', '其它')
        with self._data_lock: # ⭐ [FIX] 使用锁保护统计数据更新
            if sector: self._sector_heat[sector] = self._sector_heat.get(sector, 0) + 1
            if code not in self._stock_stats: self._stock_stats[code] = {"count": 0, "name": payload.get('name', '')}
            self._stock_stats[code]["count"] += 1
        
        if update_ui: self._append_to_tables(event)

    def _append_to_tables(self, event: BusEvent):
        payload = event.payload
        code, name = payload.get('code', ''), payload.get('name', '')
        if not code or not name: return # 🛡️ 进一步兜底校验
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

    def _on_search_text_changed(self, text):
        search_text = text.lower()
        # 获取当前选中的原始类型 key (从 UserData 子午线)
        target_type_key = self.type_filter.currentData() or "ALL"
        
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget): return
        
        for r in range(table.rowCount()):
            row_visible = True
            
            # 1. 文本搜索 (代码/名称)
            if search_text:
                code_item = table.item(r, 2)
                name_item = table.item(r, 3)
                if code_item and name_item:
                    row_visible = (search_text in code_item.text().lower() or 
                                  search_text in name_item.text().lower())
            
            # 2. 类型过滤
            if row_visible and target_type_key != "ALL":
                pattern_item = table.item(r, 4)
                if pattern_item:
                    raw_pattern = str(pattern_item.data(Qt.ItemDataRole.UserRole) or pattern_item.text())
                    # [FIX] 使用关键词映射判定归属，解决中英文过滤不统一问题
                    keywords = SIGNAL_TYPE_KEYWORDS.get(target_type_key, [target_type_key])
                    row_visible = any(kw.lower() in raw_pattern.lower() for kw in keywords)
            
            table.setRowHidden(r, not row_visible)

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
            
            # 形态/信号 (中文化展示)
            display_pattern = pattern
            for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                if any(kw.lower() in pattern.lower() for kw in keywords):
                    display_pattern = SIGNAL_TYPE_MAP.get(eng_key, pattern)
                    break
            
            p_item = QTableWidgetItem(display_pattern)
            p_item.setData(Qt.ItemDataRole.UserRole, pattern) # 存储原始 pattern 用于过滤
            
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
            table.setItem(0, 4, p_item) # [FIX] 使用翻译后的项，且带原始数据用于过滤
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
        # [FIX] 不要因为没有信号就退出！市场温度和指数需要更新
        if total > 0:
            with self._data_lock: # ⭐ [FIX] 使用锁保护统计刷新
                self.cards["follow"].setText(str(self._stats_counters["follow"]))
                self.cards["breakout"].setText(str(self._stats_counters["breakout"]))
                self.cards["risk"].setText(str(self._stats_counters["risk"]))
                self.cards["breakdown"].setText(str(self._stats_counters["breakdown"]))
        
        
        # 优先使用从 monitor 传来的专业市场温度评分
        prof_temp = self._market_stats.get('temperature')
        if prof_temp is not None:
            temp_val = float(prof_temp)
            status = "冷清"
            if temp_val > 80: status = "火热"
            elif temp_val > 60: status = "活跃"
            elif temp_val > 40: status = "平淡"
            elif temp_val > 20: status = "低迷"
            else: status = "冰点"
            self.temp_label.setText(f"市场温度: {status} ({temp_val:.1f}°C)")
            summary = self._market_stats.get('summary', '')
            if summary:
                self.temp_label.setToolTip(summary)
                self.status_label.setText(f"🌡️ {summary}") # 同时在底部状态栏提示
            
            # 动态改色
            color = "#ddd"
            if temp_val > 80: color = "#ff4444" 
            elif temp_val > 60: color = "#ff8c00" 
            elif temp_val < 30: color = "#5bc0de" 
            self.temp_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            
            # 更新进度条
            if hasattr(self, 'temp_bar'):
                self.temp_bar.setValue(int(temp_val))
                # 调整进度条 chunk 颜色 (可选，目前使用渐变)
        else:
            # 降级使用信号比例计算 (修正以匹配专业风格)
            total_bull = self._stats_counters.get("bull", 0)
            total_bear = self._stats_counters.get("bear", 0)
            
            market_up = self._market_stats.get('up', 0)
            market_down = self._market_stats.get('down', 0)
            
            # [FIX] 优先使用全市场涨跌比，因为它更稳定且反映大盘真实深度
            if market_up + market_down > 100:
                ratio = market_up / max(1, market_down)
            elif total_bull + total_bear > 0:
                ratio = total_bull / max(1, total_bear)
            else:
                ratio = 0.5 # 默认对等
                
            self.ls_ratio_label.setText(f"多空比: {ratio:.2f}")
            
            temp_status = "冰点"
            color = "#5bc0de" # 蓝色
            if ratio > 1.5: 
                temp_status = "活跃"; color = "#ff8c00"
            elif ratio > 0.8: 
                temp_status = "平淡"; color = "#ddd"
            elif ratio > 0.3: 
                temp_status = "低迷"; color = "#6c757d"
                
            self.temp_label.setText(f"市场温度: {temp_status} (采样比例)")
            self.temp_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            if hasattr(self, 'temp_bar'): 
                self.temp_bar.setValue(min(100, int(ratio * 40)))

        # 更新指数网格 (独立于信号数)
        indices_data = self._market_stats.get('indices', [])
        if indices_data and hasattr(self, 'idx_labels'):
            for idx_info in indices_data:
                name = idx_info.get('name', '')
                pct = idx_info.get('percent', 0.0)
                # 寻找匹配的标签 (简单匹配即可)
                name_key = name.replace("指数", "")
                for label_key, label_widget in self.idx_labels.items():
                    if label_key in name_key or name_key in label_key:
                        color = "#ff4444" if pct > 0 else "#44ff44" if pct < 0 else "#aaa"
                        label_widget.setText(f"{pct:+.2f}%")
                        label_widget.setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 10pt; font-weight: bold;")
                        break

        sorted_sectors = sorted(self._sector_heat.items(), key=lambda x: x[1], reverse=True)
        top_3 = [f"{s}: {c}" for s, c in sorted_sectors[:3]]
        self.hot_sectors_label.setText(" | ".join(top_3) if top_3 else "暂无数据")
        
        # 更新底部统计信息
        follow = self._stats_counters.get("follow", 0)
        breakout = self._stats_counters.get("breakout", 0)
        risk = self._stats_counters.get("risk", 0)
        breakdown = self._stats_counters.get("breakdown", 0)
        total = self._signal_type_counts.get("ALL", 0)
        self.stats_info_label.setText(f"跟单: {follow} | 突破: {breakout} | 风险: {risk} | 破位: {breakdown} | 全部: {total}")

    def update_market_stats(self, stats: dict):
        try:
            # from PyQt6 import QtWidgets
            # app = QtWidgets.QApplication.instance()
            # if app: app.processEvents() # ⚡ [MINIMAL HEARTBEAT] 每次接收统计时驱动一次循环，确保 UI 活跃
            
            self._market_stats.update(stats)
            if hasattr(self, '_vol_dialog') and self._vol_dialog.isVisible(): self._vol_dialog.update_data(stats.get("vol_details", []))
            self.market_breadth_label.setText(f"📊 上涨:{stats.get('up', 0)} 下跌:{stats.get('down', 0)}")
            self.vol_stat_label.setText(f"🚀 放量:{stats.get('vol_up', 0)}")
            self.last_update_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")
            
            # [FIX] 显式触发全局统计刷新，确保温度计和指数网格即时更新
            self._update_stats_display()
        except Exception as e:
            logger.debug(f"Update market stats failed: {e}")

    def _on_card_clicked(self, key):
        mapping = {"follow": "跟单信号", "breakout": "突破加速", "risk": "卖点预警", "breakdown": "结构破位"}
        tab_name = mapping.get(key)
        if tab_name:
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    break

    def _on_market_breadth_clicked(self, event):
        self._vol_dialog.update_data(self._market_stats.get("vol_details", []))
        self._vol_dialog.show()

    def _on_market_temp_clicked(self, event):
        """点击温度计弹出专业复盘详情窗口"""
        try:
            # 通过主窗口弹出 MarketPulseViewer
            main_window = getattr(self, 'parent_app', None)
            if not main_window:
                # 尝试从 QApplication 查找
                for widget in QApplication.topLevelWidgets():
                    if hasattr(widget, 'open_market_pulse'):
                         main_window = widget
                         break
            
            if main_window and hasattr(main_window, 'open_market_pulse'):
                 # ✅ [FIX] 跨线程/环境调用安全：如果主窗口是 Tkinter，可能需要 dispatch
                 if hasattr(main_window, 'tk_dispatch_queue'):
                     main_window.tk_dispatch_queue.put(lambda: main_window.open_market_pulse())
                 else:
                     main_window.open_market_pulse()
            else:
                 # 备选：通知总线触发 (如果有相应监听)
                 bus = get_signal_bus()
                 bus.publish(SignalBus.EVENT_ALERT, "UI_ACTION", {"action": "open_market_pulse"})
        except Exception as e:
            logger.error(f"Failed to open MarketPulseViewer from dashboard: {e}")

    def _on_vol_code_clicked(self, code, name):
        """处理异动放量窗口代码点击联动"""
        # 1. 触发仪表盘对外的主联动信号 (代码与名称)
        self.code_clicked.emit(code, name)
        # 2. 发送内部总线事件，以便总线相关组件也能同步
        self.sig_bus_event.emit(BusEvent(SignalBus.EVENT_PATTERN, datetime.now(), "VolDialog", {"code": code, "name": name}))

    def _on_search_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu()
        clear_act = menu.addAction("清除内容")
        test_act = menu.addAction("🚀 发送并验证自检信号 (Fast-Track)")
        
        action = menu.exec(self.search_input.mapToGlobal(pos))
        if action == clear_act:
            self.search_input.clear()
        elif action == test_act:
            self._emit_test_signal()
            
    def _emit_test_signal(self):
        """[SELF-TEST] 发送一个模拟的 Fast-Track 信号用于自检"""
        try:
            from signal_bus import get_signal_bus, SignalBus
            bus = get_signal_bus()
            bus.publish(
                event_type=SignalBus.EVENT_ALERT,
                source="SelfTest",
                payload={
                    "code": "000001", "name": "自检样本", "action": "突破/跟单", 
                    "pattern": "Fast-Track", "detail": "这是一条自检测试信号，验证总线与看板连通性",
                    "score": 99.0, "grade": "S"
                }
            )
            self.status_label.setText("✅ 自检信号已发出，请检查 [极速跟单] 分类")
        except Exception as e:
            self.status_label.setText(f"❌ 自检失败: {e}")

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
        self.status_label.setText(f"当前筛选板块: {sector_name}")

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
        elif header in ("形态", "信号", "形态/信号", "评级", "次数", "得分", "时间"):
            clipboard.setText(current_text)
        else:
            clipboard.setText(code)

        self.status_label.setText(f"📋 已复制: {clipboard.text()}")
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

    def _reset_signals(self):
        """重置所有信号数据与统计，开始新监控周期"""
        # 1. 清空基础数据结构
        self._all_events.clear()
        self._table_update_buffer.clear()
        self._stock_stats.clear()
        self._sector_heat.clear()
        
        # 2. 重置计数器
        for k in self._stats_counters: self._stats_counters[k] = 0
        for k in self._signal_type_counts: self._signal_type_counts[k] = 0
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        
        # 3. 清空 UI 表格
        for table in self.tables.values():
            table.setRowCount(0)
            
        # 4. 重置 UI 标签与卡片 (进入“等待同步”状态)
        for key, lbl in self.cards.items():
            lbl.setText("0")
            
        self.temp_label.setText("市场温度: 等待数据...")
        self.temp_bar.setValue(0)
        self.market_breadth_label.setText("📊 上涨:-- 下跌:--")
        self.vol_stat_label.setText("🚀 放量:--")
        self.ls_ratio_label.setText("多空比: --")
        self.hot_sectors_label.setText("等待数据...")
        self.last_update_label.setText("最后更新: 等待同步...")
        self.stats_info_label.setText("跟单: 0 | 突破: 0 | 风险: 0 | 破位: 0 | 全部: 0")
        
        # 5. 刷新下拉框计数
        self._refresh_type_filter_items()
        self.status_label.setText("📊 信号面板已重置，等待新行情数据流入...")
        logger.info("SignalDashboard: User manual reset triggered.")

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SignalDashboardPanel()
    window.show()
    sys.exit(app.exec())

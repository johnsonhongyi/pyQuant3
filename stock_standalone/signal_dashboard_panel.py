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
import time
from PyQt6.QtGui import QColor, QFont, QBrush

from tk_gui_modules.window_mixin import WindowMixin
from signal_bus import get_signal_bus, SignalBus, BusEvent
from JohnsonUtil import commonTips as cct

# ✅ 盘中交易引擎（局部导入防止循环依赖）
def get_engine_controller():
    try:
        from sector_focus_engine import get_focus_controller
        return get_focus_controller()
    except Exception:
        return None

class VolumeDetailsDialog(QDialog, WindowMixin):
    """持久化的放量详情弹窗"""
    code_clicked = pyqtSignal(str, str) # 信号联动 (代码, 名称)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔥 今日异动放量个股 (Top 30)")
        self.setMinimumWidth(380)
        self._is_updating = False # 更新标志
        
        # 加载窗口位置与大小
        self.load_window_position_qt(self, "volume_details_dialog", default_width=450, default_height=600)
        
        # [NEW] 设置窗口标志：置顶及工具窗口样式 (工具窗口在 Windows 下有更窄的标题栏)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        
        # 窗口内置布局 (超窄边框配置)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # 头部说明 (精简版)
        header = QLabel("🔥 异动放量 | 双击行联动")
        header.setStyleSheet("color: #ffa500; font-size: 12px; padding-left: 5px; font-weight: bold;")
        layout.addWidget(header)
        
        # 表格展示
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "涨幅%", "量比"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26) # 行高微调 (适应 13px 文字)
        self.table.setSortingEnabled(True)
        
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        h_header.setFixedHeight(28) # 表头高度微调
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d121f;
                color: #ffffff;
                gridline-color: #2a2d42;
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
        """)
        
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)
        
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

    def closeEvent(self, event):
        """关闭事件时保存位置"""
        self.save_window_position_qt_visual(self, "volume_details_dialog")
        event.accept()

    def hideEvent(self, event):
        """隐藏事件时保存位置 (用于该 Dialog 频繁 hide/show 的场景)"""
        self.save_window_position_qt_visual(self, "volume_details_dialog")
        super().hideEvent(event)

logger = logging.getLogger(__name__)

# 定义信号分类
CATEGORY_MAP = {
    "跟单信号": ["跟单", "FOLLOW", "enter_queue", "WATCHING", "VALIDATED", "就绪", "入场", "BREAKOUT_STAR", "起跳新星", "low_open_pinbar", "rising_structure", "Pinbar", "结构改善", "赛马", "重点"],
    "突破加速": ["BREAKOUT_STAR", "Fast-Track", "momentum", "breakout", "strong_auction_open", "master_momentum", "high_sideways_break", "突破", "SBC-Breakout", "🚀强势结构", "🔥趋势加速", "跟单"],
    "买入机会": ["BREAKOUT_STAR", "ma60反转启动", "BUY", "bottom_signal", "instant_pullback", "open_is_low", "low_open_high_walk", "open_is_low_volume", "nlow_is_low_volume", "low_open_breakout", "bear_trap_reversal", "early_momentum_buy"],
    "卖点预警": ["SELL", "EXIT", "top_signal", "high_drop", "bull_trap_exit", "momentum_failure", "风险", "警告", "卖出", "止损", "平仓"],
    "结构破位": ["SBC-Breakdown", "跌破MA10", "跌破MA5", "结构派发", "破位", "momentum_failure", "⚠️结构破位"],
    "尾盘诱多": ["tail_end_trap", "尾盘诱多", "陷阱"],
    "其它信号": []
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
    "ALERT": "预警信号",
    "tail_end_trap": "尾盘诱多"
}

SIGNAL_TYPE_KEYWORDS = {
    "Fast-Track": ["Fast-Track", "跟单", "Pinbar", "结构改善", "起跳新星", "赛马"],
    "MOMENTUM": ["MOMENTUM", "超级动能", "动能", "加速"],
    "SBC-Breakout": ["SBC-Breakout", "突破", "强势结构", "趋势加速", "突破"],
    "SBC-Breakdown": ["SBC-Breakdown", "破位", "结构破位", "跌破", "风险", "破位"],
    "BREAKOUT_STAR": ["BREAKOUT_STAR", "起跳新星"],
    "PATTERN": ["PATTERN", "形态", "信号"],
    "tail_end_trap": ["tail_end_trap", "尾盘诱多"],
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
    sig_heartbeat = pyqtSignal(object) # [NEW] 专门用于心跳与统计更新的信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 策略信号仪表盘")
        self.setMinimumSize(400, 300)
        
        # 数据缓存
        # --- 1. 数据结构初始化 ---
        self._all_events: List[BusEvent] = []
        self._stock_stats: Dict[str, Dict] = {} 
        self._sector_heat: Dict[str, int] = {}  
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        self._signal_type_counts = {k: 0 for k in SIGNAL_TYPE_MAP.keys()}
        self._signal_type_counts["ALL"] = 0
        self._stats_counters = {"follow": 0, "breakout": 0, "risk": 0, "breakdown": 0, "bull": 0, "bear": 0, "other": 0}
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        self._is_updating_ui = False
        self._table_update_buffer: List[BusEvent] = [] # [NEW] UI 更新缓冲
        self._data_lock = threading.Lock() # ⭐ [NEW] 线程锁保护共享数据
        self._row_cache = {} # {table_obj: {code: table_item_at_col2}} 用于 O(1) 查找现有行
        
        # [NEW] 决策引擎相关
        self._decision_queue_data: List[dict] = []
        self._sector_focus_data: List[dict] = []
        self._engine_ctrl = None
        
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
        self.sig_heartbeat.connect(self._safe_process_heartbeat, Qt.ConnectionType.QueuedConnection)
        
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats_display)
        self._stats_timer.start(2000)
        
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._process_batch_signals)
        self._batch_timer.start(3000)

        # [NEW] 决策引擎同步定时器 (遵循系统 cct.duration_sleep_time)
        self._engine_sync_timer = QTimer(self)
        self._engine_sync_timer.timeout.connect(self._update_engine_views)
        # 获取系统配置的更新节奏，赋予默认 5s 兜底
        try:
            # 优先从 cct.CFG 获取，否则尝试从 cct 直接获取（取决于 JohnsonUtil 加载方式）
            interval_s = float(getattr(cct.CFG, 'duration_sleep_time', 30)) if hasattr(cct, 'CFG') else float(getattr(cct, 'duration_sleep_time', 30))
            interval_ms = max(10000, int(interval_s * 1000)) # 强制不低于 2s 以保证 UI 流畅
        except Exception:
            interval_ms = 10000
        self._engine_sync_timer.start(interval_ms)
        logger.info(f"🚀 SignalDashboard 决策引擎同步已启动，节拍: {interval_ms}ms")
        
        # [MOD] 状态栏轮播定时器与消息池
        self._carousel_idx = 0
        self._carousel_messages = []
        self._carousel_timer = QTimer(self)
        self._carousel_timer.timeout.connect(self._update_status_carousel)
        self._carousel_timer.start(10000) # 5秒切换一次消息

    def stop(self):
        """停止所有计时器和订阅，释放资源"""
        try:
            if hasattr(self, '_stats_timer') and self._stats_timer: 
                self._stats_timer.stop()
        except Exception: pass
        
        try:
            if hasattr(self, '_batch_timer') and self._batch_timer: 
                self._batch_timer.stop()
        except Exception: pass

        try:
            if hasattr(self, '_engine_sync_timer') and self._engine_sync_timer: 
                self._engine_sync_timer.stop()
        except Exception: pass
        
        try:
            if hasattr(self, '_search_timer') and self._search_timer: 
                self._search_timer.stop()
        except Exception: pass

        try:
            if hasattr(self, '_carousel_timer') and self._carousel_timer: 
                self._carousel_timer.stop()
        except Exception: pass
        
        try:
            bus = get_signal_bus()
            if bus:
                bus.unsubscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_RISK, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
        except Exception: pass
        
        if hasattr(self, '_table_update_buffer'):
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
        # [MOD] 增加 "dragon" 龙头池卡片，放在第一位
        card_configs = [
            ("dragon", "🐉 龙头池", "#FFD700"),
            ("follow", "跟单信号", "#FFD700"), 
            ("breakout", "突破加速", "#FF4500"), 
            ("trap", "尾盘诱多", "#1E90FF"),
            ("risk", "风险卖出", "#00FA9A"), 
            ("breakdown", "结构破位", "#87CEFA"), 
            ("other", "其它信号", "#A9A9A9")
        ]
        for key, name, color in card_configs:
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
        self.hot_sectors_label.setOpenExternalLinks(False)
        self.hot_sectors_label.linkActivated.connect(self._filter_by_sector)
        sector_lay.addWidget(self.hot_sectors_label)
        header_layout.addWidget(sector_frame)
        layout.addWidget(self.header)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; background: #0d121f; } QTabBar::tab { background: #1a1c2c; color: #888; padding: 4px 12px; font-size: 9pt; border: 1px solid #333; } QTabBar::tab:selected { background: #2a2d42; color: #fff; border-bottom-color: #00ff88; font-weight: bold; }")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码/名称...")
        self.search_input.setFixedWidth(150)
        self.search_input.setClearButtonEnabled(True) # 内置原生清空按钮
        self.search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.customContextMenuRequested.connect(self._on_search_context_menu)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        
        # [NEW] 信号类型下拉过滤
        self.type_filter = QComboBox()
        self.type_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents) # 自适应宽度
        self.type_filter.setStyleSheet("QComboBox { background: #1a1c2c; color: #fff; border: 1px solid #333; padding: 2px 10px 2px 5px; } QComboBox QAbstractItemView { background: #1a1c2c; color: #fff; selection-background-color: #2a2d42; }")
        self._refresh_type_filter_items()
        self.type_filter.currentTextChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
        
        # 搜索与过滤容器
        search_lay = QHBoxLayout()
        search_lay.setContentsMargins(5, 5, 5, 5)
        search_lay.addWidget(self.type_filter)
        search_lay.addWidget(self.search_input)
        
        # [MOD] 原清空按钮重构为：[🛠️ 引擎执行] (全链路逻辑触发)
        self.manual_run_btn = QPushButton("🛠️ 引擎执行")
        self.manual_run_btn.setFixedWidth(80)
        self.manual_run_btn.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff8c00, stop:1 #ff4500); 
                color: #fff; 
                border: 1px solid #ff4500; 
                border-radius: 4px; 
                padding: 3px; 
                font-size: 8.5pt; 
                font-weight: bold; 
            } 
            QPushButton:hover { background: #ff4500; border-color: #ff0000; }
            QPushButton:pressed { background: #cc3700; }
        """)
        self.manual_run_btn.clicked.connect(self._on_engine_manual_run)

        # [NEW] 重置按钮
        self.reset_btn = QPushButton("♻️ 重置")
        self.reset_btn.setFixedWidth(70)
        self.reset_btn.setStyleSheet("QPushButton { background: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 3px; font-weight: bold; } QPushButton:hover { background: #444; color: #fff; border-color: #666; }")
        self.reset_btn.clicked.connect(self._reset_signals)
        search_lay.addWidget(self.reset_btn)
        
        # 组装右上角控制区域 (类型过滤 + 搜索 + 清空 + 重置)
        corner_widget = QWidget()
        corner_lay = QHBoxLayout(corner_widget)
        corner_lay.setContentsMargins(0, 0, 10, 0)
        corner_lay.setSpacing(5)
        corner_lay.addWidget(self.type_filter)
        corner_lay.addWidget(self.search_input)
        corner_lay.addWidget(self.manual_run_btn)
        corner_lay.addWidget(self.reset_btn)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        self.tables: Dict[str, QTableWidget] = {}

        # [MOD] 新增页签：决策队列与板块热力、龙头追踪
        all_tabs = ["🌟 决策队列", "🐉 龙头追踪", "🔥 板块热力", "全部信号", "跟单信号", "突破加速", "尾盘诱多", "卖点预警", "结构破位", "买入机会", "其它信号"]
        for tab_name in all_tabs:
            if tab_name == "🌟 决策队列":
                table = self._create_decision_table()
            elif tab_name == "🐉 龙头追踪":
                table = self._create_dragon_table()
            elif tab_name == "🔥 板块热力":
                table = self._create_sector_table()
            else:
                table = self._create_signal_table()
            
            self.tables[tab_name] = table
            self.tabs.addTab(table, tab_name)
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        
        # --- 底部状态栏布局优化 ---
        self.status_container = QFrame()
        self.status_container.setStyleSheet("QFrame { background-color: #1a1c2c; border-top: 1px solid #333; } QLabel { color: #888; font-size: 9pt; }")
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(10, 2, 10, 2)
        status_layout.setSpacing(15)

        self.status_label = QLabel("就绪")
        # [NEW] 实时更新时间标签，修复 AttributeError
        self.last_update_label = QLabel("--:--:--")
        self.last_update_label.setStyleSheet("color: #666; font-family: 'Consolas';")
        
        self.stats_info_label = QLabel("跟单: 0 | 突破: 0 | 尾盘: 0 | 全部: 0")
        self.stats_info_label.setStyleSheet("color: #00ff88; font-family: 'Microsoft YaHei'; font-weight: bold;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.last_update_label) # 放置在中间或右侧
        status_layout.addWidget(self.stats_info_label)

        layout.addWidget(self.status_container)
        
    def _refresh_type_filter_items(self):
        """刷新下拉框项目（带计数）"""
        current_text = self.type_filter.currentText()
        # 提取分类名称 (不含括号)
        current_cat = current_text.split(' (')[0] if ' (' in current_text else current_text
        
        # [FIX] 下拉框中的数量统计，必须扫描实际可视表以保证所点即所得 (消除因多重覆写去重引发的 Phantom空项)
        table = getattr(self, "tables", {}).get("全部信号")
        counts = {k: 0 for k in SIGNAL_TYPE_MAP.keys()}
        if table is not None:
            counts["ALL"] = table.rowCount()
            for r in range(table.rowCount()):
                pattern_item = table.item(r, 4)
                if pattern_item:
                    raw_pattern = str(pattern_item.data(Qt.ItemDataRole.UserRole) or pattern_item.text())
                    matched_type = "ALERT"
                    for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                        if any(kw.lower() in raw_pattern.lower() for kw in keywords):
                            matched_type = eng_key
                            break
                    if matched_type in counts:
                        counts[matched_type] += 1
                    else:
                        counts[matched_type] = 1

        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        for eng_key, ch_name in SIGNAL_TYPE_MAP.items():
            count = counts.get(eng_key, 0)
            item_text = f"{ch_name} ({count})" if eng_key != "ALL" else f"{ch_name} ({counts['ALL']})"
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
        
        # [MOD] 设置默认按时间(第0列)倒序排列
        table.setSortingEnabled(True)
        table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder)
        
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch) # 详情自动拉伸
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        return table

    def _create_decision_table(self) -> QTableWidget:
        """创建决策队列表"""
        columns = ["时间", "优先级", "状态", "代码", "名称", "形态类别", "所属板块", "现价", "建议价", "周期涨变", "DFF动量", "捕捉理由"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder) # 默认按时间倒序
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 理由拉伸
        
        # [MOD] 统一单击与双击联动处理器
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        return table

    def _create_sector_table(self) -> QTableWidget:
        """创建板块热力表"""
        columns = ["板块名称", "热度", "竞分", "类型", "龙头", "龙头名称", "龙头涨幅", "跟涨%", "跟风明细", "更新时间"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 跟风明细拉伸
        
        # [MOD] 统一单击与双击联动处理器
        table.cellClicked.connect(self._on_sector_table_clicked)
        table.cellDoubleClicked.connect(self._on_sector_table_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        return table

    def _create_dragon_table(self) -> QTableWidget:
        """创建龙头追踪列表"""
        columns = ["状态", "代码", "名称", "所属板块", "现点%", "累计涨%", "追踪天", "新高天", "DFF动量", "VWAP", "更新时间", "标签"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSortIndicator(5, Qt.SortOrder.DescendingOrder) # 默认按累跌倒序
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 标签拉伸
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        return table

    def _on_sector_table_clicked(self, row, col):
        """板块表单击联动：同步龙头 K 线"""
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                t = header.text()
                if t == "龙头": code_col = i
                elif t == "龙头名称": name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it and c_it.text():
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

    def _on_sector_table_double_clicked(self, row, col):
        """板块表双击：寻找该行龙头并复制到剪贴板，随后发送联动"""
        table = self.tables.get("🔥 板块热力")
        if not table: return
        item = table.item(row, 4)
        name_item = table.item(row, 5)
        if item and item.text():
            code = item.text()
            name = name_item.text() if name_item else ""
            
            # [NEW] 双击复制功能
            header = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
            if header in ["龙头", "龙头名称"]:
                clipboard = QApplication.clipboard()
                clipboard.setText(code)
                self.status_label.setText(f"📋 龙头代码 {code} ({name}) 已复制")
                
            self.code_clicked.emit(code, name)

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
        """[BACKGROUND THREAD] 仅发射信号，不触碰任何 Qt 对象"""
        self.sig_heartbeat.emit(event)

    def _safe_process_heartbeat(self, event: BusEvent):
        """[GUI THREAD] 处理心跳和市场统计"""
        self._update_last_sync_time()
        if event.source == "market_stats" and isinstance(event.payload, dict):
            self.update_market_stats(event.payload)

    def _update_last_sync_time(self):
        self.last_update_label.setText(f"{datetime.now().strftime('%H:%M:%S')} (实时)")

    # --- [NEW] 决策引擎同步渲染逻辑 ---
    def _update_engine_views(self):
        """从 SectorFocusController 同步最新的决策与板块热力"""
        if self._engine_ctrl is None:
            self._engine_ctrl = get_engine_controller()
        
        if self._engine_ctrl is None:
            return

        # 1. 更新决策队列表
        try:
            decisions = self._engine_ctrl.get_decision_queue()
            self._refresh_decision_table(decisions)
        except Exception as e:
            logger.debug(f"Refresh decision table failed: {e}")

        # 2. 更新龙头追踪表 [NEW]
        try:
            dragons = self._engine_ctrl.get_dragon_leaders()
            self._refresh_dragon_table(dragons)
        except Exception as e:
            logger.debug(f"Refresh dragon table failed: {e}")

        # 3. 更新板块热力表
        try:
            sectors = self._engine_ctrl.get_hot_sectors(top_n=20)
            self._refresh_sector_table(sectors)
        except Exception as e:
            logger.debug(f"Refresh sector table failed: {e}")

    def _refresh_decision_table(self, decisions: List[dict]):
        table = self.tables.get("🌟 决策队列")
        if not table: return
        
        table.setSortingEnabled(False)
        # 获取当前选中的代码，用于恢复 (代码列移到了 index 3)
        current_selection = None
        sel_items = table.selectedItems()
        if sel_items: current_selection = table.item(sel_items[0].row(), 3).text()

        table.setRowCount(len(decisions))
        for i, d in enumerate(decisions):
            # ["时间", "优先级", "状态", "代码", "名称", "形态类别", "所属板块", "现价", "建议价", "周期涨变", "DFF动量", "捕捉理由"]
            table.setItem(i, 0, QTableWidgetItem(d.get('created_at', '')))
            
            prio = d.get('priority', 0)
            p_item = NumericTableWidgetItem(prio)
            if prio >= 75: p_item.setForeground(QBrush(QColor("#ff0000"))) # 极高优
            elif prio >= 60: p_item.setForeground(QBrush(QColor("#ffaa00"))) # 高优
            table.setItem(i, 1, p_item)

            st_item = QTableWidgetItem(d.get('status', '待处理'))
            if '成交' in st_item.text(): st_item.setForeground(QBrush(QColor("#00ff88")))
            table.setItem(i, 2, st_item)

            code = d.get('code', '')
            c_item = QTableWidgetItem(code)
            c_item.setForeground(QBrush(QColor("#ffff00" if code.startswith('30') else "#00ffff")))
            table.setItem(i, 3, c_item)

            table.setItem(i, 4, QTableWidgetItem(d.get('name', '')))
            table.setItem(i, 5, QTableWidgetItem(d.get('signal_type', '')))
            table.setItem(i, 6, QTableWidgetItem(d.get('sector', '')))
            
            table.setItem(i, 7, NumericTableWidgetItem(d.get('current_price', 0.0)))
            table.setItem(i, 8, NumericTableWidgetItem(d.get('suggest_price', 0.0)))
            
            pd_val = d.get('pct_diff', 0.0)
            pd_item = NumericTableWidgetItem(pd_val)
            pd_item.setText(f"{pd_val:+.2f}%")
            if pd_val > 0: pd_item.setForeground(QBrush(QColor("#ff4444")))
            elif pd_val < 0: pd_item.setForeground(QBrush(QColor("#44ff44")))
            table.setItem(i, 9, pd_item)

            table.setItem(i, 10, NumericTableWidgetItem(d.get('dff', 0.0)))
            
            reason = d.get('reason', '')
            r_item = QTableWidgetItem(reason)
            table.setItem(i, 11, r_item)

            # [Dragon] 龙头重点标记逻辑
            if '🐉' in reason:
                # 1. 突出颜色：深金黄色背景 (暗金)
                dragon_bg = QColor(100, 80, 0, 100) 
                for col in range(table.columnCount()):
                    it = table.item(i, col)
                    if it:
                        it.setBackground(QBrush(dragon_bg))
                        # 2. 核心信息加粗
                        if col in [3, 4]: # 代码与名称
                            f = it.font()
                            f.setBold(True)
                            it.setFont(f)
                            it.setForeground(QBrush(QColor("#FFD700"))) # 亮金色文字

        table.setSortingEnabled(True)
        # 恢复选中
        if current_selection:
            for r in range(table.rowCount()):
                if table.item(r, 3).text() == current_selection:
                    table.selectRow(r)

    def _refresh_dragon_table(self, dragons: List[dict]):
        """刷新龙头追踪表 [NEW]"""
        table = self.tables.get("🐉 龙头追踪")
        if not table: return
        
        table.setSortingEnabled(False)
        # 记录选中项代码 (代码在 index 1)
        current_selection = None
        sel_items = table.selectedItems()
        if sel_items: current_selection = table.item(sel_items[0].row(), 1).text()

        # 复用行逻辑
        if table.rowCount() != len(dragons):
            table.setRowCount(len(dragons))
            
        for i, d in enumerate(dragons):
            # ["状态", "代码", "名称", "所属板块", "现点%", "累计涨%", "追踪天", "新高天", "DFF动量", "VWAP", "更新时间", "标签"]
            
            # 0. 状态
            st_lbl = d.get('status_label', '')
            st_item = QTableWidgetItem(st_lbl)
            if '龙' in st_lbl: st_item.setForeground(QBrush(QColor("#FFD700"))) # 亮金
            elif '候' in st_lbl: st_item.setForeground(QBrush(QColor("#00FF00"))) # 嫩绿
            table.setItem(i, 0, st_item)

            # 1. 代码
            code = d.get('code', '')
            c_item = QTableWidgetItem(code)
            c_item.setForeground(QBrush(QColor("#ffff00" if code.startswith('30') else "#00ffff")))
            table.setItem(i, 1, c_item)

            # 2. 名称
            n_item = QTableWidgetItem(d.get('name', ''))
            if '龙' in st_lbl: 
                f = n_item.font()
                f.setBold(True)
                n_item.setFont(f)
            table.setItem(i, 2, n_item)

            # 3. 板块
            table.setItem(i, 3, QTableWidgetItem(d.get('sector', '')))

            # 4. 现点% (日内涨幅)
            c_pct = d.get('current_pct', 0.0)
            cp_item = NumericTableWidgetItem(c_pct)
            cp_item.setText(f"{c_pct:+.2f}%")
            if c_pct > 0: cp_item.setForeground(QBrush(QColor("#ff4444")))
            elif c_pct < 0: cp_item.setForeground(QBrush(QColor("#44ff44")))
            table.setItem(i, 4, cp_item)

            # 5. 累计涨% (从确认点至今)
            cum_pct = d.get('cum_pct', 0.0)
            cum_item = NumericTableWidgetItem(cum_pct)
            cum_item.setText(f"{cum_pct:+.2f}%")
            if cum_pct > 5: cum_item.setForeground(QBrush(QColor("#FFD700"))) # 大肉标金
            elif cum_pct > 0: cum_item.setForeground(QBrush(QColor("#ff4444")))
            table.setItem(i, 5, cum_item)

            # 6. 追踪天
            table.setItem(i, 6, NumericTableWidgetItem(d.get('tracked_days', 0)))

            # 7. 新高天
            nh_days = d.get('consecutive_new_highs', 0)
            nh_item = NumericTableWidgetItem(nh_days)
            if nh_days >= 3: nh_item.setForeground(QBrush(QColor("#ff4500"))) # 连续3日新高变橙红
            table.setItem(i, 7, nh_item)

            # 8. DFF动量
            dff = d.get('dff', 0.0)
            dff_item = NumericTableWidgetItem(dff)
            if dff > 0: dff_item.setForeground(QBrush(QColor("#00ff88")))
            table.setItem(i, 8, dff_item)

            # 9. VWAP
            table.setItem(i, 9, NumericTableWidgetItem(d.get('vwap', 0.0)))

            # 10. 更新时间
            up_time = d.get('last_update', '')
            if len(up_time) > 19: # ISO 格式处理
                up_time = up_time[11:19]
            table.setItem(i, 10, QTableWidgetItem(up_time))

            # 11. 标签
            table.setItem(i, 11, QTableWidgetItem(d.get('tags', '')))

        table.setSortingEnabled(True)
        # 恢复选中
        if current_selection:
            for r in range(table.rowCount()):
                if table.item(r, 1).text() == current_selection:
                    table.selectRow(r)
                    break

    def _refresh_sector_table(self, sectors: List[dict]):
        table = self.tables.get("🔥 板块热力")
        if not table: return
        
        table.setSortingEnabled(False)
        table.setRowCount(len(sectors))
        for i, s in enumerate(sectors):
            # ["板块名称", "热度", "竞分", "类型", "龙头", "龙头名称", "龙头涨幅", "跟涨%", "跟风明细"]
            table.setItem(i, 0, QTableWidgetItem(s.get('name', '')))
            
            heat = s.get('heat_score', 0.0)
            h_item = NumericTableWidgetItem(heat)
            if heat >= 40: h_item.setForeground(QBrush(QColor("#ff0000")))
            table.setItem(i, 1, h_item)

            table.setItem(i, 2, NumericTableWidgetItem(s.get('bidding_score', 0.0)))
            
            type_str = s.get('sector_type', '跟随')
            res_tag = s.get('resonance_tag', '')
            if res_tag:
                type_str = f"{type_str} | {res_tag}"
            
            type_item = QTableWidgetItem(type_str)
            if res_tag:
                type_item.setForeground(QBrush(QColor("#FF4500"))) # 橙红突出共振
                type_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                # 珊瑚红底色提示
                type_item.setBackground(QBrush(QColor(255, 69, 0, 40)))
            elif '强攻' in type_str:
                type_item.setForeground(QBrush(QColor("#ff4444")))
            elif '蓄势' in type_str:
                type_item.setForeground(QBrush(QColor("#ffaa00")))
            table.setItem(i, 3, type_item)

            table.setItem(i, 4, QTableWidgetItem(s.get('leader_code', '')))
            table.setItem(i, 5, QTableWidgetItem(s.get('leader_name', '')))
            
            l_pct = s.get('leader_change_pct', 0.0)
            lp_item = NumericTableWidgetItem(l_pct)
            lp_item.setText(f"{l_pct:+.2f}%")
            if l_pct > 0: lp_item.setForeground(QBrush(QColor("#ff4444")))
            table.setItem(i, 6, lp_item)

            table.setItem(i, 7, NumericTableWidgetItem(s.get('follow_ratio', 0.0)))
            table.setItem(i, 8, QTableWidgetItem(s.get('follower_detail', '')))
            table.setItem(i, 9, QTableWidgetItem(s.get('updated_at', '')))

        table.setSortingEnabled(True)

    def _on_signal_received(self, event: BusEvent):
        self.sig_bus_event.emit(event)


    def _categorize_and_count(self, event: BusEvent, increment: bool = True):
        delta = 1 if increment else -1
        payload = event.payload
        p = str(payload.get('pattern', payload.get('subtype', ''))).lower()
        d = str(payload.get('detail', payload.get('message', ''))).lower()
        if not hasattr(event, '_cached_cats'):
            cats = set()
            # [REVERTED] 恢复重叠多重标签: 一个复杂事件极可能是买点也符合破位结构，应被多重抓取展示
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["突破加速"]): cats.add("breakout")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["卖点预警"]): cats.add("risk")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["结构破位"]): cats.add("breakdown")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["跟单信号"]): cats.add("follow")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["买入机会"]): cats.add("bull")
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["尾盘诱多"]): cats.add("trap")
            if not cats: cats.add("other")
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
            events_raw = self._table_update_buffer[:]
            self._table_update_buffer.clear()
        
        if not events_raw: return

        # ⚡ [FIX] 移除此处的批次内按股票代码去重！
        # 如果同一个股票在3秒内同时触发"跟单"与"破位"，较早的跨分类信号若被去重丢弃，会导致某分类卡片统计增加了但表格中永远不出现该行的严重Bug。
        # 去重下放至 _insert_row 内部，针对每个子分类表格进行精准的独立覆盖更新。
        events_to_process = events_raw

        # 记录当前各表格的滚动状态
        scroll_states = {}
        for name, table in self.tables.items():
            # ⚡ [PERF] 批量禁用更新、信号和排序全家桶，提升性能
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            
            scroll_states[name] = {
                'value': table.verticalScrollBar().value(),
                'at_top': table.verticalScrollBar().value() == 0,
                'selected': [(r.topRow(), r.bottomRow()) for r in table.selectedRanges()],
                'sorting': table.isSortingEnabled() # 记录排序状态
            }
            # [FIX] 在大批量插入期间，必须全局禁用排序，否则在 setItem 时仍然有 O(N*logN) 的触发或者布局更新
            table.setSortingEnabled(False)
        
        # 批量插入
        self._is_updating_ui = True
        batch_start = time.perf_counter()
        processed_count = 0
            
        try:
            for event in events_to_process:
                self._append_to_tables(event)
                processed_count += 1
        finally:
            for name, table in self.tables.items():
                state = scroll_states.get(name)
                # 恢复排序
                if state and state.get('sorting'):
                    table.setSortingEnabled(True)
                    # 批量插入后，如果开了按时间倒排，主动执行一次
                    if table.horizontalHeader().sortIndicatorSection() == 0:
                        table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
                        
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                table.viewport().update()
                
            self._is_updating_ui = False
            batch_dur = (time.perf_counter() - batch_start) * 1000
            if batch_dur > 50:
                logger.debug(f"📊 [DASHBOARD_PERF] Batch processed {processed_count} signals in {batch_dur:.1f}ms (TotalReceived={len(events_raw)})")
            
        # 恢复/修正滚动位置
        for name, table in self.tables.items():
            state = scroll_states.get(name)
            if not state: continue
            
            # [MOD] 逻辑：
            # 1. 如果用户之前就在顶部(at_top=True)，则继续保持在顶部(0位置)，此时能看到最新冒出来的信号
            # 2. 如果用户之前正在往下翻看旧数据(at_top=False)，则向下偏移新插入的行数，以保持视窗内原来的内容不动
            if state['at_top']:
                table.verticalScrollBar().setValue(0)
            else:
                new_val = state['value'] + len(events_to_process)
                table.verticalScrollBar().setValue(new_val)

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

        append_start = time.perf_counter()
        pattern = payload.get('pattern', payload.get('subtype', 'ALERT'))
        detail = payload.get('detail', payload.get('message', ''))
        import pandas as pd
        score = payload.get('score', 0.0)
        if pd.isna(score) or score is None:
            score = 0.0
            
        grade = str(payload.get('grade', '') or '')
        time_str = event.timestamp.strftime("%H:%M:%S")
        count = self._stock_stats.get(code, {}).get("count", 1)
        
        # 1. 全部信号
        self._insert_row(self.tables["全部信号"], time_str, code, name, pattern, detail, count, score, grade, payload)
        
        # 2. 分类信号 
        matched_cats = 0
        for cat, patterns in CATEGORY_MAP.items():
            if any(p.lower() in pattern.lower() or p.lower() in detail.lower() for p in patterns):
                self._insert_row(self.tables[cat], time_str, code, name, pattern, detail, count, score, grade, payload)
                matched_cats += 1
        
        # 3. 未命中任何关键分类的归入其它
        if matched_cats == 0:
            self._insert_row(self.tables["其它信号"], time_str, code, name, pattern, detail, count, score, grade, payload)
        
        append_dur = (time.perf_counter() - append_start) * 1000
        if append_dur > 50:
            logger.debug(f"⚠️ [DASHBOARD_PERF] _append_to_tables cost {append_dur:.1f}ms for {code} (matches={matched_cats})")

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
        if "[重点]" in detail or "[重点]" in pattern: return QColor("#FFD700") # 亮金色
        if "SELL" in pattern or "风险" in detail: return QColor("#00FF00")
        if "BUY" in pattern or "突破" in detail or any(kw in detail for kw in ["上涨", "反转", "抢筹"]): return QColor("#FF4444")
        if "跟单" in detail: return QColor("#FFD700")
        return QColor("#ffffff")

    def _insert_row(self, table, time_str, code, name, pattern, detail, count, score, grade='', payload=None):
        insert_start = time.perf_counter()
        was_sorting = table.isSortingEnabled()
        if was_sorting:
            table.setSortingEnabled(False)
        try:
            # 🔍 [PERF] O(1) 查找现有行索引，取代 O(N) 循环扫描
            table_cache = self._row_cache.setdefault(table, {})
            existing_row = -1
            old_item = table_cache.get(code)
            if old_item:
                try:
                    existing_row = table.row(old_item)
                    if existing_row >= 0:
                        table.removeRow(existing_row)
                except (RuntimeError, Exception): 
                    pass # 可能 item 已失效
            
            table.insertRow(0)
            
            # 🛡️ [CAPPING] 限制表格总长度，放宽至1000，与历史总事件数匹配，防止过早丢弃导致上下数据不一
            max_rows = 1000
            if table.rowCount() > max_rows:
                # 清除将被移除行在缓存中的索引 (最后一行)
                rem_row = table.rowCount() - 1
                rem_item = table.item(rem_row, 2)
                if rem_item:
                    table_cache.pop(rem_item.text(), None)
                table.removeRow(rem_row)

            # 形态/信号 (中文化展示)
            display_pattern = pattern
            for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                if any(kw.lower() in pattern.lower() for kw in keywords):
                    display_pattern = SIGNAL_TYPE_MAP.get(eng_key, pattern)
                    break
            
            p_item = QTableWidgetItem(display_pattern)
            p_item.setData(Qt.ItemDataRole.UserRole, pattern)
            
            grade_item = QTableWidgetItem(grade)
            grade_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if grade in ['S', 'A']:
                grade_item.setForeground(QBrush(QColor("#FF1493" if grade=='S' else "#FF8C00")))
                f = grade_item.font(); f.setBold(True); grade_item.setFont(f)

            # 核心列 (存入缓存)
            code_item = QTableWidgetItem(code)
            table_cache[code] = code_item

            name_item = QTableWidgetItem(name)
            if payload:
                name_item.setData(Qt.ItemDataRole.UserRole, payload.get('sector', ''))

            table.setItem(0, 0, QTableWidgetItem(time_str))
            table.setItem(0, 1, grade_item)
            table.setItem(0, 2, code_item)
            table.setItem(0, 3, name_item)
            table.setItem(0, 4, p_item) 
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
            
            # [NEW] 重点信号行高亮 (赛马模式深度加成)
            if "[重点]" in detail or "[重点]" in pattern:
                # 使用深珊瑚红背景色突出重点，带透明度
                highlight_bg = QColor(255, 127, 80, 50) 
                for i in range(table.columnCount()):
                    it = table.item(0, i)
                    if it: 
                        it.setBackground(QBrush(highlight_bg))
                        # 名称和代码加粗显示
                        if i in [2, 3]:
                            f = it.font(); f.setBold(True); it.setFont(f)

            self._flash_row(table, 0)
            
            self._flash_row(table, 0)
            
            # [FIX] 不要在这里执行 sortByColumn，这会导致每一行插入都重排一次
            # 如果是批量插入，排序会在 _process_batch_signals 恢复时进行一次全局排序
                
        finally: 
            if was_sorting:
                table.setSortingEnabled(True)
            insert_dur = (time.perf_counter() - insert_start) * 1000
            if insert_dur > 20:
                 logger.debug(f"⚠️ [DASHBOARD_PERF] _insert_row cost {insert_dur:.1f}ms for {name}({code})")

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
        start_t = time.perf_counter()
        
        # ⚡ [PERF] 批量刷新时禁用更新与排序
        active_sortings = {}
        for name, table in self.tables.items():
            active_sortings[name] = table.isSortingEnabled()
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            table.setSortingEnabled(False)
            table.setRowCount(0)
            
        try:
            for event in self._all_events: 
                self._append_to_tables(event)
        finally:
            for name, table in self.tables.items():
                was_sorting = active_sortings.get(name, True)
                table.setSortingEnabled(was_sorting)
                # 恢复排序
                if was_sorting and table.horizontalHeader().sortIndicatorSection() == 0:
                    table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
                    
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                table.viewport().update()
                
        dur = (time.perf_counter() - start_t) * 1000
        logger.debug(f"🔄 [DASHBOARD_PERF] Full refresh cost {dur:.1f}ms for {len(self._all_events)} events")

    def _update_stats_display(self):
        total = len(self._all_events)
        
        # [FIX] 提前获取市场统计，确保无论是否有信号，后续逻辑都能安全访问
        market_up = self._market_stats.get('up', 0)
        market_down = self._market_stats.get('down', 0)
        prof_temp = self._market_stats.get('temperature')

        # [FIX] 不要因为没有信号就退出！市场温度和指数需要更新
        if total > 0:
            with self._data_lock: # ⭐ [FIX] 使用锁保护统计刷新
                # [REVERTED] 顶部卡片展示底层总触发的累计次数 (包含同一只股票的历史重复触发)，不改变既有去重策略
                self.cards["follow"].setText(str(self._stats_counters["follow"]))
                self.cards["breakout"].setText(str(self._stats_counters["breakout"]))
                self.cards["risk"].setText(str(self._stats_counters["risk"]))
                self.cards["breakdown"].setText(str(self._stats_counters["breakdown"]))
                self.cards["trap"].setText(str(self._stats_counters.get("trap", 0)))
                self.cards["other"].setText(str(self._stats_counters.get("other", 0)))
                
                # [Dragon] 更新龙头统计
                if self._engine_ctrl:
                    d_counts = self._engine_ctrl.get_dragon_count()
                    d_total = d_counts.get('dragon', 0)
                    c_total = d_counts.get('candidate', 0)
                    self.cards["dragon"].setText(str(d_total + c_total))
                    
                    # [MOD] 准备轮播消息池 (在这里更新变量，UI由定时器切换显示)
                    self._carousel_messages = [
                        f"🕒 同步: {datetime.now().strftime('%H:%M:%S')} | 下次扫描: {self._get_next_scan_time()} |🐉: 真龙 {d_total} | 候选 {c_total}",
                        f"🔥 市场信号: F:{self._stats_counters['follow']} | B:{self._stats_counters['breakout']} | T:{self._stats_counters.get('trap', 0)} | R:{self._stats_counters['risk']} | S:{self._stats_counters['breakdown']}",
                        f"🌡️ 盘中概况: 涨 {market_up} | 跌 {market_down} | 均温 {prof_temp if prof_temp else 'N/A'}℃"
                    ]
                    
                    # [MOD] 动态获取各 Tab 行数用于状态栏展示
                    counts_parts = []
                    tab_to_count = ["🌟 决策队列", "全部信号", "跟单信号", "突破加速", "尾盘诱多", "买入机会", "卖点预警", "结构破位"]
                    for t_name in tab_to_count:
                        tbl = self.tables.get(t_name)
                        if tbl:
                            # 简写映射
                            short_name = t_name.replace("信号", "").replace("🌟 ", "").replace("🔥 ", "").replace("🐉 ", "")
                            counts_parts.append(f"{short_name}: {tbl.rowCount()}")
                    
                    self.stats_info_label.setText(" | ".join(counts_parts))
        
        
        # 1. 通用计算多空比
        total_bull = self._stats_counters.get("bull", 0)
        total_bear = self._stats_counters.get("bear", 0)
        
        # 优先使用全市场涨跌比，因为它更稳定且反映大盘真实深度
        if market_up + market_down > 100:
            ratio = market_up / max(1, market_down)
        elif total_bull + total_bear > 0:
            ratio = total_bull / max(1, total_bear)
        else:
            ratio = 0.0 # 默认修正为0更符合逻辑
            
        # 2. 优先使用从 monitor 传来的专业市场温度评分
        if prof_temp is not None:
            temp_val = float(prof_temp)
            status = "冷清"
            if temp_val > 80: status = "火热"
            elif temp_val > 60: status = "活跃"
            elif temp_val > 40: status = "平淡"
            elif temp_val > 20: status = "低迷"
            else: status = "冰点"
            
            self.temp_label.setText(f"市场温度: {status} ({temp_val:.1f}°C)")
            self.ls_ratio_label.setText(f"多空比: {ratio:.2f}")
            
            summary = self._market_stats.get('summary', '')
            if summary:
                self.temp_label.setToolTip(summary)
                # [MOD] 状态栏左侧显示温度与更新时间
                self.status_label.setText(f"🌡️ {status} ({temp_val:.1f}°C) | 🕒 同步: {datetime.now().strftime('%H:%M:%S')}")
            
            # 动态改色
            color = "#ddd"
            if temp_val > 80: color = "#ff4444" 
            elif temp_val > 60: color = "#ff8c00" 
            elif temp_val < 30: color = "#5bc0de" 
            self.temp_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            
            if hasattr(self, 'temp_bar'):
                self.temp_bar.setValue(int(temp_val))
        else:
            # 3. 降级使用信号比例计算 (修正以匹配专业风格)
            temp_status = "冰点"
            color = "#5bc0de" # 蓝色
            if ratio > 1.5: 
                temp_status = "活跃"; color = "#ff8c00"
            elif ratio > 0.8: 
                temp_status = "平淡"; color = "#ddd"
            elif ratio > 0.3: 
                temp_status = "低迷"; color = "#6c757d"
                
            self.temp_label.setText(f"市场温度: {temp_status}")
            self.ls_ratio_label.setText(f"多空比: {ratio:.2f} (采样比例)")
            
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
        top_3 = []
        for s, c in sorted_sectors[:3]:
            if s == "其它":
                top_3.append(f'<a href="全部" style="color: #00FFCC; text-decoration: none;">全部: {c}</a>')
            else:
                top_3.append(f'<a href="{s}" style="color: #00FFCC; text-decoration: none;">{s}: {c}</a>')
        self.hot_sectors_label.setText(" | ".join(top_3) if top_3 else "暂无数据")
        self.hot_sectors_label.setTextFormat(Qt.TextFormat.RichText)
        
        # 更新底部统计信息 - 用于对比校验真实显示的表格行数结构
        follow_cnt = self.tables["跟单信号"].rowCount() if "跟单信号" in self.tables else 0
        breakout_cnt = self.tables["突破加速"].rowCount() if "突破加速" in self.tables else 0
        risk_cnt = self.tables["卖点预警"].rowCount() if "卖点预警" in self.tables else 0
        breakdown_cnt = self.tables["结构破位"].rowCount() if "结构破位" in self.tables else 0
        other_cnt = self.tables["其它信号"].rowCount() if "其它信号" in self.tables else 0
        total_cnt = self.tables["全部信号"].rowCount() if "全部信号" in self.tables else 0
        
        # [FIX] 使用清晰文案说明卡片展示的是历史信号流总数，而底部展示的是去重排版后的界面数据，消除数据理解误区。
        self.stats_info_label.setText(f"跟单:{follow_cnt} 突破:{breakout_cnt} 风险:{risk_cnt} 破位:{breakdown_cnt} | 总表可视数: {total_cnt}")

    def update_market_stats(self, stats: dict):
        try:
            # from PyQt6 import QtWidgets
            # app = QtWidgets.QApplication.instance()
            # if app: app.processEvents() # ⚡ [MINIMAL HEARTBEAT] 每次接收统计时驱动一次循环，确保 UI 活跃
            
            self._market_stats.update(stats)
            if hasattr(self, '_vol_dialog') and self._vol_dialog.isVisible(): self._vol_dialog.update_data(stats.get("vol_details", []))
            self.market_breadth_label.setText(f"📊 上涨:{stats.get('up', 0)} 下跌:{stats.get('down', 0)}")
            self.vol_stat_label.setText(f"🚀 放量:{stats.get('vol_up', 0)}")
            
            # [FIX] 显式触发全局统计刷新，确保温度计和指数网格即时更新
            self._update_stats_display()
        except Exception as e:
            logger.debug(f"Update market stats failed: {e}")

    def _on_card_clicked(self, key):
        mapping = {
            "dragon": "🐉 龙头追踪",
            "follow": "跟单信号", 
            "breakout": "突破加速", 
            "trap": "尾盘诱多",
            "risk": "卖点预警", 
            "breakdown": "结构破位", 
            "other": "其它信号"
        }
        tab_name = mapping.get(key)
        if tab_name:
            # [FIX] 点击顶部卡片时，不仅重置下拉列表，还要清空搜索框，彻底消除交叉过滤限制
            if hasattr(self, 'type_filter') and self.type_filter.currentData() != "ALL":
                idx = self.type_filter.findData("ALL")
                if idx >= 0:
                    self.type_filter.setCurrentIndex(idx)
                    
            if hasattr(self, 'search_input') and self.search_input.text():
                    self.search_input.clear()
                    
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    break

    def _on_market_breadth_clicked(self, event):
        self._vol_dialog.update_data(self._market_stats.get("vol_details", []))
        self._vol_dialog.show()

    def _on_market_temp_clicked(self, event):
        """点击温度计弹出专业复盘详情窗口 - 异步稳定版"""
        try:
            # 1. 发布到总线作为日志/追踪 (不使用 return，因为主程序暂无监听器，仅作解耦记录)
            bus = get_signal_bus()
            if bus:
                bus.publish(SignalBus.EVENT_ALERT, "UI_ACTION", {"action": "open_market_pulse"})
                logger.info("📡 [UI] MarketPulse opening request published via SignalBus")

            # 2. 寻找主窗口并进行安全分发 (这是目前最可靠的跨框架打开方式)
            main_window = getattr(self, 'parent_app', None)
            if not main_window:
                for widget in QApplication.topLevelWidgets():
                    if hasattr(widget, 'open_market_pulse'):
                        main_window = widget
                        break
            
            if main_window:
                # ✅ [关键适配] 使用 tk_dispatch_queue 确保在 Tkinter 主线程执行，彻底规避 GIL 锁问题
                if hasattr(main_window, 'tk_dispatch_queue') and main_window.tk_dispatch_queue:
                    # 优先级最高：如果主程序提供了专门的 Tk 任务调度队列
                    main_window.tk_dispatch_queue.put(lambda: main_window.open_market_pulse())
                elif hasattr(main_window, 'after'):
                    # 备选：如果主程序是 Tkinter 对象但没有扩展队列
                    main_window.after(10, lambda: main_window.open_market_pulse())
                else:
                    # 纯 Qt 或其它环境：通过 QTimer 异步触发，避免当前调用栈冲突
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(10, lambda: main_window.open_market_pulse())
            else:
                logger.warning("⚠️ [UI] Failed to find main_window for open_market_pulse")
                    
        except Exception as e:
            logger.error(f"Failed to open MarketPulseViewer: {e}")

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
        pass # Discarded, using linkActivated instead

    def _filter_by_sector(self, sector_name):
        self.tabs.setCurrentIndex(0)
        if sector_name == "全部":
            self.search_input.clear()
        else:
            self.search_input.setText(sector_name)
        self.status_label.setText(f"当前筛选板块: {sector_name}")

    def _on_cell_clicked(self, row, col):
        table = self.sender()
        # 动态获取列
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                t = header.text()
                if t in ["代码", "龙头"]: code_col = i
                elif t in ["名称", "龙头名称"]: name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it:
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

    def _on_selection_changed(self):
        """处理键盘上下键切换时的联动"""
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        # 获取当前选中的行（取第一个）
        items = table.selectedItems()
        if not items: return
        row = items[0].row()
        
        # 动态获取列
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                t = header.text()
                if t in ["代码", "龙头"]: code_col = i
                elif t in ["名称", "龙头名称"]: name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it and c_it.text():
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

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
        
        # 动态获取列
        code_col, name_col = 2, 3
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                text = header.text()
                if text in ["代码", "龙头"]: code_col = i
                elif text in ["名称", "龙头名称", "板块名称"]: name_col = i

        it_code = table.item(row, code_col)
        it_name = table.item(row, name_col)
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
        target_type_key = self.type_filter.currentData() or "ALL"
        
        # [FIX] 如果使用了下拉过滤且当前不在"全部信号"标签，则自动切到"全部信号"以防止交叉过滤导致全空
        if target_type_key != "ALL" and self.tabs.tabText(self.tabs.currentIndex()) != "全部信号":
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == "全部信号":
                    self.tabs.blockSignals(True)
                    self.tabs.setCurrentIndex(i)
                    self.tabs.blockSignals(False)
                    break
                    
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget): return
        
        # 动态查找当前表格关键属性所在列
        code_col, name_col, pattern_col, sector_col = -1, -1, -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                text = header.text()
                if text in ["代码", "龙头"]: code_col = i
                elif text in ["名称", "龙头名称", "板块名称"]: name_col = i
                elif text in ["形态类别", "形态/信号"]: pattern_col = i
                elif text in ["所属板块"]: sector_col = i

        for row in range(table.rowCount()):
            row_visible = True
            
            # 1. 文本搜索 (代码/名称/板块)
            if search_text:
                c_text = table.item(row, code_col).text().lower() if code_col >= 0 and table.item(row, code_col) else ""
                n_text = table.item(row, name_col).text().lower() if name_col >= 0 and table.item(row, name_col) else ""
                s_text = table.item(row, sector_col).text().lower() if sector_col >= 0 and table.item(row, sector_col) else ""
                
                # 特殊：提取 Name 单元格中存为 UserRole 的板块信息
                if name_col >= 0 and table.item(row, name_col):
                    sector_data = table.item(row, name_col).data(Qt.ItemDataRole.UserRole)
                    if sector_data: s_text += str(sector_data).lower()

                row_visible = (search_text in c_text or search_text in n_text or search_text in s_text)
                                  
            # 2. 类型下拉过滤 (保证逻辑与下拉框计数完全一致)
            if row_visible and target_type_key != "ALL" and pattern_col >= 0:
                pattern_item = table.item(row, pattern_col)
                if pattern_item:
                    raw_pattern = str(pattern_item.data(Qt.ItemDataRole.UserRole) or pattern_item.text())
                    matched_type = "ALERT"
                    for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                        if any(kw.lower() in raw_pattern.lower() for kw in keywords):
                            matched_type = eng_key
                            break
                    row_visible = (matched_type == target_type_key)
                    
            table.setRowHidden(row, not row_visible)
        
        # [NEW] 手动搜索过滤后，自动滚动到顶部显示最新信号
        table.verticalScrollBar().setValue(0)

    def _on_tab_changed(self, index):
        """[MANUAL] 手动切换 Tab 时，应用搜索并回到顶部"""
        self._apply_filter() # 先根据搜索框内容过滤
        table = self.tabs.widget(index)
        if isinstance(table, QTableWidget):
            table.verticalScrollBar().setValue(0) # 回到顶部

    def _on_search_context_menu(self, pos):
        QTimer.singleShot(30, lambda: self.search_input.setText(QApplication.clipboard().text().strip()))

    def _on_selection_changed(self):
        if getattr(self, '_is_updating_ui', False): return
        table = self.sender()
        items = table.selectedItems()
        if items:
            row = items[0].row()
            code_col = 2
            name_col = 3
            
            # 动态查找当前表格的【代码】和【名称】所在列索引
            for i in range(table.columnCount()):
                header = table.horizontalHeaderItem(i)
                if header:
                    text = header.text()
                    if text in ["代码", "龙头"]: code_col = i
                    elif text in ["名称", "龙头名称"]: name_col = i
                    
            code_item = table.item(row, code_col)
            name_item = table.item(row, name_col)
            if code_item and name_item:
                self.code_clicked.emit(code_item.text(), name_item.text())

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
        pass # 禁用布局自动恢复以避免由历史缓存引起的列宽失控异常

    def _clear_filters(self):
        """一键清空搜索框和下拉过滤状态"""
        self.search_input.clear()
        if self.type_filter.count() > 0:
            self.type_filter.setCurrentIndex(0)

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
        self.stats_info_label.setText("跟单: 0 | 突破: 0 | 尾盘: 0 | 风险: 0 | 破位: 0 | 全部: 0")
        
        # 5. 刷新下拉框计数
        self._refresh_type_filter_items()
        self.status_label.setText("📊 信号面板已重置，等待新行情数据流入...")
        logger.info("SignalDashboard: User manual reset triggered.")

    def _on_engine_manual_run(self):
        """手动触发引擎全链路逻辑验证"""
        try:
            self.status_label.setText("⚡ 正在执行引擎全链路重算...")
            self.manual_run_btn.setEnabled(False)
            
            # 1. 触发引擎层强制重算
            from sector_focus_engine import get_focus_controller
            ctrl = get_focus_controller()
            if ctrl:
                ctrl.manual_run()
            
            # 2. 立即更新 UI 视图
            self._update_engine_views()
            
            self.status_label.setText("✅ 引擎重算刷新完成")
            logger.info("📡 [UI] 仪表盘已通过手动触发完成引擎数据刷新")
        except Exception as e:
            self.status_label.setText(f"❌ 重算失败: {e}")
        finally:
            # 冷却 1.5s 后恢复可点击状态，防止疯狂连点
            QTimer.singleShot(1500, lambda: self.manual_run_btn.setEnabled(True))

    def _get_next_scan_time(self):
        """[Dragon] 计算下一个 30 分钟扫描节点"""
        now = datetime.now()
        cur_min_total = now.hour * 60 + now.minute
        # 交易节拍节点 (相对于 9:30 的偏移量)
        slots = [0, 30, 60, 90, 120, 240, 270, 300, 330] # 9:30, 10:00, 10:30...
        for s in slots:
            target_min = 570 + s
            if target_min > cur_min_total:
                h, m = target_min // 60, target_min % 60
                return f"{h:02d}:{m:02d}"
        return "15:00"

    def _update_status_carousel(self):
        """[MOD] 底部状态栏轮播逻辑"""
        if not self._carousel_messages:
            self.status_label.setText("⌛ 系统初始化中...")
            return
        self._carousel_idx = (self._carousel_idx + 1) % len(self._carousel_messages)
        self.status_label.setText(self._carousel_messages[self._carousel_idx])

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SignalDashboardPanel()
    window.show()
    sys.exit(app.exec())

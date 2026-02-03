# -*- coding: utf-8 -*-
"""
HotlistPanel - 热点自选面板
支持快捷添加、盈亏跟踪、弹出详情窗口

数据持久化：signal_strategy.db (follow_record 表)
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import pandas as pd
from JohnsonUtil import LoggerFactory
# 日内形态检测器
try:
    from intraday_pattern_detector import IntradayPatternDetector, PatternEvent
    HAS_PATTERN_DETECTOR = True
except ImportError:
    HAS_PATTERN_DETECTOR = False
    IntradayPatternDetector = None
    PatternEvent = None

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView, QMenu,
    QMessageBox, QDialog, QFrame, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QColor, QAction

# [REFACTOR] WindowMixin Imports
from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
import os
from PyQt6 import QtGui
from db_utils import SQLiteConnectionManager

logger = LoggerFactory.getLogger(__name__)

DB_FILE = "signal_strategy.db"


@dataclass
class HotlistItem:
    """热点项数据结构"""
    id: int = 0
    code: str = ""
    name: str = ""
    add_price: float = 0.0
    add_time: str = ""
    signal_type: str = "手动添加"
    group: str = "观察"  # 观察/蓄势/已启动/持仓
    current_price: float = 0.0
    pnl_percent: float = 0.0
    stop_loss: float = 0.0
    notes: str = ""
    status: str = "ACTIVE"


# [NEW] 独立的工作线程，负责后台拉取数据
class HotlistWorker(QThread):
    # 信号：(follow_queue_df, error_msg)
    data_ready = pyqtSignal(object, str)
    
    def __init__(self, interval=2.0, parent=None):
        super().__init__(parent)
        self.interval = interval
        self._running = True
        
    def run(self):
        import time
        from trading_hub import get_trading_hub
        
        while self._running:
            try:
                # 1. 拉取跟单队列数据
                hub = get_trading_hub()
                df_follow = hub.get_follow_queue_df()
                
                # 2. 发送数据 (不要在线程里操作 UI)
                self.data_ready.emit(df_follow, "")
                
            except Exception as e:
                logger.error(f"HotlistWorker error: {e}")
                self.data_ready.emit(None, str(e))
                
            # 简单的休眠
            for _ in range(int(self.interval * 10)):
                if not self._running: break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait()


class HotlistPanel(QWidget, WindowMixin):
    """
    热点自选面板（浮动窗口）
    
    功能：
    - 快速添加当前浏览股票到热点列表
    - 显示加入价、当前价、盈亏百分比
    - 双击跳转至该股票K线
    - 右键菜单管理（移除、设置止损等）
    - Alt+H 快捷键切换显示/隐藏
    
    信号：
    - stock_selected: 用户选择了某只股票，通知主窗口切换
    - item_double_clicked: 双击打开详情弹窗
    """
    
    stock_selected = pyqtSignal(str, str)  # code, name
    item_double_clicked = pyqtSignal(str, str, float)  # code, name, add_price
    voice_alert = pyqtSignal(str, str)  # code, message - 语音通知信号
    signal_log = pyqtSignal(str, str, str, str)  # code, name, pattern, message - 信号日志
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # [REFACTOR] Mixin Init
        self.scale_factor = get_windows_dpi_scale_factor()
        self.initial_x = 0
        self.initial_y = 0
        self.initial_w = 280
        self.initial_h = 400
        self.items: List[HotlistItem] = []
        self._drag_pos = None
        self.voice_enabled = True  # 是否启用语音通知
        self._voice_paused = False  # 语音播报状态
        self._is_refreshing = False # 刷新状态标识，防止信号干扰
        self._last_follow_fingerprint = ""
        self._last_follow_fingerprint = ""
        self.follow_count = 0  # [NEW] Track follow queue count
        self._connection_warning_logged = False  # [NEW] Log throttle flag
        
        # 设置为浮动工具窗口（可调整大小）
        self.setWindowFlags(
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowTitle("🔥 热点自选")
        
        # 可调整大小范围
        self.setMinimumWidth(200)
        self.setMaximumWidth(800)  # [OPTIMIZE] Allow wider window
        self.setMinimumHeight(250)
        self.setMaximumHeight(800)
        self.resize(580, 400)      # [OPTIMIZE] Wider default size
        
        self._init_db()
        self._init_ui()
        self._load_from_db()
        
        # 数据流校验缓存：{code: (price, volume, amount)}
        self._last_data_sigs: dict[str, tuple[float, float, float]] = {}
        
        # 语音前缀播放控制
        self._last_voice_prefix_time: float = 0.0  # 全局冷却计时
        self._batch_spoken_flag: bool = False      # 单批次互斥锁
        
        # 信号计数统计：{(code, pattern): count} —— 当天重复信号计数
        self._signal_counts: dict[tuple[str, str], int] = {}
        self._voice_paused: bool = False
        
        # 日期控制
        self._last_reset_date = datetime.now().date()
        
        # 检测器与指纹状态
        self._last_check_fingerprint: str = ""
        self._pattern_detector = None  # 语音暂停标记
        
        # [MODIFIED] 移除 QTimer，改用 Worker
        self.data_worker = HotlistWorker(interval=1.0, parent=self)
        self.data_worker.data_ready.connect(self._on_worker_data)
        self.data_worker.start()  # [FIX] Start immediately
        
        # [NEW] 加载信号计数（从数据库）
        self._load_signal_counts()
    
    def showEvent(self, event):
        """窗口显示时"""
        super().showEvent(event)
        if not self.data_worker.isRunning():
            self.data_worker.start()
    
    def closeEvent(self, event):
        # [NEW] Save position (debounced)
        self.save_window_position_qt_visual(self, "HotlistPanel")
        
        if self.data_worker.isRunning():
            self.data_worker.stop()
        super().closeEvent(event)
    
    def _init_db(self):
        """确保数据库表存在，并扩展字段"""
        try:
            # [OPTIMIZED] Use connection manager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            
            # 检查 follow_record 表是否存在，如不存在则创建
            c.execute("""
                CREATE TABLE IF NOT EXISTS follow_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    code TEXT NOT NULL,
                    name TEXT,
                    follow_date TEXT,
                    follow_price REAL,
                    stop_loss REAL,
                    status TEXT DEFAULT 'ACTIVE',
                    exit_date TEXT,
                    exit_price REAL,
                    pnl_pct REAL,
                    feedback TEXT
                )
            """)
            
            # Migration: 添加 group 字段
            try:
                c.execute("ALTER TABLE follow_record ADD COLUMN group_tag TEXT DEFAULT '观察'")
            except sqlite3.OperationalError:
                pass  # 字段已存在
            
            # Migration: 添加 signal_type 字段
            try:
                c.execute("ALTER TABLE follow_record ADD COLUMN signal_type TEXT DEFAULT '手动添加'")
            except sqlite3.OperationalError:
                pass
            
            # [NEW] 创建信号计数表（按天统计）
            c.execute("""
                CREATE TABLE IF NOT EXISTS signal_counts (
                    code TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    last_trigger TEXT,
                    PRIMARY KEY (code, pattern, date)
                )
            """)
            
            conn.commit()
            c.close()
        except Exception as e:
            logger.error(f"HotlistPanel DB init error: {e}")
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # 外框样式
        self.setStyleSheet("""
            HotlistPanel {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)
        
        # 标题栏（可拖动区域）
        self.header = QFrame()
        self.header.setFixedHeight(28)
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border-bottom: 1px solid #444;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }
            QLabel {
                color: #FFD700;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 9pt;
                padding: 2px 6px;
            }
            QPushButton:hover {
                color: #FFD700;
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        
        title_label = QLabel("🔥 热点自选")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("刷新盈亏")
        refresh_btn.clicked.connect(self._refresh_pnl)
        header_layout.addWidget(refresh_btn)
        
        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setToolTip("关闭 (Alt+H)")
        close_btn.setStyleSheet("QPushButton:hover { color: #ff6b6b; }")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(self.header)
        
        
        # --- 使用 TabWidget ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #1e1e1e;
            }
            QTabBar::tab {
                background: #2d2d2d;
                color: #888;
                padding: 5px 10px;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #FFD700;
                border-bottom: 1px solid #1e1e1e;
            }
            QTabBar::tab:hover {
                background: #333;
            }
        """)
        
        # Tab 1: Hotlist
        self.hotlist_widget = QWidget()
        self._init_hotlist_ui()
        self.tabs.addTab(self.hotlist_widget, "🔥 Hotlist")
        
        # Tab 2: Follow Queue
        self.follow_widget = QWidget()
        self._init_follow_queue_ui()
        self.tabs.addTab(self.follow_widget, "📋 Follow Queue")
        
        layout.addWidget(self.tabs)
        
        # 状态栏 + 暂停语音按钮
        status_bar = QHBoxLayout()
        self.status_label = QLabel("共 0 只热点股")
        self.status_label.setStyleSheet("color: #666; font-size: 9pt; padding: 2px 8px;")
        status_bar.addWidget(self.status_label)
        
        status_bar.addStretch()
        
        # 暂停语音按钮
        self.pause_voice_btn = QPushButton("🔊")
        self.pause_voice_btn.setFixedSize(28, 22)
        self.pause_voice_btn.setCheckable(True)
        self.pause_voice_btn.setToolTip("点击暂停/恢复语音播报")
        self.pause_voice_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #444;
                border-radius: 3px;
                font-size: 12pt;
            }
            QPushButton:checked {
                background: #600;
                border-color: #900;
            }
            QPushButton:hover {
                background: #333;
            }
        """)
        self.pause_voice_btn.clicked.connect(self.toggle_voice)
        status_bar.addWidget(self.pause_voice_btn)
        
        layout.addLayout(status_bar)
    
    def toggle_voice(self):
        """切换语音播报开启/暂停状态"""
        self._voice_paused = not self._voice_paused
        
        # 更新按钮文本和样式
        if self._voice_paused:
            self.pause_voice_btn.setText("恢复语音")
            self.pause_voice_btn.setStyleSheet("background-color: #600; border: 1px solid #f00;")
            logger.info(f"🔇 Hotlist Voice PAUSED (Instance {id(self)})")
        else:
            self.pause_voice_btn.setText("暂停语音")
            self.pause_voice_btn.setStyleSheet("")
            logger.info(f"🔊 Hotlist Voice RESUMED (Instance {id(self)})")

    def _init_hotlist_ui(self):
        """初始化热点列表 UI (Tab 1 content)"""
        layout = QVBoxLayout(self.hotlist_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(9) # Changed from 8 to 9 for "序号"
        self.table.setHorizontalHeaderLabels(["序号", "代码", "名称", "加入价", "现价", "盈亏%", "分组", "时间", "信号类型"]) # Added "序号" and "信号类型"
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.cellClicked.connect(self._on_click)
        
        # [NEW] 启用列排序功能
        self.table.setSortingEnabled(True)
        
        # [NEW] 添加键盘导航联动（上下键切换时也触发股票选择）
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        
        # 表头设置 - 极致紧凑，紧贴内容
        header = self.table.horizontalHeader()
        
        # 🟢 [OPTIMIZE] 使用 Interactive 模式并预设紧凑宽度
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        # 预设宽度
        self.table.setColumnWidth(0, 35)   # 序号
        self.table.setColumnWidth(1, 60)   # 代码
        self.table.setColumnWidth(3, 50)   # 加入价
        self.table.setColumnWidth(4, 50)   # 现价
        self.table.setColumnWidth(5, 55)   # 盈亏%
        self.table.setColumnWidth(6, 40)   # 分组
        self.table.setColumnWidth(7, 50)   # 时间
        self.table.setColumnWidth(8, 60)   # 信号类型
        
        # 名称列自适应拉伸
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        # 允许手动调整
        header.setStretchLastSection(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 尽量不出现横向滚动条
        
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #ddd;
                border: none;
                font-size: 10pt;
            }
            QTableWidget::item {
                padding: 1px 3px;
            }
            QTableWidget::item:selected {
                background-color: #444;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #aaa;
                border: none;
                padding: 2px 4px;
                font-size: 9pt;
            }
        """)
        
        layout.addWidget(self.table)

    def _init_follow_queue_ui(self):
        """初始化跟单队列 UI (Tab 2 content)"""
        layout = QVBoxLayout(self.follow_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.follow_table = QTableWidget()
        cols = ["序号", "状态", "代码", "名称", "信号类型", "阶段", "P", "策略", "入场", "理由", "时间"] # Added "序号"
        self.follow_table.setColumnCount(len(cols))
        self.follow_table.setHorizontalHeaderLabels(cols)
        self.follow_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.follow_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.follow_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.follow_table.customContextMenuRequested.connect(self._on_follow_context_menu)
        self.follow_table.cellDoubleClicked.connect(self._on_follow_double_click)
        self.follow_table.cellClicked.connect(self._on_follow_click)
        # [FIX] Add keyboard navigation support
        self.follow_table.currentCellChanged.connect(self._on_follow_cell_changed)
        
        header = self.follow_table.horizontalHeader()
        for i in range(self.follow_table.columnCount()):
            if i == 3: # 名称
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        
        self.follow_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.follow_table.verticalHeader().setVisible(False)
        self.follow_table.setStyleSheet(self.table.styleSheet()) # Reuse style
        
        layout.addWidget(self.follow_table)

    def _load_from_db(self):
        """从数据库加载热点列表"""
        self.items.clear()
        try:
            # [OPTIMIZED] Use connection manager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            
            # Temporarily set row factory
            old_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
            
            c = conn.cursor()
            c.execute("""
                SELECT * FROM follow_record 
                WHERE status = 'ACTIVE' 
                ORDER BY id DESC
            """)
            rows = c.fetchall()
            c.close()
            # Restore row factory
            conn.row_factory = old_factory
            
            for r in rows:
                item = HotlistItem(
                    id=r['id'],
                    code=r['code'],
                    name=r['name'] or "",
                    add_price=r['follow_price'] or 0.0,
                    add_time=r['follow_date'] or "",
                    stop_loss=r['stop_loss'] or 0.0,
                    status=r['status'],
                    group=r['group_tag'] if 'group_tag' in r.keys() else "观察",
                    signal_type=r['signal_type'] if 'signal_type' in r.keys() else "手动添加"
                )
                self.items.append(item)
            
            self._refresh_table()
        except Exception as e:
            logger.error(f"Load hotlist error: {e}")
    
    def _refresh_table(self):
        """刷新表格显示"""
        from trading_analyzerQt6 import NumericTableWidgetItem # Import here to avoid circular dependency if not already imported
        
        self._is_refreshing = True
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        
        # [FIX] 保存选中项和滚动条
        current_code = None
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            it = self.table.item(curr_row, 1) # Code col (index shifted to 1)
            if it: current_code = it.text()
            
        v_scroll = self.table.verticalScrollBar().value()
        
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.items))
        
        for row, item in enumerate(self.items):
            # 序号 (No.) - 传整数以支持正确排序
            no_item = NumericTableWidgetItem(row + 1)
            no_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, no_item)
            
            # 代码
            code_item = QTableWidgetItem(item.code)
            self.table.setItem(row, 1, code_item)
            
            # 名称
            name_item = QTableWidgetItem(item.name)
            self.table.setItem(row, 2, name_item)
            
            # 加入价 - 传浮点数
            add_price_item = NumericTableWidgetItem(item.add_price)
            add_price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, add_price_item)
            
            # 现价 - 如果有值传浮点数，否则传字符串 "-"
            cur_price_val = item.current_price if item.current_price > 0 else "-"
            cur_price_item = NumericTableWidgetItem(cur_price_val)
            cur_price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, cur_price_item)
            
            # 盈亏% - 传浮点数
            pnl_val = item.pnl_percent if item.current_price > 0 else "-"
            pnl_item = NumericTableWidgetItem(pnl_val)
            pnl_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if item.pnl_percent > 0:
                pnl_item.setForeground(QColor(220, 80, 80))  # 红色
            elif item.pnl_percent < 0:
                pnl_item.setForeground(QColor(80, 200, 120))  # 绿色
            self.table.setItem(row, 5, pnl_item)
            
            # 分组
            group_item = QTableWidgetItem(item.group)
            group_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, group_item)
            
            # 时间 (显示短时间格式)
            time_str = item.add_time[5:-3] if len(item.add_time) > 10 else item.add_time
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 7, time_item)

            # 信号类型
            signal_type_item = QTableWidgetItem(item.signal_type)
            signal_type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 8, signal_type_item)
        
        # 自动调整列宽以适应内容
        self.table.resizeColumnsToContents()
        # [FIX] 恢复选中项
        if current_code:
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 1) # Code col
                if it and it.text() == current_code:
                    self.table.setCurrentCell(r, 1)
                    break
        
        self.table.verticalScrollBar().setValue(v_scroll)
        
        self.table.setSortingEnabled(was_sorting)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._is_refreshing = False
        
        self._update_status_bar()

    def _update_status_bar(self):
        """[NEW] 统一更新状态栏信息"""
        hot_count = len(self.items)
        follow_txt = f" | 跟单: {self.follow_count}" if self.follow_count > 0 else ""
        self.status_label.setText(f"🔥 热点: {hot_count}{follow_txt}")
    
    def add_stock(self, code: str, name: str, price: float, signal_type: str = "手动添加", group: str = "观察"):
        """
        添加股票到热点列表
        
        Args:
            code: 股票代码
            name: 股票名称
            price: 加入时价格
            signal_type: 信号类型
            group: 分组名称 (观察/强势/缺口等)
        """
        # 检查是否已存在
        for item in self.items:
            if item.code == code:
                logger.info(f"热点已存在: {code} {name}")
                return False
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO follow_record 
                (code, name, follow_date, follow_price, status, signal_type, group_tag)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
            """, (code, name, now, price, signal_type, group))
            new_id = c.lastrowid
            conn.commit()
            c.close()
            
            new_item = HotlistItem(
                id=new_id,
                code=code,
                name=name,
                add_price=price,
                add_time=now,
                current_price=price,
                pnl_percent=0.0,
                signal_type=signal_type,
                group=group
            )
            self.items.insert(0, new_item)
            self._refresh_table()
            
            logger.info(f"添加热点: {code} {name} @ {price:.2f}")
            
            # 语音通知：重要信号类型
            if any(kw in signal_type for kw in ("龙头", "突破", "启动", "强势")):
                self._notify_voice(code, f"新增热点 {name}")
            return True
            
        except Exception as e:
            logger.error(f"Add hotlist error: {e}")
            return False
    
    def remove_stock(self, code: str):
        """移除股票"""
        for item in self.items:
            if item.code == code:
                try:
                    mgr = SQLiteConnectionManager.get_instance(DB_FILE)
                    conn = mgr.get_connection()
                    c = conn.cursor()
                    c.execute("UPDATE follow_record SET status = 'REMOVED' WHERE id = ?", (item.id,))
                    conn.commit()
                    c.close()
                    
                    self.items.remove(item)
                    self._refresh_table()
                    logger.info(f"移除热点: {code}")
                    return True
                except Exception as e:
                    logger.error(f"Remove hotlist error: {e}")
        return False
    
    def update_prices(self, price_map: Dict[str, float]):
        """
        批量更新现价和盈亏
        
        Args:
            price_map: {code: current_price}
        """
        for item in self.items:
            if item.code in price_map:
                item.current_price = price_map[item.code]
                if item.add_price > 0:
                    item.pnl_percent = (item.current_price - item.add_price) / item.add_price * 100
        
        self._refresh_table()
    
    def _on_worker_data(self, df_follow, error_msg):
        """Worker 数据回调 (主线程执行)"""
        if error_msg:
            return
            
        if df_follow is not None:
            # [OPTIMIZE] 差分更新检查
            try:
                # 使用 updated_at 的最大值作为指纹 (假设最新的一条变了，数据就变了)
                # 或者如果有行数变化
                current_fingerprint = ""
                if not df_follow.empty:
                    max_time = df_follow['updated_at'].max() if 'updated_at' in df_follow.columns else ""
                    current_fingerprint = f"{len(df_follow)}_{max_time}"
                
                # 如果指纹一致，跳过重绘
                if hasattr(self, '_last_follow_fingerprint') and self._last_follow_fingerprint == current_fingerprint:
                    pass
                else:
                    self.follow_count = len(df_follow) # [NEW] Update count
                    self._update_follow_queue(df_follow)
                    self._last_follow_fingerprint = current_fingerprint
                    self._update_status_bar() # [NEW] Refresh UI
            except Exception:
                # 出错降级：总是更新
                self._update_follow_queue(df_follow)

            # 刷新 PnL (仅当 Tab 1 可见时？或者总是？)
            # 用户抱怨日志太多，先静默调用
            self._refresh_pnl_ui_only()

    def _refresh_pnl(self):
        """手动刷新按钮回调"""
        self._refresh_pnl_ui_only()
        # logger.info("界面刷新已触发")

    def _refresh_pnl_ui_only(self):
        """仅做 UI 层面的 PnL 刷新（不拉取数据）"""
        # [FIX] 使用 window() 而不是 parent() 来获取主窗口（因为 parent=None）
        main_window = None
        try:
            # 尝试通过 window() 获取顶层窗口
            from PyQt6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                # 优先寻找带有 df_all 属性且看起来像 MainWindow 的窗口
                if hasattr(widget, 'df_all'):
                    if widget.__class__.__name__ == 'MainWindow' or "Visualizer" in str(widget.windowTitle()):
                        main_window = widget
                        break
        except Exception:
            pass
        
        if main_window and hasattr(main_window, 'df_all') and not main_window.df_all.empty:
            df = main_window.df_all
            price_map = {}
            phase_map = {}
            
            for item in self.items:
                if item.code in df.index:
                    row = df.loc[item.code]
                    price_map[item.code] = row.get('close', row.get('price', 0))
                    # [NEW] Extract Phase from shadow_info or last_reason if possible, or TradePhase column if it exists
                    # Currently Phase is stored in 'last_action' or just notes in Hub.
                    # Best way: Check 'last_action' or 'shadow_info' if Phase Engine writes to it.
                    # As per P0.6, Phase Engine writes to snap['trade_phase'].
                    # We might need to expose snap data in df_all or just use what we have.
                    # For now, let's try to get it from 'trade_phase' column if we added it to df_all in P0.6
                    
                    phase = str(row.get('last_action', '')) # Placeholder
                    # Try to parse Phase from 'notes' in Hub if needed, but here we just use what's in DF
                    if 'trade_phase' in row:
                        phase = str(row['trade_phase'])
                    
                    phase_map[item.code] = phase
            
            if price_map:
                self.update_prices(price_map, phase_map)
                # [SILENCE] 用户抱怨日志刷屏
                # logger.debug(f"✅ Hotlist PnL refreshed ({len(price_map)} items)")
            
            # [NEW] 刷新跟单队列
            self._update_follow_queue()
            
            # Reset warning flag if connection is good
            self._connection_warning_logged = False
            
        else:
            # 如果没有主窗口数据，也尝试刷新跟单队列（至少显示列表）
            self._update_follow_queue()
            
            if not self._connection_warning_logged:
                logger.warning("⚠️ 无法获取主窗口数据，仅刷新跟单列表 (Log once)")
                self._connection_warning_logged = True

    def update_prices(self, price_map: Dict[str, float], phase_map: Dict[str, str] = None):
        """
        批量更新现价和盈亏
        """
        for item in self.items:
            if item.code in price_map:
                item.current_price = price_map[item.code]
                if item.add_price > 0:
                    item.pnl_percent = (item.current_price - item.add_price) / item.add_price * 100
            
            if phase_map and item.code in phase_map:
                # Update visual only (since item struct doesn't have phase field yet, maybe reuse group or notes?)
                # Actually let's just update the table directly in _refresh_table or store it in item.group for now
                item.group = phase_map[item.code] or item.group
        
        self._refresh_table()

    def flash_screen(self, color="#FF0000", duration=500):
        """
        [Visual] 边框闪烁效果
        """
        original_style = self.styleSheet()
        flash_style = original_style + f"""
            HotlistPanel {{
                border: 3px solid {color};
            }}
        """
        self.setStyleSheet(flash_style)
        QTimer.singleShot(duration, lambda: self.setStyleSheet(original_style))


    def _update_follow_queue(self, df=None):
        """[Phase 2] 刷新跟单队列可视化 (数据由 Worker 提供)"""
        try:
            if df is None:
                return # 等待 Worker 数据
                
            if df.empty:
                self.follow_table.setRowCount(0)
                return

            # [FIX] Deduplicate: Ensure one row per stock (latest)
            if 'code' in df.columns:
                df['code'] = df['code'].astype(str).str.strip() # Ensure consistency
            
            df = df.sort_values(by=['priority', 'updated_at'], ascending=[False, False])
            df = df.drop_duplicates(subset=['code'], keep='first')

            # [SMART UPDATE] Check if we can do an in-place update (Speed & Stability)
            # CRITICAL: If table is sorted by user, modifying items causes them to jump rows immediately,
            # invalidating any index maps. We MUST disable sorting to update, or just Rebuild.
            
            is_sorted = self.follow_table.isSortingEnabled() 
            current_rows = self.follow_table.rowCount()
            needs_full_rebuild = False
            
            if is_sorted:
                needs_full_rebuild = True # Safe fallback for sorted tables
            elif current_rows != len(df):
                needs_full_rebuild = True
            else:
                # Check if codes match exactly in order (Model Order)
                new_codes = df['code'].tolist()
                for r in range(current_rows):
                    item = self.follow_table.item(r, 2) # Code col (index shifted to 2)
                    if not item or item.text() != new_codes[r]:
                        needs_full_rebuild = True
                        break
            
            if not needs_full_rebuild:
                # --- IN-PLACE UPDATE (Only for Unsorted/Stable Tables) ---
                for row_idx, row in enumerate(df.itertuples()):
                    # Exact row match guaranteed by checks above
                    
                    # Status Col 1
                    if (it := self.follow_table.item(row_idx, 1)):
                        if it.text() != str(row.status):
                            it.setText(str(row.status))
                            if row.status == 'TRACKING': it.setForeground(QColor('#FFD700'))
                            elif row.status == 'ENTERED': it.setForeground(QColor('#00FF00'))
                            else: it.setForeground(QColor('#ddd'))
                    
                    # Phase Col 5
                    phase_txt = "-"
                    notes = str(row.notes) if row.notes else ""
                    import re
                    match = re.search(r'\[(.*?)\]', notes)
                    if match: phase_txt = match.group(1)
                    elif notes: phase_txt = notes[:10]
                    
                    if (it := self.follow_table.item(row_idx, 5)):
                        if it.text() != phase_txt:
                            it.setText(phase_txt)
                            if phase_txt in ('TOP_WATCH', '顶部观察'): it.setForeground(QColor('#FF8C00'))
                            elif phase_txt in ('EXIT', '分批离场'): it.setForeground(QColor('#FF4500'))
                            elif phase_txt in ('LAUNCH', '启动'): it.setForeground(QColor('#00BFFF'))
                            else: it.setForeground(QColor('#ddd'))

                    # Priority Col 6
                    if (it := self.follow_table.item(row_idx, 6)):
                        if it.text() != str(row.priority):
                             it.setText(str(row.priority))
                        
                    # Time Col 10
                    time_str = str(row.updated_at).split(' ')[-1] if row.updated_at else ""
                    if (it := self.follow_table.item(row_idx, 10)):
                        if it.text() != time_str:
                             it.setText(time_str)

                return

            # --- FULL REBUILD (Structure Changed or Sorted) ---
            from trading_analyzerQt6 import NumericTableWidgetItem
            
            # [FIX] Block Signals to prevent side effects during mass changes
            self._is_refreshing = True
            self.follow_table.blockSignals(True)
            self.follow_table.setSortingEnabled(False)
            self.follow_table.setUpdatesEnabled(False)
            
            # [FIX] Preserve Scroll and Selection State
            current_code = None
            current_row = self.follow_table.currentRow()
            if current_row >= 0:
                item = self.follow_table.item(current_row, 2) # Code col (index shifted to 2)
                if item:
                    current_code = item.text()
            
            v_scroll = self.follow_table.verticalScrollBar().value()
            h_scroll = self.follow_table.horizontalScrollBar().value()

            # [FIX] Nuclear Option: Reset RowCount to 0 to guarantee no ghosts
            self.follow_table.setRowCount(0)
            self.follow_table.setRowCount(len(df))
            
            for row_idx, row in enumerate(df.itertuples()):
                # cols = ["序号", "状态", "代码", "名称", "信号类型", "阶段", "P", "策略", "入场", "理由", "时间"]
                
                # 0. No. - 传整数
                no_item = NumericTableWidgetItem(row_idx + 1)
                no_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.follow_table.setItem(row_idx, 0, no_item)
                
                # 1. Status
                status_item = QTableWidgetItem(str(row.status))
                if row.status == 'TRACKING':
                    status_item.setForeground(QColor('#FFD700')) # Gold
                elif row.status == 'ENTERED':
                    status_item.setForeground(QColor('#00FF00')) # Green
                self.follow_table.setItem(row_idx, 1, status_item)
                
                # 2. Code, 3. Name
                self.follow_table.setItem(row_idx, 2, QTableWidgetItem(str(row.code)))
                self.follow_table.setItem(row_idx, 3, QTableWidgetItem(str(row.name)))
                
                # 4. Signal Type
                self.follow_table.setItem(row_idx, 4, QTableWidgetItem(str(row.signal_type)))
                
                # 5. Phase
                phase_txt = "-"
                notes = str(row.notes) if row.notes else ""
                import re
                match = re.search(r'\[(.*?)\]', notes)
                if match:
                    phase_txt = match.group(1) # SCOUT, LAUNCH etc
                elif notes:
                    phase_txt = notes[:10] # Show part of notes if no bracket
                
                phase_item = QTableWidgetItem(phase_txt)
                # [P7] 阶段着色: 风险预警
                if phase_txt in ('TOP_WATCH', '顶部观察'):
                    phase_item.setForeground(QColor('#FF8C00')) # DarkOrange
                elif phase_txt in ('EXIT', '分批离场'):
                    phase_item.setForeground(QColor('#FF4500')) # OrangeRed
                elif phase_txt in ('LAUNCH', '启动'):
                    phase_item.setForeground(QColor('#00BFFF')) # DeepSkyBlue
                
                self.follow_table.setItem(row_idx, 5, phase_item)
                
                # 6. Priority - 尝试转为数值
                try:
                    p_val = float(row.priority)
                except:
                    p_val = row.priority
                p_item = NumericTableWidgetItem(p_val)
                p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.follow_table.setItem(row_idx, 6, p_item)
                
                # 7. Strategy
                self.follow_table.setItem(row_idx, 7, QTableWidgetItem(str(row.entry_strategy)))
                
                # 8. Entry
                entry_txt = f"{row.entry_price:.2f}" if getattr(row, 'entry_price', 0) > 0 else f"MA5" # 简单显示
                self.follow_table.setItem(row_idx, 8, QTableWidgetItem(entry_txt))
                
                # 9. Reason
                reason_item = QTableWidgetItem(str(row.notes) if row.notes else "")
                reason_item.setToolTip(str(row.notes) if row.notes else "")
                self.follow_table.setItem(row_idx, 9, reason_item)

                # 10. Time
                time_str = str(row.updated_at).split(' ')[-1] if row.updated_at else ""
                self.follow_table.setItem(row_idx, 10, QTableWidgetItem(time_str))

            # [FIX] Restore Scroll and Selection BEFORE re-enabling signals
            if current_code:
                # Find the row with this code
                for r in range(self.follow_table.rowCount()):
                    it = self.follow_table.item(r, 2)
                    if it and it.text() == current_code:
                        self.follow_table.setCurrentCell(r, 2)
                        break
            
            self.follow_table.verticalScrollBar().setValue(v_scroll)
            self.follow_table.horizontalScrollBar().setValue(h_scroll)

            self.follow_table.setUpdatesEnabled(True)
            self.follow_table.setSortingEnabled(True) # Re-enable sorting
            self.follow_table.blockSignals(False) # [FIX] Unblock signals
            self.follow_table.resizeColumnsToContents()
            self._is_refreshing = False

        except Exception as e:
            logger.error(f"Error updating follow queue UI: {e}")

    def _on_follow_cell_changed(self, currentRow, _currentColumn, _previousRow, _previousColumn):
        """跟单队列键盘导航：联动K线"""
        # 复用单击逻辑，确保行为一致
        if self._is_refreshing: return
        if currentRow >= 0:
            self._on_follow_click(currentRow, 0)
        
    def _on_follow_click(self, row, col):
        """跟单队列单击：联动K线"""
        if self._is_refreshing: return
        try:
            code_item = self.follow_table.item(row, 2) # Shift index No(0), Status(1), Code(2)
            name_item = self.follow_table.item(row, 3)
            if code_item and name_item:
                code = str(code_item.text()).strip()
                name = str(name_item.text()).strip()
                if code:
                    # [FIX] Link Only: disable active realtime fetching
                    self.stock_selected.emit(f"{code}|realtime=false", name)
        except Exception as e:
            logger.error(f"Follow click error: {e}")

    def _on_follow_double_click(self, row, col):
        """跟单队列双击：打开详情"""
        if self._is_refreshing: return
        try:
            code_item = self.follow_table.item(row, 2) # Shift index
            name_item = self.follow_table.item(row, 3)
            if code_item and name_item:
                code = str(code_item.text()).strip()
                name = str(name_item.text()).strip()
                # 触发详情信号 (Main Window handles it)
                self.item_double_clicked.emit(code, name, 0.0)
        except Exception as e:
            logger.error(f"Follow double-click error: {e}")

    def _on_follow_context_menu(self, pos):
        """跟单队列右键菜单"""
        row = self.follow_table.currentRow()
        if row < 0: return
        
        code_item = self.follow_table.item(row, 2) # Shifted index
        name_item = self.follow_table.item(row, 3) # Shifted index
        if not code_item: return
        
        code = code_item.text()
        name = name_item.text() if name_item else ""
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #ddd;
                border: 1px solid #555;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: #444;
            }
        """)
        
        # 动作：取消跟踪 (标记为 CANCELLED)
        action_cancel = QAction("🚫 不再跟踪 (Cancel)", self)
        action_cancel.triggered.connect(lambda: self._update_follow_status(code, "CANCELLED"))
        menu.addAction(action_cancel)
        
        # 动作：手动入场 (标记为 ENTERED)
        action_entered = QAction("✅ 标记为已入场 (Entered)", self)
        action_entered.triggered.connect(lambda: self._update_follow_status(code, "ENTERED"))
        menu.addAction(action_entered)

        menu.addSeparator()

        # 动作：强制移除 (Physical Delete)
        action_delete = QAction("🗑️ 彻底删除 (Delete)", self)
        action_delete.triggered.connect(lambda: self._delete_follow_item(code))
        menu.addAction(action_delete)
        
        menu.exec(self.follow_table.mapToGlobal(pos))

    def _update_follow_status(self, code, new_status):
        """更新跟单状态并刷新"""
        try:
            from trading_hub import get_trading_hub
            hub = get_trading_hub()
            if hub.update_follow_status(code, new_status, notes="Manual update"):
                logger.info(f"Updated follow status for {code} -> {new_status}")
                
                # [FIX] Force immediate reload from DB to refresh UI
                new_df = hub.get_follow_queue_df()
                self._update_follow_queue(new_df)
                
            else:
                logger.error(f"Failed to update status for {code}")
        except Exception as e:
            logger.error(f"Update follow status error: {e}")

    def _delete_follow_item(self, code: str):
        """彻底删除跟单项"""
        try:
            from trading_hub import get_trading_hub
            hub = get_trading_hub()
            if hub.delete_from_follow_queue(code):
                logger.info(f"Deleted follow item: {code}")
                # Force immediate refresh
                new_df = hub.get_follow_queue_df()
                self._update_follow_queue(new_df)
            else:
                logger.warning(f"Failed to delete {code}")
        except Exception as e:
            logger.error(f"Delete follow item error: {e}")
    
    def _clear_exited(self):
        """清空已退出的记录"""
        try:
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            # [FIX] 先查询要删除的数量
            c.execute("SELECT COUNT(*) FROM follow_record WHERE status != 'ACTIVE'")
            count = c.fetchone()[0]
            
            if count == 0:
                logger.info("ℹ️ 没有需要清理的退出记录")
                c.close()
                return
            
            c.execute("DELETE FROM follow_record WHERE status != 'ACTIVE'")
            conn.commit()
            c.close()
            
            # [FIX] 重新加载列表以显示更新
            self._load_from_db()
            logger.info(f"✅ 已清空 {count} 条退出记录")
        except Exception as e:
            logger.error(f"Clear exited error: {e}")
    
    def _load_signal_counts(self):
        """从数据库加载今日信号计数"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("SELECT code, pattern, count FROM signal_counts WHERE date = ?", (today,))
            rows = c.fetchall()
            c.close()
            
            for code, pattern, count in rows:
                self._signal_counts[(code, pattern)] = count
            
            if rows:
                logger.info(f"📊 已加载今日 {len(rows)} 条信号统计")
        except Exception as e:
            logger.debug(f"Load signal counts error: {e}")
    
    def _save_signal_count(self, code: str, pattern: str, count: int):
        """保存单个信号计数到数据库（按天）"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("""
                INSERT OR REPLACE INTO signal_counts (code, pattern, date, count, last_trigger)
                VALUES (?, ?, ?, ?, ?)
            """, (code, pattern, today, count, now))
            conn.commit()
            c.close()
        except Exception as e:
            logger.error(f"Save signal count error: {e}")
    
    def _get_item_from_row(self, row: int) -> Optional[HotlistItem]:
        """
        从表格 UI 行索引获取对应的 HotlistItem（支持排序后正确映射）
        
        Args:
            row: 表格 UI 当前行索引（排序后可能变化）
        
        Returns:
            对应的 HotlistItem 对象，如果未找到则返回 None
        """
        if row < 0 or row >= self.table.rowCount():
            return None
        
        # 从表格单元格读取 code（第 1 列，因为第 0 列是序号）
        code_item = self.table.item(row, 1)
        if not code_item:
            return None
        
        code = code_item.text().strip()
        if not code:
            return None
        
        # 在 self.items 中查找匹配的 HotlistItem
        for item in self.items:
            if item.code == code:
                return item
        return None
    
    def _on_click(self, row: int, col: int):
        """单击切换股票"""
        item = self._get_item_from_row(row)
        if item:
            # [FIX] Link Only: disable active realtime fetching
            self.stock_selected.emit(f"{item.code}|realtime=false", item.name)
    
    def _on_current_cell_changed(self, currentRow: int, _currentColumn: int, _previousRow: int, _previousColumn: int):
        """键盘导航联动（上下键切换时也触发股票选择）"""
        item = self._get_item_from_row(currentRow)
        if item:
            self.stock_selected.emit(f"{item.code}|realtime=false", item.name)
    
    def _on_double_click(self, row: int, col: int):
        """双击打开详情"""
        item = self._get_item_from_row(row)
        if item:
            # [FIX] Link Only: disable active realtime fetching
            self.stock_selected.emit(f"{item.code}|realtime=false", item.name)
            self.item_double_clicked.emit(item.code, item.name, item.add_price)

    def select_stock(self, code: str):
        """外部联动：根据代码选中行"""
        if not code: return False
        
        # 遍历所有行，找到匹配的股票代码
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)  # 第二列是代码 (Index 1)
            if item and item.text() == code:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                # 触发一次_on_current_cell_changed，确保联动K线
                self._on_current_cell_changed(row, 1, -1, -1) 
                return True
        return False
    
    def _on_context_menu(self, pos):
        """右键菜单"""
        row = self.table.currentRow()
        item = self._get_item_from_row(row)
        if not item:
            return
        
        # 使用局部变量绑定 code，避免 lambda 闭包问题
        current_code = item.code
        current_name = item.name
        current_price = item.current_price if item.current_price > 0 else item.add_price
        signal_type = item.signal_type
        
        menu = QMenu(self)
        
        # 🔥 加入跟单队列
        follow_action = QAction("📋 加入跟单队列", self)
        follow_action.triggered.connect(lambda: self._add_to_follow_queue(current_code, current_name, current_price, signal_type))
        menu.addAction(follow_action)
        
        menu.addSeparator()
        
        # 移除
        remove_action = QAction("❌ 移除", self)
        remove_action.triggered.connect(lambda: self.remove_stock(current_code))
        menu.addAction(remove_action)
        
        menu.addSeparator()
        
        # 分组切换
        group_menu = menu.addMenu("📁 分组")
        for g in ["观察", "蓄势", "已启动", "持仓"]:
            action = QAction(g, self)
            action.triggered.connect(lambda checked, grp=g, code=current_code: self._set_group(code, grp))
            group_menu.addAction(action)
        
        menu.exec(self.table.mapToGlobal(pos))
    
    def _add_to_follow_queue(self, code: str, name: str, price: float, signal_type: str):
        """添加到跟单队列"""
        try:
            from trading_hub import get_trading_hub, TrackedSignal
            hub = get_trading_hub()
            
            # 计算目标入场价（默认当前价±3%）
            target_low = price * 0.97
            target_high = price * 1.03
            stop_loss = price * 0.95  # 默认止损5%
            
            signal = TrackedSignal(
                code=code,
                name=name,
                signal_type=signal_type,
                detected_date=datetime.now().strftime("%Y-%m-%d"),
                detected_price=price,
                entry_strategy="竞价买入",
                target_price_low=target_low,
                target_price_high=target_high,
                stop_loss=stop_loss,
                priority=7,
                source="热点面板"
            )
            
            if hub.add_to_follow_queue(signal):
                logger.info(f"✅ 已加入跟单队列: {code} {name}")
                self._notify_voice(code, f"{name} 已加入跟单队列")
            else:
                logger.warning(f"⚠️ 加入跟单队列失败: {code}")
        except Exception as e:
            logger.error(f"Add to follow queue error: {e}")
    
    def _set_group(self, code: str, group: str):
        """设置分组"""
        for item in self.items:
            if item.code == code:
                old_group = item.group
                item.group = group
                try:
                    mgr = SQLiteConnectionManager.get_instance(DB_FILE)
                    conn = mgr.get_connection()
                    c = conn.cursor()
                    c.execute("UPDATE follow_record SET group_tag = ? WHERE id = ?", (group, item.id))
                    conn.commit()
                    c.close()
                except Exception as e:
                    logger.error(f"Set group error: {e}")
                
                # 语音通知：分组变更为已启动或持仓
                if group in ("已启动", "持仓") and old_group != group:
                    # [P5] 状态变更语音
                    self._notify_voice(code, f"{item.name} 状态变更为 {group}")
                break
        self._refresh_table()
    
    def _notify_voice(self, code: str, msg: str):
        """发送语音通知信号"""
        # 检查语音暂停状态
        if self._voice_paused:
            return
        if self.voice_enabled:
            self.voice_alert.emit(code, msg)
            logger.debug(f"Voice alert: {code} - {msg}")
    
    def _toggle_voice_pause(self):
        """切换语音暂停状态"""
        self._voice_paused = self.pause_voice_btn.isChecked()
        if self._voice_paused:
            self.pause_voice_btn.setText("🔇")
            self.pause_voice_btn.setToolTip("语音已暂停，点击恢复")
            logger.info("🔇 热点语音播报已暂停")
        else:
            self.pause_voice_btn.setText("🔊")
            self.pause_voice_btn.setToolTip("点击暂停/恢复语音播报")
            logger.info("🔊 热点语音播报已恢复")
    
    def contains(self, code: str) -> bool:
        """检查是否已包含该股票"""
        return any(item.code == code for item in self.items)

    # ================== 形态检测 ==================
    def check_patterns(self, df: pd.DataFrame) -> None:
        """
        检测热点股票的形态信号
        
        Args:
            df: 包含实时数据的 DataFrame (df_all)
        """
        if not HAS_PATTERN_DETECTOR:
            logger.warning("⚠️ Pattern Detector not available (Import failed)")
            return
        
        if df is None or df.empty:
            return
            
        # [MODIFIED] 每日重置信号计数（按天统计）
        current_date = datetime.now().date()
        if current_date != self._last_reset_date:
            self._signal_counts.clear()
            self._last_reset_date = current_date
            logger.info(f"📅 新的一天：已重置今日信号计数 ({current_date})")
        
        # ⭐ 使用及健壮的数据指纹 (Length + SumClose + SumVol)
        try:
            c_sum = int(df['close'].sum() * 100)
            v_sum = int(df['volume'].sum())
            current_fp = f"{len(df)}_{c_sum}_{v_sum}"
        except Exception as e:
            current_fp = f"{len(df)}_{hash(str(df.index.tolist()[:5]))}"
            
        # 如果数据未变化，跳过检测
        if hasattr(self, '_last_check_fingerprint') and self._last_check_fingerprint == current_fp:
            return
        self._last_check_fingerprint = current_fp
        
        # ⭐ 新的一轮检测开始：重置本轮说话标记
        self._batch_spoken_flag = False
        
        # 懒加载检测器
        if self._pattern_detector is None:
            self._pattern_detector = IntradayPatternDetector(
                cooldown=120,           # 2分钟冷却
                publish_to_bus=False    # 不发布到全局总线，局部处理
            )
            self._pattern_detector.on_pattern = self._on_signal_detected
            logger.info("🔥 HotlistPanel PatternDetector initialized")
            
        # logger.info(f"🔍 Scan Started: {len(self.items)} items, FP={current_fp}")
        
        # 遍历热点股票
        for item in self.items:
            if item.code not in df.index:
                continue
            try:
                row = df.loc[item.code]
                
                # 1. 基础数据校验 (Data Validation)
                price = float(row.get('price', row.get('close', 0)))
                volume = float(row.get('volume', 0))
                amount = float(row.get('amount', 0))
                prev_close = float(row.get('lastp1d', 0))
                
                # 剔除无效数据流
                if price <= 0 or prev_close <= 0 or volume < 0:
                    continue
                
                # 2. 数据更新检测 (Skip redundant data)
                # 只有当 价、量、额 至少有一个发生变化时，才认为数据流有更新
                current_sig = (price, volume, amount)
                if self._last_data_sigs.get(item.code) == current_sig:
                    continue
                
                # 更新指纹
                self._last_data_sigs[item.code] = current_sig
                
                # 3. 执行形态扫描
                self._pattern_detector.update(
                    code=item.code,
                    name=item.name,
                    tick_df=None,
                    day_row=row,
                    prev_close=prev_close
                )
            except Exception as e:
                # logger.debug(f"Pattern check error for {item.code}: {e}")
                pass

    def _on_signal_detected(self, event: 'PatternEvent') -> None:
        """形态检测回调"""
        try:
            # 数据完整性二次校验
            if not event or not event.code or event.price <= 0:
                return
                
            pattern_cn = IntradayPatternDetector.PATTERN_NAMES.get(event.pattern, event.pattern)
            time_str = datetime.now().strftime('%H:%M:%S')
            
            # ⭐ 信号计数统计（累积）
            signal_key = (event.code, event.pattern)
            count = self._signal_counts.get(signal_key, 0) + 1
            self._signal_counts[signal_key] = count
            
            # [NEW] 持久化到数据库
            self._save_signal_count(event.code, event.pattern, count)
            
            msg = f"[{time_str}] {event.code} {event.name} {pattern_cn} @ {event.price:.2f} (第{count}次)"
            
            # 发射信号日志 (仅在数据有效且由于 update 触发后产生)
            try:
                self.signal_log.emit(event.code, event.name, event.pattern, msg)
            except Exception as e_emit:
                logger.error(f"❌ Signal emit failed: {e_emit}")
            
            # ⭐ 语音通知优化
            import time as _time
            now = _time.time()
            
            should_play_prefix = False
            
            if count == 1:
                # 首次触发：只做时间冷却检查 (60秒)
                # 忽略BatchFlag，防止因数据刷新过快导致的重复播报
                time_diff = now - self._last_voice_prefix_time
                if time_diff > 60:
                    should_play_prefix = True
                    self._last_voice_prefix_time = now # 更新全局冷却
                
                prefix = "热点信息 " if should_play_prefix else ""
                voice_msg = f"{prefix}{event.name} {pattern_cn}"
            else:
                # 重复触发：简短播报
                voice_msg = f"{event.name} {pattern_cn} 第{count}次"
            
            self._notify_voice(event.code, voice_msg)
            
            logger.warning(f"🔥 热点信号: {msg}")
        except Exception as e:
            logger.error(f"Signal callback error: {e}")

    # ================== 拖动支持 ==================
    def mousePressEvent(self, event):
        """记录拖动起始位置"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在标题栏区域
            if hasattr(self, 'header') and self.header.geometry().contains(event.pos()):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.header.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
            else:
                self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """处理拖动"""
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """结束拖动"""
        if self._drag_pos is not None:
            self._drag_pos = None
            if hasattr(self, 'header'):
                self.header.setCursor(Qt.CursorShape.OpenHandCursor)
            # self._save_position()  # Old
            # self.save_window_position_qt_visual(self, "hotlist_panel") # New Unified
        super().mouseReleaseEvent(event)

    # ================== 位置保存/加载 (Unified Mixin) ==================
    # Removed custom _get_config_path, _save_position, _load_position

    def showEvent(self, event):
        """首次显示时加载位置"""
        if not hasattr(self, '_pos_loaded'):
            self._pos_loaded = True
            # [REFACTOR] Use Unified Loader
            self.load_window_position_qt(self, "hotlist_panel", default_width=280, default_height=400)
        super().showEvent(event)

    def hideEvent(self, event):
        """隐藏时保存位置"""
        # self.save_window_position_qt_visual(self, "hotlist_panel")
        super().hideEvent(event)


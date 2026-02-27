# -*- coding: utf-8 -*-
"""
HotlistPanel - 热点自选面板
支持快捷添加、盈亏跟踪、弹出详情窗口

数据持久化：signal_strategy.db (follow_record 表)
"""
import os
import sys
import sqlite3
import time
import re
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass
import pandas as pd
from JohnsonUtil import LoggerFactory
from JohnsonUtil.commonTips import timed_ctx, print_timing_summary

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView, QMenu,
    QFrame, QTabWidget, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QPoint
from PyQt6.QtGui import QColor, QAction
from PyQt6 import QtGui

# [NEW] Move to top for performance and linting
import math as _math

def _safe_num(val, default=0, as_int=False):
    """安全数值转换，NaN / None / 非法值 统一降级为 default"""
    try:
        if val is None:
            return int(default) if as_int else float(default)
        f = float(val)
        if _math.isnan(f) or _math.isinf(f):
            return int(default) if as_int else float(default)
        return int(f) if as_int else f
    except (ValueError, TypeError):
        return int(default) if as_int else float(default)

# [FIX] 增强的 NumericTableWidgetItem，支持正确排序 (避免 -9 vs -35 错误)
class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格单元格项"""
    def __init__(self, value, sort_value=None):
        # [NEW] 统一处理显示逻辑：如果是浮点数，强制保留2位
        if isinstance(value, float):
            display_text = f"{value:.2f}"
        else:
            display_text = str(value)
            
        super().__init__(display_text)
        
        if sort_value is not None:
            self.sort_value = sort_value
        elif isinstance(value, (int, float)):
            self.sort_value = value
        else:
            # 尝试从字符串中提取数值 (例如 "+9.00%")
            try:
                clean_val = display_text.replace('%', '').replace('+', '').replace(',', '').strip()
                if not clean_val or clean_val == '-':
                    self.sort_value = -999999.0
                else:
                    self.sort_value = float(clean_val)
            except (ValueError, TypeError):
                self.sort_value = display_text

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        
        self_val = getattr(self, 'sort_value', None)
        other_val = getattr(other, 'sort_value', None)
                
        if self_val is not None and other_val is not None:
            try:
                if type(self_val) == type(other_val):
                    return self_val < other_val
                return float(self_val) < float(other_val)
            except:
                pass
        
        return super().__lt__(other)

try:
    from trading_hub import get_trading_hub, TrackedSignal
except ImportError:
    get_trading_hub = None
    TrackedSignal = None

# 日内形态检测器
has_detector_imported = False
try:
    from intraday_pattern_detector import IntradayPatternDetector, PatternEvent
    has_detector_imported = True
except ImportError:
    IntradayPatternDetector = None
    PatternEvent = None


# [REFACTOR] WindowMixin Imports
from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
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
    # [NEW] 信号：(watchlist_df, error_msg)
    watchlist_ready = pyqtSignal(object, str)
    
    def __init__(self, interval: float = 2.0, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.interval = interval
        self._running = True
    
    def run(self):
        if get_trading_hub is None:
            return
        
        while self._running:
            try:
                # 1. 拉取数据
                hub = get_trading_hub()
                df_follow = hub.get_follow_queue_df()
                
                df_watchlist = pd.DataFrame()
                if hasattr(hub, 'get_watchlist_df'):
                    df_watchlist = hub.get_watchlist_df()
                
                # [NEW] 在后台线程中补全板块信息, 避免 UI 卡死
                if not df_watchlist.empty:
                    self._augment_watchlist_sectors(df_watchlist)

                # 2. 发送数据 (不要在线程里操作 UI)
                self.data_ready.emit(df_follow, "")
                if not df_watchlist.empty:
                    self.watchlist_ready.emit(df_watchlist, "")
                
            except Exception as e:
                logger.error(f"HotlistWorker error: {e}")
                self.data_ready.emit(None, str(e))
                self.watchlist_ready.emit(None, str(e))
                
            # 简单的休眠
            for _ in range(int(self.interval * 10)):
                if not self._running: break
                time.sleep(0.1)

    def _augment_watchlist_sectors(self, df):
        """后台纯内存补全板块信息, 不持久化写数据库 (最高效安全)"""
        try:
            # 1. 获取最近热点板块映射 (从本地概念库概念映射)
            hot_concepts_map = {}
            db_path = "./concept_pg_data.db"
            if os.path.exists(db_path):
                try:
                    mgr = SQLiteConnectionManager.get_instance(db_path)
                    conn = mgr.get_connection()
                    c = conn.cursor()
                    # [NEW] 扩大扫描范围 (最近 60 条记录，覆盖约 5-10 日热点)
                    c.execute("SELECT concept_name, code_list FROM concept_data ORDER BY date DESC LIMIT 60")
                    for name, raw_list in c.fetchall():
                        if not raw_list: continue
                        # 清理并拆分代码列表
                        clean_list = raw_list.replace('[','').replace(']','').replace("'",'').replace('"','').split(',')
                        for code in clean_list:
                            code = code.strip()
                            if code and code not in hot_concepts_map:
                                hot_concepts_map[code] = str(name)[:20]
                except: pass

            # 2. 内存合并: 补全 DataFrame (不写回数据库, 仅用于 UI 显示)
            if not df.empty:
                # 确保 sector 列存在
                if 'sector' not in df.columns:
                    df['sector'] = ""

                def get_fast_sector(row):
                    # 优先使用数据库已有的板块 (排除 None/nan)
                    exist = str(getattr(row, 'sector', '')).strip()
                    if exist and exist.lower() not in ('', 'none', 'nan'): 
                        return exist
                    # 否则从内存映射表中查找
                    return hot_concepts_map.get(str(row.code), "")
                
                df['sector'] = df.apply(get_fast_sector, axis=1)
                
        except Exception as e:
            logger.error(f"Memory augment sectors error: {e}")

    def stop(self):
        """停止工作线程"""
        self._running = False
        # 等待最多 2 秒让线程自然退出
        if not self.wait(2000):
            # 如果超时,强制终止
            logger.warning("HotlistWorker did not stop gracefully, terminating...")
            self.terminate()
            self.wait(500)


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
    signal_log = pyqtSignal(str, str, str, str, bool)  # code, name, pattern, message, is_high_priority - 信号日志
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # [REFACTOR] Mixin Init
        self.scale_factor = get_windows_dpi_scale_factor()
        self.initial_x = 0
        self.initial_y = 0
        self.initial_w = 280
        self.initial_h = 400
        self.items: list[HotlistItem] = []
        self._drag_pos: Optional[QPoint] = None
        self.voice_enabled = True  # 是否启用语音通知
        self._voice_paused = False  # 语音播报状态
        self._is_refreshing = False # 刷新状态标识，防止信号干扰
        self._last_follow_fingerprint = ""
        self.follow_count = 0  # [NEW] Track follow queue count
        self._last_price_map: dict[str, float] = {} # [NEW] Cache real-time prices for both Hotlist and Follow Queue
        self._last_df_follow: Optional[pd.DataFrame] = None # [NEW] Cache follow queue data for PnL updates
        self._last_df_watchlist: Optional[pd.DataFrame] = None # [NEW] Cache watchlist data
        self._last_sector_map: dict[str, str] = {} # [NEW] Cache sector info for watchlist
        self._last_watchlist_fingerprint: str = "" # [NEW] Watchlist data fingerprint for change detection
        self._connection_warning_logged = False  # [NEW] Log throttle flag
        self._pos_loaded: bool = False
        self._main_window_cache = None # [NEW] Cache for main window reference
        
        # --- 数据流管理 ---
        # 数据流校验缓存：{code: (price, volume, amount)}
        self._last_data_sigs: dict[str, tuple[float, float, float]] = {}
        
        # 语音前缀播放控制
        self._last_voice_prefix_time: float = 0.0  # 全局冷却计时
        self._batch_spoken_flag: bool = False      # 单批次互斥锁
        
        # 信号计数统计：{(code, pattern): count} —— 当天重复信号计数
        self._signal_counts: dict[tuple[str, str], int] = {}
        
        # 日期控制
        self._last_reset_date = datetime.now().date()
        
        # [NEW] 窗口缩放状态
        self._is_enlarged = False
        self._pre_enlarge_geometry = None
        
        # [NEW] 联动去重缓存：{table_name: last_code}
        self._last_selected_codes: dict[str, str] = {
            "hotlist": "",
            "follow": "",
            "watchlist": ""
        }
        
        # [NEW] 热门板块缓存
        self._recent_hot_concepts_cache: set[str] = set()
        self._last_hot_concepts_sync = 0.0
        
        # [MODIFIED] 移除 QTimer，改用 Worker
        self.data_worker = HotlistWorker(interval=1.0, parent=self)
        self.data_worker.data_ready.connect(self._on_worker_data)
        self.data_worker.watchlist_ready.connect(self._on_watchlist_data)
        
        # UI 属性定义 (用于类型提示)
        self.table: QTableWidget = None # type: ignore
        self.follow_table: QTableWidget = None # type: ignore
        self.hotlist_widget: QWidget = None # type: ignore
        self.follow_widget: QWidget = None # type: ignore
        self.status_label: QLabel = None # type: ignore
        self.pause_voice_btn: QPushButton = None # type: ignore
        self._sync_timer: QTimer = None # type: ignore
        self.tabs: QTabWidget = None # type: ignore
        self.watchlist_table: QTableWidget = None # type: ignore
        self.header: QFrame = None # type: ignore
        
        # 设置为浮动工具窗口（可调整大小）
        self.setWindowFlags(
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowTitle("🔥 热点自选")
        
        # 可调整大小范围
        self.setMinimumWidth(520)   # [FIX] 提高最小宽度，防止名称列被挤压
        self.setMinimumHeight(250)
        self.resize(580, 400)      # [OPTIMIZE] Wider default size
        
        self._init_db()
        # [NEW] Initialize UI first, then apply theme
        self._init_ui()
        self.apply_theme(is_dark=True) # Default to Dark Theme
        self._load_from_db()
        # [NEW] 加载信号计数（从数据库）
        self._load_signal_counts()

    def apply_theme(self, is_dark: bool):
        """应用主题 (支持深/浅色切换)"""
        if is_dark:
            bg_main = "#1e1e1e"
            color_text = "#ddd"
            header_bg = "#2d2d2d"
            border_color = "#555"
            tab_bg = "#1e1e1e"
            tab_selected_bg = "#1e1e1e"
            tab_selected_text = "#FFD700"
            tab_hover_bg = "#333"
            header_text = "#FFD700"
            item_selected = "rgba(255, 215, 0, 80)"
            item_selected_text = "white"
        else:
            bg_main = "#f2faff"
            color_text = "#000000"
            header_bg = "#eef7ff"
            border_color = "#b3d7ff"
            tab_bg = "#eef7ff"
            tab_selected_bg = "#eef7ff"
            tab_selected_text = "#000000"
            tab_hover_bg = "#dbeeff"
            header_text = "#333"
            item_selected = "#cce8ff"
            item_selected_text = "black"

        # 1. 主窗口样式
        self.setStyleSheet(f"""
            HotlistPanel {{
                background-color: {bg_main};
                border: 1px solid {border_color};
                border-radius: 4px;
            }}
        """)
        
        # 2. 标题栏样式
        if hasattr(self, 'header'):
            self.header.setStyleSheet(f"""
                QFrame {{
                    background-color: {header_bg};
                    border-bottom: 1px solid {border_color};
                    border-top-left-radius: 3px;
                    border-top-right-radius: 3px;
                }}
                QLabel {{
                    color: {header_text};
                    font-weight: bold;
                    font-size: 10pt;
                }}
                QPushButton {{
                    background-color: transparent;
                    color: #888;
                    border: none;
                    font-size: 9pt;
                    padding: 2px 6px;
                }}
                QPushButton:hover {{
                    color: #FFD700;
                }}
            """)
            
        # 3. TabWidget 样式
        if hasattr(self, 'tabs'):
            self.tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {border_color};
                    background-color: {bg_main};
                    top: -1px;
                }}
                QWidget#hotlist_container, QWidget#follow_container {{
                    background-color: {bg_main};
                }}
                QTabBar::tab {{
                    background: {header_bg};
                    color: #888;
                    padding: 6px 12px;
                    border: 1px solid {border_color};
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    margin-right: 2px;
                }}
                QTabBar::tab:selected {{
                    background: {tab_selected_bg};
                    color: {tab_selected_text};
                    border-bottom: 2px solid #FFD700;
                    font-weight: bold;
                }}
                QTabBar::tab:hover {{
                    background: {tab_hover_bg};
                }}
            """)

        # 4. 表格样式 (Apply to both tables if they exist)
        table_style = f"""
            QTableWidget {{
                background-color: {bg_main};
                color: {color_text};
                border: none;
                font-size: 10pt;
                gridline-color: {border_color if is_dark else '#ddd'};
            }}
            QTableWidget::item {{
                padding: 1px 3px;
            }}
            QTableWidget::item:hover {{
                background: rgba(255, 255, 255, 20);
            }}
            QTableWidget::item:selected {{
                background: {item_selected};
                color: {item_selected_text};
                font-weight: bold;
            }}
            QHeaderView {{
                background-color: {header_bg};
                border: none;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: #aaa;
                border: none;
                padding: 2px 4px;
                font-size: 9pt;
            }}
            QTableCornerButton::section {{
                background-color: {header_bg};
                border: none;
            }}
            QAbstractScrollArea::corner, QScrollBar::corner {{
                background: {bg_main};
                border: none;
            }}
            
            /* Scrollbars */
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(180, 180, 180, 100);
                min-height: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(220, 220, 220, 150);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                height: 6px;
                background: transparent;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(180, 180, 180, 100);
                min-width: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: rgba(220, 220, 220, 150);
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
        """
        
        if hasattr(self, 'table') and self.table:
            self.table.setStyleSheet(table_style)
        if hasattr(self, 'follow_table') and self.follow_table:
            self.follow_table.setStyleSheet(table_style)
        if hasattr(self, 'watchlist_table') and self.watchlist_table:
            self.watchlist_table.setStyleSheet(table_style)
    
    def showEvent(self, a0: Optional[QtGui.QShowEvent]):
        """窗口显示时：加载位置并开启工作线程"""
        super().showEvent(a0)
        
        # 1. 首次显示时加载位置
        if not getattr(self, '_pos_loaded', False):
            self._pos_loaded = True
            # [REFACTOR] Use Unified Loader
            self.load_window_position_qt(self, "HotlistPanel", default_width=280, default_height=400)
            
        # 2. 确保工作线程运行 (Lazy Start)
        if not self.data_worker.isRunning():
            self.data_worker.start()
    
    def closeEvent(self, event):
        """窗口关闭事件：保存位置"""
        try:
            # [REFACTOR] 使用 Mixin 保存位置
            self.save_window_position_qt(self, "HotlistPanel")
            
            # 停止线程
            if hasattr(self, 'data_worker'):
                self.data_worker.stop()
        except:
            pass
        super().closeEvent(event)
        if hasattr(self, 'data_worker') and self.data_worker and self.data_worker.isRunning():
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
        
        # 1. 标题栏
        self.header = QFrame()
        self.header.setFixedHeight(28)
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        
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
        close_btn.setStyleSheet("QPushButton:hover { color: #ff6b6b; }") # Keep hover color specific
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(self.header)
        
        # 2. TabWidget
        self.tabs = QTabWidget()
        
        # Tab 1: Hotlist
        self.hotlist_widget = QWidget()
        self.hotlist_widget.setObjectName("hotlist_container")
        self._init_hotlist_ui()
        self.tabs.addTab(self.hotlist_widget, "🔥 Hotlist")
        
        # Tab 2: Follow Queue
        self.follow_widget = QWidget()
        self.follow_widget.setObjectName("follow_container")
        self._init_follow_queue_ui()
        self.tabs.addTab(self.follow_widget, "🎯 Follow")
        
        # Tab 3: Watchlist (Heat)
        self.watchlist_widget = QWidget()
        self.watchlist_widget.setObjectName("watchlist_container")
        self._init_watchlist_ui()
        self.tabs.addTab(self.watchlist_widget, "📊 Watch")
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        
        # 3. 状态栏
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
        self.pause_voice_btn.clicked.connect(self.toggle_voice)
        self._update_voice_button_style() # Use existing update logic
        
        status_bar.addWidget(self.pause_voice_btn)
        # [NEW] 信号连接
        self.data_worker.data_ready.connect(self._on_worker_data)
        self.data_worker.watchlist_ready.connect(self._on_watchlist_data)
        
        # 定时刷新 PnL (仅 UI 更新,数据由 worker 提供)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_pnl)
        self.refresh_timer.start(2000)

        layout.addLayout(status_bar)
        
        # [NEW] 定时器同步 UI 状态 (如果外部改变了语音状态)
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_voice_ui)
        self._sync_timer.start(1000)

    def _sync_voice_ui(self):
        """同步语音按钮状态"""
        main_window = self._find_main_window()
        if main_window and hasattr(main_window, 'voice_thread'):
            vt = main_window.voice_thread
            # 如果处于暂停状态
            is_paused = not vt.pause_event.is_set()
            if self._voice_paused != is_paused:
                self._voice_paused = is_paused
                self._update_voice_button_style()

    def _find_main_window(self):
        """寻找主窗口实例 (带缓存)"""
        if self._main_window_cache and self._main_window_cache.isVisible():
            return self._main_window_cache
        try:
            from PyQt6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'df_all') and (widget.__class__.__name__ == 'MainWindow' or "Visualizer" in str(widget.windowTitle())):
                    self._main_window_cache = widget
                    return widget
        except:
            pass
        return None
    
    def toggle_voice(self):
        """切换语音播报：暂停/恢复 (仅 Hotlist 面板行为)"""
        main_window = self._find_main_window()
        if not main_window or not hasattr(main_window, 'voice_thread'):
            return

        self._voice_paused = not self._voice_paused
        # [FIX] 同步到主窗口标志位
        main_window._voice_paused = self._voice_paused
        
        if self._voice_paused:
            main_window.voice_thread.pause()

            logger.info("⏸ Voice paused via HotlistPanel")
        else:
            main_window.voice_thread.resume()
            logger.info("▶ Voice resumed via HotlistPanel")
            
        self._update_voice_button_style()

    def _update_voice_button_style(self):
        """更新语音按钮样式"""
        if self._voice_paused:
            self.pause_voice_btn.setText("▶")
            self.pause_voice_btn.setToolTip("恢复播报")
            self.pause_voice_btn.setStyleSheet("""
                QPushButton {
                    background: #600;
                    border: 1px solid #f00;
                    border-radius: 3px;
                    color: white;
                    font-size: 10pt;
                }
            """)
        else:
            self.pause_voice_btn.setText("⏸")
            self.pause_voice_btn.setToolTip("暂停播报")
            self.pause_voice_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid #444;
                    border-radius: 3px;
                    color: #FFD700;
                    font-size: 10pt;
                }
            """)

    def _init_hotlist_ui(self):
        """初始化热点列表 UI (Tab 1 content)"""
        layout = QVBoxLayout(self.hotlist_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["序号", "代码", "名称", "加入价", "现价", "盈亏%", "分组", "时间", "信号类型"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        
        # [NEW] 添加键盘导航联动
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        
        # [NEW] 显式点击去重 (由 itemClicked 统一触发 _on_click)
        self.table.itemClicked.connect(self._on_item_clicked_simple)
        
        # 表头设置
        h_header = self.table.horizontalHeader()
        if h_header:
            h_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            # [FIX] 名称列不再强制 Stretch 避免宽度过小时被压缩导致不显示
            h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setMinimumSectionSize(40) # 基础最小宽度
            self.table.setColumnWidth(2, 80)    # 默认给一个宽度
            h_header.setStretchLastSection(True) # 最后一列拉伸填充
        
        self.table.setSortingEnabled(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.verticalHeader().setVisible(False)
        
        # [NEW] 支持滚轮横向滚动
        self.table.wheelEvent = self._on_table_wheel_event
        setattr(self.table, '_original_wheel_event', QTableWidget.wheelEvent)
        # [NEW] Del 键删除选中行
        self.table.keyPressEvent = self._on_hotlist_key_press
        
        layout.addWidget(self.table)

    def _init_follow_queue_ui(self):
        """初始化跟单队列 UI (Tab 2 content)"""
        layout = QVBoxLayout(self.follow_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.follow_table = QTableWidget()
        cols = ["序号", "状态", "代码", "名称", "现价", "盈亏%", "信号", "入场", "时间", "理由"] 
        self.follow_table.setColumnCount(len(cols))
        self.follow_table.setHorizontalHeaderLabels(cols)
        self.follow_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.follow_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.follow_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.follow_table.customContextMenuRequested.connect(self._on_follow_context_menu)
        # [FIX] Add keyboard navigation support
        self.follow_table.currentCellChanged.connect(self._on_follow_cell_changed)
        # [NEW] Del 键删除选中行
        self.follow_table.keyPressEvent = self._on_follow_key_press
        
        hf = self.follow_table.horizontalHeader()
        if hf:
            hf.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            # [FIX] 名称列不再使用 Stretch 模式进行强行压缩，确保完整显示
            hf.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.follow_table.setColumnWidth(3, 80)
            hf.setStretchLastSection(True) # [FIX] 填充空白
        
        self.follow_table.setSortingEnabled(True) # [FIX] 启用排序
        
        self.follow_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded) 
        # [NEW] 支持滚轮横向滚动
        self.follow_table.wheelEvent = self._on_follow_wheel_event
        setattr(self.follow_table, '_original_wheel_event', QTableWidget.wheelEvent)

        self.follow_table.verticalHeader().setVisible(False)
        hf.setStyleSheet(self.table.styleSheet()) # Reuse style
        
        layout.addWidget(self.follow_table)

    def _init_watchlist_ui(self):
        """初始化观察池 UI (Tab 3 content)"""
        layout = QVBoxLayout(self.watchlist_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.watchlist_table = QTableWidget()
        # 列定义: 序号, 状态, 代码, 名称, 板块, 发现价, 现价, 盈亏%, 趋势, 量能, 连阳, 形态分, 发现日期, 形态描述, 来源
        cols = ["序号", "状态", "代码", "名称", "板块", "发现价", "现价", "盈亏%", "趋势", "量能", "连阳", "形态分", "发现日期", "形态描述", "来源"] 
        self.watchlist_table.setColumnCount(len(cols))
        self.watchlist_table.setHorizontalHeaderLabels(cols)
        self.watchlist_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.watchlist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.watchlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.watchlist_table.customContextMenuRequested.connect(self._on_watchlist_context_menu)
        self.watchlist_table.cellDoubleClicked.connect(self._on_watchlist_double_click)
        self.watchlist_table.currentCellChanged.connect(self._on_watchlist_cell_changed)
        
        hw = self.watchlist_table.horizontalHeader()
        if hw:
            hw.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            # [FIX] 名称列显示不全修正
            hw.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.watchlist_table.setColumnWidth(3, 80)
            hw.setStretchLastSection(True)
        
        self.watchlist_table.setSortingEnabled(True)
        self.watchlist_table.verticalHeader().setVisible(False)
        self.watchlist_table.setStyleSheet(self.table.styleSheet())
        
        # [NEW] 支持滚轮横向滚动
        self.watchlist_table.wheelEvent = self._on_watchlist_wheel_event
        setattr(self.watchlist_table, '_original_wheel_event', QTableWidget.wheelEvent)
        # [NEW] Del 键删除选中行
        self.watchlist_table.keyPressEvent = self._on_watchlist_key_press
        
        layout.addWidget(self.watchlist_table)

    def _update_item(self, table, row, col, value, sort_value=None, foreground=None):
        """[HIGH-PERFORMANCE] 复用 Item，避免频繁销毁创建对象导致 UI 卡死"""
        item = table.item(row, col)
        
        # 处理显示文本 (NaN 保护)
        if isinstance(value, float):
            if _math.isnan(value) or _math.isinf(value):
                value = 0.0
            display_text = f"{value:.2f}"
        else:
            display_text = str(value)

        # 降级：如果原有 Item 类型不匹配（比如原本是普通 Item 现在要 Numeric），则重建
        if item and (isinstance(value, (int, float)) or sort_value is not None):
            if not isinstance(item, NumericTableWidgetItem):
                item = None

        if not item:
            # 创建新 Item
            if isinstance(value, (int, float)) or sort_value is not None:
                item = NumericTableWidgetItem(value, sort_value=sort_value)
            else:
                item = QTableWidgetItem(display_text)
            table.setItem(row, col, item)
        else:
            # 复用并更新
            if item.text() != display_text:
                item.setText(display_text)
            if sort_value is not None:
                item.sort_value = sort_value # type: ignore
        
        # 统一设置对齐和颜色
        if isinstance(value, (int, float)):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
        if foreground:
            item.setForeground(foreground)
        else:
            # 恢复默认颜色，防止复用时颜色污染
            item.setForeground(QtGui.QBrush())
        return item

    def _on_watchlist_data(self, df_watchlist: Optional[pd.DataFrame], error_msg: str):
        """Watchlist 数据回调"""
        if error_msg or df_watchlist is None or df_watchlist.empty:
            if df_watchlist is not None and df_watchlist.empty:
                if hasattr(self, 'watchlist_table'): self.watchlist_table.setRowCount(0)
            return

        # [NEW] 强势股跟随过滤：仅保留前 30 个，按趋势分和连强分排序
        sort_cols = []
        if 'trend_score' in df_watchlist.columns: sort_cols.append('trend_score')
        if 'consecutive_strong' in df_watchlist.columns: sort_cols.append('consecutive_strong')
        
        if sort_cols:
            df_watchlist = df_watchlist.sort_values(by=sort_cols, ascending=False).head(100)
        else:
            df_watchlist = df_watchlist.head(100)
        
        # [OPTIMIZE] 数据指纹检查,避免频繁全量刷新
        codes = sorted(df_watchlist['code'].astype(str).tolist())
        statuses = df_watchlist['validation_status'].tolist() if 'validation_status' in df_watchlist.columns else []
        new_fingerprint = f"{len(codes)}:{','.join(codes[:5])}:{','.join(map(str, statuses[:5]))}"
        
        old_fingerprint = getattr(self, '_last_watchlist_fingerprint', '')
        needs_full_rebuild = (new_fingerprint != old_fingerprint)
        
        self._last_df_watchlist = df_watchlist
        self._last_watchlist_fingerprint = new_fingerprint
        
        # [OPTIMIZE] Only update UI if Watchlist tab is visible
        if hasattr(self, 'tabs') and self.tabs.currentIndex() == 2:
            if needs_full_rebuild:
                # 数据结构变化,全量重绘
                self._update_watchlist_queue(df_watchlist)
            else:
                # 仅数据值变化,轻量级更新
                self._update_watchlist_prices_only()
        self._update_status_bar()

    def _update_watchlist_queue(self, df=None):
        """刷新观察池可视化 (智能增量渲染)"""
        with timed_ctx("update_watchlist", warn_ms=100):
            try:
                if df is None:
                    df = getattr(self, '_last_df_watchlist', None)
                if df is None or df.empty:
                    if hasattr(self, 'watchlist_table'): self.watchlist_table.setRowCount(0)
                    return

                # --- 准备更新 ---
                self.watchlist_table.blockSignals(True)
                is_sorted = self.watchlist_table.isSortingEnabled()
                if is_sorted:
                    _ = self.watchlist_table.setSortingEnabled(False)
            
                try:
                    # [OPTIMIZE] 直接全量基于 _update_item，它内部会自动复用和最小化更新
                    if self.watchlist_table.rowCount() != len(df):
                        self.watchlist_table.setRowCount(len(df))
                    
                    self.watchlist_table.setUpdatesEnabled(False)
                    needs_full_rebuild_dummy = False 
                    
                    # 只有数据量较大且当前没有选中的情况下才临时关闭渲染
                    self.watchlist_table.setUpdatesEnabled(False)
                    v_scroll = self.watchlist_table.verticalScrollBar().value()
                    current_code = None
                    curr_row = self.watchlist_table.currentRow()
                    if curr_row >= 0:
                        if (it := self.watchlist_table.item(curr_row, 2)):
                            current_code = it.text()
                    
                    for i, row in enumerate(df.itertuples()):
                        # 0. 序号
                        self._update_item(self.watchlist_table, i, 0, i+1)
                        
                        code_str = str(row.code)
                        status = str(getattr(row, 'validation_status', ''))
                        color = QColor('#00FF00') if status == 'VALIDATED' else (QColor('#FFD700') if status == 'WATCHING' else None)
                        self._update_item(self.watchlist_table, i, 1, status, foreground=color)
                        
                        it_code = self._update_item(self.watchlist_table, i, 2, code_str)
                        # 存入发现日期,用于 K 线图标记
                        d_date = str(getattr(row, 'discover_date', ''))
                        if len(d_date) > 10: d_date = d_date[:10]
                        it_code.setData(Qt.ItemDataRole.UserRole, d_date)
                        
                        self._update_item(self.watchlist_table, i, 3, str(row.name))
                        
                        # [OPTIMIZE] 增强板块显示 fallback: 数据库 -> 内存缓存
                        sector = str(getattr(row, 'sector', '')).strip()
                        if not sector or sector.lower() in ('none', 'nan', ''):
                            if hasattr(self, '_last_sector_map') and code_str in self._last_sector_map:
                                sector = self._last_sector_map[code_str]
                                
                        self._update_item(self.watchlist_table, i, 4, sector[:20] if sector else "")
                        
                        discover_price = _safe_num(getattr(row, 'discover_price', 0.0))
                        self._update_item(self.watchlist_table, i, 5, discover_price)
                        
                        curr_price = 0.0
                        if hasattr(self, '_last_price_map') and code_str in self._last_price_map:
                            curr_price = self._last_price_map[code_str]
                        
                        self._update_item(self.watchlist_table, i, 6, curr_price if curr_price > 0 else "-", sort_value=curr_price)
                        
                        # 盈亏%
                        pnl_pct = (curr_price - discover_price) / discover_price * 100 if discover_price > 0 and curr_price > 0 else 0.0
                        pnl_txt = f"{pnl_pct:+.2f}%" if curr_price > 0 else "-"
                        pnl_color = QColor(220, 80, 80) if pnl_pct > 0 else (QColor(80, 200, 120) if pnl_pct < 0 else None)
                        self._update_item(self.watchlist_table, i, 7, pnl_txt, sort_value=pnl_pct if curr_price > 0 else -999.0, foreground=pnl_color)
                        
                        self._update_item(self.watchlist_table, i, 8, _safe_num(getattr(row, 'trend_score', 0)))
                        self._update_item(self.watchlist_table, i, 9, _safe_num(getattr(row, 'volume_score', 0)))
                        self._update_item(self.watchlist_table, i, 10, _safe_num(getattr(row, 'consecutive_strong', 0), as_int=True))
                        self._update_item(self.watchlist_table, i, 11, _safe_num(getattr(row, 'pattern_score', 0)))
                        
                        self._update_item(self.watchlist_table, i, 12, str(getattr(row, 'discover_date', '') or ""))
                        
                        pat_desc = str(getattr(row, 'daily_patterns', "") or "").strip()
                        display_pat = pat_desc[:20] + "..." if len(pat_desc) > 20 else pat_desc
                        it_pat = self._update_item(self.watchlist_table, i, 13, display_pat)
                        it_pat.setToolTip(pat_desc)
                        
                        self._update_item(self.watchlist_table, i, 14, str(getattr(row, 'source', "") or ""))

                    # 恢复状态
                    if current_code:
                        for r in range(self.watchlist_table.rowCount()):
                            it = self.watchlist_table.item(r, 2)
                            if it and it.text() == current_code:
                                self.watchlist_table.setCurrentCell(r, 2)
                                break
                    
                    self.watchlist_table.verticalScrollBar().setValue(v_scroll)
                finally:
                    # 只有在明确锁定的情况下才恢复, 且必须恢复
                    self.watchlist_table.setUpdatesEnabled(True)
                    self.watchlist_table.blockSignals(False)
                    
                    if is_sorted:
                        _ = self.watchlist_table.setSortingEnabled(True)
                    
                    # [OPTIMIZE] 移除 resizeColumnsToContents(), 这是卡死的罪魁祸首!
                    # 实时刷新时不应频繁进行重排版几何计算
                    
            except Exception as e:
                logger.error(f"Update watchlist UI error: {e}")

    def _get_recent_hot_concepts(self, days=2) -> set[str]:
        """获取最近几天的热门板块列表 (带缓存)"""
        now = time.time()
        if now - self._last_hot_concepts_sync < 60 and self._recent_hot_concepts_cache:
            return self._recent_hot_concepts_cache
            
        concepts = set()
        try:
            db_path = "./concept_pg_data.db"
            if not os.path.exists(db_path):
                return concepts
                
            mgr = SQLiteConnectionManager.get_instance(db_path)
            conn = mgr.get_connection()
            c = conn.cursor()
            
            # 获取最近几天的日期列表
            c.execute("SELECT DISTINCT date FROM concept_data ORDER BY date DESC LIMIT ?", (days,))
            recent_dates = [r[0] for r in c.fetchall()]
            
            if recent_dates:
                placeholders = ','.join(['?'] * len(recent_dates))
                c.execute(f"SELECT DISTINCT concept_name FROM concept_data WHERE date IN ({placeholders})", recent_dates)
                for r in c.fetchall():
                    concepts.add(str(r[0]))
            
            self._recent_hot_concepts_cache = concepts
            self._last_hot_concepts_sync = now
        except Exception as e:
            logger.error(f"Error fetching recent hot concepts: {e}")
        return concepts

    def _on_watchlist_click(self, row, col):
        if row < 0: return
        with timed_ctx("watchlist_click", warn_ms=100):
            try:
                code_item = self.watchlist_table.item(row, 2)
                name_item = self.watchlist_table.item(row, 3)
                if code_item and name_item:
                    code = code_item.text()
                    discover_date = code_item.data(Qt.ItemDataRole.UserRole) or ""
                    # [DEBUNCE] 增加去重逻辑
                    if self._last_selected_codes["watchlist"] != code:
                        self._last_selected_codes["watchlist"] = code
                        # 发送附带发现日期的信号
                        sig_str = f"{code}|realtime=false|signal_type=watchlist"
                        if discover_date:
                            sig_str += f"|signal_date={discover_date}"
                        self.stock_selected.emit(sig_str, name_item.text())
            except: pass

    def _on_watchlist_double_click(self, row, col):
        if row < 0: return
        with timed_ctx("watchlist_double_click", warn_ms=2000):
            try:
                code_item = self.watchlist_table.item(row, 2)
                name_item = self.watchlist_table.item(row, 3)
                if code_item and name_item:
                    code = code_item.text()
                    # 双击通常伴随强关联，直接记录并发送
                    self._last_selected_codes["watchlist"] = code
                    self.item_double_clicked.emit(f"{code}|realtime=false", name_item.text(), 0.0)
            except: pass

    def _on_watchlist_cell_changed(self, row, col, pr, pc):
        """Watchlist 选中单元格改变回调"""
        if not getattr(self, '_is_refreshing', False):
            self._on_watchlist_click(row, col)

    def _on_watchlist_context_menu(self, pos):
        row = self.watchlist_table.currentRow()
        if row < 0: return
        code = self.watchlist_table.item(row, 2).text()
        
        menu = QMenu(self)
        menu.addAction("🔍 查看详情", lambda: self._on_watchlist_double_click(row, 2))
        
        # [NEW] 从观察池直接晋升至跟单
        name = self.watchlist_table.item(row, 3).text()
        price = 0.0
        if (it := self.watchlist_table.item(row, 6)): # 现价列
            try: price = float(it.text())
            except: pass
        if price <= 0:
            if (it := self.watchlist_table.item(row, 5)): # 发现价列
                try: price = float(it.text())
                except: pass
        
        menu.addAction("🎯 加入跟单队列", lambda: self._add_to_follow_queue(code, name, price, "观察池晋升"))
        menu.addSeparator()
        menu.addAction("🗑️ 从观察池移除", lambda: self._remove_from_watchlist(code))
        menu.exec(self.watchlist_table.mapToGlobal(pos))

    def _remove_from_watchlist(self, code):
        try:
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("UPDATE hot_stock_watchlist SET validation_status='DROPPED' WHERE code=?", (code,))
            conn.commit()
            logger.info(f"Removed {code} from watchlist")
            self._update_watchlist_queue()
        except Exception as e:
            logger.error(f"Remove from watchlist error: {e}")

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
        self._is_refreshing = True
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        
        # [FIX] 保存选中项和滚动条
        current_code = None
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            it = self.table.item(curr_row, 1) # Code col (index shifted to 1)
            if it: current_code = it.text()
            
        v_scroll = self.table.verticalScrollBar().value()
        
        if self.table.rowCount() != len(self.items):
            self.table.setRowCount(len(self.items))
        
        for row, item in enumerate(self.items):
            # 序号 (No.)
            self._update_item(self.table, row, 0, row + 1)
            
            # 代码 (Col 1)
            self._update_item(self.table, row, 1, item.code)
            
            # 名称 (Col 2)
            self._update_item(self.table, row, 2, item.name)
            
            # 加入价 (Col 3)
            self._update_item(self.table, row, 3, item.add_price)
            
            # 现价 (Col 4)
            sort_price = item.current_price if item.current_price > 0 else -1.0
            self._update_item(self.table, row, 4, item.current_price if item.current_price > 0 else "-", sort_value=sort_price)
            
            # 盈亏% (Col 5)
            if item.current_price > 0:
                pnl_val = f"{item.pnl_percent:+.2f}%"
                pnl_color = QColor(220, 80, 80) if item.pnl_percent > 0 else (QColor(80, 200, 120) if item.pnl_percent < 0 else None)
            else:
                pnl_val = "-"
                pnl_color = None
            sort_pnl = item.pnl_percent if item.current_price > 0 else -999.0
            self._update_item(self.table, row, 5, pnl_val, sort_value=sort_pnl, foreground=pnl_color)
            
            # 分组 (Col 6)
            self._update_item(self.table, row, 6, item.group)
            
            # 时间 (Col 7)
            time_str = item.add_time[5:-3] if len(item.add_time) > 10 else item.add_time
            self._update_item(self.table, row, 7, time_str)

            # 信号类型 (Col 8)
            self._update_item(self.table, row, 8, item.signal_type)
        
        # [RESTORE] 移除性能杀手 resizeColumnsToContents()
        # [FIX] 恢复选中项
        if current_code:
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 1) # Code col
                if it and it.text() == current_code:
                    self.table.setCurrentCell(r, 1)
                    break
        
        self.table.verticalScrollBar().setValue(v_scroll)
        
        # [FIX] 强制启用排序，否则 was_sorting 默认为 False 会导致排序丢失
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._is_refreshing = False
        
        self._update_status_bar()

    def _update_status_bar(self):
        """[NEW] 统一更新状态栏信息"""
        hot_count = len(self.items)
        follow_txt = f" | 跟单: {self.follow_count}" if self.follow_count > 0 else ""
        
        # [NEW] Watchlist count
        watch_count = 0
        if hasattr(self, '_last_df_watchlist') and self._last_df_watchlist is not None:
            watch_count = len(self._last_df_watchlist)
        watch_txt = f" | 观察: {watch_count}" if watch_count > 0 else ""
        
        self.status_label.setText(f"🔥 热点: {hot_count}{follow_txt}{watch_txt}")

    def _on_table_wheel_event(self, a0: Optional[QtGui.QWheelEvent]):
        """处理主表格滚轮事件"""
        if a0:
            self._generic_wheel_handler(self.table, a0)

    def _on_follow_wheel_event(self, a0: Optional[QtGui.QWheelEvent]):
        """处理跟单表格滚轮事件"""
        if a0:
            self._generic_wheel_handler(self.follow_table, a0)

    def _on_watchlist_wheel_event(self, a0: Optional[QtGui.QWheelEvent]):
        """处理观察池表格滚轮事件"""
        if a0:
            self._generic_wheel_handler(self.watchlist_table, a0)

    def _generic_wheel_handler(self, table: QTableWidget, event: QtGui.QWheelEvent):
        """通用的滚轮横向/垂直切换逻辑 (Shift+Wheel 或 无垂直条时转向横向)"""
        # 保护性检查
        if not table or not event: return
        
        # 判断是否需要横向滚动
        shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        v_bar = table.verticalScrollBar()
        h_bar = table.horizontalScrollBar()
        
        # 检查是否可以进行横向滚动
        can_h_scroll = h_bar and h_bar.isVisible() and h_bar.maximum() > 0
        # 检查是否有垂直滚动条需求
        can_v_scroll = v_bar and v_bar.isVisible() and v_bar.maximum() > 0
        
        # 如果按下 Shift 或者没有垂直滚动条但有水平滚动条，则进行水平滚动
        if (shift_pressed or not can_v_scroll) and can_h_scroll:
            delta = event.angleDelta().y() # 垂直滚轮数值
            if delta != 0:
                h_bar.setValue(h_bar.value() - delta)
                event.accept()
                return
        
        # 否则调用原始实现处理垂直滚动
        orig_wheel = getattr(table, '_original_wheel_event', None)
        if orig_wheel:
            orig_wheel(table, event)
        else:
            # Fallback
            QTableWidget.wheelEvent(table, event)
    
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
    
    def remove_stock(self, code: str) -> bool:
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
    
    def update_prices(self, price_map: dict[str, float], phase_map: Optional[dict[str, str]] = None):
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
        
        # [OPTIMIZE] 仅当 Hotlist 标签可见时才执行主表格的刷新
        if hasattr(self, 'tabs') and self.tabs.currentIndex() == 0:
            self._refresh_table()
    
    def _on_tab_changed(self, index):
        """Tab 切换回调"""
        with timed_ctx(f"tab_changed_{index}", warn_ms=100):
            if index == 1: # Follow
                if (df := getattr(self, '_last_df_follow', None)) is not None:
                    self._update_follow_queue(df)
            elif index == 2: # Watchlist
                if (df := getattr(self, '_last_df_watchlist', None)) is not None:
                    self._update_watchlist_queue(df)
            
            # [OPTIMIZE] 仅当数据源可用时才执行同步刷新，且增加冷却控制
            self._refresh_pnl_ui_only()

    def _on_worker_data(self, df_follow: Optional[pd.DataFrame], error_msg: str):
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
                    self._last_df_follow = df_follow # [NEW] Cache
                    
                    # [OPTIMIZE] Only update UI if Follow tab is visible
                    if hasattr(self, 'tabs') and self.tabs.currentIndex() == 1:
                        with timed_ctx("tabs_update_follow_status", warn_ms=100):
                            self._update_follow_queue(df_follow)
                        
                    self._last_follow_fingerprint = current_fingerprint
                    self._update_status_bar() # [NEW] Refresh UI
            except Exception:
                # 出错降级：总是更新
                with timed_ctx("Exception_update_follow_status", warn_ms=100):
                    self._update_follow_queue(df_follow)

            # 刷新 PnL (仅当 Tab 1 可见时？或者总是？)
            # 用户抱怨日志太多，先静默调用
            self._refresh_pnl_ui_only()

    def _refresh_pnl(self):
        """手动刷新按钮回调"""
        # [NEW] 批量自动补齐板块信息 (将实盘数据持久化回信号库)
        try:
            mw = self._find_main_window()
            if mw and hasattr(mw, 'df_all') and not mw.df_all.empty:
                hub = get_trading_hub()
                updated = hub.batch_update_watchlist_sectors(mw.df_all)
                if updated > 0:
                    logger.info(f"🔄 自动补齐 {updated} 只个股板块信息")
        except Exception as e:
            logger.error(f"Auto sector sync error: {e}")

        self._refresh_pnl_ui_only()

    def _refresh_pnl_ui_only(self):
        """仅做 UI 层面的 PnL 刷新 (优化主线程负载)"""
        # [NEW] 节流保护：避免高频触发重绘
        now = time.time()
        if now - getattr(self, '_last_pnl_refresh_tick', 0) < 0.5:
            return
        self._last_pnl_refresh_tick = now

        # 1. 获取主窗口数据
        main_window = self._find_main_window()
        if not (main_window and hasattr(main_window, 'df_all' ) and not main_window.df_all.empty):
            # [FALLBACK] 无数据时仅尝试轻量级刷新 (不触发全量重绘)
            if hasattr(self, 'tabs'):
                idx = self.tabs.currentIndex()
                if idx == 1 and hasattr(self, '_last_price_map'):
                    # Follow Queue: 仅更新价格
                    self._update_follow_prices_only()
                elif idx == 2 and hasattr(self, '_last_price_map'):
                    # Watchlist: 仅更新价格
                    self._update_watchlist_prices_only()
            
            if not self._connection_warning_logged:
                logger.warning("⚠️ 无法获取主窗口数据 (df_all empty), 仅执行轻量级刷新")
                self._connection_warning_logged = True
            return
            
        df = main_window.df_all
        price_map = {}
        phase_map = {}
        
        # 2. 构建或复用 6 位代码快速查找表 (核心优化点：避免每秒重建)
        lookup_6 = getattr(self, '_cached_lookup_6', None)
        df_len = len(df)
        if lookup_6 is None or getattr(self, '_last_df_len', 0) != df_len:
            lookup_6 = {}
            for idx in df.index:
                s_idx = str(idx)
                code_6 = s_idx[-6:] if len(s_idx) >= 6 else s_idx
                if code_6 not in lookup_6: # 优先保留完整匹配
                    lookup_6[code_6] = idx
            self._cached_lookup_6 = lookup_6
            self._last_df_len = df_len

        # 3. 收集更新代码
        codes_to_price = set(item.code for item in self.items)
        if (df_f := getattr(self, '_last_df_follow', None)) is not None and not df_f.empty:
            if 'code' in df_f.columns:
                codes_to_price.update(df_f['code'].unique().astype(str))
        if (df_w := getattr(self, '_last_df_watchlist', None)) is not None and not df_w.empty:
            if 'code' in df_w.columns:
                codes_to_price.update(df_w['code'].unique().astype(str))

         # 4. 批量拉取数据 (减少 loc 调用次数)
        sector_map = {}
        hotlist_codes = {it.code for it in self.items} # [OPTIMIZE] Pre-calculate set for O(1) lookup
        
        for code in codes_to_price:
            t_idx = code if code in df.index else lookup_6.get(code[-6:] if len(code)>=6 else code)
            if t_idx and t_idx in df.index:
                row = df.loc[t_idx]
                close_p = float(row.get('close', row.get('price', 0)))
                self._last_price_map[code] = close_p
                
                # 缓存板块
                category = str(row.get('category', ''))
                if category:
                    sectors = category.split(';')
                    main_sector = sectors[0] if sectors else ''
                    if main_sector:
                        sector_map[code] = main_sector
                
                # Hotlist 额外数据
                if code in hotlist_codes:
                    price_map[code] = close_p
                    phase = str(row.get('last_action', ''))
                    if 'trade_phase' in row: phase = str(row['trade_phase'])
                    phase_map[code] = phase
        
        # 缓存板块信息供 Watchlist 使用
        if sector_map:
            if not hasattr(self, '_last_sector_map'): self._last_sector_map = {}
            self._last_sector_map.update(sector_map)
        
        # 5. 分发更新并节流刷新 UI
        if price_map:
            self.update_prices(price_map, phase_map)
        
        # [OPTIMIZE] 价格更新时仅增量更新 Follow/Watch 的价格列
        if hasattr(self, 'tabs'):
            idx = self.tabs.currentIndex()
            if idx == 1 and hasattr(self, '_last_price_map'): # Follow Queue
                self._update_follow_prices_only()
            elif idx == 2 and hasattr(self, '_last_price_map'): # Watchlist  
                self._update_watchlist_prices_only()  # [CHANGED] 轻量级价格更新
        
        self._connection_warning_logged = False
    
    def _update_follow_prices_only(self):
        """[OPTIMIZE] 批量更新 Follow Queue 的价格和盈亏列"""
        try:
            df = getattr(self, '_last_df_follow', None)
            if df is None or df.empty:
                return
            
            row_count = self.follow_table.rowCount()
            if row_count == 0:
                return
            
            # [OPTIMIZE] 阻塞信号并关闭排序，避免 setText 触发高频重排 (Lag 的核心原因)
            _ = self.follow_table.blockSignals(True)
            was_sorting = self.follow_table.isSortingEnabled()
            if was_sorting:
                self.follow_table.setSortingEnabled(False)
            
            # 一次性构建代码到行的映射
            code_to_row = {}
            for r in range(row_count):
                if (it := self.follow_table.item(r, 2)):
                    code_to_row[it.text()] = r
            
            # 批量更新
            for row in df.itertuples():
                code_str = str(row.code)
                if code_str not in code_to_row:
                    continue
                
                row_idx = code_to_row[code_str]
                curr_price = self._last_price_map.get(code_str, 0.0)
                
                # 更新现价 (Col 4)
                if curr_price > 0:
                    if (it := self.follow_table.item(row_idx, 4)):
                        price_txt = f"{curr_price:.2f}"
                        if it.text() != price_txt:
                            it.setText(price_txt)
                
                # 更新盈亏% (Col 5)
                # [FIX] Better fallback for entry_price
                entry_price = float(getattr(row, 'entry_price', 0) or 0)
                if entry_price <= 0:
                    entry_price = float(getattr(row, 'detected_price', 0) or 0)
                    
                if entry_price > 0 and curr_price > 0:
                    pnl_pct = (curr_price - entry_price) / entry_price * 100
                    if (it := self.follow_table.item(row_idx, 5)):
                        pnl_txt = f"{pnl_pct:+.2f}%"
                        if it.text() != pnl_txt:
                            it.setText(pnl_txt)
                            # 批量设置颜色
                            if pnl_pct > 0: 
                                it.setForeground(QColor(220, 80, 80))
                            elif pnl_pct < 0: 
                                it.setForeground(QColor(80, 200, 120))
                            else: 
                                it.setForeground(QColor('#ddd'))
        except Exception as e:
            logger.error(f"Update follow prices error: {e}")
        finally:
            if was_sorting:
                self.follow_table.setSortingEnabled(True)
            _ = self.follow_table.blockSignals(False)
    
    def _update_watchlist_prices_only(self):
        """[OPTIMIZE] 批量更新 Watchlist 的价格和盈亏列 (板块信息不变)"""
        try:
            df = getattr(self, '_last_df_watchlist', None)
            if df is None or df.empty:
                return
            
            row_count = self.watchlist_table.rowCount()
            if row_count == 0:
                return
            
            # [OPTIMIZE] 性能保护
            _ = self.watchlist_table.blockSignals(True)
            was_sorting = self.watchlist_table.isSortingEnabled()
            if was_sorting:
                self.watchlist_table.setSortingEnabled(False)
            
            # 一次性构建代码到行的映射
            code_to_row = {}
            for r in range(row_count):
                if (it := self.watchlist_table.item(r, 2)):
                    code_to_row[it.text()] = r
            
            # 批量更新价格和盈亏
            for row in df.itertuples():
                code_str = str(row.code)
                if code_str not in code_to_row:
                    continue
                
                row_idx = code_to_row[code_str]
                curr_price = self._last_price_map.get(code_str, 0.0)
                
                # 更新现价 (Col 6)
                if curr_price > 0:
                    if (it := self.watchlist_table.item(row_idx, 6)):
                        price_txt = f"{curr_price:.2f}"
                        if it.text() != price_txt:
                            it.setText(price_txt)
                
                # 更新盈亏% (Col 7)
                discover_price = float(row.discover_price or 0.0)
                if discover_price > 0 and curr_price > 0:
                    pnl_pct = (curr_price - discover_price) / discover_price * 100
                    if (it := self.watchlist_table.item(row_idx, 7)):
                        pnl_txt = f"{pnl_pct:+.2f}%"
                        if it.text() != pnl_txt:
                            it.setText(pnl_txt)
                            # 批量设置颜色
                            if pnl_pct > 0: 
                                it.setForeground(QColor(220, 80, 80))
                            elif pnl_pct < 0: 
                                it.setForeground(QColor(80, 200, 120))
                            else: 
                                it.setForeground(QColor('#ddd'))
                            
        except Exception as e:
            logger.error(f"Update watchlist prices error: {e}")
        finally:
            if was_sorting:
                self.watchlist_table.setSortingEnabled(True)
            _ = self.watchlist_table.blockSignals(False)

    def update_prices(self, price_map: dict[str, float], phase_map: Optional[dict[str, str]] = None):
        """批量更新现价和盈亏 (优化：仅当 Hotlist 可见时触发重绘)"""
        changed = False
        for item in self.items:
            if item.code in price_map:
                new_p = price_map[item.code]
                if abs(item.current_price - new_p) > 0.001:
                    item.current_price = new_p
                    if item.add_price > 0:
                        item.pnl_percent = (item.current_price - item.add_price) / item.add_price * 100
                    changed = True
            
            if phase_map and item.code in phase_map:
                new_phase = phase_map[item.code] or item.group
                if item.group != new_phase:
                    item.group = new_phase
                    changed = True
        
        if changed:
            if hasattr(self, 'tabs') and self.tabs.currentIndex() == 0:
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
                df = getattr(self, '_last_df_follow', None)
            
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
            self.follow_table.blockSignals(True)
            is_sorted = self.follow_table.isSortingEnabled()
            if is_sorted:
                self.follow_table.setSortingEnabled(False)
            
            current_rows = self.follow_table.rowCount()
            needs_full_rebuild = False
            
            if current_rows != len(df):
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
                    # [FIX] 纠正跟单队列 in-place 更新的列索引
                    # cols = ["序号", "状态", "代码", "名称", "现价", "盈亏%", "信号", "入场", "理由", "时间"]
                    
                    # Col 4: Price
                    curr_price = 0.0
                    col4_code = str(row.code)
                    if hasattr(self, '_last_price_map') and col4_code in self._last_price_map:
                        curr_price = self._last_price_map[col4_code]
                    
                    if (it := self.follow_table.item(row_idx, 4)):
                        price_txt = f"{curr_price:.2f}" if curr_price > 0 else "-"
                        if it.text() != price_txt:
                            it.setText(price_txt)
                            if hasattr(it, 'sort_value'): it.sort_value = curr_price if curr_price > 0 else -1.0
                    
                    # Col 5: PnL %
                    # [FIX] Better fallback for entry_price
                    entry_price = _safe_num(getattr(row, 'entry_price', 0))
                    if entry_price <= 0:
                        entry_price = _safe_num(getattr(row, 'detected_price', 0))
                        
                    pnl_pct = 0.0
                    if entry_price > 0 and curr_price > 0:
                        pnl_pct = (curr_price - entry_price) / entry_price * 100
                    
                    if (it := self.follow_table.item(row_idx, 5)):
                        pnl_txt = f"{pnl_pct:+.2f}%" if curr_price > 0 else "-"
                        if it.text() != pnl_txt:
                            it.setText(pnl_txt)
                            if hasattr(it, 'sort_value'): it.sort_value = pnl_pct if curr_price > 0 else -999.0
                            if pnl_pct > 0: it.setForeground(QColor(220, 80, 80))
                            elif pnl_pct < 0: it.setForeground(QColor(80, 200, 120))
                            else: it.setForeground(QColor('#ddd'))

                    # Col 8: Time (时间)
                    time_dt = str(row.updated_at)
                    time_str = time_dt[:16] if len(time_dt) > 10 else time_dt
                    if (it := self.follow_table.item(row_idx, 8)):
                        if it.text() != time_str:
                             it.setText(time_str)
                             it.setData(Qt.ItemDataRole.UserRole, time_dt)
                            
                    # Col 9: Reason (理由)
                    phase_txt = "-"
                    notes = str(row.notes) if row.notes else ""
                    match = re.search(r'\[(.*?)\]', notes)
                    if match: phase_txt = match.group(1)
                    elif notes: phase_txt = notes[:10]
                    
                    if (it := self.follow_table.item(row_idx, 9)):
                        if it.text() != notes:
                            it.setText(notes)
                            it.setToolTip(notes)

                return

            # --- FULL REBUILD (Structure Changed or Sorted) ---
            
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

            if self.follow_table.rowCount() != len(df):
                self.follow_table.setRowCount(len(df))
            
            for row_idx, row in enumerate(df.itertuples()):
                # 0. No.
                self._update_item(self.follow_table, row_idx, 0, row_idx + 1)
                
                # 1. Status
                status = str(row.status)
                color = QColor('#FFD700') if status == 'TRACKING' else (QColor('#00FF00') if status == 'ENTERED' else None)
                self._update_item(self.follow_table, row_idx, 1, status, foreground=color)
                
                # 2. Code, 3. Name
                self._update_item(self.follow_table, row_idx, 2, str(row.code))
                self._update_item(self.follow_table, row_idx, 3, str(row.name))
                
                # 4. 现价
                curr_price = getattr(row, 'current_price', 0.0)
                if curr_price <= 0 and hasattr(self, '_last_price_map') and str(row.code) in self._last_price_map:
                    curr_price = self._last_price_map[str(row.code)]
                self._update_item(self.follow_table, row_idx, 4, curr_price if curr_price > 0 else "-", sort_value=curr_price)

                # 5. 盈亏%
                entry_price = _safe_num(getattr(row, 'entry_price', 0))
                if entry_price <= 0:
                    entry_price = _safe_num(getattr(row, 'detected_price', 0))
                    
                pnl_pct = (curr_price - entry_price) / entry_price * 100 if entry_price > 0 and curr_price > 0 else 0.0
                pnl_txt = f"{pnl_pct:+.2f}%" if curr_price > 0 else "-"
                pnl_color = QColor(220, 80, 80) if pnl_pct > 0 else (QColor(80, 200, 120) if pnl_pct < 0 else None)
                self._update_item(self.follow_table, row_idx, 5, pnl_txt, sort_value=pnl_pct if curr_price > 0 else -999.0, foreground=pnl_color)

                # 6. 信号
                self._update_item(self.follow_table, row_idx, 6, str(getattr(row, 'signal_type', getattr(row, 'signal_name', ''))))
                
                # 7. 入场 (入场价/发现价)
                if entry_price > 0:
                    entry_txt = f"{entry_price:.2f}"
                else:
                    entry_txt = str(getattr(row, 'entry_strategy', '')) or "-"
                self._update_item(self.follow_table, row_idx, 7, entry_txt)
                
                # 8. 时间
                time_dt = str(row.updated_at)
                time_str = time_dt[:16] if len(time_dt) > 10 else time_dt
                it_time = self._update_item(self.follow_table, row_idx, 8, time_str)
                it_time.setData(Qt.ItemDataRole.UserRole, time_dt)

                # 9. 理由
                notes = str(row.notes) if row.notes else ""
                it_notes = self._update_item(self.follow_table, row_idx, 9, notes)
                it_notes.setToolTip(notes)

            # [FIX] Restore Scroll and Selection BEFORE re-enabling signals
            if current_code:
                # Find the row with this code
                for r in range(self.follow_table.rowCount()):
                    it = self.follow_table.item(r, 2)
                    if it and it.text() == current_code:
                        self.follow_table.setCurrentCell(r, 2)
                        break
            
            self.follow_table.verticalScrollBar().setValue(v_scroll)
            # [RESTORE] 移除性能杀手 resizeColumnsToContents()
            
        except Exception as e:
            logger.error(f"Update follow UI error: {e}")
        finally:
            if is_sorted:
                self.follow_table.setSortingEnabled(True)
            self.follow_table.setUpdatesEnabled(True)
            self.follow_table.blockSignals(False)
            self._is_refreshing = False

    def _on_follow_cell_changed(self, currentRow, _currentColumn, _previousRow, _previousColumn):
        """跟单队列键盘导航：联动K线"""
        # 复用单击逻辑，确保行为一致
        if getattr(self, '_is_refreshing', False): return
        with timed_ctx("follow_cell_changed", warn_ms=100):
            if currentRow >= 0:
                self._on_follow_click(currentRow, 0)
        
    def _on_follow_click(self, row, col):
        """跟单队列单击：联动K线"""
        if getattr(self, '_is_refreshing', False): return
        with timed_ctx("follow_click", warn_ms=100):
            try:
                code_item = self.follow_table.item(row, 2)
                name_item = self.follow_table.item(row, 3)
                time_item = self.follow_table.item(row, 9) # MM-DD HH:MM
                
                if code_item and name_item:
                    code = str(code_item.text()).strip()
                    name = str(name_item.text()).strip()
                    
                    # [DEBUNCE] 增加去重逻辑
                    if self._last_selected_codes["follow"] == code:
                        return
                    self._last_selected_codes["follow"] = code
                    
                    # [OPTIMIZE] 从 UserRole 获取完整日期 (YYYY-MM-DD)
                    signal_date = ""
                    if time_item:
                        full_time = time_item.data(Qt.ItemDataRole.UserRole)
                        if full_time and len(str(full_time)) >= 10:
                            signal_date = str(full_time)[:10]
                        else:
                            # Fallback
                            time_txt = time_item.text()
                            if "-" in time_txt:
                                signal_date = time_txt.split(' ')[0]
                    
                    if code:
                        # [FIX] Link with signal date for K-line marking, specify type to avoid mixing
                        link_msg = f"{code}|realtime=false|signal_type=follow"
                        if signal_date:
                            link_msg += f"|signal_date={signal_date}"
                        
                        self.stock_selected.emit(link_msg, name)
            except Exception as e:
                logger.error(f"Follow click error: {e}")

    def _on_follow_double_click(self, row, col):
        """跟单队列双击：打开详情"""
        if getattr(self, '_is_refreshing', False): return
        with timed_ctx("follow_double_click", warn_ms=100):
            try:
                code_item = self.follow_table.item(row, 2)
                name_item = self.follow_table.item(row, 3)
                time_item = self.follow_table.item(row, 9)
                
                if code_item and name_item:
                    code = str(code_item.text()).strip()
                    name = str(name_item.text()).strip()
                    
                    # 强标记为最后选中
                    self._last_selected_codes["follow"] = code
                
                # [OPTIMIZE] 从 UserRole 获取完整日期
                signal_date = ""
                if time_item:
                    full_time = time_item.data(Qt.ItemDataRole.UserRole)
                    if full_time and len(str(full_time)) >= 10:
                        signal_date = str(full_time)[:10]
                    else:
                        time_txt = time_item.text()
                        if "-" in time_txt:
                            signal_date = time_txt.split(' ')[0]
                
                link_msg = f"{code}|realtime=false|signal_type=follow"
                if signal_date:
                    link_msg += f"|signal_date={signal_date}"
                
                # 触发详情信号
                self.item_double_clicked.emit(link_msg, name, 0.0)
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
                with timed_ctx("_update_follow_status", warn_ms=100):
                    self._update_follow_queue(new_df)
                
            else:
                logger.error(f"Failed to update status for {code}")
        except Exception as e:
            logger.error(f"Update follow status error: {e}")

    def _on_hotlist_key_press(self, event):
        """Hotlist 表键盘事件：Del 键移除当前选中股票"""
        if event.key() == Qt.Key.Key_Delete:
            row = self.table.currentRow()
            if row >= 0:
                # Hotlist 表列布局：序号(0), 代码(1), 名称(2)...
                code_item = self.table.item(row, 1)
                if code_item:
                    self.remove_stock(code_item.text())
            return  # 消费 Delete 事件
        QTableWidget.keyPressEvent(self.table, event)

    def _on_watchlist_key_press(self, event):
        """Watch 表键盘事件：Del 键移除当前选中观察池条目"""
        if event.key() == Qt.Key.Key_Delete:
            row = self.watchlist_table.currentRow()
            if row >= 0:
                # Watch 表列布局：序号(0), 状态(1), 代码(2)...
                code_item = self.watchlist_table.item(row, 2)
                if code_item:
                    self._remove_from_watchlist(code_item.text())
            return  # 消费 Delete 事件
        QTableWidget.keyPressEvent(self.watchlist_table, event)

    def _on_follow_key_press(self, event):
        """follow_table 键盘事件：Del 键删除当前选中行"""
        if event.key() == Qt.Key.Key_Delete:
            row = self.follow_table.currentRow()
            if row >= 0:
                code_item = self.follow_table.item(row, 2)
                if code_item:
                    self._delete_follow_item(code_item.text())
            return  # 消费掉 Delete 事件，不再往上传
        # 其余按键交给默认处理
        QTableWidget.keyPressEvent(self.follow_table, event)

    def _delete_follow_item(self, code: str):
        """彻底删除跟单项"""
        try:
            from trading_hub import get_trading_hub
            hub = get_trading_hub()
            if hub.delete_from_follow_queue(code):
                logger.info(f"Deleted follow item: {code}")
                # Force immediate refresh
                new_df = hub.get_follow_queue_df()
                with timed_ctx("_delete_follow_item", warn_ms=100):
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
    
    def _on_item_clicked_simple(self, item):
        """[NEW] 显式点击去重，由 QTableWidget.itemClicked 触发"""
        if item:
            self._on_click(item.row(), item.column())

    def _on_click(self, row: int, col: int):
        """单击切换股票 (带去重)"""
        if row < 0: return
        with timed_ctx("hotlist_click", warn_ms=100):
            item = self._get_item_from_row(row)
            if item:
                # [DEBUNCE] 增加去重逻辑，防止重复联动主窗口
                if self._last_selected_codes["hotlist"] != item.code:
                    self._last_selected_codes["hotlist"] = item.code
                    # [FIX] Hotlist link: No signal_date needed, specify type
                    self.stock_selected.emit(f"{item.code}|realtime=false|signal_type=hotlist", item.name)
    
    def _on_current_cell_changed(self, currentRow: int, _currentColumn: int, _previousRow: int, _previousColumn: int):
        """键盘导航联动（上下键切换时也触发股票选择）"""
        if currentRow >= 0:
            self._on_click(currentRow, 0)
    
    def _on_double_click(self, row: int, col: int):
        """双击打开详情"""
        if row < 0: return
        item = self._get_item_from_row(row)
        if item:
            # [DEBUNCE] 强关联同步去重缓存
            self._last_selected_codes["hotlist"] = item.code
            # [FIX] Hotlist link: specify type
            self.stock_selected.emit(f"{item.code}|realtime=false|signal_type=hotlist", item.name)
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
            if get_trading_hub is None or TrackedSignal is None:
                return
            hub = get_trading_hub()
            
            # [NEW] 自动价格回补：如果当前价格为0，尝试从主窗口获取
            if price <= 0:
                try:
                    for widget in QApplication.topLevelWidgets():
                        if hasattr(widget, 'df_all'):
                            mw: Any = widget
                            if mw.df_all is not None and not mw.df_all.empty:
                                if code in mw.df_all.index:
                                    price = float(mw.df_all.loc[code].get('close', 0))
                                    logger.info(f"Using MainWindow price for {code}: {price}")
                                    break
                except Exception:
                    pass
            
            if price <= 0:
                logger.warning(f"⚠️ 无法获取价格，放弃加入跟单队列: {code}")
                return

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
        if not has_detector_imported:
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
                # 根据信号类型判断优先级 (风险信号为高优先级)
                is_high_priority = event.pattern in ['bull_trap_exit', 'momentum_failure', 'top_signal', 'high_drop']
                self.signal_log.emit(event.code, event.name, event.pattern, msg, is_high_priority)
            except Exception as e_emit:
                logger.error(f"❌ Signal emit failed: {e_emit}")
            
            # ⚡ [REFINED] 统一信号流向：不再此处直接调用 _notify_voice。
            # 信号通过 signal_log.emit 推送到 MainWindow 后，由“所见即所播”机制统一处理播报。
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

    def mouseDoubleClickEvent(self, event):
        """标题栏双击：自动放大1.5倍 / 还原"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否在标题栏区域
            if hasattr(self, 'header') and self.header.geometry().contains(event.pos()):
                # 排除点击标题栏上的按钮
                child = self.header.childAt(event.position().toPoint())
                if isinstance(child, QPushButton):
                    super().mouseDoubleClickEvent(event)
                    return

                if not self._is_enlarged:
                    # 放大
                    self._pre_enlarge_geometry = self.geometry()
                    new_w = int(self.width() * 1.5)
                    new_h = int(self.height() * 1.5)
                    self.resize(new_w, new_h)
                    self._is_enlarged = True
                    logger.info(f"HotlistPanel enlarged to {new_w}x{new_h}")
                else:
                    # 还原
                    if self._pre_enlarge_geometry:
                        self.setGeometry(self._pre_enlarge_geometry)
                    else:
                        new_w = int(self.width() / 1.5)
                        new_h = int(self.height() / 1.5)
                        self.resize(new_w, new_h)
                    self._is_enlarged = False
                    logger.info("HotlistPanel restored to normal size")
                
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    # ================== 位置保存/加载 (Unified Mixin) ==================
    # Removed custom _get_config_path, _save_position, _load_position

    def hideEvent(self, event):
        """隐藏时保存位置"""
        super().hideEvent(event)


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
    QMessageBox, QDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QAction

logger = logging.getLogger(__name__)

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


class HotlistPanel(QWidget):
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
        self.items: List[HotlistItem] = []
        self._drag_pos = None
        self.voice_enabled = True  # 是否启用语音通知
        
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
        
        # 定时刷新盈亏（每30秒）
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_pnl)
        self.refresh_timer.start(30000)
        
        # [NEW] 加载信号计数（从数据库）
        self._load_signal_counts()
    
    def _init_db(self):
        """确保数据库表存在，并扩展字段"""
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
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
            conn.close()
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
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "加入价", "现价", "盈亏%", "分组", "时间"])
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
        
        # 表头设置
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Code
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # Name (Stretch to fill)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Add Price
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Cur Price
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # PnL
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)            # Group
        self.table.setColumnWidth(5, 50)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)            # Time
        self.table.setColumnWidth(6, 80)                                        # [MODIFIED] 增大时间列宽度以便完整显示
        
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #ddd;
                border: none;
                font-size: 10pt;
            }
            QTableWidget::item {
                padding: 3px;
            }
            QTableWidget::item:selected {
                background-color: #444;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #aaa;
                border: none;
                padding: 4px;
                font-size: 9pt;
            }
        """)
        
        layout.addWidget(self.table)
        
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

    def _load_from_db(self):
        """从数据库加载热点列表"""
        self.items.clear()
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM follow_record 
                WHERE status = 'ACTIVE' 
                ORDER BY id DESC
            """)
            rows = c.fetchall()
            conn.close()
            
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
        self.table.setRowCount(len(self.items))
        
        for row, item in enumerate(self.items):
            # 代码
            code_item = QTableWidgetItem(item.code)
            self.table.setItem(row, 0, code_item)
            
            # 名称
            name_item = QTableWidgetItem(item.name)
            self.table.setItem(row, 1, name_item)
            
            # 加入价
            add_price_item = QTableWidgetItem(f"{item.add_price:.2f}")
            add_price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, add_price_item)
            
            # 现价
            cur_price_item = QTableWidgetItem(f"{item.current_price:.2f}" if item.current_price > 0 else "-")
            cur_price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, cur_price_item)
            
            # 盈亏%
            pnl_item = QTableWidgetItem(f"{item.pnl_percent:+.2f}%" if item.current_price > 0 else "-")
            pnl_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if item.pnl_percent > 0:
                pnl_item.setForeground(QColor(220, 80, 80))  # 红色
            elif item.pnl_percent < 0:
                pnl_item.setForeground(QColor(80, 200, 120))  # 绿色
            self.table.setItem(row, 4, pnl_item)
            
            # 分组
            group_item = QTableWidgetItem(item.group)
            group_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, group_item)

            # 时间 (显示短时间格式)
            time_str = item.add_time[5:-3] if len(item.add_time) > 10 else item.add_time
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, time_item)
        
        self.status_label.setText(f"共 {len(self.items)} 只热点股")
    
    def add_stock(self, code: str, name: str, price: float, signal_type: str = "手动添加"):
        """
        添加股票到热点列表
        
        Args:
            code: 股票代码
            name: 股票名称
            price: 加入时价格
            signal_type: 信号类型
        """
        # 检查是否已存在
        for item in self.items:
            if item.code == code:
                logger.info(f"热点已存在: {code} {name}")
                return False
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("""
                INSERT INTO follow_record 
                (code, name, follow_date, follow_price, status, signal_type, group_tag)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, '观察')
            """, (code, name, now, price, signal_type))
            new_id = c.lastrowid
            conn.commit()
            conn.close()
            
            new_item = HotlistItem(
                id=new_id,
                code=code,
                name=name,
                add_price=price,
                add_time=now,
                current_price=price,
                pnl_percent=0.0,
                signal_type=signal_type,
                group="观察"
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
                    conn = sqlite3.connect(DB_FILE, timeout=10)
                    c = conn.cursor()
                    c.execute("UPDATE follow_record SET status = 'REMOVED' WHERE id = ?", (item.id,))
                    conn.commit()
                    conn.close()
                    
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
    
    def _refresh_pnl(self):
        """刷新盈亏数据（从主窗口的df_all获取）"""
        # [FIX] 使用 window() 而不是 parent() 来获取主窗口（因为 parent=None）
        main_window = None
        try:
            # 尝试通过 window() 获取顶层窗口
            from PyQt6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'df_all') and widget.__class__.__name__ == 'MainWindow':
                    main_window = widget
                    break
        except Exception as e:
            logger.debug(f"Failed to find main window: {e}")
        
        if main_window and hasattr(main_window, 'df_all') and not main_window.df_all.empty:
            df = main_window.df_all
            price_map = {}
            for item in self.items:
                if item.code in df.index:
                    row = df.loc[item.code]
                    price_map[item.code] = row.get('close', row.get('price', 0))
            
            if price_map:
                self.update_prices(price_map)
                logger.info(f"✅ 已刷新 {len(price_map)} 只股票的盈亏数据")
            else:
                logger.warning("⚠️ 未找到匹配的股票数据")
        else:
            logger.warning("⚠️ 无法获取主窗口数据，请确保主窗口已加载数据")
    
    def _clear_exited(self):
        """清空已退出的记录"""
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            # [FIX] 先查询要删除的数量
            c.execute("SELECT COUNT(*) FROM follow_record WHERE status != 'ACTIVE'")
            count = c.fetchone()[0]
            
            if count == 0:
                logger.info("ℹ️ 没有需要清理的退出记录")
                conn.close()
                return
            
            c.execute("DELETE FROM follow_record WHERE status != 'ACTIVE'")
            conn.commit()
            conn.close()
            
            # [FIX] 重新加载列表以显示更新
            self._load_from_db()
            logger.info(f"✅ 已清空 {count} 条退出记录")
        except Exception as e:
            logger.error(f"Clear exited error: {e}")
    
    def _load_signal_counts(self):
        """从数据库加载今日信号计数"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT code, pattern, count FROM signal_counts WHERE date = ?", (today,))
            rows = c.fetchall()
            conn.close()
            
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
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("""
                INSERT OR REPLACE INTO signal_counts (code, pattern, date, count, last_trigger)
                VALUES (?, ?, ?, ?, ?)
            """, (code, pattern, today, count, now))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Save signal count error: {e}")
    
    def _on_click(self, row: int, col: int):
        """单击切换股票"""
        if 0 <= row < len(self.items):
            item = self.items[row]
            self.stock_selected.emit(item.code, item.name)
    
    def _on_current_cell_changed(self, currentRow: int, _currentColumn: int, _previousRow: int, _previousColumn: int):
        """键盘导航联动（上下键切换时也触发股票选择）"""
        if 0 <= currentRow < len(self.items):
            item = self.items[currentRow]
            self.stock_selected.emit(item.code, item.name)
    
    def _on_double_click(self, row: int, col: int):
        """双击打开详情"""
        if 0 <= row < len(self.items):
            item = self.items[row]
            self.item_double_clicked.emit(item.code, item.name, item.add_price)

    def select_stock(self, code: str):
        """外部联动：根据代码选中行"""
        if not code: return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)  # 第一列是代码
            if item and item.text() == code:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False
    
    def _on_context_menu(self, pos):
        """右键菜单"""
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            return
        
        item = self.items[row]
        menu = QMenu(self)
        
        # 移除
        remove_action = QAction("❌ 移除", self)
        remove_action.triggered.connect(lambda: self.remove_stock(item.code))
        menu.addAction(remove_action)
        
        menu.addSeparator()
        
        # 分组切换
        group_menu = menu.addMenu("📁 分组")
        for g in ["观察", "蓄势", "已启动", "持仓"]:
            action = QAction(g, self)
            action.triggered.connect(lambda checked, grp=g: self._set_group(item.code, grp))
            group_menu.addAction(action)
        
        menu.exec(self.table.mapToGlobal(pos))
    
    def _set_group(self, code: str, group: str):
        """设置分组"""
        for item in self.items:
            if item.code == code:
                old_group = item.group
                item.group = group
                try:
                    conn = sqlite3.connect(DB_FILE, timeout=10)
                    c = conn.cursor()
                    c.execute("UPDATE follow_record SET group_tag = ? WHERE id = ?", (group, item.id))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"Set group error: {e}")
                
                # 语音通知：分组变更为已启动或持仓
                if group in ("已启动", "持仓") and old_group != group:
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
            self._save_position()  # 自动保存位置
        super().mouseReleaseEvent(event)

    # ================== 位置保存/加载 ==================
    def _get_config_path(self) -> str:
        """获取配置文件路径"""
        import os
        return os.path.join(os.path.dirname(__file__), "hotlist_position.json")

    def _save_position(self):
        """保存窗口位置和尺寸"""
        import json
        try:
            config = {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
                "visible": self.isVisible()
            }
            with open(self._get_config_path(), "w", encoding="utf-8") as f:
                json.dump(config, f)
        except Exception as e:
            logger.debug(f"Save hotlist position error: {e}")

    def _load_position(self):
        """加载窗口位置和尺寸"""
        import json
        import os
        try:
            path = self._get_config_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.move(config.get("x", 100), config.get("y", 100))
                    # 恢复尺寸
                    w = config.get("width", 280)
                    h = config.get("height", 400)
                    self.resize(w, h)
                    if config.get("visible", True):
                        self.show()
                    return True
        except Exception as e:
            logger.debug(f"Load hotlist position error: {e}")
        return False

    def showEvent(self, event):
        """首次显示时加载位置"""
        if not hasattr(self, '_pos_loaded'):
            self._pos_loaded = True
            if not self._load_position():
                # 默认位置：主窗口右侧
                parent = self.parent()
                if parent:
                    parent_geo = parent.geometry()
                    self.move(parent_geo.right() - 290, parent_geo.top() + 50)
        super().showEvent(event)

    def hideEvent(self, event):
        """隐藏时保存位置"""
        self._save_position()
        super().hideEvent(event)


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
    code_clicked = pyqtSignal(str) # 信号联动
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔥 今日异动放量个股 (Top 30)")
        self.resize(450, 600)
        self.setMinimumWidth(380)
        
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
            code = self.table.item(item.row(), 0).text()
            self.code_clicked.emit(code)
            
    def _on_selection_changed(self):
        """处理键盘上下键选择变化"""
        items = self.table.selectedItems()
        if items:
            # 取得选中行的第一个 Item (代码列)
            row = items[0].row()
            code_item = self.table.item(row, 0)
            if code_item:
                self.code_clicked.emit(code_item.text())
            
    def update_data(self, details_list: List[dict]):
        """刷新数据内容"""
        self.table.setSortingEnabled(False) # 写入数据时关闭排序避免错位
        self.table.setRowCount(0)
        if not details_list: 
            self.table.setSortingEnabled(True)
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
    # 联动信号: code, name
    code_clicked = pyqtSignal(str, str)
    # 🚀 [NEW] 跨线程信号桥接信号 (解决 PyQt6 QTimer.singleShot 兼容性问题)
    sig_bus_event = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 策略信号仪表盘")
        # ⭐ [FIX] 允许更小的窗口尺寸，方便用户缩放
        self.setMinimumSize(400, 300)
        
        # 数据缓存
        self._all_events: List[BusEvent] = []
        self._stock_stats: Dict[str, Dict] = {} # {code: {count: 0, last_msg: "", last_time: ""}}
        self._sector_heat: Dict[str, int] = {}  # {sector: count}
        
        # 🚀 [NEW] 初始化放量详情弹窗
        self._vol_dialog = VolumeDetailsDialog(self)
        self._vol_dialog.code_clicked.connect(
            lambda c: self.sig_bus_event.emit(BusEvent(SignalBus.EVENT_PATTERN, datetime.now(), "VolDialog", {"code": c, "name": ""}))
        )
        
        # 窗口标志
        self.setWindowFlags(Qt.WindowType.Window)
        
        # 🚀 [NEW] 批量刷新与联动控制状态
        self._event_buffer: List[BusEvent] = []
        self._is_updating_ui = False
        
        # 初始化 UI
        self._init_ui()
        
        # 加载持久化位置
        self.load_window_position_qt(self, "signal_dashboard_panel", default_width=1100, default_height=750)
        
        # 恢复表格状态
        self._restore_ui_state()
        
        # 连接总线
        self._setup_bus_connection()
        
        # 启动定时刷新统计板
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats_display)
        self._stats_timer.start(2000)
        
        # 🔗 [NEW] 注册跨线程信号桥接处理器
        self.sig_bus_event.connect(self._safe_process_event)
        
        # 🚀 [RESTORED] 周期刷新定时器：看板独立于主程序跳动，防止高并发卡死
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._process_batch_signals)
        # 固定频率刷新，不随 sleep_time 变化太剧烈，确保 UI 响应
        self._batch_timer.start(3000) 
        
        # 市场大盘数据
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        
        # 🔗 [NEW] 注册当前实例到 SignalBus 便于调试
        logger.info(f"SignalDashboardPanel instance created: {id(self)}")

    def stop(self):
        """⭐ [NEW] 显式停止所有后台任务与连接，防止僵尸进程"""
        logger.info(f"🛑 Stopping SignalDashboardPanel {id(self)}...")
        
        # 1. 停止所有定时器
        if hasattr(self, '_stats_timer') and self._stats_timer:
            self._stats_timer.stop()
            logger.debug("Stats timer stopped.")
        
        if hasattr(self, '_batch_timer') and self._batch_timer:
            self._batch_timer.stop()
            logger.debug("Batch timer stopped.")
            
        if hasattr(self, '_search_timer') and self._search_timer:
            self._search_timer.stop()
            logger.debug("Search timer stopped.")
            
        # 2. 取消总线订阅
        try:
            bus = get_signal_bus()
            bus.unsubscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_RISK, self._on_signal_received)
            bus.unsubscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
            logger.debug("SignalBus subscriptions unsubscribed.")
        except Exception as e:
            logger.error(f"Error during SignalBus unsubscribe: {e}")
            
        # 3. 清理缓冲区
        self._event_buffer.clear()
        
    def closeEvent(self, event):
        """拦截窗口关闭事件"""
        logger.info("SignalDashboardPanel: closeEvent triggered.")
        # 保存持久化信息
        self.save_window_position_qt_visual(self, "signal_dashboard_panel")
        self._save_ui_state()
        self.stop()
        event.accept()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # 1. Dashboard Header (仪表盘头部)
        self.header = QFrame()
        # ⭐ [FIX] 改为更小的高度，允许自适应缩放
        self.header.setMinimumHeight(60)
        self.header.setStyleSheet("""
            QFrame {
                background-color: #1a1c2c;
                border: 1px solid #333;
                border-radius: 6px;
            }
            QLabel {
                color: #ddd;
            }
        """)
        header_layout = QHBoxLayout(self.header)
        
        # --- 市场温度计 ---
        temp_frame = QFrame()
        temp_frame.setStyleSheet("background: transparent; border: none;")
        temp_lay = QVBoxLayout(temp_frame)
        self.temp_label = QLabel("市场温度: --")
        self.temp_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.temp_label.setStyleSheet("color: #ffffff;")
        
        self.market_breadth_label = QLabel("📊 上涨:-- 下跌:--")
        self.market_breadth_label.setStyleSheet("color: #aaa; font-size: 10pt;")
        
        self.vol_stat_label = QLabel("🚀 放量:--")
        self.vol_stat_label.setStyleSheet("color: #FFA500; font-size: 10pt; font-weight: bold;")
        self.vol_stat_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_stat_label.mousePressEvent = self._on_market_breadth_clicked # 保持点击弹出详情
        
        self.ls_ratio_label = QLabel("多空比: --")
        self.ls_ratio_label.setStyleSheet("color: #aaa; font-size: 10pt;")
        
        temp_lay.addWidget(self.temp_label)
        temp_lay.addWidget(self.market_breadth_label)
        temp_lay.addWidget(self.vol_stat_label)
        temp_lay.addWidget(self.ls_ratio_label)
        header_layout.addWidget(temp_frame)
        
        header_layout.addSpacing(30)
        
        # --- 核心统计卡片 ---
        self.stat_cards = QHBoxLayout()
        self.cards = {}
        # 更加专业的配色方案
        # 突破: 鲜红, 风险: 鲜绿, 跟单: 橙黄, 破位: 蓝灰
        for key, name, color in [
            ("follow", "跟单信号", "#FFD700"),   # Gold
            ("breakout", "突破加速", "#FF4500"), # OrangeRed
            ("risk", "风险卖出", "#00FA9A"),     # MediumSpringGreen
            ("breakdown", "结构破位", "#87CEFA")  # LightSkyBlue
        ]:
            card = QFrame()
            # ⭐ [FIX] 更小的宽度下限
            card.setMinimumWidth(60)
            card.setMaximumWidth(200)
            card.setStyleSheet(f"""
                QFrame {{
                    border: 1px solid {color}44; 
                    border-radius: 8px; 
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {color}11, stop:1 {color}22);
                }}
            """)
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(8, 8, 8, 8)
            c_lay.setSpacing(2)
            
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
            
            # ✅ 添加点击交互：点击卡片跳转到对应标签页
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda e, k=key: self._on_card_clicked(k)
            
        header_layout.addLayout(self.stat_cards)
        
        header_layout.addStretch()
        
        # --- 板块热力 ---
        sector_frame = QFrame()
        # ⭐ [FIX] 更小的宽度下限，防止在小窗口下占据太多空间
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
        # 支持点击查看/联动热门板块详情
        self.hot_sectors_label.mousePressEvent = self._on_hot_sectors_clicked
        
        sector_lay.addWidget(self.hot_sectors_label)
        header_layout.addWidget(sector_frame)
        
        layout.addWidget(self.header)
        
        # 2. Tabs for different categories (分类列表)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #0d121f; }
            QTabBar::tab { background: #1a1c2c; color: #888; padding: 8px 20px; border: 1px solid #333; }
            QTabBar::tab:selected { background: #2a2d42; color: #fff; border-bottom-color: #00ff88; }
        """)
        
        # 🚀 [NEW] 添加搜索框到标签栏右侧 (买入机会旁)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码/名称...")
        self.search_input.setFixedWidth(180)
        self.search_input.setStyleSheet("""
            /* 右键黏贴功能,之前旧的RightClickPasteLineEdit功能有问题删除了,改成了QLineEdit() */
            QLineEdit {
                background-color: #1a1c2c;
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 3px 8px;
                margin-top: 2px;
                margin-right: 15px;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border: 1px solid #00ff88;
                background-color: #25283d;
            }
        """)
        # 🔗 [NEW] 支持右键菜单 (解决某些环境下原自定义控件的兼容性问题)
        self.search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.customContextMenuRequested.connect(self._on_search_context_menu)
        
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.tabs.setCornerWidget(self.search_input, Qt.Corner.TopRightCorner)
        
        self.tables: Dict[str, QTableWidget] = {}
        
        # 创建各分类表格
        for tab_name in ["全部信号", "跟单信号", "突破加速", "卖点预警", "结构破位", "买入机会"]:
            table = self._create_signal_table()
            self.tables[tab_name] = table
            self.tabs.addTab(table, tab_name)
            
        # 联动标签切换与搜索
        self.tabs.currentChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
            
        layout.addWidget(self.tabs)

        # 3. Footer Status
        footer_layout = QHBoxLayout()
        self.status_bar = QLabel("就绪 | 统计采样: 最近 500 条信号")
        self.status_bar.setStyleSheet("color: #666; font-size: 9pt; padding: 2px;")
        footer_layout.addWidget(self.status_bar)
        
        # [NEW] 最后更新时间展示
        self.last_update_label = QLabel("最后更新: --:--:--")
        self.last_update_label.setStyleSheet("color: #00ff88; font-family: 'Consolas'; font-size: 9pt; padding: 2px;")
        footer_layout.addStretch()
        footer_layout.addWidget(self.last_update_label)
        
        layout.addLayout(footer_layout)

    def _create_signal_table(self) -> QTableWidget:
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["时间", "代码", "名称", "形态/信号", "详情", "次数", "得分"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True) # ✅ 启用排序
        table.setStyleSheet("""
            QTableWidget { 
                background-color: #0d121f; 
                color: #ffffff; 
                gridline-color: #1a1c2c;
                alternate-background-color: #161a29;
                selection-background-color: #2a2d42;
                font-size: 10pt;
            }
            QHeaderView::section { 
                background-color: #1a1c2c; 
                color: #ffffff; 
                border: none; 
                border-bottom: 2px solid #00ff88;
                padding: 6px; 
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 4px;
            }
        """)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # 时间
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # 代码
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # 名称
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # 形态
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)          # 详情
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # 次数
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # 得分
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed) # ✅ 支持键盘上下键联动
        return table

    def _setup_bus_connection(self):
        """连接信号总线"""
        bus = get_signal_bus()
        bus.subscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_RISK, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
        
        logger.info(f"🚀 SignalDashboardPanel: Connected to SignalBus. Current history size: {len(bus.get_history())}")
        
        # 初始加载历史
        history = bus.get_history(limit=200)
        for event in history:
            self._process_event(event, update_ui=False)
        self._refresh_all_tables()

    def _on_heartbeat_received(self, event: BusEvent):
        """处理心跳消息"""
        try:
            # ⭐ [FIX] 必须传入 self 作为 context object，确保在主线程执行
            QTimer.singleShot(0, self, lambda: self._update_last_sync_time())
            
            # [BACKUP] 如果心跳中携带了 market_stats (备份通道)，也更新 UI
            if event.source == "market_stats" and isinstance(event.payload, dict):
                QTimer.singleShot(0, self, lambda: self.update_market_stats(event.payload))
        except:
            pass

    def _update_last_sync_time(self):
        """更新最后同步时间显示"""
        now_str = datetime.now().strftime("%H:%M:%S")
        self.last_update_label.setText(f"最后更新: {now_str} (实时)")

    def _on_signal_received(self, event: BusEvent):
        """处理新信号消息"""
        try:
            # ⭐ [FIX] 使用 pyqtSignal 直接抛出事件到主线程，解决 QTimer.singleShot 参数适配报错
            self.sig_bus_event.emit(event)
        except Exception as e:
            pass

    def _safe_process_event(self, event: BusEvent):
        """安全地在主线程处理事件：加入待刷新缓冲区"""
        try:
            if not isinstance(event, BusEvent):
                return
            # ⭐ [FIX] 不再立即更新 UI，而是存入缓冲区等待周期刷新
            self._event_buffer.append(event)
        except Exception as e:
            logger.error(f"Error buffering event: {e}")

    def _process_batch_signals(self):
        """⭐ [OPTIMIZED] 周期性限额批量刷新 UI 逻辑"""
        if not self._event_buffer:
            return
            
        # 🛡️ 削峰填谷：单次最多处理 10 条，多余的留到下次刷新，防止阻塞主线程
        MAX_PER_BATCH = 10
        events_to_process = self._event_buffer[:MAX_PER_BATCH]
        del self._event_buffer[:MAX_PER_BATCH]
        
        # 开启更新标识，屏蔽自动联动
        self._is_updating_ui = True
        try:
            for event in events_to_process:
                # 即使不可见也要处理以便更新统计
                self._process_event(event, update_ui=self.isVisible())
                
            # 更新状态栏与采样信息
            self._update_last_sync_time()
            self.status_bar.setText(f"就绪 | 统计采样: 最近 {len(self._all_events)} 条信号")
        except Exception as e:
            logger.error(f"Error in batch update: {e}")
        finally:
            self._is_updating_ui = False

    def _process_event(self, event: BusEvent, update_ui=True):
        """解析并记录事件"""
        self._all_events.append(event)
        if len(self._all_events) > 1000:
            self._all_events.pop(0)
            
        payload = event.payload
        code = payload.get('code', '')
        # ⭐ [FIX] 极度严格的个股验证：必须是 6 位纯数字，过滤掉 'heartbeat' 或 'market_stats' 等噪音
        if not (isinstance(code, str) and code.isdigit() and len(code) == 6):
            # 仅对非心跳类噪音进行调试日志输出
            e_type = getattr(event, 'event_type', getattr(event, 'type', 'UNKNOWN'))
            if e_type not in ['heartbeat', 'HEARTBEAT']:
                logger.debug(f"📋 [DASHBOARD] Ignored non-stock event (Pattern: {payload.get('pattern', 'N/A')}): {e_type} from {event.source}")
            return
        
        # 板块统计 (简单根据 payload 中的信息或后续集成)
        sector = payload.get('sector', '其它')
        if sector:
            self._sector_heat[sector] = self._sector_heat.get(sector, 0) + 1
            
        # 个股聚合统计
        if code not in self._stock_stats:
            self._stock_stats[code] = {"count": 0, "name": payload.get('name', '')}
        self._stock_stats[code]["count"] += 1
        
        if update_ui:
            self._append_to_tables(event)

    def _append_to_tables(self, event: BusEvent):
        """将事件添加到相关的表格中"""
        payload = event.payload
        code = payload.get('code', '')
        name = payload.get('name', '')
        pattern = payload.get('pattern', payload.get('subtype', 'ALERT'))
        detail = payload.get('detail', payload.get('message', ''))
        score = payload.get('score', 0.0)
        time_str = event.timestamp.strftime("%H:%M:%S")
        count = self._stock_stats.get(code, {}).get("count", 1)
        
        # 1. 全部信号
        self._insert_row(self.tables["全部信号"], time_str, code, name, pattern, detail, count, score)
        
        # 2. 分类投递
        for cat, patterns in CATEGORY_MAP.items():
            # 模糊匹配形态
            is_match = any(p.lower() in pattern.lower() or p.lower() in detail.lower() for p in patterns)
            if is_match:
                self._insert_row(self.tables[cat], time_str, code, name, pattern, detail, count, score)

    def _get_item_color(self, pattern, detail):
        """统一颜色计算逻辑"""
        color = QColor("#ffffff") # 默认白色
        if "SELL" in pattern or "风险" in detail: 
            return QColor("#00FF00") # 亮绿
        if "BUY" in pattern or "突破" in detail or any(kw in detail for kw in ["上涨", "反转", "抢筹"]): 
            return QColor("#FF4444") # 亮红
        if "跟单" in detail:
            return QColor("#FFD700") # 金色
        return color

    def _insert_row(self, table: QTableWidget, time_str, code, name, pattern, detail, count, score):
        """插入或更新行，确保线程安全且不会由于排序产生空行"""
        # ⭐ [FIX] 插入/删除前必须完全禁用排序，否则 rowCount 和行索引会在操作中动态变化导致空行
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        
        try:
            # 查找是否有相同代码的现有行，进行聚合显示 (最近 50 行内)
            existing_row = -1
            for r in range(min(50, table.rowCount())):
                item = table.item(r, 1)
                if item and item.text() == code:
                    existing_row = r
                    break
            
            if existing_row >= 0:
                # 1. 移除旧行
                table.removeRow(existing_row)
                
            # 2. 在顶部插入新行并更新数据
            table.insertRow(0)
            table.setItem(0, 0, QTableWidgetItem(time_str))
            table.setItem(0, 1, QTableWidgetItem(code))
            table.setItem(0, 2, QTableWidgetItem(name))
            table.setItem(0, 3, QTableWidgetItem(pattern))
            table.setItem(0, 4, QTableWidgetItem(detail))
            table.setItem(0, 5, NumericTableWidgetItem(count))
            table.setItem(0, 6, NumericTableWidgetItem(score))
            
            # ✅ [NEW] 检查当前搜索过滤 (支持代码/名称/形态/详情)
            search_text = self.search_input.text().strip().lower()
            if search_text:
                is_match = (search_text in code.lower() or 
                           search_text in name.lower() or 
                           search_text in pattern.lower() or 
                           search_text in detail.lower())
                if not is_match:
                    table.setRowHidden(0, True)
            
            # 同步之前的颜色逻辑
            color = self._get_item_color(pattern, detail)
            for i in range(7):
                it = table.item(0, i)
                if it: it.setForeground(color)
            
            # 高亮闪烁反馈
            self._flash_row(table, 0)
                
            if table.rowCount() > 500:
                table.removeRow(table.rowCount() - 1)
        finally:
            # 恢复排序状态
            table.setSortingEnabled(was_sorting)

    def _flash_row(self, table: QTableWidget, row: int):
        """简单的视觉反馈：行背景快速闪烁"""
        try:
            items = [table.item(row, i) for i in range(table.columnCount())]
            if not items or not items[0]: return # 防御性
            
            highlight_brush = QBrush(QColor(255, 255, 0, 60)) # 半透明黄
            for item in items:
                if item:
                    item.setBackground(highlight_brush)
                
            def reset():
                try:
                    transparent_brush = QBrush(QColor(0, 0, 0, 0))
                    for it in items:
                        if it:
                            it.setBackground(transparent_brush)
                except:
                    pass
                
            QTimer.singleShot(800, reset)
        except:
            pass

    def _refresh_all_tables(self):
        for table in self.tables.values():
            table.setRowCount(0)
        for event in self._all_events:
            self._append_to_tables(event)

    def _update_stats_display(self):
        """更新顶部的仪表盘统计数据"""
        total = len(self._all_events)
        if total == 0: return
        
        # 计算多空比 (简单模拟：突破 vs 卖点)
        breakout_count = 0
        risk_count = 0
        follow_count = 0
        breakdown_count = 0
        
        for event in self._all_events:
            payload = event.payload
            p = str(payload.get('pattern', payload.get('subtype', ''))).lower()
            d = str(payload.get('detail', payload.get('message', ''))).lower()
            
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["突破加速"]): breakout_count += 1
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["卖点预警"]): risk_count += 1
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["结构破位"]): breakdown_count += 1
            if any(x.lower() in p or x.lower() in d for x in CATEGORY_MAP["跟单信号"]): follow_count += 1
            
        # 更新卡片
        self.cards["follow"].setText(str(follow_count))
        self.cards["breakout"].setText(str(breakout_count))
        self.cards["risk"].setText(str(risk_count))
        self.cards["breakdown"].setText(str(breakdown_count))
        
        # 多空比: (突破 + 买入) / (风险 + 破位)
        all_bull = [e for e in self._all_events if any(kw.lower() in str(e.payload.get('pattern', e.payload.get('subtype', ''))).lower() or 
                                                     kw.lower() in str(e.payload.get('detail', e.payload.get('message', ''))).lower() 
                                                     for kw in CATEGORY_MAP["买入机会"])]
        bull = breakout_count + len(all_bull)
        bear = risk_count + breakdown_count
        ratio = bull / max(1, bear)
        self.ls_ratio_label.setText(f"多空比: {ratio:.2f}")
        
        # 市场温度感官
        temp = "冷清"
        if ratio > 2.0: temp = "活跃"
        if ratio > 5.0: temp = "狂热"
        if ratio < 0.5: temp = "低迷"
        
        self.temp_label.setText(f"市场温度: {temp} (采样{total})")
        
        # 热门板块
        sorted_sectors = sorted(self._sector_heat.items(), key=lambda x: x[1], reverse=True)
        top_3 = [f"{s}: {c}" for s, c in sorted_sectors[:3]]
        self.hot_sectors_label.setText(" | ".join(top_3) if top_3 else "暂无数据")

    def update_market_stats(self, stats: dict):
        """外部推送全盘统计数据"""
        try:
            logger.info(f"📈 Dashboard receiving market stats (Up: {stats.get('up')}, Vol: {stats.get('vol_up')})")
            self._market_stats.update(stats)
            
            # 更新已打开的详情窗口 (如果它是显示的)
            if hasattr(self, '_vol_dialog') and self._vol_dialog.isVisible():
                self._vol_dialog.update_data(stats.get("vol_details", []))
                
            # 立即更新概览显示
            up = stats.get("up", 0)
            down = stats.get("down", 0)
            vol_up = stats.get("vol_up", 0)
            
            self.market_breadth_label.setText(f"📊 上涨:{up} 下跌:{down}")
            self.vol_stat_label.setText(f"🚀 放量:{vol_up}")
            
            # [NEW] 更新底部时间戳
            now_str = datetime.now().strftime("%H:%M:%S")
            self.last_update_label.setText(f"最后更新: {now_str}")
        except Exception as e:
            logger.error(f"Signal bridging failed: {e}")
        
    def _on_card_clicked(self, key):
        """点击卡片跳转到对应标签页"""
        mapping = {
            "follow": "全部信号",
            "breakout": "突破加速",
            "risk": "卖点预警",
            "breakdown": "结构破位"
        }
        tab_name = mapping.get(key)
        if tab_name:
            # 找到对应的 index
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    break

    def _on_market_breadth_clicked(self, event):
        """点击大盘概览：显示持久化放量窗口"""
        try:
            details = self._market_stats.get("vol_details", [])
            self._vol_dialog.update_data(details)
            self._vol_dialog.show()
            self._vol_dialog.raise_()
            self._vol_dialog.activateWindow()
        except Exception as e:
            logger.error(f"Error opening volume details dialog: {e}")

    def _on_hot_sectors_clicked(self, event):
        """点击热门板块文本：所见即所得，显示板块下具体强势股"""
        text = self.hot_sectors_label.text()
        if "等待" in text: return
        
        # 简单解析出板块名 (假设格式是 "XX: 3 | YY: 2")
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        sectors = text.split(" | ")
        for s in sectors:
            if ":" in s:
                name = s.split(":")[0].strip()
                action = QAction(f"查看 {name} 详情", self)
                action.triggered.connect(lambda checked, n=name: self._filter_by_sector(n))
                menu.addAction(action)
        
        menu.exec(self.hot_sectors_label.mapToGlobal(QPoint(0, 20)))

    def _filter_by_sector(self, sector_name):
        """联动：在全部信号中搜索该板块关键词"""
        # 由于表格自带排序和可能的筛选，我们简单跳转到全部信号并提示用户
        self.tabs.setCurrentIndex(0)
        # 这里我们可以扩展一个过滤功能，但目前先确保联动
        self.status_bar.setText(f"当前筛选板块: {sector_name} | 请在下方列表查看相关个股")

    def _on_cell_clicked(self, row, col):
        """处理单击联动"""
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        code_item = table.item(row, 1)
        name_item = table.item(row, 2)
        if code_item and name_item:
            self.code_clicked.emit(code_item.text(), name_item.text())

    def _on_cell_double_clicked(self, row, col):
        """双击表格单元格：按列功能复制或联动"""

        table = self.sender()
        if not isinstance(table, QTableWidget):
            return

        # 防御：行越界
        if row < 0 or row >= table.rowCount():
            return

        # 获取列名（避免列顺序变化）
        header_item = table.horizontalHeaderItem(col)
        header = header_item.text() if header_item else ""

        # 获取基础数据
        it_code = table.item(row, 1)
        it_name = table.item(row, 2)

        if not it_code or not it_name:
            return

        code = (it_code.text() or "").strip()
        name = (it_name.text() or "").strip()

        clipboard = QApplication.clipboard()

        try:

            # ---------- 代码列 ----------
            if header == "代码":
                clipboard.setText(code)
                QApplication.processEvents()

                self.status_bar.setText(f"📋 已复制代码: {code} ({name})")
                self.code_clicked.emit(code, name)

            # ---------- 名称列 ----------
            elif header == "名称":
                clipboard.setText(name)
                QApplication.processEvents()

                self.status_bar.setText(f"📋 已复制名称: {name} ({code})")
                self.code_clicked.emit(code, name)

            # ---------- 形态列 ----------
            elif header in ("形态", "信号", "Pattern"):
                it_pattern = table.item(row, col)
                if it_pattern:
                    pattern_text = it_pattern.text().strip()
                    clipboard.setText(pattern_text)
                    QApplication.processEvents()

                    self.status_bar.setText(f"📋 已复制形态: {pattern_text}")

            # ---------- 详情列 ----------
            elif header in ("详情", "Detail", "说明"):
                it_detail = table.item(row, col)
                if it_detail:
                    detail_text = it_detail.text().strip()

                    clipboard.setText(detail_text)
                    QApplication.processEvents()

                    self.status_bar.setText(f"📋 已复制详情: {detail_text[:30]}...")

                    # 获取形态
                    pattern = ""
                    it_pattern = table.item(row, 3)
                    if it_pattern:
                        pattern = it_pattern.text()

                    dialog = SignalDetailDialog(code, name, pattern, detail_text, self)
                    dialog.exec()

            # ---------- 默认行为 ----------
            else:
                clipboard.setText(code)
                QApplication.processEvents()

                self.status_bar.setText(f"📋 已复制代码: {code} ({name})")
                self.code_clicked.emit(code, name)

        except Exception as e:
            logger.error(f"Double click handler error: {e}")

    def _on_search_text_changed(self, text):
        """⭐ [NEW] 处理搜索文本变化 - 增加防抖处理"""
        if not hasattr(self, '_search_timer'):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._apply_filter)
        
        self._search_timer.start(200)

    def _apply_filter(self):
        """执行实际过滤逻辑"""
        search_text = self.search_input.text().strip().lower()
        current_table = self.tabs.currentWidget()
        if not isinstance(current_table, QTableWidget):
            return
            
        for row in range(current_table.rowCount()):
            code_item = current_table.item(row, 1)
            name_item = current_table.item(row, 2)
            pattern_item = current_table.item(row, 3)
            detail_item = current_table.item(row, 4)
            
            if not code_item or not name_item:
                continue
                
            code = code_item.text().lower()
            name = name_item.text().lower()
            pattern = pattern_item.text().lower() if pattern_item else ""
            detail = detail_item.text().lower() if detail_item else ""
            
            if (not search_text or 
                search_text in code or 
                search_text in name or 
                search_text in pattern or 
                search_text in detail):
                current_table.setRowHidden(row, False)
            else:
                current_table.setRowHidden(row, True)

    def _on_search_context_menu(self, pos):
        def paste_clipboard():
            clipboard = QApplication.clipboard()
            text = clipboard.text().strip()

            if text:
                self.search_input.setText(text)
                self.status_bar.setText(f"📋 已从剪贴板自动粘贴搜索内容: {text}")
            else:
                menu = self.search_input.createStandardContextMenu()
                menu.exec(self.search_input.mapToGlobal(pos))

        QTimer.singleShot(30, paste_clipboard)

    def _on_selection_changed(self):
        """处理键盘上下键联动"""
        # ⭐ [FIX] 只有在非 UI 自动更新（即手动点击/按键）时才触发联动
        if getattr(self, '_is_updating_ui', False):
            return
            
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        items = table.selectedItems()
        if items:
            # 获取当前选中行的 row (取第一个 item)
            row = items[0].row()
            # 检查是否重复触发 (防止鼠标点击产生两次重复信号: cellClicked + selectionChanged)
            # 不过通常 emit 外部有去重逻辑，这里直接发送即可
            code_item = table.item(row, 1)
            name_item = table.item(row, 2)
            if code_item and name_item:
                self.code_clicked.emit(code_item.text(), name_item.text())

    # def _on_selection_changed(self):
    #     # ... logic ...
    #     pass

    def _save_ui_state(self):
        try:
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            scale = self._get_dpi_scale_factor()
            data_to_save = {}
            # 保存第一个表格的状态作为代表 (或者所有表格)
            table = self.tables["全部信号"]
            data_to_save['signal_table_header'] = table.horizontalHeader().saveState().toHex().data().decode()
            
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            import json, os
            full_data = {}
            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
            
            full_data["signal_dashboard_ui_state"] = data_to_save
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _restore_ui_state(self):
        try:
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            scale = self._get_dpi_scale_factor()
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            import json, os
            if os.path.exists(config_file_path):
                with open(config_file_path, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
                ui_state = full_data.get("signal_dashboard_ui_state")
                if ui_state and 'signal_table_header' in ui_state:
                    state = QByteArray.fromHex(ui_state['signal_table_header'].encode())
                    for table in self.tables.values():
                        table.horizontalHeader().restoreState(state)
        except:
            pass

if __name__ == "__main__":
    # 测试代码
    import sys
    app = QApplication(sys.argv)
    window = SignalDashboardPanel()
    window.show()
    sys.exit(app.exec())

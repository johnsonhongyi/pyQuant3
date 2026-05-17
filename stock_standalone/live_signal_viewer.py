import os
import sys
import pandas as pd
import numpy as np
import sqlite3
import json
from datetime import datetime
from typing import Any, Optional, Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QComboBox, QLineEdit, QHeaderView,
    QAbstractItemView, QMenu, QFileDialog, QMessageBox, QApplication,
    QCheckBox, QDialog, QTextEdit, QDateEdit
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint, QEvent, QDate
from PyQt6.QtGui import QAction, QColor, QFont, QTextCharFormat

from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
from trading_logger import TradingLogger
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import commonTips as cct

class DetailDialog(QDialog):
    """可滚动的详细信息对话框，解决长文本内容超出屏幕高度的问题"""
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 450) # 设置合理的默认大小
        
        layout = QVBoxLayout(self)
        
        # 使用 QTextEdit 承载内容，自带滚动条并支持文本选择
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(content)
        self.text_edit.setReadOnly(True)
        # 允许选择和复制
        self.text_edit.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        
        layout.addWidget(self.text_edit)
        
        # 底部关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

class NumericTableWidgetItem(QTableWidgetItem):
    """自定义 TableWidgetItem，支持正确的数值排序"""
    def __init__(self, value):
        if isinstance(value, tuple) and len(value) == 2:
            sort_val, display_val = value
            super().__init__(str(display_val))
            self.sort_value = sort_val
        elif isinstance(value, (int, float)):
            # 格式化显示，但保留原始数值用于比较
            display_val = f"{value:.2f}" if isinstance(value, float) else str(value)
            super().__init__(display_val)
            self.sort_value = value
        else:
            super().__init__(str(value))
            self.sort_value = str(value)

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            if isinstance(self.sort_value, (int, float)) and isinstance(other.sort_value, (int, float)):
                return self.sort_value < other.sort_value
        return super().__lt__(other)

class LiveSignalViewer(QWidget, WindowMixin):
    """
    实时信号历史轨迹查询窗口，支持键盘联动与自动刷新。
    """
    # 联动信号：(code, name, select_win, timestamp)
    stock_selected_signal = pyqtSignal(str, str, bool, str)
    status_msg_signal = pyqtSignal(str)          # (message)
    window_closed_signal = pyqtSignal()          # 窗口关闭通知

    def __init__(self, parent=None, on_select_callback=None, sender=None, main_app=None):
        super().__init__(parent)
        self.setWindowTitle("实时信号历史轨迹查询")
        self.on_select_callback = on_select_callback
        self.main_app = main_app
        
        # 1. 基础配置
        self.scale_factor = get_windows_dpi_scale_factor()
        self.logger_tool = TradingLogger()
        self._refresh_timer = QTimer(self) # 显式创建计时器，方便清理
        
        # 🚀 [FIX] 设置关闭时销毁窗口属性，自动清理释放内存，避免仅隐藏窗口
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self.sender = sender # 优先复用主界面的发送器
        if self.sender is None:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.sender = StockSender(callback=None)
            except Exception:
                self.sender = None
        
        # 6. 查询历史堆栈 (Back/Forward)
        self._history_stack = []
        self._history_index = -1
        self._is_navigating = False # 防止导航触发的刷新再次存入历史
        
        # 7. 日历高亮缓存
        self._signal_dates_cache = None
        
        # 2. UI 构造
        self._init_ui()
        
        # 🛡️ 记录当前选中，确保状态同步
        self._select_code = None
        
        # 3. 绑定信号 (核心：解决 GIL 引起的 Thread Safety 问题)
        self.stock_selected_signal.connect(self._execute_linkage)
        self.status_msg_signal.connect(self.status_label.setText)
        
        # 4. 加载位置 (WindowMixin)
        self.load_window_position_qt(self, "LiveSignalViewer_Geometry", default_width=1100, default_height=700)
        
        # 5. 初始加载
        QTimer.singleShot(100, self.refresh_data)

    def _init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # --- 顶部控制栏 ---
        ctrl_layout = QHBoxLayout()
        layout.addLayout(ctrl_layout)
        
        ctrl_layout.addWidget(QLabel("日期:"))
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        # 🚀 [FIX] 交易日智能判定：如果是交易日则用今天，否则用上个交易日
        if cct.get_trade_date_status():
            self.date_input.setDate(QDate.currentDate())
        else:
            last_trade_date = cct.get_last_trade_date()
            if last_trade_date:
                self.date_input.setDate(QDate.fromString(last_trade_date, "yyyy-MM-dd"))
            else:
                self.date_input.setDate(QDate.currentDate())
        
        self.date_input.setFixedWidth(int(110 * self.scale_factor))
        self.date_input.dateChanged.connect(self.refresh_data)
        ctrl_layout.addWidget(self.date_input)
        
        ctrl_layout.addWidget(QLabel("代码/名称:"))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("模糊匹配")
        self.code_input.setFixedWidth(int(100 * self.scale_factor))
        self.code_input.returnPressed.connect(self.refresh_data)
        ctrl_layout.addWidget(self.code_input)
        
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setStyleSheet("background-color: #34495e; color: white; font-weight: bold;")
        self.refresh_btn.clicked.connect(self.refresh_data)
        ctrl_layout.addWidget(self.refresh_btn)
        
        ctrl_layout.addWidget(QLabel("类型:"))
        self.type_combo = QComboBox()
        # [UPDATE] 信号分类逻辑调整：
        # 买入: 专属动作过滤 (Action)
        # 卖出: 专属动作过滤 (Action)
        # 异动/企稳/走强/警告: 针对 Alert 内容过滤 (Reason)
        self.type_combo.addItems(["全部", "买入", "卖出", "日内异动", "底部企稳", "突破走强", "风险警告"])
        self.type_combo.currentTextChanged.connect(self._apply_view_filter)
        ctrl_layout.addWidget(self.type_combo)
        
        ctrl_layout.addStretch()
        
        # 🧬 [NEW] DNA 审计功能按钮 (集成在去重前面，通过分发队列避免 GIL 锁)
        self.dna_btn = QPushButton("🧬 DNA审计")
        self.dna_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 2px 8px;")
        self.dna_btn.clicked.connect(self.run_dna_audit)
        ctrl_layout.addWidget(self.dna_btn)

        # 🚀 [NEW] 去重功能选项 (在全量轨迹前)
        self.dedup_checkbox = QCheckBox("去重")
        self.dedup_checkbox.stateChanged.connect(self._apply_view_filter)
        ctrl_layout.addWidget(self.dedup_checkbox)
        
        # 数据源选择 (如有必要后续扩展，目前默认 live_signal_history)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["全量轨迹", "选股历史"])
        ctrl_layout.addWidget(self.source_combo)

        self.export_btn = QPushButton("📤 导出 CSV")
        self.export_btn.clicked.connect(self.export_csv)
        ctrl_layout.addWidget(self.export_btn)
        
        # --- 表格区域 ---
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # 定义列: 插入“距今涨跌”列
        self.headers = ["时间", "代码", "名称", "动作", "价格", "距今涨跌", "理由", "信号流", "周期", "状态", "ID"]
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        
        # [NEW] 调整布局模式：理由自适应，剩余空间分配给信号流
        h = self.table.horizontalHeader()
        if h:
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive) 
            h.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # 理由列 (原来是 5)
            h.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)          # 信号流 (原来是 6)
            # 初始基本宽度
            self.table.setColumnWidth(0, 150) # 时间
            self.table.setColumnWidth(1, 80)  # 代码
            self.table.setColumnWidth(2, 90)  # 名称
            self.table.setColumnWidth(3, 80)  # 动作
            self.table.setColumnWidth(4, 70)  # 价格
            self.table.setColumnWidth(5, 80)  # 距今涨跌

        
        # 交互联动 (单击/键盘切换触发)
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.currentCellChanged.connect(self.on_current_cell_changed)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # 核心：安装事件过滤器以捕捉鼠标侧键 (Back/Forward)
        # 表格及其视口、日期代码输入框都可能吞掉鼠标事件，统一监听
        self.installEventFilter(self)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        self.date_input.installEventFilter(self)
        self.code_input.installEventFilter(self)
        self.type_combo.installEventFilter(self)
        self.table.horizontalHeader().installEventFilter(self)
        self.table.verticalHeader().installEventFilter(self)
        
        # 计时器逻辑
        self._refresh_timer.timeout.connect(self.refresh_data)
        
        # 🚀 [NEW] 日历选择标记当日有的数据
        calendar = self.date_input.calendarWidget()
        if calendar:
            calendar.currentPageChanged.connect(self._highlight_calendar_dates)
        
        layout.addWidget(self.table)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 10pt;")
        layout.addWidget(self.status_label)

    def _get_dates_with_signals(self):
        """从 SQLite 数据库获取所有有信号记录的日期列表"""
        dates = set()
        try:
            conn = self.logger_tool.db_manager.get_connection()
            query = "SELECT DISTINCT substr(timestamp, 1, 10) as date_str FROM live_signal_history"
            with self.logger_tool.db_manager.execute_query(query, ()) as cur:
                rows = cur.fetchall()
                for row in rows:
                    if row[0]:
                        dates.add(row[0])
        except Exception as e:
            # 容错：仅打印，不影响主流程运行
            print(f"[Calendar] Error querying signal dates: {e}")
        return dates

    def _highlight_calendar_dates(self):
        """在下拉日历中标记所有拥有信号数据的日期"""
        calendar = self.date_input.calendarWidget()
        if not calendar:
            return
            
        # 1. 确保缓存是最新的
        if self._signal_dates_cache is None:
            self._signal_dates_cache = self._get_dates_with_signals()
            
        # 2. 定义高亮样式
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#FF4444"))  # 鲜艳红高亮
        f = fmt.font()
        f.setBold(True)
        f.setUnderline(True)
        fmt.setFont(f)
        
        # 3. 在日历中遍历缓存的日期并设置格式
        for date_str in self._signal_dates_cache:
            qdate = QDate.fromString(date_str, "yyyy-MM-dd")
            if qdate.isValid():
                calendar.setDateTextFormat(qdate, fmt)

    def refresh_data(self, push_history=True):
        """异步/安全 刷新数据 (从数据库加载基础数据)"""
        # 🚀 [NEW] 清空日历缓存以便重新加载最新标记
        self._signal_dates_cache = None
        
        # 使用 QDateEdit 获取格式化的日期字符串
        date_str = self.date_input.date().toString("yyyy-MM-dd")
        code_str = self.code_input.text().strip() or None
        
        # 1. 保存到历史堆栈 (如果是新查询且不是导航触发)
        if push_history and not self._is_navigating:
            state = {
                'date': date_str,
                'code': self.code_input.text().strip(),
                'type': self.type_combo.currentIndex()
            }
            # 如果与当前位置状态不同，则存入
            if self._history_index == -1 or self._history_stack[self._history_index] != state:
                # 丢弃当前索引之后的所有记录（新的分支）
                self._history_stack = self._history_stack[:self._history_index + 1]
                self._history_stack.append(state)
                self._history_index = len(self._history_stack) - 1
                # 限制历史大小
                if len(self._history_stack) > 50:
                    self._history_stack.pop(0)
                    self._history_index -= 1

        self.status_msg_signal.emit(f"正在同步数据库...")
        
        # 2. 获取数据 (目前的 logger 访问是阻塞的，若数据量极大可考虑 QThread，目前 2000 条以内直接刷)
        self.all_data_df = self.logger_tool.get_live_signal_history_df(
            date=date_str, 
            code=code_str, 
            limit=2000
        )
        
        # [NEW] 数据空状态即时反馈
        if self.all_data_df.empty:
            self.status_msg_signal.emit(f"📅 [{date_str}] 暂无信号数据")
            # 仍然让 _apply_view_filter 清空表格
            
        # 3. 执行视图级过滤展示
        self._apply_view_filter()
        
        # 🚀 [NEW] 触发日历日期高亮
        self._highlight_calendar_dates()

    def go_back(self):
        """后退 (鼠标4键)"""
        if self._history_index > 0:
            self._history_index -= 1
            self._apply_history_state(self._history_stack[self._history_index])

    def go_forward(self):
        """前进 (鼠标5键)"""
        if self._history_index < len(self._history_stack) - 1:
            self._history_index += 1
            self._apply_history_state(self._history_stack[self._history_index])

    def _apply_history_state(self, state):
        """还原历史查询状态"""
        self._is_navigating = True
        try:
            self.date_input.setDate(QDate.fromString(state['date'], "yyyy-MM-dd"))
            self.code_input.setText(state['code'])
            self.type_combo.setCurrentIndex(state['type'])
            self.refresh_data(push_history=False)
            self.status_msg_signal.emit(f"已恢复历史查询: {state['code'] or '全部'} ({self._history_index + 1}/{len(self._history_stack)})")
        finally:
            self._is_navigating = False

    def eventFilter(self, source, event):
        """事件过滤器：捕捉全局/局部鼠标侧键"""
        if event.type() == QEvent.Type.MouseButtonPress:
            # 鼠标侧键 1 (后退) 和 2 (前进)
            if event.button() == Qt.MouseButton.XButton1:
                self.go_back()
                return True
            elif event.button() == Qt.MouseButton.XButton2:
                self.go_forward()
                return True
        return super().eventFilter(source, event)

    def mousePressEvent(self, event):
        """同步捕捉窗口本身的鼠标按下事件"""
        if event.button() == Qt.MouseButton.XButton1:
            self.go_back()
        elif event.button() == Qt.MouseButton.XButton2:
            self.go_forward()
        else:
            super().mousePressEvent(event)

    def _apply_view_filter(self):
        """执行视图级（UI侧）过滤逻辑，不影响数据库查询"""
        if not hasattr(self, 'all_data_df') or self.all_data_df.empty:
            self.table.setRowCount(0)
            self.status_msg_signal.emit(f"查询报告: 无数据 ({datetime.now().strftime('%H:%M:%S')})")
            return

        type_str = self.type_combo.currentText()
        
        # 定义精细化分类逻辑
        # 动作类: 专属动作过滤 (Action)
        # Alert类: 针对提示内容过滤 (Reason)
        filter_map = {
            "买入": ['买', 'UP', '突破', 'STAR', '加仓', '进场', '买入'],
            "卖出": ['卖', 'DOWN', '退出', '止', '出局', '离场', '卖出'],
            "日内异动": ['异动', '冲高', '炸板', '点火', '抢筹', '大单', '放量', '跳水'],
            "底部企稳": ['企稳', '支撑', '支点', '十字', '星', '回踩', '止跌'],
            "突破走强": ['加速', '强转', '走强', '多头', '站上', '横盘突破'],
            "风险警告": ['警告', '注意', '提示', '压力', '背离', '风险']
        }

        if type_str == "全部":
            df = self.all_data_df
            self.status_msg_signal.emit(f"视图刷新: 展示全部 {len(df)} 条记录")
        elif type_str == "买入":
            keywords = filter_map.get(type_str, [])
            pattern = '|'.join(keywords)
            # 买入逻辑增强：包含买入字眼，但必须剔除带有“负向涨幅特征”或“明确空头字眼”的记录
            mask_pos = (self.all_data_df['action'].str.contains(pattern, case=False, na=False) | 
                        self.all_data_df['reason'].str.contains(pattern, case=False, na=False))
            
            # 负向排除：正则匹配“涨幅 -”（负号），以及 跌、减、离、砸、跳水等词
            exclude_pattern = r'涨幅\s*-\d|跌|减仓|离场|出局|砸盘|跳水|风险|压力|背离'
            mask_neg = self.all_data_df['reason'].str.contains(exclude_pattern, case=False, na=False)
            
            mask = mask_pos & ~mask_neg
            df = self.all_data_df[mask]
            self.status_msg_signal.emit(f"视图筛选: 精准买入识别 命中 {len(df)} 条")
            
        elif type_str == "卖出":
            keywords = filter_map.get(type_str, [])
            pattern = '|'.join(keywords)
            # 卖出逻辑增强：包含卖出字眼，或者 理由中包含“深度跌幅”、“风险/警告”等特征
            mask_sell = (self.all_data_df['action'].str.contains(pattern, case=False, na=False) | 
                         self.all_data_df['reason'].str.contains(pattern, case=False, na=False))
            
            # 强制补入：即便动作是 ALERT，只要理由包含大跌特征（-5%以上或跌停）也归类到卖出/风险视图
            risk_pattern = r'涨幅\s*-[5-9]|涨幅\s*-10|跌停|风险|警告|大单出|急跌'
            mask_risk = self.all_data_df['reason'].str.contains(risk_pattern, case=False, na=False)
            
            mask = mask_sell | mask_risk
            df = self.all_data_df[mask]
            self.status_msg_signal.emit(f"视图筛选: 卖出/风险识别 命中 {len(df)} 条")
        else:
            keywords = filter_map.get(type_str, [])
            pattern = '|'.join(keywords)
            # 针对内容 (Alert/Reason) 分类模式
            # 只要理由命中关键词，不论动作是什么 (通常是 Alert/发现/信号)
            mask = self.all_data_df['reason'].str.contains(pattern, case=False, na=False)
            df = self.all_data_df[mask]
            self.status_msg_signal.emit(f"视图筛选: 内容内容[{type_str}] 命中 {len(df)} 条")

        # 🚀 [NEW] 全量轨迹代码去重 (保留最新一条记录)
        if hasattr(self, 'dedup_checkbox') and self.dedup_checkbox.isChecked() and not df.empty:
            df = df.drop_duplicates(subset=['code'], keep='first')

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        # 预计算当日信号流
        flow_map = {}
        flow_details_map = {}
        if not self.all_data_df.empty:
            try:
                sorted_all = self.all_data_df.copy().sort_values('timestamp')
                grouped = sorted_all.groupby('code')
                for code, group in grouped:
                    acts = group['action'].tolist()
                    stream = []
                    for act in acts:
                        if not stream or act != stream[-1]:
                            stream.append(act)
                    flow_map[code] = " → ".join(stream)
                    
                    details = []
                    for _, r in group.iterrows():
                        time_part = r['timestamp'].split(' ')[-1] if ' ' in str(r['timestamp']) else str(r['timestamp'])
                        details.append(f"[{time_part}] {r['action']} | {r['reason']}")
                    flow_details_map[code] = "📊 今日轨迹线:\n" + "\n ↓ ".join(details)
            except Exception as e:
                print(f"Flow pre-calc error: {e}")

        self.table.setRowCount(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            code_val = row.get('code', '')
            flow_val = flow_map.get(code_val, '')
            
            # [UPDATE] 信号流单元格内仅缩略显示前 20 个字符，内容截断
            display_flow = (flow_val[:20] + "...") if len(flow_val) > 20 else flow_val
            
            # [UPDATE] 理由单元格内仅缩略显示前 30 个字符，防止超长文本破坏布局
            raw_reason = row.get('reason', '')
            display_reason = (raw_reason[:30] + "...") if len(raw_reason) > 30 else raw_reason

            # 🚀 [NEW] 计算距今涨跌幅 (Price change from trigger price to current price)
            trigger_price = float(row.get('price', 0.0))
            change_pct_str = "-"
            change_pct_val = -9999.0  # 占位值，便于无数据排序在最后
            
            if trigger_price > 0:
                current_price = 0.0
                if self.main_app and hasattr(self.main_app, 'df_all') and not self.main_app.df_all.empty:
                    if code_val in self.main_app.df_all.index:
                        current_price = float(self.main_app.df_all.loc[code_val].get('trade', 0.0))
                
                if current_price > 0:
                    change_pct = (current_price - trigger_price) / trigger_price * 100
                    change_pct_str = f"{change_pct:+.2f}%"
                    change_pct_val = change_pct

            # 列映射: 恢复原始逻辑，并插入“距今涨跌”
            values = [
                row.get('timestamp', ''),
                code_val,
                row.get('name', ''),
                row.get('action', ''),
                row.get('price', 0.0),
                (change_pct_val, change_pct_str),  # 🚀 [NEW] 距今涨跌 (使用 (sort_value, display_text) 支持数值排序)
                display_reason, # 此处使用截断后的理由
                display_flow,   # 此处使用截断后的信号流
                row.get('resample', 'd'),
                row.get('status', 'NEW'),
                row.get('id', 0)
            ]
            
            indicators_val = row.get('indicators', '')
            tooltip_str = ""
            if indicators_val:
                try:
                    import json
                    if isinstance(indicators_val, str) and indicators_val.startswith('{'):
                        ind_dict = json.loads(indicators_val)
                        tooltip_str = "🔍 信号细节 (迭代标尺):\n" + json.dumps(ind_dict, indent=2, ensure_ascii=False)
                    elif isinstance(indicators_val, dict):
                        tooltip_str = "🔍 信号细节 (迭代标尺):\n" + json.dumps(indicators_val, indent=2, ensure_ascii=False)
                except:
                    tooltip_str = f"指标快照: {indicators_val}"

            current_flow_details = flow_details_map.get(code_val, "无轨迹详情")

            for col_idx, val in enumerate(values):
                item = NumericTableWidgetItem(val)
                
                # 提示与原始数据存储逻辑适配
                if col_idx == 7: # 信号流列 (原 6)
                    item.setData(Qt.ItemDataRole.UserRole, flow_val) # [CRITICAL] 存储未截断的原始流文本
                    item.setToolTip(current_flow_details)
                    if any(x in flow_val for x in ['卖', 'DOWN', '离场', '出局']):
                        item.setForeground(QColor("#95a5a6"))
                elif col_idx == 6: # 理由列 (原 5)
                    item.setData(Qt.ItemDataRole.UserRole, raw_reason) # [CRITICAL] 存储未截断的原始理由文本
                    # 理由列的 ToolTip 也要包含完整理由
                    reason_tip = f"📝 完整理由:\n{raw_reason}\n\n{tooltip_str}" if tooltip_str else f"📝 完整理由:\n{raw_reason}"
                    item.setToolTip(reason_tip)
                elif col_idx == 5: # 🚀 [NEW] 距今涨跌幅列高亮与染色
                    sort_val, display_str = val
                    if sort_val > -9990.0:
                        if sort_val > 0:
                            item.setForeground(QColor("#e74c3c")) # 亮红色 (配合动作红)
                            item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
                        elif sort_val < 0:
                            item.setForeground(QColor("#27ae60")) # 亮绿色 (配合动作绿)
                            item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
                    else:
                        item.setForeground(QColor("#95a5a6")) # 灰色占位符 "-"
                elif col_idx == 1: # 代码列
                    combined_tip = f"{current_flow_details}\n\n{tooltip_str}" if tooltip_str else current_flow_details
                    item.setToolTip(combined_tip)
                elif tooltip_str:
                    item.setToolTip(tooltip_str)

                # 动作列高亮 (索引 3)
                if col_idx == 3:
                    act_str = str(val).upper()
                    if any(x in act_str for x in ['买', 'UP', '突破', '加', 'STAR', '底', '企稳', '进场']):
                        item.setForeground(QColor("#e74c3c")) # 红色
                        item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
                    elif any(x in act_str for x in ['卖', 'DOWN', '退出', '止', '出局', '减', '离场']):
                        item.setForeground(QColor("#27ae60")) # 绿色
                        item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
                    elif any(x in act_str for x in ['异动', '缩量', '放量', '炸板', '警告', '注意', '提示']):
                        item.setForeground(QColor("#f39c12")) # 橙色
                self.table.setItem(i, col_idx, item)
                
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        
        # [REMOVED] 不再在每次渲染时强制 ResizeToContents，避免双击导致列跳动
        # 如果需要手动刷新所有列宽，建议在 setup_ui 或 第一次加载时做
        
        self.status_msg_signal.emit(f"就绪: 统计到 {len(df)} 条信号分析 ({datetime.now().strftime('%H:%M:%S')})")

    def on_item_clicked(self, item):
        """单击表格行联动 K 线 (默认不触发推送)"""
        self._trigger_linkage(item.row(), select_win=False)

    def on_item_double_clicked(self, item):
        """双击表格处理：如果是代码列则钻取，如果是理由/信号流则弹出详情"""
        row = item.row()
        col = item.column()
        # 1. 代码列索引为 1: 下钻查询
        if col == 1:
            code = item.text().strip()
            self.code_input.setText(code)
            self.type_combo.setCurrentIndex(0) # 切换到“全部”
            self.refresh_data() # 触发新查询（会存入历史）
            self.status_msg_signal.emit(f"已钻取查询股票: {code}")
        # 2. 理由 (6) 或 信号流 (7) 列: 弹出深度详情对话框 (放大镜功能) (由于插入“距今涨跌”移至 6, 7)
        elif col in [6, 7]:
            # [UPDATE] 由于理由列也实施了 30 字符截断，故恢复双击弹出详情功能
            # [CRITICAL] 针对理由/信号流列，应从 ToolTip 中提取完整背景信息
            # 这里的 item 是 QTableWidgetItem
            code_item = self.table.item(row, 1)
            code = code_item.text() if code_item else "000000"
            name_item = self.table.item(row, 2)
            name = name_item.text() if name_item else "Unknown"
            
            # [CRITICAL] 优先获取隐藏在 UserRole 中的未截断原始文本
            raw_content = item.data(Qt.ItemDataRole.UserRole)
            cell_text = raw_content if raw_content else item.data(Qt.ItemDataRole.DisplayRole)
            tip_content = item.toolTip()
            
            # [UPDATE] 简化展示逻辑：去除冗余的“当前内容”描述，直接显示最全的复盘信息
            # 对于理由列：tip_content 已经包含了完整理由+指标快照
            # 对于信号流：tip_content 已经包含了带时间戳的轨迹详情
            display_content = tip_content if tip_content else (raw_content if raw_content else cell_text)
            
            # 如果是信号流列，可以在头部稍微增强一下动作链的可读性
            if col == 7 and raw_content:
                display_content = f"【今日信号流】\n{raw_content}\n\n" + display_content
            
            title = f"复盘详情: {name} ({code})"
            
            # 使用自定义可滚动对话框，防止内容过长切断
            dialog = DetailDialog(title, display_content, self)
            dialog.exec()
            
            col_name = self.table.horizontalHeaderItem(col).text()
            self.status_msg_signal.emit(f"查看详情: {name} [{col_name}]")
        else:
            # 其他列双击执行“定位股票”联动
            self._trigger_linkage(row, select_win=True)

    def on_current_cell_changed(self, row, col, prev_row, prev_col):
        """键盘上下键切换行时触发联动 (默认不触发推送)"""
        if row < 0 or row == prev_row:
            return
        self._trigger_linkage(row, select_win=False)

    def _trigger_linkage(self, row, select_win=False):
        """统一触发联动逻辑"""
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        time_item = self.table.item(row, 0)
        if code_item and name_item:
            code = code_item.text().strip()
            name = name_item.text().strip()
            time_val = time_item.text().strip() if time_item else ""
            # [UPGRADE] 时间仅取年月日 (YYYY-MM-DD)，避免包含时分秒导致联动或数据匹配异常
            if time_val:
                if " " in time_val:
                    time_val = time_val.split(" ")[0]
                elif "T" in time_val:
                    time_val = time_val.split("T")[0]
            self.stock_selected_signal.emit(code, name, select_win, time_val)

    def _execute_linkage(self, code, name="", select_win=False, timestamp=None):
        """核心：跨进程/框架联动逻辑 (整合自 KlineBackupViewer 模式)"""
        if not code:
            return
            
        linkage_key = (str(code), str(timestamp) if timestamp else "")
        if getattr(self, '_last_linkage_key', None) == linkage_key:
            return
        self._last_linkage_key = linkage_key
        
        # 🛡️ 记录当前选中，确保状态同步
        self._select_code = str(code)
        
        # 🚀 联动主程序状态反馈
        msg = f"🚀 已联动主程序: {code} {name} (Time:{timestamp or 'None'}) (Push:{select_win})"
        self.status_label.setText(msg)

        # 2. 核心：通过主程序分发队列进行 UI 指令下发 (防 GIL 锁模式)
        if self.main_app and self.on_select_callback:
            try:
                # 🛡️ 优先检查是否有分发队列 (与 KlineBackupViewer 一致)
                if self.main_app and hasattr(self.main_app, 'tk_dispatch_queue'):
                    # A. 联动可视化：如果开启了 vis 标志，且主程序支持 open_visualizer，则同步开启
                    if getattr(self.main_app, "_vis_enabled_cache", False):
                        if hasattr(self.main_app, 'open_visualizer'):
                            self.main_app.tk_dispatch_queue.put(lambda c=code, t=timestamp: self.main_app.open_visualizer(str(c), timestamp=t))
                    
                    # B. 联动主界面：执行主调回调 (如 on_code_click)
                    # 尝试多种调用签名以兼容不同的联动入口
                    self.main_app.tk_dispatch_queue.put(lambda c=code, t=timestamp: self.on_select_callback(str(c), date=t))
                else:
                    # C. 直接降级调用
                    try:
                        self.on_select_callback(str(code), date=timestamp)
                    except TypeError:
                        self.on_select_callback(str(code))
            except Exception as e:
                print(f"Linkage execute error (LiveSignalViewer): {e}")
        else:         # 1. 独立运行时的外部发送器联动
            if self.sender:
                try:
                    self.sender.send(str(code))
                    print(f"[INFO] LiveSignalViewer standalone link sent: {code}")
                except Exception:
                    pass

    # def keyPressEvent(self, a0):
    #     """处理特殊功能按键 (回车定位)"""
    #     # 1. 常规导航交给父类
    #     super().keyPressEvent(a0)
        
    #     # 2. 回车键触发“定位股票”动作 (带跳转)
    #     if a0.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
    #         row = self.table.currentRow()
    #         if row >= 0:
    #             self._trigger_linkage(row, select_win=True)

    def _toggle_auto_refresh(self, checked):
        """开启/关闭自动刷新"""
        if checked:
            self._refresh_timer.start(3000) # 3秒刷新一次
        else:
            self._refresh_timer.stop()

    def show_context_menu(self, pos):
        """右键菜单：增强操作性"""
        item = self.table.itemAt(pos)
        if not item: return
        
        row = item.row()
        code = self.table.item(row, 1).text()
        name = self.table.item(row, 2).text()
        time_item = self.table.item(row, 0)
        time_val = time_item.text().strip() if time_item else ""
        # [UPGRADE] 时间仅取年月日 (YYYY-MM-DD)，避免包含时分秒导致联动或数据匹配异常
        if time_val:
            if " " in time_val:
                time_val = time_val.split(" ")[0]
            elif "T" in time_val:
                time_val = time_val.split("T")[0]
        
        menu = QMenu(self)
        
        copy_action = QAction("📋 复制代码", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(code))
        menu.addAction(copy_action)
        
        link_action = QAction("🎯 联动 K 线 (不跳转)", self)
        link_action.triggered.connect(lambda: self.stock_selected_signal.emit(code, name, False, time_val))
        menu.addAction(link_action)

        # jump_action = QAction("🚀 定位股票 (触发推送)", self)
        # jump_action.triggered.connect(lambda: self.stock_selected_signal.emit(code, name, True))
        # menu.addAction(jump_action)
        
        menu.addSeparator()
        
        # 此处可添加更多业务逻辑，如：
        # mark_done_action = QAction("✅ 标记为已处理", self)
        # menu.addAction(mark_done_action)
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def export_csv(self):
        """安全导出数据"""
        if self.table.rowCount() == 0: return
            
        default_name = f"SignalTrace_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(self, "导出轨迹分析", default_name, "CSV Files (*.csv)")
        if file_path:
            try:
                rows = []
                for row in range(self.table.rowCount()):
                    rows.append([self.table.item(row, c).text() if self.table.item(row, c) else "" for c in range(self.table.columnCount())])
                pd.DataFrame(rows, columns=self.headers).to_csv(file_path, index=False, encoding='utf_8_sig')
                self.status_msg_signal.emit(f"已导出至: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "导出异常", str(e))

    def run_dna_audit(self):
        """
        🧬 对当前表格中可见的个股进行 DNA 审计，通过主程序分发队列执行，避免 GIL 锁/线程死锁问题。
        采用与主程序 Tkinter 逻辑完全一致的高级探测逻辑 (上限 50 只)：
        1. 多选模式：仅审计选中的行 (上限 50 只)
        2. 单选模式：从当前选中行开始向下审计 50 只 (包含选中行本身)
        3. 无选模式：默认审计当前显示列表的前 50 只个股
        """
        if not self.main_app:
            QMessageBox.warning(self, "提示", "未关联主程序，无法执行 DNA 审计。")
            return

        if not hasattr(self.main_app, 'tk_dispatch_queue') or not self.main_app.tk_dispatch_queue:
            QMessageBox.warning(self, "提示", "主程序不支持分发队列，无法执行 DNA 审计。")
            return

        total_rows = self.table.rowCount()
        if total_rows == 0:
            QMessageBox.information(self, "提示", "当前显示列表为空，无有效个股可执行 DNA 审计。")
            return

        # 获取当前选中的所有行索引
        selected_indexes = self.table.selectionModel().selectedRows()
        selected_rows = sorted([idx.row() for idx in selected_indexes])
        
        limit_code = 50
        target_rows = []

        if len(selected_rows) > 1:
            # 多选模式：仅审计选中的 (上限 50)
            target_rows = selected_rows[:limit_code]
            mode_desc = f"选中的 {len(target_rows)} 只"
        elif len(selected_rows) == 1:
            # 单选模式：从选中行开始向下 50 只 (包含本身)
            start_idx = selected_rows[0]
            end_idx = min(start_idx + limit_code, total_rows)
            target_rows = list(range(start_idx, end_idx))
            mode_desc = f"从选中行向下 {len(target_rows)} 只"
        else:
            # 无选模式：默认前 50 只
            end_idx = min(limit_code, total_rows)
            target_rows = list(range(0, end_idx))
            mode_desc = f"列表前 {len(target_rows)} 只"

        # 收集目标个股代码和名称
        codes_dict = {}
        for r in target_rows:
            code_item = self.table.item(r, 1) # 代码列在索引 1
            name_item = self.table.item(r, 2) # 名称列在索引 2
            if code_item:
                code_str = code_item.text().strip()
                name_str = name_item.text().strip() if name_item else ""
                if code_str:
                    codes_dict[code_str] = name_str

        if not codes_dict:
            QMessageBox.information(self, "提示", "所选范围内无有效个股代码。")
            return

        end_date = self.date_input.date().toString("yyyy-MM-dd")
        
        # 通过主程序 tk_dispatch_queue 分发执行，彻底避免 PyQt 与 Tkinter GIL 锁冲突
        try:
            self.main_app.tk_dispatch_queue.put(
                lambda c=codes_dict, ed=end_date: self.main_app._run_dna_audit_batch(c, end_date=ed)
            )
            # 创建一个提示框并开启 2 秒自动关闭定时器
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("DNA 审计启动")
            msg_box.setText(f"已成功将 {mode_desc} 个股的 DNA 审计请求发送至主程序后台，请在主窗口查看审计进度。")
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            
            # 2秒自动关闭
            QTimer.singleShot(1000, msg_box.accept)
            msg_box.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"发送 DNA 审计请求失败: {e}")

    def closeEvent(self, event):
        """持久化窗口位置信息并执行清理逻辑"""
        try:
            # 1. 保存位置
            self.save_window_position_qt(self, "LiveSignalViewer_Geometry")
            
            # 2. 停止计时器 (如果有)
            if hasattr(self, '_refresh_timer'):
                self._refresh_timer.stop()
            
            # 3. 通知父对象进行解构/引用清理
            self.window_closed_signal.emit()
            
            # 4. 自动清理主程序及 panel_manager 中的引用缓存，防止 C++ 析构后残留引用引起二次调用异常
            if self.main_app:
                if getattr(self.main_app, '_live_signal_viewer', None) is self:
                    self.main_app._live_signal_viewer = None
                if hasattr(self.main_app, 'panel_manager') and self.main_app.panel_manager:
                    if getattr(self.main_app.panel_manager, '_live_signal_viewer', None) is self:
                        self.main_app.panel_manager._live_signal_viewer = None
            
        except Exception as e:
            print(f"LiveSignalViewer Cleanup Error: {e}")
        
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 临时模拟环境测试
    viewer = LiveSignalViewer()
    viewer.refresh_data()
    viewer.show()
    sys.exit(app.exec())

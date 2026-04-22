# -*- coding: utf-8 -*-
"""
SignalLogPanel - 实时信号日志面板 (强化版)
显示形态检测、策略信号的实时数据流

功能：
- 实时显示信号日志流 & 点击跳转联动
- 数据流校验：检查代码格式和内容完整性
- 智能去重：自动忽略与上一次完全相同的重复信号
- 支持滚动和暂停、按类型分色
- 窗口位置持久化 (WindowMixin)
"""
import logging
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QPoint
from PyQt6.QtGui import QResizeEvent, QMouseEvent, QColor
from tk_gui_modules.window_mixin import WindowMixin

logger = logging.getLogger(__name__)


class SignalLogPanel(QWidget, WindowMixin):
    """
    实时信号日志面板（浮动窗口）
    
    强化特性：
    - 点击代码超链接可触发主窗口联动
    - 基础数据校验 logic
    - 股票维度去重 (避免相同信号刷屏)
    """
    
    # 信号: code, pattern, message
    log_clicked = pyqtSignal(str, str, str)
    # 信号: code, name, pattern, message (用于同步语音播报)
    log_added = pyqtSignal(str, str, str, str)
    # 信号: 当点击清理按钮时发射
    cleared = pyqtSignal()
    # 信号: 暂停状态切换 (True=Paused, False=Resumed)
    pause_toggled = pyqtSignal(bool)
    
    # 信号颜色映射
    SIGNAL_COLORS = {
        'high_open': '#FFD700',      # 竞价高开 - 金色
        'low_open': '#87CEEB',       # 竞价低开 - 天蓝色
        'high_drop': '#FF6B6B',      # 冲高回落 - 红色
        'top_signal': '#FF4444',     # 顶部信号 - 深红
        'bottom_signal': '#44FF44',  # 底部信号 - 绿色
        'volume_spike': '#FFA500',   # 放量 - 橙色
        'breakout': '#00FF00',       # 突破 - 亮绿
        'default': '#CCCCCC',        # 默认 - 灰色
    }
    
    # 信号名称中文映射
    PATTERN_NAMES = {
        'auction_high_open': '竞价高开',
        'gap_up': '跳空高开',
        'low_open_high_walk': '低开走高',
        'open_is_low': '开盘最低',
        'open_is_low_volume': '开盘最低带量',
        'nlow_is_low_volume': '日低反转带量',
        'low_open_breakout': '低开突破',
        'instant_pullback': '回踩支撑',
        'shrink_sideways': '缩量横盘',
        'pullback_upper': '回踩上轨',
        'high_drop': '冲高回落',
        'top_signal': '顶部信号',
        'master_momentum': '核心主升',
        'open_low_retest': '开盘回踩',
        'high_sideways_break': '横盘突破',
        'bull_trap_exit': '诱多跑路',
        'momentum_failure': '主升转弱',
        'strong_auction_open': '强力竞价',
        # 策略信号
        'ALERT': '报警触发',
        'MOMENTUM': '动量信号',
        'BUY': '买入信号',
        'SELL': '卖出信号',
        'HOLD': '持有',
        'EXIT': '离场',
    }


    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._paused: bool = False
        self._log_buffer: list[str] = []
        # 记录每只股票最后一条信号上下文 {code: {'pattern': p, 'message': m, 'name': n}}
        self._last_signals: dict[str, dict] = {} 
        # 时间窗口去重 {f"{code}_{pattern}": timestamp}
        self._last_signals_time: dict[str, float] = {}
        # ⚡ [NEW] 记录相同信号的触发次数 {f"{code}_{pattern}": count}
        self._signal_counts: dict[str, int] = {}
        self._max_lines: int = 500
        
        self._drag_pos: Optional[QPoint] = None
        
        # 闪屏状态
        self._flash_step: int = 0
        self._flash_timer: Optional[QTimer] = None
        self._original_border_style: str = ""
        
        # [NEW] 防止反向联动导致死循环的标志位
        self._is_programmatic_selection: bool = False
        
        # 设置为浮动工具窗口
        self.setWindowFlags(
            Qt.WindowType.Tool
        )
        self.setWindowTitle("📊 信号日志")
        self.setMinimumWidth(300)
        self.setMinimumHeight(200)
        
        # 加载保存的位置
        self.load_window_position_qt(self, "signal_log_panel", default_width=450, default_height=350)
        
        self._init_ui()

    def apply_theme(self, is_dark: bool):
        """应用主题 (支持深/浅色切换)"""
        if is_dark:
            bg_main = "#1e1e1e"
            color_text = "#ddd"
            header_bg = "#2a2a2a"
            border_color = "#444"
            item_selected = "rgba(255, 215, 0, 80)"
            item_selected_text = "white"
            header_text = "#ddd"
        else:
            bg_main = "#f2faff"
            color_text = "#000000"
            header_bg = "#eef7ff"
            border_color = "#b3d7ff"
            item_selected = "#cce8ff"
            item_selected_text = "black"
            header_text = "#333"

        # 1. 主窗口样式
        self.setStyleSheet(f"""
            SignalLogPanel {{
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
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
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

        # 3. 表格样式
        if hasattr(self, 'log_table'):
            self.log_table.setStyleSheet(f"""
                QTableWidget {{
                    background-color: {bg_main};
                    color: {color_text};
                    border: none;
                    gridline-color: {border_color};
                    font-family: 'Consolas', 'Microsoft YaHei UI';
                    font-size: 9pt;
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
                    color: #888;
                    padding: 4px;
                    border: none;
                    font-size: 9pt;
                }}
                QTableCornerButton::section {{
                    background-color: {header_bg};
                    border: none;
                }}
                
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
            """)
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # 外框样式
        # self.setStyleSheet(...) -> Moved to apply_theme
        
        # 标题栏
        self.header = QFrame()
        self.header.setFixedHeight(28)
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        # self.header.setStyleSheet(...) -> Moved to apply_theme

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        
        title_label = QLabel("📊 信号日志")
        header_layout.addWidget(title_label)
        
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.count_label)
        
        header_layout.addStretch()
        
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.clicked.connect(self._toggle_pause)
        header_layout.addWidget(self.pause_btn)
        
        clear_btn = QPushButton("🗑️")
        clear_btn.clicked.connect(self.clear_logs)
        header_layout.addWidget(clear_btn)
        
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet("QPushButton:hover { color: #ff6b6b; }")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(self.header)
        
        # 核心升级：QTableWidget 以支持精准行定位与同步高亮
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels(["时间", "评级", "性质", "代码", "名称", "信号内容"])
        
        # 稳健性修正
        v_header = self.log_table.verticalHeader()
        if v_header: v_header.setVisible(False)
        
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_table.setAlternatingRowColors(False) # 禁用交替色，使用统一深色背景
        self.log_table.setShowGrid(False)
        # [mFIX] 启用强焦点以支持键盘导航 (Up/Down/Enter/Esc)
        self.log_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.log_table.setTextElideMode(Qt.TextElideMode.ElideRight) # 文本超长显示省略号
        
        # 列宽自适应策略
        h_header = self.log_table.horizontalHeader()
        if h_header:
            h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # 时间
            h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # 评级
            h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # 性质
            h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # 代码
            h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # 名称
            h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)          # 内容 (自适应拉伸)
            h_header.setStretchLastSection(True) # 确保最后一列占满剩余空间
        
        # [FIX] 全局背景深色，修复空白区域白色问题
        # self.setStyleSheet(...) -> Moved to apply_theme
        
        # self.log_table.setStyleSheet(...) -> Moved to apply_theme

        # Apply default Dark Theme
        self.apply_theme(is_dark=True)
        
        # 点击联动逻辑 (保持点击代码跳转)
        self.log_table.cellClicked.connect(self._on_cell_clicked)
        self.log_table.itemDoubleClicked.connect(self._on_item_double_clicked) # [NEW] 双击查看详情
        
        # [NEW] 键盘交互增强
        # 1. 上下键自动联动
        self.log_table.itemSelectionChanged.connect(self._on_selection_changed)
        # 2. 回车/Esc 事件过滤器
        self.log_table.installEventFilter(self)
        
        layout.addWidget(self.log_table)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #555; font-size: 8pt; padding: 2px 8px;")
        layout.addWidget(self.status_label)

    def _on_cell_clicked(self, row, col):
        """点击表格单元格联动"""
        code_item = self.log_table.item(row, 3)
        if not code_item: return
        code = code_item.text()
        
        pattern_cn = self.log_table.item(row, 1).text()
        msg = self.log_table.item(row, 4).text()
        
        # 寻找对应的原始 pattern
        pattern = pattern_cn
        for k, v in self.PATTERN_NAMES.items():
            if v == pattern_cn:
                pattern = k
                break
        
        self.log_clicked.emit(code, pattern, msg)

    def _on_selection_changed(self):
        """
        [NEW] 表格选择变更联动 (支持键盘上下键)
        为了防止快速滚动时频繁触发，可以考虑加个防抖，这里暂时直接触发
        """
        # [mFIX] 防止反向联动死循环
        if getattr(self, '_is_programmatic_selection', False):
            return

        items = self.log_table.selectedItems()
        if not items: return
        
        # 获取当前选中的行
        row = items[0].row()
        # 复用点击逻辑
        self._on_cell_clicked(row, 0)

    def eventFilter(self, source, event):
        """[NEW] 事件过滤器：处理回车和ESC"""
        if source == self.log_table and event.type() == 6: # QEvent.KeyPress == 6
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                # 回车查看详情
                items = self.log_table.selectedItems()
                if items:
                    self._on_item_double_clicked(items[0])
                return True
            elif event.key() == Qt.Key.Key_Escape:
                # ESC 隐藏窗口
                self.hide()
                return True
        
        return super().eventFilter(source, event)

    def _on_item_double_clicked(self, item):
        """双击处理：代码列执行复制，其他列弹出详情"""
        from PyQt6.QtWidgets import QMessageBox
        row = item.row()
        col = item.column()
        
        # 获取基础信息
        code_str = self.log_table.item(row, 3).text()
        
        # ⚡ [NEW] 双击代码列 (Col 3) -> 复制到剪贴板
        if col == 3:
            try:
                QApplication.clipboard().setText(code_str)
                self.status_label.setText(f"📋 已复制: {code_str}")
                # logger.info(f"📋 Code copied to clipboard: {code_str}")
                return
            except Exception as e:
                logger.error(f"Failed to copy to clipboard: {e}")

        # 其他列或复制失败 -> 弹出详情对话框 (保持原逻辑)
        time_str = self.log_table.item(row, 0).text()
        grade_str = self.log_table.item(row, 1).text()
        type_str = self.log_table.item(row, 2).text()
        name_str = self.log_table.item(row, 4).text()
        msg_str = self.log_table.item(row, 5).text()
        
        detail = f"<b>时间:</b> {time_str}<br>"
        detail += f"<b>评级:</b> {grade_str}<br>"
        detail += f"<b>性质:</b> {type_str}<br>"
        detail += f"<b>股票:</b> {name_str} ({code_str})<br><br>"
        detail += f"<b>信号详情:</b><br>{msg_str}"
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("🔍 信号详细信息")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        msg_box.setText(detail)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # ⭐ [NEW] 加载窗口持久化位置
        self.load_window_position_qt(msg_box, "signal_detail_msg_box", default_width=400, default_height=300)
        
        msg_box.exec()
        
        # ⭐ [NEW] 保存窗口位置 (用户关闭后持久化)
        self.save_window_position_qt_visual(msg_box, "signal_detail_msg_box")

    def _on_anchor_clicked(self, url: QUrl):
        """处理点击代码链接"""
        code = url.toString()
        if code:
            # 获取上下文
            ctx = self._last_signals.get(code, {})
            pattern = ctx.get('pattern', 'N/A')
            message = ctx.get('message', '')
            
            self.log_clicked.emit(code, pattern, message)
            self.status_label.setText(f"已跳转: {code} ({pattern})")

    def _validate_data(self, code: str, pattern: str, message: str) -> bool:
        """基础数据校验"""
        if not code or not isinstance(code, str):
            return False
        # 允许空消息，如果为空，append_log 会处理（或者显示为空）
        if not message:
           return False
        return True

    # ... (skip _validate_data) ...

    def append_log(self, code: str, name: str, pattern: str, message: str, is_high_priority: bool = False, grade: str = ''):
        """添加日志条目，包含校验与去重"""
        if self._paused:
            return
            
        # 1. 基础校验
        if not self._validate_data(code, pattern, message):
            return

        # 2. 智能去重：检查该代码的最后一条消息是否相同

        # 2. ⚡ [ENHANCED] 智能去重策略 (时间窗 + 内容)
        now_ts = time.time()
        dedup_key = f"{code}_{pattern}"
        
        # (1) 绝对时间窗去重: 相同(代码+形态)在 60秒内 不重复触发
        last_ts = self._last_signals_time.get(dedup_key, 0)
        if now_ts - last_ts < 60:
            # 特例: 如果是高优先级信号，或者消息内容完全不同且包含"跑路"等关键词，则放行
            is_critical = "跑路" in message or is_high_priority
            if not is_critical:
               return
        
        # (2) 内容完全一致校验 (防止短时震荡频繁触发相同点位)
        last_ctx = self._last_signals.get(code, {})
        # 清洗消息中的动态部分(如价格、时间)后再比对会更准，这里先比对原始消息
        if last_ctx.get('message') == message and last_ctx.get('pattern') == pattern:
            # 即使超过60秒，如果内容完全没变，也可以延长时间窗或忽略
            # 这里选择更新时间戳但不重复显示
            self._last_signals_time[dedup_key] = now_ts
            return
        
        # 更新缓存
        self._last_signals[code] = {'pattern': pattern, 'message': message, 'name': name}
        self._last_signals_time[dedup_key] = now_ts

        # (3) ⚡ [NEW] 内容片段级短时去重 (防止不同 pattern 发射相似消息)
        # 取消息的前 15 个字做指纹，3 秒内不允许同一代码重复 (除非是高优先级)
        if not is_high_priority:
            msg_snippet = message[:15]
            content_key = f"{code}_{msg_snippet}"
            if now_ts - self._last_signals_time.get(content_key, 0) < 3:
                return
            self._last_signals_time[content_key] = now_ts
        
        # 3. 翻译与配色
        pattern_cn = self.PATTERN_NAMES.get(pattern, pattern)
        color_hex = self.SIGNAL_COLORS.get(pattern, self.SIGNAL_COLORS['default'])
        text_color = QColor(color_hex)
        now_str = datetime.now().strftime("%H:%M:%S")

        # 4. 内容去重处理 (移除重复的时间、名称、代码)
        import re
        clean_msg = message
        # (1) 移除时间戳前缀 [HH:MM:SS]
        clean_msg = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', clean_msg)
        # (2) 移除名称和代码
        if name:
            clean_msg = clean_msg.replace(name, '').strip()
        clean_msg = re.sub(r'\(?\[?\d{6}\]?\)?', '', clean_msg).strip()
        
        # (3) 移除冗余的前缀 (如 "动量信号:", "报警触发:" 等)
        # 优先移除 PATTERN_NAMES 中的中文映射
        for pat_val in self.PATTERN_NAMES.values():
            if clean_msg.startswith(pat_val):
                clean_msg = clean_msg[len(pat_val):].strip()
        
        # (4) 移除开头的多余冒号和空格
        clean_msg = re.sub(r'^[:：\s]+', '', clean_msg).strip()

        # 5. 表格去重更新逻辑 (合并相同代码)
        # 查找最新的 100 行，看是否有相同代码的项
        found_row = -1
        for r in range(min(100, self.log_table.rowCount())):
            code_item = self.log_table.item(r, 2)
            if code_item and code_item.text() == code:
                found_row = r
                break
                
        # 更新计数 (按代码累积)
        self._signal_counts[code] = self._signal_counts.get(code, 0) + 1
        count = self._signal_counts[code]
        
        display_msg = clean_msg
            
        if found_row >= 0:
            # 获取原有的 pattern
            old_pattern = self.log_table.item(found_row, 1).text()
            new_pattern = pattern_cn
            if pattern_cn not in old_pattern:
                new_pattern = f"{pattern_cn}、{old_pattern}"
                
            # 获取原有的 message
            old_msg = self.log_table.item(found_row, 4).text()
            old_core_msg = re.sub(r'^\(\d+次\)\s*', '', old_msg)
            
            if clean_msg not in old_core_msg:
                combined_msg = f"{clean_msg} | {old_core_msg}"
            else:
                combined_msg = old_core_msg
                
            if count > 1:
                display_msg = f"({count}次) {combined_msg}"
            else:
                display_msg = combined_msg
                
            # 找到现有行，更新内容和时间
            self.log_table.item(found_row, 0).setText(now_str)
            self.log_table.item(found_row, 1).setText(grade if grade else self.log_table.item(found_row, 1).text())
            self.log_table.item(found_row, 2).setText(new_pattern)
            self.log_table.item(found_row, 5).setText(display_msg)
            
            # 更新评级颜色
            grade_item = self.log_table.item(found_row, 1)
            if grade == 'S': grade_item.setForeground(QColor("#FF1493"))
            elif grade == 'A': grade_item.setForeground(QColor("#FF8C00"))
            
            # 更新颜色为最新形态颜色
            for i in [0, 2, 3, 4, 5]:
                item = self.log_table.item(found_row, i)
                if item:
                    item.setForeground(text_color)
            
            # 发射日志已添加信号，用于同步语音播报 (即使更新也触发)
            self.log_added.emit(code, name, pattern, clean_msg)
            
            # 若是高优先级或计数达到特定阈值，可选触发闪屏
            if is_high_priority:
                self.flash_for_high_priority()
            return

        # 6. 没有找到现有行，插入新行
        if count > 1:
            display_msg = f"({count}次) {clean_msg}"
            
        row = 0 # 始终在最上方插入最新信号
        self.log_table.insertRow(row)
        
        # 单元格填充
        item_grade = QTableWidgetItem(grade)
        if grade == 'S': 
            item_grade.setForeground(QColor("#FF1493"))
            font = item_grade.font()
            font.setBold(True)
            item_grade.setFont(font)
        elif grade == 'A': 
            item_grade.setForeground(QColor("#FF8C00"))
            font = item_grade.font()
            font.setBold(True)
            item_grade.setFont(font)

        items = [
            QTableWidgetItem(now_str),
            item_grade,
            QTableWidgetItem(pattern_cn),
            QTableWidgetItem(code),
            QTableWidgetItem(name),
            QTableWidgetItem(clean_msg) # 使用清理后的消息
        ]
        
        for i, item in enumerate(items):
            if i != 1: # grade 已经单独设色
                item.setForeground(text_color)
            if i == 3 or i == 4: # 代码和名称加粗
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.log_table.setItem(row, i, item)
        
        # 限制行数
        if self.log_table.rowCount() > self._max_lines:
            self.log_table.removeRow(self.log_table.rowCount() - 1)
        
        # 5. 更新状态与计数
        self._log_buffer.append(f"{code} [{pattern_cn}] {message}")
        if len(self._log_buffer) > self._max_lines:
            self._log_buffer = self._log_buffer[-self._max_lines:]
            
        self.count_label.setText(str(len(self._log_buffer)))
        self.status_label.setText(f"最新: {code}")
        
        # 高优先级信号触发闪屏
        if is_high_priority:
            self.flash_for_high_priority()
        
        # 发射日志已添加信号，用于同步语音播报
        # ⭐ [FIX] 统一发射 clean_msg（已清理的消息），与更新行保持一致。
        # snippet 用于语音同步滚动定位，必须与表格内容对齐。
        self.log_added.emit(code, name, pattern, clean_msg)

    def highlight_row_by_content(self, code: str, message_snippet: str, force_scroll: bool = True):
        """
        根据内容高亮并定位行 (用于语音联动)
        :param force_scroll: 是否强行滚动到该行 (用于防夺权保护策略)
        """
        self._is_programmatic_selection = True
        import re as _re
        try:
            # 1. 快速查找所有匹配代码的项
            # ⚡ [ENHANCED] 更加鲁棒的代码匹配：先尝试精确匹配，失败则尝试模糊匹配，并对 code 进行标准化
            clean_code = _re.sub(r'[^\d]', '', code).zfill(6) if code else ""
            
            items = self.log_table.findItems(code, Qt.MatchFlag.MatchExactly)
            if not items and clean_code:
                # 尝试用 6 位纯代码搜索
                items = self.log_table.findItems(clean_code, Qt.MatchFlag.MatchExactly)
            
            if not items:
                # 降级：包含匹配
                items = self.log_table.findItems(code, Qt.MatchFlag.MatchContains)
            
            if not items:
                return False
                
            # 2. 筛选出位于 "代码" 列 (Col 3) 的项
            # 🚀 [FIX] 统一代码列索引检查
            code_items = [it for it in items if it.column() == 3]
            if not code_items:
                return False
            
            # 3. 寻找最佳匹配 (优先匹配 Row 最小的，即最新的)
            code_items.sort(key=lambda it: it.row())
            
            target_item = None
            
            if not message_snippet:
                # 如果没有片段要求，直接取最新的 (Row 最小)
                target_item = code_items[0]
            else:
                # 预处理 snippet：去除时间戳和股票名等前缀，只保留核心信息以增加命中率
                # 例如将 "[10:20:30] 恩捷股份(002812) 突破" 简化为 "突破"
                # ⚡ [REFINED] 采用多级剥离，处理 [Time] Name(Code) Pattern: Msg 各种变体
                def _get_core(text):
                    # 1. 去除时间戳 [HH:MM:SS]
                    text = _re.sub(r'^\[\d+:\d+:\d+\]\s*', '', text).strip()
                    # 2. 如果包含 )，尝试取其后的内容 (跳过名称和代码)
                    if ')' in text:
                        text = text.split(')', 1)[-1].strip()
                    # 3. 如果包含冒号，取其后的核心消息
                    if ':' in text:
                        text = text.split(':', 1)[-1].strip()
                    if '：' in text:
                        text = text.split('：', 1)[-1].strip()
                    return text
                
                core_snippet = _get_core(message_snippet)
                if not core_snippet: core_snippet = message_snippet
                
                for it in code_items:
                    row = it.row()
                    msg_item = self.log_table.item(row, 5)
                    if msg_item:
                        raw_text = msg_item.text()
                        # ⚡ [REFINED] 多维度匹配：优先匹配核心片段，次选全量匹配
                        # 1. 去除计数前缀的纯文本
                        clean_text = _re.sub(r'^\(\d+次\)\s*', '', raw_text).strip()
                        # 2. 提取表格行中的核心消息
                        core_text = _get_core(clean_text)
                        
                        if (core_snippet in core_text or 
                            core_snippet in clean_text or
                            message_snippet in clean_text or
                            message_snippet in raw_text):
                            target_item = it
                            break
                
                # 如果没找到匹配详细内容的，降级到该代码最新的行
                if not target_item:
                    target_item = code_items[0]
            
            if target_item:
                row = target_item.row()
                self.log_table.selectRow(row)
                if force_scroll:
                    self.log_table.scrollToItem(target_item)
                return True

        finally:
            self._is_programmatic_selection = False
        return False

    def clear_logs(self):
        """清空日志"""
        logger.info("🗑️ Clearing signal logs and cache...")
        self.log_table.setRowCount(0)
        self._log_buffer.clear()
        self._last_signals.clear()
        self._last_signals_time.clear()  # [FIX] Clear time deduplication cache
        self._signal_counts.clear()      # [FIX] Clear signal counts cache
        self.count_label.setText("0")
        self.status_label.setText("就绪")
        
        # 发射清理信号，以便联动清理播报队列
        self.cleared.emit()
    
    def flash_for_high_priority(self, times: int = 3, interval_ms: int = 150):
        """
        高优先级信号闪屏效果 (非阻塞)
        使用 QTimer 实现边框颜色交替闪烁
        
        Args:
            times: 闪烁次数
            interval_ms: 每次闪烁间隔（毫秒）
        """
        # 如果正在闪烁中，不重复触发
        if self._flash_timer and self._flash_timer.isActive():
            return
        
        self._flash_step = 0
        total_steps = times * 2  # 每次闪烁包含亮和暗两步
        
        # 保存原始样式
        self._original_border_style = self.styleSheet()
        
        # 闪烁样式
        flash_style = """
            SignalLogPanel {
                background-color: #1a1a1a;
                border: 3px solid #FF0000;
                border-radius: 4px;
            }
        """
        
        normal_style = """
            SignalLogPanel {
                background-color: #1a1a1a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """
        
        def do_flash():
            if self._flash_step >= total_steps:
                # 闪烁结束，恢复原始样式
                self.setStyleSheet(self._original_border_style)
                if self._flash_timer:
                    self._flash_timer.stop()
                return
            
            # 奇偶步切换样式
            if self._flash_step % 2 == 0:
                self.setStyleSheet(flash_style)
            else:
                self.setStyleSheet(normal_style)
            
            self._flash_step += 1
        
        # 创建定时器
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(do_flash)
        self._flash_timer.start(interval_ms)
        
        # 首次立即执行
        do_flash()
    
    # 信号: 暂停状态切换 (True=Paused, False=Resumed)
    pause_toggled = pyqtSignal(bool)

    def _toggle_pause(self):
        """切换暂停状态"""
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.setText("▶")
            self.status_label.setText("已暂停")
            logger.info("[SignalLog] ⏸ Panel PAUSED - Log updates suspended")
        else:
            self.pause_btn.setText("⏸")
            self.status_label.setText("运行中")
            logger.info("[SignalLog] ▶ Panel RESUMED - Log updates active")
            
        # 发射信号供外部联动 (e.g. 暂停语音)
        self.pause_toggled.emit(self._paused)
    
    # ================== 窗口交互与位置持久化 (WindowMixin) ==================
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'header') and self.header.geometry().contains(event.pos()):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.header.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
            else:
                self._drag_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_pos is not None:
            self._drag_pos = None
            if hasattr(self, 'header'):
                self.header.setCursor(Qt.CursorShape.OpenHandCursor)
            # self.save_window_position_qt_visual(self, "signal_log_panel")
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: Optional[QResizeEvent]):
        super().resizeEvent(event)
        if self.isVisible():
            self.save_window_position_qt_visual(self, "signal_log_panel")

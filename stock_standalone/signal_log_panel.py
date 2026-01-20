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
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QPoint
from PyQt6.QtGui import QResizeEvent, QMouseEvent
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
    
    # 信号: 用户点击某条日志中的代码链接时发出
    log_clicked = pyqtSignal(str)  # code
    
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
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._paused: bool = False
        self._log_buffer: list[str] = []
        self._last_messages: dict[str, str] = {}  # 记录每只股票最后一条消息，用于去重
        self._max_lines: int = 500
        self._drag_pos: Optional[QPoint] = None
        
        # 设置为浮动工具窗口
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("📊 信号日志")
        self.setMinimumWidth(300)
        self.setMinimumHeight(200)
        
        # 加载保存的位置
        self.load_window_position_qt(self, "signal_log_panel", default_width=450, default_height=350)
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # 外框样式
        self.setStyleSheet("""
            SignalLogPanel {
                background-color: #1a1a1a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        
        # 标题栏
        self.header = QFrame()
        self.header.setFixedHeight(28)
        self.header.setCursor(Qt.CursorShape.OpenHandCursor)
        self.header.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-bottom: 1px solid #333;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QLabel {
                color: #00FF00;
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
                color: #00FF00;
            }
        """)
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
        
        # 核心升级：QTextBrowser 以支持点击跳转
        self.log_text = QTextBrowser()
        self.log_text.setReadOnly(True)
        self.log_text.setOpenLinks(False)  # 禁止系统浏览器打开
        self.log_text.anchorClicked.connect(self._on_anchor_clicked)
        self.log_text.setStyleSheet("""
            QTextBrowser {
                background-color: #121212;
                color: #cccccc;
                border: none;
                font-family: 'Consolas', 'Microsoft YaHei UI';
                font-size: 9pt;
                padding: 5px;
            }
            a {
                color: #1e90ff;
                text-decoration: none;
                font-weight: bold;
            }
            a:hover {
                text-decoration: underline;
                color: #00ffff;
            }
        """)
        layout.addWidget(self.log_text)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #555; font-size: 8pt; padding: 2px 8px;")
        layout.addWidget(self.status_label)
    
    def _on_anchor_clicked(self, url: QUrl):
        """处理点击代码链接"""
        code = url.toString()
        if code:
            self.log_clicked.emit(code)
            self.status_label.setText(f"已跳转: {code}")

    def _validate_data(self, code: str, pattern: str, message: str) -> bool:
        """基础数据校验 (Data Validation)
        确保进入数据流的代码和消息格式正确，防止非法数据污染
        """
        if not code or len(code) < 5:
            logger.warning(f"[Validation] Rejected invalid code: {code}")
            return False
        if not message or len(message.strip()) < 3:
            logger.warning(f"[Validation] Rejected empty/short message for {code}")
            return False
        if not pattern:
            return False
        return True

    def append_log(self, code: str, name: str, pattern: str, message: str):
        """添加日志条目，包含校验与去重"""
        if self._paused:
            return
            
        # 1. 基础校验
        if not self._validate_data(code, pattern, message):
            return

        # 2. 智能去重：检查该代码的最后一条消息是否相同
        if self._last_messages.get(code) == message:
            return
        
        # 更新缓存
        self._last_messages[code] = message
        
        # 3. 颜色与格式化
        color = self.SIGNAL_COLORS.get(pattern, self.SIGNAL_COLORS['default'])
        
        # 构造可点击的 HTML 段
        clickable_code = f'<a href="{code}">[{code}]</a>'
        clickable_name = f'<a href="{code}">{name}</a>'

        # 尝试在消息中替换名称和代码，使整行更具交互性
        display_msg = message
        if code in display_msg:
            display_msg = display_msg.replace(code, clickable_code)
        if name in display_msg:
            display_msg = display_msg.replace(name, clickable_name)
        
        # 如果替换后没有变化（说明消息里没这两样），则强制加个前缀
        if clickable_code not in display_msg:
            display_msg = f"{clickable_code} {display_msg}"

        html = f'<div style="color:{color}; margin-bottom: 2px;">{display_msg}</div>'

        # 插入内容
        self.log_text.append(html) 
        
        # 更新计数 (本地 buffer 保持原始字符串，用于导出)
        self._log_buffer.append(f"{code} [{pattern}] {message}")
        if len(self._log_buffer) > self._max_lines:
            self._log_buffer = self._log_buffer[-self._max_lines:]
        
        self.count_label.setText(str(len(self._log_buffer)))
        self.status_label.setText(f"最新: {code}")

    def clear_logs(self):
        """清空日志"""
        self.log_text.clear()
        self._log_buffer.clear()
        self._last_messages.clear()
        self.count_label.setText("0")
        self.status_label.setText("已清空")
    
    def _toggle_pause(self):
        """切换暂停状态"""
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.setText("▶")
            self.status_label.setText("已暂停")
        else:
            self.pause_btn.setText("⏸")
            self.status_label.setText("运行中")
    
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
            self.save_window_position_qt_visual(self, "signal_log_panel")
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: Optional[QResizeEvent]):
        super().resizeEvent(event)
        if self.isVisible():
            self.save_window_position_qt_visual(self, "signal_log_panel")

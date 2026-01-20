# -*- coding: utf-8 -*-
"""
SignalLogPanel - 实时信号日志面板
显示形态检测、策略信号的实时数据流，支持快速迭代调试

功能：
- 实时显示信号日志流
- 按类型分色显示
- 支持滚动和暂停
- 可导出日志
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QFont

logger = logging.getLogger(__name__)


class SignalLogPanel(QWidget):
    """
    实时信号日志面板（浮动窗口）
    
    功能：
    - 实时显示形态检测、策略信号日志
    - 按信号类型分色高亮
    - 支持暂停/继续、清空、导出
    """
    
    # 信号: 用户点击某条日志时发出
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
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._log_buffer: List[str] = []
        self._max_lines = 500
        self._drag_pos = None
        
        # 设置为浮动工具窗口
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("📊 信号日志")
        self.setMinimumWidth(300)
        self.setMinimumHeight(200)
        self.resize(450, 350)
        
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
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
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
            QCheckBox {
                color: #888;
                font-size: 9pt;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 4, 0)
        
        title_label = QLabel("📊 信号日志")
        header_layout.addWidget(title_label)
        
        # 计数标签
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.count_label)
        
        header_layout.addStretch()
        
        # 暂停按钮
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setToolTip("暂停/继续")
        self.pause_btn.clicked.connect(self._toggle_pause)
        header_layout.addWidget(self.pause_btn)
        
        # 清空按钮
        clear_btn = QPushButton("🗑️")
        clear_btn.setToolTip("清空日志")
        clear_btn.clicked.connect(self.clear_logs)
        header_layout.addWidget(clear_btn)
        
        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setToolTip("关闭")
        close_btn.setStyleSheet("QPushButton:hover { color: #ff6b6b; }")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(self.header)
        
        # 日志文本区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #cccccc;
                border: none;
                font-family: 'Consolas', 'Microsoft YaHei UI';
                font-size: 9pt;
                padding: 5px;
            }
            QScrollBar:vertical {
                border: none;
                background: #1a1a1a;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.log_text)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #555; font-size: 8pt; padding: 2px 8px;")
        layout.addWidget(self.status_label)
    
    def append_log(self, code: str, pattern: str, message: str):
        """
        添加日志条目
        
        Args:
            code: 股票代码
            pattern: 信号类型
            message: 完整消息
        """
        if self._paused:
            return
        
        # 获取颜色
        color = self.SIGNAL_COLORS.get(pattern, self.SIGNAL_COLORS['default'])
        
        # 格式化HTML
        html = f'<span style="color:{color};">{message}</span><br>'
        
        # 追加到文本
        self.log_text.insertHtml(html)
        
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # 更新计数
        self._log_buffer.append(message)
        if len(self._log_buffer) > self._max_lines:
            self._log_buffer = self._log_buffer[-self._max_lines:]
        
        self.count_label.setText(str(len(self._log_buffer)))
        
        # 更新状态
        self.status_label.setText(f"最新: {code}")
    
    def clear_logs(self):
        """清空日志"""
        self.log_text.clear()
        self._log_buffer.clear()
        self.count_label.setText("0")
        self.status_label.setText("已清空")
    
    def _toggle_pause(self):
        """切换暂停状态"""
        self._paused = not self._paused
        if self._paused:
            self.pause_btn.setText("▶")
            self.pause_btn.setToolTip("继续")
            self.status_label.setText("已暂停")
        else:
            self.pause_btn.setText("⏸")
            self.pause_btn.setToolTip("暂停")
            self.status_label.setText("运行中")
    
    # ================== 拖动支持 ==================
    def mousePressEvent(self, event):
        """记录拖动起始位置"""
        if event.button() == Qt.MouseButton.LeftButton:
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
        super().mouseReleaseEvent(event)

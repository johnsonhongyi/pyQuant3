# -*- coding: utf-8 -*-
"""
HotSpotPopup - 热点详情弹窗
双击热点列表时显示详细信息和快速操作

功能：
- 显示股票基本信息（代码、名称、加入价、现价、盈亏）
- 显示历史K线缩略图
- 快速操作按钮（设置止损、调整分组、移除）
- 信号历史列表
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QGroupBox, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

import pyqtgraph as pg
import numpy as np
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor

logger = logging.getLogger(__name__)

DB_FILE = "signal_strategy.db"


class HotSpotPopup(QDialog, WindowMixin):
    """
    热点详情弹窗
    
    信号：
    - group_changed: 分组已更改
    - stop_loss_set: 止损已设置
    - item_removed: 项目已移除
    """
    
    group_changed = pyqtSignal(str, str)  # code, new_group
    stop_loss_set = pyqtSignal(str, float)  # code, stop_loss_price
    item_removed = pyqtSignal(str)  # code
    
    def __init__(self, code: str, name: str, add_price: float, parent=None):
        super().__init__(parent)
        self.code = code
        self.name = name
        self.add_price = add_price
        self.current_price = add_price
        self.pnl_percent = 0.0
        self.scale_factor = get_windows_dpi_scale_factor()
        
        self._init_ui()
        self._load_signal_history()
        self._load_kline_preview()

        # 加载保存的位置
        self.load_window_position_qt(self, "HotSpotPopup", default_width=500, default_height=450)
    
    def done(self, a0: int) -> None: # type: ignore
        """对话框关闭、接受或拒绝的统一终点"""
        try:
            # 统一保存位置 (此时窗口依然存在且几何信息有效)
            self.save_window_position_qt(self, "HotSpotPopup")
        except Exception as e:
            logger.error(f"Save position in done error: {e}")
        super().done(a0)
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"热点详情 - {self.code} {self.name}")
        self.setMinimumSize(500, 450)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ddd;
            }
            QGroupBox {
                color: #FFD700;
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
            QPushButton {
                background-color: #333;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background-color: #555;
            }
            QLineEdit {
                background-color: #2a2a2a;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 4px 8px;
            }
            QComboBox {
                background-color: #2a2a2a;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 4px 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # === 顶部：基本信息 ===
        info_group = QGroupBox("📊 基本信息")
        info_layout = QGridLayout(info_group)
        
        # 股票代码和名称
        code_label = QLabel(f"<b style='font-size:14pt; color:#FFD700'>{self.code}</b>")
        code_label.setTextFormat(Qt.TextFormat.RichText)
        name_label = QLabel(f"<b style='font-size:12pt'>{self.name}</b>")
        name_label.setTextFormat(Qt.TextFormat.RichText)
        
        info_layout.addWidget(code_label, 0, 0)
        info_layout.addWidget(name_label, 0, 1)
        
        # 价格信息
        info_layout.addWidget(QLabel("加入价:"), 1, 0)
        self.add_price_label = QLabel(f"¥{self.add_price:.2f}")
        self.add_price_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.add_price_label, 1, 1)
        
        info_layout.addWidget(QLabel("现价:"), 1, 2)
        self.current_price_label = QLabel(f"¥{self.current_price:.2f}")
        info_layout.addWidget(self.current_price_label, 1, 3)
        
        info_layout.addWidget(QLabel("盈亏:"), 2, 0)
        self.pnl_label = QLabel(f"{self.pnl_percent:+.2f}%")
        self._update_pnl_style()
        info_layout.addWidget(self.pnl_label, 2, 1)
        
        layout.addWidget(info_group)
        
        # === 中部：K线缩略图 ===
        kline_group = QGroupBox("📈 K线走势 (近30日)")
        kline_layout = QVBoxLayout(kline_group)
        
        self.kline_widget = pg.PlotWidget()
        self.kline_widget.setFixedHeight(120)
        self.kline_widget.setBackground('#1e1e1e')
        self.kline_widget.showGrid(x=True, y=True, alpha=0.3)
        self.kline_widget.hideAxis('bottom')
        kline_layout.addWidget(self.kline_widget)
        
        layout.addWidget(kline_group)
        
        # === 操作区 ===
        action_group = QGroupBox("⚙️ 快速操作")
        action_layout = QHBoxLayout(action_group)
        
        # 分组选择
        action_layout.addWidget(QLabel("分组:"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(["观察", "蓄势", "已启动", "持仓"])
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        action_layout.addWidget(self.group_combo)
        
        action_layout.addSpacing(20)
        
        # 止损设置
        action_layout.addWidget(QLabel("止损价:"))
        self.stop_loss_edit = QLineEdit()
        self.stop_loss_edit.setFixedWidth(80)
        self.stop_loss_edit.setText(f"{self.current_price:.2f}")
        self.stop_loss_edit.setPlaceholderText("0.00")
        action_layout.addWidget(self.stop_loss_edit)
        
        set_stop_btn = QPushButton("设置")
        set_stop_btn.clicked.connect(self._on_set_stop_loss)
        action_layout.addWidget(set_stop_btn)
        
        action_layout.addStretch()
        
        # 移除按钮
        remove_btn = QPushButton("❌ 移除")
        remove_btn.setStyleSheet("QPushButton { color: #ff6b6b; }")
        remove_btn.clicked.connect(self._on_remove)
        action_layout.addWidget(remove_btn)
        
        layout.addWidget(action_group)
        
        # === 信号历史 ===
        signal_group = QGroupBox("📋 信号历史")
        signal_layout = QVBoxLayout(signal_group)
        
        self.signal_table = QTableWidget()
        self.signal_table.setColumnCount(4)
        self.signal_table.setHorizontalHeaderLabels(["时间", "类型", "评分", "理由"])
        self.signal_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.signal_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # self.signal_table.setMaximumHeight(120)  # Removed to allow expansion
        self.signal_table.setMinimumHeight(150) # Set a reasonable minimum height
        self.signal_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        header = self.signal_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.signal_table.verticalHeader().setVisible(False)
        
        self.signal_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #ddd;
                border: none;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #aaa;
                border: none;
                padding: 4px;
            }
        """)
        
        signal_layout.addWidget(self.signal_table)
        layout.addWidget(signal_group)
        
        # === 底部按钮 ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def update_price(self, current_price: float):
        """更新当前价格"""
        # 记录旧价格用于比对
        old_price_txt = f"{self.current_price:.2f}"
        
        self.current_price = current_price
        self.current_price_label.setText(f"¥{current_price:.2f}")
        
        # [NEW] 如果止损输入框还是初始价格或为空，则自动同步为最新现价
        if hasattr(self, 'stop_loss_edit'):
            current_edit_txt = self.stop_loss_edit.text()
            if not current_edit_txt or current_edit_txt == old_price_txt or current_edit_txt == "0.00":
                self.stop_loss_edit.setText(f"{current_price:.2f}")
        
        if self.add_price > 0:
            self.pnl_percent = (current_price - self.add_price) / self.add_price * 100
            self.pnl_label.setText(f"{self.pnl_percent:+.2f}%")
            self._update_pnl_style()
    
    def _update_pnl_style(self):
        """根据盈亏更新颜色"""
        if self.pnl_percent > 0:
            self.pnl_label.setStyleSheet("color: #dc5050; font-weight: bold;")
        elif self.pnl_percent < 0:
            self.pnl_label.setStyleSheet("color: #50c878; font-weight: bold;")
        else:
            self.pnl_label.setStyleSheet("color: #888;")
    
    def _load_signal_history(self):
        """加载该股票的信号历史"""
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT timestamp, signal_type, score, reason 
                FROM signal_message 
                WHERE code = ?
                ORDER BY timestamp DESC
                LIMIT 50
            """, (self.code,))
            rows = c.fetchall()
            conn.close()
            
            self.signal_table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.signal_table.setItem(i, 0, QTableWidgetItem(r['timestamp'] or ""))
                self.signal_table.setItem(i, 1, QTableWidgetItem(r['signal_type'] or ""))
                score_item = QTableWidgetItem(f"{r['score']:.1f}" if r['score'] else "-")
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.signal_table.setItem(i, 2, score_item)
                self.signal_table.setItem(i, 3, QTableWidgetItem(r['reason'] or ""))
                
        except Exception as e:
            logger.error(f"Load signal history error: {e}")
    
    def _load_kline_preview(self):
        """加载K线缩略图"""
        try:
            # 尝试从父窗口获取day_df
            parent = self.parent()
            if parent and hasattr(parent, 'day_df') and not parent.day_df.empty:
                df = parent.day_df.tail(30)
                if not df.empty and 'close' in df.columns:
                    closes = df['close'].values
                    x = np.arange(len(closes))
                    
                    # 绘制收盘价曲线
                    pen = pg.mkPen(color='#FFD700', width=1.5)
                    self.kline_widget.plot(x, closes, pen=pen)
                    
                    # 添加加入价参考线
                    if self.add_price > 0:
                        add_line = pg.InfiniteLine(
                            pos=self.add_price, 
                            angle=0, 
                            pen=pg.mkPen('#ff6b6b', width=1, style=Qt.PenStyle.DashLine)
                        )
                        self.kline_widget.addItem(add_line)
        except Exception as e:
            logger.debug(f"Load kline preview error: {e}")
    
    def _on_group_changed(self, new_group: str):
        """分组变更"""
        self.group_changed.emit(self.code, new_group)
    
    def _on_set_stop_loss(self):
        """设置止损"""
        try:
            stop_loss = float(self.stop_loss_edit.text())
            if stop_loss > 0:
                self.stop_loss_set.emit(self.code, stop_loss)
                logger.info(f"设置止损: {self.code} @ {stop_loss:.2f}")
        except ValueError:
            pass
    
    def _on_remove(self):
        """移除热点"""
        self.item_removed.emit(self.code)
        self.accept()

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
    QCheckBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QPoint
from PyQt6.QtGui import QAction, QColor, QFont

from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import get_windows_dpi_scale_factor
from trading_logger import TradingLogger
from JohnsonUtil.stock_sender import StockSender

class NumericTableWidgetItem(QTableWidgetItem):
    """自定义 TableWidgetItem，支持正确的数值排序"""
    def __init__(self, value):
        if isinstance(value, (int, float)):
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
    # 联动信号：(code, name, select_win)
    stock_selected_signal = pyqtSignal(str, str, bool)
    status_msg_signal = pyqtSignal(str)          # (message)
    window_closed_signal = pyqtSignal()          # 窗口关闭通知

    def __init__(self, parent=None, on_select_callback=None, sender=None):
        super().__init__(parent)
        self.setWindowTitle("实时信号历史轨迹查询")
        self.on_select_callback = on_select_callback
        
        # 1. 基础配置
        self.scale_factor = get_windows_dpi_scale_factor()
        self.logger_tool = TradingLogger()
        self._refresh_timer = QTimer(self) # 显式创建计时器，方便清理
        
        self.sender = sender # 优先复用主界面的发送器
        if self.sender is None:
            try:
                from JohnsonUtil.stock_sender import StockSender
                self.sender = StockSender(callback=None)
            except Exception:
                self.sender = None
        
        # 2. UI 构造
        self._init_ui()
        
        # 3. 绑定信号 (核心：解决 GIL 引起的 Thread Safety 问题)
        self.stock_selected_signal.connect(self._safe_execute_callback)
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
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("YYYY-MM-DD")
        self.date_input.setText(datetime.now().strftime("%Y-%m-%d"))
        self.date_input.setFixedWidth(int(110 * self.scale_factor))
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
        
        self.auto_refresh_cb = QCheckBox("自动刷新(3s)")
        self.auto_refresh_cb.toggled.connect(self._toggle_auto_refresh)
        ctrl_layout.addWidget(self.auto_refresh_cb)
        
        ctrl_layout.addStretch()
        
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
        
        # 定义列
        self.headers = ["时间", "代码", "名称", "动作", "价格", "理由", "周期", "状态", "ID"]
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        
        # 交互联动 (单击/键盘切换触发)
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.currentCellChanged.connect(self.on_current_cell_changed)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # 计时器逻辑
        self._refresh_timer.timeout.connect(self.refresh_data)
        
        layout.addWidget(self.table)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 10pt;")
        layout.addWidget(self.status_label)

    def refresh_data(self):
        """异步/安全 刷新数据"""
        date_str = self.date_input.text().strip() or None
        code_str = self.code_input.text().strip() or None
        
        self.status_msg_signal.emit("正在同步数据库...")
        
        # 获取数据 (目前的 logger 访问是阻塞的，若数据量极大可考虑 QThread，目前 2000 条以内直接刷)
        df = self.logger_tool.get_live_signal_history_df(date=date_str, code=code_str, limit=2000)
        
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        if df.empty:
            self.status_msg_signal.emit(f"查询报告: 未发现匹配信号 ({datetime.now().strftime('%H:%M:%S')})")
            return

        self.table.setRowCount(len(df))
        for row_idx, row in df.iterrows():
            # 列映射: timestamp, code, name, action, price, reason, resample, status, id
            values = [
                row.get('timestamp', ''),
                row.get('code', ''),
                row.get('name', ''),
                row.get('action', ''),
                row.get('price', 0.0),
                row.get('reason', ''),
                row.get('resample', 'd'),
                row.get('status', 'NEW'),
                row.get('id', 0)
            ]
            
            for col_idx, val in enumerate(values):
                item = NumericTableWidgetItem(val)
                # 动作列高亮
                if col_idx == 3:
                    act_str = str(val)
                    if any(x in act_str for x in ['买', 'UP', '突破', 'STAR']):
                        item.setForeground(QColor("#e74c3c"))
                        item.setFont(QFont("Arial", weight=QFont.Weight.Bold))
                    elif any(x in act_str for x in ['卖', 'DOWN', '退出']):
                        item.setForeground(QColor("#27ae60"))
                self.table.setItem(row_idx, col_idx, item)
                
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        
        # 列宽自适应
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch) # 理由列拉伸
        
        self.status_msg_signal.emit(f"就绪: 统计到 {len(df)} 条轨迹轨迹 ({datetime.now().strftime('%H:%M:%S')})")

    def on_item_clicked(self, item):
        """单击表格行联动 K 线 (默认不触发推送)"""
        self._trigger_linkage(item.row(), select_win=False)

    def on_current_cell_changed(self, row, col, prev_row, prev_col):
        """键盘上下键切换行时触发联动 (默认不触发推送)"""
        if row < 0 or row == prev_row:
            return
        self._trigger_linkage(row, select_win=False)

    def _trigger_linkage(self, row, select_win=False):
        """统一触发联动逻辑"""
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and name_item:
            code = code_item.text().strip()
            name = name_item.text().strip()
            self.stock_selected_signal.emit(code, name, select_win)

    def _safe_execute_callback(self, code, name, select_win=False):
        """核心：在 GUI 信号处理中安全执行回调，避免 GIL 冲突"""
        # 清理空格，防止 Pandas 查询或 TDX 联动出错
        code = str(code).strip()
        name = str(name).strip()
        
        self.status_label.setText(f"🚀 已联动主程序: {code} {name} (Push:{select_win})")
        # 1. 触发外部(Tkinter/Process)回调
        if self.on_select_callback:
            try:
                # 传入 select_win 参数
                self.on_select_callback(code, name, select_win=select_win)
            except Exception as e:
                print(f"Callback error (LiveSignalViewer): {e}")
        
        # 2. 模拟发送指令 (联动通达信或其他软件端口)
        # 使用 callable 或是 hasattr 检查
        if self.sender:
            try:
                if hasattr(self.sender, 'send_code'):
                    self.sender.send_code({'code': code, 'name': name})
                elif hasattr(self.sender, 'send'):
                    self.sender.send(code)
            except Exception as e:
                print(f"Sender error (LiveSignalViewer): {e}")

    def keyPressEvent(self, a0):
        """增强键盘导航联动支持 (Up/Down/PageUp/PageDown/Home/End)"""
        # 交给父类处理基本的选区移动
        super().keyPressEvent(a0)
        
        # 检查是否是导航键
        nav_keys = [
            Qt.Key.Key_Up, Qt.Key.Key_Down, 
            Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, 
            Qt.Key.Key_Home, Qt.Key.Key_End
        ]
        if a0.key() in nav_keys:
            row = self.table.currentRow()
            if row >= 0:
                # 触发静默联动
                self._trigger_linkage(row, select_win=False)

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
        
        menu = QMenu(self)
        
        copy_action = QAction("📋 复制代码", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(code))
        menu.addAction(copy_action)
        
        link_action = QAction("🎯 联动 K 线 (不跳转)", self)
        link_action.triggered.connect(lambda: self.stock_selected_signal.emit(code, name, False))
        menu.addAction(link_action)

        jump_action = QAction("🚀 定位股票 (触发推送)", self)
        jump_action.triggered.connect(lambda: self.stock_selected_signal.emit(code, name, True))
        menu.addAction(jump_action)
        
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

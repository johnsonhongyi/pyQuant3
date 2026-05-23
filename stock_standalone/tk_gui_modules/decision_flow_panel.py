# -*- coding: utf-8 -*-
import json
import os
import time
import sys
import traceback
from datetime import datetime
from typing import Any, Optional

from PyQt6 import QtWidgets, QtCore, QtGui
from tk_gui_modules.window_mixin import WindowMixin
from JohnsonUtil import LoggerFactory
from stock_logic_utils import toast_message

logger = LoggerFactory.getLogger("instock_TK.DecisionFlowPanel")


class DecisionFlowPanel(QtWidgets.QWidget, WindowMixin):
    """
    ⚡ 交易内核决策流水分析面板 (Trading Kernel Decision Flow)
    采用 PyQt6 构建的只读高性能监控看板，完美适配 Windows 多进程并发环境。
    """
    # 股票点击跳转信号 (code, name)
    code_clicked = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None, journal_path: str = "logs/trading_kernel_trace.jsonl"):
        super().__init__()
        self.parent_app = parent
        self.journal_path = journal_path
        self._last_file_size = 0
        self._last_modified_time = 0.0
        
        self.setWindowFlags(QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.WindowMinMaxButtonsHint | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("⚡ 交易内核决策流水分析 (Trading Kernel Decision Flow)")
        
        # 继承 WindowMixin 缩放因子
        self.scale_factor = getattr(self.parent_app, "scale_factor", 1.0)
        
        # 1. 初始化 UI 与组件布局 (Cyberpunk Dark Mode)
        self._init_ui()
        
        # 2. 载入窗口历史尺寸与位置
        self.load_window_position_qt(self, "DecisionFlowPanel", default_width=1100, default_height=550)
        
        # 3. 首次全量扫描载入 (最多 200 条，防冷启动白屏)
        self._load_initial_records()
        
        # 4. 启动定时器：每 500ms 增量扫描更新，实现真正的零 CPU 负荷监控
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._check_and_update_records)
        self.timer.start(500)

    def _init_ui(self):
        """初始化极富科技感、暗黑渐变之美的决策监控界面 (Premium Dark Mode)"""
        # 全局 Cyberpunk 调色板
        self.setStyleSheet("""
            QWidget {
                background-color: #121214;
                color: #E2E2E6;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 11px;
            }
            QTableWidget {
                background-color: #16161A;
                border: 1px solid #232328;
                gridline-color: #232328;
                color: #D2D2D6;
                alternate-background-color: #1A1A1F;
                selection-background-color: #2A2A35;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #1E1E24;
                color: #A0A0A5;
                padding: 5px;
                border: none;
                border-bottom: 2px solid #282830;
                font-weight: bold;
            }
            QPushButton {
                background-color: #1E1E24;
                border: 1px solid #2E2E35;
                border-radius: 3px;
                padding: 4px 10px;
                color: #C2C2C6;
            }
            QPushButton:hover {
                background-color: #2E2E38;
                border-color: #00E676;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #16161B;
            }
            QLineEdit {
                background-color: #16161A;
                border: 1px solid #232328;
                border-radius: 3px;
                padding: 3px 5px;
                color: #FFFFFF;
            }
            QLabel {
                color: #A0A0A5;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 头部控制栏 (扁平紧凑)
        top_bar = QtWidgets.QHBoxLayout()
        
        title_label = QtWidgets.QLabel("🎯 决策流水监控:")
        title_label.setStyleSheet("font-weight: bold; color: #00E676; font-size: 12px;")
        top_bar.addWidget(title_label)

        # 搜索过滤框
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText(" 输入股票代码/名称/动作进行过滤...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._filter_table)
        top_bar.addWidget(self.search_input)

        top_bar.addStretch()

        # 一键手工刷新与清理按钮
        refresh_btn = QtWidgets.QPushButton("🔄 手工刷新")
        refresh_btn.clicked.connect(self._force_reload)
        top_bar.addWidget(refresh_btn)

        clear_btn = QtWidgets.QPushButton("🧹 清空显示")
        clear_btn.clicked.connect(self._clear_view)
        top_bar.addWidget(clear_btn)

        layout.addLayout(top_bar)

        # 主数据表格 (只读)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(12)
        headers = [
            "时间", "代码", "名称", "前态", "动作", 
            "拟仓位", "打分", "风控结果", "阻断码", 
            "止损价", "Trace ID", "决策理由摘要"
        ]
        self.table.setHorizontalHeaderLabels(headers)
        
        # 基础行为配置
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        
        # 表头拉伸策略
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # 绑定双击行进行代码联动
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        layout.addWidget(self.table)

        # 底部状态栏
        bottom_bar = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("初始化完成。正在监听交易内核流水...")
        bottom_bar.addWidget(self.status_label)
        layout.addLayout(bottom_bar)

        # 默认列宽微调 (适应 1100 初始宽度)
        widths = [75, 65, 75, 60, 60, 60, 50, 75, 80, 65, 75, 300]
        for idx, w in enumerate(widths):
            self.table.setColumnWidth(idx, int(w * self.scale_factor))

    def _on_cell_double_clicked(self, row, column):
        """双击表格行，提取股票代码并向主进程派发跳转联动"""
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            logger.info(f"Double clicked on DecisionFlow: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

    def _load_initial_records(self):
        """冷启动时快速扫描读取 JSONL 末尾最多 200 条决策，规避白屏"""
        if not os.path.exists(self.journal_path):
            self.status_label.setText("⚠️ 未检测到交易流水日志文件 logs/trading_kernel_trace.jsonl")
            return

        try:
            file_size = os.path.getsize(self.journal_path)
            self._last_file_size = file_size
            self._last_modified_time = os.path.getmtime(self.journal_path)

            records = []
            with open(self.journal_path, "r", encoding="utf-8") as f:
                # 采用简单、安全的尾部行扫描，提取最后 300 行 JSON，避免全文件解析的爆内存问题
                lines = f.readlines()[-300:]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue

            # 仅截取最后 200 条进行表格渲染
            records = records[-200:]
            self.table.setRowCount(0)
            for rec in records:
                self._append_record_to_table(rec)

            self.status_label.setText(f"✅ 成功载入历史 {len(records)} 条决策，实时监听中...")
            # 自动滚动到最新一行
            self.table.scrollToBottom()
        except Exception as e:
            logger.error(f"Failed to load initial records: {e}\n{traceback.format_exc()}")
            self.status_label.setText(f"❌ 载入历史流水失败: {e}")

    def _check_and_update_records(self):
        """定时扫描函数：比对文件大小与修改时间，以绝对零开销增量追溯最新决策"""
        if not os.path.exists(self.journal_path):
            return

        try:
            file_size = os.path.getsize(self.journal_path)
            if file_size == self._last_file_size:
                return

            mtime = os.path.getmtime(self.journal_path)
            
            # 若文件被物理截断或重建，则全量重载
            if file_size < self._last_file_size:
                logger.info("Journal file truncated, reloading...")
                self._load_initial_records()
                return

            # 精准的增量尾部寻址读取 (零拷贝，高速定位)
            new_records = []
            with open(self.journal_path, "r", encoding="utf-8") as f:
                f.seek(self._last_file_size)
                new_lines = f.readlines()
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        new_records.append(json.loads(line))
                    except Exception:
                        continue

            # 更新追踪指针
            self._last_file_size = file_size
            self._last_modified_time = mtime

            # 增量追加至表格
            if new_records:
                for rec in new_records:
                    self._append_record_to_table(rec)
                self.status_label.setText(f"⚡ 增量更新完成，新捕获 {len(new_records)} 条决策信号 (最新更新: {time.strftime('%H:%M:%S')})")
                self.table.scrollToBottom()
                # 重新应用过滤
                self._filter_table()
        except Exception as e:
            logger.error(f"Error in incremental records check: {e}")

    def _append_record_to_table(self, rec: dict):
        """核心解析函数：从 `JsonlJournal` 的多级 nested 结构中精准提炼出扁平的 UI 字段并渲染"""
        # 1. 字段解包
        trace = rec.get("trace", {})
        sig = rec.get("signal", {})
        intent = rec.get("intent", {})
        risk = rec.get("risk", {})
        
        # 2. 字段映射提取
        # 时间 (提取 HH:MM:SS)
        ts_str = rec.get("journal_ts", "") or trace.get("timestamp", "")
        if ts_str:
            try:
                # 比如 2026-05-23T19:52:02 -> 19:52:02
                if "T" in ts_str:
                    time_part = ts_str.split("T")[1]
                    timestamp = time_part[:8]
                else:
                    timestamp = ts_str[-8:]
            except Exception:
                timestamp = ts_str
        else:
            timestamp = datetime.now().strftime("%H:%M:%S")

        code = sig.get("code", "")
        name = sig.get("name", "")
        
        # 状态 (前置状态)
        state = rec.get("kernel_state", "") or trace.get("state", "FLAT")
        
        # 动作 (BUY, SELL 等)
        action = rec.get("kernel_action", "") or risk.get("final_action", "")
        
        # 拟仓位比率
        size_val = rec.get("kernel_size_pct", 0.0) or risk.get("final_size_pct", 0.0)
        size_pct = f"{float(size_val):.1f}%" if size_val is not None else "0.0%"
        
        # 决策打分/信心
        confidence = str(rec.get("kernel_confidence", "") or intent.get("confidence", ""))
        
        # 风控评估结果 (Allowed/Blocked)
        allowed_val = risk.get("allowed", True)
        risk_allowed = "Allowed" if allowed_val else "Blocked"
        
        # 风控阻断码
        reject_code = rec.get("kernel_reject_code", "")
        if not reject_code and not allowed_val:
            reject_code = risk.get("reject_context", {}).get("code", "RISK_REJECT")
        
        # 移动止损价
        stop_price_val = rec.get("kernel_stop_price", 0.0) or intent.get("stop_price", 0.0)
        stop_price = f"{float(stop_price_val):.2f}" if stop_price_val else "0.00"
        
        # Trace ID (截取 8 位作为防伪展示)
        trace_id = trace.get("trace_id", "") or rec.get("kernel_trace_id", "")
        short_trace_id = trace_id[:8] if trace_id else "N/A"
        
        # 决策理由摘要 (合并 is_leader / Hits / raw_reason 提取有用信息)
        reason_summary = ""
        features = sig.get("features", {})
        is_leader = features.get("is_leader", False)
        priority = features.get("priority", 0.0)
        raw_reason = features.get("raw_reason", "")
        
        reason_parts = []
        if is_leader:
            reason_parts.append("⭐龙头领涨")
        if priority and priority > 0:
            reason_parts.append(f"强度:{priority}")
        
        # 融合 kernel_reason 里面的子项
        kernel_reason = rec.get("kernel_reason", {})
        for r_k, r_v in kernel_reason.items():
            if r_v and str(r_v).strip().lower() != "false":
                reason_parts.append(f"{r_k}={r_v}")
        
        if raw_reason:
            reason_parts.append(raw_reason)
            
        reason_summary = " | ".join(reason_parts) if reason_parts else "常规扫描决策"

        # 3. 动态追加物理表格行
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        # 4. 卡片着色与项目填充
        items_data = [
            (timestamp, None),
            (code, "#FFFFFF"),
            (name, "#C2C2C6"),
            (state, "#90A4AE"),  # 状态使用温和蓝灰色
            (action, None),     # 动作根据买卖着色
            (size_pct, None),
            (confidence, "#FFEB3B"), # 打分高亮黄
            (risk_allowed, None),    # 风控红绿卡片
            (str(reject_code), "#FF8A80"),
            (stop_price, "#B0BEC5"),
            (short_trace_id, "#78909C"),
            (reason_summary, "#81C784")  # 决策理由柔和绿色
        ]

        # 颜色映射表
        action_colors = {
            "BUY": "#00E676",      # 亮盈绿
            "ADD": "#00E5FF",      # 亮青
            "SELL": "#FF1744",     # 猩红
            "REDUCE": "#FF9100",   # 橙红
            "FLAT": "#90A4AE"      # 蓝灰
        }

        for col_idx, (text, color_hex) in enumerate(items_data):
            cell_item = QtWidgets.QTableWidgetItem(str(text))
            cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            
            # 设置默认前景色
            if color_hex:
                cell_item.setForeground(QtGui.QColor(color_hex))
                
            # 个性化高亮
            if col_idx == 4:  # Action
                act_upper = str(text).upper()
                if act_upper in action_colors:
                    cell_item.setForeground(QtGui.QColor(action_colors[act_upper]))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 10, QtGui.QFont.Weight.Bold))
            elif col_idx == 5 and action in ("BUY", "ADD"): # Pct
                cell_item.setForeground(QtGui.QColor("#00E676"))
            elif col_idx == 7: # Risk Allowed
                if text == "Allowed":
                    cell_item.setForeground(QtGui.QColor("#00E676"))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                else:
                    cell_item.setForeground(QtGui.QColor("#FF1744"))
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
            elif col_idx == 10 and trace_id: # Trace ID 悬浮提示
                cell_item.setToolTip(f"防伪全量签名 ID: {trace_id}")
                
            self.table.setItem(row_idx, col_idx, cell_item)

    def _filter_table(self):
        """本地搜索快速过滤逻辑，无需重读磁盘，体验流畅"""
        query = self.search_input.text().strip().lower()
        for row in range(self.table.rowCount()):
            if not query:
                self.table.setRowHidden(row, False)
                continue
                
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and query in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _force_reload(self):
        """强制清空重载 (自愈修复时一键恢复)"""
        logger.info("Force reloading decision flow logs...")
        self._load_initial_records()
        toast_message(self.parent_app, "决策流水已强制重载")

    def _clear_view(self):
        """清空当前表格显示 (不删除物理文件)"""
        self.table.setRowCount(0)
        self.status_label.setText("显示已清空。等待新增决策流水信号...")
        toast_message(self.parent_app, "表格显示已清空")

    def closeEvent(self, event):
        """窗口关闭时自动注销并保存位置参数"""
        try:
            self.save_window_position_qt_visual(self, "DecisionFlowPanel")
            logger.info("DecisionFlowPanel position state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save window state: {e}")
        
        # 从父窗口引用中抹除，有利于 GC 回收
        if self.parent_app and hasattr(self.parent_app, "panel_manager"):
            self.parent_app.panel_manager._decision_flow_win = None
            
        event.accept()

    def showEvent(self, event):
        """展现时自适应"""
        super().showEvent(event)
        self.table.scrollToBottom()

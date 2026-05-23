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
        
        # 1.5 初始化防抖过滤计时器
        self._filter_timer = QtCore.QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._filter_table)
        
        # 2. 载入窗口历史尺寸与位置
        self.load_window_position_qt(self, "DecisionFlowPanel", default_width=1100, default_height=550)
        
        # 2.5 恢复列宽与表头状态
        has_restored = self._restore_header_state()
        if not has_restored:
            # 仅在无历史保存的手动调整配置时，才去执行默认的极致初始列宽自适应
            self._adjust_column_widths()
        
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
                padding: 1px 2px;
                border: none;
                border-bottom: 2px solid #282830;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 0px 1px;
            }
            QTabWidget::pane {
                border: 1px solid #232328;
                background-color: #121214;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1E1E24;
                color: #A0A0A5;
                border: 1px solid #2E2E35;
                padding: 6px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                margin-right: 2px;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background-color: #16161A;
                color: #00E676;
                border-bottom-color: #16161A;
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

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # 引入 QTabWidget 进行多维决策分类
        self.tabs = QtWidgets.QTabWidget()
        
        # ==========================================
        # 1. ⚡ 决策流水监控 页签
        # ==========================================
        flow_widget = QtWidgets.QWidget()
        flow_layout = QtWidgets.QVBoxLayout(flow_widget)
        flow_layout.setContentsMargins(6, 6, 6, 6)
        flow_layout.setSpacing(6)

        # 头部控制栏 (扁平紧凑)
        top_bar = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("🎯 决策流水监控:")
        title_label.setStyleSheet("font-weight: bold; color: #00E676; font-size: 12px;")
        top_bar.addWidget(title_label)

        # 搜索过滤框
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText(" 输入股票代码/名称/动作进行过滤...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        top_bar.addWidget(self.search_input)

        top_bar.addStretch()

        # 一键手工刷新与清理按钮
        refresh_btn = QtWidgets.QPushButton("🔄 手工刷新")
        refresh_btn.clicked.connect(self._force_reload)
        top_bar.addWidget(refresh_btn)

        clear_btn = QtWidgets.QPushButton("🧹 清空显示")
        clear_btn.clicked.connect(self._clear_view)
        top_bar.addWidget(clear_btn)

        flow_layout.addLayout(top_bar)

        # 主数据表格 (只读)
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(12)
        headers = [
            "日期时间", "代码", "名称", "前态", "动作", 
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
        self.table.verticalHeader().setDefaultSectionSize(18)
        
        # 启用右键菜单支持
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # 表头拉伸策略
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # 绑定双击行进行代码联动
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        flow_layout.addWidget(self.table)
        
        self.tabs.addTab(flow_widget, "⚡ 决策流水监控 (Decision Flow)")

        # ==========================================
        # 2. 💼 内核实时持仓 页签
        # ==========================================
        pos_widget = QtWidgets.QWidget()
        pos_layout = QtWidgets.QVBoxLayout(pos_widget)
        pos_layout.setContentsMargins(6, 6, 6, 6)
        pos_layout.setSpacing(6)

        # 持仓数据表格 (只读)
        self.pos_table = QtWidgets.QTableWidget()
        self.pos_table.setColumnCount(8)
        pos_headers = ["代码", "名称", "持仓股数", "买入均价", "当前市价", "持仓市值", "浮动盈亏", "盈亏比例"]
        self.pos_table.setHorizontalHeaderLabels(pos_headers)
        
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.pos_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.verticalHeader().setDefaultSectionSize(18)
        
        # 绑定双击持仓代码跳转
        self.pos_table.cellDoubleClicked.connect(self._on_pos_cell_double_clicked)
        
        pos_header = self.pos_table.horizontalHeader()
        pos_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        pos_header.setStretchLastSection(True)
        pos_layout.addWidget(self.pos_table)

        # 底部发光大卡片栏 (Summary metrics cards)
        summary_layout = QtWidgets.QHBoxLayout()
        summary_layout.setSpacing(8)
        
        self.cards = {}
        card_metrics = [
            ("cash", "💰 可用现金", "#E2E2E6"),
            ("equity", "📊 账户总资产", "#00E5FF"),
            ("market_value", "💼 持仓总市值", "#00E676"),
            ("total_pnl", "📈 账户总盈亏", "#FF1744"),
            ("ratio", "⚖️ 仓位使用率", "#FF9100")
        ]
        
        for key, name, color in card_metrics:
            card = QtWidgets.QFrame()
            card.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
            card.setStyleSheet("""
                QFrame {
                    background-color: #16161A;
                    border: 1px solid #232328;
                    border-radius: 5px;
                    padding: 4px;
                }
            """)
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setSpacing(1)
            card_layout.setContentsMargins(4, 4, 4, 4)
            
            lbl = QtWidgets.QLabel(name)
            lbl.setStyleSheet("font-size: 9px; color: #88888D;")
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
            
            val = QtWidgets.QLabel("¥ 0.00")
            val.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
            val.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            
            card_layout.addWidget(lbl)
            card_layout.addWidget(val)
            summary_layout.addWidget(card)
            self.cards[key] = val
            
        pos_layout.addLayout(summary_layout)
        self.tabs.addTab(pos_widget, "💼 内核实时持仓 (Kernel Positions & PnL)")

        main_layout.addWidget(self.tabs)

        # 底部状态栏
        bottom_bar = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("初始化完成。正在监听交易内核流水与持仓...")
        bottom_bar.addWidget(self.status_label)
        main_layout.addLayout(bottom_bar)

        # 应用自适应列宽分配
        self._adjust_column_widths()

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
            
            # 首次载入同步加载实时持仓明细页
            self._refresh_positions_tab()
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
                
            # 同步刷新实时持仓与盈亏标签页
            self._refresh_positions_tab()
        except Exception as e:
            logger.error(f"Error in incremental records check: {e}")

    def _parse_timestamp(self, ts_str: Any) -> str:
        """防弹自愈时间戳解析器：统一格式化为 MM-DD HH:MM:SS"""
        if not ts_str:
            return datetime.now().strftime("%m-%d %H:%M:%S")
        try:
            ts_str_clean = str(ts_str).strip()
            if "T" in ts_str_clean:
                parts = ts_str_clean.split("T")
                date_part = parts[0][5:] # "05-23"
                time_part = parts[1][:8] # "20:30:15"
                return f"{date_part} {time_part}"
            elif " " in ts_str_clean:
                parts = ts_str_clean.split(" ")
                date_part = parts[0][5:]
                time_part = parts[1][:8]
                return f"{date_part} {time_part}"
            elif len(ts_str_clean) >= 8:
                return ts_str_clean[-8:]
            else:
                return ts_str_clean
        except Exception:
            return str(ts_str)

    def _append_record_to_table(self, rec: dict):
        """核心解析函数：从 `JsonlJournal` 的多级 nested 结构或人工确认审计日志中精准提炼出扁平 of UI 字段并渲染"""
        # 判断是否为人工确认审计记录 (Phase 7: Human Confirmation Audit)
        is_audit = (rec.get("journal_type") == "HUMAN_CONFIRMATION_AUDIT")
        
        if is_audit:
            orig_order = rec.get("original_order", {})
            confirmed = rec.get("confirmed", False)
            reason = rec.get("override_reason", "")
            meta = rec.get("override_metadata", {})
            
            # 提取时间 (防弹 Fallback)
            timestamp = self._parse_timestamp(rec.get("timestamp", ""))
            
            code = orig_order.get("code", "")
            name = "人工确认"
            state = "AUDIT"
            
            # 下单占比微调渲染
            orig_size = float(orig_order.get("size_pct", 0.0)) * 100.0
            if meta.get("size_changed"):
                act_size = float(meta.get("actual_size_pct", 0.0)) * 100.0
                size_pct = f"{orig_size:.1f}% ➔ {act_size:.1f}%"
                action = "✍️ 覆盖"
            else:
                size_pct = f"{orig_size:.1f}%"
                action = "👤 确认" if confirmed else "❌ 拒绝"
                
            confidence = "N/A"
            risk_allowed = "Confirmed" if confirmed else "Rejected"
            reject_code = "TRADER_REJECT" if not confirmed else ""
            stop_price = "N/A"
            trace_id = "AUDIT"
            short_trace_id = "AUDIT"
            
            # 合并理由
            reason_summary = f"👤 操盘手干预 | {reason}"
            if meta.get("size_changed"):
                reason_summary += f" | 占比微调: {orig_size:.0f}% ➔ {act_size:.0f}%"
                
        else:
            # 1. 字段解包 (常规决策 trace)
            trace = rec.get("trace", {})
            sig = rec.get("signal", {})
            intent = rec.get("intent", {})
            risk = rec.get("risk", {})
            
            # 2. 字段映射提取 (防弹 Fallback)
            timestamp = self._parse_timestamp(rec.get("journal_ts", "") or trace.get("timestamp", ""))
    
            code = sig.get("code", "")
            name = sig.get("name", "")
            state = rec.get("kernel_state", "") or trace.get("state", "FLAT")
            action = rec.get("kernel_action", "") or risk.get("final_action", "")
            
            size_val = rec.get("kernel_size_pct", 0.0) or risk.get("final_size_pct", 0.0)
            size_pct = f"{float(size_val):.1f}%" if size_val is not None else "0.0%"
            
            confidence = str(rec.get("kernel_confidence", "") or intent.get("confidence", ""))
            
            allowed_val = risk.get("allowed", True)
            risk_allowed = "Allowed" if allowed_val else "Blocked"
            
            reject_code = rec.get("kernel_reject_code", "")
            if not reject_code and not allowed_val:
                reject_code = risk.get("reject_context", {}).get("code", "RISK_REJECT")
            
            stop_price_val = rec.get("kernel_stop_price", 0.0) or intent.get("stop_price", 0.0)
            stop_price = f"{float(stop_price_val):.2f}" if stop_price_val else "0.00"
            
            trace_id = trace.get("trace_id", "") or rec.get("kernel_trace_id", "")
            short_trace_id = trace_id[:8] if trace_id else "N/A"
            
            reason_parts = []
            features = sig.get("features", {})
            is_leader = features.get("is_leader", False)
            priority = features.get("priority", 0.0)
            raw_reason = features.get("raw_reason", "")
            
            if is_leader:
                reason_parts.append("⭐龙头领涨")
            if priority and priority > 0:
                reason_parts.append(f"强度:{priority}")
            
            kernel_reason = rec.get("kernel_reason", {})
            if isinstance(kernel_reason, dict):
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
            elif col_idx == 5 and action in ("BUY", "ADD", "✍️ 覆盖", "👤 确认"): # Pct / Confirmation
                cell_item.setForeground(QtGui.QColor("#00E676"))
            elif col_idx == 7: # Risk Allowed / Confirmation status
                if text in ("Allowed", "Confirmed"):
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

    def _on_search_text_changed(self):
        """输入内容变动时防抖 150ms，规避高频重绘，提升流畅度"""
        self._filter_timer.start(150)

    def _show_context_menu(self, pos):
        """为表格行提供精美的右键快捷菜单，支持 Trace ID/代码/理由复制"""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
            
        row = index.row()
        menu = QtWidgets.QMenu(self)
        
        # 扁平精致暗黑菜单风格
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E24;
                color: #E2E2E6;
                border: 1px solid #2E2E35;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #00E676;
                color: #121214;
            }
        """)
        
        # 获取各单元格的值
        code_item = self.table.item(row, 1)
        trace_item = self.table.item(row, 10)
        reason_item = self.table.item(row, 11)
        
        trace_id = trace_item.toolTip().replace("防伪全量签名 ID: ", "") if trace_item else ""
        if not trace_id and trace_item:
            trace_id = trace_item.text()
            
        code = code_item.text().strip() if code_item else ""
        reason = reason_item.text().strip() if reason_item else ""
        
        # 动作一：复制 Trace ID
        if trace_id and trace_id != "N/A" and trace_id != "AUDIT":
            action_copy_trace = menu.addAction("📋 复制完整 Trace ID")
            action_copy_trace.triggered.connect(lambda: self._copy_to_clipboard(trace_id, "Trace ID"))
            
        # 动作二：复制股票代码
        if code:
            action_copy_code = menu.addAction(f"📋 复制股票代码 ({code})")
            action_copy_code.triggered.connect(lambda: self._copy_to_clipboard(code, "股票代码"))
            
        # 动作三：复制完整决策理由
        if reason:
            action_copy_reason = menu.addAction("📋 复制决策理由")
            action_copy_reason.triggered.connect(lambda: self._copy_to_clipboard(reason, "决策理由"))
            
        menu.exec(self.table.viewport().mapToGlobal(pos))
        
    def _copy_to_clipboard(self, text: str, label: str):
        """将文本安全复制到剪贴板，并弹出 Toast 提示"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        toast_message(self.parent_app, f"已复制 {label}")

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
        """窗口关闭时自动注销并保存位置及列宽参数"""
        try:
            # 1. 保存窗口尺寸
            self.save_window_position_qt_visual(self, "DecisionFlowPanel")
            
            # 2. 精准保存列宽与表头布局状态 (Hex 格式)
            header_state = self.table.horizontalHeader().saveState().toHex().data().decode("utf-8")
            
            # 读取现有 window_config.json 并更新
            scale = self._get_dpi_scale_factor()
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            data = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
                    
            if "DecisionFlowPanel" not in data:
                data["DecisionFlowPanel"] = {}
            data["DecisionFlowPanel"]["header_state"] = header_state
            
            # 精准保存持仓表格列宽表头状态
            if hasattr(self, "pos_table"):
                pos_header_state = self.pos_table.horizontalHeader().saveState().toHex().data().decode("utf-8")
                data["DecisionFlowPanel"]["pos_header_state"] = pos_header_state
            
            # 原子写入
            tmp_file = config_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_file, config_file)
            
            logger.info("DecisionFlowPanel position and header states saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save window state: {e}\n{traceback.format_exc()}")
        
        # 从父窗口引用中抹除，有利于 GC 回收
        if self.parent_app and hasattr(self.parent_app, "panel_manager"):
            self.parent_app.panel_manager._decision_flow_win = None
            
        event.accept()

    def _restore_header_state(self):
        """恢复用户手动调整的列宽与排序状态"""
        try:
            scale = self._get_dpi_scale_factor()
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                restored_any = False
                if "DecisionFlowPanel" in data:
                    panel_cfg = data["DecisionFlowPanel"]
                    if "header_state" in panel_cfg:
                        hex_state = panel_cfg["header_state"]
                        byte_state = QtCore.QByteArray.fromHex(hex_state.encode("utf-8"))
                        self.table.horizontalHeader().restoreState(byte_state)
                        restored_any = True
                    if "pos_header_state" in panel_cfg and hasattr(self, "pos_table"):
                        pos_hex_state = panel_cfg["pos_header_state"]
                        pos_byte_state = QtCore.QByteArray.fromHex(pos_hex_state.encode("utf-8"))
                        self.pos_table.horizontalHeader().restoreState(pos_byte_state)
                        restored_any = True
                        
                if restored_any:
                    logger.info("DecisionFlowPanel header states restored successfully.")
                    return True
        except Exception as e:
            logger.error(f"Failed to restore DecisionFlowPanel header states: {e}")
        return False

    def showEvent(self, event):
        """展现时自适应"""
        super().showEvent(event)
        self.table.scrollToBottom()

    def _on_pos_cell_double_clicked(self, row, column):
        """双击持仓表格行，提取持仓个股代码并向主进程派发跳转联动"""
        code_item = self.pos_table.item(row, 0)
        name_item = self.pos_table.item(row, 1)
        if code_item and code_item.text():
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else ""
            logger.info(f"Double clicked on KernelPosition: {code} ({name}), linking...")
            self.code_clicked.emit(code, name)

    def _refresh_positions_tab(self):
        """核心无摩擦刷新：每 500ms 直接从 `get_kernel_service()` 单例物理提取内存中最新持仓与浮盈状态"""
        try:
            from trading_kernel.kernel_service import get_kernel_service
            service = get_kernel_service()
            if not service:
                logger.warning("Kernel service not available yet.")
                return
                
            mode = service.mode
            executor = service.executor
            
            # 物理对账数据源切换自愈：如果是 LIVE_AUTO 则拉取实盘真柜台数据，否则高保真拉取模拟盘
            adapter = executor if (executor is not None and mode == "LIVE_AUTO") else service.paper_adapter
            if not adapter:
                logger.warning("Active execution adapter not found.")
                return
            
            positions = adapter.get_positions()
            account = adapter.get_account_snapshot()
        except Exception as ex:
            logger.error(f"Failed to fetch real-time kernel positions for rendering: {ex}")
            return

        self.pos_table.setRowCount(0)
        total_market_val = 0.0
        
        # 依次填充持仓行
        for code, pos in positions.items():
            row_idx = self.pos_table.rowCount()
            self.pos_table.insertRow(row_idx)
            
            entry_price = float(pos.get("entry_price", 0.0))
            volume = float(pos.get("volume", 0.0))
            curr_price = float(pos.get("current_price", 0.0))
            market_val = volume * curr_price
            total_market_val += market_val
            
            pnl = float(pos.get("pnl", 0.0))
            pnl_pct = float(pos.get("pnl_pct", 0.0))
            
            # 精密名称补齐：尝试从父窗口的实时数据集中查找，降级为默认
            stock_name = ""
            if self.parent_app and hasattr(self.parent_app, "current_df") and self.parent_app.current_df is not None:
                df = self.parent_app.current_df
                if code in df.index:
                    stock_name = str(df.loc[code].get("name", ""))
            if not stock_name:
                stock_name = "已持仓"
                
            # 盈亏柔和色彩管理 (亮盈绿 vs 猩红)
            pnl_color = "#00E676" if pnl >= 0 else "#FF1744"
            pnl_sign = "+" if pnl >= 0 else ""
            
            items = [
                (code, "#FFFFFF"),
                (stock_name, "#C2C2C6"),
                (f"{volume:.0f}", "#B0BEC5"),
                (f"{entry_price:.2f}", "#B0BEC5"),
                (f"{curr_price:.2f}", "#FFFFFF"),
                (f"¥ {market_val:,.2f}", "#00E5FF"),
                (f"{pnl_sign}¥ {pnl:,.2f}", pnl_color),
                (f"{pnl_sign}{pnl_pct:.2f}%", pnl_color)
            ]
            
            for col_idx, (text, color_hex) in enumerate(items):
                cell_item = QtWidgets.QTableWidgetItem(str(text))
                cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if color_hex:
                    cell_item.setForeground(QtGui.QColor(color_hex))
                if col_idx in {6, 7}:
                    cell_item.setFont(QtGui.QFont("Microsoft YaHei", 9, QtGui.QFont.Weight.Bold))
                self.pos_table.setItem(row_idx, col_idx, cell_item)

        # 刷新大卡片统计数据
        cash = float(account.get("cash", 0.0))
        equity = float(account.get("total_equity", 0.0))
        total_pnl = float(account.get("total_pnl", 0.0))
        total_pnl_pct = float(account.get("total_pnl_pct", 0.0))
        ratio = (total_market_val / equity * 100.0) if equity > 0 else 0.0
        
        self.cards["cash"].setText(f"¥ {cash:,.2f}")
        self.cards["equity"].setText(f"¥ {equity:,.2f}")
        self.cards["market_value"].setText(f"¥ {total_market_val:,.2f}")
        
        # 盈亏卡片动态变色与柔和发光渲染
        pnl_sign = "+" if total_pnl >= 0 else ""
        self.cards["total_pnl"].setText(f"{pnl_sign}¥ {total_pnl:,.2f} ({total_pnl_pct:.2f}%)")
        if total_pnl >= 0:
            self.cards["total_pnl"].setStyleSheet("font-size: 13px; font-weight: bold; color: #00E676;")
        else:
            self.cards["total_pnl"].setStyleSheet("font-size: 13px; font-weight: bold; color: #FF1744;")
            
        self.cards["ratio"].setText(f"{ratio:.1f}%")

    def resizeEvent(self, event):
        """拖动放大窗口时不要自动_adjust_column_widths，由主窗体布局进行自适应弹性拉伸"""
        super().resizeEvent(event)

    def _adjust_column_widths(self):
        """极致模式自适应：按照可视化左侧列的紧凑显示方式，强行重设并压实列宽参数"""
        if hasattr(self, "table") and self.table.columnCount() == 12:
            total_w = self.table.viewport().width()
            if total_w > 100:
                # 0.日期时间, 1.代码, 2.名称, 3.前态, 4.动作, 5.拟仓, 6.打分, 7.风控, 8.阻断, 9.止损, 10.Trace ID, 11.决策理由摘要
                static_widths = [110, 65, 75, 45, 52, 48, 45, 55, 70, 52, 55]
                scaled_total = int(sum(static_widths) * self.scale_factor)
                
                # 强行设置互动模式，确保完全压实宽度并不受历史配置死锁阻碍
                headers = self.table.horizontalHeader()
                for idx, w in enumerate(static_widths):
                    headers.setSectionResizeMode(idx, QtWidgets.QHeaderView.ResizeMode.Interactive)
                    self.table.setColumnWidth(idx, int(w * self.scale_factor))
                
                # 最后一列“决策理由摘要”自适应 Stretch
                reason_width = max(250, total_w - scaled_total)
                self.table.setColumnWidth(11, reason_width)
                
        if hasattr(self, "pos_table") and self.pos_table.columnCount() == 8:
            total_pos_w = self.pos_table.viewport().width()
            if total_pos_w > 100:
                # 0.代码, 1.名称, 2.数量, 3.买均, 4.现价, 5.市值, 6.盈亏, 7.盈亏比例
                static_pos_widths = [65, 75, 60, 60, 60, 85, 90]
                scaled_pos_total = int(sum(static_pos_widths) * self.scale_factor)
                
                pos_headers = self.pos_table.horizontalHeader()
                for idx, w in enumerate(static_pos_widths):
                    pos_headers.setSectionResizeMode(idx, QtWidgets.QHeaderView.ResizeMode.Interactive)
                    self.pos_table.setColumnWidth(idx, int(w * self.scale_factor))
                
                # 最后一列“盈亏比例”自适应 Stretch
                pct_width = max(80, total_pos_w - scaled_pos_total)
                self.pos_table.setColumnWidth(7, pct_width)

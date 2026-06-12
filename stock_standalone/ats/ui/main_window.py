# -*- coding: utf-8 -*-
"""
ATS Main Window Panel
Assembles the complete Autonomous Trading System UI dashboard.
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTabWidget, QLabel, QToolBar, QPushButton, QStatusBar, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QGridLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QColor, QBrush

from ats.ui.styles import DARK_THEME_QSS
from ats.ui.universe_widget import UniverseTreeWidget
from ats.ui.heatmap_widget import SectorHeatmapWidget
from ats.ui.chart_widgets import DistributionBarChart, EquityCurveChart
from ats.ui.swing_table import SwingStateTable
from ats.ui.trade_flow import TradeFlowTable, PositionPanel, BacktestReportPanel
from ats.ui.kernel_trace_panel import KernelTracePanel
from ats.universe_manager import UniverseManager
from ats.swing_tracker import SwingTracker

class StockDetailDialog(QDialog):
    def __init__(self, code, name, df_row=None, context_info=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📈 实时实盘个股详情 - {code} {name}")
        self.resize(550, 650)
        self.setMinimumSize(450, 550)
        
        # Auto-scan latest kernel trace
        self.kernel_info = {}
        try:
            from sys_utils import get_app_root
            import os
            import json
            base = get_app_root()
            trace_path = os.path.join(base, "logs", "trading_kernel_trace.jsonl")
            if os.path.exists(trace_path):
                with open(trace_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                signal_data = data.get("signal", {})
                                intent_data = data.get("intent", {})
                                trace_code = signal_data.get("code") or intent_data.get("code") or ""
                                if str(trace_code).strip() == str(code).strip():
                                    self.kernel_info = data
                            except Exception:
                                pass
        except Exception as e:
            print(f"Error scanning kernel trace in dialog: {e}")
        
        # Inherit parent stylesheet to match the high-end dark theme
        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #121214;
                    color: #e2e2e5;
                }
                QLabel {
                    color: #aad4ff;
                }
                QTableWidget {
                    background-color: #18181c;
                    alternate-background-color: #1f1f24;
                    gridline-color: #2e2e36;
                    border: 1px solid #2e2e36;
                    color: #e2e2e5;
                }
                QHeaderView::section {
                    background-color: #1a1a1f;
                    color: #aad4ff;
                    border: 1px solid #2e2e36;
                    font-weight: bold;
                }
                QPushButton {
                    background-color: #222228;
                    border: 1px solid #3e3e4a;
                    color: #e2e2e5;
                    padding: 6px 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #2c2c35;
                    border-color: #aad4ff;
                    color: #ffffff;
                }
            """)
            
        self._init_ui(code, name, df_row, context_info)
        
    def _init_ui(self, code, name, df_row, context_info):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # 1. Title and header info
        header_layout = QHBoxLayout()
        title_label = QLabel(f"📊 {code}  {name}")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        price_str = "--"
        pct_str = "--"
        color_hex = "#8e8e93"
        
        if df_row is not None:
            # Resolve price
            for p_col in ['close', 'trade', 'price']:
                if p_col in df_row and df_row[p_col] is not None and df_row[p_col] != '':
                    try:
                        price_str = f"{float(df_row[p_col]):.2f}"
                        break
                    except:
                        pass
            # Resolve percent
            if 'percent' in df_row and df_row['percent'] is not None and df_row['percent'] != '':
                try:
                    pct_val = float(df_row['percent'])
                    pct_str = f"{pct_val:+.2f}%"
                    if pct_val > 0:
                        color_hex = "#ff4444"
                    elif pct_val < 0:
                        color_hex = "#33cc5a"
                except:
                    pct_str = str(df_row['percent'])
                    if pct_str.startswith("+"):
                        color_hex = "#ff4444"
                    elif pct_str.startswith("-"):
                        color_hex = "#33cc5a"
                        
        price_pct_label = QLabel(f"{price_str}  ({pct_str})")
        price_pct_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {color_hex};")
        header_layout.addWidget(price_pct_label)
        layout.addLayout(header_layout)
        
        # 1.5 Context Info Block (If provided)
        if context_info:
            ctx_group = QGroupBox("📍 策略特征上下文 (Context Info)")
            ctx_group.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #2e2e36;
                    border-radius: 6px;
                    margin-top: 10px;
                    font-weight: bold;
                    color: #aad4ff;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
            """)
            ctx_layout = QGridLayout(ctx_group)
            ctx_layout.setContentsMargins(12, 18, 12, 12)
            ctx_layout.setSpacing(10)
            
            # Position
            lbl_pos_title = QLabel("触发位置:")
            lbl_pos_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
            lbl_pos_val = QLabel(context_info.get('position', '--'))
            lbl_pos_val.setStyleSheet("color: #ffffff; font-weight: bold;")
            lbl_pos_val.setWordWrap(True)
            
            # Reason
            lbl_reason_title = QLabel("推荐理由:")
            lbl_reason_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
            lbl_reason_val = QLabel(context_info.get('reason', '--'))
            lbl_reason_val.setStyleSheet("color: #ffaa44; font-weight: bold;")
            lbl_reason_val.setWordWrap(True)
            
            # Status
            lbl_status_title = QLabel("追涨/特征状态:")
            lbl_status_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
            lbl_status_val = QLabel(context_info.get('status', '--'))
            lbl_status_val.setStyleSheet("color: #00ff88; font-weight: bold;")
            lbl_status_val.setWordWrap(True)
            
            ctx_layout.addWidget(lbl_pos_title, 0, 0)
            ctx_layout.addWidget(lbl_pos_val, 0, 1)
            ctx_layout.addWidget(lbl_reason_title, 1, 0)
            ctx_layout.addWidget(lbl_reason_val, 1, 1)
            ctx_layout.addWidget(lbl_status_title, 2, 0)
            ctx_layout.addWidget(lbl_status_val, 2, 1)
            
            ctx_layout.setColumnStretch(1, 1)
            layout.addWidget(ctx_group)
            
        # 2. Source indicator
        hint_label = QLabel()
        if df_row is not None:
            hint_label.setText("🟢 已成功对接实盘行情快照核心特征:")
            hint_label.setStyleSheet("color: #00ff88; font-size: 9.5pt; font-weight: bold;")
        else:
            hint_label.setText("⚠️ 暂无当前个股实盘快照特征数据（等待行情推送中）:")
            hint_label.setStyleSheet("color: #ff9900; font-size: 9.5pt; font-weight: bold;")
        layout.addWidget(hint_label)
        
        # 3. Main feature table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["指标核心特征", "特征实盘数据值"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        features = []
        if df_row is not None:
            main_keys = {
                'percent': '今日涨幅 (%)',
                'close': '最新收盘价 (元)',
                'trade': '最新成交价 (元)',
                'open': '开盘价 (元)',
                'high': '最高价 (元)',
                'low': '最低价 (元)',
                'volume': '累计成交量 (手/股)',
                'amount': '累计成交额 (元)',
                'vwap': '分时均价线 (VWAP)',
                'ma20': '20日移动平均 (MA20)',
                'category': '所属行业/概念板块',
                'strategy': '匹配筛选策略'
            }
            
            for k, label in main_keys.items():
                if k in df_row and df_row[k] is not None and df_row[k] != '':
                    val = df_row[k]
                    if isinstance(val, float):
                        if k in ('percent', 'pct_chg'):
                            val_str = f"{val:+.2f}%"
                        elif k in ('volume', 'amount') and val > 10000:
                            val_str = f"{val:,.2f}"
                        else:
                            val_str = f"{val:.2f}"
                    else:
                        val_str = str(val)
                    features.append((label, val_str))
                    
            for k, val in df_row.items():
                if k not in main_keys and k not in ('code', 'name') and val is not None and val != '':
                    label = k.replace('_', ' ').title()
                    if isinstance(val, float):
                        val_str = f"{val:.4f}"
                    else:
                        val_str = str(val)
                    features.append((label, val_str))
        else:
            features.append(("证券代码", code))
            features.append(("证券名称", name))
            
        # Add trading kernel trace features if available
        if hasattr(self, 'kernel_info') and self.kernel_info:
            res = self.kernel_info.get("kernel_result", {})
            sig = self.kernel_info.get("signal", {})
            intent = self.kernel_info.get("intent", {})
            
            # Action
            action = res.get("kernel_action") or intent.get("action") or "HOLD"
            action_cn = "买入" if action == "BUY" else ("卖出" if action == "SELL" else "观察")
            features.append(("🤖 内核决策动作", action_cn))
            
            # Confidence
            conf = res.get("kernel_confidence") or intent.get("confidence") or 0.0
            conf_str = f"{conf:.2%}" if isinstance(conf, float) else str(conf)
            features.append(("🤖 内核决策置信度", conf_str))
            
            # State
            state = res.get("kernel_state") or "NORMAL"
            features.append(("🤖 内核运行状态", str(state)))
            
            # Reject code
            reject = res.get("kernel_reject_code")
            if reject:
                features.append(("🚫 风控阻断代码", str(reject)))
                
            # Signal Type
            sig_type = sig.get("signal_type") or ""
            if sig_type:
                features.append(("⚡ 触发信号类型", str(sig_type)))
                
            # Reason
            reason = sig.get("features", {}).get("raw_reason") or intent.get("reason", {}).get("raw_reason") or ""
            if not reason and intent.get("reason"):
                reason = str(intent.get("reason"))
            if reason:
                features.append(("💡 内核决策依据", str(reason)))
                
            # Timestamp
            ts = self.kernel_info.get("journal_ts") or self.kernel_info.get("timestamp") or ""
            if ts:
                features.append(("📅 内核评估时间", str(ts).replace("T", " ")))
                
        if len(features) <= 2:
            features = [
                ("证券代码", code),
                ("证券名称", name),
                ("日内价格", "加载中..."),
                ("实盘状态", "等待主进程推送行情"),
                ("说明", "双击可实现实盘特征一屏清，当前暂未收到主进程行情推送")
            ]
            
        self.table.setRowCount(len(features))
        for row, (lbl, val) in enumerate(features):
            item_lbl = QTableWidgetItem(lbl)
            item_lbl.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, item_lbl)
            
            item_val = QTableWidgetItem(val)
            item_val.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if "涨幅" in lbl or "Percent" in lbl:
                if val.startswith("+"):
                    item_val.setForeground(QColor("#ff4444"))
                elif val.startswith("-"):
                    item_val.setForeground(QColor("#33cc5a"))
            self.table.setItem(row, 1, item_val)
            
        layout.addWidget(self.table)
        
        # 4. Button close
        btn_close = QPushButton("关闭窗口")
        btn_close.clicked.connect(self.accept)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

class ATSMainWindow(QMainWindow):
    realtime_data_signal = pyqtSignal(object)
    realtime_signal_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛡️ ATS v2 智能自治股票交易终端 (Autonomous Trading Terminal)")
        self.resize(1440, 900)
        self.current_font_size = self.load_font_size()
        self.apply_qss_with_font_size(self.current_font_size)
        self.current_df = None  # Live streaming DataFrame snapshot data source
        self._listener_started = False
        self.name_cache = {}  # Global name cache to prevent "未知" names
        self.price_pct_cache = {}  # Cache for price and percent when current_df is empty/missing
        
        self.universe_manager = UniverseManager()
        self.swing_tracker = SwingTracker()
        self.stock_history_cache = {}
        
        # Connect thread-safe PyQt signals
        self.realtime_data_signal.connect(self._handle_realtime_data)
        self.realtime_signal_signal.connect(self._handle_realtime_signal)
        
        # Subscribe to global favorite changes
        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().subscribe(self._on_favorites_changed)
        except Exception as e:
            print(f"[ATSMainWindow] Error subscribing to favorites: {e}")
            
        self._init_toolbar()
        self._init_ui()
        self._restore_layout_state()
        self._init_statusbar()
        
        # Prepopulate name cache from database history on startup
        self._prepopulate_name_cache()
        
        # Load SQLite database data (P1 Integration)
        self.load_db_data(force=True)
        
        # Setup simple timer for mock ticker updating (simulate live environment in P0)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_heartbeat)
        self.update_timer.start(3000)

    def _prepopulate_name_cache(self):
        self.name_cache = {}
        try:
            from ats.ipc_bridge import IPCBridge
            bridge = IPCBridge()
            queries = [
                "SELECT DISTINCT code, name FROM signal_history WHERE name IS NOT NULL AND name != ''",
                "SELECT DISTINCT code, name FROM trade_records WHERE name IS NOT NULL AND name != ''"
            ]
            for query in queries:
                try:
                    with bridge.db_manager.execute_query(query) as cursor:
                        for row in cursor.fetchall():
                            c = str(row[0]).strip()
                            n = str(row[1]).strip()
                            if c and n:
                                self.name_cache[c] = n
                except Exception as e:
                    print(f"[ATSMainWindow] Prepopulate cache query failed: {e}")
        except Exception as e:
            print(f"[ATSMainWindow] Prepopulate cache failed: {e}")


    def _init_toolbar(self):
        toolbar = QToolBar("Main Controls")
        self.addToolBar(toolbar)
        toolbar.setMovable(False)
        
        self.btn_toggle_rotation = QPushButton("▶ 启动 24x7 自动旋转")
        self.btn_toggle_rotation.setStyleSheet("background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88;")
        self.btn_toggle_rotation.clicked.connect(self.toggle_rotation)
        toolbar.addWidget(self.btn_toggle_rotation)
        
        toolbar.addSeparator()
        
        self.lbl_ipc_status = QLabel("  IPC 通道: 🔌 已连接  |  ")
        self.lbl_ipc_status.setStyleSheet("color: #00ff88; font-weight: bold;")
        toolbar.addWidget(self.lbl_ipc_status)
        
        self.lbl_db_status = QLabel("数据库: 🗄️ 已加载  |  ")
        self.lbl_db_status.setStyleSheet("color: #aad4ff;")
        toolbar.addWidget(self.lbl_db_status)

        self.lbl_rotator_status = QLabel("旋转引擎: ⏸️ 已暂停")
        self.lbl_rotator_status.setStyleSheet("color: #ff9900;")
        toolbar.addWidget(self.lbl_rotator_status)
        
        toolbar.addSeparator()
        
        btn_font_dec = QPushButton("A-")
        btn_font_dec.setToolTip("减小字号 (Font Size Down)")
        btn_font_dec.setStyleSheet("min-width: 24px; max-width: 28px; background-color: #2e2e36; color: #e2e2e5; font-weight: bold; border: 1px solid #44444f;")
        btn_font_dec.clicked.connect(self.decrease_font_size)
        toolbar.addWidget(btn_font_dec)
        
        self.lbl_font_size = QLabel(f" {self.current_font_size} pt ")
        self.lbl_font_size.setStyleSheet("color: #aad4ff; font-weight: bold;")
        toolbar.addWidget(self.lbl_font_size)
        
        btn_font_inc = QPushButton("A+")
        btn_font_inc.setToolTip("增大字号 (Font Size Up)")
        btn_font_inc.setStyleSheet("min-width: 24px; max-width: 28px; background-color: #2e2e36; color: #e2e2e5; font-weight: bold; border: 1px solid #44444f;")
        btn_font_inc.clicked.connect(self.increase_font_size)
        toolbar.addWidget(btn_font_inc)

    def _init_ui(self):
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.main_splitter)

        # 1. Left panel: Universe Tree (Width: 350)
        self.universe_widget = UniverseTreeWidget()
        self.universe_widget.setMinimumWidth(300)
        self.main_splitter.addWidget(self.universe_widget)

        # 2. Center panel: Swing Table & Trading Tabs (Width: 700)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.swing_table = SwingStateTable()
        self.center_splitter.addWidget(self.swing_table)
        
        # Bottom Tabs in center panel
        self.center_tabs = QTabWidget()
        
        self.position_panel = PositionPanel()
        self.center_tabs.addTab(self.position_panel, "💰 当前持仓 (Holdings)")
        
        self.trade_flow_table = TradeFlowTable()
        self.center_tabs.addTab(self.trade_flow_table, "📋 交易流水 (Orders)")
        
        self.backtest_panel = BacktestReportPanel()
        self.center_tabs.addTab(self.backtest_panel, "📊 离线回测报告 (Backtest)")
        
        self.kernel_trace_panel = KernelTracePanel()
        self.center_tabs.addTab(self.kernel_trace_panel, "🤖 内核轨迹 (Kernel Trace)")
        
        self.center_splitter.addWidget(self.center_tabs)
        self.center_splitter.setSizes([450, 450])
        
        center_layout.addWidget(self.center_splitter)
        self.main_splitter.addWidget(center_widget)

        # 3. Right panel: Heatmap & Distribution charts (Width: 390)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.heatmap_widget = SectorHeatmapWidget()
        self.right_splitter.addWidget(self.heatmap_widget)
        
        # Right charts tab
        self.right_tabs = QTabWidget()
        
        self.dist_chart = DistributionBarChart()
        self.right_tabs.addTab(self.dist_chart, "📊 市场分布 (Dist)")
        
        self.equity_chart = EquityCurveChart()
        self.right_tabs.addTab(self.equity_chart, "📈 资金曲线 (Equity)")
        
        self.right_splitter.addWidget(self.right_tabs)
        self.right_splitter.setSizes([450, 450])
        
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_widget)

        # Set stretch factors and initial sizes
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setStretchFactor(2, 2)
        self.main_splitter.setSizes([350, 700, 390])

        # Connect internal signal linkages
        # 1. 单击事件 -> 联动外部同花顺/通达信及可视化器 (link_stock)
        self.universe_widget.stock_clicked.connect(self.link_stock)
        self.swing_table.stock_clicked.connect(self.link_stock)
        self.position_panel.stock_clicked.connect(self.link_stock)
        self.trade_flow_table.stock_clicked.connect(self.link_stock)
        self.kernel_trace_panel.stock_clicked.connect(self.link_stock)
        
        # 2. 双击事件 -> 弹窗详情展示 context_info (on_stock_clicked)
        self.universe_widget.stock_selected.connect(self.on_stock_clicked)
        self.swing_table.stock_double_clicked.connect(self.on_stock_clicked)
        self.position_panel.stock_double_clicked.connect(self.on_stock_clicked)
        self.trade_flow_table.stock_double_clicked.connect(self.on_stock_clicked)
        self.kernel_trace_panel.stock_double_clicked.connect(self.on_stock_clicked)
        
        self.heatmap_widget.sector_selected.connect(self.on_sector_clicked)
        self.swing_table.btn_refresh.clicked.connect(lambda: self.load_db_data(force=True))
        self.backtest_panel.btn_run_backtest.clicked.connect(self.on_run_backtest_clicked)

    def _init_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("初始化独立自治交易系统，就绪。")

    def toggle_rotation(self):
        if self.btn_toggle_rotation.text().startswith("▶"):
            self.btn_toggle_rotation.setText("■ 停止 24x7 自动旋转")
            self.btn_toggle_rotation.setStyleSheet("background-color: #3d0000; color: #ff6060; font-weight: bold; border: 1px solid #ff4444;")
            self.lbl_rotator_status.setText("旋转引擎: 🟢 运行中")
            self.lbl_rotator_status.setStyleSheet("color: #00ff88;")
            self.status_bar.showMessage("24x7 自动过滤、信号评估、及大级别历史回测轮转已启动。")
        else:
            self.btn_toggle_rotation.setText("▶ 启动 24x7 自动旋转")
            self.btn_toggle_rotation.setStyleSheet("background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88;")
            self.lbl_rotator_status.setText("旋转引擎: ⏸️ 已暂停")
            self.lbl_rotator_status.setStyleSheet("color: #ff9900;")
            self.status_bar.showMessage("自动轮转引擎已暂停。")

    def link_stock(self, code, name):
        """
        [LINKAGE] 单击个股触发联动：
        1. 向 trade_visualizer_qt6 可视化服务器 (TCP 端口 26668) 发送 CODE|{code} 切换行情。
        2. 调用 get_link_manager().push() 执行外部通达信/同花顺终端物理联动。
        """
        code_clean = str(code).strip()
        self.status_bar.showMessage(f"🔗 [联动] 推送股票 {code_clean} {name} (已同步可视化及外部交易终端)")
        
        # 1. 异步向 26668 发送切换个股 socket 指令
        import socket
        import threading
        
        def send_switch():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1) # 极低超时，不阻塞 UI
                    s.connect(('127.0.0.1', 26668))
                    s.sendall(f"CODE|{code_clean}".encode("utf-8"))
            except Exception:
                pass # 可视化器可能未启动，静默失败即可
                
        threading.Thread(target=send_switch, daemon=True).start()

        # 2. 向独立联动进程投递物理联动任务 (TDX/THS 物理联动机能)
        try:
            from linkage_service import get_link_manager
            get_link_manager().push(code_clean, auto=False)
        except Exception as e:
            print(f"[Linkage] External linkage failed: {e}")

    def on_stock_clicked(self, code, name, context_info=None):
        self.status_bar.showMessage(f"双击详情: {code} {name}")
        
        # Fetch real-time row data from the live streaming DataFrame (df_row)
        df_row = None
        code_clean = str(code).strip()
        if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            # Match code either in index or 'code' column
            if code_clean in self.current_df.index:
                df_row = self.current_df.loc[code_clean].to_dict()
            elif 'code' in self.current_df.columns:
                matched = self.current_df[self.current_df['code'] == code_clean]
                if not matched.empty:
                    df_row = matched.iloc[0].to_dict()
                    
        # If not found in current streaming df (e.g. outside trading hours or on non-trading days),
        # auto-retrieve latest data from Sina API/local cache.
        if df_row is None:
            try:
                from JSONData import sina_data
                tick_df = sina_data.Sina().get_real_time_tick(code_clean, enrich_data=True)
                if tick_df is not None and not tick_df.empty:
                    df_row = tick_df.iloc[0].to_dict()
                    
                    # Map keys from Sina tick data to what detail table expects
                    if 'trade' not in df_row and 'close' in df_row:
                        df_row['trade'] = df_row['close']
                    if 'close' not in df_row and 'trade' in df_row:
                        df_row['close'] = df_row['trade']
                    if 'percent' not in df_row and 'close' in df_row and 'llastp' in df_row:
                        try:
                            close_val = float(df_row['close'])
                            last_val = float(df_row['llastp'])
                            if last_val > 0:
                                df_row['percent'] = (close_val - last_val) / last_val * 100
                        except:
                            pass
                    if 'vwap' not in df_row and 'avg_price' in df_row:
                        df_row['vwap'] = df_row['avg_price']
            except Exception as e:
                print(f"[ATSMainWindow] Error auto-retrieving Sina tick for {code_clean}: {e}")
                    
        # Launch detail dialog
        dialog = StockDetailDialog(code, name, df_row, context_info, parent=self)
        dialog.exec()

    def on_sector_clicked(self, name):
        self.status_bar.showMessage(f"选中板块: {name} | 正在展示成分股明细...")
        from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
        dialog = ATSSectorDetailDialog(name, self.link_stock, self.on_stock_clicked, parent=self)
        dialog.exec()

    def on_heartbeat(self):
        # 1. Periodically load and update DB data
        self.load_db_data()
        
        # 2. Periodically load trace logs
        if hasattr(self, 'kernel_trace_panel'):
            self.kernel_trace_panel.load_trace_logs()
            
        # 3. Periodically load sector heatmap
        if hasattr(self, 'heatmap_widget'):
            self.heatmap_widget.load_live_sectors()

    def _update_name_cache_from_df(self, df):
        if df is not None and not df.empty and 'name' in df.columns:
            try:
                # Fast vectorized extraction of code -> name
                temp_dict = df['name'].dropna().to_dict()
                cleaned_dict = {str(k).strip(): str(v).strip() for k, v in temp_dict.items() if str(v).strip()}
                self.name_cache.update(cleaned_dict)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating name cache from df: {e}")

    def get_stock_name(self, code):
        if not code:
            return "未知"
        code_str = str(code).strip()
        # 1. Try name_cache
        name = self.name_cache.get(code_str)
        if name and name != "未知" and not name.startswith("个股_"):
            return name
            
        # 2. Use system-wide authoritative and robust resolver with networking and file self-healing fallbacks
        try:
            from sys_utils import resolve_stock_name
            res_name = resolve_stock_name(code_str)
            if res_name and not res_name.startswith("个股_"):
                self.name_cache[code_str] = res_name
                return res_name
            name = res_name
        except Exception:
            pass
            
        # 3. Try current_df
        if self.current_df is not None and code_str in self.current_df.index:
            name_df = str(self.current_df.loc[code_str].get('name', '')).strip()
            if name_df:
                self.name_cache[code_str] = name_df
                return name_df
                
        return name if name else "未知"

    def load_db_data(self, force=False):
        try:
            # First, check if logs/paper_account_state.json exists and read it
            # This contains live paper account status (positions, cash, orders)
            import os
            import json
            from sys_utils import get_app_root
            
            base = get_app_root()
            state_path = os.path.join(base, "logs", "paper_account_state.json")
            db_path = os.path.join(base, "trading_signals.db")
            if not os.path.exists(db_path):
                db_path = "./trading_signals.db"
                
            db_mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else 0
            paper_mtime = os.path.getmtime(state_path) if os.path.exists(state_path) else 0
            
            # Check modification time to avoid redundant heavy IO/queries
            if not force and getattr(self, '_last_db_mtime', None) == db_mtime and getattr(self, '_last_paper_mtime', None) == paper_mtime:
                return
                
            self._last_db_mtime = db_mtime
            self._last_paper_mtime = paper_mtime
            
            state_data = None
            if os.path.exists(state_path):
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                except Exception as e:
                    print(f"[ATSMainWindow] Error loading paper_account_state.json: {e}")

            from ats.ipc_bridge import IPCBridge
            if not hasattr(self, 'bridge') or self.bridge is None:
                self.bridge = IPCBridge()
            
            # Update name cache from current_df if available using fast vectorized call
            self._update_name_cache_from_df(self.current_df)
            
            # --- 1. Load trade flows (Orders) ---
            flow_data = []
            if state_data and "orders" in state_data:
                for o in state_data["orders"]:
                    action = "买入" if o.get('action') == 'BUY' else "卖出"
                    qty = o.get('volume') or 0
                    price = o.get('price') or 0.0
                    amount = price * qty
                    ts = o.get('timestamp') or ''
                    if 'T' in ts:
                        ts = ts.replace('T', ' ')
                    flow_data.append((
                        str(ts),
                        str(o.get('code') or ''),
                        "", # Filled from cache later
                        str(action),
                        f"{price:.2f}" if price else "0.00",
                        f"{int(qty):,}" if qty else "0",
                        f"{amount:,.2f}" if amount else "0.00",
                        "核对无误"
                    ))
                flow_data.sort(key=lambda x: x[0], reverse=True)
                
            flow_df = self.bridge.get_all_trade_flows()
            if not flow_df.empty:
                db_flow_data = []
                for _, row in flow_df.iterrows():
                    action = row.get('action') or ('买入' if row.get('status') == 'OPEN' else '卖出')
                    date = row.get('buy_date') if action == '买入' else (row.get('sell_date') or row.get('buy_date'))
                    price = row.get('buy_price') if action == '买入' else (row.get('sell_price') or row.get('buy_price'))
                    qty = row.get('buy_amount') or 0
                    amount = price * qty if price and qty else 0.0
                    db_flow_data.append((
                        str(date or ''),
                        str(row.get('code') or ''),
                        str(row.get('name') or ''),
                        str(action or ''),
                        f"{price:.2f}" if price else "0.00",
                        f"{int(qty):,}" if qty else "0",
                        f"{amount:,.2f}" if amount else "0.00",
                        str(row.get('buy_reason') or '自动触发')
                    ))
                # Update global name cache with any names from database flow data
                for x in db_flow_data:
                    c = x[1]
                    n = x[2]
                    if c and n and n != "未知":
                        self.name_cache[c] = n
                        
                final_flow = []
                seen_orders = set()
                # Process paper account orders
                for item in flow_data:
                    code = item[1]
                    name = self.get_stock_name(code)
                    key = (item[0], code, item[3])
                    if key not in seen_orders:
                        final_flow.append((item[0], code, name, item[3], item[4], item[5], item[6], item[7]))
                        seen_orders.add(key)
                # Process DB flows
                for item in db_flow_data:
                    key = (item[0], item[1], item[3])
                    if key not in seen_orders:
                        final_flow.append(item)
                        seen_orders.add(key)
                
                final_flow.sort(key=lambda x: x[0], reverse=True)
                if final_flow:
                    self.trade_flow_table.update_flow_list(final_flow)
            else:
                if flow_data:
                    # Resolve names from cache
                    resolved_flow_data = []
                    for item in flow_data:
                        code = item[1]
                        name = self.get_stock_name(code)
                        resolved_flow_data.append((item[0], code, name, item[3], item[4], item[5], item[6], item[7]))
                    self.trade_flow_table.update_flow_list(resolved_flow_data)
 
            # --- 2. Load open positions ---
            pos_data = []
            cash = 1000000.0
            total_assets = 1000000.0
            
            if state_data and "positions" in state_data:
                cash = state_data.get("cash", 1000000.0)
                positions = state_data.get("positions", {})
                total_market_value = 0.0
                
                for code, p in positions.items():
                    name = self.get_stock_name(code)
                    if name == "未知" and p.get("name"):
                        name = p.get("name")
                    qty = p.get("volume") or 0.0
                    cost = p.get("entry_price") or 0.0
                    price = p.get("current_price") or cost
                    
                    # Update price to current_df price if available
                    if hasattr(self, 'current_df') and self.current_df is not None and code in self.current_df.index:
                        try:
                            price_val = float(self.current_df.loc[code].get('close', self.current_df.loc[code].get('trade', price)))
                            if price_val > 0:
                                price = price_val
                        except:
                            pass
                            
                    market_val = qty * price
                    total_market_value += market_val
                    pnl = (price - cost) * qty
                    pnl_pct_val = ((price - cost) / cost * 100) if cost else 0.0
                    pnl_pct = f"{pnl_pct_val:+.2f}%"
                    
                    pos_data.append({
                        'code': code,
                        'name': name,
                        'qty': qty,
                        'cost': cost,
                        'price': price,
                        'market_val': market_val,
                        'pnl_pct': pnl_pct,
                        'pnl_val': pnl
                    })
                
                total_assets = cash + total_market_value
                
                formatted_pos = []
                for p in pos_data:
                    alloc = f"{(p['market_val'] / total_assets) * 100:.1f}%" if total_assets else "0.0%"
                    formatted_pos.append((
                        str(p['code']),
                        str(p['name']),
                        f"{int(p['qty']):,}" if p['qty'] else "0",
                        f"{p['cost']:.2f}" if p['cost'] else "0.00",
                        f"{p['price']:.2f}" if p['price'] else "0.00",
                        f"{p['market_val']:,.2f}" if p['market_val'] else "0.00",
                        p['pnl_pct'],
                        alloc
                    ))
                self.position_panel.update_positions(formatted_pos, cash=cash, total_assets=total_assets)
            else:
                pos_df = self.bridge.get_open_positions()
                if not pos_df.empty:
                    db_pos_data = []
                    total_market_value = 0.0
                    for _, row in pos_df.iterrows():
                        code = row.get('code')
                        name = row.get('name') or self.get_stock_name(code)
                        qty = row.get('buy_amount') or 0
                        cost = row.get('buy_price') or 0.0
                        price = cost  # Fallback for last price
                        market_val = qty * price
                        total_market_value += market_val
                        pnl_pct = "+0.00%"
                        alloc = f"{(market_val / 1000000.0) * 100:.1f}%"
                        db_pos_data.append((
                            str(code or ''),
                            str(name or ''),
                            f"{int(qty):,}" if qty else "0",
                            f"{cost:.2f}" if cost else "0.00",
                            f"{price:.2f}" if price else "0.00",
                            f"{market_val:,.2f}" if market_val else "0.00",
                            pnl_pct,
                            alloc
                        ))
                    self.position_panel.update_positions(db_pos_data, cash=cash, total_assets=cash + total_market_value)
 
            # --- 3. Load historical signals and populate universe manager ---
            self.universe_manager.radar_pool.clear()
            self.universe_manager.watch_pool.clear()
            self.universe_manager.trade_pool.clear()
            
            signals_df = self.bridge.get_historical_signals(limit=50)
            if not signals_df.empty:
                for _, row in signals_df.iterrows():
                    code = str(row.get('code') or '').strip()
                    if not code:
                        continue
                    name = row.get('name') or self.get_stock_name(code)
                    if name == "未知":
                        name = ""
                    price = float(row.get('price') or 0.0)
                    action = row.get('action')
                    reason = row.get('reason') or '指标共振'
                    strategy = row.get('resample') or 'd'
                    
                    if action == 'BUY':
                        self.universe_manager.watch_pool[code] = {
                            "name": name,
                            "price": price,
                            "pct": 0.0,
                            "strategy": f"周期:{strategy}",
                            "reason": reason
                        }
                    else:
                        self.universe_manager.radar_pool[code] = {
                            "name": name,
                            "price": price,
                            "pct": 0.0,
                            "strategy": f"周期:{strategy}",
                            "reason": reason
                        }
            
            # Add open positions to trade pool
            pos_df = self.bridge.get_open_positions()
            if not pos_df.empty:
                for _, row in pos_df.iterrows():
                    p_code = str(row.get('code') or '').strip()
                    if not p_code:
                        continue
                    name = row.get('name') or self.get_stock_name(p_code)
                    price = float(row.get('buy_price') or 0.0)
                    self.universe_manager.trade_pool[p_code] = {
                        "name": name,
                        "price": price,
                        "pct": 0.0,
                        "strategy": "当前持仓",
                        "reason": "大级别多头持股"
                    }
            
            # Refresh tree widget UI
            radar_list, watch_list, trade_list = self.universe_manager.get_pools()
            self.universe_widget.update_pools(radar_list, watch_list, trade_list)
            
            # Pre-fetch history for these initial stocks asynchronously to populate swing states
            all_init_codes = list(self.universe_manager.radar_pool.keys()) + list(self.universe_manager.watch_pool.keys()) + list(self.universe_manager.trade_pool.keys())
            if all_init_codes:
                self._async_load_stock_history(all_init_codes)
 
            # --- 4. Load equity curves ---
            dates, strat_equity, bench_equity = self.bridge.get_equity_curve_data()
            x = list(range(len(dates)))
            self.equity_chart.update_curve(x, strat_equity, bench_equity)
 
            # --- 5. Load performance metrics ---
            from ats.backtest_engine import BacktestEngine
            self.backtest_engine = BacktestEngine(self.bridge)
            metrics = self.backtest_engine.calculate_performance_metrics()
            self.backtest_panel.update_stats(metrics)
 
            # --- 6. Start real-time IPC socket listener (P6) ---
            if not getattr(self, '_listener_started', False):
                self.bridge.start_realtime_listener(
                    port=26670,
                    data_callback=lambda data: self.realtime_data_signal.emit(data),
                    signal_callback=lambda sig: self.realtime_signal_signal.emit(sig)
                )
                self._listener_started = True
 
        except Exception as e:
            print(f"[ATSMainWindow] Error loading SQLite data: {e}")

    def on_run_backtest_clicked(self):
        self.status_bar.showMessage("正在读取历史信号与 K 线分时数据库进行多周期回测...")
        self.backtest_panel.lbl_status.setText("状态: 正在测算中...")
        
        try:
            from ats.backtest_engine import BacktestEngine
            engine = BacktestEngine(self.bridge)
            metrics = engine.calculate_performance_metrics()
            self.backtest_panel.update_stats(metrics)
            self.backtest_panel.lbl_status.setText("状态: 回测已完成 (数据已刷新)")
            self.status_bar.showMessage("历史回测计算完成，已更新全部绩效指标。")
        except Exception as e:
            self.backtest_panel.lbl_status.setText("状态: 计算失败")
            self.status_bar.showMessage(f"❌ 回测计算失败: {e}")

    def _handle_realtime_data(self, data_pkg):
        import pandas as pd
        
        # 1. 识别协议格式与提取 DataFrame
        msg_type = 'UPDATE_DF_ALL'
        df_payload = None
        
        if isinstance(data_pkg, dict):
            msg_type = data_pkg.get('type', 'UPDATE_DF_ALL')
            df_payload = data_pkg.get('data')
            if df_payload is None:
                # 兼容历史数据结构
                df_payload = data_pkg.get('full_snapshot')
        elif isinstance(data_pkg, pd.DataFrame):
            df_payload = data_pkg
        elif isinstance(data_pkg, tuple) and len(data_pkg) > 0:
            df_payload = data_pkg[0]
            
        if df_payload is None or not isinstance(df_payload, pd.DataFrame) or df_payload.empty:
            return

        # 2. 将提取出的 DataFrame 强制转换为以 code 字符串作为 index
        df_payload = df_payload.copy()
        if 'code' in df_payload.columns:
            df_payload['code'] = df_payload['code'].astype(str).str.strip()
            df_payload.set_index('code', inplace=True)
        elif df_payload.index.name != 'code':
            # 如果索引不是 code，尝试将其类型转换为 str
            df_payload.index = df_payload.index.astype(str).str.strip()
            df_payload.index.name = 'code'

        # 3. 处理全量/增量更新
        if msg_type == 'UPDATE_DF_DIFF' and hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            try:
                df_diff = df_payload
                # 取两边股票代码的交集
                common_idx = self.current_df.index.intersection(df_diff.index)
                if len(common_idx) > 0:
                    for col in df_diff.columns:
                        if col in self.current_df.columns:
                            try:
                                col_data = df_diff.loc[common_idx, col]
                                valid_mask = col_data.notna()
                                valid_indices = valid_mask[valid_mask].index
                                if len(valid_indices) > 0:
                                    self.current_df.loc[valid_indices, col] = df_diff.loc[valid_indices, col]
                            except Exception:
                                pass
                # 取 diff 中新出现的股票追加进来
                new_idx = df_diff.index.difference(self.current_df.index)
                if len(new_idx) > 0:
                    self.current_df = pd.concat([self.current_df, df_diff.loc[new_idx]])
            except Exception as e:
                print(f"[ATS_Realtime] Apply diff error: {e}")
        else:
            # 全量更新或冷启动
            self.current_df = df_payload

        # Fast vectorized name cache update
        self._update_name_cache_from_df(self.current_df)

        # 4. 更新 UI 显示与计算
        if self.current_df is not None and not self.current_df.empty:
            self.lbl_ipc_status.setText("  IPC 通道: 🔌 实时接入中  |  ")
            self.lbl_ipc_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            
            # 绘制 A 股涨跌幅度直方图
            if 'percent' in self.current_df.columns:
                pcts = self.current_df['percent'].dropna()
                bins = [-999, -8, -6, -4, -2, 0, 2, 4, 6, 8, 999]
                counts = pd.cut(pcts, bins=bins).value_counts().sort_index().tolist()
                if len(counts) == 10:
                    self.dist_chart.update_data(counts)
            
            self.refresh_realtime_ui()
            self.status_bar.showMessage(f"已同步接收到主进程最新实时行情快照 (个股数: {len(self.current_df)})")

    def _async_load_stock_prices(self, codes):
        if not codes:
            return
        
        import threading
        def worker():
            try:
                from JSONData import sina_data
                s = sina_data.Sina()
                
                valid_codes = [c for c in codes if c and len(c) == 6]
                if not valid_codes:
                    return
                    
                # Direct online fetch using Sina's list data API to get real-time price and llastp
                tick_df = s.get_stock_list_data(valid_codes)
                        
                if tick_df is not None and not tick_df.empty:
                    for idx, row in tick_df.iterrows():
                        code_str = str(idx).strip().zfill(6)
                        price = float(row.get('close', 0.0))  # Current price is stored under 'close' after mapping
                        llastp = float(row.get('llastp', 0.0))  # Yesterday's close is stored under 'llastp'
                        
                        if llastp > 0:
                            pct = (price - llastp) / llastp * 100.0
                        else:
                            pct = 0.0
                            
                        self.price_pct_cache[code_str] = (price, pct)
                        
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, self.refresh_realtime_ui)
            except Exception as e:
                print(f"[ATSMainWindow] Error loading prices in background: {e}")
                
        threading.Thread(target=worker, daemon=True).start()

    def _async_load_stock_history(self, codes):
        if not codes:
            return
        
        # Mark as loading with empty lists
        for code in codes:
            if code not in self.stock_history_cache:
                self.stock_history_cache[code] = []
                
        import threading
        def worker():
            try:
                import pandas as pd
                import os
                path = 'g:\\sina_MultiIndex_data.h5'
                if not os.path.exists(path):
                    return
                with pd.HDFStore(path, mode='r') as store:
                    code_query = ", ".join([f"'{c}'" for c in codes])
                    df = store.select('/all_30', where=f"code in [{code_query}]")
                
                if df.empty:
                    return
                
                dates = pd.to_datetime(df.index.get_level_values('ticktime')).date
                grouped = df.groupby([df.index.get_level_values('code'), dates])['close'].last()
                
                for (code, d), val in grouped.items():
                    d_str = d.strftime("%Y-%m-%d")
                    hist = self.stock_history_cache.get(code, [])
                    if not any(item[0] == d_str for item in hist):
                        hist.append((d_str, float(val)))
                    self.stock_history_cache[code] = hist
                    
                for code in codes:
                    if code in self.stock_history_cache:
                        self.stock_history_cache[code].sort(key=lambda x: x[0])
                
                # Trigger thread-safe UI update
                QTimer.singleShot(0, self.refresh_realtime_ui)
            except Exception as e:
                print(f"[ATSMainWindow] Error loading history in background: {e}")
                
        threading.Thread(target=worker, daemon=True).start()

    def refresh_realtime_ui(self):
        has_df = self.current_df is not None and not self.current_df.empty
        
        # 1. Update prices/percents in universe_manager pools
        all_codes = list(self.universe_manager.radar_pool.keys()) + list(self.universe_manager.watch_pool.keys()) + list(self.universe_manager.trade_pool.keys())
        missing_realtime_codes = []
        
        for pool in [self.universe_manager.radar_pool, self.universe_manager.watch_pool, self.universe_manager.trade_pool]:
            for code in list(pool.keys()):
                if has_df and code in self.current_df.index:
                    row = self.current_df.loc[code]
                    pool[code]['price'] = float(row.get('close', row.get('price', 0.0)))
                    pool[code]['pct'] = float(row.get('percent', 0.0))
                elif code in self.price_pct_cache:
                    price, pct = self.price_pct_cache[code]
                    pool[code]['price'] = price
                    pool[code]['pct'] = pct
                else:
                    if code in self.stock_history_cache and self.stock_history_cache[code]:
                        pool[code]['price'] = float(self.stock_history_cache[code][-1][1])
                        pool[code]['pct'] = 0.0
                    else:
                        pool[code]['price'] = 0.0
                        pool[code]['pct'] = 0.0
                    missing_realtime_codes.append(code)

        if missing_realtime_codes:
            import time
            now = time.time()
            if not hasattr(self, "_last_price_fetch_time") or now - self._last_price_fetch_time > 15:
                self._last_price_fetch_time = now
                self._async_load_stock_prices(missing_realtime_codes)
                
        # 2. Run pipeline filtering
        if has_df:
            self.universe_manager.run_pipeline_filtering(self.current_df)
            
        # 3. Update universe tree widget
        radar_list, watch_list, trade_list = self.universe_manager.get_pools()
        self.universe_widget.update_pools(radar_list, watch_list, trade_list)
        
        # 4. Update swing state table
        missing_history_codes = [c for c in all_codes if c not in self.stock_history_cache or not self.stock_history_cache[c]]
        if missing_history_codes:
            self._async_load_stock_history(missing_history_codes)
            
        swing_rows = []
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        for code in all_codes:
            if code in self.stock_history_cache and self.stock_history_cache[code]:
                hist = self.stock_history_cache[code]
                
                latest_close = None
                if has_df and code in self.current_df.index:
                    row = self.current_df.loc[code]
                    latest_close = float(row.get('close', row.get('price', 0.0)))
                elif code in self.price_pct_cache:
                    latest_close = self.price_pct_cache[code][0]
                else:
                    latest_close = float(hist[-1][1])
                    
                name = self.get_stock_name(code)
                
                # Append or replace today's price
                close_series = [item[1] for item in hist]
                if hist[-1][0] == today_str:
                    close_series[-1] = latest_close
                else:
                    close_series.append(latest_close)
                    
                # Calc rolling MA
                import pandas as pd
                close_pd = pd.Series(close_series)
                ma20_series = close_pd.rolling(20, min_periods=1).mean().tolist()
                ma5_series = close_pd.rolling(5, min_periods=1).mean().tolist()
                
                # Update state machine
                state, dev_str, position, reason = self.swing_tracker.update_stock_state(
                    code, name, latest_close, close_series, ma20_series, ma5_series
                )
                
                # limit ups (consecutive close days up)
                limit_ups = 0
                if len(close_series) > 1:
                    for idx in range(len(close_series)-1, 0, -1):
                        if close_series[idx] > close_series[idx-1] * 1.002:
                            limit_ups += 1
                        else:
                            break
                
                swing_rows.append((
                    code, name, f"{latest_close:.2f}", state, dev_str, str(limit_ups), position, reason
                ))
        if swing_rows:
            self.swing_table.update_data_list(swing_rows)

    def _handle_realtime_signal(self, signal):
        if not signal:
            return
        code = signal.get('code')
        name = signal.get('name')
        action = signal.get('action')
        reason = signal.get('reason') or '实时指标共振'
        self.status_bar.showMessage(f"🔔 [实时信号广播] {code} {name} -> 建议: {action} ({reason})")

    def load_font_size(self) -> int:
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return int(data.get("ats_font_size", 9))  # 默认降为更紧凑的 9pt
        except Exception as e:
            print(f"[ATSMainWindow] Error loading font size: {e}")
        return 9

    def save_font_size(self, size: int):
        try:
            import json
            import os
            import tempfile
            from sys_utils import get_app_root, get_conf_path
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        pass
                data["ats_font_size"] = size
                
                temp_dir = os.path.dirname(config_path) or "."
                fd, temp_path = tempfile.mkstemp(dir=temp_dir, text=True)
                try:
                    with os.fdopen(fd, 'w', encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(temp_path, config_path)
                except Exception as e:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    raise e
        except Exception as e:
            print(f"[ATSMainWindow] Error saving font size: {e}")

    def apply_qss_with_font_size(self, size: int):
        import re
        qss = DARK_THEME_QSS
        qss = re.sub(r'font-size:\s*\d+(\.\d+)?pt;', f'font-size: {size}pt;', qss)
        self.setStyleSheet(qss)

    def decrease_font_size(self):
        if self.current_font_size > 7:
            self.current_font_size -= 1
            self.lbl_font_size.setText(f" {self.current_font_size} pt ")
            self.save_font_size(self.current_font_size)
            self.apply_qss_with_font_size(self.current_font_size)

    def increase_font_size(self):
        if self.current_font_size < 16:
            self.current_font_size += 1
            self.lbl_font_size.setText(f" {self.current_font_size} pt ")
            self.save_font_size(self.current_font_size)
            self.apply_qss_with_font_size(self.current_font_size)

    def _restore_layout_state(self):
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from PyQt6.QtCore import QByteArray
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            if not os.path.exists(config_path):
                return
            with CONFIG_FILE_LOCK:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # 1. Restore geometry
            geom_hex = data.get("ats_main_window_geometry")
            if geom_hex:
                self.restoreGeometry(QByteArray.fromHex(geom_hex.encode()))
                
            # 2. Restore splitters
            if hasattr(self, 'main_splitter'):
                main_sizes = data.get("ats_main_splitter_sizes")
                if main_sizes:
                    self.main_splitter.setSizes(main_sizes)
            if hasattr(self, 'center_splitter'):
                center_sizes = data.get("ats_center_splitter_sizes")
                if center_sizes:
                    self.center_splitter.setSizes(center_sizes)
            if hasattr(self, 'right_splitter'):
                right_sizes = data.get("ats_right_splitter_sizes")
                if right_sizes:
                    self.right_splitter.setSizes(right_sizes)
            
            # 3. Restore tabs active indexes
            if hasattr(self, 'center_tabs'):
                center_index = data.get("ats_center_tabs_index")
                if center_index is not None:
                    self.center_tabs.setCurrentIndex(int(center_index))
            if hasattr(self, 'right_tabs'):
                right_index = data.get("ats_right_tabs_index")
                if right_index is not None:
                    self.right_tabs.setCurrentIndex(int(right_index))
        except Exception as e:
            print(f"[ATSMainWindow] Error restoring layout state: {e}")

    def _save_layout_state(self):
        try:
            import json
            import os
            import tempfile
            from sys_utils import get_app_root, get_conf_path
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_path):
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        pass
                
                # Save geometry
                data["ats_main_window_geometry"] = self.saveGeometry().toHex().data().decode()
                
                # Save splitters
                if hasattr(self, 'main_splitter'):
                    data["ats_main_splitter_sizes"] = self.main_splitter.sizes()
                if hasattr(self, 'center_splitter'):
                    data["ats_center_splitter_sizes"] = self.center_splitter.sizes()
                if hasattr(self, 'right_splitter'):
                    data["ats_right_splitter_sizes"] = self.right_splitter.sizes()
                    
                # Save tabs index
                if hasattr(self, 'center_tabs'):
                    data["ats_center_tabs_index"] = self.center_tabs.currentIndex()
                if hasattr(self, 'right_tabs'):
                    data["ats_right_tabs_index"] = self.right_tabs.currentIndex()
                
                temp_dir = os.path.dirname(config_path) or "."
                fd, temp_path = tempfile.mkstemp(dir=temp_dir, text=True)
                try:
                    with os.fdopen(fd, 'w', encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(temp_path, config_path)
                except Exception as e:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    raise e
        except Exception as e:
            print(f"[ATSMainWindow] Error saving layout state: {e}")

    def closeEvent(self, event):
        # Synchronously save all layout configurations and column widths on application exit
        try:
            # Unsubscribe from global favorites changes
            try:
                from global_favorites import GlobalFavoriteManager
                GlobalFavoriteManager().unsubscribe(self._on_favorites_changed)
            except Exception as ex:
                print(f"[ATSMainWindow] Error unsubscribing from favorites: {ex}")

            # First, save geometry and splitter layouts
            self._save_layout_state()
            
            # Next, save column widths of tables and trees
            if hasattr(self, 'universe_widget') and hasattr(self.universe_widget, 'tree'):
                if hasattr(self.universe_widget.tree, 'save_header_state'):
                    self.universe_widget.tree.save_header_state()
            elif hasattr(self, 'universe_tree') and hasattr(self.universe_tree, 'tree'):
                if hasattr(self.universe_tree.tree, 'save_header_state'):
                    self.universe_tree.tree.save_header_state()
            
            if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
                if hasattr(self.swing_table.table, 'save_column_widths'):
                    self.swing_table.table.save_column_widths()
                    
            if hasattr(self, 'trade_flow_table') and hasattr(self.trade_flow_table, 'table'):
                if hasattr(self.trade_flow_table.table, 'save_column_widths'):
                    self.trade_flow_table.table.save_column_widths()
                    
            if hasattr(self, 'position_panel') and hasattr(self.position_panel, 'table'):
                if hasattr(self.position_panel.table, 'save_column_widths'):
                    self.position_panel.table.save_column_widths()
        except Exception as e:
            print(f"[ATSMainWindow] Error saving column widths on close: {e}")
            
        super().closeEvent(event)

    def _on_favorites_changed(self):
        # Thread-safe trigger UI refresh on favorite changes using QTimer
        QTimer.singleShot(0, self._safe_favorites_changed)

    def _safe_favorites_changed(self):
        try:
            # Refresh universe tree and swing table
            self.refresh_realtime_ui()
            
            # If the universe tree is currently displaying mock data, refresh the mock view too
            if hasattr(self, 'universe_widget') and getattr(self.universe_widget, '_is_mock_active', False):
                self.universe_widget.load_mock_data()
                
            # Refresh heatmap widget
            if hasattr(self, 'heatmap_widget'):
                self.heatmap_widget.load_live_sectors()
        except Exception as e:
            print(f"[ATSMainWindow] Error refreshing UI on favorites changed: {e}")

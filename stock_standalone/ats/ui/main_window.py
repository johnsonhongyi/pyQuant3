# -*- coding: utf-8 -*-
"""
ATS Main Window Panel
Assembles the complete Autonomous Trading System UI dashboard.
"""

import sys
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTabWidget, QLabel, QToolBar, QPushButton, QStatusBar
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from ats.ui.styles import DARK_THEME_QSS
from ats.ui.universe_widget import UniverseTreeWidget
from ats.ui.heatmap_widget import SectorHeatmapWidget
from ats.ui.chart_widgets import DistributionBarChart, EquityCurveChart
from ats.ui.swing_table import SwingStateTable
from ats.ui.trade_flow import TradeFlowTable, PositionPanel, BacktestReportPanel

class ATSMainWindow(QMainWindow):
    realtime_data_signal = pyqtSignal(object)
    realtime_signal_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛡️ ATS v2 智能自治股票交易终端 (Autonomous Trading Terminal)")
        self.resize(1440, 900)
        self.current_font_size = self.load_font_size()
        self.apply_qss_with_font_size(self.current_font_size)
        
        # Connect thread-safe PyQt signals
        self.realtime_data_signal.connect(self._handle_realtime_data)
        self.realtime_signal_signal.connect(self._handle_realtime_signal)
        
        self._init_toolbar()
        self._init_ui()
        self._init_statusbar()
        
        # Load SQLite database data (P1 Integration)
        self.load_db_data()
        
        # Setup simple timer for mock ticker updating (simulate live environment in P0)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_heartbeat)
        self.update_timer.start(2000)

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
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        # 1. Left panel: Universe Tree (Width: 350)
        self.universe_widget = UniverseTreeWidget()
        self.universe_widget.setMinimumWidth(300)
        main_splitter.addWidget(self.universe_widget)

        # 2. Center panel: Swing Table & Trading Tabs (Width: 700)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        
        center_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.swing_table = SwingStateTable()
        center_splitter.addWidget(self.swing_table)
        
        # Bottom Tabs in center panel
        self.center_tabs = QTabWidget()
        
        self.position_panel = PositionPanel()
        self.center_tabs.addTab(self.position_panel, "💰 当前持仓 (Holdings)")
        
        self.trade_flow_table = TradeFlowTable()
        self.center_tabs.addTab(self.trade_flow_table, "📋 交易流水 (Orders)")
        
        self.backtest_panel = BacktestReportPanel()
        self.center_tabs.addTab(self.backtest_panel, "📊 离线回测报告 (Backtest)")
        
        center_splitter.addWidget(self.center_tabs)
        center_splitter.setSizes([450, 450])
        
        center_layout.addWidget(center_splitter)
        main_splitter.addWidget(center_widget)

        # 3. Right panel: Heatmap & Distribution charts (Width: 390)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.heatmap_widget = SectorHeatmapWidget()
        right_splitter.addWidget(self.heatmap_widget)
        
        # Right charts tab
        self.right_tabs = QTabWidget()
        
        self.dist_chart = DistributionBarChart()
        self.right_tabs.addTab(self.dist_chart, "📊 市场分布 (Dist)")
        
        self.equity_chart = EquityCurveChart()
        self.right_tabs.addTab(self.equity_chart, "📈 资金曲线 (Equity)")
        
        right_splitter.addWidget(self.right_tabs)
        right_splitter.setSizes([450, 450])
        
        right_layout.addWidget(right_splitter)
        main_splitter.addWidget(right_widget)

        # Set stretch factors and initial sizes
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setStretchFactor(2, 2)
        main_splitter.setSizes([350, 700, 390])

        # Connect internal signal linkages
        self.universe_widget.stock_selected.connect(self.on_stock_clicked)
        self.swing_table.stock_clicked.connect(self.on_stock_clicked)
        self.heatmap_widget.sector_selected.connect(self.on_sector_clicked)
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

    def on_stock_clicked(self, code, name):
        self.status_bar.showMessage(f"选中股票: {code} {name} (已同步推送至外部通达信/同花顺联动通道)")

    def on_sector_clicked(self, name):
        self.status_bar.showMessage(f"选中板块: {name} | 正在筛选相关成分股...")

    def on_heartbeat(self):
        # In actual P6, this is where we query live shared memory.
        # For P0, we do a minor change simulation to make UI look alive.
        pass

    def load_db_data(self):
        try:
            from ats.ipc_bridge import IPCBridge
            self.bridge = IPCBridge()
            
            # 1. Load trade flows
            flow_df = self.bridge.get_all_trade_flows()
            if not flow_df.empty:
                flow_data = []
                for _, row in flow_df.iterrows():
                    action = row.get('action') or ('买入' if row.get('status') == 'OPEN' else '卖出')
                    date = row.get('buy_date') if action == '买入' else (row.get('sell_date') or row.get('buy_date'))
                    price = row.get('buy_price') if action == '买入' else (row.get('sell_price') or row.get('buy_price'))
                    qty = row.get('buy_amount') or 0
                    amount = price * qty if price and qty else 0.0
                    flow_data.append((
                        str(date or ''),
                        str(row.get('code') or ''),
                        str(row.get('name') or ''),
                        str(action or ''),
                        f"{price:.2f}" if price else "0.00",
                        f"{int(qty):,}" if qty else "0",
                        f"{amount:,.2f}" if amount else "0.00",
                        str(row.get('buy_reason') or '自动触发')
                    ))
                if flow_data:
                    self.trade_flow_table.update_flow_list(flow_data)

            # 2. Load open positions
            pos_df = self.bridge.get_open_positions()
            if not pos_df.empty:
                pos_data = []
                cash = 1000000.0
                total_market_value = 0.0
                for _, row in pos_df.iterrows():
                    code = row.get('code')
                    name = row.get('name')
                    qty = row.get('buy_amount') or 0
                    cost = row.get('buy_price') or 0.0
                    price = cost  # Fallback for last price
                    market_val = qty * price
                    total_market_value += market_val
                    cash -= market_val
                    pnl_pct = "+0.00%"
                    alloc = f"{(market_val / 1000000.0) * 100:.1f}%"
                    pos_data.append((
                        str(code or ''),
                        str(name or ''),
                        f"{int(qty):,}" if qty else "0",
                        f"{cost:.2f}" if cost else "0.00",
                        f"{price:.2f}" if price else "0.00",
                        f"{market_val:,.2f}" if market_val else "0.00",
                        pnl_pct,
                        alloc
                    ))
                if pos_data:
                    self.position_panel.update_positions(pos_data, cash=max(0.0, cash), total_assets=cash + total_market_value)

            # 3. Load historical signals
            signals_df = self.bridge.get_historical_signals(limit=50)
            if not signals_df.empty:
                radar_list = []
                watch_list = []
                trade_list = []
                for _, row in signals_df.iterrows():
                    code = row.get('code')
                    name = row.get('name')
                    price = row.get('price') or 0.0
                    action = row.get('action')
                    reason = row.get('reason') or '指标共振'
                    pct = "+0.0%"
                    strategy = row.get('resample') or 'd'
                    
                    sig_tuple = (str(code or ''), str(name or ''), f"{price:.2f}", pct, f"周期:{strategy}", str(reason))
                    if action == 'BUY':
                        watch_list.append(sig_tuple)
                    else:
                        radar_list.append(sig_tuple)
                
                # Add open positions to trade list
                for _, row in pos_df.iterrows():
                    trade_list.append((
                        str(row.get('code') or ''),
                        str(row.get('name') or ''),
                        f"{row.get('buy_price') or 0.0:.2f}",
                        "+0.0%",
                        "当前持仓",
                        "大级别多头持股"
                    ))
                
                # Update universe tree
                self.universe_widget.update_pools(radar_list[:15], watch_list[:15], trade_list)

            # 4. Load equity curves
            dates, strat_equity, bench_equity = self.bridge.get_equity_curve_data()
            x = list(range(len(dates)))
            self.equity_chart.update_curve(x, strat_equity, bench_equity)

            # 5. Load performance metrics using BacktestEngine
            from ats.backtest_engine import BacktestEngine
            self.backtest_engine = BacktestEngine(self.bridge)
            metrics = self.backtest_engine.calculate_performance_metrics()
            self.backtest_panel.update_stats(metrics)

            # 6. Start real-time IPC socket listener (P6)
            self.bridge.start_realtime_listener(
                port=26669,
                data_callback=lambda data: self.realtime_data_signal.emit(data),
                signal_callback=lambda sig: self.realtime_signal_signal.emit(sig)
            )

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
        df = None
        if isinstance(data_pkg, pd.DataFrame):
            df = data_pkg
        elif isinstance(data_pkg, dict):
            df = data_pkg.get('full_snapshot')
        elif isinstance(data_pkg, tuple) and len(data_pkg) > 0:
            df = data_pkg[0]
            
        if df is not None and not df.empty:
            self.lbl_ipc_status.setText("  IPC 通道: 🔌 实时接入中  |  ")
            self.lbl_ipc_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            
            # Calculate and update today's A-share return distribution
            if 'percent' in df.columns:
                pcts = df['percent'].dropna()
                bins = [-999, -8, -6, -4, -2, 0, 2, 4, 6, 8, 999]
                counts = pd.cut(pcts, bins=bins).value_counts().sort_index().tolist()
                if len(counts) == 10:
                    self.dist_chart.update_data(counts)
            
            self.status_bar.showMessage(f"已同步接收到主进程最新实时行情快照 (个股数: {len(df)})")

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
            config_path = get_conf_path("window_config.json", get_app_root())
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
            config_path = get_conf_path("window_config.json", get_app_root())
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

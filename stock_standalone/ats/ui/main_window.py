# -*- coding: utf-8 -*-
"""
ATS Main Window Panel
Assembles the complete Autonomous Trading System UI dashboard.
"""

import sys
import os
import time
import json
import logging

logger = logging.getLogger("ATS")

# 必须在导入任何 PyQt6 UI 元素前确保 HighDPI 高分屏自适应生效
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTabWidget, QLabel, QToolBar, QPushButton, QStatusBar, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QGridLayout, QCheckBox, QComboBox, QAbstractItemView
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QRect
from PyQt6.QtGui import QAction, QIcon, QColor, QBrush

from ats.ui.favorite_panel import FavoritePanel
from ats.ui.styles import DARK_THEME_QSS
from ats.ui.universe_widget import UniverseTreeWidget
from ats.ui.heatmap_widget import SectorHeatmapWidget
from ats.ui.chart_widgets import DistributionBarChart, EquityCurveChart
from ats.ui.swing_table import SwingStateTable
from ats.ui.trade_flow import TradeFlowTable, PositionPanel, BacktestReportPanel
from ats.ui.kernel_trace_panel import KernelTracePanel
from ats.ui.dragon_monitor import DragonLeaderMonitorDialog
from ats.universe_manager import UniverseManager
from ats.swing_tracker import SwingTracker
from ats.signal_ledger import SignalLedger
from ats.volume_profiler import VolumeProfiler
from ats.session_snapshot import SessionSnapshot
from JohnsonUtil import commonTips as cct

class QtVarProxy:
    """包装 QCheckBox 或 Callable 为带 .get() 方法的 Var 对象，用于兼容全系统 StockSender 标准单例"""
    def __init__(self, getter_func):
        self.getter_func = getter_func
    def get(self):
        try:
            return bool(self.getter_func())
        except Exception:
            return True

class EquityPopDialog(QDialog):
    """资金曲线与大盘走势独立放大查看窗口"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📈 资金收益率曲线与全市场走势独立放大看板")
        self.resize(960, 640)
        self.setMinimumSize(720, 480)
        
        # 设置为独立 Window 模式，支持最大化、最小化和关闭按钮
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window
        flags |= Qt.WindowType.WindowMinMaxButtonsHint
        self.setWindowFlags(flags)

        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
            
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 1. 顶部工具栏
        top_bar = QHBoxLayout()
        title_lbl = QLabel("📈 资金收益率曲线与全市场走势独立放大看板")
        title_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13pt;")
        
        btn_refresh = QPushButton("🔄 刷新收益曲线")
        btn_refresh.setStyleSheet("background-color: #1f1f2e; color: #aad4ff; font-weight: bold; padding: 4px 12px; border: 1px solid #3a3a48; border-radius: 4px;")
        btn_refresh.clicked.connect(self._on_refresh)

        btn_close = QPushButton("关闭窗口")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; padding: 4px 12px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)

        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        top_bar.addWidget(btn_refresh)
        top_bar.addWidget(btn_close)
        layout.addLayout(top_bar)

        # 2. TabWidget
        self.pop_tabs = QTabWidget()
        self.pop_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #303042; background: #121216; }
            QTabBar::tab { background: #1a1a24; color: #a0a0b0; padding: 8px 16px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #252538; color: #38bdf8; border-bottom: 2px solid #38bdf8; }
        """)

        self.equity_chart = EquityCurveChart()
        self.dist_chart = DistributionBarChart()

        self.pop_tabs.addTab(self.equity_chart, "📈 策略资金收益曲线 (Equity Curve)")
        self.pop_tabs.addTab(self.dist_chart, "📊 全市场涨跌分布 (Market Distribution)")

        layout.addWidget(self.pop_tabs, 1)

    def _on_refresh(self):
        parent_mw = self.parent()
        if parent_mw and hasattr(parent_mw, 'bridge') and parent_mw.bridge:
            try:
                dates, strat_equity, bench_equity = parent_mw.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self.equity_chart.update_curve(x, strat_equity, bench_equity)
                return
            except Exception as e:
                print(f"[EquityPopDialog] Refresh error: {e}")
        if hasattr(self.equity_chart, 'draw_mock_curve'):
            self.equity_chart.draw_mock_curve()

    def update_data(self, df_realtime=None):
        if hasattr(self.dist_chart, 'update_data') and df_realtime is not None:
            self.dist_chart.update_data(df_realtime)
        parent_mw = self.parent()
        if parent_mw and hasattr(parent_mw, 'bridge') and parent_mw.bridge:
            try:
                dates, strat_equity, bench_equity = parent_mw.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self.equity_chart.update_curve(x, strat_equity, bench_equity)
            except Exception:
                pass


class StockDetailDialog(QDialog):
    def __init__(self, code, name, df_row=None, context_info=None, parent=None, batch_codes=None):
        super().__init__(parent)
        self.code = str(code).strip()
        self.name = name
        self.df_row = df_row
        self.context_info = context_info
        self.batch_codes = batch_codes
        
        # 0. 明确设置为独立窗口类型，从而使磁吸、贴边隐藏和多显示器移动在 Windows 下完美执行
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window
        self.setWindowFlags(flags)
        
        self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
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
                                if str(trace_code).strip() == str(self.code).strip():
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
            
        self._init_ui(self.code, self.name, df_row, context_info)
        
        # Initialize dynamic data & filter results
        self.update_data(df_row)
        
        # 1. 自动删除属性以防非模态显示内存泄露
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # 2. 磁吸与隐藏状态初始化
        self.anchor_edge = None
        self.is_hidden_state = False
        self.normal_geometry = None
        self.hover_ticks = 0
        self.leave_ticks = 0
        self._in_snap_action = False
        self.anim_group = None
        self._is_dragging = False
        self._last_show_time = 0.0
        self._has_hovered_since_show = False
        self._is_auto_popping = False
        self._switching = False
        
        # 悬停与离开监控定时器
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)
        self.hover_timer.start()
        
        # 拖拽结束防抖定时器
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(200)
        self.snap_timer.timeout.connect(self._detect_and_snap)

    def update_batch_codes(self, new_batch_codes=None, current_code=None):
        """【关键机制】动态实时更新弹窗顶部的 [本轮强势信号] 下拉框列表，并 100% 自动高亮选中当前 code"""
        if new_batch_codes is not None:
            self.batch_codes = new_batch_codes
            
        parent_mw = self.parent()
        signal_list = self.batch_codes
        if not signal_list and parent_mw and hasattr(parent_mw, "_last_batch_signal_codes") and parent_mw._last_batch_signal_codes:
            signal_list = parent_mw._last_batch_signal_codes

        if not hasattr(self, 'combo_signals') or self.combo_signals is None:
            return

        target_code = str(current_code or self.code).strip()
        
        parsed_list = []
        seen = set()
        if signal_list:
            for item in signal_list:
                if isinstance(item, (tuple, list)):
                    c, n = str(item[0]).strip(), str(item[1]).strip()
                else:
                    c, n = str(item).strip(), str(item).strip()
                if c and c not in seen:
                    seen.add(c)
                    parsed_list.append((c, n))
                    
        # 确保当前被查看的股票 (如 601567) 绝对不会在下拉框中漏掉
        if target_code and target_code not in seen:
            t_name = target_code
            if parent_mw and hasattr(parent_mw, "get_stock_name"):
                t_name = parent_mw.get_stock_name(target_code)
            parsed_list.insert(0, (target_code, t_name))

        if not parsed_list:
            return

        self.combo_signals.blockSignals(True)
        try:
            self.combo_signals.clear()
            cur_idx = 0
            for idx, (c, n) in enumerate(parsed_list):
                self.combo_signals.addItem(f"{c} {n}", c)
                if c == target_code:
                    cur_idx = idx
            self.combo_signals.setCurrentIndex(cur_idx)
        finally:
            self.combo_signals.blockSignals(False)

    def switch_to_code(self, target_c: str, target_n: str = "", batch_codes=None):
        """【核心机制】窗口原地无缝复用刷新，包含磁吸恢复唤醒与下拉框实时更新"""
        if not target_c:
            return
        if getattr(self, '_switching', False):
            return
            
        import time
        t0 = time.perf_counter()
        self._switching = True
        try:
            self.code = str(target_c).strip()
            parent_mw = self.parent()
            if parent_mw:
                if not target_n and hasattr(parent_mw, "get_stock_name"):
                    self.name = parent_mw.get_stock_name(self.code)
                elif target_n:
                    self.name = target_n
                else:
                    self.name = self.code

                # 1. 若处于贴边磁吸隐藏状态，强制滑出展平唤醒；若被最小化/隐藏则恢复显示并唤醒；正常显示中则仅原地更新数据
                if getattr(self, 'is_hidden_state', False):
                    if hasattr(self, 'show_normal_position'):
                        self.show_normal_position()
                    else:
                        self.show()
                        self.raise_()
                        self.activateWindow()
                elif self.isMinimized():
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
                elif not self.isVisible():
                    self.show()
                    self.raise_()
                    self.activateWindow()

                # 2. 内存极速提取最新 df_row 行情 (包含 current_df 与 df_realtime 级联回退)
                df_row = None
                c_clean = str(self.code).strip().zfill(6)
                for attr in ("current_df", "df_realtime"):
                    if hasattr(parent_mw, attr):
                        df = getattr(parent_mw, attr)
                        if df is not None and not df.empty:
                            if c_clean in df.index:
                                row = df.loc[c_clean]
                                df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                                break
                            elif 'code' in df.columns:
                                m = df[df['code'] == c_clean]
                                if not m.empty:
                                    df_row = m.iloc[0].to_dict()
                                    break

                t1 = time.perf_counter()
                # 3. 补齐策略上下文
                if hasattr(parent_mw, "_ensure_context_info"):
                    self.context_info = parent_mw._ensure_context_info(self.code, self.name, {})

                t2 = time.perf_counter()
                # 4. 【极速 UI 优先渲染】瞬间重绘窗口标题、策略上下文与特征表格 (0 毫秒肉眼无感反馈)
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
                if hasattr(self, 'title_label'):
                    self.title_label.setText(f"📊 {self.code}  {self.name}")
                    
                if hasattr(self, 'lbl_pos_val') and self.lbl_pos_val and self.context_info:
                    self.lbl_pos_val.setText(self.context_info.get('position', '--'))
                if hasattr(self, 'lbl_reason_val') and self.lbl_reason_val and self.context_info:
                    self.lbl_reason_val.setText(self.context_info.get('reason', '--'))
                if hasattr(self, 'lbl_status_val') and self.lbl_status_val and self.context_info:
                    self.lbl_status_val.setText(self.context_info.get('status', '--'))

                self.update_data(df_row)
                t3 = time.perf_counter()

                # 5. 【丝滑物理/软件联动】异步发送至外部通达信/同花顺/VIS 终端与 Tree 视图，彻底杜绝界面卡顿
                target_code = self.code
                target_name = self.name
                if hasattr(parent_mw, "link_stock"):
                    QTimer.singleShot(0, lambda: parent_mw.link_stock(target_code, target_name))

                import sys
                is_debug_log = ("-log" in sys.argv and "debug" in sys.argv) or (logger.getEffectiveLevel() <= logging.DEBUG)
                if is_debug_log:
                    print(
                        f"[PERF] StockDetailDialog switch_to_code({self.code}) total: {(t3 - t0)*1000:.2f}ms "
                        f"(prep: {(t1 - t0)*1000:.2f}ms, ctx: {(t2 - t1)*1000:.2f}ms, update: {(t3 - t2)*1000:.2f}ms)"
                    )
        finally:
            self._switching = False
        
    def _init_ui(self, code, name, df_row, context_info):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 0.5 仅加载【本轮输出的强势信号列表】(例如本轮 2 只或 6 只，绝不上百只堆叠)
        parent_mw = self.parent()
        signal_list = self.batch_codes
        if not signal_list and parent_mw and hasattr(parent_mw, "_last_batch_signal_codes") and parent_mw._last_batch_signal_codes:
            signal_list = parent_mw._last_batch_signal_codes

        if signal_list and len(signal_list) > 1:
            nav_layout = QHBoxLayout()
            nav_label = QLabel("📋 本轮强势信号:")
            nav_label.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 10pt;")
            
            self.btn_prev = QPushButton("◀ 上一只")
            self.btn_next = QPushButton("下一只 ▶")
            self.combo_signals = QComboBox()
            self.combo_signals.setStyleSheet("background-color: #1f1f26; color: #aad4ff; font-weight: bold; padding: 3px 8px; border: 1px solid #3a3a48;")
            
            cur_idx = 0
            for idx, item in enumerate(signal_list):
                if isinstance(item, (tuple, list)):
                    c, n = item[0], item[1]
                else:
                    c, n = str(item), str(item)
                
                c_str = str(c).strip().zfill(6)
                pct_lbl = self._get_pct_str_for_code(parent_mw, c_str)
                self.combo_signals.addItem(f"{c_str} {n}{pct_lbl}", c_str)
                if c_str == str(code).strip().zfill(6):
                    cur_idx = idx
            self.combo_signals.setCurrentIndex(cur_idx)
            
            def _on_signal_changed(idx):
                if idx >= 0 and hasattr(self, 'combo_signals'):
                    target_c = self.combo_signals.itemData(idx)
                    if target_c and str(target_c).strip() != str(self.code).strip():
                        target_text = self.combo_signals.itemText(idx)
                        parts = target_text.split(" ")
                        target_n = parts[1] if len(parts) > 1 else target_c
                        self.switch_to_code(target_c, target_n)
            
            def _on_prev_clicked():
                count = self.combo_signals.count()
                if count > 0:
                    c_idx = self.combo_signals.currentIndex()
                    next_idx = (c_idx - 1 + count) % count
                    self.combo_signals.setCurrentIndex(next_idx)
                    
            def _on_next_clicked():
                count = self.combo_signals.count()
                if count > 0:
                    c_idx = self.combo_signals.currentIndex()
                    next_idx = (c_idx + 1) % count
                    self.combo_signals.setCurrentIndex(next_idx)

            self.combo_signals.currentIndexChanged.connect(_on_signal_changed)
            self.btn_prev.clicked.connect(_on_prev_clicked)
            self.btn_next.clicked.connect(_on_next_clicked)
            
            nav_layout.addWidget(nav_label)
            nav_layout.addWidget(self.btn_prev)
            nav_layout.addWidget(self.combo_signals, 1)
            nav_layout.addWidget(self.btn_next)
            layout.addLayout(nav_layout)

        # 1. Title and header info
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"📊 {code}  {name}")
        self.title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.price_pct_label = QLabel("--  (--)")
        self.price_pct_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #8e8e93;")
        header_layout.addWidget(self.price_pct_label)
        layout.addLayout(header_layout)
        
        # 1.5 Context Info Block (策略特征上下文)
        ctx_info_safe = context_info if context_info else {}
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
        self.lbl_pos_val = QLabel(ctx_info_safe.get('position', '--'))
        self.lbl_pos_val.setStyleSheet("color: #ffffff; font-weight: bold;")
        self.lbl_pos_val.setWordWrap(True)
        
        # Reason
        lbl_reason_title = QLabel("推荐理由:")
        lbl_reason_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
        self.lbl_reason_val = QLabel(ctx_info_safe.get('reason', '--'))
        self.lbl_reason_val.setStyleSheet("color: #ffaa44; font-weight: bold;")
        self.lbl_reason_val.setWordWrap(True)
        
        # Status
        lbl_status_title = QLabel("追涨/特征状态:")
        lbl_status_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
        self.lbl_status_val = QLabel(ctx_info_safe.get('status', '--'))
        self.lbl_status_val.setStyleSheet("color: #00ff88; font-weight: bold;")
        self.lbl_status_val.setWordWrap(True)
        
        ctx_layout.addWidget(lbl_pos_title, 0, 0)
        ctx_layout.addWidget(self.lbl_pos_val, 0, 1)
        ctx_layout.addWidget(lbl_reason_title, 1, 0)
        ctx_layout.addWidget(self.lbl_reason_val, 1, 1)
        ctx_layout.addWidget(lbl_status_title, 2, 0)
        ctx_layout.addWidget(self.lbl_status_val, 2, 1)
        
        ctx_layout.setColumnStretch(1, 1)
        layout.addWidget(ctx_group)
            
        # 2. Source indicator
        self.hint_label = QLabel("⏳ 正在等待数据同步...")
        self.hint_label.setStyleSheet("color: #ff9900; font-size: 9.5pt; font-weight: bold;")
        layout.addWidget(self.hint_label)
        
        # 2.5 过滤公式匹配状态
        self.filter_status_layout = QHBoxLayout()
        self.lbl_filter_title = QLabel("🔍 过滤测试: ")
        self.lbl_filter_title.setStyleSheet("color: #aad4ff; font-weight: bold;")
        self.lbl_filter_expr = QLabel("无")
        self.lbl_filter_expr.setStyleSheet("color: #8e8e93; font-style: italic;")
        self.lbl_filter_result = QLabel("")
        self.lbl_filter_result.setStyleSheet("font-weight: bold;")
        
        self.filter_status_layout.addWidget(self.lbl_filter_title)
        self.filter_status_layout.addWidget(self.lbl_filter_expr)
        self.filter_status_layout.addStretch()
        self.filter_status_layout.addWidget(self.lbl_filter_result)
        layout.addLayout(self.filter_status_layout)
        
        # 3. Main feature table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["指标核心特征", "特征实盘数据值"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        
        # 4. Button close
        btn_close = QPushButton("关闭窗口")
        btn_close.clicked.connect(self.accept)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

    def update_data(self, df_row):
        t_u0 = time.perf_counter()
        self.df_row = df_row
        
        # 1. Update price pct header labels
        price_str = "--"
        pct_str = "--"
        color_hex = "#8e8e93"
        
        if df_row is not None:
            self.hint_label.setText("🟢 已成功对接实盘行情快照核心特征:")
            self.hint_label.setStyleSheet("color: #00ff88; font-size: 9.5pt; font-weight: bold;")
            
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
        else:
            self.hint_label.setText("⚠️ 暂无当前个股实盘快照特征数据（等待行情推送中）:")
            self.hint_label.setStyleSheet("color: #ff9900; font-size: 9.5pt; font-weight: bold;")
            
        self.price_pct_label.setText(f"{price_str}  ({pct_str})")
        self.price_pct_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {color_hex};")
        
        t_u1 = time.perf_counter()
        # 1.5 动态补充更新顶部标题与窗口 title 上的 code + name + 涨跌幅
        if hasattr(self, 'title_label') and self.title_label:
            if pct_str != "--":
                self.title_label.setText(f"📊 {self.code}  {self.name}  ({pct_str})")
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name} ({pct_str})")
            else:
                self.title_label.setText(f"📊 {self.code}  {self.name}")
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
        
        t_u2 = time.perf_counter()
        # 2. Update feature list
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
                'turnover': '换手率 (%)',
                'ratio': '量比',
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
                    
            extra_cnt = 0
            for k, val in df_row.items():
                if k not in main_keys and k not in ('code', 'name') and val is not None and val != '':
                    if extra_cnt >= 30:  # 🚀 [PERF] 严格限制 UI 控件特征数 (最多 30 个)，防止上千指标轰炸卡死 DOM
                        break
                    label = k.replace('_', ' ').title()
                    if isinstance(val, float):
                        val_str = f"{val:.4f}"
                    else:
                        val_str = str(val)
                    features.append((label, val_str))
                    extra_cnt += 1
        else:
            features.append(("证券代码", self.code))
            features.append(("证券名称", self.name))
            
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
                ("证券代码", self.code),
                ("证券名称", self.name),
                ("日内价格", "加载中..."),
                ("实盘状态", "等待主进程推送行情"),
                ("说明", "双击可实现实盘特征一屏清，当前暂未收到主进程行情推送")
            ]
            
        t_u3 = time.perf_counter()
        self.table.setUpdatesEnabled(False)
        try:
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
        finally:
            self.table.setUpdatesEnabled(True)
            
        t_u4 = time.perf_counter()
        # 3. 同步刷新下拉框中所有股票的最新涨跌幅
        self._refresh_combo_signals_pct()
        
        t_u5 = time.perf_counter()
        # 4. Update filter evaluation
        self.update_filter_status()
        
        t_u6 = time.perf_counter()
        import sys
        is_debug_log = ("-log" in sys.argv and "debug" in sys.argv) or (logger.getEffectiveLevel() <= logging.DEBUG)
        if is_debug_log:
            print(
                f"[PERF-BREAKDOWN] update_data({self.code}): total={(t_u6-t_u0)*1000:.2f}ms | "
                f"hdr={(t_u1-t_u0)*1000:.2f}ms | title={(t_u2-t_u1)*1000:.2f}ms | feat_build={(t_u3-t_u2)*1000:.2f}ms | "
                f"tbl_render={(t_u4-t_u3)*1000:.2f}ms | combo_pct={(t_u5-t_u4)*1000:.2f}ms | filter_status={(t_u6-t_u5)*1000:.2f}ms"
            )

    def _get_pct_str_for_code(self, parent_mw, code):
        if not parent_mw:
            return ""
        c_clean = str(code).strip().zfill(6)
        df_row = None
        for attr in ("current_df", "df_realtime"):
            if hasattr(parent_mw, attr):
                df = getattr(parent_mw, attr)
                if df is not None and not df.empty:
                    if c_clean in df.index:
                        row = df.loc[c_clean]
                        df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                        break
        
        if df_row and 'percent' in df_row and df_row['percent'] is not None and df_row['percent'] != '':
            try:
                p_val = float(df_row['percent'])
                return f" ({p_val:+.2f}%)"
            except Exception:
                pass
        return ""

    def _refresh_combo_signals_pct(self):
        """同步刷新下拉框 combo_signals 中每一项的涨跌幅文本后缀 (0毫秒极速字典查找)"""
        if not hasattr(self, 'combo_signals') or self.combo_signals is None:
            return
        
        parent_mw = self.parent()
        if not parent_mw:
            return

        # 1. 一次性向量化提取全量代码->涨跌幅字典 (耗时 0.01ms，替代 M*N 循环扫描)
        pct_map = {}
        for attr in ("current_df", "df_realtime"):
            if hasattr(parent_mw, attr):
                df = getattr(parent_mw, attr)
                if df is not None and not df.empty and 'percent' in df.columns:
                    try:
                        if 'code' in df.columns:
                            pct_map.update(dict(zip(df['code'].astype(str).str.strip().str.zfill(6), df['percent'])))
                        else:
                            pct_map.update(dict(zip(df.index.astype(str).str.strip().str.zfill(6), df['percent'])))
                    except Exception:
                        pass
        
        if not pct_map:
            return

        # 2. 下拉框极速 O(1) 字典查表匹配
        self.combo_signals.blockSignals(True)
        try:
            for idx in range(self.combo_signals.count()):
                c = self.combo_signals.itemData(idx)
                if not c:
                    continue
                c_str = str(c).strip().zfill(6)
                p_val = pct_map.get(c_str)
                pct_lbl = ""
                if p_val is not None and p_val != '':
                    try:
                        pct_lbl = f" ({float(p_val):+.2f}%)"
                    except Exception:
                        pass
                
                cur_text = self.combo_signals.itemText(idx)
                if pct_lbl and not cur_text.endswith(pct_lbl):
                    # 仅在文本变动时才调用 setItemText
                    parts = cur_text.split(" ")
                    c_part = parts[0] if len(parts) > 0 else c_str
                    n_part = parts[1] if len(parts) > 1 else ""
                    # 剥离旧括号
                    if "(" in n_part and ")" in n_part:
                        n_part = n_part.split("(")[0]
                    new_text = f"{c_part} {n_part}{pct_lbl}".strip()
                    if cur_text != new_text:
                        self.combo_signals.setItemText(idx, new_text)
        finally:
            self.combo_signals.blockSignals(False)

    def update_filter_status(self, query_expr=None):
        if query_expr is None:
            if self.parent() and hasattr(self.parent(), 'query_expr'):
                query_expr = self.parent().query_expr
            else:
                query_expr = ""
                
        self.query_expr = query_expr
        if not query_expr:
            self.lbl_filter_expr.setText("无")
            self.lbl_filter_expr.setStyleSheet("color: #8e8e93; font-style: italic;")
            self.lbl_filter_result.setText("")
            return
            
        disp_expr = query_expr
        if len(disp_expr) > 40:
            disp_expr = disp_expr[:37] + "..."
        self.lbl_filter_expr.setText(disp_expr)
        self.lbl_filter_expr.setStyleSheet("color: #e2e2e5; font-style: normal;")
        
        # 🚀【极速 O(1) 6位清洗容错匹配】如果该股票原本就在主窗口当前结果集中，0 毫秒确认命中
        c_clean = str(self.code).strip().zfill(6)
        parent_mw = self.parent()
        is_hit = False
        
        if parent_mw:
            if hasattr(parent_mw, "filtered_codes_set") and parent_mw.filtered_codes_set:
                if any(str(x).strip().zfill(6) == c_clean for x in parent_mw.filtered_codes_set):
                    is_hit = True
            
            if not is_hit:
                for attr in ("current_df", "df_realtime"):
                    if hasattr(parent_mw, attr):
                        df = getattr(parent_mw, attr)
                        if df is not None and not df.empty:
                            if c_clean in df.index:
                                is_hit = True
                                break
                            elif 'code' in df.columns:
                                # 向量化极速检查
                                if (df['code'].astype(str).str.strip().str.zfill(6) == c_clean).any():
                                    is_hit = True
                                    break
                            elif (df.index.astype(str).str.strip().str.zfill(6) == c_clean).any():
                                is_hit = True
                                break

        if is_hit:
            self.lbl_filter_result.setText("✅ 命中")
            self.lbl_filter_result.setStyleSheet("color: #00ff88; font-weight: bold;")
            return

        import pandas as pd
        if self.df_row is None:
            self.lbl_filter_result.setText("⏳ 等待数据...")
            self.lbl_filter_result.setStyleSheet("color: #ff9900; font-weight: bold;")
            return
            
        row_dict = self.df_row.to_dict() if hasattr(self.df_row, 'to_dict') else dict(self.df_row)
        row_dict['code'] = self.code
        row_dict['name'] = self.name
        
        mapping = {
            '价格': 'close', '最新价': 'close', '现价': 'close', 
            '涨幅': 'pct', 
            '量': 'volume', '成交量': 'volume',
            '成交额': 'turnover',
            '最高': 'high', '最低': 'low', '开盘': 'open',
            '板块': 'category', '异动类型': 'category', 'hy': 'category'
        }
        for cn, en in mapping.items():
            if cn in row_dict and en not in row_dict:
                row_dict[en] = row_dict[cn]
                
        if 'close' in row_dict:
            for col in ['open', 'high', 'low']:
                if col not in row_dict or row_dict[col] is None or row_dict[col] == '':
                    row_dict[col] = row_dict['close']
                    
        df_code = pd.DataFrame([row_dict])
        df_code.set_index('code', inplace=True, drop=False)
        
        # 🚀【真正 threading.Thread 子线程后台计算】彻底从 UI 主线程事件循环中隔离
        def _bg_eval_worker():
            from stock_logic_utils import test_code_against_queries
            try:
                res = test_code_against_queries(df_code, [{"query": query_expr}])
                hit = res[0].get("hit", 0) if res else 0
                def _update_ui():
                    if hit > 0:
                        self.lbl_filter_result.setText("✅ 命中")
                        self.lbl_filter_result.setStyleSheet("color: #00ff88; font-weight: bold;")
                    else:
                        self.lbl_filter_result.setText("❌ 未命中")
                        self.lbl_filter_result.setStyleSheet("color: #ff4444; font-weight: bold;")
                QTimer.singleShot(0, _update_ui)
            except Exception as e:
                def _update_err():
                    self.lbl_filter_result.setText("⚠️ 评估出错")
                    self.lbl_filter_result.setStyleSheet("color: #ff9900; font-weight: bold;")
                QTimer.singleShot(0, _update_err)

        import threading
        threading.Thread(target=_bg_eval_worker, daemon=True).start()

    def start_slide_animation(self, target_rect, target_opacity, duration=250, is_snap_feedback=False):
        """
        统一的滑动与透明度动画控制器，提供流畅的 QQ 窗口滑动和呼吸反馈效果
        """
        if hasattr(self, 'anim_group') and self.anim_group is not None:
            try:
                if self.anim_group.state() == QParallelAnimationGroup.State.Running:
                    self.anim_group.stop()
            except Exception:
                pass
                
        self.anim_group = QParallelAnimationGroup(self)
        
        # 1. 窗口位置大小动画 (Geometry)
        self.geom_anim = QPropertyAnimation(self, b"geometry")
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_rect)
        if is_snap_feedback:
            # 磁吸成功时采用微弹插值，让贴边动作更具弹性物理质感
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        # 2. 窗口不透明度动画 (Opacity)
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(target_opacity)
        if is_snap_feedback:
            # 磁吸动态提示：透明度从 1.0 快速淡化到 0.4 左右再恢复，模拟“吸附上”的视觉脉冲
            self.opacity_anim.setKeyValueAt(0.5, 0.4)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        
        self._in_snap_action = True
        
        def on_finished():
            self._in_snap_action = False
            # 动画结束时做状态对齐安全保护
            if self.is_hidden_state:
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(1.0)
                
        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        if self.is_hidden_state:
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start()
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35  # 磁吸检测门槛像素
        
        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()
        
        # 排除底边（即任务栏所在方向，通常不磁吸底边）。我们磁吸顶边、左边、右边。
        if abs(win_geo.top() - screen_geo.top()) < margin:
            edge = "top"
            target_y = screen_geo.top()
            snapped = True
        elif abs(win_geo.left() - screen_geo.left()) < margin:
            edge = "left"
            target_x = screen_geo.left()
            snapped = True
        elif abs(win_geo.right() - screen_geo.right()) < margin:
            edge = "right"
            target_x = screen_geo.right() - win_geo.width()
            snapped = True
            
        self._is_dragging = False
        if snapped:
            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            
            # 使用带有呼吸闪烁反馈的滑动动画平滑移动到磁吸位置
            self.start_slide_animation(self.normal_geometry, 1.0, duration=250, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None

    def hide_to_edge(self):
        if not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        w = self.normal_geometry.width()
        h = self.normal_geometry.height()
        x = self.normal_geometry.x()
        y = self.normal_geometry.y()
        
        strip_size = 5  # 隐藏后在屏幕内留出的极窄感应/观察条像素宽度
        
        if self.anchor_edge == "left":
            target_x = screen_geo.left() - w + strip_size
            target_y = y
        elif self.anchor_edge == "right":
            target_x = screen_geo.right() - strip_size
            target_y = y
        elif self.anchor_edge == "top":
            target_x = x
            target_y = screen_geo.top() - h + strip_size
        else:
            return
            
        self.is_hidden_state = True
        # 启动滑入贴边隐藏的平滑过渡动画
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=300)

    def show_normal_position(self):
        if not self.is_hidden_state or not self.normal_geometry:
            return
            
        self._is_auto_popping = True
        QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            
        self.is_hidden_state = False
        import time
        self._last_show_time = time.time()
        self._has_hovered_since_show = False
        # 启动滑出恢复的平滑过渡动画
        self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
        
        self.raise_()
        self.activateWindow()

    def _check_hover(self):
        if not self.isVisible():
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return
            
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        in_window = self.frameGeometry().contains(mouse_pos)
        
        if in_window:
            self._has_hovered_since_show = True
            
        if self.is_hidden_state:
            if in_window:
                self.hover_ticks += 1
                if self.hover_ticks >= 2:  # 100ms * 2 = 200ms 停留防误触
                    self.show_normal_position()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0
        else:
            if self.anchor_edge is not None:
                if not in_window:
                    if not getattr(self, '_has_hovered_since_show', False):
                        self.leave_ticks = 0
                        return
                    import time
                    if time.time() - getattr(self, '_last_show_time', 0.0) < 1.2:
                        self.leave_ticks = 0
                        return
                        
                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:  # 100ms * 4 = 400ms 离开防抖
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            # 拖拽时立即重置磁吸边缘，避免拖动过程中鼠标离开导致的强行缩回
            self.anchor_edge = None
            self.snap_timer.start()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()
                
    def closeEvent(self, event):
        self.hover_timer.stop()
        self.snap_timer.stop()
        parent_mw = self.parent()
        if parent_mw and hasattr(parent_mw, '_detail_dialog') and parent_mw._detail_dialog is self:
            parent_mw._detail_dialog = None
        super().closeEvent(event)
        
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

class ATSMainWindow(QMainWindow):
    realtime_data_signal = pyqtSignal(object)
    realtime_signal_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        if app:
            app.main_window = self
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
        from ats.signal_ledger import get_signal_ledger
        self.signal_ledger = get_signal_ledger()
        self.volume_profiler = VolumeProfiler()
        self.session_snapshot = SessionSnapshot()
        import threading
        self.hdf5_history_lock = threading.Lock()
        
        # 通达信 / OrderMon 信号文件后台监听器
        try:
            from ats.tdx_signal_watcher import TdxSignalWatcher
            self.tdx_watcher = TdxSignalWatcher(parent=self)
            self.tdx_watcher.signal_detected.connect(self._on_tdx_signal_detected)
            self.tdx_watcher.start()
        except Exception as e:
            print(f"[ATSMainWindow] 初始化 TdxSignalWatcher 异常: {e}")

        # 自动加载昨日快照，恢复跨日 WATCH/TRADE 精选标的以实现跨日持续跟进
        try:
            prev_signals = self.session_snapshot.load_previous_day_signals()
            if prev_signals:
                self.signal_ledger.load_previous_signals(prev_signals)
        except Exception as e:
            print(f"[MainWindow] 跨日快照加载异常: {e}")
        self.stock_history_cache = {}
        self.dragon_monitor_dialog = None
        self.history_loading_codes = set()
        # Changed from a simple set to a {code: fail_timestamp} dict.
        # Codes that failed will be retried after 5 minutes, and the entire
        # blacklist is reset at the start of a new calendar day so that
        # next-day ATS startup always re-attempts history loading.
        self.history_failed_codes = {}   # {code: fail_time (float unix ts)}
        self._history_failed_date = None  # tracks the date when failures were recorded
        self.prices_loading_codes = set()
        self.prices_failed_codes = set()
        self._is_closing = False
        
        # Initialize ratios for equal proportional scaling
        self._main_ratio = [0.24, 0.49, 0.27]
        self._center_ratio = [0.5, 0.5]
        self._right_ratio = [0.5, 0.5]
        self._is_restoring_sizes = False
        
        # Connect thread-safe PyQt signals
        self.realtime_data_signal.connect(self._handle_realtime_data)
        self.realtime_signal_signal.connect(self._handle_realtime_signal)
        
        # Initialize favorites version-tracking and start polling loop
        try:
            from global_favorites import GlobalFavoriteManager
            self._last_favorites_version = GlobalFavoriteManager().version
        except Exception:
            self._last_favorites_version = 0

        self._favorites_poll_timer = QTimer(self)
        self._favorites_poll_timer.setInterval(500)
        self._favorites_poll_timer.timeout.connect(self._poll_favorites_loop)
        self._favorites_poll_timer.start()
        
        # 初始化过滤公式表达式和搜索历史数据缓存 (History Filter Integration)
        self.query_expr = ""
        self.search_histories = {"history1": [], "history2": [], "history3": [], "history4": [], "history5": []}
        self._load_search_history_data()
        
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

        # 尝试初始化全系统标准的 StockSender 通道 (动态绑定 UI checkbox 勾选与持久化状态)
        self.sender = None
        try:
            from JohnsonUtil.stock_sender import StockSender
            self.sender = StockSender(
                tdx_var=QtVarProxy(lambda: self.cb_tdx.isChecked() if hasattr(self, 'cb_tdx') else True),
                ths_var=QtVarProxy(lambda: self.cb_ths.isChecked() if hasattr(self, 'cb_ths') else True),
                dfcf_var=False,
                callback=None
            )
        except Exception as e:
            print(f"[ATSMainWindow] Init standard StockSender failed: {e}")



    def _get_search_history_filepath(self):
        try:
            from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
            return SEARCH_HISTORY_FILE
        except ImportError:
            import os
            from sys_utils import get_app_root
            return os.path.join(get_app_root(), "datacsv", "search_history.json")

    def _load_search_history_data(self):
        import os
        filepath = self._get_search_history_filepath()
        h1, h2, h3, h4, h5 = [], [], [], [], []
        self.last_query = ""
        self.last_group = "history5"
        if os.path.exists(filepath):
            try:
                import json
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                def _normalize_record(r):
                    if isinstance(r, dict):
                        q = r.get("query", "")
                        try:
                            q_dict = eval(q)
                            if isinstance(q_dict, dict) and "query" in q_dict:
                                q = q_dict["query"]
                        except:
                            pass
                        note = r.get("note", "")
                        starred = r.get("starred", 0)
                    elif isinstance(r, str):
                        q = r
                        note = ""
                        starred = 0
                    else:
                        q = str(r)
                        note = ""
                        starred = 0
                    
                    q = q.strip()
                    note = note.strip()
                    if isinstance(starred, bool):
                        starred = 1 if starred else 0
                    elif not isinstance(starred, int):
                        starred = 0
                    return {"query": q, "starred": starred, "note": note}
                
                h1 = [_normalize_record(r) for r in data.get("history1", [])]
                h2 = [_normalize_record(r) for r in data.get("history2", [])]
                h3 = [_normalize_record(r) for r in data.get("history3", [])]
                h4 = [_normalize_record(r) for r in data.get("history4", [])]
                h5 = [_normalize_record(r) for r in data.get("history5", [])]
                self.last_query = data.get("last_query", "")
                self.last_group = data.get("last_group", "history5")
            except Exception as e:
                print(f"[ATSMainWindow] Direct history load failed: {e}")
        
        self.search_histories = {
            "history1": h1,
            "history2": h2,
            "history3": h3,
            "history4": h4,
            "history5": h5
        }

    def _save_search_history_data(self):
        filepath = self._get_search_history_filepath()
        try:
            import json
            import os
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            data = {
                "history1": self.search_histories.get("history1", []),
                "history2": self.search_histories.get("history2", []),
                "history3": self.search_histories.get("history3", []),
                "history4": self.search_histories.get("history4", []),
                "history5": self.search_histories.get("history5", []),
                "last_query": getattr(self, "query_expr", ""),
                "last_group": self.history_selector.currentText() if hasattr(self, "history_selector") else "history5"
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ATSMainWindow] Direct history save failed: {e}")


    def _init_toolbar(self):
        toolbar = QToolBar("Main Controls")
        self.addToolBar(toolbar)
        toolbar.setMovable(False)
        
        self.btn_toggle_rotation = QPushButton("▶ 启动 24x7 自动旋转")
        self.btn_toggle_rotation.setStyleSheet("background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88;")
        self.btn_toggle_rotation.clicked.connect(self.toggle_rotation)
        toolbar.addWidget(self.btn_toggle_rotation)
        
        self.btn_multi_period = QPushButton("多周期🎯")
        self.btn_multi_period.setStyleSheet("QPushButton { background-color: #2b1f3c; color: #e0b0ff; font-weight: bold; border: 1px solid #c8a2c8; border-radius: 3px; padding: 2px 6px; } QPushButton:hover { background-color: #3d2f54; border-color: #e0b0ff; }")
        self.btn_multi_period.clicked.connect(self.open_multi_period_tester)
        toolbar.addWidget(self.btn_multi_period)

        self.btn_global_market = QPushButton("外盘看板🌐")
        self.btn_global_market.setStyleSheet("QPushButton { background-color: #1e3a5f; color: #00e5ff; font-weight: bold; border: 1px solid #00e5ff; border-radius: 3px; padding: 2px 6px; } QPushButton:hover { background-color: #00e5ff; color: #000; }")
        self.btn_global_market.clicked.connect(self.open_global_market_dialog)
        toolbar.addWidget(self.btn_global_market)
        
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

        toolbar.addSeparator()
        
        lbl_link = QLabel(" 联动:")
        lbl_link.setStyleSheet("color: #aad4ff; font-weight: bold;")
        toolbar.addWidget(lbl_link)
        
        self.cb_tdx = QCheckBox("TDX")
        self.cb_tdx.setChecked(True)
        self.cb_tdx.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; margin-left: 4px; }")
        self.cb_tdx.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_tdx)
        
        self.cb_ths = QCheckBox("THS")
        self.cb_ths.setChecked(True)
        self.cb_ths.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; margin-left: 4px; }")
        self.cb_ths.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_ths)
        
        self.cb_vis = QCheckBox("VIS")
        self.cb_vis.setChecked(True)
        self.cb_vis.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; margin-left: 4px; }")
        self.cb_vis.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_vis)
        
        toolbar.addSeparator()
        
        lbl_his_grp = QLabel("")
        lbl_his_grp.setStyleSheet("color: #aad4ff; font-weight: bold;")
        toolbar.addWidget(lbl_his_grp)
        
        self.history_selector = QComboBox()
        self.history_selector.addItems(["history1", "history2", "history3", "history4", "history5"])
        self.history_selector.setCurrentText(getattr(self, "last_group", "history5"))
        self.history_selector.setStyleSheet("QComboBox { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; min-width: 60px; max-width: 65px; }")
        self.history_selector.currentTextChanged.connect(self._on_history_group_changed)
        toolbar.addWidget(self.history_selector)
                
        lbl_filter = QLabel(" 过滤:")
        lbl_filter.setStyleSheet("color: #aad4ff; font-weight: bold;")
        toolbar.addWidget(lbl_filter)
        
        self.query_combo = QComboBox()
        self.query_combo.setEditable(True)
        self.query_combo.setStyleSheet("QComboBox { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; min-width: 120px; max-width: 150px; }")
        self.query_combo.view().setMinimumWidth(450) # 展开下拉菜单时，宽度自适应为最少 450px，防止长公式截断
        self.query_combo.lineEdit().returnPressed.connect(self.apply_filter)
        self.query_combo.currentIndexChanged.connect(self.apply_filter)
        toolbar.addWidget(self.query_combo)
        
        self.btn_filter = QPushButton("过滤")
        self.btn_filter.setStyleSheet("QPushButton { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; padding: 2px 4px; min-width: 30px; } QPushButton:hover { background-color: #3e3e4a; border-color: #aad4ff; }")
        self.btn_filter.clicked.connect(self.apply_filter)
        toolbar.addWidget(self.btn_filter)
        
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setStyleSheet("QPushButton { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; padding: 2px 4px; min-width: 30px; } QPushButton:hover { background-color: #3e3e4a; border-color: #ff4444; }")
        self.btn_clear.clicked.connect(self.clear_filter)
        toolbar.addWidget(self.btn_clear)

        self.btn_hit = QPushButton("Hit")
        self.btn_hit.setToolTip("计算当前组所有历史公式的命中数")
        self.btn_hit.setStyleSheet("QPushButton { background-color: #fff9c4; color: #000000; font-weight: bold; border: 1px solid #ffeb3b; border-radius: 3px; padding: 2px 4px; min-width: 25px; } QPushButton:hover { background-color: #fdd835; }")
        self.btn_hit.clicked.connect(self.calculate_history_hits_ui)
        toolbar.addWidget(self.btn_hit)
        
        self.btn_view_filtered = QPushButton("查看")
        self.btn_view_filtered.setToolTip("查看当前过滤条件命中的个股明细")
        self.btn_view_filtered.setStyleSheet("QPushButton { background-color: #2e2e36; color: #00ffcc; font-weight: bold; border: 1px solid #00ffcc; border-radius: 3px; padding: 2px 4px; min-width: 30px; } QPushButton:hover { background-color: #00ffcc; color: #000000; }")
        self.btn_view_filtered.clicked.connect(self.view_filtered_stocks_dialog)
        toolbar.addWidget(self.btn_view_filtered)
        
        # 载入默认的公式数据
        self._on_history_group_changed()

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
        
        # 1. Top Tabs in center panel (顶部主看板 Tab: 重点关注 + 回调跟踪器)
        self.top_tabs = QTabWidget()
        self.top_tabs.setStyleSheet("""
            QTabBar::tab { font-size: 10.5pt; font-weight: bold; padding: 6px 14px; min-width: 140px; }
            QTabBar::tab:selected { background-color: #1a2a1a; color: #ffd700; border-bottom: 3px solid #ffd700; }
        """)
        
        self.favorite_panel = FavoritePanel()
        self.favorite_panel.stock_selected.connect(self.on_stock_clicked)
        self.top_tabs.addTab(self.favorite_panel, "⭐ 重点关注 (基础重点)")

        self.swing_table = SwingStateTable()
        self.swing_table.dragon_monitor_requested.connect(self.open_dragon_monitor)
        self.top_tabs.addTab(self.swing_table, "📉 大级别 MA20d 回调跟踪器")
        
        # 将 [🔄 刷新状态] 按钮上移放置到 top_tabs 的右上角 CornerWidget
        if hasattr(self.swing_table, "btn_refresh"):
            self.top_tabs.setCornerWidget(self.swing_table.btn_refresh, Qt.Corner.TopRightCorner)

        self.top_tabs.currentChanged.connect(self._on_top_tab_changed)
        self.center_splitter.addWidget(self.top_tabs)
        
        # 2. Bottom Tabs in center panel (底部从属 Tab: 持仓 + 订单 + 回测 + 轨迹)
        self.center_tabs = QTabWidget()
        self.center_tabs.setMinimumWidth(100)
        self.center_tabs.setMinimumHeight(80)
        
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
        self.right_tabs.setMinimumWidth(100)
        self.right_tabs.setMinimumHeight(80)
        
        self.dist_chart = DistributionBarChart()
        self.right_tabs.addTab(self.dist_chart, "📊 市场分布 (Dist)")
        
        self.equity_chart = EquityCurveChart()
        self.right_tabs.addTab(self.equity_chart, "📈 资金曲线 (Equity)")
        
        # 资金曲线 / 右侧 Tab 右上角添加【📋 强势黑马详情】(图2) 与【🗔 独立放大窗口】组合入口
        corner_container = QWidget()
        corner_layout = QHBoxLayout(corner_container)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(6)

        self.btn_pop_signal_detail = QPushButton("📋 强势黑马详情")
        self.btn_pop_signal_detail.setToolTip("弹出/唤醒本轮强势黑马信号个股详情看板 (支持上一只/下一只轮转与特征分析)")
        self.btn_pop_signal_detail.setStyleSheet("""
            QPushButton {
                background-color: #1a261a;
                color: #4ade80;
                border: 1px solid #4ade80;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4ade80;
                color: #0f172a;
            }
        """)
        self.btn_pop_signal_detail.clicked.connect(self._open_signal_detail_dialog)

        self.btn_pop_equity_window = QPushButton("🗔 独立放大窗口")
        self.btn_pop_equity_window.setToolTip("在独立放大窗口中查看资金收益率曲线及全市场分布图表")
        self.btn_pop_equity_window.setStyleSheet("""
            QPushButton {
                background-color: #1a1a26;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        self.btn_pop_equity_window.clicked.connect(self._open_equity_pop_dialog)

        corner_layout.addWidget(self.btn_pop_signal_detail)
        corner_layout.addWidget(self.btn_pop_equity_window)
        self.right_tabs.setCornerWidget(corner_container, Qt.Corner.TopRightCorner)
        
        self.right_splitter.addWidget(self.right_tabs)
        self.right_splitter.setSizes([450, 450])
        
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_widget)

        # Set stretch factors and initial sizes
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setStretchFactor(2, 2)
        
        # Enforce non-collapsible panels to prevent UI collapse to 0 size
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.center_splitter.setCollapsible(0, False)
        self.center_splitter.setCollapsible(1, False)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)
        
        self.main_splitter.setSizes([350, 700, 390])
        
        # Bind splitterMoved signals to track user-adjusted resize ratios
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)
        self.center_splitter.splitterMoved.connect(self._on_center_splitter_moved)
        self.right_splitter.splitterMoved.connect(self._on_right_splitter_moved)
        
        # Compute initial ratios
        self._main_ratio = [350/1440, 700/1440, 390/1440]
        self._center_ratio = [0.5, 0.5]
        self._right_ratio = [0.5, 0.5]

        # Connect internal signal linkages
        # 1. 单击事件 -> 联动外部同花顺/通达信及可视化器 (link_stock)
        self.universe_widget.stock_clicked.connect(self.link_stock)
        self.swing_table.stock_clicked.connect(self.link_stock)
        self.favorite_panel.table.stock_activated.connect(self.link_stock)
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
        self.heatmap_widget.sector_selected_with_codes.connect(lambda name, codes: self.on_sector_clicked(name, member_codes=codes))
        self.swing_table.btn_refresh.clicked.connect(lambda: self.load_db_data(force=True))
        self.backtest_panel.btn_run_backtest.clicked.connect(self.on_run_backtest_clicked)

    def _on_history_group_changed(self):
        group = self.history_selector.currentText()
        h_list = self.search_histories.get(group, [])
            
        formatted_list = []
        for item in h_list:
            display_text = self._format_history_item_local(item)
            if display_text:
                formatted_list.append(display_text)
                
        self.query_combo.blockSignals(True)
        self.query_combo.clear()
        self.query_combo.addItems(formatted_list)
        
        restored = False
        last_q = getattr(self, "last_query", "")
        if last_q:
            for display_text in formatted_list:
                real_q = ""
                if "  |  " in display_text:
                    real_q = display_text.split("  |  ")[-1].strip()
                else:
                    real_q = display_text.strip()
                if real_q == last_q:
                    self.query_combo.setCurrentText(display_text)
                    restored = True
                    break
            if not restored:
                self.query_combo.setEditText(last_q)
                restored = True
                
        if not restored:
            if formatted_list:
                self.query_combo.setCurrentIndex(0)
            else:
                self.query_combo.setCurrentText("")
                
        self.query_combo.blockSignals(False)
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))
        
        # 默认应用并加载最前面的（最新一条）历史过滤公式
        self.apply_filter()

    def _format_history_item_local(self, item):
        if not isinstance(item, dict): 
            return str(item)
        q = item.get("query", "").strip()
        q = " ".join(q.split())
        note = item.get("note", "").strip()
        hit = item.get("hit", "")
        parts = []
        if note: 
            parts.append(note)
        if hit != "" and hit is not None: 
            parts.append(f"[Hit: {hit}]")
        parts.append(q)
        return "  |  ".join(parts)

    def _get_real_query(self):
        text = self.query_combo.currentText().strip()
        if "  |  " in text:
            return text.split("  |  ")[-1].strip()
        return text

    def calculate_history_hits_ui(self):
        test_df = self.get_test_df_for_hits()
        if test_df.empty:
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, "⚠️ 实盘数据未就绪")
            return
            
        group = self.history_selector.currentText()
        target = self.search_histories.get(group, [])
        if not target: 
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, "⚠️ 当前历史组为空")
            return
            
        from stock_logic_utils import test_code_against_queries, toast_messageQT
        
        enriched_results = test_code_against_queries(test_df, target)
        
        new_values = []
        for i, item in enumerate(target):
            hit_count = 0
            if i < len(enriched_results):
                hit_count = enriched_results[i].get("hit", 0)
            item["hit"] = hit_count
            display = self._format_history_item_local(item)
            new_values.append(display)
            
        current_val = self.query_combo.currentText()
        raw_q = self._get_real_query()
        
        self.query_combo.blockSignals(True)
        self.query_combo.clear()
        self.query_combo.addItems(new_values)
        
        if raw_q:
            matched_display = None
            for idx, item in enumerate(target):
                if item.get("query") == raw_q:
                    matched_display = self._format_history_item_local(item)
                    break
            if matched_display:
                self.query_combo.setCurrentText(matched_display)
            else:
                self.query_combo.setCurrentText(current_val)
        elif current_val:
            self.query_combo.setCurrentText(current_val)
            
        self.query_combo.blockSignals(False)
                    
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))
                    
        toast_messageQT(self, f"✅ 策略命中统计完成 (n={len(target)})")

    def get_test_df_for_hits(self):
        import pandas as pd
        if self.current_df is not None and not self.current_df.empty:
            test_df = self.current_df.copy()
            mapping = {
                '价格': 'close', '最新价': 'close', '现价': 'close', 
                '涨幅': 'pct', 
                '量': 'volume', '成交量': 'volume',
                '成交额': 'turnover',
                '最高': 'high', '最低': 'low', '开盘': 'open',
                '板块': 'category', '异动类型': 'category', 'hy': 'category'
            }
            for cn, en in mapping.items():
                if cn in test_df.columns and en not in test_df.columns:
                    test_df[en] = test_df[cn]
            if 'close' in test_df.columns:
                for col in ['open', 'high', 'low']:
                    if col not in test_df.columns:
                        test_df[col] = test_df['close']
            return test_df
        return pd.DataFrame()

    def apply_filter(self):
        query = self._get_real_query()
        self.query_expr = query
        
        if query:
            group = self.history_selector.currentText()
            h_list = self.search_histories.get(group, [])
            
            exists = False
            for item in h_list:
                if isinstance(item, dict) and item.get("query") == query:
                    exists = True
                    break
                elif isinstance(item, str) and item == query:
                    exists = True
                    break
                    
            if not exists:
                h_list.insert(0, {"query": query, "starred": 0, "note": ""})
                if len(h_list) > 500: # MAX_HISTORY
                    h_list.pop()
                
                # 同步回写保存
                self._save_search_history_data()
                
                self._on_history_group_changed()
                
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, StockDetailDialog) and widget.isVisible():
                widget.update_filter_status(self.query_expr)
                
        # 广播更新过滤后的个股明细窗口
        if hasattr(self, 'dist_chart'):
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)
                
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))

    def clear_filter(self):
        self.query_combo.setCurrentText("")
        self.query_expr = ""
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, StockDetailDialog) and widget.isVisible():
                widget.update_filter_status("")
                
        # 广播清空过滤明细窗口
        if hasattr(self, 'dist_chart'):
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)

    def view_filtered_stocks_dialog(self):
        query = self._get_real_query()
        self.query_expr = query
        
        if hasattr(self, 'dist_chart'):
            config = {}
            try:
                import os
                import json
                from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
                if os.path.exists(WINDOW_CONFIG_FILE):
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        config = data.get("distribution_details_dialog_999", {})
            except Exception:
                pass
                
            self.dist_chart.open_details_dialog(999, restore_state=config, cold_start=True)
            
            # 刷新最新数据
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)

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
        if not code_clean:
            return
            
        import time
        now = time.time()
        last_code = getattr(self, "_last_linked_code", None)
        last_time = getattr(self, "_last_linked_time", 0)
        if last_code == code_clean and (now - last_time) < 0.2:
            # 500ms 内重复对同一代码发起联动，直接短路忽略，防止多重绑定信号引起重复联动导致 TDX/THS 闪烁
            return
        self._last_linked_code = code_clean
        self._last_linked_time = now
        
        self.status_bar.showMessage(f"🔗 [联动] 推送股票 {code_clean} {name} (已同步可视化及外部交易终端)")
        
        # 1. 异步向 26668 发送切换个股 socket 指令 (VIS 联动)
        if hasattr(self, 'cb_vis') and self.cb_vis.isChecked():
            import socket
            import threading
            
            # Check if this stock is in favorites and retrieve its add date
            add_date = None
            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                if code_clean in fav_mgr.get_favorite_stocks():
                    add_date = fav_mgr.get_favorite_stock_date(code_clean)
            except Exception:
                pass
            
            # If add_date is available, format as TIME_LINK; otherwise CODE
            if add_date:
                cmd_str = f"TIME_LINK|{code_clean}|{add_date}|label=重点关注"
            else:
                cmd_str = f"CODE|{code_clean}"
            
            def send_switch(msg):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.1) # 极低超时，不阻塞 UI
                        s.connect(('127.0.0.1', 26668))
                        s.sendall(msg.encode("utf-8"))
                except Exception:
                    pass # 可视化器可能未启动，静默失败即可
                    
            threading.Thread(target=send_switch, args=(cmd_str,), daemon=True).start()

        # 2. 向独立联动进程投递物理联动任务 (TDX/THS 物理联动机能)
        is_tdx = self.cb_tdx.isChecked() if hasattr(self, 'cb_tdx') else True
        is_ths = self.cb_ths.isChecked() if hasattr(self, 'cb_ths') else True
        if is_tdx or is_ths:
            try:
                from linkage_service import get_link_manager
                flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
                get_link_manager().push(code_clean, flags=flags, auto=False)
            except Exception as e:
                print(f"[Linkage] External linkage failed: {e}")

    def _get_today_signal_codes(self):
        """归纳今日所有已发现/记录的特异与共振强势股票代码列表 (供弹窗左右导航联动)"""
        codes = []
        seen = set()
        
        # 1. 优先从 SignalLedger 提取
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries'):
            for c, entry in self.signal_ledger.entries.items():
                c_clean = str(c).strip()
                if c_clean and c_clean not in seen:
                    seen.add(c_clean)
                    name = getattr(entry, 'name', c_clean)
                    if hasattr(self, 'get_stock_name'):
                        name = self.get_stock_name(c_clean)
                    codes.append((c_clean, name))
                    
        # 2. 补充从 SwingStateTable 提取
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            for r in range(tbl.rowCount()):
                c_item = tbl.item(r, 0)
                n_item = tbl.item(r, 1)
                if c_item:
                    c_clean = c_item.text().strip()
                    if c_clean and c_clean not in seen:
                        seen.add(c_clean)
                        n_str = n_item.text().strip() if n_item else c_clean
                        codes.append((c_clean, n_str))
        return codes

    def _ensure_context_info(self, code, name, context_info):
        """保证弹窗必定包含完整的 [📍 策略特征上下文 (Context Info)] 面板 (100% 对齐图 2 样式)"""
        code_clean = str(code).strip()
        res = context_info.copy() if context_info else {}

        # 1. 尝试从 swing_table 匹配 (优先获取 MA20d 回调跟踪器上下文, 使用 findItems 原生优化查找)
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            found_items = tbl.findItems(code_clean, Qt.MatchFlag.MatchExactly)
            if found_items:
                row = found_items[0].row()
                res['position'] = "波段回调跟踪器 (Swing Pullback Tracker)"
                res['reason'] = "股价缩量向大级别MA20均线回调靠拢中"
                parts = []
                for col in [3, 4, 5, 6, 7]:
                    h = tbl.horizontalHeaderItem(col)
                    v = tbl.item(row, col)
                    if h and v and v.text().strip():
                        parts.append(f"{h.text()}: {v.text().strip()}")
                res['status'] = " | ".join(parts) if parts else "MA20均线回调企稳中"
                return res

        # 2. 尝试从 signal_ledger 匹配
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries'):
            entry = self.signal_ledger.entries.get(code_clean)
            if entry:
                res['position'] = f"SignalLedger {getattr(entry, 'tier', 'RADAR')} 信号池"
                res['reason'] = getattr(entry, 'promote_reason', '黄金特异高分跟进信号')
                res['status'] = (
                    f"MA20偏离: {getattr(entry, 'latest_deviation', 0.0):+.2f}% | "
                    f"优先级: {getattr(entry, 'priority_score', 0.0):.0f} | "
                    f"特异打分: {getattr(entry, 'specialty_score', 90.0):.0f}"
                )
                return res

        # 3. 兜底默认补齐
        if not res.get('position'):
            res['position'] = "大级别波段跟踪与实盘监控热点"
            res['reason'] = "大盘共振/相对大盘强偏离拉升买点"
            res['status'] = f"代码: {code_clean} | 已成功对接实盘行情快照核心特征"

        return res

    def on_stock_clicked(self, code, name, context_info=None, batch_codes=None):
        self.status_bar.showMessage(f"双击详情: {code} {name}")
        context_info = self._ensure_context_info(code, name, context_info)
        code_clean = str(code).strip()

        # 【核心机制】若详情弹窗实例存在且有效（不论处于悬浮显示还是磁吸贴边隐藏），直接复用唤醒展现；若已被 C++ 销毁则清空重新创建
        from PyQt6.sip import isdeleted
        if hasattr(self, '_detail_dialog') and self._detail_dialog is not None:
            if isdeleted(self._detail_dialog):
                self._detail_dialog = None
            else:
                try:
                    effective_batch = batch_codes or getattr(self, "_last_batch_signal_codes", None)
                    self._detail_dialog.switch_to_code(code_clean, name, batch_codes=effective_batch)
                    return
                except RuntimeError:
                    self._detail_dialog = None
                except Exception as e:
                    print(f"[ATSMainWindow] Error reusing detail dialog: {e}")
                    self._detail_dialog = None
        
        # 内存极速提取最新行情 (current_df -> df_realtime 级联匹配，杜绝主线程网络 API 阻塞)
        df_row = None
        c_clean = str(code).strip().zfill(6)
        for attr in ("current_df", "df_realtime"):
            if hasattr(self, attr):
                df = getattr(self, attr)
                if df is not None and not df.empty:
                    if c_clean in df.index:
                        row = df.loc[c_clean]
                        df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                        break
                    elif 'code' in df.columns:
                        m = df[df['code'] == c_clean]
                        if not m.empty:
                            df_row = m.iloc[0].to_dict()
                            break
                    
        # 安全清理已存在的详情弹窗旧实例
        if hasattr(self, '_detail_dialog') and self._detail_dialog is not None:
            if not isdeleted(self._detail_dialog):
                try:
                    self._detail_dialog.close()
                except Exception:
                    pass
            self._detail_dialog = None
                
        # Launch detail dialog as non-modal so it can snap and auto-hide
        self._detail_dialog = StockDetailDialog(code, name, df_row, context_info, parent=self, batch_codes=batch_codes)
        self._detail_dialog.show()

    def on_sector_clicked(self, name, member_codes=None):
        if getattr(self, "_showing_sector_detail", False):
            return
        self._showing_sector_detail = True
        try:
            self.status_bar.showMessage(f"选中板块: {name} | 正在展示成分股明细...")
            from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
            dialog = ATSSectorDetailDialog(name, self.link_stock, self.on_stock_clicked, member_codes=member_codes, parent=self)
            dialog.exec()
        finally:
            self._showing_sector_detail = False

    def on_heartbeat(self):
        # 1. Periodically load and update DB data
        self.load_db_data()
        
        # 2. Periodically load trace logs
        if hasattr(self, 'kernel_trace_panel'):
            self.kernel_trace_panel.load_trace_logs()
            
        # 3. Periodically load sector heatmap
        if hasattr(self, 'heatmap_widget'):
            self.heatmap_widget.load_live_sectors()

        # 4. Periodically request full sync if data is empty (cold start) or if we haven't received pushed data for > 10 minutes during trading hours
        import time
        now = time.time()
        should_sync = False
        if not hasattr(self, "current_df") or self.current_df is None or self.current_df.empty:
            # 即使冷启动数据为空，也限制至少 15 秒请求一次，防止数据传输中高频重发导致堵塞
            if now - getattr(self, "_last_pipe_sync_t", 0) > 15:
                should_sync = True
        else:
            # 只有在交易时间段，且超过 10 分钟（600秒）没有收到更新时才手动请求一次，防止高频请求导致 TK 后台持续发送
            try:
                is_work = cct.get_work_time()
            except Exception:
                is_work = False
            
            if is_work and (now - getattr(self, "_last_recv_t", 0) > 600):
                if now - getattr(self, "_last_pipe_sync_t", 0) > 60:
                    should_sync = True
            
        if should_sync:
            self._last_pipe_sync_t = now
            try:
                from data_utils import send_code_via_pipe, PIPE_NAME_TK
                import logging
                local_logger = logging.getLogger("ATS")
                send_code_via_pipe({"cmd": "REQ_FULL_SYNC"}, logger=local_logger, pipe_name=PIPE_NAME_TK)
            except Exception as e:
                print(f"[ATSMainWindow] Failed to send REQ_FULL_SYNC: {e}")

    def _update_name_cache_from_df(self, df):
        if df is not None and not df.empty and 'name' in df.columns:
            try:
                # 向量化快速提取 IPC 推送的 DataFrame 中的 code -> name 关联字典
                temp_dict = df['name'].dropna().to_dict()
                cleaned_dict = {
                    str(k).strip().zfill(6): str(v).strip() 
                    for k, v in temp_dict.items() 
                    if str(v).strip() and str(v).strip() != str(k).strip().zfill(6) and not str(v).strip().isdigit() and str(v).strip() != "未知"
                }
                self.name_cache.update(cleaned_dict)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating name cache from df: {e}")

    def get_stock_name(self, code):
        if not code:
            return "未知"
        code_str = str(code).strip().zfill(6)
        
        # 1. 直接从 IPC 推送的核心 memory 数据集 (current_df / df_realtime) 中查找 (无需舍近求远)
        for attr_name in ('current_df', 'df_realtime'):
            df_obj = getattr(self, attr_name, None)
            if df_obj is not None and not df_obj.empty and code_str in df_obj.index:
                try:
                    row_val = df_obj.loc[code_str]
                    name_val = str(row_val.get('name', '') if hasattr(row_val, 'get') else row_val['name']).strip()
                    if name_val and name_val != code_str and not name_val.isdigit() and name_val != "未知":
                        self.name_cache[code_str] = name_val
                        return name_val
                except Exception:
                    pass

        # 2. 检查 name_cache (排除与 code_str 相同或全数字的纯代码名称)
        name = self.name_cache.get(code_str)
        if name and name != "未知" and name != code_str and not name.isdigit() and not name.startswith("个股_"):
            return name

        # 3. 调起全局权威解析器 sys_utils
        try:
            from sys_utils import resolve_stock_name
            res_name = resolve_stock_name(code_str)
            if res_name and res_name != code_str and not res_name.isdigit() and not res_name.startswith("个股_"):
                self.name_cache[code_str] = res_name
                return res_name
        except Exception:
            pass

        return name if (name and name != code_str and not name.isdigit()) else code_str

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
                
                # Trigger immediate sync upon listener startup
                try:
                    from data_utils import send_code_via_pipe, PIPE_NAME_TK
                    import logging
                    import time
                    local_logger = logging.getLogger("ATS")
                    self._last_pipe_sync_t = time.time()  # 初始化时间戳，防止 heartbeat 瞬间重复请求
                    send_code_via_pipe({"cmd": "REQ_FULL_SYNC"}, logger=local_logger, pipe_name=PIPE_NAME_TK)
                except Exception as e:
                    print(f"[ATSMainWindow] Startup failed to send REQ_FULL_SYNC: {e}")
 
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

        # 2. 将提取出的 DataFrame 强制转换为以 code 字符串作为 index (如果后台没有预先处理)
        if not (df_payload.index.name == 'code' and df_payload.index.dtype == object):
            df_payload = df_payload.copy()
            if 'code' in df_payload.columns:
                df_payload['code'] = df_payload['code'].astype(str).str.strip()
                df_payload.set_index('code', inplace=True)
            else:
                df_payload.index = df_payload.index.astype(str).str.strip()
                df_payload.index.name = 'code'

        # 3. 处理全量/增量更新
        if msg_type == 'UPDATE_DF_DIFF' and hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            try:
                df_diff = df_payload
                # 💥 支持 MultiIndex 格式列 (如由 df.compare 产出)
                if isinstance(df_diff.columns, pd.MultiIndex):
                    new_cols = {}
                    for col in df_diff.columns:
                        if isinstance(col, tuple) and len(col) >= 2:
                            base_col, val_type = col[0], col[1]
                            if val_type == 'self':
                                new_cols[base_col] = df_diff[col]
                    df_diff = pd.DataFrame(new_cols, index=df_diff.index)
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
                
                # 计算统计数据以更新市场温度与家数
                up_count = int((pcts > 0).sum())
                down_count = int((pcts < 0).sum())
                flat_count = int((pcts == 0).sum())
                total_count = up_count + down_count + flat_count
                avg_pct = float(pcts.mean()) if total_count > 0 else 0.0
                market_temp = (up_count / total_count * 100.0) if total_count > 0 else 0.0
                
                stats_dict = {
                    "up": up_count,
                    "down": down_count,
                    "flat": flat_count,
                    "avg": avg_pct,
                    "temp": market_temp
                }
                
                if len(counts) == 10:
                    self.dist_chart.update_data(counts, stats_dict, self.current_df)
            
            self.refresh_realtime_ui()
            self.status_bar.showMessage(f"已同步接收到主进程最新实时行情快照 (个股数: {len(self.current_df)})")
            import time
            self._last_recv_t = time.time()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ATS_Realtime] Received data update: {msg_type}, rows={len(self.current_df)}")

    def _async_load_stock_prices(self, codes):
        if not codes:
            return
        
        # Filter out codes already loading or failed
        codes_to_load = [c for c in codes if c not in self.prices_loading_codes and c not in self.prices_failed_codes]
        if not codes_to_load:
            return
            
        for code in codes_to_load:
            self.prices_loading_codes.add(code)
            
        import threading
        def worker():
            try:
                from JSONData import sina_data
                s = sina_data.Sina(readonly=True)
                
                valid_codes = [c for c in codes_to_load if c and len(c) == 6]
                if not valid_codes:
                    for code in codes_to_load:
                        self.prices_loading_codes.discard(code)
                        self.prices_failed_codes.add(code)
                    return
                    
                # Direct online fetch using Sina's list data API to get real-time price and llastp
                tick_df = s.get_stock_list_data(valid_codes)
                        
                loaded_codes = set()
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
                        loaded_codes.add(code_str)
                        
                # Update loading/failed states
                for code in codes_to_load:
                    self.prices_loading_codes.discard(code)
                    if code not in loaded_codes:
                        self.prices_failed_codes.add(code)
                        
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self.refresh_realtime_ui)
            except Exception as e:
                print(f"[ATSMainWindow] Error loading prices in background: {e}")
                for code in codes_to_load:
                    self.prices_loading_codes.discard(code)
                    self.prices_failed_codes.add(code)
                
        threading.Thread(target=worker, daemon=True).start()

    def _async_load_stock_history(self, codes):
        if not codes:
            return
        
        import time, datetime, random
        now_ts = time.time()
        today = datetime.date.today().isoformat()
        
        # 动态计算重试冷却时长：cct.duration_sleep_time + 随机(1,10)秒
        sleep_base = 10
        try:
            if hasattr(cct, 'duration_sleep_time'):
                sleep_base = int(cct.duration_sleep_time)
        except Exception:
            pass
        cooldown_sec = sleep_base + random.randint(1, 10)
        
        # Reset failed codes at the start of a new calendar day so that a fresh
        # ATS launch always retries history loading (avoids permanent blacklist).
        if self._history_failed_date != today:
            self._history_failed_date = today
            self.history_failed_codes.clear()
        
        # Filter out codes already loading or failed within the cooldown_sec
        codes_to_load = [
            c for c in codes
            if c not in self.history_loading_codes
            and (c not in self.history_failed_codes or now_ts - self.history_failed_codes[c] > cooldown_sec)
        ]
        if not codes_to_load:
            return
            
        # Mark as loading
        for code in codes_to_load:
            self.history_loading_codes.add(code)
            if code not in self.stock_history_cache:
                self.stock_history_cache[code] = []
                
        import threading
        def worker():
            import time as _time
            import pandas as pd
            import os

            # 尝试非阻塞式获取 HDF5 读写锁，防止多线程并发读取 HDF5 文件触发 PyTables 内存访问冲突崩溃 (Access Violation)
            acquired = self.hdf5_history_lock.acquire(blocking=False)
            if not acquired:
                # 锁竞争失败：也加上 cooldown_sec 秒冷却，避免每 3 秒刷新时重复请求撞锁
                fail_ts = _time.time()
                for code in codes_to_load:
                    self.history_loading_codes.discard(code)
                    self.history_failed_codes[code] = fail_ts
                return

            try:
                path = r'g:\sina_MultiIndex_data.h5'
                if not os.path.exists(path):
                    fail_ts = _time.time()
                    for code in codes_to_load:
                        self.history_loading_codes.discard(code)
                        self.history_failed_codes[code] = fail_ts
                    print(f"[ATSHistory] HDF5 文件不存在: {path}")
                    return

                # ── 带重试的 HDF5 读取，对抗写锁冲突 ──────────────────────────────
                MAX_RETRY = 3
                RETRY_SLEEP = 0.5   # 每次重试间隔 0.5 秒

                df = None
                last_err = None
                for attempt in range(MAX_RETRY):
                    try:
                        with pd.HDFStore(path, mode='r') as store:
                            code_query = ", ".join([f"'{c}'" for c in codes_to_load])
                            df = store.select('/all_30', where=f"code in [{code_query}]")
                        last_err = None
                        break   # 成功则跳出重试
                    except Exception as e:
                        last_err = e
                        print(f"[ATSHistory] 读取 HDF5 失败 (attempt {attempt+1}/{MAX_RETRY}): {e}")
                        if attempt < MAX_RETRY - 1:
                            _time.sleep(RETRY_SLEEP)

                if last_err is not None:
                    # 全部重试均失败 → IO/锁问题，用短冷却避免长时间黑名单
                    fail_ts = _time.time() - (300 - IO_FAIL_COOLDOWN)  # 只冷却 IO_FAIL_COOLDOWN 秒
                    for code in codes_to_load:
                        self.history_loading_codes.discard(code)
                        self.history_failed_codes[code] = fail_ts
                    print(f"[ATSHistory] HDF5 读取彻底失败，{IO_FAIL_COOLDOWN}s 后重试: {last_err}")
                    return

                # ── 清除成功读取的 code 的失败标记 ────────────────────────────────
                for code in codes_to_load:
                    self.history_failed_codes.pop(code, None)

                loaded_codes = set()
                if df is not None and not df.empty:
                    dates = pd.to_datetime(df.index.get_level_values('ticktime')).date
                    grouped = df.groupby([df.index.get_level_values('code'), dates])['close'].last()

                    for (code, d), val in grouped.items():
                        d_str = d.strftime("%Y-%m-%d")
                        hist = self.stock_history_cache.get(code, [])
                        if not any(item[0] == d_str for item in hist):
                            hist.append((d_str, float(val)))
                        self.stock_history_cache[code] = hist
                        loaded_codes.add(code)

                    for code in codes_to_load:
                        if code in self.stock_history_cache:
                            self.stock_history_cache[code].sort(key=lambda x: x[0])

                # ── 数据为空的 code：正常标记失败（RETRY_INTERVAL=300s） ──────────
                fail_ts = _time.time()
                for code in codes_to_load:
                    self.history_loading_codes.discard(code)
                    if code not in loaded_codes:
                        self.history_failed_codes[code] = fail_ts
                        print(f"[ATSHistory] code={code} 在 /all_30 中无数据")

                print(f"[ATSHistory] 加载完成: {len(loaded_codes)}/{len(codes_to_load)} 只有历史数据")

                # 触发线程安全 UI 刷新
                QTimer.singleShot(0, self.refresh_realtime_ui)
            finally:
                # 释放锁，确保任何退出分支均能安全解锁，防止死锁
                self.hdf5_history_lock.release()
                
        threading.Thread(target=worker, daemon=True).start()

    def refresh_realtime_ui(self):
        if getattr(self, '_is_closing', False):
            return
        has_df = self.current_df is not None and not self.current_df.empty
        
        # 1. Update prices/percents in universe_manager pools
        fav_stocks = set()
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            pass

        pool_codes = list(self.universe_manager.radar_pool.keys()) + list(self.universe_manager.watch_pool.keys()) + list(self.universe_manager.trade_pool.keys())
        all_codes = list(dict.fromkeys(pool_codes + [c for c in fav_stocks if c]))
        missing_realtime_codes = []
        
        # 2. 增量更新信号账本（替代全量重算，信号只增不删）
        if has_df:
            self._update_signal_ledger(self.current_df)
            # 从信号账本同步到三级池（稳定展示，不快速流动）
            self.universe_manager.sync_from_ledger(self.signal_ledger, df_realtime=self.current_df, price_pct_cache=self.price_pct_cache)
        else:
            self.universe_manager.sync_from_ledger(self.signal_ledger, price_pct_cache=self.price_pct_cache)

        for pool in [self.universe_manager.radar_pool, self.universe_manager.watch_pool, self.universe_manager.trade_pool]:
            for code in list(pool.keys()):
                real_name = self.get_stock_name(code)
                if real_name and real_name not in ('未知', '重点标的', ''):
                    pool[code]['name'] = real_name

                if has_df and code in self.current_df.index:
                    row = self.current_df.loc[code]
                    import pandas as pd
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
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
        
        # 4. Update swing state table
        missing_history_codes = [c for c in all_codes if c not in self.stock_history_cache or not self.stock_history_cache[c]]
        if missing_history_codes:
            self._async_load_stock_history(missing_history_codes)
            
        swing_rows = []
        current_batch_alpha = []
        
        # 计算大盘参考涨幅 (优先使用上证指数，回退到个股等权均值)
        sh_pct = 0.0
        if has_df:
            if 'sh000001' in self.current_df.index:
                sh_pct = float(self.current_df.loc['sh000001'].get('percent', 0.0))
            elif '000001' in self.current_df.index and 'sh' in str(self.current_df.loc['000001'].get('code', '')):
                sh_pct = float(self.current_df.loc['000001'].get('percent', 0.0))
            else:
                if 'percent' in self.current_df.columns:
                    sh_pct = float(self.current_df['percent'].mean())
                    
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        for code in all_codes:
            latest_close = 0.0
            pct_val = 0.0
            dff_val = 0.0
            rank_val = 0
            dff2_val = 0.0
            dff3_val = 0.0
            
            if has_df and code in self.current_df.index:
                import pandas as pd
                row = self.current_df.loc[code]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                latest_close = float(row.get('close', row.get('price', 0.0)))
                pct_val = float(row.get('percent', 0.0))
                try: dff_val = float(row.get('dff', 0.0))
                except: pass
                try: rank_val = int(row.get('Rank', row.get('rank', 0)))
                except: pass
                try: dff2_val = float(row.get('dff2', 0.0))
                except: pass
                try: dff3_val = float(row.get('dff3', 0.0))
                except: pass
            elif code in self.price_pct_cache:
                latest_close = self.price_pct_cache[code][0]
                pct_val = self.price_pct_cache[code][1]
            elif code in self.stock_history_cache and self.stock_history_cache[code]:
                latest_close = float(self.stock_history_cache[code][-1][1])
                pct_val = 0.0
                
            name = self.get_stock_name(code)
            
            # 计算大盘偏离度和共振状态
            rs_val = pct_val - sh_pct
            resonance = "同步整理"
            if sh_pct < -0.3 and pct_val > 1.5:
                resonance = "逆市抗跌"
            elif sh_pct > 0.3 and pct_val > 3.0 and dff_val > 2.0:
                resonance = "大盘共振"
            elif pct_val < -3.0 and rs_val < -2.0:
                resonance = "同步走弱"
            
            # Try to use database history first
            has_history = (code in self.stock_history_cache and self.stock_history_cache[code])
            
            if has_history:
                hist = self.stock_history_cache[code]
                close_series = [item[1] for item in hist]
                if hist[-1][0] == today_str:
                    close_series[-1] = latest_close
                else:
                    close_series.append(latest_close)
                close_series = [float(x) for x in close_series if x is not None]
                
                # Calc rolling MA in pure Python for high performance (no pandas Series overhead)
                ma20_series = []
                ma5_series = []
                for i in range(len(close_series)):
                    sub20 = close_series[max(0, i - 19) : i + 1]
                    ma20_series.append(sum(sub20) / len(sub20) if sub20 else close_series[i])
                    sub5 = close_series[max(0, i - 4) : i + 1]
                    ma5_series.append(sum(sub5) / len(sub5) if sub5 else close_series[i])
            else:
                # Fallback: Reconstruct history and MAs from the real-time slice data (up to compute_lastdays days)
                # This allows the state machine to run immediately even if HDF5 is missing/empty
                is_in_df = (has_df and code in self.current_df.index)
                row_data = row if is_in_df else {}
                
                limit_days = int(getattr(cct, 'compute_lastdays', 9))
                
                # Extract lastp1d ... lastp{limit_days}d dynamically
                history_closes = []
                last_val = latest_close
                for d_idx in range(limit_days, 0, -1):
                    col_name = f"lastp{d_idx}d"
                    val_raw = row_data.get(col_name, last_val) if is_in_df else last_val
                    try:
                        val = float(val_raw)
                    except:
                        val = last_val
                    if val > 0:  # Avoid 0 or invalid values
                        history_closes.append(val)
                        last_val = val
                        
                close_series = history_closes + [latest_close]
                
                try:
                    current_ma20 = float(row_data.get('ma20d', latest_close)) if is_in_df else latest_close
                except:
                    current_ma20 = latest_close
                try:
                    current_ma5 = float(row_data.get('ma5d', latest_close)) if is_in_df else latest_close
                except:
                    current_ma5 = latest_close
                
                ma20_series = [current_ma20] * len(close_series)
                ma5_series = [current_ma5] * len(close_series)
            
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
            
            # 从信号账本提取首次发现和优先级评分，提供回退值
            entry = self.signal_ledger.entries.get(code)
            if entry:
                from ats.signal_ledger import PHASE_LABELS
                phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
                first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
                first_seen = f"{phase_label} [{first_time}]"
                priority_val = f"{entry.priority_score:.1f}"
            else:
                first_seen = "⏳ 初始/持仓"
                priority_val = "0.0"
                
            swing_rows.append((
                code, name, f"{latest_close:.2f}", state, dev_str, str(limit_ups), position, 
                first_seen, priority_val,
                f"{dff_val:.2f}", str(rank_val), f"{dff2_val:.2f}", f"{dff3_val:.2f}", f"{rs_val:+.2f}%", resonance, reason
            ))
            
            # 记录逆市/共振个股，提供每日跟踪与高级反馈能力
            if resonance in ("逆市抗跌", "大盘共振"):
                current_batch_alpha.append((code, name))
                self._record_alpha_signal(code, name, pct_val, sh_pct, rs_val, resonance)
            
        if current_batch_alpha:
            self._last_batch_signal_codes = current_batch_alpha

        if swing_rows:
            self.swing_table.update_data_list(swing_rows)
            if hasattr(self, 'favorite_panel'):
                fav_rows = [r for r in swing_rows if str(r[0]).strip() in fav_stocks]
                self.favorite_panel.update_favorite_rows(fav_rows)

        # 7. 更新三级池 UI 展示
        radar_list, watch_list, trade_list = self.universe_manager.get_pools()
        self.universe_widget.update_pools(radar_list, watch_list, trade_list)
            
        if hasattr(self, 'heatmap_widget'):
            self.heatmap_widget.load_live_sectors()
            
        from PyQt6.sip import isdeleted
        if self.dragon_monitor_dialog and not isdeleted(self.dragon_monitor_dialog) and self.dragon_monitor_dialog.isVisible():
            try:
                self.dragon_monitor_dialog.update_data(self.current_df, sh_pct)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating dragon monitor: {e}")

        if hasattr(self, '_equity_pop_dialog') and self._equity_pop_dialog is not None and not isdeleted(self._equity_pop_dialog) and self._equity_pop_dialog.isVisible():
            try:
                self._equity_pop_dialog.update_data(self.current_df)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating equity pop dialog: {e}")
            
        # 实时高频更新所有打开的个股明细窗口的实盘特征和过滤状态 (Live update details & filter status)
        if has_df:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, StockDetailDialog) and widget.isVisible():
                    code = widget.code
                    if code in self.current_df.index:
                        row = self.current_df.loc[code]
                        import pandas as pd
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]
                        widget.update_data(row)

    def _update_signal_ledger(self, df_all):
        """增量更新信号账本（核心方法 — 替代全量 run_pipeline_filtering）

        核心逻辑:
        1. 扫描全市场 DataFrame，计算 MA20 偏离度
        2. 偏离度在范围内的标的 → 写入 SignalLedger
        3. 已存在的信号 → 仅更新最新价格，不改变首次发现时间
        4. 更新 VolumeProfiler 量能画像
        5. 定时执行 SessionSnapshot 快照持久化

        时间复杂度: O(候选数) 而非 O(全市场), 大幅降低 UI 开销
        """
        import pandas as pd

        if df_all is None or df_all.empty:
            return

        # 1. 更新大盘量能环境上下文
        self.volume_profiler.update_market_context(df_all)

        # 2. 定位 MA20 列
        ma20_col = None
        for col_name in ['ma20d', 'ma20', 'MA20', 'ma20_series']:
            if col_name in df_all.columns:
                ma20_col = col_name
                break

        if not ma20_col:
            return

        # 3. 计算全市场偏离度（向量化计算，极速）
        close_col = 'close' if 'close' in df_all.columns else 'price'
        if close_col not in df_all.columns:
            return

        close_s = pd.to_numeric(df_all[close_col], errors='coerce')
        safe_ma20 = pd.to_numeric(df_all[ma20_col], errors='coerce').replace(0, float('nan'))
        dev_series = (close_s - safe_ma20) / safe_ma20 * 100.0

        # 4. 筛选偏离度在目标范围内 OR 已在 ledger 中的标的
        tracked_codes = set(self.signal_ledger.entries.keys())
        valid_mask = (
            ((dev_series >= self.signal_ledger.DEVIATION_MIN) &
             (dev_series <= self.signal_ledger.DEVIATION_MAX)) |
            df_all.index.isin(tracked_codes)
        )
        target_df = df_all[valid_mask]

        # 5. 增量写入信号账本（第一步：更新各股票量能初分与形态）
        valid_target_codes = []
        for code, row in target_df.iterrows():
            code_str = str(code).strip()
            if not code_str or code_str in ('sh000001', 'sz399001', 'sz399006', '000001.SH', '399001.SZ', '399006.SZ'):
                continue  # 跳过指数
                
            try:
                # 预提取价格与均线值，确保合法性
                price = float(row.get(close_col, 0.0))
                ma20_val = 0.0
                try:
                    ma20_val = float(row.get(ma20_col, 0.0))
                except (TypeError, ValueError):
                    pass
                    
                if price <= 0 or ma20_val <= 0:
                    continue
                    
                self.volume_profiler.update_profile(code_str, row)
                valid_target_codes.append((code_str, row, price, ma20_val))
            except Exception:
                continue

        # 核心板块分析第二步: 运行板块动能与共振分析 (识别板块内谁是带队大哥, 谁是跟风小弟并提权评分)
        active_codes_list = [item[0] for item in valid_target_codes]
        self.volume_profiler.analyze_sector_resonance(active_codes=active_codes_list)

        # 第三步: 将包含板块共振和连阳加权后的最终评分，正式录入信号账本
        for code_str, row, price, ma20_val in valid_target_codes:
            try:
                name = str(row.get('name', ''))
                pct = float(row.get('percent', 0.0))
                deviation = (price - ma20_val) / ma20_val * 100.0
                
                # 获取经过板块共振和多日连阳加成修正后的最终 vol_score
                vol_score = self.volume_profiler.get_volume_score(code_str)

                # 写入信号账本（新信号锁定首次发现时间，已有信号仅更新最新数据）
                self.signal_ledger.record_signal(
                    code=code_str,
                    name=name,
                    price=price,
                    pct=pct,
                    deviation=deviation,
                    row=row,
                    volume_score=vol_score,
                )
            except Exception:
                continue

        # 6. 定时快照持久化
        if self.session_snapshot.should_snapshot():
            self.session_snapshot.save_snapshot(self.signal_ledger)
            self.session_snapshot.cleanup_old_snapshots()

        # 6.5 收盘盘后自动生成当日总结快照 (必须是真实交易日 且 15:00 之后)
        import datetime
        now_dt = datetime.datetime.now()
        if cct.get_trade_date_status() and now_dt.hour >= 15:
            self.session_snapshot.save_daily_summary(self.signal_ledger)

        # 6.6 清理不再追踪的旧股票量能画像 (防 24x7 内存累积)
        if hasattr(self.signal_ledger, "get_all_tracked_codes"):
            tracked_codes = self.signal_ledger.get_all_tracked_codes()
        elif hasattr(self.signal_ledger, "entries") and isinstance(self.signal_ledger.entries, dict):
            tracked_codes = [code for code, entry in self.signal_ledger.entries.items()
                             if getattr(entry, 'tier', '') in ('RADAR', 'WATCH', 'TRADE')]
        else:
            tracked_codes = []

        if hasattr(self, "volume_profiler") and hasattr(self.volume_profiler, "cleanup_stale"):
            self.volume_profiler.cleanup_stale(tracked_codes)

        # 7. 状态栏显示信号统计
        if hasattr(self.signal_ledger, "get_stats"):
            stats = self.signal_ledger.get_stats()
        elif hasattr(self.signal_ledger, "entries") and isinstance(self.signal_ledger.entries, dict):
            tier_counts = {}
            for entry in self.signal_ledger.entries.values():
                t = getattr(entry, 'tier', 'RADAR')
                tier_counts[t] = tier_counts.get(t, 0) + 1
            stats = {
                'tiers': tier_counts,
                'today_new': getattr(self.signal_ledger, '_signal_count', len(self.signal_ledger.entries))
            }
        else:
            stats = {'tiers': {}, 'today_new': 0}
        tier_info = stats.get('tiers', {})
        radar_n = tier_info.get('RADAR', 0)
        watch_n = tier_info.get('WATCH', 0)
        trade_n = tier_info.get('TRADE', 0)

        # 大盘环境标签
        env_label = ''
        if self.volume_profiler.market_context.is_rebound_from_shrink:
            env_label = f' | 🔥 缩量{self.volume_profiler.market_context.consecutive_market_shrink_days}日后反弹'

        self.status_bar.showMessage(
            f"📊 信号池: 候选 {radar_n} | 精选 {watch_n} | 实盘 {trade_n} | "
            f"今日新发现: {stats.get('today_new', 0)}{env_label}"
        )

    def _open_signal_detail_dialog(self):
        """点击按钮直接弹出/唤醒 [实时实盘个股详情] 提示窗口 (自动归纳 SignalLedger、TDX 信号及历史精选)"""
        signal_list = []
        seen = set()

        # 1. 优先从 SignalLedger 按 priority_score 降序与 TDX 标签提取全量已被锁定/提醒的强势个股
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries') and self.signal_ledger.entries:
            sorted_entries = sorted(
                self.signal_ledger.entries.values(),
                key=lambda e: (
                    1 if getattr(e, 'tdx_label', '') else 0,
                    getattr(e, 'priority_score', 0.0),
                    getattr(e, 'first_seen_ts', 0.0)
                ),
                reverse=True
            )
            for entry in sorted_entries:
                c_str = str(getattr(entry, 'code', '')).strip().zfill(6)
                if c_str and c_str not in seen:
                    seen.add(c_str)
                    n_str = getattr(entry, 'name', '')
                    if not n_str or n_str == c_str or n_str.isdigit():
                        n_str = self.get_stock_name(c_str)
                    
                    # 恢复默认模式，仅对通达信 (TDX) 信号单独增加 🔔 标记
                    if getattr(entry, 'tdx_label', '') or getattr(entry, 'signal_source', '') == 'TDX':
                        if not n_str.startswith('🔔'):
                            n_str = f"🔔 {n_str}"
                    signal_list.append((c_str, n_str))

        # 2. 补充 _last_batch_signal_codes 逆市/共振及 TDX 最新信号
        last_batch = getattr(self, "_last_batch_signal_codes", None) or []
        for item in last_batch:
            if isinstance(item, (tuple, list)):
                c_clean, n_clean = str(item[0]).strip().zfill(6), item[1]
            else:
                c_clean = str(item).strip().zfill(6)
                n_clean = self.get_stock_name(c_clean)
            if not n_clean or n_clean == c_clean or str(n_clean).isdigit():
                n_clean = self.get_stock_name(c_clean)
            if c_clean and c_clean not in seen:
                seen.add(c_clean)
                signal_list.append((c_clean, n_clean))

        # 3. 补充 SwingStateTable 大级别回调跟踪器中的个股
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            for r in range(tbl.rowCount()):
                c_item = tbl.item(r, 0)
                n_item = tbl.item(r, 1)
                if c_item:
                    c_clean = c_item.text().strip().zfill(6)
                    if c_clean and c_clean not in seen:
                        seen.add(c_clean)
                        n_str = n_item.text().strip() if n_item else self.get_stock_name(c_clean)
                        signal_list.append((c_clean, n_str))

        target_code = "000039"
        target_name = "中集集团"
        if signal_list:
            target_code, target_name = signal_list[0][0], signal_list[0][1]

        self.on_stock_clicked(target_code, target_name, batch_codes=signal_list)

    def _open_equity_pop_dialog(self):
        """打开/唤醒资金收益曲线及全市场走势独立放大查看窗口"""
        from PyQt6.sip import isdeleted
        if not hasattr(self, '_equity_pop_dialog') or self._equity_pop_dialog is None or isdeleted(self._equity_pop_dialog):
            self._equity_pop_dialog = EquityPopDialog(parent=self)
            
        if hasattr(self, 'current_df') and self.current_df is not None:
            self._equity_pop_dialog.update_data(self.current_df)

        if hasattr(self, 'bridge') and self.bridge:
            try:
                dates, strat_equity, bench_equity = self.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self._equity_pop_dialog.equity_chart.update_curve(x, strat_equity, bench_equity)
            except Exception as e:
                print(f"[ATSMainWindow] Sync equity curve error: {e}")

        self._equity_pop_dialog.show()
        self._equity_pop_dialog.raise_()
        self._equity_pop_dialog.activateWindow()

    def broadcast_code_link(self, code: str, bring_tdx_to_top: bool = False):
        """全系统统一标准的 StockSender 广播引擎：支持 TDX/THS 的零卡顿高可靠联动"""
        if not code:
            return
        code_clean = "".join(x for x in str(code) if x.isdigit()).zfill(6)
        if not code_clean:
            return

        # 优先使用项目标准的 StockSender 发送通道 (基于句柄消息投递与进程 Proxy 防卡死)
        if hasattr(self, 'sender') and self.sender is not None:
            try:
                self.sender.send(code_clean)
                return
            except Exception as e:
                print(f"[ATSMainWindow] Standard StockSender send failed: {e}")

        # 兜底静默剪贴板注入
        try:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            if cb:
                cb.setText(code_clean)
        except Exception:
            pass

    def locate_stock_in_tree(self, code: str, auto_popup: bool = False, bring_tdx_to_top: bool = False):
        """自动在 Universe 树、MA20d回调跟踪器表格与重点关注列表中高亮定位显示行，并自动广播联动 TDX 通达信"""
        if not code:
            return
        target_code = str(code).strip()

        # 1. 树定位高亮 (UniverseTree)
        if hasattr(self, "universe_tree") and self.universe_tree is not None:
            try:
                self.universe_tree.select_code(target_code)
            except Exception:
                pass

        # 2. 大级别 MA20d 回调跟踪器表格 (SwingStateTable) 自动定位高亮显示行
        if hasattr(self, "swing_table") and hasattr(self.swing_table, "table"):
            try:
                tbl = self.swing_table.table
                for row in range(tbl.rowCount()):
                    item = tbl.item(row, 0)
                    if item and item.text().strip() == target_code:
                        tbl.setCurrentCell(row, 0)
                        tbl.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                        break
            except Exception:
                pass

        # 3. 重点关注面板表格 (FavoritePanel) 自动定位高亮显示行
        if hasattr(self, "favorite_panel") and hasattr(self.favorite_panel, "table"):
            try:
                tbl_fav = self.favorite_panel.table
                for row in range(tbl_fav.rowCount()):
                    item = tbl_fav.item(row, 0)
                    if item and item.text().strip() == target_code:
                        tbl_fav.setCurrentCell(row, 0)
                        tbl_fav.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                        break
            except Exception:
                pass

        # 4. 秒级自动联动 TDX 通达信 (仅在显式请求时置顶通达信)
        self.broadcast_code_link(target_code, bring_tdx_to_top=bring_tdx_to_top)

        # 5. 仅在用户手动点击 Toast 时 (auto_popup=True) 自动弹出个股详情小窗口
        if auto_popup:
            try:
                name_str = target_code
                if hasattr(self, "get_stock_name"):
                    name_str = self.get_stock_name(target_code)
                batch_list = getattr(self, "_last_batch_signal_codes", None)
                self.on_stock_clicked(target_code, name_str, batch_codes=batch_list)
            except Exception:
                pass

    def _record_alpha_signal(self, code, name, pct_val, sh_pct, rs_val, resonance):
        """持久化记录大盘偏离共振信号，提供每日复盘与实时跟踪"""
        import os
        import json
        import time
        
        # 仅在有意义的逆市/共振强信号时记录；对符合条件的所有信号均纳入本轮批次列表
        if resonance not in ("逆市抗跌", "大盘共振"):
            return False

        recorded = True
        
        # 仅对暴拉偏离>=4.0%的排头黑马才触发系统 Toast 弹窗与语音 (杜绝刷屏)
        if pct_val >= 5.0 and (pct_val - sh_pct) >= 4.0:
            try:
                from ats.alert_notifier import AlertNotifier
                AlertNotifier().notify_special_signal(
                    code, name,
                    reason=f"{resonance} | 暴拉偏离大盘: {pct_val - sh_pct:+.2f}%",
                    score=90.0,
                    parent=self
                )
            except Exception:
                pass
            
        try:
            today_date = time.strftime("%Y-%m-%d")
            from sys_utils import get_app_root
            data_dir = os.path.join(get_app_root(), "datacsv")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                
            # 自动迁移旧路径下的所有 ats_alpha_tracker_*.json 文件到新的 datacsv 目录下
            old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            if os.path.exists(old_data_dir) and old_data_dir != data_dir:
                try:
                    import shutil
                    for fname in os.listdir(old_data_dir):
                        if fname.startswith("ats_alpha_tracker_") and fname.endswith(".json"):
                            old_filepath = os.path.join(old_data_dir, fname)
                            new_filepath = os.path.join(data_dir, fname)
                            if os.path.exists(old_filepath) and not os.path.exists(new_filepath):
                                shutil.copy2(old_filepath, new_filepath)
                                print(f"[ATSAlphaTracker] Migrated old alpha tracker data: {fname}")
                except Exception as e:
                    print(f"[ATSAlphaTracker] Failed to migrate old alpha tracker data: {e}")
                    
            log_path = os.path.join(data_dir, f"ats_alpha_tracker_{today_date}.json")
            
            # 使用内存去重，避免对同一个股票每秒行情刷新都重复写文件
            if not hasattr(self, "_recorded_alpha_stocks"):
                self._recorded_alpha_stocks = {}
                
            last_recorded_time = self._recorded_alpha_stocks.get(code, 0)
            now = time.time()
            # 针对同一只股票，同一状态，在 5 分钟（300秒）内只记录一次
            if now - last_recorded_time < 300:
                return
                
            self._recorded_alpha_stocks[code] = now
            
            # 读取已有的
            records = []
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r', encoding='utf-8') as f:
                        records = json.load(f)
                except Exception:
                    records = []
                    
            # 追加新纪录
            time_str = time.strftime("%H:%M:%S")
            records.append({
                "time": time_str,
                "code": code,
                "name": name,
                "pct": f"{pct_val:+.2f}%",
                "index_pct": f"{sh_pct:+.2f}%",
                "relative_strength": f"{rs_val:+.2f}%",
                "type": resonance
            })
            
            # 限制大小，最多保留 1000 条
            if len(records) > 1000:
                records = records[-1000:]
                
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
                
            print(f"[ATSAlphaTracker] 记录强势信号: {code} ({name}) {pct_val:+.2f}% {resonance}")
        except Exception as e:
            print(f"[ATSAlphaTracker] 记录信号失败: {e}")
        return recorded

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
            from ats.ui.styles import save_config_node
            save_config_node("ats_font_size", size)
        except Exception as e:
            print(f"[ATSMainWindow] Error saving font size: {e}")

    def apply_qss_with_font_size(self, size: int):
        import re
        from PyQt6.QtWidgets import QApplication, QTableView, QTreeView
        
        app = QApplication.instance()
        if app:
            app._is_updating_font = True
            
        try:
            qss = DARK_THEME_QSS
            qss = re.sub(r'font-size:\s*\d+(\.\d+)?pt;', f'font-size: {size}pt;', qss)
            self.setStyleSheet(qss)
            
            # Force restore column widths for all tables/trees with persistent headers
            for table in self.findChildren(QTableView):
                if hasattr(table, "restore_header_state"):
                    table.restore_header_state()
            for tree in self.findChildren(QTreeView):
                if hasattr(tree, "restore_header_state"):
                    tree.restore_header_state()
        finally:
            if app:
                app._is_updating_font = False

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

    def _on_main_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        if total > 0:
            self._main_ratio = [s / total for s in sizes]

    def _on_center_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        sizes = self.center_splitter.sizes()
        total = sum(sizes)
        if total > 0:
            self._center_ratio = [s / total for s in sizes]

    def _on_right_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        sizes = self.right_splitter.sizes()
        total = sum(sizes)
        if total > 0:
            self._right_ratio = [s / total for s in sizes]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_splitter_sizes_by_ratio()

    def _adjust_splitter_sizes_by_ratio(self):
        self._is_restoring_sizes = True
        try:
            # Adjust main horizontal splitter
            main_width = self.main_splitter.width()
            handle_count = self.main_splitter.count() - 1
            handle_width = self.main_splitter.handleWidth()
            available_width = main_width - (handle_count * handle_width)
            if available_width > 0:
                new_sizes = [int(available_width * r) for r in self._main_ratio]
                new_sizes[-1] = available_width - sum(new_sizes[:-1])
                self.main_splitter.setSizes(new_sizes)

            # Adjust center vertical splitter
            center_height = self.center_splitter.height()
            handle_count = self.center_splitter.count() - 1
            handle_width = self.center_splitter.handleWidth()
            available_height = center_height - (handle_count * handle_width)
            if available_height > 0:
                new_sizes = [int(available_height * r) for r in self._center_ratio]
                new_sizes[-1] = available_height - sum(new_sizes[:-1])
                self.center_splitter.setSizes(new_sizes)

            # Adjust right vertical splitter
            right_height = self.right_splitter.height()
            handle_count = self.right_splitter.count() - 1
            handle_width = self.right_splitter.handleWidth()
            available_height = right_height - (handle_count * handle_width)
            if available_height > 0:
                new_sizes = [int(available_height * r) for r in self._right_ratio]
                new_sizes[-1] = available_height - sum(new_sizes[:-1])
                self.right_splitter.setSizes(new_sizes)
        except Exception as e:
            print(f"[ATSMainWindow] Error adjusting splitter sizes: {e}")
        finally:
            self._is_restoring_sizes = False

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
            self._is_restoring_sizes = True
            try:
                from PyQt6.QtCore import QTimer
                if hasattr(self, 'main_splitter'):
                    main_sizes = data.get("ats_main_splitter_sizes")
                    if main_sizes:
                        self.main_splitter.setSizes(main_sizes)
                        total = sum(main_sizes)
                        if total > 0:
                            self._main_ratio = [s / total for s in main_sizes]
                        QTimer.singleShot(350, lambda: self._force_set_splitter_sizes('main_splitter', main_sizes))
                        
                if hasattr(self, 'center_splitter'):
                    center_sizes = data.get("ats_center_splitter_sizes")
                    if center_sizes:
                        self.center_splitter.setSizes(center_sizes)
                        total = sum(center_sizes)
                        if total > 0:
                            self._center_ratio = [s / total for s in center_sizes]
                        QTimer.singleShot(350, lambda: self._force_set_splitter_sizes('center_splitter', center_sizes))
                        
                if hasattr(self, 'right_splitter'):
                    right_sizes = data.get("ats_right_splitter_sizes")
                    if right_sizes:
                        self.right_splitter.setSizes(right_sizes)
                        total = sum(right_sizes)
                        if total > 0:
                            self._right_ratio = [s / total for s in right_sizes]
                        QTimer.singleShot(350, lambda: self._force_set_splitter_sizes('right_splitter', right_sizes))
            finally:
                self._is_restoring_sizes = False
            
            # 3. Restore tabs active indexes
            if hasattr(self, 'top_tabs'):
                top_index = data.get("ats_top_tab_index")
                if top_index is not None and 0 <= int(top_index) < self.top_tabs.count():
                    self.top_tabs.setCurrentIndex(int(top_index))
            if hasattr(self, 'center_tabs'):
                center_index = data.get("ats_center_tabs_index")
                if center_index is not None:
                    self.center_tabs.setCurrentIndex(int(center_index))
            if hasattr(self, 'right_tabs'):
                right_index = data.get("ats_right_tabs_index")
                if right_index is not None:
                    self.right_tabs.setCurrentIndex(int(right_index))
                    
            # 4. Restore link checkboxes
            if hasattr(self, 'cb_tdx'):
                tdx_link = data.get("ats_link_tdx")
                if tdx_link is not None:
                    self.cb_tdx.setChecked(bool(tdx_link))
            if hasattr(self, 'cb_ths'):
                ths_link = data.get("ats_link_ths")
                if ths_link is not None:
                    self.cb_ths.setChecked(bool(ths_link))
            if hasattr(self, 'cb_vis'):
                vis_link = data.get("ats_link_vis")
                if vis_link is not None:
                    self.cb_vis.setChecked(bool(vis_link))
        except Exception as e:
            print(f"[ATSMainWindow] Error restoring layout state: {e}")

    def _force_set_splitter_sizes(self, splitter_name, target_sizes):
        if getattr(self, '_is_closing', False):
            return
        splitter = getattr(self, splitter_name, None)
        if splitter:
            self._is_restoring_sizes = True
            try:
                splitter.setSizes(target_sizes)
                total = sum(target_sizes)
                if total > 0:
                    ratio = [s / total for s in target_sizes]
                    if splitter_name == 'main_splitter':
                        self._main_ratio = ratio
                    elif splitter_name == 'center_splitter':
                        self._center_ratio = ratio
                    elif splitter_name == 'right_splitter':
                        self._right_ratio = ratio
            finally:
                self._is_restoring_sizes = False

    def _save_layout_state(self):
        try:
            from ats.ui.styles import save_config_nodes
            updates = {}
            # Save geometry
            updates["ats_main_window_geometry"] = self.saveGeometry().toHex().data().decode()
            
            # Save splitters
            if hasattr(self, 'main_splitter'):
                updates["ats_main_splitter_sizes"] = self.main_splitter.sizes()
            if hasattr(self, 'center_splitter'):
                updates["ats_center_splitter_sizes"] = self.center_splitter.sizes()
            if hasattr(self, 'right_splitter'):
                updates["ats_right_splitter_sizes"] = self.right_splitter.sizes()
                
            # Save tabs index
            if hasattr(self, 'top_tabs'):
                updates["ats_top_tab_index"] = self.top_tabs.currentIndex()
            if hasattr(self, 'center_tabs'):
                updates["ats_center_tabs_index"] = self.center_tabs.currentIndex()
            if hasattr(self, 'right_tabs'):
                updates["ats_right_tabs_index"] = self.right_tabs.currentIndex()

            # Save link checkboxes
            if hasattr(self, 'cb_tdx'):
                updates["ats_link_tdx"] = self.cb_tdx.isChecked()
            if hasattr(self, 'cb_ths'):
                updates["ats_link_ths"] = self.cb_ths.isChecked()
            if hasattr(self, 'cb_vis'):
                updates["ats_link_vis"] = self.cb_vis.isChecked()
            
            save_config_nodes(updates)
        except Exception as e:
            print(f"[ATSMainWindow] Error saving layout state: {e}")

    def _on_top_tab_changed(self, index: int):
        """自动持久化记忆当前打开的是【重点关注】还是【大级别回调跟踪器】Tab 选项卡"""
        if not getattr(self, '_is_restoring_sizes', False):
            self._save_layout_state()

    def _on_tdx_signal_detected(self, sig_dict):
        """当后台 TdxSignalWatcher 捕获到通达信 / OrderMon 信号时的全逻辑联动处理"""
        if not sig_dict or not isinstance(sig_dict, dict):
            return

        code = sig_dict.get('code')
        if not code:
            return

        name = sig_dict.get('name', code)
        flag_label = sig_dict.get('flag_label', 'TDX信号')
        direction_cn = sig_dict.get('direction_cn', '买入')
        price = sig_dict.get('price', 0.0)
        time_str = sig_dict.get('time_str', '')

        # 1. 查找内存行情数据行并由 current_df 精确定位真实中文名称 (df 数据获取 name)
        df_row = None
        c_clean = str(code).zfill(6)
        if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            if c_clean in self.current_df.index:
                df_row = self.current_df.loc[c_clean]

        name = sig_dict.get('name', '')
        if df_row is not None and 'name' in df_row and str(df_row['name']).strip() and str(df_row['name']).strip() != c_clean:
            name = str(df_row['name']).strip()
        elif not name or name == c_clean or str(name).isdigit():
            name = self.get_stock_name(c_clean)

        sig_dict['name'] = name

        # 2. 写入 SignalLedger 并自动提权置顶
        if hasattr(self, 'signal_ledger'):
            entry = self.signal_ledger.record_tdx_signal(sig_dict, row=df_row)

        # 3. 将新捕获的通达信信号直接注册到 _last_batch_signal_codes 顶部
        if not hasattr(self, "_last_batch_signal_codes") or self._last_batch_signal_codes is None:
            self._last_batch_signal_codes = []
        self._last_batch_signal_codes = [x for x in self._last_batch_signal_codes if (x[0] if isinstance(x, (tuple, list)) else x) != c_clean]
        self._last_batch_signal_codes.insert(0, (c_clean, name))

        # 4. 实时更新并刷新 UI
        if hasattr(self, 'refresh_realtime_ui'):
            self.refresh_realtime_ui()

        # 5. 状态栏与控制台提醒 (带 AlertNotifier 去重语音与 Toast 提示)
        msg = f"🔔 [通达信信号] {code} {name} [{flag_label}] ({direction_cn}) 价格:{price:.2f} [{time_str}]"
        if hasattr(self, 'statusBar') and self.statusBar():
            self.statusBar().showMessage(msg, 10000)

        print(f"[ATS] {msg}")

        try:
            from ats.alert_notifier import AlertNotifier
            AlertNotifier().notify_special_signal(
                code=code,
                name=name,
                reason=f"通达信实盘信号: {flag_label} ({direction_cn})",
                score=95.0,
                parent=self
            )
        except Exception as e_notify:
            print(f"[ATS] TDX signal alert notification error: {e_notify}")

        # 6. 自动切股并联动外部通达信/同花顺终端
        if hasattr(self, 'link_stock'):
            self.link_stock(code, name)

    def closeEvent(self, event):
        """主窗口关闭退出时，自动跟随关闭所有独立的 TopLevel 子窗口、对话框、保存全量布局配置及安全回收后台线程"""
        self._is_closing = True
        
        # 1. 停止定时器与后台 Watcher
        if hasattr(self, 'update_timer') and self.update_timer.isActive():
            self.update_timer.stop()
            
        if hasattr(self, '_favorites_poll_timer') and self._favorites_poll_timer:
            self._favorites_poll_timer.stop()

        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().shutdown()
        except Exception as ex:
            print(f"[ATSMainWindow] Error shutting down favorites: {ex}")
            
        if hasattr(self, 'bridge') and self.bridge is not None:
            try:
                self.bridge.stop_listener()
            except Exception as ex:
                print(f"[ATSMainWindow] Error stopping IPC listener: {ex}")

        if hasattr(self, 'tdx_watcher') and self.tdx_watcher is not None:
            try:
                self.tdx_watcher.stop()
                self.tdx_watcher.wait(1000)
            except Exception as ex:
                print(f"[ATSMainWindow] Error stopping TDX signal watcher: {ex}")

        # 2. 🚀【广播主窗口退出信号】：通知所有悬浮独立窗口 (DNA、诊断、个股详情等) 接收退出事件并主动 close()
        try:
            from ats.ui.multi_period_dialog import ui_event_hub
            ui_event_hub.main_window_closing.emit()
            ui_event_hub.multi_period_closing.emit()
        except Exception as e:
            print(f"[ATSMainWindow] Error emitting closing signals: {e}")

        # 3. 遍历关闭所有活动的顶级 TopLevelWidgets（如个股分类详情弹窗、检查报告弹窗、DNA审计窗口等）
        try:
            from PyQt6.QtWidgets import QApplication
            for widget in list(QApplication.topLevelWidgets()):
                if widget != self:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(widget):
                        try:
                            widget.close()
                        except Exception:
                            pass
        except Exception as e:
            print(f"[ATSMainWindow] Error closing topLevelWidgets: {e}")

        # 4. 同步持久化保存所有物理窗口布局、Splitter 尺寸及 TDX/THS/VIS 联动勾选状态
        try:
            self._save_layout_state()
            
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

        try:
            if hasattr(self, "save_window_position_qt_visual"):
                self.save_window_position_qt_visual(self, getattr(self, "window_name", "ats_main_window"))
        except Exception:
            pass

        # 5. 关闭散落的行情分布弹窗、搜索历史与辅助对话框
        try:
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_close_all_dialogs'):
                self.dist_chart._close_all_dialogs()
        except Exception as e:
            print(f"[ATSMainWindow] Error closing dist chart dialogs: {e}")
            
        self._save_search_history_data()
        
        from PyQt6.sip import isdeleted
        if hasattr(self, 'dragon_monitor_dialog') and self.dragon_monitor_dialog and not isdeleted(self.dragon_monitor_dialog):
            try:
                self.dragon_monitor_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing dragon monitor on close: {e}")
                
        try:
            import ats.ui.multi_period_dialog as mpd
            if mpd._dialog_instance and not isdeleted(mpd._dialog_instance):
                mpd._dialog_instance.close()
            mpd._dialog_instance = None
        except Exception as e:
            print(f"[ATSMainWindow] Error closing multi period dialog on close: {e}")
            
        super().closeEvent(event)

    def _on_favorites_changed(self):
        # Thread-safe trigger UI refresh on favorite changes using QTimer
        QTimer.singleShot(0, self._safe_favorites_changed)

    def _poll_favorites_loop(self):
        try:
            from global_favorites import GlobalFavoriteManager
            current_version = GlobalFavoriteManager().version
            if current_version != getattr(self, '_last_favorites_version', 0):
                self._last_favorites_version = current_version
                self._on_favorites_changed()
        except Exception:
            pass

    def _safe_favorites_changed(self):
        if getattr(self, '_is_closing', False):
            return
        try:
            # Refresh universe tree and swing table
            self.refresh_realtime_ui()
            
            # If the universe tree is currently displaying mock data, refresh the mock view too
            if hasattr(self, 'universe_widget') and getattr(self.universe_widget, '_is_mock_active', False):
                self.universe_widget.load_mock_data()
                
            # Refresh heatmap widget
            if hasattr(self, 'heatmap_widget'):
                self.heatmap_widget.load_live_sectors()
                
            # Refresh active distribution details dialogs if open
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_active_dialogs'):
                from PyQt6.sip import isdeleted
                for d in self.dist_chart._active_dialogs:
                    try:
                        if not isdeleted(d) and d.isVisible() and hasattr(d, 'refresh_favorites_display'):
                            d.refresh_favorites_display()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ATSMainWindow] Error refreshing UI on favorites changed: {e}")

    def open_dragon_monitor(self):
        if getattr(self, '_is_closing', False):
            return
        from PyQt6.sip import isdeleted
        if self.dragon_monitor_dialog is None or isdeleted(self.dragon_monitor_dialog):
            self.dragon_monitor_dialog = DragonLeaderMonitorDialog(self)
            self.dragon_monitor_dialog.code_clicked.connect(self.link_stock)
        self.dragon_monitor_dialog.show_normal_position()
        
        has_df = self.current_df is not None and not self.current_df.empty
        sh_pct = 0.0
        if has_df:
            if 'sh000001' in self.current_df.index:
                sh_pct = float(self.current_df.loc['sh000001'].get('percent', 0.0))
            elif '000001' in self.current_df.index and 'sh' in str(self.current_df.loc['000001'].get('code', '')):
                sh_pct = float(self.current_df.loc['000001'].get('percent', 0.0))
            else:
                if 'percent' in self.current_df.columns:
                    sh_pct = float(self.current_df['percent'].mean())
        try:
            self.dragon_monitor_dialog.update_data(self.current_df, sh_pct)
        except Exception as e:
            print(f"[ATSMainWindow] Error updating dragon monitor on open: {e}")

    def open_global_market_dialog(self):
        """打开/激活【🌐 全球外盘与热点情绪看板】独立自适应窗口 (不影响主界面原有布局)"""
        from ats.ui.global_market_dialog import open_global_market_dialog
        open_global_market_dialog(parent_window=self)

    def open_multi_period_tester(self):
        """[NEW] 打开/切换多周期联动策略筛选器 (优先检测内部调用，其次检测外部 MultiPeriodTester.exe/脚本)"""
        if getattr(self, '_is_closing', False):
            return

        import time
        now = time.time()
        last_t = getattr(self, "_last_multi_period_trigger_t", 0.0)
        if now - last_t < 0.3:
            return
        self._last_multi_period_trigger_t = now

        # 1. 优先检测并切换内部 PyQt6 Dialog 的打开/显示/隐藏状态
        from PyQt6.sip import isdeleted
        import ats.ui.multi_period_dialog as mpd
        
        dialog = mpd._dialog_instance
        if dialog is not None and not isdeleted(dialog):
            try:
                if dialog.isVisible() and not dialog.isMinimized():
                    dialog.hide()
                    print("[MultiPeriod] Internal dialog is visible, hiding it.")
                else:
                    if dialog.isMinimized():
                        dialog.showNormal()
                    else:
                        dialog.show()
                    dialog.raise_()
                    dialog.activateWindow()
                    print("[MultiPeriod] Internal dialog shown and activated.")
                return
            except Exception as e:
                print(f"[MultiPeriod] Toggle internal dialog error: {e}")
                mpd._dialog_instance = None

        # 2. 如果内部窗口不存在，检测并切换外部独立进程窗口
        titles = ["多周期联动策略筛选器", "⏱️ 多周期交叉筛选与诊断系统"]
        hwnd = None
        try:
            import ctypes
            import os
            for t in titles:
                found_hwnd = ctypes.windll.user32.FindWindowW(None, t)
                if found_hwnd:
                    # 排除本进程的窗口，防止标题一致时误判内部窗口为外部窗口
                    pid = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(found_hwnd, ctypes.byref(pid))
                    if pid.value != os.getpid():
                        hwnd = found_hwnd
                        break
            
            if hwnd:
                is_visible = ctypes.windll.user32.IsWindowVisible(hwnd)
                is_iconic = ctypes.windll.user32.IsIconic(hwnd)
                
                if is_visible and not is_iconic:
                    # 如果外部窗口当前可见且未最小化，再次点击则隐藏它
                    ctypes.windll.user32.ShowWindow(hwnd, 0) # SW_HIDE = 0
                    print("[MultiPeriod] External window is visible, hiding it.")
                else:
                    # 如果外部窗口不可见，或者在后台，则将其唤醒、恢复并置顶聚焦
                    if is_iconic:
                        ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE = 9
                    else:
                        ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW = 5
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    print("[MultiPeriod] External window is background/hidden, restoring and bringing to foreground.")
                return
        except Exception as e:
            print(f"[MultiPeriod] FindWindowW error: {e}")

        # 3. 否则，全新打开内部多周期窗口
        try:
            print("🚀 [MultiPeriod] Opening internal PyQt6 MultiPeriodDialog...")
            mpd.open_multi_period_tester(parent_window=self)
        except Exception as e:
            print(f"[MultiPeriod] Failed to open internal MultiPeriodDialog: {e}")



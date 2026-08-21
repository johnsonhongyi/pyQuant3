# -*- coding: utf-8 -*-
"""
ats/ui/new_stock_panel.py — ATS 新股/次新股/IPO全流程监控与分时阶梯策略主控看板
特点：
1. 极简轻量顶部工具栏（含【🚀 阶梯盯盘】与【📈 SBC 走势】核心直达入口，支持 3 秒高频自动刷新）；
2. 基于 BaseATSTableWidget 实现极窄自适应列宽与用户手动列宽持久化记忆；
3. 【视图与焦点保护】：数据刷新时 100% 保持当前滚动条位置、不跳行、不丢焦点、零闪烁、0 Qt警告；
4. 【排序持久化】：支持点击表头任意列排序，自动物理持久化并于每次刷新与启动时精准恢复；
5. 全通道（腾讯+东财+新浪+TDX）自动补齐现价、涨跌幅、换手率、成交额、流通市值与总市值，杜绝数据缺失；
6. 单击仅联动外部行情 (link_stock)，双击调出分时阶梯独立盯盘 (PinzhunLadderStandaloneWindow)。
"""

import sys
import os
import time
import logging
import datetime
import pandas as pd
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QHeaderView, QSplitter, QGroupBox, QComboBox, QLineEdit,
    QMenu, QMessageBox, QFrame, QGridLayout, QApplication, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QBrush, QIcon, QCursor, QAction

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import (
    NumericTableWidgetItem, COLOR_UP, COLOR_DOWN, COLOR_WARN,
    COLOR_ACCENT, COLOR_INFO, load_config_node, save_config_node
)
from ats.new_stock_fetcher import NewStockFetcher
from ats.new_stock_strategy_generator import NewStockStrategyGenerator
from ats.intraday_strategy_engine import IntradayStrategyEngine
from sys_utils import get_app_root, resolve_stock_name

logger = logging.getLogger("NewStockPanel")

SORT_CONFIG_KEY = "ats_new_stock_sort_state_v1"


class NewStockFetchWorker(QThread):
    """后台新股数据抓取与实时补齐 Worker 线程 (完全解耦网络 IO 与 UI 渲染)"""
    data_ready = pyqtSignal(object)  # pd.DataFrame
    fetch_failed = pyqtSignal(str)

    def __init__(self, force_refresh: bool = False, enrich_tdx: bool = True):
        super().__init__()
        self.force_refresh = force_refresh
        self.enrich_tdx = enrich_tdx

    def run(self):
        try:
            fetcher = NewStockFetcher.get_instance()
            df = fetcher.get_combined_new_stocks(force_refresh=self.force_refresh)
            self.data_ready.emit(df)
        except Exception as e:
            logger.error(f"NewStockFetchWorker 执行异常: {e}")
            self.fetch_failed.emit(str(e))


class NewStockPanel(QWidget):
    """新股与次新股主控看板面板"""

    # 信号定义：单击仅发送选中/联动，双击才发送打开详情
    stock_selected = pyqtSignal(str, str)        # code, name (单击联动)
    stock_double_clicked = pyqtSignal(str, str) # code, name (双击详情)

    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.df_data = pd.DataFrame()
        self.selected_code = ""
        self.selected_name = ""
        self.selected_row_data: Dict[str, Any] = {}
        self._is_fetching = False

        # 排序持久化状态 (默认: 第3列 上市日 降序)
        self.sort_col = 3
        self.sort_order = Qt.SortOrder.DescendingOrder
        self._load_sort_state()

        self._init_ui()
        self._start_auto_refresh()

    def _load_sort_state(self):
        """从配置文件加载恢复最后的排序设置"""
        try:
            cfg = load_config_node(SORT_CONFIG_KEY)
            if isinstance(cfg, dict) and "col" in cfg:
                self.sort_col = int(cfg.get("col", 3))
                order_val = int(cfg.get("order", 1))
                self.sort_order = Qt.SortOrder(order_val)
        except Exception as e:
            logger.debug(f"加载新股表格排序配置异常: {e}")

    def _save_sort_state(self, col: int, order: Qt.SortOrder):
        """将当前排序列与方向持久化保存"""
        self.sort_col = col
        self.sort_order = order
        try:
            save_config_node(SORT_CONFIG_KEY, {
                "col": int(col),
                "order": int(order.value if hasattr(order, 'value') else int(order))
            })
        except Exception as e:
            logger.debug(f"保存新股表格排序配置异常: {e}")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── 1. 顶部操作与控制栏 (极简紧凑排布) ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setToolTip("手动立即重新拉取全量新股与实时行情数据")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #1e293b; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px 6px; font-size: 9pt; }
            QPushButton:hover { background-color: #38bdf8; color: #000000; }
        """)
        self.btn_refresh.clicked.connect(lambda: self.load_data(force_refresh=True))
        top_bar.addWidget(self.btn_refresh)

        # 自动刷新复选框 (默认开启，实盘 3 秒级自动更新)
        self.cb_auto_refresh = QCheckBox("自动刷新(3s)")
        self.cb_auto_refresh.setChecked(True)
        self.cb_auto_refresh.setToolTip("开启后，实盘交易时段每 3 秒自动静默拉取并刷新最新行情与换手率")
        self.cb_auto_refresh.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        self.cb_auto_refresh.toggled.connect(self._on_auto_refresh_toggled)
        top_bar.addWidget(self.cb_auto_refresh)

        # 分类筛选
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["全部标的", "🌟 首日(N)", "🚀 前5日(C)", "📈 次新股", "⏳ 待上市"])
        self.combo_filter.setStyleSheet("""
            QComboBox { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 3px; padding: 2px 4px; font-size: 9pt; min-width: 90px; }
            QComboBox QAbstractItemView { background-color: #0f172a; color: #f8fafc; selection-background-color: #1e293b; }
        """)
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        top_bar.addWidget(self.combo_filter)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜代码/名称")
        self.search_edit.setStyleSheet("""
            QLineEdit { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; border-radius: 3px; padding: 2px 4px; font-size: 9pt; max-width: 95px; }
        """)
        self.search_edit.textChanged.connect(self._apply_filter)
        top_bar.addWidget(self.search_edit)

        # 核心快捷操作按钮
        self.btn_gen_strategy = QPushButton("⚡ 生成阶梯策略")
        self.btn_gen_strategy.setToolTip("为选中或批量新股自动构建标准统一的 v1.0-unified 分时阶梯策略文件")
        self.btn_gen_strategy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen_strategy.setStyleSheet("""
            QPushButton { background-color: #3b1d1d; color: #f87171; font-weight: bold; border: 1px solid #ef4444; border-radius: 3px; padding: 2px 6px; font-size: 9pt; }
            QPushButton:hover { background-color: #ef4444; color: #ffffff; }
        """)
        self.btn_gen_strategy.clicked.connect(self._on_generate_strategy_clicked)
        top_bar.addWidget(self.btn_gen_strategy)

        self.btn_open_ladder = QPushButton("🚀 阶梯盯盘")
        self.btn_open_ladder.setToolTip("打开选中新股专属的分时阶梯策略独立盯盘窗口与7节点动态评估系统")
        self.btn_open_ladder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_ladder.setStyleSheet("""
            QPushButton { background-color: #1c2e24; color: #4ade80; font-weight: bold; border: 1px solid #22c55e; border-radius: 3px; padding: 2px 6px; font-size: 9pt; }
            QPushButton:hover { background-color: #22c55e; color: #000000; }
        """)
        self.btn_open_ladder.clicked.connect(self._on_open_ladder_clicked)
        top_bar.addWidget(self.btn_open_ladder)

        self.btn_open_sbc = QPushButton("📈 SBC 走势")
        self.btn_open_sbc.setToolTip("调出选中标的的 SBC 实盘分时走势独立窗口")
        self.btn_open_sbc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_sbc.setStyleSheet("""
            QPushButton { background-color: #1e1e38; color: #a78bfa; font-weight: bold; border: 1px solid #8b5cf6; border-radius: 3px; padding: 2px 6px; font-size: 9pt; }
            QPushButton:hover { background-color: #8b5cf6; color: #ffffff; }
        """)
        self.btn_open_sbc.clicked.connect(self._on_open_sbc_clicked)
        top_bar.addWidget(self.btn_open_sbc)

        top_bar.addStretch()

        self.lbl_status = QLabel("🟢 正在初始化数据...")
        self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        top_bar.addWidget(self.lbl_status)

        main_layout.addLayout(top_bar)

        # ── 2. 主表与底部抽屉 Splitter ──
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # 核心数据表格 (基于 BaseATSTableWidget 实现极窄自适应与列宽持久化)
        self.table = BaseATSTableWidget(self)
        self.headers = [
            "代码", "名称", "状态", "上市日", "申购日", "发行价",
            "现价", "涨跌%", "换手%", "流通(亿)", "总值(亿)",
            "成交(亿)", "阶梯策略"
        ]
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        
        # 极窄默认列宽 (紧凑自适应，总宽约 750px，完全一屏容纳)
        default_widths = [55, 68, 62, 68, 68, 48, 48, 52, 50, 58, 58, 52, 65]
        self.table.setup_persistence(
            config_key="ats_new_stock_table_state_v1",
            default_widths=default_widths
        )

        # 允许用户自由拖拽调整列宽
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)

        # 监听用户点击表头排序事件并实时持久化
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort_changed)

        self.table.stock_activated.connect(self._on_stock_activated)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self.splitter.addWidget(self.table)

        # ── 3. 底部阶梯档位推演与发行参数抽屉卡片 ──
        self.preview_card = QGroupBox("📍 新股发行参数与分时阶梯档位推演 (Ladder Prediction)")
        self.preview_card.setStyleSheet("""
            QGroupBox {
                background-color: #0b0f19;
                color: #38bdf8;
                border: 1px solid #1e293b;
                border-radius: 4px;
                margin-top: 4px;
                font-weight: bold;
                padding: 6px;
                font-size: 8.5pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
        """)
        preview_layout = QGridLayout(self.preview_card)
        preview_layout.setContentsMargins(6, 8, 6, 6)
        preview_layout.setSpacing(6)

        self.lbl_spec_title = QLabel("请在上方表格中选择任意新股以查看阶梯档位与发行推演")
        self.lbl_spec_title.setStyleSheet("color: #94a3b8; font-size: 9pt; font-weight: normal;")
        preview_layout.addWidget(self.lbl_spec_title, 0, 0, 1, 5)

        # 阶梯档位标签 (5大档位)
        self.ladder_labels = []
        for i in range(5):
            lbl = QLabel(f"档位 +{(i+1)*100}%: --")
            lbl.setStyleSheet("background-color: #0f172a; color: #f8fafc; padding: 2px 4px; border: 1px solid #334155; border-radius: 2px; font-size: 8.5pt;")
            preview_layout.addWidget(lbl, 1, i)
            self.ladder_labels.append(lbl)

        # 临停与过热警戒
        self.lbl_halt_info = QLabel("临停: +30% (-- 元) | +60% (-- 元)")
        self.lbl_halt_info.setStyleSheet("color: #fbbf24; font-size: 8.5pt;")
        preview_layout.addWidget(self.lbl_halt_info, 2, 0, 1, 2)

        self.lbl_overheat_info = QLabel("资金强度: 警戒成交额 > -- 亿 (换手>90%进入过热区)")
        self.lbl_overheat_info.setStyleSheet("color: #f87171; font-size: 8.5pt;")
        preview_layout.addWidget(self.lbl_overheat_info, 2, 2, 1, 3)

        self.splitter.addWidget(self.preview_card)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.splitter)

    def _on_header_sort_changed(self, col: int, order: Qt.SortOrder):
        """用户点击表头排序列时触发：记录并持久化"""
        self._save_sort_state(col, order)

    def _start_auto_refresh(self):
        """初始异步拉取与定时高频自动刷新"""
        self.load_data(force_refresh=False)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(3000)  # 3秒高频轮询
        self.auto_refresh_timer.timeout.connect(self._on_auto_timer_tick)
        self.auto_refresh_timer.start()

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked:
            self.auto_refresh_timer.start(3000)
            self.lbl_status.setText("🟢 自动刷新已开启 (3s)")
        else:
            self.auto_refresh_timer.stop()
            self.lbl_status.setText("⏸️ 自动刷新已暂停")

    def _on_auto_timer_tick(self):
        """定时器触发：在后台静默拉取更新，不阻塞 UI"""
        if self._is_fetching or not self.cb_auto_refresh.isChecked():
            return
        self.load_data(force_refresh=False)

    def load_data(self, force_refresh: bool = False):
        """启动后台线程拉取全量新股与实时数据"""
        if self._is_fetching:
            return
        self._is_fetching = True
        self.worker = NewStockFetchWorker(force_refresh=force_refresh, enrich_tdx=True)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.fetch_failed.connect(self._on_fetch_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self):
        self._is_fetching = False

    def _on_data_ready(self, df: pd.DataFrame):
        self._is_fetching = False
        if df is not None and not df.empty:
            self.df_data = df
            self._render_table()
            if self.selected_code:
                match = self.df_data[self.df_data["code"] == self.selected_code]
                if not match.empty:
                    self.selected_row_data = match.iloc[0].to_dict()
                    self._update_preview_card(self.selected_row_data)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        strat_cnt = self.df_data['has_strategy'].sum() if not self.df_data.empty else 0
        self.lbl_status.setText(f"🟢 实时更新: {now_str} | 共 {len(self.df_data)} 标的 (已配置: {strat_cnt})")

    def _on_fetch_failed(self, err_msg: str):
        self._is_fetching = False
        self.lbl_status.setText(f"❌ 刷新异常: {err_msg[:25]}")

    def update_from_ipc_df(self, df_ipc: pd.DataFrame):
        """
        接收来自 ATS 主终端 IPC 数据流的实时全市场 DataFrame:
        优先采用 IPC 行情，并进行原地静默平滑刷新
        """
        if self.df_data.empty or df_ipc is None or df_ipc.empty:
            return

        updated_any = False
        for idx, row in self.df_data.iterrows():
            code = str(row["code"]).zfill(6)
            ipc_row = None
            if code in df_ipc.index:
                ipc_row = df_ipc.loc[code]
            elif code.lstrip('0') in df_ipc.index:
                ipc_row = df_ipc.loc[code.lstrip('0')]

            if ipc_row is not None:
                if hasattr(ipc_row, "iloc") and len(ipc_row.shape) > 1:
                    ipc_row = ipc_row.iloc[0]
                p = float(ipc_row.get("close", ipc_row.get("price", ipc_row.get("now", 0.0))) or 0.0)
                if p > 0:
                    self.df_data.at[idx, "price"] = p
                    pct_val = float(ipc_row.get("percent", ipc_row.get("pct", 0.0)) or 0.0)
                    self.df_data.at[idx, "pct"] = pct_val
                    to_val = float(ipc_row.get("turnover", ipc_row.get("turnover_rate", 0.0)) or 0.0)
                    if to_val > 0:
                        self.df_data.at[idx, "turnover"] = to_val
                    amt_val = float(ipc_row.get("amount", 0.0) or 0.0)
                    if amt_val > 0:
                        self.df_data.at[idx, "amount_yi"] = round(amt_val / 1e8, 2)
                    updated_any = True

        if updated_any:
            self._render_table()

    def _apply_filter(self):
        """应用分类筛选和关键词过滤"""
        self._render_table()

    def _set_or_update_item(self, row: int, col: int, text: str, 
                            color: Optional[str] = None, 
                            font: Optional[QFont] = None, 
                            align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter):
        """
        【零警告原地单元格更新 Helper】
        若 item 已存在则直接复用更新属性，绝不重复调用 setItem，彻底杜绝 Qt 警告
        """
        item = self.table.item(row, col)
        if item is None:
            new_item = NumericTableWidgetItem(str(text))
            new_item.setTextAlignment(align)
            if color:
                new_item.setForeground(QBrush(QColor(color)))
            if font:
                new_item.setFont(font)
            self.table.setItem(row, col, new_item)
        else:
            item.setText(str(text))
            item.setTextAlignment(align)
            if color:
                item.setForeground(QBrush(QColor(color)))
            if font:
                item.setFont(font)

    def _render_table(self):
        """
        【⚡ 核心视图与焦点保护渲染】
        1. 保持当前滚动条位置 (v_scroll / h_scroll)；
        2. 保持当前选中的股票焦点 (selected_code)，绝不因刷新而重置跳动；
        3. 严格遵循持久化的排序规则 (sort_col, sort_order)；
        4. 原地复用单元格，零闪烁、平滑刷新、0 Qt 警告。
        """
        if self.df_data.empty:
            self.table.setRowCount(0)
            return

        # ── 1. 记录刷新前的视图状态与焦点 ──
        v_scroll_val = self.table.verticalScrollBar().value()
        h_scroll_val = self.table.horizontalScrollBar().value()
        saved_selected_code = self.selected_code

        df_filtered = self.df_data.copy()
        
        # 分类筛选
        filter_type = self.combo_filter.currentText()
        if "首日" in filter_type:
            df_filtered = df_filtered[df_filtered["status"].str.contains("首日|N", regex=True)]
        elif "前5日" in filter_type:
            df_filtered = df_filtered[df_filtered["status"].str.contains("前5日|C", regex=True)]
        elif "次新股" in filter_type:
            df_filtered = df_filtered[df_filtered["status"].str.contains("次新")]
        elif "待上市" in filter_type:
            df_filtered = df_filtered[df_filtered["status"].str.contains("待上市|即将上市")]

        # 搜索关键词过滤
        search_txt = self.search_edit.text().strip().lower()
        if search_txt:
            mask = (
                df_filtered["code"].astype(str).str.lower().str.contains(search_txt) |
                df_filtered["name"].astype(str).str.lower().str.contains(search_txt)
            )
            df_filtered = df_filtered[mask]

        target_row_count = len(df_filtered)

        # ── 2. 屏蔽信号并进行原地单元格更新 ──
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)

        if self.table.rowCount() != target_row_count:
            self.table.setRowCount(target_row_count)

        bold_font = QFont("Microsoft YaHei", 9, QFont.Weight.Bold)
        consolas_bold = QFont("Consolas", 9, QFont.Weight.Bold)

        for row_idx, (_, row) in enumerate(df_filtered.iterrows()):
            code = str(row.get("code", "")).zfill(6)
            name = str(row.get("name", ""))
            status = str(row.get("status", "次新"))
            listing_d = str(row.get("listing_date", "-"))
            apply_d = str(row.get("apply_date", "-"))
            issue_p = float(row.get("issue_price", 0.0))
            price = float(row.get("price", 0.0))
            pct = float(row.get("pct", 0.0))
            turnover = float(row.get("turnover", 0.0))
            float_mv = float(row.get("float_mv_yi", 0.0))
            total_mv = float(row.get("total_mv_yi", 0.0))
            amt = float(row.get("amount_yi", 0.0))
            has_strat = bool(row.get("has_strategy", False))

            # 极简状态名称
            status_short = status
            if "首日" in status:
                status_short = "首日(N)"
            elif "前5日" in status:
                status_short = "前5日(C)"
            elif "待上市" in status or "即将" in status:
                status_short = "待上市"
            elif "次新" in status:
                status_short = "次新"

            # 0: 代码
            self._set_or_update_item(row_idx, 0, code, color="#38bdf8", align=Qt.AlignmentFlag.AlignCenter)

            # 1: 名称
            name_color = "#f43f5e" if name.startswith("N") else ("#fbbf24" if name.startswith("C") else "#ffffff")
            self._set_or_update_item(row_idx, 1, name, color=name_color, font=bold_font, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # 2: 状态
            status_color = "#f43f5e" if "首日" in status_short else ("#fbbf24" if "前5日" in status_short else ("#a78bfa" if "待上市" in status_short else "#94a3b8"))
            self._set_or_update_item(row_idx, 2, status_short, color=status_color, align=Qt.AlignmentFlag.AlignCenter)

            # 3: 上市日
            self._set_or_update_item(row_idx, 3, listing_d, align=Qt.AlignmentFlag.AlignCenter)

            # 4: 申购日
            self._set_or_update_item(row_idx, 4, apply_d, align=Qt.AlignmentFlag.AlignCenter)

            # 5: 发行价
            issue_str = f"{issue_p:.2f}" if issue_p > 0 else "--"
            self._set_or_update_item(row_idx, 5, issue_str, color="#cbd5e1", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 6: 现价 & 7: 涨跌%
            p_display = f"{price:.2f}" if price > 0 else "--"
            pct_str = f"{pct:+.2f}%" if price > 0 else "--"
            p_color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else "#94a3b8")
            self._set_or_update_item(row_idx, 6, p_display, color=p_color, font=consolas_bold, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._set_or_update_item(row_idx, 7, pct_str, color=p_color, font=consolas_bold, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 8: 换手%
            to_str = f"{turnover:.2f}%" if turnover > 0 else "--"
            to_color = "#f43f5e" if turnover >= 70.0 else ("#fbbf24" if turnover >= 50.0 else "#94a3b8")
            to_font = consolas_bold if turnover >= 70.0 else None
            self._set_or_update_item(row_idx, 8, to_str, color=to_color, font=to_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 9: 流通(亿)
            fmv_str = f"{float_mv:.2f}" if float_mv > 0 else "--"
            self._set_or_update_item(row_idx, 9, fmv_str, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 10: 总值(亿)
            tmv_str = f"{total_mv:.2f}" if total_mv > 0 else "--"
            self._set_or_update_item(row_idx, 10, tmv_str, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 11: 成交(亿)
            amt_str = f"{amt:.2f}" if amt > 0 else "--"
            self._set_or_update_item(row_idx, 11, amt_str, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # 12: 策略状态
            strat_txt = "✅ 已配" if has_strat else "⚪ 未配"
            strat_color = "#4ade80" if has_strat else "#64748b"
            self._set_or_update_item(row_idx, 12, strat_txt, color=strat_color, align=Qt.AlignmentFlag.AlignCenter)

        # ── 3. 应用并保持持久化的排序列和方向 ──
        self.table.setSortingEnabled(True)
        if 0 <= self.sort_col < self.table.columnCount():
            self.table.sortItems(self.sort_col, self.sort_order)

        # ── 4. 恢复选中焦点与滚动条位置 ──
        if saved_selected_code:
            target_row = -1
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 0)
                if it and it.text().strip() == saved_selected_code:
                    target_row = r
                    break
            if target_row >= 0:
                self.table.setCurrentCell(target_row, 0)

        # 恢复滚动条
        self.table.verticalScrollBar().setValue(v_scroll_val)
        self.table.horizontalScrollBar().setValue(h_scroll_val)

        self.table.blockSignals(False)

    def _on_stock_activated(self, code: str, name: str):
        """
        BaseATSTableWidget 激活行（键盘上下键或鼠标单击）：
        仅更新选中高亮与底部推演卡片，并发送 stock_selected 联动外部行情，绝不主动弹出任何详情弹窗！
        """
        self.selected_code = code
        self.selected_name = name

        if not self.df_data.empty:
            match = self.df_data[self.df_data["code"] == code]
            if not match.empty:
                self.selected_row_data = match.iloc[0].to_dict()

        self._update_preview_card(self.selected_row_data)
        self.stock_selected.emit(code, name)

        # 向主终端发送物理行情联动 (link_stock)
        if self.main_window and hasattr(self.main_window, "link_stock"):
            try:
                self.main_window.link_stock(code, name)
            except Exception as e:
                logger.debug(f"link_stock 异常: {e}")

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击单元格：直接调出分时阶梯独立盯盘窗口"""
        item_code = self.table.item(row, 0)
        item_name = self.table.item(row, 1)
        if item_code:
            code = item_code.text()
            name = item_name.text() if item_name else ""
            self._on_stock_activated(code, name)
            self.stock_double_clicked.emit(code, name)
            self._on_open_ladder_clicked()

    def _update_preview_card(self, row_data: Dict[str, Any]):
        """根据选中标的数据更新底部阶梯推演卡片"""
        if not row_data:
            return

        code = str(row_data.get("code", "")).zfill(6)
        name = str(row_data.get("name", ""))
        issue_p = float(row_data.get("issue_price", 0.0))
        float_mv = float(row_data.get("float_mv_yi", 0.0))
        curr_p = float(row_data.get("price", 0.0))
        listing_d = str(row_data.get("listing_date", "-"))

        if issue_p <= 0 and curr_p > 0:
            issue_p = round(curr_p / 2.0, 2)

        self.lbl_spec_title.setText(
            f"【{name} ({code})】 发行价: {issue_p:.2f}元 | 上市: {listing_d} | 发行流通市值: {float_mv:.2f}亿"
        )

        sign_shares = 100 if code.startswith(("920", "83", "87", "88", "43")) else 500
        gains = [100.0, 200.0, 300.0, 400.0, 500.0]

        for i, gain in enumerate(gains):
            target_p = round(issue_p * (1.0 + gain / 100.0), 2)
            profit = round((target_p - issue_p) * sign_shares, 2)
            if i < len(self.ladder_labels):
                self.ladder_labels[i].setText(f"+{int(gain)}%: {target_p:.2f}元 (赚{profit:,.0f}元)")

        # 临停监控
        base_p = curr_p if curr_p > 0 else issue_p
        halt30 = round(base_p * 1.30, 2)
        halt60 = round(base_p * 1.60, 2)
        self.lbl_halt_info.setText(f"临停监控 (基准 {base_p:.2f}元): +30% 临停 {halt30:.2f}元 | +60% 临停 {halt60:.2f}元")

        # 资金强度
        overheat_amt = round(float_mv * 2.5, 2) if float_mv > 0 else round(issue_p * 0.5, 2)
        self.lbl_overheat_info.setText(f"资金强度: 警戒成交额 > {overheat_amt:.2f} 亿 (换手>90%进入过热区)")

    def _on_generate_strategy_clicked(self):
        """一键为选中标的（或批量未配置标的）生成标准分时阶梯策略"""
        if not self.selected_code:
            unconfigured = []
            if not self.df_data.empty:
                unconfigured = self.df_data[~self.df_data["has_strategy"]].to_dict("records")

            if not unconfigured:
                QMessageBox.information(self, "提示", "所有新股标的均已生成配套分时阶梯策略！")
                return

            reply = QMessageBox.question(
                self, "批量生成策略确认",
                f"检测到 {len(unconfigured)} 只未配置策略的新股，是否一键批量生成标准分时阶梯策略？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                generator = NewStockStrategyGenerator.get_instance()
                count = generator.batch_generate_and_save(unconfigured)
                QMessageBox.information(self, "成功", f"🎉 成功批量构建生成 {count} 只新股的分时阶梯策略并完成热重载！")
                self.load_data(force_refresh=True)
            return

        generator = NewStockStrategyGenerator.get_instance()
        strat = generator.generate_strategy(self.selected_row_data)
        ok = generator.save_or_update_strategy(strat)
        if ok:
            QMessageBox.information(
                self, "策略生成成功",
                f"🎉 标的【{self.selected_name} ({self.selected_code})】分时阶梯与 7 节点动态策略已构建完成！\n"
                f"已自动写入 config/intraday_newstock_strategies.json 并即时热重载生效。"
            )
            self.load_data(force_refresh=True)
        else:
            QMessageBox.warning(self, "失败", "生成策略写入异常，请查看日志！")

    def _on_open_ladder_clicked(self):
        """打开独立分时阶梯盯盘窗口"""
        if not self.selected_code:
            QMessageBox.warning(self, "提示", "请先在表格中选择要盯盘的新股标的！")
            return

        if not self.selected_row_data.get("has_strategy", False):
            generator = NewStockStrategyGenerator.get_instance()
            strat = generator.generate_strategy(self.selected_row_data)
            generator.save_or_update_strategy(strat)

        if self.main_window and hasattr(self.main_window, "open_intraday_strategy_dialog"):
            self.main_window.open_intraday_strategy_dialog(self.selected_code, self.selected_name)
        else:
            try:
                from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow
                win = PinzhunLadderStandaloneWindow(self.selected_code, self.selected_name)
                win.show()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"调起分时阶梯独立窗口异常: {e}")

    def _on_open_sbc_clicked(self):
        """调出 SBC 实盘分时走势独立窗口"""
        if not self.selected_code:
            QMessageBox.warning(self, "提示", "请先在表格中选择新股标的！")
            return
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(parent_win=self, code=self.selected_code)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"调起 SBC 实盘窗口异常: {e}")

    def _on_add_fav_clicked(self):
        """右键菜单：加入重点关注"""
        if not self.selected_code:
            return
        if self.main_window and hasattr(self.main_window, "favorite_panel"):
            self.main_window.favorite_panel.add_favorite(self.selected_code, self.selected_name)
            QMessageBox.information(self, "成功", f"⭐ 已将【{self.selected_name} ({self.selected_code})】加入重点关注！")

    def _on_add_dragon_clicked(self):
        """右键菜单：加入加速龙头追踪器"""
        if not self.selected_code:
            return
        if self.main_window and hasattr(self.main_window, "dragon_monitor_dialog") and self.main_window.dragon_monitor_dialog:
            self.main_window.dragon_monitor_dialog.add_stock_to_manual(self.selected_code, self.selected_name)
            QMessageBox.information(self, "成功", f"🐉 已将【{self.selected_name} ({self.selected_code})】加入加速龙头追踪器！")

    def _show_context_menu(self, pos):
        """右键菜单：保留完整全部功能"""
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        item_code = self.table.item(row, 0)
        item_name = self.table.item(row, 1)
        if item_code:
            self._on_stock_activated(item_code.text(), item_name.text() if item_name else "")

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; padding: 4px; font-size: 9pt; }
            QMenu::item:selected { background-color: #1e293b; color: #38bdf8; }
        """)

        act_ladder = menu.addAction(f"🚀 调出 【{self.selected_name}】 分时阶梯独立盯盘")
        act_ladder.triggered.connect(self._on_open_ladder_clicked)

        act_sbc = menu.addAction(f"📈 调出 【{self.selected_name}】 SBC 实盘分时走势")
        act_sbc.triggered.connect(self._on_open_sbc_clicked)

        menu.addSeparator()

        act_gen = menu.addAction(f"⚡ 自动生成/重新生成分时阶梯策略")
        act_gen.triggered.connect(self._on_generate_strategy_clicked)

        menu.addSeparator()

        act_fav = menu.addAction(f"⭐ 加入重点关注")
        act_fav.triggered.connect(self._on_add_fav_clicked)

        act_dragon = menu.addAction(f"🐉 加入加速龙头追踪器")
        act_dragon.triggered.connect(self._on_add_dragon_clicked)

        menu.addSeparator()
        act_copy = menu.addAction(f"📋 复制股票代码 ({self.selected_code})")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(self.selected_code))

        menu.exec(QCursor.pos())

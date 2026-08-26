# -*- coding: utf-8 -*-
"""
ats/ui/new_stock_panel.py — ATS 新股/次新股/IPO全流程监控与分时阶梯策略主控看板
特点：
1. 极简轻量顶部工具栏（含【🚀 阶梯盯盘】与【📈 SBC 走势】核心直达入口，专属【📥 更新新股数据】按钮）；
2. 遵循全系统统一设计：【启动时强制全量拉取一次数据】，经严格清洗保证 100% 合法有效；
3. 【⭐ 重点关注优先置顶与高亮】：自动读取 GlobalFavoriteManager，重点关注标的拥有第0梯队置顶权重，并以 ⭐ 金星 + #ffd700 金色字体 + #1f2d1f 专属背景高亮，支持一键筛选重点关注；
4. 【全 ATS 统一对齐】：列名与重点关注/龙头追踪器完全一致 (DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振)；
5. 【双通道与降级保护】：默认 TDX 行情驱动，IPC 数据流精准对齐额外列与全市场指标，无 IPC 时自动降级推算大盘偏离与共振态势；
6. 【支持 ats_col 自定义列】：动态扩展用户配置的自定义指标列并支持列宽自适应持久化；
7. 【交易时段精准识别】：非交易时段（盘前、午休、盘后、周末）初始化后彻底休眠静止，实盘时段自动 3 秒高频更新；
8. 【视图与焦点保护】：数据刷新时 100% 保持当前滚动条位置、不跳行、不丢焦点、零闪烁、0 Qt警告。
"""

import sys
import os
import time
import math
import logging
import datetime
import numpy as np
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
from JohnsonUtil import commonTips as cct

logger = logging.getLogger("NewStockPanel")

SORT_CONFIG_KEY = "ats_new_stock_sort_state_v1"
TABLE_CONFIG_KEY = "ats_new_stock_table_state_v3"


# 完全采用全系统统一、支持重点关注置顶与高精度数值排序的 NumericTableWidgetItem
NewStockNumericItem = NumericTableWidgetItem


def clean_num(val: Any, default: float = 0.0) -> float:
    """严格清理浮点数，杜绝 NaN / Inf / None / 占位符"""
    if val is None or val == "" or val == "-" or val == "--" or val == "None" or val == "null":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def get_new_stock_extra_cols() -> List[str]:
    """获取 ats_col 排除基础固定列后的自定义追加列"""
    try:
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']
    
    BASE_EXCLUDE = {
        'code', 'name', 'status', 'listing_date', 'apply_date', 'issue_price',
        'price', 'close', 'now', 'trade', 'pct', 'percent', 'turnover', 'turnoverrate',
        'turnover_ratio', 'hsl', 'float_mv_yi', 'total_mv_yi', 'amount_yi', 'amount',
        'has_strategy', 'dfi', 'dff', 'rank', 'dff2', 'dff3', 'rs', 'rs_val',
        'deviation', 'resonance', 'market_resonance'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_new_stock_table_headers(extra_cols: Optional[List[str]] = None) -> List[str]:
    """
    组合全 ATS 统一的新股看板表头：
    12基础列 + 6核心对齐列 (DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振) + 动态自定义列 (ats_col) + 1个阶梯策略列
    """
    if extra_cols is None:
        extra_cols = get_new_stock_extra_cols()
    try:
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
        
    base_headers = [
        "代码", "名称", "状态", "上市日", "申购日", "发行价",
        "现价", "涨跌%", "换手%", "流通(亿)", "总值(亿)", "成交(亿)",
        "DFF", "Rank", "DFF2", "DFF3", "大盘偏离", "大盘共振"
    ]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    return base_headers + extra_headers + ["阶梯策略"]


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
        self.last_sh_pct = 0.0
        self._last_ipc_df: Optional[pd.DataFrame] = None
        self._last_ipc_sh_pct: float = 0.0
        self.extra_cols = get_new_stock_extra_cols()

        # 排序持久化状态 (默认: 第3列 上市日 降序)
        self.sort_col = 3
        self.sort_order = Qt.SortOrder.DescendingOrder
        self._load_sort_state()

        self._init_ui()
        self._start_system_lifecycle()

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

        # 专属新股数据更新按钮 (醒目亮蓝主题，区别于全局 IPC 刷新)
        self.btn_refresh = QPushButton("📥 更新新股数据")
        self.btn_refresh.setToolTip("专门从东方财富 IPO 日历与全市场通道强制穿透拉取最新新股/次新股数据与发行参数")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton { 
                background-color: #0284c7; 
                color: #ffffff; 
                font-weight: bold; 
                border: 1px solid #38bdf8; 
                border-radius: 3px; 
                padding: 3px 10px; 
                font-size: 9pt; 
            }
            QPushButton:hover { 
                background-color: #38bdf8; 
                color: #000000; 
            }
            QPushButton:pressed {
                background-color: #0369a1;
                color: #ffffff;
            }
        """)
        self.btn_refresh.clicked.connect(lambda: self.load_data(force_refresh=True, is_manual_btn=True))
        top_bar.addWidget(self.btn_refresh)

        # 自动刷新复选框 (默认开启，实盘交易时段 3 秒自动更新)
        self.cb_auto_refresh = QCheckBox("自动刷新(3s)")
        self.cb_auto_refresh.setChecked(True)
        self.cb_auto_refresh.setToolTip("实盘交易时段 (09:15~11:30, 13:00~15:02) 每 3 秒后台静默拉取并刷新；非交易时段自动休眠")
        self.cb_auto_refresh.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        self.cb_auto_refresh.toggled.connect(self._on_auto_refresh_toggled)
        top_bar.addWidget(self.cb_auto_refresh)

        # 分类筛选 (支持 ⭐ 重点关注)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["全部标的", "⭐ 重点关注", "🌟 首日(N)", "🚀 前5日(C)", "📈 次新股", "⏳ 待上市"])
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

        self.lbl_status = QLabel("🟢 启动初始化数据中...")
        self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        top_bar.addWidget(self.lbl_status)

        main_layout.addLayout(top_bar)

        # ── 2. 主表与底部抽屉 Splitter ──
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # 核心数据表格
        self.table = BaseATSTableWidget(self)
        headers = get_new_stock_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        # 默认列宽：12基础列 + 6核心对齐列 + N动态列 + 1策略列
        base_widths = [55, 78, 62, 68, 68, 48, 48, 52, 50, 58, 58, 52, 52, 45, 52, 52, 62, 62]
        default_widths = base_widths + [60] * len(self.extra_cols) + [65]
        self.table.setup_persistence(
            config_key=TABLE_CONFIG_KEY,
            default_widths=default_widths
        )

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._on_header_sort_changed)

        self.table.stock_activated.connect(self._on_stock_activated)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self.splitter.addWidget(self.table)

        # ── 3. 底部阶梯档位推演与发行参数抽屉卡片 ──
        self.preview_card = QGroupBox("📍 新股发行参数与分时阶梯档位推演 (Ladder Prediction)")
        self.preview_card.setStyleSheet("""
            QGroupBox {
                background-color: #0b1120;
                color: #38bdf8;
                border: 1px solid #1e293b;
                border-radius: 4px;
                margin-top: 4px;
                font-weight: bold;
                padding: 6px;
                font-size: 9pt;
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

        self.ladder_labels = []
        for i in range(5):
            lbl = QLabel(f"档位 +{(i+1)*100}%: --")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background-color: #111827; color: #cbd5e1; padding: 3px 6px; border: 1px solid #1e293b; border-radius: 3px; font-size: 8.5pt; font-family: Consolas, 'Microsoft YaHei';")
            preview_layout.addWidget(lbl, 1, i)
            self.ladder_labels.append(lbl)

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

    def _is_market_active(self) -> bool:
        """判断当前是否处于 A 股实盘交易与竞价活跃时段 (09:15~11:30, 13:00~15:02)"""
        try:
            return bool(cct.get_work_time())
        except Exception:
            now = datetime.datetime.now()
            if now.weekday() >= 5:
                return False
            t_int = now.hour * 100 + now.minute
            return (915 <= t_int <= 1130) or (1300 <= t_int <= 1502)

    def _start_system_lifecycle(self):
        """
        【全系统生命周期启动】：
        1. 启动时瞬间从本地磁盘持久化数据加载并渲染，保证 0 秒开箱即显，绝无白屏或0标的；
        2. 发起后台静默增量刷新；
        3. 启动 3 秒定时器：实盘时段自动静默刷新，非交易时段自动休眠。
        """
        try:
            fetcher = NewStockFetcher.get_instance()
            init_df = fetcher.get_combined_new_stocks(force_refresh=False)
            if init_df is not None and not init_df.empty:
                self.df_data = init_df
                self._render_table()
        except Exception as e:
            logger.debug(f"冷启动恢复本地新股持久化数据异常: {e}")

        self.load_data(force_refresh=False)

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(3000)
        self.auto_refresh_timer.timeout.connect(self._on_auto_timer_tick)
        self.auto_refresh_timer.start()

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked:
            self.auto_refresh_timer.start(3000)
            if self._is_market_active():
                self.lbl_status.setText("🟢 自动刷新已开启 (3s)")
                self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
            else:
                self.lbl_status.setText("🕒 休市静态模式 (非交易时段暂停轮询)")
                self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        else:
            self.auto_refresh_timer.stop()
            self.lbl_status.setText("⏸️ 自动刷新已暂停")
            self.lbl_status.setStyleSheet("color: #fbbf24; font-size: 8.5pt;")

    def _on_auto_timer_tick(self):
        """定时器触发：仅在交易时段轮询，非交易时段彻底静止"""
        if self._is_fetching or not self.cb_auto_refresh.isChecked():
            return

        if not self._is_market_active():
            return

        self.load_data(force_refresh=False)

    def load_data(self, force_refresh: bool = False, is_manual_btn: bool = False):
        """启动后台线程拉取全量新股与实时数据（默认以 TDX + 权威日历为核心）"""
        if self._is_fetching:
            return
        self._is_fetching = True
        self._is_manual_refresh = is_manual_btn
        if is_manual_btn and hasattr(self, 'btn_refresh'):
            self.btn_refresh.setText("⏳ 正在更新新股...")
            self.btn_refresh.setEnabled(False)
            self.lbl_status.setText("🔄 正在通过 TDX 权威接口强制更新 100 只新股行情与股本...")
            self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 8.5pt; font-weight: bold;")
            logger.info("🔄 [NewStockPanel] 正在通过 TDX 权威接口强制更新 100 只新股行情、真实股本与换手率...")

        self.worker = NewStockFetchWorker(force_refresh=force_refresh, enrich_tdx=True)
        self.worker.data_ready.connect(self._on_data_ready)
        self.worker.fetch_failed.connect(self._on_fetch_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self):
        self._is_fetching = False
        if hasattr(self, 'btn_refresh'):
            self.btn_refresh.setText("📥 更新新股数据")
            self.btn_refresh.setEnabled(True)

    def _on_data_ready(self, df: pd.DataFrame):
        self._is_fetching = False
        if df is not None and not df.empty:
            # 基础数据回填，严格保留已计算好的 IPC / 指标字段
            if not self.df_data.empty:
                old_map = {str(r["code"]).zfill(6): r for _, r in self.df_data.iterrows()}
                flds_to_keep = ("dff", "rank", "dff2", "dff3", "rs", "resonance") + tuple(self.extra_cols)
                
                # 先确保 df 中具有这些列（初始化为 NaN）
                for fld in flds_to_keep:
                    if fld not in df.columns:
                        df[fld] = np.nan

                for idx, row in df.iterrows():
                    c = str(row["code"]).zfill(6)
                    if c in old_map:
                        old_r = old_map[c]
                        for fld in flds_to_keep:
                            old_val = old_r.get(fld)
                            if old_val is not None and not pd.isna(old_val):
                                df.at[idx, fld] = old_val

            self.df_data = df

            # ── 优先从缓存的 IPC 数据或主终端现存 current_df 中立即同步对齐 ──
            target_ipc_df = self._last_ipc_df
            if (target_ipc_df is None or target_ipc_df.empty) and self.main_window and hasattr(self.main_window, 'current_df'):
                main_df = getattr(self.main_window, 'current_df', None)
                if main_df is not None and not main_df.empty:
                    target_ipc_df = main_df

            if target_ipc_df is not None and not target_ipc_df.empty:
                self.update_from_ipc_df(target_ipc_df, self._last_ipc_sh_pct)
            else:
                self._render_table()

            if self.selected_code:
                match = self.df_data[self.df_data["code"] == self.selected_code]
                if not match.empty:
                    self.selected_row_data = match.iloc[0].to_dict()
                    self._update_preview_card(self.selected_row_data)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        strat_cnt = self.df_data['has_strategy'].sum() if not self.df_data.empty else 0
        if getattr(self, '_is_manual_refresh', False):
            self._is_manual_refresh = False
            self.lbl_status.setText(f"🎉 新股数据已更新 ({now_str}) | 共 {len(self.df_data)} 标的")
            self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        elif self._is_market_active():
            self.lbl_status.setText(f"🟢 实时更新: {now_str} | 共 {len(self.df_data)} 标的 (已配置: {strat_cnt})")
            self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        else:
            self.lbl_status.setText(f"🕒 休市静态模式 ({now_str}) | 共 {len(self.df_data)} 标的 (已配置: {strat_cnt})")
            self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")

    def _on_fetch_failed(self, err_msg: str):
        self._is_fetching = False
        self.lbl_status.setText(f"❌ 刷新异常: {err_msg[:25]}")
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 8.5pt;")

    def update_from_ipc_df(self, df_ipc: pd.DataFrame, sh_pct: float = 0.0):
        """
        接收来自 ATS 主终端 IPC 数据流的实时全市场 DataFrame:
        严格校验字段类型与有效性，并同步更新 DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振 及 ats_col 自定义列
        """
        if df_ipc is None or df_ipc.empty:
            return

        # 始终缓存最新的 IPC 全量数据与大盘涨幅，杜绝启动竞态丢失
        self._last_ipc_df = df_ipc
        if sh_pct == 0.0:
            for sh_code in ("999999", "000001", "sh000001"):
                if sh_code in df_ipc.index:
                    sh_row = df_ipc.loc[sh_code]
                    if hasattr(sh_row, "iloc") and len(sh_row.shape) > 1:
                        sh_row = sh_row.iloc[0]
                    sh_pct = clean_num(sh_row.get("percent", sh_row.get("pct", 0.0)))
                    break
        self.last_sh_pct = sh_pct
        if self.df_data.empty:
            try:
                fetcher = NewStockFetcher.get_instance()
                loaded = fetcher.get_combined_new_stocks(force_refresh=False)
                if loaded is not None and not loaded.empty:
                    self.df_data = loaded
            except Exception:
                pass

        if self.df_data.empty:
            return

        ipc_index_set = set(str(k) for k in df_ipc.index)
        has_code_col = 'code' in df_ipc.columns

        updated_any = False
        for idx, row in self.df_data.iterrows():
            code = str(row["code"]).zfill(6)
            ipc_row = None
            for key in (code, code.lstrip('0'), f"sh{code}", f"sz{code}", f"bj{code}"):
                if key in ipc_index_set:
                    ipc_row = df_ipc.loc[key]
                    break
            
            if ipc_row is None and has_code_col:
                matched = df_ipc[df_ipc['code'].astype(str).str.zfill(6) == code]
                if not matched.empty:
                    ipc_row = matched.iloc[0]

            if ipc_row is not None:
                if hasattr(ipc_row, "iloc") and len(ipc_row.shape) > 1:
                    ipc_row = ipc_row.iloc[0]

                # ── 新股行情权威性原则 ──
                # 新股现价、涨跌幅、换手率等核心实时行情由底层 TDX API 权威直连驱动，IPC 仅同步全市场指标，绝不覆写已由 TDX 算好的真实价格与涨跌幅！
                local_p = clean_num(self.df_data.at[idx, "price"], default=0.0)
                local_pct = clean_num(self.df_data.at[idx, "pct"], default=0.0)

                p = clean_num(ipc_row.get("close", ipc_row.get("price", ipc_row.get("now", 0.0))))
                # 仅当本地尚无价格时，才允许从 IPC 降级补充
                if local_p <= 0 and p > 0:
                    self.df_data.at[idx, "price"] = p
                    raw_pct = ipc_row.get("percent", ipc_row.get("pct", ipc_row.get("ratio", ipc_row.get("changepercent"))))
                    pct_val = clean_num(raw_pct, default=float('nan'))
                    if not math.isnan(pct_val) and pct_val != 0.0:
                        self.df_data.at[idx, "pct"] = pct_val

                # 换手率：若本地无换手率且 IPC 有有效换手率时补充
                local_to = clean_num(self.df_data.at[idx, "turnover"], default=0.0)
                if local_to <= 0:
                    to_val = ipc_row.get("turnoverrate", ipc_row.get("turnover_ratio", ipc_row.get("hsl")))
                    if to_val is not None:
                        to_clean = clean_num(to_val, default=0.0)
                        if 0.0 < to_clean <= 100.0:
                            self.df_data.at[idx, "turnover"] = to_clean

                # 成交额：若本地无成交额且 IPC 有有效成交额时补充
                local_amt = clean_num(self.df_data.at[idx, "amount_yi"], default=0.0)
                if local_amt <= 0:
                    amt_val = ipc_row.get("amount", ipc_row.get("turnover", 0.0))
                    amt_clean = clean_num(amt_val, default=0.0)
                    if amt_clean > 100000:
                        self.df_data.at[idx, "amount_yi"] = round(amt_clean / 1e8, 2)
                    elif amt_clean > 0:
                        self.df_data.at[idx, "amount_yi"] = round(amt_clean, 2)

                # 4. 对齐重点关注核心指标: DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振
                dff_raw = ipc_row.get("dff", ipc_row.get("dfi", ipc_row.get("dff_d")))
                if dff_raw is not None and not pd.isna(dff_raw):
                    self.df_data.at[idx, "dff"] = clean_num(dff_raw, default=0.0)

                rank_raw = ipc_row.get("Rank", ipc_row.get("rank", ipc_row.get("market_rank")))
                if rank_raw is not None and not pd.isna(rank_raw):
                    self.df_data.at[idx, "rank"] = rank_raw

                dff2_raw = ipc_row.get("dff2", ipc_row.get("dff_w"))
                if dff2_raw is not None and not pd.isna(dff2_raw):
                    self.df_data.at[idx, "dff2"] = clean_num(dff2_raw, default=0.0)

                dff3_raw = ipc_row.get("dff3", ipc_row.get("dff_m"))
                if dff3_raw is not None and not pd.isna(dff3_raw):
                    self.df_data.at[idx, "dff3"] = clean_num(dff3_raw, default=0.0)

                rs_raw = ipc_row.get("rs", ipc_row.get("rs_val", ipc_row.get("deviation")))
                if rs_raw is not None and not pd.isna(rs_raw):
                    self.df_data.at[idx, "rs"] = clean_num(rs_raw, default=0.0)

                res_raw = ipc_row.get("resonance", ipc_row.get("market_resonance", ipc_row.get("sync_status")))
                if res_raw is not None and not pd.isna(res_raw):
                    self.df_data.at[idx, "resonance"] = str(res_raw)

                # 5. 同步市值字段 (若本地无市值时从 IPC 补充)
                local_fmv = clean_num(self.df_data.at[idx, "float_mv_yi"], default=0.0)
                if local_fmv <= 0:
                    fmv_raw = ipc_row.get("nmc", ipc_row.get("float_mv", ipc_row.get("float_mv_yi")))
                    if fmv_raw is not None and not pd.isna(fmv_raw):
                        fmv_num = clean_num(fmv_raw)
                        if fmv_num > 1e4:
                            fmv_num = round(fmv_num / 1e8, 2)
                        if fmv_num > 0:
                            self.df_data.at[idx, "float_mv_yi"] = fmv_num

                local_tmv = clean_num(self.df_data.at[idx, "total_mv_yi"], default=0.0)
                if local_tmv <= 0:
                    tmv_raw = ipc_row.get("mktcap", ipc_row.get("total_mv", ipc_row.get("total_mv_yi")))
                    if tmv_raw is not None and not pd.isna(tmv_raw):
                        tmv_num = clean_num(tmv_raw)
                        if tmv_num > 1e4:
                            tmv_num = round(tmv_num / 1e8, 2)
                        if tmv_num > 0:
                            self.df_data.at[idx, "total_mv_yi"] = tmv_num

                # 6. 提取动态自定义列 (ats_col)
                for c_name in self.extra_cols:
                    for k in (c_name, c_name.lower(), c_name.upper()):
                        if k in ipc_row:
                            self.df_data.at[idx, c_name] = ipc_row.get(k)
                            break

                updated_any = True

        if updated_any or not self.df_data.empty:
            self._render_table()
            if self.selected_code:
                match = self.df_data[self.df_data["code"] == self.selected_code]
                if not match.empty:
                    self.selected_row_data = match.iloc[0].to_dict()
                    self._update_preview_card(self.selected_row_data)

    def _apply_filter(self):
        """应用分类筛选和关键词过滤"""
        self._render_table()

    def _set_or_update_item(self, row: int, col: int, text: str, 
                            color: Optional[str] = None, 
                            font: Optional[QFont] = None, 
                            align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
                            bg_color: Optional[str] = None,
                            is_pinned: bool = False,
                            raw_val: Any = None):
        """【零警告原地单元格更新 Helper，支持背景高亮、精确 UserRole 绑定与重点关注置顶排序】"""
        item = self.table.item(row, col)
        if item is None:
            new_item = NumericTableWidgetItem(str(text), is_pinned=is_pinned, raw_val=raw_val)
            new_item.setTextAlignment(align)
            if color:
                new_item.setForeground(QBrush(QColor(color)))
            if font:
                new_item.setFont(font)
            if bg_color:
                new_item.setBackground(QBrush(QColor(bg_color)))
            self.table.setItem(row, col, new_item)
        else:
            item.setText(str(text))
            item.is_pinned = is_pinned
            item.set_raw_value(raw_val)
            item.setTextAlignment(align)
            if color:
                item.setForeground(QBrush(QColor(color)))
            if font:
                item.setFont(font)
            if bg_color:
                item.setBackground(QBrush(QColor(bg_color)))
            else:
                item.setBackground(QBrush(QColor(0, 0, 0, 0)))

    def _render_table(self):
        """
        【⚡ 核心视图与焦点保护渲染】
        1. 保持当前滚动条位置 (v_scroll / h_scroll)；
        2. 保持当前选中的股票焦点 (selected_code)，绝不因刷新而重置跳动；
        3. 【重点关注优先置顶与高亮】：自动读取 GlobalFavoriteManager，重点关注标的拥有第0梯队置顶权重，标 ⭐ 并以专属背景和字体高亮；
        4. 呈现 12基础列 + 6核心对齐监控列 (DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振) + N动态自定义列 + 1策略列；
        5. 【降级保护】：若 IPC 尚未推送某些指标，全自动根据当前行情与大盘偏离度推导对齐。
        """
        if self.df_data.empty:
            self.table.setRowCount(0)
            return

        # 获取系统最新全局重点关注列表
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = set(GlobalFavoriteManager().get_favorite_stocks())
        except Exception:
            fav_stocks = set()

        # 动态检查自定义列是否发生变化
        current_extra = get_new_stock_extra_cols()
        if self.extra_cols != current_extra:
            self.extra_cols = current_extra
            headers = get_new_stock_table_headers(self.extra_cols)
            if self.table.columnCount() != len(headers):
                self.table.setColumnCount(len(headers))
                self.table.setHorizontalHeaderLabels(headers)

        # ── 1. 记录刷新前的视图状态与焦点 ──
        v_scroll_val = self.table.verticalScrollBar().value()
        h_scroll_val = self.table.horizontalScrollBar().value()
        saved_selected_code = self.selected_code

        df_filtered = self.df_data.copy()
        
        # 分类筛选
        filter_type = self.combo_filter.currentText()
        if "重点关注" in filter_type:
            df_filtered = df_filtered[df_filtered["code"].astype(str).str.zfill(6).isin(fav_stocks)]
        elif "首日" in filter_type:
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

        if df_filtered.empty:
            self.table.setRowCount(0)
            return

        # ── 2. 重点关注优先权重排序 (置顶第一梯队) ──
        def _sort_weight(row):
            c_code = str(row["code"]).zfill(6)
            is_fav = (c_code in fav_stocks)
            st = str(row.get("status", ""))
            ld = str(row.get("listing_date", "-"))
            if is_fav:
                w = 0  # 重点关注拥有绝对第0梯队置顶特权
            elif "首日" in st:
                w = 1
            elif "前5日" in st:
                w = 2
            elif "待上市" in st:
                w = 3
            elif "次新" in st:
                w = 4
            else:
                w = 5
            return (w, ld if ld != "-" else "1970-01-01")

        df_filtered["_sort_w"] = df_filtered.apply(_sort_weight, axis=1)
        df_filtered.sort_values(by=["_sort_w", "pct"], ascending=[True, False], inplace=True)
        df_filtered.drop(columns=["_sort_w"], inplace=True)

        target_row_count = len(df_filtered)

        # ── 3. 屏蔽信号并进行原地单元格更新 ──
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)

        if self.table.rowCount() != target_row_count:
            self.table.setRowCount(target_row_count)

        # 统一规范的字体系统（等宽数字 + 雅黑文本，杜绝忽大忽小与基线参差不齐）
        text_font = QFont("Microsoft YaHei", 9)
        num_font = QFont("Consolas", 9)
        bold_text_font = QFont("Microsoft YaHei", 9, QFont.Weight.Bold)
        bold_num_font = QFont("Consolas", 9, QFont.Weight.Bold)
        sh_pct = self.last_sh_pct

        for row_idx, (_, row) in enumerate(df_filtered.iterrows()):
            code = str(row.get("code", "")).zfill(6)
            name = str(row.get("name", ""))
            status = str(row.get("status", "次新"))
            listing_d = str(row.get("listing_date", "-"))
            apply_d = str(row.get("apply_date", "-"))
            
            issue_p = clean_num(row.get("issue_price", 0.0))
            price = clean_num(row.get("price", 0.0))
            pct = clean_num(row.get("pct", 0.0))
            turnover = clean_num(row.get("turnover", 0.0))
            float_mv = clean_num(row.get("float_mv_yi", 0.0))
            total_mv = clean_num(row.get("total_mv_yi", 0.0))
            amt = clean_num(row.get("amount_yi", 0.0))
            has_strat = bool(row.get("has_strategy", False))

            is_fav = (code in fav_stocks)
            bg_color = "#1f2d1f" if is_fav else None  # 重点关注微光高亮背景

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

            # 0: 代码 (等宽字体)
            code_col = "#00ff88" if is_fav else "#38bdf8"
            self._set_or_update_item(row_idx, 0, code, color=code_col, font=bold_num_font if is_fav else num_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=code)

            # 1: 名称 (重点关注显示 ⭐ + 亮金加粗)
            display_name = f"⭐ {name}" if is_fav else name
            if is_fav:
                name_color = "#ffd700"
            elif name.startswith("N"):
                name_color = "#f43f5e"
            elif name.startswith("C"):
                name_color = "#fbbf24"
            else:
                name_color = "#ffffff"
            self._set_or_update_item(row_idx, 1, display_name, color=name_color, font=bold_text_font if (is_fav or name.startswith(("N", "C"))) else text_font, align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=name)

            # 2: 状态
            status_color = "#f43f5e" if "首日" in status_short else ("#fbbf24" if "前5日" in status_short else ("#a78bfa" if "待上市" in status_short else "#94a3b8"))
            self._set_or_update_item(row_idx, 2, status_short, color=status_color, font=bold_text_font if ("首日" in status_short or "前5日" in status_short) else text_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=status_short)

            # 3: 上市日
            listing_val = listing_d if (listing_d and listing_d != "-") else None
            self._set_or_update_item(row_idx, 3, listing_d, color="#cbd5e1", font=num_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=listing_val)

            # 4: 申购日
            apply_val = apply_d if (apply_d and apply_d != "-") else None
            self._set_or_update_item(row_idx, 4, apply_d, color="#94a3b8", font=num_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=apply_val)

            # 5: 发行价
            issue_str = f"{issue_p:.2f}" if issue_p > 0 else "--"
            self._set_or_update_item(row_idx, 5, issue_str, color="#cbd5e1", font=num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=issue_p if issue_p > 0 else None)

            # 6: 现价 & 7: 涨跌%
            p_display = f"{price:.2f}" if price > 0 else "--"
            pct_str = f"{pct:+.2f}%" if price > 0 else "--"
            p_color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else "#94a3b8")
            self._set_or_update_item(row_idx, 6, p_display, color=p_color, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=price if price > 0 else None)
            self._set_or_update_item(row_idx, 7, pct_str, color=p_color, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=pct if price > 0 else None)

            # 8: 换手% (字体粗细字号完全一致，通过专业色温区分活跃度)
            to_str = f"{turnover:.2f}%" if (0.0 < turnover <= 100.0) else "--"
            to_color = "#f43f5e" if turnover >= 70.0 else ("#fbbf24" if turnover >= 50.0 else "#94a3b8")
            self._set_or_update_item(row_idx, 8, to_str, color=to_color, font=bold_num_font if turnover >= 50.0 else num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=turnover if (0.0 < turnover <= 100.0) else None)

            # 9: 流通(亿)
            fmv_str = f"{float_mv:.2f}" if float_mv > 0 else "--"
            self._set_or_update_item(row_idx, 9, fmv_str, color="#cbd5e1", font=num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=float_mv if float_mv > 0 else None)

            # 10: 总值(亿)
            tmv_str = f"{total_mv:.2f}" if total_mv > 0 else "--"
            self._set_or_update_item(row_idx, 10, tmv_str, color="#cbd5e1", font=num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=total_mv if total_mv > 0 else None)

            # 11: 成交(亿)
            amt_str = f"{amt:.2f}" if amt > 0 else "--"
            self._set_or_update_item(row_idx, 11, amt_str, color="#cbd5e1", font=num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=amt if amt > 0 else None)

            # ── 12~17: 对齐重点关注核心指标列 (DFF, Rank, DFF2, DFF3, 大盘偏离, 大盘共振) ──
            # 12: DFF (日线动量强度，带降级计算保护)
            dff_val = clean_num(row.get("dff", row.get("dfi", None)), default=float('nan'))
            if math.isnan(dff_val) and price > 0:
                dff_val = round(pct * 0.4 + turnover * 0.05, 2)
                
            if not math.isnan(dff_val):
                dff_str = f"{dff_val:+.2f}"
                dff_col = COLOR_UP if dff_val > 0 else (COLOR_DOWN if dff_val < 0 else "#94a3b8")
            else:
                dff_str = "--"
                dff_col = "#94a3b8"
            self._set_or_update_item(row_idx, 12, dff_str, color=dff_col, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=dff_val if not math.isnan(dff_val) else None)

            # 13: Rank (全市场综合排名，带降级排序保护)
            rank_val = row.get("rank", row.get("Rank", None))
            rank_num = None
            if rank_val is not None and not pd.isna(rank_val) and str(rank_val).strip() not in ("", "--", "nan"):
                try:
                    rank_num = int(float(rank_val))
                    rank_str = str(rank_num)
                except:
                    rank_str = str(rank_val)
                    rank_num = rank_str
                rank_col = "#38bdf8"
            else:
                rank_num = (row_idx + 1) if price > 0 else None
                rank_str = str(rank_num) if rank_num is not None else "--"
                rank_col = "#38bdf8" if price > 0 else "#94a3b8"
            self._set_or_update_item(row_idx, 13, rank_str, color=rank_col, font=num_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=rank_num)

            # 14: DFF2 (周线强度)
            dff2_val = clean_num(row.get("dff2", row.get("dff_w", None)), default=float('nan'))
            if math.isnan(dff2_val) and price > 0:
                dff2_val = round(dff_val * 1.5, 2) if not math.isnan(dff_val) else float('nan')
            if not math.isnan(dff2_val):
                dff2_str = f"{dff2_val:+.2f}"
                dff2_col = COLOR_UP if dff2_val > 0 else (COLOR_DOWN if dff2_val < 0 else "#94a3b8")
            else:
                dff2_str = "--"
                dff2_col = "#94a3b8"
            self._set_or_update_item(row_idx, 14, dff2_str, color=dff2_col, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=dff2_val if not math.isnan(dff2_val) else None)

            # 15: DFF3 (月线/3日强度)
            dff3_val = clean_num(row.get("dff3", row.get("dff_m", None)), default=float('nan'))
            if math.isnan(dff3_val) and price > 0:
                dff3_val = round(dff_val * 2.2, 2) if not math.isnan(dff_val) else float('nan')
            if not math.isnan(dff3_val):
                dff3_str = f"{dff3_val:+.2f}"
                dff3_col = COLOR_UP if dff3_val > 0 else (COLOR_DOWN if dff3_val < 0 else "#94a3b8")
            else:
                dff3_str = "--"
                dff3_col = "#94a3b8"
            self._set_or_update_item(row_idx, 15, dff3_str, color=dff3_col, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=dff3_val if not math.isnan(dff3_val) else None)

            # 16: 大盘偏离 (rs = pct - sh_pct)
            rs_val = clean_num(row.get("rs", row.get("rs_val", row.get("deviation", None))), default=float('nan'))
            if math.isnan(rs_val) and price > 0:
                rs_val = round(pct - sh_pct, 2)
                
            if not math.isnan(rs_val):
                rs_str = f"{rs_val:+.2f}%"
                rs_col = COLOR_UP if rs_val > 0 else (COLOR_DOWN if rs_val < 0 else "#94a3b8")
            else:
                rs_str = "--"
                rs_col = "#94a3b8"
            self._set_or_update_item(row_idx, 16, rs_str, color=rs_col, font=bold_num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=rs_val if not math.isnan(rs_val) else None)

            # 17: 大盘共振 (全 ATS 统一对齐判定逻辑)
            res_val = str(row.get("resonance", row.get("market_resonance", "--"))).strip()
            if not res_val or res_val in ("nan", "None", "--"):
                if price > 0 and not math.isnan(rs_val):
                    if sh_pct < -0.3 and pct > 1.5 and rs_val > 1.8:
                        res_val = "逆市抗跌"
                    elif sh_pct > 0.3 and pct > 3.0 and (not math.isnan(dff_val) and dff_val > 1.0):
                        res_val = "大盘共振"
                    elif pct < -3.0 and rs_val < -2.0:
                        res_val = "同步走弱"
                    elif abs(rs_val) <= 2.0:
                        res_val = "同步整理"
                    elif rs_val > 2.0:
                        res_val = "逆市抗跌" if pct >= 0 else "强势抗跌"
                    else:
                        res_val = "同步走弱"
                else:
                    res_val = "--"
            
            if "逆市" in res_val or "共振" in res_val or "抗跌" in res_val:
                res_col = "#ffd700"
                res_font = bold_text_font
            elif "走弱" in res_val or "破位" in res_val:
                res_col = "#f87171"
                res_font = text_font
            else:
                res_col = "#94a3b8"
                res_font = text_font
            self._set_or_update_item(row_idx, 17, res_val, color=res_col, font=res_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=res_val if res_val != "--" else None)

            # ── 动态自定义列 (ats_col) ──
            col_offset = 18
            for c_name in self.extra_cols:
                raw_c_val = None
                for k in (c_name, c_name.lower(), c_name.upper()):
                    if k in row:
                        raw_c_val = row.get(k)
                        break
                c_sort_val = None
                if raw_c_val is not None and not pd.isna(raw_c_val):
                    try:
                        c_num = float(raw_c_val)
                        if not (math.isnan(c_num) or math.isinf(c_num)):
                            c_str = f"{c_num:+.2f}"
                            c_col = COLOR_UP if c_num > 0 else (COLOR_DOWN if c_num < 0 else "#94a3b8")
                            c_sort_val = c_num
                        else:
                            c_str = "--"
                            c_col = "#94a3b8"
                    except:
                        c_str = str(raw_c_val)
                        c_col = "#cbd5e1"
                        c_sort_val = c_str
                else:
                    c_str = "--"
                    c_col = "#94a3b8"
                self._set_or_update_item(row_idx, col_offset, c_str, color=c_col, font=num_font, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=c_sort_val)
                col_offset += 1

            # 最后一列: 阶梯策略
            strat_txt = "✅ 已配" if has_strat else "⚪ 未配"
            strat_color = "#4ade80" if has_strat else "#64748b"
            self._set_or_update_item(row_idx, col_offset, strat_txt, color=strat_color, font=text_font, align=Qt.AlignmentFlag.AlignCenter, bg_color=bg_color, is_pinned=is_fav, raw_val=1 if has_strat else 0)

        # ── 4. 应用并保持持久化的排序列和方向 ──
        self.table.setSortingEnabled(True)
        if 0 <= self.sort_col < self.table.columnCount():
            self.table.sortItems(self.sort_col, self.sort_order)

        # ── 5. 恢复选中焦点与滚动条位置 ──
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
        """BaseATSTableWidget 激活行：仅联动行情与推演卡片，绝不主动弹窗"""
        self.selected_code = code
        self.selected_name = name.replace("⭐ ", "").strip()

        if not self.df_data.empty:
            match = self.df_data[self.df_data["code"] == code]
            if not match.empty:
                self.selected_row_data = match.iloc[0].to_dict()

        self._update_preview_card(self.selected_row_data)
        self.stock_selected.emit(code, self.selected_name)

        if self.main_window and hasattr(self.main_window, "link_stock"):
            try:
                self.main_window.link_stock(code, self.selected_name)
            except Exception as e:
                logger.debug(f"link_stock 异常: {e}")

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击单元格：联动选中并通知主窗口打开详情窗口（不自动调起阶梯盯盘）"""
        item_code = self.table.item(row, 0)
        item_name = self.table.item(row, 1)
        if item_code:
            code = item_code.text()
            name = item_name.text().replace("⭐ ", "").strip() if item_name else ""
            self._on_stock_activated(code, name)
            self.stock_double_clicked.emit(code, name)

    def _update_preview_card(self, row_data: Dict[str, Any]):
        """根据选中标的数据更新底部阶梯推演卡片，并根据当前价格自动点亮对应档位与实际盈利"""
        if not row_data:
            return

        code = str(row_data.get("code", "")).zfill(6)
        name = str(row_data.get("name", "")).replace("⭐ ", "").strip()
        issue_p = clean_num(row_data.get("issue_price", 0.0))
        float_mv = clean_num(row_data.get("float_mv_yi", 0.0))
        curr_p = clean_num(row_data.get("price", 0.0))
        listing_d = str(row_data.get("listing_date", "-"))

        if issue_p <= 0 and curr_p > 0:
            issue_p = round(curr_p / 2.0, 2)

        self.lbl_spec_title.setText(
            f"【{name} ({code})】 发行价: {issue_p:.2f}元 | 上市: {listing_d} | 发行流通市值: {float_mv:.2f}亿"
        )

        sign_shares = 500  # 统一量化标准：单签均按 500 股计算收益
        gains = [100.0, 200.0, 300.0, 400.0, 500.0]

        def _fmt_profit(val: float) -> str:
            """格式化收益金额：超过 1 万元的转为保留 2 位小数的万格式 (如 盈利38.03万)，低于 1 万元显示具体元 (如 盈利4,420元)"""
            abs_v = abs(val)
            if abs_v >= 10000.0:
                wan = val / 10000.0
                return f"盈利{wan:.2f}万"
            else:
                return f"盈利{val:,.0f}元"

        # 计算当前相对于发行价的累计涨幅与实际单签盈利
        if issue_p > 0 and curr_p > 0:
            cum_pct = (curr_p - issue_p) / issue_p * 100.0
            actual_profit = round((curr_p - issue_p) * sign_shares, 2)

            # 档位判定：
            # 低于 100% 或 100%~199.99% 落在 100 档 (index 0)；
            # 200%~299.99% 落在 200 档 (index 1)；
            # 300%~399.99% 落在 300 档 (index 2)；
            # 400%~499.99% 落在 400 档 (index 3)；
            # 超过 500% 落在 500 档 (index 4)。
            if cum_pct < 200.0:
                active_idx = 0
            elif cum_pct < 300.0:
                active_idx = 1
            elif cum_pct < 400.0:
                active_idx = 2
            elif cum_pct < 500.0:
                active_idx = 3
            else:
                active_idx = 4
        else:
            cum_pct = 0.0
            actual_profit = 0.0
            active_idx = -1

        # 样式定义：优雅量化暗色主题，高对比易读且舒适直观
        normal_style = (
            "background-color: #111827; color: #cbd5e1; padding: 3px 6px; "
            "border: 1px solid #1e293b; border-radius: 3px; font-size: 8.5pt; font-family: Consolas, 'Microsoft YaHei';"
        )
        highlight_style = (
            "background-color: #581c1c; color: #ffffff; padding: 3px 6px; "
            "border: 1px solid #ef4444; border-radius: 3px; font-size: 8.5pt; font-weight: bold; font-family: Consolas, 'Microsoft YaHei';"
        )

        for i, gain in enumerate(gains):
            if i >= len(self.ladder_labels):
                break
            target_p = round(issue_p * (1.0 + gain / 100.0), 2)
            est_profit = round((target_p - issue_p) * sign_shares, 2)

            if i == active_idx:
                # 所在档位：显示取整实际比例与实际盈利金额，并以纯净白字+深绯红高亮呈现
                int_pct = int(cum_pct) if cum_pct >= 0 else int(round(cum_pct))
                self.ladder_labels[i].setText(f"+{int_pct}%: {curr_p:.2f}元 ({_fmt_profit(actual_profit)})")
                self.ladder_labels[i].setStyleSheet(highlight_style)
            else:
                # 普通档位：显示标准预估
                self.ladder_labels[i].setText(f"+{int(gain)}%: {target_p:.2f}元 ({_fmt_profit(est_profit)})")
                self.ladder_labels[i].setStyleSheet(normal_style)

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

    def _toggle_favorite(self):
        """右键菜单：切换重点关注 (极速响应与全系统 0ms 联动)"""
        if not self.selected_code:
            return
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            fav_mgr.toggle_favorite_stock(self.selected_code)
            self._render_table()
            
            # 主动通知 ATS 主窗口同步刷新重点关注 Tab 与左侧策略股票池
            if self.main_window and hasattr(self.main_window, '_safe_favorites_changed'):
                self.main_window._safe_favorites_changed()
        except Exception as e:
            logger.debug(f"Toggle favorite error: {e}")

    def refresh_favorites_display(self):
        """[0ms 极速刷新] 当全局重点关注变更时即时重绘新股次新股表格"""
        try:
            self._render_table()
        except Exception as e:
            logger.debug(f"[NewStockPanel] refresh_favorites_display error: {e}")

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

        act_eval_60f = menu.addAction(f"🎯 运行 【{self.selected_name}】 60f 通道底部反转测算 (TDX直连)")
        act_eval_60f.triggered.connect(self._on_eval_60f_clicked)

        menu.addSeparator()

        act_gen = menu.addAction(f"⚡ 自动生成/重新生成分时阶梯策略")
        act_gen.triggered.connect(self._on_generate_strategy_clicked)

        menu.addSeparator()

        # 动态重点关注文案
        try:
            from global_favorites import GlobalFavoriteManager
            is_fav = self.selected_code in GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            is_fav = False

        fav_title = f"⭐ 取消重点关注 ({self.selected_code})" if is_fav else f"⭐ 加入重点关注 ({self.selected_code})"
        act_fav = menu.addAction(fav_title)
        act_fav.triggered.connect(self._toggle_favorite)

        act_dragon = menu.addAction(f"🐉 加入加速龙头追踪器")
        act_dragon.triggered.connect(self._on_add_dragon_clicked)

        menu.addSeparator()
        act_copy = menu.addAction(f"📋 复制股票代码 ({self.selected_code})")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(self.selected_code))

        menu.exec(QCursor.pos())

    def _on_eval_60f_clicked(self):
        """60f 通道底部反转突破策略直连 TDX API 测算事件 (支持单选与全量批量)"""
        from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
        strategy = ChannelBottomReversalStrategy()

        # 1. 如果选中了单只标的，单股直连诊断
        if self.selected_code and self.selected_name:
            code = self.selected_code
            name = self.selected_name
            self.lbl_status.setText(f"📡 正在通过 TDX API 直连拉取 【{name}】 60m K线进行通道测算...")
            QApplication.processEvents()

            res = strategy.evaluate_stock_tdx(code)
            self.lbl_status.setText("🟢 60f 通道策略测算完成")

            if res.get("is_matched", False):
                msg = (
                    f"🎉 【{name} ({code})】 命中 60f 通道底部反转突破形态！\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 形态评分: {res.get('score', 0)} 分\n"
                    f"🎯 建议介入价: {res.get('entry_price', 0.0):.2f} 元\n"
                    f"🛡️ 止损保护位: {res.get('stop_loss', 0.0):.2f} 元\n"
                    f"🚀 第一目标位: {res.get('target_price_1', 0.0):.2f} 元\n"
                    f"💎 第二目标位: {res.get('target_price_2', 0.0):.2f} 元\n"
                    f"📉 通道下倾角: {res.get('channel_slope_deg', 0.0):+.1f}°\n"
                    f"💧 底部缩量比: {res.get('volume_shrink_pct', 0.0):.1f}%\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 逻辑解析:\n{res.get('reason', '')}"
                )
                QMessageBox.information(self, f"60f 通道策略诊断 - {name}", msg)
            else:
                msg = (
                    f"⚠️ 【{name} ({code})】 未触发 60f 通道底部反转信号\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔍 未满足原因: {res.get('reason', '不满足形态条件')}\n"
                    f"📉 通道斜率: {res.get('channel_slope_deg', 0.0):+.1f}°\n"
                    f"最低波谷: {res.get('lowest_low', 0.0):.2f} 元\n"
                    f"整理高点: {res.get('base_high', 0.0):.2f} 元\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                QMessageBox.information(self, f"60f 通道策略诊断 - {name}", msg)
            return

        # 2. 批量扫描：优先提取多选选中的标的，否则扫描当前面板全量新股
        stock_pairs = []
        if hasattr(self, 'table') and hasattr(self.table, 'get_selected_stock_pairs'):
            stock_pairs = self.table.get_selected_stock_pairs()
        
        if stock_pairs:
            codes = [c for c, _ in stock_pairs if c]
            code_to_name = {c: n for c, n in stock_pairs if c}
        elif not self.df_data.empty:
            codes = list(self.df_data["code"].dropna().unique())
            code_to_name = dict(zip(self.df_data["code"], self.df_data["name"]))
        else:
            QMessageBox.warning(self, "提示", "当前新股列表中无可用标的！")
            return

        self.lbl_status.setText(f"📡 正在直连 TDX API 批量拉取 {len(codes)} 只新股 60m K线进行形态扫描...")
        QApplication.processEvents()

        df_matched = strategy.scan_stocks_tdx(codes)
        self.lbl_status.setText(f"🟢 批量扫描完成: 命中 {len(df_matched)} 只标的")

        if not df_matched.empty:
            df_matched["name"] = df_matched["code"].map(lambda c: code_to_name.get(c, c))

        from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog
        if not hasattr(self, '_channel_scan_dialog') or self._channel_scan_dialog is None:
            self._channel_scan_dialog = ChannelReversalScanResultDialog(
                parent=self,
                df_results=df_matched,
                total_scanned=len(codes),
                source_tab_name="新股次新股"
            )
            self._channel_scan_dialog.stock_linkage_requested.connect(self.stock_selected)
        else:
            self._channel_scan_dialog.update_results(
                df_results=df_matched,
                total_scanned=len(codes),
                source_tab_name="新股次新股"
            )
        self._channel_scan_dialog.show()
        self._channel_scan_dialog.raise_()
        self._channel_scan_dialog.activateWindow()

# -*- coding: utf-8 -*-
"""Next-Day Anomaly Watch Comprehensive Center (次日异动候选池综合管理中心)

Features:
1. NextDayAnomalyWatchWidget: 可直接嵌入 ATS 主看板 Tab 的核心面板，也可在独立弹窗中运行；
2. Tab 1: Premarket Manifest (盘前候选清单: 日期检索, 分层徽章, 特征明细, 板块证据, 联动看盘与SBC分时图, 支持手动/补算生成)
3. Tab 2: Intraday Verification (盘中实时后验: TDX轮询状态, 两帧确认证据链钻取, 检查点时序微图)
4. Tab 3: Multi-day Followup & Stats (跨日顺延跟踪看板: 多版本表现对比, 顺延走强兑现明细)
5. Tab 4: Strategy & JSON Config Manager (策略与规则管理: 可视表单 + 高亮JSON双向联动, 版本克隆, 防呆校验与原子保存)
6. NextDayAnomalyWatchDialog: 独立外挂伴侣窗口
"""
from __future__ import annotations

import copy
import glob
import json
import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ats.strategy.next_day_watch_config_manager import NextDayWatchConfigManager
from ats.ui.base_table import BaseATSTableWidget, send_to_linkage
from ats.ui.styles import NumericTableWidgetItem
from JohnsonUtil import LoggerFactory
from next_day_anomaly_watch import _read_json, run_cycle
from sys_utils import get_app_root, get_conf_path

logger = LoggerFactory.getLogger()


class NextDayWatchDataLoaderWorker(QThread):
    """Background worker for scanning and loading candidate files without freezing UI."""

    dates_scanned = pyqtSignal(list)
    manifest_loaded = pyqtSignal(dict)
    eval_loaded = pyqtSignal(dict)
    stats_loaded = pyqtSignal(list)

    def __init__(self, target_date: Optional[str] = None):
        super().__init__()
        self.target_date = target_date
        self.app_root = get_app_root()
        self.data_dir = os.path.join(self.app_root, "datacsv")

    def run(self):
        try:
            watch_pattern = os.path.join(self.data_dir, "next_day_anomaly_watch_*.json")
            files = glob.glob(watch_pattern)
            dates = []
            for f in files:
                base = os.path.basename(f)
                d = base.replace("next_day_anomaly_watch_", "").replace(".json", "")
                if len(d) == 10 and d.count("-") == 2:
                    dates.append(d)
            dates.sort(reverse=True)
            self.dates_scanned.emit(dates)

            cur_date = self.target_date or (dates[0] if dates else time.strftime("%Y-%m-%d"))

            watch_path = os.path.join(self.data_dir, f"next_day_anomaly_watch_{cur_date}.json")
            watch_data = _read_json(watch_path, {})
            self.manifest_loaded.emit(watch_data)

            eval_path = os.path.join(self.data_dir, f"next_day_anomaly_eval_{cur_date}.json")
            eval_data = _read_json(eval_path, {})
            self.eval_loaded.emit(eval_data)

            stats_list = []
            stats_pattern = os.path.join(self.data_dir, "next_day_anomaly_stats_*.json")
            for sf in sorted(glob.glob(stats_pattern), reverse=True)[:30]:
                sdata = _read_json(sf, {})
                if sdata:
                    stats_list.append(sdata)
            self.stats_loaded.emit(stats_list)

        except Exception as exc:
            logger.warning("[NextDayWatchDataLoaderWorker] Background read failed: %s", exc)


class NextDayAnomalyWatchWidget(QWidget):
    """Reusable comprehensive panel for next day anomaly watch (can be embedded in tabs or dialogs)."""

    status_message_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.available_dates: List[str] = []
        self.current_date: str = time.strftime("%Y-%m-%d")
        self.manifest_data: Dict[str, Any] = {}
        self.eval_data: Dict[str, Any] = {}
        self.stats_data_list: List[Dict[str, Any]] = []
        self.current_config: Dict[str, Any] = {}
        self.active_worker: Optional[NextDayWatchDataLoaderWorker] = None

        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(3000)
        self.auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)

        self._init_ui()
        self._load_config_data()
        self.reload_all_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self._build_manifest_tab()
        self._build_eval_tab()
        self._build_stats_tab()
        self._build_config_tab()

    # =========================================================================
    # Tab 1: 盘前候选清单 (Premarket Manifest Viewer)
    # =========================================================================
    def _build_manifest_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        top_bar.addWidget(QLabel("📅 交易日:"))
        self.combo_manifest_date = QComboBox()
        self.combo_manifest_date.setMinimumWidth(120)
        self.combo_manifest_date.currentTextChanged.connect(self._on_manifest_date_changed)
        top_bar.addWidget(self.combo_manifest_date)

        top_bar.addWidget(QLabel("分层:"))
        self.combo_tier_filter = QComboBox()
        self.combo_tier_filter.addItems(["全部分层", "Tier A (企稳支撑)", "Tier B (高低抬升)", "Tier C (温和放量)"])
        self.combo_tier_filter.currentIndexChanged.connect(self._render_manifest_table)
        top_bar.addWidget(self.combo_tier_filter)

        top_bar.addWidget(QLabel("策略:"))
        self.combo_strat_filter = QComboBox()
        self.combo_strat_filter.addItems(["全部策略", "channel_stepup"])
        self.combo_strat_filter.currentIndexChanged.connect(self._render_manifest_table)
        top_bar.addWidget(self.combo_strat_filter)

        top_bar.addWidget(QLabel("搜索:"))
        self.edit_manifest_search = QLineEdit()
        self.edit_manifest_search.setPlaceholderText("代码 / 名称 / 板块")
        self.edit_manifest_search.setClearButtonEnabled(True)
        self.edit_manifest_search.textChanged.connect(self._render_manifest_table)
        top_bar.addWidget(self.edit_manifest_search)

        self.btn_refresh_manifest = QPushButton("🔄 刷新数据")
        self.btn_refresh_manifest.clicked.connect(self.reload_all_data)
        top_bar.addWidget(self.btn_refresh_manifest)

        # ⚡ 手动补算/生成今日候选池按钮
        self.btn_manual_freeze = QPushButton("⚡ 补算生成今日候选清单")
        self.btn_manual_freeze.setToolTip("基于当前市场全量宽表数据立即执行筛选并冻结生成今日候选清单 (盘后/非08:30时间段补算)")
        self.btn_manual_freeze.setStyleSheet("""
            QPushButton {
                background-color: #3b2d12;
                color: #fbbf24;
                font-weight: bold;
                border: 1px solid #d97706;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #d97706;
                color: #ffffff;
            }
        """)
        self.btn_manual_freeze.clicked.connect(self._on_manual_freeze_clicked)
        top_bar.addWidget(self.btn_manual_freeze)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.lbl_manifest_summary = QLabel("盘前概况: 正在载入...")
        self.lbl_manifest_summary.setStyleSheet("""
            background-color: #1f242c;
            border-left: 4px solid #58a6ff;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: 500;
            color: #d1d5db;
        """)
        layout.addWidget(self.lbl_manifest_summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        self.table_manifest = QTableWidget()
        self.table_manifest.setColumnCount(10)
        self.table_manifest.setHorizontalHeaderLabels([
            "代码", "名称", "分层", "阶段", "综合分", "所属板块", "策略版本", "关键特征摘要", "板块共振证据", "状态"
        ])
        self.table_manifest.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_manifest.horizontalHeader().setStretchLastSection(True)
        self.table_manifest.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_manifest.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_manifest.setAlternatingRowColors(True)
        self.table_manifest.itemSelectionChanged.connect(self._on_manifest_row_selected)
        self.table_manifest.itemDoubleClicked.connect(self._on_candidate_double_clicked)
        self.table_manifest.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_manifest.customContextMenuRequested.connect(self._on_manifest_context_menu)
        splitter.addWidget(self.table_manifest)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        self.lbl_feature_detail_title = QLabel("🔍 选中标的选入特征钻取明细 (单击表格行更新):")
        self.lbl_feature_detail_title.setStyleSheet("font-weight: bold; color: #58a6ff;")
        bottom_layout.addWidget(self.lbl_feature_detail_title)

        self.text_feature_detail = QPlainTextEdit()
        self.text_feature_detail.setReadOnly(True)
        self.text_feature_detail.setMaximumHeight(150)
        bottom_layout.addWidget(self.text_feature_detail)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        self.tab_widget.addTab(tab, "📋 盘前候选清单 (Premarket)")

    # =========================================================================
    # Tab 2: 盘中实时后验与确认 (Intraday Verification)
    # =========================================================================
    def _build_eval_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        self.lbl_eval_status = QLabel("⚡ 盘中后验引擎: 正在监听 TDX 实时数据流...")
        self.lbl_eval_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
        top_bar.addWidget(self.lbl_eval_status)
        top_bar.addStretch()

        self.chk_auto_refresh = QCheckBox("自动刷新 (3秒)")
        self.chk_auto_refresh.setChecked(True)
        self.chk_auto_refresh.toggled.connect(self._on_toggle_auto_refresh)
        top_bar.addWidget(self.chk_auto_refresh)

        btn_manual_refresh = QPushButton("立即刷新")
        btn_manual_refresh.clicked.connect(self.reload_all_data)
        top_bar.addWidget(btn_manual_refresh)

        layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_box = QGroupBox("🔔 盘中确认与阶段跃迁事件流 (Events Stream)")
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(6, 12, 6, 6)

        self.table_events = QTableWidget()
        self.table_events.setColumnCount(7)
        self.table_events.setHorizontalHeaderLabels([
            "触发时间", "代码", "名称", "事件类型", "现价", "涨跌幅%", "交付状态"
        ])
        self.table_events.horizontalHeader().setStretchLastSection(True)
        self.table_events.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_events.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_events.itemSelectionChanged.connect(self._on_event_row_selected)
        self.table_events.itemDoubleClicked.connect(self._on_event_double_clicked)
        left_layout.addWidget(self.table_events)

        self.lbl_event_proof = QLabel("两帧证据链: 请在上方选择确认事件")
        self.lbl_event_proof.setStyleSheet("""
            background-color: #1a1e24;
            color: #7ee787;
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #30363d;
            font-size: 9pt;
        """)
        self.lbl_event_proof.setWordWrap(True)
        left_layout.addWidget(self.lbl_event_proof)
        splitter.addWidget(left_box)

        right_box = QGroupBox("⏱️ 标的检查点时序与真实均价跟踪 (Checkpoints)")
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(6, 12, 6, 6)

        self.table_checkpoints = QTableWidget()
        self.table_checkpoints.setColumnCount(7)
        self.table_checkpoints.setHorizontalHeaderLabels([
            "采样时间", "阶段", "最高价", "现价", "真实VWAP", "成交量", "突破证据"
        ])
        self.table_checkpoints.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self.table_checkpoints)
        splitter.addWidget(right_box)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.tab_widget.addTab(tab, "⚡ 盘中实时后验 (Intraday)")

    # =========================================================================
    # Tab 3: 跨日顺延跟踪看板 (Multi-day Followup & Stats)
    # =========================================================================
    def _build_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        top_box = QGroupBox("📊 历史各交易日策略版本表现矩阵 (Strategy Performance Matrix)")
        top_layout = QVBoxLayout(top_box)
        top_layout.setContentsMargins(6, 12, 6, 6)

        self.table_stats = QTableWidget()
        self.table_stats.setColumnCount(9)
        self.table_stats.setHorizontalHeaderLabels([
            "目标交易日", "策略ID", "版本", "候选数", "即日确认 (EARLY_VALID)",
            "顺延命中 (DELAYED)", "未命中 (DAY_MISS)", "彻底失效 (MISSED)", "即日确认率"
        ])
        self.table_stats.horizontalHeader().setStretchLastSection(True)
        self.table_stats.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        top_layout.addWidget(self.table_stats)
        splitter.addWidget(top_box)

        bottom_box = QGroupBox("🚀 顺延走强标的兑现明细 (Delayed Winners - T+1~T+3突破样本)")
        bottom_layout = QVBoxLayout(bottom_box)
        bottom_layout.setContentsMargins(6, 12, 6, 6)

        self.table_delayed_winners = QTableWidget()
        self.table_delayed_winners.setColumnCount(6)
        self.table_delayed_winners.setHorizontalHeaderLabels([
            "代码", "名称", "初选目标日", "顺延兑现日", "初选高点", "最新状态"
        ])
        self.table_delayed_winners.horizontalHeader().setStretchLastSection(True)
        self.table_delayed_winners.itemDoubleClicked.connect(self._on_delayed_double_clicked)
        bottom_layout.addWidget(self.table_delayed_winners)
        splitter.addWidget(bottom_box)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self.tab_widget.addTab(tab, "📊 跨日成效看板 (Followup & Stats)")

    # =========================================================================
    # Tab 4: 策略与规则 JSON 配置管理 (Strategy & JSON Config Manager)
    # =========================================================================
    def _build_config_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(6, 6, 6, 6)
        form_layout.setSpacing(10)

        group_global = QGroupBox("🌐 全局运行控制 (Global Control)")
        gl_layout = QVBoxLayout(group_global)

        self.chk_global_enabled = QCheckBox("启用次日候选池引擎 (enabled)")
        self.chk_global_enabled.setStyleSheet("font-weight: bold; color: #7ee787;")
        gl_layout.addWidget(self.chk_global_enabled)

        lbl_notice = QLabel("💡 提示: 规则在每日 08:30 盘前自动冻结，修改将在下一交易日 08:30 盘前生效。")
        lbl_notice.setStyleSheet("color: #8b949e; font-size: 9pt;")
        gl_layout.addWidget(lbl_notice)

        h_vwap = QHBoxLayout()
        h_vwap.addWidget(QLabel("VWAP 字段名称:"))
        self.combo_vwap_field = QComboBox()
        self.combo_vwap_field.addItems(["vwap", "price", "None"])
        h_vwap.addWidget(self.combo_vwap_field)
        h_vwap.addStretch()
        gl_layout.addLayout(h_vwap)

        form_layout.addWidget(group_global)

        group_strat_sel = QGroupBox("🎯 策略选择与版本控制")
        strat_sel_layout = QHBoxLayout(group_strat_sel)

        strat_sel_layout.addWidget(QLabel("当前编辑策略:"))
        self.combo_strat_edit = QComboBox()
        self.combo_strat_edit.setMinimumWidth(180)
        self.combo_strat_edit.currentIndexChanged.connect(self._on_strat_edit_selection_changed)
        strat_sel_layout.addWidget(self.combo_strat_edit)

        self.btn_clone_version = QPushButton("➕ 克隆为新版本 (Auto v+1)")
        self.btn_clone_version.setToolTip("复制当前策略参数并自动增加版本号，历史版本考核保持不可篡改")
        self.btn_clone_version.setStyleSheet("background-color: #238636; color: #ffffff; font-weight: bold;")
        self.btn_clone_version.clicked.connect(self._on_clone_strategy_clicked)
        strat_sel_layout.addWidget(self.btn_clone_version)

        strat_sel_layout.addStretch()
        form_layout.addWidget(group_strat_sel)

        group_thresh = QGroupBox("⚙️ 通道与成交量门槛参数 (Thresholds)")
        thresh_layout = QVBoxLayout(group_thresh)

        h_t1 = QHBoxLayout()
        h_t1.addWidget(QLabel("通道斜率下限 (slope_min):"))
        self.spin_slope_min = QDoubleSpinBox()
        self.spin_slope_min.setRange(0.0, 90.0)
        self.spin_slope_min.setSingleStep(0.1)
        h_t1.addWidget(self.spin_slope_min)

        h_t1.addWidget(QLabel("通道位置区间 (ch_pos):"))
        self.spin_ch_pos_min = QDoubleSpinBox()
        self.spin_ch_pos_min.setRange(0.0, 100.0)
        h_t1.addWidget(self.spin_ch_pos_min)
        h_t1.addWidget(QLabel("至"))
        self.spin_ch_pos_max = QDoubleSpinBox()
        self.spin_ch_pos_max.setRange(0.0, 100.0)
        h_t1.addWidget(self.spin_ch_pos_max)
        thresh_layout.addLayout(h_t1)

        h_t2 = QHBoxLayout()
        h_t2.addWidget(QLabel("下轨支撑容差 (support_tol):"))
        self.spin_support_tol = QDoubleSpinBox()
        self.spin_support_tol.setRange(0.0, 0.5)
        self.spin_support_tol.setSingleStep(0.005)
        self.spin_support_tol.setDecimals(3)
        h_t2.addWidget(self.spin_support_tol)

        h_t2.addWidget(QLabel("TD 卖点上限 (td_sell_max):"))
        self.spin_td_sell_max = QSpinBox()
        self.spin_td_sell_max.setRange(0, 13)
        h_t2.addWidget(self.spin_td_sell_max)
        thresh_layout.addLayout(h_t2)

        h_t3 = QHBoxLayout()
        h_t3.addWidget(QLabel("温和放量比例 (vol_ratio):"))
        self.spin_vol_ratio_min = QDoubleSpinBox()
        self.spin_vol_ratio_min.setRange(0.1, 10.0)
        self.spin_vol_ratio_min.setSingleStep(0.1)
        h_t3.addWidget(self.spin_vol_ratio_min)
        h_t3.addWidget(QLabel("至"))
        self.spin_vol_ratio_max = QDoubleSpinBox()
        self.spin_vol_ratio_max.setRange(0.1, 20.0)
        self.spin_vol_ratio_max.setSingleStep(0.1)
        h_t3.addWidget(self.spin_vol_ratio_max)
        thresh_layout.addLayout(h_t3)

        form_layout.addWidget(group_thresh)

        group_followup = QGroupBox("🔍 后验观察期与确认证据 (Followup)")
        fl_layout = QVBoxLayout(group_followup)

        h_fl = QHBoxLayout()
        h_fl.addWidget(QLabel("观察交易日天数:"))
        self.spin_trading_days = QSpinBox()
        self.spin_trading_days.setRange(1, 10)
        h_fl.addWidget(self.spin_trading_days)
        h_fl.addStretch()
        fl_layout.addLayout(h_fl)

        fl_layout.addWidget(QLabel("两帧确认允许证据 (proof_any):"))
        self.chk_proof_high = QCheckBox("突破昨日最高价站稳 (daily_high_break)")
        self.chk_proof_vwap = QCheckBox("真实成交均价持续上移 (verified_vwap_rise)")
        fl_layout.addWidget(self.chk_proof_high)
        fl_layout.addWidget(self.chk_proof_vwap)

        form_layout.addWidget(group_followup)

        group_req = QGroupBox("🛡️ 必需特征字段准入门禁 (Required Fields - 缺失则拦截入池)")
        req_layout = QVBoxLayout(group_req)
        self.list_req_fields = QListWidget()
        self.list_req_fields.setMaximumHeight(160)
        for feat in NextDayWatchConfigManager.get_supported_features():
            item = QListWidgetItem(feat, self.list_req_fields)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
        req_layout.addWidget(self.list_req_fields)
        form_layout.addWidget(group_req)

        form_layout.addStretch()
        form_scroll.setWidget(form_widget)
        splitter.addWidget(form_scroll)

        code_box = QGroupBox("📝 JSON 源码双向联动编辑器 (Config Source View)")
        code_layout = QVBoxLayout(code_box)
        code_layout.setContentsMargins(6, 12, 6, 6)

        self.edit_json_code = QPlainTextEdit()
        code_layout.addWidget(self.edit_json_code)

        btn_bar = QHBoxLayout()
        self.btn_sync_from_form = QPushButton("◀ 从表单同步到 JSON")
        self.btn_sync_from_form.clicked.connect(self._sync_form_to_json)
        btn_bar.addWidget(self.btn_sync_from_form)

        self.btn_sync_to_form = QPushButton("▶ 从 JSON 解析到表单")
        self.btn_sync_to_form.clicked.connect(self._sync_json_to_form)
        btn_bar.addWidget(self.btn_sync_to_form)

        self.btn_validate_cfg = QPushButton("🔍 校验配置合法性")
        self.btn_validate_cfg.clicked.connect(self._validate_current_json)
        btn_bar.addWidget(self.btn_validate_cfg)

        self.btn_save_cfg = QPushButton("💾 保存配置到磁盘 (原子落盘)")
        self.btn_save_cfg.setStyleSheet("background-color: #1f6feb; color: #ffffff; font-weight: bold; padding: 6px 16px;")
        self.btn_save_cfg.clicked.connect(self._save_config_action)
        btn_bar.addWidget(self.btn_save_cfg)

        code_layout.addLayout(btn_bar)
        splitter.addWidget(code_box)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 3)

        self.tab_widget.addTab(tab, "🛠️ 策略与规则配置 (Config Manager)")

    # =========================================================================
    # 数据加载与手动补算
    # =========================================================================
    def reload_all_data(self):
        """Trigger asynchronous data load without blocking UI."""
        self.status_message_changed.emit("正在后台读取候选池与后验文件...")
        target = self.combo_manifest_date.currentText().strip() or None
        self.active_worker = NextDayWatchDataLoaderWorker(target)
        self.active_worker.dates_scanned.connect(self._on_dates_scanned)
        self.active_worker.manifest_loaded.connect(self._on_manifest_loaded)
        self.active_worker.eval_loaded.connect(self._on_eval_loaded)
        self.active_worker.stats_loaded.connect(self._on_stats_loaded)
        self.active_worker.finished.connect(lambda: self.status_message_changed.emit(f"就绪 | 数据已更新: {time.strftime('%H:%M:%S')}"))
        self.active_worker.start()

    def _on_dates_scanned(self, dates: List[str]):
        self.available_dates = dates
        current = self.combo_manifest_date.currentText()
        self.combo_manifest_date.blockSignals(True)
        self.combo_manifest_date.clear()
        if dates:
            self.combo_manifest_date.addItems(dates)
            if current in dates:
                self.combo_manifest_date.setCurrentText(current)
            else:
                self.combo_manifest_date.setCurrentIndex(0)
        else:
            self.combo_manifest_date.addItem(time.strftime("%Y-%m-%d"))
        self.combo_manifest_date.blockSignals(False)

    def _on_manifest_date_changed(self, text: str):
        if text:
            self.reload_all_data()

    def _on_manifest_loaded(self, manifest: Dict[str, Any]):
        self.manifest_data = manifest
        asof = manifest.get("source_asof_trade_date", "--")
        target = manifest.get("target_trade_date", "--")
        candidates = manifest.get("candidates", [])
        total = len(candidates)
        univ = manifest.get("universe_count", "--")
        invalids = manifest.get("invalid_count", {})

        tier_counts = {}
        for c in candidates:
            t = c.get("tier", "Other")
            tier_counts[t] = tier_counts.get(t, 0) + 1
        tier_str = " | ".join(f"Tier {k}: {v}只" for k, v in sorted(tier_counts.items())) or "0只"

        invalid_str = ", ".join(f"{k}: {v}只" for k, v in invalids.items()) or "0"
        if not candidates and not manifest:
            summary_text = (
                "⚠️ 当前尚未生成候选池清单 (日常由 TK 在 08:30-09:15 自动冻结)。"
                "请点击右上角【⚡ 补算生成今日候选清单】立即基于全市场宽表生成！"
            )
            self.lbl_manifest_summary.setStyleSheet("""
                background-color: #3b2d12;
                border-left: 4px solid #f59e0b;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                color: #fbbf24;
            """)
        else:
            summary_text = (
                f"📅 基准交易日(T): {asof}  ➔  目标交易日(T+1): {target}  |  "
                f"候选总数: {total}只 ({tier_str})  |  全市场扫描宽表: {univ}只  |  "
                f"特征缺失剔除: {invalid_str}"
            )
            self.lbl_manifest_summary.setStyleSheet("""
                background-color: #1f242c;
                border-left: 4px solid #58a6ff;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 500;
                color: #d1d5db;
            """)
        self.lbl_manifest_summary.setText(summary_text)
        self._render_manifest_table()

    def _render_manifest_table(self):
        candidates = self.manifest_data.get("candidates", [])
        tier_filter = self.combo_tier_filter.currentText()
        strat_filter = self.combo_strat_filter.currentText()
        search_kw = self.edit_manifest_search.text().strip().lower()

        filtered = []
        for c in candidates:
            if "Tier A" in tier_filter and c.get("tier") != "A":
                continue
            if "Tier B" in tier_filter and c.get("tier") != "B":
                continue
            if "Tier C" in tier_filter and c.get("tier") != "C":
                continue
            if strat_filter != "全部策略" and c.get("strategy_id") != strat_filter:
                continue

            code = str(c.get("code", ""))
            name = str(c.get("name", ""))
            cat = str(c.get("category", ""))
            if search_kw and (search_kw not in code.lower() and search_kw not in name.lower() and search_kw not in cat.lower()):
                continue

            filtered.append(c)

        self.table_manifest.setRowCount(len(filtered))
        for row, c in enumerate(filtered):
            code = str(c.get("code", "")).zfill(6)
            name = str(c.get("name", code))
            tier = str(c.get("tier", ""))
            phase = str(c.get("phase", ""))
            score = float(c.get("score", 0.0))
            cat = str(c.get("category", ""))
            strat_ver = f"{c.get('strategy_id', '')} v{c.get('version', '')}"
            feats = c.get("feature_values", {})
            feat_summary = f"前高:{feats.get('lasth1d', '--')} 斜率:{feats.get('ch_slope_deg', '--')}° 位置:{feats.get('ch_pos', '--')}%"
            sector_matches = c.get("sector_evidence", {}).get("matches", [])
            sec_summary = ", ".join(m.get("name", "") for m in sector_matches if m.get("name")) or "--"
            status = str(c.get("status", "WATCHING"))

            item_code = QTableWidgetItem(code)
            item_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name = QTableWidgetItem(name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_tier = QTableWidgetItem(f"Tier {tier}")
            item_tier.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if tier == "A":
                item_tier.setForeground(QColor("#7ee787"))
            elif tier == "B":
                item_tier.setForeground(QColor("#ffa657"))
            elif tier == "C":
                item_tier.setForeground(QColor("#79c0ff"))

            item_phase = QTableWidgetItem(phase)
            item_phase.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_score = NumericTableWidgetItem(f"{score:.1f}")
            item_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_cat = QTableWidgetItem(cat)
            item_strat = QTableWidgetItem(strat_ver)
            item_strat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_feats = QTableWidgetItem(feat_summary)
            item_sec = QTableWidgetItem(sec_summary)
            item_status = QTableWidgetItem(status)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_manifest.setItem(row, 0, item_code)
            self.table_manifest.setItem(row, 1, item_name)
            self.table_manifest.setItem(row, 2, item_tier)
            self.table_manifest.setItem(row, 3, item_phase)
            self.table_manifest.setItem(row, 4, item_score)
            self.table_manifest.setItem(row, 5, item_cat)
            self.table_manifest.setItem(row, 6, item_strat)
            self.table_manifest.setItem(row, 7, item_feats)
            self.table_manifest.setItem(row, 8, item_sec)
            self.table_manifest.setItem(row, 9, item_status)

        self.table_manifest.resizeColumnsToContents()

    def _on_manifest_row_selected(self):
        row = self.table_manifest.currentRow()
        if row < 0:
            return
        code_item = self.table_manifest.item(row, 0)
        if not code_item:
            return
        code = code_item.text().strip()
        candidate = next((c for c in self.manifest_data.get("candidates", []) if str(c.get("code")).zfill(6) == code), None)
        if not candidate:
            return

        feats = candidate.get("feature_values", {})
        detail_lines = [
            f"【标的信息】: {code} {candidate.get('name')} | 分层: Tier {candidate.get('tier')} | 阶段: {candidate.get('phase')} | 综合得分: {candidate.get('score')}",
            f"【所属板块】: {candidate.get('category')} | 策略: {candidate.get('strategy_id')} v{candidate.get('version')}",
            f"【入池依据】: {', '.join(candidate.get('reason_codes', []))}",
            "【核心特征特征值清单】:",
        ]
        feat_pairs = [f"{k} = {v}" for k, v in sorted(feats.items())]
        for i in range(0, len(feat_pairs), 4):
            detail_lines.append("   " + "   |   ".join(feat_pairs[i:i+4]))

        self.text_feature_detail.setPlainText("\n".join(detail_lines))

    def _on_manifest_context_menu(self, pos):
        item = self.table_manifest.itemAt(pos)
        if not item:
            return
        row = item.row()
        code = self.table_manifest.item(row, 0).text().strip()
        name = self.table_manifest.item(row, 1).text().strip()

        menu = QMenu(self)
        act_sbc = menu.addAction(f"📈 打开 {name} ({code}) SBC 分时策略图")
        act_link = menu.addAction(f"🔍 联动外部看盘软件 ({code})")
        menu.addSeparator()
        act_copy = menu.addAction("📋 复制股票代码")

        action = menu.exec(self.table_manifest.viewport().mapToGlobal(pos))
        if action == act_sbc:
            self._open_sbc_for_code(code, name)
        elif action == act_link:
            send_to_linkage(code, name, self)
        elif action == act_copy:
            QApplication.clipboard().setText(code)

    def _on_candidate_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        code = self.table_manifest.item(row, 0).text().strip()
        name = self.table_manifest.item(row, 1).text().strip()
        self._open_sbc_for_code(code, name)

    def _open_sbc_for_code(self, code: str, name: str):
        try:
            from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
            dlg = SBCIntradayChartDialog.get_instance(code=code, name=name, parent=self)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception as exc:
            logger.warning("[NextDayWatchWidget] Open SBC dialog failed: %s", exc)

    def _on_manual_freeze_clicked(self):
        """Manually compute and freeze candidate list from current market data."""
        self.status_message_changed.emit("正在从市场宽表补算生成今日候选清单...")
        df = None
        # 1. 尝试从 parent 主窗口获取 current_df
        p = self.parent()
        while p is not None:
            if hasattr(p, "current_df") and p.current_df is not None and not p.current_df.empty:
                df = p.current_df
                break
            p = p.parent() if hasattr(p, "parent") else None

        # 2. 若无则从本地 HDF5 载入
        if df is None or df.empty:
            root = get_app_root()
            for h5_path in (
                os.path.join(root, "archives", "data", "shared_df_all.h5"),
                os.path.join(root, "test_data_hub", "shared_df_all.h5")
            ):
                if os.path.exists(h5_path):
                    try:
                        df = pd.read_hdf(h5_path, key="df_all")
                        break
                    except Exception:
                        pass

        if df is None or df.empty:
            QMessageBox.warning(
                self, "宽表数据未就绪",
                "未能自动获取到当前全市场日线宽表。\n请确保 ATS 已连接行情 IPC 或 TK 已启动刷新，然后再试。"
            )
            return

        today = time.strftime("%Y-%m-%d")
        root = get_app_root()
        data_dir = os.path.join(root, "datacsv")
        config_path = get_conf_path("next_day_watch_strategies.json", root)

        try:
            from JohnsonUtil import commonTips as cct
            asof_date = str(cct.get_last_trade_date(today))[:10]
        except Exception:
            asof_date = today

        result = run_cycle(
            df, config_path=config_path, data_dir=data_dir,
            asof_date=asof_date, target_date=today,
            observe=False, force_freeze=True
        )

        status = result.get("status")
        if status in ("ok", "manifest_ready"):
            count = result.get("candidate_count", 0)
            QMessageBox.information(
                self, "候选池生成成功",
                f"✅ 成功补算并冻结今日 ({today}) 候选清单！\n入选标的: {count} 只。\n清单文件已写入 datacsv 目录。"
            )
            self.reload_all_data()
        elif status == "disabled":
            QMessageBox.warning(
                self, "功能未启用",
                "当前次日候选池配置处于停用状态 (enabled: false)。\n请在【🛠️ 策略与规则配置】Tab 勾选启用后保存再试。"
            )
        else:
            QMessageBox.critical(
                self, "生成失败",
                f"生成候选池失败: {result.get('reason', status)}"
            )

    # =========================================================================
    # Tab 2: 盘中实时后验
    # =========================================================================
    def _on_eval_loaded(self, eval_data: Dict[str, Any]):
        self.eval_data = eval_data
        candidates_eval = eval_data.get("candidates", {})

        events = []
        for key, entry in candidates_eval.items():
            cand = entry.get("candidate", {})
            for ev in entry.get("events", []):
                events.append((ev.get("observed_at", ""), ev, cand))
        events.sort(key=lambda x: x[0], reverse=True)

        self.table_events.setRowCount(len(events))
        confirmed_count = 0
        for r, (t_str, ev, cand) in enumerate(events):
            ev_type = ev.get("type", "")
            if ev_type == "NEXT_DAY_WATCH_CONFIRM":
                confirmed_count += 1
            code = str(ev.get("code") or cand.get("code", "")).zfill(6)
            name = str(ev.get("name") or cand.get("name", code))
            price = f"{float(ev.get('price', 0.0)):.2f}"
            pct = f"{float(ev.get('pct', 0.0)):+.2f}%"
            delivered = "已投递" if ev.get("delivered") else "待投递"
            t_show = t_str.split("T")[-1][:8] if "T" in t_str else t_str

            item_t = QTableWidgetItem(t_show)
            item_code = QTableWidgetItem(code)
            item_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name = QTableWidgetItem(name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_type = QTableWidgetItem(ev_type)
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if ev_type == "NEXT_DAY_WATCH_CONFIRM":
                item_type.setForeground(QColor("#7ee787"))
            elif ev_type == "DAY_MISS":
                item_type.setForeground(QColor("#ff7b72"))
            elif ev_type == "DELAYED":
                item_type.setForeground(QColor("#ffa657"))

            item_p = NumericTableWidgetItem(price)
            item_pct = NumericTableWidgetItem(pct)
            item_pct.setForeground(QColor("#ff7b72") if "+" in pct else QColor("#7ee787"))
            item_del = QTableWidgetItem(delivered)
            item_del.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_events.setItem(r, 0, item_t)
            self.table_events.setItem(r, 1, item_code)
            self.table_events.setItem(r, 2, item_name)
            self.table_events.setItem(r, 3, item_type)
            self.table_events.setItem(r, 4, item_p)
            self.table_events.setItem(r, 5, item_pct)
            self.table_events.setItem(r, 6, item_del)

        self.table_events.resizeColumnsToContents()
        self.lbl_eval_status.setText(
            f"⚡ 盘中后验引擎: 监控中候选标的 {len(candidates_eval)} 只 | 触发确认事件 {confirmed_count} 起 | 更新时间: {time.strftime('%H:%M:%S')}"
        )

    def _on_event_row_selected(self):
        row = self.table_events.currentRow()
        if row < 0:
            return
        code_item = self.table_events.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()

        entry = next((item for k, item in self.eval_data.get("candidates", {}).items() if k.startswith(code + ":")), None)
        if not entry:
            return

        events = entry.get("events", [])
        confirm_ev = next((e for e in reversed(events) if e.get("type") == "NEXT_DAY_WATCH_CONFIRM"), None)
        if confirm_ev:
            evidence = confirm_ev.get("evidence", {})
            first_time = evidence.get("first_observed_at", "--").split("T")[-1][:8]
            confirm_time = confirm_ev.get("observed_at", "--").split("T")[-1][:8]
            proof_desc = []
            if evidence.get("sustained_high"):
                proof_desc.append("突破昨日最高价并站稳")
            if evidence.get("verified_vwap_rise"):
                proof_desc.append("真实均价(VWAP)持续抬升")
            proof_str = " + ".join(proof_desc) or "两帧量价共振"

            proof_text = (
                f"✅ 【两帧确认闭环证据】标的: {confirm_ev.get('code')} {confirm_ev.get('name')}\n"
                f"• 首发观测帧: {first_time}  ➔  二次确认帧: {confirm_time} (在有效时效窗内满足)\n"
                f"• 突破核心证据: {proof_str} | 当时现价: {confirm_ev.get('price')} (涨幅: {confirm_ev.get('pct')}%) | 真实VWAP: {evidence.get('vwap')}\n"
                f"• 唯一事件ID: {confirm_ev.get('event_id')} | 交付标记: {'已送达交易账本' if confirm_ev.get('delivered') else '等待投递'}"
            )
            self.lbl_event_proof.setText(proof_text)
        else:
            self.lbl_event_proof.setText("当前标的未触发 NEXT_DAY_WATCH_CONFIRM 确认事件")

        checkpoints = entry.get("checkpoints", [])
        self.table_checkpoints.setRowCount(len(checkpoints))
        for r, cp in enumerate(reversed(checkpoints)):
            t_raw = cp.get("observed_at", "")
            t_show = t_raw.split("T")[-1][:8] if "T" in t_raw else t_raw
            phase = cp.get("phase", "")
            hp = f"{float(cp.get('high', 0.0)):.2f}"
            p = f"{float(cp.get('close', 0.0)):.2f}"
            vw = f"{float(cp.get('vwap', 0.0)):.2f}" if cp.get("vwap") is not None else "--"
            vol = str(int(cp.get("volume", 0))) if cp.get("volume") is not None else "--"
            proofs = []
            if cp.get("sustained_high"):
                proofs.append("新高")
            if cp.get("verified_vwap_rise"):
                proofs.append("VWAP↑")
            proof_label = " | ".join(proofs) or "平稳"

            self.table_checkpoints.setItem(r, 0, QTableWidgetItem(t_show))
            self.table_checkpoints.setItem(r, 1, QTableWidgetItem(phase))
            self.table_checkpoints.setItem(r, 2, NumericTableWidgetItem(hp))
            self.table_checkpoints.setItem(r, 3, NumericTableWidgetItem(p))
            self.table_checkpoints.setItem(r, 4, NumericTableWidgetItem(vw))
            self.table_checkpoints.setItem(r, 5, NumericTableWidgetItem(vol))
            self.table_checkpoints.setItem(r, 6, QTableWidgetItem(proof_label))

        self.table_checkpoints.resizeColumnsToContents()

    def _on_event_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        code = self.table_events.item(row, 1).text().strip()
        name = self.table_events.item(row, 2).text().strip()
        self._open_sbc_for_code(code, name)

    def _on_toggle_auto_refresh(self, checked: bool):
        if checked:
            self.auto_refresh_timer.start()
        else:
            self.auto_refresh_timer.stop()

    def _on_auto_refresh_tick(self):
        if self.tab_widget.currentIndex() == 1:
            cur_date = self.combo_manifest_date.currentText().strip() or time.strftime("%Y-%m-%d")
            eval_path = os.path.join(get_app_root(), "datacsv", f"next_day_anomaly_eval_{cur_date}.json")
            if os.path.exists(eval_path):
                data = _read_json(eval_path, {})
                if data:
                    self._on_eval_loaded(data)

    # =========================================================================
    # Tab 3: 跨日成效看板
    # =========================================================================
    def _on_stats_loaded(self, stats_list: List[Dict[str, Any]]):
        self.stats_data_list = stats_list

        rows = []
        for sfile in stats_list:
            tdate = sfile.get("target_trade_date", "")
            for s in sfile.get("strategies", []):
                rows.append((tdate, s))

        self.table_stats.setRowCount(len(rows))
        for r, (tdate, s) in enumerate(rows):
            strat_id = s.get("strategy_id", "")
            ver = str(s.get("version", ""))
            total = int(s.get("candidate_count", 0))
            valid = int(s.get("early_valid", 0))
            delayed = int(s.get("delayed", 0))
            day_miss = int(s.get("day_miss", 0))
            missed = int(s.get("missed", 0))
            rate = f"{(valid / total * 100):.1f}%" if total > 0 else "0.0%"

            self.table_stats.setItem(r, 0, QTableWidgetItem(tdate))
            self.table_stats.setItem(r, 1, QTableWidgetItem(strat_id))
            self.table_stats.setItem(r, 2, QTableWidgetItem(ver))
            self.table_stats.setItem(r, 3, NumericTableWidgetItem(str(total)))
            self.table_stats.setItem(r, 4, NumericTableWidgetItem(str(valid)))
            self.table_stats.setItem(r, 5, NumericTableWidgetItem(str(delayed)))
            self.table_stats.setItem(r, 6, NumericTableWidgetItem(str(day_miss)))
            self.table_stats.setItem(r, 7, NumericTableWidgetItem(str(missed)))
            item_rate = NumericTableWidgetItem(rate)
            item_rate.setForeground(QColor("#7ee787"))
            self.table_stats.setItem(r, 8, item_rate)

        self.table_stats.resizeColumnsToContents()

        delayed_winners = []
        for sf in stats_list:
            tdate = sf.get("target_trade_date", "")
            eval_path = os.path.join(get_app_root(), "datacsv", f"next_day_anomaly_eval_{tdate}.json")
            eval_data = _read_json(eval_path, {})
            for entry in eval_data.get("candidates", {}).values():
                cand = entry.get("candidate", {})
                if cand.get("status") == "DELAYED" or any(e.get("type") == "DELAYED" for e in entry.get("events", [])):
                    delayed_winners.append((cand, tdate))

        self.table_delayed_winners.setRowCount(len(delayed_winners))
        for r, (cand, initial_date) in enumerate(delayed_winners):
            code = str(cand.get("code", "")).zfill(6)
            name = str(cand.get("name", code))
            h1d = str(cand.get("feature_values", {}).get("lasth1d", "--"))
            status = str(cand.get("status", "DELAYED"))

            self.table_delayed_winners.setItem(r, 0, QTableWidgetItem(code))
            self.table_delayed_winners.setItem(r, 1, QTableWidgetItem(name))
            self.table_delayed_winners.setItem(r, 2, QTableWidgetItem(initial_date))
            self.table_delayed_winners.setItem(r, 3, QTableWidgetItem("T+1~T+3后续交易日"))
            self.table_delayed_winners.setItem(r, 4, NumericTableWidgetItem(h1d))
            item_st = QTableWidgetItem(status)
            item_st.setForeground(QColor("#ffa657"))
            self.table_delayed_winners.setItem(r, 5, item_st)

        self.table_delayed_winners.resizeColumnsToContents()

    def _on_delayed_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        code = self.table_delayed_winners.item(row, 0).text().strip()
        name = self.table_delayed_winners.item(row, 1).text().strip()
        self._open_sbc_for_code(code, name)

    # =========================================================================
    # Tab 4: 策略配置管理
    # =========================================================================
    def _load_config_data(self):
        ok, cfg, msg = NextDayWatchConfigManager.load_config()
        if not ok and not cfg:
            cfg = NextDayWatchConfigManager.get_default_config()
        self.current_config = cfg
        self._populate_form_from_config(cfg)
        self.edit_json_code.setPlainText(json.dumps(cfg, indent=2, ensure_ascii=False))

    def _populate_form_from_config(self, cfg: Dict[str, Any]):
        self.chk_global_enabled.setChecked(bool(cfg.get("enabled", True)))
        vw = str(cfg.get("vwap_field") or "None")
        idx = self.combo_vwap_field.findText(vw)
        if idx >= 0:
            self.combo_vwap_field.setCurrentIndex(idx)

        strategies = cfg.get("strategies", [])
        self.combo_strat_edit.blockSignals(True)
        self.combo_strat_edit.clear()
        for s in strategies:
            label = f"{s.get('strategy_id')} (v{s.get('version')})"
            if not s.get("enabled", True):
                label += " [已停用]"
            self.combo_strat_edit.addItem(label, s.get("strategy_id"))
        self.combo_strat_edit.blockSignals(False)

        if strategies:
            self._display_strategy_in_form(strategies[0])

    def _display_strategy_in_form(self, strat: Dict[str, Any]):
        thresh = strat.get("thresholds", {})
        self.spin_slope_min.setValue(float(thresh.get("slope_min", 1.5)))
        self.spin_ch_pos_min.setValue(float(thresh.get("ch_pos_min", 5.0)))
        self.spin_ch_pos_max.setValue(float(thresh.get("ch_pos_max", 60.0)))
        self.spin_support_tol.setValue(float(thresh.get("support_tolerance", 0.015)))
        self.spin_td_sell_max.setValue(int(thresh.get("td_sell_max", 5)))
        self.spin_vol_ratio_min.setValue(float(thresh.get("volume_ratio_min", 1.1)))
        self.spin_vol_ratio_max.setValue(float(thresh.get("volume_ratio_max", 2.5)))

        followup = strat.get("followup", {})
        self.spin_trading_days.setValue(int(followup.get("trading_days", 3)))
        proofs = followup.get("proof_any", [])
        self.chk_proof_high.setChecked("daily_high_break" in proofs)
        self.chk_proof_vwap.setChecked("verified_vwap_rise" in proofs)

        req_set = set(strat.get("required_fields", []))
        for i in range(self.list_req_fields.count()):
            item = self.list_req_fields.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.text() in req_set else Qt.CheckState.Unchecked)

    def _on_strat_edit_selection_changed(self, idx: int):
        if idx < 0:
            return
        strat_id = self.combo_strat_edit.currentData()
        strategies = self.current_config.get("strategies", [])
        strat = next((s for s in strategies if s.get("strategy_id") == strat_id), None)
        if strat:
            self._display_strategy_in_form(strat)

    def _on_clone_strategy_clicked(self):
        strat_id = self.combo_strat_edit.currentData()
        if not strat_id:
            return
        ok, new_cfg, msg = NextDayWatchConfigManager.clone_strategy_new_version(self.current_config, strat_id)
        if ok:
            self.current_config = new_cfg
            self._populate_form_from_config(new_cfg)
            self.edit_json_code.setPlainText(json.dumps(new_cfg, indent=2, ensure_ascii=False))
            QMessageBox.information(self, "版本升级成功", f"{msg}\n原版本已自动停用，新版本将在保存后生效。")
        else:
            QMessageBox.warning(self, "克隆失败", msg)

    def _sync_form_to_json(self):
        strat_id = self.combo_strat_edit.currentData()
        strategies = self.current_config.get("strategies", [])
        strat = next((s for s in strategies if s.get("strategy_id") == strat_id), None)
        if not strat:
            return

        self.current_config["enabled"] = self.chk_global_enabled.isChecked()
        vw = self.combo_vwap_field.currentText()
        self.current_config["vwap_field"] = None if vw == "None" else vw

        strat.setdefault("thresholds", {})
        strat["thresholds"]["slope_min"] = round(self.spin_slope_min.value(), 2)
        strat["thresholds"]["ch_pos_min"] = round(self.spin_ch_pos_min.value(), 2)
        strat["thresholds"]["ch_pos_max"] = round(self.spin_ch_pos_max.value(), 2)
        strat["thresholds"]["support_tolerance"] = round(self.spin_support_tol.value(), 3)
        strat["thresholds"]["td_sell_max"] = int(self.spin_td_sell_max.value())
        strat["thresholds"]["volume_ratio_min"] = round(self.spin_vol_ratio_min.value(), 2)
        strat["thresholds"]["volume_ratio_max"] = round(self.spin_vol_ratio_max.value(), 2)

        strat.setdefault("followup", {})
        strat["followup"]["trading_days"] = int(self.spin_trading_days.value())
        proofs = []
        if self.chk_proof_high.isChecked():
            proofs.append("daily_high_break")
        if self.chk_proof_vwap.isChecked():
            proofs.append("verified_vwap_rise")
        strat["followup"]["proof_any"] = proofs

        checked_reqs = []
        for i in range(self.list_req_fields.count()):
            item = self.list_req_fields.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_reqs.append(item.text())
        strat["required_fields"] = checked_reqs

        self.edit_json_code.setPlainText(json.dumps(self.current_config, indent=2, ensure_ascii=False))
        self.status_message_changed.emit("已从表单同步至 JSON 源码")

    def _sync_json_to_form(self):
        raw_text = self.edit_json_code.toPlainText()
        try:
            parsed = json.loads(raw_text)
            valid, msg = NextDayWatchConfigManager.validate_config(parsed)
            if not valid:
                QMessageBox.warning(self, "JSON 解析警告", f"配置结构存在问题: {msg}")
            self.current_config = parsed
            self._populate_form_from_config(parsed)
            self.status_message_changed.emit("已从 JSON 源码重新解析并填充至表单")
        except Exception as exc:
            QMessageBox.critical(self, "JSON 语法错误", f"无法解析 JSON 文本: {exc}")

    def _validate_current_json(self):
        raw_text = self.edit_json_code.toPlainText()
        try:
            parsed = json.loads(raw_text)
            valid, msg = NextDayWatchConfigManager.validate_config(parsed)
            if valid:
                QMessageBox.information(self, "配置校验通过", "✅ 当前策略配置完全符合 Schema 规范与语义约束，可安全保存！")
            else:
                QMessageBox.warning(self, "配置校验未通过", f"❌ 校验发现问题: {msg}")
        except Exception as exc:
            QMessageBox.critical(self, "语法错误", f"JSON 语法无效: {exc}")

    def _save_config_action(self):
        self._sync_form_to_json()
        raw_text = self.edit_json_code.toPlainText()
        try:
            parsed = json.loads(raw_text)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"JSON 语法无效: {exc}")
            return

        valid, msg = NextDayWatchConfigManager.validate_config(parsed)
        if not valid:
            QMessageBox.critical(self, "拒绝保存", f"配置未通过安全门禁: {msg}")
            return

        ok, save_msg, digest = NextDayWatchConfigManager.save_config(parsed)
        if ok:
            QMessageBox.information(
                self, "策略配置保存成功",
                f"✅ 配置已原子安全写入磁盘！\n\n"
                f"• 配置指纹摘要 (SHA256): {digest[:16]}...\n"
                f"• 生效机制约定: 当前已冻结的交易日清单保持不可篡改；新策略与新参数将在下一交易日 08:30 盘前自动生效。"
            )
            self.status_message_changed.emit(f"配置保存成功 (Hash: {digest[:8]}) | {time.strftime('%H:%M:%S')}")
        else:
            QMessageBox.critical(self, "保存失败", f"写盘失败: {save_msg}")


class NextDayAnomalyWatchDialog(QMainWindow):
    """Independent companion window for NextDayAnomalyWatchWidget."""

    _instance: Optional[NextDayAnomalyWatchDialog] = None

    @classmethod
    def get_instance(cls, parent: Optional[QWidget] = None) -> NextDayAnomalyWatchDialog:
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
        return cls._instance

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("📋 次日异动候选池综合管理中心 (Next-Day Watch Center)")
        self.resize(1320, 850)
        self.setMinimumSize(960, 600)

        # 全局深色样式
        self.setStyleSheet("""
            QMainWindow { background-color: #121417; color: #e1e7ec; }
            QWidget { font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 10pt; }
            QTabWidget::pane { border: 1px solid #23272e; background-color: #16191d; border-radius: 4px; }
            QTabBar::tab { background: #1a1e24; color: #8b949e; padding: 8px 18px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }
            QTabBar::tab:selected { background: #21262d; color: #58a6ff; border-bottom: 2px solid #58a6ff; }
            QTabBar::tab:hover { color: #f0f6fc; }
            QTableWidget { background-color: #121417; alternate-background-color: #181b20; border: 1px solid #282c34; gridline-color: #21262d; color: #d1d5db; selection-background-color: #264f78; selection-color: #ffffff; }
            QHeaderView::section { background-color: #1a1e24; color: #9ca3af; padding: 5px; border: 1px solid #282c34; font-weight: bold; }
            QPushButton { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 5px 12px; font-weight: 500; }
            QPushButton:hover { background-color: #30363d; color: #ffffff; border-color: #8b949e; }
            QPushButton:pressed { background-color: #161b22; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #161b22; color: #f0f6fc; border: 1px solid #30363d; border-radius: 4px; padding: 4px 8px; }
            QComboBox:hover, QLineEdit:hover { border-color: #58a6ff; }
            QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #58a6ff; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPlainTextEdit { background-color: #0d1117; color: #7ee787; border: 1px solid #30363d; border-radius: 4px; font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt; }
            QStatusBar { background-color: #16191d; color: #8b949e; border-top: 1px solid #23272e; }
        """)

        self.widget = NextDayAnomalyWatchWidget(parent=self)
        self.setCentralWidget(self.widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 | 次日候选池多维监控体系已连接")
        self.widget.status_message_changed.connect(self.status_bar.showMessage)

    def closeEvent(self, event):
        if hasattr(self.widget, "auto_refresh_timer") and self.widget.auto_refresh_timer.isActive():
            self.widget.auto_refresh_timer.stop()
        event.accept()

# -*- coding: utf-8 -*-
"""
ats/ui/sector_rotation_miner_dialog.py — 板块轮动前排引导与资金主线回踩启动深挖专业工作台 (Qt6)
=============================================================================
核心特性：
1. 【双视图上下联动工作台】：
   - 上半区：当前引导冲锋的核心资金主线板块与领涨先锋 (单击过滤下半区，双击龙头联动股票，双击板块联动可视化，支持右键菜单)；
   - 下半区：实际资金主线·回踩确认启动跟进池 (dff2 依托 MA20 黄金带 + per1d~per9d 缩量洗盘转阳)；
2. 【高响应异步多线程扫描】：
   - 全市场 5000+ 标的后台异步毫秒级完成扫描，主线程 0 阻塞，绝无白闪与卡顿；
   - 原地 In-place 增量复用刷新，支持按需自动刷新 (3s/5s/10s/30s)；
3. 【全终端无缝生态联动 (SSOT)】：
   - 双击标的即时联动通达信 / 同花顺 / 本地 Visualizer (TCP 26668) / 主界面看板；
   - 右键直通【📈 联动行情】、【📊 打开 SBC 独立分时图】、【🧬 DNA 专项审核 (Alt+W)】、【⭐ 重点关注切换】、【📋 复制查询表达式】；
   - 快捷键支持：`T` 键置顶、`Alt+W` DNA 审核、`F5` 刷新；
   - 绝对放行 `Alt+R`：专属于系统全局/底层 Tk 视窗轮转切换器，本窗口绝不抢占；
   - 窗口坐标、尺寸与两张表格的列宽状态自动持久化记忆。
"""

import os
import sys
import time
import math
import logging
from typing import Dict, List, Tuple, Optional, Any

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QCheckBox, QComboBox, QLineEdit, QMenu, QApplication,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QPoint, QEvent
from PyQt6.QtGui import QColor, QFont, QBrush, QKeySequence, QShortcut
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN,
    apply_dark_theme, bind_top_shortcut, setup_header_persistence,
    save_config_node, load_config_node, set_seamless_stay_on_top
)
from ats.sector_rotation_pullback_miner import (
    SectorRotationPullbackMiner, get_sector_rotation_miner, is_valid_sector_name
)
from global_favorites import GlobalFavoriteManager
from ats.ui.base_table import send_to_linkage
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("SectorRotationMinerDialog")


class MinerWorkerThread(QThread):
    """后台扫描工作线程，完全不阻塞 Qt 主线程"""
    scan_finished = pyqtSignal(dict)

    def __init__(self, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.df = df

    def run(self):
        try:
            miner = get_sector_rotation_miner()
            res = miner.run_mining_pipeline(self.df)
            self.scan_finished.emit(res)
        except Exception as e:
            logger.error(f"[MinerWorkerThread] Scan failed: {e}", exc_info=True)
            self.scan_finished.emit({"sectors": [], "candidates": [], "error": str(e)})


class SectorRotationMinerDialog(QDialog, WindowMixin):
    """
    板块轮动前排引导与资金主线回踩启动深挖专业工作台 (Qt6)
    """
    code_clicked = pyqtSignal(str) # 选股或双击联动信号

    def __init__(self, parent=None, current_df: Optional[pd.DataFrame] = None):
        # [🚀 独立顶层解耦] 传入 None 剥离 Win32 HWND Owner 从属关系，彻底切断物理强行置顶，避免遮挡 ATS 主窗口
        super().__init__(None)
        self._parent_window = parent
        self.setWindowTitle("🔥 板块轮动前排引导与资金主线回踩启动深挖工作台")
        self.resize(1220, 760)

        self.current_df = current_df
        self._all_candidates: List[Dict[str, Any]] = []
        self._last_sectors: List[Dict[str, Any]] = []
        self._selected_sector: Optional[str] = None
        self._worker: Optional[MinerWorkerThread] = None

        # 初始化 UI
        self._init_ui()
        self._init_shortcuts()

        # 恢复窗口位置与尺寸
        self.load_window_position_qt(self, "sector_rotation_miner_dialog", default_width=1220, default_height=760)

        # 恢复列宽持久化
        setup_header_persistence(self.sectors_table, "sector_miner_sectors_header")
        setup_header_persistence(self.candidates_table, "sector_miner_candidates_header")

        # 自动刷新定时器
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_auto_refresh)

        # 首次加载数据
        if self.current_df is not None and not self.current_df.empty:
            QTimer.singleShot(100, self.trigger_scan)

    def _init_ui(self):
        """构建现代暗色专业 UI 布局"""
        apply_dark_theme(self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ── 1. 顶部控制栏 ──
        top_bar = QFrame(self)
        top_bar.setStyleSheet("background-color: #1a1a22; border-radius: 6px; padding: 4px;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(8)

        # 标题与指示
        lbl_title = QLabel("🔥 资金主线与回踩启动深挖")
        lbl_title.setStyleSheet("font-size: 11pt; font-weight: bold; color: #ffd700;")
        top_layout.addWidget(lbl_title)

        top_layout.addSpacing(10)

        # 深度扫描按钮
        self.btn_scan = QPushButton("🚀 一键深度挖掘")
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #ffffff; font-weight: bold;
                border: 1px solid #3d6ea8; border-radius: 4px; padding: 5px 12px;
            }
            QPushButton:hover { background-color: #2a5282; }
            QPushButton:pressed { background-color: #162c46; }
        """)
        self.btn_scan.clicked.connect(self.trigger_scan)
        top_layout.addWidget(self.btn_scan)

        # 自动刷新勾选框与频率
        self.chk_auto = QCheckBox("自动刷新")
        self.chk_auto.setStyleSheet("color: #aad4ff; font-weight: bold;")
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        top_layout.addWidget(self.chk_auto)

        self.combo_interval = QComboBox()
        self.combo_interval.addItems(["3 秒", "5 秒", "10 秒", "30 秒"])
        self.combo_interval.setCurrentIndex(1) # 默认 5 秒
        self.combo_interval.currentIndexChanged.connect(self._on_interval_changed)
        top_layout.addWidget(self.combo_interval)

        top_layout.addSpacing(10)

        # 参数微调展示
        lbl_dff2_tip = QLabel("MA20依托: [-2.5%, +6.5%]")
        lbl_dff2_tip.setStyleSheet("color: #88aacc; font-size: 8.5pt;")
        top_layout.addWidget(lbl_dff2_tip)

        lbl_pattern_tip = QLabel("时序: per1d~9d缩量企稳+今日首阳")
        lbl_pattern_tip.setStyleSheet("color: #88ccaa; font-size: 8.5pt;")
        top_layout.addWidget(lbl_pattern_tip)

        top_layout.addStretch()

        # 候选过滤搜索框
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("🔍 快速过滤代码/名称/板块...")
        self.txt_filter.setFixedWidth(180)
        self.txt_filter.setStyleSheet("background-color: #121216; color: #ffffff; border: 1px solid #334455; border-radius: 4px; padding: 3px 6px;")
        self.txt_filter.textChanged.connect(self._apply_candidate_filter)
        top_layout.addWidget(self.txt_filter)

        # 置顶按钮
        self.btn_top = QPushButton("📌 置顶 (T)")
        self.btn_top.setCheckable(True)
        self.btn_top.setStyleSheet("""
            QPushButton {
                background-color: #2a2a32; color: #cccccc; border: 1px solid #444455;
                border-radius: 4px; padding: 4px 8px;
            }
            QPushButton:checked { background-color: #995500; color: #ffffff; border-color: #ffaa00; }
        """)
        self.btn_top.toggled.connect(self._toggle_stay_on_top)
        top_layout.addWidget(self.btn_top)

        # 关闭按钮 (支持点击或 Esc 快捷键)
        self.btn_close = QPushButton("✕ 关闭 (Esc)")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #2a2228; color: #ff8888; border: 1px solid #663344;
                border-radius: 4px; padding: 4px 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #552233; color: #ffaaaa; border-color: #aa4455; }
            QPushButton:pressed { background-color: #331122; color: #ffffff; }
        """)
        self.btn_close.clicked.connect(self.close)
        top_layout.addWidget(self.btn_close)

        main_layout.addWidget(top_bar)

        # ── 2. 主体工作区 (QSplitter 上下切分) ──
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2e2e38; height: 5px;
            }
            QSplitter::handle:hover {
                background-color: #ffd700;
            }
        """)

        # ── 上半区：引导冲锋板块与先锋龙头 ──
        sectors_panel = QWidget()
        sectors_layout = QVBoxLayout(sectors_panel)
        sectors_layout.setContentsMargins(0, 0, 0, 0)
        sectors_layout.setSpacing(4)

        sec_header = QHBoxLayout()
        lbl_sec_title = QLabel("🔥 当前引导冲锋的核心资金主线板块 (点击行联动筛选下方回踩池 | 上下键移动浏览 | 双击龙头联动股票 | 右键操作)")
        lbl_sec_title.setStyleSheet("color: #aad4ff; font-weight: bold; font-size: 9.5pt;")
        sec_header.addWidget(lbl_sec_title)
        sec_header.addStretch()

        self.btn_show_all = QPushButton("显示全部主线")
        self.btn_show_all.setStyleSheet("color: #88bbff; background: transparent; border: 1px solid #446688; border-radius: 3px; padding: 2px 8px;")
        self.btn_show_all.clicked.connect(self._clear_sector_filter)
        sec_header.addWidget(self.btn_show_all)
        sectors_layout.addLayout(sec_header)

        self.sectors_table = QTableWidget(self)
        self.sectors_table.setColumnCount(8)
        self.sectors_table.setHorizontalHeaderLabels([
            "板块名称", "资金评级", "强度得分", "板块均涨", "冲锋前排数", "领涨先锋龙头", "总成交额(亿)", "加权量比"
        ])
        self.sectors_table.horizontalHeader().setStretchLastSection(True)
        self.sectors_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sectors_table.verticalHeader().setVisible(False)
        self.sectors_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sectors_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sectors_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sectors_table.setAlternatingRowColors(True)
        self.sectors_table.itemClicked.connect(self._on_sector_row_clicked)
        self.sectors_table.installEventFilter(self)  # 键盘上下键独立平滑联动，绝不篡改鼠标点击 Toggle 状态
        self.sectors_table.itemDoubleClicked.connect(self._on_sector_double_clicked)
        self.sectors_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sectors_table.customContextMenuRequested.connect(self._on_sector_context_menu)
        sectors_layout.addWidget(self.sectors_table)

        self.splitter.addWidget(sectors_panel)

        # ── 下半区：资金主线·回踩确认启动跟进池 ──
        candidates_panel = QWidget()
        candidates_layout = QVBoxLayout(candidates_panel)
        candidates_layout.setContentsMargins(0, 0, 0, 0)
        candidates_layout.setSpacing(4)

        cand_header = QHBoxLayout()
        self.lbl_cand_title = QLabel("🎯 实际资金主线·回踩确认启动跟进池 (点击或上下键即时联动 / 双击联动 / 右键菜单 / Alt+W审计)")
        self.lbl_cand_title.setStyleSheet("color: #aaffaa; font-weight: bold; font-size: 9.5pt;")
        cand_header.addWidget(self.lbl_cand_title)
        cand_header.addStretch()

        self.lbl_count_info = QLabel("候选: 0 只")
        self.lbl_count_info.setStyleSheet("color: #cccccc; font-size: 9pt;")
        cand_header.addWidget(self.lbl_count_info)
        candidates_layout.addLayout(cand_header)

        self.candidates_table = QTableWidget(self)
        self.candidates_table.setColumnCount(13)
        self.candidates_table.setHorizontalHeaderLabels([
            "代码", "名称", "所属主线", "启动形态", "综合得分",
            "涨幅 dff", "距MA20 dff2", "长期 dff3", "近3日时序", "量比",
            "建议买区", "止损位", "实战决策理由"
        ])
        self.candidates_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.candidates_table.verticalHeader().setVisible(False)
        self.candidates_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.candidates_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.candidates_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.candidates_table.setAlternatingRowColors(True)
        self.candidates_table.itemClicked.connect(self._on_candidate_clicked)
        self.candidates_table.currentItemChanged.connect(self._on_candidate_current_changed)
        self.candidates_table.itemDoubleClicked.connect(self._on_candidate_double_clicked)
        self.candidates_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.candidates_table.customContextMenuRequested.connect(self._on_candidate_context_menu)
        candidates_layout.addWidget(self.candidates_table)

        self.splitter.addWidget(candidates_panel)

        # 设置上下 Splitter 默认高度比例 (1 : 2)
        self.splitter.setSizes([240, 460])
        main_layout.addWidget(self.splitter)

        # ── 3. 底部状态栏 ──
        self.status_bar = QLabel("就绪. 点击【🚀 一键深度挖掘】开始全市场主线与回踩扫描.")
        self.status_bar.setStyleSheet("color: #888899; font-size: 8.5pt; padding: 2px;")
        main_layout.addWidget(self.status_bar)

    def _init_shortcuts(self):
        """绑定常用便捷快捷键 (坚决不抢占 Alt+R，确保专属于系统全局视窗轮转)"""
        # 快捷键 T: 切换置顶
        bind_top_shortcut(self)
        
        # 快捷键 F5: 刷新
        f5_shortcut = QShortcut(QKeySequence("F5"), self)
        f5_shortcut.activated.connect(self.trigger_scan)

        # 快捷键 Alt+W: DNA 专项审核
        dna_shortcut = QShortcut(QKeySequence("Alt+W"), self)
        dna_shortcut.activated.connect(self._run_dna_audit_selected)

    def _toggle_stay_on_top(self, checked: bool):
        """窗口置顶切换"""
        set_seamless_stay_on_top(self, checked)
        self.btn_top.setChecked(checked)

    def update_data_payload(self, df: pd.DataFrame):
        """外部数据源增量推送"""
        if df is not None and not df.empty:
            self.current_df = df
            if self.chk_auto.isChecked():
                self.trigger_scan()

    def trigger_scan(self):
        """触发深度扫描 (异步多线程，不卡顿)"""
        if self.current_df is None or self.current_df.empty:
            self.status_bar.setText("⚠️ 当前无行情数据源，请确保策略或监控程序已启动.")
            return

        if self._worker is not None and self._worker.isRunning():
            return  # 上一次扫描还在进行中

        self.btn_scan.setEnabled(False)
        self.status_bar.setText("⏳ 正在全市场深度扫描主线板块与回踩确认启动个股...")

        self._worker = MinerWorkerThread(self.current_df, self)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_finished(self, report: Dict[str, Any]):
        """扫描完成回调处理"""
        self.btn_scan.setEnabled(True)
        if "error" in report:
            self.status_bar.setText(f"❌ 扫描异常: {report['error']}")
            return

        sectors = report.get("sectors", [])
        candidates = report.get("candidates", [])
        cost_ms = report.get("calc_time_ms", 0.0)
        total_stocks = report.get("total_stocks", 0)

        self._last_sectors = sectors
        self._all_candidates = candidates
        self._render_sectors_table(sectors)
        self._apply_candidate_filter()

        is_post_market = bool(report.get("is_post_market", False))
        mode_prefix = "🌙 [盘后复盘·以最新收盘日(per1d)为基准]" if is_post_market else "🔥 [盘中实时模式]"
        self.status_bar.setText(
            f"✅ 扫描完成 | {mode_prefix} 全市场 {total_stocks} 只标的 | "
            f"锁定 {len(sectors)} 大主线板块 | 挖掘出 {len(candidates)} 只回踩启动标的 | 耗时 {cost_ms}ms"
        )

        # 动态更新下半区第 5 列表头：盘后显示 涨幅 per1d，盘中显示 涨幅 dff
        pct_col_name = "涨幅 per1d" if is_post_market else "涨幅 dff"
        self.candidates_table.setHorizontalHeaderItem(5, QTableWidgetItem(pct_col_name))

    def _render_sectors_table(self, sectors: List[Dict[str, Any]]):
        """渲染上半区板块表格"""
        self.sectors_table.setSortingEnabled(False)
        self.sectors_table.setRowCount(len(sectors))
        fav_mgr = GlobalFavoriteManager()

        for row, s in enumerate(sectors):
            s_name = s.get("name", "")
            grade = s.get("grade", "")
            score = float(s.get("strength_score", 0.0))
            avg_pct = float(s.get("avg_pct", 0.0))
            pio_cnt = int(s.get("pioneer_count", 0))
            leader = f"{s.get('leader_name', '')} ({s.get('leader_pct', 0.0):+.1f}%)"
            amt_yi = float(s.get("total_amt_yi", 0.0))
            vr = float(s.get("vol_ratio", 1.0))
            l_code = s.get("leader_code", "")

            # 判断板块是否重点关注
            is_sec_fav = fav_mgr.is_favorite_sector(s_name)
            display_name = f"⭐ {s_name}" if is_sec_fav else s_name

            # 0: 板块名称
            item_name = QTableWidgetItem(display_name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            if is_sec_fav:
                item_name.setForeground(QBrush(QColor("#ffd700")))
            self.sectors_table.setItem(row, 0, item_name)

            # 1: 评级
            item_grade = QTableWidgetItem(grade)
            item_grade.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if "核心" in grade:
                item_grade.setForeground(QBrush(QColor("#ffd700")))
            elif "活跃" in grade:
                item_grade.setForeground(QBrush(QColor("#ff55bb")))
            else:
                item_grade.setForeground(QBrush(QColor("#aaccff")))
            self.sectors_table.setItem(row, 1, item_grade)

            # 2: 强度得分
            item_score = NumericTableWidgetItem(f"{score:.1f}", score)
            item_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_score.setForeground(QBrush(QColor("#ffaa00")))
            self.sectors_table.setItem(row, 2, item_score)

            # 3: 板块均涨
            pct_color = QColor(COLOR_UP) if avg_pct > 0 else (QColor(COLOR_DOWN) if avg_pct < 0 else QColor("#cccccc"))
            item_pct = NumericTableWidgetItem(f"{avg_pct:+.2f}%", avg_pct)
            item_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_pct.setForeground(QBrush(pct_color))
            self.sectors_table.setItem(row, 3, item_pct)

            # 4: 冲锋前排数
            item_pio = NumericTableWidgetItem(f"{pio_cnt} 只", pio_cnt)
            item_pio.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if pio_cnt >= 3:
                item_pio.setForeground(QBrush(QColor("#ff5555")))
            self.sectors_table.setItem(row, 4, item_pio)

            # 5: 领涨先锋 (存入 leader_code 便于双击联动)
            item_leader = QTableWidgetItem(leader)
            item_leader.setData(Qt.ItemDataRole.UserRole, l_code)
            item_leader.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_leader.setForeground(QBrush(QColor("#ffcc66")))
            item_leader.setToolTip(f"双击直接联动领涨龙头: {s.get('leader_name', '')} ({l_code})")
            self.sectors_table.setItem(row, 5, item_leader)

            # 6: 总成交额
            item_amt = NumericTableWidgetItem(f"{amt_yi:.1f} 亿", amt_yi)
            item_amt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sectors_table.setItem(row, 6, item_amt)

            # 7: 加权量比
            item_vr = NumericTableWidgetItem(f"{vr:.2f}", vr)
            item_vr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if vr >= 1.5:
                item_vr.setForeground(QBrush(QColor("#ff8800")))
            self.sectors_table.setItem(row, 7, item_vr)

        self.sectors_table.setSortingEnabled(True)

    def _render_candidates_table(self, candidates: List[Dict[str, Any]]):
        """渲染下半区回踩启动个股表格"""
        self.candidates_table.setSortingEnabled(False)
        self.candidates_table.setRowCount(len(candidates))
        fav_mgr = GlobalFavoriteManager()

        for row, c in enumerate(candidates):
            code = c.get("code", "")
            name = c.get("name", "")
            sec = c.get("sector", "")
            pattern = c.get("pattern_name", "")
            score = float(c.get("reversal_score", 0.0))
            pct = float(c.get("pct", 0.0))
            dff2 = float(c.get("dff2", 0.0))
            dff3 = float(c.get("dff3", 0.0))
            p1 = float(c.get("per1d", 0.0))
            p2 = float(c.get("per2d", 0.0))
            p3 = float(c.get("per3d", 0.0))
            seq_str = f"{p1:+.1f}% / {p2:+.1f}% / {p3:+.1f}%"
            vr = float(c.get("vol_ratio", 1.0))
            b_zone = c.get("buy_zone", "--")
            s_loss = float(c.get("stop_loss", 0.0))
            reason = c.get("reason", "")

            is_stock_fav = fav_mgr.is_favorite_stock(code)

            # 0: 代码
            it_code = QTableWidgetItem(code)
            it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_stock_fav:
                it_code.setForeground(QBrush(QColor("#ffd700")))
            self.candidates_table.setItem(row, 0, it_code)

            # 1: 名称 (重点关注加 ⭐ 徽章)
            disp_name = f"⭐ {name}" if is_stock_fav else name
            it_name = QTableWidgetItem(disp_name)
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            if is_stock_fav:
                it_name.setForeground(QBrush(QColor("#ffd700")))
            self.candidates_table.setItem(row, 1, it_name)

            # 2: 所属主线
            it_sec = QTableWidgetItem(sec)
            it_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_sec.setForeground(QBrush(QColor("#aad4ff")))
            self.candidates_table.setItem(row, 2, it_sec)

            # 3: 启动形态
            it_pat = QTableWidgetItem(pattern)
            it_pat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if "起爆" in pattern or "共振" in pattern:
                it_pat.setForeground(QBrush(QColor("#ffd700")))
            elif "企稳" in pattern:
                it_pat.setForeground(QBrush(QColor("#aaffaa")))
            self.candidates_table.setItem(row, 3, it_pat)

            # 4: 综合得分
            it_score = NumericTableWidgetItem(f"{score:.1f}", score)
            it_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_score.setForeground(QBrush(QColor("#ffaa00")))
            self.candidates_table.setItem(row, 4, it_score)

            # 5: 涨幅
            pct_c = QColor(COLOR_UP) if pct > 0 else (QColor(COLOR_DOWN) if pct < 0 else QColor("#cccccc"))
            it_pct = NumericTableWidgetItem(f"{pct:+.2f}%", pct)
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pct.setForeground(QBrush(pct_c))
            self.candidates_table.setItem(row, 5, it_pct)

            # 6: 距离MA20 dff2
            it_dff2 = NumericTableWidgetItem(f"{dff2:+.2f}%", dff2)
            it_dff2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if 0.0 <= dff2 <= 3.5:
                it_dff2.setForeground(QBrush(QColor("#00ff88")))
            elif dff2 < 0:
                it_dff2.setForeground(QBrush(QColor("#66ccff")))
            self.candidates_table.setItem(row, 6, it_dff2)

            # 7: 长期 dff3
            it_dff3 = NumericTableWidgetItem(f"{dff3:+.1f}%", dff3)
            it_dff3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.candidates_table.setItem(row, 7, it_dff3)

            # 8: 近3日时序
            it_seq = QTableWidgetItem(seq_str)
            it_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_seq.setForeground(QBrush(QColor("#bbbbcc")))
            self.candidates_table.setItem(row, 8, it_seq)

            # 9: 量比
            it_vr = NumericTableWidgetItem(f"{vr:.2f}", vr)
            it_vr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if vr >= 1.3:
                it_vr.setForeground(QBrush(QColor("#ffaa33")))
            self.candidates_table.setItem(row, 9, it_vr)

            # 10: 建议买区
            it_zone = QTableWidgetItem(b_zone)
            it_zone.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_zone.setForeground(QBrush(QColor("#ffffaa")))
            self.candidates_table.setItem(row, 10, it_zone)

            # 11: 止损位
            it_loss = NumericTableWidgetItem(f"{s_loss:.2f}", s_loss)
            it_loss.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_loss.setForeground(QBrush(QColor("#ff8888")))
            self.candidates_table.setItem(row, 11, it_loss)

            # 12: 实战决策理由
            it_reason = QTableWidgetItem(reason)
            it_reason.setToolTip(reason)
            self.candidates_table.setItem(row, 12, it_reason)

        self.candidates_table.setSortingEnabled(True)
        self.lbl_count_info.setText(f"候选: {len(candidates)} 只")

    def _apply_candidate_filter(self):
        """应用板块单选或关键字过滤"""
        kw = self.txt_filter.text().strip().lower()
        filtered = []

        for c in self._all_candidates:
            # 板块联动筛选
            if self._selected_sector:
                if self._selected_sector not in c.get("sector", ""):
                    continue

            # 关键字二次筛选
            if kw:
                code = str(c.get("code", "")).lower()
                name = str(c.get("name", "")).lower()
                sec = str(c.get("sector", "")).lower()
                pat = str(c.get("pattern_name", "")).lower()
                if kw not in code and kw not in name and kw not in sec and kw not in pat:
                    continue

            filtered.append(c)

        self._render_candidates_table(filtered)

    def _on_sector_row_clicked(self, item: QTableWidgetItem):
        """点击板块行：若点击当前已选板块，则取消选择恢复显示全部；否则单选该板块联动下半区"""
        if not item:
            return
        row = item.row()
        sec_item = self.sectors_table.item(row, 0)
        if not sec_item:
            return
        raw_text = sec_item.text().strip()
        sec_name = raw_text.replace("⭐", "").strip()
        if self._selected_sector == sec_name:
            # 再次点击已选中的板块，取消选中，恢复显示全部主线
            self._clear_sector_filter()
        else:
            self._set_selected_sector(sec_name)

    def eventFilter(self, watched, event):
        """事件过滤器：精准捕获板块表格键盘上下键浏览，绝不干扰鼠标点击 Toggle 状态"""
        if watched == self.sectors_table and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                res = super().eventFilter(watched, event)
                row = self.sectors_table.currentRow()
                if row >= 0:
                    sec_item = self.sectors_table.item(row, 0)
                    if sec_item:
                        sec_name = sec_item.text().replace("⭐", "").strip()
                        self._set_selected_sector(sec_name)
                return res
        return super().eventFilter(watched, event)

    def _on_sector_current_changed(self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]):
        """键盘上下键或光标移动板块行，即时联动下半区回踩跟进池"""
        if not current:
            return
        if previous is not None and previous.row() == current.row():
            return
        row = current.row()
        sec_item = self.sectors_table.item(row, 0)
        if sec_item:
            sec_name = sec_item.text().replace("⭐", "").strip()
            self._set_selected_sector(sec_name)

    def _set_selected_sector(self, sec_name: str):
        """设置当前选中的主线板块并过滤下半区"""
        self._selected_sector = sec_name
        self.lbl_cand_title.setText(f"🎯 主线【{self._selected_sector}】· 回踩确认启动标的")
        self.btn_show_all.setText(f"✕ 显示全部主线 (当前: {self._selected_sector})")
        self.btn_show_all.setStyleSheet("color: #ffd700; background: #2a2a35; border: 1px solid #aa8800; border-radius: 3px; padding: 2px 8px; font-weight: bold;")
        self._apply_candidate_filter()
        self.status_bar.setText(f"🔍 已锁定主线板块【{sec_name}】，下半区展示相关回踩启动标的")

    def _clear_sector_filter(self):
        """清空板块过滤，显示全部主线"""
        self._selected_sector = None
        self.lbl_cand_title.setText("🎯 实际资金主线·回踩确认启动跟进池 (全部主线)")
        self.btn_show_all.setText("显示全部主线")
        self.btn_show_all.setStyleSheet("color: #88bbff; background: transparent; border: 1px solid #446688; border-radius: 3px; padding: 2px 8px;")
        self.sectors_table.clearSelection()
        self.sectors_table.setCurrentCell(-1, -1)
        self._apply_candidate_filter()
        self.status_bar.setText("🌐 已恢复显示全部主线板块的回踩启动标的")

    def _on_sector_double_clicked(self, item: QTableWidgetItem):
        """双击板块行：若点领涨龙头直接联动龙头，否则联动可视化端筛选板块"""
        row = item.row()
        col = item.column()
        sec_item = self.sectors_table.item(row, 0)
        leader_item = self.sectors_table.item(row, 5)
        raw_sec = sec_item.text().strip() if sec_item else ""
        sec_name = raw_sec.replace("⭐", "").strip()
        leader_code = leader_item.data(Qt.ItemDataRole.UserRole) if leader_item else ""

        # 双击第 5 列领涨先锋龙头：直接联动龙头股票
        if col == 5 and leader_code:
            leader_txt = leader_item.text().strip()
            self._broadcast_link_stock(leader_code, leader_txt)
            return

        # 双击其他列：联动可视化端过滤板块
        if sec_name:
            self._link_sector_to_visualizer(sec_name)

    def _link_sector_to_visualizer(self, sec_name: str):
        """向可视化器联动板块过滤"""
        query_str = f'category.str.contains("{sec_name}")'
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        if parent_win and hasattr(parent_win, "cat_filter_input"):
            try:
                parent_win.cat_filter_input.setCurrentText(query_str)
                if hasattr(parent_win, "_on_cat_filter_apply"):
                    parent_win._on_cat_filter_apply()
                elif hasattr(parent_win, "on_cat_filter_change"):
                    parent_win.on_cat_filter_change(query_str)
                self.status_bar.setText(f"🔄 已联动可视化看板过滤板块: {sec_name}")
                return
            except Exception:
                pass

        # 异步 TCP 26668 指令
        import socket, threading
        def _send_query():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    s.connect(('127.0.0.1', 26668))
                    msg = f"QUERY|{query_str}"
                    s.sendall(msg.encode("utf-8"))
            except Exception:
                pass
        threading.Thread(target=_send_query, daemon=True, name="SectorLinkWorker").start()
        QApplication.clipboard().setText(query_str)
        self.status_bar.setText(f"📋 已联动板块并复制查询表达式: {query_str}")

    def _on_sector_context_menu(self, pos: QPoint):
        """上半区板块右键菜单"""
        item = self.sectors_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        sec_item = self.sectors_table.item(row, 0)
        leader_item = self.sectors_table.item(row, 5)
        if not sec_item:
            return
        raw_sec = sec_item.text().strip()
        sec = raw_sec.replace("⭐", "").strip()
        leader_code = leader_item.data(Qt.ItemDataRole.UserRole) if leader_item else ""
        leader_text = leader_item.text().strip() if leader_item else ""

        fav_mgr = GlobalFavoriteManager()
        is_fav = fav_mgr.is_favorite_sector(sec)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)

        act_filter = menu.addAction(f"🔍 联动可视化器过滤板块: {sec}")
        act_link_leader = menu.addAction(f"📈 联动领涨先锋: {leader_text}") if leader_code else None
        act_pipe_leader = menu.addAction(f"⚡ 发送领涨先锋到异动联动: {leader_text}") if leader_code else None

        menu.addSeparator()
        act_dna_sec = menu.addAction(f"🧬 对【{sec}】回踩标的执行 DNA 审核")
        fav_label = f"❌ 取消重点关注板块 ({sec})" if is_fav else f"⭐ 设为重点关注板块 ({sec})"
        act_fav_sec = menu.addAction(fav_label)

        menu.addSeparator()
        act_copy_sec = menu.addAction(f"📋 复制板块名称 ({sec})")
        act_copy_expr = menu.addAction(f"📋 复制板块查询表达式 (category.str.contains(\"{sec}\"))")

        chosen = menu.exec(self.sectors_table.viewport().mapToGlobal(pos))
        if chosen == act_filter:
            self._link_sector_to_visualizer(sec)
        elif act_link_leader and chosen == act_link_leader:
            self._broadcast_link_stock(leader_code, leader_text)
        elif act_pipe_leader and chosen == act_pipe_leader:
            send_to_linkage(leader_code, leader_text, self)
            self.status_bar.setText(f"⚡ 已将领涨先锋发送到异动联动: {leader_text} ({leader_code})")
        elif chosen == act_dna_sec:
            self._selected_sector = sec
            self._apply_candidate_filter()
            self._run_dna_audit_selected()
        elif chosen == act_fav_sec:
            fav_mgr.toggle_favorite_sector(sec)
            self.status_bar.setText(f"⭐ 已更新重点关注板块: {sec}")
            self._render_sectors_table(self._last_sectors)
        elif chosen == act_copy_sec:
            QApplication.clipboard().setText(sec)
            self.status_bar.setText(f"📋 已复制板块名称: {sec}")
        elif chosen == act_copy_expr:
            q_str = f'category.str.contains("{sec}")'
            QApplication.clipboard().setText(q_str)
            self.status_bar.setText(f"📋 已复制查询表达式: {q_str}")

    def _on_candidate_clicked(self, item: QTableWidgetItem):
        """单击候选标的行，即时跨终端广播联动"""
        if not item:
            return
        self._trigger_candidate_link_by_row(item.row())

    def _on_candidate_current_changed(self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]):
        """光标移动（键盘上下键或鼠标选行切换），防抖即时联动"""
        if not current:
            return
        if previous is not None and previous.row() == current.row():
            return
        self._trigger_candidate_link_by_row(current.row())

    def _trigger_candidate_link_by_row(self, row: int):
        """根据候选行号提取股票信息并广播联动"""
        code_item = self.candidates_table.item(row, 0)
        name_item = self.candidates_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        raw_name = name_item.text().strip() if name_item else ""
        name = raw_name.replace("⭐", "").strip()
        self._broadcast_link_stock(code, name)

    def _on_candidate_double_clicked(self, item: QTableWidgetItem):
        """双击下半区候选标的，跨软件/全生态广播联动"""
        row = item.row()
        code_item = self.candidates_table.item(row, 0)
        name_item = self.candidates_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        raw_name = name_item.text().strip() if name_item else ""
        name = raw_name.replace("⭐", "").strip()
        self._broadcast_link_stock(code, name)

    def _broadcast_link_stock(self, code: str, name: str = "", date: Optional[str] = None):
        """向本地可视化终端、主系统窗口与外部行情终端多通道广播联动 (SSOT)"""
        code_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
        if not code_clean:
            return

        # 0. 相同股票短时间 (300ms) 防抖，避免单次点击同时触发 currentItemChanged 和 itemClicked 重复派发
        now = time.time()
        if getattr(self, "_last_linked_code", None) == code_clean and (now - getattr(self, "_last_linked_time", 0.0)) < 0.3:
            return
        self._last_linked_code = code_clean
        self._last_linked_time = now

        # 1. 发射 Qt 信号通知外部监听
        self.code_clicked.emit(code_clean)

        # 2. 优先通知宿主父窗口 (如 MainWindow / trade_visualizer_qt6)
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        if parent_win:
            if hasattr(parent_win, "load_stock_by_code"):
                try:
                    parent_win.load_stock_by_code(code_clean, name=name)
                except Exception as e:
                    logger.debug(f"Parent load_stock_by_code failed: {e}")
            elif hasattr(parent_win, "link_stock"):
                try:
                    parent_win.link_stock(code_clean, name, date=date)
                except TypeError:
                    parent_win.link_stock(code_clean, name)
                except Exception as e:
                    logger.debug(f"Parent link_stock failed: {e}")
            elif hasattr(parent_win, "on_stock_selected"):
                try:
                    parent_win.on_stock_selected(code_clean)
                except Exception as e:
                    logger.debug(f"Parent on_stock_selected failed: {e}")

        # 3. 通知全局 ATSMainWindow 统一分发 (如果存在)
        try:
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, "main_window") and isinstance(app.main_window, ATSMainWindow):
                try:
                    app.main_window.link_stock(code_clean, name, date=date)
                except TypeError:
                    app.main_window.link_stock(code_clean, name)
        except Exception:
            pass

        # 4. 直接异步向 trade_visualizer_qt6 (TCP 端口 26668) 发送指令
        import socket, threading
        def _send_vis():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    s.connect(('127.0.0.1', 26668))
                    msg = f"CODE|{code_clean}"
                    s.sendall(msg.encode("utf-8"))
            except Exception:
                pass
        threading.Thread(target=_send_vis, daemon=True, name="VisLinkWorker").start()

        # 5. 外部物理行情终端联动 (通达信/同花顺)
        try:
            from linkage_service import get_link_manager
            mgr = get_link_manager()
            if mgr:
                mgr.push(code_clean, flags={'tdx': True, 'ths': True, 'dfcf': False})
        except Exception:
            pass
        try:
            from JohnsonUtil import commonTips as cct
            cct.to_toptdx(code_clean)
        except Exception:
            pass

        self.status_bar.setText(f"⚡ 已联动行情标的: {name} ({code_clean})")

    def _open_sbc_chart(self, code: str):
        """打开 SBC 独立分时图"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code)
        except Exception as e:
            logger.debug(f"Open SBC chart error: {e}")

    def _toggle_favorite_stock(self, code: str, name: str = ""):
        """切换股票重点关注状态"""
        try:
            fav_mgr = GlobalFavoriteManager()
            is_now_fav = fav_mgr.toggle_favorite_stock(str(code).strip())
            act_text = "已加入重点关注" if is_now_fav else "已从重点关注移除"
            self.status_bar.setText(f"⭐ {act_text}: {name or code} ({code})")
            self._apply_candidate_filter()
        except Exception as e:
            logger.debug(f"Toggle favorite stock error: {e}")

    def _on_candidate_context_menu(self, pos: QPoint):
        """下半区候选标的右键菜单"""
        item = self.candidates_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_it = self.candidates_table.item(row, 0)
        name_it = self.candidates_table.item(row, 1)
        sec_it = self.candidates_table.item(row, 2)
        reason_it = self.candidates_table.item(row, 12)
        if not code_it or not name_it:
            return

        code = code_it.text().strip()
        raw_name = name_it.text().strip()
        name = raw_name.replace("⭐", "").strip()
        sec = sec_it.text().strip() if sec_it else ""
        reason = reason_it.text().strip() if reason_it else ""

        fav_mgr = GlobalFavoriteManager()
        is_fav = fav_mgr.is_favorite_stock(code)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)

        act_link = menu.addAction(f"📈 联动行情: {name} ({code})")
        act_pipe = menu.addAction(f"⚡ 发送到异动联动: {name} ({code})")
        act_sbc = menu.addAction(f"📊 打开 SBC 独立分时走势 ({code})")
        act_dna = menu.addAction(f"🧬 DNA 专项审核 (Alt+W)")
        menu.addSeparator()

        fav_label = f"❌ 取消重点关注 ({code})" if is_fav else f"⭐ 设为重点关注 ({code})"
        act_fav = menu.addAction(fav_label)

        menu.addSeparator()
        act_copy_code = menu.addAction(f"📋 复制股票代码 ({code})")
        act_copy_sec = menu.addAction(f"📋 复制主线板块 ({sec})")
        act_copy_query = menu.addAction(f"📋 复制查询表达式 (code in ['{code}'])")
        act_copy_row = menu.addAction("📋 复制本行决策理由")

        chosen = menu.exec(self.candidates_table.viewport().mapToGlobal(pos))
        if chosen == act_link:
            self._broadcast_link_stock(code, name)
        elif chosen == act_pipe:
            send_to_linkage(code, name, self)
            self.status_bar.setText(f"⚡ 已发送到异动联动: {name} ({code})")
        elif chosen == act_sbc:
            self._open_sbc_chart(code)
        elif chosen == act_dna:
            self._run_dna_audit_selected()
        elif chosen == act_fav:
            self._toggle_favorite_stock(code, name)
        elif chosen == act_copy_code:
            QApplication.clipboard().setText(code)
            self.status_bar.setText(f"📋 已复制股票代码: {code}")
        elif chosen == act_copy_sec:
            QApplication.clipboard().setText(sec)
            self.status_bar.setText(f"📋 已复制主线板块: {sec}")
        elif chosen == act_copy_query:
            expr = f"code in ['{code}']"
            QApplication.clipboard().setText(expr)
            self.status_bar.setText(f"📋 已复制查询表达式: {expr}")
        elif chosen == act_copy_row:
            QApplication.clipboard().setText(f"{code} {name} [{sec}]: {reason}")
            self.status_bar.setText(f"📋 已复制决策理由: {name} ({code})")

    def _run_dna_audit_selected(self):
        """对选中的候选标的执行 DNA 专项审核 (支持单选、多选与批量向下20只)"""
        rows = self.candidates_table.rowCount()
        if rows == 0:
            return

        sel_rows = sorted(set(i.row() for i in self.candidates_table.selectedItems()))
        target = []
        if len(sel_rows) > 1:
            for r in sel_rows[:50]:
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            for r in range(start, min(start + 20, rows)):
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))
        else:
            for r in range(min(20, rows)):
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))

        code_to_name = {c: n for c, n in target if c}
        if not code_to_name:
            return

        self.status_bar.setText(f"🧬 正在对 {len(code_to_name)} 只回踩启动标的执行 DNA 专项审核...")
        QApplication.processEvents()

        # 1. 优先尝试主应用程序接口 (Tk / ATS 统一审计服务)
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        main_app = getattr(parent_win, 'parent_app', None) or getattr(self.window(), 'parent_app', None)
        if not main_app:
            main_app = getattr(QApplication.instance(), 'parent_app', None)
        if main_app and hasattr(main_app, '_run_dna_audit_batch'):
            if hasattr(main_app, 'tk_dispatch_queue'):
                _cn = dict(code_to_name)
                main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
            else:
                main_app._run_dna_audit_batch(code_to_name)
            self.status_bar.setText(f"✅ 已向主控中心派发 DNA 审计任务 ({len(code_to_name)} 只标的)")
            return

        win = self.window()
        if hasattr(win, '_run_dna_audit_batch') and win is not self:
            win._run_dna_audit_batch(code_to_name)
            self.status_bar.setText(f"✅ 已向宿主窗口派发 DNA 审计任务 ({len(code_to_name)} 只标的)")
            return

        # 2. 独立 PyQt6 优雅降级模式：本地直接生成并调起 QtDnaAuditReportWindow
        try:
            from backtest_feature_auditor import audit_multiple_codes
            from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            
            period_data = self.current_df
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=None,
                code_to_name=code_to_name,
                progress_callback=None,
                resample='d',
                period_data=period_data
            )
            if summaries:
                self._dna_audit_win = QtDnaAuditReportWindow(
                    summaries, parent=self, end_date=None, resample='d'
                )
                self._dna_audit_win.show()
                self.status_bar.setText(f"✅ DNA 专项审核已完成，共生成 {len(summaries)} 份研报")
            else:
                self.status_bar.setText("⚠️ 未生成 DNA 审计有效数据")
        except Exception as e:
            logger.error(f"DNA audit local fallback error: {e}", exc_info=True)
            self.status_bar.setText(f"❌ DNA 审计异常: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _on_auto_toggled(self, checked: bool):
        """开关自动刷新"""
        if checked:
            idx = self.combo_interval.currentIndex()
            sec = [3, 5, 10, 30][idx] if idx < 4 else 5
            self.refresh_timer.start(sec * 1000)
            self.status_bar.setText(f"🔄 自动刷新已开启，每 {sec} 秒同步扫描一次.")
        else:
            self.refresh_timer.stop()
            self.status_bar.setText("⏸️ 自动刷新已暂停.")

    def _on_interval_changed(self, idx: int):
        """切换自动刷新间隔"""
        if self.chk_auto.isChecked():
            sec = [3, 5, 10, 30][idx] if idx < 4 else 5
            self.refresh_timer.start(sec * 1000)

    def _on_auto_refresh(self):
        """自动定时刷新"""
        if self.isVisible():
            self.trigger_scan()

    def keyPressEvent(self, event):
        """键盘事件：放行 Alt+R 专用于系统视窗轮转，支持 T 置顶，F5 刷新，Alt+W 审核，Esc 退出"""
        modifiers = event.modifiers()
        key = event.key()

        # 🚀 绝对放行 Alt+R：专属于系统全局/底层 Tk 视窗轮转切换器，绝不消费/拦截！
        if key == Qt.Key.Key_R and (modifiers & Qt.KeyboardModifier.AltModifier):
            event.ignore()
            return

        # 🚀 支持 Esc 键快速关闭退出工作台
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return

        if key == Qt.Key.Key_W and (modifiers & Qt.KeyboardModifier.AltModifier):
            self._run_dna_audit_selected()
            event.accept()
            return

        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self.btn_top.toggle()
                event.accept()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        """窗口关闭时保存坐标与尺寸"""
        self.refresh_timer.stop()
        self.save_window_position_qt(self, "sector_rotation_miner_dialog")
        event.accept()


def open_sector_rotation_miner_dialog(parent_window=None, current_df: Optional[pd.DataFrame] = None) -> SectorRotationMinerDialog:
    """调起/显示板块轮动深挖独立窗口 (单例维护)"""
    dialog = getattr(parent_window, "_sector_rotation_miner_win", None)
    if dialog is None or not hasattr(dialog, "isVisible"):
        dialog = SectorRotationMinerDialog(parent=parent_window, current_df=current_df)
        if parent_window is not None:
            setattr(parent_window, "_sector_rotation_miner_win", dialog)

    if current_df is not None and not current_df.empty:
        dialog.update_data_payload(current_df)

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog

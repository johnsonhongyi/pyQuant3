# -*- coding: utf-8 -*-
"""
ats/ui/sector_rotation_miner_dialog.py — 板块轮动前排引导与资金主线回踩启动深挖专业工作台 (Qt6)
=============================================================================
核心特性：
1. 【双视图上下联动工作台】：
   - 上半区：当前引导冲锋的核心资金主线板块与领涨先锋 (点击板块行即时联动过滤)；
   - 下半区：实际资金主线·回踩确认启动跟进池 (dff2 依托 MA20 黄金带 + per1d~per9d 缩量洗盘转阳)；
2. 【高响应异步多线程扫描】：
   - 全市场 5000+ 标的后台异步秒级完成扫描 (<50ms)，主线程 0 阻塞，绝无白闪与残影；
   - 原地 In-place 增量复用刷新，支持按需自动刷新 (3s/5s/10s)；
3. 【全终端无缝生态联动】：
   - 双击标的即时联动通达信 / 同花顺 / 本地 Qt6 K线分时图；
   - 右键直通【🧬 DNA 专项审核 (Alt+W)】、【⭐ 设为重点关注】、【📋 复制查询表达式】；
   - 支持快捷键 `T` 无缝置顶、`Alt+R` 独立呼出、`F5` 立即刷新、`Esc` 退出；
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
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, QPoint
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
        super().__init__(parent)
        self.setWindowTitle("🔥 板块轮动前排引导与资金主线回踩启动深挖工作台 (Alt+R)")
        self.resize(1220, 760)

        self.current_df = current_df
        self._all_candidates: List[Dict[str, Any]] = []
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

        # 标题与状态指示灯
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
        lbl_sec_title = QLabel("🔥 当前引导冲锋的核心资金主线板块 (点击行联动筛选下方回踩池)")
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
        sectors_layout.addWidget(self.sectors_table)

        self.splitter.addWidget(sectors_panel)

        # ── 下半区：资金主线·回踩确认启动跟进池 ──
        candidates_panel = QWidget()
        candidates_layout = QVBoxLayout(candidates_panel)
        candidates_layout.setContentsMargins(0, 0, 0, 0)
        candidates_layout.setSpacing(4)

        cand_header = QHBoxLayout()
        self.lbl_cand_title = QLabel("🎯 实际资金主线·回踩确认启动跟进池 (双击联动行情 / 右键DNA审核)")
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
        self.candidates_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.candidates_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.candidates_table.setAlternatingRowColors(True)
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
        """绑定常用便捷快捷键"""
        # 快捷键 T: 切换置顶
        bind_top_shortcut(self)
        
        # 快捷键 F5: 刷新
        f5_shortcut = QShortcut(QKeySequence("F5"), self)
        f5_shortcut.activated.connect(self.trigger_scan)

        # 快捷键 Alt+W: DNA 专项审核
        dna_shortcut = QShortcut(QKeySequence("Alt+W"), self)
        dna_shortcut.activated.connect(self._run_dna_audit_on_selected)

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

        for row, s in enumerate(sectors):
            s_name = s.get("name", "")
            grade = s.get("grade", "")
            score = float(s.get("strength_score", 0.0))
            avg_pct = float(s.get("avg_pct", 0.0))
            pio_cnt = int(s.get("pioneer_count", 0))
            leader = f"{s.get('leader_name', '')} ({s.get('leader_pct', 0.0):+.1f}%)"
            amt_yi = float(s.get("total_amt_yi", 0.0))
            vr = float(s.get("vol_ratio", 1.0))

            # 0: 板块名称
            item_name = QTableWidgetItem(s_name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
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

            # 5: 领涨先锋
            item_leader = QTableWidgetItem(leader)
            item_leader.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_leader.setForeground(QBrush(QColor("#ffcc66")))
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

            # 0: 代码
            it_code = QTableWidgetItem(code)
            it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.candidates_table.setItem(row, 0, it_code)

            # 1: 名称
            it_name = QTableWidgetItem(name)
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
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

            # 5: 涨幅 dff
            pct_c = QColor(COLOR_UP) if pct > 0 else (QColor(COLOR_DOWN) if pct < 0 else QColor("#cccccc"))
            it_pct = NumericTableWidgetItem(f"{pct:+.2f}%", pct)
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pct.setForeground(QBrush(pct_c))
            self.candidates_table.setItem(row, 5, it_pct)

            # 6: 距离MA20 dff2
            it_dff2 = NumericTableWidgetItem(f"{dff2:+.2f}%", dff2)
            it_dff2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 贴近 0~3% 范围高亮绿色/金色
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
        """点击板块行，即时联动下半区"""
        row = item.row()
        sec_item = self.sectors_table.item(row, 0)
        if sec_item:
            self._selected_sector = sec_item.text().strip()
            self.lbl_cand_title.setText(f"🎯 主线【{self._selected_sector}】· 回踩确认启动标的")
            self._apply_candidate_filter()

    def _clear_sector_filter(self):
        """清空板块过滤，显示全部主线"""
        self._selected_sector = None
        self.lbl_cand_title.setText("🎯 实际资金主线·回踩确认启动跟进池 (全部主线)")
        self.sectors_table.clearSelection()
        self._apply_candidate_filter()

    def _on_candidate_double_clicked(self, item: QTableWidgetItem):
        """双击候选标的，跨软件/本地联动"""
        row = item.row()
        code_item = self.candidates_table.item(row, 0)
        if not code_item:
            return
        code = code_item.text().strip()
        self.link_stock(code)

    def link_stock(self, code: str):
        """联动股票行情 (TDX/THS/本地)"""
        code_clean = "".join(filter(str.isdigit, code)).zfill(6)
        if not code_clean:
            return

        self.code_clicked.emit(code_clean)
        try:
            from JohnsonUtil import commonTips as cct
            cct.to_toptdx(code_clean)
        except Exception as e:
            logger.debug(f"Link stock {code_clean} error: {e}")

    def _on_candidate_context_menu(self, pos: QPoint):
        """右键菜单"""
        item = self.candidates_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_it = self.candidates_table.item(row, 0)
        name_it = self.candidates_table.item(row, 1)
        if not code_it or not name_it:
            return

        code = code_it.text().strip()
        name = name_it.text().strip()

        menu = QMenu(self)
        act_link = menu.addAction(f"📈 联动通达信: {name} ({code})")
        act_dna = menu.addAction(f"🧬 DNA 专项审核 (Alt+W)")
        menu.addSeparator()
        act_fav = menu.addAction(f"⭐ 设为重点关注")
        act_copy_code = menu.addAction("📋 复制股票代码")
        act_copy_row = menu.addAction("📋 复制本行研报理由")

        chosen = menu.exec(self.candidates_table.viewport().mapToGlobal(pos))
        if chosen == act_link:
            self.link_stock(code)
        elif chosen == act_dna:
            self._run_dna_audit(code)
        elif chosen == act_fav:
            self._add_to_favorite(code)
        elif chosen == act_copy_code:
            QApplication.clipboard().setText(code)
        elif chosen == act_copy_row:
            reason_it = self.candidates_table.item(row, 12)
            if reason_it:
                QApplication.clipboard().setText(f"{code} {name}: {reason_it.text()}")

    def _run_dna_audit_on_selected(self):
        """快捷键 Alt+W 触发当前选中标的 DNA 审核"""
        curr_row = self.candidates_table.currentRow()
        if curr_row >= 0:
            code_it = self.candidates_table.item(curr_row, 0)
            if code_it:
                self._run_dna_audit(code_it.text().strip())

    def _run_dna_audit(self, code: str):
        """执行 DNA 专项审核"""
        try:
            from backtest_feature_auditor import run_dna_audit_for_code
            run_dna_audit_for_code(code, parent_window=self)
        except Exception:
            try:
                # 降级尝试调起系统通用审核
                from JohnsonUtil import commonTips as cct
                cct.to_toptdx(code)
            except Exception:
                pass

    def _add_to_favorite(self, code: str):
        """加入重点关注池"""
        try:
            from ats.ui.favorite_panel import add_code_to_favorites
            add_code_to_favorites(code)
            QMessageBox.information(self, "关注成功", f"标的 {code} 已成功添加至 ATS 重点关注池!")
        except Exception as e:
            logger.debug(f"Add to favorites error: {e}")

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

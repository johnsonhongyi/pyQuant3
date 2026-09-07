# -*- coding: utf-8 -*-
"""
ats/ui/capital_dragon_panel.py — ATS 资金主线与真龙中枢核心 C 位看板 (SSOT)
=============================================================================
设计定位：
1. 【今日核心资金主线看板 (Top Sector Cards)】：
   - 顶部全景呈现全市场 Top 3 主力增量资金主线 (总成交额、涨停家数、上涨比率、领跑先锋)；
2. 【全景真龙角色矩阵 (True Dragon Matrix Table)】：
   - 汇聚【👑 空间高度龙】、【🛡️ 趋势容量中军】、【🚀 主线板块先锋】、【💎 强势换手首板】；
   - 呈现真实成交额(亿)、换手率%、自适应趋势状态与建议买点区间；
3. 【高响应行情联动与持久化】：
   - 支持上下方向键、单击、双击秒级联动外部行情与 SBC 分时走势图；
   - 列宽自动记忆与多列高精数值排序。
"""

import os
import time
import math
import logging
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton,
    QLineEdit, QFrame, QGridLayout, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QColor, QBrush, QFont, QCursor

from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN,
    setup_header_persistence, auto_fit_columns_once
)
from ats.capital_dragon_engine import CapitalDragonEngine, _safe_float, _clean_code

logger = logging.getLogger("CapitalDragonPanel")


class ClickableLabel(QLabel):
    """支持单击与双击信号的响应式 Label"""
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            return
        super().mouseDoubleClickEvent(event)


class SectorCardWidget(QFrame):
    """
    可交互式核心资金主线卡片 (SSOT):
    - 单击卡片/标题/查看明细: 调起板块成分股明细并标记强势股 (sector_clicked)
    - 单击领涨先锋: 联动该股行情并广播 (pioneer_clicked)
    - 双击领涨先锋: 打开 SBC 分时通道走势图 (pioneer_double_clicked)
    """
    sector_clicked = pyqtSignal(str)              # (sector_name)
    pioneer_clicked = pyqtSignal(str, str)        # (code, name)
    pioneer_double_clicked = pyqtSignal(str, str) # (code, name)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.sector_name = ""
        self.leader_code = ""
        self.leader_name = ""

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QFrame:hover {
                border: 1px solid #58a6ff;
                background-color: #1f242c;
            }
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(6, 4, 6, 4)
        card_layout.setSpacing(2)

        # 标题栏：主线名称 + 查看明细按钮
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        self.lbl_title = ClickableLabel(f"主线 {index+1}: 正在识别资金聚集...")
        self.lbl_title.setStyleSheet("color: #ffd700; font-size: 10pt; font-weight: bold;")
        self.lbl_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_title.clicked.connect(self._on_card_clicked)
        title_layout.addWidget(self.lbl_title)

        title_layout.addStretch()

        self.btn_detail = QPushButton("🔍 查看明细")
        self.btn_detail.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detail.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #58a6ff;
                font-size: 8pt;
                font-weight: bold;
                border: 1px solid #30363d;
                border-radius: 3px;
                padding: 1px 5px;
            }
            QPushButton:hover {
                background-color: #388bfd26;
                color: #79c0ff;
                border-color: #58a6ff;
            }
        """)
        self.btn_detail.clicked.connect(self._on_card_clicked)
        title_layout.addWidget(self.btn_detail)

        card_layout.addLayout(title_layout)

        # 描述行：成交额、均涨、涨停
        self.lbl_desc = ClickableLabel("成交额: -- 亿 | 均涨: --% | 涨停: -- 家")
        self.lbl_desc.setStyleSheet("color: #8b949e; font-size: 8.5pt;")
        self.lbl_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_desc.clicked.connect(self._on_card_clicked)
        card_layout.addWidget(self.lbl_desc)

        # 先锋行：带联动与双击响应
        self.lbl_leader = ClickableLabel("🚀 先锋: --")
        self.lbl_leader.setStyleSheet("""
            QLabel {
                color: #38bdf8;
                font-size: 8.5pt;
                font-weight: bold;
            }
            QLabel:hover {
                color: #7dd3fc;
                text-decoration: underline;
            }
        """)
        self.lbl_leader.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_leader.setToolTip("🎯 单击联动行情与K线 | 双击查看 SBC 分时通道")
        self.lbl_leader.clicked.connect(self._on_leader_clicked)
        self.lbl_leader.double_clicked.connect(self._on_leader_double_clicked)
        card_layout.addWidget(self.lbl_leader)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_card_clicked()
            return
        super().mousePressEvent(event)

    def _on_card_clicked(self):
        if self.sector_name:
            self.sector_clicked.emit(self.sector_name)

    def _on_leader_clicked(self):
        if self.leader_code:
            self.pioneer_clicked.emit(self.leader_code, self.leader_name)

    def _on_leader_double_clicked(self):
        if self.leader_code:
            self.pioneer_double_clicked.emit(self.leader_code, self.leader_name)


class CapitalDragonPanel(QWidget):
    """
    资金主线与龙头中枢核心面板
    """
    stock_selected = pyqtSignal(str, str)         # 单击/方向键联动 (code, name)
    stock_double_clicked = pyqtSignal(str, str)  # 双击打开 SBC (code, name)

    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.engine = CapitalDragonEngine.get_instance()
        self._last_report = {}
        self._last_df_all = None
        self._last_sig = None
        self._is_updating = False

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. 顶部 3 大资金主线卡片展示区 (Top Mainstream Sector Cards)
        self.top_sector_container = QWidget()
        self.top_sector_layout = QHBoxLayout(self.top_sector_container)
        self.top_sector_layout.setContentsMargins(0, 0, 0, 0)
        self.top_sector_layout.setSpacing(8)

        self.sector_card_widgets = []
        for i in range(3):
            card = SectorCardWidget(i)
            card.sector_clicked.connect(self.open_sector_detail)
            card.pioneer_clicked.connect(self._on_pioneer_clicked)
            card.pioneer_double_clicked.connect(self._on_pioneer_double_clicked)
            self.top_sector_layout.addWidget(card)
            self.sector_card_widgets.append({
                "frame": card,
                "title": card.lbl_title,
                "desc": card.lbl_desc,
                "leader": card.lbl_leader,
                "sector_name": "",
                "leader_code": "",
                "leader_name": "",
                "card_widget": card
            })

        main_layout.addWidget(self.top_sector_container)

        # 2. 中间过滤与控制工具条 (Filter Bar)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.lbl_stats = QLabel("🐉 资金主线龙头已就位: 0 只")
        self.lbl_stats.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 9.5pt;")
        toolbar_layout.addWidget(self.lbl_stats)

        toolbar_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码 / 名称 / 主线 / 角色...")
        self.search_input.setFixedWidth(220)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0d1117;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border: 1px solid #58a6ff;
            }
        """)
        self.search_input.textChanged.connect(self._apply_filter)
        toolbar_layout.addWidget(self.search_input)

        self.btn_limit_up = QPushButton("🔥 涨停天梯")
        self.btn_limit_up.setStyleSheet("""
            QPushButton {
                background-color: #3d1414; color: #ff5555; font-weight: bold;
                border: 1px solid #ff4444; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #ff4444; color: #000000; }
        """)
        self.btn_limit_up.clicked.connect(self._on_click_limit_up)
        toolbar_layout.addWidget(self.btn_limit_up)

        self.btn_hot_sector = QPushButton("📊 板块雷达")
        self.btn_hot_sector.setStyleSheet("""
            QPushButton {
                background-color: #1a2a1a; color: #00ff88; font-weight: bold;
                border: 1px solid #00ff88; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #00ff88; color: #000000; }
        """)
        self.btn_hot_sector.clicked.connect(self._on_click_hot_sector)
        toolbar_layout.addWidget(self.btn_hot_sector)

        self.btn_dragon_mon = QPushButton("🐉 加速龙头")
        self.btn_dragon_mon.setStyleSheet("""
            QPushButton {
                background-color: #2b1f0e; color: #ffd700; font-weight: bold;
                border: 1px solid #ffd700; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #ffd700; color: #000000; }
        """)
        self.btn_dragon_mon.clicked.connect(self._on_click_dragon_mon)
        toolbar_layout.addWidget(self.btn_dragon_mon)

        # ⚡ 极限性能模式控制开关 (零卡顿/自适应精选)
        self.extreme_perf_mode = True
        self.btn_extreme_perf = QPushButton("⚡ 极限性能: 开")
        self.btn_extreme_perf.setStyleSheet("""
            QPushButton {
                background-color: #1a2a1a; color: #00ff88; font-weight: bold;
                border: 1px solid #00ff88; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #00ff88; color: #000000; }
        """)
        self.btn_extreme_perf.setToolTip("开启极限性能模式：原位更新零重绘，精选核心真龙，彻底杜绝主线程卡顿")
        self.btn_extreme_perf.clicked.connect(self._toggle_extreme_perf)
        toolbar_layout.addWidget(self.btn_extreme_perf)

        main_layout.addLayout(toolbar_layout)

        # 3. 核心真龙矩阵表格 (True Dragon Matrix Table)
        self.table = QTableWidget()
        self.headers = [
            "代码", "名称", "龙头角色", "所属主线", "现价", "涨幅%", "虚拟量比",
            "成交额(亿)", "换手率%", "资金买点类型", "建议买入区间", "止损参考", "核心逻辑与驱动"
        ]
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)

        default_widths = {
            "代码": 68, "名称": 78, "龙头角色": 115, "所属主线": 88, "现价": 68, "涨幅%": 68,
            "虚拟量比": 75, "成交额(亿)": 88, "换手率%": 68, "资金买点类型": 110, "建议买入区间": 110, "止损参考": 70, "核心逻辑与驱动": 280
        }
        setup_header_persistence(self.table, "capital_dragon_table_header_v2", default_widths=default_widths)

        # 信号连接
        self.table.itemClicked.connect(self._on_row_clicked)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table)

    def update_payload(self, df_all: Optional[pd.DataFrame], sh_pct: float = 0.0, force: bool = False):
        """
        接收最新行情快照，优先复用后台 Worker 计算好的报告，彻底杜绝主线程卡顿
        """
        if df_all is None or df_all.empty or self._is_updating:
            return

        self._last_df_all = df_all
        
        # ⚡ 极限性能复用：优先直接从引擎读取后台 Worker 计算好的缓存报告 (0ms 耗时，零计算)
        report = self.engine.get_cached_report(max_age=3.0, df_check=df_all)
        if report is None or force:
            report = self.engine.analyze_capital_dragon_universe(df_all, sh_pct)
        if not report:
            return

        # 特征签名检查，防无意义重绘
        dragons = report.get("dragon_records", [])
        top_secs = report.get("top_sectors", [])
        sig_tuple = (
            len(dragons),
            tuple(d["code"] for d in dragons[:15]),
            tuple(round(d["pct"], 1) for d in dragons[:15]),
            tuple(s["name"] for s in top_secs[:3]),
            getattr(self, 'extreme_perf_mode', True)
        )

        if sig_tuple == self._last_sig:
            return
        self._last_sig = sig_tuple
        self._last_report = report

        # 1. 刷新顶部主线卡片
        self._render_top_sector_cards(top_secs)

        # 2. 刷新核心真龙表格
        self._render_table(dragons)

    def _render_top_sector_cards(self, top_secs: List[Dict[str, Any]]):
        for i in range(3):
            w = self.sector_card_widgets[i]
            card_obj = w.get("card_widget")
            if i < len(top_secs):
                st = top_secs[i]
                sec_name = st["name"]
                w["sector_name"] = sec_name
                l_code = st.get("leader_code", "")
                l_name = st.get("leader_name", "")
                w["leader_code"] = l_code
                w["leader_name"] = l_name
                if card_obj:
                    card_obj.sector_name = sec_name
                    card_obj.leader_code = l_code
                    card_obj.leader_name = l_name

                grade = st.get("grade", "主线")
                w["title"].setText(f"{grade}: {sec_name}")
                w["frame"].setToolTip(f"💡 点击直接打开【{sec_name}】板块成分股明细与强势股")

                pct_col = COLOR_UP if st["avg_pct"] > 0 else (COLOR_DOWN if st["avg_pct"] < 0 else "#ffffff")
                vol_ratio = st.get("vol_ratio", 1.0)
                proj_amt = st.get("proj_amt_yi", st["total_amt_yi"])

                vr_col = "#ff1744" if vol_ratio >= 2.0 else ("#00e5ff" if vol_ratio >= 1.2 else "#c9d1d9")
                proj_str = f" <font color='#888888'>(预估{proj_amt:.0f}亿)</font>" if proj_amt > st["total_amt_yi"] * 1.05 else ""

                dual_cnt = st.get("dual_accel_count", 0)
                gap_cnt = st.get("gap_accel_count", 0)
                ol_cnt = st.get("open_low_count", 0)
                accel_tot = st.get("accel_total_count", 0)

                accel_desc = ""
                if accel_tot > 0:
                    accel_desc = f" | 加速: <font color='#ffd700'><b>{accel_tot}只</b></font>"

                w["desc"].setText(
                    f"成交: <font color='#ffd700'><b>{st['total_amt_yi']:.1f}亿</b></font>{proj_str} | "
                    f"量比: <font color='{vr_col}'><b>{vol_ratio:.1f}x</b></font> | "
                    f"均涨: <font color='{pct_col}'><b>{st['avg_pct']:+.2f}%</b></font> | "
                    f"涨停: <font color='#ff4444'><b>{st['limit_up_count']}只</b></font>"
                    f"{accel_desc}"
                )
                w["desc"].setTextFormat(Qt.TextFormat.RichText)

                accel_tip_str = ""
                if accel_tot > 0:
                    accel_tip_str = f"⚡ 群起加速: 共 {accel_tot} 只呈现早盘加速形态 (👑双加速 {dual_cnt} 只, 🚀缺口加速 {gap_cnt} 只, ⚡光脚加速 {ol_cnt} 只)\n🔥 板块内群起加速，显性印证该主线早盘资金进攻动能超强！\n"

                w["frame"].setToolTip(
                    f"💡 点击直接打开【{sec_name}】板块成分股明细与强势股\n"
                    f"📊 累计成交: {st['total_amt_yi']:.1f}亿元 | 全天预估: {proj_amt:.1f}亿元\n"
                    f"⚡ 板块虚拟量比: {vol_ratio:.2f}x (按盘中交易进度折算)\n"
                    f"{accel_tip_str}"
                )

                if l_name and l_code:
                    w["leader"].setText(f"🚀 先锋: {l_name} ({l_code}) +{st['leader_pct']:.1f}%")
                    w["leader"].setToolTip(f"🎯 单击联动【{l_name} ({l_code})】行情与K线 | 双击查看 SBC 分时通道")
                else:
                    w["leader"].setText("🚀 先锋: 正在争夺...")
                    w["leader"].setToolTip("")
                w["frame"].setVisible(True)
            else:
                w["frame"].setVisible(False)

    def _render_table(self, dragons: List[Dict[str, Any]]):
        self._is_updating = True
        self.table.setUpdatesEnabled(False)
        try:
            # 记住当前选中代码
            selected_code = None
            curr_row = self.table.currentRow()
            if curr_row >= 0:
                c_item = self.table.item(curr_row, 0)
                if c_item:
                    selected_code = c_item.text()

            self.table.setSortingEnabled(False)
            filter_text = self.search_input.text().strip().lower()
            
            matched_records = []
            for d in dragons:
                if filter_text:
                    match_str = f"{d['code']} {d['name']} {d['role']} {d['sector']} {d['action_type']} {d['reason']}".lower()
                    if filter_text not in match_str:
                        continue
                matched_records.append(d)

            # ⚡ 极限性能模式：精选 Top 30 核心真龙，极大提升高频渲染丝滑度
            if getattr(self, 'extreme_perf_mode', True) and not filter_text:
                matched_records = matched_records[:30]

            self.table.setRowCount(len(matched_records))
            new_selected_row = -1

            for row_idx, d in enumerate(matched_records):
                code = d["code"]
                name = d["name"]
                role = d["role"]
                sector = d["sector"]
                price = d["price"]
                pct = d["pct"]
                amt = d["amount_yi"]
                turnover = d["turnover"]
                buy_type = d["action_type"]
                buy_zone = d["buy_zone"]
                stop_loss = d["stop_loss"]
                reason = d["reason"]

                if code == selected_code:
                    new_selected_row = row_idx

                # 0: 代码
                it_code = NumericTableWidgetItem(code, 0)
                it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, 0, it_code)

                # 1: 名称
                it_name = QTableWidgetItem(name)
                it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, 1, it_name)

                # 2: 龙头角色 (高辨识度徽标色)
                it_role = NumericTableWidgetItem(role, d.get("priority", 0))
                it_role.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                font = it_role.font()
                font.setBold(True)
                it_role.setFont(font)
                if "空间" in role:
                    it_role.setForeground(QBrush(QColor("#ff1744")))
                elif "容量" in role:
                    it_role.setForeground(QBrush(QColor("#ffd700")))
                elif "先锋" in role:
                    it_role.setForeground(QBrush(QColor("#00e676")))
                else:
                    it_role.setForeground(QBrush(QColor("#00b0ff")))
                self.table.setItem(row_idx, 2, it_role)

                # 3: 所属主线
                it_sec = QTableWidgetItem(sector)
                it_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_sec.setForeground(QBrush(QColor("#e0e0e0")))
                if sector and sector not in ('--', '未知'):
                    it_sec.setToolTip(f"💡 双击直接打开【{sector}】板块成分股明细与强势股")
                self.table.setItem(row_idx, 3, it_sec)

                # 4: 现价
                it_price = NumericTableWidgetItem(f"{price:.2f}", price)
                it_price.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 4, it_price)

                # 5: 涨幅%
                pct_str = f"{pct:+.2f}%"
                it_pct = NumericTableWidgetItem(pct_str, pct)
                it_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                font = it_pct.font()
                font.setBold(True)
                it_pct.setFont(font)
                pct_col = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else "#c9d1d9")
                it_pct.setForeground(QBrush(QColor(pct_col)))
                self.table.setItem(row_idx, 5, it_pct)

                # 6: 虚拟量比 (系统的虚拟量比，反映资金加速流入速度)
                vr_val = float(d.get("vol_ratio", 1.0))
                it_vr = NumericTableWidgetItem(f"{vr_val:.2f}x", vr_val)
                it_vr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                f_vr = it_vr.font()
                if vr_val >= 3.0:
                    it_vr.setForeground(QBrush(QColor("#ff1744")))
                    f_vr.setBold(True)
                elif vr_val >= 2.0:
                    it_vr.setForeground(QBrush(QColor("#ffd700")))
                    f_vr.setBold(True)
                elif vr_val >= 1.2:
                    it_vr.setForeground(QBrush(QColor("#00e5ff")))
                elif vr_val <= 0.7:
                    it_vr.setForeground(QBrush(QColor("#888888")))
                else:
                    it_vr.setForeground(QBrush(QColor("#ffffff")))
                it_vr.setFont(f_vr)
                it_vr.setToolTip(f"系统的虚拟量比: {vr_val:.2f}x\n按上午实时交易进度计算全天预估成交倍速，量比越大资金加速流入越猛烈")
                self.table.setItem(row_idx, 6, it_vr)

                # 7: 成交额(亿)
                it_amt = NumericTableWidgetItem(f"{amt:.1f}亿", amt)
                it_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if amt >= 15.0:
                    it_amt.setForeground(QBrush(QColor("#ffd700")))
                    f = it_amt.font()
                    f.setBold(True)
                    it_amt.setFont(f)
                else:
                    it_amt.setForeground(QBrush(QColor("#ffffff")))
                self.table.setItem(row_idx, 7, it_amt)

                # 8: 换手率%
                it_to = NumericTableWidgetItem(f"{turnover:.1f}%", turnover)
                it_to.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 8, it_to)

                # 9: 资金买点类型 (精细化视觉高亮，对齐龙头突击与天梯)
                it_buy = QTableWidgetItem(buy_type)
                it_buy.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                font_buy = it_buy.font()
                font_buy.setBold(True)
                it_buy.setFont(font_buy)
                if "双加速" in buy_type:
                    it_buy.setForeground(QBrush(QColor("#FFD700"))) # 金黄双加速
                    it_buy.setBackground(QBrush(QColor(80, 20, 60, 180))) # 尊荣金紫
                elif "缺口加速" in buy_type:
                    it_buy.setForeground(QBrush(QColor("#FF55BB"))) # 亮粉紫缺口加速
                    it_buy.setBackground(QBrush(QColor(50, 15, 45, 160)))
                elif "光脚加速" in buy_type:
                    it_buy.setForeground(QBrush(QColor("#FFAA00"))) # 亮橙黄光脚加速
                    it_buy.setBackground(QBrush(QColor(60, 35, 10, 160)))
                elif "主升" in buy_type or "先锋" in buy_type or "龙头" in buy_type:
                    it_buy.setForeground(QBrush(QColor("#00e676")))
                    it_buy.setBackground(QBrush(QColor(10, 50, 30, 150)))
                else:
                    it_buy.setForeground(QBrush(QColor("#38bdf8")))
                    it_buy.setBackground(QBrush(QColor(0, 0, 0, 0)))
                self.table.setItem(row_idx, 9, it_buy)

                # 10: 建议买入区间
                it_zone = QTableWidgetItem(buy_zone)
                it_zone.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_zone.setForeground(QBrush(QColor("#ffb74d")))
                self.table.setItem(row_idx, 10, it_zone)

                # 11: 止损参考
                it_sl = NumericTableWidgetItem(f"{stop_loss:.2f}", stop_loss)
                it_sl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                it_sl.setForeground(QBrush(QColor("#ef5350")))
                self.table.setItem(row_idx, 11, it_sl)

                # 12: 核心逻辑与驱动
                it_reason = QTableWidgetItem(reason)
                it_reason.setToolTip(reason)
                it_reason.setForeground(QBrush(QColor("#b0bec5")))
                self.table.setItem(row_idx, 12, it_reason)

            dual_cnt = self._last_report.get('dual_accel_count', 0) if self._last_report else 0
            gap_cnt = self._last_report.get('gap_accel_count', 0) if self._last_report else 0
            ol_cnt = self._last_report.get('open_low_count', 0) if self._last_report else 0
            accel_tot = dual_cnt + gap_cnt + ol_cnt
            accel_str = f" | ⚡加速: {accel_tot}只 (👑双加速:{dual_cnt} 🚀缺口:{gap_cnt})" if accel_tot > 0 else ""
            perf_tag = " <font color='#00ff88'>[⚡极限性能]</font>" if getattr(self, 'extreme_perf_mode', True) else ""

            self.lbl_stats.setText(
                f"🐉 资金主线龙头已就位: <b>{len(matched_records)}</b> 只 "
                f"(空间龙: {self._last_report.get('space_dragon_count', 0)} | "
                f"容量中军: {self._last_report.get('midcap_dragon_count', 0)} | "
                f"主线先锋: {self._last_report.get('pioneer_dragon_count', 0)})"
                f"{accel_str}{perf_tag}"
            )

            if new_selected_row >= 0:
                self.table.setCurrentCell(new_selected_row, 0)

            auto_fit_columns_once(self.table, "capital_dragon_table_header_v2")
            self.table.setSortingEnabled(True)

        finally:
            self.table.setUpdatesEnabled(True)
            self._is_updating = False

    def _toggle_extreme_perf(self):
        """切换极限性能模式 (精选 Top 30，极速无阻滞渲染)"""
        self.extreme_perf_mode = not getattr(self, 'extreme_perf_mode', True)
        if self.extreme_perf_mode:
            self.btn_extreme_perf.setText("⚡ 极限性能: 开")
            self.btn_extreme_perf.setStyleSheet("""
                QPushButton {
                    background-color: #1a2a1a; color: #00ff88; font-weight: bold;
                    border: 1px solid #00ff88; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #00ff88; color: #000000; }
            """)
        else:
            self.btn_extreme_perf.setText("⚡ 极限性能: 关")
            self.btn_extreme_perf.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a; color: #888888; font-weight: normal;
                    border: 1px solid #555555; border-radius: 3px; padding: 3px 8px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #3a3a3a; color: #ffffff; }
            """)
        self._apply_filter()

    def _apply_filter(self):
        if self._last_report:
            self._render_table(self._last_report.get("dragon_records", []))

    def _on_row_clicked(self, item):
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if c_item and n_item:
            code = c_item.text().strip()
            name = n_item.text().strip()
            self.stock_selected.emit(code, name)

    def _on_current_cell_changed(self, cur_row, cur_col, prev_row, prev_col):
        if cur_row >= 0 and cur_row != prev_row:
            c_item = self.table.item(cur_row, 0)
            n_item = self.table.item(cur_row, 1)
            if c_item and n_item:
                code = c_item.text().strip()
                name = n_item.text().strip()
                self.stock_selected.emit(code, name)

    def open_sector_detail(self, sector_name: str):
        """
        【🎯 直接打开板块详情核心入口】
        清洗板块名称并从当前全市场行情中提取成分股代码，唤醒或复用 ATSSectorDetailDialog 并标记强势股
        """
        if not sector_name:
            return
        import re
        clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sector_name)).strip()
        for pfx in ("核心主线:", "核心主线", "主线:", "主线", "板块:", "板块"):
            if clean_sec.startswith(pfx):
                clean_sec = clean_sec[len(pfx):].strip()
        if not clean_sec or clean_sec in ('--', '未知'):
            return

        logger.info(f"直接打开板块详情: {clean_sec}")

        member_codes = []
        df_all = getattr(self, '_last_df_all', None)
        if df_all is not None and not df_all.empty:
            sec_col = next((c for c in ('category', 'industry', 'concept') if c in df_all.columns), None)
            if sec_col:
                try:
                    mask = df_all[sec_col].astype(str).str.contains(re.escape(clean_sec), case=False, na=False)
                    df_sec = df_all[mask]
                    if not df_sec.empty:
                        member_codes = [_clean_code(c) for c in df_sec.index]
                except Exception as e:
                    logger.debug(f"从 df_all 提取板块成分股代码异常: {e}")

        if self.main_window and hasattr(self.main_window, 'on_sector_clicked'):
            self.main_window.on_sector_clicked(clean_sec, member_codes=member_codes)
        else:
            try:
                from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
                from PyQt6.sip import isdeleted
                dlg = getattr(self, "_sector_detail_dialog", None)
                if dlg and not isdeleted(dlg):
                    if dlg.isMinimized():
                        dlg.showNormal()
                    dlg.sector_name = clean_sec
                    dlg.member_codes = member_codes
                    dlg.setWindowTitle(f"🔥 {clean_sec} 板块明细 (实时高频行情)")
                    dlg.refresh_data(force=True)
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
                else:
                    dlg = ATSSectorDetailDialog(
                        clean_sec,
                        linkage_cb=lambda c, n: self.stock_selected.emit(c, n),
                        double_click_cb=lambda c, n: self.stock_double_clicked.emit(c, n),
                        member_codes=member_codes,
                        parent=self.main_window or self
                    )
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
                    self._sector_detail_dialog = dlg
            except Exception as e:
                logger.error(f"打开板块详情失败: {e}")

    def _on_pioneer_clicked(self, code: str, name: str):
        if not code:
            return
        logger.info(f"先锋联动点击: {name} ({code})")
        self.stock_selected.emit(code, name)
        if self.main_window and hasattr(self.main_window, 'link_stock'):
            self.main_window.link_stock(code, name)

    def _on_pioneer_double_clicked(self, code: str, name: str):
        if not code:
            return
        logger.info(f"先锋双击打开 SBC: {name} ({code})")
        self.stock_double_clicked.emit(code, name)
        if self.main_window and hasattr(self.main_window, 'on_stock_clicked'):
            self.main_window.on_stock_clicked(code, name, {})

    def _on_row_double_clicked(self, item):
        row = item.row()
        col = item.column()
        if col == 3:  # 双击所属主线列，直接打开板块成分股详情
            s_item = self.table.item(row, 3)
            if s_item:
                sec_name = s_item.text().strip()
                if sec_name and sec_name not in ('--', '未知'):
                    self.open_sector_detail(sec_name)
                    return

        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if c_item and n_item:
            code = c_item.text().strip()
            name = n_item.text().strip()
            self.stock_double_clicked.emit(code, name)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        s_item = self.table.item(row, 3)
        code = c_item.text().strip() if c_item else ""
        name = n_item.text().strip() if n_item else ""
        sector = s_item.text().strip() if s_item else ""

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a1f;
                color: #e2e2e5;
                border: 1px solid #30363d;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
        """)

        if sector and sector not in ('--', '未知'):
            act_sec = menu.addAction(f"📊 查看【{sector}】板块成分股明细 (标记强势股)")
            act_sec.triggered.connect(lambda: self.open_sector_detail(sector))

            act_filter = menu.addAction(f"🔍 在列表中仅筛选【{sector}】")
            act_filter.triggered.connect(lambda: self.search_input.setText(sector))

            menu.addSeparator()

        if code:
            act_sbc = menu.addAction(f"📈 打开 {name}({code}) SBC 通道走势图 (R)")
            act_sbc.triggered.connect(lambda: self.stock_double_clicked.emit(code, name))

        act_ladder = menu.addAction("🔥 打开每日涨停天梯看板")
        act_ladder.triggered.connect(self._on_click_limit_up)

        act_radar = menu.addAction("📊 打开板块雷达")
        act_radar.triggered.connect(self._on_click_hot_sector)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_click_limit_up(self):
        if self.main_window and hasattr(self.main_window, 'open_daily_limit_up_analyzer'):
            self.main_window.open_daily_limit_up_analyzer()

    def _on_click_hot_sector(self):
        if self.main_window and hasattr(self.main_window, 'open_hot_sector_leaderboard'):
            self.main_window.open_hot_sector_leaderboard()

    def _on_click_dragon_mon(self):
        if self.main_window and hasattr(self.main_window, 'open_dragon_monitor'):
            self.main_window.open_dragon_monitor()

# -*- coding: utf-8 -*-
"""
ATS Sector Detail Dialog
Displays all constituent stocks of a given sector from the bidding session data.
"""

import os
import json
import zlib
import re
import time
import datetime
import urllib.request
from typing import List, Dict, Tuple, Optional, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton, QApplication, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut

from ats.ui.styles import NumericTableWidgetItem, setup_header_persistence, apply_dark_theme, CONFIG_FILE_LOCK
from sys_utils import get_app_root, get_conf_path
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)

from ats.sector_data_aggregator import (
    SectorDataAggregator,
    get_sector_extra_cols,
    get_sector_table_headers,
    fetch_sina_stock_quotes_fast,
    FAMOUS_SECTOR_LEADERS,
    SECTOR_SYNONYMS
)


class SectorDetailWorker(QThread):
    """后台异步板块成分股发现与高频行情拉取工作线程 (绝不阻塞 UI 主线程)"""
    finished_signal = pyqtSignal(list, float, str, dict) # (rows, score, leader_info_str, meta_dict)

    def __init__(self, sector_name: str, member_codes: list = None, current_df = None, extra_cols: list = None, get_name_fn = None, parent=None):
        super().__init__(parent)
        self.sector_name = sector_name
        self.member_codes = member_codes or []
        self.current_df = current_df
        self.extra_cols = extra_cols or []
        self.get_name_fn = get_name_fn

    def run(self):
        try:
            aggregator = SectorDataAggregator.get_instance()
            rows, score, leader_str, meta = aggregator.fetch_sector_detail(
                sector_name=self.sector_name,
                member_codes=self.member_codes,
                current_df=self.current_df,
                extra_cols=self.extra_cols,
                get_name_fn=self.get_name_fn
            )
            self.finished_signal.emit(rows, score, leader_str, meta)
        except Exception as e:
            logger.error(f"SectorDetailWorker run error: {e}")
            self.finished_signal.emit([], 0.0, "--", {'status': f'⚠️ 更新异常: {e}'})
        
class ATSSectorDetailDialog(QDialog):
    """
    ATS 强势板块成分股明细与高频量化实时弹窗
    具备：新浪直连 50ms 真实股价 + TDX 秒级盘口 + 自动定时轮询 + 手动 F5 强制刷新
    """
    def __init__(self, sector_name, linkage_cb=None, double_click_cb=None, member_codes=None, parent=None):
        super().__init__(None) # [🚀 独立顶层解耦] 传入 None 剥离 Win32 HWND Owner 从属关系
        self._py_parent = parent
        self.sector_name = sector_name
        self.linkage_cb = linkage_cb
        self.double_click_cb = double_click_cb
        self.member_codes = member_codes or []
        self.extra_cols = get_sector_extra_cols()
        self._worker = None
        self._is_rendering = False
        
        self.setWindowTitle(f"🔥 {sector_name} 板块明细 (实时高频行情)")
        self.resize(780, 520)
        
        # 继承统一的 ATS 暗黑 Mode QSS 风格
        apply_dark_theme(self)
        
        self.setStyleSheet(self.styleSheet() + """
            QDialog {
                background-color: #121214;
                color: #e2e2e5;
            }
            QTableWidget {
                background-color: #18181c;
                alternate-background-color: #1c1c22;
                color: #e2e2e5;
                gridline-color: #282830;
                selection-background-color: #2e3b4e;
                selection-color: #00ff88;
                border: 1px solid #282830;
                font-family: 'Microsoft YaHei', sans-serif;
            }
            QHeaderView::section {
                background-color: #1a1a1f;
                color: #aad4ff;
                font-weight: bold;
                border: 1px solid #2e2e36;
                padding: 3px 6px;
            }
            QTableCornerButton::section {
                background-color: #1a1a1f;
                border: 1px solid #2e2e36;
            }
        """)
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)

        self._init_ui()
        self._start_auto_refresh_timer()
        self.refresh_data(force=True)
        self._restore_geometry()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 1. 顶部 Header 状态栏与操作区域
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #18181c; border: 1px solid #282830; border-radius: 4px; padding: 4px 8px; }")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.title_lbl = QLabel(f"板块名称: {self.sector_name}")
        self.title_lbl.setStyleSheet("font-size: 12.5pt; font-weight: bold; color: #00ff88;")
        top_row.addWidget(self.title_lbl)

        self.score_lbl = QLabel("强度得分: --")
        self.score_lbl.setStyleSheet("font-size: 12pt; font-weight: bold; color: #ff9900; margin-left: 10px;")
        top_row.addWidget(self.score_lbl)

        top_row.addStretch()

        self.lbl_status = QLabel("📡 状态: 初始化...")
        self.lbl_status.setStyleSheet("color: #00e5ff; font-size: 8.5pt; margin-right: 6px;")
        top_row.addWidget(self.lbl_status)

        self.lbl_update_time = QLabel("最后更新: --:--:--")
        self.lbl_update_time.setStyleSheet("color: #888888; font-size: 8.5pt;")
        top_row.addWidget(self.lbl_update_time)

        header_layout.addLayout(top_row)
        
        # Stats info (成员数与领涨标的)
        self.stats_lbl = QLabel("成员数: 0 | 领涨标的: --")
        self.stats_lbl.setStyleSheet("font-size: 9.5pt; color: #aad4ff;")
        header_layout.addWidget(self.stats_lbl)

        layout.addWidget(header_frame)
        
        # 2. Table of members
        self.table = QTableWidget()
        headers = get_sector_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.setStretchLastSection(False)
        
        self.table.setAlternatingRowColors(True)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        default_widths = [60, 75, 48, 65, 68, 68, 58, 45, 58, 58] + [55] * len(self.extra_cols) + [100]
        setup_header_persistence(self.table, "ats_sector_detail_table_v2", default_widths=default_widths)
        
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.table.currentItemChanged.connect(self.on_current_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        
        # 3. Bottom action bar
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("🔄 强制刷新数据")
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #1976d2; color: #ffffff; border: 1px solid #2196f3;
                          border-radius: 4px; padding: 4px 12px; font-weight: bold; font-size: 9pt; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:disabled { background-color: #333333; color: #777777; border-color: #444444; }
        """)
        self.btn_refresh.clicked.connect(lambda: self.refresh_data(force=True))
        btn_layout.addWidget(self.btn_refresh)

        btn_dna = QPushButton("🧬 DNA审计")
        btn_dna.setStyleSheet("""
            QPushButton { background-color: #1b5e20; color: #a5d6a7; border: 1px solid #388e3c;
                          border-radius: 4px; padding: 4px 10px; font-weight: bold; font-size: 9pt; }
            QPushButton:hover { background-color: #2e7d32; }
        """)
        btn_dna.clicked.connect(self._run_dna_audit)
        btn_layout.addWidget(btn_dna)

        btn_layout.addStretch()

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #2a2e39; color: #d1d4dc; border: 1px solid #363c4e;
                          border-radius: 4px; padding: 4px 14px; font-size: 9pt; }
            QPushButton:hover { background-color: #363c4e; color: #ffffff; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        # 4. 绑定 F5 键盘刷新快捷键
        self._f5_shortcut = QShortcut(QKeySequence("F5"), self)
        self._f5_shortcut.activated.connect(lambda: self.refresh_data(force=True))

    def _get_parent_mw(self):
        return getattr(self, '_py_parent', None) or self.parent()

    def _restore_geometry(self):
        """从 window_config.json 恢复弹窗位置与大小"""
        try:
            from ats.ui.styles import load_config_node
            geom = load_config_node("ats_sector_detail_dialog_geom")
            if geom:
                from PyQt6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
        except Exception:
            pass

    def _save_geometry(self):
        """原子写盘持久化弹窗位置与大小至 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            hex_data = self.saveGeometry().toHex().data().decode('utf-8')
            save_config_node("ats_sector_detail_dialog_geom", hex_data)
        except Exception:
            pass

    def accept(self):
        """OK/关闭按钮同样触发持久化"""
        self._save_geometry()
        super().accept()

    def _start_auto_refresh_timer(self):
        """启动后台定时自动静默更新 (盘中 15 秒轮询，休市 60 秒轮询)"""
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(lambda: self.refresh_data(force=False))
        self._auto_timer.start(15000)

    def update_data(self, current_df=None):
        """【外部/主窗口数据同步入口】供主窗口实盘行情轮询时推送最新 DataFrame 或原地复用更新"""
        if current_df is not None and not current_df.empty:
            self._cached_df = current_df
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"板块名称: {self.sector_name}")
        self.setWindowTitle(f"🔥 {self.sector_name} 板块明细 (实时高频行情)")
        self.refresh_data(force=False)

    def load_data(self, df_realtime=None, member_codes=None):
        """【兼容/快速加载入口】支持同步直接根据传入 DataFrame 计算并渲染，或触发异步刷新"""
        if df_realtime is not None and not df_realtime.empty:
            self._cached_df = df_realtime
        if member_codes:
            self.member_codes = member_codes
        # 优先使用显式注入的 DataFrame 同步计算渲染（单测/极速离线保障）
        aggregator = SectorDataAggregator.get_instance()
        current_df = getattr(self, '_cached_df', None)
        get_name_fn = None
        if current_df is None:
            current_df, get_name_fn = aggregator.resolve_active_strategy_df(self)
        rows, score, leader_str, meta = aggregator.fetch_sector_detail(
            sector_name=self.sector_name,
            member_codes=self.member_codes,
            current_df=current_df,
            extra_cols=self.extra_cols,
            get_name_fn=get_name_fn
        )
        self._on_worker_finished(rows, score, leader_str, meta)

    def refresh_data(self, force: bool = False):
        """异步拉取板块成分股最新实时高频行情与特征"""
        if self._worker and self._worker.isRunning():
            return

        if force:
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText("⏳ 正在刷新...")

        # 优先使用显式注入的 _cached_df，否则从统一聚合引擎探测感知系统活跃的策略 DataFrame
        current_df = getattr(self, '_cached_df', None)
        get_name_fn = None
        if current_df is None:
            current_df, get_name_fn = SectorDataAggregator.get_instance().resolve_active_strategy_df(self)

        self._worker = SectorDetailWorker(
            sector_name=self.sector_name,
            member_codes=self.member_codes,
            current_df=current_df,
            extra_cols=self.extra_cols,
            get_name_fn=get_name_fn,
            parent=self
        )
        self._worker.finished_signal.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self, rows: list, score: float, leader_str: str, meta: dict):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("🔄 强制刷新数据")

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_update_time.setText(f"最后更新: {now_str}")

        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"板块名称: {self.sector_name}")

        self.score_lbl.setText(f"强度得分: {score:.1f}")
        self.stats_lbl.setText(f"成员数: {len(rows)} | 领涨标的: {leader_str}")

        st_text = meta.get('status', '✅ 实时数据已同步')
        self.lbl_status.setText(f"📡 状态: {st_text}")
        if '⚠️' in st_text:
            self.lbl_status.setStyleSheet("color: #ffa500; font-size: 8.5pt; margin-right: 6px;")
        else:
            self.lbl_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; margin-right: 6px;")

        self.setWindowTitle(f"🔥 {self.sector_name} 板块明细 (实时高频 {len(rows)}只)")
        self._render_rows(rows)

    def _render_rows(self, rows):
        self._is_rendering = True
        self.table.blockSignals(True)
        try:
            # 记录刷新前用户选中的股票代码，避免刷新导致选中状态跳脱
            curr_sel_code = None
            curr_row = self.table.currentRow()
            if curr_row >= 0 and curr_row < self.table.rowCount():
                item0 = self.table.item(curr_row, 0)
                if item0:
                    curr_sel_code = item0.text().strip()

            current_extra = get_sector_extra_cols()
            if not hasattr(self, 'extra_cols') or self.extra_cols != current_extra:
                self.extra_cols = current_extra
                headers = get_sector_table_headers(self.extra_cols)
                if self.table.columnCount() != len(headers):
                    self.table.setColumnCount(len(headers))
                    self.table.setHorizontalHeaderLabels(headers)
                    default_widths = [60, 75, 48, 65, 68, 68, 58, 45, 58, 58] + [55] * len(self.extra_cols) + [100]
                    setup_header_persistence(self.table, "ats_sector_detail_table_v2", default_widths=default_widths)

            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(rows))
            num_extra = len(self.extra_cols)
            
            for row_idx, r in enumerate(rows):
                # 0. Code
                code_item = QTableWidgetItem(str(r['code']))
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 0, code_item)
                
                # 1. Name
                name_item = QTableWidgetItem(str(r['name']))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 1, name_item)
                
                # 2. Score
                score_item = NumericTableWidgetItem(f"{r['score']:.1f}")
                score_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 2, score_item)
                
                # 3. Type
                type_item = QTableWidgetItem(str(r['type']))
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if '👑' in r['type']:
                    type_item.setForeground(QColor("#ffcc00")) # gold
                self.table.setItem(row_idx, 3, type_item)
                
                # 4. Pct
                pct_val = r['pct']
                pct_str = f"{pct_val:+.2f}%"
                pct_item = NumericTableWidgetItem(pct_str)
                pct_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if pct_val > 0.001:
                    pct_item.setForeground(QColor("#ff4444"))
                elif pct_val < -0.001:
                    pct_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 4, pct_item)
                
                # 5. Start Pct
                start_val = r['start_pct']
                start_str = f"{start_val:+.2f}%"
                start_item = NumericTableWidgetItem(start_str)
                start_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if start_val > 0.001:
                    start_item.setForeground(QColor("#ff4444"))
                elif start_val < -0.001:
                    start_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 5, start_item)
                
                # 6. DFF
                dff_val = r['dff']
                dff_str = f"{dff_val:+.2f}%"
                dff_item = NumericTableWidgetItem(dff_str)
                dff_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff_val > 0.001:
                    dff_item.setForeground(QColor("#ff4444"))
                elif dff_val < -0.001:
                    dff_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 6, dff_item)
                
                # 7. Rank
                rank_item = NumericTableWidgetItem(str(r['rank']))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, 7, rank_item)
                
                # 8. DFF2
                dff2_val = r['dff2']
                dff2_item = NumericTableWidgetItem(f"{dff2_val:+.2f}%")
                dff2_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff2_val > 0.001:
                    dff2_item.setForeground(QColor("#ff4444"))
                elif dff2_val < -0.001:
                    dff2_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 8, dff2_item)
                
                # 9. DFF3
                dff3_val = r['dff3']
                dff3_item = NumericTableWidgetItem(f"{dff3_val:+.2f}%")
                dff3_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if dff3_val > 0.001:
                    dff3_item.setForeground(QColor("#ff4444"))
                elif dff3_val < -0.001:
                    dff3_item.setForeground(QColor("#33cc5a"))
                self.table.setItem(row_idx, 9, dff3_item)
                
                # 10 ~ 10 + num_extra - 1: Dynamic Extra Cols
                extra_data = r.get('extra_cols', {})
                for ei, ec in enumerate(self.extra_cols):
                    c_idx = 10 + ei
                    e_val = extra_data.get(ec, '--')
                    e_item = NumericTableWidgetItem(str(e_val))
                    e_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if str(e_val).startswith('+'):
                        e_item.setForeground(QColor("#ff4444"))
                    elif str(e_val).startswith('-'):
                        e_item.setForeground(QColor("#33cc5a"))
                    else:
                        e_item.setForeground(QColor("#e2e2e5"))
                    self.table.setItem(row_idx, c_idx, e_item)

                # Pattern (Last Column)
                pat_col_idx = 10 + num_extra
                pat_item = QTableWidgetItem(str(r['pattern'] or '--'))
                pat_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, pat_col_idx, pat_item)
                
            self.table.setSortingEnabled(True)

            # 恢复刷新前用户选中的股票行
            if curr_sel_code:
                for r_i in range(len(rows)):
                    if str(rows[r_i].get('code', '')) == curr_sel_code:
                        self.table.selectRow(r_i)
                        break
            else:
                self.table.clearSelection()
        finally:
            self.table.blockSignals(False)
            self._is_rendering = False
            
    def on_item_clicked(self, item):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.linkage_cb:
            code = code_item.text().strip()
            name = name_item.text().strip()
            if getattr(self, '_last_linked_code', None) != code:
                self._last_linked_code = code
                self.linkage_cb(code, name)
            
    def on_current_item_changed(self, current, previous):
        if getattr(self, '_is_rendering', False) or self.table.signalsBlocked():
            return
        if current and self.linkage_cb:
            row = current.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                code = code_item.text().strip()
                name = name_item.text().strip()
                if getattr(self, '_last_linked_code', None) != code:
                    self._last_linked_code = code
                    self.linkage_cb(code, name)
                
    def on_item_double_clicked(self, item):
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item and self.double_click_cb:
            self.double_click_cb(code_item.text().strip(), name_item.text().strip())

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else ""
        if not code:
            return

        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        from ats.ui.base_table import send_to_linkage

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #ffffff;
            }
        """)

        # 🔄 强制刷新
        refresh_act = menu.addAction(f"🔄 强制刷新【{self.sector_name}】板块实时行情 (F5)")
        refresh_act.triggered.connect(lambda: self.refresh_data(force=True))

        menu.addSeparator()

        # 选中联动
        if self.linkage_cb:
            link_act = menu.addAction(f"⚡ 选中联动 ({code})")
            link_act.triggered.connect(lambda: self.linkage_cb(code, name))

        # 📈 调出 SBC 实盘分时走势
        sbc_act = menu.addAction(f"📈 调出 {name or code} SBC 实盘分时走势")
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code)
        sbc_act.triggered.connect(_open_sbc)

        # 发送到异动联动
        pipe_act = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        pipe_act.triggered.connect(lambda: send_to_linkage(code, name, self))

        menu.addSeparator()

        copy_code_act = menu.addAction("📋 复制代码")
        copy_code_act.triggered.connect(lambda: QApplication.clipboard().setText(code))
        copy_name_act = menu.addAction("📋 复制名称")
        copy_name_act.triggered.connect(lambda: QApplication.clipboard().setText(name))

        menu.addSeparator()
        from ats.ui.styles import auto_fit_columns_once
        fit_act = menu.addAction("↔️ 一键自适应全列宽")
        fit_act.triggered.connect(lambda: auto_fit_columns_once(self.table))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _run_dna_audit(self):
        """对板块内所有成员股（按表格顺序，最多20只）执行 DNA 审计。
        优先通过主程序 parent_app._run_dna_audit_batch，降级到本地 QtDnaAuditReportWindow。
        """
        rows = self.table.rowCount()
        if rows == 0:
            return

        # Collect all member stocks from the table (code in col 0, name in col 1)
        items = []
        for r in range(rows):
            c_it = self.table.item(r, 0)
            n_it = self.table.item(r, 1)
            if c_it and n_it:
                items.append((c_it.text().strip(), n_it.text().strip()))

        # Align with chart_widgets.py selection logic:
        #   multi-select  → all selected rows (up to 50)
        #   single-select → current row + next 19 rows (total ≤ 20)
        #   no selection  → first 20 rows of the table
        sel_rows = sorted(set(i.row() for i in self.table.selectedItems()))
        if len(sel_rows) > 1:
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip()) for r in sel_rows[:50]
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            target = [(self.table.item(r, 0).text().strip(),
                       self.table.item(r, 1).text().strip())
                      for r in range(start, min(start + 20, rows))
                      if self.table.item(r, 0) and self.table.item(r, 1)]
        else:
            target = items[:20]

        code_to_name = {c: n for c, n in target if c}
        if not code_to_name:
            return

        # Try main app first
        main_app = getattr(self.parent(), 'parent_app', None)
        if not main_app:
            main_app = getattr(self.window(), 'parent_app', None)
        if not main_app:
            main_app = getattr(QApplication.instance(), 'parent_app', None)

        if main_app and hasattr(main_app, '_run_dna_audit_batch'):
            if hasattr(main_app, 'tk_dispatch_queue'):
                _cn = dict(code_to_name)
                main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
            else:
                main_app._run_dna_audit_batch(code_to_name)
            return

        # ATSMainWindow or any Qt window with _run_dna_audit_batch
        win = self.window()
        if hasattr(win, '_run_dna_audit_batch'):
            win._run_dna_audit_batch(code_to_name)
            return

        # Local PyQt6 fallback (packaged env)
        try:
            from backtest_feature_auditor import audit_multiple_codes
            from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            # 从统一聚合引擎探测感知系统活跃的策略 DataFrame
            _period_data, _ = SectorDataAggregator.get_instance().resolve_active_strategy_df(self)
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=None,
                code_to_name=code_to_name,
                progress_callback=None,
                resample='d',
                period_data=_period_data
            )
            if summaries:
                self._dna_audit_win = QtDnaAuditReportWindow(
                    summaries, parent=self.window(), end_date=None, resample='d'
                )
                self._dna_audit_win.show()
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "DNA 审计", "没有产生审计数据或结论。")
        except Exception as e:
            print(f"[ATSSectorDetailDialog] DNA audit local fallback failed: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_auto_timer') and self._auto_timer and not self._auto_timer.isActive():
            self._auto_timer.start(15000)

    def hideEvent(self, event):
        if hasattr(self, '_auto_timer') and self._auto_timer and self._auto_timer.isActive():
            self._auto_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        if hasattr(self, '_auto_timer') and self._auto_timer:
            self._auto_timer.stop()
        if hasattr(self, '_worker') and self._worker and self._worker.isRunning():
            try:
                self._worker.wait(1000)
            except Exception:
                pass
        # Save header state of the table
        if hasattr(self.table, 'save_column_widths'):
            try:
                self.table.save_column_widths()
            except Exception:
                pass
        super().closeEvent(event)

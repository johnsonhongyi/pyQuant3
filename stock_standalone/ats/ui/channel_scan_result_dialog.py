# -*- coding: utf-8 -*-
"""
ats/ui/channel_scan_result_dialog.py — 60f 通道策略批量测算统计与联动独立窗口
具备高品质量化深色主题、形态统计卡片、全字段结果表格、单击/双击系统级多图联动与右键 SBC 走势直达能力。
【100% 独立非模态窗口】：不阻塞主窗口与看盘窗口，自由层级覆盖、可拖拽多屏浏览。
"""

import os
import re
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QApplication, 
    QFrame, QGridLayout, QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QCursor, QKeySequence, QShortcut

from ats.ui.styles import (
    setup_header_persistence, NumericTableWidgetItem, 
    save_config_node, load_config_node, bind_top_shortcut
)

PERSIST_KEY_LAST_TDX_BLK = "channel_scan_last_selected_tdx_blk"


class ChannelReversalScanResultDialog(QWidget):
    """
    【60f 通道底部反转/上涨顺势策略批量测算统计独立窗口】
    - 📊 顶部统计面板: 扫描总数、命中总数、命中率、平均分、最高分;
    - 📋 结果明细表格: 代码、名称、通道类型、形态名称、得分、介入价、止损位、第一目标、第二目标、通道斜率、缩量比、逻辑解析;
    - ⚡ 联动能力: 单击/双击/上下键表格行触发主工作台/外部终端联动 (绝不发送到异动模块);
    - 📁 TDX 板块写入: 底部自适应读取可写板块，支持一键追加或覆写;
    - 📈 右键菜单: 调出 SBC 实盘走势、调出分时阶梯盯盘、加入关注、复制代码;
    - 🪟 100% 独立顶层窗口: 不阻塞主界面，支持多屏拖拽、自由缩放，支持按 Esc 快速关闭。
    """
    stock_linkage_requested = pyqtSignal(str, str)  # code, name

    def __init__(self, parent=None, df_results: Optional[pd.DataFrame] = None, total_scanned: int = 0, source_tab_name: str = "", period: str = "60f"):
        # 向 QWidget 构造传 None，使其成为真正的顶层非模态独立桌面窗口，绝不阻塞或锁定主界面
        super().__init__(None)
        self.main_window = parent.window() if parent else None
        self.df_results = df_results if df_results is not None else pd.DataFrame()
        self.total_scanned = total_scanned if total_scanned > 0 else len(self.df_results)
        self.source_tab_name = source_tab_name or "当前看板"
        self.period = period or "60f"

        # 防抖与键盘上下键联动状态
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._linkage_timer.setInterval(30)  # 30ms 防抖，过滤键盘长按连续触发
        self._pending_linkage_row = -1
        self._last_emitted_code = ""
        self._linkage_timer.timeout.connect(self._fire_linkage_debounced)

        # Esc 快捷键极速关闭独立窗口 (全局与各子控件焦点均生效)
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.esc_shortcut.activated.connect(self.close)

        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.stays_on_top = self._load_stays_on_top()
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle(f"🎯 {self.period} 通道策略批量测算结果 - 来自【{self.source_tab_name}】")
        self.resize(1060, 640)
        self.setMinimumSize(800, 480)
        self.setStyleSheet("""
            QWidget { background-color: #0f172a; color: #f8fafc; font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; }
            QLabel { color: #cbd5e1; }
        """)

        self._init_ui()
        self._populate_table()

    def _load_stays_on_top(self) -> bool:
        try:
            return bool(load_config_node("channel_scan_stays_on_top", False))
        except Exception:
            return False

    def _on_top_toggled(self, checked: bool):
        self.stays_on_top = checked
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        save_config_node("channel_scan_stays_on_top", checked)

    def keyPressEvent(self, event):
        """支持按 T 键切换置顶，按 Esc 键安全关闭独立结果窗口"""
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                if hasattr(self, 'chk_on_top'):
                    self.chk_on_top.toggle()
                    event.accept()
                    return
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def update_results(self, df_results: pd.DataFrame, total_scanned: int = 0, source_tab_name: str = "", period: str = ""):
        """动态刷新测算结果与统计面板"""
        self.df_results = df_results if df_results is not None else pd.DataFrame()
        self.total_scanned = total_scanned if total_scanned > 0 else len(self.df_results)
        if period:
            self.period = period
        if source_tab_name:
            self.source_tab_name = source_tab_name
        self.setWindowTitle(f"🎯 {self.period} 通道策略批量测算结果 - 来自【{self.source_tab_name}】")

        hit_cnt = len(self.df_results)
        hit_rate = (hit_cnt / max(1, self.total_scanned)) * 100.0
        avg_score = float(self.df_results['score'].mean()) if hit_cnt > 0 and 'score' in self.df_results.columns else 0.0
        max_score = float(self.df_results['score'].max()) if hit_cnt > 0 and 'score' in self.df_results.columns else 0.0

        self.lbl_val_scanned.setText(f"<b>{self.total_scanned}</b> 只")
        self.lbl_val_hit.setText(f"<b style='color: #00ff88;'>{hit_cnt} 只 (命中率: {hit_rate:.1f}%)</b>")
        self.lbl_val_score.setText(f"<b style='color: #38bdf8;'>{avg_score:.1f} 分</b> / <span style='color: #fbbf24;'>最高 {max_score:.1f} 分</span>")

        self._populate_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. 顶部统计信息卡片区 (4 格网格磁贴)
        stat_card = QFrame()
        stat_card.setStyleSheet("QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; }")
        grid_lay = QGridLayout(stat_card)
        grid_lay.setContentsMargins(12, 10, 12, 10)
        grid_lay.setSpacing(12)

        hit_cnt = len(self.df_results)
        hit_rate = (hit_cnt / max(1, self.total_scanned)) * 100.0
        avg_score = float(self.df_results['score'].mean()) if hit_cnt > 0 and 'score' in self.df_results.columns else 0.0
        max_score = float(self.df_results['score'].max()) if hit_cnt > 0 and 'score' in self.df_results.columns else 0.0

        lbl_tit_scanned = QLabel("🔍 扫描标的总数:")
        lbl_tit_scanned.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.lbl_val_scanned = QLabel(f"<b>{self.total_scanned}</b> 只")
        self.lbl_val_scanned.setStyleSheet("color: #38bdf8; font-size: 11pt;")

        lbl_tit_hit = QLabel("🎯 策略命中总数:")
        lbl_tit_hit.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.lbl_val_hit = QLabel(f"<b style='color: #00ff88;'>{hit_cnt} 只 (命中率: {hit_rate:.1f}%)</b>")
        self.lbl_val_hit.setStyleSheet("font-size: 11pt;")

        lbl_tit_score = QLabel("📊 平均得分 / 最高:")
        lbl_tit_score.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.lbl_val_score = QLabel(f"<b style='color: #38bdf8;'>{avg_score:.1f} 分</b> / <span style='color: #fbbf24;'>最高 {max_score:.1f} 分</span>")
        self.lbl_val_score.setStyleSheet("font-size: 11pt;")

        grid_lay.addWidget(lbl_tit_scanned, 0, 0)
        grid_lay.addWidget(self.lbl_val_scanned, 0, 1)
        grid_lay.addWidget(lbl_tit_hit, 0, 2)
        grid_lay.addWidget(self.lbl_val_hit, 0, 3)

        grid_lay.addWidget(lbl_tit_score, 1, 0)
        grid_lay.addWidget(self.lbl_val_score, 1, 1)

        lbl_tips = QLabel("💡 提示: <b>单击/双击</b>联动主终端与行情；<b>右键</b>调出 SBC 走势与分时阶梯盯盘。")
        lbl_tips.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        grid_lay.addWidget(lbl_tips, 1, 2)

        from PyQt6.QtWidgets import QCheckBox
        self.chk_on_top = QCheckBox("置顶 (T)")
        self.chk_on_top.setToolTip("开启/关闭窗口置顶 (快捷键: T)")
        self.chk_on_top.setStyleSheet("color: #ffd700; font-size: 9pt; font-weight: bold;")
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.toggled.connect(self._on_top_toggled)
        grid_lay.addWidget(self.chk_on_top, 1, 3, Qt.AlignmentFlag.AlignRight)
        bind_top_shortcut(self)

        main_layout.addWidget(stat_card)

        # 2. 明细结果表格
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0b0f19;
                gridline-color: #1e293b;
                color: #e2e8f0;
                font-size: 9pt;
                selection-background-color: #1e3a8a;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: bold;
                padding: 4px 6px;
                border: 1px solid #334155;
            }
            QTableWidget::item:selected {
                background-color: #1e3a8a;
                color: #38bdf8;
                font-weight: bold;
            }
        """)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)

        headers = [
            "股票代码", "股票名称", "通道类型", "形态名称", "综合得分", 
            "建议介入价", "止损保护位", "第一目标位", "第二目标位", "通道斜率", "缩量比", "结构逻辑解析"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        default_widths = [80, 90, 85, 120, 75, 90, 90, 90, 90, 80, 75, 300]
        setup_header_persistence(self.table, "channel_scan_dialog_headers_v2", default_widths=default_widths)

        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table, 1)

        # 3. 底部按钮与 TDX 板块写入栏
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        lbl_blk = QLabel("📁 写入TDX板块:")
        lbl_blk.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 9pt;")
        btn_bar.addWidget(lbl_blk)

        self.combo_tdx_blk = QComboBox()
        self.combo_tdx_blk.setStyleSheet("""
            QComboBox {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #1e3a8a;
                selection-color: #38bdf8;
                border: 1px solid #334155;
                padding: 4px;
            }
        """)
        self._populate_tdx_blocks()
        btn_bar.addWidget(self.combo_tdx_blk)

        self.btn_append_blk = QPushButton("➕ 追加板块")
        self.btn_append_blk.setToolTip("将测算命中股票‘追加’到选中的 TDX 自定义板块 (保留原板块已有股票)")
        self.btn_append_blk.setStyleSheet("""
            QPushButton {
                background-color: #132e22;
                color: #00ff88;
                border: 1px solid #00ff88;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00ff88;
                color: #0b0f19;
            }
        """)
        self.btn_append_blk.clicked.connect(lambda: self._on_write_block_clicked(append=True))
        btn_bar.addWidget(self.btn_append_blk)

        self.btn_rewrite_blk = QPushButton("📝 覆写板块")
        self.btn_rewrite_blk.setToolTip("将选中的 TDX 自定义板块‘覆写’为当前测算命中的股票")
        self.btn_rewrite_blk.setStyleSheet("""
            QPushButton {
                background-color: #331d24;
                color: #fb7185;
                border: 1px solid #fb7185;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fb7185;
                color: #0b0f19;
            }
        """)
        self.btn_rewrite_blk.clicked.connect(lambda: self._on_write_block_clicked(append=False))
        btn_bar.addWidget(self.btn_rewrite_blk)

        self.lbl_blk_status = QLabel("")
        self.lbl_blk_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        btn_bar.addWidget(self.lbl_blk_status)

        btn_bar.addStretch()

        self.btn_export = QPushButton("📋 复制全部选中代码")
        self.btn_export.setStyleSheet("""
            QPushButton { background-color: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #38bdf8; color: #000000; }
        """)
        self.btn_export.clicked.connect(self._on_export_clicked)
        btn_bar.addWidget(self.btn_export)

        btn_close = QPushButton("关闭窗口")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #334155; color: #f8fafc; border: 1px solid #475569; border-radius: 4px; padding: 4px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_close.clicked.connect(self.close)
        btn_bar.addWidget(btn_close)

        main_layout.addLayout(btn_bar)

    def _populate_table(self):
        """填充表格数据"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        if self.df_results.empty:
            return

        self.table.setRowCount(len(self.df_results))
        for r, (_, row) in enumerate(self.df_results.iterrows()):
            c_code = str(row.get("code", "")).zfill(6)
            c_name = str(row.get("name", ""))
            if not c_name or c_name == c_code or c_name == "未知":
                try:
                    from ats.intraday_strategy_engine import resolve_stock_name
                    c_name = resolve_stock_name(c_code)
                except Exception:
                    c_name = c_code

            ch_type_cn = str(row.get("channel_type_cn", "上涨通道" if float(row.get("channel_slope_deg", 0)) > 0 else "下降通道"))
            pat_name = str(row.get("pattern_name", "通道顺势/反转"))
            score_v = float(row.get("score", 0.0))
            entry_p = float(row.get("entry_price", 0.0))
            stop_p = float(row.get("stop_loss", 0.0))
            tgt_1 = float(row.get("target_price_1", 0.0))
            tgt_2 = float(row.get("target_price_2", 0.0))
            deg_v = float(row.get("channel_slope_deg", 0.0))
            shrink_v = float(row.get("volume_shrink_pct", 0.0))
            reason_str = str(row.get("reason", ""))

            # 0. 代码
            it_code = QTableWidgetItem(c_code)
            it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_code.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            it_code.setForeground(QColor("#38bdf8"))
            self.table.setItem(r, 0, it_code)

            # 1. 名称
            it_name = QTableWidgetItem(c_name)
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            it_name.setForeground(QColor("#f8fafc"))
            self.table.setItem(r, 1, it_name)

            # 2. 通道类型
            it_ch = QTableWidgetItem(ch_type_cn)
            it_ch.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_ch.setFont(QFont("Microsoft YaHei", 9))
            it_ch.setForeground(QColor("#00ff88") if "上" in ch_type_cn else QColor("#fbbf24"))
            self.table.setItem(r, 2, it_ch)

            # 3. 形态名称
            it_pat = QTableWidgetItem(pat_name)
            it_pat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pat.setFont(QFont("Microsoft YaHei", 9))
            it_pat.setForeground(QColor("#e2e8f0"))
            self.table.setItem(r, 3, it_pat)

            # 4. 得分
            it_score = NumericTableWidgetItem(f"{score_v:.1f}")
            it_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_score.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            it_score.setForeground(QColor("#fbbf24") if score_v >= 80 else QColor("#00ff88"))
            self.table.setItem(r, 4, it_score)

            # 5. 建议介入价
            it_entry = NumericTableWidgetItem(f"{entry_p:.2f}")
            it_entry.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_entry.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            it_entry.setForeground(QColor("#f43f5e"))
            self.table.setItem(r, 5, it_entry)

            # 6. 止损保护位
            it_stop = NumericTableWidgetItem(f"{stop_p:.2f}")
            it_stop.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_stop.setFont(QFont("Consolas", 9))
            it_stop.setForeground(QColor("#ef4444"))
            self.table.setItem(r, 6, it_stop)

            # 7. 第一目标位
            it_tgt1 = NumericTableWidgetItem(f"{tgt_1:.2f}")
            it_tgt1.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_tgt1.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            it_tgt1.setForeground(QColor("#10b981"))
            self.table.setItem(r, 7, it_tgt1)

            # 8. 第二目标位
            it_tgt2 = NumericTableWidgetItem(f"{tgt_2:.2f}")
            it_tgt2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_tgt2.setFont(QFont("Consolas", 9))
            it_tgt2.setForeground(QColor("#059669"))
            self.table.setItem(r, 8, it_tgt2)

            # 9. 通道斜率
            it_deg = NumericTableWidgetItem(f"{deg_v:+.1f}°")
            it_deg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_deg.setFont(QFont("Consolas", 9))
            it_deg.setForeground(QColor("#00ff88") if deg_v > 0 else QColor("#f43f5e"))
            self.table.setItem(r, 9, it_deg)

            # 10. 缩量比
            it_shrink = NumericTableWidgetItem(f"{shrink_v:.1f}%")
            it_shrink.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_shrink.setFont(QFont("Consolas", 9))
            it_shrink.setForeground(QColor("#38bdf8"))
            self.table.setItem(r, 10, it_shrink)

            # 11. 逻辑解析
            it_reason = QTableWidgetItem(reason_str)
            it_reason.setToolTip(reason_str)
            it_reason.setFont(QFont("Microsoft YaHei", 9))
            it_reason.setForeground(QColor("#cbd5e1"))
            self.table.setItem(r, 11, it_reason)

        self.table.setSortingEnabled(True)

    def _get_current_code_name(self) -> tuple[str, str]:
        """获取当前高亮选中的 (code, name)"""
        r = self.table.currentRow()
        if r < 0:
            return "", ""
        it_c = self.table.item(r, 0)
        it_n = self.table.item(r, 1)
        code = it_c.text().strip() if it_c else ""
        name = it_n.text().strip() if it_n else ""
        return code, name

    def _on_current_cell_changed(self, currentRow: int, currentColumn: int, previousRow: int, previousColumn: int):
        """键盘上下键或焦点单元格切换时触发防抖联动"""
        if currentRow < 0 or currentRow == self._pending_linkage_row:
            return
        self._pending_linkage_row = currentRow
        self._linkage_timer.start()

    def _fire_linkage_debounced(self):
        """防抖定时器超时后触发真实联动"""
        row = self._pending_linkage_row
        if row < 0 or row >= self.table.rowCount():
            return
        it_c = self.table.item(row, 0)
        it_n = self.table.item(row, 1)
        code = it_c.text().strip() if it_c else ""
        name = it_n.text().strip() if it_n else ""
        if code and code != self._last_emitted_code:
            self._last_emitted_code = code
            self.stock_linkage_requested.emit(code, name)
            if self.main_window and hasattr(self.main_window, "link_stock"):
                self.main_window.link_stock(code, name)

    def _on_item_clicked(self, item):
        """单击表格行触发常规联动 (绝不发送到异动监测)"""
        code, name = self._get_current_code_name()
        if code and code != self._last_emitted_code:
            self._last_emitted_code = code
            self.stock_linkage_requested.emit(code, name)
            if self.main_window and hasattr(self.main_window, "link_stock"):
                self.main_window.link_stock(code, name)

    def _on_item_double_clicked(self, item):
        """双击表格行直接调出 SBC 实盘走势窗口"""
        code, name = self._get_current_code_name()
        if code:
            self._open_sbc_window(code, name)

    def _open_sbc_window(self, code: str, name: str):
        """调出 SBC 实盘走势 (自动与当前通道测算周期对齐)"""
        sbc_period = "60m"
        p_str = getattr(self, "period", "60f").lower()
        if "120" in p_str:
            sbc_period = "120m"
        elif "月" in p_str or "month" in p_str:
            sbc_period = "month"
        elif "周" in p_str or "week" in p_str or p_str == "w":
            sbc_period = "week"
        elif "日" in p_str or "day" in p_str or p_str == "d":
            sbc_period = "day"
        elif "60" in p_str:
            sbc_period = "60m"

        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(code, self.main_window, initial_period_mode=sbc_period)
        except Exception as e:
            try:
                from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
                dlg = SBCIntradayChartDialog(self.main_window, code=code, initial_period_mode=sbc_period)
                dlg.show()
            except Exception:
                pass

    def _open_ladder_window(self, code: str, name: str):
        """调出分时阶梯盯盘"""
        try:
            from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow
            win = PinzhunLadderStandaloneWindow(code=code, name=name, parent=self.main_window)
            win.show()
        except Exception:
            pass

    def _show_context_menu(self, pos):
        """右键菜单：SBC走势、分时阶梯、重点关注、复制代码"""
        code, name = self._get_current_code_name()
        if not code:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; padding: 4px; font-size: 9pt; }
            QMenu::item:selected { background-color: #1e293b; color: #38bdf8; }
        """)

        cur_period = getattr(self, "period", "60f")
        act_sbc = menu.addAction(f"📈 调出 【{name} ({code})】 SBC 实盘走势 ({cur_period}通道)")
        act_sbc.triggered.connect(lambda: self._open_sbc_window(code, name))

        act_ladder = menu.addAction(f"🚀 调出 【{name} ({code})】 分时阶梯独立盯盘")
        act_ladder.triggered.connect(lambda: self._open_ladder_window(code, name))

        menu.addSeparator()
        act_copy = menu.addAction("📋 复制该股票代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))

        menu.exec(QCursor.pos())

    def _on_export_clicked(self):
        """复制全部命中代码到剪贴板"""
        codes = self._get_target_codes_for_export()
        if not codes:
            QMessageBox.information(self, "提示", "当前没有可复制的股票代码！")
            return
        clip_str = "\n".join(codes)
        QApplication.clipboard().setText(clip_str)
        QMessageBox.information(self, "复制成功", f"已成功复制 {len(codes)} 只股票代码至系统剪贴板！")

    # ── TDX 自定义板块读取与写入支持 ──────────────────────────────────
    def _get_tdx_blocknew_dir(self) -> str:
        """自适应获取通达信 T0002/blocknew/ 物理目录路径"""
        try:
            from JohnsonUtil import commonTips as cct
            blk_dir = cct.get_tdx_dir_blocknew()
            if blk_dir and os.path.exists(blk_dir):
                return blk_dir
        except Exception:
            pass

        try:
            from JohnsonUtil import commonTips as cct
            tdx_dir = cct.get_tdx_dir()
            if tdx_dir and os.path.exists(tdx_dir):
                blk_dir = os.path.join(tdx_dir, "T0002", "blocknew")
                if os.path.exists(blk_dir):
                    return blk_dir
        except Exception:
            pass

        # 尝试从 global.ini 或常用路径探测
        candidate_paths = [
            r"D:\MacTools\WinTools\new_tdx2\T0002\blocknew",
            r"D:\Quant\new_tdx2\T0002\blocknew",
            r"C:\zd_zszq\T0002\blocknew",
            r"D:\MacTools\WinTools\zd_dxzq\T0002\blocknew",
            r"C:\new_tdx\T0002\blocknew",
            r"D:\new_tdx\T0002\blocknew",
        ]
        for cp in candidate_paths:
            if os.path.exists(cp):
                return cp
        return ""

    def _load_available_tdx_blocks(self) -> List[Tuple[str, str]]:
        """
        自适应读取通达信可写自定义板块列表
        返回: [(blk_code, display_text), ...]，例如 [('066', '[066] 形态066'), ...]
        """
        blk_dir = self._get_tdx_blocknew_dir()
        cfg_map: Dict[str, str] = {}
        if blk_dir and os.path.exists(blk_dir):
            cfg_path = os.path.join(blk_dir, "blocknew.cfg")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "rb") as f:
                        buf = f.read()
                    rec_len = 120
                    for i in range(0, len(buf), rec_len):
                        chunk = buf[i:i + rec_len]
                        if len(chunk) < rec_len:
                            break
                        raw_name = chunk[:50].split(b"\x00")[0]
                        raw_code = chunk[50:100].split(b"\x00")[0]
                        name = raw_name.decode("gbk", errors="ignore").strip()
                        code = raw_code.decode("gbk", errors="ignore").strip()
                        if code:
                            cfg_map[code] = name or code
                except Exception:
                    pass

        blocks: List[Tuple[str, str]] = []
        seen_codes = set()

        # 1. 扫描存在的 *.blk 文件
        if blk_dir and os.path.exists(blk_dir):
            try:
                for fname in sorted(os.listdir(blk_dir)):
                    if fname.lower().endswith(".blk"):
                        bcode = fname[:-4]
                        seen_codes.add(bcode)
                        bname = cfg_map.get(bcode, "")
                        if bname and bname != bcode:
                            display = f"[{bcode}] {bname}"
                        else:
                            display = f"[{bcode}] {bcode}"
                        blocks.append((bcode, display))
            except Exception:
                pass

        # 2. 补充在 cfg 中已声明但 blk 文件暂未创建的板块
        for bcode, bname in cfg_map.items():
            if bcode not in seen_codes:
                seen_codes.add(bcode)
                display = f"[{bcode}] {bname}" if bname and bname != bcode else f"[{bcode}] {bcode}"
                blocks.append((bcode, display))

        # 3. 若未检测到任何板块，兜底提供默认列表
        if not blocks:
            default_candidates = [
                ("063", "[063] 063 (默认板块)"),
                ("066", "[066] 形态066"),
                ("061", "[061] 061-3D"),
                ("064", "[064] 064多头排列"),
                ("068", "[068] 068"),
                ("069", "[069] 069"),
                ("098", "[098] 远端次新"),
                ("zxg", "[zxg] 自选股"),
            ]
            blocks.extend(default_candidates)

        return blocks

    def _populate_tdx_blocks(self):
        """填充 TDX 板块下拉选择框并自动恢复上次持久化记忆的板块项"""
        self.combo_tdx_blk.blockSignals(True)
        self.combo_tdx_blk.clear()
        blocks = self._load_available_tdx_blocks()
        for idx, (bcode, display) in enumerate(blocks):
            self.combo_tdx_blk.addItem(display, bcode)

        # 1. 优先读取上次持久化保存的最后写入/选中板块代号
        saved_blk = load_config_node(PERSIST_KEY_LAST_TDX_BLK)
        default_index = -1
        if saved_blk:
            for i in range(self.combo_tdx_blk.count()):
                if self.combo_tdx_blk.itemData(i) == str(saved_blk).strip():
                    default_index = i
                    break

        # 2. 若无历史记录，按系统推荐首选板块规则选取
        if default_index < 0:
            preferred_blks = ["063", "066", "098", "061", "064", "zxg"]
            for pref in preferred_blks:
                found = False
                for i in range(self.combo_tdx_blk.count()):
                    if self.combo_tdx_blk.itemData(i) == pref:
                        default_index = i
                        found = True
                        break
                if found:
                    break

        if default_index < 0:
            default_index = 0

        self.combo_tdx_blk.setCurrentIndex(default_index)
        self.combo_tdx_blk.blockSignals(False)

        # 连接切换信号，用户手动切换或写入时自动记忆
        try:
            self.combo_tdx_blk.currentIndexChanged.disconnect()
        except TypeError:
            pass
        self.combo_tdx_blk.currentIndexChanged.connect(self._on_tdx_block_combo_changed)

    def _on_tdx_block_combo_changed(self, index: int):
        """板块下拉框切换时自动持久化最新选中的板块代号"""
        if index < 0 or index >= self.combo_tdx_blk.count():
            return
        blk_code = self.combo_tdx_blk.itemData(index)
        if blk_code:
            save_config_node(PERSIST_KEY_LAST_TDX_BLK, blk_code)

    def _get_target_codes_for_export(self) -> List[str]:
        """提取待导出的股票代码（优先选区，兜底全量）"""
        selected_indexes = self.table.selectedIndexes()
        if selected_indexes:
            rows = sorted(list(set(idx.row() for idx in selected_indexes)))
            codes = []
            for r in rows:
                it = self.table.item(r, 0)
                if it:
                    c = re.sub(r"[^\d]", "", it.text())
                    if c:
                        codes.append(c.zfill(6))
            if codes:
                return codes

        if not self.df_results.empty and "code" in self.df_results.columns:
            return [str(c).zfill(6) for c in self.df_results["code"] if str(c).strip()]
        return []

    def _on_write_block_clicked(self, append: bool = True):
        """一键写入/追加到通达信自定义板块并持久化记忆当前板块"""
        codes = self._get_target_codes_for_export()
        if not codes:
            QMessageBox.warning(self, "提示", "当前没有可写入的股票代码！")
            return

        blk_code = self.combo_tdx_blk.currentData()
        if not blk_code:
            current_text = self.combo_tdx_blk.currentText()
            m = re.search(r"\[(.*?)\]", current_text)
            blk_code = m.group(1) if m else current_text.strip()

        blk_dir = self._get_tdx_blocknew_dir()
        if not blk_dir or not os.path.exists(blk_dir):
            QMessageBox.warning(self, "错误", f"未找到通达信 blocknew 目录，请检查配置！\n路径: {blk_dir}")
            return

        blk_path = os.path.join(blk_dir, f"{blk_code}.blk")
        try:
            from JohnsonUtil import commonTips as cct
            cct.write_to_blocknew(
                blk_path, codes, append=append, doubleFile=False, keep_last=0, dfcf=False, reappend=True
            )
            # 写入成功后自动持久化当前板块位置
            save_config_node(PERSIST_KEY_LAST_TDX_BLK, blk_code)

            action_name = "追加" if append else "覆写"
            msg = f"成功{action_name} {len(codes)} 只标的至板块 [{blk_code}]"
            self.lbl_blk_status.setText(f"✅ {msg}")
            QMessageBox.information(self, "写入成功", f"已成功{action_name} {len(codes)} 只股票至通达信板块：\n{blk_path}")
        except Exception as e:
            err_msg = f"写入通达信板块失败: {e}"
            self.lbl_blk_status.setText(f"❌ {err_msg}")
            QMessageBox.critical(self, "写入失败", err_msg)


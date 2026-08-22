# -*- coding: utf-8 -*-
"""
ats/ui/channel_scan_result_dialog.py — 60f 通道策略批量测算统计与联动独立窗口
具备高品质量化深色主题、形态统计卡片、全字段结果表格、单击/双击系统级多图联动与右键 SBC 走势直达能力。
【100% 独立非模态窗口】：不阻塞主窗口与看盘窗口，自由层级覆盖、可拖拽多屏浏览。
"""

from typing import Dict, List, Any, Optional
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QApplication, 
    QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCursor

from ats.ui.styles import setup_header_persistence, NumericTableWidgetItem


class ChannelReversalScanResultDialog(QWidget):
    """
    【60f 通道底部反转/上涨顺势策略批量测算统计独立窗口】
    - 📊 顶部统计面板: 扫描总数、命中总数、命中率、平均分、最高分;
    - 📋 结果明细表格: 代码、名称、通道类型、形态名称、得分、介入价、止损位、第一目标、第二目标、通道斜率、缩量比、逻辑解析;
    - ⚡ 联动能力: 单击/双击表格行触发主工作台/外部终端联动 (绝不发送到异动模块);
    - 📈 右键菜单: 调出 SBC 实盘走势、调出分时阶梯盯盘、加入关注、复制代码;
    - 🪟 100% 独立顶层窗口: 不阻塞主界面，支持多屏拖拽、自由缩放。
    """
    stock_linkage_requested = pyqtSignal(str, str)  # code, name

    def __init__(self, parent=None, df_results: Optional[pd.DataFrame] = None, total_scanned: int = 0, source_tab_name: str = ""):
        # 向 QWidget 构造传 None，使其成为真正的顶层非模态独立桌面窗口，绝不阻塞或锁定主界面
        super().__init__(None)
        self.main_window = parent.window() if parent else None
        self.df_results = df_results if df_results is not None else pd.DataFrame()
        self.total_scanned = total_scanned if total_scanned > 0 else len(self.df_results)
        self.source_tab_name = source_tab_name or "当前看板"

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle(f"🎯 60f 通道策略批量测算结果 - 来自【{self.source_tab_name}】")
        self.resize(1060, 640)
        self.setMinimumSize(800, 480)
        self.setStyleSheet("""
            QWidget { background-color: #0f172a; color: #f8fafc; font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; }
            QLabel { color: #cbd5e1; }
        """)

        self._init_ui()
        self._populate_table()

    def update_results(self, df_results: pd.DataFrame, total_scanned: int = 0, source_tab_name: str = ""):
        """动态刷新测算结果与统计面板"""
        self.df_results = df_results if df_results is not None else pd.DataFrame()
        self.total_scanned = total_scanned if total_scanned > 0 else len(self.df_results)
        if source_tab_name:
            self.source_tab_name = source_tab_name
            self.setWindowTitle(f"🎯 60f 通道策略批量测算结果 - 来自【{self.source_tab_name}】")

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
        grid_lay.addWidget(lbl_tips, 1, 2, 1, 2)

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
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table, 1)

        # 3. 底部按钮栏
        btn_bar = QHBoxLayout()
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

    def _on_item_clicked(self, item):
        """单击表格行触发常规联动 (绝不发送到异动监测)"""
        code, name = self._get_current_code_name()
        if code:
            self.stock_linkage_requested.emit(code, name)
            if self.main_window and hasattr(self.main_window, "link_stock"):
                self.main_window.link_stock(code, name)

    def _on_item_double_clicked(self, item):
        """双击表格行直接调出 SBC 实盘走势窗口"""
        code, name = self._get_current_code_name()
        if code:
            self._open_sbc_window(code, name)

    def _open_sbc_window(self, code: str, name: str):
        """调出 SBC 实盘走势"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(code, self.main_window, initial_period_mode="60m")
        except Exception as e:
            try:
                from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
                dlg = SBCIntradayChartDialog(self.main_window, code=code, initial_period_mode="60m")
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

        act_sbc = menu.addAction(f"📈 调出 【{name} ({code})】 SBC 实盘走势 (60f通道)")
        act_sbc.triggered.connect(lambda: self._open_sbc_window(code, name))

        act_ladder = menu.addAction(f"🚀 调出 【{name} ({code})】 分时阶梯独立盯盘")
        act_ladder.triggered.connect(lambda: self._open_ladder_window(code, name))

        menu.addSeparator()
        act_copy = menu.addAction("📋 复制该股票代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))

        menu.exec(QCursor.pos())

    def _on_export_clicked(self):
        """复制全部命中代码到剪贴板"""
        if self.df_results.empty or 'code' not in self.df_results.columns:
            return
        codes = [str(c).zfill(6) for c in self.df_results['code']]
        clip_str = "\n".join(codes)
        QApplication.clipboard().setText(clip_str)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "复制成功", f"已成功复制 {len(codes)} 只命中股票代码至系统剪贴板！")

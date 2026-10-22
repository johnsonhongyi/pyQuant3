# -*- coding: utf-8 -*-
"""
ATS Favorite Panel ("⭐ 重点关注" 专属 Tab 页面)
一键直达重点关注股票、最近强势标的及底层全量监控特征。

核心功能:
1. 阶段一 (冷启动/无 IPC 推送): 读取 GlobalFavoriteManager + 本地缓存，秒级展示基础关注清单。
2. 阶段二 (收到 IPC 实盘推送): 实时高密更新价格、涨幅、波段状态、MA20 偏离度、DFF、Rank 等底层监控列。
3. 阶段三 (超短特异赛马与温度周期去弱留强): 融合 SBC 多日分时缓存与全底层异动，高亮标识
   【👑 特异加速·留强】、【🏇 赛马突然冒头】、【🌱 阶段特异蓄势】与【⚠️ 过热未加速·出局】。
4. 提供双击图表联动、右键发送异动联动与关注管理。
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont
import os
import json
import datetime
import time
import logging

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, setup_header_persistence,
    NumericTableWidgetItem, load_config_node, save_config_node, parse_bool_config
)

logger = logging.getLogger("FavoritePanel")

PERSIST_KEY_FAV_FILTER = "ats_fav_tab_filter_enabled"
PERSIST_KEY_FAV_HORSE_FILTER = "ats_fav_horse_race_filter_enabled"

FONT_BOLD = QFont("Microsoft YaHei", -1, QFont.Weight.Bold)
COLOR_GREEN = QColor("#00FF88")
COLOR_GOLD = QColor("#FFD700")
COLOR_CYAN = QColor("#00E5FF")
COLOR_RED = QColor("#FF4444")
COLOR_ORANGE = QColor("#FF9800")
COLOR_GRAY = QColor("#E2E2E5")
COLOR_FAV_BG = QColor("#1F2D1F")
COLOR_DEFAULT_BG = QColor("#121214")
COLOR_UP_Q = QColor(COLOR_UP)
COLOR_DOWN_Q = QColor(COLOR_DOWN)


def get_ats_extra_cols():
    """获取 ats_col 排除已有固定列后的自定义追加列"""
    try:
        from JohnsonUtil import commonTips as cct
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']

    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'trade', 'state', 'deviation',
        'limit_ups', 'position', 'first_seen', 'priority', 'dff', 'rank',
        'dff2', 'dff3', 'rs', 'resonance', 'reason'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_ats_table_headers(extra_cols=None, base_day: int = 1):
    """获取与 SwingStateTable 100% 严格对齐的标准表头 (支持动态多日基准 DFF 标签)"""
    if extra_cols is None:
        extra_cols = get_ats_extra_cols()
    dff_label = f"DFF({base_day}D)" if base_day > 1 else "DFF"
    base_pre = [
        "股票代码", "股票名称", "当前价", "波段状态", "MA20 偏离", "连板数", "推荐仓位",
        "首次发现", "优先级", dff_label, "Rank", "DFF2", "DFF3", "大盘偏离", "大盘共振"
    ]
    extra_headers = [c.upper() for c in extra_cols]
    return base_pre + extra_headers + ["推荐理由"]


class FavoritePanel(QWidget):
    """⭐ 重点关注(基础重点) 专属看板页"""

    stock_selected = pyqtSignal(str, str, dict)  # code, name, context_info
    stock_double_clicked = pyqtSignal(str, str)  # code, name (双击直通 SBC)
    dragon_monitor_requested = pyqtSignal()

    def minimumSizeHint(self) -> QSize:
        # 允许中间面板极致弹性缩放，绝不撑大主窗口或挤压左右侧分割条
        return QSize(150, 100)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.extra_cols = get_ats_extra_cols()

        # 🎯 策略过滤持久化开关 (专属独立持久化，默认关闭)
        saved_filter = load_config_node(PERSIST_KEY_FAV_FILTER, load_config_node("ats_tab_filter_enabled", False))
        self.filter_enabled = parse_bool_config(saved_filter, default=False)

        # 🏇 特异赛马去弱留强快筛开关 (默认关闭，展示全量重点关注)
        saved_horse = load_config_node(PERSIST_KEY_FAV_HORSE_FILTER, False)
        self.horse_filter_enabled = parse_bool_config(saved_horse, default=False)

        self.pct_base_day: int = int(load_config_node("ats_pct_base_day", 1))

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # Header bar
        header = QHBoxLayout()
        title = QLabel("⭐ 重点关注 (基础重点与底层监控)")
        title.setStyleSheet("font-weight: bold; color: #ffd700; font-size: 11pt;")
        header.addWidget(title)

        self.count_label = QLabel("共 0 只标的")
        self.count_label.setStyleSheet("color: #888888; font-size: 9pt;")
        header.addWidget(self.count_label)

        self.linkage_context_label = QLabel("共享证据：等待快照")
        self.linkage_context_label.setStyleSheet("color: #9aa7b5; font-size: 8pt;")
        self.linkage_context_label.setToolTip("只读题材、人气与天梯上下文；不参与交易准入或执行。")
        header.addWidget(self.linkage_context_label)
        header.addStretch()

        # 🏇 特异赛马(去弱留强)快筛开关按钮
        self.btn_horse_filter = QPushButton()
        self._update_horse_button_ui()
        self.btn_horse_filter.clicked.connect(self.toggle_horse_filter_state)
        header.addWidget(self.btn_horse_filter)

        # 🎯 策略过滤持久化开关按钮
        self.btn_toggle_filter = QPushButton()
        self._update_filter_button_ui()
        self.btn_toggle_filter.clicked.connect(self.toggle_filter_state)
        header.addWidget(self.btn_toggle_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("过滤重点代码/名称...")
        self.search_input.setMaximumWidth(160)
        self.search_input.setStyleSheet("background-color: #1a1a22; border: 1px solid #333; border-radius: 4px; padding: 2px 5px;")
        self.search_input.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_input)

        layout.addLayout(header)

        # BaseATSTableWidget
        self.table = BaseATSTableWidget(self)
        # 视口深暗黑底色设置，确保局部重绘与列宽调整时干净擦除旧图元，杜绝重影与白闪
        self.table.viewport().setStyleSheet("background-color: #121218; border: none;")
        self.table.setStyleSheet("QTableWidget { background-color: #121218; border: none; }")

        headers = get_ats_table_headers(self.extra_cols, base_day=self.pct_base_day)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        default_widths = [90, 100, 90, 110, 110, 90, 100, 110, 75, 60, 50, 60, 60, 75, 75] + [70] * len(self.extra_cols) + [250]
        self.table.setup_persistence(
            config_key="ats_swing_table_state_v2",
            default_widths=default_widths,
            max_widths={len(headers) - 1: 350}
        )

        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.table)

        # 启动时若无推送，立即加载基础重点关注股票清单
        self.load_initial_favorites()

    def set_pct_base_day(self, base_day: int):
        """动态切换涨跌幅基准日并即时更新表头"""
        self.pct_base_day = max(1, int(base_day))
        headers = get_ats_table_headers(self.extra_cols, base_day=self.pct_base_day)
        if self.table.columnCount() == len(headers):
            self.table.setHorizontalHeaderLabels(headers)

    def set_linkage_context(self, text):
        if hasattr(self, "linkage_context_label"):
            self.linkage_context_label.setText(str(text or "共享证据：等待快照"))

    def load_initial_favorites(self):
        """冷启动/无 IPC 推送时：从 GlobalFavoriteManager 加载重点关注基础列表"""
        try:
            from global_favorites import GlobalFavoriteManager
            from sys_utils import resolve_stock_name
            fav_mgr = GlobalFavoriteManager()
            fav_stocks = fav_mgr.get_favorite_stocks()
            if not fav_stocks:
                return

            rows = []
            extra_cols = getattr(self, 'extra_cols', [])
            extra_fallback = ['--'] * len(extra_cols)

            for code in sorted(fav_stocks):
                code_clean = str(code).strip().zfill(6)
                name = resolve_stock_name(code_clean) or "重点标的"
                fav_date = fav_mgr.get_favorite_stock_date(code_clean) or "--"

                row = (
                    code_clean, name, "--", "重点关注", "--", "--", "观察",
                    fav_date, "--", "--", "--", "--", "--", "--", "普通",
                    *extra_fallback,
                    "行情待获取"
                )
                rows.append(row)

            if rows:
                self.update_favorite_rows(rows)
        except Exception:
            pass

    def toggle_horse_filter_state(self):
        """切换特异赛马(去弱留强)快筛状态"""
        self.horse_filter_enabled = not getattr(self, 'horse_filter_enabled', False)
        save_config_node(PERSIST_KEY_FAV_HORSE_FILTER, bool(self.horse_filter_enabled))
        self._update_horse_button_ui()
        self._apply_row_visibility()

    def _update_horse_button_ui(self):
        if not hasattr(self, 'btn_horse_filter'):
            return
        if getattr(self, 'horse_filter_enabled', False):
            self.btn_horse_filter.setText("🏇 特异赛马 (开)")
            self.btn_horse_filter.setStyleSheet("""
                QPushButton {
                    background-color: #38240c;
                    color: #ffd700;
                    font-weight: bold;
                    border: 1.5px solid #ffd700;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #ffd700;
                    color: #000000;
                }
            """)
            self.btn_horse_filter.setToolTip(
                "当前状态：【已开启】仅显示具备连续杀跌小级别企稳异动、盘中赛马冒头或过热未加速出局警示的重点标的"
            )
        else:
            self.btn_horse_filter.setText("🏇 特异赛马 (关)")
            self.btn_horse_filter.setStyleSheet("""
                QPushButton {
                    background-color: #222228;
                    color: #9aa7b5;
                    font-weight: bold;
                    border: 1px solid #44444f;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #33333d;
                    color: #ffd700;
                    border-color: #ffd700;
                }
            """)
            self.btn_horse_filter.setToolTip(
                "点击开启【🏇 特异赛马(去弱留强)】快筛：聚焦连杀小企稳高开加速、赛马冒头及过热未加速出局标的"
            )

    def toggle_filter_state(self):
        """切换策略公式过滤状态并专属独立持久化"""
        self.filter_enabled = not self.filter_enabled
        save_config_node(PERSIST_KEY_FAV_FILTER, bool(self.filter_enabled))
        self._update_filter_button_ui()
        self._apply_row_visibility()

    def _update_filter_button_ui(self):
        """更新策略过滤按钮的高亮与状态文案"""
        if getattr(self, 'filter_enabled', False):
            self.btn_toggle_filter.setText("🎯 策略过滤 (开)")
            self.btn_toggle_filter.setStyleSheet("""
                QPushButton {
                    background-color: #1a3322;
                    color: #00ff88;
                    font-weight: bold;
                    border: 1.5px solid #00ff88;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #00ff88;
                    color: #000000;
                }
            """)
            self.btn_toggle_filter.setToolTip("当前状态：【已开启】根据主窗口策略公式过滤当前列表 (点击可关闭)")
        else:
            self.btn_toggle_filter.setText("🎯 策略过滤 (关)")
            self.btn_toggle_filter.setStyleSheet("""
                QPushButton {
                    background-color: #222228;
                    color: #888888;
                    font-weight: bold;
                    border: 1px solid #44444f;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #33333d;
                    color: #ffffff;
                    border-color: #777788;
                }
            """)
            self.btn_toggle_filter.setToolTip("当前状态：【已关闭】展示全部标的 (点击开启根据策略公式过滤)")

    def _get_parent_mw(self):
        """稳健获取持有 filtered_codes_set 的主窗口实例"""
        mw = getattr(self, 'main_window', None)
        if mw and hasattr(mw, 'filtered_codes_set'):
            return mw
        p = getattr(self, 'parent', lambda: None)()
        if p and hasattr(p, 'filtered_codes_set'):
            return p
        if hasattr(self, 'window'):
            w = self.window()
            if w and w is not self and hasattr(w, 'filtered_codes_set'):
                return w
        from PyQt6.QtWidgets import QApplication
        for tw in QApplication.topLevelWidgets():
            if hasattr(tw, 'filtered_codes_set'):
                return tw
        return None

    def _build_temp_horse_badge(self) -> str:
        """从 UltraShortAnomalyEngine 读取当前市场温度周期与赛马统计"""
        try:
            from ats.ultra_short_anomaly_engine import UltraShortAnomalyEngine
            eng = UltraShortAnomalyEngine.get_instance()
            t = eng.temp_tracker
            if t.total_count > 0:
                rep = eng.get_cached_report()
                em = int(rep.get("horse_emerge_count", 0)) + int(rep.get("keep_strong_count", 0))
                cull = int(rep.get("overheat_cull_count", 0))
                return f" | {t.get_trend_arrow_text()} 🏇冒头:{em} ⚠️出局:{cull}"
        except Exception:
            pass
        return ""

    def _apply_row_visibility(self):
        """根据搜索框文本、主窗口策略过滤条件与特异赛马快筛联合控制行显示"""
        text = self.search_input.text().strip().lower()
        parent_mw = self._get_parent_mw()
        horse_only = getattr(self, 'horse_filter_enabled', False)
        badge_str = self._build_temp_horse_badge()

        fset = None
        if (getattr(self, 'filter_enabled', False) and parent_mw is not None
                and getattr(parent_mw, 'query_expr', '')):
            fset = getattr(parent_mw, 'filtered_codes_set', None)
            if fset is None:
                fset = set()

        total_cnt = self.table.rowCount()
        # ⚡ [极致性能快速路径] 若无搜索过滤且未启用策略过滤与赛马快筛，直接恢复全部可见
        if not text and fset is None and not horse_only:
            for row in range(total_cnt):
                if self.table.isRowHidden(row):
                    self.table.setRowHidden(row, False)
            self.count_label.setText(f"共 {total_cnt} 只标的{badge_str}")
            return

        visible_cnt = 0
        for row in range(total_cnt):
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            state_item = self.table.item(row, 3)
            res_item = self.table.item(row, 14)
            code_str = code_item.text().strip() if code_item else ""
            name_str = name_item.text().lower() if name_item else ""
            state_str = state_item.text() if state_item else ""
            res_str = res_item.text() if res_item else ""

            match_search = (not text) or (text in code_str.lower()) or (text in name_str)
            match_filter = (fset is None) or (code_str.zfill(6) in fset)
            match_horse = True
            if horse_only:
                match_horse = any(
                    kw in res_str or kw in state_str
                    for kw in ("👑", "🏇", "🌱", "⚠️", "📈", "🎯", "⚡", "赛马", "特异", "过热")
                )

            visible = match_search and match_filter and match_horse
            if self.table.isRowHidden(row) != (not visible):
                self.table.setRowHidden(row, not visible)
            if visible:
                visible_cnt += 1

        if (getattr(self, 'filter_enabled', False) and fset is not None) or horse_only:
            self.count_label.setText(f"共 {total_cnt} 只标的 (过滤后 {visible_cnt} 只){badge_str}")
        else:
            self.count_label.setText(f"共 {total_cnt} 只标的{badge_str}")

    def open_sbc_chart(self, code: str, name: str = ""):
        """【📈 打开 SBC 通道走势图】重点关注标的双击直通 SBC 通道走势图"""
        if not code:
            return
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if any(x.isdigit() for x in str(code)) else str(code).strip()
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(parent_win=self.window(), code=c_clean, period_mode="10d")
        except Exception as e:
            logger.error(f"[FavoritePanel] 打开 SBC 走势图异常: {e}")

    def _on_double_clicked(self, item):
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip().replace("⭐ ", "") if name_item else ""
            self.open_sbc_chart(code, name)
            self.stock_double_clicked.emit(code, name)
            self.stock_selected.emit(code, name, {})

    def _on_search_changed(self, text):
        self._apply_row_visibility()

    def update_favorite_rows(self, rows):
        """更新重点关注看板表格 (双缓冲平滑覆盖，杜绝更新前清空导致的闪烁/清0)"""
        if rows is None:
            return

        try:
            current_extra = get_ats_extra_cols()
            if not hasattr(self, 'extra_cols') or self.extra_cols != current_extra:
                self.extra_cols = current_extra
                headers = get_ats_table_headers(self.extra_cols)
                if self.table.columnCount() != len(headers):
                    self.table.setColumnCount(len(headers))
                    self.table.setHorizontalHeaderLabels(headers)

            header = self.table.horizontalHeader()
            sort_col = header.sortIndicatorSection() if (header and header.isSortIndicatorShown()) else -1
            sort_order = header.sortIndicatorOrder() if header else Qt.SortOrder.AscendingOrder

            vbar = self.table.verticalScrollBar()
            scroll_pos = vbar.value() if vbar else 0

            self.table.setSortingEnabled(False)
            badge_str = self._build_temp_horse_badge()
            self.count_label.setText(f"共 {len(rows)} 只重点标的{badge_str}")

            if not rows:
                if self.table.rowCount() > 0:
                    self.table.setRowCount(0)
                self.table.setSortingEnabled(True)
                return

            def _parse_num_val(row_item, col_idx):
                if col_idx >= len(row_item):
                    return 0.0
                val_str = str(row_item[col_idx]).strip()
                s_clean = val_str.translate(str.maketrans('', '', '⭐★🐉🔥⚡❄️💎👑🚀🏇🌱📈🎯⚠️⛔🔻,%+￥$° ')).strip()
                try:
                    return float(s_clean)
                except (ValueError, TypeError):
                    return 0.0

            sorted_rows = sorted(rows, key=lambda x: (-_parse_num_val(x, 8), _parse_num_val(x, 4), str(x[0]).strip()))

            if self.table.rowCount() != len(sorted_rows):
                self.table.setRowCount(len(sorted_rows))

            num_extra = len(self.extra_cols)
            total_cols = 16 + num_extra
            reason_col_idx = total_cols - 1

            for row_idx, row_data in enumerate(sorted_rows):
                code_str = str(row_data[0])
                name = str(row_data[1])
                price = str(row_data[2])
                state = str(row_data[3])
                dev_str = str(row_data[4])
                limit_ups = str(row_data[5])
                position = str(row_data[6])
                first_seen = str(row_data[7])
                priority = str(row_data[8])
                dff = str(row_data[9])
                rank = str(row_data[10])
                dff2 = str(row_data[11])
                dff3 = str(row_data[12])
                rs_val = str(row_data[13])
                resonance = str(row_data[14])

                # 动态列提取
                extra_vals = []
                if len(row_data) > 16:
                    extra_vals = [str(row_data[15 + i]) for i in range(num_extra) if 15 + i < len(row_data) - 1]
                while len(extra_vals) < num_extra:
                    extra_vals.append("--")

                reason = str(row_data[-1]) if len(row_data) > 15 else "重点关注追踪"

                display_name = f"⭐ {name}"
                col_values = [
                    code_str, display_name, price, state, dev_str, limit_ups, position,
                    first_seen, priority, dff, rank, dff2, dff3, rs_val, resonance,
                    *extra_vals, reason
                ]

                for col_idx, val in enumerate(col_values):
                    if col_idx >= self.table.columnCount():
                        break

                    # ⚡ [In-Place 复用] 优先复用已有 NumericTableWidgetItem，杜绝 20000+ 对象重复内存分配与 GC 卡顿
                    item = self.table.item(row_idx, col_idx)
                    if item is None:
                        item = NumericTableWidgetItem(str(val))
                        self.table.setItem(row_idx, col_idx, item)
                    else:
                        item.setText(str(val))

                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col_idx not in (1, reason_col_idx) else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

                    # Highlight entire row for favorite
                    item.setBackground(COLOR_FAV_BG)

                    # Standard color coding + 特异赛马与过热未加速去弱留强着色
                    if col_idx == 0:
                        item.setForeground(COLOR_GREEN)
                        item.setFont(FONT_BOLD)
                    elif col_idx == 1:
                        item.setForeground(COLOR_GOLD)
                        item.setFont(FONT_BOLD)
                    elif col_idx == 3:  # 波段状态
                        if "过热未加速" in state or "破位" in state or "弱" in state:
                            item.setForeground(COLOR_RED)
                            item.setFont(FONT_BOLD)
                        elif "企稳" in state or "买入" in state or "加速" in state or "冒头" in state:
                            item.setForeground(COLOR_GREEN)
                            item.setFont(FONT_BOLD)
                        elif "持股" in state:
                            item.setForeground(COLOR_CYAN)
                        else:
                            item.setForeground(COLOR_GRAY)
                    elif col_idx == 4:  # MA20 偏离
                        if dev_str.startswith("+"):
                            item.setForeground(COLOR_UP_Q)
                        elif dev_str.startswith("-"):
                            item.setForeground(COLOR_DOWN_Q)
                    elif col_idx == 6:  # 推荐仓位/去弱留强动作
                        if "出局" in position or "去弱" in position:
                            item.setForeground(COLOR_RED)
                            item.setFont(FONT_BOLD)
                        elif "留强" in position or "赛马" in position or "加仓" in position:
                            item.setForeground(COLOR_GOLD)
                            item.setFont(FONT_BOLD)
                    elif col_idx == 8:  # 优先级
                        item.setForeground(COLOR_GREEN)
                        item.setFont(FONT_BOLD)
                    elif col_idx == 14:  # 大盘共振 / 特异赛马标签
                        if "过热未加速" in resonance or "淘汰" in resonance:
                            item.setForeground(COLOR_RED)
                            item.setFont(FONT_BOLD)
                        elif "👑" in resonance or "🏇" in resonance or "赛马" in resonance or "特异加速" in resonance:
                            item.setForeground(COLOR_GOLD)
                            item.setFont(FONT_BOLD)
                        elif "🌱" in resonance or "逆市" in resonance or "共振" in resonance or "企稳" in resonance:
                            item.setForeground(COLOR_GREEN)
                            item.setFont(FONT_BOLD)
                        else:
                            item.setForeground(COLOR_GRAY)
                    elif 15 <= col_idx < 15 + num_extra:  # 动态自定义列
                        if str(val).startswith("+"):
                            item.setForeground(COLOR_UP_Q)
                        elif str(val).startswith("-"):
                            item.setForeground(COLOR_DOWN_Q)
                        else:
                            item.setForeground(COLOR_GRAY)

            self.table.setSortingEnabled(True)
            if sort_col >= 0:
                self.table.sortItems(sort_col, sort_order)
            if vbar and vbar.value() != scroll_pos:
                vbar.setValue(scroll_pos)
        finally:
            pass

        self._apply_row_visibility()

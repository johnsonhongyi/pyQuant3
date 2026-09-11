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
    QLineEdit, QFrame, QGridLayout, QSizePolicy, QMenu, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QSize
from PyQt6.QtGui import QColor, QBrush, QFont, QCursor

from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN,
    setup_header_persistence, auto_fit_columns_once,
    load_config_node, save_config_node, parse_bool_config
)
from ats.capital_dragon_engine import (
    CapitalDragonEngine, _safe_float, _clean_code,
    compute_dragon_buy_type_sort_score,
    get_dragon_extra_cols, get_dragon_table_headers,
    is_index_or_fund, is_major_index, MAJOR_INDEX_CODES
)
from JohnsonUtil import commonTips as cct

PERSIST_KEY_DRAGON_FILTER = "ats_capital_dragon_filter_enabled"
PERSIST_KEY_DRAGON_AUTO_UPDATE = "ats_capital_dragon_auto_update_enabled"
PERSIST_KEY_DRAGON_FOCUS_STOCKS = "ats_capital_dragon_focus_stocks"

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


def _update_label_text(lbl: QLabel, new_text: str, is_rich: bool = False):
    """
    针对 QLabel 实施增量 Dirty Check 渲染：
    仅在文本真实变动时更新，杜绝重复触发 QTextDocument 重建与排版开销
    """
    if lbl.text() != new_text:
        target_format = Qt.TextFormat.RichText if is_rich else Qt.TextFormat.PlainText
        if lbl.textFormat() != target_format:
            lbl.setTextFormat(target_format)
        lbl.setText(new_text)


class SectorCardWidget(QFrame):
    """
    可交互式核心资金主线卡片 (SSOT):
    - 物理级绝对锁定高度 (72px)，禁止折行抖动打扰外层 QSplitter
    - 单击卡片/标题/查看明细: 调起板块成分股明细并标记强势股 (sector_clicked)
    - 单击领涨先锋: 联动该股行情并广播 (pioneer_clicked)
    - 双击领涨先锋: 打开 SBC 分时通道走势图 (pioneer_double_clicked)
    """
    sector_clicked = pyqtSignal(str)              # (sector_name)
    pioneer_clicked = pyqtSignal(str, str)        # (code, name)
    pioneer_double_clicked = pyqtSignal(str, str) # (code, name)

    CARD_HEIGHT = 72  # 物理级绝对锁定高度，彻底根治 QSplitter 几何跳变引起的整窗闪屏

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.sector_name = ""
        self.leader_code = ""
        self.leader_name = ""

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.CARD_HEIGHT)
        self.setMinimumWidth(0)

        self.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QFrame:hover {
                border: 1px solid #58a6ff;
                background-color: #1f242c;
            }
        """)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(10, 7, 10, 7)
        card_layout.setSpacing(4)

        # 标题栏：主线名称 + 查看明细按钮
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(6)

        self.lbl_title = ClickableLabel(f"主线 {index+1}: 正在识别资金聚集...")
        self.lbl_title.setStyleSheet("color: #ffd700; font-size: 10.5pt; font-weight: bold;")
        self.lbl_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_title.setMinimumWidth(0)
        self.lbl_title.clicked.connect(self._on_card_clicked)
        title_layout.addWidget(self.lbl_title, 1)

        self.btn_detail = QPushButton("🔍 查看明细")
        self.btn_detail.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_detail.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #58a6ff;
                font-size: 8.5pt;
                font-weight: bold;
                border: 1px solid #30363d;
                border-radius: 3px;
                padding: 2px 7px;
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

        # 描述行：成交额、均涨、涨停、加速（支持自动折行自适应展示）
        self.lbl_desc = ClickableLabel("成交: -- 亿 | 均涨: --% | 涨停: -- 家")
        self.lbl_desc.setStyleSheet("color: #8b949e; font-size: 9pt;")
        self.lbl_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_desc.setMinimumWidth(0)
        self.lbl_desc.clicked.connect(self._on_card_clicked)
        card_layout.addWidget(self.lbl_desc)

        # 先锋行：代码、名称、涨幅、虚拟量比、买点类型（支持自动折行自适应展示）
        self.lbl_leader = ClickableLabel("🚀 先锋: --")
        self.lbl_leader.setStyleSheet("""
            QLabel {
                color: #38bdf8;
                font-size: 9pt;
                font-weight: bold;
            }
            QLabel:hover {
                color: #7dd3fc;
                text-decoration: underline;
            }
        """)
        self.lbl_leader.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_leader.setWordWrap(True)
        self.lbl_leader.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_leader.setMinimumWidth(0)
        self.lbl_leader.setToolTip("🎯 单击联动行情与K线 | 双击查看 SBC 分时通道")
        self.lbl_leader.clicked.connect(self._on_leader_clicked)
        self.lbl_leader.double_clicked.connect(self._on_leader_double_clicked)
        card_layout.addWidget(self.lbl_leader)

    def sizeHint(self) -> QSize:
        return QSize(240, 92)

    def minimumSizeHint(self) -> QSize:
        # 宽度支持弹性缩放折行，高度确保三行文字舒适舒展不被裁切
        return QSize(60, 86)

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
    async_report_ready = pyqtSignal(dict)         # ⚡ 后台异步报告就绪信号 (主线程安全投递)

    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.main_window = main_window
        self.engine = CapitalDragonEngine.get_instance()
        self._last_report = {}
        self._last_df_all = None
        self._last_sig = None
        self._is_updating = False

        # 🎯 工业级防抖与节流控制器 (350ms 节流合并高频 IPC 行情广播，杜绝主线程雪崩)
        self._pending_payload: Optional[Tuple[pd.DataFrame, float]] = None
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setInterval(350)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._process_pending_payload)

        # ⚡ 异步计算状态与信号槽绑定
        self._is_async_calculating = False
        self.async_report_ready.connect(self._on_async_report_ready)

        # ⚡ 切股联动去重与当前高亮代码
        self._last_emitted_code: Optional[str] = None

        # ⚡ 工业级懒更新 (Lazy Rendering) 脏标记与挂起报告缓存
        self._pending_report: Optional[dict] = None
        self._needs_render: bool = False

        # 🎯 策略过滤持久化开关 (专属独立持久化，默认关闭)
        saved_filter = load_config_node(PERSIST_KEY_DRAGON_FILTER, False)
        self.filter_enabled = parse_bool_config(saved_filter, default=False)

        # 🐉 全资金主线模块自动更新持久化开关 (专属独立持久化，默认开启)
        saved_auto_update = load_config_node(PERSIST_KEY_DRAGON_AUTO_UPDATE, True)
        self.auto_update_enabled = parse_bool_config(saved_auto_update, default=True)

        # ⭐ 资金主线专属独立重点关注持久化 (与全局重点关注完全解耦，优先级在指数之下、普通个股之上)
        saved_focus = load_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, [])
        if isinstance(saved_focus, (list, tuple, set)):
            self.dragon_focus_stocks = set(str(c).strip().zfill(6) for c in saved_focus if c)
        else:
            self.dragon_focus_stocks = set()

        self._init_ui()

    def is_dragon_focused(self, code: str) -> bool:
        """判定标的是否在资金主线独立重点关注池中"""
        c_clean = str(code).strip().zfill(6)
        return c_clean in getattr(self, 'dragon_focus_stocks', set())

    def toggle_dragon_focus(self, code: str, name: str = ""):
        """切换资金主线独立重点关注状态，自动持久化并原地刷新表格与排序"""
        c_clean = str(code).strip().zfill(6)
        if not c_clean:
            return
        if not hasattr(self, 'dragon_focus_stocks'):
            self.dragon_focus_stocks = set()

        if c_clean in self.dragon_focus_stocks:
            self.dragon_focus_stocks.discard(c_clean)
            toast_msg = f"⭐ 已取消【{name or c_clean}】资金主线重点关注"
        else:
            self.dragon_focus_stocks.add(c_clean)
            toast_msg = f"⭐ 已将【{name or c_clean}】设为资金主线重点关注 (优先级仅次于指数)"

        save_config_node(PERSIST_KEY_DRAGON_FOCUS_STOCKS, list(self.dragon_focus_stocks))
        try:
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, toast_msg)
        except Exception:
            pass

        self._render_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. 顶部 3 大资金主线卡片展示区 (Top Mainstream Sector Cards) - 弹性自适应缩放与折行
        self.top_sector_container = QWidget()
        self.top_sector_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.top_sector_container.setMinimumWidth(0)
        self.top_sector_layout = QHBoxLayout(self.top_sector_container)
        self.top_sector_layout.setContentsMargins(0, 0, 0, 0)
        self.top_sector_layout.setSpacing(8)

        self.sector_card_widgets = []
        for i in range(3):
            card = SectorCardWidget(i)
            card.sector_clicked.connect(self.open_sector_detail)
            card.pioneer_clicked.connect(self._on_pioneer_clicked)
            card.pioneer_double_clicked.connect(self._on_pioneer_double_clicked)
            self.top_sector_layout.addWidget(card, 1)  # stretch=1 权重均分，自适应等宽缩放
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

        # 🐉 全资金主线模块功能开关按钮 (自动持久化，关闭时完全停止自动更新)
        self.btn_toggle_module = QPushButton()
        self._update_module_button_ui()
        self.btn_toggle_module.clicked.connect(self.toggle_module_state)
        toolbar_layout.addWidget(self.btn_toggle_module)

        # 🔄 手动单次刷新数据按钮 (点击一次强制刷新一次数据)
        self.btn_manual_refresh = QPushButton("🔄 手动刷新")
        self.btn_manual_refresh.setStyleSheet("""
            QPushButton {
                background-color: #162638;
                color: #58a6ff;
                font-weight: bold;
                border: 1px solid #388bfd;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #1f6feb;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #0d419d;
            }
        """)
        self.btn_manual_refresh.setToolTip("点击立即手动计算并刷新一次资金主线与核心真龙数据")
        self.btn_manual_refresh.clicked.connect(self.manual_refresh)
        toolbar_layout.addWidget(self.btn_manual_refresh)

        # 🎯 策略过滤持久化开关按钮
        self.btn_toggle_filter = QPushButton()
        self._update_filter_button_ui()
        self.btn_toggle_filter.clicked.connect(self.toggle_filter_state)
        toolbar_layout.addWidget(self.btn_toggle_filter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码 / 名称 / 主线 / 角色...")
        self.search_input.setMaximumWidth(220)
        self.search_input.setMinimumWidth(80)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
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

        # ⚡ 极限性能模式控制开关 (开启精选 Top 30，关闭展示全部 300+ 全量候选池)
        self.extreme_perf_mode = True
        self.btn_extreme_perf = QPushButton("⚡ 极限性能: 开")
        self.btn_extreme_perf.setStyleSheet("""
            QPushButton {
                background-color: #1a2a1a; color: #00ff88; font-weight: bold;
                border: 1px solid #00ff88; border-radius: 3px; padding: 3px 10px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #00ff88; color: #000000; }
        """)
        self.btn_extreme_perf.setToolTip("开启：精选核心真龙(Top 30/收敛容量中军)，原位批量图元零卡顿；\n关闭：展示全部 300+ 全量候选池。")
        self.btn_extreme_perf.clicked.connect(self._toggle_extreme_perf)
        toolbar_layout.addWidget(self.btn_extreme_perf)

        main_layout.addLayout(toolbar_layout)

        # 3. 核心真龙矩阵表格 (True Dragon Matrix Table)
        self.table = QTableWidget()
        # 视口深暗黑底色设置，确保局部重绘与列宽调整时干净擦除旧图元，杜绝重影与白闪
        self.table.viewport().setStyleSheet("background-color: #121218; border: none;")
        self.table.setStyleSheet("QTableWidget { background-color: #121218; border: none; }")

        self.extra_cols = get_dragon_extra_cols()
        self.headers = get_dragon_table_headers(self.extra_cols)
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)

        try:
            col_map = getattr(cct, 'vis_column_map', {}) or {}
        except Exception:
            col_map = {}

        default_widths = {
            "代码": 68, "名称": 78, "龙头角色": 115, "所属主线": 88, "现价": 68, "涨幅%": 68,
            "虚拟量比": 75, "成交额(亿)": 88, "换手率%": 68, "资金买点类型": 110
        }
        for ec in self.extra_cols:
            header_name = col_map.get(ec, col_map.get(ec.lower(), ec.upper()))
            default_widths[header_name] = 75
        default_widths.update({
            "建议买入区间": 110, "止损参考": 70, "核心逻辑与驱动": 280
        })
        setup_header_persistence(self.table, "capital_dragon_table_header_v3", default_widths=default_widths)

        # 信号连接
        self.table.itemClicked.connect(self._on_row_clicked)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table)

    def update_payload(self, df_all: Optional[pd.DataFrame], sh_pct: float = 0.0, force: bool = False):
        """
        接收最新行情快照，采用前沿节流 (Leading Edge Throttling) 合并高频 IPC 广播：
        1. 首帧或间隔 >300ms 时立即响应渲染，用户界面 0 迟滞；
        2. 300ms 内高频涌入时平滑合并到定时器，彻底杜绝主线程重算与重绘雪崩；
        3. 🛡️ 当 auto_update_enabled 为 False 时，仅暂存行情，彻底阻断自动计算与重绘。
        """
        if df_all is None or df_all.empty:
            return

        self._last_df_all = df_all
        self._pending_sh_pct = sh_pct

        # 🛡️ 核心守卫：若未开启全资金主线自动更新且非手动强制触发，彻底阻断后续更新，不启动节流，不计算，不重绘
        if not getattr(self, 'auto_update_enabled', True) and not force:
            return

        self._pending_payload = (df_all, sh_pct)

        now = time.time()
        elapsed = now - getattr(self, '_last_update_time', 0.0)

        if force or elapsed >= 0.3:
            self._throttle_timer.stop()
            self._process_pending_payload(force=force)
        else:
            if not self._throttle_timer.isActive():
                rem_ms = max(int((0.3 - elapsed) * 1000), 50)
                self._throttle_timer.start(rem_ms)

    def _process_pending_payload(self, force: bool = False):
        """节流定时器触发的数据处理入口"""
        if self._pending_payload is None:
            return
        df_all, sh_pct = self._pending_payload
        self._pending_payload = None
        self._last_update_time = time.time()

        # ⚡ 极限性能复用：非 force 时优先直接从引擎读取后台 Worker 计算好的缓存报告 (0ms 耗时，零计算，支持 180s 容错回退)
        report = None
        if not force:
            report = self.engine.get_cached_report(max_age=5.0, df_check=df_all, fallback_stale=True)

        if report is None:
            # 若尚无可用缓存或为 force 强制刷新：在 force 或首帧冷启动时同步计算一次保底；在后续高频轮询中异步计算杜绝卡顿
            if force or not self._last_report:
                report = self.engine.analyze_capital_dragon_universe(df_all, sh_pct)
            else:
                if not self._is_async_calculating:
                    self._is_async_calculating = True
                    import threading
                    def _async_worker():
                        try:
                            rep = self.engine.analyze_capital_dragon_universe(df_all, sh_pct)
                            self.async_report_ready.emit(rep or {})
                        except Exception as e:
                            logger.warning(f"后台异步分析资金主线异常: {e}")
                            self.async_report_ready.emit({})
                    t = threading.Thread(target=_async_worker, daemon=True)
                    t.start()
                return

        if report:
            self._apply_report_to_ui(report)

    def _on_async_report_ready(self, report: dict):
        self._is_async_calculating = False
        is_manual = getattr(self, '_is_manual_refresh_active', False)
        self._is_manual_refresh_active = False

        if report:
            self._apply_report_to_ui(report)
            if is_manual:
                self._show_manual_refresh_msg("✅ 已刷新")
        else:
            if is_manual:
                self._show_manual_refresh_msg("⚠️ 无数据")
            elif hasattr(self, 'btn_manual_refresh') and self.btn_manual_refresh is not None:
                self._restore_manual_refresh_btn()

    def _show_manual_refresh_msg(self, msg: str):
        """
        直接在【🔄 手动刷新】按钮本身呈现高质感轻量反馈，杜绝动态拉长 lbl_stats 撑大工具栏引发整窗布局放大缩小
        """
        if hasattr(self, 'btn_manual_refresh') and self.btn_manual_refresh is not None:
            self.btn_manual_refresh.setEnabled(True)
            self.btn_manual_refresh.setText(msg)
            if "已刷新" in msg or "✅" in msg:
                self.btn_manual_refresh.setStyleSheet("""
                    QPushButton {
                        background-color: #1a3322;
                        color: #00ff88;
                        font-weight: bold;
                        border: 1.5px solid #00ff88;
                        border-radius: 3px;
                        padding: 2px 8px;
                        font-size: 8.5pt;
                    }
                """)
            else:
                self.btn_manual_refresh.setStyleSheet("""
                    QPushButton {
                        background-color: #33221a;
                        color: #ffaa00;
                        font-weight: bold;
                        border: 1.5px solid #ffaa00;
                        border-radius: 3px;
                        padding: 2px 8px;
                        font-size: 8.5pt;
                    }
                """)
            QTimer.singleShot(1800, self._restore_manual_refresh_btn)

    def _restore_manual_refresh_btn(self):
        """恢复手动刷新按钮默认质感蓝样式"""
        if hasattr(self, 'btn_manual_refresh') and self.btn_manual_refresh is not None:
            self.btn_manual_refresh.setEnabled(True)
            self.btn_manual_refresh.setText("🔄 手动刷新")
            self.btn_manual_refresh.setStyleSheet("""
                QPushButton {
                    background-color: #162638;
                    color: #58a6ff;
                    font-weight: bold;
                    border: 1px solid #388bfd;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8.5pt;
                }
                QPushButton:hover {
                    background-color: #1f6feb;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: #0d419d;
                }
            """)

    def is_panel_visible(self) -> bool:
        """
        判断面板当前是否对用户可见（自身可见且未处于非活动 Tab 页，窗口未最小化）
        """
        # 1. 若宿主顶层窗口已最小化，判定为不可见
        top_win = self.window()
        if top_win and top_win.isMinimized():
            return False

        # 2. 逐级向上检查是否处于 QTabWidget 的非激活页面
        curr = self
        parent = self.parent()
        while parent:
            if isinstance(parent, QTabWidget):
                cw = parent.currentWidget()
                if cw is not None and cw is not curr and not cw.isAncestorOf(self):
                    return False
            curr = parent
            parent = parent.parent()

        # 3. 若已被显式 hide 则不可见
        if self.isHidden():
            return False

        # 4. 若有父级容器，检查 isVisible；若无父级容器（单测或独立组件），未被显式 hide 即视为可见
        if self.parent() is not None:
            return self.isVisible()
        return True

    def ensure_rendered(self):
        """当外部 Tab 切换或面板恢复显示时调用，确保挂起的数据瞬间补齐渲染"""
        if not getattr(self, 'auto_update_enabled', True):
            return
        if self._needs_render and self._pending_report:
            self._do_render_report(self._pending_report)

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_rendered()

    def _apply_report_to_ui(self, report: dict):
        if not report:
            return
        self._pending_report = report
        # ⚡ 懒渲染拦截：首帧必须渲染打底；后续更新若面板不可见（处于非激活 Tab 或窗口最小化），仅打上脏标记，0 耗时 0 控件操作
        if self._last_report and not self.is_panel_visible():
            self._needs_render = True
            return
        self._do_render_report(report)

    def _do_render_report(self, report: dict):
        if not report:
            return
        self._needs_render = False

        # 特征签名检查，防无意义重绘
        is_extreme = getattr(self, 'extreme_perf_mode', True)
        key = "dragon_records_converged" if is_extreme else "dragon_records_all"
        dragons = report.get(key, report.get("dragon_records", []))
        top_secs = report.get("top_sectors", [])
        sig_tuple = (
            len(dragons),
            tuple(d["code"] for d in dragons[:15]),
            tuple(round(d["pct"], 1) for d in dragons[:15]),
            tuple(s["name"] for s in top_secs[:3]),
            is_extreme
        )

        if sig_tuple == self._last_sig:
            return
        self._last_sig = sig_tuple
        self._last_report = report

        # 1. 刷新顶部主线卡片
        self._render_top_sector_cards(top_secs)

        # 2. 刷新核心真龙表格 (单元格复用更新，0 阻塞)
        self._render_table(dragons)

    def _set_or_update_cell(
        self, row: int, col: int, text: str, raw_val: Any = None,
        align: int = Qt.AlignmentFlag.AlignCenter,
        fg_color: Optional[str] = None,
        bg_color: Optional[QColor] = None,
        font_bold: bool = False,
        tooltip: Optional[str] = None,
        is_numeric: bool = True,
        is_pinned: bool = False,
        pin_rank: int = 999
    ):
        """原地更新单元格，实施 Dirty Check，避免重复销毁与重建对象，降低 90%+ 的 UI 渲染开销"""
        item = self.table.item(row, col)
        if item is None:
            item = NumericTableWidgetItem(text, is_pinned=is_pinned, raw_val=raw_val, pin_rank=pin_rank)
            item.setTextAlignment(align)
            if fg_color:
                item.setForeground(QBrush(QColor(fg_color)))
            if bg_color:
                item.setBackground(QBrush(bg_color))
            if font_bold:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            if tooltip:
                item.setToolTip(tooltip)
            self.table.setItem(row, col, item)
            return

        # 针对已存在的 item 执行 Dirty Check 原地更新
        if item.text() != text:
            item.setText(text)
        if hasattr(item, 'set_pin_status'):
            item.set_pin_status(is_pinned, pin_rank=pin_rank)
        elif hasattr(item, 'is_pinned'):
            item.is_pinned = is_pinned
            item.pin_rank = pin_rank
        if hasattr(item, 'set_raw_value') and raw_val is not None:
            if getattr(item, '_raw_value', None) != raw_val:
                item.set_raw_value(raw_val)
        if fg_color:
            cur_fg = item.foreground().color().name()
            if cur_fg.lower() != fg_color.lower():
                item.setForeground(QBrush(QColor(fg_color)))
        if bg_color is not None:
            cur_bg = item.background().color()
            if cur_bg != bg_color:
                item.setBackground(QBrush(bg_color))
        elif item.background().style() != Qt.BrushStyle.NoBrush:
            item.setBackground(QBrush())
        if font_bold != item.font().bold():
            f = item.font()
            f.setBold(font_bold)
            item.setFont(f)
        if tooltip and item.toolTip() != tooltip:
            item.setToolTip(tooltip)

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
                _update_label_text(w["title"], f"{grade}: {sec_name}", is_rich=False)

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

                desc_html = (
                    f"成交: <font color='#ffd700'><b>{st['total_amt_yi']:.1f}亿</b></font>{proj_str} | "
                    f"量比: <font color='{vr_col}'><b>{vol_ratio:.1f}x</b></font> | "
                    f"均涨: <font color='{pct_col}'><b>{st['avg_pct']:+.2f}%</b></font> | "
                    f"涨停: <font color='#ff4444'><b>{st['limit_up_count']}只</b></font>"
                    f"{accel_desc}"
                )
                _update_label_text(w["desc"], desc_html, is_rich=True)

                accel_tip_str = ""
                if accel_tot > 0:
                    accel_tip_str = f"⚡ 群起加速: 共 {accel_tot} 只呈现早盘加速形态 (👑双加速 {dual_cnt} 只, 🚀缺口加速 {gap_cnt} 只, ⚡光脚加速 {ol_cnt} 只)\n🔥 板块内群起加速，显性印证该主线早盘资金进攻动能超强！\n"

                card_tip = (
                    f"💡 点击直接打开【{sec_name}】板块成分股明细与强势股\n"
                    f"📊 累计成交: {st['total_amt_yi']:.1f}亿元 | 全天预估: {proj_amt:.1f}亿元\n"
                    f"⚡ 板块虚拟量比: {vol_ratio:.2f}x (按盘中交易进度折算)\n"
                    f"{accel_tip_str}"
                )
                if w["frame"].toolTip() != card_tip:
                    w["frame"].setToolTip(card_tip)

                if l_name and l_code:
                    l_pct = st.get("leader_pct", 0.0)
                    l_vr = st.get("leader_vr", 1.0)
                    l_buy_type = st.get("leader_buy_type", "")

                    l_pct_col = COLOR_UP if l_pct > 0 else (COLOR_DOWN if l_pct < 0 else "#ffffff")

                    # 虚拟量比高亮色彩
                    if l_vr >= 2.0:
                        l_vr_col = "#ffd700"  # 爆量金黄
                    elif l_vr >= 1.2:
                        l_vr_col = "#00e5ff"  # 活跃青蓝
                    elif l_vr <= 0.7:
                        l_vr_col = "#8b949e"  # 缩量灰
                    else:
                        l_vr_col = "#c9d1d9"  # 正常白

                    # 买点类型高亮色彩
                    if "👑双加速" in l_buy_type or "👑" in l_buy_type:
                        l_bt_col = "#ffd700"
                    elif "🚀缺口加速" in l_buy_type:
                        l_bt_col = "#ff55bb"
                    elif "⚡光脚加速" in l_buy_type:
                        l_bt_col = "#ffaa00"
                    elif "板" in l_buy_type or "封" in l_buy_type or "涨停" in l_buy_type:
                        l_bt_col = "#ff4444"
                    else:
                        l_bt_col = "#38bdf8"

                    vr_text = f" | 量比: <font color='{l_vr_col}'><b>{l_vr:.1f}x</b></font>"
                    bt_text = f" | <font color='{l_bt_col}'><b>{l_buy_type}</b></font>" if l_buy_type else ""

                    leader_html = (
                        f"🚀 先锋: {l_name} ({l_code}) "
                        f"<font color='{l_pct_col}'><b>{l_pct:+.1f}%</b></font>"
                        f"{vr_text}{bt_text}"
                    )
                    _update_label_text(w["leader"], leader_html, is_rich=True)
                    leader_tip = (
                        f"🎯 单击联动【{l_name} ({l_code})】行情与K线 | 双击查看 SBC 分时通道\n"
                        f"📊 先锋虚拟量比: {l_vr:.2f}x (早盘放量加速评估)\n"
                        f"💡 先锋买点形态: {l_buy_type or '主线冲锋'}"
                    )
                    if w["leader"].toolTip() != leader_tip:
                        w["leader"].setToolTip(leader_tip)
                else:
                    _update_label_text(w["leader"], "🚀 先锋: 正在争夺...", is_rich=False)
                    if w["leader"].toolTip():
                        w["leader"].setToolTip("")
                if not w["frame"].isVisible():
                    w["frame"].setVisible(True)
            else:
                # 保持 3 大卡片稳定占位，绝不 setVisible(False)，彻底防止容器高度坍塌促发整窗 Splitter 重新布局与闪烁
                w["sector_name"] = ""
                w["leader_code"] = ""
                w["leader_name"] = ""
                if card_obj:
                    card_obj.sector_name = ""
                    card_obj.leader_code = ""
                    card_obj.leader_name = ""
                _update_label_text(w["title"], f"主线 {i+1}: 正在识别资金聚集...", is_rich=False)
                _update_label_text(w["desc"], "成交: -- 亿 | 均涨: --% | 涨停: -- 只", is_rich=False)
                _update_label_text(w["leader"], "🚀 先锋: 正在争夺...", is_rich=False)
                if w["leader"].toolTip():
                    w["leader"].setToolTip("")
                if w["frame"].toolTip():
                    w["frame"].setToolTip("")
                if not w["frame"].isVisible():
                    w["frame"].setVisible(True)

    def _render_table(self, dragons: Optional[List[Dict[str, Any]]] = None):
        if dragons is None:
            if self._last_report:
                is_extreme = getattr(self, 'extreme_perf_mode', True)
                key = "dragon_records_converged" if is_extreme else "dragon_records_all"
                dragons = self._last_report.get(key, self._last_report.get("dragon_records", []))
            else:
                dragons = []

        self._is_updating = True
        self.table.blockSignals(True)
        try:
            # 动态同步自定义列 (ats_col)：若配置发生变化，即时平滑热重载表头与列结构
            current_extra = get_dragon_extra_cols()
            if getattr(self, 'extra_cols', None) != current_extra:
                self.extra_cols = current_extra
                self.headers = get_dragon_table_headers(self.extra_cols)
                self.table.setColumnCount(len(self.headers))
                self.table.setHorizontalHeaderLabels(self.headers)

            # 记录滚动条位置，彻底防止视口跳跃
            v_bar = self.table.verticalScrollBar()
            h_bar = self.table.horizontalScrollBar()
            scroll_v = v_bar.value() if v_bar else 0
            scroll_h = h_bar.value() if h_bar else 0

            # 1. 记住当前选中的标的代码与行位置
            selected_code = None
            curr_row = self.table.currentRow()
            if curr_row >= 0:
                c_item = self.table.item(curr_row, 0)
                if c_item:
                    selected_code = c_item.text().strip()

            # 2. 记住用户当前激活的排序状态，避免刷新时排序冲突
            h_header = self.table.horizontalHeader()
            sort_col = h_header.sortIndicatorSection() if h_header.isSortIndicatorShown() else -1
            sort_order = h_header.sortIndicatorOrder() if sort_col >= 0 else Qt.SortOrder.AscendingOrder
            self.table.setSortingEnabled(False)

            filter_text = self.search_input.text().strip().lower()

            parent_mw = self._get_parent_mw()
            fset = None
            if getattr(self, 'filter_enabled', False) and parent_mw is not None:
                fset = getattr(parent_mw, 'filtered_codes_set', None)
                if fset is None:
                    fset = set()

            focus_set = getattr(self, 'dragon_focus_stocks', set())

            def _get_dragon_record_tier(record: Dict[str, Any]) -> Tuple[int, int]:
                """
                计算记录的置顶梯队与 pin_rank：
                - Tier 0: 主要指数 (Major Index) -> tier=0, pin_rank=0 (绝对最前)
                - Tier 1: 资金主线重点关注 (Dragon Focus) -> tier=1, pin_rank=1 (优先级仅次于指数，在普通个股之上)
                - Tier 2: 普通真龙个股 -> tier=2, pin_rank=999
                """
                c_clean = _clean_code(record.get('code', ''))
                nm = str(record.get('name', '')).strip()
                is_idx = record.get('is_index', False) or is_major_index(c_clean, nm)
                if is_idx:
                    return 0, 0
                if c_clean in focus_set:
                    return 1, 1
                return 2, 999

            matched_records = []
            for d in dragons:
                c_clean = _clean_code(d.get('code', ''))
                tier, _ = _get_dragon_record_tier(d)
                if tier != 0 and fset is not None and c_clean not in fset:
                    continue
                if filter_text:
                    extra_vals_str = " ".join(str(d.get("extra_cols", {}).get(ec, d.get(ec, ""))) for ec in getattr(self, 'extra_cols', []))
                    match_str = f"{d.get('code', '')} {d.get('name', '')} {d.get('role', '')} {d.get('sector', '')} {d.get('action_type', '')} {d.get('reason', '')} {extra_vals_str}".lower()
                    if filter_text not in match_str:
                        continue
                matched_records.append(d)

            # 若开启极限性能模式且有重点关注标的，若 dragon_records_all 中有但 dragons 中未收录，补齐收录
            if getattr(self, 'extreme_perf_mode', True) and self._last_report:
                all_recs = self._last_report.get("dragon_records_all", [])
                existing_codes = {_clean_code(r.get('code', '')) for r in matched_records}
                for r in all_recs:
                    c_c = _clean_code(r.get('code', ''))
                    if c_c in focus_set and c_c not in existing_codes:
                        if fset is not None and c_c not in fset:
                            continue
                        if filter_text:
                            extra_vals_str = " ".join(str(r.get("extra_cols", {}).get(ec, r.get(ec, ""))) for ec in getattr(self, 'extra_cols', []))
                            match_str = f"{r.get('code', '')} {r.get('name', '')} {r.get('role', '')} {r.get('sector', '')} {r.get('action_type', '')} {r.get('reason', '')} {extra_vals_str}".lower()
                            if filter_text not in match_str:
                                continue
                        matched_records.append(r)
                        existing_codes.add(c_c)

            # 无论是否有排序列，预排序均保证：Tier 0 指数最前 -> Tier 1 重点关注次之 -> Tier 2 普通标的
            matched_records.sort(
                key=lambda x: (
                    _get_dragon_record_tier(x)[0],  # 0: 指数, 1: 重点关注, 2: 普通
                    -x.get("priority", 0),
                    -float(x.get("buy_type_sort_score", 0.0) or 0.0),
                    -float(x.get("amount_yi", 0.0) or 0.0),
                    -float(x.get("pct", 0.0) or 0.0)
                )
            )

            # ⚡ 极限性能模式开启时：若未启用文本搜索且未启用策略过滤，精选 Top 50 核心真龙
            # 由于已按 Tier 排序，所有的主要指数和重点关注均绝对优先保留在 Top 50 内！
            if getattr(self, 'extreme_perf_mode', True) and not filter_text and fset is None:
                matched_records = matched_records[:50]

            target_row_count = len(matched_records)
            if self.table.rowCount() != target_row_count:
                self.table.setRowCount(target_row_count)

            new_selected_row = -1

            for row_idx, d in enumerate(matched_records):
                code = str(d["code"]).strip()
                name = str(d["name"]).strip()
                c_clean = _clean_code(code)
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

                tier, pin_rank = _get_dragon_record_tier(d)
                is_row_pinned = (tier < 2)

                # 行背景微光与高亮：
                # Tier 0 (指数): 沉稳微弱暗蓝底色
                # Tier 1 (重点关注): 尊贵微弱暗金底色
                # Tier 2 (普通): 默认
                row_bg = None
                if tier == 1:
                    row_bg = QColor(50, 42, 16, 130)
                elif tier == 0:
                    row_bg = QColor(18, 28, 42, 120)

                # 重点关注名称醒目标注
                name_display = f"⭐ {name}" if (tier == 1 and not name.startswith("⭐")) else name

                if code == selected_code:
                    new_selected_row = row_idx

                # 0: 代码 (纯数字则传入数值以支持精确数字排序)
                code_raw = int(c_clean) if c_clean.isdigit() else c_clean
                self._set_or_update_cell(
                    row_idx, 0, code, raw_val=code_raw,
                    align=Qt.AlignmentFlag.AlignCenter, bg_color=row_bg,
                    is_numeric=True, is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 1: 名称
                self._set_or_update_cell(
                    row_idx, 1, name_display, raw_val=name,
                    align=Qt.AlignmentFlag.AlignCenter, bg_color=row_bg,
                    font_bold=(tier < 2), is_numeric=False,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 2: 龙头角色 (高辨识度徽标色)
                role_col = "#00b0ff"
                if "空间" in role:
                    role_col = "#ff1744"
                elif "容量" in role:
                    role_col = "#ffd700"
                elif "先锋" in role:
                    role_col = "#00e676"
                self._set_or_update_cell(
                    row_idx, 2, role, raw_val=d.get("priority", 0),
                    align=Qt.AlignmentFlag.AlignCenter, fg_color=role_col,
                    bg_color=row_bg, font_bold=True, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 3: 所属主线
                sec_tip = f"💡 双击直接打开【{sector}】板块成分股明细与强势股" if (sector and sector not in ('--', '未知')) else None
                self._set_or_update_cell(
                    row_idx, 3, sector,
                    align=Qt.AlignmentFlag.AlignCenter, fg_color="#e0e0e0",
                    bg_color=row_bg, tooltip=sec_tip, is_numeric=False,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 4: 现价
                self._set_or_update_cell(
                    row_idx, 4, f"{price:.2f}", raw_val=price,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    bg_color=row_bg, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 5: 涨幅%
                pct_str = f"{pct:+.2f}%"
                pct_col = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else "#c9d1d9")
                self._set_or_update_cell(
                    row_idx, 5, pct_str, raw_val=pct,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    fg_color=pct_col, bg_color=row_bg, font_bold=True, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 6: 虚拟量比 (系统的虚拟量比，反映资金加速流入速度)
                vr_val = float(d.get("vol_ratio", 1.0))
                vr_bold = False
                if vr_val >= 3.0:
                    vr_col = "#ff1744"
                    vr_bold = True
                elif vr_val >= 2.0:
                    vr_col = "#ffd700"
                    vr_bold = True
                elif vr_val >= 1.2:
                    vr_col = "#00e5ff"
                elif vr_val <= 0.7:
                    vr_col = "#888888"
                else:
                    vr_col = "#ffffff"
                vr_tip = f"系统的虚拟量比: {vr_val:.2f}x\n按上午实时交易进度计算全天预估成交倍速，量比越大资金加速流入越猛烈"
                self._set_or_update_cell(
                    row_idx, 6, f"{vr_val:.2f}x", raw_val=vr_val,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    fg_color=vr_col, bg_color=row_bg, font_bold=vr_bold, tooltip=vr_tip, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 7: 成交额(亿)
                amt_col = "#ffd700" if amt >= 15.0 else "#ffffff"
                amt_bold = amt >= 15.0
                self._set_or_update_cell(
                    row_idx, 7, f"{amt:.1f}亿", raw_val=amt,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    fg_color=amt_col, bg_color=row_bg, font_bold=amt_bold, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 8: 换手率%
                self._set_or_update_cell(
                    row_idx, 8, f"{turnover:.1f}%", raw_val=turnover,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    bg_color=row_bg, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 9: 资金买点类型 (精细化视觉高亮与量化排序，对齐龙头突击与天梯 SSOT)
                buy_score = float(d.get("buy_type_sort_score", 0.0))
                if buy_score <= 0.0:
                    buy_score = compute_dragon_buy_type_sort_score(
                        action_type=buy_type,
                        is_dual_accel=d.get("is_dual_accel", False),
                        is_gap_accel=d.get("is_gap_accel", False),
                        is_open_low_accel=d.get("is_open_low_accel", False),
                        amount_yi=amt,
                        pct=pct
                    )
                buy_fg = "#38bdf8"
                buy_bg = None
                if "双加速" in buy_type:
                    buy_fg = "#FFD700"
                    buy_bg = QColor(80, 20, 60, 180)
                elif "缺口加速" in buy_type:
                    buy_fg = "#FF55BB"
                    buy_bg = QColor(50, 15, 45, 160)
                elif "光脚加速" in buy_type:
                    buy_fg = "#FFAA00"
                    buy_bg = QColor(60, 35, 10, 160)
                elif "主升" in buy_type or "先锋" in buy_type or "龙头" in buy_type:
                    buy_fg = "#00e676"
                    buy_bg = QColor(10, 50, 30, 150)

                buy_tip = f"【资金买点】: {buy_type}\n" \
                          f"• 🎯 形态梯队排序分: {buy_score:.0f}\n" \
                          f"• 💡 梯队优先级: 👑双加速 > 🚀缺口加速 > ⚡光脚加速 > 常规主升 > 🎯通道支撑企稳"
                self._set_or_update_cell(
                    row_idx, 9, buy_type, raw_val=buy_score,
                    align=Qt.AlignmentFlag.AlignCenter, fg_color=buy_fg,
                    bg_color=buy_bg or row_bg, font_bold=True, tooltip=buy_tip, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 10+: 动态自定义列 (ats_col, 紧随资金买点类型后面)
                col_offset = 10
                for ec in getattr(self, 'extra_cols', []):
                    val_str = "--"
                    if "extra_cols" in d and ec in d["extra_cols"]:
                        val_str = str(d["extra_cols"][ec])
                    elif ec in d:
                        val_str = str(d[ec])
                    elif self._last_df_all is not None and not self._last_df_all.empty:
                        for k in (ec, ec.lower(), ec.upper()):
                            if k in self._last_df_all.columns and code in self._last_df_all.index:
                                val_raw = self._last_df_all.loc[code, k]
                                val_str = cct.format_col_value(ec, val_raw)
                                break

                    raw_num = None
                    try:
                        raw_num = float(val_str)
                    except Exception:
                        raw_num = None

                    ec_col = "#888888"
                    if raw_num is not None:
                        if raw_num > 0:
                            ec_col = COLOR_UP
                        elif raw_num < 0:
                            ec_col = COLOR_DOWN
                        else:
                            ec_col = "#e2e2e5"

                    self._set_or_update_cell(
                        row_idx, col_offset, val_str, raw_val=raw_num,
                        align=Qt.AlignmentFlag.AlignCenter, fg_color=ec_col,
                        bg_color=row_bg, tooltip=f"【{ec.upper()} 自定义指标】: {val_str}",
                        is_numeric=True, is_pinned=is_row_pinned, pin_rank=pin_rank
                    )
                    col_offset += 1

                # 建议买入区间
                self._set_or_update_cell(
                    row_idx, col_offset, buy_zone,
                    align=Qt.AlignmentFlag.AlignCenter, fg_color="#ffb74d",
                    bg_color=row_bg, is_numeric=False,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 止损参考
                self._set_or_update_cell(
                    row_idx, col_offset + 1, f"{stop_loss:.2f}", raw_val=stop_loss,
                    align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    fg_color="#ef5350", bg_color=row_bg, is_numeric=True,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

                # 核心逻辑与驱动
                self._set_or_update_cell(
                    row_idx, col_offset + 2, reason,
                    align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    fg_color="#b0bec5", bg_color=row_bg, tooltip=reason, is_numeric=False,
                    is_pinned=is_row_pinned, pin_rank=pin_rank
                )

            is_extreme = getattr(self, 'extreme_perf_mode', True)
            dual_cnt = self._last_report.get('dual_accel_count', 0) if self._last_report else 0
            gap_cnt = self._last_report.get('gap_accel_count', 0) if self._last_report else 0
            ol_cnt = self._last_report.get('open_low_count', 0) if self._last_report else 0
            accel_tot = dual_cnt + gap_cnt + ol_cnt
            accel_str = f" | ⚡加速: {accel_tot}只 (👑双加速:{dual_cnt} 🚀缺口:{gap_cnt})" if accel_tot > 0 else ""

            focus_cnt = sum(1 for r in matched_records if _get_dragon_record_tier(r)[0] == 1)
            focus_str = f" | ⭐重点: <font color='#ffd700'><b>{focus_cnt}只</b></font>" if focus_cnt > 0 else ""

            if is_extreme:
                sp_cnt = self._last_report.get('space_dragon_count', 0) if self._last_report else 0
                mc_cnt = self._last_report.get('midcap_dragon_count', 0) if self._last_report else 0
                pn_cnt = self._last_report.get('pioneer_dragon_count', 0) if self._last_report else 0
            else:
                sp_cnt = self._last_report.get('all_space_count', self._last_report.get('space_dragon_count', 0)) if self._last_report else 0
                mc_cnt = self._last_report.get('all_midcap_count', self._last_report.get('midcap_dragon_count', 0)) if self._last_report else 0
                pn_cnt = self._last_report.get('all_pioneer_count', self._last_report.get('pioneer_dragon_count', 0)) if self._last_report else 0

            total_dragons = len(dragons)
            if getattr(self, 'filter_enabled', False) and fset is not None:
                count_str = f"共 {total_dragons} 只 (过滤后 <b>{len(matched_records)}</b> 只)"
            else:
                count_str = f"<b>{len(matched_records)}</b> 只"

            self.lbl_stats.setText(
                f"🐉 资金主线龙头已就位: {count_str} "
                f"(空间龙: {sp_cnt} | "
                f"容量中军: {mc_cnt} | "
                f"主线先锋: {pn_cnt})"
                f"{focus_str}"
                f"{accel_str}"
            )

            # 3. 恢复用户激活的排序列与排序规则
            if sort_col >= 0:
                self.table.sortItems(sort_col, sort_order)
            self.table.setSortingEnabled(True)

            # 4. 恢复选中行状态 (仅当之前用户确有选中项时恢复，杜绝无端选中第0行触发视口滚动)
            if selected_code:
                for r in range(self.table.rowCount()):
                    it = self.table.item(r, 0)
                    if it and it.text().strip() == selected_code:
                        self.table.setCurrentCell(r, 0)
                        break

            # 5. 锁定滚动条原位，绝对防止 setCurrentCell 触发的 scrollTo 导致视口跳跃
            if v_bar and v_bar.value() != scroll_v:
                v_bar.setValue(scroll_v)
            if h_bar and h_bar.value() != scroll_h:
                h_bar.setValue(scroll_h)

            if not getattr(self, '_table_columns_fitted', False):
                self._table_columns_fitted = True
                auto_fit_columns_once(self.table, "capital_dragon_table_header_v3")

        finally:
            self.table.blockSignals(False)
            self._is_updating = False

    def toggle_module_state(self):
        """切换全资金主线模块自动更新开关并专属独立持久化"""
        self.auto_update_enabled = not getattr(self, 'auto_update_enabled', True)
        save_config_node(PERSIST_KEY_DRAGON_AUTO_UPDATE, bool(self.auto_update_enabled))
        self._update_module_button_ui()

        if not self.auto_update_enabled:
            # 关闭时：停止节流定时器，清除挂起脏标记，保持界面当前静止
            self._throttle_timer.stop()
            self._needs_render = False
            try:
                from stock_logic_utils import toast_messageQT
                toast_messageQT(self, "⏸️ 资金主线模块已暂停自动更新 (可点击[🔄 手动刷新]按需更新)")
            except Exception:
                pass
        else:
            try:
                from stock_logic_utils import toast_messageQT
                toast_messageQT(self, "▶️ 资金主线模块已恢复自动更新")
            except Exception:
                pass
            # 若暂存有最新行情快照，立即触发一次更新恢复最新状态
            df_all = self._last_df_all
            if df_all is None or df_all.empty:
                if self.main_window and hasattr(self.main_window, 'current_df'):
                    df_all = self.main_window.current_df
            if df_all is not None and not df_all.empty:
                sh_pct = getattr(self, '_pending_sh_pct', 0.0)
                self.update_payload(df_all, sh_pct, force=True)

    def _update_module_button_ui(self):
        """更新全资金主线模块开关按钮的高亮与状态文案"""
        if getattr(self, 'auto_update_enabled', True):
            self.btn_toggle_module.setText("🐉 资金主线 (开)")
            self.btn_toggle_module.setStyleSheet("""
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
            self.btn_toggle_module.setToolTip("全资金主线模块功能开关【已开启】：\n实时接收行情并后台自动计算与刷新资金主线与真龙矩阵。\n点击可切换为【关闭】，完全停止自动更新以节约系统资源。")
        else:
            self.btn_toggle_module.setText("🐉 资金主线 (关)")
            self.btn_toggle_module.setStyleSheet("""
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
            self.btn_toggle_module.setToolTip("全资金主线模块功能开关【已关闭】：\n资金主线全部停止后台自动更新数据，界面保持当前静止状态。\n可点击右侧【🔄 手动刷新】按需单次更新，或点击此处重新开启自动更新。")

    def manual_refresh(self):
        """
        手动刷新按钮：强制立即获取最新行情并计算刷新一次资金主线与真龙看板
        无论自动更新开关是否开启，均可单次强制刷新
        ⚡ 全异步后台 Worker 调度 (实盘)，主线程 0 阻塞，彻底根治手动刷新卡顿与闪白
        """
        if getattr(self, '_is_async_calculating', False):
            return

        df_all = self._last_df_all
        if df_all is None or df_all.empty:
            if self.main_window and hasattr(self.main_window, 'current_df'):
                df_all = self.main_window.current_df

        if df_all is None or df_all.empty:
            self._show_manual_refresh_msg("⚠️ 暂无可用行情数据，请等待底层行情就绪")
            return

        sh_pct = getattr(self, '_pending_sh_pct', 0.0)

        # 针对微型测试样本（<= 50 行），走轻量直接通道，保证单元测试即时断言
        if len(df_all) <= 50:
            self.update_payload(df_all, sh_pct, force=True)
            self._show_manual_refresh_msg("✅ 资金主线数据已手动刷新完成")
            return

        # ⚡ 实盘全市场模式 (行数 > 50): 立即更新按钮状态，启动独立后台 Worker 异步计算，主线程 0 卡顿
        if hasattr(self, 'btn_manual_refresh') and self.btn_manual_refresh is not None:
            self.btn_manual_refresh.setEnabled(False)
            self.btn_manual_refresh.setText("⏳ 计算中...")

        self._is_manual_refresh_active = True
        self._is_async_calculating = True
        self._throttle_timer.stop()
        self._pending_payload = None

        import threading
        def _async_manual_worker():
            try:
                rep = self.engine.analyze_capital_dragon_universe(df_all, sh_pct)
                self.async_report_ready.emit(rep or {})
            except Exception as e:
                logger.warning(f"后台异步手动刷新资金主线异常: {e}")
                self.async_report_ready.emit({})

        t = threading.Thread(target=_async_manual_worker, daemon=True)
        t.start()

    def toggle_filter_state(self):
        """切换策略公式过滤状态并专属独立持久化"""
        self.filter_enabled = not getattr(self, 'filter_enabled', False)
        save_config_node(PERSIST_KEY_DRAGON_FILTER, bool(self.filter_enabled))
        self._update_filter_button_ui()
        self._apply_filter()

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
            self.btn_toggle_filter.setToolTip("当前状态：【已开启】根据主窗口策略公式过滤当前真龙列表 (点击可关闭)")
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
            self.btn_toggle_filter.setToolTip("当前状态：【已关闭】展示全部真龙标的 (点击开启根据策略公式过滤)")

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

    def _toggle_extreme_perf(self):
        """切换极限性能模式 (开启精选 Top 30，关闭展示全部 300+ 全量候选池)"""
        self.extreme_perf_mode = not getattr(self, 'extreme_perf_mode', True)
        if self.extreme_perf_mode:
            self.btn_extreme_perf.setText("⚡ 极限性能: 开")
            self.btn_extreme_perf.setStyleSheet("""
                QPushButton {
                    background-color: #1a2a1a; color: #00ff88; font-weight: bold;
                    border: 1px solid #00ff88; border-radius: 3px; padding: 3px 10px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #00ff88; color: #000000; }
            """)
        else:
            self.btn_extreme_perf.setText("⚡ 极限性能: 关")
            self.btn_extreme_perf.setStyleSheet("""
                QPushButton {
                    background-color: #2b1f0e; color: #ffd700; font-weight: bold;
                    border: 1px solid #ffd700; border-radius: 3px; padding: 3px 10px; font-size: 8.5pt;
                }
                QPushButton:hover { background-color: #ffd700; color: #000000; }
            """)
        self._apply_filter()

    def _apply_filter(self):
        if self._last_report:
            is_extreme = getattr(self, 'extreme_perf_mode', True)
            key = "dragon_records_converged" if is_extreme else "dragon_records_all"
            records = self._last_report.get(key, self._last_report.get("dragon_records", []))
            self._render_table(records)

    def _trigger_stock_linkage(self, code: str, name: str):
        """统一的选股联动触发器 (带严格防抖去重，避免双发与频繁切换K线导致主线程卡顿)"""
        if getattr(self, '_is_updating', False):
            return
        code_clean = str(code).strip()
        if not code_clean or code_clean == getattr(self, '_last_emitted_code', None):
            return
        self._last_emitted_code = code_clean
        self.stock_selected.emit(code_clean, name)

    def _on_row_clicked(self, item):
        if getattr(self, '_is_updating', False) or item is None:
            return
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if c_item and n_item:
            code = _clean_code(c_item.text().strip())
            name = n_item.text().replace("⭐", "").strip()
            self._trigger_stock_linkage(code, name)

    def _on_current_cell_changed(self, cur_row, cur_col, prev_row, prev_col):
        # 正在后台刷新数据或无效行期间严禁触发切股联动与抢焦
        if getattr(self, '_is_updating', False) or cur_row < 0:
            return
        if cur_row != prev_row:
            c_item = self.table.item(cur_row, 0)
            n_item = self.table.item(cur_row, 1)
            if c_item and n_item:
                code = _clean_code(c_item.text().strip())
                name = n_item.text().replace("⭐", "").strip()
                self._trigger_stock_linkage(code, name)

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
            code = _clean_code(c_item.text().strip())
            name = n_item.text().replace("⭐", "").strip()
            self.stock_double_clicked.emit(code, name)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        s_item = self.table.item(row, 3)
        code = _clean_code(c_item.text().strip()) if c_item else ""
        name = n_item.text().replace("⭐", "").strip() if n_item else ""
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
            is_idx = is_major_index(code, name)
            if not is_idx:
                is_foc = self.is_dragon_focused(code)
                foc_text = f"⭐ 取消资金主线重点关注: {name} ({code})" if is_foc else f"⭐ 设为资金主线重点关注: {name} ({code})"
                act_focus = menu.addAction(foc_text)
                act_focus.triggered.connect(lambda checked=False, c=code, n=name: self.toggle_dragon_focus(c, n))
                menu.addSeparator()

            act_sbc = menu.addAction(f"📈 打开 {name}({code}) SBC 通道走势图 (R)")
            act_sbc.triggered.connect(lambda checked=False, c=code, n=name: self.stock_double_clicked.emit(c, n))

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

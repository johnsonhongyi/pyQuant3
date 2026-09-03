# -*- coding: utf-8 -*-
"""
ats/ui/hot_sector_leaderboard.py — Top 3 强势板块龙头突击跟单看板 (Hot Alpha Leaderboard)
功能：
1. 自动吸纳板块热力图 Top 3 强势板块（如 CPO、国家大基建、存储芯片等）成分股与重点自选池；
2. 整合 TDX 秒级高频高精度盘口 + 底层多日底座 (DFF, Rank, DFF2, DFF3, 动态自定义列)；
3. 动态呈现【👑 领涨龙头】与【🚀 先锋突破】（最佳上车点），并给出建议买入区间与止损位；
4. 顶部热点板块按钮支持交互式点击开/关过滤（默认全开，点击单选/多选/切换），快速聚焦；
5. 排序状态自动持久化记忆，刷新时原位 In-place 更新，锁定滚动条与焦点，浏览时绝不跳屏；
6. 具备磁吸边沿吸附、自动隐藏、窗口置顶与极速跨软件联动（TDX/THS/本地分时）。
"""

import os
import json
import time
import math
import threading
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, 
    QPushButton, QFrame, QMenu, QApplication, QComboBox, QLineEdit, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QBrush, QColor, QFont
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from logger_utils import LoggerFactory
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN, 
    auto_fit_columns_once, setup_header_persistence, save_config_node, load_config_node,
    apply_dark_theme, bind_top_shortcut, ColorPreservingItemDelegate, set_seamless_stay_on_top
)
from ats.ui.favorite_panel import get_ats_extra_cols
from ats.hot_sector_engine import HotSectorEngine, is_valid_sector_name
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()


def _safe_float(val: Any, default: float = 0.0) -> float:
    """健壮的浮点数安全转换函数"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """健壮的整数安全转换函数"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


def get_leaderboard_headers(extra_cols=None):
    """组合跟单看板的列名与自定义列映射"""
    if extra_cols is None:
        extra_cols = get_ats_extra_cols()
    try:
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
        
    base_headers = [
        "代码", "名称", "所属强板块", "买点类型", "现价", "涨幅%", "涨速%", "换手%", "量比", 
        "盘口意图", "分时攻角", "VWAP偏离", "DFF", "Rank", "DFF2", "DFF3"
    ]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    tail_headers = ["建议买入区间", "止损防守", "综合得分", "决策依据"]
    full_headers = base_headers + extra_headers + tail_headers
    return full_headers, extra_cols


class TDXFetchLogDialog(QDialog):
    """
    通达信 (pytdx) 结构获取数据的日志与网络诊断独立对话框
    """
    def __init__(self, parent=None):
        super().__init__(None) # [独立顶层窗口]
        self._py_parent = parent
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle("📜 通达信 (TDX) 实时数据获取日志与网络诊断")
        self.resize(780, 520)
        apply_dark_theme(self)
        self.setStyleSheet(self.styleSheet() + """
            QDialog { background-color: #121214; color: #e2e2e5; font-family: 'Microsoft YaHei', sans-serif; }
            QTextEdit { background-color: #18181c; color: #e2e2e5; border: 1px solid #282830; font-family: 'Consolas', 'Courier New', monospace; font-size: 9pt; }
            QFrame#top_info_frame { background-color: #18181c; border: 1px solid #282830; border-radius: 4px; }
        """)
        self._init_ui()
        self._refresh_logs()

        # 定时刷新器 (默认不开启，由用户勾选控制)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh_logs)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 顶部状态卡片
        info_frame = QFrame()
        info_frame.setObjectName("top_info_frame")
        info_lay = QHBoxLayout(info_frame)
        info_lay.setContentsMargins(10, 6, 10, 6)

        self.lbl_session_status = QLabel("时段: --")
        self.lbl_session_status.setStyleSheet("color: #00ffaa; font-weight: bold; font-size: 9.5pt;")
        info_lay.addWidget(self.lbl_session_status)

        sep = QLabel("|")
        sep.setStyleSheet("color: #444a66; font-weight: bold;")
        info_lay.addWidget(sep)

        self.lbl_server_info = QLabel("主站: --")
        self.lbl_server_info.setStyleSheet("color: #ffaa44; font-size: 9pt;")
        info_lay.addWidget(self.lbl_server_info)

        info_lay.addStretch()

        self.chk_auto_refresh = QCheckBox("自动刷新 (1s)")
        self.chk_auto_refresh.setChecked(False) # 默认关闭自动刷新
        self.chk_auto_refresh.setStyleSheet("color: #ffd700; font-size: 8.5pt; font-weight: bold;")
        self.chk_auto_refresh.toggled.connect(self._toggle_auto_refresh)
        info_lay.addWidget(self.chk_auto_refresh)

        self.chk_auto_scroll = QCheckBox("自动滚动到底部")
        self.chk_auto_scroll.setChecked(True)
        self.chk_auto_scroll.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        info_lay.addWidget(self.chk_auto_scroll)

        layout.addWidget(info_frame)

        # 中间日志文本展示区 (支持富文本彩色渲染)
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log)

        # 底部操作栏
        btn_lay = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 立即刷新")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton { 
                background-color: #1a2e22; 
                color: #00ffaa; 
                border: 1px solid #00ffaa; 
                border-radius: 3px; 
                padding: 4px 14px; 
                font-weight: bold; 
                font-size: 9pt;
            }
            QPushButton:hover { 
                background-color: #00ffaa; 
                color: #000000; 
            }
            QPushButton:pressed {
                background-color: #00aa77;
                color: #ffffff;
            }
        """)
        self.btn_refresh.clicked.connect(self._on_click_refresh)
        btn_lay.addWidget(self.btn_refresh)

        self.btn_copy = QPushButton("📋 复制全部")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet("background-color: #202436; color: #ffffff; border: 1px solid #445577; border-radius: 3px; padding: 4px 10px;")
        self.btn_copy.clicked.connect(self._copy_logs)
        btn_lay.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("🗑️ 清空日志")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet("background-color: #332020; color: #ff8888; border: 1px solid #663333; border-radius: 3px; padding: 4px 10px;")
        self.btn_clear.clicked.connect(self._clear_logs)
        btn_lay.addWidget(self.btn_clear)

        btn_lay.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("background-color: #24283b; color: #ffffff; border: 1px solid #3e445f; border-radius: 3px; padding: 4px 14px;")
        self.btn_close.clicked.connect(self.close)
        btn_lay.addWidget(self.btn_close)

        layout.addLayout(btn_lay)

    def _toggle_auto_refresh(self, checked: bool):
        if checked:
            self.timer.start()
        else:
            self.timer.stop()

    def _on_click_refresh(self):
        """用户主动点击刷新按钮"""
        self._refresh_logs()

    def _refresh_logs(self):
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher, is_trading_time
        fetcher = TDXRealtimeFetcher.get_instance()
        is_t, s_text = is_trading_time()
        self.lbl_session_status.setText(f"时段: {'🟢 交易时段' if is_t else '💤 非交易休眠'} ({s_text})")
        if fetcher.current_host:
            h_name, h_ip, h_port = fetcher.current_host
            self.lbl_server_info.setText(f"主站: {h_name} [{h_ip}:{h_port}] (延迟: {fetcher.latency_ms:.1f}ms)")
        else:
            self.lbl_server_info.setText("主站: 未连接")

        logs = fetcher.get_logs(limit=400)
        html_lines = []
        for line in logs:
            if "[ERROR]" in line or "❌" in line:
                color = "#ff5566"
            elif "[WARN]" in line or "⚠️" in line:
                color = "#ffaa33"
            elif "[SLEEP]" in line or "💤" in line:
                color = "#66ccff"
            elif "[INFO]" in line or "✅" in line:
                color = "#00ff88"
            elif "[SPEED]" in line or "⚡" in line:
                color = "#ffd700"
            else:
                color = "#dcdcdc"
            html_lines.append(f"<div style='color: {color}; margin-bottom: 2px; font-family: monospace;'>{line}</div>")

        self.text_log.setHtml("".join(html_lines))
        if self.chk_auto_scroll.isChecked():
            sb = self.text_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _copy_logs(self):
        from PyQt6.QtWidgets import QApplication
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        logs = TDXRealtimeFetcher.get_instance().get_logs(limit=400)
        QApplication.clipboard().setText("\n".join(logs))

    def _clear_logs(self):
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
        TDXRealtimeFetcher.get_instance().clear_logs()
        self._refresh_logs()


class HotSectorLeaderboardDialog(QWidget, WindowMixin):
    """
    Top 3 强势板块龙头突击跟单看板窗口
    完全独立顶层运行，具备独立任务栏图标与原生暗黑纯黑主题
    """
    code_clicked = pyqtSignal(str, str) # code, name

    def __init__(self, parent=None, restore_state=None):
        super().__init__(None) # [🚀 独立窗口解耦] 传入 None 剥离 Win32 HWND Owner 从属关系，独立任务栏运行，不随主窗口缩放/最小化
        self._py_parent = parent
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False) # 关闭独立子窗口不退出主进程
        self.setWindowTitle("🔥 Top 3 强势板块龙头突击跟单榜 (Hot Alpha Leaderboard)")
        self.resize(1080, 560)
        self.setMinimumWidth(320)
        self.setMinimumHeight(150)
        self._is_updating = False
        self._is_restoring_sort = False

        # 0. Magnetic snap setup & Timers
        self.anchor_edge = None
        self.is_hidden_state = False
        self.normal_geometry = None
        self.hover_ticks = 0
        self.leave_ticks = 0
        self._in_snap_action = False
        self.anim_group = None
        self._is_dragging = False
        self._last_show_time = 0.0
        self._has_hovered_since_show = False
        self._is_auto_popping = False

        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)
        self.hover_timer.start()

        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(400)
        self.snap_timer.timeout.connect(self._detect_and_snap)

        # 1. 窗口置顶与外观
        self.stays_on_top = self._load_stays_on_top()
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # 2. 恢复窗口位置
        if restore_state is None and os.path.exists(WINDOW_CONFIG_FILE):
            try:
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        restore_state = data.get("hot_sector_leaderboard_dialog", {})
            except Exception:
                restore_state = None

        if restore_state:
            try:
                scale = self._get_dpi_scale_factor()
                rx = int(restore_state.get("x", 120) * scale)
                ry = int(restore_state.get("y", 120) * scale)
                rw = int(restore_state.get("width", 1080) * scale)
                rh = int(restore_state.get("height", 560) * scale)
                from gui_utils import clamp_window_to_screens
                rx, ry = clamp_window_to_screens(rx, ry, rw, rh)
                self.normal_geometry = QRect(rx, ry, rw, rh)
                if self.stays_on_top or restore_state.get("stays_on_top", False):
                    self.anchor_edge = None
                    self.is_hidden_state = False
                    self.setWindowOpacity(1.0)
                else:
                    self.anchor_edge = restore_state.get("anchor_edge")
                self.setGeometry(rx, ry, rw, rh)
            except Exception as e:
                logger.warning(f"恢复窗口位置异常: {e}")
                self.load_window_position_qt(self, "hot_sector_leaderboard_dialog", default_width=1080, default_height=560)
        else:
            self.load_window_position_qt(self, "hot_sector_leaderboard_dialog", default_width=1080, default_height=560)

        # 3. 状态与引擎
        self.engine = HotSectorEngine.get_instance()
        self.filter_mode = "ALL" # ALL / TOP5_FOCUS / FOCUS / LOW_VOL / LEADER / BREAKOUT / PULLBACK / SURGE / NEW_CONCEPT
        self.cached_results: List[Dict[str, Any]] = []
        self.current_top_sectors: List[str] = []
        self.active_sectors: set = set() # 当前激活/选中的板块集合
        self.selected_single_sector: Optional[str] = None # 用户手动单选锁定的具体板块名称 (None 表示处于全选模式)
        self.seen_sectors_history: Set[str] = set() # 盘中已出现过的板块历史集合
        self.newly_promoted_sectors: Set[str] = set() # 当前 Top 3 中属于新晋上榜的板块集合
        self.latest_new_sector: Optional[str] = None # 最近一个新晋杀入 Top 3 的新板块名称
        self.last_announced_new_sector: Optional[str] = None # 防重复播报与日志限流
        self._has_init_fetched: bool = False # 记录是否已完成非交易时段初次初始化
        self.tdx_log_dialog: Optional[TDXFetchLogDialog] = None # 独立日志弹窗引用

        # 4. 轮动播报调度器状态 (Round-Robin Alert Scheduler)
        self._alert_rotation_cursor: int = 0  # 候选标的环形轮动游标
        self._stock_alert_cd: Dict[str, float] = {}  # 单股本地冷却记录 {code: last_notified_ts}

        # 4. 初始化 UI 布局与表头
        self.extra_cols = get_ats_extra_cols()
        self.headers, _ = get_leaderboard_headers(self.extra_cols)
        self._init_ui()

        # 5. 恢复上次用户使用的排序列与排序方向
        self._restore_saved_sorting()

        # 6. 秒级高频刷新定时器 (UI 定时刷新，基准 3.0s，支持自适应动态退避)
        self.ui_refresh_timer = QTimer(self)
        self.ui_refresh_timer.setInterval(3000) # 3.0s
        self.ui_refresh_timer.timeout.connect(self._on_ui_timer_tick)
        self.ui_refresh_timer.start()

    def _init_ui(self):
        # 1. 继承统一的 ATS 暗黑 Mode QSS 风格
        apply_dark_theme(self)
        self.setStyleSheet(self.styleSheet() + """
            QDialog {
                background-color: #121214;
                color: #e2e2e5;
                font-family: 'Microsoft YaHei', sans-serif;
            }
            QTableWidget {
                background-color: #18181c;
                alternate-background-color: #1c1c22;
                color: #e2e2e5;
                gridline-color: #282830;
                selection-background-color: #1e334d;
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
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(160, 160, 180, 80); border-radius: 3px; }
            QScrollBar::horizontal { height: 6px; background: transparent; }
            QScrollBar::handle:horizontal { background: rgba(160, 160, 180, 80); border-radius: 3px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── 顶部控制与状态栏 ──
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #18181c; border-radius: 4px; border: 1px solid #282830; }")
        header_lay = QHBoxLayout(header_frame)
        header_lay.setContentsMargins(6, 4, 6, 4)
        header_lay.setSpacing(5)

        # 全选 / 全部板块按钮
        self.btn_top_all = QPushButton("🔥 全部板块")
        self.btn_top_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_top_all.setToolTip("点击重置并显示所有 Top 3 强势板块标的 (默认全选)")
        self.btn_top_all.setStyleSheet("""
            QPushButton { background-color: #1a2a3a; color: #00FFCC; border: 1px solid #00FFCC; border-radius: 3px; font-weight: bold; font-size: 9pt; padding: 2px 6px; }
            QPushButton:hover { background-color: #00FFCC; color: #000000; }
        """)
        self.btn_top_all.clicked.connect(self._on_all_sectors_clicked)
        header_lay.addWidget(self.btn_top_all)

        # Top 3 板块可点击切换按钮容器
        self.sec_tags_layout = QHBoxLayout()
        self.sec_tags_layout.setSpacing(4)

        self.btn_sec1 = QPushButton("🔥 No.1 --")
        self.btn_sec1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec1.setToolTip("点击只显示该板块标的，快速定位板块 (再次点击恢复全选)")
        self.btn_sec1.clicked.connect(lambda: self._select_single_sector(0))

        self.btn_sec2 = QPushButton("🔥 No.2 --")
        self.btn_sec2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec2.setToolTip("点击只显示该板块标的，快速定位板块 (再次点击恢复全选)")
        self.btn_sec2.clicked.connect(lambda: self._select_single_sector(1))

        self.btn_sec3 = QPushButton("🔥 No.3 --")
        self.btn_sec3.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec3.setToolTip("点击只显示该板块标的，快速定位板块 (再次点击恢复全选)")
        self.btn_sec3.clicked.connect(lambda: self._select_single_sector(2))

        self.sec_buttons = [self.btn_sec1, self.btn_sec2, self.btn_sec3]
        for btn in self.sec_buttons:
            self.sec_tags_layout.addWidget(btn)
        
        header_lay.addLayout(self.sec_tags_layout)

        # 🆕 专属新概念/新热点板块极速捕捉直达按钮
        self.btn_new_concept = QPushButton("🆕 暂无新概念")
        self.btn_new_concept.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_concept.setToolTip("盘中新概念极速捕捉：当有新板块杀入 Top 3 时高亮激活，点击可一键直达单选聚焦该新板块 (再次点击恢复全选)")
        self.btn_new_concept.setStyleSheet("""
            QPushButton { background-color: #14161f; color: #555566; border: 1px solid #222533; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt; }
        """)
        self.btn_new_concept.setEnabled(False)
        self.btn_new_concept.clicked.connect(self._on_new_concept_clicked)
        header_lay.addWidget(self.btn_new_concept)

        header_lay.addStretch()

        # 📜 TDX 数据获取日志与异常诊断按钮
        self.btn_log = QPushButton("📜 TDX日志")
        self.btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log.setToolTip("查看通达信 (pytdx) 结构获取数据的实时日志、非交易休眠状态与网络诊断")
        self.btn_log.setStyleSheet("""
            QPushButton { 
                background-color: #1a2233; 
                color: #aad4ff; 
                border: 1px solid #334466; 
                border-radius: 3px; 
                padding: 2px 6px; 
                font-size: 8.5pt; 
                font-weight: bold; 
                height: 20px;
            }
            QPushButton:hover { 
                background-color: #2b3855; 
                color: #00ffcc; 
                border: 1px solid #00ffcc; 
            }
        """)
        self.btn_log.clicked.connect(self._open_tdx_log_dialog)
        header_lay.addWidget(self.btn_log)

        # ⏱️ 盘中时间片生命周期直选 (支持实盘时间自动跟随 / 手动点选锁定)
        self.combo_time_slice = QComboBox()
        self.combo_time_slice.addItems([
            "⚡ 自动实盘跟随",
            "⏱️ 全天全时段",
            "👑 09:30~10:00 黄金定龙",
            "💎 10:00~11:30 分歧低吸",
            "🚀 13:00~14:00 午后助攻",
            "⚠️ 14:00~14:45 尾盘诱多",
            "🔒 14:45~15:00 尾盘定盘"
        ])
        self.combo_time_slice.setMinimumWidth(155)
        self.combo_time_slice.setStyleSheet("""
            QComboBox { background-color: #241e12; color: #ffd700; border: 1px solid #ffaa00; border-radius: 3px; padding: 2px 4px; font-weight: bold; font-size: 8.5pt; min-width: 150px; }
            QComboBox::drop-down { width: 16px; }
            QComboBox QAbstractItemView { background-color: #1e1e24; color: #ffd700; selection-background-color: #3d3014; }
        """)
        self.combo_time_slice.currentIndexChanged.connect(lambda: self._render_table_data(self.cached_results))
        header_lay.addWidget(self.combo_time_slice)

        # ⏱️ 涨速交易时段分段选择器 (极窄紧凑模式，支持30分/15分/60分/开盘/60秒，自动持久化记忆)
        self.combo_segment_mode = QComboBox()
        self.combo_segment_mode.addItems([
            "⏱️ 30分",
            "⏱️ 15分",
            "⏱️ 60分",
            "⏱️ 开盘",
            "⏱️ 60秒"
        ])
        saved_seg_idx = load_config_node("ats_velocity_segment_mode", 0)
        try:
            saved_seg_idx = int(saved_seg_idx)
            if 0 <= saved_seg_idx < self.combo_segment_mode.count():
                self.combo_segment_mode.setCurrentIndex(saved_seg_idx)
        except Exception:
            pass
        self.combo_segment_mode.setToolTip("选择涨速计算的交易时段分段周期: 30分/15分/60分(60F)/开盘累计/60秒 (自动持久化记忆)")
        self.combo_segment_mode.setStyleSheet("""
            QComboBox { background-color: #162536; color: #66ccff; border: 1px solid #336699; border-radius: 3px; padding: 1px 2px; font-weight: bold; font-size: 8.5pt; min-width: 54px; max-width: 66px; }
            QComboBox::drop-down { border: none; width: 12px; }
            QComboBox QAbstractItemView { background-color: #101a26; color: #66ccff; selection-background-color: #243b59; min-width: 90px; }
        """)
        self.combo_segment_mode.currentIndexChanged.connect(self._on_segment_mode_changed)
        header_lay.addWidget(self.combo_segment_mode)

        # 筛选下拉框 (支持盘中极度聚焦与买点分拣)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems([
            "🔥 全部跟单标的", 
            "⭐ 核心聚焦 (Top 5)", 
            "⭐ 仅看重点关注",
            "💎 仅看地量起爆",
            "👑 仅看领涨龙头", 
            "🚀 仅看先锋突破", 
            "💎 仅看反身低吸", 
            "⚡ 仅看扫盘冲板",
            "🆕 仅看新晋概念"
        ])
        self.combo_filter.setStyleSheet("""
            QComboBox { background-color: #1c1c22; color: #00ffaa; border: 1px solid #3e3e4a; border-radius: 3px; padding: 2px 6px; font-size: 9pt; font-weight: bold; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #18181c; color: #ffffff; selection-background-color: #2e3b4e; }
        """)
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        header_lay.addWidget(self.combo_filter)

        # 置顶复选框 (快捷键: T)
        self.chk_on_top = QCheckBox("置顶 (T)")
        self.chk_on_top.setToolTip("开启/关闭窗口置顶 (快捷键: T)")
        self.chk_on_top.setStyleSheet("QCheckBox { color: #00FFCC; font-size: 9pt; font-weight: bold; }")
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.stateChanged.connect(self._on_stays_on_top_toggled)
        header_lay.addWidget(self.chk_on_top)
        bind_top_shortcut(self)

        # 🔔 语音与弹窗预警开关
        self.is_voice_alert_enabled = self._load_voice_alert_enabled()
        self.btn_voice_alert = QPushButton("🟢 语音" if self.is_voice_alert_enabled else "⚪ 静音")
        self.btn_voice_alert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice_alert.setToolTip("开启/关闭 板块龙头突击与异动 语音播报与右下角弹窗通知")
        self._update_voice_btn_style()
        self.btn_voice_alert.clicked.connect(self._toggle_voice_alert)
        header_lay.addWidget(self.btn_voice_alert)

        # 立即刷新按钮
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setFixedWidth(65)
        self.btn_refresh.setStyleSheet("""
            QPushButton { background: #1b382b; color: #00ff88; border: 1px solid #00ff88; border-radius: 3px; font-size: 8.5pt; font-weight: bold; height: 22px; }
            QPushButton:hover { background: #00ff88; color: #000; }
        """)
        self.btn_refresh.clicked.connect(self._force_refresh_data)
        header_lay.addWidget(self.btn_refresh)

        layout.addWidget(header_frame)

        # ── 主表格 ──
        self.table = QTableWidget(0, len(self.headers))
        self.table.setItemDelegate(ColorPreservingItemDelegate(self.table))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)

        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_header.setFixedHeight(28)
        h_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # 列宽持久化配置
        setup_header_persistence(self.table, "hot_sector_alpha_table_v2")
        h_header.setStretchLastSection(True)

        # 监听排序变化并自动持久化
        h_header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

        # 信号连接
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.currentItemChanged.connect(self._on_current_item_changed)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        # ── 底部统计与板块龙头信息栏 ──
        self.bottom_frame = QFrame()
        self.bottom_frame.setStyleSheet("QFrame { background-color: #141620; border-radius: 4px; border: 1px solid #222638; }")
        bottom_lay = QHBoxLayout(self.bottom_frame)
        bottom_lay.setContentsMargins(8, 3, 8, 3)
        bottom_lay.setSpacing(10)

        self.lbl_stats = QLabel("标的: 0 | 👑龙头: 0 | 🚀先锋: 0 | 🎯回踩: 0")
        self.lbl_stats.setStyleSheet("color: #aad4ff; font-size: 9pt; font-weight: bold;")
        bottom_lay.addWidget(self.lbl_stats)

        sep = QLabel("|")
        sep.setStyleSheet("color: #444a66; font-weight: bold;")
        bottom_lay.addWidget(sep)

        self.lbl_sector_leaders = QLabel("👑 板块领涨: --")
        self.lbl_sector_leaders.setStyleSheet("color: #ffbb44; font-size: 9pt; font-weight: bold;")
        bottom_lay.addWidget(self.lbl_sector_leaders)

        bottom_lay.addStretch()

        self.lbl_update_time = QLabel("更新: --:--:--")
        self.lbl_update_time.setStyleSheet("color: #778899; font-size: 8.5pt;")
        bottom_lay.addWidget(self.lbl_update_time)

        layout.addWidget(self.bottom_frame)
        self.setLayout(layout)
        self._update_speed_column_header()

    def _get_current_segment_mode_key(self) -> str:
        """获取当前选中的分段模式 key ('30m', '15m', '60m', 'day_open', '60s')"""
        if not hasattr(self, "combo_segment_mode"):
            return "30m"
        idx = self.combo_segment_mode.currentIndex()
        mode_keys = ["30m", "15m", "60m", "day_open", "60s"]
        if 0 <= idx < len(mode_keys):
            return mode_keys[idx]
        return "30m"

    def _on_segment_mode_changed(self, index: int):
        """用户切换分段周期：自动原子持久化，并触发即时刷新与表头更新"""
        try:
            save_config_node("ats_velocity_segment_mode", int(index))
        except Exception as e:
            logger.debug(f"保存 ats_velocity_segment_mode 异常: {e}")
        self._update_speed_column_header()
        self._force_refresh_data()

    def _update_speed_column_header(self):
        """根据当前分段模式动态更新第 6 列表头名称 (支持 60F 简写)"""
        mode = self._get_current_segment_mode_key()
        label_map = {
            "30m": "30分涨速%",
            "15m": "15分涨速%",
            "60m": "60分涨速%",
            "day_open": "开盘涨速%",
            "60s": "60秒涨速%"
        }
        col_label = label_map.get(mode, "时段涨速%")
        item = self.table.horizontalHeaderItem(6)
        if item:
            item.setText(col_label)
            tip_map = {
                "30m": "30分交易分段净涨速% (30F)",
                "15m": "15分交易分段净涨速% (15F)",
                "60m": "60分交易分段净涨速% (60F)",
                "day_open": "全天开盘累计净涨速%",
                "60s": "60秒滑动微观涨速%"
            }
            item.setToolTip(tip_map.get(mode, "交易时段分段涨速%"))

    def _get_parent_mw(self):
        # 1. 优先从 _py_parent 或 parent() 链条查找
        curr = getattr(self, '_py_parent', None) or (self.parent() if hasattr(self, 'parent') and callable(self.parent) else None)
        while curr:
            if hasattr(curr, 'link_stock') or hasattr(curr, 'on_stock_clicked'):
                return curr
            curr = getattr(curr, '_py_parent', None) or (curr.parent() if hasattr(curr, 'parent') and callable(curr.parent) else None)

        # 2. 遍历顶层窗口查找 ATSMainWindow
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(widget) and hasattr(widget, 'link_stock'):
                        return widget
                except Exception:
                    pass
        return None

    def _load_stays_on_top(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        cfg = data.get("hot_sector_leaderboard_dialog", {})
                        return cfg.get("stays_on_top", False)
        except Exception:
            pass
        return False

    def _on_stays_on_top_toggled(self, state):
        self.stays_on_top = self.chk_on_top.isChecked()
        if self.stays_on_top:
            # 【置顶与磁吸互斥】：开启置顶时，立即退出磁吸并恢复正常窗口显示
            if self.is_hidden_state:
                self.show_normal_position()
            self.anchor_edge = None
            self.normal_geometry = None
            self.snap_timer.stop()
            self.hover_ticks = 0
            self.leave_ticks = 0
            self.setWindowOpacity(1.0)
        set_seamless_stay_on_top(self, self.stays_on_top)
        self._save_window_states()

    def _save_window_states(self, is_open=None) -> None:
        try:
            scale = self._get_dpi_scale_factor()
            geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
            width = max(200, int(geom.width() / scale))
            height = max(100, int(geom.height() / scale))
            x = int(geom.x() / scale)
            y = int(geom.y() / scale)

            if is_open is None:
                is_open = self.isVisible() or getattr(self, 'is_hidden_state', False)

            node_data = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "stays_on_top": self.stays_on_top,
                "anchor_edge": None if self.stays_on_top else self.anchor_edge,
                "is_hidden_state": False if self.stays_on_top else self.is_hidden_state,
                "is_open": bool(is_open)
            }
            from ats.ui.styles import save_config_node
            save_config_node("hot_sector_leaderboard_dialog", node_data)
        except Exception as e:
            logger.warning(f"保存热榜窗口状态异常: {e}")

    # ── 排序自动持久化与恢复 ──
    def _on_sort_indicator_changed(self, logical_index: int, order: Qt.SortOrder):
        if self._is_updating or self._is_restoring_sort:
            return
        try:
            save_config_node("hot_sector_sort_col", int(logical_index))
            save_config_node("hot_sector_sort_order", int(order.value))
        except Exception as e:
            logger.debug(f"保存排序列异常: {e}")

    def _restore_saved_sorting(self):
        self._is_restoring_sort = True
        try:
            saved_col = load_config_node("hot_sector_sort_col")
            saved_order = load_config_node("hot_sector_sort_order")
            
            score_col = self.headers.index("综合得分") if "综合得分" in self.headers else (len(self.headers) - 2)
            default_col = int(saved_col) if saved_col is not None and 0 <= int(saved_col) < len(self.headers) else score_col
            default_order = Qt.SortOrder(int(saved_order)) if saved_order is not None else Qt.SortOrder.DescendingOrder

            self.table.horizontalHeader().setSortIndicator(default_col, default_order)
        except Exception as e:
            logger.debug(f"恢复排序列异常: {e}")
        finally:
            self._is_restoring_sort = False

    # ── 板块按钮交互与过滤 ──
    def _on_all_sectors_clicked(self):
        """点击【全部板块】：一键全选并激活所有当前 Top 3 强势板块 (解除单选模式)"""
        valid_secs = [s for s in self.current_top_sectors if is_valid_sector_name(s)]
        self.selected_single_sector = None
        self.active_sectors = set(valid_secs)
        self._update_sector_button_styles()
        self._render_table_data(self.cached_results)

    def _select_single_sector(self, sec_idx: int):
        """点击单个板块按钮：只显示该点击板块（快速定位板块），若已唯选该板块再次点击则恢复全选"""
        if sec_idx >= len(self.current_top_sectors):
            return
        sec_name = self.current_top_sectors[sec_idx]
        if not is_valid_sector_name(sec_name):
            return

        valid_secs = [s for s in self.current_top_sectors if is_valid_sector_name(s)]
        # 如果当前已经是唯一选中该板块，再次点击则切回全部板块；否则单选该板块
        if self.selected_single_sector == sec_name or self.active_sectors == {sec_name}:
            self.selected_single_sector = None
            self.active_sectors = set(valid_secs)
        else:
            self.selected_single_sector = sec_name
            self.active_sectors = {sec_name}

        self._update_sector_button_styles()
        self._render_table_data(self.cached_results)

    def _on_new_concept_clicked(self):
        """点击【🆕 新概念】直达按钮：一键聚焦查看最新冲入 Top 3 的新板块龙头与跟单标的，再次点击恢复全选"""
        target_sec = self.latest_new_sector
        valid_secs = [s for s in self.current_top_sectors if is_valid_sector_name(s)]
        if not target_sec or not is_valid_sector_name(target_sec) or target_sec not in valid_secs:
            return

        if self.selected_single_sector == target_sec or self.active_sectors == {target_sec}:
            # 已经处于该新概念单选聚焦态，再次点击平滑切回全选
            self.selected_single_sector = None
            self.active_sectors = set(valid_secs)
        else:
            # 一键直达聚焦该新概念
            self.selected_single_sector = target_sec
            self.active_sectors = {target_sec}

        self._update_sector_button_styles()
        self._render_table_data(self.cached_results)

    def _update_sector_button_styles(self):
        """刷新顶部 全部板块、新概念按钮及 3 个板块按钮的高亮/置灰状态与 🆕 徽章"""
        color_themes = [
            ("#2a1b1b", "#ff5577", "#ff4466"), # No.1 红色系
            ("#2a221b", "#ffaa44", "#ff9933"), # No.2 橙色系
            ("#1b262a", "#44ddff", "#33bbdd"), # No.3 青色系
        ]
        
        valid_current = [s for s in self.current_top_sectors if is_valid_sector_name(s)]
        all_active = (self.selected_single_sector is None) and (set(valid_current) <= self.active_sectors) and len(valid_current) > 0
        if all_active:
            self.btn_top_all.setStyleSheet("""
                QPushButton { background-color: #1a2a3a; color: #00FFCC; border: 1px solid #00FFCC; border-radius: 3px; font-weight: bold; font-size: 9pt; padding: 2px 6px; }
                QPushButton:hover { background-color: #00FFCC; color: #000000; }
            """)
        else:
            self.btn_top_all.setStyleSheet("""
                QPushButton { background-color: #141720; color: #778899; border: 1px solid #24293e; border-radius: 3px; font-weight: bold; font-size: 9pt; padding: 2px 6px; }
                QPushButton:hover { background-color: #00FFCC; color: #000000; }
            """)

        # 🆕 刷新专属新概念按钮状态
        if hasattr(self, "btn_new_concept"):
            if self.latest_new_sector and self.latest_new_sector in valid_current:
                is_new_active = (self.selected_single_sector == self.latest_new_sector) or (self.active_sectors == {self.latest_new_sector})
                s_short = self.latest_new_sector.split('(')[0] if '(' in self.latest_new_sector else self.latest_new_sector
                if is_new_active:
                    self.btn_new_concept.setText(f"🆕 聚焦: {s_short}")
                    self.btn_new_concept.setStyleSheet("""
                        QPushButton { background-color: #4a1d6d; color: #ffffff; border: 1px solid #d055ff; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 8.5pt; }
                        QPushButton:hover { background-color: #d055ff; color: #000000; }
                    """)
                else:
                    self.btn_new_concept.setText(f"🆕 新概念: {s_short}")
                    self.btn_new_concept.setStyleSheet("""
                        QPushButton { background-color: #231530; color: #e077ff; border: 1px solid #a344db; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 8.5pt; }
                        QPushButton:hover { background-color: #a344db; color: #ffffff; }
                    """)
                self.btn_new_concept.setToolTip(f"【🆕 盘中新概念突击】板块【{self.latest_new_sector}】最新冲入 Top 3！\n点击一键快速聚焦查看该新板块全部龙头与跟单标的 (再次点击恢复全选)")
                self.btn_new_concept.setEnabled(True)
            else:
                self.btn_new_concept.setText("🆕 暂无新概念")
                self.btn_new_concept.setStyleSheet("""
                    QPushButton { background-color: #14161f; color: #555566; border: 1px solid #222533; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt; }
                """)
                self.btn_new_concept.setToolTip("盘中新概念极速捕捉：当前 Top 3 强势板块保持稳定，无新晋轮动板块")
                self.btn_new_concept.setEnabled(False)

        # 刷新 3 个板块按钮
        for i, btn in enumerate(self.sec_buttons):
            if i < len(self.current_top_sectors):
                sname = self.current_top_sectors[i]
                if not is_valid_sector_name(sname):
                    btn.setVisible(False)
                    continue
                is_promoted = (sname in self.newly_promoted_sectors)
                prefix_tag = "🆕" if is_promoted else ""
                btn.setText(f"🔥 No.{i+1} {prefix_tag}{sname}")
                btn.setVisible(True)

                is_active = (sname in self.active_sectors)
                bg, fg, border = color_themes[i] if i < len(color_themes) else ("#181b26", "#ffffff", "#334466")
                
                if is_active:
                    btn.setStyleSheet(f"""
                        QPushButton {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; border-radius: 3px; padding: 2px 5px; font-weight: bold; font-size: 9pt; }}
                        QPushButton:hover {{ background-color: {border}; color: #ffffff; }}
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton { background-color: #14161f; color: #555566; border: 1px solid #222533; border-radius: 3px; padding: 2px 5px; font-size: 9pt; }
                        QPushButton:hover { background-color: #1f2333; color: #888899; }
                    """)
                tip = f"【🔥 No.{i+1} 强势板块】点击只显示该板块标的，快速定位板块 (再次点击恢复全选)"
                if is_promoted:
                    tip = f"【🆕 盘中新概念突击】板块【{sname}】刚刚新晋冲入 Top 3！\n点击快速单选聚焦该板块标的 (再次点击恢复全选)"
                btn.setToolTip(tip)
            else:
                btn.setVisible(False)

    def _on_filter_changed(self, idx):
        if idx == 1:
            self.filter_mode = "TOP5_FOCUS" # ⭐ 核心聚焦 (Top 5)
        elif idx == 2:
            self.filter_mode = "FOCUS"      # ⭐ 仅看重点关注
        elif idx == 3:
            self.filter_mode = "LOW_VOL"    # 💎 仅看地量起爆
        elif idx == 4:
            self.filter_mode = "LEADER"     # 👑 仅看领涨龙头
        elif idx == 5:
            self.filter_mode = "BREAKOUT"   # 🚀 仅看先锋突破
        elif idx == 6:
            self.filter_mode = "PULLBACK"   # 💎 仅看反身低吸
        elif idx == 7:
            self.filter_mode = "SURGE"      # ⚡ 仅看扫盘冲板
        elif idx == 8:
            self.filter_mode = "NEW_CONCEPT" # 🆕 仅看新晋概念
        else:
            self.filter_mode = "ALL"
        self._render_table_data(self.cached_results)

    def _open_tdx_log_dialog(self):
        """打开/激活通达信高频数据获取诊断日志独立窗口"""
        from PyQt6.sip import isdeleted
        if self.tdx_log_dialog is not None and not isdeleted(self.tdx_log_dialog):
            self.tdx_log_dialog.show()
            self.tdx_log_dialog.raise_()
            self.tdx_log_dialog.activateWindow()
            return
        
        self.tdx_log_dialog = TDXFetchLogDialog(parent=self)
        self.tdx_log_dialog.show()
        self.tdx_log_dialog.raise_()
        self.tdx_log_dialog.activateWindow()

    def _force_refresh_data(self):
        self._on_ui_timer_tick(force=True)

    def _on_ui_timer_tick(self, force=False):
        """定时从主窗口提取 Top3 强势板块与 current_df 进行计算与渲染，非交易时段智能休眠"""
        if self._is_updating or getattr(self, '_is_dragging', False):
            return

        from ats.tdx_realtime_fetcher import is_trading_time, TDXRealtimeFetcher
        fetcher = TDXRealtimeFetcher.get_instance()
        is_trading, session_desc = is_trading_time()

        # 非交易时段智能休眠策略：
        # 如果非交易时段，且已完成至少一次初始化获取，且非用户手动强制刷新，则跳过网络拉取避免被通达信封禁
        if not is_trading and self._has_init_fetched and not force:
            self.lbl_update_time.setText(f"💤 非交易休眠 ({time.strftime('%H:%M:%S')})")
            return

        main_app = self._get_parent_mw()
        top_sectors = []
        current_df = None
        manual_list = None

        if main_app:
            if hasattr(main_app, "current_df"):
                current_df = main_app.current_df

            # 尝试从热力图组件提取 Top 3 板块 (联动跟随热力图当前选择的排序维度)
            if hasattr(main_app, "heatmap_widget") and main_app.heatmap_widget:
                hw = main_app.heatmap_widget
                if hasattr(hw, "get_top_sectors"):
                    top_sectors = hw.get_top_sectors(top_n=3)
                    sec_to_codes = getattr(hw, "sector_to_codes", {})
                    sort_idx = hw.sort_combo.currentIndex() if hasattr(hw, 'sort_combo') else 0
                    self.engine.extract_top_sectors_from_heatmap(getattr(hw, "sectors", []), sec_to_codes, top_n=3, sort_mode=sort_idx)
                elif hasattr(hw, "sectors") and hw.sectors:
                    sec_to_codes = getattr(hw, "sector_to_codes", {})
                    top_sectors = self.engine.extract_top_sectors_from_heatmap(hw.sectors, sec_to_codes, top_n=3)

            # 龙头突击榜标的严格来源于当前 Top 3 强势板块与新增板块成分股，不强行注入非热点自选股
            manual_list = None
        else:
            manual_list = None

        # 过滤非明确板块
        top_sectors = [s for s in top_sectors if is_valid_sector_name(s)]
        # 降级默认板块
        if not top_sectors:
            top_sectors = ["共封装光学(CPO)", "国家大基金持股", "存储芯片"]

        # 板块变化或初次加载时初始化 active_sectors 并触发新概念检测
        if self.current_top_sectors != top_sectors:
            old_sectors_set = set(self.current_top_sectors)
            new_sectors_set = set(top_sectors)

            # 1. 盘中新概念捕捉：检测新晋进入 Top 3 的板块
            if self._has_init_fetched and old_sectors_set:
                brand_new = [s for s in top_sectors if s not in old_sectors_set]
                if brand_new:
                    for s in brand_new:
                        self.newly_promoted_sectors.add(s)
                        self.seen_sectors_history.add(s)
                    self.latest_new_sector = brand_new[0]
                    if self.latest_new_sector != self.last_announced_new_sector:
                        self.last_announced_new_sector = self.latest_new_sector
                        fetcher.add_log(f"🚀 盘中新概念突发:【{self.latest_new_sector}】新晋冲入 Top 3 强势榜", level="SPEED")
            else:
                # 首次初始化启动时记录基础板块
                for s in top_sectors:
                    self.seen_sectors_history.add(s)

            # 清理跌出当前 Top 3 的新晋板块
            self.newly_promoted_sectors = {s for s in self.newly_promoted_sectors if s in new_sectors_set}
            if self.latest_new_sector and self.latest_new_sector not in new_sectors_set:
                self.latest_new_sector = next(iter(self.newly_promoted_sectors), None)

            self.current_top_sectors = list(top_sectors)

            # 2. 选区状态机同步（彻底修复默认全选 Bug）
            if self.selected_single_sector is None:
                # 全选模式 (默认)：新出现的板块自动加入 active_sectors，保持 100% 全选展示！
                self.active_sectors = set(top_sectors)
            else:
                # 单选模式：检查用户单选的板块是否仍在 Top 3
                if self.selected_single_sector in new_sectors_set:
                    self.active_sectors = {self.selected_single_sector}
                else:
                    # 单选板块已跌出 Top 3，自动平滑解除单选恢复全选
                    self.selected_single_sector = None
                    self.active_sectors = set(top_sectors)

            self._update_sector_button_styles()

        # 计算并返回最新 Alpha 列表
        try:
            if not is_trading:
                fetcher.add_log(f"非交易时段初始化/单次手动刷新 ({session_desc})", level="SLEEP")
            seg_mode = self._get_current_segment_mode_key()
            results = self.engine.compute_hot_alpha_leaderboard(
                top_sector_names=top_sectors,
                current_df=current_df,
                manual_watchlist=manual_list,
                segment_mode=seg_mode
            )
            self.cached_results = results
            self._render_table_data(results)
            self._has_init_fetched = True

            # 动态根据 TDX 自适应退避机制同步 UI 刷新定时器
            rec_ms = fetcher.get_recommended_interval_ms()
            if self.ui_refresh_timer.interval() != rec_ms:
                self.ui_refresh_timer.setInterval(rec_ms)
        except Exception as e:
            fetcher.add_log(f"热榜轮询计算异常: {e}", level="ERROR")
            logger.warning(f"热榜轮询计算异常: {e}")

    def _render_table_data(self, results: List[Dict[str, Any]]):
        """将 Alpha 结果渲染到表格，支持原地更新、滚动条与选中焦点严格保持"""
        if not results:
            return

        self._is_updating = True

        # 1. 记录刷新前的状态 (选中的股票代码、垂直与水平滚动条位置、当前排序规则)
        curr_selected_code = None
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            it = self.table.item(curr_row, 0)
            if it:
                curr_selected_code = it.text().strip()

        saved_scroll_v = self.table.verticalScrollBar().value()
        saved_scroll_h = self.table.horizontalScrollBar().value()

        h_header = self.table.horizontalHeader()
        sort_col = h_header.sortIndicatorSection()
        sort_order = h_header.sortIndicatorOrder()

        # 2. 过滤数据
        raw_slice = self.combo_time_slice.currentText() if hasattr(self, "combo_time_slice") else "⚡ 自动实盘跟随"
        if "全天全时段" in raw_slice:
            time_slice = "⏱️ 全天全时段"
        elif "自动实盘跟随" in raw_slice:
            from ats.limit_up_engine import get_live_time_slice_name
            time_slice = get_live_time_slice_name()
        else:
            time_slice = raw_slice

        # 获取全局重点关注集合 (用于在当前板块中精准匹配重点关注标的)
        from global_favorites import GlobalFavoriteManager
        fav_set = set(GlobalFavoriteManager().get_favorite_stocks())
        parent_mw = self._get_parent_mw()
        if parent_mw and hasattr(parent_mw, "fav_stocks") and parent_mw.fav_stocks:
            fav_set |= set(parent_mw.fav_stocks)

        filtered = []
        for r in results:
            sec = r.get("sector", "")
            code_str = str(r.get("code", "")).strip().zfill(6)
            # 只有当该股票属于当前有效热点板块成分股，且其 code 存在于用户的重点关注中，才是有效匹配
            is_fav = (code_str in fav_set)
            r["is_focus"] = is_fav

            # 🛡️ 过滤非明确板块
            if not is_valid_sector_name(sec):
                continue

            # 板块标签开关过滤：标的必须严格属于当前激活的热点板块 (当前 Top 3 或单选板块)
            if self.active_sectors and sec not in self.active_sectors:
                continue

            tag = r.get("buy_tag", "")
            pct = float(r.get("pct", 0.0))
            vwap_dev = float(r.get("vwap_dev_pct", 0.0))

            # ⏱️ 盘中时间片生命周期过滤 (全天全时段时跳过过滤)
            if "全天全时段" in time_slice:
                pass
            elif "黄金定龙" in time_slice:
                if tag not in ("LEADER", "SURGE", "BREAKOUT") and pct < 4.0:
                    continue
            elif "分歧低吸" in time_slice:
                if tag != "PULLBACK" and not (-0.5 <= vwap_dev <= 2.0 and 0.5 <= pct <= 5.0):
                    continue
            elif "午后助攻" in time_slice:
                if tag not in ("BREAKOUT", "SURGE", "LEADER"):
                    continue
            elif "尾盘诱多" in time_slice:
                if tag != "WEAK" and not (pct >= 5.0 and vwap_dev > 4.0):
                    continue
            elif "尾盘定盘" in time_slice:
                if tag != "LEADER":
                    continue

            # 筛选模式过滤
            if getattr(self, "filter_mode", "ALL") == "TOP5_FOCUS":
                filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "FOCUS":
                # ⭐ 仅看重点关注：仅展示当前板块中匹配了重点关注的标的
                if is_fav:
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "LOW_VOL":
                if "地量" in r.get("buy_type", "") or "地量" in r.get("reason", ""):
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "LEADER":
                if tag == "LEADER":
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "BREAKOUT":
                if tag == "BREAKOUT":
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "PULLBACK":
                if tag == "PULLBACK":
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "SURGE":
                if tag == "SURGE":
                    filtered.append(r)
            elif getattr(self, "filter_mode", "ALL") == "NEW_CONCEPT":
                if sec in self.newly_promoted_sectors or (self.latest_new_sector and sec == self.latest_new_sector):
                    filtered.append(r)
            else:
                filtered.append(r)

        # 👑 重点关注优先置顶排序：无论当前处于何种筛选模式，重点关注的 code 永远优先置顶排在最前！
        # 👑 同加速类型后在对比 Alpha 得分与开盘下影微小度：双加速 > 单加速 > 常规，同类型内得分最高优先
        filtered.sort(key=lambda x: (
            0 if str(x.get("code", "")).strip().zfill(6) in fav_set else 1,
            0 if x.get("is_dual_accel") else (1 if (x.get("is_open_low_accel") or x.get("is_gap_accel")) else 2),
            -float(x.get("alpha_score", 0.0)),
            float(x.get("low_diff_pct", 999.0))
        ))

        if getattr(self, "filter_mode", "ALL") == "TOP5_FOCUS":
            filtered = filtered[:5]

        # 3. 原地填充表格
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        if self.table.rowCount() != len(filtered):
            self.table.setRowCount(len(filtered))

        font_bold = QFont()
        font_bold.setBold(True)

        for row_idx, r in enumerate(filtered):
            self._populate_row(row_idx, r, font_bold, fav_set)

        # 4. 恢复并应用用户当前指定的排序列
        self.table.setSortingEnabled(True)
        if 0 <= sort_col < len(self.headers):
            self.table.sortItems(sort_col, sort_order)

        # 5. 恢复选中的焦点行
        if curr_selected_code:
            for r_idx in range(self.table.rowCount()):
                it = self.table.item(r_idx, 0)
                if it and it.text().strip() == curr_selected_code:
                    self.table.setCurrentCell(r_idx, 0)
                    break

        # 6. 恢复滚动条位置 (杜绝跳屏)
        self.table.verticalScrollBar().setValue(saved_scroll_v)
        self.table.horizontalScrollBar().setValue(saved_scroll_h)
        self.table.blockSignals(False)

        # 7. 更新底部统计栏与各板块领跑个股
        total_cnt = len(filtered)
        fav_cnt = sum(1 for x in filtered if str(x.get("code", "")).strip().zfill(6) in fav_set)
        leader_cnt = sum(1 for x in filtered if x.get("buy_tag") == "LEADER")
        surge_cnt = sum(1 for x in filtered if x.get("buy_tag") == "SURGE")
        breakout_cnt = sum(1 for x in filtered if x.get("buy_tag") == "BREAKOUT")
        pullback_cnt = sum(1 for x in filtered if x.get("buy_tag") == "PULLBACK")

        fav_info = f"⭐关注: {fav_cnt} | " if fav_cnt > 0 else ""
        self.lbl_stats.setText(f"标的: {total_cnt} | {fav_info}👑龙头: {leader_cnt} | ⚡扫盘: {surge_cnt} | 🚀先锋: {breakout_cnt} | 💎回踩: {pullback_cnt}")

        # 找出各板块内涨幅最高的领跑股
        sec_leaders = {}
        for x in filtered:
            s = x.get("sector", "")
            if not is_valid_sector_name(s) or s == "重点关注":
                continue
            if s not in sec_leaders or x.get("pct", -999) > sec_leaders[s].get("pct", -999):
                sec_leaders[s] = x

        leader_strs = []
        for s in self.current_top_sectors:
            if not is_valid_sector_name(s):
                continue
            if s in sec_leaders:
                lead_stock = sec_leaders[s]
                s_short = s.split('(')[0] if '(' in s else s
                is_new = "🆕" if s in self.newly_promoted_sectors else ""
                leader_strs.append(f"{is_new}{s_short}: {lead_stock['name']}({lead_stock['pct']:+.2f}%)")

        self.lbl_update_time.setText(time.strftime("更新: %H:%M:%S"))

        self._is_updating = False

        # 🔔 触发强势板块龙头突击特异标的语音与弹窗通知
        self._check_and_notify_sector_highlights(filtered)

    def _load_voice_alert_enabled(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("hot_sector_leaderboard", {}).get("voice_alert_enabled", True)
        except Exception:
            pass
        return True

    def _save_voice_alert_enabled(self, enabled: bool):
        try:
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(WINDOW_CONFIG_FILE):
                    try:
                        with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                if "hot_sector_leaderboard" not in data:
                    data["hot_sector_leaderboard"] = {}
                data["hot_sector_leaderboard"]["voice_alert_enabled"] = enabled
                with open(WINDOW_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Save voice_alert_enabled failed: {e}")

    def _toggle_voice_alert(self):
        self.is_voice_alert_enabled = not self.is_voice_alert_enabled
        self._save_voice_alert_enabled(self.is_voice_alert_enabled)
        self._update_voice_btn_style()

    def _update_voice_btn_style(self):
        if not hasattr(self, 'btn_voice_alert'):
            return
        if self.is_voice_alert_enabled:
            self.btn_voice_alert.setText("🟢 语音")
            self.btn_voice_alert.setStyleSheet("""
                QPushButton {
                    background-color: #102a1e;
                    color: #00ff88;
                    font-weight: bold;
                    font-size: 8.5pt;
                    border: 1px solid #00cc66;
                    border-radius: 3px;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #00cc66;
                    color: #ffffff;
                }
            """)
        else:
            self.btn_voice_alert.setText("⚪ 静音")
            self.btn_voice_alert.setStyleSheet("""
                QPushButton {
                    background-color: #24242e;
                    color: #8e8e93;
                    font-weight: bold;
                    font-size: 8.5pt;
                    border: 1px solid #444455;
                    border-radius: 3px;
                    padding: 2px 6px;
                }
                QPushButton:hover {
                    background-color: #333344;
                    color: #ffffff;
                }
            """)

    def locate_stock_in_table(self, code: str, auto_popup: bool = False):
        """【全端联动定位】在板块跟单榜中高亮并居中定位该股"""
        if not code or not hasattr(self, 'table'):
            return
        c = str(code).strip().zfill(6)
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            if code_item and code_item.text().strip().zfill(6) == c:
                self.table.selectRow(row)
                self.table.scrollToItem(code_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                name_item = self.table.item(row, 1)
                n = name_item.text().strip() if name_item else c
                self._broadcast_link_stock(c, n)
                if auto_popup:
                    if hasattr(self, 'isMinimized') and self.isMinimized():
                        self.showNormal()
                    if hasattr(self, 'isHidden') and self.isHidden():
                        self.show()
                    self.show()
                    self.raise_()
                    self.activateWindow()
                break

    def _broadcast_link_stock(self, code: str, name: str):
        """向全局主窗口与外部行情终端广播联动"""
        try:
            self.code_clicked.emit(code, name)
            main_win = self._get_parent_mw()
            if main_win and hasattr(main_win, "link_stock"):
                main_win.link_stock(code, name)
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, 'main_window') and isinstance(app.main_window, ATSMainWindow):
                app.main_window.link_stock(code, name)
        except Exception:
            pass

    def _check_and_notify_sector_highlights(self, filtered_records: List[Dict[str, Any]]):
        """【板块龙头与特异异动自动挖掘通知】采用环形游标轮询 (Round-Robin) 与单股防刷屏冷却，依次轮动推送达标标的"""
        if not getattr(self, "is_voice_alert_enabled", True):
            return
        if not filtered_records:
            return
        try:
            from ats.alert_notifier import AlertNotifier
            notifier = AlertNotifier.get_instance()

            # 1. 收集达标的优质候选标的池 (按优先级分层：双加速优先，其次打分 >= 80 或领涨/突破强特征标的)
            dual_cands = [r for r in filtered_records if r.get("is_dual_accel")]
            other_cands = []
            for r in filtered_records:
                if r.get("is_dual_accel"):
                    continue
                score = float(r.get("alpha_score", 0.0))
                tag = r.get("buy_tag", "")
                if score >= 80.0 or tag in ("LEADER", "SURGE", "BREAKOUT", "PULLBACK") or r.get("sector") == "重点关注":
                    other_cands.append(r)

            # 候选池按优先级组合：双加速在前，优质其他标的在后 (最多截取前 12 只构建轮动池)
            pool = (dual_cands + other_cands)[:12]
            if not pool:
                return

            if not hasattr(self, "_alert_rotation_cursor"):
                self._alert_rotation_cursor = 0
            if not hasattr(self, "_stock_alert_cd"):
                self._stock_alert_cd = {}

            now_ts = time.time()
            SECTOR_STOCK_CD = 180.0  # 单股本地轮动冷却周期：3分钟 (180秒)

            selected_cand = None
            selected_idx = -1
            n_cands = len(pool)

            # 2. 环形游标轮询扫描 (Round-Robin Scan)：
            # 从当前游标开始环形扫描一周，挑选出首个满足 180 秒冷却周期的优质标的
            for step in range(n_cands):
                curr_idx = (self._alert_rotation_cursor + step) % n_cands
                cand = pool[curr_idx]
                c = str(cand.get("code", "")).zfill(6)
                last_ts = self._stock_alert_cd.get(c, 0.0)

                if (now_ts - last_ts) >= SECTOR_STOCK_CD:
                    selected_cand = cand
                    selected_idx = curr_idx
                    break

            # 若所有候选标的均在 180 秒冷却期内，静默等待冷却，不重复轰炸同一只股票
            if selected_cand is None:
                return

            # 3. 推进游标至下一位置，实现平滑流水式轮动！
            self._alert_rotation_cursor = (selected_idx + 1) % n_cands

            c = str(selected_cand.get("code", "")).zfill(6)
            self._stock_alert_cd[c] = now_ts

            n = str(selected_cand.get("name", c))
            score = float(selected_cand.get("alpha_score", 88.0))
            buy_type = str(selected_cand.get("buy_type", ""))
            sec = str(selected_cand.get("sector", ""))
            reason = f"{buy_type} | {selected_cand.get('reason', '')}"

            notifier.notify_special_signal(code=c, name=n, reason=reason, score=score, parent=self, source="龙头突击")
        except Exception as e:
            logger.debug(f"_check_and_notify_sector_highlights error: {e}")

    def _populate_row(self, row_idx: int, r: Dict[str, Any], font_bold: QFont, fav_set: Optional[set] = None):
        """填充/原位更新单行数据，支持重点关注置顶与金色高亮"""
        code = str(r.get("code", "--"))
        name = str(r.get("name", "--"))
        sec = str(r.get("sector", "--"))
        buy_type = str(r.get("buy_type", "蓄势观察"))
        buy_tag = str(r.get("buy_tag", "OBSERVE"))
        price = float(r.get("price", 0.0))
        pct = float(r.get("pct", 0.0))
        vel_pct = float(r.get("velocity_pct", 0.0))
        vel_tag = r.get("velocity_tag", "⏱️ 窄幅横盘")
        seg_label = r.get("segment_label", "⏱️ 30分分段")
        seg_base_p = float(r.get("segment_base_price", price))
        seg_amt_wan = float(r.get("segment_amount_wan", 0.0))
        is_midway = r.get("is_midway_init", False)
        turnover = float(r.get("turnover", 0.0))
        vol_r = float(r.get("vol_ratio", 1.0))
        intent = r.get("order_intent", "⚖️ 均衡博弈")
        slope = float(r.get("slope_score", 50.0))
        vwap_dev = float(r.get("vwap_dev_pct", 0.0))
        dff = float(r.get("dff", r.get("DFF", 0.0)) or 0.0)
        rank_val = r.get("rank", r.get("Rank", r.get("排名", 0)))
        dff2 = float(r.get("dff2", r.get("DFF2", 0.0)) or 0.0)
        dff3 = float(r.get("dff3", r.get("DFF3", 0.0)) or 0.0)
        extra_vals = r.get("extra_vals", {})
        buy_zone = str(r.get("buy_zone", "--"))
        stop_loss = str(r.get("stop_loss", "--"))
        alpha_score = float(r.get("alpha_score", 0.0))
        reason = str(r.get("reason", "--"))

        # 判定是否属于重点关注
        code_clean = code.strip().zfill(6)
        is_fav = False
        if fav_set is not None:
            is_fav = (code_clean in fav_set)
        else:
            try:
                from global_favorites import GlobalFavoriteManager
                is_fav = (code_clean in GlobalFavoriteManager().get_favorite_stocks())
            except Exception:
                pass
        pin_rank = 0 if is_fav else 999
        fav_bg = QColor(60, 45, 12, 110) if is_fav else None

        pct_color = QColor("#ff4455") if pct > 0 else (QColor("#00ee77") if pct < 0 else QColor("#cccccc"))
        
        # 买点类型专属精细化视觉高亮
        if "双加速" in buy_type:
            type_color = QColor("#FFD700") # 金黄双加速
            type_bg = QColor(80, 20, 60, 180) # 尊荣金紫
        elif buy_tag == "LEADER":
            type_color = QColor("#FF3399") # 亮洋红领涨龙头
            type_bg = QColor(65, 20, 45, 160)
        elif buy_tag == "SURGE":
            type_color = QColor("#FF5533") # 亮橙红扫盘冲板
            type_bg = QColor(65, 30, 20, 160)
        elif "光脚加速" in buy_type:
            type_color = QColor("#FFAA00") # 亮橙黄光脚加速
            type_bg = QColor(60, 35, 10, 160)
        elif "缺口加速" in buy_type:
            type_color = QColor("#FF55BB") # 亮粉紫缺口加速
            type_bg = QColor(50, 15, 45, 160)
        elif buy_tag == "BREAKOUT":
            type_color = QColor("#00FF88") # 荧光绿先锋起爆
            type_bg = QColor(10, 50, 30, 150)
        elif buy_tag == "PULLBACK":
            type_color = QColor("#00FFFF") # 荧光亮青反身低吸
            type_bg = QColor(10, 45, 60, 160)
        elif buy_tag == "WEAK":
            type_color = QColor("#FF8800") # 橙色破位
            type_bg = QColor(50, 30, 10, 140)
        else:
            type_color = QColor("#aaaaaa")
            type_bg = QColor(30, 30, 35, 100)

        # 0: 代码
        it_code = NumericTableWidgetItem(code, is_pinned=is_fav, pin_rank=pin_rank)
        it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_fav:
            it_code.setForeground(QBrush(QColor("#ffd700")))
            it_code.setFont(font_bold)
            it_code.setBackground(QBrush(fav_bg))
        else:
            it_code.setForeground(QBrush(QColor("#aad4ff")))
        self.table.setItem(row_idx, 0, it_code)

        # 1: 名称 (重点关注加 ⭐ 徽章)
        disp_name = f"⭐ {name}" if is_fav and not name.startswith("⭐") else name
        it_name = NumericTableWidgetItem(disp_name, is_pinned=is_fav, pin_rank=pin_rank)
        it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_fav:
            it_name.setForeground(QBrush(QColor("#ffd700")))
            it_name.setBackground(QBrush(fav_bg))
        else:
            it_name.setForeground(QBrush(QColor("#ffffff")))
        it_name.setFont(font_bold)
        self.table.setItem(row_idx, 1, it_name)

        # 2: 所属强板块
        it_sec = NumericTableWidgetItem(sec, is_pinned=is_fav, pin_rank=pin_rank)
        it_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sec.setForeground(QBrush(QColor("#ffbb55")))
        if is_fav:
            it_sec.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 2, it_sec)

        # 3: 买点类型 (支持加速结构详细透视 ToolTip)
        accel_t = str(r.get("accel_tag", ""))
        open_v = _safe_float(r.get("open", 0.0))
        low_v = _safe_float(r.get("low", 0.0))
        lc_v = _safe_float(r.get("last_close", 0.0))
        diff_v = _safe_float(r.get("low_diff_pct", 0.0))
        jump_v = _safe_float(r.get("open_jump_pct", 0.0))
        type_tip = f"【买点分析】: {buy_type}\n" \
                   f"• 👑 加速结构: {accel_t if accel_t else '常规波动'}\n" \
                   f"• 📊 盘口开低跳空: 开{open_v:.2f} | 低{low_v:.2f} (下影差异: {diff_v:.2f}%) | 昨收{lc_v:.2f} (跳空幅度: {jump_v:+.2f}%)\n" \
                   f"• 🎯 决策依据: {reason}"
        it_type = NumericTableWidgetItem(buy_type, is_pinned=is_fav, pin_rank=pin_rank)
        it_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_type.setForeground(QBrush(type_color))
        it_type.setBackground(QBrush(type_bg))
        it_type.setFont(font_bold)
        it_type.setToolTip(type_tip)
        self.table.setItem(row_idx, 3, it_type)

        # 4: 现价
        it_p = NumericTableWidgetItem(f"{price:.2f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_p.setForeground(QBrush(pct_color))
        if is_fav:
            it_p.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 4, it_p)

        # 5: 涨幅%
        it_pct = NumericTableWidgetItem(f"{pct:+.2f}%", is_pinned=is_fav, pin_rank=pin_rank)
        it_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_pct.setForeground(QBrush(pct_color))
        it_pct.setFont(font_bold)
        if is_fav:
            it_pct.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 5, it_pct)

        # 6: 交易分段涨速% (支持 30分/15分/60分/开盘累计，多级业务阈值状态)
        if vel_pct >= 2.0:
            vel_str = f"🚀+{vel_pct:.1f}%"
            vel_color = QColor("#ff2244")
        elif vel_pct >= 0.8:
            vel_str = f"🔥+{vel_pct:.1f}%"
            vel_color = QColor("#ff5533")
        elif vel_pct >= 0.3:
            vel_str = f"⚡+{vel_pct:.1f}%"
            vel_color = QColor("#ffaa33")
        elif vel_pct <= -1.5:
            vel_str = f"❄️{vel_pct:.1f}%"
            vel_color = QColor("#00ff88")
        elif vel_pct <= -0.8:
            vel_str = f"⚠️{vel_pct:.1f}%"
            vel_color = QColor("#00ddbb")
        elif vel_pct <= -0.3:
            vel_str = f"🔻{vel_pct:.1f}%"
            vel_color = QColor("#00bbcc")
        else:
            vel_str = "0.0%"
            vel_color = QColor("#888899")

        it_vel = NumericTableWidgetItem(vel_str, is_pinned=is_fav, pin_rank=pin_rank)
        it_vel.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_vel.setForeground(QBrush(vel_color))
        if is_fav:
            it_vel.setBackground(QBrush(fav_bg))
        
        tip_lines = [
            f"【交易分段】: {seg_label}",
            f"【时段基准价】: {seg_base_p:.2f} {'(盘中启动初测第一笔)' if is_midway else '(开盘/时段基准)'}",
            f"【当前价格】: {price:.2f}",
            f"【时段净拉升】: {vel_pct:+.2f}%",
            f"【时段增量额】: {seg_amt_wan:.1f} 万元",
            f"【状态评估】: {vel_tag}",
            f"说明: 自动记忆每个交易时段个股首笔数据为基线进行净拉升统计"
        ]
        it_vel.setToolTip("\n".join(tip_lines))
        self.table.setItem(row_idx, 6, it_vel)

        # 7: 换手%
        turn_str = f"{turnover:.2f}%" if turnover > 0 else "--"
        it_turn = NumericTableWidgetItem(turn_str, is_pinned=is_fav, pin_rank=pin_rank)
        it_turn.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_turn.setForeground(QBrush(QColor("#ffe066" if turnover >= 5.0 else "#c0c0d0")))
        if is_fav:
            it_turn.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 7, it_turn)

        # 8: 量比
        it_vr = NumericTableWidgetItem(f"{vol_r:.2f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_vr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vr_color = QColor("#ff4466") if vol_r >= 2.5 else (QColor("#ffaa44") if vol_r >= 1.5 else QColor("#e2e2e5"))
        it_vr.setForeground(QBrush(vr_color))
        if is_fav:
            it_vr.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 8, it_vr)

        # 9: 盘口意图
        it_intent = NumericTableWidgetItem(intent, is_pinned=is_fav, pin_rank=pin_rank)
        it_intent.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if "扫买" in intent or "抢筹" in intent:
            it_intent.setForeground(QBrush(QColor("#ff3355")))
            it_intent.setBackground(QBrush(QColor(60, 20, 25, 160)))
            it_intent.setFont(font_bold)
        elif "托底" in intent:
            it_intent.setForeground(QBrush(QColor("#00ffbb")))
            it_intent.setBackground(QBrush(QColor(10, 45, 35, 160)))
        elif "砸盘" in intent or "压盘" in intent:
            it_intent.setForeground(QBrush(QColor("#55ddff")))
            it_intent.setBackground(QBrush(QColor(20, 30, 50, 160)))
        else:
            it_intent.setForeground(QBrush(QColor("#aaaaaa")))
            if is_fav:
                it_intent.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 9, it_intent)

        # 10: 分时攻角
        it_sl = NumericTableWidgetItem(f"{slope:.0f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_sl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_sl.setForeground(QBrush(QColor("#00ffcc") if slope >= 60 else QColor("#aaaaaa")))
        if is_fav:
            it_sl.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 10, it_sl)

        # 11: VWAP偏离
        it_dev = NumericTableWidgetItem(f"{vwap_dev:+.1f}%", is_pinned=is_fav, pin_rank=pin_rank)
        it_dev.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dev_color = QColor("#ff88aa") if vwap_dev > 0 else QColor("#66aacc")
        it_dev.setForeground(QBrush(dev_color))
        if is_fav:
            it_dev.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 11, it_dev)

        # 12: DFF (多日偏离度)
        it_dff = NumericTableWidgetItem(f"{dff:+.2f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_dff.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_dff.setForeground(QBrush(QColor(COLOR_UP if dff > 0 else COLOR_DOWN)))
        if is_fav:
            it_dff.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 12, it_dff)

        # 13: Rank (强度排位，支持全市场 1~9999 真实排位)
        rank_int = _safe_int(rank_val, 0)
        rank_str = str(rank_int) if rank_int > 0 else "--"
        it_rank = NumericTableWidgetItem(rank_str, is_pinned=is_fav, pin_rank=pin_rank)
        it_rank.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_rank.setForeground(QBrush(QColor("#FFD700" if (0 < rank_int < 500) else "#e2e2e5")))
        if is_fav:
            it_rank.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 13, it_rank)

        # 14: DFF2 (2日加速)
        it_d2 = NumericTableWidgetItem(f"{dff2:+.2f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_d2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_d2.setForeground(QBrush(QColor(COLOR_UP if dff2 > 0 else COLOR_DOWN)))
        if is_fav:
            it_d2.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 14, it_d2)

        # 15: DFF3 (3日加速)
        it_d3 = NumericTableWidgetItem(f"{dff3:+.2f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_d3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_d3.setForeground(QBrush(QColor(COLOR_UP if dff3 > 0 else COLOR_DOWN)))
        if is_fav:
            it_d3.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, 15, it_d3)

        # 填入动态自定义扩展列 (extra_cols，从列 16 开始)
        col_offset = 16
        for ec in self.extra_cols:
            ec_val = extra_vals.get(ec, "--")
            it_ec = NumericTableWidgetItem(str(ec_val), is_pinned=is_fav, pin_rank=pin_rank)
            it_ec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_ec.setForeground(QBrush(QColor("#E0E0E0")))
            if is_fav:
                it_ec.setBackground(QBrush(fav_bg))
            self.table.setItem(row_idx, col_offset, it_ec)
            col_offset += 1

        # 建议买入区间
        it_bz = NumericTableWidgetItem(buy_zone, is_pinned=is_fav, pin_rank=pin_rank)
        it_bz.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_bz.setForeground(QBrush(QColor("#00ffaa")))
        it_bz.setFont(font_bold)
        if is_fav:
            it_bz.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, col_offset, it_bz)

        # 止损防守位
        it_sloss = NumericTableWidgetItem(f"{stop_loss:.2f}" if isinstance(stop_loss, (int, float)) else str(stop_loss), is_pinned=is_fav, pin_rank=pin_rank)
        it_sloss.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_sloss.setForeground(QBrush(QColor("#ffaa66")))
        if is_fav:
            it_sloss.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, col_offset + 1, it_sloss)

        # 综合得分
        it_score = NumericTableWidgetItem(f"{alpha_score:.1f}", is_pinned=is_fav, pin_rank=pin_rank)
        it_score.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_score.setForeground(QBrush(QColor("#ffd700")))
        it_score.setFont(font_bold)
        if is_fav:
            it_score.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, col_offset + 2, it_score)

        # 决策依据
        it_rs = NumericTableWidgetItem(reason, is_pinned=is_fav, pin_rank=pin_rank)
        it_rs.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        it_rs.setForeground(QBrush(QColor("#cccccc")))
        if is_fav:
            it_rs.setBackground(QBrush(fav_bg))
        self.table.setItem(row_idx, col_offset + 3, it_rs)

    def _on_item_clicked(self, item):
        if item:
            self._link_current_row(item.row())

    def _on_current_item_changed(self, current, previous):
        if current:
            self._link_current_row(current.row())

    def _link_current_row(self, row: int):
        if getattr(self, '_is_updating', False) or getattr(self, '_is_auto_popping', False):
            return
        if row < 0 or row >= self.table.rowCount():
            return
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if c_item:
            code = c_item.text().strip()
            name = n_item.text().strip() if n_item else code
            self.code_clicked.emit(code, name)
            # 联动主窗口（分时图、K线与外部行情联动）
            main_win = self._get_parent_mw()
            if main_win and hasattr(main_win, "link_stock"):
                try:
                    main_win.link_stock(code, name)
                except Exception as e:
                    logger.debug(f"link_stock error: {e}")

    def _on_item_double_clicked(self, item):
        if not item:
            return
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if c_item:
            code = c_item.text().strip()
            name = n_item.text().strip() if n_item else code
            main_win = self._get_parent_mw()
            if main_win and hasattr(main_win, "on_stock_clicked"):
                try:
                    main_win.on_stock_clicked(code, name)
                except Exception as e:
                    logger.debug(f"on_stock_clicked error: {e}")

    def keyPressEvent(self, event):
        from ats.ui.styles import is_editing_text
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            if not is_editing_text(self):
                if hasattr(self, 'chk_on_top'):
                    self.chk_on_top.toggle()
                    event.accept()
                    return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            super().keyPressEvent(event)
            curr_row = self.table.currentRow()
            if curr_row >= 0:
                self._link_current_row(curr_row)
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            curr_row = self.table.currentRow()
            if curr_row >= 0:
                c_item = self.table.item(curr_row, 0)
                if c_item:
                    self._on_item_double_clicked(c_item)
            return
        elif key == Qt.Key.Key_Escape:
            if self.anchor_edge:
                self.hide_to_edge()
            else:
                self.close()
            return
        super().keyPressEvent(event)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        c_item = self.table.item(row, 0)
        n_item = self.table.item(row, 1)
        if not c_item:
            return

        code = c_item.text().strip()
        name = n_item.text().strip() if n_item else code
        code_clean = str(code).strip().zfill(6)
        clean_name = name.replace("⭐ ", "").replace("★ ", "").strip()

        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        is_fav = code_clean in fav_mgr.get_favorite_stocks()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1d28; color: #ffffff; border: 1px solid #2e354f; padding: 4px; }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: #2c3554; color: #00ffaa; }
        """)

        # 1. 重点关注切换操作 (优先显示/取消优先)
        if is_fav:
            act_fav = menu.addAction(f"❌ 取消重点关注 ({code_clean})")
        else:
            act_fav = menu.addAction(f"⭐ 设为重点关注 ({code_clean})")

        def _toggle_fav():
            fav_mgr.toggle_favorite_stock(code_clean)
            main_win = self._get_parent_mw()
            if main_win and hasattr(main_win, '_safe_favorites_changed'):
                try:
                    main_win._safe_favorites_changed()
                except Exception:
                    pass
            # 立即触发表格重新渲染以更新重点关注置顶与金色高亮
            self._render_table_data(self.cached_results)

        act_fav.triggered.connect(_toggle_fav)
        menu.addSeparator()

        # 2. 行情联动与分时图
        act_link = menu.addAction(f"📊 联动查看 {clean_name} ({code_clean}) 分时K线")
        act_link.triggered.connect(lambda: self._on_item_clicked(c_item))

        act_sbc = menu.addAction(f"📈 使用 SBC 打开独立分时图 ({code_clean})")
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code_clean)
        act_sbc.triggered.connect(_open_sbc)

        act_send = menu.addAction(f"⚡ 发送到异动联动 ({code_clean})")
        def _send_link():
            from ats.ui.base_table import send_to_linkage
            send_to_linkage(code_clean, clean_name, self)
        act_send.triggered.connect(_send_link)

        act_strategy = menu.addAction(f"🎯 调出 {clean_name} 分时阶梯交易策略")
        act_strategy.triggered.connect(lambda: self._on_item_double_clicked(c_item))

        # 3. 复制操作
        menu.addSeparator()
        act_copy_code = menu.addAction(f"📋 复制代码 {code_clean}")
        act_copy_code.triggered.connect(lambda: QApplication.clipboard().setText(code_clean))
        act_copy_name = menu.addAction(f"📋 复制名称 {clean_name}")
        act_copy_name.triggered.connect(lambda: QApplication.clipboard().setText(clean_name))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── 磁吸边缘贴边与 Hover 动画支持 ──
    def start_slide_animation(self, target_rect, target_opacity, duration=250, is_snap_feedback=False):
        if hasattr(self, 'anim_group') and self.anim_group is not None:
            try:
                if self.anim_group.state() == QParallelAnimationGroup.State.Running:
                    self.anim_group.stop()
            except Exception:
                pass

        self.anim_group = QParallelAnimationGroup(self)
        self.geom_anim = QPropertyAnimation(self, b"geometry")
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_rect)
        if is_snap_feedback:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(target_opacity)
        if is_snap_feedback:
            self.opacity_anim.setKeyValueAt(0.5, 0.4)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)

        self._in_snap_action = True

        def on_finished():
            self._in_snap_action = False
            if self.is_hidden_state:
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(1.0)
            self._save_window_states(is_open=True)

        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        # 【置顶与磁吸严格互斥】：置顶状态下完全禁用磁吸贴边功能，保持自由悬浮置顶
        if self.stays_on_top or self.is_hidden_state:
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start(300)
            return

        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 20 # 调优为更自然的 20px 阈值，避免误吸

        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()

        if abs(win_geo.top() - screen_geo.top()) < margin:
            edge = "top"
            target_y = screen_geo.top()
            snapped = True
        elif abs(win_geo.left() - screen_geo.left()) < margin:
            edge = "left"
            target_x = screen_geo.left()
            snapped = True
        elif abs(win_geo.right() - screen_geo.right()) < margin:
            edge = "right"
            target_x = screen_geo.right() - win_geo.width()
            snapped = True

        self._is_dragging = False
        if snapped:
            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            self.start_slide_animation(self.normal_geometry, 1.0, duration=200, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None
            self._save_window_states(is_open=True)

    def hide_to_edge(self):
        if self.stays_on_top or not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
            return

        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()

        w = self.normal_geometry.width()
        h = self.normal_geometry.height()
        x = self.normal_geometry.x()
        y = self.normal_geometry.y()
        strip_size = 5

        if self.anchor_edge == "left":
            target_x = screen_geo.left() - w + strip_size
            target_y = y
        elif self.anchor_edge == "right":
            target_x = screen_geo.right() - strip_size
            target_y = y
        elif self.anchor_edge == "top":
            target_x = x
            target_y = screen_geo.top() - h + strip_size
        else:
            return

        self.is_hidden_state = True
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=300)

    def show_normal_position(self):
        if self.is_hidden_state:
            self.is_hidden_state = False
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            self._last_show_time = time.time()
            self._has_hovered_since_show = False
            if self.normal_geometry:
                self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
            self.setWindowOpacity(1.0)
        else:
            self.setWindowOpacity(1.0)

        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        self._save_window_states(is_open=True)

    def _check_hover(self):
        if not self.isVisible() or self.stays_on_top:
            return

        # 仅在有贴边锚定边缘或处于贴边隐藏状态时才执行悬浮检测，其余时刻 0 开销
        if not self.anchor_edge and not self.is_hidden_state:
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return

        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        in_window = self.frameGeometry().contains(mouse_pos)

        if in_window:
            self._has_hovered_since_show = True

        if self.is_hidden_state:
            if in_window:
                self.hover_ticks += 1
                if self.hover_ticks >= 2:
                    self.show_normal_position()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0
        else:
            if self.anchor_edge is not None:
                if not in_window:
                    if not getattr(self, '_has_hovered_since_show', False):
                        self.leave_ticks = 0
                        return
                    if time.time() - getattr(self, '_last_show_time', 0.0) < 1.2:
                        self.leave_ticks = 0
                        return

                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.stays_on_top:
            self.snap_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            return
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            self.anchor_edge = None
            self.snap_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

    def closeEvent(self, event):
        self.hover_timer.stop()
        self.snap_timer.stop()
        main_app = self._get_parent_mw()
        is_app_exiting = False
        if main_app:
            if not main_app.isVisible() or getattr(main_app, '_is_closing', False) or getattr(main_app, '_is_exiting', False):
                is_app_exiting = True

        if is_app_exiting or getattr(self, 'is_hidden_state', False):
            self._save_window_states(is_open=True)
        else:
            self._save_window_states(is_open=False)
        event.accept()

    def hideEvent(self, event):
        main_app = self._get_parent_mw()
        is_app_exiting = False
        if main_app:
            if not main_app.isVisible() or getattr(main_app, '_is_closing', False) or getattr(main_app, '_is_exiting', False):
                is_app_exiting = True

        if is_app_exiting or getattr(self, 'is_hidden_state', False):
            self._save_window_states(is_open=True)
        else:
            self._save_window_states(is_open=False)
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.layout():
            self.layout().activate()
        self._save_window_states(is_open=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()

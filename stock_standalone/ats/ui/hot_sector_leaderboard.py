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
    apply_dark_theme
)
from ats.ui.favorite_panel import get_ats_extra_cols
from ats.hot_sector_engine import HotSectorEngine
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()


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


class HotSectorLeaderboardDialog(QDialog, WindowMixin):
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
        self.setMinimumWidth(880)
        self.setMinimumHeight(460)
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
        self.snap_timer.setInterval(200)
        self.snap_timer.timeout.connect(self._detect_and_snap)

        # 1. 窗口置顶与外观
        self.stays_on_top = self._load_stays_on_top()
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags &= ~Qt.WindowType.Tool
        flags |= Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
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
                self.anchor_edge = restore_state.get("anchor_edge")
                self.setGeometry(rx, ry, rw, rh)
            except Exception as e:
                logger.warning(f"恢复窗口位置异常: {e}")
                self.load_window_position_qt(self, "hot_sector_leaderboard_dialog", default_width=1080, default_height=560)
        else:
            self.load_window_position_qt(self, "hot_sector_leaderboard_dialog", default_width=1080, default_height=560)

        # 3. 状态与引擎
        self.engine = HotSectorEngine.get_instance()
        self.filter_mode = "ALL" # ALL / LEADER_BREAKOUT / PULLBACK
        self.cached_results: List[Dict[str, Any]] = []
        self.current_top_sectors: List[str] = []
        self.active_sectors: set = set() # 当前激活/选中的板块集合
        self._has_init_fetched: bool = False # 记录是否已完成非交易时段初次初始化
        self.tdx_log_dialog: Optional[TDXFetchLogDialog] = None # 独立日志弹窗引用

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
        header_lay.setContentsMargins(8, 4, 8, 4)
        header_lay.setSpacing(8)

        # 全选 / 全部板块按钮
        self.btn_top_all = QPushButton("🔥 全部板块")
        self.btn_top_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_top_all.setToolTip("点击重置并显示所有 Top 3 强势板块标的")
        self.btn_top_all.setStyleSheet("""
            QPushButton { background-color: #1a2a3a; color: #00FFCC; border: 1px solid #00FFCC; border-radius: 3px; font-weight: bold; font-size: 9.5pt; padding: 3px 8px; }
            QPushButton:hover { background-color: #00FFCC; color: #000000; }
        """)
        self.btn_top_all.clicked.connect(self._on_all_sectors_clicked)
        header_lay.addWidget(self.btn_top_all)

        # Top 3 板块可点击切换按钮容器
        self.sec_tags_layout = QHBoxLayout()
        self.sec_tags_layout.setSpacing(6)

        self.btn_sec1 = QPushButton("🔥 No.1 --")
        self.btn_sec1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec1.setToolTip("点击开启/关闭该板块显示过滤")
        self.btn_sec1.clicked.connect(lambda: self._toggle_sector_filter(0))

        self.btn_sec2 = QPushButton("🔥 No.2 --")
        self.btn_sec2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec2.setToolTip("点击开启/关闭该板块显示过滤")
        self.btn_sec2.clicked.connect(lambda: self._toggle_sector_filter(1))

        self.btn_sec3 = QPushButton("🔥 No.3 --")
        self.btn_sec3.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sec3.setToolTip("点击开启/关闭该板块显示过滤")
        self.btn_sec3.clicked.connect(lambda: self._toggle_sector_filter(2))

        self.sec_buttons = [self.btn_sec1, self.btn_sec2, self.btn_sec3]
        for btn in self.sec_buttons:
            self.sec_tags_layout.addWidget(btn)
        
        header_lay.addLayout(self.sec_tags_layout)
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
                padding: 2px 8px; 
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
        self.combo_time_slice.setMinimumWidth(185)
        self.combo_time_slice.setStyleSheet("""
            QComboBox { background-color: #241e12; color: #ffd700; border: 1px solid #ffaa00; border-radius: 3px; padding: 2px 6px; font-weight: bold; font-size: 9pt; min-width: 180px; }
            QComboBox::drop-down { width: 18px; }
            QComboBox QAbstractItemView { background-color: #1e1e24; color: #ffd700; selection-background-color: #3d3014; }
        """)
        self.combo_time_slice.currentIndexChanged.connect(lambda: self._render_table_data(self.cached_results))
        header_lay.addWidget(self.combo_time_slice)

        # 筛选下拉框 (支持盘中极度聚焦与买点分拣)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems([
            "🔥 全部跟单标的", 
            "⭐ 核心聚焦 (Top 5)", 
            "👑 仅看领涨龙头", 
            "🚀 仅看先锋突破", 
            "💎 仅看反身低吸", 
            "⚡ 仅看扫盘冲板"
        ])
        self.combo_filter.setStyleSheet("""
            QComboBox { background-color: #1c1c22; color: #00ffaa; border: 1px solid #3e3e4a; border-radius: 3px; padding: 2px 6px; font-size: 9pt; font-weight: bold; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #18181c; color: #ffffff; selection-background-color: #2e3b4e; }
        """)
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        header_lay.addWidget(self.combo_filter)

        # 置顶复选框
        self.chk_on_top = QCheckBox("置顶")
        self.chk_on_top.setStyleSheet("QCheckBox { color: #00FFCC; font-size: 9pt; font-weight: bold; }")
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.stateChanged.connect(self._on_stays_on_top_toggled)
        header_lay.addWidget(self.chk_on_top)

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
        flags = self.windowFlags()
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            # 【置顶与磁吸互斥】：开启置顶时，立即退出磁吸并恢复正常窗口显示
            if self.is_hidden_state:
                self.show_normal_position()
            self.anchor_edge = None
            self.normal_geometry = None
            self.snap_timer.stop()
            self.hover_ticks = 0
            self.leave_ticks = 0
            self.setWindowOpacity(1.0)
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self._save_window_states()

    def _save_window_states(self, is_open=None) -> None:
        try:
            scale = self._get_dpi_scale_factor()
            geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
            width = max(200, int(geom.width() / scale))
            height = max(150, int(geom.height() / scale))
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
                "anchor_edge": self.anchor_edge,
                "is_hidden_state": self.is_hidden_state,
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
        """点击【全部板块】：一键全选并激活所有当前 Top 3 强势板块"""
        self.active_sectors = set(self.current_top_sectors)
        self._update_sector_button_styles()
        self._render_table_data(self.cached_results)

    def _toggle_sector_filter(self, sec_idx: int):
        """点击单个板块按钮：切换其开/关显示状态"""
        if sec_idx >= len(self.current_top_sectors):
            return
        sec_name = self.current_top_sectors[sec_idx]
        if sec_name in self.active_sectors:
            # 已开启 -> 关闭
            self.active_sectors.remove(sec_name)
        else:
            # 已关闭 -> 开启
            self.active_sectors.add(sec_name)

        # 如果全部关闭了，则自动重置为全部开启，避免完全空白
        if not self.active_sectors:
            self.active_sectors = set(self.current_top_sectors)

        self._update_sector_button_styles()
        self._render_table_data(self.cached_results)

    def _update_sector_button_styles(self):
        """刷新顶部 3 个板块按钮的高亮/置灰状态"""
        color_themes = [
            ("#2a1b1b", "#ff5577", "#ff4466"), # No.1 红色系
            ("#2a221b", "#ffaa44", "#ff9933"), # No.2 橙色系
            ("#1b262a", "#44ddff", "#33bbdd"), # No.3 青色系
        ]
        
        all_active = (set(self.current_top_sectors) <= self.active_sectors) and len(self.current_top_sectors) > 0
        if all_active:
            self.btn_top_all.setStyleSheet("""
                QPushButton { background-color: #1a2a3a; color: #00FFCC; border: 1px solid #00FFCC; border-radius: 3px; font-weight: bold; font-size: 9.5pt; padding: 3px 8px; }
                QPushButton:hover { background-color: #00FFCC; color: #000000; }
            """)
        else:
            self.btn_top_all.setStyleSheet("""
                QPushButton { background-color: #141720; color: #778899; border: 1px solid #24293e; border-radius: 3px; font-weight: bold; font-size: 9.5pt; padding: 3px 8px; }
                QPushButton:hover { background-color: #00FFCC; color: #000000; }
            """)

        for i, btn in enumerate(self.sec_buttons):
            if i < len(self.current_top_sectors):
                sname = self.current_top_sectors[i]
                btn.setText(f"🔥 No.{i+1} {sname}")
                btn.setVisible(True)

                is_active = (sname in self.active_sectors)
                bg, fg, border = color_themes[i] if i < len(color_themes) else ("#181b26", "#ffffff", "#334466")
                
                if is_active:
                    btn.setStyleSheet(f"""
                        QPushButton {{ background-color: {bg}; color: {fg}; border: 1px solid {border}; border-radius: 3px; padding: 2px 7px; font-weight: bold; font-size: 9pt; }}
                        QPushButton:hover {{ background-color: {border}; color: #ffffff; }}
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton { background-color: #14161f; color: #555566; border: 1px solid #222533; border-radius: 3px; padding: 2px 7px; font-size: 9pt; }
                        QPushButton:hover { background-color: #1f2333; color: #888899; }
                    """)
            else:
                btn.setVisible(False)

    def _on_filter_changed(self, idx):
        if idx == 1:
            self.filter_mode = "TOP5_FOCUS" # ⭐ 核心聚焦 (Top 5)
        elif idx == 2:
            self.filter_mode = "LEADER"     # 👑 仅看领涨龙头
        elif idx == 3:
            self.filter_mode = "BREAKOUT"   # 🚀 仅看先锋突破
        elif idx == 4:
            self.filter_mode = "PULLBACK"   # 💎 仅看反身低吸
        elif idx == 5:
            self.filter_mode = "SURGE"      # ⚡ 仅看扫盘冲板
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
        if self._is_updating:
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

            # 尝试从热力图组件提取 Top 3 板块
            if hasattr(main_app, "heatmap_widget") and main_app.heatmap_widget:
                hw = main_app.heatmap_widget
                if hasattr(hw, "sectors") and hw.sectors:
                    sec_to_codes = getattr(hw, "sector_to_codes", {})
                    top_sectors = self.engine.extract_top_sectors_from_heatmap(hw.sectors, sec_to_codes, top_n=3)

            # 尝试从自选面板提取重点关注池
            if hasattr(main_app, "fav_stocks") and main_app.fav_stocks:
                manual_list = list(main_app.fav_stocks)

        # 降级默认板块
        if not top_sectors:
            top_sectors = ["共封装光学(CPO)", "国家大基金持股", "存储芯片"]

        # 板块变化或初次加载时初始化 active_sectors
        if self.current_top_sectors != top_sectors:
            self.current_top_sectors = list(top_sectors)
            # 如果先前未设置或者刚启动，默认全选开启
            if not self.active_sectors or not (self.active_sectors & set(top_sectors)):
                self.active_sectors = set(top_sectors)
            self._update_sector_button_styles()

        # 计算并返回最新 Alpha 列表
        try:
            if not is_trading:
                fetcher.add_log(f"非交易时段初始化/单次手动刷新 ({session_desc})", level="SLEEP")
            results = self.engine.compute_hot_alpha_leaderboard(
                top_sector_names=top_sectors,
                current_df=current_df,
                manual_watchlist=manual_list
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

        filtered = []
        for r in results:
            sec = r.get("sector", "")
            # 板块标签开关过滤
            if self.active_sectors and sec not in self.active_sectors and sec != "重点关注":
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
            else:
                filtered.append(r)

        if getattr(self, "filter_mode", "ALL") == "TOP5_FOCUS":
            filtered.sort(key=lambda x: x.get("alpha_score", 0.0), reverse=True)
            filtered = filtered[:5]

        # 3. 原地填充表格
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        if self.table.rowCount() != len(filtered):
            self.table.setRowCount(len(filtered))

        font_bold = QFont()
        font_bold.setBold(True)

        for row_idx, r in enumerate(filtered):
            self._populate_row(row_idx, r, font_bold)

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
        leader_cnt = sum(1 for x in filtered if x.get("buy_tag") == "LEADER")
        surge_cnt = sum(1 for x in filtered if x.get("buy_tag") == "SURGE")
        breakout_cnt = sum(1 for x in filtered if x.get("buy_tag") == "BREAKOUT")
        pullback_cnt = sum(1 for x in filtered if x.get("buy_tag") == "PULLBACK")

        self.lbl_stats.setText(f"标的: {total_cnt} | 👑龙头: {leader_cnt} | ⚡扫盘: {surge_cnt} | 🚀先锋: {breakout_cnt} | 💎回踩: {pullback_cnt}")

        # 找出各板块内涨幅最高的领跑股
        sec_leaders = {}
        for x in filtered:
            s = x.get("sector", "")
            if not s or s == "重点关注":
                continue
            if s not in sec_leaders or x.get("pct", -999) > sec_leaders[s].get("pct", -999):
                sec_leaders[s] = x

        leader_strs = []
        for s in self.current_top_sectors:
            if s in sec_leaders:
                lead_stock = sec_leaders[s]
                s_short = s.split('(')[0] if '(' in s else s
                leader_strs.append(f"{s_short}: {lead_stock['name']}({lead_stock['pct']:+.2f}%)")

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
                break

    def _check_and_notify_sector_highlights(self, filtered_records: List[Dict[str, Any]]):
        """【板块龙头与特异异动自动挖掘通知】"""
        if not getattr(self, "is_voice_alert_enabled", True):
            return

        try:
            from ats.alert_notifier import AlertNotifier
            notifier = AlertNotifier.get_instance()
        except Exception:
            return

        if not filtered_records:
            return

        # 筛选得分最高的 3~5 只核心领涨龙头与先锋突破标的
        candidates = []
        for r in filtered_records:
            score = float(r.get("alpha_score", 0.0))
            tag = r.get("buy_tag", "")
            if score >= 85.0 and tag in ("LEADER", "SURGE", "BREAKOUT", "PULLBACK"):
                candidates.append(r)
            if len(candidates) >= 5: # 精选 3~5 个
                break

        for idx, top_cand in enumerate(candidates, 1):
            c = str(top_cand.get("code", "")).zfill(6)
            n = str(top_cand.get("name", c))
            score = float(top_cand.get("alpha_score", 88.0))
            buy_type = str(top_cand.get("buy_type", ""))
            sec = str(top_cand.get("sector", ""))
            reason = f"【{sec}精选#{idx}】{buy_type} | {top_cand.get('reason', '')}"
            notifier.notify_special_signal(code=c, name=n, reason=reason, score=score, parent=self)

    def _populate_row(self, row_idx: int, r: Dict[str, Any], font_bold: QFont):
        """填充/原位更新单行数据"""
        code = r["code"]
        name = r["name"]
        sec = r["sector"]
        buy_type = r["buy_type"]
        buy_tag = r["buy_tag"]
        price = r["price"]
        pct = r["pct"]
        vel_pct = r.get("velocity_pct", 0.0)
        turnover = r.get("turnover", 0.0)
        vol_r = r.get("vol_ratio", 1.0)
        intent = r.get("order_intent", "⚖️ 均衡博弈")
        slope = r["slope_score"]
        vwap_dev = r["vwap_dev_pct"]
        dff = r.get("dff", 0.0)
        rank_val = r.get("rank", 999)
        dff2 = r.get("dff2", 0.0)
        dff3 = r.get("dff3", 0.0)
        extra_vals = r.get("extra_vals", {})
        buy_zone = r["buy_zone"]
        stop_loss = r["stop_loss"]
        alpha_score = r["alpha_score"]
        reason = r["reason"]

        pct_color = QColor("#ff4455") if pct > 0 else (QColor("#00ee77") if pct < 0 else QColor("#cccccc"))
        
        # 买点类型专属精细化视觉高亮
        if buy_tag == "LEADER":
            type_color = QColor("#FF3399") # 亮洋红领涨龙头
            type_bg = QColor(65, 20, 45, 160)
        elif buy_tag == "SURGE":
            type_color = QColor("#FF5533") # 亮橙红扫盘冲板
            type_bg = QColor(65, 30, 20, 160)
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
        it_code = NumericTableWidgetItem(code)
        it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_code.setForeground(QBrush(QColor("#aad4ff")))
        self.table.setItem(row_idx, 0, it_code)

        # 1: 名称
        it_name = NumericTableWidgetItem(name)
        it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_name.setForeground(QBrush(QColor("#ffffff")))
        it_name.setFont(font_bold)
        self.table.setItem(row_idx, 1, it_name)

        # 2: 所属强板块
        it_sec = NumericTableWidgetItem(sec)
        it_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_sec.setForeground(QBrush(QColor("#ffbb55")))
        self.table.setItem(row_idx, 2, it_sec)

        # 3: 买点类型
        it_type = NumericTableWidgetItem(buy_type)
        it_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_type.setForeground(QBrush(type_color))
        it_type.setBackground(QBrush(type_bg))
        it_type.setFont(font_bold)
        self.table.setItem(row_idx, 3, it_type)

        # 4: 现价
        it_p = NumericTableWidgetItem(f"{price:.2f}")
        it_p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_p.setForeground(QBrush(pct_color))
        self.table.setItem(row_idx, 4, it_p)

        # 5: 涨幅%
        it_pct = NumericTableWidgetItem(f"{pct:+.2f}%")
        it_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_pct.setForeground(QBrush(pct_color))
        it_pct.setFont(font_bold)
        self.table.setItem(row_idx, 5, it_pct)

        # 6: 涨速%
        if vel_pct > 0.8:
            vel_str = f"🔥+{vel_pct:.1f}%"
            vel_color = QColor("#ff3344")
        elif vel_pct > 0.1:
            vel_str = f"⚡+{vel_pct:.1f}%"
            vel_color = QColor("#ff8844")
        elif vel_pct < -0.8:
            vel_str = f"❄️{vel_pct:.1f}%"
            vel_color = QColor("#00ff88")
        elif vel_pct < -0.1:
            vel_str = f"🔻{vel_pct:.1f}%"
            vel_color = QColor("#00ddcc")
        else:
            vel_str = "0.0%"
            vel_color = QColor("#888899")

        it_vel = NumericTableWidgetItem(vel_str)
        it_vel.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_vel.setForeground(QBrush(vel_color))
        self.table.setItem(row_idx, 6, it_vel)

        # 7: 换手%
        turn_str = f"{turnover:.2f}%" if turnover > 0 else "--"
        it_turn = NumericTableWidgetItem(turn_str)
        it_turn.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_turn.setForeground(QBrush(QColor("#ffe066" if turnover >= 5.0 else "#c0c0d0")))
        self.table.setItem(row_idx, 7, it_turn)

        # 8: 量比
        it_vr = NumericTableWidgetItem(f"{vol_r:.2f}")
        it_vr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        vr_color = QColor("#ff4466") if vol_r >= 2.5 else (QColor("#ffaa44") if vol_r >= 1.5 else QColor("#e2e2e5"))
        it_vr.setForeground(QBrush(vr_color))
        self.table.setItem(row_idx, 8, it_vr)

        # 9: 盘口意图
        it_intent = NumericTableWidgetItem(intent)
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
        self.table.setItem(row_idx, 9, it_intent)

        # 10: 分时攻角
        it_sl = NumericTableWidgetItem(f"{slope:.0f}")
        it_sl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_sl.setForeground(QBrush(QColor("#00ffcc") if slope >= 60 else QColor("#aaaaaa")))
        self.table.setItem(row_idx, 10, it_sl)

        # 11: VWAP偏离
        it_dev = NumericTableWidgetItem(f"{vwap_dev:+.1f}%")
        it_dev.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dev_color = QColor("#ff88aa") if vwap_dev > 0 else QColor("#66aacc")
        it_dev.setForeground(QBrush(dev_color))
        self.table.setItem(row_idx, 11, it_dev)

        # 12: DFF (多日偏离度)
        it_dff = NumericTableWidgetItem(f"{dff:+.2f}")
        it_dff.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_dff.setForeground(QBrush(QColor(COLOR_UP if dff > 0 else COLOR_DOWN)))
        self.table.setItem(row_idx, 12, it_dff)

        # 13: Rank (强度排位)
        rank_str = str(rank_val) if rank_val != 999 else "--"
        it_rank = NumericTableWidgetItem(rank_str)
        it_rank.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_rank.setForeground(QBrush(QColor("#FFD700" if rank_val < 500 else "#e2e2e5")))
        self.table.setItem(row_idx, 13, it_rank)

        # 14: DFF2 (2日加速)
        it_d2 = NumericTableWidgetItem(f"{dff2:+.2f}")
        it_d2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_d2.setForeground(QBrush(QColor(COLOR_UP if dff2 > 0 else COLOR_DOWN)))
        self.table.setItem(row_idx, 14, it_d2)

        # 15: DFF3 (3日加速)
        it_d3 = NumericTableWidgetItem(f"{dff3:+.2f}")
        it_d3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_d3.setForeground(QBrush(QColor(COLOR_UP if dff3 > 0 else COLOR_DOWN)))
        self.table.setItem(row_idx, 15, it_d3)

        # 填入动态自定义扩展列 (extra_cols，从列 16 开始)
        col_offset = 16
        for ec in self.extra_cols:
            ec_val = extra_vals.get(ec, "--")
            it_ec = NumericTableWidgetItem(str(ec_val))
            it_ec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_ec.setForeground(QBrush(QColor("#E0E0E0")))
            self.table.setItem(row_idx, col_offset, it_ec)
            col_offset += 1

        # 建议买入区间
        it_bz = NumericTableWidgetItem(buy_zone)
        it_bz.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_bz.setForeground(QBrush(QColor("#00ffaa")))
        it_bz.setFont(font_bold)
        self.table.setItem(row_idx, col_offset, it_bz)

        # 止损防守位
        it_sloss = NumericTableWidgetItem(f"{stop_loss:.2f}" if isinstance(stop_loss, (int, float)) else str(stop_loss))
        it_sloss.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_sloss.setForeground(QBrush(QColor("#ffaa66")))
        self.table.setItem(row_idx, col_offset + 1, it_sloss)

        # 综合得分
        it_score = NumericTableWidgetItem(f"{alpha_score:.1f}")
        it_score.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it_score.setForeground(QBrush(QColor("#ffd700")))
        it_score.setFont(font_bold)
        self.table.setItem(row_idx, col_offset + 2, it_score)

        # 决策依据
        it_rs = NumericTableWidgetItem(reason)
        it_rs.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        it_rs.setForeground(QBrush(QColor("#cccccc")))
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
        key = event.key()
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

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1d28; color: #ffffff; border: 1px solid #2e354f; padding: 4px; }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: #2c3554; color: #00ffaa; }
        """)

        act_link = menu.addAction(f"📊 联动查看 {name} ({code}) 分时K线")
        act_link.triggered.connect(lambda: self._on_item_clicked(c_item))

        act_sbc = menu.addAction(f"📈 使用 SBC 打开独立分时图 ({code})")
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code)
        act_sbc.triggered.connect(_open_sbc)

        act_send = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        def _send_link():
            from ats.ui.base_table import send_to_linkage
            send_to_linkage(code, name, self)
        act_send.triggered.connect(_send_link)

        act_strategy = menu.addAction(f"🎯 调出 {name} 分时阶梯交易策略")
        act_strategy.triggered.connect(lambda: self._on_item_double_clicked(c_item))

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
            self.snap_timer.start()
            return

        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35

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
            self.start_slide_animation(self.normal_geometry, 1.0, duration=250, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None

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
        if self.layout():
            self.layout().setGeometry(self.rect())
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()

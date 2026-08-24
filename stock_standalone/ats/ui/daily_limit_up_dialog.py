# -*- coding: utf-8 -*-
"""
ats/ui/daily_limit_up_dialog.py — ATS 每日涨停分析与多日强势股天梯看板 (Daily Limit-Up & Momentum Leaderboard)
特点：
1. 【市场核心涨停 KPI 实时大盘看板】：
   - 顶部实时统计当日涨停家数、连板家数、炸板家数、封板率、最高连板高度、平均封流比与封单总额；
2. 【全维封单比与量能比数据呈现】：
   - 买一封单额 (万元/亿元)、封流比 (封单占流通盘比例 %)、封成比 (封单占当日成交量比 %)、买盘压强与封板质量评分；
   - 真实流通换手率 (%)、量比与成交额 (亿元)；
3. 【多日强势股与连板天梯快速切换】：
   - 支持 今日涨停 / 3日强势 / 5日强势 / 10日强势 / 连板天梯 / 历史日期回溯等不同视角的极速切换；
   - 自动统计 N 日 M 板 (如 5日3板、10日6板)、区间累计涨幅与强势梯队；
4. 【跟随 ATS 的 dff 等策略特征与 ats_col 动态自定义列】：
   - 完整继承 ATS 核心指标：dff, dff2, dff3, rank, perc3d, 大盘偏离, 大盘共振；
   - 动态提取与渲染 cct.ats_col 自定义指标列，并支持列宽自适应记忆与数值排序；
5. 【全端联动与极速磁吸】：
   - 具备磁吸边沿吸附、自动贴边隐藏、窗口置顶、平滑动画与位置记忆；
   - 单击联动通达信/同花顺及可视化器，双击调起 SBC 日内分时走势图。
"""

import os
import json
import time
import math
import threading
from typing import Optional, List, Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, 
    QPushButton, QFrame, QMenu, QApplication, QComboBox, QLineEdit, 
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QBrush, QColor, QFont, QAction
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from logger_utils import LoggerFactory
from ats.ui.styles import (
    COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN, 
    auto_fit_columns_once, setup_header_persistence, save_config_node, load_config_node,
    apply_dark_theme, ColorPreservingItemDelegate
)
from ats.ui.favorite_panel import get_ats_extra_cols
from ats.limit_up_engine import LimitUpEngine, get_ats_custom_extra_cols
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()


def _safe_float(val: Any, default: float = 0.0) -> float:
    """健壮的浮点数安全转换函数，杜绝 '-', '--', 'None', NaN, Inf 抛出异常"""
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
    """安全转换为 int"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


def get_limit_up_table_headers(extra_cols=None) -> Tuple[List[str], List[str]]:
    """生成每日涨停与强势股天梯看板的标准表头字段与动态自定义列列表"""
    if extra_cols is None:
        extra_cols = get_ats_custom_extra_cols()
    try:
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}

    base_headers = [
        "代码", "名称", "现价", "涨幅%", "连板数", "梯队分类", "形态与质量",
        "封单额(万)", "封流比%", "封成比%", "换手%", "量比", "成交额(亿)", 
        "DFF", "Rank", "DFF2", "DFF3", "大盘偏离", "共振状态"
    ]
    extra_headers = [col_map.get(c, c) for c in extra_cols]
    tail_headers = ["所属板块"]
    full_headers = base_headers + extra_headers + tail_headers
    return full_headers, extra_cols


class DailyLimitUpDialog(QWidget, WindowMixin):
    """
    每日涨停分析与多日强势股天梯看板独立窗口
    支持磁吸边沿吸附、自动贴边隐藏、独立窗口模式、多日时序分析与全端联动。
    """
    code_clicked = pyqtSignal(str, str) # 单击联动 (code, name)
    code_double_clicked = pyqtSignal(str, str) # 双击查看详情 (code, name)

    def __init__(self, parent=None, restore_state=None):
        super().__init__(None) # 必须为 None，确保是系统级独立窗口，不依附于主窗口层级
        self._py_parent = parent
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("🔥 每日涨停分析与强势股天梯 (Limit-Up & Multi-Day Momentum)")
        self.resize(1280, 720)
        self.setMinimumWidth(360)
        self.setMinimumHeight(240)
        apply_dark_theme(self)

        self.engine = LimitUpEngine.get_instance()
        self.current_df: Optional[pd.DataFrame] = None
        self.current_records: List[Dict[str, Any]] = []
        self.current_mode: str = "TODAY"  # "TODAY", "3D", "5D", "10D", "LADDER", "HISTORY"
        self.selected_history_date: Optional[str] = None
        self.last_sh_pct: float = 0.0
        self.is_narrow_mode: bool = False
        self._last_wide_width: int = 1280
        # 极窄模式下保留的精选核心列索引：代码(0), 名称(1), 现价(2), 涨幅%(3), 连板数(4), 梯队(5), 形态与质量(6), 封单额(7), 封流比(8), 换手(10), DFF(13), Rank(14)
        self._narrow_cols_to_keep = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 14}

        # 空间龙头当前标的
        self.current_top_leader_code: str = ""
        self.current_top_leader_name: str = ""

        # 键盘上下键与单元格平滑防抖联动
        self._pending_linkage_row: int = -1
        self._last_emitted_code: str = ""
        self._is_populating: bool = False
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setInterval(60)
        self._linkage_timer.setSingleShot(True)
        self._linkage_timer.timeout.connect(self._fire_linkage_debounced)

        # 手动列宽调整防抖持久化定时器
        self._header_save_timer = QTimer(self)
        self._header_save_timer.setInterval(300)
        self._header_save_timer.setSingleShot(True)
        self._header_save_timer.timeout.connect(self._save_current_column_widths)

        # 实时数据推送节流定时器 (1500ms 智能合并，杜绝无谓重复计算与主线程卡顿)
        self._pending_df: Optional[pd.DataFrame] = None
        self._pending_sh_pct: float = 0.0
        self._last_refresh_time: float = 0.0
        self._last_disk_save_time: float = 0.0
        self._refresh_throttle_timer = QTimer(self)
        self._refresh_throttle_timer.setInterval(1500)
        self._refresh_throttle_timer.setSingleShot(True)
        self._refresh_throttle_timer.timeout.connect(self._on_throttle_refresh)

        # 0. Magnetic snap setup (必须在 restore_state 前初始化)
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

        # 1. 独立窗口模式与置顶配置 (默认不置顶，完全独立窗口)
        self.stays_on_top = self._load_stays_on_top()
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        self._init_ui()

        # 2. 恢复几何布局与磁吸状态
        if restore_state:
            self._apply_restore_state(restore_state)
        else:
            self._load_saved_geometry()

        # 3. 首次加载与主动扫描
        self._refresh_data_for_mode()
        if self.is_narrow_mode:
            self._apply_narrow_mode_layout()

        # 4. 实盘时钟周期巡检定时器 (每 5 秒巡检一次时钟跨越，自动平滑切片)
        self._last_time_slice_cache = ""
        self._clock_tick_timer = QTimer(self)
        self._clock_tick_timer.setInterval(5000)
        self._clock_tick_timer.timeout.connect(self._on_clock_tick)
        self._clock_tick_timer.start()

    def _on_clock_tick(self):
        """实盘时钟巡检：若处于【自动实盘跟随】且跨越了时间窗口，自动无缝平滑切片"""
        raw_slice = self.combo_time_slice.currentText() if hasattr(self, "combo_time_slice") else ""
        if "自动实盘跟随" in raw_slice:
            from ats.limit_up_engine import get_live_time_slice_name
            live_slice = get_live_time_slice_name()
            if live_slice != getattr(self, "_last_time_slice_cache", ""):
                self._last_time_slice_cache = live_slice
                self._apply_filter()

    def _load_stays_on_top(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("daily_limit_up_dialog", {}).get("stays_on_top", False)
        except Exception:
            pass
        return False

    def _save_current_column_widths(self):
        """持久化保存当前所有可见/隐藏列的精确列宽"""
        try:
            if hasattr(self, 'table') and self.table:
                col_count = self.table.columnCount()
                widths = [self.table.columnWidth(i) for i in range(col_count)]
                save_config_node("ats_daily_limit_up_table_header", widths)
        except Exception as e:
            logger.debug(f"保存每日涨停看板列宽异常: {e}")

    def _save_window_states(self, is_open: Optional[bool] = None):
        try:
            with _CONFIG_FILE_LOCK:
                config_data = {}
                if os.path.exists(WINDOW_CONFIG_FILE):
                    try:
                        with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                            config_data = json.load(f)
                    except Exception:
                        config_data = {}

                geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
                node = config_data.get("daily_limit_up_dialog", {})
                node.update({
                    "x": geom.x(),
                    "y": geom.y(),
                    "width": geom.width(),
                    "height": geom.height(),
                    "anchor_edge": None if self.stays_on_top else self.anchor_edge,
                    "is_hidden": False if self.stays_on_top else self.is_hidden_state,
                    "stays_on_top": self.stays_on_top,
                    "current_mode": self.current_mode,
                    "is_narrow_mode": self.is_narrow_mode,
                    "last_wide_width": self._last_wide_width
                })
                if hasattr(self, 'table') and self.table:
                    node["column_widths"] = [self.table.columnWidth(i) for i in range(self.table.columnCount())]
                if is_open is not None:
                    node["is_open"] = is_open

                config_data["daily_limit_up_dialog"] = node
                with open(WINDOW_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存每日涨停看板窗口配置异常: {e}")

    def _apply_restore_state(self, state: Dict[str, Any]):
        try:
            x = state.get("x")
            y = state.get("y")
            w = state.get("width", 1280)
            h = state.get("height", 720)
            self._last_wide_width = state.get("last_wide_width", 1280)
            self.is_narrow_mode = state.get("is_narrow_mode", False)
            if hasattr(self, 'btn_narrow_mode'):
                self.btn_narrow_mode.setChecked(self.is_narrow_mode)

            if x is not None and y is not None:
                self.setGeometry(x, y, w, h)
                self.normal_geometry = QRect(x, y, w, h)

            if self.stays_on_top or state.get("stays_on_top", False):
                self.anchor_edge = None
                self.is_hidden_state = False
                self.setWindowOpacity(1.0)
            else:
                self.anchor_edge = state.get("anchor_edge")
                self.is_hidden_state = state.get("is_hidden", False)
            if state.get("current_mode"):
                self.current_mode = state["current_mode"]
        except Exception as e:
            logger.debug(f"应用每日涨停看板恢复状态异常: {e}")

    def _load_saved_geometry(self):
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        st = data.get("daily_limit_up_dialog", {})
                        if st:
                            self._apply_restore_state(st)
        except Exception:
            pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ── 1. 顶部市场核心涨停概览 KPI 卡片 ──
        self.kpi_frame = QFrame()
        self.kpi_frame.setStyleSheet("""
            QFrame {
                background-color: #16181f;
                border: 1px solid #282a36;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        self.kpi_layout = QHBoxLayout(self.kpi_frame)
        self.kpi_layout.setContentsMargins(8, 4, 8, 4)
        self.kpi_layout.setSpacing(12)

        self.lbl_kpi_zt = QLabel("🔴 今日涨停: <b>0</b> 家")
        self.lbl_kpi_zt.setStyleSheet("color: #ff4444; font-size: 10pt;")
        self.kpi_layout.addWidget(self.lbl_kpi_zt)

        self.lbl_kpi_ladder = QLabel("👑 连板天梯: <b>0</b> 家 (最高 <b>0</b> 板)")
        self.lbl_kpi_ladder.setStyleSheet("color: #ffd700; font-size: 10pt;")
        self.kpi_layout.addWidget(self.lbl_kpi_ladder)

        self.lbl_kpi_broken = QLabel("💥 炸板: <b>0</b> 家 (封板率 <b>0.0%</b>)")
        self.lbl_kpi_broken.setStyleSheet("color: #ff9900; font-size: 10pt;")
        self.kpi_layout.addWidget(self.lbl_kpi_broken)

        self.lbl_kpi_seal = QLabel("💰 平均封流比: <b>0.0%</b> | 封单总额: <b>0.0</b> 亿")
        self.lbl_kpi_seal.setStyleSheet("color: #00ffaa; font-size: 10pt;")
        self.kpi_layout.addWidget(self.lbl_kpi_seal)

        self.kpi_layout.addSpacing(10)

        # ⏱️ 盘中时间片生命周期直选 (支持根据实盘时间自动切换 / 手动点选锁定)
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
            QComboBox { background-color: #241e12; color: #ffd700; border: 1px solid #ffaa00; border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 9.5pt; min-width: 180px; }
            QComboBox::drop-down { width: 20px; }
            QComboBox QAbstractItemView { background-color: #1e1e24; color: #ffd700; selection-background-color: #3d3014; }
        """)
        self.combo_time_slice.currentTextChanged.connect(self._apply_filter)
        self.kpi_layout.addWidget(self.combo_time_slice)

        # 梯队分类过滤 (放置在第一行宽敞区域，完整显示无截断)
        self.combo_tier_filter = QComboBox()
        self.combo_tier_filter.addItems([
            "全部梯队", 
            "💎 冰点反身性龙",
            "💎 地量地价起爆",
            "💎 冰点反身潜伏",
            "🟢 黄金潜伏区",
            "🟡 半路点火区",
            "🔴 封板临界区",
            "👑 空间高度龙", 
            "🚀 连板接力", 
            "💎 统治级大封单",
            "🎯 支撑阳包阴反转", 
            "⭐ 20cm强势首板",
            "🔥 强势主升首板", 
            "⚡ 大阳冲板未封",
            "💥 曾涨停炸板"
        ])
        self.combo_tier_filter.setMinimumWidth(135)
        self.combo_tier_filter.setStyleSheet("""
            QComboBox { background-color: #12241e; color: #00ffaa; border: 1px solid #00aa77; border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 9.5pt; min-width: 130px; }
            QComboBox::drop-down { width: 20px; }
            QComboBox QAbstractItemView { background-color: #1e1e24; color: #00ffaa; selection-background-color: #143d2c; }
        """)
        self.combo_tier_filter.currentTextChanged.connect(self._apply_filter)
        self.kpi_layout.addWidget(self.combo_tier_filter)

        self.kpi_layout.addStretch()

        self.btn_top_leader = QPushButton("🏆 空间龙头: --")
        self.btn_top_leader.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_top_leader.setToolTip("点击立即联动切股并在表格中高亮定位当前最高板空间龙头")
        self.btn_top_leader.setStyleSheet("""
            QPushButton {
                background-color: #2b1430;
                color: #ff77ff;
                font-weight: bold;
                font-size: 10pt;
                border: 1px solid #d946ef;
                border-radius: 4px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #d946ef;
                color: #ffffff;
                border-color: #f0abfc;
            }
            QPushButton:pressed {
                background-color: #a21caf;
            }
        """)
        self.btn_top_leader.clicked.connect(self._on_top_leader_clicked)
        self.kpi_layout.addWidget(self.btn_top_leader)

        # 🔔 语音与弹窗预警开关 (圆形绿点指示灯)
        self.is_voice_alert_enabled = self._load_voice_alert_enabled()
        self.btn_voice_alert = QPushButton("🟢 语音预警" if self.is_voice_alert_enabled else "⚪ 语音静音")
        self.btn_voice_alert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_voice_alert.setToolTip("开启/关闭 时间片重点标的挖掘与大盘退潮雪崩 语音播报与右下角弹窗通知")
        self._update_voice_btn_style()
        self.btn_voice_alert.clicked.connect(self._toggle_voice_alert)
        self.kpi_layout.addWidget(self.btn_voice_alert)

        main_layout.addWidget(self.kpi_frame)

        # ── 2. 控制栏 (周期切换、历史回溯、搜索与操作按钮) ──
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 2, 0, 2)
        ctrl_layout.setSpacing(6)

        # 模式切换按钮组
        self.btn_mode_today = QPushButton("🔥 今日涨停")
        self.btn_mode_today.setCheckable(True)
        self.btn_mode_today.setChecked(True)
        self.btn_mode_today.setStyleSheet(self._get_btn_style(active=True))
        self.btn_mode_today.clicked.connect(lambda: self._switch_mode("TODAY"))
        ctrl_layout.addWidget(self.btn_mode_today)

        self.btn_mode_radar = QPushButton("🎯 盘中上车雷达")
        self.btn_mode_radar.setToolTip("盘中动态潜伏与梯度上车雷达 (VWAP均价回踩低吸 / 半路点火确认 / 临界抢跑)")
        self.btn_mode_radar.setCheckable(True)
        self.btn_mode_radar.setStyleSheet(self._get_btn_style(active=False))
        self.btn_mode_radar.clicked.connect(lambda: self._switch_mode("RADAR"))
        ctrl_layout.addWidget(self.btn_mode_radar)

        self.btn_mode_3d = QPushButton("🚀 3日强势")
        self.btn_mode_3d.setCheckable(True)
        self.btn_mode_3d.setStyleSheet(self._get_btn_style(active=False))
        self.btn_mode_3d.clicked.connect(lambda: self._switch_mode("3D"))
        ctrl_layout.addWidget(self.btn_mode_3d)

        self.btn_mode_5d = QPushButton("⚡ 5日强势")
        self.btn_mode_5d.setCheckable(True)
        self.btn_mode_5d.setStyleSheet(self._get_btn_style(active=False))
        self.btn_mode_5d.clicked.connect(lambda: self._switch_mode("5D"))
        ctrl_layout.addWidget(self.btn_mode_5d)

        self.btn_mode_10d = QPushButton("👑 10日强势")
        self.btn_mode_10d.setCheckable(True)
        self.btn_mode_10d.setStyleSheet(self._get_btn_style(active=False))
        self.btn_mode_10d.clicked.connect(lambda: self._switch_mode("10D"))
        ctrl_layout.addWidget(self.btn_mode_10d)

        self.btn_mode_ladder = QPushButton("🪜 连板天梯")
        self.btn_mode_ladder.setCheckable(True)
        self.btn_mode_ladder.setStyleSheet(self._get_btn_style(active=False))
        self.btn_mode_ladder.clicked.connect(lambda: self._switch_mode("LADDER"))
        ctrl_layout.addWidget(self.btn_mode_ladder)

        # 历史日期回溯选择框
        lbl_date = QLabel(" 📅 历史回溯:")
        lbl_date.setStyleSheet("color: #8e8e93; font-size: 9pt;")
        ctrl_layout.addWidget(lbl_date)

        self.combo_history_date = QComboBox()
        self.combo_history_date.setMinimumWidth(110)
        self.combo_history_date.setStyleSheet("""
            QComboBox { background-color: #1e1e24; color: #ffffff; border: 1px solid #33333f; border-radius: 4px; padding: 2px 6px; }
            QComboBox::drop-down { width: 18px; }
        """)
        self._populate_history_dates()
        self.combo_history_date.currentIndexChanged.connect(self._on_history_date_selected)
        ctrl_layout.addWidget(self.combo_history_date)

        # 搜索过滤框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索代码/名称/板块...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet("""
            QLineEdit { background-color: #1e1e24; color: #ffffff; border: 1px solid #33333f; border-radius: 4px; padding: 2px 6px; min-width: 160px; }
        """)
        self.search_edit.textChanged.connect(self._apply_filter)
        ctrl_layout.addWidget(self.search_edit)

        ctrl_layout.addStretch()

        # 📐 自适应与 📱 极窄模式快捷按钮
        self.btn_autofit = QPushButton("📐 自适应")
        self.btn_autofit.setToolTip("一键自适应调整所有表格列宽 (右键表格亦可调用)")
        self.btn_autofit.setStyleSheet("""
            QPushButton { background-color: #1a233a; color: #60a5fa; border: 1px solid #3b82f6; border-radius: 4px; padding: 3px 8px; font-weight: bold; }
            QPushButton:hover { background-color: #3b82f6; color: #ffffff; }
        """)
        self.btn_autofit.clicked.connect(self.auto_fit_columns)
        ctrl_layout.addWidget(self.btn_autofit)

        self.btn_narrow_mode = QPushButton("📱 极窄模式")
        self.btn_narrow_mode.setCheckable(True)
        self.btn_narrow_mode.setChecked(self.is_narrow_mode)
        self.btn_narrow_mode.setToolTip("开启/关闭极窄紧凑盯盘模式 (隐藏次要列，窗口宽度收敛至480px，适合侧边吸附)")
        self.btn_narrow_mode.setStyleSheet("""
            QPushButton { background-color: #2b1f3c; color: #c084fc; border: 1px solid #a855f7; border-radius: 4px; padding: 3px 8px; font-weight: bold; }
            QPushButton:checked { background-color: #7e22ce; color: #ffffff; border-color: #d8b4fe; }
            QPushButton:hover { background-color: #a855f7; color: #ffffff; }
        """)
        self.btn_narrow_mode.toggled.connect(self.toggle_narrow_mode)
        ctrl_layout.addWidget(self.btn_narrow_mode)

        # 刷新与导出按钮
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #1a2a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 8px; }
            QPushButton:hover { background-color: #00ff88; color: #000000; }
        """)
        self.btn_refresh.clicked.connect(self._refresh_data_for_mode)
        ctrl_layout.addWidget(self.btn_refresh)

        self.btn_export = QPushButton("📤 导出")
        self.btn_export.setStyleSheet("""
            QPushButton { background-color: #1e1e24; color: #8e8e93; border: 1px solid #33333f; border-radius: 4px; padding: 3px 8px; }
            QPushButton:hover { background-color: #2e2e36; color: #ffffff; }
        """)
        self.btn_export.clicked.connect(self._export_to_csv)
        ctrl_layout.addWidget(self.btn_export)

        # 置顶保持勾选
        self.chk_ontop = QCheckBox("置顶")
        self.chk_ontop.setChecked(self.stays_on_top)
        self.chk_ontop.setStyleSheet("color: #ffd700; font-size: 9pt;")
        self.chk_ontop.toggled.connect(self._on_stays_on_top_toggled)
        ctrl_layout.addWidget(self.chk_ontop)

        main_layout.addLayout(ctrl_layout)

        # ── 3. 主数据表格 ──
        headers, self.extra_cols = get_limit_up_table_headers()
        self.table = QTableWidget()
        self.table.setItemDelegate(ColorPreservingItemDelegate(self.table))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #121214;
                alternate-background-color: #17171c;
                color: #e2e2e5;
                gridline-color: #282830;
                border: 1px solid #282830;
                selection-background-color: #1e334d;
            }
            QHeaderView::section {
                background-color: #18181f;
                color: #8e8e93;
                font-weight: bold;
                border: 1px solid #282830;
                padding: 4px 6px;
            }
        """)

        # 键盘上下键与鼠标点击统一驱动实时防抖联动
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # 表头右键菜单支持与手动拖拽列宽防抖持久化监听
        header = self.table.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        header.sectionResized.connect(self._on_header_section_resized)

        setup_header_persistence(self.table, "ats_daily_limit_up_table", self)
        main_layout.addWidget(self.table)

        # ── 4. 底部状态栏 ──
        self.lbl_status = QLabel("就绪。实时监控全市场涨停与封单比数据。")
        self.lbl_status.setStyleSheet("color: #8e8e93; font-size: 8.5pt;")
        main_layout.addWidget(self.lbl_status)

    def _on_header_section_resized(self, logicalIndex: int, oldSize: int, newSize: int):
        """当用户手动拖拽调整表格列宽时，触发防抖持久化保存"""
        if getattr(self, '_is_populating', False):
            return
        if hasattr(self, '_header_save_timer'):
            self._header_save_timer.start()

    def _get_btn_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #3b1818;
                    color: #ff5555;
                    font-weight: bold;
                    border: 1px solid #ff4444;
                    border-radius: 4px;
                    padding: 3px 10px;
                }
            """
        return """
            QPushButton {
                background-color: #1e1e24;
                color: #c0c0c8;
                border: 1px solid #33333f;
                border-radius: 4px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #2a2a36;
                color: #ffffff;
            }
        """

    def _populate_history_dates(self):
        curr_text = self.combo_history_date.currentText() if hasattr(self, 'combo_history_date') else ""
        self.combo_history_date.blockSignals(True)
        self.combo_history_date.clear()
        self.combo_history_date.addItem("实时今日")
        archived_dates = self.engine.get_all_archived_dates()
        target_idx = 0
        for idx, d in enumerate(reversed(archived_dates), 1):
            self.combo_history_date.addItem(d)
            if d == curr_text:
                target_idx = idx
        if target_idx > 0:
            self.combo_history_date.setCurrentIndex(target_idx)
        self.combo_history_date.blockSignals(False)

    def _switch_mode(self, mode: str):
        self.current_mode = mode
        self.btn_mode_today.setChecked(mode == "TODAY")
        self.btn_mode_radar.setChecked(mode == "RADAR")
        self.btn_mode_3d.setChecked(mode == "3D")
        self.btn_mode_5d.setChecked(mode == "5D")
        self.btn_mode_10d.setChecked(mode == "10D")
        self.btn_mode_ladder.setChecked(mode == "LADDER")

        self.btn_mode_today.setStyleSheet(self._get_btn_style(mode == "TODAY"))
        self.btn_mode_radar.setStyleSheet(self._get_btn_style(mode == "RADAR"))
        self.btn_mode_3d.setStyleSheet(self._get_btn_style(mode == "3D"))
        self.btn_mode_5d.setStyleSheet(self._get_btn_style(mode == "5D"))
        self.btn_mode_10d.setStyleSheet(self._get_btn_style(mode == "10D"))
        self.btn_mode_ladder.setStyleSheet(self._get_btn_style(mode == "LADDER"))

        if mode != "HISTORY":
            self.combo_history_date.blockSignals(True)
            self.combo_history_date.setCurrentIndex(0)
            self.combo_history_date.blockSignals(False)

        self._refresh_data_for_mode()

    def _on_history_date_selected(self, index: int):
        if index == 0:
            self._switch_mode("TODAY")
        else:
            date_str = self.combo_history_date.currentText()
            self.selected_history_date = date_str
            self.current_mode = "HISTORY"
            for btn in (self.btn_mode_today, self.btn_mode_radar, self.btn_mode_3d, self.btn_mode_5d, self.btn_mode_10d, self.btn_mode_ladder):
                btn.setChecked(False)
                btn.setStyleSheet(self._get_btn_style(False))
            self._refresh_data_for_mode()

    def update_data_payload(self, current_df: Optional[pd.DataFrame] = None, sh_pct: float = 0.0):
        """【外部实时数据注入入口】由 ATS 主窗口在收到 IPC 或轮询数据时驱动，内置节流合并"""
        if current_df is not None and not current_df.empty:
            self.current_df = current_df
            self._pending_df = current_df
        self.last_sh_pct = sh_pct
        self._pending_sh_pct = sh_pct

        # 如果窗口未显示且未隐藏贴边，仅缓存数据，跳过耗时计算与 UI 渲染
        if not self.isVisible() and not getattr(self, 'is_hidden_state', False):
            return

        # 如果用户正在拖拽窗口，暂缓计算重绘，避免拖动掉帧卡顿
        if getattr(self, '_is_dragging', False):
            if not self._refresh_throttle_timer.isActive():
                self._refresh_throttle_timer.start(500)
            return

        now = time.time()
        elapsed = now - getattr(self, '_last_refresh_time', 0.0)
        # 1.5s 智能节流：距离上次更新 >= 1.5s 则立即刷新，否则单次定时器延时合并刷新
        if elapsed >= 1.5:
            self._last_refresh_time = now
            self._refresh_data_for_mode()
        else:
            remaining_ms = max(50, int((1.5 - elapsed) * 1000))
            if not self._refresh_throttle_timer.isActive():
                self._refresh_throttle_timer.start(remaining_ms)

    def _on_throttle_refresh(self):
        """节流定时器到期回调：合并高频推送后执行单次完整计算与渲染"""
        if getattr(self, '_is_dragging', False):
            self._refresh_throttle_timer.start(500)
            return
        self._last_refresh_time = time.time()
        self._refresh_data_for_mode()

    def _resolve_active_strategy_df(self) -> Optional[pd.DataFrame]:
        """【统一感知接口】复用 SectorDataAggregator 递归感知探测系统当前运行中的量化策略主 DataFrame"""
        try:
            from ats.sector_data_aggregator import SectorDataAggregator
            df, _ = SectorDataAggregator.get_instance().resolve_active_strategy_df(self._py_parent or self)
            if df is not None and not df.empty:
                self.current_df = df
                return df
        except Exception:
            pass
        if self.current_df is not None and not self.current_df.empty:
            return self.current_df
        return None

    def _refresh_data_for_mode(self):
        """根据当前选定的视图模式计算并刷新数据"""
        df = self._resolve_active_strategy_df()
        today_str = time.strftime("%Y-%m-%d")
        is_trade_day = cct.get_trade_date_status() if hasattr(cct, "get_trade_date_status") else True
        effective_trade_date = today_str if is_trade_day else (cct.get_last_trade_date() if hasattr(cct, "get_last_trade_date") else today_str)

        if self.current_mode == "TODAY":
            if df is not None and not df.empty:
                self.current_records = self.engine.scan_limit_up_records_from_df(df, fetch_l2_quotes=True, extra_cols=self.extra_cols)
                # 仅在实际交易日进行盘中/盘后自动归档 (非交易日不向磁盘写周六/周日归档)
                if is_trade_day:
                    now = time.time()
                    is_post_trading = time.strftime("%H:%M") >= "15:00"
                    if is_post_trading or (now - getattr(self, '_last_disk_save_time', 0.0) >= 300.0):
                        self._last_disk_save_time = now
                        recs_copy = list(self.current_records)
                        threading.Thread(
                            target=self.engine.save_daily_records_atomic,
                            args=(today_str, recs_copy),
                            kwargs={"force": is_post_trading, "is_eod": is_post_trading},
                            daemon=True
                        ).start()
            else:
                self.current_records = self.engine.get_records_by_date(effective_trade_date)
        elif self.current_mode == "RADAR":
            # 🎯 盘中上车雷达视图
            self.current_records = self.engine.get_intraday_radar_records(current_df=df)
        elif self.current_mode == "3D":
            self.current_records = self.engine.aggregate_multi_day_strong_stocks(days=3, min_limit_ups=1, current_df=df)
        elif self.current_mode == "5D":
            self.current_records = self.engine.aggregate_multi_day_strong_stocks(days=5, min_limit_ups=1, current_df=df)
        elif self.current_mode == "10D":
            self.current_records = self.engine.aggregate_multi_day_strong_stocks(days=10, min_limit_ups=1, current_df=df)
        elif self.current_mode == "LADDER":
            # 连板天梯：连板数 >= 2 的标的
            all_strong = self.engine.aggregate_multi_day_strong_stocks(days=5, min_limit_ups=1, current_df=df)
            self.current_records = [r for r in all_strong if _safe_int(r.get("max_consecutive", r.get("consecutive_boards", 1))) >= 2]
        elif self.current_mode == "HISTORY" and self.selected_history_date:
            self.current_records = self.engine.get_records_by_date(self.selected_history_date)

        # 更新顶部 KPI 卡片 (传入当前全量策略 df 获取全市场宏观情绪与涨跌广度)
        summary = self.engine.get_market_limit_up_summary(self.selected_history_date if self.current_mode == "HISTORY" else effective_trade_date, current_df=df)
        self._update_kpi_display(summary)

        # 应用时间片与梯队过滤并填充表格
        self._apply_filter()

    def _apply_filter(self):
        """【三维精准分拣】联合时间片生命周期、梯队分类与搜索文本进行实时原位过滤"""
        if not hasattr(self, "current_records") or not self.current_records:
            self._populate_table_rows([])
            return

        raw_slice = self.combo_time_slice.currentText() if hasattr(self, "combo_time_slice") else "⚡ 自动实盘跟随"
        if getattr(self, "current_mode", "TODAY") == "HISTORY" and "自动实盘跟随" in raw_slice:
            # 历史回溯模式下，若选择自动实盘跟随，默认展示该历史日的全天完整数据，不应受当前本地时钟截断
            time_slice = "⏱️ 全天全时段"
        elif "全天全时段" in raw_slice:
            # 用户明确选择【全天全时段】时，锁定全量展示，绝不自动切换
            time_slice = "⏱️ 全天全时段"
        elif "自动实盘跟随" in raw_slice:
            # 自动根据当前实盘本地/A股时钟切换对应时间片动能
            from ats.limit_up_engine import get_live_time_slice_name
            time_slice = get_live_time_slice_name()
        else:
            time_slice = raw_slice

        tier_filter = self.combo_tier_filter.currentText() if hasattr(self, "combo_tier_filter") else "全部梯队"
        kw = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""

        filtered = []
        for r in self.current_records:
            # 1. 关键词搜索
            if kw:
                c = str(r.get("code", "")).lower()
                n = str(r.get("name", "")).lower()
                cat = str(r.get("category", "")).lower()
                if kw not in c and kw not in n and kw not in cat:
                    continue

            # 2. 梯队分类过滤
            if tier_filter != "全部梯队":
                tag = str(r.get("tier_tag", ""))
                if tier_filter not in tag:
                    continue

            # 3. ⏱️ 盘中时间片生命周期过滤 (全天全时段时跳过过滤)
            if "全天全时段" in time_slice:
                pass
            elif "黄金定龙" in time_slice:
                # 09:30~10:00 黄金定龙期标的
                t_phase = str(r.get("time_phase", ""))
                is_zt = r.get("is_limit_up", False)
                pct = _safe_float(r.get("pct", 0.0))
                if "黄金定龙" not in t_phase and not is_zt and pct < 7.0:
                    continue
            elif "分歧低吸" in time_slice:
                # 10:00~11:30 分歧回踩低吸标的
                stage = str(r.get("entry_stage", ""))
                is_supp = r.get("is_support_bounce", False)
                if "低吸" not in stage and "潜伏" not in stage and not is_supp:
                    continue
            elif "午后助攻" in time_slice:
                t_phase = str(r.get("time_phase", ""))
                stage = str(r.get("entry_stage", ""))
                if "午后" not in t_phase and "点火" not in stage and "先锋" not in stage:
                    continue
            elif "尾盘诱多" in time_slice:
                # 尾盘脉冲高危标的
                stage = str(r.get("entry_stage", ""))
                tier = str(r.get("tier_tag", ""))
                if "尾盘" not in stage and "尾盘" not in tier and not r.get("is_broken", False):
                    continue
            elif "尾盘定盘" in time_slice:
                if not r.get("is_limit_up", False):
                    continue

            filtered.append(r)

        # 针对具体时间片，按动能评分降序 > 连板高度 > 封流比 精准排序，确保 Top 3~5 核心标的排在最前
        if "全天全时段" not in time_slice:
            filtered.sort(key=lambda x: (
                _safe_float(x.get("momentum_score", 0.0)),
                _safe_int(x.get("consecutive_boards", 1)),
                _safe_float(x.get("seal_to_circ_ratio", 0.0)),
                _safe_float(x.get("pct", 0.0))
            ), reverse=True)

        self._populate_table_rows(filtered)
        top_focus_cnt = min(5, len(filtered))
        self.lbl_status.setText(f"数据已过滤: 视图【{self.current_mode}】时间片【{time_slice}】精选 Top {top_focus_cnt}/{len(filtered)} 核心标的 (更新: {time.strftime('%H:%M:%S')})")

        # 🔔 自动触发时间片重点标的与大盘退潮雪崩语音弹窗通知 (精选 3-5 个)
        self._check_and_notify_slice_highlights(filtered, time_slice)

    def _load_voice_alert_enabled(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("daily_limit_up_dialog", {}).get("voice_alert_enabled", True)
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
                if "daily_limit_up_dialog" not in data:
                    data["daily_limit_up_dialog"] = {}
                data["daily_limit_up_dialog"]["voice_alert_enabled"] = enabled
                with open(WINDOW_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Save voice_alert_enabled failed: {e}")

    def _toggle_voice_alert(self):
        self.is_voice_alert_enabled = not self.is_voice_alert_enabled
        self._save_voice_alert_enabled(self.is_voice_alert_enabled)
        self._update_voice_btn_style()
        status_text = "开启" if self.is_voice_alert_enabled else "关闭"
        self.lbl_status.setText(f"🔔 语音与弹窗预警已【{status_text}】 ({time.strftime('%H:%M:%S')})")

    def _update_voice_btn_style(self):
        if not hasattr(self, 'btn_voice_alert'):
            return
        if self.is_voice_alert_enabled:
            self.btn_voice_alert.setText("🟢 语音预警")
            self.btn_voice_alert.setStyleSheet("""
                QPushButton {
                    background-color: #102a1e;
                    color: #00ff88;
                    font-weight: bold;
                    font-size: 9.5pt;
                    border: 1px solid #00cc66;
                    border-radius: 4px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background-color: #00cc66;
                    color: #ffffff;
                }
            """)
        else:
            self.btn_voice_alert.setText("⚪ 语音静音")
            self.btn_voice_alert.setStyleSheet("""
                QPushButton {
                    background-color: #24242e;
                    color: #8e8e93;
                    font-weight: bold;
                    font-size: 9.5pt;
                    border: 1px solid #444455;
                    border-radius: 4px;
                    padding: 3px 8px;
                }
                QPushButton:hover {
                    background-color: #333344;
                    color: #ffffff;
                }
            """)

    def locate_stock_in_table(self, code: str, auto_popup: bool = False):
        """【全端联动定位】在表格中高亮并居中滚动到指定股票代码"""
        if not code or not hasattr(self, 'table'):
            return
        c = str(code).strip().zfill(6)
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            if code_item and code_item.text().strip().zfill(6) == c:
                self.table.selectRow(row)
                self.table.scrollToItem(code_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                self.lbl_status.setText(f"🎯 已自动定位信号标的: {c} ({time.strftime('%H:%M:%S')})")
                name_item = self.table.item(row, 1)
                n = name_item.text().strip() if name_item else c
                self._broadcast_link_stock(c, n)
                break

    def _check_and_notify_slice_highlights(self, filtered_records: List[Dict[str, Any]], time_slice: str):
        """【时间片重点标的与异动自动挖掘通知：每个时间切片精选 3-5 个核心标的】"""
        if not getattr(self, "is_voice_alert_enabled", True):
            return

        try:
            from ats.alert_notifier import AlertNotifier
            notifier = AlertNotifier.get_instance()
        except Exception:
            return

        if not filtered_records:
            return

        # 筛选当前时间片内评分 >= 85.0 分、未炸板、按综合动能排序精选的前 3~5 个核心标的
        candidates = []
        for r in filtered_records:
            score = _safe_float(r.get("momentum_score", 0.0))
            if score >= 85.0 and not r.get("is_broken", False):
                candidates.append(r)
            if len(candidates) >= 5: # 精选 3~5 个
                break

        for idx, top_cand in enumerate(candidates, 1):
            c = str(top_cand.get("code", "")).zfill(6)
            n = str(top_cand.get("name", c))
            score = _safe_float(top_cand.get("momentum_score", 88.0))
            tier = str(top_cand.get("tier_tag", ""))
            desc = str(top_cand.get("pattern_desc", ""))
            advice = str(top_cand.get("entry_advice", ""))
            
            reason = f"【{time_slice}精选#{idx}】{tier} | {desc} | {advice}"
            notifier.notify_special_signal(code=c, name=n, reason=reason, score=score, parent=self)

    def _update_kpi_display(self, s: Dict[str, Any]):
        self._last_market_summary = s
        zt_cnt = s.get("zt_count", 0)
        max_b = s.get("max_boards", 0)
        multi_b = s.get("multi_boards_count", 0)
        brk_cnt = s.get("broken_count", 0)
        rate = s.get("seal_rate", 0.0)
        avg_seal = s.get("avg_seal_circ_ratio", 0.0)
        tot_amt = s.get("total_seal_amount_yi", 0.0)
        leader = s.get("top_leader", "--")
        self.current_top_leader_code = s.get("top_leader_code", "")
        self.current_top_leader_name = s.get("top_leader_name", "")

        # 市场情绪与防猎状态
        s_phase = s.get("sentiment_phase", "⚖️ 均衡博弈期")
        s_defense = s.get("defense_status", "")
        is_avalanche = s.get("is_avalanche", False)
        up_cnt = s.get("up_cnt", 0)
        down_cnt = s.get("down_cnt", 0)

        if up_cnt > 0 or down_cnt > 0:
            self.lbl_kpi_zt.setText(f"🔴 涨停: <b>{zt_cnt}</b> 家 (<b>{up_cnt}</b>涨/<b>{down_cnt}</b>跌)")
        else:
            self.lbl_kpi_zt.setText(f"🔴 涨停: <b>{zt_cnt}</b> 家")

        self.lbl_kpi_ladder.setText(f"👑 连板: <b>{multi_b}</b> 家 (最高 <b>{max_b}</b> 板)")
        
        # 炸板率恶化时的防猎高亮警示
        if rate < 50.0 and brk_cnt >= 10:
            self.lbl_kpi_broken.setStyleSheet("color: #ff3344; font-size: 10pt; font-weight: bold;")
            self.lbl_kpi_broken.setText(f"🚨 炸板: <b>{brk_cnt}</b> 家 (封板率 <b>{rate:.1f}%</b> 退潮高危!)")
        else:
            self.lbl_kpi_broken.setStyleSheet("color: #ff9900; font-size: 10pt;")
            self.lbl_kpi_broken.setText(f"💥 炸板: <b>{brk_cnt}</b> 家 (封板率 <b>{rate:.1f}%</b>)")

        self.lbl_kpi_seal.setText(f"💰 平均封流比: <b>{avg_seal:.2f}%</b> | 封单总额: <b>{tot_amt:.2f}</b> 亿")
        
        btn_text = f"🏆 空间龙头: {leader}"
        if self.current_top_leader_code:
            btn_text += " ⚡"
        self.btn_top_leader.setText(btn_text)

        if is_avalanche:
            self.lbl_status.setStyleSheet("color: #ff3344; font-weight: bold; background-color: #330000; padding: 2px 6px; border-radius: 3px;")
            self.lbl_status.setText(f"🚨 触发全局防猎熔断: {s_defense}")
            # 触发退潮雪崩全局语音播报
            if getattr(self, "is_voice_alert_enabled", True):
                try:
                    now_ts = time.time()
                    if now_ts - getattr(self, "_last_avalanche_voice_ts", 0.0) > 300.0:
                        self._last_avalanche_voice_ts = now_ts
                        from ats.alert_notifier import AlertNotifier
                        AlertNotifier.get_instance().notify_special_signal("000001", "全市场退潮", f"全市场退潮雪崩，炸板率{100.0-rate:.0f}%, 严禁开仓执行止损", score=99.0, parent=self)
                except Exception:
                    pass

    def _on_top_leader_clicked(self):
        """点击顶部空间龙头按钮：立即联动切股并在表格中高亮定位"""
        if not self.current_top_leader_code:
            return
        c = self.current_top_leader_code
        n = self.current_top_leader_name
        self.code_clicked.emit(c, n)
        self._broadcast_link_stock(c, n)

        # 遍历表格，高亮并滚动到该龙头股票所在行
        found = False
        for row in range(self.table.rowCount()):
            code_item = self.table.item(row, 0)
            if code_item and code_item.text().strip() == c:
                self.table.selectRow(row)
                self.table.scrollToItem(code_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                found = True
                break
        self.lbl_status.setText(f"🏆 已联动并定位空间龙头: {c} {n} ({time.strftime('%H:%M:%S')})")

    def _set_table_item(self, row: int, col: int, text: str, user_data: Any = None, 
                        fg: Optional[QColor] = None, align: int = Qt.AlignmentFlag.AlignCenter,
                        is_bold: bool = False, tooltip: Optional[str] = None):
        """【高性能单元格复用与脏检查】复用已有 QTableWidgetItem，杜绝高频垃圾回收与重绘风暴"""
        item = self.table.item(row, col)
        if item is None:
            item = NumericTableWidgetItem(text)
            self.table.setItem(row, col, item)
        else:
            if item.text() != text:
                item.setText(text)

        if user_data is not None:
            if item.data(Qt.ItemDataRole.UserRole) != user_data:
                item.setData(Qt.ItemDataRole.UserRole, user_data)
        else:
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                item.setData(Qt.ItemDataRole.UserRole, None)
            if hasattr(item, '_raw_value'):
                item._raw_value = None

        if fg is not None:
            item.setForeground(QBrush(fg))
        else:
            item.setForeground(QBrush(QColor("#e2e2e5")))

        item.setTextAlignment(align)

        font = item.font()
        if is_bold != font.bold():
            font.setBold(is_bold)
            item.setFont(font)

        if tooltip:
            item.setToolTip(tooltip)
        elif item.toolTip():
            item.setToolTip("")

    def _populate_table_rows(self, records: List[Dict[str, Any]]):
        """【极速原位填充】批量关闭重绘，复用已有单元格对象，保障 60fps 丝滑拖拽与浏览"""
        self._is_populating = True
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)

        # 记录当前选中代码以保持焦点
        selected_code = None
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            c_it = self.table.item(curr_row, 0)
            if c_it:
                selected_code = c_it.text().strip()

        saved_v = self.table.verticalScrollBar().value()
        saved_h = self.table.horizontalScrollBar().value()

        try:
            if self.table.rowCount() != len(records):
                self.table.setRowCount(len(records))

            for row_idx, r in enumerate(records):
                code = str(r.get("code", "")).zfill(6)
                name = str(r.get("name", code))
                price = _safe_float(r.get("price", 0.0))
                pct = _safe_float(r.get("pct", 0.0))
                consecutive = _safe_int(r.get("consecutive_boards", r.get("max_consecutive", 1)))
                tier_tag = str(r.get("tier_tag", "🔥 首板"))
                seal_amt_wan = _safe_float(r.get("seal_amount_wan", 0.0))
                seal_to_circ = _safe_float(r.get("seal_to_circ_ratio", 0.0))
                seal_to_vol = _safe_float(r.get("seal_to_vol_ratio", 0.0))
                turnover = _safe_float(r.get("turnover_rate", r.get("turnover", 0.0)))
                vol_ratio = _safe_float(r.get("vol_ratio", 1.0))
                amt_yi = _safe_float(r.get("amount_yi", 0.0))

                dff = _safe_float(r.get("dff", 0.0))
                rank_val = _safe_int(r.get("rank", 999))
                dff2 = _safe_float(r.get("dff2", 0.0))
                dff3 = _safe_float(r.get("dff3", 0.0))
                rs_val = _safe_float(r.get("rs_val", 0.0))
                resonance = str(r.get("resonance", "同步整理"))
                category = str(r.get("category", "--"))
                extra_dict = r.get("extra_cols", {})

                # 颜色设定
                color_pct = QColor(COLOR_UP) if pct > 0 else (QColor(COLOR_DOWN) if pct < 0 else QColor("#e2e2e5"))
                color_seal = QColor("#ffd700") if seal_to_circ >= 5.0 else QColor("#ffffff")

                col = 0
                # 0. 代码
                self._set_table_item(row_idx, col, code, fg=QColor("#00ffcc"), align=Qt.AlignmentFlag.AlignCenter); col += 1

                # 1. 名称
                name_fg = QColor("#ffd700") if consecutive >= 3 else QColor("#ffffff")
                self._set_table_item(row_idx, col, name, fg=name_fg, align=Qt.AlignmentFlag.AlignCenter, is_bold=(consecutive >= 3)); col += 1

                # 2. 现价
                self._set_table_item(row_idx, col, f"{price:.2f}", user_data=price, fg=QColor("#ffffff"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 3. 涨幅%
                self._set_table_item(row_idx, col, f"{pct:+.2f}%", user_data=pct, fg=color_pct,
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, is_bold=True); col += 1

                # 4. 连板数
                is_zt = r.get("is_limit_up", False)
                cons_text = f"{consecutive}板" if (consecutive >= 1 and is_zt) else "--"
                cons_data = consecutive if (consecutive >= 1 and is_zt) else None
                cons_fg = QColor("#ff55ff") if (consecutive >= 3 and is_zt) else (QColor("#ffd700") if (consecutive == 2 and is_zt) else QColor("#e2e2e5"))
                self._set_table_item(row_idx, col, cons_text, user_data=cons_data, fg=cons_fg, align=Qt.AlignmentFlag.AlignCenter); col += 1

                # 5. 梯队分类
                tier_fg = QColor("#e2e2e5")
                tier_bold = False
                if "冰点反身" in tier_tag:
                    tier_fg = QColor("#00ffff") # 荧光亮青
                    tier_bold = True
                elif "空间高度龙" in tier_tag:
                    tier_fg = QColor("#ff3399") # 亮洋红
                    tier_bold = True
                elif "统治级" in tier_tag:
                    tier_fg = QColor("#00ffcc") # 碧青极强
                    tier_bold = True
                elif "支撑阳包阴" in tier_tag:
                    tier_fg = QColor("#ff55ff") # 亮紫粉
                    tier_bold = True
                elif "20cm" in tier_tag:
                    tier_fg = QColor("#ffd700") # 金黄
                    tier_bold = True
                elif "连板接力" in tier_tag:
                    tier_fg = QColor("#ffaa00") # 亮橙黄
                elif "黄金潜伏" in tier_tag:
                    tier_fg = QColor("#00e676") # 翠绿
                elif "半路点火" in tier_tag:
                    tier_fg = QColor("#ffea00") # 亮黄
                elif "冲板未封" in tier_tag or "跟涨" in tier_tag:
                    tier_fg = QColor("#aad4ff") # 浅蓝
                elif "炸板" in tier_tag:
                    tier_fg = QColor("#ff8800") # 橙色
                self._set_table_item(row_idx, col, tier_tag, fg=tier_fg, align=Qt.AlignmentFlag.AlignCenter, is_bold=tier_bold); col += 1

                # 6. 形态与质量
                quality_score = _safe_float(r.get("seal_quality_score", 70.0))
                momentum_score = _safe_float(r.get("momentum_score", quality_score))
                desc_tag = str(r.get("pattern_desc", f"动能 {momentum_score:.0f}分"))
                is_bullish_engulfing = r.get("is_bullish_engulfing", False)
                is_support_bounce = r.get("is_support_bounce", False)
                is_reflex_lead = r.get("is_reflexivity_leader", False)
                pct_yesterday = _safe_float(r.get("pct_yesterday", 0.0))
                supp_dist_pct = _safe_float(r.get("supp_dist_pct", 0.0))

                desc_fg = QColor("#e2e2e5")
                desc_bold = False
                if is_reflex_lead:
                    desc_fg = QColor("#00ffff")
                    desc_bold = True
                elif momentum_score >= 95 and is_zt:
                    desc_fg = QColor("#ff3399")
                    desc_bold = True
                elif is_support_bounce and is_bullish_engulfing and is_zt:
                    desc_fg = QColor("#ff55ff")
                    desc_bold = True
                elif is_zt:
                    desc_fg = QColor("#00ffcc")
                elif "黄金潜伏" in desc_tag or "低吸" in desc_tag:
                    desc_fg = QColor("#00e676")
                elif "冲板未封" in desc_tag:
                    desc_fg = QColor("#aad4ff")
                elif r.get("is_broken"):
                    desc_fg = QColor("#ff8800")

                entry_stage = str(r.get("entry_stage", "📋 蓄势观察区"))
                entry_advice = str(r.get("entry_advice", "分时震荡蓄势"))
                bid_p = _safe_float(r.get("bid_pressure", 50.0))
                vwap_val = _safe_float(r.get("vwap", price))
                vwap_dev = _safe_float(r.get("vwap_dev_pct", 0.0))

                tip = (
                    f"【{code} {name} 盘中潜伏与上车深度透视】\n"
                    f"────────────────────────\n"
                    f"• ⏰ 介入时机评估: {r.get('time_phase', '稳健定盘期')} ({r.get('time_tip', '')})\n"
                    f"• 上车信号梯度: {entry_stage}\n"
                    f"• 实战操作建议: {entry_advice}\n"
                    f"• 梯队动能评分: {momentum_score:.0f} 分 (统治力梯队: {tier_tag})\n"
                    f"• 日内VWAP均线: {vwap_val:.2f} 元 (偏离度: {vwap_dev:+.1f}%)\n"
                    f"• 盘口买盘压强: {bid_p:.1f}% | 量比: {vol_ratio:.2f} | 换手: {turnover:.2f}%\n"
                    f"• 2日情绪反包: 昨日涨跌 {pct_yesterday:+.2f}% ➔ 今日涨跌 {pct:+.2f}%"
                    f"{' (🔥阳包阴反转)' if is_bullish_engulfing else ''}\n"
                    f"• 关键支撑位状态: 偏离支撑 {supp_dist_pct:+.1f}%"
                    f"{' (🎯回踩支撑起爆)' if is_support_bounce else ''}\n"
                    f"• 多日趋势强度: DFF={dff:+.2f} | DFF2={dff2:+.1f} | DFF3={dff3:+.1f}\n"
                    f"• 封单指标: 封单额 {seal_amt_wan:,.0f}万 | 封流比 {seal_to_circ:.2f}%\n"
                    f"• 大盘共振偏离: {rs_val:+.2f}% ({resonance})"
                )
                self._set_table_item(row_idx, col, desc_tag, user_data=momentum_score, fg=desc_fg,
                                     align=Qt.AlignmentFlag.AlignCenter, is_bold=desc_bold, tooltip=tip); col += 1

                # 7. 封单额(万)
                seal_amt_txt = f"{seal_amt_wan:,.0f}" if (seal_amt_wan > 0 and is_zt) else "--"
                seal_amt_data = seal_amt_wan if (seal_amt_wan > 0 and is_zt) else None
                self._set_table_item(row_idx, col, seal_amt_txt, user_data=seal_amt_data, fg=color_seal,
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 8. 封流比%
                seal_circ_txt = f"{seal_to_circ:.2f}%" if (seal_to_circ > 0 and is_zt) else "--"
                seal_circ_data = seal_to_circ if (seal_to_circ > 0 and is_zt) else None
                seal_circ_fg = QColor("#ffd700") if (seal_to_circ >= 10.0 and is_zt) else (QColor("#ff9900") if (seal_to_circ >= 5.0 and is_zt) else QColor("#ffffff"))
                self._set_table_item(row_idx, col, seal_circ_txt, user_data=seal_circ_data, fg=seal_circ_fg,
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 9. 封成比%
                seal_vol_txt = f"{seal_to_vol:.1f}%" if (seal_to_vol > 0 and is_zt) else "--"
                seal_vol_data = seal_to_vol if (seal_to_vol > 0 and is_zt) else None
                self._set_table_item(row_idx, col, seal_vol_txt, user_data=seal_vol_data, fg=QColor("#ffffff"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 10. 换手%
                self._set_table_item(row_idx, col, f"{turnover:.2f}%", user_data=turnover, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 11. 量比
                self._set_table_item(row_idx, col, f"{vol_ratio:.2f}", user_data=vol_ratio, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 12. 成交额(亿)
                amt_txt = f"{amt_yi:.2f}" if amt_yi > 0 else "--"
                amt_data = amt_yi if amt_yi > 0 else None
                self._set_table_item(row_idx, col, amt_txt, user_data=amt_data, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 13. DFF
                dff_fg = QColor(COLOR_UP) if dff > 0 else (QColor(COLOR_DOWN) if dff < 0 else QColor("#8e8e93"))
                self._set_table_item(row_idx, col, f"{dff:+.2f}", user_data=dff, fg=dff_fg,
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 14. Rank
                rank_txt = str(rank_val) if rank_val < 999 else "--"
                rank_data = rank_val if rank_val < 999 else None
                self._set_table_item(row_idx, col, rank_txt, user_data=rank_data, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignCenter); col += 1

                # 15. DFF2
                self._set_table_item(row_idx, col, f"{dff2:+.1f}", user_data=dff2, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 16. DFF3
                self._set_table_item(row_idx, col, f"{dff3:+.1f}", user_data=dff3, fg=QColor("#e2e2e5"),
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 17. 大盘偏离
                rs_fg = QColor(COLOR_UP) if rs_val > 0 else QColor(COLOR_DOWN)
                self._set_table_item(row_idx, col, f"{rs_val:+.2f}%", user_data=rs_val, fg=rs_fg,
                                     align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); col += 1

                # 18. 共振状态
                res_fg = QColor("#ff55ff") if resonance == "逆市抗跌" else (QColor("#00ff88") if resonance == "大盘共振" else QColor("#e2e2e5"))
                self._set_table_item(row_idx, col, resonance, fg=res_fg, align=Qt.AlignmentFlag.AlignCenter); col += 1

                # 19. 动态 ats_col 自定义列
                for ec in self.extra_cols:
                    raw_val = extra_dict.get(ec, extra_dict.get(ec.lower(), extra_dict.get(ec.upper(), r.get(ec, r.get(ec.lower(), "--")))))
                    self._set_table_item(row_idx, col, str(raw_val), fg=QColor("#e2e2e5"), align=Qt.AlignmentFlag.AlignCenter); col += 1

                # 20. 所属板块
                self._set_table_item(row_idx, col, category if category else "--", fg=QColor("#e2e2e5"), align=Qt.AlignmentFlag.AlignCenter); col += 1

            # 恢复选中的焦点行
            if selected_code:
                for r_idx in range(self.table.rowCount()):
                    it = self.table.item(r_idx, 0)
                    if it and it.text().strip() == selected_code:
                        self.table.setCurrentCell(r_idx, 0)
                        break

            self.table.verticalScrollBar().setValue(saved_v)
            self.table.horizontalScrollBar().setValue(saved_h)

        finally:
            self.table.setSortingEnabled(True)
            self._is_populating = False
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def _on_current_cell_changed(self, currentRow: int, currentColumn: int, previousRow: int, previousColumn: int):
        """键盘上下键导航与鼠标点击行统一防抖入口"""
        if self._is_populating or currentRow < 0:
            return
        if currentRow == self._pending_linkage_row:
            return
        self._pending_linkage_row = currentRow
        self._linkage_timer.start()

    def _fire_linkage_debounced(self):
        """防抖定时器到期后执行真实切股联动"""
        row = self._pending_linkage_row
        if row < 0 or self._is_populating or row >= self.table.rowCount():
            return
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item:
            c = code_item.text().strip()
            n = name_item.text().strip() if name_item else c
            if c and c != "N/A" and c != self._last_emitted_code:
                self._last_emitted_code = c
                self.code_clicked.emit(c, n)
                self._broadcast_link_stock(c, n)
                self.lbl_status.setText(f"🔗 已联动: {c} {n} (第 {row+1}/{self.table.rowCount()} 行)")

    def _broadcast_link_stock(self, code: str, name: str):
        """向全局主窗口与外部行情终端广播联动"""
        try:
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, 'main_window') and isinstance(app.main_window, ATSMainWindow):
                app.main_window.link_stock(code, name)
        except Exception:
            pass

    def keyPressEvent(self, event):
        """键盘事件处理：回车打开SBC分时图，空格切换关注，Ctrl+C复制"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            row = self.table.currentRow()
            if row >= 0:
                self._on_cell_double_clicked(row, 0)
                return
        elif event.key() == Qt.Key.Key_Space:
            row = self.table.currentRow()
            if row >= 0:
                code_item = self.table.item(row, 0)
                if code_item:
                    c = code_item.text().strip()
                    try:
                        from global_favorites import GlobalFavoriteManager
                        fav_mgr = GlobalFavoriteManager()
                        if c in fav_mgr.get_favorite_stocks():
                            fav_mgr.remove_favorite_stock(c)
                            self.lbl_status.setText(f"⭐ 已从重点关注移除: {c}")
                        else:
                            fav_mgr.add_favorite_stock(c)
                            self.lbl_status.setText(f"⭐ 已加入重点关注: {c}")
                    except Exception:
                        pass
                    return
        super().keyPressEvent(event)

    def _on_cell_clicked(self, row: int, col: int):
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item:
            c = code_item.text().strip()
            n = name_item.text().strip()
            self.code_clicked.emit(c, n)
            self._broadcast_link_stock(c, n)

    def _on_cell_double_clicked(self, row: int, col: int):
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item:
            c = code_item.text().strip()
            n = name_item.text().strip()
            self.code_double_clicked.emit(c, n)
            # 调起 SBC 日内分时图与详情
            try:
                from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
                open_sbc_chart_dialog(self, c)
            except Exception as e:
                logger.debug(f"打开 SBC 分时窗口异常: {e}")

    def auto_fit_columns(self):
        """一键自适应调整所有可见列宽（考虑单元格与表头最大宽度，加安全内边距并保存）"""
        col_count = self.table.columnCount()
        for col in range(col_count):
            if self.table.isColumnHidden(col):
                continue
            self.table.resizeColumnToContents(col)
            w = self.table.columnWidth(col)
            # 增加 12px 安全内边距
            new_w = max(48, w + 12)
            if col == 0:    # 代码
                new_w = max(58, min(80, new_w))
            elif col == 1:  # 名称
                new_w = max(68, min(105, new_w))
            elif col == 2:  # 现价
                new_w = max(56, min(80, new_w))
            elif col == 3:  # 涨幅%
                new_w = max(62, min(85, new_w))
            elif col == 4:  # 连板数
                new_w = max(52, min(75, new_w))
            elif col == 5:  # 梯队分类
                new_w = max(75, min(120, new_w))
            elif col in (12, 13, 14, 15): # DFF / Rank / DFF2 / DFF3
                new_w = max(48, min(75, new_w))
            elif col == col_count - 1: # 最后一列：所属板块 (严格限制列宽)
                new_w = max(65, min(95, new_w))
            elif col == col_count - 2: # 倒数第二列：形态与质量
                new_w = max(70, min(100, new_w))
            self.table.setColumnWidth(col, new_w)

        # 触发持久化保存列宽
        self._save_current_column_widths()
        self.lbl_status.setText(f"📐 已完成一键自适应列宽 ({time.strftime('%H:%M:%S')})")

    def reset_default_columns(self):
        """恢复默认紧凑列宽"""
        default_widths = {
            0: 62, 1: 72, 2: 60, 3: 65, 4: 56, 5: 85,
            6: 78, 7: 68, 8: 65, 9: 60, 10: 58, 11: 72,
            12: 58, 13: 48, 14: 52, 15: 52, 16: 68, 17: 72
        }
        col_count = self.table.columnCount()
        for col in range(col_count):
            if col == col_count - 1:
                w = 80  # 所属板块默认 80px
            elif col == col_count - 2:
                w = 85  # 形态与质量默认 85px
            else:
                w = default_widths.get(col, 65)
            self.table.setColumnWidth(col, w)
        self._save_current_column_widths()
        self.lbl_status.setText(f"🔄 已恢复默认紧凑列宽 ({time.strftime('%H:%M:%S')})")

    def toggle_narrow_mode(self, enabled: Optional[bool] = None):
        """切换极窄紧凑盯盘模式 / 宽屏全景模式"""
        if enabled is None:
            self.is_narrow_mode = not self.is_narrow_mode
        else:
            self.is_narrow_mode = bool(enabled)

        if hasattr(self, 'btn_narrow_mode'):
            self.btn_narrow_mode.blockSignals(True)
            self.btn_narrow_mode.setChecked(self.is_narrow_mode)
            self.btn_narrow_mode.blockSignals(False)

        self._apply_narrow_mode_layout()
        self._save_window_states()

    def _apply_narrow_mode_layout(self):
        """根据当前是否为极窄模式动态调整列显隐、窗口尺寸与 KPI 布局"""
        col_count = self.table.columnCount()

        if self.is_narrow_mode:
            # 1. 隐藏非核心次要列
            for col in range(col_count):
                if col in self._narrow_cols_to_keep:
                    self.table.setColumnHidden(col, False)
                else:
                    self.table.setColumnHidden(col, True)

            # 2. 调整窗口尺寸收敛为极窄宽度
            if self.width() > 620:
                self._last_wide_width = self.width()
                self.resize(480, self.height())
            self.setMinimumWidth(320)

            # 3. 精简顶部 KPI 卡片
            if hasattr(self, 'lbl_kpi_seal'):
                self.lbl_kpi_seal.setVisible(False)
            if hasattr(self, 'lbl_top_leader'):
                self.lbl_top_leader.setVisible(False)

            self.lbl_status.setText(f"📱 已切换为【极窄紧凑模式】 (核心11列, 适合侧边挂靠)")
        else:
            # 1. 恢复展示全部列
            for col in range(col_count):
                self.table.setColumnHidden(col, False)

            # 2. 恢复宽屏尺寸
            if self.width() < 700:
                target_w = max(1120, self._last_wide_width)
                self.resize(target_w, self.height())
            self.setMinimumWidth(480)

            # 3. 恢复顶部全量 KPI 卡片
            if hasattr(self, 'lbl_kpi_seal'):
                self.lbl_kpi_seal.setVisible(True)
            if hasattr(self, 'lbl_top_leader'):
                self.lbl_top_leader.setVisible(True)

            self.lbl_status.setText(f"🖥️ 已切换为【宽屏全量模式】 (全字段+自定义列)")

        # 自适应调整可见列宽
        self.auto_fit_columns()

    def _show_context_menu(self, pos):
        """表格区域右键菜单（支持一键自适应列宽、极窄模式切换及个股深度诊断）"""
        row = self.table.rowAt(pos.y())
        has_stock = False
        c, n = "", ""
        if row >= 0:
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item:
                c = code_item.text().strip()
                n = name_item.text().strip() if name_item else c
                has_stock = True

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e24; color: #e2e2e5; border: 1px solid #33333f; padding: 4px; }
            QMenu::item:selected { background-color: #2a3b4c; color: #ffffff; }
        """)

        # ── 1. 布局与列宽操作项 ──
        act_autofit = menu.addAction("📐 一键自适应列宽")
        act_reset_cols = menu.addAction("🔄 恢复默认列宽")
        act_narrow = menu.addAction("📱 极窄模式 (Narrow Mode)")
        act_narrow.setCheckable(True)
        act_narrow.setChecked(self.is_narrow_mode)
        menu.addSeparator()

        # ── 2. 个股联动与分析项 ──
        act_link = None
        act_sbc = None
        act_60f = None
        act_fav = None
        act_copy = None

        if has_stock:
            act_link = menu.addAction(f"🔗 联动行情终端 ({c} {n})")
            act_sbc = menu.addAction(f"📊 打开 SBC 日内分时走势图")
            act_60f = menu.addAction(f"🎯 60f 通道底部反转测算")
            menu.addSeparator()

            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                is_fav = c in fav_mgr.get_favorite_stocks()
                fav_txt = f"⭐ 取消重点关注 ({c})" if is_fav else f"⭐ 加入重点关注 ({c})"
                act_fav = menu.addAction(fav_txt)
            except Exception:
                pass

            menu.addSeparator()
            act_copy = menu.addAction("📋 复制股票代码")
            menu.addSeparator()

        # ── 3. 全局刷新与导出 ──
        act_refresh = menu.addAction("🔄 刷新当前视图数据")
        act_export = menu.addAction("📤 导出为 CSV 文件")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not action:
            return

        if action == act_autofit:
            self.auto_fit_columns()
        elif action == act_reset_cols:
            self.reset_default_columns()
        elif action == act_narrow:
            self.toggle_narrow_mode()
        elif act_link and action == act_link:
            self.code_clicked.emit(c, n)
            self._broadcast_link_stock(c, n)
        elif act_sbc and action == act_sbc:
            try:
                from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
                open_sbc_chart_dialog(self, c)
            except Exception as ex:
                logger.warning(f"打开 SBC 分时走势异常: {ex}")
        elif act_60f and action == act_60f:
            try:
                from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
                from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog
                strategy = ChannelBottomReversalStrategy()
                df_matched = strategy.scan_stocks_tdx([c], count=120)
                if not df_matched.empty:
                    df_matched["name"] = n
                diag = ChannelReversalScanResultDialog(parent=self, df_results=df_matched, total_scanned=1, source_tab_name="每日涨停")
                diag.show()
            except Exception as ex:
                logger.debug(f"测算 60f 通道异常: {ex}")
        elif act_fav and action == act_fav:
            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                if c in fav_mgr.get_favorite_stocks():
                    fav_mgr.remove_favorite_stock(c)
                else:
                    fav_mgr.add_favorite_stock(c)
            except Exception:
                pass
        elif act_copy and action == act_copy:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(c)
        elif action == act_refresh:
            self._refresh_data_for_mode()
        elif action == act_export:
            self._export_to_csv()

    def _show_header_context_menu(self, pos):
        """表头右键菜单（支持自适应列宽、极窄模式与各列自定义勾选显隐）"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e24; color: #e2e2e5; border: 1px solid #33333f; padding: 4px; }
            QMenu::item:selected { background-color: #2a3b4c; color: #ffffff; }
        """)

        act_autofit = menu.addAction("📐 一键自适应列宽")
        act_reset_cols = menu.addAction("🔄 恢复默认列宽")
        act_narrow = menu.addAction("📱 极窄模式 (Narrow Mode)")
        act_narrow.setCheckable(True)
        act_narrow.setChecked(self.is_narrow_mode)
        menu.addSeparator()

        # 列显隐子菜单
        col_menu = menu.addMenu("👁️ 显示/隐藏各列...")
        col_menu.setStyleSheet(menu.styleSheet())
        col_actions = []
        for i in range(self.table.columnCount()):
            hdr_text = self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else f"第{i+1}列"
            act = col_menu.addAction(hdr_text)
            act.setCheckable(True)
            act.setChecked(not self.table.isColumnHidden(i))
            col_actions.append((act, i))

        action = menu.exec(self.table.horizontalHeader().viewport().mapToGlobal(pos))
        if not action:
            return

        if action == act_autofit:
            self.auto_fit_columns()
        elif action == act_reset_cols:
            self.reset_default_columns()
        elif action == act_narrow:
            self.toggle_narrow_mode()
        else:
            for act, col_idx in col_actions:
                if action == act:
                    self.table.setColumnHidden(col_idx, not act.isChecked())
                    break

    def _export_to_csv(self):
        if not self.current_records:
            QMessageBox.information(self, "提示", "当前列表无数据可导出！")
            return
        fname, _ = QFileDialog.getSaveFileName(self, "导出涨停分析数据", f"ats_limit_up_{self.current_mode}_{time.strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)")
        if fname:
            try:
                df_export = pd.DataFrame(self.current_records)
                df_export.to_csv(fname, index=False, encoding="utf-8-sig")
                QMessageBox.information(self, "成功", f"数据已成功导出至:\n{fname}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"导出文件异常: {e}")

    def _on_stays_on_top_toggled(self, checked: bool):
        self.stays_on_top = checked
        if checked:
            self.snap_timer.stop()
            if hasattr(self, 'hover_timer') and self.hover_timer:
                self.hover_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            if self.is_hidden_state:
                self.show_normal_position()
            self.setWindowOpacity(1.0)
        else:
            if hasattr(self, 'hover_timer') and self.hover_timer:
                self.hover_timer.start()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()
        self._save_window_states()

    def start_slide_animation(self, target_geo: QRect, target_opacity: float = 1.0, duration: int = 250, is_snap_feedback: bool = False):
        if self.anim_group:
            self.anim_group.stop()
            
        self.anim_group = QParallelAnimationGroup(self)
        self.geom_anim = QPropertyAnimation(self, b"geometry", self)
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_geo)
        self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
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
        if self.is_hidden_state:
            return
            
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start(300)
            return
            
        self._is_dragging = False

        if self.stays_on_top:
            self.anchor_edge = None
            self.normal_geometry = None
            return

        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 20 # 调优为更从容自然的 20px，避免过早误吸
        
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
            
        if snapped:
            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            self.start_slide_animation(self.normal_geometry, 1.0, duration=200, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None
            self._save_window_states(is_open=True)

    def hide_to_edge(self):
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止折叠隐藏
        if getattr(self, "stays_on_top", False):
            return
        if not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
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

    def _get_main_app(self):
        curr = self.parent() if hasattr(self, 'parent') else None
        from PyQt6.sip import isdeleted
        try:
            while curr:
                if not isdeleted(curr) and curr.__class__.__name__ == 'ATSMainWindow':
                    return curr
                curr = curr.parent() if hasattr(curr, 'parent') else None
        except Exception:
            pass
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and getattr(app, 'main_window', None) is not None:
            try:
                mw = app.main_window
                if not isdeleted(mw) and mw.__class__.__name__ == 'ATSMainWindow':
                    return mw
            except Exception:
                pass
        return None

    def moveEvent(self, event):
        super().moveEvent(event)
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止触发磁吸贴边
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
        if hasattr(self, '_header_save_timer'):
            self._header_save_timer.stop()
        # 显式持久化保存最新手动/自动调整的表格列宽
        self._save_current_column_widths()

        # 关闭前确保当日最新涨停分析数据即时原子落盘并完成 Gzip 压缩打包（仅限实际交易日）
        is_trade_day = cct.get_trade_date_status() if hasattr(cct, "get_trade_date_status") else True
        if is_trade_day and getattr(self, "current_mode", "") == "TODAY" and hasattr(self, "current_records") and self.current_records:
            today_str = time.strftime("%Y-%m-%d")
            recs_copy = list(self.current_records)
            threading.Thread(
                target=self.engine.save_daily_records_atomic,
                args=(today_str, recs_copy),
                kwargs={"force": True, "is_eod": True},
                daemon=True
            ).start()

        main_app = self._get_main_app()
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
        if hasattr(self, '_header_save_timer'):
            self._header_save_timer.stop()
        self._save_current_column_widths()

        is_trade_day = cct.get_trade_date_status() if hasattr(cct, "get_trade_date_status") else True
        if is_trade_day and getattr(self, "current_mode", "") == "TODAY" and hasattr(self, "current_records") and self.current_records:
            today_str = time.strftime("%Y-%m-%d")
            recs_copy = list(self.current_records)
            threading.Thread(
                target=self.engine.save_daily_records_atomic,
                args=(today_str, recs_copy),
                kwargs={"force": True, "is_eod": True},
                daemon=True
            ).start()

        main_app = self._get_main_app()
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


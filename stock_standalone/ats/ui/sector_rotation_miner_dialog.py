# -*- coding: utf-8 -*-
"""
ats/ui/sector_rotation_miner_dialog.py — 板块轮动前排引导与资金主线回踩启动深挖专业工作台 (Qt6)
=============================================================================
核心特性：
1. 【双视图上下联动工作台】：
   - 上半区：当前引导冲锋的核心资金主线板块与领涨先锋 (单击过滤下半区，双击龙头联动股票，双击板块联动可视化，支持右键菜单)；
   - 下半区：实际资金主线·回踩确认启动跟进池 (dff2 依托 MA20 黄金带 + per1d~per9d 缩量洗盘转阳)；
2. 【高响应异步多线程扫描】：
   - 全市场 5000+ 标的后台异步毫秒级完成扫描，主线程 0 阻塞，绝无白闪与卡顿；
   - 原地 In-place 增量复用刷新，支持按需自动刷新 (3s/5s/10s/30s)；
3. 【全终端无缝生态联动 (SSOT)】：
   - 双击标的即时联动通达信 / 同花顺 / 本地 Visualizer (TCP 26668) / 主界面看板；
   - 右键直通【📈 联动行情】、【📊 打开 SBC 独立分时图】、【🧬 DNA 专项审核 (Alt+W)】、【⭐ 重点关注切换】、【📋 复制查询表达式】；
   - 快捷键支持：`T` 键置顶、`Alt+W` DNA 审核、`F5` 刷新；
   - 绝对放行 `Alt+R`：专属于系统全局/底层 Tk 视窗轮转切换器，本窗口绝不抢占；
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
    QFrame, QMessageBox, QDoubleSpinBox, QFormLayout, QGroupBox, QDialogButtonBox
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QThread, QPoint, QEvent, QRect,
    QParallelAnimationGroup, QPropertyAnimation, QEasingCurve
)
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
    SectorRotationPullbackMiner, get_sector_rotation_miner, is_valid_sector_name,
    PullbackFilterConfig, PRESET_FILTER_MODES
)
from global_favorites import GlobalFavoriteManager
from ats.ui.base_table import send_to_linkage
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("SectorRotationMinerDialog")


class MinerWorkerThread(QThread):
    """后台扫描工作线程，完全不阻塞 Qt 主线程"""
    scan_finished = pyqtSignal(dict)

    def __init__(self, df: pd.DataFrame, filter_config: Optional[PullbackFilterConfig] = None, parent=None):
        super().__init__(parent)
        self.df = df
        self.filter_config = filter_config

    def run(self):
        try:
            miner = get_sector_rotation_miner()
            res = miner.run_mining_pipeline(self.df, filter_config=self.filter_config)
            self.scan_finished.emit(res)
        except Exception as e:
            logger.error(f"[MinerWorkerThread] Scan failed: {e}", exc_info=True)
            self.scan_finished.emit({"sectors": [], "candidates": [], "error": str(e)})


STYLE_PRESET_NORMAL = """
    QPushButton {
        background-color: #2b2b36;
        color: #dcdcdc;
        border: 1px solid #4a4a5a;
        border-radius: 4px;
        padding: 6px 12px;
        font-weight: normal;
    }
    QPushButton:hover {
        background-color: #383848;
        border-color: #6a6a7a;
    }
"""

STYLE_PRESET_ACTIVE = """
    QPushButton {
        background-color: #1a3a60;
        color: #ffd700;
        border: 2px solid #ffd700;
        border-radius: 4px;
        padding: 5px 11px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #234d7d;
    }
"""


class PullbackConfigDialog(QDialog):
    """
    回踩确认启动底层筛选量化参数微调与自定义对话框 (Qt6)
    """
    def __init__(self, current_config: PullbackFilterConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 回踩启动筛选策略参数自定义微调")
        self.resize(520, 500)
        self._config = PullbackFilterConfig.from_dict(current_config.to_dict())
        self._is_updating_ui = False
        apply_dark_theme(self)
        self._init_ui()
        self._sync_mode_state(self._config.mode_name)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. 快捷预设按钮栏与当前生效策略指示
        preset_box = QGroupBox("快捷填充预设模式")
        preset_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #ffd700; border: 1px solid #444455; "
            "border-radius: 4px; margin-top: 6px; padding-top: 10px; }"
        )
        preset_vlayout = QVBoxLayout(preset_box)
        preset_vlayout.setContentsMargins(8, 8, 8, 8)
        preset_vlayout.setSpacing(8)

        preset_btn_layout = QHBoxLayout()
        preset_btn_layout.setSpacing(8)

        self.btn_classic = QPushButton("🎯 经典标准")
        self.btn_classic.clicked.connect(lambda: self._apply_preset("🎯 经典标准"))
        preset_btn_layout.addWidget(self.btn_classic)

        self.btn_breakout = QPushButton("🚀 极速起爆")
        self.btn_breakout.clicked.connect(lambda: self._apply_preset("🚀 极速起爆"))
        preset_btn_layout.addWidget(self.btn_breakout)

        self.btn_channel = QPushButton("💎 稳健通道低吸")
        self.btn_channel.clicked.connect(lambda: self._apply_preset("💎 稳健通道低吸"))
        preset_btn_layout.addWidget(self.btn_channel)

        preset_vlayout.addLayout(preset_btn_layout)

        # 当前生效策略指示器（位于预设按钮下方醒目展示）
        self.lbl_current_strategy = QLabel()
        self.lbl_current_strategy.setWordWrap(True)
        self.lbl_current_strategy.setStyleSheet("""
            QLabel {
                background-color: #162232;
                border: 1px solid #2a4c75;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                color: #e0e8f0;
            }
        """)
        preset_vlayout.addWidget(self.lbl_current_strategy)

        layout.addWidget(preset_box)

        # 2. 核心量化参数表单
        form_box = QGroupBox("量化筛选四维阈值 (修改即自动归为自定义模式)")
        form_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #aad4ff; border: 1px solid #444455; "
            "border-radius: 4px; margin-top: 6px; padding-top: 10px; }"
        )
        form_layout = QFormLayout(form_box)
        form_layout.setContentsMargins(10, 8, 10, 8)
        form_layout.setSpacing(8)

        # MA20 依托区间
        ma_layout = QHBoxLayout()
        self.spin_dff2_min = QDoubleSpinBox()
        self.spin_dff2_min.setRange(-15.0, 10.0)
        self.spin_dff2_min.setSingleStep(0.1)
        self.spin_dff2_min.setSuffix(" %")
        self.spin_dff2_min.setValue(self._config.dff2_min)

        self.spin_dff2_max = QDoubleSpinBox()
        self.spin_dff2_max.setRange(-5.0, 20.0)
        self.spin_dff2_max.setSingleStep(0.1)
        self.spin_dff2_max.setSuffix(" %")
        self.spin_dff2_max.setValue(self._config.dff2_max)

        ma_layout.addWidget(QLabel("下限:"))
        ma_layout.addWidget(self.spin_dff2_min)
        ma_layout.addWidget(QLabel("上限:"))
        ma_layout.addWidget(self.spin_dff2_max)
        form_layout.addRow("MA20依托乖离(dff2):", ma_layout)

        # 涨幅区间 (坚决收阳 >= 0.0)
        pct_layout = QHBoxLayout()
        self.spin_min_pct = QDoubleSpinBox()
        self.spin_min_pct.setRange(0.0, 10.0)
        self.spin_min_pct.setSingleStep(0.1)
        self.spin_min_pct.setSuffix(" %")
        self.spin_min_pct.setValue(max(0.0, self._config.min_eval_pct))

        self.spin_max_pct = QDoubleSpinBox()
        self.spin_max_pct.setRange(1.0, 20.0)
        self.spin_max_pct.setSingleStep(0.5)
        self.spin_max_pct.setSuffix(" %")
        self.spin_max_pct.setValue(self._config.max_eval_pct)

        pct_layout.addWidget(QLabel("最小收阳:"))
        pct_layout.addWidget(self.spin_min_pct)
        pct_layout.addWidget(QLabel("防追高上限:"))
        pct_layout.addWidget(self.spin_max_pct)
        form_layout.addRow("涨幅区间 (坚决收阳):", pct_layout)

        # 最小放量量比
        self.spin_vr = QDoubleSpinBox()
        self.spin_vr.setRange(0.5, 10.0)
        self.spin_vr.setSingleStep(0.05)
        self.spin_vr.setValue(self._config.min_vol_ratio)
        form_layout.addRow("启动温和量比(vr >=):", self.spin_vr)

        # 最小换手率
        self.spin_to = QDoubleSpinBox()
        self.spin_to.setRange(0.0, 50.0)
        self.spin_to.setSingleStep(0.1)
        self.spin_to.setSuffix(" %")
        self.spin_to.setValue(self._config.min_turnover)
        form_layout.addRow("活跃势能换手率(>=):", self.spin_to)

        # 最小成交额
        self.spin_amt = QDoubleSpinBox()
        self.spin_amt.setRange(0.0, 50.0)
        self.spin_amt.setSingleStep(0.05)
        self.spin_amt.setSuffix(" 亿元")
        self.spin_amt.setValue(self._config.min_amt_yi)
        form_layout.addRow("成交额底线(>=):", self.spin_amt)

        # 长期跌幅底线
        self.spin_dff3 = QDoubleSpinBox()
        self.spin_dff3.setRange(-50.0, 50.0)
        self.spin_dff3.setSingleStep(1.0)
        self.spin_dff3.setSuffix(" %")
        self.spin_dff3.setValue(self._config.min_dff3)
        form_layout.addRow("长期跌幅底线(dff3 >=):", self.spin_dff3)

        # 通道支撑选项
        ch_layout = QHBoxLayout()
        self.chk_require_ch = QCheckBox("必须处于通道支撑/底座")
        self.chk_require_ch.setChecked(self._config.require_channel_supp)
        self.chk_prefer_ch = QCheckBox("通道支撑优先加权(+5分)")
        self.chk_prefer_ch.setChecked(self._config.prefer_channel_supp)
        ch_layout.addWidget(self.chk_require_ch)
        ch_layout.addWidget(self.chk_prefer_ch)
        form_layout.addRow("通道支撑共振:", ch_layout)

        # 监听所有输入变动以动态感知模式变化
        for spin in [self.spin_dff2_min, self.spin_dff2_max, self.spin_min_pct, self.spin_max_pct,
                     self.spin_vr, self.spin_to, self.spin_amt, self.spin_dff3]:
            spin.valueChanged.connect(self._on_param_changed)

        self.chk_require_ch.toggled.connect(self._on_param_changed)
        self.chk_prefer_ch.toggled.connect(self._on_param_changed)

        layout.addWidget(form_box)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 保存并应用扫描")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #ffffff; font-weight: bold;
                border: 1px solid #3d6ea8; border-radius: 4px; padding: 6px 14px;
            }
            QPushButton:hover { background-color: #2a5282; }
        """)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("✕ 取消")
        self.btn_cancel.setStyleSheet("padding: 6px 12px;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _detect_current_mode(self) -> str:
        """根据当前表单数值智能识别是否匹配某个内置预设模式，否则为自定义"""
        cur_dff2_min = round(self.spin_dff2_min.value(), 2)
        cur_dff2_max = round(self.spin_dff2_max.value(), 2)
        cur_min_pct = round(max(0.0, self.spin_min_pct.value()), 2)
        cur_max_pct = round(self.spin_max_pct.value(), 2)
        cur_vr = round(self.spin_vr.value(), 2)
        cur_to = round(self.spin_to.value(), 2)
        cur_amt = round(self.spin_amt.value(), 2)
        cur_dff3 = round(self.spin_dff3.value(), 2)
        cur_req_ch = self.chk_require_ch.isChecked()
        cur_pref_ch = self.chk_prefer_ch.isChecked()

        for name, p in PRESET_FILTER_MODES.items():
            if (cur_dff2_min == round(p.dff2_min, 2) and
                cur_dff2_max == round(p.dff2_max, 2) and
                cur_min_pct == round(p.min_eval_pct, 2) and
                cur_max_pct == round(p.max_eval_pct, 2) and
                cur_vr == round(p.min_vol_ratio, 2) and
                cur_to == round(p.min_turnover, 2) and
                cur_amt == round(p.min_amt_yi, 2) and
                cur_dff3 == round(p.min_dff3, 2) and
                cur_req_ch == p.require_channel_supp and
                cur_pref_ch == p.prefer_channel_supp):
                return name
        return "⚙️ 自定义"

    def _sync_mode_state(self, mode_name: str):
        """同步更新当前策略标签与预设按钮的高亮状态"""
        self.btn_classic.setStyleSheet(STYLE_PRESET_ACTIVE if mode_name == "🎯 经典标准" else STYLE_PRESET_NORMAL)
        self.btn_breakout.setStyleSheet(STYLE_PRESET_ACTIVE if mode_name == "🚀 极速起爆" else STYLE_PRESET_NORMAL)
        self.btn_channel.setStyleSheet(STYLE_PRESET_ACTIVE if mode_name == "💎 稳健通道低吸" else STYLE_PRESET_NORMAL)

        if mode_name == "🎯 经典标准":
            self.lbl_current_strategy.setText(
                "📌 当前生效策略: <b style='color: #00d2ff; font-size: 13px;'>🎯 经典标准</b> "
                "<span style='color: #90caf9; font-size: 11px;'>(均衡稳健·MA20依托+放量收阳)</span>"
            )
        elif mode_name == "🚀 极速起爆":
            self.lbl_current_strategy.setText(
                "📌 当前生效策略: <b style='color: #ff5252; font-size: 13px;'>🚀 极速起爆</b> "
                "<span style='color: #ff8a80; font-size: 11px;'>(追击主升突破·强收阳+高换手+大量比)</span>"
            )
        elif mode_name == "💎 稳健通道低吸":
            self.lbl_current_strategy.setText(
                "📌 当前生效策略: <b style='color: #ffd700; font-size: 13px;'>💎 稳健通道低吸</b> "
                "<span style='color: #ffe082; font-size: 11px;'>(硬约束通道底座支撑+均线企稳低吸)</span>"
            )
        else:
            self.lbl_current_strategy.setText(
                "📌 当前生效策略: <b style='color: #ffb74d; font-size: 13px;'>⚙️ 自定义微调</b> "
                "<span style='color: #b0bec5; font-size: 11px;'>(参数已手动微调，偏离标准预设)</span>"
            )

    def _on_param_changed(self):
        if self._is_updating_ui:
            return
        mode_name = self._detect_current_mode()
        self._sync_mode_state(mode_name)

    def _apply_preset(self, mode_name: str):
        if mode_name in PRESET_FILTER_MODES:
            p = PRESET_FILTER_MODES[mode_name]
            self._is_updating_ui = True
            try:
                self.spin_dff2_min.setValue(p.dff2_min)
                self.spin_dff2_max.setValue(p.dff2_max)
                self.spin_min_pct.setValue(p.min_eval_pct)
                self.spin_max_pct.setValue(p.max_eval_pct)
                self.spin_vr.setValue(p.min_vol_ratio)
                self.spin_to.setValue(p.min_turnover)
                self.spin_amt.setValue(p.min_amt_yi)
                self.spin_dff3.setValue(p.min_dff3)
                self.chk_require_ch.setChecked(p.require_channel_supp)
                self.chk_prefer_ch.setChecked(p.prefer_channel_supp)
            finally:
                self._is_updating_ui = False
            self._sync_mode_state(mode_name)

    def _on_save_clicked(self):
        mode_name = self._detect_current_mode()
        self._config = PullbackFilterConfig(
            mode_name=mode_name,
            dff2_min=round(self.spin_dff2_min.value(), 2),
            dff2_max=round(self.spin_dff2_max.value(), 2),
            min_eval_pct=round(max(0.0, self.spin_min_pct.value()), 2),
            max_eval_pct=round(self.spin_max_pct.value(), 2),
            min_vol_ratio=round(self.spin_vr.value(), 2),
            min_turnover=round(self.spin_to.value(), 2),
            min_amt_yi=round(self.spin_amt.value(), 2),
            min_dff3=round(self.spin_dff3.value(), 2),
            require_channel_supp=self.chk_require_ch.isChecked(),
            prefer_channel_supp=self.chk_prefer_ch.isChecked()
        )
        self.accept()

    def get_config(self) -> PullbackFilterConfig:
        return self._config


class SectorRotationMinerDialog(QDialog, WindowMixin):
    """
    板块轮动前排引导与资金主线回踩启动深挖专业工作台 (Qt6)
    """
    code_clicked = pyqtSignal(str) # 选股或双击联动信号

    def __init__(self, parent=None, current_df: Optional[pd.DataFrame] = None):
        # [🚀 独立顶层解耦] 传入 None 剥离 Win32 HWND Owner 从属关系，彻底切断物理强行置顶，避免遮挡 ATS 主窗口
        super().__init__(None)
        self._parent_window = parent

        # 启用完整独立窗口行为 (支持最小化、最大化与自由缩放调节)
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowFlags(flags)
        self.setWindowTitle("🔥 板块轮动前排引导与资金主线回踩启动深挖工作台")
        self.resize(1180, 720)
        self.setMinimumSize(680, 420) # 明确放开最小窗口限制，支持小屏/分屏自适应调整

        self.current_df = current_df
        self._all_candidates: List[Dict[str, Any]] = []
        self._last_sectors: List[Dict[str, Any]] = []
        self._selected_sector: Optional[str] = None
        self._worker: Optional[MinerWorkerThread] = None
        self._current_filter_config: PullbackFilterConfig = PRESET_FILTER_MODES["🎯 经典标准"]

        # 视图模式（精简 vs 全貌）与几何尺寸
        self._is_compact_mode: bool = False
        self._full_geometry = None
        self._compact_geometry = None
        self._is_snapping: bool = False
        self._in_snap_action: bool = False
        self.anim_group = None
        self.geom_anim = None
        self.opacity_anim = None

        # ATS 标准磁吸贴边与折叠感应状态 (对齐 DailyLimitUpDialog / HotSectorLeaderboard SSOT)
        self.anchor_edge: Optional[str] = None
        self.is_hidden_state: bool = False
        self.normal_geometry: Optional[QRect] = None
        self.hover_ticks: int = 0
        self.leave_ticks: int = 0
        self._is_dragging: bool = False
        self._last_show_time: float = 0.0
        self._has_hovered_since_show: bool = False
        self._is_auto_popping: bool = False
        self.stays_on_top: bool = False

        # 联动记忆与防抖 (遵循系统底层联动逻辑：相同 code 绝不触发外部联动)
        self._last_linked_code: Optional[str] = None
        self._last_linked_date: Optional[str] = None
        self._last_linked_time: float = 0.0

        # 悬停与离开监控定时器 (默认保持停止，仅在贴边或隐藏感应态激活，0 额外开销)
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)

        # 磁吸贴边防抖定时器 (拖拽释放后 300ms 检测靠近屏幕边缘贴边)
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(300)
        self.snap_timer.timeout.connect(self._detect_and_snap)
        self._snap_timer = self.snap_timer

        # 自动刷新定时器
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_auto_refresh)

        # 初始化 UI 与快捷键
        self._init_ui()
        self._init_shortcuts()
        self._init_filter_config()

        # 恢复窗口位置与尺寸
        self.load_window_position_qt(self, "sector_rotation_miner_dialog", default_width=1180, default_height=720)

        # 恢复 normal_geometry 与磁吸贴边状态
        saved_normal = load_config_node("sector_miner_normal_geo", None)
        if saved_normal and isinstance(saved_normal, (list, tuple)) and len(saved_normal) >= 4:
            nx, ny, nw, nh = saved_normal[:4]
            from gui_utils import clamp_window_to_screens
            nx, ny = clamp_window_to_screens(nx, ny, nw, nh)
            from PyQt6.QtCore import QPoint
            _scr = QApplication.screenAt(QPoint(nx, ny)) or QApplication.primaryScreen()
            if _scr:
                _s_geo = _scr.availableGeometry()
                nx = max(_s_geo.left(), min(nx, _s_geo.right() - nw))
                ny = max(_s_geo.top(), min(ny, _s_geo.bottom() - nh))
            self.normal_geometry = QRect(nx, ny, nw, nh)
        else:
            self.normal_geometry = self.geometry()

        # 恢复持久化的置顶与磁吸折叠状态
        saved_top = load_config_node("sector_miner_stays_on_top", False)
        if saved_top:
            self._toggle_stay_on_top(True)
        else:
            self.anchor_edge = load_config_node("sector_miner_anchor_edge", None)
            saved_hidden = load_config_node("sector_miner_is_hidden", False)
            if saved_hidden and self.anchor_edge and self.normal_geometry:
                self.is_hidden_state = True
                strip_size = 5
                screen = self.screen() or QApplication.primaryScreen()
                screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                rw, rh = self.normal_geometry.width(), self.normal_geometry.height()
                rx, ry = self.normal_geometry.x(), self.normal_geometry.y()
                if self.anchor_edge == "left":
                    hx = screen_geo.left() - rw + strip_size
                    hy = ry
                elif self.anchor_edge == "right":
                    hx = screen_geo.right() - strip_size
                    hy = ry
                elif self.anchor_edge == "top":
                    hx = rx
                    hy = screen_geo.top() - rh + strip_size
                else:
                    hx, hy = rx, ry
                    self.is_hidden_state = False
                self.setGeometry(hx, hy, rw, rh)
                self.setWindowOpacity(0.35)
                if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
                    self.hover_timer.start()
            elif self.anchor_edge:
                if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
                    self.hover_timer.start()

        # 恢复列宽持久化
        setup_header_persistence(self.sectors_table, "sector_miner_sectors_header")
        setup_header_persistence(self.candidates_table, "sector_miner_candidates_header")

        # 恢复持久化的视图模式 (若上次退出为精简模式，则自适应切换)
        saved_view = load_config_node("sector_miner_view_mode", "full")
        if saved_view == "compact":
            self.toggle_compact_mode(force_compact=True)

        # 首次加载数据
        if self.current_df is not None and not self.current_df.empty:
            QTimer.singleShot(100, self.trigger_scan)

    def _init_ui(self):
        """构建现代暗色专业 UI 布局 (自适应响应式，支持任意窗口尺寸调整)"""
        apply_dark_theme(self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(5)

        # ── 1. 顶部控制栏 (自适应双行紧凑布局，彻底消除单行横向卡死窗口问题) ──
        top_bar = QFrame(self)
        top_bar.setStyleSheet("background-color: #1a1a22; border-radius: 6px; padding: 4px;")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(4)

        # 1.1 主控制操作行 (Row 1)
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)

        self.lbl_title = QLabel("🔥 轮动深挖与回踩启动")
        self.lbl_title.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #ffd700;")
        row1_layout.addWidget(self.lbl_title)

        self.lbl_compact_title = QLabel("🔥 轮动精简")
        self.lbl_compact_title.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffd700;")
        self.lbl_compact_title.setVisible(False)
        row1_layout.addWidget(self.lbl_compact_title)

        row1_layout.addSpacing(6)

        self.btn_scan = QPushButton("🚀 一键深度挖掘")
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #ffffff; font-weight: bold;
                border: 1px solid #3d6ea8; border-radius: 4px; padding: 4px 10px;
            }
            QPushButton:hover { background-color: #2a5282; }
            QPushButton:pressed { background-color: #162c46; }
        """)
        self.btn_scan.clicked.connect(self.trigger_scan)
        row1_layout.addWidget(self.btn_scan)

        base_sec = self._get_global_ats_interval()
        base_sec_str = f"{int(base_sec)}" if base_sec.is_integer() else f"{base_sec:.1f}"

        self.chk_auto = QCheckBox("自动刷新")
        self.chk_auto.setStyleSheet("color: #aad4ff; font-weight: bold;")
        self.chk_auto.setToolTip(
            f"勾选开启盘中自动轮询扫描。\n"
            f"• 默认对齐系统全局基准 (cct.ats_tdx_interval = {base_sec_str}s)\n"
            f"• 亦可在右侧下拉框独立按需微调刷新频率"
        )
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        row1_layout.addWidget(self.chk_auto)

        self.combo_interval = QComboBox()
        intervals = [3.0, 5.0, 10.0, 30.0]
        if not any(abs(x - base_sec) < 0.1 for x in intervals):
            intervals.append(base_sec)
            intervals.sort()

        default_idx = 1
        for idx, sec in enumerate(intervals):
            sec_text = f"{int(sec)} 秒" if sec.is_integer() else f"{sec:.1f} 秒"
            if abs(sec - base_sec) < 0.1:
                sec_text += " (全局基准)"
                default_idx = idx
            self.combo_interval.addItem(sec_text)

        self.combo_interval.setCurrentIndex(default_idx)
        self.combo_interval.setToolTip(
            f"自动刷新间隔设置：\n"
            f"• 系统全局基准: cct.ats_tdx_interval = {base_sec_str}s\n"
            f"• 支持按需独立微调: 3s 极速抢筹 | 5s 均衡扫描 | 10s 稳健省流 | 30s 低耗"
        )
        self.combo_interval.currentIndexChanged.connect(self._on_interval_changed)
        row1_layout.addWidget(self.combo_interval)

        self.lbl_mode = QLabel("策略:")
        self.lbl_mode.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 9pt;")
        row1_layout.addWidget(self.lbl_mode)

        self.combo_filter_mode = QComboBox()
        self.combo_filter_mode.addItems(["🎯 经典标准", "🚀 极速起爆", "💎 稳健通道低吸", "⚙️ 自定义"])
        self.combo_filter_mode.setStyleSheet("""
            QComboBox {
                background-color: #1a2233; color: #ffffff; border: 1px solid #3d6ea8;
                border-radius: 4px; padding: 3px 6px; font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #1a1a22; selection-background-color: #2a5282; color: #ffffff; }
        """)
        self.combo_filter_mode.currentIndexChanged.connect(self._on_filter_mode_changed)
        row1_layout.addWidget(self.combo_filter_mode)

        self.btn_config = QPushButton("⚙️ 微调")
        self.btn_config.setToolTip("自定义微调MA20依托区间、涨幅收阳门槛、量比、换手率与通道支撑")
        self.btn_config.setStyleSheet("""
            QPushButton {
                background-color: #263345; color: #aad4ff; border: 1px solid #456285;
                border-radius: 4px; padding: 3px 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #354a66; color: #ffffff; }
            QPushButton:pressed { background-color: #1a2533; }
        """)
        self.btn_config.clicked.connect(self._open_filter_config_dialog)
        row1_layout.addWidget(self.btn_config)

        row1_layout.addStretch()

        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("🔍 快速过滤...")
        self.txt_filter.setMinimumWidth(80)
        self.txt_filter.setMaximumWidth(150)
        self.txt_filter.setStyleSheet("background-color: #121216; color: #ffffff; border: 1px solid #334455; border-radius: 4px; padding: 3px 5px;")
        self.txt_filter.textChanged.connect(self._apply_candidate_filter)
        row1_layout.addWidget(self.txt_filter)

        self.btn_top = QPushButton("📌 置顶 (T)")
        self.btn_top.setCheckable(True)
        self.btn_top.setStyleSheet("""
            QPushButton {
                background-color: #2a2a32; color: #cccccc; border: 1px solid #444455;
                border-radius: 4px; padding: 3px 7px;
            }
            QPushButton:checked { background-color: #995500; color: #ffffff; border-color: #ffaa00; }
        """)
        self.btn_top.toggled.connect(self._toggle_stay_on_top)
        row1_layout.addWidget(self.btn_top)

        self.btn_compact = QPushButton("🧲 精简 (M)")
        self.btn_compact.setToolTip("切换精简盯盘卡片模式 / 恢复全貌 (快捷键 M)\n支持屏幕贴边磁吸吸附、独立悬浮置顶盯盘")
        self.btn_compact.setStyleSheet("""
            QPushButton {
                background-color: #23354a; color: #aadcff; border: 1px solid #3d6ea8;
                border-radius: 4px; padding: 3px 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2d4562; color: #ffffff; }
        """)
        self.btn_compact.clicked.connect(lambda: self.toggle_compact_mode())
        row1_layout.addWidget(self.btn_compact)

        self.btn_close = QPushButton("✕ 关闭 (Esc)")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #2a2228; color: #ff8888; border: 1px solid #663344;
                border-radius: 4px; padding: 3px 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #552233; color: #ffaaaa; border-color: #aa4455; }
            QPushButton:pressed { background-color: #331122; color: #ffffff; }
        """)
        self.btn_close.clicked.connect(self.close)
        row1_layout.addWidget(self.btn_close)

        top_layout.addLayout(row1_layout)

        # 1.2 策略量化简报与快捷提示副行 (Row 2，自适应伸缩容器)
        self.row2_widget = QWidget(self)
        row2_layout = QHBoxLayout(self.row2_widget)
        row2_layout.setContentsMargins(2, 0, 2, 0)
        row2_layout.setSpacing(6)

        self.lbl_mode_summary = QLabel("")
        self.lbl_mode_summary.setStyleSheet("color: #88ccaa; font-size: 8.5pt;")
        row2_layout.addWidget(self.lbl_mode_summary)

        row2_layout.addStretch()

        lbl_quick_tip = QLabel("💡 单击板块过滤/反选 | 单击领涨龙头自动联动 | ↑↓浏览 | 双击联动 | M精简 | Alt+W 审计")
        lbl_quick_tip.setStyleSheet("color: #778899; font-size: 8pt;")
        row2_layout.addWidget(lbl_quick_tip)

        top_layout.addWidget(self.row2_widget)

        main_layout.addWidget(top_bar)

        # ── 2. 主体工作区 (QSplitter 上下切分，支持平滑缩放与最小高度保护) ──
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
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
        sectors_layout.setSpacing(3)

        sec_header = QHBoxLayout()
        lbl_sec_title = QLabel("🔥 引导冲锋·核心资金主线板块")
        lbl_sec_title.setToolTip("单击板块过滤/反选下半区 | 单击领涨龙头自动联动股票 | 上下键移动光标浏览 | 右键菜单操作")
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
        self.sectors_table.setMinimumHeight(100)
        self.sectors_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sectors_table.itemClicked.connect(self._on_sector_row_clicked)
        self.sectors_table.currentItemChanged.connect(self._on_sector_current_changed)
        self.sectors_table.installEventFilter(self)  # 回车/空格直接联动龙头股票
        self.sectors_table.itemDoubleClicked.connect(self._on_sector_double_clicked)
        self.sectors_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sectors_table.customContextMenuRequested.connect(self._on_sector_context_menu)
        sectors_layout.addWidget(self.sectors_table)

        self.splitter.addWidget(sectors_panel)

        # ── 下半区：资金主线·回踩确认启动跟进池 ──
        candidates_panel = QWidget()
        candidates_layout = QVBoxLayout(candidates_panel)
        candidates_layout.setContentsMargins(0, 0, 0, 0)
        candidates_layout.setSpacing(3)

        cand_header = QHBoxLayout()
        self.lbl_cand_title = QLabel("🎯 资金主线·回踩确认启动跟进池")
        self.lbl_cand_title.setToolTip("点击或上下键即时联动 / 双击联动外部行情 / 右键异动联动 / Alt+W 审计")
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
        self.candidates_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.candidates_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.candidates_table.setAlternatingRowColors(True)
        self.candidates_table.setMinimumHeight(120)
        self.candidates_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.candidates_table.itemClicked.connect(self._on_candidate_clicked)
        self.candidates_table.currentItemChanged.connect(self._on_candidate_current_changed)
        self.candidates_table.itemDoubleClicked.connect(self._on_candidate_double_clicked)
        self.candidates_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.candidates_table.customContextMenuRequested.connect(self._on_candidate_context_menu)
        candidates_layout.addWidget(self.candidates_table)

        self.splitter.addWidget(candidates_panel)

        # 设置上下 Splitter 默认高度比例 (1 : 2)
        self.splitter.setSizes([200, 420])
        main_layout.addWidget(self.splitter)

        # ── 3. 底部状态栏 ──
        self.status_bar = QLabel("就绪. 点击【🚀 一键深度挖掘】开始全市场主线与回踩扫描.")
        self.status_bar.setStyleSheet("color: #888899; font-size: 8.5pt; padding: 2px;")
        main_layout.addWidget(self.status_bar)

    def _init_shortcuts(self):
        """绑定常用便捷快捷键 (坚决不抢占 Alt+R，确保专属于系统全局视窗轮转)"""
        # 快捷键 T: 切换置顶 (使用全局穿透回调)
        bind_top_shortcut(self, lambda: self._toggle_stay_on_top())

        # 快捷键 M: 切换精简/全貌模式 (窗口级全局穿透，子控件获焦亦可触发)
        m_shortcut = QShortcut(QKeySequence(Qt.Key.Key_M), self)
        m_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        m_shortcut.activated.connect(self._on_m_shortcut_activated)
        setattr(self, "_compact_shortcut_m", m_shortcut)

        # 快捷键 F5: 刷新
        f5_shortcut = QShortcut(QKeySequence("F5"), self)
        f5_shortcut.activated.connect(self.trigger_scan)

        # 快捷键 Alt+W: DNA 专项审核
        dna_shortcut = QShortcut(QKeySequence("Alt+W"), self)
        dna_shortcut.activated.connect(self._run_dna_audit_selected)

    def _on_m_shortcut_activated(self):
        """M 快捷键响应：文本编辑时不抢占，其余状态秒切精简/全貌"""
        from ats.ui.styles import is_editing_text
        if not is_editing_text(self):
            self.toggle_compact_mode()

    def _toggle_stay_on_top(self, checked: Optional[bool] = None):
        """窗口置顶切换 (支持无参调用用于快捷键 T)"""
        if checked is None:
            checked = not self.btn_top.isChecked()
        set_seamless_stay_on_top(self, checked)
        self.stays_on_top = bool(checked)
        if self.btn_top.isChecked() != checked:
            self.btn_top.blockSignals(True)
            self.btn_top.setChecked(checked)
            self.btn_top.blockSignals(False)

        # 【置顶与磁吸严格互斥】(对齐 ATS SSOT):
        # 置顶开启时，完全禁用磁吸贴边与折叠，保持自由悬浮；置顶关闭时恢复磁吸贴边
        if checked:
            if hasattr(self, 'snap_timer') and self.snap_timer:
                self.snap_timer.stop()
            if hasattr(self, 'hover_timer') and self.hover_timer:
                self.hover_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            if getattr(self, 'is_hidden_state', False):
                self.show_normal_position()
            self.setWindowOpacity(1.0)
        else:
            if hasattr(self, 'hover_timer') and self.hover_timer and self.anchor_edge:
                self.hover_timer.start()

        self._save_current_filter_and_view_state()

    def _normalize_mode_name(self, name: Optional[str]) -> str:
        """智能规范化策略模式名称，容错 Unicode/Emoji 及空格波动"""
        if not name or not isinstance(name, str):
            return "🎯 经典标准"
        name_clean = name.strip()
        if "起爆" in name_clean or "极速" in name_clean:
            return "🚀 极速起爆"
        if "通道" in name_clean or "低吸" in name_clean:
            return "💎 稳健通道低吸"
        if "自定义" in name_clean:
            return "⚙️ 自定义"
        if "经典" in name_clean or "标准" in name_clean:
            return "🎯 经典标准"
        return name_clean

    def _init_filter_config(self):
        """初始化底层筛选策略配置并恢复持久化状态"""
        raw_saved_mode = load_config_node("sector_miner_filter_mode", "🎯 经典标准")
        saved_mode = self._normalize_mode_name(raw_saved_mode)
        custom_dict = load_config_node("sector_miner_custom_filter", {})

        if saved_mode in PRESET_FILTER_MODES:
            self._current_filter_config = PRESET_FILTER_MODES[saved_mode]
        elif saved_mode == "⚙️ 自定义":
            if custom_dict and isinstance(custom_dict, dict):
                self._current_filter_config = PullbackFilterConfig.from_dict(custom_dict)
            else:
                self._current_filter_config = PullbackFilterConfig.from_dict(PRESET_FILTER_MODES["🎯 经典标准"].to_dict())
            self._current_filter_config.mode_name = "⚙️ 自定义"
        else:
            self._current_filter_config = PRESET_FILTER_MODES["🎯 经典标准"]
            saved_mode = "🎯 经典标准"

        # 设置下拉框选中项 (阻塞信号防止重复触发)
        self.combo_filter_mode.blockSignals(True)
        idx = self.combo_filter_mode.findText(saved_mode)
        if idx >= 0:
            self.combo_filter_mode.setCurrentIndex(idx)
        else:
            best_idx = 0
            for i in range(self.combo_filter_mode.count()):
                if self._normalize_mode_name(self.combo_filter_mode.itemText(i)) == saved_mode:
                    best_idx = i
                    break
            self.combo_filter_mode.setCurrentIndex(best_idx)
        self.combo_filter_mode.blockSignals(False)

        # 自动刷新状态恢复
        saved_auto = load_config_node("sector_miner_auto_refresh", False)
        if saved_auto:
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(True)
            self.chk_auto.blockSignals(False)
            sec = self._get_selected_interval_sec()
            self.refresh_timer.start(int(sec * 1000))

        self._update_mode_summary()

    def _save_current_filter_and_view_state(self):
        """线程安全、全量原子保存当前策略模式、自定义参数、刷新状态与视图布局"""
        try:
            norm_geo = self.normal_geometry if (getattr(self, 'is_hidden_state', False) and self.normal_geometry) else self.geometry()
            payload = {
                "sector_miner_filter_mode": cur_mode,
                "sector_miner_view_mode": "compact" if self._is_compact_mode else "full",
                "sector_miner_auto_refresh": self.chk_auto.isChecked(),
                "sector_miner_refresh_interval": self._get_selected_interval_sec(),
                "sector_miner_anchor_edge": None if self.stays_on_top else self.anchor_edge,
                "sector_miner_is_hidden": False if self.stays_on_top else getattr(self, 'is_hidden_state', False),
                "sector_miner_stays_on_top": self.stays_on_top,
                "sector_miner_normal_geo": [norm_geo.x(), norm_geo.y(), norm_geo.width(), norm_geo.height()],
            }
            if self._current_filter_config and self._current_filter_config.mode_name == "⚙️ 自定义":
                payload["sector_miner_custom_filter"] = self._current_filter_config.to_dict()

            geo = self.geometry()
            geo_list = [geo.x(), geo.y(), geo.width(), geo.height()]
            if self._is_compact_mode:
                payload["sector_miner_compact_geo"] = geo_list
            else:
                payload["sector_miner_full_geo"] = geo_list

            from ats.ui.styles import save_config_nodes
            save_config_nodes(payload)
        except Exception as e:
            logger.debug(f"保存策略与视图状态异常: {e}")

    def _update_mode_summary(self):
        """更新策略参数简要说明"""
        cfg = self._current_filter_config
        ch_text = "+通道" if cfg.require_channel_supp else ("优先通道" if cfg.prefer_channel_supp else "")
        ch_suffix = f" | {ch_text}" if ch_text else ""
        self.lbl_mode_summary.setText(
            f"MA20:[{cfg.dff2_min:+.1f}%,{cfg.dff2_max:+.1f}%] | 收阳:>={cfg.min_eval_pct:.1f}% | 量比:>={cfg.min_vol_ratio:.2f} | 换手:>={cfg.min_turnover:.1f}%{ch_suffix}"
        )

    def _on_filter_mode_changed(self, index: int):
        """切换策略模式"""
        raw_mode = self.combo_filter_mode.currentText()
        mode_name = self._normalize_mode_name(raw_mode)
        if mode_name in PRESET_FILTER_MODES:
            self._current_filter_config = PRESET_FILTER_MODES[mode_name]
        elif mode_name == "⚙️ 自定义":
            custom_dict = load_config_node("sector_miner_custom_filter", {})
            if custom_dict and isinstance(custom_dict, dict):
                self._current_filter_config = PullbackFilterConfig.from_dict(custom_dict)
            else:
                self._current_filter_config = PullbackFilterConfig.from_dict(PRESET_FILTER_MODES["🎯 经典标准"].to_dict())
            self._current_filter_config.mode_name = "⚙️ 自定义"

        self._update_mode_summary()
        self._save_current_filter_and_view_state()
        self.trigger_scan()

    def _open_filter_config_dialog(self):
        """弹出自定义参数微调窗口"""
        dlg = PullbackConfigDialog(self._current_filter_config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dlg.get_config()
            self._current_filter_config = new_cfg

            self.combo_filter_mode.blockSignals(True)
            idx = self.combo_filter_mode.findText(new_cfg.mode_name)
            if idx >= 0:
                self.combo_filter_mode.setCurrentIndex(idx)
            else:
                idx_custom = self.combo_filter_mode.findText("⚙️ 自定义")
                if idx_custom >= 0:
                    self.combo_filter_mode.setCurrentIndex(idx_custom)
            self.combo_filter_mode.blockSignals(False)

            self._update_mode_summary()
            self._save_current_filter_and_view_state()
            self.trigger_scan()

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

        self._worker = MinerWorkerThread(self.current_df, filter_config=self._current_filter_config, parent=self)
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

        self._last_sectors = sectors
        self._all_candidates = candidates
        self._render_sectors_table(sectors)
        self._apply_candidate_filter()

        is_post_market = bool(report.get("is_post_market", False))
        mode_prefix = "🌙 [盘后复盘·以最新收盘日(per1d)为基准]" if is_post_market else "🔥 [盘中实时模式]"
        filter_mode = report.get("filter_mode", self._current_filter_config.mode_name)
        self.status_bar.setText(
            f"✅ 扫描完成 | 策略: [{filter_mode}] | {mode_prefix} 全市场 {total_stocks} 只标的 | "
            f"锁定 {len(sectors)} 大主线板块 | 挖掘出 {len(candidates)} 只回踩启动标的 | 耗时 {cost_ms}ms"
        )

        # 动态更新下半区第 5 列表头：盘后显示 涨幅 per1d，盘中显示 涨幅 dff
        pct_col_name = "涨幅 per1d" if is_post_market else "涨幅 dff"
        self.candidates_table.setHorizontalHeaderItem(5, QTableWidgetItem(pct_col_name))

    def _render_sectors_table(self, sectors: List[Dict[str, Any]]):
        """渲染上半区板块表格"""
        self.sectors_table.setSortingEnabled(False)
        self.sectors_table.setRowCount(len(sectors))
        fav_mgr = GlobalFavoriteManager()

        for row, s in enumerate(sectors):
            s_name = s.get("name", "")
            grade = s.get("grade", "")
            score = float(s.get("strength_score", 0.0))
            avg_pct = float(s.get("avg_pct", 0.0))
            pio_cnt = int(s.get("pioneer_count", 0))
            leader = f"{s.get('leader_name', '')} ({s.get('leader_pct', 0.0):+.1f}%)"
            amt_yi = float(s.get("total_amt_yi", 0.0))
            vr = float(s.get("vol_ratio", 1.0))
            l_code = s.get("leader_code", "")

            # 判断板块是否重点关注
            is_sec_fav = fav_mgr.is_favorite_sector(s_name)
            display_name = f"⭐ {s_name}" if is_sec_fav else s_name

            # 0: 板块名称
            item_name = QTableWidgetItem(display_name)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            if is_sec_fav:
                item_name.setForeground(QBrush(QColor("#ffd700")))
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

            # 5: 领涨先锋 (存入 leader_code 与 leader_name 便于单击/双击自动联动)
            l_name = s.get('leader_name', '')
            l_pct = float(s.get('leader_pct', 0.0))
            l_type = s.get('leader_type', '领涨龙头')
            l_amt = float(s.get('leader_amt_yi', 0.0))
            l_vr = float(s.get('leader_vr', 1.0))
            item_leader = QTableWidgetItem(leader)
            item_leader.setData(Qt.ItemDataRole.UserRole, l_code)
            item_leader.setData(Qt.ItemDataRole.UserRole + 1, l_name)
            item_leader.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_leader.setForeground(QBrush(QColor("#ffcc66")))
            tip_lines = [
                f"👉 单击直接联动领涨龙头: {l_name} ({l_code})",
                f"👑 动能画像: {l_type} | 涨幅: {l_pct:+.2f}%"
            ]
            if l_amt > 0:
                tip_lines.append(f"💰 资金成交: {l_amt:.1f} 亿 | 盘中量比: {l_vr:.2f}")
            tip_lines.append("⚡ 盘中随实时资金动能竞争与更替 | 双击全终端联动")
            item_leader.setToolTip("\n".join(tip_lines))
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
        fav_mgr = GlobalFavoriteManager()

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

            is_stock_fav = fav_mgr.is_favorite_stock(code)

            # 0: 代码
            it_code = QTableWidgetItem(code)
            it_code.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_stock_fav:
                it_code.setForeground(QBrush(QColor("#ffd700")))
            self.candidates_table.setItem(row, 0, it_code)

            # 1: 名称 (重点关注加 ⭐ 徽章)
            disp_name = f"⭐ {name}" if is_stock_fav else name
            it_name = QTableWidgetItem(disp_name)
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_name.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            if is_stock_fav:
                it_name.setForeground(QBrush(QColor("#ffd700")))
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

            # 5: 涨幅
            pct_c = QColor(COLOR_UP) if pct > 0 else (QColor(COLOR_DOWN) if pct < 0 else QColor("#cccccc"))
            it_pct = NumericTableWidgetItem(f"{pct:+.2f}%", pct)
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_pct.setForeground(QBrush(pct_c))
            self.candidates_table.setItem(row, 5, it_pct)

            # 6: 距离MA20 dff2
            it_dff2 = NumericTableWidgetItem(f"{dff2:+.2f}%", dff2)
            it_dff2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def _resolve_leader_code_and_name(self, row: int) -> Tuple[str, str]:
        """从板块表格第 5 列解析领涨龙头代码与名称 (带多重保底)"""
        leader_item = self.sectors_table.item(row, 5)
        if not leader_item:
            return "", ""
        l_code = str(leader_item.data(Qt.ItemDataRole.UserRole) or "").strip()
        l_name = str(leader_item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
        raw_text = leader_item.text().strip()
        if not l_name and raw_text:
            l_name = raw_text.split('(')[0].strip()

        # 保底 1: 若 l_code 为空，从文本中正则提取纯 6 位数字代码
        if not l_code and raw_text:
            import re
            m = re.search(r'\b(\d{6})\b', raw_text)
            if m:
                l_code = m.group(1)

        # 保底 2: 若仍为空且存在 current_df，根据名称反查代码
        if not l_code and l_name and self.current_df is not None and not self.current_df.empty:
            try:
                if 'name' in self.current_df.columns:
                    matched = self.current_df[self.current_df['name'] == l_name]
                    if not matched.empty:
                        l_code = str(matched.index[0])
            except Exception:
                pass

        return l_code, l_name

    def _on_sector_row_clicked(self, item: QTableWidgetItem):
        """
        点击板块表格行：
        1. 若点击第 0 列板块名称且已处于锁定状态：支持再次点击反选取消恢复全部主线；
        2. 若点击其他列或切换到不同板块：单选锁定该板块联动下半区，并自动联动该主线领涨先锋龙头股票。
        """
        if not item:
            return
        row = item.row()
        col = item.column()
        sec_item = self.sectors_table.item(row, 0)
        if not sec_item:
            return
        raw_text = sec_item.text().strip()
        sec_name = raw_text.replace("⭐", "").strip()

        # 点击已选中的第 0 列（名称）：反选取消，恢复显示全部主线
        if col == 0 and self._selected_sector == sec_name:
            self._clear_sector_filter()
            return

        # 锁定当前板块并联动下半区
        if self._selected_sector != sec_name:
            self._set_selected_sector(sec_name)

        # 自动联动领涨先锋龙头股票 (广播通达信/同花顺/Visualizer)
        leader_code, leader_name = self._resolve_leader_code_and_name(row)
        if leader_code:
            self._broadcast_link_stock(leader_code, leader_name)
            self.status_bar.setText(f"⚡ 已自动联动【{sec_name}】领涨先锋龙头: {leader_name} ({leader_code})")

    def eventFilter(self, watched, event):
        """事件过滤器：回车或空格直接全终端联动龙头股票"""
        if watched == self.sectors_table and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                row = self.sectors_table.currentRow()
                if row >= 0:
                    leader_code, leader_name = self._resolve_leader_code_and_name(row)
                    if leader_code:
                        self._broadcast_link_stock(leader_code, leader_name)
                        return True
        return super().eventFilter(watched, event)

    def _on_sector_current_changed(self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]):
        """键盘上下键或光标移动板块行，即时联动下半区回踩跟进池与领涨龙头"""
        if not current:
            return
        if previous is not None and previous.row() == current.row() and previous.tableWidget() == current.tableWidget():
            return
        row = current.row()
        sec_item = self.sectors_table.item(row, 0)
        if sec_item:
            sec_name = sec_item.text().replace("⭐", "").strip()
            self._set_selected_sector(sec_name)
            leader_code, leader_name = self._resolve_leader_code_and_name(row)
            if leader_code:
                self._broadcast_link_stock(leader_code, leader_name)

    def _set_selected_sector(self, sec_name: str):
        """设置当前选中的主线板块并过滤下半区"""
        self._selected_sector = sec_name
        self.lbl_cand_title.setText(f"🎯 主线【{self._selected_sector}】· 回踩确认启动标的")
        self.btn_show_all.setText(f"✕ 显示全部主线 (当前: {self._selected_sector})")
        self.btn_show_all.setStyleSheet("color: #ffd700; background: #2a2a35; border: 1px solid #aa8800; border-radius: 3px; padding: 2px 8px; font-weight: bold;")
        self._apply_candidate_filter()
        self.status_bar.setText(f"🔍 已锁定主线板块【{sec_name}】，下半区展示相关回踩启动标的")

    def _clear_sector_filter(self):
        """清空板块过滤，显示全部主线"""
        self._selected_sector = None
        self.lbl_cand_title.setText("🎯 实际资金主线·回踩确认启动跟进池 (全部主线)")
        self.btn_show_all.setText("显示全部主线")
        self.btn_show_all.setStyleSheet("color: #88bbff; background: transparent; border: 1px solid #446688; border-radius: 3px; padding: 2px 8px;")
        self.sectors_table.clearSelection()
        self.sectors_table.setCurrentCell(-1, -1)
        self._apply_candidate_filter()
        self.status_bar.setText("🌐 已恢复显示全部主线板块的回踩启动标的")

    def _on_sector_double_clicked(self, item: QTableWidgetItem):
        """双击板块行：若点领涨龙头直接联动龙头，否则联动可视化端筛选板块"""
        row = item.row()
        col = item.column()
        sec_item = self.sectors_table.item(row, 0)
        raw_sec = sec_item.text().strip() if sec_item else ""
        sec_name = raw_sec.replace("⭐", "").strip()

        # 双击第 5 列领涨先锋龙头：直接联动龙头股票 (强制执行)
        if col == 5:
            leader_code, leader_name = self._resolve_leader_code_and_name(row)
            if leader_code:
                self._broadcast_link_stock(leader_code, leader_name, force=True)
                return

        # 双击其他列：联动可视化端过滤板块
        if sec_name:
            self._link_sector_to_visualizer(sec_name)

    def _link_sector_to_visualizer(self, sec_name: str):
        """向可视化器联动板块过滤"""
        query_str = f'category.str.contains("{sec_name}")'
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        if parent_win and hasattr(parent_win, "cat_filter_input"):
            try:
                parent_win.cat_filter_input.setCurrentText(query_str)
                if hasattr(parent_win, "_on_cat_filter_apply"):
                    parent_win._on_cat_filter_apply()
                elif hasattr(parent_win, "on_cat_filter_change"):
                    parent_win.on_cat_filter_change(query_str)
                self.status_bar.setText(f"🔄 已联动可视化看板过滤板块: {sec_name}")
                return
            except Exception:
                pass

        # 异步 TCP 26668 指令
        import socket, threading
        def _send_query():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    s.connect(('127.0.0.1', 26668))
                    msg = f"QUERY|{query_str}"
                    s.sendall(msg.encode("utf-8"))
            except Exception:
                pass
        threading.Thread(target=_send_query, daemon=True, name="SectorLinkWorker").start()
        QApplication.clipboard().setText(query_str)
        self.status_bar.setText(f"📋 已联动板块并复制查询表达式: {query_str}")

    def _on_sector_context_menu(self, pos: QPoint):
        """上半区板块右键菜单"""
        item = self.sectors_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        sec_item = self.sectors_table.item(row, 0)
        if not sec_item:
            return
        raw_sec = sec_item.text().strip()
        sec = raw_sec.replace("⭐", "").strip()
        leader_code, leader_text = self._resolve_leader_code_and_name(row)

        fav_mgr = GlobalFavoriteManager()
        is_fav = fav_mgr.is_favorite_sector(sec)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)

        act_filter = menu.addAction(f"🔍 联动可视化器过滤板块: {sec}")
        act_link_leader = menu.addAction(f"📈 联动领涨先锋: {leader_text}") if leader_code else None
        act_pipe_leader = menu.addAction(f"⚡ 发送领涨先锋到异动联动: {leader_text}") if leader_code else None

        menu.addSeparator()
        act_dna_sec = menu.addAction(f"🧬 对【{sec}】回踩标的执行 DNA 审核")
        fav_label = f"❌ 取消重点关注板块 ({sec})" if is_fav else f"⭐ 设为重点关注板块 ({sec})"
        act_fav_sec = menu.addAction(fav_label)

        menu.addSeparator()
        act_copy_sec = menu.addAction(f"📋 复制板块名称 ({sec})")

        chosen = menu.exec(self.sectors_table.viewport().mapToGlobal(pos))
        if chosen == act_filter:
            self._link_sector_to_visualizer(sec)
        elif act_link_leader and chosen == act_link_leader:
            self._broadcast_link_stock(leader_code, leader_text, force=True)
        elif act_pipe_leader and chosen == act_pipe_leader:
            send_to_linkage(leader_code, leader_text, self)
            self.status_bar.setText(f"⚡ 已将领涨先锋发送到异动联动: {leader_text} ({leader_code})")
        elif chosen == act_dna_sec:
            self._selected_sector = sec
            self._apply_candidate_filter()
            self._run_dna_audit_selected()
        elif chosen == act_fav_sec:
            fav_mgr.toggle_favorite_sector(sec)
            self.status_bar.setText(f"⭐ 已更新重点关注板块: {sec}")
            self._render_sectors_table(self._last_sectors)
        elif chosen == act_copy_sec:
            QApplication.clipboard().setText(sec)
            self.status_bar.setText(f"📋 已复制板块名称: {sec}")

    def _on_candidate_clicked(self, item: QTableWidgetItem):
        """单击候选标的行，即时跨终端广播联动"""
        if not item:
            return
        self._trigger_candidate_link_by_row(item.row())

    def _on_candidate_current_changed(self, current: Optional[QTableWidgetItem], previous: Optional[QTableWidgetItem]):
        """光标移动（键盘上下键或鼠标选行切换），防抖即时联动"""
        if not current:
            return
        if previous is not None and previous.row() == current.row():
            return
        self._trigger_candidate_link_by_row(current.row())

    def _trigger_candidate_link_by_row(self, row: int):
        """根据候选行号提取股票信息并广播联动"""
        code_item = self.candidates_table.item(row, 0)
        name_item = self.candidates_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        raw_name = name_item.text().strip() if name_item else ""
        name = raw_name.replace("⭐", "").strip()
        self._broadcast_link_stock(code, name)

    def _on_candidate_double_clicked(self, item: QTableWidgetItem):
        """双击下半区候选标的，跨软件/全生态广播联动"""
        row = item.row()
        code_item = self.candidates_table.item(row, 0)
        name_item = self.candidates_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        raw_name = name_item.text().strip() if name_item else ""
        name = raw_name.replace("⭐", "").strip()
        self._broadcast_link_stock(code, name, force=True)

    def _broadcast_link_stock(self, code: str, name: str = "", date: Optional[str] = None, force: bool = False):
        """向本地可视化终端、主系统窗口与外部行情终端多通道广播联动 (SSOT)"""
        code_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
        if not code_clean:
            return

        # 0. 遵循系统底层联动逻辑：相同的 code (且日期一致) 绝不重复触发外部物理联动 (除非 force=True)
        last_code = getattr(self, "_last_linked_code", None)
        last_date = getattr(self, "_last_linked_date", None)
        now = time.time()
        if not force and last_code == code_clean and last_date == date:
            return
        self._last_linked_code = code_clean
        self._last_linked_time = now
        self._last_linked_date = date

        # 发射 Qt 信号通知外部监听
        self.code_clicked.emit(code_clean)

        # 1. 单通道分发机制：优先交由宿主主窗口 (ATSMainWindow) 统一管理分发
        # 外部终端 (TDX/THS) 与 Visualizer 严格受控于主界面统一逻辑与开关，绝不产生二次重复轰炸
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        if parent_win:
            if hasattr(parent_win, "link_stock"):
                try:
                    parent_win.link_stock(code_clean, name, date=date, force=force)
                except TypeError:
                    try:
                        parent_win.link_stock(code_clean, name, date=date)
                    except TypeError:
                        parent_win.link_stock(code_clean, name)
                self.status_bar.setText(f"⚡ 已联动行情标的: {name} ({code_clean})")
                return
            elif hasattr(parent_win, "load_stock_by_code"):
                try:
                    parent_win.load_stock_by_code(code_clean, name=name)
                    self.status_bar.setText(f"⚡ 已联动行情标的: {name} ({code_clean})")
                    return
                except Exception as e:
                    logger.debug(f"Parent load_stock_by_code failed: {e}")

        # 2. 若 parent 不是主窗口，尝试从全局 QApplication 获取 ATSMainWindow 统一分发
        try:
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, "main_window") and isinstance(app.main_window, ATSMainWindow):
                try:
                    app.main_window.link_stock(code_clean, name, date=date, force=force)
                except TypeError:
                    try:
                        app.main_window.link_stock(code_clean, name, date=date)
                    except TypeError:
                        app.main_window.link_stock(code_clean, name)
                self.status_bar.setText(f"⚡ 已联动行情标的: {name} ({code_clean})")
                return
        except Exception:
            pass

        # 3. 兜底保护：脱离 ATS 独立运行场景，直接向 trade_visualizer_qt6 发送 socket 指令，并推送 TDX/THS
        import socket, threading
        def _send_vis():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    s.connect(('127.0.0.1', 26668))
                    msg = f"CODE|{code_clean}"
                    s.sendall(msg.encode("utf-8"))
            except Exception:
                pass
        threading.Thread(target=_send_vis, daemon=True, name="VisLinkWorker").start()

        try:
            from linkage_service import get_link_manager
            mgr = get_link_manager()
            if mgr:
                mgr.push(code_clean, flags={'tdx': True, 'ths': True, 'dfcf': False})
        except Exception:
            pass
        try:
            from JohnsonUtil import commonTips as cct
            cct.to_toptdx(code_clean)
        except Exception:
            pass

        self.status_bar.setText(f"⚡ 已联动行情标的: {name} ({code_clean})")

    def _open_sbc_chart(self, code: str):
        """打开 SBC 独立分时图"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code)
        except Exception as e:
            logger.debug(f"Open SBC chart error: {e}")

    def _toggle_favorite_stock(self, code: str, name: str = ""):
        """切换股票重点关注状态"""
        try:
            fav_mgr = GlobalFavoriteManager()
            is_now_fav = fav_mgr.toggle_favorite_stock(str(code).strip())
            act_text = "已加入重点关注" if is_now_fav else "已从重点关注移除"
            self.status_bar.setText(f"⭐ {act_text}: {name or code} ({code})")
            self._apply_candidate_filter()
        except Exception as e:
            logger.debug(f"Toggle favorite stock error: {e}")

    def _on_candidate_context_menu(self, pos: QPoint):
        """下半区候选标的右键菜单"""
        item = self.candidates_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_it = self.candidates_table.item(row, 0)
        name_it = self.candidates_table.item(row, 1)
        sec_it = self.candidates_table.item(row, 2)
        reason_it = self.candidates_table.item(row, 12)
        if not code_it or not name_it:
            return

        code = code_it.text().strip()
        raw_name = name_it.text().strip()
        name = raw_name.replace("⭐", "").strip()
        sec = sec_it.text().strip() if sec_it else ""
        reason = reason_it.text().strip() if reason_it else ""

        fav_mgr = GlobalFavoriteManager()
        is_fav = fav_mgr.is_favorite_stock(code)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)

        act_link = menu.addAction(f"📈 联动行情: {name} ({code})")
        act_pipe = menu.addAction(f"⚡ 发送到异动联动: {name} ({code})")
        act_sbc = menu.addAction(f"📊 打开 SBC 独立分时走势 ({code})")
        act_dna = menu.addAction(f"🧬 DNA 专项审核 (Alt+W)")
        menu.addSeparator()

        fav_label = f"❌ 取消重点关注 ({code})" if is_fav else f"⭐ 设为重点关注 ({code})"
        act_fav = menu.addAction(fav_label)

        menu.addSeparator()
        act_copy_code = menu.addAction(f"📋 复制股票代码 ({code})")
        act_copy_sec = menu.addAction(f"📋 复制主线板块 ({sec})")
        act_copy_row = menu.addAction("📋 复制本行决策理由")

        chosen = menu.exec(self.candidates_table.viewport().mapToGlobal(pos))
        if chosen == act_link:
            self._broadcast_link_stock(code, name, force=True)
        elif chosen == act_pipe:
            send_to_linkage(code, name, self)
            self.status_bar.setText(f"⚡ 已发送到异动联动: {name} ({code})")
        elif chosen == act_sbc:
            self._open_sbc_chart(code)
        elif chosen == act_dna:
            self._run_dna_audit_selected()
        elif chosen == act_fav:
            self._toggle_favorite_stock(code, name)
        elif chosen == act_copy_code:
            QApplication.clipboard().setText(code)
            self.status_bar.setText(f"📋 已复制股票代码: {code}")
        elif chosen == act_copy_sec:
            QApplication.clipboard().setText(sec)
            self.status_bar.setText(f"📋 已复制主线板块: {sec}")
        elif chosen == act_copy_row:
            QApplication.clipboard().setText(f"{code} {name} [{sec}]: {reason}")
            self.status_bar.setText(f"📋 已复制决策理由: {name} ({code})")

    def _run_dna_audit_selected(self):
        """对选中的候选标的执行 DNA 专项审核 (支持单选、多选与批量向下20只)"""
        rows = self.candidates_table.rowCount()
        if rows == 0:
            return

        sel_rows = sorted(set(i.row() for i in self.candidates_table.selectedItems()))
        target = []
        if len(sel_rows) > 1:
            for r in sel_rows[:50]:
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            for r in range(start, min(start + 20, rows)):
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))
        else:
            for r in range(min(20, rows)):
                c_it = self.candidates_table.item(r, 0)
                n_it = self.candidates_table.item(r, 1)
                if c_it and n_it:
                    c = c_it.text().strip()
                    n = n_it.text().replace("⭐", "").strip()
                    target.append((c, n))

        code_to_name = {c: n for c, n in target if c}
        if not code_to_name:
            return

        self.status_bar.setText(f"🧬 正在对 {len(code_to_name)} 只回踩启动标的执行 DNA 专项审核...")
        QApplication.processEvents()

        # 1. 优先尝试主应用程序接口 (Tk / ATS 统一审计服务)
        parent_win = getattr(self, '_parent_window', None) or self.parent()
        main_app = getattr(parent_win, 'parent_app', None) or getattr(self.window(), 'parent_app', None)
        if not main_app:
            main_app = getattr(QApplication.instance(), 'parent_app', None)
        if main_app and hasattr(main_app, '_run_dna_audit_batch'):
            if hasattr(main_app, 'tk_dispatch_queue'):
                _cn = dict(code_to_name)
                main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
            else:
                main_app._run_dna_audit_batch(code_to_name)
            self.status_bar.setText(f"✅ 已向主控中心派发 DNA 审计任务 ({len(code_to_name)} 只标的)")
            return

        win = self.window()
        if hasattr(win, '_run_dna_audit_batch') and win is not self:
            win._run_dna_audit_batch(code_to_name)
            self.status_bar.setText(f"✅ 已向宿主窗口派发 DNA 审计任务 ({len(code_to_name)} 只标的)")
            return

        # 2. 独立 PyQt6 优雅降级模式：本地直接生成并调起 QtDnaAuditReportWindow
        try:
            from backtest_feature_auditor import audit_multiple_codes
            from ats.ui.multi_period_dialog import QtDnaAuditReportWindow
            from PyQt6.QtCore import Qt as _Qt
            QApplication.setOverrideCursor(_Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            
            period_data = self.current_df
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=None,
                code_to_name=code_to_name,
                progress_callback=None,
                resample='d',
                period_data=period_data
            )
            if summaries:
                self._dna_audit_win = QtDnaAuditReportWindow(
                    summaries, parent=self, end_date=None, resample='d'
                )
                self._dna_audit_win.show()
                self.status_bar.setText(f"✅ DNA 专项审核已完成，共生成 {len(summaries)} 份研报")
            else:
                self.status_bar.setText("⚠️ 未生成 DNA 审计有效数据")
        except Exception as e:
            logger.error(f"DNA audit local fallback error: {e}", exc_info=True)
            self.status_bar.setText(f"❌ DNA 审计异常: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _get_global_ats_interval(self) -> float:
        """获取 ATS 全局统一的 TDX 刷新间隔基准 (SSOT: cct.ats_tdx_interval)"""
        try:
            val = getattr(cct, 'ats_tdx_interval', 5.0)
            return max(1.0, float(val if val is not None else 5.0))
        except Exception:
            return 5.0

    def _get_selected_interval_sec(self) -> float:
        """获取当前下拉框选中的自动刷新秒数 (浮点数支持)"""
        try:
            txt = self.combo_interval.currentText().strip()
            import re
            m = re.search(r"(\d+(\.\d+)?)", txt)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return self._get_global_ats_interval()

    def sync_with_global_interval(self, new_interval: Optional[float] = None) -> float:
        """动态对齐全局 cct.ats_tdx_interval 基准，同步刷新下拉框与定时器"""
        try:
            base_sec = self._get_global_ats_interval() if new_interval is None else float(new_interval)
            best_idx = -1
            min_diff = 999.0
            for i in range(self.combo_interval.count()):
                txt = self.combo_interval.itemText(i)
                import re
                m = re.search(r"(\d+(\.\d+)?)", txt)
                if m:
                    val = float(m.group(1))
                    diff = abs(val - base_sec)
                    if diff < min_diff:
                        min_diff = diff
                        best_idx = i

            if best_idx >= 0 and best_idx != self.combo_interval.currentIndex():
                self.combo_interval.blockSignals(True)
                self.combo_interval.setCurrentIndex(best_idx)
                self.combo_interval.blockSignals(False)

            if self.chk_auto.isChecked():
                sec = self._get_selected_interval_sec()
                self.refresh_timer.start(int(sec * 1000))
            return base_sec
        except Exception as e:
            logger.debug(f"[sync_with_global_interval] error: {e}")
            return 5.0

    def _on_auto_toggled(self, checked: bool):
        """开关自动刷新 (以 cct.ats_tdx_interval 为基准，支持工作台按需独立微调)"""
        if checked:
            sec = self._get_selected_interval_sec()
            base_sec = self._get_global_ats_interval()
            self.refresh_timer.start(int(sec * 1000))
            sync_note = " (与系统全局基准同步)" if abs(sec - base_sec) < 0.1 else f" (工作台独立微调，系统基准: {base_sec:g}s)"
            self.status_bar.setText(f"🔄 自动刷新已开启，每 {sec:g} 秒同步扫描一次{sync_note}.")
        else:
            self.refresh_timer.stop()
            self.status_bar.setText("⏸️ 自动刷新已暂停.")

    def _on_interval_changed(self, idx: int):
        """切换自动刷新间隔"""
        sec = self._get_selected_interval_sec()
        base_sec = self._get_global_ats_interval()
        sync_note = " (与系统全局基准同步)" if abs(sec - base_sec) < 0.1 else f" (工作台独立微调，系统基准: {base_sec:g}s)"
        if self.chk_auto.isChecked():
            self.refresh_timer.start(int(sec * 1000))
            self.status_bar.setText(f"🔄 自动刷新间隔已切换为 {sec:g} 秒{sync_note}.")

    def _on_auto_refresh(self):
        """自动定时刷新"""
        if self.isVisible():
            self.trigger_scan()

    def start_slide_animation(self, target_geo: QRect, target_opacity: float = 1.0, duration: int = 220, is_snap_feedback: bool = False):
        """高质感平滑缓动滑入与磁吸动效反馈 (对齐 DailyLimitUpDialog 与 DragonMonitor SSOT)"""
        if hasattr(self, 'anim_group') and self.anim_group:
            try:
                self.anim_group.stop()
            except Exception:
                pass

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
            self.opacity_anim.setKeyValueAt(0.5, 0.45)  # 磁吸贴边时瞬时透明度闪烁呼吸反馈
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        self._in_snap_action = True

        def on_finished():
            self._in_snap_action = False
            if getattr(self, "is_hidden_state", False):
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(target_opacity)
            self._save_current_filter_and_view_state()

        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def toggle_compact_mode(self, force_compact: Optional[bool] = None):
        """在【精简版样式 (Compact Mode)】与【全貌模式 (Full Mode)】之间平滑切换"""
        # 容错处理：若从 QPushButton.clicked 传入 bool 参数 (非显式调用)，忽略该参数执行取反切换
        if force_compact is not None and not isinstance(force_compact, bool):
            force_compact = None

        if force_compact is not None:
            new_mode = bool(force_compact)
        else:
            new_mode = not self._is_compact_mode

        if new_mode == self._is_compact_mode:
            return

        self._is_compact_mode = new_mode

        if self._is_compact_mode:
            # ── 1. 切换进入精简版样式 ──
            # 若正处于贴边隐藏状态，先恢复正常展示
            if getattr(self, "is_hidden_state", False):
                self.show_normal_position()

            # 记忆当前全貌尺寸与坐标
            self._full_geometry = self.geometry()

            # 隐藏全貌复杂控件，收起第二行
            self.lbl_title.setVisible(False)
            self.lbl_mode.setVisible(False)
            self.combo_filter_mode.setVisible(False)
            self.btn_config.setVisible(False)
            self.txt_filter.setVisible(False)
            self.combo_interval.setVisible(False)
            self.row2_widget.setVisible(False)
            self.lbl_compact_title.setVisible(True)

            # 按钮精炼以适配紧凑卡片宽度 (300~380px)
            self.btn_scan.setText("🚀 挖掘")
            self.chk_auto.setText("自动")
            self.btn_top.setText("📌")
            self.btn_close.setText("✕ 关闭")

            # 按钮文字与高亮切换为【🖥️ 恢复全貌 (M)】
            self.btn_compact.setText("🖥️ 恢复全貌 (M)")
            self.btn_compact.setStyleSheet("""
                QPushButton {
                    background-color: #1a3a60; color: #ffd700; border: 2px solid #ffd700;
                    border-radius: 4px; padding: 3px 6px; font-weight: bold;
                }
                QPushButton:hover { background-color: #234d7d; }
            """)
            self.btn_compact.setToolTip("当前处于精简盯盘卡片模式。点击一键恢复完整双表大工作台全貌 (快捷键 M)")

            # 表格列自适应展示尽量多的核心列信息 (dff, dff2, dff3, 量比等)
            self._adapt_compact_columns()

            # 放开最小尺寸并平滑调整为紧凑卡片
            self.setMinimumSize(300, 320)

            # 恢复保存的精简尺寸，若无则自适应平滑贴靠屏幕右侧黄金看盘位
            saved_compact_geo = load_config_node("sector_miner_compact_geo", None)
            if saved_compact_geo and len(saved_compact_geo) == 4:
                target_geo = QRect(*saved_compact_geo)
            else:
                screen = self.screen() or QApplication.primaryScreen()
                s_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                comp_w = 370
                comp_h = min(660, s_geo.height() - 80)
                comp_x = max(s_geo.left(), s_geo.right() - comp_w - 10)
                comp_y = s_geo.top() + 40
                target_geo = QRect(comp_x, comp_y, comp_w, comp_h)

            self.start_slide_animation(target_geo, 1.0, duration=220)
            self.normal_geometry = target_geo
            # 表格列自适应展示尽量多的核心列信息 (dff, dff2, dff3, 量比等)
            self._adapt_compact_columns(target_geo.width())

            # 【用户明确需求：精简模式不要直接自动置顶，置顶手动选择】
            # 完全保留用户当前的置顶设置，不再强制修改 self.btn_top

            self.status_bar.setText("🧲 精简盯盘模式: 点击【🖥️ 恢复全貌 (M)】或按 M 键还原.")
        else:
            # ── 2. 恢复全貌模式 ──
            # 若正处于贴边隐藏状态，先恢复正常展示
            if getattr(self, "is_hidden_state", False):
                self.show_normal_position()

            # 记忆当前精简尺寸
            self._compact_geometry = self.geometry()

            # 还原控件可见性与完整文案
            self.lbl_compact_title.setVisible(False)
            self.lbl_title.setVisible(True)
            self.btn_scan.setText("🚀 一键深度挖掘")
            self.chk_auto.setText("自动刷新")
            self.combo_interval.setVisible(True)
            self.lbl_mode.setVisible(True)
            self.combo_filter_mode.setVisible(True)
            self.btn_config.setVisible(True)
            self.txt_filter.setVisible(True)
            self.btn_top.setText("📌 置顶 (T)")
            self.btn_close.setText("✕ 关闭 (Esc)")
            self.row2_widget.setVisible(True)

            # 按钮文字还原
            self.btn_compact.setText("🧲 精简 (M)")
            self.btn_compact.setStyleSheet("""
                QPushButton {
                    background-color: #23354a; color: #aadcff; border: 1px solid #3d6ea8;
                    border-radius: 4px; padding: 3px 8px; font-weight: bold;
                }
                QPushButton:hover { background-color: #2d4562; color: #ffffff; }
            """)
            self.btn_compact.setToolTip("切换精简盯盘卡片模式 / 恢复全貌 (快捷键 M)\n支持屏幕贴边磁吸吸附、独立悬浮置顶盯盘")

            # 表格所有列全量展现
            for c in range(self.sectors_table.columnCount()):
                self.sectors_table.setColumnHidden(c, False)
            for c in range(self.candidates_table.columnCount()):
                self.candidates_table.setColumnHidden(c, False)

            # 恢复全貌最小尺寸
            self.setMinimumSize(680, 420)

            # 恢复全貌几何位置
            if self._full_geometry:
                target_geo = self._full_geometry
            else:
                saved_full_geo = load_config_node("sector_miner_full_geo", None)
                if saved_full_geo and len(saved_full_geo) == 4:
                    target_geo = QRect(*saved_full_geo)
                else:
                    target_geo = QRect(self.x(), self.y(), 1180, 720)

            self.start_slide_animation(target_geo, 1.0, duration=220)
            self.normal_geometry = target_geo
            self.status_bar.setText("🖥️ 已恢复完整双表大工作台全貌.")

        self._save_current_filter_and_view_state()

    def resizeEvent(self, event):
        """窗口缩放事件：精简模式下自适应动态调整列展示"""
        super().resizeEvent(event)
        if getattr(self, '_is_compact_mode', False):
            self._adapt_compact_columns()

    def _adapt_compact_columns(self, target_width: Optional[int] = None):
        """精简模式下自适应窗口尺寸呈现尽量多的核心列信息 (dff, dff2, dff3, 量比等)"""
        if not getattr(self, '_is_compact_mode', False):
            return
        w = target_width if target_width is not None else self.width()

        # 1. 下半区候选表自适应列展示与紧凑列宽
        # 核心必显字段: 0(代码), 1(名称), 3(启动形态), 5(涨幅 dff), 6(距MA20 dff2), 7(长期 dff3), 9(量比)
        cand_visible = {0, 1, 3, 5, 6, 7, 9}
        if w >= 560:
            cand_visible.add(4)   # 综合得分
        if w >= 640:
            cand_visible.add(10)  # 建议买区
        if w >= 720:
            cand_visible.add(11)  # 止损位
        if w >= 800:
            cand_visible.add(8)   # 近3日时序
        if w >= 880:
            cand_visible.add(2)   # 所属主线

        for c in range(self.candidates_table.columnCount()):
            self.candidates_table.setColumnHidden(c, c not in cand_visible)

        self.candidates_table.setColumnWidth(0, 52)   # 代码
        self.candidates_table.setColumnWidth(1, 62)   # 名称
        self.candidates_table.setColumnWidth(3, 85)   # 启动形态
        self.candidates_table.setColumnWidth(5, 58)   # 涨幅 dff
        self.candidates_table.setColumnWidth(6, 68)   # 距MA20 dff2
        self.candidates_table.setColumnWidth(7, 65)   # 长期 dff3
        self.candidates_table.setColumnWidth(9, 48)   # 量比
        if 4 in cand_visible:
            self.candidates_table.setColumnWidth(4, 55)
        if 10 in cand_visible:
            self.candidates_table.setColumnWidth(10, 75)
        if 11 in cand_visible:
            self.candidates_table.setColumnWidth(11, 55)

        # 2. 上半区板块表自适应列展示与紧凑列宽
        # 核心必显字段: 0(板块名称), 3(板块均涨), 5(领涨先锋龙头)
        sec_visible = {0, 3, 5}
        if w >= 480:
            sec_visible.add(1)    # 资金评级
        if w >= 560:
            sec_visible.add(4)    # 冲锋前排数
        if w >= 640:
            sec_visible.add(6)    # 总成交额
        if w >= 720:
            sec_visible.add(2)    # 强度得分

        for c in range(self.sectors_table.columnCount()):
            self.sectors_table.setColumnHidden(c, c not in sec_visible)

        self.sectors_table.setColumnWidth(0, 90)   # 板块名称
        if 1 in sec_visible:
            self.sectors_table.setColumnWidth(1, 58) # 资金评级
        self.sectors_table.setColumnWidth(3, 58)   # 板块均涨
        if 4 in sec_visible:
            self.sectors_table.setColumnWidth(4, 52) # 冲锋数
        self.sectors_table.setColumnWidth(5, 120)  # 领涨先锋龙头
        if 6 in sec_visible:
            self.sectors_table.setColumnWidth(6, 65) # 总成交额

    def _detect_and_snap(self):
        """边缘磁吸贴齐检测：靠近屏幕边缘 (<25px) 自动贴边吸附并提供动效反馈 (对齐 ATS SSOT)"""
        # 【置顶与磁吸严格互斥】：置顶状态下完全禁用磁吸贴边功能，保持自由悬浮置顶
        if getattr(self, "stays_on_top", False) or getattr(self, "is_hidden_state", False):
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            if hasattr(self, 'snap_timer'):
                self.snap_timer.start(300)
            return

        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35  # 35px 舒适自然磁吸感应范围

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
            self.start_slide_animation(self.normal_geometry, 1.0, duration=180, is_snap_feedback=True)
            edge_desc = {"top": "顶部", "left": "左侧", "right": "右侧"}.get(edge, edge)
            self.status_bar.setText(f"🧲 窗口已平滑磁吸贴齐屏幕{edge_desc} (X:{target_x}, Y:{target_y})")
            # 仅在进入贴边后激活悬停检测
            if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
                self.hover_timer.start()
        else:
            self.anchor_edge = None
            self.normal_geometry = None
            # 脱离贴边进入屏幕常规区域，彻底停止悬停定时器，0 开销
            if hasattr(self, 'hover_timer') and self.hover_timer and self.hover_timer.isActive():
                self.hover_timer.stop()
        self._save_current_filter_and_view_state()

    def hide_to_edge(self):
        """贴边自动折叠隐藏为 5px 边缘感应条 (对齐 ATS SSOT)"""
        if getattr(self, "stays_on_top", False) or not self.anchor_edge or getattr(self, "is_hidden_state", False) or not self.normal_geometry:
            return

        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
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
        if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
            self.hover_timer.start()
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=250)

    def show_normal_position(self):
        """从边缘感应条平滑滑出展开 (对齐 ATS SSOT)"""
        if getattr(self, "is_hidden_state", False):
            self.is_hidden_state = False
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            self._last_show_time = time.time()
            self._has_hovered_since_show = False

            # 兜底恢复 normal_geometry 避免启动后为 None 导致无法滑出
            if not getattr(self, 'normal_geometry', None):
                w = self.width()
                h = self.height()
                screen = self.screen() or QApplication.primaryScreen()
                screen_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                if self.anchor_edge == "left":
                    self.normal_geometry = QRect(screen_geo.left(), self.y(), w, h)
                elif self.anchor_edge == "right":
                    self.normal_geometry = QRect(screen_geo.right() - w, self.y(), w, h)
                elif self.anchor_edge == "top":
                    self.normal_geometry = QRect(self.x(), screen_geo.top(), w, h)
                else:
                    self.normal_geometry = self.geometry()

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
        self._save_current_filter_and_view_state()

    def _check_hover(self):
        """鼠标悬停与移开检测 (对齐 ATS SSOT)"""
        # 【置顶与磁吸严格互斥】：置顶状态下不执行任何贴边或离开折叠检测，立即休眠
        if not self.isVisible() or getattr(self, "stays_on_top", False):
            if hasattr(self, 'hover_timer') and self.hover_timer and self.hover_timer.isActive():
                self.hover_timer.stop()
            return

        # 仅在有贴边锚定边缘或处于贴边隐藏状态时才执行悬浮检测，其余时刻 0 开销休眠
        if not self.anchor_edge and not getattr(self, "is_hidden_state", False):
            if hasattr(self, 'hover_timer') and self.hover_timer and self.hover_timer.isActive():
                self.hover_timer.stop()
            return

        # 滑动动画进行中直接短路，绝不中途打断动画或产生乱序闪烁
        if getattr(self, "_in_snap_action", False):
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

        if getattr(self, "is_hidden_state", False):
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
                    if self.leave_ticks >= 4:  # 移开 400ms 自动折叠
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        """窗口移动事件 (对齐 ATS SSOT)"""
        super().moveEvent(event)
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止触发磁吸贴边
        if getattr(self, "stays_on_top", False):
            if hasattr(self, 'snap_timer') and self.snap_timer:
                self.snap_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            return
        if not getattr(self, "is_hidden_state", False) and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            self.anchor_edge = None
            if hasattr(self, 'snap_timer'):
                self.snap_timer.start(300)

    def changeEvent(self, event):
        """窗体事件：激活时从隐藏边缘自动唤醒 (对齐 ATS SSOT)"""
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and getattr(self, 'is_hidden_state', False):
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

    def showEvent(self, event):
        """窗体显示事件"""
        super().showEvent(event)
        if (self.anchor_edge is not None or getattr(self, "is_hidden_state", False)) and not getattr(self, "stays_on_top", False):
            if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
                self.hover_timer.start()

    def hideEvent(self, event):
        """窗体隐藏事件"""
        if hasattr(self, 'hover_timer') and self.hover_timer and self.hover_timer.isActive():
            self.hover_timer.stop()
        if hasattr(self, 'snap_timer') and self.snap_timer and self.snap_timer.isActive():
            self.snap_timer.stop()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        """键盘事件：放行 Alt+R 专用于系统视窗轮转，支持 T 置顶，M 精简/全貌，F5 刷新，Alt+W 审核，Esc 退出"""
        modifiers = event.modifiers()
        key = event.key()

        # 🚀 绝对放行 Alt+R：专属于系统全局/底层 Tk 视窗轮转切换器，绝不消费/拦截！
        if key == Qt.Key.Key_R and (modifiers & Qt.KeyboardModifier.AltModifier):
            event.ignore()
            return

        # 🚀 支持 Esc 键快速关闭退出工作台
        if key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return

        # 🚀 支持 M 键快速切换精简/全貌模式 (兜底)
        if key == Qt.Key.Key_M and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self.toggle_compact_mode()
                event.accept()
                return

        if key == Qt.Key.Key_W and (modifiers & Qt.KeyboardModifier.AltModifier):
            self._run_dna_audit_selected()
            event.accept()
            return

        # 🚀 支持 T 键快速切换置顶 (兜底)
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self._toggle_stay_on_top()
                event.accept()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        """窗口关闭时全量原子持久化当前策略、自定义参数、刷新频率与视图几何"""
        self.refresh_timer.stop()
        if hasattr(self, 'snap_timer'):
            self.snap_timer.stop()
        if hasattr(self, 'hover_timer'):
            self.hover_timer.stop()
        self._save_current_filter_and_view_state()
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

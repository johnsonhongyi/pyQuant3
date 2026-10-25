# -*- coding: utf-8 -*-
"""ats/ui/fusion_ladder_dialog.py — 融合梯度监视器（所见即所得）。

三个页签对应三种"看得见"：
    1. 实时梯度：直接读 `logs/fusion_shadow/<day>.jsonl`，按选择日期加载，支持实盘与回补数据呈现；
    2. 按日回放：选历史交易日运行全天，不仅完成回测，更自动将有效信号回补持久化为影子流与上下文快照；
    3. 验收与复盘：填几只"走出来的答案"（如 688787,300296），看系统哪一天、几点、几级抓到。

设计约束（对齐 ATS 专业看板体系）：
    - 系统级独立顶层窗口 (super().__init__(None) 剥离 HWND Owner 从属，任务栏独立显示，支持自由最小化/最大化)；
    - 完整支持磁吸贴边功能 (35px 舒适感应贴边、平滑动画、移开 400ms 折叠隐藏至 5px 观察条、悬停 200ms 滑出展开)；
    - 磁吸与置顶互斥切换，快捷键 T 切换置顶，Esc 贴边折叠；
    - 完整补齐股票名称（name）列、当时现价（price）列与当时涨幅（pct%）列；
    - 所有列头均配备字典级 ToolTip 悬浮说明（RAR/位/接/意/环/MFE/MAE定义与好坏标准）；
    - 采用 NumericTableWidgetItem 支持所有列精准数值/文本升降序排序；
    - 完整联动：点击联动、键盘上下键移动联动 link_stock(code, name)；
    - 双击任意行秒开通达信同款 SBC 分时走势图 (open_sbc_chart_dialog)；
    - 标准 ATS 右键菜单（📈 查看分时图 / 🔍 个股详情 / ⭐ 关注 / 📋 复制）；
    - 全 Tab 极窄列模式 (Narrow Mode) 支持与列宽自动防抖持久化；
    - 回测即回补数据：选定日期跑完回放自动落盘 logs/fusion_shadow/{day}.jsonl 与 session_ctx/{day}.json。
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ats.fusion.adapter import today_str
from ats.fusion.names import name_of
from ats.fusion.panel import build_panel, render_panel
from ats.fusion.replay import DayReplay, ReplayConfig, render_focus, render_report
from ats.fusion.review import load_records, render_markdown, suggest_cuts, summarize
from ats.fusion.tracker import deploy_path
from ats.ui.styles import (
    NumericTableWidgetItem,
    load_config_node,
    save_config_node,
    set_seamless_stay_on_top,
)
from global_favorites import GlobalFavoriteManager
from tk_gui_modules.window_mixin import WINDOW_CONFIG_FILE, WindowMixin

logger = logging.getLogger(__name__)

_DARK_QSS = """
QWidget { background-color: #17171c; color: #d8d8e0; font-size: 9pt; }
QLabel { color: #b9b9c8; }
QCheckBox { color: #d8d8e0; spacing: 5px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #3a3a48; border-radius: 3px; background: #202028; }
QCheckBox::indicator:checked { background: #5a4b81; border-color: #a97bff; }
QPushButton {
    background-color: #24242e; color: #e6e6f0; border: 1px solid #3a3a48;
    border-radius: 3px; padding: 2px 8px; font-size: 8.5pt;
}
QPushButton:hover { background-color: #30303e; border-color: #5a5a72; }
QPushButton:disabled { color: #666677; border-color: #2c2c36; }
QComboBox, QLineEdit, QSpinBox {
    background-color: #202028; color: #e6e6f0; border: 1px solid #3a3a48;
    border-radius: 3px; padding: 2px 6px;
}
QTabWidget::pane { border: 1px solid #2c2c36; }
QTabBar::tab {
    background: #1d1d24; color: #9a9aac; padding: 4px 12px;
    border: 1px solid #2c2c36; border-bottom: none;
}
QTabBar::tab:selected { background: #2a2a36; color: #ffcc66; }
QTableWidget {
    background-color: #14141a; alternate-background-color: #191921;
    gridline-color: #26262f; color: #d8d8e0; border: none;
    selection-background-color: #2a3a5a; selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #23232d; color: #9fa4b8; border: none;
    border-right: 1px solid #2c2c36; border-bottom: 1px solid #2c2c36; padding: 3px 4px;
    font-weight: bold;
}
QProgressBar { border: 1px solid #2c2c36; border-radius: 3px; text-align: center; color: #cfcfda; }
QProgressBar::chunk { background-color: #3a6ea5; }
QTextBrowser { background-color: #14141a; border: 1px solid #2c2c36; }
QMenu {
    background-color: #202028; color: #e6e6f0; border: 1px solid #3a3a48; padding: 4px;
}
QMenu::item:selected { background-color: #38384a; color: #00ff88; }
"""

_TIER_COLORS = {
    4: QColor("#ff5c5c"),
    3: QColor("#ffa64d"),
    2: QColor("#ffd75e"),
    1: QColor("#7fb3d5"),
    0: QColor("#6b6b7b"),
}

# 💡 专业列头 ToolTip 说明字典
HEADER_TOOLTIPS: Dict[str, str] = {
    "时间": "【时间】信号触发或更新的分时时点。\n• 09:30~10:00: 早盘先手爆发力最强；\n• 10:30 以后: 随着时间推移先手衰减，追高风险增大。",
    "代码": "【股票代码】6位证券代码。\n• 支持单击联动主图，上下键跟随，双击查看 SBC 分时图。",
    "名称": "【股票简称】证券中文简称。",
    "现价": "【现价 / 当时价格】信号触发瞬间的分时现价，作为买入基准价格参考。",
    "涨幅%": "【当时涨幅】信号发出时的当日涨幅。\n• 0%~5%: 最佳起爆启动区间；\n• >6%: 日内已透支，追高风险剧增。",
    "级别": (
        "【梯度执行级别 (L0~L4)】\n"
        "• L4 主攻 (仓位上限30%): 首波放量突破且回踩不破均价，大盘翻转确认 + 强板块共振龙头；\n"
        "• L3 参与 (仓位上限18%): 分时突破前高确认，结构清晰度≥60；\n"
        "• L2 试仓 (仓位上限10%): 回踩 VWAP 低吸，不追高；\n"
        "• L1 观察 (4%): 限价试探挂单；\n"
        "• L0 观察 (0%): 触发风控硬否决，仅监控不下单。"
    ),
    "RAR": (
        "【RAR (Risk-Adjusted Rating 风险调整后综合评分)】\n"
        "• 定义: 综合评估买入位置、承接盘压、资金意图、大盘环境、相对强度并扣除追高/拥挤风险后的最终总分 (0~100分)。\n"
        "• 判定好坏标准:\n"
        "  - ≥80分: 极强 (满足 L4 主攻标准，进攻性强，胜率最高)；\n"
        "  - 70~80分: 强势 (L3 参与区间，结构清晰承接强)；\n"
        "  - 60~70分: 中等 (L2 试仓低吸，适合回踩时介入)；\n"
        "  - <60分: 弱势 (仅做观察，不建议重仓)。"
    ),
    "位": "【位 (Position 位置质量)】买在此处的盈亏比。\n• 衡量到止损底线的距离与上方阻力空间；\n• 止损在 2%~4.5% 且日内位于中位区为最佳，顶部(>85%)重罚。",
    "接": "【接 (Support 承接盘压)】拉升后是否有资金托底。\n• 外盘买入比(Taker Buy)≥60%、买盘压≥60% 且分时维持在均价上方为优质承接。",
    "意": "【意 (Intent 资金意图)】拉升是否果断、持续、有主攻攻角。\n• 攻角≥70、主力意图分≥75 且带量突破为佳，非散户脉冲拉升。",
    "环": "【环 (Regime 大盘环境)】大盘温度配合度、翻转状态与所属板块共振度。\n• 低温拐头与翻转确认期加分，退潮期非龙头重罚。",
    "仓位%": "【建议仓位%】综合考虑环境系数与时间衰减后的建议执行仓位上限 (占可用资金百分比)。",
    "进场": "【进场区间】建议挂单或低吸的合理价格区间 (严禁脱离均价追高)。",
    "止损": "【止损参考】跌破底台、SBC支撑或均线时的建议硬性离场价格。",
    "先手min": "【先手时间】距离该股当日首次异动过去的分钟数。\n• 先手优势随时间衰减，>40分钟严禁盲目追进。",
    "来源": "【信号来源】触发该梯度的底层信号源或回补标识。",
    "MFE%": "【MFE% (Maximum Favorable Excursion 最大潜在浮盈)】\n• 买入后全天最高价相对买入价的最大涨幅，衡量止盈空间与上行天花板。",
    "MAE%": "【MAE% (Maximum Adverse Excursion 最大回撤风险)】\n• 买入后全天最低价相对买入价的最大跌幅，衡量回踩风险与止损压力。",
    "收盘%": "【收盘收益%】持有至当天收盘时的收益率，衡量日内封板或承接稳定性。",
    "温度℃": "【市场温度】全市场多头情绪指标。\n• <30℃ 冰点 (首发排头兵最值钱)；\n• 45~62℃ 温和活跃；\n• >65℃ 过热非龙头易被埋。",
    "买入": "【买入时间】T+1 模拟成交执行时间。",
    "买入价": "【买入成交价】执行成交价格。",
    "时段": "【执行时段】成交所在的分时时间窗口。",
    "卖出": "【卖出时间】次日 T+1 规则离场时间。",
    "卖出价": "【卖出成交价】次日平仓成交价格。",
    "盈亏%": "【T+1 净盈亏%】该笔交易的最终实际盈亏百分比。",
    "当日最低%": "【买入当日最低回撤%】买入日盘中承受的最大下探幅度。",
    "被锁止损": "【T+1 是否被锁止损】因 A 股 T+1 规则导致日内触及止损而无法当天卖出的锁定状态。",
    "原因": "【离场原因】止盈减半、止损清仓或时间到期等退场归因。",
    "入局": "【入局时间】通过发令枪与证据链确认进入实盘入局阶段的时间。",
    "入局价": "【入局基准价】入局确认瞬间的股票现价。",
    "当时涨幅%": "【入局涨幅%】入局确认时的日内涨幅。",
    "首异动": "【首度异动时间】该股全天首次被系统捕捉到形态或放量突破的时间。",
    "首异动涨幅%": "【首异动涨幅%】首次异动时的涨幅。",
    "首→入%": "【首异动至入局涨幅】从首次异动到确认入局之间的涨幅跨度。",
    "持续分": "【持续性得分 (Persist)】\n• 异动发出后分时维持在均线上方和高位承接的持续性分数，越高代表走势越稳健。",
    "证据数": "【证据数量】盘中累积确认的结构性量价证据笔数。",
    "证据链": "【证据链详情】记录突破形态、放量特征、板块带头等连续判断证据日志。",
    "之后MFE%": "【入局后最大浮盈%】入局后全天达到的最高浮动收益。",
}


def _detect_ramdisk_dir() -> Optional[str]:
    """探测高速内存盘 (Ramdisk) 路径 (如 R:\\fusion_shadow, G:\\fusion_shadow 等)。
    若探测到有效 Ramdisk 且可写，返回对应影子快照目录，否则返回 None。
    """
    for drive in ("R:", "G:", "Z:"):
        base = os.path.join(drive, os.sep)
        if os.path.exists(base):
            candidate = os.path.join(drive, "fusion_shadow")
            try:
                os.makedirs(candidate, exist_ok=True)
                test_f = os.path.join(candidate, ".perm_test")
                with open(test_f, "w") as f:
                    f.write("ok")
                if os.path.exists(test_f):
                    os.remove(test_f)
                return candidate
            except Exception:
                continue
    return None


def _shadow_storage_paths(day: str = "") -> Tuple[str, Optional[str]]:
    """返回 (本地主落盘路径, Ramdisk高速快照路径) 双通道元组"""
    d_str = day or today_str()
    try:
        from sys_utils import get_app_root  # type: ignore

        root = get_app_root()
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    primary_path = os.path.join(root, "logs", "fusion_shadow", "{}.jsonl".format(d_str))

    ramdisk_dir = _detect_ramdisk_dir()
    ramdisk_path = os.path.join(ramdisk_dir, "{}.jsonl".format(d_str)) if ramdisk_dir else None
    return primary_path, ramdisk_path


def _shadow_log_path(day: str = "") -> str:
    primary, _ = _shadow_storage_paths(day)
    return primary


def persist_shadow_records(records: List[Dict[str, Any]], day: str = "") -> int:
    """双通道原子持久化：同时写入 Ramdisk (微秒级) 与 logs/fusion_shadow (高可靠物理落盘)"""
    if not records:
        return 0
    primary, ramdisk = _shadow_storage_paths(day)

    # 1. 写入 Ramdisk (高速内存虚拟盘，实盘零阻塞防崩溃)
    if ramdisk:
        try:
            os.makedirs(os.path.dirname(ramdisk), exist_ok=True)
            tmp_r = ramdisk + ".tmp"
            with open(tmp_r, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp_r, ramdisk)
        except Exception as e:
            logger.debug(f"[FusionLadder] Ramdisk 写入异常: {e}")

    # 2. 写入物理主落盘 logs/fusion_shadow/{day}.jsonl
    try:
        os.makedirs(os.path.dirname(primary), exist_ok=True)
        tmp_p = primary + ".tmp"
        with open(tmp_p, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp_p, primary)
    except Exception as e:
        logger.warning(f"[FusionLadder] 主落盘写入异常: {e}")

    return len(records)


def load_live_rows(day: str = "", max_lines: int = 5000) -> List[Dict[str, Any]]:
    """读影子日志，优先从 Ramdisk 读取，若无或落后则读落盘主日志，按 code 取最新一条，按级别+RAR 排序。"""
    primary, ramdisk = _shadow_storage_paths(day)
    target_path = primary

    # 优先使用 Ramdisk 镜像（若存在且修改时间更新）
    if ramdisk and os.path.exists(ramdisk):
        try:
            if not os.path.exists(primary) or os.path.getmtime(ramdisk) >= os.path.getmtime(primary):
                target_path = ramdisk
        except Exception:
            target_path = primary

    if not os.path.exists(target_path):
        return []
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=max_lines)
    except Exception:
        return []

    latest: Dict[str, Dict[str, Any]] = {}
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        code = str(rec.get("code") or "")
        if not code:
            continue
        code = code.split(".")[0].zfill(6)
        if not rec.get("name"):
            rec["name"] = name_of(code)
        prev = latest.get(code)
        if prev is None or float(rec.get("ts") or 0) >= float(prev.get("ts") or 0):
            latest[code] = rec

    rows = list(latest.values())
    rows.sort(key=lambda r: (int((r.get("fusion") or {}).get("tier") or 0),
                             float((r.get("fusion") or {}).get("rar") or 0)), reverse=True)
    return rows


class ReplayWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, day: str, focus: List[str], top_n: int = 300, step: int = 1,
                 cuts_mode: str = "percentile", parent=None):
        super().__init__(parent)
        self.day = day
        self.focus = focus
        self.top_n = top_n
        self.step = step
        self.cuts_mode = cuts_mode

    def run(self) -> None:  # noqa: D401
        try:
            rp = DayReplay(config=ReplayConfig(
                top_n=self.top_n, step=self.step,
                focus_codes=tuple(self.focus), cuts_mode=self.cuts_mode,
            ))
            if not rp.cache:
                self.failed.emit("找不到分钟线缓存（G:/minute_kline_cache.pkl）")
                return
            day = self.day or (rp.days()[-1] if rp.days() else today_str())
            result = rp.run_day(day, progress=lambda a, b: self.progress.emit(a, b), focus=self.focus)
            self.done.emit(result)
        except Exception as exc:  # 线程内异常必须自己吞，否则整个窗口崩
            self.failed.emit("{}: {}".format(type(exc).__name__, exc))


class FusionLadderDialog(QWidget, WindowMixin):
    """融合梯度监视器主窗口（系统级独立顶层窗口，对齐 ATS 专业看板体系）。"""

    def __init__(self, parent=None):
        # [🚀 独立顶层解耦] 必须传 None，彻底切断 Win32 HWND Owner 从属关系，成为系统级独立窗口
        super().__init__(None)
        self._py_parent = parent
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("🧬 融合梯度监视器 · SFL")
        self.setStyleSheet(_DARK_QSS)
        self.setMinimumSize(500, 320)

        # 1. 磁吸与隐藏状态初始化 (置顶状态下停用磁吸并还原)
        self.anchor_edge: Optional[str] = None
        self.is_hidden_state: bool = False
        self.normal_geometry: Optional[QRect] = None
        self.hover_ticks: int = 0
        self.leave_ticks: int = 0
        self._is_dragging: bool = False
        self._in_snap_action: bool = False
        self.anim_group: Optional[QParallelAnimationGroup] = None
        self._last_show_time: float = 0.0
        self._has_hovered_since_show: bool = False
        self._is_auto_popping: bool = False

        # 悬停与离开监控定时器 (默认保持停止，仅在贴边或隐藏感应态激活，0 额外开销)
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)

        # 拖拽结束防抖定时器
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(400)
        self.snap_timer.timeout.connect(self._detect_and_snap)

        # 2. 独立窗口 flags 与置顶配置
        self.stays_on_top = self._load_stays_on_top()
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        self.fav_manager = GlobalFavoriteManager()
        self.is_narrow_mode = bool(load_config_node("fusion_ladder_narrow_mode", False))
        self._worker: Optional[ReplayWorker] = None
        self._result = None
        self._replay_days: List[str] = []

        # 盘后自动沉淀与每日上下文定时检查
        self._last_auto_settle_day = str(load_config_node("fusion_last_auto_settle_day", ""))
        self._closing_settle_timer = QTimer(self)
        self._closing_settle_timer.timeout.connect(self._check_and_auto_settle_closing)
        self._closing_settle_timer.start(15000)

        self._init_ui()
        self._load_saved_geometry()
        self._init_days()
        self.refresh_live()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ---- 顶部控制条 ----
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.lbl_status = QLabel("状态：就绪")
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")
        bar.addWidget(self.lbl_status)
        bar.addStretch(1)

        # 极窄模式切换开关
        self.chk_narrow = QCheckBox("📐 极窄")
        self.chk_narrow.setChecked(self.is_narrow_mode)
        self.chk_narrow.setToolTip("开启极窄列模式：仅保留核心关键列，适合靠边停靠或小屏查看")
        self.chk_narrow.toggled.connect(self._on_narrow_mode_toggled)
        bar.addWidget(self.chk_narrow)

        # 置顶复选框 (置顶与磁吸互斥)
        self.chk_on_top = QCheckBox("📌 置顶")
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.setToolTip("开启置顶 (快捷键 T)；置顶状态下窗口始终浮于最前，停用边缘折叠隐藏")
        self.chk_on_top.toggled.connect(self._on_stays_on_top_toggled)
        bar.addWidget(self.chk_on_top)

        bar.addWidget(QLabel("交易日"))
        self.cmb_day = QComboBox()
        self.cmb_day.setMinimumWidth(105)
        self.cmb_day.currentTextChanged.connect(self._on_day_changed)
        bar.addWidget(self.cmb_day)

        bar.addWidget(QLabel("标的"))
        self.spin_top = QSpinBox()
        self.spin_top.setRange(50, 2000)
        self.spin_top.setSingleStep(50)
        self.spin_top.setValue(300)
        bar.addWidget(self.spin_top)

        bar.addWidget(QLabel("步长"))
        self.cmb_step = QComboBox()
        for s in (1, 2, 3):
            self.cmb_step.addItem("每{}根".format(s), s)
        bar.addWidget(self.cmb_step)

        self.btn_run = QPushButton("▶ 跑回放(回补)")
        self.btn_run.setToolTip("执行所选日期的全市场回放，并自动将有效决策回补持久化为影子流与上下文快照")
        self.btn_run.clicked.connect(self.run_replay)
        bar.addWidget(self.btn_run)

        self.btn_refresh = QPushButton("🔄 刷新影子")
        self.btn_refresh.setToolTip("加载当前所选交易日已持久化的影子记录")
        self.btn_refresh.clicked.connect(self.refresh_live)
        bar.addWidget(self.btn_refresh)

        root.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumHeight(6)
        root.addWidget(self.progress)

        # ---- 页签 ----
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab 0: 实时梯度 [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源]
        self.tbl_live = self._create_interactive_table([
            "级别", "代码", "名称", "现价", "涨幅%", "RAR", "位", "接", "意", "环", "仓位%", "进场", "止损", "先手min", "来源",
        ], "tbl_live")
        self.tabs.addTab(self.tbl_live, "实时梯度（影子流）")

        # Tab 1: 按日回放 [时间, 代码, 名称, 现价, 涨幅%, 级别, RAR, 仓位%, MFE%, MAE%, 收盘%, 温度℃]
        self.tbl_replay = self._create_interactive_table([
            "时间", "代码", "名称", "现价", "涨幅%", "级别", "RAR", "仓位%", "MFE%", "MAE%", "收盘%", "温度℃",
        ], "tbl_replay")
        self.tabs.addTab(self.tbl_replay, "按日回放")

        # Tab 2: T+1 订单与成交
        self.tbl_trades = self._create_interactive_table([
            "代码", "名称", "买入", "买入价", "时段", "卖出", "卖出价", "盈亏%", "当日最低%", "被锁止损", "原因",
        ], "tbl_trades")
        self.tabs.addTab(self.tbl_trades, "T+1 订单与成交")

        # Tab 3: 赛马跟踪
        self.tbl_track = self._create_interactive_table([
            "代码", "名称", "入局", "入局价", "当时涨幅%", "首异动", "首异动涨幅%", "首→入%",
            "持续分", "证据数", "证据链", "之后MFE%", "MAE%", "收盘%",
        ], "tbl_track")
        self.tabs.addTab(self.tbl_track, "赛马跟踪（第一波入局）")

        # Tab 4: 信号面板
        page_panel = QWidget()
        vp = QVBoxLayout(page_panel)
        vp.setContentsMargins(4, 4, 4, 4)
        self.txt_panel = QTextBrowser()
        self.txt_panel.setOpenExternalLinks(False)
        vp.addWidget(self.txt_panel, 1)
        self.tabs.addTab(page_panel, "信号面板（全部信号统计）")

        # Tab 5: 验收与复盘
        page3 = QWidget()
        v3 = QVBoxLayout(page3)
        v3.setContentsMargins(4, 4, 4, 4)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("验收标的"))
        self.ed_focus = QLineEdit("688787,300296")
        self.ed_focus.setPlaceholderText("逗号分隔，如 688787,300296")
        row3.addWidget(self.ed_focus, 1)
        self.btn_focus = QPushButton("跑验收")
        self.btn_focus.clicked.connect(self.run_focus)
        row3.addWidget(self.btn_focus)
        v3.addLayout(row3)
        self.txt_report = QTextBrowser()
        self.txt_report.setOpenExternalLinks(False)
        v3.addWidget(self.txt_report, 1)
        self.tabs.addTab(page3, "验收与复盘")

        self._apply_all_narrow_modes()

    # ------------------------------------------------------------------
    # 交互表格工厂 (精准数值排序 + 上下键联动 + 双击SBC + 右键菜单 + 列头 ToolTip)
    # ------------------------------------------------------------------
    def _create_interactive_table(self, headers: List[str], name: str) -> QTableWidget:
        tbl = QTableWidget(0, len(headers))
        tbl.setObjectName(name)
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setSortingEnabled(True)

        # 💡 设置字典级专业列头 ToolTip
        for col_idx, h_name in enumerate(headers):
            item = tbl.horizontalHeaderItem(col_idx)
            if item:
                tip = HEADER_TOOLTIPS.get(h_name) or f"【{h_name}】点击列头可按数值升/降序切换排序"
                item.setToolTip(tip)

        # 1. 鼠标点击联动
        tbl.itemClicked.connect(self._on_table_item_clicked)
        # 2. 键盘上下键行移动联动
        tbl.selectionModel().currentChanged.connect(
            lambda cur, prev, t=tbl: self._on_table_current_changed(t, cur)
        )
        # 3. 双击秒开通达信同款 SBC 分时走势图
        tbl.itemDoubleClicked.connect(self._on_table_item_double_clicked)
        # 4. ATS 标准右键上下文菜单
        tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tbl.customContextMenuRequested.connect(
            lambda pos, t=tbl: self._on_table_context_menu(t, pos)
        )
        return tbl

    def _get_row_code_name(self, tbl: QTableWidget, row: int) -> tuple[str, str]:
        if row < 0 or row >= tbl.rowCount():
            return "", ""
        code = ""
        name = ""
        for col in range(tbl.columnCount()):
            header = tbl.horizontalHeaderItem(col)
            if not header:
                continue
            h_text = header.text().strip()
            it = tbl.item(row, col)
            if not it:
                continue
            if "代码" in h_text and not code:
                raw_code = it.text().strip()
                if raw_code:
                    code = raw_code.split(".")[0].zfill(6)
            elif "名称" in h_text and not name:
                name = it.text().strip()
        if code and not name:
            name = name_of(code)
        return code, name

    def _on_table_item_clicked(self, item: QTableWidgetItem) -> None:
        if not item:
            return
        tbl = item.tableWidget()
        if not tbl:
            return
        code, name = self._get_row_code_name(tbl, item.row())
        if code:
            self._link_main_stock(code, name)

    def _on_table_current_changed(self, tbl: QTableWidget, current) -> None:
        if not current.isValid():
            return
        code, name = self._get_row_code_name(tbl, current.row())
        if code:
            self._link_main_stock(code, name)

    def _on_table_item_double_clicked(self, item: QTableWidgetItem) -> None:
        if not item:
            return
        tbl = item.tableWidget()
        if not tbl:
            return
        code, name = self._get_row_code_name(tbl, item.row())
        if code:
            self.open_sbc_chart(code, name)

    def _link_main_stock(self, code: str, name: str = "") -> None:
        main_app = self._get_main_app()
        if main_app and hasattr(main_app, "link_stock"):
            try:
                main_app.link_stock(code, name)
            except Exception as e:
                logger.debug(f"[FusionLadderDialog] 联动异常: {e}")

    def open_sbc_chart(self, code: str, name: str = "") -> None:
        """双击秒开通达信同款 SBC 分时走势图独立窗口"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog

            c_clean = str(code).split(".")[0].zfill(6)
            open_sbc_chart_dialog(parent_win=self.window(), code=c_clean, period_mode="10d")
        except Exception as exc:
            logger.warning(f"[FusionLadderDialog] 调起SBC走势图异常: {exc}")

    def _on_click_limit_up(self) -> None:
        mw = self._get_main_app()
        if mw and hasattr(mw, "open_daily_limit_up_analyzer"):
            mw.open_daily_limit_up_analyzer()

    def _on_click_hot_sector(self) -> None:
        mw = self._get_main_app()
        if mw and hasattr(mw, "open_hot_sector_leaderboard"):
            mw.open_hot_sector_leaderboard()

    def _on_click_miner(self) -> None:
        mw = self._get_main_app()
        if mw and hasattr(mw, "open_sector_rotation_miner"):
            mw.open_sector_rotation_miner()
        else:
            try:
                from ats.ui.sector_rotation_miner_dialog import open_sector_rotation_miner_dialog
                open_sector_rotation_miner_dialog(parent_window=self.window())
            except Exception as e:
                logger.warning(f"[FusionLadderDialog] 打开主线回踩深挖异常: {e}")

    def _on_table_context_menu(self, tbl: QTableWidget, pos) -> None:
        """ATS 资金主线级标准右键菜单 (带异动联动推送、SBC、详情、次新超短、DNA审计、重点关注与深挖)"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a1f;
                color: #e2e2e5;
                border: 1px solid #30363d;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #30363d;
                margin: 4px 6px;
            }
        """)

        item = tbl.itemAt(pos)
        # 点击空白区域时的通用菜单
        if not item:
            act_ladder = menu.addAction("🔥 打开每日涨停天梯看板")
            act_ladder.triggered.connect(self._on_click_limit_up)

            act_radar = menu.addAction("📊 打开板块雷达")
            act_radar.triggered.connect(self._on_click_hot_sector)

            act_miner = menu.addAction("🔄 打开主线回踩深挖")
            act_miner.triggered.connect(self._on_click_miner)

            menu.addSeparator()
            act_refresh = menu.addAction("🔄 手动刷新实时梯度数据")
            act_refresh.triggered.connect(self.refresh_live)

            menu.exec(tbl.viewport().mapToGlobal(pos))
            return

        row = item.row()
        code, name = self._get_row_code_name(tbl, row)
        if not code:
            return

        # 1. 📋 复制股票代码 (首项，一键直达剪贴板)
        copy_label = f"📋 复制股票代码 {code}"
        if name:
            copy_label += f" ({name})"
        act_copy = menu.addAction(copy_label)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(f"{code} {name}".strip()))

        menu.addSeparator()

        # 2. ⚡ 发送到异动联动 (named pipe)
        act_linkage = menu.addAction(f"⚡ 发送到异动联动 {code}")

        def _on_send_linkage():
            try:
                from ats.ui.base_table import send_to_linkage
                send_to_linkage(code, name, self)
                self.lbl_status.setText(f"⚡ 已发送 {name}({code}) 到异动联动")
                mw = self._get_main_app()
                if mw and hasattr(mw, "statusBar") and mw.statusBar():
                    mw.statusBar().showMessage(f"⚡ 已发送 {name}({code}) 到异动联动", 3000)
            except Exception as e:
                logger.error(f"[FusionLadderDialog] 发送异动联动异常: {e}")

        act_linkage.triggered.connect(_on_send_linkage)

        # 3. 📈 打开 SBC 通道走势图与个股详情
        act_sbc = menu.addAction(f"📈 打开 {name}({code}) SBC 通道走势图 (R)")
        act_sbc.triggered.connect(lambda: self.open_sbc_chart(code, name))

        act_detail = menu.addAction(f"🔍 查看 {name}({code}) 个股详情")

        def _view_detail():
            self.link_stock(code, name)
            mw = self._get_main_app()
            if mw and hasattr(mw, "on_stock_clicked"):
                try:
                    mw.on_stock_clicked(code, name, {})
                except Exception:
                    pass

        act_detail.triggered.connect(_view_detail)

        # 4. 🎯 发送到新股次新超短检测工具
        act_ipo = menu.addAction(f"🎯 发送到新股次新超短检测工具 ({code})")

        def _on_send_ipo():
            try:
                from ats.ui.ipo_detector_ipc import send_stock_to_ipo_detector
                send_stock_to_ipo_detector(code, name)
                self.lbl_status.setText(f"🎯 已发送 {name}({code}) 到新股次新超短检测工具")
            except Exception as e:
                logger.error(f"[FusionLadderDialog] 发送到次新超短检测工具异常: {e}")

        act_ipo.triggered.connect(_on_send_ipo)

        # 5. 🧬 调出 DNA 特征审计报告
        act_dna = menu.addAction(f"🧬 调出 {name or code} DNA 特征审计报告")

        def _on_dna_audit():
            try:
                from ats.ui.multi_period_dialog import run_dna_audit_batch_qt
                run_dna_audit_batch_qt({code: name}, parent=self.window())
            except Exception as e:
                logger.error(f"[FusionLadderDialog] 调出 DNA 审计报告异常: {e}")

        act_dna.triggered.connect(_on_dna_audit)

        menu.addSeparator()

        # 6. ⭐ 全系统重点关注管理
        is_fav = False
        if self.fav_manager:
            try:
                is_fav = self.fav_manager.is_favorite_stock(code)
            except Exception:
                try:
                    is_fav = self.fav_manager.is_favorite(code)
                except Exception:
                    is_fav = False

        fav_text = f"❌ 取消全系统重点关注: {name} ({code})" if is_fav else f"⭐ 设为全系统重点关注: {name} ({code})"
        act_fav = menu.addAction(fav_text)

        def _toggle_fav():
            if self.fav_manager:
                try:
                    if hasattr(self.fav_manager, "toggle_favorite"):
                        self.fav_manager.toggle_favorite(code)
                    else:
                        self.fav_manager.toggle_favorite_stock_result(code)
                    self.lbl_status.setText(f"⭐ 已更新重点关注: {name}({code})")
                except Exception as ex:
                    logger.warning(f"[FusionLadderDialog] 重点关注切换异常: {ex}")

        act_fav.triggered.connect(_toggle_fav)

        menu.addSeparator()

        # 7. 全局大看板与深挖工具
        act_ladder = menu.addAction("🔥 打开每日涨停天梯看板")
        act_ladder.triggered.connect(self._on_click_limit_up)

        act_radar = menu.addAction("📊 打开板块雷达")
        act_radar.triggered.connect(self._on_click_hot_sector)

        act_miner = menu.addAction("🔄 打开主线回踩深挖")
        act_miner.triggered.connect(self._on_click_miner)

        menu.exec(tbl.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # 极窄列模式与自适应持久化
    # ------------------------------------------------------------------
    def _on_narrow_mode_toggled(self, checked: bool) -> None:
        self.is_narrow_mode = bool(checked)
        save_config_node("fusion_ladder_narrow_mode", self.is_narrow_mode)
        self._apply_all_narrow_modes()

    def _apply_all_narrow_modes(self) -> None:
        # Tab 0: 实时梯度 [级别(0), 代码(1), 名称(2), 现价(3), 涨幅%(4), RAR(5), 仓位%(10), 进场(11), 止损(12)]
        self._set_cols_visibility(self.tbl_live, [0, 1, 2, 3, 4, 5, 10, 11, 12] if self.is_narrow_mode else None)
        # Tab 1: 按日回放 [时间(0), 代码(1), 名称(2), 现价(3), 涨幅%(4), 级别(5), RAR(6), 收盘%(10)]
        self._set_cols_visibility(self.tbl_replay, [0, 1, 2, 3, 4, 5, 6, 10] if self.is_narrow_mode else None)
        # Tab 2: T+1 订单 [代码(0), 名称(1), 买入价(3), 卖出价(6), 盈亏%(7), 原因(10)]
        self._set_cols_visibility(self.tbl_trades, [0, 1, 3, 6, 7, 10] if self.is_narrow_mode else None)
        # Tab 3: 赛马跟踪 [代码(0), 名称(1), 入局价(3), 当时涨幅%(4), 持续分(8), 证据链(10), 收盘%(13)]
        self._set_cols_visibility(self.tbl_track, [0, 1, 3, 4, 8, 10, 13] if self.is_narrow_mode else None)

    @staticmethod
    def _set_cols_visibility(tbl: QTableWidget, keep_cols: Optional[List[int]]) -> None:
        for c in range(tbl.columnCount()):
            if keep_cols is None:
                tbl.setColumnHidden(c, False)
            else:
                tbl.setColumnHidden(c, c not in keep_cols)

    def _get_main_app(self):
        """寻找 ATSMainWindow 实例，支持跨窗口联动"""
        curr = getattr(self, "_py_parent", None) or (self.parent() if hasattr(self, "parent") else None)
        from PyQt6.sip import isdeleted

        try:
            while curr:
                if not isdeleted(curr) and curr.__class__.__name__ == "ATSMainWindow":
                    return curr
                curr = curr.parent() if hasattr(curr, "parent") else None
        except Exception:
            pass

        app = QApplication.instance()
        if app:
            if getattr(app, "main_window", None) is not None:
                try:
                    mw = app.main_window
                    if not isdeleted(mw) and mw.__class__.__name__ == "ATSMainWindow":
                        return mw
                except Exception:
                    pass
            try:
                for widget in app.topLevelWidgets():
                    if not isdeleted(widget) and widget.__class__.__name__ == "ATSMainWindow":
                        return widget
            except Exception:
                pass
        return None

    def _init_days(self) -> None:
        try:
            rp = DayReplay()
            self._replay_days = rp.days()
        except Exception:
            self._replay_days = []
        self.cmb_day.blockSignals(True)
        self.cmb_day.clear()
        if self._replay_days:
            for d in self._replay_days:
                self.cmb_day.addItem(d)
            self.cmb_day.setCurrentIndex(len(self._replay_days) - 1)
        else:
            self.cmb_day.addItem(today_str())
            self.cmb_day.setCurrentIndex(0)
        self.cmb_day.blockSignals(False)

    def _on_day_changed(self, text: str) -> None:
        day = text.strip()
        if day:
            self.refresh_live()

    @staticmethod
    def _num_item(text: Any, raw_val: Any = None, color: Optional[QColor] = None, bold: bool = False) -> NumericTableWidgetItem:
        """基于 ATS NumericTableWidgetItem 构建支持高精度数值比对的单元格"""
        it = NumericTableWidgetItem(value=text, raw_val=raw_val)
        if color is not None:
            it.setForeground(color)
        if bold:
            f = QFont()
            f.setBold(True)
            it.setFont(f)
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it

    # ------------------------------------------------------------------
    # 窗口持久化与置顶控制
    # ------------------------------------------------------------------
    def _load_stays_on_top(self) -> bool:
        try:
            val = load_config_node("fusion_ladder_stays_on_top", False)
            return bool(val)
        except Exception:
            return False

    def _on_stays_on_top_toggled(self, checked: bool) -> None:
        self.stays_on_top = bool(checked)
        if checked:
            if self.is_hidden_state:
                self.show_normal_position()
            self.is_hidden_state = False
            self.anchor_edge = None
            self.normal_geometry = None
            if hasattr(self, "snap_timer") and self.snap_timer:
                self.snap_timer.stop()
            if hasattr(self, "hover_timer") and self.hover_timer:
                self.hover_timer.stop()
            self.setWindowOpacity(1.0)
        else:
            if hasattr(self, "hover_timer") and self.hover_timer:
                self.hover_timer.start()

        set_seamless_stay_on_top(self, self.stays_on_top)
        self._save_window_states(is_open=True)

    def _load_saved_geometry(self) -> None:
        """从持久化配置加载窗口几何位置与磁吸状态"""
        try:
            data = load_config_node("fusion_ladder_dialog") or {}
            screen = self.screen() or QApplication.primaryScreen()
            s_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

            if data and isinstance(data, dict):
                rx = int(data.get("x", s_geo.left() + 50))
                ry = int(data.get("y", s_geo.top() + 50))
                rw = int(data.get("width", 1220))
                rh = int(data.get("height", 760))
                rw = max(500, min(rw, s_geo.width()))
                rh = max(320, min(rh, s_geo.height()))
                rx = max(s_geo.left(), min(rx, s_geo.right() - rw))
                ry = max(s_geo.top(), min(ry, s_geo.bottom() - rh))

                self.normal_geometry = QRect(rx, ry, rw, rh)
                self.setGeometry(rx, ry, rw, rh)

                if not self.stays_on_top:
                    saved_edge = data.get("anchor_edge")
                    is_hidden = data.get("is_hidden", False)
                    if saved_edge in ("top", "left", "right"):
                        self.anchor_edge = saved_edge
                        if is_hidden:
                            self.is_hidden_state = True
                            strip_size = 5
                            if saved_edge == "left":
                                hx = s_geo.left() - rw + strip_size
                                hy = ry
                            elif saved_edge == "right":
                                hx = s_geo.right() - strip_size
                                hy = ry
                            elif saved_edge == "top":
                                hx = rx
                                hy = s_geo.top() - rh + strip_size
                            else:
                                hx, hy = rx, ry
                                self.is_hidden_state = False
                            self.setGeometry(hx, hy, rw, rh)
                            self.setWindowOpacity(0.35)
                            if hasattr(self, "hover_timer") and not self.hover_timer.isActive():
                                self.hover_timer.start()
                        elif self.anchor_edge:
                            if hasattr(self, "hover_timer") and not self.hover_timer.isActive():
                                self.hover_timer.start()
            else:
                self.resize(1220, 760)
                self.normal_geometry = self.geometry()
        except Exception as e:
            logger.debug(f"[FusionLadderDialog] 加载几何位置异常: {e}")
            self.resize(1220, 760)
            self.normal_geometry = self.geometry()

    def _save_window_states(self, is_open: Optional[bool] = None) -> None:
        """保存窗口位置、尺寸、置顶与磁吸隐藏状态"""
        try:
            geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
            width = max(500, int(geom.width()))
            height = max(320, int(geom.height()))
            x = int(geom.x())
            y = int(geom.y())

            if is_open is None:
                is_open = self.isVisible()

            node_data = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "stays_on_top": self.stays_on_top,
                "anchor_edge": None if self.stays_on_top else self.anchor_edge,
                "is_hidden": False if self.stays_on_top else self.is_hidden_state,
                "is_open": is_open,
            }
            save_config_node("fusion_ladder_dialog", node_data)
            save_config_node("fusion_ladder_stays_on_top", self.stays_on_top)
            save_config_node("fusion_ladder_anchor_edge", None if self.stays_on_top else self.anchor_edge)
            save_config_node("fusion_ladder_is_hidden", False if self.stays_on_top else self.is_hidden_state)
        except Exception as e:
            logger.debug(f"[FusionLadderDialog] 保存窗口状态异常: {e}")

    # ------------------------------------------------------------------
    # 磁吸贴边与平滑展开/隐藏动效
    # ------------------------------------------------------------------
    def start_slide_animation(
        self,
        target_geo: QRect,
        target_opacity: float = 1.0,
        duration: int = 250,
        is_snap_feedback: bool = False,
    ) -> None:
        """平滑滑动与透明度双属性复合动画控制器"""
        if self.anim_group:
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
            self.opacity_anim.setKeyValueAt(0.5, 0.45)
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

    def _detect_and_snap(self) -> None:
        """拖拽结束检测边缘磁吸吸附 (35px 阈值，支持 top / left / right)"""
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

        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35

        d_top = abs(win_geo.top() - screen_geo.top())
        d_left = abs(win_geo.left() - screen_geo.left())
        d_right = abs((win_geo.x() + win_geo.width()) - (screen_geo.x() + screen_geo.width()))

        min_dist = min(d_top, d_left, d_right)

        if min_dist < margin:
            target_x = win_geo.left()
            target_y = win_geo.top()
            if min_dist == d_top:
                edge = "top"
                target_y = screen_geo.top()
            elif min_dist == d_left:
                edge = "left"
                target_x = screen_geo.left()
            else:
                edge = "right"
                target_x = screen_geo.x() + screen_geo.width() - win_geo.width()

            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            self.start_slide_animation(self.normal_geometry, 1.0, duration=180, is_snap_feedback=True)
            if hasattr(self, "hover_timer") and not self.hover_timer.isActive():
                self.hover_timer.start()
        else:
            self.anchor_edge = None
            self.normal_geometry = None
            self._save_window_states(is_open=True)
            if hasattr(self, "hover_timer") and self.hover_timer.isActive():
                self.hover_timer.stop()

    def hide_to_edge(self) -> None:
        """贴边后收缩为 5px 边缘观察/感应条 (透明度 0.35)"""
        if getattr(self, "stays_on_top", False):
            return
        if not self.anchor_edge or not self.normal_geometry:
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
            target_x = screen_geo.x() + screen_geo.width() - strip_size
            target_y = y
        elif self.anchor_edge == "top":
            target_x = x
            target_y = screen_geo.top() - h + strip_size
        else:
            return

        self.is_hidden_state = True
        if hasattr(self, "hover_timer") and not self.hover_timer.isActive():
            self.hover_timer.start()
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=250)

    def show_normal_position(self) -> None:
        """鼠标滑过感应条或窗口激活时，平滑展开至原始尺寸与位置 (透明度 1.0)"""
        if getattr(self, "is_hidden_state", False):
            self.is_hidden_state = False
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, "_is_auto_popping", False))
            self._last_show_time = time.time()
            self._has_hovered_since_show = False

            if not getattr(self, "normal_geometry", None):
                w = self.width()
                h = self.height()
                screen = self.screen() or QApplication.primaryScreen()
                s_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                if self.anchor_edge == "left":
                    self.normal_geometry = QRect(s_geo.left(), self.y(), w, h)
                elif self.anchor_edge == "right":
                    self.normal_geometry = QRect(s_geo.right() - w, self.y(), w, h)
                elif self.anchor_edge == "top":
                    self.normal_geometry = QRect(self.x(), s_geo.top(), w, h)
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
        self._save_window_states(is_open=True)

    def _check_hover(self) -> None:
        """贴边状态下的鼠标悬停/离开巡检 (0 开销设计)"""
        if not self.isVisible() or getattr(self, "stays_on_top", False):
            if hasattr(self, "hover_timer") and self.hover_timer.isActive():
                self.hover_timer.stop()
            return

        if not self.anchor_edge and not getattr(self, "is_hidden_state", False):
            if hasattr(self, "hover_timer") and self.hover_timer.isActive():
                self.hover_timer.stop()
            return

        if getattr(self, "_in_snap_action", False):
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return

        mouse_pos = QCursor.pos()
        in_window = self.frameGeometry().contains(mouse_pos)

        if in_window:
            self._has_hovered_since_show = True

        if getattr(self, "is_hidden_state", False):
            if in_window:
                self.hover_ticks += 1
                if self.hover_ticks >= 2:  # 悬停 200ms 滑出
                    self.show_normal_position()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0
        else:
            if self.anchor_edge is not None:
                if not in_window:
                    if not getattr(self, "_has_hovered_since_show", False):
                        self.leave_ticks = 0
                        return
                    if time.time() - getattr(self, "_last_show_time", 0.0) < 1.2:
                        self.leave_ticks = 0
                        return
                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:  # 移开 400ms 自动折叠
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    # ------------------------------------------------------------------
    # Qt 事件系统处理
    # ------------------------------------------------------------------
    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        if self.stays_on_top:
            self.snap_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            return
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            self.anchor_edge = None
            self.snap_timer.start(300)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and getattr(self, "is_hidden_state", False):
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, "_is_auto_popping", False))
                self.show_normal_position()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if (self.anchor_edge is not None or getattr(self, "is_hidden_state", False)) and not getattr(self, "stays_on_top", False):
            if hasattr(self, "hover_timer") and not self.hover_timer.isActive():
                self.hover_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "hover_timer") and self.hover_timer.isActive():
            self.hover_timer.stop()
        if hasattr(self, "snap_timer") and self.snap_timer.isActive():
            self.snap_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        """系统事件响应：当窗口被系统/Alt+R激活时，若处于边缘折叠隐藏状态，自动平滑展开"""
        try:
            if event and event.type() == QEvent.Type.ActivationChange:
                if self.isActiveWindow() and getattr(self, "is_hidden_state", False):
                    self.show_normal_position()
        except Exception:
            pass
        try:
            super().changeEvent(event)
        except Exception:
            pass

    def _check_and_auto_settle_closing(self) -> None:
        """盘后自动执行设计的自动持久化及上下文功能，每日自动更新上下文，无需反复重启"""
        try:
            now_dt = datetime.datetime.now()
            t_str = now_dt.strftime("%H:%M:%S")
            cur_day = today_str()

            # 1. 每日自动感知与跨日更新：如果日期跨日，自动刷新下拉框和界面
            curr_combo_day = self.cmb_day.currentText().strip()
            if curr_combo_day and curr_combo_day != cur_day and t_str >= "09:15:00":
                idx = self.cmb_day.findText(cur_day)
                if idx < 0:
                    self.cmb_day.addItem(cur_day)
                    idx = self.cmb_day.findText(cur_day)
                self.cmb_day.setCurrentIndex(idx)
                self.refresh_live()

            # 2. 盘后自动沉淀：15:00 以后自动执行收盘持久化与上下文交接
            if t_str >= "15:00:00" and self._last_auto_settle_day != cur_day:
                self._execute_closing_session_settlement(cur_day)
        except Exception as exc:
            logger.warning(f"[FusionLadderDialog] 自动沉淀巡检异常: {exc}")

    def _execute_closing_session_settlement(self, day: str) -> None:
        """执行收盘自动持久化、上下文固化与次日 handoff 交接"""
        try:
            from ats.fusion.session_ctx import default_store
            store = default_store()

            live_rows = load_live_rows(day)
            if live_rows:
                # 双通道持久化：Ramdisk + 物理落盘
                persist_shadow_records(live_rows, day)

            store.close_day(
                day,
                phase_path=[{"time": "15:00", "phase": "收盘完成", "note": f"有效梯度标的{len(live_rows)}只"}],
                amount_wan=None,
                capital_ratio=1.0,
            )
            try:
                handoff_data = store.handoff(day)
                logger.info(f"[FusionLadderDialog] 今日收盘上下文已自动沉淀并完成次日交接: {handoff_data.get('label')}")
            except Exception:
                pass

            self._last_auto_settle_day = day
            save_config_node("fusion_last_auto_settle_day", day)
            self.lbl_status.setText(f"✅ 今日收盘上下文已自动沉淀 (session_ctx/{day}.json)")
        except Exception as e:
            logger.warning(f"[FusionLadderDialog] 收盘沉淀失败: {e}")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """快捷键：T 切换置顶，Escape 优先贴边隐藏"""
        if event.key() == Qt.Key.Key_T:
            if hasattr(self, "chk_on_top"):
                self.chk_on_top.setChecked(not self.chk_on_top.isChecked())
            return
        if event.key() == Qt.Key.Key_Escape:
            if self.anchor_edge and not self.is_hidden_state and not self.stays_on_top:
                self.hide_to_edge()
                return
            self.close()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 实时与回补数据展示
    # ------------------------------------------------------------------
    def refresh_live(self) -> None:
        day = self.cmb_day.currentText().strip() or today_str()
        rows = load_live_rows(day)
        tbl = self.tbl_live
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        if not rows:
            self.lbl_status.setText(f"状态：{day} 暂无影子记录（可点击 [▶ 跑回放(回补)] 自动生成）")
            self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")
            tbl.setSortingEnabled(True)
            return

        tier_count = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        for r in rows:
            fusion = r.get("fusion") or {}
            tier = int(fusion.get("tier") or 0)
            tier_count[tier] = tier_count.get(tier, 0) + 1
            i = tbl.rowCount()
            tbl.insertRow(i)
            axes = fusion.get("axes") or {}
            entry = fusion.get("entry") or {}
            stop = fusion.get("stop") or {}
            band = ""
            if entry.get("price_lo") and entry.get("price_hi"):
                band = "{:.2f}~{:.2f}".format(float(entry["price_lo"]), float(entry["price_hi"]))

            code = str(r.get("code", "")).split(".")[0].zfill(6)
            name = str(r.get("name") or "") or name_of(code)
            price = float(r.get("price") or (entry.get("price_lo") or 0.0) or 0.0)
            pct = float(r.get("pct") or 0.0)

            # 各列严格接入 NumericTableWidgetItem 保证高精度数值排序
            # 表头: [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源]
            tbl.setItem(i, 0, self._num_item(f"L{tier}", tier, _TIER_COLORS.get(tier), bold=True))
            tbl.setItem(i, 1, self._num_item(code, code))
            tbl.setItem(i, 2, self._num_item(name, name))
            tbl.setItem(i, 3, self._num_item(f"{price:.2f}" if price > 0 else "-", price))
            tbl.setItem(i, 4, self._num_item(f"{pct:+.2f}%", pct, color=QColor("#ff5c5c") if pct >= 0 else QColor("#00ff88"), bold=True))
            tbl.setItem(i, 5, self._num_item(fusion.get("rar", 0), float(fusion.get("rar", 0) or 0)))
            tbl.setItem(i, 6, self._num_item(axes.get("position", 0), float(axes.get("position", 0) or 0)))
            tbl.setItem(i, 7, self._num_item(axes.get("support", 0), float(axes.get("support", 0) or 0)))
            tbl.setItem(i, 8, self._num_item(axes.get("intent", 0), float(axes.get("intent", 0) or 0)))
            tbl.setItem(i, 9, self._num_item(axes.get("regime", 0), float(axes.get("regime", 0) or 0)))
            tbl.setItem(i, 10, self._num_item(f"{fusion.get('size_pct', 0)}%", float(fusion.get("size_pct", 0) or 0)))
            tbl.setItem(i, 11, self._num_item(band, band))
            tbl.setItem(i, 12, self._num_item(stop.get("price", "-"), float(stop.get("price") or 0) if stop.get("price") not in ("-", None) else 0.0))
            tbl.setItem(i, 13, self._num_item(fusion.get("age_min", 0), float(fusion.get("age_min", 0) or 0)))
            tbl.setItem(i, 14, self._num_item(",".join(fusion.get("sources") or []), ",".join(fusion.get("sources") or [])))

        tbl.setSortingEnabled(True)
        self.lbl_status.setText(
            "状态：{} 影子 {} 条｜L4 {} / L3 {} / L2 {} / L1 {} / L0 {}".format(
                day, len(rows), tier_count[4], tier_count[3], tier_count[2], tier_count[1], tier_count[0]
            )
        )
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

    # ------------------------------------------------------------------
    # 回放与回补持久化
    # ------------------------------------------------------------------
    def _start_worker(self, focus: List[str]) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.lbl_status.setText("状态：回放进行中，请稍候…")
            return
        day = self.cmb_day.currentText().strip()
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_focus.setEnabled(False)
        self.lbl_status.setText("状态：回放 {} 中…".format(day))
        self.lbl_status.setStyleSheet("color:#ffd75e; font-weight:bold;")

        self._worker = ReplayWorker(
            day=day, focus=focus, top_n=self.spin_top.value(),
            step=int(self.cmb_step.currentData() or 1),
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_replay_done)
        self._worker.failed.connect(self._on_replay_failed)
        self._worker.start()

    def _on_progress(self, cur: int, total: int) -> None:
        pct = int(cur * 100 / max(1, total))
        self.progress.setValue(pct)

    def _on_replay_failed(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.lbl_status.setText("状态：回放失败 — {}".format(msg))
        self.lbl_status.setStyleSheet("color:#ff5c5c; font-weight:bold;")

    def _persist_replay_shadow_and_context(self, result) -> int:
        """回测即回补数据：将所选日期的回放结果自动持久化落盘至影子日志与上下文快照"""
        day = getattr(result, "day", "")
        if not day or not getattr(result, "records", None):
            return 0
        try:
            from ats.fusion.session_ctx import default_store

            # 1. 回补双通道持久化：同时落盘 logs/fusion_shadow/{day}.jsonl 与 Ramdisk
            by_code: Dict[str, Dict[str, Any]] = {}
            for r in result.records:
                cd = str(r.get("code") or "").split(".")[0].zfill(6)
                if not cd:
                    continue
                tier = int(r.get("tier") or 0)
                rar = float(r.get("rar") or 0.0)
                entry_p = float(r.get("entry") or 0.0)
                pct_val = float(r.get("pct") or 0.0)
                row = {
                    "ts": float(r.get("ts") or time.time()),
                    "code": cd,
                    "name": r.get("name") or name_of(cd),
                    "price": entry_p,
                    "pct": pct_val,
                    "trade_date": day,
                    "fusion": {
                        "tier": tier,
                        "tier_name": str(r.get("tier_name") or ""),
                        "rar": rar,
                        "size_pct": float(r.get("size_pct") or 0.0),
                        "age_min": float(r.get("age_min") or 0.0),
                        "entry": {"price_lo": entry_p, "price_hi": entry_p},
                        "stop": {"price": r.get("stop") or "-"},
                        "axes": {
                            "position": float((r.get("axes") or {}).get("position") or 50.0),
                            "support": float((r.get("axes") or {}).get("support") or 50.0),
                            "intent": float((r.get("axes") or {}).get("intent") or 50.0),
                            "regime": float((r.get("axes") or {}).get("regime") or 50.0),
                        },
                        "sources": ["REPLAY_BACKFILL"],
                    },
                }
                prev = by_code.get(cd)
                if (prev is None or
                        row["fusion"]["tier"] > prev["fusion"]["tier"] or
                        (row["fusion"]["tier"] == prev["fusion"]["tier"] and row["fusion"]["rar"] > prev["fusion"]["rar"])):
                    by_code[cd] = row

            persist_shadow_records(list(by_code.values()), day)

            # 2. 回补沉淀 logs/fusion_state/session_ctx/{day}.json 上下文快照
            store = default_store()
            store.close_day(
                day,
                phase_path=[{"time": "15:00", "phase": "回补就绪", "note": f"回补标的{len(by_code)}只"}],
                amount_wan=None,
                capital_ratio=1.0,
            )
            return len(by_code)
        except Exception as exc:
            logger.warning(f"[FusionLadderDialog] 回放回补持久化异常: {exc}")
            return 0

    def _on_replay_done(self, result) -> None:
        self._result = result
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.progress.setValue(100)

        # 🚀 自动持久化回补 (回测即回补)
        backfilled_count = self._persist_replay_shadow_and_context(result)

        # Tab 1: 按日回放表格渲染
        # 表头: [时间(0), 代码(1), 名称(2), 现价(3), 涨幅%(4), 级别(5), RAR(6), 仓位%(7), MFE%(8), MAE%(9), 收盘%(10), 温度℃(11)]
        rows = sorted(result.records, key=lambda r: (r["tier"], r["rar"]), reverse=True)[:1000]
        tbl = self.tbl_replay
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        for r in rows:
            i = tbl.rowCount()
            tbl.insertRow(i)
            cd = str(r["code"]).split(".")[0].zfill(6)
            nm = str(r.get("name") or "") or name_of(cd)
            entry_p = float(r.get("entry") or 0.0)
            pct_v = float(r.get("pct") or 0.0)
            tier = r["tier"]

            tbl.setItem(i, 0, self._num_item(r["time"], r["time"]))
            tbl.setItem(i, 1, self._num_item(cd, cd))
            tbl.setItem(i, 2, self._num_item(nm, nm))
            tbl.setItem(i, 3, self._num_item(f"{entry_p:.2f}" if entry_p > 0 else "-", entry_p))
            tbl.setItem(i, 4, self._num_item(f"{pct_v:+.2f}%", pct_v, color=QColor("#ff5c5c") if pct_v >= 0 else QColor("#00ff88"), bold=True))
            tbl.setItem(i, 5, self._num_item(r["tier_name"], tier, _TIER_COLORS.get(tier), bold=True))
            tbl.setItem(i, 6, self._num_item(r["rar"], float(r["rar"] or 0)))
            tbl.setItem(i, 7, self._num_item(f"{r['size_pct']}%", float(r["size_pct"] or 0)))
            tbl.setItem(i, 8, self._num_item(f"{r['mfe']:+.2f}%", float(r["mfe"] or 0)))
            tbl.setItem(i, 9, self._num_item(f"{r['mae']:+.2f}%", float(r["mae"] or 0)))
            tbl.setItem(i, 10, self._num_item(f"{r['close_ret']:+.2f}%", float(r["close_ret"] or 0)))
            tbl.setItem(i, 11, self._num_item(f"{r['temp']}℃", float(r["temp"] or 0)))
        tbl.setSortingEnabled(True)

        # Tab 2: T+1 订单与成交
        t2 = self.tbl_trades
        t2.setSortingEnabled(False)
        t2.setRowCount(0)
        for tr in sorted(getattr(result, "trades", []), key=lambda x: x.entry_ts):
            d = tr.to_dict()
            i = t2.rowCount()
            t2.insertRow(i)
            cd = str(d["code"]).split(".")[0].zfill(6)
            nm = name_of(cd)
            pnl = float(d["pnl_pct"] or 0)
            color = QColor("#ff5c5c") if pnl >= 0 else QColor("#00ff88")

            t2.setItem(i, 0, self._num_item(cd, cd))
            t2.setItem(i, 1, self._num_item(nm, nm))
            t2.setItem(i, 2, self._num_item(d["entry_time"], d["entry_time"]))
            t2.setItem(i, 3, self._num_item(d["entry_price"], float(d["entry_price"] or 0)))
            t2.setItem(i, 4, self._num_item(d["window"], d["window"]))
            t2.setItem(i, 5, self._num_item(d["exit_time"], d["exit_time"]))
            t2.setItem(i, 6, self._num_item(d["exit_price"] or "-", float(d["exit_price"] or 0)))
            t2.setItem(i, 7, self._num_item(f"{pnl:+.2f}%", pnl, color=color, bold=True))
            t2.setItem(i, 8, self._num_item(f"{d['day0_mae_pct']:+.2f}%", float(d["day0_mae_pct"] or 0)))
            t2.setItem(i, 9, self._num_item("是" if d["stop_blocked"] else "否", 1 if d["stop_blocked"] else 0))
            t2.setItem(i, 10, self._num_item(d["exit_reason"], d["exit_reason"]))
        t2.setSortingEnabled(True)

        # Tab 3: 赛马跟踪：入局清单（带旧信号）
        t3 = self.tbl_track
        t3.setSortingEnabled(False)
        t3.setRowCount(0)
        for e in sorted(getattr(result, "entries", []) or [], key=lambda x: -float(x.get("persist") or 0)):
            i = t3.rowCount()
            t3.insertRow(i)
            cd = str(e.get("code", "")).split(".")[0].zfill(6)
            nm = name_of(cd)
            ret = float(e.get("close_ret") or 0)
            color = QColor("#ff5c5c") if ret >= 0 else QColor("#00ff88")

            t3.setItem(i, 0, self._num_item(cd, cd))
            t3.setItem(i, 1, self._num_item(nm, nm))
            t3.setItem(i, 2, self._num_item(e.get("enter_time", ""), e.get("enter_time", "")))
            t3.setItem(i, 3, self._num_item(e.get("enter_price", ""), float(e.get("enter_price") or 0)))
            t3.setItem(i, 4, self._num_item(f"{e.get('enter_pct', 0):+.2f}%", float(e.get("enter_pct") or 0)))
            t3.setItem(i, 5, self._num_item(e.get("first_time", ""), e.get("first_time", "")))
            t3.setItem(i, 6, self._num_item(f"{e.get('first_pct', 0):+.2f}%", float(e.get("first_pct") or 0)))
            t3.setItem(i, 7, self._num_item(f"{e.get('since_first_pct', 0):+.2f}%", float(e.get("since_first_pct") or 0)))
            t3.setItem(i, 8, self._num_item(e.get("persist", 0), float(e.get("persist") or 0), bold=True))
            t3.setItem(i, 9, self._num_item(e.get("evidence_n", 0), int(e.get("evidence_n") or 0)))
            t3.setItem(i, 10, self._num_item(e.get("chain", ""), e.get("chain", "")))
            t3.setItem(i, 11, self._num_item(f"{e.get('mfe', 0):+.2f}%", float(e.get("mfe") or 0), color=color))
            t3.setItem(i, 12, self._num_item(f"{e.get('mae', 0):+.2f}%", float(e.get("mae") or 0)))
            t3.setItem(i, 13, self._num_item(f"{ret:+.2f}%", ret, color=color, bold=True))
        t3.setSortingEnabled(True)

        # Tab 4: 信号面板
        try:
            dep_n = sum(1 for e in (getattr(result, "entries", []) or []) if deploy_path(e))
            panel = build_panel(records=result.records, entries=getattr(result, "entries", []) or [],
                                meta=result.meta, deploy_count=dep_n)
            self.txt_panel.setPlainText(render_panel(panel))
        except Exception as exc:
            self.txt_panel.setPlainText("信号面板生成失败：{}".format(exc))

        self.txt_report.setPlainText(render_report(result))

        # 更新极窄列显示
        self._apply_all_narrow_modes()

        self.lbl_status.setText(
            "状态：{} 回放完成并已回补落盘影子流({}条)｜评估 {}｜入局 {}".format(
                result.day, backfilled_count, result.meta.get("evaluations"),
                result.meta.get("entries", 0),
            )
        )
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

    def run_replay(self) -> None:
        self._start_worker([])

    def run_focus(self) -> None:
        codes = [c.strip() for c in self.ed_focus.text().split(",") if c.strip()]
        self.tabs.setCurrentIndex(5)
        self._start_worker(codes)

    # ------------------------------------------------------------------
    # 复盘
    # ------------------------------------------------------------------
    def refresh_review(self) -> None:
        day = self.cmb_day.currentText().strip()
        records = load_records(day)
        md = render_markdown(summarize(records), suggest_cuts(records), day)
        self.txt_report.setPlainText(md)

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭事件：妥善停止 worker 并持久化窗口状态"""
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.progress.disconnect()
                self._worker.done.disconnect()
                self._worker.failed.disconnect()
            except Exception:
                pass
        self._save_window_states(is_open=False)
        super().closeEvent(event)


_INSTANCE: Optional[FusionLadderDialog] = None


def open_fusion_ladder_dialog(parent_window=None) -> Optional[FusionLadderDialog]:
    """单例打开（系统级独立顶层窗口，不抢焦点，支持折叠自动弹开）。"""
    global _INSTANCE
    try:
        from PyQt6.sip import isdeleted

        if _INSTANCE is not None and not isdeleted(_INSTANCE):
            if getattr(_INSTANCE, "is_hidden_state", False):
                _INSTANCE.show_normal_position()
            else:
                if _INSTANCE.isMinimized():
                    _INSTANCE.showNormal()
                else:
                    _INSTANCE.show()
                _INSTANCE.raise_()
                _INSTANCE.activateWindow()
            _INSTANCE.refresh_live()
            return _INSTANCE
    except Exception:
        _INSTANCE = None

    try:
        dlg = FusionLadderDialog(parent=parent_window)
        dlg.show()
        _INSTANCE = dlg
        return dlg
    except Exception as exc:
        logger.error(f"[open_fusion_ladder_dialog] 创建窗口失败: {exc}")
        return None


def get_open_fusion_ladder_dialog() -> Optional[FusionLadderDialog]:
    """获取当前已打开且存活的融合信号梯度监视器单例 (供 Alt+R 轮转与外部直接获取)"""
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            from PyQt6.sip import isdeleted

            if not isdeleted(_INSTANCE) and _INSTANCE.isVisible():
                return _INSTANCE
        except Exception:
            pass
    return None


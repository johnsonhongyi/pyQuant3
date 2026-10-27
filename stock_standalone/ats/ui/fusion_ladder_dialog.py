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
import re
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QKeyEvent, QPainter, QPalette, QPen
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
QCheckBox[hitOnly="true"] { color: #4dd0e1; font-weight: bold; }
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

# 💡 专业列头悬浮说明：对齐 TK 指标悬浮卡片（指标名 / 一句话定义 / 判断依据）
def _tip(title: str, desc: str, rule: str) -> str:
    """生成统一版式的悬浮卡片 HTML：标题 + 定义 + 判断依据（配色对齐 TK 指标卡）。"""
    return (
        '<div style="max-width:360px;">'
        '<div style="font-size:13px;font-weight:600;color:#4dd0e1;">{}</div>'
        '<div style="font-size:12px;color:#eceff4;margin-top:5px;line-height:150%;">{}</div>'
        '<div style="font-size:12px;color:#c3e88d;margin-top:6px;line-height:150%;">判断依据：{}</div>'
        '</div>'
    ).format(title, desc, rule)


HEADER_TOOLTIPS: Dict[str, str] = {
    "时间": _tip(
        "🕒 时间 (time)",
        "该条信号被写入影子流的分时时点。",
        "09:30~10:00 先手爆发力最强；10:30 之后每过 10 分钟，追进的容错空间都在收窄。",
    ),
    "代码": _tip(
        "🔖 代码 (code)",
        "6 位证券代码。单击联动主图，上下键跟随，双击打开 SBC 分时图。",
        "仅展示当日进入评估池的标的，未进入池子的票不会出现在这里。",
    ),
    "名称": _tip("🏷 名称 (name)", "证券中文简称。", "名称与代码一一对应，缺失时按本地映射表回填。"),
    "现价": _tip(
        "💲 现价 (price)",
        "信号触发瞬间的分时成交价，是仓位与止损的计算基准。",
        "显示 -- 表示该条记录没有落行情（旧版本记录），不代表价格为 0。",
    ),
    "涨幅%": _tip(
        "📈 涨幅% (percent)",
        "信号发出时的当日涨幅，最新价相对昨收盘价的涨跌百分比。",
        "0%~5% 是最佳起爆区间；>6% 日内已透支，追高风险剧增；<0% 属于逆势信号，仅观察。",
    ),
    "级别": _tip(
        "🧬 梯度级别 · L0~L4",
        "按 RAR 分档给出的执行级别，级别直接决定仓位上限与进场方式。",
        "L4 主攻 30% / L3 参与 18% / L2 试仓 10% / L1 观察 4% / L0 仅记录；"
        "级别还会被大盘温度与先手时间双重封顶。",
    ),
    "RAR": _tip(
        "⚖️ RAR 风险调整分 (Risk-Adjusted Rating)",
        "综合买入位置、承接盘压、资金意图、大盘环境、相对强度，再扣除追高/拥挤/流动性风险后的总分（0~100）。",
        "分档按当日横截面分位（p98/p92/p80/p60）+ 绝对下限 68/60/52/45，当天排名越靠前级别越高，历史基准 ≥80分 为极强。",
    ),
    "位": _tip(
        "📍 位 · 位置质量 (position)",
        "买在这里的盈亏比：离止损多远、上方还有多少空间、处于日内什么位置。",
        "止损距离 2%~4.5% 最佳（太近易被扫、太远亏太多）；日内位置 0.2~0.8 加分，>0.85 顶部重罚。",
    ),
    "接": _tip(
        "🤝 接 · 承接质量 (support)",
        "拉上去之后有没有人接盘，衡量真实承接力度而不是涨幅本身。",
        "外盘买入占比 ≥60% 且五档买压 ≥60% 视为优质承接；这两项缺失时按剩余项归一，不按 0 分打死。",
    ),
    "意": _tip(
        "🎯 意 · 资金意图 (intent)",
        "拉升是果断主攻还是散户脉冲：看攻角、主力意图分、净拉升速度与增量量能。",
        "攻角 ≥70、意图分 ≥75、带量突破为佳；缺攻角/意图数据时按剩余项归一并在覆盖%里标注。",
    ),
    "环": _tip(
        "🌡 环 · 大盘环境 (regime)",
        "大盘温度、翻转状态与所属板块共振度的配合情况。",
        "45~62℃ 温和活跃最有利；<30℃ 冰点时首个排头兵最值钱；退潮期非龙头重罚。",
    ),
    "仓位%": _tip(
        "💰 建议仓位%",
        "级别基准仓位 × 温度系数 × 先手衰减系数，得到单票可用资金占比上限。",
        "单票上限 35%；组合总仓位上限 85%；L4 同时最多 2 只，超额自动降档而不是全砍。",
    ),
    "进场": _tip(
        "🚪 进场区间",
        "建议挂单或低吸的合理价格带，由当前价与 VWAP 推导。",
        "L2 只在 VWAP±0.5% 低吸不追价；L3 突破前高 2 根确认；L4 首波放量突破后回踩不破 VWAP。",
    ),
    "止损": _tip(
        "🛑 止损参考",
        "触发离场的硬性价格：底台/SBC 支撑 → 分时均价，逐级兜底。",
        "跌破即失效；L1/L2 用支撑-1.0%~VWAP-1.2%，L3/L4 用 VWAP-0.6%/支撑-0.5%。",
    ),
    "先手min": _tip(
        "⏱ 先手min (age)",
        "距离当日首次异动已过去的分钟数。先手越晚成本越高，回撤来临时操盘来不及响应，所以必须按时间衰减。",
        "≤10min 可到 L4；≤25min 封顶 L3；≤45min 封顶 L2；≤70min 封顶 L1；>70min 直接失效。",
    ),
    "来源": _tip(
        "🔗 来源 (source)",
        "这条梯度由谁产出。",
        "live_strategy = 实盘实时链路；REPLAY_BACKFILL = 按日回放回补；多来源会合并显示。",
    ),
    "更新时间": _tip(
        "🕘 更新时间",
        "该标的最后一次影子记录写入的时刻（HH:MM:SS）。",
        "超过 60 秒未更新即判定断流，此时价格与涨幅不再代表当前行情，状态栏会高亮告警。",
    ),
    "命中": _tip(
        "✅ 命中标记",
        "本次融合结论是否达到可执行梯度。",
        "✅ = 级别 ≥L2 或旧策略给出买入；空白 = 仅观察，不构成任何操作依据。",
    ),
    "覆盖%": _tip(
        "📶 覆盖% (coverage)",
        "参与加权的四轴中，有多少比例来自真实行情字段，用来判断这条结论有多可信。",
        "≥80% 视为完整；<80% 表示缺外盘/买压/攻角/意图/结构清晰度，结论标记为临时，只能作观察。",
    ),
    "MFE%": _tip(
        "🚀 MFE% 最大浮盈",
        "买入后全天最高价相对买入价的最大涨幅，衡量止盈空间。",
        "≥6% 说明有足够的止盈余量；<2% 表示上行天花板很低，不值得占仓位。",
    ),
    "MAE%": _tip(
        "🌊 MAE% 最大回撤",
        "买入后全天最低价相对买入价的最大跌幅，衡量回踩压力。",
        "回撤超过止损距离说明止损会被打掉；接近 0 说明进场点极稳。",
    ),
    "收盘%": _tip(
        "🏁 收盘收益%",
        "持有至当天收盘的收益率，衡量日内封板或承接的最终结果。",
        ">0 表示信号方向正确；显著低于 MFE 说明盘中冲高回落、止盈未执行。",
    ),
    "温度℃": _tip(
        "🌡 市场温度",
        "全市场多头情绪指标，0~100℃。",
        "<30℃ 冰点（首发排头兵最值钱）；45~62℃ 温和活跃；>65℃ 过热，非龙头容易被埋。",
    ),
    "买入": _tip("🟢 买入时间", "T+1 模拟成交的执行时间。", "仅在回放/模拟链路出现，实盘以实际成交为准。"),
    "买入价": _tip("🟢 买入价", "模拟成交价格。", "用于计算该笔交易的盈亏与回撤基准。"),
    "时段": _tip("🕒 执行时段", "成交所在的分时时间窗口。", "早盘与尾盘的滑点特征不同，复盘时需分开看。"),
    "卖出": _tip("🔴 卖出时间", "次日按 T+1 规则离场的时间。", "A 股 T+1，当日买入无法当日卖出。"),
    "卖出价": _tip("🔴 卖出价", "次日平仓成交价格。", "用于结算该笔交易的最终盈亏。"),
    "盈亏%": _tip(
        "📊 盈亏%",
        "该笔交易扣除滑点后的最终盈亏百分比。",
        ">0 盈利；<0 亏损；结合 MFE/MAE 判断是信号问题还是执行问题。",
    ),
    "当日最低%": _tip(
        "📉 当日最低%",
        "买入当日盘中承受的最大下探幅度。",
        "下探超过止损线说明当日已被扫损，但因 T+1 无法离场，属于被锁风险。",
    ),
    "被锁止损": _tip(
        "🔒 被锁止损",
        "因 T+1 规则导致日内触及止损却无法当天卖出的锁定状态。",
        "出现即说明该笔交易的风险敞口被规则放大，需在仓位设计上预留缓冲。",
    ),
    "原因": _tip("📝 离场原因", "止盈减半、止损清仓或时间到期等退场归因。", "用于统计各类离场规则的胜率与盈亏比。"),
    "入局": _tip(
        "🚩 入局时间",
        "通过发令枪与证据链确认、进入实盘入局阶段的时间。",
        "入局越早（首异动后 3~10 分钟）胜率越高；超过 20 分钟才入局多为追高。",
    ),
    "入局价": _tip("🚩 入局价", "入局确认瞬间的现价。", "作为该次跟踪的盈亏基准。"),
    "当时涨幅%": _tip("📈 当时涨幅%", "入局确认时的日内涨幅。", "3%~6% 为常见入局区间，>8% 追高风险显著。"),
    "首异动": _tip(
        "⚡ 首异动时间",
        "该股全天首次被系统捕捉到放量/形态突破的时间。",
        "首异动与入局的时间差越小，说明信号确认越快、先手越足。",
    ),
    "首异动涨幅%": _tip("⚡ 首异动涨幅%", "首次异动时的涨幅。", "首异动涨幅越低，后续空间通常越大。"),
    "首→入%": _tip(
        "➡️ 首→入%",
        "从首次异动到确认入局之间的涨幅跨度。",
        "跨度 <2% 说明入局及时；>5% 说明确认过程消耗了大部分空间。",
    ),
    "持续分": _tip(
        "🧱 持续分 (persist)",
        "异动后分时维持在均价上方与高位承接的持续性得分。",
        "≥70 走势稳健；<40 多为脉冲拉升，容易一日游。",
    ),
    "证据数": _tip("🧾 证据数", "盘中累积确认的结构性量价证据笔数。", "证据越多结论越可靠，通常 ≥3 条才算成立。"),
    "证据链": _tip("🧾 证据链", "突破形态、放量特征、板块带头等连续判断的证据明细。", "可逐条回溯，用于复盘为什么给/不给这个级别。"),
    "之后MFE%": _tip("🚀 入局后 MFE%", "入局后全天达到的最高浮动收益。", "≥5% 说明入局点选得好；接近 0 说明入局即高点。"),
}


class _TipCard(QWidget):
    """自绘深色卡片：不依赖 QSS 与系统主题，底色/对比度稳定。

    为什么不用 QLabel + QSS：带 ToolTip 标志的顶层窗口在部分环境下不会绘制
    QSS 背景，浅色文字会直接落在系统白底上（实测就是"看不清"）。
    这里改为 WA_TranslucentBackground + paintEvent 自己画圆角矩形。
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._body = QLabel(self)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setWordWrap(True)
        self._body.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.addWidget(self._body)

    def set_html(self, html: str) -> None:
        self._body.setMaximumWidth(360)
        self._body.setText(html)
        self._body.adjustSize()
        self.adjustSize()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor("#1e1f24"))
        p.setPen(QPen(QColor("#3d4048"), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)


class _KeyNavLinker(QObject):
    """上下键联动：键盘移动当前行后主动联动主图。

    为什么不只靠 selectionModel().currentChanged：
    表格每 2 秒会按影子文件变化重建，重建过程中 current 索引会被清空/恢复，
    期间键盘移动产生的 currentChanged 可能被吞掉，表现为"只有点击联动"。
    这里在按键后延迟一拍读当前行，直接联动，不依赖信号时序。
    """

    _KEYS = (
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_PageUp,
        Qt.Key.Key_PageDown,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
    )

    def __init__(self, dialog, table: QTableWidget):
        super().__init__(table)
        self.dialog = dialog
        self.table = table
        table.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            if event.type() == QEvent.Type.KeyPress and event.key() in self._KEYS:
                QTimer.singleShot(0, self._link_current)
        except Exception:
            pass
        return False

    def _link_current(self) -> None:
        try:
            row = self.table.currentRow()
            if row < 0:
                return
            code, name = self.dialog._get_row_code_name(self.table, row)
            if code:
                self.dialog._link_main_stock(code, name)
        except Exception:
            pass


class HeaderToolTip(QObject):
    """表头悬浮说明：深色卡片（对齐 TK 指标悬浮样式），替代 Qt 默认灰底纯文本提示。

    - 悬停表头即弹出「指标名 / 定义 / 判断依据」三段式卡片；
    - 自动避开屏幕边缘，鼠标移出表头立即收起；
    - 不拦截点击，不抢焦点。
    """

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table
        self._label: Optional["_TipCard"] = None
        self._hover_idx = -1
        self._pending_html = ""
        self._pending_pos = None
        header = table.horizontalHeader()
        header.setMouseTracking(True)
        header.installEventFilter(self)
        try:
            header.viewport().installEventFilter(self)
        except Exception:
            pass
        # 用"悬停 450ms"驱动卡片，不依赖 Qt 的 ToolTip 事件路由（实测会被系统提示抢走）
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.setInterval(450)
        self._delay.timeout.connect(self._show_pending)

    def _ensure_label(self) -> "_TipCard":
        if self._label is not None:
            try:
                self._label.isVisible()   # C++ 对象已被销毁时会抛 RuntimeError
                return self._label
            except RuntimeError:
                self._label = None
        self._label = _TipCard()
        return self._label

    def _hide(self) -> None:
        lbl = self._label
        if lbl is None:
            return
        try:
            if lbl.isVisible():
                lbl.hide()
        except RuntimeError:
            self._label = None

    def _show(self, gpos, html: str) -> None:
        lbl = self._ensure_label()
        lbl.set_html(html)
        w, h = lbl.width(), lbl.height()
        x, y = gpos.x() + 14, gpos.y() + 20
        try:
            screen = QApplication.screenAt(gpos) or QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            if geo is not None:
                if x + w > geo.right():
                    x = geo.right() - w - 6
                if y + h > geo.bottom():
                    y = gpos.y() - h - 10
                x = max(geo.left() + 4, x)
                y = max(geo.top() + 4, y)
        except Exception:
            pass
        lbl.move(x, y)
        lbl.show()

    def _html_at(self, obj, pos) -> str:
        """取鼠标所在列头的说明 HTML；取不到返回空串。"""
        try:
            idx = obj.logicalIndexAt(pos)
        except Exception:
            return ""
        if idx is None or idx < 0:
            return ""
        item = self.table.horizontalHeaderItem(int(idx))
        text = item.text().strip() if item is not None else ""
        return HEADER_TOOLTIPS.get(text, "")

    def _show_pending(self) -> None:
        if self._pending_html and self._pending_pos is not None:
            self._show(self._pending_pos, self._pending_html)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            et = event.type()
            if et == QEvent.Type.MouseMove:
                idx = -1
                try:
                    idx = int(obj.logicalIndexAt(event.pos()))
                except Exception:
                    idx = -1
                if idx != self._hover_idx:
                    self._hover_idx = idx
                    self._delay.stop()
                    self._hide()
                    html = self._html_at(obj, event.pos())
                    if html:
                        self._pending_html = html
                        self._pending_pos = event.globalPosition().toPoint()
                        self._delay.start()
                return False
            if et == QEvent.Type.ToolTip:
                # 系统提示一律拦掉，改由自绘卡片呈现，避免白底浅字
                html = self._html_at(obj, event.pos())
                if html:
                    self._pending_html = html
                    self._pending_pos = event.globalPos()
                    self._show_pending()
                return True
            if et in (
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Hide,
                QEvent.Type.Scroll,
            ):
                self._delay.stop()
                self._hover_idx = -1
                self._hide()
        except Exception:
            self._hide()
        return False


# 各表默认列宽（仅在从未保存过布局时使用；用户调整后由 ATS 表头持久化接管）
_DEFAULT_COL_WIDTHS: Dict[str, List[int]] = {
    "tbl_live": [56, 74, 104, 76, 78, 64, 52, 52, 52, 52, 64, 108, 78, 70, 104, 82, 52, 62],
    "tbl_replay": [70, 74, 104, 76, 78, 56, 64, 64, 64, 64, 64, 62],
    "tbl_trades": [74, 104, 64, 76, 60, 64, 76, 72, 78, 78, 200],
    "tbl_track": [74, 104, 60, 76, 84, 76, 88, 72, 64, 60, 220, 74, 64, 64],
}


_RAMDISK_DIR_CACHE: List[Optional[str]] = []


def _detect_ramdisk_dir() -> Optional[str]:
    """探测高速内存盘 (Ramdisk) 路径 (如 R:\\fusion_shadow, G:\\fusion_shadow 等)。
    若探测到有效 Ramdisk 且可写，返回对应影子快照目录，否则返回 None。

    结果进程内缓存：旧实现每次取路径都要 makedirs + 写探针文件 + 删除探针，
    在 2 秒级自动刷新下会变成高频磁盘抖动（也是 os.makedirs 被反复触发的来源）。
    """
    if _RAMDISK_DIR_CACHE:
        return _RAMDISK_DIR_CACHE[0]
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
                _RAMDISK_DIR_CACHE.append(candidate)
                return candidate
            except Exception:
                continue
    _RAMDISK_DIR_CACHE.append(None)
    return None


def _shadow_dir_candidates() -> List[str]:
    """所有可能存放影子日志的目录，按"当前运行根优先"排序。

    为什么需要多根：换构建/换部署目录后 app_root 会变，当日流水还留在旧目录，
    旧实现只读当前根 → 新版本一启动就是白板。读取时多根取最新，写入仍只写当前根。
    """
    roots: List[str] = []
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root:
        roots.append(env_root)
    try:
        from sys_utils import get_app_root  # type: ignore

        roots.append(get_app_root())
    except Exception:
        pass
    roots.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        import sys as _sys

        exe_dir = os.path.dirname(os.path.abspath(_sys.executable or ""))
        if exe_dir:
            roots.append(exe_dir)
    except Exception:
        pass
    try:
        roots.append(os.getcwd())
    except Exception:
        pass

    dirs: List[str] = []
    for root in roots:
        if not root:
            continue
        d = os.path.join(root, "logs", "fusion_shadow")
        if d not in dirs:
            dirs.append(d)
    return dirs


def _day_file_candidates(day: str) -> List[str]:
    """当日影子文件的所有候选路径（Ramdisk 优先）。"""
    d_str = day or today_str()
    out: List[str] = []
    ramdisk_dir = _detect_ramdisk_dir()
    if ramdisk_dir:
        out.append(os.path.join(ramdisk_dir, "{}.jsonl".format(d_str)))
    for d in _shadow_dir_candidates():
        p = os.path.join(d, "{}.jsonl".format(d_str))
        if p not in out:
            out.append(p)
    return out


def _resolve_day_file(day: str) -> Optional[str]:
    """当日的可读文件：多个候选里取修改时间最新的那个（Ramdisk 更新时用 Ramdisk）。"""
    best: Optional[str] = None
    best_mtime = -1.0
    for p in _day_file_candidates(day):
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                m = os.path.getmtime(p)
                if m > best_mtime:
                    best, best_mtime = p, m
        except Exception:
            continue
    return best


def _resolve_shadow_file(day: str) -> Tuple[Optional[str], str]:
    """返回 (文件路径, 实际交易日)。当日无数据时回退到最近一个有数据的交易日，永不返回白板。"""
    d_str = day or today_str()
    path = _resolve_day_file(d_str)
    if path:
        return path, d_str

    # 当日没有任何数据：找所有候选目录里最近的一个交易日文件
    newest_path: Optional[str] = None
    newest_day = ""
    newest_mtime = -1.0
    for d in _shadow_dir_candidates() + ([_detect_ramdisk_dir()] if _detect_ramdisk_dir() else []):
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for nm in names:
            if not nm.endswith(".jsonl") or nm.startswith("."):
                continue
            p = os.path.join(d, nm)
            try:
                if os.path.getsize(p) <= 0:
                    continue
                m = os.path.getmtime(p)
            except Exception:
                continue
            if m > newest_mtime:
                newest_path, newest_day, newest_mtime = p, nm[:-6], m
    return newest_path, (newest_day or d_str)


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


def _plain_tip(html: str) -> str:
    """把卡片 HTML 降级成纯文本，作为系统提示的兜底（白底黑字至少可读）。"""
    txt = re.sub(r"<br\s*/?>", "\n", html or "")
    txt = re.sub(r"</div>", "\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return txt.strip()


def _fmt_hms(ts: float) -> str:
    """epoch 秒 → HH:MM:SS；无效值返回空串。"""
    try:
        v = float(ts)
    except Exception:
        return ""
    if v <= 0:
        return ""
    try:
        return datetime.datetime.fromtimestamp(v).strftime("%H:%M:%S")
    except Exception:
        return ""


def _in_trading_session(ts: float) -> bool:
    """记录是否落在当日交易时段（09:15~15:05）。

    盘后程序仍在轮询时会产生 21:11 这类记录，直接拿来当"入局"是错的，
    赛马跟踪必须只看盘中过程。
    """
    try:
        v = float(ts)
    except Exception:
        return False
    if v <= 0:
        return False
    try:
        hm = datetime.datetime.fromtimestamp(v).strftime("%H:%M")
        return "09:15" <= hm <= "15:05"
    except Exception:
        return False


def _row_is_hit(rec: Dict[str, Any]) -> bool:
    """是否命中：L2 及以上，或旧策略给出买入。梯度层只对"命中"负责，不重复播报异动。"""
    try:
        tier = int((rec.get("fusion") or {}).get("tier") or 0)
    except Exception:
        tier = 0
    action = str((rec.get("legacy") or {}).get("action") or "")
    return bool(rec.get("hit")) or tier >= 2 or action in ("买入", "加仓", "BUY", "ADD")


def load_live_series(day: str = "", max_lines: int = 20000) -> Dict[str, List[Dict[str, Any]]]:
    """按 code 返回当日全部影子记录（时间升序），供赛马跟踪等"过程类"视图使用。

    与 `load_live_rows` 的区别：那个只保留每只票最新一条（看板用），
    这个保留整条时间序列，才能算出入局时间、入局后 MFE/MAE、持续分。
    """
    path, _src_day = _resolve_shadow_file(day)
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=max_lines)
    except Exception:
        return {}

    series: Dict[str, List[Dict[str, Any]]] = {}
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        code = str(rec.get("code") or "").split(".")[0].zfill(6)
        if not code:
            continue
        if not rec.get("name"):
            rec["name"] = name_of(code)
        series.setdefault(code, []).append(rec)
    for recs in series.values():
        recs.sort(key=lambda r: float(r.get("ts") or 0.0))
    return series


def _record_key(rec: Dict[str, Any]) -> Tuple[str, float]:
    code = str(rec.get("code") or "").split(".")[0].zfill(6)
    try:
        ts = round(float(rec.get("ts") or 0.0), 3)
    except Exception:
        ts = 0.0
    return (code, ts)


def _merge_records(path: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把新记录并入已有流水：按 (code, ts) 去重追加，绝不丢弃已有行。

    旧实现是"用新列表整体覆盖文件"，收盘沉淀与回放回补都会把当日几万行流水
    截断成几十行（10-23 的文件只剩 772 字节就是这么来的）。
    """
    kept: List[Dict[str, Any]] = []
    seen = set()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    key = _record_key(rec)
                    if key in seen:
                        continue
                    seen.add(key)
                    kept.append(rec)
    except Exception as exc:
        logger.debug("[FusionLadder] 合并读取旧流水失败: %s", exc)

    added = 0
    for rec in records:
        key = _record_key(rec)
        if key in seen:
            continue
        seen.add(key)
        kept.append(rec)
        added += 1
    logger.debug("[FusionLadder] 影子流水合并: 已有 %d 行, 新增 %d 行", len(kept) - added, added)
    return kept


def _atomic_write_lines(path: str, records: List[Dict[str, Any]]) -> None:
    """对齐 ATS 底层持久化：目录跨进程写锁 + Windows 共享冲突重试 + 原子替换。"""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_p = path + ".tmp"
    try:
        from ats.persistence_lock import directory_write_lock, replace_with_retry

        with directory_write_lock(directory, timeout=2.0):
            with open(tmp_p, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            replace_with_retry(tmp_p, path)
    except Exception:
        # 锁不可用（被其他进程占用超时）时，退回无锁原子替换，绝不静默丢数据
        try:
            with open(tmp_p, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
            os.replace(tmp_p, path)
        finally:
            if os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass


def persist_shadow_records(records: List[Dict[str, Any]], day: str = "", merge: bool = True) -> int:
    """双通道原子持久化：同时写入 Ramdisk (微秒级) 与 logs/fusion_shadow (高可靠物理落盘)

    merge=True（默认）时与已有流水合并后落盘，只追加不截断。
    写入走 ATS 统一的目录写锁 + Windows 重试，避免被占用时静默失败。
    """
    if not records:
        return 0
    primary, ramdisk = _shadow_storage_paths(day)
    payload = _merge_records(primary, records) if merge else list(records)

    # 1. 写入 Ramdisk (高速内存虚拟盘，实盘零阻塞防崩溃)
    if ramdisk:
        try:
            _atomic_write_lines(ramdisk, payload)
        except Exception as e:
            logger.debug(f"[FusionLadder] Ramdisk 写入异常: {e}")

    # 2. 写入物理主落盘 logs/fusion_shadow/{day}.jsonl
    try:
        _atomic_write_lines(primary, payload)
    except Exception as e:
        logger.warning(f"[FusionLadder] 主落盘写入异常: {e}")

    return len(records)


def load_live_rows(day: str = "", max_lines: int = 5000, allow_fallback: bool = True) -> List[Dict[str, Any]]:
    """读影子日志（多根取最新），按 code 取最新一条，按级别+RAR 排序。

    allow_fallback=True 时，当日无数据会回退到最近一个有数据的交易日，
    并在每行打上 `_source_day`，由界面显式标注"展示的是哪一天"，不伪装成今日数据。
    """
    if allow_fallback:
        target_path, src_day = _resolve_shadow_file(day)
    else:
        target_path, src_day = _resolve_day_file(day), (day or today_str())

    if not target_path or not os.path.exists(target_path):
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
    for r in rows:
        r["_source_day"] = src_day
        r["_source_file"] = target_path
    rows.sort(key=lambda r: (int((r.get("fusion") or {}).get("tier") or 0),
                             float((r.get("fusion") or {}).get("rar") or 0)), reverse=True)
    return rows


class _ReplayCancelled(Exception):
    """用户/退出流程取消回放时，用于从进度回调里快速退出。"""


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

    def _on_progress(self, cur: int, total: int) -> None:
        # 进度回调是唯一贯穿全程的钩子：在这里响应取消，退出时才能及时收敛线程
        if self.isInterruptionRequested():
            raise _ReplayCancelled()
        self.progress.emit(cur, total)

    def run(self) -> None:  # noqa: D401
        try:
            rp = DayReplay(config=ReplayConfig(
                top_n=self.top_n, step=self.step,
                focus_codes=tuple(self.focus), cuts_mode=self.cuts_mode,
            ))
            if not rp.cache:
                self.failed.emit("找不到分钟线缓存（cct ramdisk: minute_kline_cache.pkl）")
                return
            day = self.day or (rp.days()[-1] if rp.days() else today_str())
            result = rp.run_day(day, progress=self._on_progress, focus=self.focus)
            self.done.emit(result)
        except _ReplayCancelled:
            logger.info("[FusionLadder] 回放已按请求中断")
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

        # 实时梯度自动刷新：2s 巡检一次，仅在影子文件真的变化时重绘（静止不重绘，零额外开销）
        self._live_sig = None
        self._last_init_scan_t = 0.0
        self._init_scan_started = False
        self._replay_backfill_started = False
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._auto_refresh_live)
        self._live_timer.start(2000)

        # 启动即初始化：每次打开窗口都保证跑一次（非交易时段自动豁免），绝不白板
        QTimer.singleShot(1200, self._startup_init_scan)

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

        # 只看命中：梯度层是"打分命中"，不是把异动列表再显示一遍。
        # 文字里不带 ✅（勾号会和复选框状态混淆），改用颜色表达选中态。
        self.chk_hit_only = QCheckBox("只看命中")
        self.chk_hit_only.setToolTip(
            "只显示 L2 及以上（或旧策略给出买入）的命中标的。\n"
            "关掉可看全池梯度分布，用于观察 L0/L1 的边缘标的。"
        )
        try:
            self.chk_hit_only.setChecked(bool(load_config_node("fusion_ladder_hit_only", False)))
        except Exception:
            pass
        self.chk_hit_only.toggled.connect(self._on_hit_only_toggled)
        self._style_hit_only(self.chk_hit_only.isChecked())
        bar.addWidget(self.chk_hit_only)

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
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        # Tab 0: 实时梯度 [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源, 更新时间, 命中, 覆盖%]
        self.tbl_live = self._create_interactive_table([
            "级别", "代码", "名称", "现价", "涨幅%", "RAR", "位", "接", "意", "环", "仓位%", "进场", "止损", "先手min", "来源",
            "更新时间", "命中", "覆盖%",
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

        # 💡 设置字典级专业列头 ToolTip（富文本三段式，供自绘卡片使用；
        #    系统提示只放纯文本兜底，避免白底浅字看不清）
        for col_idx, h_name in enumerate(headers):
            item = tbl.horizontalHeaderItem(col_idx)
            if item:
                tip = HEADER_TOOLTIPS.get(h_name) or _tip(
                    h_name, "该列的数值含义。", "点击列头可按数值升/降序切换排序。"
                )
                item.setToolTip(_plain_tip(tip))

        # 🖱 深色卡片式表头悬浮说明（对齐 TK 指标悬浮样式）
        try:
            tbl._header_tip = HeaderToolTip(tbl)
        except Exception as exc:
            logger.debug("[FusionLadder] 表头悬浮说明挂载失败 %s: %s", name, exc)

        # 🔗 直接复用 ATS 成熟的表头持久化（列宽/列序/隐藏 + 退出前 flush），不重复实现。
        # 用独立布局文件：window_config.json 会被其他窗口/退出流程反复整体重写，
        # 与本窗口的异步布局写入互相覆盖，正是"重启 ATS 后列宽丢失"的根因之一。
        try:
            from ats.ui.styles import setup_header_persistence
            from sys_utils import get_app_root, get_conf_path

            layout_path = get_conf_path("fusion_ladder_layout.json", get_app_root())
            setup_header_persistence(
                tbl,
                config_key="fusion_ladder_{}_state".format(name),
                default_widths=_DEFAULT_COL_WIDTHS.get(name),
                storage_path=layout_path,
            )
            # 恢复完成后重新套用极窄模式，避免历史隐藏状态覆盖当前模式
            flt = getattr(tbl, "_show_event_filter", None)
            if flt is not None:
                prev_cb = getattr(flt, "restore_callback", None)

                def _restore_then_narrow(_prev=prev_cb):
                    if callable(_prev):
                        _prev()
                    self._apply_all_narrow_modes()

                flt.restore_callback = _restore_then_narrow

            # 🛡️ 落盘兜底：TK 主循环退出时 Qt 的 aboutToQuit 不一定会触发，
            # 只靠退出前 flush 会让"重启 ATS 后列宽丢失"。这里在调整结束后主动 flush。
            from ats.ui.styles import flush_config_writer

            _flush_timer = QTimer(tbl)
            _flush_timer.setSingleShot(True)
            _flush_timer.setInterval(800)

            def _persist_layout_now(_tbl=tbl):
                try:
                    _tbl.save_header_state(sync=True)
                    flush_config_writer(timeout_sec=1.0)
                except Exception as exc:
                    logger.debug("[FusionLadder] 布局落盘失败 %s: %s", name, exc)

            _flush_timer.timeout.connect(_persist_layout_now)
            _hdr = tbl.horizontalHeader()
            _hdr.sectionResized.connect(lambda *_: _flush_timer.start())
            _hdr.sectionMoved.connect(lambda *_: _flush_timer.start())
            tbl._layout_flush_timer = _flush_timer
        except Exception as exc:
            logger.debug("[FusionLadder] 表头持久化挂载失败 %s: %s", name, exc)

        # 1. 鼠标点击联动
        tbl.itemClicked.connect(self._on_table_item_clicked)
        # 2. 键盘上下键行移动联动
        tbl.selectionModel().currentChanged.connect(
            lambda cur, prev, t=tbl: self._on_table_current_changed(t, cur)
        )
        # 2b. 键盘联动兜底：重建表格期间 currentChanged 可能被吞，按键后主动补一次
        tbl._key_nav_linker = _KeyNavLinker(self, tbl)
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
        code = str(code or "").split(".")[0].zfill(6)
        if not code or code == "000000":
            return
        # 去重：表格每 2 秒重建会重新 selectRow，若不去重会反复联动同一只票、
        # 把主图刷得来回跳，用户就会觉得"键盘联动没生效"。
        if getattr(self, "_last_link_code", "") == code:
            return
        self._last_link_code = code
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

    def _on_hit_only_toggled(self, checked: bool) -> None:
        try:
            save_config_node("fusion_ladder_hit_only", bool(checked))
        except Exception:
            pass
        self._style_hit_only(bool(checked))
        self._render_live(force=True)

    def _style_hit_only(self, checked: bool) -> None:
        """选中态用颜色表达：走窗口 QSS 的属性选择器，避免覆盖原生指示器样式。"""
        try:
            self.chk_hit_only.setProperty("hitOnly", "true" if checked else "false")
            st = self.chk_hit_only.style()
            st.unpolish(self.chk_hit_only)
            st.polish(self.chk_hit_only)
            self.chk_hit_only.update()
        except Exception:
            pass

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

            # 只读当日文件，绝不把"回退展示的其他交易日"写进今天
            live_rows = load_live_rows(day, allow_fallback=False)
            if live_rows:
                # 双通道持久化（合并语义，保留当日全量流水不被截断）
                persist_shadow_records(live_rows, day)

            store.close_day(
                day,
                phase_path=[{"time": "15:00", "phase": "收盘完成", "note": f"有效梯度标的{len(live_rows)}只"}],
                amount_wan=None,
                # 巡检不测资金量能：传 None 而不是占位 1.0，避免覆盖回放算出的真实比值
                capital_ratio=None,
            )
            try:
                handoff_data = store.handoff(day)
                logger.info(f"[FusionLadderDialog] 今日收盘上下文已自动沉淀并完成次日交接: {handoff_data.get('label')}")
            except Exception:
                pass

            self._last_auto_settle_day = day
            save_config_node("fusion_last_auto_settle_day", day)
            self.lbl_status.setText(f"✅ 今日收盘上下文已自动沉淀 (session_ctx/{day}.json)")

            # 收盘后补跑当日回放：T+1 订单 / 信号面板 / 验收复盘 三张表的数据源是回放结果，
            # 实盘影子流不产生成交，不补跑就会一直是空的。
            self._maybe_auto_replay_after_close(day)
        except Exception as e:
            logger.warning(f"[FusionLadderDialog] 收盘沉淀失败: {e}")

    def _maybe_auto_replay_after_close(self, day: str) -> None:
        """收盘后自动回放一次，把 T+1/信号面板/验收 三张表补齐（每日一次，可配置关闭）。"""
        try:
            if not bool(load_config_node("fusion_auto_replay_after_close", True)):
                return
            if getattr(self, "_auto_replay_day", "") == day:
                return
            if self._worker is not None and self._worker.isRunning():
                return
            result = self._result
            if result is not None and str(getattr(result, "day", "")) == day:
                return
            idx = self.cmb_day.findText(day)
            if idx >= 0 and self.cmb_day.currentText().strip() != day:
                self.cmb_day.setCurrentIndex(idx)
            self._auto_replay_day = day
            logger.info("[FusionLadder] 收盘后自动回放 %s：补齐 T+1/信号面板/验收复盘", day)
            self._start_worker([])
            self.lbl_status.setText(f"状态：今日收盘上下文已自动沉淀，自动回放 {day} 中…")
        except Exception as exc:
            logger.warning("[FusionLadder] 收盘后自动回放触发失败: %s", exc)

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
        self._render_live(force=True)

    def _live_source_signature(self, day: str) -> tuple:
        """影子文件指纹：路径 + 大小 + 修改时间。用于判断是否需要重绘。"""
        try:
            path, src_day = _resolve_shadow_file(day)
            if not path or not os.path.exists(path):
                return (day, "", 0, 0.0)
            st = os.stat(path)
            return (day, path, st.st_size, round(st.st_mtime, 3))
        except Exception:
            return (day, "", 0, 0.0)

    def _auto_refresh_live(self) -> None:
        """定时静默刷新：只有影子文件真的变了才重绘，避免无谓重建表格。"""
        if getattr(self, "_is_closing", False) or not self.isVisible():
            return
        idx = self.tabs.currentIndex()
        if idx not in (0, 3):
            return
        if self._worker is not None:
            return
        day = self.cmb_day.currentText().strip() or today_str()
        sig = self._live_source_signature(day)
        if sig == getattr(self, "_live_sig", None):
            self._maybe_ensure_data()
            return
        if idx == 3:
            self._live_sig = sig
            self._render_track_from_shadow(day)
            return
        self._render_live(force=False)

    # ------------------------------------------------------------------
    # 初始化扫描（永远执行一次；非交易时段豁免；永不白板）
    # ------------------------------------------------------------------
    def _is_trading_window(self) -> bool:
        """交易时段判定：工作日 09:15~15:05（非交易时段豁免自动扫描）。"""
        try:
            now = datetime.datetime.now()
            if now.weekday() >= 5:
                return False
            hm = now.strftime("%H:%M")
            if not ("09:15" <= hm <= "15:05"):
                return False
            try:
                from ats.tdx_realtime_fetcher import TDXGlobalCachePool

                today = now.strftime("%Y-%m-%d")
                return bool(TDXGlobalCachePool.is_trading_day(today))
            except Exception:
                return True
        except Exception:
            return False

    def _trigger_host_scan(self) -> bool:
        """请宿主（TK 主控 / ATS 主窗）跑一轮实时逻辑扫描，产出影子记录。"""
        targets = []
        parent = getattr(self, "_py_parent", None)
        if parent is not None:
            targets.append(parent)
            for attr in ("master", "app", "_tk_app", "_root_window"):
                obj = getattr(parent, attr, None)
                if obj is not None:
                    targets.append(obj)
        if not targets:
            # TK 入口打开窗口时 parent 传 None，这里回落到主控全局实例
            try:
                import instock_MonitorTK as _tk

                app_inst = getattr(_tk, "_global_app_instance", None)
                if app_inst is not None:
                    targets.append(app_inst)
            except Exception:
                pass
        for obj in targets:
            fn = getattr(obj, "_run_live_strategy_process", None)
            if not callable(fn):
                continue
            try:
                schedule = getattr(obj, "_schedule_after", None)
                if callable(schedule):
                    schedule(0, lambda f=fn: f(manual_scan=True))
                else:
                    fn(manual_scan=True)
                logger.info("[FusionLadder] 已请求宿主执行一轮实时逻辑扫描（初始化）")
                return True
            except Exception as exc:
                logger.debug("[FusionLadder] 触发宿主扫描失败: %s", exc)
        return False

    def _startup_init_scan(self) -> None:
        """窗口打开后的初始化：先渲染已有数据，再确保交易时段内至少跑过一轮扫描。"""
        try:
            self._render_live(force=True)
        except Exception as exc:
            logger.debug("[FusionLadder] 首次渲染异常: %s", exc)
        try:
            if not self._is_trading_window():
                logger.info("[FusionLadder] 非交易时段，跳过初始化扫描（豁免）")
                return
            self._init_scan_started = True
            self._maybe_ensure_data()
        except Exception as exc:
            logger.warning("[FusionLadder] 初始化扫描异常: %s", exc)

    def _maybe_ensure_data(self) -> None:
        """交易时段内：当日无数据或数据断流超过 180s 时，自动拉起一次初始化扫描（5 分钟限频）。"""
        if not self._is_trading_window():
            return
        if self._worker is not None and self._worker.isRunning():
            return
        day = self.cmb_day.currentText().strip() or today_str()
        rows = load_live_rows(day, allow_fallback=False)
        has_data = bool(rows)
        if has_data:
            try:
                latest = max(float(r.get("ts") or 0.0) for r in rows)
            except Exception:
                latest = 0.0
            if latest > 0 and (time.time() - latest) <= 180:
                return
        now = time.time()
        if (now - float(getattr(self, "_last_init_scan_t", 0.0) or 0.0)) < 300:
            return
        self._last_init_scan_t = now
        if self._trigger_host_scan():
            self.lbl_status.setText("状态：{} 已请求主程序执行一轮逻辑扫描，等待影子数据…".format(day))
            self.lbl_status.setStyleSheet("color:#ffd75e; font-weight:bold;")
            return
        # 宿主没有扫描入口时不自动跑全市场回放：回放要加载全量分钟缓存，
        # 与实时扫描抢 CPU，且线程长跑难以在退出时收敛。这里给出明确指引，仍不白板。
        self.lbl_status.setText(
            "状态：{} 未找到主程序扫描入口｜请确认主程序在运行，或点 [▶ 跑回放(回补)] 初始化".format(day)
        )
        self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")

    def _render_live(self, force: bool = True) -> None:
        day = self.cmb_day.currentText().strip() or today_str()
        sig = self._live_source_signature(day)
        if not force and sig == getattr(self, "_live_sig", None):
            return
        rows = load_live_rows(day)
        tbl = self.tbl_live
        total_rows = len(rows)
        hit_only = bool(getattr(self, "chk_hit_only", None) is not None and self.chk_hit_only.isChecked())
        if hit_only and rows:
            rows = [r for r in rows if _row_is_hit(r)]
            if not rows:
                tbl.setSortingEnabled(False)
                tbl.setRowCount(0)
                tbl.insertRow(0)
                it = self._num_item("当前无命中（L2 及以上）——取消勾选 [只看命中] 可查看全池 L0/L1 梯度", "no_hit")
                it.setForeground(QColor("#ffa64d"))
                tbl.setItem(0, 0, it)
                for c in range(1, tbl.columnCount()):
                    tbl.setItem(0, c, self._num_item("", 0))
                tbl.setSpan(0, 0, 1, max(1, tbl.columnCount()))
                self.lbl_status.setText(
                    "状态：{} 全池 {} 条｜命中 0｜等待 L2+ 信号（取消勾选可看全池）".format(day, total_rows)
                )
                self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")
                tbl.setSortingEnabled(True)
                return

        # 保留滚动位置与当前选中代码，避免定时刷新把用户视线拽走
        scroll = tbl.verticalScrollBar().value()
        had_focus = tbl.hasFocus()
        selected_code = ""
        try:
            cur = tbl.currentRow()
            if cur >= 0:
                selected_code = self._get_row_code_name(tbl, cur)[0]
        except Exception:
            selected_code = ""

        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        self._live_sig = sig
        if not rows:
            # 永不白板：放一行占位说明，并按交易时段自动拉起初始化
            tbl.insertRow(0)
            hint = ("正在初始化扫描…（交易时段会自动拉起一轮逻辑扫描，无需手动操作）"
                    if self._is_trading_window() else
                    "非交易时段暂无当日记录：{} 无影子数据，可点 [▶ 跑回放(回补)] 生成".format(day))
            it = self._num_item(hint, hint)
            it.setForeground(QColor("#ffa64d"))
            tbl.setItem(0, 0, it)
            for c in range(1, tbl.columnCount()):
                tbl.setItem(0, c, self._num_item("", 0))
            tbl.setSpan(0, 0, 1, max(1, tbl.columnCount()))
            self.lbl_status.setText("状态：{} 暂无影子记录｜{}".format(day, "初始化中" if self._is_trading_window() else "非交易时段"))
            self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")
            tbl.setSortingEnabled(True)
            self._maybe_ensure_data()
            return

        source_day = str(rows[0].get("_source_day") or day)
        # 写盘进程版本自检：旧版本写的记录没有 price/pct/coverage，
        # 界面必须直接说明"是 exe 旧"而不是让用户以为数据没更新。
        try:
            schema_ver = int(rows[0].get("schema") or 0)
        except Exception:
            schema_ver = 0
        schema_note = "" if schema_ver >= 2 else "｜⚠ 记录由旧版 exe 写入（无现价/涨幅/覆盖），请更新 exe"
        writer_note = ""
        try:
            _wexe = str(rows[0].get("writer_exe") or "")
            _wpid = rows[0].get("writer_pid")
            if _wexe:
                writer_note = "｜写:{}".format(_wexe if not _wpid else "{}#{}".format(_wexe, _wpid))
        except Exception:
            writer_note = ""

        tier_count = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        coverage_sum = 0.0
        coverage_n = 0
        latest_ts = 0.0
        hit_count = 0
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

            # 现价/涨幅必须来自真实落盘行情；缺失就显示 "--"，绝不伪造成 0.00%
            raw_price = r.get("price")
            raw_pct = r.get("pct")
            price = float(raw_price) if isinstance(raw_price, (int, float)) else 0.0
            pct = float(raw_pct) if isinstance(raw_pct, (int, float)) else None
            price_txt = "{:.2f}".format(price) if price > 0 else "--"
            pct_txt = "{:+.2f}%".format(pct) if pct is not None else "--"

            ts = float(r.get("ts") or 0.0)
            latest_ts = max(latest_ts, ts)
            time_txt = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts > 0 else "--"

            cov = r.get("coverage")
            if cov is None:
                cov = fusion.get("coverage")
            cov_val = float(cov) if isinstance(cov, (int, float)) else 0.0
            if isinstance(cov, (int, float)):
                coverage_sum += cov_val
                coverage_n += 1

            legacy_action = str((r.get("legacy") or {}).get("action") or "")
            hit = bool(r.get("hit")) or tier >= 2 or legacy_action in ("买入", "加仓", "BUY", "ADD")
            if hit:
                hit_count += 1

            pct_color = QColor("#c8c8d0") if pct is None else (QColor("#ff5c5c") if pct >= 0 else QColor("#00ff88"))

            # 各列严格接入 NumericTableWidgetItem 保证高精度数值排序
            # 表头: [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源, 更新时间, 命中, 覆盖%]
            tbl.setItem(i, 0, self._num_item(f"L{tier}", tier, _TIER_COLORS.get(tier), bold=True))
            tbl.setItem(i, 1, self._num_item(code, code))
            tbl.setItem(i, 2, self._num_item(name, name))
            tbl.setItem(i, 3, self._num_item(price_txt, price))
            tbl.setItem(i, 4, self._num_item(pct_txt, pct if pct is not None else 0.0, color=pct_color, bold=True))
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
            tbl.setItem(i, 15, self._num_item(time_txt, ts))
            tbl.setItem(i, 16, self._num_item("✅" if hit else "", 1 if hit else 0,
                                             color=QColor("#ffd24d") if hit else None, bold=hit))
            tbl.setItem(i, 17, self._num_item(f"{cov_val * 100:.0f}%", cov_val,
                                              color=QColor("#8fd18f") if cov_val >= 0.8 else QColor("#ffa64d")))

        tbl.setSortingEnabled(True)

        if selected_code:
            try:
                for r_i in range(tbl.rowCount()):
                    if self._get_row_code_name(tbl, r_i)[0] == selected_code:
                        tbl.selectRow(r_i)
                        break
            except Exception:
                pass
        try:
            tbl.verticalScrollBar().setValue(scroll)
        except Exception:
            pass
        if had_focus:
            # 重建后把焦点还给表格，否则方向键会落到别的控件上，联动就"失灵"了
            try:
                tbl.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        cov_avg = (coverage_sum / coverage_n) if coverage_n else 0.0
        now_txt = datetime.datetime.now().strftime("%H:%M:%S")
        stale = ""
        if latest_ts > 0:
            age_s = time.time() - latest_ts
            if age_s > 60:
                stale = "｜⚠ 最新记录已 {}s 未更新".format(int(age_s))
        day_note = ""
        if source_day and source_day != day:
            day_note = "｜⚠ 今日暂无记录，展示 {} 数据".format(source_day)
        count_txt = ("命中 {} / 共 {} 条".format(len(rows), total_rows) if hit_only
                     else "影子 {} 条".format(len(rows)))
        self.lbl_status.setText(
            "状态：{} {}｜L4 {} / L3 {} / L2 {} / L1 {} / L0 {}｜命中 {}｜覆盖 {:.0f}%｜刷新 {}{}{}{}{}".format(
                day, count_txt, tier_count[4], tier_count[3], tier_count[2], tier_count[1], tier_count[0],
                hit_count, cov_avg * 100, now_txt, stale, day_note, schema_note, writer_note,
            )
        )
        warn = bool(stale or day_note or schema_note)
        self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;" if warn else "color:#8fd18f; font-weight:bold;")

    # ------------------------------------------------------------------
    # 赛马跟踪（实盘影子流直出，不依赖回放）
    # ------------------------------------------------------------------
    def _track_entries_from_shadow(self, day: str) -> List[Dict[str, Any]]:
        """从当日影子时间序列还原"第一波入局"清单。

        入局口径：该票当日首次达到 L2（可执行梯度）的那一条记录。
        入局后 MFE/MAE/收盘% 用后续记录里的真实 price 计算，不依赖回放。
        """
        series = load_live_series(day)
        out: List[Dict[str, Any]] = []
        for code, recs in series.items():
            # 只保留盘中记录：盘后轮询写进来的 21:xx 记录不能当作"入局"
            recs = [r for r in recs if _in_trading_session(r.get("ts"))]
            if not recs:
                continue
            entry_i = None
            for i, r in enumerate(recs):
                try:
                    tier = int((r.get("fusion") or {}).get("tier") or 0)
                except Exception:
                    tier = 0
                if tier >= 2:
                    entry_i = i
                    break
            if entry_i is None:
                continue
            first = recs[0]
            entry = recs[entry_i]
            ep = float(entry.get("price") or 0.0)
            after = recs[entry_i:]
            prices = [float(x.get("price") or 0.0) for x in after if float(x.get("price") or 0.0) > 0]
            mfe = mae = close_ret = 0.0
            if ep > 0 and prices:
                mfe = (max(prices) - ep) / ep * 100.0
                mae = (min(prices) - ep) / ep * 100.0
                close_ret = (prices[-1] - ep) / ep * 100.0
            keep = 0
            for x in after:
                try:
                    t = int((x.get("fusion") or {}).get("tier") or 0)
                except Exception:
                    t = 0
                if t >= 1:
                    keep += 1
            ev = list((entry.get("fusion") or {}).get("evidence") or [])
            out.append({
                "code": code,
                "name": entry.get("name") or name_of(code),
                "tier": int((entry.get("fusion") or {}).get("tier") or 0),
                "enter_ts": float(entry.get("ts") or 0.0),
                "enter_price": ep,
                "enter_pct": float(entry.get("pct") or 0.0),
                "first_ts": float(first.get("ts") or 0.0),
                "first_pct": float(first.get("pct") or 0.0),
                "since_first": float(entry.get("pct") or 0.0) - float(first.get("pct") or 0.0),
                "persist": round(keep * 100.0 / max(1, len(after)), 1),
                "evidence_n": len(ev),
                "chain": " · ".join(ev)[:160],
                "mfe": mfe,
                "mae": mae,
                "close_ret": close_ret,
            })
        out.sort(key=lambda e: (-e["tier"], -e["persist"]))
        return out

    def _render_track_from_shadow(self, day: str) -> None:
        t3 = self.tbl_track
        entries = self._track_entries_from_shadow(day)
        t3.setSortingEnabled(False)
        t3.setRowCount(0)
        if not entries:
            self._fill_table_hint(
                t3,
                "今日暂无 L2+ 入局（赛马跟踪只收录命中 L2 及以上的标的）。"
                "若要看全池过程，请在[实时梯度]取消勾选[只看命中]。",
            )
            t3.setSortingEnabled(True)
            return
        for e in entries:
            i = t3.rowCount()
            t3.insertRow(i)
            ret = float(e.get("close_ret") or 0.0)
            color = QColor("#ff5c5c") if ret >= 0 else QColor("#00ff88")
            t3.setItem(i, 0, self._num_item(e["code"], e["code"]))
            t3.setItem(i, 1, self._num_item(e["name"], e["name"]))
            t3.setItem(i, 2, self._num_item(_fmt_hms(e["enter_ts"]), e["enter_ts"]))
            t3.setItem(i, 3, self._num_item(f"{e['enter_price']:.2f}" if e["enter_price"] > 0 else "--", e["enter_price"]))
            t3.setItem(i, 4, self._num_item(f"{e['enter_pct']:+.2f}%", e["enter_pct"]))
            t3.setItem(i, 5, self._num_item(_fmt_hms(e["first_ts"]), e["first_ts"]))
            t3.setItem(i, 6, self._num_item(f"{e['first_pct']:+.2f}%", e["first_pct"]))
            t3.setItem(i, 7, self._num_item(f"{e['since_first']:+.2f}%", e["since_first"]))
            t3.setItem(i, 8, self._num_item(e["persist"], float(e["persist"]), bold=True))
            t3.setItem(i, 9, self._num_item(e["evidence_n"], int(e["evidence_n"])))
            t3.setItem(i, 10, self._num_item(e["chain"], e["chain"]))
            t3.setItem(i, 11, self._num_item(f"{e['mfe']:+.2f}%", e["mfe"], color=color))
            t3.setItem(i, 12, self._num_item(f"{e['mae']:+.2f}%", e["mae"]))
            t3.setItem(i, 13, self._num_item(f"{ret:+.2f}%", ret, color=color, bold=True))
        t3.setSortingEnabled(True)

    def _fill_table_hint(self, tbl: QTableWidget, text: str) -> None:
        """空表占位：写清"为什么没有数据"，不留白板。"""
        tbl.setRowCount(0)
        tbl.insertRow(0)
        it = self._num_item(text, text)
        it.setForeground(QColor("#ffa64d"))
        tbl.setItem(0, 0, it)
        for c in range(1, tbl.columnCount()):
            tbl.setItem(0, c, self._num_item("", 0))
        try:
            tbl.setSpan(0, 0, 1, max(1, tbl.columnCount()))
        except Exception:
            pass

    def _on_tab_changed(self, index: int) -> None:
        day = self.cmb_day.currentText().strip() or today_str()
        if index == 3:
            try:
                self._render_track_from_shadow(day)
            except Exception as exc:
                logger.debug("[FusionLadder] 赛马跟踪渲染失败: %s", exc)
        elif index == 2 and self.tbl_trades.rowCount() == 0:
            self._fill_table_hint(
                self.tbl_trades,
                "T+1 订单由回放撮合产生：实盘影子流不下单。点 [▶ 跑回放(回补)] 后这里显示当日模拟成交。",
            )
        elif index == 4 and not self.txt_panel.toPlainText().strip():
            self.txt_panel.setPlainText(
                "信号面板由回放统计生成。实盘阶段可先看[实时梯度]与[赛马跟踪]；"
                "收盘后点 [▶ 跑回放(回补)] 即可得到完整统计。"
            )

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
        # 进程退出时若回放线程仍在跑，QThread 被销毁会触发 Qt Fatal；退出前做一次有界等待
        try:
            import atexit

            atexit.register(self._wait_worker_on_exit)
        except Exception:
            pass

    def _wait_worker_on_exit(self) -> None:
        try:
            w = self._worker
            if w is not None and w.isRunning():
                w.requestInterruption()
                w.wait(3000)
        except Exception:
            pass

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
                    # 回补记录必须与实盘记录同构：否则界面会把它当成"旧版 exe 写入"，
                    # 覆盖% / 命中 / 证据链也会集体缺失。
                    "schema": 2,
                    "writer_pid": 0,
                    "writer_exe": "REPLAY_BACKFILL",
                    "ts": float(r.get("ts") or time.time()),
                    "code": cd,
                    "name": r.get("name") or name_of(cd),
                    "price": entry_p,
                    "pct": pct_val,
                    "trade_date": day,
                    "hit": bool(tier >= 2),
                    "coverage": 1.0,
                    "fusion": {
                        "tier": tier,
                        "tier_name": str(r.get("tier_name") or ""),
                        "rar": rar,
                        "size_pct": float(r.get("size_pct") or 0.0),
                        "age_min": float(r.get("age_min") or 0.0),
                        "coverage": 1.0,
                        "provisional": False,
                        "entry": {"price_lo": entry_p, "price_hi": entry_p},
                        "stop": {"price": r.get("stop") or "-"},
                        "axes": {
                            "position": float((r.get("axes") or {}).get("position") or 50.0),
                            "support": float((r.get("axes") or {}).get("support") or 50.0),
                            "intent": float((r.get("axes") or {}).get("intent") or 50.0),
                            "regime": float((r.get("axes") or {}).get("regime") or 50.0),
                            "relative": float((r.get("axes") or {}).get("relative") or 50.0),
                            "penalty": float((r.get("axes") or {}).get("penalty") or 0.0),
                            "rar": rar,
                        },
                        "evidence": list(r.get("evidence") or [])[:6],
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
                capital_ratio=None,
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
            # 有界等待，避免 QThread 在运行中被销毁（进程退出时的 Qt Fatal）
            try:
                self._worker.requestInterruption()
                self._worker.wait(2000)
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


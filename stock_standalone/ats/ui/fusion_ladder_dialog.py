# -*- coding: utf-8 -*-
"""ats/ui/fusion_ladder_dialog.py — 融合梯度监视器（所见即所得）。

三个页签对应三种"看得见"：
    1. 实时梯度：直接读 `logs/fusion_shadow/<day>.jsonl`，按选择日期加载，支持实盘与回补数据呈现；
    2. 按日回放：历史结果写入独立迭代档案；
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
    - 迭代档案与生产影子流、会话快照分开保存。
"""

from __future__ import annotations

import datetime
from html import escape
import gzip
import json
import logging
import os
import re
import time
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from PyQt6.QtCore import (
    QDate,
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
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QKeyEvent, QPainter, QPalette, QPen, QTextCharFormat, QTextLayout
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QDialog,
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
    QSizePolicy,
    QStyle,
    QStyleOptionViewItem,
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
from ats.ui.fusion_focus_item import FusionFocusItem
from ats.ui.styles import (
    ColorPreservingItemDelegate,
    NumericTableWidgetItem,
    load_config_node,
    save_config_node,
    save_config_node_async,
    save_config_nodes_async,
    set_seamless_stay_on_top,
)
from global_favorites import GlobalFavoriteManager
from tk_gui_modules.window_mixin import WINDOW_CONFIG_FILE, WindowMixin

logger = logging.getLogger(__name__)


def _change_color(value):
    try:
        number = float(value)
        if not np.isfinite(number) or number == 0:
            return None
        return QColor("#ff5c5c" if number > 0 else "#00ff88")
    except (TypeError, ValueError, OverflowError):
        return None


class SignedPercentDelegate(ColorPreservingItemDelegate):
    """同一轨迹单元格中逐个百分比着色，保留原文本、排序和选中背景。"""
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        text = opt.fontMetrics.elidedText(opt.text, opt.textElideMode, max(0, rect.width()))
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        layout = QTextLayout(text, opt.font)
        formats = []
        for match in re.finditer(r"[+-]?\d+(?:\.\d+)?%", text):
            color = _change_color(match.group()[:-1])
            if color is not None:
                span = QTextLayout.FormatRange()
                span.start, span.length = match.start(), len(match.group())
                span.format.setForeground(color)
                formats.append(span)
        layout.setFormats(formats)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(max(0, rect.width()))
        layout.endLayout()
        painter.save()
        painter.setClipRect(rect)
        painter.setPen(opt.palette.color(QPalette.ColorRole.Text))
        painter.translate(rect.left(), rect.top() + (rect.height() - layout.boundingRect().height()) / 2)
        layout.draw(painter, layout.position())
        painter.restore()

_DARK_QSS = """
QWidget { background-color: #17171c; color: #d8d8e0; font-size: 9pt; }
QLabel { color: #b9b9c8; }
QCheckBox { color: #d8d8e0; spacing: 5px; }
QCheckBox[hitOnly="true"] { color: #4dd0e1; font-weight: bold; }
QCheckBox[structureOnly="true"] { color: #ffd24d; font-weight: bold; }
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
/* ToolTip 深色金融质感样式，彻底根治 Windows 原生白底白字缺陷 */
QToolTip {
    background-color: #1e1f24;
    color: #eceff4;
    border: 1px solid #3d4048;
    border-radius: 6px;
    padding: 8px 12px;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 9pt;
}
"""

def get_effective_ats_trade_date(now_dt: Optional[datetime.datetime] = None) -> Tuple[str, bool, str]:
    """[DRY] 获取与 ATS 及 cct 权威日历对齐的交易日信息。
    返回: (自然日 cur_today, 是否法定交易日 is_trade_day, 最后一个有效交易日 last_trade_day)
    """
    if now_dt is None:
        now_dt = datetime.datetime.now()
    cur_today = now_dt.strftime("%Y-%m-%d")
    try:
        from JohnsonUtil import commonTips as cct
        is_trade_day = bool(cct.get_day_istrade_date(now_dt.date()))
    except Exception:
        try:
            from JohnsonUtil import commonTips as cct
            is_trade_day = bool(cct.get_trade_date_status())
        except Exception:
            is_trade_day = now_dt.weekday() < 5
    try:
        from JohnsonUtil import commonTips as cct
        last_trade_day = cct.get_last_trade_date(cur_today)
        if hasattr(last_trade_day, 'strftime'):
            last_trade_day = last_trade_day.strftime('%Y-%m-%d')
        last_trade_day = str(last_trade_day).strip()[:10]
    except Exception:
        last_trade_day = cur_today
    return cur_today, is_trade_day, last_trade_day


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
        "live_strategy = 实盘观测答案；回放档案独立保存，仅在对照页比较，不合并为实盘记录。",
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
    "终收%": _tip(
        "🏁 终收%（全天最终收盘涨跌幅）",
        "标的在当日 15:00 最终收盘时的绝对涨跌幅（相对昨日收盘价）。",
        "【自动后验对照】：对比「涨幅%」（入局触发时）与「终收%」（全天收盘），\n"
        "若终收% > 涨幅%，说明入局后持续走强甚至封板；\n"
        "若终收% < 涨幅%，说明入局后发生冲高回落。",
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
        self._body.setStyleSheet("background:transparent;border:none;color:#eceff4;font-family:'Microsoft YaHei','Segoe UI',sans-serif;font-size:9pt;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.addWidget(self._body)

    def set_html(self, html: str, max_width: int = 480) -> None:
        self._body.setMaximumWidth(max_width)
        self._body.setText(html)
        self._body.adjustSize()
        self.adjustSize()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor("#1e1f24"))
        p.setPen(QPen(QColor("#3d4048"), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)


def _format_tip_card_html(raw_text: str) -> str:
    """将任意纯文本或富文本提示转换对齐图2设计的深色卡片 HTML 规范。"""
    raw_text = str(raw_text or "").strip()
    if not raw_text:
        return ""
    if re.match(r"<(?:div|html|table|p|span)\b", raw_text, re.IGNORECASE):
        return '<div style="color:#eceff4;font-family:Microsoft YaHei,Segoe UI,sans-serif;font-size:12px;line-height:150%;">' + raw_text + '</div>'

    lines = raw_text.splitlines()
    html_parts = ['<div style="color:#eceff4;font-family:Microsoft YaHei,Segoe UI,sans-serif;font-size:12px;line-height:150%;">']
    for idx, line in enumerate(lines):
        line = line.strip()
        line = escape(line)
        if not line:
            html_parts.append('<div style="height:5px;"></div>')
            continue
        if idx == 0 and ("：" not in line or len(line) <= 28):
            html_parts.append(f'<div style="font-size:13px;font-weight:600;color:#4dd0e1;margin-bottom:4px;">{line}</div>')
        elif line.startswith("判断依据：") or line.startswith("依据："):
            html_parts.append(f'<div style="color:#c3e88d;margin-top:4px;">{line}</div>')
        elif line.startswith("说明：") or line.startswith("提示：") or line.startswith("注意："):
            html_parts.append(f'<div style="color:#ffd75e;margin-top:4px;">{line}</div>')
        elif line.startswith("否决：") or "否决" in line:
            html_parts.append(f'<div style="color:#ff8080;margin-top:4px;">{line}</div>')
        else:
            html_parts.append(f'<div>{line}</div>')
    html_parts.append('</div>')
    return "".join(html_parts)


class UnifiedToolTipFilter(QObject):
    """全局深色卡片 ToolTip 拦截器。
    彻底拦截 Windows 原生 QTipLabel 白底白字渲染 Bug，100% 呈现 _TipCard 统一设计样式。
    """

    def __init__(self, parent_window: QWidget):
        super().__init__(parent_window)
        self.window = parent_window
        self._tip_card = _TipCard()

    def _hide_card(self) -> None:
        try:
            if self._tip_card is not None and self._tip_card.isVisible():
                if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                    self._tip_card.hide()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            # 拖拽或鼠标按住期间绝不弹出/操作外部卡片，杜绝 Windows Input-Synchronous 循环崩溃 (0x8001010d)
            if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                return False

            if not isinstance(obj, QWidget):
                return False

            # 仅处理隶属于当前监视器窗口体系的组件
            if obj != self.window and not self.window.isAncestorOf(obj) and getattr(obj, "window", lambda: None)() != self.window:
                return False

            et = event.type()

            if et == QEvent.Type.ToolTip:
                tip_text = ""
                view = obj if isinstance(obj, QAbstractItemView) else (
                    obj.parentWidget() if isinstance(obj, QWidget) else None)
                if isinstance(view, QHeaderView):
                    return False  # 列头由 HeaderToolTip 使用同款卡片处理。
                if isinstance(view, QAbstractItemView):
                    pos = view.viewport().mapFrom(obj, event.pos())
                    index = view.indexAt(pos)
                    if index.isValid():
                        tip_text = str(index.data(Qt.ItemDataRole.ToolTipRole) or "")
                        cold_value = index.data(Qt.ItemDataRole.UserRole + 100)
                        if isinstance(cold_value, (tuple, dict)):
                            from ats.fusion.observation import observation_summary
                            from ats.fusion.shadow_io import hydrate
                            evidence = (hydrate({"_raw_ref": cold_value[0], "_raw_digest": cold_value[1]}).get("observation_evidence")
                                        if isinstance(cold_value, tuple) else cold_value)
                            tip_text += "\n" + observation_summary(evidence)
                        title = str(view.model().headerData(index.column(), Qt.Orientation.Horizontal) or "")
                        if tip_text and title and not re.match(r"\s*<", tip_text):
                            tip_text = title + "\n" + tip_text
                if not tip_text and isinstance(obj, QWidget):
                    tip_text = obj.toolTip()

                if tip_text:
                    html = _format_tip_card_html(tip_text)
                    gpos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    screen = QApplication.screenAt(gpos) or QApplication.primaryScreen()
                    geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
                    self._tip_card.set_html(html, max_width=max(80, min(480, geo.width() - 44)))
                    card_w = self._tip_card.width()
                    card_h = self._tip_card.height()

                    target_x = gpos.x() + 14
                    target_y = gpos.y() + 18
                    if target_x + card_w > geo.right() - 8:
                        target_x = max(geo.left() + 8, gpos.x() - card_w - 6)
                    if target_y + card_h > geo.bottom() - 8:
                        target_y = max(geo.top() + 8, gpos.y() - card_h - 6)
                    target_x = max(geo.left() + 8, min(target_x, geo.right() - card_w - 8))
                    target_y = max(geo.top() + 8, min(target_y, geo.bottom() - card_h - 8))

                    self._tip_card.move(target_x, target_y)
                    self._tip_card.show()
                    self._tip_card.raise_()
                    return True
            elif et in (
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.KeyPress,
                QEvent.Type.Wheel,
                QEvent.Type.WindowDeactivate,
                QEvent.Type.Hide,
            ):
                self._hide_card()
            elif et == QEvent.Type.MouseMove and self._tip_card.isVisible():
                self._hide_card()
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False


class FusionCalendarDialog(QDialog):
    """交易日历模式选择器：深色金融终端风，高亮有影子/回放数据的交易日。"""

    def __init__(self, available_days: List[str], current_day: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📅 交易日历选择")
        self.setFixedSize(360, 420)
        self.setStyleSheet("""
            QDialog { background-color: #17171c; color: #eceff4; }
            QLabel { color: #d8d8e0; font-size: 9pt; }
            QCalendarWidget QWidget { alternate-background-color: #17171c; }
            QCalendarWidget QAbstractItemView:enabled {
                background-color: #14141a;
                color: #eceff4;
                selection-background-color: #3d4a68;
                selection-color: #00ff88;
                font-size: 9pt;
            }
            QCalendarWidget QToolButton {
                background-color: #24242e;
                color: #ffd75e;
                font-weight: bold;
                border: 1px solid #3a3a48;
                border-radius: 3px;
                padding: 4px;
            }
            QCalendarWidget QSpinBox {
                background-color: #202028;
                color: #eceff4;
                border: 1px solid #3a3a48;
            }
            QPushButton {
                background-color: #24242e;
                color: #e6e6f0;
                border: 1px solid #3a3a48;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 9pt;
            }
            QPushButton:hover { background-color: #30303e; border-color: #5a5a72; }
        """)
        self.selected_day = current_day
        self.available_days_set = set(available_days or [])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        tip = QLabel("红色日期有有效分时缓存；无数据日期不可选择回放")
        tip.setStyleSheet("color:#ff6868; background:#202028; padding:5px 8px; border-radius:4px;")
        lay.addWidget(tip)

        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        unavailable_fmt = QTextCharFormat()
        unavailable_fmt.setForeground(QColor("#707078"))
        for weekday in Qt.DayOfWeek:
            self.calendar.setWeekdayTextFormat(weekday, unavailable_fmt)

        cur_qdate = QDate.fromString(current_day, "yyyy-MM-dd")
        if cur_qdate.isValid():
            self.calendar.setSelectedDate(cur_qdate)

        avail_fmt = QTextCharFormat()
        avail_fmt.setForeground(QColor("#ff6868"))
        f = avail_fmt.font()
        f.setBold(True)
        avail_fmt.setFont(f)

        for d_str in self.available_days_set:
            qd = QDate.fromString(d_str, "yyyy-MM-dd")
            if qd.isValid():
                self.calendar.setDateTextFormat(qd, avail_fmt)

        self.calendar.activated.connect(self._on_date_selected)
        self.calendar.selectionChanged.connect(self._guard_selection)
        lay.addWidget(self.calendar)

        btn_box = QHBoxLayout()
        btn_today = QPushButton("🎯 最后一个交易日")
        btn_today.clicked.connect(self._select_last_trade_day)
        btn_box.addWidget(btn_today)

        btn_ok = QPushButton("确认选择")
        btn_ok.setEnabled(bool(self.available_days_set))
        btn_ok.setStyleSheet("background-color: #2a3a5a; color: #00ff88; font-weight: bold;")
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        lay.addLayout(btn_box)
        if self.selected_day not in self.available_days_set:
            self.selected_day = max(self.available_days_set, default="")
            if self.selected_day:
                self.calendar.setSelectedDate(QDate.fromString(self.selected_day, "yyyy-MM-dd"))

    def _guard_selection(self):
        day = self.calendar.selectedDate().toString("yyyy-MM-dd")
        if day in self.available_days_set:
            self.selected_day = day
        elif self.selected_day:
            self.calendar.blockSignals(True)
            self.calendar.setSelectedDate(QDate.fromString(self.selected_day, "yyyy-MM-dd"))
            self.calendar.blockSignals(False)

    def _on_date_selected(self, qdate: QDate) -> None:
        if qdate.toString("yyyy-MM-dd") not in self.available_days_set:
            return
        self.selected_day = qdate.toString("yyyy-MM-dd")
        self.accept()

    def _select_last_trade_day(self) -> None:
        last_trade_day = max(self.available_days_set, default="")
        qd = QDate.fromString(last_trade_day, "yyyy-MM-dd")
        if qd.isValid():
            self.calendar.setSelectedDate(qd)
            self.selected_day = last_trade_day

    def _on_ok(self) -> None:
        qd = self.calendar.selectedDate()
        if qd.toString("yyyy-MM-dd") not in self.available_days_set:
            return
        self.selected_day = qd.toString("yyyy-MM-dd")
        self.accept()


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
        lbl.raise_()

    def _get_logical_index(self, obj, pos) -> int:
        header = self.table.horizontalHeader()
        try:
            p = pos
            if obj is header and hasattr(header, "viewport") and header.viewport():
                p = header.viewport().mapFrom(header, pos)
            return int(header.logicalIndexAt(p))
        except Exception:
            return -1

    def _html_at_index(self, idx: int) -> str:
        """取指定逻辑列索引的说明 HTML；取不到返回空串。"""
        if idx < 0:
            return ""
        item = self.table.horizontalHeaderItem(int(idx))
        if item is None:
            return ""
        text = item.text().strip()
        if text in HEADER_TOOLTIPS:
            return HEADER_TOOLTIPS[text]
        for k, v in HEADER_TOOLTIPS.items():
            if k == text or text.startswith(k) or k.startswith(text):
                return v
        return ""

    def _show_pending(self) -> None:
        # 若鼠标左键按下（正拖拽调整列宽）或窗口正在移动，绝不弹出卡片打断 Windows 输入同步循环
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self._pending_html = ""
            self._pending_pos = None
            return
        if self._pending_html and self._pending_pos is not None:
            self._show(self._pending_pos, self._pending_html)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            et = event.type()
            if et == QEvent.Type.MouseMove:
                if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                    self._delay.stop()
                    self._hide()
                    self._hover_idx = -1
                    return False
                idx = self._get_logical_index(obj, event.pos())
                if idx != self._hover_idx:
                    self._hover_idx = idx
                    self._delay.stop()
                    self._hide()
                    if idx >= 0:
                        html = self._html_at_index(idx)
                        if html:
                            self._pending_html = html
                            self._pending_pos = (
                                event.globalPosition().toPoint()
                                if hasattr(event, "globalPosition")
                                else event.globalPos()
                            )
                            self._delay.start()
                return False
            if et == QEvent.Type.ToolTip:
                idx = self._get_logical_index(obj, event.pos())
                if idx >= 0:
                    html = self._html_at_index(idx)
                    if html:
                        self._pending_html = html
                        self._pending_pos = (
                            event.globalPosition().toPoint()
                            if hasattr(event, "globalPosition")
                            else event.globalPos()
                        )
                        self._show_pending()
                        return True
                return False
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



class FusionSearchLineEdit(QLineEdit):
    """梯度监视器专用快速搜索输入框。

    特性：
    - 支持股票代码 (code) 与名称 (name) 模糊查询；
    - 支持右键弹出中文菜单一键粘贴 (📋 粘贴)，剪切，复制，清空；
    - 鼠标中键一键粘贴剪贴板代码；
    - 带有清除按钮 (ClearButton)；
    - 支持 Enter/Return 快速选中第一个匹配行并联动主图；
    - 支持 Esc 键清空搜索。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("🔍 搜索代码/名称...")
        self.setClearButtonEnabled(True)
        self.setToolTip("输入股票代码 (如 600688/688) 或名称 (如 上海石化) 模糊查询\n支持右键菜单一键黏贴，按 Enter 键快速定位联动")
        self.setStyleSheet(
            "QLineEdit { "
            "  background-color: #202028; color: #e6e6f0; "
            "  border: 1px solid #3a3a48; border-radius: 3px; "
            "  padding: 2px 6px; font-size: 8.5pt; "
            "  min-width: 140px; max-width: 180px; "
            "} "
            "QLineEdit:focus { border: 1px solid #7fb3d5; background-color: #252530; }"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            clip = QApplication.clipboard()
            text = clip.text().strip() if clip else ""
            if text:
                self.setText(text)
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """支持右键菜单一键粘贴及常用快捷操作。"""
        menu = QMenu(self)
        clip = QApplication.clipboard()
        clip_text = clip.text().strip() if clip else ""

        # 1. 粘贴 (支持直接黏贴剪贴板内容)
        act_paste = menu.addAction("📋 粘贴 (Paste)")
        act_paste.setShortcut("Ctrl+V")
        act_paste.setEnabled(bool(clip_text))

        def _do_paste() -> None:
            c_text = QApplication.clipboard().text().strip()
            if c_text:
                if self.hasSelectedText():
                    self.insert(c_text)
                elif not self.text():
                    self.setText(c_text)
                else:
                    self.insert(c_text)

        act_paste.triggered.connect(_do_paste)

        menu.addSeparator()

        # 2. 剪切
        act_cut = menu.addAction("✂️ 剪切 (Cut)")
        act_cut.setShortcut("Ctrl+X")
        act_cut.setEnabled(self.hasSelectedText() and not self.isReadOnly())
        act_cut.triggered.connect(self.cut)

        # 3. 复制
        act_copy = menu.addAction("📄 复制 (Copy)")
        act_copy.setShortcut("Ctrl+C")
        act_copy.setEnabled(self.hasSelectedText())
        act_copy.triggered.connect(self.copy)

        # 4. 全选
        act_select_all = menu.addAction("全选 (Select All)")
        act_select_all.setShortcut("Ctrl+A")
        act_select_all.setEnabled(bool(self.text()))
        act_select_all.triggered.connect(self.selectAll)

        menu.addSeparator()

        # 5. 清空
        act_clear = menu.addAction("❌ 清空 (Clear)")
        act_clear.setEnabled(bool(self.text()))
        act_clear.triggered.connect(self.clear)

        menu.exec(event.globalPos())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.text():
                self.clear()
                event.accept()
                return
        super().keyPressEvent(event)


def get_ats_custom_extra_cols() -> List[str]:
    """获取用户在 global.ini 中配置的 ats_col 自定义扩展列（排除已有的基础固定字段）"""
    try:
        from JohnsonUtil import commonTips as cct
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']

    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'trade', 'pct', 'percent',
        'tier', 'rar', 'size_pct', 'entry', 'stop', 'mfe', 'mae', 'time',
        'update_time', 'source', 'hit', 'coverage', 'temp', 'position',
        'support', 'intent', 'regime', 'enter_time', 'enter_price',
        'enter_pct', 'first_time', 'first_pct', 'since_first_pct',
        'persist', 'evidence_n', 'chain', 'close_ret', 'day_close', 'day_close_pct'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_ats_col_display_name(col_name: str) -> str:
    """根据 vis_column_map 将自定义列名转换为界面中文/展示名"""
    try:
        from JohnsonUtil import commonTips as cct
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
    return col_map.get(col_name, col_map.get(col_name.lower(), col_name.upper()))


# 各表基础固定表头定义
_LIVE_BASE_HEADERS = [
    "级别", "代码", "名称", "现价", "涨幅%", "RAR", "位", "接", "意", "环", "仓位%", "进场", "止损", "先手min", "来源",
    "更新时间", "命中", "覆盖%",
]

_REPLAY_BASE_HEADERS = [
    "时间", "代码", "名称", "现价", "涨幅%", "终收%", "级别", "RAR", "仓位%", "MFE%", "MAE%", "收盘%", "温度℃",
    "历史换手%", "历史量比", "特征日期",
]

_TRADES_BASE_HEADERS = [
    "代码", "名称", "买入", "买入价", "时段", "卖出", "卖出价", "盈亏%", "当日最低%", "被锁止损", "原因",
]

_TRACK_BASE_HEADERS = [
    "代码", "名称", "入局", "入局价", "当时涨幅%", "首异动", "首异动涨幅%", "首→入%",
    "持续分", "证据数", "证据链", "之后MFE%", "MAE%", "收盘%",
]

# 各表默认列宽（仅在从未保存过布局时使用；用户调整后由 ATS 表头持久化接管）
_DEFAULT_COL_WIDTHS: Dict[str, List[int]] = {
    "tbl_live": [56, 74, 104, 76, 78, 64, 52, 52, 52, 52, 64, 108, 78, 70, 104, 82, 52, 62],
    "tbl_replay": [70, 74, 104, 76, 78, 78, 56, 64, 64, 64, 64, 64, 62, 82, 76, 100],
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
    selected_root = str(load_config_node("fusion_trade_center_root", "") or "").strip()
    if selected_root:
        return [os.path.join(selected_root, "logs", "fusion_shadow")]
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
    from ats.fusion.shadow_io import day_paths, log_directories
    paths = []
    for directory in _shadow_dir_candidates():
        paths.extend(day_paths(log_directories(directory), day or today_str()))
    # 兼容旧版 UI 快照目录，生产新分片使用按应用根隔离的目录。
    if not str(load_config_node("fusion_trade_center_root", "") or "").strip():
        ram = _detect_ramdisk_dir()
        if ram:
            paths.extend(day_paths([ram], day or today_str()))
    return paths


def _resolve_day_file(day: str) -> Optional[str]:
    """当日的可读文件：多个候选里取修改时间最新的那个（Ramdisk 更新时用 Ramdisk）。"""
    best: Optional[str] = None
    best_mtime = -1.0
    for p in _day_file_candidates(day):
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                if p.endswith(".gz") and best and not best.endswith(".gz"):
                    continue
                if best and best.endswith(".gz") and not p.endswith(".gz"):
                    best, best_mtime = p, -1.0
                m = os.path.getmtime(p)
                if m > best_mtime:
                    best, best_mtime = p, m
        except Exception:
            continue
    return best


def _resolved_day_paths(path, day):
    """合并所选应用根的全部 PID 分片，避免把不同部署目录混成一条流。"""
    from ats.fusion.shadow_io import day_paths, log_directories
    directory = os.path.normcase(os.path.dirname(os.path.abspath(path)))
    for root in _shadow_dir_candidates():
        directories = log_directories(root)
        if directory in {os.path.normcase(os.path.abspath(p)) for p in directories}:
            return day_paths(directories, day)
    return day_paths([os.path.dirname(path)], day)


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
    from ats.fusion.shadow_io import log_directories, LOG_NAME
    directories = [p for directory in _shadow_dir_candidates() for p in log_directories(directory)]
    if not str(load_config_node("fusion_trade_center_root", "") or "").strip() and _detect_ramdisk_dir():
        directories.append(_detect_ramdisk_dir())
    for d in directories:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for nm in names:
            if not LOG_NAME.fullmatch(nm):
                continue
            p = os.path.join(d, nm)
            try:
                if os.path.getsize(p) <= 0:
                    continue
                m = os.path.getmtime(p)
            except Exception:
                continue
            if m > newest_mtime:
                newest_path, newest_day, newest_mtime = p, nm[:10], m
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


def _in_trading_session(ts: float, allow_premarket: bool = False) -> bool:
    """记录是否落在交易时段。默认仅认连续竞价时段（09:30~11:30, 13:00~15:00）。

    09:15~09:29 为集合竞价阶段，未发生正式连续竞价撮合，报价为虚拟快照；
    赛马跟踪入局必须从 09:30 正式开盘连续竞价开始，绝不能把集合竞价试盘假价格当作入局点。
    """
    try:
        v = float(ts)
    except Exception:
        return False
    if v <= 0:
        return False
    try:
        hm = datetime.datetime.fromtimestamp(v).strftime("%H:%M:%S")
        if allow_premarket:
            return "09:15:00" <= hm <= "15:05:00"
        return ("09:30:00" <= hm <= "11:30:05") or ("13:00:00" <= hm <= "15:00:05")
    except Exception:
        return False


def _row_is_hit(rec: Dict[str, Any]) -> bool:
    """梯度命中以融合结果为准；仅旧格式缺少融合结果时兼容旧策略。"""
    try:
        tier = int((rec.get("fusion") or {}).get("tier") or 0)
    except Exception:
        tier = 0
    if isinstance(rec.get("fusion"), dict) and "tier" in rec["fusion"]:
        return tier >= 2
    if "hit" in rec:
        return bool(rec["hit"])
    action = str((rec.get("legacy") or {}).get("action") or "")
    return action in ("买入", "加仓", "BUY", "ADD")


def _row_is_structure_opportunity(rec: Dict[str, Any]) -> bool:
    """判断单行是否属于多周期 VWAP 【结构机会】黄金标的。

    操盘手核心实战心法：
    1. 命中 10 日 VWAP 结构预判 (is_structure_prejudged == 1.0)；
    2. 或昨日洗盘充分重心不破底 (wash_quality == 1.0)；
    3. 或昨日大阳突破带头总龙头 (prev_strong_vwap == 1.0 或 is_prime_leader == 1.0)；
    4. 或分时命中核心形态：结构预判验证、十日洗盘悬空突破、箱体悬空突破；
    5. 或证据链中明确包含结构预判、总龙头等关键词。
    """
    if not isinstance(rec, dict):
        return False
    fusion = rec.get("fusion") or {}
    extra = rec.get("extra") or fusion.get("extra") or {}
    struct = rec.get("struct") or {}
    patterns = list(rec.get("patterns") or fusion.get("patterns") or fusion.get("evidence") or [])
    p_str = " ".join(str(p) for p in patterns)

    # 0. 结构时间轴优先：已失守/已剔除的票不再算"结构机会"（价格走坏了就要让位）
    _status = str(struct.get("status") or rec.get("struct_status") or "")
    if _status in ("BROKEN", "EVICTED"):
        return False
    if _status == "CONFIRMED":
        return True

    # 1. 优先从紧凑结构字典 struct、顶层字段或 extra 提取结构预判标识
    if float(struct.get("is_structure_prejudged") or rec.get("is_structure_prejudged") or extra.get("is_structure_prejudged") or 0.0) == 1.0:
        return True
    if float(struct.get("wash_quality") or rec.get("wash_quality") or extra.get("wash_quality") or 0.0) == 1.0:
        return True
    if float(struct.get("prev_strong_vwap") or rec.get("prev_strong_vwap") or extra.get("prev_strong_vwap") or 0.0) == 1.0:
        return True
    if float(struct.get("is_prime_leader") or rec.get("is_prime_leader") or extra.get("is_prime_leader") or 0.0) == 1.0:
        return True

    # 2. 命中核心结构形态
    for pat in ("结构预判验证", "十日洗盘悬空突破", "箱体悬空突破", "多周期VWAP金叉"):
        if pat in p_str:
            return True

    # 3. 证据链关键词兜底 (补齐 结构验证、🎯结构验证、🚀板块总龙头)
    chain = str((fusion.get("tracker") or {}).get("chain") or " ".join(str(e) for e in (fusion.get("evidence") or [])))
    if any(k in chain for k in ("结构预判", "结构验证", "结构强势", "十日洗盘", "总龙头", "3V10V粘合")):
        return True
    return False


_SHADOW_CURSORS: Dict[Tuple[str, Tuple[str, ...]], Any] = {}
_SHADOW_ROWS_SNAPSHOT: Dict[Tuple[str, Tuple[str, ...]], Tuple[int, List[Dict[str, Any]]]] = {}
_SHADOW_RETENTION_DEFAULT = 20000


def _shadow_retention_records() -> int:
    """内存驻留条数上限（可配）。

    实测单条记录解析后约 38KB，2 万条约 750MB；赛马视图需要当日过程序列，
    因此默认不压缩。内存吃紧时把 `fusion_shadow_retention_records` 调到
    8000 可省约 440MB，代价是当日更早的序列点被裁掉。
    """
    try:
        value = int(load_config_node("fusion_shadow_retention_records", _SHADOW_RETENTION_DEFAULT) or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value >= 500 else _SHADOW_RETENTION_DEFAULT


def _shadow_dataset(paths: Sequence[str], src_day: str, max_records: int = 20000):
    """当日分片的唯一增量游标：看板与赛马共用一次解析。

    旧实现 rows/series 各建一份"按文件指纹"的缓存，交易时段文件每几秒追加一次，
    指纹必然变化 → 缓存必然失效 → 每次刷新把 200MB+ 分片整份重解析两遍（实测
    12.6 秒/次），并把最多 8~12 份全量副本留在内存里。现在改为按字节偏移增量
    读取：稳态零解析，新增一行只解析一行。
    """
    from ats.fusion.shadow_io import DayLogCursor

    key = (src_day, tuple(str(p) for p in paths))
    cursor = _SHADOW_CURSORS.get(key)
    if cursor is None:
        for stale in [k for k in _SHADOW_CURSORS if k[0] == src_day]:
            _SHADOW_CURSORS.pop(stale, None)
            _SHADOW_ROWS_SNAPSHOT.pop(stale, None)
        # 浏览历史日期时限制驻留天数，避免每切一天就累积一份 2 万条记录。
        while len(_SHADOW_CURSORS) >= 2:
            stale = next(iter(_SHADOW_CURSORS))
            _SHADOW_CURSORS.pop(stale, None)
            _SHADOW_ROWS_SNAPSHOT.pop(stale, None)
        cursor = DayLogCursor(max_records=max_records, compact=True)
        _SHADOW_CURSORS[key] = cursor
    else:
        # dict 保持插入顺序；命中日期移到末尾，淘汰最久未查看的日期。
        _SHADOW_CURSORS.pop(key)
        _SHADOW_CURSORS[key] = cursor
    cursor.refresh(paths)
    if cursor.errors:
        logger.warning("[FusionLadder] 影子读取异常: %s", cursor.errors[:5])
    return key, cursor


def _shadow_rows(paths: Sequence[str], src_day: str, max_records: int = 20000) -> List[Dict[str, Any]]:
    """游标内记录的只读快照；同一版本号内不重复复制列表。"""
    key, cursor = _shadow_dataset(paths, src_day, max_records)
    cached = _SHADOW_ROWS_SNAPSHOT.get(key)
    if cached is not None and cached[0] == cursor.version:
        return cached[1]
    rows = cursor.rows()
    _SHADOW_ROWS_SNAPSHOT[key] = (cursor.version, rows)
    return rows


def load_live_series(day: str = "", max_lines: int = 20000, allow_fallback: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """按 code 返回当日全部影子记录（时间升序），供赛马跟踪等"过程类"视图使用。

    与 `load_live_rows` 的区别：那个只保留每只票最新一条（看板用），
    这个保留整条时间序列，才能算出入局时间、入局后 MFE/MAE、持续分。
    两者共用同一个增量游标，不再各自全量重读。
    """
    path = _resolve_shadow_file(day)[0] if allow_fallback else _resolve_day_file(day)
    if not path or not os.path.exists(path):
        return {}
    path_day = os.path.basename(path)[:10]
    try:
        from ats.fusion.shadow_io import record_ts
        paths = _resolved_day_paths(path, path_day)
        records = _shadow_rows(paths, path_day, _shadow_retention_records())
        tail = sorted((r for r in records if record_ts(r) is not None), key=record_ts)[-max_lines:]
    except (OSError, ValueError, TypeError):
        logger.exception("[FusionLadder] 影子分片读取失败")
        return {}

    series: Dict[str, List[Dict[str, Any]]] = {}
    for rec in tail:
        from ats.fusion.source_identity import record_matches_day, is_replay_record
        if is_replay_record(rec) or not record_matches_day(rec, path_day):
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
    from ats.fusion.source_identity import is_replay_record
    if any(not isinstance(record, dict) or is_replay_record(record) for record in records):
        logger.warning("拒绝将回放或无效记录写入生产影子日志")
        return 0
    from ats.fusion.source_identity import record_matches_day
    day = day or today_str()
    if any(not record_matches_day(record, day) for record in records):
        logger.warning("拒绝跨日期或无有效时间戳的影子记录：%s", day)
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
    内置文件指纹 (path, size, mtime) 缓存，文件未变化时 0 磁盘 IO 直接返回。
    """
    if allow_fallback:
        target_path, src_day = _resolve_shadow_file(day)
    else:
        target_path, src_day = _resolve_day_file(day), (day or today_str())

    if not target_path or not os.path.exists(target_path):
        return []
    try:
        from ats.fusion.shadow_io import record_ts
        paths = _resolved_day_paths(target_path, src_day)
        records = _shadow_rows(paths, src_day, _shadow_retention_records())
        tail = sorted((r for r in records if record_ts(r) is not None), key=record_ts)[-max_lines:]
    except (OSError, ValueError, TypeError):
        logger.exception("[FusionLadder] 影子分片读取失败")
        return []

    latest: Dict[str, Dict[str, Any]] = {}
    for rec in tail:
        from ats.fusion.source_identity import record_matches_day, is_replay_record
        if is_replay_record(rec) or not record_matches_day(rec, src_day):
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

    # 记录由游标长期持有，这里只做浅拷贝再打来源标记，避免把 _source_* 写回共享记录。
    rows = [dict(r, _source_day=src_day, _source_file=target_path) for r in latest.values()]
    rows.sort(key=lambda r: (int((r.get("fusion") or {}).get("tier") or 0),
                             float((r.get("fusion") or {}).get("rar") or 0)), reverse=True)
    return rows


class _ReplayCancelled(Exception):
    """用户/退出流程取消回放时，用于从进度回调里快速退出。"""


class ReplayCalendarWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self):
        try:
            replay = DayReplay(config=ReplayConfig(persist_context=False, market_path=os.devnull,
                                                   use_production_history=False))
            days = replay.days()
            if not self.isInterruptionRequested():
                self.done.emit(days)
        except Exception as exc:
            self.failed.emit(str(exc))


class ReplayWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, day: str, focus: List[str], top_n: int = 300, step: int = 1,
                 cuts_mode: str = "percentile", parent=None, iterate=False, history_root=""):
        super().__init__(parent)
        self.day = day
        self.focus = focus
        self.top_n = top_n
        self.step = step
        self.cuts_mode = cuts_mode
        self.iterate = iterate
        self.history_root = history_root

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
                persist_context=False, market_path=os.devnull, max_records=100000,
                history_root=self.history_root, use_production_history=False,
            ))
            if not rp.cache:
                self.failed.emit("找不到分钟线缓存（cct ramdisk: minute_kline_cache.pkl）")
                return
            day = self.day or (rp.days()[-1] if rp.days() else today_str())
            days = [d for d in rp.days() if d <= day]
            if day not in days:
                self.failed.emit("{} 不在分钟缓存中".format(day))
                return
            from ats.fusion.iteration import run_iterations
            selected = days[-5:] if self.iterate else [day]
            def on_iteration_progress(index, count, cur, total):
                self._on_progress(index * 100 + int(cur * 100 / max(1, total)), count * 100)
            output = run_iterations(days=selected, focus=self.focus, replay=rp, history_root=self.history_root or None, progress=on_iteration_progress)
            if self.iterate:
                self.done.emit(output)
            else:
                output["last_result"].meta["iteration_dir"] = output["run_dir"]
                from ats.fusion.iteration import render_iteration
                output["last_result"].meta["iteration_report"] = render_iteration(output)
                self.done.emit(output["last_result"])
        except _ReplayCancelled:
            logger.info("[FusionLadder] 回放已按请求中断")
        except Exception as exc:  # 线程内异常必须自己吞，否则整个窗口崩
            self.failed.emit("{}: {}".format(type(exc).__name__, exc))


class CrossDayWorker(QThread):
    done = pyqtSignal(object, str)
    failed = pyqtSignal(str)

    def __init__(self, days, day, parent=None, root="", replay_run=""):
        super().__init__(parent)
        self.days, self.day = days, day
        self.root = root
        self.replay_run = replay_run

    def run(self):
        from ats.fusion.cross_day import build_cross_day
        from ats.fusion.paper_follow import read_paper_account, read_shadow_days, build_paper_follow
        from ats.fusion.replay_follow import read_replay_follow
        from ats.fusion.replay import load_minute_cache
        from sys_utils import get_app_root
        try:
            series, errors = read_shadow_days(self.root, self.day)
            if self.isInterruptionRequested():
                return
            signals = build_cross_day(series, self.day)
            paper = build_paper_follow(read_paper_account(self.root), signals, self.day)
            if self.isInterruptionRequested():
                return
            minute_cache = load_minute_cache()
            if self.isInterruptionRequested():
                return
            replay = read_replay_follow([os.path.join(self.root, "logs", "fusion_iterations"),
                                         os.path.join(get_app_root(), "logs", "fusion_iterations"),
                                         os.path.join(get_app_root(), "artifacts", "fusion_research", "iterations")],
                                        self.day, self.replay_run, price_days=self.days,
                                        minute_cache=minute_cache, should_cancel=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                return
            self.done.emit({"signals": signals, "paper": paper, "root": self.root,
                            "shadow_errors": errors, "replay": replay,
                            "requested_replay": self.replay_run}, self.day)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.failed.emit("跨日/PAPER读取失败：{}".format(exc))


class FusionLadderDialog(QWidget, WindowMixin):
    _LIVE_BASE_HEADERS = _LIVE_BASE_HEADERS
    _REPLAY_BASE_HEADERS = _REPLAY_BASE_HEADERS
    _TRADES_BASE_HEADERS = _TRADES_BASE_HEADERS
    _TRACK_BASE_HEADERS = _TRACK_BASE_HEADERS
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
        self._state_save_timer = QTimer(self)
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.setInterval(10000)
        self._state_save_timer.timeout.connect(self._persist_window_states)
        self._pending_window_states = None

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
        self._follow_worker = None
        self._result = None
        self._replay_follow_dir = ""
        self._replay_days: List[str] = []

        # 盘后自动沉淀与每日上下文定时检查
        self._last_auto_settle_day = str(load_config_node("fusion_last_auto_settle_day", ""))
        self._closing_settle_timer = QTimer(self)
        self._closing_settle_timer.timeout.connect(self._check_and_auto_settle_closing)
        self._closing_settle_timer.start(15000)

        # 实时梯度自动刷新：30s 巡检一次。看板展示的是"每票最新一条"，
        # 该行集通常几分钟才变化一次，2s 一次纯属空转（每次要重建 3 万多个单元格）。
        self._live_sig = None
        self._live_render_fp = None
        self._tab_signatures: Dict[int, Any] = {}
        self._last_init_scan_t = 0.0
        self._init_scan_started = False
        self._replay_backfill_started = False
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._auto_refresh_live)
        self._live_timer.start(30000)

        # 启动即初始化：每次打开窗口都保证跑一次（非交易时段自动豁免），绝不白板
        QTimer.singleShot(1200, self._startup_init_scan)

        # 注入全局深色卡片 ToolTip 拦截器与暗黑调色板，彻底消除 Windows 原生白底白字缺陷
        from ats.ui.styles import apply_dark_tooltip_palette
        apply_dark_tooltip_palette(self)
        self._tooltip_filter = UnifiedToolTipFilter(self)
        try:
            self.installEventFilter(self._tooltip_filter)
        except Exception:
            pass

        self._init_ui()
        self._load_saved_geometry()
        self._init_days()
        self.refresh_live()
        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._refresh_cross_day_if_visible)
        self._follow_timer.start(30000)

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ---- 顶部控制条 ----
        bar = QHBoxLayout()
        bar.setSpacing(4)
        bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_status = QLabel("状态：就绪")
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")
        self.lbl_status.setWordWrap(False)
        self.lbl_status.setFixedSize(
            self.lbl_status.fontMetrics().horizontalAdvance("状态：2026-10-30 重点10/10 ⚠") + 16,
            self.lbl_status.fontMetrics().lineSpacing() + 8,
        )
        bar.addWidget(self.lbl_status)

        # 极窄模式切换开关
        self.chk_narrow = QCheckBox("窄屏")
        self.chk_narrow.setChecked(self.is_narrow_mode)
        self.chk_narrow.setToolTip("开启极窄列模式：仅保留核心关键列，适合靠边停靠或小屏查看")
        self.chk_narrow.toggled.connect(self._on_narrow_mode_toggled)
        bar.addWidget(self.chk_narrow)

        # 📊 自定义列扩展开关
        self.show_custom_cols = self._load_show_custom_cols()
        self.chk_custom_cols = QCheckBox("扩展列")
        self.chk_custom_cols.setChecked(self.show_custom_cols)
        self.chk_custom_cols.setToolTip("开启/关闭 ATS 策略 DataFrame 动态自定义列扩展 (如 DFF, Rank, ch_bc2 等)")
        self.chk_custom_cols.toggled.connect(self._on_custom_cols_toggled)
        bar.addWidget(self.chk_custom_cols)

        # 置顶复选框 (置顶与磁吸互斥)
        self.chk_on_top = QCheckBox("置顶")
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.setToolTip("开启置顶 (快捷键 T)；置顶状态下窗口始终浮于最前，停用边缘折叠隐藏")
        self.chk_on_top.toggled.connect(self._on_stays_on_top_toggled)
        bar.addWidget(self.chk_on_top)

        # 只看命中：梯度层是"打分命中"，不是把异动列表再显示一遍。
        # 文字里不带 ✅（勾号会和复选框状态混淆），改用颜色表达选中态。
        self.chk_hit_only = QCheckBox("命中")
        self.chk_hit_only.setToolTip(
            "显示融合梯度 L2 及以上，以及逆势收复观察信号；观察信号不代表可执行梯度。\n"
            "关掉可看全池梯度分布，用于观察 L0/L1 的边缘标的。"
        )
        try:
            self.chk_hit_only.setChecked(bool(load_config_node("fusion_ladder_hit_only", False)))
        except Exception:
            pass
        self.chk_hit_only.toggled.connect(self._on_hit_only_toggled)
        self._style_hit_only(self.chk_hit_only.isChecked())
        bar.addWidget(self.chk_hit_only)

        self.chk_focus_only = QCheckBox("重点")
        self.chk_focus_only.setChecked(True)
        self.chk_focus_only.setToolTip("实时页最多标记10只当前重点；回放页标记当日14:45前首次进入重点的记录，全天累计可能超过10只。重点排序置前；观察不代表买入。")
        self.chk_focus_only.toggled.connect(self._on_focus_toggled)
        bar.addWidget(self.chk_focus_only)

        # 🎯 只看结构机会：操盘手核心过滤，过滤95%无结构脉冲杂音，聚焦真正具备主升浪潜力的黄金机会
        self.chk_structure_only = QCheckBox("结构")
        self.chk_structure_only.setToolTip(
            "【操盘手核心铁律】只看结构机会：\n"
            "仅保留符合多周期 VWAP 结构预判（尾盘收盘站稳 10V/3V、洗盘充分重心不破底、板块总龙头或悬空突破验证）的黄金标的。\n"
            "坚决过滤全池 95% 无结构支撑的脉冲杂音、水下抽搐、走弱反抽与不过前高诱多，聚焦主升浪持有底气！"
        )
        try:
            self.chk_structure_only.setChecked(bool(load_config_node("fusion_ladder_structure_only", False)))
        except Exception:
            pass
        self.chk_structure_only.toggled.connect(self._on_structure_only_toggled)
        self._style_structure_only(self.chk_structure_only.isChecked())
        bar.addWidget(self.chk_structure_only)
        for control in (self.chk_narrow, self.chk_custom_cols, self.chk_on_top,
                        self.chk_hit_only, self.chk_focus_only, self.chk_structure_only):
            control.setStyleSheet(
                "QCheckBox { spacing: 3px; margin: 0px; padding: 0px; }"
                "QCheckBox::indicator { width: 14px; height: 14px; }"
            )

        bar.addWidget(QLabel("实盘日"))
        self.cmb_day = QComboBox()
        self.cmb_day.setMinimumWidth(105)
        self.cmb_day.currentTextChanged.connect(self._on_day_changed)
        self.cmb_day.setToolTip("实盘观测与对照答案日期；不受回放分钟缓存保留期限限制。")
        bar.addWidget(self.cmb_day)
        bar.addWidget(QLabel("回放日"))
        self.cmb_replay_day = QComboBox()
        self.cmb_replay_day.setMinimumWidth(105)
        self.cmb_replay_day.setEnabled(False)
        self.cmb_replay_day.setToolTip("独立回放日期；与右侧日历一致，只列有效分时缓存日期。")
        bar.addWidget(self.cmb_replay_day)

        self.btn_calendar = QPushButton("📅")
        self.btn_calendar.setToolTip("后台核验分时缓存：红色日期可回放，无有效缓存的日期禁止选择；影子文件存在不代表可回放。")
        self.btn_calendar.setFixedWidth(28)
        self.btn_calendar.clicked.connect(self._open_calendar_mode)
        bar.addWidget(self.btn_calendar)

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

        self.btn_run = QPushButton("▶ 跑回放")
        self.btn_run.setToolTip("按所选日期回放并保存独立档案，不覆盖生产梯度或会话快照")
        self.btn_run.clicked.connect(self.run_replay)
        bar.addWidget(self.btn_run)

        self.btn_iteration = QPushButton("📊 逐日迭代")
        self.btn_iteration.setToolTip("按时间顺序回放所选日期及之前最多五个缓存交易日，生成跨日比较和独立档案")
        self.btn_iteration.clicked.connect(self.run_iteration)
        bar.addWidget(self.btn_iteration)

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
        self.status_details = QLineEdit(self)
        self.status_details.setReadOnly(True)
        self.status_details.setFrame(False)
        self.status_details.setMinimumWidth(0)
        self.status_details.setFixedHeight(self.status_details.fontMetrics().lineSpacing() + 8)
        self.status_details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.status_details.setPlaceholderText("统计、数据来源与告警信息")
        self.status_details.setStyleSheet("color:#b8bec9; background:transparent; font-size:9pt;")
        root.addWidget(self.status_details)

        # 获取用户配置的动态自定义扩展列 (ats_col)
        self.extra_cols = get_ats_custom_extra_cols()
        extra_headers = [get_ats_col_display_name(c) for c in self.extra_cols]

        # Tab 0: 实时梯度 [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源, 更新时间, 命中, 覆盖%] + 自定义列
        self.tbl_live = self._create_interactive_table(self._LIVE_BASE_HEADERS + extra_headers, "tbl_live")
        self.tbl_live.sortItems(1, Qt.SortOrder.AscendingOrder)
        self.tabs.addTab(self.tbl_live, "实时梯度（影子流）")

        # Tab 1: 按日回放 [时间, 代码, 名称, 现价, 涨幅%, 终收%, 级别, RAR, 仓位%, MFE%, MAE%, 收盘%, 温度℃] + 自定义列
        self.tbl_replay = self._create_interactive_table(self._REPLAY_BASE_HEADERS + extra_headers, "tbl_replay")
        self.tabs.addTab(self.tbl_replay, "按日回放")

        # Tab 2: T+1 订单与成交
        self.tbl_trades = self._create_interactive_table(self._TRADES_BASE_HEADERS, "tbl_trades")
        self.tabs.addTab(self.tbl_trades, "T+1 订单与成交")

        # Tab 3: 赛马跟踪 [代码, 名称, 入局, 入局价, 当时涨幅%, 首异动, 首异动涨幅%, 首→入%, 持续分, 证据数, 证据链, 之后MFE%, MAE%, 收盘%] + 自定义列
        self.tbl_track = self._create_interactive_table(self._TRACK_BASE_HEADERS + extra_headers, "tbl_track")
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

        cross_page = QWidget()
        cross_layout = QVBoxLayout(cross_page)
        cross_layout.setContentsMargins(4, 4, 4, 4)
        self.lbl_cross_status = QLabel("跨日跟踪：等待加载生产与回放来源。")
        self.lbl_cross_status.setWordWrap(True)
        cross_layout.addWidget(self.lbl_cross_status)
        self.tbl_cross_day = self._create_interactive_table(
            ["代码", "信号来源", "名称", "首次信号日", "首次时间", "参考价", "最新记录日", "最新时间", "最新记录价", "相对参考%", "记录天数", "数据状态", "采样MFE%", "采样MAE%", "信号状态", "逐日轨迹", "PAPER交易状态", "双流对照"],
            "tbl_cross_day")
        cross_layout.addWidget(self.tbl_cross_day)
        for column in (15, 17):
            self.tbl_cross_day.setItemDelegateForColumn(column, SignedPercentDelegate(self.tbl_cross_day))
        for column in (9, 12, 13):
            self.tbl_cross_day.setItemDelegateForColumn(column, ColorPreservingItemDelegate(self.tbl_cross_day))
        self.tabs.addTab(cross_page, "跨日信号跟踪")
        self.tbl_cross_day.setToolTip("分别展示生产影子和兼容回放档案的跨日轨迹；回放不关联PAPER成交，缺失日期不填零。")

        from sys_utils import get_app_root
        paper_page = QWidget()
        paper_layout = QVBoxLayout(paper_page)
        source_bar = QHBoxLayout()
        source_bar.addWidget(QLabel("交易中心目录"))
        self.ed_trade_root = QLineEdit(str(load_config_node("fusion_trade_center_root", "") or get_app_root()))
        source_bar.addWidget(self.ed_trade_root, 1)
        self.btn_paper_refresh = QPushButton("刷新 PAPER 全程")
        self.btn_paper_refresh.clicked.connect(self._refresh_paper_source)
        self.ed_trade_root.returnPressed.connect(self._refresh_paper_source)
        source_bar.addWidget(self.btn_paper_refresh)
        paper_layout.addLayout(source_bar)
        self.lbl_paper_status = QLabel("PAPER 成交按账户原账本读取；不下单、不回写账户。")
        self.lbl_paper_status.setWordWrap(True)
        paper_layout.addWidget(self.lbl_paper_status)
        self.tbl_paper_follow = self._create_interactive_table(
            ["代码", "名称", "观察日", "观察参考价", "买入时间", "买入均价", "买入股数", "卖出股数",
             "持仓股数", "可卖股数", "末成交/快照价", "浮盈%", "已实现盈亏", "已实现%", "平仓时间",
             "生命周期", "关联依据", "逐笔链路", "价格/数量口径"], "tbl_paper_follow")
        paper_layout.addWidget(self.tbl_paper_follow)
        for column in (11, 12, 13):
            self.tbl_paper_follow.setItemDelegateForColumn(column, ColorPreservingItemDelegate(self.tbl_paper_follow))
        self.tabs.addTab(paper_page, "交易中心 PAPER 全程")

        # ---- 选项卡右上角搜索栏 (代码/名称模糊查询 + 右键黏贴) ----
        search_box = QWidget(self.tabs)
        search_box.setStyleSheet("background: transparent;")
        sb_layout = QHBoxLayout(search_box)
        sb_layout.setContentsMargins(0, 0, 6, 2)
        sb_layout.setSpacing(6)

        self.lbl_search_count = QLabel("")
        self.lbl_search_count.setStyleSheet(
            "font-size: 8.5pt; color: #8fd18f; font-weight: bold; background: transparent;"
        )
        self.lbl_search_count.hide()
        sb_layout.addWidget(self.lbl_search_count)

        self.ed_search = FusionSearchLineEdit(search_box)
        self.ed_search.textChanged.connect(self._on_search_text_changed)
        self.ed_search.returnPressed.connect(self._on_search_return_pressed)
        sb_layout.addWidget(self.ed_search)

        self.tabs.setCornerWidget(search_box, Qt.Corner.TopRightCorner)

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
            def_widths = list(_DEFAULT_COL_WIDTHS.get(name, []))
            if len(def_widths) < len(headers):
                def_widths.extend([68] * (len(headers) - len(def_widths)))
            setup_header_persistence(
                tbl,
                config_key="fusion_ladder_{}_state".format(name),
                default_widths=def_widths,
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

            # 调整结束后将表头状态排入后台写入队列。
            _flush_timer = QTimer(tbl)
            _flush_timer.setSingleShot(True)
            _flush_timer.setInterval(800)

            def _persist_layout_now(_tbl=tbl):
                try:
                    _tbl.save_header_state(sync=False)
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


    # ------------------------------------------------------------------
    # 搜索与过滤逻辑（代码/名称模糊查询 + 右键黏贴 + 回车联动）
    # ------------------------------------------------------------------
    def _get_active_table(self) -> Optional[QTableWidget]:
        """获取当前激活选项卡中的表格组件。"""
        idx = self.tabs.currentIndex()
        if idx == 0:
            return self.tbl_live
        elif idx == 1:
            return self.tbl_replay
        elif idx == 2:
            return self.tbl_trades
        elif idx == 3:
            return self.tbl_track
        elif idx == 6:
            return self.tbl_cross_day
        elif idx == 7:
            return self.tbl_paper_follow
        return None

    def _apply_search_filter(self, target_tbl: Optional[QTableWidget] = None) -> None:
        """根据搜索框内容对目标表格执行行级模糊过滤。"""
        tbl = target_tbl if target_tbl is not None else self._get_active_table()
        if tbl is None:
            if hasattr(self, "lbl_search_count"):
                self.lbl_search_count.hide()
            return

        raw_kw = self.ed_search.text().strip() if hasattr(self, "ed_search") else ""
        n_rows = tbl.rowCount()

        if not raw_kw:
            # 清空关键词：恢复显示全量行
            for r in range(n_rows):
                tbl.setRowHidden(r, False)
            if hasattr(self, "lbl_search_count"):
                self.lbl_search_count.setText("")
                self.lbl_search_count.hide()
            return

        kw = raw_kw.lower()
        # 清洗市场前缀 (如 sh600688 / sz002526 / bj832089 -> 纯代码)
        pure_kw = kw.replace("sh", "").replace("sz", "").replace("bj", "")

        # 占位提示单行不隐藏 (如"当前无符合..."或"非交易时段暂无当日记录")
        if n_rows == 1:
            c0, n0 = self._get_row_code_name(tbl, 0)
            if not c0 and not n0:
                tbl.setRowHidden(0, False)
                if hasattr(self, "lbl_search_count"):
                    self.lbl_search_count.hide()
                return

        match_count = 0
        total_count = 0
        for r in range(n_rows):
            code, name = self._get_row_code_name(tbl, r)
            if not code and not name:
                # 非数据行若在搜索状态下隐藏
                tbl.setRowHidden(r, True)
                continue

            total_count += 1
            c_clean = code.lower().replace("sh", "").replace("sz", "").replace("bj", "")
            n_clean = name.lower()

            is_matched = bool(
                (pure_kw and pure_kw in c_clean)
                or (kw in code.lower())
                or (kw in n_clean)
            )

            tbl.setRowHidden(r, not is_matched)
            if is_matched:
                match_count += 1

        if hasattr(self, "lbl_search_count"):
            self.lbl_search_count.setText(f"{match_count}/{total_count}")
            if match_count > 0:
                self.lbl_search_count.setStyleSheet(
                    "font-size: 8.5pt; color: #8fd18f; font-weight: bold; background: transparent;"
                )
            else:
                self.lbl_search_count.setStyleSheet(
                    "font-size: 8.5pt; color: #ffa64d; font-weight: bold; background: transparent;"
                )
            self.lbl_search_count.show()

    def _on_search_text_changed(self, text: str) -> None:
        """输入框内容变化实时响应过滤。"""
        self._apply_search_filter()

    def _on_search_return_pressed(self) -> None:
        """回车键响应：自动选中并联动第一条匹配的标的。"""
        tbl = self._get_active_table()
        if tbl is None:
            return
        for r in range(tbl.rowCount()):
            if not tbl.isRowHidden(r):
                old_row = tbl.currentRow()
                tbl.selectRow(r)
                it = tbl.item(r, 0)
                if it:
                    tbl.scrollToItem(it)
                if old_row == r:
                    code, name = self._get_row_code_name(tbl, r)
                    if code:
                        self._link_main_stock(code, name)
                tbl.setFocus()
                break

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
                self._set_status(f"⚡ 已发送 {name}({code}) 到异动联动")
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
                self._set_status(f"🎯 已发送 {name}({code}) 到新股次新超短检测工具")
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
                    self._set_status(f"⭐ 已更新重点关注: {name}({code})")
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
        save_config_node_async("fusion_ladder_narrow_mode", self.is_narrow_mode)
        self._apply_all_narrow_modes()

    def _load_show_custom_cols(self) -> bool:
        try:
            return bool(load_config_node("fusion_ladder_show_custom_cols", False))
        except Exception:
            return False

    def _on_custom_cols_toggled(self, checked: bool) -> None:
        self.show_custom_cols = bool(checked)
        save_config_node_async("fusion_ladder_show_custom_cols", self.show_custom_cols)
        self._apply_all_narrow_modes()

    def _resolve_ats_strategy_df(self) -> Optional[pd.DataFrame]:
        """递归获取当前系统运行中的策略主 DataFrame (提取 dff, rank, custom_cols)"""
        try:
            from ats.sector_data_aggregator import SectorDataAggregator
            df, _ = SectorDataAggregator.get_instance().resolve_active_strategy_df(self)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
        main_app = self._get_main_app()
        if main_app is not None:
            for attr in ('current_df', '_last_flat_df', 'last_result_df', 'flat_df', 'result_df', 'df_all', 'top_now'):
                cand = getattr(main_app, attr, None)
                if cand is not None and not cand.empty:
                    return cand
        return None

    def _extract_stock_custom_val(self, df: Optional[pd.DataFrame], code: str, col_key: str) -> tuple[str, Any]:
        """从策略 DataFrame 中提取指定股票代码的自定义列值与数值表示 (供 NumericTableWidgetItem 排序)"""
        if df is None or df.empty:
            return "--", 0.0
        try:
            from JohnsonUtil import commonTips as cct
            format_fn = getattr(cct, 'format_col_value', None)
        except Exception:
            format_fn = None

        cd = str(code).split(".")[0].zfill(6)
        row = None
        if cd in df.index:
            row = df.loc[cd]
        elif 'code' in df.columns:
            matched = df[df['code'].astype(str).str.zfill(6) == cd]
            if not matched.empty:
                row = matched.iloc[0]

        if row is not None:
            for k in (col_key, col_key.lower(), col_key.upper()):
                if k in row:
                    raw_v = row[k]
                    if raw_v is None or (isinstance(raw_v, float) and np.isnan(raw_v)):
                        return "--", 0.0
                    txt = format_fn(col_key, raw_v) if callable(format_fn) else str(raw_v)
                    try:
                        num_v = float(raw_v)
                        if not np.isfinite(num_v):
                            num_v = 0.0
                    except (ValueError, TypeError):
                        num_v = str(raw_v)
                    return txt, num_v
        return "--", 0.0

    def _apply_all_narrow_modes(self) -> None:
        if self.is_narrow_mode:
            # 极窄模式下仅显示核心列，自定义列全部自动隐藏
            self._set_cols_visibility(self.tbl_live, [0, 1, 2, 3, 4, 5, 10, 11, 12])
            self._set_cols_visibility(self.tbl_replay, [0, 1, 2, 3, 4, 5, 6, 7, 11])
            self._set_cols_visibility(self.tbl_trades, [0, 1, 3, 6, 7, 10])
            self._set_cols_visibility(self.tbl_track, [0, 1, 3, 4, 8, 10, 13])
        else:
            # 非极窄模式下：基础列全部展示，自定义列依据 self.show_custom_cols 状态展示/隐藏
            for tbl, base_len in (
                (self.tbl_live, len(self._LIVE_BASE_HEADERS)),
                (self.tbl_replay, len(self._REPLAY_BASE_HEADERS)),
                (self.tbl_trades, len(self._TRADES_BASE_HEADERS)),
                (self.tbl_track, len(self._TRACK_BASE_HEADERS)),
            ):
                col_count = tbl.columnCount()
                for c in range(col_count):
                    if c < base_len:
                        tbl.setColumnHidden(c, False)
                    else:
                        tbl.setColumnHidden(c, not self.show_custom_cols)

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

    def _open_calendar_mode(self) -> None:
        self._calendar_requested = True
        self._refresh_replay_days()

    def _refresh_replay_days(self) -> None:
        if getattr(self, "_is_closing", False):
            return
        worker = getattr(self, "_calendar_worker", None)
        if worker is not None and worker.isRunning():
            return
        self.btn_calendar.setEnabled(False)
        if getattr(self, "_calendar_requested", False):
            self._set_status("状态：后台核验回放分时缓存日期…")
        self._calendar_worker = ReplayCalendarWorker(self)
        self._calendar_worker.done.connect(self._show_verified_calendar)
        self._calendar_worker.failed.connect(self._on_calendar_failed)
        self._calendar_worker.finished.connect(lambda: self.btn_calendar.setEnabled(True))
        self._calendar_worker.start()

    def _on_calendar_failed(self, message):
        self._apply_verified_days([])
        self._set_status("日历读取失败：" + message)

    def _apply_verified_days(self, days):
        """下拉框与日历共享同一份经过分时缓存核验的日期集合。"""
        days = sorted(set(days))
        current = self.cmb_replay_day.currentText().strip()
        self._available_minute_days = set(days)
        self._replay_days = days
        self.cmb_replay_day.blockSignals(True)
        try:
            self.cmb_replay_day.clear()
            for day in days:
                self.cmb_replay_day.addItem(day)
                self.cmb_replay_day.setItemData(self.cmb_replay_day.count() - 1, QColor("#ff6868"), Qt.ItemDataRole.ForegroundRole)
            target = current if current in self._available_minute_days else (days[-1] if days else "")
            self.cmb_replay_day.setCurrentIndex(self.cmb_replay_day.findText(target))
        finally:
            self.cmb_replay_day.blockSignals(False)
        self.cmb_replay_day.setEnabled(bool(days))

    def _show_verified_calendar(self, days):
        if getattr(self, "_is_closing", False):
            return
        self._apply_verified_days(days)
        if not getattr(self, "_calendar_requested", False):
            return
        self._calendar_requested = False
        current = self.cmb_replay_day.currentText().strip()
        dlg = FusionCalendarDialog(days, current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            day = dlg.selected_day
            if day in self._available_minute_days:
                index = self.cmb_replay_day.findText(day)
                if index < 0:
                    self.cmb_replay_day.addItem(day)
                    index = self.cmb_replay_day.findText(day)
                self.cmb_replay_day.setCurrentIndex(index)

    def _init_days(self) -> None:
        """初始化下拉列表日期（严格对齐 ATS 权威交易日历，打开默认显示最后一个交易日数据）。

        严禁在 Qt UI 主线程实例化 DayReplay()（会反序列化 21MB minute_kline_cache.pkl 导致界面冻结 600ms+）。
        """
        cur_today, is_trade_day, last_trade_day = get_effective_ats_trade_date()
        days_set = set()
        try:
            cand_dirs = list(_shadow_dir_candidates())
            cand_dirs.insert(0, os.path.join(self.ed_trade_root.text().strip(), "logs", "fusion_shadow"))
            ram_d = _detect_ramdisk_dir()
            if ram_d:
                cand_dirs.append(ram_d)
            from ats.fusion.shadow_io import log_days, log_directories
            directories = [p for directory in cand_dirs for p in log_directories(directory)]
            days_set.update(log_days(directories))
            try:
                from ats.fusion.session_ctx import default_store

                st_dir = getattr(default_store(), "dir", "")
                if st_dir and os.path.isdir(st_dir):
                    for nm in os.listdir(st_dir):
                        if nm.endswith(".json") and len(nm) == 15 and nm[:4].isdigit():
                            days_set.add(nm[:-5])
            except Exception:
                pass

            now_hm = datetime.datetime.now().strftime("%H:%M")
            # 仅当当天已有记录，或（是真正交易所交易日且时间已达 09:15 盘前）才将今天纳入
            if (cur_today in days_set) or (is_trade_day and now_hm >= "09:15"):
                days_set.add(cur_today)

            # 确保最后一个有效交易日也在候选中
            if last_trade_day:
                days_set.add(last_trade_day)

            self._production_days = sorted(days_set) if days_set else [last_trade_day or cur_today]
        except Exception:
            self._production_days = [last_trade_day or cur_today]

        # 确定“打开显示最后一个交易日数据”的目标交易日
        now_hm = datetime.datetime.now().strftime("%H:%M")
        if is_trade_day and now_hm >= "09:15" and (cur_today in days_set):
            target_default_day = cur_today
        else:
            # 优先选择有实际影子数据记录的有效交易日，避免开盘前或周末打开白板
            days_with_data = [d for d in self._production_days if d in days_set]
            if days_with_data:
                target_default_day = days_with_data[-1]
            else:
                target_default_day = last_trade_day if last_trade_day in self._production_days else self._production_days[-1]

        self.cmb_day.blockSignals(True)
        self.cmb_day.clear()
        for d in self._production_days:
            self.cmb_day.addItem(d)

        # 默认高亮选中最后一个有效交易日
        sel_idx = self.cmb_day.findText(target_default_day)
        if sel_idx >= 0:
            self.cmb_day.setCurrentIndex(sel_idx)
        else:
            self.cmb_day.setCurrentIndex(len(self._production_days) - 1)
        self.cmb_day.blockSignals(False)
        # 临时候选仅用于启动时显示；核验完成前禁止选择，避免把日志日期当作分时日期。
        self.cmb_replay_day.setEnabled(False)
        QTimer.singleShot(0, self._refresh_replay_days)

    def _on_day_changed(self, text: str) -> None:
        day = text.strip()
        if day:
            self.refresh_live()
            if self.tabs.currentIndex() in (6, 7):
                self._start_cross_day(day)

    def _on_hit_only_toggled(self, checked: bool) -> None:
        try:
            save_config_node_async("fusion_ladder_hit_only", bool(checked))
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

    def _style_structure_only(self, checked: bool) -> None:
        """结构机会选中态用高亮金黄色表达。"""
        try:
            if hasattr(self, "chk_structure_only") and self.chk_structure_only:
                self.chk_structure_only.setProperty("structureOnly", "true" if checked else "false")
                st = self.chk_structure_only.style()
                st.unpolish(self.chk_structure_only)
                st.polish(self.chk_structure_only)
                self.chk_structure_only.update()
        except Exception:
            pass

    def _on_structure_only_toggled(self, checked: bool) -> None:
        """只看结构机会切换：持久化并即时刷新全界面。"""
        try:
            save_config_node_async("fusion_ladder_structure_only", bool(checked))
        except Exception:
            pass
        self._style_structure_only(bool(checked))
        self._render_live(force=True)
        try:
            day = self.cmb_day.currentText().strip() or today_str()
            self._render_track_from_shadow(day)
        except Exception:
            pass

    def _resolve_name(self, code: str, fallback_dict: Optional[Dict[str, Any]] = None) -> str:
        """多通道极速解析股票名称，带多层兜底与常驻缓存，确保绝不返回空白。"""
        cd = str(code or "").strip().split(".")[0].zfill(6)
        if not cd or cd == "000000":
            return ""
        # 1. 优先从 fallback_dict 中获取现有有效中文名
        if fallback_dict and isinstance(fallback_dict, dict):
            fn = str(fallback_dict.get("name") or "").strip()
            if fn and fn != cd and not fn.isdigit() and not fn.startswith("个股_") and fn != "未知":
                return fn
        # 2. 调起加强版 name_of
        nm = name_of(cd)
        if nm and nm != cd and not nm.isdigit() and not nm.startswith("个股_") and nm != "未知":
            return nm
        # 3. 尝试从父窗口/主程序的 name_cache 提取
        for p_obj in (getattr(self, "_py_parent", None), getattr(self, "parent_window", None)):
            if p_obj is not None:
                nc = getattr(p_obj, "name_cache", None)
                if isinstance(nc, dict) and cd in nc:
                    v = str(nc[cd]).strip()
                    if v and v != cd and not v.isdigit() and not v.startswith("个股_") and v != "未知":
                        return v
                if hasattr(p_obj, "get_stock_name"):
                    try:
                        v = str(p_obj.get_stock_name(cd)).strip()
                        if v and v != cd and not v.isdigit() and not v.startswith("个股_") and v != "未知":
                            return v
                    except Exception:
                        pass
        # 4. 终极兜底：调起全局权威解析器 sys_utils.resolve_stock_name
        try:
            from sys_utils import resolve_stock_name
            sn = resolve_stock_name(cd, cached_only=True)
            if sn and sn != cd and not sn.isdigit() and not sn.startswith("个股_") and sn != "未知":
                return sn
        except Exception:
            pass
        return nm or cd

    def _get_live_quote_snapshot(self, code: str) -> Tuple[float, float, float]:
        """微秒级获取个股的 (现价, 当日最高, 当日最低)，无锁只读内存缓存，0 网络 I/O。"""
        cd = str(code or "").strip().split(".")[0].zfill(6)
        if not cd:
            return 0.0, 0.0, 0.0
        # 1. 尝试从父窗口的 current_df / df_realtime 获取
        for p_obj in (getattr(self, "_py_parent", None), getattr(self, "parent_window", None)):
            if p_obj is not None:
                for attr in ("df_realtime", "current_df"):
                    df = getattr(p_obj, attr, None)
                    if df is not None and not getattr(df, "empty", True):
                        try:
                            row = None
                            if cd in df.index:
                                row = df.loc[cd]
                            elif "code" in df.columns:
                                m = df[df["code"] == cd]
                                if not m.empty:
                                    row = m.iloc[0]
                            if row is not None:
                                p = float(row.get("trade", row.get("price", 0.0)) or 0.0)
                                h = float(row.get("high", p) or p)
                                l = float(row.get("low", p) or p)
                                if p > 0:
                                    return p, h, l
                        except Exception:
                            pass
        # 2. 尝试从 TDXGlobalCachePool 内存缓存获取
        try:
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool
            pool = getattr(TDXGlobalCachePool, "_instance", None)
            if pool is not None:
                bars = pool.get_today_bars(cd) if hasattr(pool, "get_today_bars") else None
                if bars and len(bars) > 0:
                    last_b = bars[-1]
                    p = float(last_b.get("close", 0.0) or 0.0)
                    h = max(float(b.get("high", 0.0) or 0.0) for b in bars)
                    l = min(float(b.get("low", 999999.0) or 999999.0) for b in bars)
                    if p > 0:
                        return p, h, l
        except Exception:
            pass
        return 0.0, 0.0, 0.0

    def _get_batch_quotes_snapshot(self, codes: List[str]) -> Dict[str, Dict[str, float]]:
        """批量获取标的权威行情快照（通达信实时/收盘对齐），包含 price, high, low, last_close, day_pct"""
        out: Dict[str, Dict[str, float]] = {}
        clean_codes = [str(c).split(".")[0].zfill(6) for c in codes if c]
        if not clean_codes:
            return out
        # 1. 优先从父窗口 current_df / df_realtime 批量读取
        for p_obj in (getattr(self, "_py_parent", None), getattr(self, "parent_window", None)):
            if p_obj is not None:
                for attr in ("df_realtime", "current_df"):
                    df = getattr(p_obj, attr, None)
                    if df is not None and not getattr(df, "empty", True):
                        for cd in clean_codes:
                            if cd in out:
                                continue
                            try:
                                row = None
                                if cd in df.index:
                                    row = df.loc[cd]
                                elif "code" in df.columns:
                                    m = df[df["code"] == cd]
                                    if not m.empty:
                                        row = m.iloc[0]
                                if row is not None:
                                    p = float(row.get("trade", row.get("price", row.get("close", 0.0))) or 0.0)
                                    h = float(row.get("high", p) or p)
                                    l = float(row.get("low", p) or p)
                                    # 优先提取权威 percent / pct
                                    dp = None
                                    for k in ("percent", "pct", "change_pct", "chg", "day_pct"):
                                        if k in row and row[k] is not None:
                                            try:
                                                v = float(row[k])
                                                if np.isfinite(v):
                                                    dp = v
                                                    break
                                            except Exception:
                                                pass
                                    # 提取真正昨收 (严禁使用 close 避免差值为 0)
                                    lc = None
                                    for k in ("last_close", "lastp", "prev_close", "preclose", "llastp"):
                                        if k in row and row[k] is not None:
                                            try:
                                                v = float(row[k])
                                                if v > 0:
                                                    lc = v
                                                    break
                                            except Exception:
                                                pass
                                    if dp is None and p > 0 and lc is not None and lc > 0:
                                        dp = (p - lc) / lc * 100.0
                                    if lc is None and p > 0 and dp is not None and abs(dp + 100.0) > 1e-4:
                                        lc = p / (1.0 + dp / 100.0)
                                    if p > 0:
                                        out[cd] = {
                                            "price": p,
                                            "high": h,
                                            "low": l,
                                            "last_close": round(lc if lc is not None else p, 3),
                                            "day_pct": round(dp if dp is not None else 0.0, 2),
                                        }
                            except Exception:
                                pass
        # 2. 剩余未命中的代码，通过 TDX 批量极速拉取（0.1s 内完成）
        missing = [c for c in clean_codes if c not in out]
        if missing:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                qs = fetcher.get_security_quotes_safe(missing)
                for q in qs or []:
                    cd = str(q.get("code") or "").split(".")[0].zfill(6)
                    p = float(q.get("price") or 0.0)
                    h = float(q.get("high") or p)
                    l = float(q.get("low") or p)
                    lc = float(q.get("last_close") or p)
                    dp = None
                    for k in ("percent", "pct", "day_pct"):
                        if k in q and q[k] is not None:
                            try:
                                v = float(q[k])
                                if np.isfinite(v):
                                    dp = v
                                    break
                            except Exception:
                                pass
                    if dp is None and p > 0 and lc > 0 and abs(p - lc) > 1e-4:
                        dp = (p - lc) / lc * 100.0
                    if p > 0:
                        out[cd] = {
                            "price": p,
                            "high": h,
                            "low": l,
                            "last_close": lc,
                            "day_pct": round(dp if dp is not None else 0.0, 2),
                        }
            except Exception:
                pass
        return out

    def _set_status(self, message, summary=None):
        full = str(message)
        primary = summary if summary is not None else full.split("｜", 1)[0].replace("\n", " ")
        if len(primary) > 30:
            primary = primary[:29] + "…"
        self.lbl_status.setText(primary)
        self.lbl_status.setToolTip(full)
        details = getattr(self, "status_details", None)
        if details is not None:
            details.setText(full)
            details.setCursorPosition(0)
            details.setToolTip(full)

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
            self._pending_window_states = {
                "fusion_ladder_dialog": node_data,
                "fusion_ladder_stays_on_top": self.stays_on_top,
                "fusion_ladder_anchor_edge": None if self.stays_on_top else self.anchor_edge,
                "fusion_ladder_is_hidden": False if self.stays_on_top else self.is_hidden_state,
            }
            self._state_save_timer.start()
        except Exception as e:
            logger.debug(f"[FusionLadderDialog] 保存窗口状态异常: {e}")

    def _persist_window_states(self) -> None:
        updates = self._pending_window_states
        if updates is None:
            return
        if save_config_nodes_async(updates):
            self._pending_window_states = None
        else:
            logger.warning("[FusionLadderDialog] 窗口状态未能加入配置写入队列")
            self._state_save_timer.start()

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
        if self.is_hidden_state or self.isMaximized() or self.isFullScreen():
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
        if getattr(self, "stays_on_top", False) or self.isMaximized() or self.isFullScreen():
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
        if (not self.isVisible() or getattr(self, "stays_on_top", False)
                or self.isMaximized() or self.isFullScreen()):
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
        if self.isMaximized() or self.isFullScreen():
            if hasattr(self, "snap_timer") and self.snap_timer:
                self.snap_timer.stop()
            return
        if getattr(self, "stays_on_top", False):
            if hasattr(self, "snap_timer") and self.snap_timer:
                self.snap_timer.stop()
            self.anchor_edge = None
            self.normal_geometry = None
            return
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            self.anchor_edge = None
            if hasattr(self, "snap_timer") and self.snap_timer:
                self.snap_timer.start(400)

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
            if (event and event.type() == QEvent.Type.WindowStateChange
                    and (self.isMaximized() or self.isFullScreen())):
                self.snap_timer.stop()
                self.hover_timer.stop()
                if self.anim_group:
                    self.anim_group.stop()
                self._in_snap_action = False
                self._is_dragging = False
                self.anchor_edge = None
                self.is_hidden_state = False
                self.normal_geometry = None
                self.setWindowOpacity(1.0)
            if event and event.type() == QEvent.Type.ActivationChange:
                if self.isActiveWindow() and getattr(self, "is_hidden_state", False):
                    self._is_auto_popping = True
                    QTimer.singleShot(500, lambda: setattr(self, "_is_auto_popping", False))
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
            cur_today, is_trade_day, last_trade_day = get_effective_ats_trade_date(now_dt)

            # 1. 挂机跨日自动推进（仅在系统真实发生跨日且新日为法定交易日时自动更新，绝不篡改用户主动查看的历史日）
            last_sys_day = getattr(self, "_last_tracked_calendar_day", cur_today)
            if cur_today != last_sys_day:
                self._last_tracked_calendar_day = cur_today
                if is_trade_day and t_str >= "09:15:00":
                    curr_combo_day = self.cmb_day.currentText().strip()
                    # 仅当用户此前停留在上一个交易日跟随模式时才平滑递进
                    if curr_combo_day == last_trade_day:
                        idx = self.cmb_day.findText(cur_today)
                        if idx < 0:
                            self.cmb_day.addItem(cur_today)
                            idx = self.cmb_day.findText(cur_today)
                        self.cmb_day.setCurrentIndex(idx)
                        self.refresh_live()

            # 2. 盘后自动沉淀：15:00 以后自动执行收盘持久化（仅限工作日/交易日执行）
            if is_trade_day and t_str >= "15:00:00" and self._last_auto_settle_day != cur_today:
                self._execute_closing_session_settlement(cur_today)
        except Exception as exc:
            logger.warning(f"[FusionLadderDialog] 自动沉淀巡检异常: {exc}")

    def _execute_closing_session_settlement(self, day: str) -> None:
        """执行收盘自动持久化、上下文固化与次日 handoff 交接"""
        try:
            from ats.fusion.session_ctx import default_store
            store = default_store()

            # 只读当日文件，绝不把"回退展示的其他交易日"写进今天
            live_rows = load_live_rows(day, allow_fallback=False)
            # 日志由生产写入进程落盘；UI 不复制 PID 分片回旧单文件。

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
            self._set_status(f"✅ 今日收盘上下文已自动沉淀 (session_ctx/{day}.json)")

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
            idx = self.cmb_replay_day.findText(day)
            if idx < 0:
                self._refresh_replay_days()
                self._set_status("状态：自动收盘沉淀已完成；该日分时缓存待核验，未启动回放")
                return
            self.cmb_replay_day.setCurrentIndex(idx)
            self._auto_replay_day = day
            logger.info("[FusionLadder] 收盘后自动回放 %s：补齐 T+1/信号面板/验收复盘", day)
            self._start_worker([])
            self._set_status(f"状态：今日收盘上下文已自动沉淀，自动回放 {day} 中…")
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
            from ats.fusion.shadow_io import file_signature
            return (day, src_day, file_signature(_resolved_day_paths(path, src_day)))
        except Exception:
            return (day, "", 0, 0.0)

    def _auto_refresh_live(self) -> None:
        """定时静默刷新：只有影子文件真的变了才重绘，避免无谓重建表格。"""
        if getattr(self, "_is_closing", False) or not self.isVisible():
            return
        idx = self.tabs.currentIndex()
        if idx not in (0, 3):
            return
        if self._worker is not None and self._worker.isRunning():
            return
        day = self.cmb_day.currentText().strip() or today_str()
        sig = self._live_source_signature(day)
        if self.chk_focus_only.isChecked() and day == today_str() and self._is_trading_window():
            sig = (sig, int(time.time() // 30))
        tab_sig_map = getattr(self, "_tab_signatures", None)
        if tab_sig_map is None:
            tab_sig_map = self._tab_signatures = {}
        last_sig = tab_sig_map.get(idx)
        if sig == last_sig:
            if idx == 0:
                self._maybe_ensure_data()
            return
        tab_sig_map[idx] = sig
        if idx == 3:
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
            # TK 入口打开窗口时 parent 传 None，这里仅在运行时内存已存在主控时回落到全局实例（杜绝静态 import 导致打包污染）
            try:
                import sys

                _tk = sys.modules.get("instock_MonitorTK")
                if _tk is not None:
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
        now = time.time()
        if (now - float(getattr(self, "_last_init_scan_t", 0.0) or 0.0)) < 300:
            return
        day = self.cmb_day.currentText().strip() or today_str()
        # 优先使用已缓存的最新记录时间戳，避免每 2 秒无变化时仍在 UI 线程重读文件
        cached_day = getattr(self, "_latest_live_day", "")
        cached_ts = float(getattr(self, "_latest_live_ts", 0.0) or 0.0)
        if cached_day == day and cached_ts > 0 and (now - cached_ts) <= 180:
            return
        # 交易时段严格查看当天实时流；非交易时段（夜间/周末/盘前）无数据时自动平滑回退至最近有数据的交易日，绝不白板
        allow_fallback = not (self._is_trading_window() and day == today_str())
        rows = load_live_rows(day, allow_fallback=allow_fallback)
        has_data = bool(rows)
        if has_data:
            try:
                latest = max(float(r.get("ts") or 0.0) for r in rows)
            except Exception:
                latest = 0.0
            self._latest_live_day = day
            self._latest_live_ts = latest
            if latest > 0 and (now - latest) <= 180:
                return
        self._last_init_scan_t = now
        if self._trigger_host_scan():
            self._set_status("状态：{} 已请求主程序执行一轮逻辑扫描，等待影子数据…".format(day))
            self.lbl_status.setStyleSheet("color:#ffd75e; font-weight:bold;")
            return
        # 宿主没有扫描入口时不自动跑全市场回放：回放要加载全量分钟缓存，
        # 与实时扫描抢 CPU，且线程长跑难以在退出时收敛。这里给出明确指引，仍不白板。
        self._set_status(
            "状态：{} 未找到实盘扫描入口｜请确认主程序运行；回放不会生成实盘观测".format(day)
        )
        self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")

    def _on_focus_toggled(self, _checked) -> None:
        self._render_live(force=True)
        result = getattr(self, "_result", None)
        if result is not None:
            self._on_replay_done(result)

    @staticmethod
    def _mark_focus_row(table, row, identity_columns):
        """所有列参与重点置顶，代码和名称使用红色提示。"""
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                continue
            if hasattr(item, "set_pin_status"):
                item.set_pin_status(True)
            item.setBackground(QColor("#4b2026"))
            if column in identity_columns:
                item.setForeground(QColor("#ff6868"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

    @staticmethod
    def _rows_fingerprint(rows: Sequence[Dict[str, Any]]) -> int:
        """看板行集指纹：只有真正影响展示的数据变了才重建表格。

        文件指纹（大小+修改时间）每追加一条记录就会变，但"每票最新一条"的行集
        往往几分钟才变一次。用行集指纹判断，可以避免把 3 万多个单元格反复重建。
        """
        return hash(tuple(
            (r.get("code"), r.get("ts"),
             (r.get("fusion") or {}).get("tier"),
             (r.get("fusion") or {}).get("rar"),
             r.get("focus_rank"))
            for r in rows
        ))

    def _render_live(self, force: bool = True) -> None:
        """包一层重绘开关：整表重建期间关闭重绘，避免 3 万个单元格逐个触发刷新。"""
        tbl = getattr(self, "tbl_live", None)
        if tbl is None:
            return self._render_live_inner(force=force)
        previous = tbl.updatesEnabled()
        tbl.setUpdatesEnabled(False)
        try:
            self._render_live_inner(force=force)
        finally:
            if previous:
                tbl.setUpdatesEnabled(True)

    def _render_live_inner(self, force: bool = True) -> None:
        day = self.cmb_day.currentText().strip() or today_str()
        sig = self._live_source_signature(day)
        if self.chk_focus_only.isChecked() and day == today_str() and self._is_trading_window():
            sig = (sig, int(time.time() // 30))
        if not force and sig == getattr(self, "_live_sig", None):
            return
        rows = load_live_rows(day, allow_fallback=False)
        tbl = self.tbl_live
        total_rows = len(rows)
        if self.chk_focus_only.isChecked():
            from ats.fusion.focus import select_focus
            asof_ts = time.time() if day == today_str() and self._is_trading_window() else max([float(r.get("ts") or 0) for r in rows] or [0])
            focus_ranks = {r["code"]: r["focus_rank"] for r in select_focus(rows, asof_ts)}
            rows = [dict(r, focus_rank=focus_ranks.get(r.get("code"), 0)) for r in rows]
        hit_only = bool(getattr(self, "chk_hit_only", None) is not None and self.chk_hit_only.isChecked())
        structure_only = bool(getattr(self, "chk_structure_only", None) is not None and self.chk_structure_only.isChecked())

        if structure_only and rows:
            rows = [r for r in rows if r.get("focus_rank") or _row_is_structure_opportunity(r)]
            if not rows:
                tbl.setSortingEnabled(False)
                tbl.setRowCount(0)
                tbl.insertRow(0)
                it = self._num_item("当前无符合10日VWAP结构预判的黄金机会——取消勾选 [🎯 只看结构机会] 可查看全池标的", "no_struct")
                it.setForeground(QColor("#ffd24d"))
                tbl.setItem(0, 0, it)
                for c in range(1, tbl.columnCount()):
                    tbl.setItem(0, c, self._num_item("", 0))
                tbl.setSpan(0, 0, 1, max(1, tbl.columnCount()))
                self._set_status(
                    "状态：{} 全池 {} 条｜🎯 结构机会 0｜等待尾盘站稳10V/3V及次日验证点火标的（取消勾选可看全池）".format(day, total_rows)
                )
                self.lbl_status.setStyleSheet("color:#ffd24d; font-weight:bold;")
                tbl.setSortingEnabled(True)
                return

        if hit_only and rows:
            rows = [r for r in rows if r.get("focus_rank") or _row_is_hit(r) or {"逆势收复启动", "逆势收复持稳"} & set(r.get("patterns") or [])]
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
                self._set_status(
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

        fingerprint = self._rows_fingerprint(rows)
        if not force and fingerprint == getattr(self, "_live_render_fp", None):
            # 行集完全没变：不重建表格，只更新状态栏时间戳。
            self._live_sig = sig
            return
        self._live_render_fp = fingerprint

        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        self._live_sig = sig
        tbl.clearSpans()
        if not rows:
            # 永不白板：放一行占位说明，并按交易时段自动拉起初始化
            tbl.insertRow(0)
            hint = ("正在初始化扫描…（交易时段会自动拉起一轮逻辑扫描，无需手动操作）"
                    if self._is_trading_window() else
                    "实盘通道：{} 无有效观测记录；回放结果独立保存，不能补成实盘答案".format(day))
            it = self._num_item(hint, hint)
            it.setForeground(QColor("#ffa64d"))
            tbl.setItem(0, 0, it)
            for c in range(1, tbl.columnCount()):
                tbl.setItem(0, c, self._num_item("", 0))
            tbl.setSpan(0, 0, 1, max(1, tbl.columnCount()))
            self._set_status("状态：{} 暂无影子记录｜{}".format(day, "初始化中" if self._is_trading_window() else "非交易时段"))
            self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;")
            tbl.setSortingEnabled(False)
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
        df_strat = self._resolve_ats_strategy_df()
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
            name = self._resolve_name(code, r)

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
            hit = _row_is_hit(r)
            if hit:
                hit_count += 1

            pct_color = QColor("#c8c8d0") if pct is None else (QColor("#ff5c5c") if pct >= 0 else QColor("#00ff88"))

            # 各列严格接入 NumericTableWidgetItem 保证高精度数值排序
            # 表头: [级别, 代码, 名称, 现价, 涨幅%, RAR, 位, 接, 意, 环, 仓位%, 进场, 止损, 先手min, 来源, 更新时间, 命中, 覆盖%]
            tbl.setItem(i, 0, self._num_item(f"L{tier}", tier, _TIER_COLORS.get(tier), bold=True))
            for col, text in ((1, code), (2, name)):
                item = FusionFocusItem(text, r.get("focus_rank"))
                if r.get("focus_rank"):
                    item.setForeground(QColor("#ff6868"))
                    item.setBackground(QColor("#4b2026"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip("当前逆势重点 #{}；承接站稳优先、低追高距离优先。\n观察不等于可执行；否决：{}".format(r["focus_rank"], fusion.get("veto_reason") or "无"))
                tbl.setItem(i, col, item)
            tbl.setItem(i, 3, self._num_item(price_txt, price))
            pct_item = self._num_item(pct_txt, pct if pct is not None else 0.0, color=pct_color, bold=True)
            pct_source = r.get("pct_source")
            if pct_source == "price_prev_close":
                pct_item.setToolTip("按该记录的现价和昨收计算；原始上报涨幅：{}".format(r.get("reported_pct")))
            elif pct_source == "reported":
                pct_item.setToolTip("缺少同源昨收，显示上报值，尚未校验。")
            else:
                pct_item.setToolTip("旧记录或缺少可信涨幅，不能确认口径。")
            tbl.setItem(i, 4, pct_item)
            tbl.setItem(i, 5, self._num_item(fusion.get("rar", 0), float(fusion.get("rar", 0) or 0)))
            tbl.setItem(i, 6, self._num_item(axes.get("position", 0), float(axes.get("position", 0) or 0)))
            tbl.setItem(i, 7, self._num_item(axes.get("support", 0), float(axes.get("support", 0) or 0)))
            tbl.setItem(i, 8, self._num_item(axes.get("intent", 0), float(axes.get("intent", 0) or 0)))
            tbl.setItem(i, 9, self._num_item(axes.get("regime", 0), float(axes.get("regime", 0) or 0)))
            tbl.setItem(i, 10, self._num_item(f"{fusion.get('size_pct', 0)}%", float(fusion.get("size_pct", 0) or 0)))
            tbl.setItem(i, 11, self._num_item(band, band))
            tbl.setItem(i, 12, self._num_item(stop.get("price", "-"), float(stop.get("price") or 0) if stop.get("price") not in ("-", None) else 0.0))
            tbl.setItem(i, 13, self._num_item(fusion.get("age_min", 0), float(fusion.get("age_min", 0) or 0)))
            sources = ",".join(fusion.get("sources") or [])
            pats = r.get("patterns") or []
            observing = "逆势收复启动" in pats or "逆势收复持稳" in pats
            source_item = self._num_item(("重点{} · ".format(r["focus_rank"]) if r.get("focus_rank") else "") + (("逆势收复持稳" if "逆势收复持稳" in pats else "逆势收复观察") if observing else sources), sources)
            first_ts = r.get("counter_reclaim_first_ts")
            if observing and first_ts:
                source_item.setToolTip("首次发现：{}；仅为观察信号，梯度及否决原因以本行为准".format(
                    datetime.datetime.fromtimestamp(float(first_ts)).strftime("%H:%M:%S")))
            # Qt 单元格只保存回读位置，不复制整条记录或证据。
            cold_value = ((r["_raw_ref"], r.get("_raw_digest"))
                          if r.get("_has_observation_evidence") and r.get("_raw_ref")
                          else r.get("observation_evidence"))
            if cold_value is not None:
                source_item.setData(Qt.ItemDataRole.UserRole + 100, cold_value)
            source_item.setToolTip(source_item.toolTip() or "观察证据：旧记录未保存，不能回填推断")
            tbl.setItem(i, 14, source_item)
            tbl.setItem(i, 15, self._num_item(time_txt, ts))
            tbl.setItem(i, 16, self._num_item("✅" if hit else "", 1 if hit else 0,
                                             color=QColor("#ffd24d") if hit else None, bold=hit))
            tbl.setItem(i, 17, self._num_item(f"{cov_val * 100:.0f}%", cov_val,
                                              color=QColor("#8fd18f") if cov_val >= 0.8 else QColor("#ffa64d")))

            # 动态自定义列 (ats_col)
            if getattr(self, "extra_cols", None):
                for idx_ec, ec in enumerate(self.extra_cols):
                    val_txt, val_raw = self._extract_stock_custom_val(df_strat, code, ec)
                    tbl.setItem(i, 18 + idx_ec, self._num_item(val_txt, val_raw))
            if r.get("focus_rank"):
                self._mark_focus_row(tbl, i, (1, 2))

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
        if source_day == day and latest_ts > 0:
            self._latest_live_day = day
            self._latest_live_ts = latest_ts
        now_txt = datetime.datetime.now().strftime("%H:%M:%S")
        stale = ""
        if latest_ts > 0:
            age_s = time.time() - latest_ts
            if age_s > 60:
                stale = "｜⚠ 最新记录已 {}s 未更新".format(int(age_s))
        day_note = ""
        if source_day and source_day != day:
            day_note = "｜⚠ 今日暂无记录，展示 {} 数据".format(source_day)
        focus_evidence_missing = False
        if self.chk_focus_only.isChecked():
            count_txt = "重点 {} / 上限10｜展示{} / 原始{}条".format(sum(bool(r.get("focus_rank")) for r in rows), len(rows), total_rows)
            if rows and not any(r.get("reclaim_detail") for r in rows):
                focus_evidence_missing = True
                count_txt += "｜⚠ 来源记录缺少重点所需证据"
        elif structure_only:
            count_txt = "🎯 结构机会 {} / 共 {} 条 (已过滤脉冲杂音)".format(len(rows), total_rows)
        elif hit_only:
            count_txt = "命中 {} / 共 {} 条".format(len(rows), total_rows)
        else:
            count_txt = "影子 {} 条".format(len(rows))
        warn = bool(stale or day_note or schema_note or focus_evidence_missing)
        brief = "状态：{} {}{}".format(
            day,
            "重点{}/10".format(sum(bool(r.get("focus_rank")) for r in rows)) if self.chk_focus_only.isChecked()
            else "{}条".format(len(rows)),
            " ⚠" if warn else "",
        )
        self._set_status(
            "状态：{} {}｜L4 {} / L3 {} / L2 {} / L1 {} / L0 {}｜命中 {}｜覆盖 {:.0f}%｜刷新 {}{}{}{}{}".format(
                day, count_txt, tier_count[4], tier_count[3], tier_count[2], tier_count[1], tier_count[0],
                hit_count, cov_avg * 100, now_txt, stale, day_note, schema_note, writer_note,
            ), summary=brief
        )
        self.lbl_status.setStyleSheet("color:#ffa64d; font-weight:bold;" if warn else "color:#8fd18f; font-weight:bold;")
        self._apply_search_filter(tbl)

    # ------------------------------------------------------------------
    # 赛马跟踪（实盘影子流直出，不依赖回放）
    # ------------------------------------------------------------------
    def _track_entries_from_shadow(self, day: str) -> List[Dict[str, Any]]:
        """从当日影子时间序列还原"第一波入局"清单，严格对齐连续竞价交易与通达信权威行情。

        入局口径：该票当日在正式开盘连续竞价（09:30~15:00）首次达到 L2（可执行梯度）的那一条记录。
        彻底排除 09:15~09:29 集合竞价撮合前的虚拟未成交报价，杜绝假价格污染。
        入局后 MFE/MAE/收盘% 接入通达信权威行情（日内最高、最低与最新收盘价），实现点对点精准对齐。
        """
        series = load_live_series(day, allow_fallback=False)
        # 1. 批量获取权威行情快照，实现通达信全口径对齐
        # 仅对当日或显式注入/测试 mock 的场景获取快照，历史普通回放使用时间切片内极值
        quotes_map = {}
        if day == today_str() or hasattr(self, "_custom_quotes_snapshot") or hasattr(self, "_get_batch_quotes_snapshot"):
            try:
                quotes_map = self._get_batch_quotes_snapshot(list(series.keys()))
            except Exception:
                quotes_map = {}

        out: List[Dict[str, Any]] = []
        for code, recs in series.items():
            # 必须只取正式连续竞价时段（09:30~11:30, 13:00~15:00），严格剔除集合竞价假价格
            recs = [r for r in recs if _in_trading_session(r.get("ts"), allow_premarket=False)]
            if not recs:
                continue
            # 严格时序排序：确保时间戳递增
            recs = sorted(recs, key=lambda x: float(x.get("ts") or 0.0))

            # 1. 寻找当日首异动帧 (First Anomaly Frame)：首次出现 tier>=1 或形态识别的记录，若无则取首根
            first_rec = None
            for r in recs:
                t_val = int((r.get("fusion") or {}).get("tier") or 0)
                pats = (r.get("patterns") or (r.get("fusion") or {}).get("evidence") or [])
                if t_val >= 1 or pats:
                    first_rec = r
                    break
            if first_rec is None:
                first_rec = recs[0]

            # 2. 寻找当日入局帧 (Entry Frame)：首次达到可执行梯度（tier>=2）的记录
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

            entry_rec = recs[entry_i]
            ep = float(entry_rec.get("price") or 0.0)
            after = recs[entry_i:]
            prices = [float(x.get("price") or 0.0) for x in after if float(x.get("price") or 0.0) > 0]
            if not prices and ep > 0:
                prices = [ep]

            # 3. 获取通达信权威行情
            q = quotes_map.get(code, {})
            q_price = float(q.get("price") or 0.0)
            q_last_close = float(q.get("last_close") or 0.0)
            q_day_pct = q.get("day_pct")
            q_high = float(q.get("high") or 0.0)
            q_low = float(q.get("low") or 0.0)

            # 4. 买入后时序因果性：
            max_p = max(prices) if prices else ep
            min_p = min(prices) if prices else ep
            if q_high > max_p:
                max_p = q_high
            if q_low > 0 and q_low < min_p:
                min_p = q_low

            # 收盘/最新价：优先通达信权威当前价/收盘价，其次采样点末尾
            cur_price = q_price if q_price > 0 else (prices[-1] if prices else ep)

            # 若当前最新价在买入后创出新高或新低，将其纳入买入后的极值对比
            if cur_price > 0:
                if cur_price > max_p:
                    max_p = cur_price
                if cur_price < min_p:
                    min_p = cur_price

            # 严格计算 MFE 与 MAE
            if ep > 0:
                mfe = max(0.0, (max_p - ep) / ep * 100.0)
                # MAE 是买入后的最大回撤（只能 <= 0，若买入后价格始终高于买入价，回撤为 0.00%）
                mae = min(0.0, (min_p - ep) / ep * 100.0)
                holding_ret = (cur_price - ep) / ep * 100.0
            else:
                mfe = mae = holding_ret = 0.0

            # 当日真实收盘涨跌幅（对齐通达信权威行情）
            if q_day_pct is not None and abs(float(q_day_pct)) > 1e-4:
                day_close_pct = float(q_day_pct)
            elif q_price > 0 and q_last_close > 0 and abs(q_price - q_last_close) > 1e-4:
                day_close_pct = (q_price - q_last_close) / q_last_close * 100.0
            elif recs and recs[-1].get("pct") is not None:
                day_close_pct = float(recs[-1].get("pct"))
            elif entry_rec.get("pct") is not None and abs(float(entry_rec.get("pct") or 0.0)) > 1e-4:
                day_close_pct = float(entry_rec.get("pct"))
            elif first_rec.get("pct") is not None and abs(float(first_rec.get("pct") or 0.0)) > 1e-4:
                day_close_pct = float(first_rec.get("pct"))
            else:
                day_close_pct = float(q_day_pct if q_day_pct is not None else (entry_rec.get("pct") or 0.0))

            keep = 0
            for x in after:
                try:
                    t = int((x.get("fusion") or {}).get("tier") or 0)
                except Exception:
                    t = 0
                if t >= 1:
                    keep += 1
            ev = list((entry_rec.get("fusion") or {}).get("evidence") or [])
            from ats.fusion.shadow_io import hydrate
            te = hydrate(entry_rec).get("track_entry") or entry_rec.get("track") or {}

            # 5. 首异动与入局点数据精确提取（严密对齐时序）
            # 入局：
            te_enter_ts = float(te.get("enter_ts") or 0.0)
            te_enter_price = float(te.get("enter_price") or 0.0)
            if te_enter_ts > 0 and te_enter_price > 0 and te.get("enter_pct") is not None:
                enter_ts = te_enter_ts
                enter_price_val = te_enter_price
                enter_pct = float(te.get("enter_pct"))
            else:
                enter_ts = float(entry_rec.get("ts") or 0.0)
                enter_price_val = ep
                enter_pct = float(entry_rec.get("pct") if entry_rec.get("pct") is not None else 0.0)

            # 首异动：
            first_ts = float(first_rec.get("ts") or enter_ts)
            first_pct = float(first_rec.get("pct") if first_rec.get("pct") is not None else enter_pct)

            te_first_ts = float(te.get("first_ts") or 0.0)
            te_first_pct = te.get("first_pct")
            if te_first_ts > 0 and te_first_ts <= enter_ts and te_first_pct is not None:
                first_ts = te_first_ts
                first_pct = float(te_first_pct)

            # 若时序倒挂（首异动晚于入局），则守卫对齐
            if first_ts > enter_ts and enter_ts > 0:
                first_ts = enter_ts
                first_pct = enter_pct

            since_first = round(enter_pct - first_pct, 2)

            persist_val = float(te.get("persist") or round(keep * 100.0 / max(1, len(after)), 1))
            chain_txt = str(te.get("chain") or " · ".join(ev))[:160]
            ev_n = int(te.get("evidence_n") or len(ev) or (1 if chain_txt else 0))
            is_struct = _row_is_structure_opportunity(entry_rec) or _row_is_structure_opportunity(first_rec)
            out.append({
                "code": code,
                "name": self._resolve_name(code, entry_rec),
                "is_structure": is_struct,
                "tier": int((entry_rec.get("fusion") or {}).get("tier") or 0),
                "enter_ts": enter_ts,
                "enter_price": enter_price_val,
                "enter_pct": enter_pct,
                "first_ts": first_ts,
                "first_pct": first_pct,
                "since_first": since_first,
                "persist": round(persist_val, 1),
                "evidence_n": ev_n,
                "chain": chain_txt,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
                "holding_ret": round(holding_ret, 2),
                "day_close_pct": round(day_close_pct, 2),
                "close_ret": round(holding_ret, 2),
                "cur_price": round(cur_price, 3),
                "max_p": round(max_p, 3),
                "min_p": round(min_p, 3),
            })
        out.sort(key=lambda e: (-e["tier"], -e["persist"]))
        return out

    def _render_track_from_shadow(self, day: str) -> None:
        t3 = self.tbl_track
        df_strat = self._resolve_ats_strategy_df()
        entries = self._track_entries_from_shadow(day)
        structure_only = bool(getattr(self, "chk_structure_only", None) is not None and self.chk_structure_only.isChecked())
        if structure_only and entries:
            entries = [e for e in entries if e.get("is_structure")]
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
            day_pct = float(e.get("day_close_pct") if e.get("day_close_pct") is not None else (e.get("close_ret") or 0.0))
            holding_ret = float(e.get("holding_ret") if e.get("holding_ret") is not None else (e.get("close_ret") or 0.0))
            color_ret = QColor("#ff5c5c") if day_pct >= 0 else QColor("#00ff88")
            mfe_v = float(e.get("mfe") or 0.0)
            mae_v = float(e.get("mae") or 0.0)

            t3.setItem(i, 0, self._num_item(e["code"], e["code"]))
            t3.setItem(i, 1, self._num_item(e["name"], e["name"]))
            t3.setItem(i, 2, self._num_item(_fmt_hms(e["enter_ts"]), e["enter_ts"]))
            t3.setItem(i, 3, self._num_item(f"{e['enter_price']:.2f}" if e["enter_price"] > 0 else "--", e["enter_price"]))
            t3.setItem(i, 4, self._num_item(f"{e['enter_pct']:+.2f}%", e["enter_pct"]))
            t3.setItem(i, 5, self._num_item(_fmt_hms(e["first_ts"]), e["first_ts"]))
            t3.setItem(i, 6, self._num_item(f"{e['first_pct']:+.2f}%", e["first_pct"]))
            # 优化首→入%展示：
            # 若入局即首异动 (first_ts == enter_ts)，但入局后最新价相比入局价已有涨幅走阔 (holding_ret != 0)，
            # 显性呈现 "+0.00% (现+X.XX%)"，让操盘手清晰看到入局后走阔空间，彻底根除全表死 "+0.00%" 的误解；
            # 若 enter_ts > first_ts，展示真实的确认消耗跨度 "+X.XX%"
            sf_val = float(e.get("since_first") or 0.0)
            if e.get("enter_ts", 0) > 0 and e.get("first_ts", 0) > 0 and abs(e["enter_ts"] - e["first_ts"]) < 1e-3:
                if abs(holding_ret) >= 0.05:
                    sf_txt = f"+0.00% (现{holding_ret:+.2f}%)"
                else:
                    sf_txt = "+0.00%"
            else:
                sf_txt = f"{sf_val:+.2f}%"
            item_sf = self._num_item(sf_txt, sf_val)
            item_sf.setToolTip(
                f"首异动时间: {_fmt_hms(e.get('first_ts', 0))} 涨幅: {e.get('first_pct', 0.0):+.2f}%\n"
                f"入局确认时间: {_fmt_hms(e.get('enter_ts', 0))} 涨幅: {e.get('enter_pct', 0.0):+.2f}%\n"
                f"确认跨度: {sf_val:+.2f}% ｜ 入局后持仓走阔: {holding_ret:+.2f}%"
            )
            t3.setItem(i, 7, item_sf)
            t3.setItem(i, 8, self._num_item(e["persist"], float(e["persist"]), bold=True))
            t3.setItem(i, 9, self._num_item(e["evidence_n"], int(e["evidence_n"])))
            t3.setItem(i, 10, self._num_item(e["chain"], e["chain"]))
            t3.setItem(i, 11, self._num_item(f"{mfe_v:+.2f}%", mfe_v, color=QColor("#ff5c5c") if mfe_v > 0 else QColor("#b9b9c8")))
            t3.setItem(i, 12, self._num_item(f"{mae_v:+.2f}%", mae_v, color=QColor("#00ff88") if mae_v < 0 else QColor("#b9b9c8")))

            # 收盘%：与通达信盘口收盘涨幅 100% 对齐，同时兼顾入局后收益
            display_ret = f"{day_pct:+.2f}% (入{holding_ret:+.2f}%)" if abs(day_pct - holding_ret) > 0.05 else f"{day_pct:+.2f}%"
            item_ret = self._num_item(display_ret, day_pct, color=color_ret, bold=True)
            item_ret.setToolTip(
                f"收盘价: {e.get('cur_price', 0.0):.2f} ｜ 当日收盘: {day_pct:+.2f}% ｜ 入局收益: {holding_ret:+.2f}%\n"
                f"全天最高: {e.get('max_p', 0.0):.2f} ｜ 全天最低: {e.get('min_p', 0.0):.2f}"
            )
            t3.setItem(i, 13, item_ret)
            if getattr(self, "extra_cols", None):
                for idx_ec, ec in enumerate(self.extra_cols):
                    val_txt, val_raw = self._extract_stock_custom_val(df_strat, e["code"], ec)
                    t3.setItem(i, 14 + idx_ec, self._num_item(val_txt, val_raw))
        t3.setSortingEnabled(True)
        self._apply_search_filter(t3)

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
        if index == 0:
            try:
                self._render_live(force=False)
            except Exception as exc:
                logger.debug("[FusionLadder] 实时梯度刷新失败: %s", exc)
        elif index == 3:
            try:
                self._render_track_from_shadow(day)
            except Exception as exc:
                logger.debug("[FusionLadder] 赛马跟踪渲染失败: %s", exc)
        elif index in (6, 7):
            self._start_cross_day(day)
        elif index == 2 and self.tbl_trades.rowCount() == 0:
            self._fill_table_hint(
                self.tbl_trades,
                "T+1 订单由回放撮合产生：实盘影子流不下单。点 [▶ 跑回放] 后这里显示当日模拟成交。",
            )
        elif index == 4 and not self.txt_panel.toPlainText().strip():
            self.txt_panel.setPlainText(
                "信号面板由回放统计生成。实盘阶段可先看[实时梯度]与[赛马跟踪]；"
                "收盘后点 [▶ 跑回放] 即可得到完整统计。"
            )
        self._apply_search_filter()

    # ------------------------------------------------------------------
    # 回放与回补持久化
    # ------------------------------------------------------------------
    def _start_worker(self, focus: List[str], iterate: bool = False) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._set_status("状态：回放进行中，请稍候…")
            return
        day = self.cmb_replay_day.currentText().strip()
        if not day:
            self._set_status("状态：无已核验的回放日期，请刷新回放日历")
            return
        # worker 每次读取最新缓存校验日期，不能用上次日历快照阻止新增交易日。
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_focus.setEnabled(False)
        self.btn_iteration.setEnabled(False)
        self._set_status("状态：回放 {} 中…".format(day))
        self.lbl_status.setStyleSheet("color:#ffd75e; font-weight:bold;")

        self._worker = ReplayWorker(
            day=day, focus=focus, top_n=self.spin_top.value(),
            step=int(self.cmb_step.currentData() or 1),
            parent=self, iterate=iterate, history_root=os.path.abspath(self.ed_trade_root.text().strip()),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_iteration_done if iterate else self._on_replay_done)
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
        self.btn_iteration.setEnabled(True)
        self._set_status("状态：回放失败 — {}".format(msg))
        self.lbl_status.setStyleSheet("color:#ff5c5c; font-weight:bold;")

    def _persist_replay_shadow_and_context(self, result) -> int:
        """停用旧回补入口；独立回放由 run_iterations 写入隔离档案。"""
        logger.warning("旧回放回补入口已停用：禁止写入生产影子日志和会话快照")
        return 0

    def _on_replay_done(self, result) -> None:
        self._result = result
        run_dir = result.meta.get("iteration_dir") or ""
        if run_dir and run_dir != self._replay_follow_dir:
            self._replay_follow_dir = run_dir
            self._start_cross_day(self.cmb_day.currentText().strip() or result.day)
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.btn_iteration.setEnabled(True)
        self.progress.setValue(100)

        # Tab 1: 按日回放表格渲染
        # 表头: [时间(0), 代码(1), 名称(2), 现价(3), 涨幅%(4), 终收%(5), 级别(6), RAR(7), 仓位%(8), MFE%(9), MAE%(10), 收盘%(11), 温度℃(12)] + 自定义列
        df_strat = self._resolve_ats_strategy_df()
        # 展示首次发现优先，避免最高分帧淹没早期观察。
        first_by_code = {}
        records = sorted(result.records, key=lambda r: float(r.get("ts") or 0))
        for record in records:
            first_by_code.setdefault(record.get("code"), record)
        focus_rows = []
        if self.chk_focus_only.isChecked():
            selected = (result.meta.get("focus_selection") or {}).get("first_selected") or []
            by_identity = {(str(r.get("code")), float(r.get("ts") or 0)): r for r in records}
            for item in selected:
                code = str(item.get("code") or "")
                record = by_identity.get((code, float(item.get("ts") or 0)))
                if record is not None:
                    focus_rows.append(dict(record, focus_rank=item.get("focus_rank") or 1,
                                           focus_selected_time=item.get("time") or ""))
            focus_codes = {r.get("code") for r in focus_rows}
            rows = (focus_rows + [r for c, r in first_by_code.items() if c not in focus_codes])[:1000]
        else:
            rows = list(first_by_code.values())[:1000]
        tbl = self.tbl_replay
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        for r in rows:
            i = tbl.rowCount()
            tbl.insertRow(i)
            cd = str(r["code"]).split(".")[0].zfill(6)
            nm = self._resolve_name(cd, r)
            entry_p = float(r.get("entry") or 0.0)
            pct_v = float(r.get("pct") or 0.0)
            tier = r["tier"]

            tbl.setItem(i, 0, self._num_item(r["time"], r["time"]))
            tbl.setItem(i, 1, self._num_item(cd, cd))
            tbl.setItem(i, 2, self._num_item(nm, nm))
            tbl.setItem(i, 3, self._num_item(f"{entry_p:.2f}" if entry_p > 0 else "-", entry_p))
            tbl.setItem(i, 4, self._num_item(f"{pct_v:+.2f}%", pct_v, color=QColor("#ff5c5c") if pct_v >= 0 else QColor("#00ff88"), bold=True))

            # 🌟 自动后验能力：终收% (全天最终收盘涨跌幅)
            day_close_pct = r.get("day_close_pct")
            if day_close_pct is None:
                close_evidence = r.get("close_ret")
                day_close_pct = ((1 + pct_v / 100) * (1 + float(close_evidence) / 100) - 1) * 100 if close_evidence is not None else None
            else:
                day_close_pct = float(day_close_pct)
            close_p = float(r.get("day_close") or 0.0)
            close_ret_v = float(r.get("close_ret") or 0.0)

            item_day_close = self._num_item(
                f"{day_close_pct:+.2f}%" if day_close_pct is not None else "--",
                day_close_pct,
                color=(QColor("#ff5c5c") if day_close_pct >= 0 else QColor("#00ff88")) if day_close_pct is not None else None,
                bold=True
            )
            item_day_close.setToolTip(
                f"【自动后验对照】\n"
                f"• 标的代码: {cd} {nm}\n"
                f"• 触发时间: {r['time']}（当时入局涨幅: {pct_v:+.2f}%）\n"
                + ("• 终收涨幅: 未知" if day_close_pct is None else f"• 终收涨幅: {day_close_pct:+.2f}%") + (f" (全天收盘价: {close_p:.2f})" if close_p > 0 else "") + "\n"
                f"• 入局后收益: {close_ret_v:+.2f}%\n"
                f"• 最大浮盈 MFE: {float(r.get('mfe') or 0):+.2f}% | 最大回撤 MAE: {float(r.get('mae') or 0):+.2f}%\n"
                f"说明: 若终收% > 触发涨幅%，说明入局后持续冲高走强；反之冲高回落。"
            )
            tbl.setItem(i, 5, item_day_close)

            tbl.setItem(i, 6, self._num_item(r["tier_name"], tier, _TIER_COLORS.get(tier), bold=True))
            tbl.setItem(i, 7, self._num_item(r["rar"], float(r["rar"] or 0)))
            tbl.setItem(i, 8, self._num_item(f"{r['size_pct']}%", float(r["size_pct"] or 0)))
            tbl.setItem(i, 9, self._num_item(f"{r['mfe']:+.2f}%", float(r["mfe"] or 0)))
            tbl.setItem(i, 10, self._num_item(f"{r['mae']:+.2f}%", float(r["mae"] or 0)))
            tbl.setItem(i, 11, self._num_item(f"{close_ret_v:+.2f}%", close_ret_v, color=QColor("#ff5c5c") if close_ret_v >= 0 else QColor("#00ff88"), bold=True))
            tbl.setItem(i, 12, self._num_item(f"{r['temp']}℃", float(r["temp"] or 0)))

            liquidity = (result.meta.get("liquidity_history") or {}).get(cd) or {}
            history = liquidity.get("history") or []
            latest = history[0] if history else {}
            turnover, vol_ratio, feature_day = latest.get("turnover_pct"), latest.get("volume_ratio"), latest.get("date")
            evidence = "历史归档：{}；只取回放日前日期，逐行写入时间未知，不参与评分。量比1.0可能为归档默认值。".format(liquidity.get("source") or "不可用")
            for column, value in ((13, turnover), (14, vol_ratio), (15, feature_day)):
                text = "--" if value is None else "{:.2f}".format(value) if isinstance(value, (int, float)) else str(value)
                item = self._num_item(text, value)
                item.setToolTip(evidence)
                tbl.setItem(i, column, item)

            # 动态自定义列 (ats_col)
            if getattr(self, "extra_cols", None):
                for idx_ec, ec in enumerate(self.extra_cols):
                    item = self._num_item("--", None)
                    item.setToolTip("回放档案未保存该自定义列的历史时点值；不使用当前行情补填。")
                    tbl.setItem(i, len(self._REPLAY_BASE_HEADERS) + idx_ec, item)
            if r.get("focus_rank"):
                self._mark_focus_row(tbl, i, (1, 2))
                for column in (1, 2):
                    tbl.item(i, column).setToolTip(
                        "当日首次进入重点：{}；该条行情时间：{}。历史重点不代表当前重点或买入。".format(
                            r.get("focus_selected_time") or r["time"], r["time"]))
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
            nm = self._resolve_name(cd, d)
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
            nm = self._resolve_name(cd, e)
            ret = float(e.get("close_ret") or 0)
            day_pct = float(e.get("day_close_pct") if e.get("day_close_pct") is not None else ret)
            color_ret = QColor("#ff5c5c") if day_pct >= 0 else QColor("#00ff88")
            display_ret = f"{day_pct:+.2f}% (入{ret:+.2f}%)" if abs(day_pct - ret) > 0.05 else f"{day_pct:+.2f}%"

            t3.setItem(i, 0, self._num_item(cd, cd))
            t3.setItem(i, 1, self._num_item(nm, nm))
            ep_val = float(e.get("enter_price") if e.get("enter_price") is not None else (e.get("price") or 0.0))
            ep_pct = float(e.get("enter_pct") if e.get("enter_pct") is not None else (e.get("pct") or 0.0))
            f_pct = float(e.get("first_pct") if e.get("first_pct") is not None else ep_pct)
            sf_pct = float(e.get("since_first_pct") if e.get("since_first_pct") is not None else (ep_pct - f_pct))
            t3.setItem(i, 2, self._num_item(e.get("enter_time") or e.get("first_time", ""), e.get("enter_time") or e.get("first_time", "")))
            t3.setItem(i, 3, self._num_item(f"{ep_val:.2f}" if ep_val > 0 else "--", ep_val))
            t3.setItem(i, 4, self._num_item(f"{ep_pct:+.2f}%", ep_pct))
            t3.setItem(i, 5, self._num_item(e.get("first_time", ""), e.get("first_time", "")))
            t3.setItem(i, 6, self._num_item(f"{f_pct:+.2f}%", f_pct))
            t3.setItem(i, 7, self._num_item(f"{sf_pct:+.2f}%", sf_pct))
            t3.setItem(i, 8, self._num_item(e.get("persist", 0), float(e.get("persist") or 0), bold=True))
            t3.setItem(i, 9, self._num_item(e.get("evidence_n", 0), int(e.get("evidence_n") or 0)))
            t3.setItem(i, 10, self._num_item(e.get("chain", ""), e.get("chain", "")))
            t3.setItem(i, 11, self._num_item(f"{e.get('mfe', 0):+.2f}%", float(e.get("mfe") or 0), color=color_ret))
            t3.setItem(i, 12, self._num_item(f"{e.get('mae', 0):+.2f}%", float(e.get("mae") or 0)))
            item_ret = self._num_item(display_ret, day_pct, color=color_ret, bold=True)
            item_ret.setToolTip(
                f"【收盘表现后验】\n"
                f"• 当日收盘涨幅: {day_pct:+.2f}%\n"
                f"• 入局后真实收益: {ret:+.2f}%\n"
                f"提示: 点击表头可按【收盘涨幅%】升降序排序。"
            )
            t3.setItem(i, 13, item_ret)
            if getattr(self, "extra_cols", None):
                for idx_ec, ec in enumerate(self.extra_cols):
                    val_txt, val_raw = self._extract_stock_custom_val(df_strat, cd, ec)
                    t3.setItem(i, 14 + idx_ec, self._num_item(val_txt, val_raw))
        t3.setSortingEnabled(True)

        # Tab 4: 信号面板
        try:
            dep_n = sum(1 for e in (getattr(result, "entries", []) or []) if deploy_path(e))
            panel = build_panel(records=result.records, entries=getattr(result, "entries", []) or [],
                                meta=result.meta, deploy_count=dep_n)
            self.txt_panel.setPlainText(render_panel(panel))
        except Exception as exc:
            self.txt_panel.setPlainText("信号面板生成失败：{}".format(exc))

        self.txt_report.setPlainText(render_report(result) + "\n\n" + result.meta.get("iteration_report", ""))

        # 更新极窄列显示
        self._apply_all_narrow_modes()
        self._apply_search_filter()

        self._set_status(
            "状态：{} 回放完成｜独立档案 {}｜评估 {}｜入局 {}｜14:45前历史重点 {}".format(
                result.day, result.meta.get("iteration_dir", "--"), result.meta.get("evaluations"),
                result.meta.get("entries", 0), len(focus_rows),
            )
        )
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

    def run_replay(self) -> None:
        self._start_worker([])

    def _start_cross_day(self, day: str) -> None:
        if self._follow_worker is not None and self._follow_worker.isRunning():
            self._follow_pending_day = day
            return
        days = [d for d in sorted(set(self._replay_days) | set(getattr(self, "_production_days", []))
                                 | set(getattr(self, "_comparison_archive_days", []))) if d <= day]
        self._follow_pending_day = None
        root = os.path.abspath(self.ed_trade_root.text().strip())
        self._follow_worker = CrossDayWorker(days, day, self, root=root, replay_run=self._replay_follow_dir)
        self._follow_worker.done.connect(self._render_cross_day)
        self._follow_worker.failed.connect(self.lbl_paper_status.setText)
        self._follow_worker.finished.connect(self._on_follow_finished)
        self._follow_worker.start()

    def _on_follow_finished(self) -> None:
        pending = getattr(self, "_follow_pending_day", None)
        if pending:
            self._follow_pending_day = None
            QTimer.singleShot(0, lambda: self._start_cross_day(pending))

    def _refresh_cross_day_if_visible(self) -> None:
        if self.isVisible() and self.tabs.currentIndex() in (6, 7):
            self._start_cross_day(self.cmb_day.currentText().strip() or today_str())

    def _refresh_paper_source(self) -> None:
        root = os.path.abspath(self.ed_trade_root.text().strip())
        save_config_node("fusion_trade_center_root", root)
        day = self.cmb_day.currentText().strip() or today_str()
        self._init_days()
        if self.cmb_day.findText(day) >= 0:
            self.cmb_day.setCurrentText(day)
        self._start_cross_day(day)

    def _render_cross_day(self, output, day: str) -> None:
        if (os.path.normcase(output["root"]) != os.path.normcase(os.path.abspath(self.ed_trade_root.text().strip()))
                or day != self.cmb_day.currentText().strip()
                or output.get("requested_replay", "") != self._replay_follow_dir):
            self._follow_pending_day = self.cmb_day.currentText().strip() or today_str()
            return
        replay = output.get("replay") or {"rows": [], "status": "unavailable", "sources": {}, "errors": []}
        self._comparison_archive_days = set(replay.get("sources") or {})
        from ats.fusion.replay_follow import compare_signal_streams
        independent = replay.get("independent") is True
        replay_label = ("独立回放" if independent else
                        "回放含生产证据" if replay.get("production_history") is True else "回放来源待核")
        comparison = compare_signal_streams(output["signals"], replay["rows"]) if independent else {
            row["code"]: "回放输入非独立或未核，不能独立验证" for row in output["signals"] + replay["rows"]}
        rows = [(row, "生产影子") for row in output["signals"]] + [(row, replay_label) for row in replay["rows"]]
        replay_note = ("回放 {} 条 / {} 个档案日｜{}".format(len(replay["rows"]), len(replay["sources"]), replay.get("run_dir", ""))
                       if replay.get("status") == "ready" else "未发现可用回放档案，请运行逐日迭代")
        if replay.get("compatibility_note"):
            replay_note += "｜" + replay["compatibility_note"]
        if replay.get("status") == "ready":
            replay_note += "｜" + replay_label
        self.lbl_cross_status.setText("生产影子 {} 条｜{}｜信号流独立、共用行情缓存；回放不关联PAPER".format(len(output["signals"]), replay_note)
                                      + ("｜档案提示：" + "；".join(replay["errors"][:3]) if replay.get("errors") else ""))
        self._render_paper_follow(output["paper"], output["shadow_errors"])
        paper_by_code = {}
        for cycle in output["paper"]["rows"]:
            if cycle["remaining"] > 0 or cycle["code"] not in paper_by_code:
                paper_by_code[cycle["code"]] = cycle
        table = self.tbl_cross_day
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for row, source in rows:
            i = table.rowCount()
            table.insertRow(i)
            values = [row["code"], source, row["name"], row["first_day"], _fmt_hms(row["first_ts"]),
                      "{:.2f}".format(row["reference"]), row["last_day"], _fmt_hms(row["last_ts"]),
                      "{:.2f}".format(row["last_price"]), "{:+.2f}%".format(row["return_pct"]),
                      len(row["days"]), row["status"], "{:+.2f}%".format(row["mfe_pct"]),
                      "{:+.2f}%".format(row["mae_pct"]), row["signal_status"],
                      " → ".join("{} {:+.2f}%".format(d["day"][5:], d["return_pct"]) for d in row["timeline"]),
                      ("未关联（回放）" if source != "生产影子" else
                       paper_by_code[row["code"]]["status"] if row["code"] in paper_by_code else
                       "无PAPER成交" if output["paper"]["account"].get("read_status") == "READY" else "PAPER源不可用"),
                      comparison.get(row["code"], "来源不足")]
            for col, value in enumerate(values):
                changes = {9: row["return_pct"], 12: row["mfe_pct"], 13: row["mae_pct"]}
                raw = changes.get(col, value)
                item = self._num_item(str(value), raw, _change_color(raw) if col in changes else None)
                note = "回放记录" if source != "生产影子" else "生产影子"
                paths = "\n".join("{}：{}".format(d["day"], replay["sources"].get(d["day"], "仅分钟行情，无回放档案")) for d in row["timeline"]) if source != "生产影子" else ""
                item.setToolTip("{}参考价；MFE/MAE仅含信号后采样价格，非完整行情极值；最新记录不等于收盘价。\n".format(note) + "\n".join("{}：{}条决策记录，状态{}，末价{:.2f}{}".format(d["day"], d.get("signal_records", d["records"]), d.get("signal_status", "未知"), d["last_price"], "（分钟缓存采样）" if d.get("price_source") else "") for d in row["timeline"]) + ("\n" + paths if paths else ""))
                if col == 15:
                    from ats.fusion.observation import observation_summary
                    item.setToolTip(item.toolTip() + "\n" + "\n".join(
                        d["day"] + "：" + observation_summary(d.get("observation_evidence")) for d in row["timeline"]))
                if col == len(values) - 1:
                    item.setToolTip("逐日比较同代码共同记录日的首条决策记录；时间差=回放时间−生产时间。相差不超过3分钟才显示参考价差，不代表成交或两套决策完全一致。\n" + comparison.get(row["code"], "来源不足").replace("｜", "\n"))
                table.setItem(i, col, item)
        table.setSortingEnabled(True)
        if not rows:
            self._fill_table_hint(table, "没有可用生产或回放观察；请运行逐日迭代并确认档案目录。")
        if replay.get("errors"):
            self.lbl_paper_status.setText(self.lbl_paper_status.text() + "｜回放档案提示：" + "；".join(replay["errors"][:3]))
        self._apply_search_filter(table)

    def _render_paper_follow(self, output, shadow_errors=0) -> None:
        account, rows = output["account"], output["rows"]
        reconciliation = account.get("reconciliation") or {}
        self.lbl_paper_status.setText(
            "PAPER｜{}｜快照日 {}｜订单 {} / 持仓 {}｜{}｜影子坏行 {}｜{}".format(
                account.get("source_path", ""), account.get("trade_date") or "未知",
                len(account.get("orders") or []), len(account.get("positions") or {}),
                "账户可执行" if reconciliation.get("paper_execution_ready") is True else "账户未就绪/待对账",
                shadow_errors, account.get("error") or reconciliation.get("block_reason") or ""))
        table = self.tbl_paper_follow
        table.setSortingEnabled(False)
        table.clearSpans()
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            chain = " → ".join("{} {} {}@{} #{}".format(e.get("timestamp"), e.get("action"), e.get("volume"), e.get("price"), e.get("order_id")) for e in row["events"])
            values = [row["code"], row["name"] or row["code"], row["signal_day"], row["signal_price"],
                      row["entry_time"], row["buy_price"], row["bought"], row["sold"], row["remaining"],
                      row.get("sellable"), row["last_price"], row["floating_pct"], row["realized"], row["realized_pct"],
                      row["exit_time"], row["status"], row["association"], chain, row["data_status"]]
            tooltip = chain + "\n" + "；".join(row["issues"]) + "\n指令ID：" + row["directive"]
            for col, value in enumerate(values):
                text = "--" if value is None else "{:.2f}".format(value) if isinstance(value, float) else str(value)
                item = self._num_item(text, value, _change_color(value) if col in (11, 12, 13) else None)
                item.setToolTip(tooltip)
                if row["issues"] and col not in (11, 12, 13):
                    item.setForeground(QColor("#ffd166"))
                table.setItem(i, col, item)
        table.setSortingEnabled(True)
        if not rows:
            self._fill_table_hint(table, "所选日之前没有可用PAPER成交；" + str(account.get("error") or "请核对交易中心目录与快照日期。"))
        self._apply_search_filter(table)

    def run_iteration(self) -> None:
        self._start_worker([], iterate=True)

    def _on_iteration_done(self, output) -> None:
        from ats.fusion.iteration import render_iteration
        result = output.get("last_result")
        if result is not None:
            result.meta["iteration_dir"] = output["run_dir"]
            self._on_replay_done(result)
        self.btn_run.setEnabled(True)
        self.btn_focus.setEnabled(True)
        self.btn_iteration.setEnabled(True)
        self.progress.setValue(100)
        self.txt_report.setPlainText(render_iteration(output))
        self.tabs.setCurrentIndex(5)
        self._set_status("状态：逐日迭代完成｜档案 {}".format(output["run_dir"]))
        self.lbl_status.setStyleSheet("color:#8fd18f; font-weight:bold;")

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
        calendar_worker = getattr(self, "_calendar_worker", None)
        if calendar_worker is not None and calendar_worker.isRunning():
            calendar_worker.requestInterruption()
            if not calendar_worker.wait(2000):
                event.ignore()
                return
        if hasattr(self, "_tooltip_filter") and self._tooltip_filter is not None:
            try:
                self._tooltip_filter._hide_card()
                app = QApplication.instance()
                if app is not None:
                    app.removeEventFilter(self._tooltip_filter)
            except Exception:
                pass
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
        if self._follow_worker is not None and self._follow_worker.isRunning():
            self._follow_pending_day = None
            try:
                self._follow_worker.done.disconnect(self._render_cross_day)
                self._follow_worker.finished.disconnect(self._on_follow_finished)
            except (TypeError, RuntimeError):
                pass
            self._follow_worker.requestInterruption()
            self._follow_worker.wait(2000)
        self._save_window_states(is_open=False)
        self._state_save_timer.stop()
        self._persist_window_states()
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


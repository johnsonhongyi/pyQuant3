# -*- coding: utf-8 -*-
"""ats/fusion/trap.py — 诱多陷阱与隔日杀跌识别。

为什么单独一层：
    系统此前只会说"放量拉升"，不会说"这是拉给你看的"。
    而 T+1 的亏损大多不是买在下跌里，是买在**冲高回落的那一刻**：
        1) 日内冲高 3%，然后一路回落跌破均价——盘中看着还是红的；
        2) 高开 4%，随后回吐全部涨幅——开盘追进去的人当天就被埋；
        3) 前一日大涨（甚至涨停），第二日直接低开急杀——隔夜风险，止损来不及。

三类陷阱 + 一个跨日风险分，全部只用当下可见的量（不含未来）。

判定口径刻意保守：
    - 必须有"回落幅度"这个硬证据，不靠形态想象；
    - 跨日风险只做加权，不做单一阈值否决（单一阈值会把真突破一起枪毙）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# 盘中陷阱（当天就能看出来）
TRAP_SPIKE_FADE = "冲高回落"       # 从日内高点回落 >= 2.5% 且跌破均价
TRAP_GAP_FADE = "高开回落"         # 高开 >= 3% 后回吐 >= 1.5%
TRAP_PREV_DUMP = "前日大涨今日杀跌"  # 昨日 >= +7%，今日 <= -2% 且放量
TRAP_VOL_STALL = "放量滞涨"        # 量比 >= 2 但涨幅 < 1% 且跌破均价
TRAP_BREAK_VWAP = "跌破均价放量"    # 跌破均价且量比 >= 1.5

TRAP_LABELS: Dict[str, str] = {
    TRAP_SPIKE_FADE: "🪤 冲高回落",
    TRAP_GAP_FADE: "🪤 高开回落",
    TRAP_PREV_DUMP: "🪤 前日大涨今日杀跌",
    TRAP_VOL_STALL: "🪤 放量滞涨",
    TRAP_BREAK_VWAP: "🪤 跌破均价放量",
}

# 每个陷阱的严重度（用于持续性扣分，0~1）
TRAP_WEIGHT = {
    TRAP_SPIKE_FADE: 0.45,
    TRAP_GAP_FADE: 0.40,
    TRAP_PREV_DUMP: 0.75,
    TRAP_VOL_STALL: 0.35,
    TRAP_BREAK_VWAP: 0.30,
}


@dataclass
class TrapConfig:
    spike_drop_pct: float = 2.5        # 自日内高点回落幅度
    spike_min_high_pct: float = 2.0    # 高点至少涨过多少才算"冲高"
    gap_open_pct: float = 3.0          # 高开幅度
    gap_fade_pct: float = 1.5          # 自开盘回吐幅度
    prev_surge_pct: float = 7.0        # 昨日大涨门槛
    dump_pct: float = -2.0             # 今日杀跌门槛
    dump_vol: float = 1.3              # 杀跌放量门槛
    vol_stall_ratio: float = 2.0
    vol_stall_max_pct: float = 1.0
    break_vwap_vol: float = 1.5


def detect_traps(
    price: float,
    prev_close: float,
    day_open: float,
    day_high: float,
    vwap: float,
    pct: float,
    prev_pct: float,
    vol_ratio: float,
    cfg: Optional[TrapConfig] = None,
) -> List[str]:
    """盘中陷阱判定。返回命中的标签列表（可能为空）。"""
    c = cfg or TrapConfig()
    out: List[str] = []
    if price <= 0 or prev_close <= 0:
        return out

    # 1) 冲高回落：高点涨过 2%，当前自高点回落 >= 2.5%，且已跌破均价
    if day_high > 0 and vwap > 0:
        high_pct = (day_high / prev_close - 1.0) * 100.0
        drop = (day_high - price) / day_high * 100.0
        if high_pct >= c.spike_min_high_pct and drop >= c.spike_drop_pct and price < vwap:
            out.append(TRAP_SPIKE_FADE)

    # 2) 高开回落：高开 >= 3%，回吐 >= 1.5%（不要求跌破均价，开盘价本身就是锚）
    if day_open > 0:
        gap = (day_open / prev_close - 1.0) * 100.0
        fade = (day_open - price) / day_open * 100.0
        if gap >= c.gap_open_pct and fade >= c.gap_fade_pct:
            out.append(TRAP_GAP_FADE)

    # 3) 前一日大涨、今日急速杀跌
    if prev_pct >= c.prev_surge_pct and pct <= c.dump_pct and vol_ratio >= c.dump_vol:
        out.append(TRAP_PREV_DUMP)

    # 4) 放量滞涨：量能很大但价格不动，且已在均价下方
    if vol_ratio >= c.vol_stall_ratio and pct < c.vol_stall_max_pct and vwap > 0 and price < vwap:
        out.append(TRAP_VOL_STALL)

    # 5) 跌破均价放量（没有前面几条那么强，单独标记）
    if vwap > 0 and price < vwap * 0.995 and vol_ratio >= c.break_vwap_vol:
        if TRAP_BREAK_VWAP not in out:
            out.append(TRAP_BREAK_VWAP)

    return out


def trap_severity(traps: List[str]) -> float:
    """陷阱严重度 0~1（取最强的一条，避免叠加放大）。"""
    if not traps:
        return 0.0
    return max(TRAP_WEIGHT.get(t, 0.3) for t in traps)


def cross_day_risk(
    prev_pct: float,
    prev_close_pos: float,
    prev_upper_shadow: float,
    ret5d: float,
    prev_amp: float,
) -> Tuple[float, List[str]]:
    """跨日风险分（0~100）：预判"前一日大涨、第二日急速杀跌"。

    这是隔夜风险的唯一可控项——买入当日不能卖，只能靠"昨天长什么样"决定今天要不要接。
    """
    score = 0.0
    notes: List[str] = []

    if prev_pct >= 9.5:
        score += 40.0
        notes.append("昨日涨停/接近涨停({:+.1f}%)".format(prev_pct))
    elif prev_pct >= 7.0:
        score += 32.0
        notes.append("昨日大涨{:+.1f}%".format(prev_pct))
    elif prev_pct >= 5.0:
        score += 18.0

    if prev_upper_shadow >= 0.45 and prev_pct > 2.0:
        score += 22.0
        notes.append("昨日长上影{:.0f}%".format(prev_upper_shadow * 100))
    if prev_close_pos <= 0.35 and prev_pct > 3.0:
        score += 14.0
        notes.append("昨日收在低位{:.0f}%".format(prev_close_pos * 100))

    if ret5d >= 25.0:
        score += 18.0
        notes.append("5日已涨{:+.0f}%".format(ret5d))
    elif ret5d >= 15.0:
        score += 10.0

    if prev_amp >= 10.0:
        score += 8.0
        notes.append("昨日振幅{:.1f}%".format(prev_amp))

    return min(100.0, score), notes


# ---- T+1 持仓决策：昨天买的，今天要不要跟 ----
ACT_CLEAR = "清仓"
ACT_HALF = "减半"
ACT_HOLD = "持有"
ACT_ADD = "加仓"


def position_decision(
    persist: float,
    traps: List[str],
    gap_risk: float,
    drawdown: float,
    carried: bool = True,
) -> Tuple[str, str]:
    """T+1 持仓决策。

    A股买入当日不能卖，所以真正能做的决策只有"次日开盘后"：
        昨日大涨、今日杀跌  -> 清仓（这是最差的信号，不留幻想）
        高开回落 / 冲高回落  -> 减半（先落袋一半，剩下的交给结构）
        量能持续且创新高     -> 加仓
        其余                -> 持有
    """
    if TRAP_PREV_DUMP in traps:
        return ACT_CLEAR, "昨日大涨今日杀跌"
    if gap_risk >= 85.0:
        return ACT_CLEAR, "跨日风险{:.0f}".format(gap_risk)
    if TRAP_SPIKE_FADE in traps and drawdown >= 2.0:
        return ACT_CLEAR, "冲高回落{:.1f}%".format(drawdown)
    if TRAP_GAP_FADE in traps:
        return ACT_HALF, "高开回落"
    if TRAP_BREAK_VWAP in traps and persist < 50.0:
        return ACT_HALF, "跌破均价且持续性弱"
    if persist < 45.0:
        return ACT_HALF, "持续性降至{:.0f}".format(persist)
    if persist >= 75.0 and not traps and drawdown <= 0.5:
        return ACT_ADD, "量能持续{:.0f}且创新高".format(persist)
    return ACT_HOLD, ""


def render_traps(rows: List[Dict]) -> str:
    """陷阱统计（复盘用）。"""
    if not rows:
        return ""
    from collections import Counter

    cnt: Counter = Counter()
    for r in rows:
        for t in (r.get("traps") or []):
            cnt[t] += 1
    if not cnt:
        return ""
    lines = ["| 陷阱 | 次数 |", "|---|---|"]
    for t, n in cnt.most_common():
        lines.append("| {} | {} |".format(TRAP_LABELS.get(t, t), n))
    return "\n".join(lines)

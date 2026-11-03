# -*- coding: utf-8 -*-
"""ats/fusion/engine.py — 三轴评分 + 风险否决 + L0~L4 梯度映射。

核心命题（对应本次需求）：
    系统现在用"单阈值"回答"能不能买"（例如 Supervisor 里 bias > 5% 一律否决），
    所以只有"能/不能"两档。但市场是连续的：同样偏离均价 5%，
    底部箱体首次放量突破 与 连涨三天后高位放量，风险完全不同。
    本引擎把"能不能"改写成四个连续问题：
        1. 买在这里，止损有多近、上方还有多少空间？   -> position
        2. 拉上去之后，有没有人接？                   -> support
        3. 拉升的意图是否明确且持续？                 -> intent
        4. 环境配不配合（温度、板块、龙头）？         -> regime
    再把它们压成一个风险调整分 RAR，映射到 L0~L4 五档执行规格。

三条不可让步的设计约束：
    - 风险是否决器，不是扣分项。破位/过期/跨日/流动性枯竭直接 L0。
    - 级别是时间的函数。同一个票，启动 40 分钟后即使分再高也不能给 L4。
    - 每个结论必须可解释、可复算、可回溯（evidence / invalidate 必填）。
"""

from __future__ import annotations

import time

import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from ats.fusion.contract import AxisScores, FusionDecision, SignalEvent, TierSpec
from ats.fusion.regime import (
    FLIP_ARMED,
    FLIP_CONFIRMED,
    FLIP_FADING,
    FLIP_FLIPPING,
    STAGE_COLD,
    STAGE_EBB,
    STAGE_ICE,
    STAGE_OVERHEAT,
    STAGE_WARMING,
    MarketRegime,
)

# ---------------------------------------------------------------------------
# 梯度表：这是"梯度"的实体。仓位为账户可用资金的百分比上限。
# ---------------------------------------------------------------------------
LADDER: Dict[int, TierSpec] = {
    4: TierSpec(
        tier=4,
        name="L4 主攻",
        base_size_pct=30.0,
        entry_mode="首波放量突破·回踩不破VWAP",
        stop_anchor="底台/SBC支撑-0.5%",
        expire_min=20,
        split=[0.5, 0.3, 0.2],
        max_bias_pct=3.5,
        note="仅温度翻转确认期 + 板块龙头/强共振；分三笔，第二笔必须承接增强",
    ),
    3: TierSpec(
        tier=3,
        name="L3 参与",
        base_size_pct=18.0,
        entry_mode="分时突破前高确认(2bar)",
        stop_anchor="VWAP-0.6%",
        expire_min=30,
        split=[0.6, 0.4],
        max_bias_pct=3.0,
        note="结构清晰度需≥60；突破后回踩不破前高才补第二笔",
    ),
    2: TierSpec(
        tier=2,
        name="L2 试仓",
        base_size_pct=10.0,
        entry_mode="回踩VWAP±0.5%低吸",
        stop_anchor="VWAP-1.2%",
        expire_min=45,
        split=[],
        max_bias_pct=1.5,
        note="不追价，只在均价附近接；跌破均价即撤单",
    ),
    1: TierSpec(
        tier=1,
        name="L1 观察单",
        base_size_pct=4.0,
        entry_mode="限价挂单≤VWAP",
        stop_anchor="支撑-1.0%",
        expire_min=60,
        split=[],
        max_bias_pct=0.5,
        note="只挂不追，用来保持注意力与手感，不参与主仓",
    ),
    0: TierSpec(
        tier=0,
        name="L0 观察",
        base_size_pct=0.0,
        entry_mode="仅记录",
        stop_anchor="-",
        expire_min=0,
        split=[],
        max_bias_pct=0.0,
        note="信号成立但风险不允许参与，只进观察池",
    ),
}

# RAR 分档（初始先验，须按 §校准 用历史分位重标定）
RAR_TIER_CUTS = ((82.0, 4), (72.0, 3), (62.0, 2), (50.0, 1))

# 温度阶段 -> (级别上限, 仓位系数)
TEMP_MATRIX: Dict[str, tuple] = {
    STAGE_ICE: (2, 0.50),
    STAGE_COLD: (3, 0.70),
    STAGE_WARMING: (4, 1.00),
    STAGE_OVERHEAT: (2, 0.60),
    STAGE_EBB: (1, 0.30),
}

# 先手衰减：启动后经过的分钟数 -> (级别上限, 仓位系数)
AGE_TABLE = ((10.0, 4, 1.00), (25.0, 3, 0.85), (45.0, 2, 0.70), (70.0, 1, 0.50))
AGE_FLOOR = (0, 0.00)

MAX_SINGLE_SIZE_PCT = 35.0
MAX_PENALTY = 60.0
STALE_SECONDS = 20.0

DEFAULT_WEIGHTS = {"position": 0.25, "support": 0.20, "intent": 0.20, "regime": 0.15, "relative": 0.20}

# 轴内子项权重：(子项名, 权重)。子项名为 None 表示该子项总有数据。
# 缺失子项从加权中剔除后归一，并用于计算 coverage（数据覆盖率）。
_SUPPORT_PARTS = (
    ("taker_buy_ratio", 0.30),
    ("bid_pressure", 0.25),
    ("structure_clarity", 0.25),
    (None, 0.20),
)
_INTENT_PARTS = (
    ("slope_score", 0.35),
    ("intent_score", 0.30),
    (None, 0.20),
    (None, 0.15),
)


def _axis_availability(parts: tuple, missing: frozenset) -> float:
    """轴内可用子权重占比 (0~1)。"""
    total = sum(w for _n, w in parts) or 1.0
    avail = sum(w for name, w in parts if not name or name not in missing)
    return max(0.0, min(1.0, avail / total))


DEFAULT_VETO = {"stale_seconds": STALE_SECONDS, "max_bias_pct": 7.0, "min_amount_wan": 3000.0}

DEFAULT_PENALTY = {
    "chase_start_pct": 3.0,
    "chase_per_pct": 6.0,
    "chase_cap": 30.0,
    "overheat_penalty": 20.0,
    "crowd_vol_ratio": 4.5,
    "crowd_penalty": 10.0,
    "illiquid_penalty": 15.0,
    "cap": MAX_PENALTY,
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _band(x: float, full_lo: float, full_hi: float, soft_lo: float, soft_hi: float) -> float:
    """梯形隶属度：核心区间给 1.0，两侧线性衰减到 0。"""
    if x < soft_lo or x > soft_hi:
        return 0.0
    if full_lo <= x <= full_hi:
        return 1.0
    if x < full_lo:
        span = max(1e-9, full_lo - soft_lo)
        return max(0.0, (x - soft_lo) / span)
    span = max(1e-9, soft_hi - full_hi)
    return max(0.0, (soft_hi - x) / span)


def tier_of(rar: float, cuts: Optional[tuple] = None) -> int:
    for cut, tier in (cuts or RAR_TIER_CUTS):
        if rar >= cut:
            return tier
    return 0


def _parse_cuts(raw: Any) -> tuple:
    """配置里的分档阈值 -> ((cut, tier), ...)，降序。坏数据退回默认。"""
    if not raw:
        return RAR_TIER_CUTS
    try:
        if isinstance(raw, dict):
            pairs = [
                (float(raw.get("l4", 82.0)), 4),
                (float(raw.get("l3", 72.0)), 3),
                (float(raw.get("l2", 62.0)), 2),
                (float(raw.get("l1", 50.0)), 1),
            ]
        else:
            pairs = [(float(item[0]), int(item[1])) for item in raw]
        pairs.sort(key=lambda x: x[0], reverse=True)
        return tuple(pairs)
    except Exception:
        return RAR_TIER_CUTS


def _parse_age_table(raw: Any) -> tuple:
    """[[分钟上限, 级别上限, 仓位系数], ...] -> 按分钟升序的元组。"""
    if not raw:
        return AGE_TABLE
    try:
        rows = sorted(
            ((float(item[0]), int(item[1]), float(item[2])) for item in raw),
            key=lambda x: x[0],
        )
        return tuple(rows) or AGE_TABLE
    except Exception:
        return AGE_TABLE


def _stop_anchor(event: SignalEvent) -> float:
    """止损锚点优先级：底台 > SBC 支撑 > 分时均价。"""
    if event.base_support > 0:
        return event.base_support * 0.995
    if event.sbc_supp > 0:
        return event.sbc_supp * 0.995
    if event.vwap > 0:
        return event.vwap * 0.994
    return 0.0


def _age_limits(age_min: float) -> tuple:
    for limit_min, tier_cap, coef in AGE_TABLE:
        if age_min <= limit_min:
            return tier_cap, coef
    return AGE_FLOOR


# ---------------------------------------------------------------------------
# 四轴评分
# ---------------------------------------------------------------------------
def score_position(event: SignalEvent) -> tuple:
    """位置质量：买在这里的风险收益结构。

    三个子项：
      止损距离  太近(易被扫)与太远(亏太多)都扣分，2%~4.5% 最佳
      上行空间  到最近阻力的百分比，>2.5% 才算有空间
      日内位置  中位区(0.25~0.65)最佳，顶部(>0.85)显著扣分
    """
    price = event.price
    anchor = _stop_anchor(event)
    notes: List[str] = []

    if anchor > 0 and price > 0:
        stop_gap = (price - anchor) / price * 100.0
    else:
        stop_gap = 0.0
    s_stop = _band(stop_gap, 2.0, 4.5, 0.8, 7.5)

    if event.resistance > price > 0:
        up_room = (event.resistance - price) / price * 100.0
        s_room = _band(up_room, 2.5, 12.0, 0.8, 20.0)
    else:
        s_room = 0.60  # 无阻力数据，给中性值，不奖不罚

    pos = event.pos_in_range()
    s_pos = _band(pos, 0.20, 0.80, 0.02, 0.95)

    s_multi = 0.5
    if event.vwap_5d > 0 and price > 0:
        s_multi = 1.0 if price >= event.vwap_5d else 0.2
        notes.append("站上5日VWAP" if s_multi == 1.0 else "低于5日VWAP")

    if stop_gap > 0:
        notes.append("止损距离{:.1f}%".format(stop_gap))
    if pos >= 0.85:
        notes.append("日内位置{:.0f}%偏高".format(pos * 100))

    score = 100.0 * (0.40 * s_stop + 0.30 * s_room + 0.20 * s_pos + 0.10 * s_multi)
    return _clip(score), notes


def score_support(event: SignalEvent, missing: Optional[frozenset] = None) -> tuple:
    """承接质量：拉上去有没有人接。"""
    missing = missing or frozenset()
    notes: List[str] = []

    s_taker = _band(event.taker_buy_ratio, 58.0, 78.0, 45.0, 95.0)
    s_bid = _band(event.bid_pressure, 55.0, 75.0, 40.0, 92.0)
    s_clarity = _clip(event.structure_clarity) / 100.0
    s_minutes = _band(event.minutes_above_vwap, 20.0, 240.0, 0.0, 300.0)
    if event.minutes_above_vwap <= 0:
        s_minutes = 0.35

    if event.taker_buy_ratio >= 60:
        notes.append("外盘{:.0f}%".format(event.taker_buy_ratio))
    if event.bid_pressure >= 60:
        notes.append("买盘压{:.0f}%".format(event.bid_pressure))
    if event.structure_clarity >= 60:
        notes.append("结构清晰{:.0f}".format(event.structure_clarity))

    parts = (
        (0.30, s_taker, "taker_buy_ratio"),
        (0.25, s_bid, "bid_pressure"),
        (0.25, s_clarity, "structure_clarity"),
        (0.20, s_minutes, None),
    )
    w_sum = 0.0
    acc = 0.0
    for weight, sub, field_name in parts:
        if field_name and field_name in missing:
            continue
        w_sum += weight
        acc += weight * sub
    if w_sum <= 0:
        return 50.0, notes
    return _clip(100.0 * acc / w_sum), notes


def score_intent(event: SignalEvent, missing: Optional[frozenset] = None) -> tuple:
    """意愿强度：拉升是否明确且持续。"""
    missing = missing or frozenset()
    notes: List[str] = []

    s_slope = _clip((event.slope_score - 40.0) / 55.0, 0.0, 1.0)
    s_intent = _clip((event.intent_score - 15.0) / 85.0, 0.0, 1.0)
    s_vel = _band(event.velocity_pct, 0.6, 6.0, 0.0, 9.0)
    if event.velocity_pct <= 0 and event.segment_vol_inc <= 0:
        s_vel = 0.35
    s_vol = _band(event.vol_ratio, 1.6, 4.0, 0.9, 6.0)

    if event.slope_score >= 70:
        notes.append("攻角{:.0f}".format(event.slope_score))
    if event.intent_score >= 75:
        notes.append("意图{:.0f}".format(event.intent_score))
    if event.velocity_pct >= 0.6:
        notes.append("净拉升{:+.1f}%".format(event.velocity_pct))

    parts = (
        (0.35, s_slope, "slope_score"),
        (0.30, s_intent, "intent_score"),
        (0.20, s_vel, None),
        (0.15, s_vol, None),
    )
    w_sum = 0.0
    acc = 0.0
    for weight, sub, field_name in parts:
        if field_name and field_name in missing:
            continue
        w_sum += weight
        acc += weight * sub
    if w_sum <= 0:
        return 50.0, notes
    return _clip(100.0 * acc / w_sum), notes


def score_regime(event: SignalEvent, regime: Optional[MarketRegime]) -> tuple:
    """环境配合：温度、板块共振、翻转状态、龙头地位。"""
    notes: List[str] = []
    if regime is None:
        base = 50.0
        flip_adj = 0.0
    else:
        s_temp = _band(regime.temp, 45.0, 62.0, 28.0, 78.0)
        base = 100.0 * s_temp
        notes.append("温度{:.0f}℃".format(regime.temp))

        flip_adj = 0.0
        if regime.flip_state == FLIP_ARMED:
            flip_adj = 10.0
            notes.append("低位拐头")
        elif regime.flip_state == FLIP_FLIPPING:
            flip_adj = 14.0
            notes.append("正在翻转")
        elif regime.flip_state == FLIP_CONFIRMED:
            flip_adj = 9.0
            notes.append("翻转确认")
        elif regime.flip_state == FLIP_FADING:
            flip_adj = -30.0
            notes.append("退潮中")

    s_sector = _clip(event.sector_resonance) / 100.0
    if event.sector_resonance <= 0:
        s_sector = 0.50
    else:
        if event.sector_resonance >= 60:
            notes.append("板块共振{:.0f}".format(event.sector_resonance))

    score = 0.55 * base + 0.30 * (100.0 * s_sector) + flip_adj
    if event.is_leader:
        score += 8.0
        notes.append("板块龙头")
    return _clip(score), notes


def multiday_adjust(event: SignalEvent) -> float:
    """跨日连续性修正（±10）。"""
    adj = 0.0
    if event.limit_up_streak >= 3:
        adj -= 6.0
    elif event.limit_up_streak >= 1:
        adj += 3.0
    if event.days_since_high == 0:
        adj += 4.0
    elif event.days_since_high >= 15:
        adj -= 3.0
    if event.ret20d > 15.0:
        adj -= 4.0
    elif 0.0 < event.ret20d <= 8.0:
        adj += 2.0

    hunger = float(event.extra.get("hunger", 1.0) or 1.0)
    if hunger > 1.0:
        adj += min(6.0, (hunger - 1.0) * 12.0)
    return adj


def leadership_value(temp: float, consensus: float) -> float:
    """带头价值：温度越低越值钱，趋同越高越没意义。"""
    temp_f = _clip((58.0 - float(temp)) / 30.0, 0.25, 1.0)
    cons_f = _clip(1.0 - 0.70 * float(consensus), 0.25, 1.0)
    return float(0.35 + 0.65 * temp_f * cons_f)


def lead_adjust(event: SignalEvent) -> float:
    """领先度修正（±7）：排头兵加分，跟风扣分。"""
    score = event.extra.get("lead_score")
    if score is None:
        return 0.0
    return float(np.clip((float(score) - 50.0) * 0.16, -7.0, 7.0))


def score_relative(event: SignalEvent, regime: Optional[MarketRegime] = None) -> tuple:
    """相对强度（逆势异动）：大盘在跌、别人在跌，它在涨。"""
    if not event.extra.get("has_rs"):
        return 50.0, []

    rs = float(event.rs5)
    mkt = float(event.extra.get("mkt_ret5", 0.0))
    notes: List[str] = []

    if rs >= 4.0:
        base = 95.0
    elif rs >= 2.5:
        base = 85.0
    elif rs >= 1.5:
        base = 75.0
    elif rs >= 0.5:
        base = 62.0
    elif rs >= -0.5:
        base = 50.0
    elif rs >= -1.5:
        base = 38.0
    else:
        base = 25.0

    if mkt < -0.3 and rs > 0.5:
        base = min(100.0, base + 8.0)
        notes.append("逆势超额{:+.1f}%(全池{:+.1f}%)".format(rs, mkt))
    elif rs >= 1.5:
        notes.append("相对强度{:+.1f}%".format(rs))

    if regime is not None and rs > 0.5:
        cons = float(event.extra.get("consensus", 0.0) or 0.0)
        lv = leadership_value(regime.temp, cons)
        base = 50.0 + (base - 50.0) * lv
        if lv < 0.55:
            notes.append("趋同{:.0%}·温度{:.0f}℃,带头×{:.2f}".format(cons, regime.temp, lv))
        elif lv >= 0.9:
            notes.append("低温低趋同,带头×{:.2f}".format(lv))

    return float(max(0.0, min(100.0, base))), notes


def penalty_of(event: SignalEvent, regime: Optional[MarketRegime], params: Optional[Dict[str, Any]] = None) -> tuple:
    """风险惩罚：解决流动性惩罚读参等问题。"""
    p_cfg = dict(DEFAULT_PENALTY)
    p_cfg.update(params or {})
    notes: List[str] = []
    p = 0.0

    bias = event.bias_pct()
    if bias > p_cfg["chase_start_pct"]:
        chase = min(p_cfg["chase_cap"], (bias - p_cfg["chase_start_pct"]) * p_cfg["chase_per_pct"])
        p += chase
        notes.append("偏离均价{:+.1f}%".format(bias))

    if event.pct >= 7.0 and event.turnover >= 15.0:
        p += 12.0
        notes.append("涨幅{:.1f}%+换手{:.0f}%透支".format(event.pct, event.turnover))

    if event.vol_ratio > p_cfg["crowd_vol_ratio"]:
        p += p_cfg["crowd_penalty"]
        notes.append("量比{:.1f}过度拥挤".format(event.vol_ratio))

    if regime is not None and regime.temp >= 60.0 and not event.is_leader:
        p += p_cfg["overheat_penalty"]
        notes.append("过热期非龙头")

    min_amt = float(p_cfg.get("min_amount_wan", 3000.0))
    if 0 < event.amount_wan < min_amt:
        p += p_cfg["illiquid_penalty"]
        notes.append("成交额不足{:.0f}万".format(event.amount_wan))

    # 操盘手防追涨铁闸：深水下反抽诱多（坚决刹住追涨）
    close_pre1_val = float(event.extra.get("close_pre1") or 0.0)
    vwap10_val = float(event.vwap_10d or event.extra.get("vwap10") or 0.0)
    if close_pre1_val > 0 and vwap10_val > 0 and close_pre1_val < vwap10_val * 0.96:
        p += 15.0
        gap_p = (1.0 - close_pre1_val / vwap10_val) * 100.0
        notes.append("水下结构诱多(昨收距10V-{:.1f}%)".format(gap_p))

    lead_gap_v = float(event.extra.get("lead_gap_min") or 0.0)
    is_prime_v = bool(event.extra.get("is_prime_leader") or event.extra.get("prev_strong_vwap"))
    if not is_prime_v and lead_gap_v >= 10.0 and event.pct >= 4.0:
        chase_p = min(15.0, 6.0 + (lead_gap_v - 10.0) * 0.4)
        p += chase_p
        notes.append("滞后跟风(落后龙头{:.0f}min)".format(lead_gap_v))

    return min(p_cfg["cap"], p), notes


# ---------------------------------------------------------------------------
# 否决器
# ---------------------------------------------------------------------------
def veto_of(
    event: SignalEvent,
    regime: Optional[MarketRegime],
    today: str = "",
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """硬否决：直接 L0，不参与打分。"""
    v_cfg = dict(DEFAULT_VETO)
    v_cfg.update(params or {})

    if event.price <= 0 or event.vwap <= 0:
        return "行情缺失(price/vwap无效)"
    if "pct" in (event.extra.get("missing") or ()):
        return "行情缺失(涨幅及昨收无效)"
    if event.freshness_s > v_cfg["stale_seconds"]:
        return "数据过期{:.0f}s".format(event.freshness_s)
    expected_day = today or (time.strftime("%Y-%m-%d", time.localtime(event.ts)) if event.ts > 0 else "")
    if expected_day and event.trade_date and event.trade_date != expected_day:
        return "跨交易日数据({})".format(event.trade_date)
    if event.base_support > 0 and event.price < event.base_support * 0.998:
        return "跌破底台{:.2f}".format(event.base_support)
    if event.sbc_supp > 0 and event.price < event.sbc_supp * 0.995:
        return "跌破SBC支撑{:.2f}".format(event.sbc_supp)

    vwap10_val = float(event.vwap_10d or event.extra.get("vwap10") or 0.0)
    day_high_val = max(float(event.day_high or 0.0), float(event.extra.get("day_high") or 0.0), float(event.price))

    v3_val = float(event.extra.get("vwap3") or event.extra.get("v3") or 0.0)
    if v3_val > 0 and vwap10_val > 0 and v3_val < vwap10_val * 0.985 and not event.is_leader:
        if event.price < vwap10_val:
            return "均线空头排列下行(3V低于10V·水下诱多禁止赌博)"
    close_pre1_val = float(event.extra.get("close_pre1") or 0.0)
    if close_pre1_val > 0 and event.price < close_pre1_val * 0.98 and event.price < event.vwap and not event.is_leader:
        return "低开破位杀跌(跌破昨收2%且水下运行·禁止接飞刀)"

    underwater_depth = float(event.extra.get("underwater_depth_pct") or 0.0)
    multi_ready = bool(event.extra.get("vwap_multi_cycle_ready"))
    if underwater_depth >= 3.0 and not multi_ready and not event.is_leader and not ("一阳穿三线" in (event.extra.get("patterns") or ())):
        return "多周期VWAP严重水下(距10V-{:.1f}%·反抽诱多)".format(underwater_depth)

    is_weak_val = bool(event.extra.get("is_underwater_weak"))
    if is_weak_val and vwap10_val > 0 and event.price < vwap10_val * 1.005:
        drawdown_pct = ((day_high_val - event.price) / day_high_val * 100.0) if day_high_val > 0 else 0.0
        if drawdown_pct >= 0.8:
            return "走弱反弹至10日VWAP压力区(是止损点不是买点)"

    hi_10d_val = float(event.extra.get("hi_10d") or 0.0)
    if hi_10d_val > 0 and event.price < hi_10d_val:
        near_hi = (hi_10d_val - day_high_val) / hi_10d_val * 100.0 <= 1.5
        drawdown_pct = ((day_high_val - event.price) / day_high_val * 100.0) if day_high_val > 0 else 0.0
        if near_hi and (drawdown_pct >= 1.0 or event.price < event.vwap):
            return "受阻10日前高压力区(前高{:.2f}·不过前高是卖点)".format(hi_10d_val)

    if vwap10_val > 0 and event.price < vwap10_val:
        drawdown_pct = ((day_high_val - event.price) / day_high_val * 100.0) if day_high_val > 0 else 0.0
        if drawdown_pct >= 1.5:
            return "10日VWAP水下冲高回落(回撤{:.1f}%)".format(drawdown_pct)

    if event.price < event.vwap * 0.998:
        return "水下运行(现价{:.2f}低于均价{:.2f})".format(event.price, event.vwap)
    if event.bias_pct() > v_cfg["max_bias_pct"]:
        return "追高透支(偏离均价{:+.1f}%)".format(event.bias_pct())
    if regime is not None and regime.stage == STAGE_EBB and not event.is_leader:
        return "退潮期非龙头"
    if 0 < event.amount_wan < v_cfg["min_amount_wan"]:
        return "流动性不足({:.0f}万)".format(event.amount_wan)
    return ""


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------
class FusionEngine:
    """把 SignalEvent + MarketRegime 压成一条 FusionDecision。

    单写者、纯函数式、无 IO。调用方负责提供新鲜事件与当前温度。
    """

    def __init__(
        self,
        today: str = "",
        max_single_size_pct: float = MAX_SINGLE_SIZE_PCT,
        params: Optional[Dict[str, Any]] = None,
    ):
        self.today = today
        self.params: Dict[str, Any] = dict(params or {})
        self.max_single_size_pct = float(self.params.get("max_single_size_pct", max_single_size_pct))
        self.struct_floor = bool(self.params.get("struct_floor", True))
        self.max_struct_floor_tier = int(self.params.get("max_struct_floor_tier", 4))
        self.exempt_temp_cap_on_struct = bool(self.params.get("exempt_temp_cap_on_struct", True))
        self.use_fixed_cuts = bool(self.params.get("use_fixed_cuts", True))

        self.weights = dict(DEFAULT_WEIGHTS)
        self.weights.update(self.params.get("weights") or {})

        self.veto_params = dict(DEFAULT_VETO)
        self.veto_params.update(self.params.get("veto") or {})

        self.penalty_params = dict(DEFAULT_PENALTY)
        self.penalty_params.update(self.params.get("penalty") or {})

        self.temp_matrix = dict(TEMP_MATRIX)
        for stage, pair in (self.params.get("temp_matrix") or {}).items():
            try:
                self.temp_matrix[stage] = (int(pair[0]), float(pair[1]))
            except Exception:
                continue

        self.cuts = _parse_cuts(self.params.get("tier_cuts"))
        self.age_table = _parse_age_table(self.params.get("age_table"))

    # -- 级别与仓位 -------------------------------------------------------
    def _temp_cap(self, regime: Optional[MarketRegime], event: SignalEvent) -> tuple:
        if regime is None:
            return 4, 1.0
        cap, coef = self.temp_matrix.get(regime.stage, (4, 1.0))

        if regime.stage == STAGE_OVERHEAT and event.is_leader:
            cap = 3
            coef = 0.60

        if regime.flip_state == FLIP_ARMED:
            cap = min(4, cap + 1)
            coef = min(1.0, coef + 0.10)
        elif regime.flip_state == FLIP_FLIPPING:
            cap = min(4, max(cap, 3))
            coef = min(1.0, coef + 0.15)
        elif regime.flip_state == FLIP_CONFIRMED:
            coef = min(1.0, coef + 0.10)
        elif regime.flip_state == FLIP_FADING:
            cap = min(cap, 1)
            coef = min(coef, 0.30)

        return cap, coef

    def _age(self, event: SignalEvent, now: float) -> tuple:
        if event.launch_ts <= 0 or now <= event.launch_ts:
            return 0.0, 4, 1.0
        age_min = (now - event.launch_ts) / 60.0
        for limit_min, cap, coef in self.age_table:
            if age_min <= limit_min:
                return age_min, cap, coef
        return age_min, 0, 0.0

    def _entry_plan(self, tier: int, event: Optional[SignalEvent]) -> Dict[str, Any]:
        spec = LADDER.get(tier)
        if spec is None or tier <= 0 or event is None:
            return {}
        price, vwap = event.price, event.vwap

        if tier == 4:
            lo = max(price * 0.997, vwap * 1.000)
            hi = min(price * 1.003, vwap * 1.030)
        elif tier == 3:
            lo = vwap * 1.000
            hi = min(vwap * 1.015, price * 1.002)
        elif tier == 2:
            lo = vwap * 0.995
            hi = vwap * 1.005
        else:
            lo = 0.0
            hi = vwap * 1.000

        if lo > hi:
            lo = hi * 0.998
        return {
            "mode": spec.entry_mode,
            "price_lo": round(lo, 3),
            "price_hi": round(hi, 3),
            "expire_min": spec.expire_min,
            "split": list(spec.split),
            "max_bias_pct": spec.max_bias_pct,
        }

    def _stop_plan(self, tier: int, event: Optional[SignalEvent]) -> Dict[str, Any]:
        """按档位选止损锚：越激进越贴结构，越试探越留容错。"""
        if event is None or tier <= 0:
            return {}
        price = event.price
        if tier >= 4:
            anchor = event.base_support * 0.995 if event.base_support > 0 else _stop_anchor(event)
        elif tier == 3:
            anchor = event.vwap * 0.994 if event.vwap > 0 else _stop_anchor(event)
        elif tier == 2:
            anchor = event.vwap * 0.988 if event.vwap > 0 else _stop_anchor(event)
        else:
            base = event.base_support if event.base_support > 0 else event.sbc_supp
            anchor = base * 0.99 if base > 0 else event.vwap * 0.985
        if anchor <= 0:
            return {}
        pct = (anchor - price) / price * 100.0 if price > 0 else 0.0
        return {
            "price": round(anchor, 3),
            "pct": round(pct, 2),
            "anchor": LADDER[tier].stop_anchor if tier in LADDER else "-",
        }

    # -- 主入口 -----------------------------------------------------------
    def evaluate(
        self,
        event: SignalEvent,
        regime: Optional[MarketRegime] = None,
        now: Optional[float] = None,
        tier_cap: Optional[int] = None,
        tier_floor: Optional[int] = None,
        cuts: Optional[tuple] = None,
    ) -> FusionDecision:
        now = float(now if now is not None else (event.ts or time.time()))

        # 数据覆盖率前置全量计算（解决 E7：否决分支 coverage=0 的缺陷）
        missing = frozenset(event.extra.get("missing") or ())
        avail = {
            "position": 1.0 if event.price > 0 else 0.0,
            "support": _axis_availability(_SUPPORT_PARTS, missing),
            "intent": _axis_availability(_INTENT_PARTS, missing),
            "regime": 1.0 if regime is not None else 0.0,
            "relative": 1.0 if event.extra.get("has_rs") else 0.0,
        }
        w_all = sum(self.weights.get(k, 0.0) for k in avail) or 1.0
        coverage = sum(self.weights.get(k, 0.0) * v for k, v in avail.items()) / w_all
        provisional = bool(coverage < 0.80)
        used_cuts = tuple(cuts) if cuts else self.cuts

        veto = veto_of(event, regime, self.today, self.veto_params)
        if veto:
            return FusionDecision(
                code=event.code,
                ts=now,
                tier=0,
                tier_name="L0 观察",
                rar=0.0,
                axes=AxisScores(rar=0.0),
                veto_reason=veto,
                size_pct=0.0,
                sources=[event.source] if event.source else [],
                decision_id="{}:{}".format(event.code, int(now * 1000)),
                regime_stage=regime.stage if regime else "",
                flip_state=regime.flip_state if regime else "",
                coverage=round(coverage, 3),
                provisional=provisional,
                cuts=used_cuts,
                evidence=[veto],
                score_tier=0,
                signal_tier=0,
                signal_size_pct=0.0,
                portfolio_tier=0,
                base_rar=0.0,
                adj_rar=0.0,
                floor_tier=0,
                floor_source="",
                cap_tier=0,
                cap_reasons=[veto],
            )

        p, n_pos = score_position(event)
        s, n_sup = score_support(event, missing)
        i, n_itn = score_intent(event, missing)
        r, n_reg = score_regime(event, regime)
        rel, n_rel = score_relative(event, regime)
        pen, n_pen = penalty_of(event, regime, self.penalty_params)

        w = dict(self.weights)
        if not event.extra.get("has_rs"):
            w.pop("relative", None)
        w_sum = sum(w.get(k, 0.0) for k in ("position", "support", "intent", "regime", "relative")) or 1.0
        raw_rar = (
            w.get("position", 0.0) * p
            + w.get("support", 0.0) * s
            + w.get("intent", 0.0) * i
            + w.get("regime", 0.0) * r
            + w.get("relative", 0.0) * rel
        ) / w_sum - pen + multiday_adjust(event) + lead_adjust(event)
        base_rar = _clip(raw_rar, 0.0, 100.0)

        _ev_pats = event.extra.get("patterns") or getattr(event, "patterns", None) or ()
        _struct_status = str(event.extra.get("struct_status") or "")
        _struct_blocked = _struct_status in ("BROKEN", "EVICTED")
        has_box10_hover = bool(
            (not _struct_blocked)
            and (
                "十日洗盘悬空突破" in _ev_pats
                or "结构预判验证" in _ev_pats
                or event.extra.get("box10_hover_break")
                or event.extra.get("structure_confirmed")
            )
        )

        lead_lbl_v = str(event.extra.get("lead_label") or "")
        lead_gap_v = float(event.extra.get("lead_gap_min") or 0.0)
        today_continue_strong = bool(event.pct > 0 and event.price >= event.vwap * 0.998)
        is_prime_leader = bool(
            event.extra.get("is_prime_leader")
            and today_continue_strong
            and lead_lbl_v not in ("跟风", "LABEL_FOLLOW", "冲锋队", "LABEL_STRIKE")
            and lead_gap_v <= 5.0
        )
        is_struct_confirmed = bool("结构预判验证" in _ev_pats or event.extra.get("structure_confirmed"))

        # 定档前加减分（彻底解决 E1 缺陷与 decision.rar != axes.rar）：
        adj_rar = base_rar
        if is_prime_leader:
            adj_rar = min(100.0, adj_rar + 12.0)
        elif bool(event.extra.get("prev_strong_vwap")):
            adj_rar = min(100.0, adj_rar + 8.0)
        elif is_struct_confirmed:
            adj_rar = min(100.0, adj_rar + 8.0)

        if _struct_status == "BROKEN":
            adj_rar = max(0.0, adj_rar - 6.0)
        elif _struct_status == "EVICTED":
            adj_rar = max(0.0, adj_rar - 12.0)

        rar = adj_rar
        axes = AxisScores(position=p, support=s, intent=i, regime=r, relative=rel, penalty=pen, rar=rar)

        score_tier = tier_of(rar, used_cuts)
        tier = score_tier

        # ---- 形态/结构保底 ----
        _floor_cand = int(tier_floor or 0)
        floor_source = "caller_tier_floor" if _floor_cand > 0 else ""
        if has_box10_hover and not _struct_blocked and self.struct_floor:
            if self.max_struct_floor_tier > _floor_cand:
                _floor_cand = self.max_struct_floor_tier
                floor_source = "box10_hover_break" if event.extra.get("box10_hover_break") else "struct_confirm"
        if is_prime_leader and not _struct_blocked:
            if self.max_struct_floor_tier > _floor_cand:
                _floor_cand = self.max_struct_floor_tier
                floor_source = "prime_leader"

        floor_tier = _floor_cand if not _struct_blocked else 0
        if floor_tier > 0:
            tier = max(tier, floor_tier)

        cap_reasons: List[str] = []
        cap_tier = 4

        temp_cap, temp_coef = self._temp_cap(regime, event)
        if ((has_box10_hover and self.struct_floor) or is_prime_leader) and not _struct_blocked:
            if self.exempt_temp_cap_on_struct:
                temp_cap = max(temp_cap, 4)
        if temp_cap < 4:
            cap_reasons.append(f"temp_cap_{regime.stage if regime else ''}_{temp_cap}")
            cap_tier = min(cap_tier, temp_cap)

        age_min, age_cap, age_coef = self._age(event, now)
        if age_cap < 4:
            cap_reasons.append(f"age_cap_{age_min:.0f}m_{age_cap}")
            cap_tier = min(cap_tier, age_cap)

        tier = min(tier, temp_cap, age_cap)

        # 操盘手防追涨铁闸 1：深水下非龙头一律封顶 L2 试仓
        close_pre1_v = float(event.extra.get("close_pre1") or 0.0)
        vwap10_v = float(event.vwap_10d or event.extra.get("vwap10") or 0.0)
        if close_pre1_v > 0 and vwap10_v > 0 and close_pre1_v < vwap10_v * 0.96 and not event.is_leader and not ("一阳穿三线" in _ev_pats):
            if tier > 2:
                cap_reasons.append("deep_water_cap_l2")
                cap_tier = min(cap_tier, 2)
            tier = min(tier, 2)

        # 操盘手防追涨铁闸 2：龙头永远强于其他！同板块滞后跟风标的坚决禁止给 L4
        if not is_prime_leader and lead_gap_v >= 10.0 and lead_lbl_v in ("冲锋队", "跟风", "无导向"):
            if tier >= 4:
                tier = 3
                cap_reasons.append("lagging_follower_cap_l3")
                cap_tier = min(cap_tier, 3)
            if lead_gap_v >= 25.0:
                tier = min(tier, 2)
                cap_reasons.append("lagging_follower_cap_l2")
                cap_tier = min(cap_tier, 2)

        # L4 额外门槛：必须是龙头或强共振，且结构清晰度达标
        if tier >= 4 and not (
            event.is_leader or event.sector_resonance >= 60.0 or has_box10_hover or is_prime_leader
        ):
            tier = 3
            cap_reasons.append("l4_requires_leader_or_resonance")
            cap_tier = min(cap_tier, 3)
        if tier >= 3 and event.structure_clarity > 0 and event.structure_clarity < 60.0:
            tier = min(tier, 2)
            cap_reasons.append("low_clarity_cap_l2")
            cap_tier = min(cap_tier, 2)

        if tier_cap is not None:
            tc = int(tier_cap)
            if tier > tc:
                cap_reasons.append(f"caller_tier_cap_{tc}")
                cap_tier = min(cap_tier, tc)
            tier = max(0, min(tier, tc))

        # 结构失守/剔除的降级
        if _struct_status == "EVICTED":
            if tier > 1:
                cap_reasons.append("struct_evicted_cap_l1")
                cap_tier = min(cap_tier, 1)
            tier = min(tier, 1)
        elif _struct_status == "BROKEN":
            if tier > 2:
                cap_reasons.append("struct_broken_cap_l2")
                cap_tier = min(cap_tier, 2)
            tier = min(tier, 2)

        signal_tier = tier
        spec = LADDER[tier]
        size = spec.base_size_pct * temp_coef * age_coef
        size = min(self.max_single_size_pct, round(max(0.0, size), 1))
        signal_size_pct = size

        invalidate: List[str] = []
        stop_plan = self._stop_plan(tier, event)
        if stop_plan:
            invalidate.append("跌破{:.2f}".format(stop_plan["price"]))
        if tier > 0:
            invalidate.append("{:.0f}min未成交撤单".format(spec.expire_min))
            invalidate.append("温度退潮/炸板率>30%")
            if tier >= 3:
                invalidate.append("外盘回落<50%承接转弱")

        targets: List[Dict[str, Any]] = []
        if tier > 0 and event.price > 0:
            r1 = event.resistance if event.resistance > event.price else event.price * 1.03
            targets.append({"price": round(r1, 3), "action": "减半"})
            targets.append({"price": round(max(r1, event.price * 1.06), 3), "action": "清仓"})

        struct_evs: List[str] = []
        if _struct_status == "EVICTED":
            struct_evs.append("🚫结构剔除(失守{}次·当日不再主攻)".format(int(event.extra.get("struct_break_n") or 0)))
        elif _struct_status == "BROKEN":
            struct_evs.append("⚠️结构失守({}·保底已撤销)".format(str(event.extra.get("struct_reason") or "跌破均线")))

        if is_prime_leader:
            struct_evs.append("🚀板块总龙头(昨日强势VWAP突破带动)")
        elif is_struct_confirmed:
            _cr = float(event.extra.get("struct_cushion_roll") or 0.0)
            if bool(event.extra.get("wash_quality")):
                struct_evs.append("🎯结构验证(洗盘充分·悬空{:+.2f}%)".format(_cr))
            else:
                struct_evs.append("🎯结构验证(昨收站稳10V·悬空{:+.2f}%)".format(_cr))
        elif bool(event.extra.get("is_structure_prejudged")) and not _struct_blocked:
            struct_evs.append("🎯结构预判(昨收站稳10V蓄势)")
        elif bool(event.extra.get("prev_strong_vwap")) and not _struct_blocked:
            struct_evs.append("🎯结构强势(昨日倍量突破10V)")

        if lead_lbl_v == "排头兵" and lead_gap_v <= 5.0 and not is_prime_leader:
            struct_evs.append("🧭首动先锋(早盘领先全板块)")
        elif not is_prime_leader and lead_gap_v >= 10.0 and lead_lbl_v in ("冲锋队", "跟风", "无导向"):
            struct_evs.append("⚠️同板块滞后跟风(落后龙头{:.0f}min·防回落)".format(lead_gap_v))

        evidence = (struct_evs + n_pos + n_sup + n_itn + n_reg + n_rel + n_pen)[:8]

        return FusionDecision(
            code=event.code,
            ts=now,
            tier=tier,
            tier_name=spec.name,
            rar=rar,
            axes=axes,
            size_pct=size,
            temp_coef=temp_coef,
            age_coef=age_coef,
            age_min=age_min,
            entry=self._entry_plan(tier, event),
            stop=stop_plan,
            targets=targets,
            invalidate=invalidate,
            evidence=evidence,
            sources=[event.source] if event.source else [],
            decision_id="{}:{}".format(event.code, int(now * 1000)),
            regime_stage=regime.stage if regime else "",
            flip_state=regime.flip_state if regime else "",
            coverage=round(coverage, 3),
            provisional=provisional,
            cuts=used_cuts,
            score_tier=score_tier,
            signal_tier=signal_tier,
            signal_size_pct=signal_size_pct,
            portfolio_tier=tier,
            base_rar=base_rar,
            adj_rar=adj_rar,
            floor_tier=floor_tier,
            floor_source=floor_source,
            cap_tier=cap_tier,
            cap_reasons=cap_reasons,
        )


# ---------------------------------------------------------------------------
# 收敛：同一标的只留一条，按级别排序
# ---------------------------------------------------------------------------
class FusionBus:
    """跨来源收敛 + 组合级配额。"""

    def __init__(
        self,
        engine: Optional[FusionEngine] = None,
        max_l4: int = 2,
        max_total_pct: float = 85.0,
    ):
        self.engine = engine or FusionEngine()
        self._decisions: Dict[str, FusionDecision] = {}
        self._events: Dict[str, SignalEvent] = {}
        self._regimes: Dict[str, Optional[MarketRegime]] = {}
        self._cuts: Dict[str, Optional[tuple]] = {}
        self._tier_floors: Dict[str, Optional[int]] = {}
        self.max_l4 = int(max_l4)
        self.max_total_pct = float(max_total_pct)
        self._portfolio: List[FusionDecision] = []

    def update(
        self,
        event: SignalEvent,
        regime: Optional[MarketRegime] = None,
        decision: Optional[FusionDecision] = None,
        cuts: Optional[tuple] = None,
        tier_floor: Optional[int] = None,
    ) -> FusionDecision:
        """更新/注册单标的决策。若已传 decision 则直接复用，避免二次无参重评。"""
        self._cuts[event.code] = cuts
        self._tier_floors[event.code] = tier_floor
        if decision is not None:
            new_decision = decision
        else:
            new_decision = self.engine.evaluate(event, regime, cuts=cuts, tier_floor=tier_floor)

        prev = self._decisions.get(event.code)
        if prev is None or new_decision.ts >= prev.ts:
            if prev is not None:
                new_decision.sources = list(dict.fromkeys(list(prev.sources) + list(new_decision.sources)))
            self._decisions[event.code] = new_decision
            self._events[event.code] = event
            self._regimes[event.code] = regime
        else:
            if event.source and event.source not in prev.sources:
                prev.sources = list(dict.fromkeys(prev.sources + [event.source]))
        return self._decisions[event.code]

    def _force_downgrade(self, d: FusionDecision, ev: Optional[SignalEvent] = None) -> FusionDecision:
        """强制降一档并重算执行计划，保证组合预算一定收敛。"""
        nt = max(0, int(d.tier) - 1)
        spec = LADDER[nt]
        size = spec.base_size_pct * float(d.temp_coef or 1.0) * float(d.age_coef or 1.0)
        size = min(float(self.engine.max_single_size_pct), round(max(0.0, size), 1))

        entry = self.engine._entry_plan(nt, ev) if (ev and nt > 0) else {}
        stop_plan = self.engine._stop_plan(nt, ev) if (ev and nt > 0) else {}

        targets: List[Dict[str, Any]] = []
        if nt > 0 and ev and ev.price > 0:
            r1 = ev.resistance if ev.resistance > ev.price else ev.price * 1.03
            targets.append({"price": round(r1, 3), "action": "减半"})
            targets.append({"price": round(max(r1, ev.price * 1.06), 3), "action": "清仓"})

        invalidate: List[str] = []
        if stop_plan:
            invalidate.append("跌破{:.2f}".format(stop_plan["price"]))
        if nt > 0:
            invalidate.append("{:.0f}min未成交撤单".format(spec.expire_min))
            invalidate.append("温度退潮/炸板率>30%")
            if nt >= 3:
                invalidate.append("外盘回落<50%承接转弱")

        return replace(
            d,
            tier=nt,
            portfolio_tier=nt,
            tier_name=spec.name,
            size_pct=size,
            entry=entry,
            stop=stop_plan,
            targets=targets,
            invalidate=invalidate,
        )

    def rebalance(self, max_l4: Optional[int] = None, max_total_pct: Optional[float] = None) -> List[FusionDecision]:
        """按级别 + RAR 重新分配组合预算：限制 L4 数量与总仓位。

        超额时逐级降档，保证计划与档位自洽。
        """
        cap_l4 = self.max_l4 if max_l4 is None else int(max_l4)
        budget = self.max_total_pct if max_total_pct is None else float(max_total_pct)

        ranked = sorted(self._decisions.values(), key=lambda d: (d.tier, d.rar), reverse=True)
        l4_used = 0
        total = 0.0
        out: List[FusionDecision] = []

        for base in ranked:
            ev = self._events.get(base.code)
            rg = self._regimes.get(base.code)
            cached_cuts = self._cuts.get(base.code)
            decision = base

            if decision.tier >= 4 and l4_used >= cap_l4:
                if ev:
                    nxt = self.engine.evaluate(ev, rg, now=base.ts, tier_cap=3, cuts=cached_cuts, tier_floor=0)
                    decision = replace(
                        nxt,
                        score_tier=base.score_tier,
                        signal_tier=base.signal_tier,
                        signal_size_pct=base.signal_size_pct,
                        portfolio_tier=nxt.tier,
                    )

            _guard = 0
            while ev is not None and decision.tier > 0 and total + decision.size_pct > budget:
                _guard += 1
                if _guard > 6:
                    decision = self._force_downgrade(decision, ev)
                    break
                nxt = self.engine.evaluate(
                    ev, rg, now=base.ts, tier_cap=decision.tier - 1, cuts=cached_cuts, tier_floor=0
                )
                if nxt.tier >= decision.tier:
                    decision = self._force_downgrade(decision, ev)
                else:
                    decision = replace(
                        nxt,
                        score_tier=base.score_tier,
                        signal_tier=base.signal_tier,
                        signal_size_pct=base.signal_size_pct,
                        portfolio_tier=nxt.tier,
                    )

            if decision.tier >= 4:
                l4_used += 1
            total += decision.size_pct
            self._decisions[decision.code] = decision
            out.append(decision)

        self._portfolio = out
        return out

    def portfolio(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._portfolio]

    def total_size_pct(self) -> float:
        return round(sum(d.size_pct for d in self._portfolio), 1)

    def top(self, n: int = 10, actionable_only: bool = False) -> List[FusionDecision]:
        items = list(self._decisions.values())
        if actionable_only:
            items = [d for d in items if d.actionable]
        items.sort(key=lambda d: (d.tier, d.rar), reverse=True)
        return items[:n]

    def get(self, code: str) -> Optional[FusionDecision]:
        return self._decisions.get(code)

    def snapshot(self, n: int = 10) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self.top(n)]

    def reset(self) -> None:
        self._decisions.clear()
        self._events.clear()
        self._regimes.clear()
        self._cuts.clear()
        self._tier_floors.clear()
        self._portfolio.clear()

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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    # 注意：突破型龙头本来就贴着日内高点，位置轴不该因此重罚——
    # 追高风险由 penalty 里的"偏离均价"负责，避免同一件事被扣两次。
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


def score_support(event: SignalEvent) -> tuple:
    """承接质量：拉上去有没有人接。"""
    notes: List[str] = []

    s_taker = _band(event.taker_buy_ratio, 58.0, 78.0, 45.0, 95.0)
    s_bid = _band(event.bid_pressure, 55.0, 75.0, 40.0, 92.0)
    s_clarity = _clip(event.structure_clarity) / 100.0
    s_minutes = _band(event.minutes_above_vwap, 20.0, 240.0, 0.0, 300.0)
    if event.minutes_above_vwap <= 0:
        # 字段缺失时给中性偏低值：缺失不等于"刚站上均价"
        s_minutes = 0.35

    if event.taker_buy_ratio >= 60:
        notes.append("外盘{:.0f}%".format(event.taker_buy_ratio))
    if event.bid_pressure >= 60:
        notes.append("买盘压{:.0f}%".format(event.bid_pressure))
    if event.structure_clarity >= 60:
        notes.append("结构清晰{:.0f}".format(event.structure_clarity))

    score = 100.0 * (0.30 * s_taker + 0.25 * s_bid + 0.25 * s_clarity + 0.20 * s_minutes)
    return _clip(score), notes


def score_intent(event: SignalEvent) -> tuple:
    """意愿强度：拉升是否明确且持续。

    注意这里不用"涨幅"作为主变量——涨幅是结果，不是意愿。
    意愿由攻角、主力意图分、净拉升速度、增量量能共同刻画。
    """
    notes: List[str] = []

    s_slope = _clip((event.slope_score - 40.0) / 55.0, 0.0, 1.0)
    s_intent = _clip((event.intent_score - 15.0) / 85.0, 0.0, 1.0)
    s_vel = _band(event.velocity_pct, 0.6, 6.0, 0.0, 9.0)
    if event.velocity_pct <= 0 and event.segment_vol_inc <= 0:
        s_vel = 0.35   # 无分段数据：中性偏低，而不是当作"零拉升"
    s_vol = _band(event.vol_ratio, 1.6, 4.0, 0.9, 6.0)

    if event.slope_score >= 70:
        notes.append("攻角{:.0f}".format(event.slope_score))
    if event.intent_score >= 75:
        notes.append("意图{:.0f}".format(event.intent_score))
    if event.velocity_pct >= 0.6:
        notes.append("净拉升{:+.1f}%".format(event.velocity_pct))

    score = 100.0 * (0.35 * s_slope + 0.30 * s_intent + 0.20 * s_vel + 0.15 * s_vol)
    return _clip(score), notes


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
        s_sector = 0.50   # 板块数据缺失 -> 中性，不惩罚也不奖励
    else:
        if event.sector_resonance >= 60:
            notes.append("板块共振{:.0f}".format(event.sector_resonance))

    score = 0.55 * base + 0.30 * (100.0 * s_sector) + flip_adj
    if event.is_leader:
        score += 8.0
        notes.append("板块龙头")
    return _clip(score), notes


def multiday_adjust(event: SignalEvent) -> float:
    """跨日连续性修正（±10）：让"第几根"影响结论，而不是每天从零开始。"""
    adj = 0.0
    if event.limit_up_streak >= 3:
        adj -= 6.0            # 连板高位接力，T+1 风险大
    elif event.limit_up_streak >= 1:
        adj += 3.0            # 首板/二板：有资金记忆
    if event.days_since_high == 0:
        adj += 4.0            # 昨日刚创 20 日新高
    elif event.days_since_high >= 15:
        adj -= 3.0            # 远离高点，趋势未修复
    if event.ret20d > 15.0:
        adj -= 4.0            # 20 日已透支
    elif 0.0 < event.ret20d <= 8.0:
        adj += 2.0            # 温和上行
    return adj


def score_relative(event: SignalEvent) -> tuple:
    """相对强度（逆势异动）：大盘在跌、别人在跌，它在涨。

    这是用户反复强调的"异动"本质：不是绝对涨幅，而是**相对全池的超额**。
    没有相对强度数据时返回中性 50，不奖不罚。
    """
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

    # 逆势加成：全池在跌而它跑赢
    if mkt < -0.3 and rs > 0.5:
        base = min(100.0, base + 8.0)
        notes.append("逆势超额{:+.1f}%(全池{:+.1f}%)".format(rs, mkt))
    elif rs >= 1.5:
        notes.append("相对强度{:+.1f}%".format(rs))

    return float(max(0.0, min(100.0, base))), notes


def penalty_of(event: SignalEvent, regime: Optional[MarketRegime], params: Optional[Dict[str, Any]] = None) -> tuple:
    """风险惩罚：这些不是"缺点"，是会让你亏钱的东西。"""
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

    if 0 < event.amount_wan < 3000:
        p += p_cfg["illiquid_penalty"]
        notes.append("成交额不足{:.0f}万".format(event.amount_wan))

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
    """硬否决：直接 L0，不参与打分。

    刻意保持"少而硬"：只有不可修复的风险才进这里，
    其余通过 penalty 与级别上限表达，避免又退化成单阈值。
    """
    v_cfg = dict(DEFAULT_VETO)
    v_cfg.update(params or {})

    if event.price <= 0 or event.vwap <= 0:
        return "行情缺失(price/vwap无效)"
    if event.freshness_s > v_cfg["stale_seconds"]:
        return "数据过期{:.0f}s".format(event.freshness_s)
    if today and event.trade_date and event.trade_date != today:
        return "跨交易日数据({})".format(event.trade_date)
    if event.base_support > 0 and event.price < event.base_support * 0.998:
        return "跌破底台{:.2f}".format(event.base_support)
    if event.sbc_supp > 0 and event.price < event.sbc_supp * 0.995:
        return "跌破SBC支撑{:.2f}".format(event.sbc_supp)
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

        # 过热期龙头单独放行一档，但仓位仍压低
        if regime.stage == STAGE_OVERHEAT and event.is_leader:
            cap = 3
            coef = 0.60

        # 翻转状态对级别与系数做微调：这是"提前量"的唯一入口
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

    def _entry_plan(self, tier: int, event: SignalEvent) -> Dict[str, Any]:
        spec = LADDER.get(tier)
        if spec is None or tier <= 0:
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

    def _stop_plan(self, tier: int, event: SignalEvent) -> Dict[str, Any]:
        """按档位选止损锚：越激进越贴结构，越试探越留容错。"""
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
    ) -> FusionDecision:
        now = float(now if now is not None else (event.ts or time.time()))

        veto = veto_of(event, regime, self.today, self.veto_params)
        if veto:
            return FusionDecision(
                code=event.code,
                ts=now,
                tier=0,
                tier_name="L0 观察",
                veto_reason=veto,
                sources=[event.source] if event.source else [],
                decision_id="{}:{}".format(event.code, int(now * 1000)),
                regime_stage=regime.stage if regime else "",
                flip_state=regime.flip_state if regime else "",
                evidence=[veto],
            )

        p, n_pos = score_position(event)
        s, n_sup = score_support(event)
        i, n_itn = score_intent(event)
        r, n_reg = score_regime(event, regime)
        rel, n_rel = score_relative(event)
        pen, n_pen = penalty_of(event, regime, self.penalty_params)

        w = dict(self.weights)
        if not event.extra.get("has_rs"):
            # 没有相对强度数据时，按剩余轴重新归一，避免"缺数据反而加分"
            w.pop("relative", None)
        w_sum = sum(w.get(k, 0.0) for k in ("position", "support", "intent", "regime", "relative")) or 1.0
        rar = (
            w.get("position", 0.0) * p
            + w.get("support", 0.0) * s
            + w.get("intent", 0.0) * i
            + w.get("regime", 0.0) * r
            + w.get("relative", 0.0) * rel
        ) / w_sum - pen + multiday_adjust(event)
        rar = _clip(rar, 0.0, 100.0)
        axes = AxisScores(position=p, support=s, intent=i, regime=r, relative=rel, penalty=pen, rar=rar)

        tier = tier_of(rar, self.cuts)
        temp_cap, temp_coef = self._temp_cap(regime, event)
        age_min, age_cap, age_coef = self._age(event, now)
        tier = min(tier, temp_cap, age_cap)

        # L4 额外门槛：必须是龙头或强共振，且结构清晰度达标
        if tier >= 4 and not (event.is_leader or event.sector_resonance >= 60.0):
            tier = 3
        if tier >= 3 and event.structure_clarity > 0 and event.structure_clarity < 60.0:
            tier = min(tier, 2)
        if tier_cap is not None:
            tier = max(0, min(tier, int(tier_cap)))

        spec = LADDER[tier]
        size = spec.base_size_pct * temp_coef * age_coef
        size = min(self.max_single_size_pct, round(max(0.0, size), 1))

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

        evidence = (n_pos + n_sup + n_itn + n_reg + n_rel + n_pen)[:8]

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
        )


# ---------------------------------------------------------------------------
# 收敛：同一标的只留一条，按级别排序
# ---------------------------------------------------------------------------
class FusionBus:
    """跨来源收敛 + 组合级配额。

    现状问题：一个票被 5 个模块报警就播 5 条，用户无法判断哪条更重要。
    这里以 code 为键只保留一条决策，来源合并进 sources[]，
    对外只输出"按级别 + RAR 排序的 TopN"。

    组合配额（rebalance）解决翻转日的另一个问题：
    单票评分是独立算的，温度一翻转可能同时冒出 5 只 L4，每只 30%，
    合计 150%——仓位梯度必须再加一层"总预算与头部数量"约束。
    """

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
        self.max_l4 = int(max_l4)
        self.max_total_pct = float(max_total_pct)
        self._portfolio: List[FusionDecision] = []

    def update(self, event: SignalEvent, regime: Optional[MarketRegime] = None) -> FusionDecision:
        decision = self.engine.evaluate(event, regime)
        prev = self._decisions.get(event.code)
        if prev is None or decision.ts >= prev.ts:
            if prev is not None:
                decision.sources = list(dict.fromkeys(list(prev.sources) + list(decision.sources)))
            self._decisions[event.code] = decision
            self._events[event.code] = event
            self._regimes[event.code] = regime
        else:
            if event.source and event.source not in prev.sources:
                prev.sources = list(dict.fromkeys(prev.sources + [event.source]))
        return self._decisions[event.code]

    def rebalance(self, max_l4: Optional[int] = None, max_total_pct: Optional[float] = None) -> List[FusionDecision]:
        """按级别 + RAR 重新分配组合预算：限制 L4 数量与总仓位。

        超额时不是"全部砍掉"，而是逐级降档（L4->L3->L2...），
        保证强弱顺序不变、梯度不塌陷。
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
            decision = base

            if decision.tier >= 4 and l4_used >= cap_l4:
                decision = self.engine.evaluate(ev, rg, now=base.ts, tier_cap=3) if ev else decision

            while ev is not None and decision.tier > 0 and total + decision.size_pct > budget:
                decision = self.engine.evaluate(ev, rg, now=base.ts, tier_cap=decision.tier - 1)

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
        self._portfolio.clear()

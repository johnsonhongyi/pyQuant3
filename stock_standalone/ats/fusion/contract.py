# -*- coding: utf-8 -*-
"""ats/fusion/contract.py — 融合层统一数据契约。

为什么需要契约：
    当前系统里同时存在 9 套互不兼容的打分/分级口径
    （SignalLedger 优先级、alpha_score、7 节点 total_score、IPO signal_tier、
     momentum total_score、pattern PRIORITY_MAP、RiskEngine、Supervisor、
     ConsensusArbiter），字段名与量纲都不同，所以无法横向比较，
    也就无法排序，最终只能退化成"谁涨得多谁先报"。

    本文件把各来源压缩成同一个 SignalEvent，把结论压缩成同一个
    FusionDecision，让"跨源比较"成为可能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 输入：统一事件
# ---------------------------------------------------------------------------
@dataclass
class SignalEvent:
    """一个标的在一个时刻的融合输入快照。

    字段全部取自现有模块的真实输出，不做二次行情计算：
      vwap / pct / vol_ratio / amount       <- ats/tdx_realtime_fetcher.py:3726 _normalize_quote_to_snapshot
      bid_pressure / taker_buy_ratio        <- 同上 :5334 / :5335
      slope_score / intent_score            <- 同上 :5583-5594 / :5440-5550
      velocity_pct / segment_vol_inc        <- 同上 :5091 calculate_segmented_velocity
      structure_clarity / minutes_above_vwap<- ats/vwap_trading_engine.py:45-66 VWAPTickState
      sbc_supp / sbc_rev                    <- ats/sbc_core.py:1095 get_sbc_baseline_data
      upper_score                           <- ats/upper_structure_engine.py:95 run()
      launch_ts                             <- 各引擎的首次启动时间（本轮行情的"先手"锚点）
    """

    code: str
    ts: float
    source: str = ""
    price: float = 0.0

    # 均线与结构锚点
    vwap: float = 0.0            # 今日分时 VWAP
    vwap_5d: float = 0.0         # 5 日累计 VWAP（vwap_cum_5d）
    sbc_supp: float = 0.0        # SBC 支撑线
    sbc_rev: float = 0.0         # SBC 反转线
    base_support: float = 0.0    # 底台/箱体下沿（有则优先作为止损锚）
    resistance: float = 0.0      # 上方最近阻力（昨高/前高/箱体上沿）

    # 日内位置
    day_high: float = 0.0
    day_low: float = 0.0
    pct: float = 0.0             # 当日涨幅 %

    # 量能与承接
    vol_ratio: float = 1.0
    turnover: float = 0.0
    amount_wan: float = 0.0      # 成交额（万元）
    taker_buy_ratio: float = 50.0   # 外盘占比 0-100
    bid_pressure: float = 50.0      # 5 档买量占比 0-100
    structure_clarity: float = 0.0  # 0-100
    minutes_above_vwap: float = 0.0

    # 意愿
    slope_score: float = 40.0    # 攻角 10-100
    intent_score: float = 50.0   # 主力意图 15-100
    velocity_pct: float = 0.0    # 分段净拉升 %
    segment_vol_inc: float = 0.0 # 分段增量量能

    # 环境
    sector_resonance: float = 0.0  # 板块共振 0-100
    is_leader: bool = False
    upper_score: float = 0.0

    # 先手与新鲜度（数据不变量）
    launch_ts: float = 0.0       # 本轮启动时刻；0 表示未知
    freshness_s: float = 0.0     # 数据延迟秒数
    trade_date: str = ""         # 事件所属交易日 YYYY-MM-DD

    extra: Dict[str, Any] = field(default_factory=dict)

    def bias_pct(self) -> float:
        """现价相对分时均价偏离 %。正数=已在高位。"""
        if self.vwap <= 0 or self.price <= 0:
            return 0.0
        return (self.price - self.vwap) / self.vwap * 100.0

    def pos_in_range(self) -> float:
        """日内位置 0=最低 1=最高；区间无效时返回 0.5。"""
        if self.day_high <= self.day_low or self.price <= 0:
            return 0.5
        return max(0.0, min(1.0, (self.price - self.day_low) / (self.day_high - self.day_low)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "ts": self.ts,
            "source": self.source,
            "price": self.price,
            "vwap": self.vwap,
            "vwap_5d": self.vwap_5d,
            "sbc_supp": self.sbc_supp,
            "sbc_rev": self.sbc_rev,
            "base_support": self.base_support,
            "resistance": self.resistance,
            "day_high": self.day_high,
            "day_low": self.day_low,
            "pct": self.pct,
            "vol_ratio": self.vol_ratio,
            "turnover": self.turnover,
            "amount_wan": self.amount_wan,
            "taker_buy_ratio": self.taker_buy_ratio,
            "bid_pressure": self.bid_pressure,
            "structure_clarity": self.structure_clarity,
            "minutes_above_vwap": self.minutes_above_vwap,
            "slope_score": self.slope_score,
            "intent_score": self.intent_score,
            "velocity_pct": self.velocity_pct,
            "segment_vol_inc": self.segment_vol_inc,
            "sector_resonance": self.sector_resonance,
            "is_leader": self.is_leader,
            "upper_score": self.upper_score,
            "launch_ts": self.launch_ts,
            "freshness_s": self.freshness_s,
            "trade_date": self.trade_date,
        }


# ---------------------------------------------------------------------------
# 中间：三轴 + 风险惩罚
# ---------------------------------------------------------------------------
@dataclass
class AxisScores:
    """四轴分（0-100）与风险惩罚（0-60）。

    position  位置质量：买在这里，止损有多近、上方空间有多大
    support   承接质量：拉上去有没有人接
    intent    意愿强度：拉升是否明确且持续
    regime    环境配合：温度、板块、龙头
    penalty   风险惩罚：追高、透支、拥挤、过热、流动性
    """

    position: float = 0.0
    support: float = 0.0
    intent: float = 0.0
    regime: float = 0.0
    penalty: float = 0.0
    rar: float = 0.0   # risk-adjusted rank = 加权 - 惩罚

    def to_dict(self) -> Dict[str, float]:
        return {
            "position": round(self.position, 2),
            "support": round(self.support, 2),
            "intent": round(self.intent, 2),
            "regime": round(self.regime, 2),
            "penalty": round(self.penalty, 2),
            "rar": round(self.rar, 2),
        }


# ---------------------------------------------------------------------------
# 输出：梯度决策
# ---------------------------------------------------------------------------
@dataclass
class TierSpec:
    """一个梯度档位的执行规格。

    base_size_pct 是"账户可用资金"的百分比上限，最终仓位还要乘温度系数与
    先手衰减系数；两者都由引擎计算，不在这里写死。
    """

    tier: int
    name: str
    base_size_pct: float
    entry_mode: str
    stop_anchor: str
    expire_min: int
    split: List[float] = field(default_factory=list)   # 分批比例，空=一次性
    max_bias_pct: float = 99.0                          # 允许的最大偏离均价
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "name": self.name,
            "base_size_pct": self.base_size_pct,
            "entry_mode": self.entry_mode,
            "stop_anchor": self.stop_anchor,
            "expire_min": self.expire_min,
            "split": list(self.split),
            "max_bias_pct": self.max_bias_pct,
            "note": self.note,
        }


@dataclass
class FusionDecision:
    """融合层唯一出口。一个标的同一时刻只有一条。"""

    code: str
    ts: float
    tier: int = 0
    tier_name: str = "L0 观察"
    rar: float = 0.0
    axes: AxisScores = field(default_factory=AxisScores)
    veto_reason: str = ""

    size_pct: float = 0.0
    temp_coef: float = 0.0
    age_coef: float = 0.0
    age_min: float = 0.0

    entry: Dict[str, Any] = field(default_factory=dict)
    stop: Dict[str, Any] = field(default_factory=dict)
    targets: List[Dict[str, Any]] = field(default_factory=list)
    invalidate: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    sources: List[str] = field(default_factory=list)
    decision_id: str = ""
    regime_stage: str = ""
    flip_state: str = ""

    @property
    def actionable(self) -> bool:
        return self.tier >= 1 and not self.veto_reason

    def one_line(self) -> str:
        """单行播报：一眼能看出"几级、多大仓、在哪进、错在哪出"。"""
        if self.veto_reason:
            return "L0 观察 {code} | 否决: {r}".format(code=self.code, r=self.veto_reason)
        if self.tier == 0:
            return "L0 观察 {code} | RAR {rar:.1f} 不足，仅记录".format(
                code=self.code, rar=self.rar
            )
        entry = self.entry or {}
        stop = self.stop or {}
        band = ""
        if entry.get("price_lo") and entry.get("price_hi"):
            band = "{lo:.2f}~{hi:.2f}".format(lo=entry["price_lo"], hi=entry["price_hi"])
        return (
            "{name} {code} | RAR {rar:.1f} (位{pos:.0f}/接{sup:.0f}/意{itn:.0f}/环{reg:.0f}) | "
            "仓{size:.0f}% (温{temp:.2f}×先{age:.2f}) | 进:{mode} {band} {exp}min内 | "
            "止{stop:.2f}({stop_pct:+.1f}%) | 失效:{inv}"
        ).format(
            name=self.tier_name,
            code=self.code,
            rar=self.rar,
            pos=self.axes.position,
            sup=self.axes.support,
            itn=self.axes.intent,
            reg=self.axes.regime,
            size=self.size_pct,
            temp=self.temp_coef,
            age=self.age_coef,
            mode=entry.get("mode", ""),
            band=band,
            exp=entry.get("expire_min", 0),
            stop=stop.get("price", 0.0),
            stop_pct=stop.get("pct", 0.0),
            inv="/".join(self.invalidate[:2]) if self.invalidate else "-",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "ts": self.ts,
            "tier": self.tier,
            "tier_name": self.tier_name,
            "rar": round(self.rar, 2),
            "axes": self.axes.to_dict(),
            "veto_reason": self.veto_reason,
            "size_pct": round(self.size_pct, 2),
            "temp_coef": round(self.temp_coef, 3),
            "age_coef": round(self.age_coef, 3),
            "age_min": round(self.age_min, 1),
            "entry": dict(self.entry),
            "stop": dict(self.stop),
            "targets": list(self.targets),
            "invalidate": list(self.invalidate),
            "evidence": list(self.evidence),
            "sources": list(self.sources),
            "decision_id": self.decision_id,
            "regime_stage": self.regime_stage,
            "flip_state": self.flip_state,
        }

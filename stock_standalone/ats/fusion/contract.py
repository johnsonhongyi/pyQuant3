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

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from safe_copy import safe_deepcopy
except Exception:
    def safe_deepcopy(x: Any) -> Any:
        return copy.deepcopy(x)


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
    vwap_10d: float = 0.0        # 10 日累计 VWAP（盘前 ma10dcum），压力区
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

    # 跨日结构（截至昨日，避免未来函数）
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ret5d: float = 0.0
    ret10d: float = 0.0
    ret20d: float = 0.0
    days_since_high: float = 0.0
    limit_up_streak: float = 0.0
    dist_ma20_pct: float = 0.0

    # 相对强度（逆势异动）
    rs5: float = 0.0          # 近 5 根 bar 相对全池的超额收益 %
    rs_day: float = 0.0       # 当日相对全池的超额收益 %

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
            "vwap_10d": self.vwap_10d,
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
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "ret5d": self.ret5d,
            "ret10d": self.ret10d,
            "ret20d": self.ret20d,
            "days_since_high": self.days_since_high,
            "limit_up_streak": self.limit_up_streak,
            "dist_ma20_pct": self.dist_ma20_pct,
            "rs5": self.rs5,
            "rs_day": self.rs_day,
            "launch_ts": self.launch_ts,
            "freshness_s": self.freshness_s,
            "trade_date": self.trade_date,
            "extra": safe_deepcopy(self.extra) if self.extra else {},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SignalEvent:
        if not d:
            return cls(code="", ts=0.0)
        extra_val = d.get("extra")
        extra_clean = safe_deepcopy(extra_val) if isinstance(extra_val, dict) else {}
        return cls(
            code=str(d.get("code") or ""),
            ts=float(d.get("ts") or 0.0),
            source=str(d.get("source") or ""),
            price=float(d.get("price") or 0.0),
            vwap=float(d.get("vwap") or 0.0),
            vwap_5d=float(d.get("vwap_5d") or 0.0),
            vwap_10d=float(d.get("vwap_10d") or 0.0),
            sbc_supp=float(d.get("sbc_supp") or 0.0),
            sbc_rev=float(d.get("sbc_rev") or 0.0),
            base_support=float(d.get("base_support") or 0.0),
            resistance=float(d.get("resistance") or 0.0),
            day_high=float(d.get("day_high") or 0.0),
            day_low=float(d.get("day_low") or 0.0),
            pct=float(d.get("pct") or 0.0),
            vol_ratio=float(d.get("vol_ratio") or 1.0),
            turnover=float(d.get("turnover") or 0.0),
            amount_wan=float(d.get("amount_wan") or 0.0),
            taker_buy_ratio=float(d.get("taker_buy_ratio") or 50.0),
            bid_pressure=float(d.get("bid_pressure") or 50.0),
            structure_clarity=float(d.get("structure_clarity") or 0.0),
            minutes_above_vwap=float(d.get("minutes_above_vwap") or 0.0),
            slope_score=float(d.get("slope_score") or 40.0),
            intent_score=float(d.get("intent_score") or 50.0),
            velocity_pct=float(d.get("velocity_pct") or 0.0),
            segment_vol_inc=float(d.get("segment_vol_inc") or 0.0),
            sector_resonance=float(d.get("sector_resonance") or 0.0),
            is_leader=bool(d.get("is_leader")),
            upper_score=float(d.get("upper_score") or 0.0),
            ma5=float(d.get("ma5") or 0.0),
            ma10=float(d.get("ma10") or 0.0),
            ma20=float(d.get("ma20") or 0.0),
            ret5d=float(d.get("ret5d") or 0.0),
            ret10d=float(d.get("ret10d") or 0.0),
            ret20d=float(d.get("ret20d") or 0.0),
            days_since_high=float(d.get("days_since_high") or 0.0),
            limit_up_streak=float(d.get("limit_up_streak") or 0.0),
            dist_ma20_pct=float(d.get("dist_ma20_pct") or 0.0),
            rs5=float(d.get("rs5") or 0.0),
            rs_day=float(d.get("rs_day") or 0.0),
            launch_ts=float(d.get("launch_ts") or 0.0),
            freshness_s=float(d.get("freshness_s") or 0.0),
            trade_date=str(d.get("trade_date") or ""),
            extra=extra_clean,
        )


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
    relative: float = 50.0
    penalty: float = 0.0
    rar: float = 0.0   # risk-adjusted rank = 加权 - 惩罚

    def to_dict(self) -> Dict[str, float]:
        return {
            "position": round(self.position, 2),
            "support": round(self.support, 2),
            "intent": round(self.intent, 2),
            "regime": round(self.regime, 2),
            "relative": round(self.relative, 2),
            "penalty": round(self.penalty, 2),
            "rar": round(self.rar, 2),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> AxisScores:
        if not d:
            return cls()
        return cls(
            position=float(d.get("position") or 0.0),
            support=float(d.get("support") or 0.0),
            intent=float(d.get("intent") or 0.0),
            regime=float(d.get("regime") or 0.0),
            relative=float(d.get("relative") if d.get("relative") is not None else 50.0),
            penalty=float(d.get("penalty") or 0.0),
            rar=float(d.get("rar") or 0.0),
        )


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

    # 数据可信度：coverage=参与加权的轴中"有真实数据"的权重占比 (0~1)。
    # 缺失字段不再按 0 分计入，而是从加权中剔除后归一，避免"缺数据=必死"。
    # provisional=True 表示本次结论建立在部分缺失数据上，只能作为观察依据。
    coverage: float = 0.0
    provisional: bool = False
    cuts: tuple = ()

    # 三层档位与决策分解
    score_tier: int = 0
    signal_tier: int = 0
    signal_size_pct: float = 0.0
    portfolio_tier: int = 0
    base_rar: float = 0.0
    adj_rar: float = 0.0
    floor_tier: int = 0
    floor_source: str = ""
    cap_tier: int = 4
    cap_reasons: List[str] = field(default_factory=list)

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
        cuts_list = []
        if self.cuts:
            for item in self.cuts:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    cuts_list.append([round(float(item[0]), 2), int(item[1])])
                else:
                    cuts_list.append(item)
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
            "coverage": round(self.coverage, 3),
            "provisional": bool(self.provisional),
            "score_tier": int(self.score_tier),
            "signal_tier": int(self.signal_tier),
            "signal_size_pct": round(float(self.signal_size_pct), 2),
            "portfolio_tier": int(self.portfolio_tier),
            "base_rar": round(float(self.base_rar), 2),
            "adj_rar": round(float(self.adj_rar), 2),
            "floor_tier": int(self.floor_tier),
            "floor_source": str(self.floor_source),
            "cap_tier": int(self.cap_tier),
            "cap_reasons": list(self.cap_reasons),
            "cuts": cuts_list,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> FusionDecision:
        if not d:
            return cls(code="", ts=0.0)
        axes_raw = d.get("axes")
        axes = AxisScores.from_dict(axes_raw) if isinstance(axes_raw, dict) else AxisScores()
        cuts_raw = d.get("cuts")
        cuts_tuple: tuple = ()
        if isinstance(cuts_raw, (list, tuple)):
            cuts_items = []
            for item in cuts_raw:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    cuts_items.append((float(item[0]), int(item[1])))
                else:
                    cuts_items.append(item)
            cuts_tuple = tuple(cuts_items)

        tier_val = int(d.get("tier") or 0)
        return cls(
            code=str(d.get("code") or ""),
            ts=float(d.get("ts") or 0.0),
            tier=tier_val,
            tier_name=str(d.get("tier_name") or "L0 观察"),
            rar=float(d.get("rar") or 0.0),
            axes=axes,
            veto_reason=str(d.get("veto_reason") or ""),
            size_pct=float(d.get("size_pct") or 0.0),
            temp_coef=float(d.get("temp_coef") or 0.0),
            age_coef=float(d.get("age_coef") or 0.0),
            age_min=float(d.get("age_min") or 0.0),
            entry=dict(d.get("entry") or {}),
            stop=dict(d.get("stop") or {}),
            targets=list(d.get("targets") or []),
            invalidate=list(d.get("invalidate") or []),
            evidence=list(d.get("evidence") or []),
            sources=list(d.get("sources") or []),
            decision_id=str(d.get("decision_id") or ""),
            regime_stage=str(d.get("regime_stage") or ""),
            flip_state=str(d.get("flip_state") or ""),
            coverage=float(d.get("coverage") or 0.0),
            provisional=bool(d.get("provisional")),
            cuts=cuts_tuple,
            score_tier=int(d.get("score_tier") if d.get("score_tier") is not None else tier_val),
            signal_tier=int(d.get("signal_tier") if d.get("signal_tier") is not None else tier_val),
            signal_size_pct=float(d.get("signal_size_pct") if d.get("signal_size_pct") is not None else d.get("size_pct", 0.0)),
            portfolio_tier=int(d.get("portfolio_tier") if d.get("portfolio_tier") is not None else tier_val),
            base_rar=float(d.get("base_rar") if d.get("base_rar") is not None else d.get("rar", 0.0)),
            adj_rar=float(d.get("adj_rar") if d.get("adj_rar") is not None else d.get("rar", 0.0)),
            floor_tier=int(d.get("floor_tier") or 0),
            floor_source=str(d.get("floor_source") or ""),
            cap_tier=int(d.get("cap_tier") if d.get("cap_tier") is not None else 4),
            cap_reasons=list(d.get("cap_reasons") or []),
        )

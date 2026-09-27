"""T+1 carry assessment with fail-closed pseudo-strength checks (Gate 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Optional

from ats.strategy.ipo_live_heat_engine import IPOLiveHeatSnapshot
from ats.strategy.ipo_regime_fsm import IPORegimeSnapshot, IPORegimeState
from ats.strategy.lrrm_engine import LRRMSnapshot


class T1CarryState(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class T1CarryResult:
    score: float = 0.0
    state: str = "BLOCK"
    positive_factors: List[str] = field(default_factory=list)
    negative_factors: List[str] = field(default_factory=list)
    nonlinear_zone: str = "UNKNOWN"
    overheat_score: float = 0.0
    exhaustion_risk: float = 0.0
    is_pseudo_strength_blocked: bool = False
    veto_reason: str = "DATA_NOT_READY"
    data_ready: bool = False


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class T1CarryEvaluator:
    ALLOW_THRESHOLD = 65.0
    CAUTION_THRESHOLD = 40.0

    @staticmethod
    def _blocked(reason: str, detail: str, live_heat: Optional[IPOLiveHeatSnapshot]) -> T1CarryResult:
        return T1CarryResult(
            negative_factors=[detail],
            nonlinear_zone=(live_heat.nonlinear_zone if live_heat is not None else "UNKNOWN"),
            overheat_score=(live_heat.overheat_score if live_heat is not None else 0.0),
            exhaustion_risk=(live_heat.exhaustion_risk if live_heat is not None else 0.0),
            veto_reason=reason,
        )

    def evaluate(
        self,
        code: str,
        live_heat: IPOLiveHeatSnapshot,
        ipo_regime: Optional[IPORegimeSnapshot] = None,
        lrrm: Optional[LRRMSnapshot] = None,
    ) -> T1CarryResult:
        if not isinstance(code, str) or not code.strip():
            return self._blocked("CODE_MISSING", "缺少标的代码", live_heat)
        if not isinstance(live_heat, IPOLiveHeatSnapshot) or live_heat.data_ready is not True:
            return self._blocked("LIVE_HEAT_NOT_READY", "盘中热度数据未就绪", None)
        if live_heat.code != code:
            return self._blocked("LIVE_HEAT_CODE_MISMATCH", "盘中热度标的与评估标的不一致", live_heat)
        values = (
            live_heat.turnover_pct,
            live_heat.minutes_above_vwap_ratio,
            live_heat.close_location,
            live_heat.pullback_from_peak_pct,
            live_heat.heat_score,
            live_heat.overheat_score,
            live_heat.exhaustion_risk,
        )
        if any(not _finite(value) for value in values):
            return self._blocked(
                "INCOMPLETE_LIVE_HEAT_METRICS", "伪强判据所需指标缺失或无效", live_heat
            )
        if (
            live_heat.turnover_pct < 0
            or not 0.0 <= live_heat.minutes_above_vwap_ratio <= 1.0
            or not 0.0 <= live_heat.close_location <= 1.0
            or live_heat.pullback_from_peak_pct < 0
            or any(not 0 <= value <= 100 for value in (
                live_heat.heat_score, live_heat.overheat_score, live_heat.exhaustion_risk
            ))
            or (
                live_heat.turnover_climb_speed is not None
                and (not _finite(live_heat.turnover_climb_speed) or live_heat.turnover_climb_speed < 0)
            )
        ):
            return self._blocked("INVALID_LIVE_HEAT_METRICS", "分时指标超出物理范围", live_heat)
        if (
            live_heat.nonlinear_zone not in {"NORMAL", "HOT", "EXTREME"}
            or not isinstance(live_heat.is_overheated_veto, bool)
        ):
            return self._blocked("LIVE_HEAT_STATE_INVALID", "过热区间状态无效", live_heat)

        cond1_above_vwap = live_heat.minutes_above_vwap_ratio >= 0.70
        cond2_turnover = (
            (live_heat.turnover_climb_speed is not None and live_heat.turnover_climb_speed >= 0.8)
            or live_heat.turnover_pct >= 75.0
        )
        cond3_weak_close = live_heat.close_location <= 0.40
        cond4_deep_pullback = live_heat.pullback_from_peak_pct >= 25.0
        is_pseudo = cond1_above_vwap and cond2_turnover and cond3_weak_close and cond4_deep_pullback
        if is_pseudo:
            return T1CarryResult(
                score=0.0,
                state=T1CarryState.BLOCK.value,
                negative_factors=[
                    "命中华大海天伪强结构(表面在线上+天量松动+弱收盘+高位大跳水)"
                ],
                nonlinear_zone=live_heat.nonlinear_zone,
                overheat_score=live_heat.overheat_score,
                exhaustion_risk=live_heat.exhaustion_risk,
                is_pseudo_strength_blocked=True,
                veto_reason="HUA_DA_HAI_TIAN_PSEUDO_STRENGTH_VETO",
                data_ready=True,
            )

        if not isinstance(ipo_regime, IPORegimeSnapshot) or ipo_regime.data_ready is not True:
            return self._blocked("IPO_REGIME_NOT_READY", "新股 Regime 数据未就绪", live_heat)
        if ipo_regime.state not in {
            state.value for state in IPORegimeState if state != IPORegimeState.UNKNOWN
        }:
            return self._blocked("IPO_REGIME_STATE_INVALID", "IPO Regime 状态无效", live_heat)
        if not isinstance(lrrm, LRRMSnapshot) or lrrm.data_ready is not True:
            return self._blocked("LRRM_NOT_READY", "宏观流动性数据未就绪", live_heat)
        if lrrm.liquidity_regime not in {"LOOSE", "NORMAL", "TIGHT", "SHOCK"}:
            return self._blocked("LRRM_STATE_INVALID", "LRRM 状态无效", live_heat)
        positive: List[str] = []
        negative: List[str] = []
        score = live_heat.heat_score - live_heat.overheat_score * 0.8 - live_heat.exhaustion_risk * 0.5
        if ipo_regime.state == "CONTINUATION":
            score += 10.0
            positive.append("IPO Regime 处于 CONTINUATION 主升期 (+10)")
        elif ipo_regime.state == "REPAIR":
            score += 5.0
            positive.append("IPO Regime 处于 REPAIR 修复期 (+5)")
        elif ipo_regime.state == "EXHAUSTION":
            score -= 25.0
            negative.append("IPO Regime 动能衰竭 (-25)")
        elif ipo_regime.state == "DISTRIBUTION":
            score -= 15.0
            negative.append("IPO Regime 处于 DISTRIBUTION 派发期 (-15)")
        if lrrm.liquidity_regime in {"TIGHT", "SHOCK"}:
            score -= 15.0
            negative.append("大盘流动性收紧 (-15)")
        score = max(0.0, min(100.0, score))

        if is_pseudo:
            state, veto = T1CarryState.BLOCK, "HUA_DA_HAI_TIAN_PSEUDO_STRENGTH_VETO"
        elif live_heat.is_overheated_veto:
            state, veto = T1CarryState.BLOCK, "LIVE_HEAT_EXTREME_OVERHEAT_VETO"
        elif ipo_regime.state == "EXHAUSTION":
            state, veto = T1CarryState.BLOCK, "IPO_REGIME_EXHAUSTION_VETO"
        elif score >= self.ALLOW_THRESHOLD and live_heat.nonlinear_zone != "EXTREME":
            state, veto = T1CarryState.ALLOW, ""
            positive.append(f"T1 Carry 综合评分达标({score:.1f} >= {self.ALLOW_THRESHOLD:.1f})")
        elif score >= self.CAUTION_THRESHOLD:
            state, veto = T1CarryState.CAUTION, ""
            negative.append("T1 Carry 处于谨慎观察区，严禁直接买入放行")
        else:
            state, veto = T1CarryState.BLOCK, f"SCORE_BELOW_THRESHOLD ({score:.1f} < {self.CAUTION_THRESHOLD:.1f})"

        return T1CarryResult(
            score=round(score, 1),
            state=state.value,
            positive_factors=positive,
            negative_factors=negative,
            nonlinear_zone=live_heat.nonlinear_zone,
            overheat_score=live_heat.overheat_score,
            exhaustion_risk=live_heat.exhaustion_risk,
            is_pseudo_strength_blocked=is_pseudo,
            veto_reason=veto,
            data_ready=True,
        )

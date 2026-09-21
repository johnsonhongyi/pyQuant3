# -*- coding: utf-8 -*-
"""Online, point-in-time tide state machine for IPO and subnew-stock breadth."""

from dataclasses import dataclass, field
from datetime import datetime
import math
import statistics
from typing import Iterable, List, Optional, Any


@dataclass(frozen=True)
class TideObservation:
    observed_at: str
    sample_count: int
    completeness: float
    advance_ratio: float
    above_vwap_ratio: float
    median_return_pct: float
    amount_yi: float
    top20_return_pct: float
    bottom20_return_pct: float


@dataclass
class TideDecision:
    observed_at: str
    state: str
    confidence: float
    position_cap_pct: float
    allow_probe: bool
    requires_price_confirmation: bool
    target_action: str
    transition_reasons: List[str] = field(default_factory=list)
    revision_count: int = 0


def build_tide_observation(
    signals,
    observed_at: str,
    expected_count: Optional[int] = None,
) -> TideObservation:
    """Build one cross-section from already computed in-memory stock signals."""
    valid = [signal for signal in signals if signal is not None and float(getattr(signal, "price", 0.0) or 0.0) > 0]
    changes = [float(getattr(signal, "change_pct", 0.0) or 0.0) for signal in valid]
    sample_count = len(valid)
    denominator = max(sample_count, int(expected_count or sample_count or 1))
    completeness = sample_count / denominator
    quintile_count = max(1, int(math.ceil(sample_count * 0.2))) if sample_count else 1

    amounts = []
    for signal in valid:
        extra = getattr(signal, "extra_data", {})
        extra = extra if isinstance(extra, dict) else {}
        amount = getattr(signal, "amount", 0.0) or extra.get("amount", 0.0) or extra.get("turnover_amount", 0.0)
        amounts.append(max(0.0, float(amount or 0.0)))

    ordered = sorted(changes)
    return TideObservation(
        observed_at=observed_at,
        sample_count=sample_count,
        completeness=round(completeness, 4),
        advance_ratio=(sum(change > 0 for change in changes) / sample_count) if sample_count else 0.0,
        above_vwap_ratio=(sum(bool(getattr(signal, "is_above_vwap", False)) for signal in valid) / sample_count) if sample_count else 0.0,
        median_return_pct=statistics.median(changes) if changes else 0.0,
        amount_yi=sum(amounts) / 100000000.0,
        top20_return_pct=statistics.mean(ordered[-quintile_count:]) if ordered else 0.0,
        bottom20_return_pct=statistics.mean(ordered[:quintile_count]) if ordered else 0.0,
    )


_POLICY = {
    "T0_INSUFFICIENT": (0.0, False, "WAIT"),
    "T1_CLIMAX_DISTRIBUTION": (0.0, False, "EXIT_RISK"),
    "T2_EBB_EARLY": (10.0, False, "REDUCE"),
    "T3_EBB_SPREAD": (5.0, False, "DEFEND"),
    "T4_PANIC_ACCEL": (0.0, False, "WAIT_FOR_DIVERGENCE"),
    "T5_ICE": (5.0, True, "PROBE_ONLY"),
    "T6_ICE_DIVERGENCE": (15.0, True, "PROBE_LEADERS"),
    "T7_WEAK_REPAIR": (25.0, True, "HOLD_PROBES"),
    "T8_REFLOW_CONFIRM": (40.0, True, "ROTATE_TO_LEADERS"),
    "T9_FLOOD_SPREAD": (70.0, True, "EXPAND"),
    "T10_MAIN_UP": (80.0, True, "HOLD_LEADERS"),
    "T11_OVERHEATED": (15.0, False, "TAKE_PROFIT"),
}

_DIRECTION = {
    "T0_INSUFFICIENT": 0,
    "T1_CLIMAX_DISTRIBUTION": -1,
    "T2_EBB_EARLY": -1,
    "T3_EBB_SPREAD": -1,
    "T4_PANIC_ACCEL": -1,
    "T5_ICE": 0,
    "T6_ICE_DIVERGENCE": 1,
    "T7_WEAK_REPAIR": 1,
    "T8_REFLOW_CONFIRM": 1,
    "T9_FLOOD_SPREAD": 1,
    "T10_MAIN_UP": 1,
    "T11_OVERHEATED": -1,
}


class SubnewTideStateMachine:
    """Classify each observation using only current and previously seen records."""

    def __init__(self, config: Optional[Any] = None):
        self._config = config
        self._previous_observation: Optional[TideObservation] = None
        self._previous_decision: Optional[TideDecision] = None
        self._last_timestamp: Optional[datetime] = None
        self._revision_count = 0
        self._session_date = None
        self._session_base_observation: Optional[TideObservation] = None
        self._session_base_decision: Optional[TideDecision] = None
        self._session_base_revision_count = 0

    def reset(self) -> None:
        self.__init__(config=self._config)

    def replay(self, observations: Iterable[TideObservation]) -> List[TideDecision]:
        self.reset()
        return [self.update(observation) for observation in observations]

    def update(self, observation: TideObservation) -> TideDecision:
        timestamp = datetime.fromisoformat(observation.observed_at)
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("observations must be strictly increasing")

        session_date = timestamp.date()
        if self._session_date != session_date:
            self._session_date = session_date
            self._session_base_observation = self._previous_observation
            self._session_base_decision = self._previous_decision
            self._session_base_revision_count = self._revision_count
        else:
            # Re-evaluate the live session against the last finalized session.
            # This prevents 3-second refreshes from masquerading as new days.
            self._previous_observation = self._session_base_observation
            self._previous_decision = self._session_base_decision
            self._revision_count = self._session_base_revision_count

        state, reasons = self._classify(observation, self._previous_observation)
        previous_state = self._previous_decision.state if self._previous_decision else None
        if previous_state:
            previous_direction = _DIRECTION[previous_state]
            current_direction = _DIRECTION[state]
            if previous_direction and current_direction and previous_direction != current_direction:
                self._revision_count += 1
                if previous_direction > 0:
                    reasons.append("failed_follow_through")
                else:
                    reasons.append("risk_recovery_confirmed")

        cap, allow_probe, action = _POLICY[state]
        confidence = self._confidence(observation, state)
        decision = TideDecision(
            observed_at=observation.observed_at,
            state=state,
            confidence=confidence,
            position_cap_pct=cap,
            allow_probe=allow_probe,
            requires_price_confirmation=allow_probe,
            target_action=action,
            transition_reasons=reasons,
            revision_count=self._revision_count,
        )
        self._previous_observation = observation
        self._previous_decision = decision
        self._last_timestamp = timestamp
        return decision

    def _classify(
        self,
        current: TideObservation,
        previous: Optional[TideObservation],
    ):
        cfg = self._config
        min_samples = getattr(cfg, "min_sample_count", 10) if cfg else 10
        min_comp = getattr(cfg, "min_completeness", 0.8) if cfg else 0.8

        if current.sample_count < min_samples or current.completeness < min_comp:
            return "T0_INSUFFICIENT", ["insufficient_cross_section"]

        t2_adv_collapse = getattr(cfg, "t2_advance_ratio_collapse", 0.30) if cfg else 0.30
        t2_vwap_collapse = getattr(cfg, "t2_above_vwap_ratio_collapse", 0.20) if cfg else 0.20

        prior_state = self._previous_decision.state if self._previous_decision else ""
        if (prior_state in ("T9_FLOOD_SPREAD", "T10_MAIN_UP")
                and current.advance_ratio < t2_adv_collapse and current.above_vwap_ratio < t2_vwap_collapse):
            return "T2_EBB_EARLY", ["breadth_collapse", "vwap_support_lost"]

        if previous is not None:
            amount_ratio = current.amount_yi / previous.amount_yi if previous.amount_yi > 0 else 1.0

            # A mature advance must persist beyond one broad-up session before it
            # earns the larger T10 allocation.  This deliberately sits below T11
            # so an extreme blow-off is still classified as over-heated.
            t10_adv_min = getattr(cfg, "t10_advance_ratio_min", 0.75) if cfg else 0.75
            t10_vwap_min = getattr(cfg, "t10_above_vwap_ratio_min", 0.70) if cfg else 0.70
            t10_med_min = getattr(cfg, "t10_median_return_min", 2.0) if cfg else 2.0
            t10_med_max = getattr(cfg, "t10_median_return_max", 5.0) if cfg else 5.0
            t10_top_min = getattr(cfg, "t10_top20_return_min", 6.0) if cfg else 6.0
            t10_amt_min = getattr(cfg, "t10_amount_ratio_min", 0.90) if cfg else 0.90

            if (prior_state in ("T9_FLOOD_SPREAD", "T10_MAIN_UP")
                    and current.advance_ratio >= t10_adv_min
                    and current.above_vwap_ratio >= t10_vwap_min
                    and t10_med_min <= current.median_return_pct < t10_med_max
                    and current.top20_return_pct >= t10_top_min
                    and amount_ratio >= t10_amt_min):
                return "T10_MAIN_UP", [
                    "broad_advance_persisted",
                    "leader_strength_persisted",
                    "turnover_held",
                ]

            # After a broad advance, turnover expansion accompanied by fading
            # breadth/VWAP acceptance is distribution, not a normal pullback.
            # A deeper collapse remains T2 via the hard guard above.
            t1_adv_max = getattr(cfg, "t1_advance_ratio_max", 0.55) if cfg else 0.55
            t1_vwap_max = getattr(cfg, "t1_above_vwap_ratio_max", 0.50) if cfg else 0.50
            t1_med_max = getattr(cfg, "t1_median_return_max", 1.0) if cfg else 1.0
            t1_top_min = getattr(cfg, "t1_top20_return_min", 3.0) if cfg else 3.0
            t1_amt_min = getattr(cfg, "t1_amount_ratio_min", 1.20) if cfg else 1.20

            if (prior_state in ("T9_FLOOD_SPREAD", "T10_MAIN_UP", "T11_OVERHEATED")
                    and current.advance_ratio <= t1_adv_max
                    and current.above_vwap_ratio <= t1_vwap_max
                    and current.median_return_pct <= t1_med_max
                    and current.top20_return_pct >= t1_top_min
                    and amount_ratio >= t1_amt_min):
                return "T1_CLIMAX_DISTRIBUTION", [
                    "high_turnover_distribution",
                    "breadth_faded_after_advance",
                    "vwap_acceptance_lost",
                ]

        t11_adv_min = getattr(cfg, "t11_advance_ratio_min", 0.90) if cfg else 0.90
        t11_med_min = getattr(cfg, "t11_median_return_min", 5.0) if cfg else 5.0
        if current.advance_ratio >= t11_adv_min and current.median_return_pct >= t11_med_min:
            return "T11_OVERHEATED", ["extreme_breadth", "extreme_median_return"]

        t9_adv_min = getattr(cfg, "t9_advance_ratio_min", 0.75) if cfg else 0.75
        t9_vwap_min = getattr(cfg, "t9_above_vwap_ratio_min", 0.70) if cfg else 0.70
        if current.advance_ratio >= t9_adv_min and current.above_vwap_ratio >= t9_vwap_min:
            return "T9_FLOOD_SPREAD", ["broad_advance", "broad_vwap_acceptance"]

        if (prior_state in ("T1_CLIMAX_DISTRIBUTION", "T2_EBB_EARLY", "T3_EBB_SPREAD", "T4_PANIC_ACCEL", "T5_ICE", "T6_ICE_DIVERGENCE")
                and current.advance_ratio >= 0.55 and current.above_vwap_ratio >= 0.65
                and current.median_return_pct > 0):
            return "T8_REFLOW_CONFIRM", ["breadth_recovered", "vwap_reclaimed"]

        if previous is not None:
            vwap_improvement = current.above_vwap_ratio - previous.above_vwap_ratio
            if (current.median_return_pct < -1.5 and amount_ratio >= 1.35
                    and vwap_improvement >= 0.15 and current.top20_return_pct >= 6.0):
                return "T6_ICE_DIVERGENCE", [
                    "volume_returned_before_breadth",
                    "leader_resilience",
                    "vwap_acceptance_improved",
                ]

        t4_adv_max = getattr(cfg, "t4_advance_ratio_max", 0.20) if cfg else 0.20
        t4_med_max = getattr(cfg, "t4_median_return_max", -2.20) if cfg else -2.20
        if current.advance_ratio <= t4_adv_max and current.median_return_pct <= t4_med_max:
            return "T4_PANIC_ACCEL", ["breadth_panic", "median_loss_accelerating"]

        t5_vwap_max = getattr(cfg, "t5_above_vwap_ratio_max", 0.15) if cfg else 0.15
        t5_adv_max = getattr(cfg, "t5_advance_ratio_max", 0.25) if cfg else 0.25
        if current.above_vwap_ratio <= t5_vwap_max and current.advance_ratio <= t5_adv_max:
            return "T5_ICE", ["vwap_acceptance_floor", "selling_pressure_decelerating"]

        t3_adv_max = getattr(cfg, "t3_advance_ratio_max", 0.25) if cfg else 0.25
        t3_med_max = getattr(cfg, "t3_median_return_max", -1.50) if cfg else -1.50
        if current.advance_ratio <= t3_adv_max and current.median_return_pct <= t3_med_max:
            return "T3_EBB_SPREAD", ["weak_breadth", "losses_spreading"]

        t7_adv_min = getattr(cfg, "t7_advance_ratio_min", 0.55) if cfg else 0.55
        t7_vwap_min = getattr(cfg, "t7_above_vwap_ratio_min", 0.55) if cfg else 0.55
        if current.advance_ratio >= t7_adv_min and current.above_vwap_ratio >= t7_vwap_min:
            return "T7_WEAK_REPAIR", ["breadth_repair", "vwap_repair"]
        return "T2_EBB_EARLY", ["mixed_or_deteriorating_structure"]

    @staticmethod
    def _confidence(observation: TideObservation, state: str) -> float:
        sample_score = min(1.0, observation.sample_count / 25.0)
        completeness = max(0.0, min(1.0, observation.completeness))
        structural = 0.9 if state not in ("T0_INSUFFICIENT", "T2_EBB_EARLY") else 0.65
        return round(sample_score * completeness * structural, 3)

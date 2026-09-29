"""Fail-closed liquidity and risk-regime manager (Gate 0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo


class LiquidityRegime(str, Enum):
    LOOSE = "LOOSE"
    NORMAL = "NORMAL"
    TIGHT = "TIGHT"
    SHOCK = "SHOCK"
    UNKNOWN = "UNKNOWN"


class RiskAppetite(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


@dataclass(frozen=True)
class LRRMSnapshot:
    liquidity_regime: str = "UNKNOWN"
    risk_appetite: str = "RISK_OFF"
    concentration_state: str = "UNKNOWN"
    liquidity_confidence: float = 0.0
    transition_reason: str = "数据未就绪"
    market_amount_yi: float = 0.0
    amount_20d_percentile: float = 0.0
    advance_decline_ratio: float = 0.0
    limit_down_count: int = 0
    generated_at: str = ""
    data_ready: bool = False
    missing_inputs: List[str] = field(default_factory=list)


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _aware_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        value = datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    try:
        if value.utcoffset() is None:
            return None
        return value.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
    except (OverflowError, OSError, TypeError, ValueError):
        return None


class LRRMEngine:
    """Classify liquidity only after every configured source is healthy."""

    def __init__(self, required_inputs: Sequence[str]) -> None:
        if (
            not isinstance(required_inputs, (list, tuple))
            or not required_inputs
            or any(not isinstance(name, str) or not name.strip() for name in required_inputs)
            or len(required_inputs) != len(set(required_inputs))
        ):
            raise ValueError("LRRM required_inputs 必须为唯一且非空的字段列表")
        self.required_inputs = tuple(required_inputs)

    def evaluate(
        self,
        market_amount_yi: float,
        amount_history_20d: List[float],
        up_count: int,
        down_count: int,
        limit_up_count: int,
        limit_down_count: int,
        required_input_health: Dict[str, bool],
        fsm_state: Optional[str] = None,
        *,
        as_of: Optional[datetime] = None,
    ) -> LRRMSnapshot:
        generated_at = _aware_iso(as_of)
        missing: List[str] = []
        if generated_at is None:
            missing.append("evaluation_time")
        if not isinstance(required_input_health, Mapping):
            missing.append("required_input_health")
        else:
            missing.extend(
                name for name in self.required_inputs
                if required_input_health.get(name) is not True
            )
        if not isinstance(amount_history_20d, (list, tuple)) or len(amount_history_20d) < 20:
            missing.append("amount_history_20d(<20)")
        elif any(not _finite_number(value) or value <= 0 for value in amount_history_20d):
            missing.append("amount_history_20d_invalid")
        if not _finite_number(market_amount_yi) or market_amount_yi <= 0:
            missing.append("market_amount_yi")
        for name, value in (
            ("up_count", up_count),
            ("down_count", down_count),
            ("limit_up_count", limit_up_count),
            ("limit_down_count", limit_down_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                missing.append(name)
        if isinstance(up_count, int) and isinstance(down_count, int) and up_count + down_count <= 0:
            missing.append("breadth_counts_empty")
        if missing:
            return LRRMSnapshot(
                generated_at=generated_at or "",
                transition_reason="LRRM 数据未就绪: " + ", ".join(sorted(set(missing))),
                missing_inputs=sorted(set(missing)),
            )

        rank = sum(1 for amount in amount_history_20d if amount <= market_amount_yi)
        percentile = rank / len(amount_history_20d) * 100.0
        breadth_ratio = up_count / (up_count + down_count)

        if percentile < 5.0 or limit_down_count >= 30 or (
            breadth_ratio < 0.20 and percentile < 15.0
        ):
            regime, appetite = LiquidityRegime.SHOCK, RiskAppetite.RISK_OFF
            reason = f"流动性休克熔断: 20日分位 {percentile:.1f}%, 跌停家数 {limit_down_count}"
        elif percentile < 20.0 or fsm_state == "PANIC":
            regime, appetite = LiquidityRegime.TIGHT, RiskAppetite.RISK_OFF
            reason = f"流动性紧缩: 20日分位 {percentile:.1f}%, 市场情绪 PANIC"
        elif percentile > 80.0 and breadth_ratio > 0.60:
            regime, appetite = LiquidityRegime.LOOSE, RiskAppetite.RISK_ON
            reason = f"流动性充裕宽松: 20日分位 {percentile:.1f}%, 涨跌比 {breadth_ratio:.2f}"
        else:
            regime, appetite = LiquidityRegime.NORMAL, RiskAppetite.NEUTRAL
            reason = "流动性平稳中性"

        return LRRMSnapshot(
            liquidity_regime=regime.value,
            risk_appetite=appetite.value,
            liquidity_confidence=85.0 if regime in {LiquidityRegime.SHOCK, LiquidityRegime.LOOSE} else 65.0,
            transition_reason=reason,
            market_amount_yi=float(market_amount_yi),
            amount_20d_percentile=percentile,
            advance_decline_ratio=breadth_ratio,
            limit_down_count=limit_down_count,
            generated_at=generated_at,
            data_ready=True,
        )

    def evaluate_contract_metrics(
        self,
        metrics: Mapping[str, Any],
        required_input_health: Mapping[str, bool],
        fsm_state: Optional[str] = None,
        *,
        as_of: Optional[datetime] = None,
    ) -> LRRMSnapshot:
        """Classify from source-contract aggregates when raw turnover history is unavailable."""
        generated_at = _aware_iso(as_of)
        missing: List[str] = []
        if generated_at is None:
            missing.append("evaluation_time")
        if not isinstance(metrics, Mapping):
            missing.append("metrics_invalid")
            metrics = {}
        if not isinstance(required_input_health, Mapping):
            missing.append("required_input_health")
        else:
            missing.extend(
                name for name in self.required_inputs
                if required_input_health.get(name) is not True
            )
        for name in self.required_inputs:
            if name not in metrics or not _finite_number(metrics.get(name)):
                missing.append(f"{name}_invalid")
        p20 = metrics.get("volume_percentile_20d")
        p60 = metrics.get("volume_percentile_60d")
        breadth = metrics.get("advance_decline_ratio")
        limit_down = metrics.get("limit_down_count")
        if _finite_number(p20) and not 0.0 <= p20 <= 1.0:
            missing.append("volume_percentile_20d_out_of_range")
        if _finite_number(p60) and not 0.0 <= p60 <= 1.0:
            missing.append("volume_percentile_60d_out_of_range")
        if _finite_number(breadth) and not 0.0 <= breadth <= 1.0:
            missing.append("advance_decline_ratio_out_of_range")
        if isinstance(limit_down, bool) or not isinstance(limit_down, int) or limit_down < 0:
            missing.append("limit_down_count_invalid")
        if missing:
            return LRRMSnapshot(
                generated_at=generated_at or "",
                transition_reason="LRRM 数据未就绪: " + ", ".join(sorted(set(missing))),
                missing_inputs=sorted(set(missing)),
            )

        percentile_20 = float(p20) * 100.0
        percentile_60 = float(p60) * 100.0
        if min(percentile_20, percentile_60) < 5.0 or limit_down >= 30 or (
            breadth < 0.20 and min(percentile_20, percentile_60) < 15.0
        ):
            regime, appetite = LiquidityRegime.SHOCK, RiskAppetite.RISK_OFF
            reason = (
                f"流动性休克熔断: 20/60日分位 {percentile_20:.1f}%/"
                f"{percentile_60:.1f}%, 跌停家数 {limit_down}"
            )
        elif min(percentile_20, percentile_60) < 20.0 or fsm_state == "PANIC":
            regime, appetite = LiquidityRegime.TIGHT, RiskAppetite.RISK_OFF
            reason = "流动性紧缩: 成交额分位或市场情绪触发收缩"
        elif min(percentile_20, percentile_60) > 80.0 and breadth > 0.60:
            regime, appetite = LiquidityRegime.LOOSE, RiskAppetite.RISK_ON
            reason = f"流动性充裕宽松: 20/60日分位均高且涨跌比 {breadth:.2f}"
        else:
            regime, appetite = LiquidityRegime.NORMAL, RiskAppetite.NEUTRAL
            reason = "流动性平稳中性: 基于契约校验后的20/60日分位与涨跌比"
        return LRRMSnapshot(
            liquidity_regime=regime.value,
            risk_appetite=appetite.value,
            liquidity_confidence=85.0 if regime in {LiquidityRegime.SHOCK, LiquidityRegime.LOOSE} else 65.0,
            transition_reason=reason,
            amount_20d_percentile=percentile_20,
            advance_decline_ratio=float(breadth),
            limit_down_count=limit_down,
            generated_at=generated_at or "",
            data_ready=True,
        )

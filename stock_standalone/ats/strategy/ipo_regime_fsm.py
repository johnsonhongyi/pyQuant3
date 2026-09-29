"""Fail-closed five-state IPO cross-section regime classifier (Gate 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from ats.strategy.lrrm_engine import LRRMSnapshot


class IPORegimeState(str, Enum):
    DISTRIBUTION = "DISTRIBUTION"
    REPAIR = "REPAIR"
    CONTINUATION = "CONTINUATION"
    MANIA = "MANIA"
    EXHAUSTION = "EXHAUSTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IPORegimeSnapshot:
    state: str = "UNKNOWN"
    confidence: float = 0.0
    trigger_factors: List[str] = field(default_factory=list)
    d1_positive_rate: float = 0.0
    first_day_peak_ratio: float = 0.0
    new_high_ratio: float = 0.0
    turnover_median: float = 0.0
    generated_at: str = ""
    data_ready: bool = False
    sample_count: int = 0
    missing_metrics: List[str] = field(default_factory=list)


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


class IPORegimeFSM:
    LOOKBACK_STOCKS = 10
    MIN_SAMPLE_COUNT = 5

    def __init__(self, required_metrics: Sequence[str]) -> None:
        if (
            not isinstance(required_metrics, (list, tuple))
            or not required_metrics
            or any(not isinstance(name, str) or not name.strip() for name in required_metrics)
            or len(required_metrics) != len(set(required_metrics))
        ):
            raise ValueError("IPO Regime required_metrics 必须为唯一且非空的字段列表")
        self.required_metrics = tuple(required_metrics)

    def update(
        self,
        recent_ipos: List[Dict[str, Any]],
        required_metric_health: Dict[str, bool],
        lrrm: Optional[LRRMSnapshot] = None,
        *,
        as_of: Optional[datetime] = None,
    ) -> IPORegimeSnapshot:
        generated_at = _aware_iso(as_of)
        missing: List[str] = []
        if generated_at is None:
            missing.append("evaluation_time")
        if not isinstance(required_metric_health, Mapping):
            missing.append("required_metric_health")
        else:
            missing.extend(
                name for name in self.required_metrics
                if required_metric_health.get(name) is not True
            )
        if not isinstance(recent_ipos, list):
            missing.append("recent_ipos_invalid")
            samples: List[Mapping[str, Any]] = []
        else:
            samples = recent_ipos[-self.LOOKBACK_STOCKS:]
        if len(samples) < self.MIN_SAMPLE_COUNT:
            missing.append(f"sample_count(<{self.MIN_SAMPLE_COUNT})")

        normalized = []
        for index, sample in enumerate(samples):
            if not isinstance(sample, Mapping):
                missing.append(f"sample_{index}_invalid")
                continue
            d1_return = sample.get("d1_return_pct")
            peak = sample.get("is_first_day_peak")
            new_high = sample.get("made_new_high")
            turnover = sample.get("first_day_turnover")
            if not _finite_number(d1_return):
                missing.append(f"sample_{index}_d1_return_invalid")
            if not isinstance(peak, bool):
                missing.append(f"sample_{index}_peak_flag_invalid")
            if not isinstance(new_high, bool):
                missing.append(f"sample_{index}_new_high_flag_invalid")
            if not _finite_number(turnover) or turnover < 0:
                missing.append(f"sample_{index}_turnover_invalid")
            if (
                _finite_number(d1_return) and isinstance(peak, bool)
                and isinstance(new_high, bool) and _finite_number(turnover)
                and turnover >= 0
            ):
                normalized.append((d1_return, peak, new_high, turnover))

        if lrrm is not None and not getattr(lrrm, "data_ready", False):
            missing.append("lrrm_not_ready")
        if missing:
            return IPORegimeSnapshot(
                generated_at=generated_at or "",
                trigger_factors=["Regime 数据未就绪: " + ", ".join(sorted(set(missing)))],
                sample_count=len(samples),
                missing_metrics=sorted(set(missing)),
            )

        n = len(normalized)
        d1_rate = sum(1 for row in normalized if row[0] > 0) / n
        peak_rate = sum(1 for row in normalized if row[1]) / n
        high_rate = sum(1 for row in normalized if row[2]) / n
        turnover_median = float(median(row[3] for row in normalized))
        factors: List[str] = []

        if lrrm is not None and lrrm.liquidity_regime == "SHOCK":
            state = IPORegimeState.DISTRIBUTION
            factors.append("大盘流动性休克，强制进入 DISTRIBUTION 杀跌期")
        elif peak_rate >= 0.40 and d1_rate < 0.40:
            state = IPORegimeState.EXHAUSTION
            factors.append(
                f"首日见顶率过高({peak_rate:.1%})，次日正收益率恶化({d1_rate:.1%})，进入 EXHAUSTION 衰竭期"
            )
        elif d1_rate >= 0.80 and turnover_median >= 65.0:
            state = IPORegimeState.MANIA
            factors.append(
                f"次日正收益率达 {d1_rate:.1%}，换手极高({turnover_median:.1f}%)，进入 MANIA 狂热高潮"
            )
        elif d1_rate >= 0.55 and high_rate >= 0.40:
            state = IPORegimeState.CONTINUATION
            factors.append(
                f"次日溢价稳定({d1_rate:.1%})，创新高比例达标({high_rate:.1%})，处于 CONTINUATION 主升接力期"
            )
        elif d1_rate >= 0.40:
            state = IPORegimeState.REPAIR
            factors.append(f"次日溢价企稳({d1_rate:.1%})，处于 REPAIR 修复初期")
        else:
            state = IPORegimeState.DISTRIBUTION
            factors.append(f"次日破发兑现率高({1.0 - d1_rate:.1%})，处于 DISTRIBUTION 派发退潮期")

        return IPORegimeSnapshot(
            state=state.value,
            confidence=80.0,
            trigger_factors=factors,
            d1_positive_rate=d1_rate,
            first_day_peak_ratio=peak_rate,
            new_high_ratio=high_rate,
            turnover_median=turnover_median,
            generated_at=generated_at or "",
            data_ready=True,
            sample_count=n,
        )

    def update_from_contract_metrics(
        self,
        metrics: Mapping[str, Any],
        required_metric_health: Mapping[str, bool],
        sample_count: int,
        cohort_id: str,
        thresholds: Mapping[str, Any],
        lrrm: Optional[LRRMSnapshot] = None,
        *,
        as_of: Optional[datetime] = None,
    ) -> IPORegimeSnapshot:
        """Build the typed regime snapshot from fresh, reviewed cohort aggregates."""
        generated_at = _aware_iso(as_of)
        missing: List[str] = []
        if generated_at is None:
            missing.append("evaluation_time")
        if not isinstance(metrics, Mapping):
            missing.append("metrics_invalid")
            metrics = {}
        if not isinstance(required_metric_health, Mapping):
            missing.append("required_metric_health")
        else:
            missing.extend(
                name for name in self.required_metrics
                if required_metric_health.get(name) is not True
            )
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < self.MIN_SAMPLE_COUNT:
            missing.append(f"sample_count(<{self.MIN_SAMPLE_COUNT})")
        if not isinstance(cohort_id, str) or not cohort_id.strip():
            missing.append("cohort_id_missing")
        normalized: Dict[str, float] = {}
        percent_fields = {
            "d1_positive_rate", "d1_top_rate", "d2_positive_rate", "d3_positive_rate",
            "limit_down_rate", "new_stock_innovation_high_rate",
        }
        for name in self.required_metrics:
            value = metrics.get(name)
            if not _finite_number(value):
                missing.append(f"{name}_invalid")
                continue
            normalized[name] = float(value)
        for name in percent_fields:
            value = normalized.get(name)
            if value is not None:
                if not 0.0 <= value <= 100.0:
                    missing.append(f"{name}_out_of_range")
                else:
                    normalized[name] = value / 100.0
        if "close_position" in normalized and not 0.0 <= normalized["close_position"] <= 1.0:
            missing.append("close_position_out_of_range")
        if "new_stock_turnover_median" in normalized and normalized["new_stock_turnover_median"] < 0:
            missing.append("new_stock_turnover_median_out_of_range")
        if "d1_d2_max_drawdown" in normalized and not -100.0 <= normalized["d1_d2_max_drawdown"] <= 0.0:
            missing.append("d1_d2_max_drawdown_out_of_range")
        if lrrm is not None and lrrm.data_ready is not True:
            missing.append("lrrm_not_ready")
        if not isinstance(thresholds, Mapping):
            missing.append("transition_thresholds_missing")
            thresholds = {}
        if missing:
            return IPORegimeSnapshot(
                generated_at=generated_at or "",
                trigger_factors=["Regime 数据未就绪: " + ", ".join(sorted(set(missing)))],
                sample_count=sample_count if isinstance(sample_count, int) and not isinstance(sample_count, bool) else 0,
                missing_metrics=sorted(set(missing)),
            )

        def threshold(section: str, key: str) -> Optional[float]:
            group = thresholds.get(section)
            value = group.get(key) if isinstance(group, Mapping) else None
            return float(value) if _finite_number(value) else None

        d1 = normalized["d1_positive_rate"]
        d1_top = normalized["d1_top_rate"]
        d2 = normalized["d2_positive_rate"]
        d3 = normalized["d3_positive_rate"]
        limit_down = normalized["limit_down_rate"]
        innovation_high = normalized["new_stock_innovation_high_rate"]
        turnover = normalized["new_stock_turnover_median"]
        d1_min = threshold("distribution_to_repair", "d1_positive_rate_min")
        limit_down_max = threshold("distribution_to_repair", "limit_down_rate_max")
        continuation_d1_min = threshold("repair_to_continuation", "d1_positive_rate_min")
        continuation_high_min = threshold("repair_to_continuation", "new_high_ratio_min")
        mania_d1_min = threshold("continuation_to_mania", "d1_positive_rate_min")
        mania_turnover = threshold("continuation_to_mania", "turnover_extreme_pct")
        exhaustion_top_min = threshold("mania_to_exhaustion", "first_day_peak_ratio_min")
        exhaustion_d1_max = threshold("exhaustion_to_distribution", "d1_positive_rate_max")
        if any(value is None for value in (
            d1_min, limit_down_max, continuation_d1_min, continuation_high_min,
            mania_d1_min, mania_turnover, exhaustion_top_min, exhaustion_d1_max,
        )):
            missing_thresholds = [
                name for name, value in (
                    ("distribution_to_repair", d1_min), ("limit_down_rate_max", limit_down_max),
                    ("repair_to_continuation", continuation_d1_min), ("new_high_ratio_min", continuation_high_min),
                    ("continuation_to_mania", mania_d1_min), ("turnover_extreme_pct", mania_turnover),
                    ("mania_to_exhaustion", exhaustion_top_min), ("exhaustion_to_distribution", exhaustion_d1_max),
                ) if value is None
            ]
            return IPORegimeSnapshot(
                generated_at=generated_at or "",
                trigger_factors=["Regime 配置阈值未就绪: " + ", ".join(missing_thresholds)],
                sample_count=sample_count,
                missing_metrics=missing_thresholds,
            )

        factors = [
            f"队列样本={sample_count} cohort={cohort_id}",
            f"D1/D2/D3正收益率={d1:.1%}/{d2:.1%}/{d3:.1%}",
            f"D1-D2最大回撤={normalized['d1_d2_max_drawdown']:.1f}%",
            f"新股相对强度={normalized['new_stock_relative_strength']:.1f}%",
            f"收盘位置={normalized['close_position']:.2f}",
        ]
        if lrrm is not None and lrrm.liquidity_regime == "SHOCK":
            state = IPORegimeState.DISTRIBUTION
            factors.insert(0, "大盘流动性休克，进入 DISTRIBUTION")
        elif d1_top >= exhaustion_top_min and d1 < d1_min:
            state = IPORegimeState.EXHAUSTION
            factors.insert(0, "首日高收益占比高且D1正收益率低，进入 EXHAUSTION")
        elif d1 >= mania_d1_min and turnover >= mania_turnover:
            state = IPORegimeState.MANIA
            factors.insert(0, "D1正收益率与新股换手达到狂热阈值，进入 MANIA")
        elif d1 >= continuation_d1_min and innovation_high >= continuation_high_min:
            state = IPORegimeState.CONTINUATION
            factors.insert(0, "D1正收益率与创新高占比达标，进入 CONTINUATION")
        elif d1 >= d1_min and limit_down <= limit_down_max:
            state = IPORegimeState.REPAIR
            factors.insert(0, "D1正收益率企稳且跌停样本受控，进入 REPAIR")
        else:
            state = IPORegimeState.DISTRIBUTION
            factors.insert(0, "D1收益或跌停比例未达到修复阈值，进入 DISTRIBUTION")
        return IPORegimeSnapshot(
            state=state.value, confidence=80.0, trigger_factors=factors,
            d1_positive_rate=d1, first_day_peak_ratio=d1_top,
            new_high_ratio=innovation_high, turnover_median=turnover,
            generated_at=generated_at or "", data_ready=True,
            sample_count=sample_count,
        )

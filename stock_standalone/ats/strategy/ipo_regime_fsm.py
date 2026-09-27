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

# -*- coding: utf-8 -*-
"""Point-in-time event sentiment for IPO and recently listed stocks."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable, List


_EVENT_WEIGHTS = {
    "IPO_PIPELINE": 0.70,
    "INSTITUTIONAL_DEMAND": 1.00,
    "FIRST_DAY_PROFIT_EFFECT": 1.00,
    "SECTOR_CATALYST": 0.85,
    "SUBSCRIPTION_HEAT": 0.80,
    "BREAK_RATE": 1.00,
    "REGULATORY_RISK": 1.20,
    "SUPPLY_PRESSURE": 0.90,
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).strip())


@dataclass(frozen=True)
class SubnewEvent:
    occurred_at: str
    event_type: str
    severity: float
    source: str
    summary: str


@dataclass
class SubnewEventSentimentSnapshot:
    as_of: str
    window_start: str
    stage: str
    event_score: float
    used_event_count: int
    event_types: List[str] = field(default_factory=list)
    evidence: List[dict] = field(default_factory=list)
    price_confirmation: bool = False
    watch_priority: str = "NORMAL"
    allow_buy: bool = False
    snapshot_id: str = ""

    def finalize(self) -> "SubnewEventSentimentSnapshot":
        payload = asdict(self)
        payload["snapshot_id"] = ""
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.snapshot_id = hashlib.sha256(raw).hexdigest()[:16]
        return self


class SubnewEventSentimentEngine:
    """Aggregate only information available at ``as_of``; never inspect future events."""

    def __init__(self, half_life_days: float = 15.0):
        self.half_life_days = max(1.0, float(half_life_days))

    def evaluate(
        self,
        events: Iterable[SubnewEvent],
        window_start: str,
        as_of: str,
        price_change_pct: float = 0.0,
    ) -> SubnewEventSentimentSnapshot:
        start_dt = _parse_time(window_start)
        as_of_dt = _parse_time(as_of)
        if start_dt > as_of_dt:
            raise ValueError("window_start must not be after as_of")

        weighted_score = 0.0
        evidence = []
        for event in events:
            occurred_dt = _parse_time(event.occurred_at)
            if occurred_dt < start_dt or occurred_dt > as_of_dt:
                continue
            event_type = str(event.event_type).strip().upper()
            type_weight = _EVENT_WEIGHTS.get(event_type, 0.5)
            severity = max(-1.0, min(1.0, float(event.severity)))
            age_days = max(0.0, (as_of_dt - occurred_dt).total_seconds() / 86400.0)
            recency_weight = math.pow(0.5, age_days / self.half_life_days)
            contribution = severity * type_weight * recency_weight
            weighted_score += contribution
            evidence.append({
                "occurred_at": event.occurred_at,
                "event_type": event_type,
                "source": event.source,
                "summary": event.summary,
                "severity": severity,
                "contribution": round(contribution, 4),
            })

        event_score = round(max(0.0, min(100.0, 50.0 + weighted_score * 25.0)), 2)
        if event_score <= 25.0:
            stage, priority = "RISK_OFF", "DEFENSIVE"
        elif event_score < 45.0:
            stage, priority = "COLD", "LOW"
        elif event_score < 60.0:
            stage, priority = "WATCH", "NORMAL"
        elif event_score < 80.0:
            stage, priority = "WARMING", "HIGH"
        else:
            stage, priority = "HOT", "HIGH"

        price_confirmation = abs(float(price_change_pct)) >= 1.0
        snapshot = SubnewEventSentimentSnapshot(
            as_of=as_of_dt.isoformat(sep=" "),
            window_start=start_dt.isoformat(sep=" "),
            stage=stage,
            event_score=event_score,
            used_event_count=len(evidence),
            event_types=sorted({item["event_type"] for item in evidence}),
            evidence=sorted(evidence, key=lambda item: item["occurred_at"]),
            price_confirmation=price_confirmation,
            watch_priority=priority,
            allow_buy=stage in ("WARMING", "HOT") and price_confirmation,
        )
        return snapshot.finalize()

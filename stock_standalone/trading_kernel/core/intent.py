from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionReason:
    regime: str
    setup: str
    sector_heat: float
    sector_rank: int | None
    is_leader: bool
    breakout: bool
    volume_ratio: float
    dff: float
    dff_positive: bool
    price_above_vwap: bool
    confidence_inputs: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class DecisionIntent:
    code: str
    action: str
    size_pct: float
    stop_price: float | None
    confidence: float
    reason: DecisionReason
    expires_at: str


from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ApprovedOrder:
    order_id: str
    code: str
    action: str
    size_pct: float
    price: float
    stop_price: float | None


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    final_action: str
    final_size_pct: float
    reject_context: Mapping[str, Any]
    order: ApprovedOrder | None


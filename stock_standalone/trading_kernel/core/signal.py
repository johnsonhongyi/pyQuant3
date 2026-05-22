from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class StrategySignal:
    code: str
    name: str
    ts: str
    source: str
    signal_type: str
    price: float
    features: Mapping[str, Any]


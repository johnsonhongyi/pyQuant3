from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelTrace:
    trace_id: str
    raw_event_hash: str
    signal_hash: str
    state: str
    intent_hash: str | None
    risk_hash: str | None
    execution_hash: str | None
    timestamp: str


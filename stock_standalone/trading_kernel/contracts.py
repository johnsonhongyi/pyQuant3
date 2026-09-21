# -*- coding: utf-8 -*-
"""Versioned extension contracts for the packaged trading kernel.

External systems must depend on these contracts and ``KernelGateway`` only.
They must not reach into ``TradingKernelService`` implementation attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from trading_kernel.core.intent import DecisionIntent
from trading_kernel.core.signal import StrategySignal


KERNEL_API_VERSION = "1.0"


@dataclass(frozen=True)
class DecisionRequest:
    code: str
    name: str = ""
    action: str = ""
    signal_type: str = "UNKNOWN"
    price: float = 0.0
    requested_size_pct: float = 0.0
    reason: str = ""
    source: str = "EXTERNAL"
    timestamp: str = ""
    features: Mapping[str, Any] = field(default_factory=dict)
    request_id: str = ""
    api_version: str = KERNEL_API_VERSION

    def to_kernel_item(self) -> dict[str, Any]:
        item = dict(self.features)
        item.update({
            "code": self.code,
            "name": self.name,
            "action": self.action,
            "signal_type": self.signal_type,
            "current_price": self.price,
            "suggest_price": self.price,
            "requested_size_pct": self.requested_size_pct,
            "reason": self.reason,
            "source": self.source,
        })
        if self.timestamp:
            item["created_at"] = self.timestamp
        if self.request_id:
            item["request_id"] = self.request_id
        return item


@dataclass(frozen=True)
class DecisionResponse:
    accepted: bool
    executed: bool
    action: str
    size_pct: float
    trace_id: str
    order_id: str
    reject_code: str = ""
    state: str = "FLAT"
    api_version: str = KERNEL_API_VERSION


@runtime_checkable
class StrategyProvider(Protocol):
    """Pluggable strategy decision port."""

    provider_id: str

    def decide(self, signal: StrategySignal, state: str) -> DecisionIntent:
        ...


@runtime_checkable
class StateStore(Protocol):
    """Cross-process trade-state storage port."""

    def get(self, code: str) -> str:
        ...

    def set(self, code: str, state: str) -> None:
        ...

    def snapshot(self) -> dict[str, str]:
        ...


@runtime_checkable
class EventSink(Protocol):
    """Audit/event output port."""

    def append(self, record: Mapping[str, Any]) -> None:
        ...

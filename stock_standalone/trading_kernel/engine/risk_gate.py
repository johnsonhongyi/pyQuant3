from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from trading_kernel.core.intent import DecisionIntent
from trading_kernel.core.risk import ApprovedOrder, RiskDecision
from trading_kernel.core.signal import StrategySignal
from trading_kernel.observability.trace_hasher import stable_hash


@dataclass(frozen=True)
class RiskLimits:
    max_single_size_pct: float = 0.40
    min_confidence: float = 0.55
    allow_buy: bool = True
    allow_sell: bool = True


def evaluate(
    intent: DecisionIntent,
    signal: StrategySignal,
    state: str,
    limits: RiskLimits = RiskLimits(),
    held_codes: Mapping[str, str] | None = None,
) -> RiskDecision:
    held_codes = held_codes or {}
    action = intent.action
    reject = {}

    if action == "BUY":
        if not limits.allow_buy:
            reject = {"code": "BUY_DISABLED", "severity": "HARD_BLOCK"}
        elif intent.confidence < limits.min_confidence:
            reject = {
                "code": "LOW_CONFIDENCE",
                "confidence": intent.confidence,
                "limit": limits.min_confidence,
                "severity": "HARD_BLOCK",
            }
        elif signal.code in held_codes or state == "IN_TRADE":
            reject = {"code": "ALREADY_IN_TRADE", "severity": "HARD_BLOCK"}
    elif action in {"SELL", "REDUCE"}:
        if not limits.allow_sell:
            reject = {"code": "SELL_DISABLED", "severity": "HARD_BLOCK"}
    elif action == "ADD" and state != "IN_TRADE":
        reject = {"code": "ADD_REQUIRES_POSITION", "severity": "HARD_BLOCK"}

    if reject:
        return RiskDecision(
            allowed=False,
            final_action="BLOCK",
            final_size_pct=0.0,
            reject_context=reject,
            order=None,
        )

    final_size = min(intent.size_pct, limits.max_single_size_pct)
    order = None
    if action in {"BUY", "ADD", "SELL", "REDUCE"} and final_size > 0:
        order = ApprovedOrder(
            order_id=stable_hash((signal.code, signal.ts, action, final_size))[:24],
            code=signal.code,
            action=action,
            size_pct=round(final_size, 4),
            price=signal.price,
            stop_price=intent.stop_price,
        )

    return RiskDecision(
        allowed=order is not None or action == "HOLD",
        final_action=action,
        final_size_pct=round(final_size, 4),
        reject_context={},
        order=order,
    )


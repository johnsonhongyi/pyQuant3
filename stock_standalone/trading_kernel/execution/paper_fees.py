"""Explicit simulation fee policy; amounts are rounded half up to cents."""

from decimal import Decimal, ROUND_HALF_UP


def paper_fee(notional: float, side: str, rate: float = 0.0000754,
              sell_extra: float = 5.0) -> float:
    amount, commission, extra = map(lambda v: Decimal(str(v)), (notional, rate, sell_extra))
    if any(not v.is_finite() or v < 0 for v in (amount, commission, extra)):
        raise ValueError("INVALID_PAPER_FEE_INPUT")
    action = side.upper()
    if action not in {"BUY", "ADD", "SELL", "REDUCE"}:
        raise ValueError("INVALID_PAPER_FEE_SIDE")
    return float((amount * commission + (extra if action in {"SELL", "REDUCE"} else 0))
                 .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

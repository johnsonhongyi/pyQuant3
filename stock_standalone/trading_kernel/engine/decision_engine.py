from __future__ import annotations

import math

from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.core.signal import StrategySignal


def _num(signal: StrategySignal, key: str, default: float = 0.0) -> float:
    try:
        return float(signal.features.get(key, default))
    except Exception:
        return default


def _confidence(priority: float, sector_heat: float, pct_diff: float, dff: float) -> float:
    score = 0.0
    score += min(max(priority, 0.0), 100.0) * 0.004
    score += min(max(sector_heat, 0.0), 100.0) * 0.003
    score += min(max(pct_diff, 0.0), 8.0) * 0.025
    score += min(max(dff, 0.0), 8.0) * 0.0125
    return round(min(max(score, 0.0), 0.95), 4)


def decide(signal: StrategySignal, state: str) -> DecisionIntent:
    # ── 手工干预或强制平仓与买入逻辑，直接走绿色通道无条件执行 ──
    raw_action = str(signal.features.get("action", "")).upper()
    is_manual_sell = (raw_action == "SELL" or signal.signal_type == "手工平仓" or "手工平仓" in str(signal.features.get("raw_reason", "")))
    is_manual_buy = (raw_action in {"BUY", "ADD"} and (signal.signal_type == "手动买入" or "手动买入" in str(signal.features.get("raw_reason", "")) or "Confirm:" in str(signal.features.get("raw_reason", ""))))
    
    if is_manual_sell or is_manual_buy:
        action = "BUY" if is_manual_buy else "SELL"
        reason = DecisionReason(
            regime="MANUAL_OVERRIDE",
            setup="手动交易" if is_manual_buy else "手工平仓",
            sector_heat=0.0,
            sector_rank=None,
            is_leader=False,
            breakout=False,
            volume_ratio=1.0,
            dff=0.0,
            dff_positive=False,
            price_above_vwap=True,
            confidence_inputs=(),
        )
        return DecisionIntent(
            code=signal.code,
            action=action,
            size_pct=0.30 if action == "BUY" else 1.0,  # 手工买入默认为30%仓位，卖出100%全平
            stop_price=round(signal.price * 0.98, 3) if action == "BUY" and signal.price > 0 else None,
            confidence=1.0,
            reason=reason,
            expires_at=signal.ts,
        )

    priority = _num(signal, "priority")
    sector_heat = _num(signal, "sector_heat")
    pct_diff = _num(signal, "pct_diff")
    dff = _num(signal, "dff")
    price = signal.price
    suggest_price = _num(signal, "suggest_price", price)
    volume_ratio = max(1.0, _num(signal, "hits", 1.0))
    breakout = pct_diff > 0.3 or "BREAKOUT" in signal.signal_type.upper()
    dff_positive = dff > 0
    is_leader = bool(signal.features.get("is_leader", False))
    regime = "BREAKOUT_ALLOWED" if sector_heat >= 20 and priority >= 50 else "WATCH_ONLY"
    setup = signal.signal_type or "UNKNOWN"
    confidence = _confidence(priority, sector_heat, pct_diff, dff)

    action = "HOLD"
    size_pct = 0.0
    if state in {"FLAT", "ARMED"} and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
        action = "BUY"
        size_pct = 0.30 if confidence < 0.75 else 0.40
    elif state == "IN_TRADE" and (pct_diff < -1.5 or dff < -1.0):
        action = "SELL"
        size_pct = 1.0
    elif state == "IN_TRADE" and confidence >= 0.80:
        action = "ADD"
        size_pct = 0.20
    elif state == "EXITING":
        action = "SELL"
        size_pct = 1.0

    stop_price = None
    if action in {"BUY", "ADD"} and suggest_price > 0:
        stop_price = round(suggest_price * 0.98, 3)

    reason = DecisionReason(
        regime=regime,
        setup=setup,
        sector_heat=round(sector_heat, 4),
        sector_rank=None,
        is_leader=is_leader,
        breakout=breakout,
        volume_ratio=round(volume_ratio, 4),
        dff=round(dff, 4),
        dff_positive=dff_positive,
        price_above_vwap=not math.isnan(price) and price > 0,
        confidence_inputs=(
            ("priority", round(priority, 4)),
            ("sector_heat", round(sector_heat, 4)),
            ("pct_diff", round(pct_diff, 4)),
            ("dff", round(dff, 4)),
        ),
    )
    return DecisionIntent(
        code=signal.code,
        action=action,
        size_pct=round(size_pct, 4),
        stop_price=stop_price,
        confidence=confidence,
        reason=reason,
        expires_at=signal.ts,
    )


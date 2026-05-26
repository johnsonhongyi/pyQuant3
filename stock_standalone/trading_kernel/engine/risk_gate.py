from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from trading_kernel.core.intent import DecisionIntent
from trading_kernel.core.risk import ApprovedOrder, RiskDecision
from trading_kernel.core.signal import StrategySignal
from trading_kernel.observability.trace_hasher import stable_hash


@dataclass(frozen=True)
class RiskLimits:
    max_single_size_pct: float = 0.40
    min_confidence: float = 0.55  # Retain 0.55 for headless tests alignment, override by physical configuration
    allow_buy: bool = True
    allow_sell: bool = True
    
    # Phase 5 Hard Constraints
    max_single_stock_position_pct: float = 0.30  # single stock max position
    max_single_sector_exposure_pct: float = 0.50  # single sector max exposure
    total_exposure_cap_pct: float = 0.80  # total exposure cap
    daily_loss_limit_amount: float = 50000.0  # daily loss limit amount
    max_consecutive_losses: int = 3  # cooldown after consecutive losses
    
    # High extension no-chase block
    max_pct_diff: float = 6.0  # limit up / chase limit
    
    # Low volume filter card
    min_volume: float = 1.0  # standard volume threshold
    
    # Blacklist block
    blacklist: tuple[str, ...] = ()


def parse_ts(t_str: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
        try:
            return datetime.strptime(t_str, fmt)
        except ValueError:
            continue
    return None


def evaluate(
    intent: DecisionIntent,
    signal: StrategySignal,
    state: str,
    limits: RiskLimits = RiskLimits(),
    held_codes: Mapping[str, str] | None = None,
    # Phase 5 dynamic parameters passed dynamically
    current_stock_exposure: float = 0.0,
    current_sector_exposure: float = 0.0,
    current_total_exposure: float = 0.0,
    today_pnl_loss: float = 0.0,
    consecutive_losses: int = 0,
    current_time: str = "",
) -> RiskDecision:
    held_codes = held_codes or {}
    action = intent.action
    reject = {}

    # 1. Non-trading session block
    time_part = signal.ts.split()[-1] if " " in signal.ts else signal.ts.split("T")[-1]
    try:
        parts = time_part.split(":")
        hhmm = int(parts[0]) * 100 + int(parts[1])
    except Exception:
        hhmm = 930
    
    is_trading_hour = (915 <= hhmm <= 1130) or (1300 <= hhmm <= 1505)
    
    if action in {"BUY", "ADD"}:
        if not is_trading_hour:
            reject = {"code": "NON_TRADING_SESSION", "time": signal.ts, "severity": "HARD_BLOCK"}
        
        # 2. Blacklist block
        elif signal.code in limits.blacklist:
            reject = {"code": "BLACKLISTED_SYMBOL", "severity": "HARD_BLOCK"}
            
        # 3. Expired signal block
        elif current_time:
            dt_sig = parse_ts(signal.ts)
            dt_curr = parse_ts(current_time)
            if dt_sig and dt_curr:
                diff = (dt_curr - dt_sig).total_seconds()
                if diff > 300:
                    reject = {"code": "SIGNAL_EXPIRED", "diff_seconds": diff, "severity": "HARD_BLOCK"}
                    
        # 4. Cooldown after consecutive losses
        elif consecutive_losses >= limits.max_consecutive_losses:
            reject = {
                "code": "CONSECUTIVE_LOSS_COOLDOWN",
                "consecutive_losses": consecutive_losses,
                "limit": limits.max_consecutive_losses,
                "severity": "HARD_BLOCK",
            }
            
        # 5. Daily loss limit
        elif today_pnl_loss >= limits.daily_loss_limit_amount:
            reject = {
                "code": "DAILY_LOSS_LIMIT_EXCEEDED",
                "today_pnl_loss": today_pnl_loss,
                "limit": limits.daily_loss_limit_amount,
                "severity": "HARD_BLOCK",
            }
            
        # 6. High extension no-chase block
        elif float(signal.features.get("pct_diff", 0.0)) > limits.max_pct_diff:
            reject = {
                "code": "HIGH_EXTENSION_NO_CHASE",
                "pct_diff": signal.features.get("pct_diff", 0.0),
                "limit": limits.max_pct_diff,
                "severity": "HARD_BLOCK",
            }
            
        # 6.5 Low volume block (volume filter)
        else:
            try:
                sig_vol = float(signal.features.get("volume", 1.0))
            except (ValueError, TypeError):
                sig_vol = 1.0
            if sig_vol < limits.min_volume:
                reject = {
                    "code": "LOW_VOLUME_BLOCKED",
                    "volume": sig_vol,
                    "limit": limits.min_volume,
                    "severity": "HARD_BLOCK",
                }

    # Core Action Evaluation
    if not reject:
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

    # Core Position Exposure Check & Size Reduction (Sizing Adjustments)
    if action in {"BUY", "ADD"}:
        final_size = min(intent.size_pct, limits.max_single_size_pct)
    else:
        final_size = intent.size_pct
    
    if action in {"BUY", "ADD"} and final_size > 0:
        # 7. Single stock max position check & sizing limit
        if current_stock_exposure + final_size > limits.max_single_stock_position_pct:
            final_size = max(0.0, limits.max_single_stock_position_pct - current_stock_exposure)
            if final_size <= 0:
                return RiskDecision(
                    allowed=False,
                    final_action="BLOCK",
                    final_size_pct=0.0,
                    reject_context={
                        "code": "SINGLE_STOCK_EXPOSURE_EXCEEDED",
                        "current_exposure": current_stock_exposure,
                        "limit": limits.max_single_stock_position_pct,
                        "severity": "HARD_BLOCK",
                    },
                    order=None,
                )
        
        # 8. Single sector max exposure check & sizing limit
        if current_sector_exposure + final_size > limits.max_single_sector_exposure_pct:
            final_size = max(0.0, limits.max_single_sector_exposure_pct - current_sector_exposure)
            if final_size <= 0:
                return RiskDecision(
                    allowed=False,
                    final_action="BLOCK",
                    final_size_pct=0.0,
                    reject_context={
                        "code": "SECTOR_EXPOSURE_EXCEEDED",
                        "current_sector_exposure": current_sector_exposure,
                        "limit": limits.max_single_sector_exposure_pct,
                        "severity": "HARD_BLOCK",
                    },
                    order=None,
                )
                
        # 9. Total exposure cap check & sizing limit
        if current_total_exposure + final_size > limits.total_exposure_cap_pct:
            final_size = max(0.0, limits.total_exposure_cap_pct - current_total_exposure)
            if final_size <= 0:
                return RiskDecision(
                    allowed=False,
                    final_action="BLOCK",
                    final_size_pct=0.0,
                    reject_context={
                        "code": "TOTAL_EXPOSURE_EXCEEDED",
                        "current_total_exposure": current_total_exposure,
                        "limit": limits.total_exposure_cap_pct,
                        "severity": "HARD_BLOCK",
                    },
                    order=None,
                )

    order = None
    if action in {"BUY", "ADD", "SELL", "REDUCE"} and final_size > 0:
        order = ApprovedOrder(
            # 10. Single trade stop loss is incorporated into order stop_price
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


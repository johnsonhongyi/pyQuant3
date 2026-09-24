# -*- coding: utf-8 -*-
"""Read-only views and performance metrics for the authoritative TK paper account.

All ATS presentation layers should consume this module instead of inventing their
own paper ledgers.  Order execution remains owned by ``TradingKernelService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ClosedPaperTrade:
    code: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    volume: float
    profit: float
    pnl_pct: float


@dataclass(frozen=True)
class PaperExecutionResult:
    executed: bool
    order_id: str = ""
    trace_id: str = ""
    action: str = "HOLD"
    reject_code: str = ""
    volume: float = 0.0
    size_pct: float = 0.0
    request_id: str = ""
    execution_id: str = ""
    status: str = "REJECTED"
    related_orders: tuple = ()


def get_ssot_read_model(gateway: Any = None) -> Dict[str, Any]:
    """Return one coherent TK-owned read model for ATS presentation."""
    from trading_kernel.gateway import KernelGateway

    return dict((gateway if gateway is not None else KernelGateway()).get_account_read_model())


def get_orders(gateway: Any = None) -> List[Dict[str, Any]]:
    return [
        dict(item)
        for item in get_ssot_read_model(gateway).get("orders", [])
        if isinstance(item, dict)
    ]


def get_positions(gateway: Any = None) -> Dict[str, Dict[str, Any]]:
    return {
        str(code): dict(raw)
        for code, raw in get_ssot_read_model(gateway).get("positions", {}).items()
        if isinstance(raw, dict)
    }


def get_account_snapshot(gateway: Any = None) -> Dict[str, Any]:
    return dict(get_ssot_read_model(gateway).get("account", {}))


def reconcile_account(read_model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Audit orders versus holdings without creating a second financial ledger.

    Current holdings/cash/orders come only from the TK read model. Legacy
    inconsistencies are reported, never repaired by ATS-side bookkeeping.
    """
    if read_model is None:
        read_model = get_ssot_read_model()
    read_model = dict(read_model) if isinstance(read_model, dict) else {}
    kernel_reconciliation = read_model.get("reconciliation")
    kernel_reconciliation = (
        dict(kernel_reconciliation) if isinstance(kernel_reconciliation, dict) else {}
    )
    account = read_model.get("account")
    account = account if isinstance(account, dict) else {}
    paper_execution_ready = account.get("paper_execution_ready") is True
    kernel_status = str(kernel_reconciliation.get("status") or "")
    ledger_status = str(kernel_reconciliation.get("ledger_status") or "")
    positions = {
        str(code): dict(raw)
        for code, raw in read_model.get("positions", {}).items()
        if isinstance(raw, dict)
    }
    orders = [
        dict(item)
        for item in read_model.get("orders", [])
        if isinstance(item, dict)
    ]
    open_volume: Dict[str, float] = {}
    for order in sorted(orders, key=lambda item: str(item.get("timestamp") or "")):
        code = str(order.get("code") or "").strip().zfill(6)
        action = str(order.get("action") or "").upper()
        volume = _number(order.get("volume"))
        if not code or volume <= 0:
            continue
        if action in {"BUY", "ADD"}:
            open_volume[code] = open_volume.get(code, 0.0) + volume
        elif action == "SELL":
            # PaperAdapter semantics: SELL always closes the full position even
            # when an old ledger row carries a stale/partial volume value.
            open_volume[code] = 0.0
        elif action == "REDUCE":
            open_volume[code] = max(0.0, open_volume.get(code, 0.0) - volume)
    derived_codes = {code for code, volume in open_volume.items() if volume > 1e-9}
    snapshot_codes = set(positions)
    code_sets_aligned = snapshot_codes == derived_codes
    quantity_mismatches: Dict[str, Dict[str, float]] = {}
    for code in sorted(snapshot_codes & derived_codes):
        raw_position = positions[code]
        snapshot_qty = _number(
            raw_position.get("total_qty", raw_position.get("volume", raw_position.get("shares")))
        )
        order_qty = open_volume.get(code, 0.0)
        if abs(snapshot_qty - order_qty) > 1e-6:
            quantity_mismatches[code] = {
                "snapshot_qty": snapshot_qty,
                "order_derived_qty": order_qty,
            }
    projection_aligned = code_sets_aligned and not quantity_mismatches
    if not paper_execution_ready:
        status = "PAPER_RESTORE_BLOCKED"
    elif (
        kernel_status != "ALIGNED"
        or ledger_status != "ALIGNED"
        or not projection_aligned
    ):
        status = "RECONCILIATION_MISMATCH"
    else:
        status = "ALIGNED"
    return {
        "status": status,
        "kernel_status": kernel_status or "SSOT_RECONCILIATION_MISSING",
        "ledger_status": ledger_status or "SSOT_LEDGER_STATUS_MISSING",
        "paper_execution_ready": paper_execution_ready,
        "paper_execution_block_reason": str(
            account.get("paper_execution_block_reason") or
            ("PAPER_EXECUTION_READINESS_MISSING" if "paper_execution_ready" not in account else "")
        ),
        "changed_count": kernel_reconciliation.get("changed_count"),
        "differences": list(kernel_reconciliation.get("differences") or []),
        "snapshot_position_count": len(snapshot_codes),
        "order_derived_position_count": len(derived_codes),
        "projection_status": (
            "CODE_SET_MISMATCH" if not code_sets_aligned else
            "QUANTITY_MISMATCH" if quantity_mismatches else "ALIGNED"
        ),
        "snapshot_only_codes": sorted(snapshot_codes - derived_codes),
        "order_only_codes": sorted(derived_codes - snapshot_codes),
        "quantity_mismatches": quantity_mismatches,
        "authoritative_current_source": "paper_account_snapshot",
        "authoritative_performance_source": "paper_orders_fifo",
    }


def execute_command_directive(directive: Any, *, gateway: Any = None) -> PaperExecutionResult:
    """Route one command-room directive through the authoritative TK kernel."""
    raw_action = str(getattr(directive, "action", "") or "").upper()
    if raw_action == "FULL_ROTATION_SWAP":
        from types import SimpleNamespace

        directive_id = str(getattr(directive, "directive_id", "") or "")
        old_code = str(getattr(directive, "target_swap_code", "") or "").zfill(6)
        sell_request_id = f"{directive_id}:sell" if directive_id else ""
        buy_request_id = f"{directive_id}:buy" if directive_id else ""
        orders = get_orders(gateway) if gateway is not None else get_orders()
        prior_sell = next(
            (item for item in reversed(orders)
             if sell_request_id and str(item.get("request_id") or "") == sell_request_id
             and str(item.get("action") or "").upper() == "SELL"),
            None,
        )
        prior_buy = next(
            (item for item in reversed(orders)
             if buy_request_id and str(item.get("request_id") or "") == buy_request_id
             and str(item.get("action") or "").upper() == "BUY"),
            None,
        )
        if prior_buy is not None and prior_sell is None:
            return PaperExecutionResult(
                False, action=raw_action, reject_code="ROTATION_BUY_WITHOUT_SELL_AUDIT",
                request_id=directive_id, order_id=str(prior_buy.get("order_id") or ""),
                execution_id=str(prior_buy.get("execution_id") or prior_buy.get("order_id") or ""),
                status="REJECTED",
            )
        if prior_sell is not None:
            sold = PaperExecutionResult(
                True, order_id=str(prior_sell.get("order_id") or ""), action="SELL",
                volume=_number(prior_sell.get("volume")), size_pct=_number(prior_sell.get("size_pct")),
                request_id=sell_request_id,
                execution_id=str(prior_sell.get("execution_id") or prior_sell.get("order_id") or ""),
                status="FILLED",
            )
            if prior_buy is not None:
                bought = PaperExecutionResult(
                    True, order_id=str(prior_buy.get("order_id") or ""), action="BUY",
                    volume=_number(prior_buy.get("volume")), size_pct=_number(prior_buy.get("size_pct")),
                    request_id=buy_request_id,
                    execution_id=str(prior_buy.get("execution_id") or prior_buy.get("order_id") or ""),
                    status="FILLED",
                )
            else:
                buy_leg = SimpleNamespace(
                    action="BUY", code=getattr(directive, "code", ""),
                    name=getattr(directive, "name", ""), price=getattr(directive, "price", 0.0),
                    size_pct=getattr(directive, "size_pct", 0.0),
                    reason=f"全仓轮动买入腿: {getattr(directive, 'reason', '')}",
                    directive_id=buy_request_id,
                )
                bought = execute_command_directive(buy_leg, gateway=gateway)
            related = (
                {"leg": "SELL", "request_id": sold.request_id, "order_id": sold.order_id,
                 "execution_id": sold.execution_id, "status": sold.status, "volume": sold.volume},
                {"leg": "BUY", "request_id": bought.request_id, "order_id": bought.order_id,
                 "execution_id": bought.execution_id, "status": bought.status, "volume": bought.volume},
            )
            if not bought.executed:
                return PaperExecutionResult(
                    False, action=raw_action,
                    reject_code=f"ROTATION_BUY_FAILED_AFTER_SELL:{bought.reject_code}",
                    request_id=directive_id, order_id=sold.order_id, execution_id=sold.execution_id,
                    status="PARTIAL", related_orders=related,
                )
            return PaperExecutionResult(
                True, bought.order_id, bought.trace_id, raw_action, "", bought.volume,
                bought.size_pct, directive_id or bought.request_id, bought.execution_id,
                bought.status, related_orders=related,
            )
        old_position = (get_positions(gateway) if gateway is not None else get_positions()).get(old_code)
        if not old_position:
            return PaperExecutionResult(False, action=raw_action, reject_code="ROTATION_SOURCE_NOT_HELD")
        sell_leg = SimpleNamespace(
            action="SELL",
            code=old_code,
            name=str(getattr(directive, "target_swap_name", "") or old_code),
            price=_number(old_position.get("current_price") or old_position.get("entry_price")),
            size_pct=100.0,
            reason=f"全仓轮动卖出腿: {getattr(directive, 'reason', '')}",
            directive_id=f"{directive_id}:sell" if directive_id else "",
        )
        sold = execute_command_directive(sell_leg, gateway=gateway)
        if not sold.executed:
            return PaperExecutionResult(
                False, action=raw_action, reject_code=f"ROTATION_SELL_REJECTED:{sold.reject_code}",
                request_id=sold.request_id, order_id=sold.order_id, execution_id=sold.execution_id,
                status=sold.status, related_orders=sold.related_orders,
            )
        buy_leg = SimpleNamespace(
            action="BUY",
            code=getattr(directive, "code", ""),
            name=getattr(directive, "name", ""),
            price=getattr(directive, "price", 0.0),
            size_pct=getattr(directive, "size_pct", 0.0),
            reason=f"全仓轮动买入腿: {getattr(directive, 'reason', '')}",
            directive_id=f"{directive_id}:buy" if directive_id else "",
        )
        bought = execute_command_directive(buy_leg, gateway=gateway)
        if not bought.executed:
            return PaperExecutionResult(
                False, action=raw_action, reject_code=f"ROTATION_BUY_FAILED_AFTER_SELL:{bought.reject_code}",
                request_id=directive_id, order_id=sold.order_id, execution_id=sold.execution_id,
                status="PARTIAL",
                related_orders=(
                    {"leg": "SELL", "request_id": sold.request_id, "order_id": sold.order_id,
                     "execution_id": sold.execution_id, "status": sold.status, "volume": sold.volume},
                    {"leg": "BUY", "request_id": bought.request_id, "order_id": bought.order_id,
                     "execution_id": bought.execution_id, "status": bought.status, "volume": bought.volume},
                ),
            )
        return PaperExecutionResult(
            True, bought.order_id, bought.trace_id, raw_action, "",
            bought.volume, bought.size_pct,
            directive_id or bought.request_id, bought.execution_id, bought.status,
            related_orders=(
                {"leg": "SELL", "request_id": sold.request_id, "order_id": sold.order_id,
                 "execution_id": sold.execution_id, "status": sold.status, "volume": sold.volume},
                {"leg": "BUY", "request_id": bought.request_id, "order_id": bought.order_id,
                 "execution_id": bought.execution_id, "status": bought.status, "volume": bought.volume},
            ),
        )

    if raw_action in {"BUY", "BUY_SCOUT", "BUY_CONFIRM"}:
        kernel_action = "BUY"
        signal_type = "手动买入"
    elif raw_action in {"SELL", "EXIT_ALL", "SWITCH_SWAP"}:
        kernel_action = "SELL"
        signal_type = "手工平仓"
    elif raw_action in {"REDUCE_30", "REDUCE_HALF"}:
        kernel_action = "REDUCE"
        signal_type = "手工减仓"
    else:
        return PaperExecutionResult(
            executed=False,
            action=raw_action or "HOLD",
            reject_code="UNSUPPORTED_COMMAND_ACTION",
        )

    price = _number(getattr(directive, "price", 0.0))
    requested_pct = _number(getattr(directive, "size_pct", 0.0)) / 100.0
    if kernel_action == "SELL":
        requested_pct = 1.0
    elif raw_action == "REDUCE_30":
        requested_pct = 0.30
    elif raw_action == "REDUCE_HALF":
        requested_pct = 0.50
    if price <= 0:
        return PaperExecutionResult(False, action=kernel_action, reject_code="INVALID_PRICE")

    from trading_kernel.contracts import DecisionRequest
    from trading_kernel.gateway import KernelGateway

    directive_id = str(getattr(directive, "directive_id", "") or "")
    audit = getattr(directive, "audit_envelope", None) or {}
    if not isinstance(audit, dict):
        audit = {}
    strategy_tag = str(
        audit.get("strategy_tag") or getattr(directive, "strategy_tag", "") or ""
    )
    tide_state = str(audit.get("tide_state") or audit.get("market_tide_state") or "")
    cross_day_state = str(
        audit.get("cross_day_state") or audit.get("cross_day_path") or ""
    )
    gateway = gateway if gateway is not None else KernelGateway()
    if gateway.get_mode() != "PAPER":
        if not gateway.set_mode("PAPER"):
            return PaperExecutionResult(False, action=kernel_action, reject_code="PAPER_MODE_UNAVAILABLE")

    before_count = len(gateway.get_order_history())
    response = gateway.submit(
        DecisionRequest(
            code=str(getattr(directive, "code", "") or "").zfill(6),
            name=str(getattr(directive, "name", "") or ""),
            action=kernel_action,
            signal_type=signal_type,
            price=price,
            requested_size_pct=requested_pct,
            reason=f"交易指挥室统一PAPER执行: {getattr(directive, 'reason', '')}",
            source="IPO_COMMAND_ROOM",
            request_id=directive_id,
            features={
                "priority": 100.0,
                "directive_id": directive_id,
                "candidate_id": str(audit.get("candidate_id") or ""),
                "plan_id": str(audit.get("plan_id") or ""),
                "exit_rule_id": str(audit.get("exit_rule_id") or ""),
                "strategy_tag": strategy_tag,
                "tide_state": tide_state,
                "cross_day_state": cross_day_state,
            },
        ),
        write_journal=True,
    )
    orders = gateway.get_order_history()
    last_order = orders[-1] if len(orders) > before_count and isinstance(orders[-1], dict) else {}
    if not last_order and directive_id:
        last_order = next(
            (dict(item) for item in reversed(orders)
             if isinstance(item, dict) and str(item.get("request_id") or "") == directive_id),
            {},
        )
    volume = _number(last_order.get("volume"))
    requested_shares = _number(getattr(directive, "shares", 0))
    status = "REJECTED"
    if response.executed:
        status = "PARTIAL" if volume > 0 and requested_shares > 0 and volume < requested_shares else (
            "FILLED" if volume > 0 else "EXECUTED"
        )
    return PaperExecutionResult(
        executed=response.executed,
        order_id=response.order_id or str(last_order.get("order_id") or ""),
        trace_id=response.trace_id,
        action=response.action or kernel_action,
        reject_code=response.reject_code,
        volume=volume,
        size_pct=_number(last_order.get("size_pct"), requested_pct),
        request_id=str(last_order.get("request_id") or directive_id),
        execution_id=str(last_order.get("execution_id") or response.order_id or last_order.get("order_id") or ""),
        status=status,
    )


def pair_closed_trades(orders: Optional[Iterable[Dict[str, Any]]] = None) -> List[ClosedPaperTrade]:
    """FIFO-pair BUY/ADD with SELL/REDUCE without using future information."""
    lots: Dict[str, List[Dict[str, Any]]] = {}
    closed: List[ClosedPaperTrade] = []
    ordered = sorted(
        [dict(item) for item in (orders if orders is not None else get_orders()) if isinstance(item, dict)],
        key=lambda item: str(item.get("timestamp") or ""),
    )

    for order in ordered:
        code = str(order.get("code") or "").strip().zfill(6)
        action = str(order.get("action") or "").upper()
        price = _number(order.get("price"))
        volume = _number(order.get("volume"))
        timestamp = str(order.get("timestamp") or "")
        if not code or price <= 0 or volume <= 0:
            continue
        if action in {"BUY", "ADD"}:
            lots.setdefault(code, []).append(
                {"price": price, "remaining": volume, "timestamp": timestamp}
            )
            continue
        if action not in {"SELL", "REDUCE"}:
            continue

        remaining_sell = volume
        code_lots = lots.setdefault(code, [])
        while remaining_sell > 1e-9 and code_lots:
            lot = code_lots[0]
            matched = min(remaining_sell, _number(lot.get("remaining")))
            entry_price = _number(lot.get("price"))
            if matched <= 0 or entry_price <= 0:
                code_lots.pop(0)
                continue
            profit = (price - entry_price) * matched
            closed.append(
                ClosedPaperTrade(
                    code=code,
                    entry_time=str(lot.get("timestamp") or ""),
                    exit_time=timestamp,
                    entry_price=entry_price,
                    exit_price=price,
                    volume=matched,
                    profit=profit,
                    pnl_pct=(price - entry_price) / entry_price * 100.0,
                )
            )
            lot["remaining"] = _number(lot.get("remaining")) - matched
            remaining_sell -= matched
            if lot["remaining"] <= 1e-9:
                code_lots.pop(0)
    return closed


def calculate_metrics() -> Dict[str, Any]:
    """Calculate auditable paper metrics; never return demonstration values."""
    trades = pair_closed_trades()
    if not trades:
        return {
            "总交易次数": "0",
            "策略胜率": "--",
            "平均盈利/亏损": "--",
            "最大回撤": "--",
            "凯利建议仓位": "--",
            "持有期衰减": "--",
            "累计收益": "--",
            "data_status": "NO_CLOSED_PAPER_TRADES",
        }

    profits = [trade.profit for trade in trades]
    wins = [trade for trade in trades if trade.profit > 0]
    losses = [trade for trade in trades if trade.profit <= 0]
    gross_profit = sum(trade.profit for trade in wins)
    gross_loss = abs(sum(trade.profit for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    initial = _number(get_account_snapshot().get("initial_capital"), 1_000_000.0)
    equity = initial
    peak = initial
    max_drawdown = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, (equity - peak) / peak)

    win_rate = len(wins) / len(trades)
    avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses)) if losses else 0.0
    if avg_loss > 0 and avg_win > 0:
        payoff = avg_win / avg_loss
        kelly = max(0.0, min(0.30, win_rate - (1.0 - win_rate) / payoff))
        kelly_text = f"{kelly * 100:.1f}%"
    else:
        kelly_text = "--"

    return {
        "总交易次数": str(len(trades)),
        "策略胜率": f"{win_rate * 100:.1f}%",
        "平均盈利/亏损": "∞" if profit_factor == float("inf") else f"{profit_factor:.2f}",
        "最大回撤": f"{max_drawdown * 100:.1f}%",
        "凯利建议仓位": kelly_text,
        "持有期衰减": "待按交易日历计算",
        "累计收益": f"{sum(profits):+.2f}",
        "data_status": "OK",
    }

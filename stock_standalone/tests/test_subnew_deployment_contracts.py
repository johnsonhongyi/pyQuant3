# -*- coding: utf-8 -*-
"""
tests/test_subnew_deployment_contracts.py

Task 014 Verification Suite:
- GO/NO-GO one-way gate latching and trading center integration.
- EXIT > BUY independent blocking contract (convergence + execution layers).
- T+1 physical isolation: newly bought shares are not sellable today (available_shares=0).
- T+1 physical isolation: yesterday's shares + today's additions -> only yesterday's sellable.
- No bypass of T+1 lock by catastrophic stop loss.
- Authoritative reconciliation mismatch triggers bidirectional EXECUTION_BLOCKED.
- Explicit reconciliation resolution unblocks execution.
- No ghost positions upon bottom position clearance.
- Rejection paths guarantee zero ghost positions and zero cash drift.
- No real broker connections or credentials.
"""

import copy
import time
import pytest

from ats.strategy.ipo_trading_center import (
    IPOTradingCenter,
    IPOTradingPosition,
    IPOOrderDirective,
)
from ats.strategy.signal_convergence import (
    converge_directives,
    check_exit_buy_contract,
    EXIT_ACTIONS,
    ENTRY_ACTIONS,
)
from ats.strategy.subnew_deployment_gate import (
    SubnewDeploymentGate,
    GateStatus,
    GateResult,
)
from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan


@pytest.fixture
def clean_center():
    """Create a fresh, isolated IPOTradingCenter instance with mock capital."""
    center = IPOTradingCenter(total_capital=1000000.0, auto_load_ledger=False)
    # Ensure empty state
    center._positions.clear()
    center._closed_positions.clear()
    center._order_history.clear()
    center._pending_directives.clear()
    center._signal_iteration_log.clear()
    center._execution_blocked_codes.clear()
    center._reconciliation_mismatches.clear()
    return center


# ── 1. EXIT > BUY Independent Blocking Contract Tests ──

def test_exit_overrides_buy_in_signal_convergence():
    """EXIT directives must physically suppress ENTRY directives for the same code in the same refresh."""
    directives = [
        IPOOrderDirective(
            action="BUY",
            code="000001",
            name="平安银行",
            price=10.0,
            shares=1000,
            signal_level="S5",
            signal_state="ACTIONABLE",
        ),
        IPOOrderDirective(
            action="SELL",
            code="000001",
            name="平安银行",
            price=10.0,
            shares=1000,
            urgency="CRITICAL",
        ),
        IPOOrderDirective(
            action="BUY",
            code="000002",
            name="万科A",
            price=8.0,
            shares=2000,
            signal_level="S5",
            signal_state="ACTIONABLE",
        ),
    ]

    # Raw input violates contract
    compliant, violations = check_exit_buy_contract(directives)
    assert not compliant
    assert any("000001" in v for v in violations)

    # Converged result physically strips BUY for 000001
    res = converge_directives(directives)
    assert res.exit_count == 1
    assert res.entry_count == 1
    assert "EXIT_OVERRIDES_ENTRY" in res.suppressed_reasons

    # Check that 000001 has only SELL, while 000002 has BUY
    codes_actions = {(d.code, d.action) for d in res.directives}
    assert ("000001", "SELL") in codes_actions
    assert ("000001", "BUY") not in codes_actions
    assert ("000002", "BUY") in codes_actions

    # Converged directives pass the contract
    ok, viols = check_exit_buy_contract(res.directives)
    assert ok
    assert len(viols) == 0


def test_exit_buy_blocking_contract_at_execution(clean_center):
    """Execution layer blocks BUY if there is a pending EXIT directive for the same code."""
    # Add pending EXIT directive for 000001
    clean_center._pending_directives.append(
        IPOOrderDirective(action="SELL", code="000001", name="平安银行", price=10.0, shares=1000)
    )

    buy_directive = IPOOrderDirective(
        action="BUY",
        code="000001",
        name="平安银行",
        price=10.0,
        shares=1000,
        signal_level="S5",
        signal_state="ACTIONABLE",
    )

    cash_before = clean_center.available_cash
    result = clean_center.execute_directive(buy_directive)

    assert result is False
    assert buy_directive.reject_code == "EXIT_BUY_CONFLICT"
    assert clean_center.available_cash == cash_before
    assert clean_center.get_position("000001") is None


# ── 2. T+1 Physical Isolation Tests ──

def test_t1_physical_lock_for_new_position_today(clean_center):
    """Newly bought shares today must have available_shares=0 and cannot be sold on the same day."""
    today_str = time.strftime("%Y-%m-%d")

    # Buy new shares today
    buy_dir = IPOOrderDirective(
        action="BUY",
        code="301001",
        name="次新股A",
        price=20.0,
        shares=1000,
        size_pct=10.0,
        timestamp=time.time(),
        signal_level="S5",
        signal_state="ACTIONABLE",
    )

    # Inject mock market context so buy execution can pass market checks
    from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot
    clean_center._last_market_context = MarketSentimentSnapshot(
        tide_state="T10_MAIN_UP",
        generated_at=time.time(),
        tide_position_cap_pct=80.0,
        position_multiplier=1.0,
        risk_mode="NORMAL",
    )

    executed = clean_center.record_order_execution(buy_dir)
    assert executed is True

    pos = clean_center.get_position("301001")
    assert pos is not None
    assert pos.shares == 1000
    assert pos.available_shares == 0  # T+1 physical lock: 0 sellable today
    assert pos.entry_date == today_str

    # Attempt to sell on the same day
    sell_dir = IPOOrderDirective(
        action="SELL",
        code="301001",
        name="次新股A",
        price=21.0,
        shares=1000,
    )
    sell_res = clean_center.record_order_execution(sell_dir)
    assert sell_res is False
    assert sell_dir.reject_code == "T1_SELL_LOCK"
    assert pos.shares == 1000
    assert pos.available_shares == 0

    # Attempt partial sell (REDUCE_HALF) on the same day
    reduce_dir = IPOOrderDirective(
        action="REDUCE_HALF",
        code="301001",
        name="次新股A",
        price=21.0,
        shares=500,
    )
    reduce_res = clean_center.record_order_execution(reduce_dir)
    assert reduce_res is False
    assert reduce_dir.reject_code == "T1_SELL_LOCK"
    assert pos.shares == 1000


def test_t1_cannot_be_bypassed_by_catastrophic_stop(clean_center):
    """Catastrophic stop-loss paths cannot bypass T+1 physical lock at execution time."""
    today_str = time.strftime("%Y-%m-%d")

    # Initialize position bought today
    clean_center._positions["301002"] = IPOTradingPosition(
        code="301002",
        name="次新股B",
        shares=1000,
        available_shares=0,  # Bought today
        cost_price=30.0,
        entry_date=today_str,
        status="HOLDING",
    )

    # Create catastrophic stop order with bypass_t1_lock flag
    hard_stop_dir = IPOOrderDirective(
        action="SELL",
        code="301002",
        name="次新股B",
        price=27.0,
        shares=1000,
        urgency="CRITICAL",
        exit_rule_id="exit_hard_stop",
        bypass_t1_lock=True,  # Attempted bypass
    )

    res = clean_center.record_order_execution(hard_stop_dir)
    assert res is False
    assert hard_stop_dir.reject_code == "T1_SELL_LOCK"

    pos = clean_center.get_position("301002")
    assert pos.shares == 1000
    assert pos.available_shares == 0

    # Test evaluate_position_exit also blocks when available_shares <= 0
    exit_directive = clean_center.evaluate_position_exit(
        code="301002",
        price=26.0,
        vwap_today=29.0,
        volume=50000,
    )
    assert exit_directive is None  # Blocked by available_shares <= 0


def test_t1_yesterday_shares_plus_today_additions(clean_center):
    """When yesterday's position is augmented today, only yesterday's shares are sellable."""
    # Yesterday position: 1000 shares, all sellable
    clean_center._positions["301003"] = IPOTradingPosition(
        code="301003",
        name="次新股C",
        shares=1000,
        available_shares=1000,
        cost_price=10.0,
        entry_date="2026-09-21",
        status="HOLDING",
    )

    # Buy 500 more shares today
    from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot
    clean_center._last_market_context = MarketSentimentSnapshot(
        tide_state="T10_MAIN_UP",
        generated_at=time.time(),
        tide_position_cap_pct=80.0,
        position_multiplier=1.0,
        risk_mode="NORMAL",
    )

    buy_more = IPOOrderDirective(
        action="BUY",
        code="301003",
        name="次新股C",
        price=10.0,
        shares=500,
        size_pct=5.0,
        timestamp=time.time(),
        signal_level="S5",
        signal_state="ACTIONABLE",
    )
    assert clean_center.record_order_execution(buy_more) is True

    pos = clean_center.get_position("301003")
    assert pos.shares == 1500
    assert pos.available_shares == 1000  # Added 500 shares must NOT increase available_shares

    # Sell 1500 shares: only 1000 can be sold
    sell_all = IPOOrderDirective(
        action="SELL",
        code="301003",
        name="次新股C",
        price=12.0,
        shares=1500,
    )
    cash_before = clean_center.available_cash
    assert clean_center.record_order_execution(sell_all) is True

    # Check cash increment is exactly for 1000 shares, not 1500
    assert clean_center.available_cash == cash_before + (1000 * 12.0)

    # Remaining 500 shares stay in holding, available_shares is 0
    pos_after = clean_center.get_position("301003")
    assert pos_after is not None
    assert pos_after.shares == 500
    assert pos_after.available_shares == 0
    assert pos_after.status == "HOLDING"

    # Further sell attempts today are rejected
    second_sell = IPOOrderDirective(action="SELL", code="301003", name="次新股C", price=12.0, shares=500)
    assert clean_center.record_order_execution(second_sell) is False
    assert second_sell.reject_code == "T1_SELL_LOCK"


# ── 3. Authoritative Reconciliation Blocking Contract Tests ──

def test_authoritative_reconciliation_conflict_blocks_bidirectional(clean_center):
    """Authoritative reconciliation mismatch puts code in EXECUTION_BLOCKED, blocking BUY and SELL."""
    # Setup local position: 1000 shares, 1000 sellable
    clean_center._positions["301004"] = IPOTradingPosition(
        code="301004",
        name="次新股D",
        shares=1000,
        available_shares=1000,
        cost_price=15.0,
        entry_date="2026-09-21",
        status="HOLDING",
    )

    # Input authoritative reconciliation with mismatch (broker has 800 shares, 800 sellable)
    report = clean_center.reconcile_authoritative_position(
        code="301004",
        shares=800,
        sellable_qty=800,
        reason="Broker statement mismatch test",
    )

    assert report["status"] == "EXECUTION_BLOCKED"
    assert report["is_blocked"] is True
    assert clean_center.is_execution_blocked("301004") is True

    mismatches = clean_center.get_reconciliation_mismatches()
    assert "301004" in mismatches
    assert mismatches["301004"]["shares_diff"] == -200

    cash_before = clean_center.available_cash
    pos_before = copy.deepcopy(clean_center.get_position("301004"))

    # BUY is blocked
    buy_dir = IPOOrderDirective(
        action="BUY", code="301004", name="次新股D", price=15.0, shares=500, signal_level="S5", signal_state="ACTIONABLE"
    )
    assert clean_center.record_order_execution(buy_dir) is False
    assert buy_dir.reject_code == "RECONCILIATION_BLOCKED"

    # SELL is blocked
    sell_dir = IPOOrderDirective(
        action="SELL", code="301004", name="次新股D", price=15.0, shares=500
    )
    assert clean_center.record_order_execution(sell_dir) is False
    assert sell_dir.reject_code == "RECONCILIATION_BLOCKED"

    # Zero cash drift, zero position mutation
    assert clean_center.available_cash == cash_before
    assert clean_center.get_position("301004").shares == pos_before.shares


def test_authoritative_reconciliation_resolution_restores_execution(clean_center):
    """Explicit reconciliation resolution unblocks execution."""
    clean_center._positions["301005"] = IPOTradingPosition(
        code="301005",
        name="次新股E",
        shares=500,
        available_shares=500,
        cost_price=20.0,
        entry_date="2026-09-21",
        status="HOLDING",
    )

    # Cause conflict
    clean_center.reconcile_authoritative_position("301005", shares=300, sellable_qty=300)
    assert clean_center.is_execution_blocked("301005") is True

    # Resolve conflict explicitly by accepting authoritative state
    resolved = clean_center.resolve_reconciliation("301005")
    assert resolved is True
    assert clean_center.is_execution_blocked("301005") is False

    pos = clean_center.get_position("301005")
    assert pos.shares == 300
    assert pos.available_shares == 300
    assert pos.status == "HOLDING"

    # Now SELL can execute
    sell_dir = IPOOrderDirective(
        action="SELL", code="301005", name="次新股E", price=22.0, shares=300
    )
    assert clean_center.record_order_execution(sell_dir) is True


def test_zero_ghost_positions_upon_position_clearance(clean_center):
    """When a position is fully cleared, it is deleted from _positions, leaving zero ghost positions."""
    clean_center._positions["301006"] = IPOTradingPosition(
        code="301006",
        name="次新股F",
        shares=500,
        available_shares=500,
        cost_price=10.0,
        entry_date="2026-09-21",
        status="HOLDING",
    )

    sell_all = IPOOrderDirective(
        action="SELL", code="301006", name="次新股F", price=11.0, shares=500
    )
    assert clean_center.record_order_execution(sell_all) is True

    # Must be deleted from active positions
    assert "301006" not in clean_center._positions
    assert clean_center.get_position("301006") is None

    # Appears in closed positions
    closed_codes = [
        p.code if hasattr(p, "code") else p.get("code")
        for p in clean_center.get_closed_positions()
    ]
    assert "301006" in closed_codes


def test_sellable_qty_not_deduced_from_trade_plan(clean_center):
    """sellable_qty is strictly an accounting / T+1 concept and cannot be deduced from TradePlan."""
    plan = IPOTradePlan(
        plan_id="TP_TEST_01",
        code="301007",
        name="次新股G",
        strategy_tag="TAG_CHANNEL_SECONDARY_BUY",
        signal_level="S4",
        quality_grade="S",
        trigger_price=15.0,
        suggested_action="BUY_CONFIRM",
        position_pct=30.0,
    )
    clean_center.register_trade_plan(plan)

    # Position without prior holding has available_shares=0
    pos = clean_center.get_position("301007")
    assert pos is None

    # Even if plan suggests 30% position, sellable shares are 0
    clean_center._positions["301007"] = IPOTradingPosition(
        code="301007",
        name="次新股G",
        shares=1000,
        available_shares=0,
        cost_price=15.0,
        trade_plan=plan,
        entry_date=time.strftime("%Y-%m-%d"),
    )
    p = clean_center.get_position("301007")
    assert p.available_shares == 0  # Not influenced by TradePlan


# ── 4. SubnewDeploymentGate Integration and One-Way Latch Tests ──

def test_deployment_gate_monitor_only_blocks_all_execution(clean_center):
    """When gate is MONITOR_ONLY, execute_directive, execute_all_pending_directives, and auto-follow block."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    clean_center.set_deployment_gate(gate)

    # Evaluate Gate 2 with a failure to latch MONITOR_ONLY
    res = gate.evaluate_gate2({
        "build_identity": True,
        "market_data_fresh": False,  # Stale data
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    })
    assert res.status == GateStatus.MONITOR_ONLY
    assert gate.is_latched() is True
    assert clean_center.current_gate_status() == GateStatus.MONITOR_ONLY

    # Prepare pending directive
    directive = IPOOrderDirective(
        action="BUY",
        code="301008",
        name="次新股H",
        price=10.0,
        shares=1000,
        signal_level="S5",
        signal_state="ACTIONABLE",
    )
    clean_center._pending_directives.append(directive)

    # 1. execute_directive is blocked
    executed = clean_center.execute_directive(directive)
    assert executed is False
    assert directive.reject_code == "GATE_MONITOR_ONLY"

    # 2. execute_all_pending_directives returns 0
    count = clean_center.execute_all_pending_directives()
    assert count == 0

    # 3. auto_follow does not execute
    clean_center.auto_follow_trading = True
    clean_center._auto_execute_if_enabled()
    assert clean_center.get_position("301008") is None

    # Gate downgrade must NOT swallow risk EXIT signals or iteration logs
    exit_directive = IPOOrderDirective(
        action="SELL", code="301008", name="次新股H", price=10.0, shares=1000
    )
    clean_center._pending_directives.append(exit_directive)
    pending = clean_center.get_pending_directives()
    assert any(d.action == "SELL" and d.code == "301008" for d in pending)
    # Log has recorded the rejection
    logs = clean_center.get_signal_iteration_log()
    assert any(item.get("reject_code") == "GATE_MONITOR_ONLY" for item in logs)


def test_deployment_gate_one_way_latch_same_day(clean_center):
    """Gate latched in MONITOR_ONLY will NEVER automatically return to CONFIRM on the same day."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")

    # First evaluation fails on market_data_fresh
    res1 = gate.evaluate_gate2({
        "build_identity": True,
        "market_data_fresh": False,
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    })
    assert res1.status == GateStatus.MONITOR_ONLY

    # Second evaluation has all checks pass, but latch prevents upgrade
    res2 = gate.evaluate_gate2({
        "build_identity": True,
        "market_data_fresh": True,  # Recovered
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    })
    assert res2.status == GateStatus.MONITOR_ONLY
    assert "DAY_LATCHED_MONITOR_ONLY" in res2.reject_codes

    # Only a new trading day reset can clear the latch
    gate.reset_for_trading_day("2026-09-23")
    assert gate.is_latched() is False

    res3 = gate.evaluate_gate2({
        "build_identity": True,
        "market_data_fresh": True,
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    })
    assert res3.status == GateStatus.CONFIRM


def test_gate2_auto_inspects_trading_center_reconciliation(clean_center):
    """Gate 2 evaluation auto-inspects trading center state for reconciliation mismatches."""
    # When no mismatches exist, account_reconciliation is true
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    res1 = gate.evaluate_gate2(
        trading_center=clean_center,
        build_identity=True,
        market_data_fresh=True,
        pending_directives_empty_at_boot=True,
        duplicate_plan_check=True,
        risk_execution_path=True,
    )
    assert res1.checks["account_reconciliation"] is True
    assert res1.checks["sellable_qty_reconciliation"] is True
    assert res1.status == GateStatus.CONFIRM

    # New day: introduce a reconciliation mismatch
    gate.reset_for_trading_day("2026-09-23")
    clean_center.reconcile_authoritative_position("301009", shares=1000, sellable_qty=1000)
    # Now local is 0, authoritative is 1000 -> mismatch
    assert clean_center.is_execution_blocked("301009") is True

    res2 = gate.evaluate_gate2(
        trading_center=clean_center,
        build_identity=True,
        market_data_fresh=True,
        pending_directives_empty_at_boot=True,
        duplicate_plan_check=True,
        risk_execution_path=True,
    )
    assert res2.checks["account_reconciliation"] is False
    assert res2.status == GateStatus.MONITOR_ONLY


def test_rejection_paths_zero_cash_drift_and_zero_ghost_positions(clean_center):
    """All rejection paths must strictly leave available_cash and positions unmodified."""
    init_cash = clean_center.available_cash
    init_positions = copy.deepcopy(clean_center._positions)
    init_closed = copy.deepcopy(clean_center._closed_positions)

    # 1. Invalid price rejection
    d1 = IPOOrderDirective(action="BUY", code="301010", name="测试", price=0.0, shares=100)
    assert clean_center.record_order_execution(d1) is False

    # 2. Reconciliation blocked rejection
    clean_center._execution_blocked_codes.add("301011")
    d2 = IPOOrderDirective(action="BUY", code="301011", name="测试", price=10.0, shares=100)
    assert clean_center.record_order_execution(d2) is False

    # 3. No position sell rejection
    d3 = IPOOrderDirective(action="SELL", code="301012", name="测试", price=10.0, shares=100)
    assert clean_center.record_order_execution(d3) is False

    # Verify zero cash drift, zero position mutation, zero ghost positions
    assert clean_center.available_cash == init_cash
    assert len(clean_center._positions) == len(init_positions)
    assert len(clean_center._closed_positions) == len(init_closed)


def test_t1_guard_runs_before_paper_kernel_route(clean_center, monkeypatch):
    """Persistent PAPER path must not reach kernel when T+1 physical lock rejects the sell."""
    import ats.unified_paper_account as paper_account

    clean_center._auto_load_ledger = True
    clean_center._positions["301099"] = IPOTradingPosition(
        code="301099",
        name="当日新仓",
        shares=1000,
        available_shares=0,
        cost_price=20.0,
        current_price=20.0,
        entry_date=time.strftime("%Y-%m-%d"),
        status="HOLDING",
    )

    calls = []

    def forbidden_kernel_call(directive):
        calls.append(directive)
        raise AssertionError("paper kernel must not be called before T+1 guard")

    monkeypatch.setattr(paper_account, "execute_command_directive", forbidden_kernel_call)

    sell = IPOOrderDirective(
        action="EXIT_ALL",
        code="301099",
        name="当日新仓",
        price=19.0,
        shares=1000,
        urgency="CRITICAL",
        bypass_t1_lock=True,
    )
    assert clean_center.record_order_execution(sell) is False
    assert sell.reject_code == "T1_SELL_LOCK"
    assert calls == []
    assert clean_center._positions["301099"].shares == 1000
    assert clean_center._positions["301099"].available_shares == 0


def test_market_risk_guard_runs_before_paper_kernel_route(clean_center, monkeypatch):
    """Absolute market risk block must reject a BUY before the PAPER adapter can see it."""
    import ats.unified_paper_account as paper_account
    from ats.strategy.ipo_market_sentiment_engine import MarketSentimentSnapshot

    clean_center._auto_load_ledger = True
    snap = MarketSentimentSnapshot(
        tide_state="T4_PANIC_ACCEL",
        generated_at=time.time(),
        tide_position_cap_pct=0.0,
        position_multiplier=0.0,
        risk_mode="BLOCK_NEW_BUYS",
    ).finalize()
    clean_center._last_market_context = snap

    calls = []

    def forbidden_kernel_call(directive):
        calls.append(directive)
        raise AssertionError("paper kernel must not be called before market risk guard")

    monkeypatch.setattr(paper_account, "execute_command_directive", forbidden_kernel_call)

    buy = IPOOrderDirective(
        action="BUY",
        code="301098",
        name="风险买入",
        price=20.0,
        shares=1000,
        size_pct=10.0,
        timestamp=time.time(),
        signal_level="S5",
        signal_state="ACTIONABLE",
    )
    assert clean_center.record_order_execution(buy) is False
    assert buy.reject_code == "MARKET_RISK_BLOCK"
    assert calls == []
    assert clean_center.get_position("301098") is None

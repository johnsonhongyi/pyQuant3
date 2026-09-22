"""
tests/test_subnew_deployment_gate.py
Unit tests for subnew deployment GO/NO-GO gate core.
"""

import json
from datetime import datetime, timezone
import pytest

from ats.strategy.subnew_deployment_gate import (
    GATE1_REQUIRED_CHECKS,
    GATE2_REQUIRED_CHECKS,
    GateResult,
    GateStatus,
    MarketFreshnessResult,
    SubnewDeploymentGate,
    check_market_data_fresh,
)


# ---------------------------------------------------------------------------
# Helper Fixtures & Data
# ---------------------------------------------------------------------------

@pytest.fixture
def base_gate1_checks():
    return {
        "build_identity": True,
        "account_reconciliation": True,
        "sellable_init": True,
        "pending_directives_empty_at_boot": True,
    }


@pytest.fixture
def base_gate2_checks():
    return {
        "build_identity": True,
        "market_data_fresh": True,
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    }


# ---------------------------------------------------------------------------
# Gate 1 Tests: All Green & Single Item Failure
# ---------------------------------------------------------------------------

def test_gate1_all_green(base_gate1_checks):
    """Gate 1 with all 4 required items True should return CONFIRM."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate1(base_gate1_checks)

    assert result.gate_name == "GATE1"
    assert result.trading_day == "2026-09-22"
    assert result.status == GateStatus.CONFIRM
    assert result.status == "CONFIRM"
    assert result.passed is True
    assert result.failed_checks == []
    assert result.reject_codes == []
    assert not gate.is_latched()
    assert gate.current_status() == GateStatus.CONFIRM


@pytest.mark.parametrize("failed_check", [
    "build_identity",
    "account_reconciliation",
    "sellable_init",
    "pending_directives_empty_at_boot",
])
def test_gate1_single_item_failure(base_gate1_checks, failed_check):
    """Any single check failing in Gate 1 must return MONITOR_ONLY and latch the day."""
    checks = dict(base_gate1_checks)
    checks[failed_check] = False

    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate1(checks)

    assert result.status == GateStatus.MONITOR_ONLY
    assert result.passed is False
    assert failed_check in result.failed_checks
    assert f"REJECT_{failed_check.upper()}" in result.reject_codes
    assert gate.is_latched()
    assert gate.current_status() == GateStatus.MONITOR_ONLY


def test_gate1_aliases_support():
    """Gate 1 accepts common alias names like sellable_qty_initialization or Chinese alias."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    checks = {
        "build_identity": True,
        "account_reconciliation": True,
        "sellable_qty_initialization": True,
        "pending_directives_boot_empty": True,
    }
    result = gate.evaluate_gate1(checks)
    assert result.status == GateStatus.CONFIRM
    assert result.passed is True


# ---------------------------------------------------------------------------
# Gate 2 Tests: All Green & 7/8 MONITOR_ONLY
# ---------------------------------------------------------------------------

def test_gate2_all_green_confirm(base_gate2_checks):
    """Gate 2 requires all fixed 8 items to be True to return CONFIRM."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate2(base_gate2_checks)

    assert result.gate_name == "GATE2"
    assert result.trading_day == "2026-09-22"
    assert result.status == GateStatus.CONFIRM
    assert result.passed is True
    assert result.failed_checks == []
    assert result.reject_codes == []
    assert not gate.is_latched()


@pytest.mark.parametrize("failing_item", GATE2_REQUIRED_CHECKS)
def test_gate2_seven_of_eight_must_be_monitor_only(base_gate2_checks, failing_item):
    """If exactly 7 of 8 items are True and 1 is False, status MUST be MONITOR_ONLY."""
    checks = dict(base_gate2_checks)
    checks[failing_item] = False

    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate2(checks)

    assert result.status == GateStatus.MONITOR_ONLY
    assert result.passed is False
    assert failing_item in result.failed_checks
    assert f"REJECT_{failing_item.upper()}" in result.reject_codes
    assert gate.is_latched()
    assert gate.current_status() == GateStatus.MONITOR_ONLY


def test_gate2_multiple_failures(base_gate2_checks):
    """Multiple failures in Gate 2 must all be reported in reject_codes and failed_checks."""
    checks = dict(base_gate2_checks)
    checks["market_data_fresh"] = False
    checks["duplicate_plan_check"] = False
    checks["risk_execution_path"] = False

    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate2(checks)

    assert result.status == GateStatus.MONITOR_ONLY
    assert result.passed is False
    assert set(result.failed_checks) == {
        "market_data_fresh",
        "duplicate_plan_check",
        "risk_execution_path",
    }
    assert "REJECT_MARKET_DATA_FRESH" in result.reject_codes
    assert "REJECT_DUPLICATE_PLAN_CHECK" in result.reject_codes
    assert "REJECT_RISK_EXECUTION_PATH" in result.reject_codes


def test_gate2_missing_item_treated_as_rejection(base_gate2_checks):
    """If an item is missing from provided checks, it is treated as False with MISSING code."""
    checks = dict(base_gate2_checks)
    del checks["EXIT_BUY_contract"]

    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate2(checks)

    assert result.status == GateStatus.MONITOR_ONLY
    assert result.passed is False
    assert "EXIT_BUY_contract" in result.failed_checks
    assert "MISSING_EXIT_BUY_CONTRACT" in result.reject_codes


# ---------------------------------------------------------------------------
# One-way Safety Latch Tests
# ---------------------------------------------------------------------------

def test_one_way_safety_latch_same_day(base_gate1_checks, base_gate2_checks):
    """
    Once degraded to MONITOR_ONLY on a trading day, subsequent evaluations on the
    same day NEVER automatically upgrade back to CONFIRM, even if 100% green.
    """
    gate = SubnewDeploymentGate(trading_day="2026-09-22")

    # Step 1: Gate 1 fails on account_reconciliation
    g1_failing = dict(base_gate1_checks)
    g1_failing["account_reconciliation"] = False
    r1 = gate.evaluate_gate1(g1_failing)
    assert r1.status == GateStatus.MONITOR_ONLY
    assert gate.is_latched() is True

    # Step 2: Gate 1 re-evaluated with all items True -> STILL MONITOR_ONLY
    r2 = gate.evaluate_gate1(base_gate1_checks)
    assert r2.status == GateStatus.MONITOR_ONLY
    assert r2.passed is False
    assert "DAY_LATCHED_MONITOR_ONLY" in r2.reject_codes

    # Step 3: Gate 2 evaluated with 8/8 all green -> STILL MONITOR_ONLY
    r3 = gate.evaluate_gate2(base_gate2_checks)
    assert r3.status == GateStatus.MONITOR_ONLY
    assert r3.passed is False
    assert "DAY_LATCHED_MONITOR_ONLY" in r3.reject_codes
    assert gate.is_latched() is True


def test_reset_for_new_trading_day(base_gate2_checks):
    """
    Explicit call to reset_for_trading_day releases previous day latch and allows
    evaluating CONFIRM for the new day.
    """
    gate = SubnewDeploymentGate(trading_day="2026-09-22")

    # Degrade on day 2026-09-22
    checks_bad = dict(base_gate2_checks)
    checks_bad["market_data_fresh"] = False
    r_bad = gate.evaluate_gate2(checks_bad)
    assert r_bad.status == GateStatus.MONITOR_ONLY
    assert gate.is_latched() is True

    # Reset for next day: 2026-09-23
    gate.reset_for_trading_day("2026-09-23")
    assert gate.is_latched() is False
    assert gate.trading_day == "2026-09-23"
    assert gate.current_status() == GateStatus.CONFIRM

    # Evaluate on new day with all green -> CONFIRM
    r_new = gate.evaluate_gate2(base_gate2_checks)
    assert r_new.status == GateStatus.CONFIRM
    assert r_new.passed is True
    assert r_new.trading_day == "2026-09-23"


# ---------------------------------------------------------------------------
# Market Data Freshness Boundary Tests (<= 3s semantics)
# ---------------------------------------------------------------------------

def test_market_data_freshness_boundaries():
    """Verify market data freshness <= 3s boundary semantics."""
    now = 1000.0

    # 0.0s elapsed -> Fresh
    res_0s = check_market_data_fresh(market_time=1000.0, current_time=now)
    assert res_0s.is_fresh is True
    assert res_0s.staleness_seconds == 0.0

    # 1.5s elapsed -> Fresh
    res_1_5s = check_market_data_fresh(market_time=998.5, current_time=now)
    assert res_1_5s.is_fresh is True
    assert pytest.approx(res_1_5s.staleness_seconds, 1e-4) == 1.5

    # 3.0s elapsed -> Fresh (exact boundary: <= 3.0s is True)
    res_3s = check_market_data_fresh(market_time=997.0, current_time=now)
    assert res_3s.is_fresh is True
    assert pytest.approx(res_3s.staleness_seconds, 1e-4) == 3.0

    # 3.001s elapsed -> Stale (> 3.0s is False)
    res_3_001s = check_market_data_fresh(market_time=996.999, current_time=now)
    assert res_3_001s.is_fresh is False
    assert res_3_001s.staleness_seconds > 3.0

    # 5.0s elapsed -> Stale
    res_5s = check_market_data_fresh(market_time=995.0, current_time=now)
    assert res_5s.is_fresh is False
    assert "stale" in res_5s.reason.lower()

    # Slight future skew within 0.5s tolerance -> Fresh
    res_skew = check_market_data_fresh(market_time=1000.2, current_time=now)
    assert res_skew.is_fresh is True

    # Significant future skew (>0.5s) -> False
    res_fut = check_market_data_fresh(market_time=1001.0, current_time=now)
    assert res_fut.is_fresh is False
    assert "future" in res_fut.reason.lower()


def test_market_data_freshness_datetime_and_iso_inputs():
    """Verify ISO strings and datetime objects are properly parsed."""
    c_dt = datetime(2026, 9, 22, 9, 25, 0, tzinfo=timezone.utc)
    m_dt_fresh = datetime(2026, 9, 22, 9, 24, 58, tzinfo=timezone.utc)
    m_dt_stale = datetime(2026, 9, 22, 9, 24, 55, tzinfo=timezone.utc)

    # Datetime inputs
    res_fresh = check_market_data_fresh(m_dt_fresh, current_time=c_dt)
    assert res_fresh.is_fresh is True
    assert pytest.approx(res_fresh.staleness_seconds, 1e-4) == 2.0

    res_stale = check_market_data_fresh(m_dt_stale, current_time=c_dt)
    assert res_stale.is_fresh is False
    assert pytest.approx(res_stale.staleness_seconds, 1e-4) == 5.0

    # ISO string inputs
    res_iso_fresh = check_market_data_fresh(
        market_time="2026-09-22T09:24:57.500+00:00",
        current_time="2026-09-22T09:25:00.000+00:00",
    )
    assert res_iso_fresh.is_fresh is True
    assert pytest.approx(res_iso_fresh.staleness_seconds, 1e-4) == 2.5


def test_gate2_auto_market_time_computation(base_gate2_checks):
    """evaluate_gate2 can compute market_data_fresh automatically if market_time is given."""
    gate = SubnewDeploymentGate(
        trading_day="2026-09-22",
        clock=lambda: 1000.0,
    )
    checks_without_mdf = dict(base_gate2_checks)
    del checks_without_mdf["market_data_fresh"]

    # Passing market_time=998.0 (staleness 2s <= 3s) -> CONFIRM
    r1 = gate.evaluate_gate2(checks_without_mdf, market_time=998.0)
    assert r1.status == GateStatus.CONFIRM
    assert r1.passed is True
    assert r1.checks["market_data_fresh"] is True

    # New gate instance: passing market_time=996.0 (staleness 4s > 3s) -> MONITOR_ONLY
    gate2 = SubnewDeploymentGate(
        trading_day="2026-09-22",
        clock=lambda: 1000.0,
    )
    r2 = gate2.evaluate_gate2(checks_without_mdf, market_time=996.0)
    assert r2.status == GateStatus.MONITOR_ONLY
    assert r2.passed is False
    assert r2.checks["market_data_fresh"] is False
    assert "REJECT_MARKET_DATA_FRESH" in r2.reject_codes


# ---------------------------------------------------------------------------
# Clock Injection & Determinism
# ---------------------------------------------------------------------------

def test_clock_injection_determinism(base_gate1_checks):
    """Injected clock produces exact deterministic timestamps."""
    fixed_time = datetime(2026, 9, 22, 9, 15, 0, tzinfo=timezone.utc)
    gate = SubnewDeploymentGate(
        trading_day="2026-09-22",
        clock=lambda: fixed_time,
    )
    result = gate.evaluate_gate1(base_gate1_checks)

    assert result.evaluated_at == fixed_time.isoformat()


# ---------------------------------------------------------------------------
# Serialization & History
# ---------------------------------------------------------------------------

def test_result_to_dict_and_json_serializable(base_gate2_checks):
    """GateResult.to_dict() must return JSON-serializable dictionary with all required fields."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    result = gate.evaluate_gate2(base_gate2_checks)

    d = result.to_dict()
    assert d["gate_name"] == "GATE2"
    assert d["trading_day"] == "2026-09-22"
    assert d["status"] == "CONFIRM"
    assert d["passed"] is True
    assert isinstance(d["evaluated_at"], str)
    assert isinstance(d["checks"], dict)
    assert len(d["checks"]) == 8
    assert isinstance(d["failed_checks"], list)
    assert isinstance(d["reject_codes"], list)
    assert isinstance(d["details"], dict)

    # Must serialize with json.dumps without error
    serialized = json.dumps(d)
    deserialized = json.loads(serialized)
    assert deserialized["status"] == "CONFIRM"
    assert deserialized["passed"] is True


def test_history_tracking(base_gate1_checks, base_gate2_checks):
    """Gate keeps track of evaluation history."""
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    r1 = gate.evaluate_gate1(base_gate1_checks)
    r2 = gate.evaluate_gate2(base_gate2_checks)

    history = gate.get_history()
    assert len(history) == 2
    assert history[0].gate_name == "GATE1"
    assert history[1].gate_name == "GATE2"

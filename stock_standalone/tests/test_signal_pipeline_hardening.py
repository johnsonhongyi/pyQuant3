# -*- coding: utf-8 -*-
from datetime import datetime
from types import SimpleNamespace

from ats.candidate_cache import CandidateCache
from ats.ledger_update_service import LedgerUpdateService
from ats.replay_release_gate import ReplayReleaseGate
from ats.session_snapshot import SessionSnapshot
from ats.signal_lifecycle import LifecycleEvent, LifecycleState, SignalLifecycle
from ats.strategy.signal_convergence import (
    get_directive_arbitrator,
    converge_directives,
)
from ats.strategy.subnew_deployment_gate import GateStatus, SubnewDeploymentGate


class _FakeEntry:
    def __init__(self):
        self.tdx_label = ""
        self.tdx_price = 0.0
        self.tdx_time_str = ""
        self.signal_tag = ""
        self.tdx_boost = 0.0
        self.promotions = []

    def promote(self, tier, reason=""):
        self.promotions.append((tier, reason))


class _FakeLedger:
    def __init__(self):
        self.calls = []
        self.entry = _FakeEntry()

    def record_signal(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.entry


def _directive(action, code="000001", **kwargs):
    base = {
        "action": action,
        "code": code,
        "urgency": kwargs.pop("urgency", "NORMAL"),
        "horse_rank": kwargs.pop("horse_rank", 999),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_candidate_cache_isolates_premarket_seed_and_confirms_consecutive_frames():
    cache = CandidateCache(required_frames=2, max_gap_seconds=8.0)

    seed = cache.observe(
        "1",
        source="ATS",
        payload={"price": 10.0},
        observed_at=datetime(2026, 9, 22, 9, 20, 0),
    )
    assert seed.code == "000001"
    assert seed.seed_only is True
    assert seed.eligible is False
    assert cache.snapshot()["active_candidates"] == {}
    assert "ATS:000001" in cache.snapshot()["premarket_seeds"]

    first = cache.observe(
        "000001",
        source="ATS",
        payload={"price": 10.1},
        observed_at=datetime(2026, 9, 22, 9, 31, 0),
    )
    assert first.seed_only is False
    assert first.eligible is False
    assert first.consecutive_frames == 1

    second = cache.observe(
        "000001",
        source="ATS",
        payload={"price": 10.2},
        observed_at=datetime(2026, 9, 22, 9, 31, 3),
    )
    assert second.eligible is True
    assert second.consecutive_frames == 2
    assert second.seed_payload == {"price": 10.0}


def test_ledger_update_service_is_single_write_gate_and_preserves_source():
    ledger = _FakeLedger()
    service = LedgerUpdateService(
        ledger,
        CandidateCache(required_frames=2, max_gap_seconds=8.0),
    )

    seed = service.update_candidate(
        code="300058", name="蓝色光标", price=13.0, pct=1.0, deviation=0.2,
        source="FAVORITE",
        observed_at=datetime(2026, 9, 22, 9, 20, 0),
    )
    assert seed.wrote_ledger is False
    assert ledger.calls == []

    one = service.update_candidate(
        code="300058", name="蓝色光标", price=13.1, pct=1.2, deviation=0.3,
        source="FAVORITE",
        observed_at=datetime(2026, 9, 22, 9, 31, 0),
    )
    assert one.wrote_ledger is False

    two = service.update_candidate(
        code="300058", name="蓝色光标", price=13.2, pct=1.5, deviation=0.4,
        source="FAVORITE",
        observed_at=datetime(2026, 9, 22, 9, 31, 2),
    )
    assert two.wrote_ledger is True
    assert len(ledger.calls) == 1
    assert ledger.calls[0]["signal_source"] == "FAVORITE"


def test_tdx_uses_same_service_but_external_event_requires_only_one_active_frame():
    ledger = _FakeLedger()
    service = LedgerUpdateService(ledger)
    result = service.update_tdx(
        {
            "code": "600000",
            "name": "浦发银行",
            "price": 10.5,
            "flag_label": "5上10",
            "direction_cn": "买入",
            "period_cn": "5m",
            "time_str": "09:31:01",
        },
        row={"percent": 1.2, "dff": 0.5},
        observed_at=datetime(2026, 9, 22, 9, 31, 1),
    )
    assert result.wrote_ledger is True
    assert len(ledger.calls) == 1
    assert ledger.calls[0]["signal_source"] == "TDX"
    assert ledger.entry.tdx_boost == 150.0
    assert ledger.entry.promotions and ledger.entry.promotions[-1][0] == "WATCH"


def test_signal_lifecycle_blocks_same_tick_weakened_direct_revival():
    lifecycle = SignalLifecycle(LifecycleState.WATCH)
    lifecycle.transition(
        LifecycleEvent.PEAK_DRAWDOWN,
        LifecycleState.WEAKENED,
        reason="drawdown",
    )
    try:
        lifecycle.transition(
            LifecycleEvent.STRUCTURE_GAINED,
            LifecycleState.WATCH,
            reason="same tick",
        )
    except ValueError as exc:
        assert "cannot revive directly" in str(exc)
    else:
        raise AssertionError("WEAKENED must not directly revive to WATCH")


def test_directive_arbitrator_is_unique_and_exit_overrides_buy():
    arb = get_directive_arbitrator()
    assert arb is get_directive_arbitrator()
    result = arb.arbitrate([
        _directive("BUY", code="000001"),
        _directive("EXIT_ALL", code="000001", urgency="CRITICAL"),
        _directive("BUY", code="000002"),
    ])
    actions = {(d.code, d.action) for d in result.directives}
    assert ("000001", "EXIT_ALL") in actions
    assert ("000001", "BUY") not in actions
    assert ("000002", "BUY") in actions
    # compatibility facade must use the same authority
    assert converge_directives([_directive("SELL")]).exit_count == 1


def test_session_snapshot_v2_migrates_v1_and_rejects_corrupt_v2(tmp_path):
    snap = SessionSnapshot(log_dir=str(tmp_path))
    v1 = {
        "date": "2026-09-22",
        "entries": {"000001": {"tier": "WATCH"}},
    }
    migrated = snap.migrate_snapshot_v2(v1)
    assert migrated["snapshot_version"] == 2
    assert migrated["schema"] == "ats.signal_ledger"
    assert migrated["integrity"]["entry_count"] == 1
    assert migrated["migration"]["mode"] == "FAIL_CLOSED"

    corrupt = {
        "snapshot_version": 2,
        "schema": "ats.signal_ledger",
        "entries": {"000001": {"tier": "WATCH"}},
        "integrity": {"entry_count": 2, "fail_closed": True},
    }
    assert snap.migrate_snapshot_v2(corrupt) is None
    assert snap.migrate_snapshot_v2({"snapshot_version": 99, "entries": {}}) is None


def test_replay_release_gate_all_green_and_hard_failures(tmp_path):
    gate = ReplayReleaseGate()
    read_model = {
        "reconciliation": {"status": "ALIGNED"},
        "positions": {
            "000001": {
                "total_qty": 100,
                "sellable_qty": 60,
                "today_buy_qty": 40,
            }
        },
    }
    frames = [
        {
            "event_key": "2026-09-22|000001|S4|ATS",
            "timestamp": "2026-09-22T09:31:00",
            "code": "000001",
            "price": 10.0,
        },
        {
            "event_key": "2026-09-22|000002|S4|ATS",
            "timestamp": "2026-09-22T09:31:01",
            "code": "000002",
            "price": 20.0,
        },
    ]
    ok = gate.evaluate(
        frames=frames,
        directives=[_directive("BUY", code="000002")],
        read_model=read_model,
        expected_build="abc",
        actual_build="abc",
    )
    assert ok.passed is True
    assert all(ok.checks.values())

    path = tmp_path / "morning_replay.json"
    gate.freeze_frames(frames, str(path))
    assert gate.load_frozen_frames(str(path)) == frames

    bad = gate.evaluate(
        frames=frames + [dict(frames[0], price=0.0)],
        directives=[
            _directive("BUY", code="000001"),
            _directive("SELL", code="000001"),
        ],
        read_model={
            "reconciliation": {"status": "LEGACY_MISMATCH"},
            "positions": {"000001": {"total_qty": 100, "sellable_qty": 120, "today_buy_qty": 0}},
        },
        expected_build="abc",
        actual_build="def",
    )
    assert bad.passed is False
    assert bad.checks["duplicate_rate_zero"] is False
    assert bad.checks["zero_price_zero"] is False
    assert bad.checks["EXIT_BUY_contract"] is False
    assert bad.checks["account_reconciliation"] is False
    assert bad.checks["t1_position_facts"] is False
    assert bad.checks["build_identity"] is False


def test_gate2_replay_result_is_hard_veto_and_latches_monitor_only():
    gate = SubnewDeploymentGate(trading_day="2026-09-22")
    replay_fail = {
        "passed": False,
        "checks": {"build_identity": True},
        "details": {"reason": "replay failed"},
    }
    checks = {
        "build_identity": True,
        "market_data_fresh": True,
        "account_reconciliation": True,
        "sellable_qty_reconciliation": True,
        "pending_directives_empty_at_boot": True,
        "duplicate_plan_check": True,
        "EXIT_BUY_contract": True,
        "risk_execution_path": True,
    }
    result = gate.evaluate_gate2(checks, replay_release_result=replay_fail)
    assert result.status == GateStatus.MONITOR_ONLY
    assert result.passed is False
    assert result.checks["risk_execution_path"] is False
    assert gate.latched_monitor_only is True


def test_tdx_premarket_is_seed_only_and_never_writes_ledger():
    ledger = _FakeLedger()
    service = LedgerUpdateService(ledger)
    result = service.update_tdx(
        {
            "code": "600000",
            "name": "浦发银行",
            "price": 10.5,
            "flag_label": "5上10",
            "direction_cn": "买入",
        },
        row={"percent": 1.2, "dff": 0.5},
        observed_at=datetime(2026, 9, 22, 9, 20, 0),
    )
    assert result.wrote_ledger is False
    assert result.decision.seed_only is True
    assert ledger.calls == []


def test_replay_release_gate_rejects_overallocated_t1_facts():
    result = ReplayReleaseGate().evaluate(
        frames=[],
        directives=[],
        read_model={
            "reconciliation": {"status": "ALIGNED"},
            "positions": {
                "000001": {"total_qty": 100, "sellable_qty": 70, "today_buy_qty": 40}
            },
        },
    )
    assert result.passed is False
    assert result.checks["t1_position_facts"] is False
    assert "000001:T1_FACTS_OVERALLOCATED" in result.details["t1_violations"]

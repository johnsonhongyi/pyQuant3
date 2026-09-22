# -*- coding: utf-8 -*-
"""P1 Hardening Tests: SignalLedger single-entry physical convergence and bypass prevention."""

from datetime import datetime
import pytest

from ats.candidate_cache import CandidateCache
from ats.ledger_update_service import LedgerUpdateService, get_ledger_update_service
from ats.signal_ledger import SignalLedger, get_signal_ledger


def test_signal_ledger_has_bound_update_service():
    ledger = SignalLedger()
    service = ledger.get_update_service()
    assert isinstance(service, LedgerUpdateService)
    assert service.signal_ledger is ledger
    # Idempotent access
    assert ledger.get_update_service() is service


def test_get_ledger_update_service_singleton_matches_signal_ledger():
    global_ledger = get_signal_ledger()
    global_service = get_ledger_update_service()
    assert isinstance(global_service, LedgerUpdateService)
    assert global_service.signal_ledger is global_ledger


def test_direct_record_signal_bypass_is_intercepted_and_premarket_seed_isolated():
    ledger = SignalLedger()
    # Premarket observation at 09:20:00 (HH:MM:SS string auto-coerced)
    entry = ledger.record_signal(
        code="000001",
        name="平安银行",
        price=10.0,
        pct=0.5,
        deviation=0.2,
        observed_at="09:20:00",
    )
    # Gated by CandidateCache: premarket observation must be isolated as seed only
    assert entry is None
    assert "000001" not in ledger.entries
    assert len(ledger.entries) == 0


def test_direct_record_signal_enforces_consecutive_frame_confirmation():
    ledger = SignalLedger()
    # First intraday frame at 09:31:00
    entry1 = ledger.record_signal(
        code="600519",
        name="贵州茅台",
        price=1600.0,
        pct=1.2,
        deviation=1.0,
        observed_at="09:31:00",
    )
    # Requires 2 consecutive frames by default
    assert entry1 is None
    assert "600519" not in ledger.entries

    # Second intraday frame at 09:31:03
    entry2 = ledger.record_signal(
        code="600519",
        name="贵州茅台",
        price=1602.0,
        pct=1.3,
        deviation=1.1,
        observed_at="09:31:03",
    )
    assert entry2 is not None
    assert "600519" in ledger.entries
    assert ledger.entries["600519"].latest_price == 1602.0


def test_record_signal_internal_allows_authorized_service_writes():
    ledger = SignalLedger()
    # Authorized write from service with _from_service=True
    entry = ledger.record_signal(
        code="000002",
        name="万科A",
        price=9.5,
        pct=1.0,
        deviation=0.5,
        _from_service=True,
    )
    assert entry is not None
    assert "000002" in ledger.entries
    assert ledger.entries["000002"].latest_price == 9.5


def test_record_tdx_signal_bypass_reroutes_to_update_tdx():
    ledger = SignalLedger()
    sig_dict = {
        "code": "300750",
        "name": "宁德时代",
        "price": 250.0,
        "flag_label": "5上10",
        "direction_cn": "买入",
        "period_cn": "5m",
        "time_str": "09:31:10",
    }
    # Direct bypass call
    entry = ledger.record_tdx_signal(sig_dict, row={"percent": 2.5, "dff": 1.2})
    assert entry is not None
    assert "300750" in ledger.entries
    assert entry.signal_source == "TDX"
    assert entry.tdx_boost == 150.0
    assert entry.tier == "WATCH"


def test_tick_time_auto_extraction_from_row():
    ledger = SignalLedger()
    service = ledger.get_update_service()

    # Provide time in row dict
    row_with_tick = {
        "percent": 1.5,
        "dff": 0.8,
        "tick_time": "09:32:00",
    }
    # Frame 1
    res1 = service.update_candidate(
        code="002475",
        name="立讯精密",
        price=32.0,
        pct=1.5,
        deviation=0.8,
        row=row_with_tick,
    )
    assert res1.wrote_ledger is False

    # Frame 2 with time_str
    row_with_time_str = {
        "percent": 1.8,
        "dff": 1.0,
        "time_str": "09:32:03",
    }
    res2 = service.update_candidate(
        code="002475",
        name="立讯精密",
        price=32.2,
        pct=1.8,
        deviation=1.0,
        row=row_with_time_str,
    )
    assert res2.wrote_ledger is True
    assert res2.entry is not None
    assert "002475" in ledger.entries

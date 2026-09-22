# -*- coding: utf-8 -*-
"""T+1 sellable quantity safety at the TK SSOT synchronization boundary."""

import datetime

from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOTradingPosition


def _persistent_center() -> IPOTradingCenter:
    center = IPOTradingCenter(auto_load_ledger=False)
    center._auto_load_ledger = True
    return center


def test_empty_ssot_does_not_erase_nonempty_local_position(monkeypatch):
    center = _persistent_center()
    center._positions["688836"] = IPOTradingPosition(
        code="688836", name="测试持仓", shares=500, available_shares=300,
        cost_price=10.0, current_price=10.2, status="HOLDING",
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.get_ssot_read_model",
        lambda: {"positions": {}, "account": {}},
    )

    center._sync_from_unified_paper_account()

    assert center._positions["688836"].shares == 500
    assert center._positions["688836"].available_shares == 300
    assert center._paper_reconciliation["status"] == "SSOT_EMPTY_LOCAL_NONEMPTY"


def test_ssot_without_sellable_never_unlocks_same_day_position(monkeypatch):
    today = datetime.date.today().isoformat()
    center = _persistent_center()
    center._positions["601091"] = IPOTradingPosition(
        code="601091", name="当日仓", shares=500, available_shares=0,
        cost_price=50.0, current_price=80.0, entry_date=today, status="HOLDING",
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.get_ssot_read_model",
        lambda: {
            "positions": {
                "601091": {
                    "volume": 500,
                    "entry_price": 50.0,
                    "current_price": 80.0,
                    "entry_time": f"{today}T09:31:00",
                }
            },
            "account": {"initial_capital": 1_000_000, "cash": 975_000},
            "orders": [],
        },
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.reconcile_account",
        lambda read_model: {"status": "ALIGNED"},
    )

    center._sync_from_unified_paper_account()

    assert center._positions["601091"].shares == 500
    assert center._positions["601091"].available_shares == 0


def test_ssot_explicit_sellable_is_clamped_to_total_shares(monkeypatch):
    center = _persistent_center()
    monkeypatch.setattr(
        "ats.unified_paper_account.get_ssot_read_model",
        lambda: {
            "positions": {
                "300001": {
                    "volume": 500,
                    "sellable_qty": 900,
                    "entry_price": 10.0,
                    "current_price": 10.5,
                    "entry_time": "2026-09-21T09:31:00",
                }
            },
            "account": {"initial_capital": 1_000_000, "cash": 995_000},
            "orders": [],
        },
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.reconcile_account",
        lambda read_model: {"status": "ALIGNED"},
    )

    center._sync_from_unified_paper_account()

    assert center._positions["300001"].available_shares == 500


def test_ssot_missing_sellable_preserves_partial_reconciled_quantity(monkeypatch):
    """An incomplete SSOT row must not silently unlock the remaining lot."""
    center = _persistent_center()
    center._positions["300002"] = IPOTradingPosition(
        code="300002", name="部分可卖", shares=500, available_shares=200,
        cost_price=10.0, current_price=10.5, entry_date="2026-09-21",
        status="HOLDING",
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.get_ssot_read_model",
        lambda: {
            "positions": {
                "300002": {
                    "volume": 500,
                    "entry_price": 10.0,
                    "current_price": 10.5,
                    "entry_time": "2026-09-21T09:31:00",
                }
            },
            "account": {"initial_capital": 1_000_000, "cash": 995_000},
            "orders": [],
        },
    )
    monkeypatch.setattr(
        "ats.unified_paper_account.reconcile_account",
        lambda read_model: {"status": "ALIGNED"},
    )

    center._sync_from_unified_paper_account()

    assert center._positions["300002"].shares == 500
    assert center._positions["300002"].available_shares == 200

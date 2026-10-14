from datetime import datetime
from types import SimpleNamespace

import pytest

from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
from trading_kernel.execution.paper_fees import paper_fee
from tools.run_shadow_live_test import _fresh_signal


def order(key, action, price=10, size=0.1):
    return ApprovedOrder(order_id=key, code="600000", action=action, size_pct=size,
                         price=price, stop_price=9)


def test_fee_policy():
    assert paper_fee(10000, "BUY") == 0.75
    assert paper_fee(10000, "SELL") == 5.75
    assert paper_fee(11000, "REDUCE") == 5.83


def test_fee_cash_roundtrip_and_idempotency(tmp_path, monkeypatch):
    adapter = PaperExecutionAdapter(initial_capital=100000, state_file_path=str(tmp_path / "state.json"),
                                    commission_rate=0.0000754, sell_extra_fee=5)
    monkeypatch.setattr("trading_kernel.engine.reentry_tracker.reentry_tracker.register_exit", lambda *a: None)
    buy = order("buy", "BUY")
    assert adapter.submit_order(buy)
    assert adapter.account.cash == pytest.approx(89999.25)
    assert adapter.submit_order(buy)
    assert len(adapter.orders) == 1
    sell = order("sell", "SELL", 11, 1)
    assert adapter.submit_order(sell)
    assert adapter.account.cash == pytest.approx(100993.42)
    assert adapter.get_account_snapshot()["fees_paid"] == 6.58
    positions, cash, errors = adapter._replay_order_ledger(adapter.orders, 100000)
    assert not positions and not errors
    assert cash == pytest.approx(adapter.account.cash)
    from ats.unified_paper_account import pair_closed_trades
    closed = pair_closed_trades(adapter.orders)
    assert sum(trade.profit for trade in closed) == pytest.approx(993.42)


def test_fees_respect_available_cash(tmp_path):
    adapter = PaperExecutionAdapter(initial_capital=10000, state_file_path=str(tmp_path / "state.json"),
                                    commission_rate=0.0000754, sell_extra_fee=5)
    assert adapter.submit_order(order("all", "BUY", size=1))
    assert adapter.account.cash >= 0


def test_fee_state_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    adapter = PaperExecutionAdapter(initial_capital=100000, state_file_path=str(path),
                                    commission_rate=0.0000754, sell_extra_fee=5)
    assert adapter.submit_order(order("buy", "BUY"))
    adapter._is_test = False
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    adapter._save_state()
    restored = PaperExecutionAdapter(state_file_path=str(path), commission_rate=0.0000754, sell_extra_fee=5)
    assert restored.get_restore_status()["ready"]
    assert restored.account.cash == pytest.approx(89999.25)
    assert restored.orders[0]["fee"] == 0.75
    assert restored.submit_order(order("buy", "BUY"))
    assert len(restored.orders) == 1
    wrong_policy = PaperExecutionAdapter(state_file_path=str(path))
    assert not wrong_policy.get_restore_status()["ready"]


@pytest.mark.parametrize("stamp", ["", "2026-10-13T10:00:00", "2026-10-14T10:01:00", "2026-10-14T09:54:59"])
def test_stale_or_future_signals_blocked(stamp):
    signal = SimpleNamespace(extra_data={"ipo_source_bar_as_of": stamp})
    assert not _fresh_signal(signal, datetime(2026, 10, 14, 10))


def test_fresh_source_bar_accepted():
    signal = SimpleNamespace(extra_data={"ipo_source_bar_as_of": "2026-10-14T09:59:00"})
    assert _fresh_signal(signal, datetime(2026, 10, 14, 10))


def test_concurrent_retry_only_fills_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    adapter = PaperExecutionAdapter(state_file_path=str(tmp_path / "state.json"),
                                    commission_rate=0.0000754, sell_extra_fee=5)
    buy = order("same", "BUY")
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(adapter.submit_order, [buy] * 8))
    assert len(adapter.orders) == 1


def test_automatic_orders_enforce_t1(tmp_path, monkeypatch):
    adapter = PaperExecutionAdapter(state_file_path=str(tmp_path / "state.json"),
                                    commission_rate=0.0000754, sell_extra_fee=5)
    adapter._is_test = False
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr("sys_utils.is_active_trading_hours", lambda **k: True)
    assert adapter.submit_order(order("buy", "BUY"))
    cash = adapter.account.cash
    assert not adapter.submit_order(order("sell", "SELL", size=1))
    assert adapter.account.cash == cash
    assert len(adapter.orders) == 1


def test_failed_persistence_blocks_followup(tmp_path, monkeypatch):
    adapter = PaperExecutionAdapter(state_file_path=str(tmp_path / "state.json"))
    adapter._is_test = False
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr("sys_utils.is_active_trading_hours", lambda **k: True)
    monkeypatch.setattr(adapter, "_save_state", lambda: None)
    assert not adapter.submit_order(order("buy", "BUY"))
    assert adapter.get_restore_status()["block_reason"] == "PAPER_PERSISTENCE_UNCONFIRMED"
    assert not adapter.submit_order(order("buy2", "BUY"))

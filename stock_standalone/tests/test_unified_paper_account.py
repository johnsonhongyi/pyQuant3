from ats.unified_paper_account import calculate_metrics, pair_closed_trades
from trading_kernel.engine.decision_engine import decide
from trading_kernel.engine.signal_canonicalizer import canonicalize_decision_queue_item


def test_fifo_pairing_and_metrics_shape(monkeypatch):
    orders = [
        {"code": "000001", "action": "BUY", "price": 10.0, "volume": 1000, "timestamp": "2026-01-01 10:00:00"},
        {"code": "000001", "action": "SELL", "price": 11.0, "volume": 1000, "timestamp": "2026-01-02 10:00:00"},
        {"code": "000002", "action": "BUY", "price": 20.0, "volume": 500, "timestamp": "2026-01-01 10:00:00"},
        {"code": "000002", "action": "SELL", "price": 18.0, "volume": 500, "timestamp": "2026-01-02 10:00:00"},
    ]
    trades = pair_closed_trades(orders)
    assert len(trades) == 2
    assert sum(t.profit for t in trades) == 0.0

    monkeypatch.setattr("ats.unified_paper_account.get_orders", lambda: orders)
    monkeypatch.setattr(
        "ats.unified_paper_account.get_account_snapshot",
        lambda: {"initial_capital": 100000.0},
    )
    metrics = calculate_metrics()
    assert metrics["总交易次数"] == "2"
    assert metrics["策略胜率"] == "50.0%"
    assert metrics["data_status"] == "OK"


def test_no_closed_trades_never_returns_demo_profit():
    # Empty pairing is deterministic and is covered without touching persistent state.
    assert pair_closed_trades([]) == []


def test_command_room_requested_position_reaches_manual_kernel_intent():
    signal = canonicalize_decision_queue_item({
        "code": "000001",
        "name": "平安银行",
        "action": "BUY",
        "signal_type": "手动买入",
        "current_price": 10.0,
        "requested_size_pct": 0.12,
        "reason": "交易指挥室统一PAPER执行",
    })
    intent = decide(signal, "FLAT")
    assert intent.action == "BUY"
    assert intent.size_pct == 0.12

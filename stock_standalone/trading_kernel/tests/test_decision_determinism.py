from trading_kernel.engine.decision_engine import decide
from trading_kernel.engine.signal_canonicalizer import canonicalize_decision_queue_item
from trading_kernel.observability.trace_hasher import stable_hash


def test_decision_engine_is_deterministic():
    raw = {
        "code": "300001",
        "name": "Demo",
        "created_at": "09:45:00",
        "signal_type": "SECTOR_BREAKOUT",
        "priority": 80,
        "current_price": 10.0,
        "suggest_price": 10.0,
        "pct_diff": 1.2,
        "dff": 2.0,
        "sector_heat": 70,
        "is_leader": True,
    }
    signal = canonicalize_decision_queue_item(raw)
    outputs = [decide(signal, "FLAT") for _ in range(100)]
    assert len({stable_hash(o) for o in outputs}) == 1


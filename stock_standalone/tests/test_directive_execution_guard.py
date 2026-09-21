import time
from types import SimpleNamespace

from ats.strategy.directive_execution_guard import validate_directive


def _directive(**kwargs):
    base = dict(
        action="BUY", price=100.0, timestamp=time.time(),
        expire_at="", stop_loss_price=95.0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _report(**kwargs):
    base = dict(price=100.5, update_time=time.strftime("%H:%M:%S"))
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_guard_accepts_fresh_entry_and_returns_live_price():
    result = validate_directive(_directive(), _report())
    assert result.allowed is True
    assert result.live_price == 100.5


def test_guard_rejects_stale_directive():
    result = validate_directive(_directive(timestamp=time.time() - 181), _report())
    assert result.allowed is False
    assert result.code == "STALE_DIRECTIVE"



def test_guard_rejects_price_drift():
    result = validate_directive(_directive(price=100.0), _report(price=103.0))
    assert result.allowed is False
    assert result.code == "PRICE_DRIFT_EXCEEDED"


def test_guard_rejects_structure_invalidated():
    result = validate_directive(
        _directive(price=100.0, stop_loss_price=99.0),
        _report(price=98.5),
    )
    assert result.allowed is False
    assert result.code == "STRUCTURE_INVALIDATED"


def test_guard_allows_exit_without_live_snapshot():
    result = validate_directive(
        _directive(action="EXIT_ALL", price=99.0, timestamp=0.0),
        None,
    )
    assert result.allowed is True
    assert result.live_price == 99.0

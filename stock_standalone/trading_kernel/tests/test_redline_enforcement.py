import inspect

from trading_kernel.engine.state_manager import StateManager


def test_state_manager_is_pure_behavior_lock():
    forbidden = {
        "pnl",
        "entry_price",
        "position_size",
        "signal_history",
        "strategy_memory",
        "decision_history",
        "last_reason",
        "account_data",
    }
    attrs = set(dir(StateManager)) | set(StateManager().__dict__.keys())
    assert not (attrs & forbidden)


def test_state_manager_source_does_not_contain_strategy_memory_terms():
    source = inspect.getsource(StateManager)
    forbidden_terms = ["entry_price", "position_size", "signal_history", "strategy_memory", "decision_history"]
    for term in forbidden_terms:
        assert term not in source


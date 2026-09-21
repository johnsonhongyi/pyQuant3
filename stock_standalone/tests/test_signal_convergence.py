from types import SimpleNamespace

from ats.strategy.signal_convergence import converge_directives


def directive(action, code="000001", urgency="NORMAL", horse_rank=9):
    return SimpleNamespace(
        action=action, code=code, urgency=urgency, horse_rank=horse_rank,
    )


def test_convergence_keeps_one_highest_priority_exit_per_code():
    result = converge_directives([
        directive("REDUCE_30", urgency="CRITICAL"),
        directive("SELL", urgency="NORMAL"),
    ])

    assert [item.action for item in result.directives] == ["SELL"]
    assert result.exit_count == 1
    assert result.suppressed_reasons == ("DUPLICATE_LOWER_PRIORITY",)


def test_convergence_exit_overrides_entry_for_same_code():
    result = converge_directives([
        directive("BUY", horse_rank=1),
        directive("EXIT_ALL", urgency="CRITICAL"),
    ])

    assert [item.action for item in result.directives] == ["EXIT_ALL"]
    assert result.entry_count == 0
    assert "EXIT_OVERRIDES_ENTRY" in result.suppressed_reasons


def test_convergence_keeps_independent_rotation_and_entry_actions():
    result = converge_directives([
        directive("FULL_ROTATION_SWAP", code="000001", urgency="CRITICAL"),
        directive("BUY", code="000002", horse_rank=1),
        directive("BUY_SCOUT", code="000002", horse_rank=2),
    ])

    assert [item.action for item in result.directives] == ["FULL_ROTATION_SWAP", "BUY"]
    assert result.rotation_count == 1
    assert result.entry_count == 1

# -*- coding: utf-8 -*-
"""Point-in-time tests for the subnew-stock tide state machine."""

from ats.strategy.subnew_tide_state_machine import (
    SubnewTideStateMachine,
    TideObservation,
)


def _obs(date, advance, above_vwap, median, amount, top20, bottom20):
    return TideObservation(
        observed_at=f"{date} 15:00:00",
        sample_count=28,
        completeness=1.0,
        advance_ratio=advance,
        above_vwap_ratio=above_vwap,
        median_return_pct=median,
        amount_yi=amount,
        top20_return_pct=top20,
        bottom20_return_pct=bottom20,
    )


def test_prefix_replay_never_uses_tomorrow_to_classify_today():
    observations = [
        _obs("2026-09-08", .167, .292, -1.96, 91.73, 3.27, -10.09),
        _obs("2026-09-09", .192, .115, -2.57, 101.74, 3.43, -8.19),
        _obs("2026-09-10", .222, .111, -1.71, 106.47, 7.23, -4.22),
        _obs("2026-09-11", .250, .357, -2.74, 167.18, 8.19, -10.46),
        _obs("2026-09-14", .821, .821, 2.34, 135.66, 11.60, -4.60),
    ]

    prefix_machine = SubnewTideStateMachine()
    prefix_states = [prefix_machine.update(item).state for item in observations]

    replay_machine = SubnewTideStateMachine()
    replay_states = replay_machine.replay(observations)
    assert [item.state for item in replay_states] == prefix_states
    assert prefix_states == ["T3_EBB_SPREAD", "T4_PANIC_ACCEL", "T5_ICE", "T6_ICE_DIVERGENCE", "T9_FLOOD_SPREAD"]


def test_panic_allows_only_small_probe_after_divergence_not_blind_buying():
    machine = SubnewTideStateMachine()
    panic = machine.update(_obs("2026-09-09", .192, .115, -2.57, 101.74, 3.43, -8.19))
    ice = machine.update(_obs("2026-09-10", .222, .111, -1.71, 106.47, 7.23, -4.22))
    divergence = machine.update(_obs("2026-09-11", .250, .357, -2.74, 167.18, 8.19, -10.46))

    assert panic.allow_probe is False
    assert panic.position_cap_pct == 0.0
    assert ice.allow_probe is True
    assert ice.position_cap_pct == 5.0
    assert divergence.allow_probe is True
    assert divergence.position_cap_pct == 15.0
    assert divergence.requires_price_confirmation is True


def test_wrong_repair_hypothesis_self_corrects_and_rotates_position_down():
    machine = SubnewTideStateMachine()
    machine.update(_obs("2026-09-14", .821, .821, 2.34, 135.66, 11.60, -4.60))
    failed_follow_through = machine.update(
        _obs("2026-09-15", .179, .000, -1.45, 122.07, 2.47, -5.95)
    )
    reflow = machine.update(
        _obs("2026-09-16", .633, .800, .83, 146.14, 7.68, -4.03)
    )

    assert failed_follow_through.state == "T2_EBB_EARLY"
    assert failed_follow_through.position_cap_pct == 10.0
    assert failed_follow_through.target_action == "REDUCE"
    assert failed_follow_through.revision_count == 1
    assert "failed_follow_through" in failed_follow_through.transition_reasons

    assert reflow.state == "T8_REFLOW_CONFIRM"
    assert reflow.position_cap_pct == 40.0
    assert reflow.target_action == "ROTATE_TO_LEADERS"
    assert reflow.revision_count == 2

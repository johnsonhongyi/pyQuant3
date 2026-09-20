# -*- coding: utf-8 -*-
"""Offline review-contract tests. Samples are deterministic, not claimed as market history."""

from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan, TAG_CHANNEL_SECONDARY_BUY
from ats.strategy.ipo_trading_center import IPOOrderDirective, IPOTradingCenter


def test_closed_trade_review_links_plan_and_execution() -> None:
    center = IPOTradingCenter(total_capital=100000.0)
    plan = IPOTradePlan(
        code="TEST01", name="review sample", plan_id="TP_REPLAY_001",
        strategy_tag=TAG_CHANNEL_SECONDARY_BUY, signal_level="S4",
        quality_grade="S", higher_low_stop=98.0,
        target_1_channel_mid=106.0,
    )
    center.record_order_execution(IPOOrderDirective(
        action="BUY_SCOUT", code="TEST01", name="review sample",
        price=100.0, shares=1000, trade_plan=plan,
    ))
    center.get_position("TEST01").entry_date = "2026-09-19"
    center.record_order_execution(IPOOrderDirective(
        action="EXIT_ALL", code="TEST01", name="review sample",
        price=104.0, shares=1000, trade_plan=plan,
        exit_rule_id="exit_failed_rally", exit_rule_layer=3,
        reason="deterministic replay exit",
    ))

    review = center.get_closed_trade_reviews()[0]
    assert review["plan_id"] == "TP_REPLAY_001"
    assert review["planned_risk_pct"] == 2.0
    assert review["planned_reward_pct"] == 6.0
    assert review["planned_reward_risk"] == 3.0
    assert review["actual_return_pct"] == 4.0
    assert review["target_1_deviation_pct"] == -2.0
    assert review["exit_rule_id"] == "exit_failed_rally"


def test_review_supports_cold_start_dictionary_snapshot() -> None:
    center = IPOTradingCenter(total_capital=100000.0)
    center._closed_positions = [{
        "code": "TEST02", "name": "loaded sample", "cost_price": 20.0,
        "exit_price": 19.0, "realized_pnl_pct": -5.0,
        "exit_rule_id": "exit_hard_stop", "exit_rule_layer": 8,
        "trade_plan": {
            "plan_id": "TP_LOADED", "strategy_tag": TAG_CHANNEL_SECONDARY_BUY,
            "signal_level": "S4", "quality_grade": "A",
            "higher_low_stop": 19.0, "target_1_channel_mid": 22.0,
        },
    }]
    review = center.get_closed_trade_reviews()[0]
    assert review["plan_id"] == "TP_LOADED"
    assert review["planned_risk_pct"] == 5.0
    assert review["actual_return_pct"] == -5.0

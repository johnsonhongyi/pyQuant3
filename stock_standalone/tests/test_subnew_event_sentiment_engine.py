# -*- coding: utf-8 -*-
"""Event sentiment must lead price confirmation without becoming a buy signal."""

from ats.strategy.subnew_event_sentiment_engine import (
    SubnewEvent,
    SubnewEventSentimentEngine,
)


def test_august_to_now_events_raise_preprice_warming_without_buy_permission():
    engine = SubnewEventSentimentEngine()
    events = [
        SubnewEvent("2026-08-04 08:30:00", "IPO_PIPELINE", 0.7, "exchange", "发行节奏恢复"),
        SubnewEvent("2026-08-11 18:00:00", "INSTITUTIONAL_DEMAND", 0.9, "allocation", "网下机构需求增强"),
        SubnewEvent("2026-08-19 15:30:00", "FIRST_DAY_PROFIT_EFFECT", 0.8, "market", "首日赚钱效应扩散"),
        SubnewEvent("2026-09-02 07:40:00", "SECTOR_CATALYST", 0.8, "industry", "次新所属产业催化"),
        SubnewEvent("2026-09-08 20:00:00", "BREAK_RATE", -0.5, "market", "破发率仍需警惕"),
        # This event is after as_of and must never leak into the decision.
        SubnewEvent("2026-09-16 09:31:00", "REGULATORY_RISK", -1.0, "regulator", "未来事件"),
    ]

    snapshot = engine.evaluate(
        events,
        window_start="2026-08-01 00:00:00",
        as_of="2026-09-15 09:25:00",
        price_change_pct=0.0,
    )

    assert snapshot.stage == "WARMING"
    assert snapshot.event_score > 0
    assert snapshot.price_confirmation is False
    assert snapshot.watch_priority == "HIGH"
    assert snapshot.allow_buy is False
    assert snapshot.used_event_count == 5
    assert "REGULATORY_RISK" not in snapshot.event_types
    assert snapshot.evidence


def test_negative_events_enter_risk_off_before_price_breaks():
    engine = SubnewEventSentimentEngine()
    snapshot = engine.evaluate(
        [
            SubnewEvent("2026-09-10 18:00:00", "REGULATORY_RISK", -1.0, "regulator", "监管风险"),
            SubnewEvent("2026-09-11 15:30:00", "BREAK_RATE", -0.9, "market", "破发扩散"),
            SubnewEvent("2026-09-12 08:00:00", "SUPPLY_PRESSURE", -0.8, "exchange", "供给压力"),
        ],
        window_start="2026-08-01 00:00:00",
        as_of="2026-09-15 09:25:00",
        price_change_pct=0.0,
    )

    assert snapshot.stage == "RISK_OFF"
    assert snapshot.watch_priority == "DEFENSIVE"
    assert snapshot.allow_buy is False
    assert snapshot.price_confirmation is False

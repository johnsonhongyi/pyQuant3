from unittest.mock import patch

from auction_decision_engine import AuctionDecisionEngine
from market_sentiment_fsm import (
    BiddingSnapshot,
    MarketSentimentFSM,
    MarketSnapshot,
    SectorRecord,
    SentimentState,
)


def _reversal_fixture():
    sectors = (
        SectorRecord("光模块", -4.5, leader_code="600001", leader_name="龙头一"),
        SectorRecord("半导体", -3.8, leader_code="600002", leader_name="龙头二"),
        SectorRecord("算力", -3.2, leader_code="600003", leader_name="龙头三"),
    )
    fsm = MarketSentimentFSM()
    fsm.yesterday_snapshot = MarketSnapshot(
        date="2026-06-02", index_pct=-1.5, up_count=500, down_count=4000,
        limit_up=5, limit_down=80, temperature=10.0, breadth_ratio=0.11,
        top_sectors=(), worst_sectors=sectors, source_version="daily_sentiment.v1",
    )
    fsm._yesterday_worst_sectors = {item.name for item in sectors}
    fsm._sector_record_by_name = {item.name: item for item in sectors}
    active_sectors = tuple(
        SectorRecord(item.name, 0.5, leader_code=item.leader_code)
        for item in sectors
    )
    stocks = {
        "600001": {"code": "600001", "name": "龙头一", "score": 99, "pct": 5.0, "price": 10.0},
    }
    for index in range(14):
        code = f"600{100 + index:03d}"
        stocks[code] = {"code": code, "name": "高开股", "score": 98 - index, "pct": 5.0, "price": 10.0}
    bidding = BiddingSnapshot(
        date="2026-06-03", generated_at="09:25:00", up_count=80, down_count=20,
        limit_up=15, limit_down=5, active_sectors=active_sectors, stock_snap=stocks,
    )
    return fsm, bidding


def test_fomo_does_not_override_confirmed_reversal():
    fsm, bidding = _reversal_fixture()

    assert fsm.classify(bidding) is SentimentState.REVERSAL


def test_state_publish_failure_closes_auction_candidate_path():
    fsm, bidding = _reversal_fixture()
    engine = AuctionDecisionEngine(fsm)
    engine._is_immediately_previous_session = lambda *_args: True

    with patch("market_pulse_db.save_current_sentiment_state", return_value=False):
        assert engine.generate_signals(bidding) == []

    assert engine.last_state is SentimentState.REVERSAL
    assert engine.last_published_state is SentimentState.COOLDOWN

# scratch/test_auction_engine.py
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import MagicMock
from market_sentiment_fsm import MarketSentimentFSM, SectorRecord, MarketSnapshot, BiddingSnapshot, SentimentState
from auction_decision_engine import AuctionDecisionEngine, AuctionSignal, map_auction_signal_to_dict

class TestAuctionEngine(unittest.TestCase):
    def setUp(self):
        self.fsm = MarketSentimentFSM()
        # Mock yesterday snapshot
        self.yesterday = MarketSnapshot(
            date="2026-06-02",
            index_pct=-1.5, # Panic index drop
            up_count=500,
            down_count=4000,
            limit_up=5,
            limit_down=80,
            temperature=10.0,
            breadth_ratio=0.11,
            top_sectors=(
                SectorRecord(name="银行", avg_pct=0.5, board_score=50.0),
            ),
            worst_sectors=(
                SectorRecord(name="共封装光学", avg_pct=-4.5, leader_code="601869", leader_name="长飞光纤", leader_pct=-9.9, board_score=-45.0),
                SectorRecord(name="大基金持股", avg_pct=-3.8, leader_code="002440", leader_name="闰土股份", leader_pct=-8.0, board_score=-38.0),
                SectorRecord(name="半导体", avg_pct=-3.5, leader_code="603103", leader_name="横店影视", leader_pct=-7.5, board_score=-35.0),
            ),
            source_version="daily_sentiment.v1"
        )
        self.fsm.yesterday_snapshot = self.yesterday
        self.fsm._yesterday_worst_sectors = {s.name for s in self.yesterday.worst_sectors}
        self.fsm._yesterday_top_sectors = {s.name for s in self.yesterday.top_sectors}
        self.fsm._sector_record_by_name = {s.name: s for s in self.yesterday.worst_sectors}
        self.fsm._sector_record_by_name.update({s.name: s for s in self.yesterday.top_sectors})
        
        self.engine = AuctionDecisionEngine(self.fsm)

    def test_reversal_state_generation(self):
        # Mock bidding snapshot indicating high-open rebound of worst sectors
        bidding = BiddingSnapshot(
            date="2026-06-03",
            generated_at="09:25:00",
            up_count=2500,
            down_count=2000,
            limit_up=15,
            limit_down=10,
            active_sectors=(
                SectorRecord(name="共封装光学", avg_pct=0.8, leader_code="601869", leader_name="长飞光纤", leader_pct=1.5, board_score=8.0),
                SectorRecord(name="大基金持股", avg_pct=1.2, leader_code="002440", leader_name="闰土股份", leader_pct=2.0, board_score=12.0),
                SectorRecord(name="半导体", avg_pct=0.2, leader_code="603103", leader_name="横店影视", leader_pct=0.5, board_score=2.0),
            ),
            stock_snap={
                "601869": {
                    "code": "601869",
                    "name": "长飞光纤",
                    "category": "共封装光学",
                    "score": 85.0, # high strength
                    "pct": 1.5, # reasonable high open
                    "price": 35.5,
                    "is_untradable": False
                },
                "002440": {
                    "code": "002440",
                    "name": "闰土股份",
                    "category": "大基金持股",
                    "score": 92.0,
                    "pct": 2.5,
                    "price": 10.2,
                    "is_untradable": False
                }
            }
        )
        
        # Test transition to REVERSAL state
        state = self.fsm.classify(bidding)
        self.assertEqual(state, SentimentState.REVERSAL)
        
        # Test signal generation
        signals = self.engine.generate_signals(bidding)
        self.assertTrue(len(signals) > 0)
        
        for sig in signals:
            self.assertEqual(sig.signal_type, "REVERSAL_BUY")
            # Map signal to dict format for Trading Kernel
            item_dict = map_auction_signal_to_dict(sig)
            self.assertEqual(item_dict["code"], sig.code)
            self.assertEqual(item_dict["action"], "BUY")
            self.assertTrue("Sentiment reversal" in item_dict["reason"])
            print(f"Generated Auction Signal Dict: {item_dict}")

if __name__ == '__main__':
    unittest.main()

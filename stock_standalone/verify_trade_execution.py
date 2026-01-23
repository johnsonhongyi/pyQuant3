
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
from stock_live_strategy import StockLiveStrategy
from trading_hub import TrackedSignal

class TestTradeExecution(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_logger = MagicMock()
        self.mock_voice = MagicMock()
        
        # Instantiate Strategy with mocks
        self.strategy = StockLiveStrategy()
        self.strategy.trading_logger = MagicMock()
        self.strategy.voice_announcer = self.mock_logger # Mock voice
        self.strategy.voice_announcer.announce = MagicMock()
        
        # Mock _monitored_stocks
        self.strategy._monitored_stocks = {}
        self.strategy._save_monitors = MagicMock()
        
        # Mock AlertManager via VoiceAnnouncer
        # (Already mocked via announce method)

    @patch('stock_live_strategy.get_trading_hub')
    def test_auction_buy_execution(self, mock_get_hub):
        # Setup Hub Mock
        mock_hub = MagicMock()
        mock_get_hub.return_value = mock_hub
        
        # 1. Setup Signal (Auction Buy)
        signal = TrackedSignal(
            code="600000", 
            name="TestStock", 
            signal_type="Test", 
            detected_date="2026-01-01", 
            detected_price=10.0,
            entry_strategy="竞价买入"
        )
        self.strategy.follow_queue_cache = [signal]
        
        # 2. Setup Market Data (Open +2%)
        # Auction time logic in strategy relies on datetime.now()
        # We need to bypass the time check or mock datetime.
        # However, _process_follow_queue checks: if "竞价" in entry_strategy and is_auction_time
        
        # Let's bypass the time check logic by modifying the test focus 
        # OR by patching datetime.
        # Instead of patching datetime (complex), let's call _execute_follow_trade directly 
        # to verify the execution logic itself, assuming _process_follow_queue calls it.
        # Then we verify _process_follow_queue selection logic separately if needed.
        
        # Actually, let's verify _execute_follow_trade first.
        
        self.strategy._execute_follow_trade(signal, 10.2, "竞价高开2%")
        
        # 3. Assertions
        # Check Logger
        self.strategy.trading_logger.record_trade.assert_called_with(
            "600000", "TestStock", "买入", 10.2, 0, reason="[竞价买入] 竞价高开2%", resample='d'
        )
        print("[PASS] Trade Recorded")
        
        # Check Hub Update
        mock_hub.update_follow_status.assert_called_with(
            "600000", "ENTERED", notes="Executed at 10.2: 竞价高开2%"
        )
        print("[PASS] Hub Status Updated")
        
        # Check Monitor Injection
        self.assertIn("600000", self.strategy._monitored_stocks)
        monitor = self.strategy._monitored_stocks["600000"]
        self.assertEqual(monitor["tags"], "auto_followed_竞价买入")
        print("[PASS] Monitor Injected")
        
        # Check Voice
        self.strategy.voice_announcer.announce.assert_called()
        print("[PASS] Voice Announce Triggered")

if __name__ == '__main__':
    unittest.main()

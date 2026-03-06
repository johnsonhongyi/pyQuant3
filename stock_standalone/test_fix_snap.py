import sys
import os
import pandas as pd
from unittest.mock import MagicMock, patch

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

def test_fix_snap():
    print("Starting verification for 'snap' variable fix...")
    
    # Mocking necessary components
    mock_logger = MagicMock()
    mock_trading_logger = MagicMock()
    mock_t1_engine = MagicMock()
    mock_hub = MagicMock()
    
    # Mocking the get_trading_hub function
    with patch('stock_live_strategy.get_trading_hub', return_value=mock_hub), \
         patch('stock_live_strategy.logger', mock_logger), \
         patch('JohnsonUtil.LoggerFactory.getLogger', return_value=mock_logger):
        
        from stock_live_strategy import StockLiveStrategy
        
        # Initialize strategy with minimal setup
        strategy = StockLiveStrategy()
        strategy.trading_logger = mock_trading_logger
        strategy.t1_engine = mock_t1_engine
        strategy.follow_queue_cache = [MagicMock(code='600395', name='TestStock', status='ENTERED', entry_strategy='回踩MA5')]
        strategy._monitored_stocks = {}
        strategy._t0_cooldowns = {}
        
        # Prepare mock DataFrame
        df = pd.DataFrame({
            'trade': [10.5],
            'high': [11.0],
            'lastp1d': [10.0],
            'ma5d': [10.2],
            'nclose': [10.4]
        }, index=['600395'])
        
        # Mock datetime to be in trading hours
        with patch('datetime.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "10:00:00"
            mock_datetime.now.return_value = mock_now
            
            # Mock cct.get_day_istrade_date
            with patch('JohnsonUtil.commonTips.get_day_istrade_date', return_value=True):
                try:
                    # Call the problematic method
                    strategy._process_follow_queue(df, resample='d')
                    print("✅ Verification passed: _process_follow_queue executed without NameError.")
                except NameError as e:
                    print(f"❌ Verification failed: {e}")
                except Exception as e:
                    print(f"⚠️ An unexpected error occurred: {e}")
                    import traceback
                    traceback.print_exc()

if __name__ == "__main__":
    test_fix_snap()

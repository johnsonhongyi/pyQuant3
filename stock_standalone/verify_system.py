
import sys
import os
import time
import pandas as pd
import logging
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SystemVerification")

def verify_system():
    logger.info("Starting System Verification...")

    try:
        # 1. Import Modules
        logger.info("Importing modules...")
        from realtime_data_service import DataPublisher
        from stock_live_strategy import StockLiveStrategy
        from intraday_decision_engine import IntradayDecisionEngine
        
        logger.info("Modules imported successfully.")

        # 2. Initialize Realtime Service (DataPublisher)
        logger.info("Initializing RealtimeDataService...")
        publisher = DataPublisher()
        publisher.reset_state()
        
        # 3. Initialize Strategy
        logger.info("Initializing StockLiveStrategy...")
        strategy = StockLiveStrategy(voice_enabled=False)
        strategy.set_realtime_service(publisher)
        
        # Mocking the configuration loading to avoid file dependency
        strategy._monitored_stocks = {
            "600000": {
                "name": "TestStock",
                "rules": [],
                "snapshot": {}
            }
        }
        
        # 4. Simulate Data Update
        logger.info("Simulating Data Update...")
        
        # Create a mock dataframe for a snapshot
        data = {
            "code": ["600000"],
            "name": ["TestStock"],
            "price": [10.5],
            "last_close": [10.0],
            "open": [10.1],
            "high": [10.6],
            "low": [10.1],
            "volume": [10000],
            "amount": [100000],
            "percent": [5.0]
        }
        df_snapshot = pd.DataFrame(data)
        
        # Push data to publisher
        publisher.update_batch(df_snapshot)
        
        # check if cache updated
        klines = publisher.get_minute_klines("600000")
        logger.info(f"K-lines cached: {len(klines)}")
        assert len(klines) > 0, "K-lines should be cached"
        
        # 5. Trigger Strategy Check
        logger.info("Triggering Strategy Check...")
        strategy._check_strategies(df_snapshot)
        
        logger.info("Strategy check completed without error.")
        
        # 6. Verify Reset
        logger.info("Verifying Reset...")
        publisher.reset_state()
        assert len(publisher.kline_cache) == 0, "Cache should be empty after reset"
        
        logger.info("✅ System Verification PASSED!")
        return True

    except Exception as e:
        logger.error(f"❌ System Verification FAILED: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    verify_system()

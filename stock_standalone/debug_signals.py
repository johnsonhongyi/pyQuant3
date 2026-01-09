import sys
import os
sys.path.append(os.getcwd())
from trading_logger import TradingLogger
from datetime import datetime

print(f"Checking signals for today...")
try:
    logger = TradingLogger()
    today = datetime.now().strftime('%Y-%m-%d')
    signals = logger.get_signals(start_date=today)
    print(f"Found {len(signals)} signals for {today}")
    for s in signals:
        print(s)
except Exception as e:
    print(f"Error: {e}")

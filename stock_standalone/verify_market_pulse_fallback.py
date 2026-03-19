
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from market_pulse_engine import DailyPulseEngine
from JohnsonUtil import LoggerFactory

class MockSelector:
    def __init__(self):
        self.resample = 'd'
        self.df_all_realtime = pd.DataFrame(index=['600000', '000001'])
        self.df_all_realtime['score'] = [95, 85]
        self.df_all_realtime['percent'] = [3.0, 2.0]
        self.df_all_realtime['name'] = ['Mock A', 'Mock B']
        self.df_all_realtime['trade'] = [10.3, 20.4]
        self.df_all_realtime['category'] = ['Sector X', 'Sector Y']
        self.df_all_realtime['reason'] = ['Reason A', 'Reason B']

    def get_candidates_df(self):
        return self.df_all_realtime

    def get_market_hotspots(self):
        return [('Sector X', 2.5), ('Sector Y', 1.8)]

def test_fallback_logic():
    mock_selector = MockSelector()
    engine = DailyPulseEngine(stock_selector=mock_selector)
    
    # Mock helpers to avoid network/DB issues
    engine._get_market_breadth = lambda: {'up': 3000, 'down': 1000, 'flat': 1000, 'total': 5000, 'up_ratio': 0.6}
    engine._get_index_status = lambda: [{'name': '上证指数', 'percent': 0.5}]
    
    # Test 1: Empty monitored_stocks
    print("Testing Case: Empty monitored_stocks (Expect Fallback)")
    summary, stocks = engine.generate_daily_report({}, force_date='2026-03-19')
    
    print(f"Total processed stocks: {len(stocks)}")
    for s in stocks:
        print(f" - {s['code']} ({s['name']}): Score {s['score']}")
    
    assert len(stocks) > 0, "Action Radar should not be empty!"
    print("\nFallback Verification Passed: Action Radar populated with selector candidates.")

if __name__ == "__main__":
    test_fallback_logic()

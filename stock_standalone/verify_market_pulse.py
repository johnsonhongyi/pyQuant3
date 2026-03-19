
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from market_pulse_engine import DailyPulseEngine
from JohnsonUtil import LoggerFactory

def test_market_pulse_logic():
    engine = DailyPulseEngine()
    
    # 1. Mock "Good Market" Data
    print("Testing Case 1: Good Market (Indices Up, High Breadth)")
    monitored = {
        '600000': {'name': 'Stock A', 'price': 10.5, 'create_price': 10.0, 'snapshot': {'score': 90, 'win': 3, 'percent': 2.0}},
        '000001': {'name': 'Stock B', 'price': 21.0, 'create_price': 20.0, 'snapshot': {'score': 88, 'win': 2, 'percent': 1.5}},
    }
    
    # Manually monkey-patch or mock internal helpers for reproducible testing
    def mock_breadth_good():
        return {'up': 4000, 'down': 800, 'flat': 200, 'total': 5000, 'up_ratio': 0.8}
    
    def mock_indices_good():
        return [
            {'name': '上证指数', 'percent': 1.2},
            {'name': '深证成指', 'percent': 1.5},
            {'name': '创业板指', 'percent': 2.0}
        ]
        
    engine._get_market_breadth = mock_breadth_good
    engine._get_index_status = mock_indices_good
    
    summary, stocks = engine.generate_daily_report(monitored, force_date='2026-03-19')
    print(f"Temperature (Good): {summary['temperature']}")
    print(f"Summary: {summary['summary']}")
    
    # 2. Mock "Bad Market" Data (Downturn)
    print("\nTesting Case 2: Bad Market (Indices Down, Low Breadth)")
    # Even if we have some high-scoring stocks (which happens in bear markets), the temp should be low.
    def mock_breadth_bad():
        return {'up': 500, 'down': 4300, 'flat': 200, 'total': 5000, 'up_ratio': 0.1}
        
    def mock_indices_bad():
        return [
            {'name': '上证指数', 'percent': -2.5},
            {'name': '深证成指', 'percent': -3.0},
            {'name': '创业板指', 'percent': -3.5}
        ]
        
    engine._get_market_breadth = mock_breadth_bad
    engine._get_index_status = mock_indices_bad
    
    summary_bad, stocks_bad = engine.generate_daily_report(monitored, force_date='2026-03-19')
    print(f"Temperature (Bad): {summary_bad['temperature']}")
    print(f"Summary (Bad): {summary_bad['summary']}")
    
    # 3. Validation
    assert summary_bad['temperature'] < summary['temperature']
    print("\nLogic Verification Passed: Market Temperature correctly reflects overall context.")

if __name__ == "__main__":
    test_market_pulse_logic()

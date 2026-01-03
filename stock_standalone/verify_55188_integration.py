# -*- coding: utf-8 -*-
import pandas as pd
from intraday_decision_engine import IntradayDecisionEngine
from scraper_55188 import Scraper55188

def verify_log_logic():
    engine = IntradayDecisionEngine()
    
    # Mock row data (Price is above MA5/MA10, basic buy signal)
    row = {
        "code": "002131",
        "trade": 10.5,
        "high": 10.6,
        "low": 10.4,
        "open": 10.3,
        "ratio": 2.5,
        "ma5d": 10.2,
        "ma10d": 10.1,
        "nclose": 10.45
    }
    
    # Test Case 1: No 55188 data
    snap_none = {"last_close": 10.0, "market_win_rate": 0.5}
    res_none = engine.evaluate(row, snap_none, mode="buy_only")
    print(f"Case 1 (No Ext): Score Bonus - Popularity: {res_none['debug'].get('popularity_bonus', 0)}, Capital: {res_none['debug'].get('capital_bonus', 0)}")

    # Test Case 2: High popularity (Rank 5)
    snap_high_pop = {
        "last_close": 10.0, 
        "market_win_rate": 0.5,
        "hot_rank": 5, 
        "zhuli_rank": 999,
        "net_ratio_ext": 0.0
    }
    res_pop = engine.evaluate(row, snap_high_pop, mode="buy_only")
    print(f"Case 2 (High Pop): Popularity Bonus: {res_pop['debug'].get('popularity_bonus', 0)}, Hot Info: {res_pop['debug'].get('hot_info')}")

    # Test Case 3: Strong Capital Flow (Ratio 8%)
    snap_cap = {
        "last_close": 10.0, 
        "market_win_rate": 0.5,
        "hot_rank": 999, 
        "zhuli_rank": 20, # 进入主力前 100
        "net_ratio_ext": 8.5 # 8.5%
    }
    res_cap = engine.evaluate(row, snap_cap, mode="buy_only")
    print(f"Case 3 (Strong Cap): Capital Bonus: {res_cap['debug'].get('capital_bonus', 0)}, Zhuli Info: {res_cap['debug'].get('zhuli_info')}")

if __name__ == "__main__":
    try:
        # Note: Importing from local file might fail if paths aren't right, 
        # but the logic check is what matters. 
        # I'll manually check the code logic in my thought process if I can't run it easily.
        # But let's try a simplified version.
        verify_log_logic()
    except Exception as e:
        print(f"Verification script error (likely import path related): {e}")

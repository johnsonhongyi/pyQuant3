# -*- coding:utf-8 -*-
import pandas as pd
import numpy as np
from intraday_decision_engine import IntradayDecisionEngine
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger()

def test_concept_mining_logic():
    engine = IntradayDecisionEngine()
    
    # Mock data
    row = {
        'code': '600000',
        'trade': 10.0,
        'high': 10.5,
        'low': 9.8,
        'open': 9.9,
        'volume': 100000,
        'amount': 1000000,
        'percent': 1.0,
        'ratio': 1.2,
        'ma5d': 9.5,
        'ma10d': 9.4
    }
    
    # Case 1: No theme
    snapshot_none = {
        'last_close': 10.0,
        'score': 50,
        'rt_emotion': 50,
        'v_shape_signal': False
    }
    
    result_none = engine.evaluate(row, snapshot_none)
    debug_none = result_none.get('debug', {})
    print(f"\n[Case 1] No Theme:")
    print(f"Sector Bonus: {debug_none.get('sector_bonus', 0)}")
    print(f"Final Base Position: {result_none.get('position', 0)}")

    # Case 2: New Theme (No persistence)
    snapshot_new = {
        'last_close': 10.0,
        'score': 50,
        'rt_emotion': 50,
        'v_shape_signal': False,
        'theme_name': '人工智能',
        'theme_logic': '算力爆发',
        'sector_score': 0.0 # No persistence
    }
    
    result_new = engine.evaluate(row, snapshot_new)
    debug_new = result_new.get('debug', {})
    print(f"\n[Case 2] New Theme (No persistence):")
    print(f"Theme: {debug_new.get('题材名称')}")
    print(f"Sector Bonus: {debug_new.get('sector_bonus', 0)}")
    print(f"Final Base Position: {result_new.get('position', 0)}")
    
    # Case 3: Hot Theme (High persistence)
    snapshot_hot = {
        'last_close': 10.0,
        'score': 50,
        'rt_emotion': 50,
        'v_shape_signal': False,
        'theme_name': '低空经济',
        'theme_logic': '政策利好',
        'sector_score': 1.0 # Max persistence
    }
    
    result_hot = engine.evaluate(row, snapshot_hot)
    debug_hot = result_hot.get('debug', {})
    print(f"\n[Case 3] Hot Theme (Max persistence):")
    print(f"Theme: {debug_hot.get('题材名称')}")
    print(f"Sector Bonus: {debug_hot.get('sector_bonus', 0)}")
    print(f"Final Base Position: {result_hot.get('position', 0)}")
    
    # Combined check
    diff = debug_hot.get('sector_bonus', 0) - debug_new.get('sector_bonus', 0)
    print(f"\nPersistence Alpha: {round(diff, 2)}")
    
    if diff > 0 and debug_new.get('sector_bonus', 0) > 0:
        print("✅ Concept Mining and Sector Persistence logic verified successfully!")
    else:
        print("❌ Logic verification failed.")

if __name__ == "__main__":
    test_concept_mining_logic()

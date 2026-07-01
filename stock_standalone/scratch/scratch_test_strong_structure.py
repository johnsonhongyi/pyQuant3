import pandas as pd
import sys
import os

# Add root directory to path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multi_period_strategy_engine import MultiPeriodStrategyEngine
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct

def test_strong_structure():
    print("Initializing MultiPeriodStrategyEngine...")
    engine = MultiPeriodStrategyEngine()
    
    print("Loading all stock list (Sina Alldf)...")
    top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
    
    # 1. Test Daily ('d')
    print("\n" + "="*20 + " Testing Daily ('d') Cycle " + "="*20)
    df_d = engine.load_period_data('d', top_now)
    if df_d is not None and not df_d.empty:
        print(f"Loaded {len(df_d)} rows for Daily.")
        
        # Verify columns exist
        verify_cols = ['td_setup', 'td_sell_setup', 'td_buy_setup', 'strong_rebound_score', 'strong_structure_score']
        for col in verify_cols:
            if col in df_d.columns:
                print(f"Column '{col}' exists.")
            else:
                print(f"Column '{col}' is MISSING!")
                
        # Filter for non-zero scores
        df_strong = df_d[df_d['strong_structure_score'] > 0]
        print(f"Found {len(df_strong)} stocks with Daily strong_structure_score > 0")
        if not df_strong.empty:
            df_print = df_strong.sort_values(by='strong_structure_score', ascending=False)
            cols_to_print = ['name', 'close', 'percent', 'td_setup', 'strong_structure_score']
            cols_to_print = [c for c in cols_to_print if c in df_print.columns]
            print(df_print[cols_to_print].head(15))
        else:
            print("No daily stocks triggered strong_structure_score > 0 (this is normal if no stock met all strict pullback criteria today).")
            # Let's print general TD statistics
            print(f"TD setup positive (Sell Setup) counts:\n{df_d['td_setup'][df_d['td_setup'] > 0].value_counts()}")
            print(f"TD setup negative (Buy Setup) counts:\n{df_d['td_setup'][df_d['td_setup'] < 0].value_counts()}")
            
    # 2. Test 2D Cycle ('2d')
    print("\n" + "="*20 + " Testing 2D ('2d') Cycle " + "="*20)
    df_2d = engine.load_period_data('2d', top_now)
    if df_2d is not None and not df_2d.empty:
        print(f"Loaded {len(df_2d)} rows for 2D.")
        
        df_strong_2d = df_2d[df_2d['strong_structure_score'] > 0]
        print(f"Found {len(df_strong_2d)} stocks with 2D strong_structure_score > 0")
        if not df_strong_2d.empty:
            df_print = df_strong_2d.sort_values(by='strong_structure_score', ascending=False)
            cols_to_print = ['name', 'close', 'percent', 'td_setup', 'strong_structure_score']
            cols_to_print = [c for c in cols_to_print if c in df_print.columns]
            print(df_print[cols_to_print].head(15))
        else:
            print("No 2D stocks triggered strong_structure_score > 0.")
            print(f"TD setup positive counts (2D):\n{df_2d['td_setup'][df_2d['td_setup'] > 0].value_counts()}")

if __name__ == '__main__':
    test_strong_structure()


import sys
import os
import pandas as pd

# ── 环境配置 ─────────────────────────────────────────────────────────────────
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'stock_standalone'))

from JSONData import sina_data

def test_enrich():
    code = '688787'
    print(f"Testing enrich_data for {code}...")
    try:
        sina = sina_data.Sina()
        # Test real-time fetch with enrichment
        df = sina.get_real_time_tick(code, enrich_data=True, debug=True)
        
        if df is not None and not df.empty:
            print(f"Success! Columns: {df.columns.tolist()}")
            if 'avg_price' in df.columns:
                print(f"avg_price: {df['avg_price'].iloc[0]}")
            else:
                print("Error: avg_price missing from enriched data!")
            
            if 'tick_vol' in df.columns:
                print(f"tick_vol: {df['tick_vol'].iloc[0]}")
            else:
                print("Error: tick_vol missing!")
        else:
            print("Failed to fetch data or data is empty.")
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_enrich()


import os
import pickle
import pandas as pd
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger("AnalyzeCache")

def analyze():
    # Attempt to get path from the same logic used in the app
    cache_path = cct.get_ramdisk_path("minute_kline_cache.pkl")
    print(f"Targeting cache path: {cache_path}")
    
    if not os.path.exists(cache_path):
        # Fallback to current dir or data dir
        if os.path.exists("minute_kline_cache.pkl"):
            cache_path = "minute_kline_cache.pkl"
        elif os.path.exists("data/minute_kline_cache.pkl"):
            cache_path = "data/minute_kline_cache.pkl"
        else:
            print("❌ minute_kline_cache.pkl not found!")
            return

    try:
        with open(cache_path, 'rb') as f:
            data = pickle.load(f)
            
        if isinstance(data, pd.DataFrame):
            df = data
            counts = df.groupby('code').size()
        elif isinstance(data, dict):
            # If it's the raw _shared_cache dict from MinuteKlineCache
            counts = {code: len(dq) for code, dq in data.items()}
            counts = pd.Series(counts)
        else:
            print(f"Unknown data format: {type(data)}")
            return

        total_stocks = len(counts)
        low_ticks = counts[counts < 200]
        very_low_ticks = counts[counts < 40]
        
        print(f"Total Stocks in Cache: {total_stocks}")
        print(f"Stocks with < 200 ticks: {len(low_ticks)} ({len(low_ticks)/total_stocks*100:.2f}%)")
        print(f"Stocks with < 40 ticks: {len(very_low_ticks)} ({len(very_low_ticks)/total_stocks*100:.2f}%)")
        
        if not low_ticks.empty:
            print("\nSample of stocks with low ticks:")
            print(low_ticks.head(20))
            
    except Exception as e:
        print(f"Error analyzing cache: {e}")

if __name__ == "__main__":
    analyze()

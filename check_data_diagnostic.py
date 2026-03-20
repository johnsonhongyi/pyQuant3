
import os
import sys
import json
import gzip
import pandas as pd
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.getcwd())

def check_snapshot():
    snapshots_dir = os.path.join(os.getcwd(), "stock_standalone", "snapshots")
    if not os.path.exists(snapshots_dir):
        # try another path
        snapshots_dir = os.path.join(os.getcwd(), "snapshots")
    
    if not os.path.exists(snapshots_dir):
        print(f"Snapshots directory not found: {snapshots_dir}")
        return

    files = [f for f in os.listdir(snapshots_dir) if f.endswith('.json.gz')]
    if not files:
        print("No snapshot files found.")
        return

    files.sort(reverse=True)
    latest = os.path.join(snapshots_dir, files[0])
    print(f"Checking latest snapshot: {latest}")

    try:
        with gzip.open(latest, 'rt', encoding='utf-8') as f:
            data = json.load(f)
        
        meta_data = data.get('meta_data', {})
        if not meta_data:
            print("No meta_data in snapshot.")
            return

        print(f"Found {len(meta_data)} stocks in meta_data.")
        
        # Check first few stocks for kline volume
        count = 0
        for code, info in meta_data.items():
            klines = info.get('klines', [])
            if klines:
                print(f"\nStock: {code} ({info.get('name')})")
                print(f"Yesterday Close: {info.get('last_close')}")
                first_k = klines[0]
                last_k = klines[-1]
                print(f"Num Klines: {len(klines)}")
                print(f"First K: {first_k}")
                print(f"Last K: {last_k}")
                
                vols = [k.get('volume', 0) for k in klines]
                print(f"Max Volume in Klines: {max(vols)}")
                print(f"Is 'vol' present instead of 'volume'?: {'vol' in first_k}")
                
                count += 1
                if count >= 3:
                    break
            else:
                print(f"Stock {code} has no klines.")

    except Exception as e:
        print(f"Error checking snapshot: {e}")

if __name__ == "__main__":
    check_snapshot()

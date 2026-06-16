# -*- coding: utf-8 -*-
import os
import zlib
import gzip
import json
import datetime

def diagnose_snapshots():
    snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'snapshots')
    if not os.path.exists(snapshot_dir):
        print(f"Snapshot directory not found: {snapshot_dir}")
        return

    files = sorted([f for f in os.listdir(snapshot_dir) if f.startswith('bidding_') and f.endswith('.json.gz')])
    print(f"Found {len(files)} snapshot files in {snapshot_dir}")
    print("-" * 100)
    print(f"{'Filename':<25} | {'Size (KB)':<10} | {'Status':<15} | {'Stocks':<8} | {'Sectors':<8} | {'Watchlist':<9} | {'Date/Time'}")
    print("-" * 100)

    problematic_files = []

    for filename in files:
        filepath = os.path.join(snapshot_dir, filename)
        size_kb = os.path.getsize(filepath) / 1024
        
        status = "OK"
        stocks_count = 0
        sectors_count = 0
        watchlist_count = 0
        dt_str = "N/A"
        
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            
            # Try zlib decompress first, then gzip
            try:
                json_str = zlib.decompress(raw_data).decode('utf-8')
            except Exception:
                try:
                    json_str = gzip.decompress(raw_data).decode('utf-8')
                except Exception as e:
                    status = "CORRUPT_DECOMPRESS"
                    raise e
            
            try:
                data = json.loads(json_str)
            except Exception as e:
                status = "CORRUPT_JSON"
                raise e
                
            stocks_count = len(data.get('stock_scores', {}))
            sectors_count = len(data.get('sector_data', {}))
            watchlist_count = len(data.get('watchlist', {}))
            
            snap_ts = data.get('timestamp', 0)
            if snap_ts > 0:
                dt_str = datetime.datetime.fromtimestamp(snap_ts).strftime('%Y-%m-%d %H:%M:%S')
            
            if stocks_count == 0:
                status = "EMPTY_STOCKS"
            elif stocks_count < 100:
                status = "TINY_STOCKS"
                
        except Exception as e:
            if status == "OK":
                status = f"ERROR: {str(e)[:20]}"
        
        print(f"{filename:<25} | {size_kb:>10.2f} | {status:<15} | {stocks_count:>8} | {sectors_count:>8} | {watchlist_count:>9} | {dt_str}")
        
        if status != "OK":
            problematic_files.append((filename, size_kb, status, stocks_count, sectors_count, watchlist_count, dt_str))

    print("-" * 100)
    print(f"Diagnosis completed. Found {len(problematic_files)} problematic file(s) out of {len(files)}.")
    if problematic_files:
        print("\n=== Problematic Files Summary ===")
        for f in problematic_files:
            print(f"- {f[0]}: Size={f[1]:.2f}KB, Status={f[2]}, Stocks={f[3]}, Sectors={f[4]}, Watchlist={f[5]}, SnapTime={f[6]}")

if __name__ == "__main__":
    diagnose_snapshots()

# -*- coding: utf-8 -*-
import json
import os

def check_cache_files():
    conf_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    files = [
        os.path.join(conf_dir, 'global_market_klines_yahoo.json'),
        os.path.join(conf_dir, 'global_market_klines_sina.json'),
        os.path.join(conf_dir, 'global_market_klines.json'),
    ]
    
    for fpath in files:
        if not os.path.exists(fpath):
            print(f"File not found: {fpath}")
            continue
        print(f"\n--- Checking file: {os.path.basename(fpath)} ---")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for sym, klines in data.items():
                if klines:
                    last_k = klines[-1]
                    print(f"Symbol: {sym}, Total Klines: {len(klines)}, Last Date: {last_k.get('date')}, Last Close: {last_k.get('close')}, Last Pct: {last_k.get('pct')}%")
        except Exception as ex:
            print(f"Error reading {fpath}: {ex}")

if __name__ == '__main__':
    check_cache_files()

import gzip
import json
import os

filepath = r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\snapshots\bidding_20260312.json.gz"
if not os.path.exists(filepath):
    print("File not found")
else:
    with gzip.open(filepath, 'rt', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Timestamp: {data.get('timestamp')}")
    print(f"Sector Data keys count: {len(data.get('sector_data', {}))}")
    print(f"Watchlist count: {len(data.get('watchlist', {}))}")
    print(f"Meta Data count: {len(data.get('meta_data', {}))}")
    
    # Print a sample sector
    sectors = data.get('sector_data', {})
    if sectors:
        first_sector = list(sectors.keys())[0]
        print(f"\nSample Sector: {first_sector}")
        print(json.dumps(sectors[first_sector], indent=2, ensure_ascii=False)[:500])
    
    # Print a sample meta entry
    meta = data.get('meta_data', {})
    if meta:
        first_code = list(meta.keys())[0]
        print(f"\nSample Meta [{first_code}]:")
        # Don't print full klines
        m_sample = meta[first_code].copy()
        if 'klines' in m_sample:
            m_sample['klines'] = f"[{len(m_sample['klines'])} klines]"
        print(json.dumps(m_sample, indent=2, ensure_ascii=False))

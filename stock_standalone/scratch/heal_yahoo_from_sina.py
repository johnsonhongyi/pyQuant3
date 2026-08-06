import json, os, sys
sys.path.insert(0, '.')
from JSONData.global_market_data import get_kline_cache_file_path, sanitize_klines_for_symbol

yahoo_path = get_kline_cache_file_path().replace('.json', '_yahoo.json')
sina_path = get_kline_cache_file_path().replace('.json', '_sina.json')

if os.path.exists(yahoo_path) and os.path.exists(sina_path):
    with open(yahoo_path, 'r', encoding='utf-8') as f:
        yahoo_cache = json.load(f)
    with open(sina_path, 'r', encoding='utf-8') as f:
        sina_cache = json.load(f)

    restored_count = 0
    for sym, sina_klines in sina_cache.items():
        if sym == 'TEST_SYM':
            continue
        yahoo_klines = yahoo_cache.get(sym, [])
        # 若 yahoo 中缺少数据或数据条数被异常覆盖断裂 (len < 20)，用 sina 的健全历史充实恢复
        if len(yahoo_klines) < 20 and len(sina_klines) >= 20:
            clean_sina = sanitize_klines_for_symbol(sym, sina_klines)
            if clean_sina:
                yahoo_cache[sym] = clean_sina
                restored_count += 1
                print(f"[Heal] 成功将 {sym} 从 sina 盘库恢复至 yahoo 盘库 (恢复 {len(clean_sina)} 条 K 线)")

    if 'TEST_SYM' in yahoo_cache:
        del yahoo_cache['TEST_SYM']

    with open(yahoo_path, 'w', encoding='utf-8') as f:
        json.dump(yahoo_cache, f, ensure_ascii=False, indent=2)
    print(f"🎉 完成自愈恢复: 成功救回 {restored_count} 个标的的全量 K 线历史数据!")

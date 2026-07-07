# -*- coding: utf-8 -*-
"""
合并策略:
- 基础: D:\Ramdisk\backup\20260703\sina_MultiIndex_data.h5 (干净历史，截至 0703)
- 追加: g:\sina_MultiIndex_data.h5 中 0707 的数据 (跳过被污染的 0706)
- 输出: g:\sina_MultiIndex_data_merged.h5 (验证后再手动替换)
"""
import pandas as pd
import os
import time
from collections import Counter

BASE    = r'D:\Ramdisk\backup\20260703\sina_MultiIndex_data.h5'
CURRENT = r'g:\sina_MultiIndex_data.h5'
OUTPUT  = r'g:\sina_MultiIndex_data_merged.h5'
KEY     = '/all_30'
SKIP_DATE = '2026-07-06'   # 被污染，完全跳过
KEEP_FROM = '2026-07-07'   # 当前文件只保留 0707 及以后

print("=" * 65)
print("Step 1: 读取基础备份 (0703，全量)")
print("=" * 65)

t0 = time.time()
print(f"  读取 {BASE} ...", end=' ', flush=True)
df_base = pd.read_hdf(BASE, key=KEY)
print(f"{len(df_base)} 行, {time.time()-t0:.1f}s")

times_base = pd.to_datetime(df_base.index.get_level_values('ticktime'))
print(f"  日期范围: {times_base.min().date()} ~ {times_base.max().date()}")

print("\n" + "=" * 65)
print(f"Step 2: 读取当前文件，只保留 {KEEP_FROM} 及以后的数据")
print("=" * 65)

t0 = time.time()
print(f"  读取 {CURRENT} ...", end=' ', flush=True)
df_cur = pd.read_hdf(CURRENT, key=KEY)
print(f"{len(df_cur)} 行, {time.time()-t0:.1f}s")

# 筛选出 0707 及以后的数据，跳过污染的 0706
times_cur = pd.to_datetime(df_cur.index.get_level_values('ticktime'))
mask_keep = times_cur >= pd.Timestamp(KEEP_FROM)
df_cur_clean = df_cur[mask_keep]
df_cur_skip  = df_cur[~mask_keep]

print(f"  原始行数: {len(df_cur)}")
print(f"  跳过 {SKIP_DATE} 及以前: {len(df_cur_skip)} 行")
print(f"  保留 {KEEP_FROM} 及以后: {len(df_cur_clean)} 行")

if not df_cur_clean.empty:
    t2 = pd.to_datetime(df_cur_clean.index.get_level_values('ticktime'))
    print(f"  保留数据日期: {t2.min().date()} ~ {t2.max().date()}")

print("\n" + "=" * 65)
print("Step 3: 合并与去重")
print("=" * 65)

t0 = time.time()
# 0703 在前（旧），0707 在后（新）→ keep='last' 保留 0707 数据
combined = pd.concat([df_base, df_cur_clean], axis=0)
before = len(combined)
combined = combined[~combined.index.duplicated(keep='last')]
combined = combined.sort_index()
after = len(combined)
print(f"  合并前: {before} 行  →  去重后: {after} 行 (减少 {before-after} 重复), {time.time()-t0:.1f}s")

times_all = pd.to_datetime(combined.index.get_level_values('ticktime'))
codes_all  = combined.index.get_level_values('code').unique()
print(f"  日期范围: {times_all.min().date()} ~ {times_all.max().date()}")
print(f"  code 总数: {len(codes_all)}")

# 各日期行数（最近 10 天）
dates = times_all.date
date_counts = sorted(Counter(dates).items())
print(f"\n  各日期行数 (共 {len(date_counts)} 天，显示最近 10 天):")
for d, cnt in date_counts[-10:]:
    print(f"    {d}: {cnt} 行")

print("\n" + "=" * 65)
print("Step 4: 写入合并文件")
print("=" * 65)

if os.path.exists(OUTPUT):
    os.remove(OUTPUT)
    print(f"  已删除旧文件: {OUTPUT}")

t0 = time.time()
print(f"  写入 {OUTPUT} ...", end=' ', flush=True)
# 使用 table 格式，支持 where 查询
combined.to_hdf(OUTPUT, key=KEY, mode='w', format='table',
                complevel=9, complib='blosc', data_columns=True)
size_mb = os.path.getsize(OUTPUT) / 1024 / 1024
print(f"完成! {size_mb:.1f} MB, {time.time()-t0:.1f}s")

print("\n" + "=" * 65)
print("Step 5: 验证合并结果")
print("=" * 65)

with pd.HDFStore(OUTPUT, mode='r') as store:
    nrows = store.get_storer(KEY).nrows
    # 用 where 查询验证日期范围，使用具体 level 'ticktime'
    df_verify = store.select(KEY, where="ticktime>='2026-07-01'", columns=['close'])
    times_v = pd.to_datetime(df_verify.index.get_level_values('ticktime'))
    print(f"  总行数: {nrows}")
    print(f"  7月以来数据: {len(df_verify)} 行")
    if not df_verify.empty:
        dates_v = sorted(set(times_v.date))
        for d in dates_v:
            cnt = (times_v.date == d).sum()
            print(f"    {d}: {cnt} 行")

print("\n" + "=" * 65)
print("验证通过！执行以下命令替换原文件:")
print()
print(r"  python -c ""import os,shutil; os.rename(r'g:\sina_MultiIndex_data.h5', r'g:\sina_MultiIndex_data.h5.bak2'); shutil.copy2(r'g:\sina_MultiIndex_data_merged.h5', r'g:\sina_MultiIndex_data.h5'); print('替换完成!')""")
print("=" * 65)

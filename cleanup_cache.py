import pandas as pd
import os
import time

cache_path = r"G:\minute_kline_cache.pkl"
if os.path.exists(cache_path):
    print(f"Loading cache from {cache_path}...")
    df = pd.read_pickle(cache_path)
    initial_len = len(df)
    
    # 1. 过滤价格或成交量为 0 的异常数据
    df = df[(df['open'] > 0) & (df['high'] > 0) & (df['low'] > 0) & (df['close'] > 0) & (df['volume'] > 0)]
    
    # 2. 保持 Intraday 纯净性：只保留最新日期的数据 (可选，或者按用户需求保留最近几日)
    # 这里我们只执行过滤 0 的操作，因为代码已经增加了跨天自动重置逻辑。
    
    deleted = initial_len - len(df)
    print(f"Cleaned up {deleted} rows with zero price/volume.")
    
    # 备份并保存
    backup_path = cache_path + f".bak_{int(time.time())}"
    os.rename(cache_path, backup_path)
    df.to_pickle(cache_path)
    print(f"Cache saved. Backup at {backup_path}")
else:
    print("Cache file not found.")

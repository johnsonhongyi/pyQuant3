
import os
import sys
import pandas as pd
import numpy as np
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger()

sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')
from JohnsonUtil import commonTips as cct
cct.get_work_time = lambda: True # 激活极致优化

import JSONData.tdx_hdf5_api as h5a

def test_full_scale_stress():
    source_h5 = r'G:\sina_MultiIndex_data.h5'
    target_h5 = r'G:\sina_MultiIndex_full_stress.h5'
    
    if os.path.exists(target_h5):
        os.remove(target_h5)
        print(f"Removed old test file.")

    print(f"Analyzing source data from {source_h5}...")
    try:
        with pd.HDFStore(source_h5, mode='r') as store:
            key = store.keys()[0].lstrip('/')
            full_df = store.get(key)
    except Exception as e:
        print(f"Error loading source: {e}")
        return

    # 统计每个 ticktime 的股票数量，找一个数据量大的
    counts = full_df.groupby(level='ticktime').size()
    max_count_time = counts.idxmax()
    max_count = counts.max()
    
    print(f"Found peak ticktime: {max_count_time} with {max_count} rows.")
    
    # 提取该时刻的所有数据
    df_peak = full_df[full_df.index.get_level_values('ticktime') == max_count_time]
    
    # 模拟连续 5 次 1.1万行量级的追加 (总计 5.5万行新数据追加)
    print(f"\n>>> Starting FULL-MARKET (11227 rows) Stress Test...")
    
    # 初始化：第一次写入，开启物理重写
    print(f"Initializing {target_h5} with {len(df_peak)} rows...")
    h5a.write_hdf_db(target_h5, df_peak, table=key, index=False, MultiIndex=True, append=True, rewrite=True)
    
    latencies = []
    names = df_peak.index.names # ['code', 'ticktime']
    
    for i in range(5):
        new_time = max_count_time + pd.Timedelta(seconds=5*(i+1))
        df_append = df_peak.copy()
        
        # 安全地更新 MultiIndex 索引 (修复上轮 crash)
        codes = df_append.index.get_level_values('code')
        df_append.index = pd.MultiIndex.from_arrays([codes, [new_time]*len(df_append)], names=names)
        
        print(f"Append {i+1}: {len(df_append)} rows...", end="", flush=True)
        start_t = time.time()
        # 核心验证点：极致追加模式
        success = h5a.write_hdf_db(target_h5, df_append, table=key, index=False, MultiIndex=True, append=True, rewrite=False)
        duration = time.time() - start_t
        
        if success:
            latencies.append(duration)
            print(f" Done. Latency: {duration:.4f}s")
        else:
            print(" FAILED!")
            return
    
    if latencies:
        avg_lat = sum(latencies)/len(latencies)
        print(f"\n>>> FINAL FULL-MARKET RESULT:")
        print(f"Avg Latency for {max_count} stocks: {avg_lat:.4f}s")
        if avg_lat < 1.0:
            print("🏆🏆🏆 [STRESS TEST PASSED] Ultra-fast performance verified for full market load!")
        else:
            print(f"⚠️ Performance Warning: {avg_lat:.2f}s is higher than targeted 1s.")

if __name__ == "__main__":
    test_full_scale_stress()

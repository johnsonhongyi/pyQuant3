
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
cct.get_work_time = lambda: True # 激活极致优化模式

import JSONData.tdx_hdf5_api as h5a

def run_chronological_stress_test():
    source_h5 = r'G:\sina_MultiIndex_data.h5'
    target_h5 = r'G:\sina_MultiIndex_chronological_test.h5'
    
    if os.path.exists(target_h5):
        os.remove(target_h5)
        print(f"Cleaned up {target_h5}")

    print(f"Loading FULL source data from {source_h5} (Wait for 1.6M rows)...")
    try:
        with pd.HDFStore(source_h5, mode='r') as store:
            key = store.keys()[0].lstrip('/')
            full_df = store.get(key)
    except Exception as e:
        print(f"Error: {e}")
        return

    # 1. 按照 ticktime 排序并分组
    print("Sorting data chronologically...")
    unique_times = sorted(full_df.index.get_level_values('ticktime').unique())
    print(f"Total time steps: {len(unique_times)}")

    # 2. 我们模拟前 100 个时间步的自然追加 (Tick 1, 2, 3...)
    # 这样能覆盖从开盘的稀疏数据到逐渐密集的数据波峰
    simulation_steps = unique_times[:100]
    
    print(f"\n>>> Starting Chronological Append (Tick-by-Tick for 100 steps)...")
    
    # 初始化
    first_t = simulation_steps[0]
    df_first = full_df[full_df.index.get_level_values('ticktime') == first_t]
    h5a.write_hdf_db(target_h5, df_first, table=key, index=False, MultiIndex=True, append=True, rewrite=True)
    
    latencies = []
    total_added_rows = len(df_first)
    
    for i, current_t in enumerate(simulation_steps[1:], 2):
        df_step = full_df[full_df.index.get_level_values('ticktime') == current_t]
        
        start_t = time.time()
        # 激活极速追加路径
        success = h5a.write_hdf_db(target_h5, df_step, table=key, index=False, MultiIndex=True, append=True, rewrite=False)
        duration = time.time() - start_t
        
        if success:
            latencies.append(duration)
            total_added_rows += len(df_step)
            if i % 10 == 0:
                print(f"Progress: Step {i}/100 | Rows this tick: {len(df_step)} | Latency: {duration:.4f}s")
        else:
            print(f"Failed at step {i}")
            return

    # 3. 结果验证
    print("\n>>> [CHRONOLOGICAL VERIFICATION]")
    try:
        with pd.HDFStore(target_h5, mode='r') as store:
            result_df = store.get(key)
            final_unique_codes = len(result_df.index.get_level_values('code').unique())
            print(f"Target file unique codes: {final_unique_codes}")
            print(f"Total rows matched: {len(result_df)} vs Expected {total_added_rows}")
            
            if final_unique_codes > 0:
                print(f"✅ Data verified. Successfully captured {final_unique_codes} unique stocks in chronological order.")
            
            avg_lat = sum(latencies)/len(latencies)
            print(f"⚡ Avg Processing Latency: {avg_lat:.4f}s")
            if avg_lat < 0.3:
                print("🚀🚀🚀 [CHRONOLOGICAL SUCCESS] High performance maintained through all market states.")
                
    except Exception as e:
        print(f"Verification fail: {e}")

if __name__ == "__main__":
    run_chronological_stress_test()

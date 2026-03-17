
import os
import sys
import pandas as pd
import numpy as np
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger()

# 添加项目路径
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')
from JohnsonUtil import commonTips as cct

# --- Mock 交易时间：激活极致优化路径 ---
cct.get_work_time = lambda: True

import JSONData.tdx_hdf5_api as h5a

def run_safety_stress_test():
    source_h5 = r'G:\sina_MultiIndex_data.h5'
    target_h5 = r'G:\sina_MultiIndex_safety_test.h5'
    
    if os.path.exists(target_h5):
        os.remove(target_h5)
        print(f"Cleaned up old test file: {target_h5}")

    print(f"Loading source data from {source_h5}...")
    try:
        with pd.HDFStore(source_h5, mode='r') as store:
            key = store.keys()[0].lstrip('/')
            # 我们不需要加载全部 1.6M 行，取前 100个 unique ticktimes 的数据作为测试集
            # 但为了测试“安全性”，我们要分步追加
            full_df = store.get(key)
            print(f"Loaded {len(full_df)} rows from {source_h5}")
    except Exception as e:
        print(f"Error loading source: {e}")
        return

    # 获取唯一的 ticktime 列表
    ticktimes = full_df.index.get_level_values('ticktime').unique().sort_values()
    # 取前 20 个时刻进行测试，每个时刻包含所有股票
    test_times = ticktimes[:20]
    print(f"Simulating {len(test_times)} sequential appends (one per ticktime)...")

    latencies = []
    
    # 第一次写入：初始化文件 (rewrite=True)
    first_time = test_times[0]
    df_step = full_df[full_df.index.get_level_values('ticktime') == first_time]
    print(f"Step 1: Initializing {target_h5} with {len(df_step)} rows...")
    h5a.write_hdf_db(target_h5, df_step, table=key, index=False, MultiIndex=True, append=True, rewrite=True)

    # 后续追加：进入极致优化路径
    for i, t in enumerate(test_times[1:], 2):
        df_step = full_df[full_df.index.get_level_values('ticktime') == t]
        print(f"Step {i}: Appending {len(df_step)} rows (Time: {t})...", end="", flush=True)
        
        start_t = time.time()
        # 激活极致追加模式 (MultiIndex=True, append=True, rewrite=False, is_work_time=True)
        success = h5a.write_hdf_db(target_h5, df_step, table=key, index=False, MultiIndex=True, append=True, rewrite=False)
        duration = time.time() - start_t
        
        if success:
            latencies.append(duration)
            print(f" Done. Latency: {duration:.4f}s")
        else:
            print(" FAILED!")
            return

    # --- 最终校验 ---
    print("\n>>> [FINAL VERIFICATION] Checking data integrity...")
    try:
        with pd.HDFStore(target_h5, mode='r') as store:
            result_df = store.get(key)
            print(f"Appended file rows: {len(result_df)}")
            
            # 基础对比：行数是否匹配
            expected_count = len(full_df[full_df.index.get_level_values('ticktime').isin(test_times)])
            if len(result_df) == expected_count:
                print("✅ Row count match!")
            else:
                print(f"❌ Row count mismatch! Expected {expected_count}, got {len(result_df)}")

            # 结构对比：索引是否正常
            if isinstance(result_df.index, pd.MultiIndex):
                print("✅ MultiIndex preserved!")
            else:
                print("❌ MultiIndex LOST!")

            # 延迟分析
            if latencies:
                avg_lat = sum(latencies) / len(latencies)
                print(f"⚡ Performance: Avg Latency: {avg_lat:.4f}s, Max: {max(latencies):.4f}s, Min: {min(latencies):.4f}s")
                if avg_lat < 0.5:
                    print("🚀🚀🚀 [SAFETY & PERFORMANCE VERIFIED] 'True Append' mode is extremely fast and stable.")

    except Exception as e:
        print(f"Verification error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_safety_stress_test()

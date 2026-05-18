# -*- coding: utf-8 -*-
"""
verify_platform_breakout.py — Advanced Platform Breakout Strategy validation and benchmarking
"""

import os
import sys
import logging
import time
import pandas as pd
import numpy as np

# 强制将当前目录加入 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入系统组件与数据加载器
try:
    from JSONData import tdx_data_Day as tdd
    from JohnsonUtil import johnson_cons as ct
    from stock_logic_utils import calc_platform_breakout
    from JohnsonUtil.commonTips import timed_ctx
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

# 对齐 TDX 路径
tdx_root = r"D:\MacTools\WinTools\new_tdx2"
if os.path.exists(tdx_root):
    tdd.path_dir = os.path.join(tdx_root, "vipdoc")
    os.environ['TDX_ROOT'] = tdx_root

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VerifyBreakout")

def get_lookback_for_resample(resample_str: str) -> int:
    """
    Mathematically scales lookback period based on K-line frequency to ensure identical
    real-world platform window duration (approx. 6 months) across all resample cycles.
    """
    multiplier = 1
    if resample_str == '2d':
        multiplier = 2
    elif resample_str == '3d':
        multiplier = 3
    elif resample_str == 'w':
        multiplier = 5
    elif resample_str == 'm':
        multiplier = 20
    return max(15, int(120 / multiplier))

def run_performance_benchmark(code: str, df: pd.DataFrame, lookback: int, iterations: int = 100):
    """
    Runs robust performance benchmarking over a specified number of iterations to calculate
    average latency (ms) and throughput (operations per second).
    """
    logger.info(f"⏱️ Running performance benchmark for {code} ({iterations} iterations)...")
    
    # Warm up run to ensure caching and JIT overhead are excluded
    with timed_ctx(f"calc_platform_breakout{code}", warn_ms=50, logger=logger):
        _ = calc_platform_breakout(df, lookback=lookback)
    
    start_time = time.perf_counter()
    with timed_ctx(f"calc_platform_breakout{code}_benchmark_100_runs", warn_ms=18000, logger=logger):
        for _ in range(iterations):
            _ = calc_platform_breakout(df, lookback=lookback)
    end_time = time.perf_counter()
    
    total_time = end_time - start_time
    avg_latency_ms = (total_time / iterations) * 1000
    ops_per_second = iterations / total_time
    
    logger.info(f"📊 [BENCHMARK RESULTS - {code}]")
    logger.info(f"   - Total Elapsed Time: {total_time:.4f} seconds")
    logger.info(f"   - Average Latency: {avg_latency_ms:.4f} ms per run")
    logger.info(f"   - Throughput: {ops_per_second:.2f} ops/sec")
    return avg_latency_ms, ops_per_second

def run_loading_benchmark(code: str, dl: int, iterations: int = 50):
    """
    Benchmarks the K-line data loading speed of get_tdx_Exp_day_to_df
    with fastohlc=False vs fastohlc=True.
    """
    logger.info(f"⏱️ Running K-line Loading Benchmark for {code} ({iterations} iterations)...")
    
    # 1. Benchmark with fastohlc=False
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample='d', fastohlc=False)
    time_slow = time.perf_counter() - start_time
    
    # 2. Benchmark with fastohlc=True
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample='d', fastohlc=True)
    time_fast = time.perf_counter() - start_time
    
    logger.info(f"📊 [LOADING BENCHMARK RESULTS - {code}]")
    logger.info(f"   - fastohlc=False (With Indicators): {time_slow:.4f}s | Avg: {(time_slow/iterations*1000):.2f}ms")
    logger.info(f"   - fastohlc=True  (Raw price only): {time_fast:.4f}s | Avg: {(time_fast/iterations*1000):.2f}ms")
    logger.info(f"   - Speedup: {time_slow/time_fast:.2f}x faster!")

def verify_stock_with_periods(code: str, name: str):
    """
    Verifies the platform breakout algorithm across Daily, 3-Day, and Weekly resample periods,
    printing clear and highly informative outputs.
    """
    logger.info(f"\n==================== Verifying {code} ({name}) Multi-Period ====================")
    
    periods = ['d', '3d', 'w']
    
    for resample in periods:
        lookback = get_lookback_for_resample(resample)
        
        # Use standard system duration mapping
        dl_len = ct.Resample_LABELS_Days[resample]
        logger.info(f"🔄 Loading data for period '{resample}' (dl={dl_len}, default_lookback={lookback})...")
        
        df = tdd.get_tdx_Exp_day_to_df(code, dl=dl_len, resample=resample, fastohlc=False)
        
        if df is None or df.empty:
            logger.error(f"❌ Failed to load K-line data for {code} in period '{resample}'!")
            continue
            
        # Standardize columns to lowercase
        df.columns = [c.lower() for c in df.columns]
        if 'code' not in df.columns:
            df['code'] = code
            
        logger.info(f"📈 Loaded K-line data: {len(df)} bars (period='{resample}')")
        
        # We use the pre-calculated platform breakout columns from the standard data pipeline
        df_result = df
        
        # Extract breakout date rows
        breakout_df = df_result[df_result['pbreak'] == 1]
        
        if breakout_df.empty:
            logger.warning(f"⚠️ No platform breakout signals found for {code} in period '{resample}'.")
            continue
            
        logger.info(f"🎯 Found {len(breakout_df)} platform breakout signals in period '{resample}':")
        for date_str, row in breakout_df.iterrows():
            p_top = row['ptop']
            c_price = row['close']
            vol = row.get('volume', row.get('vol', 0))
            
            # Trace subsequent max trend days and peak wave profit
            idx_loc = df_result.index.get_loc(date_str)
            sub_after = df_result.iloc[idx_loc:]
            
            max_trend_days = 0
            peak_close_after = c_price
            for _, r_after in sub_after.iterrows():
                if r_after['pdays'] > 0:
                    max_trend_days = max(max_trend_days, r_after['pdays'])
                    peak_close_after = max(peak_close_after, r_after['close'])
                else:
                    if max_trend_days > 0:
                        break  # Trend ended
                        
            gain_ratio = (peak_close_after - p_top) / p_top * 100
            
            p_bottom = row.get('pbottom', np.nan)
            logger.info(f"   📍 Date: {str(date_str)[:10]} | Platform Range: [{p_bottom:.2f} - {p_top:.2f}] | Close Price: {c_price:.2f} "
                        f"| Jump: {((c_price-p_top)/p_top*100):.1f}% | Vol: {vol:.0f} | Max Trend Duration: {max_trend_days} Bars"
                        f" | Peak Gain: +{gain_ratio:.1f}%")

def verify_low_or_high_power_test_cases(code = '002361'):
    logger.info(f"\n==================== Verifying get_tdx_exp_low_or_high_power Test Cases ====================")
    
    # 1. Daily resample='d'
    resample_d = 'd'
    logger.info(f"🔄 Loading get_tdx_exp_low_or_high_power for '{resample_d}'...")
    df2 = tdd.get_tdx_exp_low_or_high_power(code, dl=ct.Resample_LABELS_Days[resample_d], resample=resample_d)
    if isinstance(df2, pd.Series) and not df2.empty:
        logger.info(f"✅ Daily Period ('d'): ptop={df2.get('ptop', np.nan)}, pbottom={df2.get('pbottom', np.nan)}, pbreak={df2.get('pbreak', 0)}, pdays={df2.get('pdays', 0)}, date={str(df2.get('date', 'None'))[:10]}")
    else:
        logger.error(f"❌ Failed to calculate daily power for {code}!")

    # 2. 3-Day resample='3d'
    resample_3d = '3d'
    logger.info(f"🔄 Loading get_tdx_exp_low_or_high_power for '{resample_3d}'...")
    df3 = tdd.get_tdx_exp_low_or_high_power(code, dl=ct.Resample_LABELS_Days[resample_3d], resample=resample_3d)
    if isinstance(df3, pd.Series) and not df3.empty:
        logger.info(f"✅ 3-Day Period ('3d'): ptop={df3.get('ptop', np.nan)}, pbottom={df3.get('pbottom', np.nan)}, pbreak={df3.get('pbreak', 0)}, pdays={df3.get('pdays', 0)}, date={str(df3.get('date', 'None'))[:10]}")
    else:
        logger.error(f"❌ Failed to calculate 3-day power for {code}!")

    # 3. Weekly resample='w'
    resample_w = 'w'
    logger.info(f"🔄 Loading get_tdx_exp_low_or_high_power for '{resample_w}'...")
    df4 = tdd.get_tdx_exp_low_or_high_power(code, dl=ct.Resample_LABELS_Days[resample_w], resample=resample_w)
    if isinstance(df4, pd.Series) and not df4.empty:
        logger.info(f"✅ Weekly Period ('w'): ptop={df4.get('ptop', np.nan)}, pbottom={df4.get('pbottom', np.nan)}, pbreak={df4.get('pbreak', 0)}, pdays={df4.get('pdays', 0)}, date={str(df4.get('date', 'None'))[:10]}")
    else:
        logger.error(f"❌ Failed to calculate weekly power for {code}!")

def main():
    logger.info("🚀 Launching Platform Breakout Multi-Period & Benchmarking Script")
    
    # Classic stocks with known breakouts
    test_stocks = [
        # ("002361", "Digital China"),
        # ("002475", "Luxshare Precision"),
        ("688800", "Jingchenghuihang")
    ]
    
    # 1. Run multi-period validation
    for code, name in test_stocks:
        verify_stock_with_periods(code, name)
        
    # 2. Run low/high power test cases
    verify_low_or_high_power_test_cases('688800')
        
    # # 2. Run loading benchmarking
    # logger.info(f"\n==================== Running K-line Loading Benchmarking ====================")
    # for code, name in test_stocks:
    #     run_loading_benchmark(code, dl=500, iterations=50)
        
    # # 3. Run performance benchmarking
    # logger.info(f"\n==================== Running Performance Benchmarking ====================")
    # for code, name in test_stocks:
    #     # Load 500 daily bars for benchmark testing
    #     df = tdd.get_tdx_Exp_day_to_df(code, dl=500, resample='d', fastohlc=True)
    #     if df is not None and not df.empty:
    #         df.columns = [c.lower() for c in df.columns]
    #         if 'code' not in df.columns:
    #             df['code'] = code
    #         run_performance_benchmark(code, df, lookback=120, iterations=100)

if __name__ == "__main__":
    main()

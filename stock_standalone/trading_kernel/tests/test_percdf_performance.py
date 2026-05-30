# -*- encoding: utf-8 -*-
import sys
import os
import time
import pytest
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from JohnsonUtil import commonTips as cct

def run_legacy(df):
    """
    原先使用的多次 combine_dataFrame 级联拼接方法
    """
    percdf = cct.get_col_market_value_df(df, 'lasto', '6')
    percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lasth', '6'))
    percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lastl', '6'))
    percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lastp', '15'))
    percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'ma5', '15'))
    percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'ma20', '15'))
    if percdf.index.name != 'code':
        percdf = percdf.rename_axis('code')
    percdf = percdf.reset_index().drop_duplicates('code').set_index('code')
    return percdf

def run_optimized(df):
    """
    我们重构后的 O(1) 级单步切片提取方法（完全动态自适应对齐旧正则天数逻辑）
    """
    limit_days = getattr(cct, 'compute_lastdays', 9)
    remainder = 15 % 10 if 15 <= limit_days else int(limit_days) % 10
    p_days = 10 + remainder
    
    cols_to_keep = []
    for col in ['lasto', 'lasth', 'lastl']:
        cols_to_keep.extend([f"{col}{i}d" for i in range(1, 7)])
    for col in ['lastp', 'ma5', 'ma20']:
        cols_to_keep.extend([f"{col}{i}d" for i in range(1, p_days + 1)])
    
    valid_cols = [c for c in cols_to_keep if c in df.columns]
    percdf = df[valid_cols].copy()
    if percdf.index.name != 'code':
        percdf = percdf.rename_axis('code')
    percdf = percdf.reset_index().drop_duplicates('code').set_index('code')
    return percdf

def load_real_market_data():
    """
    直接从 G:\\ 盘的 tdx_last_df.h5 中加载真实的庞大 A 股日线行情大表，不用任何模拟测试数据
    """
    fname_path = "G:/tdx_last_df.h5"
    if not os.path.exists(fname_path):
        raise FileNotFoundError(f"Real HDF5 file not found: {fname_path}")
    
    # 动态获取第一个可用的 Table Key
    with pd.HDFStore(fname_path, mode='r') as store:
        keys = store.keys()
        if not keys:
            raise ValueError(f"No tables found in {fname_path}")
        table_key = keys[0].strip('/')
        df = store.get(table_key)
        
    print(f"\n[LOAD SUCCESS] Loaded real data from {fname_path}[{table_key}] with shape: {df.shape}")
    
    # 规范 index
    if df.index.name != 'code':
        df = df.rename_axis('code')
    
    # 填充缺失列为0，确保 Legacy 的 filter 不会出错
    df = df.fillna(0)
    return df

def test_percdf_data_parity():
    """
    单元测试：确保两个方法产生的数据完全 100% 同构一致
    """
    df = load_real_market_data()
    
    legacy_res = run_legacy(df)
    optimized_res = run_optimized(df)
    
    legacy_cols = set(legacy_res.columns)
    opt_cols = set(optimized_res.columns)
    
    # 打印调试列信息
    print(f"[DIAGNOSTIC] Legacy shape: {legacy_res.shape} | Optimized shape: {optimized_res.shape}")
    print(f"[DIAGNOSTIC] Legacy Columns not in Optimized: {sorted(list(legacy_cols - opt_cols))}")
    print(f"[DIAGNOSTIC] Optimized Columns not in Legacy: {sorted(list(opt_cols - legacy_cols))}")
    
    # 验证行、列、索引及具体数值 100% 完全相等
    pd.testing.assert_frame_equal(legacy_res, optimized_res)
    assert legacy_res.index.name == 'code'
    assert optimized_res.index.name == 'code'
    print("[PARITY SUCCESS] Legacy and Optimized percdf data is 100% IDENTICAL on REAL data!")

def run_performance_benchmark(iterations=200):
    """
    性能对比压测
    """
    print(f"\n[BENCHMARK] Starting Performance Benchmark (REAL scale, {iterations} iterations)...")
    df = load_real_market_data()
    
    # 1. 预热
    run_legacy(df)
    run_optimized(df)
    
    # 2. 测试 Legacy 耗时
    t_legacy_start = time.perf_counter()
    legacy_times = []
    for _ in range(iterations):
        iter_start = time.perf_counter()
        run_legacy(df)
        legacy_times.append(time.perf_counter() - iter_start)
    legacy_total = time.perf_counter() - t_legacy_start
    
    # 3. 测试 Optimized 耗时
    t_opt_start = time.perf_counter()
    opt_times = []
    for _ in range(iterations):
        iter_start = time.perf_counter()
        run_optimized(df)
        opt_times.append(time.perf_counter() - iter_start)
    opt_total = time.perf_counter() - t_opt_start
    
    # 统计数据
    legacy_mean = (legacy_total / iterations) * 1000.0
    opt_mean = (opt_total / iterations) * 1000.0
    legacy_min = min(legacy_times) * 1000.0
    opt_min = min(opt_times) * 1000.0
    legacy_max = max(legacy_times) * 1000.0
    opt_max = max(opt_times) * 1000.0
    
    speedup = legacy_total / opt_total
    
    # 打印精美对比表 (无 emoji，纯 ASCII 完美支持中文 Win32 终端)
    print("\n" + "="*70)
    print(f"{'Performance Metric (ms)':<25} | {'Legacy Method':<18} | {'Optimized Method':<18}")
    print("-"*70)
    print(f"{'Total Time (for 200 runs)':<25} | {legacy_total*1000.0:15.2f} ms | {opt_total*1000.0:15.2f} ms")
    print(f"{'Average Time per Run':<25} | {legacy_mean:15.3f} ms | {opt_mean:15.3f} ms")
    print(f"{'Fastest (Min) Time':<25} | {legacy_min:15.3f} ms | {opt_min:15.3f} ms")
    print(f"{'Slowest (Max) Time':<25} | {legacy_max:15.3f} ms | {opt_max:15.3f} ms")
    print("="*70)
    print(f"[SPEEDUP RATIO] The Optimized Method is {speedup:.1f}x FASTER than Legacy!")
    print("="*70 + "\n")

if __name__ == '__main__':
    # 运行数据一致性校验
    test_percdf_data_parity()
    # 运行性能压测对比
    run_performance_benchmark(iterations=200)

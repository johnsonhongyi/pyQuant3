import sys
import os
import pandas as pd
import numpy as np
import time
import cProfile
import pstats

# 添加项目根目录到 path
sys.path.append(os.getcwd())

from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct

def find_existing_code():
    """查找一个存在的股票数据文件"""
    basedir = tdd.get_tdx_dir()
    exp_path = os.path.join(basedir, 'T0002', 'export', 'forwardp')
    if not os.path.exists(exp_path):
        print(f"Export path not found: {exp_path}")
        return None
    
    for f in os.listdir(exp_path):
        if f.endswith('.txt') and os.path.getsize(os.path.join(exp_path, f)) > 1024: # > 1KB
            # 提取代码
            code = f.split('.')[0]
            # 去除 sh/sz 前缀
            if code.startswith('SH') or code.startswith('SZ'):
                code = code[2:]
            return code
    return '999999' # 默认指数

def run_benchmark():
    code = find_existing_code()
    print(f"Testing with code: {code}")
    
    if code is None:
        print("No data file found to test.")
        return

    # 1. 测试 IO 性能 - get_tdx_Exp_day_to_df
    print("-" * 30)
    print("Benchmarking get_tdx_Exp_day_to_df (Refactored)...")
    start_time = time.time()
    try:
        df_new = tdd.get_tdx_Exp_day_to_df(code, start=None, end=None, dl=None, newdays=0)
    except Exception as e:
        print(f"Error running new function: {e}")
        return

    end_time = time.time()
    print(f"Refactored IO Time: {end_time - start_time:.4f} seconds")
    print(f"Refactored DF Shape: {df_new.shape}")

    # 对比 IO 结果
    if os.path.exists("tests/benchmark_orig_io.pkl"):
        print("Comparing with original IO results...")
        df_orig = pd.read_pickle("tests/benchmark_orig_io.pkl")
        
        # 基础形状对比
        if df_orig.shape != df_new.shape:
            print(f"[FAIL] Shape mismatch! Orig: {df_orig.shape}, New: {df_new.shape}")
        else:
            print(f"[PASS] Shape match: {df_new.shape}")

        # 列名对比
        if list(df_orig.columns) != list(df_new.columns):
            print(f"[FAIL] Columns mismatch!\nOrig: {list(df_orig.columns)}\nNew: {list(df_new.columns)}")
        else:
            print("[PASS] Columns match")
            
        # 数据内容粗略对比 (检查关键列的 sum)
        try:
            for col in ['close', 'vol', 'amount']:
                if col in df_new.columns:
                    diff = df_orig[col].sum() - df_new[col].sum()
                    if abs(diff) > 0.1:
                         print(f"[FAIL] Column {col} sum mismatch! Diff: {diff}")
                    else:
                         print(f"[PASS] Column {col} sum match")
        except Exception as e:
            print(f"[ERROR] During data comparison: {e}")

    else:
        print("[WARN] No original IO benchmark found to compare.")
    
    # 2. 测试 check_conditions_auto 性能 (暂未重构，先跑通 IO)
    # 为了测试效果，我们构造一个较大的 DF 或者直接使用读取的 DF 如果够大
    print("-" * 30)
    print("Benchmarking check_conditions_auto (Original/Refactored)...")
    
    # 确保所需列存在，模拟一些数据以防缺失
    cols_needed = []
    days = 6
    for i in range(1, days + 2):
        cols_needed.extend([f'lasto{i}d', f'lastl{i}d', f'lastp{i}d', f'per{i}d', f'ma5{i}d'])
    
    # 简单的填充缺失列用于测试逻辑
    df_calc = df_orig.copy()
    for col in cols_needed:
        if col not in df_calc.columns:
            df_calc[col] = np.random.rand(len(df_calc)) * 10 

    start_time = time.time()
    # df_res_orig in previous code was just variable name, now running refactored
    df_res_new = tdd.check_conditions_auto(df_calc.copy())
    end_time = time.time()
    
    print(f"Refactored Calculation Time (all rows): {end_time - start_time:.4f} seconds")

    if os.path.exists("tests/benchmark_orig_calc.pkl"):
        print("Comparing with original Calculation results...")
        df_res_orig = pd.read_pickle("tests/benchmark_orig_calc.pkl")
        
        # Determine if matches
        # Key column is 'MainU'
        if 'MainU' not in df_res_new.columns:
            print("[FAIL] 'MainU' column missing in refactored result")
        elif 'MainU' not in df_res_orig.columns:
            print("[FAIL] 'MainU' column missing in original result (saved pkl might be wrong)")
        else:
            # Compare strings
            # Check for unique index
            if not df_res_orig.index.is_unique:
                print(f"[WARN] Original Index has duplicates. Length: {len(df_res_orig)}, Unique: {len(df_res_orig.index.unique())}")
            
            # Reset index for comparison to avoid 'cannot reindex on an axis with duplicate labels'
            # Also reset index usually preserves order, but to be sure we can sort by index if needed
            # But the error implies Type Error during alignment.
            # Let's drop index completely and compare values as numpy arrays or reset series
            
            # Using .values ensures no index alignment is attempted
            s_orig_vals = df_res_orig['MainU']
            # If duplicated columns, it returns a DataFrame
            if isinstance(s_orig_vals, pd.DataFrame):
                s_orig_vals = s_orig_vals.iloc[:, -1].values
            else:
                s_orig_vals = s_orig_vals.values

            s_new_vals = df_res_new['MainU'].values
            
            mismatch = s_orig_vals != s_new_vals
            
            # Check if mismatch is a boolean scalar (e.g. if arrays are different shapes and numpy returns False)
            # or an array
            
            print(f"Debug: New Shape: {df_res_new.shape}, Orig Shape: {df_res_orig.shape}")
            print(f"Debug: New Series Shape: {s_new_vals.shape}, Orig Series Shape: {s_orig_vals.shape}")

            if np.any(mismatch):
                print(f"[FAIL] MainU mismatch detected.")
                if hasattr(mismatch, 'sum'):
                     print(f"Count: {mismatch.sum()} rows")
                else:
                     print("Mismatch result is a scalar (Shapes likely different?)")
            else:
                print("[PASS] MainU columns match exactly")
    else:
        print("[WARN] No original Calculation benchmark found to compare.")

if __name__ == "__main__":
    run_benchmark()

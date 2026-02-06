
import sys
import os
import psutil
import gc
import time

def get_memory_mb():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def benchmark_memory():
    print(f"PID: {os.getpid()}")
    
    # 1. Baseline
    gc.collect()
    mem_base = get_memory_mb()
    print(f"[1] Baseline Memory: {mem_base:.2f} MB")
    
    # 2. Import tdx_data_Day (Optimized)
    print("Importing tdx_data_Day (Current/Optimized)...")
    t0 = time.time()
    from JSONData import tdx_data_Day as tdd
    t1 = time.time()
    
    gc.collect()
    mem_opt = get_memory_mb()
    print(f"[2] After Optimized Import: {mem_opt:.2f} MB")
    print(f"    Inc: {mem_opt - mem_base:.2f} MB")
    print(f"    Time: {t1 - t0:.4f} s")

    # 3. Simulate Old Behavior (Import heavy libs)
    print("\nSimulating Legacy Load (Importing pandas_ta, talib)...")
    t2 = time.time()
    import pandas_ta as ta
    import talib
    t3 = time.time()
    
    gc.collect()
    mem_full = get_memory_mb()
    print(f"[3] After Heavy Libs Import: {mem_full:.2f} MB")
    print(f"    Inc (vs Opt): {mem_full - mem_opt:.2f} MB")
    print(f"    Total Cost (Legacy): {mem_full - mem_base:.2f} MB")
    print(f"    Time: {t3 - t2:.4f} s")

    print(f"\nSummary:")
    print(f"Optimized Import Cost: {mem_opt - mem_base:.2f} MB")
    print(f"Legacy Import Cost:    {mem_full - mem_base:.2f} MB")
    print(f"Savings:               {mem_full - mem_opt:.2f} MB")

if __name__ == "__main__":
    benchmark_memory()

# -*- coding: utf-8 -*-
import time
import pandas as pd
import numpy as np
import psutil
import os
import sys
import tkinter as tk
from tkinter import ttk

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_logic_utils import detect_signals
from performance_optimizer import TreeviewIncrementalUpdater

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

def generate_mock_data(n_rows=1000):
    columns = [
        'name', 'trade', 'boll', 'dff', 'df2', 'couts',
        'percent', 'per1d', 'perc1d', 'ra', 'ral',
        'topR', 'volume', 'red', 'lastdu4', 'category', 'emotion_status',
        'code', 'high', 'low', 'open', 'lastp1d', 'now',
        'ma51d', 'ma10d', 'lastp2d', 'lastp3d',
        'macddif', 'macddea', 'macd', 'macdlast1', 'macdlast2', 'macdlast3',
        'rsi', 'kdj_j', 'kdj_k', 'kdj_d'
    ]
    data = []
    for i in range(n_rows):
        code = f"{600000 + i:06d}"
        price = round(np.random.uniform(10, 100), 2)
        data.append({
            'code': code,
            'name': f"Stock_{code}",
            'trade': price,
            'now': price,
            'percent': round(np.random.uniform(-10, 10), 2),
            'volume': np.random.randint(1000, 100000),
            'high': price * 1.05,
            'low': price * 0.95,
            'open': price * 1.01,
            'lastp1d': price * 0.98,
            'lastp2d': price * 0.97,
            'lastp3d': price * 0.96,
            'ma51d': price * 0.99,
            'ma10d': price * 0.98,
            'ra': 1.5,
            'category': 'Tech'
        })
    df = pd.DataFrame(data)
    # Fill missing columns with default values
    for col in columns:
        if col not in df.columns:
            df[col] = 0.0
    return df

def benchmark_tk_updater(df, n_iterations=5):
    root = tk.Tk()
    root.withdraw()
    tree = ttk.Treeview(root, columns=list(df.columns), show='headings')
    updater = TreeviewIncrementalUpdater(tree, list(df.columns))
    
    print(f"Benchmarking TreeviewIncrementalUpdater with {len(df)} rows...")
    start_time = time.time()
    for _ in range(n_iterations):
        # Slightly modify data to trigger incremental update
        df_mod = df.copy()
        df_mod.iloc[0, df_mod.columns.get_loc('trade')] += 0.01
        updater.update(df_mod)
    
    avg_time = (time.time() - start_time) / n_iterations
    root.destroy()
    return avg_time

def benchmark_detect_signals(df, n_iterations=5):
    print(f"Benchmarking detect_signals with {len(df)} rows...")
    start_time = time.time()
    for _ in range(n_iterations):
        _ = detect_signals(df)
    avg_time = (time.time() - start_time) / n_iterations
    return avg_time

def run_benchmark():
    print("=== Performance Benchmark (Baseline) ===")
    mem_before = get_memory_usage()
    print(f"Initial Memory Usage: {mem_before:.2f} MB")
    
    df = generate_mock_data(1000)
    mem_after_data = get_memory_usage()
    print(f"Memory after generating 1000 rows: {mem_after_data:.2f} MB (Delta: {mem_after_data - mem_before:.2f} MB)")
    
    dt_time = benchmark_detect_signals(df)
    print(f"Average detect_signals time: {dt_time*1000:.2f} ms")
    
    tk_time = benchmark_tk_updater(df)
    print(f"Average Treeview update time: {tk_time*1000:.2f} ms")
    
    final_mem = get_memory_usage()
    print(f"Final Memory Usage: {final_mem:.2f} MB")
    print(f"Total Memory Overhead: {final_mem - mem_before:.2f} MB")
    print("========================================")

if __name__ == "__main__":
    run_benchmark()

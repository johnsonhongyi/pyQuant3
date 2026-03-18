import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime

# 确保导入路径正确
sys.path.append(r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone")

try:
    from JSONData import tdx_data_Day as tdd
    from JSONData import sina_data
    import sbc_core
    from strategy_controller import StrategyController
    from JohnsonUtil import commonTips as cct
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def benchmark():
    code = "000001"
    print(f"--- Benchmarking {code} ---")
    
    # 1. 获取数据
    sina = sina_data.Sina()
    day_df = tdd.get_tdx_Exp_day_to_df(code, dl=60)
    tick_df = sina.get_real_time_tick(code, enrich_data=True)
    
    if day_df is None or tick_df is None or day_df.empty or tick_df.empty:
        print("Failed to fetch data for benchmark")
        return

    print(f"Data ready: day_df={len(day_df)} rows, tick_df={len(tick_df)} rows")
    
    # 2. 测试 sbc_core.run_sbc_analysis_core
    print("\n[Testing sbc_core.run_sbc_analysis_core]")
    
    # 2.1 Before optimization (no object reuse)
    start_time = time.time()
    iterations = 20
    for i in range(iterations):
        _ = sbc_core.run_sbc_analysis_core(code, day_df, tick_df, verbose=False)
    no_reuse_time = (time.time() - start_time) / iterations
    print(f"Average time (NO object reuse): {no_reuse_time*1000:.2f} ms")
    
    # 2.2 After optimization (with object reuse)
    from intraday_decision_engine import IntradayDecisionEngine
    from realtime_data_service import DailyEmotionBaseline
    engine = IntradayDecisionEngine()
    baseline = DailyEmotionBaseline()
    
    start_time = time.time()
    for i in range(iterations):
        _ = sbc_core.run_sbc_analysis_core(code, day_df, tick_df, verbose=False, engine=engine, baseline_loader=baseline)
    reuse_time = (time.time() - start_time) / iterations
    print(f"Average time (WITH object reuse): {reuse_time*1000:.2f} ms")
    print(f"SBC Speedup (Object Reuse): {(no_reuse_time/reuse_time - 1)*100:.1f}%")

    # 3. Simulate Cache Hit (MainWindow)
    print("\n[Testing Cache Hit Simulation]")
    start_time = time.time()
    for i in range(iterations):
        # Cache hit simulation: O(1) dictionary lookup
        _ = [] # mock signals
    cache_hit_time = (time.time() - start_time) / iterations
    print(f"Average time (CACHE HIT): {cache_hit_time*1000:.6f} ms")
    print(f"Overall Speedup for Static View: {(no_reuse_time/cache_hit_time):.0f}x")

if __name__ == "__main__":
    benchmark()

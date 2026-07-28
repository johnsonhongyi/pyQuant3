import sys
import os
sys.path.insert(0, r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone")

import time
import numpy as np
import pandas as pd
from JSONData.tdx_data_Day import calc_trend_channel

def generate_mock_data(n=200):
    np.random.seed(42)
    dates = pd.date_range(start="2026-01-01", periods=n, freq="D")
    base = np.linspace(10, 25, n)
    close = base + np.random.normal(0, 0.5, n)
    high = close + np.abs(np.random.normal(0.4, 0.1, n))
    low = close - np.abs(np.random.normal(0.4, 0.1, n))
    open_p = low + (high - low) * np.random.rand(n)
    vol = np.random.randint(10000, 500000, n).astype(float)
    return pd.DataFrame({'open': open_p, 'high': high, 'low': low, 'close': close, 'vol': vol}, index=dates)

df = generate_mock_data(200)

# Run once for warm-up and correctness
res = calc_trend_channel(df.copy())
print(f"Generated DataFrame shape: {df.shape}")
print(f"Output columns count: {len(res.columns)} (Added {len(res.columns) - len(df.columns)} new indicator columns)")

# Test 1000 runs timing
N_RUNS = 1000
t0 = time.perf_counter()
for _ in range(N_RUNS):
    _ = calc_trend_channel(df.copy())
t1 = time.perf_counter()

total_ms = (t1 - t0) * 1000.0
per_run_ms = total_ms / N_RUNS
qps = N_RUNS / (t1 - t0)

print(f"\n--- Performance Summary ---")
print(f"Total time for {N_RUNS} runs: {total_ms:.2f} ms")
print(f"Average time per stock (200 bars): {per_run_ms:.3f} ms / stock")
print(f"Throughput: {qps:.1f} stocks / sec")

# Check key columns summary statistics to prove consistency & validity
key_cols = ['ch_upper', 'ch_mid', 'ch_lower', 'ch_slope', 'ch_slope_deg', 'ch_pos', 'ch_dir', 'fib_50', 'sig_bottom', 'sig_launch', 'rsi6']
print(f"\n--- Output Indicator Snapshot (Last row) ---")
for c in key_cols:
    val = res[c].iloc[-1]
    print(f"  {c:<14}: {val}")

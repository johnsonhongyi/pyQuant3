import pandas as pd
import numpy as np
import sys
import os

# 确保能导入 data_utils
sys.path.append(os.getcwd())
import data_utils
from JohnsonUtil import johnson_cons as cct

def generate_mock_data(scenario='breakout', n_days=50):
    """
    生成模拟数据
    scenario: 'breakout', 'pullback', 'weak', 'perfect_jump'
    """
    dates = pd.date_range(end='2026-01-25', periods=n_days)
    prices = np.zeros(n_days)
    
    if scenario == 'breakout':
        prices[:40] = 10.0 + np.random.normal(0, 0.05, 40)
        prices[40:] = 10.0 + np.linspace(0.1, 5.0, 10)
    elif scenario == 'pullback':
        prices[:20] = np.linspace(10.0, 15.0, 20)
        prices[20:40] = np.linspace(15.0, 12.0, 20)
        prices[40:] = 12.0 + np.linspace(0.1, 1.0, 10)
    elif scenario == 'perfect_jump':
        prices[:40] = 10.0
        prices[40:] = 11.0 + np.linspace(0.1, 4.0, 10)
    else:
        prices = np.linspace(15.0, 8.0, n_days)

    df = pd.DataFrame({'close': prices, 'open': prices * 0.99, 'high': prices * 1.01, 'low': prices * 0.98, 'volume': 1000000}, index=dates)
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['std'] = df['close'].rolling(20).std().fillna(0.1)
    df['upper'] = df['ma10'] + 1.2 * df['std']
    df['high4'] = df['high'].rolling(4).max()
    df['per'] = df['close'].pct_change() * 100
    return df

def flatten_history(df, scenario, max_days=20):
    latest = df.iloc[-1].to_dict()
    latest['code'] = 'TEST_CODE'
    latest['name'] = f'模拟-{scenario}'
    
    for i in range(1, max_days + 1):
        if i < len(df):
            row = df.iloc[-(i+1)]
            latest[f'lastp{i}d'] = row['close']
            latest[f'lasto{i}d'] = row['open']
            latest[f'lasth{i}d'] = row['high']
            latest[f'lastl{i}d'] = row['low']
            latest[f'lastv{i}d'] = row['volume']
            latest[f'ma5{i}d'] = row['ma5']
            latest[f'ma10{i}d'] = row['ma10']
            latest[f'upper{i}'] = row['upper']
            latest[f'high4{i}'] = row['high4']
            latest[f'per{i}d'] = row['per']
        else:
            for suffix in ['p', 'o', 'h', 'l', 'v']: latest[f'last{suffix}{i}d'] = 1.0
            latest[f'ma5{i}d'] = 1.0; latest[f'ma10{i}d'] = 1.0
            latest[f'upper{i}'] = 100.0; latest[f'high4{i}'] = 100.0; latest[f'per{i}d'] = 0

    latest['lastp'] = latest['close']
    latest['lasto'] = latest['open']
    latest['lasth'] = latest['high']
    latest['lastl'] = latest['low']
    
    if scenario == 'perfect_jump':
        # 强制 4d (idx 3) 为启动点
        # 启动条件: L <= MA(触碰) AND P > H4 (起跳)
        # 逻辑内 idx 0=1d, 1=2d, 2=3d, 3=4d
        latest['lastl4d'] = 9.9; latest['ma54d'] = 10.0 # L <= MA
        latest['lastp4d'] = 10.5; latest['high44'] = 10.1 # P > H4
        latest['upper4'] = 10.2 # P > Upper (连阳计数开始)
        
        # 3d, 2d, 1d 连续 > Upper
        latest['lastp3d'] = 11.0; latest['upper3'] = 10.5
        latest['lastp2d'] = 11.5; latest['upper2'] = 11.0
        latest['lastp1d'] = 12.0; latest['upper1'] = 11.5
        # 0d (今天) 也满足 P > Upper
        latest['lastp'] = 13.0
        # 逻辑：从启动点 4d(idx 3) 开始向 1d(idx 0) 遍历。
        # 启动点必须 above_upper，如果是 4d，那么 count 从 4d 开始连续到 1d。
        # 结果预期 win_upper = 4
        
    return latest

def run_test(scenario):
    print(f"\n--- 场景: {scenario} ---")
    df = generate_mock_data(scenario)
    flat = flatten_history(df, scenario)
    test_df = pd.DataFrame([flat]).set_index('code')
    
    test_df = data_utils.scoring_momentum_pullback_system(test_df)
    test_df = data_utils.strong_momentum_large_cycle_vect_consecutive_above(test_df)
    print(test_df[['name', 'gem_score', 'win_upper']].to_string())

run_test('breakout')
run_test('perfect_jump')
run_test('weak')

import pandas as pd
import numpy as np
import sys
import os

# 确保能导入 data_utils
sys.path.append(os.getcwd())
import data_utils

def test_cycle_calc():
    print("=== Testing calc_cycle_stage_vect (Multi-Day) ===")
    
    # 构造历史数据 (10天)
    # lookback 默认为 5
    data = []
    # 构造一条顺畅的主升浪 (Stage 2)
    for i in range(10):
        data.append({
            'code': 'S2_rising', 
            'close': 10.0 + i*0.5, 
            'ma5d': 9.5 + i*0.5, 
            'ma10d': 9.0 + i*0.5, 
            'ma20d': 8.5 + i*0.5, 
            'ma60d': 8.0 + i*0.1, 
            'upper1': 12.0 + i*0.5, 
            'volume': 100 + i*5, 
            'lastv1d': 100
        })
    
    # 构造一条原本在主升但量能萎缩且跌破 MA5 的回落 (Stage 4)
    for i in range(10):
        c = 20.0 - i*0.5
        data.append({
            'code': 'S4_fall', 
            'close': c, 
            'ma5d': 20.5 - i*0.2, 
            'ma10d': 20.8 - i*0.1, 
            'ma20d': 21.0, 
            'ma60d': 15.0, 
            'upper1': 25.0, 
            'volume': 50, 
            'lastv1d': 100
        })
        
    df = pd.DataFrame(data)
    
    stages = data_utils.calc_cycle_stage_vect(df)
    df['stage_calc'] = stages.values
    
    print("\n--- Multi-Day Test Results ---")
    print(df[['code', 'close', 'ma20d', 'stage_calc']])
    
    # 验证主升浪
    rising_df = df[df['code'] == 'S2_rising']
    # 在 5 天之后（lookback），应该稳定在 Stage 2
    assert (rising_df.iloc[5:]['stage_calc'] == 2).all(), "Stage 2 not detected correctly in rising trend"
    
    # 验证回落浪
    fall_df = df[df['code'] == 'S4_fall']
    # 最后几行应该是 Stage 4 (由于破均线且量能不足)
    assert (fall_df.tail(3)['stage_calc'] == 4).all(), "Stage 4 not detected correctly in falling trend"
    
    print("\nSUCCESS: Multi-day Cycle Stages correctly identified!")
    return True

if __name__ == "__main__":
    if test_cycle_calc():
        sys.exit(0)
    else:
        sys.exit(1)

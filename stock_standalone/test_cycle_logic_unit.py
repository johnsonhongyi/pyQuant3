import pandas as pd
import numpy as np
import sys
import os

# 确保能导入 data_utils
sys.path.append(os.getcwd())
import data_utils

def test_cycle_calc():
    print("=== Testing calc_cycle_stage_vect ===")
    
    # 构造测试数据
    data = [
        # 1. 筑底启动: 站上 MA20, MA5 接近 MA20
        {'code': 'S1_start', 'close': 10.5, 'ma5d': 10.1, 'ma10d': 10.0, 'ma20d': 10.1, 'ma60d': 10.2, 'upper1': 11.5},
        # 2. 主升健康: 均线顺排
        {'code': 'S2_rising', 'close': 12.0, 'ma5d': 11.5, 'ma10d': 11.0, 'ma20d': 10.5, 'ma60d': 10.0, 'upper1': 13.0},
        # 3. 脉冲扩张: 破上轨
        {'code': 'S3_over', 'close': 15.0, 'ma5d': 13.0, 'ma10d': 12.0, 'ma20d': 11.0, 'ma60d': 10.0, 'upper1': 14.5},
        # 3. 脉冲扩张: 乖离 MA5 > 8%
        {'code': 'S3_bias', 'close': 13.2, 'ma5d': 12.0, 'ma10d': 11.5, 'ma20d': 11.0, 'ma60d': 10.0, 'upper1': 14.0},
        # 4. 见顶回落: 破 MA5
        {'code': 'S4_fall', 'close': 11.8, 'ma5d': 12.0, 'ma10d': 11.5, 'ma20d': 11.0, 'ma60d': 10.0, 'upper1': 14.0},
    ]
    df = pd.DataFrame(data)
    
    stages = data_utils.calc_cycle_stage_vect(df)
    df['stage_calc'] = stages.values
    
    print(df[['code', 'close', 'ma5d', 'upper1', 'stage_calc']])
    
    # 断言验证
    expected = {
        'S1_start': 1,
        'S2_rising': 2,
        'S3_over': 3,
        'S3_bias': 3,
        'S4_fall': 4
    }
    
    success = True
    for _, row in df.iterrows():
        exp = expected[row['code']]
        if row['stage_calc'] != exp:
            print(f"FAILED: {row['code']} expected {exp}, got {row['stage_calc']}")
            success = False
            
    if success:
        print("\nSUCCESS: Cycle Stages correctly identified!")
    else:
        print("\nFAILURE: Some stages were incorrectly identified.")

if __name__ == "__main__":
    test_cycle_calc()

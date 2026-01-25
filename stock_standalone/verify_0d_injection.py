import pandas as pd
import numpy as np
import sys
import os

# 确保能导入 data_utils
sys.path.append(os.getcwd())
import data_utils
from JohnsonUtil import johnson_cons as cct

def test_jump_logic():
    print("\n=== 测试 1: 盘后静态场景 (仅 1d 历史数据) ===")
    df_post = pd.DataFrame([{
        'code': '600001', 'name': '测试1',
        'lastp1d': 12.0, 'upper1': 11.5, 'ma51d': 10.5, 'high41': 11.0, 'lastl1d': 10.0
    }]).set_index('code')
    
    # 盘后计算，应该根据 1d 计算出 win_upper=1
    res_post = data_utils.strong_momentum_large_cycle_vect_consecutive_above(df_post, max_days=5)
    print(f"盘后 win_upper: {res_post.loc['600001', 'win_upper']} (预期: 1)")

    print("\n=== 测试 2: 盘中实时场景 (注入 0d 数据) ===")
    # 模拟盘中：昨日 (1d) 未突破，今日 (now/high) 刚突破
    df_live = pd.DataFrame([{
        'code': '600001', 'name': '测试2',
        'now': 13.0, 'open': 12.5, 'high': 13.5, 'low': 12.1, 'volume': 500000,
        'lastp1d': 11.0, 'upper1': 12.5, 'ma51d': 12.2, 'high41': 12.0, 'lastl1d': 11.5,
        'lastv1d': 1000000
    }]).set_index('code')
    
    # 模拟 data_utils 中的 0d 注入逻辑
    df_live['lastp0d'] = df_live['now']
    df_live['lasth0d'] = df_live['high']
    df_live['lastl0d'] = df_live['low']
    df_live['lastv0d'] = df_live['volume']
    df_live['upper0'] = df_live['upper1']
    df_live['ma50d'] = df_live['ma51d']
    df_live['high40'] = df_live['high41']

    # 1. 验证基础函数响应 0d
    res_live = data_utils.strong_momentum_large_cycle_vect_consecutive_above(df_live, max_days=5)
    print(f"盘中 win_upper: {res_live.loc['600001', 'win_upper']} (预期: 1, 代表今日已起跳)")
    
    # 2. 验证多变体同步响应 (wm5)
    res_wm5 = data_utils.strong_momentum_large_cycle_vect_consecutive_above_m5(df_live, max_days=5)
    print(f"盘中 wm5_upper: {res_wm5.loc['600001', 'wm5_upper']} (预期: 1)")

    # 3. 验证打分系统集成
    res_score = data_utils.scoring_momentum_pullback_system(df_live)
    print(f"盘中 gem_score: {res_score.loc['600001', 'gem_score']} (预期高于 0)")

if __name__ == "__main__":
    test_jump_logic()

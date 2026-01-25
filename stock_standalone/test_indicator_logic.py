import pandas as pd
import numpy as np
import sys
import os

# 确保能导入 data_utils
sys.path.append(os.getcwd())
import data_utils

def generate_mock_row(scenario='normal', win_upper_prev=0):
    """
    生成单行模拟数据
    """
    data = {
        'code': '600001',
        'name': f'测试-{scenario}',
        'close': 13.0, 'open': 12.8, 'high': 13.2, 'low': 12.7, 'volume': 1000000,
        'TrendS': 85.0, 'power_idx': 1.8, 'gem_score': 75.0,
        'lastp1d': 12.0, 'upper1': 12.5, 'ma51d': 12.2, 'high41': 12.1
    }
    
    # 模拟启动点条件: L <= MA AND P > H4
    if scenario == 'buy1_trigger':
        data['low'] = 12.1   # 触碰 MA51d (12.2)
        data['close'] = 13.0 # 突破 High41 (12.1) 且站上 Upper1 (12.5)
    
    return data

def demo_buy_point_transition():
    print("\n=== 1. 捕捉起跳买点 (win_upper 0 -> 1 跳变演示) ===")
    
    # 模拟“昨日”：未站稳 Upper
    df_yesterday = pd.DataFrame([{
        'code': '600001', 'name': '起跳新星',
        'lastp': 12.4, 'upper1': 12.5 # P < Upper -> win_upper 会是 0
    }]).set_index('code')
    # 实际上 win_upper 计算依赖历史列，这里我们直接模拟计算后的结果展示逻辑
    
    # 模拟“今日”触发起跳
    # 逻辑：P1d > Upper1d (假启动) vs 今日初次触碰均线
    df_today = pd.DataFrame([{
        'code': '600001', 'name': '起跳新星',
        'lastp1d': 12.0, 'upper1': 11.5,
        'lastl1d': 10.0, 'ma51d': 10.1, 'high41': 10.0
    }]).set_index('code')
    
    # 补全历史列，使函数内部 range(1, max_days+1) 不会因为列缺失报错
    max_days = 10
    for i in range(1, max_days + 1):
        if f'lastp{i}d' not in df_today.columns:
            df_today[f'lastp{i}d'] = 10.0; df_today[f'upper{i}'] = 11.0
            df_today[f'lastl{i}d'] = 9.0; df_today[f'ma5{i}d'] = 9.1; df_today[f'high4{i}'] = 9.5
    
    # 强制 1d (idx 0) 为启动点：L <= MA 且 P > H4 且 P > Upper
    df_today['lastl1d'] = 10.0; df_today['ma51d'] = 10.5 # L <= MA
    df_today['lastp1d'] = 12.0; df_today['high41'] = 11.0 # P > H4
    df_today['upper1'] = 11.5 # P > Upper (计数开始)
    
    # 我们运行函数，它会遍历从 max_days 到 1d
    res = data_utils.strong_momentum_large_cycle_vect_consecutive_above(df_today, max_days=max_days)
    print(f"今日计算 win_upper: {res.loc['600001', 'win_upper']} (成功捕捉 1d 起跳)")

def demo_top_20_ranking():
    print("\n=== 2. Top 20 二次排序逻辑演示 ===")
    # 构造一个包含 5 只股票的池子
    pool_data = [
        {'code': '001', 'TrendS': 95, 'power_idx': 2.5, 'gem_score': 80, 'win_upper': 3},
        {'code': '002', 'TrendS': 80, 'power_idx': 1.2, 'gem_score': 60, 'win_upper': 1},
        {'code': '003', 'TrendS': 88, 'power_idx': 3.0, 'gem_score': 90, 'win_upper': 4},
        {'code': '004', 'TrendS': 70, 'power_idx': 0.8, 'gem_score': 50, 'win_upper': 0},
        {'code': '005', 'TrendS': 92, 'power_idx': 1.5, 'gem_score': 70, 'win_upper': 2},
    ]
    df_pool = pd.DataFrame(pool_data).set_index('code')
    
    # 筛选
    candidates = df_pool.query('power_idx > 1.0 and win_upper >= 1').copy()
    
    # 二次排序
    candidates['final_score'] = (
        candidates['TrendS'].astype(float) * 0.4 + 
        candidates['power_idx'] * 30 + 
        candidates['gem_score'] * 0.3
    )
    
    result = candidates.sort_values('final_score', ascending=False)
    print("优选池排序结果:")
    print(result[['TrendS', 'power_idx', 'win_upper', 'final_score']].to_string())

if __name__ == "__main__":
    demo_buy_point_transition()
    demo_top_20_ranking()

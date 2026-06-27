import pandas as pd
import sys
import os

from multi_period_strategy_engine import MultiPeriodStrategyEngine
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct

def test_engine():
    engine = MultiPeriodStrategyEngine()
    strategies = engine.load_strategies()
    strat = strategies[0] # 大周期触底 + 小周期启动
    print(f"测试策略: {strat['name']}")
    
    # 修改测试条件以更容易命中
    strat['conditions']['m'] = {"filter": "close > ma10d", "weight": 1.0}
    strat['conditions']['w'] = {"filter": "close > ma5d", "weight": 1.0}
    strat['conditions']['d'] = {"filter": "close > ma10d", "weight": 1.0}
    
    print("获取基础数据...")
    top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
    
    active_periods = ['m', 'w', 'd']
    
    for p in active_periods:
        print(f"正在加载 {p} 周期数据...")
        df = engine.load_period_data(p, top_now)
        if df is not None and not df.empty:
             print(f" - {p} 周期数据加载成功: {len(df)} 条")
        else:
             print(f" - {p} 周期数据加载失败!")
        
    print("执行多周期交叉验证...")
    res = engine.evaluate_strategy(strat, active_periods)
    
    print(f"策略执行完毕，找到 {len(res)} 只标的:")
    if not res.empty:
        cols = ['name', 'close', 'percent', 'volume'] + [f'pass_{p}' for p in active_periods]
        cols = [c for c in cols if c in res.columns]
        print(res[cols].head(20))
    else:
        print("无符合条件数据。")

if __name__ == '__main__':
    test_engine()

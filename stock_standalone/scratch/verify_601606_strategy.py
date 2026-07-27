import sys
import os
import pandas as pd

# 将项目路径加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from multi_period_strategy_engine import MultiPeriodStrategyEngine
from query_engine_util import PandasQueryEngine

def test_601606_rule_evaluation():
    engine = MultiPeriodStrategyEngine()
    strategies = engine._strategies if hasattr(engine, '_strategies') and engine._strategies else []
    
    # 手动解析配置文件
    import json
    with open(engine.config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        strategies = data.get("strategies", [])
        
    target_strat = None
    for s in strategies:
        if s.get("id") == "tpl_bottom_oversold_wash_breakout":
            target_strat = s
            break
            
    assert target_strat is not None, "未找到目标策略 tpl_bottom_oversold_wash_breakout"
    
    print(f"[FOUND] Strategy: {target_strat['name']}")
    
    # 模拟长城军工 601606 在启动日的真实底层数据
    row_601606_d = {
        'percent': 9.99,
        'close': 32.05,
        'open': 30.63,
        'ma5d': 28.01,
        'lastv0d': 30260888.0,
        'lastv1d': 30465419.0,
        'volume': 2.2,
        'lastv2d': 14650988.0,
        'lastv3d': 13191270.0,
        'ma20d': 27.6,
        'macddif': -1.17,
        'macddea': -1.56
    }
    
    df_d = pd.DataFrame([row_601606_d])
    
    # 诊断过滤
    raw_filter = target_strat['conditions']['d']['filter']
    print(f"Raw D Filter: {raw_filter}")
    
    query_engine = PandasQueryEngine()
    processed_expr = query_engine._preprocess_query(raw_filter)
    print(f"Processed Filter: {processed_expr}")
    
    res_df = query_engine.execute(df_d, processed_expr)
    
    if not res_df.empty:
        print("[SUCCESS] 601606 Evaluation 100% PASSED D Filter!")
    else:
        print("[FAILED] Evaluation failed, please check expression logic!")

if __name__ == "__main__":
    test_601606_rule_evaluation()

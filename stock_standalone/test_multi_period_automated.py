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
    import pprint
    print("各周期及最终统计数据 (last_stats):")
    pprint.pprint(engine.last_stats)
    if not res.empty:
        cols = ['name', 'close', 'percent', 'volume'] + [f'pass_{p}' for p in active_periods]
        cols = [c for c in cols if c in res.columns]
        print(res[cols].head(20))
    else:
        print("无符合条件数据。")
        
    # 直接复用本次加载的数据与 engine 执行单股诊断测试
    test_individual_diagnosis(engine, strat, top_now)

def test_individual_diagnosis(engine, strat, top_now):
    print("\n" + "="*20 + " 测试单股多周期诊断逻辑 (数据复用模式) " + "="*20)
    
    # 优先使用 凯莱英 (002821)
    code = "002821"
    if code not in top_now.index:
        code = top_now.index[0]
        
    print(f"拟诊断股票代码: {code}")
    
    active_periods = ['m', 'w', 'd']
    
    # 执行多周期诊断平铺合并
    merged_row = {"name": top_now.loc[code, 'name'] if 'name' in top_now.columns else "未知"}
    
    import re
    def suffix_expr(expr, period_suffix, cols_set):
        def repl(match):
            word = match.group(0)
            if word in cols_set:
                return f"{word}_{period_suffix}"
            return word
        return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)
        
    queries = []
    for period in active_periods:
        df_p = engine._period_dfs.get(period)
        if df_p is not None and not df_p.empty:
            valid_cols = set(df_p.columns)
            if code in df_p.index:
                row_p = df_p.loc[code]
                if isinstance(row_p, pd.DataFrame):
                    row_p = row_p.iloc[0]
                for k, val in row_p.to_dict().items():
                    if k not in ('code', 'name'):
                        merged_row[f"{k}_{period}"] = val
            
            cond = strat['conditions'].get(period)
            if cond:
                raw_filter = cond['filter']
                suffixed_filter = suffix_expr(raw_filter, period, valid_cols)
                queries.append({
                    "name": f"{period.upper()}周期条件",
                    "expr": suffixed_filter
                })
                
    df_flat = pd.DataFrame([merged_row], index=[code])
    df_flat.index.name = 'code'
    
    print("平铺后的数据字段样例:")
    sample_cols = [c for c in df_flat.columns if c.startswith('close_') or c.startswith('ma')]
    print({k: df_flat.loc[code, k] for k in sample_cols[:8] if k in df_flat.columns})
    
    print("\n后缀化后的诊断 queries 表达式:")
    for q in queries:
        print(f" - {q['name']}: {q['expr']}")
        
    # 调用 test_code_query 模拟诊断结果
    from stock_logic_utils import test_code_query, format_check_result
    report = test_code_query(df_flat, queries)
    print("\n测试诊断报告输出:")
    try:
        report_str = format_check_result(report)
        # 将 emoji 替换为 ascii 字符以保证 Windows 控制台打印时不产生 Unicode 编码崩溃
        report_str = report_str.replace("✅", "[Pass]").replace("❌", "[Fail]")
        print(report_str)
    except Exception as e:
        print(f"打印报告输出失败(编码兼容限制): {e}")

if __name__ == '__main__':
    test_engine()

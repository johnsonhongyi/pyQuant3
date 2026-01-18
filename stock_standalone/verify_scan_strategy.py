
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strong_consolidation_strategy import StrongConsolidationStrategy

def create_mock_market_data(num_stocks=10):
    all_dfs = []
    codes = [f"{i:06d}" for i in range(num_stocks)]
    
    # 增加历史深度到 100 天，确保滚动指标稳定
    now = datetime.now()
    dates = [now - timedelta(days=i) for i in range(100)][::-1]
    
    for code in codes:
        # 基准价格
        base_vals = np.linspace(10, 15, 100) + np.random.normal(0, 0.5, 100)
        data = {
            'open': base_vals * 0.99,
            'high': base_vals * 1.01,
            'low': base_vals * 0.98,
            'close': base_vals,
            'volume': np.random.randint(1000, 5000, 100),
            'percent': np.random.uniform(-1, 1, 100),
            'name': [f"Stock_{code}"] * 100
        }
        
        # 针对 000001 和 000005 植入模式
        if code in ['000001', '000005']:
            # 1. 突破日 (Day 80)
            data['close'][80] = 20.0
            data['open'][80] = 18.0
            data['high'][80] = 20.5
            data['percent'][80] = 10.0
            data['volume'][80] = 10000
            
            # 2. 强势整理 (Day 81 - 97) - 维持在突破日收盘之上
            for j in range(81, 98):
                data['close'][j] = 20.2 + np.random.random() * 0.5
                data['open'][j] = data['close'][j] * 0.99
                data['high'][j] = data['close'][j] * 1.01
                data['low'][j] = data['close'][j] * 0.98
                data['volume'][j] = 5000
                data['percent'][j] = 0.5
                
            # 3. 攻击形态 (Day 98 - 99)
            data['high'][98] = 21.0
            data['close'][98] = 20.8
            data['high'][99] = 21.5
            data['close'][99] = 21.3
            
        df = pd.DataFrame(data, index=dates)
        df.index.name = 'date'
        df['code'] = code
        all_dfs.append(df)
        
    full_df = pd.concat(all_dfs).reset_index().set_index(['date', 'code']).sort_index()
    return full_df

def test_scan():
    print(">>> Testing StrongConsolidationStrategy.execute_scan (Enhanced Mode)...")
    df_market = create_mock_market_data(num_stocks=10)
    
    strat = StrongConsolidationStrategy()
    
    # 手动验证单只股票模式
    print("\n[Diagnostic: Stock 000001]")
    sub_01 = df_market.xs('000001', level='code')
    sig = strat._detect_pattern('000001', sub_01)
    if sig:
        print(f"✅ Diagnostic Match: {sig.reason}")
    else:
        print("❌ Diagnostic Fail: Stock 000001 did not match.")
        # 打印最后几行看看
        # print(sub_01.tail(5))
    
    # 执行全市场扫描
    print("\n[Running execute_scan]")
    results = strat.execute_scan(df_market, resample='d', parallel=True)
    
    found_codes = [r['code'] for r in results]
    print(f"Total Matches Found: {len(found_codes)}")
    print(f"Matches: {found_codes}")
    
    if '000001' in found_codes and '000005' in found_codes:
        print("\n✅ execute_scan Verification PASSED!")
    else:
        print(f"\n❌ execute_scan Verification FAILED!")

if __name__ == "__main__":
    test_scan()

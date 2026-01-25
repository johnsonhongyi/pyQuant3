import pandas as pd
import numpy as np
import sys
import os
import time

# 环境配置
sys.path.append(os.getcwd())
import data_utils
from JSONData import tdx_data_Day as tdd
from JSONData import sina_data
from JohnsonUtil import johnson_cons as ct

def test_real_data_injection(code='600000'):
    print(f"\n=== 真实数据注入模拟测试: {code} ===")
    
    # 1. 获取盘后历史数据 (包含 1d, 2d... 特征)
    # 模拟 instock_MonitorTK 中的获取逻辑
    try:
        resample = 'd'
        dl = 11 # 获取 11 天数据
        with data_utils.timed_ctx("get_tdx_Exp_day_to_df", warn_ms=800):
            day_df = tdd.get_tdx_Exp_day_to_df(code, dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=False)
        
        if day_df is None or day_df.empty:
            print("未能获取到历史数据")
            return

        # 2. 获取实时 Tick 数据 (模拟日内最新 OHLC)
        with data_utils.timed_ctx("get_real_time_tick", warn_ms=800):
            tick_df = sina_data.Sina().get_real_time_tick(code)
            
        if tick_df is None or tick_df.empty:
            print("未能获取到实时 Tick")
            # 兼容性：如果获取失败，用 lastp1d 构造一个伪 0d 触发
            tick_now = day_df.iloc[0]['close'] * 1.05
            tick_high = tick_now
            tick_low = day_df.iloc[0]['close'] * 0.99
            tick_vol = 1000000
        else:
            tick_now = float(tick_df.iloc[0].get('trade', 0))
            tick_high = float(tick_df.iloc[0].get('high', 0))
            tick_low = float(tick_df.iloc[0].get('low', 0))
            tick_vol = float(tick_df.iloc[0].get('volume', 0))

        # 3. 构造基础 DataFrame
        df_all = day_df.copy()
        
        # 4. 注入必备的基础列（如果原本没有 upper1 等衍生列）
        # 模拟 data_utils 计算链中可能赋予的初始值
        if 'upper' in df_all.columns: df_all['upper1'] = df_all['upper']
        if 'ma5' in df_all.columns: df_all['ma51d'] = df_all['ma5']
        if 'high4' in df_all.columns: df_all['high41'] = df_all['high4']
        if 'lastl' in df_all.columns: df_all['lastl1d'] = df_all['lastl']
        if 'lastp' in df_all.columns: df_all['lastp1d'] = df_all['lastp']
        if 'lastv' in df_all.columns: df_all['lastv1d'] = df_all['lastv']

        # 4. 注入 0d 数据列
        df_all['lastp0d'] = tick_now
        df_all['lasth0d'] = tick_high
        df_all['lastl0d'] = tick_low
        df_all['lasto0d'] = tick_now 
        df_all['lastv0d'] = tick_vol
        
        # 注入 0d 阈值特征
        # 在盘中刷新时，我们通常用昨日的指标作为今日的基准
        df_all['upper0'] = df_all['upper1'] if 'upper1' in df_all.columns else tick_now * 1.01
        df_all['ma50d'] = df_all['ma51d'] if 'ma51d' in df_all.columns else tick_now * 0.98
        df_all['high40'] = df_all['high41'] if 'high41' in df_all.columns else tick_now * 0.99

        print(f"当前价: {tick_now:.2f}, 昨天压力位: {df_all.iloc[0].get('upper1', 'N/A')}")
        
        # 5. 执行计算
        # 注意：此处要验证能否基于 0d 到 10d 进行计算
        res = data_utils.strong_momentum_large_cycle_vect_consecutive_above(df_all, max_days=10)
        
        win_upper = res.iloc[0]['win_upper']
        print(f"最终计算 win_upper: {win_upper}")
        if win_upper > 0:
            print("🚀 [捕捉成功] 该股正在压力位上方运行！")
        else:
            print("⏸️ [监控中] 尚未突围压力位或不满足起跳条件。")

    except Exception as e:
        print(f"运行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 可以通过环境变量或参数传入代码，默认使用 600000
    target_code = sys.argv[1] if len(sys.argv) > 1 else '000001'
    test_real_data_injection(target_code)

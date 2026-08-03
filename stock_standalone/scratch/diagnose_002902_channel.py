# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import re
import pandas as pd
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df

def diagnose_stock_channel(code_str="002902"):
    # 自动正则提取 6 位数字代码
    digit_match = re.search(r'\d{6}', str(code_str))
    code_str = digit_match.group(0) if digit_match else "002902"

    print(f"\n==================================================")
    print(f"=== 股票【{code_str}】自动通道极值诊断 (读取最新切片数据) ===")
    print(f"==================================================")
    
    # 1. 读取数据 (get_tdx_Exp_day_to_df 内部已算好全套通道指标)
    df = get_tdx_Exp_day_to_df(code_str)
    if df is None or len(df) == 0:
        print(f"❌ 错误：无法获取股票 [{code_str}] 的日线数据。")
        return

    # 2. 直接读取最新一天的数据切片 (df.iloc[-1])
    last = df.iloc[-1]
    n = len(df)

    tc2 = int(last['ch_tc2'])
    bc2 = int(last['ch_bc2'])
    nod = int(last['ch_nod'])
    high_date = df.index[max(0, n - tc2)]
    low_date = df.index[max(0, n - bc2)]

    print(f"最新交易日: {df.index[-1]}, 最新收盘价: {last['close']:.2f} 元")
    print(f"通道三轨: 上轨 (ch_upper) = {last['ch_upper']:.2f} 元, 中轨 (ch_mid) = {last['ch_mid']:.2f} 元, 下轨 (ch_lower) = {last['ch_lower']:.2f} 元")
    print(f"通道斜率: {last['ch_slope']:.4f} (倾角 {last['ch_slope_deg']:.2f}°), 价格相对位置 (ch_pos): {last['ch_pos']:.2f}%")
    print(f"顶点日期: {high_date}, 顶点最高价: {last['ch_anchor_high_price']:.2f} 元, 距今 (tc2): {tc2} 根")
    print(f"底点日期: {low_date}, 底点最低价: {last['ch_anchor_low_price']:.2f} 元, 距今 (bc2): {bc2} 根")
    print(f"高低点间隔 (nod): {nod} 根, 趋势格局 (ch_pattern): {int(last['ch_pattern'])} ({'触底走高' if last['ch_pattern'] == 1 else '触顶走低'})\n")

    # 3. 输出最近 10 天特征明细表
    cols = [
        'close', 'ch_upper', 'ch_mid', 'ch_lower', 'ch_slope', 'ch_slope_deg', 'ch_pos',
        'ch_anchor_high_price', 'ch_anchor_low_price', 'ch_tc2', 'ch_bc2', 'ch_nod', 'ch_pattern'
    ]
    pd.set_option('display.max_columns', 20)
    pd.set_option('display.width', 1000)
    print(f"=== 最近 10 个交易日【{code_str}】通道与极值特征明细表 ===")
    print(df[cols].tail(10))

if __name__ == "__main__":
    target_code = sys.argv[1] if len(sys.argv) > 1 else input("请输入 6 位股票代码 (回车默认 002902): ").strip() or "002902"
    diagnose_stock_channel(target_code)

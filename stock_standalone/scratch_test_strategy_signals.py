import sys
import os
import pandas as pd
import numpy as np

sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')
from JSONData import tdx_data_Day as tdd
import data_utils

def test_stock_signals(code, name):
    print(f"\n{'='*50}")
    print(f"Testing: {code} {name}")
    print(f"{'='*50}")
    
    try:
        df = tdd.get_tdx_append_now_df_api(code)
        if df is None or df.empty:
            print(f"Failed to get data for {code}")
            return
    except Exception as e:
        print(f"Exception: {e}")
        return

    df['std20'] = df['close'].rolling(20).std()
    df['upper1'] = df['ma20d'] + 2 * df['std20']
    
    if 'volume' in df.columns and 'vol' not in df.columns:
        df['vol'] = df['volume']
        
    df['lastp1d'] = df['close'].shift(1)
    df['lasto1d'] = df['open'].shift(1)
    df['lasth1d'] = df['high'].shift(1)
    df['lastl1d'] = df['low'].shift(1)
    df['lastv1d'] = df['vol'].shift(1)
    df['upper'] = df['upper1'].shift(1) 
    df['ma51d'] = df['ma5d'].shift(1)
    df['now'] = df['close']
    
    df['cycle_stage'] = data_utils.calc_cycle_stage_vect(df)

    eval_state = np.full(len(df), 9)
    trade_signal = np.full(len(df), 5)

    for i in range(20, len(df)):
        curr_c = df['close'].iloc[i]
        curr_o = df['open'].iloc[i]
        curr_l = df['low'].iloc[i]
        curr_a = df['vol'].iloc[i]
        
        close_1d = df['lastp1d'].iloc[i]
        amount_1d = df['lastv1d'].iloc[i]
        upper_1d = df['upper'].iloc[i]
        ma_ref = df['ma51d'].iloc[i]
        
        eval_1d = eval_state[i-1]
        eval_2d = eval_state[i-2] if i > 1 else 9

        # --- 核心改进：抛弃布林线上轨，改用均线启动逻辑 ---
        pct = (curr_c - close_1d) / close_1d * 100
        is_big_yang = (pct >= 4.0) and (curr_c > curr_o)
        
        # 启动条件: 大阳线，并且开盘价在 MA5/MA10/MA20 其中任意一条均线之下，收盘站上MA5
        ma5_curr = df['ma5d'].iloc[i]
        ma10_curr = df['ma10d'].iloc[i]
        ma20_curr = df['ma20d'].iloc[i]
        ma60_curr = df['ma60d'].iloc[i] if 'ma60d' in df.columns else ma20_curr
        
        started_under_ma = (curr_o < ma5_curr) or (curr_o < ma10_curr) or (curr_o < ma20_curr) or (curr_o < ma60_curr)
        cond_trend_start = is_big_yang and started_under_ma and (curr_c > ma5_curr)
        
        # 修复：只有不在主升期时，大阳线才叫启动。否则叫延续或反包
        cond_trend_start = cond_trend_start and (eval_1d not in [1, 2, 3])
        
        # 延续条件: 只要站在MA20之上，就认定为主升延续
        cond_trend_continue = (curr_c >= ma20_curr)
        
        # 回撤条件: 价格下跌缩量，但守住 MA60 生命线（洗盘）
        cond_pullback = (curr_c < close_1d) and (curr_l >= ma60_curr) and (curr_a < amount_1d)
        
        # 破位条件: 彻底跌破 MA60，或者【有效跌破 MA20】（今日和昨日均收在MA20之下）
        ma20_1d = df['ma20d'].iloc[i-1] if i > 0 else ma20_curr
        effective_break_ma20 = (curr_c < ma20_curr) and (close_1d < ma20_1d)
        cond_bear = (curr_c < ma60_curr) or effective_break_ma20
        # --------------------------------------------------------

        curr_eval = eval_1d
        if cond_trend_start: curr_eval = 1
        elif curr_eval != 1 and cond_trend_continue: curr_eval = 2
        elif eval_1d in [2, 3] and cond_pullback: curr_eval = 3
        elif eval_1d == 3 and curr_l >= ma_ref and curr_c >= close_1d: curr_eval = 2
        elif cond_bear: curr_eval = 9

        # --- 信号产生 ---
        t_sig = 5
        # 买一：启动确认
        if eval_1d == 1 and curr_eval == 2 and curr_o <= close_1d * 1.03:
            t_sig = 1
            
        # 买二：趋势中的均线回踩反包 (最低价曾靠近MA20/MA60 5%以内，且今日大阳线反包)
        near_support = (curr_l <= df['ma20d'].iloc[i] * 1.05) or (curr_l <= ma60_curr * 1.05)
        if eval_1d in [1, 2, 3] and near_support and is_big_yang:
            t_sig = 2
            
        # 卖出：破位
        elif eval_1d in [1, 2, 3] and curr_eval == 9:
            t_sig = -1

        eval_state[i] = curr_eval
        trade_signal[i] = t_sig

    df['eval_state'] = eval_state
    df['trade_signal'] = trade_signal

    # Print ALL signals and cycle transitions
    holding = False
    buy_price = 0.0
    total_profit = 0.0
    
    print(f"{'Date':<12} | {'Close':<6} | {'Pct%':<6} | {'Cycle':<5} | {'State':<5} | {'Action':<18} | {'Profit'}")
    print("-" * 80)
    
    last_cycle = None
    
    for idx, row in df.iterrows():
        pct = 0
        if pd.notna(row['lastp1d']) and row['lastp1d'] > 0:
            pct = (row['close'] - row['lastp1d']) / row['lastp1d'] * 100
            
        cycle_str = {1: '1-BTM', 2: '2-UP', 3: '3-EXH', 4: '4-TOP'}.get(row['cycle_stage'], str(row['cycle_stage']))
        state_str = {1: '1-Start', 2: '2-Main', 3: '3-Pull', 9: '9-Bear'}.get(row['eval_state'], str(row['eval_state']))
        
        sig = row['trade_signal']
        action_str = "-"
        
        if sig == 1:
            action_str = "BUY 1 (Start)"
            if not holding:
                holding = True
                buy_price = row['close']
        elif sig == 2:
            action_str = "BUY 2 (Pullback)"
            if not holding:
                holding = True
                buy_price = row['close']
        elif sig == -1:
            action_str = "SELL (Break)"
            if holding:
                profit = (row['close'] - buy_price) / buy_price * 100
                total_profit += profit
                action_str += f" PNL:{profit:.1f}%"
                holding = False
                
        # Hard stop if cycle_stage goes to 4 (Top/Falling)
        if holding and row['cycle_stage'] == 4 and sig != -1:
             profit = (row['close'] - buy_price) / buy_price * 100
             total_profit += profit
             action_str = f"STOP (Top) PNL:{profit:.1f}%"
             holding = False
             
        should_print = False
        if sig != 5 or action_str != "-":
            should_print = True
        if row['cycle_stage'] != last_cycle:
            should_print = True
            
        if name == 'TongDing' and str(idx) >= '2026-06-01':
            should_print = True
            
        if should_print:
            ma60 = row.get('ma60d', row.get('ma20d', 0))
            print(f"{str(idx)[:10]:<12} | {row['close']:<8.2f} | {pct:>5.1f}% | {cycle_str:<6} | {state_str:<7} | {action_str:<18} | MA5:{row['ma5d']:.2f} MA60:{ma60:.2f}")
            
        last_cycle = row['cycle_stage']

    print("-" * 80)
    print(f"[{name}] Full History Simulated PNL: {total_profit:.2f}%\n")

if __name__ == "__main__":
    stocks = [
        ('600460', 'ShiLanWei'),
        ('603083', 'CambridgeTech'),
        ('601869', 'Changfei'),
        ('002491', 'TongDing'),
        ('688158', 'UCloud') 
    ]
    # 直接输出到控制台，以便立即看到结果
    for code, name in stocks:
        test_stock_signals(code, name)

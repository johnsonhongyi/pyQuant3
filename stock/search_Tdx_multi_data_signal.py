import os
import struct
import sys
import time
import pandas as pd

sys.path.append('../../')
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
from JSONData import tdx_data_Day as tdd
from JSONData import sina_data


import pandas as pd
import numpy as np

# ----------------------
# 1️⃣ 计算布林带
# ----------------------
def compute_bollinger(df_stock, n=20, k=2):
    df = df_stock.copy()
    df['ma'] = df['close'].rolling(n).mean()
    df['std'] = df['close'].rolling(n).std()
    df['upper'] = df['ma'] + k * df['std']
    df['lower'] = df['ma'] - k * df['std']
    return df

# ----------------------
# 2️⃣ 生成 bullish_breakout 信号
# ----------------------
def compute_bullish_breakout(df_stock, lookback=4):
    df = df_stock.copy()
    df = compute_bollinger(df)
    df['high4'] = df['high'].rolling(lookback).max()
    df['bullish_breakout'] = (df['high'] > df['high4']) | (df['high'] > df['upper'])
    return df

# ----------------------
# 3️⃣ 跟踪 first / second 信号
# ----------------------
def track_bullish_signals(df_stock, breakout_col='bullish_breakout', gap=5, stop_loss_pct=0.05, take_profit_pct=0.15):
    df = df_stock.copy()

    # 如果是 MultiIndex
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index(['code','date'])
    else:
        df.index = pd.to_datetime(df.index)

    # 初始化
    df['bullish_first'] = False
    df['bullish_second'] = False
    df['signal_status'] = None
    df['entry_price'] = np.nan
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
    df['alert'] = False

    holding = False
    entry_price = None
    stop_loss = None
    take_profit = None

    # 找到所有突破信号
    signal_idx = df[df[breakout_col]].index
    signal_pos = df.index.get_indexer(signal_idx)
    last_pos = -gap*2

    # 区分第一次和第二次突破
    for pos, idx in zip(signal_pos, signal_idx):
        if pos - last_pos > gap:
            df.loc[idx, 'bullish_first'] = True
            df.loc[idx, 'signal_status'] = 'observing'
            df.loc[idx, 'alert'] = True
        else:
            df.loc[idx, 'bullish_second'] = True
            df.loc[idx, 'signal_status'] = 'holding'
            entry_price = df.loc[idx, 'close']
            df.loc[idx, 'entry_price'] = entry_price
            df.loc[idx, 'stop_loss'] = entry_price * (1 - stop_loss_pct)
            df.loc[idx, 'take_profit'] = entry_price * (1 + take_profit_pct)
            df.loc[idx, 'alert'] = True
        last_pos = pos

    return df

# ----------------------
# 4️⃣ 多股票批量处理
# ----------------------
def process_all_stocks(df):
    all_df = []
    for code, df_stock in df.groupby(level='code'):
        df_stock = compute_bullish_breakout(df_stock)
        df_stock = track_bullish_signals(df_stock)
        all_df.append(df_stock)
    return pd.concat(all_df)

# ----------------------
# 5️⃣ 使用示例
# ----------------------
# df 是原始大表，MultiIndex [code, date]，必须包含 ['open','high','low','close','vol','amount']
# df_processed = process_all_stocks(df)




if __name__ == '__main__':
    code_list = sina_data.Sina().market('all').index.tolist()
    code_list.extend(['999999','399001','399006'])
    print("all code:",len(code_list))
    duration = 300

    if duration <= 300 :
        h5_fname = 'tdx_all_df' + '_' + str(300)
        h5_table = 'all' + '_' + str(300)
    else:
        h5_fname = 'tdx_all_df' + '_' + str(900)
        h5_table = 'all' + '_' + str(900) 
        
        
    df = tdd.search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date')
    # df 是原始大表，MultiIndex [code, date]，必须包含 ['open','high','low','close','vol','amount']
    starttime = time.time()
    df_processed = process_all_stocks(df)
    print(f'total time : {time.time() -  starttime}')
    import ipdb;ipdb.set_trace()
    











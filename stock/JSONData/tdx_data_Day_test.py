import pandas as pd
import numpy as np
import os
import struct
import sys

import pandas as pd

sys.path.append('../')
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
from JSONData import tdx_data_Day as tdd
from JSONData import sina_data

# =============== 原版 (无 start_pos) =================
def track_bullish_signals_orig(df,
                               price_col='close',
                               high_col='high',
                               low_col='low',
                               upper_col='upper',
                               mid_col='ene',
                               ma26_col='ma20d',
                               lookback=60,
                               gap=5,
                               stop_loss_pct=0.05,
                               take_profit_pct=0.15):
    df = df.copy()
    signals = pd.Series(False, index=df.index)

    for i in range(lookback, len(df)):
        window = df.iloc[i-lookback:i+1]

        cond1 = (window[high_col].iloc[:-5] > window[upper_col].iloc[:-5]).any()
        cond2 = (window[low_col].iloc[:-5].min() > window[mid_col].iloc[:-5].min())
        cond3 = window[price_col].iloc[-1] > window[upper_col].iloc[-1]
        cond4 = window[price_col].iloc[-1] > window[ma26_col].iloc[-1]
        recent_high = window[high_col].iloc[:-1].max()
        cond5 = window[price_col].iloc[-1] > recent_high

        if cond1 and cond2 and cond3 and cond4 and cond5:
            signals.iloc[i] = True

    df['bullbreak'] = signals
    df['bull_f'] = False
    df['bull_s'] = False
    df['entry'] = np.nan
    df['sl'] = np.nan
    df['tp'] = np.nan
    df['alert'] = False

    signal_idx = df.index[df['bullbreak']].tolist()
    last_pos = -gap*2

    for idx in signal_idx:
        pos = df.index.get_loc(idx)
        if pos - last_pos > gap:
            df.at[idx, 'bull_f'] = True
            df.at[idx, 'alert'] = True
        else:
            df.at[idx, 'bull_s'] = True
            df.at[idx, 'alert'] = True
            entry_price = df.at[idx, price_col]
            df.at[idx, 'entry'] = entry_price
            df.at[idx, 'sl'] = entry_price * (1 - stop_loss_pct)
            df.at[idx, 'tp'] = entry_price * (1 + take_profit_pct)
        last_pos = pos

    df['obs_d'] = 0
    df['hold_d'] = 0
    df['status'] = -101
    df['has_first'] = False

    first_occurred = False
    observing_count = 0
    holding_count = 0

    for idx, row in df.iterrows():
        if row['bull_f']:
            first_occurred = True
            observing_count = 1
            holding_count = 0
            df.at[idx, 'status'] = 'observing'
        elif row['bull_s']:
            holding_count = 1
            df.at[idx, 'status'] = 'holding'
        elif holding_count > 0:
            holding_count += 1
            df.at[idx, 'status'] = 'holding'
        elif first_occurred and observing_count > 0:
            observing_count += 1
            df.at[idx, 'status'] = 'observing'
        else:
            df.at[idx, 'status'] = -101

        df.at[idx, 'has_first'] = first_occurred
        df.at[idx, 'obs_d'] = observing_count
        df.at[idx, 'hold_d'] = holding_count

    return df


# =============== start_pos 版 =================
def track_bullish_signals_startpos(df,
                                   price_col='close',
                                   high_col='high',
                                   low_col='low',
                                   upper_col='upper',
                                   mid_col='ene',
                                   ma26_col='ma20d',
                                   lookback=60,
                                   gap=5,
                                   stop_loss_pct=0.05,
                                   take_profit_pct=0.15):
    df = df.copy()
    valid_start = df[upper_col].replace(0, np.nan).first_valid_index()
    if valid_start is None:
        return df

    start_pos = df.index.get_loc(valid_start)
    signals = pd.Series(False, index=df.index)

    for i in range(max(lookback, start_pos), len(df)):
        window = df.iloc[i-lookback:i+1]

        cond1 = (window[high_col].iloc[:-5] > window[upper_col].iloc[:-5]).any()
        cond2 = (window[low_col].iloc[:-5].min() > window[mid_col].iloc[:-5].min())
        cond3 = window[price_col].iloc[-1] > window[upper_col].iloc[-1]
        cond4 = window[price_col].iloc[-1] > window[ma26_col].iloc[-1]
        recent_high = window[high_col].iloc[:-1].max()
        cond5 = window[price_col].iloc[-1] > recent_high

        if cond1 and cond2 and cond3 and cond4 and cond5:
            signals.iloc[i] = True

    df['bullbreak'] = signals
    df['bull_f'] = False
    df['bull_s'] = False
    df['entry'] = np.nan
    df['sl'] = np.nan
    df['tp'] = np.nan
    df['alert'] = False

    signal_idx = df.index[df['bullbreak']].tolist()
    last_pos = -gap*2

    for idx in signal_idx:
        pos = df.index.get_loc(idx)
        if pos - last_pos > gap:
            df.at[idx, 'bull_f'] = True
            df.at[idx, 'alert'] = True
        else:
            df.at[idx, 'bull_s'] = True
            df.at[idx, 'alert'] = True
            entry_price = df.at[idx, price_col]
            df.at[idx, 'entry'] = entry_price
            df.at[idx, 'sl'] = entry_price * (1 - stop_loss_pct)
            df.at[idx, 'tp'] = entry_price * (1 + take_profit_pct)
        last_pos = pos

    df['obs_d'] = 0
    df['hold_d'] = 0
    df['status'] = -101
    df['has_first'] = False

    first_occurred = False
    observing_count = 0
    holding_count = 0

    for idx, row in df.iterrows():
        if row['bull_f']:
            first_occurred = True
            observing_count = 1
            holding_count = 0
            df.at[idx, 'status'] = 'observing'
        elif row['bull_s']:
            holding_count = 1
            df.at[idx, 'status'] = 'holding'
        elif holding_count > 0:
            holding_count += 1
            df.at[idx, 'status'] = 'holding'
        elif first_occurred and observing_count > 0:
            observing_count += 1
            df.at[idx, 'status'] = 'observing'
        else:
            df.at[idx, 'status'] = -101

        df.at[idx, 'has_first'] = first_occurred
        df.at[idx, 'obs_d'] = observing_count
        df.at[idx, 'hold_d'] = holding_count

    return df


# =============== 测试对比 =================
if __name__ == "__main__":
    # 假设你已经有 df (包含 close, high, low, upper, ene, ma20d)
    code='600895'
    # df = tdd.get_tdx_Exp_day_to_df(code,dl=ct.duration_date_day,resample='d',lastday=None )
    df = tdd.get_tdx_Exp_day_to_df(code,dl=120,resample='3d',lastday=None )
    print(df[['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d']].tail(10))
    cols_to_drop = ['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d']
    df = df.drop(columns=cols_to_drop)
    # print(df[['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d']].tail(10))
    print(df.columns.values,df.shape)
    df_orig = track_bullish_signals_orig(df, lookback=30)
    df_start = track_bullish_signals_startpos(df, lookback=30)

    print("=== 原版 tail(10) ===")
    print(df_orig[['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d']].tail(10))
    print("\n=== start_pos tail(10) ===")
    print(df_start[['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d']].tail(10))

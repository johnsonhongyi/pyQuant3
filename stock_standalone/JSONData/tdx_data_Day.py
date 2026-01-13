# encoding: utf-8
# !/usr/bin/python


import os
import sys
sys.path.append("..")
import time
from struct import *
import numpy as np
import pandas as pd
from pandas import Series
from JSONData import tdx_hdf5_api as h5a
from JSONData import realdatajson as rl
from JSONData import wencaiData as wcd
from JSONData import tdxbk
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx
from JohnsonUtil import johnson_cons as ct
import tushare as ts
import pandas_ta as ta
import talib
from JSONData import sina_data
# import numba as nb
import datetime
import random
from collections import deque
import traceback
# import logbook
from collections import deque
from io import StringIO

log = LoggerFactory.getLogger()

path_sep = os.path.sep
newdaysinit = ct.newdays_limit_days
changedays = 0
global initTdxdata, initTushareCsv
initTdxdata = 0
initTushareCsv = 0
atomStockSize = 50
# tdx_index_code_list = ['999999', '399001']
tdx_index_code_list = ['999999', '399006', '399005', '399001']
# win7rootAsus = r'D:\Program Files\gfzq'
# win10Lengend = r'D:\Program\gfzq'
# win7rootXunji = r'E:\DOC\Parallels\WinTools\zd_pazq'
# win7rootList = [win7rootAsus,win7rootXunji,win10Lengend]
# macroot = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq'
# xproot = r'E:\DOC\Parallels\WinTools\zd_pazq'
import warnings
warnings.filterwarnings("ignore")

def get_tdx_dir():
    return cct.get_tdx_dir()

def get_tdx_dir_blocknew():
    return cct.get_tdx_dir_blocknew()
#     blocknew_path = get_tdx_dir() + r'/T0002/blocknew/'.replace('/', path_sep).replace('\\', path_sep)
#     return blocknew_path

basedir = get_tdx_dir()
blocknew = get_tdx_dir_blocknew()
# blocknew = r'/Users/Johnson/Documents/Johnson/WinTools/zd_pazq/T0002/blocknew'
# blocknew = 'Z:\Documents\Johnson\WinTools\zd_pazq\T0002\blocknew'
lc5_dir_sh = basedir + r'\Vipdoc\sh\fzline'
lc5_dir_sz = basedir + r'\Vipdoc\sz\fzline'
lc5_dir = basedir + r'\Vipdoc\%s\fzline'
 # "D:\MacTools\WinTools\new_tdx2\vipdoc\bj\lday\\sh601628.day"
# day_dir = basedir + r'\Vipdoc\%s\lday/'
# day_dir = os.path.join(basedir, "Vipdoc", market, "lday")
# day_dir_sh = basedir + r'\Vipdoc\sh\lday/'
# day_dir_sz = basedir + r'/Vipdoc/sz/lday/'
day_dir_sh = os.path.join(basedir, "Vipdoc", "sh", "lday")
day_dir_sz = os.path.join(basedir, "Vipdoc", "sz", "lday")
day_dir_bj = os.path.join(basedir, "Vipdoc", "bj", "lday")

# exp_path = basedir + \
#     "/T0002/export/".replace('/', path_sep).replace('\\', path_sep)
exp_path = os.path.join(basedir, "T0002", "export")

day_path = {'sh': day_dir_sh, 'sz': day_dir_sz ,'bj': day_dir_bj}
resample_dtype = ['d', 'w', 'm','3d','5d']
# http://www.douban.com/note/504811026/


def get_code_file_path(code, type='f'):
    if code == None:
        raise Exception("code is None")
    # os.path.getmtime(ff)
    code_u = cct.code_to_symbol(code)
    # if type == 'f':
    #     file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    # elif type == 'b':
    #     file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    # else:
    #     return None
    base = 'forwardp' if type == 'f' else 'backp'
    file_path = os.path.join(exp_path, base, f"{code_u.upper()}.txt")

    return file_path


def get_kdate_data(code, start='', end='', ktype='D', index=False,ascending=False):
    '''
        write get_k_data to tdx volume *100
    '''
    if start is None:
        start = ''
    if end is None:
        end = ''
    if code.startswith('999'):
        index = True
        code = str(1000000 - int(code)).zfill(6)
    elif code.startswith('399'):
        index = True

    # df = ts.get_k_data(code=code, start=start, end=end, ktype=ktype,
    # autype='qfq', index=index, retry_count=3, pause=0.001)
    if start == '' and end != '' and end is not None:
        df = ts.get_k_data(code=code, ktype=ktype, index=index)
        df = df[df.date <= end]
    else:
        df = ts.get_k_data(code=code, start=start, end=end,
                           ktype=ktype, index=index)
    if len(df) > 0:
        df.set_index('date', inplace=True)
        df.sort_index(ascending=ascending, inplace=True)
        lastdy = df.index[0]
        if cct.get_work_hdf_status() and cct.get_today_duration(lastdy) == 0:
            df.drop(lastdy, axis=0, inplace=True)
            # print df.index
        df['volume'] = df.volume.apply(lambda x: x * 100)
    return df

def LIS_TDX(X):


    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.92,  22.98,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.92, 22.98], [0, 1, 2, 3, 4, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.98,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.98], [0, 1, 2, 3, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.96,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.68, 22.96], [0, 1, 2, 3, 5])
    # ipdb> LIS_TDX([ 20.57,  21.35,  22.04,  22.68,  22.98,  22.06,  22.58,  22.23,21.81,  21.57])
    # ([20.57, 21.35, 22.04, 22.06, 22.23], [0, 1, 2, 5, 7])

    N = len(X)
    P = [0] * N
    M = [0] * (N + 1)
    L = 0
    for i in range(N):
        lo = 1
        hi = L
        while lo <= hi:
            mid = (lo + hi) // 2
            if (X[M[mid]] < X[i]):
                lo = mid + 1
            else:
                hi = mid - 1

        newL = lo
        P[i] = M[newL - 1]
        M[newL] = i

        if (newL > L):
            L = newL

    S = []
    pos = []
    k = M[L]

    for i in range(L - 1, -1, -1):
        S.append(round(X[k],2))
        pos.append(k)
        k = P[k]
    return S[::-1], pos[::-1]

def LIS_TDX_Cum(X):
    #Lis 逐级升高,重复break
    #
    N = len(X)
    P = [0] * N
    M = [0] * (N + 1)
    L = 0
    init_break=False
    for i in range(N):
        lo = 1
        hi = L
        while lo <= hi:
            mid = (lo + hi) // 2
            if (X[M[mid]] < X[i]):
                lo = mid + 1
            else:
                #出现新低 newLow LIS ma5d               
                hi = mid - 1
                init_break = True
        if init_break:
            #出现新低 newLow LIS ma5d 
            break        
        newL = lo
        P[i] = M[newL - 1]
        M[newL] = i

        if (newL > L):
            L = newL

    S = []
    pos = []
    k = M[L]
    idx = 0
    for i in range(L - 1, -1, -1):

        if idx == 0:
            idx = k
        else:
            if k + 1 != idx:
                break
            else:
                idx = k
        S.append(round(X[k], 2))
        pos.append(k)
        k = P[k]

    return S[::-1], pos[::-1]


def get_ascending_is_monotonic_decreasing(df,increasing=True):
    if not df.index.is_monotonic_increasing:
        increasing = False
        df = df.sort_index(ascending=True)

    #return default increasing
    # if not increasing:
    #     df = df.sort_index(ascending=False)
    # no ok
    return df

def write_all_kdata_to_file(code, f_path, df=None):
    """

    Function: write_all_kdata_to_file

    Summary: InsertHere

    Examples: InsertHere

    Attributes: 

        @param (code):InsertHere

        @param (f_path):InsertHere

        @param (df) default=None: InsertHere

    Returns: InsertHere

    """
    fsize = os.path.getsize(f_path)
    if fsize != 0:
        o_file = open(f_path, 'w+')
        o_file.truncate()
        o_file.close()
    if df is None:
        df = get_kdate_data(code)
    write_tdx_tushare_to_file(code, df=df)
    print("writeCode:%s size:%s" % (code, os.path.getsize(f_path) / 50))


def custom_macd(prices, fastperiod=12, slowperiod=26, signalperiod=9):
   """
 自定义的MACD计算函数，根据指定的计算方法计算EMA，然后基于这些EMA值计算MACD值。

 :param prices: 价格数组。
 :param fastperiod: 快速EMA的周期，默认为12。
 :param slowperiod: 慢速EMA的周期，默认为26。
 :param signalperiod: 信号线的周期，默认为9。
 :return: 返回DIFF, DEA和MACD。
   """
   # 初始化EMA数组
   ema_fast = np.zeros_like(prices)
   ema_slow = np.zeros_like(prices)

   # 计算EMA
   for i in range(1, len(prices)):
       if i == 1:  # 第二日的EMA计算
            ema_fast[i] = prices[i - 1] + (prices[i] - prices[i - 1]) * 2 / (fastperiod + 1)
            ema_slow[i] = prices[i - 1] + (prices[i] - prices[i - 1]) * 2 / (slowperiod + 1)
       else:  # 第三日及以后的EMA计算
            ema_fast[i] = ema_fast[i - 1] * (fastperiod - 1) / (fastperiod + 1) + prices[i] * 2 / (fastperiod + 1)
            ema_slow[i] = ema_slow[i - 1] * (slowperiod - 1) / (slowperiod + 1) + prices[i] * 2 / (slowperiod + 1)

   # 计算DIFF
   diff = ema_fast - ema_slow

   # 计算DEA
   dea = np.zeros_like(prices)
   for i in range(1, len(prices)):
        dea[i] = ((signalperiod - 1) * dea[i - 1] + 2 * diff[i]) / (signalperiod + 1)
   # 计算MACD
   macd = 2 * (diff - dea)
   return diff, dea, macdmmm

def detect_bullish_breakout(df, 
                            price_col='close', 
                            high_col='high', 
                            low_col='low', 
                            upper_col='upper', 
                            mid_col='ene', 
                            ma26_col='ma20d',
                            lookback=60):
    """
    识别多头爆发形态：
    1. 最近 lookback 天内至少一次冲击过上轨 upper
    2. 回落时没有有效跌破 mid
    3. 当前价格重新突破 upper（二次突破）
    4. 站上 ma26，且突破近期高点
    
    返回: 一个 Series，标记每个交易日是否符合形态
    """

    price = df[price_col]
    high = df[high_col]
    low = df[low_col]
    upper = df[upper_col]
    mid = df[mid_col]
    ma26 = df[ma26_col]

    signals = pd.Series(False, index=df.index)

    for i in range(lookback, len(df)):
        window = df.iloc[i-lookback:i+1]

        # Step 1: 曾经冲击过上轨
        cond1 = (window[high_col].iloc[:-5] > window[upper_col].iloc[:-5]).any()

        # Step 2: 回落时守住 mid
        cond2 = (window[low_col].iloc[:-5].min() > window[mid_col].iloc[:-5].min())

        # Step 3: 当前突破 upper
        cond3 = window[price_col].iloc[-1] > window[upper_col].iloc[-1]

        # Step 4: 当前在 ma26 上方
        cond4 = window[price_col].iloc[-1] > window[ma26_col].iloc[-1]

        # Step 5: 突破近期高点
        recent_high = window[high_col].iloc[:-1].max()
        cond5 = window[price_col].iloc[-1] > recent_high

        if cond1 and cond2 and cond3 and cond4 and cond5:
            signals.iloc[i] = True

    return signals

def track_bullish_signals_simple(df, breakout_col='bullbreak', gap=5, stop_loss_pct=0.05, take_profit_pct=0.15):
    """
    简单版本：单表处理 bullish_first 和 bullish_second，直接在 df 中增加列
    """
    df = df.copy()
    # df.index = pd.to_datetime(df.index)

    # 找到 upper 有效的开始位置
    valid_start = df['upper'].replace(0, np.nan).first_valid_index()
    if valid_start is None:
        return df  # 没有可用 upper，直接返回

    df['bullbreak'] = detect_bullish_breakout(df)


    df['bull_f'] = False
    df['bull_s'] = False
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
            df.loc[idx, 'bull_f'] = True
            df.loc[idx, 'signal_status'] = 'observing'
            df.loc[idx, 'alert'] = True
        else:
            df.loc[idx, 'bull_s'] = True
            df.loc[idx, 'signal_status'] = 'holding'
            entry_price = df.loc[idx, 'close']
            df.loc[idx, 'entry_price'] = entry_price
            df.loc[idx, 'stop_loss'] = entry_price * (1 - stop_loss_pct)
            df.loc[idx, 'take_profit'] = entry_price * (1 + take_profit_pct)
            df.loc[idx, 'alert'] = True
        last_pos = pos

    df = track_bullish_status(df)

    return df


def track_bullish_status(df):
    df = df.copy()
    
    df['has_first'] = False
    df['obs_d'] = 0
    df['hold_d'] = 0
    df['status'] = None
    
    first_occurred = False
    observing_count = 0
    holding_count = 0
    
    for idx, row in df.iterrows():
        # 第一次突破
        if row.get('bull_f', False):
            first_occurred = True
            observing_count = 1
            holding_count = 0
            df.loc[idx, 'status'] = 'observing'
        
        # 第二次突破
        elif row.get('bull_s', False):
            holding_count = 1
            df.loc[idx, 'status'] = 'holding'
        
        # 持仓延续
        elif holding_count > 0:
            holding_count += 1
            df.loc[idx, 'status'] = 'holding'
        
        # 观察延续（第一次突破后）
        elif first_occurred and observing_count > 0:
            observing_count += 1
            df.loc[idx, 'status'] = 'observing'
        
        else:
            df.loc[idx, 'status'] = None
        
        # 保存累计信息
        df.loc[idx, 'has_first'] = first_occurred
        df.loc[idx, 'obs_d'] = observing_count
        df.loc[idx, 'hold_d'] = holding_count
    
    return df


    # 使用示例
    # df 是单只股票的 DataFrame，包含 bullish_first / bullish_second / bullish_breakout
    # df_tracked = track_bullish_status(df)

    # # 查看最后几行
    # print(df[['bull_f','bull_s','bullbreak','has_first','status','hold_d']].tail(10))


# =============== start_pos 版 =================
def track_bullish_signals_startpos(df,
                                   price_col='close',
                                   high_col='high',
                                   low_col='low',
                                   upper_col='upper',
                                   mid_col='ene',
                                   ma26_col='ma20d',
                                   lookback=30,
                                   gap=5,
                                   stop_loss_pct=0.05,
                                   take_profit_pct=0.15):
    # Vectorized implementation
    df = df.copy()
    
    # Ensure columns exist to avoid errors
    if not all(col in df.columns for col in [price_col, high_col, low_col, upper_col, mid_col, ma26_col]):
        return df

    # Breakout condition Boolean Series
    high_gt_upper = (df[high_col] > df[upper_col])
    
    # Cond1: Any breakout in the past (excluding recent 5 days)
    # Rolling max of boolean gives 1.0 if any True.
    rolling_window_1 = max(1, lookback - 4)
    cond1 = high_gt_upper.rolling(window=rolling_window_1).max().shift(5).fillna(0).astype(bool)

    # Cond2: Min(Low) > Min(Mid) in [i-lookback, i-5)
    low_rolling_min = df[low_col].rolling(window=rolling_window_1).min().shift(5)
    mid_rolling_min = df[mid_col].rolling(window=rolling_window_1).min().shift(5)
    cond2 = (low_rolling_min > mid_rolling_min)
    
    # Cond3: Current Price > Current Upper
    cond3 = df[price_col] > df[upper_col]
    
    # Cond4: Current Price > Current MA26
    cond4 = df[price_col] > df[ma26_col]
    
    # Cond5: Current Price > Recent High (in [i-lookback, i)) => window[:-1].max()
    recent_high = df[high_col].rolling(window=lookback).max().shift(1)
    cond5 = df[price_col] > recent_high
    
    # Combine conditions
    signals = cond1 & cond2 & cond3 & cond4 & cond5
    
    df['bullbreak'] = signals
    df['bull_f'] = False
    df['bull_s'] = False
    df['entry'] = np.nan
    df['sl'] = np.nan
    df['tp'] = np.nan
    df['alert'] = False

    # Vectorized Signal Processing
    # We still need to iterate through signals to handle 'gap' logic which is state dependent relative to last signal
    # But since signals are sparse, we iterate only over True indices
    
    signal_indices = np.where(signals)[0]
    last_pos = -gap * 2
    
    for pos in signal_indices:
        idx = df.index[pos]
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

    # Status tracking loop: 'observing' / 'holding' 
    # Optimized loop using arrays
    status_values = np.full(len(df), -101, dtype=object)
    has_first_values = np.zeros(len(df), dtype=bool)
    obs_d_values = np.zeros(len(df), dtype=int)
    hold_d_values = np.zeros(len(df), dtype=int)
    
    bull_f_arr = df['bull_f'].values
    bull_s_arr = df['bull_s'].values
    
    first_occurred = False
    observing_count = 0
    holding_count = 0
    
    for i in range(len(df)):
        if bull_f_arr[i]:
            first_occurred = True
            observing_count = 1
            holding_count = 0
            status_values[i] = 'observing'
        elif bull_s_arr[i]:
            holding_count = 1
            status_values[i] = 'holding'
        elif holding_count > 0:
            holding_count += 1
            status_values[i] = 'holding'
        elif first_occurred and observing_count > 0:
            observing_count += 1
            status_values[i] = 'observing'
        else:
            status_values[i] = -101
            
        has_first_values[i] = first_occurred
        obs_d_values[i] = observing_count
        hold_d_values[i] = holding_count
        
    df['status'] = status_values
    df['has_first'] = has_first_values
    df['obs_d'] = obs_d_values
    df['hold_d'] = hold_d_values

    return df


def track_bullish_signals_optimized(df,
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
    """
    完整版本：
    1. 检测 bullish_breakout
    2. 区分 bullish_first / bullish_second
    3. 计算观察天数 / 持仓天数 / 状态 / has_first_occurred
    4. 支持 entry_price / stop_loss / take_profit / alert
    """
    df = df.copy()

    price = df[price_col]
    high = df[high_col]
    low = df[low_col]
    upper = df[upper_col]
    mid = df[mid_col]
    ma26 = df[ma26_col]


    valid_start = df['upper'].replace(0, np.nan).first_valid_index()
    if valid_start is None:
        return df  # 没有有效 upper，直接返回

    # # 将 index 转为位置
    # start_pos = df.index.get_loc(valid_start)
    # lookback = start_pos
    # ------------------------
    # Step1: 计算 bullish_breakout
    # ------------------------
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

    # ------------------------
    # Step2: 区分第一次/第二次突破
    # ------------------------
    df['bull_f'] = False
    df['bull_s'] = False
    df['entry_price'] = np.nan
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
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
            df.at[idx, 'entry_price'] = entry_price
            df.at[idx, 'stop_loss'] = entry_price * (1 - stop_loss_pct)
            df.at[idx, 'take_profit'] = entry_price * (1 + take_profit_pct)
        last_pos = pos

    # ------------------------
    # Step3: 计算 observing_days / holding_days / status / has_first_occurred
    # ------------------------
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



 

def track_bullish_signals_vectorized_full(
        df,
        price_col='close',
        high_col='high',
        low_col='low',
        upper_col='upper',
        mid_col='ene',
        ma26_col='ma20d',
        lookback=60,
        gap=5,
        stop_loss_pct=0.05,
        take_profit_pct=0.15
    ):
    df = df.copy()

    price = df[price_col]
    high = df[high_col]
    low = df[low_col]
    upper = df[upper_col]
    mid = df[mid_col]
    ma26 = df[ma26_col]

    # =======================
    # Step1: bullish_breakout
    # =======================
    recent_high = high.shift(1).rolling(lookback).max()
    recent_upper = upper.shift(1).rolling(lookback).max()
    recent_low = low.shift(1).rolling(lookback).min()
    recent_mid = mid.shift(1).rolling(lookback).min()

    cond1 = recent_high > recent_upper
    cond2 = recent_low > recent_mid
    cond3 = price > upper
    cond4 = price > ma26
    cond5 = price > recent_high

    df['bullbreak'] = (cond1 & cond2 & cond3 & cond4 & cond5).fillna(False)

    # =======================
    # Step2: bullish_first / bullish_second
    # =======================
    signal_idx = np.flatnonzero(df['bullbreak'].values)
    bullish_first = np.zeros(len(df), dtype=bool)
    bullish_second = np.zeros(len(df), dtype=bool)

    entry_price = np.full(len(df), np.nan)
    stop_loss = np.full(len(df), np.nan)
    take_profit = np.full(len(df), np.nan)

    last_pos = -gap*2
    for pos in signal_idx:
        if pos - last_pos > gap:
            bullish_first[pos] = True
        else:
            bullish_second[pos] = True
            entry_price[pos] = price.iloc[pos]
            stop_loss[pos] = price.iloc[pos] * (1 - stop_loss_pct)
            take_profit[pos] = price.iloc[pos] * (1 + take_profit_pct)
        last_pos = pos

    df['bull_f'] = bullish_first
    df['bull_s'] = bullish_second
    df['entry_price'] = entry_price
    df['stop_loss'] = stop_loss
    df['take_profit'] = take_profit

    # =======================
    # Step3: has_first_occurred
    # =======================
    df['has_first'] = df['bull_f'].cumsum() > 0

    # =======================
    # Step4: observing_days / holding_days
    # =======================
    obs_days = np.zeros(len(df), dtype=int)
    hold_days = np.zeros(len(df), dtype=int)

    obs_counter = 0
    hold_counter = 0
    for i in range(len(df)):
        if df['bull_f'].iloc[i]:
            obs_counter = 1
            hold_counter = 0
        elif df['bull_s'].iloc[i]:
            hold_counter = 1
            obs_counter = 0
        else:
            if obs_counter > 0:
                obs_counter += 1
            if hold_counter > 0:
                hold_counter += 1
        obs_days[i] = obs_counter
        hold_days[i] = hold_counter

    df['obs_d'] = obs_days
    df['hold_d'] = hold_days

    # =======================
    # Step5: status
    # =======================
    df['status'] = np.where(df['hold_d'] > 0, 'holding',
                            np.where(df['obs_d'] > 0, 'observing', -101))

    return df


def detect_local_extremes_filtered(df, N=10, tol_pct=0.01):
    """
    动态识别局部高低点和极点，并只在最后一天放置中枢相关值。
    
    df: 包含 'high', 'low', 'close' 列的 DataFrame
    N: 计算局部高低点的滚动窗口长度
    tol_pct: 极值容差百分比
    """
    df = df.copy()
    # 1. 原始局部高低点
    LLV_L_N = df['low'].rolling(N, min_periods=1).min()
    HHV_H_N = df['high'].rolling(N, min_periods=1).max()
    
    df['局部低点'] = np.where(df['low'] <= LLV_L_N * (1 + tol_pct), -1, 0)
    df['局部高点'] = np.where(df['high'] >= HHV_H_N * (1 - tol_pct), 1, 0)
    
    # 2. 只保留窗口内极值
    low_idx = np.where(df['局部低点'] != 0)[0]
    high_idx = np.where(df['局部高点'] != 0)[0]
    
    for i in low_idx:
        if df['low'].iloc[max(0, i-N+1):i+1].idxmin() == df.index[i]:
            df.at[df.index[i], '局部低点'] = -1
        else:
            df.at[df.index[i], '局部低点'] = 0

    for i in high_idx:
        if df['high'].iloc[max(0, i-N+1):i+1].idxmax() == df.index[i]:
            df.at[df.index[i], '局部高点'] = 1
        else:
            df.at[df.index[i], '局部高点'] = 0
    
    # 3. 极点和局部极点
    # df['极点'] = df['局部高点'] + df['局部低点']
    # df['局部极点'] = df['close'].where(df['极点'] != 0, np.nan)
    
    # 4. 中枢上轨/下轨，只保留最后一天有效
    high_peaks = df['high'].where(df['局部高点'] == 1)
    low_troughs = df['low'].where(df['局部低点'] == -1)
    
    df['ZSH'] = high_peaks.max()  # 最大高点
    df['ZSL'] = low_troughs.min()  # 最小低点
    
    # 清空列，只在最后一天放置值
    df['ZSH'] = np.nan
    df['ZSL'] = np.nan
    if not high_peaks.dropna().empty:
        df.at[df.index[-1], 'ZSH'] = high_peaks.dropna().iloc[-1]
    if not low_troughs.dropna().empty:
        df.at[df.index[-1], 'ZSL'] = low_troughs.dropna().iloc[-1]

    return df

# ============================================
# ============   技术指标整合版   =============
# ============================================

def calc_support_resistance(df):

    LLV = lambda x, n: x.rolling(n, min_periods=1).min()
    HHV = lambda x, n: x.rolling(n, min_periods=1).max()
    SMA = lambda x, n, m: x.ewm(alpha=m/n, adjust=False).mean()

    # --- 短周期 ---
    RSV13 = (df['close'] - LLV(df['low'], 13)) / (HHV(df['high'], 13) - LLV(df['low'], 13)) * 100
    ARSV = SMA(RSV13, 3, 1)
    AK = SMA(ARSV, 3, 1)
    AD = (3 * ARSV) - (2 * AK)

    # --- 长周期 ---
    RSV55 = (df['close'] - LLV(df['low'], 55)) / (HHV(df['high'], 55) - LLV(df['low'], 55)) * 100
    ARSV24 = SMA(RSV55, 3, 1)
    AK24 = SMA(ARSV24, 3, 1)
    AD24 = (3 * ARSV24) - (2 * AK24)

    # --- CROSS 检测 ---
    cross_up = (AD24 > AD) & (AD24.shift(1) <= AD.shift(1))

    # 通达信逻辑：撑 = IF(CROSS, HIGH, REF(HIGH, BARSLAST(CROSS)))
    pressure = []
    last_high = None
    last_cross_idx = None

    for i in range(len(df)):
        if cross_up.iloc[i]:
            last_high = df['high'].iloc[i]
            last_cross_idx = i
        elif last_high is not None and last_cross_idx is not None:
            # REF(HIGH, BARSLAST(...)) → 维持上次的高点
            last_high = df['high'].iloc[last_cross_idx]
        pressure.append(last_high)

    df['pressure'] = pressure

    # --- 支撑线 ---
    df['support'] = LLV(df['high'], 30)

    return df

def calc_support_resistance_vec(df):
    """
    矢量化计算支撑/压力位，参考通达信逻辑。
    df: DataFrame 包含 ['open','high','low','close']
    返回 df 增加 ['pressure','support']
    """
    LLV = lambda x, n: x.rolling(n, min_periods=1).min()
    HHV = lambda x, n: x.rolling(n, min_periods=1).max()
    SMA = lambda x, n, m: x.ewm(alpha=m/n, adjust=False).mean()

    # --- 短周期 ---
    RSV13 = (df['close'] - LLV(df['low'], 13)) / (HHV(df['high'], 13) - LLV(df['low'], 13)) * 100
    ARSV = SMA(RSV13, 3, 1)
    AK = SMA(ARSV, 3, 1)
    AD = 3 * ARSV - 2 * AK

    # --- 长周期 ---
    RSV55 = (df['close'] - LLV(df['low'], 55)) / (HHV(df['high'], 55) - LLV(df['low'], 55)) * 100
    ARSV24 = SMA(RSV55, 3, 1)
    AK24 = SMA(ARSV24, 3, 1)
    AD24 = 3 * ARSV24 - 2 * AK24

    # --- CROSS 检测 ---
    cross_up = (AD24 > AD) & (AD24.shift(1) <= AD.shift(1))

    # --- 压力位（pressure）矢量化 ---
    # 生成 cross_up 为 True 的索引对应的 high
    cross_high = df['high'].where(cross_up)

    # 用 ffill 填充，等价于 REF(HIGH, BARSLAST(CROSS)) 压力
    # resistance
    df['resist'] = cross_high.ffill()

    # --- 支撑位（support）矢量化 ---
    df['support'] = LLV(df['high'], 30)

    return df


def check_conditions_auto(df, days=6):
    """
    自动批量检查 DataFrame 条件 (Vectorized)：
    1. 对每行，检查每一天的条件：
       lasto <= lastl*1.002 and lastp > lasto and per > 1
    2. 最终条件：至少一天满足 + lastp1d > lastp2d
    返回 DataFrame 新增列：
      - MainU (字符串)
      - 满足天数 (逗号分隔字符串)
    """
    if df.empty:
        df['MainU'] = '0'
        return df

    # Initialize result string series
    # We will accumulate "i," for each satisfied day
    
    # Pre-calculate fill value (0) for missing columns to match row.get(col, 0)
    # Actually most pandas ops with 0 work fine.
    
    # We accumulate strings directly. Starting with empty strings.
    res_str = pd.Series("", index=df.index, dtype=object)
    
    for i in range(1, days + 1):
        # 构造列名
        str_i = str(i)
        lasto_col = f'lasto{str_i}d'
        lasto2_col = f'lasto{i+1}d'
        lastl_col = f'lastl{str_i}d'
        lastp_col = f'lastp{str_i}d'
        lasth_col = f'lasth{str_i}d'
        lastp2d_col = f'lastp{i+1}d'
        per_col   = f'per{str_i}d'
        # high4_col = f'high4{str_i}d'
        # hmax_col = f'hmax{str_i}d'
        high4_col = f'high4'
        hmax_col = f'hmax'
        ma5d_col = f'ma5{str_i}d'

        # Get columns efficiently, defaulting to 0
        def get_col(col_name):
            return df[col_name] if col_name in df.columns else 0

        lasto = get_col(lasto_col)
        # lasto2 = get_col(lasto2_col) # Not used in condition?
        lastl = get_col(lastl_col)
        lastp = get_col(lastp_col)
        lasth = get_col(lasth_col)
        lastp2d = get_col(lastp2d_col)
        per = get_col(per_col)
        high4 = get_col(high4_col)
        hmax = get_col(hmax_col)
        ma5d = get_col(ma5d_col)

        # Condition logic:
        # if (lasto <= lastl * 1.002 or (lasth > high4 and lasth >= hmax*0.99) or (lastp > ma5d and lastp >= lastp2d)) and (lastp >= lasto) and (per > 0):
        
        # Note: comparison with 0 (scalar) broadcasts correctly
        
        cond1 = (lasto <= lastl * 1.002)
        cond2 = (lasth > high4) & (lasth >= hmax * 0.99)
        cond3 = (lastp > ma5d) & (lastp >= lastp2d)
        
        # Combine
        # (cond1 or cond2 or cond3) and ...
        combined_cond = (cond1 | cond2 | cond3) & (lastp >= lasto) & (per > 0)
        
        # If combined_cond is True, append "i," to res_str
        # Using numpy where is faster than series apply
        # We need to ensure res_str is updated.
        # res_str += np.where(combined_cond, f"{i},", "")
        
        # Careful with types, ensure string
        to_add = np.where(combined_cond, f"{i},", "")
        res_str = res_str + to_add

    # Post-process
    # Remove trailing comma
    res_str = res_str.str.rstrip(',')
    # Replace empty with '0'
    res_str = res_str.replace('', '0')
    
    # Assign to new DataFrame/Column
    # Original returned concat of df and result (which was just MainU series)
    # We can just assign
    df = df.copy() # Avoid SettingWithCopy if necessary, though typical usage accepts modification or new df
    df['MainU'] = res_str
    
    return df

def boll_probe_stage(df, n=5, m=2):
    """
    Bollinger 试盘期（使用 high）
    """
    cond_probe_daily = (df['high'] >= df['upper']) & (df['close'] < df['upper']) & (df['upper'] > df['upper'].shift(1))

    cond_probe_continue = cond_probe_daily.rolling(n).sum() >= m

    cond_probe_alive = df['close'] >= df['mid']

    df['boll_probe'] = cond_probe_continue & cond_probe_alive

    return df

def boll_boost_stage(df, n=5, m=3):
    """
    Bollinger 主升期（使用 close）
    """
    cond_boost_daily = (df['close'] > df['upper']) & (df['upper'] > df['upper'].shift(1))

    cond_boost_continue = cond_boost_daily.rolling(n).sum() >= m

    cond_boost_alive = df['close'] >= df['mid']

    df['boll_boost'] = cond_boost_continue & cond_boost_alive

    return df

def boll_stage(df):
    """
    0: 非趋势
    1: 试盘期
    2: 主升期
    """
    stage = np.zeros(len(df), dtype=int)

    stage[df['boll_probe']] = 1
    stage[df['boll_boost']] = 2

    # 主升优先级最高
    stage[df['boll_boost']] = 2

    df['boll_stage'] = stage
    return df

def boll_trend_breakout(df, n=5, m=3):
    """
    趋势型 Bollinger 连续上轨突破判定
    返回：df['boll_trend_up']  (bool)
    """
    # 1. 单日基础条件
    cond_daily = (df['close'] > df['upper']) & (df['upper'] > df['upper'].shift(1))

    # 2. N 日内满足 M 次
    cond_continue = cond_daily.rolling(n).sum() >= m

    # 3. 趋势未被破坏（不跌破中轨）
    cond_trend_alive = df['close'] >= df['ene']

    df['boll_signal'] = cond_continue & cond_trend_alive

    return df

def intraday_trade_signal(df, vol_threshold=1.2, pullback_ratio=0.3):
    """
    盘中快速买卖信号
    df 必须包含字段: ['open','close','high','low','upper','amount','ma5d','ma10d','EVAL_STATE']
    trade_signal:
        1  -> 集合竞价高开买入
        2  -> 回撤低吸买入
        0  -> 保持/等待
       -1  -> 止损离场
    vol_threshold: 集合竞价量放大倍数
    pullback_ratio: 回撤低吸参考比例（相对前两日涨幅）
    """
    df = df.copy()
    df['trade_signal'] = 0

    for i in range(1, len(df)):
        state = df.at[df.index[i], 'EVAL_STATE']
        open_price = df.at[df.index[i], 'open']
        close_price = df.at[df.index[i], 'close']
        ma5 = df.at[df.index[i], 'ma5d']
        ma10 = df.at[df.index[i], 'ma10d']
        amount = df.at[df.index[i], 'amount']
        
        prev_close = df.at[df.index[i-1], 'close']
        prev_amount = df.at[df.index[i-1], 'amount']
        # 上两日涨幅参考
        if i >= 2:
            prev2_close = df.at[df.index[i-2], 'close']
            prev2_high = df.at[df.index[i-2], 'high']
        else:
            prev2_close = prev_close
            prev2_high = df.at[df.index[i-1], 'high']
        
        # 1️⃣ 集合竞价高开买入（快速响应）
        if state == 1 and open_price > prev_close and amount > prev_amount * vol_threshold and close_price > ma10:
            df.at[df.index[i], 'trade_signal'] = 1
        
        # 2️⃣ 回撤低吸
        elif state in [2,3]:
            # 前两日涨幅
            recent_gain = max(prev_close, prev2_high) - prev2_close
            pullback_level = prev2_close + recent_gain * (1 - pullback_ratio)
            if close_price <= pullback_level and close_price > ma10:
                df.at[df.index[i], 'trade_signal'] = 2
        
        # 3️⃣ 快速止损离场
        if close_price < ma5:
            df.at[df.index[i], 'trade_signal'] = -1

    return df

def extract_all_features(df, lastdays=5, code=None):
    """单只股票
    从 df 中提取最近 lastdays 的所有字段，返回一个字典：
    open/close/high/low/vol/ma/upper/per + evalNd/signalNd
    每个列做安全检查，更健壮
    code: 可选，单只股票代码，会加入字典中
    """
    features = {}
    # if code is not None:
    #     features['code'] = code  # 添加股票代码

    # 定义字段映射
    cols_map = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        'perd': 'per'
    }

    # 安全获取倒数 idx 行
    def safe_get(colname, idx, default=0):
        if colname in df.columns and len(df) >= idx:
            return df[colname].iloc[-idx]
        return default

    # 遍历最近 lastdays
    for da in range(1, lastdays + 1):
        for col, prefix in cols_map.items():
            features[f'{prefix}{da}d'] = safe_get(col, da)
        
        # eval 和 signal
        features[f'eval{da}d'] = safe_get(f'eval{da}d', 1)
        features[f'signal{da}d'] = safe_get(f'signal{da}d', 1)

    return features

def evaluate_realtime_signal_tick(rt_tick, daily_feat, mode='A'):
    """
    实时计算单个标的的交易信号
    :param rt_tick: 字典，包含当前实时行情 {'open', 'close', 'high', 'low', 'amount'}
    :param daily_feat: 字典，generate_df_vect_daily_features 返回的 1d 特征 (list中的第一个元素)
    :param mode: 'A' 强势优先, 'B' 风控优先
    :return: (current_state, trade_signal)
    """
        
    """
    自适应版本：自动处理数据类型
    """
    # --- 1. 类型自适应处理 ---
    # 如果 rt_tick 是 DataFrame 或 Series，提取标量值
    def get_val(obj, key):
        val = obj[key]
        # 如果是 Series 或数组，取第一个值 (.item() 或 .iloc[0])
        return val.iloc[0] if hasattr(val, 'iloc') else val

    # 映射字段（适配你的 sina 结构）
    curr_o = float(get_val(rt_tick, 'open'))
    curr_c = float(get_val(rt_tick, 'now'))   # 对应你 sina 里的 now
    curr_l = float(get_val(rt_tick, 'low'))
    # 优先取 amount，没有则取 volume
    curr_a = float(get_val(rt_tick, 'volume'))


    # 1. 数据映射 (实时数据与历史特征)

    # curr_o = rt_tick['open']
    # curr_c = rt_tick['close']
    # curr_l = rt_tick['low']
    # curr_a = rt_tick['volume']
    
    # 历史特征 (1d 代表昨天)
    upper_1d = daily_feat['upper1d']
    close_1d = daily_feat['lastp1d']
    amount_1d = daily_feat['lastv1d']
    eval_1d = int(daily_feat['eval1d'])
    ma10d_curr = daily_feat['ma51d'] # 假设实时判断的生命线使用昨日MA5作为参考

    if upper_1d <= 0:
        return 9, 5

    # 2. 条件判定 (基于实时 Tick)
    cond_trend_start = (curr_c > upper_1d) and (close_1d <= upper_1d) and (curr_a > amount_1d * 1.1)
    cond_trend_continue = (curr_c > upper_1d) and (close_1d > upper_1d)
    cond_pullback = (curr_c < close_1d) and (curr_l >= ma10d_curr) and (curr_a < amount_1d)
    cond_bear = (curr_c < ma10d_curr)

    # 3. 状态转移逻辑 (EVAL_STATE)
    curr_state = 9 # 默认值
    
    if mode == 'A': # 强势优先逻辑
        if cond_trend_start:
            curr_state = 1
        elif cond_bear:
            curr_state = 9
        elif cond_trend_continue:
            curr_state = 2
        elif cond_pullback and eval_1d in [2, 3]:
            curr_state = 3
        elif eval_1d == 3 and curr_l >= ma10d_curr:
            curr_state = 2
        else:
            curr_state = eval_1d # 维持昨日状态
            
    elif mode == 'B': # 风控优先逻辑
        if cond_bear:
            curr_state = 9
        elif cond_trend_start:
            curr_state = 1
        elif cond_trend_continue:
            curr_state = 2
        elif cond_pullback and eval_1d in [2, 3]:
            curr_state = 3
        elif eval_1d == 3 and curr_l >= ma10d_curr:
            curr_state = 2
        else:
            curr_state = eval_1d

    # 4. 交易信号推演 (trade_signal)
    # EVAL_STATE: 9=空头, 1=启动, 2=主升, 3=回撤
    # trade_signal: 5=HOLD, 1=买一, 2=买二, -1=卖出
    trade_signal = 5
    
    # 买一：从启动(1)确认转入主升(2)，且开盘未大幅跳空
    if eval_1d == 1 and curr_state == 2 and curr_o <= close_1d * 1.03:
        trade_signal = 1
    # 买二：从主升(2)进入缩量回撤(3)
    elif eval_1d == 2 and curr_state == 3:
        trade_signal = 2
    # 卖出：持有状态(1,2,3)下触发破位(9)
    elif eval_1d in [1, 2, 3] and curr_state == 9:
        trade_signal = -1

    return curr_state, trade_signal



def generate_simple_vect_features(df):
    """
    极简矢量化版本
    仅提取最新日的: open, close, high, low, nlow, nhigh 和 过去6日均量 last6vol
    """
    # 确保索引排序正确
    df = df.sort_index(level=[0, 1])
    
    # 1. 提取最新一行的原始数据
    # last() 会自动按第一个索引(code)分组并取每个代码的最后一行
    feat_df = df.groupby(level=0)[['open', 'close', 'high', 'low', 'nlow', 'nhigh']].last()

    # 2. 计算过去6日均量 (包含当日)
    # rolling(6) 计算滚动均值，然后再取最后一行
    vol_col = 'vol' if 'vol' in df.columns else 'volume'
    last6vol = df.groupby(level=0)[vol_col].rolling(window=6, min_periods=1).mean()
    
    # 因为 rolling 会增加一层索引，我们需要对齐后提取最后一行
    feat_df['last6vol'] = last6vol.groupby(level=0).last()

    # 3. 转换为你需要的字典列表格式
    # reset_index() 将 code 变成一列，to_dict('records') 转为字典列表
    return feat_df.reset_index().to_dict('records')


def dump_vect_daily_ohlcv(vect_daily_t, max_days=6, title=True):
    """
    将 vect_daily_t 中的 lastoNd / lasthNd / lastlNd / lastpNd / lastvNd
    按时间顺序展开打印，方便人工校验
    # dump_vect_daily_ohlcv(vect_daily_t, max_days=6)
    1d = 昨天
    2d = 前天
    ...

    Parameters
    ----------
    vect_daily_t : list[dict] | dict
        单只或多只股票的 vect 数据
    max_days : int
        展示多少天（从 1d 开始）
    """

    if isinstance(vect_daily_t, dict):
        vect_daily_t = [vect_daily_t]

    for item in vect_daily_t:
        code = item.get("code", "")
        name = item.get("name", "")
        if title:
            print(f"\n=== {code} {name} ===")
            print("day |   open     high     low      close        vol")
            print("-" * 62)

        for d in range(1, max_days + 1):
            o = item.get(f"lasto{d}d")
            h = item.get(f"lasth{d}d")
            l = item.get(f"lastl{d}d")
            c = item.get(f"lastp{d}d")
            v = item.get(f"lastv{d}d")

            print(
                f"{d:>3}d | "
                f"{o:>8.2f} "
                f"{h:>8.2f} "
                f"{l:>8.2f} "
                f"{c:>8.2f} "
                f"{int(v) if v else 0:>12}"
            )
            

def generate_df_vect_daily_features(df, lastdays=cct.compute_lastdays):
    """
    df:
        index = code
        columns 包含 open/high/low/close/... 以及可能存在的 lasto2d, lasto3d ...
        必须包含 'name' 列
    返回:
        List[dict]，每个 dict 对应一只股票
    """
    features_list = []

    cols_map_today = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        'perd': 'per'
    }

    for code, row in df.iterrows():

        feat = {'code': code, 'name': row['name'] if 'name' in df.columns else code}
        # ========= 0️⃣ today（实时 OHLC） =========
        for col in ('open', 'high', 'low', 'close', 'vol'):
            feat[col] = row[col] if col in df.columns else 0

        # ===== 1️⃣ 当天 (1d) =====
        for col, prefix in cols_map_today.items():
            feat[f'{prefix}1d'] = row[col] if col in df.columns else 0
        for suffix in ('eval', 'signal'):
            colname = f'{suffix}1d'
            feat[colname] = row[colname] if colname in df.columns else 0

        # ===== 2️⃣ 历史 (2d ~ lastdays) =====
        for d in range(2, lastdays + 1):
            for _, prefix in cols_map_today.items():
                colname = f'{prefix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0
            for suffix in ('eval', 'signal'):
                colname = f'{suffix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0

        features_list.append(feat)

    return features_list


def generate_df_vect_daily_features_noname(df, lastdays=cct.compute_lastdays):
    """
    df:
        index = code
        columns:
            today: open/high/low/close/vol
            history: lasto1d, lasto2d, ..., lasth1d, lastp1d ...
    返回:
        List[dict]，每个 dict 对应一只股票
    """

    features_list = []

    # history 字段前缀
    hist_prefixes = (
        'lasto', 'lasth', 'lastl', 'lastp', 'lastv',
        'upper', 'ma5', 'ma20', 'ma60',
        'perc', 'per'
    )

    for code, row in df.iterrows():
        feat = {'code': code}

        # ========= 0️⃣ today（实时 OHLC） =========
        for col in ('open', 'high', 'low', 'close', 'vol'):
            feat[col] = row[col] if col in df.columns else 0

        # eval / signal（若是实时）
        for suffix in ('eval', 'signal'):
            if suffix in df.columns:
                feat[suffix] = row[suffix]
            else:
                feat[suffix] = 0

        # ========= 1️⃣ history：last*1d ~ last*Nd =========
        for d in range(1, lastdays + 1):
            for prefix in hist_prefixes:
                colname = f'{prefix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0

            for suffix in ('eval', 'signal'):
                colname = f'{suffix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0

        features_list.append(feat)

    return features_list


def generate_df_vect_daily_features_lastday(df, lastdays=cct.compute_lastdays):
    """
    df:
        index = code
        columns 包含 open/high/low/close/... 以及可能存在的 lasto2d, lasto3d ...
    返回:
        List[dict]，每个 dict 对应一只股票
    """

    features_list = []

    # 映射：今天字段 → last*1d
    cols_map_today = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        'perd': 'per'
    }

    for code, row in df.iterrows():
        feat = {'code': code}

        # ===== 1️⃣ 当天 (1d) =====
        for col, prefix in cols_map_today.items():
            feat[f'{prefix}1d'] = row[col] if col in df.columns else 0

        for suffix in ('eval', 'signal'):
            colname = f'{suffix}1d'
            feat[colname] = row[colname] if colname in df.columns else 0

        # ===== 2️⃣ 历史 (2d ~ lastdays) =====
        for d in range(2, lastdays + 1):
            for _, prefix in cols_map_today.items():
                colname = f'{prefix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0

            for suffix in ('eval', 'signal'):
                colname = f'{suffix}{d}d'
                feat[colname] = row[colname] if colname in df.columns else 0

        features_list.append(feat)

    return features_list


def generate_df_vect_daily_features_MultiIndex(df, lastdays=5):
    """
    df: 多股票 DataFrame，index 为 (code, date)，多列 open/close/high/low/vol/ma/upper/eval/signal
    lastdays: 提取最近 N 天特征
    返回: 每只股票一行字典，字段格式 lasto1d,lastp1d,...,eval1d,signal1d,...，并带 'code' 字段
    """

     # === 关键修复：统一 index 结构 ===
    if isinstance(df.index, pd.MultiIndex):
        pass
    elif 'code' in df.columns:
        # 单 index，但 code 在列里
        df = df.set_index(['code', df.index])
    else:
        raise ValueError("df index 必须是 MultiIndex(code, date) 或包含 code 列")

    features_list = []
    cols_map = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        'perd': 'per'
    }

    for code, df_stock in df.groupby(level=0):
        feat = {'code': code}  # 添加股票 code
        df_stock = df_stock.sort_index(level=1)
        n_rows = len(df_stock)

        for da in range(1, lastdays + 1):
            for col, prefix in cols_map.items():
                if col in df_stock.columns and da <= n_rows:
                    feat[f'{prefix}{da}d'] = df_stock[col].iloc[-da]
                else:
                    feat[f'{prefix}{da}d'] = 0

            # eval / signal
            for suffix in ['eval', 'signal']:
                colname = f'{suffix}{da}d'
                if colname in df_stock.columns and da <= n_rows:
                    feat[colname] = df_stock[colname].iloc[-da]
                else:
                    feat[colname] = 0

        features_list.append(feat)

    return features_list




def extract_eval_signal_dict(df, lastdays=5):
    """
    将 df 中 evalNd 和 signalNd 列提取成一个字典，用于每日早盘汇总
    lastdays: 提取最近 N 天的数据
    返回: dict {'eval1d':..., 'signal1d':..., 'eval2d':..., ...}
    """
    result = {}
    for da in range(1, lastdays + 1):
        eval_col = f'eval{da}d'
        signal_col = f'signal{da}d'

        # 安全获取最后 da 天的数据，如果列不存在则默认 0
        result[eval_col] = df[eval_col].iloc[-1] if eval_col in df.columns else 0
        result[signal_col] = df[signal_col].iloc[-1] if signal_col in df.columns else 0

    return result


def evaluate_trading_signal_vB(df):
    """
    版本 B: 風控優先（保守型）。
    EVAL_STATE: 9=空頭, 1=啟動, 2=主升, 3=回撤, 0=無效數據
    trade_signal: 5=HOLD, 1=買一(啟動), 2=買二(低吸), -1=賣出, 0=無效數據
    """
    df = df.copy()
    valid = df['upper'] > 0

    # 1. 條件定義（已單行化）
    cond_trend_start = valid & (df['close'] > df['upper']) & (df['close'].shift(1) <= df['upper'].shift(1)) & (df['amount'] > df['amount'].shift(1) * 1.1)
    cond_trend_continue = valid & (df['close'] > df['upper']) & (df['close'].shift(1) > df['upper'].shift(1))
    cond_pullback = valid & (df['close'] < df['close'].shift(1)) & (df['low'] >= df['ma10d']) & (df['amount'] < df['amount'].shift(1))
    # 使用原始 cond_bear 邏輯
    cond_bear = valid & ((df['close'] < df['ma10d']) | ((df['open'] > df['close'].shift(1)) & (df['close'] < df['ma10d'])))

    # 2. 狀態機邏輯
    df['EVAL_STATE'] = 9 # 默認空頭/禁止交易
    for i in range(len(df)):
        if not valid.iloc[i]: continue
        prev_state = df['EVAL_STATE'].iloc[i-1] if i > 0 else 9

        if cond_bear.iloc[i]:       # <-- 風控邏輯優先級最高，會錯過強勢反轉信號
            df.at[df.index[i], 'EVAL_STATE'] = 9
        elif cond_trend_start.iloc[i]: # <-- 強勢啟動次之
            df.at[df.index[i], 'EVAL_STATE'] = 1
        elif cond_trend_continue.iloc[i]:
            df.at[df.index[i], 'EVAL_STATE'] = 2
        elif cond_pullback.iloc[i] and prev_state in [2, 3]:
            df.at[df.index[i], 'EVAL_STATE'] = 3
        elif prev_state == 3 and df['low'].iloc[i] >= df['ma10d'].iloc[i]:
            df.at[df.index[i], 'EVAL_STATE'] = 2
        else:
            df.at[df.index[i], 'EVAL_STATE'] = prev_state

    # 3. 生成交易訊號
    df['EVAL_STATE_PREV'] = df['EVAL_STATE'].shift(1).fillna(9).astype(int)
    df['trade_signal'] = 5 # 預設 HOLD
    df.loc[(df['EVAL_STATE_PREV'] == 1) & (df['EVAL_STATE'] == 2) & (df['open'] <= df['close'].shift(1) * 1.03), 'trade_signal'] = 1
    df.loc[(df['EVAL_STATE_PREV'] == 2) & (df['EVAL_STATE'] == 3), 'trade_signal'] = 2
    df.loc[(df['EVAL_STATE_PREV'].isin([1, 2, 3])) & (df['EVAL_STATE'] == 9), 'trade_signal'] = -1

    # 4. 無效數據強制歸零
    df.loc[~valid, ['EVAL_STATE', 'trade_signal']] = 0

    return df


def evaluate_trading_signal_vA(df):
    """
    版本 A: 強勢反轉優先捕捉大行情。
    EVAL_STATE: 9=空頭, 1=啟動, 2=主升, 3=回撤, 0=無效數據
    trade_signal: 5=HOLD, 1=買一(啟動), 2=買二(低吸), -1=賣出, 0=無效數據
    """
    df = df.copy()
    valid = df['upper'] > 0

    # 1. 條件定義（已單行化）
    # cond_bear 修正為「收盤價」必須確立跌破 10 日線才算轉熊
    cond_trend_start = valid & (df['close'] > df['upper']) & (df['close'].shift(1) <= df['upper'].shift(1)) & (df['amount'] > df['amount'].shift(1) * 1.1)
    cond_trend_continue = valid & (df['close'] > df['upper']) & (df['close'].shift(1) > df['upper'].shift(1))
    cond_pullback = valid & (df['close'] < df['close'].shift(1)) & (df['low'] >= df['ma10d']) & (df['amount'] < df['amount'].shift(1))
    cond_bear = valid & (df['close'] < df['ma10d']) 

    # 2. 狀態機邏輯
    df['EVAL_STATE'] = 9 # 默認空頭/禁止交易
    for i in range(len(df)):
        if not valid.iloc[i]: continue 
        prev_state = df['EVAL_STATE'].iloc[i-1] if i > 0 else 9

        if cond_trend_start.iloc[i]: # <-- 捕捉「水下起跳」的大陽線，優先級最高
            df.at[df.index[i], 'EVAL_STATE'] = 1
        elif cond_bear.iloc[i]:       # <-- 其次判斷風控條件
            df.at[df.index[i], 'EVAL_STATE'] = 9
        elif cond_trend_continue.iloc[i]:
            df.at[df.index[i], 'EVAL_STATE'] = 2
        elif cond_pullback.iloc[i] and prev_state in [2, 3]:
            df.at[df.index[i], 'EVAL_STATE'] = 3
        elif prev_state == 3 and df['low'].iloc[i] >= df['ma10d'].iloc[i]:
            df.at[df.index[i], 'EVAL_STATE'] = 2
        else:
            df.at[df.index[i], 'EVAL_STATE'] = prev_state

    # 3. 生成交易訊號
    df['EVAL_STATE_PREV'] = df['EVAL_STATE'].shift(1).fillna(9).astype(int)
    df['trade_signal'] = 5 # 預設 HOLD
    df.loc[(df['EVAL_STATE_PREV'] == 1) & (df['EVAL_STATE'] == 2) & (df['open'] <= df['close'].shift(1) * 1.03), 'trade_signal'] = 1
    df.loc[(df['EVAL_STATE_PREV'] == 2) & (df['EVAL_STATE'] == 3), 'trade_signal'] = 2
    df.loc[(df['EVAL_STATE_PREV'].isin([1, 2, 3])) & (df['EVAL_STATE'] == 9), 'trade_signal'] = -1

    # 4. 無效數據強制歸零
    df.loc[~valid, ['EVAL_STATE', 'trade_signal']] = 0

    return df


def evaluate_trading_signal(df, mode='A'):
    """
    优化结构版（版本 C）
    mode: 'A'=强势反转优先, 'B'=风控优先
    EVAL_STATE: 9=空头, 1=启动, 2=主升, 3=回撤, 0=无效
    trade_signal: 5=HOLD, 1=买一, 2=买二, -1=卖出, 0=无效
    """
    df = df.copy()
    valid = df['upper'] > 0

    # 条件定义
    cond_trend_start = valid & (df['close'] > df['upper']) & (df['close'].shift(1) <= df['upper'].shift(1)) & (df['amount'] > df['amount'].shift(1) * 1.1)
    cond_trend_continue = valid & (df['close'] > df['upper']) & (df['close'].shift(1) > df['upper'].shift(1))
    cond_pullback = valid & (df['close'] < df['close'].shift(1)) & (df['low'] >= df['ma10d']) & (df['amount'] < df['amount'].shift(1))
    cond_bear = valid & (df['close'] < df['ma10d'])

    df['EVAL_STATE'] = 9  # 默认空头
    for i in range(len(df)):
        if not valid.iloc[i]:
            continue
        prev_state = df['EVAL_STATE'].iloc[i-1] if i > 0 else 9

        if mode == 'A':  # 强势优先
            if cond_trend_start.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 1
            elif cond_bear.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 9
            elif cond_trend_continue.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 2
            elif cond_pullback.iloc[i] and prev_state in [2,3]:
                df.at[df.index[i], 'EVAL_STATE'] = 3
            elif prev_state == 3 and df['low'].iloc[i] >= df['ma10d'].iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 2
            else:
                df.at[df.index[i], 'EVAL_STATE'] = prev_state

        elif mode == 'B':  # 风控优先
            if cond_bear.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 9
            elif cond_trend_start.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 1
            elif cond_trend_continue.iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 2
            elif cond_pullback.iloc[i] and prev_state in [2,3]:
                df.at[df.index[i], 'EVAL_STATE'] = 3
            elif prev_state == 3 and df['low'].iloc[i] >= df['ma10d'].iloc[i]:
                df.at[df.index[i], 'EVAL_STATE'] = 2
            else:
                df.at[df.index[i], 'EVAL_STATE'] = prev_state

    # 前一日状态
    df['EVAL_STATE_PREV'] = df['EVAL_STATE'].shift(1).fillna(9).astype(int)

    # 交易信号
    df['trade_signal'] = 5  # 默认HOLD
    df.loc[(df['EVAL_STATE_PREV'] == 1) & (df['EVAL_STATE'] == 2) & (df['open'] <= df['close'].shift(1) * 1.03), 'trade_signal'] = 1
    df.loc[(df['EVAL_STATE_PREV'] == 2) & (df['EVAL_STATE'] == 3), 'trade_signal'] = 2
    df.loc[(df['EVAL_STATE_PREV'].isin([1,2,3])) & (df['EVAL_STATE'] == 9), 'trade_signal'] = -1

    # 无效数据
    df.loc[~valid, ['EVAL_STATE','trade_signal']] = [9,5]

    return df



def get_tdx_macd(df: pd.DataFrame, min_len: int = 39, rsi_period: int = 14, kdj_period: int = 9 ,detect_calc_support=False) -> pd.DataFrame:
    """
    统一计算：
      - BOLL, MACD, RSI, KDJ
      - EMA10/20, SWL/SWS 支撑压力
      - 明日支撑/阻力, 分数（XX）
    """
    if df.empty or not all(col in df.columns for col in ['close', 'high', 'low']):
        return df.copy()

    increasing = None
    id_cout = len(df)
    limit = min_len

    if id_cout < limit:
        # if  df.index.is_monotonic_increasing:
        #     increasing = True
        #     df = df.sort_index(ascending=False)
        # else:
        #     increasing = False

        # runtimes = limit-id_cout
        # df = df.reset_index()
        # temp = df.loc[np.repeat(df.index[-1], runtimes)].reset_index(drop=True)
        # df = pd.concat([df, temp], axis=0)
        # df = df.reset_index(drop=True)
        # df=df.sort_index(ascending=False)

        runtimes = limit-id_cout
        df = df.reset_index()
        temp = df.loc[np.repeat(df.index[0], runtimes)].reset_index(drop=True)
        df = pd.concat([temp,df], axis=0)
        df = df.reset_index(drop=True)

    # --- BOLLINGER BANDS ---
    bb = ta.bbands(df['close'], length=20, std=2, mamode='sma')
    df['lower'] = bb['BBL_20_2.0']
    df['upper'] = bb['BBU_20_2.0']
    df['ene'] = bb['BBM_20_2.0']
    df['bandwidth'] = df['upper'] - df['lower']
    df['bollpect'] = (df['close'] - df['lower']) / df['bandwidth'] * 100
    df['boll_sq'] = ((df['close'] - df['ene']) / df['bandwidth'] * 100).round(2)
    # boll_strength_quant
    # 结果正值 → 股价在中轨上方，越大越强
    # 结果负值 → 股价在中轨下方，越小越弱

    df = boll_trend_breakout(df)
    # --- MACD ---
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df['macddif'] = macd['MACD_12_26_9']
    df['macddea'] = macd['MACDs_12_26_9']
    df['macd'] = macd['MACDh_12_26_9']
    for i in range(1, 7):
        df[f'macdlast{i}'] = df['macd'].shift(i - 1)

    # --- RSI ---
    df['rsi'] = ta.rsi(df['close'], length=rsi_period)

    # --- KDJ ---
    kdj = ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=3, d=3, smooth_k=3)
    df['kdj_k'] = kdj['STOCHk_3_3_3']
    df['kdj_d'] = kdj['STOCHd_3_3_3']
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']

    # ========== 均线与支撑压力 ==========
    df["EMA10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["SWL"] = (df["EMA10"] * 7 + df["EMA20"] * 3) / 10  # 支撑线

    vol5 = df["vol"].rolling(5).sum()
    df["CAPITAL"] = df.get("CAPITAL", vol5.rolling(20).mean())
    if len(df) < 100:
        df["SWS"] = df["EMA20"].copy()
    else:
        factor = np.maximum(1, 100 * (vol5 / (3 * df["CAPITAL"])))
        alpha = 2 / (1 + factor.clip(1, 200))  # 动态平滑因子

        # 动态加权平均（模拟 DMA） - Optimized to use NumPy array loop
        ema20_vals = df["EMA20"].values
        alpha_vals = alpha.values
        sws_vals = np.zeros(len(df))
        
        # 初始化第一个值（可用EMA20首个值）
        sws_vals[0] = ema20_vals[0]

        for i in range(1, len(df)):
            # prev_sws = sws_vals[i - 1]
            # ema20_now = ema20_vals[i]
            # a = alpha_vals[i]
            sws_vals[i] = alpha_vals[i] * ema20_vals[i] + (1 - alpha_vals[i]) * sws_vals[i-1]

        df["SWS"] = sws_vals

        # 补 NaN
        df["SWS"] = df["SWS"].fillna(method="ffill").fillna(df["EMA20"])

    # ========== 明日支撑 / 阻力 ==========
    E = (df["high"] + df["low"] + df["open"] + 2 * df["close"]) / 5
    df["resist_next"] = 2 * E - df["low"]
    df["support_next"] = 2 * E - df["high"]
    df["break_next"] = E + (df["high"] - df["low"])
    df["reverse_next"] = E - (df["high"] - df["low"])
    df["resist_today"] = df["resist_next"].shift(1)
    df["support_today"] = df["support_next"].shift(1)

    # ========== 量化评分（XX） ==========
    X1 = np.where(df["close"].rolling(5).mean() > df["close"].rolling(10).mean(), 20, 0)
    X2 = np.where(df["close"].rolling(20).mean() > df["close"].rolling(60).mean(), 10, 0)
    X3 = np.where(df["kdj_j"] > df["kdj_k"], 10, 0)
    X4 = np.where(df["macddif"] > df["macddea"], 10, 0)
    X5 = np.where(df["macd"] > 0, 10, 0)

    X6 = np.where(df["vol"] > df["vol"].rolling(60).mean(), 10, 0)
    X7 = np.where(
        (df["close"] - df["low"].rolling(60).min()) /
        (df["high"].rolling(60).max() - df["low"].rolling(60).min()) > 0.5, 10, 0
    )
    X8 = np.where(df["close"] / df["close"].shift(1) > 1.03, 10, 0)
    df["score"] = X1 + X2 + X3 + X4 + X5 + X6 + X7 + X8

    # ======== 清理格式 =========
    df = df.fillna(0)

    # if df.index.name != 'date':
    #     df=df[-id_cout:].set_index('date')
    # if not isinstance(df.index, pd.DatetimeIndex) and 'date' in df.columns:
    #     df.index = pd.to_datetime(df.pop('date'), errors='coerce')
    if 'date' in df.columns:
        df.index = df.pop('date')
        df=df[-id_cout:]
    else:
        df=df[-id_cout:]

    # if increasing is not None:
    #     df = df.sort_index(ascending=increasing)
    if detect_calc_support:
        df = detect_local_extremes_filtered(df)
        df = calc_support_resistance_vec(df)
    return df

tdx_max_int = ct.tdx_max_int
tdx_max_int_end = ct.tdx_max_int_end
tdx_high_da = ct.tdx_high_da

# DAY_DTYPE = np.dtype([
#     ('date',   '<u4'),   # YYYYMMDD
#     ('open',   '<u4'),
#     ('high',   '<u4'),
#     ('low',    '<u4'),
#     ('close',  '<u4'),
#     ('amount', '<f4'),
#     ('vol',    '<u4'),
#     ('_skip',  '<u4'),
# ])

DAY_DTYPE = np.dtype([
    ('date', np.uint32),
    ('open', np.uint32),
    ('high', np.uint32),
    ('low', np.uint32),
    ('close', np.uint32),
    ('amount', np.uint32),
    ('vol', np.uint32),
    ('_skip', np.uint32)
])

def read_tdx_day_fast(fname: str, dl: int) -> pd.DataFrame:
    arr = np.fromfile(fname, dtype=DAY_DTYPE)
    if arr.size == 0:
        return pd.DataFrame()

    if dl:
        arr = arr[-dl:]

    df = pd.DataFrame(arr)

    # 数值缩放（向量化）
    df[['open','high','low','close']] /= 100.0

    df.drop(columns=['_skip'], inplace=True)

    # 基础清洗（等价你原来的）
    df = df[(df.open != 0) & (df.amount != 0)]

    if df.empty:
        return pd.DataFrame()

    # # date 直接当 index（int，最快）
    # df['date'] = df['date'].astype(str)
    # df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')  # 转为 datetime
    df['date'] = (
        df['date'].astype(str).str[:4] + '-' +
        df['date'].astype(str).str[4:6] + '-' +
        df['date'].astype(str).str[6:8]
    )
    df.set_index('date', inplace=True)

    return df

# def get_tdx_Exp_day_to_df(
def get_tdx_Exp_day_to_df_lday(
    code, start=None, end=None, dl=None, newdays=None,
    type='f', wds=True, lastdays=3, resample='d',
    MultiIndex=False, lastday=None,
    detect_calc_support=True, normalized=False,
):
    """
    全极速稳定版（二进制 .day 路径）
    """

    # =========================
    # 1. 文件定位（.day）
    # =========================
    code_u = cct.code_to_symbol(code)
    # market = 'sh' if code_u.startswith('6') else 'sz'
    market = code_u[:2]
    day_path = os.path.join(
        basedir,'Vipdoc',market, 'lday', f'{market}{code_u}.day'
    )
    if not code_u:
        return None  # 或者 raise ValueError("Invalid code")
    market = code_u[:2]  # 'sh', 'sz', 'bj'
    day_path = os.path.join(
        basedir,'Vipdoc',market, 'lday', f'{code_u}.day'
    )

    if not os.path.exists(day_path):
        return pd.DataFrame()

    if dl is None:
        dl = 70

    # =========================
    # 2. 极速二进制读取
    # =========================
    df = read_tdx_day_fast(day_path, dl + 10)

    if df.empty:
        return pd.DataFrame()

    # =========================
    # 3. 裁剪
    # =========================
    if lastday:
        df = df.iloc[:-lastday]

    df = df.iloc[-dl:]

    if df.empty:
        return pd.DataFrame()

    df['code'] = code

    if dl == 1:
        # 找到最后一条有效记录
        valid = df[(df['open'] != 0) & (df['amount'] != 0)]
        if valid.empty:
            return pd.Series([], dtype='float64')
        last_row = valid.iloc[-1]
        return pd.Series({
            'code': last_row['code'],          # 股票代码
            'date': last_row.name,     # 交易日
            'open': last_row['open'],
            'high': last_row['high'],
            'low': last_row['low'],
            'close': last_row['close'],
            'amount': last_row['amount'],
            'vol': last_row['vol']
        })


    # df = df.set_index('date').sort_index()
    # =========================
    # 4. 非日线 resample
    # =========================
    if resample != 'd':
        df = get_tdx_stock_period_to_type(df, period_day=resample)
        if 'date' in df.columns:
            df = df.set_index('date')

    # =========================
    # 5. 技术指标（原样保留）
    # =========================
    df = get_tdx_macd(df, detect_calc_support=detect_calc_support)

    df = compute_lastdays_percent(
        df, lastdays=lastdays,
        resample=resample, normalized=normalized
    )

    # =========================
    # 6. fib / maxp
    # =========================
    per_cols = [c for c in df.columns if c.startswith('per') and c.endswith('d')]
    if per_cols:
        last = df.iloc[-1][per_cols]
        df.loc[df.index[-1], 'maxp'] = last.max()
        fib = (last > (10 if resample != 'd' else 2)).sum()
        df.loc[df.index[-1], 'fib'] = fib
        df.loc[df.index[-1], 'maxpcout'] = fib
    else:
        df[['maxp', 'fib', 'maxpcout']] = 0

    # =========================
    # 7. 结构指标（完全向量化）
    # =========================
    c1 = df.close.shift(1)
    df['max5']  = c1.rolling(5).max()
    df['max10'] = c1.rolling(10).max()
    df['hmax']  = c1.rolling(30).max()
    df['low10'] = df.low.shift(1).rolling(10).min()
    df['low4']  = df.low.shift(1).rolling(4).min()

    if len(df) > 10:
        df['high4']  = c1.rolling(4).max()
        df['hmax60'] = c1.rolling(60).max()
        # lmin
        try:
            df['lmin'] = df.low.iloc[-tdx_max_int_end:-tdx_high_da].min()
        except: 
            df['lmin'] = 0

        # min5
        df['min5'] = df.low.iloc[-6:-1].min() if len(df) >= 6 else df.low.min()

        # cmean
        df['cmean'] = round(df.close.iloc[-10:-tdx_high_da].mean(), 2) if len(df) >= 10 else round(df.close.mean(), 2)

        # hv / lv / llowvol
        df['hv'] = df.vol.iloc[-tdx_max_int:-tdx_high_da].max() if len(df) >= tdx_max_int else df.vol.max()
        df['lv'] = df.vol.iloc[-tdx_max_int:-tdx_high_da].min() if len(df) >= tdx_max_int else df.vol.min()
        df['llowvol'] = df['lv']

        # low60
        df['low60'] = df.close.iloc[-tdx_max_int_end*2:-tdx_max_int_end].min() if len(df) >= tdx_max_int_end*2 else df.close.min()

        # lastdu4
        df['lastdu4'] = (
            (df.high.rolling(4).max() - df.low.rolling(4).min()) / df.close.rolling(4).mean() * 100
        ).round(1).fillna(0)

        # high4 / hmax60 已有，保留
    # =========================
    # 8. MainU（最后一行）
    # =========================
    if len(df) > 10:
        chk = check_conditions_auto(df.iloc[-1:])
        df.loc[df.index[-1], 'MainU'] = chk['MainU'].iloc[0]

    if 'date' in df.columns:
        df.index = df.pop('date')

    return df



# def get_tdx_Exp_day_to_df_txt(
def get_tdx_Exp_day_to_df(
    code, start=None, end=None, dl=None, newdays=None,
    type='f', wds=True, lastdays=3, resample='d',
    MultiIndex=False, lastday=None,
    detect_calc_support=True, normalized=False,
    fastohlc=False,
):
    """
    全极速稳定版（无回退 / 自动支持 resample & MultiIndex）
    """

    # =========================
    # 1. 文件定位
    # =========================
    code_u = cct.code_to_symbol(code)
    base = 'forwardp' if type == 'f' else 'backp'
    file_path = os.path.join(exp_path, base, f"{code_u.upper()}.txt")

    if not os.path.exists(file_path):
        return pd.DataFrame()

    if dl is None:
        dl = 70  # 防止上层漏传

    if dl == 1:
        data = cct.read_last_lines(file_path, int(dl) + 3)
        data_l = data.split('\n')
        data_l.reverse()
        for line in data_l:
            a = line.split(',')
            if len(a) == 7:
                tdate = a[0]
                if len(tdate) != 10:
                    continue
                topen = round(float(a[1]), 2)
                thigh = round(float(a[2]), 2)
                tlow = round(float(a[3]), 2)
                tclose = round(float(a[4]), 2)
                tvol = round(float(a[5]), 2)
                amount = round(float(a[6].replace('\r\n','')), 1)
                if int(topen) == 0 or int(amount) == 0:
                    continue
                df = pd.Series({
                    'code': code, 'date': tdate, 'open': topen, 'high': thigh,
                    'low': tlow, 'close': tclose, 'amount': amount, 'vol': tvol
                })
                return df
        # 如果循环结束没有有效行，返回空 Series
        return pd.Series([], dtype='float64')
    # =========================
    # 2. 极速尾部读取（日线原始）
    # =========================
    from collections import deque
    from io import StringIO

    with open(file_path, 'r', encoding='gb18030', errors='replace') as f:
        lines = deque(f, maxlen=dl + 10)

    if not lines:
        return pd.DataFrame()

    cols = ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']
    df = pd.read_csv(
        StringIO(''.join(lines)),
        names=cols,
        header=None,
        engine='c',
        on_bad_lines='skip'
    )

    # =========================
    # 3. 清洗 & 裁剪
    # =========================
    num_cols = cols[1:]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
    df.dropna(inplace=True)
    df = df[(df.open != 0) & (df.amount != 0)]
    df.drop_duplicates(subset='date', inplace=True)

    if df.empty:
        return pd.DataFrame()

    df['code'] = code
    df = df.set_index('date').sort_index()

    if lastday:
        df = df.iloc[:-lastday]
    df = df.iloc[-dl:]


    if df.empty:
        return pd.DataFrame()

    # =========================
    # 4. 非日线：统一在这里 resample
    # =========================
    if resample != 'd':
        df = get_tdx_stock_period_to_type(df, period_day=resample)
        if 'date' in df.columns:
            df = df.set_index('date')
    if fastohlc:
        if 'date' in df.columns:
            df.index = df.pop('date')
        return df
    # =========================
    # 5. 核心指标（极速）
    # =========================

    df = get_tdx_macd(df, detect_calc_support=detect_calc_support)
    df = compute_lastdays_percent(
        df, lastdays=lastdays,
        resample=resample, normalized=normalized
    )

    # =========================
    # 6. fib / maxp
    # =========================
    per_cols = [c for c in df.columns if c.startswith('per') and c.endswith('d')]
    if per_cols:
        last = df.iloc[-1][per_cols]
        df.loc[df.index[-1], 'maxp'] = last.max()
        fib = (last > (10 if resample != 'd' else 2)).sum()
        df.loc[df.index[-1], 'fib'] = fib
        df.loc[df.index[-1], 'maxpcout'] = fib
    else:
        df[['maxp', 'fib', 'maxpcout']] = 0


    # =========================
    # 7. 结构指标（向量化）
    # =========================
    # tdx_max_int = ct.tdx_max_int  #10
    # tdx_max_int_end = ct.tdx_max_int_end   #30
    # tdx_high_da = ct.tdx_high_da   #3
    df['max5'] = df.close.iloc[-6:-1].max()
    df['max10'] = df.high.iloc[-13:-tdx_high_da].max()
    df['hmax'] = df.high.iloc[-tdx_max_int_end:-tdx_high_da].max()
    df['low10'] = df.low.iloc[-13:-tdx_high_da].min()
    df['low4'] = df.low.iloc[-13:-tdx_high_da].min()
    # =========================
    # 7+. 补齐旧版依赖的结构指标（极速等价）
    # =========================

    if len(df) > 10:
        try:
            df['lmin'] = df.low.iloc[-tdx_max_int_end:-tdx_high_da].min()
            df['min5'] = df.low.iloc[-6:-1].min()
            df['cmean'] = round(df.close.iloc[-10:-tdx_high_da].mean(), 2)
            df['hv'] = df.vol.iloc[-tdx_max_int:-tdx_high_da].max()
            df['lv'] = df.vol.iloc[-tdx_max_int:-tdx_high_da].min()
            df['llowvol'] = df['lv']
            df['high4'] = df.high.iloc[-5:-1].max()
            df['hmax60'] = df.high.iloc[-60:-tdx_high_da].max()
            df['low60'] = df.low.iloc[-60:-tdx_max_int_end].min()
            # df['low60'] = df.low.iloc[-tdx_max_int_end*2:-tdx_max_int_end].min()

            df['lastdu4'] = (
                (df.high.rolling(4).max() - df.low.rolling(4).min()) /
                df.close.rolling(4).mean() * 100
            ).round(1)
        except Exception:
            pass

    # =========================
    # 7++. 统一兜底缺失列（防 KeyError）
    # =========================
    # REQUIRED_COLS = [
    #     'lmin','min5','cmean','hv','lv','llowvol',
    #     'max5','max10','hmax','hmax60','high4',
    #     'low10','low60','low4','lastdu4'
    # ]

    # for c in REQUIRED_COLS:
    #     if c not in df.columns:
    #         df[c] = 0

    # df.fillna(0, inplace=True)

    # =========================
    # 8. MainU（仅最后一行）
    # =========================
    if len(df) > 10:
        chk = check_conditions_auto(df.iloc[-1:])
        df.loc[df.index[-1], 'MainU'] = chk['MainU'].iloc[0]

    # =========================
    # 9. MultiIndex（可选）
    # =========================
    # if MultiIndex:
    #     df['code'] = code
    #     df.set_index(['code', df.index], inplace=True)

    # if not isinstance(df.index, pd.DatetimeIndex):
    #     df.index = pd.to_datetime(df.pop('date'), errors='coerce')
    if 'date' in df.columns:
        df.index = df.pop('date')

    return df


# def get_tdx_Exp_day_to_df_impl(code, start=None, end=None, dl=None, newdays=None,
def get_tdx_Exp_day_to_df_slow(code, start=None, end=None, dl=None, newdays=None,
                          type='f', wds=True, lastdays=3, resample='d', MultiIndex=False,lastday=None,detect_calc_support=True,normalized=False):
    """
    获取指定股票的日线数据，并计算各类指标
    保留原有逻辑和所有变量

    Arguments:
        code (str): 股票代码
        start (str, optional): 开始日期 YYYYMMDD
        end (str, optional): 结束日期 YYYYMMDD
        dl (int, optional): 最近天数
        newdays (int, optional): 新数据天数
        type (str, optional): 'f' forward / 'b' back
        wds (bool, optional): 是否写入数据
        lastdays (int, optional): 最近几日计算涨幅
        resample (str, optional): 'd','w','m'等
        MultiIndex (bool, optional): 是否返回多索引格式

    Returns:
        pd.DataFrame: 包含原始数据与计算指标的 DataFrame
    """

    # ------------------------------
    # 初始化参数
    # ------------------------------

    code_u = cct.code_to_symbol(code)
    if type == 'f':
        file_path = os.path.join(exp_path, 'forwardp', f"{code_u.upper()}.txt")
    elif type == 'b':
        file_path = os.path.join(exp_path, 'backp', f"{code_u.upper()}.txt")
    else:
        return pd.DataFrame()

    global initTdxdata
    write_k_data_status = False #wds and not code_u.startswith('bj')

    # if dl is not None:
    #     start = cct.get_trade_day_before_dl(dl)
        # start = cct.last_tddate(dl)
    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)

    tdx_max_int = ct.tdx_max_int
    tdx_max_int_end = ct.tdx_max_int_end
    tdx_high_da = ct.tdx_high_da
    newstockdayl = newdays if newdays is not None else newdaysinit

    df = None

    # if log.getEffectiveLevel() <= LoggerFactory.DEBUG:
    #     # 只有当日志等级是 DEBUG 或更低才进入 ipdb
    #     import ipdb; ipdb.set_trace()
    log.debug(f'file_path:{file_path} code: {code}')

    # ------------------------------
    # 文件不存在或为空
    # ------------------------------
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        log.error(f'get_kdate_data {code_u} file not exists: {file_path}')
        tmp_df = get_kdate_data(code, start='', end='', ktype='D')
        if len(tmp_df) > 0:
            write_tdx_tushare_to_file(code, df=tmp_df, start=None, type='f')
            log.error(f'{code_u} file not exists: {file_path}')
        else:
            if initTdxdata < 10:
                log.error(f"file_path not exists code: {code}")
            else:
                print('.',end=' ')
            initTdxdata += 1
        return pd.DataFrame()

    # ------------------------------
    # dl == 1 的特殊处理
    # ------------------------------
    if dl is not None and int(dl) == 1:
        data = cct.read_last_lines(file_path, int(dl) + 3)
        data_l = data.split('\n')
        data_l.reverse()
        for line in data_l:
            a = line.split(',')
            if len(a) == 7:
                tdate = a[0]
                if len(tdate) != 10:
                    continue
                topen = round(float(a[1]), 2)
                thigh = round(float(a[2]), 2)
                tlow = round(float(a[3]), 2)
                tclose = round(float(a[4]), 2)
                tvol = round(float(a[5]), 2)
                amount = round(float(a[6].replace('\r\n','')), 1)
                if int(topen) == 0 or int(amount) == 0:
                    continue
                # 返回 pd.Series
                df = pd.Series({
                    'code': code, 'date': tdate, 'open': topen, 'high': thigh,
                    'low': tlow, 'close': tclose, 'amount': amount, 'vol': tvol
                })
                return df
        # 如果循环结束没有有效行，返回空 Series
        return pd.Series([], dtype='float64')

    # ------------------------------
    # 读取文件数据 (Refactored to use read_csv)
    # ------------------------------
    try:
        # Use C engine for speed, handle bad lines by skipping
        # Assuming ct.TDX_Day_columns is ['code', 'date', 'open', 'high', 'low', 'close', 'vol', 'amount']
        # The file content is: date, open, high, low, close, vol, amount (7 columns)
        # So we must NOT use the first column name 'code' for reading.
        
        file_cols = ct.TDX_Day_columns[1:] # Exclude 'code'
        try:
            df = pd.read_csv(
                    file_path, 
                    names=file_cols, 
                    header=None, 
                    index_col=False, 
                    # usecols=range(len(file_cols)), # Only read the first len(file_cols) columns (0 to 6)
                    engine='c',
                    encoding='gb18030', # Use broadly compatible encoding
                    encoding_errors='replace', # Ignore encoding errors
                    on_bad_lines='skip', 
                    )
        except pd.errors.ParserError as e:
            log.warning(f"{code} ParserError reading file {file_path}: {e}")
            df_err = pd.DataFrame()
            df_err.attrs['__error__'] = {
                "code": code,
                "exc_type": "EmptyFile",
                "exc_msg": "通达信 TXT 文件为空或格式错误",
            }
            return df_err
        

        # # 倒序取最后 dl+3 行
        # df = df.iloc[-(dl+3):].iloc[::-1].reset_index(drop=True)

        # # 用 deque 高效读取文件尾 dl+1 行
        # with open(file_path, 'r', encoding='gb18030', errors='replace') as f:
        #     last_lines = deque(f, maxlen=dl+1)

        # df = pd.read_csv(
        #     pd.io.common.StringIO(''.join(last_lines)),
        #     names=file_cols,
        #     header=None,
        #     index_col=False,
        #     engine='c',
        #     on_bad_lines='skip'
        # )
        # # 倒序
        # df = df.iloc[::-1].reset_index(drop=True)
        # t1 = time.time()
        
        # Ensure numeric columns are numeric (coerce errors to NaN)
        cols_to_numeric = ['open', 'high', 'low', 'close', 'vol', 'amount']
        df[cols_to_numeric] = df[cols_to_numeric].apply(pd.to_numeric, errors='coerce')
        
        # t2 = time.time()

        # Drop NaNs created by coercion
        df.dropna(subset=cols_to_numeric, inplace=True)
        
        # Filter logic: if topen == 0 or amount == 0: continue
        df = df[(df['open'] != 0) & (df['amount'] != 0)]
        
        # Add 'code' column
        df['code'] = code
        # t_io_end = time.time()
        # Format 'date' to string

        # df['date'] = df['date'].astype(str)
        # df = df[df['date'].str.len() == 10]

        # Reorder columns to match ct.TDX_Day_columns exactly
        # This puts 'code' back at the first position
        final_cols = [c for c in ct.TDX_Day_columns if c in df.columns]
        df = df[final_cols]

    except Exception as e:
        # log.error(f"Error {code} reading file {file_path} with read_csv: {e}")
        # # print(f"DEBUG Error: {e}") # Print to stdout for visibility in test logs
        # return pd.DataFrame()
        # return {
        #         "__error__": True,
        #         "code": code,
        #         "exc_type": type(e).__name__,
        #         "exc_msg": str(e),
        #     }
        df_err = pd.DataFrame()
        df_err.attrs['__error__'] = {
            "code": code,
            "exc_type": type(e).__name__,
            "exc_msg": str(e),
        }
        return df_err

    df = df[~df.date.duplicated()]
    # print(f'code: {code} df:{len(df)}', end=' ')
    # ------------------------------
    # 筛选日期
    # ------------------------------
    # if start is not None:
    #     df = df[df.date >= start]
    # if end is not None:
    #     df = df[df.date <= end]

    if start is not None or end is not None:
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= df['date'] >= start
        if end is not None:
            mask &= df['date'] <= end
        df = df.loc[mask]
    elif dl is not None:
        df = df[-dl:]

    if len(df) == 0:
        return pd.DataFrame()

    # df['date'] = df['date'].astype(str)
    df = df.set_index('date').sort_index(ascending=True)

    # if lastday is not None:
    #     df = df[:-lastday]
    if lastday is not None:
        df = df.iloc[:-lastday] if lastday > 0 else df
    # ------------------------------
    # 非日线重采样
    # ------------------------------
    if not MultiIndex and resample != 'd':
        df = get_tdx_stock_period_to_type(df, period_day=resample)
        if 'date' in df.columns:
            # df['date'] = df['date'].astype(str)
            df = df.set_index('date')

    # ------------------------------
    # 数据完整性检查
    # ------------------------------

    # ------------------------------
    # MACD 和涨幅
    # ------------------------------
    t_macd_start = time.time()
    if 'macd' not in df.columns:
        df = get_tdx_macd(df,detect_calc_support=detect_calc_support)
    t_macd_end = time.time()

    # ------------------------------
    # maxp / fib / maxpcout
    # ------------------------------
    per_couts = df.filter(regex=r'per[1-9]d')[-1:]
    if len(per_couts.T) > 2:
        if resample == 'd':
            df['maxp'] = per_couts.T[1:].values.max()
            fib_c = (per_couts.T.values > 2).sum()
        else:
            df['maxp'] = per_couts.T[:3].values.max()
            fib_c = (per_couts.T[:3].values > 10).sum()
        df['fib'] = fib_c
        df['maxpcout'] = fib_c
    else:
        df['maxp'] = df['fib'] = df['maxpcout'] = 0

        
    t_perc_start = time.time()
    if f'perc{lastdays}d' not in df.columns:
        df = compute_lastdays_percent(df, lastdays=lastdays, resample=resample,normalized=normalized)
    t_perc_end = time.time()


    # ------------------------------
    # 高低价 / 成交量 / 均价指标
    # ------------------------------
    if len(df) > 10:
        df['lmin'] = df.low[-tdx_max_int_end:-tdx_high_da].min()
        df['min5'] = df.low[-6:-1].min()
        df['cmean'] = round(df.close[-10:-tdx_high_da].mean(), 2)
        df['hv'] = df.vol[-tdx_max_int:-tdx_high_da].max()
        df['lv'] = df.vol[-tdx_max_int:-tdx_high_da].min()
        df = df.fillna(0)

        # 滚动指标
        df['max5'] = df.close.shift(1).rolling(5).max()
        df['max10'] = df.close.shift(1).rolling(10).max()
        df['hmax'] = df.close.shift(1).rolling(30).max()
        df['hmax60'] = df.close.shift(1).rolling(60).max()
        df['high4'] = df.close.shift(1).rolling(4).max()
        df['llowvol'] = df.vol[-tdx_max_int_end:-tdx_high_da].min()
        df['low10'] = df.low.shift(1).rolling(10).min()
        df['low60'] = df.close[-tdx_max_int_end*2:-tdx_max_int_end].min()
        df['low4'] = df.low.shift(1).rolling(4).min()
        df['lastdu4'] = ((df.high.rolling(4).max() - df.low.rolling(4).min()) /
                          df.close.rolling(4).mean() * 100).round(1)

    if len(df) > 10:
        # 2. 调用自动检查函数
        df_checked = check_conditions_auto(df[-1:])
        # 3. 直接赋值给原始 df 的 'MainU' 列对应最后一行
        # df.loc[df.index[-1], 'MainU'] = df_checked.loc[df_checked.index[-1], '符合条件']
        df.loc[df.index[-1], 'MainU'] = df_checked.loc[df_checked.index[-1], 'MainU']

        # 索引设置与排序
    # ------------------------------
    if len(df) > 0:
        if 'date' in df.columns:
            df = df.set_index('date')
        df = df.sort_index(ascending=True)
    # ------------------------------
    # tdx_err_code 检查逻辑
    # ------------------------------
    if resample == 'd':
        try:
            cond = cct.get_today_duration(df.index[-1]) > 20 or df.close[-3:].max() / df.open[-3:].min() > 5
        except Exception as e:
            log.error(f"tdx_err_code cond check failed: {e}")
            cond = False

        if cond:
            tdx_err_code = cct.GlobalValues().getkey('tdx_err_code')
            if tdx_err_code is None:
                tdx_err_code = [code]
                cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                log.error(f"{code} dl None outdata!")
                initTdxdata += 1
                if write_k_data_status:
                    write_all_kdata_to_file(code, f_path=file_path)
                    df = get_tdx_Exp_day_to_df(
                        code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex
                    )
            else:
                if code not in tdx_err_code:
                    tdx_err_code.append(code)
                    cct.GlobalValues().setkey('tdx_err_code', tdx_err_code)
                    log.error(f"{code} dl None outdata!")
                    initTdxdata += 1
                    if write_k_data_status:
                        write_all_kdata_to_file(code, f_path=file_path)
                        df = get_tdx_Exp_day_to_df(
                            code, start=start, end=end, dl=dl, newdays=newdays, type='f', wds=False, MultiIndex=MultiIndex
                        )

    return df
    # t_end = time.time()
    # t_total = t_end - t_start
    # if t_start > 0 and t_total > 0.1: # Threshold 50ms
    #     io_time = t_io_end - t_start if t_io_end > 0 else 0
    #     macd_time = t_macd_end - t_macd_start if t_macd_end > 0 else 0
    #     perc_time = t_perc_end - t_perc_start if t_perc_end > 0 else 0
    #     other_time = t_total - io_time - macd_time - perc_time
    #     log.info(f"SLOW_LOG: {code} Total:{t_total:.3f}s | IO:{io_time:.3f}s | MACD:{macd_time:.3f}s | PERC:{perc_time:.3f}s | Other:{other_time:.3f}s")


INDEX_LIST = {'sh': 'sh000001', 'sz': 'sz399001', 'hs300': 'sz399300',
              'sz50': 'sh000016', 'zxb': 'sz399005', 'cyb': 'sz399006'}



def get_tdx_append_now_df_api(code, start=None, end=None, type='f', df=None, dm=None, dl=None, power=True, newdays=None, write_tushare=False, writedm=False,detect_calc_support=False):

    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if start is not None and end is not None:
        dl = None
    if df is None:
        df = get_tdx_Exp_day_to_df(
            code, start=start, end=end, dl=dl, newdays=newdays).sort_index(ascending=True)
    else:
        df = df.sort_index(ascending=True)
    index_status = False

    if code == '999999':
        code_ts = str(1000000 - int(code)).zfill(6)
        index_status = True
    elif code.startswith('399'):
        index_status = True
        code_ts = code
#            for k in INDEX_LIST.keys():
#                if INDEX_LIST[k].find(code) > 0:
#                    code_ts = k
    else:
        index_status = False
        code_ts = code
    if not power:
        return get_tdx_macd(df,detect_calc_support=detect_calc_support)

    today = cct.get_today()

    if len(df) > 0:
        tdx_last_day = df.index[-1]
        tdx_last_day = cct.get_timestamp_to_fms(tdx_last_day)
        
        if tdx_last_day == today:
            return get_tdx_macd(df,detect_calc_support=detect_calc_support)
    else:
        if start is not None:
            tdx_last_day = start
        else:
            tdx_last_day = None
#            log.warn("code :%s start is None and DF is None"%(code))
    if tdx_last_day is not None:
        duration = cct.get_today_duration(tdx_last_day)
    else:
        duration = 2
    log.debug("duration:%s" % duration)
    log.debug("tdx_last_day:%s" % tdx_last_day)
    log.debug("duration:%s" % duration)
    if end is not None:
        # print end,df.index[-1]
        if len(df) == 0:
            return df
        if end <= df.index[-1]:
            # print(end, df.index[-1])
            # return df
            duration = 0
        else:
            today = end
    if duration > 1 and (tdx_last_day != cct.last_tddate(1)):
        import urllib.request, urllib.error, urllib.parse
        ds = None
        try:
            ds = get_kdate_data(code_ts, start=tdx_last_day,
                                end=today, index=index_status)
        except (IOError, EOFError, Exception, urllib.error.URLError) as e:
            print("Error Duration:", e, end=' ')
            print("code:%s" % (code_ts))
            cct.sleep(0.1)
        if ds is not None and len(ds) > 1:
            if len(df) > 0:
                lends = len(ds)
            else:
                lends = len(ds) + 1
            ds['code'] = code
            ds = ds[:lends - 1]

            if not 'amount' in ds.columns:
                ds['amount'] = list(map(lambda x, y, z: round(
                    (y + z) / 2 * x, 1), ds.volume, ds.high, ds.low))
            else:
                ds['amount'] = ds['amount'].apply(lambda x: round(x , 1))

            ds = ds.loc[:, ['code', 'open', 'high',
                            'low', 'close', 'volume', 'amount']]
            ds.rename(columns={'volume': 'vol'}, inplace=True)
            ds.sort_index(ascending=True, inplace=True)

            ds = ds.fillna(0)
            df = pd.concat([df,ds])
            if write_tushare and ((len(ds) == 1 and ds.index.values[0] != cct.get_today()) or len(ds) > 1):
                duration_day= cct.get_today_duration(ds.index.values[0],cct.get_today())
                if duration_day and duration_day < 5:
                    log.error(f'write_tdx_tushare_to_file-duration_day: {duration_day}')
                    sta = write_tdx_tushare_to_file(code, df=df)
                    if sta:
                        if today == ds.index[-1]:
                            return get_tdx_macd(df,detect_calc_support=detect_calc_support)


    if cct.get_now_time_int() > 830 and cct.get_now_time_int() < 930:
        log.debug("now > 830 and <930 return")
        if isinstance(df, pd.DataFrame):
            df = df.sort_index(ascending=True)
            df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
            df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
            df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
            df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
            df = df.fillna(0)
            df = df.sort_index(ascending=False)
        return get_tdx_macd(df,detect_calc_support=detect_calc_support)

    if dm is None and end is None:
        if index_status:
            dm = sina_data.Sina().get_stock_code_data(code, index=index_status)

        else:
            dm = sina_data.Sina().get_stock_code_data(code)


    if df is not None and len(df) > 0:
        if df.index.values[-1] == today:
            if dm is not None and not isinstance(dm, Series):

                dz = dm.loc[code].to_frame().T
            if index_status:
                vol_div = 1000
            else:
                vol_div = 10
            if dz.open.values[0] == df.open[-1] and 'volume' in dz.columns and int(df.vol[-1] / vol_div) == int(dz.volume.values / vol_div):
                df = df.sort_index(ascending=True)
                df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
                df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
                df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
                df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
                df = df.fillna(0)
                df = df.sort_index(ascending=False)
                return get_tdx_macd(df,detect_calc_support=detect_calc_support)
            else:
                writedm = True

    if dm is not None and df is not None and not dm.empty and len(df) > 0:
        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)

        if code not in dm.index:
            if index_status:
                if code == '999999':
                    c_name = dm.loc[code_ts, ['name']].values[0]
                    dm_code = (
                        dm.loc[code_ts, ['open', 'high', 'low', 'close', 'amount', 'vol']]).to_frame().T
                    log.error("dm index_status:%s %s %s" %
                              (code, code_ts, c_name))
            else:
                log.error("code not in index:%s %s" % (code, code_ts))
        else:
            c_name = dm.loc[code, ['name']].values[0]
            dm_code = (dm.loc[code, ['open', 'high', 'low',
                                     'close', 'amount', 'vol']]).to_frame().T
        log.debug("dm_code:%s" % dm_code)

        dm_code['date'] = today
        dm_code = dm_code.set_index('date')

        if end is None and ((df is not None and not dm.empty) and (round(df.open[-1], 2) != round(dm.open[-1], 2)) and (round(df.close[-1], 2) != round(dm.close[-1], 2))):
            if dm.open[0] > 0 and len(df) > 0:
                if dm_code.index == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])

        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))


    if len(df) > 0:
        df = df.sort_index(ascending=True)

        df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
        df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
        df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
        df['ma60d'] = talib.SMA(df['close'], timeperiod=60)


        df = df.fillna(0)
        df = df.sort_index(ascending=False)
    if end is None and writedm and len(df) > 0:
        if cct.get_now_time_int() < 900 or cct.get_now_time_int() > 1505:
            sta = write_tdx_sina_data_to_file(code, df=df)

    return df


def get_tdx_append_now_df_api_tofile(code, dm=None, newdays=0, start=None, end=None, type='f', df=None, dl=10, power=True,detect_calc_support=False):
    #补数据power = false
    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if df is None:
        log.debug(f'df is none get dl:{dl}')
        df = get_tdx_Exp_day_to_df(
            code, start=start, end=end, dl=dl, newdays=newdays).sort_index(ascending=True)
    else:
        df = df.sort_index(ascending=True)

    index_status = False
    if code == '999999':
        code_ts = str(1000000 - int(code)).zfill(6)
        index_status = True
    elif code.startswith('399'):
        index_status = True
        code_ts = code
#            for k in INDEX_LIST.keys():
#                if INDEX_LIST[k].find(code) > 0:
#                    code_ts = k
    else:
        index_status = False
        code_ts = code

    if not power:
        return df

    if dm is not None and code in dm.index:
        today = dm.dt.loc[code]
    else:
        today = cct.get_today()
    if len(df) > 0:
        tdx_last_day = df.index[-1]
        if tdx_last_day == today:
            return df
    else:
        if start is not None:
            tdx_last_day = start
        else:
            tdx_last_day = None

    if tdx_last_day is not None:
        # duration = cct.get_today_duration(tdx_last_day)
        duration = cct.get_trade_day_distance(tdx_last_day)
    else:
        duration = 1

    log.debug(f"duration: {duration} tdx_last_day: {tdx_last_day} lastdays_trade_date: {cct.get_lastdays_trade_date(1)}" )
    if end is not None:
        # print end,df.index[-1]
        if len(df) == 0:
            return df
        if end <= df.index[-1]:
            # print(end, df.index[-1])
            # return df
            duration = 0
        else:
            today = end

    if duration > 1 and (tdx_last_day != cct.get_lastdays_trade_date(1)):
        try:
            ds = get_kdate_data(code_ts, start=tdx_last_day,
                                end=today, index=index_status)
            if ds is None:
                return df
            if index_status:
                ds['volume'] = [round(x / 100 /100,1) for x in ds['volume']]
            # ds['volume'] = ds.volume.apply(lambda x: x * 100)
            # ds = ts.get_h_data('000001', start=tdx_last_day, end=today,index=index_status)
            # df.index = pd.to_datetime(df.index)
        except (IOError, EOFError, Exception) as e:
            print("Error Duration:", e, end=' ')
            print("code:%s" % (code))
            cct.sleep(0.1)
            # ds = ts.get_h_data(code_t, start=tdx_last_day, end=today, index=index_status)
            # df.index = pd.to_datetime(df.index)
        if ds is not None and len(ds) >= 1:
            if len(df) > 0:
                lends = len(ds)
            else:
                lends = len(ds) + 1
            ds = ds[:lends - 1]
            ds['code'] = code
#            ds['volume']=ds.volume.apply(lambda x: x * 100)
            if not 'amount' in ds.columns:
                ds['amount'] = list(map(lambda x, y, z: round(
                    (y + z) / 2  * x, 1), ds.volume, ds.high, ds.low))
                    # (y + z) / 2 /100 * x, 1), ds.volume, ds.high, ds.low))
            else:
                ds['amount'] = ds['amount'].apply(lambda x: round(x , 1))

            ds = ds.loc[:, ['code', 'open', 'high',
                            'low', 'close', 'volume', 'amount']]
            cols = ['code', 'open', 'high', 'low', 'close']
            # code 通常是字符串或整数，先排除
            num_cols = ['open', 'high', 'low', 'close']
            # ds.loc[:, num_cols] = ds.loc[:, num_cols].round(2)
            ds.loc[:, num_cols] = (
                ds.loc[:, num_cols]
                .apply(pd.to_numeric, errors='coerce')
                .round(2)
            )

            # ds.rename(columns={'volume': 'amount'}, inplace=True)
            ds.rename(columns={'volume': 'vol'}, inplace=True)
            ds.sort_index(ascending=True, inplace=True)
            ds = ds.fillna(0)
            df = pd.concat([df,ds])

            # if (len(ds) == 1 and ds.index.values[0] != cct.get_today()) or len(ds) > 1:
            if (len(ds) == 1 and ((not cct.get_work_time()) or (ds.index.values[0] != cct.get_today())) ) or len(ds) > 1:
                duration_day= cct.get_today_duration(ds.index.values[0],cct.get_today())
                if duration_day is not None and duration_day < 5:
                    log.error(f'{code} write_tdx_tushare_to_file-duration_day: {duration_day}')
                    # 随机生成 0 到 2 之间的浮点数
                    delay = random.uniform(0.1, 1.8)
                    time.sleep(delay)
                    sta = write_tdx_tushare_to_file(code, df=df)
                    if sta:
                        log.info("write %s OK." % (code))
                        if today == ds.index[-1]:
                            return df
                    else:
                        log.warn("write %s error." % (code))

    if cct.get_now_time_int() > 900 and cct.get_now_time_int() < 930 and len(df) > 0:
        log.debug("now > 830 and <930 return")
        df = df.sort_index(ascending=True)
        df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
        df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
        df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
        df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
        df = df.fillna(0)
        df = df.sort_index(ascending=False)
        return df
#    print df.index.values,code
    if dm is None and end is None:
        # if dm is None and today != df.index[-1]:
        # log.warn('today != end:%s'%(df.index[-1]))
        if index_status:
            dm = sina_data.Sina().get_stock_code_data(code, index=index_status)
            # dm = dm.set_index('code')
        else:
            dm = sina_data.Sina().get_stock_code_data(code)
    if len(df) != 0 and duration == 0:
        writedm = False
    else:
        writedm = True

    if df is not None and len(df) > 0:
        if df.index.values[-1] == today:
            if dm is not None and not isinstance(dm, Series) and code in dm.index:
                dz = dm.loc[code].to_frame().T
            else:
                return df
            if index_status:
                vol_div = 1000
            else:
                vol_div = 10

            if round(dz.open.values[0], 1) == round(df.open[-1], 1) and 'volume' in dz.columns and int(df.vol[-1] / vol_div) == int(dz.volume.values / vol_div):
                df = df.sort_index(ascending=True)
                df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
                df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
                df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
                df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
                df = df.fillna(0)
                df = df.sort_index(ascending=False)
                return df
            else:
                writedm = True

    if not writedm and cct.get_now_time_int() > 1530 or cct.get_now_time_int() < 925:
        return df

    if dm is not None and not dm.empty:
        if len(dm) > 0:
            if code in dm.index:
                dm = dm.loc[code, :].to_frame().T
            else:
                dm = sina_data.Sina().get_stock_code_data(code)
                if dm is None or len(dm) == 0:
                    log.error("code is't find:%s" % (code))
                    return df
        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)
        c_name = dm.loc[code, ['name']].values[0]
        dm_code = (dm.loc[code, ['open', 'high', 'low',
                                 'close', 'amount', 'vol']]).to_frame().T
        log.debug("dm_code:%s" % dm_code)
        # dm_code['amount'] = round(float(dm_code['amount']), 2)
        # if index_status:
        #     if code == 'sh':
        #         code_ts = '999999'
        #     else:
        #         code_ts = code_t
        #     dm_code['code'] = code_ts
        # else:
        #     dm_code['code'] = code
        dm_code['date'] = today
        dm_code = dm_code.set_index('date')
        # log.debug("df.open:%s dm.open%s" % (df.open[-1], round(dm.open[-1], 2)))
        # print df.close[-1],round(dm.close[-1],2)

        if end is None and ((df is not None and not dm.empty) and ((len(df) > 0 and round(df.open[-1], 2) != round(dm.open[-1], 2) )) or ((len(df) > 0 and round(df.close[-1], 2) != round(dm.close[-1], 2)))):
            if dm.open[0] > 0 and len(df) > 0:
                if dm_code.index[-1] == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])
            elif len(dm) != 0 and len(df) == 0:
                df = dm_code
        else:
            df = dm_code
                # df = df.astype(float)
            # df=pd.concat([df,dm],axis=0, ignore_index=True).set
        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))

    if len(df) > 5:
        df = df.sort_index(ascending=True)
        df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
        df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
        df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
        df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
        df = df.fillna(0)
        df = df.sort_index(ascending=False)

    if writedm and len(df) > 0:
        if cct.get_now_time_int() < 900 or cct.get_now_time_int() > 1505:
            df['amount'] = df['amount'].apply(lambda x: round(x, 2))
            sta = write_tdx_sina_data_to_file(code, df=df)
    return df


def write_tdx_tushare_to_file(code, df=None, start=None, type='f',rewrite=False):
    #    st=time.time()
    #    pname = 'sdata/SH601998.txt'
    # rewritefile = False
    
    code_u = cct.code_to_symbol(code)
    if code_u.startswith('bj'):
        return None
    log.debug("tushare code:%s code_u:%s" % (code, code_u))
    # if type == 'f':
    #     file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    # elif type == 'b':
    #     file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    # else:
    #     return None
    # file_path = get_code_file_path(code)

    base = 'forwardp' if type == 'f' else 'backp'
    file_path = os.path.join(exp_path, base, f"{code_u.upper()}.txt")

    #add 250527 johnson
    if rewrite:
        o_file = open(file_path, 'w+')
        o_file.truncate()
        o_file.close()

    if df is None:
        # df = get_tdx_Exp_day_to_df(code, newdays=0)
        ldatedf = get_tdx_Exp_day_to_df(code, dl=1, newdays=0)
        if len(ldatedf) > 0:
            lastd = ldatedf.date
        else:
            k_df = get_kdate_data(code)
            if len(k_df) > 0:
                df = k_df
            else:
                return False
        # today = cct.get_today()
        # duration = cct.get_today_duration(tdx_last_day)
        if df is None:
            if lastd == cct.last_tddate(1):
                return False
            df = get_tdx_append_now_df_api(
                code, start=start, write_tushare=False, newdays=0)
    # else:
    #     ldatedf = get_tdx_Exp_day_to_df(code, newdays=0)
    #     if len(ldatedf) < 10 and len(df) > 50:
    #         rewritefile = True

    if len(df) == 0:
        return False


    if not os.path.exists(file_path) and len(df) > 0:
        # fo = open(file_path, "w+")
        fo = open(file_path, "wb+")
#        return False
    else:
        # if rewritefile:
        #     os.remove(file_path)
        #     fo = open(file_path, "wb+")
        # else:
        fo = open(file_path, "rb+")

    fsize = os.path.getsize(file_path)
    limitpo = fsize if fsize < 150 else 150

    if not os.path.exists(file_path) or os.path.getsize(file_path) < limitpo:
        log.warn("not path:%s" % (file_path))
        return False


    if fsize != 0:
        fo.seek(-limitpo, 2)
        plist = []
        line = True
        while line:
            tmpo = fo.tell()
            line = fo.readline().decode(errors="ignore")
            alist = line.split(',')
            if len(alist) >= 7:
                if len(alist[0]) != 10:
                    continue
                tvol = round(float(alist[5]), 0)
                tamount = round(float(alist[6].split('\r')[0].replace('\r\n', '')), 0)
    #            print int(tamount)
                if fsize > 600 and (int(tvol) == 0 or int(tamount) == 0):
                    continue
    #            print line,tmpo
                if tmpo not in plist:
                    plist.append(tmpo)
        if len(plist) == 0:
            # raise Exception("data position is None")
            log.error("Exception:%s data position is None to 0" % (code))
            write_all_kdata_to_file(code, file_path)
            return False
        po = plist[-1]
        fo.seek(po)
        dater = fo.read(10).decode(errors="ignore")
        if dater.startswith('\n') and len(dater) == 10:
            po = plist[-1] + 2
            fo.seek(po)
            dater = fo.read(10).decode(errors="ignore")
        df = df[df.index >= dater]
    if len(df) >= 1:
        if fsize == 0:
            po = 0
        df = df.fillna(0)
        df.sort_index(ascending=True, inplace=True)
        fo.seek(po)
        if 'volume' in df.columns:
            df.rename(columns={'volume': 'vol'}, inplace=True)
        if not 'amount' in df.columns:
            df['amount'] = list(map(lambda x, y, z: round(
                (y + z) / 2 * x, 1), df.vol, df.high, df.low))
        else:
            df['amount'] = df['amount'].apply(lambda x: round(x , 1))

        w_t = time.time()
        wdata_list = []
        for date in df.index:
            td = df.loc[date, ['open', 'high',
                               'close', 'low', 'vol', 'amount']]
            if td.open > 0 and td.high > 0 and td.low > 0 and td.close > 0:
                tdate = str(date)[:10]
                topen = str(td.open)
                thigh = str(td.high)
                tlow = str(td.low)
                tclose = str(td.close)
                # tvol = round(float(a[5]) / 10, 2)
                tvol = str(td.vol)
                amount = str(td.amount)
                tdata = tdate + ',' + topen + ',' + thigh + ',' + tlow + \
                    ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                    # ',' + tclose + ',' + tvol + ',' + amount + '\n'
                    # ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                wdata_list.append(tdata.encode())
#        import cStringIO
#        b = cStringIO.StringIO()
#        x=0
#        while x < len(wdata_list):
#            b.write(wdata_list[x])
#            x += 1
# fo.write(b.getvalue())

        #rb+ wb+ byte bug
        fo.writelines(wdata_list)
        fo.close()
        log.info(f"code :{code} write_done:{(time.time() - w_t):.3f}")
        return True
    fo.close()
    return "NTrue"


def write_tdx_sina_data_to_file(code, dm=None, df=None, dl=2, type='f'):
    #    ts=time.time()
    #    if dm is None:
    #        dm = get_sina_data_df(code)
    #    if df is None:
    #        dz = dm.loc[code].to_frame().T
    #        df = get_tdx_append_now_df_api2(code,dl=dl,dm=dz,newdays=5)

    if df is None and dm is None or len(df) == 0:
        return False

    code_u = cct.code_to_symbol(code)
    log.debug("code:%s code_u:%s" % (code, code_u))
    # if type == 'f':
    #     file_path = exp_path + 'forwardp' + path_sep + code_u.upper() + ".txt"
    # elif type == 'b':
    #     file_path = exp_path + 'backp' + path_sep + code_u.upper() + ".txt"
    # else:
    #     return None
    base = 'forwardp' if type == 'f' else 'backp'
    file_path = os.path.join(exp_path, base, f"{code_u.upper()}.txt")

    if not os.path.exists(file_path) and len(df) > 0:
        fo = open(file_path, "w+")
#        return False
    else:
        fo = open(file_path, "rb+")

    fsize = os.path.getsize(file_path)
    limitpo = fsize if fsize < 150 else 150

    if limitpo > 40:
        fo.seek(-limitpo, 2)
        plist = []
        line = True
        while line:
            tmpo = fo.tell()
            line = fo.readline().decode(errors="ignore")
            alist = line.split(',')
            if len(alist) >= 7:
                if len(alist[0]) != 10:
                    continue
                tdate = alist[0]
                tvol = round(float(alist[5]), 0)
                tamount = round(float(alist[6].split('\r')[0].replace('\r\n', '')), 0)
                # tamount = round(float(alist[6].split('\r')[0].replace('\n', '')), 0)
    #            print int(tamount)
                if fsize > 600 and (int(tvol) == 0 or int(tamount) == 0):
                    continue
    #            print line,tmpo
                if tmpo not in plist:
                    plist.append(tmpo)
    #                break
        if len(plist) == 0:
            log.error("Exception:%s data position is None to 0" % (code))
            write_all_kdata_to_file(code, file_path)
            return False
        po = plist[-1]
        fo.seek(po)
        dater = fo.read(10).decode(errors="ignore")
        if dater.startswith('\n') and len(dater) == 10:
            po = plist[-1] + 2
            fo.seek(po)
            dater = fo.read(10).decode(errors="ignore")
        df = df[df.index >= dater]

    if len(df) >= 1:
        df = df.fillna(0)
        df.sort_index(ascending=True, inplace=True)
        if limitpo > 40:
            fo.seek(po)
        w_data = []
        for date in df.index:
            td = df.loc[date, ['open', 'high',
                               'close', 'low', 'vol', 'amount']]
            tdate = date
            if len(tdate) != 10:
                continue

            # topen = str(round(td.open, 2))
            # thigh = str(round(td.high, 2))
            # tlow = str(round(td.low, 2))
            # tclose = str(round(td.close, 2))
            
            topen = f"{td.open:.2f}"
            thigh = f"{td.high:.2f}"
            tlow = f"{td.low:.2f}"
            tclose = f"{td.close:.2f}"
            # tvol = round(float(a[5]) / 10, 2)
            tvol = str(round(td.vol))
            # amount = str(round(td.amount, 2))
            amount = f"{td.amount:.2f}"
            tdata = tdate + ',' + topen + ',' + thigh + ',' + tlow + \
                ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
                # ',' + tclose + ',' + tvol + ',' + amount + '\n'
                # ',' + tclose + ',' + tvol + ',' + amount + '\r\n'
            w_data.append(tdata.encode())
        fo.writelines(w_data)
        fo.close()
        return True
    fo.flush()
    fo.close()
    return "NTrue"


def Write_tdx_all_to_hdf(market, h5_fname='tdx_all_df', h5_table='all', dl=300, index=False, rewrite=False):
    """[summary]

    [Write all code tdx to h5]

    Arguments:
        market {[type]} -- ['cyb','sz','sh']

    Keyword Arguments:
        h5_fname {str} -- [description] (default: {'tdx_all_df'})
        h5_table {str} -- [description] (default: {'all'})
        dl {number} -- [description] (default: {300})
        index {bool} -- [description] (default: {False})

    Returns:
        [boll] -- [write status]
    """

    time_a = time.time()
    if not h5_fname.endswith(str(dl)):
        h5_fname = h5_fname + '_' + str(dl)
        h5_table = h5_table + '_' + str(dl)
    else:
        log.error("start write index tdx data:%s" % (tdx_index_code_list))

    if market == 'all':
        index_key = tdx_index_code_list
        Write_tdx_all_to_hdf(index_key, h5_fname=h5_fname, h5_table=h5_table, dl=dl, index=True,rewrite = rewrite)
        index = False
        rewrite = False
        market = ['all']
        # market = ['cyb', 'sh', 'sz']
    if not isinstance(market, list):
        mlist = [market]
    else:
        mlist = market

    if index:
        mlist = ['inx']
    status = False

    for ma in mlist:
        dd = pd.DataFrame()
        if not index:
            df = sina_data.Sina().market(ma)
            dfcode = df.index.tolist()
        else:
            dfcode = market
        # print dfcode[:5]
        print("ma:%s dl:%s count:%s" % (ma, dl, len(dfcode)))
        # f_name = 'tdx_all_df_30'
        time_s = time.time()
        # st=h5a.get_hdf5_file(f_name, wr_mode='w', complevel=9, complib='zlib',mutiindx=True)
        # for code in dfcode[:500]:
        idx = 0
        for code in dfcode:
            # for code in dfcode:
            df = get_tdx_Exp_day_to_df(code, dl=dl, MultiIndex=True)

            # df = df[1:] # 取消最新一天数据

            # print df
            # (map(lambda x, y: y if int(x) == 0 else x, top_dif['buy'].values, top_dif['trade'].values))
            # print df.index
            idx+=1
            if idx%100 == 1:
                print(".",end='')
            if len(df) > 0:
                # df.index = map(lambda x: x.replace('-', '').replace('\n', ''), df.index)
                df.index = [x.replace('\n', '') for x in df.index]
                df.index = df.index.astype(str)
                df.index.name = 'date'
                df.index = pd.to_datetime(df.index)
                if 'code' in df.columns:
                    df.code = df.code.astype(str)

                '''sina_data MutiIndex
                df.index = df.index.astype(str)
                df.ticktime = df.ticktime.astype(str)
                # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
                df.ticktime = map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime)
                df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')
                # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
                df = df.loc[:, ['close', 'high', 'low', 'llastp', 'volume', 'ticktime']]
                if 'code' not in df.columns:
                   df = df.reset_index()
                if 'dt' in df.columns:
                   df = df.drop(['dt'], axis=1)
                   # df.dt = df.dt.astype(str)
                if 'name' in df.columns:
                   # df.name = df.name.astype(str)
                   df = df.drop(['name'], axis=1)
                df = df.set_index(['code', 'ticktime'])
                h5a.write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True)
                log.info("hdf5 class all :%s  time:%0.2f" % (len(df), time.time() - time_s))
                '''

                # df.info()
                # if 'code' in df.columns:
                # df.drop(['code'],axis=1,inplace=True)

                df = df.sort_index(ascending=True)
                df = df.loc[:, ['code','open', 'high', 'low', 'close', 'vol', 'amount']]
                df = df.reset_index()
                df = df.set_index(['code', 'date'])
                # df = df.astype(float)
                # xcode = cct.code_to_symbol(code)
                # if len(dd) >0:
                #     print "code:%s df in :%s"%(code,code in dd.index.get_level_values('code'))
                dd = pd.concat([dd, df], axis=0)
                # print ".", len(dd)
                # st.append(xcode,df)
                # put_time = time.time()
                # st.put("df", df, format="table", append=True, data_columns=['code','date'])
                # print "t:%0.1f"%(time.time()-put_time),
                # aa[aa.index.get_level_values('code')==333]
                # st.select_column('df','code').unique()
                # %timeit st.select_column('df','code')
                # %timeit st.select('df',columns=['close'])
                # result_df = df.loc[(df.index.get_level_values('A') > 1.7) & (df.index.get_level_values('B') < 666)]
                # x.loc[(x.A>=3.3)&(x.A<=6.6)]
                # st[xcode]=df
                '''
                Traceback (most recent call last):
                  File "tdx_data_Day.py", line 3013, in <module>
                    df = get_tdx_Exp_day_to_df(code,dl=30)
                  File "tdx_data_Day.py", line 200, in get_tdx_Exp_day_to_df
                    topen = float(a[1])
                IndexError: list index out of range
                Closing remaining open files:/Volumes/RamDisk/tdx_all_df_30.h5...done
                '''
        concat_t = time.time() - time_s

        # dd = dd.loc[:,[u'open', u'high', u'low', u'close', u'vol', u'amount']]
        print(("rewrite:%s dd.concat all :%s  time:%0.2f" % (rewrite, len(dfcode), concat_t)))
        status = h5a.write_hdf_db(h5_fname, dd, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True,rewrite=rewrite)
        if status:
            print(("hdf5 write all ok:%s  atime:%0.2f wtime:%0.2f" % (len(dfcode), time.time() - time_a, time.time() - time_s - concat_t)))
        else:
            print(("hdf5 write false:%s  atime:%0.2f wtime:%0.2f" % (len(dfcode), time.time() - time_a, time.time() - time_s - concat_t)))

    return status


def Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=300, index=False):
    """[summary]

    [description]

    Keyword Arguments:
        market {str} -- [description] (default: {'all'})
        h5_fname {str} -- [description] (default: {'tdx_all_df'})
        h5_table {str} -- [description] (default: {'all'})
        dl {number} -- [description] (default: {300})
        index {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """
    h5_fname = h5_fname + '_' + str(dl)
    h5_table = h5_table + '_' + str(dl)
    status = False
    if cct.get_work_day_status() and (cct.get_now_time_int() > 1500 or cct.get_now_time_int() < 900):
        if market == 'all':
            index = False
            # mlist = ['sh', 'sz', 'cyb' ,'kcb']
            mlist = ['sh', 'sz', 'cyb']
        else:
            if index:
                mlist = ['inx']
            else:
                mlist = [market]
        # results = []
        for mk in mlist:
            time_t = time.time()
            if not index:
                df = sina_data.Sina().market(mk)
                if 'b1' in df.columns:
                    df = df[(df.b1 > 0) | (df.a1 > 0)]
            else:
                df = sina_data.Sina().get_stock_list_data(market)
            allcount = len(df)
            # df = rl.get_sina_Market_json(mk)
            # print df.loc['600581']

            print(("market:%s A:%s open:%s" % (mk, allcount, len(df))), end=' ')
            # code_list = df.index.tolist()
            # df = get_sina_data_df(code_list)


            # df.index = [x.replace('\n', '') for x in df.index]
            # df.index = df.index.astype(str)
            # df.index.name = 'date'
            # df.index = pd.to_datetime(df.index)
            # if 'code' in df.columns:
            #     df.code = df.code.astype(str)

            df.index = df.index.astype(str)
            # df.ticktime = map(lambda x: int(x.replace(':', '')), df.ticktime)
            # df.ticktime = map(lambda x, y: str(x) + ' ' + str(y), df.dt, df.ticktime)
            # df.ticktime = pd.to_datetime(df.ticktime, format='%Y-%m-%d %H:%M:%S')
            df.dt = df.dt.astype(str)
            df['dt'] = ([str(x)[:10] for x in df['dt']])

            # df = df.loc[:, ['open', 'high', 'low', 'close', 'llastp', 'volume', 'ticktime']]
            # ['code', 'date', 'open', 'high', 'low', 'close', 'vol','amount']
            df.rename(columns={'volume': 'vol', 'turnover': 'amount', 'dt': 'date'}, inplace=True)
            #write py3 all hdf need datetime
            df['date'] = pd.to_datetime(df['date'])
            df = df.loc[:, ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']]
            if 'code' not in df.columns:
                df = df.reset_index()
            # if 'dt' in df.columns:
                # df = df.drop(['dt'], axis=1)
                # df.dt = df.dt.astype(str)
            # if 'name' in df.columns:
                # df.name = df.name.astype(str)
                # df = df.drop(['name'], axis=1)
            df = df.set_index(['code', 'date'])
            df = df.astype(float)
            status = h5a.write_hdf_db(h5_fname, df, table=h5_table, index=False, baseCount=500, append=False, MultiIndex=True)
            # search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date',tail=1)
            if status is not None and status:
                print("Tdx writime:%0.2f" % (time.time() - time_t))
            else:
                print("Tdx no writime:%0.2f" % (time.time() - time_t))

        return status
    else:
        log.info("no work day data or < 1500")
    return status


def search_Tdx_multi_data_duration(fname='tdx_all_df_300', table='all_300', df=None,  code_l=None, start=None, end=None, freq=None, col=None, index='date',tail=0):
    """[summary]

    [description]

    Keyword Arguments:
        fname {str} -- [description] (default: {'tdx_all_df_300'})
        table {str} -- [description] (default: {'all_300'})
        df {[type]} -- [description] (default: {None})
        code_l {[type]} -- [description] (default: {None})
        start {[type]} -- [description] (default: {None})
        end {[type]} -- [description] (default: {None})
        freq {[type]} -- [description] (default: {None})
        col {[type]} -- [description] (default: {None})
        index {str} -- [description] (default: {'date'})

    Returns:
        [type] -- [description]
    """
    # h5_fname='tdx_all_df'
    # h5_table='all'
    # dl=300
    time_s = time.time()
    # h5_fname = h5_fname +'_'+str(dl)
    # h5_table = h5_table + '_' + str(dl)

    tdx_hd5_name = cct.tdx_hd5_name
    log.debug(f'tdx_hd5_name:{tdx_hd5_name}')
    if df is None and fname == tdx_hd5_name:
        df = cct.GlobalValues().getkey(tdx_hd5_name)
        
    if df is None:
        if start is not None and len(str(start)) < 8:
            df_tmp = get_tdx_Exp_day_to_df('999999', end=end).sort_index(ascending=False)
            start = df_tmp.index[start]
        h5 = h5a.load_hdf_db(fname, table=table, code_l=code_l, timelimit=False, MultiIndex=True)
    else:
        h5 = df.loc[df.index.isin(code_l, level='code')]

    if h5 is not None and len(h5) > 0:
        h51 = cct.get_limit_multiIndex_Row(h5, col=col, index=index, start=start, end=end)
    else:
        h51 = None
        # log.error("h5 is None")
    if fname == tdx_hd5_name:
        if h51 is not None and len(h51) > 0 and cct.GlobalValues().getkey(tdx_hd5_name) is None:
            # cct.GlobalValues()
            log.info("cct.GlobalValues().getkey(%s)" % (tdx_hd5_name))
            cct.GlobalValues().setkey(tdx_hd5_name, h51)
        else:
            log.info("cct.GlobalValues().setkey(%s) is ok" % (tdx_hd5_name))

    log.info("search_Multi_tdx time:%0.2f" % (time.time() - time_s))
    if tail == 0:
        return h51
    else:
        return h51.groupby(level=[0]).tail(tail)
# code_list = ['000001','399006','999999']
# code_list = sina_data.Sina().all.index.tolist()
# print(f'code_list:{len(code_list)}')
# df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start=20170101, end=None, freq=None, col=None, index='date')
# import ipdb;ipdb.set_trace()

# print df.index.get_level_values('code').unique().shape
# print df.loc['600310']

# duration_zero=[]
# duration_other=[]

def check_tdx_Exp_day_duration(market='all'):
    duration_zero=[]
    duration_other=[]
    df = sina_data.Sina().market(market)
    df = df[df.high > 0]    
    for code in df.index:
        dd = get_tdx_Exp_day_to_df(code, dl=1) 
        duration = cct.get_today_duration(dd.date,tdx=True) if dd is not None and len(dd) > 5 else -1
        if duration == 0:
            duration_zero.append(code)
        elif duration > 0 and duration < 60:
            duration_other.append(code)
    duration_zero =list(set(duration_zero))
    duration_other = list(set(duration_other))
    log.info(("duration_zero:%s duration_other:%s"%(len(duration_zero),len(duration_other))))
    return duration_other

def write_market_index_to_df():
    dm_index = sina_data.Sina().get_stock_list_data(tdx_index_code_list,index=True)
    for inx in tdx_index_code_list:
        log.info(f'write index append to df:{inx}')
        get_tdx_append_now_df_api_tofile(inx,dm=dm_index)

def Write_market_all_day_mp(market='all', rewrite=False,recheck=True,detect_calc_support=False):
    """
    rewrite True: history date ?
    rewrite False: Now Sina date

    """
    sh_index = '000002'
    dd = get_tdx_Exp_day_to_df(sh_index, dl=1)

    log.info(f'check_tdx_Exp_day_duration:{market}')
    duration_code=check_tdx_Exp_day_duration(market)

    # print dt,dd.date
    if market == 'alla':
        rewrite = True
        market = 'all'
    # if not rewrite and len(dd) > 0:
    if not rewrite:
        if len(duration_code) == 0:
            print("Duration:%s is OK" % (len(duration_code)))
            # return False
        else:
            if len(duration_code) < 10:
                print(f"Write duration_code: {len(duration_code)} code:{duration_code}")
            else:
                print("Write duration_code:%s " %(len(duration_code)))
            log.info("duration to write :%s"%(len(duration_code)))
    if len(duration_code) == 0:
        dfs = search_Tdx_multi_data_duration(code_l=[sh_index],tail=1)
        mdate = dfs.reset_index().date.values
        mdate = str(mdate[0])[:10] if len(mdate) > 0 else mdate
        if mdate == dd.date:
            print("Multi_data:%s %s all writed" % (sh_index,mdate))
            log.info("Multi_data:%s %s all writed" % (sh_index,mdate))
            return True

    if market == 'all':
        mlist = ['all']

    else:
        mlist = [market]

    results = []

    if len(duration_code) > 0:
        for mk in mlist:
            time_t = time.time()
            df = sina_data.Sina().market(mk)

            if df is None or len(df) < 10:
                print("dsina_data f is None")
                break
            else:

                df = df[((df.b1 > 0) | (df.a1 > 0))]

            code_list = duration_code
            dm = get_sina_data_df(code_list)
            dm = dm[((dm.open > 0) | (dm.a1 > 0))]
            print(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))), end=' ')
            log.info(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))))
            count_list = len(code_list)
            # count_list = len(['000002'])
            log.info('code_list:%s df:%s' % (code_list if count_list < 10 else count_list, len(df)))

            if len(dm) > 0:
                results = cct.to_mp_run_async(
                    get_tdx_append_now_df_api_tofile, code_list, dm=dm, newdays=0,detect_calc_support=detect_calc_support)

                # for code in code_list:
                #    print(code,)
                #    results.append(get_tdx_append_now_df_api_tofile(code, dm=dm, newdays=0,detect_calc_support=detect_calc_support))
                # results = get_tdx_exp_low_or_high_price(codeList[0], dt,ptype,dl)))

            else:
                print(("dm is not open sell:%s"%(code_list if len(code_list) <10 else len(code_list))))
                log.info(("dm is not open sell:%s"%(code_list if len(code_list) <10 else len(code_list))))


            if recheck:
                duration_code=check_tdx_Exp_day_duration(market)
                if len(duration_code) > 0 and recheck: 
                    if len(duration_code) < 30:
                        log.info(f'recheck duration_code:{len(duration_code)} to write')
                    else:
                        print(f'recheck duration_code write:{len(duration_code)}: {duration_code[:5]}')
                        log.info(f'recheck duration_code write:{len(duration_code)}: {duration_code[:5]}')

                    results = cct.to_mp_run_async(
                        get_tdx_append_now_df_api_tofile, duration_code, dm=dm, newdays=0,detect_calc_support=detect_calc_support)
                    print(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))), end=' ')
                    log.info(("market:%s A:%s open_dm:%s" % (mk, len(df),len(dm))))

        if recheck:
            recheck = False
        print("AllWrite:%s t:%s"%(len(duration_code),round(time.time() - time_t, 2)))
        log.info("AllWrite:%s t:%s"%(len(duration_code),round(time.time() - time_t, 2)))




    if market == 'all':

        dm_index = sina_data.Sina().get_stock_list_data(tdx_index_code_list,index=True)
        for inx in tdx_index_code_list:
            get_tdx_append_now_df_api_tofile(inx,dm=dm_index)
        print("")
        print("Index Wri 300 ok", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True)
        Write_sina_to_tdx(market='all')
        print("Index Wri 900 ok", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True,dl=900)
        Write_sina_to_tdx(market='all', h5_fname='tdx_all_df', h5_table='all', dl=900)
    print("All is ok")
    return results


def get_tdx_power_now_df(code, start=None, end=None, type='f', df=None, dm=None, dl=None,detect_calc_support=False):
    if code == '999999' or code.startswith('399'):

        if start is None and dl is not None:
            start = cct.get_trade_day_before_dl(dl)
            # start = cct.last_tddate(days=dl)
        df = get_tdx_append_now_df_api(
            code, start=start, end=end, type=type, df=df, dm=dm,detect_calc_support=detect_calc_support)
        return df
    start = cct.day8_to_day10(start)
    end = cct.day8_to_day10(end)
    if df is None:
        df = get_tdx_Exp_day_to_df(
            code, type=type, start=start, end=end, dl=dl).sort_index(ascending=True)
        if len(df) > 0:
            df['vol'] = [round(x * 10, 1) for x in df.vol.values]
        else:
            log.warn("%s df is Empty" % (code))
        if end is not None:
            return df
    else:
        df = df.sort_index(ascending=True)
    today = cct.get_today()
    if dm is None and (today != df.index[-1] or df.vol[-1] < df.vol[-2] * 0.8)and (cct.get_now_time_int() < 830 or cct.get_now_time_int() > 930):

        dm = sina_data.Sina().get_stock_code_data(code)

    if dm is not None and df is not None and not dm.empty:

        dm.rename(columns={'volume': 'vol',
                           'turnover': 'amount'}, inplace=True)
        c_name = dm.loc[code, ['name']].values[0]
        dm_code = (
            dm.loc[:, ['open', 'high', 'low', 'close', 'amount', 'vol']])
        log.debug("dm_code:%s" % dm_code)

        dm_code['code'] = code

        dm_code['date'] = today
        dm_code = dm_code.set_index('date')
        log.debug("df.code:%s" % (code))
        log.debug("df.open:%s dm.open%s" %
                  (df.open[-1], round(dm.open[-1], 2)))


        if end is None and ((df is not None and not dm.empty) and (round(df.open[-1], 2) != round(dm.open[-1], 2)) and (round(df.close[-1], 2) and round(dm.close[-1], 2))):
            if dm.open[0] > 0:
                if dm_code.index == df.index[-1]:
                    log.debug("app_api_dm.Index:%s df:%s" %
                              (dm_code.index.values, df.index[-1]))
                    df = df.drop(dm_code.index)
                df = pd.concat([df,dm_code])


        df['name'] = c_name
        log.debug("c_name:%s df.name:%s" % (c_name, df.name[-1]))
    if len(df) > 0:
        df = df.sort_index(ascending=True)
        df['ma5d'] = talib.SMA(df['close'], timeperiod=5)
        df['ma10d'] = talib.SMA(df['close'], timeperiod=10)
        df['ma20d'] = talib.SMA(df['close'], timeperiod=26)
        df['ma60d'] = talib.SMA(df['close'], timeperiod=60)
        # df['ma5d'].fillna(0)
        # df['ma10d'].fillna(0)
        # df['ma20d'].fillna(0)
        # df['ma60d'].fillna(0)
        df = df.fillna(0)
        df = df.sort_index(ascending=False)

    df = get_tdx_macd(df,detect_calc_support=detect_calc_support)
    return df


def get_sina_data_df(code,index=False):

    # index_status=False

    if isinstance(code, list):
        if len(code) > 0:
            dm = sina_data.Sina().get_stock_list_data(code,index=index)
        else:
            dm=[]
            log.error("code is None:%s"%(code))
    else:
        dm = sina_data.Sina().get_stock_code_data(code,index=index)
    return dm

def get_sina_data_cname(cname,index=False):
    # index_status=False
    code = sina_data.Sina().get_cname_code(cname)
    return code

def get_sina_data_code(code,index=False):
    # index_status=False
    if not index:
        cname = sina_data.Sina().get_code_cname(code)
    else:
        cname = sina_data.Sina().get_stock_code_data(code,index=index).name[0]
    return cname

def get_sina_datadf_cnamedf(code,df,index=False,categorylimit=16):
    # index_status=False
    dm = get_sina_data_df(code)
    # ths = wcd.search_ths_data(code)
    ths = wcd.get_wencai_data(df,categorylimit=categorylimit)
    if 'close' not in df.columns:
        dd = cct.combine_dataFrame(df,dm.loc[:,['close','name']])
    else:
        dd = cct.combine_dataFrame(df,dm['name'])
    if ths is not None and 'category' in ths.columns:
        dd = cct.combine_dataFrame(dd,ths.loc[:,['category','hangye']])
    # cname = sina_data.Sina().get_code_cname(code)
    return dd

# print get_sina_data_cname('通合科技')
def getSinaJsondf(market='cyb', vol=ct.json_countVol, vtype=ct.json_countType):
    df = rl.get_sina_Market_json(market)
    top_now = rl.get_market_price_sina_dd_realTime(df, vol, vtype)
    return top_now


def getSinaIndexdf():
    # '''
    # # return index df,no work
    # '''
    # dm_index = sina_data.Sina().get_stock_code_data('999999,399001,399006',index=True)
    # # dm = get_sina_data_df(dm_index.index.tolist())
    # dm = cct.combine_dataFrame(dm, dm_index, col=None, compare=None, append=True, clean=True)
    dm = getSinaAlldf(market='index')
    # tdxdata = get_tdx_exp_all_LastDF_DL(
    #             dm.index.tolist(), dt=30,power=True)

    top_all, lastpTDX_DF = get_append_lastp_to_df(dm, None, dl=ct.duration_date_day, power=ct.lastPower)

    if 'lvolume' not in top_all.columns:
        top_all.rename(columns={'lvol': 'lvolume'}, inplace=True)
    # from JSONData import powerCompute as pct
    # top_all = pct.powerCompute_df(top_all.index.tolist(), dl=ct.PowerCountdl, talib=True, filter='y', index=True)

    return top_all

tdxbkdict={'近期新高':'880865','近期异动':'880884'}

def getSinaAlldf(market='kcb', vol=ct.json_countVol, vtype=ct.json_countType, filename='mnbk', table='top_now', trend=False):
    ### Sina获取 Ratio 和tdx数据
    with timed_ctx("getSinaAlldf", warn_ms=1000):
        print("initdx", end=' ')
        market_all = False
        log.info(f'tdd_market: {market}')
    if not isinstance(market, list):
        # m_mark = market.split(',')
        m_mark = market.split('+')
        if len(m_mark) > 1:
            # m_0 = m_mark[0]
            if len(m_mark[0]) > 12:
                m_0 = eval(m_mark[0])
            else:
                m_0 = (m_mark[0])
            market = m_mark[1]
    else:
        m_mark=[]
    if isinstance(market, list):
        code_l = market 
        df = sina_data.Sina().get_stock_list_data(code_l)

    elif market == 'rzrq':

        df = cct.get_rzrq_code()
        code_l = cct.read_to_blocknew('068')
        code_l.extend(df.code.tolist())
        code_l = list(set(code_l))
        df = sina_data.Sina().get_stock_list_data(code_l)

    elif market == 'cx':
        df = cct.get_rzrq_code(market)
    elif market == 'zxb':
        df = cct.get_tushare_market(market, renew=True, days=60)
    elif market == 'captops':
        global initTushareCsv
        if initTushareCsv == 0:
            initTushareCsv += 1
            df = cct.get_tushare_market(market=market, renew=True, days=5)
        else:
            df = cct.get_tushare_market(market, renew=False, days=5)
    elif market == 'index':
            # blkname = '061.blk'
        # df = sina_data.Sina().get_stock_code_data('999999,399001,399006',index=True)
        df = sina_data.Sina().get_stock_code_data(['999999', '399006', '399001'], index=True)

    # elif market.lower().find('indb') >=0 :
    #         # blkname = '061.blk'
    #     indb =  cct.GlobalValues().getkey('indb')
    #     if indb is None:    
    #         code_l = cct.read_to_indb().code.tolist()
    #         cct.GlobalValues().setkey('indb',code_l)
    #     else:
    #         code_l = indb
    #     df = sina_data.Sina().get_stock_list_data(code_l)

    elif market.find('blk') > 0 or market.isdigit():
            # blkname = '061.blk'

        code_l = cct.read_to_blocknew(market)
        df = sina_data.Sina().get_stock_list_data(code_l)

        # if len(code_l) > 0:
        #     df = sina_data.Sina().get_stock_list_data(code_l)
        # else:
        #     df = wcd.get_wcbk_df(filter=market, market=filename,
        #                      perpage=1000, days=ct.wcd_limit_day)
        # df = pd.read_csv(block_path,dtype={'code':str},encoding = 'gbk')
    elif market in ['kcb','sh', 'sz', 'cyb' ,'kcb' ,'bj']:
        # df = rl.get_sina_Market_json(market)
        df = sina_data.Sina().market(market)
        # df = sina_data.Sina().market(market)
    elif market in ['all','bj']:
        df = sina_data.Sina().all
        if market in ['bj']:
            co_inx = [inx for inx in df.index if str(inx).startswith(('43','83','87','92'))]
            df = df.loc[co_inx]
        else:
            market_all = True

    elif market in tdxbkdict.keys():
        codelist = tdxbk.get_tdx_gn_block_code(tdxbkdict[market])
        df = sina_data.Sina().get_stock_list_data(codelist)
    else:
        if filename == 'cxg':
            df = wcd.get_wcbk_df(filter=market, market=filename,
                                 perpage=1000, days=15,monitor=True)
        else:
            df = wcd.get_wcbk_df(filter=market, market=filename,
                                 perpage=1000, days=ct.wcd_limit_day,monitor=True)
        if 'code' in df.columns:
            df = df.set_index('code')
        df = sina_data.Sina().get_stock_list_data(df.index.tolist())


    if isinstance(df, pd.DataFrame) and 'code' in df.columns:
        df = df.set_index('code')

    if len(m_mark) > 1:
        dfw_codel=[]
        if not isinstance(m_0,list):
            dfw = wcd.get_wcbk_df(filter=m_0, market=filename,
                                 perpage=1000, days=ct.wcd_limit_day,monitor=True)
            if 'code' in dfw.columns:
                dfw = dfw.set_index('code')
            dfw_codel = dfw.index.tolist()
        else:
            dfw_codel = m_0
        dfw = sina_data.Sina().get_stock_list_data(dfw_codel)
        df = cct.combine_dataFrame(df,dfw,append=True)
        codelist = df.index.astype(str).tolist()
        

    if trend and isinstance(df, pd.DataFrame):
        code_l = cct.read_to_blocknew('060')
        if market == 'all':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('6', '30', '00'))]
        elif market == 'sh':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('6'))]
        elif market == 'sz':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('00'))]
        elif market == 'cyb':
            co_inx = [inx for inx in code_l if inx in df.index and str(inx).startswith(('30'))]
        else:
            co_inx = [inx for inx in code_l if inx in df.index]
        
        df = df.loc[co_inx]
    # codelist=df.code.tolist()
    # cct._write_to_csv(df,'codeall')
    # top_now = get_mmarket='all'arket_price_sina_dd_realTime(df, vol, type)
#    df =  df.dropna()
    

    if isinstance(df, pd.DataFrame) and len(df) > 0:
        if 'code' in df.columns:
            df = df.set_index('code')
        codelist = df.index.astype(str).tolist()

    elif isinstance(df, list):
        codelist = df
    else:
        if not market  in ['sz','sh']:
            market = 'all'
        df = rl.get_sina_Market_json(market)
#        codelist = df.code.tolist()
#        df = df.set_index('code')
        log.error("get_sina_Market_json %s : %s" % (market, len(df)))
#    if cct.get_now_time_int() > 915:
#        if cct.get_now_time_int() > 930:
#            if 'open' in df.columns:
#                df = df[(df.open > 0)]
#        else:
#            if 'buy' in df.columns:
#                df = df[(df.buy > 0)]

        if isinstance(df, pd.DataFrame):
            codelist = df.index.astype(str).tolist()
        else:
            log.error("df isn't pd:%s" % (df))
            
#    h5_table = market if not cct.check_chinese(market) else filename
#    h5 = top_hdf_api(fname=h5_fname,table=h5_table,df=None)
    h5_fname = 'tdx_now'
    h5_table = 'all'
    time_s = time.time()

    if not market_all and market != 'index':
        dm = sina_data.Sina().get_stock_list_data(codelist)
    else:
        dm = df

    # if cct.get_work_time() or (cct.get_now_time_int() > 915) :
    # dm['percent'] = map(lambda x, y: round((x - y) / y * 100, 2), dm.close.values, dm.llastp.values)
    dm['percent'] = ((dm['close'] - dm['llastp']) / dm['llastp'] * 100).round(2)
    log.debug("dm percent:%s" % (dm[:1]))
    # dm['volume'] = map(lambda x: round(x / 100, 1), dm.volume.values)
    # dm['trade'] = dm['close'] if dm['b1'] ==0 else dm['b1']
    
    dm['trade'] = np.where(dm['now'] > 0, dm['now'], dm['b1'])

    dm['buy'] = dm['trade']
    
    # stop_code = dm[~((dm.b1 > 0) | (dm.a1 > 0) | (dm.buy >0) | (dm.sell >0))].loc[:,['name']].T

    if market != 'index':
        now_time_int = cct.get_now_time_int()
        if now_time_int > 920 and now_time_int < 926:
            # print dm[dm.code=='000001'].b1
            # print dm[dm.code=='000001'].a1
            # print dm[dm.code=='000001'].a1_v
            # print dm[dm.code=='000001'].b1_v
            dm['volume'] = dm['b1_v'].values + dm['b2_v'].values
            # dm = dm[(dm.b1 > 0) | (dm.a1 > 0)]
            dm[((dm.b1 > 0) | (dm.a1 > 0) | (dm.buy >0) | (dm.sell >0))]
            dm['b1_v'] = ((dm['b1_v'] + dm['b2_v']) / 1000000.0).round(1) + 0.01

        elif 926 < now_time_int < 1502 :
            # dm = dm[dm.open > 0]
            # dm = dm[(dm.b1 > 0) | (dm.a1 > 0)]
            dm[((dm.b1 > 0) | (dm.a1 > 0) | (dm.buy >0) | (dm.sell >0))]
            dm['b1_v'] = (dm['b1_v'] / dm['volume'] * 100).round(1)

            # dm['b1_v'] = map(lambda x, y: round(x / y * 100, 1), dm['b1_v'], dm['volume'])

        else:
            # dm = dm[(dm.buy > 0) | (dm.b1 > 0) | (dm.a1 > 0)]
            dm['b1_v'] = (dm['b1_v'] / dm['volume'] * 100).round(1)

    # print 'ratio' in dm.columns
    # print time.time()-time_s
    dm['nvol'] = dm['volume']

    if (cct.get_now_time_int() < 830 or cct.get_now_time_int() > 932) and market not in ['sh', 'sz', 'cyb']:
        dd = rl.get_sina_Market_json('all')
        if isinstance(dd, pd.DataFrame):
            dd.drop([inx for inx in dd.index if inx not in dm.index],
                    axis=0, inplace=True)
            df = dd
    if len(df) < 1 or len(dm) < 1:
        log.info("len(df):%s dm:%s" % (len(df), len(dm)))
        dm['ratio'] = 0.0
    else:
        if len(dm) != len(df):
            log.info("code:%s %s diff:%s" %
                     (len(dm), len(df), len(dm) - len(df))),
#        dm=pd.merge(dm,df.loc[:,['name','ratio']],on='name',how='left')
#        dm=dm.drop_duplicates('code')
        if 'ratio' in df.columns:
            dm = cct.combine_dataFrame(dm, df.loc[:, ['name', 'ratio']])
        else:
            dm = cct.combine_dataFrame(dm, df.loc[:, ['name']])
        log.info("dm combine_df ratio:%s %s" % (len(dm), len(df))),
        dm = dm.fillna(0)
        
    if market != 'index' and (cct.get_now_time_int() > 935 or not cct.get_work_time()):
        top_now = rl.get_market_price_sina_dd_realTime(dm, vol, vtype)
    else:
        if 'code' in dm.columns:
            dm = dm.set_index('code')
        top_now = dm
        top_now['couts'] = 0
        top_now['dff'] = 0
        top_now['prev_p'] = 0
        top_now['kind'] = 0
        
    print(":%s b1>:%s it:%s" % (initTdxdata, len(top_now), round(time.time() - time_s, 1)), end=' ')
    # log.info(f'停牌个股: {stop_code}')
    if top_now is None or len(top_now) == 0:
        log.error("top_all is None :%s" % (top_now))
    if isinstance(top_now,pd.DataFrame) and not 'ratio' in top_now.columns:
        top_now['ratio'] = 0.0
    # top_now = top_now.query('open != 0 and close != 0')
    # return cct.reduce_memory_usage(top_now)
    return top_now


def get_tdx_day_to_df(code):
    """
        »ñÈ¡¸ö¹ÉÀúÊ·½»Ò×¼ÇÂ¼
    Parameters
    ------
      code:string
                  ¹ÉÆ±´úÂë e.g. 600848
      start:string
                  ¿ªÊ¼ÈÕÆÚ format£ºYYYY-MM-DD Îª¿ÕÊ±È¡µ½APIËùÌá¹©µÄ×îÔçÈÕÆÚÊý¾Ý
      end:string
                  ½áÊøÈÕÆÚ format£ºYYYY-MM-DD Îª¿ÕÊ±È¡µ½×î½üÒ»¸ö½»Ò×ÈÕÊý¾Ý
      ktype£ºstring
                  Êý¾ÝÀàÐÍ£¬D=ÈÕkÏß W=ÖÜ M=ÔÂ 5=5·ÖÖÓ 15=15·ÖÖÓ 30=30·ÖÖÓ 60=60·ÖÖÓ£¬Ä¬ÈÏÎªD
      retry_count : int, Ä¬ÈÏ 3
                 ÈçÓöÍøÂçµÈÎÊÌâÖØ¸´Ö´ÐÐµÄ´ÎÊý
      pause : int, Ä¬ÈÏ 0
                ÖØ¸´ÇëÇóÊý¾Ý¹ý³ÌÖÐÔÝÍ£µÄÃëÊý£¬·ÀÖ¹ÇëÇó¼ä¸ôÊ±¼äÌ«¶Ì³öÏÖµÄÎÊÌâ
    return
    -------
      DataFrame
          ÊôÐÔ:ÈÕÆÚ £¬¿ªÅÌ¼Û£¬ ×î¸ß¼Û£¬ ÊÕÅÌ¼Û£¬ ×îµÍ¼Û£¬ ³É½»Á¿£¬ ¼Û¸ñ±ä¶¯ £¬ÕÇµø·ù£¬5ÈÕ¾ù¼Û£¬10ÈÕ¾ù¼Û£¬20ÈÕ¾ù¼Û£¬5ÈÕ¾ùÁ¿£¬10ÈÕ¾ùÁ¿£¬20ÈÕ¾ùÁ¿£¬»»ÊÖÂÊ
    """
    # time_s=time.time()
    # print code
    code_u = cct.code_to_symbol(code)
    day_path = day_dir % 'sh' if code[:1] in [
        '5', '6', '9'] else day_dir % 'sz'
    p_day_dir = day_path.replace('/', path_sep).replace('\\', path_sep)
    # p_exp_dir = exp_dir.replace('/', path_sep).replace('\\', path_sep)
    # print p_day_dir,p_exp_dir
    file_path = p_day_dir + code_u + '.day'
    if not os.path.exists(file_path):
        ds = Series(
            {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
             'vol': 0})
        return ds

    ofile = open(file_path, 'rb')
    buf = ofile.read().decode(errors="ignore")
    ofile.close()
    num = len(buf)
    no = int(num / 32)
    b = 0
    e = 32
    dt_list = []
    for i in range(no):
        a = unpack('IIIIIfII', buf[b:e])
        # dt=datetime.date(int(str(a[0])[:4]),int(str(a[0])[4:6]),int(str(a[0])[6:8]))
        if len(a) < 7:
            continue
        tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
        # tdate=dt.strftime('%Y-%m-%d')
        topen = float(a[1] / 100.0)
        thigh = float(a[2] / 100.0)
        tlow = float(a[3] / 100.0)
        tclose = float(a[4] / 100.0)
        amount = float(a[5] / 10.0)
        tvol = int(a[6])  # int
        tpre = int(a[7])  # back
        dt_list.append(
            {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose, 'amount': amount,
             'vol': tvol, 'pre': tpre})
        b = b + 32
        e = e + 32
    df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
    df = df[~df.date.duplicated()]

    df = df.set_index('date')
    # print "time:",(time.time()-time_s)*1000
    return df


def get_duration_Index_date(code='999999', dt=None, ptype='low', dl=None, power=False,detect_calc_support=False):
    """[summary]

    [description]

    Keyword Arguments:
        code {str} -- [description] (default: {'999999'})
        dt {[type]} -- [description] (default: {None})
        ptype {str} -- [description] (default: {'low'})
        dl {[type]} -- [description] (default: {None})
        power {bool} -- [description] (default: {False})

    Returns:
        [type] -- [description]
    """
    if dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt) + changedays
            # df = get_tdx_day_to_df(code).sort_index(ascending=False)
            df = get_tdx_append_now_df_api(
                code, power=power,detect_calc_support=detect_calc_support).sort_index(ascending=False)
            dt = get_duration_price_date(code, dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("code:%s LastDF:%s,%s" % (code,dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            # df = get_tdx_day_to_df(code).sort_index(ascending=False)
            df = get_tdx_append_now_df_api(
                code, start=dt, power=power,detect_calc_support=detect_calc_support).sort_index(ascending=False)
            # dl = len(get_tdx_Exp_day_to_df(code, start=dt)) + changedays
            dl = len(df) + changedays

            dt = df[df.index <= dt].index.values[changedays] if len(df[df.index <= dt]) > 0 else df.index.values[-1]
            log.info("LastDF:%s,%s" % (dt, dl))
        return dt, dl
    if dl is not None:
        # dl = int(dl)
        df = get_tdx_append_now_df_api(
            code, start=dt, dl=dl, power=power,detect_calc_support=detect_calc_support).sort_index(ascending=False)
        # print df
        # dl = len(get_tdx_Exp_day_to_df(code, start=dt)) + changedays
        # print df[:dl].index,dl
        dt = df[:dl].index[-1]
        log.info("dl to dt:%s" % (dt))
        return dt
    return None, None


def get_duration_date(code, ptype='low', dt=None, df=None, dl=None):
    if df is None:
        df = get_tdx_day_to_df(code).sort_index(ascending=False)
        # log.debug("code:%s" % (df[:1].index))
    else:
        df = df.sort_index(ascending=False)
    if dt != None:
        if len(str(dt)) == 10:
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        elif len(str(dt)) == 8:
            dt = cct.day8_to_day10(dt)
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        else:
            if len(df) > int(dt):
                dz = df[:int(dt)]
            else:
                dz = df
    elif dl is not None:
        if len(df) > int(dl):
            dz = df[:int(dl)]
        else:
            dz = df
        return dz.index[-1]
    else:
        dz = df
    if ptype == 'high':
        lowp = dz.high.max()
        lowdate = dz[dz.high == lowp].index.values[-1]
        log.debug("high:%s" % lowdate)
    elif ptype == 'close':
        lowp = dz.close.min()
        lowdate = dz[dz.close == lowp].index.values[-1]
        log.debug("high:%s" % lowdate)
    else:
        lowp = dz.low.min()
        lowdate = dz[dz.close == lowp].index.values[-1]
        log.debug("low:%s" % lowdate)
    # if ptype == 'high':
    #     lowp = dz.close.max()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("high:%s"%lowdate)
    # else:
    #     lowp = dz.close.min()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("low:%s"%lowdate)
    log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
    return lowdate


def get_duration_price_date(code=None, ptype='low', dt=None, df=None, dl=None, end=None, vtype=None, filter=True,
                            power=False,resample='d',detect_calc_support=False):
    # if code == "600760":
        # log.setLevel(LoggerFactory.DEBUG)
    # else:u
        # log.setLevel(LoggerFactory.ERROR)
    # if ptype == 'low' and code == '999999':
    #     log.setLevel(LoggerFactory.DEBUG)
    # else:
    #     log.setLevel(LoggerFactory.ERROR)
    if df is None and code is not None:
        # df = get_tdx_day_to_df(code).sort_index(ascending=False)
        if power:
            df = get_tdx_append_now_df_api(
                code, start=dt, end=end, dl=dl,detect_calc_support=detect_calc_support).sort_index(ascending=False)
        else:
            df = get_tdx_Exp_day_to_df(
                code, start=dt, end=end, dl=dl,detect_calc_support=detect_calc_support).sort_index(ascending=False)
    else:
        df = df.sort_index(ascending=False)
        # log.debug("code:%s" % (df[:1].index))
    # if resample.lower() != 'd':
    #     df = df
    if dt != None:
        if len(str(dt)) == 10:
            dz = df[df.index >= dt]
            if dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
        elif len(str(dt)) == 8:
            dt = cct.day8_to_day10(dt)
            dz = df[df.index >= dt]
            if len(dz) > 0 and dl is not None:
                if len(dz) < int(dl) - changedays:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                else:
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
            else:
                # log.error("code:%s dt:%s no data"%(code,dt))
                if not filter:
                    index_d = df.index[0]

        else:
            if len(df) > int(dt):
                dz = df[:int(dt)]
            else:
                dz = df
    elif dl is not None:
        if len(df) > int(dl) + 1:
            dz = df[:int(dl)]
        else:
            dz = df
        if not filter:
            if len(dz) > 0:
                index_d = dz[:1].index.values[0]
            else:
                index_d = cct.get_today()
                lowdate = cct.get_today()
                log.error("code:%s dz:%s" % (code, dz))
                if filter:
                    return lowdate
                elif not power:
                    return lowdate, index_d
                else:
                    return lowdate, index_d, pd.DataFrame()
    else:
        dz = df
    if len(dz) > 0:
        if ptype == 'high':
            lowp = dz.high.max()
            lowdate = dz[dz.high == lowp].index.values[-1]
            log.debug("high:%s" % lowdate)
        elif ptype == 'close':
            lowp = dz.close.min()
            lowdate = dz[dz.close == lowp].index.values[-1]
            log.debug("high:%s" % lowdate)
        else:
            lowp = dz.low.min()
            lowdate = dz[dz.low == lowp].index.values[-1]
            log.debug("low:%s" % lowdate)
        log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
    else:
        lowdate = df.index[0]
    # if ptype == 'high':
    #     lowp = dz.close.max()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("high:%s"%lowdate)
    # else:
    #     lowp = dz.close.min()
    #     lowdate = dz[dz.close == lowp].index.values[0]
    #     log.debug("low:%s"%lowdate)
    if filter:
        return lowdate
    elif not power:
        return lowdate, index_d
    else:
        return lowdate, index_d, df


def compute_power_tdx_df_slow(tdx_df,dd):
    if len(tdx_df) >= 5:

        # idxh = tdx_df.high.argmax()
        idxl = tdx_df.low.idxmin()
        idxh = tdx_df.low.idxmax()
        idxl_date=tdx_df.index.tolist().index(idxl)
        idxh_date=tdx_df.index.tolist().index(idxh)
        fibh = len(tdx_df[idxl_date:].query('high > high.shift(1)*0.998 or close > close.shift(1)'))
        dd['fibl'] = fibh
        # dd['ldate'] = idx
        # dd['boll'] = dd.upperL[0]
        dd['boll'] = dd.upperT[0]
        dd['ra'] = dd.upperL[0]
        # dd['ra'] = dd.upperT[0]
        dd['ma'] = 1
        dd['oph'] = 1
        dd['rah'] = 1
    else:
        dd['op'] = -1
        dd['ra'] = -1
        dd['fib'] = -1
        dd['fibl'] = -1
        dd['ldate'] = -1
        dd['boll'] = -1

        dd['ma'] = -1
        dd['oph'] = -1
        dd['rah'] = -1
        # log.error("tdx_df is no 9:%s"%(dd.code[0]))
    return dd

def compute_power_tdx_df(tdx_df, dd):
    if len(tdx_df) >= 5:
        # 找 low 的最小值位置
        idx_low = tdx_df['low'].idxmin()
        pos_low = tdx_df.index.get_loc(idx_low)

        # 从 idx_low 开始的子 DataFrame
        sub_df = tdx_df.iloc[pos_low:]

        # fibh 计算
        fibh = ((sub_df['high'] > sub_df['high'].shift(1) * 0.998) | (sub_df['close'] > sub_df['close'].shift(1))).sum()

        # 赋值给整个 dd
        dd['fibl'] = fibh
        dd['boll'] = dd['upperT'].iloc[0]  # 用第一行 upperT 作为标量
        dd['ra'] = dd['upperL'].iloc[0]    # 用第一行 upperL 作为标量
        dd['ma'] = 1
        dd['oph'] = 1
        dd['rah'] = 1
    else:
        for col in ['op', 'ra', 'fib', 'fibl', 'ldate', 'boll', 'ma', 'oph', 'rah']:
            dd[col] = -1
    return dd




def dataframe_mode_round(df):
    roundlist = [1, 0]
    df_mode = []
    for i in roundlist:
        df_mode = df.apply(lambda x: round(x, i)).mode()
        if len(df_mode) > 0:
            break
    return df_mode


def compute_condition_up_sample(df):
    condition_up = df['low'] > df['high'].shift()        #向上跳空缺口
    condition_down = df['high'] < df['low'].shift()      #向下跳空缺口



    df.loc[condition_up,'hop_up'] = -1
    df.loc[condition_down,'hop_down'] =1

    hop_record=[]
    #向上跳空,看是否有回落(之后的最低价有没有低于缺口前价格)
    #向下跳空,看是否有回升(之后的最高价有没有高于缺口前价格)
    for i in range(len(df)):
        #如果向上跳空
        if list(df['hop_up'].at[i].values()) == -1:     #at loc index 
            hop_date = df['date'].at[i] #跳空时间 
            ex_hop_price = df['high'].at[i -1]  #前一根K线最高价   
            post_hop_price = df['low'].at[i]  #跳空后的价格
            fill_data = ''
            #看滞后有没有回补向上的跳空
            for j in range(i,len(df)):
                if df['low'].at[j] <= ex_hop_price:
                    fill_data = df['date'].at[i]
                    break
            hop_record.append({'hop':'up',
                                'jop_date':hop_date,
                                'ex_hop_price':ex_hop_price,
                                'post_hop_price':post_hop_price,
                                'fill_data':fill_data })
        #如果有向下跳空
        elif df['hop_down'].at[i] == 1:
            hop_date = df['date'].at[i] #跳空时间
            ex_hop_price = df['low'].at[i -1] #前一根K线最低价   
            post_hop_price = df['high'].at[i]  #跳空后的价格
            fill_data = ''
            #看之后有没有回补向下的跳空
            for j in range(i,len(df)):
                if df['high'].at[j] >= ex_hop_price:
                    fill_data = df['date'].at[j]
                    break

            hop_record.append({'hop':'down',
                                'jop_date':hop_date,
                                'ex_hop_price':ex_hop_price,
                                'post_hop_price':post_hop_price,
                                'fill_data':fill_data })

    hop_df = pd.DataFrame(hop_record)
    return hop_df

def compute_condition_up(df):

    condition_up = df[df['low'] > df['high'].shift(1)]       #向上跳空缺口
    condition_down = df[df['high'] < df['low'].shift(1)]
          #向下跳空缺口
    # df = df.assign(hop=np.nan)

    # df.loc[condition_up,'hop_up'] = -1
    # df.loc[condition_down,'hop_down'] =1

    hop_record= []

    # hop_record=[{'hop':np.nan,
    #             'jop_date':np.nan,
    #             'ex_hop_price':np.nan,
    #             'post_hop_price':np.nan,
    #             'fill_data':np.nan,
    #             'fill_day':np.nan }]
    # hop_record_up=[]
    # hop_record_down=[]
    #向上跳空,看是否有回落(之后的最低价有没有低于缺口前价格)
    #向下跳空,看是否有回升(之后的最高价有没有高于缺口前价格)
    for i in condition_up.index:
        #如果向上跳空

        hop_date = i #跳空时间 
        # lastday = cct.day_last_days(i,-1)
        lastday = df.index[df.index < i][-1]

        ex_hop_price = df['high'].at[lastday]  #前一根K线最高价   
        post_hop_price = df['low'].at[i]  #跳空后的价格

        fill_data = ''          #回补时间
        fill_day = np.nan           #回补天数
        #看滞后有没有回补向上的跳空
        duration = df.index[df.index > i] #跳空后的数据日

        for j in duration:
            log.debug(f"j:{j}: low :{df['low'].at[j]}")
            if df['low'].at[j] <= ex_hop_price:
                fill_data = j
                fill_day = len(df.index[(df.index > i) & (df.index <= j)])
                break
        hop_record.append({'hop':'up',
                            'jop_date':hop_date,
                            'ex_hop_price':ex_hop_price,
                            'post_hop_price':post_hop_price,
                            'fill_data':fill_data,
                            'fill_day':fill_day })

        #如果有向下跳空
    for i in condition_down.index:
        #如果向下跳空

        hop_date = i #跳空时间 
        # lastday = cct.day_last_days(i,-1)
        lastday = df.index[df.index < i][-1]
        ex_hop_price = df['low'].at[lastday]  #前一根K线最低价   
        post_hop_price = df['high'].at[i]  #跳空后的价格

        fill_data = ''          #回补时间
        fill_day = np.nan           #回补天数
        #看滞后有没有回补向上的跳空
        duration = df.index[df.index > i] #跳空后的数据日
        
        for j in duration:
            if df['low'].at[j] >= ex_hop_price:
                fill_data = j
                fill_day = len(df.index[(df.index > i) & (df.index <= j)])
                break
        hop_record.append({'hop':'down',
                            'jop_date':hop_date,
                            'ex_hop_price':ex_hop_price,
                            'post_hop_price':post_hop_price,
                            'fill_data':fill_data,
                            'fill_day':fill_day })
    hop_df = pd.DataFrame(hop_record)
    # hop_df[hop_df.fill_day <> '']         #已经回补
    # hop_df.fill_day.isnull()  #没有回补
    return hop_df


def compute_condition_up_add_up(df,condition_up):

    co_up = condition_up.query('hop == "up" and @pd.isnull(fill_day)')
    if len(co_up) == 1 :
        idx_date = co_up.jop_date.values[0]
        if idx_date  in df.index:
            idx_close = df.loc[idx_date,'close']
        else:
            idx_close = df.close[0]
        # df2 = df[df.index >= idx_date]
        # condition_up2 = df2.query(f'high > high.shift(1) and close > close.shift(1)*0.99 and close >= {idx_close}')  #1跳空新高收高
        condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999 and high > upper')  #2跳空新高收高
        condition_up3 = df.query('(close - close.shift(1))/close.shift(1)*100 > 4 and close >= high*0.99')
        condition_up2 = pd.concat([condition_up2,condition_up3],axis=0)
    elif len(co_up) > 1:
        # idx_date = condition_up.index[0]
        # idx_close = condition_up.close[0]
        idx_date = co_up.jop_date.values[0]
        if idx_date in df.index:
            idx_close = df.loc[idx_date,'close']
        else:
            idx_close = df.close[0]
        # df2 = df[df.index >= idx_date]
        # condition_up2 = df2.query(f'high > high.shift(1) and close > close.shift(1)*0.99 and close >= {idx_close}')  #1跳空新高收高
        # condition_up2 = df2.query(f'low > low.shift(1) and high > high.shift(1) and close > close.shift(1) and close > {idx_close}')  #2跳空新高收高
        # condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999')  #2跳空新高收高
        condition_up2 = df.query(f'low > low.shift(1) and high > high.shift(1) and close > high.shift(1)*0.999 and high > upper')  #2跳空新高收高
        condition_up3 = df.query('(close - close.shift(1))/close.shift(1)*100 > 6 and close >= high*0.99')
        
        condition_up2 = pd.concat([condition_up2,condition_up3],axis=0)
    else:
        condition_up2 = pd.DataFrame()
        # condition_up3 = pd.DataFrame()

    return condition_up2

def compute_perd_df(dd, lastdays=3, resample='d',normalized=False):
    #fast to def ,src to slow
    last_TopR_days = cct.compute_lastdays if resample == 'd' else cct.compute_lastdays
    np.seterr(divide='ignore', invalid='ignore')

    # 向量化处理看涨信号
    dd = track_bullish_signals_startpos(dd)

    df = dd.copy()
    df['close_shift1'] = df['close'].shift(1)
    df['high_shift1'] = df['high'].shift(1)
    df['low_shift1'] = df['low'].shift(1)
    df['open_shift1'] = df['open'].shift(1)
    df['vol_shift1'] = df['vol'].shift(1)

    # rolling max/min
    df['max5'] = df['close_shift1'].rolling(5).max()
    df['max10'] = df['close_shift1'].rolling(10).max()
    df['hmax'] = df['close_shift1'].rolling(30).max()
    df['high4'] = df['close_shift1'].rolling(4).max()
    df['low4'] = df['low_shift1'].rolling(4).min()
    df['lastdu4'] = (df['high4'].iloc[0] - (df['low4'].iloc[0]+0.1)) / (df['low4'].iloc[0]+0.1) * 100

    df['lastupper'] = ((df['close'] > df['upper']) & (df['upper'] > 0)).sum()

    df = df[-(last_TopR_days+1):]

    # 计算涨跌幅
    df['perlastp'] = cct.func_compute_percd2021_vectorized(df).round(1)
    df['perd'] = ((df['close'] - df['close_shift1']) / df['close_shift1'] * 100).round(1)

    # 向量化 red_cout
    if resample == 'd':
        red_mask = (
            (df['close'] > df['ma5d']) |
            (df['high'] > df['high_shift1']) |
            ((df['low'] > df['low_shift1']) & (df['close'] > df['close_shift1']*1.01)) |
            ((df['close'] > df['upper']) & (df['close'] > df['open']*1.01)) |
            ((df['low'] >= df['open']*0.992) & (df['close'] >= df['close_shift1']*1.005))
        )
    else:
        red_mask = (
            (df['close'] > df['ma5d']) |
            ((df['high'] > df['high_shift1']) & ((df['low'] > df['low_shift1']) & (df['close'] > df['close_shift1']*1.03))) |
            ((df['close'] > df['upper']) & (df['close'] > df['open']*1.01)) |
            ((df['low'] >= df['open']*0.992) & (df['close'] >= df['close_shift1']*1.03))
        )

    red_cout = df[red_mask]
    
    df2 = df[df.index >= (df[df['high'] > df['upper']].index[0] if len(df[df['high'] > df['upper']]) > 0 else df['high'].idxmax())]

    green_mask = (
        ((df2['low'] < df2['low_shift1']) & (df2['high'] < df2['high_shift1'])) |
        (df2['close'] < df2['open'])
    )
    green_cout = df2[green_mask]

    df['lastdu'] = ((df['high'].rolling(4).max() - df['low'].rolling(4).min()) / df['close'].rolling(4).mean() * 100).round(1)
    dfupper = df[-ct.bollupperT:]
    upperT = dfupper['high'][(dfupper['high'] > 0) & (dfupper['high'] > dfupper['upper'])]
    upperL = dfupper['low'][(dfupper['low'] > dfupper['ma5d']) & (dfupper['ma5d'] > 0)]
    upperLIS, posLIS = LIS_TDX(upperT) if len(upperT) > 0 else ([], [])
    dd['upperT'] = len(posLIS)
    dd['upperL'] = len(upperL)

    dd['red'] = len(red_cout)
    dd['gren'] = len(green_cout)

    top15 = dd[-ct.ddtop0:].query('(low >= open*0.992 or open > open.shift(1)) and close > open and ((high > upper or high > high.shift(1)) and close > close.shift(1)*1.04)')
    top0 = dd[-ct.ddtop0:].query('low == high and low != 0')
    dd['top0'] = len(top0)
    dd['top15'] = len(top15)

    # 计算跳空缺口回补
    hop_df = compute_condition_up(dd[-15:])
    condition_up = hop_df[(hop_df.fill_day.isnull()) & (hop_df.hop == 'up')] if len(hop_df) > 0 else pd.DataFrame()
    condition_down = hop_df[(hop_df.fill_day.isnull()) & (hop_df.hop == 'down')] if len(hop_df) > 0 else pd.DataFrame()
    c_up, c_down = len(condition_up), len(condition_down)
    if c_up > 0:
        dd['topR'] = c_up
        dd['topD'] = c_down
    else:
        dd['topR'] = -c_down if c_down > 0 else 0
        dd['topD'] = c_down

    # 计算 ma20d_upper
    df_ma20d = dd[-20:]
    if resample == 'd':
        ma20d_upper = len(df_ma20d.query('low > ma20d'))
    elif resample in ['3d', 'w']:
        ma20d_upper = len(df_ma20d.query('low > ma10d'))
    else:
        ma20d_upper = len(df_ma20d.query('low > ma5d'))
    dd['ral'] = ma20d_upper

    #归一化涨幅
    if normalized:
        if resample == 'd':
            df['perd'] = df['perd'].apply(lambda x: round(x, 1) if x < 9.85 else 10.0)


    dd['perd'] = df['perd'][~df.index.duplicated()]
    dd.fillna(ct.FILLNA, inplace=True)
    dd['perlastp'] = df['perlastp']

    # df_orig = compute_power_tdx_df_slow(df, dd)
    dd = compute_power_tdx_df(df, dd)
    # result = compare_perd_df_results(df_orig, dd, columns=None)
    # # 查看匹配统计
    # # print(result['match_stats'])
    # print(result['mismatch_details'])

    return dd

def resample_dataframe_recut(temp,resample='d',increasing=True,check=False):

    ascending=None

    if not temp.index.is_monotonic_increasing:
        # log.info(f'increasing is False')
        ascending=False
        temp = temp.sort_index(ascending=True)

    # else:
    #     ascending=False
        
    if resample == 'm':
        temp = temp[-30:]
    elif resample == 'w':
        temp = temp[-40:]
    elif resample == '3d':
        temp = temp[-60:]
    else:
        temp = temp[-90:]

    if ascending is not None:
        temp = temp.sort_index(ascending=ascending)   
    return temp

def compute_upper_cross_slow(dd,ma1='upper',ma2='ma5d',ratio=0.02,resample='d'): 
    if ma1 in dd.columns:
        df = dd[(dd[ma1] != 0)]
        df = df[-ct.upper_cross_days:]
        # temp = df[ (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio)) ]
        # temp = df[(df.low > df.upper)]
        temp = df[(df.high >= df.upper)]
        # if len(temp) >0 and  temp.index[-1] == df.index[-1]:
        #     dd['topU'] = len(temp)
        # else:
        #     dd['topU'] = 0
        dd['topU'] = len(temp) 
        #high >= df.upper
        dd['eneU'] = len(df[(df.close >= df.ene)])
    else:
        dd['topU'] = 0 
        #high >= df.upper
        dd['eneU'] = 0
    #close >= df.ene
    
    return dd

def compute_upper_cross(dd, ma1='upper', ma2='ma5d', ratio=0.02, resample='d'):
    """
    向量化计算 upper 与 ma5d 交叉相关指标。
    dd: DataFrame，必须包含 'close', 'high', 'ene', ma1 列
    ma1: 上轨列名，默认 'upper'
    ma2: 均线列名，默认 'ma5d'
    ratio: 比例阈值（预留）
    resample: 重采样类型
    """
    # 初始化列
    dd['topU'] = 0
    dd['eneU'] = 0

    if ma1 not in dd.columns:
        return dd

    # 只取非零 upper 行
    mask_upper_nonzero = dd[ma1] != 0
    df = dd[mask_upper_nonzero]

    if len(df) == 0:
        return dd

    # 取最后 N 天
    df_tail = df.tail(ct.upper_cross_days)

    # high >= upper
    dd['topU'] = (df_tail['high'] >= df_tail['upper']).sum()

    # close >= ene
    dd['eneU'] = (df_tail['close'] >= df_tail['ene']).sum()

    return dd


def compute_ma_cross(dd, ma1='ma5d', ma2='ma10d', ratio=0.02, resample='d'):
    """
    向量化计算 MA 均线交叉相关指标。
    dd: DataFrame，必须包含 'close', 'low', ma1, ma2 列
    ma1, ma2: 均线列名
    ratio: 比例阈值，保留以备后续逻辑扩展
    resample: 重采样类型
    """
    # 重采样
    temp = resample_dataframe_recut(dd, resample=resample)
    
    # 初始化列
    dd['op'] = 0.0
    dd['ldate'] = pd.NaT
    dd['fib'] = -1
    
    if len(temp) == 0:
        # fallback: ma1 > ma2
        temp = dd[dd[ma1] > dd[ma2]]
        if len(temp) == len(dd) and len(dd) > 0:
            base_price = temp['close'].iloc[0]
            dd['op'] = (dd['close'] / base_price * 100 - 100).round(1)
            dd['ldate'] = temp.index[0]
        return dd
    
    # 找 low > 0 的 idx_min 和 close 的 idx_max
    temp_low_positive = temp['low'] > 0
    if temp_low_positive.any():
        idx_min = temp[temp_low_positive]['low'].idxmin()
    else:
        idx_min = temp.index[-1]

    base_price = temp.at[idx_min, 'close'] if idx_min in temp.index else temp['close'].iloc[-1]

    # 向量化计算 op 列
    dd['op'] = ((dd['close'] / base_price) * 100 - 100).round(1)
    dd['ldate'] = temp.index[0]

    return dd

def compute_cross_indicators(df, ma_cross_list=None, upper_cross_list=None, ratio=0.02, resample='d'):
    """
    向量化计算 MA 交叉和 Upper 交叉指标。
    
    df: pd.DataFrame, 必须包含 'close', 'high', 'low', 'ene' 列，以及相关均线列和 upper 列
    ma_cross_list: list of tuple, 每个 tuple ('ma短期列', 'ma长期列', '结果列名')
    upper_cross_list: list of tuple, 每个 tuple ('upper列', 'ma列', 'topU列', 'eneU列')
    ratio: MA交叉阈值
    resample: 重采样类型（可选）
    """
    # 初始化结果列，防止不存在时报错
    if ma_cross_list:
        for ma1, ma2, col_name in ma_cross_list:
            df[col_name] = 0
            df[f'{col_name}_ldate'] = pd.NaT

    if upper_cross_list:
        for upper_col, ma_col, topU_col, eneU_col in upper_cross_list:
            df[topU_col] = 0
            df[eneU_col] = 0

    # MA 交叉向量化计算
    if ma_cross_list:
        for ma1, ma2, col_name in ma_cross_list:
            if ma1 in df.columns and ma2 in df.columns:
                # 计算条件
                mask_cross = (df[ma1] > df[ma2] * (1 - ratio)) & (df[ma1] < df[ma2] * (1 + ratio))
                df_cross = df[mask_cross].copy().dropna()
                # if not df_cross.empty:
                #     idx_max = df_cross['close'][:-1].idxmax()
                #     idx_min = df_cross['low'][:-1].idxmin()
                #     # 最后一行收盘价相对低点百分比
                #     if idx_min in df_cross.index:
                #         df[col_name].iloc[-1] = round(df['close'].iloc[-1] / df_cross['close'].loc[idx_min] * 100 - 100, 1)
                #     else:
                #         df[col_name].iloc[-1] = round(df['close'].iloc[-1] / df_cross['close'].iloc[-1] * 100 - 100, 1)
                #     df[f'{col_name}_ldate'].iloc[-1] = df_cross.index[0]
                if not df_cross.empty:
                    close_series = df_cross['close'][:-1].dropna()
                    low_series = df_cross['low'][:-1].dropna()

                    if not close_series.empty:
                        idx_max = close_series.idxmax()
                    else:
                        idx_max = df_cross.index[-1]

                    if not low_series.empty:
                        idx_min = low_series.idxmin()
                    else:
                        idx_min = df_cross.index[-1]

                    # 最后一行收盘价相对低点百分比
                    base_idx = idx_min if idx_min in df_cross.index else df_cross.index[-1]
                    df.at[df.index[-1], col_name] = round(df['close'].iloc[-1] / df_cross['close'].loc[base_idx] * 100 - 100, 1)

                    # 最早日期
                    df.at[df.index[-1], f'{col_name}_ldate'] = df_cross.index[0]
                else:
                    # df_cross 为空时赋默认值
                    df.at[df.index[-1], col_name] = 0
                    df.at[df.index[-1], f'{col_name}_ldate'] = None

    # Upper 交叉向量化计算
    if upper_cross_list:
        for upper_col, ma_col, topU_col, eneU_col in upper_cross_list:
            if upper_col in df.columns:
                df_nonzero = df[df[upper_col] != 0].copy()
                if not df_nonzero.empty:
                    df_tail = df_nonzero.tail(ct.upper_cross_days)
                    df[topU_col].iloc[-1] = (df_tail['high'] >= df_tail['upper']).sum()
                    df[eneU_col].iloc[-1] = (df_tail['close'] >= df_tail['ene']).sum()

    return df


def compute_ma_cross_slow(dd,ma1='ma5d',ma2='ma10d',ratio=0.02,resample='d'):
    #low

    temp = dd
    # temp = df[ (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio)) ]
    # temp = df[ ((df.close > df.ene) & (df.close < df.upper)) & (df[ma1] > df[ma2] * (1-ratio))  & (df[ma1] < df[ma2] * (1+ratio))]
    # temp default: temp.sort_index(ascending=False)

    temp=resample_dataframe_recut(temp,resample=resample)

    if len(temp) > 0:
        temp_close = temp.low
        if len(temp_close[temp_close >0]) >0:
            idx_max = temp.close[:-1].idxmax()
            idx_min = temp_close[:-1].idxmin()
        else:
            idx_min = -1
            idx_max = -1

        if idx_min != -1:
            idx = round((dd.close.iloc[-1]/temp.close[temp.index == idx_min])*100-100,1)

        else:
            idx = round((dd.close.iloc[-1]/temp.close[-1])*100-100,1)
        dd['op'] = idx
        dd['ldate'] = temp.index[0]
    else:

        temp = dd[ dd[ma1] > dd[ma2]]
        if len(temp) == len(dd) and len(dd) > 0:
            idx = round((dd.close[-1]/temp.close[0])*100-100,1)
            dd['op'] = idx
            dd['ldate'] = temp.index[0]
        else:
            idx = 0
            dd['op'] = idx
            dd['fib'] = -1
            dd['ldate'] = -1
    return dd

# def safe_get(df, col, idx=-1, default=0):
#     if col in df.columns:
#         return df[col].iloc[idx]
#     return default

def safe_get(df, col, idx, default=0):
    """安全获取 df[col] 的倒数 idx 行，如果不存在返回 default"""
    if col in df.columns and len(df) >= abs(idx):
        return df[col].iloc[idx]
    return default

def safe_SMA(df, column, period, name):
    try:
        df[name] = talib.SMA(df[column].astype(float), timeperiod=period)
        return True
    except Exception:
        tb = traceback.format_exc()

        log.error(
            f"TA-Lib SMA 计算失败: column={column}, period={period}, name={name}\n"
            f"Exception:\n{tb}\n"
        )

        # f"=== DF INFO START ===\n"
        # f"{df.describe(include='all')}\n\n"
        # f"Columns: {list(df.columns)}\n"
        # f"Head:\n{df.head(5)}\n"
        # f"Tail:\n{df.tail(5)}\n"
        # f"DF isnull sum:\n{df.isnull().sum()}\n"
        # f"=== DF INFO END ==="

        # 失败时填充 NaN，不中断主流程
        df[name] = 0.1
        return False


def compare_shifted_df(df, df_aug, lastdays=6):
    """
    比对 df 与 df_aug 中 shift 生成的历史列是否一致
    自动匹配 df_aug 的列名规则
    """
    consistent = True
    n_rows = len(df)

    # 1. 前 6 天特殊列
    special_cols_map = {'lasto': 'open', 'lastl': 'low', 'truer': 'truer'}
    for da in range(1, min(6, lastdays)+1):
        for aug_prefix, orig_col in special_cols_map.items():
            aug_col = f'{aug_prefix}{da}d'
            expected = df[orig_col].shift(da-1) if orig_col in df.columns else pd.Series([np.nan]*n_rows)
            actual = df_aug.get(aug_col)
            if actual is None:
                print(f"列 {aug_col} 不存在")
                consistent = False
                continue
            if not expected.equals(actual):
                print(f"列 {aug_col} 数据不一致!")
                inconsistent_idx = np.where(~expected.eq(actual).fillna(True))[0]
                print("不一致索引示例:", inconsistent_idx[:10])
                consistent = False

    # 2. 通用列
    general_cols_map = {
        'lasth': 'high',
        'lastp': 'close',
        'lastv': 'vol',
        'per': 'perd',
        'upper': 'upper',
        'ma5': 'ma5d',
        'ma20': 'ma20d',
        'ma60': 'ma60d',
        'perc': 'perlastp',
    }
        # 'high4': 'high4',
        # 'hmax': 'hmax'

    for da in range(1, lastdays+1):
        for aug_prefix, orig_col in general_cols_map.items():
            aug_col = f'{aug_prefix}{da}d' if aug_prefix not in ['upper'] else f'{aug_prefix}{da}'
            expected = df[orig_col].shift(da-1) if orig_col in df.columns else pd.Series([np.nan]*n_rows)
            actual = df_aug.get(aug_col)
            if actual is None:
                print(f"列 {aug_col} 不存在")
                consistent = False
                continue
            if not expected.equals(actual):
                print(f"列 {aug_col} 数据不一致!")
                inconsistent_idx = np.where(~expected.eq(actual).fillna(True))[0]
                print("不一致索引示例:", inconsistent_idx[:10])
                consistent = False

    if consistent:
        print("所有历史列一致！")
    return consistent


def compare_first_rows(df, df_aug, lastdays=6, n=10):
    """
    对比 df 与 df_aug 的前 n 行是否符合 lastdays 历史列规则
    df: 原始 DataFrame
    df_aug: 扩展后的 DataFrame
    lastdays: 最大历史天数
    n: 比对前几行
    """
    consistent = True
    cols_special = ['open', 'low', 'truer']
    cols_general = ['high', 'close', 'vol', 'perd', 'upper', 'ma5d', 'ma20d', 'ma60d', 'perlastp', 'high4', 'hmax']

    for da in range(1, lastdays+1):
        for col in cols_special:
            if da <= 6 and col in df.columns:
                aug_col = f'last{col[0]}{da}d' if col != 'truer' else f'truer{da}d'
                expected = df[col].iloc[-da]
                actual = df_aug[aug_col].iloc[:n]
                if not all(actual == expected):
                    print(f"列 {aug_col} 前 {n} 行不一致")
                    consistent = False

        for col in cols_general:
            if col not in df.columns:
                continue
            prefix_map = {
                'high':'lasth','close':'lastp','vol':'lastv','perd':'per',
                'upper':'upper','ma5d':'ma5','ma20d':'ma20','ma60d':'ma60',
                'perlastp':'perc','high4':'high4','hmax':'hmax'
            }
            aug_col = f"{prefix_map[col]}{da}d" if prefix_map[col] not in ['upper'] else f"{prefix_map[col]}{da}"
            expected = df[col].iloc[-da]
            actual = df_aug[aug_col].iloc[:n]
            if not all(actual == expected):
                print(f"列 {aug_col} 前 {n} 行不一致")
                consistent = False

    if consistent:
        print(f"前 {n} 行所有历史列一致")
    return consistent

def build_aug_from_last_row(df, lastdays=6):
    """
    只用 df 的最后一行生成 df_aug 的历史列，前 lastdays 天。
    df: 原始 DataFrame，索引为日期
    lastdays: 最大历史天数
    返回: df_aug
    """
    n_rows = len(df)
    df_aug = pd.DataFrame(index=df.index)

    # 特殊列，前 6 天
    special_cols = ['open', 'low', 'truer']
    for da in range(1, min(6, lastdays)+1):
        for col in special_cols:
            if col in df.columns:
                val = df[col].iloc[-da]
                aug_col = f'last{col[0]}{da}d' if col != 'truer' else f'truer{da}d'
                df_aug[aug_col] = [val] * n_rows

    # 通用列
    general_cols = {
        'high':'lasth','close':'lastp','vol':'lastv','perd':'per',
        'upper':'upper','ma5d':'ma5','ma20d':'ma20','ma60d':'ma60',
        'perlastp':'perc'
    }
    # ,'high4':'high4','hmax':'hmax'
    for da in range(1, lastdays+1):
        for col, prefix in general_cols.items():
            if col in df.columns:
                val = df[col].iloc[-da]
                aug_col = f"{prefix}{da}d" if prefix not in ['upper'] else f"{prefix}{da}"
                df_aug[aug_col] = [val] * n_rows
            else:
                aug_col = f"{prefix}{da}d" if prefix not in ['upper'] else f"{prefix}{da}"
                df_aug[aug_col] = [np.nan] * n_rows

    return df_aug

def add_last_days_features(df, lastdays=10):
    """
    df: 原始 DataFrame
    lastdays: 需要处理的总天数
    """
    df_new = df.copy()

    # ------------------------
    # 1. 前 6 天的特殊列
    # ------------------------
    for da in range(1, min(6, lastdays) + 1):
        df_new[f'lasto{da}d'] = df_new['open'].shift(da-1)
        df_new[f'lastl{da}d'] = df_new['low'].shift(da-1)
        df_new[f'truer{da}d'] = df_new['truer'].shift(da-1)

    # ------------------------
    # 2. 所有 lastdays 的通用列
    # ------------------------
    for da in range(1, lastdays + 1):
        df_new[f'lasth{da}d'] = df_new['high'].shift(da-1)
        df_new[f'lastp{da}d'] = df_new['close'].shift(da-1)
        df_new[f'lastv{da}d'] = df_new['vol'].shift(da-1)
        df_new[f'per{da}d'] = df_new['perd'].shift(da-1)
        df_new[f'upper{da}'] = df_new['upper'].shift(da-1)
        df_new[f'ma5{da}d'] = df_new['ma5d'].shift(da-1)
        df_new[f'ma20{da}d'] = df_new['ma20d'].shift(da-1)
        df_new[f'ma60{da}d'] = df_new['ma60d'].shift(da-1)
        df_new[f'perc{da}d'] = df_new['perlastp'].shift(da-1)

        # safe_get 列，如果不存在返回 NaN
        # for col in ['high4', 'hmax']:
        #     df_new[f'{col}{da}d'] = df_new[col].shift(da-1) if col in df_new else np.nan

    return df_new

def compute_lastdays_percent_profile(df=None, lastdays=3, resample='d', vc_radio=100):
    """
    包装 compute_lastdays_percent 并添加性能分析
    """
    if df is None or len(df) <= 1:
        log.info("compute df is none or too short")
        return df
    import cProfile
    import pstats
    import io
    pr = cProfile.Profile()
    pr.enable()  # 开始性能分析

    # -----------------------------
    # 原 compute_lastdays_percent 逻辑
    # -----------------------------
    result_df = compute_lastdays_percent(df=df, lastdays=lastdays, resample=resample, vc_radio=vc_radio)

    pr.disable()  # 停止性能分析

    # -----------------------------
    # 输出 profile 信息到日志
    # -----------------------------
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)  # 打印前30条耗时记录
    profile_output = s.getvalue()
    log.info(f"[PROFILE] compute_lastdays_percent\n{profile_output}")

    return result_df


# def compare_perd_df_results(df_orig, df_opt, columns):
#     result = {}
#     mismatch_details = {}
    
#     for col in columns:
#         s1 = df_orig[col] if col in df_orig else pd.Series([np.nan]*len(df_orig), index=df_orig.index)
#         s2 = df_opt[col] if col in df_opt else pd.Series([np.nan]*len(df_orig), index=df_orig.index)
        
#         # mask for non-NaN comparisons
#         mask = s1.notna() & s2.notna()
#         mismatches = []
#         for idx in s1.index:
#             val1 = s1.loc[idx]
#             val2 = s2.loc[idx]
#             if pd.isna(val1) and pd.isna(val2):
#                 continue
#             if val1 != val2:
#                 mismatches.append({'index': idx, 'orig': val1, 'opt': val2, 'diff': val2-val1 if pd.notna(val2) and pd.notna(val1) else None})

#         result[col] = {
#             'match': mask.sum() - len(mismatches),
#             'mismatch': len(mismatches),
#             'missing_in_orig': s1.isna().sum(),
#             'missing_in_opt': s2.isna().sum(),
#         }
#         mismatch_details[col] = mismatches
#     result['match_stats'] = match_stats
#     result['mismatch_details'] = mismatch_details
#     return result


def compare_perd_df_results(df_orig, df_opt, columns=None):
    """
    对比两个 DataFrame 中指定列的值。
    返回每列的 match/mismatch/missing 信息，并增加 match_stats 方便统计。
    """
    result = {}
    if columns is None:
        columns = df_orig.columns.tolist()
    for col in columns:
        # 初始化
        col_result = {
            'match': [],
            'mismatch': [],
            'missing_in_orig': [],
            'missing_in_opt': []
        }

        # 遍历索引
        all_index = df_orig.index.union(df_opt.index)
        for idx in all_index:
            val_orig = df_orig[col].get(idx, None) if col in df_orig else None
            val_opt = df_opt[col].get(idx, None) if col in df_opt else None

            # 缺失判断
            if val_orig is None:
                col_result['missing_in_orig'].append(idx)
                continue
            if val_opt is None:
                col_result['missing_in_opt'].append(idx)
                continue

            # 比较值，NaN 当作相等
            if pd.isna(val_orig) and pd.isna(val_opt):
                col_result['match'].append(idx)
            elif val_orig == val_opt:
                col_result['match'].append(idx)
            else:
                col_result['mismatch'].append({
                    'index': idx,
                    'orig': val_orig,
                    'opt': val_opt,
                    'diff': (val_opt - val_orig) if pd.notna(val_opt) and pd.notna(val_orig) else None
                })

        result[col] = col_result

    # 汇总 match_stats
    match_stats = {}
    for col in columns:
        match_stats[col] = {
            'match': len(result[col]['match']),
            'mismatch': len(result[col]['mismatch']),
            'missing_in_orig': len(result[col]['missing_in_orig']),
            'missing_in_opt': len(result[col]['missing_in_opt']),
        }
    result['match_stats'] = match_stats
    result['mismatch_details'] = {col: result[col]['mismatch'] for col in columns}
    return result

def compare_compute_perd(df, func1, func2, key_cols=None, verbose=True):
    """
    对比两个 compute_perd_df 版本的性能和结果。
    
    参数:
        df: 输入 DataFrame
        func1: 原始函数
        func2: 新/优化函数
        key_cols: 需要验证的关键列列表, 默认 ['perlastp', 'perd', 'red', 'gren', 'upperT', 'upperL', 'topR', 'topD', 'ral']
        verbose: 是否打印详细信息
    
    返回:
        dict: {
            'time_func1': float,
            'time_func2': float,
            'results_match': dict {列名: True/False},
            'diffs': dict {列名: DataFrame 差异明细}
        }
    """
    if key_cols is None:
        key_cols = ['perlastp', 'perd', 'red', 'gren', 'upperT', 'upperL', 'topR', 'topD', 'ral']
    
    # 性能测试
    start = time.time()
    df1 = func1(df.copy())
    t1 = time.time() - start
    
    start = time.time()
    df2 = func2(df.copy())
    t2 = time.time() - start
    
    results_match = {}
    diffs = {}
    
    for col in key_cols:
        if col in df1.columns and col in df2.columns:
            equal = (df1[col] == df2[col]).all()
            results_match[col] = equal
            if not equal:
                diffs[col] = pd.concat([df1[col], df2[col]], axis=1).rename(columns={df1[col].name:'func1', df2[col].name:'func2'})
        else:
            results_match[col] = False
    
    if verbose:
        print(f"{func1.__name__} time: {t1:.4f}s")
        print(f"{func2.__name__} time: {t2:.4f}s")
        for col, match in results_match.items():
            print(f"{col}: {'MATCH' if match else 'MISMATCH'}")
    
    return {
        'time_func1': t1,
        'time_func2': t2,
        'results_match': results_match,
        'diffs': diffs
    }

# 使用示例：
# result = compare_compute_perd(dd, compute_perd_df_ver, compute_perd_df_fast)
# 如果有不匹配的列，可查看 result['diffs']['列名']

def generate_lastN_features_dict(df, lastdays=5):
    """
    将 df 的最近 lastdays 天生成字典特征，每个字段 lastN 作为键
    包含 EVAL_STATE 和 trade_signal
    """
    COL_MAPPING = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'perd': 'per',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        # 'high4': 'high4',
        # 'hmax': 'hmax',
        'EVAL_STATE': 'eval',
        'trade_signal': 'signal',
        'truer': 'truer'
    }

    data = {}
    for da in range(1, lastdays + 1):
        for col, prefix in COL_MAPPING.items():
            # 倒数索引为 -da
            if col in df.columns and len(df) >= da:
                val = df[col].iloc[-da]
            else:
                val = 0
            # upper 不加 d 后缀
            if prefix == 'upper':
                key = f'{prefix}{da}' if da > 0 else prefix
            else:
                key = f'{prefix}{da}d'
            data[key] = val

    return data

COL_MAPPING = {
    'open': 'lasto',
    'high': 'lasth',
    'low': 'lastl',
    'close': 'lastp',
    'vol': 'lastv',
    'perd': 'per',
    'upper': 'upper',
    'ma5d': 'ma5',
    'ma20d': 'ma20',
    'ma60d': 'ma60',
    'perlastp': 'perc',
    # 'high4': 'high4',
    # 'hmax': 'hmax',
    'EVAL_STATE': 'eval',
    'trade_signal': 'signal'
}

def generate_lastN_features(df, lastdays=6):
    df_temp = pd.DataFrame()
    for col, prefix in COL_MAPPING.items():
        if col in df.columns:
            col_values = df[col].iloc[-lastdays:]
            if len(col_values) < lastdays:
                col_values = pd.concat([pd.Series([0]*(lastdays-len(col_values))), col_values])
        else:
            col_values = pd.Series([0]*lastdays)
        
        for i in range(1, lastdays+1):
            df_temp[f'{prefix}{i}d'] = [col_values.iloc[-i]]
    
    return df_temp
# def generate_lastN_features(df, lastdays=6, feature_cols=None):
#     """
#     生成 df 的过去 lastdays 天的多列特征，向量化处理。
#     df: 原始DataFrame，必须按时间升序排列
#     lastdays: 要取的过去天数
#     feature_cols: list, 需要生成的特征列，如果 None，使用默认列
#     返回: df_temp，单行 DataFrame，包含 lastdays 天的所有特征
#     """
#     if feature_cols is None:
#         feature_cols = [
#             'open', 'close', 'high', 'low', 'vol', 'perd', 'upper',
#             'ma5d', 'ma20d', 'ma60d', 'perlastp', 'high4', 'hmax',
#             'EVAL_STATE', 'trade_signal'
#         ]

#     df_temp = pd.DataFrame()

#     for c in feature_cols:
#         if c in df.columns:
#             col_values = df[c].iloc[-lastdays:]  # 取最后 N 行
#             # 如果不足 lastdays，用 NaN 填充
#             if len(col_values) < lastdays:
#                 col_values = pd.concat([pd.Series([np.nan]*(lastdays - len(col_values))), col_values])
#         else:
#             # 列不存在，全用 NaN 填充
#             col_values = pd.Series([np.nan]*lastdays)

#         # 给每一天生成列名
#         for i in range(1, lastdays+1):
#             df_temp[f'{c}{i}d'] = [col_values.iloc[-i]]

#     return df_temp

def compute_lastdays_percent(df=None, lastdays=3, resample='d',vc_radio=100,normalized=False):
    if df is not None and len(df) > lastdays:
        if len(df) > lastdays + 1:
            # 判断lastdays > 9 
            lastdays = len(df) - 2
            lastdays = lastdays if lastdays < cct.compute_lastdays else cct.compute_lastdays
        else:
            lastdays = len(df) - 1
        # if 'date' in df.columns:
        #     df = df.set_index('date')
        # if not isinstance(df.index, pd.DatetimeIndex) and 'date' in df.columns:
        #     df.index = pd.to_datetime(df.pop('date'), errors='coerce')
        if 'date' in df.columns:
            df.index = df.pop('date')
        # df = df.sort_index(ascending=True)
        if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
            df = df[df.index < cct.get_today()]

        df['ma5d'] = talib.EMA(df['close'], timeperiod=5)
        df['ma10d'] = talib.EMA(df['close'], timeperiod=10)
        df['ma20d'] = talib.EMA(df['close'], timeperiod=26)
        df['ma60d'] = talib.SMA(df['close'], timeperiod=60)

        # safe_SMA(df, 'close', 5,  'ma5d')
        # safe_SMA(df, 'close', 10, 'ma10d')
        # safe_SMA(df, 'close', 20, 'ma20d')
        # safe_SMA(df, 'close', 60, 'ma60d')

        df['truer'] = ta.true_range(df.high, df.low, df.close)


        df = compute_cross_indicators(df, [('ma5d', 'ma10d', 'op')], [('upper', 'ma5d', 'topU', 'eneU')])

        df = compute_perd_df(df,lastdays=lastdays,resample=resample,normalized=normalized)


        df['vchange'] = ((df['vol'] - df['vol'].shift(1)) / df['vol'].shift(1) * 100).round(1)
        df = df.fillna(0)
        df['vcra'] = len(df[df.vchange > vc_radio])
        df['vcall'] = df['vchange'].max()
        df = evaluate_trading_signal(df)
        df_temp = generate_lastN_features_dict(df, lastdays=lastdays)
        df_repeat = pd.DataFrame([df_temp]).loc[np.repeat(0, len(df))].reset_index(drop=True)
        df = pd.concat([df.reset_index(), df_repeat], axis=1)
        df = df.loc[:,~df.columns.duplicated()]
        df = compute_cum_and_top_stats(
                df,
                ma_days_list=['5','10'],            # 计算 ma5dcum 和 ma10dcum
                lastdays=cct.compute_lastdays,
                per_top_limits=[(9.9, 'top10'), (5, 'top5')]  # top10/top5 统计
            )

        # result = compare_perd_df_results(df_orig, df, columns=None)
        # # 查看匹配统计
        # # print(result['match_stats'])
        # print(result['mismatch_details'])

        if 'date' in df.columns:
            df.index = df.pop('date')
            # df.index = pd.to_datetime(df.pop('date'), errors='coerce')

    return df

        # compare_first_rows(df, df_aug, lastdays=lastdays,n=1)
        # compare_shifted_df(df, df_aug, lastdays=lastdays)

        # cols = [
        #         'lasto1d','lastl1d','lastp1d','per1d',
        #         'lasto2d','lastl2d','lastp2d','per2d',
        #         'lasto3d','lastl3d','lastp3d','per3d',
        #         'lasto4d','lastl4d','lastp4d','per4d',
        #         'lasto5d','lastl5d','lastp5d','per5d',
        #         'lasto6d','lastl6d','lastp6d','per6d'
        #     ]

        # # df_cols_only = df.loc[:, cols][-1:]
        # # df_checked = check_conditions_auto(df_cols_only)
        # # df['MainU'] = df_checked.MainU.values[0]


        # # # 1. 保留最后一行需要检查的列
        # # df_cols_only = df.loc[:, cols].iloc[[-1]]  # 用 iloc[[-1]] 返回 DataFrame 而非 Series

        # # 2. 调用自动检查函数

        # df_checked = check_conditions_auto(df[-1:])

        # # 3. 直接赋值给原始 df 的 'MainU' 列对应最后一行
        # # df.loc[df.index[-1], 'MainU'] = df_checked.loc[df_checked.index[-1], '符合条件']

        # df.loc[df.index[-1], 'MainU'] = df_checked.loc[df_checked.index[-1], 'MainU']
        # # 列表 → 逗号分隔字符串
        # # df.loc[df.index[-1], 'MainU'] = ','.join(map(str, df_checked.loc[df_checked.index[-1], 'MainU']))
        # # print(df.MainU)
        # # import ipdb;ipdb.set_trace()


        # new_row_df = pd.DataFrame([df_temp]) 
        # df = pd.concat([df, new_row_df], ignore_index=True)
            # df['perc%sd' % da] = (df['perlastp'][-da:].sum())
        # df['lastv9m'] = df['vol'][-lastdays:].mean()
            # df['mean%sd' % da] = df['meann'][-da]




def get_tdx_exp_low_or_high_price(code, dt=None, ptype='close', dl=None, end=None):
    '''
    :param code:999999
    :param dayl:Duration Days
    :param type:TDX type
    :param dt:  Datetime
    :param ptype:low or high
    :return:Series or df
    '''
    # dt = cct.day8_to_day10(dt)
    if dt is not None and dl is not None:
        # log.debug("dt:%s dl:%s"%(dt,dl))
        df = get_tdx_Exp_day_to_df(
            code, start=dt, dl=dl, end=end).sort_index(ascending=False)
        if df is not None and not df.empty:
            if len(str(dt)) == 10:
                dz = df[df.index >= dt]
                # if dz.empty:
                # dd = Series(
                # {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
                # 'vol': 0})
                # return dd
                if len(dz) < abs(int(dl) - changedays):
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                if isinstance(dz, Series):
                    # dz=pd.DataFrame(dz)
                    # dz=dz.set_index('date')
                    return dz

            else:
                if len(df) > int(dl):
                    dz = df[:int(dl)]
                else:
                    dz = df
            if dz is not None and not dz.empty:
                if ptype == 'high':
                    lowp = dz.high.max()
                    lowdate = dz[dz.high == lowp].index.values[-1]
                    log.debug("high:%s" % lowdate)
                elif ptype == 'close':
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                    log.debug("close:%s" % lowdate)
                else:
                    lowp = dz.low.min()
                    lowdate = dz[dz.low == lowp].index.values[-1]
                    log.debug("low:%s" % lowdate)

                log.debug("date:%s %s:%s" % (lowdate, ptype, lowp))
                # log.debug("date:%s %s:%s" % (dt, ptype, lowp))
                dd = df[df.index == lowdate]
                if len(dd) > 0:
                    dd = dd[:1]
                    dt = dd.index.values[0]
                    dd = dd.T[dt]
                    dd['date'] = dt
            else:
                dd = pd.Series([],dtype='float64')

        else:
            log.warning("code:%s no < dt:NULL" % (code))
            dd = pd.Series([],dtype='float64')
            # dd = Series(
            #     {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
            #      'vol': 0})
        return dd
    else:
        dd = get_tdx_Exp_day_to_df(code, dl=1)
        return dd

def get_tdx_exp_low_or_high_power(
    code, dt=None, ptype='close', dl=None, end=None,
    power=False, lastp=False, newdays=None,
    resample='d', lvoldays=ct.lastdays * 3,
    detect_calc_support=False
):
    if dt is None and dl is None:
        return get_tdx_Exp_day_to_df(code, dl=1)

    df = get_tdx_Exp_day_to_df(
        code, start=dt, dl=dl, end=end,
        newdays=newdays, resample=resample,
        detect_calc_support=detect_calc_support
    )

    if df is None or len(df) <= 5:
        return pd.Series([], dtype='float64')

    df = df.sort_index(ascending=False)

    # ✅ 极早裁剪
    need_len = max(int(dl or 0), lvoldays) + 5
    df = df.iloc[:need_len]

    df = resample_dataframe_recut(df, resample=resample)

    # ========= lastp 快速返回 =========
    if lastp:
        row = df.iloc[0]
        out = row.copy()
        out['date'] = df.index[0]
        if 'ma5d' in row and row.ma5d:
            out['ma5d'] = round(float(row.ma5d), 2)
        if 'ma10d' in row and row.ma10d:
            out['ma10d'] = round(float(row.ma10d), 2)
        return out

    # ========= dz 区间 =========
    if dl:
        dz = df.iloc[:int(dl)]
    else:
        dz = df

    if dz.empty:
        return pd.Series([], dtype='float64')

    # ========= 极值点 =========
    if ptype == 'high':
        lowdate = dz.close.idxmax()
    else:
        lowdate = dz.close.idxmin()

    dtemp = df.loc[lowdate]

    # ========= 成交量 =========
    vols = dz.vol.values[:lvoldays]
    if vols.size > 5:
        vols = vols[(vols != vols.min()) & (vols != vols.max())]
    lastvol = round(vols.mean(), 1) if vols.size else 0

    # ========= 输出 =========
    latest = df.iloc[0].copy()
    latest['date'] = lowdate
    latest['high'] = dtemp.high
    latest['low'] = dtemp.low
    latest['close'] = dtemp.close
    latest['open'] = dtemp.open
    latest['lowvol'] = dtemp.vol
    latest['last6vol'] = lastvol
    return latest


def get_tdx_exp_low_or_high_power_slow(code, dt=None, ptype='close', dl=None, end=None, power=False, lastp=False, newdays=None, resample='d', lvoldays=ct.lastdays * 3,detect_calc_support=False):
    '''
    :param code:999999
    :param dayl:Duration Days
    :param type:TDX type
    :param dt:  Datetime
    :param ptype:low or high
    :return:Series or df
    '''
    # dt = cct.day8_to_day10(dt)

    if dt is not None or dl is not None:
        # log.debug("dt:%s dl:%s"%(dt,dl))
        df = get_tdx_Exp_day_to_df(code, start=dt, dl=dl, end=end, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support).sort_index(ascending=False)
        if df is not None and len(df) > 5:

            df=resample_dataframe_recut(df,resample=resample)

            if lastp:
                dd = df[:1]
                dt = dd.index.values[0]
                dd = dd.T[dt]
                dd['date'] = dt
                if 'ma5d' in df.columns and 'ma10d' in df.columns:
                    if df[:1].ma5d[0] is not None and df[:1].ma5d[0] != 0:
                        dd['ma5d'] = round(float(df[:1].ma5d[0]), 2)
                    if df[:1].ma10d[0] is not None and df[:1].ma10d[0] != 0:
                        dd['ma10d'] = round(float(df[:1].ma10d[0]), 2)
                return dd

            if len(str(dt)) == 10:
                dz = df[df.index >= dt]
                if len(dz) < abs(int(dl) - changedays):
                    if len(df) > int(dl):
                        dz = df[:int(dl)]
                    else:
                        dz = df
                if isinstance(dz, Series):
                    return dz

            else:
                if len(df) > int(dl):
                    dz = df[:int(dl)]
                else:
                    dz = df
            if dz is not None and not dz.empty:
                if ptype == 'high':
                    lowp = dz.close.max()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                elif ptype == 'close':
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                else:
                    lowp = dz.close.min()
                    lowdate = dz[dz.close == lowp].index.values[-1]
                volmean = dz.vol[:lvoldays].tolist()
                
                if len(volmean) > 5:
                    volmean.remove(min(volmean))    
                    volmean.remove(max(volmean))  

                lastvol = round(sum(volmean) / len(volmean),1)

                dtemp = df[df.index == lowdate]
                dd = df[:1]

                if len(dd) > 0:
                    dd = dd[:1]
                    dt = dd.index.values[0]
                    dd = dd.T[dt]
                    dd['date'] = lowdate

                dd['high'] = dtemp.high.values[0]
                dd['low'] = dtemp.low.values[0]
                dd['close'] = dtemp.close.values[0]
                dd['open'] = dtemp.open.values[0]

                dd['lowvol'] = dtemp.vol.values[0]
                dd['last6vol'] = lastvol

            else:
                dd = pd.Series([],dtype='float64')

        else:
            dd = pd.Series([],dtype='float64')
        return dd
    else:
        dd = get_tdx_Exp_day_to_df(code, dl=1)
        return dd


# def get_tdx_day_to_df_last(code, dayl=1, type=0, dt=None, ptype='close', dl=None, newdays=None):
#     '''
#     :param code:999999
#     :param dayl:Duration Days
#     :param type:TDX type
#     :param dt:  Datetime
#     :param ptype:low or high
#     :return:Series or df
#     '''
#     # dayl=int(dayl)
#     # type=int(type)
#     # print "t:",dayl,"type",type
#     if newdays is not None:
#         newstockdayl = newdays
#     else:
#         newstockdayl = newdaysinit
#     if not type == 0:
#         f = (lambda x: str((1000000 - int(x))) if x.startswith('0') else x)
#         code = f(code)
#     code_u = cct.code_to_symbol(code)
#     day_path = day_dir % 'sh' if code.startswith(
#         ('5', '6', '9')) else day_dir % 'sz'
#     p_day_dir = day_path.replace('/', path_sep).replace('\\', path_sep)
#     # p_exp_dir=exp_dir.replace('/',path_sep).replace('\\',path_sep)
#     # print p_day_dir,p_exp_dir
#     file_path = p_day_dir + code_u + '.day'
#     if not os.path.exists(file_path):
#         ds = Series(
#             {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
#              'vol': 0})
#         return ds
#     ofile = file(file_path, 'rb')
#     b = 0
#     e = 32
#     if dayl == 1 and dt == None:
#         log.debug("%s" % (dayl == 1 and dt == None))
#         fileSize = os.path.getsize(file_path)
#         if fileSize < 32:
#             print "why", code
#         ofile.seek(-e, 2)
#         buf = ofile.read()
#         ofile.close()
#         a = unpack('IIIIIfII', buf[b:e])
#         # if len(a) < 7:
#         #     continue
#         tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#         topen = float(a[1] / 100.0)
#         thigh = float(a[2] / 100.0)
#         tlow = float(a[3] / 100.0)
#         tclose = float(a[4] / 100.0)
#         amount = float(a[5] / 10.0)
#         tvol = int(a[6])  # int
#         # tpre = int(a[7])  # back
#         dt_list = Series(
#             {'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose, 'amount': amount,
#              'vol': tvol})
#         return dt_list
#     elif dayl == 1 and dt is not None and dl is not None:
#         log.debug("dt:%s" % (dt))
#         dt_list = []
#         # if len(str(dt)) == 8:
#         # dt = cct.day8_to_day10(dt)
#         # else:
#         # dt=get_duration_price_date(code, ptype=ptype, dt=dt)
#         # print ("dt:%s"%dt)
#         fileSize = os.path.getsize(file_path)
#         if fileSize < 32:
#             print "why", code
#         b = fileSize
#         ofile.seek(-fileSize, 2)
#         no = int(fileSize / e)
#         if no < newstockdayl:
#             return pd.Series([],dtype='float64')
#         # print no,b,day_cout,fileSize
#         buf = ofile.read()
#         ofile.close()
#         # print repr(buf)
#         # df=pd.DataFrame()
#         for i in xrange(no):
#             a = unpack('IIIIIfII', buf[-e:b])
#             if len(a) < 7:
#                 continue
#             tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#             topen = float(a[1] / 100.0)
#             thigh = float(a[2] / 100.0)
#             tlow = float(a[3] / 100.0)
#             tclose = float(a[4] / 100.0)
#             amount = float(a[5] / 10.0)
#             tvol = int(a[6])  # int
#             # tpre = int(a[7])  # back
#             dt_list.append({'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
#                             'amount': amount, 'vol': tvol})
#             # print series
#             # dSeries.append(series)
#             # dSeries.append(Series({'code':code,'date':tdate,'open':topen,'high':thigh,'low':tlow,'close':tclose,'amount':amount,'vol':tvol,'pre':tpre}))
#             b = b - 32
#             e = e + 32
#             # print tdate,dt
#             if tdate < dt:
#                 # print "why"
#                 break
#         df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
#         # print "len:%s %s"%(len(df),fileSize)
#         df = df.set_index('date')
#         dt = get_duration_price_date(code, ptype=ptype, dt=dt, df=df, dl=dl)
#         log.debug('last_dt:%s' % dt)
#         dd = df[df.index == dt]
#         if len(dd) > 0:
#             dd = dd[:1]
#             dt = dd.index.values[0]
#             dd = dd.T[dt]
#             dd['date'] = dt
#         else:
#             log.warning("no < dt:NULL")
#             dd = pd.Series([],dtype='float64')
#             # dd = Series(
#             # {'code': code, 'date': cct.get_today(), 'open': 0, 'high': 0, 'low': 0, 'close': 0, 'amount': 0,
#             # 'vol': 0})
#         return dd
#     else:
#         dt_list = []
#         fileSize = os.path.getsize(file_path)
#         # print fileSize
#         day_cout = abs(e * int(dayl))
#         # print day_cout
#         if day_cout > fileSize:
#             b = fileSize
#             ofile.seek(-fileSize, 2)
#             no = int(fileSize / e)
#         else:
#             no = int(dayl)
#             b = day_cout
#             ofile.seek(-day_cout, 2)
#         # print no,b,day_cout,fileSize
#         buf = ofile.read()
#         ofile.close()
#         # print repr(buf)
#         # df=pd.DataFrame()
#         for i in xrange(no):
#             a = unpack('IIIIIfII', buf[-e:b])
#             if len(a) < 7:
#                 continue
#             tdate = str(a[0])[:4] + '-' + str(a[0])[4:6] + '-' + str(a[0])[6:8]
#             topen = float(a[1] / 100.0)
#             thigh = float(a[2] / 100.0)
#             tlow = float(a[3] / 100.0)
#             tclose = float(a[4] / 100.0)
#             amount = float(a[5] / 10.0)
#             tvol = int(a[6])  # int
#             # tpre = int(a[7])  # back
#             dt_list.append({'code': code, 'date': tdate, 'open': topen, 'high': thigh, 'low': tlow, 'close': tclose,
#                             'amount': amount, 'vol': tvol})
#             # print series
#             # dSeries.append(series)
#             # dSeries.append(Series({'code':code,'date':tdate,'open':topen,'high':thigh,'low':tlow,'close':tclose,'amount':amount,'vol':tvol,'pre':tpre}))
#             b = b - 32
#             e = e + 32
#         df = pd.DataFrame(dt_list, columns=ct.TDX_Day_columns)
#         df = df.set_index('date')
#         return df


#############################################################
# usage Ê¹ÓÃËµÃ÷
#
#############################################################
def get_tdx_all_day_LastDF(codeList, dt=None, ptype='close',detect_calc_support=False):
    '''
    outdate
    '''
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    if dt is not None:
        if len(str(dt)) != 8:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            dl = len(df[df.index >= dt])
            log.info("LastDF:%s" % dt)
        else:
            # dt = int(dt)+10
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            dl = len(df[df.index >= dt])
            log.info("LastDF:%s" % dt)
    else:
        dl = None

    if len(codeList) > 100:
        results = cct.to_mp_run_async(
            get_tdx_Exp_day_to_df, codeList, start=None, end=None, dl=1, newdays=0,detect_calc_support=detect_calc_support)
        # get_tdx_day_to_df_last, codeList, 1, type, dt, ptype, dl)
    else:
        results=[]
        for code in codeList:
            results.append(get_tdx_Exp_day_to_df(code, dl=1))


#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.set_index('code')
    # df.loc[:, 'open':] = df.loc[:, 'open':].astype(float)
    log.info("get_to_mp:%s" % (len(df)))
    log.info(f"TDXTime:{time.time() - time_t:.3f}")
    if dt != None:
        print(("TDX:%0.2f" % (time.time() - time_t)), end=' ')
    return df

def get_single_df_lastp_to_df(top_all, lastpTDX_DF=None, dl=ct.PowerCountdl, end=None, ptype='low', filter='y', power=True, lastp=False, newdays=None, checknew=True, resample='d'):

    time_s = time.time()
    codelist = top_all.index.tolist()
#    codelist = ['603169']
    log.info('toTDXlist:%s dl=%s end=%s ptype=%s' % (len(codelist), dl, end, ptype))
    # print codelist[5]
    h5_fname = 'tdx_last_df'
    # market=ptype+'_'+str(dl)+'_'+filter+'_'+str(len(codelist))
    if end is not None:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + \
            '_' + end.replace('-', '') + '_' + 'all'
    else:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'

    # if newdays is not None:
    #     h5_table = h5_table + '_'+ str(newdays)

    log.info('h5_table:%s' % (h5_table))

    # codelist = dm.index.tolist()
    # codelist.extend(tdx_index_code_list)
    # search_Tdx_multi_data_duration(cct.tdx_hd5_name, 'all_300',code_l=codelist, start=60, end=None, index='date')

    if lastpTDX_DF is None or len(lastpTDX_DF) == 0:
        # h5 = top_hdf_api(fname=h5_fname,table=market,df=None)
        h5 = h5a.load_hdf_db(h5_fname, table=h5_table,
                             code_l=codelist, timelimit=False)

        if h5 is not None and not h5.empty:
            #            o_time = h5[h5.time <> 0].time
            #            if len(o_time) > 0:
            #                o_time = o_time[0]
            #            print time.time() - o_time
            #                if time.time() - o_time > h5_limit_time:
            log.info("load hdf data:%s %s %s" % (h5_fname, h5_table, len(h5)))
            tdxdata = h5
        else:
            log.error("TDX None:%s")
            return top_all
    else:
        tdxdata = lastpTDX_DF

    top_all = cct.combine_dataFrame(
        top_all, tdxdata, col=None, compare=None, append=False)

    # log.info('Top-merge_now:%s' % (top_all[:1]))
    top_all['llow'] = top_all.get('llow', 0)  # 列不存在时用默认0
    top_all = top_all[top_all['llow'] > 0]
    log.debug('T:%0.2f'%(time.time()-time_s))
    return top_all

def compute_jump_du_count(df,lastdays=cct.compute_lastdays,resample='d'):

    # if 'op' in df.columns and 'boll' in df.columns:
    #     df = df[(df.op > -1) & (df.boll > -1)]
    _Integer = int(lastdays/10) 
    _remainder = lastdays%10


    #没有用处理顺序截取非个股处理
    # if _Integer > 0:
    #     # temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]
    #     temp=df[df.columns[((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(9)))]]
    #     #lastday > 20 error !!!!
    #     # if _Integer > 1:
    #     #     for i in range(1,_Integer, 1):
    #     #         # temp=df[df.columns[((df.columns >= 'per1d') & (df.columns <= 'per%sd'%(9))) | ((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder))) ]]
    #     #         # d_col=df[ ((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder))) ]
    #     #         d_col=df[df.columns[((df.columns >= 'per%s0d'%(i)) & (df.columns <= 'per%s%sd'%(i,9)))]]
    #     #         temp = cct.combine_dataFrame(temp, d_col, col=None, compare=None, append=False, clean=True)
    #     d_col=df[df.columns[((df.columns >= 'per%s0d'%(_Integer)) & (df.columns <= 'per%s%sd'%(_Integer,_remainder)))]]
    #     temp = cct.combine_dataFrame(temp, d_col, col=None, compare=None, append=False, clean=True)


    # else:

    #     temp=df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(lastdays))]]
    
    temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]

    if resample == 'd':
        tpp =temp[temp >9.9].count()
        # temp[temp >9.9].per1d.dropna(how='all')
        idxkey= tpp[ tpp ==tpp.min()].index.values[0]
        perlist = temp.columns[temp.columns <= idxkey][-2:].values.tolist()
        if len(perlist) >=2:
            # codelist= temp[ ((temp[perlist[0]] >9) &(temp[perlist[1]] > 9)) | (temp[perlist[1]] > 9) ].index.tolist()
            codelist= temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) ].index.tolist()
            # temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) | ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 0)].shape
        else:
            codelist= temp[ (temp[perlist[0]] >9.9)].index.tolist()
    else:
        codelist = temp.index.tolist()
        # tpp =temp[temp >9.9].count()
        # # temp[temp >9.9].per1d.dropna(how='all')
        # idxkey= tpp[ tpp ==tpp.min()].index.values[0]
        # perlist = temp.columns[temp.columns <= idxkey][-2:].values.tolist()
        # if len(perlist) >=2:
        #     # codelist= temp[ ((temp[perlist[0]] >9) &(temp[perlist[1]] > 9)) | (temp[perlist[1]] > 9) ].index.tolist()
        #     codelist= temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) ].index.tolist()
        #     # temp[ ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 9) | ((temp[perlist[0]] >9)) & (temp[perlist[1]] > 0)].shape
        # else:
        #     codelist= temp[ (temp[perlist[0]] >9.9)].index.tolist()


    return codelist

# def compute_ma5d_ra(df,lastdays=cct.compute_lastdays,madays='5'):
#     # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]][-1:]
#     temp=df.ma5d[-10:]
#     cum_min,ops=LIS_TDX_Cum(temp.sort_index(ascending=False).values)
#     #倒叙新低了几天
#     # sorted([20.57, 21.35, 22.04, 22.68, 22.92,23.1,23.2,23.4,23.5],reverse=True)
#     df['ra']=ops[-1]+1 if ops[-1] > 0 else 0
#     return df

def compute_ma5d_count(df, lastdays=cct.compute_lastdays, madays='5'):
    """
    计算 MA 累计值
    """
    # 匹配 maXd 列
    ma_cols = df.filter(regex=f"ma{madays}\\d{{1,2}}d$")

    # 计算累计均值
    df[f'ma{madays}dcum'] = ma_cols.sum(axis=1) / lastdays
    df[f'ma{madays}dcum'] = df[f'ma{madays}dcum'].round(1)

    return df.fillna(0)


def compute_cum_and_top_stats(df, ma_days_list=['5'], lastdays=cct.compute_lastdays, per_top_limits=[(9.9, 'top10'), (5, 'top5')]):
    """
    统一计算 MA 累计值和涨幅统计指标

    参数:
        df: pd.DataFrame, 股票数据
        ma_days_list: list, 需要计算累计值的 MA 天数列表
        lastdays: int, 计算累计均值的天数
        per_top_limits: list of tuple, (阈值, 输出列名)
    返回:
        df: pd.DataFrame, 增加统计列
    """
    # 计算 MA 累计
    for madays in ma_days_list:
        ma_cols = df.filter(regex=f"ma{madays}\\d{{1,2}}d$")
        if not ma_cols.empty:
            df[f'ma{madays}dcum'] = (ma_cols.sum(axis=1) / lastdays).round(1)
        else:
            df[f'ma{madays}dcum'] = 0

    # 计算涨幅统计
    per_cols = df.filter(regex=r"per\d{1,2}d$")
    for threshold, colname in per_top_limits:
        if not per_cols.empty:
            df[colname] = (per_cols >= threshold).sum(axis=1)
        else:
            df[colname] = 0

    return df.fillna(0)

def compute_top10_count(df, lastdays=cct.compute_lastdays, top_limit=ct.per_redline):
    """
    计算涨幅统计，如 top10/top5
    """
    per_cols = df.filter(regex=r"per\d{1,2}d$")

    df['top10'] = (per_cols >= 9.9).sum(axis=1)
    df['top5'] = (per_cols > 5).sum(axis=1)

    return df.fillna(0)

def compute_ma5d_count_slow(df,lastdays=cct.compute_lastdays,madays='5'):
    # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]][-1:]
    # temp=df[df.columns[(df.columns >= 'ma%s1d'%(madays)) & (df.columns <= 'ma%s%sd'%(madays,lastdays))]]

    temp=df.loc[:,df.columns.str.contains( "ma%s\d{1,2}d$"%(madays),regex= True)]

    # temp_du=df[df.columns[(df.columns >= 'du1d') & (df.columns <= 'du%sd'%(lastdays))]]
    # temp.T[temp.T >=10].count()

    df['ma%sdcum'%(madays)]=(temp.T.sum()/lastdays)
    df['ma%sdcum'%(madays)] = df['ma%sdcum'%(madays)].apply(lambda x: round(x,1))  
      
    # df['topU']=temp.T[temp.T >= top_limit].count()  #0.8 上涨个数  compute_upper_cross
    # df['topR']=temp_du.T[temp_du.T >= 0].count()    #跳空缺口
    # df['top0']=temp_du.T[temp_du.T == 0].count()    #一字涨停
    # df['upper'] = map(lambda x: round((1 + 11.0 / 100) * x, 1), df.ma10d)
    # df['lower'] = map(lambda x: round((1 - 9.0 / 100) * x, 1), df.ma10d)
    # df['ene'] = map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower)
    df = df.fillna(0)
    return df

def compute_top10_count_slow(df,lastdays=cct.compute_lastdays,top_limit=ct.per_redline):
    # top_temp.loc[:,top_temp.columns.str.contains('perc')]
    # top_temp.loc[:,top_temp.columns.str.startswith('perc')]
    # temp.loc[:,temp.columns.str.contains( "per\d{1,2}d$",regex= True)]
    # temp=df.loc[:,df.columns.str.contains( "perc\d{1,2}d$",regex= True)]

    # temp=df[df.columns[(df.columns >= 'per1d') & (df.columns <= 'per%sd'%(lastdays))]][-15:]
    temp=df.loc[:,df.columns.str.contains( "per\d{1,2}d$",regex= True)]
    # temp_du=df[df.columns[(df.columns >= 'du1d') & (df.columns <= 'du%sd'%(lastdays))]]
    # temp.T[temp.T >=10].count()

    df['top10']=temp.T[temp.T >=9.9].count()        #涨停个数
    df['top5']=temp.T[temp.T >5].count()
    # df['topU']=temp.T[temp.T >= top_limit].count()  #0.8 上涨个数  compute_upper_cross
    # df['topR']=temp_du.T[temp_du.T >= 0].count()    #跳空缺口
    # df['top0']=temp_du.T[temp_du.T == 0].count()    #一字涨停
    # df['upper'] = map(lambda x: round((1 + 11.0 / 100) * x, 1), df.ma10d)
    # df['lower'] = map(lambda x: round((1 - 9.0 / 100) * x, 1), df.ma10d)
    # df['ene'] = map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower)
    df = df.fillna(0)
    return df

def get_index_percd(codeList=tdx_index_code_list, dt=60, end=None, ptype='low', filter='n', power=False, lastp=False, newdays=None, dl=None, resample='d', showRunTime=True):
    tdxdata = get_tdx_exp_all_LastDF_DL(codeList, dt=dt, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample)
    return tdxdata

def select_codes_from_tdx(tdxdata: pd.DataFrame, tdx_index_code_list: list) -> pd.DataFrame:
    """
    从 tdxdata 中选择 tdx_index_code_list 存在的行。
    不存在的代码会被自动忽略。
    """
    # ---------- 1. 找到存在的代码 ----------
    existing_codes = [code for code in tdx_index_code_list if code in tdxdata.index]

    if not existing_codes:
        # 没有匹配的代码，返回空 DataFrame
        return pd.DataFrame(columns=tdxdata.columns)

    # ---------- 2. 用 loc 取出 ----------
    return tdxdata.loc[existing_codes]


def get_append_lastp_to_df(top_all=None, lastpTDX_DF=None, dl=ct.Resample_LABELS_Days['d'], end=None, ptype='low', filter='y', power=True, lastp=False, newdays=None, checknew=True, resample='d',showtable=False,detect_calc_support=False):
    time_s = time.time()
    if top_all is None or top_all.empty:
        top_all = getSinaAlldf(market='all')
    codelist = top_all.index.tolist()
    codelist.extend(tdx_index_code_list)
    codelist = list(set(codelist))
    log.info('toTDXlist:%s dl=%s end=%s ptype=%s' % (len(codelist), dl, end, ptype))
    h5_fname = 'tdx_last_df'
    if end is not None:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + \
            '_' + end.replace('-', '') + '_' + 'all'
    else:
        h5_table = ptype + '_' + resample + '_' + str(dl) + '_' + filter + '_' + 'all'

    log.debug('h5_table:%s' % (h5_table))

    if lastpTDX_DF is None or len(lastpTDX_DF) == 0:
        h5 = h5a.load_hdf_db(h5_fname, table=h5_table,
                             code_l=codelist, timelimit=False,showtable=showtable)
        print(("%s:%0.2f" % (h5_fname,time.time() - time_s)), end=' ')
        if h5 is not None and not h5.empty:
            log.debug("load hdf data:%s %s %s" % (h5_fname, h5_table, len(h5)))
            tdxdata = h5
            if cct.GlobalValues().getkey('tdx_Index_Tdxdata') is None:
                if tdx_index_code_list[0] in tdxdata.index:
                    cct.GlobalValues().setkey('tdx_Index_Tdxdata', select_codes_from_tdx(tdxdata, tdx_index_code_list))
        else:
            log.info("no hdf data:%s %s" % (h5_fname, h5_table))
            print(f"TDD: {len(codelist)} resample:{resample}",end='')
            tdxdata = get_tdx_exp_all_LastDF_DL(
                codelist, dt=dl, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support)
            
            tdxdata.rename(columns={'open': 'lopen'}, inplace=True)
            tdxdata.rename(columns={'high': 'lhigh'}, inplace=True)
            tdxdata.rename(columns={'close': 'lastp'}, inplace=True)
            tdxdata.rename(columns={'low': 'llow'}, inplace=True)
            tdxdata.rename(columns={'vol': 'lvol'}, inplace=True)
            tdxdata.rename(columns={'amount': 'lamount'}, inplace=True)
            wcdf = wcd.get_wencai_data(top_all.name)
            wcdf['category'] = wcdf['category'].apply(lambda x:x.replace('\r','').replace('\n',''))
            tdxdata = cct.combine_dataFrame(tdxdata, wcdf.loc[:, ['category','hangye']])
            if cct.GlobalValues().getkey('tdx_Index_Tdxdata') is None:
                if tdx_index_code_list[0] in tdxdata.index:
                    cct.GlobalValues().setkey('tdx_Index_Tdxdata', select_codes_from_tdx(tdxdata, tdx_index_code_list))
            tdxdata = tdxdata.drop_duplicates(keep='first')  # 保留第一次出现的行
            h5 = h5a.write_hdf_db(
                h5_fname, tdxdata, table=h5_table, append=True)

        log.debug("TDX Col:%s" % tdxdata.columns.values[:10])
    else:
        tdxdata = lastpTDX_DF
    log.debug("TdxLastP: %s %s" %
              (len(tdxdata), tdxdata.columns.values[:10]))

    if checknew:
        tdx_list = tdxdata.index.tolist()
        diff_code = list(set(codelist) - set(tdx_list))
        diff_code = [
            co for co in diff_code if co.startswith(cct.code_startswith)]
        if len(diff_code) > 5:
            log.error("tdx Out:%s code:%s" % (len(diff_code), diff_code))
            print(f"diff_code: {len(diff_code)} resample:{resample} ",end='')
            tdx_diff = get_tdx_exp_all_LastDF_DL(
                diff_code, dt=dl, end=end, ptype=ptype, filter=filter, power=power, lastp=lastp, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support)
            if tdx_diff is not None and len(tdx_diff) > 0:
                tdx_diff.rename(columns={'open': 'lopen'}, inplace=True)
                tdx_diff.rename(columns={'high': 'lhigh'}, inplace=True)
                tdx_diff.rename(columns={'close': 'lastp'}, inplace=True)
                tdx_diff.rename(columns={'low': 'llow'}, inplace=True)
                tdx_diff.rename(columns={'vol': 'lvol'}, inplace=True)
                tdx_diff.rename(columns={'amount': 'lamount'}, inplace=True)
                tdx_diff = tdx_diff.drop_duplicates(keep='first')  # 保留第一次出现的行
                wcdf = wcd.get_wencai_data(top_all.name)
                wcdf['category'] = wcdf['category'].apply(lambda x:x.replace('\r','').replace('\n',''))
                tdx_diff = cct.combine_dataFrame(tdx_diff, wcdf.loc[:, ['category']])

                if newdays is None or newdays > 0:
                    h5 = h5a.write_hdf_db(h5_fname, tdx_diff, table=h5_table, append=True)
                tdxdata = pd.concat([tdxdata, tdx_diff], axis=0)
                
    top_all = cct.combine_dataFrame(
        top_all, tdxdata, col=None, compare=None, append=False)
    top_all['llow'] = top_all.get('llow', 0)  # 列不存在时用默认0
    top_all = top_all[top_all['llow'] > 0]
    #20231110 add today topR
    #20250607 mod today topR
    if cct.get_day_istrade_date() and len(top_all) > 2:
        with timed_ctx("topR_compute_vec", warn_ms=100):
            now_time = cct.get_now_time_int()
            # Determine reference column
            if not cct.get_trade_date_status() or now_time < 915:
                ref_col = 'lasth2d'
            else:
                if (top_all['open'].iloc[-1] == top_all['lasto1d'].iloc[-1]) and (top_all['open'].iloc[0] == top_all['lasto1d'].iloc[0]):
                    ref_col = 'lasth2d'
                else:
                    ref_col = 'lasth1d'
            
            if ref_col in top_all.columns and 'topR' in top_all.columns:
                tr = top_all['topR'].values
                low = top_all['low'].values
                ref = top_all[ref_col].values
                
                if cct.get_work_time_duration():
                    op = top_all['open'].values
                    hi = top_all['high'].values
                    mask = (tr > 0) & ((low > ref) | ((ref < op * 0.99) & (hi > ref)))
                else:
                    hi = top_all['high'].values
                    cl = top_all['close'].values
                    op = top_all['open'].values
                    mask = (tr > 0) & (((low > ref) & (hi > ref)) | ((ref < op * 0.99) & (hi > ref) & (cl > ref)))
                
                top_all['topR'] = np.where(mask, (tr + 1.1), tr)
                top_all['topR'] = top_all['topR'].round(1)
    
    if 'llastp' not in top_all.columns:
        log.error("why not llastp in topall:%s" % (top_all.columns))

    co2int = ['boll','dff','ra','ral','fib','fibl','op','red','ra']    
    # co2int = ['boll','dff','ra','ral','fib','fibl','op', 'ratio','red','top5','top10','ra']    
    for col in co2int:
        if col in top_all.columns:
            top_all[col] = top_all[col].astype(int)
    topR_series = top_all.get('topR', pd.Series(0, index=top_all.index))
    # 四舍五入处理
    top_all['topR'] = topR_series.apply(lambda x: round(x, 1))

    # 2️⃣ 安全处理 df2 和 buy 列，缺失用默认值 0
    df2_series = top_all.get('df2', pd.Series(0, index=top_all.index))
    buy_series = top_all.get('buy', pd.Series(0, index=top_all.index))

    top_all['df2'] = df2_series
    top_all['buy'] = buy_series

    # 3️⃣ 安全计算 dff
    def safe_dff(x, y):
        if y == 0 or pd.isnull(x) or pd.isnull(y):
            return np.nan
        return round((x - y) / y * 100, 1)

    # 只在满足条件时计算
    if (top_all.get('dff', pd.Series([0]*len(top_all)))[0] == 0) \
            or (top_all.get('close', pd.Series([0]*len(top_all)))[0] == top_all.get('lastp1d', pd.Series([0]*len(top_all)))[0]):
        top_all['dff'] = list(map(safe_dff, top_all['buy'].values, top_all['df2'].values))
        

    for col in co2int:
        if col in tdxdata.columns:
            tdxdata[col] = tdxdata[col].astype(int)
    # top_all = cct.reduce_memory_usage(top_all)       
    if lastpTDX_DF is None:
        tdx_code = [co for co in codelist if co in tdxdata.index]
        tdxdata = tdxdata.loc[tdx_code]
        # tdxdata = cct.reduce_memory_usage(tdxdata)
        return top_all, tdxdata
    else:
        return top_all


def get_powerdf_to_all(top_all, powerdf):
    # codelist = top_all.index.tolist()
    # all_t = top_all.reset_index()
    # p_t = powerdf.reset_index()
    # top_dif['buy'] = (map(lambda x, y: y if int(x) == 0 else x, top_dif['buy'].values, top_dif['trade'].values))
    time_s = time.time()
    #     columns_list = ['ra', 'op', 'fib', 'ma5d','ma10d', 'ldate', 'ma20d', 'ma60d', 'oph', \
    #                     'rah', 'fibl', 'boll', 'kdj','macd','rsi', 'ma', 'vstd', 'lvolume', 'category', 'df2']
    # #    columns_list = [col for col in powerdf.columns if col in top_all.columns]
    #     if not 'boll' in top_all.columns:
    #         p_t = powerdf.loc[:,columns_list]
    #         # top_all.drop('column_name', axis=1, inplace=True)
    #         # top_all.drop([''], axis = 1, inplace = True, errors = 'ignore')
    #         top_all_co = top_all.columns
    #         top_all.drop([col for col in top_all_co if col in p_t], axis=1, inplace=True)
    #         top_all = top_all.merge(p_t, left_index=True, right_index=True, how='left')
    #         top_all = top_all.fillna(0)
    #     else:
    #         # p_t = powerdf.loc[:,'ra':'df2']
    #         po_inx = powerdf.index
    #         top_all.drop([inx for inx in powerdf.index  if inx in top_all.index], axis=0, inplace=True)
    #         # p_t = powerdf.iloc[:,57:69]
    #         # 'oph', u'rah', u'fibl', u'boll', u'kdj',u'macd', u'rsi', u'ma', u'vstd', u'lvolume', u'category'
    #         # top_all = top_all.merge(p_t, left_index=True, right_index=True, how='left')
    #         top_all = pd.concat([top_all, powerdf],axis=0)
    #         # top_dd =  cct.combine_dataFrame(top_temp[:10], top_end,append=True, clean=True)
    #         # for symbol in p_t.index:
    #         #     if symbol in top_all.index:
    #         #         # top_all.loc[symbol, 'oph':'category'] = p_t.loc[symbol, 'oph':'category']
    #         #         top_all.loc[symbol, 'ra':'df2'] = p_t.loc[symbol, 'ra':'df2']
    #     if 'time' not in top_all.columns:
    # #        top_all['time'] = cct.get_now_time_int()
    #         top_all['time'] = time.time()
    #     else:
    #         top_all = top_all.fillna(0)
    #         time_t = top_all[top_all.time <> 0].time[0] if len(top_all[top_all.time <> 0]) > 0 else 0
    #         if time.time() - time_t > ct.power_update_time:
    #             top_all['time'] = time.time()
    #     print "Pta:%0.2f"%(time.time()-time_s),
    return top_all


def get_tdx_exp_all_LastDF(codeList, dt=None, end=None, ptype='low', filter='n'):
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    if dt is not None and filter == 'n':
        if len(str(dt)) < 8:
            dl = int(dt) + changedays
            df = get_tdx_Exp_day_to_df(
                '999999', end=end).sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            df = get_tdx_Exp_day_to_df('999999', end=end).sort_index(ascending=False)
            dl = len(df[df.index >= dt]) + changedays
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s,%s" % (dt, dl))
        results = []
        for code in codeList:
            results.append(get_tdx_exp_low_or_high_price(code, dt, ptype, dl))
    elif dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt)
            df = get_tdx_Exp_day_to_df(
                '999999', end=end).sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[0]
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
            dl = len(get_tdx_Exp_day_to_df('999999', start=dt,
                                           end=end).sort_index(ascending=False))
            # dl = len(get_kdate_data('sh', start=dt))
            log.info("LastDF:%s,%s" % (dt, dl))
        results = cct.to_mp_run_async(
            get_tdx_exp_low_or_high_price, codeList, dt=dt, ptype=ptype, dl=dl, end=end)
      
        # print dt,ptype,dl,end
        # results=[]
        # for code in codelist:
        #     print(code,)
        #     result=get_tdx_exp_low_or_high_price(code, dt=dt, ptype=ptype, dl=dl, end=end)
        #     results.append(result)

    else:
        results = cct.to_mp_run_async(
            get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1)

        # results=[]
        # for code in codelist:
        #     print(code,)
        #     result=get_tdx_Exp_day_to_df(code, type='f', start=None, end=None, dl=None, newdays=1)
        #     results.append(result)

    # print results
#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.set_index('code')
    # df.loc[:, 'open':] = df.loc[:, 'open':].astype(float)
    # df.vol = df.vol.apply(lambda x: x / 100)
    log.info("get_to_mp:%s" % (len(df)))
    log.info(f"TDXTime:{time.time() - time_t:.3f}")
    if dt != None:
        print(("DFTDXE:%0.2f" % (time.time() - time_t)), end=' ')
    return df


def get_tdx_exp_all_LastDF_DL(codeList, dt=None, end=None, ptype='low', filter='n', power=False, lastp=False, newdays=None, dl=None, resample='d', showRunTime=True,detect_calc_support=False):
    """

    Function: get_tdx_exp_all_LastDF_DL

    Summary: TDX init Day by Mp

    # Examples: InsertHere

    Attributes: 

        @param (codeList):InsertHere

        @param (dt) default=None: InsertHere

        @param (end) default=None: InsertHere

        @param (ptype) default='low': InsertHere

        @param (filter) default='n': InsertHere

        @param (power) default=False: InsertHere

        @param (lastp) default=False: InsertHere

        @param (newdays) default=None: InsertHere

        @param (dl) default=None: InsertHere

        @param (resample) default='d': InsertHere

        @param (showRunTime) default=True: InsertHere

    Returns: InsertHere

    """
    time_t = time.time()
    # df = rl.get_sina_Market_json(market)
    # code_list = np.array(df.code)
    # if type==0:
    #     results = cct.to_mp_run(get_tdx_day_to_df_last, codeList)
    # else:
    end = cct.day8_to_day10(end)
    if dt is not None and filter == 'n':
        if len(str(dt)) < 8:
            dl = int(dt)
            dt = None
            log.info("LastDF:%s,%s" % (dt, dl))
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            elif len(str(dt)) == 10:
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            else:
                log.warning('dt :%s error dl=60,dt->None' % (dt))
                dl = 30
                dt = None
            log.info("LastDF:%s,%s" % (dt, dl))
        results = cct.to_mp_run_async(
            get_tdx_exp_low_or_high_power, codeList, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support)

        # results = get_tdx_exp_low_or_high_price(codeList[0], dt,ptype,dl)

        # results=[]
        # for code in codeList:
        #    print(code,)
        #    results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support))
           # results.append(get_tdx_exp_low_or_high_price(code, dt, ptype, dl,end,power,lastp,newdays))
        # results = get_tdx_exp_low_or_high_price(codeList[0], dt,ptype,dl)))

    elif dt is not None:
        if len(str(dt)) < 8:
            dl = int(dt)
#            dt = int(dt)
            # dt = None
            # df = get_tdx_Exp_day_to_df('999999',end=end).sort_index(ascending=False)
            # dt = get_duration_price_date('999999', dt=dt,ptype=ptype,df=df)
            # dt = df[df.index <= dt].index.values[0]
#            dt=get_duration_Index_date('999999',dl=dt)
            log.info("Codelist:%s LastDF:%s,%s" % (len(codeList),dt, dl))
            dt = None
        else:
            if len(str(dt)) == 8:
                dt = cct.day8_to_day10(dt)
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            elif len(str(dt)) == 10:
                df = get_tdx_Exp_day_to_df(
                    '999999', end=end).sort_index(ascending=False)
                dl = len(df[df.index >= dt])
            else:
                log.warning('dt :%s error dl=60,dt->None' % (dt))
                dl = 30
                dt = None
            log.info("LastDF:%s,%s" % (dt, dl))
        if dl is not None and end is not None:
            dl = dl + cct.get_today_duration(end, cct.get_today())
#            print cct.get_today_duration(end,cct.get_today())

        if len(codeList) > 200:
            log.debug("Codelist:%s LastDF:%s,%s" % (len(codeList),dt, dl))
            
            results = cct.to_mp_run_async(
                get_tdx_exp_low_or_high_power, codeList, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample,detect_calc_support=detect_calc_support)
                
            
            # codeList = ['300055','002443']
            # # results=[]
            # # from tqdm import tqdm
            # # for inx in tqdm(list(range(len(codeList))),unit='%',mininterval=ct.tqdm_mininterval,unit_scale=True,total=len(codeList),ncols=ct.ncols):
            # #     code = codeList[inx]
            # #     print(code,)
            # #     results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample))
                
            # results=[]
            # for code in codeList:
            #    print(code,)
            #    results.append(get_tdx_exp_low_or_high_power(code, dt=dt, ptype=ptype, dl=dl, end=end, power=power, lastp=lastp, newdays=newdays, resample=resample))

        else:
            results = []
            ts = time.time()
            for code in codeList:
                log.debug(f'codeList: {len(codeList)}: idx: {codeList.index(code)} code: {code} dt: {dt}')
                results.append(get_tdx_exp_low_or_high_power(code, dt, ptype, dl, end, power, lastp, newdays, resample,ct.lastdays * 3,detect_calc_support))
            # print("tdxdataT:%s"%(round(time.time()-ts,2)),)
#        print round(time.time()-ts,2),
        # print dt,ptype,dl,end
        # for code in codelist:
        #     print code,
        #     print get_tdx_exp_low_or_high_price('600654', dt, ptype, dl,end)

    else:
        dl = None
        # results = cct.to_mp_run_async(
        #     get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1)
        results=[]
        for code in codeList:
           # print(code)
           results.append(get_tdx_Exp_day_to_df, codeList, type='f', start=None, end=None, dl=None, newdays=1,detect_calc_support=detect_calc_support)
    # print results
#    df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    df = pd.DataFrame(results)
    df = df.dropna(how='all')
    if len(df) > 0 and 'code' in df.columns:
        df = df.set_index('code')
        # df.loc[:, 'open':'amount'] = df.loc[:, 'open':'amount'].astype(float)
    # df.vol = df.vol.apply(lambda x: x / 100)
    log.info(f"Get_to_mp: {len(df)} TDXTime:{time.time() - time_t:.3f}")

    # if power and 'op' in df.columns:
    #     df=df[df.op >10]
    #     df=df[df.ra < 11]
    # print "op:",len(df),
    if showRunTime and dl != None:
        global initTdxdata
        if initTdxdata > 2:
            print("All_OUT:%s " % (initTdxdata), end=' ')
        print(("DLTDXE:%0.2f" % (time.time() - time_t)), end=' ')
    return df


# def get_tdx_all_StockList_DF(code_list, dayl=1, type=0):
#     time_t = time.time()
#     # df = rl.get_sina_Market_json(market)
#     # code_list = np.array(df.code)
#     # log.info('code_list:%s' % len(code_list))
#     results = cct.to_mp_run_async(
#         get_tdx_day_to_df_last, code_list, dayl, type)
#     log.info("get_to_mp_op:%s" % (len(results)))
#     # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
#     # df = df.set_index('code')
#     # print df[:1]
#     print "t:", time.time() - time_t
#     return results


# def get_tdx_all_day_DayL_DF(market='cyb', dayl=1):
#     time_t = time.time()
#     df = rl.get_sina_Market_json(market)
#     code_list = np.array(df.code)
#     log.info('code_list:%s' % len(code_list))
#     results = cct.to_mp_run_async(get_tdx_day_to_df_last, code_list, dayl)
#     log.info("get_to_mp_op:%s" % (len(results)))
#     # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
#     # df = df.set_index('code')
#     # print df[:1]

#     # print len(df),df[:1]
#     # print "<2015-08-25",len(df[(df.date< '2015-08-25')])
#     # print "06-25-->8-25'",len(df[(df.date< '2015-08-25')&(df.date >
#     # '2015-06-25')])
#     print "t:", time.time() - time_t
#     return results


def get_tdx_search_day_DF(market='cyb'):
    time_t = time.time()
    df = rl.get_sina_Market_json(market)
    code_list = np.array(df.code)
    log.info('code_list:%s' % len(code_list))
    results = cct.to_mp_run(get_tdx_day_to_df, code_list)
    log.info("get_to_mp_op:%s" % (len(results)))
    # df = pd.DataFrame(results, columns=ct.TDX_Day_columns)
    # df = df.set_index('code')
    # print df[:1]

    # print len(df),df[:1]
    # print "<2015-08-25",len(df[(df.date< '2015-08-25')])
    # print "06-25-->8-25'",len(df[(df.date< '2015-08-25')&(df.date >
    print("t:", time.time() - time_t)
    return results

period_type_dic={'w':'W-FRI','m':'BM'}

def get_tdx_stock_period_to_type_in(df, period_day='W-FRI', periods=5, ncol=None, ratiodays=False):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """
    #快速日期处理
    #https://www.likecs.com/show-204682607.html
    stock_data = df.copy()
    period_type = period_type_dic[period_day.lower()]
    if 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
    stock_data['date'] = stock_data.index
    lastday = str(stock_data.date.values[-1])[:10]
    lastday2 = str(stock_data.date.values[-2])[:10]
    # duration_day = get_today_duration(lastday2,lastday)
    # print("duration:%s"%(duration_day))
    
    # if duration_day > 3:
    #     if 'date' in stock_data.columns:
    #         stock_data = stock_data.drop(['date'], axis=1)
    #     return stock_data.reset_index()
    
    # indextype = True if stock_data.index.dtype == 'datetime64[ns]' else False
    # if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
    #     stock_data = stock_data[stock_data.index < cct.get_today()]

    if stock_data.index.name == 'date':
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    elif 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
        stock_data.sort_index(ascending=True, inplace=True)
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    # else:
    #     log.error("index.name not date,pls check:%s" % (stock_data[:1]))

    period_stock_data = stock_data.resample(period_type).last()
    # period_stock_data['percent']=stock_data['percent'].resample(period_type,how=lambda x:(x+1.0).prod()-1.0)
    # print stock_data.index[0],stock_data.index[-1]
    # period_stock_data.index =
    # pd.DatetimeIndex(start=stock_data.index.values[0],end=stock_data.index.values[-1],freq='BM')

    period_stock_data['open'] = stock_data[
        'open'].resample(period_type).first()
    period_stock_data['high'] = stock_data[
        'high'].resample(period_type).max()
    period_stock_data['low'] = stock_data[
        'low'].resample(period_type).min()

    lastWeek1 = str(period_stock_data['open'].index.values[-1])[:10]
    lastweek2 = str(period_stock_data['open'].index.values[-2])[:10]
    if ratiodays:
        if period_day == 'W-FRI':
            # print(lastWeek1,lastweek2,lastday,lastday2)
            duratio = int(str(datetime.datetime.strptime(lastWeek1, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[0])
            ratio_d =(5-(duratio%5))/5
            # print("ratio_d:%s %s"%(ratio_d,lastday))
        elif period_day.find('W') >= 0:
            # print(lastWeek1,lastweek2,lastday,lastday2)
            duratio = int(str(datetime.datetime.strptime(lastday, '%Y-%m-%d').date() - datetime.datetime.strptime(lastweek2, '%Y-%m-%d').date())[0])
            ratio_d =(duratio)/5
            # print("ratio_d:%s %s"%(ratio_d,lastday))
        elif period_day == 'BM':
            # daynow = '2023-04-26'
            # lastday = '2023-04-23'
            # print(lastWeek1,lastweek2,lastday,lastday2)
            # print((str(datetime.datetime.strptime(lastWeek1, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[:2]))
            duratio = int(str(datetime.datetime.strptime(lastday, '%Y-%m-%d').date() - datetime.datetime.strptime(lastweek2, '%Y-%m-%d').date())[:2])
            ratio_d =(30-(duratio%30))/30
            # print("ratio_d:%s %s dura:%s"%(ratio_d,lastday,duratio))
        elif period_day.find('M') >= 0:
            ratio_d = 1
            
    else:
        ratio_d = 1
        print(ratio_d)
        
    if ncol is not None:
        for co in ncol:
            period_stock_data[co] = stock_data[co].resample(period_type).sum()
            if ratiodays:
                period_stock_data[co] = period_stock_data[co].apply(lambda x: round(x / ratio_d, 1))
                
    # else:
    period_stock_data['amount'] = stock_data[
        'amount'].resample(period_type).sum()
    period_stock_data['vol'] = stock_data[
        'vol'].resample(period_type).sum()
    if ratiodays:
        period_stock_data['amount'] = period_stock_data['amount'].apply(lambda x: round(x / ratio_d, 1))
        period_stock_data['vol'] = period_stock_data['vol'].apply(lambda x: round(x / ratio_d, 1))
                
    # period_stock_data['turnover']=period_stock_data['vol']/(period_stock_data['traded_market_value'])/period_stock_data['close']
    period_stock_data.index = stock_data['date'].resample(period_type).last().index
    # print period_stock_data.index[:1]
    if 'code' in period_stock_data.columns:
        period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data = period_stock_data.dropna()
    # period_stock_data.reset_index(inplace=True)
    # period_stock_data.set_index('date',inplace=True)
    # print period_stock_data.columns,period_stock_data.index.name
    # and period_stock_data.index.dtype != 'datetime64[ns]')
    
    # if not indextype and period_stock_data.index.name == 'date':
    #     # stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    #     period_stock_data.index = [str(x)[:10] for x in period_stock_data.index]
    #     period_stock_data.index.name = 'date'
    # else:
    #     if 'date' in period_stock_data.columns:
    #         period_stock_data = period_stock_data.drop(['date'], axis=1)
    
    if 'date' in period_stock_data.columns:
            period_stock_data = period_stock_data.drop(['date'], axis=1)
    return period_stock_data.reset_index()

def get_tdx_stock_period_to_type(stock_data, period_day='w', periods=5, ncol=None):
    """
    极限优化版本：
    - 避免重复 datetime 解析和排序
    - 使用 loc 索引切片
    - 分列聚合 numeric 与 first/last separately
    """

    period_type = period_type_dic.get(period_day.lower(), period_day)

    # 1️⃣ 如果 index 已经是 DatetimeIndex 且已排序，可跳过

    if not isinstance(stock_data.index, pd.DatetimeIndex):
        stock_data.index = pd.to_datetime(stock_data.index)
        stock_data = stock_data.sort_index()

    # 2️⃣ 当天未收盘剔除今日数据
    now_time = cct.get_now_time_int()
    is_trade_day = cct.get_trade_date_status()
    is_work_day = cct.get_work_day_status()
    if 915 < now_time < 1500 and is_trade_day and is_work_day:
        stock_data = stock_data.loc[stock_data.index < pd.Timestamp(cct.get_today())]

    # 3️⃣ 数值列单独 sum
    numeric_cols = ['vol', 'amount']
    if ncol:
        numeric_cols += ncol
    numeric_cols = [col for col in numeric_cols if col in stock_data.columns]

    numeric_agg = stock_data[numeric_cols].resample(period_type, label='right', closed='right').sum()

    # 4️⃣ first/last/max/min 列 separately
    ohlc_cols = ['open', 'high', 'low', 'close']
    ohlc_cols = [col for col in ohlc_cols if col in stock_data.columns]
    ohlc_agg = stock_data[ohlc_cols].resample(period_type, label='right', closed='right').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    })

    # 5️⃣ code 列 last
    code_agg = None
    if 'code' in stock_data.columns:
        code_agg = stock_data['code'].resample(period_type, label='right', closed='right').last()

    # 6️⃣ 合并所有结果
    dfs = [ohlc_agg, numeric_agg]
    if code_agg is not None:
        dfs.append(code_agg)
    period_stock_data = pd.concat(dfs, axis=1)

    # 7️⃣ 清理无效数据
    if 'code' in period_stock_data.columns:
        period_stock_data = period_stock_data.loc[period_stock_data['code'].notnull()]
    period_stock_data = period_stock_data.dropna(how='all')  # 仅删除全空行

    return period_stock_data

def get_tdx_stock_period_to_type_slow(stock_data, period_day='w', periods=5, ncol=None):
    """
    将日K数据转换为周K/月K等周期数据，保留必要列，支持 sum 聚合。
    """
    # 1️⃣ 周期类型
    period_type = period_type_dic.get(period_day.lower(), period_day)

    # 2️⃣ 缓存交易日判断
    now_time = cct.get_now_time_int()
    is_trade_day = cct.get_trade_date_status()
    is_work_day = cct.get_work_day_status()
    
    if 915 < now_time < 1500 and is_trade_day and is_work_day:
        stock_data = stock_data[stock_data.index < cct.get_today()]

    # 3️⃣ 确保索引为 datetime
    stock_data.index = pd.to_datetime(stock_data.index)
    stock_data = stock_data.sort_index()

    # 4️⃣ 构建 agg_dict
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'vol': 'sum',
        'amount': 'sum'
    }
    if 'code' in stock_data.columns:
        agg_dict['code'] = 'last'
    if ncol:
        agg_dict.update({co: 'sum' for co in ncol})

    # 5️⃣ resample 并聚合
    period_stock_data = stock_data.resample(period_type, label='right', closed='right').agg(agg_dict)

    # 6️⃣ 清理无效数据
    if 'code' in period_stock_data.columns:
        period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data = period_stock_data.dropna()

    return period_stock_data

def get_tdx_stock_period_to_type_ok(stock_data, period_day='w', periods=5, ncol=None):
    """
    将股票日K数据转换为周K/月K等周期数据。

    Args:
        stock_data (pd.DataFrame): 日K数据，必须包含 open, high, low, vol, amount 列。
        period_day (str): 周期类型，'w' 周，'m' 月等。
        periods (int): 使用周期数，暂未使用。
        ncol (list|None): 附加需要求和的列，默认 None。

    Returns:
        pd.DataFrame: resample 后的周期数据。
    """
    # 1. 确定周期类型
    period_type = period_type_dic.get(period_day.lower(), period_day)

    # 2. 检查索引类型
    indextype = stock_data.index.dtype == 'datetime64[ns]'

    # 3. 工作日过滤，若在交易时段且今天已有数据，则排除当天
    if 915 < cct.get_now_time_int() < 1500 and cct.get_trade_date_status() and cct.get_work_day_status():
        stock_data = stock_data[stock_data.index < cct.get_today()]

    # 4. 确保索引为 datetime
    stock_data['date'] = stock_data.index
    if stock_data.index.name != 'date':
        if 'date' in stock_data.columns:
            stock_data = stock_data.set_index('date')
        else:
            log.error(f"index.name not date, pls check: {stock_data[:1]}")
    stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    stock_data = stock_data.sort_index(ascending=True)

    # 5. 生成周期数据
    agg_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'vol': 'sum',
        'amount': 'sum'
    }
    if 'code' in stock_data.columns:
        agg_dict['code'] = 'last'
    
    if ncol:
        for co in ncol:
            agg_dict[co] = 'sum'

    period_stock_data = stock_data.resample(period_type).agg(agg_dict)

    # 7. 设置索引为周期最后一天
    period_stock_data.index = stock_data['date'].resample(period_type).last().index

    # 8. 清理无效数据
    if 'code' in period_stock_data.columns:
        period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data = period_stock_data.dropna()

    # 9. 如果原始索引不是 datetime，则保留原 date 列作为索引
    if not indextype and period_stock_data.index.name == 'date' and 'date' in period_stock_data.columns:
        period_stock_data.index = period_stock_data['date']
        period_stock_data = period_stock_data.drop(['date'], axis=1)
    else:
        if 'date' in period_stock_data.columns:
            period_stock_data = period_stock_data.drop(['date'], axis=1)

    return period_stock_data



'''
def usage(p=None):
    import timeit
#     print """
# for example :
# python %s 999999 20070101 20070302
# python %s -t txt 999999 20070101 20070302
#     """ % (p, p, p)
    status = None
    run = 1
    df = rl.get_sina_Market_json('cyb')
    df = df.set_index('code')
    codelist = df.index.tolist()
    duration_date = 20160101
    ptype = 'low'
    dt = duration_date
    # codeList='999999'
    print("")
    for x in range(1):
        if len(str(dt)) != 8:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s" % dt)
        else:
            dt = int(dt) + changedays
        # print dt
        # top_now = rl.get_market_price_sina_dd_realTime(df, vol, vtype)
        # get_tdx_exp_all_LastDF_DL(codelist,dt=duration_date,ptype=ptype)
        split_t = timeit.timeit(lambda: get_tdx_exp_all_LastDF_DL(
            codelist, dt=duration_date, ptype=ptype), number=run)
        # split_t = timeit.timeit(lambda : get_tdx_all_day_LastDF(codelist,dt=duration_date,ptype=ptype), number=run)
        # split_t = timeit.timeit(lambda: get_tdx_day_to_df_last(codeList, 1, type, dt,ptype),number=run)
        print(("df Read:", split_t))

        dt = duration_date
        if len(str(dt)) != 8:
            dl = int(dt) + changedays
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dt = get_duration_price_date('999999', dt=dt, ptype=ptype, df=df)
            dt = df[df.index <= dt].index.values[changedays]
            log.info("LastDF:%s" % dt)
        else:
            df = get_tdx_day_to_df('999999').sort_index(ascending=False)
            dl = len(get_tdx_Exp_day_to_df('999999', start=dt)) + changedays
            dt = cct.day8_to_day10(dt)

        # print dt,dl
        # strip_tx = timeit.timeit(lambda: get_tdx_exp_low_or_high_price(codeList, dt, ptype, dl), number=run)
        strip_tx = timeit.timeit(lambda: get_tdx_exp_all_LastDF_DL(
            codelist, dt=duration_date, ptype=ptype), number=run)
        # strip_tx = timeit.timeit(lambda : get_tdx_exp_all_LastDF(codelist, dt=duration_date, ptype=ptype), number=run)
        print(("ex Read:", strip_tx))
'''

def write_to_all():
    st = cct.cct_raw_input("will to Write Y or N:")
    if str(st) == 'y':
        Write_market_all_day_mp('all')
    else:
        print("not write")


def python_resample(qs, xs, rands):
    n = qs.shape[0]
    lookup = np.cumsum(qs)
    results = np.empty(n)

    for j in range(n):
        for i in range(n):
            if rands[j] < lookup[i]:
                results[j] = xs[i]
                break
    return results

    # import timeit
    # n = 100
    # xs = np.arange(n, dtype=np.float64)
    # qs = np.array([1.0 / n, ] * n)
    # rands = np.random.rand(n)
    # from numba.decorators import autojit
    # print(timeit.timeit(lambda: python_resample(qs, xs, rands), number=number))
    # # print timeit.timeit(lambda:cct.run_numba(python_resample(qs, xs,
    # # rands)),number=number)
    # print(timeit.timeit(lambda: autojit(lambda: python_resample(qs, xs, rands)), number=number))
    # # print timeit.timeit(lambda:cct.run_numba(python_resample(qs, xs,
    # # rands)),number=number)

def safe_join(df, df_aug):
    # 清除重复列
    overlap = df.columns.intersection(df_aug.columns)
    if len(overlap) > 0:
        df_aug = df_aug.drop(columns=list(overlap))
    return df.join(df_aug)

def tdx_profile_test_tdx():
    resample = 'd'
    code = '000002'
    dl = ct.Resample_LABELS_Days[resample]
    # -----------------------
    # 原始方法性能测试
    # -----------------------
    time_s = time.time()
    for _ in range(10):
        df = get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        # df = get_tdx_Exp_day_to_df(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        # df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days[resample],resample=resample) 
        
        # 原始扩展方法
        # df_temp = {}
        # lastdays = 12
        # for da in range(1, lastdays+1):
        #     df_temp[f'lasth{da}d'] = df['high'][-da]
        #     df_temp[f'lastp{da}d'] = df['close'][-da]
        #     df_temp[f'lastv{da}d'] = df['vol'][-da]
        # df_repeat = pd.DataFrame([df_temp]).loc[np.repeat(0, len(df))].reset_index(drop=True)
        # df_orig = pd.concat([df.reset_index(), df_repeat], axis=1)
    print("原始方法 time: %s s" % round(time.time() - time_s, 2))

    # -----------------------
    # 优化方法性能测试
    # -----------------------
    time_s = time.time()
    for _ in range(10):
        # df = get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        # df = get_tdx_Exp_day_to_df(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
        df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days[resample],resample=resample) 


        # # 优化扩展方法
        # lastdays = 12
        # df_aug = build_aug_from_last_row(df, lastdays=lastdays)
        # # df_opt = df.join(df_aug)
        # df_opt = safe_join(df, df_aug)
        # df_opt = df_opt.loc[:, ~df_opt.columns.duplicated()]
        # df_opt = df_opt.sort_index(ascending=True)

    print("优化方法 time: %s s" % round(time.time() - time_s, 2))
    print("done")

def tdx_profile_test():
    resample = 'd'
    code='000002'
    dl=ct.Resample_LABELS_Days[resample]
    time_s=time.time()
    for i in range(10):
        df = get_tdx_exp_low_or_high_power(code, dl=dl, end=None, ptype='low', power=False, resample=resample)
    print("time:%s"%( round((time.time()-time_s),2) ))
    print("done")
if __name__ == '__main__':
    # import sys
    # import timeit

    from docopt import docopt
    # log = LoggerFactory.log
    log = LoggerFactory.getLogger()
    args = docopt(cct.sina_doc, version='sina_cxdn')
    # print args,args['-d']
    if args['-d'] == 'debug':
        log_level = LoggerFactory.DEBUG
    elif args['-d'] == 'info':
        log_level = LoggerFactory.INFO
    else:
        log_level = LoggerFactory.INFO
    # log_level = LoggerFactory.DEBUG if args['-d']  else LoggerFactory.ERROR
    # log_level = LoggerFactory.DEBUG
    log.setLevel(log_level)
    # tdx_profile_test_tdx()
        
    resample = 'd'
    code = '002151'
    # dm = sina_data.Sina().market('all').loc['000002']
    # get_tdx_append_now_df_api_tofile(code, dm=None, newdays=0,detect_calc_support=False)

    # dm_index = sina_data.Sina().get_stock_list_data(tdx_index_code_list,index=True)
    # for inx in tdx_index_code_list:
    #     get_tdx_append_now_df_api_tofile(inx,dm=dm_index)
    # write_market_index_to_df()
    # Write_market_all_day_mp()


    dd = get_tdx_Exp_day_to_df(code, dl=1) 
    dd2 = get_tdx_Exp_day_to_df(code, dl=480,resample='m')
    dd3 = get_tdx_Exp_day_to_df(code, dl=60,resample='d')
    import ipdb;ipdb.set_trace()

    duration = cct.get_today_duration(dd.date,tdx=True) if dd is not None and len(dd) > 5 else -1
    df = get_tdx_Exp_day_to_df_lday(code, dl=1) 
    dm = get_tdx_Exp_day_to_df_lday(code, dl=480,resample='m')
    print(f'df_txt:{dd} df_day:{df}')
    import ipdb;ipdb.set_trace()

    # code_l=['920274','300342','300696', '603091', '605167']
    # # code_l=['920274']
    # df=get_tdx_exp_all_LastDF_DL(code_l, dt=ct.Resample_LABELS_Days['d'],filter='y', resample='d')
    # print(f'{df[:2]} ')
    # import ipdb;ipdb.set_trace()

    # time_s = time.time()
    # signal_dict = extract_eval_signal_dict(df,lastdays=cct.compute_lastdays)
    # print(f'time: {time.time() - time_s :.8f}  check code: {code_l} signal_dict:{(signal_dict)} ')
    # time_s = time.time()
    # all_features = extract_all_features(df,lastdays=cct.compute_lastdays)
    # print(f'time: {time.time() - time_s :.8f}  check code: {code_l} all_features:{len(all_features)} ')
    # sina = get_sina_data_df('920274')

    # realtime_signal = evaluate_realtime_signal_tick(sina,all_features)
    # print(f'evaluate_realtime_signal_tick: {realtime_signal}')

    # import ipdb;ipdb.set_trace()

    # time_s = time.time()
    # generate_df_vect_daily_features = generate_df_vect_daily_features(df,lastdays=cct.compute_lastdays)
    # # pd.DataFrame(generate_df_vect_daily_features).set_index('code')
    # print(f'time: {time.time() - time_s :.8f}  check code: {code_l} generate_df_vect_daily_features:{len(generate_df_vect_daily_features)} ')

    # (get_tdx_Exp_day_to_df_performance(code,dl=ct.Resample_LABELS_Days[resample],resample=resample))
    code = '920101'
    code = '399001'
    df2 = get_tdx_Exp_day_to_df(code,dl=1,newdays=0)
    # df2 = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['m'],resample='m' )
    import ipdb;ipdb.set_trace()
    df=get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days[resample],resample=resample)
    
    # df=get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days[resample],resample=resample)
    df=get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days[resample],resample=resample)
    
    import ipdb;ipdb.set_trace()
    # compute_lastdays_percent_profile(df, lastdays=5)
    evtdf = evaluate_trading_signal(df)
    print(f"evtdf: {evtdf[['open', 'close','upper','EVAL_STATE','trade_signal']].tail(60)}")
    import ipdb;ipdb.set_trace(),

    print(f'check code: {code}  boll_Signal: {df.boll_signal}')

    df=(getSinaAlldf('all'))
    print(f'check code: {df.loc["920023"]}  ')

    # tdx_profile_test()
    # pyprof2calltree -k -i tdx.profile
    # # import cProfile
    # from cProfile import Profile
    # prof = Profile()
    # prof.enable()
    # # ... 执行代码 ...
    # prof.run('tdx_profile_test()')

    # prof.disable()
    # stats = prof.getstats()
    # cct.timeit_time(get_tdx_exp_low_or_high_power('000002', dl=60, end=None, ptype='low', power=False, resample='d'),num=5)
    # import ipdb;ipdb.set_trace()
    # sys.exit()
    # time_s=time.time()
    # check_tdx_Exp_day_duration('all')
    # print("use time:%s"%(time.time()-time_s))
    # import ipdb;ipdb.set_trace()
    # code='399001'
    # code='000862'
    # code='000859'
    # code='002870'
    # code='603000'
    # code='002387'
    # code='603888'
    # code='000686'
    # code='600776'
    # code='000837'
    # code='000750'
    # code='000752'
    # print write_tdx_tushare_to_file('300055')
    # print write_tdx_sina_data_to_file('300055')
    '''
    import ipdb;ipdb.set_trace()
    # df=search_Tdx_multi_data_duration()
    #test Jupyter bug
    code_list = sina_data.Sina().market('all').index.tolist()
    df=search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start='20150501', end=None, freq=None, col=None, index='date')
    code_uniquelist=df.index.get_level_values('code').unique()
    code_select = code_uniquelist[random.randint(0,len(code_uniquelist)-1)]
    round(time.time()-time_s,2),df.index.get_level_values('code').unique().shape,code_select,df.loc[code_select][:2]
    df = df.drop_duplicates()
    '''

    # Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300, rewrite=True)
    # import ipdb;ipdb.set_trace()
    
    # code='603603'
    # df=get_tdx_append_now_df_api_tofile(code)
    # import ipdb;ipdb.set_trace()
    
    code='001896' #豫能控股
    code='002594' #byd
    code='601628' #中国人寿
    code='601015' #陕西黑猫
    code='000988' #华工科技
    code='300346' #南大光电
    code='600499' #科达制造
    code='600438' #隆基绿能
    code='300798' #如意集团
    # code='002828'  
    # code='002176' #江特电机
    code='601127'  #捷荣技术
    code='002620'  #捷荣技术
    code='600240'  #捷荣技术
    # code='300290'  #捷荣技术
    # code='300826'  #测绘股份
    # code='002251'  #步步高
    # code='002512'  #达华智能

    # get_index_percd()

    # wri_index = cct.cct_raw_input("If append  Index 399001... data to tdx[y|n]:")
    # if wri_index == 'y':
    #     for inx in tdx_index_code_list:
    #         get_tdx_append_now_df_api_tofile(inx)

    # code='688106' #科创信息
    # code='399001'
    code = '002238'
    code = '002786'
    code = '600863'
    # code = '600190'
    # code = '600240'
    # code = '600890'
    # code = '002865'

    '''

    Date              Open        High         Low       Close   Volume
    2010-01-04   38.660000   39.299999   38.509998   39.279999  1293400   
    2010-01-05   39.389999   39.520000   39.029999   39.430000  1261400   
    2010-01-06   39.549999   40.700001   39.020000   40.250000  1879800   
    2010-01-07   40.090000   40.349998   39.910000   40.090000   836400   
    2010-01-08   40.139999   40.310001   39.720001   40.290001   654600   
    2010-01-11   40.209999   40.520000   40.040001   40.290001   963600   
    2010-01-12   40.160000   40.340000   39.279999   39.980000  1012800   
    2010-01-13   39.930000   40.669998   39.709999   40.560001  1773400   
    2010-01-14   40.490002   40.970001   40.189999   40.520000  1240600   
    2010-01-15   40.570000   40.939999   40.099998   40.450001  1244200 
    df = pd.read_clipboard(parse_dates=['Date'], index_col=['Date'])
    logic = {'Open'  : 'first',
             'High'  : 'max',
             'Low'   : 'min',
             'Close' : 'last',
             'Volume': 'sum'}

    dfw = df.resample('W').apply(logic)
    # set the index to the beginning of the week
    dfw.index = dfw.index - pd.tseries.frequencies.to_offset("6D")
    '''
    
    sh_index = '300696'
    dd = get_tdx_Exp_day_to_df(sh_index, dl=1)
    print(f'dd : {dd} ')
    # dd=pd.read_clipboard(parse_dates=['Date'], index_col=['Date'])
    code='601028'
    # df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['d'], end=None, newdays=0, resample='d')
    # print(df.loc[:,df.columns[df.columns.str.contains('perc')]][-1:])
    # import ipdb;ipdb.set_trace()
    
    # df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['w'],resample='w',lastday=None )
    # import ipdb;ipdb.set_trace()



    df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['d'],resample='d',lastday=None )
    
    df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['w'],resample='w',lastday=None )
    print(f"{code} : {df.loc[:,['boll','lastp1d','ma51d','lastp2d','ma52d','lastp3d','ma53d','lasth1d','lasth2d','lasth3d']][-1:].values}")
    print(f"{code} 'resist','support' : {df.loc[:,['resist','support']][-1:].values}")
    print(f'd per1d:{df.per1d[0]}  per2d:{df.per2d[0]}  per3d:{df.per3d[0]}  per4d:{df.per4d[0]}  per5d:{df.per5d[0]}  ')
    cols = [
        'lasto1d','lastl1d','lastp1d','per1d',
        'lasto2d','lastl2d','lastp2d','per2d',
        'lasto3d','lastl3d','lastp3d','per3d',
        'lasto4d','lastl4d','lastp4d','per4d',
        'lasto5d','lastl5d','lastp5d','per5d'
        # 'lasto6d','lastl6d','lastp6d','per6d'
    ]
    df_cols_only = df.loc[:, cols]
    print(df_cols_only[-1:].T)
    df_checked = check_conditions_auto(df_cols_only[-1:])
    print(f'df_checked print(df.MainU): {df.MainU[-1:]}')


    # df = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['3d'],resample='3d',lastday=None )
    # print(f"{code} : {df.loc[:,['boll','lastp1d','ma51d','lastp2d','ma52d','lastp3d','ma53d','lasth1d','lasth2d','lasth3d']][-1:].values}")
    # print(f"{code} 'resist','support' : {df.loc[:,['resist','support']][-1:].values}")
    # print(f'3d per1d:{df.per1d[0]}  per2d:{df.per2d[0]}  per3d:{df.per3d[0]}  per4d:{df.per4d[0]}  per5d:{df.per5d[0]}  ')
    # df_cols_only2 = df.loc[:, cols]
    # print(df_cols_only2[-1:])
    # print(f'print(df.MainU): {df.MainU[-1:]}')
    
    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days['w'],resample='w')
    df2 = get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days['w'],resample='w')
    print(df2[['bull_f','bull_s','bullbreak','has_first','status','hold_d','obs_d','resist','support']].tail(10))
    print(f"{code} 'resist','support' : {df2.loc[:,['resist','support']][-1:].values}")
    print(f' d: {ct.Resample_LABELS_Days["w"] } df.ma60d : {df2.ma60d[-3:]} \n\n')
    # print(df[-3:],df[-1:])
    print(df2.loc[:,df2.columns[df2.columns.str.contains('perc')]][-1:])
    print(f'df lastp1d:{df[:2].lastp1d}')
    print(f'3d per1d:{df.per1d[0]}  per2d:{df.per2d[0]}  per3d:{df.per3d[0]}  per4d:{df.per4d[0]}  per5d:{df.per5d[0]}  ')
    # df = get_tdx_Exp_day_to_df(code, dl=1)
    # 
    # dm = get_sina_data_df(code)
    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')

    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end='20230925', newdays=0, resample='d')


    # df = get_tdx_Exp_day_to_df(code,dl=200, end=None, newdays=0, resample='3d')

    # df = get_tdx_Exp_day_to_df(code,dl=60, start='20230925',end=None, newdays=0, resample='d')
    #get_tdx_exp_all_LastDF_DL() get_tdx_exp_low_or_high_power
    code='600602'
    code='603038'
    code='833171'
    code='688652'
    code='301260'
    code='603518'
    code='002082'
    code='002250'
    code='300084'
    # code='837748'
    # code='920799'
    code='002268'
    # code='603212'
    code='002670'
    code='600110'
    code='600744'
    code='600111'
    code='600392'
    code='688189'
    code='300085'
    code_l=['300696', '603091', '605167']
    df=get_tdx_exp_all_LastDF_DL(code_l, dt='80',filter='y', resample='d')
    print(f'{df[:2]} ')
    print(f'check code: {code_l}  boll_Signal: {df.boll_signal}')
    # write_to_all()

    # # dd = compute_ma_cross(dd,resample='d')
    # print(get_tdx_stock_period_to_type(dd)[-5:])
    # df = get_tdx_append_now_df_api_tofile('001236')
    # df = get_tdx_append_now_df_api('001236')
    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_day,resample='d' )
    df2 = get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days['d'],resample='d' )
    print(f'df2 lastp1d:{df2.lastp1d}')
    print(f'code:{code}')
    print(f'topR-d:{df2.topR} red:{df2.red} lastdu4:{df2.lastdu4} boll:{df2.boll} ra:{df2.ra} fibl:{df2.fibl}  macd:{df2.macd} macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')

    print(f"d :{ct.Resample_LABELS_Days['d']} df2.ma60d : {df2.ma60d}\n")

    df2 = get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days['3d'],resample='3d' )
    print(f'topR-3d:{df2.topR} red:{df2.red} lastdu:{df2.lastdu4} lastdu4:{df2.lastdu4} boll:{df2.boll} ra:{df2.ra} fibl:{df2.fibl} macd:{df2.macd} macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')
    print(f"3d :{ct.Resample_LABELS_Days['3d']} df2.ma60d : {df2.ma60d}\n")


    df2 = get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days['w'],resample='w' )
    print(f'topR-W:{df2.topR} red:{df2.red} lastdu:{df2.lastdu4} lastdu4:{df2.lastdu4} boll:{df2.boll} ra:{df2.ra} fibl:{df2.fibl} macd:{df2.macd} macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')

    print(f' w: {ct.Resample_LABELS_Days["w"] } df2.ma60d : {df2.ma60d} \n\n')
    # print(df[-3:],df[-1:])

    df2 = get_tdx_exp_low_or_high_power(code,dl=ct.Resample_LABELS_Days['m'],resample='m' )
    print(f'topR-m:{df2.topR} red:{df2.red} lastdu:{df2.lastdu4} lastdu4:{df2.lastdu4} boll:{df2.boll} ra:{df2.ra} fibl:{df2.fibl} macd:{df2.macd} macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')

    print(f' m: {ct.Resample_LABELS_Days["m"] } df2.ma20d : {df2.ma20d} df2.ma60d : {df2.ma60d} \n\n')

    print(f'topR:{df2.topR} red:{df2.red} df2.maxp: {df2.maxp} maxpcout: {df2.maxpcout}')
    # print(f'ldate:{df2.ldate[:2]}')
    df = df2.to_frame().T
    print(df.loc[:,df.columns[df.columns.str.contains('perc')]][-1:])
    print(df.loc[:,df.columns[df.columns.str.contains('per[0-9]{1}d', regex=True, case=False)]][-1:])
    print(f'macdlast1:{df2.macdlast1} macdlast2:{df2.macdlast2} macdlast6:{df2.macdlast6} macddif:{df2.macddif} macddea:{df2.macddea}')
    import ipdb;ipdb.set_trace()
    # write_to_all()
    

    # df2 = get_tdx_exp_low_or_high_power(code,dl=ct.duration_date_day,resample='d' )

    # tmp_df = get_kdate_data(code, start='', end='', ktype='D')
    # if len(tmp_df) > 0:
    #     write_tdx_tushare_to_file(code, df=tmp_df, start=None, type='f')

    # df = get_tdx_append_now_df_api_tofile('301287')

    # code='600005'
    # df2 = get_tdx_exp_low_or_high_power(code,dl=120,resample='d' )
    # df = get_tdx_Exp_day_to_df(code,dl=60, start=None,end=None, newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code,dl=ct.duration_date_month, start=None,end=None, newdays=0, resample='m')

    # import ipdb;ipdb.set_trace()

    # df3 = get_tdx_exp_low_or_high_power(code,dl=60)
    # print(df3.macd)
    # df1 = get_tdx_Exp_day_to_df(code,dl=60, start=None,end=None, newdays=0, resample='d').sort_index(ascending=True)
    # diff, dea, macd3 = custom_macd(df1.close)

    # df = get_tdx_power_now_df(code,dl=60, start=None,end=None).sort_index(ascending=True)
    # macd = df.ta.macd(fast=12,slow=26,signal=9)
    # import ipdb;ipdb.set_trace()

    # print(df.loc[:,df.columns[df.columns.str.contains('perc')]][:1].T)
    # df[(df.close > df.upper) & (df.upper > 0) ]
    # import ipdb;ipdb.set_trace()

    # df = get_tdx_Exp_day_to_df(code,dl=60, end='2023-10-13', newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')
    # df2 = get_tdx_append_now_df_api_tofile(code)
    print("code:%s boll:%s df2:%s"%(code,df.boll[0],df.df2[0]))

    resample = 'w'
    df = get_tdx_Exp_day_to_df(code,dl=180, end=None, newdays=0, resample=resample,lastdays=3)
    print("code:%s boll:%s df2:%s"%(code,df.boll[0],df.df2[0]))
    # import ipdb;ipdb.set_trace()

    # df2 = get_tdx_Exp_day_to_df(code,dl=134, end=None, newdays=0, resample=resample,lastdays=1)

    # get_tdx_Exp_day_to_df(code, start=None, end=None, dl=None, newdays=None, type='f', wds=True, lastdays=3, resample='d', MultiIndex=False)
    # df3 = compute_jump_du_count(df2, lastdays=9, resample='d')

    # df = get_tdx_exp_low_or_high_power(code, dl=30, newdays=0, resample=resample)
    # df3 =  get_tdx_exp_all_LastDF_DL([code],  dt=60, ptype='low', filter='y', power=ct.lastPower, resample=resample)

    # df3 = get_tdx_append_now_df_api_tofile(code,newdays=0, start=None, end=None, type='f', df=None, dl=10, power=False)

    # type D:\MacTools\WinTools\new_tdx\T0002\export\forwardp\SH688020.txt


    # Write_market_all_day_mp('all')


    # print df2.shape,df2.cumin
    # print get_kdate_data('000859', start='2023-01-01', end='', ktype='D')
    # write_tdx_tushare_to_file(code)
   
    # df = get_tdx_Exp_day_to_df(code, dl=ct.PowerCountdl,end=None, newdays=0, resample='d')
    # print df.perc1d[-1:],df.perc2d[-1:],df.perc3d[-1:],df.perc4d[-1:],df.perc5d[-1:]
    # print df[df.columns[(df.columns >= 'perc1d') & (df.columns <= 'perc%sd'%(9))]][:1]

    # df3 = df.sort_index(ascending=True)
    # print "cumin:",df[:2].cumin.values,df[:2].cumaxe.values,df[:2].cumins.values,df[:2].cumine.values,df[:2].cumaxc.values, df[:2].cmean.values

    # df2 = get_tdx_Exp_day_to_df(code,dl=60, end=None, newdays=0, resample='d')
    # # df4 = df2.sort_index(ascending=True)
    # print "cumin:",df2[:2].cumin.values,df2[:2].cumaxe.values,df2[:2].cumins.values,df2[:2].cumine.values,df2[:2].cumaxc.values, df2[:2].cmean.values

    # print get_tdx_day_to_df_last('999999', type=1)
    # sys.exit(0)
    # log.setLevel(LoggerFactory.INFO)
    # print Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300)
    # print Write_tdx_all_to_hdf(tdx_index_code_list, h5_fname='tdx_all_df', h5_table='all', dl=300,index=True)
    # print Write_sina_to_tdx(tdx_index_code_list,index=True)
    # print cct.get_ramdisk_path('tdx')

    # code_list = sina_data.Sina().market('cyb').index.tolist()
    # code_list.extend(tdx_index_code_list)
    time_s = time.time()


    # df = h5a.load_hdf_db('tdx_all_df_300', table='all_300', timelimit=False,MultiIndex=True)
    # if cct.GlobalValues().getkey(cct.tdx_hd5_name) is None:
    #     # cct.GlobalValues()
    #     cct.GlobalValues().setkey(cct.tdx_hd5_name, df)
    # else:
    #     print "load cct.GlobalValues().setkey('tdx_multi_data') is ok"
    # print df.info()


    # print "t0:%0.2f" % (time.time() - time_s)
    # start = '20170126'
    # start = None
    # time_s = time.time()
    # df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None, code_l=code_list, start=start, end=None, freq=None, col=None, index='date')
    # if df is not None:
    #     print "t1:%0.2f %s" % (time.time() - time_s, df.loc['399005'][:2])
    # time_s = time.time()
    # df = search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', code_l=code_list, start=start, end=None, freq=None, col=None, index='date')
    # print "t1:%0.2f" % (time.time() - time_s)
    # if df is not None:
    #     print "1:", df[-1:]




        # print df[df.index.get_level_values('code')]
    # testnumba(1000)
    # n = 100
    # xs = np.arange(n, dtype=np.float64)
    # qs = np.array([1.0/n,]*n)
    # rands = np.random.rand(n)
    # print python_resample(qs, xs, rands)

#    code='300174'
    # dm = get_sina_data_df(sina_data.Sina().market('all').index.tolist())
    # dm = None
    # get_tdx_append_now_df_api_tofile('000838', dm=dm,newdays=0, start=None, end=None, type='f', df=None, dl=10, power=True)
    # get_tdx_append_now_df_api_tofile('002196', dm=dm,newdays=1,dl=5)
#
    # code = '300661'
    # code = '600581'
    # code = '300609'
    # code = '000916'
    # code = '000593'
    code = '000557'
    code = '002175'
    # code = '300707'
    # resample = '3d'
    resample = 'd'
    # code = '000001'
    # code = '000916'
    # code = '600619'

    df = get_tdx_exp_all_LastDF_DL([code],end='2023-10-13',  dt=60, ptype='low', filter='y', power=ct.lastPower, resample=resample)

    # df = get_tdx_exp_low_or_high_power(code, dl=30, newdays=0, resample='d')
    df = get_tdx_Exp_day_to_df(code, dl=60, newdays=0, resample=resample)

    print("day_to_df:", df[:1][['per1d','per2d','per3d']])

    # col_co = df.columns.tolist()
    # col_ra_op = col_co.extend([ 'ra', 'op', 'fib', 'ma5d', 'ma10d', 'ldate', 'hmax', 'lmin', 'cmean'])
    # print col_ra_op,col_co
    # df = df.loc[:,col_ra_op]
    # print get_tdx_exp_low_or_high_power(code, dl=20,end='2017-06-28',ptype='high')
    # print get_tdx_exp_low_or_high_power(code, dl=20, end='2017-06-28', ptype='low')

    # print get_tdx_exp_low_or_high_power(code, dl=60, end=None, ptype='high', power=False, resample=resample)[:1]
    # df = get_tdx_exp_low_or_high_power(code, dl=60, end=None, ptype='low', power=False, resample=resample)
    # print get_tdx_Exp_day_to_df(code, dl=60, newdays=0, resample='m')[:2]
    # print get_tdx_Exp_day_to_df(code, dl=30, newdays=0, resample='d')[:2]
    # print get_tdx_append_now_df_api(code, start=None, end=None, type='f', df=None, dm=None, dl=6, power=True, newdays=0, write_tushare=False).T
    # print get_tdx_append_now_df_api_tofile(code, dm=None, newdays=0, start=None, end=None, type='f', df=None, dl=2, power=True)
    # print df
    # sys.exit(0)
#    print write_tdx_tushare_to_file(code)

    while 1:
        market = cct.cct_raw_input("1Day-Today check Duration Single write all TDXdata append [all,sh,sz,cyb,alla,q,n] :")
        if market != 'q' and market != 'n'  and len(market) != 0:
            if market in ['all', 'sh', 'sz', 'cyb', 'alla']:
                if market != 'all':
                    Write_market_all_day_mp(market, rewrite=True)
                    break
                else:
                    Write_market_all_day_mp(market)
                    break
            else:
                print("market is None ")
        else:
            break

    hdf5_wri_append = cct.cct_raw_input("1Day-Today No check Duration Single write Multi-300 append sina to Tdx data to Multi hdf_300[y|n]:")
    if hdf5_wri_append == 'y':
        for inx in tdx_index_code_list:
            get_tdx_append_now_df_api_tofile(inx)
        print("Index Wri ok 300", end=' ')
        Write_sina_to_tdx(tdx_index_code_list, index=True)
        Write_sina_to_tdx(market='all')

    hdf5_wri = cct.cct_raw_input("Multi-300 write all Tdx data to Multi hdf_300[rw|y|n]:")
    if hdf5_wri == 'rw':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300, rewrite=True)
    elif hdf5_wri == 'y':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=300)


    hdf5_wri = cct.cct_raw_input("Multi-900 write all Tdx data to Multi hdf_900[rw|y|n]:")
    if hdf5_wri == 'rw':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900, rewrite=True)
    elif hdf5_wri == 'y':
        Write_tdx_all_to_hdf('all', h5_fname='tdx_all_df', h5_table='all', dl=900)

    # hdf5_wri = cct.cct_raw_input("write all index tdx data to hdf[y|n]:")
    # if hdf5_wri == 'y':
        # Write_tdx_all_to_hdf(tdx_index_code_list, h5_fname='tdx_all_df', h5_table='all', dl=300,index=True)
        # Write_tdx_all_to_hdf(market='all')
        # Write_sina_to_tdx(market='all')

        # time_s = time.time()

        # st.close()



    # print get_tdx_Exp_day_to_df('300546',dl=20)
    # print get_tdx_Exp_day_to_df('999999',end=None).sort_index(ascending=False).shape
    # print sina_data.Sina().get_stock_code_data('300006').set_index('code')
#    dd=rl.get_sina_Market_json('cyb').set_index('code')
#    codelist= dd.index.tolist()
#    df = get_tdx_exp_all_LastDF(codelist, dt=30,end=20160401, ptype='high', filter='y')
    # print write_tdx_sina_data_to_file('300583')
    # print get_tdx_Exp_day_to_df('300583',dl=2,newdays=1)

    # write_to_all()
#    print get_tdx_append_now_df_api('600760')[:3]
    # print get_tdx_append_now_df_api('000411')[:3]
    # print get_tdx_Exp_day_to_df('300311',dl=2)[:2]
    # usage()

    # print get_tdx_append_now_df_api_tofile('300583')
    sys.exit(0)
#    get_append_lastp_to_df(None,end='2017-03-20',ptype='high')
#    print get_tdx_exp_low_or_high_power('603169',dl=10,ptype='high')
    print(get_tdx_exp_low_or_high_power('603169', None, 'high', 14, '2017-03-20', True, True, None))


#    get_tdx_exp_low_or_high_power, codeList, dt, ptype, dl,end,power,lastp,newdays
#    code=['603878','300575']
#    dm = get_sina_data_df(code)
#    code='603878'


#    print get_tdx_append_now_df_api2('603878',dl=2,dm=dm,newdays=5)
#    print write_tdx_sina_data_to_file('999999',dm)
    code = '999999'
#    print get_sina_data_df(code).index
#    print get_tdx_Exp_day_to_df(code,dl=2)
#    print df.date
    sys.exit(0)

    # print get_tdx_append_now_df_api(code,dl=30)
    # ldatedf = get_tdx_Exp_day_to_df(code,dl=1)
    # lastd = ldatedf.date
    # today = cct.get_today()
    # duration = cct.get_today_duration(lastd)
    # print cct.last_tddate(1)
    # print lastd,duration,today
#    300035,300047,300039

    # print get_tdx_append_now_df_api(code,dl=30)[:2]
#    print df
#    print write_tdx_tushare_to_file(code,None)
    sys.exit(0)
#
    df = get_tdx_exp_all_LastDF_DL(
        codeList=codelist, dt=30, end=None, ptype='low', filter='y', power=True)
    # print df[:1]
    sys.exit(0)
    #
    # print get_tdx_write_now_file_api('999999', type='f')
    time_s = time.time()
    print(get_tdx_exp_all_LastDF_DL(codeList=['000034', '300290', '300116', '300319', '300375', '300519'], dt='2016101', end='2016-06-23', ptype='low', filter='n', power=True))
    print("T1:", round(time.time() - time_s, 2))
    time_s = time.time()
    print(get_tdx_exp_all_LastDF_DL(codeList=['300102', '300290', '300116', '300319', '300375', '300519'], dt='2016101', end='2016-06-23', ptype='high', filter='n', power=True))
    print("T2:", round(time.time() - time_s, 2))

    sys.exit(0)
    print("index_Date:", get_duration_Index_date('999999', dl=3))
    print(get_duration_price_date('999999', dl=30, ptype='low', filter=False, power=True))
    print(get_duration_price_date('399006', dl=30, ptype='high', filter=False, power=True))
    # print get_duration_price_date('999999', dl=30, ptype='high',
    # filter=False,power=True)
    sys.exit(0)
    # print get_duration_price_date('999999',ptype='high',dt='2015-01-01')
    # print get_duration_price_date('999999',ptype='low',dt='2015-01-01')
    # df = get_tdx_Exp_day_to_df('300311')
    # print get_tdx_stock_period_to_type(df)
    # print get_sina_data_df(['601998','000503'])
    df = get_tdx_power_now_df(
        '000001', start='20160329', end='20160401', type='f', df=None, dm=None)
    print("a", (df))
    print("b", get_tdx_exp_low_or_high_price('999999', dt='20160101', end='20160401', ptype='low', dl=5))
    sys.exit(0)
    # df = get_tdx_exp_all_LastDF(['600000', '603377', '601998', '002504'], dt=20160301,end=20160401, ptype='low', filter='y')
    # list=['000001','399001','399006','399005']
    # df = get_tdx_all_day_LastDF(list,type=1)
    # print df
    '''
    index_d,dl=get_duration_Index_date(dt='20160101')
    print index_d
    get_duration_price_date('000935',ptype='low',dt=index_d)
    df= get_tdx_append_now_df('99999').sort_index(ascending=True)
    print df[-2:]
    '''
    '''
    # df = get_tdx_exp_low_or_high_price('600000', dt='20160304')
    # df,inx = get_duration_price_date('600000',dt='20160301',filter=False)
    df = get_tdx_append_now_df_api('300502',start='2016-03-03')
    # df= get_tdx_append_now_df_api('999999',start='2016-02-01',end='2016-02-27')
    print "a:%s"%df
    # print df[df.index == '2015-02-27']
    # print df[-2:]
    '''
    time_s = time.time()
    # df = get_tdx_Exp_day_to_df('999999')
    # dd = get_tdx_stock_period_to_type(df)
    # df = get_tdx_exp_all_LastDF( ['999999', '603377','603377'], dt=30,ptype='high')
    # df = get_tdx_exp_all_LastDF(['600000', '603377', '601998', '002504'], dt=20160329,end=None, ptype='low', filter='y')
    # print df
    sys.exit(0)
    # tdxdata = get_tdx_all_day_LastDF(['999999', '603377','603377'], dt=30,ptype='high')
    # print get_tdx_Exp_day_to_df('999999').sort_index(ascending=False)[:1]

    # tdxdata = get_tdx_exp_all_LastDF(['999999', '601998', '300499'], dt=20120101, ptype='high')

    print(get_tdx_exp_low_or_high_price('600610', dl=30))
    # main_test()
    sys.exit()

    # df = get_tdx_day_to_df_last('999999', dt=30,ptype='high')
    # print df
    # df = get_tdx_exp_low_or_high_price('603377', dt=20160101)
    # print len(df), df
    tdxdata = get_tdx_all_day_LastDF(['999999', '601998'])
    # print tdxdata
    # sys.exit(0)

    tdxdata = get_tdx_exp_all_LastDF(['600610', '603377', '000503'], dt=30)
    # tdxdata = get_tdx_all_day_LastDF(['999999','601998'],dt=30)
    print(tdxdata)

    # dt=get_duration_price_date('999999')
    # print dt

    print("t:", time.time() - time_s)
    # df.sort_index(ascending=True,inplace=True)
    # df.index=df.index.apply(lambda x:datetime.time)

    # df.index = pd.to_datetime(df.index)
    # dd = get_tdx_stock_period_to_type(df)
    # print "t:",time.time()-time_s
    # print len(dd)
    # print dd[-1:]

    # df= get_tdx_all_StockList_DF(list,1,1)
    # print df[:6]

    sys.exit(0)
    time_t = time.time()
    # df = get_tdx_allday_lastDF()
    # print "date<2015-08-25:",len(df[(df.date< '2015-08-25')])
    # df= df[(df.date< '2015-08-25')&(df.date > '2015-06-25')]
    # print "2015-08-25-2015-06-25",len(df)
    # print df[:1]
    # print (time.time() - time_t)

    # import sys
    # sys.exit(0)

    # df = rl.get_sina_Market_json('all')
    # code_list = np.array(df.code)
    # print len(code_list)

    # results = cct.to_mp_run_op(get_tdx_day_to_df_last,code_list,2)
    # df=pd.DataFrame((x.get() for x in results),columns=ct.TDX_Day_columns)
    # print df[:1]

    # get_tdx_allday_lastDF()

    # results=cct.to_mp_run(get_tdx_day_to_df,code_list)
    # print results[:2]
    # print len(results)
    # df = rl.get_sina_Market_json('all')
    # print(len(df))
    # code_list = np.array(df.code)
    # get_tdx_all_day_LastDF(code_list)
    # get_tdx_all_day_DayL_DF('all')
    # time.sleep(5)
    # print len(df)
    # df=df.drop_duplicates()
    # print(len(df))
    # for x in df.index:
    #     print df[df.index==x]
    # df=get_tdx_all_day_DayL_DF('all',20)
    # print len(df)
    # dd=pd.DataFrame()
    # for res in df:
    #     print res.get()[:1]
    #     # dd.concat
    #     pass
    # for x in results:
    # print x[:1]
    # df=pd.DataFrame(results,columns=ct.TDX_Day_columns)
    # print df[:1]
    # for res in results:
    #     print res.get()
    # df=pd.DataFrame(results,)
    # for x in  results:
    #     print x
    # for code in results:
    #     print code[:2]
    #     print type(code)
    #     break
    print((time.time() - time_t))

    # print code_list
    # df=get_tdx_day_to_df('002399')
    # print df[-1:]

    # print df[:1]
    # df=get_tdx_day_totxt('002399')
    # print df[:1]
    #
    # df=get_tdx_day_to_df('000001')
    # print df[:1]
    #
    # df=get_tdx_day_totxt('000001')
    # print df[:1]
    #
    # df=get_tdx_day_to_df('600018')
    # df=get_tdx_day_totxt('600018')
    #
    # import tushare as ts
    # print len(df),df[:1]

    # print df[df.]
    # code_stop=[]
    # for code in results:
    #     dt=code.values()[0]
    #     if dt[-1:].index.values < '2015-08-25':
    #         code_stop.append(code.keys())
    # print "stop:",len(code_stop)
    # pprint.pprint(df)

    """
    python readtdxlc5.py 999999 20070101 20070131

    argv = sys.argv[1:]
    try:
        opts, args = getopt.getopt(argv, "ht:", ["help", "type="])
    except getopt.GetoptError:
        usage(sys.argv[0])
        sys.exit(0)
    l_type = 'zip'  # default type is zipfiles!
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit(1)
        elif opt in ("-t", "--type"):
            l_type = arg
    if len(args) < 1:
        print 'You must specified the stock No.!'
        usage(sys.argv[0])
        sys.exit(1)
    """

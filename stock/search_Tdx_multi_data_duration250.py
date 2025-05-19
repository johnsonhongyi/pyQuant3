#-*- coding:utf-8 -*-
import sys,logging
stdout=sys.stdout
sys.path.append('../../')
from JSONData import  tdx_data_Day as tdd
from JSONData import sina_data 
from JSONData import tdx_hdf5_api as h5a
from JohnsonUtil import commonTips as cct
import pandas as pd
sys.stdout=stdout

import time,random
start = None
time_s = time.time()
# code_list = ['399006','000001','999999']

def get_multi_date_duration(df,dt):
    dd = df.reset_index()
    if dt is not None:
        dd = dd[dd.date >= dt]
    if len(dd) == 0:
        print("dd is None check dt:%s"%(dt))
    # dd['couts'] = dd.groupby(['code'])['code'].transform('count')
    dd = dd.set_index(['code', 'date'])
    return dd
def get_multi_code_count(df,col='code'):
    dd = df.reset_index()
    dd['couts'] = dd.groupby([col])[col].transform('count')
    # dd = dd.sort_values(by='couts',ascending=0)
    print('count dd.couts')
    dd = dd.set_index(['code', 'date'])
    return dd

def multindex_iloc(df, index):
    label = df.index.levels[0][index]
    return df.iloc[df.index.get_loc(label)]

def get_roll_mean_all(single=True,tdx=False,app=True,duration=100,ma_250_l=1.02,ma_250_h=1.11,resample ='d',rewrite=False,runrule='1'):
    # df = tdd.search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start=start, end=None, freq=None, col=None, index='date')
    time_s = time.time()
    if not cct.check_file_exist(cct.tdx_hd5_path):
        print('%s not ok'%(cct.tdx_hd5_path))
    block_path_upper = tdd.get_tdx_dir_blocknew() + '077.blk'
    if resample.lower() == 'd':
        block_path = tdd.get_tdx_dir_blocknew() + '061.blk'
    elif resample.lower() == 'w':
        block_path = tdd.get_tdx_dir_blocknew() + '060.blk'
    else:
        block_path = tdd.get_tdx_dir_blocknew() + '062.blk'

    if not rewrite and not app and cct.get_file_size(block_path) > 100 and cct.creation_date_duration(block_path) == 0:
        print("It's Today Update")
        return True
    code_list = sina_data.Sina().market('all').index.tolist()
    code_list.extend(['999999','399001','399006'])
    print("all code:",len(code_list))
    if duration <= 300 :
        h5_fname = 'tdx_all_df' + '_' + str(300)
        h5_table = 'all' + '_' + str(300)
    else:
        h5_fname = 'tdx_all_df' + '_' + str(900)
        h5_table = 'all' + '_' + str(900)
    # df = tdd.search_Tdx_multi_data_duration('tdx_all_df_300', 'all_300', df=None,code_l=code_list, start='20150501', end=None, freq=None, col=None, index='date')
    df = tdd.search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date')
    # df = tdd.search_Tdx_multi_data_duration(h5_fname, h5_table, df=None,code_l=code_list, start=None, end=None, freq=None, col=None, index='date',tail=1)
    def check_date_accurate(dfs):
        dd = dfs.reset_index().set_index('code')
        last3day = str(dd.loc['000002'].date[-3])[:10]
        last1day = str(dd.loc['000002'].date[-1])[:10]
        dd=dd[dd['date'] > last3day]
        dd['couts'] = dd.groupby('code')['date'].transform('count')
        return dd[(dd.couts == 1) &(dd.date != last1day)]

    if resample == 'd':
        checkdf = (check_date_accurate(df))
        for code in checkdf.index:
            # print('code:%s'%(code))
            tdd.get_tdx_append_now_df_api_tofile(code)

    #append data is end ,need re sort
    df = df.reset_index().sort_values(by=['code','date'],ascending=[0,1]).set_index(['code','date'])

    code_uniquelist=df.index.get_level_values('code').unique()

    code_select = code_uniquelist[random.randint(0,len(code_uniquelist)-1)]
    print(round(time.time()-time_s,2),df.index.get_level_values('code').unique().shape,code_select,df.loc[code_select].shape)
    lastday1 = df.loc['999999'].index[-1]
    print("!!!check lastDay!!!:%s close:%s"%(df.loc['999999'].index[-1],df.loc['999999'].close[-1]))
    # df.groupby(level=[0]),df.index.get_level_values(0)
    # len(df.index.get_level_values('code').unique())
    # df = df[~df.index.duplicated(keep='first')]

    import numpy as np

    def calculate_slope(data):
        # Calculate the slope of the line that connects two points
        slope = round((data[1] - data[0]) / (1), 2)
        return slope


    def detect_bull_bear(price_data, window=10):
        # Calculate the slopes of the price data for the last `window` days
        slopes = []
        # try:
        if len(price_data) > 20:
            for i in range(len(price_data) - window, len(price_data) - 1):
                        slope = calculate_slope([price_data[i], price_data[i + 1]])
                        # print(slope)
                        slopes.append(slope)

            # Compare the current slope with the average slope of the last `window` days
            avg_slope = round(np.mean(slopes), 2)
            curr_slope = calculate_slope([price_data[-window], price_data[-1]])
            # print(len(slopes), avg_slope, curr_slope)

            # if curr_slope > avg_slope:
            #     # return "Bullish"
            #     return "Bull"
            # else:
            #     return "Bear"
            return curr_slope
        else:
            return round((price_data[-1] - price_data[0])/(1),2)

        # except Exception as e:

        #     raise e
    def regression_ratio(df,limit=10):
        # Calculate the coefficients of the regression line

        # date = df.index.get_level_values('date')[0]
        # ??????10??????

        # last_10_days = x.loc[date-pd.Timedelta(days=10):date-pd.Timedelta(days=1)]
        # df = df.loc[df.index.get_level_values('date') <= date]

        if isinstance(df,pd.Series):
            Y = df.values[-limit:]
            X = df.reset_index().index[-limit:]
            
        else:
            X = df.index[-10:]
            Y = df.close[-10:]

        n = len(X)
        if n < 2:
            return 0
        else:
            sum_x = np.sum(X)
            sum_y = np.sum(Y)
            sum_xy = np.sum(X * Y)
            sum_xx = np.sum(X * X)
            # a = round((sum_y * sum_xx - sum_x * sum_xy) / (n * sum_xx - sum_x * sum_x),2)
            b = round((n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x),2)
        return b   

    # ?????????????????十?????????
    def last_10_days_stats(x):
        # ?????前??
        # date = x.index.get_level_values('date')[0]
        # ??????10??????

        # last_10_days = x.loc[date-pd.Timedelta(days=10):date-pd.Timedelta(days=1)]
        # last_10_days = x.loc[x.index.get_level_values('date') <= date]

        # ?????????
        # return pd.Series({'last_10_days_min': last_10_days.min()})
        return x.min()

        # return pd.Series({'last_10_days_mean': last_10_days['close'].mean(),
        #                   'last_10_days_max': last_10_days['close'].max(),
        #                   'last_10_days_min': last_10_days['close'].min()})


    def last_10_days_stats_outdate(x):
        import ipdb;ipdb.set_trace()

        last_10_days = x.iloc[-10:-1]
        return pd.Series({"min": last_10_days.min()})

    # def last_10_days_stats(df):
    #     grouped = df.groupby(level='date')
        
    #     import ipdb;ipdb.set_trace()

    #     stats = grouped.apply(lambda x: x.loc[x.index.get_level_values('date') - pd.Timedelta(days=10) : x.index.get_level_values('date') - pd.Timedelta(days=1)].close.agg(['mean', 'std']))
        
    #     df = pd.concat([df, stats.add_prefix('last_10_days_')], axis=1)
        
    #     return df

    def get_groupby_mean_median_close(dfs):

        groupd = dfs.groupby(level=[0])
        ###detect_bull_bear
        # dd= groupd['close'].rolling(20).apply(detect_bull_bear)

        df = groupd['close'].rolling(20).agg(['median','mean'])
        

        # df=dfs.copy()

        # dfsmin = groupd['close'].rolling(10).apply(last_10_days_stats)
        # time_s = time.time()
        dfsr = groupd['close'].rolling(10).apply(regression_ratio)
        dfsr.index =dfsr.to_frame().index.droplevel(1)
        df['xratio'] = dfsr
        print(time.time()-time_s)



        df['close'] = groupd.tail(1).reset_index().set_index(['code'])['close']
        # dfs['mean'] = groupd['close'].agg('mean')
        # dfs['median'] = groupd['close'].agg('median')
        
        # dfs = dfs.fillna(0)
        # idx = pd.IndexSlice
        # mask = ( (dfs['mean'] > dfs['median'])
        #         & (dfs['close'] > dfs['mean'])
        #         )
        # df=dfs.loc[idx[mask, :]]
        
        df = df[(df['mean']>df['median'])  & (df['close'] > df['mean'])]

        # dt_low = None
        # if dl == 1:
        #     dfs = groupd.tail(1)
        #     print("dfs tail1")
        # else:
        #     dl = 30
        #     dindex = tdd.get_tdx_Exp_day_to_df(
        #         '999999', dl=dl).sort_index(ascending=False)
        #     dt = tdd.get_duration_price_date('999999', df=dindex)
        #     dt = dindex[dindex.index >= dt].index.values
        #     dt_low = dt[-1]
        #     dtlen = len(dt) if len(dt) >0 else 1
        #     dfs = groupd.tail(dtlen)
        #     print("dfs tail:%s dt:%s"%(dtlen,dt))
        #     dfs = get_multi_date_duration(dfs,dt[-1])
        return df

    # multiIndex_func = {'close': 'mean', 'low': 'min', 'high': 'max', 'volume': 'sum', 'open': 'first'}
    # cct.using_Grouper(df, freq='W', col={'close': 'last'})
# *** TypeError: Only valid with DatetimeIndex, TimedeltaIndex or PeriodIndex, but got an instance of 'Index'
    # roll_dl = duration

    # print("resample:%s %s"%(resample.upper()))
    print("resample:%s time:%s"%(resample.upper(),round(time.time()-time_s,2)))

    if resample != 'd':
        time_sr = time.time()
        dfs = df.groupby(level=0).resample(resample, level=1).last()
        dfs['open'] = df.groupby(level=0)['open'].resample(resample, level=1).first()
        dfs['high'] = df.groupby(level=0)['high'].resample(resample, level=1).max()
        dfs['low'] = df.groupby(level=0)['low'].resample(resample, level=1).min()
        dfs['vol'] = df.groupby(level=0)['vol'].resample(resample, level=1).sum()   
        dfs = dfs.dropna()
        # r1 = len(df.loc['000001'])
        # r2 = len(df.loc['999999'])
        # roll_dl = r1 if r1 < r2 else r2
        print("resample time:%s"%(round(time.time()-time_sr,2)))


    else:
        dfs = df.copy()

    groupd = dfs.groupby(level=[0])
    # groupd.['close']
    # https://stackoverflow.com/questions/50915213/using-pct-change-with-multiindex-groupby
    dfs['percent'] = groupd['close'].apply(lambda x: round(x.pct_change()*100,2))
    dfs['volchang'] = groupd['amount'].apply(lambda x: round(x.pct_change()*100,2))

    # rollma = ['5','10','60','100','200']
    # rollma = ['5','10','250']
    # df.index.get_level_values('code')[0]
    if resample.upper() == 'D' or resample.lower() == 'd':
        if duration < 300:
            rollma = ['5','20','26','200']
        else:
            rollma = ['5','20','26','250']

    elif resample.upper() == 'W' or resample.lower() == 'w':
        rollma = ['5','10','20']
    else:
        rollma = ['5','10']

    # rollma.extend([str(duration)])

    # import ipdb;ipdb.set_trace()
    # df.loc['300130'][:2]

    # dfs['mean'] = groupd['close'].agg('mean')
    # dfs['median'] = groupd['close'].agg('median')

    for da in rollma:
        cumdays=int(da)
        dfs['ma%d'%cumdays] = round(dfs['close'].rolling(cumdays).mean(),2)
        if resample.lower() != 'm' and cumdays == 20 :
            dfs['std'] = round(dfs['close'].rolling(cumdays).std(),2)
            # dfs['upper'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 + 11.0 / 100) * x, 1))
            # dfs['lower'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 - 9.0 / 100) * x, 1))
            # dfs['ene'] = list(map(lambda x, y: round((x + y) / 2, 1), dfs['upper'], dfs['lower']))
            # dfs['upper'] = map(lambda x,y: round(x+ 2*y, 1),dfs['ma%d'%cumdays],dfs['std'])
            # dfs['lower'] = map(lambda x,y: round(x-2*y, 1),dfs['ma%d'%cumdays],dfs['std'])
            dfs['upper'] = round(dfs['ma%d'%cumdays]+dfs['std']*2,2)
            dfs['lower'] = round(dfs['ma%d'%cumdays]-dfs['std']*2,2)
            dfs['ene'] = dfs['ma%d'%cumdays]

        elif cumdays == 10:
            # dfs['upper'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 + 11.0 / 100) * x, 1))
            # dfs['lower'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 - 9.0 / 100) * x, 1))
            # dfs['ene'] = list(map(lambda x, y: round((x + y) / 2, 1), dfs['upper'], dfs['lower']))
            dfs['std'] = round(dfs['close'].rolling(cumdays).std(),2)
            # dfs['upper'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 + 11.0 / 100) * x, 1))
            # dfs['lower'] = dfs['ma%d'%cumdays].apply(lambda x: round((1 - 9.0 / 100) * x, 1))
            # dfs['ene'] = list(map(lambda x, y: round((x + y) / 2, 1), dfs['upper'], dfs['lower']))
            dfs['upper'] = round(dfs['ma%d'%cumdays]+dfs['std']*2,2)
            dfs['lower'] = round(dfs['ma%d'%cumdays]-dfs['std']*2,2)
            dfs['ene'] = dfs['ma%d'%cumdays]

        # df['upper'] = map(lambda x: round((1 + 11.0 / 100) * x, 1), df.ma10d)
        # df['lower'] = map(lambda x: round((1 - 9.0 / 100) * x, 1), df.ma10d)
        # df['ene'] = map(lambda x, y: round((x + y) / 2, 1), df.upper, df.lower)
        # dfs['amount%d'%cumdays] = groupd['amount'].apply(pd.rolling_mean, cumdays)
    # df.ix[df.index.levels[0]]
    #df.ix[df.index[len(df.index)-1][0]] #last row
    # dfs = tdd.search_Tdx_multi_data_duration(df=dfs,code_l=code_list, start='20170918', end='20170918', freq=None, col=None, index='date')
    import pandas_ta as ta
    CustomStrategy = ta.Strategy(
        name="Momo and Volatility",
        description="SMA 50,200, BBANDS, RSI, MACD and Volume SMA 20",
        ta=[
            {"kind":"macd","fastperiod":12, "slowperiod":26, "signalperiod":9}
           ]
        # ta=[
        #     {"kind": "sma", "length": 20},
        #     {"kind": "sma", "length": 60},
        #     {"kind": "bbands", "length": 20}
        # ]
    )
        
    def apply_strat(x):
        x.ta.strategy(CustomStrategy)
        return x

    # def Get_MACD_OP(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    def Get_MACD_OP(df, dtype='d'):
        # 参数12,26,9
        # if len(df) < limitCount:
        #     return (df, 1)
        # df = df.sort_index(ascending=True)
        # if len(df) > 1 + lastday:
        #     if lastday != 0:
        #         df = df[:-lastday]
    #    df=df.fillna(0)
        df[[ 'diff%s' % dtype,'ddea%s' % dtype, 'dea%s' % dtype]] = ta.macd(
            df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        return df

    def Get_RSI_OP(df, dtype='d'):
        # 参数12,26,9
        # if len(df) < limitCount:
        #     return (df, 1)
        # df = df.sort_index(ascending=True)
        # if len(df) > 1 + lastday:
        #     if lastday != 0:
        #         df = df[:-lastday]
    #    df=df.fillna(0)
        df[[ 'diff%s' % dtype,'ddea%s' % dtype, 'dea%s' % dtype]] = ta.macd(
            df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        return df

    # time_sm =time.time()
    # # newdf = dfs.groupby(['code']).apply(apply_strat)
    # df_list = []
    # dfg = df.groupby(['code'])
    # import ipdb;ipdb.set_trace()
    # macd = lambda x: ta.macd(df.loc[x.index, "close"])
    # df[['macd', 'macdsignal', 'macdhist'] = df.groupby(['code']).apply(macd).reset_index(0,drop=True)
    # # cct.to_mp_run_async()
    # for grp in dfg.groups:
    #     time_s =time.time()
    #     x = dfg.get_group(grp).copy()
    #     x.ta.strategy(CustomStrategy)
    #     print("time:%s"%(round(time.time()-time_s,2)))
    #     df_list.append(x)
    # newdf = pd.concat(df_list)  
    # print("time:%s"%(round(time.time()-time_sm,2)))

    
    dfs = dfs.dropna()
    # print dfs[:1],len(dfs)
    # groupd.agg({'low': 'min'})
    # '''idx mask filter'''
    # '''
    dt_low = None
    df_idx = []

    if single:
        dfs = groupd.tail(1)
        print("dfs tail1")
    else:

        if resample.lower() != 'n':
            dl = 30
            dindex = tdd.get_tdx_Exp_day_to_df(
                '999999', dl=dl,resample=resample).sort_index(ascending=False)
            dt = tdd.get_duration_price_date('999999', df=dindex)

            dt = dindex[dindex.index >= dt].index.values
            dt_low = dt[-1]
            dtlen = len(dt) if len(dt) >0 else 1
            print("dtlen:%s not use dt"%(dtlen))
            dtlen = 6
            dfs = groupd.tail(6)
        # import ipdb;ipdb.set_trace()
        # if dtlen == 1:
        #     dt = str(dfs.loc['999999'].index[0])[:10]

            #too slow
            # df_idx = get_groupby_mean_median_close(dfs)

            print(("dfs tail:%s dt:%s "%(dtlen,dt)))
            dfs = get_multi_date_duration(dfs,None)
        # else:
        #     print("dtlen:30")
        #     dfs = groupd.tail(30)
        #     df_idx = get_groupby_mean_median_close(dfs)
        #     dfs = get_multi_date_duration(dfs,None)

        # groupd2 = dfs.groupby(level=[0])
        # dfs['ma%d'%cumdays] = groupd['close'].apply(pd.rolling_mean, cumdays)


        # dfs.reset_index().groupby(['code'])['date'].transform('count')
        single = True
        
    dfs = dfs.fillna(0)
    idx = pd.IndexSlice
    # mask = (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])]) & (dfs[('ma%s')%(rollma[-1])] > 0) & (dfs[('close')] > dfs[('ma%s')%(rollma[0])])  & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]) 
    # mask = (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])]) & (dfs[('ma%s')%(rollma[-1])] > 0) & (dfs[('close')] > dfs[('ma%s')%(rollma[1])])  & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]) 
    # mask = (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])]) & (dfs[('ma%s')%(rollma[-1])] > 0) &  (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]) 


    # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]) & (dfs[('close')] > dfs[('ma%s')%(rollma[0])]))

    # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
    #         & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
    #         & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
    #         & (dfs[('close')] > dfs[('ma%s')%(rollma[0])]))


                # & (dfs['mean'] > dfs['median'])
                # & (dfs['close'] > dfs['mean'])


    if len(rollma) > 1:
        if resample.upper() == 'M' or resample.lower() == 'm' :
            # mask =  ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[0])].shift(1))
            #         & (dfs[('close')] >= dfs[('ma%s')%(rollma[0])])
            #         & (dfs[('close')].shift(1) >= dfs[('ma%s')%(rollma[0])].shift(1))
            #         & (dfs[('low')].shift(1) > dfs[('low')].shift(2))
            #         & (dfs[('low')] > dfs[('ma%s')%(rollma[0])])
            #         & (dfs['high'].shift(1) > dfs[('high')].shift(1))
            #         )
            mask =  ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
                    & (dfs[('close')] >= dfs[('high')]*0.92)
                    & (dfs[('close')] >= dfs[('ma%s')%(rollma[1])])
                    & (dfs[('low')] <= dfs[('ma%s')%(rollma[1])]*1.05)
                    & (dfs[('low')] > dfs[('ma%s')%(rollma[0])] * 0.99)
                    & (dfs[('close')].shift(1) >  dfs[('ma5')]) 
                    )
                    # & (dfs[('high')] >=  dfs[('upper')].shift(1)) 
                    # & (dfs[('close')].shift(3) >  dfs[('ma5d')].shift(3)) 
                    # & (dfs[('close')].shift(1) > dfs[('ma%s')%(rollma[0])].shift(1) * 0.98)
                    # & (dfs[('low')] > dfs[('low')].shift(1))
                    # & (dfs[('low')] >= dfs[('ma%s')%(rollma[0])].shift(1))
                    # & (dfs['low'].shift(1) > dfs[('low')].shift(2))

        elif resample.upper() == 'W' or resample.lower() == 'w':
            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
            #         & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[-1])])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[0])])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
            #         & ((dfs[('close')] > dfs['ene']) | (dfs[('close')] > dfs['upper']) )   
            #         & (dfs[('close')] > dfs[('close')].shift(1))
            #         & (dfs[('close')] > dfs[('close')].shift(2))
            #         & (dfs[('close')] > dfs[('close')].shift(3))

            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
            #         & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])])
            #         & (dfs[('close')] > dfs[('ene')])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[0])].shift(1) )
            #         & (dfs[('low')] < dfs[('ma%s')%(rollma[0])]*1.05)
            #         & (dfs[('close')].shift(1) > dfs[('ma%s')%(rollma[0])].shift(1) )
            #         & (dfs[('close')].shift(2) > dfs[('ma%s')%(rollma[0])].shift(2) )
            #         & (dfs[('close')] >= dfs[('close')].shift(1))
            #         & ((dfs[('percent')].shift(1) > 1)|(dfs[('percent')].shift(2) > 1))
            #         & (dfs[('percent')].shift(3) > 0)
            #         & (dfs[('high')] >= dfs[('upper')].shift(1))
            #         & (dfs[('low')] > dfs[('low')].shift(1))
            #         & ((dfs[('high')].shift(1) >= dfs[('high')].shift(2)) | (dfs[('close')].shift(1) >= dfs[('close')].shift(2)) )
            #         )


            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
            #         & (dfs[('ma%s')%(rollma[0])] >= dfs[('ma%s')%(rollma[-1])])
            #         & (dfs[('close')] > dfs[('ene')])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[0])].shift(1)*0.98 )
            #         & (dfs[('close')].shift(1) > dfs[('ma%s')%(rollma[0])].shift(1)*0.98 )
            #         & (dfs[('close')].shift(2) > dfs[('ma%s')%(rollma[0])].shift(2)*0.98 )
            #         & (dfs[('close')].shift(3) > dfs[('ma%s')%(rollma[0])].shift(3)*0.98 )
            #         & (dfs[('high')].shift(1) >= dfs['high'].shift(2)*0.98 )
            #         & (dfs[('low')].shift(1) >= dfs[('low')].shift(2)*0.98 )
            #         & (dfs[('low')] > dfs[('low')].shift(1)*0.98)
            #         )

                    # & (dfs[('upper')].shift(1) >= dfs[('upper')].shift(2))

            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
            #         & (dfs['upper'] > 0)
            #         & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])])
            #         & ((dfs[('high')].shift(1) >= dfs['upper'].shift(1)) | (dfs[('high')].shift(2) >= dfs[('upper')].shift(2)) | (dfs[('high')].shift(3) >= dfs[('upper')].shift(3)) | (dfs[('high')].shift(4) >= dfs[('upper')].shift(4)) | (dfs[('high')].shift(5) >= dfs[('upper')].shift(5)) | (dfs[('high')].shift(6) >= dfs[('upper')].shift(6)))
            #         & (dfs[('close')] >= dfs[('ma%s')%(rollma[0])])
            #         & (dfs[('high')] >= dfs['high'].shift(1))
            #         )

            mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0)
                    & (dfs['upper'] > 0)
                    & ((dfs[('close')] >= dfs[('high')]*0.92) | (dfs[('close')] > dfs[('open')]))
                    & (dfs[('close')] > dfs[('ma20')])
                    & (dfs[('low')] <= dfs[('ma20')]*1.05)
                    & ((dfs[('high')] >= dfs['upper'].shift(1))  | (dfs[('high')].shift(1) >= dfs['upper'].shift(1)) | (dfs[('high')].shift(2) >= dfs[('upper')].shift(2)) | (dfs[('high')].shift(3) >= dfs[('upper')].shift(3)) | (dfs[('high')].shift(4) >= dfs[('upper')].shift(4)) | (dfs[('high')].shift(5) >= dfs[('upper')].shift(5)) | (dfs[('high')].shift(6) >= dfs[('upper')].shift(6)))
                    & ((dfs[('high')].shift(1) >= dfs['high'].shift(2)) | (  (dfs['close'].shift(1) > dfs[('upper')].shift(1)) & (dfs['low'].shift(1) > dfs['low'].shift(2)) ) )
                    & (dfs[('low')] >= dfs[('ma%s')%(rollma[0])])
                    )
                    # & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[1])])
                    # & (dfs[('percent')] > 0)
                    # & (dfs[('low')] >= dfs[('ma%s')%(rollma[0])]*0.98)
                    # & (dfs[('low')] <= dfs[('ma%s')%(rollma[0])]*1.03)


                    
        else:
            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0)
            #         & (dfs[('ma%s')%(rollma[0])] > dfs[('ma%s')%(rollma[-1])])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[0])])
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
            #         & ((dfs[('close')] > dfs['upper']) | (dfs[('close')].shift(1) > dfs['upper'].shift(1)) | (dfs[('close')].shift(2) > dfs['upper'].shift(2)))   
            #         & (dfs[('close')] > dfs[('close')].shift(1))
            #         )

            # mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
            #         & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
            #         & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 

            #超跌反弹,20240220,蓝英装备
            if runrule == '2':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('lower')] > 0)
                        & ((dfs[('high')] > dfs[('high')].shift(1)) & (dfs[('high')] > dfs[('high')].shift(2)) )
                        & ((dfs[('close')] > dfs[('close')].shift(1)) & (dfs[('close')].shift(1) > dfs[('close')].shift(2)))
                        & ((dfs[('low')] <= dfs[('ma%s')%(rollma[0])]*1.01) | (dfs[('low')].shift(1) <= dfs[('lower')]*1.05) | (dfs[('low')].shift(1) <= dfs[('lower')]*1.05)  )
                        & ((dfs[('volchang')] < 100) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & ((dfs[('percent')] > 5) | (dfs[('percent')].shift(1) > 5) | (dfs[('percent')].shift(2) > 5))
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )
            #适合大盘稳定,年线附近多头,一阳high4,high upper,追涨模型
            elif runrule == '1':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('upper')] > 0)
                        & (dfs[('ma5')] > dfs[('ene')])
                        & ((dfs[('high')] > dfs[('upper')]) | (dfs[('high')].shift(3) > dfs[('upper')].shift(3)) | (dfs[('high')].shift(5) > dfs[('upper')].shift(5)) | (dfs[('high')].shift(6) > dfs[('upper')].shift(6)) | (dfs[('high')].shift(7) > dfs[('upper')].shift(7)) | (dfs[('high')].shift(9) > dfs[('upper')].shift(9)) | (dfs[('high')].shift(10) > dfs[('upper')].shift(10)) | (dfs[('high')].shift(11) > dfs[('upper')].shift(11)) | (dfs[('high')].shift(12) > dfs[('upper')].shift(12)) )
                        & (dfs[('close')] > dfs[('ene')])
                        & (dfs[('low')] <= dfs[('ma20')]*1.05)
                        & ((dfs[('volchang')] < 100) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & (dfs[('percent')] > 2)
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )
            #新高连阳
            elif runrule == '3':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('lower')] > 0)
                        & ((dfs[('high')] > dfs[('high')].shift(1)) & (dfs[('high')].shift(1) > dfs[('high')].shift(2)))
                        & ((dfs[('close')] > dfs[('close')].shift(1)) & (dfs[('close')].shift(1) > dfs[('close')].shift(2)))
                        & ((dfs[('percent')] > 2) & ((dfs[('percent')].shift(1) > 2) | (dfs[('percent')].shift(2) > 2)) )
                        & ((dfs[('volchang')] < 100) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )
                        # & ((dfs[('volchang')] < 60) | (dfs[('volchang')].shift(1) < 60) | (dfs[('volchang')].shift(2) < 100) )
            #连阳,不新高
            elif runrule == '4':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('lower')] > 0)
                        & ((dfs[('close')] >= dfs[('high')]*0.98) & (dfs[('close')].shift(1) >= dfs[('high')].shift(1)*0.98))
                        & ((dfs[('high')] > dfs[('high')].shift(1)) | (dfs[('high')].shift(1) > dfs[('high')].shift(2)) | (dfs[('high')] > dfs[('high')].shift(2)) )
                        & ((dfs[('close')] > dfs[('close')].shift(1)) & (dfs[('close')].shift(1) > dfs[('close')].shift(2)))
                        & ((dfs[('percent')] > 2) & ((dfs[('percent')].shift(1) > 2) | (dfs[('percent')].shift(2) > 2)))
                        & ((dfs[('volchang')] < 100) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )
            #新高连阳高开高走
            elif runrule == '5':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('lower')] > 0)
                        & ((dfs[('close')] >= dfs[('high')]*0.98) & (dfs[('close')].shift(1) >= dfs[('high')].shift(1)*0.98))
                        & ((dfs[('high')] > dfs[('high')].shift(1)) & (dfs[('high')].shift(1) > dfs[('high')].shift(2)))
                        & ((dfs[('close')] > dfs[('close')].shift(1)) & (dfs[('close')].shift(1) > dfs[('close')].shift(2)))
                        & ((dfs[('percent')] > 2) & ((dfs[('percent')].shift(1) > 2) | (dfs[('percent')].shift(2) > 2)) )
                        & ((dfs[('volchang')] < 100) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )
                        # & ((dfs[('lower')] >= dfs[('close')].shift(1)) |  (dfs[('lower')] >= dfs[('close')].shift(2)))
                        # & ((dfs[('volchang')] < 60) | (dfs[('volchang')].shift(1) < 60) | (dfs[('volchang')].shift(2) < 100) )
                        # & ((dfs[('low')] <= dfs[('ma%s')%(rollma[0])]*1.01) | (dfs[('low')].shift(1) <= dfs[('lower')]*1.05) | (dfs[('low')].shift(1) <= dfs[('lower')]*1.05)  )
            
            #适合大盘稳定,年线附近多头,一阳high4,high upper,追涨模型,不限涨幅
            elif runrule == '6':
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) & (dfs[('ma%s')%(rollma[1])] > 0) & (dfs[('ma%s')%(rollma[-1])] > 0) 
                        & (dfs[('upper')] > 0)
                        & (dfs[('ma5')] > dfs[('ene')])
                        & ((dfs[('high')] > dfs[('upper')]*0.98) | (dfs[('high')].shift(1) > dfs[('upper')].shift(1)*0.98)  | (dfs[('high')].shift(2) > dfs[('upper')].shift(2)*0.98) | (dfs[('high')].shift(3) > dfs[('upper')].shift(3)*0.98) | (dfs[('high')].shift(5) > dfs[('upper')].shift(5)*0.98) | (dfs[('high')].shift(6) > dfs[('upper')].shift(6)*0.98) | (dfs[('high')].shift(7) > dfs[('upper')].shift(7)*0.98) | (dfs[('high')].shift(9) > dfs[('upper')].shift(9)*0.98) | (dfs[('high')].shift(10) > dfs[('upper')].shift(10)*0.98) | (dfs[('high')].shift(11) > dfs[('upper')].shift(11)*0.98) | (dfs[('high')].shift(12) > dfs[('upper')].shift(12)*0.98) )
                        & (dfs[('close')] > dfs[('ene')])
                        & ((dfs[('volchang')] > 10) & (dfs[('volchang')].shift(1) < 100) & (dfs[('volchang')].shift(2) < 100) )
                        & (dfs[('percent')] > 2)
                        & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                        & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                        )      
                        # & (dfs[('low')] <= dfs[('ma20')]*1.05)

                    # & (dfs[('low')] > dfs[('low')].shift(1))
                    # & (dfs[('high')] > dfs[('high')].shift(1))
                    # & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l)
                    # & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h)  
                    # & (dfs[('close')] > dfs[('close')].shift(2))
                    # & (dfs[('close')] > dfs[('close')].shift(3))
                        # & (dfs[('low')] < dfs[('close')].shift(1))
               
    else:
                mask = ( (dfs[('ma%s')%(rollma[0])] > 0) 
                & (dfs[('close')] > dfs[('ma%s')%(rollma[0])])
                & ((dfs[('close')] > dfs['ene']) | (dfs[('close')] > dfs['upper']) ) 
                & (dfs[('close')] > dfs[('ma%s')%(rollma[-1])]*ma_250_l) 
                & (dfs[('close')] < dfs[('ma%s')%(rollma[-1])]*ma_250_h) 
                )


    # mask = ((dfs[('close')] > dfs[('ma%s')%(rollma[-1])])) 
    #
    mask_upper= ((dfs[('ma%s')%(rollma[0])] > 0)
                & (dfs[('upper')] > 0)
                & ( dfs[('high')] > dfs[('upper')])
                )

    df_u = dfs.loc[idx[mask_upper, :]]
    df_u = get_multi_code_count(df_u)
    df_u = df_u.groupby(level=[0]).tail(1).reset_index().set_index('code')
    df_u = df_u[df_u.date>=lastday1]
    # df_u = df_u[(~df_u.index.str.contains('688'))] 
    df_u = df_u.sort_values(by=['percent','couts','volchang'],ascending=[0,1,1])
    df_u = df_u[df_u.percent > 0]
    codeupper = df_u.index.tolist()
    print("resample:%s count upper:%s :%s"%(resample.upper(),len(df_u),df_u.couts[:5]))



    
    df=dfs.loc[idx[mask, :]]
    
    # print(df.loc['300293'])
    # import ipdb;ipdb.set_trace()

    if len(df) == 0:
        import ipdb;ipdb.set_trace()
        print("df is None,check mask")
        return False

    # import ipdb;ipdb.set_trace()
    # df.sort_values(by='couts',ascending=0)
    # groupd.first()[:2],groupd.last()[:2]
    # groupd = df250.groupby(level=[0])
    # '''
    # groupd.transform(lambda x: x.iloc[-1])
    # groupd.last()
    # groupd.apply(lambda x: x.close > x.ma250)
    # df.shape,df.sort_index(ascending=False)[:5]
    # ?groupd.agg
    # groupd = df.groupby(level=[0])
    # groupd['close'].apply(pd.rolling_mean, 250, min_periods=1)
    #ex:# Group df by df.platoon, then apply a rolling mean lambda function to df.casualties
     # df.groupby('Platoon')['Casualties'].apply(lambda x:x.rolling(center=False,window=2).mean())

    code_uniquelist=df.index.get_level_values('code').unique()
    code_select = code_uniquelist[random.randint(0,len(code_uniquelist)-1)]

    if app:
        print(round(time.time()-time_s,2),'s',df.index.get_level_values('code').unique().shape,code_select,df.loc[code_select][-1:])

    if single:
        # groupd = df.groupby(level=[0])
        if tdx:
            # block_path = tdd.get_tdx_dir_blocknew() + '060.blk'
            # if cct.get_work_time():
            #     codew = df[df.date == cct.get_today()].index.tolist()

            if dt_low is not None:
                
                # if runrule !=1 :
                #     df = get_multi_code_count(df)
                    # df = get_multi_code_count(df).groupby(level=[0]).tail(1)
                df = get_multi_code_count(df)
                groupd2 = df.groupby(level=[0])
                df = groupd2.tail(1)
                df = df.reset_index().set_index('code')
                # import ipdb;ipdb.set_trace()

                # df = df[(df.date >= dt_low) & (df.date <= cct.get_today())]
                dd = df[(df.date == dt_low)]
                # df = df[(df.date >= cct.last_tddate(1))]
                df = df[(df.date >= df.date.max())]  # today
                # df = df[(df.date >= df.date.max()) | (df.date >= cct.last_tddate())]  # lastday and today



            else:
                #runrule?
                df = get_multi_code_count(df)

                groupd2 = df.groupby(level=[0])
                df = groupd2.tail(1)
                df = df.reset_index().set_index('code')
                if resample.lower() == 'd':
                    df = df[(df.date >= cct.last_tddate(days=10)) & (df.date <= cct.get_today())]
                # codew = df.index.tolist()

            top_temp = tdd.get_sina_datadf_cnamedf( df.index.tolist(),df) 
            # check df_upper 追涨模型
            if runrule == '1':
                top_temp = cct.combine_dataFrame(top_temp,df_u.couts)
                top_temp = top_temp[top_temp.couts > 0]
            # else:
            #     top_temp = get_multi_code_count(top_temp).groupby(level=[0]).tail(1)
                # top_temp['couts'] = 0

            print(("df:%s %s df_idx:%s"%(len(df),df.index[:5],len(df_idx))))
            top_temp.date = top_temp.date.apply(lambda x: str(x)[:10])
            percet = 'percma5w'
            if resample.upper() == 'M' or resample.lower() == 'm':
                percet = 'percma5M'
                top_temp[percet] = ((top_temp['close'] - top_temp['ma5']) / top_temp['ma5'] * 100).map(lambda x: round(x, 2))
            elif resample.upper() == 'D' or resample.lower() == 'd':
                percet = 'percma5d'
                top_temp[percet] = ((top_temp['close'] - top_temp['ma5']) / top_temp['ma5'] * 100).map(lambda x: round(x, 2))
            else:
                percet = 'percma5w'
                top_temp[percet] = ((top_temp['close'] - top_temp['ma5']) / top_temp['ma5'] * 100).map(lambda x: round(x, 2))
            
            # top_temp.loc[top_temp.percent >= 9.94, 'percent'] = 10
            if runrule in ['2','3','4','5']:
                top_temp = top_temp.sort_values(by=['couts','percent',percet,'volchang'],ascending=[0,0,0,1])
                # top_temp = top_temp[top_temp.couts > 1]
            else:
                top_temp = top_temp.sort_values(by=['percent','couts','volchang',percet],ascending=[0,1,1,1])
            # top_temp = top_temp[ (~top_temp.index.str.contains('688'))]  
            top_temp = top_temp[ (~top_temp.name.str.contains('ST'))]  
            if app:
                if resample.lower() == 'd' or resample.lower() == 'w' :
                    table, widths=cct.format_for_print(top_temp.loc[:,[percet ,'close','high','percent','volchang','ma5' , 'ma20','upper','lower','ene','couts','name']][:100 if len(top_temp) > 100 else len(top_temp)], widths=True)
                else:
                    table, widths=cct.format_for_print(top_temp.loc[:,[percet ,'close','high','percent','volchang','ma5' , 'ma10','upper','lower','ene','couts','name']][:100 if len(top_temp) > 100 else len(top_temp)], widths=True)
                print(table)

            if df_idx is not None and len(df) > 0 and len(df_idx) > 0:
                idx_set_=[x for x in   df_idx.index if x in df.index]
                df = df.loc[idx_set_,:].dropna()

            if resample.lower() != 'm':
                print(("Main Down dd :%s MainUP df:%s couts std:%0.1f "%(len(dd),len(top_temp),top_temp.couts.std())))
            else:
                print(("MainUP df:%s couts std:%0.1f "%(len(top_temp),top_temp.couts.std())))
            # print df.date.mode()[0]
            # df = df.sort_values(by='couts',ascending=1)
            # df = df[df.couts > df.couts.std()]
            # # df = df[(df.date >= df.date.mode()[0]) & (df.date <= cct.get_today())]
            # codew = df.index.tolist()

            if app:
                print(round(time.time()-time_s,2),'groupd2',len(top_temp))

            # top_temp = tdd.get_sina_datadf_cnamedf(codew,df) 
            # # top_temp['percent'] = ((top_temp['ma5'] - top_temp['ma10']) / top_temp['ma10'] * 100).map(lambda x: round(x, 2))
            # if resample.upper() == 'M' or resample.lower() == 'm':
            #     percet = 'percma5M'
            #     top_temp[percet] = ((top_temp['close'] - top_temp['ma5']) / top_temp['ma5'] * 100).map(lambda x: round(x, 2))
            # elif resample.upper() == 'D' or resample.lower() == 'd':
            #     percet = 'percma20d'
            #     top_temp[percet] = ((top_temp['close'] - top_temp['ma20']) / top_temp['ma20'] * 100).map(lambda x: round(x, 2))
            # else:
            #     percet = 'percma5w'
            #     top_temp[percet] = ((top_temp['close'] - top_temp['ma5']) / top_temp['ma5'] * 100).map(lambda x: round(x, 2))
            # top_temp = top_temp.sort_values(by=percet,ascending=1)

            # # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]  
            # top_temp = top_temp[ (~top_temp.index.str.contains('688'))]  



            if len(top_temp) > 100:
                codew = top_temp.index.tolist()[:100]
            else:
                codew = top_temp.index.tolist()

            #clean st and 688

            if app:
                print("Write blk:%s"%(block_path))
                hdf5_wri = cct.cct_raw_input("rewrite code [Y] or append [N]:")
                if hdf5_wri == 'y' or hdf5_wri == 'Y':
                    append_status=False
                else:
                    append_status=True
                dfcf_wri = cct.cct_raw_input("write dfcf[Y]:")
                if dfcf_wri == 'y' or dfcf_wri == 'Y':
                    dfcf_status=True
                else:
                    dfcf_status=False



            else:
                append_status=False
                dfcf_status=False
                
            if len(codew) > 0: 
                cct.write_to_blocknew(block_path, codew, append_status,doubleFile=False,keep_last=0,dfcf=dfcf_status)
                print("write:%s block_path:%s"%(len(codew),block_path))
                print(top_temp.name.tolist()[:20])
                if len(codeupper) > 0:
                    print("upper Write blk:%s"%(block_path_upper))
                    wri_upper = cct.cct_raw_input("upper Write blk[Y] or Exit [N]:")
                    if wri_upper == 'y' or wri_upper == 'Y':
                        upper_wri = cct.cct_raw_input("rewrite code [Y] or append [N]:")
                        if upper_wri == 'y' or upper_wri == 'Y':
                            append_status=False
                        else:
                            append_status=True
                        cct.write_to_blocknew(block_path_upper, codeupper, append=append_status,doubleFile=False,keep_last=0,dfcf=False)
                    # print("write:%s block_path:%s"%(len(codeupper),block_path_upper))
            else:
                # cct.write_to_blocknew(block_path, codew, append_status,doubleFile=False,keep_last=0,dfcf=dfcf_status)
                print("write error:%s block_path:%s"%(len(codew),block_path))
                # print("write:%s block_path:%s"%(len(codew),block_path))
                # print(top_temp.name.tolist())


        # df['date'] = df['date'].apply(lambda x:(x.replace('-','')))
        # df['date'] = df['date'].astype(int)
        # print df.loc[code_select].T,df.shape
        MultiIndex = False
    else:
        MultiIndex = True
    h5a.write_hdf_db('all300', df, table='roll200', index=False, baseCount=500, append=False, MultiIndex=MultiIndex)
    return df

if __name__ == '__main__':
    # get_roll_mean_all(single=False,tdx=True,app=True,duration=250) ???
    # get_roll_mean_all(single=False,tdx=True,app=True,duration=120) ???

    # get_roll_mean_all(single=False,tdx=True,app=True,duration=250,ma_250_l=1.02,ma_250_h=1.2,resample='w')
    # get_roll_mean_all(single=True,tdx=True,app=True)
    # get_roll_mean_all(single=True,tdx=True,app=False)
    runruledict={'1':'追涨','2':'超跌反弹','3':'连阳新高','4':'连阳','5':'高开高走','6':'追涨High',}
    runrule = cct.cct_raw_input("runrule:追涨/1,超跌反弹/2,连阳新高/3,连阳/4,高开高走/5,追涨High/6:[1/2/3(默认)/4/5/6]: ")

    if runrule is None or len(runrule) == 0:
        runrule = '3'
    print("runrule:%s"%(runruledict[runrule]))
    runDay = cct.cct_raw_input("runDay[Y/y]/[N/n]:")
    if runDay.lower() != 'n':
        get_roll_mean_all(single=False,tdx=True,app=True,duration=300,ma_250_l=1.2,ma_250_h=1.5,resample='d',runrule=runrule)

    runWeek = cct.cct_raw_input("runWeek[Y/y]/[N/n]:")


    if runWeek.lower() != 'n' :
        runrule = None
        runruledict={'1':'追涨','2':'超跌反弹','3':'连阳新高','4':'连阳','5':'高开高走','6':'追涨High',}
        runrule = cct.cct_raw_input("runrule:追涨/1,超跌反弹/2,连阳新高/3,连阳/4,高开高走/5,追涨High/6:[1/2/3(默认)/4/5/6]: ")

        if runrule is None or len(runrule) == 0:
            runrule = '3'
        print("runrule:%s"%(runruledict[runrule]))

        get_roll_mean_all(single=False,tdx=True,app=True,duration=300,ma_250_l=1.2,ma_250_h=1.5,resample='w',runrule=runrule)
    runMon = cct.cct_raw_input("runMon[Y/y]/[N/n]:")
    if runMon.lower() != 'n' :
        runrule = None
        runruledict={'1':'追涨','2':'超跌反弹','3':'连阳新高','4':'连阳','5':'高开高走','6':'追涨High',}
        runrule = cct.cct_raw_input("runrule:追涨/1,超跌反弹/2,连阳新高/3,连阳/4,高开高走/5,追涨High/6:[1/2/3(默认)/4/5/6]: ")

        if runrule is None or len(runrule) == 0:
            runrule = '3'
        print("runrule:%s"%(runruledict[runrule]))

        get_roll_mean_all(single=False,tdx=True,app=True,duration=900,ma_250_l=1.2,ma_250_h=1.5,resample='m',runrule=runrule)

    # get_roll_mean_all(single=False, tdx=True, app=False,duration=300,ma_250_l=1.02,ma_250_h=1.2,resample='w',rewrite=True)
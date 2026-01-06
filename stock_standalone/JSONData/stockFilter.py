# -*- coding:utf-8 -*-
import sys
sys.path.append("..")
from JohnsonUtil import commonTips as cct
import JohnsonUtil.johnson_cons as ct
# from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory
log = LoggerFactory.getLogger()
import time
import random

# def func_compute_df2(c,lc,lp,h,l,b1_v):


def func_compute_df2(c, lc, h, l):
    if h - l == 0:
        du_p = 0.1
    else:
        du_p = round((h - l) / lc * 100, 1)
    mean_p = round((h + l) / 2, 1)
    if c < mean_p and c < lc:
        du_p = -du_p
    return du_p


def filterPowerCount(df, count=200, down=False, duration=2):

    nowint = cct.get_now_time_int()
    df.sort_values('percent', ascending=False, inplace=True)
    top_temp = df[:count].copy()

    if 915 < nowint <= 945:
        if nowint <= 935:
            top_temp = df[(df.buy > df.llastp) | (
                df.percent > df['per%sd' % (duration)])]
        else:
            top_temp = df[((df.open > df.llastp) & (df.low >= df.llastp)) | (
                df.percent > df['per%sd' % (duration)])]
        if len(top_temp) > 0:
            return top_temp
        else:
            log.error("915 open>llastp is None")
            return df[:count].copy()

    if 930 < nowint <= 945:
        top_high = df[((df.open > df.llastp) & (df.low >= df.llastp))]
    elif 945 < nowint:
        if 'nlow' in df.columns:
            # top_high = df[ (df.nlow >= df.llastp) | (df.close >= df.nlow)]
            top_high = df[((df.nlow >= df.llastp) & (df.nlow >= df.low)) | (
                (df.nlow <= df.low) & (df.open == df.nlow))]
        else:
            top_high = df[((df.open > df.llastp) & (df.low > df.llastp)) | (
                df.percent > df['per%sd' % (duration)])]
    else:
        top_high = None

    if top_high is not None:
        top_high['upper'] = [round(
            (1 + 11.0 / 100) * x, 1) for x in top_high.ma10d]
        top_high['lower'] = [round(
            (1 - 9.0 / 100) * x, 1) for x in top_high.ma10d]
        top_high['ene'] = list(map(lambda x, y: round(
            (x + y) / 2, 1), top_high.upper, top_high.lower))
        if 930 < nowint < 1500:
            radio_t = cct.get_work_time_ratio()
        else:
            radio_t = 1

        top_high = top_high[(((top_high.buy > top_high.ene) & (top_high.volume / radio_t > 2))) | (
            ((top_high.lastv1d > top_high.lvol * 1.5)) & (top_high.lastp1d > top_high.ene))]
        if len(top_high) > count:
            top_high = top_high[(top_high.low > top_high.ene) | (
                (top_high.percent > 1) & (top_high.volume > 2))]
        top_temp = cct.combine_dataFrame(
            top_temp, top_high, col=None, compare=None, append=True, clean=True)

    return top_temp


def compute_perd_value(df, market_value=3, col='per'):

    if market_value==None or int(market_value) < 2:
        market_value = 3

    # temp = df[df.columns[(df.columns >= '%s1d' % (col)) & (df.columns <= '%s%sd' % (col, market_value))]]
    # temp = df.loc[:,df.columns.str.contains( "%s\d{1,2}d$"%(col),regex= True)]



    if int(market_value) < 10:
        temp =df.loc[:,df.columns.str.contains( "%s[1-%s]d$"%(col,market_value),regex= True)]
    else:
        if int(market_value) <= ct.compute_lastdays:
            _remainder = int(market_value)%10
        else:
            _remainder = int(ct.compute_lastdays)%10
        # df.loc[:,df.columns.str.contains( "%s[0-9][0-%s]d$"%(col,_remainder),regex= True)][:1]
        temp =df.loc[:,df.columns.str.contains( "%s([1-9]|1[0-%s])d$"%(col,_remainder),regex= True)]
    # temp = cct.get_col_market_value_df(df,col,market_value)


    # if  '%s%sd' % (col,market_value) == temp.T.index[-1]:
    #     df['%s%sd' % (col, market_value)] = temp.T.sum().apply(lambda x: round(x, 1))
    # else:
    #     df[temp.T.index[-1]] = temp.T.sum().apply(lambda x: round(x, 1))
    if col in ['lastv']:
        # df['%s%sd' % (col, market_value)] = ((temp.T/temp.T.shift(-1)).sum()/(int(market_value)-1)).apply(lambda x:round(x,1))
        df['%s%sd' % (col, market_value)] = ((temp.T/df.lowvol).sum()/(int(market_value))).apply(lambda x:round(x,1))
        df['volume0'] = df['volume'] 
        df['volume'] = df['%s%sd' % (col, market_value)]
    else:
        df['%s%sd' % (col, market_value)] = temp.T.sum().apply(lambda x: round(x, 1))
    return df

def getBollFilter_vect(df=None, boll=ct.bollFilter, duration=ct.PowerCountdl,
                            filter=True, ma5d=True, dl=14, percent=True, resample='d',
                            ene=False, upper=False, down=False, indexdff=True, cuminTrend=False,
                            top10=True, end=False):

    if df is None or df.empty:
        print("dataframe is None or empty")
        return df

    time_s = time.time()
    now_int = cct.get_now_time_int()
    radio_t = cct.get_work_time_ratio(resample=resample)

    # ===== 缓存全局值 =====
    gv = cct.GlobalValues()
    indexfibl = gv.getkey('indexfibl')
    sort_value = gv.getkey('market_sort_value')
    market_key = gv.getkey('market_key')
    market_value = gv.getkey('market_value')
    tdx_Index_Tdxdata = gv.getkey('tdx_Index_Tdxdata')
    market_va_filter = gv.getkey('market_va_filter')

    # ===== 处理 market_value =====
    try:
        market_value_f = float(market_value)
    except:
        market_value_f = 1

    if market_value_f != 1.1 and int(market_value_f) > ct.compute_lastdays:
        market_value_f = ct.compute_lastdays

    idx_k = int(market_value_f) if market_value_f >= 2 else 1

    # ===== 修正 perc 列 =====
    if resample in ['d', 'w'] and len(df) > 2:
        df['percent'] = df['percent'].clip(upper=10).round(2)

        # 自动选择 perc / per 列
        perc_cols = [c for c in df.columns if c.startswith('perc') and c != 'percent']
        per_cols = [c for c in df.columns if c.startswith('per') and c not in perc_cols + ['per1d', 'perlastp']]

        # ===== 初始化 percdf =====
        if gv.getkey('percdf') is None:
            percdf = cct.get_col_market_value_df(df, 'lasto', '6')
            percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lasth', '6'))
            percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lastl', '6'))
            percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'lastp', '15'))
            percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'ma5', '15'))
            percdf = cct.combine_dataFrame(percdf, cct.get_col_market_value_df(df, 'ma20', '15'))
            percdf = percdf.reset_index().drop_duplicates('code').set_index('code')
            gv.setkey('percdf', percdf)

    # ===== 向量化 perc_n 计算 =====
    nowd = 1
    cols_needed = ['open', 'close', 'high', 'low', 'lasto%sd'%nowd, 'lastp%sd'%nowd,
                   'lasth%sd'%nowd, 'lastl%sd'%nowd, 'ma5d', 'ma10d', 'nvol', 'lastv%sd'%nowd,
                   'upper', 'high4', 'max5', 'hmax', 'lastdu4']
    missing_cols = [c for c in cols_needed if c not in df.columns]
    for c in missing_cols:
        df[c] = 0  # 缺失列用0填充

    # 使用 numpy 向量化 func_compute_percd2021
    open_arr = df['open'].to_numpy()
    close_arr = df['close'].to_numpy()
    high_arr = df['high'].to_numpy()
    low_arr = df['low'].to_numpy()
    lasto_arr = df['lasto%sd'%nowd].to_numpy()
    lastp_arr = df['lastp%sd'%nowd].to_numpy()
    lasth_arr = df['lasth%sd'%nowd].to_numpy()
    lastl_arr = df['lastl%sd'%nowd].to_numpy()
    ma5_arr = df['ma5d'].to_numpy()
    ma10_arr = df['ma10d'].to_numpy()
    nvol_arr = (df['nvol']/radio_t).to_numpy() if 'nvol' in df.columns else np.zeros(len(df))
    lastv_arr = df['lastv%sd'%nowd].to_numpy() if 'lastv%sd'%nowd in df.columns else np.zeros(len(df))
    upper_arr = df['upper'].to_numpy() if 'upper' in df.columns else np.zeros(len(df))
    high4_arr = df['high4'].to_numpy() if 'high4' in df.columns else np.zeros(len(df))
    max5_arr = df['max5'].to_numpy() if 'max5' in df.columns else np.zeros(len(df))
    hmax_arr = df['hmax'].to_numpy() if 'hmax' in df.columns else np.zeros(len(df))
    lastdu4_arr = df['lastdu4'].to_numpy() if 'lastdu4' in df.columns else np.zeros(len(df))
    index_arr = df.index.to_numpy()
    # perc_n 计算向量化
    import numpy as np
    vec_func = np.vectorize(cct.func_compute_percd2021)
    df['perc_n'] = vec_func(
        open_arr, close_arr, high_arr, low_arr,
        lasto_arr, lastp_arr, lasth_arr, lastl_arr,
        ma5_arr, ma10_arr, nvol_arr, lastv_arr,
        upper_arr, high4_arr, max5_arr, hmax_arr,
        lastdu4_arr, index_arr, index_arr
    )

    # df['perc_n'] = cct.func_compute_percd2021(open_arr, close_arr, high_arr, low_arr,
    #                                               lasto_arr, lastp_arr, lasth_arr, lastl_arr,
    #                                               ma5_arr, ma10_arr, nvol_arr, lastv_arr,
    #                                               upper_arr, high4_arr, max5_arr, hmax_arr, lastdu4_arr,index_arr,index_arr)
   #  cct.func_compute_percd2021, 
   #  df['open'], df['close'], df['nhigh'], df['nlow'], df['lasto%sd' % nowd], df['lastp%sd' % (nowd)],

   # df['lasth%sd' % (nowd)], df['lastl%sd' % (nowd)], df['ma5d'], df['ma10d'], df['nvol'] / radio_t,
   #  df['lastv%sd' % (nowd)],df['upper'],df['high4'],df['max5'],df['hmax'],df['lastdu4'],df.index,df.index
    # ===== 类型转换 =====
    co2int = ['boll', 'op', 'fib', 'fibl', 'red', 'gren', 'ra']
    co2int = [c for c in co2int if c in df.columns]
    df[co2int] = df[co2int].astype(int)

    # ===== 时间段过滤 =====
    if cct.get_work_time() and 'b1_v' in df.columns and 'nvol' in df.columns:
        mask_b1 = (df.b1_v>0) | (df.nvol>0)
        df = df[mask_b1]

    # ===== 上下界过滤 =====
    if filter:
        # 统一时间段 mask
        mask_filter = ((df.buy > df.llastp) | (df.buy > df.hmax*ct.changeRatio) | (df.buy < df.lmin*ct.changeRatioUp))
        df = df[mask_filter]

    # ===== ENE 处理 =====
    if ene:
        if 'nclose' in df.columns:
            mask_ene = ((df.low > df.upper) | 
                        ((df.nopenRatio <= df.nclose) & (df.low >= df.nlow) & (df.close >= df.ncloseRatio)) |
                        ((df.nopenRatio <= df.nclose) & (df.close >= df.ncloseRatio) & (df.high >= df.nhigh)))
            df = df[mask_ene]
        else:
            df = df[((df.low >= df.nlow) & (df.close > df.llastp * ct.changeRatio))]

    print("getBollFilter cost: %.2f s" % (time.time()-time_s))
    log.info(f'indexfibl:{indexfibl} sort_value: {sort_value} market_key: {market_key} market_value: {market_value} tdx_Index_Tdxdata: {tdx_Index_Tdxdata} market_va_filter: {market_va_filter}\n')

    return df


def getBollFilter(df=None, boll=ct.bollFilter, duration=ct.PowerCountdl, filter=True, ma5d=True, dl=14, percent=True, resample='d', ene=False, upper=False, down=False, indexdff=True, cuminTrend=False, top10=True,end=False):

    time_s = time.time()
    radio_t = cct.get_work_time_ratio(resample=resample)
    df['lvolr%s' % (resample)] = df['volume']

    indexfibl = cct.GlobalValues().getkey('indexfibl')
    sort_value = cct.GlobalValues().getkey('market_sort_value')
    market_key = cct.GlobalValues().getkey('market_key')
    market_value = cct.GlobalValues().getkey('market_value')
    tdx_Index_Tdxdata = cct.GlobalValues().getkey('tdx_Index_Tdxdata')
    market_va_filter = cct.GlobalValues().getkey('market_va_filter')
    log.debug(f'indexfibl:{indexfibl} sort_value: {sort_value} market_key: {market_key} market_value: {market_value} market_va_filter: {market_va_filter}\n')
    log.debug(f'tdx_Index_Tdxdata: {tdx_Index_Tdxdata}')
    if market_value != '1.1' and int(float(market_value)) > ct.compute_lastdays:
        market_value = ct.compute_lastdays

    if market_value is not None and market_value != '1' and market_value != '1.1' and int(float(market_value)) >= 2:
        df= compute_perd_value(df, market_value, 'perc')
        df= compute_perd_value(df, market_value, 'per')
        df= compute_perd_value(df, market_value, 'lastv')
        if tdx_Index_Tdxdata is not None:
            tdx_Index_Tdxdata = compute_perd_value(tdx_Index_Tdxdata,market_value,'perc')
            tdx_Index_Tdxdata = compute_perd_value(tdx_Index_Tdxdata,market_value,'per')
        if market_key == '3' and tdx_Index_Tdxdata is not None:
            idx_k = tdx_Index_Tdxdata['perc%sd'%(int(float(market_value)))].max()
        else:

            idx_k = int(float(market_value)) if market_value is not None else 1
    else:
        idx_k = int(float(market_value))


    if df is None:
        print("dataframe is None")
        return None
    else:

        if resample in ['d','w'] and len(df) > 2:
            # df.loc[((df.percent >= 9.94) & (df.percent < 10.1)), 'percent'] = 10
            df['percent'] = df['percent'].apply(lambda x: round(x, 2))
            # time_ss = time.time()
            perc_col = [co for co in df.columns if co.find('perc') == 0]
            per_col = [co for co in df.columns if co.find('per') == 0]
            per_col = list(set(per_col) - set(perc_col) -
                           set(['per1d', 'perlastp']))

            perc_col.remove('percent')

            for co in perc_col:
                df[co] = df[co].apply(lambda x: round(x, 2))

            
            idx_rnd = random.randint(0, len(df) - 10) if len(df) > 10 else 0

            if cct.GlobalValues().getkey('percdf') is None:
                time_df =time.time()
                filter_key = '6'
                percdf = cct.get_col_market_value_df(df,'lasto',filter_key)
                percdf = cct.combine_dataFrame(percdf,cct.get_col_market_value_df(df,'lasth',filter_key))
                percdf = cct.combine_dataFrame(percdf,cct.get_col_market_value_df(df,'lastl',filter_key))
                percdf = cct.combine_dataFrame(percdf,cct.get_col_market_value_df(df,'lastp','15'))
                percdf = cct.combine_dataFrame(percdf,cct.get_col_market_value_df(df,'ma5','15'))
                percdf = cct.combine_dataFrame(percdf,cct.get_col_market_value_df(df,'ma20','15'))
                percdf = percdf.reset_index().drop_duplicates('code').set_index('code')
                cct.GlobalValues().setkey('percdf',percdf)
                print("timecol:%s"%(round(time.time()-time_df,2)),end=' ')

                
            if cct.get_work_time_duration():
                nowd, per1d=1, 1
                if 'nlow' in df.columns:
                    df['perc_n']=list(map(cct.func_compute_percd2021, df['open'], df['close'], df['nhigh'], df['nlow'], df['lasto%sd' % nowd], df['lastp%sd' % (nowd)],
                                     df['lasth%sd' % (nowd)], df['lastl%sd' % (nowd)], df['ma5d'], df['ma10d'], df['nvol'] / radio_t, df['lastv%sd' % (nowd)],df['upper'],df['high4'],df['max5'],df['hmax'],df['lastdu4'],df.index,df.index))
                else:                                                
                    df['perc_n']=list(map(cct.func_compute_percd2021, df['open'], df['close'], df['high'], df['low'], df['lasto%sd' % nowd], df['lastp%sd' % (nowd)],
                                     df['lasth%sd' % (nowd)], df['lastl%sd' % (nowd)], df['ma5d'], df['ma10d'], df['nvol'] / radio_t, df['lastv%sd' % (nowd)],df['upper'],df['high4'],df['max5'],df['hmax'],df['lastdu4'],df.index,df.index))
                if market_value == '0' and market_key == '3':
                    df['perc1d'] = df['perc_n']
                    perc_col.remove('perc1d')

            else:
                
                _top_all = df[df.close > 10]
                if _top_all.empty:
                    return  _top_all               
                if (_top_all['open'][1] == _top_all['lasto1d'][1]) and (_top_all['open'][0] == _top_all['lasto1d'][0]):
                    nowd, per1d=2, 1
                    df['perc_n']=list(map(cct.func_compute_percd2021, df['open'], df['close'], df['high'], df['low'], df['lasto%sd' % nowd], df['lastp%sd' % (nowd)],
                                         df['lasth%sd' % (nowd)], df['lastl%sd' % (nowd)], df['ma5d'], df['ma10d'], df['nvol'] / radio_t, df['lastv%sd' % (nowd)],df['upper'],df['high4'],df['max5'],df['hmax'],df['lastdu4'],df.index,df.index))
                                            
                    df['perc1d'] = df['perc_n']
                    perc_col.remove('perc1d')
                else:
                    nowd, per1d=1, 1
                    df['perc_n']=list(map(cct.func_compute_percd2021, df['open'], df['close'], df['high'], df['low'], df['lasto%sd' % nowd], df['lastp%sd' % (nowd)],
                                         df['lasth%sd' % (nowd)], df['lastl%sd' % (nowd)], df['ma5d'], df['ma10d'], df['nvol'] / radio_t, df['lastv%sd' % (nowd)],df['upper'],df['high4'],df['max5'],df['hmax'],df['lastdu4'],df.index,df.index))
                    
                    if market_value == '0' and market_key == '3':
                        df['perc1d'] = df['perc_n']
                        perc_col.remove('perc1d')
        else:
            df['percent']=(list(map(lambda x, y: round(
                (x - y) / y * 100, 1) if int(y) > 0 else 0, df.buy, df.lastp1d)))
    if 'fib' not in df.columns:
        df['fib']= 0
    if market_key == '1' or market_key == '4':
        # if cct.get_now_time_int() < 1530:
        filterlastday = 'lasth1d'
        filterma51d = 'ma51d'
        if len(df) > 0 and df.lastp1d[0] == df.close[0]:
            filterlastday = 'lasth2d'
            filterma51d = 'ma52d'

    if (market_key in ['1','2', '3','5','4','6','7','8','9','x','x1','x2']) :
        if market_key is not None and market_value is not None:
            if market_key == '3' and market_value not in ['1']:
                market_value= int(float(market_value))
                log.info("stf market_key:%s" % (market_key))
                idx_k= cct.get_col_in_columns(df, 'perc%sd', market_value)
                if market_va_filter is not None:
                    df= df[(df[("perc%sd" % (idx_k))] >= int(market_va_filter)) ]
                    cct.GlobalValues().setkey('market_va_filter',None)
            elif market_key == '2' and market_value not in ['1']:

                market_value= int(float(market_value))
                log.info("stf market_key:%s" % (market_key))
                idx_k= cct.get_col_in_columns(df, 'per%sd', market_value)
                if market_va_filter is not None:
                    df= df[(df[("per%sd" % (idx_k))] >= int(market_va_filter)) ]
                    cct.GlobalValues().setkey('market_va_filter',None)

            elif market_key in ['x1','x','6'] and market_value not in ['1']:
                
                if market_value == '1.1' and market_key in [ 'x']:
                    df['topR']=list(map(lambda x, op,lastp,close: round( x + 1 if x > 0 and close >= op > lastp  else x, 1), df.topR,df.open,df.per1d,df.close))
                    topr_up = list(set(df.topR.tolist()))
                    topRlist = list(set(map(lambda x: x  if x > 0 else 0, topr_up)))
                    if 0 in topRlist:
                        topRlist.remove(0)
                    df = df[df.topR.isin(topRlist)]
                else:
                    df= df[ (df[("%s" % (sort_value))] <= idx_k) ]

            elif market_key in ['x2','4','8','5','1','7','9'] and market_value not in ['1']:

                idx_k = int(float(market_value))
                if market_key not in ['1','5','7']:
                    idx_k = int(cct.GlobalValues().getkey('market_value'))
                    if market_value == '10' and market_key in ['4']:
                        df = df[df.percent < 8 ]
                    elif market_key in ['4']:
                        df = df[df.dff >= idx_k ]
                        if 'macd' in df.columns:
                            df = df.query('macd >= -0.02 and high >= max5 and close >= lastp1d')
                    else:
                        df= df[ (df[("%s" % (sort_value))] <= idx_k) ]
                else:
                    df= df[ (df[("%s" % (sort_value))] >= idx_k) ]


    co2int= ['boll', 'op',  'fib', 'fibl','red','gren']
    co2int.extend(['ra'])

    co2int= [inx for inx in co2int if inx in df.columns]

    for co in co2int:
        df[co]= df[co].astype(int)


    if cct.get_work_time() and 'b1_v' in df.columns and 'nvol' in df.columns:
        df= df[(df.b1_v > 0) | (df.nvol > 0)]

    if (cct.get_work_time() and cct.get_now_time_int() > 915 and cct.get_now_time_int() < 926):
        df['b1_v']= df['volume']
    else:
        dd= df[df.percent < 10]
        dd['b1_v']= dd['volume']
        df= cct.combine_dataFrame(df, dd.loc[:, ['b1_v']])

    if ene:
        pass
        if 'nclose' in df.columns:
            df= df[((df.buy > df.llastp)) | ((df['nclose'] > df['ene'] * ct.changeRatio) & (df['percent'] > -3) & (df.volume > 1.5)) |
                    ((df['nclose'] > df['upper'] * ct.changeRatio) & (df['buy'] > df['upper'] * ct.changeRatioUp)) | ((df['llastp'] > df['upper']) & (df['nclose'] > df['upper']))]
        else:
            df = df[((df.buy > df.llastp)) | ((df.buy > df.ene)) |
                    ((df.buy > df.upper) & (df.close > df.cmean))]

        if 'nlow' in df.columns and 930 < cct.get_now_time_int():
            if 'nhigh' in df.columns and 'nclose' in df.columns:
                df['ncloseRatio'] = [x * 0.99 for x in df.nclose]
                df['nopenRatio'] = [x * 0.99 for x in df.open]
                if 'nstd' in df.columns:
                    df['stdv'] = list(map(lambda x, y: round(
                        x / y * 100, 1), df.nstd, df.open))

                df = df[(df.low > df.upper) | (((df.nopenRatio <= df.nclose) & (df.low >= df.nlow) & (df.close >= df.ncloseRatio)) |
                                               ((df.nopenRatio <= df.nclose) & (df.close >= df.ncloseRatio) & (df.high >= df.nhigh)))]
            else:
                df = df[((df.low >= df.nlow) & (
                    df.close > df.llastp * ct.changeRatio))]

        if filter:

            if cct.get_now_time_int() > 915 and cct.get_now_time_int() <= 1000:
                df = df[((df.buy > df.llastp)) | (df.buy > df.hmax *
                                                  ct.changeRatio) | (df.buy < df.lmin * ct.changeRatioUp)]

            elif cct.get_now_time_int() > 1000 and cct.get_now_time_int() <= 1430:
                df = df[((df.buy > df.llastp)) | (df.buy > df.hmax *
                                                  ct.changeRatio) | (df.buy < df.lmin * ct.changeRatioUp)]
            else:
                df = df[((df.buy > df.llastp)) | (df.buy > df.hmax *
                                                  ct.changeRatio) | (df.buy < df.lmin * ct.changeRatioUp)]


            if 'vstd' in df.columns:
                df['hvRatio'] = list(map(lambda x, y: round(
                    x / y / cct.get_work_time_ratio(), 1), df.hv, df.lv))
                df['volRatio'] = (list(map(lambda x, y: round(
                    x / y / radio_t, 1), df.nvol.values, df.lv.values)))

                if 'nclose' in df.columns:
                    df = df[(((df.buy > df.lastp) & (df.nclose > df.lastp))) | ((
                        (df.percent > -5) & ((df.vstd + df.lvol) * 1.2 < df.nvol) & (df.nvol > (df.vstd + df.lvol))))]
                else:
                    df = df[(((df.buy > df.lastp))) | ((
                        (df.percent > -5) & ((df.vstd + df.lvol) * 1.2 < df.nvol) & (df.nvol > (df.vstd + df.lvol))))]

            if percent:
                pass
            per3d_l = 2
            percent_l = -1
            op_l = 3
    print(("bo:%0.1f" % (time.time() - time_s)), end=' ')

    if not end  and market_key in ['4','9']:
        if 930 < cct.get_now_time_int() < 1000:
            df = df.query('macd > -0.1 and macddif >= macddea*0.99')
            df = df.query('low >= ma201d')
            df = df.query('volume > 5')
        elif 1000 < cct.get_now_time_int() < 1100:
            df = df.query(' percent < 9.97 or 10.2 < percent < 19.95')
            df = df.query('low >= ma201d')
            df = df.query('macd >= -0.1 and macddif >= macddea*0.99')

        elif 1100 < cct.get_now_time_int() < 1400:
            df = df.query(' percent < 9.97 or 10.2 < percent < 19.95')
            df = df.query('low >= ma201d')
            df = df.query('macd >= -0.1 and macddif >= macddea*0.99')
            
        elif 1400 < cct.get_now_time_int() < 1445:
            df = df.query('close >= lasth1d')
        df = df.query('close > ma201d ')
    return df
    # return cct.reduce_memory_usage(df)

    # df = df[df.buy > df.cmean * ct.changeRatio]
    # else:
    #     df = df[df.buy > df.lmin]
    # ra * fibl + rah*fib +ma +kdj+rsi
#    time_s = time.time()
    # df['dff'] = (map(lambda x, y: round((x - y) / y * 100, 1), df['buy'].values, df['lastp'].values))
    # a = range(1,4)
    # b = range(3,6)
    # c = range(2,5)
    # (map(lambda ra,fibl,rah:(ra * fibl + rah),\
    #                      a,b,c ))

#    df['dff'] = (map(lambda ra, fibl,rah,:round(float(ra) * float(fibl) + float(rah),2),df['ra'].values, df['fibl'].values,df['rah'].values))

#    df['dff'] = (map(lambda ra, fibl,rah,fib,ma,kdj,rsi:round(ra * fibl + rah*fib +ma +kdj+rsi),\
#                         df['ra'].values, df['fibl'].astype(float).values,df['rah'].values,df['fib'].astype(float).values,df['ma'].values,\
#                         df['kdj'].values,df['rsi'].values))
    # df['diff2'] = df['dff'].copy()
    # pd.options.mode.chained_assignment = None
    # df.rename(columns={'dff': 'df2'}, inplace=True)
    # df['diff2'] = df['dff']

    # df['df2'] = (map(lambda ra, fibl,rah,fib,ma,kdj,rsi:round(eval(ct.powerdiff%(duration)),1),\
    #                      df['ra'].values, df['fibl'].values,df['rah'].values,df['fib'].values,df['ma'].values,\
    #                      df['kdj'].values,df['rsi'].values))


#    print "map time:%s"%(round((time.time()-time_s),2))
    # df.loc[:, ['fibl','op']] = df.loc[:, ['fibl','op']].astype(int)
    # df.loc[:, 'fibl'] = df.loc[:, 'fibl'].astype(int)

    # elif filter and cct.get_now_time_int() > 1015 and cct.get_now_time_int() <= 1445:
    #     df = df[((df.fibl < int(duration / 1.5)) &  (df.volume > 3)) | (df.percent > 3)]
    # print df
    # if 'ra' in df.columns and 'op' in df.columns:
    #     df = df[ (df.ma > 0 ) & (df.diff > 1) & (df.ra > 1) & (df.op >= 5) ]

def WriteCountFilter(df, op='op', writecount=ct.writeCount, end=None, duration=10):
    codel = []
    # market_value = cct.GlobalValues().getkey('market_value')
    # market_key = cct.GlobalValues().getkey('market_key')
    # if market_key == '2':
    #     market_value_perd = int(market_value) * 10
    if str(writecount) != 'all' and cct.isDigit(writecount):
        if end is None and int(writecount) > 0:
            # if int(writecount) < 101 and len(df) > 0 and 'percent' in df.columns:
            if int(writecount) < 101 and len(df) > 0:
                codel = df.index[:int(writecount)].tolist()
                # market_value = cct.GlobalValues().getkey('market_value')
                # market_key = cct.GlobalValues().getkey('market_key')
                # if market_key == '2':
                #     # market_value_perd = int(market_value) * 9.8
                #     market_value_perd = 9.8
                #     dd=df[ df['per%sd'%(market_value)] > market_value_perd ]
                #     df_list=dd.index.tolist()
                #     for co in df_list:
                #         if co not in codel:
                #             codel.append(co)
            else:
                if len(str(writecount)) >= 4:
                    codel.append(str(writecount).zfill(6))
                else:
                    print("writeCount DF is None or Wri:%s" % (writecount))
        else:
            if end is None:
                writecount = int(writecount)
                if writecount > 0:
                    writecount -= 1
                codel.append(df.index.tolist()[writecount])
            else:
                writecount, end = int(writecount), int(end)

                if writecount > end:
                    writecount, end = end, writecount
                if end < -1:
                    end += 1
                    codel = df.index.tolist()[writecount:end]
                elif end == -1:
                    codel = df.index.tolist()[writecount::]
                else:
                    if writecount > 0 and end > 0:
                        writecount -= 1
                        end -= 1
                    codel = df.index.tolist()[writecount:end]
    else:
        if df is not None and len(df) > 0:
            codel = df.index.tolist()
    return codel

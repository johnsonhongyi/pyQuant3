# coding=utf-8
import datetime
import os
import time

import numpy as np
import pandas as pd
import pandas_ta as ta
import talib as tl
import tushare as ts
import sys
sys.path.append("..")
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
import math
# log = LoggerFactory.getLogger("get_macd_kdj_rsi")
log = LoggerFactory.log
# log.setLevel(LoggerFactory.DEBUG)

# http://blog.sina.com.cn/s/blog_620987bf0102vlmz.html
# 获取股票列表
# code,代码 name,名称 industry,所属行业 area,地区 pe,市盈率 outstanding,流通股本 totals,总股本(万) totalAssets,总资产(万)liquidAssets,流动资产
# fixedAssets,固定资产 reserved,公积金 reservedPerShare,每股公积金 eps,每股收益 bvps,每股净资
# pb,市净率 timeToMarket,上市日期

limitCount = 15


def Get_Stock_List():
    df = ts.get_stock_basics().head(10)
#     print (df)
    return df


def algoMultiDay_trends(df, column='close', days=6, op=0, filter=True,lastday=ct.Power_last_da):
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    if filter:
        dt = tdd.get_duration_price_date(ptype='low', df=df, filter=True)
        df = df[df.index >= dt]
        days = len(df)
        idx_status = False
    else:
        idx_status = True
        if len(df) < days + 2:
            # days = len(df) - 2
            days = len(df)
    if df is not None and len(df) > 1:
        obo = 0
        if column in df.columns:
            close_df = pd.DataFrame(df.loc[:, column], columns=[column])
            for day in range(days, 1, -1):
                print(day)
                if idx_status:
                    tmpdf = close_df[-days - 2:-1 - day]
                    idx = -1 - day
                    idxl = idx - 1
                else:
                    tmpdf = close_df[-days:-day]
                    idx = -day
                    idxl = idx - 1 if abs(idx - 1) < len(df) else idx

                c_max = tmpdf.max().values
                c_min = tmpdf.min().values
                c_mean = tmpdf.mean().values
                # print len(df),days,idx,idx-1
                if math.isnan(df[column][idx]) or math.isnan(df[column][idxl]):
                    break
                nowp = round(df[column][idx], 2)
                lowp = round(df['low'][idx], 2)
                highp = round(df['high'][idx], 2)
                openp = round(df['open'][idx], 2)
                lastp = round(df[column][idxl], 2)
                # if nowp >= c_max and day == 0:
                # print (code,day,idx,idxl,tmpdf.index.values,nowp,c_max)
                if not math.isnan(c_max) and nowp >= c_max:
                    if openp > lowp * ct.changeRatio and nowp == highp and lowp > lastp:
                        if obo < 2:
                            obo += 1
                            op += 100
                        else:
                            op += 10

                else:
                    print(nowp, lastp, df.index[idx], df.index[idxl], tmpdf.index)
                    if nowp > lastp:
                        op += 1
                        if df['high'][idx] > df['high'][idxl]:
                            op += 5
                            if df['low'][idx] > df['low'][idxl]:
                                op += 3
                        else:
                            if lowp > lastp:
                                op -= 2.3
                            else:
                                op -= 5.3

                    else:
                        if obo > 2:
                            op += -100.3
                            log.error("code:%s obo down:-100.3 obo:%s" %
                                      (code, obo))
                            obo += 1
                        else:
                            if nowp <= lowp * ct.changeRatioUp:
                                op += -55.3
                                log.error(
                                    "code:%s obo down:-55.3 obo:%s" % (code, obo))
                            else:
                                op += -50.3
                                log.error(
                                    "code:%s obo down:-50.3 obo:%s" % (code, obo))
    return op


def algoMultiDay(df, column='close', days=ct.Power_Ma_Days, op=0,lastday=ct.Power_last_da):
    df = df.sort_index(ascending=True)
    # print df[:2],set(df.code)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
            
    if len(df) < days + 2:
        days = len(df) - 2
    # if len(df) < 2object0:
    #     days = int(len(df)/2)
    # elif 40 < len(df) < 60:
    #     days = 25
    # elif len(df) >= 60:
    #     days = 30
    # print days
    # df = df.fillna(0)
    if df is not None:
        obo = 0
        if column in df.columns:
            # for day in range(days,-1,-1):
            for day in range(days, 0, -1):
                # print day
                tmpdf = pd.DataFrame(
                    df.loc[:, column][-days - 2:-1 - day], columns=[column])
                # print tmpdf.index
                c_max = tmpdf.max().values
                c_min = tmpdf.min().values
                c_mean = tmpdf.mean().values
                idx = -1 - day
                # print len(df),days,idx,idx-1
                if math.isnan(df[column][idx]) or math.isnan(df[column][idx - 1]):
                    break
                nowp = round(df[column][idx], 2)
                lastp = round(df[column][idx - 1], 2)
                # if nowp >= c_max and day == 0:
                if nowp >= c_max:
                    op += 10
                    # print obo,df.index[idx],df.index[idx-1]
                    if obo < 0:
                        op += 100
                    else:
                        op += 10
                    obo += 1
                    continue
                elif nowp > c_mean:
                    if nowp > df['high'][idx - 1]:
                        op += 2
                    elif nowp > lastp:
                        op += 1
                    else:
                        op += 0.5

                elif nowp < c_min:
                    op += -10
                    obo = -1
                elif nowp < c_mean:
                    if obo > 0:
                        op += -100
                    else:
                        op += -1
                else:
                    if nowp > lastp:
                        op += 1
                        if df['high'][idx] > df['high'][idx - 1]:
                            op += 1
                        if df['low'][idx] > df['low'][idx - 1]:
                            op += 0.5
                        else:
                            op -= 1
                        if df['open'][idx] > df['close'][idx - 1] and df['close'][idx] > df['close'][idx - 1]:
                            op += 1
                        if df['open'][idx] < df['low'][idx - 1] and df['close'][idx] <= c_min:
                            op -= 10
                    else:
                        op += -1
        if obo > 0:
            op += 10.11
#        else:
#            op +=-days
    return op


def algoMultiTech(df, column='close', days=ct.Power_Ma_Days, op=0,lastday=ct.Power_last_da):
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    if len(df) < days:
        days = len(df) - 1
    if df is not None:
        if column in df.columns:
            for day in range(days):
                idx = -1 - day
                if math.isnan(df[column][idx]) or math.isnan(df[column][idx - 1]):
                    break
                nowp = round(df[column][idx], 2)
                lastp = round(df[column][idx - 1], 2)
#                if math.isnan(nowp) or math.isnan(lastp):
#                    break
                if nowp > lastp:
                    op
                else:
                    op += -1

    return op


def Get_BBANDS_algo(df,lastday=ct.Power_last_da):
    if isinstance(df, type(pd.DataFrame())):
        df = df.sort_index(ascending=True)
        df[['lowb%s'%dtype, 'midb%s'%dtype, 'upbb%s'%dtype,'bandwidth','percent']]  = ta.bbands(
            df['close'], length=20, std=2, ddof=0)
    else:
        df[['lowb%s'%dtype, 'midb%s'%dtype, 'upbb%s'%dtype,'bandwidth','percent']] = ta.bbands(
            np.array(df), length=20, std=2, ddof=0)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    operate = 0
    log.debug('updbb:%s midb:%s close:%s' %
              (df['upbb%s' % dtype][-1], df['midb%s' % dtype][-1], df.close[-1]))

    cnowp = df.close[-1]
    clastp = df.close[-2]
    hnowp = df.high[-1]
    hlastp = df.high[-2]
    lnowp = df.low[-1]
    llastp = df.low[-2]
    upbbp = df['upbb%s' % dtype][-1]
    lowbp = df['lowb%s' % dtype][-1]
    openp = df.open[-1]
    if df.close[-1] >= df['midb%s' % dtype][-1] and df['midb%s' % dtype][-1] > df['midb%s' % dtype][-2]:
        # print '5'
        operate = 1

#        if cnowp > clastp:
#            if hnowp > hlastp:
#                if cnowp > upbbp:
#                    operate+=5
#                elif lnowp > llastp:
#                    operate+=1
#                else:
#                    operate+=0.5
#
# elif lnowp > llastp:

        if hnowp == lnowp and cnowp > clastp:
            operate += 1
        if cnowp == hnowp and cnowp >= openp:
            if cnowp >= clastp:
                operate += 10
        if cnowp >= hnowp * ct.changeRatio and cnowp > openp and openp >= lnowp * ct.changeRatio:
            operate += 10
        if cnowp >= openp * 1.04 and openp >= lnowp * ct.changeRatio:
            operate += 5
        if cnowp > clastp and cnowp > upbbp:
            operate += 10
        elif hnowp > upbbp:
            operate += 5
    else:
        # print 'low'
        operate = -1
        if cnowp > clastp:
            if hnowp > hlastp:
                if cnowp < lowbp:
                    operate += -5
                elif lnowp > llastp:
                    operate += -1
                else:
                    operate += -0.5
        else:
            operate += -2.5
#    for cl in ['upbb%s'%dtype,'midb%s'%dtype,'lowb%s'%dtype]:
#        operate = algoMultiTech(df, column=cl, days=days, op=operate)
#        print operate
#    operate = op
    return operate


def Get_BBANDS(df, dtype='d', days=ct.Power_Ma_Days,dl=ct.PowerCountdl,dm=None,lastday=ct.Power_last_da):
    # dl = dl *2 if dl < 20 else dl
    if not isinstance(df,pd.DataFrame):
        code = df
        df = tdd.get_tdx_append_now_df_api(code,dl=dl,dm=dm,newdays=5)
        df = df.sort_index(ascending=True)
    else:
        code = None

    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]

    log.debug("BBANDS:%s" % (len(df)))
    if len(df) < limitCount:
        return (df, 10)
    df = df.sort_index(ascending=True)
    df[['lowb%s'%dtype, 'midb%s'%dtype, 'upbb%s'%dtype,'bandwidth','percent']] = ta.bbands(df['close'], length=20, std=2, ddof=0)
    
    # df['upbb%s' % dtype] = pd.Series(upperband, index=df.index)
    # df['midb%s' % dtype] = pd.Series(middleband, index=df.index)
    # df['lowb%s' % dtype] = pd.Series(lowerband, index=df.index)
    df = df.fillna(0)
    operate = 0
    log.debug('updbb:%s midb:%s close:%s' %
              (df['upbb%s' % dtype][-1], df['midb%s' % dtype][-1], df.close[-1]))

    cnowp = df.close[-1]
    clastp = df.close[-2]
    hnowp = df.high[-1]
    hlastp = df.high[-2]
    lnowp = df.low[-1]
    llastp = df.low[-2]
    upbbp = df['upbb%s' % dtype][-1]
    lowbp = df['lowb%s' % dtype][-1]
    openp = df.open[-1]
    if df.close[-1] >= df['midb%s' % dtype][-1] and df['midb%s' % dtype][-1] > df['midb%s' % dtype][-2]:
        # print '5'
        operate = 1

#        if cnowp > clastp:
#            if hnowp > hlastp:
#                if cnowp > upbbp:
#                    operate+=5
#                elif lnowp > llastp:
#                    operate+=1
#                else:
#                    operate+=0.5
        top_v,high_v = 5,5
        if hnowp == lnowp and cnowp > clastp:
            operate += 1
        if cnowp == hnowp and cnowp >= openp:
            if cnowp >= clastp:
                operate += top_v
        if cnowp >= hnowp * ct.changeRatio and cnowp > openp and openp >= lnowp * ct.changeRatio:
            operate += top_v
        if cnowp >= openp * 1.02 and openp >= lnowp * ct.changeRatio:
            operate += high_v
        # if cnowp > clastp and cnowp > upbbp:
        if cnowp > clastp and lnowp > upbbp:
            operate += top_v
        elif hnowp > upbbp:
            operate += high_v
    else:
        # print 'low'
        operate = -1
        if cnowp > clastp:
            if hnowp > hlastp:
                if cnowp < lowbp:
                    operate += -5
                elif lnowp > llastp:
                    operate += -1
                else:
                    operate += -0.5
        else:
            operate += -2.5
#    for cl in ['upbb%s'%dtype,'midb%s'%dtype,'lowb%s'%dtype]:
#        operate = algoMultiTech(df, column=cl, days=days, op=operate)
#        print operate
#    operate = op
    df = df.sort_index(ascending=False)
    if code is None:
        return df, operate
    else:
        return code,operate

# 修改了的函数，按照多个指标进行分析

# 按照MACD，KDJ等进行分析


def Get_TA(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    if dtype != 'd':
        # if not dtype == 'd':
        df = tdd.get_tdx_stock_period_to_type(
            df, dtype).sort_index(ascending=True)
        df['ma5%s' % dtype] = pd.rolling_mean(df.close, 5)
        df['ma10%s' % dtype] = pd.rolling_mean(df.close, 10)
        df['ma20%s' % dtype] = pd.rolling_mean(df.close, 20)

    operate_array1 = []
    operate_array2 = []
    operate_array3 = []
# index,0 - 6 date：日期 open：开盘价 high：最高价 close：收盘价 low：最低价 volume：成交量 price_change：价格变动 p_change：涨跌幅
# 7-12 ma5：5日均价 ma10：10日均价 ma20:20日均价 v_ma5:5日均量v_ma10:10日均量 v_ma20:20日均量
    dflen = df.shape[0]
    print(dflen)
    if dflen > 34:
        try:
            (df, operate1) = Get_MACD(df, dtype)
            (df, operate2) = Get_KDJ(df, dtype)
            (df, operate3) = Get_RSI(df, dtype)
        except Exception as e:
            # Write_Blog(e,Dist)
            print("error:%s" % e)
            pass
    else:
        log.error("dflen < 34:%s" % (len(df)))
        operate1 = -9
        operate2 = -9
        operate3 = -9
    # print len(df),operate1
    operate_array1.append(operate1)
    operate_array2.append(operate2)
    operate_array3.append(operate3)

    df['MACD%s' % dtype] = pd.Series(operate_array1, index=df.index)
    df['KDJ%s' % dtype] = pd.Series(operate_array2, index=df.index)
    df['RSI%s' % dtype] = pd.Series(operate_array3, index=df.index)

    df, op = Get_BBANDS(df, dtype)
    print("boll:%s ma:%s kdj:%s rsi:%s" % (op, operate_array1, operate_array2, operate_array3))
    df = df.sort_index(ascending=False)
    return df, op


def Get_MACD_OP(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    # 参数12,26,9
    if len(df) < limitCount:
        return (df, 1)
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
#    df=df.fillna(0)
    df[[ 'diff%s' % dtype,'ddea%s' % dtype, 'dea%s' % dtype]] = ta.macd(
        df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
#    SignalMA5 = ta.ma(macdsignal, timeperiod=5, matype=0)
#    SignalMA10 = ta.ma(macdsignal, timeperiod=10, matype=0)
#    SignalMA20 = ta.ma(macdsignal, timeperiod=20, matype=0)
    # 13-15 DIFF  DEA  DIFF-DEA
    # df['diff%s' % dtype] = pd.Series(macd, index=df.index)  # DIFF 13
    # df['dea%s' % dtype] = pd.Series(macdsignal, index=df.index)  # DEA  14
    # df['ddea%s' % dtype] = pd.Series(macdhist, index=df.index)  # DIFF-DEA  15
#    dflen = df.shape[0]
#    MAlen = len(SignalMA5)
    operate = 0
    # 2个数组 1.DIFF、DEA均为正，DIFF向上突破DEA，买入信号。 2.DIFF、DEA均为负，DIFF向下跌破DEA，卖出信号。
    # 待修改
#    diff=df.loc[df.index[-1],'diff%s'%dtype]
#    diff2=df.loc[df.index[-2],'diff%s'%dtype]
#    dea=df.loc[df.index[-1],'dea%s'%dtype]
#    dea2=df.loc[df.index[-2],'dea%s'%dtype]

    for cl in ['diff%s' % dtype, 'dea%s' % dtype, 'ddea%s' % dtype]:
        operate = algoMultiTech(df, column=cl, days=days, op=operate)
    df = df.sort_index(ascending=False)
    return (df, operate)

# 通过MACD判断买入卖出

def Get_MACD(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    # 参数12,26,9
    # increasing = True
    # if not df.index.is_monotonic_increasing:
    #     increasing = False
    #     df = df.sort_index(ascending=True)

    increasing = None
    if  df.index.is_monotonic_increasing:
        increasing = True
        df = df.sort_index(ascending=False)

    limit = 36
    if id_cout < limit:
        # temp_df = df.iloc[0]
        runtimes = limit-id_cout
        df = df.reset_index()
        # for t in range(runtimes):
        #     df.loc[df.shape[0]] = temp_df
        temp = df.loc[np.repeat(df.index[-1], runtimes)]
        df = df.append(temp)
    df=df.sort_index(ascending=False)
    # if len(df) > 1 + lastday:
    #     if lastday != 0:
    #         df = df[:-lastday]
    # if len(df) < limitCount:
    #     return (df, 1)


    # df=df.fillna(0)
    # macd=DIF，signal=DEA，hist=BAR

    # df[[ 'macd%s' % dtype,'ddea%s' % dtype, 'dea%s' % dtype]] = tl.MACD(
    #     df['close'], fastperiod=12, slowperiod=26, signalperiod=9)

    df.loc[:, 'macddif'], df.loc[:, 'macddea'], df.loc[:, 'macd'] = tl.MACD(
        df['close'], fastperiod=12, slowperiod=26, signalperiod=9) 
    # data.loc[:, 'diff'], data.loc[:, 'dea'], data.loc[:, 'macd'] = tl.MACD(
    #     data['close'].values, fastperiod=5, slowperiod=34, signalperiod=5)
    #     # data['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    
    df['macddif'] = round( df['macddif'], 2)
    df['macddea'] = round( df['macddea'], 2)
    df['macd'] = round( df['macd']*2, 2)
    # data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    # data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    # data['macd'].values[np.isnan(data['macd'].values)] = 0.0

    if df.index.name != 'date':
        df=df[-id_cout:].set_index('date')
    else:
        df=df[-id_cout:]
        
    if increasing is not None:
        df = df.sort_index(ascending=increasing)

    return df

def Get_MACD_o(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    # 参数12,26,9
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    if len(df) < limitCount:
        return (df, 1)
#    df=df.fillna(0)
    df[[ 'diff%s' % dtype,'ddea%s' % dtype, 'dea%s' % dtype]] = ta.macd(
        df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
    # macd=DIF，signal=DEA，hist=BAR
    # df[[ 'macd' % dtype,'signal' % dtype, 'hist' % dtype]] = ta.macd(
    #     df['close'], fastperiod=5, slowperiod=26, signalperiod=5)
    SignalMA5 = ta.ma("sma",df['dea%s' % dtype], length=5)
    SignalMA10 = ta.ma("sma",df['dea%s' % dtype], length=10)
    SignalMA20 = ta.ma("sma",df['dea%s' % dtype], length=20)
    # 13-15 DIFF  DEA  DIFF-DEA
    # df['diff%s' % dtype] = pd.Series(macd, index=df.index)  # DIFF 13
    # df['dea%s' % dtype] = pd.Series(macdsignal, index=df.index)  # DEA  14
    # df['ddea%s' % dtype] = pd.Series(macdhist, index=df.index)  # DIFF-DEA  15
    dflen = df.shape[0]
    MAlen = len(SignalMA5)
    operate = 0
    dd = df.dropna()
    # print(dd[['diffd','dead','ddead']],dd.ddead.argmin())
    # 2个数组 1.DIFF、DEA均为正，DIFF向上突破DEA，买入信号。 2.DIFF、DEA均为负，DIFF向下跌破DEA，卖出信号。
    # 待修改
    diff = df.loc[df.index[-1], 'diff%s' % dtype]
    diff2 = df.loc[df.index[-2], 'diff%s' % dtype]
    dea = df.loc[df.index[-1], 'dea%s' % dtype]
    dea2 = df.loc[df.index[-2], 'dea%s' % dtype]

    if diff > 0:
        if dea > 0:
            if diff > dea and diff2 <= dea2:
                operate = operate + 10  # 买入

    else:
        if dea < 0:
            if diff == dea2:
                operate = operate - 10  # 卖出

    # 3.DEA线与K线发生背离，行情反转信号。
    ma5 = df.loc[df.index[-1], 'ma5%s' % dtype]  # 7
    ma10 = df.loc[df.index[-1], 'ma10%s' % dtype]  # 8
    ma20 = df.loc[df.index[-1], 'ma20%s' % dtype]  # 9

    if ma5 >= ma10 and ma10 >= ma20:  # K线上涨
        if SignalMA5[MAlen - 1] <= SignalMA10[MAlen - 1] and SignalMA10[MAlen - 1] <= SignalMA20[MAlen - 1]:  # DEA下降
            operate = operate - 1
    elif ma5 <= ma10 and ma10 <= ma20:  # K线下降
        if SignalMA5[MAlen - 1] >= SignalMA10[MAlen - 1] and SignalMA10[MAlen - 1] >= SignalMA20[MAlen - 1]:  # DEA上涨
            operate = operate + 1

    # 4.分析MACD柱状线，由负变正，买入信号。
    diffdea = df.loc[df.index[-1], 'ddea%s' % dtype]
    # diffdea2 = df.loc[df.index[-2],'macdhist%s'%dtype]

    if diffdea > 0 and dflen > 30:
        for i in range(1, 26):
            if df.loc[df.index[-1 - i], 'ddea%s' % dtype] <= 0:
                operate = operate + 5
                break
            # 由正变负，卖出信号
    if diffdea < 0 and dflen > 30:
        dayl = 26 if len(df) > 26 else len(df)
        for i in range(1,):
            if df.loc[df.index[-1 - i], 'ddea%s' % dtype] >= 0:
                operate = operate - 5
                break
    for cl in ['diff%s' % dtype, 'dea%s' % dtype]:
        operate = algoMultiTech(df, column=cl, days=days, op=operate)
    df = df.sort_index(ascending=False)
    return (df, operate)


# 通过KDJ判断买入卖出
def Get_KDJ(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    # 参数9,3,3
    if len(df) < limitCount:
        return (df, 1)
    else:
        df = df.sort_index(ascending=True)
        if len(df) > 1 + lastday:
            if lastday != 0:
                df = df[:-lastday]
        if not 'ma5d' in df.columns:
            # newstock
            df['ma5d'] = pd.rolling_mean(df.close, 5)
            df['ma10d'] = pd.rolling_mean(df.close, 10)
            df['ma20d'] = pd.rolling_mean(df.close, 20)

        df = df.sort_index(ascending=True)
        df[['slowk%s' % dtype,'slowd%s' % dtype]] = ta.stoch(df['high'], (df['low']),(
            df['close']), k=9, d=3, slowk_matype=0, smooth_k=3)

        slowkMA5 = ta.ma("sma",df['slowk%s' % dtype], length=5)
        slowkMA10 = ta.ma("sma",df['slowk%s' % dtype], length=10)
        slowkMA20 = ta.ma("sma",df['slowk%s' % dtype], length=20)
        slowdMA5 = ta.ma("sma",df['slowd%s' % dtype], length=5)
        slowdMA10 = ta.ma("sma",df['slowd%s' % dtype], length=10)
        slowdMA20 = ta.ma("sma",df['slowd%s' % dtype], length=20)

        # 16-17 K,D
        # df['slowk%s' % dtype] = pd.Series(slowk, index=df.index)  # K
        # df['slowd%s' % dtype] = pd.Series(slowd, index=df.index)  # D
        dflen = df.shape[0]
        MAlen = len(slowkMA5)
        operate = 0

        kdjk = df.loc[df.index[-1], 'slowk%s' % dtype]
        kdjk2 = df.loc[df.index[-2], 'slowk%s' % dtype]
        kdjd = df.loc[df.index[-1], 'slowd%s' % dtype]
        kdjd2 = df.loc[df.index[-2], 'slowd%s' % dtype]

        ma5 = df.loc[df.index[-1], 'ma5%s' % dtype]
        ma10 = df.loc[df.index[-1], 'ma10%s' % dtype]
        ma20 = df.loc[df.index[-1], 'ma20%s' % dtype]

        # print kdjk,kdjk2,kdjd,kdjd2
        # 1.K线是快速确认线——数值在90以上为超买，数值在10以下为超卖；D大于80时，行情呈现超买现象。D小于20时，行情呈现超卖现象。
    #    if kdjk>=90:
    #        operate = operate - 3
    #    elif kdjk<=10:
    #        operate = operate + 3
    #
    #    if kdjd>=80:
    #        operate = operate - 3
    #    elif kdjd<=20:
    #        operate = operate + 3
    #    if len(kdjk) >1:
    #        raise Exception("Data not one,Drop_duplicates")
        # 2.上涨趋势中，K值大于D值，K线向上突破D线时，为买进信号。#待修改
        if kdjk > kdjd and kdjk2 <= kdjd2:
            operate = operate + 10
        # 下跌趋势中，K小于D，K线向下跌破D线时，为卖出信号。#待修改
        elif kdjk < kdjd and kdjk2 >= kdjd2:
            operate = operate - 10

        # 3.当随机指标与股价出现背离时，一般为转势的信号。
        if ma5 >= ma10 and ma10 >= ma20:  # K线上涨
            if (slowkMA5[MAlen - 1] <= slowkMA10[MAlen - 1] and slowkMA10[MAlen - 1] <= slowkMA20[MAlen - 1]) or \
               (slowdMA5[MAlen - 1] <= slowdMA10[MAlen - 1] and slowdMA10[MAlen - 1] <= slowdMA20[MAlen - 1]):  # K,D下降
                operate = operate - 1
        elif ma5 <= ma10 and ma10 <= ma20:  # K线下降
            if (slowkMA5[MAlen - 1] >= slowkMA10[MAlen - 1] and slowkMA10[MAlen - 1] >= slowkMA20[MAlen - 1]) or \
               (slowdMA5[MAlen - 1] >= slowdMA10[MAlen - 1] and slowdMA10[MAlen - 1] >= slowdMA20[MAlen - 1]):  # K,D上涨
                operate = operate + 1
        for cl in ['slowk%s' % dtype, 'slowd%s' % dtype]:
            operate = algoMultiTech(df, column=cl, days=days, op=operate)
        df = df.sort_index(ascending=False)
    return (df, operate)

#ASI
def Get_Asi(df):
    df['asi']


# 通过RSI判断买入卖出
def Get_RSI(df, dtype='d', days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    # 参数14,5
    if len(df) < limitCount:
        return (df, 1)
    df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    df['slowreal%s' % dtype] = ta.rsi(df['close'], length=14)
    df['fastreal%s' % dtype] = ta.rsi(df['close'], length=5)

    slowrealMA5 = ta.ma("sma",df['slowreal%s' % dtype], length=5)
    slowrealMA10 = ta.ma("sma",df['slowreal%s' % dtype], length=10)
    slowrealMA20 = ta.ma("sma",df['slowreal%s' % dtype], length=20)
    fastrealMA5 = ta.ma("sma",df['fastreal%s' % dtype], length=5)
    fastrealMA10 = ta.ma("sma",df['fastreal%s' % dtype], length=10)
    fastrealMA20 = ta.ma("sma",df['fastreal%s' % dtype], length=20)
    # 18-19 慢速real，快速real
    # df['slowreal%s' % dtype] = pd.Series(slowreal, index=df.index)  # 慢速real 18
    # df['fastreal%s' % dtype] = pd.Series(fastreal, index=df.index)  # 快速real 19
    dflen = df.shape[0]
    MAlen = len(slowrealMA5)
    operate = 0

    slow = df.loc[df.index[-1], 'slowreal%s' % dtype]
    slow2 = df.loc[df.index[-2], 'slowreal%s' % dtype]
    fast = df.loc[df.index[-1], 'fastreal%s' % dtype]
    fast2 = df.loc[df.index[-2], 'fastreal%s' % dtype]
    # RSI>80为超买区，RSI<20为超卖区
#    if slow>80 or fast>80:
#        operate = operate - 2
#    elif slow<20 or fast<20:
#        operate = operate + 2

    # RSI上穿50分界线为买入信号，下破50分界线为卖出信号
    if (slow2 <= 50 and slow > 50) or (fast2 <= 50 and fast > 50):
        operate = operate + 4
    elif (slow2 >= 50 and slow < 50) or (fast2 >= 50 and fast < 50):
        operate = operate - 4

    ma5 = df.loc[df.index[-1], 'ma5%s' % dtype]
    ma10 = df.loc[df.index[-1], 'ma10%s' % dtype]
    ma20 = df.loc[df.index[-1], 'ma20%s' % dtype]

    # RSI掉头向下为卖出讯号，RSI掉头向上为买入信号
    if ma5 >= ma10 and ma10 >= ma20:  # K线上涨
        if (slowrealMA5[MAlen - 1] <= slowrealMA10[MAlen - 1] and slowrealMA10[MAlen - 1] <= slowrealMA20[MAlen - 1]) or \
           (fastrealMA5[MAlen - 1] <= fastrealMA10[MAlen - 1] and fastrealMA10[MAlen - 1] <= fastrealMA20[MAlen - 1]):  # RSI下降
            operate = operate - 1
    elif ma5 <= ma10 and ma10 <= ma20:  # K线下降
        if (slowrealMA5[MAlen - 1] >= slowrealMA10[MAlen - 1] and slowrealMA10[MAlen - 1] >= slowrealMA20[MAlen - 1]) or \
           (fastrealMA5[MAlen - 1] >= fastrealMA10[MAlen - 1] and fastrealMA10[MAlen - 1] >= fastrealMA20[MAlen - 1]):  # RSI上涨
            operate = operate + 1

    # 慢速线与快速线比较观察，若两线同向上，升势较强；若两线同向下，跌势较强；若快速线上穿慢速线为买入信号；若快速线下穿慢速线为卖出信号
    if fast > slow and fast2 <= slow2:
        operate = operate + 10
    elif fast < slow and fast2 >= slow2:
        operate = operate - 10
    for cl in ['slowreal%s' % dtype, 'fastreal%s' % dtype]:
        operate = algoMultiTech(df, column=cl, days=days, op=operate)
    df = df.sort_index(ascending=False)
    return (df, operate)


def Output_Csv(df, Dist):
    TODAY = datetime.date.today()
    CURRENTDAY = TODAY.strftime('%Y-%m-%d')
#     reload(sys)
#     sys.setdefaultencoding( "gbk" )
    print("write csv")
    df.to_csv(Dist + CURRENTDAY + 'stock-macd-kdj.csv', encoding='gbk')  # 选择保存


def Close_machine():
    o = "c:\\windows\\system32\\shutdown -s"
    os.system(o)


# 日志记录
def Write_Blog(strinput, Dist):
    TODAY = datetime.date.today()
    CURRENTDAY = TODAY.strftime('%Y-%m-%d')
    TIME = time.strftime("%H:%M:%S")
    print("Blog")
    # 写入本地文件
    fp = open(Dist + 'blog.txt', 'a')
    fp.write('------------------------------\n' +
             CURRENTDAY + " " + TIME + " " + strinput + '  \n')
    fp.close()
    time.sleep(1)


def get_All_Count(code, dl=None, start=None, end=None, days=ct.Power_Ma_Days,lastday=ct.Power_last_da):
    s = time.time()
    if start is not None or end is not None:
        dl = None
    # else:
    #     dl = int(dl*2)
    df = tdd.get_tdx_append_now_df_api(
        code, start=start, end=end, dl=dl).sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    dd, boll = Get_BBANDS(df, dtype='d', days=days,lastday=lastday)
    print('boll:%s' % (boll), end=' ')
    dd, kdj = Get_KDJ(dd, days=days,lastday=lastday)
    print('kdj:', kdj, end=' ')
    dd, macd = Get_MACD_OP(dd, days=days,lastday=lastday)
    print(' macd:%s' % (macd), end=' ')
    dd, rsi = Get_RSI(dd, days=days)
    print('RSI:%s' % (rsi), end=' ')
    ma = algoMultiDay(dd, column='close', days=days,lastday=lastday)
    print('ma:', ma, end=' ')
#    sys.exit()
    # print dd.shape,dd.loc[:,['close','upbbd','midbd','lowbd']][:2]
    dtype = 'd'
    bollCT = 0
    for cl in ['upbb%s' % dtype, 'midb%s' % dtype, 'lowb%s' % dtype]:
        bollCT += algoMultiTech(dd, column=cl, days=days, op=bollCT,lastday=lastday)
    print('bollCT:', bollCT, end=' ')
    print("time:%0.3f" % (time.time() - s), end=' ')
    return boll, kdj, macd, rsi, ma, bollCT


def powerStd(code=None, df=None, ptype='close', dl=60,lastday=ct.Power_last_da):
    if df is None and code is not None:
        df = tdd.get_tdx_Exp_day_to_df(code, dl=dl)
        df = df.sort_index(ascending=True)
    if len(df) > 1 + lastday:
        if lastday != 0:
            df = df[:-lastday]
    nowT = 'df.%s' % (ptype)
    nowS = eval(nowT)
    if ptype in df.columns:
        res = np.std(nowS)
    else:
        log.warn("ptype is not in columns")
    # print nowS[:3]
    return res

if __name__ == '__main__':
    # df = Get_Stock_List()
    # Dist = 'E:\\Quant\\'
    # df = Get_TA(df,Dist)
    # df = get_kdate_data('sh')
    # code='300110'
    #    code='300201'
    import sys
    # print powerStd('600208',ptype='vol')
    code = '603887'
    code = '600600'
    # codel=['600917','300638','002695','601555','002486','600321','002437','399006','999999']
    # codel = ['300661', '600212', '300153', '603580']
    # codel=['603887']
    # dl = 21
    # for code in codel:
    #     df = tdd.get_tdx_append_now_df_api(
    #         code, dl=dl).sort_index(ascending=True)
    # # print algoMultiDay(df, column='close')
    #     print "code:%s : %s" % (code, algoMultiDay_trends(df, column='close'))
    # dm = tdd.get_sina_data_df(code)
    dm2 = tdd.get_tdx_Exp_day_to_df(code)
    # dm = tdd.get_tdx_power_now_df(code)
    dm = tdd.get_tdx_power_now_df(code)
    # print("tt",Get_BBANDS(code,'d',5,ct.PowerCountdl,dm)) 
    # time_st=time.time()
    macd = Get_MACD(dm)
    macd2 = Get_MACD(dm2)

    import ipdb;ipdb.set_trace()

    dm = tdd.get_sina_data_df(codel)

    results = cct.to_mp_run_async(Get_BBANDS,codel,dtype='d',days=5,dl=ct.PowerCountdl,dm=dm)
    # results=[]
    # for code in codel:
        # results.append(Get_BBANDS(code,'d',5,ct.PowerCountdl,dm))  
    bolldf = pd.DataFrame(results, columns=['code','boll'])  
    bolldf = bolldf.set_index('code')
    print("t:%.2f %s"%(time.time()-time_st,bolldf))
#    code='600321'
#    code:002732 boll: 45 ma: 6.0  macd:-1 RSI:0 kdj: 3 time:0.0241
#    code:002623 boll: 41 ma: 10.0  macd:-5 RSI:4 kdj: -1 time:0.0216
    days = 5
    dl = 60
    # for x in range(9,30):
    # for x in ['000737','002695','601555','002486','600321','002437','399006','999999']:get_All_Count(x,9)
    # sys.exit(0)
    for code in codel:
        df = tdd.get_tdx_append_now_df_api(
            code, dl=int(dl * 1)).sort_index(ascending=True)
    #    df = tdd.get_tdx_power_now_df(code,dl=30)
        # print df[:2]
        # print "len:",len(df)
        s = time.time()
        print(('code:%s' % (code)), end=' ')
        dd, op = Get_BBANDS(df, dtype='d', days=days)
        print('boll:', op)
        print(dd.shape, dd.loc[:, ['close', 'upbbd', 'midbd', 'lowbd']][:2])
#        print dd[:5]
        # sys.exit(0)
        dtype = 'd'
        operate = 0
        for cl in ['upbb%s' % dtype, 'midb%s' % dtype, 'lowb%s' % dtype]:
            operate += algoMultiTech(dd, column=cl, days=days, op=operate)
        print('bollcalgoMultiTech:', operate, end=' ')
        operate = algoMultiDay(df, column='close', days=days)
        print('ma:', operate, end=' ')
        dd, op = Get_MACD_OP(df, days=days)
        # dd, op = Get_MACD(df, days=days)
        print(' macd:%s' % (op), end=' ')
        dd, op = Get_RSI(df, days=days)
        print('RSI:%s' % (op), end=' ')
        import sys
    #    sys.exit()
        dd, op = Get_KDJ(df, days=days)
        print('kdj:', op, end=' ')
        print("time:%0.3f" % (time.time() - s))
#    sys.exit()
    while 1:
        code = input('pls:')
        if len(code) != 6:
            continue
        else:
            df = tdd.get_tdx_append_now_df_api(code, dl=300)
            df = tdd.get_tdx_stock_period_to_type(df)
            
            # print df[:2]
            # print "len:",len(df)
            s = time.time()
            print(('code:%s' % (code)), end=' ')
            dd, op = Get_BBANDS(df, dtype='d', days=days)
            print('boll:', op, end=' ')
            dtype = 'd'
            operate = 0
            for cl in ['upbb%s' % dtype, 'midb%s' % dtype, 'lowb%s' % dtype]:
                operate = algoMultiTech(dd, column=cl, days=days, op=operate)
            print('bollc:', operate, end=' ')
            operate = algoMultiDay(df, column='close', days=days)
            print('ma:', operate, end=' ')
            dd, op = Get_MACD_OP(df, days=days)
            print(' macd:%s' % (op), end=' ')
            dd, op = Get_RSI(df, days=days)
            print('RSI:%s' % (op), end=' ')
            import sys
        #    sys.exit()
            dd, op = Get_KDJ(df, days=days)
            print('kdj:', op, end=' ')
            print("time:%0.3f" % (time.time() - s))
    # print df[:3]
    # df = Get_BBANDS(df)
    # df = Get_TA(df)
    # a,op = Get_BBANDS(df, dtype='d')
    # print df[:2]
    # print op,len(df)
    # for dtype in ['w','m']:
    # for dtype in ['w']:
        # df = tdd.get_tdx_stock_period_to_type(df, dtype).sort_index(ascending=True).set_index('date')
        # df = Get_TA(df,dtype)
    # print df.columns
    colmdw = ['name', 'code', 'open', 'high', 'low', 'close',
              'ma5d', 'ma5w', 'ma10d', 'ma10w', 'ma20d', 'ma20w', 'MACDd', 'MACDw', 'KDJd', 'KDJw', 'RSId', 'RSIw',
              'upbbd', 'midbd']
    colmd = ['name', 'code', 'open', 'high', 'low', 'close',
             'ma5d', 'ma10d', 'ma20d', 'MACDd', 'KDJd', 'RSId',
             'upbbd', 'midbd']
    colmaw = ['name', 'code', 'open', 'high', 'low', 'close',
              'ma5d', 'ma10d', 'ma20d', 'MACDd', 'MACDw', 'KDJd', 'KDJw', 'RSId', 'RSIw',
              'upbbd',  'upbbw', 'midbd', 'midbw', ]
    # print ("df:"),df.loc[df.index[0],colmd]
    col = ['code', 'open', 'high', 'low', 'close', 'vol', 'amount', 'name',
           'ma5d', 'ma10d', 'ma20d', 'diffd', 'dead', 'ddead', 'slowkd',
           'slowdd', 'slowreald', 'fastreald', 'MACDd', 'KDJd', 'RSId',
           'upbbd', 'midbd', 'lowbd']
    # time.sleep(1)
    # Close_machine()

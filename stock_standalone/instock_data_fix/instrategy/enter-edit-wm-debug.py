#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import imp
import numpy as np
import talib as tl
import pandas as pd
import datetime
import time


__author__ = 'myh '
__date__ = '2023/3/10 '


# 量比大于2
# 例如：
#   2017-09-26 2019-02-11 京东方A
#   2019-03-22 浙江龙盛
#   2019-02-13 汇顶科技
#   2019-01-29 新城控股
#   2017-11-16 保利地产

def get_work_day_status():
    today = datetime.datetime.today().date()
    day_n = int(today.strftime("%w"))
    if day_n > 0 and day_n < 6:
        return True
    else:
        return False
    
def get_now_time_int():
    return int(datetime.datetime.now().strftime("%H%M"))

# def get_now_time_int():
#     now_t = datetime.datetime.now().strftime("%H%M")
#     return int(now_t)

def get_work_time_duration():
    # return True
    now_t = get_now_time_int()
    if not get_work_day_status():
        return False
    # if (now_t > 1132 and now_t < 1300) or now_t < 915 or now_t > 1502:
    if now_t < 930 or now_t > 1500:
        
        return False
        # return True
    else:
        # if now_t > 1300 and now_t <1302:
            # sleep(random.randint(5, 120))
        return True
    
def get_work_time_ratio():
    initx = 6.5
    stepx = 0.5
    init = 0
    initAll = 10
    now = time.localtime()
    ymd = time.strftime("%Y:%m:%d:", now)
    hm1 = '09:30'
    hm2 = '13:00'
    all_work_time = 14400
    d1 = datetime.datetime.now()
    now_t = get_now_time_int()
    # d2 = datetime.datetime.strptime('201510111011','%Y%M%d%H%M')
    if now_t >= 1500 or now_t < 930:
        return 1.0
    elif now_t > 915 and now_t <= 930:
        d2 = datetime.datetime.strptime(ymd + '09:29', '%Y:%m:%d:%H:%M')
        d1 = datetime.datetime.strptime(ymd + '09:30', '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 930 and now_t <= 1000:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1000 and now_t <= 1030:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 2
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1030 and now_t <= 1100:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 3
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1100 and now_t <= 1130:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 4
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1130 and now_t < 1300:
        init += 4
        return 0.5 / (initx + init * stepx) * initAll

    elif now_t > 1300 and now_t <= 1330:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 5
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1330 and now_t <= 1400:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 6
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1400 and now_t <= 1430:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 7
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    else:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        return round((ds + 7200) / all_work_time, 3)

def get_today_duration(startday, endday=None):
    if startday is not None and len(startday) > 6:
        if endday:
            today = datetime.datetime.strptime((endday), '%Y-%m-%d').date()
        else:
            today = datetime.date.today()
        # if get_os_system() == 'mac':
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        # else:
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        last_day = datetime.datetime.strptime(startday, '%Y-%m-%d').date()
        
        duration_day = int((today - last_day).days)
    else:
        duration_day = None
    return (duration_day)


def get_tdx_stock_period_to_type(df, period_day='W-FRI', periods=5, ncol=None, ratiodays=True):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """
    #快速日期处理
    #https://www.likecs.com/show-204682607.html
    stock_data = df.copy()
    period_type = period_day
    if 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
    stock_data['date'] = stock_data.index
    lastday = stock_data.date.values[-1]
    lastday2 = stock_data.date.values[-2]
    duration_day = get_today_duration(lastday2,lastday)
    # print("duration:%s"%(duration_day))
    
    # if duration_day > 3:
    #     if 'date' in stock_data.columns:
    #         stock_data = stock_data.drop(['date'], axis=1)
    #     return stock_data.reset_index()
    
    indextype = True if stock_data.index.dtype == 'datetime64[ns]' else False
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
        'open'].resample(period_type).last()
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
            duratio = int(str(datetime.datetime.strptime(lastWeek1, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[:2])
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
    period_stock_data['volume'] = stock_data[
        'volume'].resample(period_type).sum()
    if ratiodays:
        period_stock_data['amount'] = period_stock_data['amount'].apply(lambda x: round(x / ratio_d, 1))
        period_stock_data['volume'] = period_stock_data['volume'].apply(lambda x: round(x / ratio_d, 1))
                
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

def check_macd_status(df,threshold=60,period_day=False):
    # macd
    data = df.copy()
    data.loc[:, 'diff'], data.loc[:, 'dea'], data.loc[:, 'macd'] = tl.MACD(
        data['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    data['macd'].values[np.isnan(data['macd'].values)] = 0.0
    # diff_max =  data.iloc[-threshold:]['diff'].max()
    p_diff =  data.iloc[-1]['diff']
    p_dea =  data.iloc[-1]['dea']
    p_macd = data.iloc[-1]['macd']
    last_macd = data.iloc[-1]['macd']
    last2_macd = data.iloc[-2]['macd']
    if period_day:
        #Week and month
        if last_macd > last2_macd and p_diff > 0 and p_dea > 0 and p_macd > 0 and p_diff > p_dea:
            return True
        else:
            return False
        
    elif last_macd > last2_macd and p_diff > p_dea  and p_macd > 0 :
        
        return True
    else:
        return False
    
def check_volume(code_name, data, date=None, threshold=60):
    if date is None:
        end_date = code_name[0]
    else:
        end_date = date.strftime("%Y-%m-%d")
    if end_date is not None:
        mask = (data['date'] <= end_date)
        data = data.loc[mask].copy()
    if len(data.index) < threshold:
        return False

    p_change = data.iloc[-1]['p_change']

    last_close = data.iloc[-1]['close']
    # 最后一天成交量
    last_vol = data.iloc[-1]['volume']

    amount = last_close * last_vol

    # 成交额不低于2亿
    if amount < 200000000:
        return False

    #日K
    p_macd_status = check_macd_status(data)

    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    data.loc[:, 'ma20'] = tl.MA(data['close'].values, timeperiod=20)
    data['ma20'].values[np.isnan(data['ma20'].values)] = 0.0
    p_ma5 = data.iloc[-1]['ma5']
    p_close = data.iloc[-1]['close']
    p_ma20 = data.iloc[-1]['ma20']



    #boll
    data.loc[:, 'boll_ub'], data.loc[:, 'boll'], data.loc[:, 'boll_lb'] = tl.BBANDS \
        (data['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    data['boll_ub'].values[np.isnan(data['boll_ub'].values)] = 0.0
    data['boll'].values[np.isnan(data['boll'].values)] = 0.0
    data['boll_lb'].values[np.isnan(data['boll_lb'].values)] = 0.0

    bollub_close = data.iloc[-1]['boll_ub']
    boll_close = data.iloc[-1]['boll']



    if not p_macd_status or p_ma5 < p_ma20 or p_close < p_ma20 or p_change < 2 or data.iloc[-1]['close'] < data.iloc[-1]['open'] or p_close < boll_close :
        return False

    data = data.tail(n=threshold + 1)
    if len(data) < threshold + 1:
        return False

    data.loc[:, 'vol_ma5'] = tl.MA(data['volume'].values, timeperiod=10)
    data['vol_ma5'].values[np.isnan(data['vol_ma5'].values)] = 0.0
    mean_vol = data.iloc[-1]['vol_ma5']
    last_volw = data.iloc[-1]['volume']
    
    vol_ratio = last_volw / mean_vol

    #转换周K数据
    data = get_tdx_stock_period_to_type(data, period_day='W-FRI', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    #check Week
    if not check_macd_status(data):
        return False
    #re ta ma5 at W
    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    pw_ma5 = data.iloc[-1]['ma5']
    pw_close = data.iloc[-1]['close']

    pw_ma52 = data.iloc[-2]['ma5']
    pw_ma53 = data.iloc[-3]['ma5']
    pw_close2 = data.iloc[-2]['close']
    pw_close3 = data.iloc[-3]['close']

    pw_close_max3 = data.iloc[-4:-1]['close'].max()

    #转换月K数据
    data = get_tdx_stock_period_to_type(data, period_day='BM', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    #check Month
    if not check_macd_status(data):
        return False

    data = data.tail(n=threshold + 1)
    data = data.head(n=threshold)



    # if vol_ratio < 1.5 and (
    #     pw_close < pw_close_max3 * 0.98 or pw_close2 < pw_ma52 * 0.99
    # ):
    #     return False
    if vol_ratio > 1.5 and ((pw_close > pw_ma5 and p_ma5 > boll_close) or p_close > bollub_close):
        print(f"code:{code_name}")
        return True
    else:
        return False


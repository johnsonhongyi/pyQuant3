#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import numpy as np
import talib as tl
import pandas as pd
import datetime


__author__ = 'myh '
__date__ = '2023/3/10 '


# 量比大于2
# 例如：
#   2017-09-26 2019-02-11 京东方A
#   2019-03-22 浙江龙盛
#   2019-02-13 汇顶科技
#   2019-01-29 新城控股
#   2017-11-16 保利地产
def get_tdx_stock_period_to_type(stock_data, period_day='W-FRI', periods=5, ncol=None, ratiodays=True):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """
    #快速日期处理
    #https://www.likecs.com/show-204682607.html

    period_type = period_day
    if 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
    stock_data['date'] = stock_data.index
    lastday = stock_data.date.values[-1]
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

    if ratiodays:
        daynow = str(period_stock_data['open'].index.values[-1])[:10]
        # daynow = '2023-04-26'
        # lastday = '2023-04-23'
        duratio = int(str(datetime.datetime.strptime(daynow, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[0])
        ratio_d =(5-(duratio%5))/5
        print("ratio_d:%s %s"%(ratio_d,lastday))
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
    if not indextype and period_stock_data.index.name == 'date':
        # stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
        period_stock_data.index = [str(x)[:10] for x in period_stock_data.index]
        period_stock_data.index.name = 'date'
    else:
        if 'date' in period_stock_data.columns:
            period_stock_data = period_stock_data.drop(['date'], axis=1)
    # print period_stock_data
    return period_stock_data

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
    
    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    data.loc[:, 'ma20'] = tl.MA(data['close'].values, timeperiod=20)
    data['ma20'].values[np.isnan(data['ma20'].values)] = 0.0
    p_ma5 = data.iloc[-1]['ma5']
    p_close = data.iloc[-1]['close']
    p_ma20 = data.iloc[-1]['ma20']
    
    
    if p_ma5 < p_ma20 or p_close < p_ma20 or p_change < 2 or data.iloc[-1]['close'] < data.iloc[-1]['open']:
        return False

    data = data.tail(n=threshold + 1)
    if len(data) < threshold + 1:
        return False
    
    # 最后一天收盘价
    last_close = data.iloc[-1]['close']
    # 最后一天成交量
    last_vol = data.iloc[-1]['volume']
    
    amount = last_close * last_vol
            
    # 成交额不低于2亿
    if amount < 200000000:
        return False
    
    #转换周K数据
    data = get_tdx_stock_period_to_type(data, period_day='W-FRI', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)
    
    data.loc[:, 'vol_ma5'] = tl.MA(data['volume'].values, timeperiod=10)
    data['vol_ma5'].values[np.isnan(data['vol_ma5'].values)] = 0.0

    #re ta ma5 at W
    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    pw_ma5 = data.iloc[-1]['ma5']
    pw_close = data.iloc[-1]['close']
    
    last_volw = data.iloc[-1]['volume']
    
    data = data.tail(n=threshold + 1)
    data = data.head(n=threshold)
    
    mean_vol = data.iloc[-1]['vol_ma5']

    vol_ratio = last_volw / mean_vol
    
    if vol_ratio >= 2 and pw_close > pw_ma5 :
        return True
    else:
        return False

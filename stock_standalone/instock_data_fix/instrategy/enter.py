#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import logging
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
# 在项目运行时，临时将项目路径添加到环境变量
import os.path
import sys
# cpath_current = os.path.dirname(os.path.dirname(__file__))
# cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
cpath_current = '/data/InStock/instock/'
sys.path.append(cpath_current)
log_path = os.path.join(cpath_current, 'log')
if not os.path.exists(log_path):
    os.makedirs(log_path)
logging.basicConfig(format='%(asctime)s %(message)s', filename=os.path.join(log_path, 'stock_enter_job.log'))
root_logger = logging.getLogger()
if not any(isinstance(existing, logging.StreamHandler)
           and not isinstance(existing, logging.FileHandler)
           for existing in root_logger.handlers):
    handler = logging.StreamHandler()
    ch_formatter = logging.Formatter("[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s")
    handler.setFormatter(ch_formatter)
    root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

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

def check_rsi_status(data,threshold=60,period_day=False):
    # macd
    # cci 计算方法和结果和stockstats不同，stockstats典型价采用均价(总额/成交量)计算
    data.loc[:, 'cci'] = tl.CCI(data['high'].values, data['low'].values, data['close'].values, timeperiod=14)
    data['cci'].values[np.isnan(data['cci'].values)] = 0.0
    # data.loc[:, 'cci_84'] = tl.CCI(data['high'].values, data['low'].values, data['close'].values, timeperiod=84)
    # data['cci_84'].values[np.isnan(data['cci_84'].values)] = 0.0
    rsilast5 = data.iloc[-6:-1]['cci']
    rsilast5max = rsilast5.max()
    rsilast = data.iloc[-1]['cci']

    #周K滞后可以<0 日线节奏回踩多
    if period_day:
        return(rsilast5max < 0 and rsilast > rsilast5max and rsilast5.iloc[-1] < rsilast5max)
    else:
        return(rsilast > rsilast5max and rsilast5.iloc[-1] < rsilast5max)
        
    
def check_macd_status(data,threshold=60,period_day=False):
    # macd
    data.loc[:, 'diff'], data.loc[:, 'dea'], data.loc[:, 'macd'] = tl.MACD(
        data['close'].values, fastperiod=5, slowperiod=34, signalperiod=5)
        # data['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    
    data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    data['macd'].values[np.isnan(data['macd'].values)] = 0.0
    # diff_max =  data.iloc[-threshold:]['diff'].max()
    p_diff =  data.iloc[-1]['diff']
    p_dea =  data.iloc[-1]['dea']
    p_macd = data.iloc[-1]['macd']
    last_macd = data.iloc[-1]['macd']
    last2_macd = data.iloc[-2]['macd']
    last3_macd = data.iloc[-3]['macd']
    p_last_close = data.iloc[-1]['close']
    p_close_max5 = data.iloc[-6:-1]['close'].max()
    p_close_min5 = data.iloc[-6:-1]['close'].min()
    # p_percent = round((p_close_max5 - p_close_min5)/p_close_min5*100,1)
    data['percent'] =  data['close'].pct_change(periods=1) * 100
    p_percent = data.iloc[-1]['percent']
    p_percent_max = data['percent'][-6:-1].max()
    
    # if period_day:
    #     #Week and month
    #     # if last_macd > last2_macd and p_diff > 0 and p_dea > 0 and p_macd > 0 and p_diff > p_dea:
    #     #week 回踩零轴后 英可瑞 20230508
    #     # if  ((p_percent < 5 and p_percent > -1 and p_last_close >=p_close_max5) or p_diff >0) and p_diff >= p_dea * 0.98 and ((last_macd >= last2_macd or last2_macd >= last3_macd ) or (p_diff >= -0.1 and p_dea >= -0.1)) :            
    #     if  ((p_percent > 0 and p_last_close >=p_close_max5) or p_diff >0) and p_diff >= p_dea * 0.98 and ((last_macd >= last2_macd or last2_macd >= last3_macd ) or (p_diff >= -0.1 and p_dea >= -0.1)) :            
        
    #         return True
    #     else:
    #         return False
        
    # elif ((p_diff > 0 and p_dea > 0 ) or  p_macd >= 0 ) and last_macd > last2_macd and p_diff > p_dea*0.99 :
    if ((p_percent_max < 6 and  p_percent > p_percent_max ) or (p_percent > 0 and p_last_close > p_close_max5))  and p_diff >= p_dea*0.98 and ((last_macd >= last2_macd or last2_macd >= last3_macd)  or  p_macd >= -0.2 ):
         
        return True
    else:
        return False

def check_week_status(data,threshold=60,period_day=False):
    # macd
    # data.loc[:, 'diff'], data.loc[:, 'dea'], data.loc[:, 'macd'] = tl.MACD(
    #     data['close'].values, fastperiod=5, slowperiod=34, signalperiod=5)
    #     # data['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    
    # data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    # data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    # data['macd'].values[np.isnan(data['macd'].values)] = 0.0
    # # diff_max =  data.iloc[-threshold:]['diff'].max()
    # p_diff =  data.iloc[-1]['diff']
    # p_dea =  data.iloc[-1]['dea']
    # p_macd = data.iloc[-1]['macd']
    # last_macd = data.iloc[-1]['macd']
    # last2_macd = data.iloc[-2]['macd']
    # last3_macd = data.iloc[-3]['macd']
    data['percent'] =  data['close'].pct_change(periods=1) * 100
    p_last_close = data.iloc[-1]['close']
    p_close_max5 = data.iloc[-6:-1]['close'].max()
    p_close_min5 = data.iloc[-6:-1]['close'].min()
    # p_percent = round((p_close_max5 - p_close_min5)/p_close_min5*100,1)
    p_percent = data.iloc[-1]['percent']
    p_percent_max = data['percent'][-6:-1].max()
    if period_day:
        #Week and month
        # if last_macd > last2_macd and p_diff > 0 and p_dea > 0 and p_macd > 0 and p_diff > p_dea:
        #week 回踩零轴后 英可瑞 20230508
        # if  ((p_percent < 5 and p_percent > -1 and p_last_close >=p_close_max5) or p_diff >0) and p_diff >= p_dea * 0.98 and ((last_macd >= last2_macd or last2_macd >= last3_macd ) or (p_diff >= -0.1 and p_dea >= -0.1)) :            
        if  ((p_percent > p_percent_max) or (p_percent_max > 10)) and p_last_close >= p_close_max5  :            
        
            return True
        else:
            return False
        
    # elif ((p_diff > 0 and p_dea > 0 ) or  p_macd >= 0 ) and last_macd > last2_macd and p_diff > p_dea*0.99 :
    elif p_percent > 1 and p_last_close >= p_close_max5:
         
        return True
    else:
        
        return False
    
def check_volume(code_name, data, date=None, threshold=60):
    # pr_value['date'] = pd.to_datetime(pr_value.date, format='%Y-%m-%d')
    data['date'] = pd.to_datetime(data.date, format='%Y-%m-%d')
    if date is None:
        end_date = code_name[0]
    else:
        end_date = date.strftime("%Y-%m-%d")
    if end_date is not None:
        mask = (data['date'] <= end_date)
        data = data.loc[mask].copy()
    if len(data.index) < threshold:
        return False

    now_time = datetime.datetime.now()
    run_date = now_time.date()
    n_time = now_time.time()
    realtime = False
    if str(run_date) == str(data.date.values[-1])[:10]:
        if n_time >= datetime.time(9, 30, 0) and n_time <= datetime.time(15, 00, 0):
            realtime = True
            v_ratio = get_work_time_ratio()
            data.loc[ data.date == str(run_date),'volume'] = data[ data.date == str(run_date)]['volume'].apply(lambda x: round(x / v_ratio, 1))
            data.loc[ data.date == str(run_date),'amount'] = data[ data.date == str(run_date)]['amount'].apply(lambda x: round(x / v_ratio, 1))
    
    p_change = data.iloc[-1]['p_change']

    last_close = data.iloc[-1]['close']
    # 最后一天成交量
    last_vol = data.iloc[-1]['volume']

    amount = last_close * last_vol

    # 成交额不低于2亿
    if amount < 200000000:
        return False

    
            
    #日K
    
    #p_rsi_status = check_rsi_status(data)
    
    #if not p_rsi_status:
    #    return False
    #else:
    #    logging.info(f"code:{code_name} 日,RSI OK")
    
    p_macd_status = check_macd_status(data)
    if not p_macd_status:
        return False
    
    #转换月K数据
    # dataM = get_tdx_stock_period_to_type(data, period_day='BM', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    # #check Month
    # p_macd_status_m = check_macd_status(dataM)
    # if not p_macd_status_m:
    #     return False

    #转换周K数据
    dataW = get_tdx_stock_period_to_type(data, period_day='W-FRI', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    #check Week
    # if not check_macd_status(dataW):
    p_macd_status_w = check_week_status(dataW,period_day=True)
    if not p_macd_status_w:
        return False
    else:
        pass
        # logging.info(f"code:{code_name} 日,周,月K OK")
    #re ta ma5 at W
    dataW.loc[:, 'ma5'] = tl.MA(dataW['close'].values, timeperiod=5)
    dataW['ma5'].values[np.isnan(dataW['ma5'].values)] = 0.0
    
    dataW.loc[:, 'ma20'] = tl.MA(dataW['close'].values, timeperiod=26)
    dataW['ma20'].values[np.isnan(dataW['ma20'].values)] = 0.0
    pw_ma5 = dataW.iloc[-1]['ma5']
    pw_ma20 = dataW.iloc[-1]['ma20']
    
    pw_close = dataW.iloc[-1]['close']
    
    pw_low = dataW.iloc[-1]['low']
    pw_open = data.iloc[-1]['open']
    pw_high = data.iloc[-1]['high']
    
    
    pw_ma52 = dataW.iloc[-2]['ma5']
    pw_ma53 = dataW.iloc[-3]['ma5']
    pw_close2 = dataW.iloc[-2]['close']
    pw_close3 = dataW.iloc[-3]['close']
    pw_close_max3 = dataW.iloc[-4:-1]['close'].max()
    

    #日K
    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    data.loc[:, 'ma20'] = tl.MA(data['close'].values, timeperiod=26)
    data['ma20'].values[np.isnan(data['ma20'].values)] = 0.0
    p_ma5 = data.iloc[-1]['ma5']
    p_close = data.iloc[-1]['close']
    p_close2 = data.iloc[-2]['close']
    
    p_open = data.iloc[-1]['open']
    p_high = data.iloc[-1]['high']
    
    p2_high = data.iloc[-2]['high']
    p_low = data.iloc[-1]['low']
    p2_low = data.iloc[-2]['low']
    p_ma20 = data.iloc[-1]['ma20']



    #boll
    data.loc[:, 'boll_ub'], data.loc[:, 'boll'], data.loc[:, 'boll_lb'] = tl.BBANDS \
        (data['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    data['boll_ub'].values[np.isnan(data['boll_ub'].values)] = 0.0
    data['boll'].values[np.isnan(data['boll'].values)] = 0.0
    data['boll_lb'].values[np.isnan(data['boll_lb'].values)] = 0.0

    bollub_close = data.iloc[-1]['boll_ub']
    boll_close = data.iloc[-1]['boll']



    if p_ma5 < p_ma20 or p_close < p_ma20 or p_change < 2 or data.iloc[-1]['close'] < data.iloc[-1]['open'] or p_close < boll_close :
        return False

    # data = data.tail(n=threshold + 1)
    # if len(data) < threshold + 1:
    #     return False

    data.loc[:, 'vol_ma5'] = tl.MA(data['volume'].values, timeperiod=6)
    data['vol_ma5'].values[np.isnan(data['vol_ma5'].values)] = 0.0
    mean_vol = data.iloc[-1]['vol_ma5']
    last_vol = data.iloc[-1]['volume']
    last_vol2 = data.iloc[-2]['volume']
    vol_ratio = last_vol / mean_vol
    vol_ratio2 = last_vol / last_vol2
    vol_ratio_diff = vol_ratio2 - vol_ratio

     #bollW
    dataW.loc[:, 'boll_ub'], dataW.loc[:, 'boll'], dataW.loc[:, 'boll_lb'] = tl.BBANDS \
        (dataW['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    dataW['boll_ub'].values[np.isnan(dataW['boll_ub'].values)] = 0.0
    dataW['boll'].values[np.isnan(dataW['boll'].values)] = 0.0
    dataW['boll_lb'].values[np.isnan(dataW['boll_lb'].values)] = 0.0      

    bollub_closew = dataW.iloc[-1]['boll_ub']
    bollub_closew2 = dataW.iloc[-2]['boll_ub']
    boll_closew = dataW.iloc[-1]['boll']
    
    dataW.loc[:, 'vol_ma5'] = tl.MA(dataW['volume'].values, timeperiod=6)
    dataW['vol_ma5'].values[np.isnan(dataW['vol_ma5'].values)] = 0.0
    mean_volw = dataW.iloc[-1]['vol_ma5']
    last_volw = dataW.iloc[-1]['volume']
    last_volw2 = dataW.iloc[-2]['volume']
    
    vol_ratiow = last_volw / mean_volw
    vol_ratiow2 = last_volw / last_volw2
    vol_ratiow_diff = vol_ratiow2 - vol_ratiow
    # data = data.tail(n=threshold + 1)
    # data = data.head(n=threshold)



    # if vol_ratio < 1.5 and (
    #     pw_close < pw_close_max3 * 0.98 or pw_close2 < pw_ma52 * 0.99
    # ):
    #     return False
    # if  vol_ratiow2 > 1.2 and pw_ma5 >= pw_ma52 and ((pw_low > pw_ma5*0.98 and pw_low < pw_ma5*1.05 and pw_close > pw_ma5) or (pw_close > bollub_closew and pw_close2 <= bollub_closew2)) :
   
    # if  pw_close > pw_ma20 and pw_close2 < pw_ma20 and  pw_ma5 >= pw_ma52 and ((pw_low > pw_ma5*0.98 and pw_low < pw_ma5*1.05 and pw_close > pw_ma5) or (pw_close > bollub_closew and pw_close2 <= bollub_closew2)) :
    #     # print(vol_ratiow  , pw_close , pw_ma5 , pw_close , bollub_closew , pw_close2 , bollub_closew2 , bollub_closew , bollub_closew)
    #     logging.info(f"codeW: pw_close:{pw_close} pw_ma20: {pw_ma20} pw_close2:{pw_close2}pw_ma20:{pw_ma20} codeW:{code_name} {round(vol_ratiow,2)} pw2: {round(pw_close2,2)} upp2: {round(bollub_closew2,2)}")
    #     return True
#    if p_open > p_low*0.98 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.3   and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.05) or (p_close > p2_high and p_high > bollub_close  and p_close < bollub_close)):
    #if p_open > p_low*0.95 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.5  and vol_ratio < 3 and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.2) or (p_close > p2_high and p_high > bollub_close)):
    if p_open > p_low*0.95 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.1  and vol_ratio < 5 and pw_close2 >= bollub_closew2 * 0.97 and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close ) or (p_close > p2_high and p_high > bollub_close)):

        # print(vol_ratio ,pw_close , pw_ma5 , p_ma5 , boll_close , pw_close2 , bollub_closew2 * 1.08 , p_close , p2_high , p_high , bollub_close , p_close ,bollub_close )
        logging.info(f"enter codeD:{code_name} Select volD:{round(vol_ratio,2)} pclose: {round(p_close,2)} upp: {round(bollub_close,2)}")
        return True
    else:
        return False

    # if (vol_ratiow2 > 1.5 and pw_close > pw_ma5 and pw_close > bollub_closew and pw_close2 <= bollub_closew2 and bollub_closew >= bollub_closew):
    #     # print(vol_ratiow  , pw_close , pw_ma5 , pw_close , bollub_closew , pw_close2 , bollub_closew2 , bollub_closew , bollub_closew)
    #     logging.info(f"codeW:{code_name} Select volW:{round(vol_ratiow,2)} pw2: {round(pw_close2,2)} upp2: {round(bollub_closew2,2)}")
    #     return True
    # elif vol_ratio2 > 1.5  and ((pw_close > pw_ma5 and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.08) or (p_close > p2_high and p_high > bollub_close  and p_close < bollub_close)):
    #     # print(vol_ratio ,pw_close , pw_ma5 , p_ma5 , boll_close , pw_close2 , bollub_closew2 * 1.08 , p_close , p2_high , p_high , bollub_close , p_close ,bollub_close )
    #     logging.info(f"codeD:{code_name} Select volW:{round(vol_ratio,2)} pclose: {round(p_close,2)} upp: {round(bollub_close,2)}")
    #     return True
    # else:
    #     return False




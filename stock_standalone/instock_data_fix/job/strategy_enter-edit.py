#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import logging
import concurrent.futures
import pandas as pd
import os
import os.path
import sys


cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
from instock.core.singleton_stock import stock_hist_data
from instock.core.stockfetch import fetch_stock_top_entity_data,fetch_stocks,_normalize_talib_columns

__author__ = 'myh '
__date__ = '2023/3/10 '
import instock.lib.trade_time as trd
import datetime
import talib as tl
import instock.job.backtest_data_daily_job_edit as bk_job_edit

def prepare(date, strategy):
    try:
        stocks_data = stock_hist_data(date=date).get_data()
        if stocks_data is None:
            return
        table_name = strategy['name']
        strategy_func = strategy['func']
        results = run_check(strategy_func, table_name, stocks_data, date)
        if results is None:
            return

        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            mdb.executeSql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_STRATEGIES[0]['columns'])

        if not results:
            logging.info("%s在%s没有命中策略", table_name, date)
            return

        data = pd.DataFrame(results)
        columns = tuple(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])
        data.columns = columns
        _columns_backtest = tuple(tbs.TABLE_CN_STOCK_BACKTEST_DATA['columns'])
        data = pd.concat([data, pd.DataFrame(columns=_columns_backtest)])
        # 单例，时间段循环必须改时间
        date_str = date.strftime("%Y-%m-%d")
        if date.strftime("%Y-%m-%d") != data.iloc[0]['date']:
            data['date'] = date_str
        mdb.insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")

    except Exception as e:
        logging.error(f"strategy_data_daily_job.prepare处理异常：{strategy}策略{e}")

def pandas_df(conn, sql):
    df = pd.read_sql(sql, conn)
    # conn.close()
    return df

def stocks_data_to_realtime(date,stocks_data,realdf):
    realdf['open'] = realdf['open_price']
    realdf['high'] = realdf['high_price']
    realdf['low'] = realdf['low_price']
    realdf['quote_change'] = realdf['change_rate']
    realdf['lastp'] = realdf['pre_close_price']
    # realdf['close'] = realdf['pre_close_price']basic_data_daily_job.py
    realdf['close'] = realdf['new_price']
    realdf['amount'] = realdf['deal_amount']
    realdf['turnover'] = realdf['turnoverrate']
    realdf['volume'] = pd.to_numeric(realdf['volume'], errors='coerce').fillna(0).astype('float64') * 100
    realdf['amount'] = pd.to_numeric(realdf['amount'], errors='coerce').fillna(0).astype('float64') * 100
    
    h_col = tuple(tbs.CN_STOCK_HIST_DATA['columns'])
    # h_col.append('p_change')
    # ('2023-05-11', '603058', '永吉股份')
    stocks_data2={}
    rundate = str(date.strftime("%Y-%m-%d"))
    # rundate = date
    for key in stocks_data:
        # date1 = key[0]
        code  = key[1]
        name = key[2]
        pr_value = stocks_data[key]
        pr_value = pr_value[pr_value.date < str(date)[:10]]
        # scol = stocks_data[key].columns.values
        data = realdf.loc[realdf.code==code,h_col]
        # pr_value = pr_value.append(data).reset_index(drop=True)
        
        #debug realtime
        # pr_value = pr_value[:-1]
        #debug realtime
        pr_value = pd.concat([pr_value, data], axis=0).reset_index(drop=True)
        pr_value = _normalize_talib_columns(pr_value)
        pr_value.loc[:, 'p_change'] = tl.ROC(pr_value['close'].to_numpy(dtype='float64'), 1)
        pr_value['date'] = pd.to_datetime(pr_value.date, format='%Y-%m-%d')
        stocks_data2[(rundate,code,name)] = pr_value
        
    return stocks_data2

def filter_code_to_stock_data(stocks_data,codelist):
    stocks_data2 = {}
    for code in codelist:
        for row in stocks_data:
            if row[1] == code:
                stocks_data2[row]=stocks_data[row]
    return stocks_data2

global stockdata
stockdata = None
def prepareRealtime(date, strategy):
    try:
        stocks_data = stock_hist_data(date=date).get_data()
        if not stocks_data:
            raise RuntimeError(f"{date}的TDX历史数据为空或覆盖不足")
        

        #debug
        # code_list=['600258']
        # stocks_data = filter_code_to_stock_data(stocks_data,code_list) 
        
        global stockdata
        stockdata = stocks_data
        now_time = datetime.datetime.now()
        run_date = now_time.date()
        # run_date = date + datetime.timedelta(days=1)
        table_name = strategy['name']
        strategy_func = strategy['func']
        
        # if trd.is_trade_date(run_date) :
        if trd.is_trade_date(run_date) and trd.is_open(now_time) and not trd.is_close(now_time):
            
            date = run_date
            logging.info(f"strategy_enter_readldf：{date}")
            real_table_name = 'cn_stock_spot'
            read_sql = f"SELECT * FROM `{real_table_name}` where `date` = '{date}'"
            realdf = pandas_df(mdb.engine(),read_sql)
            if len(realdf) == 0:
                logging.info(f"strategy_enter_readldf.prepare处理异常：{date}")
                realdf = fetch_stocks(date)
            if realdf is None or realdf.empty:
                raise RuntimeError(f"{date}的实时行情接口没有返回股票数据")
            stocks_data = stocks_data_to_realtime(date,stocks_data,realdf)
            if not stocks_data:
                raise RuntimeError(f"{date}实时行情与TDX历史数据无法匹配")
            stockdata = stocks_data
            logging.info(f"realtime_enter_readldf：{list(stocks_data.keys())[0]}")
            
        results = run_check(strategy_func, table_name, stocks_data, date)
        if results is None:
            return

        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            mdb.executeSql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_STRATEGIES[0]['columns'])

        if not results:
            logging.info("%s在%s没有命中策略", table_name, date)
            return

        data = pd.DataFrame(results)
        columns = tuple(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])
        data.columns = columns
        _columns_backtest = tuple(tbs.TABLE_CN_STOCK_BACKTEST_DATA['columns'])
        data = pd.concat([data, pd.DataFrame(columns=_columns_backtest)])
        # 单例，时间段循环必须改时间
        date_str = date.strftime("%Y-%m-%d")
        if date.strftime("%Y-%m-%d") != data.iloc[0]['date']:
            data['date'] = date_str
        mdb.insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")

    except Exception as e:
        logging.exception(f"Strategy_enter-edit-_daily_job.prepareRealtime处理异常：{e}")
        raise
        
def run_check(strategy_fun, table_name, stocks, date, workers=2):
    if not stocks:
        raise RuntimeError(f"{table_name}没有可计算的股票历史数据")
    is_check_high_tight = False
    if strategy_fun.__name__ == 'check_high_tight':
        stock_tops = fetch_stock_top_entity_data(date)
        if stock_tops is not None:
            is_check_high_tight = True
    data = []
    
    #debug
    # for k in stocks:
    #     import instock.core.strategy.enter as cn_stock_strategy_enter
    #     print(k)
    #     if k[1] == '300527':
    #         print(cn_stock_strategy_enter.check_volume(k,stocks[k],date=date))
    #debug
    
    error_count = 0
    future_count = 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            if is_check_high_tight:
                future_to_data = {executor.submit(strategy_fun, k, stocks[k], date=date, istop=(k[1] in stock_tops)): k for k in stocks}
            else:
                future_to_data = {executor.submit(strategy_fun, k, stocks[k], date=date): k for k in stocks}
            future_count = len(future_to_data)
            for future in concurrent.futures.as_completed(future_to_data):
                stock = future_to_data[future]
                try:
                    if future.result():
                        data.append(stock)
                except Exception as e:
                    error_count += 1
                    if error_count <= 10:
                        logging.error(f"strategy_data_daily_job.run_check处理异常：{stock[1]}代码{e}策略{table_name}")
    except Exception as e:
        logging.exception(f"strategy_data_daily_job.run_check处理异常：{e}策略{table_name}")
        raise
    if error_count:
        logging.error("%s逐股计算异常 %s/%s", table_name, error_count, future_count)
    if future_count and error_count > max(5, int(future_count * 0.01)):
        raise RuntimeError(f"{table_name}逐股计算失败过多：{error_count}/{future_count}")
    return data


def main():
    # 使用方法传递。
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for strategy in tbs.TABLE_CN_STOCK_STRATEGIES:
            executor.submit(runt.run_with_args, prepare, strategy)


def _strategy_run_dates():
    if len(sys.argv) == 3:
        run_date = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
        dates = []
        while run_date <= end_date:
            if trd.is_trade_date(run_date):
                dates.append(run_date)
            run_date += datetime.timedelta(days=1)
        return dates
    if len(sys.argv) == 2:
        dates = [datetime.datetime.strptime(value, "%Y-%m-%d").date()
                 for value in sys.argv[1].split(",")]
        return [date for date in dates if trd.is_trade_date(date)]
    return [trd.get_trade_date_last()[0]]


def strategy_enter(small_strategies_only=False):
    # 串行运行两项手动策略，避免小内存节点同时构造两套逐股任务。
    run_dates = _strategy_run_dates()
    if not run_dates:
        raise RuntimeError("指定范围内没有交易日")
    failures = []
    for run_date in run_dates:
        for strategy in [tbs.TABLE_CN_STOCK_STRATEGIES[0], tbs.TABLE_CN_STOCK_STRATEGIES[1]]:
            logging.info(f"start strategyrealtime:{strategy['cn']} {strategy['name']} {run_date}")
            try:
                prepareRealtime(run_date, strategy)
            except Exception as e:
                failures.append(f"{strategy['name']} {run_date}: {e}")
    if failures:
        raise RuntimeError("手动策略刷新失败: " + "; ".join(failures))
    if not small_strategies_only:
        logging.info("start bk job realtime:")
        global stockdata
        bk_job_edit.prepareRealTime(stocks_data=stockdata)
# main函数入口
if __name__ == '__main__':
    strategy_enter(small_strategies_only=os.environ.get("INSTOCK_SMALL_STRATEGIES_ONLY") == "1")

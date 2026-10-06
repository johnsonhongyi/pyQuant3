#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import logging
import concurrent.futures
import pandas as pd
import os.path
import sys
import time
from collections import Counter

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
from instock.core.singleton_stock import stock_hist_data
from instock.core.stockfetch import fetch_stock_top_entity_data
from scan_helpers import bounded_results

__author__ = 'myh '
__date__ = '2023/3/10 '


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
        logging.error(f"strategy_data_daily_job.prepare处理异常：{str(strategy)[:50]}策略{e}")


def run_check(strategy_fun, table_name, stocks, date, workers=2):
    started = time.perf_counter()
    is_check_high_tight = False
    if strategy_fun.__name__ == 'check_high_tight':
        stock_tops = fetch_stock_top_entity_data(date)
        if stock_tops is not None:
            is_check_high_tight = True
    data = []
    error_counts = Counter()
    error_samples = []
    checked = 0
    workers = max(1, min(int(workers), 2))
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            def check_one(stock):
                kwargs = {'date': date}
                if is_check_high_tight:
                    kwargs['istop'] = stock[1] in stock_tops
                return strategy_fun(stock, stocks[stock], **kwargs)

            for stock, result, error in bounded_results(
                    executor, stocks, check_one, max_pending=workers * 2):
                checked += 1
                if error:
                    error_counts[error.partition(':')[0]] += 1
                    if len(error_samples) < 3:
                        error_samples.append('%s:%s' % (stock[1], error[:120]))
                elif result:
                    data.append(stock)
    except Exception as e:
        logging.error(f"strategy_data_daily_job.run_check处理异常：{e}策略{table_name}")
    logging.info(
        'strategy scan complete: strategy=%s checked=%s matched=%s errors=%s elapsed=%.1fs',
        table_name, checked, len(data), sum(error_counts.values()), time.perf_counter() - started,
    )
    if error_counts:
        logging.error('strategy scan errors: strategy=%s types=%s samples=%s',
                      table_name, dict(error_counts), error_samples)
    if not data:
        return None
    else:
        return data


def main():
    # 使用方法传递。
    for strategy in tbs.TABLE_CN_STOCK_STRATEGIES:
        runt.run_with_args(prepare, strategy)


# main函数入口
if __name__ == '__main__':
    main()

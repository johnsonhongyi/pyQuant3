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
import instock.core.pattern.pattern_recognitions as kpr
from scan_helpers import bounded_results

__author__ = 'myh '
__date__ = '2023/3/10 '


def prepare(date):
    try:
        stocks_data = stock_hist_data(date=date).get_data()
        if stocks_data is None:
            return
        results = run_check(stocks_data, date=date)
        if results is None:
            return

        table_name = tbs.TABLE_CN_STOCK_KLINE_PATTERN['name']
        # 删除老数据。
        if mdb.checkTableIsExist(table_name):
            del_sql = f"DELETE FROM `{table_name}` where `date` = '{date}'"
            mdb.executeSql(del_sql)
            cols_type = None
        else:
            cols_type = tbs.get_field_types(tbs.TABLE_CN_STOCK_KLINE_PATTERN['columns'])

        dataKey = pd.DataFrame(results.keys())
        _columns = tuple(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])
        dataKey.columns = _columns

        dataVal = pd.DataFrame(results.values())

        data = pd.merge(dataKey, dataVal, on=['code'], how='left')
        # 单例，时间段循环必须改时间
        date_str = date.strftime("%Y-%m-%d")
        if date.strftime("%Y-%m-%d") != data.iloc[0]['date']:
            data['date'] = date_str
        mdb.insert_db_from_df(data, table_name, cols_type, False, "`date`,`code`")

    except Exception as e:
        logging.error(f"klinepattern_data_daily_job.prepare处理异常：{e}")


def run_check(stocks, date=None, workers=2):
    started = time.perf_counter()
    data = {}
    error_counts = Counter()
    error_samples = []
    checked = 0
    workers = max(1, min(int(workers), 2))
    columns = tbs.STOCK_KLINE_PATTERN_DATA['columns']
    data_column = columns
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            def pattern_one(stock):
                return kpr.get_pattern_recognition(stock, stocks[stock], data_column, date=date)

            for stock, result, error in bounded_results(
                    executor, stocks, pattern_one, max_pending=workers * 2):
                checked += 1
                if error:
                    error_counts[error.partition(':')[0]] += 1
                    if len(error_samples) < 3:
                        error_samples.append('%s:%s' % (stock[1], error[:120]))
                elif result is not None:
                    data[stock] = result
    except Exception as e:
        logging.error(f"klinepattern_data_daily_job.run_check处理异常：{e}")
    logging.info('kline-pattern scan complete: checked=%s results=%s errors=%s elapsed=%.1fs',
                 checked, len(data), sum(error_counts.values()), time.perf_counter() - started)
    if error_counts:
        logging.error('kline-pattern scan errors: types=%s samples=%s',
                      dict(error_counts), error_samples)
    if not data:
        return None
    else:
        return data


def main():
    # 使用方法传递。
    runt.run_with_args(prepare)


# main函数入口
if __name__ == '__main__':
    main()

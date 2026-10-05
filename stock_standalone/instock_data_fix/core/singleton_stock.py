#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import concurrent.futures
import instock.core.stockfetch as stf
import instock.core.tablestructure as tbs
import instock.lib.trade_time as trd
from instock.lib.singleton_type import singleton_type

__author__ = 'myh '
__date__ = '2023/3/10 '


# 读取当天股票数据
class stock_data(metaclass=singleton_type):
    def __init__(self, date):
        try:
            #import pdb;pdb.set_trace()
            self.data = stf.fetch_stocks(date)
        except Exception as e:
            logging.error(f"singleton.stock_data处理异常：{e}")

    def get_data(self):
        return self.data


# 读取股票历史数据
class stock_hist_data(metaclass=singleton_type):
    def __init__(self, date=None, stocks=None, workers=2):
        if stocks is None:
            snapshot = stock_data(date).get_data()
            if snapshot is None or snapshot.empty:
                logging.error("singleton.stock_hist_data没有%s的股票行情列表", date)
                self.data = None
                return
            _subset = snapshot[list(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])]
            stocks = [tuple(x) for x in _subset.values]
            #import pdb;pdb.set_trace()
        if stocks is None or len(stocks) == 0:
            self.data = None
            return
        date_start, is_cache = trd.get_trade_hist_interval(stocks[0][0])  # 提高运行效率，只运行一次
        _data = {}
        try:
            # max_workers是None还是没有给出，将默认为机器cup个数*5
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_stock = {executor.submit(stf.fetch_stock_hist, stock, date_start, is_cache): stock for stock
                                   in stocks}
                for future in concurrent.futures.as_completed(future_to_stock):
                    stock = future_to_stock[future]
                    try:
                        __data = future.result()
                        if __data is not None:
                            _data[stock] = __data
                    except Exception as e:
                        logging.error(f"singleton.stock_hist_data处理异常：{stock[1]}代码{e}")
        except Exception as e:
            logging.error(f"singleton.stock_hist_data处理异常：{e}")
        minimum = max(1, int(len(stocks) * 0.7))
        if len(_data) < minimum:
            logging.error("singleton.stock_hist_data TDX历史数据覆盖不足: %s/%s", len(_data), len(stocks))
            self.data = None
        else:
            self.data = _data

    def get_data(self):
        return self.data

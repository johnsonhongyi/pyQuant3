#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import concurrent.futures
from itertools import islice
from threading import RLock
import instock.core.stockfetch as stf
import instock.core.tablestructure as tbs
import instock.lib.trade_time as trd
from instock.lib.singleton_type import singleton_type

__author__ = 'myh '
__date__ = '2023/3/10 '


# 读取当天股票数据
class stock_data(metaclass=singleton_type):
    def __init__(self, date):
        self._lock = RLock()
        self._loaded_date = None
        self._loaded = False
        self.data = None
        self._load(date)

    @staticmethod
    def _date_key(date):
        return date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]

    def _load(self, date, refresh=False):
        date_key = self._date_key(date)
        with self._lock:
            if not refresh and self._loaded and self._loaded_date == date_key:
                return
            if self._loaded_date != date_key:
                self.data = None
                self._loaded = False
            try:
                result = stf.fetch_stocks(date)
                if result is not None and not result.empty:
                    self.data = result
                    self._loaded = True
                    self._loaded_date = date_key
                elif refresh:
                    self.data = None
                    self._loaded = False
                    logging.error('singleton.stock_data fresh Sina snapshot unavailable for %s', date_key)
            except Exception as e:
                logging.error(f"singleton.stock_data处理异常：{e}")
                if refresh:
                    self.data = None
                    self._loaded = False

    def get_data(self, date=None, refresh=False):
        if date is not None:
            self._load(date, refresh=refresh)
        return self.data


# 读取股票历史数据
class stock_hist_data(metaclass=singleton_type):
    def __init__(self, date=None, stocks=None, workers=2):
        self._lock = RLock()
        self._loaded_key = None
        self._loaded_date = None
        self._loaded = False
        self.data = None
        self._load(date, stocks, workers)

    @staticmethod
    def _date_key(date):
        return date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]

    def _load(self, date=None, stocks=None, workers=2):
        with self._lock:
            date_key = self._date_key(date)
            if self._loaded and self._loaded_date == date_key and stocks is None:
                return
            if stocks is None:
                snapshot = stock_data(date).get_data(date)
                if snapshot is None or snapshot.empty:
                    logging.error("singleton.stock_hist_data没有%s的股票行情列表", date)
                    self.data = None
                    self._loaded_key = (date_key, None)
                    self._loaded_date = date_key
                    self._loaded = True
                    return
                subset = snapshot[list(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])]
                stocks = [tuple(row) for row in subset.values]
            if stocks is None or len(stocks) == 0:
                self.data = None
                self._loaded_key = (date_key, ())
                self._loaded_date = date_key
                self._loaded = True
                return

            cache_key = (date_key, tuple(str(stock[1]) for stock in stocks))
            if self._loaded and self._loaded_key == cache_key:
                return
            self._loaded = True
            self._loaded_key = cache_key
            self._loaded_date = date_key

            date_start, is_cache = trd.get_trade_hist_interval(stocks[0][0])
            _data = {}
            worker_count = max(1, min(int(workers), 2))
            batch_size = worker_count * 4
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                    stock_iter = iter(stocks)
                    while True:
                        batch = list(islice(stock_iter, batch_size))
                        if not batch:
                            break
                        future_to_stock = {
                            executor.submit(stf.fetch_stock_hist, stock, date_start, is_cache): stock
                            for stock in batch
                        }
                        for future in concurrent.futures.as_completed(future_to_stock):
                            stock = future_to_stock[future]
                            try:
                                history = future.result()
                                if history is not None:
                                    _data[stock] = history
                            except Exception as e:
                                logging.error("singleton.stock_hist_data处理异常：%s代码%s", stock[1], e)
            except Exception as e:
                logging.error(f"singleton.stock_hist_data处理异常：{e}")
            minimum = max(1, int(len(stocks) * 0.7))
            if len(_data) < minimum:
                logging.error("singleton.stock_hist_data TDX历史数据覆盖不足: %s/%s", len(_data), len(stocks))
                self.data = None
            else:
                self.data = _data

    def get_data(self, date=None, stocks=None, workers=2):
        if date is not None:
            self._load(date, stocks, workers)
        return self.data

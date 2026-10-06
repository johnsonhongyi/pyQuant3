#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import datetime
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
log_dir = os.path.join(cpath_current, 'log')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    format='%(asctime)s %(message)s',
    filename=os.path.join(log_dir, 'stock_execute_job.log'),
)
logging.getLogger().setLevel(logging.INFO)

sys.path.insert(0, os.path.dirname(__file__))
sys.path.append(cpath)

from sqlalchemy import text

import init_job as bj
import basic_data_other_daily_job as hdtj
import indicators_data_daily_job as gdj
import klinepattern_data_daily_job as kdj
import strategy_data_daily_job as sdj
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
import instock.lib.trade_time as trd

_TIMEZONE = ZoneInfo('Asia/Shanghai')


def _run_stage(name, function):
    started = time.perf_counter()
    logging.info('daily pipeline stage start: %s', name)
    function()
    logging.info('daily pipeline stage complete: %s elapsed=%.1fs',
                 name, time.perf_counter() - started)


def _current_spot_rows(run_date):
    table_name = tbs.TABLE_CN_STOCK_SPOT['name']
    if not mdb.checkTableIsExist(table_name):
        return 0
    query = text('SELECT COUNT(*) AS row_count FROM `%s` WHERE `date` = :run_date' % table_name)
    with mdb.engine().connect() as connection:
        count = connection.execute(query, {'run_date': run_date.isoformat()}).scalar()
    return int(count or 0)


def main():
    started = time.perf_counter()
    run_date = datetime.datetime.now(_TIMEZONE).date()
    is_trade_day = trd.is_trade_date(run_date)
    if not (is_trade_day is True or str(is_trade_day).strip().lower() in ('true', '1')):
        logging.info('skip daily pipeline on non-trading date: %s', run_date)
        return

    logging.info('daily pipeline start: date=%s', run_date)
    try:
        _run_stage('database-init', bj.main)

        minimum_rows = max(1, int(os.environ.get('INSTOCK_MIN_DAILY_STOCK_ROWS', '3000')))
        spot_rows = _current_spot_rows(run_date)
        if spot_rows < minimum_rows:
            logging.warning(
                'skip stale full-market pipeline: date=%s current_stock_rows=%s required=%s; '
                'close snapshot job owns stock/ETF refresh',
                run_date, spot_rows, minimum_rows,
            )
            return

        # The 16:05/16:35 close job has already persisted these snapshots.
        _run_stage('other-daily-data', hdtj.main)
        _run_stage('indicators', gdj.main)
        _run_stage('kline-patterns', kdj.main)
        _run_stage('strategies', sdj.main)

        # Backtests have their own 18:15 cron entry; do not compute them twice.
        logging.info('daily pipeline backtest deferred to its dedicated 18:15 job')
    except Exception:
        logging.exception('daily pipeline failed: date=%s', run_date)
    finally:
        logging.info('daily pipeline finished: date=%s elapsed=%.1fs',
                     run_date, time.perf_counter() - started)


if __name__ == '__main__':
    main()

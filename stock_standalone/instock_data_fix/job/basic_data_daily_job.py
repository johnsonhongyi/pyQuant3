#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import argparse
import logging
import os
import sys
import contextlib
import datetime
import json
import tempfile
import threading
from zoneinfo import ZoneInfo
import pandas as pd

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
import instock.lib.trade_time as trd
import instock.core.stockfetch as stf
from instock.core.singleton_stock import stock_data

try:
    import fcntl
except ImportError:  # pragma: no cover - production runs on Linux
    fcntl = None

__author__ = 'myh '
__date__ = '2023/3/10 '


_CACHE_DIR = os.path.join(cpath_current, 'cache', 'close_finalize')
_LOCAL_LOCK = threading.RLock()
_TIMEZONE = ZoneInfo('Asia/Shanghai')


@contextlib.contextmanager
def _file_lock(name):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    handle = open(os.path.join(_CACHE_DIR, name + '.lock'), 'a+b')
    with _LOCAL_LOCK:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def _date_key(date):
    return date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)[:10]


def _is_close_finalize(date):
    now = datetime.datetime.now(_TIMEZONE)
    return (_date_key(date) == now.date().isoformat()
            and now.weekday() < 5 and now.time() >= datetime.time(16, 0))


def _final_marker(kind, date):
    return os.path.join(_CACHE_DIR, '%s-%s.done' % (kind, _date_key(date)))


def _write_final_marker(kind, date, source, stats=None, complete=True):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    marker = _final_marker(kind, date)
    fd, temporary = tempfile.mkstemp(prefix=kind + '-', suffix='.tmp', dir=_CACHE_DIR)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'date': _date_key(date), 'source': source, 'complete': bool(complete),
                       'stats': stats or {}, 'completed_at':
                       datetime.datetime.now(_TIMEZONE).isoformat(timespec='seconds')}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _final_marker_is_current(kind, date, source):
    marker = _final_marker(kind, date)
    try:
        with open(marker, 'r', encoding='utf-8') as stream:
            payload = json.load(stream)
        return (payload.get('date') == _date_key(date)
                and payload.get('source') == source and payload.get('complete') is True)
    except (OSError, ValueError, TypeError):
        return False


def _persist_daily_snapshot(data, table, date, schema, replace_date=True):
    date_key = _date_key(date)
    frame = data.copy()
    frame['date'] = date_key
    frame['code'] = frame['code'].astype(str).str.split('.').str[0].str.zfill(6)
    frame = frame.drop_duplicates(['date', 'code'], keep='last')
    if frame.empty:
        return 0
    table_name = schema['name']
    with _file_lock(table + '-database'):
        if not mdb.checkTableIsExist(table_name):
            mdb.insert_db_from_df(frame, table_name,
                                  tbs.get_field_types(schema['columns']), False,
                                  '`date`,`code`')
            return len(frame)

        from sqlalchemy import text
        with mdb.engine().begin() as connection:
            if replace_date:
                connection.execute(text('DELETE FROM `%s` WHERE `date` = :date' % table_name),
                                   {'date': date_key})
            else:
                codes = frame['code'].astype(str).drop_duplicates().tolist()
                params = {'date': date_key}
                placeholders = []
                for index, code in enumerate(codes):
                    key = 'code%s' % index
                    params[key] = code
                    placeholders.append(':' + key)
                connection.execute(
                    text('DELETE FROM `%s` WHERE `date` = :date AND `code` IN (%s)'
                         % (table_name, ','.join(placeholders))), params
                )
            frame.to_sql(table_name, con=connection, if_exists='append', index=False)
    return len(frame)


def _recent_stock_volumes(date):
    table_name = tbs.TABLE_CN_STOCK_SPOT['name']
    if not mdb.checkTableIsExist(table_name):
        return {}
    try:
        from sqlalchemy import text
        with mdb.engine().connect() as connection:
            date_rows = connection.execute(
                text('SELECT DISTINCT `date` FROM `%s` WHERE `date` < :date '
                     'ORDER BY `date` DESC LIMIT 5' % table_name),
                {'date': _date_key(date)},
            ).fetchall()
            history_dates = [row[0] for row in date_rows]
            if not history_dates:
                return {}
            placeholders = ','.join(':d%s' % index for index in range(len(history_dates)))
            params = {'d%s' % index: value for index, value in enumerate(history_dates)}
            history = pd.read_sql_query(
                text('SELECT `code`, `date`, `volume` FROM `%s` '
                     'WHERE `date` IN (%s) ORDER BY `code`, `date` DESC'
                     % (table_name, placeholders)),
                connection,
                params=params,
            )
        if history.empty:
            return {}
        history['code'] = history['code'].astype(str).str.zfill(6)
        result = {}
        for code, group in history.groupby('code', sort=False):
            volumes = pd.to_numeric(group['volume'], errors='coerce').dropna().head(5).tolist()
            result[code] = list(reversed(volumes))
        return result
    except Exception as exc:
        logging.warning('recent spot-volume history unavailable: %s', exc)
        return {}


# 股票实时行情数据。
def save_nph_stock_spot_data(date, before=True, force_finalize=False):
    if before:
        return
    try:
        finalize = force_finalize or _is_close_finalize(date)
        with _file_lock('stock-finalize-' + _date_key(date)) if finalize else contextlib.nullcontext():
            if (finalize and not force_finalize
                    and _final_marker_is_current('stock', date, 'tdx-daily-files-v1')):
                logging.info('stock close snapshot already finalized: %s', _date_key(date))
                return

            data = stock_data(date).get_data(date, refresh=True)
            if data is None or len(data.index) == 0:
                logging.error("basic_data_daily_job没有获取到%s股票行情，保留原有数据", date)
                return
            data = stf.apply_dynamic_volume_ratio(data, _recent_stock_volumes(date))

            stats = None
            if finalize:
                stats = stf.backfill_tdx_daily_data(data, date, return_stats=True)

            complete = bool(stats and stats.get('complete', False)) if finalize else True
            rows = _persist_daily_snapshot(
                data, 'stock-spot', date, tbs.TABLE_CN_STOCK_SPOT,
                replace_date=(not finalize or complete),
            )
            logging.info('stock spot persisted: date=%s rows=%s finalize=%s complete=%s',
                         _date_key(date), rows, finalize, complete)
            if finalize and complete:
                _write_final_marker('stock', date, 'tdx-daily-files-v1', {
                    key: value for key, value in stats.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                })
            elif finalize:
                logging.warning('TDX close snapshot incomplete; valid rows persisted and final marker withheld: %s',
                                stats)
    except Exception as e:
        logging.error(f"basic_data_daily_job.save_stock_spot_data处理异常：{e}")


# 基金实时行情数据。
def save_nph_etf_spot_data(date, before=True):
    if before:
        return
    try:
        finalize = _is_close_finalize(date)
        with _file_lock('etf-finalize-' + _date_key(date)) if finalize else contextlib.nullcontext():
            marker = _final_marker('etf', date)
            if finalize and _final_marker_is_current('etf', date, 'etf-snapshot-v1'):
                logging.info('ETF close snapshot already finalized: %s', _date_key(date))
                return

            data = stf.fetch_etfs(date)
            if data is None or len(data.index) == 0:
                logging.error("basic_data_daily_job没有获取到%s ETF行情，保留原有数据", date)
                return

            if finalize:
                stats = stf.backfill_tdx_daily_data(data, date, return_stats=True,
                                                    asset_type='etf')
                if not stats.get('complete', False):
                    raise RuntimeError('TDX ETF close backfill incomplete; final marker withheld for retry: %s' % stats)

            rows = _persist_daily_snapshot(data, 'etf-spot', date, tbs.TABLE_CN_ETF_SPOT)
            logging.info('ETF spot persisted: date=%s rows=%s finalize=%s',
                         _date_key(date), rows, finalize)
            if finalize:
                _write_final_marker('etf', date, 'etf-snapshot-v1', {
                    key: value for key, value in stats.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                })
    except Exception as e:
        logging.error(f"basic_data_daily_job.save_nph_etf_spot_data处理异常：{e}")



def main():
    parser = argparse.ArgumentParser(description='Persist daily stock and ETF snapshots')
    parser.add_argument('--repair-close-date', help='rebuild and verify a historical TDX close date (YYYY-MM-DD)')
    args = parser.parse_args()
    if args.repair_close_date:
        try:
            target_date = datetime.date.fromisoformat(args.repair_close_date)
        except ValueError:
            parser.error('--repair-close-date must use YYYY-MM-DD')
        if target_date > datetime.datetime.now(_TIMEZONE).date():
            parser.error('--repair-close-date cannot be in the future')
        _write_final_marker('stock', target_date, 'tdx-daily-files-v1',
                            {'repair_in_progress': True}, complete=False)
        save_nph_stock_spot_data(target_date, before=False, force_finalize=True)
        if not _final_marker_is_current('stock', target_date, 'tdx-daily-files-v1'):
            raise SystemExit('TDX close repair did not reach a complete state; see job log')
        return

    now = datetime.datetime.now(_TIMEZONE)
    is_trade_day = trd.is_trade_date(now.date())
    if not (is_trade_day is True or str(is_trade_day).strip().lower() in ('true', '1')):
        return
    runt.run_with_args(save_nph_stock_spot_data)
    if os.environ.get("INSTOCK_STOCK_SPOT_ONLY") != "1":
        runt.run_with_args(save_nph_etf_spot_data)


# main函数入口
if __name__ == '__main__':
    main()

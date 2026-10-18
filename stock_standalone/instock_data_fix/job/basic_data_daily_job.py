#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import argparse
import logging
import math
import stat
import os
import sys
import contextlib
import datetime
import json
import tempfile
import threading
from zoneinfo import ZoneInfo
import pandas as pd
import requests

cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
import instock.lib.run_template as runt
import instock.core.tablestructure as tbs
import instock.lib.database as mdb
import instock.lib.trade_time as trd
import instock.core.stockfetch as stf
import instock.core.tdx_hq as tdx_hq
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


_TDX_INDEX_INCEPTION = {
    '399001': '1991-04-03',
    '399006': '2010-06-01',
    '000001': '1991-07-15',
}
_TDX_INDEX_EXCHANGE = {'399001': 'SZ', '399006': 'SZ', '000001': 'SH'}
_TDX_INDEX_FINAL_SOURCE = 'tdx-index-files-v1'
_TDX_INDEX_VERIFY_BARS = 300


def _tdx_index_path(forward_dir, code):
    prefix = _TDX_INDEX_EXCHANGE[code]
    canonical = os.path.join(forward_dir, prefix + code + '.TXT')
    candidates = (canonical, os.path.join(forward_dir, prefix + code + '.txt'))
    if prefix == 'SZ' and code.startswith('399'):
        candidates += (os.path.join(forward_dir, code + '.TXT'),
                       os.path.join(forward_dir, code + '.txt'))
    return next((path for path in candidates if os.path.isfile(path)), canonical)


def _read_tdx_index_file(path):
    bars = {}
    invalid = 0
    try:
        with open(path, 'rb') as stream:
            for raw in stream:
                bar = tdx_hq.parse_daily_line(raw)
                if bar is None:
                    if raw.strip():
                        invalid += 1
                    continue
                bars[bar['date']] = bar
    except FileNotFoundError:
        pass
    return bars, invalid


def _parse_tdx_index_lines(lines, start_date, end_date):
    bars = {}
    invalid = 0
    for raw in lines or ():
        try:
            if isinstance(raw, dict):
                raw = tdx_hq.daily_bar_to_line(raw)
            if isinstance(raw, str):
                raw = raw.encode('gb18030')
            bar = tdx_hq.parse_daily_line(raw)
        except (TypeError, ValueError, UnicodeError):
            bar = None
        if bar is None:
            invalid += 1
            continue
        if start_date <= bar['date'] <= end_date:
            bars[bar['date']] = bar
    return bars, invalid


def _fetch_tencent_tdx_index_history(code, start_date, end_date):
    """Fetch Tencent daily bars and convert them to the shared TDX file format."""
    symbol = _TDX_INDEX_EXCHANGE[code].lower() + code
    url = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
    lines = []
    seen_dates = set()
    for year in range(int(start_date[:4]), int(end_date[:4]) + 1):
        params = {
            '_var': 'kline_day%s' % year,
            'param': '%s,day,%s-01-01,%s-12-31,640,' % (symbol, year, year + 1),
            'r': '0.8205512681390605',
        }
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            json_start = response.text.find('={')
            if json_start < 0:
                raise ValueError('Tencent daily history response is not valid JSONP')
            payload = json.loads(response.text[json_start + 1:].strip().rstrip(';'))
            daily_rows = payload.get('data', {}).get(symbol, {}).get('day', [])
        except Exception as exc:
            logging.warning('Tencent index history unavailable: code=%s year=%s error=%s',
                            code, year, exc)
            continue
        if not daily_rows:
            logging.info('Tencent returned no index rows: code=%s year=%s', code, year)
            continue
        for row in daily_rows:
            if len(row) < 9:
                continue
            bar_date = str(row[0])[:10]
            if bar_date < start_date or bar_date > end_date or bar_date in seen_dates:
                continue
            try:
                values = [float(row[1]), float(row[3]), float(row[4]), float(row[2]),
                          float(row[5]) * 100.0, float(row[8]) * 10000.0]
            except (TypeError, ValueError, OverflowError):
                continue
            if (not all(math.isfinite(value) for value in values)
                    or min(values[:4]) <= 0 or values[1] < max(values[0], values[2], values[3])
                    or values[2] > min(values[0], values[3])
                    or values[4] < 0 or values[5] < 0):
                continue
            try:
                line = tdx_hq.daily_bar_to_line(dict(
                    date=bar_date, open=values[0], high=values[1], low=values[2],
                    close=values[3], volume=values[4], amount=values[5],
                ))
            except (TypeError, ValueError):
                continue
            seen_dates.add(bar_date)
            lines.append(line)
    if not lines:
        raise ValueError('Tencent returned no usable daily bars for %s (%s..%s)'
                         % (symbol, start_date, end_date))
    return lines


def _fetch_tdx_index_range(code, start_date, end_date, expected_dates=(), force_fallback=False):
    bars = {}
    sources = []
    try:
        tdx_bars = tdx_hq.get_tdx_client().fetch_daily_bars(code, start_date, end_date)
        parsed, invalid = _parse_tdx_index_lines(tdx_bars, start_date, end_date)
        bars.update(parsed)
        if invalid:
            logging.warning('TDX HQ returned invalid index bars: code=%s invalid=%s', code, invalid)
        if parsed:
            sources.append('tdx-hq')
    except Exception as exc:
        logging.warning('TDX HQ index history failed: code=%s range=%s..%s error=%s',
                        code, start_date, end_date, exc)

    missing_expected = set(expected_dates) - set(bars)
    if force_fallback or end_date not in bars or missing_expected:
        try:
            fallback_lines = _fetch_tencent_tdx_index_history(code, start_date, end_date)
            parsed, invalid = _parse_tdx_index_lines(fallback_lines, start_date, end_date)
            bars.update(parsed)
            if parsed:
                sources.append('tencent')
            if invalid:
                logging.warning('Tencent returned invalid index bars: code=%s invalid=%s', code, invalid)
        except Exception as exc:
            logging.error('Tencent index-history fallback failed: code=%s range=%s..%s error=%s',
                          code, start_date, end_date, exc)
    return bars, '+'.join(sources) or 'unavailable'


def _write_tdx_index_file(path, bars):
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix='.tdx-index-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='ascii', newline='') as stream:
            for day in sorted(bars):
                stream.write(tdx_hq.daily_bar_to_line(bars[day]))
            stream.flush()
            os.fsync(stream.fileno())
        mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backfill_tdx_index_history(date, codes=None, return_stats=True):
    """Repair benchmark index bars in the shared InStock TDX daily directory."""
    target_date = _date_key(date)
    stats = {'codes': 0, 'written': 0, 'failed': 0, 'invalid_existing': 0,
             'calendar_dates': 0, 'calendar_failed': 0, 'missing_dates': 0,
             'missing_recent_dates': 0,
             'target_in_calendar': None, 'complete': False}
    try:
        target = datetime.date.fromisoformat(target_date)
        now = datetime.datetime.now(_TIMEZONE)
        if target > now.date() or (target == now.date() and now.time() < datetime.time(16, 0)):
            stats['deferred'] = 1
            return stats if return_stats else 0
        selected = list(codes or _TDX_INDEX_INCEPTION)
        if not selected or any(code not in _TDX_INDEX_INCEPTION for code in selected):
            raise ValueError('unsupported TDX benchmark index code')
        stats['codes'] = len(selected)
        forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
        if not os.path.isdir(forward_dir):
            stats['failed'] = len(selected)
            logging.error('TDX index directory does not exist: %s', forward_dir)
            return stats if return_stats else 0

        with _file_lock('tdx-index-backfill'):
            try:
                calendar = stf.fetch_stocks_trade_date()
            except Exception as exc:
                logging.warning('TDX index local trade calendar unavailable: %s', exc)
                calendar = None
            earliest_inception = min(_TDX_INDEX_INCEPTION[code] for code in selected)
            calendar_dates = sorted({
                _date_key(value) for value in (calendar or ())
                if earliest_inception <= _date_key(value) <= target_date
            })
            stats['calendar_dates'] = len(calendar_dates)
            stats['target_in_calendar'] = target_date in calendar_dates
            if not calendar_dates:
                stats['calendar_failed'] = 1
                logging.warning('TDX index calendar unavailable; target-bar verification will be used')

            code_results = []
            for code in selected:
                inception = _TDX_INDEX_INCEPTION[code]
                path = _tdx_index_path(forward_dir, code)
                existing, invalid = _read_tdx_index_file(path)
                stats['invalid_existing'] += invalid
                expected = [day for day in calendar_dates if inception <= day <= target_date]
                expected_recent = expected[-_TDX_INDEX_VERIFY_BARS:]
                missing = [day for day in expected if day not in existing]
                missing_recent = [day for day in expected_recent if day not in existing]
                stats['missing_dates'] += len(missing)
                stats['missing_recent_dates'] += len(missing_recent)
                if not existing:
                    start_date = inception
                    force_fallback = True
                elif missing_recent:
                    start_date = missing_recent[0]
                    force_fallback = True
                elif target_date not in existing and max(existing) <= target_date:
                    start_date = (datetime.date.fromisoformat(max(existing))
                                  + datetime.timedelta(days=1)).isoformat()
                    force_fallback = True
                elif target_date not in existing:
                    start_date = max(inception, (target - datetime.timedelta(days=5)).isoformat())
                    force_fallback = True
                else:
                    recent = expected_recent[-3:]
                    start_date = recent[0] if recent else max(
                        inception, (target - datetime.timedelta(days=5)).isoformat())
                    force_fallback = False

                fetch_expected = [day for day in expected_recent if day >= start_date]
                incoming, source = _fetch_tdx_index_range(
                    code, start_date, target_date, expected_dates=fetch_expected, force_fallback=force_fallback)
                merged = dict(existing)
                merged.update(incoming)
                missing_after = [day for day in expected_recent if day not in merged]
                target_found = target_date in merged
                complete = target_found and not missing_after
                canonical_path = os.path.join(forward_dir, _TDX_INDEX_EXCHANGE[code] + code + '.TXT')
                changed = (os.path.abspath(path) != os.path.abspath(canonical_path)
                           or any(day not in existing or existing[day] != bar
                                  for day, bar in incoming.items()))
                if changed:
                    _write_tdx_index_file(canonical_path, merged)
                    stats['written'] += len(incoming)
                if not complete:
                    stats['failed'] += 1
                logging.info('TDX benchmark index backfill: code=%s target=%s source=%s '
                             'existing=%s fetched=%s missing_recent=%s complete=%s',
                             code, target_date, source, len(existing), len(incoming),
                             len(missing_after), complete)
                code_results.append(complete)

            stats['complete'] = bool(code_results) and all(code_results)
        return stats if return_stats else stats['written']
    except Exception as exc:
        stats['failed'] += 1
        logging.exception('TDX benchmark index backfill failed for %s: %s', target_date, exc)
        return stats if return_stats else 0


def _tdx_index_files_have_date(date, codes=None):
    date_key = _date_key(date)
    forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
    return all(date_key in _read_tdx_index_file(_tdx_index_path(forward_dir, code))[0]
               for code in (codes or _TDX_INDEX_INCEPTION))


def save_tdx_index_history(date, before=True, force_finalize=False):
    if before:
        return
    target_date = _date_key(date)
    finalize = force_finalize or _is_close_finalize(date)
    if not finalize:
        return
    try:
        with _file_lock('tdx-index-finalize-' + target_date):
            if (not force_finalize
                    and _final_marker_is_current('tdx-index', date, _TDX_INDEX_FINAL_SOURCE)
                    and _tdx_index_files_have_date(date)):
                logging.info('TDX benchmark index bars already finalized: %s', target_date)
                return
            stats = backfill_tdx_index_history(date, return_stats=True)
            scalar_stats = {
                key: value for key, value in stats.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
            _write_final_marker('tdx-index', date, _TDX_INDEX_FINAL_SOURCE,
                                scalar_stats, complete=stats.get('complete', False))
            if not stats.get('complete', False):
                logging.error('TDX benchmark index backfill incomplete; retry remains enabled: %s', stats)
    except Exception as exc:
        logging.exception('save_tdx_index_history failed for %s: %s', target_date, exc)

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
    parser.add_argument('--repair-index-date', help='rebuild and verify benchmark index TDX files (YYYY-MM-DD)')
    args = parser.parse_args()
    if args.repair_index_date and args.repair_close_date:
        parser.error('choose only one repair date option')
    if args.repair_index_date:
        try:
            target_date = datetime.date.fromisoformat(args.repair_index_date)
        except ValueError:
            parser.error('--repair-index-date must use YYYY-MM-DD')
        if target_date > datetime.datetime.now(_TIMEZONE).date():
            parser.error('--repair-index-date cannot be in the future')
        _write_final_marker('tdx-index', target_date, _TDX_INDEX_FINAL_SOURCE,
                            {'repair_in_progress': True}, complete=False)
        save_tdx_index_history(target_date, before=False, force_finalize=True)
        if not _final_marker_is_current('tdx-index', target_date, _TDX_INDEX_FINAL_SOURCE):
            raise SystemExit('benchmark index TDX repair did not reach a complete state; see job log')
        return
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
    # The generic runner leaves before=True for non-save_nph functions.
    # Run the index close writer explicitly for this trading date.
    save_tdx_index_history(now.date(), before=False)


# main函数入口
if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os.path
import datetime
import os
import re
import tempfile
import json
import pickle
import functools
import threading
import requests
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import talib as tl
try:
    from instock.JSONData.sina_data import Sina
    from instock.JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, get_tdx_file_path
except ImportError:
    from JSONData.sina_data import Sina
    from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, get_tdx_file_path
import instock.core.tablestructure as tbs
import instock.lib.trade_time as trd
import instock.core.crawling.trade_date_hist as tdh
import instock.core.crawling.fund_etf_em as fee
import instock.core.crawling.stock_selection as sst
import instock.core.crawling.stock_lhb_em as sle
import instock.core.crawling.stock_lhb_sina as sls
import instock.core.crawling.stock_dzjy_em as sde
import instock.core.crawling.stock_hist_em as she
import instock.core.crawling.stock_fund_em as sff
import instock.core.crawling.stock_fhps_em as sfe
from instock.core.eastmoney_daily import (
    fetch_etf_spot_once,
    fetch_etf_history_once,
    fetch_external_once,
    fetch_stock_fund_flow_once,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - production runs on Linux
    fcntl = None

__author__ = 'myh '
__date__ = '2023/3/10 '

# 设置基础目录，每次加载使用。
cpath_current = os.path.dirname(os.path.dirname(__file__))
stock_hist_cache_path = os.environ.get(
    'INSTOCK_STRATEGY_PREPARED_DIR',
    os.environ.get(
        'INSTOCK_PREPARED_HISTORY_CACHE_DIR',
        os.environ.get('INSTOCK_HISTORY_CACHE_DIR',
        os.path.join(cpath_current, 'cache', 'hist'),
    ))
)
_TDX_BACKFILL_LOCAL_LOCK = threading.RLock()


def _tdx_backfill_serialized(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        lock_dir = os.path.join(cpath_current, 'cache')
        os.makedirs(lock_dir, exist_ok=True)
        with open(os.path.join(lock_dir, 'tdx-close-backfill.lock'), 'a+b') as lock_file:
            with _TDX_BACKFILL_LOCAL_LOCK:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    return function(*args, **kwargs)
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return wrapped
if not os.path.exists(stock_hist_cache_path):
    os.makedirs(stock_hist_cache_path, exist_ok=True)


def _tdx_history_source(code):
    digits = ''.join(re.findall(r'\d', str(code)))
    if len(digits) < 6:
        return None, None, None
    symbol = digits[-6:]
    if symbol.startswith(('4', '8', '92')):
        exchange = 'BJ'
    elif symbol.startswith(('5', '6', '9')):
        exchange = 'SH'
    else:
        exchange = 'SZ'
    forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
    source_path = get_tdx_file_path(forward_dir, exchange, symbol)
    if source_path is None:
        candidates = [os.path.join(forward_dir, exchange + symbol + suffix) for suffix in ('.TXT', '.txt')]
        candidates.extend(os.path.join(forward_dir, symbol + suffix) for suffix in ('.TXT', '.txt'))
        source_path = next((path for path in candidates if os.path.isfile(path)), None)
    if source_path is None:
        return symbol, None, None
    try:
        stat = os.stat(source_path)
        fingerprint = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        return symbol, source_path, fingerprint
    except OSError:
        return symbol, source_path, None


def _volume_time_ratio(now=None):
    """Match the desktop volume projection curve for an A-share trading day."""
    try:
        if now is None:
            now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
        elif now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        else:
            now = now.astimezone(ZoneInfo('Asia/Shanghai'))
        status = trd.is_trade_date(now.date())
        if not (status is True or str(status).strip().lower() in ('true', '1')):
            return 1.0
        minutes = now.hour * 60 + now.minute
        if minutes >= 15 * 60 or minutes < 9 * 60 + 20:
            return 1.0
        segments = ((570, 600, 0.35), (600, 690, 0.65),
                    (780, 840, 0.80), (840, 900, 1.00))
        previous_ratio = 0.0
        for start, end, end_ratio in segments:
            if minutes <= start:
                passed_ratio = previous_ratio
                break
            if start < minutes <= end:
                passed_ratio = previous_ratio + (end_ratio - previous_ratio) * (
                    (minutes - start) / (end - start)
                )
                break
            previous_ratio = end_ratio
        else:
            passed_ratio = 1.0
        return max(float(passed_ratio), 0.05)
    except Exception as exc:
        logging.debug('intraday volume progress unavailable: %s', exc)
        return 1.0


def _dynamic_volume_ratio(current_volume, previous_volumes, progress_ratio):
    try:
        current = float(current_volume)
        previous = []
        for value in list(previous_volumes or [])[-5:]:
            try:
                value = float(value)
                if np.isfinite(value) and value >= 0:
                    previous.append(value)
            except (TypeError, ValueError):
                continue
        if not np.isfinite(current) or current < 0:
            return 0.0
        baseline_values = previous + [current]
        baseline = float(np.mean(baseline_values)) if baseline_values else 0.0
        if baseline <= 0:
            return 0.0
        ratio = current / baseline
        stale_volume = bool(previous) and current == previous[-1]
        if progress_ratio < 1.0 and current > 0 and not stale_volume:
            ratio /= max(float(progress_ratio), 0.01)
        return round(float(ratio), 1)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def apply_dynamic_volume_ratio(data, history_by_code, now=None):
    """Add the TK-compatible projected volume ratio while preserving raw shares."""
    if data is None or data.empty or 'volume' not in data.columns:
        return data
    progress_ratio = _volume_time_ratio(now)
    result = data.copy()
    codes = result['code'].astype(str).str.split('.').str[0].str.zfill(6)
    ratios = []
    for code, volume in zip(codes.values, result['volume'].values):
        ratios.append(_dynamic_volume_ratio(
            volume, (history_by_code or {}).get(code, []), progress_ratio
        ))
    result['volume_ratio'] = ratios
    return result


# 600 601 603 605开头的股票是上证A股
# 600开头的股票是上证A股，属于大盘股，其中6006开头的股票是最早上市的股票，
# 6016开头的股票为大盘蓝筹股；900开头的股票是上证B股；
# 688开头的是上证科创板股票；
# 000开头的股票是深证A股，001、002开头的股票也都属于深证A股，
# 其中002开头的股票是深证A股中小企业股票；
# 200开头的股票是深证B股；
# 300、301开头的股票是创业板股票；400开头的股票是三板市场股票。
# 430、83、87开头的股票是北证A股
def is_a_stock(code):
    # 上证A股  # 深证A股
    return code.startswith(('600', '601', '603', '605', '688', '689', '000', '001', '002', '003', '300', '301',
                            '43', '83', '87', '92'))


# 过滤掉 st 股票。
def is_not_st(name):
    return not name.startswith(('*ST', 'ST'))


# 过滤价格，如果没有基本上是退市了。
def is_open(price):
    return not np.isnan(price)


def is_open_with_line(price):
    return price != '-'


def _format_trade_date(date):
    if hasattr(date, 'strftime'):
        return date.strftime('%Y-%m-%d')
    if date is None:
        return datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    value = str(date).strip()
    if len(value) == 8 and value.isdigit():
        return '%s-%s-%s' % (value[:4], value[4:6], value[6:8])
    return value[:10]


def _tdx_line_date(line):
    value = line.split(',', 1)[0].strip()
    if re.fullmatch(r'\d{8}', value):
        return '%s-%s-%s' % (value[:4], value[4:6], value[6:8])
    value = value[:10]
    return value if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) else None


def _tdx_history_gap_range(existing_dates, target_date, trade_dates):
    previous_dates = [date for date in existing_dates if date < target_date]
    if not previous_dates:
        return None, None
    latest_existing = max(previous_dates)
    expected_dates = trade_dates
    if expected_dates:
        latest_expected = expected_dates[-1]
        if latest_existing < latest_expected:
            next_dates = [date for date in expected_dates if date > latest_existing]
            return (next_dates[0], latest_expected) if next_dates else (None, None)

        recent_dates = expected_dates[-60:]
        run_start = None
        run_length = 0
        for date in recent_dates:
            if date not in existing_dates:
                if run_start is None:
                    run_start = date
                run_length += 1
                if run_length >= 5:
                    return run_start, latest_expected
            else:
                run_start = None
                run_length = 0
        return None, None

    if (datetime.date.fromisoformat(target_date)
            - datetime.date.fromisoformat(latest_existing)).days > 3:
        start_date = (datetime.date.fromisoformat(latest_existing)
                      + datetime.timedelta(days=1)).isoformat()
        end_date = (datetime.date.fromisoformat(target_date)
                    - datetime.timedelta(days=1)).isoformat()
        return start_date, end_date
    return None, None


def _fetch_tencent_tdx_history_gap(code, start_date, end_date):
    if code.startswith(('4', '8', '43', '83', '87', '92')):
        exchange = 'bj'
    elif code.startswith(('5', '6', '9')):
        exchange = 'sh'
    else:
        exchange = 'sz'
    symbol = exchange + code
    url = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
    lines = []
    seen_dates = set()
    for year in range(int(start_date[:4]), int(end_date[:4]) + 1):
        params = {
            '_var': 'kline_day%s' % year,
            'param': '%s,day,%s-01-01,%s-12-31,640,' % (symbol, year, year + 1),
            'r': '0.8205512681390605',
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        json_start = response.text.find('={')
        if json_start < 0:
            raise ValueError('Tencent daily history response is not valid JSONP')
        payload = json.loads(response.text[json_start + 1:].strip().rstrip(';'))
        stock_data = payload.get('data', {}).get(symbol, {})
        daily_rows = stock_data.get('day', [])
        if not daily_rows:
            raise ValueError('Tencent daily history is unavailable for %s in %s' % (symbol, year))

        for row in daily_rows:
            if len(row) < 9:
                continue
            bar_date = str(row[0])[:10]
            if bar_date < start_date or bar_date > end_date or bar_date in seen_dates:
                continue
            try:
                # Tencent returns main-board/ChiNext volume in lots and amount in 10k yuan;
                # STAR Market volume is already shares. TDX files store shares and yuan.
                volume_multiplier = 1 if symbol.startswith('sh688') else 100
                numbers = [float(row[1]), float(row[3]), float(row[4]), float(row[2]),
                           float(row[5]) * volume_multiplier, float(row[8]) * 10000]
            except (TypeError, ValueError):
                continue
            if (not np.isfinite(numbers).all() or min(numbers[:4]) <= 0
                    or numbers[4] < 0 or numbers[5] < 0):
                continue
            seen_dates.add(bar_date)
            lines.append(bar_date + ',' + ','.join(format(value, '.10g') for value in numbers) + '\n')

    if not lines:
        raise ValueError('Tencent returned no usable daily bars for %s (%s..%s)' %
                         (symbol, start_date, end_date))
    return lines


def _fetch_tdx_history_gap(code, start_date, end_date):
    fetch_history = getattr(she, 'stock_zh_a_hist', None)
    if not callable(fetch_history):
        logging.info('Eastmoney history API unavailable; using Tencent for %s', code)
        return _fetch_tencent_tdx_history_gap(code, start_date, end_date)
    try:
        history = fetch_history(
            symbol=code, period='daily', start_date=start_date.replace('-', ''),
            end_date=end_date.replace('-', ''), adjust='',
        )
        if history is None or history.empty:
            logging.info('Eastmoney returned no history for %s; using Tencent', code)
            return _fetch_tencent_tdx_history_gap(code, start_date, end_date)
    except Exception as e:
        logging.warning('Eastmoney history failed for %s; using Tencent: %s', code, e)
        return _fetch_tencent_tdx_history_gap(code, start_date, end_date)

    history = history.rename(columns={
        '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low',
        '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
    })
    required = ('date', 'open', 'high', 'low', 'close', 'volume', 'amount')
    if any(column not in history.columns for column in required):
        raise ValueError('historical quote response is missing daily bar columns')
    history = history.loc[:, required].copy()
    history['date'] = pd.to_datetime(history['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    for column in required[1:]:
        history[column] = pd.to_numeric(history[column], errors='coerce')
    history = history.dropna(subset=required)
    # Eastmoney/AkShare reports stock volume in lots; TDX daily files store shares.
    history['volume'] *= 100

    lines = []
    seen_dates = set()
    for row in history.sort_values('date').itertuples(index=False):
        bar_date = row.date
        values = [row.open, row.high, row.low, row.close, row.volume, row.amount]
        numbers = [float(value) for value in values]
        if (not isinstance(bar_date, str) or bar_date < start_date or bar_date > end_date
                or bar_date in seen_dates or not np.isfinite(numbers).all()
                or min(numbers[:4]) <= 0 or numbers[4] < 0 or numbers[5] < 0):
            continue
        seen_dates.add(bar_date)
        lines.append(bar_date + ',' + ','.join(format(value, '.10g') for value in numbers) + '\n')
    return lines


def _normalize_talib_columns(data):
    """Make TDX/AkShare numeric series safe for TA-Lib's double-only inputs."""
    for column in ('open', 'high', 'low', 'close', 'volume', 'amount', 'turnover'):
        if column in data.columns:
            values = pd.to_numeric(data[column], errors='coerce')
            if column in ('volume', 'amount', 'turnover'):
                values = values.fillna(0)
            data[column] = values.astype(np.float64)
    return data


# 读取股票交易日历数据
def fetch_stocks_trade_date():
    try:
        data = tdh.tool_trade_date_hist_sina()
        if data is None or len(data.index) == 0:
            return None
        data_date = set(data['trade_date'].values.tolist())
        return data_date
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks_trade_date处理异常：{e}")
    return None


@_tdx_backfill_serialized
def repair_tdx_history_gaps(target_date=None, return_stats=True):
    """Repair historical gaps in existing TDX stock files without writing today's quote."""
    stats = {'scanned': 0, 'gaps_detected': 0, 'files_repaired': 0,
             'gap_rows_filled': 0, 'gap_dates_missing': 0, 'gap_failed': 0,
             'failed': 0, 'calendar_failed': 0}
    try:
        target_date = _format_trade_date(target_date)
        trade_dates = fetch_stocks_trade_date()
        if not trade_dates:
            stats['calendar_failed'] = 1
            logging.error('TDX history repair skipped because the trade-date calendar is unavailable')
            return stats if return_stats else 0
        trade_dates = sorted({
            _format_trade_date(value) for value in trade_dates
            if _format_trade_date(value) < target_date
        })
        if not trade_dates:
            logging.info('TDX history repair found no completed trade dates before %s', target_date)
            return stats if return_stats else 0

        forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
        if not os.path.isdir(forward_dir):
            stats['failed'] = 1
            logging.error('TDX history repair directory does not exist: %s', forward_dir)
            return stats if return_stats else 0
        with os.scandir(forward_dir) as entries:
            paths = sorted(
                (entry.path for entry in entries
                 if entry.is_file() and entry.name.lower().endswith('.txt')),
                key=str.lower,
            )

        for path in paths:
            stem = os.path.splitext(os.path.basename(path))[0].upper()
            match = re.fullmatch(r'(?:SH|SZ|BJ)?(\d{6})', stem)
            if not match:
                continue
            code = match.group(1)
            if not is_a_stock(code):
                continue
            stats['scanned'] += 1
            try:
                with open(path, 'r', encoding='gb18030', errors='replace', newline='') as source:
                    old_lines = source.readlines()
                existing_dates = {
                    value for value in (_tdx_line_date(old_line) for old_line in old_lines)
                    if value
                }
                gap_start, gap_end = _tdx_history_gap_range(
                    existing_dates, target_date, trade_dates
                )
                if not gap_start or not gap_end or gap_start > gap_end:
                    continue

                stats['gaps_detected'] += 1
                expected_missing = {
                    value for value in trade_dates
                    if gap_start <= value <= gap_end and value not in existing_dates
                }
                try:
                    fetched_lines = _fetch_tdx_history_gap(code, gap_start, gap_end)
                    gap_lines = {
                        _tdx_line_date(line): line for line in fetched_lines
                        if _tdx_line_date(line) in expected_missing
                    }
                except Exception as e:
                    stats['gap_failed'] += 1
                    stats['gap_dates_missing'] += len(expected_missing)
                    logging.error('TDX history gap repair failed for %s (%s..%s): %s',
                                  code, gap_start, gap_end, e)
                    continue

                stats['gap_rows_filled'] += len(gap_lines)
                stats['gap_dates_missing'] += len(expected_missing - set(gap_lines))
                if not gap_lines:
                    continue

                pending_dates = sorted(gap_lines)
                merged = []
                pending_index = 0
                for old_line in old_lines:
                    old_date = _tdx_line_date(old_line)
                    while (pending_index < len(pending_dates) and old_date
                           and pending_dates[pending_index] < old_date):
                        merged.append(gap_lines[pending_dates[pending_index]])
                        pending_index += 1
                    merged.append(old_line if old_line.endswith(('\n', '\r')) else old_line + '\n')
                merged.extend(gap_lines[value] for value in pending_dates[pending_index:])

                fd, temporary = tempfile.mkstemp(prefix=code + '.', suffix='.tmp', dir=forward_dir)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as destination:
                        destination.writelines(merged)
                        destination.flush()
                        os.fsync(destination.fileno())
                    os.chmod(temporary, os.stat(path).st_mode & 0o777)
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                stats['files_repaired'] += 1
            except Exception as e:
                stats['failed'] += 1
                logging.error('TDX history repair failed for %s: %s', path, e)

        logging.info('TDX history-only repair completed: target=%s scanned=%s gaps=%s repaired=%s '
                     'rows_filled=%s dates_missing=%s gap_failed=%s failed=%s',
                     target_date, stats['scanned'], stats['gaps_detected'],
                     stats['files_repaired'], stats['gap_rows_filled'],
                     stats['gap_dates_missing'], stats['gap_failed'], stats['failed'])
        return stats if return_stats else stats['files_repaired']
    except Exception as e:
        logging.exception('stockfetch.repair_tdx_history_gaps处理异常：%s', e)
        stats['failed'] += 1
        return stats if return_stats else 0


def _save_etf_codes(codes, date):
    cache_dir = os.path.join(cpath_current, 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'etf-codes.txt')
    stamp_path = os.path.join(cache_dir, 'etf-codes.date')
    fd, temporary = tempfile.mkstemp(prefix='etf-codes.', suffix='.tmp', dir=cache_dir)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write('\n'.join(sorted(codes)) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    fd, stamp_temporary = tempfile.mkstemp(prefix='etf-codes-date.', suffix='.tmp', dir=cache_dir)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            stream.write(_format_trade_date(date))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stamp_temporary, stamp_path)
    finally:
        if os.path.exists(stamp_temporary):
            os.unlink(stamp_temporary)


def _get_etf_codes(date):
    cache_dir = os.path.join(cpath_current, 'cache')
    cache_path = os.path.join(cache_dir, 'etf-codes.txt')
    stamp_path = os.path.join(cache_dir, 'etf-codes.date')
    codes = set()
    try:
        with open(cache_path, 'r', encoding='ascii') as stream:
            codes.update(line.strip() for line in stream if line.strip().isdigit())
    except OSError:
        pass

    try:
        with open(stamp_path, 'r', encoding='ascii') as stream:
            refreshed = stream.read().strip() == _format_trade_date(date)
    except OSError:
        refreshed = False

    table_name = tbs.TABLE_CN_ETF_SPOT['name']
    if not refreshed:
        try:
            from instock.lib import database as mdb
            if mdb.checkTableIsExist(table_name):
                with mdb.engine().connect() as connection:
                    frame = pd.read_sql_query('SELECT DISTINCT `code` FROM `%s`' % table_name,
                                              connection)
                codes.update(str(value).split('.')[0].zfill(6) for value in frame['code'].dropna())
                if codes:
                    _save_etf_codes(codes, date)
        except Exception as e:
            logging.warning('ETF code universe database lookup failed: %s', e)

    if not codes:
        forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
        try:
            for entry in os.scandir(forward_dir):
                match = re.match(r'(?:SH|SZ)?([0-9]{6})\.txt$', entry.name, re.IGNORECASE)
                if entry.is_file() and match and match.group(1).startswith(('1', '5')):
                    codes.add(match.group(1))
        except OSError:
            pass

    if len(codes) < 50:
        seed = fetch_etf_spot_once(date)
        if seed is not None and not seed.empty:
            codes.update(seed['code'].astype(str).str.split('.').str[0].str.zfill(6))

    codes = {code for code in codes if code.isdigit() and len(code) == 6
             and code.startswith(('1', '5'))}
    if codes:
        _save_etf_codes(codes, date)
    return sorted(codes)


def _save_etf_metadata(metadata, date):
    cache_dir = os.path.join(cpath_current, 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'etf-metadata-%s.pkl' % _format_trade_date(date))
    fd, temporary = tempfile.mkstemp(prefix='etf-metadata.', suffix='.tmp', dir=cache_dir)
    try:
        with os.fdopen(fd, 'wb') as stream:
            pd.to_pickle(metadata, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _get_etf_metadata(date):
    path = os.path.join(cpath_current, 'cache',
                        'etf-metadata-%s.pkl' % _format_trade_date(date))
    try:
        metadata = pd.read_pickle(path)
        if isinstance(metadata, pd.DataFrame):
            return metadata
    except (OSError, EOFError, ValueError, TypeError, pickle.UnpicklingError):
        pass

    try:
        from instock.lib import database as mdb
        table_name = tbs.TABLE_CN_ETF_SPOT['name']
        if mdb.checkTableIsExist(table_name):
            query = (
                'SELECT `code`,`new_price`,`turnoverrate`,`total_market_cap`,`free_cap` '
                'FROM `%s` WHERE `date`=(SELECT MAX(`date`) FROM `%s` '
                'WHERE `total_market_cap` > 0)' % (table_name, table_name)
            )
            with mdb.engine().connect() as connection:
                metadata = pd.read_sql_query(query, connection)
            if not metadata.empty:
                metadata['code'] = metadata['code'].astype(str).str.split('.').str[0].str.zfill(6)
                _save_etf_metadata(metadata, date)
                return metadata
    except Exception as e:
        logging.debug('ETF cached metadata lookup failed: %s', e)
    return pd.DataFrame(columns=['code', 'new_price', 'turnoverrate',
                                 'total_market_cap', 'free_cap'])


# ETF实时价格和成交量使用Sina；东方财富仅提供代码种子与收盘补充字段。
def fetch_etfs(date):
    try:
        codes = _get_etf_codes(date)
        if not codes:
            logging.error('stockfetch.fetch_etfs没有可用ETF代码池')
            return None
        quotes = Sina().market_codes(codes)
        if quotes is None or quotes.empty:
            return None
        target_date = _format_trade_date(date)
        quotes = quotes.copy()
        quotes['code'] = quotes['code'].astype(str).str.zfill(6)
        quotes = quotes.loc[quotes['dt'].astype(str).str[:10] == target_date]
        quotes = quotes.drop_duplicates('code', keep='last')
        minimum = max(50, int(len(codes) * 0.7))
        if len(quotes) < minimum:
            logging.error('Sina ETF行情覆盖不足: %s/%s', len(quotes), minimum)
            return None

        metadata = _get_etf_metadata(date)
        now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
        if target_date == now.date().isoformat() and now.weekday() < 5 \
                and now.time() >= datetime.time(16, 0):
            current_metadata = fetch_etf_spot_once(date)
            if current_metadata is not None and not current_metadata.empty:
                metadata = current_metadata[['code', 'new_price', 'turnoverrate',
                                             'total_market_cap', 'free_cap']].copy()
                metadata['code'] = metadata['code'].astype(str).str.zfill(6)
                _save_etf_metadata(metadata, date)
        if metadata is not None and not metadata.empty:
            metadata = metadata.drop_duplicates('code', keep='last').set_index('code')
            for column in ('turnoverrate', 'total_market_cap', 'free_cap'):
                quotes[column] = quotes['code'].map(metadata[column])
                quotes[column] = pd.to_numeric(quotes[column], errors='coerce').fillna(0)

        def metadata_values(column):
            if column not in quotes.columns:
                return np.zeros(len(quotes), dtype=np.float64)
            return pd.to_numeric(quotes[column], errors='coerce').fillna(0).values

        previous = pd.to_numeric(quotes['close'], errors='coerce').fillna(0)
        current = pd.to_numeric(quotes['now'], errors='coerce').fillna(0)
        values = {
            'date': target_date,
            'code': quotes['code'].values,
            'name': quotes['name'].fillna('').values,
            'new_price': current.values,
            'change_rate': np.where(previous != 0, (current - previous) / previous * 100, 0),
            'ups_downs': (current - previous).values,
            'volume': pd.to_numeric(quotes['volume'], errors='coerce').fillna(0).values,
            'deal_amount': pd.to_numeric(quotes['turnover'], errors='coerce').fillna(0).values,
            'open_price': pd.to_numeric(quotes['open'], errors='coerce').fillna(0).values,
            'high_price': pd.to_numeric(quotes['high'], errors='coerce').fillna(0).values,
            'low_price': pd.to_numeric(quotes['low'], errors='coerce').fillna(0).values,
            'pre_close_price': previous.values,
            'turnoverrate': metadata_values('turnoverrate'),
            'total_market_cap': metadata_values('total_market_cap'),
            'free_cap': metadata_values('free_cap'),
        }
        columns = list(tbs.TABLE_CN_ETF_SPOT['columns'])
        return pd.DataFrame({column: values.get(column, 0) for column in columns},
                            index=range(len(quotes)))
    except Exception as e:
        logging.error('stockfetch.fetch_etfs Sina行情获取失败：%s', e)
    return None


# 读取当天股票数据
def fetch_stocks(date):
    try:
        quotes = Sina().market('all')
        if quotes is None or quotes.empty:
            return None
        quotes = quotes.copy()
        quotes['code'] = quotes['code'].astype(str).str.zfill(6)
        quotes = quotes.loc[quotes['code'].apply(is_a_stock)]
        target_date = _format_trade_date(date)
        quote_dates = quotes['dt'].astype(str).str[:10]
        quotes = quotes.loc[quote_dates == target_date].drop_duplicates('code', keep='last')
        minimum = max(500, int(len(_get_tdx_stock_codes()) * 0.7))
        if len(quotes) < minimum:
            logging.error('stockfetch.fetch_stocks Sina行情覆盖不足: %s/%s', len(quotes), minimum)
            return None

        previous = pd.to_numeric(quotes['close'], errors='coerce').fillna(0)
        current = pd.to_numeric(quotes['now'], errors='coerce').fillna(0)
        high = pd.to_numeric(quotes['high'], errors='coerce').fillna(0)
        low = pd.to_numeric(quotes['low'], errors='coerce').fillna(0)
        values = {
            'date': target_date,
            'code': quotes['code'].values,
            'name': quotes['name'].fillna('').values,
            'new_price': current.values,
            'change_rate': np.where(previous != 0, (current - previous) / previous * 100, 0),
            'ups_downs': (current - previous).values,
            'volume': pd.to_numeric(quotes['volume'], errors='coerce').fillna(0).values,
            'deal_amount': pd.to_numeric(quotes['turnover'], errors='coerce').fillna(0).values,
            'amplitude': np.where(previous != 0, (high - low) / previous * 100, 0),
            'open_price': pd.to_numeric(quotes['open'], errors='coerce').fillna(0).values,
            'high_price': high.values,
            'low_price': low.values,
            'pre_close_price': previous.values,
        }
        columns = list(tbs.TABLE_CN_STOCK_SPOT['columns'])
        data = pd.DataFrame(index=range(len(quotes)))
        for column in columns:
            if column in values:
                data[column] = values[column]
            elif column == 'industry':
                data[column] = ''
            elif column in ('report_date', 'listing_date'):
                data[column] = None
            else:
                data[column] = 0
        return data[columns]
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks处理异常：{e}")
    return None


_TDX_STOCK_CODES_CACHE = {}


def _get_tdx_stock_codes():
    """Return the persistent TDX code universe for quote coverage validation."""
    forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
    try:
        dir_stat = os.stat(forward_dir)
        cache_key = (forward_dir, dir_stat.st_mtime_ns)
        cached = _TDX_STOCK_CODES_CACHE.get(cache_key)
        if cached is not None:
            return cached
        codes = set()
        for path in os.scandir(forward_dir):
            match = re.match(r'(?:SH|SZ|BJ)?([0-9]{6})\.txt$', path.name, re.IGNORECASE)
            if path.is_file() and match and is_a_stock(match.group(1)):
                codes.add(match.group(1))
        _TDX_STOCK_CODES_CACHE.clear()
        _TDX_STOCK_CODES_CACHE[cache_key] = codes
        return codes
    except OSError:
        return set()


def fetch_stock_selection():
    try:
        def fetcher():
            data = sst.stock_selection()
            if data is None or len(data.index) == 0:
                return None
            data.columns = list(tbs.TABLE_CN_STOCK_SELECTION['columns'])
            data.drop_duplicates('code', keep='last', inplace=True)
            return data

        return fetch_external_once('stock-selection', None, fetcher, after_close=False)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks_selection处理异常：{e}")
    return None


# 读取股票资金流向
def fetch_stocks_fund_flow(index, date=None):
    try:
        return fetch_stock_fund_flow_once(index, date)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks_fund_flow处理异常：{e}")
    return None


# 读取板块资金流向
def fetch_stocks_sector_fund_flow(index_sector, index_indicator):
    try:
        cn_flow = tbs.CN_STOCK_SECTOR_FUND_FLOW[1][index_indicator]

        def fetcher():
            data = sff.stock_sector_fund_flow_rank(
                indicator=cn_flow['cn'],
                sector_type=tbs.CN_STOCK_SECTOR_FUND_FLOW[0][index_sector],
            )
            if data is None or len(data.index) == 0:
                return None
            data.columns = list(cn_flow['columns'])
            return data

        dataset = 'sector-flow-%s-%s' % (index_sector, index_indicator)
        return fetch_external_once(dataset, None, fetcher, after_close=True, eastmoney=True)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks_sector_fund_flow处理异常：{e}")
    return None


# 读取股票分红配送
def fetch_stocks_bonus(date):
    try:
        def fetcher():
            data = sfe.stock_fhps_em(date=trd.get_bonus_report_date())
            if data is None or len(data.index) == 0:
                return None
            if date is None:
                data.insert(0, 'date', datetime.datetime.now().strftime("%Y-%m-%d"))
            else:
                data.insert(0, 'date', date.strftime("%Y-%m-%d"))
            data.columns = list(tbs.TABLE_CN_STOCK_BONUS['columns'])
            return data.loc[data['code'].apply(is_a_stock)]

        return fetch_external_once('stock-bonus', date, fetcher,
                                   after_close=True, eastmoney=True)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stocks_bonus处理异常：{e}")
    return None


# 股票近三月上龙虎榜且必须有2次以上机构参与的
def fetch_stock_top_entity_data(date):
    run_date = date + datetime.timedelta(days=-90)
    start_date = run_date.strftime("%Y%m%d")
    end_date = date.strftime("%Y%m%d")
    code_name = '代码'
    entity_amount_name = '买方机构数'
    try:
        def fetcher():
            data = sle.stock_lhb_jgmmtj_em(start_date, end_date)
            if data is None or len(data.index) == 0:
                return None

            # 90日内机构买方次数累计大于1的股票才参与筛选。
            data = data.loc[data[entity_amount_name] > 0]
            if data.empty:
                return None
            data_series = data.groupby(by=data[code_name])[entity_amount_name].sum()
            data_code = set(data_series[data_series > 1].index.values)
            return data_code or None

        return fetch_external_once('lhb-entity-%s-%s' % (start_date, end_date), date,
                                   fetcher, after_close=False, eastmoney=True)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stock_top_entity_data处理异常：{e}")
    return None


# 描述: 获取新浪财经-龙虎榜-个股上榜统计
def fetch_stock_top_data(date):
    try:
        def fetcher():
            data = sls.stock_lhb_ggtj_sina()
            if data is None or len(data.index) == 0:
                return None
            columns = list(tbs.TABLE_CN_STOCK_TOP['columns'])
            columns.pop(0)
            data.columns = columns
            data = data.loc[data['code'].apply(is_a_stock)]
            data.drop_duplicates('code', keep='last', inplace=True)
            if date is None:
                data.insert(0, 'date', datetime.datetime.now().strftime("%Y-%m-%d"))
            else:
                data.insert(0, 'date', date.strftime("%Y-%m-%d"))
            return data

        return fetch_external_once('lhb-sina', date, fetcher, after_close=False)
    except Exception as e:
        logging.error(f"stockfetch.fetch_stock_top_data处理异常：{e}")
    return None


# 描述: 获取东方财富网-数据中心-大宗交易-每日统计
def fetch_stock_blocktrade_data(date):
    date_str = date.strftime("%Y%m%d")
    try:
        def fetcher():
            data = sde.stock_dzjy_mrtj(start_date=date_str, end_date=date_str)
            if data is None or len(data.index) == 0:
                return None
            columns = list(tbs.TABLE_CN_STOCK_BLOCKTRADE['columns'])
            columns.insert(0, 'index')
            data.columns = columns
            data = data.loc[data['code'].apply(is_a_stock)]
            data.drop('index', axis=1, inplace=True)
            return data

        return fetch_external_once('stock-blocktrade', date, fetcher,
                                   after_close=True, eastmoney=True)
    except TypeError:
        logging.error("处理异常：目前还没有大宗交易数据，请17:00点后再获取！")
        return None
    except Exception as e:
        logging.error(f"stockfetch.fetch_stock_blocktrade_data处理异常：{e}")
    return None


# 读取股票历史数据
def fetch_etf_hist(data_base, date_start=None, date_end=None, adjust='qfq'):
    date = data_base[0]
    code = data_base[1]

    if date_start is None:
        date_start, _ = trd.get_trade_hist_interval(date)
    try:
        if adjust in ('', 'qfq'):
            tdx_data = get_tdx_Exp_day_to_df(code, start=date_start, end=date_end,
                                             dl=10000, fastohlc=True)
            if tdx_data is not None and not tdx_data.empty:
                data = tdx_data.reset_index().rename(columns={'vol': 'volume'})
                previous = data['close'].shift(1)
                data['amplitude'] = np.where(previous.fillna(0) != 0,
                                             (data['high'] - data['low']) / previous * 100, 0)
                data['quote_change'] = np.where(previous.fillna(0) != 0,
                                                (data['close'] - previous) / previous * 100, 0)
                data['ups_downs'] = (data['close'] - previous).fillna(0)
                data['turnover'] = 0.0
                data = _normalize_talib_columns(data)
                data = data[list(tbs.CN_STOCK_HIST_DATA['columns'])]
                data['p_change'] = tl.ROC(data['close'].to_numpy(dtype=np.float64), 1)
                data['p_change'].values[np.isnan(data['p_change'].values)] = 0.0
                return data

        def fetcher():
            if date_end is not None:
                data = fee.fund_etf_hist_em(symbol=code, period="daily", start_date=date_start,
                                            end_date=date_end, adjust=adjust)
            else:
                data = fee.fund_etf_hist_em(symbol=code, period="daily", start_date=date_start,
                                            adjust=adjust)
            if data is None or len(data.index) == 0:
                return None
            data.columns = tuple(tbs.CN_STOCK_HIST_DATA['columns'])
            data = _normalize_talib_columns(data.sort_index())
            data.loc[:, 'p_change'] = tl.ROC(data['close'].to_numpy(dtype=np.float64), 1)
            data['p_change'].values[np.isnan(data['p_change'].values)] = 0.0
            data['volume'] = data['volume'].astype('float64') * 100
            return data

        return fetch_etf_history_once(code, date, date_start, date_end, adjust, fetcher)
    except Exception as e:
        logging.error(f"stockfetch.fetch_etf_hist处理异常：{e}")
    return None


# 读取股票历史数据
def fetch_stock_hist(data_base, date_start=None, is_cache=True):
    date = data_base[0]
    code = data_base[1]

    if date_start is None:
        date_start, is_cache = trd.get_trade_hist_interval(date)  # 提高运行效率，只运行一次
        # date_end = date_end.strftime("%Y%m%d")
    try:
        date_end = str(date)[:10] if os.environ.get('INSTOCK_COLUMNAR_HISTORY_CACHE') else None
        data = stock_hist_cache(code, date_start, date_end, is_cache, 'qfq')
        if data is not None:
            data = _normalize_talib_columns(data)
            data.loc[:, 'p_change'] = tl.ROC(data['close'].to_numpy(dtype=np.float64), 1)
            data['p_change'].values[np.isnan(data['p_change'].values)] = 0.0
        return data
    except Exception as e:
        logging.error(f"stockfetch.fetch_stock_hist处理异常：{e}")
    return None


# 增加读取股票缓存方法。加快处理速度。多线程解决效率
def stock_hist_cache(code, date_start, date_end=None, is_cache=True, adjust=''):
    if os.environ.get('INSTOCK_PREPARED_HISTORY_CACHE_DIR'):
        try:
            from instock.JSONData.prepared_history import prepared_history
        except ImportError:
            from JSONData.prepared_history import prepared_history
        symbol, path, fingerprint = _tdx_history_source(code)
        if path and fingerprint:
            signature = (str(date_start or ''), str(date_end or ''), adjust, tuple(tbs.CN_STOCK_HIST_DATA['columns']), path, fingerprint)
            cache_path = os.path.join(stock_hist_cache_path, symbol + '-' + (adjust or 'raw') + '.pkl')
            return prepared_history(cache_path, signature, lambda: _stock_hist_cache_uncached(code, date_start, date_end, is_cache, adjust))
    return _stock_hist_cache_uncached(code, date_start, date_end, is_cache, adjust)


def _stock_hist_cache_uncached(code, date_start, date_end=None, is_cache=True, adjust=''):
    symbol, source_path, source_fingerprint = _tdx_history_source(code)
    cache_fingerprint = None
    cache_path = None
    if source_path and source_fingerprint and (os.environ.get('INSTOCK_PREPARED_HISTORY_CACHE_DIR') or not os.environ.get('INSTOCK_HISTORY_CACHE_DIR')):
        cache_fingerprint = (
            str(date_start or ''), str(date_end or ''), str(adjust or ''),
            tuple(tbs.CN_STOCK_HIST_DATA['columns']), source_path, source_fingerprint,
        )
        cache_name = re.sub(r'[^A-Za-z0-9_.-]', '_', str(adjust or 'raw'))
        cache_path = os.path.join(stock_hist_cache_path, '%s-%s.pkl' % (symbol, cache_name))
        try:
            payload = None if os.environ.get('INSTOCK_COLUMNAR_HISTORY_CACHE') else pd.read_pickle(cache_path)
            if (isinstance(payload, dict) and payload.get('version') == 1
                    and payload.get('fingerprint') == cache_fingerprint
                    and isinstance(payload.get('data'), pd.DataFrame)):
                try:
                    from instock.JSONData.history_cache import _count
                except ImportError:
                    from JSONData.history_cache import _count
                _count('prepared_hits')
                return payload['data']
        except (OSError, EOFError, ValueError, TypeError, pickle.UnpicklingError):
            logging.debug('TDX history cache miss for %s', symbol)
        except Exception as e:
            logging.debug('TDX history cache read failed for %s: %s', symbol, e)

    try:
        rows = int(os.environ.get('INSTOCK_HIST_LOOKBACK_ROWS', '150')) + 1 if os.environ.get('INSTOCK_COLUMNAR_HISTORY_CACHE') else 10000
        stock = get_tdx_Exp_day_to_df(code, start=date_start, end=date_end, dl=rows, fastohlc=True)
        if stock is None or stock.empty:
            return None
        stock = stock.reset_index().rename(columns={'vol': 'volume'})
        stock = _normalize_talib_columns(stock)
        previous = stock['close'].shift(1)
        stock['amplitude'] = np.where(previous.fillna(0) != 0,
                                      (stock['high'] - stock['low']) / previous * 100, 0)
        stock['quote_change'] = np.where(previous.fillna(0) != 0,
                                         (stock['close'] - previous) / previous * 100, 0)
        stock['ups_downs'] = (stock['close'] - previous).fillna(0)
        stock['turnover'] = 0.0
        stock = _normalize_talib_columns(stock)
        result = stock[list(tbs.CN_STOCK_HIST_DATA['columns'])]
        if cache_path and cache_fingerprint and not os.environ.get('INSTOCK_COLUMNAR_HISTORY_CACHE'):
            _, current_path, current_source_fingerprint = _tdx_history_source(code)
            if current_path == source_path and current_source_fingerprint == source_fingerprint:
                temporary = None
                try:
                    os.makedirs(stock_hist_cache_path, exist_ok=True)
                    fd, temporary = tempfile.mkstemp(prefix=symbol + '.', suffix='.tmp',
                                                     dir=stock_hist_cache_path)
                    with os.fdopen(fd, 'wb') as stream:
                        pd.to_pickle({
                            'version': 1,
                            'fingerprint': cache_fingerprint,
                            'data': result,
                        }, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, cache_path)
                except Exception as e:
                    logging.debug('TDX history cache write failed for %s: %s', symbol, e)
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
        return result
    except Exception as e:
        logging.error(f"stockfetch.stock_hist_cache处理异常：{code}代码{e}")
    return None


@_tdx_backfill_serialized
def backfill_tdx_daily_data(data, date, return_stats=False, asset_type='stock'):
    """Repair recent TDX stock-history gaps and atomically upsert today's Sina close."""
    stats = {'eligible': 0, 'written': 0, 'unchanged': 0, 'failed': 0, 'deferred': 0,
             'gaps_detected': 0, 'gap_rows_filled': 0, 'gap_failed': 0}
    try:
        target_date = _format_trade_date(date)
        now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
        if target_date != now.strftime('%Y-%m-%d') or now.time() < datetime.time(16, 0):
            logging.info('skip TDX close backfill before market close or for a non-current date: %s', target_date)
            stats['deferred'] = 1
            return stats if return_stats else 0
        if data is None or data.empty:
            return stats if return_stats else 0
        trade_dates = set()
        if asset_type != 'etf':
            try:
                trade_dates = sorted({
                    _format_trade_date(value) for value in (fetch_stocks_trade_date() or set())
                })
                trade_dates = [value for value in trade_dates if value < target_date]
            except Exception as e:
                logging.warning('TDX history gap calendar unavailable: %s', e)
        forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
        os.makedirs(forward_dir, exist_ok=True)
        for row in data.itertuples(index=False):
            code = str(row.code).zfill(6)
            is_etf = asset_type == 'etf'
            if not code.isdigit() or (is_etf and not code.startswith(('1', '5'))) \
                    or (not is_etf and not is_a_stock(code)):
                continue
            values = [row.open_price, row.high_price, row.low_price, row.new_price,
                      row.volume, row.deal_amount]
            numbers = [float(value) for value in values]
            if not np.isfinite(numbers).all() or numbers[0] <= 0 or numbers[1] <= 0 or numbers[2] <= 0 or numbers[3] <= 0:
                continue
            stats['eligible'] += 1
            line = target_date + ',' + ','.join(format(value, '.10g') for value in numbers) + '\n'
            exchange = ('BJ' if code.startswith(('4', '8', '92')) else
                        'SH' if code.startswith(('5', '6', '9')) else 'SZ')
            names = [exchange + code + '.TXT', exchange + code + '.txt', code + '.TXT', code + '.txt']
            path = next((os.path.join(forward_dir, name) for name in names
                         if os.path.exists(os.path.join(forward_dir, name))),
                        os.path.join(forward_dir, names[0]))
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='gb18030', errors='replace', newline='') as source:
                        old_lines = source.readlines()
                else:
                    old_lines = []
                existing_dates = {value for value in (_tdx_line_date(old_line) for old_line in old_lines)
                                  if value}
                gap_lines = []
                if asset_type != 'etf':
                    gap_start, gap_end = _tdx_history_gap_range(
                        existing_dates, target_date, trade_dates
                    )
                    if gap_start and gap_end and gap_start <= gap_end:
                        stats['gaps_detected'] += 1
                        try:
                            fetched_lines = _fetch_tdx_history_gap(code, gap_start, gap_end)
                            gap_lines = [
                                history_line for history_line in fetched_lines
                                if _tdx_line_date(history_line) not in existing_dates
                                and _tdx_line_date(history_line) != target_date
                            ]
                            stats['gap_rows_filled'] += len(gap_lines)
                        except Exception as e:
                            stats['gap_failed'] += 1
                            logging.error('TDX history gap repair failed for %s (%s..%s): %s',
                                          code, gap_start, gap_end, e)
                merged = []
                replaced = False
                inserted_gap = False
                date_matches = 0
                same_record = False
                for old_line in old_lines:
                    old_date = _tdx_line_date(old_line)
                    if old_date == target_date:
                        if not inserted_gap:
                            merged.extend(gap_lines)
                            inserted_gap = True
                        date_matches += 1
                        if not replaced:
                            merged.append(line)
                            replaced = True
                            same_record = old_line.rstrip('\r\n') == line.rstrip('\n')
                    else:
                        merged.append(old_line if old_line.endswith(('\n', '\r')) else old_line + '\n')
                if not inserted_gap:
                    merged.extend(gap_lines)
                if not replaced:
                    merged.append(line)
                if date_matches == 1 and same_record and not gap_lines:
                    stats['unchanged'] += 1
                    continue
                fd, temporary = tempfile.mkstemp(prefix=code + '.', suffix='.tmp', dir=forward_dir)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as destination:
                        destination.writelines(merged)
                        destination.flush()
                        os.fsync(destination.fileno())
                    if os.path.exists(path):
                        os.chmod(temporary, os.stat(path).st_mode & 0o777)
                    else:
                        os.chmod(temporary, 0o644)
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                stats['written'] += 1
            except Exception as e:
                stats['failed'] += 1
                logging.error('TDX close backfill failed for %s: %s', code, e)
        logging.info('TDX %s close backfill completed: date=%s eligible=%s written=%s unchanged=%s '
                     'gaps=%s gap_rows=%s gap_failed=%s failed=%s',
                     asset_type, target_date, stats['eligible'], stats['written'],
                     stats['unchanged'], stats['gaps_detected'], stats['gap_rows_filled'],
                     stats['gap_failed'], stats['failed'])
        return stats if return_stats else stats['written']
    except Exception as e:
        logging.error('stockfetch.backfill_tdx_daily_data处理异常：%s', e)
        stats['failed'] += 1
        return stats if return_stats else 0


if __name__ == "__main__":
    date_start, is_cache = trd.get_trade_hist_interval('2025-05-29') 
    data = stock_hist_cache('688819', date_start, None, is_cache, 'qfq')
    print(f'data:{data}')

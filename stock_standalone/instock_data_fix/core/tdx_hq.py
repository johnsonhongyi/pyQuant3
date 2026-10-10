"""Small pytdx adapter for InStock snapshots and daily-bar repair."""

import datetime
import json
import logging
import math
import os
import threading
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)
_BATCH_SIZE = 40
_DAILY_CATEGORY = 4  # pytdx TDXParams.KLINE_TYPE_DAILY


class TDXUnavailable(RuntimeError):
    pass


def normalize_code(code):
    value = str(code or '').strip().split('.')[0].zfill(6)
    return value if len(value) == 6 and value.isdigit() else ''


def market_code(code):
    code = normalize_code(code)
    if code.startswith(('92', '89', '88', '87', '83', '82', '43')):
        return 2
    if code.startswith(('6', '5', '9')):
        return 1
    return 0


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _day(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%Y-%m-%d')
    value = str(value or '').strip()[:10]
    if len(value) == 8 and value.isdigit():
        return '%s-%s-%s' % (value[:4], value[4:6], value[6:8])
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def validate_daily_bar(bar):
    if not isinstance(bar, dict):
        return False
    day = _day(bar.get('date', bar.get('datetime')))
    values = [_number(bar.get(key)) for key in ('open', 'high', 'low', 'close', 'volume', 'amount')]
    if not day or any(value is None for value in values):
        return False
    open_price, high, low, close, volume, amount = values
    return (
        min(open_price, high, low, close) > 0
        and high >= max(open_price, low, close)
        and low <= min(open_price, high, close)
        and volume >= 0 and amount >= 0
    )


def quote_to_snapshot(code, quote, target_date):
    """Return (status, row): status is valid, no_trade, or invalid."""
    code = normalize_code(code)
    if not code or not isinstance(quote, dict):
        return 'invalid', None
    quoted_code = normalize_code(quote.get('code'))
    if quoted_code and quoted_code != code:
        return 'invalid', None

    values = {
        'price': _number(quote.get('price', quote.get('trade'))),
        'pre_close': _number(quote.get('last_close', quote.get('pre_close'))),
        'open': _number(quote.get('open')),
        'high': _number(quote.get('high')),
        'low': _number(quote.get('low')),
        'volume_lots': _number(quote.get('vol', quote.get('volume'))),
        'amount': _number(quote.get('amount')),
    }
    if any(value is None for value in values.values()):
        return 'invalid', None
    if values['volume_lots'] == 0 and values['amount'] == 0:
        return 'no_trade', None
    if values['volume_lots'] <= 0 or values['amount'] <= 0:
        return 'invalid', None

    price, open_price, high, low = (
        values['price'], values['open'], values['high'], values['low']
    )
    if (min(price, open_price, high, low) <= 0
            or high < max(price, open_price, low)
            or low > min(price, open_price)):
        return 'invalid', None

    previous = values['pre_close']
    change = ((price - previous) / previous * 100.0) if previous and previous > 0 else None
    amplitude = ((high - low) / previous * 100.0) if previous and previous > 0 else None
    return 'valid', {
        'date': _day(target_date),
        'code': code,
        'name': str(quote.get('name') or ''),
        'new_price': price,
        'change_rate': change,
        'ups_downs': price - previous if previous and previous > 0 else None,
        'volume': values['volume_lots'] * 100.0,
        'deal_amount': values['amount'],
        'amplitude': amplitude,
        'open_price': open_price,
        'high_price': high,
        'low_price': low,
        'pre_close_price': previous if previous > 0 else None,
    }


def parse_daily_line(raw_line):
    try:
        parts = raw_line.decode('gb18030', errors='replace').strip().split(',')
        if len(parts) < 7:
            return None
        day = _day(parts[0])
        values = [_number(value) for value in parts[1:7]]
        if not day or any(value is None for value in values):
            return None
        bar = dict(zip(('open', 'high', 'low', 'close', 'volume', 'amount'), values))
        bar['date'] = day
        return bar if validate_daily_bar(bar) else None
    except (AttributeError, UnicodeError, ValueError):
        return None


def read_tdx_tail_bars(path, target_date, max_bytes=131072, max_bars=2):
    """Read a bounded file tail and return the latest valid bars plus malformed-line count."""
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as source:
            source.seek(max(0, size - max_bytes))
            payload = source.read()
    except OSError:
        return [], 0
    if not payload:
        return [], 0

    lines = payload.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]  # discard the partial line at the beginning of the window
    by_date = {}
    invalid = 0
    for line in lines:
        if not line.strip():
            continue
        bar = parse_daily_line(line)
        if bar is None:
            invalid += 1
        else:
            by_date[bar['date']] = bar

    target = _day(target_date)
    selected = []
    if target and target in by_date:
        selected.append(by_date[target])
        previous = [day for day in by_date if day < target]
        if previous:
            selected.append(by_date[max(previous)])
    else:
        selected = [by_date[day] for day in sorted(by_date)[-max(1, int(max_bars)):]]
    selected.sort(key=lambda bar: bar['date'])
    return selected, invalid


def read_tdx_local_calendar(paths, target_date=None, max_bytes=131072, max_bars=500):
    """Union local TDX calendars that contain the requested trading date."""
    target = _day(target_date)
    calendars = []
    for path in paths:
        if not path or not os.path.isfile(path):
            continue
        bars, _ = read_tdx_tail_bars(path, None, max_bytes=max_bytes, max_bars=max_bars)
        dates = {bar['date'] for bar in bars}
        if not dates or (target and target not in dates):
            continue
        calendars.append(dates)
    if not calendars:
        return None
    return sorted(set().union(*calendars))

def daily_bar_to_line(bar):
    values = [bar.get(key) for key in ('open', 'high', 'low', 'close', 'volume', 'amount')]
    numbers = [_number(value) for value in values]
    normalized = {'date': _day(bar.get('date', bar.get('datetime')))}
    normalized.update(dict(zip(('open', 'high', 'low', 'close', 'volume', 'amount'), numbers)))
    if not validate_daily_bar(normalized):
        raise ValueError('invalid TDX daily bar')
    return normalized['date'] + ',' + ','.join(format(value, '.10g') for value in numbers) + '\n'


def daily_bar_to_snapshot(code, bar, previous_close=None, name=''):
    if not validate_daily_bar(bar):
        return None
    code = normalize_code(code)
    if not code:
        return None
    close = _number(bar.get('close'))
    previous = _number(previous_close)
    if previous is None or previous <= 0:
        previous = None
    high, low = _number(bar.get('high')), _number(bar.get('low'))
    return {
        'date': _day(bar.get('date', bar.get('datetime'))),
        'code': code,
        'name': str(name or ''),
        'new_price': close,
        'change_rate': (close - previous) / previous * 100.0 if previous else None,
        'ups_downs': close - previous if previous else None,
        'volume': _number(bar.get('volume')),
        'deal_amount': _number(bar.get('amount')),
        'amplitude': (high - low) / previous * 100.0 if previous else None,
        'open_price': _number(bar.get('open')),
        'high_price': high,
        'low_price': low,
        'pre_close_price': previous,
    }


def _default_hosts():
    host = os.environ.get('TDX_HQ_HOST', '').strip()
    if host:
        try:
            port = int(os.environ.get('TDX_HQ_PORT', '7709'))
        except ValueError:
            port = 7709
        hosts = [('configured', host, port)]
    else:
        hosts = []
    try:
        from pytdx.config.hosts import hq_hosts
        for item in hq_hosts:
            if len(item) >= 3:
                candidate = (str(item[0]), str(item[1]), int(item[2]))
                if candidate[1] and candidate[2] > 0 and candidate not in hosts:
                    hosts.append(candidate)
            if len(hosts) >= 9:
                break
    except ImportError as exc:
        if not hosts:
            raise TDXUnavailable('pytdx is not installed') from exc
    return hosts


class TDXHqClient:
    def __init__(self, api_factory=None, hosts=None, daily_api_url=None, urlopen=None):
        self._api_factory = api_factory
        self._hosts = hosts
        self._daily_api_url = (
            os.environ.get('INSTOCK_TDX_DAILY_API_URL', '').strip()
            if daily_api_url is None else str(daily_api_url).strip()
        )
        self._urlopen = urlopen
        self._api = None
        self._host_index = 0
        self._lock = threading.RLock()

    def _new_api(self):
        if self._api_factory is not None:
            return self._api_factory()
        try:
            from pytdx.hq import TdxHq_API
        except ImportError as exc:
            raise TDXUnavailable('pytdx is not installed in the InStock runtime') from exc
        return TdxHq_API(heartbeat=False, raise_exception=True)

    def _connect(self):
        if self._api is not None:
            return self._api
        hosts = self._hosts if self._hosts is not None else _default_hosts()
        if not hosts:
            raise TDXUnavailable('no TDX HQ hosts are configured')
        failures = []
        for offset in range(min(len(hosts), 8)):
            index = (self._host_index + offset) % len(hosts)
            name, host, port = hosts[index]
            api = self._new_api()
            try:
                if api.connect(host, int(port), time_out=2.0):
                    self._api = api
                    self._host_index = index
                    logger.info('TDX HQ connected: host=%s address=%s:%s', name, host, port)
                    return api
                failures.append('%s: no response' % name)
            except Exception as exc:
                failures.append('%s: %s' % (name, exc))
            try:
                api.disconnect()
            except Exception:
                pass
        self._host_index = (self._host_index + 1) % len(hosts)
        raise TDXUnavailable('TDX HQ connection failed: %s' % '; '.join(failures[:3]))

    def _disconnect(self):
        api, self._api = self._api, None
        if api is not None:
            try:
                api.disconnect()
            except Exception:
                logger.debug('TDX HQ disconnect failed', exc_info=True)

    def _advance_host(self):
        hosts = self._hosts if self._hosts is not None else _default_hosts()
        if hosts:
            self._host_index = (self._host_index + 1) % len(hosts)

    def close(self):
        with self._lock:
            self._disconnect()

    @staticmethod
    def _daily_api_limit(start_day, end_day):
        start = datetime.date.fromisoformat(start_day)
        end = datetime.date.fromisoformat(end_day)
        return min(8000, max(300, (end - start).days * 3 // 2 + 5))

    def _fetch_daily_bars_api(self, code, start_day, end_day):
        market = market_code(code)
        suffix = '.SH' if market == 1 else '.BJ' if market == 2 else '.SZ'
        query = urllib.parse.urlencode({
            'symbol': code + suffix,
            'period': 'day',
            'limit': self._daily_api_limit(start_day, end_day),
        })
        separator = '&' if '?' in self._daily_api_url else '?'
        request = urllib.request.Request(
            self._daily_api_url + separator + query,
            headers={'Accept': 'application/json'},
        )
        opener = self._urlopen or urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open
        try:
            with opener(request, timeout=20) as response:
                payload = json.loads(response.read(12 * 1024 * 1024).decode('utf-8'))
        except Exception as exc:
            raise TDXUnavailable('Go TDX daily API failed for %s: %s' % (code, exc)) from exc

        if payload.get('implementation') != 'go-native-tdx':
            raise TDXUnavailable('Go TDX daily API returned an unexpected implementation')
        raw_bars = payload.get('data')
        if not isinstance(raw_bars, list):
            raise TDXUnavailable('Go TDX daily API response has no data list')
        collected = {}
        for raw in raw_bars:
            if not isinstance(raw, dict):
                continue
            metadata = raw.get('meta')
            if not isinstance(metadata, dict) or metadata.get('source') != 'tdx':
                raise TDXUnavailable('Go TDX daily API returned a non-TDX bar')
            day = _day(raw.get('time', raw.get('date')))
            if not day or day < start_day or day > end_day:
                continue
            bar = {
                'date': day,
                'open': _number(raw.get('open')),
                'high': _number(raw.get('high')),
                'low': _number(raw.get('low')),
                'close': _number(raw.get('close')),
                'volume': _number(raw.get('volume')),
                'amount': _number(raw.get('amount')),
            }
            if validate_daily_bar(bar):
                collected[day] = bar
        return [collected[day] for day in sorted(collected)]

    def fetch_quotes(self, codes, batch_size=_BATCH_SIZE):
        normalized = list(dict.fromkeys(filter(None, (normalize_code(code) for code in codes))))
        result = {}
        failed = set()
        with self._lock:
            for offset in range(0, len(normalized), max(1, int(batch_size))):
                batch = normalized[offset:offset + max(1, int(batch_size))]
                hosts = self._hosts if self._hosts is not None else _default_hosts()
                attempts = min(max(len(hosts), 1), 3)
                batch_received = False
                for _ in range(attempts):
                    try:
                        api = self._connect()
                    except TDXUnavailable:
                        failed.update(batch)
                        break
                    try:
                        raw_quotes = api.get_security_quotes(
                            [(market_code(code), code) for code in batch]
                        ) or []
                    except Exception:
                        logger.warning('TDX quote batch failed: codes=%s', batch[:5], exc_info=True)
                        self._disconnect()
                        self._advance_host()
                        continue
                    requested = set(batch)
                    matched = {}
                    for quote in raw_quotes:
                        if not isinstance(quote, dict):
                            continue
                        code = normalize_code(quote.get('code'))
                        if code in requested:
                            matched[code] = quote
                    if matched:
                        result.update(matched)
                        batch_received = True
                        break
                    self._disconnect()
                    self._advance_host()
                if not batch_received:
                    failed.update(batch)
        return result, failed

    def fetch_daily_bars(self, code, start_date, end_date, max_pages=16):
        code = normalize_code(code)
        start_day, end_day = _day(start_date), _day(end_date)
        if not code or not start_day or not end_day or start_day > end_day:
            return []
        if self._daily_api_url:
            return self._fetch_daily_bars_api(code, start_day, end_day)
        with self._lock:
            hosts = self._hosts if self._hosts is not None else _default_hosts()
            attempts = min(max(len(hosts), 1), 3)
            last_error = None
            for _ in range(attempts):
                collected = {}
                offset = 0
                received_page = False
                retry_host = False
                for _ in range(max_pages):
                    api = self._connect()
                    try:
                        batch = api.get_security_bars(
                            _DAILY_CATEGORY, market_code(code), code, offset, 800
                        ) or []
                    except Exception as exc:
                        last_error = exc
                        logger.warning('TDX daily-bar request failed: code=%s offset=%s',
                                       code, offset, exc_info=True)
                        self._disconnect()
                        self._advance_host()
                        retry_host = True
                        break
                    if not batch:
                        if not received_page:
                            self._disconnect()
                            self._advance_host()
                            retry_host = True
                            break
                        return [collected[day] for day in sorted(collected)]
                    received_page = True
                    for raw in batch:
                        if not isinstance(raw, dict):
                            continue
                        day = _day(raw.get('datetime', raw.get('date')))
                        if not day or day < start_day or day > end_day:
                            continue
                        volume_lots = _number(raw.get('vol', raw.get('volume')))
                        amount = _number(raw.get('amount'))
                        bar = {
                            'date': day,
                            'open': _number(raw.get('open')),
                            'high': _number(raw.get('high')),
                            'low': _number(raw.get('low')),
                            'close': _number(raw.get('close')),
                            'volume': volume_lots * 100.0 if volume_lots is not None else None,
                            'amount': amount,
                        }
                        if validate_daily_bar(bar):
                            collected[day] = bar
                    dates = [_day(raw.get('datetime', raw.get('date')))
                             for raw in batch if isinstance(raw, dict)]
                    dates = [day for day in dates if day]
                    if not dates or min(dates) <= start_day or len(batch) < 800:
                        return [collected[day] for day in sorted(collected)]
                    offset += len(batch)
                if not retry_host:
                    return [collected[day] for day in sorted(collected)]
            if last_error is not None:
                raise TDXUnavailable('TDX daily-bar nodes failed: %s' % last_error) from last_error
        return []


_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def get_tdx_client():
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = TDXHqClient()
        return _CLIENT
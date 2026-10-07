"""Read daily TDX export files from the persistent forwardp directory."""

import os
import re

import pandas as pd
try:
    from instock.JSONData.history_cache import load_history
except ImportError:
    from JSONData.history_cache import load_history


import threading
from io import BytesIO

_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']
_FORWARD_DIR_CACHE = {}
_FORWARD_DIR_LOCK = threading.RLock()


def get_tdx_file_path(forward_dir, exchange, symbol):
    """Zero-IO directory hash index for TDX daily TXT files."""
    if not forward_dir or not os.path.isdir(forward_dir):
        return None
    try:
        dir_stat = os.stat(forward_dir)
        cache_key = (forward_dir, dir_stat.st_mtime_ns)
    except OSError:
        return None

    with _FORWARD_DIR_LOCK:
        index = _FORWARD_DIR_CACHE.get(cache_key)
        if index is None:
            index = {}
            try:
                for entry in os.scandir(forward_dir):
                    if not entry.is_file():
                        continue
                    name_upper = entry.name.upper()
                    if not name_upper.endswith('.TXT'):
                        continue
                    stem = name_upper[:-4]
                    index[stem] = entry.path
                    if stem.startswith(('BJ', 'SH', 'SZ')):
                        index[stem[2:]] = entry.path
                _FORWARD_DIR_CACHE.clear()
                _FORWARD_DIR_CACHE[cache_key] = index
            except OSError:
                return None

    # 优先匹配 exchange + symbol，其次匹配纯 symbol
    key = (exchange + symbol).upper()
    path = index.get(key)
    if path is None:
        path = index.get(symbol.upper())
    return path


def _read_tdx_csv(file_path, min_rows=600, start_date=None, encoding='gb18030'):
    """Accelerate HDD reads on large historical files by seeking near the tail."""
    file_size = 0
    try:
        file_size = os.path.getsize(file_path)
    except OSError:
        pass

    estimate_bytes = (min_rows + 100) * 100  # ~70 KB for 600 rows
    if file_size > estimate_bytes * 1.3:
        try:
            with open(file_path, 'rb') as fp:
                fp.seek(file_size - estimate_bytes)
                fp.readline()  # drop partial line
                tail_bytes = fp.read()
            frame = pd.read_csv(
                BytesIO(tail_bytes), header=None, names=_COLUMNS, usecols=range(7),
                dtype={'date': str}, encoding=encoding, on_bad_lines='skip',
            )
            if len(frame) >= min_rows:
                if start_date:
                    first_date = str(frame.iloc[0]['date']).strip()
                    if len(first_date) == 8 and first_date.isdigit():
                        first_date = f"{first_date[:4]}-{first_date[4:6]}-{first_date[6:8]}"
                    else:
                        first_date = first_date[:10]
                    if first_date <= str(start_date)[:10]:
                        return frame
                else:
                    return frame
        except Exception:
            pass

    return pd.read_csv(
        file_path, header=None, names=_COLUMNS, usecols=range(7),
        dtype={'date': str}, encoding=encoding, on_bad_lines='skip',
    )


def _day_string(value):
    if value is None:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    value = str(value).strip()
    if re.fullmatch(r'\d{8}', value):
        return '%s-%s-%s' % (value[:4], value[4:6], value[6:8])
    return value[:10]


def get_tdx_Exp_day_to_df(
    code, start=None, end=None, dl=None, newdays=None,
    type='f', wds=True, lastdays=3, resample='d',
    MultiIndex=False, lastday=None,
    detect_calc_support=True, normalized=False,
    fastohlc=False,
):
    """Return TDX daily bars with the desktop function's raw OHLCV columns."""
    digits = ''.join(re.findall(r'\d', str(code)))
    if len(digits) < 6:
        return pd.DataFrame()
    symbol = digits[-6:]
    if symbol.startswith(('4', '8', '92')):
        exchange = 'BJ'
    elif symbol.startswith(('5', '6', '9')):
        exchange = 'SH'
    else:
        exchange = 'SZ'

    forward_dir = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
    if type != 'f':
        forward_dir = os.path.join(os.path.dirname(forward_dir), 'backp')

    file_path = get_tdx_file_path(forward_dir, exchange, symbol)
    if file_path is None:
        # Fallback to direct candidate check if directory index was unavailable
        candidates = [os.path.join(forward_dir, exchange + symbol + suffix) for suffix in ('.TXT', '.txt')]
        candidates.extend(os.path.join(forward_dir, symbol + suffix) for suffix in ('.TXT', '.txt'))
        file_path = next((path for path in candidates if os.path.isfile(path)), None)
    if file_path is None:
        return pd.DataFrame()

    min_needed = max(int(dl or 600), 600)
    start_day = _day_string(start)

    def read_normalized():
        frame = _read_tdx_csv(file_path, min_rows=min_needed, start_date=start_day)
        frame['date'] = pd.to_datetime(frame['date'].str.strip(), errors='coerce')
        for column in _COLUMNS[1:]:
            frame[column] = pd.to_numeric(frame[column], errors='coerce')
        frame = frame.dropna(subset=_COLUMNS).drop_duplicates('date', keep='last')
        return frame.loc[(frame['open'] > 0) & (frame['close'] > 0)]

    try:
        frame = load_history(file_path, read_normalized, cache_variant=(min_needed, start_day))
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()

    end_day = _day_string(end)
    if start_day:
        frame = frame.loc[frame['date'] >= pd.Timestamp(start_day)]
    if end_day:
        frame = frame.loc[frame['date'] <= pd.Timestamp(end_day)]
    if lastday:
        frame = frame.iloc[:-int(lastday)]
    if dl is not None:
        limit = int(dl)
        if limit <= 0:
            return pd.DataFrame()
        frame = frame.iloc[-limit:]
    if frame.empty:
        return pd.DataFrame()

    frame['date'] = frame['date'].dt.strftime('%Y-%m-%d')
    frame['code'] = symbol
    frame = frame.set_index('date').sort_index()
    return frame[['code', 'open', 'high', 'low', 'close', 'vol', 'amount']]

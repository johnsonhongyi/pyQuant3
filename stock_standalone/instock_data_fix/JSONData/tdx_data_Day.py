"""Read daily TDX export files from the persistent forwardp directory."""

import os
import re

import pandas as pd


_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']


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
    candidates = [os.path.join(forward_dir, exchange + symbol + suffix) for suffix in ('.TXT', '.txt')]
    candidates.extend(os.path.join(forward_dir, symbol + suffix) for suffix in ('.TXT', '.txt'))
    file_path = next((path for path in candidates if os.path.isfile(path)), None)
    if file_path is None:
        return pd.DataFrame()

    try:
        frame = pd.read_csv(
            file_path, header=None, names=_COLUMNS, usecols=range(7),
            dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
        )
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()

    frame['date'] = pd.to_datetime(frame['date'].str.strip(), errors='coerce')
    for column in _COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=_COLUMNS).drop_duplicates('date', keep='last')
    frame = frame.loc[(frame['open'] > 0) & (frame['close'] > 0)]

    start_day, end_day = _day_string(start), _day_string(end)
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

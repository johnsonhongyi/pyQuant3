"""Small, portable Sina quote client compatible with Sina().market('all')."""

import glob
import os
import re
import time

import pandas as pd
import requests


_API = 'https://hq.sinajs.cn/list='
_CODE_RE = re.compile(r'hq_str_(sh|sz|bj)(\d{6})="([^"]*)"')
_A_PREFIXES = ('600', '601', '603', '605', '688', '689', '000', '001', '002', '003', '300', '301', '43', '83', '87', '92')
_HEADERS = {
    'Referer': 'https://finance.sina.com.cn/',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
}


def _symbol(code):
    if code.startswith(('4', '8', '92')):
        return 'bj' + code
    if code.startswith(('5', '6', '9')):
        return 'sh' + code
    return 'sz' + code


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _stock_codes():
    directory = os.environ.get('TDX_FORWARDP_DIR', '/data/InStock/instock/forwardp')
    found = set()
    for path in glob.glob(os.path.join(directory, '*')):
        match = re.search(r'([0-9]{6})\.txt$', path, re.IGNORECASE)
        if match and match.group(1).startswith(_A_PREFIXES):
            found.add(match.group(1))
    if not found:
        raise RuntimeError('No TDX stock files found in %s' % directory)
    return sorted(found)


def _parse_quote(code, values):
    fields = values.split(',')
    if len(fields) < 10:
        return None
    quote = {
        'code': code,
        'name': fields[0].strip(),
        'open': _number(fields[1]),
        'close': _number(fields[2]),
        'now': _number(fields[3]),
        'high': _number(fields[4]),
        'low': _number(fields[5]),
        'volume': _number(fields[8]),
        'turnover': _number(fields[9]),
        'dt': fields[30].strip() if len(fields) > 30 else '',
        'ticktime': fields[31].strip() if len(fields) > 31 else '',
    }
    return quote if quote['now'] > 0 else None


class Sina:
    """Fetch all supported A-share snapshots represented by TDX history files."""

    def market(self, market):
        if market != 'all':
            raise ValueError('Only the all-market snapshot is supported')
        codes = _stock_codes()
        quotes = self.market_codes(codes)
        minimum = max(500, int(len(codes) * 0.5))
        if len(quotes) < minimum:
            raise RuntimeError('Sina quote coverage too low: %s/%s' % (len(quotes), len(codes)))
        return quotes

    def market_codes(self, codes):
        """Fetch one Sina snapshot for an explicit stock or ETF code universe."""
        normalized = []
        for value in codes:
            digits = re.sub(r'\D', '', str(value))
            if len(digits) <= 6 and digits:
                normalized.append(digits.zfill(6))
        codes = sorted(set(normalized))
        if not codes:
            return pd.DataFrame(columns=['code', 'name', 'open', 'close', 'now', 'high', 'low',
                                         'volume', 'turnover', 'dt', 'ticktime'])
        quotes = []
        session = requests.Session()
        try:
            for offset in range(0, len(codes), 850):
                batch = codes[offset:offset + 850]
                response = None
                for attempt in range(3):
                    try:
                        response = session.get(_API + ','.join(_symbol(code) for code in batch),
                                               headers=_HEADERS, timeout=(5, 25))
                        response.raise_for_status()
                        response.encoding = 'gbk'
                        break
                    except requests.RequestException:
                        if attempt == 2:
                            raise
                        time.sleep(attempt + 1)
                parsed = {
                    code: _parse_quote(code, values)
                    for exchange, code, values in _CODE_RE.findall(response.text)
                }
                quotes.extend(row for row in parsed.values() if row is not None)
                if not parsed:
                    raise RuntimeError('Sina returned no quotes for batch starting at %s' % batch[0])
        finally:
            session.close()
        return pd.DataFrame(quotes)

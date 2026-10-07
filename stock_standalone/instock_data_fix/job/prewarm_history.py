"""Trading-day premarket baseline initialization; no strategies/table writes."""
import datetime
import json
import os
import sys
import time

root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, root)
import instock.lib.trade_time as trd

today = datetime.date.today()
if not trd.is_trade_date(today):
    sys.exit(0)
directory = os.environ.get('INSTOCK_STRATEGY_PREPARED_DIR', os.path.join(root, 'instock', 'cache', 'hist'))
os.environ.update(INSTOCK_PREPARED_HISTORY_CACHE_DIR=directory, INSTOCK_COLUMNAR_HISTORY_CACHE='1',
                  INSTOCK_HISTORY_CACHE_EPOCH=str(today), INSTOCK_HISTORY_CACHE_MB='0')
from instock.core.singleton_stock import stock_data
import instock.core.tablestructure as tbs
import instock.core.stockfetch as stf
from JSONData.prepared_history import prepared_history
from JSONData.history_cache import cache_statistics
from pathlib import Path

date = trd.get_trade_date_last()[0]
quotes = stock_data(date).get_data(date)
if quotes is None or quotes.empty:
    raise RuntimeError('Premarket history initialization: no stock list')
stocks = [tuple(row) for row in quotes[list(tbs.TABLE_CN_STOCK_FOREIGN_KEY['columns'])].values]
start_date, cached = trd.get_trade_hist_interval(str(date))
os.environ['INSTOCK_HIST_LOOKBACK_ROWS'] = '600'


def warm_stock(stock, date, start_date, cached, directory):
    symbol = str(stock[1]).split('.')[0].zfill(6)
    os.environ['INSTOCK_HIST_LOOKBACK_ROWS'] = '600'
    frame = stf.fetch_stock_hist(stock, start_date, cached)
    if frame is None or frame.empty:
        return False
    _, source, fingerprint = stf._tdx_history_source(stock[1])
    if source and fingerprint:
        columns = list(tbs.CN_STOCK_HIST_DATA['columns'])
        signature = (str(start_date or ''), str(date), 'qfq', tuple(columns), source, fingerprint)
        prepared_history(os.path.join(directory, symbol + '-qfq.pkl'), signature,
                         lambda: frame[columns])

    return True


started = time.perf_counter()
loaded = sum(warm_stock(stock, date, start_date, cached, directory) for stock in stocks)
if loaded < max(1, int(len(stocks) * .7)):
    raise RuntimeError('Premarket history coverage insufficient: %s/%s' % (loaded, len(stocks)))

from JSONData.prepared_history import save_manifest
manifest_file = save_manifest(directory)

print(json.dumps(dict(epoch=str(today), stocks=len(stocks), seconds=round(time.perf_counter() - started, 3),
                      manifest=bool(manifest_file), cache=cache_statistics())))

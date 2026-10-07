"""Trading-day premarket baseline initialization; no strategies/table writes."""
import concurrent.futures
import datetime
import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(filename)s(%(lineno)d): %(message)s'
)

root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, root)
import instock.lib.trade_time as trd

today = datetime.date.today()
if not trd.is_trade_date(today):
    logging.info("Today %s is not a trade date; skipping premarket history prewarm", today)
    sys.exit(0)

directory = os.environ.get('INSTOCK_STRATEGY_PREPARED_DIR', os.path.join(root, 'instock', 'cache', 'hist'))
os.environ.update(INSTOCK_PREPARED_HISTORY_CACHE_DIR=directory, INSTOCK_COLUMNAR_HISTORY_CACHE='1',
                  INSTOCK_HISTORY_CACHE_EPOCH=str(today), INSTOCK_HISTORY_CACHE_MB='0')
from instock.core.singleton_stock import stock_data
import instock.core.tablestructure as tbs
import instock.core.stockfetch as stf
try:
    from instock.JSONData.prepared_history import prepared_history
    from instock.JSONData.history_cache import cache_statistics
except ImportError:
    from JSONData.prepared_history import prepared_history
    from JSONData.history_cache import cache_statistics
from pathlib import Path

try:
    from instock.job.prewarm_tuner import auto_tune_prewarm_config, record_prewarm_metrics
except ImportError:
    try:
        from job.prewarm_tuner import auto_tune_prewarm_config, record_prewarm_metrics
    except ImportError:
        auto_tune_prewarm_config = None
        record_prewarm_metrics = None

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


# 1. 自适应调优分析与决策
cpu_total = os.cpu_count() or 4
if auto_tune_prewarm_config:
    tuning = auto_tune_prewarm_config(cpu_total=cpu_total)
    workers = tuning.get('workers', max(1, min(3, cpu_total - 1)))
    logging.info("Auto-tuner activated: workers=%s (max_safe=%s), strategy=%s, reason: %s",
                 workers, tuning.get('max_safe_workers'), tuning.get('strategy'), tuning.get('recommendation'))
else:
    workers = max(1, min(3, cpu_total - 1))
    tuning = {'strategy': 'fallback_default'}

logging.info("Premarket history initialization started: epoch=%s stocks=%d workers=%d base_rows=600",
             today, len(stocks), workers)

started = time.perf_counter()
loaded = 0
completed = 0

# 2. 受限并发执行预热
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
    for success in pool.map(lambda s: warm_stock(s, date, start_date, cached, directory), stocks):
        completed += 1
        if success:
            loaded += 1
        if completed % 1000 == 0 or completed == len(stocks):
            elapsed_now = time.perf_counter() - started
            logging.info("Premarket warm progress: %d/%d (%.1f%%) loaded=%d elapsed=%.1fs (%.1f stocks/s)",
                         completed, len(stocks), completed / len(stocks) * 100, loaded,
                         elapsed_now, completed / max(elapsed_now, 0.001))

if loaded < max(1, int(len(stocks) * .7)):
    raise RuntimeError('Premarket history coverage insufficient: %s/%s' % (loaded, len(stocks)))

try:
    from instock.JSONData.prepared_history import save_manifest
except ImportError:
    from JSONData.prepared_history import save_manifest
manifest_file = save_manifest(directory)

total_elapsed = round(time.perf_counter() - started, 3)
throughput = round(len(stocks) / max(total_elapsed, 0.001), 1)

summary = dict(
    epoch=str(today),
    stocks=len(stocks),
    loaded=loaded,
    seconds=total_elapsed,
    workers=workers,
    throughput=throughput,
    tuning_strategy=tuning.get('strategy'),
    manifest=bool(manifest_file),
    cache=cache_statistics()
)

logging.info("Premarket history initialization complete: total=%d loaded=%d seconds=%.1fs (%.1f stocks/s) manifest=%s",
             len(stocks), loaded, total_elapsed, throughput, bool(manifest_file))

# 3. 持久化记录到指标历史账本
if record_prewarm_metrics:
    record_prewarm_metrics(summary)

print(json.dumps(summary, ensure_ascii=False))

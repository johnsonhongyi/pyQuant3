"""Scan bounded history batches; publish only after coverage validation."""
from itertools import islice
import hashlib
import json
import time


def history_rows(strategy_name, default=150):
    return {'cn_stock_strategy_backtrace_ma250': 310,
            'cn_stock_strategy_low_atr': 260,
            'cn_stock_strategy_breakthrough_platform': 210,
            'cn_stock_strategy_keep_increasing': 1000}.get(strategy_name, default)


def scan_batches(stocks, strategies, load_batch, check, publish, date, stats, batch_size=64):
    results = {item['name']: [] for item in strategies}
    counters = {item['name']: dict(checked=0, matched=0, errors=0, seconds=0.) for item in strategies}
    requested, loaded, load_seconds = 0, 0, 0.
    iterator = iter(stocks)
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            break
        requested += len(batch)
        started = time.perf_counter()
        frames = load_batch(batch)
        load_seconds += time.perf_counter() - started
        loaded += len(frames)
        if frames:
            for strategy in strategies:
                matches, metrics = check(strategy, frames)
                results[strategy['name']].extend(matches)
                for key in counters[strategy['name']]:
                    counters[strategy['name']][key] += metrics.get(key, 0)
        frames.clear()
        # Progress must be visible even during a long full-market scan.
        stats.progress(date=str(date), requested=requested, loaded=loaded,
                       load_seconds=round(load_seconds, 3), scans=counters, batch_size=batch_size)
    if loaded < max(1, int(requested * .7)):
        raise RuntimeError('History coverage insufficient: %s/%s; results preserved' % (loaded, requested))
    for strategy in strategies:
        metric = counters[strategy['name']]
        if metric['errors'] > max(5, int(metric['checked'] * .01)):
            raise RuntimeError('Too many stock errors: %s; results preserved' % strategy['name'])
    stats.stages.append(dict(name='snapshot', seconds=round(load_seconds, 3),
                             date=str(date), stocks=loaded, requested=requested))
    for strategy in strategies:
        started = time.perf_counter()
        publish(date, strategy, results[strategy['name']])
        metric = counters[strategy['name']]
        metric['result_sha256'] = hashlib.sha256(json.dumps(
            sorted(results[strategy['name']], key=str), default=str,
            sort_keys=True).encode('utf-8')).hexdigest()
        stats.stages.append(dict(name=strategy['name'], seconds=round(metric['seconds'] +
            time.perf_counter() - started, 3), date=str(date), stocks=loaded, scan=metric))
    return loaded

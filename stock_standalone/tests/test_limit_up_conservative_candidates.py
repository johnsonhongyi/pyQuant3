import random

import pandas as pd

from ats.limit_up_engine import (_conservative_limit_candidates,
    calc_theoretical_limit_up_price, get_limit_up_ratio_threshold)


def test_prefilter_preserves_limit_broken_and_auction_candidates():
    frame = pd.DataFrame([
        {'trade': 10.5, 'last_close': 10., 'high': 10.5, 'percent': 5.},
        {'trade': 10.3, 'last_close': 10., 'high': 11., 'percent': 3.},
        {'trade': 0., 'last_close': 10., 'high': 0., 'percent': 0., 'buy': 11.},
        {'trade': 10.1, 'last_close': 10., 'high': 10.2, 'percent': 1.},
    ])
    assert list(_conservative_limit_candidates(frame).index) == [0, 1, 2]


def test_prefilter_does_not_drop_scalar_candidates():
    rng = random.Random(7)
    rows = []
    for _ in range(10000):
        last = rng.uniform(.11, 1000)
        rows.append({'trade': rng.uniform(0, last * 1.4), 'last_close': last,
                     'high': rng.uniform(0, last * 1.4), 'percent': rng.uniform(-20, 35)})
    frame = pd.DataFrame(rows)
    kept = set(_conservative_limit_candidates(frame).index)
    for index, row in frame.iterrows():
        for code, name in [('600000', '*ST'), ('600000', ''), ('300001', ''), ('830001', '')]:
            threshold = get_limit_up_ratio_threshold(code, name)
            limit = calc_theoretical_limit_up_price(code, row.last_close, name)
            at_limit = row.trade >= limit - .01 or row.percent >= threshold
            broken = row.high >= limit - .01 and not at_limit and row.percent < threshold - .5
            if at_limit or broken or row.percent >= 7:
                assert index in kept


def test_prefilter_keeps_ambiguous_schema():
    frame = pd.DataFrame({'trade': ['10.0'], 'last_close': [10.], 'high': [10.], 'percent': [1.]})
    assert _conservative_limit_candidates(frame) is frame


def test_prefilter_keeps_nonfinite_percent_for_scalar_fallback():
    frame = pd.DataFrame([{'trade': 104.9, 'last_close': 100., 'high': 104.9, 'percent': float('-inf')}])
    assert len(_conservative_limit_candidates(frame)) == 1


def test_full_engine_candidates_match_unfiltered(monkeypatch):
    import ats.limit_up_engine as module
    rng = random.Random(11)
    rows = []
    for i in range(250):
        last = rng.uniform(5., 100.)
        rows.append({'code': str(600000 + i), 'name': '*ST' if i % 7 == 0 else 'A',
                     'trade': last * rng.uniform(.9, 1.15), 'last_close': last,
                     'high': last * rng.uniform(.95, 1.15), 'percent': rng.uniform(-5., 12.)})
    rows.extend([
        {'code': '600901', 'name': '*ST', 'trade': 10.5, 'last_close': 10., 'high': 10.5, 'percent': 5.},
        {'code': '600902', 'name': 'A', 'trade': 10.3, 'last_close': 10., 'high': 11., 'percent': 3.},
        {'code': '600903', 'name': 'A', 'trade': 0., 'last_close': 10., 'high': 0., 'percent': 0., 'buy': 11.},
    ])
    frame = pd.DataFrame(rows)
    engine = module.LimitUpEngine.get_instance()
    optimized = engine.scan_limit_up_records_from_df(frame, fetch_l2_quotes=False)
    monkeypatch.setattr(module, '_conservative_limit_candidates', lambda data: data)
    reference = engine.scan_limit_up_records_from_df(frame, fetch_l2_quotes=False)
    fields = ('code', 'name', 'pct', 'is_limit_up', 'is_broken', 'consecutive_boards')
    assert [tuple(row.get(key) for key in fields) for row in optimized] == [
        tuple(row.get(key) for key in fields) for row in reference]


def test_low_precision_and_nullable_price_boundaries_are_conservative():
    import numpy as np
    values = [0.1, 1., 9.99, 100., 10000., 999999.]
    rows = []
    for last in values:
        previous = np.float32(last)
        limit = calc_theoretical_limit_up_price('600000', float(previous), '*ST')
        price = np.nextafter(np.float32(limit - .01), np.float32(np.inf))
        rows.append({'trade': price, 'last_close': previous, 'high': price, 'percent': np.float32(1.)})
    frame = pd.DataFrame(rows, dtype='float32')
    assert len(_conservative_limit_candidates(frame)) == len(frame)
    nullable = pd.DataFrame({'trade': pd.Series([10., pd.NA], dtype='Float32'),
        'last_close': pd.Series([10., 10.], dtype='Float32'),
        'high': pd.Series([10., 10.], dtype='Float32'),
        'percent': pd.Series([1., 1.], dtype='Float32')})
    assert list(_conservative_limit_candidates(nullable).index) == [1]


def test_cent_prices_and_threshold_edges_have_no_candidate_loss():
    import numpy as np
    rows = []
    expected = []
    for cents in range(11, 10001):
        previous = cents / 100.
        limit = calc_theoretical_limit_up_price('600000', previous, '*ST')
        for delta in (-1e-8, 0., 1e-8):
            for pct in (0., 1., 4.84, 4.85, 7., float('-inf')):
                trade = limit - .01 + delta
                for high in (trade, limit - .01):
                    rows.append((trade, previous, high, pct))
                    effective = pct if np.isfinite(pct) else 0.
                    if effective == 0. and trade > 0:
                        effective = round((trade - previous) / previous * 100., 2)
                    at_limit = effective >= 4.85 or (limit > 0 and trade > 0 and trade >= limit - .01)
                    broken = limit > 0 and high > 0 and high >= limit - .01 and not at_limit and effective < 4.35
                    expected.append(at_limit or broken or effective >= 7.)
    frame = pd.DataFrame(rows, columns=['trade', 'last_close', 'high', 'percent'])
    kept = np.zeros(len(frame), dtype=bool)
    kept[_conservative_limit_candidates(frame).index.to_numpy()] = True
    assert not np.any(np.asarray(expected) & ~kept)

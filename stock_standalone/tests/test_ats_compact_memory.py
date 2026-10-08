"""Focused lossless-memory and lazy cache regression checks."""
import pickle
import sys
import zlib

import pandas as pd

from ats.compact_cache import CompactBarRecords, read_cache_payload, write_cache_payload


def test_columnar_rows_are_lossless_and_legacy_pickle_compatible(tmp_path):
    rows = [dict(date='2026-09-30', time_only=f'{9+i//60:02}:{i%60:02}',
                 close=12.3456789012345, bar_vol=2**53 + i, active=True)
            for i in range(240)]
    rows[3]['optional'] = None
    compact = CompactBarRecords(rows)
    assert list(compact) == rows
    assert compact[-1] == rows[-1]
    assert compact[2:5] == rows[2:5]
    compact[0]['close'] = 0
    assert compact[0]['close'] == rows[0]['close']
    pd.testing.assert_frame_equal(pd.DataFrame(compact), pd.DataFrame(rows))
    restored = pickle.loads(pickle.dumps(compact))
    assert type(restored) is list and restored == rows
    assert compact.nbytes < sum(sys.getsizeof(row) for row in rows) / 3
    path = tmp_path / 'cache.z'
    with path.open('wb') as destination:
        write_cache_payload({'history': compact}, destination)
    assert read_cache_payload(path) == {'history': rows}
    assert pickle.loads(zlib.decompress(path.read_bytes())) == {'history': rows}
    with path.open('wb') as destination:
        write_cache_payload({'frame': pd.DataFrame(rows)}, destination)
    pd.testing.assert_frame_equal(read_cache_payload(path)['frame'], pd.DataFrame(rows))
    path.write_bytes(path.read_bytes()[:-2])
    import pytest
    with pytest.raises((EOFError, zlib.error)):
        read_cache_payload(path)


def test_default_singleton_never_decodes_unrequested_history(monkeypatch, tmp_path):
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    monkeypatch.setattr(TDXGlobalCachePool, '_instance', None)
    monkeypatch.setattr(TDXGlobalCachePool, '_get_ramdisk_cache_path',
                        lambda self: str(tmp_path / 'shared.z'))
    calls = []
    monkeypatch.setattr(TDXGlobalCachePool, '_load_from_ramdisk',
                        lambda self, **kwargs: calls.append(kwargs) or True)
    pool = TDXGlobalCachePool.get_instance()
    pool._maybe_sync_from_ramdisk(force=True)
    assert calls == []
    pool._ensure_startup_code_loaded('600108')
    assert calls[-1]['codes'] == {'600108'}
    assert pool._startup_loaded_codes == {'600108'}


def test_legacy_reader_accepts_new_rows_without_ats_module(tmp_path):
    import subprocess
    rows = [{}, {'value': None}, {'value': 2**80, 'extra': '保留'},
            {'value': -0.0}, {'value': float('inf')}, {'value': float('nan')}]
    compact = CompactBarRecords(rows)
    restored = list(compact)
    assert [set(row) for row in restored] == [set(row) for row in rows]
    assert restored[2] == rows[2]
    import math
    assert math.copysign(1, restored[3]['value']) == -1
    assert math.isinf(restored[4]['value']) and math.isnan(restored[5]['value'])
    path = tmp_path / 'legacy.z'
    with path.open('wb') as destination:
        write_cache_payload({'records': compact}, destination)
    result = subprocess.run([sys.executable, '-I', '-c',
        "import pickle,zlib,sys; d=pickle.loads(zlib.decompress(open(sys.argv[1],'rb').read())); "
        "assert type(d['records']) is list; assert d['records'][2]['value']==2**80; "
        "assert not any(m=='ats' or m.startswith('ats.') for m in sys.modules)", str(path)],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_direct_frame_preserves_types_missing_values_and_write_isolation(monkeypatch):
    import numpy as np
    cases = [[], [{}, {}], [{}, {'optional': None}],
             [{'value': None}, {}, {'value': 2**80}],
             [{'value': 2**63 + 1}, {'value': 2**63 + 2}],
             [{'value': -0.0}, {'value': float('inf')}, {'value': float('nan')}],
             [{'flag': True, 'mixed': '保留'}, {'flag': False, 'mixed': 3}],
             [{'date': '2026-09-30', 'close': 12.3456789012345, 'vol': 2**53 + i}
              for i in range(3)]]
    for rows in cases:
        compact = CompactBarRecords(rows)
        frame = compact.to_frame()
        pd.testing.assert_frame_equal(frame, pd.DataFrame(rows))
        mask = np.arange(len(rows)) % 2 == 0
        tail = [{'value': -1, 'new_field': None}]
        expected = [row for row, keep in zip(rows, mask) if keep] + tail
        pd.testing.assert_frame_equal(compact.to_frame(tail, mask), pd.DataFrame(expected))
        pd.testing.assert_frame_equal(
            compact.to_frame(tail, np.zeros(len(rows), dtype=bool)), pd.DataFrame(tail))
        if rows:
            tail = [dict(rows[-1])]
            pd.testing.assert_frame_equal(compact.to_frame(tail), pd.DataFrame(rows + tail))
    compact = CompactBarRecords(cases[-1])
    monkeypatch.setattr(CompactBarRecords, '__getitem__',
                        lambda *args: (_ for _ in ()).throw(AssertionError('row expansion')))
    frame = compact.to_frame()
    frame.loc[0, 'close'] = 0.0
    frame.loc[0, 'date'] = 'changed'
    fresh = compact.to_frame()
    assert fresh.loc[0, 'close'] == cases[-1][0]['close']
    assert fresh.loc[0, 'date'] == cases[-1][0]['date']
    tail = [dict(cases[-1][0])]
    pd.testing.assert_frame_equal(
        compact.to_frame(tail, np.ones(3, dtype=bool)), pd.DataFrame(cases[-1] + tail))

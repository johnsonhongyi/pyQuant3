"""Verify instock.JSONData internal layout and backward compatibility."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'instock_data_fix'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_instock_jsondata_import():
    import instock.JSONData as jsondata
    assert hasattr(jsondata, 'history_cache')
    assert hasattr(jsondata, 'prepared_history')
    assert hasattr(jsondata, 'sina_data')
    assert hasattr(jsondata, 'tdx_data_Day')


def test_jsondata_backward_compatibility_alias():
    import instock.JSONData
    import JSONData
    assert JSONData is sys.modules['JSONData']
    assert hasattr(JSONData, 'history_cache')


def test_internal_cross_imports():
    from instock.JSONData.tdx_data_Day import load_history
    from instock.JSONData.prepared_history import UNIFIED_BASE_ROWS
    assert UNIFIED_BASE_ROWS == 600
    assert callable(load_history)


def test_consumer_modules_import():
    from instock.job.run_statistics import _get_cache_statistics
    stats = _get_cache_statistics()
    assert isinstance(stats, dict)

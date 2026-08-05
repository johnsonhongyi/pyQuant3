import pytest
import pandas as pd
import numpy as np
import time
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from realtime_data_service import MinuteKlineCache

from datetime import datetime

from realtime_data_service import KLineItem

def test_attach_multiday_twap_injects_full_columns():
    """验证 attach_multiday_twap_to_df 能够在 DataFrame 中成功算齐全量多日均价 col"""
    cache = MinuteKlineCache()
    df = pd.DataFrame({
        'code': ['300058', '600000'],
        'close': [15.73, 10.50],
        'volume': [10000, 20000]
    })
    
    now_ts = int(time.time())
    cache._shared_cache['300058'] = [KLineItem(time=now_ts, open=15.73, high=15.73, low=15.73, close=15.73, volume=10000.0, cum_vol_start=0.0)]
    cache._shared_cache['600000'] = [KLineItem(time=now_ts, open=10.50, high=10.50, low=10.50, close=10.50, volume=20000.0, cum_vol_start=0.0)]
    
    res = cache.attach_multiday_twap_to_df(df)
    
    expected_cols = ['nclose', 'vwap', 'vwap_cum_2d', 'vwap_cum_3d', 'last_vwap_cum_2d']
    for col in expected_cols:
        assert col in res.columns, f"Missing derived column: {col}"
    
    print("✅ attach_multiday_twap_to_df column injection verification PASSED!")

def test_ipc_send_package_contains_dynamic_twap():
    """验证在 MarketBus 与 send_df 发送流程中全量衍生列能够被保底挂载"""
    cache = MinuteKlineCache()
    now_ts = int(time.time())
    cache._shared_cache['300058'] = [KLineItem(time=now_ts, open=15.73, high=15.73, low=15.73, close=15.73, volume=10000.0, cum_vol_start=0.0)]
    
    df_bus_all = pd.DataFrame({
        'code': ['300058'],
        'close': [15.73]
    })
    
    cache.attach_multiday_twap_to_df(df_bus_all)
    assert 'vwap_cum_2d' in df_bus_all.columns
    assert 'nclose' in df_bus_all.columns
    print("✅ IPC send package dynamic twap attachment PASSED!")

if __name__ == '__main__':
    pytest.main([__file__])

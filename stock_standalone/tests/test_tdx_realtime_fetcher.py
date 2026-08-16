# -*- coding: utf-8 -*-
"""
tests/test_tdx_realtime_fetcher.py — 通达信独立行情引擎单元测试
"""

import pytest
import os
import sys
import pandas as pd

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import (
    extract_hosts_from_tdx_cfg,
    get_all_tdx_hosts,
    get_market_code,
    TDXRealtimeFetcher,
    FALLBACK_TDX_HOSTS
)


def test_get_market_code():
    assert get_market_code("600519") == 1
    assert get_market_code("688826") == 1
    assert get_market_code("688981") == 1
    assert get_market_code("000001") == 0
    assert get_market_code("300750") == 0
    assert get_market_code("301001") == 0


def test_extract_hosts_and_fallback():
    hosts = get_all_tdx_hosts()
    assert len(hosts) > 0
    # 确保包含了常见的 IP 格式
    for name, ip, port in hosts[:5]:
        assert isinstance(name, str)
        assert len(ip.split(".")) == 4
        assert isinstance(port, int)


def test_tdx_realtime_fetcher_quotes_and_convert_df():
    fetcher = TDXRealtimeFetcher.get_instance()
    # 确保能连接或在离线时安全处理
    if fetcher.connect():
        quotes = fetcher.get_security_quotes_safe(["600519", "000001"])
        assert isinstance(quotes, list)
        if quotes:
            df = fetcher.convert_quotes_to_df(quotes)
            assert isinstance(df, pd.DataFrame)
            assert "trade" in df.columns
            assert "open" in df.columns
            assert "buy" in df.columns
            assert "amount" in df.columns

            snap = fetcher.fetch_stock_snapshot("600519")
            assert isinstance(snap, dict)
            assert snap.get("code") == "600519"
            assert snap.get("price") > 0
            assert "vwap" in snap
            assert "turnover_rate" in snap
    else:
        # 离线兜底测试 convert_quotes_to_df
        mock_quotes = [{
            "code": "688826", "price": 565.0, "open": 560.0, "high": 580.0, "low": 555.0,
            "last_close": 186.88, "vol": 10000, "amount": 56500000.0, "bid1": 564.5, "ask1": 565.5
        }]
        df = fetcher.convert_quotes_to_df(mock_quotes)
        assert len(df) == 1
        assert df.iloc[0]["trade"] == 565.0
        assert df.iloc[0]["code"] == "688826"

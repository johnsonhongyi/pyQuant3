# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher, FALLBACK_TDX_HOSTS

def test_tdx_hosts_clean():
    for name, ip, port in FALLBACK_TDX_HOSTS:
        assert ip != '111.15.15.43'

def test_tdx_connect_probe():
    fetcher = TDXRealtimeFetcher.get_instance()
    ok = fetcher.connect(probe=True)
    assert ok is True
    assert fetcher.current_host is not None
    assert fetcher.current_host[1] != '111.15.15.43'

def test_tdx_available_servers():
    fetcher = TDXRealtimeFetcher.get_instance()
    servers = fetcher.get_available_servers()
    assert len(servers) > 0
    assert any('117.34.114.' in s['ip'] or '223.112.100.' in s['ip'] for s in servers)

def test_tdx_auto_failover():
    fetcher = TDXRealtimeFetcher.get_instance()
    ok = fetcher.auto_failover()
    assert ok is True
    assert fetcher.current_host is not None

def test_tdx_realtime_quotes_with_bj():
    fetcher = TDXRealtimeFetcher.get_instance()
    codes = ['000001', '600519', '920045']
    quotes = fetcher.get_security_quotes_safe(codes, force=True)
    assert len(quotes) == len(codes)
    for q in quotes:
        assert float(q.get('price', 0.0)) > 0

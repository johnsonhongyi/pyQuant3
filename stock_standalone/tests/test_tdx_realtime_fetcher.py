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
            assert snap.get("price", 0.0) > 0 or snap.get("last_close", 0.0) > 0
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


# ─────────────────────────────────────────────────────────────────────────────
# 【自动数据修复】单元测试 — 纯内存，无需网络连接
# ─────────────────────────────────────────────────────────────────────────────

import threading
import time as _time
from ats.tdx_realtime_fetcher import TDXGlobalCachePool


def _make_pool_isolated(tmp_path: str = "") -> TDXGlobalCachePool:
    """创建一个独立（非单例）的 CachePool 实例，指向临时路径"""
    pool = TDXGlobalCachePool.__new__(TDXGlobalCachePool)
    pool._mutex = threading.RLock()
    pool._current_date_str = "2026-09-18"
    pool._history_static_bars = {}
    pool._multi_day_df_cache = {}
    pool._incremental_intraday_pool = {}
    pool._daily_metrics_cache = {}
    pool._quotes_cache = {}
    pool._kline_cache = {}
    pool._shares_cache = {}
    pool.stats = {"total_queries": 0, "cache_hits": 0, "network_calls": 0, "saved_network_calls": 0}
    pool._ramdisk_path = tmp_path
    pool._last_ramdisk_mtime = 0.0
    pool._last_mtime_check_ts = 0.0
    pool._last_flush_ts = 0.0
    pool._is_dirty = False
    return pool


def _make_record(t="09:31", price=10.0, bar_vol=1000.0, bar_amt=10000.0, cum_vol=1000.0, cum_amt=10000.0):
    return {
        "date": "2026-09-18", "time_only": t, "time": f"09-18 {t}",
        "close": price, "price": price, "open": price, "high": price, "low": price,
        "bar_vol": bar_vol, "bar_amt": bar_amt,
        "cum_vol_shares": cum_vol, "cum_amt": cum_amt,
        "volume": cum_vol / 100.0, "vol": cum_vol / 100.0, "amount": cum_amt,
        "vwap": round(cum_amt / max(cum_vol, 1), 2),
    }


# ── _validate_and_repair_records ──────────────────────────────────────────

def test_repair_price_zero_discarded():
    """价格为 0 的 Bar 应被丢弃"""
    records = [
        _make_record("09:31", price=10.0, bar_vol=1000, bar_amt=10000, cum_vol=1000, cum_amt=10000),
        _make_record("09:32", price=0.0,  bar_vol=500,  bar_amt=0,     cum_vol=1500, cum_amt=10000),
        _make_record("09:33", price=10.5, bar_vol=800,  bar_amt=8400,  cum_vol=2300, cum_amt=18400),
    ]
    cleaned, repaired = TDXGlobalCachePool._validate_and_repair_records(records, "2026-09-18", 10)
    assert repaired
    assert all(r["close"] > 0 for r in cleaned)
    assert len(cleaned) == 2


def test_repair_duplicate_time_keeps_last():
    """同日相同 time_only 重复时，保留最后一条"""
    records = [
        _make_record("09:31", price=10.0, bar_vol=1000, bar_amt=10000, cum_vol=1000, cum_amt=10000),
        _make_record("09:31", price=10.2, bar_vol=900,  bar_amt=9180,  cum_vol=1900, cum_amt=19180),
    ]
    cleaned, repaired = TDXGlobalCachePool._validate_and_repair_records(records, "2026-09-18", 10)
    assert repaired
    assert len(cleaned) == 1
    assert abs(cleaned[0]["close"] - 10.2) < 0.01


def test_repair_negative_bar_vol_set_zero():
    """bar_vol 负数应置 0"""
    records = [_make_record("09:31", price=10.0, bar_vol=-500, bar_amt=0, cum_vol=0, cum_amt=0)]
    cleaned, repaired = TDXGlobalCachePool._validate_and_repair_records(records, "2026-09-18", 10)
    assert repaired
    assert cleaned[0]["bar_vol"] == 0.0


def test_repair_vwap_severely_wrong_corrected():
    """VWAP 严重失真（< close*0.5）应被修正"""
    records = [_make_record("09:31", price=100.0, bar_vol=1000, bar_amt=100000, cum_vol=1000, cum_amt=100000)]
    records[0]["vwap"] = 5.0  # 明显失真
    cleaned, repaired = TDXGlobalCachePool._validate_and_repair_records(records, "2026-09-18", 10)
    assert repaired
    assert cleaned[0]["vwap"] >= 100.0 * 0.5


def test_repair_empty_records_returns_empty():
    """空 records 输入返回空列表"""
    cleaned, _ = TDXGlobalCachePool._validate_and_repair_records([], "2026-09-18", 10)
    assert cleaned == []


# ── _validate_history_entry ───────────────────────────────────────────────

def test_validate_history_entry_rejects_old_date():
    """缓存日期距今 > 30 天应被拒绝"""
    pool = _make_pool_isolated()
    entry = {"date": "2020-01-01", "days": 10, "records": [_make_record()],
             "last_cum_vol": 1000.0, "last_cum_amt": 10000.0}
    assert pool._validate_history_entry("600519", entry, "2026-09-18") is False


def test_validate_history_entry_rejects_amt_overflow():
    """last_cum_amt > 1e11 应被拒绝"""
    pool = _make_pool_isolated()
    entry = {"date": "2026-09-18", "days": 10, "records": [_make_record()],
             "last_cum_vol": 1000.0, "last_cum_amt": 2e11}
    assert pool._validate_history_entry("600519", entry, "2026-09-18") is False


def test_validate_history_entry_accepts_valid():
    """合法 entry 通过校验"""
    pool = _make_pool_isolated()
    entry = {"date": "2026-09-18", "days": 10, "records": [_make_record()],
             "last_cum_vol": 1000.0, "last_cum_amt": 10000.0}
    assert pool._validate_history_entry("600519", entry, "2026-09-18") is True


# ── _load_from_ramdisk 损坏文件自动删除 ──────────────────────────────────

def test_corrupted_pkl_auto_deleted():
    """pkl 文件损坏时，应自动删除并返回 False"""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    pkl_path = os.path.join(tmp_dir, "tdx_cache.pkl.z")
    with open(pkl_path, "wb") as f:
        f.write(b"\x00\x01\x02corrupt_garbage")

    pool = _make_pool_isolated(pkl_path)
    result = pool._load_from_ramdisk()

    assert result is False
    assert not os.path.exists(pkl_path), "损坏的 pkl 文件应被自动删除"


# ── diagnose_and_repair ───────────────────────────────────────────────────

def test_diagnose_and_repair_returns_report_fields():
    """diagnose_and_repair 返回包含预期字段的诊断报告"""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    pkl_path = os.path.join(tmp_dir, "tdx_cache.pkl.z")
    pool = _make_pool_isolated(pkl_path)
    pool._history_static_bars["600519"] = {
        "date": "2026-09-18", "days": 10,
        "records": [_make_record()],
        "last_cum_vol": 1000.0, "last_cum_amt": 10000.0,
        "updated_at": _time.time(),
    }
    report = pool.diagnose_and_repair()
    for key in ("total_history", "repaired_history", "skipped_history",
                "total_incremental", "repaired_incremental", "skipped_incremental",
                "deleted_ramdisk"):
        assert key in report, f"报告缺少字段: {key}"


def test_diagnose_and_repair_skips_invalid_entry():
    """含异常 cum_amt 的 entry 应被丢弃，反映在 skipped_history"""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    pkl_path = os.path.join(tmp_dir, "tdx_cache.pkl.z")
    pool = _make_pool_isolated(pkl_path)
    pool._history_static_bars["600519"] = {
        "date": "2026-09-18", "days": 10,
        "records": [_make_record()],
        "last_cum_vol": 1000.0, "last_cum_amt": 9e11,  # 异常
        "updated_at": _time.time(),
    }
    report = pool.diagnose_and_repair("600519")
    assert report["skipped_history"] == 1
    assert "600519" not in pool._history_static_bars

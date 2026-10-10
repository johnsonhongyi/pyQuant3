from datetime import datetime, timedelta
import pickle
import struct

import pandas as pd
import pytest

from system_linkage_quotes import (
    collect_linkage_quote_batch,
    normalize_supported_stock_code,
    quote_row_status,
    schedule_linkage_quote_fetch,
)


TRADE_DATE = "2026-10-10"
NOW = datetime(2026, 10, 10, 10, 0, 0)


def _quotes(codes, ticktime=NOW):
    return pd.DataFrame(
        {
            "code": codes,
            "name": [f"stock-{code}" for code in codes],
            "close": [10.0] * len(codes),
            "dt": [TRADE_DATE] * len(codes),
            "ticktime": [ticktime] * len(codes),
        }
    ).set_index("code", drop=False)


def test_supported_code_scope_excludes_indices_etf_bj_and_hk():
    assert normalize_supported_stock_code("600000") == "600000"
    assert normalize_supported_stock_code("300001") == "300001"
    assert normalize_supported_stock_code("999999") == ""
    assert normalize_supported_stock_code("510300") == ""
    assert normalize_supported_stock_code("830001") == ""
    assert normalize_supported_stock_code("00700") == ""


def test_quote_status_requires_current_trade_date_and_fresh_tick():
    fresh = _quotes(["600000"]).loc["600000"]
    old_day = fresh.copy()
    old_day["dt"] = "2026-10-09"
    old_tick = fresh.copy()
    old_tick["ticktime"] = NOW - timedelta(minutes=3)
    no_tick = fresh.copy()
    no_tick["ticktime"] = pd.NaT

    assert quote_row_status(fresh, TRADE_DATE, True, now=NOW) == "ready"
    assert quote_row_status(old_day, TRADE_DATE, True, now=NOW) == "stale"
    assert quote_row_status(old_tick, TRADE_DATE, True, now=NOW) == "stale"
    assert quote_row_status(no_tick, TRADE_DATE, True, now=NOW) == "unknown"
    assert quote_row_status(fresh, TRADE_DATE, False, now=NOW) == "market_closed"
    assert quote_row_status(None, TRADE_DATE, False, now=NOW) == "market_closed"


def test_fresh_base_rows_are_not_fetched_and_stale_rows_are():
    base = _quotes(["600000", "000001"])
    statuses, selected, _cursor = schedule_linkage_quote_fetch(
        ["600000", "000001", "510300"], base, TRADE_DATE, True, now=NOW,
    )

    assert selected == []
    assert statuses["600000"] == "ready"
    assert statuses["000001"] == "ready"
    assert statuses["510300"] == "unsupported"

    base.loc["600000", "ticktime"] = NOW - timedelta(minutes=3)
    statuses, selected, _cursor = schedule_linkage_quote_fetch(
        ["600000", "000001"], base, TRADE_DATE, True, now=NOW,
    )
    assert selected == ["600000"]
    assert statuses["600000"] == "pending_fetch"
    assert statuses["000001"] == "ready"


def test_fetch_batch_is_capped_and_round_robin_cursor_advances():
    favorites = [f"600{number:03d}" for number in range(260)]
    statuses, first, cursor = schedule_linkage_quote_fetch(
        favorites, pd.DataFrame(), TRADE_DATE, True, limit=128, now=NOW,
    )
    assert len(first) == 128
    assert cursor == 128
    _statuses, second, next_cursor = schedule_linkage_quote_fetch(
        favorites, pd.DataFrame(), TRADE_DATE, True, cursor=cursor, limit=128, now=NOW,
    )
    assert len(second) == 128
    assert set(first).isdisjoint(second)
    assert next_cursor == 256
    assert len(statuses) == 260


def test_batch_fetch_status_and_quota_failure_are_explicit():
    requested = []

    def fetcher(codes):
        requested.extend(codes)
        return _quotes(codes)

    frame, statuses, _cursor = collect_linkage_quote_batch(
        ["600000", "000001"], pd.DataFrame(), TRADE_DATE, True,
        fetcher, now=NOW,
    )
    assert requested == ["000001", "600000"]
    assert len(frame) == 2
    assert statuses == {"000001": "ready", "600000": "ready"}

    class QuotaError(Exception):
        status_code = 429

    _frame, statuses, _cursor = collect_linkage_quote_batch(
        ["600000"], pd.DataFrame(), TRADE_DATE, True,
        lambda _codes: (_ for _ in ()).throw(QuotaError("rate limited")), now=NOW,
    )
    assert statuses["600000"] == "quota_limited"


def test_ats_ipc_routes_favorite_quotes_away_from_market_frame_callback():
    from ats.ipc_bridge import IPCBridge

    class FakeConnection:
        def __init__(self, payload):
            self.buffer = payload

        def settimeout(self, _timeout):
            pass

        def recv(self, size):
            chunk, self.buffer = self.buffer[:size], self.buffer[size:]
            return chunk

        def close(self):
            pass

    body = {
        "type": "UPDATE_LINKAGE_QUOTES",
        "data": _quotes(["600000"]),
        "statuses": {"600000": "ready", "510300": "unsupported"},
        "favorites_revision": 17,
    }
    payload = pickle.dumps(("UPDATE_DF_DATA", body), protocol=pickle.HIGHEST_PROTOCOL)
    connection = FakeConnection(b"DATA" + struct.pack("!I", len(payload)) + payload)
    market_frames = []
    linkage_frames = []

    IPCBridge.__new__(IPCBridge)._handle_client(
        connection, market_frames.append, None, linkage_frames.append,
    )

    assert market_frames == []
    assert len(linkage_frames) == 1
    assert list(linkage_frames[0]["data"].index) == ["600000"]
    assert linkage_frames[0]["statuses"] == {
        "600000": "ready", "510300": "unsupported",
    }
    assert linkage_frames[0]["favorites_revision"] == 17


def test_force_network_skips_hdf_and_surfaces_http_429(monkeypatch):
    from JSONData import sina_data

    instance = sina_data.Sina.__new__(sina_data.Sina)
    instance.sina_stock_api = "https://quotes.invalid/?list="
    instance.stock_data = []
    instance.stock_codes = []
    instance.max_num = 850
    instance.encoding = "utf-8"
    instance.sinaheader = {}
    instance.readonly = True
    hdf_calls = []
    http_calls = []

    def unexpected_hdf_read(*_args, **_kwargs):
        hdf_calls.append(True)
        raise AssertionError("forced network fetch must not read HDF")

    class Response:
        status_code = 200
        text = "quote-body"
        encoding = None

    monkeypatch.setattr(sina_data.h5a, "load_hdf_db", unexpected_hdf_read)
    monkeypatch.setattr(sina_data.requests, "get", lambda *a, **k: (http_calls.append(a) or Response()))
    monkeypatch.setattr(
        sina_data.Sina, "format_response_data",
        lambda self, index=False: pd.DataFrame({"close": [10.0]}, index=["600000"]),
    )
    result = instance.get_stock_list_data(["600000"], force_network=True)
    assert result.loc["600000", "close"] == 10.0
    assert hdf_calls == []
    assert len(http_calls) == 1

    class RateLimitedError(Exception):
        status_code = 429

    class RateLimitedResponse(Response):
        status_code = 429

        def raise_for_status(self):
            raise RateLimitedError("429 too many requests")

    monkeypatch.setattr(sina_data.requests, "get", lambda *_a, **_k: RateLimitedResponse())
    with pytest.raises(RateLimitedError):
        instance.get_stock_list_data(["600000"], force_network=True)

"""Exercise the Sina refresh without importing GUI/HDF runtime dependencies."""
import ast
import asyncio
import re
import time
import unittest
import threading
import requests
from urllib.error import HTTPError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / "JSONData" / "realdatajson.py"


def load_function(name, namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


class SinaRefreshRegressionTests(unittest.TestCase):


    def test_main_thread_cold_start_schedules_only_one_background_refresh(self):
        self._check_cold_start(True)

    def test_holiday_without_cache_still_schedules_background_refresh(self):
        self._check_cold_start(False)

    def _check_cold_start(self, is_trade_day):
        worker = Mock()
        fake_threading = SimpleNamespace(current_thread=threading.current_thread,
                                         main_thread=threading.main_thread, Thread=Mock(return_value=worker))
        lock = threading.Lock()
        ns = dict(time=time, log=Mock(), threading=fake_threading,
                  cct=SimpleNamespace(sina_dd_limit_time=60, get_trade_date_status=lambda: is_trade_day),
                  g_sina_blocked={}, _SINA_HDF_LOCK=threading.RLock(), _SINA_REFRESH_LOCK=lock,
                  _get_dynamic_fetch_params=lambda *a: (8, (0.2, 0.6), False, 60),
                  h5a=SimpleNamespace(load_hdf_db=lambda *a, **k: None),
                  _run_sina_refresh_in_background=Mock(), _refresh_sina_Market_json=Mock())
        get_market = load_function("get_sina_Market_json", ns)
        try:
            self.assertEqual(get_market(), [])
            self.assertEqual(get_market(), [])
            worker.start.assert_called_once()
            ns["_refresh_sina_Market_json"].assert_not_called()
        finally:
            if lock.locked():
                lock.release()

    def test_tls_timeout_falls_back_to_http_and_reuses_session(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.text = '[{"code":"600000"}]'
        session = Mock()
        session.get.side_effect = [requests.exceptions.ConnectTimeout("TLS handshake timeout"), response, response]
        request_api = SimpleNamespace(Session=Mock(return_value=session), exceptions=requests.exceptions)
        ns = dict(requests=request_api, _SINA_HTTP_LOCAL=threading.local(), sinaheader={}, log=Mock())
        read = load_function("_read_sina_market_text", ns)
        self.assertEqual(read("https://sina.test/page=7"), response.text)
        self.assertEqual(session.get.call_args_list[1][0][0], "http://sina.test/page=7")
        read("https://sina.test/page=8")
        request_api.Session.assert_called_once()
        response.raise_for_status.assert_called()

    def test_dd_cooling_returns_immediately_without_network(self):
        ns = dict(time=time, asyncio=asyncio, log=Mock(),
                  g_sina_blocked={"blocked_until": time.time() + 60},
                  _parsing_sina_dd_price_json=Mock(side_effect=AssertionError("unexpected network")))
        fetch = load_function("_fetch_with_dd_delay", ns)
        started = time.monotonic()
        self.assertIsNone(asyncio.run(fetch("http://sina.test/dd", (0, 0))))
        self.assertLess(time.monotonic() - started, 0.1)
        ns["_parsing_sina_dd_price_json"].assert_not_called()

    def test_http_502_logs_url_and_error_without_extending_cooling(self):
        url = "https://sina.test/page=7"
        ns = dict(time=time, asyncio=asyncio, log=Mock(), g_sina_blocked={"count": 0},
                  _parsing_Market_price_json=Mock(side_effect=HTTPError(url, 502, "Bad Gateway", {}, None)))
        fetch = load_function("_fetch_with_delay", ns)
        self.assertIsNone(asyncio.run(fetch(url, (0.0, 0.0))))
        message = ns["log"].error.call_args[0][0]
        self.assertIn("502", message)
        self.assertIn(url, message)
        self.assertIn("elapsed=", message)
        self.assertEqual(ns["g_sina_blocked"], {"count": 0})

    def test_quoted_count_includes_last_beijing_page(self):
        for payload in (b'"348"', b'348'):
            response = Mock()
            response.read.return_value = payload
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            ns = dict(time=time, re=re, Request=lambda *a, **k: None,
                      urlopen=Mock(return_value=response), _read_sina_market_text=Mock(return_value=payload.decode()), sinaheader={}, log=Mock(),
                      ct=SimpleNamespace(JSON_Market_Center_CountURL="count/%s",
                                         JSON_Market_Center_RealURL="page/%s/%s/%s"),
                      g_sina_blocked={}, _MARKET_COUNT_CACHE={},
                      _MARKET_COUNT_CACHE_EXPIRES={}, _MARKET_DEFAULT_COUNTS={"hs_bjs": 280})
            urls = load_function("_get_sina_Market_url", ns)("hs_bjs", "100")
            self.assertEqual(len(urls), 4)
            self.assertEqual(ns["_MARKET_COUNT_CACHE"]["hs_bjs"], 348)

    def test_slow_count_discovery_does_not_abort_before_first_batch(self):
        clock = [0.0]
        requested = []
        def discover(*args, **kwargs):
            clock[0] += 11.0
            return ["page"]
        async def fetch(url, *args, **kwargs):
            requested.append(url)
            return None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ns = dict(time=SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0]),
                  asyncio=asyncio, pd=SimpleNamespace(DataFrame=object), log=Mock(), cct=SimpleNamespace(sina_dd_limit_time=60),
                  ct=SimpleNamespace(SINA_Market_KEY={}),
                  h5a=Mock(), _SINA_CACHE_UNSET=object(),
                  _get_sina_Market_url=discover, _fetch_with_delay=fetch,
                  g_sina_blocked={"count": 0},
                  _record_sina_refresh_failure=Mock(return_value=(1, 60)))
        try:
            result = load_function("_refresh_sina_Market_json", ns)(
                _cached_h5=None, _fetch_params=(8, (0.2, 0.6), False, 60))
            self.assertEqual(requested, ["page"] * 6)
            self.assertEqual(result, [])
            ns["h5a"].write_hdf_db.assert_not_called()
            self.assertIn("batch 1 failed", ns["_record_sina_refresh_failure"].call_args[0][0])
            # Slow count discovery is separate from the 30s quote refresh budget.
            requested.clear()
            clock[0] = 0.0
            def full_discovery(*args, **kwargs):
                clock[0] += 11.0
                return ["page"] * 19
            async def successful_fetch(url, *args, **kwargs):
                if len(requested) % 8 == 0:
                    clock[0] += 0.5
                requested.append(url)
                if len(requested) == 1:
                    return None  # One transient page failure, then retry succeeds.
                return SimpleNamespace(empty=False)
            class AggregationReached(Exception):
                pass
            ns["_get_sina_Market_url"] = full_discovery
            ns["_fetch_with_delay"] = successful_fetch
            ns["pd"].concat = Mock(side_effect=AggregationReached)
            with self.assertRaises(AggregationReached):
                ns["_refresh_sina_Market_json"](
                    _cached_h5=None, _fetch_params=(8, (0.2, 0.6), False, 60))
            self.assertEqual(len(requested), 58)
        finally:
            loop.close()
            asyncio.set_event_loop(None)


if __name__ == "__main__":
    unittest.main()

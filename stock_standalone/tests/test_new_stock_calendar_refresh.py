import datetime
import time

from ats.new_stock_fetcher import NewStockFetcher


def _fetcher_with_cache(updated_at: float) -> NewStockFetcher:
    fetcher = NewStockFetcher.__new__(NewStockFetcher)
    fetcher._cached_ipo_dict = {"301000": {"code": "301000", "issue_price": 10.0}}
    fetcher._last_calendar_fetch_time = updated_at
    fetcher._ipo_calendar_ttl_seconds = 300.0
    return fetcher


def test_ipo_calendar_does_not_reuse_previous_day_cache(monkeypatch):
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    fetcher = _fetcher_with_cache(yesterday.timestamp())
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"result": {"data": [{
                "SECURITY_CODE": "301686",
                "SECURITY_NAME": "中塑股份",
                "TRADE_MARKET": "创业板",
                "ISSUE_PRICE": 55.28,
                "APPLY_DATE": "2026-09-10",
                "LISTING_DATE": "2026-09-22",
            }]}}

    class Session:
        def get(self, *args, **kwargs):
            calls.append(1)
            return Response()

    monkeypatch.setattr("ats.new_stock_fetcher._get_direct_session", lambda: Session())
    result = fetcher.fetch_ipo_calendar(force=False)

    assert calls, "跨日缓存必须触发 IPO 日历更新"
    assert "301686" in result
    assert result["301686"]["listing_date"] == "2026-09-22"


def test_ipo_calendar_short_ttl_prevents_auto_polling_storm(monkeypatch):
    fetcher = _fetcher_with_cache(time.time())
    monkeypatch.setattr(
        "ats.new_stock_fetcher._get_direct_session",
        lambda: (_ for _ in ()).throw(AssertionError("recent cache must not request")),
    )

    assert fetcher.fetch_ipo_calendar(force=False) == fetcher._cached_ipo_dict

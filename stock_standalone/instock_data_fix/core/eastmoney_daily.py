"""Rate-limited daily Eastmoney ETF and fund-flow downloads."""

import contextlib
import datetime
import json
import logging
import math
import os
import tempfile
import threading
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import instock.core.tablestructure as tbs

try:
    import fcntl
except ImportError:  # pragma: no cover - production runs on Linux
    fcntl = None


_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "eastmoney")
_LOCAL_LOCK = threading.RLock()
_TIMEZONE = ZoneInfo("Asia/Shanghai")
_MIN_GAP_SECONDS = max(30, int(os.environ.get("EASTMONEY_MIN_GAP_SECONDS", "30")))
_MAX_GAP_SECONDS = max(_MIN_GAP_SECONDS, int(os.environ.get("EASTMONEY_MAX_GAP_SECONDS", "180")))
_PAGE_SIZE = max(100, int(os.environ.get("EASTMONEY_PAGE_SIZE", "10000")))
_MAX_PAGES = max(1, int(os.environ.get("EASTMONEY_MAX_PAGES", "100")))
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://quote.eastmoney.com/",
}


class EastmoneyBlockedError(RuntimeError):
    """The provider rejected or failed the request; do not retry this batch."""


class EastmoneyDataError(RuntimeError):
    """The provider returned incomplete or unrecognized data."""


@contextlib.contextmanager
def _file_lock(name):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    handle = open(os.path.join(_CACHE_DIR, name + ".lock"), "a+b")
    _LOCAL_LOCK.acquire()
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        _LOCAL_LOCK.release()


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="eastmoney-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else default.copy()
    except (OSError, ValueError, TypeError):
        return default.copy()


def _policy_path():
    return os.path.join(_CACHE_DIR, "provider-state.json")


def _read_policy():
    return _read_json(
        _policy_path(),
        {
            "last_request_at": 0,
            "blocked_until": 0,
            "failure_streak": 0,
            "success_streak": 0,
            "min_gap_seconds": _MIN_GAP_SECONDS,
        },
    )


def _record_failure(state, reason):
    streak = int(state.get("failure_streak", 0)) + 1
    cooldown_hours = min(12 * (2 ** (streak - 1)), 24 * 7)
    state.update(
        {
            "failure_streak": streak,
            "success_streak": 0,
            "blocked_until": time.time() + cooldown_hours * 3600,
            "last_error": str(reason)[:240],
            "last_error_at": datetime.datetime.now(_TIMEZONE).isoformat(timespec="seconds"),
            "min_gap_seconds": min(
                _MAX_GAP_SECONDS,
                max(60, int(state.get("min_gap_seconds", _MIN_GAP_SECONDS)) * 2),
            ),
        }
    )


def _provider_cooldown_remaining():
    with _file_lock("http"):
        state = _read_policy()
        return max(0, float(state.get("blocked_until", 0)) - time.time())


def _mark_provider_failure(reason):
    with _file_lock("http"):
        state = _read_policy()
        _record_failure(state, reason)
        _atomic_json(_policy_path(), state)


def _mark_provider_success(state, elapsed):
    state["failure_streak"] = 0
    state["blocked_until"] = 0
    state["success_streak"] = int(state.get("success_streak", 0)) + 1
    gap = max(_MIN_GAP_SECONDS, int(state.get("min_gap_seconds", _MIN_GAP_SECONDS)))
    if elapsed >= 8:
        gap = min(_MAX_GAP_SECONDS, max(60, gap * 2))
        state["success_streak"] = 0
    elif state["success_streak"] >= 12:
        gap = max(_MIN_GAP_SECONDS, gap - 5)
        state["success_streak"] = 0
    state["min_gap_seconds"] = gap
    state.pop("last_error", None)
    state.pop("last_error_at", None)


def _request_json(url, params, referer):
    """Make one paced request. There are deliberately no automatic retries."""
    with _file_lock("http"):
        state = _read_policy()
        now = time.time()
        blocked_until = float(state.get("blocked_until", 0))
        if blocked_until > now:
            raise EastmoneyBlockedError(
                "provider cooldown active for %.0f more seconds" % (blocked_until - now)
            )

        last_request = float(state.get("last_request_at", 0))
        gap = max(_MIN_GAP_SECONDS, int(state.get("min_gap_seconds", _MIN_GAP_SECONDS)))
        delay = last_request + gap - now
        if delay > 0:
            time.sleep(delay)

        started = time.monotonic()
        try:
            response = requests.get(
                url,
                params=params,
                headers={**_HEADERS, "Referer": referer},
                timeout=(5, 20),
            )
            state["last_request_at"] = time.time()
            body = (response.text or "")[:2048].lower()
            blocked_status = response.status_code in (403, 418, 429, 451, 500, 502, 503, 504)
            blocked_text = any(
                marker in body
                for marker in ("captcha", "verify", "访问频繁", "请求频繁", "风控", "安全验证")
            )
            if blocked_status or blocked_text:
                reason = "HTTP %s / provider challenge" % response.status_code
                _record_failure(state, reason)
                _atomic_json(_policy_path(), state)
                raise EastmoneyBlockedError(reason)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                reason = "non-JSON response (%s)" % type(exc).__name__
                _record_failure(state, reason)
                _atomic_json(_policy_path(), state)
                raise EastmoneyBlockedError(reason) from exc

            data = payload.get("data") if isinstance(payload, dict) else None
            if (
                not isinstance(data, dict)
                or "total" not in data
                or "diff" not in data
                or payload.get("rc") not in (None, 0)
            ):
                reason = "unrecognized or rejected JSON payload"
                _record_failure(state, reason)
                _atomic_json(_policy_path(), state)
                raise EastmoneyBlockedError(reason)

            elapsed = time.monotonic() - started
            _mark_provider_success(state, elapsed)
            _atomic_json(_policy_path(), state)
            return payload
        except EastmoneyBlockedError:
            raise
        except Exception as exc:
            state["last_request_at"] = time.time()
            _record_failure(state, "%s: %s" % (type(exc).__name__, exc))
            _atomic_json(_policy_path(), state)
            raise EastmoneyBlockedError(type(exc).__name__) from exc


def _diff_rows(payload):
    diff = payload["data"].get("diff")
    if isinstance(diff, list):
        rows = diff
    elif isinstance(diff, dict):
        if diff and all(isinstance(value, dict) for value in diff.values()):
            rows = list(diff.values())
        elif diff and any(isinstance(value, (list, tuple)) for value in diff.values()):
            rows = pd.DataFrame(diff).to_dict("records")
        elif diff and all(str(key).startswith("f") for key in diff):
            rows = [diff]
        else:
            rows = pd.DataFrame(diff).to_dict("records")
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _fetch_pages(url, params, referer):
    params = params.copy()
    params["pz"] = str(_PAGE_SIZE)
    params["pn"] = "1"
    payload = _request_json(url, params, referer)
    total = int(payload["data"].get("total") or 0)
    rows = _diff_rows(payload)
    if total <= 0 or not rows:
        raise EastmoneyDataError("empty response")

    page_size = len(rows)
    total_pages = math.ceil(total / page_size)
    if total_pages > _MAX_PAGES:
        raise EastmoneyDataError("page count exceeds safety cap: %s" % total_pages)
    for page in range(2, total_pages + 1):
        params["pn"] = str(page)
        params["pz"] = str(page_size)
        next_payload = _request_json(url, params, referer)
        page_rows = _diff_rows(next_payload)
        if not page_rows:
            raise EastmoneyDataError("empty page %s/%s" % (page, total_pages))
        rows.extend(page_rows)
    if len(rows) < total:
        raise EastmoneyDataError("incomplete response: %s/%s" % (len(rows), total))
    return rows[:total], total_pages


def _date_key(value):
    if value is None:
        return datetime.datetime.now(_TIMEZONE).date().isoformat()
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def _is_after_close_today(date_key):
    now = datetime.datetime.now(_TIMEZONE)
    return (
        date_key == now.date().isoformat()
        and now.weekday() < 5
        and now.time() >= datetime.time(16, 0)
    )


def _daily_fetch(dataset, date_key, fetcher):
    if not _is_after_close_today(date_key):
        return None

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, "%s-%s.pkl" % (dataset, date_key))
    marker_path = os.path.join(_CACHE_DIR, "%s-%s.state" % (dataset, date_key))
    with _file_lock("dataset-" + dataset + "-" + date_key):
        if os.path.exists(cache_path):
            try:
                return pd.read_pickle(cache_path)
            except Exception as exc:
                logging.error("Eastmoney cache read failed for %s: %s", dataset, exc)
                return None
        if os.path.exists(marker_path):
            return None

        remaining = _provider_cooldown_remaining()
        if remaining > 0:
            _atomic_json(marker_path, {"status": "deferred", "date": date_key})
            logging.warning(
                "Eastmoney %s deferred for %s; provider cooldown %.0f seconds remains",
                dataset,
                date_key,
                remaining,
            )
            return None

        _atomic_json(marker_path, {"status": "started", "date": date_key})
        try:
            data = fetcher()
            if (
                data is None
                or isinstance(data, pd.DataFrame) and data.empty
                or isinstance(data, dict) and not data
            ):
                raise EastmoneyDataError("no usable records")
            temp_path = cache_path + ".tmp"
            pd.to_pickle(data, temp_path)
            os.replace(temp_path, cache_path)
            _atomic_json(marker_path, {"status": "success", "date": date_key})
            return data
        except EastmoneyBlockedError as exc:
            _atomic_json(marker_path, {"status": "blocked", "date": date_key})
            logging.warning("Eastmoney %s blocked for %s: %s", dataset, date_key, exc)
        except Exception as exc:
            _mark_provider_failure("%s: %s" % (type(exc).__name__, exc))
            _atomic_json(marker_path, {"status": "failed", "date": date_key})
            logging.error("Eastmoney %s failed for %s: %s", dataset, date_key, exc)
        return None


_ETF_FIELD_MAP = {
    "code": "f12",
    "name": "f14",
    "new_price": "f2",
    "change_rate": "f3",
    "ups_downs": "f4",
    "volume": "f5",
    "deal_amount": "f6",
    "open_price": "f17",
    "high_price": "f15",
    "low_price": "f16",
    "pre_close_price": "f18",
    "turnoverrate": "f8",
    "total_market_cap": "f20",
    "free_cap": "f21",
}

_FLOW_FIELD_MAPS = {
    "今日": {
        "code": "f12", "name": "f14", "new_price": "f2", "change_rate": "f3",
        "fund_amount": "f62", "fund_rate": "f184", "fund_amount_super": "f66",
        "fund_rate_super": "f69", "fund_amount_large": "f72", "fund_rate_large": "f75",
        "fund_amount_medium": "f78", "fund_rate_medium": "f81", "fund_amount_small": "f84",
        "fund_rate_small": "f87",
    },
    "3日": {
        "code": "f12", "name": "f14", "new_price": "f2", "change_rate_3": "f127",
        "fund_amount_3": "f267", "fund_rate_3": "f268", "fund_amount_super_3": "f269",
        "fund_rate_super_3": "f270", "fund_amount_large_3": "f271", "fund_rate_large_3": "f272",
        "fund_amount_medium_3": "f273", "fund_rate_medium_3": "f274", "fund_amount_small_3": "f275",
        "fund_rate_small_3": "f276",
    },
    "5日": {
        "code": "f12", "name": "f14", "new_price": "f2", "change_rate_5": "f109",
        "fund_amount_5": "f164", "fund_rate_5": "f165", "fund_amount_super_5": "f166",
        "fund_rate_super_5": "f167", "fund_amount_large_5": "f168", "fund_rate_large_5": "f169",
        "fund_amount_medium_5": "f170", "fund_rate_medium_5": "f171", "fund_amount_small_5": "f172",
        "fund_rate_small_5": "f173",
    },
    "10日": {
        "code": "f12", "name": "f14", "new_price": "f2", "change_rate_10": "f160",
        "fund_amount_10": "f174", "fund_rate_10": "f175", "fund_amount_super_10": "f176",
        "fund_rate_super_10": "f177", "fund_amount_large_10": "f178", "fund_rate_large_10": "f179",
        "fund_amount_medium_10": "f180", "fund_rate_medium_10": "f181", "fund_amount_small_10": "f182",
        "fund_rate_small_10": "f183",
    },
}


def _fetch_etf_frame(date_key):
    params = {
        "po": "1", "np": "1", "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2", "wbp2u": "|0|0|0|web", "fid": "f12",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024,b:MK0827",
        "fields": ",".join(dict.fromkeys(_ETF_FIELD_MAP.values())),
    }
    rows, pages = _fetch_pages(
        "https://push2delay.eastmoney.com/api/qt/clist/get",
        params,
        "https://quote.eastmoney.com/center/gridlist.html#fund_etf",
    )
    frame = pd.DataFrame(rows)
    for target, source in _ETF_FIELD_MAP.items():
        if source not in frame.columns:
            raise EastmoneyDataError("ETF response missing field %s" % source)
    frame = frame[list(_ETF_FIELD_MAP.values())].rename(
        columns={source: target for target, source in _ETF_FIELD_MAP.items()}
    )
    frame["code"] = frame["code"].astype(str).str.zfill(6)
    for column in frame.columns.difference(["code", "name"]):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.loc[frame["new_price"].notna()].reset_index(drop=True)
    if frame.empty:
        raise EastmoneyDataError("ETF response has no priced records")
    frame.insert(0, "date", date_key)
    logging.info("Eastmoney ETF refresh complete: date=%s rows=%s pages=%s", date_key, len(frame), pages)
    return frame


def _fetch_flow_batch(date_key):
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    stock_filter = (
        "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,"
        "m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
    )
    result = {}
    for index, (indicator, field_map) in enumerate(_FLOW_FIELD_MAPS.items()):
        params = {
            "fid": {"今日": "f62", "3日": "f267", "5日": "f164", "10日": "f174"}[indicator],
            "po": "1", "np": "1", "fltt": "2", "invt": "2",
            "ut": "b2884a393a59ad64002292a3e90d46a5", "fs": stock_filter,
            "fields": ",".join(dict.fromkeys(field_map.values())),
        }
        rows, pages = _fetch_pages(
            url,
            params,
            "https://data.eastmoney.com/zjlx/detail.html",
        )
        frame = pd.DataFrame(rows)
        if any(source not in frame.columns for source in field_map.values()):
            raise EastmoneyDataError("fund-flow %s response is missing fields" % indicator)
        frame = frame[list(field_map.values())].rename(
            columns={source: target for target, source in field_map.items()}
        )
        frame["code"] = frame["code"].astype(str).str.zfill(6)
        frame["new_price"] = pd.to_numeric(frame["new_price"], errors="coerce")
        for column in frame.columns.difference(["code", "name"]):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.loc[
            frame["code"].str.startswith(("600", "601", "603", "605", "688", "689", "000", "001", "002", "003", "300", "301", "43", "83", "87", "92"))
            & frame["new_price"].notna()
        ].reset_index(drop=True)
        expected_columns = list(tbs.CN_STOCK_FUND_FLOW[index]["columns"])
        frame = frame.reindex(columns=expected_columns)
        if frame.empty:
            raise EastmoneyDataError("fund-flow %s response has no usable records" % indicator)
        result[index] = frame
        logging.info(
            "Eastmoney fund-flow refresh page complete: date=%s period=%s rows=%s pages=%s",
            date_key,
            indicator,
            len(frame),
            pages,
        )
    return result


def fetch_etf_spot_once(date):
    date_key = _date_key(date)
    return _daily_fetch("etf-spot", date_key, lambda: _fetch_etf_frame(date_key))


def fetch_stock_fund_flow_once(index, date=None):
    if index not in range(len(_FLOW_FIELD_MAPS)):
        raise ValueError("unsupported fund-flow index: %s" % index)
    date_key = _date_key(date)
    batch = _daily_fetch("stock-fund-flow", date_key, lambda: _fetch_flow_batch(date_key))
    if not isinstance(batch, dict):
        return None
    return batch.get(index)

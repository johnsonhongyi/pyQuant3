# -*- coding: utf-8 -*-
"""Freshness and bounded request scheduling for favorite-only quotes."""

from datetime import datetime
import math
import logging
import threading
import time


LINKAGE_QUOTE_BATCH_SIZE = 128
LINKAGE_QUOTE_CACHE_SIZE = 512
LINKAGE_QUOTE_MAX_AGE_SECONDS = 120
_SUPPORTED_PREFIXES = ("600", "601", "603", "605", "688", "689",
                       "000", "001", "002", "003", "300", "301")


class AsyncLinkageQuoteFetcher:
    """One bounded display-only request; never retain a full market frame or wait on IO."""

    def __init__(self, fetcher):
        self._fetcher = fetcher
        self._lock = threading.Lock()
        self._busy = False
        self._result = None

    def submit(self, revision, trade_date, codes, market_active):
        codes = tuple(codes[:LINKAGE_QUOTE_BATCH_SIZE])
        if not codes or not market_active:
            return False
        with self._lock:
            if self._busy or self._result is not None:
                return False
            self._busy = True

        def fetch():
            started = time.monotonic()
            try:
                frame, statuses, _ = collect_linkage_quote_batch(
                    codes, None, trade_date, market_active, self._fetcher,
                    limit=LINKAGE_QUOTE_BATCH_SIZE,
                )
                result = (revision, trade_date, codes, frame, statuses, started)
            except Exception:
                # Preserve explicit pending status if validation itself failed.
                logging.getLogger(__name__).exception('Favorite quote worker validation failed')
                result = (revision, trade_date, codes, None,
                          dict.fromkeys(codes, 'pending_fetch'), started)
            with self._lock:
                self._result = result
                self._busy = False

        try:
            threading.Thread(target=fetch, name='LinkageQuoteFetch', daemon=True).start()
        except Exception:
            with self._lock:
                self._busy = False
            raise
        return True

    def take_result(self, revision, trade_date):
        with self._lock:
            result, self._result = self._result, None
        if result is None or result[:2] != (revision, trade_date):
            return None
        # Age from request start is conservative when the network is slow.
        return result[2:]


def normalize_supported_stock_code(value):
    """Return a supported six-digit SH/SZ A-share code, otherwise an empty string."""
    if value is None:
        return ""
    code = str(value).strip()
    if code.lower() in {"", "nan", "nat", "none", "<na>"}:
        return ""
    if not isinstance(value, str) and code.isdigit() and 0 < len(code) < 6:
        code = code.zfill(6)
    if len(code) != 6 or not code.isdigit() or not code.startswith(_SUPPORTED_PREFIXES):
        return ""
    return code


def normalize_trade_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        value = value.strftime("%Y-%m-%d")
    text = str(value).strip()[:10].replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return ""


def _as_datetime(value, source_date=""):
    if value is None:
        return None
    if str(value).strip().lower() in {"", "nan", "nat", "none", "<na>"}:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("/", "-"))
    except ValueError:
        pass
    if len(text) == 6 and text.isdigit():
        text = f"{text[:2]}:{text[2:4]}:{text[4:6]}"
    if len(text) == 8 and text[2] == ":" and text[5] == ":" and source_date:
        try:
            return datetime.fromisoformat(f"{source_date} {text}")
        except ValueError:
            return None
    return None


def quote_row_status(row, latest_trade_date, market_active, frame_age_seconds=0,
                     now=None, max_age_seconds=LINKAGE_QUOTE_MAX_AGE_SECONDS):
    """Classify a row without treating missing timestamps or prior-day prices as live."""
    if row is None:
        return "market_closed" if not market_active else "pending_fetch"
    price = None
    for key in ("trade", "price", "now", "close"):
        try:
            candidate = float(row.get(key))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(candidate):
            price = candidate
            break
    if price is None:
        return "pending_fetch"
    if price <= 0:
        return "pending_fetch"

    source_date = ""
    for key in ("dt", "trade_date", "date"):
        source_date = normalize_trade_date(row.get(key))
        if source_date:
            break
    timestamp = _as_datetime(row.get("ticktime"), source_date)
    if not source_date and timestamp is not None:
        source_date = timestamp.date().isoformat()
    latest_trade_date = normalize_trade_date(latest_trade_date)
    if not source_date or not latest_trade_date:
        return "unknown"
    if source_date != latest_trade_date:
        return "stale"
    if not market_active:
        return "market_closed"
    if timestamp is None:
        return "unknown"

    now = now or datetime.now()
    if hasattr(now, "to_pydatetime"):
        now = now.to_pydatetime()
    try:
        tick_age = (now - timestamp).total_seconds()
        frame_age = float(frame_age_seconds)
    except (TypeError, ValueError, OverflowError):
        return "stale"
    if (tick_age < -30 or tick_age > max_age_seconds
            or frame_age < 0 or frame_age > 15):
        return "stale"
    return "ready"


def frame_quote_row(frame, code):
    """Find one quote row in either code-indexed or code-column frames."""
    if frame is None or getattr(frame, "empty", True):
        return None
    code = str(code).strip().zfill(6)
    try:
        if "code" in frame.columns:
            matches = frame[frame["code"].astype(str).str.strip().str.zfill(6) == code]
            if not matches.empty:
                return matches.iloc[0]
        if code in frame.index:
            row = frame.loc[code]
        elif code.isdigit() and int(code) in frame.index:
            row = frame.loc[int(code)]
        else:
            return None
        return row.iloc[0] if getattr(row, "ndim", 1) > 1 else row
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def schedule_linkage_quote_fetch(favorite_codes, base_frame, latest_trade_date,
                                 market_active, cursor=0, limit=LINKAGE_QUOTE_BATCH_SIZE,
                                 now=None, frame_age_seconds=0):
    """Return per-code status, a fair bounded fetch batch, and the next scan cursor."""
    codes = set()
    statuses = {}
    for value in favorite_codes or ():
        text = "" if value is None else str(value).strip()
        normalized = normalize_supported_stock_code(text)
        if normalized:
            codes.add(normalized)
        elif text.isdigit() and 0 < len(text) <= 6:
            statuses[text.zfill(6)] = "unsupported"
    codes = sorted(codes)
    for code in codes:
        row = frame_quote_row(base_frame, code)
        if row is None and not market_active:
            statuses[code] = "market_closed"
        else:
            statuses[code] = quote_row_status(
                row, latest_trade_date, market_active, frame_age_seconds, now=now
            )

    if not codes or not market_active or int(limit) <= 0:
        return statuses, [], int(cursor) % max(len(codes), 1)

    start = int(cursor) % len(codes)
    selected = []
    last_index = start
    for offset in range(len(codes)):
        index = (start + offset) % len(codes)
        code = codes[index]
        if statuses[code] not in {"ready", "market_closed"}:
            selected.append(code)
            statuses[code] = "pending_fetch"
            last_index = index
            if len(selected) >= int(limit):
                break
    next_cursor = (last_index + 1) % len(codes) if selected else start
    return statuses, selected, next_cursor


def collect_linkage_quote_batch(favorite_codes, base_frame, latest_trade_date,
                                market_active, fetcher, cursor=0,
                                limit=LINKAGE_QUOTE_BATCH_SIZE, now=None,
                                frame_age_seconds=0):
    """Fetch one bounded batch and return a validated display-only quote frame."""
    statuses, selected, next_cursor = schedule_linkage_quote_fetch(
        favorite_codes, base_frame, latest_trade_date, market_active,
        cursor=cursor, limit=limit, now=now,
        frame_age_seconds=frame_age_seconds,
    )
    if not selected:
        return None, statuses, next_cursor
    try:
        fetched = fetcher(selected)
    except Exception as exc:
        response = getattr(exc, "response", None)
        error_code = getattr(
            exc, "status_code",
            getattr(response, "status_code", getattr(exc, "code", None)),
        )
        is_quota_limited = error_code == 429 or "429" in str(exc)
        failure_status = "quota_limited" if is_quota_limited else "pending_fetch"
        for code in selected:
            statuses[code] = failure_status
        return None, statuses, next_cursor

    valid_codes = [code for code in selected if frame_quote_row(fetched, code) is not None]
    if not valid_codes:
        return None, statuses, next_cursor
    if "code" in fetched.columns:
        result = fetched[
            fetched["code"].astype(str).str.strip().str.zfill(6).isin(valid_codes)
        ].copy()
    else:
        result = fetched.loc[
            [key for key in fetched.index if str(key).strip().zfill(6) in valid_codes]
        ].copy()
    for code in selected:
        row = frame_quote_row(result, code)
        status = quote_row_status(
            row, latest_trade_date, market_active, 0, now=now
        )
        statuses[code] = status if row is not None else "pending_fetch"
    return result, statuses, next_cursor

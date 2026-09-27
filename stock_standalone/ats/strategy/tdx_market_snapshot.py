# -*- coding: utf-8 -*-
"""Bounded, timestamp-checked TDX market-wide snapshot collector.

This runs only in the background acquisition path. It never feeds the trading
poller directly; incomplete coverage or stale server timestamps stay UNREADY.
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_source_orchestrator import store_observation


_TZ_NAME = "Asia/Shanghai"
_TZ = ZoneInfo(_TZ_NAME)
_SOURCE_ID = "tdx.market_observation_pipeline"
_SOURCE_VERSION = "tdx_a_share_snapshot.v1"
_UNIVERSE_RELATIVE = Path("data") / "ipo_learning" / "tdx_a_share_universe.json"
_UNIVERSE_TTL = timedelta(hours=24)
_QUOTE_TTL_SECONDS = 120
_MAX_CROSS_SECTION_SECONDS = 180
_MAX_UNIVERSE_SIZE = 8000
_PAGE_SIZE = 1000
_QUOTE_BATCH_SIZE = 40
_A_SHARE_PREFIXES = (
    "000", "001", "002", "003", "300", "301", "302", "600", "601",
    "603", "605", "688", "689", "920", "43", "83", "87", "88", "92",
)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _quote_datetime(value: Any, now: datetime) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for pattern in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text, pattern).time()
            return datetime.combine(now.date(), parsed, _TZ)
        except ValueError:
            continue
    return None


def _in_continuous_session(now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    return 570 <= minute <= 690 or 780 <= minute <= 900


def _is_stock_row(row: Mapping[str, Any]) -> bool:
    code = str(row.get("code") or "").strip().zfill(6)
    return len(code) == 6 and code.isdigit() and code.startswith(_A_SHARE_PREFIXES)


def _read_universe_cache(path: Path, now_utc: datetime) -> Optional[List[Dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        refreshed = datetime.fromisoformat(payload.get("refreshed_at_utc", ""))
        if refreshed.tzinfo is None or refreshed.utcoffset() is None:
            return None
        if now_utc - refreshed.astimezone(timezone.utc) > _UNIVERSE_TTL:
            return None
        rows = payload.get("stocks")
        if not isinstance(rows, list) or len(rows) < 3000:
            return None
        clean = [row for row in rows if isinstance(row, dict) and _is_stock_row(row)]
        return clean if len(clean) == len(rows) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _fetch_universe(api: Any) -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for market in (0, 1, 2):
        count = api.get_security_count(market)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > 100000:
            raise ValueError("TDX_SECURITY_COUNT_INVALID")
        for offset in range(0, count, _PAGE_SIZE):
            page = api.get_security_list(market, offset)
            if not isinstance(page, (list, tuple)):
                raise ValueError("TDX_SECURITY_DIRECTORY_UNAVAILABLE")
            for item in page:
                if not isinstance(item, Mapping) or not _is_stock_row(item):
                    continue
                code = str(item.get("code") or "").strip().zfill(6)
                rows[code] = {
                    "market": market, "code": code,
                    "name": str(item.get("name") or ""),
                }
    if len(rows) < 3000 or len(rows) > _MAX_UNIVERSE_SIZE:
        raise ValueError("TDX_A_SHARE_DIRECTORY_COVERAGE_INVALID")
    return list(rows.values())


def _load_or_refresh_universe(root: Path, api: Any, now: datetime) -> List[Dict[str, Any]]:
    path = root / _UNIVERSE_RELATIVE
    cached = _read_universe_cache(path, now.astimezone(timezone.utc))
    if cached:
        return cached
    rows = _fetch_universe(api)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    payload = {
        "source_id": "tdx.security_directory",
        "source_version": "pytdx.security_list.v1",
        "source_timezone": _TZ_NAME,
        "refreshed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stocks": rows,
    }
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    os.replace(temporary, path)
    return rows


def _quote_chunks(api: Any, stocks: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for offset in range(0, len(stocks), _QUOTE_BATCH_SIZE):
        batch = stocks[offset:offset + _QUOTE_BATCH_SIZE]
        request = [(int(row["market"]), str(row["code"])) for row in batch]
        requested_codes = {str(row["code"]) for row in batch}
        response = api.get_security_quotes(request) or []
        if not isinstance(response, (list, tuple)):
            continue
        for quote in response:
            if not isinstance(quote, Mapping):
                continue
            code = str(quote.get("code") or "").strip().zfill(6)
            if code in requested_codes:
                result[code] = dict(quote)
        if offset + _QUOTE_BATCH_SIZE < len(stocks):
            time.sleep(0.08)
    return list(result.values())


def _connect_background_api() -> Any:
    """Create a dedicated TDX socket; never hold the live fetcher's lock during bulk I/O."""
    from pytdx.hq import TdxHq_API
    from ats.tdx_realtime_fetcher import FALLBACK_TDX_HOSTS, TDXRealtimeFetcher

    fetcher = TDXRealtimeFetcher.get_instance()
    with fetcher._conn_lock:
        preferred = fetcher.current_host
    hosts = []
    if preferred:
        hosts.append(("当前活跃主站", preferred[1], preferred[2]))
    hosts.extend(host for host in FALLBACK_TDX_HOSTS if host not in hosts)
    for _name, ip, port in hosts:
        api = TdxHq_API(heartbeat=False)
        try:
            if api.connect(ip, int(port), time_out=1.2):
                return api
        except Exception:
            pass
        try:
            api.disconnect()
        except Exception:
            pass
    raise ConnectionError("TDX_BACKGROUND_CONNECTION_UNAVAILABLE")


def _price_limit_rate(code: str, name: str) -> float:
    if code.startswith(("300", "301", "302", "688", "689")):
        return 0.20
    if code.startswith(("920", "43", "83", "87", "88", "92")):
        return 0.30
    if "ST" in name.upper():
        return 0.05
    return 0.10


def derive_market_metrics(
    quotes: Iterable[Mapping[str, Any]],
    *,
    ipo_codes: Set[str],
    no_limit_codes: Set[str],
    high_volatility_threshold_pct: float = 5.0,
) -> Dict[str, Any]:
    """Derive only the metrics whose required cross-section is present."""
    clean: Dict[str, Dict[str, Any]] = {}
    for raw in quotes:
        code = str(raw.get("code") or "").strip().zfill(6)
        price, previous = _number(raw.get("price")), _number(raw.get("last_close"))
        amount = _number(raw.get("amount"))
        if not code.isdigit() or price is None or previous is None or price <= 0 or previous <= 0:
            continue
        clean[code] = {
            **dict(raw), "code": code, "price": price, "last_close": previous,
            "amount": max(0.0, amount or 0.0),
        }
    advancing = declining = 0
    total_amount = high_vol_amount = ipo_amount = 0.0
    limit_down = 0
    for code, row in clean.items():
        price, previous, amount = row["price"], row["last_close"], row["amount"]
        change_pct = (price / previous - 1.0) * 100.0
        advancing += change_pct > 0
        declining += change_pct < 0
        total_amount += amount
        if abs(change_pct) >= high_volatility_threshold_pct:
            high_vol_amount += amount
        if code in ipo_codes:
            ipo_amount += amount
        if code not in no_limit_codes:
            rate = _price_limit_rate(code, str(row.get("name") or ""))
            lower_limit = round(previous * (1.0 - rate) + 1e-8, 2)
            if abs(price - lower_limit) <= 0.005:
                limit_down += 1
    directional = advancing + declining
    metrics: Dict[str, Any] = {
        "quote_count": len(clean), "advances": advancing, "declines": declining,
        "unchanged": len(clean) - directional,
    }
    if directional:
        metrics["advance_decline_ratio"] = advancing / directional
    if total_amount > 0:
        metrics["high_volatility_amount_share"] = high_vol_amount / total_amount * 100.0
        metrics["limit_down_count"] = limit_down
        metrics["ipo_amount_share"] = ipo_amount / total_amount * 100.0
    return metrics


def _recent_ipo_metadata(now: datetime) -> Tuple[Set[str], Dict[str, str]]:
    from ats.strategy.ipo_eastmoney_sources import fetch_issue_calendar_rows

    rows = fetch_issue_calendar_rows(page_size=500)
    cutoff = now.date() - timedelta(days=30)
    ipo_codes: Set[str] = set()
    listing_dates: Dict[str, str] = {}
    for row in rows:
        code = str(row.get("SECURITY_CODE") or "").strip().zfill(6)
        try:
            listed = date.fromisoformat(str(row.get("LISTING_DATE") or "")[:10])
        except ValueError:
            continue
        if code.isdigit() and cutoff <= listed <= now.date():
            ipo_codes.add(code)
            listing_dates[code] = listed.isoformat()
    if not listing_dates:
        raise ValueError("IPO_RECENT_LISTING_CALENDAR_EMPTY")
    return ipo_codes, listing_dates


def _no_limit_codes(api: Any, listing_dates: Mapping[str, str], now: datetime) -> Set[str]:
    result: Set[str] = set()
    for code, listing_day in listing_dates.items():
        market = 2 if code.startswith(("920", "43", "83", "87", "88", "92")) else (
            1 if code.startswith(("60", "68")) else 0
        )
        bars = api.get_security_bars(9, market, code, 0, 10) or []
        sessions = set()
        for bar in bars:
            if not isinstance(bar, Mapping):
                continue
            try:
                day_text = str(bar.get("datetime") or "")[:10]
                bar_day = date.fromisoformat(day_text)
            except ValueError:
                continue
            if listing_day <= day_text <= now.date().isoformat() and bar_day <= now.date():
                sessions.add(day_text)
        if not sessions:
            raise ValueError("TDX_RECENT_IPO_SESSION_HISTORY_MISSING")
        if len(sessions) <= 5:
            result.add(code)
    return result


def collect_tdx_market_snapshot_fields(
    root: str | Path,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Fetch a coherent live A-share quote cross-section and persist verified metrics."""
    local_now = now or datetime.now(_TZ)
    if local_now.tzinfo is None or local_now.utcoffset() is None:
        return {"status": "UNREADY", "saved_fields": [], "reason": "采集时间必须带来源时区"}
    local_now = local_now.astimezone(_TZ)
    if not _in_continuous_session(local_now):
        return {"status": "NOT_SESSION", "saved_fields": [], "reason": "仅在A股连续竞价时采集全市场快照"}
    root_path = Path(root).resolve()
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(root_path / "config" / "ipo_sentiment.yaml")
        )
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool

        if not TDXGlobalCachePool.is_trading_day(local_now.date().isoformat()):
            return {"status": "NOT_SESSION", "saved_fields": [], "reason": "TDX交易日历判定非交易日"}
        ipo_codes, listing_dates = _recent_ipo_metadata(local_now)
        api = _connect_background_api()
        try:
            universe = _load_or_refresh_universe(root_path, api, local_now)
            quotes = _quote_chunks(api, universe)
            no_limit = _no_limit_codes(api, listing_dates, local_now)
        finally:
            try:
                api.disconnect()
            except Exception:
                pass
        universe_codes = {str(row["code"]) for row in universe}
        quote_map = {str(row.get("code") or "").zfill(6): row for row in quotes}
        quote_times: List[datetime] = []
        fresh_quotes: List[Dict[str, Any]] = []
        for code, quote in quote_map.items():
            if code not in universe_codes:
                continue
            source_time = _quote_datetime(quote.get("servertime"), local_now)
            if source_time is None:
                continue
            age_seconds = (local_now - source_time).total_seconds()
            if age_seconds < -5 or age_seconds > _QUOTE_TTL_SECONDS:
                continue
            quote_times.append(source_time)
            fresh_quotes.append(quote)
        coverage = len(fresh_quotes) / max(1, len(universe))
        if coverage < 0.95:
            return {
                "status": "UNREADY", "saved_fields": [], "quote_count": len(fresh_quotes),
                "universe_count": len(universe), "coverage_ratio": coverage,
                "reason": "TDX全市场有效源时间覆盖低于95%",
            }
        if not quote_times or (max(quote_times) - min(quote_times)).total_seconds() > _MAX_CROSS_SECTION_SECONDS:
            return {"status": "UNREADY", "saved_fields": [], "reason": "全市场快照时间跨度超限"}
        as_of = min(quote_times).isoformat(timespec="seconds")
        metrics = derive_market_metrics(
            fresh_quotes, ipo_codes=ipo_codes, no_limit_codes=no_limit,
        )
        candidates = {
            "advance_decline_ratio": (metrics.get("advance_decline_ratio"), _SOURCE_ID, _SOURCE_VERSION),
            "high_volatility_amount_share": (metrics.get("high_volatility_amount_share"), _SOURCE_ID, _SOURCE_VERSION),
            "ipo_amount_share": (metrics.get("ipo_amount_share"), _SOURCE_ID, _SOURCE_VERSION),
            "limit_down_count": (metrics.get("limit_down_count"), "market_sentiment_fsm.board_aware_limit_down", "board_limit_down.v1"),
        }
        saved: List[str] = []
        rejected: List[str] = []
        available_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for field_id, (value, source_id, version) in candidates.items():
            if value is None:
                rejected.append(field_id)
                continue
            observation = {
                "status": "OBSERVED", "value": value,
                "source_id": source_id, "source_version": version,
                "source_timezone": _TZ_NAME, "as_of_time": as_of,
                "available_at": available_at,
            }
            if store_observation(
                root_path, ticker="000000", field_id=field_id,
                observation=observation, config=config,
            ):
                saved.append(field_id)
            else:
                rejected.append(field_id)
        return {
            "status": "READY" if saved else "UNREADY", "saved_fields": saved,
            "rejected_fields": rejected, "as_of_time": as_of,
            "quote_count": len(fresh_quotes), "universe_count": len(universe),
            "coverage_ratio": coverage, "metrics": metrics,
        }
    except Exception as exc:
        return {
            "status": "UNREADY", "saved_fields": [],
            "reason": "TDX全市场快照采集失败: " + type(exc).__name__,
        }

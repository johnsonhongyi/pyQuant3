"""Bounded Eastmoney collectors for IPO facts, market breadth and intraday bars.

Collectors run outside the trading loop. Every observation carries source time,
availability time, source identity and timezone; unsupported inputs stay UNREADY.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_source_orchestrator import store_observation


_DATA_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_LIMIT_UP_POOL_URL = "https://push2ex.eastmoney.com/{}"
_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q={market}{ticker}"
_TZ = "Asia/Shanghai"
_IPO_ID = "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY"
_IPO_VERSION = "ipo_calendar.v1"
_ISSUE_ID = "eastmoney.ipo_issuance_results"
_ISSUE_VERSION = "RPTA_APP_IPOAPPLY.all.v1"
_QUOTE_ID = "eastmoney.push2.stock_quote"
_QUOTE_VERSION = "stock_quote.v1"
_TENCENT_QUOTE_ID = "tencent.quote_snapshot"
_TENCENT_QUOTE_VERSION = "gtimg_hq.v1"
_BREADTH_ID = "eastmoney.push2.market_quotes"
_BREADTH_VERSION = "a_share_breadth.v1"
_MINUTE_ID = "eastmoney.push2his.minute_kline"
_MINUTE_VERSION = "minute_kline.v1"
_TDX_INDEX_ID = "tdx.daily_index_kline"
_TDX_INDEX_VERSION = "sh_sz_index_turnover.v1"
_TDX_RELATIVE_ID = "tdx.index_relative_strength"
_TDX_RELATIVE_VERSION = "sh_comp_vs_sz_comp_20d.v1"
_MARGIN_ID = "eastmoney.datacenter-web.RPTA_RZRQ_LSHJ"
_MARGIN_VERSION = "marketwide_margin_daily.v1"
_IPO_COLUMNS = (
    "SECURITY_CODE,SECURITY_NAME,ISSUE_PRICE,AFTER_ISSUE_PE,INDUSTRY_NAME,"
    "INDUSTRY_CODE,ONLINE_ES_MULTIPLE,ONLINE_ISSUE_NUM,ONLINE_VA_SHARES,"
    "ONLINE_VA_NUM,TOTAL_ISSUE_NUM,TOTAL_SHARES,UP_DATE,APPLY_DATE,LISTING_DATE"
)
_A_SHARE_PREFIXES = (
    "000", "001", "002", "003", "300", "301", "600", "601", "603",
    "605", "688", "689", "43", "83", "87", "88", "92",
)
_MARKET_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81"
_MARKET_FIELDS = "f12,f14,f2,f3,f9,f124,f100"
_MARKET_SNAPSHOT_FIELDS = "f12,f14,f2,f3,f6,f9,f124,f100"
_MARKET_METRICS_ID = "eastmoney.push2.market_quotes"
_MARKET_METRICS_VERSION = "a_share_turnover_metrics.v1"
_LIMIT_UP_POOL_ID = "eastmoney.push2ex.limit_up_pool"
_LIMIT_UP_POOL_VERSION = "eastmoney_limit_up_break.v1"


def _request_json(base_url: str, params: Mapping[str, Any], timeout: float = 8.0) -> Dict[str, Any]:
    is_quote_endpoint = base_url.startswith("https://push2")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "*/*",
        "Referer": "http://quote.eastmoney.com/" if is_quote_endpoint else "https://data.eastmoney.com/xg/",
    }
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(base_url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Eastmoney response is not an object")
    return payload


def fetch_issue_calendar_rows(page_size: int = 100) -> List[Dict[str, Any]]:
    """Fetch the newest issuance rows once, with the source's update timestamp."""
    payload = _request_json(_DATA_URL, {
        "reportName": "RPTA_APP_IPOAPPLY", "columns": _IPO_COLUMNS,
        "pageNumber": 1, "pageSize": max(1, min(int(page_size), 500)),
        "sortColumns": "APPLY_DATE", "sortTypes": -1,
        "source": "WEB", "client": "WEB",
    })
    result = payload.get("result") or {}
    rows = result.get("data") or []
    return [row for row in rows if isinstance(row, dict)]


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _error_summary(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return f"HTTP_{status_code}"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "东方财富主机连接被关闭或当前网络不允许访问该接口"
    if isinstance(exc, requests.exceptions.Timeout):
        return "东方财富接口请求超时"
    return type(exc).__name__


def _source_time(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(_TZ))
    return parsed.isoformat(timespec="seconds")


def _observation(value: Any, source_id: str, source_version: str, as_of: str) -> Dict[str, Any]:
    return {
        "status": "OBSERVED", "value": value, "source_id": source_id,
        "source_version": source_version, "source_timezone": _TZ,
        "as_of_time": as_of,
        "available_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch_ipo_row(ticker: str) -> Dict[str, Any]:
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        raise ValueError("股票代码必须为六位数字")
    filter_value = '(SECURITY_CODE="' + ticker + '")'
    payload = _request_json(_DATA_URL, {
        "reportName": "RPTA_APP_IPOAPPLY", "columns": _IPO_COLUMNS,
        "pageNumber": 1, "pageSize": 1, "filter": filter_value,
        "source": "WEB", "client": "WEB",
    })
    result = payload.get("result") or {}
    rows = result.get("data") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    return rows[0]


def fetch_tdx_float_shares(ticker: str) -> Dict[str, Any]:
    """Fetch TDX free-float shares only when the finance record has a dated update."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        return {}
    try:
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

        fetcher = TDXRealtimeFetcher.get_instance()
        with fetcher._conn_lock:
            if not fetcher._is_connected and not fetcher.connect():
                return {}
            if fetcher.api is None:
                return {}
            market = 1 if ticker.startswith("6") else 0
            info = fetcher.api.get_finance_info(market, ticker)
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    shares = _number(info.get("liutongguben"))
    updated = info.get("updated_date")
    if shares is None or shares <= 0 or isinstance(updated, bool):
        return {}
    try:
        day_text = str(int(updated))
        if len(day_text) != 8:
            return {}
        update_day = datetime.strptime(day_text, "%Y%m%d").date()
    except (TypeError, ValueError, OverflowError):
        return {}
    as_of = datetime.combine(update_day, dt_time(15, 0), ZoneInfo(_TZ))
    if as_of > datetime.now(ZoneInfo(_TZ)):
        return {}
    return {
        "value": shares / 10_000.0,
        "as_of_time": as_of.isoformat(timespec="seconds"),
        "updated_date": update_day.isoformat(),
    }


def collect_ipo_facts(root: str | Path, ticker: str) -> Dict[str, Any]:
    """Acquire only fields with unambiguous meanings in the IPO issuance record."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        row = fetch_ipo_row(ticker)
        as_of = _source_time(row.get("UP_DATE")) if row else None
        if not row or not as_of:
            return {"status": "UNREADY", "saved_fields": [], "reason": "发行记录或来源更新时间缺失"}
        issued_multiple = _number(row.get("ONLINE_ES_MULTIPLE"))
        candidates: Dict[str, Tuple[Any, str, str, str]] = {
            "issue_price": (_number(row.get("ISSUE_PRICE")), _IPO_ID, _IPO_VERSION, as_of),
            "pe_ratio": (_number(row.get("AFTER_ISSUE_PE")), _ISSUE_ID, _ISSUE_VERSION, as_of),
            "online_sub_multiple": (issued_multiple, _ISSUE_ID, _ISSUE_VERSION, as_of),
            "winning_rate_pct": (
                100.0 / issued_multiple if issued_multiple is not None and issued_multiple >= 1.0 else None,
                _ISSUE_ID, _ISSUE_VERSION, as_of,
            ),
        }
        finance = fetch_tdx_float_shares(ticker)
        if finance:
            candidates["float_shares_wan"] = (
                finance["value"], "tdx.finance_info", "pytdx.fin_info.v1",
                finance["as_of_time"],
            )
        saved: List[str] = []
        missing: List[str] = []
        for field_id, (value, source_id, source_version, source_as_of) in candidates.items():
            if value is None or value <= 0:
                missing.append(field_id)
                continue
            observation = _observation(value, source_id, source_version, source_as_of)
            if store_observation(
                root, ticker=ticker, field_id=field_id, observation=observation, config=config,
            ):
                saved.append(field_id)
            else:
                missing.append(field_id)
        if not finance:
            missing.append("float_shares_wan")
        return {
            "status": "READY" if saved else "UNREADY", "ticker": ticker,
            "saved_fields": saved, "missing_fields": missing,
            "industry_name": row.get("INDUSTRY_NAME"), "as_of_time": as_of,
            "issue_price": _number(row.get("ISSUE_PRICE")),
            "source_id": _IPO_ID, "source_version": "RPTA_APP_IPOAPPLY.ALL.v1",
        }
    except Exception as exc:
        return {"status": "UNREADY", "ticker": ticker, "saved_fields": [],
                "reason": "IPO采集失败: " + _error_summary(exc)}


def calculate_financing_balance_change(rows: Any, evaluation_day: date) -> Optional[Dict[str, Any]]:
    """Calculate the market-wide day-over-day financing-balance change in percent."""
    if not isinstance(rows, list):
        return None
    by_day: Dict[date, float] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            day = date.fromisoformat(str(row.get("DIM_DATE") or "")[:10])
        except ValueError:
            continue
        balance = _number(row.get("RZYE"))
        if day <= evaluation_day and balance is not None and balance > 0:
            by_day[day] = balance
    ordered = sorted(by_day.items())
    if len(ordered) < 2:
        return None
    previous_day, previous_balance = ordered[-2]
    latest_day, latest_balance = ordered[-1]
    return {
        "value": (latest_balance / previous_balance - 1.0) * 100.0,
        "latest_day": latest_day.isoformat(),
        "previous_day": previous_day.isoformat(),
        "latest_balance": latest_balance,
    }


def collect_financing_balance_change(root: str | Path) -> Dict[str, Any]:
    """Acquire exchange-reported aggregate margin-financing balances and persist the daily change."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        payload = _request_json(_DATA_URL, {
            "reportName": "RPTA_RZRQ_LSHJ", "columns": "ALL", "source": "WEB",
            "sortColumns": "DIM_DATE", "sortTypes": "-1", "pageNumber": 1, "pageSize": 5,
        })
        result = payload.get("result") if isinstance(payload, Mapping) else None
        rows = result.get("data") if isinstance(result, Mapping) else None
        now = datetime.now(ZoneInfo(_TZ))
        change = calculate_financing_balance_change(rows, now.date())
        if not change:
            return {"status": "UNREADY", "saved_fields": [], "reason": "两融汇总缺少两个有效交易日"}
        as_of = datetime.combine(
            date.fromisoformat(change["latest_day"]), dt_time(15, 0), ZoneInfo(_TZ)
        ).isoformat(timespec="seconds")
        saved = store_observation(
            root, ticker="000000", field_id="financing_balance_change",
            observation=_observation(
                change["value"], _MARGIN_ID, _MARGIN_VERSION, as_of,
            ),
            config=config,
        )
        return {
            "status": "READY" if saved else "UNREADY",
            "saved_fields": ["financing_balance_change"] if saved else [],
            "rejected_fields": [] if saved else ["financing_balance_change"],
            "latest_day": change["latest_day"], "previous_day": change["previous_day"],
            "change_pct": change["value"],
            "reason": "" if saved else "最新两融日数据未通过字段TTL或来源契约",
        }
    except Exception as exc:
        return {"status": "UNREADY", "saved_fields": [],
                "reason": "融资余额采集失败: " + _error_summary(exc)}


def collect_listing_supply_pace(root: str | Path, lookahead_days: int = 20) -> Dict[str, Any]:
    """Count IPOs with an announced listing date in the next 20 calendar days."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        rows = fetch_issue_calendar_rows(page_size=500)
        today = datetime.now(ZoneInfo(_TZ)).date()
        end_day = today.fromordinal(today.toordinal() + max(1, min(int(lookahead_days), 60)))
        listing_codes = set()
        source_times = []
        for row in rows:
            ticker = str(row.get("SECURITY_CODE") or "").strip().zfill(6)
            source_time = _source_time(row.get("UP_DATE"))
            if source_time:
                source_times.append(source_time)
            raw_date = str(row.get("LISTING_DATE") or "")[:10]
            try:
                listing_day = datetime.fromisoformat(raw_date).date()
            except ValueError:
                continue
            if ticker.isdigit() and today <= listing_day <= end_day:
                listing_codes.add(ticker)
        if not source_times:
            return {"status": "UNREADY", "saved_fields": [],
                    "reason": "发行日历没有带更新时间的近20日上市计划"}
        as_of = max(source_times)
        value = len(listing_codes)
        saved = store_observation(
            root, ticker="000000", field_id="listing_supply_pace",
            observation=_observation(value, "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY",
                                     "ipo_listing_supply.v1", as_of), config=config,
        )
        return {
            "status": "READY" if saved else "UNREADY",
            "saved_fields": ["listing_supply_pace"] if saved else [],
            "lookahead_days": (end_day - today).days,
            "announced_listings": value, "as_of_time": as_of,
            "reason": "" if saved else "上市供给数据未通过字段来源/时区/TTL契约",
        }
    except Exception as exc:
        return {"status": "UNREADY", "saved_fields": [],
                "reason": "上市供给采集失败: " + _error_summary(exc)}


def build_listing_anchors_from_bars(
    ticker: str, listing_date: str, bars: List[Mapping[str, Any]], float_shares_wan: float,
) -> Dict[str, Any]:
    """Derive immutable D0 anchors only from a complete, timestamped 240-minute session."""
    from ats.strategy.listing_anchor_store import ListingAnchors

    day = date.fromisoformat(listing_date)
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        raise ValueError("锚点标的代码无效")
    if not isinstance(float_shares_wan, (int, float)) or isinstance(float_shares_wan, bool):
        raise ValueError("缺少可信流通股本")
    if not math.isfinite(float(float_shares_wan)) or float(float_shares_wan) <= 0:
        raise ValueError("流通股本必须为正有限数值")
    expected: List[str] = []
    for start, end in ((9 * 60 + 31, 11 * 60 + 30), (13 * 60 + 1, 15 * 60)):
        expected.extend(
            (datetime.combine(day, dt_time()) + timedelta(minutes=minute)).strftime("%Y-%m-%d %H:%M")
            for minute in range(start, end + 1)
        )
    if not isinstance(bars, list) or len(bars) != len(expected):
        raise ValueError("首日分钟线必须覆盖完整240个连续竞价分钟")
    normalized: List[Dict[str, float]] = []
    observed_times: List[str] = []
    for bar in bars:
        if not isinstance(bar, Mapping):
            raise ValueError("首日分钟线格式无效")
        timestamp = str(bar.get("time", ""))
        try:
            parsed_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
            values = {key: float(bar[key]) for key in ("open", "high", "low", "close", "volume", "amount")}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("首日分钟线时间或数值缺失") from exc
        if parsed_time.date() != day or any(not math.isfinite(value) for value in values.values()):
            raise ValueError("首日分钟线含错日或非有限数值")
        if (
            min(values[key] for key in ("open", "high", "low", "close")) <= 0
            or values["volume"] < 0 or values["amount"] < 0
            or values["low"] > min(values["open"], values["close"])
            or values["high"] < max(values["open"], values["close"])
        ):
            raise ValueError("首日分钟线 OHLC/成交量校验失败")
        observed_times.append(timestamp)
        normalized.append(values)
    if observed_times != expected:
        raise ValueError("首日分钟线存在缺口、重复或时序错位")

    total_volume = sum(row["volume"] for row in normalized)
    total_amount = sum(row["amount"] for row in normalized)
    first_volume = sum(row["volume"] for row in normalized[:30])
    first_amount = sum(row["amount"] for row in normalized[:30])
    if total_volume <= 0 or total_amount <= 0 or first_volume <= 0 or first_amount <= 0:
        raise ValueError("首日成交额或前30分钟成交量无效")
    session_high = max(row["high"] for row in normalized)
    session_low = min(row["low"] for row in normalized)
    session_open = normalized[0]["open"]
    session_close = normalized[-1]["close"]
    session_vwap = total_amount / (total_volume * 100.0)
    first_vwap = first_amount / (first_volume * 100.0)
    span = session_high - session_low
    if span <= 0 or not session_low <= session_open <= session_high or not session_low <= session_close <= session_high:
        raise ValueError("首日高低价范围无效")
    anchors = ListingAnchors(
        code=ticker, listing_date=listing_date, listing_open=session_open,
        listing_high=session_high, listing_low=session_low, listing_close=session_close,
        listing_vwap=session_vwap, listing_anchored_vwap=session_vwap,
        first_30m_vwap=first_vwap, close_location=(session_close - session_low) / span,
        first_day_turnover=total_volume / float(float_shares_wan),
    )
    return anchors.__dict__


def collect_listing_day_anchors(root: str | Path, ticker: str) -> Dict[str, Any]:
    """Freeze D0 anchors after close when source coverage and float-share evidence pass."""
    from dataclasses import replace
    from ats.strategy.listing_anchor_store import ListingAnchorStore, ListingAnchors

    now = datetime.now(ZoneInfo(_TZ))
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        if not config.verify_integrity():
            return {"status": "UNREADY", "reason": "IPO配置哈希校验失败"}
        row = fetch_ipo_row(ticker)
        listing_date = str(row.get("LISTING_DATE") or "")[:10]
        if not listing_date:
            return {"status": "UNREADY", "reason": "发行日历缺少上市日期"}
        store = ListingAnchorStore(Path(root).resolve() / "config" / "listing_anchors.json")
        existing = store.get(ticker, listing_date)
        if existing is not None:
            return {"status": "ALREADY_FROZEN", "ticker": ticker, "listing_date": listing_date}
        if listing_date != now.date().isoformat():
            return {"status": "NOT_D0", "ticker": ticker, "listing_date": listing_date}
        if (now.hour, now.minute) < (15, 5):
            return {"status": "WAITING_CLOSE", "ticker": ticker, "listing_date": listing_date}

        finance = fetch_tdx_float_shares(ticker)
        if not finance:
            return {"status": "UNREADY", "ticker": ticker, "reason": "TDX未提供带日期的首日流通股本"}
        finance_observation = _observation(
            finance["value"], "tdx.finance_info", "pytdx.fin_info.v1", finance["as_of_time"]
        )
        finance_check = config.data_contract.validate_observation(
            "float_shares_wan", finance_observation, datetime.now(timezone.utc)
        )
        if not finance_check.usable:
            return {"status": "UNREADY", "ticker": ticker,
                    "reason": "流通股本未通过来源/时区/TTL校验: " + finance_check.reason_code}
        bars = fetch_intraday_bars(ticker, listing_date)
        raw_anchors = ListingAnchors(**build_listing_anchors_from_bars(
            ticker, listing_date, bars, finance["value"]
        ))
        anchors = replace(
            raw_anchors,
            source_id="eastmoney.push2his.minute_kline+tdx.finance_info",
            source_version="minute_kline.v1+pytdx.fin_info.v1",
            source_timezone=_TZ,
            as_of_time=datetime.combine(date.fromisoformat(listing_date), dt_time(15, 0), ZoneInfo(_TZ)).isoformat(timespec="seconds"),
            available_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            configuration_hash=config.config_hash,
            data_contract_hash=config.data_contract.config_hash,
        )
        store.freeze(anchors)
        return {
            "status": "FROZEN", "ticker": ticker, "listing_date": listing_date,
            "source_id": anchors.source_id, "source_timezone": anchors.source_timezone,
            "configuration_hash": anchors.configuration_hash,
            "data_contract_hash": anchors.data_contract_hash,
        }
    except Exception as exc:
        return {"status": "UNREADY", "ticker": ticker,
                "reason": "首日锚点采集失败: " + _error_summary(exc)}


def _is_a_share(code: Any) -> bool:
    text = str(code or "")
    return len(text) == 6 and text.isdigit() and text.startswith(_A_SHARE_PREFIXES)


def _normalize_industry(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "")
    for suffix in ("制造业", "行业"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    return text


def _fetch_market_rows() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    page_size = 5000
    payload = _request_json(_LIST_URL, {
        "pn": 1, "pz": page_size, "po": 1, "np": 1, "fltt": 2,
        "invt": 2, "fid": "f3", "fs": _MARKET_FS,
        "fields": _MARKET_SNAPSHOT_FIELDS, "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    })
    data = payload.get("data") or {}
    total = int(data.get("total") or 0)
    rows = list(data.get("diff") or [])
    pages = min(8, (total + page_size - 1) // page_size)
    for page in range(2, pages + 1):
        time.sleep(0.2)
        page_payload = _request_json(_LIST_URL, {
            "pn": page, "pz": page_size, "po": 1, "np": 1, "fltt": 2,
            "invt": 2, "fid": "f3", "fs": _MARKET_FS,
            "fields": _MARKET_SNAPSHOT_FIELDS, "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        })
        rows.extend(((page_payload.get("data") or {}).get("diff") or []))
    unique: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and _is_a_share(row.get("f12")):
            unique[str(row["f12"])] = row
    minimum_coverage = max(3000, math.ceil(total * 0.95))
    if len(unique) < minimum_coverage:
        raise ValueError("A股行情覆盖不足: " + str(len(unique)))
    times = sorted(item for item in (_number(row.get("f124")) for row in unique.values()) if item and item > 0)
    if len(times) < minimum_coverage or times[-1] - times[0] > 180:
        raise ValueError("A股报价时间覆盖不足或横截面跨度超过180秒")
    as_of = datetime.fromtimestamp(times[0], timezone.utc).isoformat(timespec="seconds") if times else None
    return list(unique.values()), as_of


def derive_market_turnover_metrics(
    rows: List[Mapping[str, Any]], *, ipo_codes: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Derive turnover-share fields from a complete, classified A-share quote set."""
    valid: List[Tuple[float, float, str, str]] = []
    for row in rows:
        amount = _number(row.get("f6"))
        change_pct = _number(row.get("f3"))
        code = str(row.get("f12") or "").strip().zfill(6)
        industry = _normalize_industry(row.get("f100"))
        if amount is None or amount <= 0 or change_pct is None or not _is_a_share(code):
            continue
        valid.append((amount, change_pct, code, industry))
    total_amount = sum(item[0] for item in valid)
    if total_amount <= 0 or len(valid) < 3000:
        return {"valid_amount_rows": len(valid), "reason": "有效成交额横截面不足"}

    metrics: Dict[str, Any] = {
        "valid_amount_rows": len(valid),
        "high_volatility_amount_share": sum(
            amount for amount, change, _code, _industry in valid if abs(change) >= 5.0
        ) / total_amount * 100.0,
    }
    if ipo_codes:
        quoted_ipo_codes = {code for _amount, _change, code, _industry in valid if code in ipo_codes}
        metrics["ipo_quote_coverage_pct"] = len(quoted_ipo_codes) / len(ipo_codes) * 100.0
        if len(quoted_ipo_codes) / len(ipo_codes) >= 0.95:
            ipo_amount = sum(amount for amount, _change, code, _industry in valid if code in ipo_codes)
            metrics["ipo_amount_share"] = ipo_amount / total_amount * 100.0
    sector_amounts: Dict[str, float] = {}
    for amount, _change, _code, industry in valid:
        if industry:
            sector_amounts[industry] = sector_amounts.get(industry, 0.0) + amount
    classified_amount = sum(sector_amounts.values())
    industry_coverage_pct = classified_amount / total_amount * 100.0
    metrics["industry_amount_coverage_pct"] = industry_coverage_pct
    if len(sector_amounts) >= 5 and industry_coverage_pct >= 95.0:
        metrics["theme_concentration"] = sum(
            (amount / classified_amount) ** 2 for amount in sector_amounts.values()
        ) * 10_000.0
        metrics["classified_industry_count"] = len(sector_amounts)
    return metrics


def _recently_listed_codes(now: datetime) -> set[str]:
    cutoff = now.astimezone(ZoneInfo(_TZ)).date() - timedelta(days=30)
    codes: set[str] = set()
    for row in fetch_issue_calendar_rows(page_size=500):
        code = str(row.get("SECURITY_CODE") or "").strip().zfill(6)
        try:
            listed = date.fromisoformat(str(row.get("LISTING_DATE") or "")[:10])
        except ValueError:
            continue
        if _is_a_share(code) and cutoff <= listed <= now.astimezone(ZoneInfo(_TZ)).date():
            codes.add(code)
    return codes


def collect_market_breadth_and_industry(
    root: str | Path, ticker: str, ipo_row: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Scrape paged A-share quotes; persist verified breadth and same-day industry PE median."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        rows, as_of = _fetch_market_rows()
        if not as_of:
            return {"status": "UNREADY", "saved_fields": [], "reason": "行情没有有效源时间戳"}
        as_of_utc = datetime.fromisoformat(as_of).astimezone(timezone.utc)
        quote_age_seconds = (datetime.now(timezone.utc) - as_of_utc).total_seconds()
        if quote_age_seconds < 0 or quote_age_seconds > 120:
            return {
                "status": "UNREADY", "saved_fields": [],
                "reason": f"全市场行情最老报价年龄{max(0, int(quote_age_seconds))}秒，超过120秒",
                "as_of_time": as_of,
            }
        advances = declines = 0
        industry_values: List[float] = []
        wanted_industry = _normalize_industry((ipo_row or {}).get("INDUSTRY_NAME"))
        for row in rows:
            change = _number(row.get("f3"))
            if change is not None:
                advances += change > 0
                declines += change < 0
            pe = _number(row.get("f9"))
            industry = _normalize_industry(row.get("f100"))
            if wanted_industry and industry == wanted_industry and pe is not None and pe > 0:
                industry_values.append(pe)
        if advances + declines < 2500:
            return {"status": "UNREADY", "saved_fields": [], "reason": "有效涨跌样本不足"}
        saved: List[str] = []
        breadth = advances / (advances + declines)
        if store_observation(
            root, ticker="000000", field_id="advance_decline_ratio",
            observation=_observation(breadth, _BREADTH_ID, _BREADTH_VERSION, as_of), config=config,
        ):
            saved.append("advance_decline_ratio")
        ipo_codes: set[str] = set()
        try:
            ipo_codes = _recently_listed_codes(datetime.now(ZoneInfo(_TZ)))
        except Exception:
            # IPO turnover is independently gated; the other broad-market metrics remain usable.
            pass
        turnover_metrics = derive_market_turnover_metrics(rows, ipo_codes=ipo_codes)
        turnover_sources = {
            "high_volatility_amount_share": _MARKET_METRICS_ID,
            "ipo_amount_share": _MARKET_METRICS_ID,
            "theme_concentration": _MARKET_METRICS_ID,
        }
        for field_id, source_id in turnover_sources.items():
            value = turnover_metrics.get(field_id)
            if value is None:
                continue
            if store_observation(
                root, ticker="000000", field_id=field_id,
                observation=_observation(
                    float(value), source_id, _MARKET_METRICS_VERSION, as_of,
                ), config=config,
            ):
                saved.append(field_id)
        if len(industry_values) >= 5:
            median_pe = float(statistics.median(industry_values))
            if store_observation(
                root, ticker=ticker, field_id="industry_pe_median",
                observation=_observation(median_pe, "eastmoney.push2.industry_valuation",
                                         "a_share_industry_pe.v1", as_of), config=config,
            ):
                saved.append("industry_pe_median")
        return {
            "status": "READY" if saved else "UNREADY", "saved_fields": saved,
            "a_share_rows": len(rows), "advances": advances, "declines": declines,
            "industry_sample_count": len(industry_values), "as_of_time": as_of,
            "turnover_metrics": turnover_metrics,
            "recent_ipo_count": len(ipo_codes),
            "quote_age_seconds": max(0, int(quote_age_seconds)),
            "reason": "未匹配至少5家同行PE样本" if wanted_industry and len(industry_values) < 5 else "",
        }
    except Exception as exc:
        return {"status": "UNREADY", "saved_fields": [],
                "reason": "市场横截面采集失败: " + _error_summary(exc)}


def _pool_codes(endpoint: str, requested_day: str) -> Tuple[Optional[str], set[str], Optional[int]]:
    payload = _request_json(_LIMIT_UP_POOL_URL.format(endpoint), {
        "ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt",
        "Pageindex": 0, "pagesize": 1000, "sort": "fbt:asc",
        "date": requested_day, "_": int(time.time() * 1000),
    })
    data = payload.get("data")
    if payload.get("rc") != 0 or not isinstance(data, dict):
        return None, set(), None
    qdate = str(data.get("qdate") or "")
    raw_pool = data.get("pool") or []
    total = data.get("tc")
    if not isinstance(raw_pool, list) or isinstance(total, bool) or not isinstance(total, int):
        return qdate or None, set(), None
    codes = {
        str(row.get("c") or "").strip().zfill(6)
        for row in raw_pool if isinstance(row, dict)
    }
    codes = {code for code in codes if len(code) == 6 and code.isdigit()}
    if total != len(codes):
        return qdate or None, set(), None
    return qdate or None, codes, total


def collect_limit_up_break_rate(root: str | Path) -> Dict[str, Any]:
    """Collect same-session Eastmoney sealed and broken limit-up pools."""
    try:
        now = datetime.now(ZoneInfo(_TZ))
        minute_now = now.hour * 60 + now.minute
        if not (570 <= minute_now <= 900):
            return {"status": "NOT_SESSION", "saved_fields": [], "reason": "仅在A股交易时段采集当日涨停/炸板池"}
        try:
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool

            if not TDXGlobalCachePool.is_trading_day(now.date().isoformat()):
                return {"status": "NOT_SESSION", "saved_fields": [], "reason": "交易日历判定今日非交易日"}
        except Exception:
            return {"status": "UNREADY", "saved_fields": [], "reason": "交易日历不可用"}
        requested_day = now.strftime("%Y%m%d")
        zt_day, zt_codes, zt_count = _pool_codes("getTopicZTPool", requested_day)
        zb_day, zb_codes, zb_count = _pool_codes("getTopicZBPool", requested_day)
        if zt_day != requested_day or zb_day != requested_day:
            return {"status": "UNREADY", "saved_fields": [], "reason": "涨停池日期不是当前交易日"}
        if zt_count is None or zb_count is None or not zt_codes | zb_codes:
            return {"status": "UNREADY", "saved_fields": [], "reason": "涨停池覆盖或行数校验失败"}
        overlap = zt_codes & zb_codes
        if overlap:
            return {
                "status": "UNREADY", "saved_fields": [],
                "reason": "涨停池与炸板池出现重叠，无法确定收盘状态",
                "overlap_count": len(overlap),
            }
        rate = zb_count / (zt_count + zb_count) * 100.0
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        as_of = now.isoformat(timespec="seconds")
        saved = store_observation(
            root, ticker="000000", field_id="limit_up_break_rate",
            observation=_observation(rate, _LIMIT_UP_POOL_ID, _LIMIT_UP_POOL_VERSION, as_of),
            config=config,
        )
        return {
            "status": "READY" if saved else "UNREADY",
            "saved_fields": ["limit_up_break_rate"] if saved else [],
            "sealed_count": zt_count, "broken_count": zb_count,
            "overlap_count": 0, "value_pct": rate, "as_of_time": as_of,
            "reason": "" if saved else "未通过来源/版本/时效契约",
        }
    except Exception as exc:
        return {
            "status": "UNREADY", "saved_fields": [],
            "reason": "涨停/炸板池采集失败: " + _error_summary(exc),
        }


def derive_index_relative_strength(
    shanghai_closes: Mapping[str, Any],
    shenzhen_closes: Mapping[str, Any],
    *,
    window: int = 20,
) -> Optional[float]:
    """Return 20-session SSE Composite minus SZSE Component cumulative return, in pct points."""
    if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
        return None
    common_days = sorted(set(shanghai_closes) & set(shenzhen_closes))
    if len(common_days) < window + 1:
        return None
    start_day, end_day = common_days[-window - 1], common_days[-1]
    sh_start, sh_end = _number(shanghai_closes[start_day]), _number(shanghai_closes[end_day])
    sz_start, sz_end = _number(shenzhen_closes[start_day]), _number(shenzhen_closes[end_day])
    if any(value is None or value <= 0 for value in (sh_start, sh_end, sz_start, sz_end)):
        return None
    return (sh_end / sh_start - sz_end / sz_start) * 100.0


def collect_tdx_market_history_fields(root: str | Path, ticker: str) -> Dict[str, Any]:
    """Derive broad-market turnover percentiles from dated SH/SZ index history."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

        fetcher = TDXRealtimeFetcher.get_instance()
        frames = {
            code: fetcher.fetch_kline_bars(code, category="day", count=70)
            for code in ("000001", "399001")
        }
        by_code: Dict[str, Dict[str, Dict[str, float]]] = {}
        for code, frame in frames.items():
            rows: Dict[str, Dict[str, float]] = {}
            if frame is None or frame.empty:
                return {"status": "UNREADY", "saved_fields": [], "reason": f"TDX指数日线缺失: {code}"}
            for _, row in frame.iterrows():
                day_text = str(row.get("datetime", row.get("time", "")))[:10]
                try:
                    date.fromisoformat(day_text)
                    amount = float(row["amount"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(amount) and amount > 0:
                    row_metrics = {"amount": amount}
                    close = _number(row.get("close"))
                    if close is not None and close > 0:
                        row_metrics["close"] = close
                    rows[day_text] = row_metrics
                    if code == "399001":
                        up, down = _number(row.get("up_count")), _number(row.get("down_count"))
                        if up is not None and down is not None and up >= 0 and down >= 0:
                            rows[day_text]["up_count"] = up
                            rows[day_text]["down_count"] = down
            by_code[code] = rows
        common_days = sorted(set(by_code["000001"]) & set(by_code["399001"]))
        if len(common_days) < 60:
            return {"status": "UNREADY", "saved_fields": [],
                    "reason": f"沪深指数共同有效日线不足60日: {len(common_days)}"}
        latest_day = common_days[-1]
        now_local = datetime.now(ZoneInfo(_TZ))
        if latest_day == now_local.date().isoformat() and now_local.hour < 15:
            common_days = common_days[:-1]
            if len(common_days) < 60:
                return {"status": "UNREADY", "saved_fields": [], "reason": "当日指数日线尚未收盘"}
            latest_day = common_days[-1]
        amounts = [by_code["000001"][day]["amount"] + by_code["399001"][day]["amount"] for day in common_days]
        latest_amount = amounts[-1]
        as_of = datetime.combine(date.fromisoformat(latest_day), datetime.strptime("15:00", "%H:%M").time(), ZoneInfo(_TZ)).isoformat(timespec="seconds")
        candidates: List[Tuple[str, float, str, str]] = []
        for window, field_id in ((20, "volume_percentile_20d"), (60, "volume_percentile_60d")):
            sample = amounts[-window:]
            candidates.append((field_id, sum(value <= latest_amount for value in sample) / len(sample), _TDX_INDEX_ID, _TDX_INDEX_VERSION))
        breadth = by_code["399001"][latest_day]
        breadth_total = breadth.get("up_count", 0.0) + breadth.get("down_count", 0.0)
        if breadth_total > 0:
            candidates.append(("advance_decline_ratio", breadth["up_count"] / breadth_total,
                               "tdx.daily_index_breadth", "index_up_down_count.v1"))
        relative_strength = derive_index_relative_strength(
            {day: row["close"] for day, row in by_code["000001"].items() if "close" in row},
            {day: row["close"] for day, row in by_code["399001"].items() if "close" in row},
        )
        if relative_strength is not None:
            candidates.append(("index_relative_strength", relative_strength,
                               _TDX_RELATIVE_ID, _TDX_RELATIVE_VERSION))
        saved: List[str] = []
        rejected: List[str] = []
        rejection_reasons: Dict[str, str] = {}
        for field_id, value, source_id, source_version in candidates:
            observation = _observation(value, source_id, source_version, as_of)
            check = config.data_contract.validate_observation(field_id, observation, datetime.now(timezone.utc))
            if check.usable and store_observation(
                root, ticker=ticker, field_id=field_id, observation=observation, config=config,
            ):
                saved.append(field_id)
            else:
                rejected.append(field_id)
                rejection_reasons[field_id] = check.reason_code or "observation_rejected"
        return {
            "status": "READY" if saved else "UNREADY", "saved_fields": saved,
            "rejected_fields": rejected, "common_sessions": len(common_days),
            "latest_session": latest_day, "as_of_time": as_of,
            "rejection_reasons": rejection_reasons,
            "reason": "" if saved else "最近沪深指数历史超出字段TTL或未通过来源契约",
        }
    except Exception as exc:
        return {"status": "UNREADY", "saved_fields": [],
                "reason": "TDX市场历史指标采集失败: " + _error_summary(exc)}


def _market_code(ticker: str) -> str:
    if ticker.startswith(("6",)):
        return "1"
    return "0"


def _quote_time(epoch: Any) -> Optional[str]:
    value = _number(epoch)
    if value is None or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def fetch_stock_quote(ticker: str) -> Dict[str, Any]:
    payload = _request_json(_QUOTE_URL, {
        "secid": _market_code(ticker) + "." + ticker,
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f124,f168,f170",
    })
    data = payload.get("data") or {}
    as_of = _quote_time(data.get("f124"))
    if not data or not as_of:
        return {}
    price = _number(data.get("f43"))
    return {
        "ticker": str(data.get("f57") or ticker), "name": data.get("f58"),
        "price": price / 1000.0 if price is not None else None,
        "high": (_number(data.get("f44")) or 0.0) / 1000.0,
        "low": (_number(data.get("f45")) or 0.0) / 1000.0,
        "open": (_number(data.get("f46")) or 0.0) / 1000.0,
        "previous_close": (_number(data.get("f60")) or 0.0) / 1000.0,
        "turnover_pct": (_number(data.get("f168")) or 0.0) / 100.0,
        "ret_pct": (_number(data.get("f170")) or 0.0) / 100.0,
        "as_of_time": as_of,
    }


def fetch_tencent_stock_quote(ticker: str) -> Dict[str, Any]:
    """Fetch Tencent's timestamped quote as an independent fallback provider."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        raise ValueError("股票代码必须为六位数字")
    market = "sh" if ticker.startswith("6") else "sz"
    url = _TENCENT_QUOTE_URL.format(market=market, ticker=ticker)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Referer": "https://gu.qq.com/",
        }, timeout=8.0)
        response.raise_for_status()
        response.encoding = "gb18030"
        payload = response.text
    if "=" not in payload:
        return {}
    body = payload.split("=", 1)[1].strip().strip(";\r\n \"")
    values = body.split("~")
    if len(values) <= 38 or values[2] != ticker:
        return {}
    try:
        local_time = datetime.strptime(values[30], "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo(_TZ))
    except (TypeError, ValueError):
        return {}

    def number_at(index: int) -> Optional[float]:
        return _number(values[index]) if index < len(values) else None

    volume_lots = number_at(6)
    amount_10k = number_at(37)
    vwap = (
        amount_10k * 100.0 / volume_lots
        if amount_10k is not None and volume_lots is not None and volume_lots > 0
        else None
    )
    return {
        "ticker": ticker, "name": values[1], "price": number_at(3),
        "previous_close": number_at(4), "open": number_at(5),
        "volume_lots": volume_lots, "amount_10k": amount_10k,
        "vwap": vwap, "ret_pct": number_at(32),
        "high": number_at(33), "low": number_at(34),
        "turnover_pct": number_at(38),
        "as_of_time": local_time.isoformat(timespec="seconds"),
        "provider": _TENCENT_QUOTE_ID,
    }


def fetch_intraday_bars(ticker: str, trade_date: str) -> List[Dict[str, Any]]:
    date_text = trade_date.replace("-", "")
    payload = _request_json(_KLINE_URL, {
        "secid": _market_code(ticker) + "." + ticker,
        "klt": 1, "fqt": 1, "beg": date_text, "end": date_text,
        "lmt": 1000, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    })
    raw_rows = ((payload.get("data") or {}).get("klines") or [])
    bars: List[Dict[str, Any]] = []
    for raw in raw_rows:
        parts = str(raw).split(",")
        if len(parts) < 7 or not parts[0].startswith(trade_date):
            continue
        values = [_number(item) for item in parts[1:7]]
        if any(item is None for item in values):
            continue
        bars.append({
            "time": parts[0], "open": values[0], "close": values[1],
            "high": values[2], "low": values[3], "volume": values[4],
            "amount": values[5],
        })
    return bars


def fetch_tdx_live_snapshot(ticker: str) -> Dict[str, Any]:
    """Use TDX only during a verified live session with a fresh latest minute bar."""
    now = datetime.now(ZoneInfo(_TZ))
    minute_now = now.hour * 60 + now.minute
    in_session = 9 * 60 + 30 <= minute_now <= 11 * 60 + 30 or 13 * 60 <= minute_now <= 15 * 60
    if not in_session:
        return {"status": "UNREADY", "reason": "当前不在A股连续竞价时段"}
    try:
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool, TDXRealtimeFetcher

        if not TDXGlobalCachePool.is_trading_day(now.date().isoformat()):
            return {"status": "UNREADY", "reason": "TDX交易日历判定今日非交易日"}
        fetcher = TDXRealtimeFetcher.get_instance()
        quote = fetcher.fetch_stock_snapshot(ticker)
        frame = fetcher.fetch_intraday_bars(ticker)
        if not quote or frame is None or frame.empty:
            return {"status": "UNREADY", "reason": "TDX未返回行情快照或分钟线"}
        last_time_text = str(frame.index[-1])[-5:]
        last_time = datetime.strptime(last_time_text, "%H:%M")
        last_minute = last_time.hour * 60 + last_time.minute
        age_minutes = minute_now - last_minute
        if age_minutes < -1 or age_minutes > 1:
            return {"status": "UNREADY", "reason": f"TDX最新分钟线{last_time_text}与当前时刻不匹配"}
        price = _number(quote.get("price"))
        previous_close = _number(quote.get("last_close"))
        high = _number(quote.get("high_price"))
        low = _number(quote.get("low_price"))
        vwap = _number(quote.get("vwap"))
        if not price or price <= 0 or not previous_close or previous_close <= 0:
            return {"status": "UNREADY", "reason": "TDX价格或昨收无效"}
        try:
            close_values = frame["close"].astype(float)
            vwap_values = frame["vwap"].astype(float)
            valid = close_values.notna() & vwap_values.notna() & (vwap_values > 0)
            minute_ratio = float((close_values[valid] > vwap_values[valid]).mean()) if valid.any() else None
        except (KeyError, TypeError, ValueError):
            minute_ratio = None
        circulation_wan = _number(fetcher.get_circulation_shares(ticker))
        volume_lots = _number(quote.get("volume"))
        turnover = volume_lots / circulation_wan if circulation_wan and circulation_wan > 0 and volume_lots is not None else None
        return {
            "status": "READY", "quote": {
                "ticker": ticker, "price": price, "previous_close": previous_close,
                "high": high, "low": low, "vwap": vwap,
                "ret_pct": (price / previous_close - 1.0) * 100.0,
                "turnover_pct": turnover,
                "as_of_time": now.isoformat(timespec="seconds"),
                "provider": "tdx.quote_snapshot",
            },
            "minute_ratio": minute_ratio, "minute_as_of_time": now.isoformat(timespec="seconds"),
            "minute_bars": len(frame), "last_bar_time": last_time_text,
        }
    except Exception as exc:
        return {"status": "UNREADY", "reason": "TDX实时备源采集失败: " + _error_summary(exc)}


def collect_live_metrics(root: str | Path, ticker: str, ipo_row: Mapping[str, Any]) -> Dict[str, Any]:
    """Collect timestamped quote and minute metrics outside the trading loop."""
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        try:
            quote = fetch_tencent_stock_quote(ticker)
        except Exception:
            quote = {}
        quote_source_id, quote_source_version = _TENCENT_QUOTE_ID, _TENCENT_QUOTE_VERSION
        quote_fresh = bool(quote and quote.get("price") is not None and config.data_contract.validate_observation(
            "current_price",
            _observation(quote.get("price"), quote_source_id, quote_source_version, quote.get("as_of_time", "")),
            datetime.now(timezone.utc),
        ).usable)
        tdx_data: Dict[str, Any] = {}
        if not quote_fresh:
            tdx_data = fetch_tdx_live_snapshot(ticker)
            if tdx_data.get("status") == "READY":
                quote = tdx_data["quote"]
                quote_source_id, quote_source_version = "tdx.quote_snapshot", "tdx_hq.quote.v1"
                quote_fresh = True
        if not quote or quote.get("price") is None:
            return {"status": "UNREADY", "saved_fields": [], "reason": "腾讯与TDX均未返回有效报价"}
        minute_ratio: Optional[float] = None
        minute_as_of = ""
        minute_source_id, minute_source_version = _MINUTE_ID, _MINUTE_VERSION
        minute_count = 0
        if tdx_data.get("status") == "READY":
            minute_ratio = tdx_data.get("minute_ratio")
            minute_as_of = tdx_data.get("minute_as_of_time", "")
            minute_source_id, minute_source_version = "tdx.minute_bars", "intraday_1m.v1"
            minute_count = int(tdx_data.get("minute_bars", 0))
        elif quote_fresh:
            trade_date = datetime.fromisoformat(quote["as_of_time"]).astimezone(ZoneInfo(_TZ)).date().isoformat()
            try:
                bars = fetch_intraday_bars(ticker, trade_date)
            except Exception:
                bars = []
            if bars:
                minute_as_of = datetime.strptime(bars[-1]["time"], "%Y-%m-%d %H:%M").replace(
                    tzinfo=ZoneInfo(_TZ)
                ).isoformat(timespec="seconds")
                cumulative_volume = cumulative_amount = 0.0
                above_vwap = 0
                for bar in bars:
                    cumulative_volume += bar["volume"]
                    cumulative_amount += bar["amount"]
                    minute_vwap = cumulative_amount / (cumulative_volume * 100.0) if cumulative_volume > 0 else 0.0
                    above_vwap += bar["close"] > minute_vwap
                minute_ratio = above_vwap / len(bars)
                minute_count = len(bars)
            else:
                tdx_data = fetch_tdx_live_snapshot(ticker)
                if tdx_data.get("status") == "READY":
                    minute_ratio = tdx_data.get("minute_ratio")
                    minute_as_of = tdx_data.get("minute_as_of_time", "")
                    minute_source_id, minute_source_version = "tdx.minute_bars", "intraday_1m.v1"
                    minute_count = int(tdx_data.get("minute_bars", 0))
        current_price = float(quote["price"])
        vwap = _number(quote.get("vwap")) or 0.0
        if quote_source_id == "tdx.quote_snapshot":
            vwap_source_id, vwap_source_version = "tdx.derived.quote_vwap", "tdx_quote_amount_volume.v1"
            peak_source_id, peak_source_version = "tdx.derived.session_peak_pullback", "tdx_quote_with_session_high.v1"
            premium_source_id, premium_source_version = "tdx.derived.issue_price_premium", "tdx_quote_plus_ipo.v1"
        else:
            vwap_source_id, vwap_source_version = "tencent.derived.quote_vwap", "quote_amount_volume.v1"
            peak_source_id, peak_source_version = "tencent.derived.quote_session_peak", "quote_with_session_high.v1"
            premium_source_id, premium_source_version = "tencent.derived.issue_price_premium", "quote_plus_ipo.v1"
        issue_price = _number(ipo_row.get("ISSUE_PRICE"))
        candidates: List[Tuple[str, Any, str, str, str]] = [
            ("ret_pct", quote.get("ret_pct"), quote_source_id, quote_source_version, quote["as_of_time"]),
            ("turnover_pct", quote.get("turnover_pct"), quote_source_id, quote_source_version, quote["as_of_time"]),
            ("current_price", current_price, quote_source_id, quote_source_version, quote["as_of_time"]),
            ("session_high", quote.get("high"), quote_source_id, quote_source_version, quote["as_of_time"]),
            ("session_low", quote.get("low"), quote_source_id, quote_source_version, quote["as_of_time"]),
            ("price_vwap_dist_pct", (current_price / vwap - 1.0) * 100.0 if vwap > 0 else None,
             vwap_source_id, vwap_source_version, quote["as_of_time"]),
            ("minutes_above_vwap_ratio", minute_ratio, minute_source_id, minute_source_version, minute_as_of),
            ("pullback_from_peak_pct", (current_price / quote["high"] - 1.0) * 100.0
             if _number(quote.get("high")) and _number(quote.get("high")) > 0 else None,
             peak_source_id, peak_source_version, quote["as_of_time"]),
        ]
        if issue_price is not None and issue_price > 0:
            candidates.append(("open_premium_pct", (current_price / issue_price - 1.0) * 100.0,
                               premium_source_id, premium_source_version, quote["as_of_time"]))
        saved: List[str] = []
        rejected: List[str] = []
        for field_id, value, source_id, source_version, as_of in candidates:
            if value is None or not math.isfinite(float(value)):
                rejected.append(field_id)
                continue
            if store_observation(
                root, ticker=ticker, field_id=field_id,
                observation=_observation(float(value), source_id, source_version, as_of),
                config=config,
            ):
                saved.append(field_id)
            else:
                rejected.append(field_id)
        return {
            "status": "READY" if saved else "UNREADY", "ticker": ticker,
            "saved_fields": saved, "rejected_fields": rejected,
            "minute_bars": minute_count, "vwap": vwap or None,
            "as_of_time": minute_as_of or quote["as_of_time"],
            "quote_provider": quote_source_id,
            "minute_status": "READY" if minute_count else "UNREADY",
        }
    except Exception as exc:
        return {"status": "UNREADY", "ticker": ticker, "saved_fields": [],
                "reason": "盘中行情采集失败: " + _error_summary(exc)}

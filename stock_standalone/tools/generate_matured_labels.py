# -*- coding: utf-8 -*-
"""Acquire verified post-listing daily bars and emit D1-D3 evidence for review."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ats.strategy.ipo_outcome_labels import build_matured_outcome  # noqa: E402
from ats.strategy.listing_anchor_store import ListingAnchorStore  # noqa: E402
from ats.strategy.ipo_eastmoney_sources import (  # noqa: E402
    _number, _source_time, _request_json, fetch_ipo_row, fetch_issue_calendar_rows,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
SOURCE_ID = "eastmoney.push2his.stock_kline"
SOURCE_VERSION = "daily_kline.raw.v1"
TDX_SOURCE_ID = "tdx.daily_kline"
TDX_SOURCE_VERSION = "pytdx.daily_bars.v1"


def _market_code(ticker: str) -> str:
    return "1" if ticker.startswith(("5", "6")) else "0"


def _fetch_daily_bars(
    ticker: str, listing_date: str, end_date: str | None = None,
) -> List[Dict[str, Any]]:
    bounded_end = date.fromisoformat(end_date) if end_date else datetime.now(SHANGHAI).date()
    payload = _request_json("https://push2his.eastmoney.com/api/qt/stock/kline/get", {
        "secid": f"{_market_code(ticker)}.{ticker}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101", "fqt": "0", "beg": listing_date.replace("-", ""),
        "end": bounded_end.strftime("%Y%m%d"), "lmt": "10",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }, timeout=8.0)
    raw = payload.get("data", {}).get("klines", []) if isinstance(payload, dict) else []
    bars = []
    for item in raw if isinstance(raw, list) else []:
        columns = str(item).split(",")
        if len(columns) < 5:
            continue
        try:
            bars.append({
                "date": columns[0][:10], "open": float(columns[1]),
                "close": float(columns[2]), "high": float(columns[3]),
                "low": float(columns[4]),
            })
        except (TypeError, ValueError, OverflowError):
            continue
    return bars


def _fetch_tdx_daily_bars(
    ticker: str, listing_date: str, count: int = 10, end_date: str | None = None,
) -> List[Dict[str, Any]]:
    """Fallback to TDX's date-stamped daily bars when Eastmoney history is unavailable."""
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 800:
        return []
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

    frame = TDXRealtimeFetcher.get_instance().fetch_kline_bars(
        ticker, category="day", count=count
    )
    if frame is None or frame.empty:
        return []
    bars = []
    for _, row in frame.iterrows():
        day_text = str(row.get("datetime", row.get("time", "")))[:10]
        try:
            day = date.fromisoformat(day_text)
            values = {key: float(row[key]) for key in ("open", "high", "low", "close")}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            day_text >= listing_date
            and (end_date is None or day_text <= end_date)
            and all(math.isfinite(value) and value > 0 for value in values.values())
        ):
            bars.append({"date": day_text, **values})
    return sorted({row["date"]: row for row in bars}.values(), key=lambda row: row["date"])


def _fetch_trading_sessions(start_date: str, end_date: str) -> List[Any]:
    """Read authoritative session dates from the configured A-share calendar."""
    try:
        from JohnsonUtil import commonTips as cct

        return list(cct.get_trade_days(start_date, end_date) or [])
    except Exception:
        return []


def collect_for_ticker(ticker: str, calendar: Any = None, root: str | Path = APP_ROOT) -> Dict[str, Any]:
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        return {"status": "UNREADY", "ticker": str(ticker), "reason": "股票代码必须为六位数字"}
    item = calendar.get(ticker, {}) if isinstance(calendar, dict) else {}
    if not item:
        try:
            item = fetch_ipo_row(ticker)
        except Exception as exc:
            return {"status": "UNREADY", "ticker": ticker, "reason": f"东方财富发行记录采集失败: {type(exc).__name__}"}
    listing_date = str(item.get("LISTING_DATE", item.get("listing_date", "")) or "")[:10]
    issue_price = _number(item.get("ISSUE_PRICE", item.get("issue_price")))
    source_meta = item.get("issue_price_source", {}) if isinstance(item, dict) else {}
    source_as_of = _source_time(item.get("UP_DATE")) if isinstance(item, dict) else None
    if source_as_of:
        source_meta = {
            "source_id": "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY",
            "source_version": "ipo_calendar.v1", "source_timezone": "Asia/Shanghai",
            "as_of_time": source_as_of,
            "available_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    if not listing_date or issue_price is None or issue_price <= 0:
        return {"status": "UNREADY", "ticker": ticker, "reason": "上市日或发行价未由新股日历确认"}
    calendar_sessions = _fetch_trading_sessions(
        listing_date, datetime.now(SHANGHAI).date().isoformat()
    )
    calendar_days = sorted({
        raw.date() if isinstance(raw, datetime) else (
            raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
        )
        for raw in calendar_sessions
    })
    listing_day = date.fromisoformat(listing_date)
    expected_d1_d3 = [day for day in calendar_days if day > listing_day][:3]
    bar_end_date = expected_d1_d3[-1].isoformat() if len(expected_d1_d3) == 3 else datetime.now(SHANGHAI).date().isoformat()
    try:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

        config = IPODecisionConfigSnapshot.from_yaml(str(Path(root).resolve() / "config" / "ipo_sentiment.yaml"))
        issue_check = config.data_contract.validate_observation("issue_price", {
            "status": "OBSERVED", "value": float(issue_price),
            "source_id": source_meta.get("source_id"),
            "source_version": source_meta.get("source_version"),
            "source_timezone": source_meta.get("source_timezone"),
            "as_of_time": source_meta.get("as_of_time"),
            "available_at": source_meta.get("available_at"),
        }, datetime.now(timezone.utc))
    except Exception:
        issue_check = None
    if not issue_check or not issue_check.usable:
        return {"status": "UNREADY", "ticker": ticker, "reason": "发行价来源/时区/TTL未通过版本化契约"}
    source_id, source_version = SOURCE_ID, SOURCE_VERSION
    try:
        bars = _fetch_daily_bars(ticker, listing_date, bar_end_date)
    except Exception:
        bars = []
    if not bars:
        try:
            listing_age = sum(day > listing_day for day in calendar_days)
            tdx_count = max(10, listing_age + 5)
            bars = _fetch_tdx_daily_bars(
                ticker, listing_date, count=tdx_count, end_date=bar_end_date
            )
            if bars:
                source_id, source_version = TDX_SOURCE_ID, TDX_SOURCE_VERSION
        except Exception:
            bars = []
    available_at = datetime.now(timezone.utc)
    latest_day = max((str(row["date"]) for row in bars), default="")
    if not latest_day:
        return {"status": "UNREADY", "ticker": ticker, "reason": "日线接口未返回有效 K 线"}
    as_of_time = datetime.combine(date.fromisoformat(latest_day), time(15, 0), SHANGHAI)
    anchors = None
    try:
        frozen = ListingAnchorStore(Path(root).resolve() / "config" / "listing_anchors.json").get(ticker, listing_date)
        if (
            frozen is not None
            and frozen.source_timezone == "Asia/Shanghai"
            and frozen.configuration_hash.lower() == config.config_hash.lower()
            and frozen.data_contract_hash.lower() == config.data_contract.config_hash.lower()
        ):
            anchors = {
                "listing_low": frozen.listing_low,
                "listing_anchored_vwap": frozen.listing_anchored_vwap,
            }
    except (OSError, ValueError, TypeError):
        pass
    evidence = build_matured_outcome(
        ticker=ticker, listing_date=listing_date, issue_price=float(issue_price),
        daily_bars=bars, source_id=source_id, source_version=source_version,
        source_timezone="Asia/Shanghai", as_of_time=as_of_time,
        available_at=available_at, anchors=anchors,
        trading_sessions=calendar_days,
    )
    if evidence.get("status") == "MATURED_PENDING_REVIEW":
        output = Path(root).resolve() / "data" / "ipo_learning" / "outcome_evidence" / f"{ticker}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp, output)
        evidence["evidence_path"] = str(output)
    return evidence


def collect_for_waiting_snapshots(root: str | Path = APP_ROOT, force: bool = False) -> List[Dict[str, Any]]:
    """Scan bounded WAITING_OUTCOME snapshots and collect one label per distinct ticker."""
    import time as time_module

    root_path = Path(root).resolve()
    now = datetime.now(SHANGHAI)
    if not force and now.time() < time(15, 30):
        return [{"status": "NOT_DUE", "reason": "D1-D3 盘后标签从 15:30 起采集"}]
    run_state = root_path / "data" / "ipo_learning" / "labels.last_run.json"
    if not force:
        try:
            previous = json.loads(run_state.read_text(encoding="utf-8"))
            if previous.get("date") == now.date().isoformat() and previous.get("status") == "DONE":
                return [{"status": "ALREADY_RUN", "reason": "今日盘后标签任务已完成"}]
        except (OSError, ValueError, AttributeError):
            pass
    path = root_path / "data" / "ipo_learning" / "decision_snapshots.sqlite"
    if not path.is_file():
        return [{"status": "NOT_STARTED", "reason": "尚无冻结决策快照"}]
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as connection:
            tickers = [row[0] for row in connection.execute(
                "SELECT DISTINCT ticker FROM decision_snapshots "
                "WHERE label_status='WAITING_OUTCOME' ORDER BY ticker LIMIT 100"
            )]
    except (OSError, sqlite3.Error):
        return [{"status": "UNREADY", "reason": "决策快照库不可读"}]
    if not tickers:
        reports = [{"status": "NO_PENDING", "reason": "没有待成熟快照"}]
        _save_label_run_state(run_state, now.date().isoformat())
        return reports
    reports = []
    for ticker in tickers:
        reports.append(collect_for_ticker(str(ticker), root=root_path))
        time_module.sleep(0.12)
    if all(report.get("status") in {"MATURED_PENDING_REVIEW", "PENDING_D3"} for report in reports):
        _save_label_run_state(run_state, now.date().isoformat())
    return reports


def collect_recent_ipo_cohort(
    root: str | Path = APP_ROOT, *, force: bool = False, batch_size: int = 20,
) -> List[Dict[str, Any]]:
    """Build review-only D1-D3 evidence for the complete recent IPO calendar cohort."""
    import time as time_module

    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
        return [{"status": "UNREADY", "reason": "队列批量大小必须在1至50之间"}]
    root_path = Path(root).resolve()
    now = datetime.now(SHANGHAI)
    if not force and now.time() < time(15, 30):
        return [{"status": "NOT_DUE", "reason": "全体新股D1-D3标签从15:30起采集"}]
    state_path = root_path / "data" / "ipo_learning" / "labels.cohort_state.json"
    report_path = root_path / "data" / "ipo_learning" / "labels.cohort.latest.json"
    try:
        saved_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        retry_after = saved_state.get("retry_after", {}) if isinstance(saved_state, dict) else {}
        if not isinstance(retry_after, dict):
            retry_after = {}
        rows = fetch_issue_calendar_rows(page_size=500)
    except Exception as exc:
        return [{"status": "UNREADY", "reason": f"新股队列日历不可用: {type(exc).__name__}"}]

    first_day = now.date() - timedelta(days=45)
    mature_cutoff = now.date() - timedelta(days=5)
    by_ticker: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("SECURITY_CODE") or "").strip().zfill(6)
        listing_text = str(row.get("LISTING_DATE") or "")[:10]
        try:
            listing_day = date.fromisoformat(listing_text)
        except ValueError:
            continue
        if (
            len(ticker) == 6 and ticker.isdigit()
            and first_day <= listing_day <= mature_cutoff
            and _number(row.get("ISSUE_PRICE")) is not None
            and _number(row.get("ISSUE_PRICE")) > 0
        ):
            by_ticker[ticker] = row

    evidence_dir = root_path / "data" / "ipo_learning" / "outcome_evidence"
    candidates = []
    for ticker, row in by_ticker.items():
        evidence_path = evidence_dir / f"{ticker}.json"
        if evidence_path.is_file():
            try:
                existing = json.loads(evidence_path.read_text(encoding="utf-8"))
                if (
                    isinstance(existing, dict)
                    and existing.get("ticker") == ticker
                    and existing.get("status") == "MATURED_PENDING_REVIEW"
                    and isinstance(existing.get("evidence_id"), str)
                    and existing.get("training_eligible") is False
                ):
                    retry_after.pop(ticker, None)
                    continue
            except (OSError, UnicodeError, ValueError):
                pass
        try:
            if date.fromisoformat(str(retry_after.get(ticker, "1900-01-01"))) > now.date():
                continue
        except (TypeError, ValueError):
            retry_after.pop(ticker, None)
        candidates.append((str(row.get("LISTING_DATE"))[:10], ticker, row))
    candidates.sort()

    reports: List[Dict[str, Any]] = []
    for _listing_day, ticker, row in candidates[:batch_size]:
        try:
            report = collect_for_ticker(ticker, calendar={ticker: row}, root=root_path)
        except Exception as exc:
            report = {"status": "UNREADY", "ticker": ticker, "reason": f"采集异常: {type(exc).__name__}"}
        reports.append(report)
        if report.get("status") in {"PENDING_D3", "UNREADY", "PENDING_D3_CLOSE"}:
            retry_after[ticker] = (now.date() + timedelta(days=1)).isoformat()
        else:
            retry_after.pop(ticker, None)
        time_module.sleep(0.12)

    matured = sum(item.get("status") == "MATURED_PENDING_REVIEW" for item in reports)
    summary = {
        "status": "COHORT_SCAN_COMPLETE" if reports or not candidates else "COHORT_RETRY_LATER",
        "scan_date": now.date().isoformat(),
        "calendar_candidates": len(by_ticker),
        "selected": min(len(candidates), batch_size),
        "matured_pending_review": matured,
        "retry_after": retry_after,
        "training_authorized": False,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in ((state_path, {"retry_after": retry_after}), (report_path, summary)):
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    reports.append(summary)
    if not reports[:-1]:
        reports[-1]["reason"] = "最近45日内没有待采集的成熟新股队列标的"
    return reports


def _save_label_run_state(path: Path, day: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"date": day, "status": "DONE"}, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="D1-D3 盘后标签证据生成（仅待人工复核，不进入训练）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", "-c", help="六位上市股票代码")
    group.add_argument("--scan-waiting", action="store_true", help="扫描待成熟的冻结决策快照")
    group.add_argument("--scan-cohort", action="store_true", help="按最新新股日历分批生成全体近期新股D1-D3证据")
    parser.add_argument("--force", action="store_true", help="忽略盘后时间与当日去重，手动重跑待成熟标签扫描")
    args = parser.parse_args()
    if args.code and (len(args.code) != 6 or not args.code.isdigit()):
        parser.error("--code 必须为六位数字")
    try:
        result = (
            collect_for_waiting_snapshots(force=args.force) if args.scan_waiting else
            collect_recent_ipo_cohort(force=args.force) if args.scan_cohort else
            collect_for_ticker(args.code)
        )
    except Exception as exc:
        result = {"status": "UNREADY", "ticker": args.code or "", "reason": f"采集异常: {type(exc).__name__}"}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    results = result if isinstance(result, list) else [result]
    statuses = {item.get("status") for item in results if isinstance(item, dict)}
    return 0 if statuses and statuses.issubset({
        "MATURED_PENDING_REVIEW", "PENDING_D3", "PENDING_D3_CLOSE", "NO_PENDING",
        "ALREADY_RUN",
        "NOT_STARTED", "NOT_DUE", "COHORT_SCAN_COMPLETE", "COHORT_RETRY_LATER",
    }) else 2


if __name__ == "__main__":
    raise SystemExit(main())

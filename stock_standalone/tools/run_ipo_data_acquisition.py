# -*- coding: utf-8 -*-
"""Bounded IPO source collector; it never invokes an LLM or authorizes trading."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, Callable, Dict, Optional

try:
    from sys_utils import get_app_root, safe_resolve_path
    APP_ROOT = safe_resolve_path(get_app_root())
except Exception:
    try:
        APP_ROOT = Path(__file__).resolve().parents[1]
    except OSError:
        APP_ROOT = Path(__file__).absolute().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot  # noqa: E402
from ats.strategy.ipo_source_orchestrator import (  # noqa: E402
    SOURCE_DB_RELATIVE_PATH,
    collect_issue_prices_from_ats_cache,
    collect_market_pulse_fields,
    collect_source_readiness,
)
from ats.strategy.ipo_eastmoney_sources import (  # noqa: E402
    collect_ipo_facts,
    collect_financing_balance_change,
    collect_listing_day_anchors,
    collect_listing_supply_pace,
    collect_live_metrics,
    collect_market_breadth_and_industry,
    collect_tdx_market_history_fields,
    collect_limit_up_break_rate,
)
from ats.strategy.tdx_market_snapshot import collect_tdx_market_snapshot_fields

_ATS_COLD_START_ATTEMPTED_ROOTS: set[str] = set()
_ATS_DAILY_SOURCE_REFRESH_DATES: Dict[str, str] = {}
_SOURCE_BOOTSTRAP_SCHEMA = "ipo.source-bootstrap.v1"


def _write_latest_report(report: Dict[str, Any], root: Path) -> None:
    path = root / "data" / "ipo_learning" / "acquisition.latest.json"
    temporary = path.with_suffix(".json.tmp")
    report["report_persistence"] = {"status": "SAVED", "path": str(path)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as exc:
        report["report_persistence"] = {"status": "FAILED", "reason": type(exc).__name__}


def _static_history_frame(code: str) -> tuple[Any, str, str]:
    """Read cached multi-day bars or local TDX daily bars without making a network request."""
    import pandas as pd

    from ats.tdx_realtime_fetcher import TDXGlobalCachePool

    # Do not initialize TDXRealtimeFetcher here: its constructor probes live servers.
    # The cache-pool singleton only reads the local RamDisk snapshot.
    try:
        pool = TDXGlobalCachePool.get_instance()
    except Exception:
        pool = None
    if pool is not None:
        try:
            cached = pool.get_incremental_intraday(
                code, days=10, ttl=86400.0, requested_days=10,
            )
            if cached and isinstance(cached[0], pd.DataFrame) and not cached[0].empty:
                return cached[0].copy(), "TDX RamDisk 多日分时缓存", "1m"
        except Exception:
            pass
        for days in (10, 9, 8, 5, 1):
            try:
                entry = pool.get_static_history_bars(
                    code, days=days, requested_days=10,
                )
                records = entry.get("records") if isinstance(entry, dict) else None
                if records:
                    return pd.DataFrame(list(records)), "TDX RamDisk 静态分时缓存", "1m"
            except Exception:
                continue

    try:
        from JSONData import tdx_data_Day as tdd

        daily = tdd.get_tdx_Exp_day_to_df(code, dl=70, fastohlc=True)
        if isinstance(daily, pd.DataFrame) and not daily.empty:
            return daily.copy(), "本地通达信日线文件", "1d"
    except Exception:
        pass
    return pd.DataFrame(), "", ""


def _static_universe_tickers(stocks: Any) -> list[str]:
    """Return the same listed ATS symbols that the AUTO queue will process."""
    try:
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        rows = stocks.to_dict("records")
    except Exception:
        return []
    tickers = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("status") or "") == "待上市":
            continue
        ticker = str(row.get("code") or "").strip()
        if len(ticker) != 6 or not ticker.isdigit():
            continue
        try:
            listing_day = datetime.strptime(str(row.get("listing_date") or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if listing_day <= today:
            tickers.add(ticker)
    return sorted(tickers)


def _static_universe_count(stocks: Any) -> int:
    return len(_static_universe_tickers(stocks))


def _analyze_static_ipo_history_raw(code: str) -> Dict[str, Any]:
    """Derive a read-only historical IPO snapshot from local cached bars only."""
    try:
        import pandas as pd

        frame, source, granularity = _static_history_frame(code)
        if frame is None or frame.empty:
            return {"status": "NO_CACHED_HISTORY", "ticker": code,
                    "reason": "本机没有该标的多日分时缓存或本地日线文件"}
        frame = frame.copy()
        if "date" not in frame.columns:
            date_column = next((name for name in ("trade_date", "trading_day", "datetime", "timestamp")
                                if name in frame.columns), None)
            if date_column:
                frame.rename(columns={date_column: "date"}, inplace=True)
            else:
                index_name = frame.index.name or "date"
                frame = frame.reset_index().rename(columns={"index": index_name})
                if index_name != "date":
                    frame.rename(columns={index_name: "date"}, inplace=True)
        if "date" not in frame.columns:
            return {"status": "UNREADY", "ticker": code, "reason": "历史数据缺少日期字段"}
        raw_dates = frame["date"].astype(str)
        parsed_dates = pd.to_datetime(raw_dates.str.slice(0, 10), errors="coerce")
        compact_dates = pd.to_datetime(raw_dates.str.extract(r"(\d{8})", expand=False),
                                       format="%Y%m%d", errors="coerce")
        parsed_dates = parsed_dates.fillna(compact_dates)
        frame["_date"] = parsed_dates.dt.strftime("%Y-%m-%d")
        frame = frame[frame["_date"].notna()].copy()
        if frame.empty or "close" not in frame.columns:
            return {"status": "UNREADY", "ticker": code, "reason": "历史数据没有可用收盘价"}

        if "time_only" not in frame.columns:
            time_column = next((name for name in ("time", "datetime", "timestamp")
                                if name in frame.columns), None)
            if time_column:
                parsed_times = pd.to_datetime(frame[time_column], errors="coerce")
                frame["_time"] = parsed_times.dt.strftime("%H:%M:%S")
            else:
                frame["_time"] = "15:00:00"
        else:
            frame["_time"] = frame["time_only"].astype(str).str.slice(0, 8)
        if granularity == "1d":
            frame["_time"] = "15:00:00"
        frame["_close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["_open"] = pd.to_numeric(frame.get("open", frame["close"]), errors="coerce")
        volume_column = next((name for name in ("bar_vol", "volume", "vol")
                              if name in frame.columns), None)
        frame["_volume"] = pd.to_numeric(frame[volume_column], errors="coerce") if volume_column else 0.0
        frame["_vwap"] = pd.to_numeric(frame["vwap"], errors="coerce") if "vwap" in frame.columns else float("nan")
        frame = frame[(frame["_close"] > 0) & frame["_close"].notna()].sort_values(["_date", "_time"])
        if frame.empty:
            return {"status": "UNREADY", "ticker": code, "reason": "历史收盘价校验未通过"}

        daily = frame.groupby("_date", sort=True).agg(
            open=("_open", "first"), close=("_close", "last"), volume=("_volume", "sum"),
        )
        latest = frame.iloc[-1]
        latest_close = float(daily.iloc[-1]["close"])
        previous_close = float(daily.iloc[-2]["close"]) if len(daily) >= 2 else 0.0
        latest_change = (latest_close / previous_close - 1.0) * 100.0 if previous_close > 0 else None
        five_day_return = (
            (latest_close / float(daily.iloc[-6]["close"]) - 1.0) * 100.0
            if len(daily) >= 6 and float(daily.iloc[-6]["close"]) > 0 else None
        )
        previous_five_day_return = (
            (float(daily.iloc[-6]["close"]) / float(daily.iloc[-10]["open"]) - 1.0) * 100.0
            if len(daily) >= 10 and float(daily.iloc[-10]["open"]) > 0 else None
        )
        latest_vwap = float(latest["_vwap"]) if pd.notna(latest["_vwap"]) and latest["_vwap"] > 0 else None
        latest_day = str(daily.index[-1])
        latest_day_frame = frame[frame["_date"] == latest_day]
        vwap_rows = latest_day_frame[latest_day_frame["_vwap"] > 0]
        vwap_hold_ratio = (
            round(float((vwap_rows["_close"] >= vwap_rows["_vwap"]).mean()) * 100.0, 1)
            if not vwap_rows.empty else None
        )
        above_vwap = latest_vwap is not None and latest_close >= latest_vwap
        if five_day_return is not None and previous_five_day_return is not None:
            if five_day_return > 0 and previous_five_day_return > 0 and five_day_return > previous_five_day_return:
                multi_day_bias = "多日动能增强"
            elif five_day_return < 0 and previous_five_day_return < 0 and five_day_return < previous_five_day_return:
                multi_day_bias = "多日动能走弱"
            elif five_day_return * previous_five_day_return < 0:
                multi_day_bias = "多日趋势反转"
            else:
                multi_day_bias = "多日趋势整理"
        elif five_day_return is not None:
            multi_day_bias = "多日趋势偏强" if five_day_return > 0 else "多日趋势承压" if five_day_return < 0 else "多日横盘"
        else:
            multi_day_bias = "有效窗口不足6个交易日"
        if five_day_return is not None and latest_vwap is not None:
            sentiment = "HISTORICAL_BULLISH" if five_day_return > 0 and above_vwap else (
                "HISTORICAL_BEARISH" if five_day_return < 0 and not above_vwap else "HISTORICAL_MIXED"
            )
        elif five_day_return is not None:
            sentiment = "HISTORICAL_UPTREND" if five_day_return > 0 else (
                "HISTORICAL_DOWNTREND" if five_day_return < 0 else "HISTORICAL_RANGE"
            )
        else:
            sentiment = "HISTORICAL_INSUFFICIENT_WINDOW"
        as_of = latest_day + "T" + str(latest.get("_time") or "15:00:00")[:8]
        now_day = datetime.now().date()
        return {
            "status": "READY", "ticker": code, "source": source,
            "granularity": granularity, "session_count": int(len(daily)),
            "as_of_time": as_of, "calendar_age_days": max(0, (now_day - datetime.fromisoformat(latest_day).date()).days),
            "latest_close": round(latest_close, 4),
            "latest_change_pct": round(latest_change, 2) if latest_change is not None else None,
            "five_day_return_pct": round(five_day_return, 2) if five_day_return is not None else None,
            "previous_five_day_return_pct": round(previous_five_day_return, 2) if previous_five_day_return is not None else None,
            "latest_vwap": round(latest_vwap, 4) if latest_vwap is not None else None,
            "vwap_hold_ratio_pct": vwap_hold_ratio,
            "above_vwap": above_vwap if latest_vwap is not None else None,
            "multi_day_bias": multi_day_bias, "sentiment": sentiment,
            "trading_authorized": False,
        }
    except Exception as exc:
        return {"status": "UNREADY", "ticker": code,
                "reason": f"本地历史分析失败: {type(exc).__name__}: {str(exc)[:180]}"}


def _with_static_emotion_score(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Always return a numeric static score, visibly distinguishing baseline from evidence."""
    result = dict(analysis)
    feature_scores: Dict[str, float] = {}

    def add(name: str, value: Any, scale: float) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            feature_scores[name] = max(0.0, min(100.0, 50.0 + float(value) * scale))

    add("latest_change", result.get("latest_change_pct"), 2.0)
    add("five_day_return", result.get("five_day_return_pct"), 0.5)
    hold_ratio = result.get("vwap_hold_ratio_pct")
    if isinstance(hold_ratio, (int, float)) and not isinstance(hold_ratio, bool) and math.isfinite(float(hold_ratio)):
        feature_scores["vwap_hold"] = max(0.0, min(100.0, float(hold_ratio)))
    elif isinstance(result.get("above_vwap"), bool):
        feature_scores["above_vwap"] = 75.0 if result["above_vwap"] else 25.0

    weights = {"latest_change": 0.35, "five_day_return": 0.45, "vwap_hold": 0.20, "above_vwap": 0.20}
    if feature_scores:
        weight_total = sum(weights[name] for name in feature_scores)
        score = sum(feature * weights[name] for name, feature in feature_scores.items()) / weight_total
        quality = "MEASURED" if len(feature_scores) >= 2 else "LIMITED_HISTORY"
        result.update({
            "emotion_score": round(score, 1),
            "emotion_tier": "偏强" if score >= 60 else "偏弱" if score < 40 else "中性",
            "score_quality": quality,
            "score_basis": "STATIC_HISTORICAL_FEATURES",
            "score_is_baseline": False,
            "score_components": {name: round(value, 1) for name, value in feature_scores.items()},
        })
    else:
        result.update({
            "emotion_score": 50.0,
            "emotion_tier": "中性",
            "score_quality": "NO_EVIDENCE",
            "score_basis": "COLD_START_NEUTRAL_BASELINE",
            "score_is_baseline": True,
            "score_components": {},
        })
        result.setdefault("sentiment", "HISTORICAL_NEUTRAL_BASELINE")
    result["trading_authorized"] = False
    return result


def _analyze_static_ipo_history(code: str) -> Dict[str, Any]:
    return _with_static_emotion_score(_analyze_static_ipo_history_raw(code))


def _update_static_sentiment_snapshot(
    root: Path, ticker: str, analysis: Dict[str, Any], universe_count: int,
) -> Dict[str, Any]:
    """Persist per-symbol offline results and a clearly labeled historical cross-section."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    path = root / "data" / "ipo_learning" / "static_sentiment.latest.json"
    previous: Dict[str, Any] = {}
    try:
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("run_date") == now.date().isoformat():
                previous = loaded
    except (OSError, UnicodeError, ValueError, TypeError):
        previous = {}
    results = previous.get("results", {})
    results = dict(results) if isinstance(results, dict) else {}
    results = {
        str(key): _with_static_emotion_score(value)
        for key, value in results.items() if isinstance(value, dict)
    }
    results[ticker] = _with_static_emotion_score(analysis)
    available = [
        value for value in results.values()
        if isinstance(value, dict) and value.get("status") == "READY"
        and isinstance(value.get("latest_change_pct"), (int, float))
    ]
    trend_available = [
        value for value in available
        if isinstance(value.get("five_day_return_pct"), (int, float))
    ]
    vwap_available = [value for value in available if isinstance(value.get("above_vwap"), bool)]
    if available:
        change_values = [float(value["latest_change_pct"]) for value in available]
        red_ratio = sum(value > 0 for value in change_values) / len(change_values) * 100.0
        avg_change = sum(change_values) / len(change_values)
        vwap_hold_ratio = (
            sum(bool(value["above_vwap"]) for value in vwap_available) / len(vwap_available) * 100.0
            if vwap_available else None
        )
        if vwap_hold_ratio is not None:
            score = round(max(0.0, min(
                red_ratio * 0.35 + vwap_hold_ratio * 0.40 + min(avg_change * 3.0, 25.0), 100.0,
            )), 1)
            score_basis = "STATIC_INTRADAY_WITH_VWAP"
        elif trend_available:
            uptrend_ratio = sum(float(value["five_day_return_pct"]) > 0 for value in trend_available) / len(trend_available) * 100.0
            score = round(max(0.0, min(red_ratio * 0.55 + uptrend_ratio * 0.45, 100.0)), 1)
            score_basis = "STATIC_DAILY_TREND_NO_VWAP"
        else:
            score = round(red_ratio, 1)
            score_basis = "STATIC_DAILY_ADVANCE_DECLINE_ONLY"
        surge_count = sum(value >= 5.0 for value in change_values)
    else:
        red_ratio = avg_change = None
        vwap_hold_ratio = None
        surge_count = 0
    scored = [
        value for value in results.values()
        if isinstance(value, dict) and isinstance(value.get("emotion_score"), (int, float))
    ]
    measured_scores = [
        float(value["emotion_score"]) for value in scored
        if value.get("score_quality") in {"MEASURED", "LIMITED_HISTORY"}
    ]
    score = round(sum(measured_scores) / len(measured_scores), 1) if measured_scores else 50.0
    score_basis = "STATIC_PER_TICKER_EMOTION_SCORES" if measured_scores else "COLD_START_NEUTRAL_BASELINE"
    if not measured_scores:
        heat_stage = "历史情绪：无证据中性基线"
    elif score >= 80.0 or surge_count >= 8:
        heat_stage = "历史情绪：狂热区间"
    elif score >= 60.0 or (red_ratio is not None and red_ratio >= 65.0):
        heat_stage = "历史情绪：偏强区间"
    elif score >= 40.0:
        heat_stage = "历史情绪：整理区间"
    else:
        heat_stage = "历史情绪：偏弱区间"
    snapshot = {
        "schema_version": "ipo.static-sentiment.v1",
        "mode": "STATIC_HISTORICAL", "run_date": now.date().isoformat(),
        "updated_at": now.isoformat(timespec="seconds"),
        "processed_count": len(results), "universe_count": max(0, int(universe_count)),
        "cached_history_count": len(available),
        "missing_history_count": sum(
            isinstance(value, dict) and value.get("status") != "READY"
            for value in results.values()
        ),
        "red_ratio_pct": round(red_ratio, 1) if red_ratio is not None else None,
        "vwap_hold_ratio_pct": round(vwap_hold_ratio, 1) if vwap_hold_ratio is not None else None,
        "vwap_sample_count": len(vwap_available),
        "multi_day_trend_sample_count": len(trend_available),
        "average_latest_change_pct": round(avg_change, 2) if avg_change is not None else None,
        "surge_count": surge_count, "heat_score": score, "heat_stage": heat_stage,
        "score_quality": "MEASURED_CROSS_SECTION" if measured_scores else "NO_EVIDENCE",
        "score_sample_count": len(measured_scores),
        "baseline_score_count": sum(value.get("score_is_baseline") is True for value in scored),
        "score_coverage_pct": (
            round(len(scored) / int(universe_count) * 100.0, 1)
            if int(universe_count) > 0 else 0.0
        ),
        "score_basis": score_basis,
        "live_data_used": False, "runtime_authorized": False,
        "universe_scan": previous.get("universe_scan", {}),
        "results": results,
    }
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        snapshot["persistence"] = {"status": "FAILED", "reason": type(exc).__name__}
    return snapshot


def _complete_static_universe_snapshot(
    root: Path, stocks: Any, ticker: str, analysis: Dict[str, Any],
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Resume a local-only cold-start sweep until every listed ATS symbol has a score."""
    codes = _static_universe_tickers(stocks)
    path = root / "data" / "ipo_learning" / "static_sentiment.latest.json"
    from zoneinfo import ZoneInfo
    local_day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    prior_scan: Dict[str, Any] = {}
    try:
        if path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
            prior = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(prior, dict) and prior.get("run_date") == local_day:
                value = prior.get("universe_scan")
                prior_scan = value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError, TypeError):
        prior_scan = {}
    scan_is_current = (
        prior_scan.get("status") == "COMPLETE"
        and prior_scan.get("scorer_version") == 1
        and prior_scan.get("universe_codes") == codes
    )
    snapshot = _update_static_sentiment_snapshot(root, ticker, analysis, len(codes))
    results = snapshot.get("results", {})
    results = results if isinstance(results, dict) else {}
    pending = codes if not scan_is_current else [
        code for code in codes
        if not isinstance(results.get(code), dict)
        or not isinstance(results[code].get("emotion_score"), (int, float))
    ]

    def emit(stage: str, message: str, status: str, event_ticker: str = "") -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({
                "stage": stage, "message": message, "status": status,
                "ticker": event_ticker or ticker,
            })
        except Exception:
            pass

    emit(
        "STATIC_UNIVERSE_SWEEP",
        f"ATS已上市名单 {len(codes)} 只；已有评分 {len(codes) - len(pending)}，本轮补算 {len(pending)} 只本地历史",
        "RUNNING" if pending else "DONE",
    )
    for index, code in enumerate(pending, 1):
        item = _analyze_static_ipo_history(code)
        snapshot = _update_static_sentiment_snapshot(root, code, item, len(codes))
        emit(
            "STATIC_UNIVERSE_ITEM",
            f"{code} 本地历史情绪 {index}/{len(pending)}；评分 {item['emotion_score']}/100 "
            f"({item['score_quality']})；{item.get('sentiment', item.get('status'))}",
            "DONE", code,
        )

    results = snapshot.get("results", {})
    results = results if isinstance(results, dict) else {}
    scored_count = sum(
        isinstance(results.get(code), dict)
        and isinstance(results[code].get("emotion_score"), (int, float))
        for code in codes
    )
    measured_count = sum(
        isinstance(results.get(code), dict)
        and results[code].get("score_quality") in {"MEASURED", "LIMITED_HISTORY"}
        for code in codes
    )
    snapshot["universe_scan"] = {
        "status": "COMPLETE" if codes and scored_count == len(codes) else "NO_UNIVERSE" if not codes else "PARTIAL",
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "processed_count": scored_count, "universe_count": len(codes),
        "measured_count": measured_count, "baseline_count": max(0, scored_count - measured_count),
        "remaining_count": max(0, len(codes) - scored_count),
        "scorer_version": 1, "universe_codes": codes,
    }
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        snapshot["persistence"] = {"status": "SAVED", "path": str(path)}
    except OSError as exc:
        snapshot["persistence"] = {"status": "FAILED", "reason": type(exc).__name__}
    emit(
        "STATIC_UNIVERSE_SWEEP",
        f"静态横截面扫描完成：评分 {scored_count}/{len(codes)}，实测 {measured_count}，中性基线 {max(0, scored_count - measured_count)}",
        "DONE" if scored_count == len(codes) else "FAILED",
    )
    return snapshot


def _gate_data_bridge(root: Path) -> Dict[str, Any]:
    """Describe the shared store and ATS reader without claiming Gate readiness."""
    store_path = root / SOURCE_DB_RELATIVE_PATH
    status_path = root / "data" / "ipo_learning" / "gate_context_provider.latest.json"
    reader: Dict[str, Any] = {}
    try:
        if status_path.is_file() and status_path.stat().st_size <= 16 * 1024:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                reader = loaded
    except (OSError, UnicodeError, ValueError):
        reader = {}
    reader_age_seconds = None
    try:
        updated = datetime.fromisoformat(str(reader.get("updated_at", "")).replace("Z", "+00:00"))
        if updated.tzinfo is not None and updated.utcoffset() is not None:
            reader_age_seconds = max(
                0.0, (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
            )
    except (TypeError, ValueError, OverflowError):
        pass
    reader_state = str(reader.get("state", "NOT_RUNNING"))[:32]
    if reader_age_seconds is None or reader_age_seconds > 15.0:
        reader_state = "STALE" if reader.get("updated_at") else "NOT_RUNNING"
    return {
        "transport": "sqlite_read_only_snapshot",
        "store_file_present": store_path.is_file(),
        "reader_state": reader_state,
        "reader_updated_at": str(reader.get("updated_at", ""))[:40],
        "reader_age_seconds": reader_age_seconds,
        "reader_process_id": reader.get("reader_process_id"),
        "stored_observation_count": reader.get("stored_observation_count", 0),
        "typed_gate_contexts_ready": reader.get("typed_gate_contexts_ready") is True,
        "runtime_authorized": False,
    }


def run_cycle(
    code: str, collect_labels: bool = False, root: str | Path = APP_ROOT,
    force_labels: bool = False,
) -> Dict[str, Any]:
    """Refresh supported upstream data and report all remaining unmet fields."""
    project_root = Path(root).resolve()
    acquisition = collect_issue_prices_from_ats_cache(project_root, ticker=code)
    ipo_facts = collect_ipo_facts(project_root, code)
    listing_anchors = collect_listing_day_anchors(project_root, code)
    listing_supply = collect_listing_supply_pace(project_root)
    market = collect_market_breadth_and_industry(
        project_root, code, {"INDUSTRY_NAME": ipo_facts.get("industry_name")}
    )
    limit_up_pool = collect_limit_up_break_rate(project_root)
    live = collect_live_metrics(
        project_root, code, {"ISSUE_PRICE": ipo_facts.get("issue_price")}
    )
    market_pulse = collect_market_pulse_fields(project_root)
    financing = collect_financing_balance_change(project_root)
    market_history = collect_tdx_market_history_fields(project_root, code)
    market_snapshot = collect_tdx_market_snapshot_fields(project_root)
    label_reports = []
    if collect_labels:
        try:
            from tools.generate_matured_labels import (
                collect_for_waiting_snapshots,
                collect_recent_ipo_cohort,
            )

            label_reports = collect_for_waiting_snapshots(project_root, force=force_labels)
            label_reports.extend(
                collect_recent_ipo_cohort(project_root, force=force_labels)
            )
        except Exception as exc:
            label_reports = [{"status": "UNREADY", "reason": f"标签采集异常: {type(exc).__name__}"}]
    try:
        config = IPODecisionConfigSnapshot.from_yaml(
            str(project_root / "config" / "ipo_sentiment.yaml")
        )
    except Exception as exc:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "CONFIG_INVALID", "reason": type(exc).__name__,
            "acquisition": acquisition, "ipo_facts": ipo_facts,
            "listing_anchors": listing_anchors,
            "listing_supply": listing_supply,
            "market": market, "live": live, "market_pulse": market_pulse,
            "market_history": market_history,
            "market_snapshot": market_snapshot,
            "limit_up_pool": limit_up_pool,
            "financing": financing,
            "gate_data_bridge": _gate_data_bridge(project_root),
            "operating_mode": "LIVE_DATA_SHADOW",
            "runtime_authorized": False,
            "llm_invocation_performed": False,
        }
        _write_latest_report(report, project_root)
        return report
    readiness = collect_source_readiness(project_root, code, config)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "READY" if readiness["status"] == "READY" else "UNREADY",
        "ticker": code, "acquisition": acquisition, "ipo_facts": ipo_facts,
        "listing_anchors": listing_anchors,
        "listing_supply": listing_supply,
        "market": market, "live": live, "market_pulse": market_pulse,
        "market_history": market_history,
        "market_snapshot": market_snapshot,
        "limit_up_pool": limit_up_pool,
        "financing": financing,
        "label_reports": label_reports,
        "ready_count": readiness["ready_count"],
        "required_count": readiness["required_count"],
        "field_readiness": readiness["observations"],
        "next_actions": readiness["next_actions"],
        "configuration_hash": readiness["configuration_hash"],
        "data_contract_hash": readiness["data_contract_hash"],
        "gate_data_bridge": _gate_data_bridge(project_root),
        "operating_mode": "LIVE_DATA_SHADOW",
        "runtime_authorized": False,
        "entry_authorized": False,
        "llm_invocation_performed": False,
    }
    _write_latest_report(report, project_root)
    return report


def _ats_market_session_active() -> bool:
    try:
        from zoneinfo import ZoneInfo
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool

        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        minute = now.hour * 60 + now.minute
        return bool(
            TDXGlobalCachePool.is_trading_day(now.date().isoformat())
            and (570 <= minute <= 690 or 780 <= minute <= 900)
        )
    except Exception:
        return False


def get_cached_ats_stock_table(fetcher: Any = None) -> Any:
    """Return ATS's persisted universe without refreshing IPO or quote endpoints."""
    import pandas as pd

    if fetcher is None:
        from ats.new_stock_fetcher import NewStockFetcher

        fetcher = NewStockFetcher.get_instance()
    cached = getattr(fetcher, "_cached_stocks_df", None)
    if isinstance(cached, pd.DataFrame) and not cached.empty and "code" in cached.columns:
        return cached.copy()
    calendar = getattr(fetcher, "_cached_ipo_dict", {})
    if not isinstance(calendar, dict):
        return pd.DataFrame()
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    records = []
    for code, item in calendar.items():
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["code"] = str(row.get("code") or code).zfill(6)
        listing_date = str(row.get("listing_date") or row.get("LISTING_DATE") or "")[:10]
        row["listing_date"] = listing_date
        if not row.get("status"):
            row["status"] = "待上市" if not listing_date or listing_date > today else "次新"
        records.append(row)
    return pd.DataFrame(records)


def _reserve_ats_source_refresh(root: Path, ticker: str, now: Optional[datetime] = None) -> bool:
    """Persist per-symbol cadence so manual refresh/restarts cannot bypass five minutes."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        return False
    point = now or datetime.now(timezone.utc)
    path = root / "data" / "ipo_learning" / "source_refresh" / f"{ticker}.json"
    temporary = path.with_name(f"{ticker}.{uuid4().hex}.tmp")
    lock_path = path.with_suffix(".lock")
    lock_fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if lock_path.is_file() and time.time() - lock_path.stat().st_mtime > 300:
            lock_path.unlink()
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        if path.is_file():
            previous = json.loads(path.read_text(encoding="utf-8"))
            last = datetime.fromisoformat(previous["attempted_at"])
            if (point - last).total_seconds() < 300:
                return False
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps({"attempted_at": point.isoformat()}) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return True
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return False
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _source_bootstrap_attempted(root: Path) -> bool:
    path = root / "data" / "ipo_learning" / "source_bootstrap.latest.json"
    try:
        if path.stat().st_size > 16 * 1024:
            return False
        state = json.loads(path.read_text(encoding="utf-8"))
        return bool(
            isinstance(state, dict)
            and state.get("schema_version") == _SOURCE_BOOTSTRAP_SCHEMA
            and state.get("status") == "ATTEMPTED"
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def _save_source_bootstrap_attempt(
    root: Path, ticker: str, source_collection: Dict[str, Any],
) -> bool:
    path = root / "data" / "ipo_learning" / "source_bootstrap.latest.json"
    temporary = path.with_suffix(".json.tmp")
    state = {
        "schema_version": _SOURCE_BOOTSTRAP_SCHEMA,
        "status": "ATTEMPTED",
        "mode": source_collection.get("mode", "UNKNOWN"),
        "ticker": ticker,
        "attempted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_status": source_collection.get("status", "UNKNOWN"),
        "reason": source_collection.get("reason", ""),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return True
    except OSError:
        return False


def _ats_recent_listing_codes(stocks: Any) -> set[str]:
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    try:
        rows = stocks.to_dict("records")
    except Exception:
        return set()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    cutoff = today - timedelta(days=30)
    codes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("status") or "") == "待上市":
            continue
        code = str(row.get("code") or "").strip().zfill(6)
        try:
            listing_day = datetime.fromisoformat(str(row.get("listing_date") or "")[:10]).date()
        except ValueError:
            continue
        if len(code) == 6 and code.isdigit() and cutoff <= listing_day <= today:
            codes.add(code)
    return codes


def _collect_ats_compatible_sources(
    project_root: Path, code: str, ats_stock: Dict[str, Any],
    stocks: Any, refresh_daily: bool,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Refresh only broad-market/TDX producers, using ATS for the IPO universe."""
    row = {
        "INDUSTRY_NAME": ats_stock.get("industry_name", ""),
        "ISSUE_PRICE": ats_stock.get("issue_price", 0),
    }
    results: Dict[str, Dict[str, Any]] = {}

    def progress(stage: str, message: str, status: str = "RUNNING") -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({"stage": stage, "message": message, "status": status, "ticker": code})
        except Exception:
            pass

    def collect(name: str, label: str, callback: Callable[[], Dict[str, Any]]) -> None:
        stage = f"SOURCE_{name.upper()}"
        progress(stage, f"开始：{label}")
        try:
            report = callback()
            if not isinstance(report, dict):
                report = {"status": "UNREADY", "saved_fields": [], "reason": "来源返回格式不是对象"}
            results[name] = report
            saved_count = len(report.get("saved_fields", [])) if isinstance(report.get("saved_fields"), list) else 0
            reason = str(report.get("reason") or "").strip()
            message = f"完成：{report.get('status', 'UNKNOWN')}，写入 {saved_count} 项"
            progress(stage, f"{message}；{reason}" if reason else message, "DONE")
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc).replace(chr(10), ' ')[:240]}"
            results[name] = {"status": "UNREADY", "saved_fields": [], "reason": reason}
            progress(stage, f"失败：{label}；{reason}", "FAILED")

    def skip(name: str, reason: str) -> None:
        results[name] = {"status": "SKIPPED", "saved_fields": [], "reason": reason}
        progress(f"SOURCE_{name.upper()}", f"跳过：{reason}", "SKIPPED")

    if ats_stock.get("status") == "READY":
        ipo_codes = _ats_recent_listing_codes(stocks)
        collect(
            "market", "市场宽度与行业成交额",
            lambda: collect_market_breadth_and_industry(
                project_root, code, row, ipo_codes=ipo_codes,
            ),
        )
        collect(
            "live", "个股实时指标与分时数据",
            lambda: collect_live_metrics(project_root, code, row),
        )
    else:
        reason = "ATS 新股/次新股表无该标的，跳过个股来源"
        skip("market", reason)
        skip("live", reason)
    collect(
        "limit_up_pool", "涨停开板率",
        lambda: collect_limit_up_break_rate(project_root),
    )
    if refresh_daily:
        collect(
            "financing", "融资余额变化",
            lambda: collect_financing_balance_change(project_root),
        )
        collect(
            "market_history", "TDX 历史指标",
            lambda: collect_tdx_market_history_fields(project_root, code),
        )
        collect(
            "market_pulse", "Market Pulse 情绪快照",
            lambda: collect_market_pulse_fields(project_root),
        )
    else:
        reason = "当日已尝试日频来源；等待下一交易日刷新"
        for name in ("financing", "market_history", "market_pulse"):
            skip(name, reason)
    return results


def run_ats_learning_cycle(
    code: str, collect_labels: bool = False, root: str | Path = APP_ROOT,
    force_labels: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Read ATS's IPO module and detector for shadow learning; never run an order path."""
    try:
        project_root = Path(root).resolve()
    except OSError:
        project_root = Path(root).absolute()

    def progress(
        stage: str, message: str, status: str = "RUNNING", event_ticker: str = "",
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback({
                "stage": stage, "message": message, "status": status,
                "ticker": event_ticker or code,
            })
        except Exception:
            pass

    ats_status: Dict[str, Any] = {"status": "UNREADY"}
    signal_status: Dict[str, Any] = {"status": "UNREADY"}
    market_active = _ats_market_session_active()
    root_key = str(project_root)
    bootstrap_pending = (
        root_key not in _ATS_COLD_START_ATTEMPTED_ROOTS
        and not _source_bootstrap_attempted(project_root)
    )
    cold_start_exempt = bootstrap_pending
    refresh_due = (
        (market_active or cold_start_exempt)
        and _reserve_ats_source_refresh(project_root, code)
    )
    progress("ATS_TABLE", "读取 ATS 新股/次新股表及标的基础字段")
    try:
        from ats.new_stock_fetcher import NewStockFetcher

        fetcher = NewStockFetcher.get_instance()
        stocks = fetcher.get_combined_new_stocks() if refresh_due else get_cached_ats_stock_table(fetcher)
        row = stocks.loc[stocks["code"].astype(str).str.zfill(6) == code]
        if not row.empty:
            selected = row.iloc[0]
            ats_status = {
                "status": "READY", "ticker": code,
                "listing_date": str(selected.get("listing_date") or ""),
                "listing_status": str(selected.get("status") or ""),
                "issue_price": float(selected.get("issue_price") or 0),
                "industry_name": str(selected.get("industry_name") or ""),
                "source": "ATS NewStockFetcher",
            }
        else:
            ats_status = {"status": "UNREADY", "reason": "ATS 新股/次新股表无该标的"}
    except Exception as exc:
        ats_status = {"status": "UNREADY", "reason": f"ATS 新股模块读取失败: {type(exc).__name__}"}
    progress(
        "ATS_TABLE", "ATS 标的基础信息就绪" if ats_status.get("status") == "READY"
        else str(ats_status.get("reason") or "ATS 标的不存在"),
        "DONE" if ats_status.get("status") == "READY" else "BLOCKED",
    )
    progress("ISSUE_CACHE", "读取 ATS IPO 发行日历与本地缓存")
    acquisition = collect_issue_prices_from_ats_cache(project_root, ticker=code)
    config_path = project_root / "config" / "ipo_sentiment.yaml"
    config = None
    readiness_before: Dict[str, Any] = {"observations": []}
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        readiness_before = collect_source_readiness(project_root, code, config)
    except Exception:
        pass
    progress("CONTRACT_BASELINE", "核对本标的 41 项来源契约与当前可用字段")
    collect_supported_sources = refresh_due
    if collect_supported_sources:
        from zoneinfo import ZoneInfo

        local_day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        refresh_daily_sources = _ATS_DAILY_SOURCE_REFRESH_DATES.get(root_key) != local_day
        source_reports: Dict[str, Dict[str, Any]] = {}
        if config_path.is_file():
            _ATS_COLD_START_ATTEMPTED_ROOTS.add(root_key)
            progress(
                "SOURCE_COLLECTION", "启动 ATS 兼容来源采集："
                + ("交易时段刷新" if market_active else "首次初始化一次性豁免；此后休市去重"),
            )
            if refresh_daily_sources:
                _ATS_DAILY_SOURCE_REFRESH_DATES[root_key] = local_day
            try:
                source_reports = _collect_ats_compatible_sources(
                    project_root, code, ats_status, stocks if "stocks" in locals() else None,
                    refresh_daily=refresh_daily_sources,
                    progress_callback=progress_callback,
                )
                source_collection = {
                    "status": "ATTEMPTED",
                    "mode": "MARKET_SESSION" if market_active else "COLD_START_EXEMPT",
                    "daily_sources_refreshed": refresh_daily_sources,
                    "reason": "盘中刷新实时来源" if market_active else "首次初始化冷启动豁免；本次执行后休市期间不重复",
                }
            except Exception as exc:
                source_collection = {
                    "status": "UNREADY", "mode": "COLD_START_EXEMPT" if cold_start_exempt else "MARKET_SESSION",
                    "reason": f"ATS兼容来源采集失败: {type(exc).__name__}",
                }
            if bootstrap_pending:
                source_collection["bootstrap_persistence"] = (
                    "SAVED" if _save_source_bootstrap_attempt(project_root, code, source_collection)
                    else "FAILED"
                )
        else:
            source_collection = {
                "status": "SKIPPED", "mode": "UNCONFIGURED",
                "reason": "缺少 IPO 字段契约配置，未启动来源采集",
            }
    else:
        source_reports = {}
        source_collection = {
            "status": "STATIC_ONLY",
            "mode": "CADENCE_THROTTLED" if market_active or cold_start_exempt else "STATIC_HISTORICAL",
            "reason": ("本标的距上次读取不足 5 分钟，或周期状态不可写；复用 ATS 缓存"
                       if market_active or cold_start_exempt else
                       "休市/周末不请求实时行情与外部来源；继续读取本机多日历史并完成静态情绪分析"),
        }
        progress("SOURCE_COLLECTION", source_collection["reason"], "DONE")
    if collect_supported_sources:
        component_counts = ", ".join(
            f"{name}={len(item.get('saved_fields', []))}项/{item.get('status', 'UNREADY')}"
            for name, item in source_reports.items() if isinstance(item, dict)
        ) or "没有来源组件返回字段"
        progress("SOURCE_COLLECTION", component_counts, "DONE")
    trading_center: Dict[str, Any] = {"status": "NOT_RUNNING", "recent_signal_count": 0}
    ledger = project_root / "ats" / "config" / "ipo_trading_ledger.json"
    try:
        from ats.strategy.ipo_trading_center import IPOTradingCenter

        center = IPOTradingCenter._instance
        logs = center.get_signal_iteration_log() if center is not None else []
        if center is None and ledger.is_file() and ledger.stat().st_size <= 4 * 1024 * 1024:
            saved_ledger = json.loads(ledger.read_text(encoding="utf-8"))
            logs = saved_ledger.get("signal_iteration_log", []) if isinstance(saved_ledger, dict) else []
        if center is not None or logs:
            matching = [item for item in logs if isinstance(item, dict) and str(item.get("code")) == code]
            trading_center = {
                "status": "IN_PROCESS" if center is not None else "HISTORICAL",
                "recent_signal_count": len(matching),
                "latest_signal": {
                    key: matching[0].get(key) for key in ("timestamp", "action", "signal_tier", "directive_id")
                } if matching else {},
                "source": "ATS IPOTradingCenter persisted signal log",
            }
    except (OSError, UnicodeError, ValueError, TypeError):
        trading_center = {"status": "UNREADY", "recent_signal_count": 0,
                          "reason": "ATS 交易中心历史信号账本不可读"}
    static_snapshot: Dict[str, Any] = {}
    progress("STATIC_HISTORY", "任何时段均读取本机多日历史；缺失时回退本地通达信日线", "RUNNING")
    historical_analysis = _analyze_static_ipo_history(code)

    def static_progress(payload: Dict[str, Any]) -> None:
        progress(
            str(payload.get("stage") or "STATIC_UNIVERSE_SWEEP"),
            str(payload.get("message") or ""),
            str(payload.get("status") or "RUNNING"),
            str(payload.get("ticker") or ""),
        )

    static_snapshot = _complete_static_universe_snapshot(
        project_root,
        stocks if "stocks" in locals() else None,
        code,
        historical_analysis,
        progress_callback=static_progress,
    )
    progress(
        "STATIC_HISTORY",
        f"静态情绪评分 {historical_analysis.get('emotion_score', 50.0)}/100 "
        f"({historical_analysis.get('score_quality', 'NO_EVIDENCE')})；"
        f"{historical_analysis.get('sentiment', historical_analysis.get('status'))}；"
        f"截至 {historical_analysis.get('as_of_time', '无本地时点')}；"
        f"全名单 {static_snapshot.get('universe_scan', {}).get('processed_count', 0)}/"
        f"{static_snapshot.get('universe_scan', {}).get('universe_count', 0)}",
        "DONE",
    )
    inspect_signal = refresh_due
    progress(
        "ATS_DETECTOR",
        "运行 ATS IPO 异动检测器并校验新鲜报价/分钟线时点"
        if inspect_signal else "未到读取周期或非交易时段；本轮复用缓存并完成静态历史评分",
        "RUNNING" if inspect_signal else "SKIPPED",
    )
    if (ats_status.get("status") == "READY" and ats_status.get("listing_status") != "待上市"
            and inspect_signal):
        try:
            from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool, TDXRealtimeFetcher
            from zoneinfo import ZoneInfo

            signal = IPOVWAPDetectorEngine.get_instance().analyze_stock(code)
            local_now = datetime.now(ZoneInfo("Asia/Shanghai"))
            minute = local_now.hour * 60 + local_now.minute
            in_session = (
                TDXGlobalCachePool.is_trading_day(local_now.date().isoformat())
                and (570 <= minute <= 690 or 780 <= minute <= 900)
            )
            source_as_of = ""
            bar_as_of = ""
            try:
                if signal.price <= 0:
                    raise ValueError("检测结果无有效价格")
                quotes = TDXRealtimeFetcher.get_instance().get_security_quotes_safe([code])
                quote = next((item for item in quotes if str(item.get("code")) == code), {})
                quote_time = datetime.fromisoformat(
                    f"{local_now.date().isoformat()}T{quote.get('servertime', '')}"
                ).replace(tzinfo=local_now.tzinfo)
                quote_price = float(quote.get("price") or 0)
                age = (local_now - quote_time).total_seconds()
                if 0 <= age <= 120 and quote_price > 0 and abs(quote_price - signal.price) / quote_price <= 0.01:
                    source_as_of = quote_time.isoformat(timespec="seconds")
            except (TypeError, ValueError, StopIteration):
                pass
            try:
                raw_bar = (signal.extra_data or {}).get("ipo_source_bar_as_of", "")
                bar_time = datetime.fromisoformat(raw_bar).replace(tzinfo=local_now.tzinfo)
                if 0 <= (local_now - bar_time).total_seconds() <= 300:
                    bar_as_of = bar_time.isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
            signal_status = {
                "status": ("OBSERVED" if source_as_of and bar_as_of and in_session else "HISTORICAL") if signal.price > 0 else "UNREADY",
                "ticker": code, "signal_type": signal.signal_type,
                "signal_tier": signal.signal_tier, "price": signal.price,
                "vwap": signal.vwap, "vwap_diff_pct": signal.vwap_diff_pct,
                "horse_race_score": signal.horse_race_score,
                "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "ATS IPOVWAPDetectorEngine",
                "source_time_verified": bool(source_as_of and bar_as_of),
                "source_as_of": source_as_of, "bar_as_of": bar_as_of,
                "trading_authorized": False,
            }
            if signal.price <= 0:
                signal_status["reason"] = "ATS 检测器未取得有效价格或分钟线"
            elif not in_session:
                signal_status["reason"] = "非交易时段；仅展示历史分析"
            elif not source_as_of:
                signal_status["reason"] = "ATS 原始报价已过期或与检测价格不一致"
            elif not bar_as_of:
                signal_status["reason"] = "ATS 检测分钟线已过期或缺少来源时间"
        except Exception as exc:
            signal_status = {"status": "UNREADY", "reason": f"ATS 新股检测失败: {type(exc).__name__}"}
    elif not market_active:
        history_ready = historical_analysis.get("status") == "READY"
        signal_status = {
            "status": "HISTORICAL" if history_ready else "UNREADY",
            "ticker": code, "source": "本机历史静态分析",
            "signal_type": historical_analysis.get("sentiment", ""),
            "price": historical_analysis.get("latest_close", 0),
            "source_time_verified": False, "trading_authorized": False,
            "reason": (
                "历史情绪结果；不代表实时异动，不进入实时影子样本或交易授权"
                if history_ready else historical_analysis.get("reason", "本机历史数据不可用")
            ),
        }
    progress(
        "ATS_DETECTOR",
        f"异动状态 {signal_status.get('status', 'UNREADY')}；"
        f"{signal_status.get('reason') or '报价与分钟线有效性已核对'}",
        (
            "DONE" if signal_status.get("status") in {"OBSERVED", "HISTORICAL"}
            else "BLOCKED" if market_active else "SKIPPED"
        ),
    )
    try:
        if config is None:
            config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        readiness = collect_source_readiness(project_root, code, config)
    except Exception as exc:
        readiness = {"status": "UNREADY", "ready_count": 0, "required_count": 41,
                     "observations": [], "next_actions": [], "configuration_hash": "",
                     "data_contract_hash": "", "reason": type(exc).__name__}
    progress(
        "CONTRACT_FINAL",
        f"最终 Gate 契约就绪 {readiness.get('ready_count', 0)}/{readiness.get('required_count', 41)}；"
        f"{'; '.join(str(item) for item in readiness.get('next_actions', [])[:3])}",
        "DONE" if readiness.get("ready_count") == readiness.get("required_count") else "BLOCKED",
    )
    signal_capture: Dict[str, Any] = {"state": "UNREADY", "reason": "ATS_SIGNAL_NOT_FRESH"}
    if signal_status.get("status") == "OBSERVED":
        try:
            from ats.strategy.ipo_shadow_observations import capture_ats_signal_observation

            signal_capture = capture_ats_signal_observation(
                project_root, signal_status,
                configuration_hash=readiness["configuration_hash"],
                data_contract_hash=readiness["data_contract_hash"],
            )
        except Exception as exc:
            signal_capture = {"state": "UNREADY", "reason": f"ATS_SIGNAL_CAPTURE_{type(exc).__name__}"}
    from ats.strategy.ipo_shadow_observations import (
        ats_signal_paper_outcomes, learn_ats_signal_quality,
    )
    signal_outcomes = ats_signal_paper_outcomes(project_root)
    signal_learning = learn_ats_signal_quality(project_root, signal_outcomes)
    labels = []
    if collect_labels:
        progress("MATURED_LABELS", "扫描已成熟 D1-D3 结果证据并生成待人工复核项")
        try:
            from tools.generate_matured_labels import collect_for_waiting_snapshots, collect_recent_ipo_cohort

            labels = collect_for_waiting_snapshots(project_root, force=force_labels)
            labels.extend(collect_recent_ipo_cohort(project_root, force=force_labels))
        except Exception as exc:
            labels = [{"status": "UNREADY", "reason": f"ATS 标签读取失败: {type(exc).__name__}"}]
        progress("MATURED_LABELS", f"本轮产生 {len(labels)} 条标签结果；训练保持关闭", "DONE")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": (
            "OBSERVING" if signal_status.get("status") == "OBSERVED"
            else "HISTORICAL" if isinstance(historical_analysis.get("emotion_score"), (int, float))
            else "UNREADY"
        ),
        "ticker": code, "ats_stock": ats_status, "ats_signal": signal_status,
        "historical_analysis": historical_analysis,
        "static_sentiment": static_snapshot,
        "ats_trading_center": trading_center, "ats_signal_capture": signal_capture,
        "ats_signal_outcomes": signal_outcomes,
        "ats_signal_learning": signal_learning,
        "acquisition": acquisition, "label_reports": labels,
        "source_collection": source_collection,
        "market": source_reports.get("market", {}),
        "live": source_reports.get("live", {}),
        "limit_up_pool": source_reports.get("limit_up_pool", {}),
        "financing": source_reports.get("financing", {}),
        "market_history": source_reports.get("market_history", {}),
        "market_pulse": source_reports.get("market_pulse", {}),
        "ready_count": readiness["ready_count"], "required_count": readiness["required_count"],
        "field_readiness": readiness["observations"], "next_actions": readiness["next_actions"],
        "configuration_hash": readiness["configuration_hash"],
        "data_contract_hash": readiness["data_contract_hash"],
        "gate_data_bridge": _gate_data_bridge(project_root),
        "operating_mode": "ATS_SIGNAL_SHADOW", "runtime_authorized": False,
        "entry_authorized": False, "llm_invocation_performed": False,
    }
    _write_latest_report(report, project_root)
    persistence = report.get("report_persistence", {})
    persistence = persistence if isinstance(persistence, dict) else {}
    progress(
        "REPORT_SAVED",
        f"{persistence.get('status', 'UNKNOWN')} acquisition.latest.json；"
        f"标的 {code} 契约 {readiness['ready_count']}/{readiness['required_count']}；"
        f"{persistence.get('reason') or persistence.get('path', '')}",
        "DONE" if persistence.get("status") == "SAVED" else "FAILED",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="ATS 新股与异动信号影子观察（LLM/交易授权保持关闭）")
    parser.add_argument("--code", "-c", default="301689", help="用于完整契约自检的六位代码")
    parser.add_argument("--watch", action="store_true", help="按固定周期持续刷新已接入来源")
    parser.add_argument("--labels", action="store_true", help="周期性扫描冻结快照并采集 D1-D3 结果证据")
    parser.add_argument("--force-labels", action="store_true", help="手动忽略盘后时间/当日去重并重跑标签扫描")
    parser.add_argument("--interval-minutes", type=int, default=5, help="周期模式间隔，范围 5..1440 分钟")
    args = parser.parse_args()
    if len(args.code) != 6 or not args.code.isdigit():
        parser.error("--code 必须为六位数字")
    if args.watch and not 5 <= args.interval_minutes <= 1440:
        parser.error("--interval-minutes 必须在 5..1440 之间")
    if args.force_labels and not args.labels:
        parser.error("--force-labels 必须与 --labels 一起使用")

    while True:
        report = run_ats_learning_cycle(args.code, args.labels, force_labels=args.force_labels)
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)
        if not args.watch:
            return 0 if report.get("status") != "CONFIG_INVALID" else 2
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())

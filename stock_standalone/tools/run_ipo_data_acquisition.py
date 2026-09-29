# -*- coding: utf-8 -*-
"""Bounded IPO source collector; it never invokes an LLM or authorizes trading."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

APP_ROOT = Path(__file__).resolve().parents[1]
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


def run_ats_learning_cycle(
    code: str, collect_labels: bool = False, root: str | Path = APP_ROOT,
    force_labels: bool = False,
) -> Dict[str, Any]:
    """Read ATS's IPO module and detector for shadow learning; never run an order path."""
    project_root = Path(root).resolve()
    ats_status: Dict[str, Any] = {"status": "UNREADY"}
    signal_status: Dict[str, Any] = {"status": "UNREADY"}
    try:
        from ats.new_stock_fetcher import NewStockFetcher

        fetcher = NewStockFetcher.get_instance()
        stocks = fetcher.get_combined_new_stocks()
        row = stocks.loc[stocks["code"].astype(str).str.zfill(6) == code]
        if not row.empty:
            selected = row.iloc[0]
            ats_status = {
                "status": "READY", "ticker": code,
                "listing_date": str(selected.get("listing_date") or ""),
                "listing_status": str(selected.get("status") or ""),
                "issue_price": float(selected.get("issue_price") or 0),
                "source": "ATS NewStockFetcher",
            }
        else:
            ats_status = {"status": "UNREADY", "reason": "ATS 新股/次新股表无该标的"}
    except Exception as exc:
        ats_status = {"status": "UNREADY", "reason": f"ATS 新股模块读取失败: {type(exc).__name__}"}
    acquisition = collect_issue_prices_from_ats_cache(project_root, ticker=code)
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
    if ats_status.get("status") == "READY" and ats_status.get("listing_status") != "待上市":
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
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(project_root / "config/ipo_sentiment.yaml"))
        readiness = collect_source_readiness(project_root, code, config)
    except Exception as exc:
        readiness = {"status": "UNREADY", "ready_count": 0, "required_count": 41,
                     "observations": [], "next_actions": [], "configuration_hash": "",
                     "data_contract_hash": "", "reason": type(exc).__name__}
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
        try:
            from tools.generate_matured_labels import collect_for_waiting_snapshots, collect_recent_ipo_cohort

            labels = collect_for_waiting_snapshots(project_root, force=force_labels)
            labels.extend(collect_recent_ipo_cohort(project_root, force=force_labels))
        except Exception as exc:
            labels = [{"status": "UNREADY", "reason": f"ATS 标签读取失败: {type(exc).__name__}"}]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "OBSERVING" if signal_status.get("status") == "OBSERVED" else "UNREADY",
        "ticker": code, "ats_stock": ats_status, "ats_signal": signal_status,
        "ats_trading_center": trading_center, "ats_signal_capture": signal_capture,
        "ats_signal_outcomes": signal_outcomes,
        "ats_signal_learning": signal_learning,
        "acquisition": acquisition, "label_reports": labels,
        "ready_count": readiness["ready_count"], "required_count": readiness["required_count"],
        "field_readiness": readiness["observations"], "next_actions": readiness["next_actions"],
        "configuration_hash": readiness["configuration_hash"],
        "data_contract_hash": readiness["data_contract_hash"],
        "gate_data_bridge": _gate_data_bridge(project_root),
        "operating_mode": "ATS_SIGNAL_SHADOW", "runtime_authorized": False,
        "entry_authorized": False, "llm_invocation_performed": False,
    }
    _write_latest_report(report, project_root)
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

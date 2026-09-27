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
    collect_issue_prices_from_eastmoney,
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


def run_cycle(
    code: str, collect_labels: bool = False, root: str | Path = APP_ROOT,
    force_labels: bool = False,
) -> Dict[str, Any]:
    """Refresh supported upstream data and report all remaining unmet fields."""
    project_root = Path(root).resolve()
    acquisition = collect_issue_prices_from_eastmoney(project_root)
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
        try:
            from ats.strategy.ipo_gate_context_provider import get_default_ipo_gate_context_provider

            get_default_ipo_gate_context_provider(project_root).invalidate()
        except Exception:
            pass
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
            "runtime_authorized": False,
        }
        _write_latest_report(report, project_root)
        return report
    readiness = collect_source_readiness(project_root, code, config)
    try:
        from ats.strategy.ipo_gate_context_provider import get_default_ipo_gate_context_provider

        get_default_ipo_gate_context_provider(project_root).refresh(config)
    except Exception:
        pass
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
        "next_actions": readiness["next_actions"],
        "configuration_hash": readiness["configuration_hash"],
        "data_contract_hash": readiness["data_contract_hash"],
        "runtime_authorized": False,
        "llm_invocation_performed": False,
    }
    _write_latest_report(report, project_root)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="新股数据采集与字段自检（LLM/交易授权保持关闭）")
    parser.add_argument("--code", "-c", default="301689", help="用于完整契约自检的六位代码")
    parser.add_argument("--watch", action="store_true", help="按固定周期持续刷新已接入来源")
    parser.add_argument("--labels", action="store_true", help="周期性扫描冻结快照并采集 D1-D3 结果证据")
    parser.add_argument("--force-labels", action="store_true", help="手动忽略盘后时间/当日去重并重跑标签扫描")
    parser.add_argument("--interval-minutes", type=int, default=60, help="周期模式间隔，范围 5..1440 分钟")
    args = parser.parse_args()
    if len(args.code) != 6 or not args.code.isdigit():
        parser.error("--code 必须为六位数字")
    if args.watch and not 5 <= args.interval_minutes <= 1440:
        parser.error("--interval-minutes 必须在 5..1440 之间")
    if args.force_labels and not args.labels:
        parser.error("--force-labels 必须与 --labels 一起使用")

    while True:
        report = run_cycle(args.code, args.labels, force_labels=args.force_labels)
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")), flush=True)
        if not args.watch:
            return 0 if report.get("status") != "CONFIG_INVALID" else 2
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    raise SystemExit(main())

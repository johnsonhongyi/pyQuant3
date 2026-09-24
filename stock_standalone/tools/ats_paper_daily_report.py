# -*- coding: utf-8 -*-
"""Read-only ATS/TK JSONL event report; never opens or mutates a database."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
from typing import Any


def _parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value)).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    event = dict(item)
    envelope = event.get("audit_envelope")
    if isinstance(envelope, dict):
        for key, value in envelope.items():
            event.setdefault(key, value)

    signal = event.get("signal")
    if not isinstance(signal, dict):
        signal = {}
    kernel = event.get("kernel_result")
    if not isinstance(kernel, dict):
        kernel = {}
    trace = event.get("trace")
    if not isinstance(trace, dict):
        trace = {}
    features = signal.get("features")
    if not isinstance(features, dict):
        features = {}

    event.setdefault("code", signal.get("code"))
    event.setdefault("name", signal.get("name"))
    event.setdefault("source", signal.get("source"))
    for field in ("candidate_id", "plan_id", "exit_rule_id"):
        if not event.get(field):
            event[field] = features.get(field) or signal.get(field) or ""
    event.setdefault(
        "strategy",
        event.get("strategy_tag") or signal.get("strategy_tag")
        or features.get("strategy_tag") or features.get("strategy"),
    )
    event.setdefault(
        "tide_state",
        event.get("tide_state") or signal.get("tide_state")
        or features.get("tide_state") or features.get("market_tide_state"),
    )
    event.setdefault(
        "cross_day_path",
        event.get("cross_day_state") or signal.get("cross_day_state") or signal.get("cross_day_path")
        or features.get("cross_day_state") or features.get("cross_day_path"),
    )
    event.setdefault("observed_at", signal.get("ts") or signal.get("timestamp"))
    event.setdefault("event_time", event.get("journal_ts") or event.get("timestamp"))
    # KernelTrace.trace_id is a stable per-decision identity. Keep repeated IDs
    # visible as duplicates; never drop or rewrite the source event.
    event.setdefault("event_id", trace.get("trace_id"))
    event.setdefault("price", signal.get("price"))
    event.setdefault("action", kernel.get("kernel_action") or event.get("action"))
    event.setdefault("directive_id", event.get("request_id"))
    event.setdefault("order_id", kernel.get("kernel_order_id") or kernel.get("order_id"))
    if "execution_status" not in event:
        kernel_status = str(kernel.get("status") or "").upper()
        if kernel_status in {"REJECTED", "PARTIAL", "FILLED", "EXECUTED", "SUBMITTED"}:
            event["execution_status"] = kernel_status
        elif kernel.get("kernel_executed") is True:
            event["execution_status"] = "SUBMITTED"
        elif kernel.get("kernel_allowed") is False:
            event["execution_status"] = "REJECTED"
    event.setdefault("event_type", event.get("execution_status") or kernel.get("kernel_action"))
    if not event.get("reject_code"):
        event["reject_code"] = kernel.get("kernel_reject_code") or ""
    for field in (
        "mfe_pct", "mae_pct", "slippage_pct", "t1_delayed_exit",
        "planned_exit_price", "exit_fill_price",
    ):
        if field not in event:
            value = kernel.get(f"kernel_{field}", kernel.get(field))
            if value is None:
                value = features.get(field)
            if value is not None:
                event[field] = value
    return event


def _expand_signal_entry(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a serialized SignalEntry lifecycle into decision events."""
    lifecycle = item.get("lifecycle")
    history = lifecycle.get("history") if isinstance(lifecycle, dict) else None
    if not isinstance(history, list) or not history:
        return [_normalize_event(item)]
    expanded = []
    for transition in history:
        if not isinstance(transition, dict):
            continue
        event = dict(transition)
        event.setdefault("code", item.get("code"))
        event.setdefault("name", item.get("name"))
        event.setdefault("candidate_id", item.get("candidate_id"))
        event.setdefault("source", item.get("signal_source"))
        event.setdefault("action", transition.get("event"))
        event.setdefault("event_type", "SIGNAL_DECISION")
        event.setdefault("event_time", transition.get("event_time"))
        expanded.append(_normalize_event(event))
    return expanded or [_normalize_event(item)]


def _read_input_events(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                snapshot_rows = payload.get("signal_iteration_log")
                snapshot_kind = "signal_iteration_log"
                if not isinstance(snapshot_rows, list) or not snapshot_rows:
                    snapshot_rows = payload.get("directive_history")
                    snapshot_kind = "directive_history"
                if not isinstance(snapshot_rows, list) or not snapshot_rows:
                    snapshot_rows = payload.get("entries")
                    snapshot_kind = "entries"
                if not isinstance(snapshot_rows, list):
                    snapshot_rows = []
                if snapshot_kind in {"signal_iteration_log", "directive_history"} and snapshot_rows:
                    for row_no, item in enumerate(snapshot_rows, 1):
                        if isinstance(item, dict):
                            events.append(_normalize_event(item))
                        else:
                            errors.append({
                                "file": path.name, "line": row_no,
                                "error": "SNAPSHOT_EVENT_NOT_OBJECT",
                            })
                elif isinstance(payload.get("entries"), list):
                    for row_no, item in enumerate(snapshot_rows, 1):
                        if isinstance(item, dict):
                            events.extend(_expand_signal_entry(item))
                        else:
                            errors.append({
                                "file": path.name, "line": row_no,
                                "error": "SIGNAL_ENTRY_NOT_OBJECT",
                            })
                elif isinstance(payload.get("lifecycle"), dict):
                    events.extend(_expand_signal_entry(payload))
                elif any(key in payload for key in (
                    "event_id", "directive_id", "signal", "kernel_result", "audit_envelope", "action", "status"
                )):
                    events.append(_normalize_event(payload))
                else:
                    errors.append({"file": path.name, "line": 0, "error": "JSON_OBJECT_NOT_EVENT_SOURCE"})
            elif isinstance(payload, list):
                for row_no, item in enumerate(payload, 1):
                    if isinstance(item, dict):
                        events.extend(_expand_signal_entry(item))
                    else:
                        errors.append({
                            "file": path.name, "line": row_no,
                            "error": "JSON_ARRAY_ROW_NOT_OBJECT",
                        })
            else:
                errors.append({"file": path.name, "line": 0, "error": "JSON_ROOT_NOT_OBJECT_OR_ARRAY"})
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append({"file": path.name, "line": 0, "error": str(exc)})
        return events, errors

    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        events.extend(_expand_signal_entry(item))
                    else:
                        errors.append({
                            "file": path.name, "line": line_no,
                            "error": "JSONL_ROW_NOT_OBJECT",
                        })
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    errors.append({"file": path.name, "line": line_no, "error": str(exc)})
    except OSError as exc:
        errors.append({"file": path.name, "line": 0, "error": str(exc)})
    return events, errors


def _cross_source_overlap_baseline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Report possible cross-source/strategy overlaps without deduplicating events."""
    window_seconds = 60
    clusters: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    eligible_event_count = 0
    missing_signature_count = 0
    for event in events:
        code = str(event.get("code") or "").strip().zfill(6)
        action = str(event.get("action") or "").strip().upper()
        event_time = _parse_time(event.get("observed_at") or event.get("event_time") or event.get("timestamp"))
        if not code or not action or event_time is None:
            missing_signature_count += 1
            continue
        if event_time.tzinfo is None:
            event_time = event_time.astimezone()
        bucket = int(event_time.timestamp()) // window_seconds
        clusters[(code, action, bucket)].append(event)
        eligible_event_count += 1

    overlaps = []
    overlapping_event_count = 0
    for (code, action, bucket), rows in sorted(clusters.items()):
        sources = sorted({str(row.get("source") or "UNKNOWN").strip() for row in rows})
        strategies = sorted({
            str(row.get("strategy") or row.get("strategy_tag") or "UNKNOWN").strip()
            for row in rows
        })
        if len(rows) < 2 or (len(sources) < 2 and len(strategies) < 2):
            continue
        overlapping_event_count += len(rows)
        overlaps.append({
            "code": code,
            "action": action,
            "window_start": dt.datetime.fromtimestamp(bucket * window_seconds).astimezone().isoformat(),
            "event_count": len(rows),
            "sources": sources,
            "strategies": strategies,
        })
    return {
        "method": "same code + action within a 60-second time bucket; possible overlap only, no automatic deduplication",
        "eligible_event_count": eligible_event_count,
        "missing_signature_count": missing_signature_count,
        "overlap_cluster_count": len(overlaps),
        "overlapping_event_count": overlapping_event_count,
        "overlapping_event_rate": round(overlapping_event_count / eligible_event_count, 4)
        if eligible_event_count else None,
        "clusters": overlaps,
    }


def build_daily_report(input_paths: list[str], as_of: dt.datetime | None = None) -> dict[str, Any]:
    events = []
    errors = []
    for raw_path in input_paths:
        path = Path(raw_path)
        loaded_events, input_errors = _read_input_events(path)
        for item in loaded_events:
            item["_source_file"] = path.name
        events.extend(loaded_events)
        errors.extend(input_errors)
    if not events:
        errors.append({"file": "", "line": 0, "error": "NO_VALID_EVENTS"})

    stage_counts: Counter[str] = Counter()
    groups: dict[tuple[str, str, str, str], Counter[str]] = defaultdict(Counter)
    group_quality: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    freshness_ms = []
    mfe = []
    mae = []
    slippage_pct = []
    t1_delay_loss_pct = []
    directive_ids = set()
    order_ids = set()
    linked_directive_ids = set()
    event_id_present_count = 0
    required_field_coverage = Counter()
    identity_field_coverage = Counter()
    identity_incomplete_event_count = 0
    signal_decision_event_count = 0
    signal_decision_field_coverage = Counter()
    signal_decision_incomplete_event_count = 0
    duplicate_events = 0
    rejected_event_count = 0
    reject_reason_counts: Counter[str] = Counter()
    seen_events = set()
    for event in events:
        stage = str(
            event.get("event_type") or event.get("execution_status")
            or event.get("state") or event.get("status") or "UNKNOWN"
        ).upper()
        stage_counts[stage] += 1
        key = (
            str(event.get("source") or "UNKNOWN"),
            str(event.get("strategy") or event.get("strategy_tag") or "UNKNOWN"),
            str(event.get("tide_state") or "UNKNOWN"),
            str(event.get("cross_day_path") or event.get("cross_day_state") or "UNKNOWN"),
        )
        groups[key][stage] += 1
        quality = group_quality.setdefault(key, {
            "event_count": 0,
            "field_present": Counter(),
            "freshness_ms": [],
            "mfe_pct": [],
            "mae_pct": [],
            "slippage_pct": [],
            "t1_delay_loss_pct": [],
            "reject_reason_counts": Counter(),
        })
        quality["event_count"] += 1
        for field in ("event_id", "source", "strategy", "tide_state", "cross_day_path"):
            value = event.get(field)
            if field == "strategy":
                value = value or event.get("strategy_tag")
            if value is not None and str(value).strip():
                quality["field_present"][field] += 1
                required_field_coverage[field] += 1
        for field in ("candidate_id", "plan_id", "exit_rule_id"):
            if event.get(field) and str(event[field]).strip():
                identity_field_coverage[field] += 1
        if str(event.get("event_type") or "").upper() == "SIGNAL_DECISION":
            signal_decision_event_count += 1
            decision_fields = (
                "event_id", "candidate_id", "snapshot_id", "state",
                "action", "reason_code", "event_time", "source",
            )
            missing_decision_fields = []
            for field in decision_fields:
                if event.get(field) is not None and str(event[field]).strip():
                    signal_decision_field_coverage[field] += 1
                else:
                    missing_decision_fields.append(field)
            if missing_decision_fields:
                signal_decision_incomplete_event_count += 1
        action = str(event.get("action") or "").upper()
        if event.get("directive_id"):
            required_identity = ["candidate_id", "plan_id"]
            if not action:
                identity_incomplete_event_count += 1
            elif action.startswith(("EXIT", "SELL")):
                required_identity.append("exit_rule_id")
            if any(not str(event.get(field) or "").strip() for field in required_identity):
                identity_incomplete_event_count += 1
        if stage in {"REJECTED", "BLOCKED", "EXECUTION_BLOCKED"}:
            rejected_event_count += 1
            reject_reason = str(event.get("reject_code") or event.get("reject_reason") or "UNKNOWN")
            reject_reason_counts[reject_reason] += 1
            quality["reject_reason_counts"][reject_reason] += 1
        # A directive can emit multiple valid lifecycle events; only event_id
        # identifies duplicate event rows.
        event_id = str(event.get("event_id") or "")
        if event_id:
            event_id_present_count += 1
            if event_id in seen_events:
                duplicate_events += 1
            seen_events.add(event_id)
        if event.get("directive_id"):
            directive_ids.add(str(event["directive_id"]))
        if event.get("order_id"):
            order_ids.add(str(event["order_id"]))
            if event.get("directive_id"):
                linked_directive_ids.add(str(event["directive_id"]))
        related_orders = event.get("related_orders")
        if isinstance(related_orders, list):
            for order in related_orders:
                if not isinstance(order, dict):
                    continue
                if order.get("order_id"):
                    order_ids.add(str(order["order_id"]))
                    if event.get("directive_id"):
                        linked_directive_ids.add(str(event["directive_id"]))
        observed = _parse_time(event.get("observed_at") or event.get("source_time"))
        recorded = _parse_time(event.get("event_time") or event.get("timestamp"))
        if observed and recorded:
            if observed.tzinfo and not recorded.tzinfo:
                recorded = recorded.replace(tzinfo=observed.tzinfo)
            elif recorded.tzinfo and not observed.tzinfo:
                observed = observed.replace(tzinfo=recorded.tzinfo)
            delay_ms = max(0.0, (recorded - observed).total_seconds() * 1000.0)
            freshness_ms.append(delay_ms)
            quality["freshness_ms"].append(delay_ms)
        for field, target in (("mfe_pct", mfe), ("mae_pct", mae)):
            try:
                if event.get(field) is not None:
                    value = float(event[field])
                    target.append(value)
                    quality[field].append(value)
            except (TypeError, ValueError):
                pass
        try:
            if event.get("slippage_pct") is not None:
                value = float(event["slippage_pct"])
                slippage_pct.append(value)
                quality["slippage_pct"].append(value)
        except (TypeError, ValueError):
            pass
        try:
            if event.get("t1_delayed_exit") and event.get("planned_exit_price") and event.get("exit_fill_price"):
                expected = float(event["planned_exit_price"])
                fill = float(event["exit_fill_price"])
                if expected > 0:
                    value = max(0.0, (expected - fill) / expected * 100.0)
                    t1_delay_loss_pct.append(value)
                    quality["t1_delay_loss_pct"].append(value)
        except (TypeError, ValueError):
            pass

    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    group_rows = []
    for key, counts in sorted(groups.items()):
        quality = group_quality[key]
        event_count = quality["event_count"]
        group_rows.append({
            "source": key[0],
            "strategy": key[1],
            "tide_state": key[2],
            "cross_day_path": key[3],
            "counts": dict(counts),
            "quality": {
                "event_count": event_count,
                "field_coverage": {
                    field: {
                        "present_count": quality["field_present"][field],
                        "missing_count": event_count - quality["field_present"][field],
                    }
                    for field in ("event_id", "source", "strategy", "tide_state", "cross_day_path")
                },
                "freshness_sample_count": len(quality["freshness_ms"]),
                "mean_freshness_delay_ms": average(quality["freshness_ms"]),
                "mfe_sample_count": len(quality["mfe_pct"]),
                "mean_mfe_pct": average(quality["mfe_pct"]),
                "mae_sample_count": len(quality["mae_pct"]),
                "mean_mae_pct": average(quality["mae_pct"]),
                "rejected_event_count": sum(quality["reject_reason_counts"].values()),
                "reject_reason_counts": dict(quality["reject_reason_counts"]),
                "slippage_sample_count": len(quality["slippage_pct"]),
                "mean_slippage_pct": average(quality["slippage_pct"]),
                "t1_delayed_exit_sample_count": len(quality["t1_delay_loss_pct"]),
                "mean_t1_delay_loss_pct": average(quality["t1_delay_loss_pct"]),
            },
        })
    report = {
        "schema_version": 1,
        "generated_at": (as_of or dt.datetime.now().astimezone()).isoformat(),
        "status": "HEALTHY" if not errors else "DEGRADED",
        "input_files": [Path(path).name for path in input_paths],
        "event_count": len(events),
        "parse_errors": errors,
        "signal_funnel_counts": dict(stage_counts),
        "by_source_strategy_tide_cross_day": group_rows,
        "freshness": {"sample_count": len(freshness_ms), "mean_delay_ms": average(freshness_ms), "missing_or_invalid_samples": len(events) - len(freshness_ms)},
        "mfe": {"sample_count": len(mfe), "mean_pct": average(mfe)},
        "mae": {"sample_count": len(mae), "mean_pct": average(mae)},
        "execution": {
            "directive_count": len(directive_ids),
            "order_count": len(order_ids),
            "directive_without_order_count": len(directive_ids - linked_directive_ids),
            "duplicate_event_id_count": duplicate_events,
            "rejected_event_count": rejected_event_count,
            "reject_reason_counts": dict(reject_reason_counts),
            "mean_slippage_pct": average(slippage_pct),
            "slippage_sample_count": len(slippage_pct),
            "t1_delayed_exit_sample_count": len(t1_delay_loss_pct),
            "mean_t1_delay_loss_pct": average(t1_delay_loss_pct),
        },
        "closed_loop_quality": {
            "event_id_coverage_count": event_id_present_count,
            "event_id_coverage_rate": round(event_id_present_count / len(events), 4) if events else 0.0,
            "duplicate_event_id_count": duplicate_events,
            "required_field_coverage": {
                field: required_field_coverage[field]
                for field in ("source", "strategy", "tide_state", "cross_day_path")
            },
            "identity_field_coverage": {
                field: identity_field_coverage[field]
                for field in ("candidate_id", "plan_id", "exit_rule_id")
            },
            "identity_incomplete_event_count": identity_incomplete_event_count,
            "signal_decision_event_count": signal_decision_event_count,
            "signal_decision_field_coverage": {
                field: signal_decision_field_coverage[field]
                for field in (
                    "event_id", "candidate_id", "snapshot_id", "state",
                    "action", "reason_code", "event_time", "source",
                )
            },
            "signal_decision_incomplete_event_count": signal_decision_incomplete_event_count,
            "directive_count": len(directive_ids),
            "linked_directive_count": len(linked_directive_ids),
            "directive_without_order_count": len(directive_ids - linked_directive_ids),
            "order_count": len(order_ids),
            "eligible": bool(events)
            and not errors
            and event_id_present_count == len(events)
            and duplicate_events == 0
            and all(
                required_field_coverage[field] == len(events)
                for field in ("source", "strategy", "tide_state", "cross_day_path")
            )
            and bool(directive_ids)
            and bool(linked_directive_ids)
            and bool(order_ids)
            and identity_incomplete_event_count == 0
            and signal_decision_incomplete_event_count == 0,
        },
        "cross_source_strategy_overlap_baseline": _cross_source_overlap_baseline(events),
        "data_limitations": [
            "MFE/MAE、滑点、T+1 延迟损失仅对输入事件明确提供的字段统计，不从缺失流水推算。",
            "跨来源/策略重叠按相同代码、动作和 60 秒时间桶估算，仅作为候选重叠基线，不代表确认重复或噪声。",
            "输入仅按只读 JSONL 导出处理；本工具不连接数据库、不修改来源文件。",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="只读 ATS/TK PAPER 事件日报")
    parser.add_argument("inputs", nargs="+", help="ATS/TK 审计 JSONL 导出文件")
    parser.add_argument("--output", required=True, help="报告 JSON 输出路径")
    args = parser.parse_args()
    report = build_daily_report(args.inputs)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"{report['status']}: {report['event_count']} events -> {output}")


if __name__ == "__main__":
    main()

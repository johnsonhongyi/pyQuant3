# -*- coding: utf-8 -*-
"""Build a fail-closed ATS release manifest from frozen evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_if_readable(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return _sha256(path) if path.is_file() else ""
    except OSError:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], check=True, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return ""


def _valid_iso_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) < 10:
        return ""
    try:
        if len(text) == 10:
            return dt.date.fromisoformat(text).isoformat()
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _strict_iso_date(value: Any) -> str:
    if not isinstance(value, str) or len(value.strip()) != 10:
        return ""
    try:
        return dt.date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return ""


def _frozen_trade_dates(calendar: dict[str, Any]) -> list[str] | None:
    dates = calendar.get("trade_dates")
    source_hash = str(calendar.get("source_sha256") or "")
    if (
        not isinstance(calendar.get("schema_version"), int)
        or isinstance(calendar.get("schema_version"), bool)
        or calendar.get("schema_version") != 1
        or not str(calendar.get("exchange") or "").strip()
        or not str(calendar.get("source") or "").strip()
        or not _strict_iso_date(calendar.get("as_of"))
        or len(source_hash) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in source_hash)
        or not isinstance(dates, list)
        or len(dates) < 2
    ):
        return None
    parsed = [_strict_iso_date(value) for value in dates]
    if (
        any(not value for value in parsed)
        or parsed != sorted(set(parsed))
        or any(dt.date.fromisoformat(value).weekday() >= 5 for value in parsed)
    ):
        return None
    return parsed


def _consecutive_frozen_sessions(observed_dates: set[str], calendar_dates: list[str]) -> bool:
    if len(observed_dates) < 2:
        return False
    indexes = {date: index for index, date in enumerate(calendar_dates)}
    observed_indexes = sorted(indexes[date] for date in observed_dates if date in indexes)
    return (
        len(observed_indexes) == len(observed_dates)
        and observed_indexes[-1] - observed_indexes[0] + 1 == len(observed_indexes)
    )


def _is_zero(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number == 0.0
    except (TypeError, ValueError, OverflowError):
        return False


def verify_release(
    *, repo_root: Path, exe_path: Path, fingerprint_path: Path,
    replay_path: Path, reconciliation_path: Path, shadow_paths: list[Path],
    daily_report_path: Path | None = None,
    trading_calendar_path: Path | None = None,
    trading_calendar_source_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain"))
    blockers = []
    def _load_evidence(path: Path, label: str) -> dict[str, Any]:
        try:
            return _read_json(path) if path.is_file() else {}
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            blockers.append(f"{label}_invalid:{exc}")
            return {}
    fingerprint = _load_evidence(fingerprint_path, "fingerprint")
    replay = _load_evidence(replay_path, "replay")
    reconciliation = _load_evidence(reconciliation_path, "reconciliation")
    daily_report = (
        _load_evidence(daily_report_path, "daily_report")
        if daily_report_path is not None else {}
    )
    trading_calendar = (
        _load_evidence(trading_calendar_path, "trading_calendar")
        if trading_calendar_path is not None else {}
    )
    frozen_dates = _frozen_trade_dates(trading_calendar) if trading_calendar_path is not None else None
    calendar_source_sha256 = _sha256_if_readable(trading_calendar_source_path)
    trading_calendar_valid = (
        trading_calendar_path is not None
        and trading_calendar_source_path is not None
        and trading_calendar_path.is_file()
        and bool(calendar_source_sha256)
        and frozen_dates is not None
        and str(trading_calendar.get("source_sha256") or "").lower() == calendar_source_sha256
    )
    shadow_rows = []
    shadow_reports_valid = True
    for path in shadow_paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if isinstance(row, dict):
                        shadow_rows.append(row)
                    else:
                        shadow_reports_valid = False
                        blockers.append(f"shadow_report_invalid_row:{path.name}")
        except (OSError, json.JSONDecodeError) as exc:
            shadow_reports_valid = False
            blockers.append(f"shadow_report_invalid:{path.name}:{exc}")

    dates = set()
    shadow_dates_valid = bool(shadow_rows)
    for row in shadow_rows:
        value = str(row.get("trade_date") or row.get("timestamp") or "")
        parsed_date = _valid_iso_date(value)
        if parsed_date:
            dates.add(parsed_date)
        else:
            shadow_dates_valid = False
    replay_checks = replay.get("checks")
    required_replay_checks = {
        "duplicate_rate_zero",
        "zero_price_zero",
        "timestamps_monotonic",
        "account_reconciliation",
        "t1_position_facts",
        "EXIT_BUY_contract",
        "build_identity",
        "invalidated_buy_zero",
        "risk_reward_floor",
        "t1_exit_recall_100",
        "duplicate_order_zero",
        "t0_sell_zero",
    }
    replay_passed = (
        replay.get("passed") is True
        and isinstance(replay_checks, dict)
        and required_replay_checks.issubset(replay_checks)
        and all(replay_checks.get(name) is True for name in required_replay_checks)
    )
    reconciliation_zero = (
        reconciliation.get("status") == "ALIGNED"
        and reconciliation.get("ledger_status") == "ALIGNED"
        and _is_zero(reconciliation.get("changed_count"))
        and reconciliation.get("snapshot_only_codes") == []
        and reconciliation.get("order_only_codes") == []
        and reconciliation.get("differences") == []
    )
    for count_name in ("mismatch_count", "oversell_count", "duplicate_order_count", "t0_sell_count"):
        if count_name in reconciliation:
            reconciliation_zero = reconciliation_zero and _is_zero(reconciliation[count_name])
    shadow_healthy = bool(shadow_rows) and all(row.get("status") == "HEALTHY" for row in shadow_rows)
    broker_orders_zero = bool(shadow_rows) and all(
        _is_zero(row.get("real_broker_orders")) for row in shadow_rows
    )
    shadow_directive_audit_complete = bool(shadow_rows) and all(
        isinstance(row.get("ledger_stats"), dict)
        and row["ledger_stats"].get("pipeline_status") == "ATS_ARBITRATED_ISOLATED_TK_PAPER"
        and isinstance(row["ledger_stats"].get("directive_count"), int)
        and not isinstance(row["ledger_stats"].get("directive_count"), bool)
        and row["ledger_stats"].get("directive_count") >= 0
        and isinstance(row["ledger_stats"].get("paper_result_count"), int)
        and not isinstance(row["ledger_stats"].get("paper_result_count"), bool)
        and row["ledger_stats"].get("paper_result_count") >= 0
        and row["ledger_stats"].get("paper_result_count") == row["ledger_stats"].get("directive_count")
        and isinstance(row["ledger_stats"].get("directive_audit"), list)
        and len(row["ledger_stats"]["directive_audit"]) == row["ledger_stats"].get("directive_count")
        and all(
            isinstance(item, dict)
            and all(str(item.get(field) or "").strip() for field in ("directive_id", "request_id", "status"))
            for item in row["ledger_stats"]["directive_audit"]
        )
        for row in shadow_rows
    )
    overlap = daily_report.get("cross_source_strategy_overlap_baseline")
    eligible_overlap_events = overlap.get("eligible_event_count") if isinstance(overlap, dict) else None
    overlapping_events = overlap.get("overlapping_event_count") if isinstance(overlap, dict) else None
    overlap_rate = overlap.get("overlapping_event_rate") if isinstance(overlap, dict) else None
    overlap_counts_valid = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in (
            eligible_overlap_events,
            overlapping_events,
            overlap.get("overlap_cluster_count") if isinstance(overlap, dict) else None,
            overlap.get("missing_signature_count") if isinstance(overlap, dict) else None,
        )
    )
    try:
        overlap_rate_value = float(overlap_rate)
        overlap_rate_valid = math.isfinite(overlap_rate_value) and 0.0 <= overlap_rate_value <= 1.0
    except (TypeError, ValueError, OverflowError):
        overlap_rate_valid = False
    closed_loop_quality = daily_report.get("closed_loop_quality")
    daily_event_count = daily_report.get("event_count")
    if not isinstance(daily_event_count, int) or isinstance(daily_event_count, bool):
        daily_event_count = -1
    signal_decision_event_count = (
        closed_loop_quality.get("signal_decision_event_count")
        if isinstance(closed_loop_quality, dict) else None
    )
    if not isinstance(signal_decision_event_count, int) or isinstance(signal_decision_event_count, bool):
        signal_decision_event_count = -1
    identity_coverage = (
        closed_loop_quality.get("identity_field_coverage")
        if isinstance(closed_loop_quality, dict) else None
    )
    identity_incomplete_count = (
        closed_loop_quality.get("identity_incomplete_event_count")
        if isinstance(closed_loop_quality, dict) else None
    )
    signal_decision_coverage = (
        closed_loop_quality.get("signal_decision_field_coverage")
        if isinstance(closed_loop_quality, dict) else None
    )
    signal_decision_incomplete_count = (
        closed_loop_quality.get("signal_decision_incomplete_event_count")
        if isinstance(closed_loop_quality, dict) else None
    )
    identity_complete = (
        isinstance(identity_coverage, dict)
        and all(
            isinstance(identity_coverage.get(field), int)
            and not isinstance(identity_coverage.get(field), bool)
            and 0 <= identity_coverage.get(field) <= daily_event_count
            for field in ("candidate_id", "plan_id", "exit_rule_id")
        )
        and isinstance(identity_incomplete_count, int)
        and not isinstance(identity_incomplete_count, bool)
        and identity_incomplete_count == 0
    )
    signal_decision_complete = (
        isinstance(signal_decision_coverage, dict)
        and all(
            isinstance(signal_decision_coverage.get(field), int)
            and not isinstance(signal_decision_coverage.get(field), bool)
            and 0 <= signal_decision_coverage.get(field) <= signal_decision_event_count
            for field in (
                "event_id", "candidate_id", "snapshot_id", "state",
                "action", "reason_code", "event_time", "source",
            )
        )
        and isinstance(signal_decision_incomplete_count, int)
        and not isinstance(signal_decision_incomplete_count, bool)
        and signal_decision_incomplete_count == 0
    )
    daily_signal_baseline_present = (
        daily_report.get("status") == "HEALTHY"
        and isinstance(daily_report.get("event_count"), int)
        and not isinstance(daily_report.get("event_count"), bool)
        and daily_report.get("event_count", 0) > 0
        and isinstance(daily_report.get("closed_loop_quality"), dict)
        and daily_report["closed_loop_quality"].get("eligible") is True
        and isinstance(daily_report["closed_loop_quality"].get("duplicate_event_id_count"), int)
        and not isinstance(daily_report["closed_loop_quality"].get("duplicate_event_id_count"), bool)
        and daily_report["closed_loop_quality"].get("duplicate_event_id_count") == 0
        and isinstance(daily_report["closed_loop_quality"].get("event_id_coverage_count"), int)
        and not isinstance(daily_report["closed_loop_quality"].get("event_id_coverage_count"), bool)
        and daily_report["closed_loop_quality"].get("event_id_coverage_count") == daily_report["event_count"]
        and isinstance(daily_report["closed_loop_quality"].get("linked_directive_count"), int)
        and not isinstance(daily_report["closed_loop_quality"].get("linked_directive_count"), bool)
        and daily_report["closed_loop_quality"].get("linked_directive_count", 0) > 0
        and identity_complete
        and signal_decision_complete
        and isinstance(daily_report["closed_loop_quality"].get("required_field_coverage"), dict)
        and all(
            isinstance(daily_report["closed_loop_quality"]["required_field_coverage"].get(field), int)
            and not isinstance(daily_report["closed_loop_quality"]["required_field_coverage"].get(field), bool)
            and daily_report["closed_loop_quality"]["required_field_coverage"].get(field) == daily_report["event_count"]
            for field in ("source", "strategy", "tide_state", "cross_day_path")
        )
        and isinstance(overlap, dict)
        and bool(str(overlap.get("method") or "").strip())
        and overlap_counts_valid
        and eligible_overlap_events > 0
        and overlapping_events <= eligible_overlap_events
        and overlap_rate_valid
    )
    exe_sha256 = _sha256_if_readable(exe_path)
    expected_fingerprint = str(fingerprint.get("fingerprint") or "")
    shadow_build_identity_matches = bool(shadow_rows and commit and expected_fingerprint and exe_sha256) and all(
        isinstance(row.get("build_identity"), dict)
        and row["build_identity"].get("git_commit") == commit
        and row["build_identity"].get("git_dirty") is False
        and row["build_identity"].get("fingerprint") == expected_fingerprint
        and row["build_identity"].get("exe_sha256") == exe_sha256
        and row["build_identity"].get("frozen_runtime") is True
        for row in shadow_rows
    )
    checks = {
        "clean_working_tree": bool(commit) and not dirty,
        "exe_present": exe_path.is_file(),
        "fingerprint_commit_matches": bool(commit) and fingerprint.get("git_commit") == commit and fingerprint.get("release_ready") is True,
        "replay_passed": replay_passed,
        "account_reconciliation_aligned": reconciliation_zero,
        "shadow_days_at_least_two": (
            shadow_dates_valid
            and trading_calendar_valid
            and frozen_dates is not None
            and _consecutive_frozen_sessions(dates, frozen_dates)
        ),
        "trading_calendar_valid": trading_calendar_valid,
        "shadow_reports_valid": shadow_reports_valid,
        "shadow_build_identity_matches": shadow_build_identity_matches,
        "shadow_reports_healthy": shadow_healthy,
        "shadow_paper_connected": bool(shadow_rows) and all(
            row.get("paper_execution") == "CONNECTED"
            and row.get("paper_execution_scope") == "ISOLATED"
            for row in shadow_rows
        ),
        "shadow_directive_audit_complete": shadow_directive_audit_complete,
        "daily_signal_baseline_present": daily_signal_baseline_present,
        "daily_signal_identity_complete": identity_complete,
        "daily_signal_decision_complete": signal_decision_complete,
        "real_broker_orders_zero": broker_orders_zero,
    }
    for name, passed in checks.items():
        if not passed:
            blockers.append(name)
    return {
        "schema_version": 1,
        "status": "GO" if all(checks.values()) else "MONITOR_ONLY",
        "git_commit": commit or "unknown",
        "git_dirty": dirty,
        "exe_path": str(exe_path.resolve()),
        "exe_sha256": exe_sha256,
        "fingerprint_path": str(fingerprint_path.resolve()),
        "fingerprint_sha256": _sha256_if_readable(fingerprint_path),
        "replay_sha256": _sha256_if_readable(replay_path),
        "reconciliation_sha256": _sha256_if_readable(reconciliation_path),
        "daily_report_sha256": _sha256_if_readable(daily_report_path),
        "trading_calendar_sha256": _sha256_if_readable(trading_calendar_path),
        "trading_calendar_source_path": (
            str(trading_calendar_source_path.resolve())
            if trading_calendar_source_path is not None else ""
        ),
        "trading_calendar_source_sha256": calendar_source_sha256,
        "shadow_report_sha256": {
            str(path): digest for path in shadow_paths
            if (digest := _sha256_if_readable(path))
        },
        "shadow_days": sorted(dates),
        "checks": checks,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ATS fail-closed release verification")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--daily-report", type=Path, required=True)
    parser.add_argument("--trading-calendar", type=Path)
    parser.add_argument("--trading-calendar-source", type=Path)
    parser.add_argument("--shadow-report", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_release(
        repo_root=args.repo_root, exe_path=args.exe, fingerprint_path=args.fingerprint,
        replay_path=args.replay, reconciliation_path=args.reconciliation,
        daily_report_path=args.daily_report,
        shadow_paths=args.shadow_report,
        trading_calendar_path=args.trading_calendar,
        trading_calendar_source_path=args.trading_calendar_source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{manifest['status']}: blockers={len(manifest['blockers'])} -> {args.output}")
    return 0 if manifest["status"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Frozen replay and release checks for the subnew-stock execution chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import Any, Dict, Iterable, List, Optional

from ats.strategy.signal_convergence import check_exit_buy_contract


@dataclass(frozen=True)
class ReplayReleaseResult:
    passed: bool
    checks: Dict[str, bool]
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "details": dict(self.details),
        }


def _event_key(item: Dict[str, Any]) -> str:
    if item.get("event_key"):
        return str(item["event_key"])
    timestamp = str(item.get("timestamp") or item.get("ts") or "")
    return "|".join((
        timestamp[:10],
        str(item.get("code") or "").strip().zfill(6),
        str(item.get("signal_type") or item.get("action") or ""),
        str(item.get("source") or ""),
    ))


def _timestamp_value(item: Dict[str, Any]) -> float:
    raw = item.get("timestamp", item.get("ts"))
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


class ReplayReleaseGate:
    """Pure release gate: no execution and no external network access."""

    def evaluate(
        self,
        *,
        frames: Iterable[Dict[str, Any]],
        directives: Iterable[Any],
        read_model: Optional[Dict[str, Any]] = None,
        expected_build: str = "",
        actual_build: str = "",
    ) -> ReplayReleaseResult:
        rows = [dict(item) for item in (frames or []) if isinstance(item, dict)]
        keys = [_event_key(item) for item in rows if _event_key(item)]
        duplicate_count = max(0, len(keys) - len(set(keys)))
        duplicate_rate = (float(duplicate_count) / len(keys)) if keys else 0.0

        zero_price_rows = []
        for item in rows:
            if "price" not in item:
                continue
            try:
                price = float(item.get("price") or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            if price <= 0:
                zero_price_rows.append(_event_key(item))

        timestamps = [_timestamp_value(item) for item in rows if _timestamp_value(item) > 0]
        monotonic = all(b >= a for a, b in zip(timestamps, timestamps[1:]))

        exit_buy_ok, violations = check_exit_buy_contract(directives or [])
        model = dict(read_model or {})
        reconciliation = dict(model.get("reconciliation") or {})
        recon_status = str(reconciliation.get("status") or "")
        reconciliation_ok = recon_status in {"ALIGNED", "ALIGNED_WITH_CHANGES"}

        t1_violations: List[str] = []
        positions = model.get("positions", {})
        if not isinstance(positions, dict):
            positions = {}
            t1_violations.append("POSITIONS_NOT_MAPPING")
        for code, raw in positions.items():
            if not isinstance(raw, dict):
                t1_violations.append("%s:INVALID_POSITION" % code)
                continue
            try:
                total = max(0.0, float(raw.get("total_qty", raw.get("volume", 0.0)) or 0.0))
                sellable = max(0.0, float(raw.get("sellable_qty", 0.0) or 0.0))
                today = max(0.0, float(raw.get("today_buy_qty", 0.0) or 0.0))
            except (TypeError, ValueError):
                t1_violations.append("%s:INVALID_QTY" % code)
                continue
            if sellable > total + 1e-9:
                t1_violations.append("%s:SELLABLE_GT_TOTAL" % code)
            if today > total + 1e-9:
                t1_violations.append("%s:TODAY_BUY_GT_TOTAL" % code)
            if sellable + today > total + 1e-9:
                t1_violations.append("%s:T1_FACTS_OVERALLOCATED" % code)
            if "unresolved_qty" in raw:
                try:
                    unresolved = max(0.0, float(raw.get("unresolved_qty", 0.0) or 0.0))
                except (TypeError, ValueError):
                    t1_violations.append("%s:INVALID_UNRESOLVED_QTY" % code)
                else:
                    if sellable + today + unresolved > total + 1e-9:
                        t1_violations.append("%s:T1_FACTS_OVERALLOCATED" % code)

        build_ok = True
        if expected_build:
            build_ok = bool(actual_build) and str(actual_build) == str(expected_build)

        checks = {
            "duplicate_rate_zero": duplicate_count == 0,
            "zero_price_zero": len(zero_price_rows) == 0,
            "timestamps_monotonic": monotonic,
            "account_reconciliation": reconciliation_ok,
            "t1_position_facts": len(t1_violations) == 0,
            "EXIT_BUY_contract": exit_buy_ok,
            "build_identity": build_ok,
        }
        details = {
            "frame_count": len(rows),
            "duplicate_count": duplicate_count,
            "duplicate_rate": duplicate_rate,
            "zero_price_count": len(zero_price_rows),
            "zero_price_keys": zero_price_rows[:20],
            "exit_buy_violations": violations,
            "t1_violations": t1_violations,
            "reconciliation_status": recon_status,
            "expected_build": expected_build,
            "actual_build": actual_build,
        }
        return ReplayReleaseResult(all(checks.values()), checks, details)

    @staticmethod
    def freeze_frames(frames: Iterable[Dict[str, Any]], path: str) -> str:
        rows = [dict(item) for item in (frames or []) if isinstance(item, dict)]
        payload = {
            "snapshot_version": "2.0",
            "frozen_at": datetime.now().isoformat(timespec="seconds"),
            "frames": rows,
        }
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp, path)
        return path

    @staticmethod
    def load_frozen_frames(path: str) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if str(payload.get("snapshot_version")) != "2.0":
            raise ValueError("unsupported replay snapshot version")
        frames = payload.get("frames")
        if not isinstance(frames, list):
            raise ValueError("invalid replay frames")
        return [dict(item) for item in frames if isinstance(item, dict)]

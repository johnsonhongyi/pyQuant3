# -*- coding: utf-8 -*-
"""Frozen replay and release checks for the subnew-stock execution chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional

from ats.strategy.signal_convergence import check_exit_buy_contract


ENTRY_ACTIONS = frozenset({"BUY", "BUY_SCOUT", "BUY_CONFIRM"})
EXIT_ACTIONS = frozenset({"SELL", "EXIT_ALL", "REDUCE", "REDUCE_30", "REDUCE_HALF", "EXIT", "STOP_LOSS"})
MIN_RR_THRESHOLD = 2.5


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _action(item: Any) -> str:
    return str(_value(item, "action", "") or "").strip().upper()


def _candidate_id(item: Any) -> str:
    envelope = _value(item, "audit_envelope", {}) or {}
    return str(_value(item, "candidate_id", "") or _value(envelope, "candidate_id", "") or "")


def _rr_value(item: Any) -> Optional[float]:
    raw = _value(item, "rr_now", None)
    if raw is None:
        raw = _value(item, "planned_reward_risk", None)
    if raw is None:
        raw = _value(item, "reward_risk_ratio", None)
    if raw is None:
        plan = _value(item, "trade_plan", None)
        raw = _value(plan, "rr_now", None)
        if raw is None:
            raw = _value(plan, "planned_reward_risk", None)
        if raw is None and plan is not None:
            try:
                current = float(_value(item, "validation_price", 0.0) or _value(item, "price", 0.0) or 0.0)
                stop = float(
                    _value(plan, "structural_stop", 0.0)
                    or _value(plan, "higher_low_stop", 0.0)
                    or _value(plan, "base_low_invalid", 0.0)
                    or 0.0
                )
                target = float(
                    _value(plan, "structural_target", 0.0)
                    or _value(plan, "target_1_channel_mid", 0.0)
                    or 0.0
                )
                if current > stop > 0 and target > current:
                    raw = (target - current) / (current - stop)
            except (TypeError, ValueError):
                raw = None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


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
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if math.isfinite(value) else 0.0
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        return value if math.isfinite(value) else 0.0
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
            raw_price = item.get("price")
            if isinstance(raw_price, bool):
                zero_price_rows.append(_event_key(item))
                continue
            try:
                price = float(raw_price or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            if not math.isfinite(price) or price <= 0:
                zero_price_rows.append(_event_key(item))

        timestamps = [_timestamp_value(item) for item in rows]
        monotonic = bool(rows) and all(value > 0 for value in timestamps) and all(
            b >= a for a, b in zip(timestamps, timestamps[1:])
        )

        directive_rows = list(directives or [])
        exit_buy_ok, violations = check_exit_buy_contract(directive_rows)
        model = dict(read_model or {})
        reconciliation = dict(model.get("reconciliation") or {})
        recon_status = str(reconciliation.get("status") or "")
        account = model.get("account")
        account = account if isinstance(account, dict) else {}
        paper_execution_ready = account.get("paper_execution_ready") is True
        reconciliation_ok = recon_status == "ALIGNED" and paper_execution_ready

        invalidated_rows = [
            item for item in rows
            if str(item.get("signal_state") or item.get("lifecycle_state") or "").upper() == "INVALIDATED"
        ]
        invalidated_candidates = {
            str(item.get("candidate_id") or "")
            for item in invalidated_rows
        }
        invalidated_missing_id_count = sum(not str(item.get("candidate_id") or "") for item in invalidated_rows)
        invalidated_candidates.discard("")
        invalidated_buy_ids = sorted(
            candidate_id for candidate_id in invalidated_candidates
            if any(_action(d) in ENTRY_ACTIONS and _candidate_id(d) == candidate_id for d in directive_rows)
        )
        unlinked_entry_count = sum(
            _action(d) in ENTRY_ACTIONS and not _candidate_id(d) for d in directive_rows
        )

        entry_directives = [d for d in directive_rows if _action(d) in ENTRY_ACTIONS]
        rr_values = [_rr_value(d) for d in entry_directives]
        rr_missing_count = sum(value is None for value in rr_values)
        rr_below_floor = [
            str(_value(d, "directive_id", "") or _candidate_id(d) or _value(d, "code", ""))
            for d, value in zip(entry_directives, rr_values)
            if value is not None and value < MIN_RR_THRESHOLD
        ]

        expected_t1_exit_ids = {
            str(item.get("exit_intent_id") or item.get("directive_id") or "")
            for item in rows if item.get("expected_t1_exit") is True
        }
        expected_t1_exit_ids.discard("")
        recalled_t1_exit_ids = {
            str(_value(d, "exit_intent_id", "") or _value(d, "directive_id", "") or "")
            for d in directive_rows
            if _action(d) in EXIT_ACTIONS
            and (
                _value(d, "exit_intent_id", "") or _value(d, "directive_id", "")
                or _value(_value(d, "audit_envelope", {}) or {}, "exit_intent_id", "")
            )
        }
        missed_t1_exit_ids = sorted(expected_t1_exit_ids - recalled_t1_exit_ids)

        order_ids = []
        for directive in directive_rows:
            envelope = _value(directive, "audit_envelope", {}) or {}
            order_id = str(_value(directive, "order_id", "") or _value(envelope, "order_id", "") or "").strip()
            if order_id:
                order_ids.append(order_id)
        duplicate_order_ids = sorted({order_id for order_id in order_ids if order_ids.count(order_id) > 1})
        t0_sell_count = reconciliation.get("t0_sell_count")
        try:
            t0_sell_zero = t0_sell_count is not None and float(t0_sell_count) == 0.0
        except (TypeError, ValueError):
            t0_sell_zero = False

        t1_violations: List[str] = []
        positions = model.get("positions", {})
        if not isinstance(positions, dict):
            positions = {}
            t1_violations.append("POSITIONS_NOT_MAPPING")
        for code, raw in positions.items():
            if not isinstance(raw, dict):
                t1_violations.append("%s:INVALID_POSITION" % code)
                continue
            required_fields = {"sellable_qty", "today_buy_qty", "unresolved_qty"}
            missing_fields = sorted(required_fields.difference(raw))
            if not ("total_qty" in raw or "volume" in raw):
                missing_fields.append("total_qty")
            if missing_fields:
                t1_violations.append("%s:MISSING_T1_FIELDS:%s" % (code, ",".join(missing_fields)))
                continue
            if any(isinstance(raw.get(field), bool) for field in (
                "total_qty", "volume", "sellable_qty", "today_buy_qty", "unresolved_qty"
            )):
                t1_violations.append("%s:INVALID_QTY" % code)
                continue
            try:
                total = float(raw.get("total_qty", raw.get("volume", 0.0)))
                sellable = float(raw.get("sellable_qty"))
                today = float(raw.get("today_buy_qty"))
            except (TypeError, ValueError):
                t1_violations.append("%s:INVALID_QTY" % code)
                continue
            if any(not math.isfinite(value) or value < 0 for value in (total, sellable, today)):
                t1_violations.append("%s:INVALID_QTY" % code)
                continue
            if sellable > total + 1e-9:
                t1_violations.append("%s:SELLABLE_GT_TOTAL" % code)
            if today > total + 1e-9:
                t1_violations.append("%s:TODAY_BUY_GT_TOTAL" % code)
            if sellable + today > total + 1e-9:
                t1_violations.append("%s:T1_FACTS_OVERALLOCATED" % code)
            try:
                unresolved = float(raw.get("unresolved_qty"))
            except (TypeError, ValueError):
                t1_violations.append("%s:INVALID_UNRESOLVED_QTY" % code)
            else:
                if not math.isfinite(unresolved) or unresolved < 0:
                    t1_violations.append("%s:INVALID_UNRESOLVED_QTY" % code)
                    continue
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
            "invalidated_buy_zero": (
                len(invalidated_buy_ids) == 0
                and invalidated_missing_id_count == 0
                and (not invalidated_candidates or unlinked_entry_count == 0)
                and not any(
                    _action(d) in ENTRY_ACTIONS
                    and str(_value(d, "signal_state", "") or "").upper() == "INVALIDATED"
                    for d in directive_rows
                )
            ),
            "risk_reward_floor": bool(entry_directives) and rr_missing_count == 0 and not rr_below_floor,
            "t1_exit_recall_100": bool(expected_t1_exit_ids) and not missed_t1_exit_ids,
            "duplicate_order_zero": not duplicate_order_ids,
            "t0_sell_zero": t0_sell_zero,
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
            "paper_execution_ready": paper_execution_ready,
            "paper_execution_block_reason": str(account.get("paper_execution_block_reason") or ""),
            "expected_build": expected_build,
            "actual_build": actual_build,
            "invalidated_candidate_count": len(invalidated_candidates),
            "invalidated_missing_id_count": invalidated_missing_id_count,
            "unlinked_entry_count": unlinked_entry_count,
            "invalidated_buy_candidate_ids": invalidated_buy_ids,
            "entry_directive_count": len(entry_directives),
            "rr_missing_count": rr_missing_count,
            "rr_floor": MIN_RR_THRESHOLD,
            "rr_below_floor_directives": rr_below_floor,
            "expected_t1_exit_count": len(expected_t1_exit_ids),
            "missed_t1_exit_ids": missed_t1_exit_ids,
            "duplicate_order_ids": duplicate_order_ids,
            "t0_sell_count": t0_sell_count,
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

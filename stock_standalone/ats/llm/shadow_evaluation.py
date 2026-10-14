"""Evaluate persisted advisory responses against later reviewed outcomes, without orders."""

from __future__ import annotations

from sys_utils import safe_resolve_path

import hashlib
import json
import sqlite3
import os
import re
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from uuid import uuid4

from ats.llm.agent_contracts import validate_agent_envelope
from ats.llm.offline_learning import _time, compute_input_snapshot_hash, validate_input_snapshot
from ats.llm.request_producer import signal_max_age_seconds
from ats.strategy.ipo_outcome_review import _verified_evidence, load_latest_outcome_reviews

POLICY_VERSION = "ipo.shadow-direction.v1"


def _report_hash(report: dict) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in report.items() if k != "report_hash"},
                                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def evaluate_shadow_records(records: list[dict], config: Any, *, generated_at: str | None = None) -> dict:
    """A score >=50 is a research direction hint, never an ENTRY/order decision."""
    now = _time(generated_at or datetime.now(timezone.utc).isoformat(), "generated_at")
    report: dict[str, Any] = {
        "schema_version": POLICY_VERSION, "generated_at": now.isoformat(),
        "state": "WAITING_MODEL_RESULTS", "record_count": len(records),
        "configuration_hash": config.config_hash, "data_contract_hash": config.data_contract.config_hash,
        "order_submitted": False, "entry_authorized": False, "model_promoted": False,
        "training_performed": False, "positive_hint_threshold": 50,
        "target": "D1 close above issue price; advisory direction only",
        "groups": [], "rejected": [], "pending_outcome_count": 0, "pending_review_count": 0,
        "future_leakage_count": 0, "duplicate_count": 0,
        "p95_latency_ms": {"status": "NOT_EVALUABLE", "reason": "request start timestamps are not persisted"},
    }
    groups: dict[tuple, dict[tuple, dict]] = {}
    for record in records:
        request_id = str(record.get("request_id", ""))
        try:
            envelope = validate_agent_envelope(record["envelope"])
            if envelope["agent_type"] != "MARKET_REGIME":
                continue
            metadata = envelope["metadata"]
            if request_id != metadata["request_id"]:
                raise ValueError("REQUEST_ID_MISMATCH")
            snapshot = record["snapshot"]
            inputs = validate_input_snapshot(snapshot["input_snapshot"], config)
            digest = compute_input_snapshot_hash(inputs)
            cutoff = _time(snapshot["cutoff"], "cutoff")
            generated = _time(metadata["generated_at"], "response.generated_at")
            if (digest != snapshot["snapshot_hash"] or metadata["evidence_ids"] != [digest]
                    or metadata["ticker"] != snapshot["ticker"]
                    or cutoff != _time(metadata["as_of_time"], "response.as_of_time")
                    or cutoff != _time(inputs["as_of_time"], "input.as_of_time")):
                raise ValueError("SNAPSHOT_BINDING_INVALID")
            if not 0 <= (generated - cutoff).total_seconds() <= signal_max_age_seconds(config) or generated > now:
                raise ValueError("LATE_OR_FUTURE_RESPONSE")
            outcome = record.get("outcome")
            if outcome is None:
                report["pending_outcome_count"] += 1
                continue
            if not _verified_evidence(outcome) or not isinstance(outcome.get("d1_positive"), bool):
                raise ValueError("OUTCOME_INVALID")
            listing_date = cutoff.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            if outcome["ticker"] != snapshot["ticker"] or outcome["listing_date"] != listing_date:
                raise ValueError("OUTCOME_IDENTITY_MISMATCH")
            matured = _time(outcome["matured_at"], "outcome.matured_at")
            source_as_of = _time(outcome["source"]["as_of_time"], "outcome.as_of_time")
            available = _time(outcome["source"]["available_at"], "outcome.available_at")
            sessions = outcome["sessions"]
            days = [datetime.fromisoformat(row["date"]).date() for row in sessions]
            if len(days) != 3 or days != sorted(set(days)) or days[0].isoformat() <= listing_date:
                raise ValueError("OUTCOME_SESSION_INVALID")
            d1_close = datetime.combine(days[0], datetime.min.time(), ZoneInfo("Asia/Shanghai")).replace(hour=15)
            d3_close = datetime.combine(days[2], datetime.min.time(), ZoneInfo("Asia/Shanghai")).replace(hour=15)
            if generated >= d1_close or matured != d3_close or not cutoff < matured <= source_as_of <= available <= now:
                raise ValueError("OUTCOME_TIME_LEAKAGE")
            review = record.get("review") or {}
            if review.get("decision") != "ACCEPTED" or review.get("evidence_hash") != outcome["evidence_hash"]:
                report["pending_review_count"] += 1
                continue
            reviewed = _time(review["reviewed_at_utc"], "review.reviewed_at")
            if reviewed < available or reviewed > now or not str(review.get("reviewer", "")).strip():
                raise ValueError("REVIEW_TIME_INVALID")
            provider = record.get("provider_id")
            if not isinstance(provider, str) or not provider:
                raise ValueError("PROVIDER_ID_MISSING")
            group_key = (provider, metadata["model_id"], metadata["prompt_version"])
            cohort_key = (snapshot["ticker"], listing_date)
            sample = {"request_id": request_id, "ticker": snapshot["ticker"],
                      "cutoff": cutoff, "available": reviewed, "generated": generated,
                      "positive": envelope["payload"]["sentiment_score"] >= 50,
                      "label": outcome["d1_positive"], "snapshot_hash": digest,
                      "outcome_evidence_id": outcome["evidence_id"]}
            cohort = groups.setdefault(group_key, {})
            previous = cohort.get(cohort_key)
            if previous is not None:
                report["duplicate_count"] += 1
            if previous is None or (cutoff, generated, request_id) < (
                    previous["cutoff"], previous["generated"], previous["request_id"]):
                cohort[cohort_key] = sample
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
            reason = str(exc)[:180]
            if reason in {"OUTCOME_TIME_LEAKAGE", "LATE_OR_FUTURE_RESPONSE"}:
                report["future_leakage_count"] += 1
            report["rejected"].append({"request_id": request_id, "reason": reason})
    for (provider, model, prompt), cohort in sorted(groups.items()):
        samples = sorted(cohort.values(), key=lambda row: (row["cutoff"], row["request_id"]))
        split = max(1, int(len(samples) * 0.7))
        forward = samples[split:]
        boundary = forward[0]["cutoff"] if forward else None
        train = [row for row in samples[:split] if boundary is not None and row["available"] < boundary]
        ready = len(samples) >= 8 and len(train) >= 5 and len(forward) >= 2
        row = {"provider_id": provider, "model_id": model, "prompt_version": prompt,
               "sample_count": len(samples), "prior_count": len(train), "forward_count": len(forward),
               "purged_count": split - len(train), "forward_cutoff": boundary.isoformat() if boundary else None,
               "state": "EVALUATED" if ready else "INSUFFICIENT_SAMPLES", "metrics": {},
               "samples": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                            for k, v in item.items()} for item in samples]}
        if ready:
            baseline_positive = sum(item["label"] for item in train) / len(train) >= 0.5
            positive = sum(item["label"] for item in forward)
            negative = len(forward) - positive
            row["metrics"] = {
                "direction_accuracy": sum(item["positive"] == item["label"] for item in forward) / len(forward),
                "prior_baseline_accuracy": sum(item["label"] == baseline_positive for item in forward) / len(forward),
                "false_positive_rate": sum(item["positive"] and not item["label"] for item in forward) / negative if negative else None,
                "miss_rate": sum(not item["positive"] and item["label"] for item in forward) / positive if positive else None,
                "positive_denominator": positive, "negative_denominator": negative,
                "forward_denominator": len(forward), "prior_denominator": len(train),
            }
        report["groups"].append(row)
    report["evaluated_group_count"] = sum(row["state"] == "EVALUATED" for row in report["groups"])
    if report["evaluated_group_count"]:
        report["state"] = "SHADOW_EVALUATED"
    elif groups:
        report["state"] = "WAITING_MORE_SAMPLES"
    elif report["pending_review_count"]:
        report["state"] = "WAITING_HUMAN_REVIEW"
    elif report["pending_outcome_count"]:
        report["state"] = "WAITING_MATURED_OUTCOMES"
    elif records:
        report["state"] = "UNREADY"
    report["rejected_count"] = len(report["rejected"])
    report["report_hash"] = _report_hash(report)
    return report


def collect_shadow_evaluation(root: str | Path) -> dict:
    """Read the latest 100 verified journal entries; never invoke a Provider."""
    from ats.llm.interaction_journal import read_verified_shadow_interactions
    from ats.llm.learning_snapshot_store import get_snapshot_record
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

    base = safe_resolve_path(Path(root))
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(base / "config/ipo_sentiment.yaml"))
        if not config.verify_integrity():
            raise ValueError("CONFIG_INTEGRITY_INVALID")
        journal = read_verified_shadow_interactions(base, limit=100)
        integrity = str(journal.get("integrity", ""))
        if journal["status"] == "UNAVAILABLE":
            raise ValueError("JOURNAL_NOT_DURABLE_OR_INVALID:" + integrity)
        interactions = journal["interactions"]
        review_database = base / "data/ipo_learning/outcome_reviews.sqlite"
        if review_database.is_file():
            with closing(sqlite3.connect(review_database.as_uri() + "?mode=ro", uri=True, timeout=0.2)) as conn:
                conn.execute("SELECT COUNT(*) FROM outcome_reviews").fetchone()
        reviews = load_latest_outcome_reviews(base)
        outcomes = {}
        for path in (base / "data/ipo_learning/outcome_evidence").glob("*.json"):
            if path.stat().st_size <= 64 * 1024:
                document = json.loads(path.read_text(encoding="utf-8"))
                if _verified_evidence(document):
                    key = (document["ticker"], document["listing_date"])
                    if key in outcomes and outcomes[key]["evidence_hash"] != document["evidence_hash"]:
                        raise ValueError("AMBIGUOUS_OUTCOME_FOR_COHORT")
                    outcomes[key] = document
        records = []
        failures = Counter()
        database = base / "data/ipo_learning/decision_snapshots.sqlite"
        for item in interactions:
            if item["status"] != "OK":
                failures[item.get("error_code") or "PROVIDER_UNAVAILABLE"] += 1
                continue
            if item["agent_type"] != "MARKET_REGIME":
                continue
            if not item.get("result") or not database.is_file():
                failures["MISSING_VERIFIED_RESULT_OR_SNAPSHOT"] += 1
                continue
            refs = item["evidence_ids"]
            if len(refs) != 1:
                failures["AMBIGUOUS_INPUT_EVIDENCE"] += 1
                continue
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2)) as conn:
                ids = conn.execute("SELECT snapshot_id FROM decision_snapshots WHERE ticker=? AND snapshot_hash=? LIMIT 2",
                                   (item["ticker"], refs[0])).fetchall()
            snapshot = get_snapshot_record(base, ids[0][0]) if len(ids) == 1 else None
            if snapshot is None:
                failures["MISSING_OR_AMBIGUOUS_SNAPSHOT"] += 1
                continue
            day = _time(snapshot["cutoff"], "cutoff").astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            outcome = outcomes.get((item["ticker"], day))
            records.append({"request_id": item["request_id"], "provider_id": item["provider_id"],
                            "envelope": item["result"], "snapshot": snapshot, "outcome": outcome,
                            "review": reviews.get(outcome["evidence_id"]) if outcome else None})
        report = evaluate_shadow_records(records, config)
        report.update(interaction_window_limit=100, interaction_count=len(interactions),
                      interaction_total_count=journal["total_count"],
                      omitted_interaction_count=max(0, journal["total_count"] - len(interactions)),
                      provider_failures=dict(failures), journal_integrity=integrity)
        if failures and not records:
            report["state"] = "UNREADY_PROVIDER_RESULTS"
        report["report_hash"] = _report_hash(report)
        return report
    except Exception as exc:
        message = str(exc)
        reason = message if re.fullmatch(r"[A-Z][A-Z0-9_:.-]{1,160}", message) else type(exc).__name__
        return {"state": "UNREADY", "reason": reason, "error_type": type(exc).__name__, "order_submitted": False,
                "entry_authorized": False, "model_promoted": False, "training_performed": False,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def save_shadow_evaluation(root: str | Path) -> dict:
    report = collect_shadow_evaluation(root)
    path = safe_resolve_path(Path(root)) / "data/ipo_learning/shadow_evaluation.latest.json"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    report["persisted"] = True
    report["report_hash"] = _report_hash(report)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except (OSError, ValueError) as exc:
        report.update(state="PERSISTENCE_FAILED", reason=type(exc).__name__, persisted=False)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as exc:
            report["cleanup_error"] = type(exc).__name__
    report["report_hash"] = _report_hash(report)
    return report

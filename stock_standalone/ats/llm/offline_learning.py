# -*- coding: utf-8 -*-
"""Fail-closed SFT/DPO dataset preparation and shadow-promotion evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ats.strategy.ipo_data_contracts import IPO_REQUIRED_FIELDS


DATASET_SCHEMA_VERSION = "r9.offline-learning.v3"
MAX_CANDIDATE_BATCH_BYTES = 64 * 1024 * 1024
_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")
_CANDIDATE_FIELDS = {
    "candidate_id", "ticker", "event_id", "listing_date", "cutoff",
    "matured_at", "labels_mature", "label_source", "review_decision",
    "outcome_evidence_ids",
    "reviewed_by", "reviewed_at", "review_draft_hash",
    "input_snapshot", "input_snapshot_hash",
    "configuration_hash", "data_contract_hash", "standard_proposal",
    "proposal_created_at", "standard_proposal_hash",
    "gate_causal_chain", "model_id", "prompt_version",
    "preference_pair",
}
_FEATURE_FIELDS = {
    "status", "value", "source_id", "source_version", "source_timezone",
    "as_of_time", "available_at",
}
_PREFERENCE_FIELDS = {
    "cutoff", "chosen_proposal", "rejected_proposal", "chosen_reason",
    "rejected_reason", "reviewer",
}
_FORBIDDEN_INPUT_FEATURES = {
    "target_outcome", "outcome_label", "realized_return", "future_return",
    "matured_return", "d1_outcome", "d2_outcome", "d3_outcome",
}
_SHADOW_METRICS = (
    "false_entry_rate", "miss_rate", "schema_valid_rate", "p95_latency_ms",
)


class OfflineLearningError(ValueError):
    """Raised when a candidate cannot safely enter an offline dataset."""


def _canonical(value: Any, max_bytes: int = 256 * 1024) -> bytes:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise OfflineLearningError("learning records must contain strict JSON values") from exc
    if len(encoded) > max_bytes:
        raise OfflineLearningError("learning record exceeds the size limit")
    return encoded


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return normalized if math.isfinite(normalized) else None


def _hash_records(records: Iterable[Any], scope: str) -> str:
    digest = hashlib.sha256()
    digest.update(_canonical({"schema_version": DATASET_SCHEMA_VERSION, "scope": scope}))
    count = 0
    for record in records:
        encoded = _canonical(record)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        count += 1
    digest.update(count.to_bytes(8, "big"))
    return digest.hexdigest()


def compute_input_snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    """Compute the canonical hash required by a sealed training candidate."""
    if not isinstance(snapshot, Mapping):
        raise OfflineLearningError("input snapshot must be a mapping")
    return hashlib.sha256(_canonical(dict(snapshot), max_bytes=128 * 1024)).hexdigest()


def _text(value: Any, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise OfflineLearningError(f"{field} is missing or invalid")
    return value.strip()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise OfflineLearningError(f"{field} must be an aware ISO-8601 timestamp")
    try:
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
    except (OverflowError, TypeError, ValueError) as exc:
        raise OfflineLearningError(f"{field} must be an aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfflineLearningError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _validate_proposal(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise OfflineLearningError(f"{field} must be a non-empty Proposal object")
    encoded = _canonical(value, max_bytes=32 * 1024)
    return json.loads(encoded)


def _contract_context(config_snapshot: Any) -> Tuple[str, str, Any]:
    try:
        from ats.strategy.ipo_data_contracts import IPO_REQUIRED_FIELDS
        verify_integrity = getattr(config_snapshot, "verify_integrity", None)
        valid = callable(verify_integrity) and verify_integrity()
    except Exception as exc:
        raise OfflineLearningError("IPO decision contract could not be loaded") from exc
    if not valid:
        raise OfflineLearningError("a verified IPO decision config snapshot is required")
    data_contract = getattr(config_snapshot, "data_contract", None)
    fields = getattr(data_contract, "fields", None)
    required_fields = getattr(data_contract, "required_fields", None)
    if not isinstance(fields, Mapping) or set(required_fields or ()) != set(IPO_REQUIRED_FIELDS):
        raise OfflineLearningError("the frozen data contract must require all 41 IPO inputs")
    configuration_hash = getattr(config_snapshot, "config_hash", "")
    data_contract_hash = getattr(data_contract, "config_hash", "")
    if not _HEX_64.fullmatch(str(configuration_hash)) or not _HEX_64.fullmatch(str(data_contract_hash)):
        raise OfflineLearningError("decision and data-contract hashes are invalid")
    if not set(IPO_REQUIRED_FIELDS).issubset(fields):
        raise OfflineLearningError("the frozen data contract does not define all 41 IPO inputs")
    return configuration_hash.lower(), data_contract_hash.lower(), data_contract


def _validate_snapshot(snapshot: Any, cutoff: datetime, config_snapshot: Any) -> Dict[str, Any]:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "as_of_time", "configuration_hash", "data_contract_hash", "features"
    }:
        raise OfflineLearningError("input_snapshot provenance fields are incomplete")
    expected_config_hash, expected_contract_hash, data_contract = _contract_context(config_snapshot)
    if snapshot["configuration_hash"] != expected_config_hash:
        raise OfflineLearningError("input snapshot decision-config hash mismatch")
    if snapshot["data_contract_hash"] != expected_contract_hash:
        raise OfflineLearningError("input snapshot data-contract hash mismatch")
    if _time(snapshot.get("as_of_time"), "input_snapshot.as_of_time") != cutoff:
        raise OfflineLearningError("input snapshot time must equal the decision cutoff")
    features = snapshot.get("features")
    if not isinstance(features, dict) or set(features) != set(IPO_REQUIRED_FIELDS):
        raise OfflineLearningError("input snapshot must contain exactly all 41 required fields")
    observations = {}
    for field_id, feature in features.items():
        field_id = _text(field_id, "feature id", 160)
        if field_id.lower() in _FORBIDDEN_INPUT_FEATURES:
            raise OfflineLearningError(f"future outcome field is forbidden in model input: {field_id}")
        if not isinstance(feature, dict) or set(feature) != _FEATURE_FIELDS:
            raise OfflineLearningError(f"feature provenance is incomplete: {field_id}")
        contract = data_contract.fields.get(field_id)
        if contract is None:
            raise OfflineLearningError(f"field is absent from the frozen contract: {field_id}")
        status = feature.get("status")
        if not isinstance(status, str) or status not in ("OBSERVED", "MISSING_CONFIRMED"):
            raise OfflineLearningError(f"field status is invalid: {field_id}")
        timezone_name = _text(feature.get("source_timezone"), f"{field_id}.source_timezone", 120)
        try:
            ZoneInfo(timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise OfflineLearningError(f"invalid source timezone: {field_id}") from exc
        if timezone_name != contract.source_timezone:
            raise OfflineLearningError(f"source timezone mismatch: {field_id}")
        observations[field_id] = {
            "status": feature["status"],
            "source_id": feature["source_id"],
            "source_version": feature["source_version"],
            contract.value_key: feature["value"],
            contract.as_of_key: feature["as_of_time"],
            contract.available_at_key: feature["available_at"],
        }
    data_ready, field_checks = data_contract.validate_observations(observations, cutoff)
    if not data_ready:
        invalid = sorted(
            field_id for field_id, check in field_checks.items()
            if not check.usable
        )
        raise OfflineLearningError("41-field source/time/TTL contract failed: " + ", ".join(invalid[:8]))
    encoded = _canonical(snapshot, max_bytes=128 * 1024)
    return json.loads(encoded)


def validate_input_snapshot(snapshot: Any, config_snapshot: Any) -> Dict[str, Any]:
    """Revalidate a stored point-in-time input before any read-only Agent receives it."""
    if not isinstance(snapshot, Mapping):
        raise OfflineLearningError("input_snapshot must be a mapping")
    cutoff = _time(snapshot.get("as_of_time"), "input_snapshot.as_of_time")
    return _validate_snapshot(dict(snapshot), cutoff, config_snapshot)


def validate_learning_candidate(
    candidate: Any, config_snapshot: Any, generated_at: Optional[str] = None
) -> Dict[str, Any]:
    """Validate a matured, manually accepted, fully provenance-tracked sample."""
    if not isinstance(candidate, Mapping) or set(candidate) != _CANDIDATE_FIELDS:
        raise OfflineLearningError("candidate fields do not match the offline-learning contract")
    clean = dict(candidate)
    candidate_id = _text(clean["candidate_id"], "candidate_id", 128)
    ticker = _text(clean["ticker"], "ticker", 16)
    if not re.fullmatch(r"\d{6}", ticker):
        raise OfflineLearningError("ticker must be a six-digit code")
    event_id = _text(clean["event_id"], "event_id", 160)
    try:
        listing_day = date.fromisoformat(_text(clean["listing_date"], "listing_date", 10))
    except ValueError as exc:
        raise OfflineLearningError("listing_date must use YYYY-MM-DD") from exc

    cutoff = _time(clean["cutoff"], "cutoff")
    matured_at = _time(clean["matured_at"], "matured_at")
    reviewed_at = _time(clean["reviewed_at"], "reviewed_at")
    now = _time(generated_at, "generated_at") if generated_at is not None else datetime.now(timezone.utc)
    if clean["labels_mature"] is not True or matured_at < cutoff or matured_at > now:
        raise OfflineLearningError("label is pending, predates cutoff, or has not matured yet")
    if clean["review_decision"] != "ACCEPTED":
        raise OfflineLearningError("only manually accepted candidates may enter training")
    if reviewed_at < matured_at or reviewed_at > now:
        raise OfflineLearningError("candidate review must occur after maturity and before dataset build")
    label_source = _text(clean["label_source"], "label_source", 240)
    outcome_refs = clean["outcome_evidence_ids"]
    if (
        not isinstance(outcome_refs, list) or not outcome_refs or len(outcome_refs) > 32
        or any(
            not isinstance(reference, str) or not reference.startswith("outcome:")
            or not reference.removeprefix("outcome:").strip() or len(reference) > 160
            or "\x00" in reference
            for reference in outcome_refs
        )
        or len(outcome_refs) != len(set(outcome_refs))
    ):
        raise OfflineLearningError("mature labels must cite unique bounded outcome evidence IDs")
    reviewer = _text(clean["reviewed_by"], "reviewed_by", 120)
    review_draft_hash = clean["review_draft_hash"]
    if not isinstance(review_draft_hash, str) or not _HEX_64.fullmatch(review_draft_hash):
        raise OfflineLearningError("review_draft_hash must be a SHA-256 digest")
    model_id = _text(clean["model_id"], "model_id", 160)
    prompt_version = _text(clean["prompt_version"], "prompt_version", 128)
    expected_config_hash, expected_contract_hash, _ = _contract_context(config_snapshot)
    if clean["configuration_hash"] != expected_config_hash:
        raise OfflineLearningError("candidate decision-config hash mismatch")
    if clean["data_contract_hash"] != expected_contract_hash:
        raise OfflineLearningError("candidate data-contract hash mismatch")

    snapshot = _validate_snapshot(clean["input_snapshot"], cutoff, config_snapshot)
    snapshot_hash = clean["input_snapshot_hash"]
    if not isinstance(snapshot_hash, str) or not _HEX_64.fullmatch(snapshot_hash):
        raise OfflineLearningError("input_snapshot_hash must be a SHA-256 digest")
    if _hash(snapshot) != snapshot_hash.lower():
        raise OfflineLearningError("input_snapshot_hash does not match the sealed snapshot")
    proposal = _validate_proposal(clean["standard_proposal"], "standard_proposal")
    proposal_created_at = _time(clean["proposal_created_at"], "proposal_created_at")
    if proposal_created_at > cutoff:
        raise OfflineLearningError("standard Proposal was created after its decision cutoff")
    proposal_hash = clean["standard_proposal_hash"]
    if not isinstance(proposal_hash, str) or not _HEX_64.fullmatch(proposal_hash):
        raise OfflineLearningError("standard_proposal_hash must be a SHA-256 digest")
    if _hash(proposal) != proposal_hash.lower():
        raise OfflineLearningError("standard_proposal_hash does not match the Proposal")
    causal_chain = clean["gate_causal_chain"]
    if not isinstance(causal_chain, list) or not causal_chain or len(causal_chain) > 100:
        raise OfflineLearningError("gate_causal_chain must be a non-empty bounded list")
    causal_chain = [_text(item, "gate_causal_chain item", 500) for item in causal_chain]

    preference = clean["preference_pair"]
    clean_preference = None
    if preference is not None:
        if not isinstance(preference, Mapping) or set(preference) != _PREFERENCE_FIELDS:
            raise OfflineLearningError("preference_pair fields do not match the DPO contract")
        if _time(preference["cutoff"], "preference_pair.cutoff") != cutoff:
            raise OfflineLearningError("DPO chosen/rejected samples must share the candidate cutoff")
        if _text(preference["reviewer"], "preference_pair.reviewer", 120) != reviewer:
            raise OfflineLearningError("DPO preference reviewer must match the human candidate reviewer")
        chosen = _validate_proposal(preference["chosen_proposal"], "chosen_proposal")
        rejected = _validate_proposal(preference["rejected_proposal"], "rejected_proposal")
        if _canonical(chosen) == _canonical(rejected):
            raise OfflineLearningError("DPO chosen and rejected proposals must differ")
        clean_preference = {
            "cutoff": clean["cutoff"],
            "chosen_proposal": chosen,
            "rejected_proposal": rejected,
            "chosen_reason": _text(preference["chosen_reason"], "chosen_reason", 1000),
            "rejected_reason": _text(preference["rejected_reason"], "rejected_reason", 1000),
            "reviewer": reviewer,
        }

    return {
        "candidate_id": candidate_id,
        "ticker": ticker,
        "event_id": event_id,
        "listing_date": listing_day.isoformat(),
        "cutoff": clean["cutoff"],
        "matured_at": clean["matured_at"],
        "label_source": label_source,
        "outcome_evidence_ids": outcome_refs,
        "input_snapshot": snapshot,
        "input_snapshot_hash": snapshot_hash.lower(),
        "configuration_hash": expected_config_hash,
        "data_contract_hash": expected_contract_hash,
        "standard_proposal": proposal,
        "proposal_created_at": clean["proposal_created_at"],
        "standard_proposal_hash": proposal_hash.lower(),
        "gate_causal_chain": causal_chain,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "reviewed_by": reviewer,
        "reviewed_at": clean["reviewed_at"],
        "review_decision": "ACCEPTED",
        "review_draft_hash": review_draft_hash.lower(),
        "preference_pair": clean_preference,
    }


def _split_dataset(rows: Sequence[Dict[str, Any]], train_fraction: float, validation_fraction: float) -> Dict[str, Any]:
    train_fraction_value = _finite_float(train_fraction)
    validation_fraction_value = _finite_float(validation_fraction)
    if (
        train_fraction_value is None or validation_fraction_value is None
        or train_fraction_value <= 0 or validation_fraction_value <= 0
        or train_fraction_value + validation_fraction_value >= 1
    ):
        raise OfflineLearningError("time-forward split fractions are invalid")
    groups: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        group_id = f"{row['ticker']}|{row['event_id']}"
        group = groups.setdefault(group_id, {"date": row["listing_date"], "rows": []})
        if group["date"] != row["listing_date"]:
            raise OfflineLearningError("one event group contains multiple listing dates")
        group["rows"].append(row)
    ordered_groups = sorted(groups.items(), key=lambda item: (item[1]["date"], item[0]))
    group_count = len(ordered_groups)
    ordered_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (row["listing_date"], row["ticker"], row["event_id"], row["candidate_id"]),
    )
    candidate_hash = _hash_records(ordered_rows, "candidate_rows")
    if group_count < 3:
        dataset_hash = _hash({
            "schema_version": DATASET_SCHEMA_VERSION,
            "status": "INSUFFICIENT_EVENT_GROUPS",
            "candidate_hash": candidate_hash,
        })
        return {
            "status": "INSUFFICIENT_EVENT_GROUPS", "event_group_count": group_count,
            "sample_count": len(rows), "candidate_hash": candidate_hash,
            "splits": {"train": [], "validation": [], "test": []},
            "dataset_hash": dataset_hash,
        }
    train_count = min(group_count - 2, max(1, int(group_count * train_fraction_value)))
    validation_count = min(group_count - train_count - 1, max(1, int(group_count * validation_fraction_value)))
    train_end = train_count
    validation_end = train_count + validation_count
    group_split: Dict[str, str] = {}
    for index, (group_id, _) in enumerate(ordered_groups):
        group_split[group_id] = (
            "train" if index < train_end
            else "validation" if index < validation_end
            else "test"
        )
    splits: Dict[str, List[Dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for row in rows:
        group_id = f"{row['ticker']}|{row['event_id']}"
        splits[group_split[group_id]].append(dict(row))
    for split_rows in splits.values():
        split_rows.sort(key=lambda row: (row["listing_date"], row["ticker"], row["event_id"], row["candidate_id"]))
    split_records = (
        {"split": split_name, "row": row}
        for split_name in ("train", "validation", "test")
        for row in splits[split_name]
    )
    dataset_hash = _hash_records(split_records, "time_forward_splits")
    return {
        "status": "READY",
        "event_group_count": group_count,
        "sample_count": len(rows),
        "candidate_hash": candidate_hash,
        "split_group_counts": {
            name: len({f"{row['ticker']}|{row['event_id']}" for row in split_rows})
            for name, split_rows in splits.items()
        },
        "splits": splits,
        "dataset_hash": dataset_hash,
    }


def _verify_manual_review_audit(
    candidates: Sequence[Mapping[str, Any]], review_db_path: Optional[Path] = None,
) -> None:
    if not candidates:
        return
    path = Path(review_db_path) if review_db_path is not None else (
        Path(__file__).resolve().parents[2] / "logs" / "ipo_learning_reviews.sqlite"
    )
    if not path.is_file():
        raise OfflineLearningError("authoritative human review database is unavailable")
    required_columns = {
        "candidate_id", "decision", "reviewer", "input_snapshot_hash", "cutoff",
        "label_source", "reviewed_at", "model_id", "prompt_version",
        "review_draft_hash", "outcome_evidence_ids_json", "ticker", "event_id",
        "listing_date", "matured_at", "configuration_hash", "data_contract_hash",
    }
    reviewed: Dict[str, Dict[str, Any]] = {}
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25
        )
        connection.execute("PRAGMA query_only=ON")
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(sample_review_decisions)"
            ).fetchall()
        }
        if not required_columns.issubset(columns):
            raise OfflineLearningError(
                "human review database schema is incomplete; new reviews are required"
            )
        selected = sorted(required_columns)
        for offset in range(0, len(candidates), 400):
            batch = candidates[offset:offset + 400]
            candidate_ids = [str(item["candidate_id"]) for item in batch]
            placeholders = ",".join("?" for _ in candidate_ids)
            query = (
                "SELECT " + ", ".join(selected)
                + " FROM sample_review_decisions WHERE candidate_id IN ("
                + placeholders + ")"
            )
            for row in connection.execute(query, candidate_ids).fetchall():
                reviewed[str(row[selected.index("candidate_id")])] = dict(zip(selected, row))
    except OfflineLearningError:
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise OfflineLearningError("human review database could not be verified") from exc
    finally:
        if connection is not None:
            connection.close()

    text_pairs = (
        ("decision", "review_decision"), ("reviewer", "reviewed_by"),
        ("label_source", "label_source"), ("model_id", "model_id"),
        ("prompt_version", "prompt_version"), ("ticker", "ticker"),
        ("event_id", "event_id"), ("listing_date", "listing_date"),
    )
    hash_pairs = (
        ("input_snapshot_hash", "input_snapshot_hash"),
        ("review_draft_hash", "review_draft_hash"),
        ("configuration_hash", "configuration_hash"),
        ("data_contract_hash", "data_contract_hash"),
    )
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        record = reviewed.get(candidate_id)
        if record is None:
            raise OfflineLearningError("candidate has no authoritative human review record")
        if any(record[column] != candidate[field] for column, field in text_pairs):
            raise OfflineLearningError("human review record does not match the candidate")
        if any(
            not isinstance(record[column], str)
            or record[column].lower() != str(candidate[field]).lower()
            for column, field in hash_pairs
        ):
            raise OfflineLearningError("human review hashes do not match the candidate")
        for column, field in (("cutoff", "cutoff"), ("matured_at", "matured_at"), ("reviewed_at", "reviewed_at")):
            if _time(record[column], "review." + column) != _time(candidate[field], field):
                raise OfflineLearningError("human review timestamps do not match the candidate")
        try:
            refs_json = record["outcome_evidence_ids_json"]
            if not isinstance(refs_json, str) or len(refs_json) > 8192:
                raise ValueError("oversized evidence references")
            recorded_refs = json.loads(refs_json)
        except (TypeError, ValueError, RecursionError) as exc:
            raise OfflineLearningError("human review evidence references are invalid") from exc
        if recorded_refs != candidate["outcome_evidence_ids"]:
            raise OfflineLearningError("reviewed outcome evidence does not match the candidate")


def build_offline_datasets(
    candidates: Iterable[Mapping[str, Any]],
    *,
    config_snapshot: Any,
    generated_at: Optional[str] = None,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    review_db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build deterministic time-forward SFT/DPO splits from accepted samples only."""
    config_hash, contract_hash, _ = _contract_context(config_snapshot)
    clean_candidates: List[Dict[str, Any]] = []
    seen_ids = set()
    candidate_bytes = 0
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()
    else:
        generated_at = _time(generated_at, "generated_at").isoformat()
    for index, candidate in enumerate(candidates):
        if index >= 100_000:
            raise OfflineLearningError("candidate batch exceeds 100000 records")
        clean = validate_learning_candidate(candidate, config_snapshot, generated_at)
        candidate_bytes += len(_canonical(clean, max_bytes=256 * 1024))
        if candidate_bytes > MAX_CANDIDATE_BATCH_BYTES:
            raise OfflineLearningError("candidate batch exceeds the 64 MiB safety limit")
        if clean["candidate_id"] in seen_ids:
            raise OfflineLearningError("duplicate candidate_id")
        seen_ids.add(clean["candidate_id"])
        clean_candidates.append(clean)

    _verify_manual_review_audit(clean_candidates, review_db_path)

    sft_rows = [
        {
            "candidate_id": item["candidate_id"],
            "ticker": item["ticker"],
            "event_id": item["event_id"],
            "listing_date": item["listing_date"],
            "cutoff": item["cutoff"],
            "input_snapshot": item["input_snapshot"],
            "input_snapshot_hash": item["input_snapshot_hash"],
            "configuration_hash": item["configuration_hash"],
            "data_contract_hash": item["data_contract_hash"],
            "target_proposal": item["standard_proposal"],
            "standard_proposal_hash": item["standard_proposal_hash"],
            "proposal_created_at": item["proposal_created_at"],
            "label_source": item["label_source"],
            "matured_at": item["matured_at"],
            "outcome_evidence_ids": item["outcome_evidence_ids"],
            "reviewed_at": item["reviewed_at"],
            "reviewed_by": item["reviewed_by"],
            "review_draft_hash": item["review_draft_hash"],
            "gate_causal_chain": item["gate_causal_chain"],
            "model_id": item["model_id"],
            "prompt_version": item["prompt_version"],
        }
        for item in clean_candidates
    ]
    dpo_rows = [
        {
            "candidate_id": item["candidate_id"],
            "ticker": item["ticker"],
            "event_id": item["event_id"],
            "listing_date": item["listing_date"],
            "cutoff": item["cutoff"],
            "input_snapshot": item["input_snapshot"],
            "input_snapshot_hash": item["input_snapshot_hash"],
            "configuration_hash": item["configuration_hash"],
            "data_contract_hash": item["data_contract_hash"],
            "chosen_proposal": item["preference_pair"]["chosen_proposal"],
            "chosen_proposal_hash": _hash(item["preference_pair"]["chosen_proposal"]),
            "rejected_proposal": item["preference_pair"]["rejected_proposal"],
            "rejected_proposal_hash": _hash(item["preference_pair"]["rejected_proposal"]),
            "chosen_reason": item["preference_pair"]["chosen_reason"],
            "rejected_reason": item["preference_pair"]["rejected_reason"],
            "reviewer": item["preference_pair"]["reviewer"],
            "reviewed_at": item["reviewed_at"],
            "review_draft_hash": item["review_draft_hash"],
            "label_source": item["label_source"],
            "matured_at": item["matured_at"],
            "outcome_evidence_ids": item["outcome_evidence_ids"],
            "gate_causal_chain": item["gate_causal_chain"],
        }
        for item in clean_candidates if item["preference_pair"] is not None
    ]
    sft = _split_dataset(sft_rows, train_fraction, validation_fraction)
    dpo = _split_dataset(dpo_rows, train_fraction, validation_fraction)
    dataset_status = (
        "READY_FOR_TRAINING"
        if sft["status"] == "READY" and dpo["status"] == "READY"
        else "INSUFFICIENT_EVENT_GROUPS"
    )
    dataset_hash = _hash({
        "schema_version": DATASET_SCHEMA_VERSION,
        "configuration_hash": config_hash,
        "data_contract_hash": contract_hash,
        "sft_dataset_hash": sft["dataset_hash"],
        "dpo_dataset_hash": dpo["dataset_hash"],
        "status": dataset_status,
    })
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "generated_at": generated_at,
        "configuration_hash": config_hash,
        "data_contract_hash": contract_hash,
        "status": dataset_status,
        "dataset_hash": dataset_hash,
        "sft": sft,
        "dpo": dpo,
    }


def evaluate_shadow_readiness(
    candidate_metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    *,
    candidate_version: str,
    baseline_version: str,
    dataset_hash: str,
    replay_report_hash: str,
) -> Dict[str, Any]:
    """Compare candidate and deterministic baseline using explicit YAML thresholds."""
    threshold_fields = {
        "max_false_entry_rate", "max_miss_rate", "min_schema_valid_rate", "max_p95_latency_ms",
    }
    if not isinstance(candidate_metrics, Mapping) or not isinstance(baseline_metrics, Mapping) or not isinstance(thresholds, Mapping):
        raise OfflineLearningError("shadow metrics and thresholds must be mappings")
    candidate_version = _text(candidate_version, "candidate_version", 160)
    baseline_version = _text(baseline_version, "baseline_version", 160)
    if not isinstance(dataset_hash, str) or not _HEX_64.fullmatch(dataset_hash):
        raise OfflineLearningError("shadow evaluation requires the dataset hash")
    if not isinstance(replay_report_hash, str) or not _HEX_64.fullmatch(replay_report_hash):
        raise OfflineLearningError("shadow evaluation requires the replay report hash")
    if not threshold_fields.issubset(thresholds):
        raise OfflineLearningError("shadow thresholds are incomplete")
    for source in (candidate_metrics, baseline_metrics):
        if not set(_SHADOW_METRICS).issubset(source):
            raise OfflineLearningError("shadow metrics are incomplete")
        for name in _SHADOW_METRICS:
            value = _finite_float(source[name])
            if value is None:
                raise OfflineLearningError(f"shadow metric is invalid: {name}")
            if name in {"false_entry_rate", "miss_rate", "schema_valid_rate"} and not 0 <= value <= 1:
                raise OfflineLearningError(f"shadow rate must be between 0 and 1: {name}")
            if name == "p95_latency_ms" and value < 0:
                raise OfflineLearningError("p95_latency_ms must not be negative")
    candidate = {name: _finite_float(candidate_metrics[name]) for name in _SHADOW_METRICS}
    baseline = {name: _finite_float(baseline_metrics[name]) for name in _SHADOW_METRICS}
    limits: Dict[str, float] = {}
    for name in threshold_fields:
        value = _finite_float(thresholds[name])
        if value is None:
            raise OfflineLearningError(f"shadow threshold is invalid: {name}")
        if name.startswith(("max_false_entry_rate", "max_miss_rate", "min_schema_valid_rate")) and not 0 <= value <= 1:
            raise OfflineLearningError(f"shadow rate threshold must be between 0 and 1: {name}")
        if name == "max_p95_latency_ms" and value < 0:
            raise OfflineLearningError("max_p95_latency_ms must not be negative")
        limits[name] = value
    checks = {
        "false_entry_rate_threshold": candidate["false_entry_rate"] <= limits["max_false_entry_rate"],
        "false_entry_rate_not_worse_than_baseline": candidate["false_entry_rate"] <= baseline["false_entry_rate"],
        "miss_rate_threshold": candidate["miss_rate"] <= limits["max_miss_rate"],
        "miss_rate_not_worse_than_baseline": candidate["miss_rate"] <= baseline["miss_rate"],
        "schema_valid_rate_threshold": candidate["schema_valid_rate"] >= limits["min_schema_valid_rate"],
        "schema_valid_rate_not_worse_than_baseline": candidate["schema_valid_rate"] >= baseline["schema_valid_rate"],
        "latency_threshold": candidate["p95_latency_ms"] <= limits["max_p95_latency_ms"],
    }
    return {
        "status": "ELIGIBLE_FOR_MANUAL_PROMOTION" if all(checks.values()) else "REJECTED",
        "candidate_version": candidate_version,
        "baseline_version": baseline_version,
        "dataset_hash": dataset_hash.lower(),
        "replay_report_hash": replay_report_hash.lower(),
        "checks": checks,
        "candidate_metrics": candidate,
        "baseline_metrics": baseline,
        "thresholds": limits,
        "metrics_hash": _hash({
            "candidate_version": candidate_version,
            "baseline_version": baseline_version,
            "dataset_hash": dataset_hash.lower(),
            "replay_report_hash": replay_report_hash.lower(),
            "candidate": candidate,
            "baseline": baseline,
            "thresholds": limits,
        }),
    }


def build_lifecycle_evidence(
    action: str,
    *,
    candidate_version: str,
    current_version: str,
    previous_version: str,
    reviewer: str,
    reason: str,
    dataset_hash: Optional[str] = None,
    artifact_hash: Optional[str] = None,
    shadow_report: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create auditable manual promotion/rollback evidence; does not switch runtime."""
    candidate_version = _text(candidate_version, "candidate_version", 160)
    current_version = _text(current_version, "current_version", 160)
    reviewer = _text(reviewer, "reviewer", 120)
    reason = _text(reason, "reason", 1000)
    if action == "PROMOTE":
        if candidate_version == current_version:
            raise OfflineLearningError("candidate is already active")
        if not isinstance(dataset_hash, str) or not _HEX_64.fullmatch(dataset_hash):
            raise OfflineLearningError("promotion requires the trained dataset hash")
        if not isinstance(artifact_hash, str) or not _HEX_64.fullmatch(artifact_hash):
            raise OfflineLearningError("promotion requires the trained artifact hash")
        if not isinstance(shadow_report, Mapping) or shadow_report.get("status") != "ELIGIBLE_FOR_MANUAL_PROMOTION":
            raise OfflineLearningError("promotion requires passing shadow evidence")
        if (
            shadow_report.get("candidate_version") != candidate_version
            or shadow_report.get("baseline_version") != current_version
            or shadow_report.get("dataset_hash") != dataset_hash.lower()
        ):
            raise OfflineLearningError("promotion evidence does not match model, baseline, and dataset")
        replay_hash = shadow_report.get("replay_report_hash")
        if not isinstance(replay_hash, str) or not _HEX_64.fullmatch(replay_hash):
            raise OfflineLearningError("promotion requires a valid replay report hash")
        if not isinstance(shadow_report.get("checks"), Mapping) or not all(
            value is True for value in shadow_report["checks"].values()
        ):
            raise OfflineLearningError("promotion requires every shadow check to pass")
        verified_report = evaluate_shadow_readiness(
            shadow_report.get("candidate_metrics", {}),
            shadow_report.get("baseline_metrics", {}),
            shadow_report.get("thresholds", {}),
            candidate_version=candidate_version,
            baseline_version=current_version,
            dataset_hash=dataset_hash,
            replay_report_hash=replay_hash,
        )
        reported_hash = shadow_report.get("metrics_hash")
        if (
            not isinstance(reported_hash, str)
            or reported_hash.lower() != verified_report["metrics_hash"]
            or shadow_report.get("checks") != verified_report["checks"]
            or verified_report["status"] != "ELIGIBLE_FOR_MANUAL_PROMOTION"
        ):
            raise OfflineLearningError("shadow report integrity or eligibility check failed")
        return {
            "action": "PROMOTION_APPROVED",
            "candidate_version": candidate_version,
            "previous_version": current_version,
            "reviewer": reviewer,
            "reason": reason,
            "dataset_hash": dataset_hash.lower(),
            "artifact_hash": artifact_hash.lower(),
            "shadow_metrics_hash": shadow_report["metrics_hash"],
            "replay_report_hash": replay_hash.lower(),
            "runtime_switch_required": True,
        }
    if action == "ROLLBACK":
        previous_version = _text(previous_version, "previous_version", 160)
        if current_version == previous_version:
            raise OfflineLearningError("rollback target is already active")
        return {
            "action": "ROLLBACK_APPROVED",
            "candidate_version": current_version,
            "previous_version": previous_version,
            "reviewer": reviewer,
            "reason": reason,
            "runtime_switch_required": True,
        }
    raise OfflineLearningError("action must be PROMOTE or ROLLBACK")

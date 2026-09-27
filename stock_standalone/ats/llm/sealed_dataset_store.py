"""Immutable, content-addressed storage for validated offline datasets."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from ats.llm.offline_learning import (
    DATASET_SCHEMA_VERSION,
    MAX_CANDIDATE_BATCH_BYTES,
    OfflineLearningError,
    _hash,
    _hash_records,
)


MAX_SEALED_DATASET_BYTES = MAX_CANDIDATE_BATCH_BYTES * 2
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise OfflineLearningError("sealed dataset must contain strict JSON values") from exc
    if len(encoded) > MAX_SEALED_DATASET_BYTES:
        raise OfflineLearningError("sealed dataset exceeds the storage limit")
    return encoded


def _verify_split(split: Any) -> Dict[str, Any]:
    if not isinstance(split, Mapping) or split.get("status") != "READY":
        raise OfflineLearningError("only complete READY time-forward splits may be sealed")
    if set(split) != {
        "status", "event_group_count", "sample_count", "candidate_hash",
        "split_group_counts", "splits", "dataset_hash",
    }:
        raise OfflineLearningError("time-forward dataset fields do not match the stored schema")
    required = {"train", "validation", "test"}
    splits = split.get("splits")
    if not isinstance(splits, Mapping) or set(splits) != required:
        raise OfflineLearningError("dataset split members are incomplete")
    normalized: Dict[str, list] = {}
    group_splits: Dict[str, str] = {}
    all_rows = []
    for split_name in ("train", "validation", "test"):
        rows = splits[split_name]
        if not isinstance(rows, list) or not rows:
            raise OfflineLearningError("each sealed split must contain samples")
        normalized_rows = []
        for row in rows:
            if not isinstance(row, dict):
                raise OfflineLearningError("dataset split contains a non-object row")
            ticker, event_id, listing_date = (
                row.get("ticker"), row.get("event_id"), row.get("listing_date")
            )
            candidate_id = row.get("candidate_id")
            if not all(
                isinstance(value, str) and value
                for value in (ticker, event_id, listing_date, candidate_id)
            ):
                raise OfflineLearningError("dataset split row is missing its event identity")
            outcome_refs = row.get("outcome_evidence_ids")
            if (
                not isinstance(outcome_refs, list) or not outcome_refs
                or len(outcome_refs) > 32
                or any(
                    not isinstance(reference, str)
                    or not reference.startswith("outcome:")
                    or not reference.removeprefix("outcome:").strip()
                    or len(reference) > 160 or "\x00" in reference
                    for reference in outcome_refs
                )
                or len(outcome_refs) != len(set(outcome_refs))
            ):
                raise OfflineLearningError(
                    "sealed training rows must retain unique outcome evidence IDs"
                )
            reviewer = row.get("reviewed_by", row.get("reviewer"))
            review_hash = row.get("review_draft_hash")
            reviewed_at = row.get("reviewed_at")
            if (
                not isinstance(reviewer, str) or not reviewer.strip()
                or not isinstance(review_hash, str) or not _HEX_64.fullmatch(review_hash)
                or not isinstance(reviewed_at, str)
            ):
                raise OfflineLearningError("sealed training rows must retain human review provenance")
            try:
                reviewed_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise OfflineLearningError("sealed training review time is invalid") from exc
            if reviewed_time.tzinfo is None or reviewed_time.utcoffset() is None:
                raise OfflineLearningError("sealed training review time must include a UTC offset")
            group_id = f"{ticker}|{event_id}"
            previous = group_splits.setdefault(group_id, split_name)
            if previous != split_name:
                raise OfflineLearningError("one listing event appears in multiple time splits")
            copied = dict(row)
            normalized_rows.append(copied)
            all_rows.append(copied)
        normalized[split_name] = normalized_rows

    ordered_rows = sorted(
        all_rows,
        key=lambda row: (row["listing_date"], row["ticker"], row["event_id"], row["candidate_id"]),
    )
    candidate_hash = _hash_records(ordered_rows, "candidate_rows")
    split_records = (
        {"split": split_name, "row": row}
        for split_name in ("train", "validation", "test")
        for row in normalized[split_name]
    )
    dataset_hash = _hash_records(split_records, "time_forward_splits")
    event_group_count = len(group_splits)
    sample_count = len(all_rows)
    expected_group_counts = {
        name: len({f"{row['ticker']}|{row['event_id']}" for row in normalized[name]})
        for name in ("train", "validation", "test")
    }
    if (
        split.get("dataset_hash") != dataset_hash
        or split.get("candidate_hash") != candidate_hash
        or split.get("sample_count") != sample_count
        or split.get("event_group_count") != event_group_count
        or split.get("split_group_counts") != expected_group_counts
    ):
        raise OfflineLearningError("time-forward dataset hashes or counts do not match its rows")
    return {
        "dataset_hash": dataset_hash,
        "sample_count": sample_count,
        "event_group_count": event_group_count,
    }


def _verify_dataset(dataset: Any) -> Dict[str, Any]:
    if not isinstance(dataset, Mapping) or dataset.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise OfflineLearningError("unsupported offline dataset schema")
    if set(dataset) != {
        "schema_version", "generated_at", "configuration_hash", "data_contract_hash",
        "status", "dataset_hash", "sft", "dpo",
    }:
        raise OfflineLearningError("offline dataset fields do not match the stored schema")
    if dataset.get("status") != "READY_FOR_TRAINING":
        raise OfflineLearningError("only READY_FOR_TRAINING datasets may be sealed")
    generated_at = dataset.get("generated_at")
    if not isinstance(generated_at, str):
        raise OfflineLearningError("sealed dataset generated_at is missing")
    try:
        generated_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OfflineLearningError("sealed dataset generated_at is invalid") from exc
    if generated_time.tzinfo is None or generated_time.utcoffset() is None:
        raise OfflineLearningError("sealed dataset generated_at must include a UTC offset")
    if any(
        not isinstance(dataset.get(key), str) or not _HEX_64.fullmatch(dataset[key])
        for key in ("configuration_hash", "data_contract_hash")
    ):
        raise OfflineLearningError("sealed dataset configuration hashes are invalid")
    sft = _verify_split(dataset.get("sft"))
    dpo = _verify_split(dataset.get("dpo"))
    expected_hash = _hash({
        "schema_version": DATASET_SCHEMA_VERSION,
        "configuration_hash": dataset.get("configuration_hash"),
        "data_contract_hash": dataset.get("data_contract_hash"),
        "sft_dataset_hash": sft["dataset_hash"],
        "dpo_dataset_hash": dpo["dataset_hash"],
        "status": dataset.get("status"),
    })
    if dataset.get("dataset_hash") != expected_hash:
        raise OfflineLearningError("offline dataset hash does not match its contents")
    return {
        "dataset_hash": expected_hash,
        "sample_count": sft["sample_count"],
        "event_group_count": sft["event_group_count"],
    }


class SealedDatasetRepository:
    """Persist verified datasets once; every load rechecks the content hashes."""

    def __init__(self, root: str | os.PathLike[str], *, create: bool = True) -> None:
        self.root = Path(root)
        self.index_path = self.root / "index.sqlite"
        if not create:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.index_path), timeout=2.0) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS sealed_datasets (
                    dataset_hash TEXT PRIMARY KEY,
                    artifact_file TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    event_group_count INTEGER NOT NULL,
                    sealed_at TEXT NOT NULL
                )"""
            )
            connection.commit()

    def _artifact_path(self, dataset_hash: str) -> Path:
        if not isinstance(dataset_hash, str) or not _HEX_64.fullmatch(dataset_hash):
            raise OfflineLearningError("dataset hash must be a lowercase SHA-256 digest")
        return self.root / f"{dataset_hash}.json"

    def seal(self, dataset: Mapping[str, Any]) -> Dict[str, Any]:
        """Store one already-built dataset after recomputing all split hashes."""
        evidence = _verify_dataset(dataset)
        artifact_path = self._artifact_path(evidence["dataset_hash"])
        payload = _canonical(dict(dataset))
        if artifact_path.exists():
            if artifact_path.is_symlink() or artifact_path.stat().st_size > MAX_SEALED_DATASET_BYTES:
                raise OfflineLearningError("existing sealed dataset artifact is unsafe")
            try:
                existing = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, RecursionError) as exc:
                raise OfflineLearningError("existing sealed dataset artifact is unreadable") from exc
            if _verify_dataset(existing)["dataset_hash"] != evidence["dataset_hash"]:
                raise OfflineLearningError("content-addressed dataset path contains different data")
        else:
            temporary_path: Optional[Path] = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=str(self.root), prefix=".sealed-", suffix=".tmp", delete=False,
                ) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(str(temporary_path), str(artifact_path))
                temporary_path = None
            except OSError as exc:
                raise OfflineLearningError("could not persist sealed dataset atomically") from exc
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass

        sealed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with sqlite3.connect(str(self.index_path), timeout=2.0) as connection:
                connection.execute(
                    """INSERT OR IGNORE INTO sealed_datasets
                        (dataset_hash, artifact_file, sample_count, event_group_count, sealed_at)
                        VALUES (?, ?, ?, ?, ?)""",
                    (
                        evidence["dataset_hash"], artifact_path.name,
                        evidence["sample_count"], evidence["event_group_count"], sealed_at,
                    ),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise OfflineLearningError("sealed dataset index could not be updated") from exc
        return {"status": "SEALED", **evidence, "artifact_file": artifact_path.name}

    def load(self, dataset_hash: str) -> Dict[str, Any]:
        artifact_path = self._artifact_path(dataset_hash)
        try:
            if artifact_path.is_symlink() or artifact_path.stat().st_size > MAX_SEALED_DATASET_BYTES:
                raise OfflineLearningError("sealed dataset artifact is unsafe")
            raw = artifact_path.read_bytes()
            dataset = json.loads(raw.decode("utf-8"))
        except OfflineLearningError:
            raise
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise OfflineLearningError("sealed dataset artifact is missing or unreadable") from exc
        evidence = _verify_dataset(dataset)
        if evidence["dataset_hash"] != dataset_hash:
            raise OfflineLearningError("sealed dataset filename and content hash disagree")
        return dataset

    def summary(self) -> Dict[str, Any]:
        if not self.index_path.is_file():
            return {
                "status": "EMPTY", "dataset_count": 0, "sample_count": 0,
                "event_group_count": 0, "latest_sealed_at": "",
                "integrity": "逐批读取时复核内容哈希",
            }
        try:
            with sqlite3.connect(str(self.index_path), timeout=0.2) as connection:
                row = connection.execute(
                    """SELECT COUNT(*), COALESCE(SUM(sample_count), 0),
                        COALESCE(SUM(event_group_count), 0), MAX(sealed_at)
                        FROM sealed_datasets"""
                ).fetchone()
        except sqlite3.Error as exc:
            raise OfflineLearningError("sealed dataset index is unavailable") from exc
        count, sample_count, event_group_count, latest = row
        return {
            "status": "READY" if count else "EMPTY",
            "dataset_count": int(count),
            "sample_count": int(sample_count),
            "event_group_count": int(event_group_count),
            "latest_sealed_at": latest or "",
            "integrity": "逐批读取时复核内容哈希",
        }

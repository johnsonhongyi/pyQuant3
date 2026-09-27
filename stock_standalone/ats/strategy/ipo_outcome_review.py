# -*- coding: utf-8 -*-
"""Append-only human review ledger for immutable D1-D3 outcome evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


_EVIDENCE_LIMIT = 64 * 1024
_REVIEW_DB = Path("data") / "ipo_learning" / "outcome_reviews.sqlite"


def _verified_evidence(document: Any) -> bool:
    if not isinstance(document, dict) or any(
        document.get(key) != expected for key, expected in (
            ("schema_version", "ipo-outcome-evidence.v1"),
            ("status", "MATURED_PENDING_REVIEW"),
            ("review_status", "PENDING_HUMAN_REVIEW"),
            ("labels_mature", True),
            ("training_eligible", False),
        )
    ):
        return False
    digest = document.get("evidence_hash")
    evidence_id = document.get("evidence_id")
    if not isinstance(digest, str) or not isinstance(evidence_id, str):
        return False
    payload = {
        key: value for key, value in document.items()
        if key not in {"evidence_id", "evidence_hash", "status"}
    }
    try:
        expected = hashlib.sha256(json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return False
    return digest == expected and evidence_id == "outcome:" + expected[:48]


def load_latest_outcome_reviews(root: str | Path) -> Dict[str, Dict[str, str]]:
    path = Path(root).resolve() / _REVIEW_DB
    if not path.is_file():
        return {}
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as connection:
            rows = connection.execute(
                "SELECT evidence_id, evidence_hash, decision, reviewer, reason, reviewed_at_utc "
                "FROM outcome_reviews ORDER BY rowid"
            ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        return {}
    latest: Dict[str, Dict[str, str]] = {}
    for evidence_id, evidence_hash, decision, reviewer, reason, reviewed_at in rows:
        if not all(isinstance(value, str) for value in (
            evidence_id, evidence_hash, decision, reviewer, reason, reviewed_at,
        )):
            continue
        latest[evidence_id] = {
            "evidence_hash": evidence_hash,
            "decision": decision,
            "reviewer": reviewer,
            "reason": reason,
            "reviewed_at_utc": reviewed_at,
        }
    return latest


def record_outcome_review(
    root: str | Path, evidence_path: str | Path, *, decision: str,
    reviewer: str, reason: str,
) -> Dict[str, Any]:
    """Record a reviewed/rejected decision without changing evidence or training state."""
    if decision not in {"ACCEPTED", "REJECTED"}:
        return {"status": "INVALID", "reason": "复核决定无效"}
    if (
        not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 120
        or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000
        or any(ord(char) < 32 and char not in "\t\n\r" for char in reviewer + reason)
    ):
        return {"status": "INVALID", "reason": "复核人或理由为空/超长/含控制字符"}
    root_path = Path(root).resolve()
    evidence_dir = (root_path / "data" / "ipo_learning" / "outcome_evidence").resolve()
    try:
        source_path = Path(evidence_path).resolve(strict=True)
        source_path.relative_to(evidence_dir)
        if not source_path.is_file() or source_path.stat().st_size > _EVIDENCE_LIMIT:
            raise ValueError("证据文件缺失或超过大小限制")
        with source_path.open("r", encoding="utf-8") as stream:
            evidence = json.load(stream)
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {"status": "UNREADY", "reason": "证据文件不可读或不在证据目录内"}
    if not _verified_evidence(evidence):
        return {"status": "UNREADY", "reason": "成熟证据哈希/状态未通过复核校验"}
    evidence_id = evidence["evidence_id"]
    reviewed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review_id = "review:" + uuid.uuid4().hex
    database = root_path / _REVIEW_DB
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database, timeout=1.0) as connection:
            connection.execute("PRAGMA busy_timeout=1000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS outcome_reviews (
                    review_id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK (decision IN ('ACCEPTED','REJECTED')),
                    reviewer TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    reviewed_at_utc TEXT NOT NULL
                )"""
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO outcome_reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
                (review_id, evidence_id, evidence["evidence_hash"], decision,
                 reviewer.strip(), reason.strip(), reviewed_at),
            )
            connection.commit()
    except (OSError, sqlite3.Error, ValueError):
        return {"status": "UNREADY", "reason": "人工复核审计写入失败"}
    return {
        "status": "SAVED", "review_id": review_id, "evidence_id": evidence_id,
        "evidence_hash": evidence["evidence_hash"],
        "decision": decision, "training_authorized": False,
    }

# -*- coding: utf-8 -*-
"""Asynchronous, local journal for point-in-time IPO decision snapshots."""

from __future__ import annotations

import json
import hashlib
import math
import queue
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 256 * 1024
_QUEUE_SIZE = 256
_STOP_WRITER = object()
_writers: Dict[str, "_SnapshotWriter"] = {}
_writers_lock = threading.Lock()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _database_path(root: Path) -> Path:
    return root / "data" / "ipo_learning" / "decision_snapshots.sqlite"


class _SnapshotWriter:
    """One bounded background writer per application root; never blocks ATS callers."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.pending: "queue.Queue[Any]" = queue.Queue(maxsize=_QUEUE_SIZE)
        self.dropped = 0
        self.failed = 0
        self.last_error = ""
        self._state_lock = threading.Lock()
        self._stopping = False
        self._thread = threading.Thread(
            target=self._run, name="ipo-learning-snapshot-writer", daemon=True
        )
        self._thread.start()

    def enqueue(self, record: Dict[str, Any]) -> bool:
        with self._state_lock:
            if self._stopping or not self._thread.is_alive():
                self.failed += 1
                self.last_error = self.last_error or "snapshot writer stopped"
                return False
            try:
                self.pending.put_nowait(record)
                return True
            except queue.Full:
                self.dropped += 1
                self.last_error = "snapshot queue full"
                return False

    def _run(self) -> None:
        connection: Optional[sqlite3.Connection] = None
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.database_path), timeout=0.25)
            connection.execute("PRAGMA busy_timeout=250")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS decision_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    snapshot_hash TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    cutoff TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    configuration_version TEXT NOT NULL DEFAULT '',
                    configuration_hash TEXT NOT NULL,
                    data_contract_hash TEXT NOT NULL,
                    input_snapshot_json TEXT NOT NULL,
                    gate_causal_chain_json TEXT NOT NULL,
                    standard_proposal_json TEXT NOT NULL DEFAULT '{}',
                    proposal_created_at TEXT NOT NULL DEFAULT '',
                    label_status TEXT NOT NULL DEFAULT 'WAITING_OUTCOME'
                )"""
            )
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(decision_snapshots)"
                ).fetchall()
            }
            if "configuration_version" not in columns:
                connection.execute(
                    "ALTER TABLE decision_snapshots ADD COLUMN "
                    "configuration_version TEXT NOT NULL DEFAULT ''"
                )
            if "standard_proposal_json" not in columns:
                connection.execute(
                    "ALTER TABLE decision_snapshots ADD COLUMN "
                    "standard_proposal_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "proposal_created_at" not in columns:
                connection.execute(
                    "ALTER TABLE decision_snapshots ADD COLUMN "
                    "proposal_created_at TEXT NOT NULL DEFAULT ''"
                )
            connection.commit()
            while True:
                record = self.pending.get()
                if record is _STOP_WRITER:
                    self.pending.task_done()
                    break
                try:
                    connection.execute(
                        """INSERT OR IGNORE INTO decision_snapshots (
                            snapshot_id, snapshot_hash, ticker, event_id, cutoff, captured_at,
                            decision, configuration_version, configuration_hash, data_contract_hash,
                            input_snapshot_json, gate_causal_chain_json, standard_proposal_json,
                            proposal_created_at, label_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WAITING_OUTCOME')""",
                        (
                            record["snapshot_id"], record["snapshot_hash"],
                            record["ticker"], record["event_id"],
                            record["cutoff"], record["captured_at"], record["decision"],
                            record["configuration_version"],
                            record["configuration_hash"], record["data_contract_hash"],
                            record["input_snapshot_json"], record["gate_causal_chain_json"],
                            record["standard_proposal_json"], record["proposal_created_at"],
                        ),
                    )
                    connection.commit()
                except sqlite3.Error as exc:
                    try:
                        connection.rollback()
                    except sqlite3.Error:
                        pass
                    with self._state_lock:
                        self.failed += 1
                        self.last_error = str(exc)[:180]
                finally:
                    self.pending.task_done()
        except (OSError, sqlite3.Error) as exc:
            with self._state_lock:
                self.failed += 1
                self.last_error = str(exc)[:180]
        finally:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass

    def stop(self, timeout_seconds: float) -> bool:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
        ):
            return False
        try:
            timeout = float(timeout_seconds)
        except (OverflowError, TypeError, ValueError):
            return False
        if not math.isfinite(timeout) or timeout <= 0:
            return False
        timeout = min(timeout, 10.0)
        with self._state_lock:
            if not self._thread.is_alive():
                return self.pending.empty()
            should_signal = not self._stopping
            self._stopping = True
        deadline = time.monotonic() + timeout
        if should_signal:
            try:
                self.pending.put(_STOP_WRITER, timeout=timeout)
            except queue.Full:
                with self._state_lock:
                    self._stopping = False
                    self.failed += 1
                    self.last_error = "snapshot writer shutdown timed out with queued records"
                return False
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        stopped = not self._thread.is_alive()
        if not stopped:
            with self._state_lock:
                self.failed += 1
                self.last_error = "snapshot writer shutdown timed out with queued records"
        return stopped

    def status(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "queued": self.pending.qsize(),
                "dropped": self.dropped,
                "failed": self.failed,
                "last_error": self.last_error,
            }


def record_decision_snapshot(
    root: str | Path,
    *,
    ticker: str,
    event_id: str,
    decision: str,
    configuration_version: str,
    snapshot: Mapping[str, Any],
    snapshot_hash: str,
    gate_causal_chain: Any,
    standard_proposal: Optional[Mapping[str, Any]] = None,
    proposal_created_at: Optional[str] = None,
) -> bool:
    """Queue one fully source-validated 41-field snapshot for local persistence."""
    try:
        from ats.llm.offline_learning import compute_input_snapshot_hash
        from ats.strategy.ipo_data_contracts import IPO_REQUIRED_FIELDS

        if not isinstance(snapshot, Mapping) or set(snapshot) != {
            "as_of_time", "configuration_hash", "data_contract_hash", "features"
        }:
            return False
        features = snapshot.get("features")
        if not isinstance(features, Mapping) or set(features) != set(IPO_REQUIRED_FIELDS):
            return False
        if not isinstance(ticker, str) or not re.fullmatch(r"\d{6}", ticker):
            return False
        if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 160:
            return False
        if decision not in {"ENTRY", "WATCH", "BLOCK"}:
            return False
        if (
            not isinstance(configuration_version, str)
            or not configuration_version.strip()
            or len(configuration_version) > 80
        ):
            return False
        if not isinstance(gate_causal_chain, list) or len(gate_causal_chain) > 100:
            return False
        if any(not isinstance(item, str) or len(item) > 500 for item in gate_causal_chain):
            return False
        if not isinstance(snapshot_hash, str) or not _HEX_64.fullmatch(snapshot_hash):
            return False
        normalized_snapshot = json.loads(_canonical(dict(snapshot)).decode("utf-8"))
        if compute_input_snapshot_hash(normalized_snapshot) != snapshot_hash:
            return False
        configuration_hash = snapshot.get("configuration_hash")
        data_contract_hash = snapshot.get("data_contract_hash")
        if (
            not isinstance(configuration_hash, str) or not _HEX_64.fullmatch(configuration_hash)
            or not isinstance(data_contract_hash, str) or not _HEX_64.fullmatch(data_contract_hash)
        ):
            return False
        snapshot_json = _canonical(normalized_snapshot).decode("utf-8")
        causal_json = _canonical(gate_causal_chain).decode("utf-8")
        if standard_proposal is None:
            normalized_proposal: Dict[str, Any] = {}
        elif isinstance(standard_proposal, Mapping):
            normalized_proposal = json.loads(_canonical(dict(standard_proposal)).decode("utf-8"))
        else:
            return False
        proposal_json = _canonical(normalized_proposal).decode("utf-8")
        proposal_time = proposal_created_at or normalized_snapshot["as_of_time"]
        try:
            parsed_proposal_time = datetime.fromisoformat(str(proposal_time).replace("Z", "+00:00"))
            parsed_cutoff = datetime.fromisoformat(
                str(normalized_snapshot["as_of_time"]).replace("Z", "+00:00")
            )
            if (
                parsed_proposal_time.tzinfo is None or parsed_proposal_time.utcoffset() is None
                or parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None
                or parsed_proposal_time > parsed_cutoff
            ):
                return False
        except (TypeError, ValueError, OverflowError):
            return False
        encoded_size = (
            len(snapshot_json.encode("utf-8")) + len(causal_json.encode("utf-8"))
            + len(proposal_json.encode("utf-8"))
        )
        if encoded_size > _MAX_RECORD_BYTES:
            return False
        record = {
            "snapshot_hash": snapshot_hash.lower(),
            "ticker": ticker,
            "event_id": event_id.strip(),
            "cutoff": normalized_snapshot["as_of_time"],
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "decision": decision,
            "configuration_version": configuration_version.strip(),
            "configuration_hash": configuration_hash.lower(),
            "data_contract_hash": data_contract_hash.lower(),
            "input_snapshot_json": snapshot_json,
            "gate_causal_chain_json": causal_json,
            "standard_proposal_json": proposal_json,
            "proposal_created_at": str(proposal_time),
        }
        record["snapshot_id"] = hashlib.sha256(_canonical({
            "snapshot_hash": record["snapshot_hash"],
            "event_id": record["event_id"],
            "decision": record["decision"],
            "gate_causal_chain": gate_causal_chain,
        })).hexdigest()
        resolved_root = Path(root).resolve()
        key = str(resolved_root).casefold()
        with _writers_lock:
            writer = _writers.get(key)
            if writer is None:
                writer = _SnapshotWriter(_database_path(resolved_root))
                _writers[key] = writer
        return writer.enqueue(record)
    except (ImportError, OSError, TypeError, ValueError, OverflowError, RecursionError):
        return False


def snapshot_store_summary(root: str | Path) -> Dict[str, Any]:
    """Return bounded read-only progress for the monitor without initializing storage."""
    path = _database_path(Path(root))
    result: Dict[str, Any] = {
        "status": "NOT_STARTED", "snapshot_count": 0,
        "waiting_outcome_count": 0, "latest_captured_at": "",
    }
    if not path.is_file():
        return result
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            row = connection.execute(
                "SELECT COUNT(*), SUM(CASE WHEN label_status='WAITING_OUTCOME' THEN 1 ELSE 0 END), "
                "MAX(captured_at) FROM decision_snapshots"
            ).fetchone()
        finally:
            connection.close()
        if row:
            result.update({
                "status": "READY", "snapshot_count": int(row[0] or 0),
                "waiting_outcome_count": int(row[1] or 0),
                "latest_captured_at": str(row[2] or ""),
            })
    except (OSError, sqlite3.Error, TypeError, ValueError):
        result["status"] = "UNAVAILABLE"
    return result


def snapshot_store_recent(root: str | Path, limit: int = 50) -> list[Dict[str, Any]]:
    """List recent snapshot metadata only; feature values require an explicit selection."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        return []
    path = _database_path(Path(root))
    if not path.is_file():
        return []
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(decision_snapshots)"
                ).fetchall()
            }
            version_column = "configuration_version" if "configuration_version" in columns else "''"
            rows = connection.execute(
                "SELECT snapshot_id, snapshot_hash, ticker, event_id, cutoff, captured_at, "
                f"decision, {version_column}, label_status FROM decision_snapshots "
                "ORDER BY captured_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "snapshot_id": str(row[0]), "snapshot_hash": str(row[1]),
                "ticker": str(row[2]), "event_id": str(row[3]),
                "cutoff": str(row[4]), "captured_at": str(row[5]),
                "decision": str(row[6]), "configuration_version": str(row[7]),
                "label_status": str(row[8]),
            }
            for row in rows
        ]
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return []


def get_snapshot_record(root: str | Path, snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Load one frozen 41-field snapshot for an explicit local UI selection."""
    if not isinstance(snapshot_id, str) or not _HEX_64.fullmatch(snapshot_id):
        return None
    path = _database_path(Path(root))
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(decision_snapshots)"
                ).fetchall()
            }
            version_column = "configuration_version" if "configuration_version" in columns else "''"
            proposal_column = (
                "standard_proposal_json" if "standard_proposal_json" in columns else "'{}'"
            )
            proposal_time_column = (
                "proposal_created_at" if "proposal_created_at" in columns else "''"
            )
            row = connection.execute(
                "SELECT snapshot_hash, ticker, event_id, cutoff, captured_at, decision, "
                f"{version_column}, configuration_hash, data_contract_hash, input_snapshot_json, "
                f"gate_causal_chain_json, label_status, {proposal_column}, {proposal_time_column} "
                "FROM decision_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        snapshot = json.loads(row[9])
        causal_chain = json.loads(row[10])
        proposal = json.loads(row[12])
        if (
            not isinstance(snapshot, dict) or not isinstance(causal_chain, list)
            or not isinstance(proposal, dict)
        ):
            return None
        return {
            "snapshot_id": snapshot_id, "snapshot_hash": str(row[0]),
            "ticker": str(row[1]), "event_id": str(row[2]),
            "cutoff": str(row[3]), "captured_at": str(row[4]),
            "decision": str(row[5]), "configuration_version": str(row[6]),
            "configuration_hash": str(row[7]), "data_contract_hash": str(row[8]),
            "input_snapshot": snapshot, "gate_causal_chain": causal_chain,
            "label_status": str(row[11]),
            "standard_proposal": proposal,
            "proposal_created_at": str(row[13]),
        }
    except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
        return None


def snapshot_writer_status(root: str | Path) -> Dict[str, Any]:
    resolved_root = Path(root).resolve()
    key = str(resolved_root).casefold()
    with _writers_lock:
        writer = _writers.get(key)
    return writer.status() if writer else {"queued": 0, "dropped": 0, "failed": 0, "last_error": ""}


def shutdown_snapshot_writers(timeout_seconds: float = 2.0) -> bool:
    """Drain local snapshot queues during application shutdown within a bounded wait."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
    ):
        return False
    try:
        timeout = float(timeout_seconds)
    except (OverflowError, TypeError, ValueError):
        return False
    if not math.isfinite(timeout) or timeout <= 0:
        return False
    with _writers_lock:
        writers = tuple(_writers.values())
    if not writers:
        return True
    deadline = time.monotonic() + min(timeout, 10.0)
    completed = True
    for writer in writers:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not writer.stop(remaining):
            completed = False
    return completed

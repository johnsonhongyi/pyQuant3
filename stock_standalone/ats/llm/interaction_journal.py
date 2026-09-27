"""Bounded asynchronous journal for validated local Agent responses."""

from __future__ import annotations

import hashlib
import json
import math
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ats.llm.agent_contracts import AgentContractError, validate_agent_envelope


_MAX_RESULT_BYTES = 64 * 1024
_QUEUE_SIZE = 256
_STOP = object()
_writers: Dict[str, "_InteractionWriter"] = {}
_writers_lock = threading.Lock()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _database_path(root: Path) -> Path:
    return root / "data" / "ipo_learning" / "agent_interactions.sqlite"


class _InteractionWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.pending: "queue.Queue[Any]" = queue.Queue(maxsize=_QUEUE_SIZE)
        self.accepted = 0
        self.dropped = 0
        self.failed = 0
        self.last_error = ""
        self._stopping = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name="ipo-agent-interaction-writer", daemon=True
        )
        self._thread.start()

    def enqueue(self, record: Dict[str, Any]) -> bool:
        with self._lock:
            if self._stopping or not self._thread.is_alive():
                self.failed += 1
                self.last_error = self.last_error or "journal writer stopped"
                return False
            try:
                self.pending.put_nowait(record)
                self.accepted += 1
                return True
            except queue.Full:
                self.dropped += 1
                self.last_error = "journal queue full"
                return False

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queued": self.pending.qsize(), "accepted": self.accepted,
                "dropped": self.dropped, "failed": self.failed,
                "last_error": self.last_error[:180],
            }

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
        with self._lock:
            if not self._thread.is_alive():
                return self.pending.empty()
            should_signal = not self._stopping
            self._stopping = True
        deadline = time.monotonic() + timeout
        if should_signal:
            try:
                self.pending.put(_STOP, timeout=timeout)
            except queue.Full:
                with self._lock:
                    self._stopping = False
                    self.failed += 1
                    self.last_error = "interaction writer shutdown timed out with queued records"
                return False
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        stopped = not self._thread.is_alive()
        if not stopped:
            with self._lock:
                self.failed += 1
                self.last_error = "interaction writer shutdown timed out with queued records"
        return stopped

    def _run(self) -> None:
        connection: Optional[sqlite3.Connection] = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=0.25)
            connection.execute("PRAGMA busy_timeout=250")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_interactions (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    as_of_time TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    evidence_ids_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    error_code TEXT NOT NULL
                )"""
            )
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(agent_interactions)"
                ).fetchall()
            }
            if "summary" not in columns:
                connection.execute(
                    "ALTER TABLE agent_interactions ADD COLUMN summary TEXT NOT NULL DEFAULT ''"
                )
            connection.commit()
            while True:
                record = self.pending.get()
                if record is _STOP:
                    self.pending.task_done()
                    break
                try:
                    connection.execute(
                        """INSERT OR IGNORE INTO agent_interactions (
                            request_id, status, ticker, agent_type, as_of_time,
                            completed_at, model_id, prompt_version, summary, evidence_ids_json,
                            result_json, result_sha256, error_code
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        tuple(record[key] for key in (
                            "request_id", "status", "ticker", "agent_type", "as_of_time",
                            "completed_at", "model_id", "prompt_version", "summary", "evidence_ids_json",
                            "result_json", "result_sha256", "error_code",
                        )),
                    )
                    connection.commit()
                except Exception as exc:
                    try:
                        connection.rollback()
                    except sqlite3.Error:
                        pass
                    with self._lock:
                        self.failed += 1
                        self.last_error = str(exc)[:180]
                finally:
                    self.pending.task_done()
        except Exception as exc:
            with self._lock:
                self.failed += self.pending.qsize()
                self.last_error = str(exc)[:180]
        finally:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass


def record_agent_interaction(
    root: str | Path, response: Mapping[str, Any], completed_at: str,
) -> bool:
    """Queue only protocol-validated results; prompts and provider raw output are excluded."""
    try:
        request_id = response.get("request_id")
        status = response.get("status")
        if (
            not isinstance(request_id, str) or not request_id.strip()
            or len(request_id) > 128 or "\x00" in request_id
        ):
            return False
        if status not in {"OK", "INVALID", "UNAVAILABLE"}:
            return False
        if not isinstance(completed_at, str) or not completed_at:
            return False
        envelope = response.get("envelope")
        error_code = response.get("error_code", "")
        if status == "OK":
            envelope = validate_agent_envelope(envelope)
            metadata = envelope["metadata"]
            if metadata.get("request_id") != request_id:
                return False
            result_bytes = _canonical(envelope)
            if len(result_bytes) > _MAX_RESULT_BYTES:
                return False
            result_json = result_bytes.decode("utf-8")
            result_hash = hashlib.sha256(result_bytes).hexdigest()
            ticker = str(metadata.get("ticker", ""))[:16]
            agent_type = str(envelope.get("agent_type", ""))[:40]
            as_of_time = str(metadata.get("as_of_time", ""))[:40]
            model_id = str(metadata.get("model_id", ""))[:160]
            prompt_version = str(metadata.get("prompt_version", ""))[:128]
            evidence_ids = metadata.get("evidence_ids", [])
            summary = _result_summary(result_json)
        else:
            if envelope is not None or not isinstance(error_code, str):
                return False
            result_json = ""
            result_hash = ""
            ticker = agent_type = as_of_time = model_id = prompt_version = ""
            evidence_ids = []
            summary = ""
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        if completed.tzinfo is None or completed.utcoffset() is None:
            return False
        record = {
            "request_id": request_id, "status": status, "ticker": ticker,
            "agent_type": agent_type, "as_of_time": as_of_time,
            "completed_at": completed.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "model_id": model_id, "prompt_version": prompt_version,
            "summary": summary,
            "evidence_ids_json": _canonical(evidence_ids).decode("utf-8"),
            "result_json": result_json, "result_sha256": result_hash,
            "error_code": error_code[:120] if isinstance(error_code, str) else "",
        }
        key = str(Path(root).resolve())
        with _writers_lock:
            writer = _writers.get(key)
            if writer is None:
                writer = _InteractionWriter(_database_path(Path(key)))
                _writers[key] = writer
        return writer.enqueue(record)
    except Exception:
        return False


def interaction_journal_status(root: str | Path) -> Dict[str, Any]:
    key = str(Path(root).resolve())
    with _writers_lock:
        writer = _writers.get(key)
    status = writer.snapshot() if writer is not None else {
        "queued": 0, "accepted": 0, "dropped": 0, "failed": 0, "last_error": "",
    }
    status["path"] = str(_database_path(Path(key)))
    return status


def recent_agent_interactions(root: str | Path, limit: int = 100) -> list[Dict[str, Any]]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        return []
    path = _database_path(Path(root))
    if not path.is_file():
        return []
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            rows = connection.execute(
                "SELECT request_id, status, ticker, agent_type, as_of_time, completed_at, "
                "model_id, prompt_version, summary, evidence_ids_json, result_sha256, error_code "
                "FROM agent_interactions ORDER BY completed_at DESC LIMIT ?", (limit,),
            ).fetchall()
        finally:
            connection.close()
        return [{
            "request_id": str(row[0]), "status": str(row[1]), "ticker": str(row[2]),
            "agent_type": str(row[3]), "as_of_time": str(row[4]),
            "completed_at": str(row[5]), "model_id": str(row[6]),
            "prompt_version": str(row[7]), "summary": str(row[8]),
            "evidence_ids": json.loads(row[9]),
            "result_sha256": str(row[10]), "error_code": str(row[11]),
        } for row in rows]
    except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
        return []


def get_agent_interaction_detail(root: str | Path, request_id: str) -> Optional[Dict[str, Any]]:
    if (
        not isinstance(request_id, str) or not request_id.strip()
        or len(request_id) > 128 or "\x00" in request_id
    ):
        return None
    path = _database_path(Path(root))
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)
        try:
            row = connection.execute(
                "SELECT status, result_json, result_sha256, error_code FROM agent_interactions "
                "WHERE request_id=?", (request_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        result = json.loads(row[1]) if row[1] else None
        if result is not None:
            result = validate_agent_envelope(result)
            digest = hashlib.sha256(_canonical(result)).hexdigest()
            if digest != row[2]:
                return None
        return {
            "request_id": request_id, "status": str(row[0]),
            "result": result, "result_sha256": str(row[2]),
            "error_code": str(row[3]),
        }
    except (AgentContractError, OSError, sqlite3.Error, TypeError, ValueError, RecursionError, UnicodeError):
        return None


def _result_summary(result_json: Any) -> str:
    try:
        envelope = json.loads(result_json) if isinstance(result_json, str) and result_json else None
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        if not isinstance(payload, dict):
            return ""
        agent_type = envelope.get("agent_type")
        if agent_type == "MARKET_REGIME":
            return "阶段 {stage} · 情绪 {score}".format(
                stage=payload.get("stage_hint", ""),
                score=payload.get("sentiment_score", ""),
            )[:300]
        if agent_type == "CASE_RETRIEVAL":
            cases = payload.get("similar_cases", [])
            return f"相似案例 {len(cases) if isinstance(cases, list) else 0} 条"
        if agent_type == "POST_CLOSE_REVIEW":
            state = "标签成熟" if payload.get("labels_mature") is True else "标签未成熟"
            draft = str(payload.get("review_draft", "")).replace("\r", " ").replace("\n", " ")
            return f"{state} · {draft[:220]}"
    except (TypeError, ValueError, RecursionError):
        return ""
    return ""


def shutdown_interaction_writers(timeout_seconds: float = 2.0) -> bool:
    """Drain all interaction journal queues within a shared bounded deadline."""
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

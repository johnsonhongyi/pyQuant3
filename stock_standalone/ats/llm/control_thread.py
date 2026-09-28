"""Dedicated parent-side controller for the gated IPO LLM Worker."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import threading
import time
from collections import deque
from typing import Any, Dict, Mapping, Optional, Tuple

from ats.llm.llm_worker import LLMWorkerProcess
from ats.llm.interaction_journal import (
    interaction_journal_status, record_agent_interaction,
)
from ats.llm.worker_protocol import WorkerProtocolError, decode_worker_request, encode_worker_request


_COMMAND_QUEUE_SIZE = 100
_MAX_COMMAND_BATCH = 32
_MAX_SUBMIT_BATCH = 8
_REQUEST_QUEUE_TTL_SECONDS = 30.0
_STATUS_INTERVAL_SECONDS = 1.0
_LOOP_INTERVAL_SECONDS = 0.1


def _is_market_session_active() -> bool:
    try:
        from ats.tdx_realtime_fetcher import is_trading_time

        return bool(is_trading_time()[0])
    except Exception:
        return False


class LLMControlThread(threading.Thread):
    """Own all parent-side multiprocessing queue operations and publish safe status."""

    def __init__(
        self,
        *,
        root: str | Path,
        worker: LLMWorkerProcess,
        provider_preflight: Mapping[str, Any],
        authorization: Mapping[str, Any],
        request_producer: Any = None,
        simulation_only: bool = False,
    ) -> None:
        super().__init__(name="ipo-llm-control", daemon=True)
        if not isinstance(worker, LLMWorkerProcess):
            raise ValueError("worker must be an LLMWorkerProcess")
        if not isinstance(provider_preflight, Mapping) or not isinstance(authorization, Mapping):
            raise ValueError("preflight and authorization must be mappings")
        self._root = Path(root).resolve()
        self._worker = worker
        self._preflight = dict(provider_preflight)
        self._authorization = dict(authorization)
        self._request_producer = request_producer
        self._simulation_only = simulation_only is True
        self._request_producer_status: Dict[str, Any] = {
            "state": "UNAVAILABLE", "reason": "请求生产端未配置", "generated": 0,
            "skipped_stale": 0, "rejected": 0,
        }
        self._commands: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=_COMMAND_QUEUE_SIZE)
        self._stop_requested = threading.Event()
        self._state_lock = threading.Lock()
        self._accepting = False
        self._command_drops = 0
        self._coalesced_requests = 0
        self._stale_requests = 0
        self._expired_requests = 0
        self._invalid_requests = 0
        self._submitted_requests = 0
        self._ok_results = 0
        self._failed_results = 0
        self._last_result: Dict[str, str] = {}
        self._recent_results = deque(maxlen=100)
        self._last_publish_error = ""

    def submit_request(self, request: Mapping[str, Any]) -> bool:
        """Queue a candidate without touching multiprocessing endpoints or Qt state."""
        with self._state_lock:
            if not self._accepting or self._stop_requested.is_set():
                return False
        if not isinstance(request, Mapping):
            return False
        try:
            command = {"request": deepcopy(dict(request)), "queued_at": time.monotonic()}
            self._commands.put_nowait(command)
            return True
        except (queue.Full, TypeError, ValueError, RecursionError):
            with self._state_lock:
                self._command_drops += 1
            return False

    def stop(self) -> None:
        """Request shutdown; the caller never waits for a Provider or process join."""
        self._stop_requested.set()

    def snapshot(self) -> Dict[str, Any]:
        """Return a bounded status view without exposing prompts or model payloads."""
        with self._state_lock:
            return {
                "accepting": self._accepting,
                "command_drops": self._command_drops,
                "coalesced_requests": self._coalesced_requests,
                "stale_requests": self._stale_requests,
                "expired_requests": self._expired_requests,
                "invalid_requests": self._invalid_requests,
                "submitted_requests": self._submitted_requests,
                "ok_results": self._ok_results,
                "failed_results": self._failed_results,
                "last_result": dict(self._last_result),
                "recent_results": [dict(item) for item in self._recent_results],
                "request_producer": dict(self._request_producer_status),
                "journal": interaction_journal_status(self._root),
                "last_publish_error": self._last_publish_error,
            }

    def run(self) -> None:
        latest_by_scope: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]] = {}
        inflight: Dict[str, Tuple[Tuple[str, str], datetime]] = {}
        producer_thread: Optional[threading.Thread] = None
        try:
            self._worker.start(
                provider_preflight=self._preflight,
                authorization=self._authorization,
            )
            if self._request_producer is not None:
                producer_thread = threading.Thread(
                    target=self._request_producer_loop,
                    name="ipo-llm-request-producer", daemon=True,
                )
                producer_thread.start()
            next_publish = 0.0
            market_active = self._simulation_only or _is_market_session_active()
            next_session_check = time.monotonic() + (5.0 if market_active else 60.0)
            while not self._stop_requested.is_set():
                now = time.monotonic()
                if now >= next_session_check:
                    was_market_active = market_active
                    market_active = self._simulation_only or _is_market_session_active()
                    next_session_check = now + (5.0 if market_active else 60.0)
                    if market_active != was_market_active:
                        next_publish = 0.0
                self._drain_commands(latest_by_scope, inflight)
                worker_state = self._worker.snapshot().get("state")
                if worker_state == "READY":
                    self._submit_latest(latest_by_scope, inflight)
                for response in self._worker.poll_results():
                    self._record_result(response, inflight)
                worker_snapshot = self._worker.snapshot()
                if worker_snapshot.get("state") in {"UNAVAILABLE", "DISABLED"}:
                    self._discard_queued(latest_by_scope)
                    inflight.clear()
                accepting = bool(
                    worker_snapshot.get("state") == "READY"
                    and worker_snapshot.get("heartbeat_healthy") is True
                    and self._preflight.get("execution_allowed") is True
                )
                self._set_accepting(accepting)
                now = time.monotonic()
                if now >= next_publish:
                    self._publish_status(worker_snapshot, latest_by_scope, inflight)
                    next_publish = now + (
                        _STATUS_INTERVAL_SECONDS if market_active else 60.0
                    )
                self._stop_requested.wait(
                    _LOOP_INTERVAL_SECONDS if market_active else 60.0
                )
        except Exception:
            self._set_accepting(False)
            self._last_publish_error = "LLM_CONTROL_THREAD_FAILED"
        finally:
            self._set_accepting(False)
            self._stop_requested.set()
            if producer_thread is not None and producer_thread.is_alive():
                producer_thread.join(1.0)
            try:
                self._worker.shutdown(timeout_seconds=1.0)
            except Exception:
                pass
            try:
                self._publish_status(self._worker.snapshot(), {}, {})
            except Exception:
                pass

    def _drain_commands(
        self,
        latest_by_scope: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]],
        inflight: Optional[Mapping[str, Tuple[Tuple[str, str], datetime]]] = None,
    ) -> None:
        for _ in range(_MAX_COMMAND_BATCH):
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                request = decode_worker_request(encode_worker_request(command.get("request")))
                queued_at = command.get("queued_at")
                if isinstance(queued_at, bool) or not isinstance(queued_at, (int, float)):
                    raise WorkerProtocolError("request queue timestamp is invalid")
                key = (request["scope_id"], request["ticker"])
                request_time = _request_time(request)
                latest = latest_by_scope.get(key)
                active_times = [
                    item[1] for item in (inflight or {}).values() if item[0] == key
                ]
                newest_active = max(active_times) if active_times else None
                if (
                    (latest is not None and request_time <= _request_time(latest[0]))
                    or (newest_active is not None and request_time <= newest_active)
                ):
                    with self._state_lock:
                        self._stale_requests += 1
                    continue
                if latest is not None:
                    with self._state_lock:
                        self._coalesced_requests += 1
                latest_by_scope[key] = (request, float(queued_at))
            except (WorkerProtocolError, TypeError, ValueError, OverflowError):
                with self._state_lock:
                    self._invalid_requests += 1
            finally:
                self._commands.task_done()

    def _submit_latest(
        self,
        latest_by_scope: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]],
        inflight: Dict[str, Tuple[Tuple[str, str], datetime]],
    ) -> None:
        now = time.monotonic()
        inflight_scopes = {item[0] for item in inflight.values()}
        submitted = 0
        for key, (request, queued_at) in list(latest_by_scope.items()):
            if now - queued_at > _REQUEST_QUEUE_TTL_SECONDS:
                latest_by_scope.pop(key, None)
                with self._state_lock:
                    self._expired_requests += 1
                continue
            if key in inflight_scopes:
                continue
            if submitted >= _MAX_SUBMIT_BATCH:
                break
            request_id = request["request_id"]
            if request_id in inflight:
                latest_by_scope.pop(key, None)
                with self._state_lock:
                    self._invalid_requests += 1
                continue
            if self._worker.submit(request):
                inflight[request_id] = (key, _request_time(request))
                inflight_scopes.add(key)
                latest_by_scope.pop(key, None)
                submitted += 1
                with self._state_lock:
                    self._submitted_requests += 1
                continue
            if self._worker.snapshot().get("last_error") == "LLM_QUEUE_FULL_DROP":
                break
            latest_by_scope.pop(key, None)
            with self._state_lock:
                self._invalid_requests += 1

    def _record_result(
        self,
        response: Mapping[str, Any],
        inflight: Dict[str, Tuple[Tuple[str, str], datetime]],
    ) -> None:
        request_id = response.get("request_id", "")
        active = inflight.pop(request_id, None)
        key = active[0] if active else None
        envelope = response.get("envelope")
        metadata = envelope.get("metadata", {}) if isinstance(envelope, dict) else {}
        summary_text = _result_summary(envelope)
        summary = {
            "request_id": str(request_id)[:128],
            "status": str(response.get("status", "INVALID"))[:24],
            "ticker": str(metadata.get("ticker", key[1] if key else ""))[:16],
            "agent_type": str(envelope.get("agent_type", ""))[:40] if isinstance(envelope, dict) else "",
            "provider_id": str(response.get("provider_id", ""))[:64],
            "model_id": str(metadata.get("model_id", response.get("model_id", "")))[:160],
            "fallback_error_code": str(response.get("fallback_error_code", ""))[:120],
            "as_of_time": str(metadata.get("as_of_time", ""))[:40],
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary_text,
        }
        record_agent_interaction(self._root, response, summary["completed_at"])
        with self._state_lock:
            if response.get("status") == "OK":
                self._ok_results += 1
            else:
                self._failed_results += 1
            self._last_result = summary
            self._recent_results.append(dict(summary))

    def _discard_queued(
        self, latest_by_scope: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]]
    ) -> None:
        if latest_by_scope:
            with self._state_lock:
                self._command_drops += len(latest_by_scope)
            latest_by_scope.clear()
        while True:
            try:
                self._commands.get_nowait()
                self._commands.task_done()
                with self._state_lock:
                    self._command_drops += 1
            except queue.Empty:
                return

    def _publish_status(
        self,
        worker_snapshot: Mapping[str, Any],
        queued: Mapping[Tuple[str, str], Any],
        inflight: Mapping[str, Any],
    ) -> None:
        path = self._root / "logs" / "llm_runtime_status.json"
        worker_state = str(worker_snapshot.get("state", "UNKNOWN"))
        with self._state_lock:
            counters = {
                "command_drops": self._command_drops,
                "coalesced_requests": self._coalesced_requests,
                "stale_requests": self._stale_requests,
                "expired_requests": self._expired_requests,
                "invalid_requests": self._invalid_requests,
                "submitted_requests": self._submitted_requests,
                "ok_results": self._ok_results,
                "failed_results": self._failed_results,
                "last_result": dict(self._last_result),
                "recent_results": [dict(item) for item in self._recent_results],
                "request_producer": dict(self._request_producer_status),
                "journal": interaction_journal_status(self._root),
            }
        document = {
            "status": worker_state,
            "provider": str(self._preflight.get("backend", "未配置"))[:100],
            "qualified": bool(
                not self._simulation_only
                and worker_state == "READY"
                and worker_snapshot.get("heartbeat_healthy") is True
                and self._preflight.get("execution_allowed") is True
            ),
            "simulation_only": self._simulation_only,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "worker": {
                "state": worker_state,
                "pending_count": int(worker_snapshot.get("pending_count", 0) or 0),
                "queued_count": len(queued) + self._commands.qsize(),
                "inflight_scope_count": len(inflight),
                "dropped_results": int(worker_snapshot.get("dropped_results", 0) or 0),
                "heartbeat_age_seconds": worker_snapshot.get("heartbeat_age_seconds"),
                "heartbeat_healthy": worker_snapshot.get("heartbeat_healthy") is True,
                "last_error": str(worker_snapshot.get("last_error", ""))[:120],
            },
            "interaction": counters,
            "runtime_status_error": self._last_publish_error,
        }
        temp_path = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    document, stream, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                )
                stream.write("\n")
            os.replace(str(temp_path), str(path))
            self._last_publish_error = ""
        except (OSError, TypeError, ValueError, OverflowError):
            self._last_publish_error = "RUNTIME_STATUS_WRITE_FAILED"

    def _set_accepting(self, accepting: bool) -> None:
        with self._state_lock:
            self._accepting = bool(accepting)

    def _poll_request_producer(self, accepting: bool) -> None:
        try:
            report = self._request_producer.poll(runtime_accepting=accepting)
            requests = report.get("requests", []) if isinstance(report, Mapping) else []
            submitted = 0
            generated = _safe_count(report.get("generated")) if isinstance(report, Mapping) else 0
            if isinstance(requests, list):
                for request in requests:
                    accepted = self.submit_request(request)
                    acknowledge = getattr(self._request_producer, "acknowledge", None)
                    if callable(acknowledge) and isinstance(request, Mapping):
                        generated = acknowledge(str(request.get("request_id", "")), accepted)
                    if accepted:
                        submitted += 1
            rejected = max(0, len(requests) - submitted) if isinstance(requests, list) else 0
            reason = str(report.get("reason", ""))[:160] if isinstance(report, Mapping) else ""
            status = {
                "state": "QUEUE_REJECTED" if rejected else str(report.get("state", "UNKNOWN"))[:40],
                "reason": (reason + f"；控制队列拒绝 {rejected} 条")[:200] if rejected else reason,
                "generated": generated,
                "submitted": submitted,
                "skipped_stale": _safe_count(report.get("skipped_stale")),
                "rejected": _safe_count(report.get("rejected")),
                "last_snapshot_id": str(report.get("last_snapshot_id", ""))[:64],
            }
        except Exception:
            status = {
                "state": "FAILED", "reason": "请求生产端异常；本轮未提交请求",
                "generated": 0, "submitted": 0, "skipped_stale": 0,
                "rejected": 1, "last_snapshot_id": "",
            }
        with self._state_lock:
            self._request_producer_status = status

    def _request_producer_loop(self) -> None:
        while not self._stop_requested.is_set():
            if not self._simulation_only and not _is_market_session_active():
                self._stop_requested.wait(60.0)
                continue
            accepting = self.snapshot().get("accepting") is True
            self._poll_request_producer(accepting)
            self._stop_requested.wait(1.0)


def _request_time(request: Mapping[str, Any]) -> datetime:
    value = request.get("as_of_time")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WorkerProtocolError("request as_of_time must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _safe_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _result_summary(envelope: Any) -> str:
    """Expose only a short preview of the validated Agent result, never its prompt."""
    if not isinstance(envelope, Mapping):
        return ""
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        return ""
    agent_type = envelope.get("agent_type")
    if agent_type == "MARKET_REGIME":
        fragments = [
            f"阶段 {payload.get('stage_hint', '')}",
            f"情绪 {payload.get('sentiment_score', '')}",
        ]
        for key, label in (("catalysts", "催化"), ("risk_warnings", "风险")):
            items = payload.get(key)
            if isinstance(items, list) and items:
                fragments.append(label + "：" + "；".join(
                    str(item.get("summary", "")) for item in items[:2]
                    if isinstance(item, Mapping)
                ))
        return " · ".join(value for value in fragments if value.strip())[:300]
    if agent_type == "CASE_RETRIEVAL":
        cases = payload.get("similar_cases")
        cases = cases if isinstance(cases, list) else []
        names = [
            str(item.get("case_id", "")) for item in cases[:3]
            if isinstance(item, Mapping)
        ]
        return f"相似案例 {len(cases)} 条" + ("：" + "、".join(names) if names else "")
    if agent_type == "POST_CLOSE_REVIEW":
        state = "标签成熟" if payload.get("labels_mature") is True else "标签未成熟"
        draft = payload.get("review_draft", "")
        return (state + " · " + str(draft).replace("\r", " ").replace("\n", " "))[:300]
    return ""

"""Explicitly gated Windows-spawn worker for the read-only IPO LLM sidecar."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import multiprocessing
from multiprocessing.connection import wait as wait_connections
import queue
import re
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

from ats.llm.agent_contracts import build_agent_envelope, payload_schema
from ats.llm.worker_protocol import (
    WorkerProtocolError,
    decode_worker_request,
    encode_worker_response,
)
from ats.llm.windows_job import WindowsProcessJob


_STOP_MESSAGE = "R9_LLM_WORKER_STOP"
_READY_MESSAGE = "R9_LLM_WORKER_READY"
_HEARTBEAT_MESSAGE = "R9_LLM_WORKER_HEARTBEAT"
_MAX_QUEUE_SIZE = 100
_MAX_RESULT_BATCH = 8
_RESULT_BUDGET_SECONDS = 0.002
_REQUEST_DEADLINE_SECONDS = 30.0
_HEARTBEAT_INTERVAL_SECONDS = 0.5
_HEARTBEAT_STALE_SECONDS = 3.0


def _worker_entry(
    request_queue: Any,
    result_queue: Any,
    heartbeat_queue: Any,
    backend_factory: Callable[[], Any],
    request_timeout_seconds: float,
    startup_gate: Any,
) -> None:
    """Consume JSON requests in the spawned process and emit validated envelopes."""
    if not startup_gate.wait(timeout=10.0):
        return
    heartbeat_stop = threading.Event()

    def heartbeat_loop() -> None:
        try:
            while not heartbeat_stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
                try:
                    heartbeat_queue.put_nowait(_HEARTBEAT_MESSAGE)
                except queue.Full:
                    continue
                except (OSError, ValueError):
                    return
        except Exception:
            return

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop, name="ipo-llm-worker-heartbeat", daemon=True
    )
    backend: Any = None
    heartbeat_thread.start()
    try:
        try:
            backend = backend_factory()
        except Exception:
            return
        try:
            result_queue.put_nowait(_READY_MESSAGE)
        except queue.Full:
            return
        while True:
            try:
                message = request_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if message == _STOP_MESSAGE:
                break
            request: Optional[Dict[str, Any]] = None
            try:
                request = decode_worker_request(message)
                generate_request = getattr(backend, "generate_request", None)
                if callable(generate_request):
                    response = generate_request(
                        request, payload_schema(request["agent_type"]),
                        timeout_seconds=request_timeout_seconds,
                    )
                else:
                    import json

                    prompt = request["prompt"] + "\n\n已验证上下文(JSON)：\n" + json.dumps(
                        request["context"], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"), allow_nan=False,
                    )
                    response = backend.generate(
                        prompt, payload_schema(request["agent_type"]),
                        timeout_seconds=request_timeout_seconds,
                    )
                if not isinstance(response, Mapping) or response.get("status") != "OK":
                    backend_error = (
                        response.get("error_code") if isinstance(response, Mapping) else None
                    )
                    if not isinstance(backend_error, str) or not re.fullmatch(
                        r"[A-Za-z0-9_.-]{1,80}", backend_error
                    ):
                        backend_error = "provider_unavailable"
                    packet = {
                        "request_id": request["request_id"], "status": "UNAVAILABLE",
                        "envelope": None, "error_code": backend_error,
                    }
                else:
                    envelope = build_agent_envelope(
                        request["agent_type"], response.get("proposal"),
                        request_id=request["request_id"], scope_id=request["scope_id"],
                        ticker=request["ticker"], as_of_time=request["as_of_time"],
                        generated_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                        model_id=request["model_id"], prompt_version=request["prompt_version"],
                        evidence_ids=request["evidence_ids"],
                    )
                    packet = {
                        "request_id": request["request_id"], "status": "OK",
                        "envelope": envelope, "error_code": "",
                    }
                encoded = encode_worker_response(packet, request)
            except (WorkerProtocolError, ValueError, TypeError, OverflowError):
                if request is None:
                    continue
                encoded = encode_worker_response({
                    "request_id": request["request_id"], "status": "INVALID",
                    "envelope": None, "error_code": "provider_output_invalid",
                }, request)
            except Exception:
                if request is None:
                    continue
                encoded = encode_worker_response({
                    "request_id": request["request_id"], "status": "UNAVAILABLE",
                    "envelope": None, "error_code": "provider_runtime_failure",
                }, request)
            try:
                result_queue.put_nowait(encoded)
            except queue.Full:
                # The control thread records queue pressure; never block the Worker on a result.
                continue
    finally:
        close_backend = getattr(backend, "close", None)
        if callable(close_backend):
            try:
                close_backend()
            except Exception:
                # Cleanup is best-effort; the Worker process remains the isolation boundary.
                pass
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=0.5)


class LLMWorkerProcess:
    """Bounded multiprocessing endpoint; every queue operation belongs to one control thread."""

    def __init__(
        self,
        backend_factory: Callable[[], Any],
        request_timeout_seconds: float,
    ) -> None:
        if not callable(backend_factory):
            raise ValueError("backend_factory must be callable")
        if (
            isinstance(request_timeout_seconds, bool)
            or not isinstance(request_timeout_seconds, (int, float))
            or request_timeout_seconds != 30.0
        ):
            raise ValueError("R9 Worker 硬截止必须由配置显式固定为 30 秒")
        self._backend_factory = backend_factory
        self._request_timeout_seconds = float(request_timeout_seconds)
        self._context = multiprocessing.get_context("spawn")
        self._request_queue: Any = None
        self._result_queue: Any = None
        self._heartbeat_queue: Any = None
        self._process: Any = None
        self._process_job: Optional[WindowsProcessJob] = None
        self._owner_thread_id: Optional[int] = None
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._state = "STOPPED"
        self._dropped_results = 0
        self._last_error = ""
        self._started_at: Optional[float] = None
        self._last_heartbeat_at: Optional[float] = None

    def start(
        self,
        *,
        provider_preflight: Mapping[str, Any],
        authorization: Mapping[str, Any],
    ) -> bool:
        """Start only after preflight and explicit provider/isolation acceptance both pass."""
        self._claim_control_thread()
        local_authorizations = {
            "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
            "acceptance_id",
        }
        remote_authorizations = local_authorizations | {
            "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
        }
        remote_provider = isinstance(provider_preflight, Mapping) and provider_preflight.get("backend") in {
            "antigravity_cli", "codex_cli",
        }
        accepted_keysets = {frozenset(remote_authorizations)} if remote_provider else {
            frozenset(local_authorizations), frozenset(remote_authorizations),
        }
        required_authorizations = remote_authorizations if remote_provider else local_authorizations
        required_flags = set(required_authorizations) - {"acceptance_id"}
        if (
            self._state not in {"STOPPED", "DISABLED"}
            or not isinstance(provider_preflight, Mapping)
            or provider_preflight.get("execution_allowed") is not True
            or provider_preflight.get("state") != "READY"
            or not isinstance(authorization, Mapping)
            or frozenset(authorization) not in accepted_keysets
            or any(authorization.get(key) is not True for key in required_flags)
            or not isinstance(authorization.get("acceptance_id"), str)
            or not authorization.get("acceptance_id", "").strip()
        ):
            self._state = "DISABLED"
            self._last_error = "R9_PROVIDER_OR_ISOLATION_ACCEPTANCE_REQUIRED"
            return False
        try:
            self._process_job = WindowsProcessJob()
        except Exception:
            self._state = "UNAVAILABLE"
            self._last_error = "WINDOWS_PROCESS_TREE_ISOLATION_UNAVAILABLE"
            return False
        try:
            self._request_queue = self._context.Queue(maxsize=_MAX_QUEUE_SIZE)
            self._result_queue = self._context.Queue(maxsize=_MAX_QUEUE_SIZE)
            self._heartbeat_queue = self._context.Queue(maxsize=8)
            startup_gate = self._context.Event()
            self._process = self._context.Process(
                target=_worker_entry,
                args=(
                    self._request_queue, self._result_queue, self._heartbeat_queue,
                    self._backend_factory,
                    self._request_timeout_seconds,
                    startup_gate,
                ),
                name="ipo-llm-worker",
                daemon=True,
            )
            self._process.start()
        except Exception:
            self._close_process_job()
            self._close_queues()
            self._process = None
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_SPAWN_FAILED"
            return False
        try:
            self._process_job.assign_process(int(self._process.pid or 0))
            startup_gate.set()
        except Exception:
            try:
                self._process.terminate()
                self._process.join(timeout=0.5)
            except Exception:
                pass
            self._close_process_job()
            try:
                self._process.join(timeout=0.5)
                if self.worker_exited():
                    self._process.close()
            except (OSError, ValueError):
                pass
            self._close_queues()
            self._process = None
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_PROCESS_TREE_ASSIGN_FAILED"
            return False
        self._state = "STARTING"
        self._last_error = ""
        self._started_at = time.monotonic()
        self._last_heartbeat_at = None
        return True

    def submit(self, request: Mapping[str, Any]) -> bool:
        self._require_owner()
        if self._state not in {"STARTING", "READY"} or self._request_queue is None:
            return False
        try:
            from ats.llm.worker_protocol import encode_worker_request

            encoded = encode_worker_request(request)
            request_id = request["request_id"]
            if request_id in self._pending:
                return False
            self._request_queue.put_nowait(encoded)
            self._pending[request_id] = {
                "request": dict(request),
                "deadline": time.monotonic() + _REQUEST_DEADLINE_SECONDS,
            }
            return True
        except (WorkerProtocolError, KeyError, TypeError, ValueError):
            self._last_error = "WORKER_REQUEST_INVALID_OR_QUEUE_FULL"
            return False
        except queue.Full:
            self._last_error = "LLM_QUEUE_FULL_DROP"
            return False

    def poll_results(self) -> list[Dict[str, Any]]:
        """Drain at most eight results or two milliseconds, whichever comes first."""
        self._require_owner()
        if self._result_queue is None:
            return []
        self._drain_heartbeats()
        now = time.monotonic()
        if (
            self._state == "STARTING" and self._started_at is not None
            and now - self._started_at > _REQUEST_DEADLINE_SECONDS
        ):
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_STARTUP_TIMEOUT_CIRCUIT_OPEN"
            self.shutdown(timeout_seconds=0.0)
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_STARTUP_TIMEOUT_CIRCUIT_OPEN"
            return []
        heartbeat_reference = self._last_heartbeat_at or self._started_at
        if (
            self._state == "READY" and heartbeat_reference is not None
            and now - heartbeat_reference > _HEARTBEAT_STALE_SECONDS
        ):
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_HEARTBEAT_STALE_CIRCUIT_OPEN"
            self.shutdown(timeout_seconds=0.0)
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_HEARTBEAT_STALE_CIRCUIT_OPEN"
            return []
        expired = [
            request_id for request_id, pending in self._pending.items()
            if now >= pending["deadline"]
        ]
        if expired:
            # One sequential Worker owns these requests. A deadline expiry opens
            # the breaker and retires it so queued work cannot run stale later.
            self._state = "UNAVAILABLE"
            self._last_error = "LLM_REQUEST_TIMEOUT_CIRCUIT_OPEN"
            self.shutdown(timeout_seconds=0.0)
            self._state = "UNAVAILABLE"
            self._last_error = "LLM_REQUEST_TIMEOUT_CIRCUIT_OPEN"
            return []
        started = time.monotonic()
        results: list[Dict[str, Any]] = []
        while len(results) < _MAX_RESULT_BATCH and time.monotonic() - started < _RESULT_BUDGET_SECONDS:
            try:
                message = self._result_queue.get_nowait()
            except queue.Empty:
                break
            if message == _READY_MESSAGE:
                self._state = "READY"
                continue
            request_id = ""
            try:
                from ats.llm.worker_protocol import decode_worker_response

                import json
                raw = json.loads(message)
                request_id = raw.get("request_id", "") if isinstance(raw, dict) else ""
                pending = self._pending.pop(request_id, None)
                if pending is None:
                    self._dropped_results += 1
                    continue
                results.append(decode_worker_response(message, pending["request"]))
            except (WorkerProtocolError, TypeError, ValueError):
                self._pending.pop(request_id, None)
                self._dropped_results += 1
                self._last_error = "WORKER_RESPONSE_INVALID"
        if self._process is not None and self.worker_exited():
            if self._state not in {"STOPPED", "DISABLED", "UNAVAILABLE"}:
                self._last_error = (
                    "WORKER_STARTUP_FAILED" if self._state == "STARTING"
                    else "WORKER_EXITED_UNEXPECTEDLY"
                )
            self._state = "UNAVAILABLE"
            self._pending.clear()
        return results

    def worker_exited(self) -> bool:
        """Check the process sentinel without a blocking join or Process.is_alive()."""
        self._require_owner()
        if self._process is None:
            return True
        return bool(wait_connections([self._process.sentinel], timeout=0))

    def shutdown(self, timeout_seconds: float = 1.0) -> bool:
        """Bounded close for the LLM control thread; never call from ATS or Qt event paths."""
        self._require_owner()
        process = self._process
        if process is None:
            self._close_process_job()
            self._close_queues()
            self._state = "STOPPED"
            return True
        try:
            try:
                normalized_timeout = float(timeout_seconds)
                if (
                    isinstance(timeout_seconds, bool)
                    or not isinstance(timeout_seconds, (int, float))
                    or not math.isfinite(normalized_timeout)
                    or normalized_timeout < 0
                ):
                    normalized_timeout = 0.0
            except (TypeError, ValueError, OverflowError):
                normalized_timeout = 0.0
            if not self.worker_exited() and self._request_queue is not None:
                try:
                    self._request_queue.put_nowait(_STOP_MESSAGE)
                except queue.Full:
                    pass
            process.join(timeout=min(normalized_timeout, 2.0))
            if self.worker_exited():
                self._state = "STOPPED"
                self._close_process_job()
                try:
                    process.close()
                except (OSError, ValueError):
                    pass
                return self._close_queues()
            process.terminate()
            process.join(timeout=0.5)
            self._close_process_job()
            process.join(timeout=0.5)
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_TERMINATED_AFTER_SHUTDOWN_TIMEOUT"
            exited = self.worker_exited()
            if exited:
                try:
                    process.close()
                except (OSError, ValueError):
                    pass
            return self._close_queues() and exited
        except Exception:
            self._state = "UNAVAILABLE"
            self._last_error = "WORKER_SHUTDOWN_FAILED"
            self._close_process_job()
            self._close_queues()
            return False
        finally:
            self._pending.clear()
            self._close_process_job()
            self._process = None

    def snapshot(self) -> Dict[str, Any]:
        """Return a bounded immutable-style status copy for the monitor/control thread."""
        heartbeat_reference = self._last_heartbeat_at or self._started_at
        heartbeat_age = (
            max(0.0, time.monotonic() - heartbeat_reference)
            if heartbeat_reference is not None else None
        )
        return {
            "state": self._state,
            "pending_count": len(self._pending),
            "dropped_results": self._dropped_results,
            "last_error": self._last_error,
            "heartbeat_age_seconds": heartbeat_age,
            "heartbeat_healthy": (
                self._state == "READY" and heartbeat_age is not None
                and heartbeat_age <= _HEARTBEAT_STALE_SECONDS
            ),
        }

    def _drain_heartbeats(self) -> None:
        endpoint = self._heartbeat_queue
        if endpoint is None:
            return
        for _ in range(8):
            try:
                message = endpoint.get_nowait()
            except queue.Empty:
                return
            if message == _HEARTBEAT_MESSAGE:
                self._last_heartbeat_at = time.monotonic()

    def _claim_control_thread(self) -> None:
        if self._owner_thread_id is None:
            self._owner_thread_id = threading.get_ident()
        self._require_owner()

    def _require_owner(self) -> None:
        if self._owner_thread_id != threading.get_ident():
            raise RuntimeError("LLM multiprocessing queues are owned by the control thread")

    def _close_queues(self) -> bool:
        clean = True
        for name in ("_request_queue", "_result_queue", "_heartbeat_queue"):
            endpoint = getattr(self, name)
            if endpoint is None:
                continue
            try:
                endpoint.close()
                endpoint.cancel_join_thread()
            except (OSError, ValueError):
                clean = False
            finally:
                setattr(self, name, None)
        return clean

    def _close_process_job(self) -> None:
        job = self._process_job
        self._process_job = None
        if job is not None:
            try:
                job.close()
            except Exception:
                pass

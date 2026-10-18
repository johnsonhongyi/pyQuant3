# -*- coding: utf-8 -*-
"""Independent Antigravity (AGV) desktop pull agent worker for chat and strategy research."""
from __future__ import annotations

import argparse
import configparser
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

def _is_packaged() -> bool:
    return (getattr(sys, 'frozen', False) or '__compiled__' in globals()
            or 'NUITKA_ONEFILE_DIRECTORY' in os.environ or hasattr(sys, 'nuitka_version'))


STRATEGY_ROOT = Path(os.path.abspath(os.fspath(__file__))).parent
if _is_packaged():
    root = Path(os.path.dirname(os.path.abspath(sys.executable)))
    if root.name.lower() in ('webtools', 'window_manager'):
        root = root.parent
        if root.name.lower() == 'webtools':
            root = root.parent
    APP_ROOT = root
else:
    APP_ROOT = STRATEGY_ROOT.parent

for _p in (STRATEGY_ROOT, APP_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from desktop_bridge_runtime import ProgressPublisher, ResultOutbox, EventInbox
from desktop_runtime import DesktopRuntimeProbe
from desktop_strategy_agent import (
    NoRedirect, DesktopPeer, _error_details, _peer_error_code, ats_evidence
)
from follow_ai import RESPONSE_SCHEMA, digest
from ats.llm.antigravity_cli_backend import matches_json_schema, _coerce_structured_output
from ats.llm.cli_process import BoundedCLIError, run_bounded_cli
from ats.llm.cli_paths import resolve_cli_path


def _emit_log(record: dict):
    line = json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **record}, ensure_ascii=False)
    print(line, flush=True)


class AntigravityCatalog:
    """Cache the signed-in CLI catalog; never invent available models."""

    def __init__(self, cli_path: str = ""):
        self.cli_override = cli_path.strip()
        self.engine = ""
        self.models = []
        self.default_model = ""
        self.catalog_error = ""
        self.fetched_at = 0.0
        self.retry_at = 0.0
        self.probe()

    @property
    def model_ids(self) -> list[str]:
        return [m["id"] if isinstance(m, dict) else m for m in self.models]

    def probe(self) -> bool:
        now = time.time()
        if now < self.retry_at:
            return bool(self.models and self.engine)
        path = self.cli_override or resolve_cli_path("", "agy")
        if path and Path(path).is_file():
            engine = str(Path(path).resolve())
            if engine != self.engine:
                self.models = []
                self.fetched_at = 0.0
            self.engine = engine
            if self.models and now - self.fetched_at < 300:
                return True
            try:
                result = run_bounded_cli([self.engine, "models"], cwd=Path(self.engine).parent,
                    stdin_bytes=b"", timeout_seconds=15, max_stdout_bytes=64 * 1024,
                    hidden_console=True)
                models = _parse_model_catalog(result.stdout.decode("utf-8", errors="replace"))
                if result.returncode or not models:
                    raise BoundedCLIError("AGY_MODEL_CATALOG_EMPTY")
                self.models = models
                self.default_model = next((m["id"] for m in models
                    if "flash" in m["id"].lower() and m["default_effort"] == "low"), models[0]["id"])
                self.fetched_at = time.time()
                self.retry_at = 0.0
                self.catalog_error = ""
                return True
            except (OSError, ValueError, BoundedCLIError) as exc:
                self.catalog_error = getattr(exc, "code", "AGY_MODEL_CATALOG_FAILED")
                self.models = []
                self.default_model = ""
                self.retry_at = time.time() + 30
                return False
        self.engine = ""
        self.models = []
        self.default_model = ""
        self.catalog_error = "AGY_ENGINE_UNAVAILABLE"
        self.retry_at = time.time() + 20.0
        return False

    def status(self) -> dict:
        return {
            "engine": self.engine,
            "engine_available": bool(self.engine and Path(self.engine).is_file()),
            "models_available": bool(self.models),
            "default_model": self.default_model,
            "catalog_error": self.catalog_error,
        }


def _parse_model_catalog(output: str) -> list[dict]:
    models = {}
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        model, name = parts
        if (not re.fullmatch(r"[a-zA-Z0-9][\w.:-]*", model)
                or model.lower().startswith("gpt-oss")
                or re.search(r"\b(unavailable|disabled)\b", name, re.I)):
            continue
        # CLI rows are ID + tab + label, not log messages or column headers.
        if "\t" not in line:
            continue
        fixed = re.search(r"-(low|medium|high|xhigh|max)$", model)
        labeled = re.search(r"\((low|medium|high|xhigh|max)\)\s*$", name, re.I)
        discovered_effort = fixed[1] if fixed else labeled[1].lower() if labeled else ""
        # `agy models` lists concrete effort slugs. A model without an explicit
        # tier (for example, Claude Thinking) uses the CLI's model default.
        efforts = [discovered_effort] if discovered_effort else ["auto"]
        models[model] = {"id": model, "name": name, "efforts": efforts,
                         "default_effort": efforts[0]}
    return list(models.values())


def _select_model(context, models, default_model):
    model = context.get("model") or default_model
    if model not in [m.get("id") if isinstance(m, dict) else m for m in models]:
        raise BoundedCLIError("AGY_MODEL_UNAVAILABLE_REFRESH_REQUIRED")
    return model


def _post_chat_result(peer: DesktopPeer, payload: dict, attempts: int = 3):
    last_error = None
    for attempt in range(attempts):
        started = time.perf_counter()
        try:
            return peer.post('chat_result', payload, timeout=3)
        except HTTPError as exc:
            if exc.code not in (408, 429) and exc.code < 500:
                raise
            last_error = exc
        except (OSError, TimeoutError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            _emit_log({
                'status': 'degraded', 'stage': 'chat_result_retry', 'operation': 'chat_result',
                'job_id': str(payload.get('id', ''))[:12], 'attempt': attempt + 1,
                'elapsed_ms': round((time.perf_counter() - started) * 1000),
                'error_code': _peer_error_code(last_error), 'error_detail': _error_details(last_error),
            })
            time.sleep(0.25 * (2 ** attempt))
    raise last_error


def _chat_event_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_chat_event_text(part) for part in value)
    if isinstance(value, dict):
        for key in ("text", "content", "delta", "response"):
            text = _chat_event_text(value.get(key))
            if text:
                return text
    return ""


def _has_antigravity_result_event(output: bytes) -> bool:
    for line in output.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("event") == "result" and isinstance(event.get("result"), dict):
            return True
    return False


def _antigravity_result_event(output: bytes):
    result = None
    for line in output.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("event") == "result":
            result = event.get("result") if isinstance(event.get("result"), dict) else None
    return result


def _job_cli_timeout(job: dict, default: int = 180) -> int:
    remaining = job.get("remaining_seconds")
    if remaining is None and job.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(str(job["expires_at"]).replace("Z", "+00:00"))
            remaining = expiry.timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            remaining = None
    try:
        seconds = float(remaining) if remaining is not None else float(default)
    except (TypeError, ValueError, OverflowError):
        seconds = float(default)
    if not 1 < seconds < 1_000_000:
        raise TimeoutError("AGY_JOB_DEADLINE_EXPIRED")
    return max(1, min(180, int(seconds) - 2))


def _chat_error_info(error: Exception):
    cause = error.__cause__ if isinstance(error, BoundedCLIError) and error.code == "CLI_OUTPUT_CALLBACK_FAILED" else None
    root_error = cause or error
    error_code = str(getattr(root_error, "peer_code", "") or getattr(root_error, "code", "") or type(root_error).__name__)[:120]
    details = _error_details(root_error)
    if getattr(root_error, "agy_error_message", ""):
        details["message"] = root_error.agy_error_message
    if cause:
        details["callback_error_code"] = error.code
    return error_code, details


def _agy_result_failure(result: dict) -> BoundedCLIError:
    status = str(result.get("status") or "ERROR").upper()
    error = BoundedCLIError("AGY_RESULT_" + (status if re.fullmatch(r"[A-Z_]{1,32}", status) else "ERROR"))
    message = result.get("error")
    if isinstance(message, dict):
        message = message.get("message")
    if isinstance(message, str):
        message = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", message)
        message = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", message)
        message = re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password)[\"']?\s*[:=]\s*[\"']?)[^\s&\"']+", r"\1[redacted]", message)
        message = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", message)
        error.agy_error_message = " ".join(message.split())[:640]
    return error


def _resolve_cli_effort(model: str, requested, models: list[dict], fallback: str = "low") -> str:
    model_info = next((item for item in models if isinstance(item, dict) and item.get("id") == model), {})
    has_catalog_efforts = isinstance(model_info.get("efforts"), list)
    efforts = model_info.get("efforts") if has_catalog_efforts else []
    efforts = [item for item in efforts if isinstance(item, str)]
    if isinstance(requested, str) and requested in efforts:
        return requested
    # Claimed jobs freeze this pair on the server. Only adapt before enqueueing.
    if requested and has_catalog_efforts and (efforts or requested != "auto"):
        raise BoundedCLIError("AGY_REASONING_EFFORT_UNSUPPORTED_REFRESH_REQUIRED")
    default = model_info.get("default_effort")
    if isinstance(default, str) and default in efforts:
        return default
    if efforts:
        return efforts[0]
    if has_catalog_efforts:
        return "auto"
    return requested if isinstance(requested, str) and requested in {"low", "medium", "high", "xhigh", "max"} else fallback


class _AntigravityChatStream:
    def __init__(self, publisher, job_id, model, effort):
        self.publisher = publisher
        self.job_id = job_id
        self.thread_id = ""
        self.model = model
        self.effort = effort
        self.pending = bytearray()
        self.content = []
        self.output_tokens = 0
        self.result_event = None
        self.first_token_at = None
        self.completed_at = None
        self.initialized_at = None
        self.token_usage = {}
        self.actual_model = ""
        self.last_progress_at = 0.0

    def feed(self, chunk: bytes):
        self.pending.extend(chunk)
        while b"\n" in self.pending:
            line, _, rest = self.pending.partition(b"\n")
            self.pending = bytearray(rest)
            self._handle_line(bytes(line))

    def finish(self):
        if self.pending:
            self._handle_line(bytes(self.pending))
            self.pending.clear()

    def _publish(self, force=False):
        now = time.monotonic()
        if self.publisher is None or not self.content or not force and now - self.last_progress_at < 0.2:
            return
        self.last_progress_at = now
        progress = {
            "content": "".join(self.content), "thread_id": self.thread_id,
            "model": self.model, "reasoning_effort": self.effort,
            "stage": "model_stream", "token_usage": {"output": self.output_tokens},
        }
        if not self.thread_id:
            progress.pop("thread_id")
        self.publisher.publish(progress)

    def _set_thread_id(self, value):
        if not isinstance(value, str) or not value:
            return
        try:
            self.thread_id = str(uuid.UUID(value))
        except (ValueError, AttributeError):
            return

    def _append(self, text: str):
        if not text:
            return
        if self.first_token_at is None:
            self.first_token_at = time.monotonic()
        self.content.append(text)
        self.output_tokens += max(1, len(text) // 4)
        self._publish()

    def _handle_line(self, line: bytes):
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line.decode("utf-8", errors="replace"))
        except (ValueError, TypeError):
            return
        if not isinstance(event, dict):
            return
        event_type = event.get("event")
        if event_type == "init":
            self.initialized_at = time.monotonic()
            init = event.get("init")
            if isinstance(init, dict):
                self.actual_model = init.get("model") or ""
            self._set_thread_id(event.get("conversation_id") or (init.get("conversation_id") if isinstance(init, dict) else None))
        elif event_type in ("message_delta", "content"):
            self._append(_chat_event_text(event.get("content") or event.get("delta") or event.get("message")))
        elif event_type == "step_update":
            step = event.get("step_update")
            if isinstance(step, dict):
                self._set_thread_id(step.get("conversation_id"))
                if step.get("step_type") == "agent_response":
                    self._append(_chat_event_text(step.get("text_delta")))
        elif event_type == "result":
            result = event.get("result") if isinstance(event.get("result"), dict) else event
            usage = result.get("usage") or result.get("token_usage") or {}
            if isinstance(usage, dict):
                aliases = {"inputTokens": ("inputTokens", "input_tokens", "prompt_tokens"),
                    "outputTokens": ("outputTokens", "output_tokens", "completion_tokens"),
                    "cachedInputTokens": ("cachedInputTokens", "cached_input_tokens", "cache_read_input_tokens", "cache_read_tokens"),
                    "reasoningOutputTokens": ("reasoningOutputTokens", "reasoning_tokens", "thinking_tokens"),
                    "totalTokens": ("totalTokens", "total_tokens")}
                for key, names in aliases.items():
                    value = next((usage[n] for n in names if type(usage.get(n)) is int and usage[n] >= 0), None)
                    if value is not None:
                        self.token_usage[key] = value
            self._set_thread_id(result.get("conversation_id"))
            if not self.content:
                self._append(_chat_event_text(result.get("response") or result.get("content") or result.get("structured_output")))
            self._publish(force=True)
            self.completed_at = time.monotonic()
            self.result_event = result


def run_antigravity_chat(peer: DesktopPeer, job: dict, cli: str, runtime: Path, models: list[str],
                         ledger: sqlite3.Connection, heartbeat, default_model: str = ""):
    started = time.monotonic()
    context = job.get('context') or {}
    job_id = job.get('id') or secrets.token_hex(8)
    prompt = context.get('prompt') or job.get('prompt') or ""
    model = context.get('model') or default_model
    bridge_test = context.get('bridge_test') is True

    ledger.execute('CREATE TABLE IF NOT EXISTS chat_results(id TEXT PRIMARY KEY, result TEXT NOT NULL, created_at REAL, delivered_at REAL)')
    ledger.commit()
    ResultOutbox.prepare(ledger)
    cached = ledger.execute('SELECT result FROM chat_results WHERE id=?', (job_id,)).fetchone()
    if cached:
        result = json.loads(cached[0])
        ResultOutbox.stage(ledger, 'chat_result', job, result)
        _post_chat_result(peer, {"id": job_id, "lease_token": job.get("lease_token", ""),
                                 "status": "completed", "result": result})
        ResultOutbox.acknowledge(ledger, 'chat_result', job)
        with ledger:
            ledger.execute('UPDATE chat_results SET delivered_at=? WHERE id=?', (time.time(), job_id))
        return

    publisher = ProgressPublisher(peer, job, heartbeat)
    result_saved = False
    thread_id = ""
    timings = {"queue_wait_ms": job.get("queue_wait_ms")}
    try:
        model = _select_model(context, models, default_model)
        effort = _resolve_cli_effort(model, context.get("reasoning_effort"), models)
        first_token_ms = None
        token_usage = {}
        if bridge_test:
            thread_id = str(uuid.uuid4())
            final_text = "ANTIGRAVITY_BRIDGE_OK: Antigravity CLI and Gemini model pipeline verified."
            publisher.publish({"thread_id": thread_id, "content": final_text, "model": model,
                "reasoning_effort": effort, "stage": "bridge_test",
                "token_usage": {"input": 10, "output": 15}})
        else:
            timeout = _job_cli_timeout(job)
            cmd = [cli, "--input-format", "stream-json", "--output-format", "stream-json",
                   "--sandbox", "--disable-slash-commands", "--print-timeout", f"{max(1, timeout - 3)}s"]
            if effort != "auto":
                cmd.extend(["--effort", effort])
            if model:
                cmd.extend(["--model", model])
            prompt_event = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
            publisher.publish({"content": "[Antigravity 正在分析...]\n",
                "model": model, "reasoning_effort": effort, "stage": "model_start"})
            stream = _AntigravityChatStream(publisher, job_id, model, effort)
            timings["turn_started_ms"] = round((time.monotonic() - started) * 1000)
            # Frozen research evidence is self-contained. A directory outside the
            # checkout avoids injecting ancestor AGENTS.md and project context.
            with tempfile.TemporaryDirectory(prefix="agv-chat-") as scratch_dir:
                completed = run_bounded_cli(
                    cmd, cwd=scratch_dir, stdin_bytes=prompt_event.encode("utf-8"),
                    timeout_seconds=timeout, timeout_limit_seconds=180.0,
                    completion_predicate=lambda _: stream.result_event is not None,
                    stdout_callback=stream.feed, hidden_console=True,
                )
            stream.finish()
            if stream.actual_model and stream.actual_model != model:
                raise BoundedCLIError("AGY_MODEL_CONFIGURATION_MISMATCH")
            if stream.result_event is None:
                if completed.returncode:
                    raise BoundedCLIError(f"AGY_CLI_EXIT_{abs(completed.returncode)}")
                raise BoundedCLIError("AGY_RESULT_EVENT_MISSING")
            result_status = stream.result_event.get("status")
            if isinstance(result_status, str) and result_status.upper() in {
                "ERROR", "FAILED", "CANCELED", "CANCELLED", "INTERRUPTED", "INVALID",
            }:
                raise _agy_result_failure(stream.result_event)
            final_text = "".join(stream.content).strip()
            if not final_text:
                raise BoundedCLIError("AGY_RESULT_CONTENT_EMPTY")
            if not stream.thread_id:
                raise BoundedCLIError("AGY_CONVERSATION_ID_MISSING")
            thread_id = stream.thread_id
            if stream.first_token_at is not None:
                first_token_ms = round((stream.first_token_at - started) * 1000)
                timings["first_token_ms"] = first_token_ms
            if stream.initialized_at is not None:
                timings["engine_ready_ms"] = round((stream.initialized_at - started) * 1000)
                timings["thread_ready_ms"] = timings["engine_ready_ms"]
                timings["turn_started_ms"] = timings["engine_ready_ms"]
            timings["bridge_to_completed_ms"] = round(((stream.completed_at or time.monotonic()) - started) * 1000)
            token_usage = stream.token_usage
        result_payload = {
            "id": job_id,
            "status": "completed",
            "provider": "antigravity-cli",
            "model": model,
            "reasoning_effort": effort,
            "content": final_text,
            "thread_id": thread_id,
            "token_usage": token_usage,
            "timings": {k: v for k, v in timings.items() if v is not None},
            "completed_at": time.time(),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "first_token_ms": first_token_ms,
        }
        with ledger:
            ledger.execute("INSERT OR REPLACE INTO chat_results(id,result,created_at,delivered_at) VALUES(?, ?, ?, NULL)",
                           (job_id, json.dumps(result_payload, ensure_ascii=False), time.time()))
            ResultOutbox.stage(ledger, 'chat_result', job, result_payload, commit=False)
        result_saved = True
        publisher.close()
        publisher = None
        _post_chat_result(peer, {"id": job_id, "lease_token": job.get("lease_token", ""),
                                 "status": "completed", "result": result_payload})
        with ledger:
            ResultOutbox.acknowledge(ledger, 'chat_result', job, commit=False)
            ledger.execute('UPDATE chat_results SET delivered_at=? WHERE id=?', (time.time(), job_id))
        _emit_log({"status": "completed", "job_id": str(job_id)[:12],
                   "elapsed_ms": result_payload["elapsed_ms"], "timings": result_payload["timings"],
                   "backend_confirmed_ms": round((time.monotonic() - started) * 1000)})
    except Exception as exc:
        if publisher:
            try:
                publisher.close()
            except Exception:
                pass
            publisher = None
        error_code, error_detail = _chat_error_info(exc)
        _emit_log({"status": "degraded", "error_code": error_code, "error_detail": error_detail,
                   "stage": "antigravity_chat_exec", "job_id": str(job_id)[:12],
                   "elapsed_ms": round((time.monotonic() - started) * 1000)})
        if result_saved:
            # The outbox owns delivery retries; never turn a completed inference
            # into a failed job or pay for the same inference again.
            raise
        failure_payload = {
            "id": job_id,
            "status": "failed",
            "provider": "antigravity-cli",
            "error_code": error_code,
            "error_message": error_detail.get("message") or error_code,
            "completed_at": time.time(),
        }
        try:
            _post_chat_result(peer, {"id": job_id, "lease_token": job.get("lease_token", ""),
                                     "status": "failed", "result": failure_payload})
        except Exception:
            pass
        raise
    finally:
        if publisher:
            publisher.close()


def run_antigravity_strategy(peer: DesktopPeer, job: dict, cli: str, runtime: Path, models: list[str],
                             ledger: sqlite3.Connection, heartbeat, default_model: str = ""):
    started = time.monotonic()
    context = job.get('context') or {}
    job_id = job.get('id') or secrets.token_hex(8)
    ledger.execute('CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,result TEXT,created_at REAL)')
    ledger.commit()
    ResultOutbox.prepare(ledger)
    cached = ledger.execute('SELECT result FROM results WHERE id=?', (job_id,)).fetchone()
    if cached:
        result = json.loads(cached[0])
        ResultOutbox.stage(ledger, 'result', job, result)
        peer.post('result', {'id': job_id, 'lease_token': job['lease_token'], 'status': 'completed', 'result': result})
        ResultOutbox.acknowledge(ledger, 'result', job)
        return
    model = _select_model(context, models, default_model)
    effort = _resolve_cli_effort(model, context.get('reasoning_effort'), models)

    scratch_dir = runtime / "strategy-scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    # Deterministic local frozen evidence extraction
    symbols = [s['symbol'] for s in context.get('stocks', [])] if isinstance(context.get('stocks'), list) else []
    evidence = ats_evidence(APP_ROOT, symbols)
    schema = copy.deepcopy(RESPONSE_SCHEMA)
    if symbols:
        schema['properties']['plans']['items']['properties']['symbol']['enum'] = symbols

    schema_file = scratch_dir / "response.schema.json"
    schema_file.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

    prompt = (
        f"【量化标的策略分析】\n"
        f"当前交易日: {context.get('trade_date', '')}\n"
        f"待分析标的: {', '.join(symbols) if symbols else '全市场强势股'}\n"
        f"本地快照证据: {json.dumps(evidence, ensure_ascii=False)[:3000]}\n"
        f"请基于上述只读证据与交易规则，生成符合 JSON Schema 的投资判断与条件预案。严禁编造行情数据。"
    )

    cmd = [
        cli, "--input-format", "stream-json", "--output-format", "stream-json",
        "--json-schema", str(schema_file), "--sandbox", "--disable-slash-commands",
        "--print-timeout", f"{max(1, _job_cli_timeout(job) - 3)}s",
    ]
    if effort != "auto":
        cmd.extend(["--effort", effort])
    if model:
        cmd.extend(["--model", model])

    publisher = ProgressPublisher(peer, job, heartbeat, operation='lease')
    try:
        publisher.publish({"stage": "strategy_model_start", "model": model, "reasoning_effort": effort})
        prompt_event = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
        stream = _AntigravityChatStream(None, job_id, model, effort)
        turn_started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="agv-strategy-") as isolated_dir:
            completed = run_bounded_cli(
                cmd, cwd=isolated_dir, stdin_bytes=prompt_event.encode("utf-8"),
                timeout_seconds=_job_cli_timeout(job), timeout_limit_seconds=180.0,
                completion_predicate=lambda _: stream.result_event is not None,
                stdout_callback=stream.feed, hidden_console=True,
            )
        stream.finish()
        if stream.actual_model and stream.actual_model != model:
            raise BoundedCLIError("AGY_MODEL_CONFIGURATION_MISMATCH")
        publisher.check()
        result_event = stream.result_event
        if not isinstance(result_event, dict):
            if completed.returncode:
                raise BoundedCLIError(f"AGY_CLI_EXIT_{abs(completed.returncode)}")
            raise BoundedCLIError("AGY_RESULT_EVENT_MISSING")
        result_status = result_event.get("status")
        if isinstance(result_status, str) and result_status.upper() not in ("SUCCESS", "COMPLETED"):
            raise _agy_result_failure(result_event)
        result_obj = _coerce_structured_output(result_event)
        if not result_obj or not matches_json_schema(result_obj, schema):
            raise BoundedCLIError("AGY_STRUCTURED_OUTPUT_INVALID")

        result_payload = {
            "proposal": result_obj,
            "thread_id": "strat-" + job_id[:8],
            "provider": "antigravity-cli",
            "model": model,
            "reasoning_effort": effort,
            "configuration_confirmed": True,
            "token_usage": stream.token_usage,
            "timings": {"turn_started_ms": round(((stream.initialized_at or turn_started) - started) * 1000),
                        "bridge_to_completed_ms": round(((stream.completed_at or time.monotonic()) - started) * 1000),
                        **({"first_token_ms": round((stream.first_token_at - started) * 1000)} if stream.first_token_at else {}),
                        **({"queue_wait_ms": job["queue_wait_ms"]} if job.get("queue_wait_ms") is not None else {})},
        }
        with ledger:
            ledger.execute('INSERT OR REPLACE INTO results(id,result,created_at) VALUES(?,?,?)',
                           (job_id, json.dumps(result_payload, ensure_ascii=False), time.time()))
            ResultOutbox.stage(ledger, 'result', job, result_payload, commit=False)
        publisher.close()
        publisher = None
        peer.post("result", {"id": job["id"], "lease_token": job.get("lease_token", ""), "status": "completed", "result": result_payload})
        ResultOutbox.acknowledge(ledger, 'result', job)
        _emit_log({"status": "completed", "job_id": job_id[:12]})
    except Exception as exc:
        if publisher:
            try:
                publisher.close()
            except Exception:
                pass
            publisher = None
        _emit_log({"status": "degraded", "error_code": str(getattr(exc, "code", "") or type(exc).__name__)[:120],
                   "error_detail": _error_details(exc), "stage": "antigravity_strategy_exec", "job_id": str(job_id)[:12]})
        raise
    finally:
        if publisher:
            publisher.close()


def _wait_for_stop(runtime: Path, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if (runtime.parent / "stop.request").is_file():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(1, remaining))


def _run_agent_loop(peer, catalog, runtime, ledger, heartbeat, persist_status, once=False):
    last_ready_heartbeat = 0.0
    peer_error_streak = 0
    unified_queue = True
    while True:
        stage = "stop_check"
        try:
            stop_request = runtime.parent / "stop.request"
            if stop_request.is_file():
                # The peer only accepts ready/analyzing/degraded. Stopping is
                # local state, as in the Codex bridge, and needs no network.
                try:
                    stop_request.unlink()
                except OSError as exc:
                    _emit_log({"status": "stop_request_cleanup_failed", "error_code": type(exc).__name__})
                persist_status("stopped", {"reason": "stop_request"})
                break
            stage = "model_catalog_refresh"
            if not catalog.probe():
                heartbeat("degraded", {"error_code": catalog.catalog_error or "engine_unavailable"})
                if once:
                    break
                _wait_for_stop(runtime, 10)
                continue
            stage = "backend_ready_heartbeat"
            if not last_ready_heartbeat or time.monotonic() - last_ready_heartbeat >= 20:
                heartbeat("ready", {"default_model": catalog.default_model})
                last_ready_heartbeat = time.monotonic()
            job, chat = None, None
            polled_at = time.monotonic()
            if unified_queue:
                stage = "unified_job_wait"
                try:
                    response = peer.post("next", {"wait_ms": 1000 if once else 4000, "prefer_chat": False}, timeout=8)
                    if response.get("kind") == "chat":
                        chat = response.get("job")
                    else:
                        job = response.get("job")
                except HTTPError as exc:
                    if exc.code not in (404, 405):
                        raise
                    unified_queue = False
            if not unified_queue:
                stage = "chat_claim"
                chat = peer.post("chat_claim", {}, timeout=5).get("job")
                if not chat:
                    stage = "strategy_claim"
                    job = peer.post("claim", {}, timeout=5).get("job")
            if chat:
                stage = "chat_run"
                run_antigravity_chat(peer, chat, catalog.engine, runtime, catalog.models, ledger, heartbeat, catalog.default_model)
                last_ready_heartbeat = 0.0
            if job:
                stage = "strategy_run"
                run_antigravity_strategy(peer, job, catalog.engine, runtime, catalog.models, ledger, heartbeat, catalog.default_model)
                last_ready_heartbeat = 0.0
            peer_error_streak = 0
            if once:
                break
            if not chat and not job:
                _wait_for_stop(runtime, max(0, 0.1 - (time.monotonic() - polled_at)))
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, queue.Empty, BoundedCLIError) as exc:
            peer_error_streak = min(peer_error_streak + 1, 5) if isinstance(exc, OSError) else 0
            retry_seconds = min(60, 5 * (2 ** peer_error_streak)) if isinstance(exc, OSError) else 5
            error_code = getattr(exc, "peer_code", "") or getattr(exc, "code", "")
            if not isinstance(error_code, str) or not error_code:
                error_code = _peer_error_code(exc)
            error_detail = {**_error_details(exc), "stage": stage}
            detail = {"error_code": error_code, "stage": stage, "error_detail": error_detail,
                      "retry_after_seconds": retry_seconds}
            # Never report an outage by sending another heartbeat to the same
            # failed backend. Keep the worker, catalog and result outbox alive.
            persist_status("degraded", detail)
            _emit_log({"status": "degraded", **detail})
            last_ready_heartbeat = 0.0
            if once:
                break
            _wait_for_stop(runtime, retry_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--desktop-root', required=True)
    parser.add_argument('--runtime-root', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)

    runtime = Path(os.path.abspath(args.runtime_root))
    runtime.mkdir(parents=True, exist_ok=True)
    peer = DesktopPeer(Path(args.config))
    catalog = AntigravityCatalog()

    ledger = sqlite3.connect(runtime / "agent.db", timeout=5)
    ledger.execute("PRAGMA journal_mode=WAL")
    ledger.execute("CREATE TABLE IF NOT EXISTS runtime(key TEXT PRIMARY KEY, value TEXT)")
    ledger.commit()
    ResultOutbox.prepare(ledger)
    deliveries = ResultOutbox(peer, runtime / "agent.db")
    status_lock = threading.Lock()

    def persist_agent_status(status: str, detail: dict):
        payload = {
            "status": status,
            "at": time.time(),
            "updated_epoch": time.time(),
            "detail": detail,
        }
        try:
            temp_file = runtime / "agent-status.pending"
            with status_lock:
                temp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                os.replace(temp_file, runtime / "agent-status.json")
        except (OSError, TypeError, ValueError) as exc:
            _emit_log({"status": "agent_status_write_failed", "stage": "local_status_write",
                       "error_code": type(exc).__name__, "error_detail": _error_details(exc)})

    desktop_probe = DesktopRuntimeProbe()

    def heartbeat(status: str, detail: dict):
        try:
            desktop = desktop_probe.snapshot()
        except Exception:
            desktop = {"tk_port": 26676, "ats_port": 26670}
        payload = {
            "provider": "antigravity-cli",
            "capabilities": ["strategy_research", "ai_chat_v1", "stock_research_v1"],
            "engine_path": catalog.engine,
            "models": catalog.models,
            "catalog_at": catalog.fetched_at,
            **catalog.status(),
            "desktop_runtime": desktop,
            **detail,
        }
        persist_agent_status(status, payload)
        try:
            peer.post("heartbeat", {"status": status, "detail": payload})
        except (OSError, ValueError) as exc:
            err = _error_details(exc)
            err["stage"] = "backend_heartbeat"
            persist_agent_status(status, {**payload, "heartbeat_error": _peer_error_code(exc), "heartbeat_error_detail": err})
            raise

    try:
        _run_agent_loop(peer, catalog, runtime, ledger, heartbeat, persist_agent_status, args.once)
    finally:
        for component in (desktop_probe, deliveries, ledger):
            try:
                component.close()
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                _emit_log({"status": "degraded", "stage": "worker_shutdown", "error_code": type(exc).__name__})


if __name__ == '__main__':
    main()

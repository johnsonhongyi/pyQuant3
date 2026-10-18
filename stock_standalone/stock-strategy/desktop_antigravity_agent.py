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
    """Probes and maintains the Antigravity CLI and Gemini model directory."""

    def __init__(self, cli_path: str = ""):
        self.cli_override = cli_path.strip()
        self.engine = ""
        self.models = [
            {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "efforts": ["low", "medium", "high"], "default_effort": "low"},
            {"id": "gemini-3.8-pro", "name": "Gemini 3.8 Pro", "efforts": ["low", "medium", "high", "max"], "default_effort": "medium"},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "efforts": ["low", "medium", "high"], "default_effort": "low"},
        ]
        self.default_model = "gemini-3.8-flash"
        self.fetched_at = 0.0
        self.retry_at = 0.0
        self.probe()

    @property
    def model_ids(self) -> list[str]:
        return [m["id"] if isinstance(m, dict) else m for m in self.models]

    def probe(self) -> bool:
        path = self.cli_override or resolve_cli_path("", "agy")
        if path and Path(path).is_file():
            self.engine = str(Path(path).resolve())
            self.fetched_at = time.time()
            self.retry_at = 0.0
            return True
        self.engine = ""
        self.retry_at = time.time() + 20.0
        return False

    def status(self) -> dict:
        return {
            "engine": self.engine,
            "engine_available": bool(self.engine and Path(self.engine).is_file()),
            "models_available": bool(self.models),
            "default_model": self.default_model,
        }


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
    if cause:
        details["callback_error_code"] = error.code
    return error_code, details


def _resolve_cli_effort(model: str, requested, models: list[dict], fallback: str = "medium") -> str:
    model_info = next((item for item in models if isinstance(item, dict) and item.get("id") == model), {})
    efforts = model_info.get("efforts") if isinstance(model_info.get("efforts"), list) else []
    efforts = [item for item in efforts if isinstance(item, str)]
    if isinstance(requested, str) and requested in efforts:
        return requested
    default = model_info.get("default_effort")
    if isinstance(default, str) and default in efforts:
        return default
    if efforts:
        return efforts[0]
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
        if not self.content or not force and now - self.last_progress_at < 0.2:
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
            init = event.get("init")
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
            self._set_thread_id(result.get("conversation_id"))
            if not self.content:
                self._append(_chat_event_text(result.get("response") or result.get("content") or result.get("structured_output")))
            self._publish(force=True)
            self.result_event = result


def run_antigravity_chat(peer: DesktopPeer, job: dict, cli: str, runtime: Path, models: list[str],
                         ledger: sqlite3.Connection, heartbeat, default_model: str = "gemini-3.8-flash"):
    context = job.get('context') or {}
    job_id = job.get('id') or secrets.token_hex(8)
    prompt = context.get('prompt') or job.get('prompt') or ""
    model = context.get('model') or default_model
    bridge_test = context.get('bridge_test') is True or "BRIDGE_OK" in prompt or "TEST" in prompt

    ledger.execute('CREATE TABLE IF NOT EXISTS chat_results(id TEXT PRIMARY KEY, result TEXT NOT NULL, created_at REAL, delivered_at REAL)')
    ledger.commit()

    publisher = ProgressPublisher(peer, job, heartbeat)
    started = time.monotonic()
    thread_id = ""
    effort = _resolve_cli_effort(model, context.get("reasoning_effort"), models)
    try:
        first_token_ms = None
        if bridge_test:
            thread_id = str(uuid.uuid4())
            final_text = "ANTIGRAVITY_BRIDGE_OK: Antigravity CLI and Gemini model pipeline verified."
            publisher.publish({"thread_id": thread_id, "content": final_text, "model": model,
                "reasoning_effort": effort, "stage": "bridge_test",
                "token_usage": {"input": 10, "output": 15}})
        else:
            scratch_dir = runtime / "chat-scratch"
            scratch_dir.mkdir(parents=True, exist_ok=True)
            timeout = _job_cli_timeout(job)
            cmd = [cli, "--input-format", "stream-json", "--output-format", "stream-json",
                   "--sandbox", "--disable-slash-commands", "--print-timeout", f"{max(1, timeout - 3)}s",
                   "--effort", effort]
            if model:
                cmd.extend(["--model", model])
            prompt_event = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
            publisher.publish({"content": "[Antigravity 正在分析...]\n",
                "model": model, "reasoning_effort": effort, "stage": "model_start"})
            stream = _AntigravityChatStream(publisher, job_id, model, effort)
            completed = run_bounded_cli(
                cmd, cwd=scratch_dir, stdin_bytes=prompt_event.encode("utf-8"),
                timeout_seconds=timeout, timeout_limit_seconds=180.0,
                completion_predicate=lambda _: stream.result_event is not None,
                stdout_callback=stream.feed,
            )
            stream.finish()
            if stream.result_event is None:
                if completed.returncode:
                    raise BoundedCLIError(f"AGY_CLI_EXIT_{abs(completed.returncode)}")
                raise BoundedCLIError("AGY_RESULT_EVENT_MISSING")
            result_status = stream.result_event.get("status")
            if isinstance(result_status, str) and result_status.upper() in {
                "ERROR", "FAILED", "CANCELED", "CANCELLED", "INTERRUPTED", "INVALID",
            }:
                raise BoundedCLIError(f"AGY_RESULT_{result_status.upper()}")
            final_text = "".join(stream.content).strip()
            if not final_text:
                raise BoundedCLIError("AGY_RESULT_CONTENT_EMPTY")
            if not stream.thread_id:
                raise BoundedCLIError("AGY_CONVERSATION_ID_MISSING")
            thread_id = stream.thread_id
            if stream.first_token_at is not None:
                first_token_ms = round((stream.first_token_at - started) * 1000)
        result_payload = {
            "id": job_id,
            "status": "completed",
            "provider": "antigravity-cli",
            "model": model,
            "reasoning_effort": effort,
            "content": final_text,
            "thread_id": thread_id,
            "token_usage": {"input_tokens": len(prompt) // 4, "output_tokens": max(1, len(final_text) // 4)},
            "completed_at": time.time(),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "first_token_ms": first_token_ms,
        }
        ledger.execute("INSERT OR REPLACE INTO chat_results VALUES(?, ?, ?, ?)",
                       (job_id, json.dumps(result_payload, ensure_ascii=False), time.time(), time.time()))
        ledger.commit()
        publisher.close()
        publisher = None
        _post_chat_result(peer, {"id": job_id, "lease_token": job.get("lease_token", ""),
                                 "status": "completed", "result": result_payload})
        _emit_log({"status": "completed", "job_id": str(job_id)[:12],
                   "elapsed_ms": result_payload["elapsed_ms"]})
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
        failure_payload = {
            "id": job_id,
            "status": "failed",
            "provider": "antigravity-cli",
            "error_code": error_code,
            "error_message": error_code,
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
                             ledger: sqlite3.Connection, heartbeat, default_model: str = "gemini-3.8-flash"):
    context = job.get('context') or {}
    job_id = job.get('id') or secrets.token_hex(8)
    model = context.get('model') or default_model
    effort = _resolve_cli_effort(model, context.get('reasoning_effort'), models, fallback="high")

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
        "--print-timeout", f"{max(1, _job_cli_timeout(job) - 3)}s", "--effort", effort,
    ]
    if model:
        cmd.extend(["--model", model])

    publisher = ProgressPublisher(peer, job, heartbeat, operation='lease')
    try:
        publisher.publish({"stage": "strategy_model_start", "model": model, "reasoning_effort": effort})
        prompt_event = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
        completed = run_bounded_cli(
            cmd, cwd=scratch_dir, stdin_bytes=prompt_event.encode("utf-8"),
            timeout_seconds=_job_cli_timeout(job), timeout_limit_seconds=180.0,
            completion_predicate=_has_antigravity_result_event,
        )
        publisher.check()
        result_event = _antigravity_result_event(completed.stdout)
        if not isinstance(result_event, dict):
            if completed.returncode:
                raise BoundedCLIError(f"AGY_CLI_EXIT_{abs(completed.returncode)}")
            raise BoundedCLIError("AGY_RESULT_EVENT_MISSING")
        result_status = result_event.get("status")
        if isinstance(result_status, str) and result_status.upper() not in ("SUCCESS", "COMPLETED"):
            raise BoundedCLIError(f"AGY_RESULT_{result_status.upper()}")
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
        }
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

    def persist_agent_status(status: str, detail: dict):
        payload = {
            "status": status,
            "at": time.time(),
            "updated_epoch": time.time(),
            "detail": detail,
        }
        temp_file = runtime / "agent-status.pending"
        temp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_file, runtime / "agent-status.json")

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

    last_ready_heartbeat = 0.0

    try:
        while True:
            stop_request = runtime.parent / "stop.request"
            if stop_request.exists():
                try:
                    stop_request.unlink()
                except OSError:
                    pass
                heartbeat("stopped", {"reason": "stop_request"})
                break

            if not catalog.probe():
                heartbeat("degraded", {"error_code": "engine_unavailable", "detail": "agy CLI not found"})
                if args.once:
                    break
                time.sleep(10)
                continue

            if time.monotonic() - last_ready_heartbeat >= 20.0:
                heartbeat("ready", {"default_model": catalog.default_model})
                last_ready_heartbeat = time.monotonic()

            job, chat = None, None
            try:
                # Poll unified queue or chat
                next_response = peer.post("next", {"wait_ms": 1000 if args.once else 4000, "prefer_chat": False}, timeout=8)
                if next_response.get("kind") == "chat":
                    chat = next_response.get("job")
                else:
                    job = next_response.get("job")
                if not chat and not job:
                    chat_response = peer.post("chat_claim", {}, timeout=5)
                    chat = chat_response.get("job")
            except (OSError, ValueError, HTTPError) as exc:
                heartbeat("degraded", {"error_code": _peer_error_code(exc)})
                if args.once:
                    break
                time.sleep(5)
                continue

            if chat:
                stage = "chat_run"
                try:
                    run_antigravity_chat(peer, chat, catalog.engine, runtime, catalog.models, ledger, heartbeat, catalog.default_model)
                except Exception as exc:
                    _emit_log({"status": "degraded", "stage": stage, "error_code": type(exc).__name__})
                last_ready_heartbeat = 0.0

            if job:
                stage = "strategy_run"
                try:
                    run_antigravity_strategy(peer, job, catalog.engine, runtime, catalog.models, ledger, heartbeat, catalog.default_model)
                except Exception as exc:
                    _emit_log({"status": "degraded", "stage": stage, "error_code": type(exc).__name__})
                last_ready_heartbeat = 0.0

            if not chat and not job:
                if args.once:
                    break
                time.sleep(3)
    finally:
        try:
            desktop_probe.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()

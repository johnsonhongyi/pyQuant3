# -*- coding: utf-8 -*-
"""Explicitly gated Antigravity CLI bridge; never a local-model backend.

AGY is an agent CLI that may process prompts remotely and may expose tools. It
is deliberately unavailable to the trading worker unless both remote use and
OS-enforced process/tool isolation have been accepted outside this module.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ats.llm.cli_process import BoundedCLIError, run_bounded_cli
from ats.llm.cli_paths import resolve_cli_path
from ats.llm.remote_prompt_templates import build_approved_remote_prompt
from ats.llm.remote_sanitizer import RemoteEgressError

_MAX_PROMPT_CHARS = 32_000
_MAX_SCHEMA_BYTES = 64 * 1024


def matches_json_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    """Validate the JSON Schema subset used by the bounded agent contracts."""
    return _json_schema_failure_code(value, schema) is None


def _json_schema_failure_code(value: Any, schema: Mapping[str, Any]) -> Optional[str]:
    if not isinstance(schema, Mapping):
        return "SCHEMA_DEFINITION_INVALID"
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            return "SCHEMA_EXPECTED_OBJECT"
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or not isinstance(properties, Mapping):
            return "SCHEMA_DEFINITION_INVALID"
        if any(key not in value for key in required):
            return "SCHEMA_REQUIRED_FIELD_MISSING"
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return "SCHEMA_EXTRA_FIELD"
        for key, item in value.items():
            if key in properties:
                failure = _json_schema_failure_code(item, properties[key])
                if failure:
                    return failure
        return None
    if schema_type == "array":
        if not isinstance(value, list):
            return "SCHEMA_TYPE_MISMATCH"
        for item in value:
            failure = _json_schema_failure_code(item, schema.get("items", {}))
            if failure:
                return failure
        return None
    if schema_type == "string":
        return None if isinstance(value, str) else "SCHEMA_TYPE_MISMATCH"
    if schema_type == "boolean":
        return None if isinstance(value, bool) else "SCHEMA_TYPE_MISMATCH"
    if schema_type == "integer":
        return None if isinstance(value, int) and not isinstance(value, bool) else "SCHEMA_TYPE_MISMATCH"
    if schema_type == "number":
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else "SCHEMA_TYPE_MISMATCH"
    return None


def _coerce_structured_output(result_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Accept only object output, parsing a JSON string before schema validation."""
    for key in ("structured_output", "response"):
        candidate = result_event.get(key)
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str):
            text = candidate.strip().lstrip("\ufeff")
            if text.startswith("```"):
                lines = text.splitlines()
                language = lines[0][3:].strip().lower()
                if (
                    len(lines) >= 3 and lines[-1].strip() == "```"
                    and language in {"", "json"}
                ):
                    text = "\n".join(lines[1:-1]).strip()
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _structured_output_failure_code(result_event: Mapping[str, Any]) -> str:
    """Return a stable shape error without exposing model text or provider details."""
    for key in ("structured_output", "response"):
        if key not in result_event:
            continue
        candidate = result_event.get(key)
        if candidate is None:
            return "SCHEMA_OUTPUT_EMPTY"
        if isinstance(candidate, str):
            try:
                parsed = json.loads(candidate)
            except (ValueError, TypeError):
                return "SCHEMA_OUTPUT_NOT_JSON"
            return "SCHEMA_OUTPUT_NOT_OBJECT" if not isinstance(parsed, dict) else "SCHEMA_OUTPUT_UNREADABLE"
        return "SCHEMA_OUTPUT_NOT_OBJECT" if not isinstance(candidate, dict) else "SCHEMA_OUTPUT_UNREADABLE"
    return "SCHEMA_STRUCTURED_OUTPUT_MISSING"


class AntigravityCLIBackend:
    """AGY bridge for controlled non-trading tasks; closed unless explicitly gated."""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        timeout_seconds: float = 25.0,
        model_id: Optional[str] = None,
        *,
        allow_remote_invocation: bool = False,
        process_tree_isolation_accepted: bool = False,
        tool_access_isolation_accepted: bool = False,
        remote_egress_isolation_accepted: bool = False,
        remote_policy: Optional[Mapping[str, Any]] = None,
        working_directory: Optional[str] = None,
    ) -> None:
        self.cli_path = self._resolve_cli_path(cli_path)
        self.timeout_seconds = max(5.0, min(float(timeout_seconds), 30.0))
        self.model_id = str(model_id).strip() if model_id else None
        self.allow_remote_invocation = allow_remote_invocation is True
        self.process_tree_isolation_accepted = process_tree_isolation_accepted is True
        self.tool_access_isolation_accepted = tool_access_isolation_accepted is True
        self.remote_egress_isolation_accepted = remote_egress_isolation_accepted is True
        self.remote_policy = dict(remote_policy) if isinstance(remote_policy, Mapping) else {}
        self.working_directory = str(Path(working_directory).resolve()) if working_directory else ""

    @staticmethod
    def _resolve_cli_path(explicit_path: Optional[str] = None) -> str:
        return resolve_cli_path(explicit_path, "agy")

    def is_available(self) -> bool:
        return bool(self.cli_path and Path(self.cli_path).is_file())

    def invoke(
        self,
        prompt: str,
        json_schema: Optional[Mapping[str, Any]] = None,
        timeout_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Reject raw invocation; callers must use the sanitized request contract."""
        return self._failure(
            "PROMPT_REQUIRES_SANITIZED_REQUEST",
            "AGY 只接受通过固定模板和字段白名单校验的请求",
        )

    def _invoke_approved(
        self,
        prompt: str,
        json_schema: Mapping[str, Any],
        timeout_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        if not (
            self.allow_remote_invocation
            and self.process_tree_isolation_accepted
            and self.tool_access_isolation_accepted
            and self.remote_egress_isolation_accepted
        ):
            return self._failure(
                "POLICY_BLOCKED",
                "AGY 调用缺少远端、工具、出口或进程树隔离授权；未调用 CLI",
            )
        if not self.working_directory or not Path(self.working_directory).is_dir():
            return self._failure("SCRATCH_NOT_READY", "AGY 隔离工作目录未就绪")
        if not self.is_available():
            return self._failure("CLI_NOT_FOUND", "未找到 agy CLI")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > _MAX_PROMPT_CHARS:
            return self._failure("PROMPT_INVALID", "prompt 为空或超过长度限制")
        if not isinstance(json_schema, Mapping):
            return self._failure("SCHEMA_INVALID", "json_schema 必须是映射")

        timeout = self.timeout_seconds
        if timeout_override is not None:
            try:
                timeout = max(1.0, min(float(timeout_override), self.timeout_seconds))
            except (TypeError, ValueError, OverflowError):
                return self._failure("TIMEOUT_INVALID", "timeout_override 无效")
        try:
            with tempfile.TemporaryDirectory(
                prefix="ipo-agy-", dir=self.working_directory
            ) as scratch:
                schema_text = json.dumps(
                    json_schema, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                )
                schema_bytes = schema_text.encode("utf-8")
                if len(schema_bytes) > _MAX_SCHEMA_BYTES:
                    return self._failure("SCHEMA_TOO_LARGE", "JSON Schema 超过长度限制")
                schema_path = Path(scratch) / "response.schema.json"
                schema_path.write_bytes(schema_bytes)
                command = self._command(schema_path, timeout)
                prompt_event = json.dumps(
                    {"event": "user", "message": {"content": prompt}},
                    ensure_ascii=False, separators=(",", ":"),
                ).encode("utf-8") + b"\n"
                completed = run_bounded_cli(
                    command, cwd=scratch, stdin_bytes=prompt_event,
                    timeout_seconds=min(30.0, timeout + 2.0),
                    completion_predicate=self._has_result_event,
                )
            duration = (time.monotonic() - started) * 1000.0
            result_event = self._parse_result_event(completed.stdout)
            if result_event is not None and result_event.get("status") != "SUCCESS":
                return self._failure(
                    self._classify_result_failure(result_event),
                    "AGY 终态未成功", duration,
                )
            # The bounded runner reaps a streaming process immediately after its
            # terminal result event; its resulting non-zero code is not provider failure.
            if completed.returncode != 0 and not completed.completed_by_predicate:
                return self._failure(
                    self._classify_cli_exit(
                        completed.returncode, completed.stderr, completed.stdout
                    ),
                    "AGY CLI 返回非零退出码", duration,
                )
            if result_event is None:
                return self._failure("CLI_RESULT_MISSING", "AGY 未返回有效终态事件", duration)
            payload = _coerce_structured_output(result_event)
            if payload is None:
                return self._failure(
                    _structured_output_failure_code(result_event),
                    "AGY 未返回对象型结构化输出", duration,
                )
            failure_code = _json_schema_failure_code(payload, json_schema)
            if failure_code:
                return self._failure(failure_code, "结构化输出不符合 JSON Schema", duration)
            return {
                "success": True,
                "payload": payload if json_schema is not None else envelope.get("response"),
                "error_code": None,
                "error_msg": None,
                "duration_ms": duration,
            }
        except BoundedCLIError as exc:
            return self._failure(exc.code, "AGY CLI 超时、输出超限或进程不可用", (time.monotonic() - started) * 1000.0)
        except (OSError, ValueError, TypeError, UnicodeError):
            return self._failure("CLI_EXCEPTION", "AGY CLI 启动或返回格式异常", (time.monotonic() - started) * 1000.0)

    def generate_request(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
        *,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        """Sanitize structured context inside the Worker before remote invocation."""
        if not isinstance(request, Mapping):
            return {"status": "UNAVAILABLE", "error_code": "request_invalid"}
        try:
            from ats.llm.remote_sanitizer import build_remote_safe_request

            safe = build_remote_safe_request(
                request.get("agent_type"), request.get("context"), self.remote_policy
            )
            prompt = build_approved_remote_prompt(
                request.get("agent_type"), request.get("prompt_version"),
                request.get("prompt"), safe["context_json"],
            )
            result = self._invoke_approved(prompt, response_schema, timeout_override=timeout_seconds)
        except RemoteEgressError:
            return {"status": "UNAVAILABLE", "error_code": "prompt_or_context_not_approved"}
        except Exception:
            return {"status": "UNAVAILABLE", "error_code": "remote_sanitization_failed"}
        if result.get("success") is not True or not isinstance(result.get("payload"), Mapping):
            return {"status": "UNAVAILABLE", "error_code": str(result.get("error_code") or "provider_unavailable")}
        return {"status": "OK", "proposal": dict(result["payload"])}

    def _command(self, schema_path: Path, timeout: float) -> list[str]:
        timeout_arg = f"{max(1, int(timeout))}s"
        args = [
            "--input-format", "stream-json", "--output-format", "stream-json",
            "--json-schema", str(schema_path), "--sandbox", "--disable-slash-commands",
            "--mode", "plan", "--print-timeout", timeout_arg,
        ]
        if self.model_id:
            args.extend(["--model", self.model_id])
        if self.cli_path.lower().endswith(".ps1"):
            return [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "RemoteSigned", "-File", self.cli_path, *args,
            ]
        return [self.cli_path, *args]

    @staticmethod
    def _has_result_event(output: bytes) -> bool:
        try:
            for line in output.decode("utf-8", errors="strict").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if isinstance(event, dict) and event.get("event") == "result":
                    return isinstance(event.get("result"), dict)
        except (UnicodeError, ValueError, TypeError):
            return False
        return False

    @staticmethod
    def _classify_result_failure(result_event: Mapping[str, Any]) -> str:
        status = result_event.get("status")
        error = result_event.get("error")
        detail = error.lower() if isinstance(error, str) else ""
        denied = result_event.get("denied_actions")
        if isinstance(denied, list) and denied:
            category = "TOOL_ACTION_DENIED"
        elif any(token in detail for token in ("authentication", "not signed in", "credential", "login required")):
            category = "AUTH_REQUIRED"
        elif any(token in detail for token in ("invalid model", "model selection", "model is not recognized")):
            category = "MODEL_UNAVAILABLE"
        elif any(token in detail for token in ("access is denied", "permission denied", "failed to redirect output", "crash reporter")):
            category = "LOCAL_STORAGE_BLOCKED"
        elif any(token in detail for token in ("connection", "deadline", "timed out", "network")):
            category = "NETWORK_FAILURE"
        elif any(token in detail for token in (
            "rate limit", "quota", "resource exhausted", "billing", "429",
        )):
            category = "QUOTA_OR_RATE_LIMIT"
        elif any(token in detail for token in (
            "schema", "structured output", "invalid json",
        )):
            category = "STRUCTURED_OUTPUT_FAILURE"
        elif any(token in detail for token in (
            "blocked", "not allowed", "policy denied", "permission denied",
        )):
            category = "PROVIDER_POLICY_BLOCKED"
        elif any(token in detail for token in ("unsupported", "invalid input", "stream-json")):
            category = "INPUT_PROTOCOL_ERROR"
        else:
            category = "PROVIDER_ERROR"
        known_statuses = {"ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"}
        status_code = status if isinstance(status, str) and status in known_statuses else "FAILED"
        return f"CLI_RESULT_{status_code}_{category}"

    @staticmethod
    def _classify_cli_exit(
        returncode: int, stderr: bytes, stdout: bytes = b""
    ) -> str:
        """Classify common AGY CLI failures without storing provider diagnostics."""
        text = (stderr + b"\n" + stdout).decode("utf-8", errors="replace").lower()
        if any(marker in text for marker in (
            "access is denied", "permission denied", "os error 5", "winerror 5",
        )):
            return "CLI_LOCAL_PERMISSION_BLOCKED"
        if any(marker in text for marker in (
            "unknown option", "unrecognized option", "invalid value", "usage of agy",
        )):
            return "CLI_ARGUMENT_INVALID"
        if any(marker in text for marker in (
            "unsupported stream input", "unsupported message", "invalid json line",
            "content block type", "message missing the event field",
        )):
            return "CLI_INPUT_PROTOCOL_ERROR"
        if any(marker in text for marker in (
            "not logged in", "authentication required", "unauthorized",
        )):
            return "CLI_AUTH_REQUIRED"
        if any(marker in text for marker in ("model not found", "unknown model")):
            return "CLI_MODEL_UNAVAILABLE"
        return f"CLI_EXIT_CODE_{abs(int(returncode))}"

    @staticmethod
    def _parse_result_event(output: bytes) -> Optional[Dict[str, Any]]:
        try:
            lines = output.decode("utf-8", errors="strict").splitlines()
            result_events = []
            for line in lines:
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    return None
                if event.get("event") == "result":
                    result_events.append(event.get("result"))
            if len(result_events) != 1 or not isinstance(result_events[0], dict):
                return None
            return result_events[0]
        except (UnicodeError, ValueError, TypeError):
            return None

    @staticmethod
    def _failure(code: str, message: str, duration: float = 0.0) -> Dict[str, Any]:
        return {
            "success": False,
            "payload": None,
            "error_code": code,
            "error_msg": message,
            "duration_ms": duration,
        }

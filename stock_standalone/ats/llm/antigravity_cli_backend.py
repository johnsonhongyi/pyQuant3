# -*- coding: utf-8 -*-
"""Explicitly gated Antigravity CLI bridge; never a local-model backend.

AGY is an agent CLI that may process prompts remotely and may expose tools. It
is deliberately unavailable to the trading worker unless both remote use and
OS-enforced process/tool isolation have been accepted outside this module.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ats.llm.cli_paths import resolve_cli_path

_MAX_PROMPT_CHARS = 32_000


def matches_json_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    """Validate the JSON Schema subset used by the bounded agent contracts."""
    if not isinstance(schema, Mapping):
        return False
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or not isinstance(properties, Mapping):
            return False
        if any(key not in value for key in required):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        return all(
            key not in properties or matches_json_schema(item, properties[key])
            for key, item in value.items()
        )
    if schema_type == "array":
        return isinstance(value, list) and all(
            matches_json_schema(item, schema.get("items", {})) for item in value
        )
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


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
        if json_schema is not None and not isinstance(json_schema, Mapping):
            return self._failure("SCHEMA_INVALID", "json_schema 必须是映射")

        timeout = self.timeout_seconds
        if timeout_override is not None:
            try:
                timeout = max(1.0, min(float(timeout_override), self.timeout_seconds))
            except (TypeError, ValueError, OverflowError):
                return self._failure("TIMEOUT_INVALID", "timeout_override 无效")
        command = self._command(prompt, json_schema, timeout)
        try:
            with tempfile.TemporaryDirectory(
                prefix="ipo-agy-", dir=self.working_directory
            ) as scratch:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout + 2.0,
                    check=False,
                    shell=False,
                    cwd=scratch,
                )
            duration = (time.monotonic() - started) * 1000.0
            try:
                envelope = json.loads(completed.stdout)
            except (TypeError, ValueError):
                return self._failure("JSON_DECODE_ERROR", "AGY 未返回 JSON envelope", duration)
            if completed.returncode != 0 or not isinstance(envelope, dict) or envelope.get("status") != "SUCCESS":
                return self._failure("CLI_FAILED", "AGY 调用未成功", duration)
            payload = envelope.get("structured_output")
            if json_schema is not None and (
                not isinstance(payload, dict) or not matches_json_schema(payload, json_schema)
            ):
                return self._failure("SCHEMA_VALIDATION_FAILED", "结构化输出不符合 JSON Schema", duration)
            return {
                "success": True,
                "payload": payload if json_schema is not None else envelope.get("response"),
                "error_code": None,
                "error_msg": None,
                "duration_ms": duration,
            }
        except subprocess.TimeoutExpired:
            return self._failure("CLI_TIMEOUT", "AGY 调用超过硬截止", (time.monotonic() - started) * 1000.0)
        except (OSError, ValueError, TypeError):
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
                str(request.get("agent_type", "")), request.get("context"), self.remote_policy
            )
            prompt = (
                str(request.get("prompt", ""))
                + "\n\n仅使用本次获准投影的上下文(JSON)：\n"
                + safe["context_json"]
            )
            result = self.invoke(prompt, response_schema, timeout_override=timeout_seconds)
        except Exception:
            return {"status": "UNAVAILABLE", "error_code": "remote_sanitization_failed"}
        if result.get("success") is not True or not isinstance(result.get("payload"), Mapping):
            return {"status": "UNAVAILABLE", "error_code": str(result.get("error_code") or "provider_unavailable")}
        return {"status": "OK", "proposal": dict(result["payload"])}

    def _command(
        self, prompt: str, schema: Optional[Mapping[str, Any]], timeout: float
    ) -> list[str]:
        timeout_arg = f"{max(1, int(timeout))}s"
        args = [
            "-p", prompt, "--output-format", "json", "--sandbox",
            "--disable-slash-commands", "--mode", "plan", "--print-timeout", timeout_arg,
        ]
        if schema is not None:
            args.extend(["--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":"))])
        if self.model_id:
            args.extend(["--model", self.model_id])
        if self.cli_path.lower().endswith(".ps1"):
            return [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "RemoteSigned", "-File", self.cli_path, *args,
            ]
        return [self.cli_path, *args]

    @staticmethod
    def _failure(code: str, message: str, duration: float = 0.0) -> Dict[str, Any]:
        return {
            "success": False,
            "payload": None,
            "error_code": code,
            "error_msg": message,
            "duration_ms": duration,
        }

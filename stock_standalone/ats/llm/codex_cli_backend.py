# -*- coding: utf-8 -*-
"""Fail-closed Codex CLI adapter for allowlisted, read-only Agent requests."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from ats.llm.antigravity_cli_backend import matches_json_schema
from ats.llm.cli_process import BoundedCLIError, run_bounded_cli
from ats.llm.remote_prompt_templates import build_approved_remote_prompt
from ats.llm.remote_sanitizer import RemoteEgressError


class CodexCLIBackend:
    """Run one structured Codex CLI request from an isolated scratch directory."""

    def __init__(
        self,
        cli_path: str,
        model_id: str,
        working_directory: str,
        remote_policy: Mapping[str, Any],
        *,
        allow_remote_invocation: bool = False,
        process_tree_isolation_accepted: bool = False,
        tool_access_isolation_accepted: bool = False,
        remote_egress_isolation_accepted: bool = False,
    ) -> None:
        self.cli_path = cli_path
        self.model_id = model_id
        self.working_directory = str(Path(working_directory).resolve())
        self.remote_policy = dict(remote_policy)
        self._allow_remote = allow_remote_invocation is True
        self._process_isolation = process_tree_isolation_accepted is True
        self._tool_isolation = tool_access_isolation_accepted is True
        self._egress_isolation = remote_egress_isolation_accepted is True

    def is_available(self) -> bool:
        return Path(self.cli_path).is_file() or bool(shutil.which(self.cli_path))

    def generate_request(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
        *,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        if not (
            self._allow_remote and self._process_isolation
            and self._tool_isolation and self._egress_isolation
        ):
            return self._failure("POLICY_BLOCKED")
        if (
            not isinstance(request, Mapping) or not isinstance(response_schema, Mapping)
            or not Path(self.working_directory).is_dir() or not self.is_available()
            or isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= 30.0
        ):
            return self._failure("CLI_NOT_READY")
        try:
            from ats.llm.remote_sanitizer import build_remote_safe_request

            agent_type = request.get("agent_type")
            safe = build_remote_safe_request(
                agent_type, request.get("context"), self.remote_policy
            )
            prompt = build_approved_remote_prompt(
                agent_type, request.get("prompt_version"), request.get("prompt"),
                safe["context_json"],
            )
            prompt_bytes = prompt.encode("utf-8")
            if len(prompt_bytes) > 48 * 1024:
                return self._failure("PROMPT_TOO_LARGE")
            schema = json.dumps(
                response_schema, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            )
            with tempfile.TemporaryDirectory(
                prefix="ipo-codex-", dir=self.working_directory
            ) as temporary:
                schema_path = Path(temporary) / "response.schema.json"
                schema_path.write_text(schema, encoding="utf-8")
                command = [
                    self.cli_path, "exec", "--ephemeral", "--ignore-user-config",
                    "--sandbox", "read-only", "--skip-git-repo-check",
                    "--color", "never", "--cd", temporary,
                    "--output-schema", str(schema_path),
                ]
                if self.model_id:
                    command.extend(["--model", self.model_id])
                command.append("-")
                completed = run_bounded_cli(
                    command, cwd=temporary, stdin_bytes=prompt_bytes,
                    timeout_seconds=float(timeout_seconds),
                )
            if completed.returncode != 0:
                return self._failure(
                    self._classify_cli_exit(completed.returncode, completed.stderr)
                )
            try:
                proposal = json.loads(completed.stdout.decode("utf-8", errors="strict").strip())
            except (UnicodeError, ValueError, TypeError):
                return self._failure("CLI_OUTPUT_INVALID")
            if not isinstance(proposal, dict) or not matches_json_schema(proposal, response_schema):
                return self._failure("SCHEMA_VALIDATION_FAILED")
            return {"status": "OK", "proposal": proposal}
        except RemoteEgressError:
            return self._failure("PROMPT_OR_CONTEXT_NOT_APPROVED")
        except BoundedCLIError as exc:
            return self._failure(exc.code)
        except Exception:
            return self._failure("CLI_EXCEPTION")

    @staticmethod
    def _failure(code: str) -> Dict[str, Any]:
        return {"status": "UNAVAILABLE", "error_code": code}

    @staticmethod
    def _classify_cli_exit(returncode: int, stderr: bytes) -> str:
        """Map common local CLI failures to stable codes without retaining diagnostics."""
        text = stderr.decode("utf-8", errors="replace").lower()
        if any(marker in text for marker in (
            "access is denied", "permission denied", "os error 5", "winerror 5",
        )):
            return "CLI_LOCAL_PERMISSION_BLOCKED"
        if any(marker in text for marker in (
            "not logged in", "authentication required", "unauthorized",
        )):
            return "CLI_AUTH_REQUIRED"
        if any(marker in text for marker in ("model not found", "unknown model")):
            return "CLI_MODEL_UNAVAILABLE"
        return f"CLI_EXIT_CODE_{abs(int(returncode))}"

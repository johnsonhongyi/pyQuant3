# -*- coding: utf-8 -*-
"""Strict provider configuration factory; unknown or remote modes fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Mapping

from ats.llm.antigravity_litert_backend import LiteRTBackendFactory
from ats.llm.cli_paths import resolve_cli_path


_MAX_CONFIG_BYTES = 128 * 1024
_REMOTE_AUTHORIZATION_KEYS = {
    "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
    "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
    "acceptance_id",
}


@dataclass(frozen=True)
class RemoteCLIBackendFactory:
    """Picklable Worker factory; remote calls require five explicit R9 acceptances."""

    provider_name: str
    cli_path: str
    model_id: str
    working_directory: str
    remote_policy: Mapping[str, Any]

    def __call__(self) -> Any:
        options = {
            "allow_remote_invocation": True,
            "process_tree_isolation_accepted": True,
            "tool_access_isolation_accepted": True,
            "remote_egress_isolation_accepted": True,
        }
        if self.provider_name == "antigravity_cli":
            from ats.llm.antigravity_cli_backend import AntigravityCLIBackend

            backend = AntigravityCLIBackend(
                cli_path=self.cli_path, model_id=self.model_id,
                remote_policy=self.remote_policy,
                working_directory=self.working_directory, **options,
            )
            backend.provider_id = self.provider_name
            return backend
        if self.provider_name == "codex_cli":
            from ats.llm.codex_cli_backend import CodexCLIBackend

            backend = CodexCLIBackend(
                cli_path=self.cli_path, model_id=self.model_id,
                working_directory=self.working_directory,
                remote_policy=self.remote_policy, **options,
            )
            backend.provider_id = self.provider_name
            return backend
        raise ValueError("unsupported remote CLI Provider")


@dataclass(frozen=True)
class RemoteCLIFailoverBackendFactory:
    """Create an explicitly configured two-provider chain inside the Worker."""

    primary: RemoteCLIBackendFactory
    fallback: RemoteCLIBackendFactory

    def __call__(self) -> Any:
        return _RemoteCLIFailoverBackend((self.primary(), self.fallback()))


class _RemoteCLIFailoverBackend:
    """Retry provider failures within one Worker deadline and retain route identity."""

    _NON_RETRYABLE = frozenset({
        "POLICY_BLOCKED", "PROMPT_INVALID", "PROMPT_TOO_LARGE", "PROMPT_REQUIRES_SANITIZED_REQUEST",
        "SCHEMA_INVALID", "SCHEMA_DEFINITION_INVALID", "SCHEMA_TOO_LARGE",
        "CLI_ARGUMENT_INVALID", "CLI_INPUT_PROTOCOL_ERROR", "CLI_LOCAL_PERMISSION_BLOCKED",
        "PROMPT_OR_CONTEXT_NOT_APPROVED", "prompt_or_context_not_approved",
        "remote_sanitization_failed", "provider_output_invalid",
    })

    def __init__(self, backends: tuple[Any, ...]) -> None:
        if len(backends) != 2:
            raise ValueError("remote failover requires exactly two configured providers")
        self._backends = backends
        self.provider_id = str(getattr(backends[0], "provider_id", ""))
        self.model_id = str(getattr(backends[0], "model_id", ""))

    def generate_request(
        self, request: Mapping[str, Any], response_schema: Mapping[str, Any], *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        try:
            budget = min(60.0, max(1.0, float(timeout_seconds)))
        except (TypeError, ValueError, OverflowError):
            return {"status": "UNAVAILABLE", "error_code": "FAILOVER_TIMEOUT_INVALID"}
        deadline = time.monotonic() + budget
        previous_error = ""
        last_result: dict[str, Any] = {
            "status": "UNAVAILABLE", "error_code": "provider_unavailable",
        }
        for index, backend in enumerate(self._backends):
            remaining = deadline - time.monotonic()
            if remaining < 5.0:
                last_result = {"status": "UNAVAILABLE", "error_code": "FAILOVER_BUDGET_EXHAUSTED"}
                break
            # Reserve the CLI runner's two-second process-reap margin. Split the
            # remaining budget between providers so a slow primary cannot starve fallback.
            attempt_timeout = (remaining - 2.0) / 2.0 if index == 0 else remaining - 2.0
            result = backend.generate_request(
                request, response_schema,
                timeout_seconds=max(1.0, min(30.0, attempt_timeout)),
            )
            if isinstance(result, Mapping) and result.get("status") == "OK":
                try:
                    from ats.llm.agent_contracts import validate_payload

                    validate_payload(
                        request.get("agent_type"), result.get("proposal"), {
                            "evidence_ids": request.get("evidence_ids"),
                            "as_of_time": request.get("as_of_time"),
                            "generated_at": datetime.now(timezone.utc).isoformat(
                                timespec="milliseconds"
                            ),
                        },
                    )
                except (ValueError, TypeError, KeyError, OverflowError):
                    last_result = {
                        "status": "UNAVAILABLE", "error_code": "AGENT_CONTRACT_INVALID",
                    }
                    if index == 1:
                        self.provider_id = str(getattr(backend, "provider_id", ""))
                        self.model_id = str(getattr(backend, "model_id", ""))
                        break
                    previous_error = "AGENT_CONTRACT_INVALID"
                    continue
                self.provider_id = str(getattr(backend, "provider_id", ""))
                self.model_id = str(getattr(backend, "model_id", ""))
                return {
                    **dict(result), "provider_id": self.provider_id,
                    "model_id": self.model_id,
                    "fallback_error_code": previous_error,
                }
            last_result = dict(result) if isinstance(result, Mapping) else {
                "status": "UNAVAILABLE", "error_code": "provider_unavailable",
            }
            error_code = last_result.get("error_code")
            if not isinstance(error_code, str):
                error_code = "provider_unavailable"
            if index == 1 or error_code in self._NON_RETRYABLE:
                self.provider_id = str(getattr(backend, "provider_id", ""))
                self.model_id = str(getattr(backend, "model_id", ""))
                break
            if error_code.startswith("CLI_RESULT_") and any(
                marker in error_code for marker in (
                    "TOOL_ACTION_DENIED", "PROVIDER_POLICY_BLOCKED",
                    "LOCAL_STORAGE_BLOCKED", "INPUT_PROTOCOL_ERROR",
                )
            ):
                self.provider_id = str(getattr(backend, "provider_id", ""))
                self.model_id = str(getattr(backend, "model_id", ""))
                break
            previous_error = error_code[:120]
        return {
            **last_result,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "fallback_error_code": previous_error,
        }

    def close(self) -> None:
        for backend in self._backends:
            close_backend = getattr(backend, "close", None)
            if callable(close_backend):
                close_backend()


def _build_remote_cli_factory(
    backend_name: str, settings: Mapping[str, Any], backends: Mapping[str, Any],
    config_path: Path, authorization: Mapping[str, Any] | None,
) -> RemoteCLIBackendFactory:
    if not isinstance(backend_name, str) or backend_name not in {"antigravity_cli", "codex_cli"}:
        raise ValueError("fallback must be an explicitly supported remote CLI Provider")
    backend = backends.get(backend_name)
    if settings.get("allow_remote") is not True or not isinstance(backend, Mapping):
        raise ValueError("remote CLI Provider is disabled")
    if backend.get("enabled") is not True:
        raise ValueError("remote CLI Provider must be explicitly enabled")
    if (
        not isinstance(authorization, Mapping)
        or set(authorization) != _REMOTE_AUTHORIZATION_KEYS
        or any(authorization.get(key) is not True for key in (
            "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
            "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
        ))
        or not isinstance(authorization.get("acceptance_id"), str)
        or not authorization.get("acceptance_id", "").strip()
    ):
        raise ValueError("remote Provider, process, tool, and egress acceptance is required")
    model_id = backend.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 160:
        raise ValueError("a fixed Provider model_id is required")
    cli_setting = backend.get("cli_path" if backend_name == "antigravity_cli" else "bin_path")
    cli_name = "agy" if backend_name == "antigravity_cli" else "codex"
    cli_path = resolve_cli_path(cli_setting, cli_name)
    if not cli_path:
        raise ValueError("configured CLI executable is unavailable")
    scratch = backend.get("scratch_cwd")
    if not isinstance(scratch, str) or not scratch.strip():
        raise ValueError("an isolated CLI scratch_cwd is required")
    scratch_path = Path(scratch).expanduser()
    if not scratch_path.is_absolute():
        scratch_path = config_path.parent.parent / scratch_path
    if not scratch_path.is_dir():
        raise ValueError("isolated CLI scratch_cwd must already exist")
    approval = settings.get("remote_egress")
    if not isinstance(approval, Mapping):
        raise ValueError("remote egress approval policy is missing")
    if authorization.get("acceptance_id", "").strip() != approval.get("approval_id"):
        raise ValueError("runtime acceptance_id must match the remote approval_id")
    from ats.llm.remote_sanitizer import validate_remote_policy

    policy = dict(approval)
    if set(policy) != {"approval_id", "destination", "policy_version", "field_allowlist_by_agent"}:
        raise ValueError("remote egress approval policy fields are invalid")
    validate_remote_policy(policy)
    return RemoteCLIBackendFactory(
        provider_name=backend_name, cli_path=cli_path,
        model_id=model_id.strip(), working_directory=str(scratch_path.resolve()),
        remote_policy=policy,
    )


def build_backend_factory(
    config_path: str | Path,
    authorization: Mapping[str, Any] | None = None,
) -> Any:
    """Build the selected local Provider or explicitly accepted CLI adapter."""
    path = Path(config_path)
    if not path.is_file() or path.stat().st_size > _MAX_CONFIG_BYTES:
        raise ValueError("LLM config is missing or exceeds the size limit")
    try:
        import yaml

        with path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
    except (ImportError, OSError, UnicodeError, ValueError) as exc:
        raise ValueError("LLM config cannot be loaded safely") from exc

    if not isinstance(document, Mapping):
        raise ValueError("LLM config root must be a mapping")
    settings = document.get("llm_settings")
    backends = document.get("backends")
    if not isinstance(settings, Mapping) or not isinstance(backends, Mapping):
        raise ValueError("LLM config is missing settings or backends")
    request_timeout = settings.get("request_timeout_seconds")
    if (
        isinstance(request_timeout, bool)
        or not isinstance(request_timeout, (int, float))
        or request_timeout not in (30.0, 60.0)
    ):
        raise ValueError("Provider requests require an explicit 30- or 60-second deadline")

    backend_name = settings.get("active_backend")
    backend: Any = backends.get(backend_name)
    if backend_name in {"antigravity_cli", "codex_cli"}:
        primary = _build_remote_cli_factory(
            backend_name, settings, backends, path, authorization,
        )
        fallback_name = settings.get("fallback_backend")
        if fallback_name in (None, ""):
            if request_timeout != 30.0:
                raise ValueError("60-second deadline is reserved for an explicit dual-Provider route")
            return primary
        if fallback_name == backend_name:
            raise ValueError("fallback Provider must differ from the primary Provider")
        fallback = _build_remote_cli_factory(
            fallback_name, settings, backends, path, authorization,
        )
        return RemoteCLIFailoverBackendFactory(primary=primary, fallback=fallback)

    if (
        backend_name != "antigravity_sdk"
        or request_timeout != 30.0
        or settings.get("allow_remote") is not False
        or settings.get("fallback_backend") not in (None, "")
    ):
        raise ValueError("unknown Provider or local LiteRT mode allowed remote fallback")
    if not isinstance(backend, Mapping) or backend.get("execution_mode") != "local_litert":
        raise ValueError("unknown or non-local provider; automatic fallback is forbidden")
    model_path = backend.get("model_path")
    expected_sha256 = backend.get("model_sha256")
    model_id = backend.get("model_id")
    if not isinstance(model_path, str) or not model_path.strip():
        raise ValueError("an absolute LiteRT model path is required")
    candidate = Path(model_path)
    if not candidate.is_absolute() or candidate.suffix.lower() != ".litertlm" or not candidate.is_file():
        raise ValueError("the configured LiteRT model file is unavailable")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in expected_sha256)
    ):
        raise ValueError("an approved model_sha256 is required")
    if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 160:
        raise ValueError("an approved model_id is required")
    return LiteRTBackendFactory(str(candidate), expected_sha256)

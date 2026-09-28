# -*- coding: utf-8 -*-
"""Strict provider configuration factory; unknown or remote modes fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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

            return AntigravityCLIBackend(
                cli_path=self.cli_path, model_id=self.model_id,
                remote_policy=self.remote_policy,
                working_directory=self.working_directory, **options,
            )
        if self.provider_name == "codex_cli":
            from ats.llm.codex_cli_backend import CodexCLIBackend

            return CodexCLIBackend(
                cli_path=self.cli_path, model_id=self.model_id,
                working_directory=self.working_directory,
                remote_policy=self.remote_policy, **options,
            )
        raise ValueError("unsupported remote CLI Provider")


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
    if settings.get("request_timeout_seconds") != 30.0:
        raise ValueError("Provider requests require the explicit 30-second deadline")

    backend_name = settings.get("active_backend")
    backend: Any = backends.get(backend_name)
    if backend_name in {"antigravity_cli", "codex_cli"}:
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
            scratch_path = path.parent.parent / scratch_path
        if not scratch_path.is_dir():
            raise ValueError("isolated CLI scratch_cwd must already exist")
        approval = settings.get("remote_egress")
        if not isinstance(approval, Mapping):
            raise ValueError("remote egress approval policy is missing")
        if authorization.get("acceptance_id", "").strip() != approval.get("approval_id"):
            raise ValueError("runtime acceptance_id must match the remote approval_id")
        from ats.llm.remote_sanitizer import validate_remote_policy

        if not callable(validate_remote_policy):
            raise ValueError("remote field sanitizer is unavailable")
        policy = dict(approval)
        if set(policy) != {
            "approval_id", "destination", "policy_version", "field_allowlist_by_agent",
        }:
            raise ValueError("remote egress approval policy fields are invalid")
        validate_remote_policy(policy)
        return RemoteCLIBackendFactory(
            provider_name=backend_name, cli_path=cli_path,
            model_id=model_id.strip(), working_directory=str(scratch_path.resolve()),
            remote_policy=policy,
        )

    if (
        backend_name != "antigravity_sdk"
        or settings.get("allow_remote") is not False
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

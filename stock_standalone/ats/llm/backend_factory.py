# -*- coding: utf-8 -*-
"""Strict provider configuration factory; unknown or remote modes fail closed."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ats.llm.antigravity_litert_backend import LiteRTBackendFactory


_MAX_CONFIG_BYTES = 128 * 1024


def build_backend_factory(config_path: str | Path) -> LiteRTBackendFactory:
    """Build the sole implemented backend from an explicit, local LiteRT config."""
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
    if (
        settings.get("active_backend") != "antigravity_sdk"
        or settings.get("allow_remote") is not False
        or settings.get("request_timeout_seconds") != 30.0
    ):
        raise ValueError("only the explicitly local LiteRT mode with a 30-second deadline is supported")

    backend: Any = backends.get("antigravity_sdk")
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

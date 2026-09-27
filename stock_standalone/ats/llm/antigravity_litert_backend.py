# -*- coding: utf-8 -*-
"""Fail-closed Antigravity SDK adapter for a local LiteRT checkpoint."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple


_MAX_AGENT_SESSIONS = 3
_CLOSE_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class LiteRTBackendFactory:
    """Picklable Worker factory; SDK imports happen only inside the spawned Worker."""

    model_path: str
    expected_sha256: str

    def __post_init__(self) -> None:
        candidate = Path(self.model_path)
        if not candidate.is_absolute() or candidate.suffix.lower() != ".litertlm":
            raise ValueError("LiteRT model path must be an absolute .litertlm path")
        if not isinstance(self.expected_sha256, str) or (
            len(self.expected_sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in self.expected_sha256)
        ):
            raise ValueError("an approved expected_sha256 is required")

    def __call__(self) -> "AntigravityLiteRTBackend":
        return AntigravityLiteRTBackend(self.model_path, self.expected_sha256)


class AntigravityLiteRTBackend:
    """Long-lived, tool-disabled LiteRT agents with native structured output."""

    def __init__(self, model_path: str, expected_sha256: str) -> None:
        candidate = Path(model_path)
        if not candidate.is_absolute() or candidate.suffix.lower() != ".litertlm" or not candidate.is_file():
            raise RuntimeError("LITERT_MODEL_NOT_READY")
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in expected_sha256)
        ):
            raise RuntimeError("LITERT_MODEL_HASH_NOT_APPROVED")
        if _file_sha256(candidate) != expected_sha256.lower():
            raise RuntimeError("LITERT_MODEL_HASH_MISMATCH")
        self._model_path = str(candidate)
        self._loop = asyncio.new_event_loop()
        self._sessions: Dict[str, Tuple[Any, Any]] = {}
        self._closed = False

    def generate(
        self,
        prompt: str,
        response_schema: Mapping[str, Any],
        *,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        if (
            self._closed or not isinstance(prompt, str) or not prompt
            or not isinstance(response_schema, Mapping)
            or isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= 30.0
        ):
            return {"status": "UNAVAILABLE", "error_code": "provider_request_invalid"}
        try:
            proposal = self._loop.run_until_complete(asyncio.wait_for(
                self._generate(prompt, dict(response_schema)),
                timeout=float(timeout_seconds),
            ))
        except asyncio.TimeoutError:
            return {"status": "UNAVAILABLE", "error_code": "provider_timeout"}
        except Exception:
            return {"status": "UNAVAILABLE", "error_code": "provider_runtime_failure"}
        if not isinstance(proposal, Mapping):
            return {"status": "UNAVAILABLE", "error_code": "provider_structured_output_invalid"}
        return {"status": "OK", "proposal": dict(proposal)}

    async def _generate(self, prompt: str, response_schema: Dict[str, Any]) -> Any:
        schema_hash = hashlib.sha256(_canonical_schema(response_schema)).hexdigest()
        session = self._sessions.get(schema_hash)
        if session is None:
            if len(self._sessions) >= _MAX_AGENT_SESSIONS:
                raise RuntimeError("LITERT_AGENT_SESSION_LIMIT")
            session = await self._open_agent(response_schema)
            self._sessions[schema_hash] = session
        _manager, agent = session
        response = await agent.chat(prompt)
        structured = await response.structured_output()
        if isinstance(structured, Mapping):
            return dict(structured)
        model_dump = getattr(structured, "model_dump", None)
        if callable(model_dump):
            value = model_dump()
            return value if isinstance(value, Mapping) else None
        legacy_dict = getattr(structured, "dict", None)
        if callable(legacy_dict):
            value = legacy_dict()
            return value if isinstance(value, Mapping) else None
        return None

    async def _open_agent(self, response_schema: Dict[str, Any]) -> Tuple[Any, Any]:
        try:
            from google.antigravity import Agent, LiteRTAgentConfig
        except Exception as exc:
            raise RuntimeError("ANTIGRAVITY_SDK_UNAVAILABLE") from exc
        config = LiteRTAgentConfig(
            model_path=self._model_path,
            response_schema=response_schema,
            tools=[],
            policies=[],
            hooks=[],
            mcp_servers=[],
            subagents=[],
            workspaces=[],
        )
        for attribute in ("tools", "mcp_servers", "subagents", "workspaces"):
            if not hasattr(config, attribute) or getattr(config, attribute) not in (None, [], (), {}):
                raise RuntimeError("ANTIGRAVITY_EXECUTION_SURFACE_NOT_EMPTY")
        manager = Agent(config)
        agent = await manager.__aenter__()
        return manager, agent

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._loop.run_until_complete(asyncio.wait_for(
                self._close_agents(), timeout=_CLOSE_TIMEOUT_SECONDS
            ))
        except Exception:
            pass
        finally:
            self._closed = True
            try:
                self._loop.close()
            except Exception:
                pass

    async def _close_agents(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        for manager, _agent in sessions:
            try:
                await manager.__aexit__(None, None, None)
            except Exception:
                continue


def _canonical_schema(value: Mapping[str, Any]) -> bytes:
    import json

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

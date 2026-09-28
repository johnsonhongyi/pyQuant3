# -*- coding: utf-8 -*-
"""Fail-closed field projection for explicitly approved remote Agent requests."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from ats.llm.agent_contracts import AGENT_TYPES


_FIELD_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_MAX_POLICY_BYTES = 64 * 1024
_MAX_CONTEXT_BYTES = 32 * 1024
_MAX_FIELDS = 256
_SENSITIVE_NAMES = {
    "account", "accountid", "accesstoken", "apikey", "authorization",
    "cookie", "credential", "credentials", "email", "identity",
    "log", "logs", "mobile", "nationalid", "password", "personalinfo",
    "phone", "prompt", "rawlog", "rawlogs", "rawprompt", "refreshtoken",
    "secret", "token",
}


class RemoteEgressError(ValueError):
    """Raised when an unapproved or unprojectable remote request is supplied."""


def _field_path(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise RemoteEgressError("field allowlist contains an invalid path")
    parts = tuple(value.split("."))
    if any(not _FIELD_SEGMENT.fullmatch(part) for part in parts) or any(
        re.sub(r"[^a-z0-9]", "", part.casefold()) in _SENSITIVE_NAMES
        for part in parts
    ):
        raise RemoteEgressError("field allowlist contains a prohibited path")
    return parts


def _normalize(
    value: Any, path: tuple[str, ...] = (), depth: int = 0,
    budget: Optional[List[int]] = None,
) -> Any:
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > 5000:
        raise RemoteEgressError("remote context exceeds the node limit")
    if depth > 8:
        raise RemoteEgressError("remote context exceeds the nesting limit")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and (len(value) > 4096 or "\x00" in value):
            raise RemoteEgressError("remote context contains an invalid string")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RemoteEgressError("remote context contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        if len(value) > 512:
            raise RemoteEgressError("remote context object exceeds the field limit")
        normalized: Dict[str, Any] = {}
        for key, item in value.items():
            if (
                not isinstance(key, str) or not _FIELD_SEGMENT.fullmatch(key)
                or re.sub(r"[^a-z0-9]", "", key.casefold()) in _SENSITIVE_NAMES
            ):
                raise RemoteEgressError("remote context contains an unapproved field name")
            normalized[key] = _normalize(item, path + (key,), depth + 1, budget)
        return normalized
    if isinstance(value, (list, tuple)):
        if len(value) > 512 or any(isinstance(item, (Mapping, list, tuple)) for item in value):
            raise RemoteEgressError("remote context arrays must be bounded scalar lists")
        return [_normalize(item, path, depth + 1, budget) for item in value]
    raise RemoteEgressError("remote context contains a non-JSON value")


def _leaf_paths(value: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if isinstance(value, Mapping) and value:
        paths: set[tuple[str, ...]] = set()
        for key, item in value.items():
            paths.update(_leaf_paths(item, prefix + (key,)))
        return paths
    return {prefix} if prefix else set()


def _get_path(root: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = root
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            raise RemoteEgressError("approved field is absent from this request")
        current = current[segment]
    return current


def _insert_path(root: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    current = root
    for segment in path[:-1]:
        child = current.setdefault(segment, {})
        if not isinstance(child, dict):
            raise RemoteEgressError("field allowlist paths overlap")
        current = child
    if path[-1] in current:
        raise RemoteEgressError("field allowlist paths overlap")
    current[path[-1]] = value


def build_remote_safe_request(
    agent_type: str, raw_context: Any, policy: Any,
) -> Dict[str, str]:
    """Return only canonical allowlisted context plus its fixed approval target.

    The caller must invoke this inside the Worker before constructing a remote
    prompt. Provider code must receive only the returned ``context_json``.
    """
    if agent_type not in AGENT_TYPES:
        raise RemoteEgressError("unknown Agent type")
    if not isinstance(raw_context, Mapping) or not raw_context:
        raise RemoteEgressError("remote context must be a non-empty mapping")
    if not isinstance(policy, Mapping) or set(policy) != {
        "approval_id", "destination", "policy_version", "field_allowlist_by_agent",
    }:
        raise RemoteEgressError("remote egress approval fields are incomplete")

    approval_id = policy.get("approval_id")
    destination = policy.get("destination")
    policy_version = policy.get("policy_version")
    if (
        not isinstance(approval_id, str) or not approval_id.strip()
        or len(approval_id) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in approval_id)
        or not isinstance(policy_version, str) or not policy_version.strip()
        or len(policy_version) > 64
        or any(ord(character) < 32 or ord(character) == 127 for character in policy_version)
        or not isinstance(destination, str) or len(destination) > 512
        or any(ord(character) < 33 or ord(character) == 127 for character in destination)
    ):
        raise RemoteEgressError("remote egress approval metadata is invalid")
    try:
        parsed = urlsplit(destination)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
        ):
            raise ValueError("destination must be a fixed HTTPS endpoint")
        _ = parsed.port
    except ValueError as exc:
        raise RemoteEgressError("remote egress destination is invalid") from exc

    allowlists = policy.get("field_allowlist_by_agent")
    if not isinstance(allowlists, Mapping) or not allowlists or any(
        not isinstance(agent, str) or agent not in AGENT_TYPES for agent in allowlists
    ):
        raise RemoteEgressError("per-Agent field allowlist is invalid")
    parsed_allowlists: Dict[str, list[tuple[str, ...]]] = {}
    for name, fields in allowlists.items():
        if not isinstance(fields, list) or not fields or len(fields) > _MAX_FIELDS:
            raise RemoteEgressError("per-Agent field allowlist is empty or oversized")
        paths_for_agent = [_field_path(field) for field in fields]
        if len(paths_for_agent) != len(set(paths_for_agent)):
            raise RemoteEgressError("field allowlist contains duplicates")
        for index, path in enumerate(paths_for_agent):
            if any(
                other != path and other[:len(path)] == path
                for other in paths_for_agent[index + 1:]
            ) or any(
                other != path and path[:len(other)] == other
                for other in paths_for_agent[:index]
            ):
                raise RemoteEgressError("field allowlist paths overlap")
        parsed_allowlists[name] = paths_for_agent
    paths = parsed_allowlists.get(agent_type)
    if not paths:
        raise RemoteEgressError("this Agent has no approved remote fields")
    try:
        policy_bytes = json.dumps(
            {
                "approval_id": approval_id,
                "destination": destination,
                "policy_version": policy_version,
                "field_allowlist_by_agent": {
                    name: [".".join(path) for path in fields]
                    for name, fields in parsed_allowlists.items()
                },
            },
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RemoteEgressError("remote approval policy is not strict JSON") from exc
    if len(policy_bytes) > _MAX_POLICY_BYTES:
        raise RemoteEgressError("remote approval policy exceeds 64 KiB")

    projected: Dict[str, Any] = {}
    budget = [0]
    for path in paths:
        selected = _normalize(_get_path(raw_context, path), path, budget=budget)
        _insert_path(projected, path, selected)
    try:
        encoded = json.dumps(
            projected, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise RemoteEgressError("projected remote context is not strict JSON") from exc
    if len(encoded) > min(_MAX_CONTEXT_BYTES, _MAX_POLICY_BYTES):
        raise RemoteEgressError("projected remote context exceeds 32 KiB")
    return {
        "agent_type": agent_type,
        "approval_id": approval_id,
        "destination": destination,
        "policy_version": policy_version,
        "context_json": encoded.decode("utf-8"),
    }


def validate_remote_policy(policy: Any) -> bool:
    """Validate every Agent allowlist without touching production request data."""
    if not isinstance(policy, Mapping):
        raise RemoteEgressError("remote egress approval fields are incomplete")
    allowlists = policy.get("field_allowlist_by_agent")
    if not isinstance(allowlists, Mapping) or not allowlists:
        raise RemoteEgressError("per-Agent field allowlist is invalid")
    for agent_type, fields in allowlists.items():
        if not isinstance(fields, list):
            raise RemoteEgressError("per-Agent field allowlist is invalid")
        sample: Dict[str, Any] = {}
        for field in fields:
            _insert_path(sample, _field_path(field), 0)
        build_remote_safe_request(agent_type, sample, policy)
    return True

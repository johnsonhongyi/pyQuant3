"""Strict JSON-only request and response contracts for the IPO LLM sidecar."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, Mapping

from ats.llm.agent_contracts import (
    AGENT_TYPES,
    AgentContractError,
    payload_schema_hash,
    validate_agent_envelope,
)


MAX_IPC_MESSAGE_BYTES = 64 * 1024
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_FIELDS = {
    "request_id", "agent_type", "scope_id", "ticker", "as_of_time",
    "prompt", "context", "model_id", "prompt_version", "evidence_ids", "schema_hash",
}
_RESPONSE_FIELDS = {"request_id", "status", "envelope", "error_code"}


class WorkerProtocolError(ValueError):
    """Raised when an IPC message violates the bounded sidecar contract."""


def _text(value: Any, name: str, limit: int, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str) or len(value) > limit or "\x00" in value
        or (not allow_empty and not value.strip())
    ):
        raise WorkerProtocolError(f"{name} is invalid")
    return value


def _aware_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise WorkerProtocolError(f"{name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkerProtocolError(f"{name} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WorkerProtocolError(f"{name} must include a UTC offset")
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise WorkerProtocolError(f"{name} is invalid") from exc


def _encode(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise WorkerProtocolError("IPC message must contain strict JSON values") from exc
    if len(encoded) > MAX_IPC_MESSAGE_BYTES:
        raise WorkerProtocolError("IPC message exceeds 64 KiB")
    return encoded.decode("utf-8")


def encode_worker_request(request: Any) -> str:
    """Validate and encode a pre-sanitized request; callers must use the LLM control thread."""
    if not isinstance(request, Mapping) or set(request) != _REQUEST_FIELDS:
        raise WorkerProtocolError("worker request fields do not match the contract")
    clean = dict(request)
    request_id = _text(clean["request_id"], "request_id", 128)
    agent_type = clean["agent_type"]
    if agent_type not in AGENT_TYPES:
        raise WorkerProtocolError("unknown agent_type")
    scope_id = _text(clean["scope_id"], "scope_id", 128)
    ticker = _text(clean["ticker"], "ticker", 16, allow_empty=True)
    if scope_id == "MARKET":
        if ticker:
            raise WorkerProtocolError("market request ticker must be empty")
    elif not re.fullmatch(r"\d{6}", ticker) or scope_id != ticker:
        raise WorkerProtocolError("ticker-scoped request identity is invalid")
    _aware_time(clean["as_of_time"], "as_of_time")
    clean["prompt"] = _text(clean["prompt"], "prompt", 48 * 1024)
    if not isinstance(clean["context"], Mapping):
        raise WorkerProtocolError("worker context must be a mapping")
    try:
        context_bytes = json.dumps(
            clean["context"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise WorkerProtocolError("worker context must contain strict JSON values") from exc
    if len(context_bytes) > 48 * 1024:
        raise WorkerProtocolError("worker context exceeds 48 KiB")
    clean["model_id"] = _text(clean["model_id"], "model_id", 160)
    clean["prompt_version"] = _text(clean["prompt_version"], "prompt_version", 128)
    evidence_ids = clean["evidence_ids"]
    if (
        not isinstance(evidence_ids, list) or len(evidence_ids) > 32
        or any(not isinstance(item, str) or not item.strip() or len(item) > 160 for item in evidence_ids)
        or len(evidence_ids) != len(set(evidence_ids))
    ):
        raise WorkerProtocolError("evidence_ids are invalid")
    schema_hash = clean["schema_hash"]
    if (
        not isinstance(schema_hash, str) or not _HEX_64.fullmatch(schema_hash)
        or schema_hash != payload_schema_hash(agent_type)
    ):
        raise WorkerProtocolError("agent schema hash mismatch")
    return _encode(clean)


def decode_worker_request(message: Any) -> Dict[str, Any]:
    if not isinstance(message, str):
        raise WorkerProtocolError("worker request message size is invalid")
    try:
        if len(message.encode("utf-8")) > MAX_IPC_MESSAGE_BYTES:
            raise WorkerProtocolError("worker request message size is invalid")
    except UnicodeError as exc:
        raise WorkerProtocolError("worker request message encoding is invalid") from exc
    try:
        request = json.loads(message)
    except (TypeError, ValueError, RecursionError) as exc:
        raise WorkerProtocolError("worker request JSON is invalid") from exc
    encode_worker_request(request)
    return request


def encode_worker_response(response: Any, request: Mapping[str, Any]) -> str:
    request = decode_worker_request(encode_worker_request(request))
    if not isinstance(response, Mapping) or set(response) != _RESPONSE_FIELDS:
        raise WorkerProtocolError("worker response fields do not match the contract")
    clean = dict(response)
    if clean["request_id"] != request.get("request_id"):
        raise WorkerProtocolError("worker response request_id mismatch")
    status = clean["status"]
    if not isinstance(status, str) or status not in {"OK", "UNAVAILABLE", "INVALID"}:
        raise WorkerProtocolError("worker response status is invalid")
    if status == "OK":
        if clean["error_code"] not in ("", None):
            raise WorkerProtocolError("successful response cannot contain an error")
        try:
            envelope = validate_agent_envelope(clean["envelope"])
        except AgentContractError as exc:
            raise WorkerProtocolError("worker envelope failed agent validation") from exc
        metadata = envelope["metadata"]
        if (
            envelope["agent_type"] != request.get("agent_type")
            or metadata["request_id"] != request.get("request_id")
            or metadata["scope_id"] != request.get("scope_id")
            or metadata["ticker"] != request.get("ticker")
            or metadata["as_of_time"] != request.get("as_of_time")
            or metadata["model_id"] != request.get("model_id")
            or metadata["prompt_version"] != request.get("prompt_version")
            or metadata["evidence_ids"] != request.get("evidence_ids")
        ):
            raise WorkerProtocolError("worker envelope does not match its request")
        clean["envelope"] = envelope
        clean["error_code"] = ""
    else:
        if clean["envelope"] is not None:
            raise WorkerProtocolError("failed response cannot contain an envelope")
        clean["error_code"] = _text(clean["error_code"], "error_code", 120)
    return _encode(clean)


def decode_worker_response(message: Any, request: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(message, str):
        raise WorkerProtocolError("worker response message size is invalid")
    try:
        if len(message.encode("utf-8")) > MAX_IPC_MESSAGE_BYTES:
            raise WorkerProtocolError("worker response message size is invalid")
    except UnicodeError as exc:
        raise WorkerProtocolError("worker response message encoding is invalid") from exc
    try:
        response = json.loads(message)
    except (TypeError, ValueError, RecursionError) as exc:
        raise WorkerProtocolError("worker response JSON is invalid") from exc
    encode_worker_response(response, request)
    return response

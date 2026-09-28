# -*- coding: utf-8 -*-
"""Strict, provider-independent contracts for the three IPO LLM agents."""

from __future__ import annotations

import json
import hashlib
import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Sequence


class AgentContractError(ValueError):
    """Raised when an agent payload or worker-created envelope is invalid."""


AGENT_TYPES = ("MARKET_REGIME", "CASE_RETRIEVAL", "POST_CLOSE_REVIEW")
AGENT_CONTRACT_VERSION = "r9.agent-payload.v2"
_STAGE_HINTS = ("NEUTRAL", "PANIC", "REPAIR", "REVERSAL", "FOMO", "COOLDOWN")
_METADATA_FIELDS = {
    "request_id", "scope_id", "ticker", "as_of_time", "generated_at",
    "model_id", "prompt_version", "evidence_ids",
}
_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _text(value: Any, name: str, limit: int = 500, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise AgentContractError(f"{name} must be a string of at most {limit} characters")
    if not allow_empty and not value.strip():
        raise AgentContractError(f"{name} is required")
    return value


def _aware_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise AgentContractError(f"{name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (OverflowError, TypeError, ValueError) as exc:
        raise AgentContractError(f"{name} is not a valid ISO-8601 time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AgentContractError(f"{name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _string_list(value: Any, name: str, limit: int = 32) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise AgentContractError(f"{name} must be a list of at most {limit} items")
    items = [_text(item, name, 160) for item in value]
    if len(items) != len(set(items)):
        raise AgentContractError(f"{name} must not contain duplicates")
    return items


_EVIDENCE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "evidence_ids": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 32},
    },
    "required": ["summary", "evidence_ids"],
    "additionalProperties": False,
}

_AGENT_PAYLOAD_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "MARKET_REGIME": {
        "type": "object",
        "properties": {
            "sentiment_score": {"type": "number", "minimum": 0, "maximum": 100},
            "stage_hint": {"type": "string", "enum": list(_STAGE_HINTS)},
            "catalysts": {"type": "array", "items": deepcopy(_EVIDENCE_ITEM_SCHEMA), "maxItems": 20},
            "risk_warnings": {"type": "array", "items": deepcopy(_EVIDENCE_ITEM_SCHEMA), "maxItems": 20},
        },
        "required": ["sentiment_score", "stage_hint", "catalysts", "risk_warnings"],
        "additionalProperties": False,
    },
    "CASE_RETRIEVAL": {
        "type": "object",
        "properties": {
            "similar_cases": {
                "type": "array", "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string", "minLength": 1, "maxLength": 160},
                        "published_at": {"type": "string", "format": "date-time"},
                        "evidence_ids": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 32},
                        "differences": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 20},
                        "evidence_summary": {"type": "string", "minLength": 1, "maxLength": 1000},
                    },
                    "required": ["case_id", "published_at", "evidence_ids", "differences", "evidence_summary"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["similar_cases"],
        "additionalProperties": False,
    },
    "POST_CLOSE_REVIEW": {
        "type": "object",
        "properties": {
            "input_snapshot_hash": {"type": "string", "pattern": "^[0-9a-fA-F]{64}$"},
            "cutoff": {"type": "string", "format": "date-time"},
            "labels_mature": {"type": "boolean"},
            "matured_at": {"type": ["string", "null"], "format": "date-time"},
            "label_source": {"type": "string", "minLength": 1, "maxLength": 240},
            "outcome_evidence_ids": {
                "type": "array", "items": {"type": "string", "maxLength": 160},
                "maxItems": 32,
            },
            "review_draft": {"type": "string", "minLength": 1, "maxLength": 4000},
            "gate_trace_ids": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 100},
            "preference_draft": {
                "type": ["object", "null"],
                "properties": {
                    "chosen_proposal": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "rejected_proposal": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
                "required": ["chosen_proposal", "rejected_proposal", "reason"],
                "additionalProperties": False,
            },
        },
        "required": [
            "input_snapshot_hash", "cutoff", "labels_mature", "matured_at",
            "label_source", "outcome_evidence_ids", "review_draft", "gate_trace_ids",
            "preference_draft",
        ],
        "additionalProperties": False,
    },
}


def payload_schema(
    agent_type: str, *, evidence_ids: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Return a defensive copy of the strict schema sent to a Provider."""
    if agent_type not in AGENT_TYPES:
        raise AgentContractError("unknown agent_type")
    schema = deepcopy(_AGENT_PAYLOAD_SCHEMAS[agent_type])
    if evidence_ids is not None and agent_type == "MARKET_REGIME":
        if (
            isinstance(evidence_ids, (str, bytes))
            or not isinstance(evidence_ids, Sequence)
            or any(not isinstance(item, str) or not item.strip() for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
        ):
            raise AgentContractError("Provider evidence IDs are invalid")
        for field in ("catalysts", "risk_warnings"):
            schema["properties"][field]["items"]["properties"]["evidence_ids"]["items"]["enum"] = list(evidence_ids)
    return schema


def payload_schema_hash(agent_type: str) -> str:
    """Return a stable SHA-256 for audit and dataset provenance."""
    encoded = json.dumps(
        payload_schema(agent_type), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_evidence_refs(items: Sequence[Mapping[str, Any]], evidence_ids: set[str], name: str) -> None:
    for index, item in enumerate(items):
        refs = _string_list(item.get("evidence_ids"), f"{name}[{index}].evidence_ids")
        if not refs or not set(refs).issubset(evidence_ids):
            raise AgentContractError(f"{name}[{index}] references evidence absent from worker metadata")


def validate_payload(agent_type: str, payload: Any, metadata: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a Provider payload against its agent-specific strict contract."""
    if agent_type not in AGENT_TYPES:
        raise AgentContractError("unknown agent_type")
    if not isinstance(payload, dict):
        raise AgentContractError("payload is not an object")
    if not isinstance(metadata, Mapping):
        raise AgentContractError("metadata is not an object")
    if set(payload) != set(_AGENT_PAYLOAD_SCHEMAS[agent_type]["required"]):
        raise AgentContractError(f"{agent_type} payload fields do not match its strict schema")
    evidence_ids = set(_string_list(metadata.get("evidence_ids"), "metadata.evidence_ids", 256))

    if agent_type == "MARKET_REGIME":
        score = payload.get("sentiment_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or not 0 <= score <= 100:
            raise AgentContractError("sentiment_score must be finite and between 0 and 100")
        if payload.get("stage_hint") not in _STAGE_HINTS:
            raise AgentContractError("stage_hint is not an allowed advisory state")
        for key in ("catalysts", "risk_warnings"):
            items = payload.get(key)
            if not isinstance(items, list) or len(items) > 20:
                raise AgentContractError(f"{key} must be a list of at most 20 items")
            for item in items:
                if not isinstance(item, dict) or set(item) != {"summary", "evidence_ids"}:
                    raise AgentContractError(f"{key} contains an invalid evidence item")
                _text(item["summary"], f"{key}.summary", 500)
            _check_evidence_refs(items, evidence_ids, key)

    elif agent_type == "CASE_RETRIEVAL":
        cases = payload.get("similar_cases")
        if not isinstance(cases, list) or len(cases) > 20:
            raise AgentContractError("similar_cases must be a list of at most 20 items")
        cutoff = _aware_time(metadata.get("as_of_time"), "metadata.as_of_time")
        seen_case_ids = set()
        for index, case in enumerate(cases):
            required = {"case_id", "published_at", "evidence_ids", "differences", "evidence_summary"}
            if not isinstance(case, dict) or set(case) != required:
                raise AgentContractError(f"similar_cases[{index}] fields do not match the schema")
            case_id = _text(case["case_id"], f"similar_cases[{index}].case_id", 160)
            if case_id in seen_case_ids:
                raise AgentContractError("similar_cases contains duplicate case_id")
            seen_case_ids.add(case_id)
            if _aware_time(case["published_at"], f"similar_cases[{index}].published_at") > cutoff:
                raise AgentContractError("similar case published after cutoff")
            refs = _string_list(case["evidence_ids"], f"similar_cases[{index}].evidence_ids")
            if not refs or not set(refs).issubset(evidence_ids):
                raise AgentContractError("similar case references evidence absent from worker metadata")
            differences = _string_list(case["differences"], f"similar_cases[{index}].differences", 20)
            if not differences:
                raise AgentContractError("similar case must explain at least one difference")
            _text(case["evidence_summary"], f"similar_cases[{index}].evidence_summary", 1000)

    else:
        if not isinstance(payload.get("input_snapshot_hash"), str) or not _HEX_64.fullmatch(payload["input_snapshot_hash"]):
            raise AgentContractError("input_snapshot_hash must be a SHA-256 hex digest")
        cutoff = _aware_time(payload.get("cutoff"), "payload.cutoff")
        if cutoff != _aware_time(metadata.get("as_of_time"), "metadata.as_of_time"):
            raise AgentContractError("review cutoff must match the sealed input snapshot time")
        mature = payload.get("labels_mature")
        if not isinstance(mature, bool):
            raise AgentContractError("labels_mature must be boolean")
        matured_at = payload.get("matured_at")
        outcome_refs = _string_list(
            payload.get("outcome_evidence_ids"), "outcome_evidence_ids", 32
        )
        if mature:
            matured_time = _aware_time(matured_at, "matured_at")
            if matured_time < cutoff:
                raise AgentContractError("matured_at must not precede the decision cutoff")
            if matured_time > _aware_time(metadata.get("generated_at"), "metadata.generated_at"):
                raise AgentContractError("matured_at cannot be after generated_at")
            if (
                not outcome_refs
                or any(not reference.startswith("outcome:") for reference in outcome_refs)
                or any(not reference.removeprefix("outcome:").strip() for reference in outcome_refs)
                or not set(outcome_refs).issubset(evidence_ids)
            ):
                raise AgentContractError(
                    "mature labels must cite worker-provided outcome evidence IDs"
                )
        elif matured_at is not None or outcome_refs:
            raise AgentContractError("pending labels must not claim maturity or outcome evidence")
        _text(payload.get("label_source"), "label_source", 240)
        _text(payload.get("review_draft"), "review_draft", 4000)
        trace_ids = _string_list(payload.get("gate_trace_ids"), "gate_trace_ids", 100)
        if not trace_ids or not set(trace_ids).issubset(evidence_ids):
            raise AgentContractError("gate_trace_ids must reference worker-provided evidence")
        preference = payload.get("preference_draft")
        if preference is not None:
            expected = {"chosen_proposal", "rejected_proposal", "reason"}
            if not isinstance(preference, dict) or set(preference) != expected:
                raise AgentContractError("preference_draft does not match its strict schema")
            _text(preference["chosen_proposal"], "chosen_proposal", 2000)
            _text(preference["rejected_proposal"], "rejected_proposal", 2000)
            _text(preference["reason"], "preference reason", 1000)
            if not mature:
                raise AgentContractError("pending labels cannot create a preference draft")

    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AgentContractError("payload must contain only strict JSON values") from exc
    if len(encoded) > 32 * 1024:
        raise AgentContractError("payload exceeds 32 KiB")
    return json.loads(encoded)


def _validate_metadata(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
        raise AgentContractError("metadata fields do not match the strict envelope schema")
    normalized = dict(metadata)
    for key, limit in (("request_id", 128), ("scope_id", 128), ("ticker", 16), ("model_id", 160), ("prompt_version", 128)):
        normalized[key] = _text(normalized.get(key), f"metadata.{key}", limit, allow_empty=(key == "ticker"))
    as_of = _aware_time(normalized.get("as_of_time"), "metadata.as_of_time")
    generated = _aware_time(normalized.get("generated_at"), "metadata.generated_at")
    if generated < as_of:
        raise AgentContractError("generated_at cannot be before as_of_time")
    normalized["evidence_ids"] = _string_list(normalized.get("evidence_ids"), "metadata.evidence_ids", 256)
    ticker = normalized["ticker"]
    if normalized["scope_id"] == "MARKET":
        if ticker:
            raise AgentContractError("MARKET scope must not contain a ticker")
    elif normalized["scope_id"] != ticker or not re.fullmatch(r"\d{6}", ticker):
        raise AgentContractError("single-stock scope_id and six-digit ticker must match")
    return normalized


def build_agent_envelope(
    agent_type: str,
    payload: Any,
    *,
    request_id: str,
    scope_id: str,
    ticker: str,
    as_of_time: str,
    generated_at: str,
    model_id: str,
    prompt_version: str,
    evidence_ids: Sequence[str],
) -> Dict[str, Any]:
    """Build trusted metadata around payload-only Provider output."""
    if agent_type not in AGENT_TYPES:
        raise AgentContractError("unknown agent_type")
    if isinstance(evidence_ids, (str, bytes)) or not isinstance(evidence_ids, Sequence):
        raise AgentContractError("evidence_ids must be a sequence of evidence identifiers")
    metadata = _validate_metadata({
        "request_id": request_id, "scope_id": scope_id, "ticker": ticker,
        "as_of_time": as_of_time, "generated_at": generated_at,
        "model_id": model_id, "prompt_version": prompt_version,
        "evidence_ids": list(evidence_ids),
    })
    clean_payload = validate_payload(agent_type, payload, metadata)
    return {"agent_type": agent_type, "metadata": metadata, "payload": clean_payload}


def validate_agent_envelope(envelope: Any) -> Dict[str, Any]:
    """Revalidate an envelope before downstream display or Gate consideration."""
    if not isinstance(envelope, dict) or set(envelope) != {"agent_type", "metadata", "payload"}:
        raise AgentContractError("envelope fields do not match the strict schema")
    agent_type = envelope["agent_type"]
    if agent_type not in AGENT_TYPES:
        raise AgentContractError("unknown agent_type")
    metadata = _validate_metadata(envelope["metadata"])
    payload = validate_payload(agent_type, envelope["payload"], metadata)
    return {"agent_type": agent_type, "metadata": metadata, "payload": payload}

"""Loopback-only, native-schema Ollama adapter for the existing bounded Worker."""

from __future__ import annotations

from sys_utils import safe_resolve_path

import json
import hashlib
import math
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path

from ats.llm.agent_contracts import AGENT_CONTRACT_VERSION, AGENT_TYPES, payload_schema, payload_schema_hash, validate_payload
from ats.llm.worker_protocol import encode_worker_request


def local_ollama_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Ollama requires an explicit loopback URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Ollama only accepts a loopback HTTP origin without credentials")
    port = parsed.port if parsed.port is not None else 11434
    if not 1 <= port <= 65535:
        raise ValueError("invalid Ollama port")
    host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{port}"


def ollama_binding_hash(base_url: str, model_id: str) -> str:
    binding = {"adapter_version": "ollama.native-schema.v1", "provider_id": "ollama_http",
               "base_url": local_ollama_url(base_url), "model_id": model_id.strip(),
               "contract_version": AGENT_CONTRACT_VERSION,
               "schemas": {name: payload_schema_hash(name) for name in AGENT_TYPES}}
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def ollama_acceptance_matches(config_path: Path, backend: Mapping[str, Any], authorization: Mapping[str, Any]) -> bool:
    """Generic runtime flags cannot authorize a different local model or origin."""
    try:
        path = config_path.with_name("ollama_provider_acceptance.json")
        if path.stat().st_size > 16 * 1024:
            return False
        record = json.loads(path.read_text(encoding="utf-8"))
        expected = ollama_binding_hash(backend["base_url"], backend["model"])
        if (record.get("status") != "ACCEPTED" or record.get("acceptance_id") != authorization.get("acceptance_id")
                or record.get("binding_hash") != expected or not isinstance(record.get("reviewer"), str)
                or not record["reviewer"].strip()):
            return False
        accepted = datetime.fromisoformat(record["accepted_at"].replace("Z", "+00:00"))
        if accepted.tzinfo is None or accepted.utcoffset() is None or accepted > datetime.now(timezone.utc):
            return False
        root = safe_resolve_path(config_path.parent.parent)
        evidence_path = (root / record["evidence_path"]).resolve()
        if not evidence_path.is_relative_to(root) or evidence_path.stat().st_size > 64 * 1024:
            return False
        raw = evidence_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.get("evidence_sha256"):
            return False
        evidence = json.loads(raw.decode("utf-8"))
        completed = datetime.fromisoformat(evidence["completed_at"].replace("Z", "+00:00"))
        return bool(
            evidence.get("state") == "PROBE_PASSED" and evidence.get("operating_mode") == "INTERFACE_PROBE"
            and evidence.get("binding_hash") == expected and evidence.get("provider_id") == "ollama_http"
            and evidence.get("model_id") == backend["model"].strip()
            and evidence.get("native_schema_validated") is True and evidence.get("worker_protocol_validated") is True
            and completed.tzinfo is not None and completed.utcoffset() is not None and completed <= accepted)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError("OLLAMA_REDIRECT_BLOCKED")


@dataclass(frozen=True)
class OllamaBackendFactory:
    base_url: str
    model_id: str

    def __call__(self) -> "OllamaHTTPBackend":
        return OllamaHTTPBackend(self.base_url, self.model_id)


class OllamaHTTPBackend:
    provider_id = "ollama_http"

    def __init__(self, base_url: str, model_id: str) -> None:
        self.base_url = local_ollama_url(base_url)
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 160:
            raise ValueError("a fixed local model ID is required")
        self.model_id = model_id.strip()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def generate_request(self, request: Mapping[str, Any], response_schema: Mapping[str, Any], *,
                         timeout_seconds: float) -> dict[str, Any]:
        result = {"status": "UNAVAILABLE", "provider_id": self.provider_id, "model_id": self.model_id}
        try:
            encode_worker_request(request)
            if request["model_id"] != self.model_id:
                raise ValueError("MODEL_ID_MISMATCH")
            schema = payload_schema(request["agent_type"], evidence_ids=request["evidence_ids"])
            if response_schema != schema:
                raise ValueError("SCHEMA_MISMATCH")
            if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                    or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30):
                raise ValueError("TIMEOUT_INVALID")
            prompt = request["prompt"] + "\n已验证上下文(JSON)：\n" + json.dumps(
                request["context"], ensure_ascii=False, sort_keys=True, allow_nan=False)
            body = json.dumps({
                "model": self.model_id, "prompt": prompt, "format": schema,
                "stream": False, "think": False,
                "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 1024},
            }, ensure_ascii=False, allow_nan=False).encode("utf-8")
            http_request = urllib.request.Request(self.base_url + "/api/generate", data=body,
                                                  headers={"Content-Type": "application/json"})
            with self._opener.open(http_request, timeout=float(timeout_seconds)) as response:
                if response.status != 200:
                    raise ValueError("OLLAMA_HTTP_ERROR")
                raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError("OLLAMA_RESPONSE_TOO_LARGE")
            document = json.loads(raw.decode("utf-8"))
            if (not isinstance(document, dict) or document.get("done") is not True
                    or document.get("done_reason") != "stop" or document.get("model") != self.model_id):
                raise ValueError("OLLAMA_INCOMPLETE_OR_WRONG_MODEL")
            proposal = json.loads(document["response"])
            proposal = validate_payload(request["agent_type"], proposal, {
                "evidence_ids": request["evidence_ids"], "as_of_time": request["as_of_time"],
                "generated_at": document.get("created_at"),
            })
            return {"status": "OK", "proposal": proposal,
                    "provider_id": self.provider_id, "model_id": self.model_id}
        except (TimeoutError, socket.timeout):
            result["error_code"] = "OLLAMA_TIMEOUT"
        except urllib.error.HTTPError as exc:
            result["error_code"] = f"OLLAMA_HTTP_{exc.code}"
            exc.close()
        except urllib.error.URLError as exc:
            result["error_code"] = "OLLAMA_TIMEOUT" if isinstance(exc.reason, TimeoutError) else "OLLAMA_SERVICE_UNAVAILABLE"
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
            result["error_code"] = "OLLAMA_REQUEST_OR_OUTPUT_INVALID"
        return result

    def close(self) -> None:
        self._opener.close()

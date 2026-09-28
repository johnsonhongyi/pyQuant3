"""App lifecycle wiring for the gated IPO LLM sidecar."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ats.llm.backend_factory import build_backend_factory
from ats.llm.control_thread import LLMControlThread
from ats.llm.llm_worker import LLMWorkerProcess
from ats.llm.provider_preflight import inspect_provider_preflight
from ats.llm.request_producer import LiveSnapshotRequestProducer, signal_max_age_seconds


_LOCAL_AUTHORIZATION_KEYS = {
    "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
    "acceptance_id",
}
_REMOTE_AUTHORIZATION_KEYS = _LOCAL_AUTHORIZATION_KEYS | {
    "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
}


def _unavailable_backend_factory() -> Any:
    raise RuntimeError("an accepted LLM backend is required")


def _load_authorization(path: Path) -> Dict[str, Any]:
    denied = {
        "stage0_accepted": False,
        "provider_accepted": False,
        "process_tree_isolation_accepted": False,
        "acceptance_id": "",
    }
    try:
        if path.stat().st_size > 16 * 1024:
            return denied
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, ValueError, RecursionError):
        return denied
    if not isinstance(document, dict) or frozenset(document) not in {
        frozenset(_LOCAL_AUTHORIZATION_KEYS), frozenset(_REMOTE_AUTHORIZATION_KEYS),
    }:
        return denied
    accepted_keys = set(document) - {"acceptance_id"}
    if any(document.get(key) is not True for key in accepted_keys):
        return denied
    if not stage0_to_2_accepted(path.parent.parent):
        return denied
    acceptance_id = document.get("acceptance_id")
    if (
        not isinstance(acceptance_id, str) or not acceptance_id.strip()
        or len(acceptance_id) > 160 or any(ord(char) < 32 for char in acceptance_id)
    ):
        return denied
    return {**document, "acceptance_id": acceptance_id.strip()}
def stage0_to_2_accepted(root: Path) -> bool:
    """Keep even local model initialization closed until the first three gates pass."""
    acceptance_path = root / "config" / "ipo_stage_acceptance.json"
    try:
        if acceptance_path.stat().st_size > 64 * 1024:
            return False
        with acceptance_path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
        stages = document.get("stages") if isinstance(document, dict) else None
        if not isinstance(stages, dict):
            return False
        for index in range(3):
            record = stages.get(str(index), stages.get(f"stage{index}"))
            if not isinstance(record, dict) or record.get("status") != "ACCEPTED" or not record.get("evidence"):
                return False
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

        config = IPODecisionConfigSnapshot.from_yaml(
            str(root / "config" / "ipo_sentiment.yaml")
        )
        return config.verify_integrity() and signal_max_age_seconds(config) > 0
    except Exception:
        return False


def create_runtime_control_thread(root: str | Path) -> LLMControlThread:
    """Create the status publisher; every execution gate remains independently enforced."""
    resolved_root = Path(root).resolve()
    config_path = resolved_root / "config" / "llm_config.yaml"
    authorization = _load_authorization(
        resolved_root / "config" / "llm_runtime_acceptance.json"
    )
    preflight = inspect_provider_preflight(config_path, authorization=authorization)
    try:
        backend_factory = build_backend_factory(config_path, authorization=authorization)
    except Exception:
        backend_factory = _unavailable_backend_factory
    worker = LLMWorkerProcess(backend_factory, request_timeout_seconds=30.0)
    return LLMControlThread(
        root=resolved_root,
        worker=worker,
        provider_preflight=preflight,
        authorization=authorization,
        request_producer=LiveSnapshotRequestProducer(resolved_root),
    )

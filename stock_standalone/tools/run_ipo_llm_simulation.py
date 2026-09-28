# -*- coding: utf-8 -*-
"""Run an isolated synthetic IPO → Gate → CLI LLM → journal smoke workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Mapping

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
SIMULATION_ROOT = APP_ROOT / "data" / "ipo_learning_simulation"
SIMULATED_TICKER = "999999"
SIMULATION_ACCEPTANCE_ID = "SIMULATION_ONLY"
REMOTE_FIELDS = ["snapshot_hash", "ticker", "cutoff", "rule_decision", "input_snapshot"]


def _synthetic_value(field_id: str, value_type: str) -> Any:
    if value_type == "integer":
        return 1
    if value_type == "any":
        return ["模拟热点", "合成样本"]
    known = {
        "issue_price": 10.0, "current_price": 10.2, "session_low": 9.8,
        "session_high": 10.5, "pe_ratio": 22.0, "industry_pe_median": 28.0,
        "advance_decline_ratio": 1.1, "price_vwap_dist_pct": 1.5,
        "ret_pct": 2.0, "turnover_pct": 8.0,
    }
    return known.get(field_id, 50.0)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _simulation_policy() -> Dict[str, Any]:
    return {
        "approval_id": SIMULATION_ACCEPTANCE_ID,
        "destination": "https://simulation.invalid",
        "policy_version": "synthetic-only-v1",
        "field_allowlist_by_agent": {
            "MARKET_REGIME": list(REMOTE_FIELDS),
            "CASE_RETRIEVAL": ["ticker"],
            "POST_CLOSE_REVIEW": ["ticker"],
        },
    }


def _simulation_authorization() -> Dict[str, Any]:
    return {
        "stage0_accepted": True,
        "provider_accepted": True,
        "process_tree_isolation_accepted": True,
        "tool_access_isolation_accepted": True,
        "remote_egress_isolation_accepted": True,
        "acceptance_id": SIMULATION_ACCEPTANCE_ID,
    }


def _write_run_configuration(root: Path, provider: str, model_id: str) -> None:
    import yaml

    from tools.bootstrap_ipo_configuration import build_configuration

    (root / "config").mkdir(parents=True, exist_ok=True)
    config = build_configuration()
    with (root / "config" / "ipo_sentiment.yaml").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False, width=110)

    scratch = root / "scratch" / provider
    scratch.mkdir(parents=True, exist_ok=True)
    policy = _simulation_policy()
    active_backend = {
        "execution_mode": "remote_api", "enabled": True, "model_id": model_id,
        "scratch_cwd": str(scratch.resolve()),
    }
    if provider == "antigravity_cli":
        active_backend["cli_path"] = "agy"
        other_backend = {
            "execution_mode": "remote_api", "enabled": False,
            "bin_path": "codex", "model_id": "gpt-6-luna",
            "scratch_cwd": str((root / "scratch" / "codex").resolve()),
        }
        backends = {"antigravity_cli": active_backend, "codex_cli": other_backend}
    else:
        active_backend["bin_path"] = "codex"
        other_backend = {
            "execution_mode": "remote_api", "enabled": False,
            "cli_path": "agy", "model_id": "gemini-3.8-flash-medium",
            "scratch_cwd": str((root / "scratch" / "antigravity").resolve()),
        }
        backends = {"antigravity_cli": other_backend, "codex_cli": active_backend}
    backends["antigravity_sdk"] = {
        "execution_mode": "local_litert", "model_path": "",
        "model_sha256": "", "model_id": "",
    }
    document = {
        "version": "simulation-only-v1",
        "llm_settings": {
            "active_backend": provider, "allow_remote": True,
            "request_timeout_seconds": 30.0,
            "remote_egress": policy,
        },
        "backends": backends,
    }
    with (root / "config" / "llm_config.yaml").open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        yaml.safe_dump(document, stream, allow_unicode=True, sort_keys=False, width=110)

    stages = {
        str(index): {
            "status": "ACCEPTED",
            "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": "仿真数据验收夹具；不构成生产验收。",
            "evidence": [f"SIMULATION_ONLY:{provider}:stage{index}"],
        }
        for index in range(3)
    }
    _write_json(root / "config" / "ipo_stage_acceptance.json", {
        "simulation_only": True, "stages": stages,
    })
    _write_json(root / "config" / "llm_runtime_acceptance.json", _simulation_authorization())


def _seed_synthetic_observations(root: Path, config: Any) -> int:
    from ats.strategy.ipo_source_orchestrator import store_observation

    now = datetime.now(timezone.utc)
    stored = 0
    for field_id, contract in config.data_contract.fields.items():
        observation = {
            "status": "OBSERVED",
            "value": _synthetic_value(field_id, contract.value_type),
            "as_of_time": now,
            "available_at": now,
            "source_id": contract.source_id,
            "source_version": contract.source_version,
            "source_timezone": contract.source_timezone,
        }
        if not store_observation(
            root, ticker=SIMULATED_TICKER, field_id=field_id,
            observation=observation, config=config,
        ):
            raise RuntimeError(f"synthetic field rejected: {field_id}")
        stored += 1
    return stored


def _record_gate_snapshot(root: Path, config: Any) -> Dict[str, Any]:
    from ats.llm.learning_snapshot_store import (
        record_decision_snapshot, shutdown_snapshot_writers,
    )
    from ats.strategy.gate_orchestrator import GateOrchestrator
    from ats.strategy.ipo_gate_context_provider import IPOGateContextProvider

    provider = IPOGateContextProvider(root)
    if not provider.refresh(config):
        raise RuntimeError("synthetic SQLite observations did not refresh")
    now = datetime.now(timezone.utc)
    context = provider(SimpleNamespace(code=SIMULATED_TICKER))
    passport = GateOrchestrator().evaluate(
        code=SIMULATED_TICKER, name="合成样本",
        lrrm=context["lrrm"], ipo_regime=context["ipo_regime"],
        t1_carry=context["t1_carry"], listing_anchors=context["listing_anchors"],
        vwap=context["vwap"], current_price=10.2, intraday_low=9.8,
        listing_age_sessions=1, horse_rank=1,
        market_as_of_time=now,
        max_vwap_stale_seconds=int(context["max_vwap_stale_seconds"]),
        issue_price=context["issue_price"],
        data_contract=context["data_contract"],
        data_observations=context["data_observations"],
        data_contract_hash=context["data_contract_hash"],
        configuration_version=context["configuration_version"],
        configuration_hash=context["configuration_hash"],
        decision_config=context["decision_config"],
    )
    snapshot = passport.learning_input_snapshot
    snapshot_hash = passport.learning_input_snapshot_hash
    if passport.final_decision != "BLOCK" or not snapshot or not snapshot_hash:
        raise RuntimeError("synthetic Gate did not fail closed with a sealed snapshot")
    event_id = f"simulation:{uuid.uuid4().hex}"
    saved = record_decision_snapshot(
        root, ticker=SIMULATED_TICKER, event_id=event_id,
        decision="BLOCK", configuration_version=config.config_version,
        snapshot=snapshot, snapshot_hash=snapshot_hash,
        gate_causal_chain=list(passport.causal_chain),
    )
    if not saved or not shutdown_snapshot_writers(timeout_seconds=5.0):
        raise RuntimeError("synthetic point-in-time snapshot did not persist")
    return {
        "event_id": event_id,
        "snapshot_hash": snapshot_hash,
        "decision": passport.final_decision,
        "block_at_gate": passport.block_at_gate,
        "causal_chain": list(passport.causal_chain),
    }


def _run_provider(root: Path, provider: str, model_id: str, timeout: float) -> Dict[str, Any]:
    from ats.llm.backend_factory import build_backend_factory
    from ats.llm.control_thread import LLMControlThread
    from ats.llm.interaction_journal import recent_agent_interactions
    from ats.llm.learning_snapshot_store import snapshot_store_recent
    from ats.llm.llm_worker import LLMWorkerProcess
    from ats.llm.provider_preflight import inspect_provider_preflight
    from ats.llm.request_producer import LiveSnapshotRequestProducer
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

    root.mkdir(parents=True, exist_ok=False)
    _write_run_configuration(root, provider, model_id)
    config = IPODecisionConfigSnapshot.from_yaml(str(root / "config" / "ipo_sentiment.yaml"))
    field_count = _seed_synthetic_observations(root, config)
    gate = _record_gate_snapshot(root, config)
    snapshots = snapshot_store_recent(root, limit=10)
    if not snapshots:
        raise RuntimeError("synthetic decision snapshot is not readable")

    authorization = _simulation_authorization()
    preflight = inspect_provider_preflight(
        root / "config" / "llm_config.yaml", authorization=authorization,
    )
    if preflight.get("execution_allowed") is not True or preflight.get("state") != "READY":
        blockers = [item for item in preflight.get("checks", []) if item.get("status") not in {"通过", "已配置"}]
        raise RuntimeError("simulation preflight blocked: " + "; ".join(
            f"{row.get('name')}={row.get('status')}" for row in blockers[:6]
        ))
    backend_factory = build_backend_factory(
        root / "config" / "llm_config.yaml", authorization=authorization,
    )
    worker = LLMWorkerProcess(backend_factory, request_timeout_seconds=30.0)
    control = LLMControlThread(
        root=root, worker=worker, provider_preflight=preflight,
        authorization=authorization,
        request_producer=LiveSnapshotRequestProducer(root),
        simulation_only=True,
    )
    control.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = control.snapshot()
        if current.get("ok_results", 0) + current.get("failed_results", 0) > 0:
            break
        producer = current.get("request_producer", {})
        if producer.get("state") == "BLOCKED" and producer.get("rejected", 0) > 0:
            break
        time.sleep(0.2)
    control.stop()
    control.join(timeout=4.0)
    if control.is_alive():
        raise RuntimeError("simulation control thread did not stop within four seconds")

    interaction_rows = []
    journal = control.snapshot().get("journal", {})
    journal_deadline = time.monotonic() + 5.0
    while time.monotonic() < journal_deadline:
        interaction_rows = recent_agent_interactions(root, limit=10)
        if interaction_rows or not journal.get("queued", 0):
            break
        time.sleep(0.1)
    result = control.snapshot()
    last = result.get("last_result", {})
    status = last.get("status", "NO_RESULT")
    summary = last.get("summary", "")
    manifest = {
        "schema_version": "ipo-llm-simulation.v1",
        "simulation_only": True,
        "production_qualified": False,
        "real_trading_enabled": False,
        "real_data_used": False,
        "synthetic_ticker": SIMULATED_TICKER,
        "provider": provider,
        "model_id": model_id,
        "result_status": status,
        "result_summary": summary[:300],
        "synthetic_fields_persisted": field_count,
        "gate": gate,
        "request_producer": result.get("request_producer", {}),
        "worker": {
            "submitted": result.get("submitted_requests", 0),
            "succeeded": result.get("ok_results", 0),
            "failed": result.get("failed_results", 0),
            "qualified": False,
        },
        "interaction_journal_rows": len(interaction_rows),
        "remote_policy_note": "仿真字段 allowlist；destination 为标记值，未形成 OS 网络出口控制证明。",
        "runtime_acceptance_note": "SIMULATION_ONLY 夹具仅用于本合成测试，不得复制到实盘配置。",
        "run_id": root.name,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_json(root / "simulation_manifest.json", manifest)
    return manifest


def _default_model(provider: str) -> str:
    return "gemini-3.8-flash-medium" if provider == "antigravity_cli" else "gpt-6-luna"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行新股情绪系统合成数据与 CLI LLM 闭环测试")
    parser.add_argument(
        "--provider", choices=("both", "antigravity_cli", "codex_cli"), default="both",
        help="both 依次运行 Antigravity 主链与 Codex Luna 备用链",
    )
    parser.add_argument("--timeout", type=float, default=40.0, help="每个 Provider 最长等待秒数（10–60）")
    args = parser.parse_args()
    timeout = max(10.0, min(float(args.timeout), 60.0))
    selected = (
        ["antigravity_cli", "codex_cli"] if args.provider == "both" else [args.provider]
    )
    SIMULATION_ROOT.mkdir(parents=True, exist_ok=True)
    failures = 0
    for provider in selected:
        model_id = _default_model(provider)
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}-{provider}"
        root = SIMULATION_ROOT / run_id
        print(f"[START] {provider} / {model_id} / {root}", flush=True)
        try:
            manifest = _run_provider(root, provider, model_id, timeout)
            print(json.dumps(manifest, ensure_ascii=False, sort_keys=True), flush=True)
            if manifest["result_status"] != "OK" or manifest["interaction_journal_rows"] != 1:
                failures += 1
        except Exception as exc:
            failures += 1
            error_manifest = {
                "schema_version": "ipo-llm-simulation.v1", "simulation_only": True,
                "production_qualified": False, "real_trading_enabled": False,
                "provider": provider, "model_id": model_id,
                "result_status": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                "run_id": run_id,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            if root.is_dir():
                _write_json(root / "simulation_manifest.json", error_manifest)
            print(json.dumps(error_manifest, ensure_ascii=False, sort_keys=True), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())

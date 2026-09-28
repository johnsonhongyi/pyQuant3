# -*- coding: utf-8 -*-
"""Run an isolated synthetic IPO → Gate → CLI LLM → journal smoke workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Mapping
from zoneinfo import ZoneInfo

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
SIMULATION_ROOT = APP_ROOT / "data" / "ipo_learning_simulation"
SIMULATED_TICKER = "999999"
SIMULATION_ACCEPTANCE_ID = "SIMULATION_ONLY"
REMOTE_FIELDS = ["snapshot_hash", "ticker", "cutoff", "rule_decision", "input_snapshot"]


def _synthetic_value(field_id: str, value_type: str) -> Any:
    if value_type == "integer":
        return 1 if field_id == "scarcity_rank" else 0
    if value_type == "any":
        return ["模拟热点", "合成样本"]
    known = {
        "issue_price": 10.0, "float_shares_wan": 1200.0,
        "current_price": 10.2, "session_low": 9.8, "session_high": 10.3,
        "pe_ratio": 22.0, "industry_pe_median": 28.0,
        "online_sub_multiple": 32.0, "winning_rate_pct": 1.0,
        "advance_decline_ratio": 1.1, "price_vwap_dist_pct": 1.0,
        "ret_pct": 8.0, "turnover_pct": 25.0, "open_premium_pct": 5.0,
        "slope_deg": 20.0, "turnover_climb_speed": 0.2,
        "minutes_above_vwap_ratio": 0.5, "pullback_from_peak_pct": 3.0,
        "halt_count": 0,
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
    config["version"] = "synthetic-only-v1"
    config["decision_config"]["implementation_status"] = "SIMULATION_ONLY"
    config["decision_config"]["trade_gate"]["signal_max_age_seconds"] = 86_400.0
    config["decision_config"]["trade_gate"]["allowed_actions"] = ["WATCH", "BUY"]
    from ats.strategy.ipo_data_contracts import IPODataContractSet, build_decision_config_hash

    contract = IPODataContractSet.from_mapping(config["data_contract"])
    config["decision_config_hash"] = build_decision_config_hash(
        config["version"], config["decision_config"], contract,
    )
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
        fallback_scratch = root / "scratch" / "codex"
        fallback_scratch.mkdir(parents=True, exist_ok=True)
        other_backend = {
            "execution_mode": "remote_api", "enabled": True,
            "bin_path": "codex", "model_id": "gpt-6-luna",
            "scratch_cwd": str(fallback_scratch.resolve()),
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
            "fallback_backend": "codex_cli" if provider == "antigravity_cli" else None,
            "request_timeout_seconds": 60.0 if provider == "antigravity_cli" else 30.0,
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
    from ats.strategy.ipo_data_contracts import LRRM_REQUIRED_FIELDS, REGIME_REQUIRED_FIELDS
    from ats.strategy.ipo_regime_fsm import IPORegimeFSM
    from ats.strategy.lrrm_engine import LRRMEngine
    from ats.strategy.t1_carry_evaluator import T1CarryEvaluator
    from ats.strategy.listing_anchor_store import ListingAnchorStore, ListingAnchors
    from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan, TAG_IPO_VWAP_STABLE
    from ats.strategy.gate_orchestrator import RiskGateContext
    from ats.vwap_factory import VWAPFactory
    from trading_kernel.core.intent import DecisionIntent, DecisionReason
    from trading_kernel.core.signal import StrategySignal
    from trading_kernel.engine.risk_gate import RiskLimits

    market_time = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=10, minute=30, second=0, microsecond=0,
    )
    listing_date = (market_time.date() - timedelta(days=1)).isoformat()
    anchor_time = (market_time - timedelta(days=1)).replace(
        hour=15, minute=0, second=0, microsecond=0,
    )
    ListingAnchorStore(root / "config" / "listing_anchors.json").freeze(ListingAnchors(
        code=SIMULATED_TICKER, listing_date=listing_date,
        listing_open=10.0, listing_high=10.2, listing_low=9.7,
        listing_close=10.1, listing_vwap=10.0, listing_anchored_vwap=10.0,
        first_30m_vwap=10.0, close_location=0.8, first_day_turnover=35.0,
        source_id="simulation.fixture", source_version="synthetic-only-v1",
        source_timezone="Asia/Shanghai", as_of_time=anchor_time.isoformat(),
        available_at=anchor_time.isoformat(), configuration_hash=config.config_hash,
        data_contract_hash=config.data_contract.config_hash,
    ))

    # Use a throwaway singleton so the test cannot inherit or mutate ATS VWAP state.
    with VWAPFactory._instance_lock:
        previous_vwap_factory = VWAPFactory._instance
        VWAPFactory._instance = VWAPFactory()
    try:
        vwap_factory = VWAPFactory.get_instance()
        vwap_factory.update_bar(SIMULATED_TICKER, {
            "date": listing_date, "time_only": "15:00", "bar_amt": 1_000_000,
            "bar_vol": 100_000, "close": 10.0,
        })
        vwap_factory.update_bar(SIMULATED_TICKER, {
            "date": market_time.date().isoformat(), "time_only": market_time.strftime("%H:%M"),
            "bar_amt": 1_020_000, "bar_vol": 100_000, "close": 10.2,
        })
        provider = IPOGateContextProvider(root)
        if not provider.refresh(config):
            raise RuntimeError("synthetic SQLite observations did not refresh")
        context = provider(SimpleNamespace(code=SIMULATED_TICKER, name="合成样本"))
    finally:
        with VWAPFactory._instance_lock:
            VWAPFactory._instance = previous_vwap_factory

    data_observations = {
        field_id: {
            **observation,
            "as_of_time": market_time.isoformat(),
            "available_at": market_time.isoformat(),
        }
        for field_id, observation in context["data_observations"].items()
    }
    lrrm = LRRMEngine(LRRM_REQUIRED_FIELDS).evaluate(
        market_amount_yi=30_000.0, amount_history_20d=[20_000.0] * 20,
        up_count=4_000, down_count=1_500, limit_up_count=80,
        limit_down_count=5,
        required_input_health={field: True for field in LRRM_REQUIRED_FIELDS},
        as_of=market_time,
    )
    ipo_regime = IPORegimeFSM(REGIME_REQUIRED_FIELDS).update(
        recent_ipos=[
            {
                "d1_return_pct": 3.0 if index < 6 else -1.0,
                "is_first_day_peak": False,
                "made_new_high": index < 5,
                "first_day_turnover": 35.0,
            }
            for index in range(10)
        ],
        required_metric_health={field: True for field in REGIME_REQUIRED_FIELDS},
        lrrm=lrrm, as_of=market_time,
    )
    t1_carry = T1CarryEvaluator().evaluate(
        SIMULATED_TICKER, context["live_heat"], ipo_regime=ipo_regime, lrrm=lrrm,
    )
    trade_plan = IPOTradePlan(
        code=SIMULATED_TICKER, name="合成样本", strategy_tag=TAG_IPO_VWAP_STABLE,
        trigger_price=10.2, buy_zone_min=10.0, buy_zone_max=10.35,
        higher_low_stop=9.5, base_low_invalid=9.4,
        target_1_channel_mid=12.2, target_2_swing_high=12.5,
        suggested_action="BUY_SCOUT", position_pct=20.0,
    )
    reason = DecisionReason(
        regime=ipo_regime.state, setup="SYNTHETIC_SMOKE", sector_heat=0.0,
        sector_rank=1, is_leader=True, breakout=True, volume_ratio=1.0,
        dff=0.0, dff_positive=True, price_above_vwap=True, confidence_inputs=(),
    )
    signal_ts = market_time.isoformat(timespec="seconds")
    intent = DecisionIntent(
        code=SIMULATED_TICKER, action="BUY", size_pct=0.2,
        stop_price=trade_plan.structural_stop, confidence=0.9, reason=reason,
        expires_at=(market_time + timedelta(seconds=10)).isoformat(),
    )
    signal = StrategySignal(
        code=SIMULATED_TICKER, name="合成样本", ts=signal_ts,
        source="SIMULATION_ONLY", signal_type="IPO_SMOKE", price=10.2,
        features={"volume": 100.0, "pct_diff": 2.0, "request_id": f"sim-{uuid.uuid4().hex}"},
    )
    risk_context = RiskGateContext(
        intent=intent, signal=signal, state="FLAT",
        limits=RiskLimits(max_single_size_pct=0.2, min_confidence=0.55),
        held_codes={}, current_stock_exposure=0.0, current_sector_exposure=0.0,
        current_total_exposure=0.0, today_pnl_loss=0.0, consecutive_losses=0,
        current_time=signal_ts,
    )
    passport = GateOrchestrator().evaluate(
        code=SIMULATED_TICKER, name="合成样本",
        lrrm=lrrm, ipo_regime=ipo_regime, t1_carry=t1_carry,
        listing_anchors=context["listing_anchors"],
        vwap=context["vwap"], current_price=10.2, intraday_low=9.8,
        listing_age_sessions=2, horse_rank=1,
        market_as_of_time=market_time,
        max_vwap_stale_seconds=int(context["max_vwap_stale_seconds"]),
        trade_plan=trade_plan, risk_context=risk_context,
        requested_position_pct=20.0, preheat=context["preheat"],
        live_heat=context["live_heat"],
        issue_price=context["issue_price"],
        data_contract=context["data_contract"],
        data_observations=data_observations,
        data_contract_hash=context["data_contract_hash"],
        configuration_version=context["configuration_version"],
        configuration_hash=context["configuration_hash"],
        decision_config=context["decision_config"],
    )
    snapshot = passport.learning_input_snapshot
    snapshot_hash = passport.learning_input_snapshot_hash
    if (
        not passport.gate0_lrrm_passed or not passport.gate1_regime_passed
        or not passport.preheat_passed or not passport.gate2_t1_carry_passed
        or not passport.gate3_anchor_passed or not passport.gate4_vwap_passed
        or passport.block_at_gate not in {-1, 5}
        or passport.diagnostics.get("risk", {}).get("status") not in {"APPROVED", "BLOCKED"}
        or not snapshot or not snapshot_hash
    ):
        raise RuntimeError(
            "synthetic Gate did not complete the six-gate RiskGate path: "
            + "; ".join(passport.causal_chain[-3:])
        )
    event_id = f"simulation:{uuid.uuid4().hex}"
    saved = record_decision_snapshot(
        root, ticker=SIMULATED_TICKER, event_id=event_id,
        decision=passport.final_decision, configuration_version=config.config_version,
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
        "gate_passes": {
            "gate0_lrrm": passport.gate0_lrrm_passed,
            "gate1_regime": passport.gate1_regime_passed,
            "preheat": passport.preheat_passed,
            "gate2_t1_carry": passport.gate2_t1_carry_passed,
            "gate3_dual_anchor": passport.gate3_anchor_passed,
            "gate4_vwap": passport.gate4_vwap_passed,
            "gate5_riskgate": passport.gate5_tde_passed,
        },
        "risk_status": passport.diagnostics.get("risk", {}).get("status", "UNREADY"),
        "risk_gate_evaluated": passport.diagnostics.get("risk", {}).get("status") in {"APPROVED", "BLOCKED"},
        "approved_order_in_memory": passport.approved_order is not None,
        "order_submitted": False,
        "market_as_of_time": market_time.isoformat(timespec="seconds"),
    }


def _run_provider(root: Path, provider: str, model_id: str, timeout: float) -> Dict[str, Any]:
    from ats.llm.backend_factory import build_backend_factory
    from ats.llm.control_thread import LLMControlThread
    from ats.llm.interaction_journal import (
        recent_agent_interactions, shutdown_interaction_writers,
    )
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
    worker_timeout = 60.0 if provider == "antigravity_cli" else 30.0
    worker = LLMWorkerProcess(backend_factory, request_timeout_seconds=worker_timeout)
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
    if not shutdown_interaction_writers(timeout_seconds=5.0):
        raise RuntimeError("simulation interaction journal did not flush before shutdown")

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
        "provider_used": last.get("provider_id", ""),
        "model_id_used": last.get("model_id", ""),
        "fallback_error_code": last.get("fallback_error_code", ""),
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
        "provider_error_code": (
            str(interaction_rows[0].get("error_code", ""))[:120]
            if interaction_rows else ""
        ),
        "remote_policy_note": "仿真字段 allowlist；destination 为标记值，未形成 OS 网络出口控制证明。",
        "runtime_acceptance_note": "SIMULATION_ONLY 夹具仅用于本合成测试，不得复制到实盘配置。",
        "simulation_execution_note": "Gate/RiskGate 仅生成内存中的模拟批准对象；未调用券商或交易下单适配器。",
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
    parser.add_argument("--timeout", type=float, default=60.0, help="每条仿真链最长等待秒数（10–60）")
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

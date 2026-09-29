# -*- coding: utf-8 -*-
"""Run an offline synthetic IPO → Gate → local worker → journal smoke workflow."""

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
SIMULATION_PROVIDER = "offline_simulation"
SIMULATION_ACCEPTANCE_ID = "SIMULATION_ONLY_LOCAL_BACKEND"


def _synthetic_market_time() -> datetime:
    """Use the real point-in-time clock; tests inject only the session predicate."""
    return datetime.now(ZoneInfo("Asia/Shanghai"))


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
        "advance_decline_ratio": 0.72,
        "volume_percentile_20d": 0.65, "volume_percentile_60d": 0.62,
        "close_position": 0.8, "d1_d2_max_drawdown": -5.0,
        "d1_positive_rate": 60.0, "d1_top_rate": 50.0,
        "d2_positive_rate": 55.0, "d3_positive_rate": 52.0,
        "limit_down_rate": 5.0, "new_stock_relative_strength": 3.0,
        "new_stock_turnover_median": 35.0, "new_stock_innovation_high_rate": 50.0,
        "price_vwap_dist_pct": 1.0,
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


class _OfflineSimulationBackend:
    """Deterministic local backend; it has no CLI, network, or tool interfaces."""

    provider_id = SIMULATION_PROVIDER

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def generate_request(self, request: Mapping[str, Any], schema: Mapping[str, Any], timeout_seconds: float) -> Dict[str, Any]:
        del request, schema, timeout_seconds
        return {
            "status": "OK",
            "proposal": {
                "sentiment_score": 50.0,
                "stage_hint": "NEUTRAL",
                "catalysts": [],
                "risk_warnings": [],
            },
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


class _OfflineSimulationBackendFactory:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def __call__(self) -> _OfflineSimulationBackend:
        return _OfflineSimulationBackend(self.model_id)


def _write_run_configuration(root: Path, provider: str, model_id: str) -> None:
    if provider != SIMULATION_PROVIDER:
        raise ValueError("IPO smoke runner only supports the deterministic offline backend")
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

    document = {
        "version": "simulation-only-v1",
        "llm_settings": {
            "active_backend": provider, "allow_remote": False,
            "fallback_backend": None,
            "request_timeout_seconds": 30.0,
        },
        "backends": {
            provider: {
                "execution_mode": "synthetic_local", "enabled": True,
                "model_id": model_id,
            },
        },
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
            "evidence": [f"SIMULATION_ONLY_LOCAL_FIXTURE:{provider}:stage{index}"],
        }
        for index in range(3)
    }
    _write_json(root / "config" / "ipo_stage_acceptance.json", {
        "simulation_only": True, "stages": stages,
    })


def _seed_synthetic_observations(root: Path, config: Any) -> int:
    from ats.strategy.ipo_source_orchestrator import store_observation
    from ats.strategy.ipo_data_contracts import REGIME_REQUIRED_FIELDS

    # Persist observations at the real collection time so the source contract's
    # future timestamp guard remains active in this simulation fixture.
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
        if field_id in REGIME_REQUIRED_FIELDS:
            observation.update(sample_count=10, cohort_id="simulation-cohort-v1")
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
    from ats.strategy.listing_anchor_store import ListingAnchorStore, ListingAnchors
    from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan, TAG_IPO_VWAP_STABLE
    from ats.strategy.gate_orchestrator import RiskGateContext
    from ats.vwap_factory import VWAPFactory
    from trading_kernel.core.intent import DecisionIntent, DecisionReason
    from trading_kernel.core.signal import StrategySignal
    from trading_kernel.engine.risk_gate import RiskLimits
    from trading_kernel.engine import risk_gate

    market_time = _synthetic_market_time()
    session_dates = [market_time.date()]
    cursor = market_time.date() - timedelta(days=1)
    while len(session_dates) < 10:
        if cursor.weekday() < 5:
            session_dates.append(cursor)
        cursor -= timedelta(days=1)
    session_dates.reverse()
    listing_date = session_dates[0].isoformat()
    anchor_time = datetime.fromisoformat(f"{listing_date}T15:00:00+08:00")
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
        for index, session_date in enumerate(session_dates[:-1]):
            vwap_factory.update_bar(SIMULATED_TICKER, {
                "date": session_date.isoformat(), "time_only": "15:00",
                "bar_amt": 1_000_000, "bar_vol": 100_000,
                "close": 9.8 + index * 0.03,
            })
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
    readiness = context.get("gate_context_readiness", {})
    if (
        readiness.get("validated_field_count") != 41
        or readiness.get("unready_field_count") != 0
    ):
        raise RuntimeError("synthetic Gate context did not validate all 41 contract fields")
    lrrm = context["lrrm"]
    ipo_regime = context["ipo_regime"]
    t1_carry = context["t1_carry"]
    if not all(getattr(item, "data_ready", False) for item in (lrrm, ipo_regime, t1_carry)):
        raise RuntimeError("41-field inputs did not produce ready LRRM/Regime/T1 Carry contexts")
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
    previous_anchor_store_path = ListingAnchorStore.STORE_PATH
    previous_session_check = risk_gate._is_trading_hour
    ListingAnchorStore.STORE_PATH = root / "config" / "listing_anchors.json"
    try:
        # This offline-only runner emulates an active session so Gate 5 can
        # validate the positive path at any wall-clock time. It never enables
        # a broker adapter or changes production trading-hour policy.
        risk_gate._is_trading_hour = lambda _signal_ts: True
        passport = GateOrchestrator().evaluate(
            code=SIMULATED_TICKER, name="合成样本",
            lrrm=lrrm, ipo_regime=ipo_regime, t1_carry=t1_carry,
            listing_anchors=context["listing_anchors"],
            vwap=context["vwap"], current_price=10.2, intraday_low=9.8,
            listing_age_sessions=10, horse_rank=1,
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
    finally:
        risk_gate._is_trading_hour = previous_session_check
        ListingAnchorStore.STORE_PATH = previous_anchor_store_path
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
        "session_policy": "SIMULATION_ONLY_ACTIVE_SESSION_EMULATED",
        "market_as_of_time": market_time.isoformat(timespec="seconds"),
    }


def _run_provider(root: Path, provider: str, model_id: str, timeout: float) -> Dict[str, Any]:
    from ats.llm.interaction_journal import (
        recent_agent_interactions, record_agent_interaction,
        shutdown_interaction_writers,
    )
    from ats.llm.learning_snapshot_store import snapshot_store_recent
    from ats.llm.llm_worker import LLMWorkerProcess
    from ats.llm.request_producer import LiveSnapshotRequestProducer
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

    if provider != SIMULATION_PROVIDER:
        raise ValueError("IPO smoke runner only supports the deterministic offline backend")
    root.mkdir(parents=True, exist_ok=False)
    _write_run_configuration(root, provider, model_id)
    config = IPODecisionConfigSnapshot.from_yaml(str(root / "config" / "ipo_sentiment.yaml"))
    field_count = _seed_synthetic_observations(root, config)
    gate = _record_gate_snapshot(root, config)
    snapshots = snapshot_store_recent(root, limit=10)
    if not snapshots:
        raise RuntimeError("synthetic decision snapshot is not readable")

    worker = LLMWorkerProcess(
        _OfflineSimulationBackendFactory(model_id), request_timeout_seconds=30.0,
    )
    local_preflight = {
        "backend": SIMULATION_PROVIDER, "execution_allowed": True, "state": "READY",
    }
    local_acceptance = {
        "stage0_accepted": True,
        "provider_accepted": True,
        "process_tree_isolation_accepted": True,
        "acceptance_id": SIMULATION_ACCEPTANCE_ID,
    }
    if not worker.start(provider_preflight=local_preflight, authorization=local_acceptance):
        raise RuntimeError("local simulation Worker could not start: " + worker.snapshot().get("last_error", ""))

    producer = LiveSnapshotRequestProducer(root)
    producer_report: Dict[str, Any] = {}
    worker_results = []
    journal_flushed = False
    try:
        deadline = time.monotonic() + max(10.0, min(float(timeout), 60.0))
        while time.monotonic() < deadline and worker.snapshot().get("state") != "READY":
            worker.poll_results()
            state = worker.snapshot()
            if state.get("state") in {"UNAVAILABLE", "DISABLED"}:
                raise RuntimeError("local simulation Worker unavailable: " + state.get("last_error", ""))
            time.sleep(0.05)
        if worker.snapshot().get("state") != "READY":
            raise TimeoutError("local simulation Worker did not become ready")

        producer_report = producer.poll(runtime_accepting=True)
        requests = producer_report.get("requests", [])
        if producer_report.get("state") != "REQUESTS_READY" or len(requests) != 1:
            raise RuntimeError("offline request producer did not yield one fresh request")
        if not worker.submit(requests[0]):
            producer.acknowledge(requests[0]["request_id"], accepted=False)
            raise RuntimeError("local simulation Worker rejected the validated request")

        while time.monotonic() < deadline and not worker_results:
            worker_results.extend(worker.poll_results())
            state = worker.snapshot()
            if state.get("state") in {"UNAVAILABLE", "DISABLED"}:
                raise RuntimeError("local simulation Worker failed: " + state.get("last_error", ""))
            if not worker_results:
                time.sleep(0.05)
        if len(worker_results) != 1:
            raise TimeoutError("local simulation Worker did not return one result")
        response = worker_results[0]
        generated_count = producer.acknowledge(
            response["request_id"], accepted=response.get("status") == "OK",
        )
        producer_report["generated"] = generated_count
        if not record_agent_interaction(
            root, response, datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ):
            raise RuntimeError("local simulation result was rejected by the interaction journal")
    finally:
        worker.shutdown(timeout_seconds=2.0)
        journal_flushed = shutdown_interaction_writers(timeout_seconds=5.0)
    if not journal_flushed:
        raise RuntimeError("local simulation interaction journal did not flush before shutdown")

    interaction_rows = recent_agent_interactions(root, limit=10)
    response = worker_results[0]
    envelope = response.get("envelope") or {}
    payload = envelope.get("payload") if isinstance(envelope, Mapping) else {}
    payload = payload if isinstance(payload, Mapping) else {}
    status = response.get("status", "NO_RESULT")
    summary = f"{payload.get('stage_hint', '')} sentiment={payload.get('sentiment_score', '')}"
    worker_state = worker.snapshot()
    request_summaries = []
    for request in producer_report.get("requests", []):
        context = request.get("context", {})
        snapshot = context.get("input_snapshot", {}) if isinstance(context, Mapping) else {}
        features = snapshot.get("features", {}) if isinstance(snapshot, Mapping) else {}
        request_summaries.append({
            "request_id": request.get("request_id", ""),
            "agent_type": request.get("agent_type", ""),
            "ticker": request.get("ticker", ""),
            "as_of_time": request.get("as_of_time", ""),
            "snapshot_hash": context.get("snapshot_hash", "") if isinstance(context, Mapping) else "",
            "validated_field_count": len(features) if isinstance(features, Mapping) else 0,
            "schema_hash": request.get("schema_hash", ""),
        })
    producer_summary = {
        key: value for key, value in producer_report.items() if key != "requests"
    }
    producer_summary.update(
        request_count=len(request_summaries), request_summaries=request_summaries,
    )
    manifest = {
        "schema_version": "ipo-llm-simulation.v1",
        "simulation_only": True,
        "production_qualified": False,
        "real_trading_enabled": False,
        "real_data_used": False,
        "synthetic_ticker": SIMULATED_TICKER,
        "provider": SIMULATION_PROVIDER,
        "model_id": model_id,
        "provider_used": response.get("provider_id", ""),
        "model_id_used": response.get("model_id", ""),
        "fallback_error_code": response.get("fallback_error_code", ""),
        "result_status": status,
        "result_summary": summary[:300],
        "synthetic_fields_persisted": field_count,
        "gate": gate,
        "request_producer": producer_summary,
        "worker": {
            "submitted": 1,
            "succeeded": int(status == "OK"),
            "failed": int(status != "OK"),
            "state": worker_state.get("state", ""),
            "qualified": False,
        },
        "interaction_journal_rows": len(interaction_rows),
        "provider_error_code": (
            str(interaction_rows[0].get("error_code", ""))[:120]
            if interaction_rows else ""
        ),
        "remote_policy_note": "本地确定性后端；未配置远端 Provider、网络出口或工具调用。",
        "runtime_acceptance_note": "未生成 runtime acceptance；本地测试准入不代表生产授权。",
        "simulation_execution_note": "Gate/RiskGate 仅生成内存中的模拟批准对象；未调用券商或交易下单适配器。",
        "risk_gate_session_policy": gate.get("session_policy", "UNSPECIFIED"),
        "run_id": root.name,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_json(root / "simulation_manifest.json", manifest)
    return manifest


def _default_model(provider: str) -> str:
    return "offline-synthetic-v1" if provider == SIMULATION_PROVIDER else "gpt-6-luna"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行新股情绪系统本地离线合成闭环测试")
    parser.add_argument(
        "--provider", choices=(SIMULATION_PROVIDER,), default=SIMULATION_PROVIDER,
        help="仅运行无网络、无 CLI 的确定性本地模拟后端",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="每条仿真链最长等待秒数（10–60）")
    args = parser.parse_args()
    timeout = max(10.0, min(float(args.timeout), 60.0))
    selected = [args.provider]
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

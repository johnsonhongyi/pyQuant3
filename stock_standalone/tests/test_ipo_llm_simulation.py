from __future__ import annotations

import json
import yaml
import pytest

from ats.llm.control_thread import LLMControlThread
from ats.llm.learning_snapshot_store import get_snapshot_record, snapshot_store_recent
from ats.llm.llm_worker import LLMWorkerProcess
from ats.llm.offline_learning import validate_input_snapshot
from ats.llm.request_producer import LiveSnapshotRequestProducer
from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from tools.run_ipo_llm_simulation import (
    _default_model,
    _record_gate_snapshot,
    _seed_synthetic_observations,
    _write_run_configuration,
)


def test_synthetic_gate_snapshot_becomes_a_valid_read_only_request(tmp_path, monkeypatch):
    from trading_kernel.engine import risk_gate

    monkeypatch.setattr(risk_gate, "_is_trading_hour", lambda _signal_ts: True)
    root = tmp_path / "simulation"
    root.mkdir()
    provider = "offline_simulation"
    _write_run_configuration(root, provider, _default_model(provider))
    llm_config = yaml.safe_load(
        (root / "config" / "llm_config.yaml").read_text(encoding="utf-8")
    )
    assert llm_config["llm_settings"]["allow_remote"] is False
    assert set(llm_config["backends"]) == {"offline_simulation"}
    assert not (root / "config" / "llm_runtime_acceptance.json").exists()
    config = IPODecisionConfigSnapshot.from_yaml(
        str(root / "config" / "ipo_sentiment.yaml")
    )

    assert _seed_synthetic_observations(root, config) == 41
    gate = _record_gate_snapshot(root, config)
    assert gate["decision"] == "ENTRY"
    assert gate["block_at_gate"] == -1
    assert all(gate["gate_passes"][name] for name in (
        "gate0_lrrm", "gate1_regime", "preheat", "gate2_t1_carry",
        "gate3_dual_anchor", "gate4_vwap", "gate5_riskgate",
    ))
    gate4_reason = next(item for item in gate["causal_chain"] if item.startswith("Gate 4 放行"))
    assert "上市日龄适用结构校验通过" in gate4_reason
    assert gate["risk_status"] == "APPROVED"
    assert gate["risk_gate_evaluated"] is True
    assert gate["approved_order_in_memory"] is True
    assert gate["order_submitted"] is False

    records = snapshot_store_recent(root, limit=1)
    assert len(records) == 1
    record = get_snapshot_record(root, records[0]["snapshot_id"])
    assert record is not None
    snapshot = validate_input_snapshot(record["input_snapshot"], config)
    assert len(snapshot["features"]) == 41
    assert all(
        feature["source_timezone"] == config.data_contract.fields[field_id].source_timezone
        for field_id, feature in snapshot["features"].items()
    )

    report = LiveSnapshotRequestProducer(root).poll(runtime_accepting=True)
    assert report["state"] == "REQUESTS_READY"
    assert report["rejected"] == 0
    assert len(report["requests"]) == 1
    request = report["requests"][0]
    assert request["ticker"] == "999999"
    assert request["model_id"] == "offline-synthetic-v1"
    assert set(request["context"]) == {
        "snapshot_hash", "ticker", "cutoff", "rule_decision", "input_snapshot",
    }


def test_simulation_control_status_can_never_be_production_qualified(tmp_path):
    worker = LLMWorkerProcess(lambda: None, request_timeout_seconds=30.0)
    control = LLMControlThread(
        root=tmp_path,
        worker=worker,
        provider_preflight={"backend": "codex_cli", "execution_allowed": True},
        authorization={},
        simulation_only=True,
    )

    control._publish_status(
        {"state": "READY", "heartbeat_healthy": True}, {}, {}
    )
    status_path = tmp_path / "logs" / "llm_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["simulation_only"] is True
    assert status["qualified"] is False


def test_simulation_runner_rejects_remote_provider_before_writing_config(tmp_path):
    root = tmp_path / "remote-provider"
    with pytest.raises(ValueError, match="deterministic offline backend"):
        _write_run_configuration(root, "codex_cli", "gpt-6-luna")
    assert not root.exists()

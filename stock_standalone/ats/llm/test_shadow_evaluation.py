"""Isolated structured-transport and point-in-time shadow evaluation regressions."""

import json
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from ats.llm.agent_contracts import build_agent_envelope, payload_schema, payload_schema_hash
from ats.llm.backend_factory import build_backend_factory
from ats.llm.ollama_backend import OllamaHTTPBackend, local_ollama_url
from ats.llm.offline_learning import compute_input_snapshot_hash
from ats.llm.provider_preflight import inspect_provider_preflight
from ats.llm.shadow_evaluation import collect_shadow_evaluation, evaluate_shadow_records, _report_hash
from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_outcome_labels import build_matured_outcome

APP_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def config():
    return IPODecisionConfigSnapshot.from_yaml(str(APP_ROOT / "config/ipo_sentiment.yaml"))


@pytest.fixture
def records(config):
    from tools.run_ipo_llm_simulation import _synthetic_value

    records = []
    for index in range(8):
        cutoff = datetime(2026, 8, 1, 1, tzinfo=timezone.utc) + timedelta(days=index * 5)
        ticker = f"0000{index:02d}"
        label = bool(index % 2)
        snapshot = {"as_of_time": cutoff.isoformat(), "configuration_hash": config.config_hash,
                    "data_contract_hash": config.data_contract.config_hash, "features": {}}
        for name, field in config.data_contract.fields.items():
            snapshot["features"][name] = {
                "status": "OBSERVED", "value": _synthetic_value(name, field.value_type),
                "source_id": field.source_id, "source_version": field.source_version,
                "source_timezone": field.source_timezone, "as_of_time": cutoff.isoformat(),
                "available_at": cutoff.isoformat(),
            }
        digest = compute_input_snapshot_hash(snapshot)
        sessions = [(cutoff + timedelta(days=i)).date().isoformat() for i in range(1, 4)]
        close = 11.0 if label else 9.0
        matured = cutoff + timedelta(days=3, hours=6)
        outcome = build_matured_outcome(
            ticker=ticker, listing_date=cutoff.date().isoformat(), issue_price=10,
            daily_bars=[{"date": day, "open": close, "high": close + 1, "low": close - 1,
                         "close": close} for day in sessions],
            source_id="fixture.daily", source_version="fixture.v1", source_timezone="Asia/Shanghai",
            as_of_time=matured, available_at=matured + timedelta(minutes=1), trading_sessions=sessions)
        envelope = build_agent_envelope(
            "MARKET_REGIME", {"sentiment_score": 75 if label else 25, "stage_hint": "NEUTRAL",
                              "catalysts": [], "risk_warnings": []},
            request_id=f"shadow-{index}", scope_id=ticker, ticker=ticker,
            as_of_time=cutoff.isoformat(), generated_at=(cutoff + timedelta(seconds=1)).isoformat(),
            model_id="fixture-local", prompt_version="fixture-shadow-v1", evidence_ids=[digest])
        records.append({
            "request_id": f"shadow-{index}", "provider_id": "ollama_http", "envelope": envelope,
            "snapshot": {"ticker": ticker, "cutoff": cutoff.isoformat(), "snapshot_hash": digest,
                         "input_snapshot": snapshot}, "outcome": outcome,
            "review": {"decision": "ACCEPTED", "evidence_hash": outcome["evidence_hash"],
                       "reviewer": "fixture-reviewer",
                       "reviewed_at_utc": (cutoff + timedelta(days=4)).isoformat()},
        })
    return records


def test_shadow_compares_same_forward_cohort_and_never_authorizes_orders(records, config):
    result = evaluate_shadow_records(records, config)
    assert result["state"] == "SHADOW_EVALUATED"
    group = result["groups"][0]
    assert group["prior_count"] == 5 and group["forward_count"] == 3
    assert group["metrics"]["direction_accuracy"] == 1
    assert group["metrics"]["prior_baseline_accuracy"] < 1
    assert result["future_leakage_count"] == 0
    assert result["report_hash"] == _report_hash(result)
    assert result["entry_authorized"] is result["order_submitted"] is result["model_promoted"] is False
    assert result["p95_latency_ms"]["status"] == "NOT_EVALUABLE"


def test_shadow_purges_review_unavailable_at_forward_cutoff(records, config):
    records[4]["review"]["reviewed_at_utc"] = records[5]["snapshot"]["cutoff"]
    result = evaluate_shadow_records(records, config)
    assert result["state"] == "WAITING_MORE_SAMPLES"
    assert result["groups"][0]["purged_count"] == 1
    assert result["groups"][0]["metrics"] == {}


def test_switching_shadow_model_does_not_reuse_journal_request_id(tmp_path, records):
    from ats.llm.request_producer import LiveSnapshotRequestProducer

    producer = LiveSnapshotRequestProducer(tmp_path)
    snapshot = records[0]["snapshot"]
    first = producer._request(snapshot, snapshot["input_snapshot"], snapshot["snapshot_hash"], "model-a")
    second = producer._request(snapshot, snapshot["input_snapshot"], snapshot["snapshot_hash"], "model-b")
    assert first["request_id"] != second["request_id"]


def test_shadow_rejects_late_response_and_keeps_unreviewed_labels_pending(records, config):
    records[0]["envelope"]["metadata"]["generated_at"] = records[0]["outcome"]["matured_at"]
    records[1]["review"] = None
    result = evaluate_shadow_records(records, config)
    assert result["future_leakage_count"] == 1
    assert result["pending_review_count"] == 1
    assert result["evaluated_group_count"] == 0


def test_verified_journal_snapshot_outcome_join_round_trips(tmp_path, records, config, monkeypatch):
    from ats.llm.interaction_journal import record_agent_interaction, shutdown_interaction_writers
    from ats.llm.learning_snapshot_store import record_decision_snapshot, shutdown_snapshot_writers

    (tmp_path / "config").mkdir()
    (tmp_path / "config/ipo_sentiment.yaml").write_bytes((APP_ROOT / "config/ipo_sentiment.yaml").read_bytes())
    directory = tmp_path / "data/ipo_learning/outcome_evidence"
    directory.mkdir(parents=True)
    with sqlite3.connect(directory.parent / "outcome_reviews.sqlite") as connection:
        connection.execute("CREATE TABLE outcome_reviews (evidence_id TEXT, evidence_hash TEXT, decision TEXT, reviewer TEXT, reason TEXT, reviewed_at_utc TEXT)")
        for index, record in enumerate(records):
            snap = record["snapshot"]
            assert record_decision_snapshot(
                tmp_path, ticker=snap["ticker"], event_id=f"fixture-event-{index}", decision="BLOCK",
                configuration_version=config.config_version, snapshot=snap["input_snapshot"],
                snapshot_hash=snap["snapshot_hash"], gate_causal_chain=["fixture:block"],
                standard_proposal={"action": "BLOCK"}, proposal_created_at=snap["cutoff"])
            assert record_agent_interaction(tmp_path, {
                "request_id": record["request_id"], "status": "OK", "envelope": record["envelope"],
                "error_code": "", "provider_id": "ollama_http", "model_id": "fixture-local", "fallback_error_code": "",
            }, datetime.now(timezone.utc).isoformat())
            outcome, review = record["outcome"], record["review"]
            (directory / f"{index}.json").write_text(json.dumps(outcome), encoding="utf-8")
            connection.execute("INSERT INTO outcome_reviews VALUES (?, ?, ?, ?, ?, ?)", (
                outcome["evidence_id"], outcome["evidence_hash"], "ACCEPTED", review["reviewer"],
                "fixture-only", review["reviewed_at_utc"]))
    assert shutdown_snapshot_writers()
    assert shutdown_interaction_writers()
    import ats.llm.interaction_journal as journal_module
    verify = journal_module._verify_journal_chain
    verification_calls = []
    def counted_verify(connection):
        verification_calls.append(1)
        return verify(connection)
    monkeypatch.setattr(journal_module, "_verify_journal_chain", counted_verify)
    result = collect_shadow_evaluation(tmp_path)
    assert result["state"] == "SHADOW_EVALUATED", result
    assert result["interaction_count"] == 8
    assert result["report_hash"] == _report_hash(result)
    assert len(verification_calls) == 1


def test_ollama_native_schema_and_factory_obey_local_authorization(tmp_path):
    document = {"llm_settings": {"active_backend": "ollama_http", "allow_remote": False,
                                  "request_timeout_seconds": 30.0},
                "backends": {"ollama_http": {"base_url": "http://localhost:11434", "model": "fixture-model"}}}
    (tmp_path / "config").mkdir()
    path = tmp_path / "config/llm_config.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    from ats.llm.request_producer import LiveSnapshotRequestProducer
    assert LiveSnapshotRequestProducer(tmp_path)._load_backend()["model_id"] == "fixture-model"
    assert inspect_provider_preflight(path)["execution_allowed"] is False
    with pytest.raises(ValueError, match="acceptance"):
        build_backend_factory(path)
    accepted = {"stage0_accepted": True, "provider_accepted": True,
                "process_tree_isolation_accepted": True, "acceptance_id": "fixture-local-acceptance"}
    assert inspect_provider_preflight(path, accepted)["execution_allowed"] is False
    from ats.llm.ollama_backend import ollama_binding_hash
    binding = ollama_binding_hash("http://localhost:11434", "fixture-model")
    now = datetime.now(timezone.utc)
    proof = {"state": "PROBE_PASSED", "operating_mode": "INTERFACE_PROBE", "binding_hash": binding,
             "provider_id": "ollama_http", "model_id": "fixture-model", "native_schema_validated": True,
             "worker_protocol_validated": True, "completed_at": (now - timedelta(seconds=1)).isoformat()}
    evidence = tmp_path / "data/probe.json"
    evidence.parent.mkdir()
    evidence.write_text(json.dumps(proof), encoding="utf-8")
    acceptance = {"status": "ACCEPTED", "acceptance_id": accepted["acceptance_id"], "binding_hash": binding,
                  "reviewer": "fixture-reviewer", "accepted_at": now.isoformat(),
                  "evidence_path": "data/probe.json", "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    path.with_name("ollama_provider_acceptance.json").write_text(json.dumps(acceptance), encoding="utf-8")
    assert inspect_provider_preflight(path, accepted)["execution_allowed"] is True
    factory = build_backend_factory(path, accepted)
    assert factory.model_id == "fixture-model"
    document["backends"]["ollama_http"]["model"] = "another-model"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    assert inspect_provider_preflight(path, accepted)["execution_allowed"] is False
    with pytest.raises(ValueError, match="acceptance"):
        build_backend_factory(path, accepted)
    document["backends"]["ollama_http"]["model"] = "fixture-model"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    backend = factory()
    request = {"request_id": "fixture-request", "agent_type": "MARKET_REGIME", "scope_id": "MARKET",
               "ticker": "", "as_of_time": "2026-08-01T01:00:00+00:00", "prompt": "fixture",
               "context": {"simulation_only": True}, "model_id": "fixture-model",
               "prompt_version": "fixture-v1", "evidence_ids": [],
               "schema_hash": payload_schema_hash("MARKET_REGIME")}
    sent = []

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit):
            return json.dumps({"model": "fixture-model", "done": True, "done_reason": "stop",
                               "response": json.dumps({"sentiment_score": 50, "stage_hint": "NEUTRAL",
                                                       "catalysts": [], "risk_warnings": []})}).encode()

    def open_request(req, timeout):
        sent.append(json.loads(req.data))
        return Response()

    backend._opener.open = open_request
    result = backend.generate_request(request, payload_schema("MARKET_REGIME", evidence_ids=[]), timeout_seconds=30)
    assert result["status"] == "OK"
    assert sent[0]["format"] == payload_schema("MARKET_REGIME", evidence_ids=[])
    assert sent[0]["format"]["properties"]["catalysts"]["maxItems"] == 0
    assert "enum" not in sent[0]["format"]["properties"]["catalysts"]["items"]["properties"]["evidence_ids"]["items"]
    assert sent[0]["stream"] is False
    request["model_id"] = "other-model"
    assert backend.generate_request(request, sent[0]["format"], timeout_seconds=30)["status"] == "UNAVAILABLE"
    assert len(sent) == 1
    backend.close()


def test_shadow_persistence_failure_returns_a_matching_hash(tmp_path, monkeypatch):
    import ats.llm.shadow_evaluation as evaluator

    (tmp_path / "config").mkdir()
    (tmp_path / "config/ipo_sentiment.yaml").write_bytes((APP_ROOT / "config/ipo_sentiment.yaml").read_bytes())
    def deny_replace(*_args):
        raise PermissionError("fixture replacement denied")
    monkeypatch.setattr(evaluator.os, "replace", deny_replace)
    result = evaluator.save_shadow_evaluation(tmp_path)
    assert result["state"] == "PERSISTENCE_FAILED"
    assert result["persisted"] is False
    assert result["report_hash"] == _report_hash(result)
    assert not (tmp_path / "data/ipo_learning/shadow_evaluation.latest.json").exists()
    assert not list((tmp_path / "data/ipo_learning").glob("*.tmp"))


@pytest.mark.parametrize("url", ["https://127.0.0.1:11434", "http://example.com:11434", "http://user@localhost:11434", "http://127.0.0.1:0"])
def test_ollama_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(ValueError):
        local_ollama_url(url)

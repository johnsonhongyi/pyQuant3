# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from ats.llm.offline_learning import (
    OfflineLearningError,
    build_lifecycle_evidence,
    build_offline_datasets,
    compute_input_snapshot_hash,
    evaluate_shadow_readiness,
)
from ats.llm.sealed_dataset_store import SealedDatasetRepository
from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot


APP_ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-10-01T00:00:00+00:00"
CUTOFF = "2026-09-28T01:00:00+00:00"
MATURED_AT = "2026-09-29T07:00:00+00:00"
REVIEWED_AT = "2026-09-29T08:00:00+00:00"


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture(scope="module")
def config_snapshot():
    return IPODecisionConfigSnapshot.from_yaml(
        str(APP_ROOT / "config" / "ipo_sentiment.yaml")
    )


def _candidate(config_snapshot, index: int) -> dict:
    from tools.run_ipo_llm_simulation import _synthetic_value

    cutoff = CUTOFF
    features = {}
    for field_id, contract in config_snapshot.data_contract.fields.items():
        features[field_id] = {
            "status": "OBSERVED",
            "value": _synthetic_value(field_id, contract.value_type),
            "source_id": contract.source_id,
            "source_version": contract.source_version,
            "source_timezone": contract.source_timezone,
            "as_of_time": cutoff,
            "available_at": cutoff,
        }
    snapshot = {
        "as_of_time": cutoff,
        "configuration_hash": config_snapshot.config_hash,
        "data_contract_hash": config_snapshot.data_contract.config_hash,
        "features": features,
    }
    proposal = {"action": "BLOCK", "reason": f"fixture-{index}"}
    preference = {
        "cutoff": cutoff,
        "chosen_proposal": {"action": "BLOCK", "reason": f"chosen-{index}"},
        "rejected_proposal": {"action": "BUY", "reason": f"rejected-{index}"},
        "chosen_reason": "人工偏好：遵守 Gate 阻断",
        "rejected_reason": "人工偏好：拒绝越权放行",
        "reviewer": "offline-fixture-reviewer",
    }
    return {
        "candidate_id": f"candidate-{index}",
        "ticker": f"00000{index + 1}",
        "event_id": f"ipo-event-{index}",
        "listing_date": (date(2026, 9, 20) + timedelta(days=index)).isoformat(),
        "cutoff": cutoff,
        "matured_at": MATURED_AT,
        "labels_mature": True,
        "label_source": "fixture:reviewed-outcome.v1",
        "review_decision": "ACCEPTED",
        "outcome_evidence_ids": [f"outcome:{index + 1:048x}"],
        "reviewed_by": "offline-fixture-reviewer",
        "reviewed_at": REVIEWED_AT,
        "review_draft_hash": f"{index + 1:064x}",
        "input_snapshot": snapshot,
        "input_snapshot_hash": compute_input_snapshot_hash(snapshot),
        "configuration_hash": config_snapshot.config_hash,
        "data_contract_hash": config_snapshot.data_contract.config_hash,
        "standard_proposal": proposal,
        "proposal_created_at": cutoff,
        "standard_proposal_hash": _sha256(proposal),
        "gate_causal_chain": ["fixture:gate0:block", "fixture:no-order"],
        "model_id": "fixture:local-base",
        "prompt_version": "fixture-prompt-v1",
        "preference_pair": preference,
    }


def _write_review_ledger(path: Path, candidates: list[dict]) -> None:
    columns = (
        "candidate_id", "decision", "reviewer", "input_snapshot_hash", "cutoff",
        "label_source", "reviewed_at", "model_id", "prompt_version",
        "review_draft_hash", "outcome_evidence_ids_json", "ticker", "event_id",
        "listing_date", "matured_at", "configuration_hash", "data_contract_hash",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE sample_review_decisions ("
            + ", ".join(f"{column} TEXT NOT NULL" for column in columns)
            + ")"
        )
        for candidate in candidates:
            values = {
                "candidate_id": candidate["candidate_id"],
                "decision": candidate["review_decision"],
                "reviewer": candidate["reviewed_by"],
                "input_snapshot_hash": candidate["input_snapshot_hash"],
                "cutoff": candidate["cutoff"],
                "label_source": candidate["label_source"],
                "reviewed_at": candidate["reviewed_at"],
                "model_id": candidate["model_id"],
                "prompt_version": candidate["prompt_version"],
                "review_draft_hash": candidate["review_draft_hash"],
                "outcome_evidence_ids_json": json.dumps(candidate["outcome_evidence_ids"]),
                "ticker": candidate["ticker"],
                "event_id": candidate["event_id"],
                "listing_date": candidate["listing_date"],
                "matured_at": candidate["matured_at"],
                "configuration_hash": candidate["configuration_hash"],
                "data_contract_hash": candidate["data_contract_hash"],
            }
            connection.execute(
                f"INSERT INTO sample_review_decisions VALUES ({','.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )


def test_reviewed_sft_dpo_dataset_splits_seals_and_round_trips(tmp_path, config_snapshot):
    candidates = [_candidate(config_snapshot, index) for index in range(3)]
    review_db = tmp_path / "review-ledger.sqlite"
    _write_review_ledger(review_db, candidates)

    dataset = build_offline_datasets(
        candidates,
        config_snapshot=config_snapshot,
        generated_at=GENERATED_AT,
        review_db_path=review_db,
    )

    assert dataset["status"] == "READY_FOR_TRAINING"
    assert dataset["sft"]["sample_count"] == 3
    assert dataset["dpo"]["sample_count"] == 3
    for split_name in ("train", "validation", "test"):
        assert dataset["sft"]["split_group_counts"][split_name] == 1
        assert dataset["dpo"]["split_group_counts"][split_name] == 1
    assert dataset["sft"]["splits"]["train"][0]["listing_date"] < dataset["sft"]["splits"]["validation"][0]["listing_date"]
    assert dataset["sft"]["splits"]["validation"][0]["listing_date"] < dataset["sft"]["splits"]["test"][0]["listing_date"]

    repository = SealedDatasetRepository(tmp_path / "sealed")
    sealed = repository.seal(dataset)
    loaded = repository.load(dataset["dataset_hash"])
    assert sealed["status"] == "SEALED"
    assert loaded["dataset_hash"] == dataset["dataset_hash"]
    assert repository.summary()["sample_count"] == 3


def test_training_dataset_fails_closed_without_matching_human_review(tmp_path, config_snapshot):
    candidates = [_candidate(config_snapshot, index) for index in range(3)]
    review_db = tmp_path / "review-ledger.sqlite"
    _write_review_ledger(review_db, candidates)
    candidates[0]["reviewed_by"] = "different-reviewer"
    candidates[0]["preference_pair"]["reviewer"] = "different-reviewer"

    with pytest.raises(OfflineLearningError, match="human review record does not match"):
        build_offline_datasets(
            candidates,
            config_snapshot=config_snapshot,
            generated_at=GENERATED_AT,
            review_db_path=review_db,
        )


def test_training_input_rejects_future_outcomes_and_unreviewed_candidates(config_snapshot):
    candidate = _candidate(config_snapshot, 0)
    candidate["input_snapshot"]["features"]["target_outcome"] = {
        "status": "OBSERVED", "value": 1.0, "source_id": "fixture",
        "source_version": "v1", "source_timezone": "Asia/Shanghai",
        "as_of_time": CUTOFF, "available_at": CUTOFF,
    }
    candidate["input_snapshot_hash"] = compute_input_snapshot_hash(candidate["input_snapshot"])
    with pytest.raises(OfflineLearningError, match="future outcome field is forbidden"):
        from ats.llm.offline_learning import validate_learning_candidate

        validate_learning_candidate(candidate, config_snapshot, GENERATED_AT)

    candidate = _candidate(config_snapshot, 0)
    candidate["review_decision"] = "PENDING"
    with pytest.raises(OfflineLearningError, match="only manually accepted"):
        from ats.llm.offline_learning import validate_learning_candidate

        validate_learning_candidate(candidate, config_snapshot, GENERATED_AT)


def test_shadow_eligibility_is_evidence_bound_and_never_switches_runtime():
    dataset_hash = "a" * 64
    replay_hash = "b" * 64
    metrics = {
        "false_entry_rate": 0.1,
        "miss_rate": 0.1,
        "schema_valid_rate": 1.0,
        "p95_latency_ms": 25.0,
    }
    baseline = {
        "false_entry_rate": 0.2,
        "miss_rate": 0.2,
        "schema_valid_rate": 0.99,
        "p95_latency_ms": 30.0,
    }
    thresholds = {
        "max_false_entry_rate": 0.2,
        "max_miss_rate": 0.2,
        "min_schema_valid_rate": 0.95,
        "max_p95_latency_ms": 300.0,
    }
    shadow = evaluate_shadow_readiness(
        metrics, baseline, thresholds,
        candidate_version="candidate-v1", baseline_version="stable-v1",
        dataset_hash=dataset_hash, replay_report_hash=replay_hash,
    )
    promotion = build_lifecycle_evidence(
        "PROMOTE", candidate_version="candidate-v1", current_version="stable-v1",
        previous_version="previous-v0", reviewer="human-reviewer", reason="offline fixture",
        dataset_hash=dataset_hash, artifact_hash="c" * 64, shadow_report=shadow,
    )
    rollback = build_lifecycle_evidence(
        "ROLLBACK", candidate_version="candidate-v1", current_version="candidate-v1",
        previous_version="stable-v1", reviewer="human-reviewer", reason="rollback fixture",
    )

    assert shadow["status"] == "ELIGIBLE_FOR_MANUAL_PROMOTION"
    assert promotion["action"] == "PROMOTION_APPROVED"
    assert promotion["runtime_switch_required"] is True
    assert rollback["action"] == "ROLLBACK_APPROVED"
    assert rollback["runtime_switch_required"] is True

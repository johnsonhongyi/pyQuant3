from __future__ import annotations

import pandas as pd

from tools.historical_cutoff_replay_engine import (
    HistoricalCutoffReplayEngine,
    ReplaySource,
)
from tools.ipo_replay_effect_metrics import (
    EFFECT_METRIC_DEFINITIONS,
    EFFECT_METRIC_CONTRACT_HASH,
    EFFECT_METRIC_CONTRACT_VERSION,
    compute_effect_metrics,
    make_outcome_evidence,
)


def _observation(index, labels, **prediction):
    cutoff = f"2026-09-28T01:0{index}:00+00:00"
    row = {
        "cutoff_time": cutoff,
        "as_of_time": cutoff,
        "causal_chain": ["rule:gate0:block"],
        **prediction,
    }
    row["outcome_evidence"] = make_outcome_evidence(
        code="301689",
        source_id="labels.reviewed.v1",
        source_version="reviewed-labels-v1",
        source_timezone="Asia/Shanghai",
        evidence_id=f"label:{index}",
        cutoff_time=cutoff,
        matured_at="2026-09-29T07:00:00+00:00",
        published_at="2026-09-29T08:00:00+00:00",
        review_decision="ACCEPTED",
        reviewed_by="reviewer-fixture",
        reviewed_at="2026-09-29T07:30:00+00:00",
        review_evidence_id=f"review:{index}",
        review_record_hash=f"{index + 1:064x}",
        labels=labels,
    )
    return row


def test_metric_contract_computes_all_thirteen_from_matured_outcomes():
    rows = [
        _observation(
            0,
            {
                "next_regime_state": "REPAIR", "d1_return_pct": 10.0,
                "bad_t1": True, "continuation": False, "quick_failure": True,
                "lrrm_transition_stable": True, "anchor_failure": True,
                "pseudo_strength": True, "exhaustion": False,
            },
            decision="BLOCK", predicted_next_regime_state="REPAIR", t1_carry_score=80,
            predicted_lrrm_transition="STABLE", anchor_failure_block=True,
            pseudo_strength_block=True, exhaustion_block=False,
            linear_baseline_decision="ENTRY", regression_case_id="golden-block",
        ),
        _observation(
            1,
            {
                "next_regime_state": "PANIC", "d1_return_pct": -5.0,
                "bad_t1": True, "continuation": True, "quick_failure": False,
                "lrrm_transition_stable": False, "anchor_failure": False,
                "pseudo_strength": False, "exhaustion": False,
            },
            decision="ENTRY", predicted_next_regime_state="PANIC", t1_carry_score=20,
            predicted_lrrm_transition="CHANGE", anchor_failure_block=False,
            pseudo_strength_block=False, exhaustion_block=False,
            linear_baseline_decision="ENTRY", regression_case_id="golden-entry",
        ),
        _observation(
            2,
            {
                "next_regime_state": "NEUTRAL", "d1_return_pct": 1.0,
                "bad_t1": False, "continuation": False, "quick_failure": False,
                "lrrm_transition_stable": True, "anchor_failure": False,
                "pseudo_strength": True, "exhaustion": True,
            },
            decision="BLOCK", predicted_next_regime_state="NEUTRAL", t1_carry_score=50,
            predicted_lrrm_transition="STABLE", anchor_failure_block=False,
            pseudo_strength_block=True, exhaustion_block=True,
            linear_baseline_decision="BLOCK",
        ),
    ]
    stocks = [{
        "summary": {"code": "301689"},
        "cutoff_observations": rows,
    }]
    metrics = compute_effect_metrics(
        stocks,
        cutoff_count=3,
        leakage_count=0,
        timestamp_check_count=3,
        outcome_as_of="2026-09-29T09:00:00+00:00",
        regression_cases=[
            {"case_id": "golden-block", "expected_decision": "BLOCK"},
            {"case_id": "golden-entry", "expected_decision": "BLOCK"},
            {"case_id": "missing-case", "expected_decision": "BLOCK"},
        ],
    )

    assert len(metrics) == len(EFFECT_METRIC_DEFINITIONS) == 13
    assert metrics["regime_transition_accuracy"]["value"] == 1.0
    assert metrics["high_carry_vs_low_carry_spread"]["value"] == 15.0
    assert metrics["bad_t1_filter_rate"]["value"] == 0.5
    assert metrics["continuation_capture_rate"]["value"] == 1.0
    assert metrics["false_entry_rate"]["value"] == 0.0
    assert metrics["future_leakage_count"]["value"] == 0
    assert metrics["explanation_coverage"]["value"] == 1.0
    assert metrics["lrrm_transition_stability"]["value"] == 1.0
    assert metrics["anchor_failure_precision"]["value"] == 1.0
    assert metrics["pseudo_strength_filter_rate"]["value"] == 1.0
    assert metrics["nonlinear_false_entry_reduction"]["value"] == 1.0
    assert metrics["exhaustion_block_precision"]["value"] == 1.0
    assert metrics["regression_case_pass_rate"]["value"] == 1 / 3
    assert metrics["regression_case_pass_rate"]["support"]["missing_case_count"] == 1
    assert all(metric["status"] == "MEASURED" for metric in metrics.values())
    assert all(metric["reason"].startswith(EFFECT_METRIC_CONTRACT_VERSION) for metric in metrics.values())
    assert len(EFFECT_METRIC_CONTRACT_HASH) == 64


def test_outcome_evidence_hash_prevents_silent_label_mutation():
    evidence = make_outcome_evidence(
        code="301689", source_id="labels.reviewed.v1", source_version="v1",
        source_timezone="Asia/Shanghai", evidence_id="label:1",
        cutoff_time="2026-09-28T01:00:00+00:00",
        matured_at="2026-09-29T07:00:00+00:00",
        published_at="2026-09-29T08:00:00+00:00",
        review_decision="ACCEPTED", reviewed_by="reviewer-fixture",
        reviewed_at="2026-09-29T07:30:00+00:00",
        review_evidence_id="review:1", review_record_hash="a" * 64,
        labels={"quick_failure": True},
    )
    row = _observation(0, {"quick_failure": False}, decision="BLOCK")
    row["outcome_evidence"] = {**evidence, "labels": {"quick_failure": False}}
    try:
        compute_effect_metrics(
            [{"summary": {"code": "301689"}, "cutoff_observations": [row]}],
            cutoff_count=1, leakage_count=0, timestamp_check_count=1,
        )
    except ValueError as exc:
        assert "哈希" in str(exc)
    else:
        raise AssertionError("tampered mature outcome label was accepted")


def test_outcome_only_source_is_cut_by_report_as_of_and_joined_after_decision():
    engine = object.__new__(HistoricalCutoffReplayEngine)
    engine.outcome_source = ReplaySource(
        source_id="labels.reviewed.v1",
        source_version="reviewed-labels-v1",
        source_timezone="Asia/Shanghai",
        source_role="outcome",
        access="OUTCOME_ONLY",
        availability_time_keys=("published_at",),
    )
    engine.replay_config = {"outcome_as_of": "2026-09-29T17:00:00+08:00"}
    history = {
        "outcomes": {
            "labels.reviewed.v1": pd.DataFrame([{
                "code": "301689",
                "cutoff_time": "2026-09-28T01:00:00+00:00",
                "matured_at": "2026-09-29T07:00:00+00:00",
                "published_at": "2026-09-29T08:00:00+00:00",
                "evidence_id": "reviewed-label:301689:20260928T0900",
                "review_decision": "ACCEPTED",
                "reviewed_by": "reviewer-fixture",
                "reviewed_at": "2026-09-29T07:30:00+00:00",
                "review_evidence_id": "review:301689:20260928T0900",
                "review_record_hash": "b" * 64,
                "labels": {"quick_failure": True},
            }]),
        },
    }

    evidence = engine._outcome_evidence_by_cutoff(
        history, "301689", ["2026-09-28T09:00:00+08:00"],
    )
    assert list(evidence) == ["2026-09-28T09:00:00+08:00"]
    assert evidence["2026-09-28T09:00:00+08:00"]["labels"] == {"quick_failure": True}

    engine.replay_config["outcome_as_of"] = "2026-09-29T07:30:00+08:00"
    assert engine._outcome_evidence_by_cutoff(
        history, "301689", ["2026-09-28T09:00:00+08:00"],
    ) == {}

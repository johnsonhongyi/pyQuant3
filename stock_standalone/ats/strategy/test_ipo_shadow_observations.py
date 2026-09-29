"""Point-in-time shadow capture must reject information available after cutoff."""

import json
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_shadow_observations import (
    capture_shadow_observation, train_shadow_candidate,
)


def test_shadow_capture_excludes_future_available_fields(tmp_path):
    cutoff = datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)
    context = {
        "configuration_hash": "a" * 64,
        "data_contract_hash": "b" * 64,
        "observation_checks": {"ret_pct": "OBSERVED", "turnover_pct": "OBSERVED"},
        "data_observations": {
            "ret_pct": {
                "status": "OBSERVED", "value": 4.5,
                "source_id": "test", "source_version": "v1",
                "as_of_time": cutoff.isoformat(), "available_at": cutoff.isoformat(),
            },
            "turnover_pct": {
                "status": "OBSERVED", "value": 12.0,
                "source_id": "test", "source_version": "v1",
                "as_of_time": cutoff.isoformat(),
                "available_at": (cutoff + timedelta(seconds=1)).isoformat(),
            },
        },
        "lrrm": SimpleNamespace(liquidity_regime="NORMAL"),
    }
    result = capture_shadow_observation(tmp_path, "301689", context, cutoff=cutoff)
    assert result["state"] == "CAPTURED"
    assert result["observed_field_count"] == 1
    with sqlite3.connect(tmp_path / "data/ipo_learning/shadow_observations.sqlite") as db:
        payload = json.loads(db.execute(
            "SELECT payload_json FROM shadow_observations"
        ).fetchone()[0])
    assert set(payload["fields"]) == {"ret_pct"}
    assert payload["sentiment"]["lrrm"] == "NORMAL"


def test_candidate_training_uses_reviewed_labels_and_stays_inactive(tmp_path):
    source = Path(__file__).resolve().parents[2] / "config/ipo_sentiment.yaml"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "ipo_sentiment.yaml").write_bytes(source.read_bytes())
    config = IPODecisionConfigSnapshot.from_yaml(str(config_dir / "ipo_sentiment.yaml"))
    evidence_dir = tmp_path / "data/ipo_learning/outcome_evidence"
    evidence_dir.mkdir(parents=True)
    review_db = tmp_path / "data/ipo_learning/outcome_reviews.sqlite"
    with sqlite3.connect(review_db) as connection:
        connection.execute("""CREATE TABLE outcome_reviews (
            evidence_id TEXT, evidence_hash TEXT, decision TEXT, reviewer TEXT,
            reason TEXT, reviewed_at_utc TEXT
        )""")
        for index in range(10):
            listing = datetime(2026, 9, 1 + index, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
            ticker = f"30{index:04d}"
            label = bool(index % 2)
            context = {
                "configuration_hash": config.config_hash,
                "data_contract_hash": config.data_contract.config_hash,
                "observation_checks": {"ret_pct": "OBSERVED", "turnover_pct": "OBSERVED"},
                "data_observations": {
                    name: {
                        "status": "OBSERVED", "value": value,
                        "source_id": "test", "source_version": "v1",
                        "as_of_time": listing.isoformat(), "available_at": listing.isoformat(),
                    }
                    for name, value in (("ret_pct", 3.0 if label else -3.0),
                                        ("turnover_pct", float(index + 1)))
                },
            }
            assert capture_shadow_observation(tmp_path, ticker, context, cutoff=listing)["state"] == "CAPTURED"
            evidence = {
                "schema_version": "ipo-outcome-evidence.v1",
                "status": "MATURED_PENDING_REVIEW",
                "review_status": "PENDING_HUMAN_REVIEW",
                "labels_mature": True, "training_eligible": False,
                "ticker": ticker, "listing_date": listing.date().isoformat(),
                "d1_positive": label,
            }
            hashed = {key: value for key, value in evidence.items() if key != "status"}
            digest = hashlib.sha256(json.dumps(
                hashed, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")).hexdigest()
            evidence["evidence_id"] = "outcome:" + digest[:48]
            evidence["evidence_hash"] = digest
            (evidence_dir / f"{ticker}.json").write_text(json.dumps(evidence), encoding="utf-8")
            connection.execute(
                "INSERT INTO outcome_reviews VALUES (?, ?, 'ACCEPTED', 'tester', 'checked', ?)",
                (evidence["evidence_id"], digest, (listing + timedelta(days=4)).isoformat()),
            )
        connection.commit()
    result = train_shadow_candidate(tmp_path)
    assert result["state"] in {"CANDIDATE_READY", "CANDIDATE_BELOW_BASELINE"}
    assert result["sample_count"] == 10
    artifact = json.loads((tmp_path / "data/ipo_learning/shadow_models" /
                           f"{result['model_hash']}.json").read_text(encoding="utf-8"))
    assert artifact["activated"] is False
    assert artifact["train_count"] + artifact["test_count"] == 10

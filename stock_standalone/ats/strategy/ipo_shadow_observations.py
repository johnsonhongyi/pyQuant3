"""Persist point-in-time IPO sentiment observations for offline shadow learning."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


_DB = Path("data/ipo_learning/shadow_observations.sqlite")
_STATUS = Path("data/ipo_learning/shadow_learning.latest.json")
_MODEL_DIR = Path("data/ipo_learning/shadow_models")


def _utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _write_status(root: Path, status: Mapping[str, Any]) -> None:
    path = root / _STATUS
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(dict(status), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        return


def capture_shadow_observation(
    root: str | Path, ticker: str, context: Mapping[str, Any], *,
    cutoff: datetime | None = None,
) -> dict[str, Any]:
    """Freeze only contract-validated facts available by cutoff; never submit orders."""
    root_path = Path(root).resolve()
    now = cutoff or datetime.now(timezone.utc)
    status: dict[str, Any] = {
        "updated_at": now.isoformat(timespec="seconds"),
        "state": "UNREADY", "ticker": ticker, "observed_field_count": 0,
        "order_submitted": False, "model_promoted": False,
    }
    if (
        not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit()
        or not isinstance(context, Mapping) or now.tzinfo is None
    ):
        status["reason"] = "INVALID_INPUT"
        _write_status(root_path, status)
        return status
    cutoff_utc = now.astimezone(timezone.utc)
    checks = context.get("observation_checks")
    observations = context.get("data_observations")
    config_hash = context.get("configuration_hash")
    contract_hash = context.get("data_contract_hash")
    if (
        not isinstance(checks, Mapping) or not isinstance(observations, Mapping)
        or not isinstance(config_hash, str) or len(config_hash) != 64
        or not isinstance(contract_hash, str) or len(contract_hash) != 64
    ):
        status["reason"] = "CONTRACT_NOT_READY"
        _write_status(root_path, status)
        return status
    fields = {}
    for field_id, row in observations.items():
        if (
            not isinstance(field_id, str) or not isinstance(row, Mapping)
            or checks.get(field_id) != "OBSERVED" or row.get("status") != "OBSERVED"
        ):
            continue
        as_of = _utc(row.get("as_of_time"))
        available = _utc(row.get("available_at"))
        if as_of is None or available is None or as_of > cutoff_utc or available > cutoff_utc:
            continue
        fields[field_id] = {
            "value": row.get("value"), "source_id": row.get("source_id"),
            "source_version": row.get("source_version"),
            "as_of_time": as_of.isoformat(), "available_at": available.isoformat(),
        }
    status["observed_field_count"] = len(fields)
    if not fields:
        status["reason"] = "NO_FRESH_SOURCE_FIELDS"
        _write_status(root_path, status)
        return status
    record = {
        "ticker": ticker, "cutoff": cutoff_utc.isoformat(),
        "configuration_hash": config_hash, "data_contract_hash": contract_hash,
        "fields": fields,
        "sentiment": {
            "lrrm": getattr(context.get("lrrm"), "liquidity_regime", "UNKNOWN"),
            "ipo_regime": getattr(context.get("ipo_regime"), "state", "UNKNOWN"),
            "live_heat": getattr(context.get("live_heat"), "heat_score", None),
            "t1_carry": getattr(context.get("t1_carry"), "state", "BLOCK"),
        },
    }
    try:
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        path = root_path / _DB
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2.0) as connection:
            connection.execute("PRAGMA busy_timeout=2000")
            connection.execute("""CREATE TABLE IF NOT EXISTS shadow_observations (
                observation_hash TEXT PRIMARY KEY, ticker TEXT NOT NULL,
                cutoff TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                data_contract_hash TEXT NOT NULL, payload_json TEXT NOT NULL
            )""")
            connection.execute(
                "INSERT OR IGNORE INTO shadow_observations VALUES (?, ?, ?, ?, ?, ?)",
                (digest, ticker, record["cutoff"], config_hash, contract_hash,
                 encoded.decode("utf-8")),
            )
            connection.commit()
    except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
        status["reason"] = "PERSISTENCE_FAILED"
        _write_status(root_path, status)
        return status
    status.update({"state": "CAPTURED", "observation_hash": digest,
                   "reason": "AWAITING_MATURE_REVIEWED_LABELS"})
    _write_status(root_path, status)
    return status


def train_shadow_candidate(root: str | Path) -> dict[str, Any]:
    """Train an offline candidate from reviewed D1 labels; never activate it."""
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
    from ats.strategy.ipo_outcome_review import _verified_evidence, load_latest_outcome_reviews

    root_path = Path(root).resolve()
    status: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": "WAITING_REVIEWED_LABELS", "sample_count": 0,
        "order_submitted": False, "model_promoted": False,
    }
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(root_path / "config/ipo_sentiment.yaml"))
        if not config.verify_integrity():
            raise ValueError("invalid config")
        reviews = load_latest_outcome_reviews(root_path)
        database = root_path / _DB
        if not reviews or not database.is_file():
            _write_status(root_path, status)
            return status
        samples = []
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5) as connection:
            connection.execute("PRAGMA query_only=ON")
            for evidence_file in sorted((root_path / "data/ipo_learning/outcome_evidence").glob("*.json")):
                if evidence_file.stat().st_size > 64 * 1024:
                    continue
                try:
                    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, ValueError):
                    continue
                if not _verified_evidence(evidence):
                    continue
                review = reviews.get(evidence["evidence_id"], {})
                if review.get("decision") != "ACCEPTED" or review.get("evidence_hash") != evidence["evidence_hash"]:
                    continue
                ticker = evidence.get("ticker")
                listing_date = evidence.get("listing_date")
                label = evidence.get("d1_positive")
                if not isinstance(label, bool) or not isinstance(ticker, str) or not isinstance(listing_date, str):
                    continue
                rows = connection.execute(
                    "SELECT observation_hash, cutoff, payload_json FROM shadow_observations "
                    "WHERE ticker=? AND configuration_hash=? AND data_contract_hash=? ORDER BY cutoff LIMIT 300",
                    (ticker, config.config_hash, config.data_contract.config_hash),
                ).fetchall()
                for digest, cutoff, payload_json in rows:
                    point = _utc(cutoff)
                    if point is None or point.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != listing_date:
                        continue
                    try:
                        if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != digest:
                            continue
                        payload = json.loads(payload_json)
                        values = {
                            field: float(item["value"])
                            for field, item in payload["fields"].items()
                            if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
                            and not isinstance(item["value"], bool)
                            and math.isfinite(item["value"])
                        }
                    except (KeyError, TypeError, ValueError, OverflowError):
                        continue
                    if values:
                        samples.append({"ticker": ticker, "listing_date": listing_date,
                                        "label": int(label), "values": values,
                                        "observation_hash": digest,
                                        "evidence_hash": evidence["evidence_hash"]})
                        break
        status["sample_count"] = len(samples)
        if len(samples) < 8:
            status["state"] = "WAITING_MORE_SAMPLES"
            status["required_count"] = 8
            _write_status(root_path, status)
            return status
        samples.sort(key=lambda item: (item["listing_date"], item["ticker"]))
        feature_names = sorted(set.intersection(*(set(item["values"]) for item in samples)))
        if len(feature_names) < 2:
            status["state"] = "WAITING_COMMON_FEATURES"
            _write_status(root_path, status)
            return status
        split = max(1, min(len(samples) - 2, int(len(samples) * 0.7)))
        train, test = samples[:split], samples[split:]
        if len({row["label"] for row in train}) < 2 or len({row["label"] for row in test}) < 2:
            status["state"] = "WAITING_CLASS_DIVERSITY"
            _write_status(root_path, status)
            return status
        means = [sum(row["values"][name] for row in train) / len(train) for name in feature_names]
        scales = [max(1e-6, (sum((row["values"][name] - mean) ** 2 for row in train) / len(train)) ** 0.5)
                  for name, mean in zip(feature_names, means)]

        def vector(row: Mapping[str, Any]) -> list[float]:
            return [(row["values"][name] - mean) / scale
                    for name, mean, scale in zip(feature_names, means, scales)]

        weights = [0.0] * len(feature_names)
        bias = 0.0
        for _ in range(200):
            for row in train:
                x = vector(row)
                z = max(-30.0, min(30.0, bias + sum(w * v for w, v in zip(weights, x))))
                error = 1.0 / (1.0 + math.exp(-z)) - row["label"]
                weights = [w - 0.03 * (error * v + 0.001 * w) for w, v in zip(weights, x)]
                bias -= 0.03 * error
        def brier(rows: list[dict[str, Any]], base: float | None = None) -> float:
            total = 0.0
            for row in rows:
                z = max(-30.0, min(30.0, bias + sum(w * v for w, v in zip(weights, vector(row)))))
                probability = base if base is not None else 1.0 / (1.0 + math.exp(-z))
                total += (probability - row["label"]) ** 2
            return total / len(rows)
        baseline_rate = sum(row["label"] for row in train) / len(train)
        model_brier = brier(test)
        baseline_brier = brier(test, baseline_rate)
        artifact = {
            "schema_version": "ipo-shadow-sentiment.v1",
            "configuration_hash": config.config_hash,
            "data_contract_hash": config.data_contract.config_hash,
            "feature_names": feature_names, "means": means, "scales": scales,
            "weights": weights, "bias": bias,
            "train_count": len(train), "test_count": len(test),
            "train_observation_hashes": [row["observation_hash"] for row in train],
            "test_observation_hashes": [row["observation_hash"] for row in test],
            "label_evidence_hashes": [row["evidence_hash"] for row in samples],
            "test_brier": model_brier, "baseline_brier": baseline_brier,
            "activated": False,
        }
        encoded = json.dumps(artifact, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        directory = root_path / _MODEL_DIR
        directory.mkdir(parents=True, exist_ok=True)
        model_path = directory / f"{digest}.json"
        if not model_path.exists():
            temporary = directory / f".{digest}.tmp"
            temporary.write_bytes(encoded)
            os.replace(temporary, model_path)
        status.update({
            "state": "CANDIDATE_READY" if model_brier < baseline_brier else "CANDIDATE_BELOW_BASELINE",
            "model_hash": digest, "train_count": len(train), "test_count": len(test),
            "test_brier": round(model_brier, 6), "baseline_brier": round(baseline_brier, 6),
        })
    except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError, RecursionError) as exc:
        status.update({"state": "UNREADY", "reason": type(exc).__name__})
    _write_status(root_path, status)
    return status

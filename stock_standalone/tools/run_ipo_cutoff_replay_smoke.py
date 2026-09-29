# -*- coding: utf-8 -*-
"""Exercise the full 41-field cutoff replay contract with synthetic observations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Dict, Mapping

import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

SYNTHETIC_TICKER = "999999"
_AUXILIARY_INPUTS = (
    ("offline.synthetic_news", "news"),
    ("offline.synthetic_announcements", "announcement"),
    ("offline.synthetic_subscriptions", "subscription"),
    ("offline.synthetic_vector_evidence", "vector_evidence"),
)


def _source_manifest(config: Any, bar_source_id: str) -> Dict[str, Any]:
    fields_by_source: Dict[str, Dict[str, Any]] = {}
    for field in config.data_contract.fields.values():
        source_id = field.source_id
        source = fields_by_source.setdefault(source_id, {
            "source_id": source_id,
            "source_version": "synthetic-field-history.v1",
            "source_timezone": field.source_timezone,
            "source_role": "feature",
            "access": "MODEL_INPUT",
            "availability_time_keys": set(),
        })
        if source["source_timezone"] != field.source_timezone:
            raise ValueError(f"field sources disagree on timezone: {source_id}")
        source["availability_time_keys"].update((field.as_of_key, field.available_at_key))

    sources = [{
        "source_id": bar_source_id,
        "source_version": "synthetic-bars.v1",
        "source_timezone": "Asia/Shanghai",
        "source_role": "bars",
        "access": "MODEL_INPUT",
        "availability_time_keys": ["datetime"],
    }]
    for source in fields_by_source.values():
        source["availability_time_keys"] = sorted(source["availability_time_keys"])
        sources.append(source)
    for source_id, role in _AUXILIARY_INPUTS:
        sources.append({
            "source_id": source_id,
            "source_version": "empty-synthetic-fixture.v1",
            "source_timezone": "Asia/Shanghai",
            "source_role": role,
            "access": "MODEL_INPUT",
            "availability_time_keys": ["available_at"],
        })
    sources.append({
        "source_id": "offline.synthetic_outcomes",
        "source_version": "no-labels.v1",
        "source_timezone": "Asia/Shanghai",
        "source_role": "outcome",
        "access": "OUTCOME_ONLY",
        "availability_time_keys": ["published_at"],
    })
    return {"manifest_version": "1", "sources": sources}


def _summary(metadata: Any, _observations: list[Mapping[str, Any]]) -> Dict[str, Any]:
    code = str(metadata.get("code", SYNTHETIC_TICKER)) if isinstance(metadata, Mapping) else SYNTHETIC_TICKER
    name = str(metadata.get("name", "离线合成回放")) if isinstance(metadata, Mapping) else "离线合成回放"
    return {
        "code": code,
        "name": name,
        "listing_date": None,
        "preheat_at_listing": None,
        "first_entry_ready_time": None,
        "max_heat_before_entry": None,
        "t1_carry_close": None,
        "D1_open_gap": None,
        "D1_min_vs_listing_open": None,
        "D1_min_vs_listing_low": None,
        "D1_reclaim_status": None,
        "false_entry_flag": None,
        "survival_flag": None,
        "blocked_by_rule": "SYNTHETIC_REPLAY_SMOKE_ONLY",
        "transition_log": [],
    }


def run_smoke(root: Path | None = None) -> Dict[str, Any]:
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
    from tools.historical_cutoff_replay_engine import (
        HistoricalCutoffReplayEngine,
        HistoricalReplayReportStore,
        load_ipo_replay_observation_frames,
    )
    from tools.run_ipo_llm_simulation import (
        SIMULATION_PROVIDER,
        _default_model,
        _seed_synthetic_observations,
        _write_run_configuration,
    )

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    run_root = (root or APP_ROOT / "data" / "ipo_replay_smoke" / run_id).resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    _write_run_configuration(run_root, SIMULATION_PROVIDER, _default_model(SIMULATION_PROVIDER))
    config = IPODecisionConfigSnapshot.from_yaml(
        str(run_root / "config" / "ipo_sentiment.yaml")
    )
    field_count = _seed_synthetic_observations(run_root, config)
    if field_count != 41:
        raise RuntimeError(f"synthetic fixture stored {field_count}/41 fields")

    bar_source_id = "offline.synthetic_bars"
    source_manifest = _source_manifest(config, bar_source_id)
    input_frames = load_ipo_replay_observation_frames(
        run_root, SYNTHETIC_TICKER, config,
    )
    for source_id, _role in _AUXILIARY_INPUTS:
        input_frames[source_id] = pd.DataFrame(columns=["available_at"])

    cutoff = datetime.now(timezone.utc)
    bars = pd.DataFrame([{
        "datetime": cutoff,
        "close": 10.2,
    }])

    def load_history(_code: str, _start_date: str) -> Dict[str, Any]:
        return {
            "bars": bars,
            "metadata": {"code": SYNTHETIC_TICKER, "name": "离线合成回放"},
            "inputs": input_frames,
        }

    def evaluate_as_of(
        _code: str, _bars: pd.DataFrame, as_of: pd.Timestamp,
        _known_inputs: Mapping[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        return {
            "as_of_time": as_of.isoformat(),
            "decision": "BLOCK",
            "causal_chain": ["synthetic cutoff replay smoke; no performance labels"],
        }

    engine = HistoricalCutoffReplayEngine(
        sample_codes=[SYNTHETIC_TICKER],
        load_history=load_history,
        evaluate_as_of=evaluate_as_of,
        build_summary=_summary,
        source_timezone="Asia/Shanghai",
        source_manifest=source_manifest,
        source_id=bar_source_id,
        start_date=cutoff.strftime("%Y-%m-%d"),
        replay_config={"purpose": "synthetic-cutoff-smoke", "production_qualified": False},
        decision_config_snapshot=config,
    )
    report_dir = run_root / "replay_reports"
    report = engine.replay_report(output_directory=report_dir)
    stored = HistoricalReplayReportStore(report_dir).load(report["replay_report_hash"])
    index = HistoricalReplayReportStore(report_dir).summary()
    metrics = stored["effect_metrics"]
    passed = (
        index.get("status") == "AVAILABLE"
        and stored.get("input_contract_status") == "READY"
        and stored.get("cutoff_count") == 1
        and metrics["future_leakage_count"].get("status") == "MEASURED"
        and metrics["future_leakage_count"].get("value") == 0
        and metrics["explanation_coverage"].get("status") == "MEASURED"
        and metrics["explanation_coverage"].get("value") == 1.0
    )
    result = {
        "schema_version": "ipo-cutoff-replay-smoke.v1",
        "simulation_only": True,
        "production_qualified": False,
        "real_data_used": False,
        "real_trading_enabled": False,
        "synthetic_fields_persisted": field_count,
        "input_contract_status": stored["input_contract_status"],
        "cutoff_count": stored["cutoff_count"],
        "effect_metrics": metrics,
        "replay_report_hash": stored["replay_report_hash"],
        "replay_report_path": str(report_dir / f"{stored['replay_report_hash']}.json"),
        "acceptance_status": "SMOKE_PASS" if passed else "SMOKE_FAIL",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    output = run_root / "cutoff_replay_smoke_manifest.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    result["manifest_path"] = str(output)
    return result


def main() -> int:
    try:
        result = run_smoke()
    except Exception as exc:
        print(json.dumps({
            "acceptance_status": "SMOKE_FAIL",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "production_qualified": False,
        }, ensure_ascii=False, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if result["acceptance_status"] == "SMOKE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

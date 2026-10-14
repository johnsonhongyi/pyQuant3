"""Read-only IPO learning inventory; no collector, model, or order is started."""

from __future__ import annotations

from sys_utils import safe_resolve_path

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _outcome_inventory(root: Path) -> dict[str, Any]:
    from ats.strategy.ipo_outcome_review import _verified_evidence, load_latest_outcome_reviews

    database = root / "data/ipo_learning/outcome_reviews.sqlite"
    if database.is_file():
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2) as connection:
                check = connection.execute("PRAGMA quick_check").fetchone()
                if not check or check[0] != "ok":
                    raise sqlite3.DatabaseError("review database integrity check failed")
                connection.execute("SELECT COUNT(*) FROM outcome_reviews").fetchone()
            reviews = load_latest_outcome_reviews(root)
        except (OSError, sqlite3.Error, ValueError):
            return {"status": "UNAVAILABLE", "invalid_count": 0,
                    "invalid_review_count": 0, "review_counts": {}}
    else:
        reviews = {}
    records = {}
    invalid = 0
    invalid_reviews = 0
    now = datetime.now(timezone.utc)
    for path in (root / "data/ipo_learning/outcome_evidence").glob("*.json"):
        try:
            if path.stat().st_size > 64 * 1024:
                raise ValueError("oversized evidence")
            document = json.loads(path.read_text(encoding="utf-8"))
            if not _verified_evidence(document):
                raise ValueError("invalid evidence")
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
            invalid += 1
            continue
        evidence_id = document["evidence_id"]
        review = reviews.get(evidence_id)
        reviewed_at = None
        available_at = None
        if isinstance(review, dict):
            try:
                reviewed_text = review.get("reviewed_at_utc")
                if isinstance(reviewed_text, str):
                    reviewed_at = datetime.fromisoformat(reviewed_text.replace("Z", "+00:00"))
                source = document.get("source")
                available_text = source.get("available_at") if isinstance(source, dict) else None
                if isinstance(available_text, str):
                    available_at = datetime.fromisoformat(available_text.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                reviewed_at = available_at = None
        valid_review = bool(
            isinstance(review, dict)
            and review.get("evidence_hash") == document["evidence_hash"]
            and review.get("decision") in {"ACCEPTED", "REJECTED"}
            and isinstance(review.get("reviewer"), str) and review["reviewer"].strip()
            and isinstance(review.get("reason"), str) and review["reason"].strip()
            and reviewed_at is not None and reviewed_at.tzinfo is not None and reviewed_at.utcoffset() is not None
            and available_at is not None and available_at.tzinfo is not None and available_at.utcoffset() is not None
            and available_at.astimezone(timezone.utc) <= reviewed_at.astimezone(timezone.utc) <= now
        )
        if review and not valid_review:
            invalid_reviews += 1
        records[evidence_id] = {
            "evidence_id": evidence_id, "evidence_hash": document["evidence_hash"],
            "ticker": document.get("ticker"), "listing_date": document.get("listing_date"),
            "decision": review["decision"] if valid_review else "PENDING_HUMAN_REVIEW",
            "reviewer": review["reviewer"] if valid_review else "",
            "reviewed_at": review["reviewed_at_utc"] if valid_review else "", "path": str(path),
        }
    counts = {name: sum(row["decision"] == name for row in records.values())
              for name in ("ACCEPTED", "REJECTED", "PENDING_HUMAN_REVIEW")}
    return {"status": "DEGRADED" if invalid_reviews else "AVAILABLE",
            "verified_count": len(records), "invalid_count": invalid,
            "invalid_review_count": invalid_reviews,
            "review_counts": counts, "records": list(records.values())}


def collect_learning_progress(root: str | Path, ticker: str = "301689") -> dict[str, Any]:
    from ats.llm.learning_snapshot_store import snapshot_store_summary
    from ats.llm.provider_preflight import inspect_provider_preflight
    from ats.llm.runtime_service import _load_authorization
    from ats.llm.sealed_dataset_store import SealedDatasetRepository
    from ats.llm.shadow_evaluation import collect_shadow_evaluation
    from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
    from ats.strategy.ipo_shadow_observations import ats_signal_paper_outcomes
    from ats.strategy.ipo_source_orchestrator import collect_source_readiness

    base = safe_resolve_path(Path(root))
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": ticker, "status": "BLOCKED", "read_only": True, "scope": "SHADOW_EVALUATION",
        "order_submitted": False, "training_performed": False, "model_promoted": False,
        "components": {}, "next_actions": [],
    }
    components = report["components"]
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(base / "config/ipo_sentiment.yaml"))
        if not config.verify_integrity():
            raise ValueError("configuration integrity mismatch")
        report.update(configuration_hash=config.config_hash,
                      data_contract_hash=config.data_contract.config_hash)
        readiness = collect_source_readiness(base, ticker, config)
        components["sources"] = {key: readiness[key] for key in
                                 ("status", "ready_count", "required_count", "observations")}
    except Exception as exc:
        components["sources"] = {"status": "UNAVAILABLE", "error": type(exc).__name__}
    readers = {
        "snapshots": lambda: snapshot_store_summary(base),
        "paper_outcomes": lambda: ats_signal_paper_outcomes(base),
        "outcome_reviews": lambda: _outcome_inventory(base),
        "shadow_evaluation": lambda: collect_shadow_evaluation(base),
        "sealed_datasets": lambda: SealedDatasetRepository(
            base / "data/ipo_learning/sealed_datasets", create=False).summary(),
        "provider": lambda: inspect_provider_preflight(
            base / "config/llm_config.yaml",
            authorization=_load_authorization(base / "config/llm_runtime_acceptance.json")),
    }
    for name, reader in readers.items():
        try:
            components[name] = reader()
        except Exception as exc:
            components[name] = {"status": "UNAVAILABLE", "error": type(exc).__name__}
    acquisition = base / "data/ipo_learning/acquisition.latest.json"
    try:
        if not acquisition.is_file():
            components["acquisition_report"] = {"status": "MISSING"}
        else:
            if acquisition.stat().st_size > 1024 * 1024:
                raise ValueError("oversized acquisition report")
            saved = json.loads(acquisition.read_text(encoding="utf-8"))
            components["acquisition_report"] = {
                "status": "HISTORICAL_REPORT", "generated_at": saved.get("generated_at"),
                "ready_count_at_capture": saved.get("ready_count"),
            }
    except (OSError, UnicodeError, ValueError, AttributeError):
        components["acquisition_report"] = {"status": "UNAVAILABLE"}
    sources = components["sources"]
    if sources.get("status") != "READY":
        report["next_actions"].append("刷新并核验同标的同 cutoff 的 41 项真实来源；逐字段见 sources.observations")
    if not components["snapshots"].get("snapshot_count"):
        report["next_actions"].append("等待完整有效 Gate 决策快照；历史/部分字段不能补成完整快照")
    if not components["paper_outcomes"].get("closed_count"):
        report["next_actions"].append("等待真实异动与 ATS PAPER 完整 T+1 平仓，核对费用和收益归因")
    if components["outcome_reviews"].get("review_counts", {}).get("PENDING_HUMAN_REVIEW"):
        report["next_actions"].append("在 IPO 学习控制台逐份人工复核 outcome_reviews.records 中的证据")
    if components["shadow_evaluation"].get("state") == "SHADOW_EVALUATED":
        report["status"] = "SHADOW_EVALUATED"
    else:
        report["next_actions"].append("使用 run_ipo_shadow_evaluation.py 关联已归档模型信封、完整快照与人工已审核成熟结果")
    report["next_actions"].extend([
        "真实 cutoff 回放及 13 项效果指标验收；缺失分母或 NOT_EVALUABLE 不算通过",
        "正式 Provider 隔离/授权及目标桌面长跑验收需独立完成",
    ])
    report["out_of_scope"] = ["SFT/DPO 权重训练", "模型晋级", "实盘交易"]
    return report

"""Inventory IPO learning, or build/seal reviewed datasets without training a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Source bootstrap is only for imports; persistent data uses the system root.
if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

from sys_utils import get_app_root, safe_resolve_path

APP_ROOT = safe_resolve_path(get_app_root())

from ats.llm.learning_progress import collect_learning_progress
from ats.llm.offline_learning import MAX_CANDIDATE_BATCH_BYTES, OfflineLearningError, build_offline_datasets
from ats.llm.sealed_dataset_store import SealedDatasetRepository
from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot


def build_reviewed_dataset(root: Path, candidates_path: Path, *, seal: bool = False) -> dict:
    """Reject an entire invalid batch; review decisions are only read from the ledger."""
    root = safe_resolve_path(root)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "BLOCKED", "training_performed": False,
        "order_submitted": False, "model_promoted": False,
    }
    try:
        with candidates_path.open("rb") as stream:
            payload = stream.read(MAX_CANDIDATE_BATCH_BYTES + 1)
        if len(payload) > MAX_CANDIDATE_BATCH_BYTES:
            raise OfflineLearningError("candidate file exceeds 64 MiB")
        candidates = json.loads(payload.decode("utf-8"))
        if not isinstance(candidates, list):
            raise OfflineLearningError("candidate file must be a JSON array")
        report["candidate_file_hash"] = hashlib.sha256(payload).hexdigest()
        report["candidate_count"] = len(candidates)
        config = IPODecisionConfigSnapshot.from_yaml(str(root / "config/ipo_sentiment.yaml"))
        if not config.verify_integrity():
            raise OfflineLearningError("configuration integrity mismatch")
        dataset = build_offline_datasets(
            candidates, config_snapshot=config, generated_at=report["generated_at"],
            review_db_path=root / "logs/ipo_learning_reviews.sqlite",
        )
        report.update({key: dataset[key] for key in
                       ("status", "dataset_hash", "configuration_hash", "data_contract_hash")})
        report["splits"] = {
            name: {key: dataset[name].get(key) for key in
                   ("status", "sample_count", "event_group_count", "split_group_counts")}
            for name in ("sft", "dpo")
        }
        if seal and dataset["status"] == "READY_FOR_TRAINING":
            repository = SealedDatasetRepository(root / "data/ipo_learning/sealed_datasets")
            report["sealed"] = repository.seal(dataset)
            repository.load(dataset["dataset_hash"])
            report["status"] = "SEALED_AND_VERIFIED"
        elif seal:
            report["reason"] = "insufficient reviewed SFT/DPO event groups; nothing sealed"
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError, sqlite3.Error) as exc:
        report.update(status="BLOCKED", reason=str(exc)[:500], error_type=type(exc).__name__)
    return report


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="IPO 学习只读盘点 / 已审核 SFT-DPO 构建与封存（不训练、不下单）")
    parser.add_argument("--root", type=Path, default=APP_ROOT)
    parser.add_argument("--code", default="301689")
    parser.add_argument("--candidates", type=Path, help="已人工审核的完整候选 JSON 数组")
    parser.add_argument("--seal", action="store_true", help="将合格数据集原子封存并重新加载验证")
    parser.add_argument("--json-out", type=Path, help="显式写入本次报告；默认只输出")
    args = parser.parse_args()
    if len(args.code) != 6 or not args.code.isdigit():
        parser.error("--code 必须为六位数字")
    if args.seal and args.candidates is None:
        parser.error("--seal 需要 --candidates")
    report = (build_reviewed_dataset(args.root, args.candidates, seal=args.seal)
              if args.candidates else collect_learning_progress(args.root, args.code))
    if args.json_out:
        try:
            write_report(args.json_out, report)
        except (OSError, ValueError) as exc:
            report.update(status="BLOCKED", report_persistence="FAILED", error_type=type(exc).__name__)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] in {"READY_FOR_TRAINING", "SEALED_AND_VERIFIED", "SHADOW_EVALUATED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

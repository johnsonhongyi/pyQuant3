"""Run a bounded, read-only 30-session production data-ingestion audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

# Source bootstrap is only for imports; persistent data uses the system root.
if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

from sys_utils import get_app_root, safe_resolve_path

APP_ROOT = safe_resolve_path(get_app_root())

from ats.llm.production_ingest_audit import collect_production_ingest_report


def _report_hash(report: dict) -> str:
    return hashlib.sha256(json.dumps(
        {key: value for key, value in report.items() if key != "report_hash"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _write_report(root: Path, target: Path, report: dict) -> None:
    destination = target.resolve()
    try:
        destination.relative_to(safe_resolve_path(root))
    except ValueError as exc:
        raise ValueError("REPORT_PATH_MUST_STAY_INSIDE_PROJECT_ROOT") from exc
    if destination in {
        safe_resolve_path(root / "trading_signals.db"),
        safe_resolve_path(root / "signal_strategy.db"),
        safe_resolve_path(root / "market_pulse.db"),
    }:
        raise ValueError("REPORT_PATH_CANNOT_OVERWRITE_A_SOURCE_DATABASE")
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    report["report_persisted"] = True
    report["report_path"] = destination.relative_to(safe_resolve_path(root)).as_posix()
    report["report_hash"] = _report_hash(report)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except (OSError, ValueError, TypeError) as exc:
        report.update(status="REPORT_PERSISTENCE_FAILED", report_persisted=False,
                      report_error=type(exc).__name__)
        report["report_hash"] = _report_hash(report)
        raise
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="30个交易日内只读核验生产交易库、信号库和TDX原始日线；不写生产库、不训练、不下单。"
    )
    parser.add_argument("--root", type=Path, default=APP_ROOT, help="包含生产SQLite副本的ATS程序根目录")
    parser.add_argument(
        "--report", type=Path,
        default=Path("data/ipo_learning/production_ingest_30d.latest.json"),
        help="仅在项目根目录内保存脱敏汇总报告",
    )
    parser.add_argument("--no-report", action="store_true", help="只输出结果，不写本地报告")
    args = parser.parse_args()
    root = safe_resolve_path(args.root)
    try:
        report = collect_production_ingest_report(root)
    except Exception as exc:
        report = {
            "schema_version": "ipo.production-ingest-test.v1",
            "status": "FAILED", "error_type": type(exc).__name__,
            "production_database_modified": False, "learning_database_modified": False,
            "training_performed": False, "model_promoted": False, "order_submitted": False,
            "report_persisted": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 2
    report["report_persisted"] = False
    if not args.no_report:
        target = args.report if args.report.is_absolute() else root / args.report
        try:
            _write_report(root, target, report)
        except Exception as exc:
            report.update(status="REPORT_PERSISTENCE_FAILED", report_persisted=False,
                          report_error=type(exc).__name__)
            report["report_hash"] = _report_hash(report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] in {"PASS", "PASS_WITH_DATA_GAPS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

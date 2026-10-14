"""Run the existing TK PAPER pipeline with explicit fees and isolated state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

# Source bootstrap is only for imports; persistent data uses the system root.
if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

from sys_utils import get_app_root, safe_resolve_path

ROOT = safe_resolve_path(get_app_root())


def discover_codes(root=ROOT):
    uri = safe_resolve_path(Path(root) / "trading_signals.db").as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            "SELECT DISTINCT code FROM signal_history WHERE date IN "
            "(SELECT DISTINCT date FROM signal_history ORDER BY date DESC LIMIT 30)"
        ).fetchall()
    finally:
        connection.close()
    from ats.llm.production_ingest_audit import normalize_code
    return sorted({code for row in rows if (code := normalize_code(row[0]))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--max-rounds", type=int)
    parser.add_argument("--codes", default="")
    args = parser.parse_args()
    if not 1 <= args.interval <= 60 or (args.max_rounds is not None and args.max_rounds < 1):
        parser.error("interval must be 1..60 seconds and max-rounds must be positive")
    output = ROOT / "data/ipo_learning/paper_auto"
    output.mkdir(parents=True, exist_ok=True)
    # Windows process-owned byte lock is automatically released after a crash.
    import msvcrt
    with (output / "runner.lock").open("a+b") as lock:
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("PAPER_AUTO_ALREADY_RUNNING", flush=True)
            return 2
        from tools.run_shadow_live_test import run_shadow_test, _write_auto_status
        if (output / "STOP").exists():
            _write_auto_status(str(output), {"status": "STOP_REQUESTED", "mode": "PAPER"})
            return 0
        try:
            codes = args.codes.split(",") if args.codes else discover_codes()
            if not codes:
                raise ValueError("NO_PRODUCTION_CANDIDATE_CODES")
            _write_auto_status(str(output), {
                "status": "STARTING", "mode": "PAPER", "candidate_count": len(codes),
                "initial_capital": 1000000, "commission_rate": 0.0000754, "sell_extra_fee": 5,
            })
            print(json.dumps({"pid": os.getpid(), "candidate_count": len(codes), "mode": "PAPER"}), flush=True)
            result = run_shadow_test(
                interval_seconds=args.interval, max_rounds=args.max_rounds,
                candidate_codes=codes, log_dir=str(output),
                isolated_paper_state_dir=str(output / "state"),
                configured_fees=True, require_fresh_market=True,
            )
            _write_auto_status(str(output), dict(result, status="STOPPED", mode="PAPER"))
            return 0
        except Exception as exc:
            _write_auto_status(str(output), {"status": "FAILED", "mode": "PAPER", "error": str(exc)})
            print(f"PAPER_AUTO_FAILED:{exc}", flush=True)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

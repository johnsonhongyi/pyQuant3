"""Add a verified cutover baseline to a TK PAPER snapshot without rewriting fills."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_state_path() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from sys_utils import get_app_root

    return Path(get_app_root()) / "logs" / "paper_account_state.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate(data: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("paper state must be a JSON object")
    if data.get("ledger_baseline") is not None:
        raise ValueError("paper state already has a ledger baseline")
    orders = data.get("orders")
    positions = data.get("positions")
    if not isinstance(orders, list) or not isinstance(positions, dict):
        raise ValueError("paper state is missing orders or positions")
    cash = float(data.get("cash"))
    if not math.isfinite(cash) or cash < 0:
        raise ValueError("paper cash must be non-negative")
    baseline_positions: dict[str, dict[str, float]] = {}
    for code, position in positions.items():
        if not isinstance(position, dict):
            raise ValueError(f"invalid position row: {code}")
        volume = float(position.get("volume"))
        entry_price = float(position.get("entry_price"))
        if not math.isfinite(volume) or not math.isfinite(entry_price) or volume <= 0 or entry_price <= 0:
            raise ValueError(f"invalid position values: {code}")
        baseline_positions[str(code).strip().zfill(6)] = {
            "volume": volume,
            "entry_price": entry_price,
        }
    order_ids = [str(row.get("order_id") or "") for row in orders if isinstance(row, dict)]
    if len(order_ids) != len(orders) or len(set(order_ids)) != len(order_ids):
        raise ValueError("orders contain invalid rows or duplicate IDs")
    through_order_id = order_ids[-1] if order_ids else ""
    canonical_orders = []
    for row in orders:
        canonical = {
            key: float(row.get(key) or 0.0)
            for key in ("price", "size_pct", "volume")
        }
        canonical.update({
            key: str(row.get(key) or "")
            for key in ("order_id", "code", "action", "timestamp", "request_id")
        })
        canonical_orders.append(canonical)
    prefix = json.dumps(
        canonical_orders, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    baseline = {
        "schema_version": 1,
        "status": "PENDING_VALIDATION",
        "source": "TK_PAPER_SNAPSHOT_CUTOVER",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "order_count": len(orders),
        "through_order_id": through_order_id,
        "orders_sha256": _sha256(prefix),
        "cash": cash,
        "positions": baseline_positions,
    }
    return data, baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=_default_state_path())
    parser.add_argument("--apply", action="store_true", help="write after creating a backup")
    args = parser.parse_args()

    path = args.path.resolve(strict=True)
    original = path.read_bytes()
    payload, baseline = _validate(json.loads(original.decode("utf-8")))
    payload["ledger_baseline"] = baseline
    reconciliation = payload.get("reconciliation")
    reconciliation = dict(reconciliation) if isinstance(reconciliation, dict) else {}
    reconciliation.update({
        "paper_execution_ready": False,
        "block_reason": "BASELINE_PENDING_RUNTIME_VALIDATION",
    })
    payload["reconciliation"] = reconciliation
    output = (json.dumps(payload, ensure_ascii=False, indent=4) + "\n").encode("utf-8")

    print(json.dumps({
        "mode": "apply" if args.apply else "preview",
        "path": str(path),
        "source_sha256": _sha256(original),
        "normalized_sha256": _sha256(output),
        "orders_preserved": len(payload["orders"]),
        "positions_seeded": len(baseline["positions"]),
        "cash_seeded": baseline["cash"],
        "baseline_status": baseline["status"],
    }, ensure_ascii=False))

    if not args.apply:
        return 0

    if _sha256(path.read_bytes()) != _sha256(original):
        raise RuntimeError("paper state changed during normalization; retry from a fresh snapshot")
    backup = path.with_name(f"{path.name}.pre_baseline_{_sha256(original)[:12]}.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".normalize.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    print(json.dumps({"backup": str(backup), "written": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

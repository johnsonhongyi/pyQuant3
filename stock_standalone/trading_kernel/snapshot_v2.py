# -*- coding: utf-8 -*-
"""Versioned reconciliation snapshot validation/migration."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Dict, Optional, Tuple

SNAPSHOT_VERSION = "2.0"


def migrate_reconciliation_snapshot(payload: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    """Migrate legacy v1 snapshots to v2, fail closed on malformed/future data."""
    if not isinstance(payload, dict):
        return None, "SNAPSHOT_NOT_MAPPING"

    version = str(payload.get("snapshot_version") or "1.0")
    if version not in {"1.0", "2.0"}:
        return None, "UNSUPPORTED_SNAPSHOT_VERSION:%s" % version

    data = deepcopy(payload)
    if not isinstance(data.get("positions", {}), dict):
        return None, "INVALID_POSITIONS"
    if not isinstance(data.get("orders", []), list):
        return None, "INVALID_ORDERS"
    if not isinstance(data.get("account", {}), dict):
        return None, "INVALID_ACCOUNT"
    if not isinstance(data.get("reconciliation", {}), dict):
        return None, "INVALID_RECONCILIATION"

    data["snapshot_version"] = SNAPSHOT_VERSION
    migration = data.get("migration")
    if migration is None:
        data["migration"] = {}
    elif not isinstance(migration, dict):
        return None, "INVALID_MIGRATION"
    if version == "1.0":
        data["migration"].update({
            "migrated_from": "1.0",
            "fail_closed_defaults": True,
        })
        # v1 did not guarantee T+1 facts. Missing quantities remain zero until
        # the kernel rebuilds them from its authoritative current read model.
        for code, raw in data.get("positions", {}).items():
            if not isinstance(raw, dict):
                return None, "INVALID_POSITION:%s" % code
            try:
                total = float(raw.get("volume", raw.get("total_qty", 0.0)) or 0.0)
            except (TypeError, ValueError):
                return None, "INVALID_LEGACY_QUANTITY:%s" % code
            if not math.isfinite(total) or total < 0:
                return None, "INVALID_LEGACY_QUANTITY:%s" % code
            # Ignore any legacy T+1 fields: v1 did not guarantee their source
            # or semantics, so all shares remain unresolved until rebuilt.
            raw.update({
                "code": str(raw.get("code") or code).strip().zfill(6),
                "trade_date": str(data.get("trade_date") or data.get("generated_at", ""))[:10],
                "snapshot_version": SNAPSHOT_VERSION,
                "total_qty": total,
                "sellable_qty": 0.0,
                "today_buy_qty": 0.0,
                "unresolved_qty": total,
                "lots": ([{
                    "qty": total,
                    "price": 0.0,
                    "buy_date": "",
                    "timestamp": "",
                    "source": "MIGRATED_V1_FAIL_CLOSED",
                    "sellable": False,
                    "today_buy": False,
                }] if total > 0 else []),
                "t1_fact_status": "MIGRATED_V1_FAIL_CLOSED",
            })

    for code, raw in data.get("positions", {}).items():
        if not isinstance(raw, dict):
            return None, "INVALID_POSITION:%s" % code
        required = (
            "code", "trade_date", "snapshot_version", "total_qty",
            "sellable_qty", "today_buy_qty", "unresolved_qty", "lots",
            "t1_fact_status",
        )
        missing = [field for field in required if field not in raw]
        if missing:
            return None, "MISSING_T1_FACTS:%s:%s" % (code, ",".join(missing))
        if str(raw.get("snapshot_version")) != SNAPSHOT_VERSION:
            return None, "POSITION_VERSION_MISMATCH:%s" % code
        quantities = {}
        for field in ("total_qty", "sellable_qty", "today_buy_qty", "unresolved_qty"):
            try:
                quantity = float(raw[field])
            except (TypeError, ValueError):
                return None, "INVALID_T1_FACTS:%s" % code
            if not math.isfinite(quantity) or quantity < 0:
                return None, "INVALID_T1_FACTS:%s" % code
            quantities[field] = quantity
        total = quantities["total_qty"]
        sellable = quantities["sellable_qty"]
        today = quantities["today_buy_qty"]
        unresolved = quantities["unresolved_qty"]
        if sellable > total + 1e-9 or today > total + 1e-9:
            return None, "T1_FACTS_EXCEED_TOTAL:%s" % code
        if sellable + today > total + 1e-9:
            return None, "T1_FACTS_OVERALLOCATED:%s" % code
        if abs(sellable + today + unresolved - total) > 1e-6:
            return None, "T1_FACTS_OVERALLOCATED:%s" % code
        lots = raw.get("lots")
        if not isinstance(lots, list):
            return None, "INVALID_LOTS:%s" % code
        lot_total = lot_sellable = lot_today = 0.0
        for lot in lots:
            if not isinstance(lot, dict) or "qty" not in lot:
                return None, "INVALID_LOT:%s" % code
            try:
                lot_qty = float(lot["qty"])
            except (TypeError, ValueError):
                return None, "INVALID_LOT:%s" % code
            if not math.isfinite(lot_qty) or lot_qty < 0:
                return None, "INVALID_LOT:%s" % code
            is_sellable = lot.get("sellable") is True
            is_today = lot.get("today_buy") is True
            if is_sellable and is_today:
                return None, "INVALID_LOT_T1_FLAGS:%s" % code
            lot_total += lot_qty
            if is_sellable:
                lot_sellable += lot_qty
            if is_today:
                lot_today += lot_qty
        if (
            abs(lot_total - total) > 1e-6
            or abs(lot_sellable - sellable) > 1e-6
            or abs(lot_today - today) > 1e-6
        ):
            return None, "LOT_FACTS_MISMATCH:%s" % code

    return data, "OK"

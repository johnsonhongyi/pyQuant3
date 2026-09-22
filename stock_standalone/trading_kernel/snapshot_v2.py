# -*- coding: utf-8 -*-
"""Versioned reconciliation snapshot validation/migration."""

from __future__ import annotations

from copy import deepcopy
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
    data.setdefault("migration", {})
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
            raw.setdefault("total_qty", float(raw.get("volume", 0.0) or 0.0))
            raw.setdefault("sellable_qty", 0.0)
            raw.setdefault("today_buy_qty", 0.0)
            raw.setdefault("unresolved_qty", float(raw.get("total_qty", 0.0) or 0.0))
            raw.setdefault("lots", [])
            raw.setdefault("t1_fact_status", "MIGRATED_V1_FAIL_CLOSED")

    for code, raw in data.get("positions", {}).items():
        try:
            total = max(0.0, float(raw.get("total_qty", 0.0) or 0.0))
            sellable = max(0.0, float(raw.get("sellable_qty", 0.0) or 0.0))
            today = max(0.0, float(raw.get("today_buy_qty", 0.0) or 0.0))
        except (TypeError, ValueError):
            return None, "INVALID_T1_FACTS:%s" % code
        if sellable > total + 1e-9 or today > total + 1e-9:
            return None, "T1_FACTS_EXCEED_TOTAL:%s" % code
        if not isinstance(raw.get("lots", []), list):
            return None, "INVALID_LOTS:%s" % code

    return data, "OK"

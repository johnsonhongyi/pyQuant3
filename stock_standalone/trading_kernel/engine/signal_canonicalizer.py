from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from trading_kernel.core.signal import StrategySignal


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def canonicalize_decision_queue_item(item: Mapping[str, Any]) -> StrategySignal:
    signal_type = str(item.get("signal_type", "") or "UNKNOWN")
    price = _float(item.get("current_price") or item.get("suggest_price"))
    ts = str(item.get("created_at") or datetime.now().isoformat(timespec="seconds"))
    features = {
        "priority": _float(item.get("priority")),
        "suggest_price": _float(item.get("suggest_price")),
        "current_price": price,
        "change_pct": _float(item.get("change_pct")),
        "pct_diff": _float(item.get("pct_diff")),
        "dff": _float(item.get("dff")),
        "sector_heat": _float(item.get("sector_heat")),
        "sector": str(item.get("sector", "") or ""),
        "sector_type": str(item.get("sector_type", "") or ""),
        "is_leader": bool(item.get("is_leader", False)),
        "leader_code": str(item.get("leader_code", "") or ""),
        "raw_reason": str(item.get("reason", "") or ""),
        "status": str(item.get("status", "") or ""),
        "hits": _float(item.get("hits", 1), 1.0),
        "volume": _float(item.get("volume"), 1.0),
    }
    return StrategySignal(
        code=str(item.get("code", "") or ""),
        name=str(item.get("name", "") or ""),
        ts=ts,
        source="SectorFocusController.decision_queue",
        signal_type=signal_type,
        price=price,
        features=features,
    )


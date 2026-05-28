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
        "action": str(item.get("action", "") or ""),
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
        
        # 物理丰富底层多周期高维特征与黄金龙头低吸判定参数
        "low": _float(item.get("low")),
        "high4": _float(item.get("high4")),
        "hmax": _float(item.get("hmax")),
        "low60": _float(item.get("low60")),
        "pbreak": int(_float(item.get("pbreak"), 0.0)),
        "ptop": _float(item.get("ptop")),
        "sws": _float(item.get("sws")),
        "swl": _float(item.get("swl")),
        "vol_ma5": _float(item.get("vol_ma5")),
        "days_held": int(_float(item.get("days_held"), 0.0)),
        "pnl_pct": _float(item.get("pnl_pct")),
        "vol_shrink_3d": bool(item.get("vol_shrink_3d", False)),
        "is_pullback_support": bool(item.get("is_pullback_support", False)),
        "is_collecting_stage": bool(item.get("is_collecting_stage", False)),
        "is_consolidation_stage": bool(item.get("is_consolidation_stage", False)),
        "is_doji": bool(item.get("is_doji", False)),
        "upper": _float(item.get("upper")),
        "max_pnl_since_entry": _float(item.get("max_pnl_since_entry", 0.0)),
        "sws_prev5": _float(item.get("sws_prev5")),
        "ma10d": _float(item.get("ma10d")),
        "ma10d_prev5": _float(item.get("ma10d_prev5")),
        "ma5d": _float(item.get("ma5d")),
        "tp_triggered": bool(item.get("tp_triggered", False)),
        "is_swing_low_mode": bool(item.get("is_swing_low_mode", False)),
        "regime": str(item.get("regime", "") or ""),
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


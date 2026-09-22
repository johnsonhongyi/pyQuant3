# -*- coding: utf-8 -*-
"""Single write/projection entry for ATS SignalLedger consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ats.candidate_cache import CandidateCache, CandidateDecision


@dataclass(frozen=True)
class LedgerUpdateResult:
    entry: Any
    decision: CandidateDecision
    wrote_ledger: bool


_global_update_service: Optional[LedgerUpdateService] = None


def get_ledger_update_service(signal_ledger: Any = None) -> LedgerUpdateService:
    """获取全系统统一的 LedgerUpdateService 单例 (SSOT 唯一写入门禁入口)"""
    global _global_update_service
    if _global_update_service is None:
        if signal_ledger is None:
            from ats.signal_ledger import get_signal_ledger
            signal_ledger = get_signal_ledger()
        if hasattr(signal_ledger, "get_update_service"):
            _global_update_service = signal_ledger.get_update_service()
        else:
            _global_update_service = LedgerUpdateService(signal_ledger)
    return _global_update_service


class LedgerUpdateService:
    """Owns session gating, consecutive-frame confirmation and projections."""

    def __init__(self, signal_ledger: Any, candidate_cache: Optional[CandidateCache] = None) -> None:
        self.signal_ledger = signal_ledger
        self.candidate_cache = candidate_cache or CandidateCache()

    @staticmethod
    def _extract_tick_time(row: Any) -> Optional[Any]:
        if row is None:
            return None
        for key in ("tick_time", "time_str", "time", "trade_time", "datetime", "timestamp"):
            val = None
            if hasattr(row, "get"):
                try:
                    val = row.get(key)
                except Exception:
                    val = None
            elif isinstance(row, dict) and key in row:
                val = row[key]
            if val is not None and str(val).strip():
                return val
        return None

    @staticmethod
    def _payload(
        name: str,
        price: float,
        pct: float,
        deviation: float,
        signal_tag: str,
    ) -> Dict[str, Any]:
        return {
            "name": str(name or ""),
            "price": float(price or 0.0),
            "pct": float(pct or 0.0),
            "deviation": float(deviation or 0.0),
            "signal_tag": str(signal_tag or ""),
        }

    def update_candidate(
        self,
        *,
        code: Any,
        name: str,
        price: float,
        pct: float,
        deviation: float,
        row: Any = None,
        volume_score: float = 0.0,
        source: str = "ATS",
        observed_at: Any = None,
        required_frames: Optional[int] = None,
        signal_tag: str = "",
        **ledger_kwargs: Any,
    ) -> LedgerUpdateResult:
        if observed_at is None and row is not None:
            observed_at = self._extract_tick_time(row)

        decision = self.candidate_cache.observe(
            code,
            source=source,
            payload=self._payload(name, price, pct, deviation, signal_tag),
            observed_at=observed_at,
            required_frames=required_frames,
        )
        if decision.seed_only or not decision.eligible:
            return LedgerUpdateResult(None, decision, False)

        record_fn = getattr(self.signal_ledger, "_record_signal_internal", None)
        if record_fn is None:
            record_fn = getattr(self.signal_ledger, "record_signal", None)

        entry = None
        if record_fn is not None:
            try:
                entry = record_fn(
                    code=decision.code,
                    name=name,
                    price=price,
                    pct=pct,
                    deviation=deviation,
                    row=row,
                    volume_score=volume_score,
                    signal_source=str(source or "ATS").upper(),
                    signal_tag=signal_tag,
                    _from_service=True,
                    **ledger_kwargs
                )
            except TypeError:
                entry = record_fn(
                    code=decision.code,
                    name=name,
                    price=price,
                    pct=pct,
                    deviation=deviation,
                    row=row,
                    volume_score=volume_score,
                    signal_source=str(source or "ATS").upper(),
                    signal_tag=signal_tag,
                    **ledger_kwargs
                )

        return LedgerUpdateResult(entry, decision, entry is not None)

    def update_tdx(self, sig_dict: Dict[str, Any], row: Any = None, observed_at: Any = None) -> LedgerUpdateResult:
        sig_dict = dict(sig_dict or {})
        code = sig_dict.get("code")
        name = sig_dict.get("name", code or "")
        price = float(sig_dict.get("price", 0.0) or 0.0)
        pct = float(row.get("percent", 0.0) or 0.0) if row is not None and hasattr(row, "get") else 0.0
        deviation = float(row.get("dff", 0.0) or 0.0) if row is not None and hasattr(row, "get") else 0.0

        if observed_at is None:
            observed_at = sig_dict.get("time_str") or self._extract_tick_time(row)

        # TDX/OrderMon is already an external event confirmation; it still obeys
        # session gating, but does not require a second polling frame.
        result = self.update_candidate(
            code=code,
            name=name,
            price=price,
            pct=pct,
            deviation=deviation,
            row=row,
            source="TDX",
            observed_at=observed_at,
            required_frames=1,
            signal_tag="🔔",
        )
        entry = result.entry
        if entry is not None:
            period_cn = sig_dict.get("period_cn", "")
            period_str = "[%s] " % period_cn if period_cn else ""
            flag_label = sig_dict.get("flag_label", "TDX信号")
            direction_cn = sig_dict.get("direction_cn", "买入")
            entry.tdx_label = "🔔 TDX %s%s" % (period_str, flag_label)
            entry.tdx_price = price
            entry.tdx_time_str = sig_dict.get("time_str", "")
            entry.signal_tag = "🔔"
            entry.tdx_boost = 150.0
            entry.promote(
                "WATCH",
                reason="通达信实盘信号: %s%s (%s)" % (period_str, flag_label, direction_cn),
            )
        return result

    def sync_projection(
        self,
        universe_manager: Any,
        *,
        df_realtime: Any = None,
        price_pct_cache: Optional[Dict[str, Any]] = None,
    ) -> None:
        universe_manager.sync_from_ledger(
            self.signal_ledger,
            df_realtime=df_realtime,
            price_pct_cache=price_pct_cache,
        )

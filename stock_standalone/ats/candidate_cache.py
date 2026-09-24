# -*- coding: utf-8 -*-
"""Session-aware candidate confirmation cache.

Premarket/auction observations are isolated as seeds and never written into the
trading SignalLedger. Intraday candidates must survive consecutive frames
before they are allowed to enter the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from threading import RLock
from typing import Any, Callable, Dict, Optional, Tuple

from ats.session_clock import (
    MARKET_TIMEZONE, SessionPhase, is_fresh_signal_allowed, is_seed_only,
    market_datetime, market_now, phase_at,
)


@dataclass(frozen=True)
class CandidateDecision:
    code: str
    source: str
    phase: SessionPhase
    consecutive_frames: int
    required_frames: int
    eligible: bool
    seed_only: bool
    reason: str
    payload: Dict[str, Any]
    seed_payload: Dict[str, Any]


class CandidateCache:
    """Thread-safe, date-scoped candidate confirmation cache."""

    def __init__(self, required_frames: int = 2, max_gap_seconds: float = 8.0,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self.required_frames = max(1, int(required_frames))
        self.max_gap_seconds = max(0.1, float(max_gap_seconds))
        self._clock = clock or market_now
        self._lock = RLock()
        self._trading_day = ""
        self._seeds: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._active: Dict[Tuple[str, str], Dict[str, Any]] = {}

    @staticmethod
    def _normalize_code(code: Any) -> str:
        raw = str(code or "").strip()
        return raw.zfill(6) if raw.isdigit() and len(raw) <= 6 else raw

    def _coerce_datetime(self, value: Optional[Any]) -> datetime:
        if value is None:
            return market_datetime(self._clock())
        if isinstance(value, datetime):
            return market_datetime(value)
        if isinstance(value, (int, float)):
            # Support millisecond timestamps
            ts = float(value)
            if not math.isfinite(ts):
                raise ValueError("invalid observation timestamp")
            if ts > 1e11:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, MARKET_TIMEZONE).replace(tzinfo=None)
        if isinstance(value, str):
            text = value.strip().replace("Z", "+00:00")
            try:
                return market_datetime(datetime.fromisoformat(text))
            except ValueError:
                pass
            # Support "YYYY-MM-DD HH:MM:SS" or "YYYY/MM/DD HH:MM:SS"
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y%m%d %H:%M:%S"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    pass
            # Support "HH:MM:SS" or "HH:MM:SS.fff" by attaching current date
            for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
                try:
                    t_val = datetime.strptime(text, fmt).time()
                    return datetime.combine(market_datetime(self._clock()).date(), t_val)
                except ValueError:
                    pass
            try:
                # If numeric string timestamp
                ts_num = float(text)
                if not math.isfinite(ts_num):
                    raise ValueError("invalid observation timestamp")
                if ts_num > 1e11:
                    ts_num /= 1000.0
                return datetime.fromtimestamp(ts_num, MARKET_TIMEZONE).replace(tzinfo=None)
            except ValueError:
                pass
        raise ValueError("invalid observation timestamp: %r" % (value,))

    def _roll_day(self, day: str) -> None:
        if self._trading_day and self._trading_day != day:
            self._seeds.clear()
            self._active.clear()
        self._trading_day = day

    def observe(
        self,
        code: Any,
        *,
        source: str = "ATS",
        payload: Optional[Dict[str, Any]] = None,
        observed_at: Optional[Any] = None,
        phase: Optional[Any] = None,
        required_frames: Optional[int] = None,
    ) -> CandidateDecision:
        normalized_code = self._normalize_code(code)
        normalized_source = str(source or "ATS").strip().upper()
        key = (normalized_source, normalized_code)
        frame_target = max(1, int(required_frames or self.required_frames))
        current_payload = dict(payload or {})
        try:
            dt = self._coerce_datetime(observed_at)
            phase_value = SessionPhase(phase) if phase is not None else phase_at(dt)
        except (TypeError, ValueError, OverflowError):
            return CandidateDecision(
                code=normalized_code,
                source=normalized_source,
                phase=SessionPhase.CLOSED,
                consecutive_frames=0,
                required_frames=frame_target,
                eligible=False,
                seed_only=False,
                reason="INVALID_OBSERVATION_CONTEXT",
                payload=current_payload,
                seed_payload={},
            )
        day = dt.date().isoformat()

        with self._lock:
            self._roll_day(day)

            if is_seed_only(phase_value):
                prior = self._seeds.get(key, {})
                seed = {
                    "payload": current_payload,
                    "first_seen": prior.get("first_seen", dt.isoformat()),
                    "last_seen": dt.isoformat(),
                    "frames": int(prior.get("frames", 0)) + 1,
                    "phase": phase_value.value,
                }
                self._seeds[key] = seed
                self._active.pop(key, None)
                return CandidateDecision(
                    code=normalized_code,
                    source=normalized_source,
                    phase=phase_value,
                    consecutive_frames=0,
                    required_frames=frame_target,
                    eligible=False,
                    seed_only=True,
                    reason="PREMARKET_SEED_ISOLATED",
                    payload=current_payload,
                    seed_payload=dict(seed["payload"]),
                )

            if not is_fresh_signal_allowed(phase_value):
                self._active.pop(key, None)
                seed_payload = dict(self._seeds.get(key, {}).get("payload", {}))
                return CandidateDecision(
                    code=normalized_code,
                    source=normalized_source,
                    phase=phase_value,
                    consecutive_frames=0,
                    required_frames=frame_target,
                    eligible=False,
                    seed_only=False,
                    reason="SESSION_NOT_ELIGIBLE",
                    payload=current_payload,
                    seed_payload=seed_payload,
                )

            prior = self._active.get(key)
            consecutive = 1
            if prior is not None:
                try:
                    last_seen = self._coerce_datetime(prior.get("last_seen"))
                    gap = (dt - last_seen).total_seconds()
                except Exception:
                    gap = self.max_gap_seconds + 1.0
                if gap == 0:
                    return CandidateDecision(
                        code=normalized_code,
                        source=normalized_source,
                        phase=phase_value,
                        consecutive_frames=int(prior.get("frames", 0)),
                        required_frames=frame_target,
                        eligible=False,
                        seed_only=False,
                        reason="DUPLICATE_FRAME_IGNORED",
                        payload=dict(prior.get("payload", {})),
                        seed_payload=dict(self._seeds.get(key, {}).get("payload", {})),
                    )
                if gap < 0:
                    return CandidateDecision(
                        code=normalized_code,
                        source=normalized_source,
                        phase=phase_value,
                        consecutive_frames=int(prior.get("frames", 0)),
                        required_frames=frame_target,
                        eligible=False,
                        seed_only=False,
                        reason="OUT_OF_ORDER_FRAME_IGNORED",
                        payload=dict(prior.get("payload", {})),
                        seed_payload=dict(self._seeds.get(key, {}).get("payload", {})),
                    )
                if gap <= self.max_gap_seconds:
                    consecutive = int(prior.get("frames", 0)) + 1

            self._active[key] = {
                "payload": current_payload,
                "first_seen": prior.get("first_seen", dt.isoformat()) if prior else dt.isoformat(),
                "last_seen": dt.isoformat(),
                "frames": consecutive,
                "phase": phase_value.value,
            }
            seed_payload = dict(self._seeds.get(key, {}).get("payload", {}))
            eligible = consecutive >= frame_target
            return CandidateDecision(
                code=normalized_code,
                source=normalized_source,
                phase=phase_value,
                consecutive_frames=consecutive,
                required_frames=frame_target,
                eligible=eligible,
                seed_only=False,
                reason="CONFIRMED" if eligible else "AWAITING_CONSECUTIVE_FRAMES",
                payload=current_payload,
                seed_payload=seed_payload,
            )

    def reject(self, code: Any, source: str = "ATS") -> None:
        key = (str(source or "ATS").strip().upper(), self._normalize_code(code))
        with self._lock:
            self._active.pop(key, None)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            def _render(source_dict: Dict[Tuple[str, str], Dict[str, Any]]) -> Dict[str, Any]:
                return {
                    "%s:%s" % key: dict(value)
                    for key, value in source_dict.items()
                }
            return {
                "trading_day": self._trading_day,
                "required_frames": self.required_frames,
                "max_gap_seconds": self.max_gap_seconds,
                "premarket_seeds": _render(self._seeds),
                "active_candidates": _render(self._active),
            }

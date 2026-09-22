# -*- coding: utf-8 -*-
"""Session-aware candidate confirmation cache.

Premarket/auction observations are isolated as seeds and never written into the
trading SignalLedger. Intraday candidates must survive consecutive frames
before they are allowed to enter the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any, Dict, Optional, Tuple

from ats.session_clock import SessionPhase, is_fresh_signal_allowed, is_seed_only, phase_at


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

    def __init__(self, required_frames: int = 2, max_gap_seconds: float = 8.0) -> None:
        self.required_frames = max(1, int(required_frames))
        self.max_gap_seconds = max(0.1, float(max_gap_seconds))
        self._lock = RLock()
        self._trading_day = ""
        self._seeds: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._active: Dict[Tuple[str, str], Dict[str, Any]] = {}

    @staticmethod
    def _normalize_code(code: Any) -> str:
        raw = str(code or "").strip()
        return raw.zfill(6) if raw.isdigit() and len(raw) <= 6 else raw

    @staticmethod
    def _coerce_datetime(value: Optional[Any]) -> datetime:
        if value is None:
            return datetime.now()
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value))
        if isinstance(value, str):
            text = value.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                pass
        raise ValueError("unsupported observation timestamp: %r" % (value,))

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
        dt = self._coerce_datetime(observed_at)
        phase_value = SessionPhase(phase) if phase is not None else phase_at(dt)
        normalized_code = self._normalize_code(code)
        normalized_source = str(source or "ATS").strip().upper()
        key = (normalized_source, normalized_code)
        frame_target = max(1, int(required_frames or self.required_frames))
        current_payload = dict(payload or {})
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
                    gap = abs((dt - last_seen).total_seconds())
                except Exception:
                    gap = self.max_gap_seconds + 1.0
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

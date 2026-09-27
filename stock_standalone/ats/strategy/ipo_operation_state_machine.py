"""Seven-state IPO operation lifecycle driven by gate and execution facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
from threading import RLock
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional


class IPOOperationState(str, Enum):
    OBSERVE = "OBSERVE"
    ARMED = "ARMED"
    ENTRY_READY = "ENTRY_READY"
    ENTERED = "ENTERED"
    HOLD_T1 = "HOLD_T1"
    EXIT_READY = "EXIT_READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class StateTransition:
    code: str
    from_state: str
    to_state: str
    transition_reason: str
    as_of_time: str
    snapshot_version: str
    facts: Mapping[str, Any]


@dataclass(frozen=True)
class TransitionOutcome:
    accepted: bool
    current_state: str
    event: Optional[StateTransition] = None
    reason_code: Optional[str] = None


_ALLOWED = {
    IPOOperationState.OBSERVE: {IPOOperationState.ARMED, IPOOperationState.BLOCKED},
    IPOOperationState.ARMED: {
        IPOOperationState.ENTRY_READY, IPOOperationState.OBSERVE, IPOOperationState.BLOCKED
    },
    IPOOperationState.ENTRY_READY: {
        IPOOperationState.ENTERED, IPOOperationState.ARMED, IPOOperationState.BLOCKED
    },
    IPOOperationState.ENTERED: {IPOOperationState.HOLD_T1, IPOOperationState.EXIT_READY},
    IPOOperationState.HOLD_T1: {IPOOperationState.EXIT_READY},
    IPOOperationState.EXIT_READY: {IPOOperationState.OBSERVE, IPOOperationState.EXIT_READY},
    IPOOperationState.BLOCKED: {IPOOperationState.OBSERVE, IPOOperationState.ARMED},
}


def _positive_number(value: Any, *, allow_zero: bool = False) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (value >= 0 if allow_zero else value > 0)
    )


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


class IPOOperationStateMachine:
    """Track legal lifecycle transitions; ENTRY_READY never means a fill."""

    def __init__(self) -> None:
        self._states: Dict[str, IPOOperationState] = {}
        self._history: Dict[str, List[StateTransition]] = {}
        self._last_event_time: Dict[str, datetime] = {}
        self._lock = RLock()

    def state_for(self, code: str) -> str:
        with self._lock:
            key = code.strip() if isinstance(code, str) else code
            return self._states.get(key, IPOOperationState.OBSERVE).value

    def history_for(self, code: str) -> List[StateTransition]:
        with self._lock:
            key = code.strip() if isinstance(code, str) else code
            return list(self._history.get(key, ()))

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a detached, UI-safe view of known lifecycle states and history."""
        def thaw(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {key: thaw(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [thaw(item) for item in value]
            return value

        with self._lock:
            rows = []
            for code in sorted(self._states):
                history = self._history.get(code, ())
                rows.append({
                    "code": code,
                    "state": self._states[code].value,
                    "history_count": len(history),
                    "history": [
                        {
                            "from_state": event.from_state,
                            "to_state": event.to_state,
                            "transition_reason": event.transition_reason,
                            "as_of_time": event.as_of_time,
                            "snapshot_version": event.snapshot_version,
                            "facts": thaw(event.facts),
                        }
                        for event in history[-200:]
                    ],
                })
            return rows

    @staticmethod
    def _facts_allow(
        current: IPOOperationState,
        target: IPOOperationState,
        facts: Mapping[str, Any],
    ) -> bool:
        if current == IPOOperationState.OBSERVE and target == IPOOperationState.ARMED:
            return all(facts.get(key) is True for key in (
                "gate0_passed", "gate1_passed", "preheat_passed", "snapshot_fresh"
            ))
        if current == IPOOperationState.OBSERVE and target == IPOOperationState.BLOCKED:
            return facts.get("hard_gate_failed") is True
        if current == IPOOperationState.ARMED and target == IPOOperationState.ENTRY_READY:
            return (
                all(facts.get(key) is True for key in (
                    "gate0_passed", "gate1_passed", "gate3_passed", "gate4_passed",
                    "trade_plan_valid", "risk_allowed", "snapshot_fresh",
                ))
                and facts.get("carry_state") == "ALLOW"
                and facts.get("horse_rank") == 1
                and facts.get("is_d0") is not True
            )
        if current == IPOOperationState.ARMED and target == IPOOperationState.OBSERVE:
            return facts.get("candidate_invalidated") is True
        if current == IPOOperationState.ARMED and target == IPOOperationState.BLOCKED:
            return facts.get("hard_gate_failed") is True
        if current == IPOOperationState.ENTRY_READY and target == IPOOperationState.ENTERED:
            return (
                facts.get("fill_confirmed") is True
                and isinstance(facts.get("execution_id"), str)
                and bool(facts.get("execution_id", "").strip())
                and _positive_number(facts.get("filled_quantity"))
            )
        if current == IPOOperationState.ENTRY_READY and target == IPOOperationState.ARMED:
            return (
                facts.get("order_rejected_or_cancelled") is True
                and _positive_number(facts.get("filled_quantity"), allow_zero=True)
                and facts.get("filled_quantity") == 0
            )
        if current == IPOOperationState.ENTRY_READY and target == IPOOperationState.BLOCKED:
            return facts.get("hard_gate_failed") is True
        if current == IPOOperationState.ENTERED and target == IPOOperationState.HOLD_T1:
            return (
                _positive_number(facts.get("position_quantity"))
                and _positive_number(facts.get("sellable_quantity"), allow_zero=True)
                and facts.get("sellable_quantity") == 0
                and facts.get("t_plus_one_locked") is True
            )
        if current in {IPOOperationState.ENTERED, IPOOperationState.HOLD_T1} and target == IPOOperationState.EXIT_READY:
            return (
                facts.get("exit_triggered") is True
                and _positive_number(facts.get("position_quantity"))
                and _positive_number(facts.get("sellable_quantity"))
                and facts.get("sellable_quantity") <= facts.get("position_quantity")
                and facts.get("t_plus_one_unlocked") is True
            )
        if current == IPOOperationState.EXIT_READY and target == IPOOperationState.EXIT_READY:
            return (
                facts.get("partial_exit_fill") is True
                and _positive_number(facts.get("remaining_quantity"))
                and _positive_number(facts.get("sellable_quantity"), allow_zero=True)
                and facts.get("sellable_quantity") <= facts.get("remaining_quantity")
            )
        if current == IPOOperationState.EXIT_READY and target == IPOOperationState.OBSERVE:
            return (
                facts.get("position_closed_confirmed") is True
                and _positive_number(facts.get("remaining_quantity"), allow_zero=True)
                and facts.get("remaining_quantity") == 0
            )
        if current == IPOOperationState.BLOCKED and target in {
            IPOOperationState.OBSERVE, IPOOperationState.ARMED
        }:
            complete_rerun = all(facts.get(key) is True for key in (
                "blocking_reason_resolved", "all_gates_rerun", "snapshot_fresh"
            ))
            if not complete_rerun:
                return False
            if target == IPOOperationState.ARMED:
                return all(facts.get(key) is True for key in (
                    "gate0_passed", "gate1_passed", "preheat_passed"
                ))
            return True
        return False

    def transition(
        self,
        code: str,
        target_state: str,
        transition_reason: str,
        as_of_time: datetime,
        snapshot_version: str,
        facts: Mapping[str, Any],
    ) -> TransitionOutcome:
        if not isinstance(code, str) or not code.strip():
            return TransitionOutcome(False, IPOOperationState.OBSERVE.value, reason_code="code_missing")
        clean_code = code.strip()
        try:
            target = IPOOperationState(target_state)
        except (TypeError, ValueError):
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="target_state_invalid")
        if (
            not isinstance(transition_reason, str) or not transition_reason.strip()
            or not isinstance(snapshot_version, str) or not snapshot_version.strip()
        ):
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_metadata_missing")
        if not isinstance(as_of_time, datetime) or as_of_time.tzinfo is None:
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_time_invalid")
        try:
            if as_of_time.utcoffset() is None:
                return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_time_invalid")
            event_time = as_of_time.isoformat()
            event_time_utc = as_of_time.astimezone(timezone.utc)
        except (OverflowError, OSError, TypeError, ValueError):
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_time_invalid")
        if not isinstance(facts, Mapping):
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_facts_invalid")
        try:
            fact_copy = json.loads(json.dumps(
                dict(facts), ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ))
            if any(not isinstance(key, str) for key in fact_copy):
                raise ValueError("fact keys must be strings")
            frozen_facts = _freeze_json(fact_copy)
        except (TypeError, ValueError, OverflowError):
            return TransitionOutcome(False, self.state_for(clean_code), reason_code="transition_facts_invalid")

        with self._lock:
            current = self._states.get(clean_code, IPOOperationState.OBSERVE)
            if target not in _ALLOWED[current]:
                return TransitionOutcome(False, current.value, reason_code="transition_not_allowed")
            last_event_time = self._last_event_time.get(clean_code)
            if last_event_time is not None and event_time_utc < last_event_time:
                return TransitionOutcome(False, current.value, reason_code="transition_time_regressed")
            if not self._facts_allow(current, target, fact_copy):
                return TransitionOutcome(False, current.value, reason_code="transition_facts_incomplete")
            event = StateTransition(
                code=clean_code,
                from_state=current.value,
                to_state=target.value,
                transition_reason=transition_reason.strip(),
                as_of_time=event_time,
                snapshot_version=snapshot_version.strip(),
                facts=frozen_facts,
            )
            self._states[clean_code] = target
            self._last_event_time[clean_code] = event_time_utc
            self._history.setdefault(clean_code, []).append(event)
            return TransitionOutcome(True, target.value, event=event)

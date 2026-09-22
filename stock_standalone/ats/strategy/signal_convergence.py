# -*- coding: utf-8 -*-
"""Deterministic final-stage signal convergence for the trading command room.

This module never creates a trading decision.  It only turns already-approved
directives into one clear action per code and direction for presentation and
PAPER execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Tuple


EXIT_ACTIONS = frozenset({"SELL", "EXIT_ALL", "REDUCE", "REDUCE_30", "REDUCE_HALF", "EXIT", "STOP_LOSS"})
ENTRY_ACTIONS = frozenset({"BUY", "BUY_SCOUT", "BUY_CONFIRM"})
ROTATION_ACTIONS = frozenset({"SWITCH_SWAP", "FULL_ROTATION_SWAP"})

_EXIT_PRIORITY = {
    "EXIT_ALL": 100,
    "SELL": 100,
    "EXIT": 100,
    "STOP_LOSS": 100,
    "REDUCE": 80,
    "REDUCE_HALF": 70,
    "REDUCE_30": 60,
}
_ENTRY_PRIORITY = {"BUY_CONFIRM": 90, "BUY": 80, "BUY_SCOUT": 70}
_URGENCY_PRIORITY = {"CRITICAL": 30, "LIMIT": 20, "NORMAL": 10}


@dataclass(frozen=True)
class SignalConvergenceResult:
    directives: tuple[Any, ...]
    raw_count: int
    actionable_count: int
    entry_count: int
    exit_count: int
    rotation_count: int
    observe_count: int
    suppressed_count: int
    suppressed_reasons: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "raw_count": self.raw_count,
            "actionable_count": self.actionable_count,
            "entry_count": self.entry_count,
            "exit_count": self.exit_count,
            "rotation_count": self.rotation_count,
            "observe_count": self.observe_count,
            "suppressed_count": self.suppressed_count,
            "suppressed_reasons": list(self.suppressed_reasons),
        }


def _action(directive: Any) -> str:
    return str(getattr(directive, "action", "") or "").upper()


def _code(directive: Any) -> str:
    return str(getattr(directive, "code", "") or "").strip().zfill(6)


def _bucket(action: str) -> str:
    if action in EXIT_ACTIONS:
        return "EXIT"
    if action in ENTRY_ACTIONS:
        return "ENTRY"
    if action in ROTATION_ACTIONS:
        return "ROTATION"
    return "OBSERVE"


def _priority(directive: Any) -> tuple[int, int, float]:
    action = _action(directive)
    action_priority = _EXIT_PRIORITY.get(action, _ENTRY_PRIORITY.get(action, 0))
    urgency_priority = _URGENCY_PRIORITY.get(
        str(getattr(directive, "urgency", "NORMAL") or "NORMAL").upper(), 0
    )
    try:
        rank_priority = -float(getattr(directive, "horse_rank", 999) or 999)
    except (TypeError, ValueError):
        rank_priority = -999.0
    return action_priority, urgency_priority, rank_priority


def check_exit_buy_contract(directives: Iterable[Any]) -> Tuple[bool, List[str]]:
    """
    Independent Blocking Contract: EXIT > BUY
    Verifies that no code has both an EXIT action and an ENTRY action in the given directive set.
    Returns (is_compliant, violation_reasons).
    """
    code_actions: dict[str, set[str]] = {}
    for d in directives or []:
        c = _code(d)
        a = _action(d)
        if c and a:
            code_actions.setdefault(c, set()).add(a)

    violations: list[str] = []
    for c, acts in code_actions.items():
        has_exit = any(a in EXIT_ACTIONS for a in acts)
        has_entry = any(a in ENTRY_ACTIONS for a in acts)
        if has_exit and has_entry:
            violations.append(
                f"Code {c} violates EXIT>BUY contract: coexisting EXIT ({acts & EXIT_ACTIONS}) and ENTRY ({acts & ENTRY_ACTIONS})"
            )

    return len(violations) == 0, violations


def converge_directives(directives: Iterable[Any]) -> SignalConvergenceResult:
    """Keep the highest-priority directive for each code/bucket.

    Exit directives suppress an entry for the same code in the same refresh.
    Rotation is retained independently because it represents a paired portfolio
    action rather than a second entry signal.
    """
    raw = list(directives or [])
    selected: dict[tuple[str, str], Any] = {}
    suppressed: list[str] = []

    # First collect all codes that have an EXIT directive in this refresh cycle
    exit_codes = {_code(d) for d in raw if _bucket(_action(d)) == "EXIT" and _code(d)}

    for directive in raw:
        code, action = _code(directive), _action(directive)
        if not code or not action:
            suppressed.append("INVALID_DIRECTIVE")
            continue
        bucket = _bucket(action)

        # EXIT > BUY independent blocking contract:
        # If code has an EXIT in the same refresh, any ENTRY is physically suppressed immediately.
        if bucket == "ENTRY" and code in exit_codes:
            suppressed.append("EXIT_OVERRIDES_ENTRY")
            continue

        key = (code, bucket)
        prior = selected.get(key)
        if prior is None or _priority(directive) > _priority(prior):
            if prior is not None:
                suppressed.append("DUPLICATE_LOWER_PRIORITY")
            selected[key] = directive
        else:
            suppressed.append("DUPLICATE_LOWER_PRIORITY")

    # Safety check: ensure no ENTRY remains if an EXIT exists
    for key in [item for item in selected if item[1] == "ENTRY" and item[0] in exit_codes]:
        selected.pop(key)
        suppressed.append("EXIT_OVERRIDES_ENTRY")

    ordered = sorted(
        selected.values(),
        key=lambda item: (
            {"EXIT": 0, "ROTATION": 1, "ENTRY": 2, "OBSERVE": 3}[_bucket(_action(item))],
            -_priority(item)[0],
            _code(item),
        ),
    )
    buckets = [_bucket(_action(item)) for item in ordered]
    return SignalConvergenceResult(
        directives=tuple(ordered),
        raw_count=len(raw),
        actionable_count=sum(bucket != "OBSERVE" for bucket in buckets),
        entry_count=buckets.count("ENTRY"),
        exit_count=buckets.count("EXIT"),
        rotation_count=buckets.count("ROTATION"),
        observe_count=buckets.count("OBSERVE"),
        suppressed_count=len(suppressed),
        suppressed_reasons=tuple(suppressed),
    )

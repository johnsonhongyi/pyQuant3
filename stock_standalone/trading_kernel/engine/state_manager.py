from __future__ import annotations

import threading


FLAT = "FLAT"
ARMED = "ARMED"
IN_TRADE = "IN_TRADE"
EXITING = "EXITING"
COOLDOWN = "COOLDOWN"

VALID_STATES = {FLAT, ARMED, IN_TRADE, EXITING, COOLDOWN}


class StateManager:
    """Behavior lock only: code -> state."""

    def __init__(self):
        self._states: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, code: str) -> str:
        with self._lock:
            return self._states.get(str(code), FLAT)

    def set(self, code: str, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid trade state: {state}")
        with self._lock:
            self._states[str(code)] = state

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._states)


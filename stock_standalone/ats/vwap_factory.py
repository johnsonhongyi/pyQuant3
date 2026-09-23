"""Process-wide incremental multi-horizon VWAP state for ATS consumers."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class VWAPSnapshot:
    code: str
    date: str
    time: str
    version: int
    vwap_1d: Optional[float]
    vwap_5d: Optional[float]
    vwap_10d: Optional[float]
    coverage_days: int
    current_price: Optional[float]
    structure: str
    complete_5d: bool
    complete_10d: bool
    stale: bool = False
    basis: str = "turnover"


class _SymbolState:
    __slots__ = ("days", "live_date", "live_bars", "live_totals", "last_key", "last_price", "updated_at", "version", "snapshot", "lock")

    def __init__(self) -> None:
        self.days: OrderedDict[str, list] = OrderedDict()
        self.live_date = ""
        self.live_bars: Dict[str, Tuple[float, float, float]] = {}
        self.live_totals = [0.0, 0.0, 0.0]
        self.last_key = ""
        self.last_price: Optional[float] = None
        self.updated_at = 0.0
        self.version = 0
        self.snapshot: Optional[VWAPSnapshot] = None
        self.lock = threading.RLock()


class VWAPFactory:
    """One in-process owner for per-symbol rolling VWAP state.

    `seed_frame` is the O(N) cold-start/recovery path. `update_bar` replaces an
    existing minute or appends a new one in O(1), then publishes an immutable
    snapshot for all consumers.
    """

    _instance: Optional["VWAPFactory"] = None
    _instance_lock = threading.Lock()
    _max_symbols = 2048

    @classmethod
    def get_instance(cls) -> "VWAPFactory":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._states: OrderedDict[str, _SymbolState] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _row_values(row: Any, is_index: bool = False) -> Tuple[str, str, float, float, float]:
        def get(name: str, default: Any = None) -> Any:
            if isinstance(row, dict):
                return row.get(name, default)
            try:
                return row.get(name, default)
            except AttributeError:
                return default

        date = str(get("date", ""))[:10]
        time = str(get("time_only", ""))[-5:]
        if not time:
            time = str(get("time", ""))[-5:]
        volume = max(0.0, float(get("bar_vol", get("vol", 0.0)) or 0.0))
        amount = max(0.0, float(get("bar_amt", get("amount", 0.0)) or 0.0))
        price = max(0.0, float(get("close", get("price", 0.0)) or 0.0))
        pv = price * volume if is_index else amount
        return date, time, amount, volume, pv

    def _state(self, code: str) -> _SymbolState:
        key = str(code).zfill(6)
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _SymbolState()
                self._states[key] = state
                while len(self._states) > self._max_symbols:
                    old_key, old_state = next(iter(self._states.items()))
                    if old_key == key:
                        break
                    if old_state.lock.acquire(blocking=False):
                        try:
                            self._states.pop(old_key, None)
                        finally:
                            old_state.lock.release()
                    else:
                        self._states.move_to_end(old_key)
                        break
            else:
                self._states.move_to_end(key)
            return state

    @staticmethod
    def _snapshot(code: str, state: _SymbolState, date: str, time: str, basis: str) -> VWAPSnapshot:
        dates = list(state.days)
        if state.live_totals[1] > 0 and date not in state.days:
            dates.append(date)
        dates = dates[-10:]
        totals = {d: list(state.days.get(d, [0.0, 0.0, 0.0])) for d in dates}
        if date and state.live_totals[1] > 0:
            totals[date] = state.live_totals

        def value(days: int) -> Optional[float]:
            selected = list(totals.values())[-days:]
            numerator = sum(x[2] for x in selected)
            denominator = sum(x[1] for x in selected)
            return numerator / denominator if denominator > 0 else None

        v1 = state.live_totals[2] / state.live_totals[1] if state.live_totals[1] > 0 else None
        v5, v10 = value(5), value(10)
        structure = "数据不足"
        price = state.last_price
        if len(totals) >= 10 and price is not None and v1 is not None and v5 is not None and v10 is not None:
            if price > v1 > v5 > v10:
                structure = "多周期偏强"
            elif price < v1 and v5 > v10:
                structure = "日内转弱 / 中期偏强"
            elif price < v1 < v5 < v10:
                structure = "多周期偏弱"
            else:
                structure = "多周期混合"
        return VWAPSnapshot(
            code=code,
            date=date,
            time=time,
            version=state.version,
            vwap_1d=v1,
            vwap_5d=v5,
            vwap_10d=v10,
            coverage_days=len(totals),
            current_price=price,
            structure=structure,
            complete_5d=len(totals) >= 5,
            complete_10d=len(totals) >= 10,
            basis="index_proxy" if basis == "index" else "turnover",
        )

    def seed_frame(self, code: str, frame: pd.DataFrame, is_index: bool = False) -> Optional[VWAPSnapshot]:
        """Rebuild the bounded state from an authoritative recent-bars frame."""
        if frame is None or frame.empty:
            return None
        clean = str(code).zfill(6)
        state = self._state(clean)
        with state.lock:
            state.days.clear()
            state.live_bars.clear()
            state.live_totals = [0.0, 0.0, 0.0]
            rows = frame.to_dict("records")
            parsed = [self._row_values(row, is_index) for row in rows]
            all_dates = sorted({r[0] for r in parsed if r[0]})
            if not all_dates:
                return None
            today = all_dates[-1]
            day_volumes: Dict[str, float] = {}
            for date, _, _, volume, _ in parsed:
                if date:
                    day_volumes[date] = day_volumes.get(date, 0.0) + volume
            traded_dates = sorted(date for date, volume in day_volumes.items() if volume > 0)
            previous_dates = [date for date in traded_dates if date < today][-9:]
            retained_dates = set(previous_dates + ([today] if day_volumes.get(today, 0.0) > 0 else []))
            historical_bars: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
            for date, minute, amount, volume, pv in parsed:
                if date not in retained_dates:
                    continue
                if date == today:
                    previous = state.live_bars.get(minute, (0.0, 0.0, 0.0))
                    state.live_bars[minute] = (amount, volume, pv)
                    state.live_totals[0] += amount - previous[0]
                    state.live_totals[1] += volume - previous[1]
                    state.live_totals[2] += pv - previous[2]
                else:
                    historical_bars.setdefault(date, {})[minute] = (amount, volume, pv)
            for date, bars in historical_bars.items():
                total = [0.0, 0.0, 0.0]
                for amount, volume, pv in bars.values():
                    total[0] += amount
                    total[1] += volume
                    total[2] += pv
                state.days[date] = total
            state.live_date = today
            state.last_key = parsed[-1][0] + " " + parsed[-1][1]
            state.last_price = float(rows[-1].get("close", rows[-1].get("price", 0.0)) or 0.0)
            state.updated_at = time.time()
            state.version += 1
            state.snapshot = self._snapshot(clean, state, today, parsed[-1][1], "index" if is_index else "stock")
            return state.snapshot

    def update_bar(self, code: str, bar: Dict[str, Any], is_index: bool = False) -> Optional[VWAPSnapshot]:
        """Append or revise one minute Bar and atomically publish its snapshot."""
        clean = str(code).zfill(6)
        date, minute, amount, volume, pv = self._row_values(bar, is_index)
        if not date or not minute:
            return self.get_snapshot(clean)
        state = self._state(clean)
        with state.lock:
            if state.live_date and date < state.live_date:
                return state.snapshot
            if date > state.live_date:
                if state.live_date:
                    if state.live_totals[1] > 0:
                        state.days[state.live_date] = list(state.live_totals)
                        state.days.move_to_end(state.live_date)
                state.live_date = date
                state.live_bars.clear()
                state.live_totals = [0.0, 0.0, 0.0]
                while len(state.days) > 9:
                    state.days.popitem(last=False)
            key = date + " " + minute
            previous = state.live_bars.get(minute, (0.0, 0.0, 0.0))
            state.live_bars[minute] = (amount, volume, pv)
            state.live_totals[0] += amount - previous[0]
            state.live_totals[1] += volume - previous[1]
            state.live_totals[2] += pv - previous[2]
            state.last_key = key
            state.last_price = float(bar.get("close", bar.get("price", 0.0)) or 0.0)
            state.updated_at = time.time()
            state.version += 1
            state.snapshot = self._snapshot(clean, state, date, minute, "index" if is_index else "stock")
            return state.snapshot

    def update_bars(self, code: str, bars: Iterable[Dict[str, Any]], is_index: bool = False) -> Optional[VWAPSnapshot]:
        result = None
        for bar in bars:
            result = self.update_bar(code, bar, is_index=is_index)
        return result or self.get_snapshot(code)

    def sync_frame(self, code: str, frame: pd.DataFrame, is_index: bool = False) -> Optional[VWAPSnapshot]:
        """Seed once, then reconcile only the latest minute on normal polls."""
        if frame is None or frame.empty:
            return self.get_snapshot(code)
        clean = str(code).zfill(6)
        state = self._state(clean)
        row = frame.iloc[-1].to_dict()
        date, minute, _, _, _ = self._row_values(row, is_index)
        latest_key = date + " " + minute
        with state.lock:
            needs_seed = not state.last_key
            if state.last_key and latest_key < state.last_key:
                needs_seed = True
            elif state.last_key and latest_key > state.last_key:
                previous_day = state.live_date
                if date == previous_day:
                    try:
                        old_minute = int(state.last_key[-5:-3]) * 60 + int(state.last_key[-2:])
                        new_minute = int(minute[:2]) * 60 + int(minute[3:5])
                        # Expected cadence is one minute; a larger gap triggers a bounded recovery rebuild.
                        if new_minute - old_minute > 1:
                            needs_seed = True
                    except (ValueError, TypeError):
                        needs_seed = True
            elif state.last_key == latest_key:
                old = state.live_bars.get(minute)
                _, _, amount, volume, pv = self._row_values(row, is_index)
                if old == (amount, volume, pv):
                    return state.snapshot
        if needs_seed:
            return self.seed_frame(clean, frame, is_index=is_index)
        return self.update_bar(clean, row, is_index=is_index)

    def get_snapshot(self, code: str) -> Optional[VWAPSnapshot]:
        state = self._state(str(code).zfill(6))
        with state.lock:
            return state.snapshot

    def export_states(self) -> Dict[str, Dict[str, Any]]:
        """Return a compact, pickle-safe copy for the existing RamDisk cache."""
        exported: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            items = list(self._states.items())
        for code, state in items:
            with state.lock:
                exported[code] = {
                    "days": [(d, list(v)) for d, v in state.days.items()],
                    "live_date": state.live_date,
                    "live_bars": dict(state.live_bars),
                    "live_totals": list(state.live_totals),
                    "last_key": state.last_key,
                    "last_price": state.last_price,
                    "updated_at": state.updated_at,
                    "version": state.version,
                    "basis": state.snapshot.basis if state.snapshot else "turnover",
                }
        return exported

    def restore_states(self, exported: Dict[str, Dict[str, Any]]) -> int:
        """Restore validated bounded state from a prior process cache payload."""
        restored = 0
        if not isinstance(exported, dict):
            return restored
        for code, item in exported.items():
            if not isinstance(item, dict):
                continue
            try:
                clean = str(code).zfill(6)
                days = OrderedDict(
                    (str(d)[:10], [max(0.0, float(x)) for x in values[:3]])
                    for d, values in item.get("days", [])[-9:]
                    if isinstance(values, (list, tuple)) and len(values) >= 3
                )
                live_date = str(item.get("live_date", ""))[:10]
                live_bars = {
                    str(minute): tuple(max(0.0, float(x)) for x in values[:3])
                    for minute, values in item.get("live_bars", {}).items()
                    if isinstance(values, (list, tuple)) and len(values) >= 3
                }
                totals = [max(0.0, float(x)) for x in item.get("live_totals", [0.0, 0.0, 0.0])[:3]]
                if len(totals) != 3 or len(live_bars) > 300 or len(days) > 9:
                    continue
                state = self._state(clean)
                with state.lock:
                    incoming_updated_at = float(item.get("updated_at", 0.0))
                    if state.updated_at > incoming_updated_at:
                        continue
                    state.days = days
                    state.live_date = live_date
                    state.live_bars = live_bars
                    state.live_totals = totals
                    state.last_key = str(item.get("last_key", ""))
                    state.last_price = float(item["last_price"]) if item.get("last_price") is not None else None
                    state.updated_at = incoming_updated_at
                    state.version = max(0, int(item.get("version", 0)))
                    basis = str(item.get("basis", "turnover"))
                    if live_date and state.last_key:
                        state.snapshot = self._snapshot(clean, state, live_date, state.last_key[-5:], basis)
                restored += 1
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
        return restored

    def clear(self, code: Optional[str] = None) -> None:
        with self._lock:
            if code is None:
                self._states.clear()
            else:
                self._states.pop(str(code).zfill(6), None)

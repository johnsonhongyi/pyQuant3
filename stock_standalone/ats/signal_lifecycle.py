"""Deterministic signal lifecycle contract used by scanners and replay tools."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class LifecycleState(str, Enum):
    DISCOVERED='DISCOVERED'; QUALIFYING='QUALIFYING'; WATCH='WATCH'; ARMED='ARMED'
    TRADE='TRADE'; WEAKENED='WEAKENED'; INVALIDATED='INVALIDATED'; EXPIRED='EXPIRED'

class LifecycleEvent(str, Enum):
    SESSION_OPEN='SESSION_OPEN'; QUOTE='QUOTE'; STRUCTURE_GAINED='STRUCTURE_GAINED'
    STRUCTURE_LOST='STRUCTURE_LOST'; VWAP_BREAK='VWAP_BREAK'; VWAP_RECLAIM='VWAP_RECLAIM'
    PEAK_DRAWDOWN='PEAK_DRAWDOWN'; FILL='FILL'; POSITION_SYNC='POSITION_SYNC'
    DAY_ROLLOVER='DAY_ROLLOVER'; DATA_STALE='DATA_STALE'; EXPIRE='EXPIRE'

@dataclass(frozen=True)
class Transition:
    revision: int; from_state: LifecycleState; to_state: LifecycleState
    event: LifecycleEvent; reason: str; snapshot_id: str = ''; event_time: str = ''

_ALLOWED = {
    LifecycleState.DISCOVERED:{LifecycleState.QUALIFYING, LifecycleState.EXPIRED},
    LifecycleState.QUALIFYING:{LifecycleState.WATCH, LifecycleState.DISCOVERED, LifecycleState.EXPIRED},
    LifecycleState.WATCH:{LifecycleState.ARMED, LifecycleState.WEAKENED, LifecycleState.INVALIDATED, LifecycleState.EXPIRED},
    LifecycleState.ARMED:{LifecycleState.TRADE, LifecycleState.WATCH, LifecycleState.WEAKENED, LifecycleState.INVALIDATED},
    LifecycleState.TRADE:{LifecycleState.WEAKENED, LifecycleState.INVALIDATED, LifecycleState.EXPIRED},
    LifecycleState.WEAKENED:{LifecycleState.ARMED, LifecycleState.INVALIDATED, LifecycleState.EXPIRED},
    LifecycleState.INVALIDATED:{LifecycleState.EXPIRED}, LifecycleState.EXPIRED:set(),
}

class SignalLifecycle:
    def __init__(self, state=LifecycleState.DISCOVERED, revision=0, history=None):
        self.state = LifecycleState(state)
        self.revision = max(0, int(revision or 0))
        self.history = list(history or [])
    def transition(self, event, to_state, reason='', snapshot_id='', event_time=None):
        event, to_state = LifecycleEvent(event), LifecycleState(to_state)
        if to_state == LifecycleState.WATCH and self.state == LifecycleState.WEAKENED:
            raise ValueError('same-tick weakened signal cannot revive directly to WATCH')
        if to_state not in _ALLOWED[self.state]:
            raise ValueError(f'illegal lifecycle transition {self.state}->{to_state}')
        self.revision += 1
        timestamp = event_time or datetime.now().isoformat(timespec='seconds')
        item=Transition(
            self.revision, self.state, to_state, event, str(reason),
            str(snapshot_id), str(timestamp),
        )
        self.history.append(item); self.state=to_state; return item

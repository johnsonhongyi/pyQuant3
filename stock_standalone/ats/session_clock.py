"""Trading-session gates shared by scanners and replay."""
from datetime import datetime, time
from enum import Enum
class SessionPhase(str, Enum):
    PREOPEN='PREOPEN'; AUCTION='AUCTION'; OPEN_CONFIRM='OPEN_CONFIRM'; MORNING='MORNING'
    LUNCH='LUNCH'; AFTERNOON='AFTERNOON'; CLOSE='CLOSE'; CLOSED='CLOSED'
def phase_at(value=None):
    t=(value or datetime.now()).time() if isinstance(value, datetime) else (value or datetime.now().time())
    if t < time(8,45) or t >= time(15): return SessionPhase.CLOSED
    if t < time(9,15): return SessionPhase.PREOPEN
    if t < time(9,30): return SessionPhase.AUCTION
    if t < time(9,45): return SessionPhase.OPEN_CONFIRM
    if t < time(11,30): return SessionPhase.MORNING
    if t < time(13): return SessionPhase.LUNCH
    if t < time(14,30): return SessionPhase.AFTERNOON
    return SessionPhase.CLOSE
def is_fresh_signal_allowed(phase):
    return SessionPhase(phase) in {SessionPhase.OPEN_CONFIRM,SessionPhase.MORNING,SessionPhase.AFTERNOON,SessionPhase.CLOSE}
def is_seed_only(phase): return SessionPhase(phase) in {SessionPhase.PREOPEN,SessionPhase.AUCTION,SessionPhase.LUNCH,SessionPhase.CLOSED}

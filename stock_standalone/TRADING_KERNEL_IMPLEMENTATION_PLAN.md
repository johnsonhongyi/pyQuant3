# Trading Kernel Implementation Plan

> Status: architecture finalized, implementation pending  
> Goal: build a deterministic, replayable, policy-driven trading execution kernel with hard risk gating and stateless execution.

## 1. Final Kernel Shape

The system must follow one strict execution path:

```text
RAW SIGNALS
  -> SignalCanonicalizer
  -> StateManager
  -> DecisionEngine
  -> RiskGate
  -> ExecutionAdapter
  -> Broker/Paper
  -> Journal
  -> Replay
```

This is not a multi-strategy opinion system. It is a deterministic execution kernel.

Core principle:

```text
Many signal sources.
One decision path.
Hard risk gate.
Stateless execution.
Append-only trace.
Replayable result.
```

## 2. Architecture Redlines

These rules are mandatory. Any violation is architecture regression.

### Redline 1: StateManager Is Behavior Lock Only

`StateManager` may only store:

```text
code -> state
```

Allowed states:

```text
FLAT
ARMED
IN_TRADE
EXITING
COOLDOWN
```

`StateManager` must not store:

```text
pnl
entry_price
position_size
signal_history
strategy_memory
decision_history
last_reason
account_data
```

State is a behavioral semaphore, not a strategy memory store.

### Redline 2: DecisionEngine Must Be Pure

`DecisionEngine` must be:

```text
intent = decide(signal, state)
```

It must be:

```text
deterministic
stateless
side-effect free
replayable
hashable
```

`DecisionEngine` must not access:

```text
database
filesystem
broker
account
UI state
global mutable state
runtime config loader
cache
current wall-clock time
randomness
```

Allowed imports for `decision_engine.py`:

```text
trading_kernel.core.*
typing
dataclasses
math
```

### Redline 3: RiskGate Is A One-Way Hard Gate

Allowed flow:

```text
DecisionIntent -> RiskGate -> RiskDecision
```

Forbidden flow:

```text
RiskGate -> DecisionEngine
RiskGate -> SignalCanonicalizer
ExecutionAdapter -> StateManager
```

`RiskGate` may:

```text
allow
block
reduce_size
force_exit
```

`RiskGate` must not reinterpret signal semantics or become another strategy engine.

### Redline 4: ExecutionAdapter Is Stateless IO

`ExecutionAdapter` may only send or simulate orders. It must not:

```text
create strategy decisions
change state
reinterpret risk
read UI state
perform hidden retries that duplicate orders
```

All execution must be idempotent through stable order ids.

## 3. Proposed Directory Structure

```text
trading_kernel/
  core/
    __init__.py
    signal.py              # StrategySignal
    intent.py              # DecisionIntent, DecisionReason
    risk.py                # RiskDecision, ApprovedOrder
    trace.py               # KernelTrace

  engine/
    __init__.py
    signal_canonicalizer.py
    state_manager.py       # behavior lock only
    decision_engine.py     # pure function only
    risk_gate.py           # hard constraints only

  execution/
    __init__.py
    execution_adapter.py   # stateless base adapter
    paper_adapter.py       # deterministic paper execution

  observability/
    __init__.py
    journal.py             # append-only log
    replay.py              # deterministic replay
    trace_hasher.py        # stable hashing

  tests/
    test_redline_enforcement.py
    test_import_boundaries.py
    test_single_flow.py
    test_decision_determinism.py
    test_replay_equivalence.py
```

## 4. Core Immutable Models

All kernel-facing models should be immutable.

```python
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class StrategySignal:
    code: str
    name: str
    ts: str
    source: str
    signal_type: str
    price: float
    features: Mapping[str, Any]


@dataclass(frozen=True)
class DecisionReason:
    regime: str
    setup: str
    sector_heat: float
    sector_rank: int | None
    is_leader: bool
    breakout: bool
    volume_ratio: float
    dff: float
    dff_positive: bool
    price_above_vwap: bool
    confidence_inputs: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class DecisionIntent:
    code: str
    action: str
    size_pct: float
    stop_price: float | None
    confidence: float
    reason: DecisionReason
    expires_at: str


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    final_action: str
    final_size_pct: float
    reject_context: Mapping[str, Any]
    order: object | None


@dataclass(frozen=True)
class KernelTrace:
    trace_id: str
    raw_event_hash: str
    signal_hash: str
    state: str
    intent_hash: str | None
    risk_hash: str | None
    execution_hash: str | None
    timestamp: str
```

## 5. Anti-Regression Test System

Architecture tests are required before real implementation expands.

### 5.1 StateManager Redline Test

```python
def test_state_manager_is_pure_behavior_lock():
    forbidden = {
        "pnl",
        "entry_price",
        "position_size",
        "signal_history",
        "strategy_memory",
        "decision_history",
        "last_reason",
    }
    attrs = set(dir(StateManager))
    assert not (attrs & forbidden)
```

### 5.2 DecisionEngine Import Boundary Test

`decision_engine.py` must not import:

```text
os
sys
sqlite3
pandas
numpy
tkinter
PyQt5
PyQt6
requests
broker SDK
trade_gateway
db_utils
config loader
```

### 5.3 Decision Purity Test

```python
def test_decision_engine_is_deterministic():
    outputs = [decide(signal, state) for _ in range(100)]
    hashes = [stable_hash(o) for o in outputs]
    assert len(set(hashes)) == 1
```

### 5.4 Single Flow Test

Rules:

```text
DecisionEngine must not import RiskGate.
RiskGate must not import DecisionEngine.
ExecutionAdapter must not import StateManager.
Journal must not affect engine output.
```

## 6. Phase Plan

### Phase 0: Redline Documentation And Tests

Deliverables:

```text
TRADING_KERNEL_IMPLEMENTATION_PLAN.md
trading_kernel/tests/test_redline_enforcement.py
trading_kernel/tests/test_import_boundaries.py
trading_kernel/tests/test_single_flow.py
```

Acceptance:

```text
Architecture tests fail if DecisionEngine imports forbidden modules.
Architecture tests fail if StateManager grows strategy memory.
```

### Phase 1: MVP Kernel Skeleton

Deliverables:

```text
immutable core dataclasses
StateManager behavior lock
pure DecisionEngine
RiskGate hard constraints
append-only Journal
stable hash helper
```

Acceptance:

```text
Same StrategySignal + same state -> identical DecisionIntent hash across 100 runs.
```

### Phase 2: Existing Signal Bypass Integration

First signal source:

```text
SectorFocusController.get_decision_queue()
```

Flow:

```text
decision_queue item
  -> SignalCanonicalizer
  -> StrategySignal
  -> StateManager
  -> DecisionEngine
  -> RiskGate
  -> Journal
```

Rules:

```text
No order execution.
No UI behavior changes.
No existing signal path replacement.
Only append deterministic traces.
```

Acceptance:

```text
One trading session can run without changing current UI behavior.
Every consumed signal has one KernelTrace.
```

### Phase 3: Replay Engine And Deterministic Runner

Replay flow:

```text
read historical raw_event
canonicalize again
rebuild state
decide again
risk evaluate again
compare original trace with replay trace
```

Acceptance:

```text
Same raw event stream replayed twice produces identical KernelTrace sequence.
Replay diff pinpoints any mismatch field.
```

### Phase 4: Paper Trading

Deliverables:

```text
PaperExecutionAdapter
PositionBook
AccountSnapshot
OrderJournal
PnL tracking
```

Rules:

```text
PositionBook may store entry_price and pnl.
StateManager must not.
ExecutionAdapter must not decide.
```

Acceptance:

```text
BUY -> HOLD -> SELL simulated loop works.
PnL is recorded.
Reject reasons are structured.
Replay reproduces paper outcomes.
```

### Phase 5: RiskGate Hardening

Initial constraints:

```text
single stock max position
single sector max exposure
total exposure cap
daily loss limit
single trade stop loss
cooldown after consecutive losses
expired signal block
high extension no-chase block
blacklist block
non-trading-session block
```

Acceptance:

```text
Every block/reduce has structured reject_context.
RiskGate does not import DecisionEngine.
RiskGate does not reinterpret StrategySignal reason.
```

### Phase 6: Decision Flow UI Panel

Add read-only panel:

```text
Trading Kernel Decision Flow
```

Columns:

```text
timestamp
code
name
state
action
size_pct
confidence
risk_allowed
reject_code
stop_price
trace_id
reason_summary
```

Acceptance:

```text
User can inspect what the kernel wanted to do, why it wanted to do it, and why RiskGate allowed or blocked it.
```

### Phase 7: Human Confirmation Mode

Flow:

```text
DecisionIntent
  -> RiskGate approved
  -> UI confirmation
  -> ExecutionAdapter
```

Rules:

```text
Confirmation belongs to UI, not ExecutionAdapter.
Manual override must be journaled with override_reason.
```

Acceptance:

```text
Manual confirmation does not mutate DecisionIntent.
Manual size change is recorded as override metadata.
```

### Phase 8: Live Broker Adapter

Deliverables:

```text
BrokerExecutionAdapter
OrderIdempotencyManager
BrokerPositionSync
KillSwitch
```

Live preconditions:

```text
Paper mode stable for at least 10 trading days.
Replay equivalence test passes.
All architecture tests pass.
RiskGate enabled.
KillSwitch available.
Broker account synced.
```

Acceptance:

```text
Duplicate order ids do not place duplicate orders.
Broker disconnect blocks new entries.
KillSwitch immediately disables new execution.
```

### Phase 9: Full Auto Mode

Mode ladder:

```text
OBSERVE      # trace only
PAPER        # simulated execution
CONFIRM      # user-approved execution
LIVE_AUTO    # fully automatic execution
```

Default mode:

```text
OBSERVE
```

LIVE_AUTO hard requirements:

```text
trading session active
broker connected
account synced
RiskGate enabled
KillSwitch off
daily loss not breached
kernel version locked
replay tests passing
```

## 7. First Implementation Target

Do not start by covering every existing signal source.

First target:

```text
SectorFocusController.get_decision_queue()
```

Minimal first complete flow:

```text
decision_queue item
  -> StrategySignal
  -> state
  -> DecisionIntent
  -> RiskDecision
  -> KernelTrace
  -> Journal
  -> Replay equivalence
```

## 8. Final Acceptance Criteria

The project is ready for automatic trading only when:

```text
All signals enter one decision flow.
DecisionEngine is deterministic and side-effect free.
RiskGate is measurable and structured.
ExecutionAdapter is stateless and idempotent.
Journal is append-only.
Replay produces equivalent traces.
Paper trading loop is complete.
Confirm mode is stable.
Live mode has KillSwitch and broker sync.
```

The success metric is not "can place orders".

The success metric is:

```text
same input event stream -> same decision trace -> same risk result -> same execution replay
```


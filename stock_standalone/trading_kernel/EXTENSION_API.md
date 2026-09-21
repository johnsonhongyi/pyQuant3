# Trading Kernel extension API 1.0

`KernelGateway` is the only supported boundary for ATS, strategy plug-ins and
future broker modules. Callers must not import `kernel_service`, adapters or the
state manager directly.

## Stable entry points

- `capabilities()` performs a version/capability handshake.
- `submit(DecisionRequest)` is the in-process typed decision endpoint.
- `submit_mapping(payload)` is the JSON/IPC-friendly endpoint. Unknown fields
  are ignored so additive upgrades remain compatible.
- `get_positions()`, `get_account_snapshot()`, `get_order_history()` and
  `get_state_snapshot()` expose read models.
- `reconcile_state()` aligns position and strategy state data.

## Reserved extension ports

- Strategy: `register_strategy_provider(provider)`; provider implements
  `decide(signal, state)`.
- Execution: `register_execution_adapter(mode, adapter)`; adapter implements
  `submit_order`, `cancel_order`, `get_positions` and `get_account_snapshot`.
- State: `register_state_store(store)`; store implements `get`, `set` and
  `snapshot`.
- Audit: `register_event_sink(sink)`; sink implements `append(record)`.

The built-in PAPER adapter remains the account authority during validation.
CONFIRM and LIVE_AUTO are reserved execution modes; registering a broker adapter
does not bypass the kernel risk gate, state machine, idempotency or audit path.

## Compatibility policy

The API uses `major.minor` versioning. A caller with the same major version is
accepted; a different major version receives `INCOMPATIBLE_API_VERSION` before
entering the decision kernel. New optional request fields and capabilities may
be added in minor releases. Existing fields and meanings remain stable within
major version 1.

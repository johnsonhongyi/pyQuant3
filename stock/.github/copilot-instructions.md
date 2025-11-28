# Copilot Instructions — pyQuant3/stock

This file gives concise, actionable guidance so an AI coding agent can quickly be productive in this repository.

Key goals:
- Understand the runtime topology (which scripts are entrypoints and how they are started).
- Follow repository-specific conventions (global state, `JohnsonUtil` helpers, `filter.ini`, `GlobalValues`).
- Know integration points (data files, ramdisk/`tdx_last_df`, JSONData/TDX modules, UI hooks).

Architecture & Big Picture
- Primary scripts (monitors): `sina_Monitor.py`, `instock_Monitor.py`, `singleAnalyseUtil.py` — these are long-running data consumers that fetch/merge live data and produce terminal/GUI output.
- Utility modules: `JohnsonUtil/*` (shared constants `johnson_cons` as `ct`, logger `LoggerFactory`, and `commonTips` as `cct`) provide global helpers and conventions used everywhere.
- Data access: `JSONData/tdx_data_Day.py` and related modules provide TDX/sina data; the code expects a shared on-disk snapshot (e.g. `tdx_last_df.h5` or ramdisk path) that other scripts wait for before starting.
- Realtime components: `RealtimeSignalManager.py` encapsulates signal detection logic (accepts a `get_df_func` and produces filtered results). Use it to add or test signal rules.
- Alerts/UI: `alerts_manager.py` implements `AlertManager` and `AlertCenter` (Tkinter). Use `set_global_manager`, `check_alert`, and `open_alert_center` for compatibility with older scripts.

Developer Workflows (how to run / debug)
- On Windows the provided orchestrator is `runall.bat` (root of `stock`). It: sets working dir, starts `sina_Monitor` first, waits for TDX snapshot file (path: `G:\tdx_last_df.h5` inside the script), then starts other processes. Use it to reproduce the normal multi-process environment.
- On macOS there are mac-specific helpers in `macRun.py` that use `osascript`/AppleScript; do not run these on Windows.
- Individual script run example: `python sina_Monitor.py -d info` (scripts use `docopt(cct.sina_doc)` — pass `-d debug|info` to control logLevel).
- Long-running runs depend on `tdx_last_df`/ramdisk files. When adding or testing code that depends on that snapshot, either provide a small sample HDF5 (or adjust checks) or run the producer script that writes it.

Project-specific Conventions & Patterns
- Global helpers: import patterns like `from JohnsonUtil import johnson_cons as ct` and `from JohnsonUtil import commonTips as cct` — expect `ct` for constants and `cct` for runtime helpers (console sizing, GlobalValues, format helpers).
- Global state: `cct.GlobalValues().setkey/getkey(...)` is used pervasively instead of passing config objects. Search for `GlobalValues()` when tracking runtime flags (e.g., `resample`, `search_key`).
- Logging: use `LoggerFactory.log` and set level via docopt `-d` flag. Avoid introducing new logging systems — reuse `LoggerFactory`.
- Filters: `filter.ini` and `JSONData/stockFilter.py` contain many domain-specific filter rules. Many scripts call `cct.read_ini(..., category='sina_Monitor')` — editing `filter.ini` affects behavior across monitors.
- Terminal/GUI: scripts favor printing formatted tables via `cct.format_for_print()` and use small Tkinter windows for interactive editing (`alerts_manager.py`). Keep UI changes isolated and preserve compatibility functions (`set_global_manager`, `check_alert`).

Integration Points & External Dependencies
- External Python packages: `pandas`, `docopt`, `tkinter` (stdlib), and others. Check imports at top of scripts when adding code.
- Local packages: `JohnsonUtil`, `JSONData` — these are internal modules (treat as stable APIs). Changes to their signatures require repo-wide updates.
- On-disk artifacts:
  - `alerts_history.json`, `alerts_rules.json` (alerts persistence)
  - `tdx_last_df.h5` or ramdisk `tdx_last_df` — monitors wait for this file; `runall.bat` checks file size before starting dependent processes.

Where to look for examples
- Data flow merging: `instock_Monitor.py` and `sina_Monitor.py` call `tdd.get_append_lastp_to_df()` to merge live feed with lastp TDX snapshot — use this pattern when joining live frames with disk snapshots.
- Signal detection: `RealtimeSignalManager.py` has a compact `detect_signals()` implementation and `refresh_loop()` example for polling + apply filters.
- Alerts UI: `alerts_manager.py` shows how to persist rules/history and expose an edit UI via `AlertCenter`. Reuse `AlertManager` to avoid duplicating alert logic.

Do / Don't (concrete)
- Do: Reuse `LoggerFactory`, `ct` and `cct` utilities for consistent behavior and console formatting.
- Do: Respect `GlobalValues` keys for flags (`resample`, `search_key`, `initfilter`), and prefer reading/writing `filter.ini` via `cct.read_ini`/`setkey`.
- Don't: Replace the on-disk handshake (waiting for `tdx_last_df`) with ad-hoc polling without a config flag; instead make it configurable through `cct.GlobalValues` and `filter.ini`.

If you change runtime behavior
- Update `runall.bat` or `macRun.py` examples if you add new long-running entry scripts.
- Add a short example in `README.md` or this file showing the run order and any new required files.

Questions for the maintainers (for iteration)
- Which file(s) should be treated as the canonical entrypoint for automated testing? (currently `sina_Monitor.py` is the primary starter used by `runall.bat`).
- Is there a minimal test data snapshot for `tdx_last_df` we can include for CI / unit tests?

If this is helpful I can:
- Run quick static scans for other cross-cutting globals and list them.
- Add a small README snippet showing `python sina_Monitor.py -d info` and `runall.bat` usage.

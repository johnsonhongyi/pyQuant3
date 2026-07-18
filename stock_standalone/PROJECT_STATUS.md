# PROJECT STATUS

> This file is the surplus source of truth for project progress.
> Every AI agent MUST update this file after completing a meaningful change.

---

## Completed Work
- [x] Initial project status created
- [x] Refined type hints in `sina_data.py` (Completed in previous session)
- [x] Added type hints to `read_ini`, `is_trade_date`, `get_day_istrade_date`, `getcwd` in `JohnsonUtil/commonTips.py`
- [x] Added type hints to `get_sys_system`, `isMac`, `get_sys_platform`, `get_ramdisk_dir`, `get_ramdisk_path` in `JohnsonUtil/commonTips.py`
- [x] Added type hints to `get_today`, `to_bool` in `JohnsonUtil/commonTips.py`
- [x] Applied comprehensive type hints to `stock_logic_utils.py`, modernizing to Python 3.9+ syntax (PEP 585)
- [x] Fixed type hint application errors for `write_to_blkdfcf` and `counterCategory` in `JohnsonUtil/commonTips.py`
- [x] Created `tk_gui_modules` and refactored `instock_MonitorTK.py` with modular Mixins
- [x] Stabilized `DragonLeaderMonitorDialog` (PyQt6) and `TkDragonLeaderMonitor` (Tkinter) multi-period deviation mining filter and lifecycle management
- [x] Implemented row focus and selection preservation in `TkDragonLeaderMonitor.update_data` to eliminate UI flickering during high-frequency refreshes
- [x] Redesigned custom column selection checkboxes in `standalone_multi_period_tester.py` to be a dropdown Menubutton menu (⚙️ 自定义列 ▼), resolving horizontal space constraints in the toolbar.

---

## Current Focus
- Files: `standalone_multi_period_tester.py`, `ats/ui/dragon_monitor.py`
- Goal: Maintain stability, performance, and robustness of the stock analysis and real-time monitoring terminals.
- Tasks:
  - [x] Optimize 2D/3D multi-period relative strength mining filter (Daily: rs_d > 0.0 + Cumulative: rs_sum >= 5.0)
  - [x] Fix `AttributeError` by redirecting name lookup to `self.get_stock_name`
  - [x] Implement selection preservation during Treeview refresh ticks
  - [x] Verify atomic cross-session persistence via tempfile/replace for leaders config
- Constraints:
  - Behavior neutral on core strategy decisions, focus on reliability, latency reduction, and seamless UI response
  - Multi-process and file locking protection under Windows

---

## Known Risks / Notes
- Avoid raising unhandled exceptions in data reload/refresh pump threads; maintain fallback values or short-circuits.
- Treeview updates require iid mapping to preserve selection correctly across resets.

---

## Next Step (ONLY ONE)
1. Monitor performance during active trading hours to ensure PyQt6 and Tkinter detail windows do not introduce frame drops or locking when handling high-volume concurrent IPC.

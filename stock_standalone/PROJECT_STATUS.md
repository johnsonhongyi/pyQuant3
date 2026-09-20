# PROJECT STATUS

> This file is the surplus source of truth for project progress.
> Every AI agent MUST update this file after completing a meaningful change.

---

## Completed Work
- [x] 建立 `.agent_hub` 文件驱动多 Agent 控制面，支持任务校验、原子领取、提交、审查退回、批准归档、事件审计和状态看板。
- [x] 增加多 Agent 生命周期自动化测试，并在项目内临时目录完成 4/4 测试。
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
- Files: `.agent_hub/`, `tools/agent_hub.py`, `tests/test_agent_hub.py`
- Goal: 以 GPT/Codex 为主脑、Antigravity 为执行 Agent，完成 ATS 交易系统的可审计迭代。
- Tasks:
  - [x] 部署 P0 文件驱动编排协议和安全策略
  - [x] 创建首个只读信号链审计任务 `001`
  - [ ] 由 Antigravity 领取并完成任务 `001`，再由 GPT/Codex 审查
- Constraints:
  - 同时最多一个执行任务
  - 自动合并和自动实盘买卖保持关闭

### Previous Focus
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
- Antigravity 是否支持原生目录监控尚未确认；当前采用固定提示加 CLI 领取，后续仅在确认其 CLI/API 后增加 adapter。
- 本机 pytest 默认临时目录可能指向失效的 `G:\Temp`，Agent Hub 测试使用 `--basetemp=.pytest_temp\...`。
- Avoid raising unhandled exceptions in data reload/refresh pump threads; maintain fallback values or short-circuits.
- Treeview updates require iid mapping to preserve selection correctly across resets.

---

## Next Step (ONLY ONE)
1. 在 Antigravity 中执行 `.agent_hub/AGENT_PROMPT.md`，领取并完成任务 `001` 的现有信号链只读审计。

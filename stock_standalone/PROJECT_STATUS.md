# PROJECT STATUS

> This file is the surplus source of truth for project progress.
> Every AI agent MUST update this file after completing a meaningful change.

---

## Completed Work
- [x] 完成任务 `004`：真实 60F K线经后台批量预取并独立注入次级买点检测，彻底停止用日K冒充 60F；45 项扩展回归通过。
- [x] 完成任务 `003`：`ProactiveExitEngine` 接入交易中心，支持递进减仓/清仓、T+1 双层硬锁、TradePlan 平仓归档及冷启动守护恢复；31 项综合测试通过并审查归档。
- [x] 完成任务 `002`：长期通道次级买点 `SECONDARY_BUY` 接通 `IPOTradingCenter` 买入指令（S4 生成 `BUY_SCOUT`，S5 生成确认仓）与全局仲裁闭环，16 项关联测试 100% 绿灯，经人工核验批准归档。
- [x] 完成任务 `001` 全自动真实演练：Gemini Worker、12 项关联测试、范围检查、Codex 复审全部通过并归档。
- [x] 为 Antigravity Worker 独立注入 Clash 代理，保持 ATS/TDX 网络路径不受影响。
- [x] 部署方式 C/C1 全自动编排器，接入 Antigravity worker、Codex 主脑审查、测试白名单、文件越界检查、认证探针和 merge report。
- [x] Agent Hub 与 Orchestrator 自动化测试共 7/7 通过，任务 `001` dry-run 成功。
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
- Files: `.agent_hub/inbox/003_proactive_exit_engine_wiring.md`, `ats/strategy/ipo_trading_center.py`, `ats/proactive_exit_engine.py`
- Goal: 以 GPT/Codex 为主脑、Antigravity 为执行 Agent，完成 ATS 交易系统的出局与风控闭环。
- Tasks:
  - [x] 部署 P0 文件驱动编排协议和安全策略
  - [x] 完成任务 `001`：信号链五维缺口审计并归档
  - [x] 完成任务 `002`：次级买点决策指令与仲裁闭环并归档
  - [x] 完成任务 `003`：风控防守引擎全面接线与 A 股 T+1 卖出防守硬锁
  - [x] 完成任务 `004`：真实 60F K 线数据流接入次级买点检测
- Constraints:
  - 同时最多一个执行任务
  - 自动合并和自动实盘买卖保持关闭

### Previous Focus
- Files: `ats/strategy/ipo_trading_center.py`, `ats/ui/ipo_command_room_dialog.py`
- Goal: 次级买点 SECONDARY_BUY 接通交易中心指令与全局仲裁闭环。
- Tasks:
  - [x] S4/S5 等级受控生成 BUY_SCOUT / 确认仓指令
  - [x] 全局仲裁独立战术角色与退潮避险豁免
  - [x] 刷新幂等去重与防追高 buy_zone_max 校验
  - [x] 16 项自动化测试 100% 绿灯验证

---

## Known Risks / Notes
- Antigravity 是否支持原生目录监控尚未确认；当前采用固定提示加 CLI 领取，后续仅在确认其 CLI/API 后增加 adapter。
- 已确认本机 `agy.exe 1.2.3` 与 `codex.exe` CLI；Codex 沙箱内无法访问 Antigravity 用户登录态，真实执行需从正常桌面终端启动。
- 用户已明确授权仅对 `Risk: LOW` 任务启用 Antigravity 全工具自动批准；sandbox、范围检查、测试闸门、自动合并关闭和实盘关闭继续强制执行。
- 用户已进一步授权计划内 `LOW/MEDIUM` 研发任务连续自动推进；`HIGH` 与真实交易权限仍需单独批准。
- 本机 pytest 默认临时目录可能指向失效的 `G:\Temp`，Agent Hub 测试使用 `--basetemp=.pytest_temp\...`。
- Avoid raising unhandled exceptions in data reload/refresh pump threads; maintain fallback values or short-circuits.
- Treeview updates require iid mapping to preserve selection correctly across resets.

---

## Next Step (ONLY ONE)
1. 准备 P1 任务 `005`：建立真实历史分时离线回放与 TradePlan 复盘质量追踪套件。

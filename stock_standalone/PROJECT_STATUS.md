# PROJECT STATUS

> This file is the project-level source of truth for project progress.
> Every AI agent MUST update this file after completing a meaningful change.

---

### Completed Work
- [x] 2026-09-21：完成 P1-00 现有退出与潮汐参数统一配置化与 SSOT 对齐落地；`config/vwap_trading_rules.json` 沉淀 `trade_plan_defaults` 与 `subnew_tide_thresholds`，`ats/vwap_rule_model.py` 增加模型校验与快照导出，`ProactiveExitEngine` 与 `SubnewTideStateMachine` 无缝解耦，单元测试 5/5 绿灯，关联回归 56/56 绿灯。
- [x] 2026-09-21：更新 `design/新股检测中心和集中交易指挥室升级交易方案2.md`，以现有代码为唯一基线，校正退出参数、测试数量、已完成 P2 状态、SBC 实际路径、后续工期与验收顺序；本次仅更新计划，未执行编码。
- [x] 2026-09-21：补齐潮汐 `T1_CLIMAX_DISTRIBUTION` / `T10_MAIN_UP` 可达性及交易闭环：T1 买入/轮动绝对拦截、非核心退出与 SSS 龙头减半；T10 SSS Rank 1 龙头 Layer 1/5 保护及严格换马门槛；7 个关联测试文件合计 86 passed。
- [x] 完成任务 `009`：普通 `BUY/BUY_SCOUT/BUY_CONFIRM` 执行端可信快照、同日关联、现金与潮汐最终仓位硬闸门；最终验证 56+7 passed，compileall 通过。
- [x] 完成任务 `008`：修复多标的累计仓位与全仓轮动穿透潮汐上限、高频刷新/时钟回退异常；生成端和执行端建立双重风控，最终验证 46+7 passed。
- [x] 完成任务 `007` 独立审计产物：确认无未来数据泄漏、日内刷新幂等及仓位闸门；审计发现的 T1/T10 可达性随后已闭环。Agent Hub 中任务文件仍位于 `inbox`，待单独整理流程状态。
- [x] 完成任务 `006`：待执行退出指令防重复、灾难止损 T+1 bypass 规则 ID 双重校验；37 项测试通过并归档。
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
- Files: `ats/strategy/subnew_tide_state_machine.py`, `ats/strategy/ipo_market_sentiment_engine.py`, `design/新股检测中心和集中交易指挥室升级交易方案2.md`
- Goal: P1-01 日内成交额同比分时归一化（时段投影系数换算，消灭早盘放量假阳性）。
- Tasks:
  - [x] P0 次级买点、TradePlan、退出保护、真实 60F 数据流闭环
  - [x] T1/T10 潮汐状态可达性与交易中心/主动退出联动
  - [x] 执行端可信快照、仓位上限、现金与 T+1 双层安全闸门
  - [x] 新版 P1/P2 实施计划与现有代码参数口径对齐
  - [x] P1-00：将现有参数原样迁入统一配置并证明迁移前后行为等价
  - [ ] P1-01：日内成交额同比分时归一化与时段投影换算
  - [ ] P1-02：潮汐状态防抖滞回机制（双阈值与连续多帧确认）
  - [ ] P1-05：T1 退出执行态状态机闭环（PENDING_NEXT_DAY_EXIT）
- Constraints:
  - 同时最多一个执行任务
  - 自动合并和自动实盘买卖保持关闭
  - 真实交易网关保持隔离，接入前必须单独授权
  - 任何公式调整必须包含时段投影系数基线验证，且不得破坏历史回放数据流口径

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
- `PROJECT_STATUS.md` 曾停留在任务 004，本次已补齐任务 006~009、T1/T10 闭环与新版计划；任务 007 的 Agent Hub 文件状态仍在 `inbox`，与已完成审计产物不一致，后续需单独整理但不影响业务代码。
- 尚未实施：P1-00 参数配置化、日内成交额归一化、潮汐滞回、多进程单源快照、L0/L1/L2 调度器、T1 次日退出执行态、T10 Layer 6 回放调优、SBC 四点图元及历史归因。
- 真实成交回报、部分成交/拒单/撤单、滑点和异常冲正尚未接入；当前真实网关继续物理隔离。
- Antigravity 是否支持原生目录监控尚未确认；当前采用固定提示加 CLI 领取，后续仅在确认其 CLI/API 后增加 adapter。
- 已确认本机 `agy.exe 1.2.3` 与 `codex.exe` CLI；Codex 沙箱内无法访问 Antigravity 用户登录态，真实执行需从正常桌面终端启动。
- 用户已明确授权仅对 `Risk: LOW` 任务启用 Antigravity 全工具自动批准；sandbox、范围检查、测试闸门、自动合并关闭和实盘关闭继续强制执行。
- 用户已进一步授权计划内 `LOW/MEDIUM` 研发任务连续自动推进；`HIGH` 与真实交易权限仍需单独批准。
- 本机 pytest 默认临时目录可能指向失效的 `G:\Temp`，Agent Hub 测试使用 `--basetemp=.pytest_temp\...`。
- Avoid raising unhandled exceptions in data reload/refresh pump threads; maintain fallback values or short-circuits.
- Treeview updates require iid mapping to preserve selection correctly across resets.

---

## Next Step (ONLY ONE)
1. 按新版方案准备 P1-00 原子任务：仅将现有退出与潮汐硬编码参数迁入统一配置，补齐配置版本、范围校验、运行时快照和行为等价回归；不调整任何策略阈值。

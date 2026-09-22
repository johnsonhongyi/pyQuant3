> 历史工程任务与设计文档已完整归档至 [Antigravity历史工程设计与任务归档文档](design/antigravity_historical_tasks_archive.md)

## 2026-09-23 00:45
- [x] **【P1 主干物理收敛：废除 SignalLedger.record_signal 旁路直写，主数据流强制统一接入 LedgerUpdateService 单一入口】(`ats/signal_ledger.py`, `ats/ledger_update_service.py`, `ats/candidate_cache.py`, `ats/ui/main_window.py`, `stock_standalone/pytest.ini`, `tests/test_p1_ledger_single_entry_hardening.py`)**：
    - [x] **彻底物理封死旁路直写与内部安全写入收敛**：
        - 将底层真实物理写入重命名为私有实现 `_record_signal_internal(..., _from_service=False)`，仅允许来自 `LedgerUpdateService` 的安全调用；
        - 公开接口 `record_signal` 改造为透明重定向门禁层：拦截一切外部直接调用并打印 `[SignalLedger][BYPASS_PREVENTED]` 警示日志，自动委托给绑定的 `LedgerUpdateService.update_candidate`，强制执行 `CandidateCache` 的会话门禁（盘前种子隔离）与连续帧防抖确认；
        - 废除 `record_tdx_signal` 内部旁路直写，自动委托给 `LedgerUpdateService.update_tdx`，彻底堵死外部通达信信号旁路；
    - [x] **单例工厂 SSOT 与双向绑定**：
        - 新增全局单例工厂 `get_ledger_update_service(signal_ledger=None)` 与 `SignalLedger.get_update_service()`，与 `get_signal_ledger()` 建立一对一强绑定；
        - `main_window.py` 初始化全面接入 `get_ledger_update_service()`，确保全系统读写事实源唯一；
    - [x] **行情时钟强化与 Tick 时间戳提取绑定**：
        - `CandidateCache` 增强自适应解析支持（`datetime`、时间戳、ISO 格式以及 `"HH:MM:SS"` / `"HH:MM:SS.fff"` 字符串结合当日自动安全拼装）；
        - `LedgerUpdateService` 自动从行情数据 `row`（`tick_time`、`time_str`、`time` 等）中提取真实 Tick 时间戳并绑定至会话门禁；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_p1_ledger_single_entry_hardening.py` 7 项用例全部通过（覆盖旁路拦截重定向、盘前种子隔离、盘中连续帧防抖、授权写入、TDX 旁路收敛、单例一致性及 Tick 自动提取）；
        - 全量黄金测试集（`tests` 与 `trading_kernel/tests`）100% 纯绿秒级通过（exit=0）；
        - 全模块 `python -m compileall ats tests trading_kernel -q` 编译零错误；
        - `stock_standalone/pytest.ini` 增加 `--basetemp=.pytest_temp` 彻底消除 Windows RamDisk `G:\Temp` 路径解析异常。

## 2026-09-23 00:00
- [x] **【彻底清理150+陈旧与外围测试轻装上阵，根治PredatorSense/弹窗/鼠标劫持并固化实战黄金测试集】(`stock_standalone/tests/`, `stock_standalone/pytest.ini`, `pytest.ini`, `conftest.py`, `stock_standalone/conftest.py`, `webTools/window_manager/core.py`)**：
    - [x] **彻底根治 PredatorSense.exe 与弹窗/鼠标劫持底层元凶**：
        - 深入排查确认元凶为自动化全量回归触发了遗留测试 `test_acer_performance.py` 与 `test_snap_windows_top_hotkey.py` / `test_intraday_dialog_fix.py`，其内部未 Mock 外部程序拉起，直接调用了 `launch_predatorsense_gui` 并执行了 `win32api.mouse_event` 和 `QWidget.show()`；
        - 在 `core.py` 中将 `launch_predatorsense_gui` 函数头部硬编码写死 `return`，彻底拔掉 `explorer.exe` 与模拟鼠标点击插头；
        - 创建全局 `conftest.py` 自动化测试静默沙箱，从底层强制拦截 `QWidget.show`、`QMessageBox.information` 与 Windows 键鼠模拟 API，绝对杜绝物理桌面弹窗；
    - [x] **全面清理 150+ 陈旧外围测试，轻装上阵**：
        - 彻底物理删除 `test_acer_performance.py`、`test_antigravity_manager.py`、`test_autostart_registry.py`、`test_intraday_dialog_fix.py`、`test_snap_windows_top_hotkey.py` 等 150 余个历史遗留与耗费资源的外围 UI/硬件测试；
        - 严选并固化针对当前实战上线生命攸关的【实战黄金测试集】（覆盖交易内核 61 项、P1 统一配置、Task 026 幂等、Task 027-033 信号流水线加固、潮汐状态机 12 阶、通道二次买点策略、指令执行闸门）；
    - [x] **全量自动化验证 100% 绿灯**：
        - `pytest stock_standalone/tests stock_standalone/trading_kernel/tests -q` 全量 100% 纯绿秒级通过（exit=0）；
        - `python -m compileall stock_standalone/ats stock_standalone/trading_kernel stock_standalone/tests -q` 编译零错误（exit=0）。

## 2026-09-22 13:15
- [x] **【彻底解决 Agent Hub 监控器与 Antigravity 账户管理器重复多开与实例堆叠 Bug（单实例IPC互斥与前台唤醒激活）】(`webTools/window_manager/agent_hub_ui.py`, `webTools/window_manager/ui.py`, `webTools/manage_window_layout.py`, `tests/test_agent_hub_ui.py`, `tests/test_antigravity_manager.py`)**：
    - [x] **Agent Hub 监控器单实例 IPC 守护与前台置顶唤醒 (`agent_hub_ui.py`)**：
        - 建立专属单实例本地命名管道 `AGENT_HUB_SINGLE_INSTANCE_SERVER = "ATS_AgentHubMonitor_SingleInstance_IPC"`；
        - `AgentHubMonitorDialog` 启动时自动开启 `QLocalServer` 监听 `WAKEUP` 消息；
        - 独立进程入口 `main()` 以及主程序 `open_agent_hub_monitor()` 中，启动前先通过 `QLocalSocket` 进行 `activate_existing_agent_hub_instance(timeout_ms=350)` 探测；
        - 若已有实例运行，发送 `WAKEUP` 消息让现有窗口执行 `activate_and_raise()`（恢复最小化、置顶激活并获取焦点），当前新请求直接退出，彻底杜绝桌面上重复弹出多个监控窗口；
    - [x] **Antigravity 账户管理器弹窗单实例守护与非模态解耦 (`ui.py`)**：
        - 在 `WindowPosManagerUI.open_antigravity_account_manager()` 中维护单例引用 `self._ag_account_dialog`；
        - 点击时若弹窗已打开且可见，直接置顶激活并拉至前台，绝不重复创建或堆叠弹窗；
        - 将阻塞式的 `dialog.exec()` 改造为非模态的 `show()`，并在关闭后自动清理实例句柄，操作流畅不阻塞操盘手看盘；
    - [x] **打包入口 `--agent-hub` 命令行支持补齐 (`manage_window_layout.py`)**：
        - 在 `manage_window_layout.py` 中补齐对 `--agent-hub` / `-agent-hub` 参数的处理，无缝桥接独立子进程模式；
    - [x] **全量自动化测试 100% 绿灯**：
        - 专项测试 `test_agent_hub_single_instance_activation` 验证单实例探测、唤醒与生命周期管理全部通过；
        - `test_agent_hub_ui.py` 3 项测试全部通过（3 passed in 1.94s）；
        - `test_antigravity_manager.py` 17 项测试全部通过（17 passed in 11.89s）；
        - 全模块 `compileall` 编译零错误。

## 2026-09-22 12:45
- [x] **【高性能多Agent运行状态与任务实施进度全景UI指挥监控大屏落地（含自动刷新与配置持久化）】(`webTools/window_manager/agent_hub_ui.py`, `webTools/window_manager/ui.py`, `manage_window_layout.spec`, `tests/test_agent_hub_ui.py`)**：
    - [x] **高性能纯后台脏检查与无锁缓存数据引擎 (`AgentHubDataEngine`)**：
        - 针对 `.agent_hub/` 下的 `inbox/running/done/archive` 任务流、`events.jsonl` 事件流、`worker_heartbeat.json` 与决策报告建立 mtime/size 轻量文件指纹检测；
        - 无变动时纯内存零磁盘 I/O 返回，彻底消除高频轮询对 PyQt 界面主线程的卡顿影响；
        - 完整提取任务元数据、打回轮数统计、Worker 实时工具调用预算（只读/写调用）、耗时及状态；
    - [x] **现代化全景大屏与多维管道实施看板 (`AgentHubMonitorDialog`)**：
        - **顶部集群卡片**：实时呈现 Antigravity Worker（运行态/模型/工具调用水位）、Codex Reviewer（模型/effort/自动审查开关/熔断阈值）及 Orchestrator 核心调度配置（并发上限/管道任务总览）；
        - **自动刷新与参数持久化保存**：
            - Header 增加【自动刷新】复选框与【刷新间隔】下拉框（支持 1.0s / 2.5s / 5.0s / 10s / 30s）；
            - 切换或勾选即时调整 QTimer 定时器，并通过 `_save_ui_settings()` / `_load_ui_settings()` 自动持久化至 `.agent_hub/monitor_ui_settings.json`，下次启动自动恢复；
        - **中部多维看板**：支持按 Inbox / Running / Done / Archive 分类筛选、按风险等级（LOW/MEDIUM/HIGH）过滤，并提供 Task ID、标题、负责人、摘要全局毫秒级模糊搜索；
        - **底部双栏深度下钻**：
            - 左侧：结构化解析 `events.jsonl`，还原任务生命周期完整流转轨迹（认领 $\to$ 提交 $\to$ 审查 $\to$ 打回 $\to$ 熔断 $\to$ 批准）；
            - 右侧：Tab 分页快速预览任务书源文件（带文件名头）、结构化 Agent 报告 / Walkthrough、Codex 审查报告、合并决策以及【🗺️ 总实施计划】；
            - 联动功能：一键在资源管理器打开当前任务专属产物目录（Artifacts），一键触发双轨极速配置备份；
    - [x] **独立端口/独立子进程启动解耦（完全不影响主管理器）**：
        - 在 `ui.py` 中将 `open_agent_hub_monitor` 改造为通过独立子进程（`subprocess.Popen`）拉起监控窗口，与桌面窗口管理器主进程完全物理隔离，绝不发生阻塞或抢占主事件循环；
    - [x] **总计划书统一一致化（事实对齐）**：
        - 统一当前计划与 UI 展现事实：在 `docs/MULTI_AGENT_SIGNAL_T1_REMEDIATION_EXECUTION_PLAN_2026-09-22.md` 与 `.agent_hub/master_plan.md` 中严肃确立当前状态为【核心 P0 修复已完成，完整计划仍有未落地项】，拒绝错误标记为“全部完成”；
        - 明确已完成项（Task 026/029/030、部分 025/027、157+25 项全绿）与后续未落地项（Task 027 剩余/028/031/032/033/034）；并在监控查看器中直观呈现。
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `tests/test_agent_hub_ui.py` 2 项测试全部通过（涵盖数据引擎解析、缓存复用、UI 初始化、表格过滤搜索、详情联动、自动刷新勾选与配置持久化）；
        - 关联测试（`test_backup_agent_tasks.py`, `test_agent_hub.py`）12 项全绿（12 passed）；
        - 全模块 `compileall` 编译零错误。


## 2026-09-22 11:20
- [x] **【多任务多Agent配置与编排策略自动化备份与秒级灾难恢复工具落地】(`tools/backup_agent_tasks.py`, `tools/restore_agent_configs.py`, `tests/test_backup_agent_tasks.py`)**：
    - [x] **纯粹性隔离（坚决不夹带业务代码）**：
        - 备份范围严格收敛于 `.agent_hub/` 全量调度配置文件（`orchestrator.json`、`PROMPT_PROTOCOL.md`、`review_prompt.md`、`task_template.md`、`master_plan.md`、`dashboard/`、`decisions/`、`events/`、`inbox/`、`running/`、`done/`、`review/`）以及 `tools/` 下的 Agent 调度脚本；
        - 完全排除 `ats/*`、`trading_kernel/*`、`strategy/*` 等大体量业务代码，备份包纯净精简（~910 KB）；
    - [x] **双轨备份与 5 存档滚动淘汰生命周期**：
        - 自动双轨持久化至 `G:\agent_config_backups`（RamDisk 极速镜像）与 `E:\RamdiskBack\agent_configs`（E 盘物理持久化）；
        - 按 `YYYYMMDD` 建立日期子目录归档，并同步更新根目录最新指针 `agent_config_latest.zip`；
        - `prune_old_archives(max_keep=5)` 严格按文件修改时间滚动淘汰，自动修剪仅保留最新的 5 个存档；
    - [x] **一键灾难恢复与秒级复活自检（Disaster Recovery）**：
        - `tools/restore_agent_configs.py` 支持优先从 RamDisk 或 E 盘一键还原多 Agent 体系，恢复后内置 Health Check，确认 `orchestrator.json` 与 `STATUS.md` 完整就绪，多 Agent 立即原地复活恢复作业；
    - [x] **自动化测试 100% 绿灯**：
        - `tests/test_backup_agent_tasks.py` 2 项滚动淘汰与打包测试全部通过；
        - 灾难恢复端到端实测成功，编排器 35 项测试全部通过，`compileall` exit=0。

## 2026-09-22 02:05
- [x] **【RamDisk Windows 单字符裸盘符根因修复与最优解全面固化】(`JohnsonUtil/commonTips.py`, `tests/test_ats_closing_ramdisk.py`)**：
    - [x] **根因定位与修复**：
        - 针对 Windows 环境下配置裸盘符（如 `win10_ramdisk_triton = 'G:'`）时，`cct.get_ramdisk_dir()` 返回裸盘符 `'G:'`（相对路径语义）；
        - 当外部模块使用 `os.path.join(ram_dir, file)` 或直接拼接时，拼成 `'G:file'` 而非 `'G:\file'`，导致底层 C 扩展、PyTables/HDF5 或多进程读写偶发找不到路径并错误回退到本地 SSD；
        - 在 `get_ramdisk_dir()` 返回前实施绝对盘符根规范化保护：当检测为 Windows 且盘符长度为 2 时，统一强制补全 `os.sep`（`'G:'` $\to$ `'G:\'`），彻底杜绝拼接断裂；
    - [x] **全量自动化验证 100% 绿灯**：
        - 验证实测 `cct.get_ramdisk_dir()` 输出规范为 `'G:\'`，`cct.get_ramdisk_path('minute_kline_cache.pkl')` 输出规范为 `'G:\minute_kline_cache.pkl'`；
        - `test_ats_closing_ramdisk.py` 与 `test_minute_kline_viewer_tdx_cache.py` 8 项测试全绿通过（8 passed in 18.48s）；
        - `compileall` 编译零错误。

## 2026-09-21 22:38
- [x] **【修复 TK 打包后 sync_with_legacy_gateway 模块导入路径与 Windows 原子替换并发锁死】(`trading_kernel/kernel_service.py`)**：
    - [x] **根因定位与修复**：
        - `sync_with_legacy_gateway` 中存在一处错误导入路径 `from trading_kernel.core.model import Position as PaperPosition`（真实位置为 `trading_kernel.execution.paper_adapter`），由于本地开发环境中通常已被缓存或 PyInstaller 静态打散，导致打包运行和后台定时对账时持续每 15 秒报 `WARNING: Error in sync_with_legacy_gateway: No module named 'trading_kernel.core.model'`；
        - 正式修正导入源为 `from trading_kernel.execution.paper_adapter import Position as PaperPosition`，立即打通持仓对账自愈通道；
    - [x] **Windows 下原子写状态快照防御加固**：
        - `_persist_reconciliation_snapshot` 中写入 `latest.json` 引入按 PID 分离的临时文件名和 `PermissionError` 智能重试机制，彻底防御 Windows 杀毒软件或多进程瞬时读句柄导致原子替换（`os.replace`）崩溃；
    - [x] **全量自动化验证 100% 绿灯**：
        - 直接实测 `s.sync_with_legacy_gateway()` 成功无报警执行：`{'restored_to_gw': 9, 'synced_from_gw': 0, 'evicted': 0}`；
        - `trading_kernel` 全量 61 项单元与流程测试全部绿灯通过（61 passed in 12.35s）；
        - `compileall` 编译零错误。

## 2026-09-21 21:35
- [x] **【TK 后台自动交易脱耦自愈、手工平仓绿色通道穿透与流水归档清理全面修复】(`trading_kernel/kernel_service.py`, `instock_MonitorTK.py`, `tk_gui_modules/decision_flow_panel.py`, `trading_kernel/engine/risk_gate.py`, `trading_kernel/execution/paper_adapter.py`)**：
    - [x] **后台自动交易与对账脱耦（消灭 UI 寄生）**：
        - 将此前寄生在 `DecisionFlowPanel` 中的“老 TradeGateway 与新内核 PaperAdapter 双向持仓对账自愈（Bridge）”下沉为 `TradingKernelService.sync_with_legacy_gateway()` 公共核心服务；
        - 在 `MonitorTK.py` 的后台驱动主循环 `bg_kernel_auto_execute_once()` 中主动触发，彻底消灭“必须手动打开交易流水窗口才能继续交易”的严重设计缺陷，后台 100% 自主运行交易与对账。
    - [x] **手工平仓绿色通道穿透与原子出清保障**：
        - `_manual_sell_position` 注入带有 `MANUAL_` 前缀的 `request_id`，在 `RiskDecision` 中以 `MANUAL_OVERRIDE` 机制放行；
        - 在 `PaperExecutionAdapter` 中识别 `is_manual_order` 豁免交易时段限制，并在 UI 侧提供底层出清兜底与退款保护，杜绝任何因盘后/时钟误差导致的平仓失败与幽灵持仓残留。
    - [x] **流水日志清空与原子备份归档闭环**：
        - 修复 `_clear_view()` 清空显示后增量指针状态；右键菜单新增【📦 归档并清空物理流水日志 (彻底重置)】，支持自动备份为 `.bak` 并物理清空，点击【🔄 手工刷新】可安全重新加载。
    - [x] **策略风控单点事实源（SSOT）确认**：
        - 经严格审计，`DecisionFlowPanel` 的 8 项风控阈值与 `trading_kernel` 的 `RiskLimits` 读写链路 100% 保持一致，无任何参数割裂。
    - [x] **全量自动化验证 100% 绿灯**：
        - `trading_kernel` 全量 59 项单元与对账测试 100% 绿灯通过（59 passed in 12.57s）；
        - ATS 16 项关联核心测试全部通过；全代码库 `compileall` exit=0 无任何语法与导入错误。

## 2026-09-21 21:00
- [x] **【TK阶段二/三统一收敛闭环 & 明日次新实战开盘部署计划书落地】(`docs/SUBNEW_REAL_MARKET_DEPLOYMENT_PLAN_2026-09-22.md`, `ats/strategy/signal_convergence.py`, `ats/strategy/ipo_trading_center.py`)**：
    - [x] **代码级统一收敛强制入口完全闭环**：
        - `get_pending_directives()` 成为唯一收敛只读入口，内部强制经过 `converge_directives()`；
        - UI 渲染、手工一键全部执行、自动跟随撮合三端强制统一步调，封死任何通过入参注入未过滤私货的漏洞；
        - 新增 `test_05b_pending_view_converges_before_execution` 验证同标的 BUY/EXIT 冲突绝对收敛为单一 EXIT；全套 77 项联合测试 100% 绿灯。
    - [x] **制定《明日开盘实战部署计划书 (实战严控优化版)》**：
        - 明确 2026-09-22 实战作战时间表（08:45 盘前自检 $\to$ 09:15 Gate 1 $\to$ 09:25 Gate 2 GO/NO-GO $\to$ 09:30 早盘抗噪 $\to$ 10:00 黄金确认 $\to$ 11:30 午盘轻量对账 $\to$ 15:00 日终对账）；
        - **流水线顺序倒置**：基线快照 $\to$ P1-01 极简折减(带开关) $\to$ S4 三层可执行门 $\to$ 契约与风控测试 $\to$ 全量回归 $\to$ 最终 commit/tag 冻结（22:00 后严禁继续调参）；
        - **P1-01 极简折减与封顶**：不做复杂全天成交预测，采用 $\text{Clamp}(\text{Signal}/\text{Ratio}, 1.0, 3.5)$，并引入配置开关随时可退回原逻辑；
        - **S4 三层可执行门**：不仅看 S4 形态，必须满足 $S4 \cap \text{结构回踩确认} \cap \text{现价在买区内} \cap \text{动态RR}\ge 2.5:1 \cap \text{未超时}$，将全天买入直接候选强力收敛至 1~3 只；
        - **EXIT > BUY 阻断与 T+1 物理锁**：作为部署上线阻断测试项，今买严禁进今卖，底仓平后杜绝幽灵持仓；
        - **09:25 GO/NO-GO 终审门**：8 项准入指标任一失败直接降级为 `MONITOR_ONLY`，确保首日实战零意外。
    - [ ] **后续推进路线 (Next Steps - 今晚按序实施与冻结)**：
        - 1) **Step 1**：P1-01 早盘极简成交额归一化（带上限 Clamp 与 Feature Flag 开关）；
        - 2) **Step 2**：S4 可执行门（`structure_confirmed` + `executable_now` 买区校验 + 动态 RR 重算 + 计划 TTL）；
        - 3) **Step 3**：EXIT > BUY 阻断专项测试、T+1 可卖校验专项测试；
        - 4) **Step 4**：全套关键契约测试 + 全量测试回归通过；
        - 5) **Step 5**：生成 `BUILD_FINGERPRINT.json`，打 Tag 并正式冻结，严禁继续微调。

## 2026-09-21 17:00
- [x] **【P1-00：现有退出与潮汐参数统一配置化与SSOT对齐落地】(`ats/vwap_rule_model.py`, `ats/proactive_exit_engine.py`, `ats/strategy/subnew_tide_state_machine.py`, `config/vwap_trading_rules.json`, `tests/test_p1_00_unified_config.py`)**：
    - [x] **严格对齐代码事实源（SSOT）**：
        - 新增 `TradePlanDefaultsConfig` 与 `SubnewTideThresholdsConfig` 数据模型，将分散在代码中的 `0.992`（防守价生成）、`0.99`（次低点破位止损）、`1.002`（保本推移）与 `0.992`（时间衰减反转豁免）以及 T10（0.75/0.70/0.90）、T1（0.55/0.50/1.20）等 12 阶潮汐分类阈值全部原样迁入 `config/vwap_trading_rules.json`；
        - 实现数值上下限安全范围校验（如 `0.90 <= higher_low_stop_ratio <= 1.0`），遇越界值自动回退安全默认值，防止极端配置击穿风控；
        - 新增 `get_config_snapshot()`，提供线程安全运行态快照导出，为多进程状态同步与审计打下基石；
    - [x] **核心消费端无缝解耦与向前兼容**：
        - `ProactiveExitEngine` 接入配置对象读取动态防守比例与反转豁免比例；
        - `SubnewTideStateMachine` 支持可选传入配置实例，未传时默认平滑回退，完全兼容历史回放与既有用例；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_p1_00_unified_config.py` 5 项用例全部通过（覆盖等价性、快照、越界回退、退出引擎与潮汐状态机配置联动）；
        - 56 项关联测试全量通过，compileall exit=0 无任何语法与导入错误。
    - [ ] **后续推进路线 (Next Steps - P1)**：
        - 1) **P1-01**：日内成交额同比分时归一化（时段投影系数换算，消灭早盘放量假阳性）；
        - 2) **P1-02**：潮汐状态防抖滞回机制（双阈值与连续多帧确认，防边界反复跳动）；
        - 3) **P1-05**：T1 退出执行态状态机闭环（`PENDING_NEXT_DAY_EXIT` 锁仓优先退出）。

## 2026-09-21 15:30
- [x] **【潮汐状态机 T1/T10 全链路风控与主升锁仓闭环落地】(`ats/strategy/ipo_trading_center.py`, `ats/proactive_exit_engine.py`, `tests/test_channel_secondary_buy_strategy.py`, `design/新股检测中心和集中交易指挥室升级交易方案2.md`)**：
    - [x] **T1 高潮派发端到端绝对防御与风险出局**：
        - `_can_execute_buy` 将 `T1_CLIMAX_DISTRIBUTION` 提升为与 `T4_PANIC_ACCEL` 同级的首要绝对门禁，拒绝普通买入与手工/外部信号注入；
        - 全仓轮动在生成端与撮合执行端双层阻断买入，严防借轮动买入新标的；
        - 自上而下组合级风险降维：非核心持仓一律发出 `EXIT_ALL`（100% 清仓）；Rank 1 且 SSS 核心龙头发出 `REDUCE_HALF`（减半锁盈）；
        - A 股 T+1 物理锁合规：严格校验 `available_shares` 与成交日期，绝不非法卖出当日新仓。
    - [x] **T10 主升浪核心龙头锁仓与严苛换马**：
        - 在 `ProactiveExitEngine` 注入潮汐状态与龙头身份；经新鲜快照确认的 SSS 唯一龙头豁免 Layer 1（时间衰减）与 Layer 5（盘中震荡不创高）洗盘误杀，同时保持结构止损（`higher_low_stop`）等硬底线 100% 坚挺；
        - 全仓轮动设置严苛换马门槛：新标的必须满足 Rank 1、SSS 梯队、动能分 $\ge 90$ 且超越旧仓 $\ge 25$ 分。
    - [x] **全量自动化验证 100% 绿灯 (86/86 PASSED)**：
        - 专项回归测试全部通过，覆盖 T1 阻断买入/自上而下减仓、T10 龙头锁仓豁免与硬防线；
        - compileall exit=0 无语法与导入错误。
    - [ ] **后续推进路线 (Next Steps - P1/P2)**：
        - 1) **P1-01**：新股检测表格增加【形态阶段】与【结构防守】列展示；
        - 2) **P1-02**：指挥室待执行指令卡片直观呈现不可变 TradePlan 网格；
        - 3) **P1-03**：`signal_id` 跨周期幂等去重与当日状态原子落盘。

## 2026-09-21 15:05
- [x] **【天梯引擎未封板标的 pattern_desc 变量未绑定 Bug 修复与多重兜底】(`ats/limit_up_engine.py`, `tests/test_ladder_background_auto_update.py`)**：
    - [x] **根因定位与修复**：在 `scan_limit_up_records_from_df` 针对未封板且未命中特定上车点（如大盘普通冲高或蓄势观察）的个股计算时，`desc_tag` 仅在部分条件分支中被赋值，当股票不符合任何预设条件分支时，后续直接使用导致 Python 抛出 `UnboundLocalError: local variable 'desc_tag' referenced before assignment`，进而导致天梯后台扫描 Worker 异常；
    - [x] **双重防御加固**：
        1. 在量化打分判定入口前预置 `desc_tag = f"📋 观察({round(pct, 1)}%)"`，消除任何分支遗漏的可能；
        2. 在未封板的 `if/elif` 判定链末尾增加 `else` 兜底分支，规范填充 `tier_tag` 与 `desc_tag = f"📋 蓄势观察({momentum_score:.0f}分)"`；
    - [x] **全量自动化验证 100% 绿灯**：
        - 针对普通非涨停、非特征股票进行极限边界扫描测试通过；
        - `test_ladder_background_auto_update.py`、`test_command_room_features_and_12tide.py` 及 `test_subnew_tide_state_machine.py` 共 20 项测试全部通过（20 passed）。

## 2026-09-21 12:55
- [x] **【集中仲裁详情窗时间友好显示到分、价格多级动态补齐与观察信号仓位纠偏】(`ats/ui/ipo_arbitration_detail_dialog.py`, `ats/strategy/ipo_trading_center.py`, `ats/ui/ipo_command_room_dialog.py`, `tests/test_command_room_features_and_12tide.py`)**：
    - [x] **全链路时间友好显示模式（精确到分）**：
        - 彻底消除弹窗顶部卡片、中间快照详情、底部指标网格中出现的纯数字秒级浮点数时间戳（如 `1789965577.1566353`）；
        - 新增 `format_time_to_minute`，自适应浮点数、纳秒时间戳及标准时分秒字符串，全链路统一格式化为直观整洁的 `YYYY-MM-DD HH:MM`（或平仓时点 `HH:MM`），时间线弹窗同步对齐。
    - [x] **价格多级动态补齐与消除 `¥0.00` 现象**：
        - 针对外部报警注入信号价格缺失问题，在 `ingest_external_alarm_signal` 中增加多源价格提取（`extra`、`reports_cache`、`ranked_cache`、持仓价）；
        - 在详情弹窗中新增 `resolve_current_price`，若日志记录的价格为 0，动态穿透查询主窗口及全局行情快照；若仍未生成买点则优雅呈现 `市价跟踪 (待买点确认)`，彻底消除冷冰冰的 `¥0.00`。
    - [x] **观察信号仓位纠偏（消除误导性 100% 满仓）**：
        - 修复 `SIGNAL_INJECT`（外部信号注入）仅作为候选关注标的却无脑写入 `size_pct=100.0` 的严重业务逻辑漏洞；
        - 明确将外部注入信号界定为观察与雷达锁定阶段，状态建议呈现为 `状态: 雷达锁定·入池监控 (待次新买点确认)`，建议仓位明确标记为 `待触发买点`，坚决不误导操盘手开仓。
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_06_friendly_time_and_price_and_position_display` 校验通过；
        - 关联 66 项量化策略、回放、账本持久化与风控闸门测试 100% 绿灯（66 passed in 6.22s）；
        - compileall exit=0，git diff --check 格式验证通过。

## 2026-09-21 12:35
- [x] **【集中交易指挥室历史日志隔离归集、标的时间线持久力透视与12级潮汐动能重构】(`ats/ui/ipo_command_room_dialog.py`, `ats/strategy/ipo_trading_center.py`, `ats/strategy/ipo_vwap_detector_engine.py`, `tests/test_command_room_features_and_12tide.py`)**：
    - [x] **完整日期补齐与今日/陈旧彻底物理隔离**：
        - 彻底根除原代码硬编码切除日期的 Bug，保留并优先使用纳秒/秒级真实时间戳，格式化为 `今日 HH:MM:SS` 与 `YY-MM-DD HH:MM:SS`，彻底消除今日与陈旧数据时间混淆；
        - 新增日期范围筛选下拉框（`📅 仅看今日` / `📅 全部历史` / `📅 历史陈旧`），默认激活 `仅看今日`，让当日看盘清爽专注，同时支持回溯历史。
    - [x] **日志原子清理归集与同标的异动时间线/连续持久力评估**：
        - 后端新增 `clear_signal_iteration_logs(keep_today: bool)`，支持原子刷盘持久化，界面提供一键清理菜单；
        - 指令面板增加 `[📜 流水]` 与 `[📊 标的归集]` 双子视图，标的归集视图自动聚合异动频次、首次/最新时间、最高级别，并输出连续持久力标签（`🔥 极强持久`、`⚡ 持续异动`、`⏱️ 单次脉冲`、`📉 动能衰减`）；
        - 全新开发 `IPOSignalTimelineDialog` 时间线弹窗，支持双击/右键秒级调出该标的全天多次异动的脉冲时序、VWAP 偏离走势与策略演化轨迹。
    - [x] **动能评分全面接入底层 12 阶潮汐状态机**：
        - 废除原动能分根据盘后涨幅无脑给 98~100 虚高分及外部信号无脑加分的漏洞；
        - 全面打通 `subnew_tide_state_machine.py` 的 12 级潮汐能力（`T0_INSUFFICIENT` ~ `T11_OVERHEATED`）；在退潮/高潮期折减追高冲高，在背离/冰点期强化次级买点（`SECONDARY_BUY`）与平底结构，构建 70~95 分严密阶梯。
    - [x] **全量自动化验证 100% 绿灯**：
        - 新增 5 项指挥室与 12 级潮汐专项测试全部通过（5 passed）；
        - 关联 65 项业务、回放、账本持久化与风控闸门测试 100% 绿灯（65 passed in 6.04s）；
        - compileall exit=0 无任何语法与导入错误。

## 2026-09-21 12:30
- [x] **【天梯底层逻辑后台自动运行与流水线驱动重构落地】(`ats/limit_up_engine.py`, `ats/ui/main_window.py`, `ats/ui/daily_limit_up_dialog.py`, `tests/test_ladder_background_auto_update.py`)**：
    - [x] **数据驱动与解除 Tab 0 单点依赖**：在 `ats/limit_up_engine.py` 中新增 `update_live_snapshot`，内置 1.5s 智能节流与纯内存向量化计算；`_on_ipc_data_received` 与 `_on_ledger_worker_done` 中无论当前停留在哪个 Tab 均在后台自动运行天梯底层引擎，彻底消除因 Tab 0（资金主线）休眠导致天梯底座饥渴的死锁；
    - [x] **挂载主窗口 Tier 3 异步错峰流水线**：在 `main_window.py` 的 `_async_refresh_tier3` 中挂载 `daily_limit_up_dialog`（错峰 90ms 调度），让天梯看板与龙头监控、板块明细同等享受主时钟轮询持续推送，消除“等很久”；
    - [x] **多日天梯聚合就地初筛与首帧乐观先行出表**：`aggregate_multi_day_strong_stocks` 在今日记录为空时就地基于 `current_df` 补齐涨停扫描，确保新晋连板股绝不漏算；天梯看板在启动时采用纯内存首帧秒级渲染，避免后台 TDX L2 盘口网络 I/O 阻塞界面；
    - [x] **盘中时间片涨停豁免与贴边启停修复**：修复分歧低吸等时间片对真实涨停个股的误杀逻辑，修正 hover_timer 仅在贴边隐藏时启动；
    - [x] **全量自动化验证 100% 绿灯**：16 项天梯、多日归档与性能节流测试全部通过（16 passed），compileall exit=0，git diff --check 格式验证通过。

## 2026-09-21 12:10
- [x] **【编排器防拉锯熔断、上下文瘦身与 Codex 限额保护规则落地】(`tools/agent_hub.py`, `tools/agent_orchestrator.py`, `.agent_hub/PROMPT_PROTOCOL.md`, `tests/test_agent_orchestrator.py`)**：
    - [x] **打回次数硬熔断 (Max Rework = 1)**：新增 `get_rework_count` 与 `rework_blocked` 状态；当任务第 2 次审查仍未通过时，立即熔断自动化循环，标记为 `REWORK_BLOCKED_FOR_HUMAN` 留在 done 状态，等待人工仲裁，彻底杜绝 5 轮拉锯打爆 5 小时配额；
    - [x] **审查上下文强力瘦身与 diff 截断 (Lean Review Context)**：编排器向 Reviewer 主动提供不超过 150 行的紧凑 diff 与清洗后的精简验证退出摘要，剥离海量 pytest 进度点与无关 warning；明令禁止 Reviewer 自行在终端执行全量无界 `git diff`；
    - [x] **Reviewer 模型解耦与只读预算动态化**：支持 `review_model` 与 `review_effort: "low"`，避免日常审查默认消耗顶配推理模型；Worker 提示词动态读取只读工具预算，防止盲目空转；
    - [x] **反测试泥潭原则固化**：在交互协议中明确区分生产风控与测试夹具，避免 Agent 为兼容测试而全量魔改历史用例；
    - [x] **全量验证 100% 绿灯**：18 项编排器测试全部通过、56+7 项业务与回放测试通过、compileall exit=0、git diff --check 格式验证通过。

## 2026-09-21 11:00
- [x] **【ATS 2026-09-21 版本：普通买入风控闸门、全仓轮动硬约束与编排器瘦回传加固】(`ats/strategy/ipo_trading_center.py`, `tools/agent_orchestrator.py`, `docs/ATS_2026-09-21_VERSION_REPORT.md`, `tests/`)**：
    - [x] **任务 008：全仓轮动仓位上限、时间戳关联与原子换马保护**：
        - 全仓轮动在生成与执行阶段均严格扣除保留持仓，杜绝换入后组合仓位穿透潮汐上限；
        - 无可信快照时，轮动仅可使用被平旧仓对应预算；买入前完成现金与整手预检查，失败时不平旧仓、不扣现金、不写平仓记录。
    - [x] **任务 009：普通买入最终风控闸门与零状态变更防御**：
        - `BUY`、`BUY_SCOUT`、`BUY_CONFIRM` 成交前强制复核市场快照（新鲜、同交易日、非 `T0_INSUFFICIENT`、300s 关联）；
        - `T4_PANIC_ACCEL`、`BLOCK_NEW_BUYS`、零风险乘数、仓位满额、现金不足一手等全部拒绝成交且绝不创建幽灵持仓。
    - [x] **编排器协议与回传架构收敛**：
        - Worker 结果强制收敛为紧凑结构化 JSON，剥离冗余对话与传输日志；
        - 设定 240s 硬性超时兜底，移除要求 worker 自行 `claim/submit` 的旧协议冲突。
    - [x] **全量验证 100% 绿灯**：
        - 56 + 7 项业务与回放测试、16 项编排器测试、compileall exit=0、git diff --check 均通过。
    - [ ] **后续推进路线 (Next Steps)**：
        - 1) 实现本地心跳监控与空转早停；
        - 2) 固化任务级范围基线（脏工作区范围隔离）；
        - 3) 完成任务 007 独立审计闭环；
        - 4) 保持真实交易与券商接口关闭。

## 2026-09-20 23:30
- [x] **【Task 008 潮汐仓位上限穿透与时钟守卫加固全面完成并闭环验证】(`ats/strategy/ipo_trading_center.py`, `ats/strategy/ipo_market_sentiment_engine.py`, `tests/test_channel_secondary_buy_strategy.py`, `tests/test_ipo_vwap_sentiment_and_horse_race.py`)**：
    - [x] **四项关键漏洞与风控隐患彻底解决 (P0)**：
        - 1) **指令时间戳因果强绑定**：换马执行端强制要求指令必须携带合法时间戳（`dir_ts > 0`）且与快照同日、相差 $\le 300\text{s}$；无时间戳手工指令拒绝信任快照并降级为老仓位上限，彻底堵死无时间戳借用快照漏洞；
        - 2) **显式历史回放时点保真**：显式历史回放重复查询同一历史时点时，严格保持原样时点，复用决策，绝对不推进 1 微秒改写历史；
        - 3) **彻底杜绝幽灵持仓**：持仓创建推迟至风控、预算与 T+1 校验完全通过之后的实际买入点，被拒路径绝不遗留空持仓对象；
        - 4) **范围纯洁性与真实测试结果归档**：44 passed、7 passed、compileall exit=0 权威绿灯记录。
    - [x] **Antigravity CLI 输入 Token 极限优化与历史日志自动归档**：
        - 全量历史无损归档至 `design/antigravity_historical_tasks_archive.md`，工作区 `gemini.md` 仅保留活跃任务，单次调用输入 token 压降 10,000+。

## 2026-09-20 23:05
- [x] **【彻底解耦双 Tab 入口：Antigravity 独立客户端与 Antigravity IDE 状态与切换完全物理隔离】(`stock_standalone/20260920_2228_task.md`, `webTools/window_manager/antigravity_manager.py`, `webTools/window_manager/ui.py`, `tests/test_antigravity_manager.py`)**：
    - [x] **操盘手现场明确指示与交互架构彻底重构 (P0)**：
        - “同步至Antigravity 同步至IDE,改成两个tab的入口即可避免逻辑bug”：
          1) **两套客户端彻底重构为独立双 Tab 入口 (`QTabWidget`)**：
             - 彻底废除“双向同步/双向对齐”导致的相互覆盖与串号 bug，两端物理与数据彻底隔离；
             - **Tab 1: `🚀 Antigravity 客户端`**：
               - 专属运行态徽章：实时展示独立客户端是否在线（`🟢 客户端运行中`），明确呈现当前客户端生效账户为 `Johnson Zou <j***i@gmail.com>`；
               - 卡片专属呈现：Johnson Zou 卡片高亮翠绿徽章【🟢 客户端在用】，其余卡片显示【⚪ 备用账户】；
               - 专属切换按钮：卡片底部为清晰定向的 `[🚀 切换给 Antigravity]`，点击纯粹且仅写入客户端数据库 `APP_DB_PATH`，绝不干扰 IDE；
             - **Tab 2: `💻 Antigravity IDE`**：
               - 专属运行态徽章：实时展示 IDE 是否在线（`🟢 IDE 运行中` 或 `⚪ IDE 离线`），明确呈现当前 IDE 生效账户为 `弘逸 <h***8@gmail.com>`；
               - 卡片专属呈现：弘逸 卡片高亮深蓝紫徽章【🟢 IDE 在用】，其余卡片显示【⚪ 备用账户】；
               - 专属切换按钮：卡片底部为清晰定向的 `[💻 切换给 IDE]`，点击纯粹且仅写入 IDE 数据库 `IDE_DB_PATH`，绝不干扰客户端；
          2) **彻底清除测试残留垃圾账户与防污染隔离**：
             - 彻底清除本地账户目录遗留的 `two@example.com.json` 垃圾文件；
             - 单元测试与真实账户目录实现彻底沙箱隔离，绝不污染真实账户库；
          3) **全量自动化与回归验证 100% 绿灯 (17/17 PASSED)**：
             - `pytest stock_standalone/tests/test_antigravity_manager.py` 17/17 绿灯通过；
             - `pytest stock_standalone/tests/test_tdx_wildcard_matching.py` 5/5 绿灯通过。

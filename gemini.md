> 历史工程任务与设计文档已完整归档至 [Antigravity历史工程设计与任务归档文档](stock_standalone/design/antigravity_historical_tasks_archive.md)

## 2026-09-23 10:20
- [x] **【Antigravity 切换系统凭据打包环境零依赖加固与 EXE 重新打包构建】(`webTools/window_manager/antigravity_manager.py`, `manage_window_layout.spec`, `tests/test_antigravity_manager.py`, `dist/manage_window_layout.exe`)**：
    - [x] **根因定位与排查确证**：
        - 现场抓取运行进程发现用户实机运行的 `D:\JohnsonProgram\instockMonitorTK\manage_window_layout.exe` 创建时间为 `0:23`（早于我们底层的 ctypes 改造时间）；
        - 旧版本严重依赖 `win32cred` / `win32crypt` 导致打包运行缺少 pywin32 C 扩展而抛异常，触发“未能读取系统安全凭据 gemini:antigravity”；
    - [x] **纯 Windows 原生 API 零外部依赖全面加固**：
        - `_capture_app_credential_snapshot` 采用 `ctypes.WinDLL("Advapi32.dll")` 的 `CredReadW` 搭配 `ctypes.string_at` 内存安全指针复制，彻底免除第三方 pywin32 丢失风险；
        - DPAPI 保护采用原生 `Crypt32.dll` (`CryptProtectData` / `CryptUnprotectData`) + `Kernel32.dll` (`LocalFree`)，实现内存与打包层面的双重安全；
        - `_write_generic_credential_blob` 增加 `CredWriteW` 与 `win32cred.CredWrite` 双向 fallback，记录完整 `GetLastError`；
    - [x] **专项测试与全量回归**：
        - 编写 `tests/test_antigravity_manager.py`（Mock pywin32 彻底移除环境下验证纯 ctypes 路径 100% 健全）；3/3 纯绿通过；全量测试集与 compileall 100% 纯绿通过；
    - [x] **PyInstaller 重新打包构建与实操验证**：
        - 运行 `pyinstaller manage_window_layout.spec --clean` 成功在 `stock_standalone\dist\` 构建生成最新的 `manage_window_layout.exe`（42MB）；
        - 通过 CLI 参数 `--ag-list` 实机调用验证，打包 exe 成功加载所有账户并正常读取系统凭据。

## 2026-09-23 00:58
- [x] **【UI 决策透出与影子实盘压测长周期守护全面落地】(`ats/universe_manager.py`, `ats/ui/swing_table.py`, `ats/ui/ipo_command_room_dialog.py`, `tools/run_shadow_live_test.py`, `tests/test_ui_decision_badges_and_shadow_runner.py`)**：
    - [x] **监控表与池子决策透出与高位回撤视觉徽章（全简短中文）**：
        - `UniverseManager` 从 `SignalLedger` 自动提取 `weak_since_ts`、`tier == INACTIVE`、`peak_drawdown`（峰值回撤）与状态流转历史；
        - 直观生成并注入全简短中文徽章：`⚠️ 回撤-X.X%` / `⚠️ 动能走弱` 与 `⛔ 破位失效`；
        - `SwingStateTable` 表格渲染增强：首次发现列与决议原因列自动识别徽章，走弱标的高亮橙黄色粗体，失效标的高亮暗红色粗体，鼠标悬停单元格浮动呈现完整高位回撤历史（如 `高位回撤-4.5% (峰值+5.0%->+0.5%)`）；
    - [x] **集中交易指挥室赛马天梯与指令表决策联动（全简短中文）**：
        - 赛马排位表 `tbl_rank` 角色列与决议依据列自动对齐账本生命周期，直观标注 `[⚠️动能走弱]` / `[⚠️回撤-X.X%]` / `[⛔破位失效]`；
        - 消除操盘手买点误判盲区，对高位走弱与跌破双 VWAP 标的实施前端醒目阻断预警；
    - [x] **影子实盘压测全天候无报单长周期守护启动器 (`tools/run_shadow_live_test.py`)**：
        - 强制锁定环境为影子/纸面撮合模式（`PAPER_TRADING_ONLY = 1`），物理隔离真实报单接口；
        - 支持全天候 2~3 个交易日长周期压测，集成内存占用（RSS MB）、CPU、Tick 延迟、快照持久化率与指令流转统计；
        - 支持 `--dry-run` 极速自检，自动按交易日输出体检快照 `logs/shadow_test_report_YYYYMMDD.json`；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_ui_decision_badges_and_shadow_runner.py` 3 项测试秒级纯绿通过；
        - 核心测试集 20/20 纯绿，全模块 `compileall` 编译零错误。

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
        - 全量历史无损归档至 `stock_standalone/design/antigravity_historical_tasks_archive.md`，工作区 `gemini.md` 仅保留活跃任务，单次调用输入 token 压降 10,000+。

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

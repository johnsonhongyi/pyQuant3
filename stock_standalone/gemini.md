> 历史工程任务与设计文档已完整归档至 [Antigravity历史工程设计与任务归档文档](design/antigravity_historical_tasks_archive.md)

## 2026-09-21 21:00
- [x] **【TK阶段二/三统一收敛闭环 & 明日次新实战开盘部署计划书落地】(`docs/SUBNEW_REAL_MARKET_DEPLOYMENT_PLAN_2026-09-22.md`, `ats/strategy/signal_convergence.py`, `ats/strategy/ipo_trading_center.py`)**：
    - [x] **代码级统一收敛强制入口完全闭环**：
        - `get_pending_directives()` 成为唯一收敛只读入口，内部强制经过 `converge_directives()`；
        - UI 渲染、手工一键全部执行、自动跟随撮合三端强制统一步调，封死任何通过入参注入未过滤私货的漏洞；
        - 新增 `test_05b_pending_view_converges_before_execution` 验证同标的 BUY/EXIT 冲突绝对收敛为单一 EXIT；全套 77 项联合测试 100% 绿灯。
    - [x] **制定《明日开盘实战部署计划书》**：
        - 明确 2026-09-22 实战作战时间表（08:45 盘前自检 $\to$ 09:15 集合竞价 $\to$ 09:30 早盘抗噪 $\to$ 10:00 黄金确认 $\to$ 14:30 尾盘结算）；
        - 今晚精准落地两大核心防噪声切片：P1-01（早盘成交额分时归一化，消灭假阳性突破）与 S4/S5 强门限（盈亏比 $\ge 2.5:1$ 才进入直接买卖点，低级别信号静默于监控大表）；
        - 明确保持 PAPER/CONFIRM 运行态，严禁开启实盘券商网关。
    - [ ] **后续推进路线 (Next Steps - 明日开盘前实战切片实施)**：
        - 1) **切片 1 (P1-01)**：分时累计成交额时段投影归一化（早盘放量衰减折减）；
        - 2) **切片 2**：待执行买点门限硬卡 S4（盈亏比 $\ge 2.5:1$），S0~S3 留在检测中心大表；
        - 3) **开盘前自检**：运行全量回归，检查对账快照与构建指纹。

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

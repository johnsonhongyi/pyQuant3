# ATS 信号治理、T+1 与 PAPER 交易闭环：独立子任务执行计划

> V1.2｜2026-09-24｜实施检查点；依赖任务按顺序核验并补缺口。生产账户/数据库保持只读，不连接券商真实报单。各 G 项分别记录源码、离线验收与线上观察，缺证据时发布门保持关闭。

## 1. 目标和现状

目标链路：行情事实 → 数据质量 → Candidate → 生命周期 → S4 计划 → S5 指令 → ATS 仲裁 → TK PAPER 执行或拒绝 → 持仓对账 → UI 与盘后结果。ATS 是决策及派发入口，TK PAPER 是账户事实和纸面撮合入口；`ATS_RECEIVED` 仅为行情 IPC 确认。

| 已核实的 2026-09-23 基线 | 当前判定 |
| --- | --- |
| 候选缓存、账本服务、信号唯一键、决策徽章、量比归一化、S5/TTL、EXIT > BUY 已有源码 | 属于“源码存在”，仍需分别证明离线回放和线上包生效 |
| 线上 `live_signal_history` 当日 2,107 条，均为 `NEW`；同一表事件键唯一 | 同键幂等已见证据，跨策略噪声和状态结果闭环未验证 |
| 当日模拟成交 4 笔 SELL、0 笔 BUY | 必须查清每个 BUY 候选被哪一层接受或拒绝；不以强制产生买单作为目标 |
| PAPER 快照 51 个持仓、订单流水推导 19 个持仓，反复告警 | 对账发布门未通过，禁止据此认定账户事实源稳定 |
| 旧计划同时记载 T+1 专项通过和 118 passed、2 failed | 次日退出结论冲突，须在同一版本和夹具上重新验收 |
| 影子脚本只喂固定样例，指令数固定为 0；线上无连续报告 | dry-run 不能替代 2–3 个交易日真实链路观察 |
| 多个线上 EXE 并存，缺构建提交与运行进程对应证据 | 打包完成及线上版本一致性待证 |

### 当前实施状态

| 项目 | 当前状态 | 证据/限制 |
| --- | --- | --- |
| G00 | 部分，线上验收阻断 | 接口契约与实现盘点已记录；只读复采找到并哈希 9/23 的 PAPER 快照、TK trace、ATS 日志及两份生产 DB。SQLite 只读查询复现 `live_signal_history` 9/23 2,107 条全为 NEW、模拟日志 SELL 4/BUY 0、消息 event_key 388,993/388,993 唯一。TK 安装/临时目录构建哈希不同；历史进程与源码/EXE 提交对应仍缺。 |
| G01 | 源码与离线验收完成 | 持仓事实和 v1/v2 校验专项 10 项通过；未用线上快照验收。 |
| G02 | 源码与离线验收完成；线上差异已定位但未解释 | 只读样本确认快照 51、运行报告订单推导 19、32 个快照独有持仓在可用 716 条订单中无记录；19 个重合代码数量一致。9/22、9/23 共 2,601 条周期对账归档全部为 `LEGACY_MISMATCH`，订单没有成交/拒绝状态字段；差异持续存在但仍无权威成交来源，发布仍阻断。 |
| G03 | 核心幂等实现已存在，线上同键去重得到只读佐证 | `signal_message` 表 388,993 行均有 event_key，非空键数与 DISTINCT 键数相等；唯一索引存在。轨迹表缺 event_id，跨表审计关联尚未实现；该 DB 证据不证明跨来源语义去重。 |
| G04 | 源码与离线验收完成，线上待验 | 固定市场时区、可注入时钟、候选帧与午休/跨日边界专项通过；线上时间戳编码未核验。 |
| G05 | 源码与离线验收完成，线上/UI 待验 | SignalLifecycle 已接入真实账本与 TDX 晋级；序列化迁移事件现携带确定性 event/candidate ID、state/action/reason/source 及输入 snapshot_id；日报可读取 lifecycle history。线上状态呈现/视图一致性归 G10，旧快照仍按跨日候选重建。 |
| G06 | 部分实施，历史失败夹具和线上待验 | 延期退出恢复与 T+1 专项通过；已补底台/VWAP 止损和高潮直接 SELL 的规则 ID/层级，并在指令发布前捕获同批 tide 与同代码 signal 上下文。新增账户级 PAPER 对账未对齐时的部署门展示与执行硬阻断；延期退出专项 3 项、底台/止损/T+1 4 项通过。118/2 历史失败夹具同版本复验和多日 PAPER 链路仍未完成。 |
| G07 | Gateway 重试与对账投影源码、定向离线验收通过；线上待验 | G07 串行扩展曾包含 `trading_kernel/gateway.py` 与契约回归；本轮复核重新打开 `ats/unified_paper_account.py` 的只读对账投影，要求继承 TK reconciliation 与 `paper_execution_ready`，独立比较快照与订单推导代码集合及共有持仓股数，即使上游误报 ALIGNED，代码/股数不一致仍返回 RECONCILIATION_MISMATCH；缺报告/就绪字段时 fail-closed。指令/对账 9 项与 Gateway 契约 7 项通过；新增指令执行维度元数据透传与序列化回归。上游当前仍未为全部指令填充潮汐/跨日值，真实 G13 质量结论不变。TK PAPER 逐笔/多日观察未做，发布仍阻断。 |
| G08 | 负样本过滤代码已补，合成专项 5 项通过 | 新增检测器→ATS 指令生成路径断言：WATCH 不产生 BUY；负样本降级、显式 CLEAR/FAILED_GAP_FADE 状态、状态沿 TradePlan 传递、正向 PRE_ORDER 对照及 CLIMAX_EXIT 优先级通过。冻结历史样本、正式 S4/S5 回放、阈值召回/误杀仍未完成。 |
| G09 | 最短状态保持代码已补，专项 11 项通过 | 覆盖 9:59 保持、10:00 转移、T2 风险即时生效及既有因果刷新用例；更广阈值回放和线上指标待验。 |
| G10 | 离线视图/动作专项 5 项通过，桌面/线上待验 | 失效/过期 BUY 在右键执行前被拦截；WATCH/TRADE 及保留的真实持仓行统一展示生命周期徽章及 `snapshot_id`/`event_id`/`candidate_id`；排名和指令表 tooltip 显示可用审计 ID 与拒绝原因；指挥室账户 tooltip 展示 TK 对账及 PAPER 恢复阻断原因。三处真实视图一致性、桌面按钮和运行时审计追溯仍需 GUI 验收。 |
| G11 | ATS 影子采集、显式隔离 TK PAPER 接线、冻结版 `--shadow-live` 路由、异常轮次降级报告及非 dry-run 隔离状态硬门已补；runner 8 项、G07 关联 3 项通过，两个帮助路由检查通过；线上多日观察未做 | 无候选代码时即使 dry-run 也必须 DEGRADED；非 dry-run 缺少隔离目录会在行情扫描前降级退出；显式隔离状态目录限定在报告目录内，adapter、KernelService、Gateway 和 ATS 执行器可注入。冻结入口尚未在真实 EXE 验收，真实行情连续 2–3 日报告未取得。 |
| G12 | 分阶段性能分位采样源码已补；旧运行日志只读提取到 290 条 dispatch 批次延迟（P50 5.1s、P95 9.6s、P99 15.7s、最大 24.0s）；新埋点运行基线待采 | 旧日志没有事件日期，批次耗时也不能拆成单任务或行情读取/IPC 根因；MarketStateBus、DataFrame、序列化、Pipe/Socket 分段 P50/P95/P99 和长周期基线仍未完成。 |
| G13 | ATS/TK 实际源码形状、日报维度和闭环质量字段已补；SignalEntry lifecycle history 展开为 SignalDecisionEvent 并校验八个契约字段；有 directive_id 却缺 action/candidate/plan 时阻断，EXIT/SELL 另要求 exit_rule_id；G13/G14 定向回归 46 项通过。真实源 1219 事件虽可解析，但 trace ID 覆盖 1019/1219且重复 1，source 覆盖 1013、strategy/tide/cross-day 覆盖 0，directive=0、order=1009、关联=0，eligible=false | 支持 ATS 账本 JSON 快照及 TK 嵌套 JSONL；`HEALTHY` 仅代表解析成功。G14 仅接受全量、无重复 event_id、来源维度全覆盖、身份完整且存在 directive/order 关联的日报；真实运行闭环未验收。 |
| G14 | 12 项回放检查、影子同构建绑定、隔离 PAPER 标记、逐指令审计、坏行阻断、G13 全量质量门及连续交易日门已补；发布必须提供冻结日历并绑定原始来源文件哈希；G14 专项 40 项通过，15 文件集成回归 186 项通过（2026-09-24 复验）。实际安装版门禁返回 `MONITOR_ONLY`，13 个阻断项 | 实际样本日报不合格；安装版无指纹，冻结回放和多日 shadow 缺失，对账未对齐。缺少或哈希不一致的冻结日历均阻断。发布清单为 `docs/ats_closed_loop/G14_release_verification_2026-09-24.json`。 |
| G15 | 集成验收未通过 | 当前证据仍缺 G00 原始历史基线与源码/构建对应、G02 32 个快照独有持仓根因/权威事实源及零差异复验、G06 历史 118/2 失败夹具、G08 冻结历史样本、G10 桌面验收、G11 真实 EXE 上的 2–3 日隔离 PAPER、多日性能基线、G13 真实源和 G14 同构建发布资料。G07 离线路由回归已通过；G11 的 PAPER 注入接口已实现但未运行多日。当前 15 文件集成回归按 `--collect-only` 核得 186 项且 pytest 退出码为 0；此离线结果不替代上述运行态验收，发布保持 `MONITOR_ONLY`。 |

## 2. 不干扰规则与冻结接口

1. **文件独占**：表中每个 G 任务拥有互不重叠的源码文件；未列出的文件只读。任务按依赖串行实施，不并行编辑同一源码；生产数据库、账户文件与全局配置不写入。
2. **先冻结接口**：G00 记录以下接口的字段、版本、默认降级行为；生产者交付后消费者才开始依赖开发。接口变更必须先更新契约并通知所有消费者，不允许临时跨任务改代码。
3. **只读生产环境**：线上日志、DB、快照用于采样与哈希；迁移和故障复现在隔离副本中进行。TK 原有 PAPER 隔离保持冻结；只有持仓事实和快照正确性需要修复时，才由 G01/G02 在独占范围内做最小改动。
4. **三层验收**：每项分别记录“源码实现、离线验收、线上 PAPER 观察”。文件存在、文档勾选或一次 dry-run 均不能单独标记完成。
5. **越界处理**：若一个任务发现必须改别人持有的文件，输出接口变更请求和最小复现；原所有者接单，或在该任务完成后串行转交文件所有权。G15 只做集成验收，不代改任何源码。

| 冻结接口 | 生产者 → 消费者 | 必需字段和规则 |
| --- | --- | --- |
| PositionFactsV2 | G01/G02 → G06/G07 | code、trade_date、total_qty、sellable_qty、today_buy_qty、lots、snapshot_version；显示持仓不可代替账户事实 |
| SignalDecisionEvent | G03/G04/G05 → G06/G10/G13 | event_id、candidate_id、snapshot_id、state、action、reason_code、event_time、source；重复输入结果稳定 |
| MarketDecisionContext | G08/G09 → G06 | 特征时间、原始/归一化量、潮汐状态及版本、跨日状态、结构锚点、质量标志；缺失则降级 |
| DirectiveAuditEnvelope | G06 → G07/G10/G11/G13 | directive_id、candidate_id、plan_id、code、action、qty、price、expires_at、gate_reason、strategy_tag、tide_state、cross_day_state；结果关联 execution_id/order_id，BUY 缺维度则不满足日报质量门 |
| ReleaseManifest | G14 → G15 | Git 提交、EXE SHA256、冻结夹具哈希、报告哈希、发布门结果 |

## 3. 独立子任务

每项交付一份任务卡：输入、只允许修改的文件、依赖接口版本、复现夹具、验收命令及结果、风险、回滚检查点。实施前先审查已有代码；已有实现只补缺口，不重复建设。

| 编号 / 依赖 | 独占范围 | 交付及可验收结果 |
| --- | --- | --- |
| **G00 基线与契约，P0**；无 | `docs/ats_closed_loop/G00_*`；源码只读 | 固定 9/22–9/23 线上日志/DB/PAPER 快照来源及哈希；盘点运行进程、EXE 路径和提交；逐代码列出 51/19 差异与 0 BUY 漏斗；冻结第 2 节接口。 |
| **G01 TK 持仓事实，P0**；G00 | `trading_kernel/t1_position_facts.py`、`trading_kernel/snapshot_v2.py`；G01 专项测试 | 明确 total/sellable/today_buy/lots；旧版、损坏、跨日快照保守迁移；昨仓、今仓、混合批次、部分成交和重启恢复一致。 |
| **G02 PAPER 恢复和对账，P0**；G01 | `trading_kernel/execution/paper_adapter.py`；G02 专项测试 | 按 G01 事实恢复，逐项解释 51/19 差异，不清库或重置线上仓位；差异为 0，无法解释时给出阻断原因；保留订单关联字段。 |
| **G03 消息幂等与零价，P0**；G00 | `signal_message_queue.py`；G03 专项测试 | 事件键原子幂等、历史重复兼容、零价隔离、状态升级不被错误去重；冻结样本同事件重复 0、零价实时记录 0。 |
| **G04 会话与候选，P0**；G00 | `ats/session_clock.py`、`ats/candidate_cache.py`；G04 专项测试 | 盘前 seed 独立、连续帧确认、跨日清理、交易时钟回放；盘前首次帧不能直接晋级，重复回放输出一致。 |
| **G05 账本与生命周期，P0**；G03/G04 | `ats/ledger_update_service.py`、`ats/signal_ledger.py`、`ats/signal_lifecycle.py`；G05 专项测试 | 定义 UI/TDX/ATS/favorite 更新语义；显示快照不伪装为确认信号；WEAKENED/INVALIDATED 的原因、时间和降级可追溯；失效后不能凭旧量比回 WATCH。 |
| **G08 量能与跨日结构，P1**；G05 | `ats/strategy/ipo_vwap_detector_engine.py`；G08 专项测试 | 已增加跨日弱势高开回落过滤与原始特征审计；仍需冻结负/正样本，验负样本 BUY=0、正样本可进 S4/S5、原始及归一化量可审计。 |
| **G09 潮汐滞回，P1**；G00 | `ats/strategy/subnew_tide_state_machine.py`；G09 专项测试 | 已增加最短状态保持、急跌/数据质量例外和转移原因；进入/退出阈值沿用现有配置，需回放验证阈值边界不翻态且风险立即降级。 |
| **G06 次日退出与 ATS 仲裁，P0**；G02/G05/G08/G09 | `ats/strategy/ipo_trading_center.py`、`ats/proactive_exit_engine.py`、`ats/strategy/signal_convergence.py`；G06 专项测试 | 在同版本重现并修复底台破位和高潮退出；`EXIT_DEFERRED_T1 → NEXT_DAY_EXIT_READY → SUBMITTED → FILLED/PARTIAL/REJECTED` 可恢复；同代码唯一 EXIT 压过 BUY；产出 DirectiveAuditEnvelope。 |
| **G07 TK PAPER 指令关联，P0**；G02/G06 | `ats/unified_paper_account.py`、`trading_kernel/engine/signal_canonicalizer.py`；G07 专项测试、`trading_kernel/tests/test_extension_contracts.py`；Gateway 扩展已串行交付 | 已补 request_id 贯通和审计回写；拒绝重试语义与 Gateway 契约离线通过。补齐 ATS→TK 指令元数据适配及 TK signal canonicalizer 特征白名单，JSONL 回归验证 directive/strategy/tide/cross-day 可贯通；缺值仍按缺失处理。每条 ATS 指令的真实 TK 回执与多日 PAPER 观察仍未完成，行情 IPC 确认不计成交。 |
| **G10 UI 决策透出，P1**；G05/G06/G07 | `ats/universe_manager.py`、`ats/ui/swing_table.py`、`ats/ui/ipo_command_room_dialog.py`；G10 专项测试 | 大表、赛马和指令表同一标的的回撤/走弱/破位/当前动作/拒绝原因一致；失效或过期 BUY 不可从 UI 执行；展示可追到快照。 |
| **G11 真正的影子运行，P1**；G07/G08/G09 | `tools/run_shadow_live_test.py`、`run_ats.py`、`trading_kernel/execution/paper_adapter.py`、`trading_kernel/kernel_service.py`；G11 专项测试和日报 | 串行接管 G02 的 Paper adapter 持久化路径、G07 的 KernelService PAPER adapter 注入口；ATS EXE 通过 `--shadow-live` 启动同一 runner，必须显式使用独立目录、隔离事件日志和 PAPER 模式。实际接入 ATS 行情、候选、赛马、S5、仲裁与 PAPER 结果，计数来自组件；报告写入失败显示 DEGRADED；连续 2–3 个交易日有日报且真实报单为 0。 |
| **G12 性能定位，P1**；G00 | `instock_MonitorTK.py`；G12 指标报告 | 对 UI 阻塞、MarketStateBus 快照、DataFrame 对比/复制及 Pipe/Socket IPC 给出分阶段 P50/P95/P99；上游行情读取调用路径仍须运行态定位，只修本文件可证实的瓶颈，外部模块问题另立任务。 |
| **G13 数据质量与结果日报，P1**；G03/G05/G07 | 新文件 `tools/ats_paper_daily_report.py`；G13 报表 | 按来源、策略、潮汐、跨日路径统计新鲜度/完整度、信号漏斗、MFE/MAE、拒绝、滑点和 T+1 延迟损失；只读事实，不写生产库。 |
| **G14 构建与发布门，P0**；G01–G13 | `trading_kernel/build_fingerprint.py`、`ats.spec`、`ats/replay_release_gate.py`、`tools/verify_ats_release.py`、`tests/test_g14_replay_evidence.py`；`tests/test_signal_pipeline_hardening.py` 仅回放发布门用例；G14 清单 | 回放生产者必须提供 12 项显式检查；T+1 召回需冻结期望退出 ID，RR 用 S5 的 2.5 下限，T+1 当日买入批次卖出数来自对账材料；缺证据即 MONITOR_ONLY。提交、EXE SHA256、测试与报告相互对应；本任务不构建/部署。 |
| **G15 集成验收，P0**；G14 | `docs/ats_closed_loop/G15_*`；源码只读 | 合并已审核产物，在同一构建上核对第 5 节发布门和文件所有权；失败退回相应 G 所有者，不在验收任务内改代码。 |

G08 合并量比与跨日结构，因为二者位于同一检测器文件；G06 集中持有交易中心、退出引擎和仲裁文件。这样没有两项并行任务编辑同一源码。

## 4. 并行批次与交接

| 批次 | 可以同时进行 | 进入下一批的条件 |
| --- | --- | --- |
| A | G00 完成后：G01、G03、G04、G09、G12 | 五项互不重叠；G00 契约与基线锁定 |
| B | G02 接 G01；G05 接 G03/G04；G08 接 G05 | 每项只消费上一批的冻结接口；不交叉改文件 |
| C | G06 接 G02/G05/G08/G09；随后 G07 接 G06 | 交易中心与 TK PAPER 关联按顺序推进 |
| D | G10、G11、G13 在 G07 契约锁定后分别进行 | UI、影子工具、日报工具分别实施；G11 仅在 G02/G07 文件工作完成后串行接管并发测试，不与其他任务并行修改这些文件 |
| E | G14 统一构建；G15 最后只读验收 | 未通过者退回原所有者，重新生成其检查点与依赖报告 |

每个任务单独提交检查点，记录 commit、diff_files、输入哈希、验证结果和回滚点。线上数据库不做不可逆清理；阈值不在盘中自学习。每批先审查 Windows 多进程、文件锁、编码与接口兼容，再合并产物。

## 5. 发布阻断门槛

| 领域 | 同一提交、同一构建、同一冻结数据上的通过条件 |
| --- | --- |
| 账户 | 持仓对账差异 0；超卖 0；重复订单 0；当日新仓 SELL 0 |
| T+1 | 既定次日退出夹具召回率 100%；今仓退出意图不丢失；可卖量不超过事实源；部分成交、拒单和重启可恢复 |
| 信号 | 零价进入实时历史 0；同一事件重复 0；跨策略冗余率给出基线和解释；失效及双 VWAP 破位样本 BUY 0 |
| 决策 | 同代码同周期 EXIT 与 BUY 冲突 0；过期或 RR 不达标 S5 执行 0；每个最终指令有事实快照、原因和执行结果 |
| 发布 | 冻结回放同输入结果一致；运行 EXE 指纹等于发布提交；2–3 日全链路影子报告齐全；内存、UI、IPC 指标可比较 |

任一硬门不通过即保持 PAPER 观察并降至 `MONITOR_ONLY + EXECUTION_BLOCKED`；UI 改善和策略收益不能豁免账户、T+1 和版本门槛。真实券商适配需另立计划与授权。

## 6. 计划依据

- `docs/MULTI_AGENT_SIGNAL_T1_REMEDIATION_EXECUTION_PLAN_2026-09-22.md`：Task 025–034、信号噪声和发布门槛。
- `docs/REALTIME_SIGNAL_T1_SUSTAINABLE_EXECUTION_PLAN_2026-09-22.md`、`docs/DATA_SIGNAL_T1_CONTINUOUS_OPTIMIZATION_PLAN_2026-09-22.md`：事实到动作、T+1 次日退出、跨日结构、质量和结果评估。
- `docs/agent_hub_versions/P1_SUBNEW_S5_EXECUTABLE_GATE_VERSION_REPORT_ZH.md`：量比、S5、TTL 已有能力及逐笔 TK 审计缺口。
- `C:\Users\Johnson\.gemini\antigravity\brain\2bbe054a-8a07-44e1-ac43-2630b274c344\implementation_plan.md`：UI 徽章和全链路影子运行目标。


# G14 构建指纹与发布门

状态：校验工具及 12 项回放检查生产逻辑已实现；源码与定向回归通过，尚无同一提交上的合格构建与运行证据。既有 build_fingerprint 可核验 Git commit/dirty，但不记录 EXE hash、对账/影子报告 hash 或联合发布门。

新增 `tools/verify_ats_release.py`，只读取 EXE、指纹、回放、对账和影子报告，输出包含各文件 SHA256、Git 状态、检查项与阻断原因的 `ReleaseManifest`。任一条件不满足即输出 `MONITOR_ONLY`：工作区不干净、构建指纹提交不一致、冻结回放失败、对账未对齐、影子不足两日、PAPER 未连接或真实券商单不为零。工具不构建、不部署、不写生产数据。

补齐影子报告与发布产物的身份关联：G11 每轮记录运行 Git commit/dirty、build fingerprint 和冻结进程 EXE SHA256；发布校验逐条要求 commit、fingerprint 与发布指纹一致，且 EXE SHA256 与待发布 EXE 一致、运行时为 frozen。旧报告、源码脚本报告和身份缺项均不能通过发布门。

复核后进一步收紧：回放必须包含重复事件、零价、时间单调、对账、T+1 事实、EXIT/BUY、构建身份、失效买入、RR 下限、次日退出召回、重复订单和 T+1 当日买入批次卖出等显式通过项；缺任何键均阻断。RR 沿用 S5 `MIN_RR_THRESHOLD=2.5`。T+1 召回以冻结帧中的 `expected_t1_exit=true` 和稳定 `exit_intent_id`/`directive_id` 为期望集合，回放指令必须逐一匹配；没有期望退出样本时不能宣称 100% 召回。失效帧必须带 `candidate_id`，存在失效样本时每个入场指令也必须有可关联 `candidate_id`；S5 入场指令提供 `rr_now`/`planned_reward_risk` 或完整 TradePlan 与执行验证价。重复订单以审计包中的非空 `order_id` 检查。T+1 当日买入批次卖出数必须由对账证据显式提供 `t0_sell_count=0`；不能把防守卖出整体当违规。对账必须同时证明状态账本和持仓/订单账本 `ALIGNED`，且差异清单为空；影子报告要求合法日期、逐条 HEALTHY、TK PAPER 已连接且真实券商单为 0。

新增影子发布门校验：每日报告必须标记 `paper_execution_scope=ISOLATED`，并证明流水状态为 `ATS_ARBITRATED_ISOLATED_TK_PAPER`；每行 `directive_count` 必须等于 `paper_result_count` 和审计数组长度，数组内每条都要有 `directive_id`、`request_id`、`status`。零指令轮次可以通过该项，但不能替代 G07 的离线路由回归；任何非零指令缺回执或请求关联均阻断。JSONL 中任何非对象、格式错误或日期非法的行也会直接阻断发布，不再忽略坏行。影子日期必须覆盖至少两个连续工作日，周五到周一按连续计算；当前门禁没有内置交易所节假日日历，跨节假日缺报按保守规则阻断，补齐可信冻结日历证据前不能放行。G14 现在还必须读取并哈希 G13 日报；日报必须健康且包含至少一个可计算的跨来源/策略重叠样本、方法说明和 0–1 范围的重叠率；还须携带 `closed_loop_quality.eligible=true`、全量 event_id 覆盖、非零 linked directive、身份字段覆盖和 SignalDecisionEvent 契约覆盖，且身份与决策事件缺项数必须为 0。缺少新质量字段的旧报告也要阻断，防止沿用陈旧的 `eligible=true` 越过新门。

盘点确认 `ats.replay_release_gate` 原来仅产出 7 项基础检查，缺 5 项。G14 已将该文件及独立专项测试纳入独占范围；新增检查只接受上述显式字段，缺失证据 fail-closed。回放专项及既有信号流水线测试共 20 项通过，语法检查及 `git diff --check` 通过。当前线上/多日 PAPER 证据仍不足，代码检查全部通过也不能令发布状态转为 GO。

Python 语法检查通过。确定性缺证据冒烟通过：缺失 EXE、指纹、回放、对账和影子报告时返回 `MONITOR_ONLY`，各证据门均阻断。当前没有合格 EXE、回放/对账及多日 TK PAPER 报告，因此本任务不能被验收为 GO；工具未对真实发布文件运行。

本轮复验：`python -m pytest tests/test_g14_replay_evidence.py tests/test_signal_pipeline_hardening.py -k "g14 or replay_release_gate" -q`：32 passed，覆盖同构建、旧报告缺身份、逐指令回执关联、PAPER 隔离标记、坏行阻断、G13 信号重叠基线、非严格对账状态、缺失及负数/非有限/布尔 T+1 数量、非有限 RR/价格、无效/布尔时间戳及缺失/错误类型的 PAPER 恢复就绪标志。CLI 现要求 `--daily-report` 并把日报哈希写入 manifest。测试只使用隔离构造证据，不能替代真实构建、运行态对账或多日 TK PAPER 报告。

复核发现并修复回放门缺口：`ALIGNED_WITH_CHANGES` 不再通过账户对账检查；T+1 数量字段缺失、为负数、非有限或布尔值均阻断，不再默认或夹成零；非有限 RR/价格、无效或布尔时间戳及缺失/错误类型的 `paper_execution_ready` 均阻断。14 文件集成回归 114 项通过。线上/多日 PAPER 证据仍不足，发布保持 `MONITOR_ONLY`。


真实样本复核后补强 G13/G14：日报解析 HEALTHY 不再等同闭环合格；G14 现在要求 `closed_loop_quality` 明确通过，且日报全量 event_id 无重复、source/strategy/tide/cross-day 全覆盖、身份字段契约完整并存在非零关联指令。真实样本 1219 条中 1019 条由 TK trace ID 提供事件身份、其中 1 个重复；source 覆盖 1013 条，strategy/tide/cross-day 均缺失；directive 与关联为 0，虽有 1009 个 order ID，日报 `eligible=false`，发布门保持 MONITOR_ONLY。专项回归覆盖重复 event_id、缺身份字段和可解析但无闭环关联的日报。

2026-09-24 实际发布校验：对安装版 `ATS_Terminal.exe`、安装目录对账报告和上面的真实源日报运行 `tools/verify_ats_release.py`，输出 `G14_release_verification_2026-09-24.json`。结果 `MONITOR_ONLY`、13 个阻断项；运行 EXE SHA256 为 `ca9498d10489245ddb9c214e0052c3b0dd95f0506746004f03f74e3913b2e72a`。工作区 dirty，安装版无指纹文件，冻结回放及多日 shadow 报告缺失，对账和日报门均未通过。校验只读取安装包/报告，未构建、部署或写入运行环境。


2026-09-24 代码变更后再次只读刷新发布校验：仍为 MONITOR_ONLY、13 个阻断；EXE SHA256 仍为 ca9498d10489245ddb9c214e0052c3b0dd95f0506746004f03f74e3913b2e72a，G13 样本 SHA256 为 b6101d841caae67ef4b6426079f3caf3e57478523274986487b728eb2dcf0f60。新源码尚未形成构建指纹/EXE，多日影子和对账门未通过；仅更新工作区校验清单，未写安装目录。

2026-09-24 日期门复核：新增回归复现旧逻辑会把相隔多日的两条报告判为 GO。发布必须提供 schema v1 冻结日历（`exchange`、`source`、`as_of`、`source_sha256`、有序 `trade_dates`）和原始来源文件；校验来源文件 SHA256 与日历声明一致，并将两文件 SHA256 写入 manifest。影子日期必须在冻结日历中连续；无日历、日期格式错误、来源不可读或哈希不一致均阻断。`tests/test_g14_replay_evidence.py` 40 项通过；当前 15 文件集成回归 186 项通过（退出码 0，`--collect-only` 数量一致）。仅为离线证据；安装版发布结论仍为 MONITOR_ONLY。

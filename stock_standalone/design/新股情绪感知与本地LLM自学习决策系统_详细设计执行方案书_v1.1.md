# 新股情绪感知与本地 LLM 自学习决策系统 — 详细设计执行方案书 v1.1 (复审修订与需求追踪版)

> **文档性质**：工程级详细设计执行方案书（**仅订正对齐方案，生产代码零变动**）<br>
> **编制日期**：2026-09-26<br>
> **版本号**：v1.1<br>
> **状态**：v1.1-R5 复审修订版；D0 锚点与 SQLite 超时规格已订正，源计划仍有实施前置项
> **关联底层文档**：
> - [新股情绪感知与T1交易决策系统_计划书_v0.2.0.md](新股情绪感知与T1交易决策系统_计划书_v0.2.0.md)
> - [新股情绪感知与T1交易决策系统_计划书_v0.2.0.docx](新股情绪感知与T1交易决策系统_计划书_v0.2.0.docx)
> - [sentiment_reversal_plan.md](sentiment_reversal_plan.md)
> - [sentiment_reversal_implementation_blueprint.md](sentiment_reversal_implementation_blueprint.md)
> - [新股检测vwap动能挖掘设计.md](新股检测vwap动能挖掘设计.md)
> - [新股检测中心和集中交易指挥室升级交易方案1.md](新股检测中心和集中交易指挥室升级交易方案1.md)
> - [新股检测中心和集中交易指挥室升级交易方案2.md](新股检测中心和集中交易指挥室升级交易方案2.md)
> - [次日异动候选池_最小侵入落地计划.md](次日异动候选池_最小侵入落地计划.md)
> - [三只代表性新股核心对照表.txt](三只代表性新股核心对照表.txt)

---

## 目录

- [壹、审核问题溯源与修正对照表](#ch1)
- [贰、六层门禁与核心引擎详细规格（消除误放行）](#ch2)
  - [2.1 Gate 0: LRRM 宏观流动性与风险状态机](#ch2-1)
  - [2.2 Gate 1: IPO Regime 五态横截面状态机](#ch2-2)
  - [2.3 IPO Pre-Heat: 上市前先验潜力打分引擎](#ch2-3)
  - [2.4 IPO Live Heat: 实时动能与 6 大非线性函数](#ch2-4)
  - [2.5 Gate 2: T+1 Carry 隔夜兑现性与华大海天伪强过滤](#ch2-5)
  - [2.6 Gate 3: 首日物理锚点永久冻结与双锚失守防漏检](#ch2-6)
  - [2.7 Gate 4: VWAP 多日结构完整性门禁（拒绝对缺失数据放行）](#ch2-7)
  - [2.8 Gate 5: 7 状态操作节点状态机与 TDE 真实终审](#ch2-8)
  - [2.9 华大海天伪强反例四项联合判据与回归断言](#ch2-9)
  - [2.10 Historical Cut-Off 历史截断回放引擎与时间沙箱](#ch2-10)
- [叁、本地 LLM 自学习决策系统（Ollama JSON Schema 约束）](#ch3)
  - [3.1 四不原则与降级守护](#ch3-1)
  - [3.2 Ollama 原生结构化输出（JSON Schema 替代纯 Prompt）](#ch3-2)
  - [3.3 三大智能体 Agent 规范](#ch3-3)
  - [3.4 本地时序向量库（BGE-M3 1024 维修正）](#ch3-4)
  - [3.5 离线自学习闭环（SFT / DPO 训练样本生成器）](#ch3-5)
- [肆、数据 Schema、数据库迁移与新增文件清单](#ch4)
  - [4.1 配置文件（YAML 阈值全局对齐）](#ch4-1)
  - [4.2 现有数据库迁移方案（ALTER TABLE 增量补列）](#ch4-2)
  - [4.3 新增文件清单](#ch4-3)
- [伍、分阶段实施路线（准入驱动）](#ch5)
- [陆、单元测试矩阵（17 组、至少 324 项用例）](#ch6)
- [柒、不可违反的十条铁律](#ch7)
- [捌、源计划需求追踪与实时旁路验收](#ch8)

---

<a id="ch1"></a>
## 壹、审核问题溯源与修正对照表

本表记录已订正的问题和仍需实施验收的前置项；源计划未覆盖部分以第捌节需求追踪表为准，不因写入本方案即视为已实现或已验收：

| # | 审查发现的问题 | 导致后果 | 本方案订正规格 |
|:---:|:---|:---|:---|
| **1** | **T1 Carry 的 CAUTION 通过 Gate 2** | 40~64分谨慎标的被错误放行买入 | `CAUTION` 严格标记为 `gate2_t1_carry_passed = False`，判定结果为 `WATCH`，严禁直接打出 `ENTRY`！仅当 `ALLOW` (>=65分 且 非EXTREME) 才通过。 |
| **2** | **Gate 3 首日实时锚点与次日封存锚点生命周期混用** | D0 尚无封存对象，直接依赖 `listing_anchors` 会缺字段或漏校验；D1+ 缺锚点也可能绕过双锚核验 | D0 从同一标的实时行情与证券主数据显式提供开盘价、发行价；任一价格缺失/非有限/非正数即 `BLOCK`。D1+ 必须有合法封存锚点并同时核验日内最低价、现价。 |
| **3** | **Gate 4 VWAP 字段缺失时用现价代替** | `vwap_1d=None`、覆盖期不足或结构字段缺失会被伪装成有效行情 | VWAP 各价格必须为有限正数；缺失一律阻断。按新股上市天数分别校验首日锚点、1D、5D、10D 数据，不以现价补值。 |
| **4** | **Gate 5 风控布尔值默认放行、无效 RR 未阻断** | 未传 RiskGate 结果仍默认放行；RR 缺失可能引发异常而非明确拒绝 | 直接调用 RiskGate 适配器并校验 `RiskDecision.allowed` 与订单；计划代码、价格区间、止损/目标、RR 和赛马名次全部有效后才允许 ENTRY。 |
| **5** | **Pre-Heat `s_sub = s_val = ...` 变量覆盖** | 估值分丢失，申购分被计算两次，总分失真 | 拆分独立变量计算：`s_val` 与 `s_sub` 互不干扰；评分阈值与 YAML 配置完全对齐（75.0 / 55.0）。 |
| **6** | **换手爬升速度只有入参、没有生产者契约** | 默认值或错误单位使伪强过滤失效 | 定义按标的、交易日维护的分时换手率差分器，按实际时间间隔计算 %/分钟；无效/回退行情不生成有效速度。 |
| **7** | **华大海天换手条件与数学判据不一致** | `heat_score >= 60` 替代换手率阈值，可能漏掉真实天量结构 | 统一为 `turnover_climb_speed >= 0.8` 或 `turnover_pct >= 75`；四项均由有来源、同一交易日的指标计算，收盘判据只在收盘确认。 |
| **8** | **缺少 Tuple 导入** | 运行时报 NameError | 在所有模块头部完整导入 `Tuple, Dict, List, Optional, Any, Mapping, Union`。 |
| **9** | **`daily_sentiment` 已存在但缺少新列** | `CREATE TABLE IF NOT EXISTS` 无法追加新列 | 增加 `migrate_market_pulse_db()` 迁移函数，使用 `PRAGMA table_info` 检查并执行 `ALTER TABLE ADD COLUMN`。 |
| **10** | **BGE-M3 向量维度标注为 768 维** | 写入 LanceDB 时 Schema 维度不匹配报错 | 全面更正为 BGE-M3 官方标准 Dense 维度：**1024 维**。 |
| **11** | **回放未调用时间沙箱且结果为固定示例** | 固定常数无法证明历史决策或零未来泄漏 | 每个历史时点均先截断行情，再生成快照、运行规则和记录决策；明确输出为 15 项字段契约，禁止使用未来行。 |
| **12** | **Ollama 调用缺少结构校验和故障降级** | JSON Schema 不能替代服务超时、错误响应与业务校验处理 | 保留原生 JSON Schema；Worker 捕获服务/解析/校验错误并返回结构化失败状态，主交易流程退回规则引擎，不向 UI 或交易线程抛裸异常。 |
| **13** | **跨模块类型和运行时依赖未导入** | 独立模块导入时可能触发 `NameError` | 各模块明确 `__future__` 注解策略、类型导入和运行时导入；编排器显式导入锚点存储及 VWAP 检查函数。 |
| **14** | **目录承诺 Agent 与 SFT/DPO，正文缺项** | “自学习系统”没有可实施的输入、输出、样本和晋级契约 | 增补三类 Agent 的边界、JSON 输出契约、经验检索及离线训练/评估/影子晋级与回滚流程。 |
| **15** | **Pre-Heat YAML 权重未参与计算** | 配置与运行时评分不一致，调参不生效 | 增加配置加载和校验；按各分项满分归一化后应用 YAML 权重，校验权重和为 1，阈值只由配置来源提供。 |
| **16** | **SQLite 迁移假定目标表已存在且缺少锁等待配置** | 新库或迁移顺序错误时 `ALTER TABLE` 失败；并发写入时可能在默认短超时下锁失败 | 迁移先确保基础表存在，连接设置 `timeout=15.0`，在 `BEGIN IMMEDIATE` 事务中执行幂等增量变更；异常回滚并在 `finally` 关闭连接。 |
| **17** | **Gate 4/5 对类型错误与 NaN 边界检查不完整** | 覆盖天数类型错误可能抛异常；非有限价格/RR 可能绕过普通大小比较 | 对上市交易日数、覆盖天数、现价及 TradePlan 区间逐项做类型、有限性与正值校验；RR 必须是有限正数且达标，否则失败关闭。 |
| **18** | **Agent 元数据与严格 JSON Schema 冲突** | 顶层 `additionalProperties=false` 不允许文中另加的 request/time/model/evidence 字段，三类 Agent 的负载也并非同一结构 | 改用严格信封结构 `{agent_type, metadata, payload}`；每类 Agent 使用独立 payload Schema，信封和负载均拒绝额外字段，并在 Worker 本地校验。 |
| **19** | **既有 768 维向量库没有升级路径** | 新旧向量写入同一表时维度/模型版本不兼容，检索或写入失败 | 新建版本化 1024 维表并记录 embedding 模型版本；离线重嵌入与校验完成后原子切换活动表指针，保留旧表供回滚，禁止混写。 |
| **20** | **回放时间戳混合时区处理未定义** | pandas 对混合 naive/aware 或不同偏移时区可能返回非统一 dtype，截断前排序/比较不可靠 | loader/沙箱逐项规范时间戳：naive 按 Asia/Shanghai 解释，aware 转为 Asia/Shanghai；解析失败拒绝样本，规范化后再排序与截断。 |
| **21** | **分时指标数值范围与布尔伪数值未校验** | bool、越界比率或负换手等异常输入可能通过“数值类型”检查污染判据 | 指标校验拒绝 bool/非有限值，并检查换手非负、VWAP 上方比例及收盘位置在 `[0,1]`、回撤非负；不合格时返回阻断结果。 |
| **22** | **VWAP 快照未核对代码与计算基准** | 错标的快照或指数代理 VWAP 可能被用于个股放行 | Gate 4 核对 `vwap.code == code` 且 `basis == "turnover"`；期限满足后仅接受 VWAPFactory 定义的已知结构枚举，缺失/未知一律阻断。 |
| **23** | **RiskGate 输入与批准订单可能不是同一标的/价格** | Gate 用当前价算 RR，但实际批准单取 `signal.price`；代码不一致或过期信号会造成错误标的/价位订单 | 入口核对 intent/signal/候选代码和行情时点一致，并将信号年龄限制在 0~300 秒；RiskGate 返回后复核 BUY 订单代码、价格区间、有限正仓位并按批准价格重算 RR。 |
| **24** | **VWAPSnapshot 的 `stale` 标记没有真实时效来源** | 当前 `VWAPSnapshot.stale` 默认为 `False`，仅检查布尔值不能发现停止更新的旧快照 | Gate 4 必须把 `date/time` 与同一行情时点比较，要求 `0 <= age_seconds <= max_vwap_stale_seconds`；时间戳无效、倒挂或超龄一律阻断。 |
| **25** | **Gate 0/1/2 缺失快照会在访问字段时抛异常** | `lrrm`、`ipo_regime` 或 `t1_carry` 为 `None` 时无法形成明确门禁结果，可能中断主流程 | 每层访问字段前先检查必需快照；缺失时记录对应 gate、原因并返回 `BLOCK`，不把异常交给交易主线程。 |
| **26** | **RiskGate 批准单的止损与计划结构止损未核对** | 计划按结构止损计算 RR，实际订单却可能携带空值或不同止损，风险距离失真 | 只接受 `BUY_SCOUT/BUY_CONFIRM` 计划；批准订单必须有正的有限止损，且与 `IPOTradePlan.structural_stop` 在 0.001 元容差内一致。 |
| **27** | **计划仓位百分数与 RiskGate 小数比例单位不同** | `IPOTradePlan.position_pct=30.0` 若直接传为 `DecisionIntent.size_pct`，将与 RiskGate 的 0.0~1.0 比例契约错位 | 适配器明确执行 `position_pct / 100.0`，校验 intent 仓位在 `(0,1]`，再交由 RiskGate 按配置限额裁剪。 |
| **28** | **SQLite 新列未接入实际写入和启动链路** | 只做 ALTER TABLE 不会保存 `lrrm_state`/`ipo_regime_state`；原 `init_pulse_db()` 会吞异常，迁移失败仍可能继续运行 | 在 `market_pulse_db.py` 的初始化入口执行同一 `DB_PATH` 迁移，迁移失败返回不可就绪状态；同步扩展 `save_daily_sentiment()` 的 INSERT/UPSERT 并测试旧库读写。 |
| **29** | **新 Gate 模块没有挂到现有下单入口** | 新建编排器可能成为未调用的孤立代码，现有 ENTRY 路径仍绕过六层门禁 | 仅在 `ats/strategy/ipo_trading_center.py` 的候选转 ENTRY 派单边界调用 GateOrchestrator；只把 RiskGate 批准的 ENTRY 交给既有订单路由，不改交易中心内部调度、退出引擎、Qt 图元与真实网关；WATCH/BLOCK 不得派单。 |
| **30** | **LLM 队列操作与结果排空可能落在 300ms 交易轮询或 Qt 事件线程** | `put_nowait/get_nowait` 仍涉及队列同步；无界排空可能在结果积压时占住事件循环 | 请求构造、父进程端队列写入/读取、序列化和结果校验只在独立 LLM 控制线程执行；Worker 只在自身进程按方向消费请求/产出结果；v1.x 交易轮询不读取 LLM 快照，Qt 仅接收合并后的低频通知。 |
| **31** | **“无锁、0 阻塞、100% CPU/GPU 隔离”超出可证明范围** | `multiprocessing.Queue`、Windows 调度器及 GPU 推理服务都不能提供硬实时或绝对抢占保证 | 删除绝对保证措辞；把保证收敛为不等待模型、不在关键路径做 I/O/IPC/推理，并用基线对照压测作为启用门槛。未达标时禁用 LLM，规则主线照常运行。 |
| **32** | **Worker 故障和缓存时效未形成真实健康契约** | `_worker_alive` 固定为 `True`；仅按接收时间 TTL 可能继续消费模型停机前的旧建议 | 增加旁路监督心跳、超时熔断和 Worker 重启状态；快照仅供 UI/离线记录。建议必须同时满足接收 TTL、行情 `as_of_time` 新鲜度及当前 request 版本，否则由旁路清除建议并异步记录故障，交易路径始终走规则决策。 |
| **33** | **响应信封无法可靠关联请求标的与新旧顺序** | Market Regime payload 没有 `code`，信封 metadata 也未定义 ticker；桥接器可能丢弃响应或让旧响应覆盖新响应 | Worker 注入并校验 `request_id/scope_id/ticker/as_of_time/generated_at`；响应须匹配待处理请求、标的和期限，按每标的递增序号拒绝迟到/重复结果。 |
| **34** | **降低 Python Worker 优先级被误当作限制 Ollama 推理资源** | 实际矩阵计算可能运行在独立 Ollama 服务进程/GPU 上；Worker 的 Windows 优先级不会限制该服务或显存占用 | 分别说明受管 Ollama 服务的启动/资源策略与外部服务的限制；不擅自改外部服务优先级。记录 CPU/GPU 压力测试，资源争用超出门槛时关闭模型旁路。 |
| **35** | **LLM 建议的交易影响边界与安全默认值不明确** | “仅输出 Proposal”与“可作微调参考”可能被解释为能直接改评分或放宽门禁 | v1.x 默认 LLM 仅展示/留痕，不改变分数、状态、阈值、TradePlan、仓位或订单；未完成人工审批、影子评估和独立配置前，正负修正均为 `0.0`。 |
| **36** | **7 状态操作状态机只有文件名，没有状态与转换契约** | Gate 结果仅为 ENTRY/WATCH/BLOCK，无法验收 ARMED、ENTERED、HOLD_T1 与 EXIT_READY 的转换 | 正文补齐七态定义、转换条件、成交确认边界、T+1 锁定、阻断恢复和每次转换的原因/时间/快照版本。 |
| **37** | **回放时间沙箱只截断行情 bars，不能证明所有输入无未来泄漏** | 新闻、公告、市场横截面、申购/流通信息、向量证据或标签仍可能来自 cutoff 之后 | 所有特征与检索证据必须携带 `available_at/published_at` 并由统一 cutoff loader 截断；仅未来结果评估器可在决策完成后读取标签。 |
| **38** | **源计划中的指标、UI、回放验收与配置需求未全部映射到 v1.1** | 有单元测试数量目标，但缺少源计划验收指标、8 月至今样本范围、告警字段及全部阈值配置追踪 | 增加源计划需求矩阵；未覆盖项标为实施前置/独立阶段，不得宣称 v1.1 已完整覆盖。 |
| **39** | **LRRM 输入缺失被中性默认值掩盖** | 无 20D 历史时把分位设为 50，`LRRMSnapshot` 默认 NORMAL/NEUTRAL，数据不足仍可能通过 Gate 0 | 为每项输入记录有效性、来源和时点；必需输入不足时给出 `UNKNOWN/UNREADY` 并阻断 ENTRY，不以中性默认值冒充有效市场状态。 |
| **40** | **“所有阈值进版本化 YAML”尚未覆盖实际门禁常量** | 方案中仍散落 RR=2.5、Gate 2 分段、锚点容差/跌破幅度、队列/TTL/熔断等数值 | 建立阈值清单和配置归属表；引擎只消费已校验配置快照，配置版本随每次决策和回放记录。 |
| **41** | **IPO Regime 小样本仍可能获得高置信度并放行** | 当前无样本才返回 DISTRIBUTION；少量样本也可算出 100% D1 胜率并赋固定 80 置信度 | 规定至少 5 只有效新股样本后才可生成可交易 Regime；样本不足或关键标签未成熟时 `data_ready=False`、置信度为 0 并失败关闭，完整指标仍按 10~20 交易日窗口计算。 |
| **42** | **LLM 旁路契约内部对交易路径是否读取快照/健康状态表述冲突** | “主路径只读快照/健康位”与“v1.x 纯规则且禁止读取”无法同时满足，实施时可能把 IPC/缓存访问带回 300ms 热路径 | 统一为 v1.x 交易决策路径完全不读取 LLM 快照或健康状态；旁路独立管理缓存、熔断及异步诊断，LLM 只用于展示/留痕。未来申请策略读取须另立版本并通过独立审批及性能验收。 |
| **43** | **跨进程队列“唯一读写者”措辞与 Worker 必须消费/产出消息相矛盾** | 按字面实现时，控制线程无法单独完成两条队列的读写；若多个 ATS/Qt 线程共享端点，又会引入竞态和阻塞风险 | 改为父进程控制线程独占父端请求/结果队列操作；Worker 仅在 Worker 进程内按方向读取请求、写入结果；两侧均不向 ATS 轮询或 Qt 事件线程暴露队列端点。 |
| **44** | **版本标题容易被误读为所有源计划需求已完整闭环** | 需求追踪表仍有指标、数据来源、回放范围、UI/告警和配置项标为部分覆盖；交易中心方案 1/2 也属于外部依赖 | 标题改为“复审修订与需求追踪版”；实施前置项和外部依赖保留显式状态，不宣称全量覆盖或已验收。 |
| **45** | **Gate 3 D0 引用的发行价字段未定义且缺失时可能放行** | `ListingAnchors` 无 `issue_price`；开盘价/发行价均为 `None` 时原分支仍标记 Gate 3 通过，NaN 也可能逃过比较 | 将 D0 开盘价和发行价作为独立、同标的、有效时点输入；两者及日内最低价/现价都须为有限正数，缺失或无效即 `BLOCK`。按配置化的开盘跌幅容差和发行价支撑校验，不读取尚未封存的 D1+ 锚点。 |
| **46** | **Gate 4 D0 仍要求已封存首日锚定 VWAP** | D0 盘中尚无完整 `ListingAnchors`，导致首日虽有有效累计 VWAP 也会被误阻断 | `listing_age_sessions == 1` 仅核验有效、同标的、同一时点的当日累计 VWAP；D1 至 D4 才要求已封存首日锚定 VWAP，D5 起按 5D/10D 完整度分流。 |
| **47** | **SQLite 迁移正文未落实 15 秒锁等待承诺** | 迁移示例使用 `sqlite3.connect(db_path)` 默认超时，与审查摘要声称的 `timeout=15.0` 不一致 | 连接改为 `sqlite3.connect(db_path, timeout=15.0)`，保留 `BEGIN IMMEDIATE`、异常回滚和连接关闭；并发锁行为仍须在迁移测试中验收。 |
| **48** | **历史数据库新增状态列默认值伪装成有效市场状态** | 旧记录被回填为 `NORMAL` / `DISTRIBUTION`，可能被报表或回放误当作真实计算结果，与缺失数据失败关闭原则冲突 | 旧行统一回填 `UNKNOWN`，读取适配层将其映射为 `data_ready=False`；只有完成真实计算的新记录才写入有效状态，不用中性状态默认值冒充历史事实。 |
| **49** | **Stage 0 基础设施实施与第捌节“实施前先完成字段/配置清单”顺序不够明确** | 可能先写配置、迁移或 Worker 代码，再发现必需输入、来源或阈值归属尚未确定 | Stage 0 先设准入设计门：冻结数据字典、来源/可用时点/缺失策略和配置归属；清单审定后才进入基础设施编码与性能基线，Stage 1 策略接入仍须通过回放及压力门禁。 |

---

<a id="ch2"></a>
## 贰、六层门禁与核心引擎详细规格（消除误放行）

### 2.1 Gate 0: LRRM 宏观流动性与风险状态机

**新增模块**：`ats/strategy/lrrm_engine.py`

```python
"""LRRM (Liquidity / Risk Regime Manager) 流动性与风险偏好状态机"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo
from enum import Enum
import math


class LiquidityRegime(Enum):
    LOOSE = "LOOSE"       # 充裕宽松 (全市场成交分位数 > 80%)
    NORMAL = "NORMAL"     # 平稳中性
    TIGHT = "TIGHT"       # 流动性紧缩 (全市场成交分位数 < 20%)
    SHOCK = "SHOCK"       # 流动性休克 (跌停潮 / 分位数 < 5%)


class RiskAppetite(Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"


@dataclass
class LRRMSnapshot:
    """LRRM 每周期输出快照"""
    liquidity_regime: str = "NORMAL"
    risk_appetite: str = "NEUTRAL"
    concentration_state: str = "BROAD"
    liquidity_confidence: float = 50.0      # 0~100
    transition_reason: str = ""
    market_amount_yi: float = 0.0           # 全市场成交额(亿元)
    amount_20d_percentile: float = 50.0     # 20日成交分位数
    advance_decline_ratio: float = 0.5      # 涨跌家数比
    limit_down_count: int = 0
    generated_at: str = ""
    data_ready: bool = False
    missing_inputs: List[str] = field(default_factory=list)


class LRRMEngine:
    def __init__(self, required_inputs: List[str]):
        self.required_inputs = tuple(required_inputs)

    def evaluate(
        self,
        market_amount_yi: float,
        amount_history_20d: List[float],
        up_count: int,
        down_count: int,
        limit_up_count: int,
        limit_down_count: int,
        required_input_health: Dict[str, bool],  # 按 YAML required_inputs 校验来源、时点和有效性
        fsm_state: Optional[str] = None,
    ) -> LRRMSnapshot:
        # 所有配置为 required 的市场输入和历史窗口必须有效；缺项不可用中性值伪造。
        missing_inputs = sorted(
            name for name in self.required_inputs
            if required_input_health.get(name) is not True
        )
        if len(amount_history_20d) < 20:
            missing_inputs.append("amount_history_20d(<20)")
        if missing_inputs:
            return LRRMSnapshot(
                liquidity_regime="UNKNOWN", risk_appetite="RISK_OFF",
                liquidity_confidence=0.0,
                transition_reason=f"LRRM 数据未就绪: {missing_inputs}",
                data_ready=False, missing_inputs=missing_inputs,
            )

        # 1. 计算 20 日成交分位数
        sorted_amounts = sorted(amount_history_20d)
        rank = sum(1 for a in sorted_amounts if a <= market_amount_yi)
        percentile = (rank / len(sorted_amounts)) * 100.0

        total_stocks = max(up_count + down_count, 1)
        ad_ratio = up_count / total_stocks

        # 2. 状态机判定
        if percentile < 5.0 or limit_down_count >= 30 or (ad_ratio < 0.20 and percentile < 15.0):
            regime = LiquidityRegime.SHOCK
            appetite = RiskAppetite.RISK_OFF
            reason = f"流动性休克熔断: 20日分位 {percentile:.1f}%, 跌停家数 {limit_down_count}"
        elif percentile < 20.0 or fsm_state == "PANIC":
            regime = LiquidityRegime.TIGHT
            appetite = RiskAppetite.RISK_OFF
            reason = f"流动性紧缩: 20日分位 {percentile:.1f}%, 市场情绪 PANIC"
        elif percentile > 80.0 and ad_ratio > 0.60:
            regime = LiquidityRegime.LOOSE
            appetite = RiskAppetite.RISK_ON
            reason = f"流动性充裕宽松: 20日分位 {percentile:.1f}%, 涨跌比 {ad_ratio:.2f}"
        else:
            regime = LiquidityRegime.NORMAL
            appetite = RiskAppetite.NEUTRAL
            reason = "流动性平稳中性"

        return LRRMSnapshot(
            liquidity_regime=regime.value,
            risk_appetite=appetite.value,
            liquidity_confidence=85.0 if regime in (LiquidityRegime.SHOCK, LiquidityRegime.LOOSE) else 65.0,
            transition_reason=reason,
            market_amount_yi=market_amount_yi,
            amount_20d_percentile=percentile,
            advance_decline_ratio=ad_ratio,
            limit_down_count=limit_down_count,
            data_ready=True,
        )
```

---

### 2.2 Gate 1: IPO Regime 五态横截面状态机

**新增模块**：`ats/strategy/ipo_regime_fsm.py`

```python
"""IPO 新股市场情绪阶段五态状态机 (基于最近 N 只新股横截面统计)"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from ats.strategy.lrrm_engine import LRRMSnapshot


class IPORegimeState(Enum):
    DISTRIBUTION = "DISTRIBUTION"    # 首日兑现杀跌型 (开仓禁止)
    REPAIR = "REPAIR"                # 弱势修复型 (允许小仓试探)
    CONTINUATION = "CONTINUATION"    # 主升接力型 (重点做多)
    MANIA = "MANIA"                  # 极度狂热型 (只出不进)
    EXHAUSTION = "EXHAUSTION"        # 动能衰竭型 (全面熔断禁买)


@dataclass
class IPORegimeSnapshot:
    state: str = "DISTRIBUTION"
    confidence: float = 0.0
    trigger_factors: List[str] = field(default_factory=list)
    d1_positive_rate: float = 0.0        # 次日正收益率
    first_day_peak_ratio: float = 0.0    # 首日见顶率
    new_high_ratio: float = 0.0          # 上市后创新高比例
    turnover_median: float = 0.0         # 换手率中位数
    generated_at: str = ""
    data_ready: bool = False
    sample_count: int = 0
    missing_metrics: List[str] = field(default_factory=list)


class IPORegimeFSM:
    LOOKBACK_STOCKS = 10

    def __init__(self, required_metrics: List[str]):
        self.required_metrics = tuple(required_metrics)

    def update(
        self,
        recent_ipos: List[Dict[str, Any]],
        required_metric_health: Dict[str, bool],  # D1/D2/D3、回撤率等必需标签成熟度
        lrrm: Optional[LRRMSnapshot] = None,
    ) -> IPORegimeSnapshot:
        missing_metrics = sorted(
            name for name in self.required_metrics
            if required_metric_health.get(name) is not True
        )
        if len(recent_ipos) < 5 or missing_metrics:
            return IPORegimeSnapshot(
                state=IPORegimeState.DISTRIBUTION.value, confidence=0.0,
                trigger_factors=[f"Regime 数据未就绪: 样本 {len(recent_ipos)}/5, 缺项 {missing_metrics}"],
                data_ready=False, sample_count=len(recent_ipos), missing_metrics=missing_metrics,
            )

        # 横截面统计
        n = len(recent_ipos)
        d1_pos_count = sum(1 for s in recent_ipos if s.get("d1_return_pct", 0.0) > 0)
        peak_count = sum(1 for s in recent_ipos if s.get("is_first_day_peak", False))
        new_high_count = sum(1 for s in recent_ipos if s.get("made_new_high", False))
        turnovers = [s.get("first_day_turnover", 0.0) for s in recent_ipos]
        turnover_med = sorted(turnovers)[n // 2] if turnovers else 0.0

        d1_rate = d1_pos_count / n
        peak_rate = peak_count / n
        high_rate = new_high_count / n

        factors = []
        # 1. 强行坠入熔断
        if lrrm and lrrm.liquidity_regime == "SHOCK":
            state = IPORegimeState.DISTRIBUTION
            factors.append("大盘流动性休克，强制进入 DISTRIBUTION 杀跌期")
        # 2. 状态机流转
        elif peak_rate >= 0.40 and d1_rate < 0.40:
            state = IPORegimeState.EXHAUSTION
            factors.append(f"首日见顶率过高({peak_rate:.1%})，次日正收益率恶化({d1_rate:.1%})，进入 EXHAUSTION 衰竭期")
        elif d1_rate >= 0.80 and turnover_med >= 65.0:
            state = IPORegimeState.MANIA
            factors.append(f"次日正收益率达 {d1_rate:.1%}，换手极高({turnover_med:.1f}%)，进入 MANIA 狂热高潮")
        elif d1_rate >= 0.55 and high_rate >= 0.40:
            state = IPORegimeState.CONTINUATION
            factors.append(f"次日溢价稳定({d1_rate:.1%})，创新高比例达标({high_rate:.1%})，处于 CONTINUATION 主升接力期")
        elif d1_rate >= 0.40:
            state = IPORegimeState.REPAIR
            factors.append(f"次日溢价企稳({d1_rate:.1%})，处于 REPAIR 修复初期")
        else:
            state = IPORegimeState.DISTRIBUTION
            factors.append(f"次日破发兑现率高({1.0 - d1_rate:.1%})，处于 DISTRIBUTION 派发退潮期")

        return IPORegimeSnapshot(
            state=state.value,
            confidence=80.0,
            trigger_factors=factors,
            d1_positive_rate=d1_rate,
            first_day_peak_ratio=peak_rate,
            new_high_ratio=high_rate,
            turnover_median=turnover_med,
            data_ready=True,
            sample_count=n,
        )
```

---

### 2.3 IPO Pre-Heat: 上市前先验潜力打分引擎（修复变量覆盖与配置对齐）

**新增模块**：`ats/strategy/ipo_preheat_engine.py`

```python
"""IPO 上市前先验潜力评估引擎 (纯静态先验数据，无未来函数，加入盯盘池门禁)"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import math


@dataclass(frozen=True)
class PreHeatConfig:
    watch_candidate_threshold: float  # 必须由版本化 YAML 显式注入
    hot_candidate_threshold: float
    weight_valuation: float
    weight_subscription: float
    weight_scarcity: float
    weight_theme: float
    weight_capital: float

    def __post_init__(self) -> None:
        weights = (self.weight_valuation, self.weight_subscription,
                   self.weight_scarcity, self.weight_theme, self.weight_capital)
        if any(not math.isfinite(w) or w < 0 for w in weights) or not math.isclose(sum(weights), 1.0):
            raise ValueError("PreHeatConfig 权重必须为非负有限值且总和为 1.0")
        if (not math.isfinite(self.watch_candidate_threshold)
                or not math.isfinite(self.hot_candidate_threshold)
                or self.watch_candidate_threshold < 0
                or self.watch_candidate_threshold >= self.hot_candidate_threshold
                or self.hot_candidate_threshold > 100):
            raise ValueError("PreHeatConfig 阈值必须满足 0 <= watch < hot <= 100")

    @classmethod
    def from_mapping(cls, section: Dict[str, Any]) -> "PreHeatConfig":
        weights = section.get("weights", {})
        return cls(
            watch_candidate_threshold=float(section["watch_candidate_threshold"]),
            hot_candidate_threshold=float(section["hot_candidate_threshold"]),
            weight_valuation=float(weights["valuation"]),
            weight_subscription=float(weights["subscription"]),
            weight_scarcity=float(weights["scarcity"]),
            weight_theme=float(weights["theme"]),
            weight_capital=float(weights["capital_structure"]),
        )


@dataclass(frozen=True)
class IPOPreHeatSnapshot:
    code: str
    name: str
    preheat_score: float = 0.0          # 0~100 综合分
    preheat_tier: str = "PRE_COLD"      # PRE_HOT (>=75) / PRE_WARM (55~74) / PRE_COLD (<55)
    valuation_score: float = 0.0        # 估值分位 (0~25)
    subscription_score: float = 0.0     # 申购热度 (0~25)
    scarcity_score: float = 0.0         # 题材稀缺度 (0~20)
    theme_match_score: float = 0.0      # 主线共振 (0~20)
    capital_structure_score: float = 0.0 # 筹码弹性 (0~10)
    is_watch_candidate: bool = False    # 是否允许进入次日重点盯盘池
    as_of_date: str = ""


class IPOPreHeatEngine:
    def __init__(self, config: PreHeatConfig):
        if not isinstance(config, PreHeatConfig):
            raise ValueError("缺少已校验的 PreHeatConfig，禁止生成可交易候选")
        self.config = config

    def evaluate(
        self,
        code: str,
        name: str,
        issue_price: float,
        float_shares_wan: float,
        pe_ratio: float,
        industry_pe_median: float,
        online_sub_multiple: float,
        winning_rate_pct: float,
        scarcity_rank: int = 3,         # 1(极稀缺)~5(同质化)
        hot_themes: Optional[List[str]] = None,
        as_of_date: str = "",
    ) -> IPOPreHeatSnapshot:
        # 1. 估值分位评分 (0~25分): PE 折价越大得分越高
        pe_discount = (industry_pe_median - pe_ratio) / max(industry_pe_median, 1.0)
        s_val = max(0.0, min(25.0, 12.5 + pe_discount * 25.0))

        # 2. 申购热度评分 (0~25分): 彻底修复 s_sub = s_val 变量覆盖 Bug！
        sub_ratio_score = min(15.0, math.log10(max(online_sub_multiple, 1.0)) * 3.75)
        win_rate_score = max(0.0, min(10.0, (0.08 - winning_rate_pct) * 125.0))
        s_sub = max(0.0, min(25.0, sub_ratio_score + win_rate_score))  # 保持 s_val 独立完整！

        # 3. 题材稀缺性评分 (0~20分)
        s_scarcity = {1: 20.0, 2: 15.0, 3: 10.0, 4: 5.0, 5: 0.0}.get(scarcity_rank, 10.0)

        # 4. 主流热点共振评分 (0~20分)
        s_theme = 15.0 if hot_themes and any(t in name for t in hot_themes) else 5.0

        # 5. 筹码流通盘弹性 (0~10分)
        if float_shares_wan < 2000:
            s_cap = 10.0
        elif float_shares_wan < 4000:
            s_cap = 7.0
        elif float_shares_wan < 8000:
            s_cap = 4.0
        else:
            s_cap = 1.0

        # 分项保留原始满分口径，再归一化后乘以唯一配置源 YAML 中的权重。
        total = 100.0 * (
            self.config.weight_valuation * (s_val / 25.0)
            + self.config.weight_subscription * (s_sub / 25.0)
            + self.config.weight_scarcity * (s_scarcity / 20.0)
            + self.config.weight_theme * (s_theme / 20.0)
            + self.config.weight_capital * (s_cap / 10.0)
        )

        # 严格使用配置阈值
        if total >= self.config.hot_candidate_threshold:
            tier = "PRE_HOT"
        elif total >= self.config.watch_candidate_threshold:
            tier = "PRE_WARM"
        else:
            tier = "PRE_COLD"

        return IPOPreHeatSnapshot(
            code=code,
            name=name,
            preheat_score=round(total, 1),
            preheat_tier=tier,
            valuation_score=round(s_val, 1),
            subscription_score=round(s_sub, 1),
            scarcity_score=round(s_scarcity, 1),
            theme_match_score=round(s_theme, 1),
            capital_structure_score=round(s_cap, 1),
            is_watch_candidate=(total >= self.config.watch_candidate_threshold),
            as_of_date=as_of_date,
        )
```

---

### 2.4 IPO Live Heat: 实时动能与 6 大非线性函数（含分时指标生产契约）

**新增模块**：`ats/strategy/ipo_live_heat_engine.py`

```python
"""IPO 上市盘中实时动能感知引擎 (含 6 大非线性饱和/反转函数及换手速率真实计算)"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import math


@dataclass
class IPOLiveHeatSnapshot:
    code: str
    heat_score: float = 0.0              # 原始热度分 (0~100)
    overheat_score: float = 0.0          # 过热惩罚分 (0~50)
    exhaustion_risk: float = 0.0         # 衰竭风险分 (0~100)
    nonlinear_zone: str = "NORMAL"       # NORMAL / HOT / EXTREME
    intraday_velocity: float = 0.0       # 拔地而起角速度(度)
    halt_count: int = 0                  # 临停次数
    turnover_pct: Optional[float] = None # 当前日累计换手率 (%)
    turnover_climb_speed: Optional[float] = None  # 换手率爬升速度 (%/分钟)
    price_vwap_dist_pct: float = 0.0     # 价格距离 VWAP 偏离度%
    close_location: float = 0.0          # (Close - Low) / (High - Low)
    minutes_above_vwap_ratio: Optional[float] = None # 在 VWAP 上方时间占比
    pullback_from_peak_pct: Optional[float] = None  # 距最高价回撤幅度%
    is_overheated_veto: bool = False     # 是否触发过热熔断


class IPOLiveHeatEngine:
    # 1. 首日涨幅非线性
    @staticmethod
    def calc_return_nonlinear(ret_pct: float) -> Tuple[float, float]:
        if ret_pct <= 0:
            return 0.0, 0.0
        elif ret_pct <= 20.0:
            return (ret_pct / 20.0) * 15.0, 0.0
        elif ret_pct <= 50.0:
            return 15.0 + ((ret_pct - 20.0) / 30.0) * 3.0, 0.0
        elif ret_pct <= 80.0:
            penalty = ((ret_pct - 50.0) / 30.0) * 15.0
            return max(0.0, 18.0 - penalty), penalty
        else:
            return -15.0, min(30.0, 15.0 + (ret_pct - 80.0) * 0.2)

    # 2. 日内换手率非线性
    @staticmethod
    def calc_turnover_nonlinear(turnover_pct: float) -> Tuple[float, float]:
        if turnover_pct <= 35.0:
            return (turnover_pct / 35.0) * 15.0, 0.0
        elif turnover_pct <= 65.0:
            return 15.0, 0.0
        elif turnover_pct <= 75.0:
            ratio = (turnover_pct - 65.0) / 10.0
            return 15.0 - ratio * 10.0, ratio * 15.0
        else:
            return -20.0, min(35.0, 15.0 + (turnover_pct - 75.0) * 1.5)

    # 3. 价格与 VWAP 乖离非线性
    @staticmethod
    def calc_vwap_distance_nonlinear(dist_pct: float) -> Tuple[float, float]:
        if -0.5 <= dist_pct <= 2.5:
            return 15.0, 0.0
        elif 2.5 < dist_pct <= 6.0:
            return 10.0, 0.0
        elif 6.0 < dist_pct <= 10.0:
            return 5.0, 10.0
        elif dist_pct > 10.0:
            return -15.0, 25.0
        else:
            return -10.0, 0.0

    # 4. 开盘溢价非线性
    @staticmethod
    def calc_opening_premium_nonlinear(open_premium_pct: float) -> Tuple[float, float]:
        if open_premium_pct <= 15.0:
            return 10.0, 0.0
        elif open_premium_pct <= 35.0:
            return 12.0, 0.0
        elif open_premium_pct <= 60.0:
            return 5.0, 12.0
        else:
            return -15.0, 25.0

    # 5. 拔起斜率时间加权
    @staticmethod
    def calc_intraday_velocity_nonlinear(slope_deg: float, now_hm: str) -> float:
        w = 1.0 if now_hm <= "0945" else (0.75 if now_hm <= "1000" else 0.40)
        return max(0.0, min(15.0, (slope_deg / 60.0) * 15.0 * w))

    # 6. 收盘位置非线性
    @staticmethod
    def calc_close_location_nonlinear(high_p: float, low_p: float, curr_p: float) -> Tuple[float, float]:
        span = max(high_p - low_p, 0.001)
        cl = (curr_p - low_p) / span
        if cl >= 0.85:
            return 15.0, 0.0
        elif cl >= 0.60:
            return 5.0, 5.0
        elif cl >= 0.45:
            return -5.0, 15.0
        else:
            return -20.0, 35.0

    def evaluate(
        self,
        code: str,
        ret_pct: float,
        turnover_pct: float,
        price_vwap_dist_pct: float,
        open_premium_pct: float,
        slope_deg: float,
        high_p: float,
        low_p: float,
        curr_p: float,
        # 彻底解决幽灵字段，明确传入分时指标
        turnover_climb_speed: Optional[float] = None,
        minutes_above_vwap_ratio: Optional[float] = None,
        pullback_from_peak_pct: Optional[float] = None,
        halt_count: int = 0,
        now_hm: str = "1000",
    ) -> IPOLiveHeatSnapshot:
        s_ret, p_ret = self.calc_return_nonlinear(ret_pct)
        s_to, p_to = self.calc_turnover_nonlinear(turnover_pct)
        s_vwap, p_vwap = self.calc_vwap_distance_nonlinear(price_vwap_dist_pct)
        s_prem, p_prem = self.calc_opening_premium_nonlinear(open_premium_pct)
        s_vel = self.calc_intraday_velocity_nonlinear(slope_deg, now_hm)
        s_cl, p_cl = self.calc_close_location_nonlinear(high_p, low_p, curr_p)

        raw_heat = max(0.0, min(100.0, 20.0 + s_ret + s_to + s_vwap + s_prem + s_vel + s_cl))
        total_overheat = min(50.0, p_ret + p_to + p_vwap + p_prem)
        exhaustion_risk = min(100.0, p_cl + (15.0 if halt_count >= 2 else 0.0) + (p_to * 0.8))

        if total_overheat >= 35.0 or exhaustion_risk >= 45.0 or p_cl >= 30.0:
            zone = "EXTREME"
            veto = True
        elif total_overheat >= 15.0 or raw_heat >= 75.0:
            zone = "HOT"
            veto = False
        else:
            zone = "NORMAL"
            veto = False

        span = max(high_p - low_p, 0.001)
        cl_val = round((curr_p - low_p) / span, 3)

        return IPOLiveHeatSnapshot(
            code=code,
            heat_score=round(raw_heat, 1),
            overheat_score=round(total_overheat, 1),
            exhaustion_risk=round(exhaustion_risk, 1),
            nonlinear_zone=zone,
            intraday_velocity=round(slope_deg, 1),
            halt_count=halt_count,
            turnover_pct=round(turnover_pct, 2) if turnover_pct is not None else None,
            turnover_climb_speed=turnover_climb_speed,
            price_vwap_dist_pct=round(price_vwap_dist_pct, 2),
            close_location=cl_val,
            minutes_above_vwap_ratio=(round(minutes_above_vwap_ratio, 2)
                                      if minutes_above_vwap_ratio is not None else None),
            pullback_from_peak_pct=(round(pullback_from_peak_pct, 2)
                                    if pullback_from_peak_pct is not None else None),
            is_overheated_veto=veto,
        )
```

#### 分时指标生产契约

- `turnover_pct` 使用当日累计换手率；`turnover_climb_speed` 由下列差分器按同一标的、同一交易日的相邻有效观测计算，单位固定为“百分点/分钟”。观测时间必须为有效且带时区的 `datetime`；首笔、时间差非正、换手率回退或数据缺失均返回 `None`，不得用 `0` 冒充有效观测。
- `minutes_above_vwap_ratio` 以已完成的一分钟 bar 计算 `close >= vwap` 的 bar 比例；`pullback_from_peak_pct = (session_high - current_price) / session_high * 100`。华大海天四项联合判据只在收盘确认时使用 `close_location`。

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple
import math


@dataclass(frozen=True)
class _TurnoverPoint:
    observed_at: datetime
    cumulative_pct: float


class TurnoverClimbTracker:
    def __init__(self) -> None:
        self._last: Dict[Tuple[str, str], _TurnoverPoint] = {}

    def update(
        self, code: str, trading_date: str, cumulative_pct: float, observed_at: datetime
    ) -> Optional[float]:
        key = (code, trading_date)
        if (isinstance(cumulative_pct, bool) or not isinstance(cumulative_pct, (int, float))
                or not math.isfinite(cumulative_pct) or cumulative_pct < 0
                or not isinstance(observed_at, datetime) or observed_at.tzinfo is None):
            self._last.pop(key, None)
            return None
        previous = self._last.get(key)
        self._last[key] = _TurnoverPoint(observed_at, cumulative_pct)
        if previous is None:
            return None
        elapsed_min = (observed_at - previous.observed_at).total_seconds() / 60.0
        delta_pct = cumulative_pct - previous.cumulative_pct
        if elapsed_min <= 0 or delta_pct < 0:
            self._last.pop(key, None)
            return None
        return delta_pct / elapsed_min
```

---

### 2.5 Gate 2: T+1 Carry 隔夜兑现性与华大海天伪强过滤（四项条件联合闭环）

**扩展模块**：`ats/strategy/t1_carry_evaluator.py`

```python
"""T+1 隔夜可兑现性评估引擎 (完整四项伪强判据，消灭误放行)"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from ats.strategy.ipo_live_heat_engine import IPOLiveHeatSnapshot
from ats.strategy.ipo_regime_fsm import IPORegimeSnapshot
from ats.strategy.lrrm_engine import LRRMSnapshot


class T1CarryState(Enum):
    ALLOW = "ALLOW"       # 允许隔夜 (>=65 且 非 EXTREME)
    CAUTION = "CAUTION"   # 谨慎待命 (40~64, 严禁直接买入放行)
    BLOCK = "BLOCK"       # 严格禁止 (<40 或 伪强否决 或 EXTREME)


@dataclass
class T1CarryResult:
    score: float = 50.0
    state: str = "CAUTION"
    positive_factors: List[str] = field(default_factory=list)
    negative_factors: List[str] = field(default_factory=list)
    nonlinear_zone: str = "NORMAL"
    overheat_score: float = 0.0
    exhaustion_risk: float = 0.0
    is_pseudo_strength_blocked: bool = False
    veto_reason: str = ""


class T1CarryEvaluator:
    def evaluate(
        self,
        code: str,
        live_heat: IPOLiveHeatSnapshot,
        ipo_regime: Optional[IPORegimeSnapshot] = None,
        lrrm: Optional[LRRMSnapshot] = None,
    ) -> T1CarryResult:
        pos_factors = []
        neg_factors = []

        required_metrics = (
            live_heat.turnover_pct,
            live_heat.minutes_above_vwap_ratio,
            live_heat.close_location,
            live_heat.pullback_from_peak_pct,
        )
        if any(value is None or isinstance(value, bool)
               or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in required_metrics):
            return T1CarryResult(
                score=0.0,
                state=T1CarryState.BLOCK.value,
                negative_factors=["伪强判据所需指标缺失或无效"],
                is_pseudo_strength_blocked=False,
                veto_reason="INCOMPLETE_LIVE_HEAT_METRICS",
            )
        if (live_heat.turnover_pct < 0
                or not 0.0 <= live_heat.minutes_above_vwap_ratio <= 1.0
                or not 0.0 <= live_heat.close_location <= 1.0
                or live_heat.pullback_from_peak_pct < 0
                or (live_heat.turnover_climb_speed is not None and (
                    isinstance(live_heat.turnover_climb_speed, bool)
                    or not isinstance(live_heat.turnover_climb_speed, (int, float))
                    or not math.isfinite(live_heat.turnover_climb_speed)
                    or live_heat.turnover_climb_speed < 0
                ))):
            return T1CarryResult(
                score=0.0,
                state=T1CarryState.BLOCK.value,
                negative_factors=["分时指标超出物理范围或类型无效"],
                is_pseudo_strength_blocked=False,
                veto_reason="INVALID_LIVE_HEAT_METRICS",
            )

        # ---------------- 华大海天四项伪强判据完整闭环实现 ----------------
        cond1_above_vwap = live_heat.minutes_above_vwap_ratio >= 0.70
        cond2_turnover = (
            (live_heat.turnover_climb_speed is not None
             and live_heat.turnover_climb_speed >= 0.8)
            or live_heat.turnover_pct >= 75.0
        )
        cond3_weak_close = live_heat.close_location <= 0.40                                    # 收盘落在当日振幅下方 40%
        cond4_deep_pullback = live_heat.pullback_from_peak_pct >= 25.0                         # 距最高价跳水

        # 四项联合命中即判为华大海天伪强派发结构
        is_pseudo = cond1_above_vwap and cond2_turnover and cond3_weak_close and cond4_deep_pullback
        if is_pseudo:
            neg_factors.append("命中华大海天伪强结构(表面在线上+天量松动+弱收盘+高位大跳水)")

        # 基础分合成
        base_score = live_heat.heat_score - (live_heat.overheat_score * 0.8) - (live_heat.exhaustion_risk * 0.5)

        # 叠加 Regime
        if ipo_regime:
            if ipo_regime.state == "CONTINUATION":
                base_score += 10.0
                pos_factors.append("IPO Regime 处于 CONTINUATION 主升期 (+10)")
            elif ipo_regime.state == "REPAIR":
                base_score += 5.0
            elif ipo_regime.state == "EXHAUSTION":
                base_score -= 25.0
                neg_factors.append("IPO Regime 动能衰竭 (-25)")
            elif ipo_regime.state == "DISTRIBUTION":
                base_score -= 15.0

        # 叠加 LRRM
        if lrrm and lrrm.liquidity_regime in ("TIGHT", "SHOCK"):
            base_score -= 15.0
            neg_factors.append("大盘流动性收紧 (-15)")

        final_score = max(0.0, min(100.0, base_score))

        # 门禁决策
        if is_pseudo:
            state = T1CarryState.BLOCK.value
            veto = "HUA_DA_HAI_TIAN_PSEUDO_STRENGTH_VETO (四项联合伪强一票否决)"
        elif live_heat.is_overheated_veto:
            state = T1CarryState.BLOCK.value
            veto = "LIVE_HEAT_EXTREME_OVERHEAT_VETO (极端过热一票否决)"
        elif ipo_regime and ipo_regime.state == "EXHAUSTION":
            state = T1CarryState.BLOCK.value
            veto = "IPO_REGIME_EXHAUSTION_VETO (板块动能衰竭熔断)"
        elif final_score >= 65.0 and live_heat.nonlinear_zone != "EXTREME":
            state = T1CarryState.ALLOW.value
            veto = ""
            pos_factors.append(f"T1 Carry 综合评分达标({final_score:.1f} >= 65.0)")
        elif final_score >= 40.0:
            state = T1CarryState.CAUTION.value
            veto = ""
            neg_factors.append(f"T1 Carry 处于谨慎观察区({final_score:.1f} in [40, 65)), 严禁盲目开仓")
        else:
            state = T1CarryState.BLOCK.value
            veto = f"SCORE_BELOW_THRESHOLD (综合得分 {final_score:.1f} < 40.0)"

        return T1CarryResult(
            score=round(final_score, 1),
            state=state,
            positive_factors=pos_factors,
            negative_factors=neg_factors,
            nonlinear_zone=live_heat.nonlinear_zone,
            overheat_score=live_heat.overheat_score,
            exhaustion_risk=live_heat.exhaustion_risk,
            is_pseudo_strength_blocked=is_pseudo,
            veto_reason=veto,
        )
```

---

### 2.6 Gate 3: 首日物理锚点永久冻结与双锚失守防漏检（改用最低价）

**新增模块**：`ats/strategy/listing_anchor_store.py`

```python
"""首日物理锚点永久固化存储与双锚失守严密检测"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any
import math
import json, os


@dataclass(frozen=True)
class ListingAnchors:
    code: str
    listing_date: str
    listing_open: float           # 首日开盘价
    listing_high: float           # 首日最高价
    listing_low: float            # 首日最低价
    listing_close: float          # 首日收盘价
    listing_vwap: float           # 首日成交均价
    listing_anchored_vwap: float  # 锚定 VWAP 原点
    first_30m_vwap: float         # 首日前 30 分钟均价
    close_location: float         # (close-low)/(high-low)
    first_day_turnover: float     # 首日换手率


class ListingAnchorStore:
    STORE_PATH = "config/listing_anchors.json"

    def check_dual_anchor_failure(
        self,
        anchors: ListingAnchors,
        intraday_low: float,
        current_price: float,
    ) -> Tuple[bool, str]:
        """
        防漏检修复：同时核验当日最低价 intraday_low 与当前价 current_price！
        只要日内曾触及击穿，或当前处于双锚下方，均判定为失守！
        """
        open_a = anchors.listing_open
        low_a = anchors.listing_low
        values = (open_a, low_a, intraday_low, current_price)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or value <= 0 for value in values):
            return True, "双锚失守检查阻断: 锚点、日内最低价或现价缺失/无效"

        # 首日锚点通常 listing_low <= listing_open；触及两者中的较低锚点即失守
        low_breached = (intraday_low < open_a and intraday_low < low_a)
        curr_breached = (current_price < open_a and current_price < low_a)

        if low_breached or curr_breached:
            return True, f"双锚失守(日内最低 {intraday_low:.2f} / 现价 {current_price:.2f} 击穿首日开盘 {open_a:.2f} 与首日最低 {low_a:.2f})"
        return False, ""
```

---

### 2.7 Gate 4: VWAP 多日结构完整性门禁（拒绝对缺失数据放行）

```python
# 在 GateOrchestrator 中实现的 Gate 4 严密核验规则：
# 现价不得补作 VWAP；按上市已完成交易日数要求对应时间跨度数据。
import math
from datetime import datetime
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo
from ats.strategy.listing_anchor_store import ListingAnchors, ListingAnchorStore
from ats.vwap_factory import VWAPSnapshot

def evaluate_gate4_vwap(
    vwap: Optional[VWAPSnapshot],
    code: str,
    current_price: float,
    listing_age_sessions: int,
    listing_anchors: Optional[ListingAnchors],
    as_of_time: datetime,
    max_vwap_stale_seconds: int,
) -> Tuple[bool, str]:
    if vwap is None:
        return False, "Gate 4 阻断: VWAP 数据源缺失，无法计算多周期量价支撑"

    if getattr(vwap, "stale", True):
        return False, "Gate 4 阻断: VWAP 数据过期或未同步最新行情"
    if getattr(vwap, "code", None) != code or getattr(vwap, "basis", None) != "turnover":
        return False, "Gate 4 阻断: VWAP 标的代码不匹配或不是个股成交额基准"
    try:
        if (as_of_time.tzinfo is None or isinstance(max_vwap_stale_seconds, bool)
                or not isinstance(max_vwap_stale_seconds, int) or max_vwap_stale_seconds <= 0):
            raise ValueError("行情时点必须带时区且 VWAP 最大延迟阈值必须为正数")
        snapshot_time = datetime.strptime(
            f"{vwap.date} {vwap.time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        age_seconds = (as_of_time.astimezone(ZoneInfo("Asia/Shanghai")) - snapshot_time).total_seconds()
    except (AttributeError, TypeError, ValueError):
        return False, "Gate 4 阻断: VWAP 或行情时点格式无效"
    if age_seconds < 0 or age_seconds > max_vwap_stale_seconds:
        return False, f"Gate 4 阻断: VWAP 快照超龄或晚于行情时点 ({age_seconds:.0f}s)"

    vwap_today = getattr(vwap, "vwap_1d", None)
    if (isinstance(current_price, bool) or not isinstance(current_price, (int, float))
            or not math.isfinite(current_price) or current_price <= 0
            or isinstance(vwap_today, bool) or not isinstance(vwap_today, (int, float))
            or not math.isfinite(vwap_today) or vwap_today <= 0):
        return False, "Gate 4 阻断: 现价或当日 VWAP 缺失/无效，禁止以现价补值"

    coverage = getattr(vwap, "coverage_days", None)
    if (isinstance(listing_age_sessions, bool) or not isinstance(listing_age_sessions, int)
            or listing_age_sessions < 1 or isinstance(coverage, bool)
            or not isinstance(coverage, int) or coverage < 0):
        return False, "Gate 4 阻断: 上市交易日数或 VWAP 覆盖天数类型无效"
    expected_coverage = min(listing_age_sessions, 10)
    if coverage < expected_coverage:
        return False, "Gate 4 阻断: 上市交易日数或 VWAP 覆盖数据无效"

    # D0 尚无封存锚点，只核验上方已校验的当日累计 VWAP。
    # D1-D4 才核验封存的首日锚定 VWAP，不能伪称多日结构。
    if listing_age_sessions == 1:
        pass
    elif listing_age_sessions < 5:
        anchor_vwap = getattr(listing_anchors, "listing_anchored_vwap", None)
        if (isinstance(anchor_vwap, bool) or not isinstance(anchor_vwap, (int, float))
                or not math.isfinite(anchor_vwap)
                or anchor_vwap <= 0):
            return False, "Gate 4 阻断: 早期上市标的缺少有效首日锚定 VWAP"
        if current_price < anchor_vwap * 0.985:
            return False, "Gate 4 阻断: 现价跌破首日锚定 VWAP 1.5%"
    elif listing_age_sessions < 10:
        vwap_5d = getattr(vwap, "vwap_5d", None)
        if (coverage < 5 or not getattr(vwap, "complete_5d", False)
                or isinstance(vwap_5d, bool) or not isinstance(vwap_5d, (int, float))
                or not math.isfinite(vwap_5d)
                or vwap_5d <= 0):
            return False, "Gate 4 阻断: 已满 5 个上市交易日但 5D VWAP 不完整"
    else:
        vwap_5d = getattr(vwap, "vwap_5d", None)
        vwap_10d = getattr(vwap, "vwap_10d", None)
        if (coverage < 10 or not getattr(vwap, "complete_5d", False)
                or isinstance(vwap_5d, bool) or not isinstance(vwap_5d, (int, float))
                or not math.isfinite(vwap_5d) or vwap_5d <= 0
                or not getattr(vwap, "complete_10d", False)
                or isinstance(vwap_10d, bool) or not isinstance(vwap_10d, (int, float))
                or not math.isfinite(vwap_10d)
                or vwap_10d <= 0):
            return False, "Gate 4 阻断: 已满 10 个上市交易日但 5D/10D VWAP 不完整"

    structure = getattr(vwap, "structure", None)
    known_structures = {"数据不足", "多周期偏强", "日内转弱 / 中期偏强", "多周期偏弱", "多周期混合"}
    if structure not in known_structures:
        return False, "Gate 4 阻断: VWAP 结构状态缺失"
    if listing_age_sessions >= 10 and structure == "数据不足":
        return False, "Gate 4 阻断: 满 10 日但 VWAPFactory 仍报告数据不足"

    # 破位水下超过 1.5% 拦截
    if current_price < vwap_today * 0.985 or structure == "多周期偏弱":
        return False, f"Gate 4 阻断: 均线破位或结构偏弱(现价 {current_price:.2f} < VWAP {vwap_today:.2f} 或 {structure})"

    return True, f"Gate 4 放行: 可用交易日 VWAP 与首日锚点数据完整 ({structure})"
```

---

### 2.8 Gate 5: 7 状态操作节点状态机与 TDE 真实终审（消灭假通过）

**新增模块**：`ats/strategy/ipo_operation_state_machine.py` 与 `ats/strategy/gate_orchestrator.py`

Gate 的 `ENTRY/WATCH/BLOCK` 是一次评估结果；业务生命周期另由以下七态承载，不能把发单意图当作成交，也不能让 Gate 结果跳过状态迁移：

| 状态 | 进入条件 | 允许的后续迁移 |
|:---|:---|:---|
| `OBSERVE` | 尚未满足候选观察门槛 | `ARMED`（Gate 0/1 允许且 PreHeat 达配置门槛）或 `BLOCKED`（硬性禁入） |
| `ARMED` | 环境与先验符合，等待盘中结构 | `ENTRY_READY`（Gate 0~4、TradePlan、Rank 1 与 RiskGate 全部通过）；`OBSERVE`（候选条件失效）；`BLOCKED`（硬门禁失败） |
| `ENTRY_READY` | 已取得有效开仓许可，但订单尚未成交 | `ENTERED` 仅在订单/成交回报确认后；拒单/撤单且零成交回 `ARMED`，部分成交则保留 `ENTERED` 和实际持仓量 |
| `ENTERED` | 至少有一笔已确认成交 | `HOLD_T1`（持仓跨收盘且受 T+1 限制）；`EXIT_READY`（存在可卖数量且退出规则触发） |
| `HOLD_T1` | 有持仓但受 T+1 可卖数量约束 | 解锁且退出规则触发后到 `EXIT_READY`；在持仓/解锁事实变化前不得发出卖单 |
| `EXIT_READY` | 退出条件成立且存在可卖数量 | 仅在成交回报确认清仓后回 `OBSERVE`；部分成交继续留在 `EXIT_READY` 并按剩余持仓管理 |
| `BLOCKED` | 任一硬门禁失败或必需输入缺失 | 仅在阻断原因解除、取得新鲜快照并完整重跑全部门禁后到 `OBSERVE/ARMED`，不得直接跳 `ENTRY_READY` |

每次迁移必须落下 `from_state/to_state/transition_reason/as_of_time/snapshot_version`。Gate 2 `CAUTION` 留在 `ARMED` 观察，不授予开仓许可。Gate 3 双锚失守先阻断当次交易；若之后出现来源有效、成交量支持的快速 reclaim，可将后续状态恢复到 `ARMED/WATCH`，但当日不得直接回 `ENTRY_READY`。`EXIT_READY` 表示退出条件待执行，不等同于已成交退出。

```python
"""六层门禁终审仲裁编排器 (真实对接 TradePlan, 买入区间与风控限额)"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from ats.strategy.channel_secondary_buy_strategy import IPOTradePlan
from ats.strategy.listing_anchor_store import ListingAnchors, ListingAnchorStore
from trading_kernel.core.intent import DecisionIntent
from trading_kernel.core.risk import RiskDecision
from trading_kernel.core.signal import StrategySignal
from trading_kernel.engine.risk_gate import RiskLimits
from trading_kernel.engine.risk_gate import evaluate as evaluate_risk_gate


@dataclass
class GatePassport:
    code: str
    name: str
    gate0_lrrm_passed: bool = False
    gate1_regime_passed: bool = False
    gate2_t1_carry_passed: bool = False
    gate2_state: str = ""
    gate2_score: float = 0.0
    gate3_anchor_passed: bool = False
    gate4_vwap_passed: bool = False
    gate5_tde_passed: bool = False
    final_decision: str = "BLOCK"  # ENTRY / WATCH / BLOCK
    block_at_gate: int = -1
    causal_chain: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskGateContext:
    """现有 RiskGate.evaluate 所需的实时账户、信号和风险上下文。"""
    intent: DecisionIntent  # 上游适配器须将 IPOTradePlan.position_pct / 100 转为 0.0~1.0
    signal: StrategySignal
    state: str
    limits: RiskLimits
    held_codes: Dict[str, str]
    current_stock_exposure: float
    current_sector_exposure: float
    current_total_exposure: float
    today_pnl_loss: float
    consecutive_losses: int
    current_time: str


class GateOrchestrator:
    """
    终审六层门禁编排器：
    - 短路拦截，任何一层不合格立即阻断并说明原因
    - Gate 2 的 CAUTION 标记为 WATCH，严禁直接进入 ENTRY！
    - Gate 3 使用当日最低价核验双锚
    - Gate 4 数据缺失必须阻断
    - Gate 5 严格核验 TradePlan 买入区间、动态盈亏比与风控额度
    """

    def evaluate(
        self,
        code: str,
        name: str,
        lrrm: Any,                       # LRRMSnapshot
        ipo_regime: Any,                 # IPORegimeSnapshot
        t1_carry: Any,                   # T1CarryResult
        listing_anchors: Optional[Any],  # ListingAnchors
        vwap: Optional[Any],             # VWAPSnapshot
        current_price: float,
        intraday_low: float,             # 当日最低价 (防漏检)
        listing_age_sessions: int,
        horse_rank: int,
        market_as_of_time: datetime,
        max_vwap_stale_seconds: int,
        trade_plan: Optional[IPOTradePlan] = None,
        risk_context: Optional[RiskGateContext] = None,
        d0_listing_open_price: Optional[float] = None,
        issue_price: Optional[float] = None,
        d0_open_break_pct: Optional[float] = None,
    ) -> GatePassport:
        passport = GatePassport(code=code, name=name)

        # ---------------- Gate 0: 宏观流动性 ----------------
        if lrrm is None:
            passport.block_at_gate = 0
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 0 阻断: LRRM 快照缺失")
            return passport
        if getattr(lrrm, "data_ready", False) is not True:
            passport.block_at_gate = 0
            passport.final_decision = "BLOCK"
            missing = getattr(lrrm, "missing_inputs", [])
            passport.causal_chain.append(f"Gate 0 阻断: LRRM 必需输入未就绪 {missing}")
            return passport
        if (lrrm.liquidity_regime not in ("NORMAL", "LOOSE")
                or lrrm.risk_appetite not in ("RISK_ON", "NEUTRAL")):
            passport.block_at_gate = 0
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(f"Gate 0 阻断: {lrrm.transition_reason}")
            return passport
        passport.gate0_lrrm_passed = True
        passport.causal_chain.append("Gate 0 放行: LRRM 宏观流动性允许")

        # ---------------- Gate 1: 新股情绪阶段 ----------------
        if ipo_regime is None:
            passport.block_at_gate = 1
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 1 阻断: IPO Regime 快照缺失")
            return passport
        if (getattr(ipo_regime, "data_ready", False) is not True
                or getattr(ipo_regime, "sample_count", 0) < 5):
            passport.block_at_gate = 1
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 1 阻断: IPO Regime 样本或关键数据未就绪")
            return passport
        if ipo_regime.state not in ("REPAIR", "CONTINUATION"):
            passport.block_at_gate = 1
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(f"Gate 1 阻断: 板块处于禁止买入阶段({ipo_regime.state})")
            return passport
        passport.gate1_regime_passed = True
        passport.causal_chain.append(f"Gate 1 放行: IPO Regime 处于放行阶段({ipo_regime.state})")

        # ---------------- Gate 2: T+1 Carry 隔夜兑现性 ----------------
        if t1_carry is None:
            passport.block_at_gate = 2
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 2 阻断: T1 Carry 快照缺失")
            return passport
        if t1_carry.state == "BLOCK" or t1_carry.is_pseudo_strength_blocked:
            passport.block_at_gate = 2
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(f"Gate 2 阻断: {t1_carry.veto_reason}")
            return passport

        # 消除误放行：CAUTION 严禁作为买入放行，降级为 WATCH！
        if t1_carry.state == "CAUTION":
            passport.gate2_t1_carry_passed = False
            passport.gate2_state = "CAUTION"
            passport.gate2_score = t1_carry.score
            passport.block_at_gate = 2
            passport.final_decision = "WATCH"
            passport.causal_chain.append(f"Gate 2 待命: T1 Carry 处于 CAUTION 观察区 (Score={t1_carry.score:.1f})，需日内进一步放量确认")
            return passport

        if (t1_carry.state != "ALLOW" or t1_carry.score < 65.0
                or t1_carry.nonlinear_zone == "EXTREME"):
            passport.block_at_gate = 2
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 2 阻断: T1 Carry 状态未知、评分不足或处于 EXTREME")
            return passport

        passport.gate2_t1_carry_passed = True
        passport.gate2_state = "ALLOW"
        passport.gate2_score = t1_carry.score
        passport.causal_chain.append(f"Gate 2 放行: T1 Carry 达标 (Score={t1_carry.score:.1f} >= 65.0)")

        # ---------------- Gate 3: 首日双锚失守防漏检 (按上市日龄生命周期分流) ----------------
        if listing_age_sessions < 1:
            passport.block_at_gate = 3
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 3 阻断: 上市交易日数无效 (< 1)")
            return passport

        if listing_age_sessions == 1:
            # D0 数据由实时行情和证券主数据直接提供，不依赖尚未封存的 ListingAnchors。
            d0_prices = (d0_listing_open_price, issue_price, intraday_low, current_price)
            if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0 for value in d0_prices)
                    or isinstance(d0_open_break_pct, bool)
                    or not isinstance(d0_open_break_pct, (int, float))
                    or not math.isfinite(d0_open_break_pct)
                    or not 0.0 <= d0_open_break_pct < 1.0):
                passport.block_at_gate = 3
                passport.final_decision = "BLOCK"
                passport.causal_chain.append("Gate 3 阻断: 首日价格输入缺失/无效或开盘容差配置无效")
                return passport
            open_p, issue_p = d0_listing_open_price, issue_price
            if (intraday_low < open_p * (1.0 - d0_open_break_pct)
                    or current_price < open_p * (1.0 - d0_open_break_pct)
                    or intraday_low < issue_p or current_price < issue_p):
                passport.block_at_gate = 3
                passport.final_decision = "BLOCK"
                passport.causal_chain.append(f"Gate 3 阻断: 上市首日跌破配置化开盘支撑或发行价 (日内低点 {intraday_low:.2f} / 现价 {current_price:.2f})")
                return passport
            passport.gate3_anchor_passed = True
            passport.causal_chain.append("Gate 3 放行: 上市首日开盘与发行价格支撑有效 (免检历史双锚)")
        else:
            # 上市次日及后续 (D1+): 必须具备合法封存的 ListingAnchors，严格核验日内最低价与现价双锚失守
            if not isinstance(listing_anchors, ListingAnchors) or listing_anchors.code != code:
                passport.block_at_gate = 3
                passport.final_decision = "BLOCK"
                passport.causal_chain.append("Gate 3 阻断: 次日及多日标的缺少合法封存的首日锚点")
                return passport
            store = ListingAnchorStore()
            breached, reason = store.check_dual_anchor_failure(
                listing_anchors, intraday_low, current_price
            )
            if breached:
                passport.block_at_gate = 3
                passport.final_decision = "BLOCK"
                passport.causal_chain.append(f"Gate 3 阻断: {reason}")
                return passport
            passport.gate3_anchor_passed = True
            passport.causal_chain.append("Gate 3 放行: 首日关键双锚守住")

        # ---------------- Gate 4: VWAP 结构完整性 ----------------
        vwap_ok, vwap_msg = evaluate_gate4_vwap(
            vwap, code, current_price, listing_age_sessions, listing_anchors,
            market_as_of_time, max_vwap_stale_seconds,
        )
        if not vwap_ok:
            passport.block_at_gate = 4
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(vwap_msg)
            return passport
        passport.gate4_vwap_passed = True
        passport.causal_chain.append(vwap_msg)

        # ---------------- Gate 5: TDE 真实终审 ----------------
        if trade_plan is None:
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append("Gate 5 待命: 尚未生成不可变 IPOTradePlan 交易计划网格")
            return passport

        plan_prices = (current_price, trade_plan.buy_zone_min, trade_plan.buy_zone_max)
        if (trade_plan.code != code
                or trade_plan.suggested_action not in ("BUY_SCOUT", "BUY_CONFIRM")
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) or value <= 0 for value in plan_prices)
                or trade_plan.buy_zone_max < trade_plan.buy_zone_min):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 阻断: 交易计划代码或买入价格区间无效")
            return passport

        # 1. 价格区间防追高
        if current_price < trade_plan.buy_zone_min:
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append(f"Gate 5 观察: 现价 {current_price:.2f} 低于买入区间下限 {trade_plan.buy_zone_min:.2f}")
            return passport
        if current_price > trade_plan.buy_zone_max:
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(f"Gate 5 阻断: 现价 {current_price:.2f} 脉冲突破买入上限 {trade_plan.buy_zone_max:.2f} (防追高)")
            return passport

        # 2. 动态盈亏比 (RR >= 2.5)
        rr = trade_plan.calculate_rr_now(current_price)
        if (rr is None or isinstance(rr, bool) or not isinstance(rr, (int, float))
                or not math.isfinite(rr) or rr <= 0):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 阻断: 止损/目标锚点无效，无法计算动态盈亏比")
            return passport
        if rr < 2.5:
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(f"Gate 5 阻断: 动态盈亏比不足 {rr:.2f} < 2.5:1")
            return passport

        # 3. 赛马排位 Top 1 限制
        if horse_rank != 1:
            passport.block_at_gate = 5
            passport.final_decision = "WATCH"
            passport.causal_chain.append(f"Gate 5 待命: 赛马排位为 #{horse_rank}，等待晋升领头羊")
            return passport

        # 4. 实际调用 RiskGate；仓位单位适配后仍需校验上下文并严格失败关闭。
        if (risk_context is None or risk_context.signal.code != code
                or risk_context.intent.code != code
                or risk_context.intent.code != risk_context.signal.code
                or risk_context.intent.action != "BUY"
                or isinstance(risk_context.intent.size_pct, bool)
                or not isinstance(risk_context.intent.size_pct, (int, float))
                or not math.isfinite(risk_context.intent.size_pct)
                or not 0 < risk_context.intent.size_pct <= 1.0
                or not risk_context.current_time
                or getattr(getattr(risk_context.intent, "reason", None), "regime", "") == "MANUAL_OVERRIDE"):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 风控阻断: RiskGate 上下文缺失或信号代码不匹配")
            return passport
        try:
            market_time = market_as_of_time.astimezone(ZoneInfo("Asia/Shanghai"))
            risk_time = datetime.fromisoformat(risk_context.current_time.replace("Z", "+00:00"))
            signal_time = datetime.fromisoformat(risk_context.signal.ts.replace("Z", "+00:00"))
            if risk_time.tzinfo is None:
                risk_time = risk_time.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            if signal_time.tzinfo is None:
                signal_time = signal_time.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            risk_time = risk_time.astimezone(ZoneInfo("Asia/Shanghai"))
            signal_time = signal_time.astimezone(ZoneInfo("Asia/Shanghai"))
            signal_age_seconds = (market_time - signal_time).total_seconds()
            risk_clock_skew_seconds = abs((risk_time - market_time).total_seconds())
        except (AttributeError, TypeError, ValueError, OverflowError):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 风控阻断: RiskGate 行情时点或信号时间无效")
            return passport
        if (signal_age_seconds < 0 or signal_age_seconds > 300
                or risk_clock_skew_seconds > 5):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 风控阻断: 信号超龄、来自未来或账户时钟与行情时点不一致")
            return passport
        risk_decision = evaluate_risk_gate(
            risk_context.intent,
            risk_context.signal,
            risk_context.state,
            limits=risk_context.limits,
            held_codes=risk_context.held_codes,
            current_stock_exposure=risk_context.current_stock_exposure,
            current_sector_exposure=risk_context.current_sector_exposure,
            current_total_exposure=risk_context.current_total_exposure,
            today_pnl_loss=risk_context.today_pnl_loss,
            consecutive_losses=risk_context.consecutive_losses,
            current_time=market_time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        if (not risk_decision.allowed or risk_decision.order is None
                or risk_decision.final_action != "BUY"
                or risk_decision.order.code != code
                or risk_decision.order.action != "BUY"
                or isinstance(risk_decision.order.price, bool)
                or not isinstance(risk_decision.order.price, (int, float))
                or not math.isfinite(risk_decision.order.price)
                or not trade_plan.buy_zone_min <= risk_decision.order.price <= trade_plan.buy_zone_max
                or isinstance(risk_decision.order.size_pct, bool)
                or not isinstance(risk_decision.order.size_pct, (int, float))
                or not math.isfinite(risk_decision.order.size_pct)
                or risk_decision.order.size_pct <= 0
                or isinstance(risk_decision.order.stop_price, bool)
                or not isinstance(risk_decision.order.stop_price, (int, float))
                or not math.isfinite(risk_decision.order.stop_price)
                or risk_decision.order.stop_price <= 0
                or abs(risk_decision.order.stop_price - trade_plan.structural_stop) > 0.001):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append(
                f"Gate 5 风控阻断: {risk_decision.reject_context or risk_decision.final_action}"
            )
            return passport

        approved_rr = trade_plan.calculate_rr_now(risk_decision.order.price)
        if (approved_rr is None or isinstance(approved_rr, bool)
                or not isinstance(approved_rr, (int, float))
                or not math.isfinite(approved_rr) or approved_rr < 2.5):
            passport.block_at_gate = 5
            passport.final_decision = "BLOCK"
            passport.causal_chain.append("Gate 5 阻断: RiskGate 批准价格对应 RR 无效或低于 2.5:1")
            return passport

        # 只有 TradePlan、RR、赛马名次及真实 RiskDecision 全部通过才生成 ENTRY。
        passport.gate5_tde_passed = True
        passport.final_decision = "ENTRY"
        passport.causal_chain.append(
            f"Gate 5 终审通过: TradePlan 合规，批准价格 RR {approved_rr:.2f}，赛马第一名，"
            f"RiskGate 已批准订单 {risk_decision.order.order_id} (ENTRY)"
        )
        return passport
```

---

### 2.9 华大海天伪强反例四项联合判据与回归断言

#### 伪强结构量化判据数学模型：
$$\text{IsPseudoStrength} = \begin{cases}
\text{True}, & \text{若同时满足以下 4 项条件：} \\
& \text{1. } \text{MinutesAboveVWAP} / \text{TotalMinutes} \ge 0.70 \quad (\text{分时价格表面看似站稳}) \\
& \text{2. } \text{TurnoverClimbSpeed} \ge 0.8\%/\text{min} \lor \text{TurnoverRate} \ge 75.0\% \quad (\text{天量松动}) \\
& \text{3. } \text{CloseLocation} = \frac{Close - Low}{High - Low} \le 0.40 \quad (\text{收盘落在当日振幅下方 40\%}) \\
& \text{4. } \text{PullbackFromPeak} = \frac{High - Close}{High} \ge 25.0\% \quad (\text{高位深度跳水}) \\
\text{False}, & \text{其他}
\end{cases}$$

#### 自动化回归测试规格 (`tests/test_regression_hua_da_hai_tian.py`)：

```python
"""华大海天伪强反例永久回归测试集 (要求 100% 拦截通过率)"""
import pytest
from ats.strategy.ipo_live_heat_engine import IPOLiveHeatEngine
from ats.strategy.t1_carry_evaluator import T1CarryEvaluator
from ats.strategy.listing_anchor_store import ListingAnchors
from ats.strategy.gate_orchestrator import GateOrchestrator


def test_hua_da_hai_tian_pseudo_strength_blocked():
    """华大海天首日：表面在线上、极端换手、长上影收低、回撤达 42%"""
    live_engine = IPOLiveHeatEngine()
    carry_evaluator = T1CarryEvaluator()

    live_snap = live_engine.evaluate(
        code="600XXX",
        ret_pct=30.0,
        turnover_pct=86.5,
        price_vwap_dist_pct=3.5,
        open_premium_pct=25.0,
        slope_deg=20.0,
        high_p=45.0,
        low_p=20.0,
        curr_p=26.0,
        turnover_climb_speed=1.2,
        minutes_above_vwap_ratio=0.78,
        pullback_from_peak_pct=42.2,  # (45 - 26) / 45 = 42.2%
        now_hm="1500",
    )

    assert live_snap.close_location <= 0.40
    assert live_snap.minutes_above_vwap_ratio >= 0.70
    assert live_snap.pullback_from_peak_pct >= 25.0

    carry_result = carry_evaluator.evaluate(code="600XXX", live_heat=live_snap)
    assert carry_result.state == "BLOCK"
    assert carry_result.is_pseudo_strength_blocked is True
    assert "HUA_DA_HAI_TIAN_PSEUDO_STRENGTH_VETO" in carry_result.veto_reason


def test_hua_da_hai_tian_dual_anchor_failure_d1():
    """次日跳空击穿首日双锚"""
    from datetime import datetime
    orchestrator = GateOrchestrator()
    anchors = ListingAnchors(
        code="600XXX",
        listing_date="2026-08-10",
        listing_open=25.0,
        listing_high=45.0,
        listing_low=20.0,
        listing_close=26.0,
        listing_vwap=24.5,
        listing_anchored_vwap=24.5,
        first_30m_vwap=28.0,
        close_location=0.24,
        first_day_turnover=86.5,
    )

    class MockObj: pass
lrrm = MockObj(); lrrm.liquidity_regime = "NORMAL"; lrrm.risk_appetite = "NEUTRAL"; lrrm.data_ready = True
ipo_regime = MockObj(); ipo_regime.state = "CONTINUATION"; ipo_regime.data_ready = True; ipo_regime.sample_count = 5
    t1_carry = MockObj(); t1_carry.state = "ALLOW"; t1_carry.score = 70.0
    t1_carry.nonlinear_zone = "NORMAL"; t1_carry.is_pseudo_strength_blocked = False

    passport = orchestrator.evaluate(
        code="600XXX",
        name="华大海天",
        lrrm=lrrm,
        ipo_regime=ipo_regime,
        t1_carry=t1_carry,
        listing_anchors=anchors,
        vwap=None,
        current_price=18.5,
        intraday_low=17.5,
        listing_age_sessions=2,
        horse_rank=1,
        market_as_of_time=datetime.fromisoformat("2026-08-11T10:00:00+08:00"),
        max_vwap_stale_seconds=120,
    )

    assert passport.final_decision == "BLOCK"
    assert passport.block_at_gate == 3
    assert "双锚失守" in passport.causal_chain[-1]
```

---

### 2.10 Historical Cut-Off 历史截断回放引擎与时间沙箱

**新增模块**：`tools/historical_cutoff_replay_engine.py`

```python
"""历史截断无未来回放引擎实现"""
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime


class TimeSandbox:
    """时间沙箱：物理隔离未来信息"""
    def __init__(self, current_cutoff_time: str):
        self.cutoff_dt = self.normalize_time(current_cutoff_time)

    @staticmethod
    def normalize_time(value: Any) -> pd.Timestamp:
        try:
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError("时间戳为空")
            return (timestamp.tz_localize("Asia/Shanghai") if timestamp.tzinfo is None
                    else timestamp.tz_convert("Asia/Shanghai"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"无效或时区不兼容的回放时间戳: {value!r}") from exc

    def filter_bars(self, df: pd.DataFrame, time_col: str = "datetime") -> pd.DataFrame:
        if df.empty or time_col not in df.columns:
            raise ValueError(f"回放输入缺失行情或时间列: {time_col}")
        # 逐项规范时区，显式拒绝脏值与混合时区造成的隐式 dtype 转换。
        timestamps = df[time_col].map(self.normalize_time)
        mask = timestamps <= self.cutoff_dt
        filtered = df.loc[mask].copy()
        filtered[time_col] = timestamps.loc[filtered.index]
        return filtered.sort_values(time_col)


class HistoricalCutoffReplayEngine:
    """纯历史驱动回放；所有输入通过 loader，所有输出由已截断 bars 计算。"""
    def __init__(self, sample_codes: List[str], load_history: Any,
                 evaluate_as_of: Any, build_summary: Any,
                 start_date: str = "2026-08-01"):
        self.sample_codes = sample_codes
        self.load_history = load_history
        self.evaluate_as_of = evaluate_as_of
        self.build_summary = build_summary
        self.start_date = start_date

    def replay_stock(self, code: str) -> Dict[str, Any]:
        """对每个历史 bar 时点重算，只把已知数据传给决策链，再组装 15 项结果。"""
        history = self.load_history(code, self.start_date)
        bars = history.bars.copy()
        if bars.empty:
            raise ValueError(f"{code}: 回放区间无行情数据")
        bars["datetime"] = bars["datetime"].map(TimeSandbox.normalize_time)
        bars = bars.sort_values("datetime")

        observations = []
        for cutoff in bars["datetime"].drop_duplicates().sort_values():
            sandbox = TimeSandbox(str(cutoff))
            known_bars = sandbox.filter_bars(bars)
            observation = self.evaluate_as_of(code, known_bars, sandbox.cutoff_dt)
            observed_at = TimeSandbox.normalize_time(observation["as_of_time"])
            if observed_at > sandbox.cutoff_dt:
                raise ValueError("回放观察时间越过当前 cutoff，拒绝未来数据泄漏")
            observations.append(observation)

        result = self.build_summary(history.metadata, observations)
        required = {
            "code", "name", "listing_date", "preheat_at_listing",
            "first_entry_ready_time", "max_heat_before_entry", "t1_carry_close",
            "D1_open_gap", "D1_min_vs_listing_open", "D1_min_vs_listing_low",
            "D1_reclaim_status", "false_entry_flag", "survival_flag",
            "blocked_by_rule", "transition_log",
        }
        if set(result) != required:
            raise ValueError("回放汇总字段契约不符，预期 15 项标准字段")
        return result
```

输入契约：`load_history` 返回含 `metadata` 和原始 `bars` 的对象；`evaluate_as_of` 仅接收 cutoff 前行情，并在每个时点重新构造快照、运行 Gate 0～5；`build_summary` 根据实际观测生成 15 项汇总字段。任一历史数据、时间戳、输出字段或时点越界校验失败时，回放样本标记为无效，不得计入通过率。

---

<a id="ch3"></a>
## 叁、本地 LLM 自学习决策系统（Ollama JSON Schema 约束）

### 3.1 四不原则与降级守护

1. **不等待模型**：LLM 推理与 ATS 交易轮询、Qt 主事件循环分离；关键路径不得进行 IPC、序列化、磁盘/网络 I/O 或推理。
2. **不直连**：LLM 仅输出 Proposal 建议，任何交易动作仍由确定性规则、Gate 0~5 与 RiskGate 决定。
3. **不黑盒**：必须输出因果链，并受 Ollama JSON Schema 强类型约束。
4. **不在线更新**：盘中只读推理，微调与对齐只在盘后执行。

### 3.2 Ollama 原生结构化输出（JSON Schema 替代纯 Prompt）

```python
# ats/llm/llm_worker.py：Market Regime Agent 的结构化 payload
import requests
import json
import math
from typing import Any, Callable

SENTIMENT_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sentiment_score": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "key_catalysts": {"type": "array", "items": {"type": "string"}},
        "risk_warnings": {"type": "array", "items": {"type": "string"}},
        "regime_hint": {"type": "string"},
        "reasoning": {"type": "string", "maxLength": 300}
    },
    "required": ["sentiment_score", "confidence", "key_catalysts", "risk_warnings", "regime_hint", "reasoning"]
}

def validate_sentiment_payload(proposal: Any) -> bool:
    required = SENTIMENT_OUTPUT_SCHEMA["required"]
    return (isinstance(proposal, dict) and set(proposal) == set(required)
            and not isinstance(proposal["sentiment_score"], bool)
            and isinstance(proposal["sentiment_score"], (int, float))
            and math.isfinite(proposal["sentiment_score"])
            and -1.0 <= proposal["sentiment_score"] <= 1.0
            and not isinstance(proposal["confidence"], bool)
            and isinstance(proposal["confidence"], (int, float))
            and math.isfinite(proposal["confidence"])
            and 0.0 <= proposal["confidence"] <= 1.0
            and isinstance(proposal["key_catalysts"], list)
            and all(isinstance(item, str) for item in proposal["key_catalysts"])
            and isinstance(proposal["risk_warnings"], list)
            and all(isinstance(item, str) for item in proposal["risk_warnings"])
            and isinstance(proposal["regime_hint"], str)
            and isinstance(proposal["reasoning"], str)
            and len(proposal["reasoning"]) <= 300)


def query_ollama_structured(
    prompt: str, schema: dict, validate_payload: Callable[[Any], bool],
    model: str = "qwen2.5:14b-instruct-q5_K_M",
) -> dict:
    """Worker 内调用 Ollama；返回统一结果，不把服务错误抛到交易主线程。"""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema,  # 核心：Ollama 官方 Structured Outputs 特性
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512}
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        proposal = json.loads(resp.json()["response"])
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {"status": "UNAVAILABLE", "proposal": None, "error": str(exc)}

    # Schema 限制语法形状；所选 Agent 对应的 validator 再检查业务边界。
    try:
        is_valid = validate_payload(proposal)
    except Exception as exc:
        return {"status": "INVALID", "proposal": None, "error": f"本地校验器异常: {exc}"}
    if not is_valid:
        return {"status": "INVALID", "proposal": None, "error": "输出未通过本地契约校验"}
    return {"status": "OK", "proposal": proposal, "error": ""}
```

`UNAVAILABLE` 或 `INVALID` 由 Worker 写入响应队列；主进程丢弃该轮 Proposal，继续纯规则流程并记录原因。主线程不能等待模型完成，超时/过期的响应按 request_id 和生成时间丢弃。

#### ATS/Qt 主路径与 LLM 旁路隔离契约 (`ats/llm/llm_bridge.py`)

操作系统、Python 运行时及 GPU 调度不是硬实时系统；`multiprocessing.Queue.put_nowait/get_nowait()` 也不等价于“无锁、绝不阻塞”。因此本方案不承诺无法证明的 **0 ms / 100% 绝对流畅**，改以可检查的隔离边界和压测门槛保证 LLM 故障不会成为交易主线的等待条件：

1. **300ms 交易轮询禁区**：轮询中不得调用 Queue、构造/序列化 LLM context、排队、读取 LLM 缓存或健康状态、检查进程、记录同步日志、访问数据库或触发网络/模型操作；v1.x 策略层始终走纯规则路径。只有后续版本经离线/影子/人工审批且性能门槛通过，才可在独立变更中评估本地快照读取；故障由旁路熔断，异步记录 `LLM_FALLBACK_DEFAULT`，不改变交易结论。
2. **Qt 事件循环禁区**：GUI 线程不消费 multiprocessing 队列、不校验完整 Proposal、不做模型/磁盘/网络工作。LLM 控制线程合并结果后，通过 Qt queued signal 投递轻量 UI 更新；过载时合并/丢弃旧 UI 更新，不能积压事件。
3. **队列端点所有权与有界快照**：父进程的 LLM 控制线程独占父端队列端点：只负责投递请求、读取结果；Worker 只在自身进程消费请求、产出结果；ATS 轮询和 Qt 事件线程不得持有或调用队列端点。LLM 控制线程维护供 UI/离线记录使用的每标的不可变快照，完成校验后整体替换已发布快照，不在控制/展示读取路径加锁或原地删除缓存项。缓存 TTL 使用 `time.monotonic()`；行情 `as_of_time` 另与决策快照时点核验，拒绝未来、过期和时钟不兼容的响应。该快照不暴露给 v1.x 交易决策路径。
4. **队列和计算预算**：请求队列与结果队列均设硬上限 `maxsize=100`，同时限制消息 JSON 编码后不超过 64 KiB、单标的至多一个进行中请求、候选仅取最新状态且待处理请求必须有失效期限。请求队列满时由控制线程丢弃/合并；结果队列满时丢弃重复/过期结果并异步计数 `LLM_QUEUE_FULL_DROP`；不得让旧请求排队等待数分钟后再推理。Worker 每次请求超时 30 秒，失败后熔断退避；重试不在交易或 UI 线程执行。
5. **有界结果排空**：控制线程每次最多处理 8 条或运行 2ms（先到即停），剩余结果留待下一轮；每标的只接受当前 request 及最新序号，禁止旧响应覆盖新响应。不得在 Qt timer callback 或 300ms 轮询中 `while get_nowait()` 无界排空。
6. **健康快照与失败关闭**：独立监督线程读取 Worker 进程 sentinel/退出码并接收有界心跳，更新 Worker/Ollama 健康快照；连续 3 秒无健康更新、请求超时、Worker 异常退出或 Proposal 校验失败均打开熔断，旁路清除可用建议状态并异步记录故障。交易路径不读取健康位；其纯规则决策不依赖 LLM 状态，因此旁路失效不会改变或阻塞交易结果。监督线程不调用阻塞式 `join()`、无界网络探活或 `Process.is_alive()`。
7. **LLM 权限默认只读**：v1.x Proposal 仅供展示、检索与留痕，不修改 Gate 状态、PreHeat/Carry 分数、阈值、TradePlan、仓位或订单。只有离线成熟样本、影子验证和人工审批完成后，才可另行定义有界且版本化的评分影响；此前正负修正均为 `0.0`。

请求队列由父进程控制线程投递、Worker 消费；结果队列由 Worker 投递、父进程控制线程有界读取。请求构造、JSON 编码、结果校验、熔断和日志均在专用 LLM 控制线程/Worker/监督线程完成；ATS 交易决策路径不读取 LLM 快照或健康状态，始终只执行规则决策。`put_nowait/get_nowait` 只用于隔离线程中的尽力而为投递，不作为硬实时证明。Windows 多进程固定使用 `spawn`，进程创建不得发生在模块导入或 Qt 窗口构造期间；退出通过有限时长的后台关闭流程清理 Queue/Worker，Qt 关闭回调不得等待模型或 `join()`。

`request_id`、`ticker`、`as_of_time`、`generated_at`、`model_id`、`prompt_version` 由 Worker 从入队任务注入信封元数据；模型 payload 不得自报这些字段。桥接器验证信封与待处理请求完全对应，再验证 Proposal Schema、数值范围、时效和证据截止时间。错误结果只产生异步状态/计数，不将异常抛到 ATS 或 Qt 主线程。

**Windows 资源隔离边界**：Python Worker 设置 `BELOW_NORMAL_PRIORITY_CLASS` 只能降低 Worker 自身调度优先级，不能降低独立 Ollama 服务或 GPU kernel 的优先级。若 ATS 管理 Ollama 服务，需在服务启动层单独配置并验收；若服务由用户/系统外部管理，不擅自更改其优先级，必须通过 CPU/GPU 竞争压力测试，否则禁用 LLM 推理旁路。`OLLAMA_NUM_PARALLEL=1` 仅限制并行请求，不能证明显存或 GPU 资源不会争用。

#### Windows 进程与 IPC 边界

1. Worker 可设置 `BELOW_NORMAL_PRIORITY_CLASS` 作为降低自身 CPU 调度优先级的尽力而为措施；不得宣称它给 ATS/Qt 提供绝对 CPU 特权。Ollama 是独立服务时，必须单独识别其进程归属并做受控压力验收。
2. `OLLAMA_NUM_PARALLEL=1` 和模型驻留时间只限制服务并发/生命周期，不能保证显存或 GPU 不争用；GPU 压力场景无法满足实时验收时必须关闭推理。
3. Windows 多进程用 `spawn`，入口受 `if __name__ == "__main__"`/`freeze_support()` 保护；子进程不创建 Qt 对象。跨进程消息使用严格 Schema 的 JSON 基础类型、有限长度字符串/列表和字节上限，不传 Qt/Pandas/C 扩展对象；编码、传输或解码失败须转为结构化失败状态。
4. Queue 使用系统同步原语和 feeder thread，基础类型消息也不能消除死锁/关闭竞态。Worker 清理、Queue 关闭和 join 必须在后台有界完成；UI/交易路径不调用 `join_thread()`、无期限 `join()` 或同步日志 I/O。

### 3.3 三大智能体 Agent 规范

三个 Agent 运行在隔离 Worker 中，不持有交易执行器、账户密钥或下单接口。上面的 `SENTIMENT_OUTPUT_SCHEMA` 仅定义 Market Regime Agent 的 payload；Case Retrieval 与 Post-close Review 必须各自定义 `additionalProperties: false` 的专属 payload Schema，禁止把不同任务硬塞进情绪字段。

| Agent | 输入 | 输出职责 | 禁止事项 |
|:---|:---|:---|:---|
| **Market Regime Agent** | 截止当前时点的全市场及新股横截面快照 | 提供情绪分数、阶段提示、催化剂和风险提示 | 不直接修改 LRRM/IPO Regime 状态，不下单 |
| **Case Retrieval Agent** | 当前候选快照及历史相似案例检索结果 | 给出可追溯的相似案例 ID、差异点和证据摘要 | 不读取 cutoff 之后的行情或结果标签 |
| **Post-close Review Agent** | 已封存的当日快照、Gate 因果链及成熟结果标签 | 生成经来源标注的复盘候选与偏好样本草稿 | 盘中不运行训练，不自动修改规则阈值 |

Ollama 仅生成所选 Agent 的 `payload`；Worker 通过匹配的 validator 校验 payload 后，将可信运行元数据组装成统一信封：`{agent_type, metadata: {request_id, scope_id, ticker, as_of_time, generated_at, model_id, prompt_version, evidence_ids}, payload}`。`scope_id` 为标的代码或 `MARKET`；按股响应的 `ticker` 必须匹配入队请求，市场级响应不得被伪装成单股快照。信封字段集合固定且拒绝额外字段；元数据由 Worker 注入，不能让模型自行编造。`CASE_RETRIEVAL_SCHEMA` 的 payload 至少包含相似案例 ID、发布时间、证据 ID、差异点和证据摘要；`POST_CLOSE_REVIEW_SCHEMA` 至少包含输入快照哈希、cutoff、标签成熟状态、标签来源和复盘草稿。Gate 只消费 Market Regime payload 中经验证的字段；缺字段、过期时间、request 不匹配或证据越过回放 cutoff 时将信封标为无效。

### 3.4 本地时序向量库（BGE-M3 1024 维修正）

```python
# ats/llm/vector_store.py
import pyarrow as pa
import lancedb

# 彻底纠正：BGE-M3 官方标准 Dense 向量为 1024 维！
NEWS_EMBEDDING_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("embedding", pa.list_(pa.float32(), 1024)),  # 修正为 1024 维
    pa.field("ticker", pa.string()),
    pa.field("published_at", pa.string()),
    pa.field("created_at", pa.string()),
])
```

入库记录必须保存来源 URL/记录 ID、发布时间、采集时间、标的、事件日期、embedding 模型版本和内容哈希。相似案例检索按 `published_at <= as_of_time` 过滤；不同维度或 embedding 版本不得混写同一向量列。

既有 768 维表不得原地写入 1024 维向量。迁移时按 embedding 模型版本创建新的 1024 维版本表，离线重嵌入并校验行数、维度和内容哈希；全部验收后原子切换活动表指针，旧表保留至回滚窗口结束。重建期间检索只读旧表，禁止新旧维度混用。

### 3.5 离线自学习闭环（SFT / DPO 样本生成器）

1. **样本候选**：收盘后由 Post-close Review Agent 生成草稿，每条记录包含输入快照哈希、cutoff、模型/提示版本、Gate 因果链、结果成熟时间和标签来源。
2. **标签成熟**：首日与次日结果未完整的样本保持 `PENDING`，不得进入训练集；人工复核后才可标记 `ACCEPTED`。
3. **数据集切分**：按事件/上市日期分组做时间前向切分；同一只股票的同一事件不能跨训练集和验证集，未来收益标签不能进入决策输入。
4. **SFT**：仅使用已复核的输入与标准 Proposal 作为监督样本；保存数据集哈希、基座模型、LoRA/Adapter 版本及训练参数。
5. **DPO**：偏好对必须有同一 cutoff 下的 chosen/rejected Proposal、两者原因和复核人；不得以未来收益单指标自动生成偏好对。
6. **晋级与回滚**：盘后离线评估通过后先进入影子模式；与规则基线比较误入率、漏报率、Schema 合格率和延迟，达到 YAML 门槛后才可人工晋级。任一关键指标回退即回滚至上一模型版本。

---

<a id="ch4"></a>
## 肆、数据 Schema、数据库迁移与新增文件清单

### 4.1 配置文件（YAML 阈值全局对齐）

```yaml
# config/ipo_sentiment.yaml
version: "1.1"
ipo_preheat:
  watch_candidate_threshold: 55.0  # 全局对齐
  hot_candidate_threshold: 75.0
  weights:
    valuation: 0.25
    subscription: 0.25
    scarcity: 0.20
    theme: 0.20
    capital_structure: 0.10

ipo_live_heat:
  overheat_threshold_warning: 15.0
  overheat_threshold_veto: 35.0
  exhaustion_risk_threshold_veto: 45.0
  close_location_veto: 0.40

vwap_freshness:
  max_stale_seconds: 120

ipo_regime:
  lookback_stocks: 10
  lookback_days: 20
  transition_thresholds:
    distribution_to_repair:
      d1_positive_rate_min: 0.40
      limit_down_rate_max: 0.10
    repair_to_continuation:
      d1_positive_rate_min: 0.55
      new_high_ratio_min: 0.40
    continuation_to_mania:
      d1_positive_rate_min: 0.80
      turnover_extreme_pct: 60.0
    mania_to_exhaustion:
      first_day_peak_ratio_min: 0.40
    exhaustion_to_distribution:
      d1_positive_rate_max: 0.30

lrrm:
  amount_shock_percentile: 5
  amount_tight_percentile: 20
  amount_loose_percentile: 80
  advance_decline_shock: 0.20
  limit_down_shock: 30

t1_carry:
  allow_threshold: 65.0
  caution_threshold: 40.0
  adjustment_bounds:
    max_positive: 10
    max_negative: -25
```

启动时由配置加载器对 YAML 执行 `safe_load`，把 `ipo_preheat` 节传给 `PreHeatConfig.from_mapping()`；引擎只接收这份配置对象，不再另设评分阈值常量。配置缺键、权重和不为 1 或阈值顺序错误时，记录配置错误并禁止生成可交易候选。

当前 YAML 示例尚非全量阈值清单。Stage 0 必须完成以下配置归属；缺少必需键或版本/哈希无法解析时，不得以代码默认值继续生成交易许可：

| 配置域 | 必须归入的运行参数/阈值 |
|:---|:---|
| `ipo_regime` / `lrrm` | 有效样本窗口和最小样本数、D1/D2/D3 转换阈值、20D/60D 成交分位、市场 breadth/跌停/炸板及流动性特征的门槛与缺失策略 |
| `ipo_live_heat` / `t1_carry` | 非线性分段、过热/衰竭阈值、Carry 加减分边界、ALLOW/CAUTION/BLOCK 分界、伪强四项判据及其单位 |
| `listing_anchors` / `vwap_execution` / `trade_gate` | `d0_open_break_pct` 首日开盘支撑容差、锚点与 reclaim 条件、VWAP 新鲜度/结构阈值、信号最大年龄、最小 RR、批准止损容差、仓位上限和允许指令 |
| `llm_config` | Worker 请求超时、缓存 TTL、队列上限、消息字节上限、并发/候选上限、结果批次/耗时预算、健康心跳/熔断时限、回退修正量和性能验收门槛 |
| `replay` / `evaluation` | 样本起止范围、时区、前向切分规则、标签成熟时间、效果指标定义及硬验收目标 |

每次决策快照、回放样本、Agent 信封和模型晋级记录均绑定配置版本与内容哈希；评估结果不能在缺少该绑定时用于晋级。

### 4.2 现有数据库迁移方案（ALTER TABLE 增量补列）

针对已存在的 `market_pulse.db`，方案中设计显式迁移函数，在系统启动时安全补齐缺失列：

```python
def migrate_market_pulse_db(db_path: str = "./market_pulse.db") -> None:
    """对生产使用的同一路径执行可重入迁移；失败时启动不得进入交易态。"""
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=15.0)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        # 首次安装时先建出现有基线列；既有表不会被重建或覆盖历史数据。
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_sentiment (
                date TEXT PRIMARY KEY, index_pct REAL, breadth_ratio REAL,
                up_count INTEGER, down_count INTEGER, limit_up INTEGER,
                limit_down INTEGER, temperature REAL, worst_sectors_json TEXT,
                top_sectors_json TEXT, indices_json TEXT, source_version TEXT,
                created_at TEXT
            )
        """)
        cursor.execute("PRAGMA table_info(daily_sentiment)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        add_cols = {
            "lrrm_state": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "ipo_regime_state": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "source_version": "TEXT DEFAULT 'daily_sentiment.v1.1'",
        }
        for col_name, col_def in add_cols.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE daily_sentiment ADD COLUMN {col_name} {col_def}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

迁移调用契约：必须在交易服务就绪前执行；只有迁移成功才允许进入候选计算阶段。`db_path` 必须与现有 `market_pulse_db.DB_PATH` 解析到同一文件，启动日志记录迁移前后 schema 与数据库路径；迁移异常由启动边界捕获并保持交易关闭。

历史行新增的状态列以 `UNKNOWN` 回填；读取适配层必须将该值解释为未就绪，不得推导成 `NORMAL`、`DISTRIBUTION` 或可交易状态。只有真实计算且输入健康的新结果才能写入有效状态。

### 4.3 新增文件清单

```
新增模块清单:
├── ats/strategy/
│   ├── lrrm_engine.py                     # Gate 0: LRRM 流动性状态机
│   ├── ipo_regime_fsm.py                  # Gate 1: IPO Regime 五态 FSM
│   ├── ipo_preheat_engine.py              # IPO Pre-Heat 上市前先验打分引擎
│   ├── ipo_live_heat_engine.py            # IPO Live Heat 实时动能与 6 大非线性函数
│   ├── t1_carry_evaluator.py              # Gate 2: T+1 Carry 与华大海天伪强过滤
│   ├── listing_anchor_store.py            # Gate 3: 首日 9 大锚点永久存储
│   ├── ipo_operation_state_machine.py     # 7 状态操作节点状态机
│   └── gate_orchestrator.py               # Gate 5: 六层门禁 + 实际 RiskGate 终审
├── ats/llm/
│   ├── __init__.py
│   ├── llm_bridge.py                      # 主系统桥接层 (进程隔离与优雅降级)
│   ├── llm_worker.py                      # 独立 Worker (Ollama JSON Schema 结构化输出)
│   ├── vector_store.py                    # LanceDB 向量存储 (1024 维 BGE-M3)
│   ├── memory_manager.py                  # 三级经验记忆管理 (热/温/冷)
│   ├── agent_pipeline.py                  # 三类只读 Agent 编排与证据追踪
│   ├── sft_dpo_pipeline.py                # 盘后样本校验、训练评估与影子晋级
│   ├── news_collector.py                  # 新闻采集管线
│   ├── embedding_service.py               # 本地 BGE-M3 服务
│   └── adapter_manager.py                 # Multi-Adapter 策略专家管理
├── config/
│   ├── ipo_sentiment.yaml                 # 情绪感知与门禁完整配置
│   ├── llm_config.yaml                    # LLM 结构化输出与推理配置
│   └── listing_anchors.json               # 首日关键锚点存储
└── tools/
    ├── historical_cutoff_replay_engine.py # 历史截断回放引擎 (15 项标准化输出)
    ├── build_sft_dataset.py               # SFT 数据集构建
    └── future_leakage_audit.py            # 未来数据泄露审计器
```

#### 既有文件集成点

| 既有文件 | 必需变更 | 验收约束 |
|:---|:---|:---|
| `market_pulse_db.py` | 在 `init_pulse_db()` / 启动就绪链路调用幂等迁移；`save_daily_sentiment()` 的 INSERT/UPSERT 写入 `lrrm_state` 与 `ipo_regime_state`；沿用现有 `DB_PATH` | 迁移异常必须返回不可就绪状态并阻止交易服务启动；旧记录 `UNKNOWN` 映射为未就绪，新记录仅保存真实计算状态；重复初始化与重复写入可用 |
| `ats/strategy/ipo_trading_center.py` | 在候选转下单边界汇集快照并调用 `GateOrchestrator`；用 `IPOTradePlan.position_pct / 100.0` 构造 `DecisionIntent.size_pct`，`stop_price` 绑定结构止损；仅把批准的 `RiskDecision.order` 送入现有路由 | 每条 ENTRY 有同一代码、行情时点、TradePlan 与 RiskDecision 因果链；WATCH/BLOCK/缺失上下文无订单副作用 |

已有 `VWAPSnapshot` 与 `RiskGate.evaluate` 字段/接口沿用当前实现；本方案不要求修改其公共签名，Gate 4 直接以快照 `date/time/code/basis` 校验身份和新鲜度。

---

<a id="ch5"></a>
## 伍、分阶段实施路线（准入驱动）

- **Stage 0: 准入清单先行，再做基础设施就绪**（先冻结第捌节未闭环指标的数据字典、来源/可用时点/缺失策略和阈值配置归属；清单审定后才实施 YAML 校验、SQLite 幂等迁移、Ollama Worker 故障/熔断验证、LanceDB 版本化 1024 维表迁移及 ATS/Qt 性能基线）
- **Stage 1: 核心门禁与算法闭环**（指标生产者 + 缺失数据失败关闭 + IPO 交易中心 ENTRY 边界接入 + 实际 RiskGate 接入 + 全输入截断回放零未来泄漏验收 + 300ms 主轮询隔离压测）
- **Stage 2: 只读 Agent 与经验沉淀**（证据可追溯 + LanceDB 截止时间过滤 + 收盘复盘候选）
- **Stage 3: 界面因果钻取与提示**（顶部流动性/温度/D1-D2 胜率/首日见顶率/次日大跌率/新股相对强度；单股 PreHeat/LiveHeat/T1Carry/VWAP/Risk/Regime/Decision；正负因子、状态、下一条件、锚点失败、迁移日志及 Regime/Carry 告警）
- **Stage 4: 离线偏好对齐与微调**（仅复核且结果成熟样本；离线评估、影子比较、人工晋级与回滚）

---

<a id="ch6"></a>
## 陆、单元测试矩阵（17 组、至少 324 项用例）

| 测试文件 | 测试重点 | 目标用例 |
|:---|:---|:---:|
| `test_lrrm_engine.py` | 4态流转、分位数计算、SHOCK 熔断 | $\ge 15$ |
| `test_ipo_regime_fsm.py` | 5态横截面计算、潮汐映射 | $\ge 20$ |
| `test_ipo_preheat_engine.py` | 变量独立计算、分位数折价、阈值对齐 | $\ge 15$ |
| `test_ipo_live_heat_engine.py` | 6大非线性函数分段、换手爬升速率、指标范围/类型拒绝 | $\ge 25$ |
| `test_t1_carry_evaluator.py` | 四项判据边界、换手率替代条件、指标缺失阻断、CAUTION 阻断 | $\ge 25$ |
| `test_listing_anchor_store.py` | 双锚击穿、锚点缺失/无效/错代码失败关闭 | $\ge 15$ |
| `test_gate_orchestrator.py` | 缺失快照及 D0 开盘/发行价缺失或非法失败关闭、D0 边界、D1+ 锚点校验、未知状态阻断、VWAP 身份/新鲜度/各期限完整性、非有限值、RiskGate 标的/信号时效/价格/止损/仓位单位/手动绕过校验 | $\ge 70$ |
| `test_historical_cutoff_replay.py`| 每个 cutoff 前向截断、naive/aware 逐项归一化、非法时间戳拒绝、未来行拒绝、15项输出契约 | $\ge 25$ |
| `test_llm_bridge.py` | Worker 隔离、超时/错误降级、Agent 信封、Schema 与本地字段校验 | $\ge 25$ |
| `test_llm_realtime_isolation.py` | 300ms 轮询零 Queue/IO 调用、Qt 事件隔离、有界排空、队列满/大消息/Worker 崩溃/服务超时/旧响应及 CPU-GPU 争用降级 | $\ge 20$ |
| `test_regression_hua_da_hai_tian.py` | 华大海天伪强结构 100% 拦截 | $\ge 5$ |
| `test_preheat_config.py` | YAML 加载、权重归一、无效配置拒绝候选 | $\ge 8$ |
| `test_market_pulse_migration.py` | 新库建表、旧库补列与历史状态 `UNKNOWN` 回填、重复迁移、状态列读写、异常回滚与启动不可就绪 | $\ge 13$ |
| `test_ipo_trading_center_gate_integration.py` | 现有下单入口门禁接入、仓位单位换算、WATCH/BLOCK 无派单 | $\ge 5$ |
| `test_sft_dpo_pipeline.py` | 标签成熟、事件分组切分、人工复核、影子晋级/回滚 | $\ge 10$ |
| `test_vector_store_migration.py` | 768→1024 版本化重嵌入、维度/哈希校验、活动表切换及回滚 | $\ge 8$ |
| `test_plan_requirement_coverage.py` | v0.2 指标清单、全样本回放、状态转换、UI/告警字段、版本化阈值与源计划验收指标的追踪和报告 | $\ge 20$ |
| **合计** | | **$\ge 324$** |

---

<a id="ch7"></a>
## 柒、不可违反的十条铁律

```
╔══════════════════════════════════════════════════════════════════╗
║  1. LLM 永远不直接控制交易执行, 只输出 Signal_Proposal         ║
║  2. 交易关键路径不等待 LLM；故障/超龄/无效时采用规则默认值     ║
║  3. future_leakage_count 必须严格为 0                           ║
║  4. 微调/训练只在非盘中时段进行                                 ║
║  5. 不引入 PyTorch/TensorFlow 等重型框架到交易主进程             ║
║  6. 所有 LLM 输出必须受 Ollama JSON Schema 强类型约束           ║
║  7. T1 Carry 的 CAUTION 严禁直接买入放行 (只能作为 WATCH)       ║
║  8. Gate 3 必须使用日内最低价核验双锚失守 (杜绝现价漏检)       ║
║  9. Gate 3/4/5 任一必需数据缺失或无效时必须失败关闭            ║
║ 10. ENTRY 必须具备有效 RR>=2.5 且真实 RiskDecision 已批准订单   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

<a id="ch8"></a>
## 捌、源计划需求追踪与实时旁路验收

本表以关联主计划《新股情绪感知与T1交易决策系统_计划书_v0.2.0.md》为需求基线。状态“已覆盖”表示 v1.1 已有可实现规格；“部分/缺失”表示仍是实施前置项，不能据当前文档宣称需求已完整闭环。引用的交易中心升级方案 1/2 是外部依赖，不代表其全部 P0/P1/P2 内容都纳入本方案。

| 源计划需求 | v1.1 审核结果 | 补齐/验收要求 |
|:---|:---|:---|
| 端到端链路：LRRM → IPO Regime → Pre-Heat → Live Heat → T+1 Carry → VWAP → TradingDecisionEngine | 主链和 Gate 0~5 已覆盖 | LLM 保持旁路建议权；最终决策由规则和 RiskGate 决定。 |
| LRRM / Regime 横截面指标与数据输入 | **部分覆盖**：现有字段主要是 20D 成交分位、涨跌比、跌停数，以及 D1 胜率、首日见顶率、创新高率和换手中位数 | 补全 60D 成交分位、融资余额变化、炸板率、高波动成交占比、指数相对强弱、新股成交额占比、主题集中度、上市供给节奏；Regime 另补 D2/D3 正收益率、D1/D2 最大回撤、跌停率、新股相对强度和收盘位置。每个字段定义来源、可用时间、缺失策略和计算窗口；缺失关键输入标记 `UNREADY` 并阻断 ENTRY。 |
| Pre-Heat、Live Heat 非线性临界点与过热/Carry 背离 | **已覆盖为算法规格** | 回归与回放仍须输出 heat、overheat、exhaustion、nonlinear_zone，并证明极端热度不会抬高 Carry 或绕过 Gate。 |
| T+1 首日九锚点、次日双锚及快速 reclaim 规则 | **部分覆盖**：锚点冻结与双锚阻断已定义，恢复条件此前缺失 | 按 Gate 3 状态条款：双锚失守先阻断；仅经有效成交量确认的快速 reclaim 可恢复至观察态，当日不得直接进入 `ENTRY_READY`。记录失守/回收时间和行情来源。 |
| VWAP 期限、OBSERVE→ARMED→ENTRY_READY→ENTERED→HOLD_T1→EXIT_READY→BLOCKED 生命周期 | VWAP 多期限门禁已覆盖；7 态转换原仅有模块名，现已补入本方案 | Gate 与下单集成验收覆盖全部合法/非法跳转；`ENTERED` 必须由成交回报确认，T+1 未解锁不可进入可卖执行。 |
| UI 状态栏、单股解释、状态迁移及告警 | **部分覆盖**：原 Stage 3 只写面板名称，字段不完整 | Stage 3 已列出市场和个股展示字段、正负因子、下一步条件、锚点失败、迁移日志，以及 Regime 变化和 T1 Carry 突变告警；须按该清单验收。 |
| Historical Cut-Off：上市前一交易日起点、竞价逐分钟、D+1/D+2/D+3 展开、首批 8 只及 8 月至今全样本 | **部分覆盖**：15 项输出和 bars 截断已写；全输入隔离及样本范围未形成验收契约 | 保留首批 8 只（华大海天、百迈科、腾信精密、信诺维、沈鼓集团、世纪数码、中塑股份、凯达重工），再扩展到 2026-08 起全部可得新股/次新股；市场/新闻/公告/申购/向量证据也按 `available_at/published_at <= cutoff` 截断，输出 D1/D2/D3 标签只在决策后解锁。 |
| 回放验收：预测分离、误入/过滤、解释覆盖、零未来泄漏与回归集通过率 | **缺失具体报表契约**：现有单测数不能代替策略效果验收 | 每次回放报告至少含 `regime_transition_accuracy`、`high_carry_vs_low_carry_spread`、`bad_t1_filter_rate`、`continuation_capture_rate`、`false_entry_rate`、`future_leakage_count`、`explanation_coverage`、`lrrm_transition_stability`、`anchor_failure_precision`、`pseudo_strength_filter_rate`、`nonlinear_false_entry_reduction`、`exhaustion_block_precision`、`regression_case_pass_rate`；硬目标：泄漏数 0、解释覆盖 100%、回归集通过率 100%。 |
| 所有阈值进入版本化 YAML 并可复现 | **部分覆盖**：当前 YAML 有 PreHeat、部分 Regime/LRRM/Carry 和 VWAP 时效配置 | 把仍写在逻辑中的 Gate 2 分段、非线性边界、锚点与 reclaim 容差、RR/仓位约束、请求超时/TTL/熔断/队列预算及回放阈值列入配置归属表；每次决策、样本和回放报告绑定配置版本与哈希。 |
| ATS 300ms 高频轮询与 Qt 事件循环不受 LLM 拖累 | **原 v1.1 过度承诺，现已收敛为可验证隔离** | v1.x 交易路径完全不读取 LLM 状态；队列、I/O、组装、验证只在旁路线程。验收要求 LLM 导致的 300ms 周期漏期数为 0，连续 30 分钟队列满/Worker 卡死/Ollama 离线/CPU-GPU 压力测试；Qt 心跳延迟相对无 LLM 基线增加不超过 5ms。快照查询 P99 ≤ 0.1ms 仅作为未来版本若申请接入快照读取时的额外门槛，当前版本不以此代替隔离验收。任一门槛失败则默认关闭 LLM，规则引擎独立启动。该验收是受控环境证据，不宣称任意操作系统负载下的数学级实时保证。 |
| 版本化维护与独立交易中心升级方案 | v1.1 自身有变更历史；交易中心方案 1/2 的完整要求不属于本方案 | v1.1 的每个版本追加修改原因、验证样本、验收结论和是否改变交易门禁；交易中心结构策略、退出引擎、L0/L1/L2 调度、图元及真实网关继续按各自计划验收，不以本文件替代。 |

**实施准入顺序**：先完成需求字段/来源与配置归属清单，再实现并跑完整回放；先通过无 LLM 基线和 LLM 最坏故障压力测试，才允许启用旁路。任何关键指标或实时门槛失败，回退到规则模式且不得影响既有交易服务启动。

---

## 变更历史

| 日期 | 版本 | 变更内容 |
|:---|:---|:---|
| 2026-09-26 | v1.0 | 初版规划方案 |
| 2026-09-26 | v1.1 | 审核全量订正闭环版：<br>1. 修复 Gate 2 CAUTION 误放行买入漏洞，降级为 WATCH；<br>2. 修复 Gate 3 仅用现价检查双锚的漏检缺陷，改用当日最低价与现价联合核验；<br>3. 修复 Gate 4 VWAP 数据缺失时静默通过缺陷，强制要求数据完整性；<br>4. 修复 Gate 5 写死 ENTRY 假通过缺陷，真实对接 TradePlan、买入区间防追高、盈亏比与风控额度；<br>5. 修复 Pre-Heat 估值分被申购分覆盖计算两遍的严重赋值错误，对齐配置阈值；<br>6. 补全 Live Heat 幽灵字段 `turnover_climb_speed` 输入来源；<br>7. 补齐华大海天四项判据完整闭环实现；<br>8. 增加 `daily_sentiment` 表 SQLite ALTER TABLE 增量补列迁移机制；<br>9. 修正 BGE-M3 向量维度为官方标准 1024 维；<br>10. 引入 Ollama 官方 Structured Outputs (JSON Schema) 解码约束，提供 TimeSandbox 真实单向回放实现。 |
| 2026-09-26 | v1.1-R1 | 复审补订：Gate 3/4 缺失数据失败关闭；Gate 5 调用 RiskGate 并阻断无效 RR/手动绕过；补全模块导入、分时指标生产者、历史回放真实数据契约、Agent 与 SFT/DPO 闭环、YAML 权重加载及 SQLite 首次建表迁移；扩展回归矩阵至至少 216 项。 |
| 2026-09-26 | v1.1-R2 | 再复审补订：统一目录与 284 项测试矩阵；为 Gate 0/1/2 缺失快照添加失败关闭；为 Gate 4/5 增加有限数值、VWAP 标的/基准/时效、信号时效、批准价格/止损及仓位单位复核；拆分 Agent payload Schema 与 Worker 信封和专属 validator；补充 LanceDB 768→1024 版本迁移、回放逐行时区规范、SQLite 状态列读写与新股下单入口集成。 |
| 2026-09-26 | v1.1-R3 | LLM/源需求复审：移除无法证明的“无锁、100% CPU/GPU 隔离”承诺；限定 300ms/Qt 关键路径与独立有界旁路、健康熔断、响应关联和资源争用验收；补齐七态迁移与快速 reclaim 约束；增加 v0.2 指标、全输入回放、UI/告警、配置和效果验收追踪矩阵；测试规划扩至至少 324 项。 |
| 2026-09-26 | v1.1-R4 | 复审一致性订正：统一为 v1.x 交易路径不读取 LLM 快照/健康状态；修正父进程控制线程与 Worker 的队列端点方向和所有权；明确 Worker sentinel 由旁路监督线程检查；保留并强调源计划尚未覆盖需求及实施前置验收。 |
| 2026-09-26 | v1.1-R5 | 终审摘要复核：Gate 3 D0 开盘价/发行价改为显式必需输入并失败关闭；Gate 4 D0 使用当日累计 VWAP、不依赖未封存锚点；SQLite 落实 `timeout=15.0` 并将历史未知状态回填为 `UNKNOWN`；明确交易中心只在 ENTRY 派单边界集成及 Stage 0 准入清单先行。 |

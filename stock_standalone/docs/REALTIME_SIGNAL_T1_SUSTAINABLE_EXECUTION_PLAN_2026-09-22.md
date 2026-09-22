# 实时数据、信号买卖点与 T+1 可持续迭代执行方案

## 0. 文档属性

- 版本：V1.0
- 日期：2026-09-22
- 范围：`instockMonitorTK`、ATS、SignalLedger、IPO/次新策略、Trading Kernel、PAPER 账户、交易指挥室。
- 当前模式：只允许回放、PAPER 和人工确认；本计划不授权真实自动下单。
- 核心目标：把“盘前发现—盘中确认—T+1 持仓—次日退出—盘后学习”形成一个可回放、可审计、可降级的闭环。

## 1. 当前基线与问题定级

2026-09-22 上午生成目录审计结果：

- 信号账本 `5025` 个状态，`TRADE=0`，但 `WATCH=3104`、`RADAR=1903`。
- `3922` 个信号首次出现于 PREMARKET，占约 78%。
- `1798` 个标的由首次正涨幅转成最新负涨幅。
- `1250` 个标的相对首次发现回落至少 3 个百分点。
- `signal_message` 上午写入 `16801` 条，存在同秒、同代码、同理由重复。
- 存在正常价格与 `price=0` 成对写入。
- “高开低走、均线压制、负涨幅”仍可能被称为“价格突破/MOMENTUM”。
- T+1 当日锁仓已有测试，但次日底台破位退出、高潮限价退出仍有专项失败。

问题按风险分级：

| 等级 | 问题 | 影响 |
| --- | --- | --- |
| P0 | 次日可卖退出链不完整 | 应卖未卖，直接影响资金安全 |
| P0 | 风险结构仍生成多头语义 | T+1 买入后当日无法纠错 |
| P0 | 数据重复、零价、跨源不一致 | 复盘样本和实时判断被污染 |
| P1 | 旧标签只增不撤销 | 已走弱标的持续占据 WATCH 前排 |
| P1 | 盘前信号直接影响盘中排序 | 集合竞价假价格长期锚定优先级 |
| P1 | 今日/昨日 VWAP 缺少统一状态机 | 无法区分回踩、破位和有效回收 |
| P2 | 缺少结果标签和分桶统计 | 参数优化容易过拟合和拍脑袋 |

## 2. 不可破坏的设计原则

1. **执行安全高于信号召回率**：宁可漏掉一个买点，也不能在 T+1 无法退出时追入走弱结构。
2. **事实、判断、动作分层**：原始行情不可改写；结构状态可更新；交易动作必须经过独立风控。
3. **退出优先**：`SELL/REDUCE > BLOCK_BUY > BUY/ADD > WATCH`。
4. **状态可逆但事实不可变**：标签可降级，首次发现记录保留；不得用新行情覆盖历史快照。
5. **跨日不继承执行资格**：昨日 WATCH/TRADE 次日一律先回到待确认，重新通过今日数据门。
6. **T+1 不吞退出意图**：当日不能卖时记录延迟退出，而不是把 SELL 改成 HOLD。
7. **单向降级**：数据异常、对账异常或版本不一致时只能降为 MONITOR_ONLY，盘中不得自动恢复执行权限。
8. **参数不盘中自学习**：盘中只应用冻结版本；优化只在盘后离线完成，经回放和 PAPER 门禁后发布。

## 3. 目标实时架构

```text
行情源/账户源
    ↓
L0 原始事件层 RawMarketEvent（只追加、不可修改）
    ↓
L1 数据质量门 DataQualityGate（新鲜度、完整度、一致性、可交易性）
    ↓
L2 特征快照 FeatureSnapshot（今日VWAP、昨日VWAP、开盘区间、结构锚点）
    ↓
L3 跨日结构状态机 CrossDayStructureFSM
    ↓
L4 策略意图 StrategyIntent（BUY/SELL/BLOCK/WATCH，不直接下单）
    ↓
L5 T+1与组合风控 ExecutionRiskGate
    ↓
L6 S4 TradePlan（固定结构事实）
    ↓
L7 S5 Directive（实时可撮合指令）
    ↓
KernelGateway → PAPER/CONFIRM
    ↓
成交、拒绝、延迟退出、结果标签与盘后复盘
```

任何上层不得绕过下层直接访问执行适配器。

## 4. 统一数据契约

### 4.1 RawMarketEvent

每条行情事件至少包含：

```text
event_id, code, market, trade_date, event_time, receive_time,
source, sequence_no, last_price, open, high, low, prev_close,
volume_delta, volume_total, amount_delta, amount_total,
bid1, ask1, trading_status
```

规则：

- `event_id = source + trade_date + code + sequence_no`，用于幂等。
- 原始事件只追加，不使用修正后的数值覆盖原记录。
- `last_price <= 0`、交易日不符、时间倒流的事件进入隔离区，不进入特征计算。
- 同一代码同一时刻多源行情并存，必须保留来源，不提前合并成无法追溯的平均值。

### 4.2 FeatureSnapshot

```text
snapshot_id, code, trade_date, feature_time, source_event_id,
price, today_vwap, yesterday_vwap, vwap_2d, vwap_5d,
open_price, opening_range_high, opening_range_low,
day_high, day_low, yesterday_high, yesterday_low,
base_support, structural_stop, structural_target,
above_today_vwap_ratio, late_above_vwap_ratio,
gap_pct, pullback_from_high_pct, volume_ratio_normalized,
quality_scores, feature_version
```

`snapshot_id` 必须随 TradePlan、Directive、订单和结果记录全链传递。

### 4.3 质量评分

每个快照输出：

- `freshness_score`：行情延迟、时间倒流、交易日一致性；
- `completeness_score`：价格、成交量、VWAP、昨日锚点、60F/日线字段完整度；
- `consistency_score`：实时源、TDX 和账户源的价格/数量差异；
- `tradability_score`：停牌、涨跌停、盘口、最小交易单位、可卖数量；
- `overall_quality = min(四项)`，关键维度不采用平均分掩盖故障。

建议门槛：

- `overall_quality < 80`：不得生成 S4/S5；
- 数据延迟超过 3 秒：禁止新买；
- 缺少今日 VWAP 或昨日 VWAP：跨日策略只能 WATCH；
- 账户持仓不一致：该代码 BUY/SELL 全部 BLOCK，等待对账。

## 5. 跨日 VWAP 结构状态机

### 5.1 状态定义

| 状态 | 含义 | 买入权限 |
| --- | --- | --- |
| `D0_BELOW_VWAP_ACCUMULATION` | 昨日在 VWAP 下缩量蓄势、底台未破 | 无 |
| `D0_LATE_NO_REVERSAL` | 昨日尾盘仍未站稳 VWAP | 无 |
| `D0_LATE_BREAKOUT` | 昨日尾盘放量站稳 VWAP/箱体上沿 | 次日待确认 |
| `D1_GAP_UP_PROBE` | 次日高开试探，开盘区间尚未完成 | 无 |
| `D1_BREAKOUT_HOLD` | 站稳关键锚点并回踩不破 | 可申请 S4 |
| `D1_PULLBACK_RECLAIM` | 先跌破今日 VWAP，回踩昨日 VWAP后重新收复 | 二次确认后可申请 S4 |
| `D1_SPIKE_FADE` | 高开冲高回落、跌回开盘价或今日 VWAP | 禁止新买 |
| `D1_TEST_YDAY_VWAP` | 今日 VWAP 下、正在测试昨日 VWAP | WATCH/昨仓防守 |
| `D1_DOUBLE_VWAP_BREAK` | 今日与昨日 VWAP 同时跌破 | BUY BLOCK；可卖仓退出 |
| `D1_FAILED_BREAKOUT` | 突破失败并跌破结构失效位 | 退出/延迟退出 |

### 5.2 状态判定细节

`D1_TEST_YDAY_VWAP` 最小条件：

```text
price < today_vwap × 0.998
and price <= yesterday_vwap × 1.008
```

`D1_DOUBLE_VWAP_BREAK` 最小条件：

```text
price < today_vwap × 0.998
and price < yesterday_vwap × 0.998
```

`D1_SPIKE_FADE` 建议条件：

```text
gap_pct >= 1%
and pullback_from_high_pct >= max(2%, 0.6 × gap_pct)
and (price < open_price or price < today_vwap)
```

`D1_BREAKOUT_HOLD` 不允许用单 Tick 确认，必须同时满足：

- 连续 5 个交易分钟位于关键锚点之上；
- 回踩最低价未有效跌破锚点；
- 归一化量比在合理区间，既不萎缩也不过热；
- 当前结构性 RR 仍不低于 2.5；
- 未触发高开冲高回落、T+1 追高或市场风险阻断。

### 5.3 防抖

- 进入风险态使用较短确认：连续 2~3 个有效 Bar。
- 从风险态恢复到可买态使用较长确认：至少 5 个交易分钟。
- 同一状态最短驻留 60 秒；仅结构止损、停牌、涨跌停等硬事件可立即跳转。
- 状态转移必须记录 `from_state/to_state/reason/snapshot_id`。

## 6. 信号生命周期与撤销机制

### 6.1 生命周期

```text
DISCOVERED → RADAR → WATCH → S4_ACTIONABLE → S5_EXECUTABLE
                    ↘ BLOCKED / EXPIRED / INVALIDATED
S5_EXECUTABLE → SUBMITTED → PARTIAL/FILLED/REJECTED/CANCELLED
```

禁止“只升不降”。每次行情更新都必须执行：

1. 更新最新价格和结构状态；
2. 先计算失效条件；
3. 撤销过期标签和加分；
4. 再计算新的候选资格；
5. 风险态未解除时不得自动晋级。

### 6.2 标签语义

标签必须属于以下一种类型：

- `FACT`：如高开幅度、VWAP 位置；
- `STRUCTURE`：如平底、通道突破；
- `RISK`：如冲高回落、双 VWAP 破位；
- `ACTION`：如等待确认、禁止追高、可减仓；
- `EXECUTION`：如可卖数量、T+1 延迟退出。

不得用“价格突破”同时表示风险和买入。`MOMENTUM` 必须满足当前价格在今日 VWAP 上，并且不存在高开低走/冲高回落否决。

### 6.3 标签失效

以下任一发生，撤销“极早起爆、均线强持有、完美双结构、上升通道、主升”等买入标签：

- 跌破今日 VWAP并测试昨日 VWAP；
- 首次发现后回撤超过 3 个百分点且最新涨幅为负；
- 高开后跌破开盘价并持续 3 分钟；
- 结构止损失效；
- 快照过期或字段质量不足。

历史标签保留在 `state_history`，不得继续参与当前优先级计算。

## 7. T+1 分批库存与执行状态机

### 7.1 持仓事实模型

每笔成交形成独立 lot：

```text
lot_id, code, buy_trade_date, buy_time, buy_price,
original_qty, remaining_qty, sellable_qty,
frozen_qty, source_order_id, strategy_version
```

聚合持仓仅用于显示：

```text
total_qty = Σ remaining_qty
sellable_qty = 柜台/纸盘返回的可卖数量
today_bought_qty = total_qty - sellable_qty - frozen_qty
```

柜台或 PAPER 账户是可卖数量事实源；策略不得自行假定今天已解锁。

### 7.2 退出状态机

```text
EXIT_INTENT_CREATED
    ├─ sellable_qty > 0 → NEXT_DAY_EXIT_READY
    └─ sellable_qty = 0 → EXIT_DEFERRED_T1

NEXT_DAY_EXIT_READY → SELL_SUBMITTED
SELL_SUBMITTED → PARTIAL / FILLED / REJECTED / CANCELLED
PARTIAL → SELL_SUBMITTED 或 EXIT_REMAINDER_PENDING
```

`EXIT_DEFERRED_T1` 必须：

- 保留原始退出原因、触发价和结构止损；
- 阻断该代码所有 BUY/ADD；
- 写入次日优先退出队列；
- 重启后恢复；
- 次日用实时价格重新评估委托方式，但不得静默取消退出意图。

### 7.3 混合批次

同时存在昨仓和今仓时：

- 只允许卖出 `sellable_qty`；
- 今仓继续锁定；
- 退出原因作用于全仓，但执行结果按 lot 分配；
- 禁止因为今仓不可卖而阻断昨仓退出。

## 8. 买点严格门禁

买入必须依次通过：

1. 数据质量门；
2. 跨日结构门；
3. T+1 追高风险门；
4. 当前价格与买区门；
5. 固定结构 RR 门；
6. 市场潮汐与组合仓位门；
7. EXIT > BUY 冲突门；
8. 快照新鲜度与幂等门。

建议统一表达：

```text
BUY_ELIGIBLE =
    quality_ok
    and state in {D1_BREAKOUT_HOLD, D1_PULLBACK_RECLAIM}
    and price >= today_vwap
    and not spike_fade
    and not t1_chase_risk
    and rr_now >= 2.5
    and price in buy_zone
    and no_exit_intent
    and risk_budget_available
```

直接 BLOCK：

- `D1_TEST_YDAY_VWAP`；
- `D1_DOUBLE_VWAP_BREAK`；
- `D1_SPIKE_FADE`；
- `D1_FAILED_BREAKOUT`；
- 高开幅度过大且首次确认发生在冲高后；
- 任何账户、快照或版本对账异常。

## 9. 卖点与昨仓处理

卖出优先级：

1. 结构硬止损；
2. 双 VWAP 破位；
3. 高开冲高回落且跌破开盘价；
4. 高潮天量、预设限价退出；
5. 达到目标后的分批止盈；
6. 时间止损和尾盘风险收缩。

昨仓建议动作：

- `D1_SPIKE_FADE`：先减仓，跌破今日 VWAP后扩大减仓；
- `D1_TEST_YDAY_VWAP`：若昨日 VWAP守住可保留观察仓，禁止新增；
- `D1_DOUBLE_VWAP_BREAK`：执行结构退出；
- 跌停无法成交：保留订单与退出意图，持续更新可成交状态，不伪造成交。

今仓不可卖时：生成 `EXIT_DEFERRED_T1` 和风险告警，绝不加仓摊低成本。

## 10. 去重、幂等与数据库治理

### 10.1 信号幂等键

```text
signal_key = trade_date + code + strategy_id + structure_state + action
```

同一 key：

- 60 秒内只更新最新快照，不新增行；
- 结构状态未变化且价格变化小于 0.5%，10 分钟内不新增；
- 风险升级、动作变化或结构失效可立即生成新版本。

### 10.2 订单幂等键

```text
order_request_id = trade_plan_id + action + lot_scope + directive_version
```

任何进程重启、重复点击或重复回调均不得生成第二笔订单。

### 10.3 数据库约束

建议增加：

- `signal_message(signal_key, version)` 唯一约束；
- `live_signal_history(event_hash)` 唯一约束；
- `price > 0` 写入检查；
- `created_date/timestamp/code/signal_type` 组合索引；
- 原始历史、当前快照和统计汇总分表，避免同表承担三种职责。

存量重复数据不立即物理删除；先生成去重视图和修复报告，经确认后再归档。

## 11. 实时处理时序

### 08:45—09:15

- 加载上一交易日结构、持仓 lot、延迟退出队列；
- 对账 PAPER/账户可卖数量；
- 校验构建指纹、策略版本、参数版本；
- 清空隔夜 S5，S4 只作为历史上下文恢复。

### 09:15—09:25

- 竞价数据仅生成 FACT/RISK，不直接生成 BUY；
- 竞价价格不得写成正式首次成交价；
- 09:25 后校验最终竞价撮合价格。

### 09:30—09:45

- 建立开盘区间；
- 量能归一化；
- 高开标的默认处于 `D1_GAP_UP_PROBE`；
- 未完成 5 分钟确认不得进入 S4。

### 09:45—11:30

- 正常结构确认；
- 每个 Tick 更新风险状态，Bar 完成时才允许买入态升级；
- 风险态即时阻断买入。

### 13:00—14:30

- 重新校验午间数据连续性；
- 处理 VWAP 回收、二次确认和昨仓防守；
- 午休不得计入 TTL。

### 14:30—15:00

- 收紧新开仓门槛；
- 未确认突破不隔夜下注；
- 汇总延迟退出和次日风险；
- 归档过期 S4/S5，不静默删除。

### 15:00 后

- 账户全量对账；
- 生成特征—决策—订单—成交—结果宽表；
- 只在盘后运行参数评估。

## 12. 可持续评价体系

### 12.1 每条信号结果标签

- MFE：触发后最大有利波动；
- MAE：触发后最大不利波动；
- 5/15/30/60 分钟收益；
- 收盘收益、T+1 开盘/最高/收盘收益；
- 首次触达止损/目标的交易分钟；
- 是否因 T+1 无法退出；
- 理论动作与实际成交差异；
- 滑点、部分成交、拒单原因。

### 12.2 必须分桶

- 昨日 VWAP 上/下；
- 尾盘变盘/未变盘；
- 次日低开/平开/高开；
- 高开延续/冲高回落/回踩再起；
- 昨仓可卖/今仓锁定/混合批次；
- 市场潮汐状态；
- 时段；
- 策略和参数版本。

### 12.3 核心指标

- S4→S5 转化率；
- S5 成交率、拒绝率、过期率；
- BUY 后 30 分钟 MAE；
- T+1 延迟退出损失；
- 双 VWAP 破位后继续下跌概率；
- 被 BLOCK 的机会成本；
- 重复信号率和零价污染率；
- 状态抖动次数；
- 回放与 PAPER 一致率。

不能只优化胜率。发布判断至少同时看期望收益、盈亏比、最大回撤、连续亏损、样本量和 T+1 尾部风险。

## 13. 参数迭代制度

1. 参数文件带 `strategy_version/feature_version/parameter_version`。
2. 每周只选择一个变量组作为挑战者，例如 VWAP 容差或确认分钟数。
3. 使用滚动窗口 walk-forward：训练区选参数，后续验证区只评估。
4. 与当前冠军版本对照，不以单日结果替换生产版本。
5. 通过顺序：离线回放 → 历史事件重放 → PAPER 影子 → PAPER 主版本 → CONFIRM。
6. 任一阶段出现账户差异、重复订单或退出丢失，挑战者立即淘汰。
7. 参数发布只允许盘后完成，生成差异报告和回滚包。

## 14. 实施工作包

### WP0：冻结基线与可重复回放（0.5—1 天）

改动范围：回放工具、配置、测试夹具。

任务：

- 复制 2026-09-22 上午日志、信号库和必要行情为只读夹具；
- 生成数据清单、哈希和字段字典；
- 固化十个正样本、十个冲高回落样本、十个双 VWAP 破位样本；
- 保留蓝色光标典型路径。

验收：同一版本重复回放，状态序列和指令完全一致。

### WP1：数据质量与去重（1—2 天，P0）

主要入口：`trading_logger.py`、`signal_message_queue.py`、行情接入层。

任务：

- 拒绝零价、跨日、倒序和过期事件；
- 建立 signal_key/event_hash；
- 数据库唯一约束与索引迁移；
- 多进程写入冲突测试；
- 输出重复率和隔离事件日报。

验收：零价污染率为 0；相同事件重复运行不新增记录；合法风险升级仍能生成新版本。

### WP2：跨日 VWAP 状态机（2—3 天，P0）

主要入口：新增 `ats/cross_day_vwap_fsm.py`，接入 `stock_live_strategy.py` 和 `ats/signal_ledger.py`。

任务：

- 实现十个结构状态和防抖；
- 输出结构原因码；
- 所有多头信号在输出前查询 FSM；
- 风险状态撤销旧标签、加分与可执行资格。

验收：冲高回落和双 VWAP 破位样本零 BUY；有效回收样本在确认前零 BUY、确认后只生成一次 S4。

### WP3：T+1 lot 与退出链（2—4 天，P0）

主要入口：PAPER adapter、Kernel state、IPOTradingCenter、Gateway。

任务：

- 分批 lot、sellable_qty 与 frozen_qty；
- `EXIT_DEFERRED_T1` 持久化；
- 次日恢复、部分成交、拒单和跌停重试；
- 修复底台破位与高潮限价退出失败。

验收：昨仓、今仓、混合仓、重启、部分成交全部通过；退出意图不丢失；卖出数量永不超过可卖量。

### WP4：S4/S5统一门禁（1—2 天，P0/P1）

任务：

- 固定 TradePlan 结构锚点；
- S5 每次生成前重取快照；
- EXIT > BUY；
- 统一拒绝码和 UI 原因；
- 15 交易分钟 TTL。

验收：任何 BLOCK 原因均可追溯；结构锚点不随 Tick 漂移；重复提交只有一个订单结果。

### WP5：复盘宽表与日报（2 天，P1）

任务：

- 结果标签器；
- 分桶指标；
- 信号漏斗、T+1 延迟损失和误报 TopN；
- 每日输出冠军/挑战者对照报告。

验收：任一买卖点可从结果追溯到原始事件、快照、状态、计划、指令和订单。

### WP6：界面可解释性（1—2 天，P1）

卡片固定显示：

```text
昨日结构 → 今日状态 → 今日/昨日VWAP位置 → T+1可卖量
当前动作 → 阻断原因 → 结构止损 → 目标 → RR → TTL
```

颜色仅表达当前状态，历史强标签不得覆盖当前风险色。

### WP7：灰度与发布（至少 5 个交易日，P1）

- 第 1—2 日：影子运行，只记录不改变现有 PAPER；
- 第 3—4 日：新状态机驱动 PAPER，旧策略并行对照；
- 第 5 日以后：达到门槛后成为 PAPER 主版本；
- CONFIRM 需另行评审；LIVE_AUTO 不在本计划内。

## 15. 测试矩阵

至少覆盖：

1. 昨日 VWAP 下蓄势，尾盘未变盘，次日高开冲高回落；
2. 昨日尾盘突破，次日回踩今日 VWAP后继续上行；
3. 今日 VWAP 下回踩昨日 VWAP并收复；
4. 今日与昨日 VWAP 同时破位；
5. 当日买入触发止损但 T+1 不可卖；
6. 昨仓可卖、今仓不可卖的混合批次；
7. 高潮限价退出；
8. 跌停无法成交；
9. 部分成交、撤单失败、重复回报；
10. 午休 TTL、跨日重启、行情断线恢复；
11. 零价、过期、倒序、重复行情；
12. 多进程同时写入同一信号；
13. EXIT 与 BUY 同周期冲突；
14. 重点关注/真龙处于双 VWAP 破位；
15. 参数版本和构建指纹不一致。

重点关注和真龙可以保留展示，但不得绕过 T+1、数据质量和结构硬止损。

## 16. 发布门禁与停止条件

发布必须同时满足：

- P0 测试全部通过；
- 零价信号为 0；
- 重复信号率低于 1%；
- 回放确定性 100%；
- 账户/持仓/可卖量对账差异为 0；
- 退出意图丢失为 0；
- 同一幂等键多订单为 0；
- 冲高回落与双 VWAP 破位产生 BUY 为 0；
- 构建指纹与 Git 提交一致；
- PAPER 连续运行达到约定观察期。

出现以下任一情况立即 MONITOR_ONLY：

- 行情过期或时钟倒流；
- 柜台与内核持仓不一致；
- sellable_qty 不可信；
- 重复订单；
- 风控拒绝后仍成交；
- 状态机版本与策略版本不一致；
- 审计写入失败。

## 17. 每日运营流程

### 盘前

- 对账、版本检查、延迟退出恢复、数据源健康检查。

### 盘中

- 只观察预设实时指标；不临时改参数；异常只降级。

### 午间

- 检查信号漏斗、重复率、零价率、退出队列和账户差异。

### 盘后

- 生成日报；复核 Top 误报和漏报；保存回放夹具；提出参数假设。

### 周度

- 运行 walk-forward；比较冠军与挑战者；批准或拒绝下周版本。

## 18. 下一步立即执行顺序

1. 固化 2026-09-22 上午数据回放夹具。
2. 完成 WP1 数据幂等与数据库去重，不修改历史原始数据。
3. 将当前内联 VWAP 否决提取为独立 `CrossDayVWAPFSM`。
4. 修复两项 T+1 次日退出失败测试。
5. 增加蓝色光标正反两条固定回放。
6. 完成 WP0—WP4 后运行核心全量回归。
7. 启动至少两个交易日影子观察，比较修改前后误报、漏报与 T+1 风险。

在第 4 项完成以前，新增买点、放宽门槛和真实自动执行均暂停。

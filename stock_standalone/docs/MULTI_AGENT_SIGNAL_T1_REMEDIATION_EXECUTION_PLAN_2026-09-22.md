# 多 Agent 信号账本、实时结构与 T+1 修复执行计划

## 0. 执行结论与当前落地状态

> **当前总体状态**：【核心 P0 修复已完成，完整计划仍有未落地项】（不能标记为“全部完成”）

### ✅ 已完成项
- **Task 026**：消息幂等、零价拦截、历史重复兼容与数据库原子保护；
- **Task 029**：T+1 交易中心退出链与 SSOT 安全（Available fallback 清除与可卖隔离）；
- **Task 030**：账本弱化、VWAP 破位、正转负治理、峰值回撤检测与软降级；
- **部分 Task 025**：生命周期契约与核心状态迁移模块；
- **部分 Task 027**：会话阶段门禁核心模块；
- **测试与回归**：Batch 1 / 核心回归 157 项通过，T+1 专项 25 项全绿。

### ⏳ 尚未完整落地项（后续推进）
- **Task 027 剩余项**：`CandidateCache`、单独的 `PREMARKET seed` 账本隔离、连续帧确认机制；
- **Task 028**：Kernel 原生 `total_qty / sellable_qty / today_buy_qty / lots` 事实源；
- **Task 031**：UI、TDX、ATS、favorite 统一由 `LedgerUpdateService` 单一入口驱动；
- **Task 032**：完整快照 v2、旧快照平滑迁移与 fail-closed 防御；
- **Task 033**：统一退出仲裁器，确保 `EXIT > BUY` 绝对阻断；
- **Task 034**：冻结上午数据回放、重复率/零价/对账/构建指纹发布门禁。

---

## 1. 计划核心背景与修复目标

| 事实 | 根因 | 必须达到的目标 |
| --- | --- | --- |
| `5025` 个账本状态，`TRADE=0` | 候选直接入账；TRADE未接成交事实 | Candidate 与 Ledger 分离；TRADE只由成交/持仓SSOT驱动 |
| `PREMARKET=3922` | 非交易会话缺门禁；静态数据当实时 | PREOPEN只做seed，不能算有效首次信号 |
| `1798` 个正转负 | 没有峰值、回撤和弱化状态 | 统一 `WEAKENED/INVALIDATED` 状态与原因码 |
| `1250` 个回撤≥3% | 只检查绝对偏离，未检查峰值回撤 | 峰值回撤必须触发软降级或硬失效 |
| `signal_message=16801` 且重复 | 多入口写入、无事件幂等键 | 同一事件只保留一个版本，状态变化才生成新版本 |
| `price=0` 成对写入 | 消息缺少价格仍持久化 | 零价进入隔离表，不进入实时历史 |
| 风险理由仍叫 MOMENTUM | 规则只看历史阈值，不复核当前结构 | `RISK` 与 `ACTION` 语义优先于旧 MOMENTUM |
| T+1退出专项失败 | SSOT同步抹掉测试/本地持仓；内核无 sellable_qty | Kernel提供可卖事实，交易中心只消费SSOT |

审计进一步确认：`signal_message` 按业务唯一键只有约 257 组，约 16,544 行为冗余；`live_signal_history` 有 1,845 条 `price<=0`，其中约 1,184 组同时存在零价和正常价。根因是 `SignalMessageQueue.push()` 自己写一次实时历史，`_async_alert_worker` 随后又写一次；多数消息没有 `extra.price`。因此“过滤零价”只是止血，Task 026 必须移除双写并采用数据库原子 UPSERT。

## 2. 多 Agent 组织与文件所有权

### 阶段 A：只读审计（已完成）

- Agent A：信号写入、去重、零价污染。
- Agent B：SignalLedger生命周期、PREMARKET、旧标签、快照和排序。
- Agent C：T+1持仓事实源、退出链和专项失败。
- 主 Agent：冻结接口、合并结论、编排实施。

审计 Agent 不得修改业务文件；只提交报告和建议任务。

### 阶段 B：实现 DAG

| Task | Agent | 独占文件范围 | 依赖 | 交付 |
| --- | --- | --- | --- | --- |
| 025 | 主 Agent | `ats/signal_lifecycle.py`、契约测试 | 无 | 生命周期事件/状态契约 |
| 026 | Agent 1 | `signal_message_queue.py`、`trading_logger.py`、迁移脚本、对应测试 | 025接口冻结 | 幂等、零价隔离、数据库索引 |
| 027 | Agent 2 | `ats/session_clock.py`、`ats/ledger_candidate_cache.py`、会话测试 | 025接口冻结 | PREOPEN/LUNCH/CLOSED/STALE门禁 |
| 028 | Agent 3 | `trading_kernel/*`、`ats/unified_paper_account.py`、内核测试 | 无 | total/sellable/today_buy事实源 |
| 029 | Agent 4 | `ats/strategy/ipo_trading_center.py`、T+1测试 | 028 | 退出链、同步保护、数量上限 |
| 030 | Agent 1 | `ats/signal_ledger.py`、账本测试 | 025、027 | 弱化/失效/旧标签撤销/稳定排序 |
| 031 | Agent 2 | `ats/ui/main_window.py`、`ats/universe_manager.py`、展示测试 | 025、030 | 单一扫描入口、候选与账本投影 |
| 032 | Agent 3 | `ats/session_snapshot.py`、迁移测试 | 025、030 | v2快照、跨日origin/today锚点 |
| 033 | 主 Agent | `ats/proactive_exit_engine.py`、集成测试 | 028、029 | 唯一退出仲裁与EXIT>BUY |
| 034 | 主 Agent | 回放工具、全量测试、docs | 026-033 | 冻结回放与发布报告 |

同一阶段不得让两个 Agent 修改同一业务文件。若必须交叉修改，先停并由主 Agent 建立接口补丁。

## 3. Task 025：冻结生命周期契约（P0）

新建纯领域模块，定义：

```text
DISCOVERED → QUALIFYING → WATCH → ARMED → TRADE
                         ↘ WEAKENED → INVALIDATED → EXPIRED
```

事件至少包含：

```text
SESSION_OPEN, QUOTE, STRUCTURE_GAINED, STRUCTURE_LOST,
VWAP_BREAK, VWAP_RECLAIM, PEAK_DRAWDOWN, FILL,
POSITION_SYNC, DAY_ROLLOVER, DATA_STALE, EXPIRE
```

规则：

- `tier` 是投影视图，不再等同于领域状态。
- favorite/dragon只能影响排序，不能绕过双 VWAP 破位、T+1或数据质量硬门。
- 同一 Tick 不允许 `WEAKENED → WATCH` 复活。
- 每次迁移输出 `revision/from/to/event/reason/snapshot_id`。

验收：状态转移表参数化测试、非法迁移拒绝、同输入确定性 100%。

## 4. Task 026：消息幂等与零价治理（P0）

统一写入前生成：

```text
event_hash = sha256(trade_date|code|signal_type|action|structure_state|snapshot_id)
signal_key = trade_date|code|strategy_id|structure_state|action
```

规则：

- 同一 `event_hash` 只写一次。
- 60 秒内同 key 只更新快照，不插入新行。
- 10 分钟内价格变化小于 0.5% 不新增；风险升级或状态变化可新增版本。
- `price<=0` 进入 `invalid_signal_events` 或隔离日志，不写 `live_signal_history`。
- `price=0` 不能作为“未知价格”继续排序或执行。

数据库：增加唯一索引、事件哈希索引和迁移前重复审计；历史原始数据先只读归档，不直接删除。

测试：双进程同事件、同秒重复、正常/零价成对、价格显著变化、风险升级、重启恢复。

验收：零价实时记录为 0；同事件重复率为 0；状态升级不被错误去重。

## 5. Task 027：交易会话与候选缓存（P0）

拆分会话：

```text
PREOPEN 08:45-09:15
AUCTION 09:15-09:25
OPEN_CONFIRM 09:30-09:45
MORNING 09:45-11:30
LUNCH 11:30-13:00
AFTERNOON 13:00-14:30
CLOSE 14:30-15:00
CLOSED 其他
```

规则：

- PREOPEN/AUCTION只允许 `seed`，不得触发 `极早起爆` 的+25/+120。
- 09:30首个新鲜 Tick 建立 `session_anchor`，昨日恢复的 `origin_*` 不计入今日首次。
- MA20偏离候选进入 CandidateCache，TTL 60—180 秒；连续 N 帧或结构事件确认后才创建 Ledger Entry。
- 午休、盘后、周末静态数据不得生成今日有效首次信号。

验收：盘前账本不膨胀；PREMARKET单列seed_count；连续回放数量稳定。

## 6. Task 028：Kernel T+1事实源（P0）

内核读模型新增：

```text
total_qty, sellable_qty, today_buy_qty, frozen_qty,
as_of, trading_day, lots[{lot_id,buy_trade_date,remaining_qty,sellable_qty}]
```

原则：

- `sellable_qty` 只能来自 Kernel/PAPER/柜台事实，不由交易中心推算。
- 缺字段、负值、超过 total、交易日不一致、快照陈旧，均为 `EXECUTION_BLOCKED`。
- T日新仓 `sellable_qty=0`；T+1按 lot 日期解锁。
- 空 SSOT 不得静默覆盖非空本地持仓，必须生成 reconciliation mismatch。

验收：T日、T+1、昨仓+今仓混合、部分成交、重启、跨日恢复和缺字段全部通过。

## 7. Task 029：交易中心退出链修复（P0）

修复要点：

- `_sync_from_unified_paper_account` 只消费 `sellable_qty`，移除 `available=0 → shares` fallback。
- SSOT空快照不清空非空本地仓，转为 `RECONCILING/EXECUTION_BLOCKED`。
- 所有退出指令数量严格为 `min(strategy_qty, sellable_qty)`。
- 底台破位、高潮限价、主动防守统一调用 `build_exit_directive`。
- T日生成 `EXIT_INTENT_BLOCKED_T1`（可展示、不可执行）；T+1生成 `ACTIONABLE_EXIT`。
- `EXIT > BUY` 同代码同周期只保留一个最终退出。

当前两个失败测试必须保留为回归，并改为隔离 SSOT/mock，不使用持久单例覆盖手工仓位。

验收：

- 当前两项专项通过；
- T日卖出成交 0；
- T+1退出召回率 100%；
- oversell=0；
- 重复 EXIT=0；
- 高潮限价价等于 preset；
- 混合批次只卖昨仓。

## 8. Task 030：账本弱化、失效和重排（P0）

`SignalEntry`增加：

```text
peak_price, peak_pct, mfe, drawdown_from_peak,
positive_to_negative, weak_since, last_fresh_ts,
invalidation_reason, reclaim_count, state_revision
```

统一 guard 顺序：

```text
数据质量 → 硬失效 → 软降级 → 恢复确认 → 晋级
```

硬/软规则：

- 正转负：至少 `WEAKENED`，撤销起爆/强持有语义。
- 峰值回撤≥3%：记录 drawdown；结合 VWAP破位升级 `INVALIDATED`。
- 今日 VWAP下回踩昨日 VWAP：禁止新买，降RADAR。
- 双 VWAP破位：`INVALIDATED/INACTIVE`。
- 恢复必须满足 VWAP收复、连续确认帧和冷却时间。
- `_compute_specialty_score`改为纯函数，不能修改 tag/boost。
- priority 使用 freshness/risk penalty；失效项不能靠旧+120复活。

验收：冻结上午回放中的 1798/1250 全部有明确分类和原因；失效 Tick不会被量比拉回 WATCH。

## 9. Task 031/032：单一扫描与快照兼容（P1）

扫描入口统一为一个 LedgerUpdateService；UI、TDX、ATS、favorite 均提交命令，不直接写 entries。

快照 v2必须包含：

```text
schema_version, trading_date, origin_anchor, today_anchor,
lifecycle_state, state_revision, state_history,
peak/drawdown/weak fields, strategy/feature/parameter_version
```

旧快照迁移原则：缺字段保守为 `STALE/RADAR`，绝不自动 WATCH；损坏、未来版本、跨日错误全部 fail closed。

UniverseManager只展示当前状态和当前 transition_reason；favorite独立 pin，不得把 INACTIVE 强行改成 WATCH。

## 10. Task 033：唯一退出仲裁（P0）

将底台、高潮和主动防守合并为单一退出协调器，优先级：

```text
HARD_STOP/DOUBLE_VWAP_BREAK
  > CLIMAX_LIMIT
  > REDUCE
  > HOLD
```

同代码同周期只输出一个最终 EXIT；退出决议生成后，任何 BUY/ADD都必须物理剥离并写明 `EXIT_SUPERSEDES_BUY`。

## 11. Task 034：冻结回放和发布门禁

冻结 2026-09-22 上午目录：

```text
D:\JohnsonProgram\instockMonitorTK\logs\signal_snapshots
D:\JohnsonProgram\instockMonitorTK\logs\trading_kernel_trace.jsonl
D:\JohnsonProgram\instockMonitorTK\logs\paper_account_state.json
D:\JohnsonProgram\instockMonitorTK\signal_strategy.db
D:\JohnsonProgram\instockMonitorTK\trading_signals.db
```

生成只读夹具哈希，不修改原始目录。

发布必须满足：

- P0测试全绿；
- 零价实时记录=0；
- 重复事件率<1%；
- 冲高回落/双VWAP破位 BUY=0；
- 当日卖出成交=0；
- T+1次日退出召回率=100%；
- oversell=0、重复订单=0；
- 对账差异=0；
- 回放同输入结果一致；
- 构建指纹与提交一致。

任一失败立即 `MONITOR_ONLY + EXECUTION_BLOCKED`，不得盘中自动恢复。

## 12. Agent Hub 任务书生成规范

每个任务文件必须包含：

- Task-ID、Owner、Priority、Risk；
- Depends-On；
- Files Allowed / Files Forbidden；
- 明确输入输出契约；
- Definition of Done；
- 精确测试命令；
- 回滚步骤；
- `agent_report.json` 必须记录 diff_files、测试结果、风险点。

禁止 Agent：

- 修改真实交易开关、券商凭据或 LIVE_AUTO；
- 越界修改其他 Agent 的文件；
- 修改历史数据库原始记录；
- 关闭测试或放宽 T+1门禁；
- 未经 checkpoint-review 自动合并。

## 13. 推荐批次

### Batch 1（可并行，接口冻结后）

- 026 消息幂等与零价；
- 027 会话与候选缓存；
- 028 Kernel T+1事实源。

### Batch 2（Batch 1 通过后）

- 029 交易中心退出链；
- 030 账本弱化失效；
- 032 快照迁移。

### Batch 3（集成）

- 031 单一扫描与 UI投影；
- 033 唯一退出仲裁；
- 034 冻结回放、全量回归、P checkpoint。

## 14. 交付与回滚

每个 P0 任务必须单独提交检查点，不允许混合提交。发布前保留：

```text
代码提交号
参数快照
构建指纹
回放夹具哈希
PAPER账户快照
对账报告
测试证据
```

回滚以最后一个全绿 P checkpoint 为准；数据库只追加，重复和隔离记录通过视图/归档处理，不执行不可逆清理。

## 15. 立即执行命令顺序

```text
1. validate Agent Hub 与当前工作区边界
2. 冻结上午目录为只读回放夹具
3. 主 Agent 提交 signal_lifecycle 契约
4. 并行运行 Batch 1
5. task_review：逐任务审查范围与测试
6. P checkpoint review：只在 Batch 1 全部通过后执行
7. Batch 2 → Batch 3
8. 全量回归 + 两个交易日影子运行
9. 只允许 PAPER/CONFIRM 评审，不开启 LIVE_AUTO
```

本计划的完成标准不是“信号变少”，而是：每一条当前信号都有新鲜事实、明确结构状态、可解释动作、T+1可执行数量、唯一审计链和可复现结果。

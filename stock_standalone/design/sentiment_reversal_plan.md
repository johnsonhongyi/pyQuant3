# 情绪翻转跟单系统 - 全面优化改造方案

> 目标：让系统在大跌次日集合竞价阶段自动识别“昨日恐慌 -> 今日修复/翻转”的高质量机会，并通过现有 TradingKernel 的 CONFIRM 人机协同模式完成 09:25-09:30 的低侵入开仓决策。
>
> 边界：本方案只定义设计与实施计划。正式实施时必须先走回测和 PAPER/CONFIRM 验证，不直接接入 LIVE_AUTO。

---

## 一、现有系统能力诊断

### 已具备能力

| 能力 | 现有模块 | 当前状态 |
|------|----------|----------|
| 竞价个股异动捕捉 | `BiddingMomentumDetector` | 已具备，含 `_global_snap_cache`、`active_sectors`、`get_active_sectors()` |
| 板块热力聚合与龙头识别 | `bidding_momentum_detector._aggregate_sectors()` + `SectorFocusController.inject_from_detector()` | 已具备，板块图可注入 |
| 盘中跟单与回踩买点 | `SectorFocusEngine` / `IntradayPullbackDetector` | 已具备，主要面向盘中 |
| 交易内核与风控 | `TradingKernelService.evaluate_decision_item()` + `risk_gate.evaluate()` | 已具备 |
| 人机协同确认 | `ConfirmExecutionAdapter` + `ConfirmDispatcher` | 已具备，CONFIRM 模式自动弹窗 |
| 历史竞价快照与回放 | `snapshots/bidding_YYYYMMDD.json.gz` + `BiddingMomentumDetector.load_from_snapshot()` | 已具备 |
| 市场温度与历史报告 | `market_pulse_engine.py` + `market_pulse_db.py` | 基础可用 |

### 核心缺口

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| 跨日情绪状态机 | 无法识别“昨日恐慌、今日修复”的市场背景 | P0 |
| 前日最弱/最强板块记忆 | 无法知道哪些板块具备翻转锚点 | P0 |
| 竞价专属决策引擎 | 09:25 前无法独立生成开仓候选 | P0 |
| AuctionSignal 到内核 dict 的适配层 | 当前内核不是 `kernel.submit(sig)`，必须使用现有 `enrich_decision_item()`/`evaluate_decision_item()` 链路 | P0 |
| 竞价场景差异化风控 | 现有风控参数为全局盘中场景，竞价需要临时上下文覆盖 | P1 |
| 离线回测和性能门槛 | 没有先验证，容易实盘误报 | P1 |
| 盘前报告与 UI 情绪灯 | 可提升可解释性，但应排在算法闭环之后 | P2 |

---

## 二、总体架构

新增三类设计组件，全部以独立模块为主，避免侵入现有盘中引擎：

1. `MarketSentimentFSM`：跨日情绪状态机，负责读取昨日/最近交易日市场快照、维护状态和解释原因。
2. `AuctionDecisionEngine`：竞价专属信号生成器，只基于只读快照计算候选，不直接下单。
3. `auction_signal_adapter`：把 `AuctionSignal` 转为当前 TradingKernel 可识别的标准 dict，再调用 `enrich_decision_item(item, write_journal=True)`。

推荐链路：

```text
15:05 收盘
  -> DailyPulseEngine / MarketPulse 数据
  -> MarketSentimentFSM.save_daily_snapshot()
  -> market_pulse.db.daily_sentiment

次日 09:15 前
  -> MarketSentimentFSM.load_latest_snapshot()
  -> 构建 yesterday_worst_sectors / yesterday_top_sectors O(1) 缓存

09:20-09:25
  -> BiddingMomentumDetector 持续更新竞价快照
  -> MarketSentimentFSM.build_bidding_snapshot(detector)
  -> MarketSentimentFSM.classify()
  -> AuctionDecisionEngine.generate_signals()

09:25-09:30
  -> auction_signal_to_decision_item()
  -> trading_kernel.kernel_service.enrich_decision_item(..., write_journal=True)
  -> RiskGate
  -> CONFIRM 气泡 / PAPER / OBSERVE
```

重要修正：不要新增或假设 `TradingKernel.submit()`。当前真实入口是 `TradingKernelService.evaluate_decision_item()`，外部更适合使用 `enrich_decision_item()`。

---

## 三、核心模块设计

### 3.1 跨日情绪状态机 `market_sentiment_fsm.py`

建议新增文件：`market_sentiment_fsm.py`

#### 状态枚举

正式采用六态，避免文档中五态和图示不一致：

```python
class SentimentState(Enum):
    NEUTRAL = "NEUTRAL"      # 中性
    PANIC = "PANIC"          # 恐慌
    REPAIR = "REPAIR"        # 修复
    REVERSAL = "REVERSAL"    # 翻转
    FOMO = "FOMO"            # 追高/高潮
    COOLDOWN = "COOLDOWN"    # 冷却
```

状态路径：

```text
NEUTRAL -> PANIC -> REPAIR -> REVERSAL -> FOMO
             ^                         |
             |                         v
             +------ COOLDOWN <--------+
```

#### 数据结构

Python 3.9.13 / Nuitka 兼容要求：

- `dataclass` 不使用 `slots=True`，统一写 `@dataclass(frozen=True)`。
- 类型标注不使用 `dict | None`、`list[str]`、`dict[str, X]` 等 3.10+ 或 3.9 编译环境中容易出问题的写法。
- 统一从 `typing` 导入 `Any, Dict, List, Mapping, Optional, Set, Tuple`。

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple


@dataclass(frozen=True)
class SectorRecord:
    name: str
    avg_pct: float
    leader_code: str = ""
    leader_name: str = ""
    leader_pct: float = 0.0
    board_score: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    date: str                    # 统一使用 YYYY-MM-DD
    index_pct: float
    up_count: int
    down_count: int
    limit_up: int
    limit_down: int
    temperature: float
    breadth_ratio: float         # up_count / (up_count + down_count)
    top_sectors: Tuple[SectorRecord, ...]
    worst_sectors: Tuple[SectorRecord, ...]
    source_version: str = "daily_sentiment.v1"


@dataclass(frozen=True)
class BiddingSnapshot:
    date: str
    generated_at: str
    up_count: int
    down_count: int
    limit_up: int
    limit_down: int
    active_sectors: Tuple[SectorRecord, ...]
    stock_snap: Mapping[str, Mapping[str, Any]]
```

#### 对外接口

```python
class MarketSentimentFSM:
    def save_daily_snapshot(self, summary_data: Dict[str, Any], active_sectors: List[Dict[str, Any]]) -> MarketSnapshot: ...
    def load_latest_snapshot(self, trade_date: Optional[str] = None) -> Optional[MarketSnapshot]: ...
    def build_bidding_snapshot(self, detector) -> BiddingSnapshot: ...
    def classify(self, bidding: BiddingSnapshot) -> SentimentState: ...
    def get_state(self) -> SentimentState: ...
    def get_confidence(self) -> float: ...
    def get_sector_sets(self) -> Dict[str, Set[str]]: ...
    def explain_state(self) -> Dict[str, Any]: ...
```

#### 状态判定规则

`PANIC` 基准：

- 昨日 `index_pct <= -1.0`，或 `breadth_ratio <= 0.35`
- 或昨日 `limit_down` 明显放大且 `temperature <= 35`

`REPAIR`：

- 昨日为 `PANIC`
- 今日竞价上涨家数占比 `>= 0.45`
- 昨日最弱板块 Top5 中至少 2 个竞价平开或高开，即 `avg_pct >= -0.3`

`REVERSAL`：

- 昨日为 `PANIC` 或当前为 `REPAIR`
- 昨日最弱板块 Top5 中至少 3 个竞价平开/高开
- 这些板块的龙头或候选股进入竞价评分 Top 20% 或全市场 Top 30
- 今日跌停数未扩散：`today_limit_down <= yesterday_limit_down * 1.2 + 3`

`FOMO`：

- 竞价高开扩散过快，最强板块/候选股普遍高开超过 4%-5%
- 这种状态下可展示，不建议自动买入

`COOLDOWN`：

- 前一交易日 FOMO 后出现强分歧，或连续误报/亏损触发冷却

---

## 四、数据持久化方案

### 4.1 新表 `daily_sentiment`

可在 `market_pulse_db.py` 扩展，建议字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | TEXT PRIMARY KEY | 统一 `YYYY-MM-DD` |
| `index_pct` | REAL | 主要指数涨跌幅 |
| `breadth_ratio` | REAL | 涨跌家数比 |
| `up_count` | INTEGER | 上涨家数 |
| `down_count` | INTEGER | 下跌家数 |
| `limit_up` | INTEGER | 涨停家数 |
| `limit_down` | INTEGER | 跌停家数 |
| `temperature` | REAL | 市场温度 |
| `worst_sectors_json` | TEXT | 昨日最弱板块 Top5 |
| `top_sectors_json` | TEXT | 昨日最强板块 Top5 |
| `indices_json` | TEXT | 指数明细 |
| `source_version` | TEXT | schema/算法版本 |
| `created_at` | TEXT | 落盘时间 |

### 4.2 日期规则

- 所有数据库日期统一为 `YYYY-MM-DD`。
- 文件名仍可沿用 `snapshots/bidding_YYYYMMDD.json.gz`。
- `load_latest_snapshot()` 不能简单取自然日“昨天”，必须查询小于今日的最近一个有记录交易日。

### 4.3 落盘原则

- 使用 `ThreadPoolExecutor` 或现有后台任务提交落盘，避免 UI 阻塞。
- SQLite 连接只在任务内部创建和关闭。
- 所有 JSON 字段必须 `ensure_ascii=False`，并做 numpy 类型转换。

---

## 五、竞价决策引擎

建议新增文件：`auction_decision_engine.py`

### 5.1 信号结构

```python
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class AuctionSignal:
    code: str
    name: str
    sector: str
    signal_type: str          # REVERSAL_BUY / CONTINUATION_BUY / OVERSOLD_BOUNCE
    confidence: float         # 0-100，人类展示用
    confidence_norm: float    # 0-1，TradingKernel 风控用
    yesterday_drop: float
    auction_open_pct: float
    bidding_score: float
    dff: float
    price: float
    priority: int
    reason: str
    features: Dict[str, object]
```

### 5.2 快照读取方式

不要无锁直接遍历 detector 内部 dict。推荐锁内只做浅拷贝，锁外计算：

```python
active_sectors = detector.get_active_sectors()
with detector._lock:
    stock_snap = dict(detector._global_snap_cache)
```

这不是“绝对零 GIL”，而是“UI 线程零阻塞、锁内极短、计算在锁外”。

### 5.3 三类信号

#### REVERSAL_BUY：情绪翻转龙头

条件：

- `fsm.state in {REPAIR, REVERSAL}`
- 所属板块在昨日最弱板块集合
- 个股昨日跌幅 `<= -3%`
- 今日竞价涨幅 `0% < auction_open_pct < 4%`
- 竞价评分位于全市场 Top 20% 或 Top 30
- `dff > 0` 或竞价量能相对昨日同段放大

置信度：

```text
base 60
+ 板块翻转强度 0-15
+ 龙头/排名确认 0-15
+ 昨日跌幅修复弹性 0-5
+ 大盘修复 0-5
```

#### CONTINUATION_BUY：主线强延续

条件：

- 所属板块在昨日最强板块集合，且连续 2 个交易日以上保持热点
- 个股昨日涨幅 `>= 3%` 或涨停
- 今日竞价未大幅低开：`auction_open_pct > -1%`
- 板块 `board_score > 均值 + 1σ` 或位于 Top 10

注意：该信号不是“情绪翻转”，应独立限额，避免主线追高和翻转低吸混在一起。

#### OVERSOLD_BOUNCE：超跌反弹

条件：

- 个股近 3 日累计跌幅 `<= -8%`
- 今日竞价 `-0.5% <= auction_open_pct <= 2%`
- 技术面接近 MA60、SWS 或其他既有支撑特征
- `dff > 0`
- 所属板块没有继续扩散杀跌

注意：该信号应最低仓位，只能作为观察/小仓试错候选。

### 5.4 信号截断

- 弹窗投递：最多 Top 3。
- 报告展示：最多 Top 8。
- 每个股票当天只投递一次，避免 09:25-09:30 重复弹窗。

---

## 六、内核适配层

建议新增文件：`auction_signal_adapter.py`

### 6.1 转换为现有内核 dict

```python
def auction_signal_to_decision_item(sig: AuctionSignal) -> Dict[str, Any]:
    return {
        "code": sig.code,
        "name": sig.name,
        "sector": sig.sector,
        "signal_type": sig.signal_type,
        "source": "auction_sentiment_reversal",
        "price": sig.price,
        "current_price": sig.price,
        "change_pct": sig.auction_open_pct,
        "pct_diff": sig.auction_open_pct,
        "dff": sig.dff,
        "priority": sig.priority,
        "reason": sig.reason,
        "raw_reason": sig.reason,
        "journal_ts": datetime.now().isoformat(timespec="seconds"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "is_auction": True,
        "features": {
            **sig.features,
            "action": "BUY",
            "is_auction": True,
            "confidence": sig.confidence_norm,
            "setup": sig.signal_type,
        },
    }
```

### 6.2 投递方式

```python
from trading_kernel.kernel_service import enrich_decision_item

result = enrich_decision_item(item, write_journal=True)
```

注意：

- `OBSERVE` 模式只记账/富化，不会真实执行。
- `PAPER` 模式模拟成交。
- `CONFIRM` 模式风控通过后弹确认气泡。
- `LIVE_AUTO` 在本策略充分验证前不建议启用。

---

## 七、竞价专属风控

当前 `RiskLimits` 字段包括：

- `min_confidence`
- `max_pct_diff`
- `max_single_size_pct`
- `max_single_stock_position_pct`
- `max_single_sector_exposure_pct`
- `total_exposure_cap_pct`
- `max_consecutive_losses`
- `min_volume`

文档中的旧名应替换：

| 旧计划名 | 现有真实字段 |
|----------|--------------|
| `chase_high_limit_pct` | `RiskLimits.max_pct_diff` |
| `max_single_stock_pct` | `RiskLimits.max_single_stock_position_pct` |
| `signal_latency_limit_sec` | 当前暂无字段，需新增或在适配层自行判断 |
| `consecutive_loss_cooldown` | `RiskLimits.max_consecutive_losses` |

建议竞价上下文覆盖：

| 参数 | 盘中常规 | 竞价建议 | 说明 |
|------|----------|----------|------|
| `max_pct_diff` | 6.0% 左右 | 4.0%，回测后可收紧到 3.0% | 防止高开追顶 |
| `max_single_stock_position_pct` | 10%-30% | 8% | 单股暴露减半 |
| `max_single_size_pct` | 依配置 | 8% | 单笔下单也要限额 |
| `min_confidence` | 0.60-0.75 | 0.60 起步 | 与信号归一化置信度一致 |
| `max_consecutive_losses` | 3 | 2 | 竞价错误代价更高 |

推荐实现方式：不要永久修改 `service.limits`，而是在 `is_auction=True` 时使用临时 `RiskLimits` 覆盖或在 `risk_gate.evaluate()` 内部做上下文分支。

额外竞价熔断：

```python
if auction_signal.confidence_norm < 0.60:
    BLOCK("AUCTION_LOW_CONFIDENCE")
if fsm.state == SentimentState.PANIC and not reversal_detected:
    BLOCK("PANIC_WITHOUT_REVERSAL")
if today_limit_down > yesterday_limit_down * 1.5 + 3:
    BLOCK("LIMIT_DOWN_SPREADING")
if auction_open_pct >= 4.0 and signal_type == "REVERSAL_BUY":
    BLOCK("AUCTION_CHASE_HIGH")
```

---

## 八、时间网关

建议挂载在 `instock_MonitorTK.py` 的主循环/定时刷新处，但只放极薄逻辑：

```python
if now_hm == "0925" and not self._auction_signals_generated:
    self._auction_signals_generated = True
    self._schedule_after(0, self._run_auction_decision)
```

要求：

- 每个交易日只触发一次。
- 支持历史/回放模式手动触发。
- 触发后立即读取 detector 快照，不在 UI 线程做重计算。
- 若竞价面板未打开或 detector 不存在，降级为只生成报告，不投递交易内核。

---

## 九、盘前战场报告与 UI

### 报告

扩展 `premarket_analyzer.py` 或新增轻量 `premarket_battlefield_report.py`。

输出内容：

- 昨日状态：指数、涨跌比、温度、涨跌停
- 昨日最弱板块 Top5
- 今日竞价这些板块是否修复
- Top 8 候选信号
- 风控拦截原因统计
- 当前 TradingKernel 模式：`OBSERVE/PAPER/CONFIRM/LIVE_AUTO`

输出路径：

```text
logs/battlefield_report_YYYY-MM-DD.md
```

### UI

可在 `sector_bidding_panel.py` 顶部状态栏添加情绪状态 QLabel：

```text
情绪: REPAIR | 置信度 72 | 昨弱板块修复 3/5
```

此项为 P2，不应阻塞算法和回测。

---

## 十、实施路线图

### Phase 0：契约与回测准备

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 定义 `MarketSnapshot/BiddingSnapshot/AuctionSignal` | `market_sentiment_fsm.py` / `auction_decision_engine.py` | P0 |
| 定义 `auction_signal_to_decision_item()` | `auction_signal_adapter.py` | P0 |
| 固化日期格式和字段契约 | 文档 + 单测 | P0 |

### Phase 1：数据基础层

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 新增 `daily_sentiment` 表 | `market_pulse_db.py` | P0 |
| 保存每日情绪快照 | `market_sentiment_fsm.py` | P0 |
| 读取最近交易日快照 | `market_sentiment_fsm.py` | P0 |

### Phase 2：状态机与信号层

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 实现六态转换 | `market_sentiment_fsm.py` | P0 |
| 实现竞价快照构建 | `market_sentiment_fsm.py` | P0 |
| 实现三类竞价信号 | `auction_decision_engine.py` | P0 |

### Phase 3：内核与风控接入

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 标准 dict 适配 | `auction_signal_adapter.py` | P0 |
| 09:25 时间网关 | `instock_MonitorTK.py` | P1 |
| 竞价临时风控覆盖 | `trading_kernel/engine/risk_gate.py` 或 `kernel_service.py` | P1 |
| CONFIRM/PAPER 投递验证 | `trading_kernel/tests/` | P1 |

### Phase 4：报告与 UI

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 盘前战场报告 | `premarket_analyzer.py` | P2 |
| 情绪状态指示灯 | `sector_bidding_panel.py` | P2 |
| 语音播报 | `alert_manager.py` | P2 |
| 历史胜率统计 | `trading_analyzerQt6.py` | P2 |

---

## 十一、验证标准

### 单元测试

1. `MarketSentimentFSM` 状态转移测试：PANIC -> REPAIR -> REVERSAL。
2. `AuctionDecisionEngine` 信号生成测试：跌幅符号、Top 排名、截断数量。
3. `auction_signal_adapter` 契约测试：输出 dict 能被 `canonicalize_decision_queue_item()` 接收。
4. `RiskGate` 竞价上下文测试：高开超过阈值、低置信度、跌停扩散。

### 离线回测

使用 `snapshots/bidding_YYYYMMDD.json.gz` + `market_pulse.db`：

| 指标 | 目标 |
|------|------|
| 09:25 信号生成耗时 | < 300ms |
| 信号到 CONFIRM 弹窗延迟 | < 2s |
| 每日弹窗数量 | <= 3 |
| 每日报告候选 | <= 8 |
| 翻转识别准确率 | 初始目标 >= 60%，稳定后 >= 65% |
| 误报率 | < 20% |
| 开盘后 5/15/30 分钟收益 | 统计均值、胜率、最大回撤 |
| PAPER/CONFIRM 连续观察 | 至少 2 周 |

---

## 十二、最终建议

本方案应以“先适配、再回测、后接入”的顺序推进。最危险的不是算法写不出来，而是信号直接绕过现有内核契约。因此正式实施前必须优先完成：

1. 统一 `AuctionSignal -> decision_item dict`。
2. 修正风控字段名和竞价临时覆盖方式。
3. 固定日期格式和 `daily_sentiment` schema。
4. 完成状态机/信号/适配/风控四类单测。

完成这些后，再进入 UI、报告和语音播报增强。

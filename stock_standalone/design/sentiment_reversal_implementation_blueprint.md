# 情绪翻转跟单系统 - 高性能落地执行蓝图

> 目标：在不破坏现有接口的前提下，为 09:25 集合竞价结束时刻增加一条“昨日恐慌 -> 今日修复/翻转”的低侵入决策支线。
>
> 工程原则：UI 线程零阻塞、锁内只做短时浅拷贝、计算基于只读快照、所有交易投递走现有 TradingKernel/CONFIRM 链路。
>
> 状态：实施蓝图。正式写代码前应先按本蓝图补齐单测和回测夹具。

---

## 0. 关键修正

原方案方向正确，但必须先修正以下落地点：

1. 当前仓库没有 `kernel.submit(sig)` 入口。交易投递必须走 `trading_kernel.kernel_service.enrich_decision_item(item, write_journal=True)` 或 `TradingKernelService.evaluate_decision_item()`。
2. 风控字段必须对齐现有 `RiskLimits`：`max_pct_diff`、`max_single_size_pct`、`max_single_stock_position_pct`、`max_consecutive_losses`。
3. 状态机统一采用六态：`NEUTRAL/PANIC/REPAIR/REVERSAL/FOMO/COOLDOWN`。
4. 日期格式数据库统一 `YYYY-MM-DD`，快照文件继续使用 `bidding_YYYYMMDD.json.gz`。
5. 算法中的跌幅条件必须用 `<= -3%`、`<= -8%` 这类方向，避免把未跌透个股误判为超跌。
6. 不宣称“绝对零 GIL”。准确目标是：主 UI 线程零阻塞，锁内浅拷贝 < 5ms，09:25 信号生成 < 300ms。
7. 运行环境为 Python 3.9.13，示例代码必须避免 Python 3.10+ 写法：不用 `dict | None`，不用 `list[str]`/`dict[str, X]`，不用 `@dataclass(slots=True)`。

---

## 1. 新增模块总览

| 模块 | 类型 | 职责 |
|------|------|------|
| `market_sentiment_fsm.py` | 新增 | 跨日情绪快照、六态状态机、昨日最弱/最强板块 O(1) 缓存 |
| `auction_decision_engine.py` | 新增 | 基于竞价只读快照生成 `AuctionSignal` |
| `auction_signal_adapter.py` | 新增 | 将 `AuctionSignal` 转成现有 TradingKernel 可接收的 dict |
| `market_pulse_db.py` | 扩展 | 增加 `daily_sentiment` 表及 CRUD |
| `instock_MonitorTK.py` | 微调 | 09:25 触发网关，只做调度 |
| `trading_kernel/engine/risk_gate.py` 或 `kernel_service.py` | 小幅扩展 | `is_auction=True` 竞价风控上下文 |
| `premarket_analyzer.py` | 扩展 | 盘前/竞价战场报告 |
| `sector_bidding_panel.py` | 可选扩展 | 情绪状态指示灯 |

---

## 2. Phase 0：契约层优先

### Step 0.1：定义数据契约

文件：`market_sentiment_fsm.py`

Python 3.9.13 / Nuitka 兼容导入：

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
```

建议结构：

```python
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
    date: str
    index_pct: float
    up_count: int
    down_count: int
    limit_up: int
    limit_down: int
    temperature: float
    breadth_ratio: float
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

### Step 0.2：定义信号契约

文件：`auction_decision_engine.py`

```python
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class AuctionSignal:
    code: str
    name: str
    sector: str
    signal_type: str
    confidence: float          # 0-100 展示
    confidence_norm: float     # 0-1 风控
    yesterday_drop: float
    auction_open_pct: float
    bidding_score: float
    dff: float
    price: float
    priority: int
    reason: str
    features: Dict[str, object]
```

### Step 0.3：定义内核适配契约

文件：`auction_signal_adapter.py`

输出 dict 必须能被 `trading_kernel.engine.signal_canonicalizer.canonicalize_decision_queue_item()` 接受。

必备字段：

```text
code, name, sector, signal_type, source, price/current_price,
change_pct, pct_diff, dff, priority, reason/raw_reason,
journal_ts, created_at, is_auction, features
```

投递方式：

```python
from trading_kernel.kernel_service import enrich_decision_item

kernel_result = enrich_decision_item(decision_item, write_journal=True)
```

---

## 3. Phase 1：数据底座

### Step 1.1：扩展 `market_pulse_db.py`

新增 `daily_sentiment` 表：

```sql
CREATE TABLE IF NOT EXISTS daily_sentiment (
    date TEXT PRIMARY KEY,
    index_pct REAL,
    breadth_ratio REAL,
    up_count INTEGER,
    down_count INTEGER,
    limit_up INTEGER,
    limit_down INTEGER,
    temperature REAL,
    worst_sectors_json TEXT,
    top_sectors_json TEXT,
    indices_json TEXT,
    source_version TEXT,
    created_at TEXT
);
```

新增函数建议：

```python
def save_daily_sentiment(date_str: str, snapshot: Dict[str, Any]) -> bool: ...
def get_daily_sentiment(date_str: str) -> Optional[Dict[str, Any]]: ...
def get_latest_sentiment_before(date_str: str) -> Optional[Dict[str, Any]]: ...
def get_sentiment_dates(limit: int = 120) -> List[str]: ...
```

注意：

- `DB_PATH` 当前为 `./market_pulse.db`，打包/工作目录漂移时可能不稳。实现时应评估是否改为 `get_app_root()` 拼接绝对路径。
- 保存前调用现有 numpy 类型清理逻辑。
- JSON 使用 `ensure_ascii=False`。

### Step 1.2：收盘快照生成

文件：`market_sentiment_fsm.py`

`save_daily_snapshot(summary_data, active_sectors)` 从以下来源组合数据：

- `summary_data["temperature"]`
- `summary_data["breadth"]`
- `summary_data["indices"]`
- `active_sectors` 或 `summary_data["hot_sectors"]`

最强/最弱板块：

- `top_sectors`：按 `avg_pct` 或 `score` 倒序取 Top5。
- `worst_sectors`：按 `avg_pct` 升序取 Top5。
- 如果当前数据源没有跌幅板块，必须返回空列表并在 `explain_state()` 中标记 `missing_worst_sectors=True`，禁止状态机强行翻转。

### Step 1.3：最近交易日读取

`load_latest_snapshot(trade_date=None)`：

1. 若指定日期，先查该日。
2. 若未指定，查 `< today` 的最近有记录日期。
3. 不使用自然日昨天，以免周末/节假日失效。

内存缓存：

```python
self._yesterday_worst_sectors: Set[str]
self._yesterday_top_sectors: Set[str]
self._sector_record_by_name: Dict[str, SectorRecord]
```

---

## 4. Phase 2：状态机

### Step 2.1：状态定义

文件：`market_sentiment_fsm.py`

```python
class SentimentState(Enum):
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"
    REPAIR = "REPAIR"
    REVERSAL = "REVERSAL"
    FOMO = "FOMO"
    COOLDOWN = "COOLDOWN"
```

### Step 2.2：竞价快照构建

从 `BiddingMomentumDetector` 读取：

```python
active_sectors = detector.get_active_sectors()
with detector._lock:
    stock_snap = dict(detector._global_snap_cache)
```

说明：

- `get_active_sectors()` 内部已经短锁并排序。
- `_global_snap_cache` 必须在锁内浅拷贝。
- 后续遍历、排序、计算全部锁外完成。

### Step 2.3：状态转移规则

`PANIC`：

```text
yesterday.index_pct <= -1.0
OR yesterday.breadth_ratio <= 0.35
OR yesterday.temperature <= 35 and yesterday.limit_down >= 10
```

`REPAIR`：

```text
previous_state == PANIC
AND today_bidding_up_ratio >= 0.45
AND yesterday_worst_top5 中 >= 2 个板块 today avg_pct >= -0.3
```

`REVERSAL`：

```text
previous_state in {PANIC, REPAIR}
AND yesterday_worst_top5 中 >= 3 个板块 today avg_pct >= -0.3
AND 至少 1 个昨日最弱板块龙头/候选股进入竞价 Top30 或 Top20%
AND today_limit_down <= yesterday_limit_down * 1.2 + 3
```

`FOMO`：

```text
大量候选高开超过 4%-5%
OR top sectors 平均高开过快
```

`COOLDOWN`：

```text
FOMO 后强分歧
OR 连续竞价误报/亏损触发冷却
```

### Step 2.4：解释输出

状态机必须提供 `explain_state()`：

```python
{
    "state": "REVERSAL",
    "confidence": 0.72,
    "matched_rules": [...],
    "repaired_worst_sectors": ["CPO概念", "光通信", "大基金持股"],
    "blocked_reasons": [],
}
```

这份解释供日志、报告、弹窗使用。

---

## 5. Phase 3：竞价决策引擎

### Step 3.1：初始化

文件：`auction_decision_engine.py`

```python
class AuctionDecisionEngine:
    def __init__(self, fsm: MarketSentimentFSM):
        self.fsm = fsm

    def generate_signals(self, bidding: BiddingSnapshot, limit: int = 3) -> List[AuctionSignal]:
        ...
```

不建议在引擎内部长期持有 detector 引用。调用方先构造 `BiddingSnapshot`，再传入引擎，便于回测。

### Step 3.2：REVERSAL_BUY

条件：

```text
fsm.state in {REPAIR, REVERSAL}
sector in fsm._yesterday_worst_sectors
yesterday_drop <= -3.0
0.0 < auction_open_pct < 4.0
bidding_score in Top20% or Top30
dff > 0 or volume_ratio >= 1.5
```

置信度：

```text
60
+ sector_repair_bonus      0-15
+ leader_rank_bonus        0-15
+ drop_elasticity_bonus    0-5
+ market_repair_bonus      0-5
```

### Step 3.3：CONTINUATION_BUY

条件：

```text
sector in yesterday_top_sectors
yesterday_pct >= 3.0 or is_limit_up
auction_open_pct > -1.0
board_score in Top10 or board_score > mean + stdev
auction_open_pct < 5.0
```

注意：

- 该信号与翻转低吸逻辑分开统计。
- 如果状态为 FOMO，仅展示不投递，避免追高。

### Step 3.4：OVERSOLD_BOUNCE

条件：

```text
three_day_drop <= -8.0
-0.5 <= auction_open_pct <= 2.0
dff > 0
near_ma60_or_sws == True
sector_not_spreading_down == True
```

该信号默认低优先级，推荐只在报告展示或极小仓试错。

### Step 3.5：排序与截断

排序键：

```text
confidence DESC
priority DESC
bidding_score DESC
dff DESC
```

输出：

- `signals_for_confirm`: Top3
- `signals_for_report`: Top8

防重复：

```python
self._submitted_auction_codes_by_date: Dict[str, Set[str]]
```

---

## 6. Phase 4：TradingKernel 适配

### Step 4.1：适配器

文件：`auction_signal_adapter.py`

```python
def auction_signal_to_decision_item(sig: AuctionSignal) -> Dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
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
        "journal_ts": now,
        "created_at": now,
        "is_auction": True,
        "features": {
            **sig.features,
            "action": "BUY",
            "setup": sig.signal_type,
            "is_auction": True,
            "confidence": sig.confidence_norm,
            "auction_open_pct": sig.auction_open_pct,
            "yesterday_drop": sig.yesterday_drop,
            "bidding_score": sig.bidding_score,
        },
    }
```

### Step 4.2：投递

```python
from trading_kernel.kernel_service import enrich_decision_item

for sig in signals_for_confirm:
    item = auction_signal_to_decision_item(sig)
    result = enrich_decision_item(item, write_journal=True)
```

行为：

- `OBSERVE`：只计算/记录，不会执行。
- `PAPER`：模拟下单。
- `CONFIRM`：风控通过后弹确认气泡。
- `LIVE_AUTO`：不建议在验证期使用。

### Step 4.3：避免误触发

必须保留 `write_journal=True` 只在真实投递链路使用。UI 富化展示仍使用 `write_journal=False`。

---

## 7. Phase 5：竞价风控上下文

### Step 5.1：字段对齐

真实 `RiskLimits` 字段：

```python
RiskLimits(
    max_single_size_pct=...,
    min_confidence=...,
    max_single_stock_position_pct=...,
    max_single_sector_exposure_pct=...,
    total_exposure_cap_pct=...,
    max_consecutive_losses=...,
    max_pct_diff=...,
    min_volume=...,
)
```

### Step 5.2：建议覆盖值

```python
auction_limits = replace(
    service.limits,
    max_single_size_pct=min(service.limits.max_single_size_pct, 0.08),
    max_single_stock_position_pct=min(service.limits.max_single_stock_position_pct, 0.08),
    max_pct_diff=min(service.limits.max_pct_diff, 4.0),
    min_confidence=max(service.limits.min_confidence, 0.60),
    max_consecutive_losses=min(service.limits.max_consecutive_losses, 2),
)
```

### Step 5.3：实现位置选择

两种可选方案：

1. 在 `kernel_service.evaluate_decision_item()` 检测 `item_dict["is_auction"]`，调用 `risk_gate.evaluate()` 时传入临时 limits。
2. 在 `risk_gate.evaluate()` 内部读取 `signal.features["is_auction"]`，局部收紧 limits。

推荐方案 1：上下文更清晰，测试更容易。

### Step 5.4：额外熔断

```python
if signal.features.get("is_auction"):
    if intent.confidence < 0.60:
        BLOCK("AUCTION_LOW_CONFIDENCE")
    if signal.features.get("auction_open_pct", 0.0) >= 4.0:
        BLOCK("AUCTION_CHASE_HIGH")
    if signal.features.get("limit_down_spreading", False):
        BLOCK("AUCTION_LIMIT_DOWN_SPREADING")
```

---

## 8. Phase 6：09:25 时间网关

文件：`instock_MonitorTK.py`

### Step 6.1：状态变量

```python
self._auction_signals_generated_date = ""
```

### Step 6.2：触发逻辑

```python
today = datetime.now().strftime("%Y-%m-%d")
now_hm = datetime.now().strftime("%H%M")

if now_hm == "0925" and self._auction_signals_generated_date != today:
    self._auction_signals_generated_date = today
    self._schedule_after(0, self._run_auction_decision)
```

### Step 6.3：执行逻辑

```python
def _run_auction_decision(self):
    detector = getattr(getattr(self, "sector_bidding_panel", None), "detector", None)
    if detector is None:
        logger.warning("[Auction] detector unavailable, skip trading submission")
        return

    fsm = self.market_sentiment_fsm
    bidding = fsm.build_bidding_snapshot(detector)
    state = fsm.classify(bidding)

    engine = AuctionDecisionEngine(fsm)
    signals = engine.generate_signals(bidding, limit=3)

    for sig in signals:
        item = auction_signal_to_decision_item(sig)
        enrich_decision_item(item, write_journal=True)
```

注意：

- 实际代码要做好 import fallback，避免启动时新增模块失败影响主程序。
- 若 state 为 `PANIC/FOMO/COOLDOWN`，默认只生成报告，不投递交易。
- 历史回放模式可加手动按钮触发，不强绑定墙上时间。

---

## 9. Phase 7：报告与 UI

### Step 7.1：盘前战场报告

文件：`premarket_analyzer.py` 或新增 `premarket_battlefield_report.py`

输出路径：

```text
logs/battlefield_report_YYYY-MM-DD.md
```

报告结构：

```markdown
# 盘前战场报告 YYYY-MM-DD 09:25

## 情绪状态
- 状态：REVERSAL
- 置信度：72/100
- 昨日大盘：-1.35%
- 涨跌比：32:68

## 昨日最弱板块修复
| 板块 | 昨日涨跌 | 今日竞价 | 状态 |

## 竞价候选
| 排名 | 类型 | 代码 | 名称 | 板块 | 昨跌 | 竞价 | 分数 | 处理 |

## 风控摘要
| 代码 | 结果 | 原因 |
```

### Step 7.2：竞价面板状态灯

文件：`sector_bidding_panel.py`

P2 可选，不阻塞核心闭环。

建议显示：

```text
情绪: REPAIR | 置信度 72 | 昨弱修复 3/5
```

---

## 10. 测试计划

### Step 10.1：单测

新增测试建议：

| 测试 | 重点 |
|------|------|
| `test_market_sentiment_fsm.py` | 日期读取、六态转换、解释输出 |
| `test_auction_decision_engine.py` | 三类信号、跌幅符号、Top 截断 |
| `test_auction_signal_adapter.py` | dict 契约与 canonicalizer 兼容 |
| `test_auction_risk_context.py` | `is_auction` 风控覆盖、高开拦截 |

### Step 10.2：离线回测

使用：

```text
snapshots/bidding_YYYYMMDD.json.gz
market_pulse.db.daily_sentiment
```

统计：

- 09:25 信号生成耗时
- Top3 信号开盘后 5/15/30 分钟收益
- 最大回撤
- 翻转识别准确率
- 误报率
- 每日弹窗数量

### Step 10.3：上线门槛

必须满足：

| 指标 | 门槛 |
|------|------|
| 信号生成耗时 | < 300ms |
| CONFIRM 弹窗延迟 | < 2s |
| 每日弹窗数 | <= 3 |
| 回测误报率 | < 20% |
| PAPER/CONFIRM 观察 | 至少 2 周 |

---

## 11. 实施顺序清单

1. [ ] 新增数据契约和 `AuctionSignal` 契约。
2. [ ] 新增 `auction_signal_adapter.py`，确认能被内核 canonicalizer 接收。
3. [ ] 扩展 `market_pulse_db.py`，新增 `daily_sentiment`。
4. [ ] 实现 `MarketSentimentFSM` 的保存、读取、六态判断。
5. [ ] 实现 `AuctionDecisionEngine`，先只回测不投递。
6. [ ] 增加竞价风控上下文。
7. [ ] 接入 09:25 时间网关，默认 OBSERVE/PAPER。
8. [ ] 增加盘前战场报告。
9. [ ] 最后增加 UI 情绪灯和语音播报。

---

## 12. 禁止事项

正式实施时避免以下做法：

- 不要绕过 `TradingKernelService.evaluate_decision_item()` 直接调用交易网关。
- 不要把 `AuctionSignal` 直接塞进 `ConfirmDispatcher`。
- 不要在 UI 线程遍历全市场 `_global_snap_cache` 做重计算。
- 不要无锁遍历 detector 内部可变 dict。
- 不要永久改写全局 `service.limits` 来适配竞价。
- 不要在 `LIVE_AUTO` 下首日启用该策略。
- 不要把自然日“昨天”等同于最近交易日。

---

## 13. 成功标准

本蓝图完成后，应达到：

1. 09:25 可基于昨日市场记忆生成 Top3 情绪翻转候选。
2. 所有候选都能解释“昨日为什么恐慌、今日为什么修复、为什么是这只股”。
3. 所有交易意图都经过现有 TradingKernel、RiskGate、CONFIRM/PAPER 链路。
4. 回测、实盘观察、风控日志可以复盘每一次通过和拦截。
5. 不影响盘中 `SectorFocusEngine`、`BiddingMomentumDetector` 和 UI 刷新性能。

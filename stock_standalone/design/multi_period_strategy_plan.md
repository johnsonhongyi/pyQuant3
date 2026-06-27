# 多周期联动策略筛选系统 — 全面规划

> **日期**: 2026-06-27 | **状态**: 仅规划，不实施 | **周期覆盖**: d, 2d, 3d, w, m, 45d, 3M

---

## 一、系统现状分析

### 1.1 已具备的基础设施

| 组件 | 文件 | 能力 |
|------|------|------|
| **数据加载** | `tdd.get_append_lastp_to_df()` | 支持按 resample 加载 274 列技术指标 |
| **MultiPeriodManager** | `multi_period_manager.py` | 已有多周期合并、共振评分、形态检测框架 |
| **StockSelector** | `stock_selector.py` | 单周期选股（趋势/量能/结构评分） |
| **StockLiveStrategy** | `stock_live_strategy.py` | 实时监控、信号触发、K线抓取调度 |
| **策略管理器** | `strategy_manager.py` | H4 过滤表达式引擎（`df.query()` 驱动） |
| **选股窗口** | `stock_selection_window.py` | UI 展示 + 板块聚焦 + 决策队列 |
| **filter_resample_Monitor** | `filter_resample_Monitor.py` | **原型参考**：已有 d/3d/w/m 四周期交集过滤 |
| **RealtimeDataService** | `realtime_data_service.py` | `_df_all_cache` 内存快照，按周期独立缓存 |

### 1.2 关键发现：filter_resample_Monitor.py 原型

该文件第 442-468 行已实现了多周期交集筛选的**原始原型**：

```python
t3d_code = top_all_3d.query(query_rule)
tw_code  = top_all_w.query(query_rule)
tm_code  = top_all_m.query(query_rule)
td_code  = top_all_d.query(query_rule)
code_f   = list(set(tw_code.index) & set(tm_code.index))
```

这是**多周期交集**的最早实现，但存在以下缺陷：
- 所有周期使用**同一条** query_rule（无法为不同周期定制不同条件）
- 无权重/评分体系，仅做布尔交集
- 硬编码，不可配置

### 1.3 数据列清单（各周期通用 274 列）

每个周期的 DataFrame 都包含以下核心列（已验证 45d/3M 均可计算）：

- **价格**: `close, open, high, low, lastp1d~10d, lasth1d~10d, lastl1d~10d`
- **均线**: `ma5d, ma10d, ma20d, ma60d, ma51d~ma510d`
- **通道**: `upper, upper1, upper2, lower, ptop, pbottom, pbreak, pdays`
- **量能**: `vol, volume, last6vol, lastv1d~10d, ratio`
- **动能**: `percent, per1d~10d, win, red, sum_perc, slope`
- **结构**: `hmax, max5, max10, high4, nlow, nhigh, nclose`
- **MACD**: `macdlast1, macdlast2`
- **评估**: `eval1d, signal1d, EVAL_STATE, TrendS, Rank`

---

## 二、多周期联动策略架构设计

### 2.1 核心设计理念

```
┌──────────────────────────────────────────────────────────┐
│                   多周期联动策略引擎                       │
│  MultiPeriodStrategyEngine                               │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Phase 1: 数据预加载层                                    │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐     │
│  │  d   │  2d  │  3d  │  w   │  m   │ 45d  │  3M  │     │
│  └──┬───┴──┬───┴──┬───┴──┬───┴──┬───┴──┬───┴──┬───┘     │
│     │      │      │      │      │      │                 │
│  Phase 2: 各周期独立条件评估 (Per-Period Filter)           │
│  ┌──────────────────────────────────────────────┐        │
│  │ 每个周期对应一组独立的筛选条件 (ConditionSet)  │        │
│  │ 输出: {code: bool} 的 mask + score            │        │
│  └──────────────────────────────────────────────┘        │
│                                                          │
│  Phase 3: 跨周期交叉验证 (Cross-Period Resonance)         │
│  ┌──────────────────────────────────────────────┐        │
│  │ 交集/并集/加权共振 → 最终候选集                │        │
│  └──────────────────────────────────────────────┘        │
│                                                          │
│  Phase 4: 排序与输出                                      │
│  ┌──────────────────────────────────────────────┐        │
│  │ 综合评分排序 → 策略选股窗口展示                │        │
│  └──────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

### 2.2 条件描述语法设计 (Strategy DSL)

为实现"快速"策略定义，设计一套**基于 JSON 配置 + pandas query 表达式**的 DSL：

```json
{
  "strategy_name": "大周期触底 + 小周期上涨结构",
  "description": "月/45d级别触底MA10反转，周线上涨，日线缩量蓄势",
  "conditions": {
    "m": {
      "filter": "close > ma10d and close > lastp1d",
      "weight": 1.5,
      "label": "月线触底反转"
    },
    "45d": {
      "filter": "close > ma10d and close > lastp1d",
      "weight": 1.5,
      "label": "45日触底反转"
    },
    "w": {
      "filter": "close > lastp1d and lastp1d > lastp2d and close > ma5d",
      "weight": 1.2,
      "label": "周线上涨结构"
    },
    "d": {
      "filter": "volume < 1.5 and close > ma10d",
      "weight": 1.0,
      "label": "日线缩量守线"
    }
  },
  "cross_mode": "intersection",
  "min_periods_pass": 3,
  "sort_by": "resonance_score"
}
```

> [!IMPORTANT]
> 条件中的列名直接映射到各周期 DataFrame 的列，与现有 `strategy_manager.py` 的 H4 过滤表达式引擎完全兼容。

---

## 三、预置策略模板库

### 3.1 策略模板 A：大周期触底 + 小周期启动

**交易逻辑**: 月线/45d 级别构建底部后首次站上 MA10，周线出现上涨结构，日线缩量确认

| 周期 | 条件 | 含义 |
|------|------|------|
| **3M / m** | `close > ma10d and close > lastp1d` | 大级别触底反转确认 |
| **45d** | `close > ma10d and close > lastp1d` | 中大级别趋势转多 |
| **w** | `close > lastp1d and lastp1d > lastp2d and close > ma5d` | 周线连续上涨 |
| **d** | `volume < 1.5 and close > ma10d and close > ma20d` | 日线缩量守住中线 |

**交叉模式**: `intersection`（全部满足）  
**预期应用**: 中线布局，持仓 2-8 周

### 3.2 策略模板 B：多周期均线共振多头

**交易逻辑**: 所有周期均线多头排列

| 周期 | 条件 |
|------|------|
| **3M** | `ma5d > ma10d and ma10d > ma20d` |
| **m** | `ma5d > ma10d and ma10d > ma20d and close > ma5d` |
| **w** | `ma5d > ma10d and close > ma5d` |
| **d** | `ma5d > ma10d and ma10d > ma20d and close > ma5d` |

**交叉模式**: `intersection`  
**预期应用**: 趋势跟随，强势股中线持仓

### 3.3 策略模板 C：大周期压力突破 + 量能确认

| 周期 | 条件 |
|------|------|
| **m / 45d** | `close > upper1 or close > hmax` |
| **w** | `close > upper1 and volume > 1.2` |
| **d** | `close > lastp1d and volume > 1.5 and close > upper` |

**交叉模式**: `weighted`（加权共振，至少 2 个大周期通过）

### 3.4 策略模板 D：周线底部横盘 + 日线放量突破

| 周期 | 条件 |
|------|------|
| **w** | `abs(close - ma60d) / ma60d < 0.05 and max5 - min5 < max5 * 0.08` |
| **d** | `close > max5 and volume > 2.0 and percent > 3` |

**交叉模式**: `intersection`  
**预期应用**: 超短/短线，底部放量首板

### 3.5 策略模板 E：周月共振回调买点

| 周期 | 条件 |
|------|------|
| **m** | `close > ma20d and ma5d > ma10d` |
| **w** | `close > ma10d and percent < 0 and close > ma20d` |
| **d** | `close > ma20d and volume < 1.0 and low > ma20d * 0.98` |

**交叉模式**: `intersection`  
**预期应用**: 趋势中的缩量回踩，低风险介入

### 3.6 策略模板 F：MACD 多周期金叉共振

| 周期 | 条件 |
|------|------|
| **m / 45d** | `macdlast1 > 0` |
| **w** | `macdlast1 > 0 and macdlast1 > macdlast2` |
| **d** | `macdlast1 > 0 and percent > 0` |

**交叉模式**: `weighted`（MACD 多周期同向）

---

## 四、实现路径规划

### Phase 1: 核心引擎 (MultiPeriodStrategyEngine)

**新增文件**: `multi_period_strategy_engine.py`

**核心类设计**:

```python
class MultiPeriodStrategyEngine:
    """多周期联动策略引擎"""
    
    SUPPORTED_PERIODS = ['d', '2d', '3d', 'w', 'm', '45d', '3M']
    
    def __init__(self, periods=None):
        self.periods = periods or ['d', 'w', 'm']
        self._period_dfs: Dict[str, pd.DataFrame] = {}
        self._strategies: List[dict] = []
        
    def load_period_data(self, period: str) -> pd.DataFrame:
        """加载指定周期数据（复用 tdd.get_append_lastp_to_df）"""
        
    def set_period_df(self, period: str, df: pd.DataFrame):
        """外部注入已加载的周期数据（盘中由 RealtimeDataService 推送）"""
        
    def evaluate_single_period(self, period: str, condition: str) -> pd.Index:
        """对单一周期执行 query 条件，返回满足条件的股票代码集"""
        
    def evaluate_strategy(self, strategy_config: dict) -> pd.DataFrame:
        """执行完整的多周期联动策略，返回排序后的候选 DataFrame"""
        
    def compute_resonance_score(self, results: Dict[str, pd.Index]) -> pd.Series:
        """计算跨周期共振评分"""
```

**关键方法流程**:

```
evaluate_strategy(config):
  1. 遍历 config["conditions"] 中的各周期条件
  2. 对每个周期: df.query(filter_expr) → 得到 pass_codes
  3. 根据 cross_mode 做交叉验证:
     - "intersection": 所有周期的 pass_codes 取交集
     - "union": 任意 N 个周期通过即可 (min_periods_pass)
     - "weighted": 按权重加分，总分排序
  4. 生成结果 DataFrame，标注每个周期的通过状态
  5. 排序输出
```

### Phase 2: 数据预加载管道

**改造点**: `realtime_data_service.py` / `instock_MonitorTK.py`

```
盘前冷启动流程:
  09:00 → 后台线程并行加载 7 个周期的 TDX 历史数据
  09:15 → 各周期 DataFrame 注入 MultiPeriodStrategyEngine
  09:25 → 首轮多周期策略扫描完成

盘中增量更新:
  主周期 (d) → 每轮行情刷新时更新 close/volume 等实时字段
  大周期 (w/m/45d/3M) → 仅在开盘时加载一次，盘中不变
  中周期 (2d/3d) → 尾盘收盘后刷新或每小时更新
```

**性能预估**:
- 单周期加载耗时: ~3-8s (约 5000 只股票 × 274 列)
- 7 个周期并行加载: ~15-25s (首次冷启动)
- 策略评估 (query + 交集): <500ms per strategy

### Phase 3: UI 集成

**改造点**: `stock_selection_window.py`

在策略选股窗口新增 **Tab: 🔗 多周期联动**:

```
┌─────────────────────────────────────────────────┐
│ 📋策略选股 │ 🔥板块聚焦 │ 🎯实时决策 │ 🔗多周期联动 │
├─────────────────────────────────────────────────┤
│ ┌─ 策略选择器 ─────────────────────────────┐    │
│ │ [▼ 大周期触底+小周期启动 ] [▶ 运行] [⚙] │    │
│ └──────────────────────────────────────────┘    │
│ ┌─ 各周期通过状态 ─────────────────────────┐    │
│ │ 3M:✅ m:✅ 45d:✅ w:✅ d:⚠  2d:-- 3d:-- │    │
│ │ 通过: 47只  共振分>80: 12只               │    │
│ └──────────────────────────────────────────┘    │
│ ┌─ 结果表 ────────────────────────────────┐    │
│ │ 代码│名称│共振分│d│w│m│45d│3M│涨幅│量比│板块│    │
│ │ ...  ...  ...                            │    │
│ └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### Phase 4: 策略编辑器 UI

新增策略可视化编辑器 (Toplevel 弹窗):

```
┌─ 多周期策略编辑器 ──────────────────────────────┐
│ 策略名称: [___________________]                  │
│                                                  │
│ ┌─ 周期条件 ───────────────────────────────────┐ │
│ │ [✓] d   : [close>ma10d and volume<1.5    ] │ │
│ │ [✓] w   : [close>lastp1d and close>ma5d  ] │ │
│ │ [✓] m   : [close>ma10d and close>lastp1d ] │ │
│ │ [ ] 45d : [                              ] │ │
│ │ [ ] 3M  : [                              ] │ │
│ └─────────────────────────────────────────────┘ │
│                                                  │
│ 交叉模式: (●)交集 ( )并集(≥N) ( )加权共振        │
│ 最少通过周期数: [3]                               │
│                                                  │
│ [💾 保存] [▶ 预览] [📋 从模板加载]                │
└──────────────────────────────────────────────────┘
```

---

## 五、数据流与集成拓扑

```
tdd.get_append_lastp_to_df(top_now, resample='d')   ──┐
tdd.get_append_lastp_to_df(top_now, resample='w')   ──┤
tdd.get_append_lastp_to_df(top_now, resample='m')   ──┤
tdd.get_append_lastp_to_df(top_now, resample='45d') ──┼─→ MultiPeriodStrategyEngine
tdd.get_append_lastp_to_df(top_now, resample='3M')  ──┤      ↓
tdd.get_append_lastp_to_df(top_now, resample='2d')  ──┤   evaluate_strategy()
tdd.get_append_lastp_to_df(top_now, resample='3d')  ──┘      ↓
                                                        候选结果 DataFrame
                                                              ↓
                                               ┌──────────────┼──────────────┐
                                               ↓              ↓              ↓
                                        StockSelector   选股窗口 UI    SignalBus
                                        (score合并)     (Tab展示)    (信号推送)
```

---

## 六、策略配置持久化

**存储位置**: `config/multi_period_strategies.json`

```json
{
  "version": 1,
  "strategies": [
    {
      "id": "tpl_bottom_reversal",
      "name": "大周期触底 + 小周期启动",
      "enabled": true,
      "conditions": { ... },
      "cross_mode": "intersection",
      "min_periods_pass": 3,
      "created_at": "2026-06-27",
      "last_used": "2026-06-27"
    }
  ],
  "active_strategy_id": "tpl_bottom_reversal"
}
```

---

## 七、与现有系统的接口对齐

### 7.1 不修改的接口

| 接口 | 理由 |
|------|------|
| `StockSelector.filter_strong_stocks()` | 保持单周期选股逻辑不变 |
| `StockLiveStrategy.check_all_stocks()` | 实时信号触发逻辑不变 |
| `RealtimeDataService` 数据管道 | 仅增加多周期 cache 注入点 |

### 7.2 需要扩展的接口

| 接口 | 改动 |
|------|------|
| `MultiPeriodManager.compute_resonance_score()` | 重构为支持自定义条件配置 |
| `StockSelector.get_candidates_df()` | 增加 `multi_period=True` 参数分支 |
| `stock_selection_window._init_ui()` | 新增 Tab 页 |
| `strategy_manager.py` H4 过滤 | 复用其 query 表达式解析能力 |

---

## 八、风险与约束

| 风险 | 缓解措施 |
|------|----------|
| 7 周期并行加载内存峰值 (~2-3GB) | 使用 float32 压缩 + 懒加载大周期 |
| query 表达式语法错误导致崩溃 | try-except 包裹 + 预校验 |
| 盘中大周期数据不更新导致信号滞后 | 大周期仅做"结构背景"判断，不做精确价格比较 |
| 首次冷启动耗时 15-25s | 后台线程加载 + 进度条 + 缓存复用 |

---

## 九、实施优先级建议

| 优先级 | 任务 | 预估工时 |
|--------|------|----------|
| **P0** | `MultiPeriodStrategyEngine` 核心类 | 3-4h |
| **P0** | 预置 6 套策略模板 JSON 配置 | 1h |
| **P1** | 数据预加载管道 (并行 7 周期) | 2-3h |
| **P1** | 选股窗口新增"多周期联动" Tab | 2-3h |
| **P2** | 策略可视化编辑器 UI | 3-4h |
| **P2** | 盘中自动扫描 + SignalBus 推送 | 2h |
| **P3** | 策略回测验证框架 | 4-5h |

> [!TIP]
> P0 阶段仅需新增 1 个文件 + 1 个 JSON 配置，**零破坏**现有系统。

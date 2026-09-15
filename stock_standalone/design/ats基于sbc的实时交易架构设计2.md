# 全自动分时多周期交易执行系统 v2 — 更新版实施设计方案

> **日期**: 2026-09-15 21:42  
> **版本**: v2 — 根据用户反馈全面修订  
> **核心修正**: 策略理念从"被动等VWAP破位止损"→"**主动识别派发/弱势特征提前出局**"

---

## 一、用户反馈的核心痛点与设计修正

### 用户实际交易教训（600733 北汽蓝谷）

```
问题链: 
  介入十字星 → 两天不及预期 → VWAP破位不舍得止损 → 反弹没走 → 亏损放大
                                    ↑
                            这里是致命的决策瘾
```

### 设计理念修正

| 原方案（v1）| 修正方案（v2）|
|-------------|-------------|
| 等 VWAP 破位才卖出 | **在 VWAP 破位之前就识别弱势特征提前出局** |
| 分时策略独立运行 | **分时策略 + 大级别守护策略 + 大盘/板块哨兵三位一体** |
| 单策略执行 | **激进组 + 保守组并行，守护策略独立于交易策略** |
| 先接实盘 | **先 PAPER 模拟 + SBC 标记买卖点校准 → 再接实盘** |

### 关键认知框架

```
❌ 错误思路: "等价格跌破VWAP再止损" → 被动、滞后、总是舍不得
✅ 正确思路: "识别弱势特征时主动减仓" → 主动、提前、机械执行
    
弱势特征 = {
    无量不涨    → 买入后 N 分钟内无放量上涨 → 出局
    反弹前高不过 → 反弹到前一波高点但无法突破 → 出局  
    冲高派发     → 拉高后放量回落（高位放量阴线）→ 出局
    震荡不创高   → 横盘振荡不能创新高 → 出局
    大级别 MA5d 回落 → 日线/60分 MA5 拐头向下 → 分时策略无法守护的大级别破位
    板块集中抛压  → 所属板块多股同时破位 → 系统性风险出局
}
```

---

## 二、系统架构设计 v2（三层守护体系）

```
┌─────────────────────────────────────────────────────────────────────┐
│                    三层守护体系 (Defense-in-Depth)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 3: 大盘/板块宏观守护 (MarketGuardian)                         │
│  ┌──────────────────────────────────────────────────────┐            │
│  │ 数据源: MarketStateBus.df_all + MarketSentimentFSM   │            │
│  │ 职责: 大盘暴跌 → 全仓止损                             │            │
│  │       板块集中抛压 → 同板块持仓全清                    │            │
│  │       涨停数骤降/跌停数暴增 → 冻结买入                 │            │
│  └──────────────────────────────────────────────────────┘            │
│           ↓ 全局风险信号                                             │
│  Layer 2: 大级别趋势守护 (MultiTimeframeGuard)                       │
│  ┌──────────────────────────────────────────────────────┐            │
│  │ 数据源: 日线/60分/30分 K线 + 通道策略                  │            │
│  │ 职责: MA5d 拐头向下 → 分时反弹出局                     │            │
│  │       60分通道下行加速 → 压制分时买入                   │            │
│  │       日线 cycle_stage=4(见顶) → 全面防御                │            │
│  └──────────────────────────────────────────────────────┘            │
│           ↓ 趋势上下文                                               │
│  Layer 1: 分时级交易策略 (VWAPTradingEngine)                          │
│  ┌──────────────────────────────────────────────────────┐            │
│  │ 数据源: 分时 Tick + df_all.VWAP + IPC 全局预处理数据   │            │
│  │ 进攻端: VWAP 筑底突破买入 / 站稳确认加仓               │            │
│  │ 防守端: ProactiveExitEngine (8层主动离场策略)           │            │
│  │         → 无量不涨、反弹前高不过、冲高派发、时间衰减     │            │
│  └──────────────────────────────────────────────────────┘            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、七大核心模块详细设计

---

### 模块①：VWAPTradingEngine — 分时均价交易策略引擎（进攻端）

#### 文件位置
```
ats/vwap_trading_engine.py
```

#### 数据源（全部来自已有基础设施）

| 数据 | 来源 | 获取方式 |
|------|------|----------|
| 分时 VWAP | `realtime_data_service.py` | `nclose`, `vwap0d`, `vwap1d` ... `vwap5d` |
| 跨日累计 VWAP | `realtime_data_service.py` | `vwap_cum_2d`, `vwap_cum_5d` |
| 实时价格/量 | `MarketStateBus.df_all` | `trade`, `volume`, `ratio` |
| 多周期通道评分 | `multi_period_channel_strategy.py` | `evaluate_multi_period_channel_strategy()` |
| 日线均线 | `df_all` 预计算 | `ma5d`, `ma10d`, `ma20d`, `ma60d` |
| 分时形态 | `IntradayPatternDetector` | `PatternEvent` 回调 |

#### 核心状态追踪

```python
@dataclass
class VWAPTickState:
    """每 Tick 更新的分时状态快照"""
    code: str
    price: float
    vwap_today: float               # 今日分时均价 (nclose)
    vwap_yesterday: float           # 昨日分时均价 (last_nclose)
    vwap_cum_5d: float              # 5日累计 VWAP
    
    # VWAP 动态特征
    vwap_slope_5m: float            # 5分钟 VWAP 斜率（线性回归）
    vwap_slope_15m: float           # 15分钟 VWAP 斜率
    vwap_direction: str             # "UP" | "FLAT" | "DOWN"
    
    # 价格结构特征
    price_vs_vwap: str              # "ABOVE" | "BELOW" | "CROSSING_UP" | "CROSSING_DOWN"
    minutes_above_vwap: int         # 连续站上 VWAP 分钟数
    minutes_below_vwap: int         # 连续跌破 VWAP 分钟数
    intraday_high: float            # 日内最高
    intraday_low: float             # 日内最低
    prev_day_high: float            # 前日高点（从 df_all 获取）
    
    # 量能配合
    volume_5m_avg: float            # 5分钟平均成交量
    current_volume: float           # 当前分钟成交量
    volume_ratio: float             # 量比

    # 横盘/筑底检测
    consolidation_minutes: int      # 横盘持续分钟数
    consolidation_range_pct: float  # 横盘振幅
```

#### 买入规则（进攻端，从 SBC 图表中提取的模式）

```python
# 规则 1: VWAP 筑底突破买入（301531 式）
BUY_VWAP_BASE_BREAKOUT = {
    "id": "buy_vwap_base_breakout",
    "name": "VWAP筑底突破",
    "conditions": [
        ("price_vs_vwap", "==", "CROSSING_UP"),       # 价格从下向上穿越 VWAP
        ("consolidation_minutes", ">=", 15),            # 此前横盘 ≥ 15 分钟
        ("consolidation_range_pct", "<", 1.0),          # 横盘振幅 < 1%
        ("volume_ratio", ">", 1.2),                     # 突破时放量（量比 > 1.2）
        ("vwap_direction", "in", ["UP", "FLAT"]),       # VWAP 不再下移
        ("multi_period_score", ">=", 70),               # 多周期通道评分 ≥ 70
    ],
    "action": "BUY_SCOUT",
    "size_pct": 0.10,      # 试探仓 10%
    "priority": 85,
}

# 规则 2: 站稳 VWAP 确认加仓
BUY_VWAP_CONFIRM = {
    "id": "buy_vwap_confirm",
    "name": "站稳VWAP确认加仓",
    "conditions": [
        ("minutes_above_vwap", ">=", 10),               # 站上 VWAP ≥ 10 分钟
        ("pullback_held", "==", True),                   # 回踩 VWAP 但未跌破
        ("volume_ratio", ">", 1.0),                      # 量能配合
    ],
    "action": "BUY_ADD",
    "size_pct": 0.15,
    "priority": 80,
}

# 规则 3: 低开站上 VWAP（利用已有 IntradayPatternDetector.low_open_high_walk）
BUY_LOW_OPEN_ABOVE_VWAP = {
    "id": "buy_low_open_above_vwap",
    "name": "低开走高站上均价",
    "conditions": [
        ("pattern_low_open_high_walk", "==", True),
        ("price_vs_vwap", "==", "ABOVE"),
        ("multi_period_score", ">=", 60),
    ],
    "action": "BUY_SCOUT",
    "size_pct": 0.10,
    "priority": 75,
}
```

---

### 模块②：ProactiveExitEngine — 主动出局引擎（防守端核心）

> **这是解决你核心痛点的关键模块**：不等 VWAP 破位，而是在弱势特征出现时主动出局

#### 文件位置
```
ats/proactive_exit_engine.py
```

#### 8 层递进式主动离场策略

```python
class ProactiveExitEngine:
    """
    主动出局引擎 — 8 层递进式离场策略
    
    核心理念：不要等破位才止损，在弱势特征出现时就主动减仓/清仓
    
    Layer 1~3: 时间维度策略（买入后 N 分钟内不满足预期 → 出局）
    Layer 4~5: 价格结构策略（反弹不过前高、冲高派发 → 出局）
    Layer 6~7: 量价配合策略（无量不涨、量价背离 → 出局）
    Layer 8:   VWAP 最后防线（所有主动策略都未触发时的兜底止损）
    """
```

#### Layer 1：时间衰减止损（Time Decay Stop）

```python
EXIT_TIME_DECAY = {
    "id": "exit_time_decay",
    "name": "时间衰减止损",
    "description": """
        买入后 N 分钟内价格无有效上涨 → 主动出局
        解决"介入十字星两天不及预期"的问题
    """,
    "logic": """
        买入后计时器启动:
        - 10 分钟内: 涨幅 < 0.3% → 警告
        - 20 分钟内: 涨幅 < 0.3% → 减半仓
        - 30 分钟内: 涨幅 < 0% (浮亏) → 清仓
        
        例外: 如果处于横盘筑底且量缩（可能是洗盘），延长到 45 分钟
    """,
    "params": {
        "warn_minutes": 10,
        "reduce_minutes": 20,
        "exit_minutes": 30,
        "min_gain_pct": 0.3,
        "washout_extension_minutes": 45,
    },
}
```

#### Layer 2：无量不涨止损（Volume Absence Stop）

```python
EXIT_NO_VOLUME_NO_RISE = {
    "id": "exit_no_volume_no_rise",
    "name": "无量不涨止损",
    "description": """
        买入后如果成交量持续萎缩且价格不上涨 → 主力不做，散户自嗨
    """,
    "logic": """
        计算滑动窗口:
        - 最近 5 分钟量 < 前 15 分钟均量的 50%
        - 且价格涨幅 < 0.2%
        - 持续 3 个窗口确认 → 减半仓
        - 持续 5 个窗口确认 → 清仓
    """,
    "params": {
        "volume_shrink_ratio": 0.5,
        "price_threshold_pct": 0.2,
        "confirm_windows": 3,
        "exit_windows": 5,
    },
}
```

#### Layer 3：反弹前高不过止损（Failed Rally Stop）

```python
EXIT_FAILED_RALLY = {
    "id": "exit_failed_rally",
    "name": "反弹前高不过",
    "description": """
        价格反弹到前一波高点（日内高点/前日高点）但无法突破 → 空头占优
        这是 600733 中反复出现的模式（图1 红色箭头标注的每一个卖点）
    """,
    "logic": """
        1. 检测 "前高" 参考点:
           - prev_day_high (前日高点)
           - intraday_high (日内此前高点)
           - vwap_yesterday (昨日 VWAP)
        
        2. 当价格反弹到前高的 99% ~ 100.5% 范围内:
           - 如果在此区间停留 ≥ 3 分钟但无法有效突破（超过 0.5%）
           - 且量能萎缩（量比 < 0.8）
           → 判定为"反弹前高不过"，执行减仓
        
        3. 如果反弹后回落超过前高的 1.5%:
           → 确认失败，清仓
    """,
    "params": {
        "near_prev_high_pct": 0.5,     # 接近前高 ±0.5%
        "dwell_minutes": 3,             # 停留确认分钟数
        "breakout_threshold_pct": 0.5,  # 有效突破定义
        "volume_weak_ratio": 0.8,       # 量弱判定
        "retreat_exit_pct": 1.5,        # 回落清仓线
    },
}
```

#### Layer 4：冲高派发识别（Distribution Detection）

```python
EXIT_DISTRIBUTION = {
    "id": "exit_distribution",
    "name": "冲高派发识别",
    "description": """
        利用已有的 IntradayPatternDetector.high_drop 和 
        decision_engine.evaluate_trap_veto 中的冲高回落检测
    """,
    "logic": """
        复用已有检测:
        1. IntradayPatternDetector 检测到 'high_drop' 事件
        2. 或 日内最高 > 开盘 +3% 但当前 < 最高 -2%
        3. 或 高位放量(量比>2.0) + 收阴（当前价 < 开盘价）
        
        触发后:
        - 如果浮盈 > 2%: 锁定利润，至少减半仓
        - 如果浮亏: 立即清仓
    """,
    "params": {
        "high_above_open_pct": 3.0,
        "retreat_from_high_pct": 2.0,
        "high_volume_ratio": 2.0,
    },
}
```

#### Layer 5：震荡不创新高（Oscillation No New High）

```python
EXIT_OSCILLATION = {
    "id": "exit_oscillation",
    "name": "震荡不创新高",
    "description": """
        进入横盘震荡阶段，连续 N 分钟无法创出日内新高
        且震荡中心逐步下移 → 空头控制
    """,
    "logic": """
        1. 计算最近 30 分钟的高点序列
        2. 如果高点序列呈下降趋势（每个高点 < 前一个高点）
        3. 且 VWAP 斜率为负或持平
        → 判定为"震荡不创新高"
        
        触发: 减仓 30%
        确认(再次失败): 清仓
    """,
    "params": {
        "lookback_minutes": 30,
        "peaks_declining_count": 3,
    },
}
```

#### Layer 6：量价背离（Volume-Price Divergence）

```python
EXIT_VOLUME_DIVERGENCE = {
    "id": "exit_volume_divergence",
    "name": "量价背离",
    "description": """
        复用 intraday_decision_engine.py 中的 P2 量价背离检测:
        价格创新高但成交量萎缩 → 多头力竭
    """,
    "logic": """
        复用已有: IntradayDecisionEngine._eval_volume_divergence()
        增强: 结合 DFF(资金流向差) < -0.5 作为辅助确认
    """,
}
```

#### Layer 7：大级别 MA5d 回落（已有 decision_engine 中的三日高点下移检测）

```python
EXIT_MA5D_ROLLOVER = {
    "id": "exit_ma5d_rollover",
    "name": "大级别MA5拐头",
    "description": """
        分时策略视角太小，无法感知日线级别的趋势反转
        当日线 MA5 拐头向下时，分时的任何反弹都是出货机会
        
        这是 600733 中最关键的守护 —— 60分通道斜率 -11.7° 持续下行，
        分时反弹只是在大趋势中的小波动
    """,
    "logic": """
        数据来源: df_all 中的 ma5d, ma5d_prev5（已有字段）
        
        检测:
        1. MA5d < MA5d_prev5 * 0.998 → MA5 拐头向下
        2. 价格 < MA5d → 已跌破 5 日均线
        3. 60分通道斜率 < -5° → 中期趋势走弱
        
        触发: 
        - 浮亏状态 → 分时反弹到 VWAP 附近即出局（不等突破）
        - 浮盈状态 → 设置跟踪止盈，保护利润
    """,
    "data_source": "df_all['ma5d'], df_all['ma5d_prev5'], channel_slope_60m",
}
```

#### Layer 8：VWAP 破位兜底（最后防线）

```python
EXIT_VWAP_BREAKDOWN = {
    "id": "exit_vwap_breakdown_final",
    "name": "VWAP破位兜底（最后防线）",
    "description": """
        如果前面 7 层都没触发，但价格已经跌破 VWAP
        → 这是最后一道防线，必须执行
        
        与 v1 不同：这不是唯一的止损策略，而是最后的兜底
    """,
    "logic": """
        1. 价格 < VWAP 超过 5 分钟
        2. VWAP 斜率持续为负
        3. 无快速反弹迹象(5分钟内未站回)
        → 强制清仓
    """,
}
```

#### 8 层策略的执行优先级

```
Layer 1: 时间衰减     → 最早触发（买入后10-30分钟），最主动
Layer 2: 无量不涨     → 买入后持续监控（量是第一信号）
Layer 3: 反弹前高不过 → 关键价格位检测（600733红色箭头模式）
Layer 4: 冲高派发     → 利用已有 IntradayPatternDetector
Layer 5: 震荡不创高   → 结构性弱势
Layer 6: 量价背离     → 利用已有 decision_engine 检测
Layer 7: MA5d 回落    → 大级别守护（分时策略无法提供的）
Layer 8: VWAP 兜底    → 最后防线（不再是唯一策略）

优先级: 高 ──────────────────────────────────→ 低
        时间衰减 > 无量 > 前高不过 > 派发 > 震荡 > 背离 > MA5d > VWAP
```

---

### 模块③：MarketGuardian — 大盘/板块宏观守护

> **解决 "分时视角太小容易被诱骗" 的问题**

#### 文件位置
```
ats/market_guardian.py
```

#### 数据源（全部已有）

| 数据 | 来源模块 | 具体字段 |
|------|----------|----------|
| 大盘状态 | `MarketSentimentFSM` | `SentimentState` (PANIC/NEUTRAL/FOMO...) |
| 全局行情 | `MarketStateBus.df_all` | 所有个股实时数据 |
| 板块热力 | `SectorFocusEngine` | `sector_heat`, `board_score` |
| 涨跌停统计 | `df_all` 聚合 | `limit_up_count`, `limit_down_count` |
| 板块龙头 | `SignalLedger` / `capital_dragon_engine` | 龙头状态追踪 |

#### 守护规则

```python
class MarketGuardian:
    """
    大盘/板块宏观守护策略
    
    独立于交易策略运行，持续监控系统性风险
    触发时可越级直接向 TradingKernelService 发送清仓指令
    """
    
    RULES = {
        # 规则 1: 大盘急杀全仓止损
        "market_crash": {
            "name": "大盘急杀全仓止损",
            "logic": """
                从 df_all 实时聚合:
                - 下跌家数 > 上涨家数 * 3
                - 或 跌停数 > 20 且 涨停数 < 5
                - 或 MarketSentimentFSM 进入 PANIC 状态
                → 所有持仓立即清仓
            """,
            "data": "df_all 聚合 + MarketSentimentFSM.current_state",
            "action": "SELL_ALL_POSITIONS",
        },
        
        # 规则 2: 板块集中抛压
        "sector_dump": {
            "name": "板块集中抛压",
            "logic": """
                从 df_all 按板块分组:
                - 同一板块内 ≥ 3 只股票同时跌破 VWAP
                - 且板块龙头涨幅从日高回落 ≥ 3%
                → 该板块所有持仓清仓
            """,
            "data": "df_all.groupby('sector') + leader tracking",
            "action": "SELL_SECTOR_POSITIONS",
        },
        
        # 规则 3: 冻结买入（防守模式）
        "freeze_buy": {
            "name": "冻结买入信号",
            "logic": """
                市场转弱时冻结所有新买入信号:
                - 大盘跌幅 > 1%
                - 或涨停数骤降（比前一小时减少 50%）
                - 或 MarketSentimentFSM 为 COOLDOWN
                → 冻结 VWAPTradingEngine 的所有买入信号，只允许卖出
            """,
            "data": "MarketSentimentFSM + 涨停数实时统计",
            "action": "FREEZE_BUY_SIGNALS",
        },
        
        # 规则 4: 板块热度衰退
        "sector_cooldown": {
            "name": "板块热度衰退",
            "logic": """
                持仓股所属板块的 sector_heat 从高位（>70）
                快速降温到 <40
                → 减仓 50%
            """,
            "data": "SectorFocusEngine.sector_heat",
            "action": "REDUCE_HALF",
        },
    }
```

#### 与分时策略的协同方式

```python
class MarketGuardian:
    def evaluate(self, df_all: pd.DataFrame, sentiment: SentimentState) -> GuardianVerdict:
        """
        每个 Tick 周期调用，返回全局守护判定
        
        Returns:
            GuardianVerdict:
                buy_allowed: bool       # 是否允许买入
                sell_urgency: str       # "NONE" | "REDUCE" | "EXIT_ALL"
                affected_codes: list    # 受影响的持仓代码
                reason: str             # 原因说明
        """

# VWAPTradingEngine 在产生买入信号前必须检查:
def on_buy_signal(signal):
    verdict = market_guardian.evaluate(df_all, sentiment)
    if not verdict.buy_allowed:
        signal.reject(reason=verdict.reason)
        return
    # ... 正常处理
```

---

### 模块④：RuleEditorModel + RuleEditorWidget

#### 文件位置
```
ats/vwap_rule_model.py          # 规则数据模型
ats/ui/vwap_rule_editor.py      # Qt6 图形化编辑器
config/vwap_trading_rules.json  # 持久化配置
```

#### 规则 JSON 配置格式（支持盘中实时生效）

```json
{
  "version": "2.0",
  "hot_reload": true,
  "strategy_groups": {
    "aggressive": {
      "name": "激进组",
      "enabled": true,
      "buy_rules": [
        {
          "id": "buy_vwap_base_breakout",
          "name": "VWAP筑底突破",
          "enabled": true,
          "priority": 85,
          "conditions": [
            {"field": "price_vs_vwap", "op": "==", "value": "CROSSING_UP"},
            {"field": "consolidation_minutes", "op": ">=", "value": 10},
            {"field": "volume_ratio", "op": ">", "value": 1.1},
            {"field": "multi_period_score", "op": ">=", "value": 60}
          ],
          "action": {"type": "BUY_SCOUT", "size_pct": 0.15}
        }
      ],
      "exit_rules": ["exit_time_decay_fast", "exit_no_volume", "exit_failed_rally"]
    },
    "conservative": {
      "name": "保守组",
      "enabled": true,
      "buy_rules": [
        {
          "id": "buy_vwap_base_breakout_conservative",
          "name": "VWAP筑底突破(保守)",
          "conditions": [
            {"field": "consolidation_minutes", "op": ">=", "value": 20},
            {"field": "volume_ratio", "op": ">", "value": 1.5},
            {"field": "multi_period_score", "op": ">=", "value": 80}
          ],
          "action": {"type": "BUY_SCOUT", "size_pct": 0.08}
        }
      ],
      "exit_rules": ["exit_time_decay_strict", "exit_no_volume_strict", "exit_failed_rally"]
    }
  },
  "guardian_rules": {
    "always_on": true,
    "market_guardian": ["market_crash", "sector_dump", "freeze_buy"],
    "multi_tf_guard": ["exit_ma5d_rollover"]
  }
}
```

#### 盘中实时生效机制

```python
class RuleEditorModel:
    def __init__(self, config_path: str):
        self._config_path = config_path
        self._rules = self._load()
        self._file_watcher = QFileSystemWatcher()  # 监控配置文件变更
        self._file_watcher.fileChanged.connect(self._on_config_changed)
    
    def _on_config_changed(self, path: str):
        """配置文件变更 → 热加载 → 实时生效"""
        new_rules = self._load()
        if new_rules != self._rules:
            self._rules = new_rules
            self.rules_changed.emit(new_rules)  # 通知所有订阅者
    
    def update_rule_param(self, rule_id: str, param_name: str, value):
        """UI 滑块调参 → 立即写入配置 → 触发热加载 → 下一个 Tick 生效"""
```

---

### 模块⑤：IntradayVWAPBacktester — 分时级回测引擎

#### 文件位置
```
ats/vwap_backtest_engine.py
```

#### 数据源策略

```python
class IntradayVWAPBacktester:
    """
    数据源优先级:
    1. HDF5 本地分时数据 (sina_MultiIndex_data.h5 的 all_30)
    2. IPC 获取的 df_all 历史快照（如果有按时间戳存档的历史 df_all）
    3. pytdx 历史分时接口 (TdxHq_API.get_history_minute_time_data)
    
    回测模式:
    - 单日单股: 验证某个具体案例（如 600733 的 09-09 到 09-15）
    - 多日连续: 跨日VWAP上下文自动传递
    - 批量扫描: 多股多日并行回测，输出策略组对比报告
    """
    
    def run_backtest(self, code, dates, rules_config) -> BacktestResult:
        """
        核心回测流程:
        1. 加载历史分时数据
        2. 逐 Tick 回放（防未来函数）
        3. VWAPTradingEngine 产生信号
        4. ProactiveExitEngine 守护检测
        5. MarketGuardian 全局守护
        6. 记录所有买卖点坐标（用于 SBC 标注）
        7. 输出绩效报告
        """
```

#### 输出内容

```python
@dataclass
class BacktestResult:
    # 绩效指标
    total_trades: int
    win_rate: float
    profit_factor: float          # 盈亏比
    max_drawdown_pct: float
    sharpe_ratio: float
    
    # 买卖点坐标（用于 SBC 图形标注）
    signal_markers: list[SignalMarker]  # [{ts, price, type, rule_name}]
    
    # 策略组对比
    aggressive_pnl: float
    conservative_pnl: float
    
    # 各规则贡献度分析
    rule_attribution: dict[str, RuleAttribution]
    # 例如: "exit_failed_rally" 贡献了 +2.3% 收益（避免了亏损）
    #       "exit_time_decay" 避免了 5 笔深套
    
    # 权益曲线
    equity_curve: pd.Series
```

---

### 模块⑥：SignalAutoDispatcher — 信号→模拟交易调度器

#### 文件位置
```
ats/signal_auto_dispatcher.py
```

#### 工作模式（当前阶段：PAPER 模拟 + SBC 标记）

```python
class SignalAutoDispatcher:
    """
    信号自动调度器
    
    当前阶段: PAPER 模拟交易 + SBC 买卖点标记校准
    
    工作流:
    1. VWAPTradingEngine 产生买入信号
       → MarketGuardian 全局守护检查
       → 通过 → 封装为 StrategySignal
       → 投递到 TradingKernelService (PAPER 模式)
       → PaperAdapter 虚拟撮合
       → 注册到 ProactiveExitEngine 守护
       → SBC 标记买入点 ⬆
    
    2. ProactiveExitEngine 产生卖出信号
       → 封装为 StrategySignal (action=SELL)
       → 投递到 TradingKernelService
       → PaperAdapter 虚拟平仓
       → SBC 标记卖出点 ⬇
    
    3. 每日收盘后自动生成绩效报告
    """
    
    def __init__(self, kernel: TradingKernelService):
        self.kernel = kernel
        # 确保运行在 PAPER 模式
        assert kernel.trading_mode == "PAPER"
        
    def dispatch_buy(self, signal: VWAPSignal):
        """买入信号调度"""
        # 1. MarketGuardian 检查
        # 2. 冷却期检查（同一标的 120 秒内不重复）
        # 3. 多周期交叉验证
        # 4. 封装 StrategySignal 并投递
        
    def dispatch_exit(self, action: ExitAction):
        """出局信号调度"""
        # 1. 直接投递（出局不需要买入那么多检查）
        # 2. 记录出局原因和规则名称
```

---

### 模块⑦：SBC 买卖点图形标记

#### 增强文件
```
sbc_core.py              # +30行: 增加 signal_markers 数据通道
ats/ui/chart_widgets.py   # +100行: ScatterPlotItem 买卖点渲染
```

#### 标记渲染设计

```python
# SBC 分时图上的标记类型
MARKER_STYLES = {
    "BUY_SCOUT":     {"color": "#00FF88", "symbol": "t",  "size": 14, "label": "▲试探"},
    "BUY_ADD":       {"color": "#00CC66", "symbol": "t",  "size": 18, "label": "▲加仓"},
    "SELL_EXIT":     {"color": "#FF4444", "symbol": "t1", "size": 14, "label": "▼出局"},
    "SELL_STOP":     {"color": "#FFD700", "symbol": "d",  "size": 14, "label": "◆止损"},
    "SELL_GUARDIAN":  {"color": "#FF6600", "symbol": "s",  "size": 16, "label": "■守护"},
}

# 每个标记点附带 tooltip:
# "10:15 ▲试探 | VWAP筑底突破 | ¥48.66 | 信心:85%"
# "10:42 ▼出局 | 无量不涨(5m) | ¥48.30 | 亏损:-0.7%"
# "14:30 ■守护 | MA5d拐头向下 | ¥47.90 | 大级别破位"
```

---

## 四、数据流与接口对接（具体到函数级）

### VWAPTradingEngine 如何获取数据

```python
# 方式 1: 从 MarketStateBus 获取 df_all（全局预处理数据）
bus = MarketStateBus.get_instance()
result = bus.get_latest(since_version=last_version)
if result:
    version, df_all, df_filtered, timestamp = result
    for code in watched_codes:
        row = df_all.loc[code]
        tick_data = {
            "trade": row["trade"],
            "nclose": row["nclose"],          # 今日 VWAP
            "volume": row["volume"],
            "ratio": row["volume_ratio"],
            "ma5d": row["ma5d"],
            "ma10d": row["ma10d"],
            "high": row["high"],
            "low": row["low"],
            # ... 所有需要的字段都已在 df_all 中预计算好
        }
        engine.tick(code, tick_data, multi_period_ctx)

# 方式 2: 通过 IPC 桥接获取（适用于独立进程运行）
# 已有 ats/ipc_bridge.py 支持
```

### ProactiveExitEngine 如何与 DecisionEngine 协同

```python
# ProactiveExitEngine 不替换 DecisionEngine，而是并行守护
# DecisionEngine (已有) → 用于新信号的买入/卖出决策
# ProactiveExitEngine (新建) → 专门守护已持仓标的

# 协同方式:
class TradingCoordinator:
    """交易协调器 — 整合进攻端与防守端"""
    
    def on_tick(self, code, tick_data, df_all):
        # 1. 如果有持仓 → ProactiveExitEngine 优先检查
        if self.has_position(code):
            exit_action = self.exit_engine.evaluate(code, tick_data)
            if exit_action:
                self.dispatcher.dispatch_exit(exit_action)
                return  # 出局信号优先于买入信号
        
        # 2. MarketGuardian 全局检查
        guardian_verdict = self.market_guardian.evaluate(df_all)
        if not guardian_verdict.buy_allowed:
            return
        
        # 3. VWAPTradingEngine 检查买入信号
        buy_signals = self.vwap_engine.tick(code, tick_data)
        for signal in buy_signals:
            self.dispatcher.dispatch_buy(signal)
```

---

## 五、实施路线图（分 6 个阶段）

### Phase 0：基础框架搭建 ⏱ 1-2 天

```
目标: 搭建模块骨架与数据通道
─────────────────────────────────────
[新建] ats/vwap_trading_engine.py      # VWAPTickState + 空壳 Engine
[新建] ats/proactive_exit_engine.py    # 8 层策略空壳 + ExitAction 数据结构
[新建] ats/market_guardian.py          # GuardianVerdict + 空壳规则
[新建] ats/vwap_rule_model.py          # 规则 JSON 加载/序列化
[新建] config/vwap_trading_rules.json  # 默认规则配置文件

验证: 模块可以被 import，数据结构正确
```

### Phase 1：防守端优先实现 ⏱ 3-4 天

```
目标: 先实现 ProactiveExitEngine 的 8 层守护
原因: 你的核心痛点是"持仓后不知道什么时候出局"，而不是"不知道什么时候买入"
─────────────────────────────────────
实现顺序:
1. Layer 8: VWAP 破位兜底（最简单，复用 position_phase_engine.py 已有逻辑）
2. Layer 3: 反弹前高不过（600733 最典型的模式）
3. Layer 1: 时间衰减止损（解决"两天不及预期"）
4. Layer 2: 无量不涨（量是第一信号）
5. Layer 4: 冲高派发（复用 IntradayPatternDetector.high_drop）
6. Layer 5: 震荡不创高
7. Layer 6: 量价背离（复用 intraday_decision_engine 已有逻辑）
8. Layer 7: MA5d 回落（从 df_all 直接读取 ma5d/ma5d_prev5）

验证: 用 600733 的 5 天历史数据手动 replay
      预期: Layer 3（反弹前高不过）应在每个红色箭头位置触发
```

### Phase 2：大盘守护实现 ⏱ 2 天

```
目标: 实现 MarketGuardian 宏观守护
─────────────────────────────────────
实现:
1. 从 MarketStateBus.df_all 聚合涨跌家数、涨跌停数
2. 接入 MarketSentimentFSM 状态
3. 板块集中抛压检测（df_all.groupby('sector')）
4. 冻结买入信号机制

验证: 模拟大盘跳水场景，检查是否正确冻结买入并触发清仓
```

### Phase 3：进攻端 + SBC 标记 ⏱ 3-4 天

```
目标: VWAPTradingEngine 买入信号 + SBC 买卖点可视化标记
─────────────────────────────────────
实现:
1. VWAPTradingEngine 核心计算（VWAP 斜率、横盘检测、穿越判定）
2. 3 条买入规则引擎
3. sbc_core.py 增加 signal_markers 数据通道
4. chart_widgets.py 增加 ScatterPlotItem 标记渲染

验证: 在 SBC 分时图上看到:
      - 600733: 只有卖出标记（因为大趋势下行）
      - 301531: 底部出现买入标记，上方出现卖出标记
```

### Phase 4：调度器 + 回测引擎 ⏱ 3-4 天

```
目标: 打通 信号→PAPER交易→回测验证 全链路
─────────────────────────────────────
实现:
1. SignalAutoDispatcher 信号调度器
2. 对接 TradingKernelService (PAPER 模式)
3. IntradayVWAPBacktester 回测引擎
4. 激进组 vs 保守组并行回测对比

验证: 
- PAPER 模式下全天运行，检查买卖信号是否合理
- 用历史数据回测 600733 和 301531，输出绩效对比
- 预期: 301531 回测盈利，600733 回测快速止损（Layer 3 触发）
```

### Phase 5：图形化编辑器 + 调优 ⏱ 2-3 天

```
目标: 可视化规则编辑器 + 参数调优
─────────────────────────────────────
实现:
1. vwap_rule_editor.py Qt6 编辑器
2. 滑块实时调参 → 盘中生效（QFileSystemWatcher 热加载）
3. 一键回测按钮
4. 规则 JSON 导入/导出

验证: 调整参数后，SBC 上的买卖点标记实时变化
```

---

## 六、与现有模块的对接矩阵

### 不修改的模块（100% 兼容）

| 模块 | 接口 |
|------|------|
| `TradingKernelService` | 通过标准 `StrategySignal` 投递 |
| `RiskGate` / `KillSwitch` | 所有新信号必经风控 |
| `PaperAdapter` / `BrokerAdapter` | 执行层不变 |
| `MarketSentimentFSM` | 只读取状态，不修改 |
| `MarketStateBus` | 只订阅 df_all，不修改发布逻辑 |
| `IntradayPatternDetector` | 复用 high_drop 等已有检测 |

### 需要最小增强的模块

| 模块 | 修改 | 行数 |
|------|------|------|
| `signal_types.py` | 增加 `VWAP_BUY`/`VWAP_SELL`/`GUARDIAN_EXIT` 枚举 | +8行 |
| `signal_bus.py` | 增加 `VWAP_SIGNAL` / `GUARDIAN_SIGNAL` 事件类型 | +5行 |
| `sbc_core.py` | 增加 `signal_markers` 数据通道 | +30行 |
| `chart_widgets.py` | 增加买卖点 ScatterPlotItem 渲染 | +100行 |

### 全新模块清单

| 文件 | 估计行数 | 核心职责 |
|------|----------|----------|
| `ats/vwap_trading_engine.py` | ~600行 | 分时 VWAP 买入策略引擎 |
| `ats/proactive_exit_engine.py` | ~800行 | **8层主动出局引擎（核心）** |
| `ats/market_guardian.py` | ~400行 | 大盘/板块宏观守护 |
| `ats/vwap_rule_model.py` | ~300行 | 规则数据模型与热加载 |
| `ats/vwap_backtest_engine.py` | ~600行 | 分时级回测引擎 |
| `ats/signal_auto_dispatcher.py` | ~400行 | 信号→PAPER交易调度器 |
| `ats/ui/vwap_rule_editor.py` | ~600行 | 图形化规则编辑器 |
| `config/vwap_trading_rules.json` | ~250行 | 默认策略配置（激进+保守） |

---

## 七、关键设计决策确认

> [!IMPORTANT]
> **实施顺序确认**: 方案先做**防守端**（ProactiveExitEngine 8层守护），后做**进攻端**（VWAPTradingEngine 买入信号）。理由是你的核心痛点是"持仓后不知道什么时候出局"，买入信号反而是次要的。是否同意？

> [!IMPORTANT]
> **策略组运行方式**: 激进组和保守组同时运行时，是分别管理独立的虚拟仓位（各自有各自的持仓），还是共用一个仓位但用投票机制决策（两组都同意才执行）？

> [!WARNING]  
> **规则参数初始值**: 上面列出的各 Layer 参数（如时间衰减 10/20/30 分钟、无量阈值 50%、前高容差 0.5% 等）都是初始估计值，需要通过回测 Phase 4 进行校准。初期建议保守设置，避免过度止损。

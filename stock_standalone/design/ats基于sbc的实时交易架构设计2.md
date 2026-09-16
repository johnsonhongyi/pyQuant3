# 全自动分时多周期交易执行系统 v2.1 — 架构设计与实施方案

> **日期**: 2026-09-15 22:15  
> **版本**: v2.1 — 融入用户决策确认（防守优先 + 共用仓位投票决策）  
> **核心原则**: 
> 1. **防守端绝对优先**: 先做 ProactiveExitEngine（8层主动出局守护），后做 VWAPTradingEngine（进攻端买入）。
> 2. **共用仓位 + 双组投票决策**: 激进组与保守组共享单一仓位池；开仓必须**两组都同意（Dual Consent）**才执行；保守组定位于**开仓分时结构不清晰、多空犹豫期的辅助监管与一票否决**；出局采用**宽出机制（任一守护触发即出局）**。
> 3. **闭环验证**: 先接实盘模拟（PAPER）+ SBC 买卖点标记校准，严禁裸跑实盘。

---

## 一、用户交易教训与核心设计决策

### 1.1 真实交易教训反思（600733 北汽蓝谷 vs 301531 春光集团）

```
600733 致命痛点链:
  介入十字星 → 两天不及预期 → VWAP破位不舍得止损 → 反弹前高没走 → 亏损无底线放大
                                    ↑
                        根本原因：缺乏机械化主动离场机制！

301531 踏空痛点:
  48.66 底部打桩信号捕捉到 (99分) → 缺乏自动下单执行链 → 错失翻倍行情
```

### 1.2 核心设计决策（用户确认）

| 维度 | 原设计方案 | v2.1 确认方案 | 解决的核心问题 |
|------|-----------|--------------|----------------|
| **实施顺序** | 进攻买入与防守出局同步设计 | **先防守端（8层出局守护），后进攻端（买入引擎）** | 仓位在手时绝不能裸奔，首先解决"怎么跑" |
| **仓位模型** | 激进组与保守组各自分配独立仓位 | **共用一个仓位池（Shared Position Pool）** | 避免多策略分仓导致资金撕裂、逻辑冲突 |
| **开仓决策机制** | 独立触发买入 | **双组投票机制（两组都同意才执行开仓）** | 激进组抓分时动能，保守组专门在**分时结构不清晰、犹豫期**辅助监管行使否决权 |
| **出局决策机制** | 协商或破位止损 | **一票出局制（OR 逻辑）+ 8层主动守护** | 任何一层出局条件满足立即撤退，绝不犹豫 |
| **运行环境** | 直接准备实盘接口 | **PAPER 虚拟撮合 + SBC 图形化买卖点标记校准** | 所见即所得，验证调优后再无缝接入实盘 |

---

## 二、系统架构总览（共用仓位 + 三层守护）

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        全自动交易系统执行流水线 (Execution Pipeline)                    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  【宏观/板块守护层】 Layer 3: MarketGuardian                                            │
│  ┌────────────────────────────────────────────────────────────────────────┐            │
│  │ 数据源: MarketStateBus.df_all + MarketSentimentFSM                      │            │
│  │ 职责: 大盘暴跌全仓清仓 / 板块集中抛压全清 / 市场降温一键冻结买入        │            │
│  └────────────────────────────────────────────────────────────────────────┘            │
│           │ (全局风控指令)                                                             │
│           ▼                                                                            │
│  【持仓防守端 — 绝对优先】 Layer 1-A: ProactiveExitEngine (8层递进守护)                │
│  ┌────────────────────────────────────────────────────────────────────────┐            │
│  │ 触发即执行（无需投票，宽出原则，强制减仓/清仓）:                       │            │
│  │ L1 时间衰减 ──> L2 无量不涨 ──> L3 反弹前高不过 ──> L4 冲高派发        │            │
│  │ L5 震荡不创高 ─> L6 量价背离 ──> L7 大级别MA5d拐头 ─> L8 VWAP兜底      │            │
│  └────────────────────────────────────────────────────────────────────────┘            │
│           │ (若无持仓 / 持仓无需出局，才允许评估进攻端)                               │
│           ▼                                                                            │
│  【开仓进攻端 — 投票监管】 Layer 1-B: VWAPTradingEngine + ConsensusArbiter             │
│  ┌────────────────────────────────────────────────────────────────────────┐            │
│  │  ┌─────────────────────────┐          ┌─────────────────────────────┐  │            │
│  │  │   激进组 (Aggressive)   │          │ 保守组 (Conservative Guard) │  │            │
│  │  │  · VWAP筑底穿越突破     │          │ · 分时结构清晰度审查        │  │            │
│  │  │  · 分时动能量比爆发     │          │ · 犹豫期/混沌震荡一票否决   │  │            │
│  │  │  · 进攻提案: [PROPOSE]  │          │ · 辅助监管: [VETO / AGREE]  │  │            │
│  │  └────────────┬────────────┘          └──────────────┬──────────────┘  │            │
│  │               └───────────────────┬──────────────────┘                 │            │
│  │                                   ▼                                    │            │
│  │                       【投票仲裁器 ConsensusArbiter】                   │            │
│  │                 两组均同意 (Dual Consent) ──> 批准开仓                 │            │
│  │                 任一组犹豫/反对 ──────────────> 拦截丢弃               │            │
│  └───────────────────────────────────┬────────────────────────────────────┘            │
│                                      ▼                                                 │
│  【统一仓位与执行层】 TradingKernelService (PAPER 模拟模式)                            │
│  ┌────────────────────────────────────────────────────────────────────────┐            │
│  │ 统一标的仓位池: SharedPositionState                                    │            │
│  │ 虚拟撮合与滑点计算: PaperAdapter                                       │            │
│  │ SBC 分时图图形渲染: ScatterPlotItem 买卖点标记 (▲买入 / ▼出局 / ■守护) │            │
│  └────────────────────────────────────────────────────────────────────────┘            │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、七大核心模块详细设计

---

### 模块①：ProactiveExitEngine — 主动出局引擎（防守端核心）

> **优先实施的第一核心**：彻底解决“买入后不及预期、VWAP破位不舍得止损、反弹没走”的致命心魔。

#### 文件位置
```
ats/proactive_exit_engine.py
```

#### 数据结构与动作定义
```python
@dataclass
class ExitAction:
    code: str
    rule_id: str             # 触发的规则 ID（例如 'exit_failed_rally'）
    rule_name: str           # 规则中文名（如 '反弹前高不过'）
    layer: int               # 1~8 层级
    action_type: str         # "REDUCE_HALF" | "REDUCE_30" | "EXIT_ALL"
    trigger_price: float     # 触发价格
    reason: str              # 详细说明（可解释性）
    timestamp: datetime
```

#### 8 层递进式主动离场策略详细规格

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                        ProactiveExitEngine 8 层防御阵列                        │
├───────┬──────────────────┬──────────────┬──────────────────┬───────────────────┤
│ 层级  │ 守护规则名称     │ 触发时效     │ 针对的痛点场景   │ 动作力度          │
├───────┼──────────────────┼──────────────┼──────────────────┼───────────────────┤
│ **L1**│ 时间衰减止损     │ 买后10~30分钟│ 买入无反应、死水 │ 20m减半/30m清仓   │
│ **L2**│ 无量不涨止损     │ 买后持续     │ 缩量盘跌、散户坑 │ 持续缩量则减半清仓│
│ **L3**│ 反弹前高不过     │ 冲高遇阻时刻 │ 600733反复被割点 │ 遇阻不过立即减/清 │
│ **L4**│ 冲高派发识别     │ 快速冲高回落 │ 诱多出货、长上影 │ 锁定浮盈或亏损清仓│
│ **L5**│ 震荡不创高       │ 30分钟窗口   │ 高点下移、多头散 │ 减仓30%→再破清仓  │
│ **L6**│ 量价背离出局     │ 创新高时刻   │ 顶背离、量能枯竭 │ 减半仓锁定利润    │
│ **L7**│ 大级别MA5d拐头   │ 日内/跨日    │ 60分通道破位大势 │ 反弹分时均线即清仓│
│ **L8**│ VWAP破位最后防线 │ 持续5分钟    │ 终极兜底（非唯一）│ 强行100%清仓      │
└───────┴──────────────────┴──────────────┴──────────────────┴───────────────────┘
```

##### Layer 1：时间衰减止损（Time Decay Stop）
- **痛点**: 买入十字星后，连续横盘或阴跌两天不及预期，一直拖延。
- **逻辑**: 
  - 买入后 $T \ge 10\text{min}$，涨幅 $< 0.3\%$：发出预警（黄色状态）。
  - $T \ge 20\text{min}$，涨幅 $< 0.3\%$：机械执行**减半仓**。
  - $T \ge 30\text{min}$ 且处于浮亏状态：**立即清仓**。
  - 特殊豁免：若处于窄幅横盘洗盘且振幅 $<0.5\%$、大盘情绪良好，允许顺延至 $45\text{min}$。

##### Layer 2：无量不涨止损（Volume Absence Stop）
- **痛点**: 买入后成交量急剧萎缩，主力根本没有拉升意愿。
- **逻辑**:
  - 滑动计算：最近 5 分钟成交量 $< 15$ 分钟均量的 $50\%$，且价格涨幅 $< 0.2\%$。
  - 持续 3 个窗口（约 3 分钟）未改善：减半仓。
  - 持续 5 个窗口：立即清仓。

##### Layer 3：反弹前高不过止损（Failed Rally Stop，600733 关键克星）
- **痛点**: 价格回落后反弹，正好打到前日高点、日内分时高点或昨日 VWAP，看似要突破，实际是主力诱多派发，随后急跌。
- **逻辑**:
  1. 识别参考高点：`prev_day_high`、`intraday_high`、`vwap_yesterday`。
  2. 当价格回升至前高 $\pm 0.5\%$ 阻力区，停留 $\ge 3\text{min}$ 且无法带量突破（突破幅度 $< 0.5\%$，量比 $< 0.8$）：**判定为“反弹不过”，立即主动出局 50%**。
  3. 一旦从阻力位回落超过 $1.5\%$：**确认反弹彻底失败，100% 清仓出局**。

##### Layer 4：冲高派发识别（Distribution Detection）
- **逻辑**: 复用 `IntradayPatternDetector.high_drop` 与 `decision_engine.evaluate_trap_veto`。
  - 日内冲高幅度 $>3\%$ 但较日内最高点回撤 $>2\%$；或分时爆量（量比 $>2.0$）却收阴线下挫。
  - 处于浮盈时：保护利润至少减半；处于浮亏时：立即清仓。

##### Layer 5：震荡不创高（Oscillation No New High）
- **逻辑**: 统计最近 30 分钟的分时局部波峰序列，若波峰序列连续 3 次下移（Lower Highs），且 VWAP 斜率 $\le 0$，判定为阴跌结构，减仓 30%，若随后跌破波谷则全清。

##### Layer 6：量价背离（Volume-Price Divergence）
- **逻辑**: 复用 `IntradayDecisionEngine._eval_volume_divergence()`，价格创新高但成交量萎缩、DFF 资金流向差下挫（$<-0.5$），执行止盈减半。

##### Layer 7：大级别 MA5d 拐头（Multi-Timeframe Rollover）
- **痛点**: 分时策略视角过窄，日线/60分钟 MA5 已拐头向下破位，分时反弹只是下跌中继。
- **逻辑**: 读取 `df_all['ma5d']` 与 `df_all['ma5d_prev5']`，若 `ma5d < ma5d_prev5 * 0.998` 且 60 分钟通道斜率 $<-5^\circ$：
  - 任何分时反抽到分时 VWAP 附近时，**直接卖出，不等突破**。

##### Layer 8：VWAP 破位兜底（Final Safety Net）
- **逻辑**: 价格低于今日 VWAP 超过 5 分钟，且 5 分钟内无法快速放量站回，作为最后一道防线强制 100% 清仓。

---

### 模块②：VWAPTradingEngine — 分时均价交易策略引擎（进攻端）

#### 文件位置
```
ats/vwap_trading_engine.py
```

#### 核心状态计算
```python
@dataclass
class VWAPTickState:
    code: str
    price: float
    vwap_today: float               # 今日分时均价 (nclose)
    vwap_yesterday: float           # 昨日分时均价 (last_nclose)
    vwap_cum_5d: float              # 5日累计均价
    vwap_slope_5m: float            # 5分钟均价斜率
    vwap_direction: str             # "UP" | "FLAT" | "DOWN"
    
    price_vs_vwap: str              # "ABOVE" | "BELOW" | "CROSSING_UP"
    minutes_above_vwap: int         # 站上均价分钟数
    consolidation_minutes: int      # 横盘整理分钟数
    consolidation_range_pct: float  # 横盘振幅 (%)
    volume_ratio: float             # 量比
    
    # 结构清晰度指标（供保守组监管审查）
    structure_clarity_score: float  # 0~100 (形态规则度)
    is_hesitation_zone: bool        # 是否处于多空犹豫期
```

#### 进攻买入规则提取
1. **VWAP 筑底放量突破（301531 式）**:
   - 价格从下向上穿越今日 VWAP (`CROSSING_UP`)。
   - 此前低位横盘 $\ge 15$ 分钟，振幅 $< 1.0\%$。
   - 突破时量比 $> 1.2$，VWAP 停止下移（走平或拐头向上）。
   - 多周期通道评分 $\ge 70$ 分。
2. **站稳 VWAP 回踩确认加仓**:
   - 价格站上 VWAP $\ge 10$ 分钟，回踩 VWAP 不破且量能承接健康。
3. **低开走高站上 VWAP**:
   - 结合已有 `IntradayPatternDetector.low_open_high_walk` 事件。

---

### 模块③：ConsensusArbiter — 双组投票与辅助监管机制（核心机制）

> **用户关键确认**: 激进组与保守组**共用一个仓位**，采用**投票机制决策（两组都同意才执行开仓）**。保守组充当分时结构不清晰、犹豫期的**辅助监管者与一票否决权行使者**。

#### 文件位置
```
ats/consensus_arbiter.py
```

#### 投票决策矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ConsensusArbiter 投票与准入决策矩阵                     │
├──────────────┬──────────────────┬──────────────────┬────────────────────────┤
│ 动作类型     │ 激进组提案       │ 保守组辅助监管   │ 最终仲裁裁决           │
├──────────────┼──────────────────┼──────────────────┼────────────────────────┤
│ **开仓买入** │ APPROVE (发现动能)│ APPROVE (结构清晰)│ ✅ **EXECUTE** (批准开仓)│
│ **开仓买入** │ APPROVE (发现动能)│ VETO (结构混乱)  │ ❌ **REJECT** (一票否决) │
│ **开仓买入** │ APPROVE (发现动能)│ HESITATE (犹豫期)│ ⏸️ **STANDBY** (保持观望)│
│ **开仓买入** │ REJECT (无信号)  │ ANY              │ ❌ **IGNORE** (不执行)   │
├──────────────┼──────────────────┼──────────────────┼────────────────────────┤
│ **出局平仓** │ EXIT 触发        │ ANY              │ 🚨 **FAST_EXIT** (秒平) │
│ **出局平仓** │ ANY              │ EXIT 触发        │ 🚨 **FAST_EXIT** (秒平) │
│ **出局平仓** │ 8层防御阵列触发  │ ANY              │ 🚨 **FORCE_EXIT** (强制)│
└──────────────┴──────────────────┴──────────────────┴────────────────────────┘
```

#### 仲裁器核心逻辑代码规范

```python
class ConsensusArbiter:
    """
    共识仲裁器:
    1. 管理单一共享仓位池 (SharedPositionState)
    2. 开仓: 必须激进组与保守组双重同意 (Dual Consent)
    3. 保守组: 专职监控分时结构是否明晰、是否存在多空犹豫，行使一票否决
    4. 出局: 宽出机制 (任一触发立即执行)
    """
    
    def __init__(self, position_state: SharedPositionState):
        self.pos = position_state
        
    def arbitrate_buy(
        self, 
        code: str, 
        agg_vote: VoteResult, 
        con_vote: VoteResult
    ) -> ArbiterDecision:
        # 1. 激进组必须有买入意愿
        if not agg_vote.is_buy:
            return ArbiterDecision(allow=False, reason="激进组未触发买点")
            
        # 2. 保守组辅助监管审查（核心！）
        # 如果分时处于结构不清晰、多空博弈犹豫期，保守组予以否决
        if con_vote.is_hesitating:
            return ArbiterDecision(
                allow=False, 
                reason=f"保守组监管否决: 分时处于犹豫期({con_vote.hesitation_reason})"
            )
            
        if not con_vote.structure_is_clear:
            return ArbiterDecision(
                allow=False, 
                reason=f"保守组监管否决: 分时结构混乱/杂波过多(清晰度:{con_vote.clarity_score}<70)"
            )
            
        if not con_vote.is_buy:
            return ArbiterDecision(
                allow=False, 
                reason=f"保守组不同意开仓: {con_vote.reject_reason}"
            )
            
        # 3. 两组均同意，批准开仓
        final_size = min(agg_vote.proposed_size, con_vote.allowed_size)
        return ArbiterDecision(
            allow=True, 
            action="BUY_SCOUT", 
            size_pct=final_size,
            reason="激进与保守双组共识通过 (动能成立 + 结构清晰)"
        )

    def arbitrate_exit(
        self, 
        code: str, 
        exit_action: Optional[ExitAction],
        agg_exit: bool,
        con_exit: bool
    ) -> ArbiterDecision:
        # 出局执行 OR 逻辑：任何一方认为有风险，立刻出局！
        if exit_action is not None:
            return ArbiterDecision(allow=True, action=exit_action.action_type, reason=f"8层防守守护触发: {exit_action.rule_name}")
        if con_exit or agg_exit:
            return ArbiterDecision(allow=True, action="EXIT_ALL", reason="策略组发出主动避险指令")
        return ArbiterDecision(allow=False, reason="无出场信号")
```

#### 保守组辅助监管的三大审查条件
1. **分时结构清晰度 (Structure Clarity $\ge 70$)**:
   - 均价线 VWAP 必须具有明确的指向性（平稳或向上，严禁上下锯齿剧烈震荡）。
   - 价格围绕均价线波动幅度收敛，没有异常单笔无量打压或拉抬。
2. **拒绝犹豫期 (Non-Hesitation)**:
   - 连续 10 根 1 分钟 K 线中，十字星比例不得超过 40%。
   - 价格横盘振幅处于明确的窄幅整理，而非多空激烈反复撕扯的“拉锯期”。
3. **真实放量验证 (Volume Confirmation)**:
   - 突破动作必须伴随真实的买盘成交，且资金流向指标 DFF 不能处于加速出逃状态。

---

### 模块④：MarketGuardian — 大盘/板块宏观守护

#### 文件位置
```
ats/market_guardian.py
```
#### 四大全局熔断规则
1. **大盘急杀全仓止损 (`market_crash`)**: 下跌家数 $> 3 \times$ 上涨家数，或跌停家数 $>20$ 且涨停 $<5$，或 `MarketSentimentFSM` 进入 `PANIC` 状态 $\rightarrow$ 所有标的立即清仓。
2. **板块集中抛压 (`sector_dump`)**: 同一板块内 $\ge 3$ 只股票跌破 VWAP 且龙头跳水 $\rightarrow$ 清仓该板块持仓。
3. **冻结买入信号 (`freeze_buy`)**: 市场弱势时，即使个股出现买点，一律冻结买入。
4. **板块退潮降温 (`sector_cooldown`)**: 行业热度从高位急跌时，自动对持仓减半避险。

---

### 模块⑤：SignalAutoDispatcher — 统一信号调度器

#### 文件位置
```
ats/signal_auto_dispatcher.py
```
#### 工作流与模式保证
- **阶段模式**: 严格锁定在 `PAPER`（模拟交易）模式，绝不直连实盘资金。
- **调度次序**:
  1. 接收行情 Tick $\rightarrow$ 先派发至 `ProactiveExitEngine` 与 `MarketGuardian`。
  2. 若产生出局动作 $\rightarrow$ 绕过所有限制，秒级推入 `PaperAdapter` 虚拟平仓，记录离场原因。
  3. 若无出局需求 $\rightarrow$ 派发至 `VWAPTradingEngine` 与 `ConsensusArbiter` 进行双组投票。
  4. 投票通过 $\rightarrow$ 推送至 `TradingKernelService` 执行虚拟开仓。
  5. 将所有买入、加仓、减仓、清仓事件打包推送至 SBC 图形标记通道。

---

### 模块⑥：SBC 图形标记与所见即所得系统

#### 增强文件
- `sbc_core.py`: 增加 `signal_markers` 内存数据总线（+30行）。
- `ats/ui/chart_widgets.py`: 增加 `ScatterPlotItem` 图元渲染（+100行，复用对象池，不频繁 add/remove）。

#### 视觉呈现标记
- `▲ 试探买入` (浅绿色，双组投票共识通过，附 Tooltip: 规则名、量比、评分)。
- `▲ 站稳加仓` (深绿色，回踩确认)。
- `▼ 主动出局` (橙红色，L1-L7主动出局规则触发，附 Tooltip: 如"反弹前高不过 -0.4%")。
- `◆ VWAP兜底` (金色，L8最后防线触发)。
- `■ 宏观守护` (深紫色，大盘或板块抛压熔断)。

---

### 模块⑦：RuleEditorModel + UI 图形编辑器（盘中热加载）

#### 文件位置
- `ats/vwap_rule_model.py`: 规则 JSON 解析模型与校验。
- `ats/ui/vwap_rule_editor.py`: Qt6 滑块调参界面。
- `config/vwap_trading_rules.json`: 持久化策略规则配置。

#### 热加载保证
- 使用 `QFileSystemWatcher` 监听配置文件。
- 用户在 UI 上拖动滑块（如将前高容差从 $0.5\%$ 改为 $0.8\%$） $\rightarrow$ 毫秒级写盘 $\rightarrow$ 信号引擎下一个 Tick 自动重载生效，无需重启软件。

---

## 四、实施路线图（分阶段循序渐进）

```
阶段路线:
Phase 0 [基础骨架] ──> Phase 1 [防守端 8层守护] ──> Phase 2 [宏观大盘哨兵]
                                                            │
Phase 5 [UI热加载调优] <── Phase 4 [调度+回测+SBC] <── Phase 3 [进攻端+双组投票]
```

### Phase 0：基础骨架与协议定义 ⏱ 1~2 天
- **目标**: 构建模块结构与数据流通协议，不写具体复杂算法。
- **新增文件**:
  - `ats/proactive_exit_engine.py` (ExitAction + 8层策略空壳接口)
  - `ats/vwap_trading_engine.py` (VWAPTickState + 进攻策略空壳)
  - `ats/consensus_arbiter.py` (SharedPositionState + VoteResult + ConsensusArbiter)
  - `ats/market_guardian.py` (GuardianVerdict 空壳)
  - `config/vwap_trading_rules.json` (默认激进/保守规则参数)
- **验收标准**: 所有新增模块可正常 `import`，单元测试中数据协议流转无报错。

### Phase 1：防守端（ProactiveExitEngine 8层主动出局）优先攻坚 ⏱ 3~4 天
- **目标**: 先建好护城河！完整实现 8 层主动离场与减仓机制。
- **执行次序**:
  1. **Layer 8**: VWAP 破位兜底（复用 `position_phase_engine.py` 逻辑）。
  2. **Layer 3**: 反弹前高不过（专门针对 600733 红色箭头阻力回落）。
  3. **Layer 1**: 时间衰减止损（买入 10/20/30 分钟不涨出局）。
  4. **Layer 2**: 无量不涨止损（缩量盘跌减半清仓）。
  5. **Layer 4**: 冲高派发（复用 `IntradayPatternDetector.high_drop`）。
  6. **Layer 5**: 震荡不创高（波峰序列连续下移检测）。
  7. **Layer 6**: 量价背离出局（复用 `decision_engine` 背离算法）。
  8. **Layer 7**: 大级别 MA5d 拐头（跨周期均线与 60 分钟通道下倾判定）。
- **回测验证**:
  - 导入 600733 真实历史分时数据回放。
  - **预期表现**: 在十字星介入后的反弹高点（Layer 3）和无量滞涨（Layer 1/2）即刻被机械出局，亏损控制在 $-1\%$ 到 $+0.5\%$ 之间，彻底避免深度被套。

### Phase 2：大盘与板块宏观守护（MarketGuardian） ⏱ 2 天
- **目标**: 系统性风险拦截与板块共振出逃。
- **实施内容**:
  1. 聚合 `MarketStateBus.df_all` 的全市场涨跌统计。
  2. 接入 `MarketSentimentFSM` 情绪状态机。
  3. 实现板块集中抛压检测与买入一键冻结。
- **验证**: 注入模拟大盘跳水数据，验证是否 100% 拦截开仓并对模拟持仓发出出局信号。

### Phase 3：进攻端 + 激进/保守双组投票机制 ⏱ 3~4 天
- **目标**: 实现买入信号捕获与共用仓位投票仲裁。
- **实施内容**:
  1. `VWAPTradingEngine`: VWAP 斜率、突破穿越、横盘筑底计算。
  2. `ConsensusArbiter`: 激进组提报动能买点，保守组审查分时结构清晰度与犹豫期。
  3. 编写双组投票决策与一票否决逻辑。
- **验证**:
  - 301531 案例：底部横盘形态规整、分时结构极度清晰，激进与保守组一致投出赞成票，成功在 48.66 发出买入信号。
  - 混沌杂乱震荡股：激进组出现微弱突破信号，但保守组判定处于犹豫期，成功行使 VETO 否决，拦截虚假开仓。

### Phase 4：调度器 + 回测引擎 + SBC 图形标记 ⏱ 3~4 天
- **目标**: 闭环运行，实现所见即所得。
- **实施内容**:
  1. `SignalAutoDispatcher`: 串联数据、策略、仲裁与 PAPER 撮合。
  2. `sbc_core.py` 与 `chart_widgets.py`: 绘制买卖点图形标记。
  3. `ats/vwap_backtest_engine.py`: 分时逐 Tick 回测引擎，输出交易清单与盈亏比。
- **验证**:
  - SBC 分时图上直观看到 301531 的买卖标记、600733 的快速出局标记。
  - 回测报告输出规则贡献度（如 Layer 3 避免了多少回撤）。

### Phase 5：Qt6 规则编辑器与盘中热加载 ⏱ 2~3 天
- **目标**: 可视化直观调参。
- **实施内容**:
  1. 构建 `ats/ui/vwap_rule_editor.py` 滑块配置界面。
  2. 对接 `QFileSystemWatcher`，实现参数盘中秒级热加载生效。

---

## 五、与既有工程对接矩阵（零破坏兼容）

| 现有核心模块 | 对接方式 | 修改幅度 |
|-------------|----------|----------|
| `MarketStateBus` | 只订阅 `get_latest()` 获取 `df_all`，不修改总线发布逻辑 | 0 行 |
| `TradingKernelService` | 运行在 `PAPER` 模式，通过标准接口投递 `StrategySignal` | 0 行 |
| `PaperAdapter` | 直接接收虚拟订单进行撮合，管理统一虚拟账户 | 0 行 |
| `IntradayPatternDetector` | 直接调用其形态判断函数（如 `high_drop`） | 0 行 |
| `signal_types.py` | 扩展 `VWAP_BUY` / `VWAP_SELL` / `GUARDIAN_EXIT` 信号标识 | +8 行 |
| `sbc_core.py` | 增加分时标记数据传递槽函数 | +30 行 |
| `chart_widgets.py` | 增加买卖点 Scatter 图元绘制（复用图元池） | +100 行 |

---

## 六、阶段交付物与总结

本设计方案严格落实了用户的核心诉求：
1. **防守走在最前面**：以 8 层防御阵列为主轴的 `ProactiveExitEngine` 优先攻坚，确保持仓任何时候都有机械退路。
2. **共用仓位 + 投票把关**：激进组负责进攻敏感度，保守组专职在分时结构不明、犹豫期行使监管否决，两组都同意才开仓，开仓严、平仓快。
3. **安全稳健**：全流程先在 PAPER 模拟与 SBC 图元标记下回测校准，不进行盲目实盘操作，与既有架构 100% 兼容无缝对接。

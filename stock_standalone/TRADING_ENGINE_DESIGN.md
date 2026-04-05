# 盘中实时交易决策引擎 — 设计文档

> 版本：v2.0（2026-04-06）  
> 状态：✅ 已实现，数据链全通，随时可进入实盘模拟验证  
> 持续迭代：P3 盘中参数微调 → P4 全自动执行升级

---

## 一、设计目标

> **从"分析明天"转型为"交易今天"**
>
> 不是分析一大堆数据幻想明天的涨跌，而是捕捉当天强势股回踩、板块异动、热点持续、龙头带头的**直接交易机会**。
> 去弱留强，资金高效运转，频繁高频交易，持续盈利。

---

## 二、交易规则配置

| 规则 | 参数 | 说明 |
|------|------|------|
| 交易模式 | 模拟下单 | 记录至 `signal_strategy.db`，不实际下单 |
| 同板块持仓 | 最多 3 只 | 龙头 + 2 跟随 |
| 最大总持仓 | 10 只 | `MAX_POSITIONS = 10` |
| 单笔仓位 | 5% | `POSITION_SIZE_PCT = 0.05` |
| 日亏损上限 | 2% | 触发全场止损清仓 |
| 个股止损线 | -2% | `STOP_LOSS_PCT = -0.02` |

---

## 三、引擎架构（五层）

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: 数据接入                                               │
│  BiddingMomentumDetector ← df_all（每次实时推送）               │
│  └─ 个股评分：score / pct_diff / dff / klines / vwap           │
│  └─ 板块聚合：board_score / score_diff / follow_ratio           │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 每30秒 inject_from_detector()
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: 板块热力图（SectorFocusMap）                           │
│  └─ 优先通道：inject_detector_sectors() → SectorHeat           │
│  └─ 降级通道：df_realtime 聚合（detector无数据时）              │
│  └─ 附加数据：55188 主力净占比 / 人气排名                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 龙头识别（StarFollowEngine）                           │
│  └─ 三重确认：涨幅≥5% + board_score≥3.0 + 人气排名≤200        │
│  └─ 每板块 Top1 = 龙头，Top2~4 = 跟随候选                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: 买点检测（IntradayPullbackDetector）                   │
│  └─ 形态1: 飞刀接落 — 回踩≥1.5%+均线+缩量              P60+   │
│  └─ 形态2: VWAP支撑 — 均线±0.3%+量放大+龙头确认        P55+   │
│  └─ 形态3: 板块共振 — 龙头确认+跟进股上翘+周期正涨幅   P70+   │
│  └─ 形态4: 强势跟进 — 蓄势/强攻板块+dff正向+pct_diff>0.3 P65+ │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: 决策队列 → 交易网关（DecisionQueue + TradeGateway）   │
│  └─ 优先级排序，最多50个信号                                    │
│  └─ RiskManager：仓位/日损/止损三重守护                         │
│  └─ MockTradeGateway → signal_strategy.db 记录                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、离场条件（ExitMonitor）

| 条件 | 触发规则 | 掩码 |
|------|----------|------|
| 龙头杀跌 | 所属板块龙头从日高回落 ≥ 2% | `LEADER_CRASH` |
| 个股不创新高 | 14:00后价格未超前高点（留0.2%容差） | `NO_NEW_DAY_HIGH` |
| 尾盘破均价 | 14:30后收盘价跌破VWAP（留0.2%容差） | `VWAP_BREAK_CLOSE` |
| 日亏损上限 | 当日组合亏损 ≥ 2% | `DAILY_LOSS_LIMIT` |

> **v2 改进**：龙头跌幅现在直接从 detector 快照精确计算（`l_price / l_high - 1`），而非以前的粗估。

---

## 五、关键接口

### 5.1 inject_from_detector(detector)  ← 核心入口
```python
# instock_MonitorTK.py 每30秒调用一次
_sbp = getattr(self, 'sector_bidding_panel', None)
_detector = getattr(_sbp, 'detector', None) if _sbp else None
if _detector is not None:
    fc.inject_from_detector(_detector)
```

**注入内容**：
1. `comparison_interval` 强制同步为 60 分钟
2. `active_sectors` → `inject_detector_sectors()` → `SectorHeat`（含完整klines/pct_diff/dff）
3. `_global_snap_cache` → 所有个股快照
4. `_tick_series[code].score` → 竞价评分（兼容旧接口）

### 5.2 get_hot_sectors(top_n=10) ← UI查询
```python
fc = get_focus_controller()
sectors = fc.get_hot_sectors(10)  # List[dict]
# 每个 dict 包含：name/heat_score/bidding_score/leader_code/leader_pct/
#                  leader_pct_diff/leader_dff/score_diff/follower_codes
#                  follower_detail/sector_type/tags
```

### 5.3 get_decision_queue() ← 决策信号列表
```python
signals = fc.get_decision_queue()  # List[dict]
# 每个 dict 包含：code/name/sector/signal_type/priority/
#                  suggest_price/change_pct/pct_diff/dff/
#                  sector_heat/sector_type/reason/leader_code
```

---

## 六、数据一致性保障

### 统计周期（comparison_interval）的一致性
```
BiddingMomentumDetector.comparison_interval = 3600 (60分钟，默认值)
    ├─ 个股锚点重置：price_anchor / pct_diff (切片涨幅)
    ├─ 板块锚点重置：sector_anchors[sector] / score_diff
    └─ inject_from_detector() 注入时再次确认此值 ≥ 3600
```

所有 `pct_diff`（个股）和 `score_diff`（板块）均使用**同一个基准时钟**，60分钟统一重置，UI和引擎完全同步。

### 数据来源优先级（SectorFocusMap）
```
优先级 A > 优先级 B
A: inject_detector_sectors() ← 来自 BiddingMomentumDetector（已计算好的权威数据）
B: update(df_realtime)       ← 来自 df_all 聚合（降级通道，detector 无数据时启用）
```

---

## 七、UI 展示对接

### stock_selection_window.py 新增面板

#### 板块聚焦面板（Tab: 板块聚焦）
| 列 | 字段 | 说明 |
|----|------|------|
| 板块名 | `name` | 板块题材名称 |
| 热度 | `heat_score` | 0~100 综合热力 |
| 板分 | `bidding_score` | board_score 原始值 |
| 强度变化 | `score_diff` | 60m内强度趋势（+增强/-减弱） |
| 类型 | `sector_type` | 🔥强攻/♨️蓄势/🔄反转/📈跟随 |
| 龙头 | `leader_code + leader_name` | |
| 龙头涨幅 | `leader_change_pct` | 当日涨幅 |
| 龙头周期 | `leader_pct_diff` | 60m内变化 |
| 龙头dff | `leader_dff` | 量价信号 |
| 跟随 | `follow_ratio` | 板块跟涨比例 |

#### 决策队列面板（Tab: 决策队列）
| 列 | 字段 | 说明 |
|----|------|------|
| 优先级 | `priority` | 1~100 |
| 代码 | `code` | |
| 名称 | `name` | |
| 信号类型 | `signal_type` | 飞刀接落/VWAP支撑/板块共振/强势跟进 |
| 板块 | `sector` | |
| 当前价 | `current_price` | |
| 建议价 | `suggest_price` | 略高于VWAP |
| 涨幅 | `change_pct` | |
| 周期涨幅 | `pct_diff` | |
| dff | `dff` | |
| 理由 | `reason` | |
| 状态 | `status` | 待处理/已提交/已成交/已忽略 |

---

## 八、待实施计划（优先级排序）

### P1 — 盘中验证与参数微调（下一步）
- [ ] 实盘模拟观察 `DecisionQueue` 信号生成频率（目标：每小时5~15个有效信号）
- [ ] 调整 `IntradayPullbackDetector.MIN_DROP_FROM_HIGH`（当前-1.5%，可根据实盘反馈调到-2%）
- [ ] 调整 `MIN_SECTOR_HEAT`（当前25.0，可测试 20.0 看信号密度）
- [ ] 调整 `LEADER_MIN_ZT_OR_PCT`（当前5.0%，可测试4.5%~6%区间）

### P2 — 板块统计周期参数化
- [ ] 在竞价面板 UI 上同步显示 60m 窗口倒计时（距下次锚点重置剩余时间）
- [ ] 支持用户在决策引擎独立配置 comparison_interval（与面板解耦）

### P3 — 全自动执行升级
- [ ] 将 `MockTradeGateway` 替换为实盘接口（券商API/QMT）
- [ ] 添加确认弹窗模式（"人机协同"，AI提议 → 用户一键确认）
- [ ] 自动跟踪已成交订单的持仓状态与PnL

### P4 — 55188 题材时效性增强
- [ ] `scraper_55188` 解析题材发酵日期，计算"题材新鲜度"
- [ ] 题材年龄 < 7天 → 板块热力加权 +20%
- [ ] 在板块聚焦面板显示题材发现时间与关联度

### P5 — 竞价阶段专项优化（9:15~9:30）
- [ ] `inject_bidding()`：在竞价阶段（9:20~9:25）专项提权，让竞价评分权重从35%升至60%
- [ ] 竞价龙头确认：竞价评分Top10 + 主力净流入 → 提前锁定主战场板块
- [ ] 竞价面板 → 开盘前自动生成"主战场板块Top5"报告

---

## 九、已知问题与注意事项

### ⚠️ 竞价面板未开启时
- `sector_bidding_panel` 不存在 → `inject_from_detector` 自动降级到 `df_realtime` 聚合
- 降级通道热力计算精度低于优先通道，但不影响系统稳定性

### ⚠️ 非交易时间行为
- `comparison_interval` 锚点**不会在非交易时间自动重置**（`is_active_session()` 守卫）
- 盘后展示的数据为收盘时最后一次计算结果，数值冻结直到下一个交易日

### ⚠️ 日初清理
- `_aggregate_sectors()` 在交易日 9:15 过后检测到日期变更时，自动清理前日评分/板块/龙头缓存
- 清理将重置所有 `TickSeries.score/momentum_score/pattern_hint`

---

## 十、版本变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-05 | v1.0 | 初始架构：SectorFocusController + MockTradeGateway |
| 2026-04-05 | v1.5 | 数据流打通：inject_from_detector 雏形 |
| 2026-04-06 | v2.0 | **完整重写**：inject_from_detector / inject_detector_sectors / _scan_one_v2 / 形态4 / 默认60m |

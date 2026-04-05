# 全能交易终端 — 系统架构设计文档

> 版本：v3.0（2026-04-06）  
> 维护者：Gemini AI + Johnson  
> 本文档为**持续更新的活文档**，每次重大架构变更时同步更新。

---

## 一、系统总览

```
╔══════════════════════════════════════════════════════════════════╗
║           pyQuant3 全能交易终端 — 五层架构                        ║
╠══════════════════════════════════════════════════════════════════╣
║  [L5] 外部数据层    55188主力/题材/人气 + TDX日线数据             ║
╠══════════════════════════════════════════════════════════════════╣
║  [L4] 实时数据层    instock_MonitorTK (Sina/东方财富 Level2推送)  ║
╠══════════════════════════════════════════════════════════════════╣
║  [L3] 智能检测层    BiddingMomentumDetector + SectorFocusEngine   ║
╠══════════════════════════════════════════════════════════════════╣
║  [L2] 决策执行层    DecisionQueue + MockTradeGateway + RiskManager║
╠══════════════════════════════════════════════════════════════════╣
║  [L1] 展示交互层    PyQt6 UI面板群 + 语音播报 + 报警弹窗          ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 二、四大功能模块

### 模块一：StockSelector（强势股筛选器）
**职责**：每日盘后/盘前从全市场筛选候选龙头  
**文件**：`stock_selector.py` + `stock_selection_window.py`

| 功能 | 说明 |
|------|------|
| 多周期均线筛选 | MA5/20/60 多头排列，强势区间 |
| 历史形态评分 | V反/平台突破/上轨攀升评分 |
| 板块聚焦 | 识别候选股所属板块，纳入 `sector_seeds` |
| 选股工具追踪 | 持续追踪已选股涨跌进展 |

**输出**：`stock_selector_seeds` → 注入 `BiddingMomentumDetector`，让选股器结果在竞价面板中获得3分加成

---

### 模块二：Stock Live Strategy（实时策略判断）
**职责**：全市场实时扫描，检测个股形态信号  
**文件**：`stock_live_strategy.py` + `intraday_pattern_detector.py`

| 组件 | 功能 |
|------|------|
| 并行扫描引擎(v2.2) | 30路Worker并行，1.4s完成全市场 |
| IntradayPatternDetector | V型反转/均线支撑/突破/高开低走 检测 |
| PositionPhaseEngine | SCOUT→LAUNCH→SURGE→EXIT 状态机 |
| T+0 风控 | VWAP止损/日亏2%强制清场 |

---

### 模块三：Alert System（日志/语音报警）
**职责**：统一信号路由、语音播报、弹窗提醒  
**文件**：`alert_manager.py` + `signal_message_queue.py`

```
信号触发 → SignalBus → AlertManager
                          ├─ VoiceAnnouncer（合成语音）
                          ├─ FlashScreen（闪屏弹窗）
                          └─ IPC → trade_visualizer_qt6（可视化进程）
```

---

### 模块四：TradingAnalyzer（交易日志分析与反向优化）
**职责**：复盘、胜率统计、信号质量评估  
**文件**：`trading_analyzerQt6.py` + `trading_logger.py`

---

## 三、核心数据流

### 3.1 实时行情数据流

```
Sina/东财 Level2推送
    └─ realtime_data_service.py (MinuteKlineCache)
        └─ df_all (全市场实时快照 DataFrame)
            ├─ instock_MonitorTK._update_ui()      [1.5s UI刷新]
            ├─ stock_live_strategy.process_data()  [30路并行扫描]
            ├─ SectorBiddingPanel.on_realtime_data_arrived()  [竞价面板]
            └─ SectorFocusController.inject_realtime()  [交易引擎, 30s节流]
```

### 3.2 竞价数据计算流（核心引擎）

```
SectorBiddingPanel.on_realtime_data_arrived(full_df)
    └─ DataProcessWorker (后台线程)
        └─ BiddingMomentumDetector
            ├─ register_codes(df)          ← 更新 TickSeries 基础数据
            ├─ update_scores()
            │    └─ _evaluate_code(code)   ← 个股评分
            │         ├─ cycle_score (周期/历史因子)
            │         ├─ bidding_score (开盘高开强度)
            │         ├─ momentum_score (持续动量累计)
            │         ├─ pct_diff (60m切片涨幅)
            │         ├─ price_diff (绝对位移)
            │         └─ dff (行情源量价信号)
            └─ _aggregate_sectors()        ← 板块聚合
                 ├─ board_score (板块强度)
                 ├─ score_diff (60m强度变化)
                 ├─ follow_ratio (跟涨比例)
                 ├─ sector_type (🔥强攻/♨️蓄势/🔄反转/📈跟随)
                 └─ active_sectors list
```

### 3.3 决策引擎数据流（v2 完整打通版）

```
BiddingMomentumDetector (每30s)
    └─ SectorFocusController.inject_from_detector(detector)
        ├─ ① SectorFocusMap.inject_detector_sectors(active_sectors, stock_snap)
        │    └─ SectorHeat（含 leader_klines/pct_diff/dff/score_diff）
        ├─ ② StarFollowEngine.confirm_leaders()
        │    └─ 基于 board_score 三重确认龙头
        ├─ ③ inject_ext_data(55188_df)    ← 主力/人气/题材
        └─ ④ tick() → _scan_pullbacks()
              └─ IntradayPullbackDetector._scan_one_v2(code, sh)
                   ├─ 真实 klines → VWAP / prices5 / vol_ratio
                   ├─ pct_diff, dff → 优先级加权
                   ├─ 形态1: 飞刀接落（回踩+均线+缩量）
                   ├─ 形态2: VWAP支撑（量放大+龙头确认）
                   ├─ 形态3: 板块共振（上翘+周期涨幅）
                   └─ 形态4: 强势跟进（蓄势/强攻+dff正向）
                        └─ DecisionSignal → DecisionQueue
```

---

## 四、关键文件索引

### 核心引擎
| 文件 | 功能 | 重要度 |
|------|------|--------|
| `instock_MonitorTK.py` | 主程序入口，全局调度中心 | ⭐⭐⭐⭐⭐ |
| `bidding_momentum_detector.py` | 竞价动量检测引擎，最核心的算法模块 | ⭐⭐⭐⭐⭐ |
| `sector_focus_engine.py` | 盘中交易决策引擎（v2） | ⭐⭐⭐⭐⭐ |
| `trade_gateway.py` | 模拟/实盘交易网关 + 风控 | ⭐⭐⭐⭐ |
| `sector_bidding_panel.py` | 竞价面板 UI + DataProcessWorker | ⭐⭐⭐⭐ |
| `scraper_55188.py` | 55188外部数据爬取与缓存 | ⭐⭐⭐⭐ |
| `realtime_data_service.py` | 实时行情数据服务（K线缓存） | ⭐⭐⭐⭐ |
| `stock_live_strategy.py` | 全市场并行扫描策略引擎 | ⭐⭐⭐⭐ |

### UI 面板
| 文件 | 功能 |
|------|------|
| `trade_visualizer_qt6.py` | 主可视化窗口（K线/持仓/信号） |
| `signal_dashboard_panel.py` | 信号看板（跟单/风险/突破分类） |
| `stock_selection_window.py` | 选股工具窗口（含板块聚焦+决策队列面板） |
| `market_pulse_viewer.py` | 市场温度大盘面板 |
| `hotlist_panel.py` | 热点标的追踪面板 |
| `strategy_manager.py` | 策略管理器 |

### 数据库
| 文件 | 内容 |
|------|------|
| `signal_strategy.db` | 主交易流水库（跟单/持仓/策略统计） |
| `trading_signals.db` | 历史信号库 |
| `market_pulse.db` | 市场温度历史（涨跌家数/板块情绪） |
| `concept_pg_data.db` | 板块/题材概念库 |

---

## 五、数据字段说明

### TickSeries 个股快照字段（BiddingMomentumDetector）
| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float | 综合动量评分（竞价+周期+持续） |
| `current_pct` | float | 当日涨幅（相对昨收） |
| `pct_diff` | float | 自切片锚点起的涨幅变化（60m周期） |
| `price_diff` | float | 自切片锚点起的绝对价格位移 |
| `dff` | float | 行情源量价偏离信号（原始字段） |
| `vwap` | float | 分时均价线（成交额/成交量） |
| `score_diff` | float | 评分自锚点的变化量 |
| `klines` | deque | 当日分钟K线队列（含time/open/high/low/close/volume） |
| `momentum_score` | float | 持续动量累计分（强势维持+0.05/次，回落减分） |
| `pattern_hint` | str | 形态描述标签（V反/突破/上轨等） |
| `first_breakout_ts` | float | 首次异动时间戳 |

### 板块快照字段（active_sectors 列表元素）
| 字段 | 类型 | 说明 |
|------|------|------|
| `sector` | str | 板块名称 |
| `score` | float | board_score 综合强度 |
| `score_diff` | float | 60m内强度变化 |
| `follow_ratio` | float | 同向跟涨比例（0~1） |
| `leader` | str | 龙头股代码 |
| `leader_pct` | float | 龙头当日涨幅 |
| `leader_pct_diff` | float | 龙头60m切片涨幅变化 |
| `leader_dff` | float | 龙头dff |
| `leader_klines` | list | 龙头最近35根分钟K线 |
| `tags` | str | 类型标签（🔥强攻/♨️蓄势等） |
| `followers` | list | 跟随股明细（含pct/dff/klines） |

---

## 六、统计周期说明

### comparison_interval（对比统计周期）
- **默认值**：`60 * 60 = 3600秒`（60分钟）
- **控制范围**：同时影响个股 `pct_diff/price_diff` 和板块 `score_diff` 的计算基准
- **UI调节**：竞价面板右上角 `-10m / +10m` 按钮实时调整
- **重置逻辑**：`_aggregate_sectors()` 中，当 `now - baseline_time >= comparison_interval` 时自动调用 `reset_observation_anchors()`，统一重置所有个股和板块的锚点

---

## 七、部署与运行环境

| 项目 | 配置 |
|------|------|
| OS | Windows 10/11 |
| Python | 3.10+ |
| UI框架 | PyQt6 + Tkinter |
| 数据本地化 | TDX 通达信历史数据 |
| 实时行情 | Sina/东财推送（instock 库） |
| 打包 | PyInstaller / Nuitka |
| 编码 | UTF-8（无BOM） |

---

## 八、迭代版本历史

| 日期 | 版本 | 核心变更 |
|------|------|----------|
| 2026-01-20 | v1.0 | 基础热点面板 + 信号总线 |
| 2026-01-24 | v1.5 | 缺口可视化 + 跟单队列 |
| 2026-02-02 | v0.9 | TD序列 + 顶部检测 |
| 2026-02-28 | v2.0 | 早盘极速抢筹 + VWAP止损 |
| 2026-03-10 | v2.1 | 强势启动识别 + 绩效评分 |
| 2026-04-04 | v2.5 | 竞价面板性能深度优化 |
| 2026-04-05 | v3.0 | **盘中实时交易引擎集成（决策引擎v2完整打通）** |

# easy-stock 策略总手册（给 Codex 本地复刻用）

> 生成日期：2026-10-14 | 策略版本：strategy.yaml v1.10 | 维护：Muse + 用户
> 本文档 = 全部 P 感知规则的定义、参数、实现位置、状态。定时任务见《工作流手册》。

---

## 1. 账户体系（5 套独立账本）

| 市场 | 账本文件 | 本金 | 锁仓 | 信号入口 |
| --- | --- | --- | --- | --- |
| A股 CN | `logs/paper_ledger.json` | 50万 RMB | T+1（买入日不可卖） | `paper_trade.py --signal` |
| 美股 US | `logs/paper_ledger_us.json` | 10万 USD | T+1（美股日历） | `paper_trade.py --market US --signal` |
| 币圈多头 CRYPTO | `logs/paper_ledger_crypto.json` | 10万 USD | T+0 | `paper_trade.py --market CRYPTO --signal` |
| 币圈空头 SHORT | `logs/paper_ledger_crypto_short.json` | 10万 USD 保证金，10倍杠杆 | T+0 | `paper_trade.py --market CRYPTO --side short --signal` |
| 币圈实验仓 EXP | `logs/paper_ledger_crypto_exp[_short].json` | 同主仓 | T+0 | `paper_trade.py --sleeve exp`（仅 CRYPTO） |

- 决策日志：`logs/decisions_<date>.json`（CN）/ `decisions_us_<date>.json` / `decisions_crypto[_short/_exp]_...`
- 铁律：模拟盘只认 strategy.yaml + 决策日志，不认聊天情绪；实盘持仓（`positions_real.json`）只影响文案不进账本。

---

## 2. 核心参数（strategy.yaml 顶层）

**买入**：`min_pool_score 8.0`（关注池分）/ `min_market_sentiment -40`（P2 水位下降时收紧到 -15）/ `max_day_chg 7.0`（P4 加速末端不追）/ `forbid_dead_day`（P5）/ `max_positions 5` / `amount_per_trade 100000`

**卖出**：`take_profit +10%` / `stop_loss -6%` / `vwap_stop` 跌破买入日1日VWAP-2% / `break_ma10` 跌破买入日10日VWAP（P6 双锚点）/ `emotion_cool_profit 5%`（P3 降温提前止盈）/ `max_hold_days 5` / `p20_band 1%`（P20 保本区）

**网格 P11**：`amount_per_grid 100000` / 卖出区=两日最高×1.005\~1.01 / 买入区=两日最低×1.01\~1.02 / `trend_break 0.99`（跌破10日VWAP×0.99 一键清仓）

**轮动 P12**：`weak_th -3`（卖弱）/ `strong_th 4`（强者打码）/ `pyramid_amount 100000` / `dead_day_relief -15`（盘中情绪≥-15 解除盘前 dead\_day）

**统一决策门 decision\_gate**：`mode: shadow`（只记录不干预，攒 20-30 笔后周复盘定是否转 enforce）/ `threshold 60` / 权重：p8\_four 30 / p25 20 / p26\_sector 15 / pool\_score 15 / p22\_leader 10 / sentiment 10

**硬 kill**：`kill.max_day_loss_pct 0.03`（单日已实现亏损≥3% 自动拉起，P8/P24/P18 新开仓全停，网格/轮动/卖出照常；`logs/kill_switch.json`；`--kill on|off|status`）

---

## 3. 感知规则总表（P1–P35）

### A股买入链

| ID | 名称 | 定义（一句话） | 关键参数 | 实现 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P1 | 调仓换股 | 高位科技放量下跌后资金流向低位；调仓窗口日新进 hot\_sectors 成分 watchpool +2 | — | `sentiment.py`→`watchpool.py` | 部分（打分加成待接入） |
| P2 | 蓄水池水位 | 全市场成交额 5 日均值连降 3 日 → 买入门槛 -40 收紧到 -15 | `min_market_sentiment_low_water -15` | `sentiment.py` | ✅ |
| P3 | 新股风向标 | 首板数+最高连板 → 风险偏好高中低；偏好低收紧门槛 | — | `sentiment.py` | ✅（代理指标） |
| P4 | 加速末端 | 当日涨幅>7% = 加速末端，不追高 | `max_day_chg 7.0` | `paper_trade.py` | ✅ |
| P5 | 大跌装死日 | 下跌家数>4000 → dead\_day 当日不新开仓；盘中情绪≥-15 解除 | `dead_day_relief -15` | `paper_trade.py effective_dead_day()` | ✅ |
| P8 | 早盘买入四条件 | 站上1日VWAP×1.005 + 量价齐升 + 偏离<2.5% + 盘中VWAP≥3日VWAP；9:45/10:00/10:15/10:30/11:30 节点冲高回落不买；数据不可验证 fail-closed | `vwap_mult 1.005` / 偏离 2.5% | `paper_trade.py do_signal` | ✅ |
| P9 | 预开仓（TK对齐） | 09:00 盘前结构分≥4 → 09:27 竞价确认（竞价额分档/高开0.5\~7.5%/开盘≈最低/VWAP门禁0.995）→ 09:45 窗口执行 → 10:05 确认 | `min_pre_score 4` / `min_auction_score 3` / `gap_range [0.5,7.5]` | `preopen.py`→`auction_scan.py`→`paper_trade.py --preopen` | ✅ |
| P10 | 异动流转 | 昨日 vwap\_ride 命中的票 → 次日关注池候选 | — | `watchpool.py:234` | ✅（yaml 未登记） |
| P24 | 大阳跟随单 | 近3日大阳启动 + 站上VWAP×1.005 + 量价齐升 + 偏离<5% + 当日最低≥大阳最低×0.98 + OBV黄线上 + 涨幅≤9%；半仓，P23 预期3天 | `sector_score ≥50`（P26） | `paper_trade.py do_signal` P24 loop | ✅ |
| P25 | 趋势门 | 1日VWAP>3日VWAP>5日VWAP 且 昨日收盘站上 MA20，否则 P8/P24 不开仓 | — | `paper_trade.py trend_gate_ok()` | ✅ |
| P26 | 板块四维 | sector\_score = 强度25+热度25+力度25+量能25；P24 要求≥50 | 阈值 50（初版待调） | `sector_leader.py score_dims()` | ✅ |
| P18 | 止盈后补回 | 止盈后重新站上 VWAP×1.005 + 量价齐升 + 偏离<2.5% → 按 P8 金额买回 | — | `protect.p18_ok()` → `paper_trade.run_buyback()` | ✅ |

### A股卖出/持仓管理

| ID | 名称 | 定义 | 关键参数 | 实现 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P6 | 破位纪律 | 跌破买入日10日VWAP 或 买入日1日VWAP-2% → 破位止损（双锚点先破先走） | `vwap_stop 0.02` / `break_ma10` | `paper_trade.py do_settle` | ✅ |
| P7 | 翻转进击点 | 持仓浮亏<-3% 且 早盘诱空→真强反转 → 加仓一笔（每只一次） | `add_trigger_loss -0.03` | `paper_trade.py` | ✅ |
| P11 | 两日网格做T | 冲高看两日最高+0.5\~1%挂卖，最低+1\~2%挂买；破位三段式：跌破VWAP标记→收复解除→反弹不过VWAP且量能<0.8倍确认，在反弹 VWAP 下方卖；分时 VWAP 下方头肩顶=多头衰竭前置预警 | `trend_break 0.99` | `grid_t.py` → `watch_600733.py` → `paper_trade run_grid_t()` | ✅ |
| P12 | 资金轮动 | 强度分=站上VWAP+2/5日动量/网格位置/疑似破位-2；≤-3 卖弱释放资金；≥4 强者打码（与P7共用每只一次上限）；P21 控盘板块跳过打码 | `weak_th -3` / `strong_th 4` | `grid_t.position_strength()` → `paper_trade run_rotation()` | ✅ |
| P15 | 板块龙头换仓 | 双轨：轨1换入（持仓强度≤-3 且 严格同板块 且 龙头连续多日VWAP强势 且 板块资金痕迹 且 盘中站上VWAP 且 非一字陷阱 → 卖一半弱势买龙头，偏离<2.5%）；轨2次日跟踪（证伪/早盘下杀等15分钟确认/动量证伪） | — | `sector_leader.py` → `paper_trade run_rotation()` | ✅ |
| P16 | 卖出带买回计划 | 任何主动卖出必须带买回触发条件，否则 SKIP；止盈/P20 自动进 `buyback_watch_<市场>.json`（5日有效） | — | `protect.buyback_plan_for()` | ✅ |
| P17 | 买入次日下杀即走 | 买入次日跌破买入日最低 或 低开低走 → 即走 | — | `paper_trade.py do_settle` | ✅ |
| P19 | 加速大阳诱多 | 横盘后首次大阳（>7%+放量>2倍+前20天无大阳+振幅<25%）→ 减半；次日不创新高/回落2% → 清仓 | — | `protect.detect_accel()` | ✅ |
| P20 | 保本出局 | 曾被套（was\_underwater）后反弹回成本±1% → 无条件减半 | `p20_band 0.01` | `paper_trade.py do_settle` | ✅ |
| P21 | 控盘板块识别 | 20天波动率中位数<1.5% + 无±4%大K + 与指数相关<0.4 → 网格模式（只做T不追突破） | — | `sector_leader.sector_mode()` | ✅ |
| P22 | 龙头早发现 | L1观察（不对称>2.5）/ L2确认（>3.0+连续VWAP结构+OBV站上黄线，资金一票否决）/ L3加码（+异动高点抬升或上轨运行）；OBV三环：启动/护盘/持有 | `ASY_WATCH 2.5` / `ASY_CONFIRM 3.0` | `sector_leader.py` | ✅ |
| P23 | 预期止损+大阳买卖点 | 买入带 expect{days, target\_pct=2%}（普通5天/P15换仓3天创新高），到期未兑现平仓；大阳：startup\_buy/pullback\_buy/watch/miss\_sell/stop\_sell（全 point-in-time） | — | `dayang.py` → `paper_trade _p23_miss()` | ✅ |
| P27 | 最低半仓+系统性风险 | 无风险且仓位<50% → 单笔1.5倍直到半仓；systemic\_risk()=（盘前情绪≤-60 或 盘中≤-30且连弱2轮）AND（一半持仓昨收<5日VWAP）→ 停新开仓 | — | `paper_trade.systemic_risk()` | ✅（美股未启用） |
| P28 | 轮动T纪律 | P25 趋势门不过 → T\_SKIP 不做T；周级节奏，日级只执行信号 | — | `paper_trade run_grid_t` | ✅ |
| P29 | 上轨运行（boll\_ride） | 近5日收盘≥BOLL UPPER×0.98 天数≥4 = 强势，并入 P22 L3 | — | `sector_leader.boll_ride()` | ✅（yaml 缺 id 字段） |

### 币圈特有

| ID | 名称 | 定义 | 实现 | 状态 |
| --- | --- | --- | --- | --- |
| P30 | 时间周期结构 | 涨跌段时长+斜率量化情绪；weak\_rebound/steady/exhaust/regime\_switch | `cycle_structure.py` / `p30_backtest.py` | 基础检测只读；**不及预期时间窗（v1.7+）策略空单自动平**（expect_dead，`paper_trade.py:2839`），镜像单只预警；v1.9 加平空后 12h 冷却 |
| P32 | 试探确认 | 破位后 6h 窗口内最大反弹<1% = 无承接，跌势延续确认 | `probe.py` | ✅ |
| P33 | 五周期压制+企稳离场 | 4h 收盘<MA5 = 压制；破位空单连续 2 根 4h 不创新低 = 企稳提前离场 | `probe.py` | ✅ |
| P34 | 反抽确认开空 | 下跌→反抽≥1%→反抽高点不见新高→受4hMA5压制→1h转弱确认再开空；止损=反抽高点×1.003 | `paper_trade.py`（主仓入口） | ✅（yaml perception\_rules 未登记） |
| S-P25/S-P8/S-P24 | 空头镜像 | 趋势门/小时触发/大阴跟随（方向反转，偏离门 2.5%） | `paper_trade.py --side short` | ✅ |

| 阻力拒绝/支撑跌破 | 阻力区≥2次未破 → 开空；支撑跌破（主仓影子） | `paper_trade.py` | ✅/影子 |
| P36 | 事件冲击（原P34，2026-10-15 改号避冲突） | 财联社电文匹配持仓+跟踪池，极端事件告警 | `event_shock.py`（hook） | shadow 2周，只告警不接门禁 |

### 提案中（未进 strategy.yaml）

| ID | 名称 | 状态 |
| --- | --- | --- |
| P35 | 趋势/通道架构（多周期通道大结构定方向 + screen 五层筛选） | `screen.py` 影子记录中，未转正，需用户批准 |

**编号说明**：P13/P14/P31 从未使用；P29 的 yaml 条目缺 `id:` 字段（见下审计）。

---

## 4. 决策链路

**do\_signal（买入）**：P11 网格 → P12 轮动 → 池/早盘/情绪门禁 → P8 四条件 / P24 大阳跟随 / P18 补回 → 统一决策门（shadow 记录）

**do\_settle（卖出优先级）**：止盈 → P17 次日下杀 → 止损 → P23 不及预期 → 时间止损 → VWAP止损 → 破位止损 → 情绪退潮止盈 → P20 保本 → P19 加速减半 → P11 头肩顶/一键清仓/网格

**预开仓链**：`preopen.py`(09:00) → `auction_scan.py`(09:15-09:27) → `paper_trade --preopen`(09:27) → `confirm_preopen_orders`(09:30-09:45) → `morning-signal`(10:05)

---

## 5. 本次审计发现的问题（2026-10-14）

1. **P29 yaml 缺&#32;`id:`&#32;字段**（strategy.yaml:237，上轨运行条目直接以 `from:` 开头）。不影响运行（代码读不到 perception\_rules 的 id），但文档不完整。建议补 `id: P29_上轨运行`。
2. **P34 未登记进 perception\_rules**（只在 changelog v1.10 和 `crypto_short.entry.bounce_fail` 有）。它是当前空头主仓入口，建议补条目。另：P34 曾被事件冲击占用（2026-10-08），2026-10-15 起统一为 P34=反抽确认开空、事件冲击改号 P36。
3. **P10 只在代码注释有**（watchpool.py:234），yaml 无条目。建议补。
4. **`updated: 2026-10-04`&#32;过期**（v1.10 实际是 2026-10-09）。建议同步。
5. **decision_gate 的 p22_leader 权重是死的（2026-10-14 更正：之前审计写反了）**：`unified_gate` 里 `factors.get("p22_l2")` 只有读（paper_trade.py:980），do_signal 从未往 factors 里写过 `p22_l2`。所以 yaml 里"暂未接入信号链，预留"的备注是对的，这 10 分权重永远拿不到。要么在 do_signal 里接 `sector_leader.leader_strength` 的 L2 结果写入 factors，要么把权重先置 0 免得误导归因。
6. **mse：`buy.min_pool_score`&#32;与&#32;`crypto_exp.min_pool_score`&#32;的覆盖关系**在 yaml 里写清楚了（exp 6.0 vs 主 8.0），无问题。

以上除第 5 条外是文档层问题；第 5 条（p22_leader 死权重）会影响评分与归因，复刻前需决定接入因子或置零权重，**不可当作备注自动实施**。

---

## 6. Codex 复刻注意事项

1. **唯一真相源**：`strategy.yaml` + `logs/decisions_*.json`。不要从聊天记录推导参数。
2. **fail-closed 铁律**：任何数据缺失/不可验证 → 不交易，只记录。这是最高优先级约束，凌驾于所有 P 规则。
3. **T+1 锁**：CN/US 买入日不可卖（`locked` 字段）；CRYPTO 无锁。
4. **版本号**：调参必须升 version + 写 changelog，禁止静默改参数。
5. **P35/screen/event\_shock 保持 shadow**：只记录不干预，等用户批准再转正。
6. **推送**：企业微信群`@在路上`；测试推送不准进正式群。
---

## 7. 情绪感知系统（2026-10-14 用户指出补录）

> 设计目标：把"市场情绪"量化成 -100~+100 的分，供买入门禁/装死日/P27 系统性风险用。
> 铁律：**情绪只能否决或调仓位，不能制造买点**。
> fail-closed 边界：P27 `systemic_risk()` 数据缺失返回 False（yaml 原文"数据缺失fail-closed=False"，属设计：不误判）；`kill_switch_armed()` 文件读取异常返回 False（fail-open）。"全链 fail-closed"不含这两处。

### 三件套

**1. `sentiment.py` 盘前（cron 08:35）**
- 数据源：55188 overview，经 `upstream.py` 门控（30 分钟冷却，503 熔断 6 小时，永不重试）；挂掉自动降级 `sentiment_local.py`。**版本注意**：这两块是 2026-10-12 加入（v1.10 环境），v1.9 本地缺失，需自行补齐或接受无降级。
- 评分公式 `market_sentiment(ov)`：
  - breadth = (上涨家数-下跌家数)/(总数) × 40
  - limit_diff = (涨停数-跌停数) × 2，±20 封顶
  - board = (最高连板-3) × 5，±15 封顶
  - money_effect = 昨日涨停今日赚钱效应 × 3，±15 封顶
  - amount_mom = 成交额环比，±10
  - broken = -炸板数 × 0.5，-10 封底
  - 总分 ±100 截断
- 标签：≥40 亢奋 / ≥15 积极 / >-15 中性 / >-40 谨慎 / ≤-40 冰点
- P5：下跌家数 >4000 → `dead_day=True`，当日不新开仓（已有持仓按卖出规则正常处理）；分数直接压到 ≤-40
- 落盘：`logs/sentiment_<date>_premarket.json`（`sentiment.py:273`；`paper_trade.latest_premarket()` 读同一路径）

**2. `sentiment_intraday.py` 盘中（hook，每 30 分钟，窗口 09:30–11:30/13:00–15:05）**
- 同口径 -100~+100；落盘 `logs/sentiment_intraday_<date>.jsonl`（供周一复盘）
- 轨迹感知 `trend_analysis`：开盘分→现分，±5 阈值判"日内走强/走弱"，+连续同向次数 +三预警：
  - 亢奋区（≥30）连续走弱 2 次 → "退潮警惕跳水"
  - 冰点（≤-15）连续走强 → "冰点修复中"
  - 高位钝化 → "方向待选"
- P5 盘中化：盘前 `dead_day` + 盘中情绪 ≥-15 → 自动解除（`dead_day_relief: -15`）

**3. `sentiment_local.py` 本地降级（2026-10-12 用户批评"不能总是等着我"后加）**
- 55188 挂掉时：盘中用新浪全推自算实时快照，盘前用昨日日K（零外部请求）
- 三大指数日K入库（market='IDX'：000001/399001/399006），指数分用真实指数日K

### 情绪在策略中的用法

| 用处 | 规则 |
|---|---|
| 买入门禁 | `min_market_sentiment -40`；P2 蓄水池水位连降 3 日收紧到 -15 |
| 系统性风险 P27 | 盘前 ≤-60，或盘中 ≤-30 且连续走弱 ≥2 轮（AND 持仓 VWAP 风险）→ 停新开仓 |
| 空头门禁 | 情绪 >+40 不开空；情绪不可验证 → fail-closed |
| 决策门 | sentiment >0 得 10 分（shadow，只记录） |
| 北汽 watcher | 盘前 dead_day + 盘中情绪 <-15 → 拦截 T+1 买点（2026-10-14 加） |

### 已知弱点（2026-10-13 实战教训）
- 早盘冰点门禁判错：盘前 -40 锁死全天，收盘情绪翻到 +43.4 亢奋。冰点修复日的门禁逻辑是已知弱点，已承认，周一复盘重点审判。**不要把这次判错包装成正确**，Codex 复刻时保留原逻辑，等复盘结论再改。

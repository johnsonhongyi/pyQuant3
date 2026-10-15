# easy-stock 工作流手册：定时任务 + Hook（给 Codex 本地复刻用）

> 生成日期：2026-10-14 | 配套文档：《策略总手册 strategy-manual-2026-10-14.md》
> Muse 来源目录：`~/workspace/easy-stock-service/`；本地服务目录：`source/easy-stock-service/`。
> 下列 Cron/Hook 表是 Muse 来源声明，✅不表示本地定义存在或生产已启用。先读第 0 节，禁止原样批量安装。

## 0. 本地适配基线（2026-10-14）

- 当前配置为 v1.9。Windows 使用 `python`；Linux 部署脚本按既有 `/usr/bin/python3` 运行，不复制个人 site-packages 或覆盖依赖。
- 受版本管理的行情计划以 `docker/stockstrategy-market-append.cron` 为准：CN 工作日 16:20 首跑、17:20 重试（Asia/Shanghai）；US 每日 06:15（Asia/Hong_Kong）；CRYPTO 每日 00:15 UTC。实际生产 crontab 未重新查询，不能据本地文件宣称线上一致。
- 所有行情计划经 `docker/market-append.sh` 执行，保留 flock、持久日志、交易日日历、共享 stock-data.db、API 容器地址解析。CRYPTO 在追加前刷新动态宇宙；CN 从 InStock forwardp 读取，不允许缺数据时回退外部日线。
- Muse 的 15:35 追加、15:40 结算早于本地 CN 16:20 追加，不能沿用固定时间依赖；盘后结算必须验证目标交易日已完成、数据新鲜且覆盖足够，否则记录失败并等待补齐。
- 本地 auction_scan.score_preopen 最少要求 3 轮；Muse 写 2 轮与源码不符，不降低门槛。confirm_preopen_orders 是 paper_trade.py 内函数，不是独立脚本。
- 本地缺少 sentiment_local.py、local_heat.py、surprise.py、paper_review.py、upstream.py、ashare_gate.py、probe.py、screen.py、event_shock.py 及所列 Hook shell；相关计划均待提供实现/接口并核验，不可启用。行情缓存实际由 market_cache.py 和 Go marketcache 负责，不能把来源的“503 永不重试”当作全链已验证事实。
- 不复制 feed-pulse-*、heartbeat、deterministic-doctor；不新建重复健康拉起服务。遵循 ENVIRONMENT_HANDOFF.md 的只读容器、外置持久化和发布回滚契约。
- push_config.json、.env、密钥和真实账本不入版本库；不整目录复制 logs/data，不向正式群测试推送。原生产 cron 保持不变；新增独立模拟 worker 已按用户授权部署。
- 自动跟单本地入口为 `python auto_follow.py --watch`，每轮后间隔 60 秒、非交易时段不取行情，独立持久账本。本地默认读盘前情绪；LXC 102 的 systemd 服务改用 Go 原生盘中情绪否决门，不换算 Muse 分数。2026-10-15 发布 20261015000500 已启动并自启，运行边界与证据见 docs/tasks/2026-10-14_2355_自动跟单模拟盘规划与实施.md。


---

## 1. Cron 定时任务总表（Asia/Shanghai 除非注明）

### A股盘前链（按时间顺序，有依赖关系）

| ID | 时间 | 命令 | 用途 | 状态 |
|---|---|---|---|---|
| structure-scan | 08:30 | `python3 watchpool.py` | 盘前关注池：重点股+跟踪池+异动集+P10流转 → Top30 | ✅ |
| premarket-sentiment | 08:35 | `python3 sentiment.py` | 盘前情绪分（-100~+100），落盘 `logs/sentiment_<date>.json` | ✅ |
| preopen-plan | 09:00 | `python3 preopen.py` | 预开仓计划：盘前结构分+龙虎榜，≥4分入选 | ✅ |
| auction-scan | 09:15 | `python3 auction_scan.py --session` | 集合竞价扫描，采样至 09:27，最小有效轮次：Muse 2 / 本地 3（以本地为准） | ✅ |
| preopen-buy | 09:27 | `python3 paper_trade.py --preopen` | 竞价预挂单（过 P5/P3/P4 门禁），落盘 `logs/preopen_orders_<date>.json` | ✅ |

### A股盘中/盘后链

| ID | 时间 | 命令 | 用途 | 状态 |
|---|---|---|---|---|
| morning-signal | 10:05 | `python3 paper_trade.py --signal` | 早盘信号：P8/P24/P18 买入 + P11网格 + P12轮动 + P15换仓 | ✅ |
| paper-settle | 15:40 | `python3 paper_trade.py --settle` | 收盘结算（卖出优先级链），写账本+决策日志+推送 | ✅ |
| daily-review | 15:35 | `python3 daily_review.py > /tmp/daily_review_out.json` | VWAP 结构盘后复盘（单轮只跑一次，输出先落文件） | ✅ |
| local-heat | 15:42 | `python3 local_heat.py` | 本地热榜每日推算 | ✅ |
| surprise-scan | 15:50 | `python3 surprise.py` | 出乎意料检测（涨幅z/量能/新高/相对四维），有结构才推 | ✅ |
| funnel-count | 16:05 | `python3 funnel_count.py` | 漏斗计数：入池→P24触发→买入→P23退出（自10-08累计，周一附周汇总） | ✅ |
| bars-daily-append | 15:35 | `python3 bars.py --append` | 日线底座追加（15:30 前拒绝执行，保证终值口径） | ✅ |
| svc-maintenance | 03:00 | `python3 maintain.py` | 日志截断/JSON 90天gzip/包365天删/K线图30天删；磁盘>80%告警 | ✅ |

### 美股链（Asia/Shanghai）

| ID | 时间 | 命令 | 用途 | 状态 |
|---|---|---|---|---|
| us-bars-append | 05:15 | `python3 bars_us.py --append` | 美股日K追加（Yahoo源） | ✅ |
| us-paper-settle | 05:35 | `python3 paper_trade.py --market US --settle` | 美股结算 | ✅ |
| us-morning-signal | 22:00 | `python3 paper_trade.py --market US --signal` | 美股早盘信号（统一策略链路） | ✅ |

### 币圈链（UTC）

| ID | 时间(UTC) | 命令 | 用途 | 状态 |
|---|---|---|---|---|
| crypto-universe-refresh | 00:05 | `python3 crypto_universe.py` | 动态宇宙刷新（静态6+Top12，上限18） | ✅ |
| crypto-bars-append | 00:10 | `python3 bars_crypto.py --append` | 币圈日K归档 | ✅ |
| crypto-paper-settle | 00:25 | `python3 paper_trade.py --market CRYPTO --settle` | 多头结算（实验仓心跳推送保留） | ✅ |
| crypto-short-settle | 00:25 | `python3 paper_trade.py --market CRYPTO --side short --settle` | 空头结算 | ✅ |
| crypto-exp-settle | 00:30 | `python3 paper_trade.py --market CRYPTO --sleeve exp --settle` | 实验仓结算 | ✅ |
| crypto-signal | 每4h (00/04/08/12/16/20) | `python3 paper_trade.py --market CRYPTO --signal` | 多头信号 | ✅ |
| crypto-short-signal | 每4h（02/06/10/14/18/22） | `python3 paper_trade.py --market CRYPTO --side short --signal` | 空头信号（与多头错开：02/06/10/14/18/22） | ✅ |
| crypto-short-watch | 每1h | `python3 crypto_short_watch.py` | 空头持仓盯盘（P30/P33/试探/企稳检查） | ✅ |
| crypto-exp-signal | 每1h | `python3 paper_trade.py --market CRYPTO --sleeve exp --signal` | 实验仓信号 | ✅ |

### 运维链

| ID | 时间 | 命令 | 用途 | 状态 |
|---|---|---|---|---|
| backup-sync | 每72h | 备份脚本 | 发布包→本地快照→密钥包→Drive（留最近3版，永不传密钥/账本） | ✅ |
| strategy-sync | 每72h | 策略包脚本 | 按 strategy.yaml 重打策略包（不含密钥账本，留最近5版） | ✅ |
| paper-review | 周一 20:00 | `python3 paper_review.py` | 周复盘归因调参（用户批准才升版本） | ✅ |

### 已禁用（转 hook，保留定义）

| ID | 原频率 | 说明 |
|---|---|---|
| beiqi-bluepark-watch | 10m | → hook（见下） |
| intraday-scan | 30m | → hook |
| intraday-sentiment | 1h | → hook |
| vwap-ride-scan | 30m | → hook |
| easy-stock-healthcheck | 15m | → hook |
| easy-stock-web-healthcheck | 15m | → hook |

**禁用原因**（2026-10-05 用户拍板）：cron 触发=启动完整 worker，非交易时段空转浪费；转 hook 后由轻量脚本预检，无事件零 worker。

---

## 2. Hook 清单（`~/hooks/scripts/`，轮询+条件唤醒）

| ID | 轮询 | 脚本 | 唤醒条件 | 状态 |
|---|---|---|---|---|
| beiqi-bluepark-watch | 600s | `beiqi-bluepark-watch.sh` | 交易时段内有 T+1/网格/破位信号 | ✅ |
| intraday-scan | 1800s | `intraday-scan.sh` → `ashare_gate.py` 预检 | 跟踪池跨档/破位/+8% | ✅ |
| intraday-sentiment | 3600s | `intraday-sentiment.sh` → `ashare_gate.py` 预检 | 情绪快照（09:30–11:30/13:00–15:05） | ✅ |
| vwap-ride-scan | 1800s | `vwap-ride-scan.sh` → `ashare_gate.py` 预检 | VWAP ride 启动 | ✅ |
| event-shock-watch | 1200s | `event-shock-watch.sh` | 财联社极端事件命中持仓/跟踪池（shadow） | ✅ |
| global-board | 900s | `global-board.sh` | 标杆600825状态/板块共振/reclaim盯盘有事件 | ✅ |
| easy-stock-backend-health | 300s | `easy-stock-backend-health.sh` | 后端 127.0.0.1:20081 失活 → 拉起 | ✅ |
| easy-stock-web-health | 300s | `easy-stock-web-health.sh` | 前端 127.0.0.1:20073 失活 → 拉起 | ✅ |

**预检门**：`ashare_gate.py`（交易日+时段窗口，0.1秒本地判断），非交易时段直接 silent，零 worker。

---

## 3. 数据流依赖图

```
08:30 watchpool ──┐
08:35 sentiment ──┴─→ 10:05 morning-signal → paper_ledger.json
09:00 preopen-plan ─→ 09:27 preopen-buy ─→ 09:30-09:45 确认 ─→ 10:05 转持仓
09:15 auction-scan ─┘（竞价确认）
15:35 bars-append ─→ 15:40 paper-settle ─→ 决策日志/推送
15:35 daily-review / 15:42 local-heat / 15:50 surprise-scan / 16:05 funnel-count（盘后分析链）
周一 20:00 paper-review（复盘→用户批准→strategy.yaml 升版）
```

---

## 4. Codex 本地复刻指南

### 目录结构（`easy-stock-service/` 下）
```
strategy.yaml          # 本地 v1.9，来源 v1.10 尚未核验
paper_trade.py         # 模拟盘核心（do_signal/do_settle/统一决策门）
sentiment.py / sentiment_intraday.py / sentiment_local.py
watchpool.py / yidong.py / structure_scan.py
preopen.py / auction_scan.py / confirm_preopen_orders.py
vwap.py / grid_t.py / watch_600733.py / t1_strategy.py
sector_leader.py / dayang.py / protect.py / cycle_structure.py / probe.py
crypto_pool.py / crypto_universe.py / crypto_short_watch.py
bars.py / bars_us.py / bars_crypto.py / trading_calendar.py
gate_attribution.py / funnel_count.py / paper_review.py / daily_review.py
upstream.py            # 数据源统一门控（55188/同花顺/选股宝节流）
logs/                  # 账本+决策日志（永不删除 paper_ledger.json）
data/*.db              # K线底座（SQLite）
```

### 环境要求
- Python 3.12，依赖 vendor 在 `~/.local/lib/python3.12/site-packages`（numpy==1.26.4, requests, pyyaml, pandas, lxml, matplotlib）
- 时区：A股链 Asia/Shanghai，币圈链 UTC
- 推送：企业微信群机器人，Key 在 `push_config.json`（600 权限，**永不进版本库/云盘**）
- `.env`（600）同上

### 复刻步骤
1. 对照本地 source/easy-stock-service 逐项适配源码；保留本地 v1.9 配置和外置数据，禁止覆盖 logs/账本/data/密钥。
2. 以第 0 节本地调度契约为准；第 1 节策略计划须验证依赖后另行启用。
3. 第 2 节 Hook 尚未随本地代码提供；先补实现和隔离验证，不直接 enable。
4. 在隔离数据目录验证；--dry-run 不等于零副作用，行情请求与缓存仍可能写入。
5. **不要**复刻 `feed-pulse-*` / `heartbeat` / `deterministic-doctor`（系统级，与策略无关）

### 铁律（复刻时必须保留）
- 有副作用脚本一轮只运行一次（`daily_review.py` 输出先落文件再读）
- 503 永不重试（`upstream.py` 门控）；批量拉取间隔≥30分钟
- 推送只走企业微信，每条 `@在路上`；测试推送不准进正式群
- `strategy.yaml` 升版必须走 changelog + 用户批准

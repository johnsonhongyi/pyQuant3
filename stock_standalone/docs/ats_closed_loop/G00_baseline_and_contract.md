# G00 基线与接口契约

状态：`PARTIAL / BLOCKED_FOR_LIVE_BASELINE`  
基准日期：2026-09-24  
仓库 HEAD：`dee64883cb9cbb780d6ab5ea6db158375956cbf2`

## 基线事实

以下运行态数字先由用户只读审核结论提出，随后对安装目录中仍可读取的 SQLite 与 JSON 文件以只读方式复核。未迁移、更新或写入线上文件；哈希为字节级 SHA256。数据库连接使用 SQLite `mode=ro`。

| 观察项 | 报告值 | 可得结论 | 缺失证据 |
| --- | --- | --- | --- |
| `live_signal_history`（2026-09-23） | 2,107 条，状态均为 `NEW` | 信号状态闭环未证实 | 状态只有 `NEW`，缺后续决策关联 |
| `mock_trade_log`（2026-09-23） | 模拟 SELL 4、BUY 0 | 未见 BUY 成交；不得推断买入门缺陷或收益 | 表是模拟日志，不是 TK 当前 PAPER 成交证明 |
| 持仓账本 | 快照 51、流水推导 19 | 对账差异 32，发布必须阻断 | 两份持仓清单、订单流水、逐代码差异表及源文件哈希 |
| 旧交易记录 | 最新日期 7 月 21 日 | 不能代表当前 PAPER 内核 | 数据库来源及查询证据 |
| 影子测试 | 固定样例，指令数固定为 0 | 不能证明端到端链路 | 运行产物、组件接线及连续交易日报告 |
| 运行包 | 当前采样到 6 个 ATS 实例，另有 TK 监控与策略进程 | 已确认当前运行路径及二进制哈希；ATS EXE 版本资源为空，安装目录未找到 fingerprint/manifest sidecar，无法证明源码/构建提交对应关系 | 进程命令行、构建时指纹或可验证的发布清单 |

### 当前进程与 EXE 只读采样

采集时间：2026-09-24 05:31 HKT（2026-09-23 21:31 UTC）。`Get-Process` 可读到映像路径和启动时间；`Win32_Process` 查询因拒绝访问失败，因此未取得命令行。未启动、停止或修改任何进程。以下为当前状态快照，不代表 9/22–9/23 历史状态。

| 进程映像 | PID / 启动时间（HKT） | 文件大小 / 最后修改（UTC） | SHA256 |
| --- | --- | --- | --- |
| `D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe` | 25160 / 2026-09-23 23:32:22；6756 / 23:32:23；1764 / 23:35:08；17292 / 23:40:32；17204 / 23:43:48；1656 / 23:44:06 | 68,121,271 bytes / 2026-09-23 15:18:24 | `CA9498D10489245DDB9C214E0052C3B0DD95F0506746004F03F74E3913B2E72A` |
| `D:\JohnsonProgram\instockMonitorTK\instock_MonitorTK_Nuita.exe` | 10548 / 2026-09-23 23:27:30 | 95,526,400 bytes / 2026-09-22 20:04:28 | `80CCD8712A6CE1233B9CB1B66CFEB1AC137DC02A358989654FA00122E2CA1485` |
| `D:\JohnsonProgram\instockMonitorTK\人气共振2.22.exe` | 2908 / 2026-09-23 23:27:54；20208 / 23:27:52 | 57,949,794 bytes / 2026-09-18 16:22:45 | `77E2939EF3409DA19E59568295AE3D4AB5E0CDC63720A32EF5D48F0E335DCB73` |

已复核的 9/23 文件及可复现查询摘要见下节；它们补足了此前认为缺失的数据库来源与哈希，但不能替代 9/22–9/23 历史进程/构建身份。逐代码持仓差异见 G02。仍不得仅凭 EXE 哈希推断构建提交。

### 线上源文件复核（SQLite 只读）

复核范围为 `D:\JohnsonProgram\instockMonitorTK`。文件修改时间来自文件系统；下面查询仅取结构、聚合计数和日期范围，不读取或输出逐笔交易内容。

| 文件 | 修改时间（HKT）/大小 | SHA256 |
| --- | --- | --- |
| `trading_signals.db` | 2026-09-23 23:28:47 / 240,402,432 bytes | `38b1d5cf36de5091faac7e7f506f021c91184215a79d20fb832cacc8e43658e5` |
| `signal_strategy.db` | 2026-09-23 23:27:35 / 128,856,064 bytes | `4bca70defa240a2d6a338fc8dff6ceb7aa18734ea6bb2f838ef9757f46e09bd4` |
| `logs/paper_account_state.json` | 2026-09-23 10:28:53 / 236,203 bytes | `df14540bb1ff76762a4004208b20710cf1914f6886a72ed01c5eaa6b782cb6f1` |
| `logs/trading_kernel_trace.jsonl` | 2026-09-23 10:28:53 / 3,151,771 bytes | `bc4029be500e01f2c948abdbf907e8bc9b8bdc3db7369f20a7e8c5583fb7b304` |
| `logs/ipo_detector.log` | 2026-09-23 23:35:17 / 276,373 bytes | `a2671f0245465b19b391ec9ddf30e923ca3f66687c16be9f7cd350f48367731e` |
| `logs/tk_reconciliation/reconciliation_20260922.jsonl` | 2026-09-22 23:54:47 / 231,202,082 bytes | `8be194cb6cc2791495be7d44ec96b4f5ff3dc228ed9efdad108ebc2ebbe0539c` |
| `logs/tk_reconciliation/reconciliation_20260923.jsonl` | 2026-09-23 23:45:26 / 161,338,359 bytes | `060425a43f2152314a4041a2e67ec19ffdab25b3679f33740360aecd90da4416` |

查询摘要：`trading_signals.db.live_signal_history` 在 9/22 有 5,642 条、9/23 有 2,107 条；9/23 的 2,107 条状态均为 `NEW`。`signal_strategy.db.mock_trade_log` 在 9/23 有 4 条，全部 `SELL` 且 `is_simulated=1`。`signal_message` 共 388,993 条，`event_key` 非空数与不同键数均为 388,993；9/22 有 18,104 条、9/23 有 380 条。`trade_records` 共 1,545 条，最新买入日为 7/21、最新卖出日为 7/22；不能代表 9/23 TK PAPER 成交。以上确认表内唯一键去重，不证明跨来源语义去重。

数据库查询命令的等价只读口径：`SELECT status, COUNT(*) FROM live_signal_history WHERE date(timestamp)='2026-09-23' GROUP BY status`；模拟成交按 `date, action, is_simulated` 分组；消息幂等以 `COUNT(*)/COUNT(event_key)/COUNT(DISTINCT event_key)` 统计。数据库和日志没有被复制到工作区。

### 当前会话复采（2026-09-24 06:13 HKT）

只读复采发现同一 TK 可执行文件同时从安装目录和 `G:\Temp\instock_Nuitka` 运行，后者 6 个进程；另有 6 个 ATS、1 个安装目录 TK 进程、2 个策略进程和 2 个窗口管理进程。`Get-Process` 未取得命令行；未启动、停止或改写任何进程。

| 映像路径 | 进程数 / PID | 大小 / 修改时间（HKT） | SHA256 |
| --- | --- | --- | --- |
| `D:\JohnsonProgram\instockMonitorTK\ATS_Terminal.exe` | 6 / 1656, 1764, 6756, 17204, 17292, 25160 | 68,121,271 bytes / 2026-09-23 23:18:24 | `CA9498D10489245DDB9C214E0052C3B0DD95F0506746004F03F74E3913B2E72A` |
| `D:\JohnsonProgram\instockMonitorTK\instock_MonitorTK_Nuita.exe` | 1 / 10548 | 95,526,400 bytes / 2026-09-23 12:04:28 | `80CCD8712A6CE1233B9CB1B66CFEB1AC137DC02A358989654FA00122E2CA1485` |
| `G:\Temp\instock_Nuitka\instock_MonitorTK_Nuita.exe` | 6 / 12136, 16828, 17428, 19160, 22784, 23044 | 257,284,096 bytes / 2026-09-23 23:27:32 | `8D4C7C40ED6E8668799BB6E6DDE87FAA7556DCB40293394C7A7DC42E7A3E6784` |
| `D:\JohnsonProgram\instockMonitorTK\人气共振2.22.exe` | 2 / 2908, 20208 | 57,949,794 bytes / 2026-09-19 00:22:45 | `77E2939EF3409DA19E59568295AE3D4AB5E0CDC63720A32EF5D48F0E335DCB73` |
| `D:\JohnsonProgram\instockMonitorTK\manage_window_layout.exe` | 2 / 16472, 23476 | 34,696,328 bytes / 2026-09-23 10:42:23 | `A8043143C1846605511546BD2F73406706ACA4C0F60E7B281E556FED3F4CF606` |

该快照表明运行中存在不同路径/哈希的 TK 构建，不能证明这些实例与本工作区提交对应；G00 构建身份门仍阻断。

## 冻结接口

接口消费者仅依赖本节字段；缺失、损坏或版本不兼容一律拒绝执行或降级为 `MONITOR_ONLY + EXECUTION_BLOCKED`。

### PositionFactsV2

- `snapshot_version: "2.0"`
- 每个 `positions[code]` 至少含 `code`、`trade_date`、`total_qty`、`sellable_qty`、`today_buy_qty`、`unresolved_qty`、`lots`、`t1_fact_status`。
- `sellable_qty + today_buy_qty + unresolved_qty <= total_qty`；未确认批次只进入 `unresolved_qty`，不得推为可卖。
- `lots[]` 包含 `qty`、`buy_date`、`sellable`、`today_buy` 和来源标识；当日新买份额不可卖。

### SignalDecisionEventV1

- 必需字段：`event_id`、`candidate_id`、`snapshot_id`、`state`、`action`、`reason_code`、`event_time`、`source`。
- 同一事件重放必须幂等；状态变化使用新事件或明确定义的升级语义，不可被静态幂等键吞掉。
- 价格无效/为零的输入不得进入可执行实时信号历史。

### MarketDecisionContextV1

- 必需字段：`feature_time`、`raw_volume`、`normalized_volume`、`tide_state`、`tide_version`、`cross_day_state`、`structure_anchors`、`quality_flags`。
- 时间或行情质量未知时只能降级，不可把缺省值解释为通过。

### DirectiveAuditEnvelopeV1

- 必需字段：`directive_id`、`candidate_id`、`plan_id`、`code`、`action`、`qty`、`price`、`expires_at`、`gate_reason`；执行决策维度 `strategy_tag`、`tide_state`、`cross_day_state` 需按当时输入采集，不能在 TK 执行时用新行情补写。退出指令的跨日状态可标记 `NOT_APPLICABLE_EXIT`；BUY 缺值仍视为证据不完整。
- 终态需关联 `execution_id`/`order_id` 和 `execution_status`；行情 IPC 确认不算指令派发或成交。
- 同代码同周期 EXIT 优先；T+1 可卖量必须来自 PositionFactsV2。

### ReleaseManifestV1

- 必需字段：Git 提交、EXE SHA256、冻结夹具哈希、报告哈希、各硬门结果。
- 缺项或账户/T+1/信号/指令/影子任一硬门失败，则状态为 `MONITOR_ONLY`，禁止发布为可执行 PAPER 构建。

## 证据与回滚点

- 仓库代码基线为上述 HEAD；当前工作区已有 Agent Hub/监控相关未提交修改，G00 不覆盖这些改动。
- 本任务未改业务源码或生产数据。
- 回滚：删除本 G00 交付文件；保留生产数据和已有工作区修改。
- 验收：接口契约已冻结；线上基线证据仍缺失，故 G00 不得标为完整通过，发布门继续关闭。

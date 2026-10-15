# Muse 2026-10-14 手册的本地适配审核

更新：2026-10-15。依据：用户最新同步的 strategy-manual-2026-10-14.md、strategyv1.10.yaml、本地 v1.9 运行源码及 20261013 交接包。来源原文不覆盖；✅仅代表来源声明，不能代替本地实现/运行验收。

结论：最新版手册的五项文档更正已核对，来源文档问题关闭；实现适配仍为 Request Changes，原因是交接包缺依赖及已复现的 P34/P12 退出问题。p22_l2 的接入或权重调整仍待用户/复盘决策，不修改运行参数。

| 级别 | 差异 | 本地处置 |
| --- | --- | --- |
| P1 | 来源 v1.10；本地运行配置仍是 v1.9 | 新交接包已提供 P34 触发函数和 MA5 退出代码，但仍缺 probe/crypto_structure 等依赖；存在下述已复现退出问题，不覆盖本地运行配置。 |
| 已关闭 | P30 自动退出描述 | 最新表格明确基础检测只读、v1.7+ 策略空单自动平、镜像单只预警，v1.9 增加冷却。 |
| 文档已关闭 | upstream/sentiment_local 版本归属 | 最新手册已注明属于 v1.10 环境、v1.9 本地缺失；实现移植仍待补齐依赖。 |
| 已关闭 | 情绪落盘路径 | 最新手册已改为 sentiment_<date>_premarket.json，与本地生产者/消费者一致。 |
| 文档已关闭 | fail-closed 边界 | 第 7 节已明确 P27 缺数据和 kill 文件异常返回 False；保留运行逻辑。第 6 节第 2 条建议加“例外见第 7 节”，避免单独引用时误读。 |
| P2 | P29 与 P28 混为 YAML 重复键，不只是无 id | 本地两份 YAML 已拆为独立 P29，并补 P10；版本及交易阈值不变。来源 v1.10 原件保留供差异比对。 |
| P2 | p22_leader 权重预留但无写入 | 最新手册承认问题；保留本地备注和权重，不擅自接因子、调参或升版本。 |
| P2 | updated 日期 | v1.10 文件日期确与 10-09 changelog 不符；本地 v1.9 的 10-04 与自身 changelog 一致，不能同步改成 10-09。 |
| 已关闭 | P34 编号冲突 | 最新手册明确 P34=反抽确认开空，事件冲击=P36；不通过文档编号变更伪造本地实现。 |

最新版已删去“可安全复刻”断言，并明确 p22 死权重会影响评分与归因、不能作为备注修补自动实施。用户当前明确选择等待接入决策；本地继续保留权重与备注，不置零、不补接因子、不升版本。

来源新增情绪章节的“情绪只能否决，不能制造买点”已用于独立跟单：Go 原生情绪只作否决，P8/P25 行情结构另外确认。LXC 没有 Muse 情绪文件，独立模拟使用 Go 盘中高位风险状态，不映射 Muse 分数，不声称实现 P2/P3/P5/P27，也不替换 Muse 原策略。

工作流仍须按本地 cron 契约适配：CN 16:20/17:20、US 06:15 香港时间、CRYPTO 00:15 UTC；实际生产 cron 本次未改。竞价本地最少 3 轮，confirm_preopen_orders 为函数。未提供 Hook shell 与 ashare_gate.py 的计划不能直接启用。

自动跟单实现、测试及部署证据见 [任务记录](../tasks/2026-10-14_2355_自动跟单模拟盘规划与实施.md)。不复制 feed-pulse/heartbeat，不提交 .env、push_config.json、密钥或账本。

## 补充：20261013 底层交接包审核

来源：`D:/Document/Downloads/easy-stock-strategy-20261013`。只读检查，未执行整个参考引擎、未覆盖本地代码或部署规则。

- 包内 strategyv1.10.yaml 与项目中同名文件逐字节一致。ref/paper_trade.py 相对本地服务版本为 394 行新增、19 行删除；cycle_structure.py 和 sector_leader.py 有差异，protect/dayang/gate_attribution 三模块一致。
- 现已提供 s_resist_reject_trigger、s_support_break_trigger、s_bounce_fail_trigger、MA5 持有开关和 shadow 读取代码；之前“没有提供触发函数”的判断据此更新为“触发函数已提供，完整依赖仍不齐”。
- 仍缺 probe.py、crypto_structure.py、trend_base.py、screen.py，以及 upstream.py、sentiment_local.py、更新后的 crypto_short_watch.py。核心开空依赖缺失会返回无信号；影子记录依赖缺失也不能视为完整运行验收。
- **P1，已隔离复现**：ref/paper_trade.py:2841 的 P12 排除列表只有 support_break/resist_reject，遗漏 bounce_fail。P34 函数声明入场不吃 S-P25，退出却可能因 S-P25 未通过立即平仓。用合成仓、MA5 压制=True、无其它止盈止损、S-P25=False 调用单独 AST 提取的 manage_shorts(dry=True)，实际产生 P12 平仓事件；测试未联网、未读写账户。
- 修复方向：明确记录每个入场通道实际经过的趋势门，退出只对适用通道执行相应证伪规则；最小修补至少将 bounce_fail 纳入现有排除列表，并覆盖“MA5 压制仍在、不应被未参与入场的 S-P25 踢出”的回归场景。未修改下载包原件或本地运行引擎。
- p22_l2 在该包仍只见读取，没有字面量字典写入；来源手册“预留”备注继续保留。README 声称 v1.10，策略总览仍标 v1.9，且 P30 标题“只读”与段内自动平仓相冲突。

结论仍为 Request Changes：可用作规则对照和最小移植参考，不能整包安全复刻；不影响已经部署的独立 A 股 paper-follow-v1 worker。

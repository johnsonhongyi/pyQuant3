# Task

将主动退出防守引擎 ProactiveExitEngine 与 IPOTradingCenter 全面接线，实现 8 层主动出局、保本位推移与 A 股 T+1 卖出防守硬锁。

## Metadata

- Task-ID: 003
- Owner: unassigned
- Priority: P0
- Risk: MEDIUM
- Depends-On: 002
- Created-By: codex
- Created-At: 2026-09-20

## Context

任务 001 审计确认 GAP-RSK-01、GAP-RSK-02、GAP-RSK-03：交易中心目前出局方式二元化（仅单一 SELL 全清），未与 ProactiveExitEngine 8层递进式主动防守体系连通，且缺乏 A 股 T+1 卖出防守硬锁。持仓未注册进主动防守池，无法在反弹无力、量价背离、盘口走弱时分批减仓锁定利润，也无法根据 TradePlan 进行保本位动态推移。当前系统仅模拟账本，真实网关、自动合并和实盘开关保持关闭。

## Files Allowed

- ats/strategy/ipo_trading_center.py
- ats/proactive_exit_engine.py
- tests/test_channel_secondary_buy_strategy.py
- .agent_hub/artifacts/003/implementation_plan.md
- .agent_hub/artifacts/003/walkthrough.md
- .agent_hub/artifacts/003/test_result.md
- .agent_hub/artifacts/003/changed_files.txt

## Files Forbidden

- trade_gateway.py
- ats/strategy/ipo_vwap_detector_engine.py
- 真实券商接口、凭据、自动合并和实盘开关
- 其它所有未在 Files Allowed 中列出的业务文件

## Requirements

- 在 IPOTradingCenter 初始化时持有或复用 ProactiveExitEngine 实例。
- 买入建仓（BUY_SCOUT, BUY_CONFIRM）时，自动将持仓信息、higher_low_stop 及 IPOTradePlan 注册到 ProactiveExitEngine。
- 交易中心在执行调度循环中，支持调用 ProactiveExitEngine.evaluate_tick，接收 REDUCE_30、REDUCE_HALF、EXIT_ALL 等递进式出局动作。
- 支持保本位动态推移：当行情触及 target_1 目标位后，自动将 higher_low_stop 提升至持仓成本位之上，锁死利润。
- 增加 A 股 T+1 卖出防守硬锁：若持仓建立日期为当天（entry_date == today_str 且非隔日），除触及灾难性硬止损外，物理拦截日内卖单生成。
- 平仓复盘强化：平仓归档时记录对应的 TradePlan 快照和出局层级/规则。

## Definition of Done

- [ ] IPOTradingCenter 买入成功建仓时自动向 ProactiveExitEngine 注册持仓及 TradePlan 防守线
- [ ] 交易中心调度循环支持处理 REDUCE_HALF、REDUCE_30 与 EXIT_ALL 指令
- [ ] 触碰 target_1 自动完成保本防守推移（提高 stop 价格）
- [ ] T+1 卖出物理硬锁生效，日内新建仓位受 T+1 保护不产生非法日内卖单
- [ ] tests/test_channel_secondary_buy_strategy.py 补充端到端测试并通过关联测试
- [ ] 未修改真实交易网关、未触碰实盘开关

## Verification

````powershell
python -m pytest tests/test_channel_secondary_buy_strategy.py tests/test_channel_secondary_buy_ui_and_engine.py -q --basetemp=.pytest_temp/agent_hub_task_003
python -m compileall -q ats/strategy/ipo_trading_center.py ats/proactive_exit_engine.py
````

## Rollback

仅撤销任务 003 在 Files Allowed 中产生的增量，不覆盖用户或其他 Agent 的既有改动；真实账本和交易数据不得删除。

## Output Contract

在 .agent_hub/artifacts/003/ 生成：

- implementation_plan.md
- walkthrough.md
- test_result.md
- changed_files.txt

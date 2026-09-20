# Task

修复 P0/P1 回归审计发现的退出重复评估与 T+1 bypass 伪造风险。

## Metadata

- Task-ID: 006
- Owner: unassigned
- Priority: P0
- Risk: MEDIUM
- Depends-On: 003,004
- Created-By: codex
- Created-At: 2026-09-20

## Context

任务 003/004 完成后的独立审计发现：已有待执行退出指令时仍可能再次调用退出引擎；执行接口仅检查 bypass 布尔值，未同时校验灾难止损规则 ID。

## Files Allowed

- ats/strategy/ipo_trading_center.py
- tests/test_channel_secondary_buy_strategy.py
- .agent_hub/artifacts/006/implementation_plan.md
- .agent_hub/artifacts/006/walkthrough.md
- .agent_hub/artifacts/006/test_result.md
- .agent_hub/artifacts/006/changed_files.txt

## Files Forbidden

- trade_gateway.py
- 真实券商接口、凭据和实盘开关
- 其它业务文件

## Requirements

- 每只持仓同时只允许一个待执行退出动作。
- T+1 bypass 必须同时满足许可布尔值和灾难规则白名单。

## Definition of Done

- [ ] 重复 tick 不重复调用退出引擎
- [ ] 伪造 bypass 不能绕过 T+1
- [ ] 关联测试通过

## Verification

```powershell
python -m pytest tests/test_channel_secondary_buy_strategy.py tests/test_channel_secondary_buy_ui_and_engine.py tests/test_agent_hub.py tests/test_agent_orchestrator.py -q --basetemp=.pytest_temp/post_audit_003_004
```

## Rollback

仅撤销任务 006 的增量。

## Output Contract

在 .agent_hub/artifacts/006/ 生成四份标准证据文件。

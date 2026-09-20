# Task

审计新股/次新股检测到交易决策中心的现有信号链，形成事实清单和缺口矩阵，不修改业务逻辑。

## Metadata

- Task-ID: 001
- Owner: unassigned
- Priority: P0
- Risk: LOW
- Depends-On: none
- Created-By: codex
- Created-At: 2026-09-20

## Context

长期通道次级买点 P0/P1 已有实现和测试，但外在事件感知、市场阶段切换、首日/次日回放和实盘风险闸门尚未形成统一闭环。先建立可引用的系统事实，避免重复开发和错误接线。

## Files Allowed

- `.agent_hub/artifacts/001/architecture_audit.md`
- `.agent_hub/artifacts/001/signal_gap_matrix.md`
- `.agent_hub/artifacts/001/test_result.md`
- `.agent_hub/artifacts/001/changed_files.txt`

## Files Forbidden

- `ats/**/*.py`
- `tests/**/*.py`
- `trade_gateway.py`
- 真实券商接口、凭据和实盘开关

## Requirements

- 追踪 `new_stock_fetcher -> ipo_vwap_detector_engine -> channel_secondary_buy_strategy -> ipo_trading_center -> proactive_exit_engine`。
- 列出每一层输入、输出、缓存、刷新频率、失败降级和线程边界。
- 区分已实现、部分实现、未实现，不得仅根据文件名推断。
- 标出首日、次日、长期通道次级买点三类信号是否进入 TradePlan 和退出保护。
- 给出不超过 5 个后续原子任务建议，包含允许文件和验收标准。

## Definition of Done

- [ ] 事实清单包含代码位置证据
- [ ] 信号缺口矩阵覆盖检测、决策、风控、执行、复盘
- [ ] 未修改任何业务代码
- [ ] 测试/导入检查结果已记录

## Verification

```powershell
python -m pytest tests/test_channel_secondary_buy_strategy.py tests/test_channel_secondary_buy_ui_and_engine.py -q --basetemp=.pytest_temp\agent_hub_task_001
```

## Rollback

仅删除 `.agent_hub/artifacts/001/` 中本任务生成的报告。

## Output Contract

在 `.agent_hub/artifacts/001/` 生成：

- `architecture_audit.md`
- `signal_gap_matrix.md`
- `test_result.md`
- `changed_files.txt`

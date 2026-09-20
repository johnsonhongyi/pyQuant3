# Task

将真实 60F K线数据流注入新股次新股通道次级买点检测，消除日K冒充 60F 的周期失真。

## Metadata

- Task-ID: 004
- Owner: unassigned
- Priority: P1
- Risk: MEDIUM
- Depends-On: 002
- Created-By: codex
- Created-At: 2026-09-20

## Context

任务 001 审计确认检测引擎把 `df_day` 同时作为 `df_60m` 传给次级买点策略，导致下降通道斜率、回踩抬高底和放量突破均使用错误周期。现有 TDXRealtimeFetcher 已提供带 30 秒缓存的 `fetch_kline_bars(category="60m")`，本任务只负责复用并打通后台数据流。

## Files Allowed

- ats/strategy/ipo_vwap_detector_engine.py
- ats/ui/ipo_subnew_detector_dialog.py
- tests/test_channel_secondary_buy_ui_and_engine.py
- .agent_hub/artifacts/004/implementation_plan.md
- .agent_hub/artifacts/004/walkthrough.md
- .agent_hub/artifacts/004/test_result.md
- .agent_hub/artifacts/004/changed_files.txt

## Files Forbidden

- trade_gateway.py
- ats/tdx_realtime_fetcher.py
- 真实券商接口、凭据、自动合并和实盘开关
- 其它所有未在 Files Allowed 中列出的业务文件

## Requirements

- 复用 TDXRealtimeFetcher 的 60m 缓存接口，单线程顺序批量预取。
- 日线与 60F 使用独立参数传入检测引擎。
- 缺少真实 60F 时不得用日线静默替代。
- Worker 记录独立 60F 预取耗时，不在 UI 主线程执行网络 I/O。

## Definition of Done

- [ ] 真实 60F 注入 evaluate_channel_secondary_buy 的 df_60m
- [ ] 日线不再冒充 60F
- [ ] Worker 批次传递 day_df 与 df_60m
- [ ] 关联回归与编译通过

## Verification

```powershell
python -m pytest tests/test_channel_secondary_buy_ui_and_engine.py tests/test_channel_secondary_buy_strategy.py tests/test_ipo_vwap_bottom_base_preorder.py tests/test_new_stock_module.py -q --basetemp=.pytest_temp/audit_004_full
python -m compileall -q ats/strategy/ipo_vwap_detector_engine.py ats/ui/ipo_subnew_detector_dialog.py
```

## Rollback

仅撤销任务 004 的允许文件增量。

## Output Contract

在 .agent_hub/artifacts/004/ 生成 implementation_plan.md、walkthrough.md、test_result.md、changed_files.txt。

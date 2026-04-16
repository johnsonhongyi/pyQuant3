# 语音播报与信号日志同步修复计划 (20260416_1320)

目前信号日志在语音播报时无法自动滚动定位到对应条目，主要原因可能是用户交互锁定时间过长，以及日志内容在合并去重后与语音播报的匹配片段不一致。

## Proposed Changes

### [trade_visualizer_qt6.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/trade_visualizer_qt6.py)

#### [MODIFY] `_poll_voice_feedback`
- 将滚动锁定的时间阈值从 3.0s 降低到 1.5s。
- 增加日志输出，以便在调试时确认反馈是否到达。

#### [MODIFY] `_on_signal_log_added`
- 优化 `match_snippet` 的生成逻辑，确保即使在消息被处理后（如合并去重）仍能被搜索到。

### [signal_log_panel.py](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/signal_log_panel.py)

#### [MODIFY] `highlight_row_by_content`
- 优化 `findItems` 和内容匹配逻辑。考虑到日志可能包含 `(x次)` 前缀或合并后的多条消息，应增强模糊匹配能力。
- 确保 `scrollToItem` 的位置在表格顶端，使用 `PositionAtTop`。

## Verification Plan

### Manual Verification
1. 启动监控系统并触发一些模拟型号（或等待实时信号）。
2. 观察语音播报开始时，信号日志面板是否能够自动选中并滚动到对应股票的行。
3. 手动点击日志面板，确认系统会暂时（约1.5s）停止自动滚动，随后自动恢复。

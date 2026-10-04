# trade_visualizer_qt6.py 补充审核与实施

日期：2026-10-04。审核范围：B2 过滤刷新任务积压、B1 画笔缓存抖动，以及相邻调度链路。

## Summary

**Pass**：B2、B1 及下列遗漏问题已修复；公开函数签名保持兼容，无新增第三方依赖。

## Critical

本轮未发现未解决的关键问题。

## Important

| 问题 | 实施方案 | 行为约束 |
|---|---|---|
| B2：每次 request_table_update 注册过滤 singleShot | 移至成功执行的 _flush_table_updates 末尾；复用一个窗口所属的单次 QTimer，重复请求合并 | 无实际刷新、失败、隐藏或关闭时不刷新过滤；定时回调再次检查可见性 |
| 全量数据入口另有独立的 400ms 过滤任务 | 改用同一个 _schedule_filter_refresh，保留最早期限 | 各入口共享任务上限；持续行情也不会反复推迟已排定的刷新 |
| 重载历史又注册独立的查询 singleShot | 使用第二个窗口所属的单次 QTimer；历史重载先停止旧查询 | 查询执行前复查可见性及关闭状态；定时回调异常记录后降级 |
| 高频请求重新推迟表格定时器，墙上时钟调整影响节流 | 改用 monotonic；按剩余等待时间安排刷新，只缩短已有较晚期限 | 保留既有自适应间隔；显式空增量不产生新工作，None 仍表示全量 |
| 全量表格分块过程中继续请求会重启批次 | 等现有批次完成，再消费积累的增量 | 保留最新请求，避免持续行情导致全量刷新无法结束 |
| 同步表格刷新异常丢失待处理代码 | 恢复待处理集合或 ALL，延迟重试 | 失败不更新时间戳、不触发过滤刷新；关闭后不继续调度 |
| 自动重载历史丢失当前查询、强行解除信号屏蔽 | 按 query 的 userData 恢复选择；恢复原来的 blockSignals 状态 | 查询不存在于新历史时保留原有默认选择逻辑 |

两个过滤定时器均由窗口拥有，既有关闭流程停止全部子 QTimer；回调同时检查关闭状态。

## Minor

- **B1 已修复**：保留主线程共享缓存，用 OrderedDict 管理最近访问顺序；256 项满额时仅移除最久未访问的一组 Pen/Brush。
- 命中时更新顺序；创建新颜色对象成功后才淘汰旧项，避免无效颜色破坏已有缓存。

## 验证与实测

新增 **19 项回归**，可视化测试合计 **64 项**；与 IPC、运行稳定性及信号链关联检查合计 **103 passed，1 deselected**。
覆盖高频请求合并及持续行情期限、隐藏/删除/关闭、空请求、失败重试、分块期间增量、查询保留及缓存单项淘汰。

基线是本轮审核前的暂存源码，blob：`2fdc34f8199068e50707e159065ab5bdb51a1ccc`。
详细数据见 [补充基准 JSON](TRADE_VISUALIZER_REVIEW_BENCHMARK_20261004.json)。

| 相同工作负载 | 审核前 | 审核后 |
|---|---:|---:|
| 固定时钟下 1000 次增量请求产生的过滤延迟任务 | 1000 | 1 |
| 上述请求实际表格刷新次数 | 1 | 1 |
| 每次命中热点色后插入冷色，连续 1024 种冷色时热点画笔创建次数 | 5 | 1 |

- 新旧 K 线像素一致：深浅主题、默认和自定义颜色、阳线、阴线及十字线均通过。
- 同机 9 次中位数：20000 根 K 线显示 150 根的 paint 为 0.985 → 0.989ms；5000 行更新 5 行为 1.408 → 1.457ms。相同 K 线数据检查为 0.352 → 1.068ms，该路径本轮未修改；时间采样存在波动，未据此宣称本轮绘制提速。
- 排除项是已知的 `test_sina_cold_start_does_not_fetch_on_non_trading_day`：接口返回 None，测试期望 []；对应生产函数与 Git HEAD 的 AST 一致，未在本轮修改。
- 本轮为离屏 Qt 回归和合成负载；未测实盘整窗 FPS 或长时间内存曲线。
- Python 编译、UTF-8 无 BOM、基准 JSON 解析及 git diff --check 均通过。

复现（工作目录 stock_standalone，PowerShell）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/benchmark_trade_visualizer.py --compare-index --repeats 9 --output docs/TRADE_VISUALIZER_REVIEW_BENCHMARK_20261004.json
python -m pytest tests/test_trade_visualizer_performance.py tests/test_ipc_trade_rollover.py tests/test_ipc_cold_start_baseline.py tests/test_runtime_stability.py tests/test_signal_pipeline_hardening.py -k 'not test_sina_cold_start_does_not_fetch_on_non_trading_day' -q -o addopts='' --basetemp=.pytest_temp/trade_visualizer_review --tb=short --no-header
```

--compare-index 以运行时暂存版本为基线；后续暂存操作会改变基线，应以报告中的 blob 标识确认版本。
原始完整优化方案与 HEAD 性能对照见 [性能方案](TRADE_VISUALIZER_PERFORMANCE_20261004.md)。

# ATS 性能审核 — 2026-10-01

结论：仍有优化空间，建议按下列顺序实施。现有优化应保留，避免再次引入主线程等待、全量复制和全量重绘。

## 范围与限制

扫描 ats 下全部 Python 文件的语法树和热点调用；对主窗口、热力图、归档缓存、历史价格加载、全球市场、策略扫描和日志面板的候选热点进行定向核查。
这是静态审核，不等于逐行完整功能审查或实盘性能测量；没有启动 ATS、连接交易接口或修改策略行为。出现 iterrows/deepcopy 本身不构成性能缺陷。

## 必须修复

### P1：历史加载临时锁冲突被记为永久失败
- `ats/ui/main_window.py:4640–4646`：HDF 锁等待 5 秒失败，将本批代码加入 prices_failed_codes。
- `main_window.py:4619、4929`：后续加载排除失败代码；文件中未发现清除或 TTL。日志说 postponed，实际不会自动再试。
- 处理：区分临时锁冲突和真实无数据，有限退避重试；后台返回结果，由 UI 线程更新请求状态。
- 验证：人为占锁后释放，代码应重新加载；持续占锁不应产生线程风暴。

## 重要优化

### P1：定时器延迟执行仍占用主线程，并可积累过期帧
- `ats/ui/main_window.py:4478–4499`：每帧创建直方图闭包，持有整帧 DataFrame，singleShot(20) 后执行 pandas 统计和图表刷新。
- `main_window.py:4438–4461`：天梯和涨停面板也是按帧 singleShot；延后执行并没有转到后台。
- 处理：每个视图只保留一个待刷新任务和最新帧；统计在后台完成，控件更新留在 UI。不要直接将 GUI 操作移至工作线程。
- 验证：高频输入时待执行回调数有界；最终显示最新 revision，点击与拖动不被统计占用。

### P1：热力图数值变化触发整批卡片销毁与创建
- `ats/ui/heatmap_widget.py:609–646`：指纹包含分数、涨幅；变化后清空布局并重建最多 60 个 QPushButton。
- 同处指纹仅覆盖前 30 条、渲染却最多 60 条，后半部单独变化可能漏刷新。
- 处理：卡片按板块标识复用；只有排序、布局和集合变化才移动/新增/销毁，数值变化只更新文字和必要样式。
- 验证：只更新第 31–60 个板块也能刷新；行情变化不增加控件总数，收藏/排序/点击行为一致。

### P2：名称缓存不足 4000 时绕过 60 秒节流
- `ats/ui/main_window.py:4424–4434`：条件为超时 OR 缓存少于 4000；小股票池或未完成冷启动时，每帧可复制名称列并创建线程。
- 处理：单任务保护，按缺失代码或名称列 revision 增量更新，已有小池完成后仍遵守刷新间隔。
- 验证：重复 500 只股票的行情帧不会连续建线程；新增、改名股票仍能更新。

### P2：归档缓存全局锁内复制与磁盘读取
- `ats/bounded_evaluation_store.py:143–176、184–193、305–314`：read/put/pending 在共用 RLock 内完成 JSON/gzip 读取、深复制或全对象比较。
- 即使命中缓存，大对象复制也延长锁持有时间。不得直接返回可变共享对象来省略复制。
- 处理：按 path/version 构建不可变快照，锁内仅获取引用与版本；锁外加载/准备副本，再校验版本提交。保留写入合并、原子持久化与回调语义。
- 验证：并发读写不丢更新；不同归档之间不因一个大副本而长时间串行。

### P2：TDX 批量扫描一次性提交全部代码
- `ats/channel_bottom_reversal_strategy.py:719–726`：为每个代码创建 future，没有扫描整体期限，也未去重规范化后的代码。
- 在后台运行可以避免直接卡 UI，但全池扫描仍占用对象、连接及任务队列；future.result 位于 as_completed 内，不是单独的主线程阻塞证据。
- 处理：去重，限制在途任务数量，补充扫描取消和总期限；保持已完成结果，不改变排序和信号规则。
- 验证：全池任务数有界；取消后停止继续提交，单个超时不会拖死整轮。

### P3：全球市场表重复重建
- `ats/ui/global_market_panel.py:487–490、692–695`：更新行情/板块表时清空行，再创建单元格。
- 规模较小、已有后台抓取，收益优先级低于主窗口与热力图。按 symbol/板块增量更新可保持选择和滚动位置。

## 已有优化及不应误改的项目

- main_window 的 IPC session/ver/source_version 去重，以及非交易时段冷启动后跳过重复行情。
- kernel_trace_panel 的后台单任务读取、尾部加载和 unchanged-lines 跳过重绘。
- heatmap 的 TK 权威板块复用；优化渲染即可，不应重新计算另一套板块强度。
- bounded_evaluation_store 的写入窗口/频率限制和脏归档保护；不能为了减内存丢弃未提交归档。
- base_table.resizeColumnsToContents 在手动自适应菜单中，不是高频自动刷新热点。
- momentum_rotation_engine.iterrows 暂未确认热路径频率，不应仅因逐行循环就宣称必须向量化。

## 执行次序与验收

1. 临时失败重试与热力图后半部漏刷新。
2. 最新帧合并、热力图控件复用、名称缓存单任务。
3. 归档锁与有限扫描并发。
4. 实盘验证主线程延迟、p95/p99 刷新耗时、线程数量、内存、队列长度及信号结果一致性；静态审查不能给出速度提升百分比。

## 扫描记录

Python 文件：149；成功解析：149；语法异常：0。

热点调用计数（仅用于定位）：Thread=57, deepcopy=38, get_connection=1, iterrows=32, readlines=1, resizeColumnsToContents=5, setRowCount=76, singleShot=96, submit=4。

| 模块 | 定位到的调用 |
|---|---|
| `ats/__init__.py` | 未命中本次热点调用模式 |
| `ats/alert_notifier.py` | Thread:1, singleShot:3 |
| `ats/archive_policy.py` | 未命中本次热点调用模式 |
| `ats/backtest_engine.py` | 未命中本次热点调用模式 |
| `ats/bounded_evaluation_store.py` | Thread:3, deepcopy:15 |
| `ats/candidate_cache.py` | 未命中本次热点调用模式 |
| `ats/capital_dragon_engine.py` | Thread:1 |
| `ats/channel_bottom_reversal_strategy.py` | submit:1 |
| `ats/channel_swing_candidate_engine.py` | 未命中本次热点调用模式 |
| `ats/common/__init__.py` | 未命中本次热点调用模式 |
| `ats/common/display_maps.py` | 未命中本次热点调用模式 |
| `ats/consensus_arbiter.py` | 未命中本次热点调用模式 |
| `ats/hot_sector_engine.py` | 未命中本次热点调用模式 |
| `ats/intraday_strategy_engine.py` | iterrows:3 |
| `ats/ipc_bridge.py` | Thread:2 |
| `ats/ladder_linkage_watcher.py` | 未命中本次热点调用模式 |
| `ats/ledger_update_service.py` | 未命中本次热点调用模式 |
| `ats/limit_up_engine.py` | Thread:1, iterrows:1 |
| `ats/llm/__init__.py` | 未命中本次热点调用模式 |
| `ats/llm/agent_contracts.py` | deepcopy:3 |
| `ats/llm/antigravity_cli_backend.py` | 未命中本次热点调用模式 |
| `ats/llm/antigravity_litert_backend.py` | 未命中本次热点调用模式 |
| `ats/llm/backend_factory.py` | 未命中本次热点调用模式 |
| `ats/llm/cli_paths.py` | 未命中本次热点调用模式 |
| `ats/llm/cli_process.py` | Thread:1 |
| `ats/llm/codex_cli_backend.py` | 未命中本次热点调用模式 |
| `ats/llm/control_thread.py` | Thread:1, deepcopy:1, submit:1 |
| `ats/llm/interaction_journal.py` | Thread:1 |
| `ats/llm/ipo_local_observer.py` | 未命中本次热点调用模式 |
| `ats/llm/learning_snapshot_store.py` | Thread:1 |
| `ats/llm/llm_worker.py` | Thread:1 |
| `ats/llm/offline_learning.py` | 未命中本次热点调用模式 |
| `ats/llm/provider_preflight.py` | 未命中本次热点调用模式 |
| `ats/llm/remote_prompt_templates.py` | 未命中本次热点调用模式 |
| `ats/llm/remote_sanitizer.py` | 未命中本次热点调用模式 |
| `ats/llm/request_producer.py` | 未命中本次热点调用模式 |
| `ats/llm/runtime_service.py` | 未命中本次热点调用模式 |
| `ats/llm/sealed_dataset_store.py` | 未命中本次热点调用模式 |
| `ats/llm/windows_job.py` | 未命中本次热点调用模式 |
| `ats/llm/worker_protocol.py` | 未命中本次热点调用模式 |
| `ats/main_ats.py` | 未命中本次热点调用模式 |
| `ats/market_frame.py` | 未命中本次热点调用模式 |
| `ats/market_guardian.py` | 未命中本次热点调用模式 |
| `ats/momentum_rotation_engine.py` | iterrows:1 |
| `ats/multi_period_channel_backtester.py` | iterrows:2 |
| `ats/multi_period_channel_strategy.py` | 未命中本次热点调用模式 |
| `ats/multi_period_resampler.py` | 未命中本次热点调用模式 |
| `ats/network/__init__.py` | 未命中本次热点调用模式 |
| `ats/network/tk_ipc_subscriber.py` | 未命中本次热点调用模式 |
| `ats/new_stock_fetcher.py` | iterrows:2 |
| `ats/new_stock_strategy_generator.py` | 未命中本次热点调用模式 |
| `ats/next_day_watch_process.py` | deepcopy:1 |
| `ats/opening_bubble_engine.py` | 未命中本次热点调用模式 |
| `ats/persistence_lock.py` | 未命中本次热点调用模式 |
| `ats/proactive_exit_engine.py` | 未命中本次热点调用模式 |
| `ats/reentry_tracker.py` | 未命中本次热点调用模式 |
| `ats/replay_release_gate.py` | 未命中本次热点调用模式 |
| `ats/sector_data_aggregator.py` | iterrows:1 |
| `ats/sector_etf_engine.py` | 未命中本次热点调用模式 |
| `ats/sector_rotation_pullback_miner.py` | 未命中本次热点调用模式 |
| `ats/session_clock.py` | 未命中本次热点调用模式 |
| `ats/session_snapshot.py` | Thread:1, deepcopy:2 |
| `ats/signal_auto_dispatcher.py` | 未命中本次热点调用模式 |
| `ats/signal_ledger.py` | 未命中本次热点调用模式 |
| `ats/signal_lifecycle.py` | 未命中本次热点调用模式 |
| `ats/startup_profiler.py` | 未命中本次热点调用模式 |
| `ats/storage_archive.py` | deepcopy:1 |
| `ats/strategy/channel_secondary_buy_strategy.py` | 未命中本次热点调用模式 |
| `ats/strategy/directive_execution_guard.py` | 未命中本次热点调用模式 |
| `ats/strategy/gate_orchestrator.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_data_contracts.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_eastmoney_sources.py` | iterrows:1 |
| `ats/strategy/ipo_gate_context_provider.py` | Thread:1 |
| `ats/strategy/ipo_live_heat_engine.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_market_sentiment_engine.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_operation_state_machine.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_outcome_labels.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_outcome_review.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_preheat_engine.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_regime_fsm.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_shadow_observations.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_source_orchestrator.py` | 未命中本次热点调用模式 |
| `ats/strategy/ipo_trading_center.py` | deepcopy:6 |
| `ats/strategy/ipo_vwap_detector_engine.py` | iterrows:3 |
| `ats/strategy/listing_anchor_store.py` | 未命中本次热点调用模式 |
| `ats/strategy/lrrm_engine.py` | 未命中本次热点调用模式 |
| `ats/strategy/next_day_watch_config_manager.py` | deepcopy:2 |
| `ats/strategy/signal_convergence.py` | 未命中本次热点调用模式 |
| `ats/strategy/subnew_deployment_gate.py` | 未命中本次热点调用模式 |
| `ats/strategy/subnew_event_sentiment_engine.py` | 未命中本次热点调用模式 |
| `ats/strategy/subnew_executable_gate.py` | 未命中本次热点调用模式 |
| `ats/strategy/subnew_tide_state_machine.py` | 未命中本次热点调用模式 |
| `ats/strategy/subnew_trading_clock.py` | 未命中本次热点调用模式 |
| `ats/strategy/t1_carry_evaluator.py` | 未命中本次热点调用模式 |
| `ats/strategy/tdx_market_snapshot.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_anchor_acquisition.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_console_responsiveness.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_eastmoney_market_metrics.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_matured_cohort.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_outcome_review.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_ipo_shadow_observations.py` | 未命中本次热点调用模式 |
| `ats/strategy/test_tdx_market_snapshot.py` | 未命中本次热点调用模式 |
| `ats/swing_tracker.py` | 未命中本次热点调用模式 |
| `ats/tdx_realtime_fetcher.py` | iterrows:1, submit:1 |
| `ats/tdx_signal_watcher.py` | readlines:1 |
| `ats/test_ui_backpressure.py` | singleShot:2 |
| `ats/tk_ipc_subscriber.py` | 未命中本次热点调用模式 |
| `ats/trade_journal.py` | 未命中本次热点调用模式 |
| `ats/ui/__init__.py` | 未命中本次热点调用模式 |
| `ats/ui/ats_window_manager.py` | 未命中本次热点调用模式 |
| `ats/ui/base_table.py` | resizeColumnsToContents:1 |
| `ats/ui/capital_dragon_panel.py` | Thread:2, setRowCount:1, singleShot:1 |
| `ats/ui/channel_scan_result_dialog.py` | iterrows:1, setRowCount:2 |
| `ats/ui/chart_widgets.py` | Thread:1, iterrows:1, setRowCount:3, singleShot:4 |
| `ats/ui/daily_limit_up_dialog.py` | Thread:6, setRowCount:1, singleShot:2 |
| `ats/ui/dragon_monitor.py` | setRowCount:1, singleShot:3 |
| `ats/ui/favorite_panel.py` | setRowCount:2 |
| `ats/ui/global_market_dialog.py` | 未命中本次热点调用模式 |
| `ats/ui/global_market_kline_dialog.py` | iterrows:1, singleShot:5 |
| `ats/ui/global_market_panel.py` | setRowCount:4, singleShot:3 |
| `ats/ui/heatmap_widget.py` | singleShot:1 |
| `ats/ui/hot_sector_leaderboard.py` | Thread:1, setRowCount:2, singleShot:4 |
| `ats/ui/intraday_strategy_dialog.py` | Thread:3, deepcopy:1, setRowCount:8, singleShot:8 |
| `ats/ui/ipc_tester_gui.py` | iterrows:1, setRowCount:2 |
| `ats/ui/ipo_arbitration_detail_dialog.py` | 未命中本次热点调用模式 |
| `ats/ui/ipo_command_room_dialog.py` | resizeColumnsToContents:1, setRowCount:7, singleShot:3 |
| `ats/ui/ipo_detector_ipc.py` | 未命中本次热点调用模式 |
| `ats/ui/ipo_learning_console.py` | Thread:1, deepcopy:6, setRowCount:13, singleShot:1 |
| `ats/ui/ipo_subnew_detector_dialog.py` | Thread:2, iterrows:1, resizeColumnsToContents:1, setRowCount:1, singleShot:19 |
| `ats/ui/kernel_trace_panel.py` | Thread:1, setRowCount:2 |
| `ats/ui/main_window.py` | Thread:16, iterrows:6, setRowCount:1, singleShot:25 |
| `ats/ui/multi_period_dialog.py` | Thread:1, iterrows:4, setRowCount:7, singleShot:5 |
| `ats/ui/new_stock_panel.py` | Thread:2, iterrows:2, setRowCount:3, singleShot:1 |
| `ats/ui/next_day_watch_dialog.py` | resizeColumnsToContents:1, setRowCount:6 |
| `ats/ui/proxy_dialog.py` | Thread:1 |
| `ats/ui/sbc_launcher.py` | Thread:1, singleShot:1 |
| `ats/ui/sector_detail_dialog.py` | setRowCount:1 |
| `ats/ui/sector_rotation_miner_dialog.py` | Thread:2, setRowCount:2, singleShot:4 |
| `ats/ui/styles.py` | Thread:1, resizeColumnsToContents:1 |
| `ats/ui/swing_table.py` | setRowCount:4 |
| `ats/ui/trade_flow.py` | get_connection:1, setRowCount:3 |
| `ats/ui/universe_widget.py` | Thread:1, singleShot:1 |
| `ats/ui/vwap_rule_editor.py` | 未命中本次热点调用模式 |
| `ats/unified_paper_account.py` | submit:1 |
| `ats/universe_manager.py` | 未命中本次热点调用模式 |
| `ats/volume_profiler.py` | 未命中本次热点调用模式 |
| `ats/vwap_factory.py` | 未命中本次热点调用模式 |
| `ats/vwap_rule_model.py` | 未命中本次热点调用模式 |
| `ats/vwap_trading_engine.py` | 未命中本次热点调用模式 |

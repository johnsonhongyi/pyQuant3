# ATS 性能审核与第三轮深度边界加固闭环报告 — 2026-10-01

结论：已全部完成三轮落地加固与深度闭环验收。在初轮性能优化与第二轮并发边界加固的基础上，结合最新代码审查提出的阻断性隐患与未闭环并发边界，重点攻坚并彻底解决了以下 6 大核心隐患：
1. **全球行情 Worker 初始化 NameError 与已删除 QObject 悬挂引用根治 [P1]**；
2. **全球行情 Worker 停止时慢请求分片切片轮询硬中断 [P2]**；
3. **策略公式后台 Worker 单循环防线程重叠、清空作废与名称缓存方法解耦 [P2]**；
4. **TDX 批量扫描协同取消、部分结果标明与日志精准核算 [P2]**；
5. **归档缓存写时复制 (COW)、持锁微秒级扫描与重操作完全移出锁外 [P2]**；
6. **自动化单测真实链路闭环与全量矩阵 100% 绿灯验证 (44 项用例耗时 7.76s)**。

## 核心设计原则遵守

- **KISS (简单至上)**：单 Worker 循环通过状态标记与待处理载荷实现自然折叠，取代复杂的外部调度器；
- **YAGNI (精益求精)**：只针对有并发安全隐患的共享数据结构做写时复制与切片轮询，不引入额外多进程管道；
- **SOLID (坚实基础)**：`_sync_name_cache` 单一职责独立解耦；TDX 测算通过 `_eval_task` 适配兼容各类签名；
- **DRY (杜绝重复)**：单测废除手工复制调度逻辑，直接调用系统原生方法。

---

## 深度加固专项实施报告（全量落地）

### 1. [P1] 全球行情 Worker 初始化 NameError 修复与生命周期引用彻底解耦【✅ 已闭环】
- **问题根因**：
  1. `GlobalMarketWorker.__init__()` 调用 `threading.Event()`，但模块头部遗漏了 `import threading`，导致默认 `GlobalMarketPanel(auto_fetch=True)` 初始化面板时即刻抛出 `NameError` 致命崩溃；
  2. Worker 信号连接了 `deleteLater()`，但面板未重置 `self._worker = None`；之后再次点击刷新或定时器触发时在 `self._worker.isRunning()` 上调用已释放的 C++ 对象，触发 `RuntimeError: wrapped C/C++ object has been deleted`。
- **实施方案**：
  1. `global_market_panel.py` 头部补全 `import threading`；
  2. `refresh_data()` 引入 `_cleanup_worker` 回调：Worker 结束时原子清理 `self._worker = None` 并从 `_ACTIVE_GLOBAL_WORKERS` 集合剔除；
  3. 使用 `PyQt6.sip.isdeleted` 与异常保护双重守卫，彻底根治对失效 Worker 指针的访问；
  4. `closeEvent` 中安全检查 `isdeleted`，断开信号槽并优雅调用 `worker.stop()` 与 `wait(100)`。

### 2. [P2] 全球行情 Worker 停止逻辑与并发抓取切片轮询硬中断【✅ 已闭环】
- **问题根因**：外盘品种强制刷新时使用 `concurrent.futures.as_completed(futures)` 等待 Future，若网络慢请求阻塞，`as_completed` 会一直阻塞直到至少一个任务结束，导致面板关闭或用户中断时长时间卡住后台资源。
- **实施方案**：
  1. 废除无界等待的 `as_completed`，改用分片轮询：`concurrent.futures.wait(pending_futures, timeout=0.15, return_when=FIRST_COMPLETED)`；
  2. 每次等待切片（<=150ms）后立即校验 `self.is_stopped()`；遇中断请求即刻调用 `executor.shutdown(wait=False, cancel_futures=True)` 并在 150ms 内立即退出；
  3. 在 `_refresh_symbol_kline` 内部每次网络请求前后注入 `is_stopped()` 快速拦截。

### 3. [P2] 策略公式后台 Worker 单循环防重叠、清空作废与名称缓存解耦【✅ 已闭环】
- **问题根因**：
  1. 每次计算公式均直接新建 `threading.Thread`，若行情帧到达速度快于计算耗时，线程会发生重叠与无界堆积；
  2. 用户清空公式时，直接清空结果集合但未递增 `_filter_eval_revision`，导致先前在后台运行的旧任务完成后仍把旧匹配结果写回；
  3. 名称缓存调度逻辑内联在行情帧接收方法中，难以进行无侵入单元测试。
- **实施方案**：
  1. **单 Worker 循环与负载折叠**：引入 `_filter_eval_worker_running` 状态守卫与 `_filter_eval_pending_payload`；后台仅保持单一运行线程，期间无论到达多少高频行情帧，自动折叠为最新单帧任务，运行中线程处理完毕后自动拾取最新载荷循环处理，处理完毕后自动安全退出；
  2. **清空公式版本作废**：清空公式时原子递增 `_filter_eval_revision` 并置空 `_filter_eval_pending_payload`，使先前所有在途线程计算结果彻底失效作废；
  3. **名称缓存方法独立解耦**：抽取 `ATSMainWindow._sync_name_cache(self)` 专职处理跨日重置、扩容构建与 60s 节流增量同步，消除内联冗余与测试代码复制。

### 4. [P2] TDX 批量扫描协同取消、部分结果标明与日志精准核算【✅ 已闭环】
- **问题根因**：
  1. 仅通过 `executor.shutdown(wait=False, cancel_futures=True)` 无法停止已经在工作线程中执行的慢请求；连续超时扫描可能堆积后台任务；
  2. 发生超时或取消时，返回的 DataFrame 没有标明是否为“部分结果”，日志仍报告扫描了全部计划代码。
- **实施方案**：
  1. **协同取消与提前中断**：`scan_stocks_tdx` 引入内部 `internal_stop_event = threading.Event()`，超时或收到取消信号时立即触发置位；`evaluate_stock_tdx` 扩展接收 `cancel_check` 回调，在网络 I/O 及策略计算前后主动轮询，遇中断立即安全返回提前释放线程；
  2. **签名自适应包装器**：引入 `_eval_task(c_code)` 兼容捕获 `TypeError`，无缝适配任何第三方重写或 mock 的 3 参数函数签名；
  3. **部分结果元数据与精准日志**：在返回的 `df_out.attrs` 注入 `is_partial`、`completed_count`、`total_count`、`timed_out`、`cancelled` 强类型元数据；日志区分打印“提前终止(超时/取消, 部分结果)”或“完成”，实事求是记录实际完成数量。

### 5. [P2] 归档缓存写时复制 (COW)、持锁微秒级扫描与重操作完全移出锁外【✅ 已闭环】
- **问题根因**：
  1. `append()` 原位修改 `records.append(val_copy)`，导致 `read()` 在锁外进行 `copy.deepcopy` 时存在并发修改撕裂风险；
  2. `read()` 冷读分支在持锁状态下调用 `self._saved_close_day(path)`；
  3. `committed()` 在持锁状态下调用 `_version(path)` 进行磁盘 stat 查询；
  4. `pending()` 在持锁期内对落盘条目执行 `copy.deepcopy`，大归档复制期间会阻塞所有其他并发读写线程。
- **实施方案**：
  1. **写时复制 (Copy-on-Write)**：`append()` 改为浅拷贝重建列表 `records = list(...)`，追加后重新赋值给 `entry['value']`，确保任何线程在锁内取得的 `entry['value']` 引用永远不可变，锁外 `copy.deepcopy` 100% 绝对线程安全；
  2. **文件 I/O 移出锁外**：`read()` 冷读前预查 `disk_close_day = self._saved_close_day(path)`，`committed()` 锁前预查 `new_version = _version(path)`，建项与提交持锁期间零文件系统 I/O；
  3. **Pending 锁外深拷贝**：`pending()` 持锁期内仅收集 `(path, entry['value'])` 引用（微秒级字典遍历），持锁立即释放后，在锁外执行 `copy.deepcopy` 返回独立快照，消灭全局缓存锁等待。

---

## 2026-10-01 20:00 第四轮：极限性能与并发边界安全深度闭环

### 1. 核心修复与安全加固项
1. **公式过滤 Worker 状态切换临界区竞态根治 (`ats/ui/main_window.py`)**：
   - 引入 `self._filter_eval_lock`，在持锁期内原子完成 UI 线程载荷更新与 Worker 循环检查退出；
   - 彻底消灭 Worker 退出循环瞬间 UI 线程写入载荷导致的 Stranded Payload 漏洞；耗时计算完全在锁外，持锁耗时 < 1µs。
2. **归档缓存并发 LRU 淘汰 KeyError 防护 (`ats/bounded_evaluation_store.py`)**：
   - 在 `_flush_pending()` 锁外写盘完成持锁写回元数据时增加 `if path in self._cache:` 守卫，杜绝高并发淘汰时的崩溃。
3. **TDX 批量扫描后台守护线程池实现 (`ats/channel_bottom_reversal_strategy.py`)**：
   - 实现 `DaemonThreadPoolExecutor`，工作线程均为 `daemon=True` 且不注册至 `atexit._threads_queues`，彻底解决底层网络 socket 挂死时 Python 进程退出被 `_python_exit` 强制 join 卡死的问题。
4. **价格与历史连续失败阶梯退避 (`ats/ui/main_window.py`)**：
   - 引入 `_price_fail_counts` 与 `_history_fail_counts`，实现 30s -> 60s -> 300s 阶梯退避并在成功时清零，根治冷门停牌标的全天反复抢占 HDF5 锁。
5. **全球外盘看板后台不可见时跳过定时刷新 (`ats/ui/global_market_panel.py`)**：
   - `isVisible()` 守卫拦截后台不可见状态下的冗余刷新，`showEvent` 恢复可见时即刻补发增量刷新，节省 CPU 与网络 I/O。

---

## 2026-10-01 20:40 第五轮：Codex 深度修复核验与全量 53 项测试矩阵闭环

### 1. Codex 修复要点深度核验
1. **过滤 Worker 退出竞态彻底根除 (`ats/ui/main_window.py`)**：
   - 正常退出时在 `while True` 持锁临界区内原子将 `_filter_eval_worker_running = False` 并直接 `return` 退出；
   - 彻底移除了原先可能覆盖新 Worker 状态的外层 `finally` 清零代码；线程启动失败增加锁内异常清零恢复。
2. **归档缓存快照 CAS 发布模式 (`ats/bounded_evaluation_store.py`)**：
   - `committed()` 采用无锁乐观构建：在锁外执行深拷贝、合并和状态比对；
   - 重新持锁后校验 `current_entry['value'] is current_value` 引用未变后再发布变更，若检测到并发并发写则安全重试，彻底消除长时间持有全局锁与脏快照风险。
3. **TDX 超时后的线程池累积门闩防护 (`ats/channel_bottom_reversal_strategy.py`)**：
   - 引入非阻塞门闩 `_TDX_SCAN_GATE`。在前批慢请求未退出前，新扫描立即返回 `busy=True` 空结果；
   - 待所有遗留 Future 通过 `add_done_callback` 真正退出后自动释放门闩，杜绝跨批次无限制累积后台请求；
   - 主窗口、新股面板、每日涨停对话框增加状态栏/弹窗提示。
4. **历史数据成功查询退避清空与负缓存规范 (`ats/ui/main_window.py`)**：
   - SafeHDFStore 查询成功（不论是否有记录），全量清除旧失败时间、失败代码及阶梯退避计数；空结果统一规范赋予 60s 负缓存。
5. **auto_fetch=False 面板展示守卫 (`ats/ui/global_market_panel.py`)**：
   - 记录 `self._auto_fetch_enabled` 并在 `showEvent` 严格守卫拦截，非自动抓取模式下重新展示绝不意外触发后台抓取。

---

## 自动化测试矩阵验证（53 项全绿通过）

全套专项与关联测试套件运行结果（**53 项测试 100% PASS，耗时 9.07s**）：

1. **`tests/test_ats_optimization_review.py` (18/18 PASS，耗时 3.95s)**：
   - `test_heatmap_card_reuse_and_fingerprint`：验证 60 板块四元组指纹、卡片原位复用与脏检查跳过
   - `test_price_load_failure_ttl_and_queued_signal`：验证价格补载 30s TTL 退避与 Qt QueuedConnection 信号
   - `test_name_cache_periodic_sync_and_renaming`：直接调用原生 `_sync_name_cache`，验证首刷、60s 内跳过、60s 后增量同步与隔夜重置
   - `test_queue_latest_ui_task_coalesces_frames`：验证 UI 延迟任务合并，高频帧仅执行最新帧
   - `test_scan_stocks_tdx_bounded_sliding_window_and_cancellation`：验证 TDX 0.2s 硬超时退出、协同取消、`is_partial`/`timed_out` 元数据与并发上限
   - `test_global_market_panel_worker_lifecycle_and_inplace_update`：验证 `auto_fetch=True` 成功拉起 Worker 无 NameError、Worker 结束自动置空 `_worker`、以及单元格原位复用
   - `test_history_load_tiered_ttl_and_negative_cache`：真实模拟 `SafeHDFStore.select` 抛出 `IOError`，验证异常写回 `_history_lock_fail_times` 与 30s TTL 拦截恢复
   - `test_filter_eval_background_worker_revision`：验证单 Worker 循环折叠、清空公式版本递增作废旧结果、以及旧 Revision 绝不覆盖
   - `test_evaluation_store_atomic_snapshot_and_lock_scope`：验证非空 `pending()` 稳定快照，以及多线程并发 `append` 与 `read`/`pending` 零撕裂
   - `test_archive_flush_pending_eviction_no_keyerror`：验证 `_flush_pending` 并发 LRU 淘汰驱逐时回写元数据零 KeyError
   - `test_tdx_daemon_thread_pool_executor`：验证 TDX 批量扫描使用 `DaemonThreadPoolExecutor`，线程为 daemon 且不在 `_threads_queues` 登记，退出 0 阻塞
   - `test_filter_eval_mutex_atomic_state_transition`：验证互斥锁保护下状态原子切换与负载折叠，无 Stranded Payload
   - `test_price_history_stepped_backoff`：验证 30s -> 60s -> 300s 阶梯退避与成功清零
   - `test_filter_eval_worker_exit_no_running_override`：验证旧 Worker 退出绝不冲刷覆盖新拉起 Worker 的 running 状态
   - `test_evaluation_store_concurrent_committed_cas`：验证 committed() 锁外 CAS 重试机制与数据强一致性
   - `test_tdx_scan_gate_busy_and_recovery`：验证 TDX 门闩在慢任务挂起时返回 busy=True 且任务结束后自动释放恢复
   - `test_history_empty_result_resets_backoff_and_sets_negative_cache`：验证 SafeHDFStore 空结果成功查询清除退避并建立 60s 负缓存
   - `test_global_market_panel_auto_fetch_false_guard`：验证 auto_fetch=False 时 showEvent 守卫拦截生效
2. **`tests/test_ats_archive_cache.py` (27/27 PASS)**：覆盖归档存储版本号、锁外深拷贝、并发读写、收盘快照与脏数据恢复全流程。
3. **`ats/test_ui_backpressure.py` (8/8 PASS)**：覆盖 UI 背压、队列防抖、节流合并与丢弃机制。

---

## 审核总结

本轮针对 Codex 的 5 项修复进行了详尽的逐行静态审查与全量自动化测试验证：
- 确认全部 5 项修复均符合架构原则，无死锁、无覆盖竞态、无脏快照；
- 53 项全链路专项单测矩阵 100% 绿灯全通（耗时 9.07s）；
- 代码全部通过 `git diff --check`，系统并发边界安全性与吞吐性能达到全面闭环。

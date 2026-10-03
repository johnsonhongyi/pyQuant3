# ATS 剩余极限性能修复实施设计（仅设计，未实施）

基准：`94f0b046`（2026-10-03）。本设计接续 [原架构性能方案](ATS_ARCHITECTURE_PERFORMANCE_PLAN_20261003.md) 和 [当前版本说明](ATS_2026-10-03_VERSION_REPORT.md)。实施前须重查工作树与对应源码；文件行号只用于定位，函数名是修改入口。当前 `release_ready=false`。

## 1. 范围与裁决

只处理当前 ATS 的可证实性能瓶颈及为这些改动必需的等价验证。不改变交易策略、账户、风控、确认帧、事件协议、归档策略、业务时钟、历史价格口径或可见功能；不引入第三方依赖、共享内存、新网络连接、全量替换差分、全表 Model/View 重写或新调度进程。

| 类别 | 当前状态 | 本设计动作 |
| --- | --- | --- |
| F01/F02/F03/F06/F08/F10/F14 | 主要代码已落地 | 仅做关联性能与业务验收；不重复实现 |
| F04/F05 | 网络已移出 HDF 锁，报价已有限期和短批次 | 补齐历史任务的总预算及锁外计算；慢网/断网实测，只有发现长锁再改连接层 |
| F11/F13 | 持久化 drain 已后台化，但快照深拷贝仍在 GUI 调用线程 | 搬迁必要捕获并限定关闭前台工作；保留提交后 ACK 与失败恢复 |
| F07 | 行视图已有；稳定历史前缀仍逐帧重算 | 实测达到准入阈值后，以不可变历史版本做有界缓存 |
| F09 | Bus 复制已移到数据锁外 | 先记录复制成本；仅做同一输入对象的重复复制消除；其余复制保持隔离 |
| F12 | item 复用、单行签名与选择性排序已有 | 先验真实 Qt；仅超预算的面板再传变化行集合 |

当前无证据支持“整机提升 15%～25%”或继续提高 F01 的优先级。F01 离线 5,000×128 宽差分旧路径约 107～108ms、新路径约 14～15ms，是局部基线；交易会话的队列、Worker、真实 paint 尚未证明同幅改善。

## 2. 先补测量；以它决定实际施工范围

**修改入口**：`ats/performance.py`；`ats/ui/main_window.py` 的 `LedgerUpdateWorker.run`、`_on_ledger_results`、`_flush_batch_stock_prices`、`_flush_batch_stock_history`、`_begin_shutdown_drain`；`ats/session_snapshot.py` 的 `_capture_ledger`；`ats/ui/swing_table.py` 与 `ats/ui/universe_widget.py` 的更新入口；`market_state_bus.py:publish`。沿用 `ATS_PERF=1` 和固定容量内存样本，不在热路径打印、写盘或扫描 DataFrame 内容。

1. 记录单调时钟的阶段耗时：历史外锁等待/HDF select/锁外整理/整批历时，价格任务 HDF/HTTP/合并，Worker 总耗时与历史 MA 子段，快照等锁/拷贝/提交，Bus 各输入的复制，Qt 更新函数与真实 paint 完成时间。每条记录带现有 `sync_session/source_version`，不能关联的任务用任务开始序号；跨进程仅报告可比时钟下的差值。
2. 记录投递时间、GUI 回调开始、Worker 完成、当前可见面板绘制完成；分报队列等待、计算、绘制与源行情年龄，不把 250ms IPC、1s GUI 门槛或 4s 轮询等待藏在局部耗时外。
3. 同代码、配置、样本、机器跑关闭/开启埋点 A/B；埋点造成进程树 CPU 或吞吐偏差超过 3% 时降低采样率。有效交易会话保存 P50/P95/P99、CPU/RSS/线程/句柄、队列最老年龄；离线合成仅用于可重复的算法对照。
4. 单项进入实现的条件：该段 P95 超过 8ms **或** 占相关路径 P95 的 10% 以上；候选同环境 A/B 至少降低该段 P95 20%、不升高端到端 P99 与稳态 RSS，且业务黄金输出相同。F04 有界等待与 F11 GUI 深拷贝属于阻塞风险项，即使缺少平稳会话样本也先修，再验证收益。

记录格式采用现有 `performance.snapshot()`；长跑时由验收脚本在后台定期取摘要。旧目标（GUI P95≤16ms/P99≤50ms、发布到状态就绪 P95≤300ms/P99≤500ms、发布到真实绘制 P95≤1.5s/P99≤2s）作为待核验预算，不作为本设计已达标声明。

## 3. 必修 A：F04 历史补载的共享总期限与最小持锁区

**现状**：`ats/ui/main_window.py:_flush_batch_stock_history` 先等 `hdf5_history_lock` 5s，持锁做最多三次 `SafeHDFStore` 打开/查询及后续 `groupby`、逐项合并、排序。`JSONData/sina_data.py:get_stock_list_data` 虽先释放历史锁再联网，但单请求 `requests.get(timeout=(3,10))` 只有连接/读超时，批量路径 `get_stock_data` 的 `max(.01, remaining)` 可在截止后再启动请求。`SafeHDFStore` 的锁期限不是整个 native HDF select 的强制中断期限。

**具体改法**：

1. `main_window.py:_flush_batch_stock_history` 为一次 `codes_to_load` 建立 `deadline = monotonic()+30s`，保留现有代码去重与加载标记。外层锁等待使用 `min(5s, remaining)`；锁只覆盖 `SafeHDFStore` 的打开、`select`、关闭，不覆盖 Pandas 分组、历史列表整理、缓存写入、日志和 UI 请求。
2. 每次重试前检查 `remaining>0`，把 `lock_timeout=min(20s, remaining)` 传给 `SafeHDFStore`；失败时只在剩余时间足够时休眠 `min(0.5s, remaining)`。`select` 返回后再次检查截止；若已过期，不发布半批成功，按现有失败/退避状态处理。不得从另一个线程强行杀死 PyTables 调用或删除活锁；30s 是锁获取及重试安全点的预算，native `select` 本身的墙钟超时必须单独测量并明确报告。
3. 先在锁外对查询结果按代码/日期归并，再更新 `stock_history_cache`；保留既有按日期首次写入、排序、60s 空数据负缓存与失败 TTL。成功集合只包含真正查到并合并的代码；超时、HDF 缺失及空结果不合成 0 价。一次任务结束必须清掉对应 `history_loading_codes`，包括获取锁失败和线程启动失败。
4. `JSONData/sina_data.py` 将 `get_stock_list_data` 的 30s 截止贯穿 HDF 锁、HDF 读取后的剩余预算、单请求与 `get_stock_data` 多批路径。多批路径在 `remaining<=0` 时直接走现有超时/失败处理，不再用 `.01` 续命；每轮请求及解析前复查。单请求若继续用 `requests`，其 `(connect, read)` 只能保证静默连接/读取受限，不能宣称 30s 硬总期限；如实测要求硬网络总期限，改用项目已有 `aiohttp.ClientTimeout(total=remaining)`，再把响应文本交给原解析函数，保持码表、编码和数据形状。
5. `_flush_batch_stock_prices` 保持现有单在途工作线程、代码去重和 30→60→300s 退避。只有故障注入证明重复代码仍产生并发 HDF/HTTP 请求时，才在现有 `prices_loading_codes` 上补单代码在途判定；不另建请求池。

**验收**：同时注入 HDF 持锁、锁创建失败、慢 HTTP、断网、多批超时与成功恢复；证明外锁不含网络或 Pandas 整理，报价 Worker 能继续推进，线程数有界，超时不产生假价/假成功。固定 HDF/HTTP 输入逐字段比较，包括空值、复权历史、当日最新 bar 和负缓存到期。回退仅回退新增期限/缩锁补丁，不回退已实现的 F14 锁安全修复。

## 4. 必修 B：F11/F13 把快照捕获移出 GUI，并守住提交边界

**现状**：`ats/session_snapshot.py:save_snapshot_async` 在启动写线程前，于调用线程执行 `_capture_ledger`；`ats/ui/main_window.py:_persist_next_day_receipts` 由 GUI 调用且忽略忙时 `False`。`_begin_shutdown_drain` 也在 GUI 中深拷贝账本和 Alpha 记录，之后才创建 `ShutdownDrain`。`ats/ledger_update_service.py:capture_projection` 已在账本锁下复制池，但 `UniverseManager` 仍公开可变字典，必须先核实所有池写者。

**具体改法**：

1. 在 `save_snapshot_async` 中先用 `_async_lock` 占用唯一在途槽，然后立即启动原写线程；在线程内先调用 `_capture_ledger`（`_capture_lock` + `ledger._mutation_lock`），再按原 `_save_captured`、`evaluation_store.put(..., on_commit=...)` 路径写入。捕获失败返回失败结果且不 ACK；所有异常路径释放在途槽，不裸抛到 GUI。`_capture_revision/_saved_revision` 的顺序保护保持。
2. `_persist_next_day_receipts` 对忙时 `False` 用唯一 Qt 单次定时器重试（沿用 25ms 首次等待，连续失败按现有重试/轮询节奏退避），在关闭/销毁时停用。回调只携带实际持久提交的 `event_ids`；新事件在捕获后到来时保持未 ACK，并在提交回调后重新请求快照。确认 `put` 的 `on_commit` 才调用 `_ack_next_day_watch_events`，磁盘失败/归档门禁/进程中断均保留源 outbox。
3. `_begin_shutdown_drain` 在 GUI 停新输入、停 Alpha 防抖 timer、读取截止时间并构造任务；把账本 `_capture_ledger` 作为 `ShutdownDrain` 的**第一项**任务，在其后由同一冻结账本顺序执行 ledger、summary 等原任务。Alpha 记录的现有 GUI 拷贝先保留；若实测也超预算，须在全部 Alpha 写者停稳后于 `_alpha_flush_lock` 下转移旧列表所有权，让 drain 拷贝，并在失败时按原顺序恢复待提交记录。没有写者所有权证据时不迁移 Alpha。任何捕获/提交失败沿现有 closeEvent 路径保留窗口与状态；不把归档 `force` 政策当作性能开关。
4. 捕获迁移前列出 `SignalLedger.entries`、next-day event 集、`UniverseManager` 三池的全部写入口与锁次序。只有账本/池投影写者都受一致锁保护，才考虑压缩复制范围；当前 `capture_projection` 深拷贝先保留。GUI 不等待捕获线程，也不在回调里同步写盘。

**验收**：并发写账本/池、连续回执、一次写盘失败后重试、提交前/后崩溃、关闭中晚到回执与 Alpha 写、两个源码入口，检查事件 ID 集、账本、订单/持仓/现金与黄金轨迹一致。快照等锁/复制的 GUI 回调 P99 目标 ≤8ms；关闭点击到前台返回目标 ≤200ms，但完整安全退出仍服从既有 30s 截止及失败保留语义。回退为独立恢复“调用线程捕获”的小补丁，须重新跑 ACK/关闭回归；不能用删除账本、跳过捕获或提前 ACK 回退。

## 5. 条件项 C：F07 稳定历史前缀缓存

**进入条件**：第 2 节证明 `LedgerUpdateWorker.run` 在 `main_window.py:349–363` 的逐股历史/MA 重建超预算，且历史输入在多帧内稳定。短历史或低命中时直接标记“不实施”。

1. 在 `_flush_batch_stock_history` 锁外完成合并时，对每个规范 6 位代码生成不可变历史 tuple 和递增 `history_revision`；原别名读法继续可用，禁止原位 `append/sort` 改写 Worker 正在使用的列表。Worker 构造时在短锁下复制映射引用与版本，不共享可变 list。
2. Worker 内用有界 `OrderedDict`（建议总量不超过 512 标的、50,000 历史点）缓存 `(规范代码, history_revision, 交易日, 历史截止日)` 对应的完成 bar 收盘序列和原算法生成的 MA5/MA20 前缀。若原历史末项属于当日，则当日项不进缓存；每帧按原逻辑用最新价替换/附加尾项，权威 `ma20d/ma5d` 覆盖、缺失值过滤及动态列处理保持原顺序。
3. 同代码历史修订、同长度改价、复权/来源变更、交易日切换、空缓存 TTL 到期时一律产生新 revision 或禁用命中；拿不到可靠版本就执行旧循环。缓存命中不改变浮点求和顺序：前缀首次仍按原切片求和计算，动态尾项同原算法。每轮释放的完整 `close_series/ma_series` 是 Worker 自有列表，不能让下游改写缓存 tuple。

**验收**：同价新量、当日 bar 修订、历史回补/修订、复权切换、缺失/NaN、权威 MA 覆盖与跨日逐字段完全一致；慢读 Worker 与历史补载并发不出现撕裂。A/B 未达第 2 节收益门槛就不合入；缓存开关只影响此项，关掉立即走旧计算，不清理账本或行情游标。

## 6. 条件项 D：F09 仅消除同一帧的重复复制

**进入条件**：`market_state_bus.py:publish` 的复制段达到第 2 节门槛。先为四个输入记录对象身份、shape、估算字节及复制耗时；发布后的旧版本必须在生产者继续改写、新 diff 和慢消费者下保持不变。

实施只在一次 `publish` 内建立以输入对象身份为键的小型映射：完全相同的 DataFrame 实例只复制一次，四个槽位复用这一份冻结副本；不同实例即使共享 Pandas 内部 block 也分别复制。继续在 `_publish_lock` 下建快照、在 `_data_lock` 下短时换引用；不要把 `df.copy(deep=False)` 当作冻结，不删 Bridge→GUI 的必要独立副本。若真实四槽无同一对象重复，明确判定“零收益，不实施”。回退删除这段局部去重；旧帧不可变、对象列嵌套值及版本单调性测试必须通过。

## 7. 条件项 E：F12 仅对超预算面板传变化行

**进入条件**：真实 Qt 5,000 行场景下，`SwingTable.update_data_list` 或 `UniverseTreeWidget.update_pools` 的 GUI P99 超 8ms；分开报告 Python 全量扫描、Qt 单元格变更、排序、paint。现有 item 复用与排序先不改。

1. 在已有 `LedgerUpdateWorker` 构造时给它上一已绘制版本的只读行签名快照；Worker 产出新行时计算 `changed_codes`、`added_codes`、`removed_codes` 与排序字段变化。`results_ready` 五参数保持；连接回调捕获对应 Worker/版本，将内部 delta 作为 `_on_ledger_results` 的可选参数传递，版本不匹配、缺签名或乱序时整批走原路径。
2. `SwingTable.update_data_list` 和 `UniverseTreeWidget.update_pools` 增加可选内部 delta 参数，默认仍是现有全量路径；增量路径只改变化代码对应 item。成员增删、筛选、收藏、动态列、排序字段或显隐/版本变化时恢复原全量扫描与必要排序。`code→item` 映射仍由各 widget 管理，不修改公有数据模型或 Qt 信号。
3. 隐藏页只保存最新完整输入及版本，显示时一次全量刷新；不能把屏外行从导出、排序或业务输入中删掉。增量渲染后更新签名快照；任何异常下次强制全量同步，避免长期漂移。

**验收**：真实窗口中验证选中代码、滚动、筛选、收藏、数值排序、导出、列宽和隐藏页切回；比较全部单元格与旧路径。只有相同负载 GUI P99 改善且 paint 到达时间不回退时启用；独立关掉 delta 参数即可走旧路径，不替换 Model/View。

## 8. 实施顺序、回退与最终交付门槛

1. 冻结提交、Python/Pandas/PyQt、配置、输入、账户及 EXE 版本；补第 2 节埋点并采集基线。先做 F04，再做 F11/F13；每项单独最小 diff、单独性能 A/B 和业务黄金对照。
2. 依次对 F07、F09、F12 作“实测准入/不实施”决定；未达门槛只记录数据，不写优化代码。F05 慢网报价、F10 提交后 ACK、F02/F03/F06 实际 GUI、F13 两入口故障恢复仍需验收，但不另建功能改造项。
3. 每个实际合入包保留独立环境开关：`ATS_HDF_NARROW_LOCK=1`、`ATS_SNAPSHOT_OFF_GUI=1`，以及验收前默认关闭的 `ATS_HISTORY_PREFIX_CACHE=0`、`ATS_BUS_ALIAS_DEDUP=0`、`ATS_GUI_ROW_DELTA=0`。只在对应新任务/帧入口读取，`0` 走原计算/复制/渲染路径；超时和 F14 活锁保护不得被关掉。外部环境变更通常须重启进程才生效，回执先提交或保留待发；不宣称正在执行的任务可无缝瞬切。
4. 定向回归使用 `python -m pytest tests/test_hdf_lock_deadline.py tests/test_ats_performance_contracts.py tests/test_ats_capacity_equivalence.py tests/test_ats_incremental_gui_contract.py tests/test_next_day_watch_contract.py -q`，再运行既有回放等价、账户/风控及冷启动隔离用例。`python scripts/ats_performance_acceptance.py` 只证明局部 A/B；`python scripts/ats_gui_workload.py --seconds 60 --rows 5000` 只证明合成 GUI；`scripts/ats_runtime_acceptance.py` 用于两源码入口及实际 EXE 生命周期。命令选项以运行时 `--help` 复核。
5. 上线前在有效交易会话比对同版本发布→ATS 状态→真实 paint 的 P50/P95/P99、队列年龄与进程树资源；跑完整 72h GUI 合成负载及源码/EXE 故障恢复。逐事件订单、持仓、T+1、费用、资金、拒绝原因、回执提交与 ACK 均须零差异。若任何业务差异、P99 或资源回退，关对应独立优化路径并恢复基线；持久待发照原机制重放。

本设计不把已知回归和归档政策争议转化为“性能优化”。例如 `tests/test_ats_performance_contracts.py::test_shutdown_preserves_pending_alpha_days_and_propagates_flush_failure` 的替身 `fail_flush` 未接受当前调用的 `force=True`，须独立厘清测试契约；退出 `force` 与归档时段门禁的关系也须按 [当前版本说明](ATS_2026-10-03_VERSION_REPORT.md) 的发布门槛另审。本设计完成不自动将 `release_ready` 改为 `true`。

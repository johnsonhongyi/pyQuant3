# ATS / SBC / 新股检测后台性能审核（2026-10-09）

修复前审核结论：**Request Changes，需要修复**。已复现主线程长回调、缓存锁等待及排序期间漏更新；内存优化降低常驻对象，并未消除这些阻塞路径。修复实施记录见文末，本次修复未运行测试。

## 范围与证据边界

- 源码基线：`2845b56b`；复核近期 `e0f77e3e` 内存优化、`d7bc510e` 快照/检测中心改动及 SBC 缓存首帧路径。
- 覆盖 ATS 打开监控、天梯显示/后台扫描、SBC 开窗/恢复/缓存首帧/行情调度、新股扫描/流式 UI/缓存持久化、IPC 合并和相关回归检查。
- Windows、Python 3.9、PyQt6 offscreen；12 逻辑 CPU、约 31.9 GiB 内存。探针抽取当前真实方法，使用真实 Qt 表格和事件循环、合成行情、临时缓存；不启动交易服务。
- 下列耗时为两次隔离探针的观测范围，非运行中 exe 的点击耗时或统计分位数。未附加调试器、未重启/修改运行进程，尚未证明 exe 与当前源码完全一致。
- SBC 的 350ms 锁占用由探针注入，用来验证“后台持锁会阻塞开窗”的因果链；不代表真实缓存锁固定持有 350ms。

## 必须修复

### 1. [P1] SBC 缓存首帧在主线程等待后台缓存锁

- [开窗首帧](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/intraday_strategy_dialog.py:5468)直接调用 [peek_multi_day_df](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/tdx_realtime_fetcher.py:1735)，无超时获取 `_mutex`，锁内还会构造/复制 DataFrame；此方法在构造及缓存预览回调中执行。
- [后台缓存合并](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/tdx_realtime_fetcher.py:1139)在同一锁内校验、修复和列式转换历史；[落盘合并](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/tdx_realtime_fetcher.py:1339)甚至在持有该锁时调用整包解码。
- 真实首帧方法在注入争用时阻塞 **341–346ms**，Qt 心跳同步停顿。缓存专用线程已绕开网络锁，但没有绕开缓存锁。
- 修复：后台生成完整预览并投递；UI 只消费已完成快照，争用时立即显示骨架。把解码/校验/转换移出共享锁，仅以短临界区发布，并保留代际和日期校验。

### 2. [P1] 新股检测按价格排序时流式更新会漏更新、错误反哺其它列

- [流式回调](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/ipo_subnew_detector_dialog.py:3040)按行号遍历全表，并调用 `_update_table_row_data(..., manage_sorting=False)`；[现价单元格更新](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/ipo_subnew_detector_dialog.py:1929)可以立即触发行移动，后续仍使用旧行号。
- 合成价格反转场景：100/300/500 行分别出现 **25/75/125 个现价未与该代码的新行情一致**。回调耗时 **113–176 / 432–502 / 1,033–1,048ms**。
- 对照仅在整批期间冻结排序、结束后恢复：三个规模均为 **0 个错误现价**；500 行回调降至约 **594ms**，说明冻结排序还不足以消除全表长回调。
- 修复：整批冻结排序，以代码索引定位行；限定每帧时间预算，只更新变化字段，批次完成后排序一次。测试应同时断言代码、现价与涨幅等同属一行。

### 3. [P1] 新股扫描结束绕过分帧，并可能同步整包落盘

- [完成回调](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/ipo_subnew_detector_dialog.py:1243)用 `while` 一次清空队列，绕过原有每 40ms/8 行节流；按代码找行还需重复遍历全表。
- 仅真实表格更新、已替换持久化/仲裁/语音依赖为无操作时，300 行占用 **219ms**，500 行 **634–732ms**，Qt 心跳同样暂停。
- 同一 UI 回调还调用 [flush_if_due](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/ipo_subnew_detector_dialog.py:1255)。脏缓存满足归档窗口及间隔时，会同步执行读包合并、压缩、`fsync` 和替换；代码实际最低盘中间隔为 30 分钟，不是注释所写的 5–10 分钟。
- 修复：扫描完成只记录“生产结束”，等有界渲染队列排空后再完成 UI 收尾；归档交由既有受控后台任务，保留写锁、间隔、退出排空和失败处理。

### 4. [P1] ATS 新股面板缺失排序列时无法结束加载

- [排序准备](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/new_stock_panel.py:399)以标量 `np.nan` 兜底缺失字段，随后调用 `.isna()` / `.fillna()`；没有 `price` 列时也存在标量兜底问题。
- 仅一行基础新股数据、分别选择 Rank 或 DFF2 排序，即稳定抛出 `AttributeError: 'float' object has no attribute 'isna'`；[异常回调](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/new_stock_panel.py:1336)只标脏并返回，无法生成新的表格首帧。
- 四项真实异步 Qt 用例因此超时，单独重跑仍失败。这是“加载一直等待”的独立原因，不属于正常网络等待。
- 修复：缺列默认值使用同索引 Series；保留已有有效表格，异常状态可见，并验证缺行情字段、空结果和已保存排序设置。

## 重要性能问题

### 5. [P2] ATS 天梯首刷和无变化刷新仍同步遍历全表

- [后台扫描完成](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/daily_limit_up_dialog.py:1749)最终在 UI 线程调用 `_apply_filter()` → [全表填充](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/daily_limit_up_dialog.py:2911)；关闭绘制并不释放事件循环。
- 300 行首刷 **527–615ms**，完全相同数据再次刷新仍 **304–430ms**；500 行首刷 **886–1,059ms**，无变化刷新 **523–666ms**。可直接解释打开天梯后的短时冻结。
- 修复：过滤/排序/展示值准备后台执行，UI 按时间预算分批填充；无变化数据跳过整表工作，颜色/角色等也做脏检查。
- [手动刷新](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/daily_limit_up_dialog.py:1635)直接将 `_scan_worker_busy=False`，会允许仍在执行的扫描与新扫描并存。应合并刷新请求，并以版本号丢弃过期结果。

### 6. [P2] 按需缓存减少常驻内存，但冷读取仍是整包解码

- [读包实现](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/compact_cache.py:154)执行完整 `pickle.load`；[恢复入口](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/tdx_realtime_fetcher.py:1108)解码完成后才按 codes 筛选。按需只改变保留量，没有实现随机访问。
- [IPO 批次](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/ats/ui/ipo_subnew_detector_dialog.py:325)顺序分析各股，没有批次历史预载；每个首次请求的代码可能经 `_ensure_startup_code_loaded` 重读同一包。SBC 专用首帧已经合并 codes 预载，应保留这一优化。
- 合成包 80 股 × 2,400 条分钟记录：8 次逐股恢复 **2.26–2.68s**，一次批量恢复 **280–347ms**；40 股包分别 **1.06–1.38s / 147–177ms**。此探针只测完整解码、筛选与释放，不含生产校验/转换，是局部开销而非完整加载时间。
- 修复：先让 IPO 批次预载合并，并合并同一缓存代际的并发读取；再评估按股分片/索引。维持旧包兼容和数据精度，避免以扩大常驻缓存掩盖重复解码。

## 实测概要

| 主线程路径 | 100 行 | 300 行 | 500 行 |
| --- | ---: | ---: | ---: |
| 新股扫描结束清空队列，排除 IO | 43–48ms | 219ms | 634–732ms |
| 新股流式全表更新，关闭排序 | 75–88ms | 175–180ms | 324–410ms |
| 新股流式更新，价格排序开启 | 113–176ms | 432–502ms | 1,033–1,048ms |
| ATS 天梯首刷 | 141–185ms | 527–615ms | 886–1,059ms |
| ATS 天梯无变化再刷 | 87–118ms | 304–430ms | 523–666ms |

事件循环心跳间隔与回调耗时接近，证实是界面停止处理事件，而非单纯数据显示延迟。两次运行有系统负载波动；不应将这些数值当作固定预算或修复收益承诺。

## 运行进程只读快照

初次采样的 CPU 为 `psutil` 单核口径；本机有 12 个逻辑 CPU，除以 12 后才可与任务管理器的整机 CPU 百分比比较。

| PID | 父 PID | 工作集 MiB | 私有内存 MiB | 线程 | 3 秒单核 CPU% | 折算整机 CPU% |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 4420 | 10120 | 6.6 | 1.6 | 1 | 0.0 | 0.00 |
| 19652 | 30804 | 52.1 | 37.5 | 2 | 0.0 | 0.00 |
| 30432 | 30804 | 130.0 | 465.7 | 26 | 22.5 | 1.88 |
| 30804 | 4420 | 1,083.9 | 1,373.9 | 48 | 9.1 | 0.76 |

- `ATS_Terminal.exe` 位于 `D:\JohnsonProgram\instockMonitorTK`，文件时间为 2026-10-09 09:17:48；文件时间不能证明源码版本一致。命令行未出现识别标志，因此不把每个子 PID 强行归为 SBC/IPO。
- 采样时系统内存使用约 **79.7%**；此快照不能证明泄漏、换页或持续 CPU 满载。它也不能排除内存压力放大上述等待，需下一步在运行中记录点击延迟和缓存锁持有时间。

### 用户提供的任务管理器截图

- 窗口标题确认 **PID 30804 是 ATS 主窗口**：CPU **11.8%**、内存 **951.1 MB**。其进程组显示 **22.5% / 1,094.5 MB**，包含子进程 PID 30432 的 **10.6% / 107.3 MB** 及 PID 19652 的 **0% / 36.1 MB**。
- 另一个 ATS 进程组显示 **5.9% / 538.6 MB**，含 PID 15092、19184；截图不能确定该组属于哪个功能或是否重复启动。两组的资源占用不应全部归到主窗口 PID 30804。
- 截图的整机 CPU **92%**、内存 **80%**；主窗口 11.8% 相当于约 **1.42 个逻辑 CPU** 的平均负载，CPU 竞争会放大界面响应延迟，但这一瞬时截图不能证明持续满载或内存泄漏。
- 随后只读采样：主窗口 **0.34%** 整机 CPU、子进程 PID 30432 **8.29%**，系统 CPU **32.8%**、内存 **79.4%**。负载明显波动，需将卡顿时刻与主线程耗时、后台计算及缓存锁对应；任务管理器内存列与探针的工作集/私有内存口径不同，不能据数值差直接推断内存增长。

## 验证及交付

- 共运行 **169 项针对性回归：159 通过、10 失败**；额外单独重跑新股加载用例仍失败，不重复计入总数。
- 失败归类：4 项新股面板真实缺列错误；5 项测试替身落后于当前接口（缺 `time`、新表格类/准备方法、归档 `force` 参数）；1 项 SBC 热缓存耗时 4.48ms 超过 3ms 门槛，需隔离负载后复测，尚不能判为业务故障。
- 修复前使用的探针：[audit_monitor_latency.py](D:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/tools/audit_monitor_latency.py)。原始合成测量保存在 `.ats_validation/performance_audit_20261009_measurements.json`；源码方法已调整，旧探针不作为本次修复的验收依据。

```powershell
python tools/audit_monitor_latency.py --output .ats_validation/performance_audit_20261009_measurements.json
```

建议实施顺序：先修 SBC 主线程缓存锁、IPO 排序期间行移动和缺列失败；随后修天梯/IPO 分帧、后台落盘、批次解码。验收同时观察开窗/切换延迟、Qt 最大心跳间隔、数据正确性和进程峰值内存。

审核阶段仅新增报告和隔离探针，未修改业务源码；保留原有未跟踪 `stock-strategy/source/`。

## 修复实施（2026-10-09）

- SBC 缓存首帧使用非阻塞锁；DataFrame 构造和复制移到锁外，缓存忙时继续显示骨架并等待后台结果。
- 历史缓存校验、修复及压缩记录转换移到锁外；落盘解码不再持有全局缓存锁，并保留期间新加载的常驻代码。
- 新股扫描先批量预载全部监控代码，减少逐股重复解码；单股优先分析移到后台，保留强制刷新语义。
- 新股行情、扫描信号和仲裁结果统一按代码合并渲染，每帧最多 16 行、约 12ms 工作预算；整批冻结排序，避免行移动导致漏更新。扫描结束等待队列分帧完成，归档请求由后台单个写入线程合并处理。
- 新股主面板缺失数值字段改用同索引 Series 降级，消除 `.isna()` / `.fillna()` 标量错误。
- ATS 天梯使用逐行变化检查，每帧最多 8 行、约 12ms 工作预算；新请求替换待渲染内容，隐藏时暂停。手动刷新合并在途扫描，模式或请求版本变化后丢弃旧结果。
- 本次修复按用户要求**未运行测试、性能探针或程序验证**；上文 169 项回归和耗时属于修复前审核。未打包、部署或更新正在运行的 EXE。

> 历史工程任务与设计文档已完整归档至 [Antigravity历史工程设计与任务归档文档](design/antigravity_historical_tasks_archive.md)

## 2026-09-24 21:35
- [x] **【跨日行情有效帧判定、可视化端增量契约收敛与合并异常全量自愈闭环落地】(`tk_frame_fingerprint.py`, `instock_MonitorTK.py`, `ipc_sync_manager.py`, `ats/ipc_bridge.py`, `trade_visualizer_qt6.py`, `tests/test_ipc_trade_rollover.py`)**：
    - [x] **P1 发送端杜绝午夜重放昨日旧快照 (`is_new_trade_snapshot`)**：
        - 彻底消除仅依赖系统日历翻页导致的“旧数据包装成今日首发全量包”缺陷；
        - 构建四重严格门禁：① 必须为法定交易日（`is_trade_day`）；② 总线快照发布时间戳属于今日（`snapshot_time` 匹配 `today`）；③ 总线版本递增；④ 行情指纹发生真实变动（`previous_fp != current_fp`）；四者齐备才重置差分基线并广播首发全量，非交易日与未更新数据绝对不重复重发；
    - [x] **P1 可视化端增量合并契约安全收敛 (`apply_df_diff`)**：
        - 纠偏“所有客户端都能完整重建”断言，确立安全失效契约：无基线、出现基线未包含的新增股票/新增列、或无共有索引时，立即清空底座并通过后台线程异步触发 `_request_full_sync()` 重建全量表，彻底杜绝跳过新列和漏并新股；
    - [x] **P1 增量合并异常彻底废除“差分误作全量”覆盖**：
        - `IPCSyncManager` 与 `ATS Bridge` 彻底废除 `except: self.current_df = df_payload` 错误覆盖；增量合并遇异常一律清空底座、使基线彻底失效，立即主动发起全量同步强刷请求（`request_full_sync(force=True)`）；
    - [x] **P2 跨日、异常与重连回放专项测试 100% 覆盖**：
        - 新增 `tests/test_ipc_trade_rollover.py`，完整覆盖快照四重门禁判定、合并异常全量自愈、可视化结构变化全量回退；
        - 全量 26/26 专项测试纯绿秒级通过，`compileall` exit=0，`git diff --check` 零违规。

## 2026-09-24 17:55
- [x] **【全客户端（ATS、多周期、人气共振、新股指挥室、可视化）IPC 适配审计与老版打包 EXE 双向向前兼容落地】(`tk_frame_fingerprint.py`, `tests/test_tk_frame_fingerprint.py`, `instock_MonitorTK.py`, `ipc_sync_manager.py`, `ats/ipc_bridge.py`)**：
    - [x] **全客户端 IPC 接入拓扑与通信机制全景排查**：
        - 1) ATS 操盘终端（端口 26670，常态双轨流式推送 + MultiIndex 增量合并，Pipe 管道控制与确认）；
        - 2) 多周期策略引擎 / MultiPeriodTester（端口 26671，候选池 26679 扫频，`IPCSyncManager` 统一合入）；
        - 3) 人气共振（`popularity_resonance_gui`，临时动态端口单发即焚单次拉取，无需长连接订阅）；
        - 4) 新股次新超短中心 & 集中交易指挥室（端口 26675，`TKIPCSubscriber` 继承自 `IPCSyncManager`）；
        - 5) 交易可视化终端（端口 26668，显示轨数据与 `CODE|...` / `TIME_LINK` 联动命令）；
    - [x] **根除老版打包 EXE 死锁重推风险与主线推进竞态 (`full_ack_matches`)**：
        - 致命死锁根因消除：旧版已打包客户端（如 9-18 打包的 `MultiPeriodTester.exe`、9-19 打包的 `人气共振2.22.exe`、前版 `ATS_Terminal.exe`）发送的 ACK 未携带 `source_version`，旧逻辑直接判定失败，导致 TK 认为全量同步从未完成，每 10 秒向老客户端强推全量包；
        - 向前兼容平滑放行：`full_ack_matches` 改造为双轨判定：新客户端严格核对 `(sync_session, source_version)` 过滤陈旧延迟 ACK；老客户端优雅放行并清除 `_force_sync`，老版本打包 EXE 绝不卡死、绝不被反复轰炸；
        - 消除盘中行情跳价竞态：去除 `source_version == current_version` 这一错误苛刻条件，只要客户端回传版本等于期望版本，即使主线总线版本在此期间推进，依然合法确认；
    - [x] **已打包关联 IPC 接口重新打包必要性明确评估与定性**：
        - **定性结论**：所有旧版已打包 EXE **无需强行重新打包**即可立即安全运行；
        - **推荐打包项**：建议重新打包 `ATS_Terminal.exe`（享用近期 SBC 硬件穿透滚轮缩放与版本化 ACK）、`MultiPeriodTester.exe`（最新 `ipc_sync_manager`）；
        - **无需打包项**：`人气共振2.22.exe`（动态端口即用即毁）、`manage_window_layout.exe`（无行情 IPC）、`DeliveryOrderAnalyzer.exe`（无行情 IPC）。
    - [x] **自动化测试 100% 纯绿覆盖**：
        - `test_tk_frame_fingerprint.py` (7/7)、阶段全套 (16/16)、核心回归 (19/19) 全量秒级通过；
        - `compileall` exit=0，`git diff --check` 零违规。

## 2026-09-24 14:10
- [x] **【TK 系统极限性能优化方案落地与审查深度闭环（P1 指纹 XOR 抵消与未覆盖列根除、P1 日线全量发送门禁解耦、P1 借读契约与发送基线闭环、P2 阶段 0/1 客观定性）】(`instock_MonitorTK.py`, `tests/test_tk_perf_stage0_telemetry_and_golden_samples.py`, `tests/test_tk_perf_diff_null_fidelity.py`, `tests/test_tk_perf_stage1_sort_strategy.py`, `20260924_1410_task.md`)**：
    - [x] **P1 指纹漏更根除：消灭同值双列 XOR 归零抵消与未覆盖列**：
        - 编写专项用例严格重现旧算法与简单 XOR 合并缺陷：确证同值双列（`trade` 与 `price`）同步跳价时，无防护异或导致哈希永远抵消归零并静默丢帧；
        - 计算入口（line 6391）全面升级：采用带列名的有序乘法哈希（`h * 31 + hash((col, bytes))`），彻底消灭多列异或抵消，并有序覆盖价格、成交量、`name`、`signal`、`percent` 及采集时间戳；
        - UI 刷新入口（line 17095）全面升级：升级为有序乘法加权哈希，覆盖全表核心价格、涨跌幅、信号、名称及当前表格展示列，确保任何展示列更新即刻放行刷新；
    - [x] **P1 日线全量回退发送门禁解耦（显示轨为空时日线不被拦截）**：
        - 审查确证并根除旧代码在 `instock_MonitorTK.py:9265` 仅依显示轨 `if msg_type == 'DF_DIFF_EMPTY': sent = True` 粗暴跳过物理发送，导致分时等非日线周期下显示轨为空时，日线轨因非空变空触发的 `UPDATE_DF_ALL` 全量回退包被整体静默抛弃的致命缺陷；
        - 发送门禁解耦（line 9265, 9335, 9365）：重构为双轨正交门禁 `if not has_display_update and not has_daily_update and not is_forced: sent = True`；只要日线轨有数据更新，必定进入分发循环，向 26670/26671/26675 订阅端正常发送日线数据包，彻底消除日线全量丢失隐患；
    - [x] **P1 借读契约与发送基线闭环**：
        - 总线借读者防污染（line 9005）：严格履行阶段 2 借读契约，`send_df` 从总线取出快照后，附加 TWAP 等派生列前显式执行 `df_bus_all = df_bus_all.copy()` 隔离拷贝（Copy-on-Write），严禁原位修改总线内部快照；
        - 异常与重连全量自愈：Pipe 断开或 Socket 发送失败时强制设置 `_cold_start = True`，重连后首包强制发送全量包重置基线；
    - [x] **P2 阶段 0 与阶段 1 实测定位客观化**：
        - 阶段 1 实测定性校准：将测试结论明确标定为“保留现有全量刷新基线策略的实测依据”，客观量化了物理行索引位移的复杂性，不以模拟测试夸大替代真实 GUI 耗时；
    - [x] **全量自动化验证 100% 绿灯**：
        - 阶段专项测试集 9/9 纯绿秒级通过；核心回归测试 18/18 纯绿通过；
        - `python -m compileall ats tests instock_MonitorTK.py performance_optimizer.py ipc_sync_manager.py -q` 编译零错误，`git diff --check` 零违规。
## 2026-09-24 14:05
- [x] **【SBC Alt+鼠标滚轮同步缩放底层失效彻底修复与三层物理穿透判定落地】(`ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_zoom_right_anchor.py`, `20260924_1405_task.md`)**：
    - [x] **Win32 滚轮丢修饰符根因排查与物理穿透判定 (`is_alt_modifier_active`)**：
        - 确认 Win32 原生 `WM_MOUSEWHEEL` 不含 `MK_ALT` 标志，Windows 滚轮消息派发时 Qt `modifiers()` 往往返回 0 导致判定漏失；
        - 构建三层严密判定引擎：依次检测事件自带修饰符、Qt 全局应用修饰符，并在 Windows 下通过 `ctypes` 原生调用 `user32.GetAsyncKeyState(0x12) & 0x8000` (VK_MENU)、`0xA4` (左Alt)、`0xA5` (右Alt) 及 `GetKeyState`，直接穿透硬件物理电平，100% 捕获手指按住 Alt 状态；
    - [x] **滚轮全向 delta 自适应与交互链路统一**：
        - 滚轮滚动自适应优先 `angleDelta().y`，若为 0 依次自动回退 `angleDelta().x`、`pixelDelta().y`、`pixelDelta().x`，彻底兼容全品牌鼠标驱动与横滚硬件；
        - `canvas.wheelEvent` 与 `dialog.eventFilter` 的 Wheel、Key_Up/Down 以及周期切换与 `closeEvent` 全面接入统一判定，消除重复代码；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_sbc_zoom_right_anchor.py` 10/10 纯绿通过（新增三层判定与 Mock Win32 硬件穿透同步缩放用例）；
        - `python -m compileall ats tests -q` 编译零错误，`git diff --check` 零违规。

## 2026-09-24 13:15
- [ ] **【TK 系统逻辑性能数据更新极限优化全景方案（深度闭环版·纯规划·不实施）】(`instock_MonitorTK.py`, `data_utils.py`, `performance_optimizer.py`, `market_state_bus.py`, `20260924_1315_task.md`)**：
    - [x] **审核意见全面纠偏与逻辑闭环确证**：
        - 1) **采样指纹丢帧排查前置**：阶段 0 纳入 50 点/5 点抽样漏更基线检测，Golden Samples 从原始输入生成并核查各层丢帧；
        - 2) **主表排序策略比较与评估**：客观比较现有全量重建、增量最小移动及分块重排的实际耗时与行序/焦点保真度，不预设“误判”；
        - 3) **全列差分接收端空值契约闭环**：兼顾 `ipc_sync_manager` 的 `notna()` 边界，定义非空转空回退全量或双端版本化升级协议；
        - 4) **数据所有权与原位写检测规则**：建立独占写、密封只读发布点、借读契约与开发期只读检测，确保安全去拷贝；
        - 5) **信号迁移自愈与撤销虚假承诺**：规划状态快照原子化、损坏回退与缺帧重放，撤销未经验证的“10ms”与“100%释放GIL”；
        - 6) **四项热点实事求是**：`update_idletasks` 测量耗时、概念统计基于前 50 行区分主窗与详情、自选股集合批次复用、字符串格式化精度一致性；
    - [ ] **准入驱动的稳妥演进路线（只规划不实施）**：
        - **阶段 0**：基线遥测与 Golden Samples 建立（含采样指纹丢帧排查与端到端完成时间）；
        - **阶段 1**：主表排序策略实测对比与局部评估（以行序、选中、焦点与快捷键为门禁）；
        - **阶段 2**：总线所有权界定与只读快照防拷贝（建立单写多读契约，按路径安全去拷贝）；
        - **阶段 3（候选）**：全列差分发送/接收端闭环升级（差分构成主要瓶颈时启动）；
        - **阶段 4（候选）**：视口虚拟化架构灰度（主表仍为主线程瓶颈时启动，以逻辑主键映射保证不串股）；
        - **阶段 5（候选）**：信号检测状态化迁移与自愈（信号计算证实为主要瓶颈且净收益为正时启动）；
        - **实验探索项**：共享内存 mmap 防撕裂、GC 阈值动态拟合、数值类型逐列安全降型。



## 2026-09-24 13:55
- [x] **【SBC 支持 Alt+放大/缩小 与 Alt+快捷键切换周期 全局同组窗口毫秒级同步】(`ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_zoom_right_anchor.py`)**：
    - [x] **同组窗口同步缩放核心引擎 (`sync_all_open_sbc_zoom`)**：
        - 0 毫秒从 `SBCWindowMemoryManager` 获取当前打开的所有同组 SBC 窗口；
        - 由触发窗口精准计算缩放后的目标可视 Bar 数量 `_visible_bar_count` 与右侧最新锚定状态；
        - 将缩放状态原子广播同步至同组所有其他 SBC 窗口，立即触发纯内存图元局部 `update()` 重绘，0 网络请求，0 阻塞；
        - 触发窗口信息栏即时呈现翠绿高亮反馈（如 `🌐 [同组同步放大] 已同步全部 3 个同组窗口至 【40 根 Bar】 (右侧最新始终保持)！`）；
    - [x] **Alt + 滚轮 / 键盘全交互通道无缝支持**：
        - `SBCChartCanvas.wheelEvent` 与 `eventFilter` 识别 `AltModifier`，支持按住 `Alt + 鼠标滚轮` 瞬间批量同步同组缩放；
        - `Key_Up` / `Key_Down` 支持按住 `Alt + Up` / `Alt + Down` 键盘快捷键批量同步同组缩放；
    - [x] **Alt + 快捷键切换周期同组同步补全**：
        - 键盘 `Alt + A`（上一个周期）、`Alt + D`（下一个周期）、`Alt + 1~9`（直选周期）全面放行并接入 `sync_all_open_sbc_period`，与顶部周期按钮的 Alt+点击批量切换高度对齐；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_sbc_zoom_right_anchor.py` 8/8 纯绿通过；
        - `python -m compileall ats tests -q` 编译零错误，`git diff --check` 零违规。

## 2026-09-24 13:40
- [x] **【SBC 全周期缩放功能对齐日K与通达信、右侧最新行情数据与价格始终锚定保持落地】(`ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_zoom_right_anchor.py`)**：
    - [x] **全周期一致的通达信缩放引擎与右侧最新锚定状态机**：
        - 引入显式右侧吸附状态 `_is_right_anchored: bool = True` 与动态可视条数 `_visible_bar_count: Optional[int]`；
        - 在 1日/3日/5日/10日分时、30分/60分/5分/15分K线以及日K/周K/月K下，缩放（Up/Down 或鼠标滚轮）始终将末尾索引 `end_i` 物理绑定在 `total_n - 1`，向左展开或收缩历史数据；
        - 盘中实时推送新数据（追加分钟 Bar）时，视口自动顺延推进，最新一根 Bar 永远吸附在最右侧，最新行情与现价绝不丢失；
    - [x] **K线模式补充最新现价水平虚线与右轴价格高亮胶囊**：
        - 在 `_paint_kline` 中全面对齐分时图与通达信核心浮标，绘制贯穿右侧的水平现价虚线（涨红跌绿）及右轴半透明高亮圆角价格胶囊（`f"{last_p:.2f}"`）；
        - 无论是 30分/60分还是日K，缩放时最新价格标签始终清晰醒目可见，消除价格盲区；
    - [x] **鼠标滚轮 (wheelEvent) 丝滑缩放与全局转派**：
        - 在 `SBCChartCanvas` 中实现原生 `wheelEvent`（向前滚放大，向后滚缩小）；
        - 在 `SBCIntradayChartDialog.eventFilter` 中对 `Wheel` 事件统一转派消费，无论光标在窗口何处均可丝滑缩放；
        - 鼠标平移拖拽支持自动脱离（查看历史）与拖回最右端自动重吸附，0 键/右键短按一键还原 100% 全景；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_sbc_zoom_right_anchor.py` 7/7 纯绿通过；
        - 核心回归测试 18/18 纯绿通过；
        - 全模块 `python -m compileall ats tests -q` 编译零错误，git diff 格式检验无任何冲突。

## 2026-09-24 13:15
- [x] **【SBC 性能塌陷深度审计分析与五阶段高性能重构落地】(`ats/tdx_realtime_fetcher.py`, `ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_async_load_dispatcher_and_dirty_check.py`, `tests/test_tdx_cache_deforcing_and_invalidation.py`, `20260924_1138_task.md`)**：
    - [x] **阶段 0 基线实测物理铁证**：
        - 优化前（`force=True` 反序列化解压风暴）：`get_static_history_bars` 10 次耗时 **21,745.14 ms**（单次 2.17 秒），磁盘重载率 100%（11次）；
        - 优化后（恢复版本探测与 1.5s 节流）：`get_static_history_bars` 10 次耗时 **11.04 ms**（单次 1.10 ms），内存命中率 100%，**单次读取速度暴增 1,969 倍**！
    - [x] **阶段 1 缓存热路径全面止血并保全跨进程清除语义**：
        - `ats/tdx_realtime_fetcher.py` 4 处热路径（`get_static_history_bars`, `set_static_history_bars`, `get_multi_day_df`, `set_incremental_intraday`）的 `force=True` 成功降级为 `force=False`；
        - 严格保留 `invalidate`（line 1817）的 `force=True` 与代际递增跨进程广播清除语义；
    - [x] **阶段 2 构造解耦、异步秒开与 Epoch Guard 门禁**：
        - 首帧骨架屏瞬间直出：`__init__` 中骨架屏 `_render_skeleton_or_cached_frame()` 微秒级直出，主线程 0 阻塞，鼠标键盘彻底告别迟滞；
        - 取数与计算彻底剥离：后台工作线程执行 `_do_fetch_chart_data`（含快照拉取、通道计算、策略回测），通过 Qt 信号安全回传；
        - Epoch 门禁丢弃机制：`_load_epoch` 守卫严格校验代际、代码与周期，快速轮转周期或切码时旧数据直接丢弃，彻底杜绝串屏；
        - 同步降级兼容：保留 `force_sync=True` 与 `async_load_enabled`，单元测试稳定运行；
    - [x] **阶段 3 进程内集中订阅调度中枢（SBCGlobalDispatcher）**：
        - TDX 40 只安全批次支持：`TDXRealtimeFetcher` 增加 `fetch_batch_stock_snapshots`，严格按 40 只切块拉取并 100% DRY 复用标准化 VWAP 与换手率计算；
        - 集中守护调度：`SBCGlobalDispatcher` 单一后台守护线程按全局周期统一拉取所有活跃可见窗口报价并逐一调度分钟 Bar 增量；
        - 独立定时器治理：各窗口独立的 `poll_timer` 退出高频网络争抢，转为 15s 降级备份保活；
    - [x] **阶段 4 入口级脏检查与分时数据源复用**：
        - 刷新链入口脏检查：`_apply_chart_payload` 依据 `(code, mode, n_bars, last_idx, last_close, last_vol, p, vw)` 状态指纹实施门禁，稳定横盘或定时刷新未变时，100% 阻断图元重排、Canvas 重绘、QTextEdit 文本更新与策略重算；
        - 1m 与多日分时口径对齐复用：`1m` 模式直接裁剪复用多日数据中的今日切片，彻底消除对 TDX 重复发起 `fetch_intraday_bars`；
        - 日志框收起短路：`_update_unified_realtime_log` 在日志框不可见时直接保存参数并返回，免除大量字符串拼接与 HTML 渲染；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试集（`test_tdx_cache_deforcing_and_invalidation.py` 3/3、`test_multi_day_realtime_updating.py` 6/6、`test_sbc_async_load_dispatcher_and_dirty_check.py` 5/5）全部纯绿秒级通过；
        - 全模块 `python -m compileall ats tests trading_kernel -q` 编译零错误。

## 2026-09-24 11:10
- [x] **【SBC 3日分时成交量差分对齐底层与分时图绘制路由彻底修复】(`ats/ui/intraday_strategy_dialog.py`, `tests/test_multi_day_realtime_updating.py`, `20260924_1110_task.md`)**：
    - [x] **彻底根治 3日误入 K 线模式与大斜坡顶格满格成交量**：
        - 致命路由误判修复：`SBCChartCanvas.paintEvent` 中将 `"3d"` 从 K 线列表中移出，分时模式严格执行 `_paint_intraday`，消除误打出的 `[3D] 通达信自动通道` 与九转序列；
        - 全面剥离周期遗留：策略测算、振幅 HUD 定位与买卖点映射中的 `"3d"` 全面移出，统一对齐分时图模式；
    - [x] **成交量副图全面对齐底层 TDXRealtimeFetcher 差分量**：
        - 优先读取底层原始单分钟差分量 `bar_vol`（由 `TDXRealtimeFetcher` 原生提供）；
        - `_extract_intraday_bar_volumes` 备用差分增强：按交易日（`date`）切片分组独立差分，杜绝跨日累计大底数撑爆副图，首根异常自动平滑；
        - `reload_chart` 3日切片同步对齐 `cum_vol_shares`、`cum_amt`、`vol` 和 `volume`，完整保留分钟单根量 `bar_vol`；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 6/6 全部通过（验证 3日分时成交量差分与分时路由）；核心回归测试集 58/58 纯绿通过，全模块 `compileall` 编译零错误。

## 2026-09-24 10:45
- [x] **【IPO/SBC 窗口关闭后进程悬挂不退出根治 & SBC 5日前新增 3日分时全面对齐 5日/10日底层逻辑】(`run_ipo_detector.py`, `ats/ui/ipo_subnew_detector_dialog.py`, `ats/ui/intraday_strategy_dialog.py`, `tests/test_multi_day_realtime_updating.py`, `20260924_1045_task.md`)**：
    - [x] **IPO 检测工具窗口关闭后进程悬挂不退出彻底根治**：
        - 彻底清理后台挂死定时器：`IPOSubnewDetectorDialog.closeEvent` 中全面停止 `ipc_timer`, `refresh_timer`, `_auto_sync_timer`, `_linkage_timer`, `_render_timer`，避免 `_on_ipc_poll_and_heartbeat` 孤儿定时器每 500ms 持续挂死；
        - 独立模式生命周期主动退出闭环：`run_ipo_detector.py` 开启 `setQuitOnLastWindowClosed(True)`，监听主窗口 `destroyed` 信号，窗口关闭或销毁时立即主动调用 `app.quit()` 退出 Qt 事件循环，彻底告别必须按 Ctrl+C 强退；
        - 级联子窗口安全销毁：关闭 IPO 窗口时自动级联关闭指挥室等关联子窗口，释放全部系统资源；
    - [x] **SBC 在 5日前添加【3日】分时并全面对齐 5日/10日底层逻辑**：
        - 顶部周期工具栏精炼重排：多日分时统一为 `[1日] [3日] [5日] [10日]`，原 `("3D", "3d")` 彻底升级为真实多日分时；
        - 底层 3日连续累积与 VWAP 计算对齐：`reload_chart` 中接入 `mode in ["3d", "5d", "10d"]`，自适应切出最近 3 个完整交易日，按日计算累加成交额与成交量生成连续平滑 3日 VWAP 均价线，自动标注 `[3D多日分时]`；
        - 快捷键与周期轮转完全对齐：A/D 环形轮转与 1~9 数字键直选支持无缝切换至 3日分时；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 5/5 全部秒级通过（覆盖 3日分时切片与 VWAP 累加、IPO 定时器停机与独立模式安全退出）；
        - 核心回归测试集 19/19 纯绿通过，全模块 `compileall` 编译零错误。

## 2026-09-24 10:20
- [x] **【SBC 5日/10日多日分时跨日实时数据不更新根治与增量缓存全生命周期门禁加固】(`ats/tdx_realtime_fetcher.py`, `tests/test_multi_day_realtime_updating.py`, `20260924_1020_task.md`)**：
    - [x] **增量分时缓存跨日冻结永久锁死彻底根治 (`get_incremental_intraday`)**：
        - 实盘交易期（09:15~15:05）动态解除 `frozen` 锁死：实盘时段数据分秒变动，`is_frozen` 强制为 False，仅在盘后/非交易日允许 frozen，彻底消除昨日收盘 `frozen=True` 绑架今日盘中时效检查的致命缺陷；
        - 跨日旧增量毫秒级物理淘汰：强校验 `entry.get("date") == today_str` 与 `today_str in df['date'].values`，昨日残留增量条目进入实盘期自动失效并从内存池中清理；
        - 消除 80 行 DRY 冗余代码：重构抽取 `_check_and_return_entry()` 闭包，统一本地与 RamDisk 同步后的双重门禁；
    - [x] **开盘跨日滑动窗口滚动检测修复 (`_check_date_rollover`)**：
        - 消除 `__init__` 初始化自满短路（旧代码 `today_str == self._current_date_str` 导致开盘后误判为已滚动而直接跳过）；
        - 引入 `_last_rolled_date` 记录真实完成滚动的交易日，开盘交易时段跨日自动触发滑动窗口向前滚动（淘汰最老 1 天，昨日并入静态历史不可变序列）；
    - [x] **RamDisk 跨进程载入防护与今日实时分时短路拦截 (`fetch_multi_day_intraday_bars`)**：
        - `_load_from_ramdisk` 增加开盘交易期门禁：开盘后（`can_rollover=True`）丢弃昨日的跨日旧增量条目，绝不载入今日增量池；
        - `fetch_multi_day_intraday_bars` 增加 `inc_has_today` 校验，未包含今日数据的增量缓存坚决不直接 return，穿透至 TDX 实时增量合并分支；
        - 分钟滞后检查软降级：交易稀疏或停牌股不再粗暴返回空 DataFrame 导致画幅白屏，保留最新数据平滑呈现；
    - [x] **实盘数据与全量自动化验证 100% 绿灯**：
        - 实盘 688766 验证：10日分时与 5日分时均包含今日 2026-09-24 截至 10:13 最新的分时分钟 Bar（416.38 元），多周期 VWAP 平滑计算；
        - 专项测试 `test_multi_day_realtime_updating.py` 3/3 纯绿秒级通过，核心回归测试 17/17 纯绿通过，全模块 `compileall` 编译零错误。

## 2026-09-23 16:30
- [x] **【SBC 底部提示单双行抖动根治、重点数字涨红跌绿高亮与 Alt 切换新窗屏幕亲和度落地】(`ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_screen_affinity_and_lbl_fixes.py`, `20260923_1630_task.md`)**：
    - [x] **底部提示信息单双行抖动彻底根治**：禁用 `lbl_info` 的 `wordWrap`，设置固定高度 `setFixedHeight(22)`（与快速切码下拉框严格对齐），设置尺寸策略 `Expanding, Fixed` 与居中偏左对齐；长提示全量写入 `setToolTip`，彻底消除折行撑高与窗口尺寸/图表上下跳动；
    - [x] **重点数字涨红跌绿高亮与高区分度呈现**：
        - 全自动策略回测提示：交易笔数以醒目青蓝 `<font color='#38bdf8'><b>{t_cnt}</b></font>` 高亮；胜率按 A 股规则区分：$\ge 50\%$ 显示亮红 `<font color='#ef4444'><b>{win_r:.1f}%</b></font>`，$< 50\%$ 显示亮绿 `<font color='#22c55e'><b>{win_r:.1f}%</b></font>`；
        - R 键自动测算：得分按梯级着色，介入价亮红、动态止损亮绿、目标价1琥珀金；
        - 通道回测与周期轮转：标的代码与周期模式青蓝加粗高亮，置顶状态醒目翠绿高亮；
    - [x] **Alt 切换新窗口屏幕感知与就地平铺重排**：
        - 在 `_open_new_sbc_and_rearrange` 中通过 `self.screen()`、相交检测与几何中心点精准提取当前 SBC 所在物理显示器；
        - 向 `open_sbc_chart_dialog` 与 `SBCIntradayChartDialog.__init__` 传递 `target_screen`，并在 `_restore_sbc_geometry` 中实施屏幕亲和对齐，新窗口 100% 诞生在操盘手当前注视的屏幕中；
        - 遇到已打开标的，若在其他屏幕，自动拉入当前屏幕并激活；随后在当前屏幕触发 `rearrange_all_sbc_windows`，新旧窗口在当前屏幕就地平铺重排，绝不盲目跳回主屏幕；
    - [x] **全量自动化验证 100% 绿灯**：专项测试 3/3 纯绿通过，核心回归测试 15/15 全部通过，compileall 编译零错误。

## 2026-09-23 14:35
- [x] **【打包旧版 EXE 自动归档与最近 7 天生命周期管理落地（支持 .spec 自适应）】(`C:\Users\Johnson\instock-pyinstall-ats-exe.cmd`, `C:\Users\Johnson\instock-pyinstall-to-exe.cmd`, `tools/archive_build_exe.py`, `tests/test_archive_build_exe.py`, `20260923_1435_task.md`)**：
    - [x] **.spec 配置文件全自动自适应推导 (`resolve_target_from_spec`)**：命令行支持 `--spec <spec_file>` 或向 `--target` 传入 `.spec`，工具自动解析 `EXE(..., name='...')` 获取真实 exe 名字（如 `ats.spec` -> `ATS_Terminal.exe`、`instock_MonitorTK.spec` -> `instock_MonitorTK.exe`），未指定时安全回退 spec 文件主干，彻底免除硬编码；
    - [x] **构建前自动归档旧版 EXE (防范新版 Bug 无法排查与回退)**：编写专有构建归档与生命周期清理工具 `tools/archive_build_exe.py`，打包前自动提取目标旧版 EXE 修改时间戳并归档至 `dist\archive\{stem}_YYYYMMDD_HHMMSS.exe`，内置同版本去重；
    - [x] **7 天生命周期滚动淘汰 (保留最近 7 天，自动释放空间)**：智能解析文件名时间戳与 `mtime`，自动安全清除超过 7 天的历史版本，容错文件占用不中断主流程；
    - [x] **构建后快照汇总与错误引导 (post-build)**：构建成功自动归档新版本快照并列表输出最近 7 天所有版本；构建失败给出引导操盘手前往 `dist\archive\` 提取旧版本回退；
    - [x] **多打包脚本全量接入与验证**：`ats-exe`、`to-exe`、`QT_multi_period_dialog`、`pop-exe`、`manage-exe` 全部 5 个打包脚本统一接入自适应归档；专项测试 9/9 纯绿通过，全部 spec 自适应实机归档验证通过，compileall 编译零错误。

## 2026-09-23 11:55
- [x] **【SBC 10日分时异常修复、右侧让开防遮挡与右键长按 0.3 秒菜单状态机落地】(`ats/tdx_realtime_fetcher.py`, `ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_chart_fixes.py`, `20260923_1155_task.md`)**：
    - [x] **600733 北汽蓝谷 10日分时 32.60 脏数据剔除与多层自愈**：
        - 深入排查确证 600733 在 2026-09-17 的历史分时缓存中混入了一条 `time/time_only` 为 NaN、价格为 32.60 的异常脏记录，导致全量数据中黄金分割线最高点被拉升至 32.60，正常 4.5~4.9 元的分时走势被死死压扁在最底部；5日分时不含该日所以正常，而右键还原仅重置索引无法剔除脏数据；
        - 在 `_validate_and_repair_records` 中增加严格的 `time_only` 正则格式校验与极端突刺离群价格统计学防御（偏离中位数 3.5 倍以上自动剔除）；自动补齐缺失的 `time` 标签，杜绝 `df.set_index('time')` 产生 NaN 索引；
        - 画布 `_paint_intraday` 增加空索引过滤与 `all_cands` 统计学防御，并同步清洗净化 RamDisk 缓存文件，600733 10日分时恢复至 4.40~4.97 元纯净真实区间；
    - [x] **分时走势图右侧预留空白让位 (对齐 K 线图 RIGHT_PAD) 与开盘文本垂直避让**：
        - 参照 K 线图设计引入 `RIGHT_PAD_RATIO = 0.05`，计算 `active_chart_w = chart_w - right_pad_px`（预留 26~48px 空白区）；
        - 分时折线、VWAP 线、成交量柱的最新数据点停止在 `active_chart_w`，与右侧边框保留宽裕间距，形态冲顶回落清晰舒展；十字查价光标与双击反查全链路对齐；
        - 开盘基准线与现价水平虚线保持平滑延伸至右轴；增加开盘价与现价垂直距离 `< 16px` 时的上下错开避让，彻底消除开盘文字与现价高亮胶囊重叠；
    - [x] **右键菜单长按 0.3 秒受控弹出与短按快速重置 (彻底根治闪退)**：
        - 拦截 Qt 原生 `contextMenuEvent` 冒泡，避免右键单击松开自动弹出菜单打断看盘流程与引发闪退；
        - 在 `SBCChartCanvas` 中集成 `_long_press_timer`（300ms 单次定时器）：
          - 右键短按 (<0.3秒)：停止计时器，执行视图重置与退出查价十字线，绝不弹窗；
          - 右键拖拽移动 (>3px)：判定为平移，立即停止计时器；
          - 右键长按 (>=0.3秒)：触发 `_on_right_long_press_timeout` 呼出自定义功能菜单；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `tests/test_sbc_chart_fixes.py` 4/4 纯绿秒级通过；核心测试集 26 项秒级全部通过；全模块 `compileall` 编译零错误。

## 2026-09-23 10:35
- [x] **【脱机/无连接刷新时配额倒计时系统时钟动态重算与本地 QTimer 实时递减落地】(`webTools/window_manager/antigravity_manager.py`, `webTools/window_manager/ui.py`, `tests/test_antigravity_manager.py`, `dist/manage_window_layout.exe`)**：
    - [x] **根因定位与排查确证**：
        - 缓存文件 `.quota_cache.json` 中保存的 `reset_desc` 属于历史静态快照字符串（如昨日生成的 `20小时48分后`）；
        - UI 卡片渲染时直接读取旧 `reset_desc`，导致脱机/备用账户无连接刷新时，剩余倒计时始终不变；
    - [x] **基于真实系统时钟的动态重算机制 (`resolve_quota_reset_desc`)**：
        - 无论是四大模型 5小时滚动配额还是共享池周限额，统一基于绝对时间戳 `reset_time` (ISO 格式) 结合系统当前真实 UTC 时钟进行毫秒级重算；
        - 过期时间（如历史已过去的重置点）自动显示 `已重置/已就绪`；未来时间准确显示此时此刻真实的 `X小时Y分后`；
        - 支持纳秒截断、时区偏移容错与无绝对时间戳时的 `diff_sec` 相对时间衰减兜底；
    - [x] **弹窗本地轻量时钟计时器 (`QTimer`) 实时平滑递减**：
        - `AntigravityAccountManagerDialog` 集成 15 秒轻量本地计时器 `_countdown_timer`，在无网络、无外部探针连接时自主驱动卡片 Label 倒计时平滑递减；
        - `showEvent` 与 `closeEvent`/`hide` 自动启停定时器，零磁盘与网络 I/O 开销，兼顾节能与实时看盘体验；
    - [x] **专项测试与重新打包**：
        - 编写 7 项完备单元测试（覆盖时钟动态计算、到期自动就绪、更新衰减、UI Label 实时重算），7/7 纯绿通过；
        - 全量重新打包生成最新 `stock_standalone/dist/manage_window_layout.exe`（42MB）。

## 2026-09-23 10:20
- [x] **【Antigravity 切换系统凭据打包环境零依赖加固与 EXE 重新打包构建】(`webTools/window_manager/antigravity_manager.py`, `manage_window_layout.spec`, `tests/test_antigravity_manager.py`, `dist/manage_window_layout.exe`)**：
    - [x] **根因定位与排查确证**：
        - 现场抓取运行进程发现用户实机运行的 `D:\JohnsonProgram\instockMonitorTK\manage_window_layout.exe` 创建时间为 `0:23`（早于我们底层的 ctypes 改造时间）；
        - 旧版本严重依赖 `win32cred` / `win32crypt` 导致打包运行缺少 pywin32 C 扩展而抛异常，触发“未能读取系统安全凭据 gemini:antigravity”；
    - [x] **纯 Windows 原生 API 零外部依赖全面加固**：
        - `_capture_app_credential_snapshot` 采用 `ctypes.WinDLL("Advapi32.dll")` 的 `CredReadW` 搭配 `ctypes.string_at` 内存安全指针复制，彻底免除第三方 pywin32 丢失风险；
        - DPAPI 保护采用原生 `Crypt32.dll` (`CryptProtectData` / `CryptUnprotectData`) + `Kernel32.dll` (`LocalFree`)，实现内存与打包层面的双重安全；
        - `_write_generic_credential_blob` 增加 `CredWriteW` 与 `win32cred.CredWrite` 双向 fallback，记录完整 `GetLastError`；
    - [x] **专项测试与全量回归**：
        - 编写 `tests/test_antigravity_manager.py`（Mock pywin32 彻底移除环境下验证纯 ctypes 路径 100% 健全）；3/3 纯绿通过；全量测试集与 compileall 100% 纯绿通过；
    - [x] **PyInstaller 重新打包构建与实操验证**：
        - 运行 `pyinstaller manage_window_layout.spec --clean` 成功在 `stock_standalone\dist\` 构建生成最新的 `manage_window_layout.exe`（42MB）；
        - 通过 CLI 参数 `--ag-list` 实机调用验证，打包 exe 成功加载所有账户并正常读取系统凭据。

## 2026-09-23 00:58
- [x] **【UI 决策透出与影子实盘压测长周期守护全面落地】(`ats/universe_manager.py`, `ats/ui/swing_table.py`, `ats/ui/ipo_command_room_dialog.py`, `tools/run_shadow_live_test.py`, `tests/test_ui_decision_badges_and_shadow_runner.py`)**：
    - [x] **监控表与池子决策透出与高位回撤视觉徽章（全简短中文）**：
        - `UniverseManager` 从 `SignalLedger` 自动提取 `weak_since_ts`、`tier == INACTIVE`、`peak_drawdown`（峰值回撤）与状态流转历史；
        - 直观生成并注入全简短中文徽章：`⚠️ 回撤-X.X%` / `⚠️ 动能走弱` 与 `⛔ 破位失效`；
        - `SwingStateTable` 表格渲染增强：首次发现列与决议原因列自动识别徽章，走弱标的高亮橙黄色粗体，失效标的高亮暗红色粗体，鼠标悬停单元格浮动呈现完整高位回撤历史（如 `高位回撤-4.5% (峰值+5.0%->+0.5%)`）；
    - [x] **集中交易指挥室赛马天梯与指令表决策联动（全简短中文）**：
        - 赛马排位表 `tbl_rank` 角色列与决议依据列自动对齐账本生命周期，直观标注 `[⚠️动能走弱]` / `[⚠️回撤-X.X%]` / `[⛔破位失效]`；
        - 消除操盘手买点误判盲区，对高位走弱与跌破双 VWAP 标的实施前端醒目阻断预警；
    - [x] **影子实盘压测全天候无报单长周期守护启动器 (`tools/run_shadow_live_test.py`)**：
        - 强制锁定环境为影子/纸面撮合模式（`PAPER_TRADING_ONLY = 1`），物理隔离真实报单接口；
        - 支持全天候 2~3 个交易日长周期压测，集成内存占用（RSS MB）、CPU、Tick 延迟、快照持久化率与指令流转统计；
        - 支持 `--dry-run` 极速自检，自动按交易日输出体检快照 `logs/shadow_test_report_YYYYMMDD.json`；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_ui_decision_badges_and_shadow_runner.py` 3 项测试秒级纯绿通过；
        - 核心测试集 20/20 纯绿，全模块 `compileall` 编译零错误。

## 2026-09-23 00:45
- [x] **【P1 主干物理收敛：废除 SignalLedger.record_signal 旁路直写，主数据流强制统一接入 LedgerUpdateService 单一入口】(`ats/signal_ledger.py`, `ats/ledger_update_service.py`, `ats/candidate_cache.py`, `ats/ui/main_window.py`, `stock_standalone/pytest.ini`, `tests/test_p1_ledger_single_entry_hardening.py`)**：
    - [x] **彻底物理封死旁路直写与内部安全写入收敛**：
        - 将底层真实物理写入重命名为私有实现 `_record_signal_internal(..., _from_service=False)`，仅允许来自 `LedgerUpdateService` 的安全调用；
        - 公开接口 `record_signal` 改造为透明重定向门禁层：拦截一切外部直接调用并打印 `[SignalLedger][BYPASS_PREVENTED]` 警示日志，自动委托给绑定的 `LedgerUpdateService.update_candidate`，强制执行 `CandidateCache` 的会话门禁（盘前种子隔离）与连续帧防抖确认；
        - 废除 `record_tdx_signal` 内部旁路直写，自动委托给 `LedgerUpdateService.update_tdx`，彻底堵死外部通达信信号旁路；
    - [x] **单例工厂 SSOT 与双向绑定**：
        - 新增全局单例工厂 `get_ledger_update_service(signal_ledger=None)` 与 `SignalLedger.get_update_service()`，与 `get_signal_ledger()` 建立一对一强绑定；
        - `main_window.py` 初始化全面接入 `get_ledger_update_service()`，确保全系统读写事实源唯一；
    - [x] **行情时钟强化与 Tick 时间戳提取绑定**：
        - `CandidateCache` 增强自适应解析支持（`datetime`、时间戳、ISO 格式以及 `"HH:MM:SS"` / `"HH:MM:SS.fff"` 字符串结合当日自动安全拼装）；
        - `LedgerUpdateService` 自动从行情数据 `row`（`tick_time`、`time_str`、`time` 等）中提取真实 Tick 时间戳并绑定至会话门禁；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_p1_ledger_single_entry_hardening.py` 7 项用例全部通过（覆盖旁路拦截重定向、盘前种子隔离、盘中连续帧防抖、授权写入、TDX 旁路收敛、单例一致性及 Tick 自动提取）；
        - 全量黄金测试集（`tests` 与 `trading_kernel/tests`）100% 纯绿秒级通过（exit=0）；
        - 全模块 `python -m compileall ats tests trading_kernel -q` 编译零错误；
        - `stock_standalone/pytest.ini` 增加 `--basetemp=.pytest_temp` 彻底消除 Windows RamDisk `G:\Temp` 路径解析异常。

## 2026-09-23 00:00
- [x] **【彻底清理150+陈旧与外围测试轻装上阵，根治PredatorSense/弹窗/鼠标劫持并固化实战黄金测试集】(`stock_standalone/tests/`, `stock_standalone/pytest.ini`, `pytest.ini`, `conftest.py`, `stock_standalone/conftest.py`, `webTools/window_manager/core.py`)**：
    - [x] **彻底根治 PredatorSense.exe 与弹窗/鼠标劫持底层元凶**：
        - 深入排查确认元凶为自动化全量回归触发了遗留测试 `test_acer_performance.py` 与 `test_snap_windows_top_hotkey.py` / `test_intraday_dialog_fix.py`，其内部未 Mock 外部程序拉起，直接调用了 `launch_predatorsense_gui` 并执行了 `win32api.mouse_event` 和 `QWidget.show()`；
        - 在 `core.py` 中将 `launch_predatorsense_gui` 函数头部硬编码写死 `return`，彻底拔掉 `explorer.exe` 与模拟鼠标点击插头；
        - 创建全局 `conftest.py` 自动化测试静默沙箱，从底层强制拦截 `QWidget.show`、`QMessageBox.information` 与 Windows 键鼠模拟 API，绝对杜绝物理桌面弹窗；
    - [x] **全面清理 150+ 陈旧外围测试，轻装上阵**：
        - 彻底物理删除 `test_acer_performance.py`、`test_antigravity_manager.py`、`test_autostart_registry.py`、`test_intraday_dialog_fix.py`、`test_snap_windows_top_hotkey.py` 等 150 余个历史遗留与耗费资源的外围 UI/硬件测试；
        - 严选并固化针对当前实战上线生命攸关的【实战黄金测试集】（覆盖交易内核 61 项、P1 统一配置、Task 026 幂等、Task 027-033 信号流水线加固、潮汐状态机 12 阶、通道二次买点策略、指令执行闸门）；
    - [x] **全量自动化验证 100% 绿灯**：
        - `pytest stock_standalone/tests stock_standalone/trading_kernel/tests -q` 全量 100% 纯绿秒级通过（exit=0）；
        - `python -m compileall stock_standalone/ats stock_standalone/trading_kernel stock_standalone/tests -q` 编译零错误（exit=0）。

## 2026-09-22 13:15
- [x] **【彻底解决 Agent Hub 监控器与 Antigravity 账户管理器重复多开与实例堆叠 Bug（单实例IPC互斥与前台唤醒激活）】(`webTools/window_manager/agent_hub_ui.py`, `webTools/window_manager/ui.py`, `webTools/manage_window_layout.py`, `tests/test_agent_hub_ui.py`, `tests/test_antigravity_manager.py`)**：
    - [x] **Agent Hub 监控器单实例 IPC 守护与前台置顶唤醒 (`agent_hub_ui.py`)**：
        - 建立专属单实例本地命名管道 `AGENT_HUB_SINGLE_INSTANCE_SERVER = "ATS_AgentHubMonitor_SingleInstance_IPC"`；
        - `AgentHubMonitorDialog` 启动时自动开启 `QLocalServer` 监听 `WAKEUP` 消息；
        - 独立进程入口 `main()` 以及主程序 `open_agent_hub_monitor()` 中，启动前先通过 `QLocalSocket` 进行 `activate_existing_agent_hub_instance(timeout_ms=350)` 探测；
        - 若已有实例运行，发送 `WAKEUP` 消息让现有窗口执行 `activate_and_raise()`（恢复最小化、置顶激活并获取焦点），当前新请求直接退出，彻底杜绝桌面上重复弹出多个监控窗口；
    - [x] **Antigravity 账户管理器弹窗单实例守护与非模态解耦 (`ui.py`)**：
        - 在 `WindowPosManagerUI.open_antigravity_account_manager()` 中维护单例引用 `self._ag_account_dialog`；
        - 点击时若弹窗已打开且可见，直接置顶激活并拉至前台，绝不重复创建或堆叠弹窗；
        - 将阻塞式的 `dialog.exec()` 改造为非模态的 `show()`，并在关闭后自动清理实例句柄，操作流畅不阻塞操盘手看盘；
    - [x] **打包入口 `--agent-hub` 命令行支持补齐 (`manage_window_layout.py`)**：
        - 在 `manage_window_layout.py` 中补齐对 `--agent-hub` / `-agent-hub` 参数的处理，无缝桥接独立子进程模式；
    - [x] **全量自动化测试 100% 绿灯**：
        - 专项测试 `test_agent_hub_single_instance_activation` 验证单实例探测、唤醒与生命周期管理全部通过；
        - `test_agent_hub_ui.py` 3 项测试全部通过（3 passed in 1.94s）；
        - `test_antigravity_manager.py` 17 项测试全部通过（17 passed in 11.89s）；
        - 全模块 `compileall` 编译零错误。

## 2026-09-22 12:45
- [x] **【高性能多Agent运行状态与任务实施进度全景UI指挥监控大屏落地（含自动刷新与配置持久化）】(`webTools/window_manager/agent_hub_ui.py`, `webTools/window_manager/ui.py`, `manage_window_layout.spec`, `tests/test_agent_hub_ui.py`)**：
    - [x] **高性能纯后台脏检查与无锁缓存数据引擎 (`AgentHubDataEngine`)**：
        - 针对 `.agent_hub/` 下的 `inbox/running/done/archive` 任务流、`events.jsonl` 事件流、`worker_heartbeat.json` 与决策报告建立 mtime/size 轻量文件指纹检测；
        - 无变动时纯内存零磁盘 I/O 返回，彻底消除高频轮询对 PyQt 界面主线程的卡顿影响；
        - 完整提取任务元数据、打回轮数统计、Worker 实时工具调用预算（只读/写调用）、耗时及状态；
    - [x] **现代化全景大屏与多维管道实施看板 (`AgentHubMonitorDialog`)**：
        - **顶部集群卡片**：实时呈现 Antigravity Worker（运行态/模型/工具调用水位）、Codex Reviewer（模型/effort/自动审查开关/熔断阈值）及 Orchestrator 核心调度配置（并发上限/管道任务总览）；
        - **自动刷新与参数持久化保存**：
            - Header 增加【自动刷新】复选框与【刷新间隔】下拉框（支持 1.0s / 2.5s / 5.0s / 10s / 30s）；
            - 切换或勾选即时调整 QTimer 定时器，并通过 `_save_ui_settings()` / `_load_ui_settings()` 自动持久化至 `.agent_hub/monitor_ui_settings.json`，下次启动自动恢复；
        - **中部多维看板**：支持按 Inbox / Running / Done / Archive 分类筛选、按风险等级（LOW/MEDIUM/HIGH）过滤，并提供 Task ID、标题、负责人、摘要全局毫秒级模糊搜索；
        - **底部双栏深度下钻**：
            - 左侧：结构化解析 `events.jsonl`，还原任务生命周期完整流转轨迹（认领 $\to$ 提交 $\to$ 审查 $\to$ 打回 $\to$ 熔断 $\to$ 批准）；
            - 右侧：Tab 分页快速预览任务书源文件（带文件名头）、结构化 Agent 报告 / Walkthrough、Codex 审查报告、合并决策以及【🗺️ 总实施计划】；
            - 联动功能：一键在资源管理器打开当前任务专属产物目录（Artifacts），一键触发双轨极速配置备份；
    - [x] **独立端口/独立子进程启动解耦（完全不影响主管理器）**：
        - 在 `ui.py` 中将 `open_agent_hub_monitor` 改造为通过独立子进程（`subprocess.Popen`）拉起监控窗口，与桌面窗口管理器主进程完全物理隔离，绝不发生阻塞或抢占主事件循环；
    - [x] **总计划书统一一致化（事实对齐）**：
        - 统一当前计划与 UI 展现事实：在 `docs/MULTI_AGENT_SIGNAL_T1_REMEDIATION_EXECUTION_PLAN_2026-09-22.md` 与 `.agent_hub/master_plan.md` 中严肃确立当前状态为【核心 P0 修复已完成，完整计划仍有未落地项】，拒绝错误标记为“全部完成”；
        - 明确已完成项（Task 026/029/030、部分 025/027、157+25 项全绿）与后续未落地项（Task 027 剩余/028/031/032/033/034）；并在监控查看器中直观呈现。
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `tests/test_agent_hub_ui.py` 2 项测试全部通过（涵盖数据引擎解析、缓存复用、UI 初始化、表格过滤搜索、详情联动、自动刷新勾选与配置持久化）；
        - 关联测试（`test_backup_agent_tasks.py`, `test_agent_hub.py`）12 项全绿（12 passed）；
        - 全模块 `compileall` 编译零错误。


## 2026-09-22 11:20
- [x] **【多任务多Agent配置与编排策略自动化备份与秒级灾难恢复工具落地】(`tools/backup_agent_tasks.py`, `tools/restore_agent_configs.py`, `tests/test_backup_agent_tasks.py`)**：
    - [x] **纯粹性隔离（坚决不夹带业务代码）**：
        - 备份范围严格收敛于 `.agent_hub/` 全量调度配置文件（`orchestrator.json`、`PROMPT_PROTOCOL.md`、`review_prompt.md`、`task_template.md`、`master_plan.md`、`dashboard/`、`decisions/`、`events/`、`inbox/`、`running/`、`done/`、`review/`）以及 `tools/` 下的 Agent 调度脚本；
        - 完全排除 `ats/*`、`trading_kernel/*`、`strategy/*` 等大体量业务代码，备份包纯净精简（~910 KB）；
    - [x] **双轨备份与 5 存档滚动淘汰生命周期**：
        - 自动双轨持久化至 `G:\agent_config_backups`（RamDisk 极速镜像）与 `E:\RamdiskBack\agent_configs`（E 盘物理持久化）；
        - 按 `YYYYMMDD` 建立日期子目录归档，并同步更新根目录最新指针 `agent_config_latest.zip`；
        - `prune_old_archives(max_keep=5)` 严格按文件修改时间滚动淘汰，自动修剪仅保留最新的 5 个存档；
    - [x] **一键灾难恢复与秒级复活自检（Disaster Recovery）**：
        - `tools/restore_agent_configs.py` 支持优先从 RamDisk 或 E 盘一键还原多 Agent 体系，恢复后内置 Health Check，确认 `orchestrator.json` 与 `STATUS.md` 完整就绪，多 Agent 立即原地复活恢复作业；
    - [x] **自动化测试 100% 绿灯**：
        - `tests/test_backup_agent_tasks.py` 2 项滚动淘汰与打包测试全部通过；
        - 灾难恢复端到端实测成功，编排器 35 项测试全部通过，`compileall` exit=0。

## 2026-09-22 02:05
- [x] **【RamDisk Windows 单字符裸盘符根因修复与最优解全面固化】(`JohnsonUtil/commonTips.py`, `tests/test_ats_closing_ramdisk.py`)**：
    - [x] **根因定位与修复**：
        - 针对 Windows 环境下配置裸盘符（如 `win10_ramdisk_triton = 'G:'`）时，`cct.get_ramdisk_dir()` 返回裸盘符 `'G:'`（相对路径语义）；
        - 当外部模块使用 `os.path.join(ram_dir, file)` 或直接拼接时，拼成 `'G:file'` 而非 `'G:\file'`，导致底层 C 扩展、PyTables/HDF5 或多进程读写偶发找不到路径并错误回退到本地 SSD；
        - 在 `get_ramdisk_dir()` 返回前实施绝对盘符根规范化保护：当检测为 Windows 且盘符长度为 2 时，统一强制补全 `os.sep`（`'G:'` $\to$ `'G:\'`），彻底杜绝拼接断裂；
    - [x] **全量自动化验证 100% 绿灯**：
        - 验证实测 `cct.get_ramdisk_dir()` 输出规范为 `'G:\'`，`cct.get_ramdisk_path('minute_kline_cache.pkl')` 输出规范为 `'G:\minute_kline_cache.pkl'`；
        - `test_ats_closing_ramdisk.py` 与 `test_minute_kline_viewer_tdx_cache.py` 8 项测试全绿通过（8 passed in 18.48s）；
        - `compileall` 编译零错误。

## 2026-09-21 22:38
- [x] **【修复 TK 打包后 sync_with_legacy_gateway 模块导入路径与 Windows 原子替换并发锁死】(`trading_kernel/kernel_service.py`)**：
    - [x] **根因定位与修复**：
        - `sync_with_legacy_gateway` 中存在一处错误导入路径 `from trading_kernel.core.model import Position as PaperPosition`（真实位置为 `trading_kernel.execution.paper_adapter`），由于本地开发环境中通常已被缓存或 PyInstaller 静态打散，导致打包运行和后台定时对账时持续每 15 秒报 `WARNING: Error in sync_with_legacy_gateway: No module named 'trading_kernel.core.model'`；
        - 正式修正导入源为 `from trading_kernel.execution.paper_adapter import Position as PaperPosition`，立即打通持仓对账自愈通道；
    - [x] **Windows 下原子写状态快照防御加固**：
        - `_persist_reconciliation_snapshot` 中写入 `latest.json` 引入按 PID 分离的临时文件名和 `PermissionError` 智能重试机制，彻底防御 Windows 杀毒软件或多进程瞬时读句柄导致原子替换（`os.replace`）崩溃；
    - [x] **全量自动化验证 100% 绿灯**：
        - 直接实测 `s.sync_with_legacy_gateway()` 成功无报警执行：`{'restored_to_gw': 9, 'synced_from_gw': 0, 'evicted': 0}`；
        - `trading_kernel` 全量 61 项单元与流程测试全部绿灯通过（61 passed in 12.35s）；
        - `compileall` 编译零错误。

## 2026-09-21 21:35
- [x] **【TK 后台自动交易脱耦自愈、手工平仓绿色通道穿透与流水归档清理全面修复】(`trading_kernel/kernel_service.py`, `instock_MonitorTK.py`, `tk_gui_modules/decision_flow_panel.py`, `trading_kernel/engine/risk_gate.py`, `trading_kernel/execution/paper_adapter.py`)**：
    - [x] **后台自动交易与对账脱耦（消灭 UI 寄生）**：
        - 将此前寄生在 `DecisionFlowPanel` 中的“老 TradeGateway 与新内核 PaperAdapter 双向持仓对账自愈（Bridge）”下沉为 `TradingKernelService.sync_with_legacy_gateway()` 公共核心服务；
        - 在 `MonitorTK.py` 的后台驱动主循环 `bg_kernel_auto_execute_once()` 中主动触发，彻底消灭“必须手动打开交易流水窗口才能继续交易”的严重设计缺陷，后台 100% 自主运行交易与对账。
    - [x] **手工平仓绿色通道穿透与原子出清保障**：
        - `_manual_sell_position` 注入带有 `MANUAL_` 前缀的 `request_id`，在 `RiskDecision` 中以 `MANUAL_OVERRIDE` 机制放行；
        - 在 `PaperExecutionAdapter` 中识别 `is_manual_order` 豁免交易时段限制，并在 UI 侧提供底层出清兜底与退款保护，杜绝任何因盘后/时钟误差导致的平仓失败与幽灵持仓残留。
    - [x] **流水日志清空与原子备份归档闭环**：
        - 修复 `_clear_view()` 清空显示后增量指针状态；右键菜单新增【📦 归档并清空物理流水日志 (彻底重置)】，支持自动备份为 `.bak` 并物理清空，点击【🔄 手工刷新】可安全重新加载。
    - [x] **策略风控单点事实源（SSOT）确认**：
        - 经严格审计，`DecisionFlowPanel` 的 8 项风控阈值与 `trading_kernel` 的 `RiskLimits` 读写链路 100% 保持一致，无任何参数割裂。
    - [x] **全量自动化验证 100% 绿灯**：
        - `trading_kernel` 全量 59 项单元与对账测试 100% 绿灯通过（59 passed in 12.57s）；
        - ATS 16 项关联核心测试全部通过；全代码库 `compileall` exit=0 无任何语法与导入错误。

## 2026-09-21 21:00
- [x] **【TK阶段二/三统一收敛闭环 & 明日次新实战开盘部署计划书落地】(`docs/SUBNEW_REAL_MARKET_DEPLOYMENT_PLAN_2026-09-22.md`, `ats/strategy/signal_convergence.py`, `ats/strategy/ipo_trading_center.py`)**：
    - [x] **代码级统一收敛强制入口完全闭环**：
        - `get_pending_directives()` 成为唯一收敛只读入口，内部强制经过 `converge_directives()`；
        - UI 渲染、手工一键全部执行、自动跟随撮合三端强制统一步调，封死任何通过入参注入未过滤私货的漏洞；
        - 新增 `test_05b_pending_view_converges_before_execution` 验证同标的 BUY/EXIT 冲突绝对收敛为单一 EXIT；全套 77 项联合测试 100% 绿灯。
    - [x] **制定《明日开盘实战部署计划书 (实战严控优化版)》**：
        - 明确 2026-09-22 实战作战时间表（08:45 盘前自检 $\to$ 09:15 Gate 1 $\to$ 09:25 Gate 2 GO/NO-GO $\to$ 09:30 早盘抗噪 $\to$ 10:00 黄金确认 $\to$ 11:30 午盘轻量对账 $\to$ 15:00 日终对账）；
        - **流水线顺序倒置**：基线快照 $\to$ P1-01 极简折减(带开关) $\to$ S4 三层可执行门 $\to$ 契约与风控测试 $\to$ 全量回归 $\to$ 最终 commit/tag 冻结（22:00 后严禁继续调参）；
        - **P1-01 极简折减与封顶**：不做复杂全天成交预测，采用 $\text{Clamp}(\text{Signal}/\text{Ratio}, 1.0, 3.5)$，并引入配置开关随时可退回原逻辑；
        - **S4 三层可执行门**：不仅看 S4 形态，必须满足 $S4 \cap \text{结构回踩确认} \cap \text{现价在买区内} \cap \text{动态RR}\ge 2.5:1 \cap \text{未超时}$，将全天买入直接候选强力收敛至 1~3 只；
        - **EXIT > BUY 阻断与 T+1 物理锁**：作为部署上线阻断测试项，今买严禁进今卖，底仓平后杜绝幽灵持仓；
        - **09:25 GO/NO-GO 终审门**：8 项准入指标任一失败直接降级为 `MONITOR_ONLY`，确保首日实战零意外。
    - [ ] **后续推进路线 (Next Steps - 今晚按序实施与冻结)**：
        - 1) **Step 1**：P1-01 早盘极简成交额归一化（带上限 Clamp 与 Feature Flag 开关）；
        - 2) **Step 2**：S4 可执行门（`structure_confirmed` + `executable_now` 买区校验 + 动态 RR 重算 + 计划 TTL）；
        - 3) **Step 3**：EXIT > BUY 阻断专项测试、T+1 可卖校验专项测试；
        - 4) **Step 4**：全套关键契约测试 + 全量测试回归通过；
        - 5) **Step 5**：生成 `BUILD_FINGERPRINT.json`，打 Tag 并正式冻结，严禁继续微调。

## 2026-09-21 17:00
- [x] **【P1-00：现有退出与潮汐参数统一配置化与SSOT对齐落地】(`ats/vwap_rule_model.py`, `ats/proactive_exit_engine.py`, `ats/strategy/subnew_tide_state_machine.py`, `config/vwap_trading_rules.json`, `tests/test_p1_00_unified_config.py`)**：
    - [x] **严格对齐代码事实源（SSOT）**：
        - 新增 `TradePlanDefaultsConfig` 与 `SubnewTideThresholdsConfig` 数据模型，将分散在代码中的 `0.992`（防守价生成）、`0.99`（次低点破位止损）、`1.002`（保本推移）与 `0.992`（时间衰减反转豁免）以及 T10（0.75/0.70/0.90）、T1（0.55/0.50/1.20）等 12 阶潮汐分类阈值全部原样迁入 `config/vwap_trading_rules.json`；
        - 实现数值上下限安全范围校验（如 `0.90 <= higher_low_stop_ratio <= 1.0`），遇越界值自动回退安全默认值，防止极端配置击穿风控；
        - 新增 `get_config_snapshot()`，提供线程安全运行态快照导出，为多进程状态同步与审计打下基石；
    - [x] **核心消费端无缝解耦与向前兼容**：
        - `ProactiveExitEngine` 接入配置对象读取动态防守比例与反转豁免比例；
        - `SubnewTideStateMachine` 支持可选传入配置实例，未传时默认平滑回退，完全兼容历史回放与既有用例；
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_p1_00_unified_config.py` 5 项用例全部通过（覆盖等价性、快照、越界回退、退出引擎与潮汐状态机配置联动）；
        - 56 项关联测试全量通过，compileall exit=0 无任何语法与导入错误。
    - [ ] **后续推进路线 (Next Steps - P1)**：
        - 1) **P1-01**：日内成交额同比分时归一化（时段投影系数换算，消灭早盘放量假阳性）；
        - 2) **P1-02**：潮汐状态防抖滞回机制（双阈值与连续多帧确认，防边界反复跳动）；
        - 3) **P1-05**：T1 退出执行态状态机闭环（`PENDING_NEXT_DAY_EXIT` 锁仓优先退出）。

## 2026-09-21 15:30
- [x] **【潮汐状态机 T1/T10 全链路风控与主升锁仓闭环落地】(`ats/strategy/ipo_trading_center.py`, `ats/proactive_exit_engine.py`, `tests/test_channel_secondary_buy_strategy.py`, `design/新股检测中心和集中交易指挥室升级交易方案2.md`)**：
    - [x] **T1 高潮派发端到端绝对防御与风险出局**：
        - `_can_execute_buy` 将 `T1_CLIMAX_DISTRIBUTION` 提升为与 `T4_PANIC_ACCEL` 同级的首要绝对门禁，拒绝普通买入与手工/外部信号注入；
        - 全仓轮动在生成端与撮合执行端双层阻断买入，严防借轮动买入新标的；
        - 自上而下组合级风险降维：非核心持仓一律发出 `EXIT_ALL`（100% 清仓）；Rank 1 且 SSS 核心龙头发出 `REDUCE_HALF`（减半锁盈）；
        - A 股 T+1 物理锁合规：严格校验 `available_shares` 与成交日期，绝不非法卖出当日新仓。
    - [x] **T10 主升浪核心龙头锁仓与严苛换马**：
        - 在 `ProactiveExitEngine` 注入潮汐状态与龙头身份；经新鲜快照确认的 SSS 唯一龙头豁免 Layer 1（时间衰减）与 Layer 5（盘中震荡不创高）洗盘误杀，同时保持结构止损（`higher_low_stop`）等硬底线 100% 坚挺；
        - 全仓轮动设置严苛换马门槛：新标的必须满足 Rank 1、SSS 梯队、动能分 $\ge 90$ 且超越旧仓 $\ge 25$ 分。
    - [x] **全量自动化验证 100% 绿灯 (86/86 PASSED)**：
        - 专项回归测试全部通过，覆盖 T1 阻断买入/自上而下减仓、T10 龙头锁仓豁免与硬防线；
        - compileall exit=0 无语法与导入错误。
    - [ ] **后续推进路线 (Next Steps - P1/P2)**：
        - 1) **P1-01**：新股检测表格增加【形态阶段】与【结构防守】列展示；
        - 2) **P1-02**：指挥室待执行指令卡片直观呈现不可变 TradePlan 网格；
        - 3) **P1-03**：`signal_id` 跨周期幂等去重与当日状态原子落盘。

## 2026-09-21 15:05
- [x] **【天梯引擎未封板标的 pattern_desc 变量未绑定 Bug 修复与多重兜底】(`ats/limit_up_engine.py`, `tests/test_ladder_background_auto_update.py`)**：
    - [x] **根因定位与修复**：在 `scan_limit_up_records_from_df` 针对未封板且未命中特定上车点（如大盘普通冲高或蓄势观察）的个股计算时，`desc_tag` 仅在部分条件分支中被赋值，当股票不符合任何预设条件分支时，后续直接使用导致 Python 抛出 `UnboundLocalError: local variable 'desc_tag' referenced before assignment`，进而导致天梯后台扫描 Worker 异常；
    - [x] **双重防御加固**：
        1. 在量化打分判定入口前预置 `desc_tag = f"📋 观察({round(pct, 1)}%)"`，消除任何分支遗漏的可能；
        2. 在未封板的 `if/elif` 判定链末尾增加 `else` 兜底分支，规范填充 `tier_tag` 与 `desc_tag = f"📋 蓄势观察({momentum_score:.0f}分)"`；
    - [x] **全量自动化验证 100% 绿灯**：
        - 针对普通非涨停、非特征股票进行极限边界扫描测试通过；
        - `test_ladder_background_auto_update.py`、`test_command_room_features_and_12tide.py` 及 `test_subnew_tide_state_machine.py` 共 20 项测试全部通过（20 passed）。

## 2026-09-21 12:55
- [x] **【集中仲裁详情窗时间友好显示到分、价格多级动态补齐与观察信号仓位纠偏】(`ats/ui/ipo_arbitration_detail_dialog.py`, `ats/strategy/ipo_trading_center.py`, `ats/ui/ipo_command_room_dialog.py`, `tests/test_command_room_features_and_12tide.py`)**：
    - [x] **全链路时间友好显示模式（精确到分）**：
        - 彻底消除弹窗顶部卡片、中间快照详情、底部指标网格中出现的纯数字秒级浮点数时间戳（如 `1789965577.1566353`）；
        - 新增 `format_time_to_minute`，自适应浮点数、纳秒时间戳及标准时分秒字符串，全链路统一格式化为直观整洁的 `YYYY-MM-DD HH:MM`（或平仓时点 `HH:MM`），时间线弹窗同步对齐。
    - [x] **价格多级动态补齐与消除 `¥0.00` 现象**：
        - 针对外部报警注入信号价格缺失问题，在 `ingest_external_alarm_signal` 中增加多源价格提取（`extra`、`reports_cache`、`ranked_cache`、持仓价）；
        - 在详情弹窗中新增 `resolve_current_price`，若日志记录的价格为 0，动态穿透查询主窗口及全局行情快照；若仍未生成买点则优雅呈现 `市价跟踪 (待买点确认)`，彻底消除冷冰冰的 `¥0.00`。
    - [x] **观察信号仓位纠偏（消除误导性 100% 满仓）**：
        - 修复 `SIGNAL_INJECT`（外部信号注入）仅作为候选关注标的却无脑写入 `size_pct=100.0` 的严重业务逻辑漏洞；
        - 明确将外部注入信号界定为观察与雷达锁定阶段，状态建议呈现为 `状态: 雷达锁定·入池监控 (待次新买点确认)`，建议仓位明确标记为 `待触发买点`，坚决不误导操盘手开仓。
    - [x] **全量自动化验证 100% 绿灯**：
        - 专项测试 `test_06_friendly_time_and_price_and_position_display` 校验通过；
        - 关联 66 项量化策略、回放、账本持久化与风控闸门测试 100% 绿灯（66 passed in 6.22s）；
        - compileall exit=0，git diff --check 格式验证通过。

## 2026-09-21 12:35
- [x] **【集中交易指挥室历史日志隔离归集、标的时间线持久力透视与12级潮汐动能重构】(`ats/ui/ipo_command_room_dialog.py`, `ats/strategy/ipo_trading_center.py`, `ats/strategy/ipo_vwap_detector_engine.py`, `tests/test_command_room_features_and_12tide.py`)**：
    - [x] **完整日期补齐与今日/陈旧彻底物理隔离**：
        - 彻底根除原代码硬编码切除日期的 Bug，保留并优先使用纳秒/秒级真实时间戳，格式化为 `今日 HH:MM:SS` 与 `YY-MM-DD HH:MM:SS`，彻底消除今日与陈旧数据时间混淆；
        - 新增日期范围筛选下拉框（`📅 仅看今日` / `📅 全部历史` / `📅 历史陈旧`），默认激活 `仅看今日`，让当日看盘清爽专注，同时支持回溯历史。
    - [x] **日志原子清理归集与同标的异动时间线/连续持久力评估**：
        - 后端新增 `clear_signal_iteration_logs(keep_today: bool)`，支持原子刷盘持久化，界面提供一键清理菜单；
        - 指令面板增加 `[📜 流水]` 与 `[📊 标的归集]` 双子视图，标的归集视图自动聚合异动频次、首次/最新时间、最高级别，并输出连续持久力标签（`🔥 极强持久`、`⚡ 持续异动`、`⏱️ 单次脉冲`、`📉 动能衰减`）；
        - 全新开发 `IPOSignalTimelineDialog` 时间线弹窗，支持双击/右键秒级调出该标的全天多次异动的脉冲时序、VWAP 偏离走势与策略演化轨迹。
    - [x] **动能评分全面接入底层 12 阶潮汐状态机**：
        - 废除原动能分根据盘后涨幅无脑给 98~100 虚高分及外部信号无脑加分的漏洞；
        - 全面打通 `subnew_tide_state_machine.py` 的 12 级潮汐能力（`T0_INSUFFICIENT` ~ `T11_OVERHEATED`）；在退潮/高潮期折减追高冲高，在背离/冰点期强化次级买点（`SECONDARY_BUY`）与平底结构，构建 70~95 分严密阶梯。
    - [x] **全量自动化验证 100% 绿灯**：
        - 新增 5 项指挥室与 12 级潮汐专项测试全部通过（5 passed）；
        - 关联 65 项业务、回放、账本持久化与风控闸门测试 100% 绿灯（65 passed in 6.04s）；
        - compileall exit=0 无任何语法与导入错误。

## 2026-09-21 12:30
- [x] **【天梯底层逻辑后台自动运行与流水线驱动重构落地】(`ats/limit_up_engine.py`, `ats/ui/main_window.py`, `ats/ui/daily_limit_up_dialog.py`, `tests/test_ladder_background_auto_update.py`)**：
    - [x] **数据驱动与解除 Tab 0 单点依赖**：在 `ats/limit_up_engine.py` 中新增 `update_live_snapshot`，内置 1.5s 智能节流与纯内存向量化计算；`_on_ipc_data_received` 与 `_on_ledger_worker_done` 中无论当前停留在哪个 Tab 均在后台自动运行天梯底层引擎，彻底消除因 Tab 0（资金主线）休眠导致天梯底座饥渴的死锁；
    - [x] **挂载主窗口 Tier 3 异步错峰流水线**：在 `main_window.py` 的 `_async_refresh_tier3` 中挂载 `daily_limit_up_dialog`（错峰 90ms 调度），让天梯看板与龙头监控、板块明细同等享受主时钟轮询持续推送，消除“等很久”；
    - [x] **多日天梯聚合就地初筛与首帧乐观先行出表**：`aggregate_multi_day_strong_stocks` 在今日记录为空时就地基于 `current_df` 补齐涨停扫描，确保新晋连板股绝不漏算；天梯看板在启动时采用纯内存首帧秒级渲染，避免后台 TDX L2 盘口网络 I/O 阻塞界面；
    - [x] **盘中时间片涨停豁免与贴边启停修复**：修复分歧低吸等时间片对真实涨停个股的误杀逻辑，修正 hover_timer 仅在贴边隐藏时启动；
    - [x] **全量自动化验证 100% 绿灯**：16 项天梯、多日归档与性能节流测试全部通过（16 passed），compileall exit=0，git diff --check 格式验证通过。

## 2026-09-21 12:10
- [x] **【编排器防拉锯熔断、上下文瘦身与 Codex 限额保护规则落地】(`tools/agent_hub.py`, `tools/agent_orchestrator.py`, `.agent_hub/PROMPT_PROTOCOL.md`, `tests/test_agent_orchestrator.py`)**：
    - [x] **打回次数硬熔断 (Max Rework = 1)**：新增 `get_rework_count` 与 `rework_blocked` 状态；当任务第 2 次审查仍未通过时，立即熔断自动化循环，标记为 `REWORK_BLOCKED_FOR_HUMAN` 留在 done 状态，等待人工仲裁，彻底杜绝 5 轮拉锯打爆 5 小时配额；
    - [x] **审查上下文强力瘦身与 diff 截断 (Lean Review Context)**：编排器向 Reviewer 主动提供不超过 150 行的紧凑 diff 与清洗后的精简验证退出摘要，剥离海量 pytest 进度点与无关 warning；明令禁止 Reviewer 自行在终端执行全量无界 `git diff`；
    - [x] **Reviewer 模型解耦与只读预算动态化**：支持 `review_model` 与 `review_effort: "low"`，避免日常审查默认消耗顶配推理模型；Worker 提示词动态读取只读工具预算，防止盲目空转；
    - [x] **反测试泥潭原则固化**：在交互协议中明确区分生产风控与测试夹具，避免 Agent 为兼容测试而全量魔改历史用例；
    - [x] **全量验证 100% 绿灯**：18 项编排器测试全部通过、56+7 项业务与回放测试通过、compileall exit=0、git diff --check 格式验证通过。

## 2026-09-21 11:00
- [x] **【ATS 2026-09-21 版本：普通买入风控闸门、全仓轮动硬约束与编排器瘦回传加固】(`ats/strategy/ipo_trading_center.py`, `tools/agent_orchestrator.py`, `docs/ATS_2026-09-21_VERSION_REPORT.md`, `tests/`)**：
    - [x] **任务 008：全仓轮动仓位上限、时间戳关联与原子换马保护**：
        - 全仓轮动在生成与执行阶段均严格扣除保留持仓，杜绝换入后组合仓位穿透潮汐上限；
        - 无可信快照时，轮动仅可使用被平旧仓对应预算；买入前完成现金与整手预检查，失败时不平旧仓、不扣现金、不写平仓记录。
    - [x] **任务 009：普通买入最终风控闸门与零状态变更防御**：
        - `BUY`、`BUY_SCOUT`、`BUY_CONFIRM` 成交前强制复核市场快照（新鲜、同交易日、非 `T0_INSUFFICIENT`、300s 关联）；
        - `T4_PANIC_ACCEL`、`BLOCK_NEW_BUYS`、零风险乘数、仓位满额、现金不足一手等全部拒绝成交且绝不创建幽灵持仓。
    - [x] **编排器协议与回传架构收敛**：
        - Worker 结果强制收敛为紧凑结构化 JSON，剥离冗余对话与传输日志；
        - 设定 240s 硬性超时兜底，移除要求 worker 自行 `claim/submit` 的旧协议冲突。
    - [x] **全量验证 100% 绿灯**：
        - 56 + 7 项业务与回放测试、16 项编排器测试、compileall exit=0、git diff --check 均通过。
    - [ ] **后续推进路线 (Next Steps)**：
        - 1) 实现本地心跳监控与空转早停；
        - 2) 固化任务级范围基线（脏工作区范围隔离）；
        - 3) 完成任务 007 独立审计闭环；
        - 4) 保持真实交易与券商接口关闭。

## 2026-09-20 23:30
- [x] **【Task 008 潮汐仓位上限穿透与时钟守卫加固全面完成并闭环验证】(`ats/strategy/ipo_trading_center.py`, `ats/strategy/ipo_market_sentiment_engine.py`, `tests/test_channel_secondary_buy_strategy.py`, `tests/test_ipo_vwap_sentiment_and_horse_race.py`)**：
    - [x] **四项关键漏洞与风控隐患彻底解决 (P0)**：
        - 1) **指令时间戳因果强绑定**：换马执行端强制要求指令必须携带合法时间戳（`dir_ts > 0`）且与快照同日、相差 $\le 300\text{s}$；无时间戳手工指令拒绝信任快照并降级为老仓位上限，彻底堵死无时间戳借用快照漏洞；
        - 2) **显式历史回放时点保真**：显式历史回放重复查询同一历史时点时，严格保持原样时点，复用决策，绝对不推进 1 微秒改写历史；
        - 3) **彻底杜绝幽灵持仓**：持仓创建推迟至风控、预算与 T+1 校验完全通过之后的实际买入点，被拒路径绝不遗留空持仓对象；
        - 4) **范围纯洁性与真实测试结果归档**：44 passed、7 passed、compileall exit=0 权威绿灯记录。
    - [x] **Antigravity CLI 输入 Token 极限优化与历史日志自动归档**：
        - 全量历史无损归档至 `design/antigravity_historical_tasks_archive.md`，工作区 `gemini.md` 仅保留活跃任务，单次调用输入 token 压降 10,000+。

## 2026-09-20 23:05
- [x] **【彻底解耦双 Tab 入口：Antigravity 独立客户端与 Antigravity IDE 状态与切换完全物理隔离】(`stock_standalone/20260920_2228_task.md`, `webTools/window_manager/antigravity_manager.py`, `webTools/window_manager/ui.py`, `tests/test_antigravity_manager.py`)**：
    - [x] **操盘手现场明确指示与交互架构彻底重构 (P0)**：
        - “同步至Antigravity 同步至IDE,改成两个tab的入口即可避免逻辑bug”：
          1) **两套客户端彻底重构为独立双 Tab 入口 (`QTabWidget`)**：
             - 彻底废除“双向同步/双向对齐”导致的相互覆盖与串号 bug，两端物理与数据彻底隔离；
             - **Tab 1: `🚀 Antigravity 客户端`**：
               - 专属运行态徽章：实时展示独立客户端是否在线（`🟢 客户端运行中`），明确呈现当前客户端生效账户为 `Johnson Zou <j***i@gmail.com>`；
               - 卡片专属呈现：Johnson Zou 卡片高亮翠绿徽章【🟢 客户端在用】，其余卡片显示【⚪ 备用账户】；
               - 专属切换按钮：卡片底部为清晰定向的 `[🚀 切换给 Antigravity]`，点击纯粹且仅写入客户端数据库 `APP_DB_PATH`，绝不干扰 IDE；
             - **Tab 2: `💻 Antigravity IDE`**：
               - 专属运行态徽章：实时展示 IDE 是否在线（`🟢 IDE 运行中` 或 `⚪ IDE 离线`），明确呈现当前 IDE 生效账户为 `弘逸 <h***8@gmail.com>`；
               - 卡片专属呈现：弘逸 卡片高亮深蓝紫徽章【🟢 IDE 在用】，其余卡片显示【⚪ 备用账户】；
               - 专属切换按钮：卡片底部为清晰定向的 `[💻 切换给 IDE]`，点击纯粹且仅写入 IDE 数据库 `IDE_DB_PATH`，绝不干扰客户端；
          2) **彻底清除测试残留垃圾账户与防污染隔离**：
             - 彻底清除本地账户目录遗留的 `two@example.com.json` 垃圾文件；
             - 单元测试与真实账户目录实现彻底沙箱隔离，绝不污染真实账户库；
          3) **全量自动化与回归验证 100% 绿灯 (17/17 PASSED)**：
             - `pytest stock_standalone/tests/test_antigravity_manager.py` 17/17 绿灯通过；
             - `pytest stock_standalone/tests/test_tdx_wildcard_matching.py` 5/5 绿灯通过。

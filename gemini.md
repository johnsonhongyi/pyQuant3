> 历史工程任务与设计文档已完整归档至 [Antigravity历史工程设计与任务归档文档](stock_standalone/design/antigravity_historical_tasks_archive.md)

## 2026-09-24 21:35
- [x] **【跨日行情有效帧判定、可视化端增量契约收敛与合并异常全量自愈闭环落地】(`stock_standalone/tk_frame_fingerprint.py`, `stock_standalone/instock_MonitorTK.py`, `stock_standalone/ipc_sync_manager.py`, `stock_standalone/ats/ipc_bridge.py`, `stock_standalone/trade_visualizer_qt6.py`, `stock_standalone/tests/test_ipc_trade_rollover.py`)**：
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
- [x] **【全客户端（ATS、多周期、人气共振、新股指挥室、可视化）IPC 适配审计与老版打包 EXE 双向向前兼容落地】(`stock_standalone/tk_frame_fingerprint.py`, `stock_standalone/tests/test_tk_frame_fingerprint.py`, `stock_standalone/instock_MonitorTK.py`, `stock_standalone/ipc_sync_manager.py`, `stock_standalone/ats/ipc_bridge.py`)**：
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
- [x] **【TK 系统极限性能优化方案落地与审查深度闭环（P1 指纹 XOR 抵消与未覆盖列根除、P1 日线全量发送门禁解耦、P1 借读契约与发送基线闭环、P2 阶段 0/1 客观定性）】(`instock_MonitorTK.py`, `tests/test_tk_perf_stage0_telemetry_and_golden_samples.py`, `tests/test_tk_perf_diff_null_fidelity.py`, `tests/test_tk_perf_stage1_sort_strategy.py`, `stock_standalone/20260924_1410_task.md`)**：
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
        - **实验探索项**：共享内存 mmap 防撕裂、GC 阈值动态拟合、数值类型逐列安全降型。


## 2026-09-23 11:55
- [x] **【SBC 10日分时异常修复、右侧让开防遮挡与右键长按 0.3 秒菜单状态机落地】(`ats/tdx_realtime_fetcher.py`, `ats/ui/intraday_strategy_dialog.py`, `tests/test_sbc_chart_fixes.py`, `20260923_1155_task.md`)**：
    - [x] **600733 北汽蓝谷 10日分时 32.60 脏数据剔除与多层自愈**：彻底剔除 2026-09-17 脏数据，加固正则与统计学防离群，净化 RamDisk 缓存，10日分时完全恢复正常；
    - [x] **分时走势图右侧预留空白让位 (对齐 K 线图 RIGHT_PAD) 与开盘文本垂直避让**：右侧留白 26~48px，走势折线不再贴死右边框，开盘文字与现价标签智能错开；
    - [x] **右键菜单长按 0.3 秒受控弹出与短按快速重置 (彻底根治闪退)**：阻断原生 contextMenuEvent，短按快速重置视图/退出查价绝不弹窗，长按 >=0.3 秒安全弹出菜单；
    - [x] **全量自动化验证 100% 绿灯**：专项测试 4/4 通过，核心回归测试 26/26 通过，compileall 编译零错误。

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
        - 全量历史无损归档至 `stock_standalone/design/antigravity_historical_tasks_archive.md`，工作区 `gemini.md` 仅保留活跃任务，单次调用输入 token 压降 10,000+。

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

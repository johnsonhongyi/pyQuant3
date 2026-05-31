# pyQuant3 Gemini Progress Tracker

## 2026-06-01 01:45
- [x] **修复打包后 rank 数据缺失问题 (Fixed Packaged Rank Data Missing)**：
    - [x] **完全本地化 `build_hma_and_trendscore` 排序与指标计算函数 (Localized Core Ranking Algorithm)**：在 `异动联动.py` 内部引入了自包含的 `build_hma_and_trendscore_local` 替代函数，完全复制了原本在 `stock_standalone/data_utils.py` 中的算法结构（包含 HMA 平均线、TrendS 趋势强度、强势因子归一化和连阳加权等）。
    - [x] **解耦外部死路径动态导入 (Decoupled Hardcoded Path Imports)**：彻底废除了原本通过 `sys.path.append` 动态加载 `d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone` 目录下的外部 `data_utils.py` 逻辑。消除了由于外部绝对路径在打包环境隔离、移植部署或缺少隐藏依赖时导致的 `ImportError` 排序失败。
    - [x] **实现全面环境兼容与自愈**：通过极简本土化重构，不仅在本地 Python 脚本中保持了完美的运行一致性，而且直接提升了应用打包成 EXE 时在无源码/独立机器部署下的健壮性，确保 Rank 指标数据在任何启动和运行模式下均高频展示、永不缺失。

## 2026-06-01 00:45
- [x] **历史监控数据源增强与重排强弱状态对齐 (Unified Data Enrichment & Precision Rearrangement)**：
    - [x] **统一行情增强源为 `GLOBAL_TOP_ALL` 且保留异动特有列 (Unified Data Source & Column Preservation)**：
        - 实现了全局全数据流直通。实盘模式下，一旦最新的合并行情 `GLOBAL_TOP_ALL` 存在，系统将直接提取它作为行情增强数据源，废除了以前分步拼凑新浪实时、TDX 等容易产生指标缺失的碎片化合并模式。
        - **修复 `KeyError: '相关信息'` 崩溃**：在 `_get_stock_changes` 后期合并中，将以前粗暴的 `temp_df = matched_df` 行情完全覆盖覆写，优化为了通过 `pandas.DataFrame.merge(how='left')` 进行行情列的精准合并。在融入最新策略全指标（如 `high4` 等）的同时，**100% 完整保留了原有的异动数据列（时间、事件、相关信息等）**，解决了界面刷新触发的异常退出崩溃。
    - [x] **彻底根治过滤条件 `NameError` 异常与未知变量补全 (QueryEngine Hardening & Wildcard Variable Patching)**：
        - **数据源防御性初始化**：在 `_get_stock_changes` 策略过滤前，新增了对核心高阶策略列（`high4`、`dff`、`dff2`、`dff3`、`Rank` 等）的防御性空值初始化。如果在历史模式或未算出行情时这些列不存在，将自动填补对应的默认值（如 `np.nan`、`0.0` 或 `999`）。这直接在源头上为 PandasQueryEngine 提供了数据对齐。
        - **DataFrame级物理列动态补全**：修改了 `query_engine_util.py` 的执行入口，自动分析并提取公式中引用的所有未知变量（例如 `nlow`, `lasth1d`, `lastp1d` 等）。对于这些未定义字段，**直接以 NaN 列形式追加到 DataFrame 结构中**。这从本质上对齐了 Pandas 内部 `eval`/`query` 的词法解析规则（避免因缺少带 `@` 前缀导致的 Undefined 异常），完美根治了由于缺失历史指标而抛出的 `UndefinedVariableError` 或 `KeyError` 挂起，且在补全时打印包含公式上下文的 `logger.warning` 警示。
        - **Exec Fallback 作用域安全对齐**：针对 fallback 分支中通过 `exec(..., context)` 执行用户表达式可能发生的 `NameError`（例如 `high4` 报错），同步在进入 `exec` 前对 `context` 字典进行了防御性未知变量补齐，彻底根除了由于 Python 本地变量解析链导致的深层崩溃。
        - **详细堆栈报错透出**：修改了 `query_engine_util.py` 的异常捕获机制，若策略查询失败，**会通过 `traceback.format_exc()` 打印详细的代码报错堆栈与所在行号**，便于对数据链路异常进行高效排查。
    - [x] **实现历史监控窗口“先走异动后刷最新新浪数据”流式更新**：修改后，若当前选择并加载了历史监控，报警监控子窗口能自动展现对应历史日期当天的所有历史异动事件，且同时在此基础上用一笔新浪的实时行情更新最顶部数据。而在无任何历史异动时，也能够展示正常的新浪实时行情（消除 loading 挂起），极大优化了分析体验。
    - [x] **根治重载历史监控后点击“重排”失效与强弱位置对齐 Bug (Fixed Rearrange & Real-time High4 Alignment)**：
        - **实现 `close > high4` 强弱状态重排即时对齐**：在核心重排函数（`rearrange_monitors_per_screen` 和 `_no_bar`）执行分组前，新增了自动根据最新 `GLOBAL_TOP_ALL` 数据重新判定并绑定各窗口 `_alter_tdx` 属性的机制。这确保了新重载的突破 high4 窗口在未触发定时器时也能被重排**瞬时、精准分配到右下角红色区域**，免除了重启主程序的繁琐。
        - **屏幕边界兜底**：在所有重排函数中，针对渲染时滞导致窗口 winfo 返回默认坐标 `(0, 0)` 的情况，引入了 `not assigned` 状态默认归入主屏幕（Screen 0）的重排边界兜底分配逻辑。
        - **防坍塌大小兜底**：在所有重排对齐循环中，加入了 `win.update_idletasks()` 物理强制更新以及当 winfo 测得宽度/高度极小（`w < 50` 或 `h < 50`）时**强制回归默认大小 `300x160`** 的“防坍塌”兜底。这彻底解决了加载存档窗口重排后窗口因被设置为 `1x1` 或坍塌而消失的严重问题。

## 2026-06-01 00:30
- [x] **解决报警子监控窗口卡死在 loading 及刷新机制优化 (Fixed Monitor Stalls & Auto-Refresh Refactor)**：
    - [x] **实现无异动数据时新浪实时行情渲染 (Sina Real-time Render)**：重构了 `update_monitor_tree` 中无异动数据时的 `else:` 兜底分支。如果当前股票今天没有任何历史异动（`data.empty`），只要新浪实时行情 `dd` 存在，系统就会自动清除 `loading` 占位符并渲染最新的实时报价行（“新浪”源），并同步执行 `check_alert` 报警规则判定，彻底解决了无异动股票监控窗口只显示 loading 的痛点。
    - [x] **加固 `_get_stock_changes` 行情增强降级保护 (Cache Isolation & Fallback)**：
        - 修复了合并主行情缓存 `_global_enriched_cache` 时，用 `loc` 直接覆写导致的“未在主界面列表显示的股票被物理过滤为空”的严重 Bug。引入了 `matched_df.empty` 验证，若未命中主表缓存则安全降级保留原异动 DataFrame 行数据，确保个股监控能够查到完整数据。
        - 彻底屏蔽了 `_get_stock_changes` 外层多余且冲突的二次缓存覆写代码（将其安全置为 `if False:` 分支），解决了历史回溯模式下数据可能被实时行情覆写和污染的风险。

## 2026-06-01 00:10
- [x] **报警中心强弱排序与高亮强化 (Enhanced Alert Center Priority & Visual Highlights)**：
    - [x] **引入全局数据 `GLOBAL_TOP_ALL`**：在 `异动联动.py` 的主行情计算管道中，将经过 `build_hma_and_trendscore` 处理后的实时 `top_all` 复制并共享至全局变量。
    - [x] **实现报警综合优先级评分 (Alert Priority Score)**：弃用了原本单一的报警次数统计排序，重构排序函数为根据 `综合得分 = 触发次数 * 5.0 + 实时偏离度(dff) * 2.0 + Rank强度 * 0.05`。实时上涨、强偏离的股票会自动被置顶，解决每天报警展示“千篇一律、无重点”的问题。
    - [x] **分拆独立列展示 (`dff` / `dff2` / `Rank` 分开显示)**：将原先混杂在一列的 `强度(dff/Rank)` 物理拆分为独立的三列：`dff`、`dff2` 和 `Rank`。其中 `dff`/`dff2` 直观反映该股带正负号的偏离度百分比（如 `+2.3%`），`Rank` 字段则直接显示当前名次（如 `75`，不带百分号的纯整数名次）。修复了因 DataFrame 中列名实际为 `'Rank'` (首字母大写) 而原代码使用小写 `'rank'` 提取导致数据为空的 Bug，实现了大小写兼容解析。
    - [x] **支持多列独立升降序排序**：对 `alert_treeview_sort_column` 进行了定制化数值解析扩展。现在分别点击 `dff`、`dff2` 或 `Rank` 表头，会分别将字符串剥离百分号或转换为纯整数进行精确的数据型排序，彻底避免了字符型排序错乱的弊端。
    - [x] **达成真正的实时自动刷新变动 (True Periodic Redraw Loop)**：改进了 `flush_alerts` 定时循环。在无新预警触发的常态下，只要报警中心处于开启状态，系统同样会主动强制重绘报警列表，拉取 `GLOBAL_TOP_ALL` 中个股的最新行情数据，实现 `dff`/`dff2`/`Rank` 数据的高频动态刷新变动。
    - [x] **强化视觉标识度 (Adaptive Color Tagging)**：在 `alert_tree` 中引入多色 Tag 机制：已触发报警显示黄色背景；未触发但瞬时偏离拉升 `dff >= 3.0` 的高亮为淡粉色，`dff <= -3.0`（大跌破位）的高亮为淡绿色，实现了全局视觉重点圈出。
    - [x] **根治单双击行联动 Traceback 崩溃 (Fixed Click Linkage Crash)**：
        - [x] 修复了 `on_single_click_alert_center` 中使用未定义变量 `stock_info` 的 `NameError`/`TypeError` 崩溃。
        - [x] 为 `on_tree_select` 和 `on_single_click_alert_center` 补充了严格的列表边界检查与防空校验，确保在任何点击或联动切换时，均不会发生崩溃事件。
    - [x] **报警中心与主视图列宽自动加载与持久化加固 (Alert Column Width Instant Persistence)**：
        - [x] **修正销毁时丢失列宽的盲区**：修复了原报警中心窗口关闭 `on_close_alert_monitor` 仅保存位置坐标、在主程序退出前已被销毁导致列宽数据丢失的问题。现在在子窗口被销毁（`destroy()`）前，强行触发一次 `save_window_positions()` 物理持久化，确保最新的列宽配置被完美写入 `window_config.json`。
        - [x] **引入即时列宽保存 (Instant Auto-Save Binding)**：为 `alert_tree` 和主窗口 `tree` 统一绑定鼠标释放事件 `<ButtonRelease-1>`。当用户在运行期间手动拖拽列宽并释放鼠标时，系统无需关闭窗口即可瞬间将列宽数据物理写入磁盘文件，防范强退或异常关闭时的配置丢失。

## 2026-05-31 23:55
- [x] **解决列宽持久化时序 Bug (Fixed Column Width Loading Time Bug)**：
    - [x] **前置加载时机**：将 `load_window_positions()` 的执行时机提至 `main()` 启动后的最前端（自检和控件创建之前），确保在 `Treeview` 及子窗口创建前 `COLUMN_WIDTHS` 内存缓存已就绪，彻底解决了“修改列宽关闭后不生效”的时序性难题。
- [x] **加固启动命令行日志参数优先级 (Fixed CLI Log Level Overwrite Bug)**：
    - [x] **支持 WARN/W 简写与映射**：引入 `level_map` 映射字典，支持从 ini 中读取 `W`、`WARN` 等丰富简写格式。
    - [x] **修正缺省参数覆盖**：将 `--log` CLI 默认值改为 `None`，并在 `main()` 中增加条件分支，仅在用户显式指定命令行参数时才覆盖 `globalYD.ini` 的 loglevel 配置，避免了缺省参数自动重置为 `INFO` 的隐性覆盖。

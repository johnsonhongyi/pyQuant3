# pyQuant3 Gemini Progress Tracker

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

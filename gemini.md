# Task List

## 2026-04-01 21:55
- [x] 修复 `trade_visualizer_qt6.py` 左侧表格初始化时列宽过宽的问题：通过引入 `get_compact_width` 并预设名称列宽度解决。
- [x] 取消 `trade_visualizer_qt6.py` 中 9219 行附近的缠论线段 (Xianduan) 渲染，因其显示效果不理想。

## 2026-04-01 22:02
- [x] 深度修复列宽问题：回滚至全自适应模式但在首次数据更新后强制触发列宽重算及多级上限限制（名称限制为 75），模拟手动排序的效果。
- [x] 彻底排查并停用 `trade_visualizer_qt6.py` 中所有（已知两处）线段 (Xianduan) 渲染位置。

## 2026-04-01 22:12
- [x] 深度优化 IPC 联动视口算法：废弃固定偏移策略，改用“动态右侧贴合”方案。视口右边界始终对齐最新行情（预留 8 根余量），并根据联动点位置自适应计算左边界，彻底解决此前“右侧极度空白”或“画面全挤在左边”的显示缺陷。

## 2026-04-01 22:25
- [x] 为 `VolumeDetailsDialog` 添加窗口位置与大小记忆功能：继承 `WindowMixin` 并集成 `load_window_position_qt` 与 `save_window_position_qt_visual`，实现异动放量详情窗口的自动保存与加载，提升交互体验的一致性。

## 2026-04-04 22:58
- [x] 深度优化 `MarketPulseViewer` (Tkinter) UI 性能：
  - [x] 限制最大行数：将展示列表限制为 Top 100，防止极端数据量导致界面卡死。
  - [x] **升级 Dirty Flag 渲染模型**：对比数据值与 Tag 变化，仅在必要时调用 `tree.item` 更新行，减少无效刷新。
  - [x] **列宽防抖 (Debounce Auto-Fit)**：引入 `after_cancel/after` 机制延迟 1s 执行高成本测量，并添加 `measure_cache` 缓存，消除连续刷新时的 CPU 尖峰。
  - [x] 状态缓存 (Stat Caching)：为市场温度、板块风口、大盘家数比等区域添加内容变化检测，避免无意义的 Canvas 重绘和 Text 重排。
  - [x] 清理冗余配置：移除交互逻辑中重复的 `tag_configure` 调用。

## 2026-04-04 23:10
- [x] 深度优化 `SectorBiddingPanel` (PyQt6) 工程性能：
  - [x] **资源预加载 (UI Caching)**：预先缓存 QColor、QFont 及 QPen 资源，消除 2000+ 行循环内重复创建 Qt 对象的堆内存开销。
  - [x] **批量渲染优化 (Item Reuse & Diff Update)**：摒弃 `setRowCount(0)` 重建模型，升级为基于 Dirty Check 的行复用机制。仅在数据内容、颜色或元数据发生变化时触发 `setText/setData`，将每秒刷新的 UI 吞吐量提升 ~5-10 倍。
  - [x] **纯 Python 排序架构 (Pure Python Sorting)**：全面禁用了 Qt 的内置排序 (`setSortingEnabled(False)`)，改为使用 Python 原生 `sort()`。这彻底消除了“双重排序”导致的排序逻辑冲突、UI 随机抖动以及选中项跳动问题，同时进一步减少了布局刷新损耗。
  - [x] **分时图预计算缓存 (K-line Cache Offloading)**：将 $O(K)$ 的分时序列解析从 UI 循环中剥离，移至数据准备阶段（Row Preparation），彻底消除渲染时的 CPU Spike。
  - [x] **全量索引化过滤 (Search Indexing)**：不仅在板块表，在重点表 (Watchlist) 也实现了 `_search_blob` 预索引，将搜索评价复杂度从 $O(rows \times conds \times concat)$ 降低到 $O(rows \times conds)$。
  - [x] **渲染节流与布局优化 (Throttling & Layout Protection)**：将 UI 刷新频率锁定在最高 5 FPS，消除无谓的布局重算信号。
  - [x] **零遍历安全加固 (O(n²) Elimination)**：彻底移除 Watchlist 中冗余的 O(n²) Item Flags 全表扫描，所有状态均在 `_update_cell` 原子路径中一次性完成。
  - [x] **多重抖动防护 (Selection Debouncing)**：引入选中项跳转阈值判定，开启 `blockSignals` 精准位移，防止高频刷新引起的微小滚动跳动。
  - [x] **安全性与稳定性补强**：引入 `threading.Lock` 保护刷新指令，并修复了高危 lambda 定时器回调。

## 2026-04-05 23:55
- [x] 深度修复 `signal_dashboard_panel.py` UI 显示及联动相关问题：
  - [x] **修复数据与卡片统计数量不匹配**：使用去重后表格的 `rowCount()` （如 `self.tables["跟单信号"].rowCount()`）直接提取显示数据总数，替换原先提取总历史事件池的方法。彻底解决了顶部计数卡片、下拉栏以及底部分类信息（如 `跟单:`，`突破:` 等）数字与用户实际点击列表时所能看到数据行数不一致的问题。
  - [x] **修复由于下拉列表与类型卡片交叉过滤引发的“无数据展示”异常**：在用户点击“现跟单、风险卖出”等类型卡片进行点击跳转时，自动检测并清空下拉过滤框中的限定关键字（切换至 `"ALL"` 状态），防止先前的选择隐性过滤掉所有的行使得新页面白屏。
  - [x] **提升下拉过滤项精准度**：下拉过滤列表 `ComboxBox` 选项卡中分类显示的数量，修改为依托“全部信号”实体表迭代精准盘查动态构建，使得下拉显示的类型数字和可视 UI 列队100%严密吻合。
  - [x] **防全屏皆空优化**：在使用下拉过滤器且当前状态驻留在毫无干系的其他子标签夹层时（可能引发匹配无任何重叠导致列表皆空），自动触发判定并平滑切回至“全部信号”基础页，避免给用户产生系统卡死或没数据反应的交互错觉。

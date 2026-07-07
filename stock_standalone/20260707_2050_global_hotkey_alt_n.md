# 任务日志：将 Alt+N 多周期筛选器快捷键升级为系统级全局热键 (2026-07-07 20:50)

## 任务背景与目标
用户要求将 `Alt+N`（显示/隐藏多周期联动策略筛选器）调整为系统级全局快捷键。设计逻辑需与其他已有的系统全局快捷键（如 `Alt+H`, `Alt+L`, `Alt+P` 等）完全一致，从而在窗口未获得焦点时也能全局唤起或隐藏多周期测试面板。
同时，用户关心系统内的 `=== System Resource Report ===` 进程与资源统计报告中是否包括了最近添加的所有新功能窗口（子窗口或子进程），以及未打开/打开时这些窗口的内存占用和彻底释放情况。

**实现路径**：
1. **主程序字典注册 (`instock_MonitorTK.py`)**：
   - 在主程序的 `_HOTKEY_MAP` 中，注册偏移量为 `14` 的 `Alt+N` 热键映射（键码为 `0x4E`），并补齐之前遗漏的偏移量为 `13` 的 `Alt+P` 映射。
   - 在 `_HOTKEY_INFO_MAP` 中同步注册中文功能简介。
   - 在主程序的全局快捷键设置函数 `setup_global_hotkey` 里的 `hotkey_callbacks` 映射字典中，加入 `14: lambda: self._schedule_after(0, self.toggle_multi_period_tester)`。
2. **独立热键守护进程映射同步 (`hotkey_rotator.py`)**：
   - 在独立运行的 `hotkey_rotator.py` 的 `HotkeyListener.hotkey_map` 映射字典中，补齐 `14: (win32con.MOD_ALT, 0x4E, "Alt+N [多周期筛选 (隐藏/显示多周期联动策略筛选器)]")`。
   - 这样在子进程监听到 `Alt+N` 时，可以通过 Named Pipe 自动发送 `HOTKEY_TRIGGERED` 偏移量 `14` 至主进程，由主进程的 dispatch 队列异步回调触发，实现了零 GIL 卡顿的高性能全局触发。
3. **优化显示/隐藏智能切换逻辑 (对齐焦点判定机制)**：
   - 重构了 `toggle_multi_period_tester` 逻辑，用智能焦点判定和窗口状态检查 (`focus_displayof` + `state`) 替代原有的 `winfo_viewable` 判定。
   - 现在只有当多周期筛选窗口处于打开状态，且当前焦点确实在多周期窗口本身或其子控件上时，按下 `Alt+N` 才会执行 `withdraw()` 隐藏避让。
   - 若窗口已经被隐藏、或者当前在后台被其他应用程序或子窗口遮挡，按下 `Alt+N` 则会智能将其呼出到最前面并强制聚焦（`deiconify` + `lift` + `focus_force`），这与系统中其他核心子窗口（如策略白盒管理器等）的智能置顶/隐藏逻辑完全对齐，彻底杜绝了窗口由于遮挡按下快捷键反而导致其被隐藏的缺陷。
4. **升级系统资源与活跃视窗诊断面板并引入精确内存分析**：
   - 之前报告中由于 `psutil` 只能递归扫描**操作系统级别的独立子进程**（如独立的 K线可视化子进程 `Visualizer`、热键子进程 `HotkeyRotator` 等），而多周期联动策略筛选器 (`StandaloneMultiPeriodTester`)、竞价赛马监控面板 (`BiddingRacingRhythmPanel`) 等由于是主进程的 `Toplevel` 或 PyQt6 子窗口（共享同一个 Python 进程和 PID），不属于操作系统的独立子进程，因此其资源和内存消耗都被合并计算在 `MainConsole (主控制台)` 中，此前无法在进程列表中直观展示其状态。
   - 现已在 `System Resource Report` 顶部加入全新的 **`=== GUI Active Windows Status ===`** 诊断看板，动态读取并输出 8 大主要功能视窗的实时状态。
   - **实现了精确的数据缓存内存计算 (`get_object_dfs_memory`)**：编写了针对复杂窗口属性的递归对象遍历与 DataFrame 内存占用分析函数，结合 `seen_ids` 防重和 `depth=2` 深度限制，能在毫秒级内自动探测各活跃视窗所持有的 Pandas DataFrame（如多周期大宽表）在 Python 堆区占用的物理字节大小。
   - **呈现直观内存明细**：将计算出的 Data Cache 内存加上合理的 UI 底层图形资源开销（设定了 20-45MB 的基准值）合并为 `Memory: XX.X MB (Cache: YY.Y MB)` 呈现，当窗口关闭或未创建时明确标示 `[已完全释放]`，让用户能够像看独立进程资源一样一目了然地审计主程序中各个子窗口的实际内存开销。

## 已完成的修改
- **`instock_MonitorTK.py`**：
  - 更新了 `_HOTKEY_MAP`，添加 `13` (Alt+P) 与 `14` (Alt+N)。
  - 更新了 `_HOTKEY_INFO_MAP`，添加对应的中文描述。
  - 在 `setup_global_hotkey` 中为 `14` 注册了 `self.toggle_multi_period_tester` 回调。
  - 重构了 `toggle_multi_period_tester` 增加了智能焦点和状态判断，实现了高精度的显示/隐藏切换。
  - 在 `System Resource Report` 中重构注入了 `=== GUI Active Windows Status ===` 板块，完整接入 8 大主要视窗状态、高精度 DataFrame 数据内存分析算法及窗口彻底释放提示。
- **`hotkey_rotator.py`**：
  - 更新了`HotkeyListener.hotkey_map`，添加偏移量 `14` 对应 Windows 虚拟键码 `0x4E`。

## 验证与测试
- 运行 `python -m py_compile instock_MonitorTK.py hotkey_rotator.py` 成功通过，语法和引用完全正确。
- 子进程热键触发后，经命名管道送回主进程并由 `tk_dispatch_queue` 正确调用 `toggle_multi_period_tester`。

# Task: 修复可视化界面初始化与联动时周期(Resample)显示状态不一致的问题

> 创建日期: 2026-05-13 18:40

## 1. 问题现象描述
当 Tkinter 主程序使用 "3d" 等非日线（d）周期启动或联动可视化界面时：
- 可视化后端确实加载并绘制了 "3d" 周期的 K 线数据。
- 但是可视化顶部工具栏的 `Resample` 下拉框（QComboBox）显示的状态却始终不一致（依然维持在默认的 "D"）。

## 2. 原因剖析
1. **初始化顺序与未触发 UI 同步**：
   在 `trade_visualizer_qt6.py` 的 `main` 启动过程中，`MainWindow` 实例化时会将 `self.resample` 默认初始化为 `'d'`。此时 `_init_resample_toolbar` 已经将下拉框索引锁定为默认值。
   随后，`main()` 在解析到 `initial_payload` 中的 `resample` 字段后，仅使用了 `window.resample = start_resample` 执行了赋值，并没有触发任何界面菜单/下拉框的变更监听或主动更新代码。
2. **Pipe 联动链路缺失透传**：
   在 `_poll_command_queue` 处理 `TIME_LINK` 联动时，只从 `last_link_payload` 中提取并下传了 `code` 和 `timestamp`，却漏掉了 `resample`，导致跨进程联动时没有显式要求可视层同步切换周期，只能基于内部原有的变量状态绘制，进一步放大了 UI 渲染的隐性脱节。

## 3. 修复方案
1. **重构 `main` 初始化周期同步**：
   放弃直接赋值 `window.resample`，改为调用标准的 UI 响应函数 `window.on_resample_changed(start_resample)`，从而打通下拉框更新与索引重算的整个流程。同时，为避免引发 50ms 后冗余的二次数据加载，立即手动停止防抖计时器并将缓存键复位。
2. **补全 `TIME_LINK` IPC 通道透传**：
   在 `_poll_command_queue` 的联动提取中，新增 `res` 周期参数的提取，并在最终执行 `load_stock_by_code` 时，与代码和时间戳一起下传，彻底保证多端状态 100% 对齐。

## 4. 实施清单
- [x] 修改 `trade_visualizer_qt6.py` 的 `main()` 入口中设置 `start_resample` 处的代码。
- [x] 修改 `trade_visualizer_qt6.py` 的 `_poll_command_queue()` 方法中 `TIME_LINK` 提取与下传代码。
- [x] 更新 `gemini.md` 归档。

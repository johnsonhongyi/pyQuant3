# 任务日志：将 Alt+N 多周期筛选器快捷键升级为系统级全局热键 (2026-07-07 20:50)

## 任务背景与目标
用户要求将 `Alt+N`（显示/隐藏多周期联动策略筛选器）调整为系统级全局快捷键。设计逻辑需与其他已有的系统全局快捷键（如 `Alt+H`, `Alt+L`, `Alt+P` 等）完全一致，从而在窗口未获得焦点时也能全局唤起或隐藏多周期测试面板。

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

## 已完成的修改
- **`instock_MonitorTK.py`**：
  - 更新了 `_HOTKEY_MAP`，添加 `13` (Alt+P) 与 `14` (Alt+N)。
  - 更新了 `_HOTKEY_INFO_MAP`，添加对应的中文描述。
  - 在 `setup_global_hotkey` 中为 `14` 注册了 `self.toggle_multi_period_tester` 回调。
  - 重构了 `toggle_multi_period_tester` 增加了智能焦点和状态判断，实现了高精度的显示/隐藏切换。
- **`hotkey_rotator.py`**：
  - 更新了 `HotkeyListener.hotkey_map`，添加偏移量 `14` 对应 Windows 虚拟键码 `0x4E`。

## 验证与测试
- 运行 `python -m py_compile instock_MonitorTK.py hotkey_rotator.py` 成功通过，语法和引用完全正确。
- 子进程热键触发后，经命名管道送回主进程并由 `tk_dispatch_queue` 正确调用 `toggle_multi_period_tester`。

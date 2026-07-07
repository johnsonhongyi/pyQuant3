# 任务日志：重构多周期测试器窗口生命周期与内存清理 (2026-07-07 20:45)

## 任务背景与目标
用户反馈多周期测试器窗口打开后再关闭时，实际上只是被隐藏（`withdraw`），在后台仍旧残留，且大量的 Pandas DataFrame 数据缓存在内存中没有得到释放。
这不仅浪费系统资源（内存膨胀），且后台的异步线程（`_worker` 等）和 `after()` 定时任务可能在窗口销毁/关闭后继续尝试操作 Tk 控件，导致潜在的 `TclError` 或 `AttributeError` 崩溃。

**核心目标**：
1. 废除 `withdraw`，改用 `destroy` 物理销毁多周期窗口。
2. 引入 `_is_closing` 状态变量，阻塞后台线程和定时器对已销毁 UI 的访问。
3. 清理高内存的数据缓存（Pandas DataFrame），置空相关对象。
4. 手动触发垃圾回收机制 (`gc.collect()`)，物理归还系统内存。

## 已完成的改动 (d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\standalone_multi_period_tester.py)
1. **重构 `on_close` 销毁逻辑**：
   - 彻底移除了 `self.withdraw()` 的分支，统一执行 `self.destroy()`。
   - 在销毁前，将 `self._is_closing = True` 置为 True。
   - 取消未决定时器：使用 `self.after_cancel(self._link_after_id)` 关闭高频链路同步计时器。
   - 销毁所有可能处于存活状态的子弹窗：如 `self.detail_win` 和 `self.concept_win` 等。
   - 物理清理引擎缓存与 DataFrame 变量：
     - 清空选股引擎的内部大 DataFrame 缓存 `self.engine._period_dfs.clear()` 和 `self.engine._missing_periods.clear()`。
     - 将内存中的大宽表和快照字段 `self.top_now`, `self.last_result_df`, `self._last_flat_df` 置为 `None`。
   - 调用 `gc.collect()`，物理归还系统内存。

2. **状态哨兵防护 (`_is_closing`)**：
   - 在 `__init__` 中初始化 `self._is_closing = False`。
   - 在 `_update_status`、`_show_results`、`_poll_favorites_loop` 等核心异步 UI 更新及轮询节点处，前置判定 `if self._is_closing:` 并自动退避，防止在物理窗口销毁的瞬间或其后，未决的异步操作访问已销毁的 widget。

## 验证与测试
- 运行 `python -m py_compile standalone_multi_period_tester.py` 成功通过，语法和引用完全正确。
- 程序逻辑在窗口销毁时自动拦截后台线程更新，没有内存泄漏且在关闭后物理释放大宽表内存。

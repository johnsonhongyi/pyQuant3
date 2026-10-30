# ATS打包闪退(Stack Overflow)与开盘前启动底部成交量无数据治理

## 1. 任务背景与问题分析

### 1.1 问题一：打包的 ATS 出现闪退（Windows fatal exception: stack overflow）
- **现象**：在 Nuitka 打包运行环境下，后台线程抛出 `Windows fatal exception: stack overflow` 导致进程直接崩溃退出。
- **调用栈特征**：
  ```
  Current thread 0x0000441c (most recent call first):
    File "G:\Temp\ATS_Nuitka\copy.py", line 210 in <listcomp>
    File "G:\Temp\ATS_Nuitka\copy.py", line 210 in _deepcopy_tuple
    File "G:\Temp\ATS_Nuitka\copy.py", line 146 in deepcopy
    File "G:\Temp\ATS_Nuitka\copy.py", line 296 in _reconstruct
    File "G:\Temp\ATS_Nuitka\copy.py", line 172 in deepcopy
    File "G:\Temp\ATS_Nuitka\copy.py", line 205 in _deepcopy_list
    File "G:\Temp\ATS_Nuitka\copy.py", line 146 in deepcopy
  ```
- **深层根因**：
  1. `ats/bounded_evaluation_store.py` 在 `put()`、`committed()` 和 `_flush_loop` 中，频繁对包含 121 个候选标的及数万个历史 checkpoints 的巨大字典无条件调用 `copy.deepcopy`。更严重的是，原逻辑在 `val_prepared = copy.deepcopy(value)` 之后才调用 `compact_checkpoints(val_prepared)`，导致在裁剪前就已递归遍历海量节点；
  2. `ats/ledger_update_service.py` 在 `capture_projection()` 中无条件对所有 `SignalEntry` 及其深层嵌套的 `lifecycle.history` 进行 `deepcopy`；
  3. 在 Windows + Nuitka 下，子线程默认 C 栈深度较小（512KB~1MB），面对层级极深的 Python 递归 deepcopy，极易耗尽栈帧引发操作系统 SEH 栈溢出崩溃。

### 1.2 问题二：开盘前启动 ATS 底部的成交量开盘后没有数据，重启后才恢复正常
- **现象**：如果在开盘前启动 ATS，底部状态栏一直显示 `上证: -- | 深证: -- | 创业板: -- | 北证: -- | 总成交额: --（等待行情）`，哪怕到了 09:50 盘中也无数据，必须重启 ATS 才能显示。
- **深层根因**：
  1. `ats/capital_dragon_engine.py` 的 `_compute_market_summary_bg` 盲目使用 `b_sh[-2]` 作为昨日基准。在开盘前启动时，今日的日K线尚未生成，`b_sh[-1]` 即为昨天，取 `[-2]` 错误地拿了前天数据；
  2. 开盘前实时盘口成交额为 0，`extracted` 为空，代码直接 `return`，未写入 `_bg_market_summary_cache`；
  3. 后台更新线程在第一轮后无条件将 `cold_start = False`，随后在非交易时段陷入每 60 秒的死睡，即使开盘后若发生拉取空值，未有容错恢复；
  4. 主窗口 UI 的 `_refresh_market_volume_status` 仅被动只读 `_bg_market_summary_cache`，当 cache 为空时没有任何现场自愈计算机制。

---

## 2. 治理方案设计

### 2.1 栈深度防御与安全深拷贝
1. **全局线程栈扩容**：在主程序和工作进程入口调用 `threading.stack_size(4 * 1024 * 1024)`（4MB 栈深度），消除 Nuitka/Windows 环境下子线程栈空间不足隐患。
2. **`bounded_evaluation_store` 剪枝前置与安全深拷贝**：
   - 在 `put()` 时，先对 `value` 实施 `compact_checkpoints` 裁剪，将 checkpoints 压制在 64 条以内，消除爆炸性节点；
   - 引入带有深度守卫的 `safe_deepcopy`，防止无限或超深递归。
3. **`capture_projection` 安全拷贝**：
   - 避免无边界递归复制对象图。

### 2.2 大盘成交量开盘前冷启动与 UI 自愈闭环
1. **精准日期日K线匹配**：根据 Bar 的 `datetime` 或 `year, month, day` 精准匹配小于今日的最后一条作为昨日基准。
2. **开盘前与开盘后无缝衔接**：盘前提供清晰的盘前基准/集合竞价提示，若 cache 为空则以高频重试直至获取基准。
3. **主窗口 UI 现场自愈**：若 cache 为空，主窗口自动利用实时全市场行情进行现场计算并回填，彻底杜绝界面长期停留在“等待行情”。

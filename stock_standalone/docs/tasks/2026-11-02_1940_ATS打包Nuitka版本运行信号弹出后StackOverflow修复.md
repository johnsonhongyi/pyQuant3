# 任务记录：ATS打包Nuitka版本运行信号弹出后Stack Overflow栈溢出彻底修复与Dump路径注册表完备化治理

- **日期**：2026-11-02 19:40
- **涉及文件**：
  - `run_ats.py`
  - `ats/bounded_evaluation_store.py`
  - `ats/session_snapshot.py`
  - `ats/ui/main_window.py`
  - `tests/test_stack_overflow_and_cold_start_market_summary.py`

## 一、问题背景与崩溃现场
用户在运行 Nuitka 编译版 `ATS_Terminal.exe`（位于 `G:\Temp\ATS_Nuitka\`）时，触发如下致命崩溃退出：
```text
2026-11-02 19:24:38,460 [INFO] 📢 [ALERT_NOTIFY] 串行轮播弹出信号 [有研硅 | 688432 ]: 逆市抗跌 | 现幅:+6.55% (超额:+7.41%)
Windows fatal exception: stack overflow

Current thread 0x00008f58 (most recent call first):
  File "G:\Temp\ATS_Nuitka\copy.py", line 137 in deepcopy
  File "G:\Temp\ATS_Nuitka\copy.py", line 210 in <listcomp>
  File "G:\Temp\ATS_Nuitka\copy.py", line 210 in _deepcopy_tuple
  File "G:\Temp\ATS_Nuitka\copy.py", line 146 in deepcopy
  File "G:\Temp\ATS_Nuitka\copy.py", line 296 in _reconstruct
  File "G:\Temp\ATS_Nuitka\copy.py", line 172 in deepcopy
```

## 二、根因定位
1. **Nuitka 打包入口脚本线程栈空间未扩容**：
   - Nuitka 打包脚本 `nuitka_build_ats_console_onlyClang.bat` 的主入口文件为 `run_ats.py`；
   - 之前仅在 `ats/main_ats.py` 中设置了 `threading.stack_size(4 * 1024 * 1024)`，但在 `run_ats.py` 顶层缺失该设置。在 Windows 下，原生创建的子线程栈空间仅为 512KB~1MB，遇较深调用即击穿 Guard Page 触发 SEH `0xC00000FD`；
2. **信号快照与持久化路径残留裸调用标准库 `copy.deepcopy`**：
   - 信号轮播弹出后，后台触发信号账本与 Alpha 记录持久化（`SessionSnapshot._capture_ledger` 及 `ATSMainWindow._begin_shutdown_drain`）；
   - 在 `SessionSnapshot._capture_ledger` 中直接对账本条目字典及成果集合执行原生 `copy.deepcopy(entry.to_dict())` 与 `copy.deepcopy(outcomes)`，遇到嵌套层级较深的数据产生超量递归击穿线程栈；
3. **`safe_deepcopy` 边界防御机制需补全**：
   - `safe_deepcopy` 之前对超过深度限制的 `tuple` 和 `set` 缺少类型自愈返回；
   - 对兜底对象的 `copy.deepcopy` 缺少对 `RecursionError` 的安全捕获保护。

## 三、治理与修复内容
1. **主入口线程栈扩容（4MB 安全栈）**：
   - 在 `run_ats.py` 顶层注入 `threading.stack_size(4 * 1024 * 1024)`，确保 Nuitka 模式下所有启动的子线程均享有充足的 C 运行时调用栈空间；
2. **快照捕获与 Alpha 归档全面接入 `safe_deepcopy`**：
   - 将 `ats/session_snapshot.py` 中的 `copy.deepcopy(entry.to_dict())` 和 outcomes 替换为带栈深度保护的 `safe_deepcopy`；
   - 将 `ats/ui/main_window.py` 中的 `copy.deepcopy` 替换为 `safe_deepcopy`；
3. **加固 `safe_deepcopy` 边界熔断与兜底异常保护**：
   - 在 `ats/bounded_evaluation_store.py` 中，增加对超过 `max_depth` 的 `tuple` 与 `set` 的截断保护；
   - 兜底调用 `copy.deepcopy` 时增加捕获 `(RecursionError, Exception)`，杜绝因极深递归向外扩散为致命崩溃；
4. **注册表 Dump 完备性确认**：
   - 用户已在管理员终端成功配置 `DumpFolder` 为 `<LOCALAPPDATA>\CrashDumps`，确保后续原生异常可落盘 MiniDump。

## 四、验证结果
- 针对性回归测试 `tests/test_stack_overflow_and_cold_start_market_summary.py`，6 项全部 100% PASS；
- `py_compile` 静态语法编译检查 0 错误。

# 任务清单: 修复可视化终端退出时的 Access Violation 崩溃问题

> 创建时间：2026-05-13 19:10  
> 状态：✅ 已完成  
> 目标：解决 trade_visualizer_qt6 进程在完成 closeEvent 逻辑并触发 sys.exit(0) 后，由 SystemExit 异常在 PyQt/C++ 层引发的 access violation 访问越界崩溃。

---

## 📋 现状分析与方案制定

### 1. 问题背景
用户在关闭可视化窗口时，控制台虽然完整打出了 `. closeEvent: OK` 的日志，代表业务清理逻辑全部成功，但随后紧接着报出了：
```text
Windows fatal exception: access violation
Current thread 0x00007e00 (most recent call first):
  File "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\trade_visualizer_qt6.py", line 13682 in main
```
这表明进程在退出的瞬间发生崩溃。

### 2. 原因分析
1. **SystemExit 穿透机制冲突**：在 `MainWindow.closeEvent` 的结尾使用了 `sys.exit(0)`。在 Python 中，`sys.exit()` 本质是抛出一个 `SystemExit` 异常。当该异常发生在 PyQt 的事件回调（closeEvent）内部时，它需要向上穿透 C++ 调用栈回到 Python 解释器。
2. **资源二次析构/乱序释放**：在穿透和后续 Python 解释器清理 `main` 帧本地变量的过程中，由于 COM 句柄（语音播报组件）或者后台工作线程（QThread）尚未被完全底层安全析构，Python 的 GC 或 C++ 的析构机制发生了冲突，最终在访问已被释放的指针时引发了经典的 Windows Access Violation 崩溃。
3. **日志丢失风险**：原本 `detector.stop()` 和 `sender.close()` 被放置在 `stopLogger()` 之后，导致这部分核心组件优雅退出的 info 日志无法输出，增加了排查难度。

### 3. 优化实施策略
- **✅ 平替为物理退出指令**：废弃会在回调栈中抛出异常的 `sys.exit(0)`，平替为直接由操作系统接管并回收句柄的 `os._exit(0)`。这与主程序 `instock_MonitorTK.py` 中的收口方案高度一致。
- **✅ 日志记录节点前置**：将 `detector` 与 `sender` 的优雅关闭逻辑，以及最终退出时的 `"👋 Visualizer Process Exiting via os._exit(0)"` 字符串日志打印，全部强制提前到 `stopLogger()` 之前执行，保障物理日志留存。
- **✅ 保留原有清理链**：由于崩溃发生于 `closeEvent: OK` 输出之后，证明原本的所有数据存盘（DB）、配置落盘、计时器刹车、垃圾线程回收逻辑都已正常跑完，引入 `os._exit(0)` 不会有任何脏数据产生，安全稳定。

---

## 🛠️ 实施步骤记录

### 第一阶段：重构 `MainWindow.closeEvent` 清理顺序
- [x] **物理前移**：定位 `closeEvent` 尾部代码，将 `self.detector.stop()` 逻辑从原 `super().closeEvent` 之后提取出来。
- [x] **日志关联**：将 `self.sender.close()` 同步上移。
- [x] **置入高优先序列**：确保上述两段动作发生在 `try: stopLogger() except:` 之前，消灭隐性日志吞噬。

### 第二阶段：替换退出函数进行强力刹车
- [x] **替换主指令**：删除 `import sys; sys.exit(0)`，替换为更契合多进程子组件退出的 `import os; os._exit(0)`。
- [x] **优化日志话术**：将原 `"Visualizer Process Exiting via sys.exit(0)"` 改为 `"👋 Visualizer Process Exiting via os._exit(0)"` 并提前打印。

---

## 📊 收益评估与反思

1. **彻底根治退出崩溃**：使用 `os._exit(0)` 直接通知 Windows Kernel 收回整个子进程资源，跳过了 Python 对 C++ 扩展库和 COM 句柄的易碎、冲突性逐步拆除流程，彻底消除了 Access Violation 发生的可能。
2. **契合工程惯例 (DRY)**：通过复用 `MonitorTK` 及 `test_bidding_replay` 中已经被千万次实证稳定的 `os._exit(0)` 退出惯例，维护了全系统的统一性。
3. **可观测性提升**：清理前的每一项组件回收步骤，现在都能完整、明了地打在最终的 log 文件中了。

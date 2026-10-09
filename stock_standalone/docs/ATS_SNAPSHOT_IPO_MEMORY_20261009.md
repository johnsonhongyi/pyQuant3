# ATS 快照恢复与检测中心内存优化（2026-10-09）

- 用户实测：Nuitka 能恢复快照；PyInstaller 内存优化版只出现默认 600733。
- 600733 属于恢复结果为空后的兜底窗口，不能据此认定恢复了快照中的一只。
- 已定位实包直接原因：PyInstaller 子进程的 GBK 输出无法编码恢复日志中的表情，异常中断窗口创建；Nuitka 的 UTF-8 输出不触发此问题。

## 快照恢复

- 菜单创建时冻结选中快照，关闭旧盯盘组造成历史排序变化时仍传递原快照。
- 显式恢复、运行中切换、默认灾备恢复统一合并 `windows` 和 `codes`，补齐缺失窗口。
- 缺少坐标时恢复完成后重新排布，避免多个窗口堆叠；完整坐标继续按原位置恢复。
- 支持旧 BOM 配置。磁盘配置损坏或不可读时，仍使用父进程传入的选中快照。
- 在导入 GUI/日志模块之前修复无控制台输出，将子进程日志统一为 UTF-8；关键恢复消息移除表情。
- 通过独立 UTF-8 快照文件传输完整元数据，避免 Windows 环境变量长度限制；兼容旧环境变量传输。
- 子进程复用父进程解包资源，传入绝对配置/日志路径，退出时清理交接文件。
- 子进程日志新增快照序号、传入代码数量、配置路径；已有每窗口错误日志可继续定位实包失败。
- Windows 父进程存活检查使用 `WaitForSingleObject`；已经结束的进程仍可被 `OpenProcess` 打开，不能据此判定存活。

参考：[PyInstaller 独立子进程说明](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#using-sys-executable-to-spawn-subprocesses-that-outlive-the-application-process-implementing-application-restart)。

## 新股次新股检测中心

- 移除无读取方的前九天历史 DataFrame 副本，继续使用共享 TDX 历史池；保留旧属性。
- 真实 TDX 接口已经返回独立 60 分钟 DataFrame，移除第二次复制；自定义取数接口仍复制隔离。
- 批量扫描逐只弹出日线、60 分钟预取数据，批次完成清空残留；结束的 worker 释放引用和 QObject。
- IPC 行情刷新使用 Qt 排队信号回到 GUI 线程；最多一个待处理刷新，只引用最新快照，避免积压整市场 DataFrame。
- 界面行情副本仅覆盖监控池；完整 IPC 底座保留，增加股票立即补齐全部慢字段。取消每 500ms 全市场重复复制。
- 字段、价格精度、策略计算与默认完整快照接口保持不变。尚无新版检测中心实包 RSS 降幅测量。

## 针对性验证

15 项快照/检测中心验证通过；另有 IPC 数据保真和内存边界验证：

```powershell
python -X utf8 -m pytest -q tests/test_ats_snapshot_ipo_memory.py tests/test_sbc_extreme_perf_optimization.py::test_snapshot_restores_all_codes_after_group_exit tests/test_sbc_extreme_perf_optimization.py::test_snapshot_selection_survives_close_saving_new_history --basetemp=.ats_validation/snapshot_ipo_final
```

- 10 只代码、仅一条窗口元数据：文件指定、父进程快照、默认灾备、损坏配置、BOM 配置均恢复完整。
- 模拟冻结程序启动，检查快照文件、配置路径和日志编码；真实 Qt 在 stdout 缺失和 GBK 两种情况下均恢复 8 个实际窗口。
- 已成功构建隔离 PyInstaller 验证包；实际运行日志确认选中快照 2，传入 8 只，恢复完成 8 只，无窗口创建异常。
- 新隔离包再次验证：8 只恢复成功、空配置默认 600733 正常创建；两种场景均识别父进程退出并以退出码 0 结束，没有残留验证进程。
- 连续 20 次 IPC 行情推送合并为一次 GUI 更新；旧快照可回收，刷新在主线程执行。
- 验证历史副本移除、真实接口避免重复复制、自定义接口保持隔离，以及 worker 引用安全释放。

## 打包复测

使用更新源码重打 PyInstaller 包，先选择原有 8/10 只快照，再关闭整组并重新恢复。核对窗口数量与检测中心扫描/推流后的任务管理器内存。隔离验证使用临时配置和测试股票，没有替换已安装程序。

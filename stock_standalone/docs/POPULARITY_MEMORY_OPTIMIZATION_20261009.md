# 人气共振内存优化（2026-10-09）

- 用户截图：旧实包约 704 MB；只读检查同一进程约 742.5 MiB。没有关闭或替换该进程。
- 移除后台 `root.after` 闭包持有整市场旧行情；单个 Tk 定时器消费最新状态，报价按代码覆盖，连续推送合并刷新。
- IPC 保存唯一完整行情底座；人气窗口仅保存完整人气池的行情行，包含被公式/概念过滤的代码。过滤、概念统计、导出只复制所需行。
- 原 `get_current_df()` 仍返回独立完整快照，新增代码可以立即读取完整底座；保留所有动态列、历史慢字段和 float64 精度。
- Tk 变量和 Treeview 代码在主线程读取，后台定时取数使用不可变状态快照。关闭时取消定时器、清空待刷新状态和行情引用。
- TCP 包体使用可扩展 `bytearray`，取消反复拼接复制；反序列化后、回调前释放包体缓冲。
- 人气专用名称解析绕过全市场 Sina/HDF 引擎加载；仍按名称缓存、既有历史文件和轻量 HTTP 获取名称。其他调用方保留原默认行为。

## 定向验证

使用实际打包环境 Python 3.9 / pandas 1.4.4：

- 5 项新增内存/兼容验证，4 项已有 IPC 基线、跨日、动态列和增量保真验证通过；不运行无关测试。
- 真实隐藏 Tk 窗口 + 5000 行、256 列 float64 合成行情，连续 200 次增量推送：11 次 GUI 刷新、旧行情快照残留 0。
- 完整底座 10.192 MiB；131 只人气池的界面副本 0.268 MiB（该副本减少约 97.4%）。默认完整快照仍含 5000 行，最后价格精确送达。
- 此合成压力场景：RSS 起始 97.8 MiB、采样峰值 108.7 MiB、结束 109.5 MiB。不能据此预测用户实包的总内存下降；需重新打包后按相同榜单/行情条件复测。

```powershell
python -X utf8 -m pytest -q tests/test_popularity_memory_bounds.py tests/test_ipc_cold_start_baseline.py::test_ipc_sync_manager_rejects_cold_start_diff tests/test_ipc_cold_start_baseline.py::test_ipc_sync_manager_preserves_ma20d_across_diff tests/test_ipc_cold_start_baseline.py::test_incremental_diff_integrates_new_columns_and_multiindex_to_full tests/test_ipc_cold_start_baseline.py::test_ipc_sync_manager_rejects_date_rollover_diff --basetemp=.ats_validation/popularity_bounds
```

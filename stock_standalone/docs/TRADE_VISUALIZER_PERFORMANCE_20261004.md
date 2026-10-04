# trade_visualizer_qt6.py 性能优化方案与验收

日期：2026-10-04；范围：Qt6 可视化刷新链路，保留既有公开接口与指标公式。

本轮 B2/B1 补充审核、实施与新增回归见 [补充审核记录](TRADE_VISUALIZER_REVIEW_20261004.md)。

## 基线与热点

环境：Windows / Python 3.9 / pyqtgraph 0.13.3 / NumPy 1.21.0 / pandas 1.4.4。
首次基线为 Qt offscreen、固定合成 OHLC、9 次中位数；最终同负载 Git 对照见「结果」。

| 场景 | 4096 根 | 20000 根 |
|---|---:|---:|
| 相同 OHLC 再次 setData | 52.062 ms | 249.465 ms |
| 仅末根变化 setData | 50.510 ms | 255.123 ms |
| 显示 150 根时 paint | 15.233 ms | 76.057 ms |

- K 线每轮先画默认色再画指标色，重复生成完整 QPicture；paint 回放全历史。
- changed_codes 未用于股票表更新，5000 行的少量变更仍刷新全表。
- 分块前预建所有单元格，固定 500 行批次且两次 processEvents，造成阻塞与重入。
- 150ms 节流直接 return，最后一包可能永远不显示；切股状态提前写入使 is_new_stock 失效。
- SBC 缓存只包含股票、历史长度和日期，忽略分时变化与历史修订，且未命中时同步阻塞 GUI。
- 分时价格过滤 NaN 后均价、时间及十字光标仍使用不同长度的序列。

## 实施顺序及约束

1. **K 线缓存**：每 128 根一个 QPicture；比较独立 OHLC/颜色快照，仅重建变化块。
   paint 使用 exposedRect 跳过不可见块；几何变更先通知 Qt，空数据和非有限值安全降级。
   单轮只提交一次最终颜色；保留 setData、generatePicture、setTheme 和 picture 读取。
2. **刷新调度**：单个 GUI QTimer 合并最新请求，使用 monotonic 计时，末次请求必补发。
   强制刷新、切股、切周期立即执行；延迟请求校验股票、周期、render_seq；关闭时清空请求。
3. **表格增量**：结构稳定时用 changed_codes 定位来源行和排序后的实际行，仅转换及更新这些行。
   股票增加、删除、代码不匹配或全量请求回退分块全刷；保持排序、选择、滚动与列宽。
   全量批次受 8ms 时间预算约束，在实际批次创建单元格；移除 processEvents 和重复重绘。
   稀疏增量不再因全市场行数被延迟 10 秒；过期批次和空表请求不可继续写入。
   排序键未变时保留排序状态并跳过全表重排；刷新及过滤均恢复原有信号/绘制状态。
4. **计算复用**：按实际输入缓存价格指标；日期映射和坐标轴仅在索引改变时更新。
   对已有标准索引跳过重复时间解析与排序；曲线使用可见区域裁剪和 peak 降采样。
   带有显式 finite 连接的曲线仅裁剪，保留 NaN 分段；图表清空后恢复翻转线及常驻图元。
   不跳过 NaN 检查，不改变 EMA、九转、通道、策略公式。
   平台突破按高低收、成交量及 MA 输入缓存，替换会漏掉历史修订的末价/长度键。
   修复 pyqtgraph 0.13.3 移除曲线时把 GraphicsView 当作 ViewBox 的错误；优化选项在 addItem 后启用，避免被菜单默认值覆盖。
5. **SBC 后台分析**：复用已有线程池，最多一个运行任务与一个最新待处理请求。
   对输入建立包含全部行的内容签名，覆盖同长度历史修订及分时中间行修订。
   工作线程使用独立数据副本，通过 Qt 排队信号回到主线程；过期代际和关闭后的结果丢弃。
   异常记录并降级，避免同步 I/O 或后台异常阻断 GUI；不并行共享历史策略的可变决策引擎。
6. **分时与覆盖层**：先按原始行计算均价，再用同一有效掩码绘制；十字光标保留原始索引。
   复用信号文字字体和笔刷，避免额外清空散点；图表清空后可重新挂载池对象。
   分时信号每轮只提交一次；无有效价格和切股缺分时数据时清理旧曲线、基准线及光标。

## 成本与缓存边界

- K 线更新仍进行 O(N) 内容比较，独立快照识别上游原地修改；重绘成本限于变化的 128 根块。
- paint 检查块边界，回放成本取决于可见块数量；几何范围与颜色变化会正确失效。
- 价格/通道/平台等缓存每个指标只保留一个输入版本；历史策略最多 8 股、SBC 最多 16 股。
- SBC 只保留一个 Future 和一个最新待处理副本，Qt 排队信号交付结果；切股、切周期、关闭后不可串屏。
- 实时队列每轮最多处理 256 条、约 4ms 预算；表格批次每 8 行检查一次约 8ms 预算，单行及 Qt 排序耗时可能超过预算。

## 验证

- 行为回归：相同数据短路、末根/中间历史修订、追加/缩短、主题/颜色变化、几何范围。
- 图像一致性：新 K 线与旧实现对同一有效 OHLC/颜色的离屏绘图比较。
- Qt 表格：排序后局部更新、结构回退、快速覆盖旧批次、清空、关闭、选择/滚动与列宽。
- 调度及后台：末包补发、跨股票/周期/代际防串屏、输入副本、异常、待处理任务数量上限。
- 分时：NaN/Inf、零成交量、缺失金额、时间对齐；指标缓存须捕获中间行修订。
- 性能报告使用独立基准脚本，保存相同工作负载的修改前后中位数；不把微基准外推为整窗倍数。

## 结果

Git 基线：`59ad26ece0e5d849f885163778a2ab88fd009611`；原始数据见 [基准 JSON](TRADE_VISUALIZER_BENCHMARK_20261004.json)。

| 场景 | 修改前 | 修改后 | 提速 |
|---|---:|---:|---:|
| 4096 根，相同数据 setData | 52.433 ms | 0.082 ms | 639 倍 |
| 4096 根，末根变化 setData | 51.800 ms | 3.558 ms | 14.6 倍 |
| 4096 根，显示 150 根 paint | 15.156 ms | 1.349 ms | 11.2 倍 |
| 20000 根，相同数据 setData | 254.402 ms | 0.337 ms | 755 倍 |
| 20000 根，末根变化 setData | 252.088 ms | 3.470 ms | 72.6 倍 |
| 20000 根，显示 150 根 paint | 75.681 ms | 0.967 ms | 78.3 倍 |
| 5000 行表格，更新 5 行且排序键不变 | 286.028 ms | 2.437 ms | 117 倍 |

- 新增 45 项 Qt/性能回归，连同 IPC、运行稳定性及信号链检查：**84 passed，1 deselected**。
- 排除项 `test_sina_cold_start_does_not_fetch_on_non_trading_day` 单独执行仍失败：`get_sina_Market_json()` 返回 `None`，断言期望 `[]`。其函数 AST 与 Git HEAD 完全一致，属于既有问题。
- K 线图像对照通过：深/浅主题、默认/自定义颜色、阳线/阴线/十字线；曲线裁剪保留原始数据，peak 下采样保留可见尖峰，finite 分段保持原点集。
- code-review 复查完成；Python 编译、UTF-8 无 BOM 及 `git diff --check` 通过。
- 验证为离屏合成数据及真实 Qt 图元/线程测试，未测实盘完整窗口 FPS、GPU 绘制或长时间内存曲线；指标首次计算仍使用既有完整公式。

复现（工作目录 `stock_standalone`，PowerShell）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/benchmark_trade_visualizer.py --compare-head --repeats 9 --output docs/TRADE_VISUALIZER_BENCHMARK_20261004.json
python -m pytest tests/test_trade_visualizer_performance.py tests/test_ipc_trade_rollover.py tests/test_ipc_cold_start_baseline.py tests/test_runtime_stability.py tests/test_signal_pipeline_hardening.py -k 'not test_sina_cold_start_does_not_fetch_on_non_trading_day' -q -o addopts='' --basetemp=.pytest_temp/trade_visualizer_performance --tb=short --no-header
```

测试通过 AST 装载真实实现并构造 Qt 图表，避免启动行情、语音与 IPC 服务；关联 IPC 测试也覆盖真实模块导入。
基准比较同一 Git HEAD 和修改后代码，每组 9 次取中位数；股票表按 code 排序，更新 5 行 close，排序键不变。

## 参考

- [Qt QGraphicsItem 几何及 exposedRect](https://doc.qt.io/qt-6/qgraphicsitem.html)
- [pyqtgraph 0.13.3 PlotDataItem 裁剪与降采样](https://pyqtgraph.readthedocs.io/en/pyqtgraph-0.13.3/api_reference/graphicsItems/plotdataitem.html)

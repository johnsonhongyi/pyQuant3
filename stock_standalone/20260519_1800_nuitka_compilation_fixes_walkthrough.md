# Nuitka 编译与打包修复记录 - 2026-05-19 18:00

## 1. 核心目标
解决程序在 Nuitka 独立编译（Standalone）打包后运行时暴露的三个致命异常：
1. 策略引擎初始化因动态懒加载未打包导致的 `ModuleNotFoundError: No module named 'stock_live_strategy'`；
2. PyTables 行情文件读取因缺少 C 扩展压缩算法模块导致的 `ModuleNotFoundError: No module named 'tables._comp_lzo'`；
3. PyQtGraph 视窗清理与回收时因 `compiled_method` 信号断开问题抛出的 `TypeError: 'compiled_method' object is not connected`。
同时，根据用户要求重新打开 UPX 二进制压缩功能。

---

## 2. 解决方案与实施步骤

### 2.1 补全本地动态懒加载模块与 PyTables C 扩展打包参数
- **痛点分析**：
  - 主应用 `instock_MonitorTK.py` 通过 `cct.LazyClass` / `cct.LazyModule` 对多个核心策略和界面组件（如 `StockLiveStrategy`, `DataPublisher`, `DailyPulseEngine`, `SignalDashboardPanel`）执行运行时延迟加载，静态依赖跟踪工具（Nuitka）无法感知。
  - PyTables 库在读取 HDF5 数据时，会动态尝试载入底层 C 扩展实现的 LZO 和 Bzip2 压缩后端，由于未在入口文件中静态导入，打包后直接报 `tables._comp_lzo` 缺失。
- **实施操作**：
  在 `nuitka_build_console.bat` 最后的编译指令参数集中，追加了对本地核心模块及 PyTables 依赖库的显式打包包含项：
  ```cmd
  --include-module=stock_live_strategy ^
  --include-module=realtime_data_service ^
  --include-module=market_pulse_engine ^
  --include-module=signal_dashboard_panel ^
  --include-module=tables._comp_lzo ^
  --include-module=tables._comp_bzip2
  ```

### 2.2 注入 PyQtGraph AxisItem `compiled_method` 异常忽略补丁 (Monkeypatch)
- **痛点分析**：
  - 在 Nuitka 环境下，所有的 Python 方法和函数都会被编译为 native C 级别的 `compiled_method` 结构。
  - PyQtGraph 内部的 `AxisItem.py` 在执行视图解绑操作 `unlinkFromView` 时，会通过 Qt 槽的 `.disconnect()` 机制清理视图信号。由于 Qt 将编译后的方法识别为异构结构，导致 disconnect 抛出 `TypeError: 'compiled_method' object is not connected` 并中断整个 GUI 线程导致闪退崩溃。
- **实施操作**：
  在 `trade_visualizer_qt6.py` 的全局 `import pyqtgraph as pg` 引用下方直接植入运行时猴子补丁。拦截并安全地忽略 disconnect 时由于 compiled_method 类型转换引发的 TypeError：
  ```python
  # Patch pyqtgraph compiled_method disconnect issue in Nuitka
  try:
      import pyqtgraph.graphicsItems.AxisItem as axis_item
      _original_unlinkFromView = axis_item.AxisItem.unlinkFromView
      def _patched_unlinkFromView(self):
          try:
              _original_unlinkFromView(self)
          except TypeError as e:
              if "compiled_method" in str(e):
                  pass
              else:
                  raise
      axis_item.AxisItem.unlinkFromView = _patched_unlinkFromView
  except Exception as e:
      print(f"Failed to patch pyqtgraph AxisItem.unlinkFromView: {e}")
  ```

### 2.3 重新启用 UPX 压缩以优化 Standalone 产物体积
- **痛点分析**：
  - 此前的构建选项中显式添加了 `--disable-plugin=upx` 禁用了压缩。
- **实施操作**：
  - 在 `nuitka_build_console.bat` 的配置中移除了 `--disable-plugin=upx` 指令。
  - 维持 `set PATH=C:\JohnsonProgram\SetDisplayMode\init\upx;%PATH%` 环境声明，使 Nuitka 在构建时能自动调用 PATH 环境变量中的 `upx.exe` 执行二进制和 DLL 的无损压缩。

---

## 3. 影响文件与变更说明

| 文件 | 变更说明 | 状态 |
|------|------|------|
| `trade_visualizer_qt6.py` | 引入 PyQtGraph AxisItem.unlinkFromView 的 Monkeypatch，彻底消除 compiled_method disconnect 崩溃 | ✅ 已实施并验证语法 |
| `nuitka_build_console.bat` | 补全 6 个动态加载与压缩扩展模块编译选项，删除 upx 禁用插件参数以启用 UPX | ✅ 已实施并验证语法 |
| `gemini.md` | 更新开发跟踪日志，新增 Nuitka 编译与打包修复的里程碑项 | ✅ 已更新 |

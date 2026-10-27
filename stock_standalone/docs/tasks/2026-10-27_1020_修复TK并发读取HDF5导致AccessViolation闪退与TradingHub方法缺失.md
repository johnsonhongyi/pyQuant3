# 任务记录：修复 TK 并发读取 HDF5 导致 Access Violation 闪退与 TradingHub 方法缺失

**任务时间**：2026-10-27 10:20  
**关联文件**：
- `stock_standalone/ats/fusion/relative_cache.py`
- `stock_standalone/stock_live_strategy.py`
- `stock_standalone/trading_hub.py`
- `stock_standalone/ats/ui/fusion_ladder_dialog.py`
- `stock_standalone/tests/test_fusion_adapter.py`
- `stock_standalone/tests/test_fusion_ladder_dialog_snapping.py`
- `stock_standalone/tests/test_fusion_full_chain_audit.py`

---

## 1. 现象与报错根因分析

### 现象 1：Windows fatal exception: access violation（TK 监控进程闪退）
```text
Windows fatal exception: access violation

Current thread 0x0000502c (most recent call first):
  File "tables\table.py", line 1843 in _read
  File "tables\table.py", line 1929 in read
  File "pandas\io\pytables.py", line 5276 in select
  ...
  File "ats\fusion\relative_cache.py", line 88 in load_rs5_map
  File "stock_live_strategy.py", line 2833 in _fusion_ensure_rs_map
  File "stock_live_strategy.py", line 2850 in _fusion_rs5
  File "stock_live_strategy.py", line 2958 in _fusion_enrich_snap
  File "stock_live_strategy.py", line 3681 in _detect_signals_single_stock
  File "concurrent\futures\thread.py", line 58 in run
```
**根因分析**：
- 在 2026/10/26 22:07 的 commit `fd289295` 引入了 relative 轴及 `relative_cache.py`；
- 在 `stock_live_strategy.py` 中，`_check_strategies` 会将多达 30~45 只监控股票分发到 `self.executor` 线程池并发执行 `_detect_signals_single_stock`；
- 每个子线程在单票计算时均会调用 `_fusion_enrich_snap` -> `_fusion_rs5` -> `_fusion_ensure_rs_map`；
- 缓存未就绪或过期瞬间，数十个子线程在同一毫秒并发调用 `load_rs5_map`；
- `relative_cache.py` 中直接使用裸 `pd.HDFStore(src, "r")` 打开同一物理 HDF5 文件，且无任何锁保护；
- Windows 下底层 HDF5 C 动态库非完全线程安全，多线程并发 `read`/`select` 导致内存野指针越界，触发 `0xC0000005` Access Violation，操作系统直接终止进程导致闪退。

### 现象 2：'TradingHub' object has no attribute 'get_open_trades'
```text
[10-27 09:55:21] DEBUG:stock_live_strategy.py(_check_strategies:2684): 📊 [PREP_ERROR] Data sync partially failed: 'TradingHub' object has no attribute 'get_open_trades'
```
**根因分析**：
- `stock_live_strategy.py` 第 2681 行直接调用 `hub.get_open_trades(resample=resample)`；
- 但 `TradingHub` 只有 `get_positions()`，没有 `get_open_trades()`，抛出 `AttributeError` 导致每轮策略准备阶段数据同步中断降级。

---

## 2. 核心整改措施

### 1. `ats/fusion/relative_cache.py` 线程安全与内存缓存加固
- **引入项目全局 HDF 线程锁**：对接 `JSONData.tdx_hdf5_api._HDF_GLOBAL_LOCK`，所有底层 HDF5 IO 严格互斥，杜绝并发竞争；
- **模块级 30 分钟内存缓存**：增加 `_CACHE_LOCK` 与 `_CACHED_RS5_MAP`，并发请求直接从内存中读取字典，零磁盘 IO 穿透；
- **采用 `SafeHDFStore` 替代裸 `pd.HDFStore`**：利用已有的文件锁与重试机制，异常时优雅降级并返回旧缓存，绝不抛出任何未捕获异常。

### 2. `stock_live_strategy.py` 并发预热与双重检查锁定 (DCL)
- **并发前主线程预热（零 IO 并发）**：在 `_check_strategies` 的准备阶段（单线程阶段），提前调用 `self._fusion_ensure_rs_map()`；分发到 30 个工作线程后仅查内存字典，耗时纳秒级，彻底消除子线程读磁盘；
- **双重检查锁定保障**：在 `StockLiveStrategy` 初始化添加 `self._fusion_rs_lock = threading.Lock()`，`_fusion_ensure_rs_map` 内置双重检查锁定，且加载失败时不置空已有数据，设置防抖窗口；
- **持仓数据弹性获取**：优先从 `self._open_trades_cache` / `self.trading_logger` 获取持仓，容错解析代码并标准化。

### 3. `trading_hub.py` 补充 `get_open_trades` 兼容接口
- 在 `TradingHub` 中实现 `get_open_trades`，打通 `TradingLogger.get_trades` 与自身的 `positions`，彻底消除 `AttributeError`。

---

## 3. 测试验证
1. `pytest tests/test_fusion_enrich.py`：11/11 PASS；
2. `pytest tests/test_fusion_adapter.py`：8/8 PASS；
3. `pytest tests/test_fusion_ladder_dialog_snapping.py`：14/14 PASS；
4. `pytest tests/test_fusion_full_chain_audit.py`：1/1 PASS；
5. `pytest tests/ -k fusion`：199 项融合测试 **全部 100% 纯绿通过（199 passed in 37.44s）**；
6. `python -m py_compile`：全量代码词法检查 0 错误。

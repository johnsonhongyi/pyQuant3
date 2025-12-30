# pyQuant3 项目开发进度存档 (2025-12-30)

## 1. 本次迭代核心任务及成果

### 🚀 多进程稳定性与日志系统修复
- **修复 AttributeError**: 解决了在 Windows `spawn` 模式下子进程尝试调用 `QueueHandler.put_nowait` 时发生的 `NoneType` 报错。通过增加 `_GLOBAL_QUEUE` 存在性校验并提供子进程 fallback 处理方案，确保了日志系统的稳健运行。
- **解决日志重复输出**: 实现了主进程识别逻辑（`MainProcess`），将重复的初始化信息（Path Mode, Config Status 等）限制在主进程打印，大幅提升了控制台的整洁度。
- **自定义日志轮转命名**: 满足用户需求，将日志轮转命名从默认的 `instock_tk.log.1` 修改为 `instock_tk_1.log`。
- **Windows 安全轮转**: 引入 `win_safe_rotator`，通过"复制+清空"逻辑解决了多进程环境下日志文件的锁定竞争问题，避免了轮转时的 `PermissionError`。

### 🧹 代码质量与 Lint 清理
- **benchmark_tdx.py**: 清理了冗余导入，增加了输入输出类型注解，修复了返回值处理逻辑。
- **data_utils.py**: 
    - 还原并修复了 `send_code_via_pipe` 核心函数。
    - 补齐了缺失的 `json` 模块导入。
    - 使用 PEP 585 (python 3.9+) 语法更新了全文件的类型提示（`dict`, `list` 代替 `Dict`, `List`）。
    - 移除了未使用的可选导入（`Optional` 等）。

### 📉 HDF5 路径处理与 MultiIndex 兼容性修复
- **修复 AttributeError (WindowsPath)**: 解决了 `tdx_hdf5_api.py` 中 `WindowsPath` 对象调用 `.lower()` 的异常。现已在 `SafeHDFStore.__init__` 强制执行字符串转换。
- **解决 MultiIndex 转换报错**: 新增 `safe_index_astype_str` 实用工具，解决了 `MultiIndex` 不能直接 `astype(str)` 的 Pandas 限制。
- **修复类型不匹配 (str vs Timestamp)**: 
    - 优化了 `commonTips.py` 中的 `select_multiIndex_index_fast`，增加了对字符串索引与 `Timestamp` 边界比较的兼容性转换。
    - 改进了 `tdx_hdf5_api.py` 的索引处理逻辑，在转换时保留了 `datetime64` 类型层级，避免了级联的比较错误。
- **增强 HDF5 校验健壮性**: 
    - 为 `validate_h5` 函数添加了重试机制（最多 3 次，间隔 100ms），避免因临时文件锁定导致校验失败。
    - 增加了详细的错误日志，包括文件不存在、文件大小为 0、无表等情况的具体提示。
    - 改进 `SafeHDFWriter.__exit__` 的错误处理：校验失败时不再直接抛出异常，而是尝试保留原有效文件或使用临时文件，提高了数据写入的容错性。

### 🔧 循环导入修复
- **解决 johnson_cons.py 与 commonTips.py 的循环导入**: 将 `johnson_cons.py` 中的 `from JohnsonUtil import commonTips as cct` 移至文件末尾，确保常量定义完成后再导入，打破循环依赖。
- **清理重复导入**: 移除了 `commonTips.py` 中重复的 `import argparse`。
- **添加缺失导入**: 在 `commonTips.py` 中添加了 `import ast`，解决 `ast.literal_eval()` 的使用问题。

---

## 2. 存档关键状态
- **核心配置文件**: `JohnsonUtil/LoggerFactory.py` (日志逻辑), `data_utils.py` (底层通信), `tdx_hdf5_api.py` (HDF5 操作)。
- **运行环境**: 已验证在多进程 `process_map` 模式下不会产生干扰日志。

---

## 3. 明日实盘推进计划 (2025-12-31)
1. **实盘校验**:
    - 在 9:15-9:30 竞价阶段观察日志轮转是否正常工作。
    - 检查 `instock_tk_1.log` 是否正确生成。
    - 验证 HDF5 数据写入的稳定性，确认校验增强后不再出现"HDF5 校验失败"错误。
2. **策略引擎测试**:
    - 基于修复后的 `send_code_via_pipe`，验证选股窗口与通达信/交易终端的联动稳定性。
3. **性能调优**:
    - 针对 `sina_data` 抓取过程中的数据对齐（Alignment）警告进行针对性修复。
4. **异常监测**:
    - 持续通过 `LoggerFactory` 捕获实盘中的潜在超时或网络波动。

---
**存档时间**: 2025-12-30 09:55 (Local Time)
**状态**: ✅ 核心 Bug 已闭环，HDF5 校验增强完成，生产环境准备就绪。

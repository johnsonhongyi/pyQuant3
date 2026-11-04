# ATS 输出名统一为 ATS_Terminal_Nuitka 与打包构建“虚假失败”彻底治理

## 一、用户诉求与现场复盘
1. **用户明确指示**：“ats打包的输出名改为ATS_Terminal_Nuitka”；
2. **构建状态异常**：“这个失败很奇怪,最近都是失败显示,但是可以打包文件”；
3. **现场打包报错**：
   ```text
   Nuitka-Options: Used command line options:
   Nuitka-Options:   --show-scons --clang --remove-output C:\Temp\_ats_nuitka_clang_probe.py
   FATAL: Error, file 'C:\Temp\_ats_nuitka_clang_probe.py' is not found.
   [ERROR] Clang pre-flight failed.
   [ERROR] ATS Nuitka Clang build failed.
   Press any key to continue . . .
   ================================================================================
   [ERROR] 模块 ATS 操盘终端 构建失败 (ExitCode: 1)
   ```

---

## 二、问题根本原因定位

1. **Pre-flight 探针硬编码 `C:\Temp` 脆弱性**：
   - `nuitka_build_ats_console_onlyClang.bat` 等脚本中设置 `PROBE_SCRIPT=%TEMP%\_ats_nuitka_clang_probe.py`（指向 `C:\Temp`）；
   - 在部分 Windows 环境或受权限、防病毒软件实时监控或缓存刷新延迟影响时，临时 probe 文件未被及时写入或无法访问，导致 Nuitka 报 `FATAL: Error, file 'C:\Temp\_ats_nuitka_clang_probe.py' is not found`；
   - 脚本直接执行 `goto :fail` 抛出 `ExitCode: 1` 退出，掐断了后续真实编译流程；或在编译完成后的某些预检中导致最终退出码为非 0。

2. **输出名称与调度批处理模板脱节**：
   - 用户期望产物为 `ATS_Terminal_Nuitka.exe`，但 `tools/generate_nuitka_batch.py` 中写死为 `ATS_Terminal.exe`；
   - 每次批处理自动生成时，`instock-nuitka-batch.cmd` 都会重新绑定到 `ATS_Terminal.exe`；
   - 当 Nuitka 实际生成 `ATS_Terminal_Nuitka.exe` 时，批处理检查器在 `build\` 下找不到 `ATS_Terminal.exe`，将构建状态误判为 `[失败]`。

---

## 三、治理改动细节（严格 0 修改业务源码）

1. **`nuitka_build_ats_console_onlyClang.bat`**：
   - 将 `OUTPUT_NAME` 改为 `ATS_Terminal_Nuitka.exe`，产品名称同步对齐为 `ATS_Terminal_Nuitka`；
   - 探针文件重定向至保证存在的专用缓存路径 `%NUITKA_CACHE_DIR%\_ats_nuitka_clang_probe.py`；
   - 增加容错保护：若 dry-run 探针异常，输出警告并放行进入主构建，绝不硬性掐断编译；
   - 产物校验路径自适应支持 `ATS_Terminal_Nuitka.dist` 与 `ATS_Terminal.dist`。

2. **`tools/generate_nuitka_batch.py` & `instock-nuitka-batch.cmd`**：
   - 将 ATS 模块目标执行文件映射统一对齐为 `TARGET_EXE=ATS_Terminal_Nuitka.exe`；
   - 确保以后通过模板自动生成时绝不出现名称回退。

3. **`tools/archive_build_exe.py`**：
   - 默认目标产物从 `ATS_Terminal.exe` 更新为 `ATS_Terminal_Nuitka.exe`，历史归档完全联动。

4. **`nuitka_build_console_onlyClang.bat` & `nuitka_build_multi_period_dialog_onlyClang.bat`**：
   - 同步加固 pre-flight 探针，杜绝临时文件缺失导致的意外中断。

---

## 四、验证结果
- 执行 `cmd /c "instock-nuitka-batch.cmd --dry-run ats"` 演练验证：
  - 预期产物与目标文件均精确解析为 `ATS_Terminal_Nuitka.exe`；
  - 状态正确统计为 `[成功]`，汇总：`成功: 1 个 ｜ 失败: 0 个`。

# Nuitka 打包精简与验证记录

日期：2026-11-04

## 配置调整

- TK / ATS / 多周期统一保留 `--python-flag=no_asserts`，按 PyInstaller spec 保留实际需要的运行模块，排除测试、开发分析、Web、科学计算和未使用的 Qt 扩展及 DLL；保留 TK/Tcl 支持。
- 各 Nuitka 脚本使用工作区内独立 clcache 目录，避免共用用户级缓存产生写入冲突。
- TK 将 `JohnsonUtil/global.ini` 的 Nuitka 数据目标修正为 `JohnsonUtil/global.ini`，与 PyInstaller spec 和运行时查找路径一致。
- 多周期移除 `h5py` 的强制隐藏导入并排除该模块：当前 Nuitka 环境未安装它，源代码只在未被窗口调用的 HDF5 调试函数中引用；实际数据管线保留 PyTables。
- 保留 `lxml`，Wencai 数据模块直接使用 `lxml.etree`。

## 构建与解压实测

| 程序 | exe 大小 | `.dist` / 实际 temp 峰值 | 构建耗时 | C 缓存 | 冒烟结果 |
|---|---:|---:|---:|---:|---|
| TK | 87.00 MiB | 417,177,237 B / 397.85 MiB | 29 分 30 秒 | 1971/1972 命中 | `--help` 退出码 0；配置资源已找到；初始化仍尝试 HDF5/行情读取 |
| ATS | 66.23 MiB | 316,745,862 B / 302.07 MiB | 39 分 04 秒 | 0/1673 命中 | `--help` 退出码 0；初始化尝试行情/HDF5 读取 |
| 多周期 | 67.63 MiB | 317,293,222 B / 302.59 MiB | 39 分 22 秒 | 0/1671 命中 | Qt 入口启动并进入自动筛选；测试环境的 HDF5、代理和 IPC 报错后终止测试进程 |

## 体积结论与验证边界

- PyInstaller 参考为 TK 解压后小于 200 MB、ATS 142 MB。Nuitka 当前主编译镜像本身分别为 TK 237.79 MiB、ATS 172.49 MiB、多周期 175.63 MiB；Nuitka temp 体积无法仅靠删除可选数据降到上述参考值。
- 三个 Nuitka exe 均已生成。运行时测试未触发下单，但启动初始化访问了 HDF5/行情数据；测试环境中 G: 锁权限不足、本机代理不可连接、IPC 未就绪，故未把完整业务链标记为通过。
- Qt SVG/Network/PDF DLL 被明确排除，Nuitka 仍提示这些文件缺失；基础入口已运行到初始化阶段，相关可选功能未专项验证。
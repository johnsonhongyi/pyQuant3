# 2026-11-05 20:50 【AI对话证据层chat_evidence.ini接入sys_utils打包环境自适应与自动释放持久化闭环】

## 1. 任务背景与问题分析
在最近实现的 `feat(desktop-chat)` 证据层中，虽然引入了 `chat_evidence.ini` 作为只读证据限额的配置文件，并在 `manage_window_layout.spec` 中打包进包内，但存在以下关键缺陷：
1. **未接入 `sys_utils` 打包环境自适应规范**：
   - 系统未在 `sys_utils.RESOURCE_MAP` 中登记 `chat_evidence.ini`；
   - 打包后外部物理目录下如果缺失该配置文件，系统仅能以只读方式回退读取包内解压临时目录（`_MEIPASS` / 临时目录），不会自动将文件释放到物理程序路径（`get_app_root()` 物理目录下），导致现场运维人员无法直观查看，且任何现场微调无法持久化落盘。
2. **Windows 内存盘（RamDisk）兼容性故障（WinError 1）**：
   - `desktop_chat_evidence.py` 与 `desktop_runtime.py` 裸调用 `Path.resolve()`，在临时目录或数据目录位于 Windows 内存盘（`G:\Temp` 等）时，由于底层不支持 `GetFinalPathNameByHandle`，会触发 `OSError: [WinError 1] 函数不正确`，导致 SQLite 数据库读取与配置解析报错。

## 2. 核心架构与实施改动

### 2.1 sys_utils 打包自适应与自动自愈释放闭环
- **`stock_standalone/sys_utils.py`**：
  - 在 `RESOURCE_MAP` 中显式登记 `"chat_evidence.ini"`（`src="stock-strategy/chat_evidence.ini"`, `dst="chat_evidence.ini"`）；
  - 增强 `get_base_path()`，准确识别 `hasattr(sys, "_MEIPASS")` 临时释放根目录；
  - `get_conf_path()` 优先命中物理程序目录下的已有配置；缺失时自动通过 `shutil.copy` 从包内资源流式复制自愈释放到程序物理根目录 `chat_evidence.ini`。

### 2.2 管理器与桌面桥双通道自动释放与加载
- **`stock_standalone/webTools/manage_window_layout.py`**：
  - 管理器入口在解析并锁定应用程序物理根目录（`_startup_app_root`）后，立即调用 `sys_utils.get_conf_path("chat_evidence.ini", base_dir=_startup_app_root)`，确保打包 EXE 启动瞬间物理磁盘即生成持久化配置。
- **`stock_standalone/stock-strategy/desktop_chat_evidence.py`**：
  - `EvidenceLimits._candidates` 接入 `sys_utils.get_conf_path("chat_evidence.ini")`，打包运行且外部无配置时自动触发底层自愈释放，并将释放归位后的物理文件作为 `"executable"` 加载，使现场修改即时生效并持久化；
  - 在无写盘权限等极端场景下，保留包内只读 `bundle` 和 `DEFAULTS` 兜底，绝不抛异常中断主流程。

### 2.3 Windows 内存盘（RamDisk）安全解析
- **`stock_standalone/stock-strategy/desktop_chat_evidence.py`** & **`desktop_runtime.py`**：
  - 封装 `_safe_resolve`，捕获 `OSError`（尤其是 `WinError 1`）并安全降级到 `Path.absolute()`，彻底修复 SQLite 数据库连接与配置定位报错。
- **`stock_standalone/manage_window_layout.spec`**：
  - 补齐 `("stock-strategy/chat_evidence.ini", "stock-strategy")` 包内多级映射。

## 3. 验证结果
- **Python 语法静态编译**：通过。
- **专项测试**：`python -m unittest test_desktop_chat_evidence.py`（61 项 100% 全部通过，新增自动释放持久化验证单测 `test_frozen_config_auto_releases_to_app_root_for_persistence`）。
- **运行时环境测试**：`python -m unittest test_desktop_runtime.py`（4 项 100% 全部通过）。
- **全量回归测试**：`python -m unittest discover -s . -p "test_*.py"`（全量 228 项测试 100% 全部通过，耗时 15.70s）。
- **pytest 快速验证**：`pytest -q test_desktop_chat_evidence.py`（61 passed）。

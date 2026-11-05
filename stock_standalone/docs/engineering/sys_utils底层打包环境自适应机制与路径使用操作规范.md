# sys_utils 底层打包环境自适应机制与路径使用操作规范

> **适用范围**：`stock_standalone`、`ats`、`trading_kernel`、`stock-strategy` 及所有量化实时监控子模块。  
> **核心目标**：彻底根治因 PyInstaller / Nuitka 打包导致的临时目录数据丢失、工作目录漂移及内存盘 WinError 1 故障，确保开发环境（Dev）与生产打包环境（EXE）行为 100% 一致。

---

## 一、 核心痛点与深层故障根因

### 1. 致命缺陷：裸 `__file__` 向上跳级导致数据销毁
- **现象**：在源码开发时，`os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 可以正常推导到工程根目录。
- **打包故障**：在 Nuitka Onefile / PyInstaller 打包环境下，`__file__` 指向操作系统自动分配的**临时只读解压目录**（如 `C:\Users\<User>\AppData\Local\Temp\onefile_xxxx\` 或 `_MEIPASS`）。
  - 若在这些目录下创建或写入日志（`logs/fusion_state`、`logs/session_ctx`）、状态快照（`hot_pool_{day}.json`）、数据库（`trading_signals.db`），**程序退出或重启后该临时目录会被操作系统自动物理清空**！
  - 导致：历史会话上下文无法跨日继承、实盘交易订单对账崩溃、本地配置重启还原为白板。

### 2. 运行时缺陷：`os.getcwd()` 工作目录漂移
- **现象**：随手使用 `os.path.join(os.getcwd(), "logs", ...)`。
- **打包故障**：当用户通过桌面快捷方式（未设置“起始位置”）、Windows 计划任务、开机自启或外部 Python 子进程拉起时，`os.getcwd()` 往往是 `C:\Windows\System32` 或当前调用的外部脚本目录，导致读取配置文件失败或在错误目录下疯狂创建垃圾文件夹。

### 3. 内存盘缺陷：`Path.resolve()` 抛出 `WinError 1`
- **现象**：使用 `pathlib.Path(p).resolve()` 解析绝对路径。
- **打包故障**：当行情或影子流放在高速内存盘（RamDisk 如 `G:\`、`R:\`）或 Subst 虚拟驱动器上时，Windows 驱动层不支持 `GetFinalPathNameByHandle` API，直接抛出致命异常：`OSError: [WinError 1] 函数不正确`。

---

## 二、 `sys_utils` 核心自适应 API 权威标准

系统在底层 [`sys_utils.py`](file:///d:/MacTools/WorkFile/WorkSpace/pyQuant3/stock_standalone/sys_utils.py) 中构建了一整套闭环的环境探测与路径自适应机制。所有业务模块**必须且只能**调用以下标准 API：

| 标准 API | 目标语义 | 打包环境行为 (Nuitka / PyInstaller) | 源码开发环境行为 (Dev) |
| :--- | :--- | :--- | :--- |
| **`get_app_root()`** | **物理可执行程序所在绝对根目录** | 返回外部物理 `.exe` 所在目录（排除临时解压目录） | 返回 `pyQuant3/stock_standalone` 根目录 |
| **`get_base_path()`** | **包内静态只读资源解压目录** | 返回临时解压释放目录（读取内置图标、默认模板） | 回退至 `get_app_root()` |
| **`get_conf_path(name)`** | **可读写配置文件专用路径** | 优先命中物理磁盘配置；若缺失自动从包内自愈释放 | 返回 `config/<name>` 路径 |
| **`safe_resolve_path(p)`** | **跨驱动器/RamDisk 安全解析** | 内部做兼容捕获，RamDisk/虚拟盘平滑降级为 `p.absolute()` | 同左，坚决杜绝抛出 WinError 1 |

> [!IMPORTANT]
> **多进程继承保证**：`get_app_root()` 首次探测成功后会自动固化至环境变量 `os.environ["INSTOCK_APP_ROOT"]`。所有由主进程启动的 multiprocessing 子进程、线程或独立 Worker，均能 100% 继承正确的物理根目录。

---

## 三、 代码重构规范（DOs and DON'Ts）

### 1. 根目录与基础路径解析

❌ **明确禁止 (DON'T)**：
```python
# 严禁：打包后落入临时目录，退出即被清理丢失！
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 严禁：工作目录不确定时引发灾难性寻址错误！
LOG_DIR = os.path.join(os.getcwd(), "logs", "fusion_shadow")
```

✅ **必须遵守 (DO)**：
```python
# 标准写法：优先从 sys_utils.get_app_root() 获取，保留轻量 fallback
try:
    from sys_utils import get_app_root
    PROJECT_ROOT = get_app_root()
except Exception:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR = os.path.join(PROJECT_ROOT, "logs", "fusion_shadow")
```

---

### 2. 配置文件读写 (`config/*.json`, `config/*.yaml`)

❌ **明确禁止 (DON'T)**：
```python
# 严禁：写死相对路径或 __file__
CONF = os.path.join(os.path.dirname(__file__), "..", "config", "alert_layout.json")
```

✅ **必须遵守 (DO)**：
```python
# 标准写法：统一走 get_conf_path，支持物理存在性检查与包内模板自愈
from sys_utils import get_conf_path

CONF = get_conf_path("alert_layout.json")
```

---

### 3. 只读资源（图标、音频、只读内置元数据）

❌ **明确禁止 (DON'T)**：
```python
# 严禁：在 Onefile 独立包下，物理磁盘根目录并不包含此未解压图标
icon = os.path.join(os.path.dirname(__file__), "MonitorTK32.ico")
```

✅ **必须遵守 (DO)**：
```python
# 标准写法：从 get_base_path() 读取解压出的资源，回退到 get_app_root()
from sys_utils import get_base_path, get_app_root

icon = os.path.join(get_base_path(), "MonitorTK32.ico")
if not os.path.exists(icon):
    icon = os.path.join(get_app_root(), "MonitorTK32.ico")
```

---

### 4. 数据文件与 SQLite 数据库搜索 (`JSONData/*.h5`, `*.db`)

❌ **明确禁止 (DON'T)**：
```python
# 严禁：写死相对路径探测
db_candidates = [
    "trading_signals.db",
    os.path.join(os.path.dirname(__file__), "..", "trading_signals.db")
]
```

✅ **必须遵守 (DO)**：
```python
# 标准写法：优先锁定物理应用程序根目录，兼容开发与部署
from sys_utils import get_app_root

app_root = get_app_root()
db_candidates = [
    os.path.join(app_root, "trading_signals.db"),
    os.path.join(app_root, "signal_strategy.db"),
    "trading_signals.db",  # 兼容特定本地目录测试
]
```

---

### 5. 内存盘路径与路径规范化

❌ **明确禁止 (DON'T)**：
```python
# 严禁：在 RamDisk (G:\, R:\) 上直接 resolve()
final_path = str(Path(path).resolve())
```

✅ **必须遵守 (DO)**：
```python
# 标准写法：使用 safe_resolve_path 杜绝 WinError 1
from sys_utils import safe_resolve_path

final_path = str(safe_resolve_path(path))
```

---

## 四、 自动化检查与防回归测试

为防止后续开发代码中再次混入非规范的路径写法，必须保持以下机制：

1. **专项路径回归单测**：
   - 每次提交前确保 `pytest tests/test_ats_packaged_path_adaptive.py` 100% 通过；
   - 该测试会自动模拟注入 `INSTOCK_APP_ROOT` 临时目录，验证各模块的路径收敛性。
2. **代码提交前静态排查**：
   - 定期或通过 pre-commit 检索 `ats/` 目录中的 `os.getcwd()` 及 `os.path.dirname(os.path.dirname(...__file__...))`；
   - 发现违规写法应立即按本手册重构为 `get_app_root()`。

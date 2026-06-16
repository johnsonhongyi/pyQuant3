# Gemini 任务跟进与计划

## 2026-06-16 10:40
- [x] **重构 findSetWindowPos 为独立功能包 (Refactor findSetWindowPos into an independent package)**：
    - [x] **创建包结构**：在 `webTools/window_manager` 下创建模块包，包括 `__init__.py`，`core.py`，`ui.py`，`config.json`。
    - [x] **设计 core.py**：将 `findSetWindowPos.py` 中底层的 Windows API 调用（如 EnumWindows、SetWindowPos、GetWindowRect 等）以及分辨率检测逻辑（基于 screeninfo 和 mouseMonitor.displayDetction）封装到 `core.py`。
    - [x] **配置文件分类持久化**：将原硬编码的所有窗口位置配置移动至独立的 `config.json` 中，并在 JSON 内部组织为 **`single_display` (单屏配置)**、**`multi_display` (多屏配置)** 和 **`custom_special` (特殊/历史配置)** 三个大类，在 `core.py` 中实现分类的安全加载、提取和保存机制。
    - [x] **设计 ui.py (PyQt6 分类配置管理器)**：设计一个符合现代暗黑美学的 PyQt6 界面，支持：
        - 查看当前系统的显示器配置和分辨率。
        - 级联/带前缀下拉展示分类后的窗口配置方案，清晰呈现不同显示器环境。
        - 列表展示当前配置中的所有窗口及其位置参数（X, Y, Width, Height），支持增、删、改。
        - 支持“新建配置”时指定所属类别（单屏/多屏/特殊）。
        - 支持“一键捕获”当前桌面上运行窗口的实际位置（方便快速保存配置）。
        - 支持“一键应用”当前配置到桌面窗口。
    - [x] **兼容性与无损开发**：依据用户指令，完全保持原 `webTools/findSetWindowPos.py` 文件不动，避免任何回归风险。在 `webTools/` 下提供了 `manage_window_layout.py`，默认支持后台不启动 UI 的自动分辨率探测与对齐，仅在加 `-ui` 或 `--ui` 参数时调起管理界面。


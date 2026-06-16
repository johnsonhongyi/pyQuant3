# Gemini 任务跟进与计划

## 2026-06-16 10:40
- [ ] **重构 findSetWindowPos 为独立功能包 (Refactor findSetWindowPos into an independent package)**：
    - [ ] **创建包结构**：在 `webTools/window_manager` 下创建模块包，包括 `__init__.py`，`core.py`，`ui.py`，`config.json`。
    - [ ] **设计 core.py**：将 `findSetWindowPos.py` 中底层的 Windows API 调用（如 EnumWindows、SetWindowPos、GetWindowRect 等）以及分辨率检测逻辑（基于 screeninfo 和 mouseMonitor.displayDetction）封装到 `core.py`。
    - [ ] **配置文件持久化**：将原来硬编码的各类 `tdx_ths_position1920`、`tdx_ths_positionDouble`、`tdx_ths_position3072` 等配置移动至 `config.json` 中，并在 `core.py` 中实现安全的加载与保存机制。
    - [ ] **设计 ui.py (PyQt6 配置管理器)**：设计一个符合现代暗黑美学的 PyQt6 界面，支持：
        - 查看当前系统的显示器配置和分辨率。
        - 下拉选择或自动匹配当前分辨率的窗口位置配置。
        - 列表展示当前配置中的所有窗口及其位置参数（X, Y, Width, Height），支持增、删、改。
        - 支持“一键捕获”当前桌面上运行窗口的实际位置（方便快速保存配置）。
        - 支持“一键应用”当前配置到桌面窗口。
    - [ ] **兼容性重定向**：在原 `webTools/findSetWindowPos.py` 中导入新包的函数并保持原有 API 兼容，确保不破坏其他现有依赖。

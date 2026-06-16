# Gemini 任务跟进与计划

## 2026-06-16 11:05
- [x] **实现多显示器物理排布与拓扑结构保存恢复功能 (Save & Restore Multi-Monitor Display Layout)**：
    - [x] **移植与抽取多屏幕拓扑 API**：将原有 `current_display_configuration.py` 的多屏幕分辨率、物理相对坐标、主屏标记获取与恢复逻辑（基于 Windows API `ChangeDisplaySettingsEx`）进行工程化重写并集成进 `window_manager/core.py`，对外透出 `save_display_configuration` 和 `restore_display_configuration` 接口。
    - [x] **支持跨多显示器组合持久化**：使用显示器组合特征签名（如 `3840x2160@2.0_1920x1080@1.25` 等）区分不同的物理显示器拓扑环境，独立保存其各自的布局配置文件，提供高度智能的自适应适配与持久化能力。
    - [x] **在配置管理器 UI 中深度集成**：在 UI 的“当前物理显示器拓扑结构”面板中新增 **`💾 保存显示器物理拓扑`** 与 **`🔄 恢复显示器物理拓扑`** 按钮，直观呈现执行状态并联动 UI 信息重新加载，带有气泡弹窗通知。
    - [x] **加固后台无 UI 模式**：在 `manage_window_layout.py` 无 UI 运行分支中，注入屏幕物理排布自动恢复流程，实现窗口对齐前自动令屏幕放置位置拓扑自愈。
    - [x] **无损且向后兼容**：完全不破坏任何原有 `current_display_configuration.py` 和 `findSetWindowPos.py` 的原生行为，保持原有调用链路的绝对安全。

## 2026-06-16 10:40
- [x] **重构 findSetWindowPos 为独立功能包 (Refactor findSetWindowPos into an independent package)**：
    - [x] **创建包结构**：在 `webTools/window_manager` 下创建模块包，包括 `__init__.py`，`core.py`，`ui.py`，`config.json`。
    - [x] **设计 core.py**：将 `findSetWindowPos.py` 中底层的 Windows API 调用（如 EnumWindows、SetWindowPos、GetWindowRect 等）以及分辨率检测逻辑（基于 screeninfo 和 mouseMonitor.displayDetction）封装到 `core.py`。
    - [x] **修复 UI 与 CLI 分辨率检测不一致缺陷**：针对 PyQt6 启动后激活 DPI 感知导致 win32api 物理坐标变化的问题，在 `core.py` 的探测逻辑中自动读取系统 DPI 缩放率并对主屏幕指标进行精确折合，确保了无 UI 命令行模式与 UI 界面下一致判定出当前系统匹配的最佳配置为 `tdx_ths_position4644`。
    - [x] **配置文件分类持久化**：将原硬编码的所有窗口位置配置移动至独立的 `config.json` 中，并在 JSON 内部组织为 **`single_display` (单屏配置)**、**`multi_display` (多屏配置)** 和 **`custom_special` (特殊/历史配置)** 三个大类，在 `core.py` 中实现分类的安全加载、提取和保存机制。
    - [x] **设计 ui.py (PyQt6 分类配置管理器)**：设计一个符合现代暗黑美学的 PyQt6 界面，支持：
        - 查看当前系统的显示器配置和分辨率。
        - 级联/带前缀下拉展示分类后的窗口配置方案，清晰呈现不同显示器环境。
        - 列表展示当前配置中的所有窗口及其位置参数（X, Y, Width, Height），支持增、删、改。
        - 支持“新建配置”时指定所属类别（单屏/多屏/特殊）。
        - 支持“一键捕获”当前桌面上运行窗口的实际位置（方便快速保存配置）。
        - 支持“一键更新已有窗口坐标”，直接从桌面捕捉当前配置表中已有程序窗口的最新位置覆盖回填（支持防最小化干扰与双向后缀容错）。
        - 表格采用 3 列布局，新增“当前桌面实际位置”对照列，实现实时比对染色（完全一致显绿色，位置发生偏移高亮显红色，未检测到程序显灰色）。
        - 支持“单项极速回填”：直接点击第三列中的红色偏移坐标单元格，即可瞬间回填覆盖第二列配置坐标，并自动比对变绿。
        - 支持“一键应用”当前配置到桌面窗口，并自动触发桌面实际位置重新检测，使移动成功的行瞬间由红转绿。对未运行的窗口静默跳过，不再输出繁杂的跳过日志。
    - [x] **兼容性与无损开发**：依据用户指令，完全保持原 `webTools/findSetWindowPos.py` 文件不动，避免任何回归风险。在 `webTools/` 下提供了 `manage_window_layout.py`，默认支持后台不启动 UI 的自动分辨率探测与对齐，仅在加 `-ui` 或 `--ui` 参数时调起管理界面。


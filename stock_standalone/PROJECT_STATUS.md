# PROJECT STATUS

> This file is the single source of truth for project progress.
> Every AI agent MUST update this file after completing a meaningful change.

---

## Completed Work
- [x] Initial project status created
- [x] Refined type hints in `sina_data.py` (Completed in previous session)
- [x] Added type hints to `read_ini`, `is_trade_date`, `get_day_istrade_date`, `getcwd` in `JohnsonUtil/commonTips.py`
- [x] Added type hints to `get_sys_system`, `isMac`, `get_sys_platform`, `get_ramdisk_dir`, `get_ramdisk_path` in `JohnsonUtil/commonTips.py`
- [x] Added type hints to `get_today`, `to_bool` in `JohnsonUtil/commonTips.py`
- [x] Applied comprehensive type hints to `stock_logic_utils.py`, modernizing to Python 3.9+ syntax (PEP 585)
- [x] Fixed type hint application errors for `write_to_blkdfcf` and `counterCategory` in `JohnsonUtil/commonTips.py`

---

## Current Focus
- Files: `instock_MonitorTK.py`
- Goal: 对 `instock_MonitorTK.py` 进行拆分重构，简化主文件结构。
- Tasks:
  - [ ] 提取顶级工具函数到独立模块
  - [ ] 将 `StockMonitorApp` 拆分为多个 Mixin 类（DPI, Window, Treeview, Data, Interaction 等）
  - [ ] 优化导入关系，减少冗余代码
- Constraints:
  - 保持现有功能不变 (Behavior Neutral)
  - 尽量减少对公共接口的改动
  - 确保模块化后的可读性与可维护性

---

## Known Risks / Notes
- `multi_replace_file_content` failed for `write_to_blkdfcf` and `counterCategory` due to content mismatch; requires careful re-targeting.
- Linter warnings in `stock_logic_utils.py` regarding `Any` usage and deprecated types have been largely addressed, but some `pd.Series` generic type errors persist due to pandas version limitations or stub issues.

---

## Next Step (ONLY ONE)
1. 创建 `tk_gui_modules` 目录并初步提取 DPI 和窗口管理相关的 Mixin。

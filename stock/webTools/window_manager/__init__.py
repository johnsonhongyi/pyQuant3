# -*- coding: utf-8 -*-
"""
窗口管理器包 (Window Manager Package)
提供股票监控系统及辅助窗口的位置/大小持久化管理与自动化布局分配功能。
"""

from .core import (
    ConfigManager,
    apply_layout_config,
    detect_display_config_name,
    set_window_pos_by_title,
    set_window_hwnd_pos,
    list_visible_windows,
    find_windows_by_title_safe,
    get_screen_resolution_summary,
    save_display_configuration,
    restore_display_configuration
)

from .ui import (
    WindowPosManagerUI,
    main as run_ui
)

__all__ = [
    'ConfigManager',
    'apply_layout_config',
    'detect_display_config_name',
    'set_window_pos_by_title',
    'set_window_hwnd_pos',
    'list_visible_windows',
    'find_windows_by_title_safe',
    'get_screen_resolution_summary',
    'save_display_configuration',
    'restore_display_configuration',
    'WindowPosManagerUI',
    'run_ui'
]

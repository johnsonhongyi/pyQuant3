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
    restore_display_configuration,
    list_display_configurations,
    delete_display_configuration,
    get_display_configuration_details,
    bring_window_to_top_by_title,
    check_and_add_route,
    get_wm_show_msg_id,
    check_and_activate_existing_instance,
    is_autostart_enabled,
    set_autostart_enabled,
    AcerPerformanceController,
    get_system_uptime,
    is_system_cold_boot,
    get_screen_topology_signature,
    get_screen_topology_orientation_tag
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
    'get_screen_topology_signature',
    'get_screen_topology_orientation_tag',
    'save_display_configuration',
    'restore_display_configuration',
    'list_display_configurations',
    'delete_display_configuration',
    'get_display_configuration_details',
    'bring_window_to_top_by_title',
    'check_and_add_route',
    'get_wm_show_msg_id',
    'check_and_activate_existing_instance',
    'is_autostart_enabled',
    'set_autostart_enabled',
    'AcerPerformanceController',
    'get_system_uptime',
    'is_system_cold_boot',
    'WindowPosManagerUI',
    'run_ui'
]



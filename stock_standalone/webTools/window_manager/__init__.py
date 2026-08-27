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
    get_screen_topology_orientation_tag,
    cancel_window_maximized_or_fullscreen,
    clean_duplicate_display_configurations,
    send_file_to_recycle_bin
)

from .sync_engine import (
    RamDiskSyncConfig,
    RamDiskSyncEngine,
    RamDiskSyncWorker,
    detect_default_ramdisk_dir,
    detect_default_backup_dir
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
    'cancel_window_maximized_or_fullscreen',
    'list_visible_windows',
    'find_windows_by_title_safe',
    'get_screen_resolution_summary',
    'get_screen_topology_signature',
    'get_screen_topology_orientation_tag',
    'save_display_configuration',
    'restore_display_configuration',
    'list_display_configurations',
    'delete_display_configuration',
    'clean_duplicate_display_configurations',
    'send_file_to_recycle_bin',
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
    'RamDiskSyncConfig',
    'RamDiskSyncEngine',
    'RamDiskSyncWorker',
    'detect_default_ramdisk_dir',
    'detect_default_backup_dir',
    'WindowPosManagerUI',
    'run_ui'
]



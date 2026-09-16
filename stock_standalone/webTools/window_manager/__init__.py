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
    send_file_to_recycle_bin,
    get_window_host_relation,
    get_window_family,
    apply_overall_window_group_by_title
)

from .sync_engine import (
    RamDiskSyncConfig,
    RamDiskSyncEngine,
    RamDiskSyncWorker,
    detect_default_ramdisk_dir,
    detect_default_backup_dir
)

from .antigravity_manager import (
    list_accounts as list_antigravity_accounts,
    get_current_account as get_current_antigravity_account,
    backup_current_account as backup_current_antigravity_account,
    switch_account as switch_antigravity_account,
    do_sync as sync_antigravity_ide,
    open_accounts_directory as open_antigravity_accounts_directory,
    AntigravitySyncWorker
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
    'get_window_host_relation',
    'get_window_family',
    'apply_overall_window_group_by_title',
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
    'list_antigravity_accounts',
    'get_current_antigravity_account',
    'backup_current_antigravity_account',
    'switch_antigravity_account',
    'sync_antigravity_ide',
    'open_antigravity_accounts_directory',
    'AntigravitySyncWorker',
    'WindowPosManagerUI',
    'run_ui'
]




# -*- coding: utf-8 -*-
"""
启动脚本：支持后台自动应用对齐、RamDisk数据自动同步或启动图形管理 UI
用法：
1. 默认双击或无参数运行：启动可视化配置管理界面 (UI)
   python manage_window_layout.py
2. 纯命令行探测并对齐：
   python manage_window_layout.py -cli
3. 托盘后台隐藏启动：
   python manage_window_layout.py -hide
4. 立即执行 RamDisk 备份：
   python manage_window_layout.py --sync-now
"""

import sys
import os
import ctypes

def get_app_root() -> str:
    """获取程序物理根目录。"""
    current_dir = os.path.dirname(os.path.abspath(__file__)) # webTools
    parent_dir = os.path.dirname(current_dir) # stock
    ws_root = os.path.dirname(parent_dir) # pyQuant3
    
    # 兼容将 stock_standalone/webTools 加入 sys.path
    standalone_wt = os.path.join(ws_root, "stock_standalone", "webTools")
    if os.path.exists(standalone_wt) and standalone_wt not in sys.path:
        sys.path.insert(0, standalone_wt)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    return parent_dir


def attach_to_parent_console() -> bool:
    """Windows 下自动附加父进程终端控制台"""
    try:
        ATTACH_PARENT_PROCESS = -1
        kernel32 = ctypes.windll.kernel32
        if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
            sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
            return True
    except Exception:
        pass
    return False


if __name__ == '__main__':
    import multiprocessing as mp
    mp.freeze_support()
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

    app_root = get_app_root()

    # 1. 前置解析命令行参数
    use_ui = True
    is_help = False
    debug_mode = False
    autostart_action = None
    sync_action = None
    hide_mode = False

    for i, arg in enumerate(sys.argv[1:], 1):
        arg_lower = arg.lower()
        if arg_lower in ['-h', '--help', '/?', '-help']:
            is_help = True
        elif arg_lower in ['--noui', '-noui', '--cli', '-cli', '--apply', '-apply', '-c']:
            use_ui = False
        elif arg_lower in ['-hide', '--hide', '-min', '--min', '-hidetray']:
            hide_mode = True
            use_ui = True
        elif arg_lower in ['--autostart-on', '-autostart-on']:
            autostart_action = 'on'
            use_ui = False
        elif arg_lower in ['--autostart-off', '-autostart-off']:
            autostart_action = 'off'
            use_ui = False
        elif arg_lower in ['--autostart-status', '-autostart-status']:
            autostart_action = 'status'
            use_ui = False
        elif arg_lower in ['--sync-now', '-sync-now', '--sync', '-sync']:
            sync_action = 'now'
            use_ui = False
        elif arg_lower in ['--sync-force', '-sync-force']:
            sync_action = 'force'
            use_ui = False
        elif arg_lower in ['--sync-daemon', '-sync-daemon']:
            sync_action = 'daemon'
            use_ui = False
        elif arg_lower in ['--sync-status', '-sync-status']:
            sync_action = 'status'
            use_ui = False
        elif arg_lower == '-log':
            debug_mode = True
            if i + 1 < len(sys.argv):
                os.environ["APP_DEBUG"] = sys.argv[i + 1]

    if not use_ui or is_help or debug_mode:
        attach_to_parent_console()

    if is_help:
        print("\n==== 桌面窗口坐标布局配置管理器 ====")
        print("用法: manage_window_layout.py [参数]")
        print("\n默认行为:")
        print("  不加任何参数双击运行时，启动完整的图形化操作界面 (UI)。")
        print("\n可选参数:")
        print("  -h, --help            显示此帮助信息并退出。")
        print("  -hide, --hide, -min   托盘后台模式。以不弹出主窗口的形式后台启动 UI 并在任务栏托盘常驻待命。")
        print("  -cli, -noui, -apply   纯命令行模式。不启动 UI 界面与托盘，直接在后台自动探测屏幕并应用窗口对齐。")
        print("  --autostart-on        开启 Windows 注册表开机自启（默认附带 -hide 不弹窗模式）。")
        print("  --autostart-off       关闭 Windows 注册表开机自启。")
        print("  --autostart-status    查询当前 Windows 注册表开机自启状态。")
        print("  --sync-now            立即执行一次 RamDisk 数据增量安全备份并退出。")
        print("  --sync-force          强制全量备份 RamDisk 数据（忽略指纹比对）并退出。")
        print("  --sync-daemon         以纯命令行控制台守护进程模式运行 RamDisk 自动同步。")
        print("  --sync-status         查询当前 RamDisk 自动同步配置与运行状态。")
        print("  -log <level>          开启调试模式并指定级别。\n")
        sys.exit(0)

    from window_manager import (
        run_ui, ConfigManager, apply_layout_config, detect_display_config_name, 
        check_and_add_route, check_and_activate_existing_instance,
        is_autostart_enabled, set_autostart_enabled,
        RamDiskSyncConfig, RamDiskSyncEngine, RamDiskSyncWorker
    )

    if autostart_action == 'on':
        success, msg = set_autostart_enabled(True)
        print(f"[AutoStart] {'[OK] ' if success else '[FAIL] '}{msg}")
        sys.exit(0 if success else 1)
    elif autostart_action == 'off':
        success, msg = set_autostart_enabled(False)
        print(f"[AutoStart] {'[OK] ' if success else '[FAIL] '}{msg}")
        sys.exit(0 if success else 1)
    elif autostart_action == 'status':
        enabled = is_autostart_enabled()
        print(f"[AutoStart] 注册表开机自启状态: {'[开启]' if enabled else '[关闭]'}")
        sys.exit(0)

    if sync_action in ['now', 'force']:
        import time
        sync_cfg = RamDiskSyncConfig()
        sync_eng = RamDiskSyncEngine(sync_cfg)
        print(f"\n[RamDisk Sync] 正在执行 {'强制全量' if sync_action == 'force' else '智能增量'} 同步备份...")
        print(f"  源目录: {sync_cfg.source_dir}")
        print(f"  备份目标: {sync_cfg.target_dir}")
        res = sync_eng.sync_once(force=(sync_action == 'force'), ignore_time_filter=True)
        print(f"  结果状态: {res.get('status')}")
        print(f"  详细消息: {res.get('message')}")
        if res.get('synced_files'):
            for sf in res['synced_files']:
                print(f"    -> 写入文件: {sf}")
        if res.get('failed_files'):
            for ff, err in res['failed_files']:
                print(f"    ❌ 失败: {ff} ({err})")
        print("[RamDisk Sync] 同步完成。\n")
        sys.exit(0 if res.get('status') in ['ok', 'skipped'] else 1)
    elif sync_action == 'status':
        sync_cfg = RamDiskSyncConfig()
        print("\n==== RamDisk 自动同步配置与状态 ====")
        print(f"  启用状态: {'[已启用]' if sync_cfg.enabled else '[已停用]'}")
        print(f"  巡检间隔: 每 {sync_cfg.sync_interval_sec} 秒")
        print(f"  源目录: {sync_cfg.source_dir}")
        print(f"  备份目录: {sync_cfg.target_dir}")
        print(f"  交易时段限制: {'是' if sync_cfg.only_trading_hours else '否'}")
        print(f"  交易时段: {sync_cfg.trading_hours}")
        print(f"  工作日限制: {'是' if sync_cfg.only_workdays else '否'}")
        print(f"  匹配通配符: {sync_cfg.file_patterns}")
        print(f"  备份模式: {sync_cfg.backup_mode}\n")
        sys.exit(0)
    elif sync_action == 'daemon':
        import time
        sync_cfg = RamDiskSyncConfig()
        sync_eng = RamDiskSyncEngine(sync_cfg)
        sync_worker = RamDiskSyncWorker(sync_eng)
        sync_worker.set_callbacks(
            on_status=lambda txt: print(f"[{time.strftime('%H:%M:%S')}] {txt}"),
            on_result=lambda r: print(f"[{time.strftime('%H:%M:%S')}] {r.get('message')}")
        )
        print(f"\n[RamDisk Daemon] 正在以控制台守护进程模式启动 (每 {sync_cfg.sync_interval_sec} 秒巡检)... 按 Ctrl+C 退出。\n")
        try:
            sync_worker.run()
        except KeyboardInterrupt:
            print("\n[RamDisk Daemon] 收到终止信号，正在退出...")
            sync_worker.stop()
        sys.exit(0)

    if use_ui:
        if check_and_activate_existing_instance():
            sys.exit(0)

        if hide_mode:
            print("正在以 [后台托盘隐藏不弹窗模式] 启动桌面窗口布局管理器 UI...")
        else:
            print("正在启动桌面窗口坐标布局配置管理器 UI...")
        config_mgr = ConfigManager()
        success, route_msg = check_and_add_route(config_mgr)
        print(f"[Route Check] {route_msg}")
        run_ui(hide_window=hide_mode)
    else:
        print("\n检测到 -cli 命令行参数，正在后台自动探测并应用窗口对齐...")
        from window_manager import restore_display_configuration
        restored, msg = restore_display_configuration()
        print(f"[Screen Layout] {msg}")
        config_mgr = ConfigManager()
        success, route_msg = check_and_add_route(config_mgr)
        print(f"[Route Check] {route_msg}")
        rec_name = detect_display_config_name(config_mgr)
        print(f"当前系统匹配的最佳配置方案为: {rec_name}")
        success = apply_layout_config(config_mgr, rec_name)
        if success:
            print("[OK] 窗口坐标布局自动对齐应用完成！\n")
        else:
            print(f"[Tips] 提示: 方案 '{rec_name}' 暂无任何窗口移动规则。\n")

# -*- coding: utf-8 -*-
"""
启动脚本：支持后台自动应用对齐或启动图形管理 UI
用法：
1. 默认静默对齐并退出 (兼容原有 BAT/后台自动调用)
   python manage_window_layout.py
2. 启动可视化配置管理界面
   python manage_window_layout.py --ui (或 -ui)
"""

import sys
import os

def get_app_root() -> str:
    """获取程序物理根目录。"""
    current_dir = os.path.dirname(os.path.abspath(__file__)) # webTools
    parent_dir = os.path.dirname(current_dir) # stock_standalone
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
        
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        try:
            os.chdir(env_root)
        except Exception:
            pass
        return env_root

    is_frozen = getattr(sys, "frozen", False)
    is_nuitka = "__compiled__" in globals() or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, "nuitka_version")
    if is_frozen or is_nuitka:
        calculated_root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 开发环境下，项目根目录是 webTools 的上级目录
        calculated_root = parent_dir

    # 强制将当前进程的工作目录切换为定位到的绝对物理根目录，防止通过右键快捷菜单或计划任务等启动时导致的 CWD 不对
    try:
        os.chdir(calculated_root)
    except Exception:
        pass

    return calculated_root


def attach_to_parent_console() -> bool:
    """
    针对 Windows 下无控制台 (noconsole / GUI 模式) 打包的 EXE，
    当用户通过 CMD / PowerShell 运行并带 -h 或 -cli 参数时，
    自动附加到调用者的控制台，确保 print 输出能在终端窗口中清晰可见。
    """
    try:
        ATTACH_PARENT_PROCESS = -1
        kernel32 = ctypes.windll.kernel32
        if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            # 重定向 sys.stdout / sys.stderr 到终端标准输出设备
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
        elif arg_lower == '-log':
            debug_mode = True
            if i + 1 < len(sys.argv):
                os.environ["APP_DEBUG"] = sys.argv[i + 1]

    # 2. 如果是命令行模式、帮助说明或调试模式，强制附加到父进程终端控制台以输出文字
    if not use_ui or is_help or debug_mode:
        attach_to_parent_console()

    # 3. 如果是请求 -h 帮助，输出帮助信息后立即退出
    if is_help:
        print("\n==== 桌面窗口坐标布局配置管理器 ====")
        print("用法: manage_window_layout.exe [参数]")
        print("\n默认行为:")
        print("  不加任何参数双击运行时，启动完整的图形化操作界面 (UI)。")
        print("\n可选参数:")
        print("  -h, --help            显示此帮助信息并退出。")
        print("  -hide, --hide, -min   托盘后台模式。以不弹出主窗口的形式后台启动 UI 并在任务栏托盘常驻待命（不自动应用布局）。")
        print("  -cli, -noui, -apply   纯命令行模式。不启动 UI 界面与托盘，直接在后台自动探测屏幕并应用窗口对齐。")
        print("  --autostart-on        开启 Windows 注册表开机自启（默认附带 -hide 不弹窗模式）。")
        print("  --autostart-off       关闭 Windows 注册表开机自启。")
        print("  --autostart-status    查询当前 Windows 注册表开机自启状态。")
        print("  -log <level>          开启调试模式并指定级别 (例如: -log debug)。\n")
        sys.exit(0)

    if debug_mode:
        print(f"[DEBUG] App root resolved to: {app_root}")
        print(f"[DEBUG] sys.path: {sys.path}")
        print(f"[DEBUG] Environment APP_DEBUG set to: {os.environ.get('APP_DEBUG')}")

    # 确保 webTools 目录在 sys.path 中，以便可以作为 package 导入 window_manager
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    from window_manager import (
        run_ui, ConfigManager, apply_layout_config, detect_display_config_name, 
        check_and_add_route, check_and_activate_existing_instance,
        is_autostart_enabled, set_autostart_enabled
    )

    # 4. 如果是处理开机自启命令行逻辑
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

    # 4. 关键隔离：只有在启动 UI 模式时才去检查单实例并唤醒已有 UI 视窗；
    # 纯命令行 CLI 模式 (-cli) 绝对不去唤醒/打开 UI 窗口！
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
        
        # 1. 尝试自适应恢复已存的多屏幕物理拓扑布局
        from window_manager import restore_display_configuration
        restored, msg = restore_display_configuration()
        print(f"[Screen Layout] {msg}")
        
        # 2. 实例化配置并探测推荐的分辨率方案名
        config_mgr = ConfigManager()
        success, route_msg = check_and_add_route(config_mgr)
        print(f"[Route Check] {route_msg}")
        rec_name = detect_display_config_name(config_mgr)
        print(f"当前系统匹配的最佳配置方案为: {rec_name}")
        
        # 3. 尝试应用窗口布局位置
        success = apply_layout_config(config_mgr, rec_name)
        if success:
            print("[OK] 窗口坐标布局自动对齐应用完成！\n")
        else:
            print(f"[Tips] 提示: 方案 '{rec_name}' 暂无任何窗口移动规则。")
            print("如需添加新窗口或录入屏幕，请直接双击运行本程序（或不在命令行加任何参数）。\n")

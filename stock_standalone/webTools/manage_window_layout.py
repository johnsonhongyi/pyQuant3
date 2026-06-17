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
    """获取程序物理根目录。独立于 sys_utils，避免加载无关依赖。"""
    env_root = os.environ.get("INSTOCK_APP_ROOT")
    if env_root and os.path.exists(env_root):
        return env_root

    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        calculated_root = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 开发环境下，项目根目录是 webTools 的上级目录
        calculated_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    os.environ["INSTOCK_APP_ROOT"] = calculated_root
    return calculated_root

app_root = get_app_root()

# 2. 确保 webTools 目录在 sys.path 中，以便可以作为 package 导入 window_manager
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from window_manager import run_ui, ConfigManager, apply_layout_config, detect_display_config_name

if __name__ == '__main__':
    # 默认启动 UI，可以通过 --cli / -cli / --noui / --apply 等参数取消 UI 直接在后台执行排版
    use_ui = True
    debug_mode = False
    
    for i, arg in enumerate(sys.argv):
        if arg.lower() in ['-h', '--help']:
            print("==== 桌面窗口坐标布局配置管理器 ====")
            print("用法: manage_window_layout.exe [参数]")
            print("\n默认行为:")
            print("  不加任何参数时，将启动完整的图形化操作界面 (UI)。")
            print("\n可选参数:")
            print("  -h, --help    显示此帮助信息并退出。")
            print("  -noui, -cli, -apply\n                静默模式。不启动 UI 界面，直接在后台自动探测屏幕并应用布局。")
            print("  -log <level>  开启调试模式并指定级别 (例如: -log debug)。")
            sys.exit(0)
        elif arg.lower() in ['--noui', '-noui', '--cli', '-cli', '--apply', '-apply']:
            use_ui = False
        elif arg.lower() == '-log':
            debug_mode = True
            if i + 1 < len(sys.argv):
                os.environ["APP_DEBUG"] = sys.argv[i + 1]
                
    if debug_mode:
        print(f"[DEBUG] App root resolved to: {app_root}")
        print(f"[DEBUG] sys.path: {sys.path}")
        print(f"[DEBUG] Environment APP_DEBUG set to: {os.environ.get('APP_DEBUG')}")

    if use_ui:
        print("正在启动桌面窗口坐标布局配置管理器 UI...")
        run_ui()
    else:
        print("检测到无 UI 参数，正在后台自动探测并应用窗口对齐...")
        
        # 1. 尝试自适应恢复已存的多屏幕物理拓扑布局
        from window_manager import restore_display_configuration
        restored, msg = restore_display_configuration()
        print(f"[Screen Layout] {msg}")
        
        # 2. 实例化配置并探测推荐的分辨率方案名
        config_mgr = ConfigManager()
        rec_name = detect_display_config_name()
        print(f"当前系统匹配的最佳配置方案为: {rec_name}")
        
        # 3. 尝试应用窗口布局位置
        success = apply_layout_config(config_mgr, rec_name)
        if success:
            print("[OK] 窗口坐标布局自动对齐应用完成！")
        else:
            print(f"[Tips] 提示: 方案 '{rec_name}' 暂无任何窗口移动规则。")
            print("如需添加新窗口或录入屏幕，请直接双击运行本程序（或不在命令行加任何参数）。")

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

# 确保父目录在 sys.path 中，以便可以作为 package 导入 window_manager
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from window_manager import run_ui, ConfigManager, apply_layout_config, detect_display_config_name

if __name__ == '__main__':
    # 检查命令行参数中是否包含 --ui 或 -ui
    use_ui = False
    for arg in sys.argv[1:]:
        if arg.lower() in ['--ui', '-ui']:
            use_ui = True
            break
            
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
            print("如需添加新窗口或录入屏幕，请运行: python manage_window_layout.py --ui")

# -*- coding: utf-8 -*-
"""
tests/test_startup_layout_and_tab_unified_sizes.py
验证 ATS 冷启动时无论默认处于资金主线(Tab 0)、重点关注(Tab 1)、大级别MA20d(Tab 2)还是新股次新股(Tab 3)，
布局绝对不变形、主分割比例严格统一锁定、左右面板绝不被挤压，且运行时连续切换 Tab 尺寸严格保持一致。
"""

import os
import json
import time
import pytest
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_top_tabs_startup_and_switch_unified_sizes(qapp):
    """验证 4 个 Tab 分别作为启动默认 Tab 时，布局均稳定一致且左右栏绝不被挤压"""
    from ats.ui.main_window import ATSMainWindow
    from sys_utils import get_app_root, get_conf_path
    
    cfg_path = get_conf_path("window_config.json", get_app_root())
    
    # 备份原始配置
    backup_data = None
    if os.path.exists(cfg_path):
        with open(cfg_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
            
    try:
        for tab_idx in [0, 1, 2, 3]:
            # 预设启动默认 Tab
            cur_data = dict(backup_data or {})
            cur_data["ats_top_tab_index"] = tab_idx
            cur_data["ats_main_splitter_sizes"] = [239, 1207, 222]
            if "ats_main_splitter_state" in cur_data:
                del cur_data["ats_main_splitter_state"]
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cur_data, f, indent=4)
                
            w = ATSMainWindow()
            w.showMaximized()
            for _ in range(20):
                qapp.processEvents()
            time.sleep(0.1)
            for _ in range(20):
                qapp.processEvents()
                
            sizes = w.main_splitter.sizes()
            # 必须满足左右面板拥有物理级最小宽度保护 (>= 180px)
            assert sizes[0] >= 180, f"Tab {tab_idx} 启动时左侧股票池被挤压: {sizes}"
            assert sizes[2] >= 180, f"Tab {tab_idx} 启动时右侧行业板块被挤压: {sizes}"
            assert sum(sizes) >= 600, f"Tab {tab_idx} 总尺寸异常: {sizes}"
            
            # 验证运行时连续切换所有 Tab，主分割尺寸完全统一不变形
            for target_tab in [0, 1, 2, 3]:
                w.top_tabs.setCurrentIndex(target_tab)
                for _ in range(10):
                    qapp.processEvents()
                switched_sizes = w.main_splitter.sizes()
                assert switched_sizes[0] >= 180, f"切换到 Tab {target_tab} 时左栏被挤压: {switched_sizes}"
                assert switched_sizes[2] >= 180, f"切换到 Tab {target_tab} 时右栏被挤压: {switched_sizes}"
                assert switched_sizes[0] == sizes[0], f"Tab {target_tab} 左栏尺寸变动: {switched_sizes[0]} != {sizes[0]}"
                assert switched_sizes[2] == sizes[2], f"Tab {target_tab} 右栏尺寸变动: {switched_sizes[2]} != {sizes[2]}"
                
            w.close()
            for _ in range(10):
                qapp.processEvents()
    finally:
        if backup_data is not None:
            # 恢复正常测试基准
            backup_data["ats_top_tab_index"] = 0
            backup_data["ats_main_splitter_sizes"] = [239, 1207, 222]
            if "ats_main_splitter_state" in backup_data:
                del backup_data["ats_main_splitter_state"]
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=4)

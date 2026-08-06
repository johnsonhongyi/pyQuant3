# -*- coding: utf-8 -*-
"""
单元测试：Acer 性能控制、CoolBoost 风扇模式与启动自动应用功能
"""

import sys
import os
import pytest

# 将项目根目录和 webTools 加入 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
webtools_dir = os.path.join(parent_dir, "webTools")
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

from window_manager.core import AcerPerformanceController, ConfigManager

def test_acer_controller_support():
    """测试 Acer 性能控制器底层硬件支持度检测与安全兜底"""
    controller = AcerPerformanceController()
    is_sup = controller.is_supported()
    status = controller.get_current_status()
    print(f"[TEST] Acer Hardware WMI Supported: {is_sup}")
    print(f"[TEST] Current Status: {status}")
    assert isinstance(is_sup, bool)
    assert isinstance(status, dict)
    assert "supported" in status
    assert "coolboost" in status
    assert "overclock_mode" in status
    assert "fan_mode" in status

def test_acer_config_persistence():
    """测试 ConfigManager 对 acer_performance 配置段的读写与默认自愈功能"""
    import tempfile
    temp_dir = tempfile.gettempdir()
    cfg_file = os.path.join(temp_dir, "test_window_config_acer.json")
    if os.path.exists(cfg_file):
        try:
            os.remove(cfg_file)
        except Exception:
            pass

    cm = ConfigManager(config_path=cfg_file)
    
    # 默认值读取
    cfg = cm.get_acer_performance_config()
    assert isinstance(cfg, dict)
    assert cfg.get("overclock_mode") in ["Default", "Fast", "Extreme", "Normal"]
    assert isinstance(cfg.get("coolboost"), bool)
    assert isinstance(cfg.get("auto_apply_on_startup"), bool)
    
    # 修改并保存
    new_cfg = {
        "overclock_mode": "Fast",
        "coolboost": True,
        "fan_mode": "Auto",
        "auto_apply_on_startup": True
    }
    saved = cm.save_acer_performance_config(new_cfg)
    assert saved is True
    
    # 重新加载验证物理落盘
    cm_new = ConfigManager(config_path=cfg_file)
    loaded_cfg = cm_new.get_acer_performance_config()
    assert loaded_cfg["overclock_mode"] == "Fast"
    assert loaded_cfg["coolboost"] is True
    assert loaded_cfg["auto_apply_on_startup"] is True

    # 清理临时文件
    if os.path.exists(cfg_file):
        try:
            os.remove(cfg_file)
        except Exception:
            pass

def test_acer_apply_profile():
    """测试批量应用 Acer 性能 Profile 接口"""
    controller = AcerPerformanceController()
    profile = {
        "overclock_mode": "Extreme",
        "coolboost": True,
        "fan_mode": "Max"
    }
    success, msg = controller.apply_performance_profile(profile)
    print(f"[TEST] Apply Profile Result: success={success}, msg={msg}")
    # 无论硬件是否存在，接口均必须安全返回 (bool, str) 元组，不引发 Exception 崩溃
    assert isinstance(success, bool)
    assert isinstance(msg, str)

if __name__ == "__main__":
    test_acer_controller_support()
    test_acer_config_persistence()
    test_acer_apply_profile()
    print("ALL ACER PERFORMANCE CONTROLLER TESTS PASSED!")

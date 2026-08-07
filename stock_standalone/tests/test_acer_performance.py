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

from window_manager.core import (
    AcerPerformanceController, ConfigManager, get_system_uptime, is_system_cold_boot
)

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

def test_system_uptime_and_cold_boot(monkeypatch=None):
    """测试系统 Uptime 计算与开机冷启动 (System Cold Boot) 判定引擎"""
    uptime = get_system_uptime()
    is_cold = is_system_cold_boot(300)
    print(f"[TEST] Real System Uptime: {uptime:.2f} s, Is Cold Boot (<300s): {is_cold}")
    assert isinstance(uptime, float)
    assert uptime >= 0.0
    assert isinstance(is_cold, bool)

    # 通过猴子补丁/直接逻辑校验阈值判定
    from window_manager import core
    orig_fn = core.get_system_uptime
    try:
        core.get_system_uptime = lambda: 15.0
        assert is_system_cold_boot(300) is True

        core.get_system_uptime = lambda: 1000.0
        assert is_system_cold_boot(300) is False
    finally:
        core.get_system_uptime = orig_fn

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
    """测试批量应用 Acer 性能 Profile 接口及每步状态更新的准确性"""
    controller = AcerPerformanceController()
    
    # 1. Step 0: 首先获取 3 个状态的初始/默认设置明细
    init_status = controller.get_current_status()
    print(f"[TEST Step 0] 初始系统探查明细 -> 超频(overclock_mode)={init_status.get('overclock_mode')}, 风扇(fan_mode)={init_status.get('fan_mode')}, CoolBoost(coolboost)={init_status.get('coolboost')}")

    # 2. Step 1: 设置极速模式 [超频=Extreme, 风扇=Max, CoolBoost=True]
    p1 = {
        "overclock_mode": "Extreme",
        "coolboost": True,
        "fan_mode": "Max"
    }
    s1, msg1 = controller.apply_performance_profile(p1, log_cb=print)
    print(f"[TEST Step 1 Result] success={s1}, msg={msg1}")
    assert s1 is True
    
    st1 = controller.get_current_status()
    print(f"[TEST Step 1 Status] 设置后状态明细 -> 超频(overclock_mode)={st1.get('overclock_mode')}, 风扇(fan_mode)={st1.get('fan_mode')}, CoolBoost(coolboost)={st1.get('coolboost')}")
    if controller.is_supported():
        assert st1["coolboost"] is True
        assert st1["overclock_mode"] == "Extreme"
        assert st1["fan_mode"] == "Max"

    # 3. Step 2: 切换为 Fast 模式 [超频=Fast, 风扇=Auto, CoolBoost=True]
    p2 = {
        "overclock_mode": "Fast",
        "coolboost": True,
        "fan_mode": "Auto"
    }
    s2, msg2 = controller.apply_performance_profile(p2, log_cb=print)
    print(f"[TEST Step 2 Result] success={s2}, msg={msg2}")
    assert s2 is True

    st2 = controller.get_current_status()
    print(f"[TEST Step 2 Status] 设置后状态明细 -> 超频(overclock_mode)={st2.get('overclock_mode')}, 风扇(fan_mode)={st2.get('fan_mode')}, CoolBoost(coolboost)={st2.get('coolboost')}")
    if controller.is_supported():
        assert st2["coolboost"] is True
        assert st2["overclock_mode"] == "Fast"
        assert st2["fan_mode"] == "Auto"

    # 4. Step 3: 再次应用相同 Fast 模式 (验证状态已完全一致，优雅跳过 UI 模拟点击)
    s3, msg3 = controller.apply_performance_profile(p2, log_cb=print)
    print(f"[TEST Step 3 Repeat Result] success={s3}, msg={msg3}")
    assert s3 is True
    assert "无需重复" in msg3 or "生效状态" in msg3

if __name__ == "__main__":
    test_acer_controller_support()
    test_system_uptime_and_cold_boot()
    test_acer_config_persistence()
    test_acer_apply_profile()
    print("ALL ACER PERFORMANCE CONTROLLER TESTS PASSED!")


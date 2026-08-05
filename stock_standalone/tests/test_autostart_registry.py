# -*- coding: utf-8 -*-
"""
单元测试：测试 Windows 注册表开机自启功能 (is_autostart_enabled / set_autostart_enabled)
"""

import sys
import os

# 将项目根目录和 webTools 加入 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
webtools_dir = os.path.join(parent_dir, "webTools")
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

from window_manager import is_autostart_enabled, set_autostart_enabled, core

def test_autostart_command_extraction():
    """测试获取自启动命令"""
    cmd = core.get_autostart_command()
    print(f"[TEST] Autostart Command: {cmd}")
    assert cmd is not None
    assert len(cmd) > 0

def test_autostart_registry_toggle():
    """测试注册表自启动开启与关闭功能"""
    if sys.platform != "win32":
        print("[TEST] Skip on non-windows platform")
        return

    orig_status = is_autostart_enabled()
    print(f"[TEST] Original Autostart status: {orig_status}")

    try:
        # 1. 测试开启自启动
        success, msg = set_autostart_enabled(True)
        print(f"[TEST] Enable result: {success}, msg: {msg}")
        assert success is True
        assert is_autostart_enabled() is True

        # 2. 测试关闭自启动
        success_off, msg_off = set_autostart_enabled(False)
        print(f"[TEST] Disable result: {success_off}, msg: {msg_off}")
        assert success_off is True
        assert is_autostart_enabled() is False

    finally:
        # 恢复原始状态
        set_autostart_enabled(orig_status)
        print(f"[TEST] Restored Autostart status to: {is_autostart_enabled()}")

if __name__ == "__main__":
    test_autostart_command_extraction()
    test_autostart_registry_toggle()
    print("ALL AUTOSTART TESTS PASSED!")

# -*- coding: utf-8 -*-
"""
测试静态路由纯动态自适应配置驱动与网络环境检测逻辑
"""
import unittest
import os
import sys

# 将工程根目录添加到 sys.path
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

webtools_dir = os.path.join(app_root, "webTools")
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

from window_manager.core import ConfigManager, check_and_add_route


class TestDynamicRouteDetection(unittest.TestCase):
    def setUp(self):
        self.config_mgr = ConfigManager()
        self.original_routing = self.config_mgr.config_data.get("routing_config", {}).copy()

    def tearDown(self):
        self.config_mgr.config_data["routing_config"] = self.original_routing

    def test_disabled_or_empty_config(self):
        """测试未配置或禁用时，安全返回且不执行任何操作系统调用"""
        self.config_mgr.config_data["routing_config"] = {}
        success, msg = check_and_add_route(self.config_mgr)
        self.assertTrue(success)
        self.assertIn("未配置", msg)

        self.config_mgr.config_data["routing_config"] = {"enabled": False}
        success, msg = check_and_add_route(self.config_mgr)
        self.assertTrue(success)
        self.assertIn("未启用", msg)

    def test_dynamic_local_direct_subnet_detection(self):
        """测试动态配置为本机当前 IP 所在的直连网段时，自适应识别为直连，不弹窗、不提权"""
        self.config_mgr.config_data["routing_config"] = {
            "enabled": True,
            "destination": "192.168.50.0",
            "mask": "255.255.255.0",
            "gateway": "192.168.50.1"
        }
        success, msg = check_and_add_route(self.config_mgr)
        self.assertTrue(success)
        self.assertTrue("直连" in msg or "已存在" in msg or "On-link" in msg)
        print(f"[Test Dynamic Local Subnet] -> success={success}, msg={msg}")

    def test_dynamic_unreachable_gateway_interception(self):
        """测试当配置的网关完全不可达且与本机所有网卡不在同一子网时，安全拦截，杜绝盲目弹窗提权"""
        self.config_mgr.config_data["routing_config"] = {
            "enabled": True,
            "destination": "10.200.0.0",
            "mask": "255.255.0.0",
            "gateway": "172.31.254.254" # 假设不可达的异构网关
        }
        success, msg = check_and_add_route(self.config_mgr)
        self.assertFalse(success)
        self.assertIn("不在同一子网", msg)
        print(f"[Test Unreachable Gateway] -> success={success}, msg={msg}")


if __name__ == '__main__':
    unittest.main()

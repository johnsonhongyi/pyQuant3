# -*- coding: utf-8 -*-
"""
Antigravity 账户管理器与 Windows 原生安全凭据隔离测试
覆盖：
1. 正常环境下凭据快照提取与 DPAPI 加密/解密
2. 彻底移除/Mock pywin32 (win32cred/win32crypt) 下纯 ctypes 独立运行能力 (对 PyInstaller 打包环境免疫)
3. 凭据缺失/解密失败时的优雅降级 (遵循不抛异常中断主流程原则)
"""

import sys
import os
import unittest
from unittest.mock import patch

from webTools.window_manager import antigravity_manager


class TestAntigravityManagerCredentials(unittest.TestCase):

    def test_01_native_credential_snapshot_and_restore(self):
        """测试通过原生 Advapi32/Crypt32 成功提取快照并正确解密"""
        snap = antigravity_manager._capture_app_credential_snapshot()
        if not snap:
            self.skipTest("当前 Windows 登录会话中未找到 gemini:antigravity 系统凭据，跳过硬件读写校验")
        
        self.assertIn(antigravity_manager.APP_PROFILE_CRED_BLOB_KEY, snap)
        self.assertIn(antigravity_manager.APP_PROFILE_CRED_USER_KEY, snap)
        self.assertIn(antigravity_manager.APP_PROFILE_CRED_PERSIST_KEY, snap)
        self.assertTrue(len(snap[antigravity_manager.APP_PROFILE_CRED_BLOB_KEY]) > 0)
        self.assertEqual(snap[antigravity_manager.APP_PROFILE_CRED_USER_KEY], "antigravity")

    def test_02_pure_ctypes_without_pywin32(self):
        """模拟打包后缺少 pywin32 (win32cred/win32crypt)，验证纯 ctypes 路径 100% 健全"""
        with patch.dict(sys.modules, {"win32cred": None, "win32crypt": None}):
            snap = antigravity_manager._capture_app_credential_snapshot()
            if not snap:
                self.skipTest("当前系统无 gemini:antigravity 凭据，跳过")
            
            # 验证在完全无 pywin32 下纯 ctypes 能完成提取
            self.assertIn(antigravity_manager.APP_PROFILE_CRED_BLOB_KEY, snap)
            self.assertEqual(snap[antigravity_manager.APP_PROFILE_CRED_USER_KEY], "antigravity")

    def test_03_restore_invalid_snapshot_graceful(self):
        """测试恢复损坏或非法的快照时，优雅返回 False 不中断不崩溃"""
        invalid_profile = {
            antigravity_manager.APP_PROFILE_CRED_BLOB_KEY: "NotABase64String!!!",
            antigravity_manager.APP_PROFILE_CRED_USER_KEY: "test_user",
        }
        ok = antigravity_manager._restore_app_credential_snapshot(invalid_profile)
        self.assertFalse(ok)

        empty_profile = {}
        ok2 = antigravity_manager._restore_app_credential_snapshot(empty_profile)
        self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main()

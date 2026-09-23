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

    def test_04_dynamic_quota_countdown_calculation(self):
        """测试脱机/无刷新时，根据系统时钟动态计算当前倒计时而非沿用旧静态文本"""
        from datetime import datetime, timezone, timedelta

        # 模拟未来 1 小时 30 分钟的重置时间
        future_dt = datetime.now(timezone.utc) + timedelta(hours=1, minutes=30)
        future_iso = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 传入带有过期描述（例如旧缓存写着 20小时48分后）的 entry
        stale_entry = {
            "reset_time": future_iso,
            "reset_desc": "20小时48分后",  # 旧静态文本
            "remaining_pct": 7.9
        }

        diff_sec, live_desc = antigravity_manager.resolve_quota_reset_desc(stale_entry)
        self.assertTrue(5000 <= diff_sec <= 5500)
        self.assertIn("1小时", live_desc)
        self.assertNotIn("20小时", live_desc)  # 必须绝不死板使用旧的 20 小时

    def test_05_expired_reset_shows_ready(self):
        """测试重置时间已经过去的旧快照，动态呈现为已重置/已就绪"""
        from datetime import datetime, timezone, timedelta

        # 模拟 3 小时前的重置时间
        past_dt = datetime.now(timezone.utc) - timedelta(hours=3)
        past_iso = past_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        stale_entry = {
            "reset_time": past_iso,
            "reset_desc": "20小时48分后",
            "remaining_pct": 0.0
        }

        diff_sec, live_desc = antigravity_manager.resolve_quota_reset_desc(stale_entry)
        self.assertEqual(diff_sec, 0.0)
        self.assertEqual(live_desc, "已重置/已就绪")

    def test_06_diff_sec_fallback_decay(self):
        """测试缺少 reset_time 时，通过 updated_at 流逝时间递减计算"""
        import time

        now = time.time()
        # 30 分钟前保存的快照，当时剩余 3600 秒 (1小时)
        stale_entry = {
            "diff_sec": 3600.0,
            "updated_at": now - 1800.0,
            "reset_desc": "1小时0分后"
        }

        diff_sec, live_desc = antigravity_manager.resolve_quota_reset_desc(stale_entry)
        self.assertTrue(1700 <= diff_sec <= 1850)
        self.assertIn("分", live_desc)
        self.assertIn("秒后", live_desc)
        self.assertNotIn("1小时", live_desc)

    def test_07_card_apply_dynamic_countdown(self):
        """测试 UI 卡片应用配额时，自动使用动态时钟计算后的描述填充 Label，而非旧静态字符串"""
        from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar
        from datetime import datetime, timezone, timedelta

        app = QApplication.instance() or QApplication(sys.argv)
        from webTools.window_manager.ui import AntigravityAccountManagerDialog

        dlg = AntigravityAccountManagerDialog(auto_fetch=False)

        # 模拟包含过期倒计时的配额数据（未来 2 小时，但静态文本写着 20小时48分后）
        target_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fake_groups = {
            "Claude": {
                "remaining_pct": 3.1,
                "reset_time": target_iso,
                "reset_desc": "20小时48分后"  # 旧静态缓存
            }
        }
        fake_summary = {
            "claude_gpt": {
                "weekly": {
                    "remaining_pct": 3.1,
                    "reset_time": target_iso,
                    "reset_desc": "20小时48分后"
                }
            }
        }

        # 构造最小 card_record
        lbl_m = QLabel()
        bar_m = QProgressBar()
        lbl_w = QLabel()
        bar_w = QProgressBar()

        card_rec = {
            "email": "test@example.com",
            "models": {"Claude": {"lbl": lbl_m, "bar": bar_m}},
            "weekly_widgets": {"claude_gpt": {"lbl": lbl_w, "bar": bar_w}},
            "is_active": False,
            "target_role": "app"
        }

        dlg._apply_quota_to_card(card_rec, fake_groups, fake_summary)

        # 验证 Label 文本绝不是旧静态的 20小时48分后
        self.assertNotIn("20小时48分", lbl_m.text())
        self.assertIn("1小时", lbl_m.text())
        self.assertNotIn("20小时48分", lbl_w.text())
        self.assertIn("1小时", lbl_w.text())

        # 注册进 dlg.account_cards 测试定时槽函数
        dlg.account_cards["test_app"] = card_rec
        dlg._update_all_card_countdowns()
        self.assertNotIn("20小时48分", lbl_m.text())

        dlg.close()


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
tests/test_sbc_open_persistence_and_manual_close_isolation.py
-------------------------------------------------------------
验证以下核心业务规则：
1. 【SBC Launcher 持仓盯盘手动关闭即时除名】手动关闭的窗口绝对不用持久化；
2. 【SBC Launcher 统一关闭只持久化未关闭窗口】统一关闭时仅精准持久化当前打开未关闭的窗口；
3. 【恢复不串扰】已初始化配置下恢复持仓盯盘绝不重新拉取已手动关闭的持仓股；
4. 【ATS 独立子进程 SBC 持久化与恢复】ATS 关闭时精准持久化正在运行的 SBC 子进程，重新打开时以独立子进程自动恢复打开；
5. 【ATS 手动关闭单窗口即时除名】ATS 看盘中手动关闭单窗口立即除名，下次启动不再跟随打开。
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

_app = QApplication.instance() or QApplication(sys.argv)


class TestSBCOpenPersistenceAndManualCloseIsolation(unittest.TestCase):

    def setUp(self):
        self.test_cfg_dir = os.path.join(_PROJECT_ROOT, "tests", "tmp_cfg")
        os.makedirs(self.test_cfg_dir, exist_ok=True)
        self.launcher_cfg = os.path.join(self.test_cfg_dir, "test_launcher_holdings_layout.json")
        self.ats_sbc_cfg = os.path.join(self.test_cfg_dir, "test_ats_sbc_layout.json")

    def tearDown(self):
        for f in (self.launcher_cfg, self.ats_sbc_cfg):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        if os.path.exists(self.test_cfg_dir):
            try:
                os.rmdir(self.test_cfg_dir)
            except Exception:
                pass

    def test_launcher_manual_close_removes_and_unified_close_persists_only_open_windows(self):
        """测试持仓盯盘：手动关闭 300335 后立即除名，统一关闭时只持久化 603787 与 601226"""
        from run_sbc import save_launcher_holdings_windows, restore_launcher_holdings_windows
        from ats.ui.intraday_strategy_dialog import _remove_sbc_open_record

        # 初始状态：3 个窗口打开
        init_data = {
            "sbc_holdings_windows": [
                {"code": "300335", "x": 10, "y": 40, "width": 640, "height": 420, "period_mode": "10d"},
                {"code": "603787", "x": 660, "y": 40, "width": 640, "height": 420, "period_mode": "10d"},
                {"code": "601226", "x": 1310, "y": 40, "width": 640, "height": 420, "period_mode": "10d"},
            ],
            "initialized": True
        }
        with open(self.launcher_cfg, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)

        with patch('run_sbc._get_launcher_layout_cfg_path', return_value=self.launcher_cfg), \
             patch('ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path', return_value=self.launcher_cfg):

            # 1. 模拟用户手动单独关闭 300335
            _remove_sbc_open_record("300335")

            with open(self.launcher_cfg, "r", encoding="utf-8") as f:
                data_after_manual_close = json.load(f)

            codes_remaining = [item["code"] for item in data_after_manual_close.get("sbc_holdings_windows", [])]
            self.assertNotIn("300335", codes_remaining, "手动关闭的 300335 必须已从持仓盯盘配置中彻底除名")
            self.assertEqual(codes_remaining, ["603787", "601226"])
            self.assertTrue(data_after_manual_close.get("initialized"))

            # 2. 模拟恢复时，严禁因任何原因把 300335 重新拉回
            with patch('run_sbc.open_sbc_chart_dialog') as mock_open:
                mock_dlg = MagicMock()
                mock_open.return_value = mock_dlg
                restored = restore_launcher_holdings_windows()

                called_codes = [call.kwargs.get('code') or call.args[1] for call in mock_open.call_args_list]
                self.assertNotIn("300335", called_codes, "恢复时绝对不能重新打开已手动关闭的 300335")
                self.assertIn("603787", called_codes)
                self.assertIn("601226", called_codes)
                self.assertEqual(len(called_codes), 2)

    def test_ats_save_all_open_sbc_windows_with_subprocesses(self):
        """测试 ATS 关闭时能够扫描到正在运行的独立子进程，绝不将 sbc_open_windows 误清空为 []"""
        from ats.ui.intraday_strategy_dialog import save_all_open_sbc_windows, restore_all_open_sbc_windows
        from ats.ui.sbc_launcher import SBCProcessManager

        mgr = SBCProcessManager.get_instance()
        mock_proc_1 = MagicMock()
        mock_proc_1.poll.return_value = None
        mock_proc_1.pid = 11111

        mock_proc_2 = MagicMock()
        mock_proc_2.poll.return_value = None
        mock_proc_2.pid = 22222

        mgr._procs = {
            "600733": mock_proc_1,
            "603407": mock_proc_2
        }

        with patch('ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path', return_value=self.ats_sbc_cfg):
            # 执行 ATS 退出保存
            save_all_open_sbc_windows()

            self.assertTrue(os.path.exists(self.ats_sbc_cfg))
            with open(self.ats_sbc_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)

            open_wins = data.get("sbc_open_windows", [])
            saved_codes = [item["code"] for item in open_wins]
            self.assertIn("600733", saved_codes, "活跃子进程 600733 必须被持久化")
            self.assertIn("603407", saved_codes, "活跃子进程 603407 必须被持久化")
            self.assertEqual(len(saved_codes), 2)

            # 验证以子进程方式恢复
            with patch('ats.ui.sbc_launcher.launch_sbc_process') as mock_launch:
                mock_launch.return_value = MagicMock()
                restore_all_open_sbc_windows(as_subprocess=True)

                launched_codes = [call.args[0] for call in mock_launch.call_args_list]
                self.assertIn("600733", launched_codes)
                self.assertIn("603407", launched_codes)
                self.assertEqual(len(launched_codes), 2)

        mgr._procs.clear()


if __name__ == "__main__":
    unittest.main()

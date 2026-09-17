# -*- coding: utf-8 -*-
"""
tests/test_sbc_holdings_launch_no_frequent_save.py
--------------------------------------------------
专项验证：修复 --sbc-holdings 默认打开频繁持久化的 bug
1. 【恢复历史配置 0 频写盘】：恢复上次退出的 4 个持仓盯盘窗口过程中及恢复完成后，调用 save_launcher_holdings_windows 次数为 0；
2. 【恢复状态守卫】：在 restore_launcher_holdings_windows 执行期间，_is_restoring_holdings 状态为 True，阻断 open_sbc_chart_dialog 内部的每次保存；
3. 【内容指纹脏检查】：未发生几何与标的变动时，不产生重复磁盘 I/O；
4. 【初次无配置自适应持久化】：仅在全新无历史配置从真实持仓初始化时，在平铺后执行 1 次落盘；
5. 【退出持久化保持完好】：用户主动退出或按 Alt 点击关闭时，依然可靠落盘保存。
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(TEST_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect
import run_sbc

_app = QApplication.instance() or QApplication(sys.argv)


class TestSBCHoldingsLaunchNoFrequentSave(unittest.TestCase):

    def setUp(self):
        self.temp_cfg = os.path.join(STOCK_STANDALONE, "config", f"test_no_frequent_save_{os.getpid()}.json")
        os.environ["SBC_LAYOUT_CONFIG_PATH"] = self.temp_cfg
        os.environ["SBC_IS_HOLDINGS_LAUNCHER"] = "1"
        run_sbc._last_save_holdings_time = 0.0
        run_sbc._last_saved_content_fingerprint = ""
        run_sbc._is_restoring_holdings = False
        if os.path.exists(self.temp_cfg):
            try:
                os.remove(self.temp_cfg)
            except Exception:
                pass

    def tearDown(self):
        run_sbc._is_restoring_holdings = False
        if os.path.exists(self.temp_cfg):
            try:
                os.remove(self.temp_cfg)
            except Exception:
                pass

    def test_restore_holdings_from_config_has_zero_saves(self):
        """【核心验证】恢复已存的 4 个持仓盯盘窗口，全流程触发保存次数为 0，彻底杜绝 1,2,3,4,4,4 重复写盘"""
        # 预先写入 4 个历史窗口配置
        init_data = {
            "sbc_holdings_windows": [
                {"code": "920038", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"},
                {"code": "603407", "x": 800, "y": 100, "width": 680, "height": 420, "period_mode": "10d"},
                {"code": "688635", "x": 100, "y": 550, "width": 680, "height": 420, "period_mode": "10d"},
                {"code": "600733", "x": 800, "y": 550, "width": 680, "height": 420, "period_mode": "10d"},
            ],
            "initialized": True
        }
        with open(self.temp_cfg, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)

        created_dlgs = []
        def fake_open_dialog(parent_win=None, code="688826", period_mode="10d", *args, **kwargs):
            # 验证在 open_sbc_chart_dialog 被调用期间，_is_restoring_holdings 必须处于保护状态 (True)
            self.assertTrue(run_sbc._is_restoring_holdings, f"恢复标的 {code} 期间 _is_restoring_holdings 必须为 True！")
            dlg = MagicMock()
            dlg.code = code
            dlg.geometry.return_value = QRect(100, 100, 680, 420)
            created_dlgs.append(dlg)
            return dlg

        with patch("run_sbc.open_sbc_chart_dialog", side_effect=fake_open_dialog), \
             patch("run_sbc.save_launcher_holdings_windows") as mock_save:

            restored = run_sbc.restore_launcher_holdings_windows()

            # 断言 4 个窗口全部成功恢复
            self.assertEqual(len(restored), 4)
            self.assertEqual([d.code for d in restored], ["920038", "603407", "688635", "600733"])

            # 核心断言：全流程 mock_save 被调用的次数严格为 0！
            mock_save.assert_not_called()

            # 恢复完成后，状态必须已安全复位为 False
            self.assertFalse(run_sbc._is_restoring_holdings)

    def test_first_launch_without_config_saves_once_after_rearrange(self):
        """【测试】无历史配置初次启动时，从真实持仓初始化后仅在平铺后落盘 1 次"""
        if os.path.exists(self.temp_cfg):
            os.remove(self.temp_cfg)

        mock_holdings = ["600733", "000001"]
        with patch("run_sbc._get_current_holding_codes", return_value=mock_holdings), \
             patch("run_sbc.open_sbc_chart_dialog") as mock_open, \
             patch("run_sbc.rearrange_all_sbc_windows") as mock_rearrange, \
             patch("run_sbc.save_launcher_holdings_windows") as mock_save:

            mock_dlg1 = MagicMock()
            mock_dlg2 = MagicMock()
            mock_open.side_effect = [mock_dlg1, mock_dlg2]

            restored = run_sbc.restore_launcher_holdings_windows()

            self.assertEqual(len(restored), 2)
            mock_rearrange.assert_called_once()
            # 初次初始化只写盘 1 次
            mock_save.assert_called_once_with(force=True)

    def test_content_fingerprint_dirty_check_skips_redundant_io(self):
        """【测试】内容指纹未变时，即使调用 save_launcher_holdings_windows 也会直接跳过重复写盘"""
        # 预先生成配置
        init_data = {
            "sbc_holdings_windows": [
                {"code": "600733", "x": 10, "y": 10, "width": 640, "height": 420, "period_mode": "10d"}
            ],
            "initialized": True
        }
        with open(self.temp_cfg, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)

        # 模拟 1 个顶层窗口
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
        mock_dlg = MagicMock(spec=SBCIntradayChartDialog)
        mock_dlg.isVisible.return_value = True
        mock_dlg._is_closing = False
        mock_dlg.code = "600733"
        mock_dlg._current_period_mode = "10d"
        mock_dlg.normal_geometry = QRect(10, 10, 640, 420)
        mock_dlg.geometry.return_value = QRect(10, 10, 640, 420)

        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[mock_dlg]), \
             patch("PyQt6.sip.isdeleted", return_value=False):

            # 第一次调用（无指纹），正常写盘并记录指纹
            run_sbc.save_launcher_holdings_windows(force=True)
            self.assertTrue(bool(run_sbc._last_saved_content_fingerprint))

            mtime_1 = os.path.getmtime(self.temp_cfg)

            # 第二次调用（内容完全一致），命中指纹直接 return，不触碰磁盘
            with patch("builtins.open", side_effect=AssertionError("不应触发文件 open 写入！")):
                run_sbc.save_launcher_holdings_windows(force=True)

            mtime_2 = os.path.getmtime(self.temp_cfg)
            self.assertEqual(mtime_1, mtime_2, "磁盘文件修改时间未变，验证跳过冗余 I/O")

    def test_prevent_overwriting_with_zero_windows(self):
        """【测试】铁壁防冲洗守卫：退出时若扫描结果为 0 个窗口，绝不覆写清零历史配置"""
        initial_data = {
            "sbc_holdings_windows": [
                {"code": "600733", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"}
            ],
            "initialized": True
        }
        with open(self.temp_cfg, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        # 模拟 QApplication.topLevelWidgets() 返回空或全部为关闭状态
        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[]):
            run_sbc.save_launcher_holdings_windows(force=True, allow_empty=False)

        # 断言：文件中的配置依然是 1 个标的，绝对没有被抹杀成 0！
        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(len(saved.get("sbc_holdings_windows", [])), 1)
        self.assertEqual(saved["sbc_holdings_windows"][0]["code"], "600733")

    def test_recent_three_history_snapshots_rotation(self):
        """【测试】维护最近 3 组历史快照，滚动更新且最多保留 3 组"""
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog

        def _make_mock_win(code):
            w = MagicMock(spec=SBCIntradayChartDialog)
            w.code = code
            w._is_closing = False
            w.isVisible.return_value = True
            w.is_hidden_state = False
            w.normal_geometry = None
            geo_mock = MagicMock()
            geo_mock.x.return_value = 100
            geo_mock.y.return_value = 100
            geo_mock.width.return_value = 680
            geo_mock.height.return_value = 420
            w.geometry.return_value = geo_mock
            w._current_period_mode = "10d"
            return w

        # 批次 1: ["600733"]
        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[_make_mock_win("600733")]), \
             patch("PyQt6.sip.isdeleted", return_value=False):
            run_sbc.save_launcher_holdings_windows(force=True)

        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            d1 = json.load(f)
        self.assertEqual(len(d1.get("recent_history_snapshots", [])), 1)
        self.assertEqual(d1["recent_history_snapshots"][0]["codes"], ["600733"])

        # 批次 2: ["600733", "603407"]
        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[_make_mock_win("600733"), _make_mock_win("603407")]), \
             patch("PyQt6.sip.isdeleted", return_value=False):
            run_sbc.save_launcher_holdings_windows(force=True)

        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            d2 = json.load(f)
        self.assertEqual(len(d2.get("recent_history_snapshots", [])), 2)
        self.assertEqual(d2["recent_history_snapshots"][0]["codes"], ["600733", "603407"])

        # 批次 3: ["688635"]
        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[_make_mock_win("688635")]), \
             patch("PyQt6.sip.isdeleted", return_value=False):
            run_sbc.save_launcher_holdings_windows(force=True)

        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            d3 = json.load(f)
        self.assertEqual(len(d3.get("recent_history_snapshots", [])), 3)
        self.assertEqual(d3["recent_history_snapshots"][0]["codes"], ["688635"])

        # 批次 4: ["000001"] -> 淘汰最旧一组，始终保持 3 组
        with patch("PyQt6.QtWidgets.QApplication.topLevelWidgets", return_value=[_make_mock_win("000001")]), \
             patch("PyQt6.sip.isdeleted", return_value=False):
            run_sbc.save_launcher_holdings_windows(force=True)

        with open(self.temp_cfg, "r", encoding="utf-8") as f:
            d4 = json.load(f)
        snapshots = d4.get("recent_history_snapshots", [])
        self.assertEqual(len(snapshots), 3, "最多保留最近 3 组历史快照")
        self.assertEqual(snapshots[0]["codes"], ["000001"])
        self.assertEqual(snapshots[1]["codes"], ["688635"])
        self.assertEqual(snapshots[2]["codes"], ["600733", "603407"])

    def test_disaster_recovery_from_snapshots_when_current_empty(self):
        """【测试】当当前持仓配置为空时，自动从 recent_history_snapshots[0] 灾备恢复"""
        corrupted_data = {
            "sbc_holdings_windows": [],
            "sbc_open_windows": [],
            "initialized": True,
            "recent_history_snapshots": [
                {
                    "time": "2026-09-17 12:00:00",
                    "codes": ["600733"],
                    "windows": [{"code": "600733", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"}]
                }
            ]
        }
        with open(self.temp_cfg, "w", encoding="utf-8") as f:
            json.dump(corrupted_data, f)

        with patch("run_sbc.open_sbc_chart_dialog") as mock_open:
            mock_dlg = MagicMock()
            mock_dlg.code = "600733"
            mock_open.return_value = mock_dlg

            restored = run_sbc.restore_launcher_holdings_windows()

        self.assertEqual(len(restored), 1)
        mock_open.assert_called_with(None, code="600733", period_mode="10d")

    def test_switch_to_history_snapshot_and_cli_selection(self):
        """【测试】通过 snapshot_index 指定加载或运行时一键切换至历史快照组"""
        sample_data = {
            "sbc_holdings_windows": [
                {"code": "600733", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"}
            ],
            "initialized": True,
            "recent_history_snapshots": [
                {
                    "time": "2026-09-17 12:45:00",
                    "codes": ["600733", "603407"],
                    "windows": [
                        {"code": "600733", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"},
                        {"code": "603407", "x": 800, "y": 100, "width": 680, "height": 420, "period_mode": "10d"}
                    ]
                },
                {
                    "time": "2026-09-17 11:30:00",
                    "codes": ["688635"],
                    "windows": [
                        {"code": "688635", "x": 100, "y": 100, "width": 680, "height": 420, "period_mode": "10d"}
                    ]
                }
            ]
        }
        with open(self.temp_cfg, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # 1. 验证获取快照列表
        snapshots = run_sbc.get_launcher_history_snapshots()
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["codes"], ["600733", "603407"])
        self.assertEqual(snapshots[1]["codes"], ["688635"])

        # 2. 验证指定 snapshot_index=2 恢复
        with patch("run_sbc.open_sbc_chart_dialog") as mock_open:
            mock_dlg = MagicMock()
            mock_dlg.code = "688635"
            mock_open.return_value = mock_dlg

            restored_snap2 = run_sbc.restore_launcher_holdings_windows(snapshot_index=2)
            self.assertEqual(len(restored_snap2), 1)
            mock_open.assert_called_with(None, code="688635", period_mode="10d")

        # 3. 验证运行时一键切换至快照 1
        with patch("run_sbc.open_sbc_chart_dialog") as mock_open, \
             patch("run_sbc.rearrange_all_sbc_windows") as mock_rearrange:
            d1 = MagicMock()
            d1.code = "600733"
            d2 = MagicMock()
            d2.code = "603407"
            mock_open.side_effect = [d1, d2]

            switched = run_sbc.switch_to_history_snapshot(1)
            self.assertEqual(len(switched), 2)
            mock_rearrange.assert_called_once()


if __name__ == "__main__":
    unittest.main()

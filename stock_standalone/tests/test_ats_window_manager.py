# -*- coding: utf-8 -*-
"""
tests/test_ats_window_manager.py
ATS 多窗口位置独立快照管理与多显示器防覆盖引擎单元测试
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QWidget, QDialog, QMainWindow
from PyQt6.QtCore import QPoint, QRect

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.ui.ats_window_manager import ATSWindowManager
from ats.ui.universe_widget import UniverseTreeWidget


class TestATSWindowManager(unittest.TestCase):

    def setUp(self):
        # 创建独立的临时配置文件隔离真实配置
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_cfg_file = os.path.join(self.temp_dir.name, "window_config.json")
        self.mock_scale2_cfg_file = os.path.join(self.temp_dir.name, "scale2_window_config.json")

        self.mgr = ATSWindowManager()
        self.mgr._config_file = self.mock_cfg_file

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_slots_info_initial_empty(self):
        """测试初始无快照时 3 个槽位状态正确返回空"""
        slots = self.mgr.get_snapshot_slots_info()
        self.assertEqual(len(slots), 3)
        for s in (1, 2, 3):
            self.assertIn(s, slots)
            self.assertFalse(slots[s]["exists"])
            self.assertEqual(slots[s]["window_count"], 0)
            self.assertIn("空 / 未保存", slots[s]["label"])

        tooltip = self.mgr.get_snapshot_tooltip_text("📍 手动保存快照")
        self.assertIn("槽位 1: [空 / 未保存]", tooltip)
        self.assertIn("槽位 2: [空 / 未保存]", tooltip)
        self.assertIn("槽位 3: [空 / 未保存]", tooltip)

    def test_02_save_and_read_snapshot_slot_1(self):
        """测试槽位 1 窗口快照保存与元信息更新"""
        # 构建 Mock 主窗口和子窗口
        mock_mw = MagicMock()
        mock_mw.isWindow.return_value = True
        mock_mw.isVisible.return_value = True
        mock_mw.isMaximized.return_value = False
        mock_mw.geometry.return_value = QRect(100, 100, 1400, 850)

        mock_dragon = MagicMock()
        mock_dragon.isWindow.return_value = True
        mock_dragon.isVisible.return_value = True
        mock_dragon.isMaximized.return_value = False
        mock_dragon.geometry.return_value = QRect(200, 200, 900, 600)
        mock_dragon.is_hidden_state = False
        mock_dragon.stays_on_top = True
        mock_mw.dragon_monitor_dialog = mock_dragon

        mock_zt = MagicMock()
        mock_zt.isWindow.return_value = True
        mock_zt.isVisible.return_value = True
        mock_zt.isMaximized.return_value = False
        mock_zt.geometry.return_value = QRect(300, 300, 900, 450)
        mock_mw.daily_limit_up_dialog = mock_zt

        # 执行保存到槽位 1
        res = self.mgr.save_snapshot(slot=1, main_window=mock_mw)
        self.assertTrue(res["success"])
        self.assertEqual(res["slot"], 1)
        self.assertGreaterEqual(res["total_windows"], 3)
        self.assertIn("ats_main_window", res["window_names"])
        self.assertIn("dragon_leader_monitor_dialog", res["window_names"])
        self.assertIn("daily_limit_up_dialog", res["window_names"])

        # 检查写盘的配置文件
        self.assertTrue(os.path.exists(self.mock_cfg_file))
        with open(self.mock_cfg_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("ats_manual_snapshot_1", data)
        snap1 = data["ats_manual_snapshot_1"]
        self.assertEqual(snap1["slot"], 1)
        self.assertGreaterEqual(len(snap1["windows"]), 3)

        # 验证槽位查询反映了最新状态
        slots = self.mgr.get_snapshot_slots_info()
        self.assertTrue(slots[1]["exists"])
        self.assertGreaterEqual(slots[1]["window_count"], 3)
        self.assertFalse(slots[2]["exists"])
        self.assertFalse(slots[3]["exists"])

    def test_03_restore_snapshot_and_window_activation(self):
        """测试从槽位 1 恢复窗口几何位置与激活前台"""
        # 先保存一个快照
        mock_mw = MagicMock()
        mock_mw.isWindow.return_value = True
        mock_mw.isVisible.return_value = True
        mock_mw.isMaximized.return_value = False
        mock_mw.geometry.return_value = QRect(150, 120, 1300, 800)

        mock_hot = MagicMock()
        mock_hot.isWindow.return_value = True
        mock_hot.isVisible.return_value = True
        mock_hot.isMaximized.return_value = False
        mock_hot.geometry.return_value = QRect(400, 250, 800, 500)
        mock_mw.hot_sector_dialog = mock_hot

        self.mgr.save_snapshot(slot=1, main_window=mock_mw)

        # 重置 mock 调用记录
        mock_mw.reset_mock()
        mock_hot.reset_mock()

        # 执行恢复
        count, restored_list = self.mgr.restore_snapshot(slot=1, main_window=mock_mw)
        self.assertGreaterEqual(count, 2)
        self.assertIn("ats_main_window", restored_list)
        self.assertIn("hot_sector_leaderboard_dialog", restored_list)

        # 验证主窗口和子窗口均被调用了 setGeometry 以及置顶唤醒
        mock_mw.setGeometry.assert_called()
        mock_hot.setGeometry.assert_called()
        mock_hot.raise_.assert_called()
        mock_hot.activateWindow.assert_called()

    def test_04_multi_screen_clamp_and_cascade_anti_overlap(self):
        """测试多显示器边界校验与副屏断开防覆盖错峰展开 (Cascade Anti-Overlap)"""
        screens = QApplication.screens()
        if not screens:
            self.skipTest("无有效显示器环境")

        primary = screens[0]
        avail = primary.availableGeometry()

        # 1. 在主屏内的正常坐标：应当被安全保持在屏幕可用区域内
        rx, ry, rw, rh = self.mgr.clamp_to_screens_qt(avail.left() + 50, avail.top() + 50, 800, 500)
        self.assertGreaterEqual(rx, avail.left())
        self.assertLessEqual(rx + rw, avail.right() + 1)
        self.assertGreaterEqual(ry, avail.top())
        self.assertLessEqual(ry + rh, avail.bottom() + 1)

        # 2. 严重越界坐标（如 x: -9999, y: -9999 飞出屏幕左上角）：智能吸附回屏幕内部
        rx_neg, ry_neg, _, _ = self.mgr.clamp_to_screens_qt(-9999, -9999, 600, 400, cascade_idx=0)
        self.assertGreaterEqual(rx_neg, avail.left())
        self.assertGreaterEqual(ry_neg, avail.top())

        # 3. 副屏断开回退场景（坐标严重超出所有当前屏幕）：测试不同 cascade_idx 的错峰偏移，杜绝覆盖
        rx1, ry1, _, _ = self.mgr.clamp_to_screens_qt(99999, 99999, 600, 400, cascade_idx=1)
        rx2, ry2, _, _ = self.mgr.clamp_to_screens_qt(99999, 99999, 600, 400, cascade_idx=2)
        # 验证两个窗口不会在同一个像素点重叠
        self.assertNotEqual((rx1, ry1), (rx2, ry2))
        self.assertEqual(rx2 - rx1, 30)
        self.assertEqual(ry2 - ry1, 30)

    def test_05_universe_widget_ui_buttons_and_menus(self):
        """测试 UniverseTreeWidget 顶部工具栏中的 📍 和 🔧 按钮及其菜单构建"""
        u_widget = UniverseTreeWidget()
        u_widget.window_manager._config_file = self.mock_cfg_file

        self.assertTrue(hasattr(u_widget, "btn_save_pos"))
        self.assertTrue(hasattr(u_widget, "btn_restore_pos"))
        self.assertEqual(u_widget.btn_save_pos.text(), "📍")
        self.assertEqual(u_widget.btn_restore_pos.text(), "🔧")

        # 验证保存菜单能正常生成且包含 3 个槽位
        save_menu = u_widget.window_manager.build_save_menu(u_widget, lambda s: None)
        actions = save_menu.actions()
        # Header + Separator + 3 Slots = 5 items
        self.assertEqual(len(actions), 5)
        self.assertFalse(actions[0].isEnabled())  # 标题不可点击
        self.assertTrue(actions[0].text().startswith("📍 选择要保存"))

        # 初始无快照时，恢复菜单中的槽位全部置灰禁用
        restore_menu = u_widget.window_manager.build_restore_menu(u_widget, lambda s: None)
        r_actions = restore_menu.actions()
        self.assertEqual(len(r_actions), 5)
        self.assertFalse(r_actions[0].isEnabled())
        # 槽位 1, 2, 3 为空，均处于 disabled 状态
        self.assertFalse(r_actions[2].isEnabled())
        self.assertFalse(r_actions[3].isEnabled())
        self.assertFalse(r_actions[4].isEnabled())

        # 验证点击弹出菜单不会抛出任何异常 (包括 QPoint 等符号引用)
        with patch("PyQt6.QtWidgets.QMenu.exec") as mock_exec:
            u_widget._popup_save_slots_menu()
            self.assertTrue(mock_exec.called)

        with patch("PyQt6.QtWidgets.QMenu.exec") as mock_exec:
            u_widget._popup_restore_slots_menu()
            self.assertTrue(mock_exec.called)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
ATS Alert Notifier Screen Persistence & Self-Healing Unit Tests
验证通知显示器与坐标的自动持久化存储、拔掉副屏/分辨率变异时的物理级自修复及 DPI 自适应
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.alert_notifier import (
    save_toast_screen_config,
    load_toast_screen_config,
    InAppToastWidget,
    get_screen_dpi_scale,
    ALERT_CONFIG_FILE
)


class TestAlertNotifierScreenPersistence(unittest.TestCase):

    def test_save_and_load_config(self):
        # 1. 测试正常保存与读取
        save_toast_screen_config(target_screen_index=0, custom_pos=(500, 300))
        load_toast_screen_config()
        self.assertEqual(InAppToastWidget._target_screen_index, 0)
        self.assertEqual(InAppToastWidget._custom_pos, (500, 300))

    def test_self_healing_invalid_screen_index(self):
        # 2. 模拟保存了不存在的副屏索引 (如拔掉副屏，屏幕变为仅 1 块，保存了 screen_index=99)
        save_toast_screen_config(target_screen_index=99, custom_pos=None)
        load_toast_screen_config()
        # 应当自愈 fallback 为 None (主屏幕)
        self.assertIsNone(InAppToastWidget._target_screen_index)

    def test_self_healing_dead_zone_coordinate(self):
        # 3. 模拟保存了不可见盲区坐标 (如负坐标或超大越界坐标 99999, 99999)
        save_toast_screen_config(target_screen_index=0, custom_pos=(99999, 99999))
        load_toast_screen_config()
        # 应当自愈重置为 None
        self.assertIsNone(InAppToastWidget._custom_pos)

    def test_dpi_scale_calc(self):
        scale = get_screen_dpi_scale(None)
        self.assertGreaterEqual(scale, 0.8)
        self.assertLessEqual(scale, 3.0)


if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    unittest.main()

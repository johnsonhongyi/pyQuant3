# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(CURRENT_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

from ats.ui.intraday_strategy_dialog import get_ats_closing_flag_path, _is_ats_shutting_down


class TestATSClosingRamDisk(unittest.TestCase):
    """测试 ATS 退出标记文件迁移至 RamDisk 的路径解析、回退机制与退出感知"""

    def setUp(self):
        self.orig_env_flag = os.environ.get("ATS_CLOSING_FLAG_PATH")
        if "ATS_CLOSING_FLAG_PATH" in os.environ:
            del os.environ["ATS_CLOSING_FLAG_PATH"]
        if "ATS_IS_CLOSING" in os.environ:
            del os.environ["ATS_IS_CLOSING"]

    def tearDown(self):
        if self.orig_env_flag is not None:
            os.environ["ATS_CLOSING_FLAG_PATH"] = self.orig_env_flag
        elif "ATS_CLOSING_FLAG_PATH" in os.environ:
            del os.environ["ATS_CLOSING_FLAG_PATH"]

    def test_env_override(self):
        """测试环境变量 ATS_CLOSING_FLAG_PATH 具备最高优先级覆盖"""
        fake_path = r"C:\fake\test\.ats_closing"
        os.environ["ATS_CLOSING_FLAG_PATH"] = fake_path
        self.assertEqual(get_ats_closing_flag_path(), fake_path)

    def test_ramdisk_path_and_drive_normalization(self):
        """测试 RamDisk 盘符结尾未带斜杠时自动补齐规范化 (如 G: -> G:\.ats_closing)"""
        with patch("JohnsonUtil.commonTips.get_ramdisk_dir", return_value="G:"), \
             patch("os.path.isdir", return_value=True):
            flag_path = get_ats_closing_flag_path()
            self.assertTrue(flag_path.startswith("G:\\") or flag_path.startswith("G:/"))
            self.assertTrue(flag_path.endswith(".ats_closing"))
            self.assertNotIn("G:.ats_closing", flag_path)

    def test_fallback_to_config_when_no_ramdisk(self):
        """测试未配置 RamDisk 或目录不存在时自动回退到本地 config/.ats_closing"""
        with patch("JohnsonUtil.commonTips.get_ramdisk_dir", return_value=None):
            flag_path = get_ats_closing_flag_path()
            expected_tail = os.path.join("config", ".ats_closing")
            self.assertTrue(flag_path.endswith(expected_tail))

    def test_is_ats_shutting_down_detection_on_ramdisk(self):
        """测试写入 RamDisk 标志文件后 _is_ats_shutting_down 能够即时感知并响应"""
        flag_path = get_ats_closing_flag_path()
        flag_dir = os.path.dirname(flag_path)
        if flag_dir and not os.path.exists(flag_dir):
            os.makedirs(flag_dir, exist_ok=True)

        # 确保测试前不存在
        if os.path.exists(flag_path):
            os.remove(flag_path)

        self.assertFalse(_is_ats_shutting_down())

        # 模拟 ATS 主程序退出写入
        try:
            with open(flag_path, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            self.assertTrue(_is_ats_shutting_down())
        finally:
            if os.path.exists(flag_path):
                os.remove(flag_path)

        self.assertFalse(_is_ats_shutting_down())


if __name__ == "__main__":
    unittest.main()

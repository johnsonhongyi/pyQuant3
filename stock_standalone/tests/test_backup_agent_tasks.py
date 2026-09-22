# -*- coding: utf-8 -*-
"""
tests/test_backup_agent_tasks.py
--------------------------------
单元测试：多任务自动化备份与最近 5 个存档滚动清理
"""

import os
import shutil
import tempfile
import unittest
from tools.backup_agent_tasks import prune_old_archives, create_backup_archive


class TestBackupAgentTasks(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source_staging")
        os.makedirs(self.source_dir, exist_ok=True)
        # 创建一个测试文件
        with open(os.path.join(self.source_dir, "sample.txt"), "w") as f:
            f.write("hello backup")

        self.target_root = os.path.join(self.temp_dir, "target_backup")
        os.makedirs(self.target_root, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prune_old_archives_keeps_exactly_limit(self):
        """测试历史备份滚动淘汰机制：生成 7 个假文件，严格保留最新的 5 个"""
        dummy_files = []
        for i in range(7):
            fname = os.path.join(self.target_root, f"agent_config_backup_2026092{i}_120000.zip")
            with open(fname, "w") as f:
                f.write(f"archive {i}")
            # 设置递增的时间戳
            os.utime(fname, (1789900000 + i * 100, 1789900000 + i * 100))
            dummy_files.append(fname)

        self.assertEqual(len(os.listdir(self.target_root)), 7)

        # 执行清理，限制保留 5 个
        deleted = prune_old_archives(self.target_root, max_keep=5)
        self.assertEqual(len(deleted), 2)

        # 检查剩余文件数量为 5
        remaining = [f for f in os.listdir(self.target_root) if f.startswith("agent_config_backup_")]
        self.assertEqual(len(remaining), 5)
        # 确认最旧的 2 个被清理
        self.assertNotIn("agent_config_backup_20260920_120000.zip", remaining)
        self.assertNotIn("agent_config_backup_20260921_120000.zip", remaining)
        # 最新的依然坚挺存在
        self.assertIn("agent_config_backup_20260926_120000.zip", remaining)

    def test_create_backup_archive_generates_zip_and_latest(self):
        """测试正常打包与最新指针生成"""
        zip_path, latest_root = create_backup_archive(self.source_dir, self.target_root, max_keep=5)
        self.assertTrue(os.path.exists(zip_path))
        self.assertTrue(os.path.exists(latest_root))
        self.assertEqual(os.path.basename(latest_root), "agent_config_latest.zip")


if __name__ == "__main__":
    unittest.main()

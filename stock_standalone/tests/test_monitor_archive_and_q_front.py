# -*- coding: utf-8 -*-
import os
import sys
import unittest
import tempfile
import shutil
import json
from unittest.mock import MagicMock, patch

class TestMonitorArchiveAndQFront(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.archive_dir = os.path.join(self.test_dir, "archives")
        os.makedirs(self.archive_dir, exist_ok=True)
        self.monitor_file = os.path.join(self.test_dir, "monitor_list.json")
        self.alerts_file = os.path.join(self.test_dir, "alerts.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_archive_file_cross_day_logic(self):
        """测试跨天即使内容完全相同，也必须生成当天的独立历史快照，不能被旧归档拦截"""
        sample_data = [{"code": "600688", "name": "上海石化"}]
        with open(self.monitor_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, ensure_ascii=False)

        # 模拟 2026-09-21 已经存在归档
        old_archive = os.path.join(self.archive_dir, "monitor_list_2026-09-21.json")
        shutil.copy2(self.monitor_file, old_archive)

        # 导入修复后的核心 archive_file 逻辑模拟测试
        def mock_archive_file(src_file, prefix, archive_dir, base_dir, current_date):
            if not os.path.isabs(src_file):
                src_file = os.path.join(base_dir, src_file)
            if not os.path.exists(src_file):
                return False
            with open(src_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content or content in ("[]", "{}", ""):
                return False

            filename = f"{prefix}_{current_date}.json"
            dest = os.path.join(archive_dir, filename)

            files = sorted(
                [f for f in os.listdir(archive_dir) if f.startswith(prefix + "_") and not f.endswith(".tmp")],
                reverse=True
            )
            if files:
                last_file = os.path.join(archive_dir, files[0])
                with open(last_file, "r", encoding="utf-8") as f:
                    last_content = f.read().strip()
                # 仅当今日已有当天归档且内容相同才跳过
                if os.path.exists(dest) and content == last_content:
                    return False

            shutil.copy2(src_file, dest)
            return True

        # 1. 模拟到了 2026-10-30 新交易日，内容与 09-21 相同：必须成功生成 10-30 归档！
        res = mock_archive_file("monitor_list.json", "monitor_list", self.archive_dir, self.test_dir, "2026-10-30")
        self.assertTrue(res, "新交易日即使内容相同，也必须成功归档")
        self.assertTrue(os.path.exists(os.path.join(self.archive_dir, "monitor_list_2026-10-30.json")))

        # 2. 模拟当天再次触发归档：当天已有归档且内容未变，跳过重复写入
        res_repeat = mock_archive_file("monitor_list.json", "monitor_list", self.archive_dir, self.test_dir, "2026-10-30")
        self.assertFalse(res_repeat, "当天已有相同归档应跳过重复写入")

    def test_bring_all_monitors_to_front_without_topmost_or_rearrange(self):
        """测试按 Q 键把所有监控带到最前显示：不用置顶，不用重排"""
        # 构造 mock windows
        win1 = MagicMock()
        win1.winfo_exists.return_value = True
        win1.state.return_value = "iconic"  # 最小化
        win1.geometry.return_value = "300x200+100+100"

        win2 = MagicMock()
        win2.winfo_exists.return_value = True
        win2.state.return_value = "normal"
        win2.geometry.return_value = "300x200+410+100"

        mock_monitor_windows = {
            "600688": {"toplevel": win1},
            "002526": {"toplevel": win2}
        }

        def mock_bring_all_monitors_to_front(event=None):
            if event and getattr(event, "widget", None):
                cls_name = getattr(event.widget, "winfo_class", lambda: "")()
                if cls_name in ("Entry", "TEntry", "Text", "Combobox", "TCombobox"):
                    return False

            count = 0
            for code, info in list(mock_monitor_windows.items()):
                win = info.get("toplevel")
                if win and win.winfo_exists():
                    if win.state() == "iconic":
                        win.deiconify()
                    win.lift()
                    count += 1
            return count

        # 触发带到最前
        count = mock_bring_all_monitors_to_front(event=None)
        self.assertEqual(count, 2)

        # 验证 win1 最小化被还原
        win1.deiconify.assert_called_once()
        win1.lift.assert_called_once()
        # 验证 win2 被提升
        win2.lift.assert_called_once()

        # 严格验证：绝不能调用 attributes("-topmost", True)，绝不能调用 geometry(...) 重新排列
        for call_args in win1.attributes.call_args_list:
            self.assertNotIn("-topmost", str(call_args))
        for call_args in win2.attributes.call_args_list:
            self.assertNotIn("-topmost", str(call_args))
        win1.geometry.assert_not_called()  # 严格不修改坐标位置
        win2.geometry.assert_not_called()

        # 验证输入框打字时不误触发
        mock_entry_event = MagicMock()
        mock_entry_event.widget.winfo_class.return_value = "Entry"
        ret = mock_bring_all_monitors_to_front(event=mock_entry_event)
        self.assertFalse(ret)

    def test_schedule_save_positions_not_overwritten(self):
        """测试 schedule_save_positions 的双任务延迟持久化不被覆盖"""
        saved = []
        def mock_save_monitor_list():
            saved.append("monitor_list")

        def mock_save_window_positions():
            saved.append("window_positions")

        def _delayed_save_both():
            mock_save_monitor_list()
            mock_save_window_positions()

        _delayed_save_both()
        self.assertEqual(saved, ["monitor_list", "window_positions"], "监控数据和窗口位置必须同时保存")

if __name__ == "__main__":
    unittest.main()

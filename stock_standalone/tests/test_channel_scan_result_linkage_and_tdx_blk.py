# -*- coding: utf-8 -*-
"""
tests/test_channel_scan_result_linkage_and_tdx_blk.py
针对 60f 通道策略批量测算结果独立窗口键盘上下键联动、防抖及自适应 TDX 板块写入与持久化记忆的专项测试。
"""

import sys
import os
import unittest
import tempfile
import pandas as pd
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication

# Ensure stock_standalone is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog, PERSIST_KEY_LAST_TDX_BLK
from ats.ui.styles import save_config_node, load_config_node

# Ensure single QApplication instance for Qt tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestChannelScanResultLinkageAndTDXBlk(unittest.TestCase):
    """测试通道测算结果窗口的键盘上下键联动、TDX 板块写入与位置持久化"""

    def setUp(self):
        self.sample_df = pd.DataFrame([
            {
                "code": "920180",
                "name": "爱得科技",
                "channel_type_cn": "上涨通道顺势",
                "pattern_name": "上涨通道下轨回踩企稳",
                "score": 96.0,
                "entry_price": 11.76,
                "stop_loss": 11.57,
                "target_price_1": 12.47,
                "target_price_2": 12.94,
                "channel_slope_deg": 14.4,
                "volume_shrink_pct": 35.3,
                "reason": "上涨通道(+14.4°) 触发"
            },
            {
                "code": "920081",
                "name": "欧伦电气",
                "channel_type_cn": "上涨通道顺势",
                "pattern_name": "上涨通道下轨回踩企稳",
                "score": 96.0,
                "entry_price": 41.12,
                "stop_loss": 40.14,
                "target_price_1": 43.59,
                "target_price_2": 45.23,
                "channel_slope_deg": 15.3,
                "volume_shrink_pct": 12.5,
                "reason": "上涨通道(+15.3°) 触发"
            },
            {
                "code": "603284",
                "name": "林平发展",
                "channel_type_cn": "上涨通道顺势",
                "pattern_name": "上涨通道下轨回踩企稳",
                "score": 96.0,
                "entry_price": 42.39,
                "stop_loss": 41.42,
                "target_price_1": 44.93,
                "target_price_2": 46.63,
                "channel_slope_deg": 19.7,
                "volume_shrink_pct": 53.4,
                "reason": "上涨通道(+19.7°) 触发"
            }
        ])
        self.dialog = ChannelReversalScanResultDialog(
            parent=None,
            df_results=self.sample_df,
            total_scanned=100,
            source_tab_name="测试板块"
        )

    def tearDown(self):
        if self.dialog:
            self.dialog.close()

    def test_keyboard_navigation_linkage(self):
        """测试键盘上下键切换当前单元格/行时正确触发联动信号"""
        emitted_signals = []
        self.dialog.stock_linkage_requested.connect(lambda code, name: emitted_signals.append((code, name)))

        # 模拟键盘光标移动到第 0 行
        self.dialog.table.setCurrentCell(0, 0)
        self.dialog._on_current_cell_changed(0, 0, -1, -1)
        self.dialog._fire_linkage_debounced()

        self.assertEqual(len(emitted_signals), 1)
        self.assertEqual(emitted_signals[0], ("920180", "爱得科技"))

        # 同一行切换列 (0, 0) -> (0, 1)，不应重复触发联动
        self.dialog._on_current_cell_changed(0, 1, 0, 0)
        self.dialog._fire_linkage_debounced()
        self.assertEqual(len(emitted_signals), 1)

        # 模拟按 Down 下方向键切换到第 1 行
        self.dialog.table.setCurrentCell(1, 0)
        self.dialog._on_current_cell_changed(1, 0, 0, 1)
        self.dialog._fire_linkage_debounced()

        self.assertEqual(len(emitted_signals), 2)
        self.assertEqual(emitted_signals[1], ("920081", "欧伦电气"))

        # 模拟按 Down 下方向键切换到第 2 行
        self.dialog.table.setCurrentCell(2, 0)
        self.dialog._on_current_cell_changed(2, 0, 1, 0)
        self.dialog._fire_linkage_debounced()

        self.assertEqual(len(emitted_signals), 3)
        self.assertEqual(emitted_signals[2], ("603284", "林平发展"))

    def test_tdx_block_discovery(self):
        """测试 TDX 自选股板块列表的自适应发现与解析"""
        blocks = self.dialog._load_available_tdx_blocks()
        self.assertIsInstance(blocks, list)
        self.assertGreater(len(blocks), 0)
        # 每个元素必须为 (bcode, display_text)
        for bcode, display in blocks:
            self.assertIsInstance(bcode, str)
            self.assertIsInstance(display, str)
            self.assertTrue(len(bcode) > 0)
            self.assertIn(bcode, display)

        # 验证下拉框加载
        self.assertGreater(self.dialog.combo_tdx_blk.count(), 0)
        current_data = self.dialog.combo_tdx_blk.currentData()
        self.assertIsNotNone(current_data)
        self.assertTrue(len(current_data) > 0)

    def test_target_codes_export_selection(self):
        """测试提取待导出代码（多选优先，全量兜底）"""
        # 1. 未选择任何特定行时，默认提取全部 3 只股票
        self.dialog.table.clearSelection()
        all_codes = self.dialog._get_target_codes_for_export()
        self.assertEqual(all_codes, ["920180", "920081", "603284"])

        # 2. 模拟单选第 1 行
        self.dialog.table.clearSelection()
        self.dialog.table.selectRow(1)
        selected_codes = self.dialog._get_target_codes_for_export()
        self.assertEqual(selected_codes, ["920081"])

        # 3. 模拟多选第 0 行和第 2 行
        self.dialog.table.clearSelection()
        for col in range(self.dialog.table.columnCount()):
            it0 = self.dialog.table.item(0, col)
            it2 = self.dialog.table.item(2, col)
            if it0:
                it0.setSelected(True)
            if it2:
                it2.setSelected(True)

        multi_selected_codes = self.dialog._get_target_codes_for_export()
        self.assertEqual(sorted(multi_selected_codes), ["603284", "920180"])

    def test_tdx_block_write_logic(self):
        """测试通过 commonTips 写入通达信板块文件的正确性"""
        from JohnsonUtil import commonTips as cct

        with tempfile.TemporaryDirectory() as tmpdir:
            test_blk_file = os.path.join(tmpdir, "099_test.blk")
            codes = ["603284", "000001", "920180"]

            # 1. 测试覆写写入
            cct.write_to_blocknew(test_blk_file, codes, append=False, doubleFile=False, keep_last=0, dfcf=False)
            self.assertTrue(os.path.exists(test_blk_file))

            with open(test_blk_file, "r", encoding="gbk", errors="ignore") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]

            # 检查通达信前缀：603284 -> 1603284, 000001 -> 0000001, 920180 -> 2920180
            self.assertIn("1603284", lines)
            self.assertIn("0000001", lines)
            self.assertIn("2920180", lines)

            # 2. 测试追加写入
            new_codes = ["688825"]
            cct.write_to_blocknew(test_blk_file, new_codes, append=True, doubleFile=False, keep_last=0, dfcf=False)

            with open(test_blk_file, "r", encoding="gbk", errors="ignore") as f:
                lines_appended = [l.strip() for l in f.readlines() if l.strip()]

            self.assertIn("1688825", lines_appended)
            self.assertIn("1603284", lines_appended)

    @patch("PyQt6.QtWidgets.QMessageBox.critical")
    @patch("PyQt6.QtWidgets.QMessageBox.warning")
    @patch("PyQt6.QtWidgets.QMessageBox.information")
    def test_ui_button_write_click(self, mock_info, mock_warn, mock_crit):
        """测试 UI 按钮触发一键写入流程及自动持久化记忆"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.dialog, "_get_tdx_blocknew_dir", return_value=tmpdir):
                # 重新填充 mock 路径下的板块
                self.dialog.combo_tdx_blk.clear()
                self.dialog.combo_tdx_blk.addItem("[066] 形态066", "066")
                self.dialog.combo_tdx_blk.addItem("[068] 068", "068")

                # 选择 068 并点击追加
                self.dialog.combo_tdx_blk.setCurrentIndex(1)
                self.dialog._on_write_block_clicked(append=True)
                self.assertIn("成功追加", self.dialog.lbl_blk_status.text())

                target_blk = os.path.join(tmpdir, "068.blk")
                self.assertTrue(os.path.exists(target_blk))

                # 验证持久化保存了 068
                saved_blk = load_config_node(PERSIST_KEY_LAST_TDX_BLK)
                self.assertEqual(saved_blk, "068")

                # 点击覆写
                self.dialog._on_write_block_clicked(append=False)
                self.assertIn("成功覆写", self.dialog.lbl_blk_status.text())

    def test_last_selected_tdx_block_persistence_restore(self):
        """测试最后选择/写入的板块在重新打开窗口时被自动恢复"""
        # 手动将持久化值设为 069
        save_config_node(PERSIST_KEY_LAST_TDX_BLK, "069")

        # 新建一个 Dialog 实例模拟重新打开窗口
        new_dialog = ChannelReversalScanResultDialog(
            parent=None,
            df_results=self.sample_df,
            total_scanned=100,
            source_tab_name="测试重新打开"
        )
        try:
            # 验证新窗口自动选中的是 069
            current_blk = new_dialog.combo_tdx_blk.currentData()
            self.assertEqual(current_blk, "069")
        finally:
            new_dialog.close()


if __name__ == "__main__":
    unittest.main()

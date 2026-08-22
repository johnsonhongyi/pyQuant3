# -*- coding: utf-8 -*-
"""
Tab 顶部公共 60f 通道测算、单选/多选交互与统计联动窗口专项单元测试
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

CURR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURR_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt6.QtWidgets import QApplication, QTableWidget
from PyQt6.QtCore import Qt, QItemSelectionModel, QItemSelection

# 确保 QApplication 单例存在
app = QApplication.instance()
if app is None:
    app = QApplication([])

from ats.ui.base_table import BaseATSTableWidget
from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog


class TestTabBatchChannelScan(unittest.TestCase):
    """Tab 顶部批量测算与单选/多选统计窗口测试套件"""

    def test_01_single_and_extended_selection(self):
        """测试 BaseATSTableWidget 的单选点击 (1行)、多选 (多行) 与未选 (全量) 标的对提取"""
        table = BaseATSTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["代码", "名称"])
        table.setRowCount(4)

        data = [("688826", "频准激光"), ("301655", "绿控传动"), ("920059", "双英集团"), ("600000", "浦发银行")]
        for r, (c, n) in enumerate(data):
            from PyQt6.QtWidgets import QTableWidgetItem
            table.setItem(r, 0, QTableWidgetItem(c))
            table.setItem(r, 1, QTableWidgetItem(n))

        self.assertEqual(table.selectionMode(), QTableWidget.SelectionMode.ExtendedSelection)

        # 1. 未选任何行时：降级提取全量
        table.clearSelection()
        all_pairs = table.get_selected_stock_pairs()
        self.assertEqual(len(all_pairs), 4)
        self.assertEqual(all_pairs[0], ("688826", "频准激光"))

        # 2. 单选点击第0行 (只选1只股票)：必须仅返回这 1 只股票，绝不跑全量！
        table.clearSelection()
        table.selectionModel().select(
            table.model().index(0, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        )
        single_pairs = table.get_selected_stock_pairs()
        self.assertEqual(len(single_pairs), 1)
        self.assertEqual(single_pairs[0], ("688826", "频准激光"))

        # 3. 模拟 Shift/Ctrl 多选选中 第0行 和 第2行 (2只股票)
        table.clearSelection()
        table.selectionModel().select(
            table.model().index(0, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        )
        table.selectionModel().select(
            table.model().index(2, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        )

        multi_pairs = table.get_selected_stock_pairs()
        self.assertEqual(len(multi_pairs), 2)
        codes = [c for c, _ in multi_pairs]
        self.assertIn("688826", codes)
        self.assertIn("920059", codes)
        print("[Test 1] BaseATSTableWidget 单选/多选/全量提取验证成功")

    def test_02_channel_scan_result_dialog_stats_and_table(self):
        """测试 ChannelReversalScanResultDialog 独立非阻塞窗口渲染与联动"""
        df_mock = pd.DataFrame([
            {
                "code": "688826",
                "name": "频准激光",
                "score": 95.0,
                "entry_price": 76.5,
                "stop_loss": 68.65,
                "target_price_1": 80.33,
                "target_price_2": 84.15,
                "channel_slope_deg": -12.5,
                "volume_shrink_pct": 35.0,
                "reason": "通道底部缩量企稳，右侧突破无新低"
            },
            {
                "code": "301655",
                "name": "绿控传动",
                "score": 88.0,
                "entry_price": 26.6,
                "stop_loss": 24.2,
                "target_price_1": 28.5,
                "target_price_2": 30.0,
                "channel_slope_deg": -8.5,
                "volume_shrink_pct": 28.0,
                "reason": "下降通道下轨触底反弹"
            }
        ])

        dlg = ChannelReversalScanResultDialog(df_results=df_mock, total_scanned=20, source_tab_name="重点关注")
        self.assertEqual(dlg.table.rowCount(), 2)
        self.assertEqual(dlg.table.item(0, 0).text(), "688826")
        self.assertEqual(dlg.table.item(0, 1).text(), "频准激光")
        self.assertEqual(dlg.table.item(0, 4).text(), "95.0")
        self.assertEqual(dlg.table.item(1, 0).text(), "301655")

        # 触发单击联动信号测试
        linkage_emitted = []
        dlg.stock_linkage_requested.connect(lambda c, n: linkage_emitted.append((c, n)))
        dlg.table.setCurrentCell(0, 0)
        dlg._on_item_clicked(dlg.table.item(0, 0))

        self.assertEqual(len(linkage_emitted), 1)
        self.assertEqual(linkage_emitted[0], ("688826", "频准激光"))
        print("[Test 2] ChannelReversalScanResultDialog 独立窗口渲染与纯粹联动触发成功")


if __name__ == "__main__":
    unittest.main()

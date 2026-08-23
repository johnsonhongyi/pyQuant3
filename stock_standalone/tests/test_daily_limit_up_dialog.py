# -*- coding: utf-8 -*-
"""
tests/test_daily_limit_up_dialog.py — 测试 DailyLimitUpDialog UI 创建与数据刷新
"""

import os
import sys
import unittest
import pandas as pd
from PyQt6.QtWidgets import QApplication

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog, get_limit_up_table_headers

app = QApplication.instance() or QApplication(sys.argv)


class TestDailyLimitUpDialog(unittest.TestCase):

    def test_headers_and_extra_cols(self):
        headers, extra_cols = get_limit_up_table_headers()
        self.assertIn("代码", headers)
        self.assertIn("名称", headers)
        self.assertIn("封流比%", headers)
        self.assertIn("封成比%", headers)
        self.assertIn("DFF", headers)
        self.assertIn("Rank", headers)
        self.assertIn("DFF2", headers)
        self.assertIn("DFF3", headers)
        # 断言末尾两列顺序：倒数第二列为形态与质量，最后一列为所属板块
        self.assertEqual(headers[-1], "所属板块")
        self.assertEqual(headers[-2], "形态与质量")

    def test_dialog_init_and_update(self):
        dialog = DailyLimitUpDialog(parent=None)
        self.assertIsNotNone(dialog)
        self.assertGreater(dialog.table.columnCount(), 15)
        # 断言默认不置顶
        self.assertFalse(dialog.stays_on_top)

        mock_df = pd.DataFrame([
            {
                "code": "600519",
                "name": "贵州茅台",
                "price": 1800.0,
                "percent": 10.0,
                "last_close": 1636.36,
                "dff": 4.5,
                "dff2": 15.0,
                "dff3": 35.0,
                "Rank": 1,
                "category": "白酒"
            }
        ])
        mock_df.set_index("code", drop=False, inplace=True)
        dialog.update_data_payload(mock_df, sh_pct=1.0)
        self.assertGreaterEqual(dialog.table.rowCount(), 1)

        # 测试自适应列宽与板块列宽限制
        dialog.auto_fit_columns()
        self.assertGreater(dialog.table.columnWidth(0), 40)
        last_col = dialog.table.columnCount() - 1
        self.assertLessEqual(dialog.table.columnWidth(last_col), 95) # 板块列限制宽度不超过95px

        # 测试空间龙头点击联动
        dialog.current_top_leader_code = "600519"
        dialog.current_top_leader_name = "贵州茅台"
        emitted_signals = []
        dialog.code_clicked.connect(lambda c, n: emitted_signals.append((c, n)))
        dialog._on_top_leader_clicked()
        self.assertEqual(len(emitted_signals), 1)
        self.assertEqual(emitted_signals[0][0], "600519")

        # 测试上下键与单元格改变联动
        dialog._pending_linkage_row = 0
        dialog._last_emitted_code = ""
        dialog._fire_linkage_debounced()
        self.assertGreaterEqual(len(emitted_signals), 2)
        self.assertEqual(emitted_signals[-1][0], "600519")

        # 测试手动调整列宽持久化保存
        dialog.table.setColumnWidth(0, 77)
        dialog._save_current_column_widths()

        # 测试数值比较与 `--` 占位符排序稳定性
        from ats.ui.styles import NumericTableWidgetItem
        from PyQt6.QtCore import Qt
        it_val = NumericTableWidgetItem("26,740")
        it_val.setData(Qt.ItemDataRole.UserRole, 26740.0)
        it_dash = NumericTableWidgetItem("--")
        it_dash.setData(Qt.ItemDataRole.UserRole, -999999999.0)

        # 降序比较断言: 26740 > --，即 not (it_val < it_dash)，it_dash < it_val 为 True
        self.assertTrue(it_dash < it_val)
        self.assertFalse(it_val < it_dash)

        # 测试切换到极窄模式
        dialog.toggle_narrow_mode(True)
        self.assertTrue(dialog.is_narrow_mode)
        self.assertTrue(dialog.table.isColumnHidden(8)) # 封成比应被隐藏
        self.assertFalse(dialog.table.isColumnHidden(0)) # 代码保留
        self.assertFalse(dialog.table.isColumnHidden(3)) # 涨幅%保留

        # 测试切回宽屏全量模式
        dialog.toggle_narrow_mode(False)
        self.assertFalse(dialog.is_narrow_mode)
        self.assertFalse(dialog.table.isColumnHidden(8))

        dialog.close()


if __name__ == "__main__":
    unittest.main()

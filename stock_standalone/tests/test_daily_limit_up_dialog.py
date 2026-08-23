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
        # 断言表头列顺序：第6列为形态与质量，最后一列为所属板块
        self.assertEqual(headers[-1], "所属板块")
        self.assertEqual(headers[6], "形态与质量")

    def test_dialog_init_and_update(self):
        dialog = DailyLimitUpDialog(parent=None)
        self.assertIsNotNone(dialog)
        # 断言置顶状态与切换互斥
        self.assertIn(dialog.stays_on_top, (True, False))
        dialog.chk_ontop.setChecked(True)
        self.assertTrue(dialog.stays_on_top)
        dialog.chk_ontop.setChecked(False)
        self.assertFalse(dialog.stays_on_top)

        # 断言顶栏存在时间片生命周期直选控件
        self.assertIsNotNone(dialog.combo_time_slice)
        self.assertGreaterEqual(dialog.combo_time_slice.count(), 5)

        mock_records = [
            {
                "code": "688356",
                "name": "键凯科技",
                "price": 107.04,
                "pct": 20.0,
                "consecutive_boards": 1,
                "tier_tag": "💎 冰点反身性龙",
                "seal_amount_wan": 47238.0,
                "seal_to_circ_ratio": 7.26,
                "seal_to_vol_ratio": 134.6,
                "turnover_rate": 5.39,
                "vol_ratio": 1.84,
                "amount_yi": 3.51,
                "is_limit_up": True,
                "is_broken": False,
                "dff": 0.0,
                "rank": 11,
                "dff2": 45.4,
                "dff3": 72.0,
                "rs_val": 19.91,
                "resonance": "同步整理",
                "category": "创新药;医美概念",
                "extra_cols": {}
            }
        ]
        dialog.current_records = mock_records
        dialog.combo_time_slice.setCurrentIndex(0)
        dialog.combo_tier_filter.setCurrentIndex(0)
        dialog.search_edit.clear()
        dialog._apply_filter()
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
        self.assertEqual(emitted_signals[-1][0], "688356")

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
        self.assertTrue(dialog.table.isColumnHidden(9)) # 封成比(索引9)应被隐藏
        self.assertFalse(dialog.table.isColumnHidden(0)) # 代码保留
        self.assertFalse(dialog.table.isColumnHidden(3)) # 涨幅%保留
        self.assertFalse(dialog.table.isColumnHidden(6)) # 形态与质量保留

        # 测试切回宽屏全量模式
        dialog.toggle_narrow_mode(False)
        self.assertFalse(dialog.is_narrow_mode)
        self.assertFalse(dialog.table.isColumnHidden(9))

        dialog.close()


if __name__ == "__main__":
    unittest.main()

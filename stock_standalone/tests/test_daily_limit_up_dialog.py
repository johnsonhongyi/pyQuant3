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
        dialog.combo_time_slice.setCurrentText("⏱️ 全天全时段")
        dialog.combo_tier_filter.setCurrentIndex(0)
        search_widget = getattr(dialog, 'search_edit', getattr(dialog, 'edit_search', None))
        if search_widget:
            search_widget.clear()
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

        # 测试数值比较与 `--` 占位符在升序与降序下的排序稳定性 (有数据永远优先，无数据永远沉底)
        from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTableWidget

        test_table = QTableWidget(4, 1)
        test_table.setSortingEnabled(True)
        it1 = NumericTableWidgetItem("126")
        it1.setData(Qt.ItemDataRole.UserRole, 126.0)
        it2 = NumericTableWidgetItem("--")
        it2.setData(Qt.ItemDataRole.UserRole, None)
        it3 = NumericTableWidgetItem("24,766")
        it3.setData(Qt.ItemDataRole.UserRole, 24766.0)
        it4 = NumericTableWidgetItem("--")
        it4.setData(Qt.ItemDataRole.UserRole, -999999999.0)

        test_table.setItem(0, 0, it1)
        test_table.setItem(1, 0, it2)
        test_table.setItem(2, 0, it3)
        test_table.setItem(3, 0, it4)

        # 1. 升序排序断言 (从小到大，-- 沉底在最后): 126 -> 24766 -> -- -> --
        test_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        asc_results = [test_table.item(r, 0).text() for r in range(4)]
        self.assertEqual(asc_results, ["126", "24,766", "--", "--"])

        # 2. 降序排序断言 (从大到小，-- 沉底在最后): 24766 -> 126 -> -- -> --
        test_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        desc_results = [test_table.item(r, 0).text() for r in range(4)]
        self.assertEqual(desc_results, ["24,766", "126", "--", "--"])

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

        # 测试语音弹窗预警开关切换
        self.assertIsNotNone(dialog.btn_voice_alert)
        orig_voice = dialog.is_voice_alert_enabled
        dialog._toggle_voice_alert()
        self.assertNotEqual(dialog.is_voice_alert_enabled, orig_voice)
        dialog._toggle_voice_alert()
        self.assertEqual(dialog.is_voice_alert_enabled, orig_voice)

        # 测试全市场宏观情绪概览与防猎熔断
        mock_summary = {
            "zt_count": 45,
            "broken_count": 28,
            "seal_rate": 61.6,
            "max_boards": 4,
            "multi_boards_count": 3,
            "avg_seal_circ_ratio": 2.15,
            "total_seal_amount_yi": 38.5,
            "top_leader": "键凯科技 (4板)",
            "top_leader_code": "688356",
            "top_leader_name": "键凯科技",
            "up_cnt": 3200,
            "down_cnt": 1800,
            "panic_down_cnt": 12,
            "limit_down_cnt": 0,
            "sentiment_phase": "⚖️ 均衡博弈期",
            "sentiment_score": 65.0,
            "defense_status": "结构分化",
            "is_avalanche": False
        }
        dialog._update_kpi_display(mock_summary)
        self.assertIn("3200", dialog.lbl_kpi_zt.text())
        self.assertIn("1800", dialog.lbl_kpi_zt.text())

        # 测试通过 locate_stock_in_table 自动高亮居中
        dialog.locate_stock_in_table("688356")
        self.assertEqual(dialog.table.currentRow(), 0)

        dialog.close()

    def test_direction_aware_sorting_comprehensive(self):
        """测试全维度升降序方向感知排序：无论升序还是降序，有数据的排在前面，无数据占位符(--)永远沉底在最下方"""
        from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTableWidget

        # 模拟 5 只股票：2 只涨停有封单数据，1 只有小封单，2 只非涨停无封单(--)
        test_rows = [
            {"code": "000017", "seal_amt": "24,766", "seal_amt_val": 24766.0, "seal_circ": "7.18%", "seal_circ_val": 7.18},
            {"code": "688356", "seal_amt": "--", "seal_amt_val": None, "seal_circ": "--", "seal_circ_val": None},
            {"code": "002172", "seal_amt": "126", "seal_amt_val": 126.0, "seal_circ": "0.02%", "seal_circ_val": 0.02},
            {"code": "920045", "seal_amt": "--", "seal_amt_val": None, "seal_circ": "--", "seal_circ_val": None},
            {"code": "002412", "seal_amt": "3,363", "seal_amt_val": 3363.0, "seal_circ": "0.52%", "seal_circ_val": 0.52},
        ]

        table = QTableWidget(len(test_rows), 2)
        table.setSortingEnabled(False)

        for r_idx, r_data in enumerate(test_rows):
            # Col 0: 封单额
            it_amt = NumericTableWidgetItem(r_data["seal_amt"])
            it_amt.setData(Qt.ItemDataRole.UserRole, r_data["seal_amt_val"])
            table.setItem(r_idx, 0, it_amt)

            # Col 1: 封流比
            it_circ = NumericTableWidgetItem(r_data["seal_circ"])
            it_circ.setData(Qt.ItemDataRole.UserRole, r_data["seal_circ_val"])
            table.setItem(r_idx, 1, it_circ)

        table.setSortingEnabled(True)

        # 1. 封单额升序 (低到高 / 排序最低优先，对应用户图 2): 126 -> 3363 -> 24766 -> -- -> --
        table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        asc_amt = [table.item(r, 0).text() for r in range(len(test_rows))]
        self.assertEqual(asc_amt[:3], ["126", "3,363", "24,766"])
        self.assertEqual(asc_amt[3:], ["--", "--"])

        # 2. 封单额降序 (高到低 / 排序最高优先，对应用户图 3): 24766 -> 3363 -> 126 -> -- -> --
        table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        desc_amt = [table.item(r, 0).text() for r in range(len(test_rows))]
        self.assertEqual(desc_amt[:3], ["24,766", "3,363", "126"])
        self.assertEqual(desc_amt[3:], ["--", "--"])

        # 3. 封流比升序 (低到高): 0.02% -> 0.52% -> 7.18% -> -- -> --
        table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        asc_circ = [table.item(r, 1).text() for r in range(len(test_rows))]
        self.assertEqual(asc_circ[:3], ["0.02%", "0.52%", "7.18%"])
        self.assertEqual(asc_circ[3:], ["--", "--"])

        # 4. 封流比降序 (高到低): 7.18% -> 0.52% -> 0.02% -> -- -> --
        table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        desc_circ = [table.item(r, 1).text() for r in range(len(test_rows))]
        self.assertEqual(desc_circ[:3], ["7.18%", "0.52%", "0.02%"])
        self.assertEqual(desc_circ[3:], ["--", "--"])


if __name__ == "__main__":
    unittest.main()


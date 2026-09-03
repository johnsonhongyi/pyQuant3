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

    def test_kpi_card_interactive_filtering(self):
        """测试天梯顶部 KPI 卡片 (涨停/连板/炸板) 点击点选单选、多选与取消过滤交互"""
        dialog = DailyLimitUpDialog(parent=None)

        mock_records = [
            {
                "code": "002886", "name": "沃特股份", "price": 30.84, "pct": 9.99,
                "consecutive_boards": 4, "tier_tag": "👑 空间高度龙 (4板)",
                "seal_amount_wan": 34721.0, "seal_to_circ_ratio": 5.38, "turnover_rate": 18.42,
                "is_limit_up": True, "is_broken": False, "category": "PEEK材料"
            },
            {
                "code": "601086", "name": "国芳集团", "price": 11.10, "pct": 10.01,
                "consecutive_boards": 3, "tier_tag": "🚀 连板接力 (3板)",
                "seal_amount_wan": 39871.0, "seal_to_circ_ratio": 5.39, "turnover_rate": 0.80,
                "is_limit_up": True, "is_broken": False, "category": "IP经济"
            },
            {
                "code": "000001", "name": "平安银行", "price": 12.00, "pct": 10.00,
                "consecutive_boards": 1, "tier_tag": "🔥 首板",
                "seal_amount_wan": 15000.0, "seal_to_circ_ratio": 1.20, "turnover_rate": 2.50,
                "is_limit_up": True, "is_broken": False, "category": "银行"
            },
            {
                "code": "000002", "name": "万科A", "price": 8.50, "pct": 6.20,
                "consecutive_boards": 1, "tier_tag": "💔 炸板未回封",
                "seal_amount_wan": 0.0, "seal_to_circ_ratio": 0.0, "turnover_rate": 6.80,
                "is_limit_up": False, "is_broken": True, "category": "房地产"
            }
        ]

        dialog.current_records = mock_records
        dialog.combo_time_slice.setCurrentText("⚡ 自动实盘跟随")
        dialog.combo_tier_filter.setCurrentIndex(0)
        dialog._apply_filter()

        # 1. 默认状态：处于【⚡ 自动实盘跟随】
        self.assertEqual(dialog.combo_time_slice.currentText(), "⚡ 自动实盘跟随")
        self.assertEqual(dialog.active_kpi_filters, set())

        # 2. 点击【连板】卡片：自动记忆【⚡ 自动实盘跟随】并平滑切换为【⏱️ 全天全时段】，确保连板标的 100% 完整展示
        dialog._toggle_kpi_filter("LADDER")
        self.assertEqual(dialog.active_kpi_filters, {"LADDER"})
        self.assertEqual(dialog.combo_time_slice.currentText(), "⏱️ 全天全时段")
        self.assertEqual(dialog.table.rowCount(), 2)
        codes_ladder = [dialog.table.item(r, 0).text() for r in range(2)]
        self.assertEqual(set(codes_ladder), {"002886", "601086"})

        # 3. 点击【涨停】卡片 (多选)：仍保持【⏱️ 全天全时段】，显示连板+涨停
        dialog._toggle_kpi_filter("ZT")
        self.assertEqual(dialog.active_kpi_filters, {"LADDER", "ZT"})
        self.assertEqual(dialog.combo_time_slice.currentText(), "⏱️ 全天全时段")
        self.assertEqual(dialog.table.rowCount(), 3)

        # 4. 全部取消 KPI 过滤：自动平滑恢复先前记忆的【⚡ 自动实盘跟随】！
        dialog._toggle_kpi_filter("LADDER")
        dialog._toggle_kpi_filter("ZT")
        self.assertEqual(dialog.active_kpi_filters, set())
        self.assertEqual(dialog.combo_time_slice.currentText(), "⚡ 自动实盘跟随")


    def test_favorite_priority_pinning_and_toggle(self):
        """测试天梯重点关注标的优先置顶显示、⭐ 徽章、金色高亮及切换联动"""
        from global_favorites import GlobalFavoriteManager
        from PyQt6.QtGui import QColor
        fav_mgr = GlobalFavoriteManager()

        mock_records = [
            {
                "code": "002886", "name": "沃特股份", "price": 30.84, "pct": 9.99,
                "consecutive_boards": 4, "tier_tag": "👑 空间高度龙 (4板)",
                "seal_amount_wan": 34721.0, "seal_to_circ_ratio": 5.38, "turnover_rate": 18.42,
                "is_limit_up": True, "is_broken": False, "category": "PEEK材料"
            },
            {
                "code": "601086", "name": "国芳集团", "price": 11.10, "pct": 10.01,
                "consecutive_boards": 3, "tier_tag": "🚀 连板接力 (3板)",
                "seal_amount_wan": 39871.0, "seal_to_circ_ratio": 5.39, "turnover_rate": 0.80,
                "is_limit_up": True, "is_broken": False, "category": "IP经济"
            },
            {
                "code": "000001", "name": "平安银行", "price": 12.00, "pct": 10.00,
                "consecutive_boards": 1, "tier_tag": "🔥 首板",
                "seal_amount_wan": 15000.0, "seal_to_circ_ratio": 1.20, "turnover_rate": 2.50,
                "is_limit_up": True, "is_broken": False, "category": "银行"
            }
        ]

        dialog = DailyLimitUpDialog(parent=None)
        dialog.current_records = mock_records
        dialog.combo_time_slice.setCurrentText("⏱️ 全天全时段")
        dialog.combo_tier_filter.setCurrentIndex(0)
        # 显式设定按连板数降序排序：沃特股份 (4板) > 国芳集团 (3板) > 平安银行 (1板)
        dialog.sort_level1_col = 4
        dialog.sort_level1_asc = False

        # 确保初始未关注 000001
        fav_mgr.remove_favorite_stock("000001")

        try:
            # 1. 初始渲染：002886 (4板) > 601086 (3板) > 000001 (1板)
            dialog._apply_filter()
            self.assertEqual(dialog.table.rowCount(), 3)
            self.assertEqual(dialog.table.item(0, 0).text(), "002886")
            self.assertEqual(dialog.table.item(1, 0).text(), "601086")
            self.assertEqual(dialog.table.item(2, 0).text(), "000001")
            self.assertFalse(dialog.table.item(2, 1).text().startswith("⭐"))

            # 2. 将原本末位的 000001 设为重点关注
            fav_mgr.add_favorite_stock("000001")
            dialog._apply_filter()

            # 3. 断言 000001 跃升至第一行 (第 0 行) 绝对置顶 (即使它只有 1 板)
            self.assertEqual(dialog.table.item(0, 0).text(), "000001")
            self.assertTrue(dialog.table.item(0, 1).text().startswith("⭐ 平安银行"))
            # 非置顶区依然保持原有连板数排序：沃特股份 (4板) > 国芳集团 (3板)
            self.assertEqual(dialog.table.item(1, 0).text(), "002886")
            self.assertEqual(dialog.table.item(2, 0).text(), "601086")

            # 断言单元格 is_pinned 置顶属性与金色高亮
            item_code = dialog.table.item(0, 0)
            item_name = dialog.table.item(0, 1)
            self.assertTrue(getattr(item_code, "is_pinned", False))
            self.assertEqual(getattr(item_code, "pin_rank", 999), 0)
            self.assertEqual(item_code.foreground().color().name().lower(), "#ffd700")
            self.assertEqual(item_name.foreground().color().name().lower(), "#ffd700")
            self.assertIn("⭐关注: 1", dialog.lbl_status.text())

            # 4. 切换排序列为涨幅降序，000001 依然永远置顶在第一行
            dialog.sort_level1_col = 3  # 涨幅列
            dialog.sort_level1_asc = False
            dialog._apply_filter()
            self.assertEqual(dialog.table.item(0, 0).text(), "000001")
            # 非置顶区按涨幅降序：国芳集团 (10.01%) > 沃特股份 (9.99%)
            self.assertEqual(dialog.table.item(1, 0).text(), "601086")
            self.assertEqual(dialog.table.item(2, 0).text(), "002886")

            # 5. 取消重点关注后，恢复正常按涨幅降序排序：国芳集团 (10.01%) > 平安银行 (10.00%) > 沃特股份 (9.99%)
            fav_mgr.remove_favorite_stock("000001")
            dialog._apply_filter()
            self.assertEqual(dialog.table.item(0, 0).text(), "601086")
            self.assertEqual(dialog.table.item(1, 0).text(), "000001")
            self.assertEqual(dialog.table.item(2, 0).text(), "002886")
            self.assertFalse(dialog.table.item(1, 1).text().startswith("⭐"))
            self.assertFalse(getattr(dialog.table.item(1, 0), "is_pinned", False))
            self.assertNotIn("⭐关注:", dialog.lbl_status.text())

        finally:
            fav_mgr.remove_favorite_stock("000001")
            dialog.close()


if __name__ == "__main__":
    unittest.main()


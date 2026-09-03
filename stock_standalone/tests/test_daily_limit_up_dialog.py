# -*- coding: utf-8 -*-
"""
tests/test_daily_limit_up_dialog.py — 测试 DailyLimitUpDialog UI 创建与数据刷新
"""

import os
import sys
import unittest
import time
import pandas as pd
from PyQt6.QtWidgets import QApplication

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog, get_limit_up_table_headers
from ats.limit_up_engine import LimitUpEngine

app = QApplication.instance() or QApplication(sys.argv)


class TestDailyLimitUpDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from global_favorites import GlobalFavoriteManager
        cls._fav_mgr = GlobalFavoriteManager()
        with cls._fav_mgr._lock:
            cls._orig_fav_stocks = set(cls._fav_mgr.favorite_stocks)
            cls._orig_fav_dates = dict(cls._fav_mgr.favorite_stocks_dates)

    @classmethod
    def tearDownClass(cls):
        from global_favorites import GlobalFavoriteManager
        fav_mgr = GlobalFavoriteManager()
        with fav_mgr._lock:
            fav_mgr.favorite_stocks = set(cls._orig_fav_stocks)
            fav_mgr.favorite_stocks_dates = dict(cls._orig_fav_dates)
            fav_mgr._version += 1
        fav_mgr.save_to_config()

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

    def test_daily_limit_up_dual_acceleration_features(self):
        """验证天梯【开盘即最低光脚加速】、【跳空缺口加速】及【双加速结构】在连板天梯中的优先置顶与视觉高亮"""
        dialog = DailyLimitUpDialog()

        # 构造3只同为1板的标的
        records = [
            {
                "code": "000001", "name": "常规首板", "price": 11.00, "last_close": 10.00,
                "open": 9.90, "high": 11.00, "low": 9.70, "pct": 10.00, "consecutive_boards": 1,
                "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 2.0, "seal_amount_wan": 1000.0,
                "tier_tag": "🔥 换手首板", "momentum_score": 80.0
            },
            {
                "code": "000002", "name": "光脚加速首板", "price": 11.00, "last_close": 10.00,
                "open": 10.02, "high": 11.00, "low": 10.02, "pct": 10.00, "consecutive_boards": 1,
                "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 2.0, "seal_amount_wan": 1000.0,
                "tier_tag": "🔥 换手首板", "momentum_score": 85.0
            },
            {
                "code": "000003", "name": "双加速首板", "price": 11.00, "last_close": 10.00,
                "open": 10.30, "high": 11.00, "low": 10.30, "pct": 10.00, "consecutive_boards": 1,
                "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 2.0, "seal_amount_wan": 1000.0,
                "tier_tag": "🔥 换手首板", "momentum_score": 90.0
            }
        ]

        # 通过 limit_up_engine 进行全流程计算赋予加速标签与提权
        from ats.limit_up_engine import LimitUpEngine
        engine = LimitUpEngine.get_instance()
        # 模拟由 scan_limit_up_records_from_df 计算得到的加速结构
        for r in records:
            open_p = r["open"]
            low_p = r["low"]
            last_c = r["last_close"]
            low_diff_pct = round((open_p - low_p) / open_p * 100.0, 3)
            is_open_low = (low_p >= open_p - 0.015 or low_diff_pct <= 0.15)
            open_jump = (open_p - last_c) / last_c * 100.0
            is_gap = (open_jump >= 0.8 and low_p > last_c)
            is_dual = (is_open_low and is_gap)
            r["is_open_low_accel"] = is_open_low
            r["is_gap_accel"] = is_gap
            r["is_dual_accel"] = is_dual
            r["low_diff_pct"] = low_diff_pct
            r["accel_tag"] = "👑双加速" if is_dual else ("⚡光脚加速" if is_open_low else "")
            r["pattern_desc"] = f"{r['accel_tag']}|动能{r['momentum_score']:.0f}分" if r["accel_tag"] else f"动能{r['momentum_score']:.0f}分"

        dialog.current_records = records
        dialog.combo_time_slice.setCurrentText("⏱️ 全天全时段")
        dialog.combo_tier_filter.setCurrentIndex(0)
        dialog.sort_level1_col = 4  # 连板数列
        dialog.sort_level1_asc = False
        # 隔离自选股：创建一个独立的虚拟管理器，绝不污染全局单例与生产磁盘文件
        class MockFavManager:
            def get_favorite_stocks(self):
                return set()
        dialog.fav_manager = MockFavManager()
        try:
            # 1. 默认排序：同为1板情况下，双加速标的 000003 必须绝对优先排在第一位！
            dialog._apply_filter()
            self.assertEqual(dialog.table.rowCount(), 3)
            self.assertEqual(dialog.table.item(0, 0).text(), "000003", f"双加速标的应排第1位，实际为: {dialog.table.item(0, 0).text()}")
            self.assertEqual(dialog.table.item(1, 0).text(), "000002", f"光脚加速标的应排第2位，实际为: {dialog.table.item(1, 0).text()}")
            self.assertEqual(dialog.table.item(2, 0).text(), "000001", f"常规标的应排第3位，实际为: {dialog.table.item(2, 0).text()}")

            # 2. 验证视觉渲染：第 6 列形态与质量应包含 👑双加速 且字体呈现金色 #ffd700
            item_desc = dialog.table.item(0, 6)
            self.assertIn("👑双加速", item_desc.text())
            self.assertEqual(item_desc.foreground().color().name().lower(), "#ffd700")

            # 3. 验证 ToolTip 包含双加速深度透视
            tooltip = item_desc.toolTip()
            self.assertIn("👑 加速结构: 👑双加速", tooltip)
            self.assertIn("双加速: 跳空高开+开盘即最低", tooltip)
            self.assertIn("下影差异: 0.00%", tooltip)

            # 4. 👑 核心断言：测试用户截图场景【同类型后在对比评分的能力】
            # 构造 4 只股票：
            # A: 300830 金现代 (缺口加速, 99分)
            # B: 002787 华浪控股 (双加速, 99分)
            # C: 301489 思泉新材 (缺口加速, 98分)
            # D: 605068 明新旭腾 (双加速, 98分)
            records_type_score = [
                {
                    "code": "300830", "name": "金现代", "price": 10.09, "last_close": 8.41,
                    "open": 8.50, "high": 10.09, "low": 8.45, "pct": 19.98, "consecutive_boards": 1,
                    "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 6.73, "seal_amount_wan": 22872.0,
                    "tier_tag": "💎 冰点反身性龙", "momentum_score": 99.0,
                    "is_dual_accel": False, "is_gap_accel": True, "is_open_low_accel": False, "low_diff_pct": 0.10,
                    "accel_tag": "🚀缺口加速", "pattern_desc": "🚀缺口加速|💎 反身性龙头(99分)"
                },
                {
                    "code": "002787", "name": "华浪控股", "price": 24.40, "last_close": 22.18,
                    "open": 22.50, "high": 24.40, "low": 22.50, "pct": 10.01, "consecutive_boards": 1,
                    "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 4.22, "seal_amount_wan": 25530.0,
                    "tier_tag": "💎 冰点反身性龙", "momentum_score": 99.0,
                    "is_dual_accel": True, "is_gap_accel": True, "is_open_low_accel": True, "low_diff_pct": 0.00,
                    "accel_tag": "👑双加速", "pattern_desc": "👑双加速|💎 反身性龙头(99分)"
                },
                {
                    "code": "301489", "name": "思泉新材", "price": 140.40, "last_close": 117.00,
                    "open": 119.00, "high": 140.40, "low": 118.00, "pct": 20.00, "consecutive_boards": 1,
                    "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 3.55, "seal_amount_wan": 34662.0,
                    "tier_tag": "💎 冰点反身性龙", "momentum_score": 98.0,
                    "is_dual_accel": False, "is_gap_accel": True, "is_open_low_accel": False, "low_diff_pct": 0.12,
                    "accel_tag": "🚀缺口加速", "pattern_desc": "🚀缺口加速|💎 反身性龙头(98分)"
                },
                {
                    "code": "605068", "name": "明新旭腾", "price": 23.50, "last_close": 21.36,
                    "open": 21.80, "high": 23.50, "low": 21.80, "pct": 10.02, "consecutive_boards": 1,
                    "is_limit_up": True, "is_broken": False, "seal_to_circ_ratio": 1.38, "seal_amount_wan": 5255.0,
                    "tier_tag": "💎 冰点反身性龙", "momentum_score": 98.0,
                    "is_dual_accel": True, "is_gap_accel": True, "is_open_low_accel": True, "low_diff_pct": 0.00,
                    "accel_tag": "👑双加速", "pattern_desc": "👑双加速|💎 反身性龙头(98分)"
                }
            ]
            dialog.current_records = records_type_score
            # 切换为按【第6列: 形态与质量】降序排序
            dialog.sort_level1_col = 6
            dialog.sort_level1_asc = False
            dialog._sort_col = None
            dialog._apply_filter()

            self.assertEqual(dialog.table.rowCount(), 4)
            # 必须严格先按加速类型分层，同类型内部对比评分：
            # 第1位: 双加速 99分 (002787 华浪控股)
            self.assertEqual(dialog.table.item(0, 0).text(), "002787", f"第1位应为双加速99分，实际为: {dialog.table.item(0, 0).text()}")
            # 第2位: 双加速 98分 (605068 明新旭腾) -> 绝对不能被99分的缺口加速插队！
            self.assertEqual(dialog.table.item(1, 0).text(), "605068", f"第2位应为双加速98分，实际为: {dialog.table.item(1, 0).text()}")
            # 第3位: 缺口加速 99分 (300830 金现代)
            self.assertEqual(dialog.table.item(2, 0).text(), "300830", f"第3位应为缺口加速99分，实际为: {dialog.table.item(2, 0).text()}")
            # 第4位: 缺口加速 98分 (301489 思泉新材)
            self.assertEqual(dialog.table.item(3, 0).text(), "301489", f"第4位应为缺口加速98分，实际为: {dialog.table.item(3, 0).text()}")

        finally:
            dialog.close()

    def test_daily_limit_up_multi_day_gradient_tiers_and_launch_accel(self):
        """【专项测试】验证动能评分分层梯度体系 (Gradient Tier) 与多日强势底蕴感知：
        实战检验：4板国芳集团 > 3板集泰股份 > 2板大晟文化 > 1板三安光电(突破双加速) > 1板嘉美包装(普通首板)
        彻底根治'每日都在同一个尺度'以及'1板98分反超2板94分'的倒挂缺陷！
        """
        engine = LimitUpEngine.get_instance()
        
        # 构造多日历史记录字典模拟近 5 日涨停底蕴
        today_str = time.strftime("%Y-%m-%d")
        with engine._cache_lock:
            old_history = dict(engine._history_daily_records)
            past_dates = [d for d in sorted(old_history.keys()) if d != today_str]
            last_date = past_dates[-1] if past_dates else "2026-09-02"
            engine._history_daily_records[last_date] = [
                {"code": "601086", "is_limit_up": True, "consecutive_boards": 3},
                {"code": "002909", "is_limit_up": True, "consecutive_boards": 2},
                {"code": "600892", "is_limit_up": True, "consecutive_boards": 1},
            ]

        try:

            # 构造当日策略 DataFrame (包含 5 种梯度的真实标的)
            data = {
                "name": ["国芳集团", "集泰股份", "大晟文化", "三安光电", "嘉美包装"],
                "trade": [6.60, 8.80, 11.20, 13.50, 4.50],
                "close": [6.60, 8.80, 11.20, 13.50, 4.50],
                "price": [6.60, 8.80, 11.20, 13.50, 4.50],
                "open": [6.30, 8.40, 10.70, 12.80, 4.30],
                "low": [6.30, 8.40, 10.70, 12.80, 4.15],
                "high": [6.60, 8.80, 11.20, 13.50, 4.50],
                "last_close": [6.00, 8.00, 10.18, 12.27, 4.09],
                "percent": [10.0, 10.0, 10.02, 10.02, 10.02],
                "pct": [10.0, 10.0, 10.02, 10.02, 10.02],
                "dff": [10.0, 10.0, 10.0, 10.0, 10.0],
                "dff2": [20.0, 20.0, 20.0, 10.0, 10.0],
                "dff3": [32.0, 32.0, 20.0, 10.0, 10.0],
                "lasth1d": [6.00, 8.00, 10.18, 12.27, 4.09],
                "lasth2d": [5.50, 7.30, 9.30, 12.10, 4.05],
                "lasth3d": [5.00, 6.70, 8.50, 12.00, 4.00],
                "hmax": [6.00, 8.00, 10.18, 12.27, 4.09],
                "vol": [100000, 100000, 100000, 100000, 100000],
                "amount": [66000000, 88000000, 112000000, 135000000, 45000000],
                "turnover": [5.0, 6.0, 7.0, 4.0, 3.0],
                "bid1": [6.60, 8.80, 11.20, 13.50, 4.50],
                "b1_v": [50000, 40000, 30000, 80000, 10000],
            }
            idx = ["601086", "002909", "600892", "600703", "002969"]
            test_df = pd.DataFrame(data, index=idx)

            # 扫描并计算带有分层梯度的实时记录
            records = engine.scan_limit_up_records_from_df(test_df, fetch_l2_quotes=False)
            rec_map = {r["code"]: r for r in records}

            # 1. 验证各标的的分层梯度动能评分
            score_gf = rec_map["601086"]["momentum_score"] # 国芳集团 (4板总龙)
            score_jt = rec_map["002909"]["momentum_score"] # 集泰股份 (3板接力)
            score_ds = rec_map["600892"]["momentum_score"] # 大晟文化 (2板连板加速)
            score_sa = rec_map["600703"]["momentum_score"] # 三安光电 (1板突破双加速)
            score_jm = rec_map["002969"]["momentum_score"] # 嘉美包装 (1板常规首板)

            print(f"\n[实战梯度评分验证] 国芳集团(4板): {score_gf} | 集泰股份(3板): {score_jt} | 大晟文化(2板): {score_ds} | 三安光电(1板双加速): {score_sa} | 嘉美包装(1板普通): {score_jm}")

            # 👑 核心断言 1: 空间总龙稳居第 1 梯度 (>= 98 分)
            self.assertGreaterEqual(score_gf, 98.0)
            # 👑 核心断言 2: 3板接力紧随其后且低于总龙
            self.assertGreaterEqual(score_jt, 95.0)
            self.assertGreater(score_gf, score_jt)
            # 👑 核心断言 3: 2板启动加速得分 >= 93.0，且低于 3板
            self.assertGreaterEqual(score_ds, 93.0)
            self.assertGreater(score_jt, score_ds)
            # 👑 核心断言 4 (彻底消灭倒挂): 2板得分严格高于 1板首板！(绝不允许 1板98分压制 2板94分)
            self.assertGreater(score_ds, score_sa, f"2板大晟文化({score_ds}分) 必须严格高于 1板双加速三安光电({score_sa}分)")
            # 👑 核心断言 5 (启动加速梯度): 1板突破启动加速标的明显高出普通首板
            self.assertGreater(score_sa, score_jm, f"1板突破加速三安光电({score_sa}分) 必须严格高于 普通首板嘉美包装({score_jm}分)")

            # 2. 验证多日聚合字段完备性
            self.assertIn("zt_cnt_3d", rec_map["601086"])
            self.assertIn("zt_cnt_5d", rec_map["601086"])
            self.assertIn("n_days_m_boards", rec_map["601086"])
            self.assertTrue(rec_map["600892"]["is_launch_accel"], "2板大晟文化应被标记为 is_launch_accel=True")

            # 3. 验证天梯表格加载后的最终多级排序顺序
            dialog = DailyLimitUpDialog()
            try:
                class MockFavManager:
                    def get_favorite_stocks(self): return set()
                    def is_favorite_stock(self, code): return False
                dialog.fav_manager = MockFavManager()
                dialog.combo_time_slice.setCurrentIndex(1)
                dialog.active_time_slice = "⏱️ 全天全时段"
                dialog.current_records = records
                dialog._apply_filter()

                # 严格降序梯队检验：第0行=国芳集团, 第1行=集泰股份, 第2行=大晟文化, 第3行=三安光电, 第4行=嘉美包装
                self.assertEqual(dialog.table.item(0, 0).text(), "601086", "第1位必须为4板空间总龙国芳集团")
                self.assertEqual(dialog.table.item(1, 0).text(), "002909", "第2位必须为3板集泰股份")
                self.assertEqual(dialog.table.item(2, 0).text(), "600892", "第3位必须为2板大晟文化")
                self.assertEqual(dialog.table.item(3, 0).text(), "600703", "第4位必须为1板双加速三安光电")
            finally:
                dialog.close()
        finally:
            with engine._cache_lock:
                engine._history_daily_records = old_history

    def test_daily_limit_up_alert_round_robin_rotation(self):
        """【专项测试】验证每日连板天梯环形游标轮动 (Round-Robin) 与单股冷却防刷屏机制"""
        from ats.alert_notifier import AlertNotifier

        dialog = DailyLimitUpDialog()
        try:
            records = [
                {
                    "code": "601086", "name": "国芳集团", "consecutive_boards": 4,
                    "momentum_score": 100.0, "tier_tag": "👑空间总龙", "pattern_desc": "连板主升",
                    "pct": 10.0, "is_broken": False, "is_dual_accel": False
                },
                {
                    "code": "002909", "name": "集泰股份", "consecutive_boards": 3,
                    "momentum_score": 98.0, "tier_tag": "🚀连板接力", "pattern_desc": "换手接力",
                    "pct": 10.0, "is_broken": False, "is_dual_accel": False
                },
                {
                    "code": "600892", "name": "大晟文化", "consecutive_boards": 2,
                    "momentum_score": 95.0, "tier_tag": "⚡启动加速", "pattern_desc": "光脚加速",
                    "pct": 10.0, "is_broken": False, "is_dual_accel": False
                }
            ]

            dialog._ladder_rotation_cursor = 0
            dialog._notify_slice_cd = {}

            notifier = AlertNotifier.get_instance()
            notifier.clear_queue()
            notifier._stock_alert_state.clear()
            dispatched = []
            notifier._enqueue_notification_item = lambda item: dispatched.append(item)

            # 1. 模拟第 1 次触发：必须推送第 1 只 (国芳集团)，游标推进到 1
            dialog._check_and_notify_ladder_highlights(records)
            self.assertEqual(len(dispatched), 1)
            self.assertEqual(dispatched[-1]["code"], "601086")
            self.assertEqual(dispatched[-1]["source"], "每日天梯")
            self.assertEqual(dialog._ladder_rotation_cursor, 1)

            # 2. 模拟第 2 次触发：必须轮换推送第 2 只 (集泰股份)，游标推进到 2
            dialog._check_and_notify_ladder_highlights(records)
            self.assertEqual(len(dispatched), 2)
            self.assertEqual(dispatched[-1]["code"], "002909")
            self.assertEqual(dialog._ladder_rotation_cursor, 2)

            # 3. 模拟第 3 次触发：必须轮换推送第 3 只 (大晟文化)，游标环形回到 0
            dialog._check_and_notify_ladder_highlights(records)
            self.assertEqual(len(dispatched), 3)
            self.assertEqual(dispatched[-1]["code"], "600892")
            self.assertEqual(dialog._ladder_rotation_cursor, 0)

            # 4. 模拟第 4 次触发：全部在冷却期内，静默跳过
            dialog._check_and_notify_ladder_highlights(records)
            self.assertEqual(len(dispatched), 3)

            # 验证 3 次推送依次轮换 3 只不同标的
            codes_sent = [it["code"] for it in dispatched]
            self.assertEqual(codes_sent, ["601086", "002909", "600892"])

        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()



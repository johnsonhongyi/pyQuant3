# -*- coding: utf-8 -*-
"""
tests/test_capital_dragon_panel_integration.py — CapitalDragonPanel 界面与数据全链路集成测试
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.ui.capital_dragon_panel import CapitalDragonPanel
from ats.capital_dragon_engine import CapitalDragonEngine


class TestCapitalDragonPanelIntegration(unittest.TestCase):

    def setUp(self):
        self.panel = CapitalDragonPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_panel_initial_state(self):
        """测试初始状态与组件布局完整性"""
        self.assertEqual(len(self.panel.sector_card_widgets), 3)
        self.assertEqual(self.panel.table.columnCount(), len(self.panel.headers))
        self.assertIn("代码", self.panel.headers)
        self.assertIn("龙头角色", self.panel.headers)
        self.assertIn("虚拟量比", self.panel.headers)
        self.assertIn("成交额(亿)", self.panel.headers)

    def test_update_payload_and_rendering(self):
        """测试数据注入后 3 大主线卡片与真龙表格的渲染"""
        mock_data = {
            # 1. 空间龙
            "600108": {
                "name": "亚盛集团", "close": 3.85, "percent": 10.0, "amount": 9.5e8,
                "category": "农业种植;西部大开发", "dff": 2.5, "dff2": 6.8, "dff3": 12.0, "ma20d": 3.2
            },
            # 2. 趋势容量中军
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            # 3. 主线先锋
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            },
            # 4. 助攻
            "300037": {
                "name": "新宙邦", "close": 38.2, "percent": 5.6, "amount": 7.2e8,
                "category": "固态电池;氟化工", "dff": 0.8, "dff2": 3.2, "dff3": 6.0, "ma20d": 35.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')

        # 触发面板更新
        self.panel.update_payload(df_mock, sh_pct=0.8)

        # 验证表格行数大于 0
        self.assertGreater(self.panel.table.rowCount(), 0)

        # 验证顶部第 1 个卡片被正确渲染
        card0 = self.panel.sector_card_widgets[0]
        self.assertFalse(card0["frame"].isHidden())
        self.assertIn("固态电池", card0["title"].text())

        # 验证表格第一列包含识别出的真龙代码
        table_codes = [self.panel.table.item(r, 0).text() for r in range(self.panel.table.rowCount())]
        self.assertIn("300750", table_codes)
        self.assertIn("002812", table_codes)

        # 验证虚拟量比列（第 6 列）
        vr_col_idx = self.panel.headers.index("虚拟量比")
        self.assertEqual(vr_col_idx, 6)
        vr_item = self.panel.table.item(0, vr_col_idx)
        self.assertIsNotNone(vr_item)
        self.assertTrue(vr_item.text().endswith("x"))

        # 验证卡片描述中显示量比
        self.assertIn("量比:", card0["desc"].text())

        # 验证搜索框即时过滤
        self.panel.search_input.setText("宁德")
        filtered_rows = self.panel.table.rowCount()
        self.assertEqual(filtered_rows, 1)
        self.assertEqual(self.panel.table.item(0, 1).text(), "宁德时代")

        # 还原搜索
        self.panel.search_input.setText("")
        self.assertGreater(self.panel.table.rowCount(), 1)

    def test_card_click_and_pioneer_linkage(self):
        """测试点击板块卡片打开板块明细，以及点击领涨先锋触发联动"""
        mock_data = {
            "300750": {
                "name": "宁德时代", "close": 265.0, "percent": 5.2, "amount": 4.8e9,
                "category": "固态电池;锂电池", "dff": 1.8, "dff2": 5.2, "dff3": 9.5, "ma20d": 240.0
            },
            "002812": {
                "name": "恩捷股份", "close": 42.5, "percent": 9.98, "amount": 1.5e9,
                "category": "固态电池;锂电池", "dff": 1.2, "dff2": 4.0, "dff3": 7.5, "ma20d": 38.0
            },
            "300037": {
                "name": "新宙邦", "close": 38.2, "percent": 5.6, "amount": 7.2e8,
                "category": "固态电池;氟化工", "dff": 0.8, "dff2": 3.2, "dff3": 6.0, "ma20d": 35.0
            }
        }
        df_mock = pd.DataFrame.from_dict(mock_data, orient='index')
        self.panel.update_payload(df_mock, sh_pct=0.8)

        # 1. 模拟主窗口记录打开板块回调
        opened_sectors = []
        linked_stocks = []
        double_clicked_stocks = []

        class MockMainWindow:
            def on_sector_clicked(self, sec_name, member_codes=None):
                opened_sectors.append((sec_name, member_codes))
            def link_stock(self, code, name):
                linked_stocks.append((code, name))
            def on_stock_clicked(self, code, name, extra):
                double_clicked_stocks.append((code, name))

        mock_mw = MockMainWindow()
        self.panel.main_window = mock_mw

        card0 = self.panel.sector_card_widgets[0]["card_widget"]
        self.assertIsNotNone(card0)
        self.assertEqual(card0.sector_name, "固态电池")

        # 2. 模拟卡片点击 -> 触发打开板块详情
        card0._on_card_clicked()
        self.assertEqual(len(opened_sectors), 1)
        self.assertEqual(opened_sectors[0][0], "固态电池")
        # 验证从 df_mock 自动提取并透传了属于固态电池的成分股代码
        self.assertIn("300750", opened_sectors[0][1])
        self.assertIn("002812", opened_sectors[0][1])

        # 3. 模拟先锋单击 -> 触发个股联动
        card0._on_leader_clicked()
        self.assertEqual(len(linked_stocks), 1)
        self.assertEqual(linked_stocks[0][0], card0.leader_code)

        # 4. 模拟先锋双击 -> 触发打开 SBC
        card0._on_leader_double_clicked()
        self.assertEqual(len(double_clicked_stocks), 1)
        self.assertEqual(double_clicked_stocks[0][0], card0.leader_code)

    def test_sector_detail_dialog_strong_stocks_marking_and_filter(self):
        """测试板块明细弹窗标记强势股与【仅看强势股】按钮筛选"""
        from ats.ui.sector_detail_dialog import ATSSectorDetailDialog

        sample_rows = [
            {"code": "300750", "name": "宁德时代", "score": 98.0, "type": "🛡️ 趋势容量中军", "pct": 5.2, "dff": 1.8, "is_strong": True},
            {"code": "002812", "name": "恩捷股份", "score": 96.0, "type": "🔥 强势涨停", "pct": 9.98, "dff": 1.2, "is_strong": True},
            {"code": "000001", "name": "平安银行", "score": 30.0, "type": "跟随", "pct": -0.5, "dff": -0.2, "is_strong": False}
        ]

        dlg = ATSSectorDetailDialog("固态电池", member_codes=["300750", "002812", "000001"])
        dlg._on_worker_finished(sample_rows, 85.0, "恩捷股份 (002812) [+9.98%]", {"count": 3, "strong_count": 2})

        # 验证默认展示 3 只
        self.assertEqual(dlg.table.rowCount(), 3)
        # 验证宁德时代与恩捷股份被标记为强势股并排在前面
        item_top0 = dlg.table.item(0, 1)
        self.assertTrue(item_top0.font().bold())

        # 开启【仅看强势股】
        dlg.btn_strong_only.setChecked(True)
        dlg._toggle_strong_only()

        # 验证过滤后仅剩 2 只强势股
        self.assertEqual(dlg.table.rowCount(), 2)
        codes = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount())]
        self.assertIn("300750", codes)
        self.assertIn("002812", codes)
        self.assertNotIn("000001", codes)

        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()

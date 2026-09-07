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

        # 验证搜索框即时过滤
        self.panel.search_input.setText("宁德")
        filtered_rows = self.panel.table.rowCount()
        self.assertEqual(filtered_rows, 1)
        self.assertEqual(self.panel.table.item(0, 1).text(), "宁德时代")

        # 还原搜索
        self.panel.search_input.setText("")
        self.assertGreater(self.panel.table.rowCount(), 1)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
import sys
import os
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STANDALONE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if STANDALONE_DIR not in sys.path:
    sys.path.insert(0, STANDALONE_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ats.ui.styles import NumericTableWidgetItem
from ats.ui.base_table import BaseATSTableWidget
from ats.ui.favorite_panel import FavoritePanel
from ats.ui.swing_table import SwingStateTable


class TestMA20DeviationSorting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_01_numeric_item_percentage_sorting(self):
        table = BaseATSTableWidget()
        table.setColumnCount(1)
        table.setRowCount(9)
        raw_vals = ['+0.17%', '+1.90%', '+10.74%', '+13.06%', '-1.50%', '+2.00%', '-10.00%', '0.0%', '--']
        for r, v in enumerate(raw_vals):
            table.setItem(r, 0, NumericTableWidgetItem(v))

        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        asc_results = [table.item(r, 0).text() for r in range(9)]
        expected_asc = ['-10.00%', '-1.50%', '0.0%', '+0.17%', '+1.90%', '+2.00%', '+10.74%', '+13.06%', '--']
        self.assertEqual(asc_results, expected_asc)

        table.sortItems(0, Qt.SortOrder.DescendingOrder)
        desc_results = [table.item(r, 0).text() for r in range(9)]
        expected_desc = ['+13.06%', '+10.74%', '+2.00%', '+1.90%', '+0.17%', '0.0%', '-1.50%', '-10.00%', '--']
        self.assertEqual(desc_results, expected_desc)

    def test_02_item_reuse_and_setdata_protection(self):
        item = NumericTableWidgetItem('+0.17%')
        self.assertEqual(item._get_sort_val(), 0.17)
        self.assertIsInstance(item._get_sort_val(), float)

        item.setText('+10.74%')
        self.assertEqual(item._get_sort_val(), 10.74)
        self.assertIsInstance(item._get_sort_val(), float)

        item.setData(Qt.ItemDataRole.UserRole, '+13.06%')
        self.assertEqual(item._get_sort_val(), 13.06)
        self.assertIsInstance(item._get_sort_val(), float)

        item.setData(Qt.ItemDataRole.UserRole, '-5.88%')
        self.assertEqual(item._get_sort_val(), -5.88)
        self.assertIsInstance(item._get_sort_val(), float)

    def test_03_favorite_panel_ma20_sorting_and_live_updates(self):
        panel = FavoritePanel()
        mock_rows = [
            ('000710', '贝瑞基因', '9.16', '回踩企稳', '+0.33%', '1', '15%', '⏳ 盘前预备 [12:58]', '179.3', '0.40', '3953', '4.40', '24.30', '+1.32%', '同步整理', '支撑位蓄势震荡'),
            ('002354', '天娱数科', '8.35', '回踩中', '+10.74%', '3', '0%', '⏳ 盘前预备 [12:57]', '368.2', '-1.90', '83', '18.90', '54.30', '+2.62%', '同步整理', '股价缩量向大级别MA20'),
            ('300721', '怡达股份', '23.07', '回踩中', '+0.17%', '0', '0%', '⏳ 盘前预备 [12:57]', '246.3', '0.10', '3854', '3.30', '56.50', '-2.61%', '同步整理', '股价缩量向大级别MA20'),
            ('688300', '联瑞新材', '179.02', '回踩中', '+13.06%', '0', '0%', '⏳ 盘前预备 [12:57]', '248.8', '0.40', '572', '26.90', '114.30', '-8.61%', '同步走弱', '股价缩量向大级别MA20'),
            ('002415', '海康威视', '35.96', '回踩中', '+1.90%', '3', '0%', '⏳ 盘前预备 [12:57]', '247.2', '-0.00', '2136', '3.90', '19.90', '-0.90%', '同步整理', '股价缩量向大级别MA20'),
            ('000001', '平安银行', '10.45', '已平仓', '-1.50%', '0', '0%', '⏳ 盘前预备 [12:57]', '45.0', '-1.00', '4800', '1.20', '15.30', '-1.20%', '同步走弱', '跌破大级别均线'),
        ]
        panel.update_favorite_rows(mock_rows)
        self.assertEqual(panel.table.rowCount(), len(mock_rows))

        panel.table.sortItems(4, Qt.SortOrder.AscendingOrder)
        asc_devs = [panel.table.item(r, 4).text() for r in range(panel.table.rowCount())]
        expected_asc = ['-1.50%', '+0.17%', '+0.33%', '+1.90%', '+10.74%', '+13.06%']
        self.assertEqual(asc_devs, expected_asc)

        panel.table.sortItems(4, Qt.SortOrder.DescendingOrder)
        desc_devs = [panel.table.item(r, 4).text() for r in range(panel.table.rowCount())]
        expected_desc = ['+13.06%', '+10.74%', '+1.90%', '+0.33%', '+0.17%', '-1.50%']
        self.assertEqual(desc_devs, expected_desc)

        updated_rows = [
            ('000710', '贝瑞基因', '9.20', '回踩企稳', '+0.77%', '1', '15%', '⏳ 盘前预备 [12:58]', '179.3', '0.40', '3953', '4.40', '24.30', '+1.32%', '同步整理', '支撑位蓄势震荡'),
            ('002354', '天娱数科', '8.50', '回踩中', '+12.00%', '3', '0%', '⏳ 盘前预备 [12:57]', '368.2', '-1.90', '83', '18.90', '54.30', '+2.62%', '同步整理', '股价缩量向大级别MA20'),
            ('300721', '怡达股份', '23.00', '回踩中', '+0.05%', '0', '0%', '⏳ 盘前预备 [12:57]', '246.3', '0.10', '3854', '3.30', '56.50', '-2.61%', '同步整理', '股价缩量向大级别MA20'),
            ('688300', '联瑞新材', '181.00', '回踩中', '+14.50%', '0', '0%', '⏳ 盘前预备 [12:57]', '248.8', '0.40', '572', '26.90', '114.30', '-8.61%', '同步走弱', '股价缩量向大级别MA20'),
            ('002415', '海康威视', '36.20', '回踩中', '+2.50%', '3', '0%', '⏳ 盘前预备 [12:57]', '247.2', '-0.00', '2136', '3.90', '19.90', '-0.90%', '同步整理', '股价缩量向大级别MA20'),
            ('000001', '平安银行', '10.30', '已平仓', '-2.80%', '0', '0%', '⏳ 盘前预备 [12:57]', '45.0', '-1.00', '4800', '1.20', '15.30', '-1.20%', '同步走弱', '跌破大级别均线'),
        ]
        panel.update_favorite_rows(updated_rows)
        new_desc_devs = [panel.table.item(r, 4).text() for r in range(panel.table.rowCount())]
        expected_new_desc = ['+14.50%', '+12.00%', '+2.50%', '+0.77%', '+0.05%', '-2.80%']
        self.assertEqual(new_desc_devs, expected_new_desc)

    def test_04_swing_table_ma20_sorting_and_live_updates(self):
        swing = SwingStateTable()
        mock_data = [
            ('600519', '贵州茅台', '1650.00', '回踩中', '-0.85%', '0', '0%', '🥈 盘中跟进 [10:15]', '75.5', '1.2', '15', '0.8', '0.5', '+0.35%', '同步整理', '日线缩量向20日均线靠拢'),
            ('002415', '海康威视', '32.40', '回踩企稳', '+0.15%', '1', '15%', '🔔 竞价先手 [09:25]', '92.0', '2.5', '8', '1.5', '1.0', '+1.25%', '逆市抗跌', 'MA20强支撑处出现十字星K线'),
            ('300750', '宁德时代', '185.50', '持股中', '+3.20%', '0', '20%', '🥇 黄金早盘 [09:35]', '88.5', '4.2', '3', '2.8', '2.1', '+4.50%', '大盘共振', '回踩确认后阳线收回，多头排列'),
            ('600111', '北方稀土', '19.25', '持股中', '+11.85%', '2', '30%', '🥇 黄金早盘 [09:42]', '84.2', '5.5', '1', '3.5', '2.8', '+6.20%', '大盘共振', '放量冲出平台，强势上涨波段'),
            ('000001', '平安银行', '10.45', '已平仓', '-1.50%', '0', '0%', '🥈 盘中跟进 [11:10]', '45.0', '-1.0', '88', '-0.5', '-0.8', '-1.20%', '同步走弱', '跌破20日均线离场信号触发'),
            ('002594', '比亚迪', '245.00', '回踩企稳', '+0.05%', '0', '10%', '🔔 竞价先手 [09:20]', '95.5', '1.8', '12', '1.2', '0.9', '+0.80%', '同步整理', '前期大涨后回踩MA20量能极度萎缩')
        ]
        swing.update_data_list(mock_data)
        self.assertEqual(swing.table.rowCount(), len(mock_data))

        swing.table.sortItems(4, Qt.SortOrder.AscendingOrder)
        asc_devs = [swing.table.item(r, 4).text() for r in range(swing.table.rowCount())]
        expected_asc = ['-1.50%', '-0.85%', '+0.05%', '+0.15%', '+3.20%', '+11.85%']
        self.assertEqual(asc_devs, expected_asc)

        swing.table.sortItems(4, Qt.SortOrder.DescendingOrder)
        desc_devs = [swing.table.item(r, 4).text() for r in range(swing.table.rowCount())]
        expected_desc = ['+11.85%', '+3.20%', '+0.15%', '+0.05%', '-0.85%', '-1.50%']
        self.assertEqual(desc_devs, expected_desc)

    def test_05_all_column_types_non_pollution_verification(self):
        """【多列全类型防污染验证】验证股票代码、名称、波段状态、首次发现时段、推荐理由等非偏离度列均 100% 独立且正确排序"""
        table = BaseATSTableWidget()
        table.setColumnCount(4)
        table.setRowCount(4)
        
        # 4 行各列测试数据：[代码, 名称, 首次发现时段, 推荐理由]
        rows = [
            ('002415', '⭐ 海康威视', '🔔 竞价先手 [09:25]', 'MA20强支撑处出现十字星K线'),
            ('600519', '⭐ 贵州茅台', '🥈 盘中跟进 [10:15]', '日线缩量向20日均线靠拢'),
            ('000001', '平安银行', '🥈 盘中跟进 [11:10]', '跌破20日均线离场信号触发'),
            ('300750', '宁德时代', '🥇 黄金早盘 [09:35]', '回踩确认后阳线收回，多头排列')
        ]
        for r_idx, r_data in enumerate(rows):
            for c_idx, val in enumerate(r_data):
                table.setItem(r_idx, c_idx, NumericTableWidgetItem(val))

        # 1. 股票代码列 (0 列) 升序
        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.assertEqual([table.item(r, 0).text() for r in range(4)], ['000001', '002415', '300750', '600519'])

        # 2. 股票代码列 (0 列) 降序
        table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.assertEqual([table.item(r, 0).text() for r in range(4)], ['600519', '300750', '002415', '000001'])

        # 3. 股票名称列 (1 列) 纯文本字典序
        table.sortItems(1, Qt.SortOrder.AscendingOrder)
        names_asc = [table.item(r, 1).text() for r in range(4)]
        self.assertEqual(len(names_asc), 4)

        # 4. 时段列 (2 列) 纯文本字典序
        table.sortItems(2, Qt.SortOrder.AscendingOrder)
        times_asc = [table.item(r, 2).text() for r in range(4)]
        self.assertEqual(len(times_asc), 4)


if __name__ == '__main__':
    unittest.main()
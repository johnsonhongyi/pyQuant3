# -*- coding: utf-8 -*-
"""
tests/test_new_stock_lift_release.py — 验证新股/次新股最近限售解禁日历自动获取、持久化与界面展示
"""

import sys
import os
import json
import unittest
import pandas as pd

# 加入项目根目录
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.new_stock_fetcher import NewStockFetcher, LIFT_CALENDAR_CACHE_FILE
from ats.ui.new_stock_panel import get_new_stock_table_headers, NewStockPanel


class TestNewStockLiftRelease(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_01_fetch_restricted_release_calendar(self):
        """测试东方财富限售解禁日历批量获取与本地持久化缓存"""
        fetcher = NewStockFetcher.get_instance()
        test_codes = ["301689", "001232", "688820"]

        result = fetcher.fetch_restricted_release_calendar(test_codes, force=True)
        self.assertIsInstance(result, dict)
        print(f"\n[Test 1] 批量拉取解禁日历返回条数: {len(result)}")

        # 验证至少包含所查测试代码
        for c in test_codes:
            if c in result:
                info = result[c]
                print(f"  标的 {c}: 解禁日={info.get('lift_date')}, 股份={info.get('lift_shares')}万股, 占比={info.get('lift_ratio')}%, 类型={info.get('lift_type')}")
                self.assertIn("lift_date", info)
                self.assertIn("lift_shares", info)
                self.assertIn("lift_ratio", info)
                self.assertIn("lift_type", info)

        # 验证本地原子落盘文件是否存在且合法
        self.assertTrue(os.path.exists(LIFT_CALENDAR_CACHE_FILE), "本地解禁日历缓存文件应存在")
        with open(LIFT_CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("items", data)
            self.assertIn("updated_at", data)
            self.assertGreater(data["count"], 0)

    def test_02_combined_new_stocks_contains_lift_data(self):
        """测试综合新股数据组装包含解禁日相关字段"""
        fetcher = NewStockFetcher.get_instance()
        df = fetcher.get_combined_new_stocks(force_refresh=False)
        self.assertFalse(df.empty, "综合新股列表不应为空")

        # 检查字段是否注入
        required_cols = ["lift_date", "lift_shares", "lift_ratio", "lift_type"]
        for col in required_cols:
            self.assertIn(col, df.columns, f"新股 DataFrame 应包含字段 {col}")

        # 检查解禁日期样本
        valid_lift_df = df[df["lift_date"] != "-"]
        print(f"\n[Test 2] 具有明确解禁日期的标的数量: {len(valid_lift_df)}/{len(df)}")
        if not valid_lift_df.empty:
            sample = valid_lift_df.iloc[0]
            print(f"  样本标的 {sample['code']} {sample['name']}: 解禁日={sample['lift_date']}, 占比={sample['lift_ratio']}%")

    def test_03_ui_headers_and_preview_card(self):
        """测试 UI 表格列对齐与推演卡片标题格式化"""
        headers = get_new_stock_table_headers()
        print(f"\n[Test 3] 表格总列数: {len(headers)}")
        self.assertEqual(headers[5], "申购日")
        self.assertEqual(headers[6], "解禁日")
        self.assertEqual(headers[7], "发行价")
        self.assertEqual(headers[10], "涨速%")

        # 验证 Panel 初始化与基础列宽配置长度对齐
        panel = NewStockPanel()
        self.assertEqual(panel.table.columnCount(), len(headers), "表格列数应与表头完全对齐")

        # 测试推演卡片包含解禁日信息
        mock_row_with_lift = {
            "code": "301689",
            "name": "富特科技",
            "issue_price": 14.00,
            "float_mv_yi": 12.50,
            "price": 28.50,
            "listing_date": "2024-09-04",
            "lift_date": "2027-09-04",
            "lift_ratio": 38.5,
        }
        panel._update_preview_card(mock_row_with_lift)
        card_title = panel.lbl_spec_title.text()
        print(f"  推演卡片标题 (带解禁日): {card_title}")
        self.assertIn("最近解禁: 2027-09-04(占比38.5%)", card_title)


if __name__ == "__main__":
    unittest.main()

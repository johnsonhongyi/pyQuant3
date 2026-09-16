# -*- coding: utf-8 -*-
"""
tests/test_new_stock_translated_ats_col.py
-------------------------------------------
专项测试：验证新股次新股 (IPO_阶梯) 面板在自定义 ats_col 包含转义列 (如 win -> 连阳) 时的完整闭环：
1. 表头映射：win 成功转义为 '连阳'；
2. 列索引解析：_render_table 中 extra_col_map 成功通过 '连阳'/'win' 双向匹配找到真实列索引；
3. 数据提取：update_from_ipc_df 兼容 'win' 与 '连阳' 的行情字段同步；
4. 单元格渲染：'连阳' 列不再空白，正确渲染带符号的连阳数值 (如 +3.00, +0.00)。
"""

import os
import sys
import unittest
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

import JohnsonUtil.commonTips as cct
from ats.ui.new_stock_panel import (
    NewStockPanel,
    get_new_stock_extra_cols,
    get_new_stock_table_headers
)


class TestNewStockTranslatedAtsCol(unittest.TestCase):
    """测试新股面板对转义自定义列 (win -> 连阳) 的解析与渲染"""

    def setUp(self):
        self.old_ats_col = getattr(cct, 'ats_col', ['ch_bc2'])
        self.old_vis_map = getattr(cct, 'vis_column_map', {})

        # 模拟用户配置
        cct.ats_col = ["dff", "ch_dir", "ch_slope_deg", "ch_bc2", "win", "red"]
        cct.vis_column_map = {
            "win": "连阳",
            "dff": "DFF",
            "code": "代码",
            "name": "名称"
        }

    def tearDown(self):
        cct.ats_col = self.old_ats_col
        cct.vis_column_map = self.old_vis_map

    def test_headers_and_extra_cols_generation(self):
        """验证表头生成时 win 成功被映射为 '连阳'"""
        extra_cols = get_new_stock_extra_cols()
        self.assertIn("win", extra_cols)
        self.assertIn("ch_dir", extra_cols)
        self.assertIn("red", extra_cols)

        headers = get_new_stock_table_headers(extra_cols)
        self.assertIn("连阳", headers, "表头必须正确显示中文转义名 '连阳'")
        self.assertNotIn("win", headers, "英文原始名 win 已转义为 '连阳'，不应重复出现")

    def test_new_stock_panel_renders_win_column(self):
        """验证面板创建后，update_from_ipc_df 并渲染时，'连阳' 列单元格被正确填充数值"""
        panel = NewStockPanel()
        try:
            # 构造模拟新股基础数据
            df_base = pd.DataFrame([
                {
                    "code": "301588",
                    "name": "N长进",
                    "status": "首日(N)",
                    "listing_date": "2026-09-16",
                    "apply_date": "2026-09-08",
                    "issue_price": 35.78,
                    "price": 61.26,
                    "pct": 71.21,
                    "turnover": 75.96,
                    "float_mv_yi": 9.37,
                    "total_mv_yi": 47.78,
                    "amount_yi": 6.71,
                },
                {
                    "code": "301599",
                    "name": "C华新",
                    "status": "前5日(C)",
                    "listing_date": "2026-09-11",
                    "apply_date": "2026-09-03",
                    "issue_price": 40.98,
                    "price": 288.17,
                    "pct": 6.30,
                    "turnover": 10.80,
                    "float_mv_yi": 51.17,
                    "total_mv_yi": 269.93,
                    "amount_yi": 5.46,
                }
            ])
            panel.df_data = df_base.copy()

            # 构造包含 win, red, ch_dir, ch_slope_deg, ch_bc2 的 IPC 行情数据
            df_ipc = pd.DataFrame([
                {
                    "code": "301588",
                    "win": 0.0,      # 0 连阳
                    "red": 0.0,
                    "ch_dir": 0.0,
                    "ch_slope_deg": 0.0,
                    "ch_bc2": 0.0,
                    "dff": 0.0,
                },
                {
                    "code": "301599",
                    "win": 3.0,      # 3 连阳
                    "red": 6.0,
                    "ch_dir": -1.0,
                    "ch_slope_deg": -74.15,
                    "ch_bc2": 34.0,
                    "dff": 0.80,
                }
            ]).set_index("code")

            # 注入 IPC 数据并触发渲染
            panel.update_from_ipc_df(df_ipc, sh_pct=0.5, force=True)

            # 定位 '连阳' 列
            col_win = panel._get_col_by_header("连阳")
            self.assertGreaterEqual(col_win, 0, "必须通过表头 '连阳' 成功定位到列号！")

            col_red = panel._get_col_by_header("red")
            self.assertGreaterEqual(col_red, 0, "必须通过表头 'red' 成功定位到列号！")

            # 校验行数
            self.assertEqual(panel.table.rowCount(), 2)

            # 检验第一行与第二行的 '连阳' 单元格文字
            item_r0_win = panel.table.item(0, col_win)
            item_r1_win = panel.table.item(1, col_win)

            self.assertIsNotNone(item_r0_win, "第一行 '连阳' 单元格不能为 None")
            self.assertIsNotNone(item_r1_win, "第二行 '连阳' 单元格不能为 None")

            val_r0_txt = item_r0_win.text().strip()
            val_r1_txt = item_r1_win.text().strip()

            # 验证不是空白或未渲染
            self.assertNotEqual(val_r0_txt, "", "第一行 '连阳' 列绝不能是空白字符串！")
            self.assertNotEqual(val_r1_txt, "", "第二行 '连阳' 列绝不能是空白字符串！")

            # 验证格式化数值
            self.assertIn(val_r0_txt, ("+0.00", "0", "0.00", "+0"))
            self.assertIn(val_r1_txt, ("+3.00", "3", "3.00", "+3"))

            # 验证 'red' 列也正常显示
            item_r1_red = panel.table.item(1, col_red)
            self.assertIsNotNone(item_r1_red)
            self.assertIn(item_r1_red.text().strip(), ("+6.00", "6", "6.00", "+6"))

        finally:
            panel.close()

    def test_new_stock_panel_handles_chinese_key_in_ipc_df(self):
        """验证如果 IPC DataFrame 里的 key 已经是中文 '连阳'，也能完美识别与渲染"""
        panel = NewStockPanel()
        try:
            df_base = pd.DataFrame([
                {
                    "code": "301599",
                    "name": "C华新",
                    "status": "次新",
                    "listing_date": "2026-09-11",
                    "price": 288.17,
                    "pct": 6.30,
                }
            ])
            panel.df_data = df_base.copy()

            # 传入的 key 就是 '连阳'
            df_ipc = pd.DataFrame([
                {
                    "code": "301599",
                    "连阳": 5.0,
                    "red": 8.0,
                }
            ]).set_index("code")

            panel.update_from_ipc_df(df_ipc, force=True)

            col_win = panel._get_col_by_header("连阳")
            self.assertGreaterEqual(col_win, 0)

            item = panel.table.item(0, col_win)
            self.assertIsNotNone(item)
            self.assertIn(item.text().strip(), ("+5.00", "5", "5.00", "+5"))

        finally:
            panel.close()


if __name__ == "__main__":
    unittest.main()

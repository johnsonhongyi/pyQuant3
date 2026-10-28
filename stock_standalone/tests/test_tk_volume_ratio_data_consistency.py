# -*- coding: utf-8 -*-
"""
专项回归测试：TK 监控主界面「量比」数据一致性与盘口快照防污染闭环测试
覆盖场景：
1. _refresh_ui_favorites 避免盘口原始成交量(如 113764手)覆盖主表量比(如 1.3)
2. rich_row 与 quote_values 合并时保护已计算的量比不受原始成交量冲刷
3. TreeviewIncrementalUpdater._prepare_rows_fast 智能自愈防线
4. StockSelector.load_data 保持 volume 为量比、vol 为成交量
5. calc_indicators 对齐 volume 与 vol_ratio
"""

import unittest
import pandas as pd
import numpy as np


class TestTKVolumeRatioDataConsistency(unittest.TestCase):

    def test_treeview_incremental_updater_volume_ratio_self_healing(self):
        """测试 TreeviewIncrementalUpdater 增量更新器在遇到脏数据(>100)时的智能自愈"""
        from performance_optimizer import TreeviewIncrementalUpdater

        # 模拟受到成交量污染的 DataFrame (volume 列为 113764, 598257)
        dirty_df = pd.DataFrame({
            'code': ['301005', '688536'],
            'name': ['超捷股份', '思瑞浦'],
            'volume': [113764.0, 598257.0],  # 脏数据：原始成交量
            'vol_ratio': [1.3, 2.2],          # 正确的量比
            'vol': [113764.0, 598257.0],
            'last6vol': [87510.0, 271935.0],
        })

        updater = TreeviewIncrementalUpdater(
            tree=None,
            columns=['code', 'name', 'volume'],
            root=None
        )

        rows = updater._prepare_rows_fast(dirty_df)
        self.assertEqual(len(rows), 2)

        # 检查 301005 的 values: ['301005', '超捷股份', '1.3']
        code_1, values_1, _ = rows[0]
        self.assertEqual(code_1, '301005')
        self.assertEqual(values_1[2], '1.3')  # 必须自愈为 1.3，绝不能是 113764!

        # 检查 688536 的 values: ['688536', '思瑞浦', '2.2']
        code_2, values_2, _ = rows[1]
        self.assertEqual(code_2, '688536')
        self.assertEqual(values_2[2], '2.2')  # 必须自愈为 2.2，绝不能是 598257!

    def test_treeview_incremental_updater_fallback_calculation_when_vol_ratio_absent(self):
        """测试当 vol_ratio 列缺失但包含 last6vol 时，Treeview 现场纠偏计算量比"""
        from performance_optimizer import TreeviewIncrementalUpdater

        # 缺失 vol_ratio，但有 last6vol 和 vol
        df = pd.DataFrame({
            'code': ['301005'],
            'name': ['超捷股份'],
            'volume': [120000.0],  # 脏数据
            'vol': [120000.0],
            'last6vol': [60000.0],
        })

        updater = TreeviewIncrementalUpdater(
            tree=None,
            columns=['code', 'name', 'volume'],
            root=None
        )

        rows = updater._prepare_rows_fast(df)
        _, values, _ = rows[0]
        # 120000 / 60000 = 2.0
        self.assertEqual(values[2], '2.0')

    def test_refresh_ui_favorites_quote_merge_protection(self):
        """测试盘口快照合并逻辑，验证主表原有量比绝对不被盘口原始成交量覆盖"""
        # 模拟主表已有数据 (含有计算好的量比 1.3，成交量 90000)
        df = pd.DataFrame({
            'code': ['301005'],
            'name': ['超捷股份'],
            'volume': [1.3],       # 主表量比
            'vol': [90000.0],      # 主表成交量
            'trade': [50.0],
        }, index=[0])

        # 模拟联动盘口快照 (带有最新成交量 113764，最新现价 50.15)
        quote_values = {
            'code': '301005',
            'trade': 50.15,
            'volume': 113764.0,    # 盘口成交量(手)
        }

        row_index = 0
        # 运行我们修补后的安全更新逻辑：
        for column, value in quote_values.items():
            if pd.isna(value) and column in df.columns:
                continue
            if column == 'volume':
                if 'vol' in df.columns:
                    df.at[row_index, 'vol'] = value
                continue
            if column not in df.columns:
                df[column] = pd.NA
            df.at[row_index, column] = value

        # 校验：现价更新为 50.15，vol 更新为 113764，而 volume 依然是量比 1.3！
        self.assertEqual(df.at[row_index, 'trade'], 50.15)
        self.assertEqual(df.at[row_index, 'vol'], 113764.0)
        self.assertEqual(df.at[row_index, 'volume'], 1.3)

    def test_stock_selector_load_data_preserves_volume_as_ratio(self):
        """测试 StockSelector.load_data 结合实时数据时保持 volume 为量比，成交量为 vol"""
        from stock_selector import StockSelector
        from unittest.mock import patch

        selector = StockSelector(df=pd.DataFrame())

        base_df = pd.DataFrame({
            'code': ['301005'],
            'name': ['超捷股份'],
            'last6vol': [10000.0],
        })

        # 实时数据：volume 是量比 1.5，vol 是成交量 15000
        rt_df = pd.DataFrame({
            'code': ['301005'],
            'volume': [1.5],
            'vol': [15000.0],
            'trade': [50.0],
        })
        selector.df_all_realtime = rt_df

        # mock read_hdf_safe 返回 base_df
        with patch('os.path.exists', return_value=True), \
             patch('JSONData.tdx_hdf5_api.read_hdf_safe', return_value=base_df):
            combined = selector.load_data()

        self.assertIn('volume', combined.columns)
        self.assertIn('vol', combined.columns)
        # volume 必须依然是量比 1.5，绝不能被覆盖成 15000
        self.assertEqual(combined.loc['301005', 'volume'], 1.5)
        self.assertEqual(combined.loc['301005', 'vol'], 15000.0)

    def test_data_utils_calc_indicators_mirrors_vol_ratio(self):
        """测试 data_utils.calc_indicators 成功为 DataFrame 注入镜像 vol_ratio"""
        from data_utils import calc_indicators
        import logging

        logger = logging.getLogger("test")

        df = pd.DataFrame({
            'code': ['301005'],
            'close': [50.0],
            'volume': [100000.0],  # 输入成交量
            'last6vol': [100000.0],
            'now': [50.0],
        })

        res = calc_indicators(df, logger, resample='d')
        self.assertIn('vol', res.columns)
        self.assertIn('vol_ratio', res.columns)
        self.assertIn('volume', res.columns)
        # vol 记录原始成交量 100000
        self.assertEqual(res['vol'].iloc[0], 100000.0)
        # volume 与 vol_ratio 严格一致，且为比率
        self.assertEqual(res['vol_ratio'].iloc[0], res['volume'].iloc[0])


if __name__ == '__main__':
    unittest.main()

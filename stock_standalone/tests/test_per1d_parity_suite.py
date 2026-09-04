# -*- coding: utf-8 -*-
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from data_utils import complete_indicators_pipeline


class TestPer1dParitySuite(unittest.TestCase):
    def setUp(self):
        self.df_base = pd.DataFrame({
            'open': [20.0],
            'high': [21.5],
            'low': [19.8],
            'close': [21.32],
            'vol': [1000.0],
            'volume': [1.5],
            'lastp1d': [16.40],
            'lastp2d': [17.17],
            'per1d': [-4.5],
            'per2d': [2.9],
            'perc3d': [54.0],
            'name': ['柏星龙']
        }, index=['920075'])

    def test_per1d_not_overwritten_by_today_percent(self):
        res_df = complete_indicators_pipeline(self.df_base.copy(), logger=None, resample='d')
        today_pct = res_df.loc['920075', 'percent']
        self.assertAlmostEqual(today_pct, 30.0, delta=0.1)
        yesterday_pct = res_df.loc['920075', 'per1d']
        self.assertEqual(yesterday_pct, -4.5)
        self.assertNotEqual(yesterday_pct, today_pct)

    def test_per1d_defensive_fill_when_missing(self):
        df_no_per1d = self.df_base.drop(columns=['per1d']).copy()
        res_df = complete_indicators_pipeline(df_no_per1d, logger=None, resample='d')
        yesterday_pct = res_df.loc['920075', 'per1d']
        self.assertAlmostEqual(yesterday_pct, -4.48, delta=0.05)
        today_pct = res_df.loc['920075', 'percent']
        self.assertAlmostEqual(today_pct, 30.0, delta=0.1)
        self.assertNotEqual(yesterday_pct, today_pct)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""
单元测试：测试多周期管理器默认只读刷新与强制刷新自动初始化功能
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

# 将项目根目录加入 sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from multi_period_strategy_engine import MultiPeriodStrategyEngine


class TestMultiPeriodAutoInit(unittest.TestCase):
    def setUp(self):
        self.engine = MultiPeriodStrategyEngine()
        self.top_now_mock = pd.DataFrame({
            'name': ['平安银行', '万科A'],
            'trade': [10.0, 15.0],
            'price': [10.0, 15.0],
            'percent': [1.5, -0.5],
            'ratio': [1.5, -0.5],
            'volume': [100000, 200000]
        }, index=['000001', '000002'])

    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_default_refresh_readonly_no_init(self, mock_get_append):
        """测试默认刷新 (force_reload=False) 保持纯只读模式，不触发初始化写入"""
        # 模拟底层只读模式返回空或缺失 lastp1d
        mock_get_append.return_value = (pd.DataFrame(), None)

        res_df = self.engine.load_period_data('45d', self.top_now_mock, force_reload=False)
        
        # 校验：应该以 readonly=True 调用一次
        mock_get_append.assert_called_once_with(self.top_now_mock, dl=3000, resample='45d', readonly=True, end=None)
        # 结果应为空
        self.assertTrue(res_df.empty)
        self.assertIn('45d', self.engine._missing_periods)

    @patch('data_utils.complete_indicators_pipeline')
    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_force_reload_auto_init(self, mock_get_append, mock_pipeline):
        """测试强制刷新 (force_reload=True) 时，缺失数据周期自动调用 get_append_lastp_to_df 进行初始化"""
        valid_df = pd.DataFrame({
            'open': [10.0, 15.0],
            'close': [10.5, 15.5],
            'high': [10.8, 15.8],
            'low': [9.9, 14.8],
            'volume': [100000, 200000],
            'lastp1d': [9.8, 14.9],
            'lastv1d': [90000, 190000]
        }, index=['000001', '000002'])

        mock_get_append.return_value = (valid_df, None)
        mock_pipeline.side_effect = lambda df, log, resample: df

        res_df = self.engine.load_period_data('3M', self.top_now_mock, force_reload=True)

        # 校验：强制刷新时应该调用 get_append_lastp_to_df (不带 readonly=True)
        mock_get_append.assert_called_once_with(self.top_now_mock, dl=4000, resample='3m', readonly=False, end=None)
        self.assertFalse(res_df.empty)
        self.assertNotIn('3M', self.engine._missing_periods)
        self.assertIn('3M', self.engine._period_dfs)

    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_readonly_switch_prevents_init(self, mock_get_append):
        """测试当只读模式勾选时 (force_reload=False)，即使强刷也不进行底层数据写盘初始化"""
        mock_get_append.return_value = (pd.DataFrame(), None)

        res_df = self.engine.load_period_data('45d', self.top_now_mock, force_reload=False)

        mock_get_append.assert_called_once_with(self.top_now_mock, dl=3000, resample='45d', readonly=True, end=None)
        self.assertTrue(res_df.empty)

    @patch('data_utils.complete_indicators_pipeline')
    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_uppercase_period_mapping(self, mock_get_append, mock_pipeline):
        """测试大写周期 (W/M) 能够自动规范化并匹配正确 dl (300/550)"""
        valid_df = pd.DataFrame({'lastp1d': [10.0, 15.0]}, index=['000001', '000002'])
        mock_get_append.return_value = (valid_df, None)
        mock_pipeline.side_effect = lambda df, log, resample: df

        res_df_w = self.engine.load_period_data('W', self.top_now_mock, force_reload=True)
        mock_get_append.assert_called_with(self.top_now_mock, dl=300, resample='w', readonly=False, end=None)
        self.assertIn('w', self.engine._period_dfs)
        self.assertIn('W', self.engine._period_dfs)

        res_df_m = self.engine.load_period_data('M', self.top_now_mock, force_reload=True)
        mock_get_append.assert_called_with(self.top_now_mock, dl=550, resample='m', readonly=False, end=None)
        self.assertIn('m', self.engine._period_dfs)
        self.assertIn('M', self.engine._period_dfs)


    @patch('data_utils.complete_indicators_pipeline')
    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_end_date_pass_through(self, mock_get_append, mock_pipeline):
        """测试 load_period_data 能够将 end 日期参数无损透传至 get_append_lastp_to_df"""
        valid_df = pd.DataFrame({'lastp1d': [10.0, 15.0]}, index=['000001', '000002'])
        mock_get_append.return_value = (valid_df, None)
        mock_pipeline.side_effect = lambda df, log, resample: df

        res_df = self.engine.load_period_data('3d', self.top_now_mock, force_reload=True, end='2026-07-27')
        mock_get_append.assert_called_once_with(self.top_now_mock, dl=200, resample='3d', readonly=False, end='2026-07-27')
        self.assertFalse(res_df.empty)

    def test_tqdm_to_pyqt_bridge(self):
        """测试 TqdmToPyQtBridge 能否在 tqdm 分片刷新时成功保留并拼接数量/用时/速率信号"""
        from ats.ui.multi_period_dialog import TqdmToPyQtBridge
        mock_signal = MagicMock()
        bridge = TqdmToPyQtBridge(sys.stderr, mock_signal, prefix="[45d]")

        # 模拟分片1：包含初始详细数据
        bridge.write("Running_MP:   7%|█▋        | 361/5.55k [00:21<04:23, 19.7it/s]\r")
        mock_signal.emit.assert_called()
        msg1 = mock_signal.emit.call_args[0][0]
        self.assertIn("361/5.55k", msg1)

        # 模拟分片2：tqdm 后续分片刷屏，仅包含了 Running_MP: 21%|\r
        mock_signal.reset_mock()
        bridge._last_emit_ts = 0  # 重置发射冷却时间
        bridge.write("Running_MP:  21%|\r")
        
        mock_signal.emit.assert_called_once()
        msg2 = mock_signal.emit.call_args[0][0]
        self.assertIn("21%", msg2)
        self.assertIn("361/5.55k", msg2)  # 验证历史数量与时间速率被成功记忆并合成！


if __name__ == '__main__':
    unittest.main()

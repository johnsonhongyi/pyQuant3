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

        res_df = self.engine.load_period_data('3M', self.top_now_mock, force_reload=True, readonly=False)

        # 校验：强制刷新时应该调用 get_append_lastp_to_df (且 resample 保留 3M 大写格式, readonly=False)
        mock_get_append.assert_called_once_with(self.top_now_mock, dl=4000, resample='3M', readonly=False, end=None)
        self.assertFalse(res_df.empty)
        self.assertNotIn('3M', self.engine._missing_periods)
        self.assertIn('3M', self.engine._period_dfs)

    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_readonly_switch_prevents_init(self, mock_get_append):
        """测试当只读模式勾选时 (readonly=True)，即使强刷也不进行底层数据写盘初始化"""
        mock_get_append.return_value = (pd.DataFrame(), None)

        res_df = self.engine.load_period_data('3M', self.top_now_mock, force_reload=True, readonly=True)
    
        # 校验：只读模式下不应触发 readonly=False 底层写盘初始化
        self.assertTrue(res_df.empty)
        self.assertIn('3M', self.engine._missing_periods)

    @patch('data_utils.complete_indicators_pipeline')
    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_uppercase_period_mapping(self, mock_get_append, mock_pipeline):
        """测试大写 (W/M) 能够自动规范匹配正确 dl (300/550) 且保留原生大写"""
        valid_df = pd.DataFrame({'lastp1d': [10.0, 15.0]}, index=['000001', '000002'])
        mock_get_append.return_value = (valid_df, None)
        mock_pipeline.side_effect = lambda df, log, resample: df
    
        res_df_w = self.engine.load_period_data('W', self.top_now_mock, force_reload=True, readonly=False)
        mock_get_append.assert_called_with(self.top_now_mock, dl=300, resample='W', readonly=False, end=None)
        self.assertIn('W', self.engine._period_dfs)

        res_df_m = self.engine.load_period_data('M', self.top_now_mock, force_reload=True, readonly=False)
        mock_get_append.assert_called_with(self.top_now_mock, dl=550, resample='M', readonly=False, end=None)
        self.assertIn('M', self.engine._period_dfs)

    @patch('data_utils.complete_indicators_pipeline')
    @patch('JSONData.tdx_data_Day.get_append_lastp_to_df')
    def test_end_date_pass_through(self, mock_get_append, mock_pipeline):
        """测试 load_period_data 能够将 end 日期参数无损透传至 get_append_lastp_to_df"""
        valid_df = pd.DataFrame({'lastp1d': [10.0, 15.0]}, index=['000001', '000002'])
        mock_get_append.return_value = (valid_df, None)
        mock_pipeline.side_effect = lambda df, log, resample: df

        res_df = self.engine.load_period_data('3d', self.top_now_mock, force_reload=True, readonly=False, end='2026-07-27')
        mock_get_append.assert_called_once_with(self.top_now_mock, dl=200, resample='3d', readonly=False, end='2026-07-27')
        self.assertFalse(res_df.empty)

    def test_intraday_volume_projection(self):
        """测试数据更新中检查并安全应用 0d 虚拟全天成交量 (lastv0d) 与 Sina 实时量比联合投影"""
        from data_utils import complete_indicators_pipeline
        from unittest.mock import patch

        df_test = pd.DataFrame({
            'now': [10.0, 20.0],
            'open': [10.0, 20.0],
            'high': [10.5, 20.5],
            'low': [9.8, 19.8],
            'close': [10.2, 20.2],
            'vol': [1000.0, 2000.0],
            'volume': [1.5, 2.0],  # 量比
            'lastp1d': [9.8, 19.8],
            'lastv1d': [20000.0, 50000.0],
            'ratio': [1.5, 2.0]
        }, index=['000001', '000002'])

        with patch('JohnsonUtil.commonTips.get_work_time_ratio', return_value=0.0208333): # 1/48
            res_df = complete_indicators_pipeline(df_test.copy(), logger=None, resample='d')
            
            # 5 分钟交易时间: ratio_t = 1/48 => 48.0
            # 000001: proj_time = 1000 * 48 = 48000
            # 000002: proj_time = 2000 * 48 = 96000
            self.assertEqual(res_df.loc['000001', 'lastv0d'], 48000.0)
            self.assertEqual(res_df.loc['000002', 'lastv0d'], 96000.0)
            # 保证 volume (量比) 列没有被破坏覆盖
            self.assertIn('volume', res_df.columns)

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

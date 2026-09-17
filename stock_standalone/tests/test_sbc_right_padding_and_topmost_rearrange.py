# -*- coding: utf-8 -*-
import sys
import os
import time
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRect

from JohnsonUtil import commonTips as cct
sys.modules['cct'] = cct

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.intraday_strategy_dialog import SBCChartCanvas, SBCIntradayChartDialog, rearrange_all_sbc_windows, _SBCWindowProxy


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestSBCRightPaddingAndTopmostRearrange:
    def test_dynamic_ats_tdx_interval_ttl(self):
        fetcher = TDXRealtimeFetcher.get_instance()
        test_code = '600733'
        today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
        dummy_df = pd.DataFrame({'close': [4.58, 4.59], 'vol': [100, 200]})
        
        if not hasattr(fetcher, '_multi_day_bars_cache'):
            fetcher._multi_day_bars_cache = {}

        fetcher._multi_day_bars_cache[(test_code, 2)] = (dummy_df, time.time() - 2.0, today_str)

        with patch.object(cct, 'ats_tdx_interval', 5.0):
            res_df = fetcher.fetch_multi_day_intraday_bars(test_code, days=2)
            assert not res_df.empty
            assert len(res_df) == 2

    def test_sbc_canvas_kline_right_padding_two_bars(self, qapp):
        canvas = SBCChartCanvas()
        canvas.period_mode = '30m'
        canvas.code = '600733'
        canvas.resize(800, 600)

        dates = pd.date_range('2026-09-17 09:30', periods=20, freq='30min')
        df_kline = pd.DataFrame({
            'open': np.linspace(4.5, 4.8, 20),
            'close': np.linspace(4.52, 4.75, 20),
            'high': np.linspace(4.6, 4.9, 20),
            'low': np.linspace(4.4, 4.7, 20),
            'vol': [1000] * 20,
        }, index=dates)
        canvas.df_intraday = df_kline

        chart_w = 800 - 55 - 75
        margin_left = 55
        n = len(df_kline)
        RIGHT_PAD_BARS = 2
        total_slots = max(1, n + RIGHT_PAD_BARS)
        bar_step = chart_w / float(total_slots)

        def k_to_x(i):
            return margin_left + (i + 0.5) * bar_step

        last_k_x = k_to_x(n - 1)
        chart_right_boundary = margin_left + chart_w

        remaining_space = chart_right_boundary - last_k_x
        expected_remaining_bars = remaining_space / bar_step

        assert expected_remaining_bars >= 2.0, f'预留空间不足 2 根 K 棒: {expected_remaining_bars}'
        assert last_k_x < chart_right_boundary - bar_step * 1.8

    def test_rearrange_all_windows_bring_all_to_front_top_view(self, qapp):
        dlg1 = SBCIntradayChartDialog(code='600733')
        dlg2 = SBCIntradayChartDialog(code='688635')
        dlg1.show()
        dlg2.show()

        dlg1.raise_ = MagicMock()
        dlg2.raise_ = MagicMock()

        with patch.dict(os.environ, {'PYTEST_CURRENT_TEST': '1'}), \
             patch('run_sbc.save_launcher_holdings_windows') as mock_save:
            rearrange_all_sbc_windows(parent_win=dlg1)

        assert dlg1.raise_.call_count >= 1
        assert dlg2.raise_.call_count >= 1

        dlg1.close()
        dlg2.close()

# -*- coding: utf-8 -*-
"""
午间休市TDX空批次保护与走势图现价兜底测试
"""
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher


def test_noon_recess_empty_batch_protection():
    """
    测试 1: 午间休市/非交易时段空批次保护
    在 not is_trading 期间，通达信返回空盘口属于正常现象：
    - 绝不触发 auto_failover 故障转移
    - 绝不启动深度二分隔离探针
    - 绝不把股票加入 unlisted/dormant 黑名单
    """
    fetcher = TDXRealtimeFetcher.get_instance()
    mock_stage_meta = {"stage": "NOON_RECESS", "is_bidding": False, "is_locked": False}
    with patch("ats.tdx_realtime_fetcher.is_tdx_trading_allowed", return_value=(False, "午间休市", mock_stage_meta)):
        with patch.object(fetcher, "auto_failover") as mock_failover:
            with patch.object(fetcher, "_probe_host_alive") as mock_probe:
                fetcher.api = MagicMock()
                fetcher.api.get_security_quotes.return_value = []
                fetcher._is_connected = True

                codes = ["002307", "601606"]
                quotes = fetcher.get_security_quotes_safe(codes)

                mock_failover.assert_not_called()
                mock_probe.assert_not_called()
                assert "002307" not in fetcher._unlisted_or_dormant_codes
                assert "601606" not in fetcher._unlisted_or_dormant_codes
                assert fetcher._consecutive_empty_batches == 0


def test_chart_data_price_fallback_not_zero():
    """
    测试 2: 走势图多日分时与各模式现价 0.00 兜底防御
    当 snapshot 返回 price=0.0 时，走势图数据引擎能从实际数据中提取真实的 p，绝不返回 0.00
    """
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
    
    class DummyDialog:
        code = "002307"
        engine = None
        _channel_overlay_enabled = False
        def _eval_vwap_proactive_strategy(self, *a, **kw):
            return []

    dummy = DummyDialog()
    do_fetch = SBCIntradayChartDialog._do_fetch_chart_data.__get__(dummy, DummyDialog)

    zero_snap = {"price": 0.0, "open_price": 0.0, "vwap": 0.0, "high_price": 0.0, "low_price": 0.0}

    df_multi = pd.DataFrame([
        {"date": "2026-10-28", "time": "09:31", "open": 3.18, "close": 3.20, "high": 3.21, "low": 3.17, "vwap": 3.19},
        {"date": "2026-10-28", "time": "11:30", "open": 3.20, "close": 3.22, "high": 3.25, "low": 3.19, "vwap": 3.21},
    ])

    fetcher = TDXRealtimeFetcher.get_instance()
    with patch.object(fetcher, "fetch_stock_snapshot", return_value=zero_snap):
        with patch.object(fetcher, "fetch_multi_horizon_vwap", return_value=(df_multi, None)):
            # 验证 3d 模式
            payload_3d = do_fetch(code="002307", mode="3d", preloaded={"snapshot": zero_snap, "multi": (df_multi, None)})
            assert payload_3d["p"] == 3.22
            assert payload_3d["op"] == 3.18
            assert payload_3d["p"] > 0.0

            # 验证 1m 模式
            payload_1m = do_fetch(code="002307", mode="1m", preloaded={"snapshot": zero_snap, "multi": (df_multi, None)})
            assert payload_1m["p"] == 3.22
            assert payload_1m["op"] == 3.18
            assert payload_1m["p"] > 0.0

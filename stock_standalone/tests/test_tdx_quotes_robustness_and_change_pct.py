# -*- coding: utf-8 -*-
"""
tests/test_tdx_quotes_robustness_and_change_pct.py
--------------------------------------------------
验证 TDX 实时盘口深度递归二分拆包隔离、未上市标的物理拦截与超短检测工具涨跌幅与集合竞价计算
"""

import pytest
import os
import sys
import pandas as pd
from unittest.mock import MagicMock, patch

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.new_stock_fetcher import NewStockFetcher
from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal
)


def test_recursive_binary_split_on_poison_code():
    """
    验证：当批次中混入未上市/异常代码导致通达信返回 None 时，
    自动启动深度二分拆包，精准隔离毒丸代码，其余正常标的 100% 成功返回
    """
    fetcher = TDXRealtimeFetcher.get_instance()
    
    mock_api = MagicMock()
    def mock_get_quotes(req_params):
        for mkt, code in req_params:
            if code == "301686":
                return None
        return [
            {"code": c, "price": 20.0, "last_close": 19.0}
            for _, c in req_params
        ]
    mock_api.get_security_quotes = mock_get_quotes

    with patch.object(fetcher, "_is_connected", True), \
         patch.object(fetcher, "api", mock_api), \
         patch.object(fetcher, "_probe_host_alive", return_value=True):
        
        test_codes = ["601091", "688801", "301686", "920298"]
        quotes = fetcher.get_security_quotes_safe(test_codes, force=True)
        
        returned_codes = [q["code"] for q in quotes]
        assert "601091" in returned_codes
        assert "688801" in returned_codes
        assert "920298" in returned_codes
        assert "301686" not in returned_codes
        assert "301686" in fetcher._unlisted_or_dormant_codes


def test_new_stock_fetcher_pre_ipo_isolation():
    """
    验证：NewStockFetcher 自动将未上市股票物理隔离，绝不传入 TDX 盘口拉取
    """
    nsf = NewStockFetcher.get_instance()
    mock_df = pd.DataFrame([
        {"code": "601091", "name": "沈鼓集团", "status": "前5日(C)", "listing_date": "2026-09-01", "price": 0.0, "pct": 0.0, "velocity_pct": 0.0, "velocity_tag": "--"},
        {"code": "301686", "name": "新奥新材", "status": "待上市", "listing_date": "2026-09-28", "price": 0.0, "pct": 0.0, "velocity_pct": 0.0, "velocity_tag": "--"},
    ])
    
    passed_chunks = []
    real_fetcher = TDXRealtimeFetcher.get_instance()
    
    def fake_quotes_safe(chunk, force=False):
        passed_chunks.append(list(chunk))
        return [{"code": "601091", "price": 20.0, "last_close": 19.0, "vol": 100, "amount": 2000.0, "open": 20.0, "high": 20.5, "low": 19.5}]

    with patch.object(real_fetcher, "get_security_quotes_safe", side_effect=fake_quotes_safe), \
         patch.object(real_fetcher, "get_batch_finance_shares", return_value={"601091": 1e8}), \
         patch.object(real_fetcher, "calculate_segmented_velocity", return_value={"velocity_pct": 0.0, "velocity_tag": "--", "velocity_desc": "--"}):
        
        res_df = nsf.enrich_with_tdx_realtime(mock_df, force=True)
        
        all_passed = [c for chunk in passed_chunks for c in chunk]
        assert "601091" in all_passed
        assert "301686" not in all_passed


def test_ipo_detector_change_pct_and_bidding_snapshot():
    """
    验证：IPOVWAPDetectorEngine 正确计算 change_pct，并融合早盘集合竞价盘口
    """
    engine = IPOVWAPDetectorEngine.get_instance()
    sig = VWAPDetectorSignal(code="601091", name="沈鼓集团")
    
    mock_df = pd.DataFrame([
        {"date": "2026-09-17", "close": 20.0, "price": 20.0, "vwap": 19.5, "open": 19.0},
        {"date": "2026-09-18", "close": 22.0, "price": 22.0, "vwap": 21.0, "open": 20.5},
    ])
    
    engine._evaluate_vwap_structure(mock_df, sig)
    assert sig.price == 22.0
    assert sig.change_pct == 10.0  # (22.0 - 20.0) / 20.0 * 100
    assert sig.vwap == 21.0
    assert sig.vwap_diff_pct == pytest.approx(4.76, 0.01)

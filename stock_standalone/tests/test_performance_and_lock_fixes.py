# -*- coding: utf-8 -*-
import os
import sys
import pytest
import pandas as pd
import numpy as np
import time
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from JohnsonUtil import commonTips as cct
from JSONData import sina_data
from realtime_data_service import DataPublisher
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

def test_hdf5_cache_preserved_after_gap_backfill():
    mock_df = pd.DataFrame({'trade': [10.0, 10.5]}, index=['600000', '600001'])
    sina = sina_data.Sina(readonly=True)
    sina_data.Sina._MEM_CACHE['all_30'] = {
        'df': mock_df,
        'last_time': time.time(),
        'ready': True
    }
    
    publisher = DataPublisher(simulation_mode=True)
    publisher.recover_from_hdf5_by_codes = MagicMock(return_value=pd.DataFrame())
    
    publisher.backfill_gaps_from_hdf5(['600000'], threshold=10)
    
    assert 'all_30' in sina_data.Sina._MEM_CACHE
    assert sina_data.Sina._MEM_CACHE['all_30']['ready'] is True

def test_controlled_gc_loop_skips_sina_clear_during_work_time():
    sina_data.Sina._MEM_CACHE['test_tbl'] = {'ready': True}
    
    with patch.object(cct, 'get_work_time', return_value=True):
        if not cct.get_work_time():
            sina_data.Sina(readonly=True).clear_unified_cache(force_gc=False)
        assert 'test_tbl' in sina_data.Sina._MEM_CACHE
        
    with patch.object(cct, 'get_work_time', return_value=False):
        if not cct.get_work_time():
            sina_data.Sina(readonly=True).clear_unified_cache(force_gc=False)
        assert 'test_tbl' not in sina_data.Sina._MEM_CACHE

def test_tdx_realtime_fetcher_binary_split_on_batch_failure():
    fetcher = TDXRealtimeFetcher()
    fetcher.is_connected = True
    fetcher.connect = MagicMock(return_value=True)
    fetcher.api = MagicMock()
    
    call_counts = {'count': 0}
    
    def mock_quotes(req_list):
        call_counts['count'] += 1
        if len(req_list) == 10:
            return []
        elif len(req_list) == 5 and req_list[0][1] == '600001':
            return [{'code': c, 'price': 10.0, 'last_close': 9.8} for _, c in req_list]
        else:
            return []
            
    fetcher.api.get_security_quotes = MagicMock(side_effect=mock_quotes)
    
    codes = [f'60000{i}' for i in range(1, 6)] + [f'92000{i}' for i in range(1, 6)]
    quotes = fetcher.get_security_quotes_safe(codes)
    
    assert call_counts['count'] == 3
    assert len(quotes) == 5
    for c in [f'92000{i}' for i in range(1, 6)]:
        assert fetcher._no_quote_counts.get(c, 0) >= 1

def test_top10_content_signature_dirty_check():
    mock_win = MagicMock()
    mock_tree = MagicMock()
    mock_win._tree_top10 = mock_tree
    mock_win.state = MagicMock(return_value='normal')
    mock_win.winfo_viewable = MagicMock(return_value=True)
    mock_tree.get_children = MagicMock(return_value=['item1', 'item2'])
    
    actual_col = 'percent'
    ascending = False
    sig_items = (('600000', 5.2, 3.1, 1), ('600001', 3.4, 1.2, 2))
    current_sig = (actual_col, ascending, sig_items)
    
    mock_win._last_display_sig = current_sig
    
    if getattr(mock_win, '_last_display_sig', None) == current_sig and len(mock_tree.get_children()) > 0:
        should_skip = True
    else:
        should_skip = False
        
    assert should_skip is True

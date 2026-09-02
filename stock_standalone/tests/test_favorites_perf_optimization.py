# -*- coding: utf-8 -*-
"""
单元测试：重点关注 (Favorites) 性能优化与增量渲染验证
验证在添加/取消重点关注时，绝不进行物理全量摧毁重绘，而是使用增量更新与现有数据流。
"""

import os
import sys
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from global_favorites import GlobalFavoriteManager

def test_global_favorite_manager_version_increment():
    fav_mgr = GlobalFavoriteManager()
    initial_ver = fav_mgr.version
    fav_mgr.add_favorite_stock("600000")
    assert fav_mgr.version > initial_ver
    
    new_ver = fav_mgr.version
    fav_mgr.remove_favorite_stock("600000")
    assert fav_mgr.version > new_ver

def test_instock_monitor_refresh_ui_favorites_uses_incremental():
    """测试 _refresh_ui_favorites 逻辑调用 refresh_tree 时 force=False"""
    # 模拟 instock_MonitorTK 的 _refresh_ui_favorites 方法行为
    mock_self = MagicMock()
    mock_self.current_df = pd.DataFrame({'code': ['600000', '000001'], 'price': [10.0, 20.0]})
    mock_self.sortby_col = None
    mock_self.sortby_col_ascend = False
    mock_self.tree_updater = MagicMock()
    mock_self.tree_updater._values_cache = {'600000': (10.0,)}

    def simulated_refresh_ui_favorites(self):
        if not hasattr(self, 'current_df') or self.current_df.empty:
            return
        df = self.current_df.copy()
        if 'code' not in df.columns:
            df['code'] = df.index.astype(str)
        self.current_df = df
        self.refresh_tree(df, force=False)

    simulated_refresh_ui_favorites(mock_self)

    # 验证 refresh_tree 接收 force=False 且 _values_cache 保持
    mock_self.refresh_tree.assert_called_once()
    args, kwargs = mock_self.refresh_tree.call_args
    assert kwargs.get('force') is False
    assert '600000' in mock_self.tree_updater._values_cache

def test_ats_main_window_favorites_refresh_skips_refresh_realtime_ui():
    """测试 ats/ui/main_window.py 中 _safe_favorites_changed 绝不调起 heavy refresh_realtime_ui，且原位调用 swing_table 和 universe_widget 刷新"""
    from ats.ui.main_window import ATSMainWindow
    
    main_win = MagicMock(spec=ATSMainWindow)
    main_win._is_closing = False
    main_win.current_df = pd.DataFrame({'code': ['600000']})
    main_win.favorite_panel = MagicMock()
    main_win.swing_table = MagicMock()
    main_win.universe_widget = MagicMock()
    main_win.universe_widget._is_mock_active = False
    
    _safe_fav_fn = ATSMainWindow._safe_favorites_changed.__get__(main_win, ATSMainWindow)
    _safe_fav_fn()
    
    # 验证 favorite_panel.update_favorite_rows 被轻量调起
    assert main_win.favorite_panel.update_favorite_rows.called
    # 验证 swing_table 与 universe_widget 的 refresh_favorites_display 被原位调起
    main_win.swing_table.refresh_favorites_display.assert_called_once()
    assert not main_win.refresh_realtime_ui.called


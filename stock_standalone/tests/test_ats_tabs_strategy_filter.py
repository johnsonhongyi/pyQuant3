# -*- coding: utf-8 -*-
"""
tests/test_ats_tabs_strategy_filter.py
验证 ATS 主界面三大 Tab 看板 (重点关注 FavoritePanel, 回调跟踪器 SwingStateTable, 新股次新股 NewStockPanel) 
的 "🎯 策略过滤 (开/关)" 选项按钮、持久化记忆与策略联动过滤能力。
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication
from ats.ui.favorite_panel import FavoritePanel
from ats.ui.swing_table import SwingStateTable
from ats.ui.new_stock_panel import NewStockPanel
from ats.ui.styles import load_config_node, save_config_node

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_favorite_panel_strategy_filter(qapp):
    """测试 ⭐ 重点关注 面板的 🎯 策略过滤 按钮与联动过滤"""
    save_config_node("ats_tab_filter_enabled", "false")
    panel = FavoritePanel()
    
    # 初始状态
    assert hasattr(panel, 'btn_toggle_filter')
    assert panel.filter_enabled is False
    assert "关" in panel.btn_toggle_filter.text()
    
    # 模拟数据
    mock_rows = [
        ("600001", "邯郸钢铁", "10.0", "持股中", "+1.2%", "0", "10%", "早盘", "85.0", "1.0", "10", "1.0", "1.0", "+0.5%", "共振", "测试1"),
        ("600002", "齐鲁石化", "20.0", "持股中", "+2.5%", "0", "10%", "早盘", "80.0", "1.0", "20", "1.0", "1.0", "+0.5%", "共振", "测试2"),
    ]
    panel.update_favorite_rows(mock_rows)
    assert panel.table.rowCount() == 2
    assert panel.table.isRowHidden(0) is False
    assert panel.table.isRowHidden(1) is False
    
    # 开启策略过滤
    panel.toggle_filter_state()
    assert panel.filter_enabled is True
    assert "开" in panel.btn_toggle_filter.text()
    assert load_config_node("ats_tab_filter_enabled") == "true"
    
    # 模拟主窗口只有 600001 命中策略
    mock_mw = MagicMock()
    mock_mw.filtered_codes_set = {"600001"}
    panel.parent = lambda: mock_mw
    
    panel._apply_row_visibility()
    assert panel.table.isRowHidden(0) is False
    assert panel.table.isRowHidden(1) is True
    assert "过滤后 1 只" in panel.count_label.text()
    
    # 关闭过滤
    panel.toggle_filter_state()
    assert panel.filter_enabled is False
    assert panel.table.isRowHidden(0) is False
    assert panel.table.isRowHidden(1) is False
    assert "过滤后" not in panel.count_label.text()


def test_swing_table_strategy_filter(qapp):
    """测试 📉 回调跟踪器 面板的 🎯 策略过滤 按钮与联动过滤"""
    save_config_node("ats_tab_filter_enabled", "true")
    table = SwingStateTable()
    assert table.filter_enabled is True
    assert "开" in table.btn_toggle_filter.text()
    
    # 加载 Mock 数据
    table.load_mock_data()
    assert table.table.rowCount() > 0
    
    # 模拟主窗口只有 600519 命中策略
    mock_mw = MagicMock()
    mock_mw.filtered_codes_set = {"600519"}
    table.parent = lambda: mock_mw
    
    table._apply_favorite_filter()
    # 600519 应可见，其余应隐藏
    row_600519 = -1
    for r in range(table.table.rowCount()):
        if table.table.item(r, 0).text().strip() == "600519":
            row_600519 = r
            break
    assert row_600519 >= 0
    assert table.table.isRowHidden(row_600519) is False
    
    for r in range(table.table.rowCount()):
        if r != row_600519:
            assert table.table.isRowHidden(r) is True


def test_new_stock_panel_strategy_filter(qapp):
    """测试 🆕 新股次新股 面板的 🎯 策略过滤 按钮与过滤执行"""
    save_config_node("ats_tab_filter_enabled", "false")
    mock_mw = MagicMock()
    mock_mw.filtered_codes_set = {"920093"}
    
    panel = NewStockPanel(main_window=mock_mw)
    assert panel.filter_enabled is False
    assert "关" in panel.btn_toggle_filter.text()
    
    panel.df_data = pd.DataFrame({
        "code": ["920093", "688808"],
        "name": ["信胜科技", "联讯仪器"],
        "price": [20.07, 81.88],
        "status": ["前5日(C)", "次新"],
        "listing_date": ["2026-08-21", "2026-04-24"],
        "apply_date": ["2026-08-12", "2026-04-14"],
        "issue_price": [14.35, 81.88],
        "pct": [2.5, 2.26],
        "turnover": [26.96, 3.51],
        "float_shares": [5.06, 435.9],
        "total_shares": [28.3, 2319.24],
        "amount": [1.35, 15.02]
    })
    
    panel._apply_filter()
    assert panel.table.rowCount() == 2
    
    # 开启策略过滤
    panel.toggle_filter_state()
    assert panel.filter_enabled is True
    assert "开" in panel.btn_toggle_filter.text()
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 0).text() == "920093"


def test_favorite_panel_initial_load(qapp):
    """测试 ⭐ 重点关注 面板启动时能自动从 GlobalFavoriteManager 加载基础重点关注清单"""
    from global_favorites import GlobalFavoriteManager
    fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
    
    panel = FavoritePanel()
    # 如果系统配置中有自选股，初始化后 rowCount 应大于 0，且不为 0
    if fav_stocks:
        assert panel.table.rowCount() == len(fav_stocks)
        assert f"共 {len(fav_stocks)} 只" in panel.count_label.text()


def test_ledger_worker_fav_rows_and_swing_rows_update(qapp):
    """测试 LedgerUpdateWorker 异步数据计算与全量重点股/回调股行情注入"""
    from ats.ui.main_window import LedgerUpdateWorker
    from ats.signal_ledger import SignalLedger
    from ats.volume_profiler import VolumeProfiler
    from ats.session_snapshot import SessionSnapshot
    from ats.swing_tracker import SwingTracker
    from ats.universe_manager import UniverseManager
    
    mock_df = pd.DataFrame({
        "code": ["000001", "600519", "300750"],
        "name": ["平安银行", "贵州茅台", "宁德时代"],
        "close": [12.34, 1850.0, 210.5],
        "percent": [2.5, 1.8, 3.2],
        "dff": [1.5, 2.0, 3.0],
        "dff2": [1.0, 1.5, 2.5],
        "dff3": [0.5, 1.0, 2.0],
        "Rank": [5, 12, 3],
        "ma20d": [12.0, 1800.0, 205.0],
        "ma5d": [12.2, 1820.0, 208.0],
    }).set_index("code")

    ledger = SignalLedger()
    vol_prof = VolumeProfiler()
    sess_snap = SessionSnapshot()
    swing_trk = SwingTracker()
    u_mgr = UniverseManager()
    
    fav_stocks = {"000001", "600519"}
    
    worker = LedgerUpdateWorker(
        df_all=mock_df,
        signal_ledger=ledger,
        volume_profiler=vol_prof,
        session_snapshot=sess_snap,
        swing_tracker=swing_trk,
        stock_history_cache={},
        price_pct_cache={},
        name_cache={},
        fav_stocks=fav_stocks,
        universe_manager=u_mgr,
        today_str="2026-08-26",
    )
    
    results = {}
    def _catch_results(swing_rows, fav_rows, sh_pct, alpha_signals, stats_str):
        results["swing_rows"] = swing_rows
        results["fav_rows"] = fav_rows
        results["stats_str"] = stats_str
        
    worker.results_ready.connect(_catch_results)
    worker.run()
    
    assert "fav_rows" in results
    assert len(results["fav_rows"]) == 2
    # 验证重点关注行中包含真实价格
    fav_codes = [r[0] for r in results["fav_rows"]]
    assert "000001" in fav_codes
    assert "600519" in fav_codes
    for r in results["fav_rows"]:
        if r[0] == "000001":
            assert r[2] == "12.34"
        elif r[0] == "600519":
            assert r[2] == "1850.00"
            
    # 测试注入给 FavoritePanel
    panel = FavoritePanel()
    panel.update_favorite_rows(results["fav_rows"])
    assert panel.table.rowCount() == 2
    assert panel.table.item(0, 2).text() in ("12.34", "1850.00")



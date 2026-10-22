# -*- coding: utf-8 -*-
"""
tests/test_multiday_pct_base_view.py — ATS 主窗口多日基准涨跌幅切换（1D昨收/2D前收/3D等）纯视图层联动测试
严格验证：
1. compute_base_day_percent 多日基准收益计算与缺失值优雅降级；
2. 重点关注面板、MA20d跟踪器与资金主线龙头中枢表头标签动态对齐 (DFF -> DFF(2D), 涨幅% -> 涨幅%(2D))；
3. LedgerUpdateWorker 视图生成与底层 SignalLedger 信号隔离性（底层 1D 真实涨跌幅 0 篡改）。
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock

from ats.ui.styles import compute_base_day_percent
from ats.ui.favorite_panel import get_ats_table_headers
from ats.ui.new_stock_panel import get_new_stock_table_headers
from ats.capital_dragon_engine import get_dragon_table_headers
from ats.signal_ledger import SignalLedger
from ats.ledger_update_service import LedgerUpdateService
from ats.ui.main_window import LedgerUpdateWorker


def test_compute_base_day_percent_1d_default():
    """测试 1D 默认基准计算 (兼容 dff / percent / 昨收计算)"""
    # 优先取已有的 dff
    row1 = {'close': 11.0, 'lastp1d': 10.0, 'dff': 9.85, 'percent': 10.0}
    assert compute_base_day_percent(row1, base_day=1) == 9.85

    # 无 dff 时取 percent
    row2 = {'close': 11.0, 'lastp1d': 10.0, 'percent': 10.0}
    assert compute_base_day_percent(row2, base_day=1) == 10.0

    # 无 dff 与 percent 时根据 lastp1d 动态计算
    row3 = {'close': 11.0, 'lastp1d': 10.0}
    assert compute_base_day_percent(row3, base_day=1) == 10.0


def test_compute_base_day_percent_multiday_2d_and_3d():
    """测试 2D(2日强), 3D(3日强) 及多日累计涨跌幅计算"""
    # 2D: (11.0 - 9.0) / 9.0 * 100 = 22.22%
    row = {
        'close': 11.0,
        'percent': 10.0,
        'dff': 10.0,
        'lastp1d': 10.0,
        'lastp2d': 9.0,
        'lastp3d': 8.0,
        'lastp5d': 7.0,
    }
    pct_2d = compute_base_day_percent(row, base_day=2)
    assert round(pct_2d, 2) == 22.22

    # 3D: (11.0 - 8.0) / 8.0 * 100 = 37.50%
    pct_3d = compute_base_day_percent(row, base_day=3)
    assert round(pct_3d, 2) == 37.50

    # 5D: (11.0 - 7.0) / 7.0 * 100 = 57.14%
    pct_5d = compute_base_day_percent(row, base_day=5)
    assert round(pct_5d, 2) == 57.14


def test_compute_base_day_percent_fallback_safety():
    """测试多日字段缺失或为 0 时的平滑降级（绝不抛出异常中断主循环）"""
    # 缺失 lastp2d，平滑降级为当日 percent
    row_missing = {'close': 11.0, 'percent': 9.5, 'dff': 9.5, 'lastp1d': 10.0}
    assert compute_base_day_percent(row_missing, base_day=2) == 9.5

    # lastp2d 为 0 或非法字符，平滑降级为当日 percent
    row_invalid = {'close': 11.0, 'percent': 8.8, 'dff': 8.8, 'lastp2d': 0.0}
    assert compute_base_day_percent(row_invalid, base_day=2) == 8.8

    # 裸 dict 为空或 None
    assert compute_base_day_percent(None, base_day=2, current_price=10.0) == 0.0


def test_table_headers_dynamic_adaptation():
    """测试各面板表头在基准日变化时的动态自适应标签"""
    extra_cols = ['amount', 'volume']

    # 重点关注面板 (FavoritePanel)
    headers_1d = get_ats_table_headers(extra_cols=extra_cols, base_day=1)
    assert 'DFF' in headers_1d
    assert 'DFF(2D)' not in headers_1d

    headers_2d = get_ats_table_headers(extra_cols=extra_cols, base_day=2)
    assert 'DFF(2D)' in headers_2d
    assert 'DFF' not in headers_2d

    headers_3d = get_ats_table_headers(extra_cols=extra_cols, base_day=3)
    assert 'DFF(3D)' in headers_3d

    # 新股次新股面板 (NewStockPanel) - 与重点关注对齐使用 DFF 呈现
    new_headers_1d = get_new_stock_table_headers(extra_cols=extra_cols, base_day=1)
    assert 'DFF' in new_headers_1d
    assert 'DFF(2D)' not in new_headers_1d

    new_headers_2d = get_new_stock_table_headers(extra_cols=extra_cols, base_day=2)
    assert 'DFF(2D)' in new_headers_2d
    assert 'DFF' not in new_headers_2d

    new_headers_3d = get_new_stock_table_headers(extra_cols=extra_cols, base_day=3)
    assert 'DFF(3D)' in new_headers_3d

    # 资金主线与龙头中枢 (CapitalDragonEngine / CapitalDragonPanel) - 还原为原逻辑，表头严格为 涨幅%
    dragon_headers = get_dragon_table_headers(extra_cols=[])
    assert '涨幅%' in dragon_headers
    assert '涨幅%(2D)' not in dragon_headers


def test_worker_view_calculation_and_signal_isolation():
    """测试 LedgerUpdateWorker 在 base_day=2 时的视图计算与底层信号完全隔离"""
    import datetime
    from ats.signal_ledger import SignalEntry
    ledger = SignalLedger()
    today_s = datetime.date.today().strftime('%Y-%m-%d')
    # 预置一个信号条目，模拟已有持仓/自选/监控标的 (TRADE 状态受跨日保护)
    entry_init = SignalEntry(code='600001', name='特异测试股', price=10.0, pct=0.0, deviation=0.0, phase='TRADE')
    entry_init.tier = 'TRADE'
    entry_init._date_str = today_s
    ledger.entries['600001'] = entry_init
    update_service = LedgerUpdateService(ledger)

    df_data = {
        '600001': {
            'close': 11.0,
            'price': 11.0,
            'percent': 10.0,
            'dff': 10.0,
            'lastp1d': 10.0,
            'lastp2d': 9.0,
            'ma20d': 10.5,
            'amount': 500000000,
        }
    }
    df_all = pd.DataFrame.from_dict(df_data, orient='index')

    mock_volume_profiler = MagicMock()
    mock_volume_profiler.market_context.is_rebound_from_shrink = False
    mock_volume_profiler.get_volume_score.return_value = 1.0

    mock_snapshot = MagicMock()
    mock_snapshot.should_snapshot.return_value = False

    mock_swing_tracker = MagicMock()
    mock_swing_tracker.update_stock_state.return_value = ('MA20企稳', '+4.76%', '持股', '测试理由')

    mock_universe = MagicMock()
    mock_universe.radar_pool = {}
    mock_universe.watch_pool = {}
    mock_universe.trade_pool = {}

    worker = LedgerUpdateWorker(
        df_all=df_all,
        signal_ledger=ledger,
        volume_profiler=mock_volume_profiler,
        session_snapshot=mock_snapshot,
        swing_tracker=mock_swing_tracker,
        stock_history_cache={},
        price_pct_cache={},
        name_cache={'600001': '特异测试股'},
        fav_stocks=['600001'],
        universe_manager=mock_universe,
        today_str='2026-10-22',
        ledger_update_service=update_service,
        pct_base_day=2,  # 传入 2D 基准日
    )

    # 捕获 results_ready 发射的数据
    ready_results = []
    worker.results_ready.connect(lambda s_rows, f_rows, sh_p, a_sigs, s_str: ready_results.append((s_rows, f_rows)))

    # 同步调用 run
    worker.run()

    assert len(ready_results) == 1
    swing_rows, fav_rows = ready_results[0]
    assert len(swing_rows) >= 1

    # 校验展示层 swing_rows 的第 9 列 (DFF 列) 为 2D 累计涨跌幅 22.22%
    row_600001 = next(r for r in swing_rows if r[0] == '600001')
    display_dff_str = row_600001[9]
    assert display_dff_str == '22.22', f"Expected 22.22%, got {display_dff_str}"

    # 核心红线校验：底层 SignalLedger 中的 latest_pct 必须严格保持 1D 真实行情 10.0%，绝对不能被篡改
    entry = ledger.entries.get('600001')
    assert entry is not None
    assert round(entry.latest_pct, 2) == 10.0, f"Core signal corrupted! Expected 10.0%, got {entry.latest_pct}"


def test_new_stock_panel_multiday_dff_adaptation():
    """测试新股次新股面板 (NewStockPanel) 适配 2D 基准日的 DFF 多日累计涨幅与排序"""
    from ats.ui.new_stock_panel import _prepare_stock_table
    df_data = pd.DataFrame([{
        'code': '301600',
        'name': '次新测试股',
        'status': '次新股',
        'price': 11.0,
        'pct': 10.0,
        'dff': 9.8,
        'lastp1d': 10.0,
        'lastp2d': 9.0,
        'turnover': 15.0,
        'listing_date': '2026-10-15',
    }])

    # 1. 默认 base_day=1，dff 保持原有数值
    records_1d, _, _, _, _ = _prepare_stock_table(
        df_data, fav_stocks=set(), sh_pct=0.0, extra_cols=(),
        filter_type='全部', search_txt='', fset=None,
        sort_col=None, sort_order=None, selected_code='', base_day=1
    )
    assert len(records_1d) == 1
    assert records_1d[0]['dff'] == 9.8

    # 2. 切换至 base_day=2，dff 自动计算为 2D 累计涨跌幅 (11.0 - 9.0)/9.0*100 = 22.22%
    records_2d, _, _, _, _ = _prepare_stock_table(
        df_data, fav_stocks=set(), sh_pct=0.0, extra_cols=(),
        filter_type='全部', search_txt='', fset=None,
        sort_col=None, sort_order=None, selected_code='', base_day=2
    )
    assert len(records_2d) == 1
    assert round(records_2d[0]['dff'], 2) == 22.22

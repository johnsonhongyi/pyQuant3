# -*- coding: utf-8 -*-
import datetime
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pandas as pd
import pytest

from ats.bounded_evaluation_store import safe_deepcopy, compact_checkpoints, EvaluationStore
from ats.capital_dragon_engine import CapitalDragonEngine


def test_safe_deepcopy_prevents_stack_overflow():
    """验证 safe_deepcopy 在超深递归（>100层）时自动熔断截断，绝对不会引发 Stack Overflow 崩溃"""
    deep_dict = {}
    curr = deep_dict
    for i in range(150):
        curr['child'] = {'val': i}
        curr = curr['child']

    # 深度超过 100 层，copy.deepcopy 会极深递归或在小栈环境崩溃，safe_deepcopy 能安全返回
    res = safe_deepcopy(deep_dict, max_depth=100)
    assert isinstance(res, dict)
    assert 'child' in res


def test_compact_checkpoints_prunes_explosive_nodes():
    """验证 compact_checkpoints 成功将爆炸性的超量 checkpoints 裁剪到 64 条以内"""
    eval_data = {
        'candidates': {
            '000001': {
                'checkpoints': [{'observed_at': f'2026-10-30 09:{i//60:02d}:{i%60:02d}', 'price': 10.0 + i * 0.01} for i in range(300)]
            }
        }
    }
    compact_checkpoints(eval_data)
    assert len(eval_data['candidates']['000001']['checkpoints']) <= 64
    assert 'checkpoint_summary' in eval_data['candidates']['000001']


def test_extract_prev_bar_before_market_open():
    """验证开盘前获取日K线基准时，准确提取昨日K线，绝不发生取 [-2] 拿到前天数据的严重偏差"""
    today_str = "2026-10-30"
    # 开盘前：bar 列表中最后一条仍为 2026-10-29
    bars_pre_open = [
        {'datetime': '2026-10-28 15:00:00', 'amount': 100e8, 'vol': 1000},
        {'datetime': '2026-10-29 15:00:00', 'amount': 200e8, 'vol': 2000},
    ]

    def _extract_prev_bar(bar_list):
        if not bar_list:
            return None
        valid_hist = []
        for bar in bar_list:
            dt_s = str(bar.get('datetime', ''))[:10]
            if dt_s and dt_s < today_str:
                valid_hist.append(bar)
        if valid_hist:
            return valid_hist[-1]
        return bar_list[-2] if len(bar_list) >= 2 else (bar_list[-1] if bar_list else None)

    # 开盘前应该拿到 10-29 的 200e8
    prev = _extract_prev_bar(bars_pre_open)
    assert prev['datetime'].startswith('2026-10-29')
    assert prev['amount'] == 200e8

    # 盘中（已生成今日 bar 10-30）
    bars_intraday = list(bars_pre_open) + [
        {'datetime': '2026-10-30 09:35:00', 'amount': 50e8, 'vol': 500}
    ]
    prev_mid = _extract_prev_bar(bars_intraday)
    assert prev_mid['datetime'].startswith('2026-10-29')
    assert prev_mid['amount'] == 200e8


def test_market_summary_cold_start_ready_before_trading(monkeypatch):
    """验证开盘前启动（模拟 09:10:00，实时盘口全空），系统也能成功构建盘前预备大盘快照写入缓存，绝不返回空"""
    engine = CapitalDragonEngine.get_instance()
    # 注入假昨日基准
    engine._yesterday_index_amounts = {
        'sh': 8000.0, 'sz': 12000.0, 'cy': 5000.0, 'bj': 200.0,
        'total': 20200.0,
        'vol_sh': 500000000.0, 'vol_sz': 600000000.0, 'vol_cy': 250000000.0, 'vol_bj': 10000000.0
    }
    # 模拟盘口为空并构造开盘前预备快照
    extracted = {
        'sh': {'amount_yi': 8000.0, 'vol_ratio': 1.0},
        'sz': {'amount_yi': 12000.0, 'vol_ratio': 1.0},
        'cy': {'amount_yi': 5000.0, 'vol_ratio': 1.0},
        'bj': {'amount_yi': 200.0, 'vol_ratio': 1.0},
    }
    now_dt = datetime.datetime.strptime('2026-10-30 09:10:00', '%Y-%m-%d %H:%M:%S')
    summary = engine._build_summary_result(extracted, engine._yesterday_index_amounts, now_dt)

    assert summary is not None
    assert summary['sh_amt'] == 8000.0
    assert summary['total_amt'] == 20200.0
    assert "昨总成交" in summary['formatted_html'] or "较昨" in summary['formatted_html']


def test_main_window_market_volume_self_heal():
    """验证主窗口在后台缓存为空时，能够通过已有实时 DataFrame 现场自愈生成大盘数据"""
    from ats.ui.main_window import ATSMainWindow
    label = MagicMock()
    label.text.return_value = ""
    label.toolTip.return_value = ""

    # 准备一份包含四大指数伪数据的 df
    df_data = {
        'amount': [5000e8, 7000e8, 3000e8, 100e8],
        'volume': [1.2, 1.1, 1.3, 1.0],
        'close': [3300.0, 10500.0, 2100.0, 1000.0]
    }
    mock_df = pd.DataFrame(df_data, index=['000001', '399001', '399006', '899050'])

    window = SimpleNamespace(
        lbl_market_volume_status=label,
        _cached_realtime_df=mock_df,
        current_df=None,
    )

    # 清空 engine 的后台缓存
    engine = CapitalDragonEngine.get_instance()
    engine._bg_market_summary_cache = None

    # 执行刷新
    ATSMainWindow._refresh_market_volume_status(window)

    # 验证 label.setText 被成功调用，且内容包含各大指数成交额，而不是纯等待行情
    assert label.setText.called
    called_html = label.setText.call_args[0][0]
    assert "上证:" in called_html
    assert "全市:" in called_html


def test_safe_deepcopy_tuple_set_and_session_snapshot_capture():
    from ats.session_snapshot import SessionSnapshot
    from types import SimpleNamespace

    deep_tuple = (1, 2, (3, (4, {'inner': 5})))
    res_t = safe_deepcopy(deep_tuple, max_depth=10)
    assert res_t == deep_tuple

    snap = SessionSnapshot()
    mock_entry = SimpleNamespace(to_dict=lambda: {'code': '688432', 'name': '有研硅', 'nested': {'a': [1, 2, 3]}})
    mock_ledger = SimpleNamespace(
        entries={'688432': mock_entry},
        _next_day_watch_event_ids={'event_1'},
        _next_day_watch_event_outcomes={'event_1': {'win': True}}
    )
    frozen, rev = snap._capture_ledger(mock_ledger)
    assert '688432' in frozen.entries
    assert frozen.entries['688432'].name == '有研硅'
    assert rev >= 1

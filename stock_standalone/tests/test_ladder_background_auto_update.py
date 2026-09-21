# -*- coding: utf-8 -*-
"""
stock_standalone/tests/test_ladder_background_auto_update.py
验证天梯底层引擎在后台自动运行、解耦Tab激活依赖、就地初筛与瞬时渲染保障
"""
import pytest
import os
import sys
import time
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from ats.limit_up_engine import LimitUpEngine
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _build_mock_market_df():
    """构建包含涨停、连板与普通标的的实时行情 DataFrame"""
    data = [
        {
            "code": "600001",
            "name": "龙头股份",
            "trade": 12.10,
            "close": 12.10,
            "last_close": 11.00,
            "percent": 10.00,
            "open": 11.20,
            "high": 12.10,
            "low": 11.10,
            "vol": 200000.0,
            "amount": 240000000.0,
            "dff": 1.2,
            "DFF2": 15.0,
            "DFF3": 25.0,
            "Rank": 1,
            "category": "超短核心;连板龙头"
        },
        {
            "code": "000002",
            "name": "万科A",
            "trade": 9.50,
            "close": 9.50,
            "last_close": 9.40,
            "percent": 1.06,
            "open": 9.45,
            "high": 9.60,
            "low": 9.35,
            "vol": 100000.0,
            "amount": 95000000.0,
            "dff": -0.5,
            "DFF2": 0.0,
            "DFF3": 0.0,
            "Rank": 50,
            "category": "房地产"
        },
        {
            "code": "300003",
            "name": "特锐德",
            "trade": 24.00,
            "close": 24.00,
            "last_close": 20.00,
            "percent": 20.00,
            "open": 21.00,
            "high": 24.00,
            "low": 20.80,
            "vol": 150000.0,
            "amount": 360000000.0,
            "dff": 2.5,
            "DFF2": 30.0,
            "DFF3": 50.0,
            "Rank": 2,
            "category": "充电桩;创业板龙"
        }
    ]
    df = pd.DataFrame(data)
    df.set_index("code", drop=False, inplace=True)
    return df


def test_limit_up_engine_background_update_snapshot():
    """验证 LimitUpEngine.update_live_snapshot 可以在后台直接运行且 0ms 填充底座"""
    engine = LimitUpEngine.get_instance()
    df = _build_mock_market_df()

    # 强制清空当前内存实时记录
    with engine._cache_lock:
        engine._current_live_records = []
        engine._last_scan_time = 0.0

    # 触发后台快照更新（无需 L2 盘口网络 IO）
    records = engine.update_live_snapshot(df, fetch_l2_quotes=False, min_interval_sec=0.0)

    assert len(records) >= 2
    codes = [r["code"] for r in records]
    assert "600001" in codes
    assert "300003" in codes

    # 验证内存全局底座已被更新
    with engine._cache_lock:
        assert len(engine._current_live_records) >= 2


def test_aggregate_multi_day_strong_stocks_fallback_with_df():
    """验证多日强势与天梯聚合在今日记录为空时能够就地提取今日涨停"""
    engine = LimitUpEngine.get_instance()
    df = _build_mock_market_df()

    # 人为清空今日实时记录
    with engine._cache_lock:
        engine._current_live_records = []
        engine._last_scan_time = 0.0

    # 传入 current_df，应自动就地初筛补齐
    strong_stocks = engine.aggregate_multi_day_strong_stocks(days=5, min_limit_ups=1, current_df=df)
    assert len(strong_stocks) >= 2
    codes = [s["code"] for s in strong_stocks]
    assert "600001" in codes
    assert "300003" in codes


def test_daily_limit_up_dialog_ensure_rendered(qapp):
    """验证 DailyLimitUpDialog ensure_rendered 能够在挂起激活时瞬间补齐渲染"""
    dlg = DailyLimitUpDialog(parent=None)
    df = _build_mock_market_df()

    # 模拟窗口未激活，先挂起数据
    dlg.hide()
    dlg.is_hidden_state = False
    dlg.update_data_payload(df, sh_pct=1.5)

    assert dlg._needs_render is True

    # 模拟激活窗口或切换 Tab 调用 ensure_rendered
    dlg.ensure_rendered()

    assert dlg._needs_render is False
    assert dlg.current_records is not None
    assert len(dlg.current_records) >= 2
    assert dlg.table.rowCount() >= 2

    dlg.close()


def test_daily_limit_up_dialog_intraday_time_slice_zt_protection(qapp):
    """验证即使处于盘中非定龙时间片，真实涨停股票也绝不会被误杀"""
    dlg = DailyLimitUpDialog(parent=None)
    
    # 模拟带有涨停标志的测试记录
    mock_records = [
        {"code": "600001", "name": "龙头股份", "pct": 10.0, "is_limit_up": True, "entry_stage": ""},
        {"code": "300003", "name": "特锐德", "pct": 20.0, "is_limit_up": True, "entry_stage": ""},
        {"code": "000002", "name": "普通股", "pct": 1.0, "is_limit_up": False, "entry_stage": ""}
    ]
    dlg.current_records = mock_records
    dlg.current_mode = "TODAY"
    dlg.combo_time_slice.setCurrentText("☕ 盘中定型 (10:00-11:30)")

    # 执行过滤，时间片不论为何种盘中类型，真实涨停标的均应保留
    dlg._apply_filter()

    row_codes = []
    for r in range(dlg.table.rowCount()):
        item = dlg.table.item(r, 0)
        if item:
            row_codes.append(item.text().strip())

    assert "600001" in row_codes
    assert "300003" in row_codes
    assert "000002" not in row_codes

    dlg.close()

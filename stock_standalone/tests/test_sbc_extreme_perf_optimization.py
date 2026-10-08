# -*- coding: utf-8 -*-
"""
tests/test_sbc_extreme_perf_optimization.py
验证 SBC 极限性能优化核心指标：
1. 2400 根 Bar 策略推演纯 NumPy 向量化重构，确保策略买卖信号绝对零漂移 (Zero-Drift) 与毫秒级运算
2. 买卖信号可视索引映射预缓存加速与 O(1) 检索
3. 成交量差分拆分与常驻列提取一致性
4. 鼠标悬停 30ms 严格时间窗节流与防抖
5. UI 主线程网络与 HTTP 阻塞消除 (后台异步/内存字典兜底)
6. 窗口重排避免冗余 Win32 EnumWindows 遍历
"""

import sys
import os
import time
import pytest
import numpy as np
import pandas as pd
import threading
from dataclasses import asdict
from PyQt6.QtGui import QPainter, QPixmap
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.new_stock_fetcher import NewStockFetcher
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui import intraday_strategy_dialog as sbc
from ats.vwap_trading_engine import VWAPTradingEngine
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QMouseEvent

from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    SBCChartCanvas,
    SBCWindowMemoryManager,
    rearrange_all_sbc_windows
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _generate_synthetic_multi_day_bars(num_days=10, bars_per_day=240):
    """生成包含跨日的多日分时仿真数据 (总计 2400 根 Bar)"""
    records = []
    base_price = 100.0
    dates = [f"2026-09-{d:02d}" for d in range(1, num_days + 1)]
    
    for d_idx, d_str in enumerate(dates):
        cur_p = base_price + d_idx * 1.5
        for b_idx in range(bars_per_day):
            hh = 9 + (b_idx * 60) // 3600
            mm = (b_idx * 60 % 3600) // 60
            t_str = f"{d_str} {hh:02d}:{mm:02d}:00"
            noise = np.sin(b_idx / 20.0) * 1.2 + (b_idx % 7) * 0.1
            p = round(max(1.0, cur_p + noise), 2)
            hi = round(p + 0.3, 2)
            lo = round(p - 0.3, 2)
            op = p
            vol = 100.0 + (b_idx % 10) * 10
            amt = p * vol * 100.0
            records.append({
                "time": t_str,
                "date": d_str,
                "datetime": t_str,
                "open": op,
                "high": hi,
                "low": lo,
                "close": p,
                "vwap": p,
                "vol": vol,
                "volume": vol,
                "amount": amt,
            })
    df = pd.DataFrame(records).set_index("time")
    return df


def test_vwap_proactive_strategy_vectorization_zero_drift():
    """验证 _eval_vwap_proactive_strategy 向量化重构：买卖信号完全一致，冷算 < 800ms，热命中 < 3ms"""
    df_bars = _generate_synthetic_multi_day_bars(num_days=10, bars_per_day=240)
    assert len(df_bars) == 2400

    state = SimpleNamespace(code="688826")
    
    # 预热并测量向量化执行耗时
    t0 = time.perf_counter()
    signals = SBCIntradayChartDialog._eval_vwap_proactive_strategy(state, df_bars, period_mode="10d")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert isinstance(signals, list)
    assert elapsed_ms < 800.0, f"策略评估耗时过长: {elapsed_ms:.2f} ms"

    # 热缓存再次评估
    cached_samples = []
    for _ in range(7):
        t1 = time.perf_counter()
        signals_cached = SBCIntradayChartDialog._eval_vwap_proactive_strategy(state, df_bars, period_mode="10d")
        cached_samples.append((time.perf_counter() - t1) * 1000.0)
    cached_ms = float(np.median(cached_samples))
    assert cached_ms < 3.0, f"热命中耗时过长: {cached_ms:.2f} ms"
    assert signals == signals_cached

    # 验证信号关键字段结构
    for sig in signals:
        assert "action" in sig
        assert "price" in sig
        assert "time" in sig
        assert "trade_id" in sig
        assert sig["price"] > 0

    actions = [s["action"] for s in signals]
    assert "sell" in actions, "买卖信号完整，验证未退化为单一 day_0"
    reference = df_bars.copy()
    reference["date"] = reference["datetime"].str[:10]
    expected = SBCIntradayChartDialog._eval_vwap_proactive_strategy(
        SimpleNamespace(code="688826"), reference, period_mode="10d")
    assert signals == expected, "日期回退必须保持信号字段一致"
    
def test_signal_index_mapping_cache(qapp):
    """验证 _map_signal_to_visible_index 预缓存加速与精准匹配"""
    canvas = SBCChartCanvas(None)
    df_bars = _generate_synthetic_multi_day_bars(num_days=3, bars_per_day=240)
    canvas.df_intraday = df_bars

    sig_valid = {"time": str(df_bars.index[150]), "action": "buy"}
    sig_outside = {"time": str(df_bars.index[500]), "action": "sell"}
    sig_unknown = {"time": "2099-01-01 09:30:00", "action": "buy"}

    df_view = df_bars.iloc[100:300]
    
    # 命中视口
    idx1 = canvas._map_signal_to_visible_index(sig_valid, df_view, start_i=100, end_i=300)
    assert idx1 == 50  # 150 - 100

    # 视口外
    idx2 = canvas._map_signal_to_visible_index(sig_outside, df_view, start_i=100, end_i=300)
    assert idx2 is None

    # 未知时间
    idx3 = canvas._map_signal_to_visible_index(sig_unknown, df_view, start_i=100, end_i=300)
    assert idx3 is None

    # 连续调用 100 次，验证缓存命中加速
    t0 = time.perf_counter()
    for _ in range(100):
        canvas._map_signal_to_visible_index(sig_valid, df_view, start_i=100, end_i=300)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 10.0, f"100次索引映射耗时过长: {elapsed_ms:.2f} ms"

    canvas.close()


def test_volume_bar_extraction_caching(qapp):
    """验证 _extract_intraday_bar_volumes 常驻列预计算与提取一致性"""
    canvas = SBCChartCanvas(None)
    df_bars = _generate_synthetic_multi_day_bars(num_days=2, bars_per_day=240)
    
    vols1 = canvas._extract_intraday_bar_volumes(df_bars)
    assert len(vols1) == len(df_bars)
    assert isinstance(vols1, np.ndarray)
    assert np.all(vols1 >= 0)

    # 验证预计算常驻列直接切片
    df_bars["_bar_vol_computed"] = vols1
    vols2 = canvas._extract_intraday_bar_volumes(df_bars)
    assert np.array_equal(vols1, vols2)

    canvas.close()


def test_mouse_hover_strict_throttling(qapp):
    """验证 mouseMoveEvent 的 30ms 严格时间窗节流，阻断位移 >3px 穿透缺陷"""
    canvas = SBCChartCanvas(None)
    canvas.resize(600, 400)
    canvas.show()

    update_mock = MagicMock()
    canvas.update = update_mock

    now = time.time()
    canvas._last_hover_update_t = now
    canvas._last_hover_pos = QPoint(100, 100)

    # 1. 紧随其后在 1ms 内移动 10px (位移 > 3px，但未达 30ms 最小间隔)
    event1 = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(110.0, 110.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(event1)
    # 应被严格节流拦截，不触发 update
    assert update_mock.call_count == 0

    # 2. 模拟经过 35ms 后再次移动
    canvas._last_hover_update_t = now - 0.035
    event2 = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(115.0, 115.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(event2)
    # 达到 30ms 窗口且有位移，放行 update
    assert update_mock.call_count == 1

    canvas.close()


def test_ui_thread_no_network_blocking(qapp):
    """验证 run_adaptive_strategy_eval 与 update_amplitude_data 在主线程不发生同步网络阻塞"""
    canvas = SBCChartCanvas(None)
    canvas.df_intraday = pd.DataFrame()  # 空数据
    canvas.code = "688826"
    canvas.period_mode = "60m"

    with patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.fetch_kline_bars") as mock_fetch:
        mock_fetch.side_effect = AssertionError("UI线程严禁同步调用 fetch_kline_bars！")
        
        # 即使数据为空，也不应在主线程同步调用网络拉取
        canvas.run_adaptive_strategy_eval()
        assert canvas.strategy_eval_result is not None
        assert not canvas.strategy_eval_result.get("is_matched")

        # 振幅补全同样严禁在主线程同步直连
        canvas.update_amplitude_data("688826")

    canvas.close()


def test_signal_layout_caching_and_zero_collision_overhead(qapp):
    """验证分时图与 K 线图买卖信号 2D 防碰撞避让布局缓存：视口与几何不变时 0ms 复用，0 次重复碰撞检测"""
    from PyQt6.QtGui import QPixmap, QPainter

    canvas = SBCChartCanvas(None)
    canvas.resize(800, 600)
    df_bars = _generate_synthetic_multi_day_bars(num_days=2, bars_per_day=240)
    canvas.df_intraday = df_bars
    canvas.code = "688826"
    canvas.period_mode = "1m"

    # 注入 10 个测试买卖信号
    signals = []
    for i in range(10):
        t_key = str(df_bars.index[20 + i * 20])
        signals.append({
            "trade_id": i + 1,
            "action": "buy" if i % 2 == 0 else "sell",
            "price": float(df_bars["close"].iloc[20 + i * 20]),
            "time": t_key,
            "pnl_pct": 2.5 if i % 2 == 1 else None
        })
    canvas.signals = signals

    pixmap = QPixmap(800, 600)
    painter = QPainter(pixmap)

    try:
        # 1. 首次渲染分时图：触发布局计算
        canvas._paint_intraday(painter, 50, 20, 700, 500)
        assert hasattr(canvas, "_cached_intraday_layout_token")
        assert hasattr(canvas, "_cached_intraday_layout_items")
        assert len(canvas._cached_intraday_layout_items) == 10
        first_token = canvas._cached_intraday_layout_token
        first_items = canvas._cached_intraday_layout_items

        # 2. 第二次模拟鼠标悬停查价重绘：视口、几何与信号未变，必须严格 0ms 复用布局
        canvas._paint_intraday(painter, 50, 20, 700, 500)
        assert canvas._cached_intraday_layout_token == first_token
        assert canvas._cached_intraday_layout_items is first_items

        # 3. 切换为 K 线模式 (5m) 并测试 K 线布局缓存
        canvas.period_mode = "5m"
        canvas._paint_kline(painter, 50, 20, 700, 500)
        assert hasattr(canvas, "_cached_kline_layout_token")
        assert hasattr(canvas, "_cached_kline_layout_items")
        kline_token = canvas._cached_kline_layout_token
        kline_items = canvas._cached_kline_layout_items

        # 4. 第二次渲染 K 线图：必须 100% 命中缓存对象
        canvas._paint_kline(painter, 50, 20, 700, 500)
        assert canvas._cached_kline_layout_token == kline_token
        assert canvas._cached_kline_layout_items is kline_items
    finally:
        painter.end()
        canvas.close()


def test_p1_3_empty_date_datetime_fallback_and_multi_day_signals(qapp):
    """P1-3 专项回归：验证 date 为空时正确回退至 datetime 且跨日多天信号正常生成 (Zero-Drift)"""
    num_days = 10
    bars_per_day = 240
    records = []
    base_price = 100.0
    dates = [f"2026-09-{d:02d}" for d in range(1, num_days + 1)]

    for d_idx, d_str in enumerate(dates):
        cur_p = base_price + d_idx * 2.0
        for b_idx in range(bars_per_day):
            hh = 9 + (b_idx * 60) // 3600
            mm = (b_idx * 60 % 3600) // 60
            time_only = f"{hh:02d}:{mm:02d}"
            t_full = f"{d_str} {hh:02d}:{mm:02d}:00"
            noise = np.sin(b_idx / 15.0) * 1.5
            p = round(max(1.0, cur_p + noise), 2)
            records.append({
                "time": time_only,  # 索引仅包含时分
                "date": "",         # 故意置空，触发 datetime 回退
                "datetime": t_full, # 完整时间包含真实跨日日期
                "open": p,
                "high": p + 0.5,
                "low": p - 0.5,
                "close": p,
                "vwap": p,
                "vol": 100.0,
                "volume": 100.0,
                "amount": p * 10000.0,
            })
    df_bars = pd.DataFrame(records).set_index("time")
    assert len(df_bars) == 2400

    dlg = SBCIntradayChartDialog(None, code="688826", initial_period_mode="10d")
    signals = dlg._eval_vwap_proactive_strategy(df_bars, period_mode="10d")

    actions = [s["action"] for s in signals]
    # 必须成功识别跨日交易日，并生成买入与卖出两类信号
    assert "buy" in actions, "必须包含买入信号"
    assert "sell" in actions, "必须包含跨日卖出信号，证明未退化为单一的 day_0"
    dlg.close()


def test_p1_4_alt_period_batch_sync_updates_dispatcher(qapp):
    """P1-4 专项回归：验证 Alt 批量切周期后 SBCGlobalDispatcher 订阅关系同步更新，后续分发不被丢弃"""
    from ats.ui.intraday_strategy_dialog import sync_all_open_sbc_period, SBCGlobalDispatcher

    dlg1 = SBCIntradayChartDialog(None, code="688826", initial_period_mode="1m")
    dlg2 = SBCIntradayChartDialog(None, code="688827", initial_period_mode="1m")
    dlg1._dispatcher_enabled = True
    dlg2._dispatcher_enabled = True

    mgr = SBCWindowMemoryManager.get_instance()
    mgr.register(dlg1)
    mgr.register(dlg2)

    dispatcher = SBCGlobalDispatcher.get_instance()
    dispatcher.subscribe(dlg1)
    dispatcher.subscribe(dlg2)

    # 验证初始订阅为 1m
    with dispatcher._lock:
        sub_modes = [mode for _, _, mode in dispatcher._subscribers.values()]
    assert all(m == "1m" for m in sub_modes)

    # 触发批量切换至 day 周期
    sync_all_open_sbc_period("day", trigger_dlg=dlg1)

    assert dlg1._current_period_mode == "day"
    assert dlg2._current_period_mode == "day"

    # 核心断言：调度器内订阅必须已更新为 day
    with dispatcher._lock:
        updated_modes = [mode for _, _, mode in dispatcher._subscribers.values()]
    assert all(m == "day" for m in updated_modes), f"订阅未更新为 day: {updated_modes}"

    # 模拟分发批次
    reload_mock = MagicMock()
    dlg1.reload_chart = reload_mock
    dlg1.show()  # 确保 isVisible 为 True

    batch = {
        "688826": {"modes": ("day",), "df": pd.DataFrame()}
    }
    dispatcher._deliver_batch(batch)
    assert reload_mock.call_count == 1, "day 周期实时批次未被成功接收，仍被拒收丢弃"

    dlg1.close()
    dlg2.close()


def test_p1_5_tdx_cached_kline_bars_interface():
    """P1-5 专项回归：验证 TDXRealtimeFetcher.get_cached_kline_bars 只读缓存接口与 TTL/代码隔离"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    fetcher = TDXRealtimeFetcher.get_instance()

    # 1. 无缓存时安全返回 None，严禁发起网络调用
    cached = fetcher.get_cached_kline_bars("999999", "day")
    assert cached is None

    # 2. 模拟填入缓存
    dummy_df = pd.DataFrame({
        "open": [10.0, 11.0],
        "close": [10.5, 11.5],
        "high": [11.0, 12.0],
        "low": [9.8, 10.8]
    }, index=["2026-09-01", "2026-09-02"])

    if not hasattr(fetcher, "_kline_bars_cache"):
        fetcher._kline_bars_cache = {}
    fetcher._kline_bars_cache[("999999", "day", 8)] = (time.time(), dummy_df)

    # 3. 只读接口成功命中返回数据
    hit_df = fetcher.get_cached_kline_bars("999999", "day", min_count=2)
    assert hit_df is not None
    assert len(hit_df) == 2
    assert "close" in hit_df.columns

    # 4. 异类周期或不同代码不串扰
    assert fetcher.get_cached_kline_bars("999999", "5m") is None
    assert fetcher.get_cached_kline_bars("888888", "day") is None

    # 清理测试缓存
    fetcher._kline_bars_cache.pop(("999999", "day", 8), None)


def test_p1_1_and_p1_2_headless_fetch_and_workbench_safety(qapp, monkeypatch):
    """P1-1 & P1-2 专项回归：验证 fetch_stock_realtime_data_headless 纯数据安全性与工作台异步装载释放 busy"""
    from ats.ui.intraday_strategy_dialog import (
        fetch_stock_realtime_data_headless,
        PinzhunLadderStandaloneWindow,
        AllCodesStrategyEvalDialog
    )
    import threading
    from ats.ui import intraday_strategy_dialog as sbc
    from ats.new_stock_fetcher import NewStockFetcher
    from ats.intraday_strategy_engine import IntradayStrategyEngine
    from PyQt6.QtCore import QThread

    # UI 回调使用替身隔离真实取数
    monkeypatch.setattr(sbc, "resolve_stock_name", lambda code: f"测试_{code}")
    monkeypatch.setattr(NewStockFetcher, "get_instance", lambda: MagicMock(_cached_ipo_dict={}))
    monkeypatch.setattr(IntradayStrategyEngine, "is_stock_unlisted", lambda self, code: False)
    monkeypatch.setattr(IntradayStrategyEngine, "save_intraday_cache", lambda *args, **kwargs: True)
    fetcher = MagicMock()
    fetcher.fetch_stock_snapshot.return_value = {
        "open_price": 100.0, "price": 101.0, "high_price": 102.0,
        "low_price": 99.0, "vwap": 100.5, "turnover_rate": 2.0,
        "amount": 1000000.0, "bid1_price": 100.9, "last_close": 99.0,
    }
    fetcher.fetch_intraday_bars.return_value = pd.DataFrame()
    fetcher.is_connected = False
    fetcher.current_host = object()
    fetcher.latency_ms = object()
    yesterday_threads = []
    def yesterday_in_worker(code):
        yesterday_threads.append(QThread.currentThread())
        return {}
    fetcher.get_cached_yesterday_ohlc.return_value = {}
    fetcher.get_yesterday_ohlc.side_effect = yesterday_in_worker
    monkeypatch.setattr(sbc.TDXRealtimeFetcher, "get_instance", lambda: fetcher)

    wb = PinzhunLadderStandaloneWindow("688826", "测试标的")
    assert "默认 (0ms)" in wb.lbl_tdx_status.text()
    wb.show()
    monkeypatch.setattr(wb.engine, "get_all_target_codes", lambda: ["600108", "688826"])

    # 1. 验证 headless 函数在子线程中调用，绝不依赖任何 QWidget
    result_container = []
    def _subthread_fetch():
        res = fetch_stock_realtime_data_headless(
            "688826",
            engine=wb.engine,
            tdx_fetcher=wb.tdx_fetcher,
            data_source="TDX_REALTIME"
        )
        result_container.append(res)

    t = threading.Thread(target=_subthread_fetch)
    t.start()
    t.join(timeout=2.0)
    assert len(result_container) == 1
    assert len(result_container[0]) == 11

    # 2. 验证工作台 request_refresh_data 异步流与 _is_tick_fetching 释放
    wb.request_refresh_data(hydrate_intraday=False)
    # 模拟事件循环调度
    for _ in range(50):
        QApplication.processEvents()
        if not wb._is_tick_fetching:
            break
        time.sleep(0.01)
    assert not wb._is_tick_fetching, "工作台异步取数后 _is_tick_fetching 必须被释放为 False"

    # 3. 验证 AllCodesStrategyEvalDialog 后台评估不篡改工作台 SpinBox 且正常完成
    eval_dlg = AllCodesStrategyEvalDialog(wb)
    initial_spin_val = wb.spin_eval_open.value()

    eval_dlg.run_evaluation()
    assert eval_dlg._is_evaluating, "评估启动后 _is_evaluating 为 True"

    for _ in range(100):
        QApplication.processEvents()
        if not eval_dlg._is_evaluating:
            break
        time.sleep(0.02)

    assert not eval_dlg._is_evaluating, "全量评估完成后 _is_evaluating 必须被安全释放为 False"
    assert wb.spin_eval_open.value() == initial_spin_val, "工作台的估价 SpinBox 绝不能被后台遍历评估篡改"
    assert len(eval_dlg.cards_data) == 2, "卡片数据必须被正常填充 2 只标的"
    assert yesterday_threads, "昨日 OHLC 应当在后台预取"
    assert all(thread != qapp.thread() for thread in yesterday_threads), "真实运行下不可在 UI 线程查询昨日 OHLC"

    eval_dlg.close()
    wb.close()


# Startup performance and correctness closure.
def bars(count=400):
    rng = np.random.default_rng(24)
    close = 10 + np.cumsum(rng.normal(0, 0.02, count))
    return pd.DataFrame({"date": ["2026-10-08"] * count, "open": close + 0.01,
                         "high": close + 0.08, "low": close - 0.08, "close": close,
                         "vwap": close + rng.normal(0, 0.03, count), "vol": np.arange(count) + 1.0},
                        index=pd.date_range("2026-10-08 09:30", periods=count, freq="min"))


def test_same_rule_is_atomic_across_workers():
    entered, release = threading.Event(), threading.Event()
    class PausedRule(dict):
        def get(self, key, default=None):
            if key == "trigger_expr":
                entered.set()
                assert release.wait(2)
            return super().get(key, default)
    rule = PausedRule(rule_id="race", trigger_expr="price > 0", sell_ratio=0.3)
    engine = IntradayStrategyEngine.__new__(IntradayStrategyEngine)
    engine.rule_state_map = {}
    engine.is_stock_unlisted = lambda code: False
    engine.get_open_price_tier = lambda *a, **k: ("normal", 0, "standard")
    engine.get_current_phase = lambda *a: ({"rules": [rule]}, 0)
    engine.mark_dirty = lambda: None
    engine.save_intraday_cache = lambda **k: True
    results, failures = [], []
    def evaluate():
        try:
            results.extend(engine.evaluate_tick("600108", {"trade": 10.1}, 10, "10:00", strategy={}))
        except Exception as exc:
            failures.append(exc)
    first, second = threading.Thread(target=evaluate), threading.Thread(target=evaluate)
    first.start()
    assert entered.wait(1)
    second.start()
    release.set()
    first.join(2)
    second.join(2)
    assert not first.is_alive() and not second.is_alive() and not failures
    assert len(results) == 1
    assert engine.rule_state_map["600108"]["remaining_ratio"] == pytest.approx(0.7)


@pytest.mark.parametrize("include_missing", [False, True])
def test_prepared_features_equal_streaming_state(include_missing):
    frame = bars(700)
    if include_missing:
        frame.loc[frame.index[::37], "close"] = 0
        frame.loc[frame.index[::41], "vwap"] = 0
    reference = VWAPTradingEngine(rule_model=SimpleNamespace(), arbiter=object())
    prepared = VWAPTradingEngine(rule_model=SimpleNamespace(), arbiter=object())
    prepared._prepare_replay_features("600108", *(frame[key].to_numpy() for key in
                                                  ("open", "high", "low", "close", "vwap")))
    for i, row in enumerate(frame.itertuples()):
        if row.close <= 0:
            continue
        states = []
        for engine in (reference, prepared):
            engine.update_minute_bar("600108", i * 60, row.open, row.high, row.low, row.close, row.vol, row.vwap)
            states.append(asdict(engine.compute_tick_state("600108", row.close, row.vwap)))
        for key, value in states[0].items():
            if isinstance(value, float):
                assert states[1][key] == pytest.approx(value, abs=1e-12)
            else:
                assert states[1][key] == value


def test_strategy_cache_reuses_copy_and_detects_history_and_rule_changes(monkeypatch):
    # 实际规则模型用于评估；单独保留引用以模拟热重载。
    from ats.vwap_rule_model import VWAPRuleModel
    model = VWAPRuleModel()
    state = SimpleNamespace(code="600108", _vwap_engine_cache=SimpleNamespace(rule_model=model))
    frame = bars()
    detect = MagicMock(return_value={})
    monkeypatch.setattr(sbc, "detect_vwap_displacement_reversal", detect)
    evaluate = sbc.SBCIntradayChartDialog._eval_vwap_proactive_strategy
    first = evaluate(state, frame)
    assert evaluate(state, frame.copy()) is first
    assert detect.call_count == 1
    revised = frame.copy()
    revised.iloc[0, revised.columns.get_loc("high")] += 2
    assert evaluate(state, revised) is not first
    assert detect.call_count == 2
    last = state._cached_vwap_signals
    model._raw_config = dict(model._raw_config, cache_probe="changed")
    assert evaluate(state, revised.copy()) is not last
    assert detect.call_count == 2


def test_preview_precedes_strategy_and_channel_and_can_cancel(monkeypatch):
    frame = bars(20)
    fetcher = MagicMock()
    fetcher.fetch_stock_snapshot.return_value = {"open_price": 10, "price": 10.1}
    fetcher.fetch_multi_horizon_vwap.return_value = (frame, {})
    monkeypatch.setattr(sbc.TDXRealtimeFetcher, "get_instance", lambda: fetcher)
    monkeypatch.setattr(NewStockFetcher, "refresh_ipo_calendar_background", lambda: None)
    monkeypatch.setattr(sbc, "resolve_stock_name", lambda code: "测试")
    monkeypatch.setattr(sbc.SBCIndicatorCache, "get", lambda *a: None)
    events = []
    state = SimpleNamespace(engine=None, _channel_overlay_enabled=True)
    state._eval_vwap_proactive_strategy = lambda *a, **k: events.append("strategy") or []
    state._fetch_channel_info_static = lambda *a: events.append("channel") or None
    load = sbc.SBCIntradayChartDialog._do_fetch_chart_data
    result = load(state, "600108", "10d", on_preview=lambda payload: events.append("preview"))
    assert events == ["preview", "channel", "strategy"]
    assert result["df_target"].equals(frame) and not result.get("is_preview")
    events.clear()
    cancelled = threading.Event()
    def preview(payload):
        events.append("preview")
        cancelled.set()
    result = load(state, "600108", "10d", on_preview=preview, is_cancelled_func=cancelled.is_set)
    assert result["is_cancelled"] and events == ["preview"]


def test_preview_keeps_worker_busy_and_rejects_old_epoch():
    state = SimpleNamespace(code="600108", _load_epoch=2, _current_period_mode="10d",
                            _load_inflight=True, _pending_load=None, _apply_chart_payload=MagicMock())
    arrive = sbc.SBCIntradayChartDialog._on_async_chart_data_arrived
    payload = {"is_preview": True}
    arrive(state, 1, "600108", "10d", payload)
    state._apply_chart_payload.assert_not_called()
    arrive(state, 2, "600108", "10d", payload)
    state._apply_chart_payload.assert_called_once()
    assert state._load_inflight


def test_static_layer_reuse_and_selection_invalidation(qapp, monkeypatch):
    canvas = sbc.SBCChartCanvas()
    canvas.resize(800, 560)
    canvas.code = "600108"
    canvas.set_data(bars(20), open_p=10)
    paints = []
    def paint(*args):
        paints.append(True)
        canvas._signal_hit_boxes = [{"trade_id": 1}]
    monkeypatch.setattr(canvas, "_paint_intraday", paint)
    monkeypatch.setattr(canvas, "_draw_amplitude_hud", lambda *a: None)
    image = QPixmap(800, 560)
    painter = QPainter(image)
    try:
        canvas._draw_chart_static_layer(painter, 50, 20, 700, 500)
        canvas._signal_hit_boxes = []
        canvas._draw_chart_static_layer(painter, 50, 20, 700, 500)
        assert len(paints) == 1 and canvas._signal_hit_boxes == [{"trade_id": 1}]
        canvas.selected_trade_id = 1
        canvas._draw_chart_static_layer(painter, 50, 20, 700, 500)
        assert len(paints) == 2
    finally:
        painter.end()
        canvas.close()


def test_pixel_simplification_preserves_column_extremes():
    values = np.sin(np.arange(1000))
    columns = np.repeat(np.arange(100), 10)
    indices = sbc._pixel_extreme_indices(values, columns)
    assert len(indices) <= 202 and indices[0] == 0 and indices[-1] == 999
    for column in range(100):
        original = values[columns == column]
        retained = values[indices[columns[indices] == column]]
        assert retained.min() == original.min() and retained.max() == original.max()


def test_fast_tdx_selection_does_not_wait_for_slow_probe(monkeypatch, tmp_path):
    import ats.tdx_realtime_fetcher as tdx
    import sys_utils
    release = threading.Event()
    finished = threading.Event()
    monkeypatch.setattr(tdx, "get_all_tdx_hosts", lambda: [("fast", "1", 7709), ("slow", "2", 7709)])
    monkeypatch.setattr(sys_utils, "get_app_root", lambda: str(tmp_path))
    state = SimpleNamespace(_conn_lock=threading.RLock(), add_log=MagicMock())
    def probe(host):
        if host[0] == "slow":
            release.wait(2)
            finished.set()
        return (10.0, *host)
    state._ping_single_host = probe
    try:
        TDXRealtimeFetcher._init_best_server(state)
        assert state.current_host[0] == "fast" and not finished.is_set()
    finally:
        release.set()
        assert finished.wait(1)


def test_cached_name_and_ipo_do_not_initialize_or_request(monkeypatch):
    import sys_utils
    monkeypatch.setattr(NewStockFetcher, "_instance", None)
    monkeypatch.setattr(NewStockFetcher, "get_instance", MagicMock(side_effect=AssertionError("no initialization")))
    assert NewStockFetcher.get_cached_ipo_calendar() == {}
    monkeypatch.setattr(sys_utils, "_resolved_name_cache", {})
    monkeypatch.setattr(sys_utils, "_SINA_ENGINE", MagicMock())
    assert sys_utils.get_cached_stock_name("600108") == "个股_600108"
    sys_utils._SINA_ENGINE.get_code_cname.assert_not_called()


def test_launcher_batches_windows_and_flushes_recents_once(qapp, monkeypatch, tmp_path):
    import json
    import run_sbc
    path = tmp_path / "layout.json"
    layout = {"initialized": True, "sbc_holdings_windows": [{"code": f"60010{i}"} for i in range(5)]}
    path.write_text(json.dumps(layout), encoding="utf-8")
    monkeypatch.setattr(run_sbc, "_get_launcher_layout_cfg_path", lambda: str(path))
    monkeypatch.setattr(sbc, "_get_sbc_layout_cfg_path", lambda: str(path))
    monkeypatch.setattr(sbc, "QSettings", MagicMock())
    monkeypatch.setattr(run_sbc, "_is_restoring_holdings", False)
    queue = []
    monkeypatch.setattr(run_sbc, "QTimer", SimpleNamespace(singleShot=lambda delay, callback: queue.append(callback)))
    persist = MagicMock(wraps=sbc._persist_sbc_recent_codes)
    monkeypatch.setattr(sbc, "_persist_sbc_recent_codes", persist)
    def open_window(parent, code, **kwargs):
        assert kwargs["record_open"] is False
        assert sbc._read_sbc_layout_config(str(path)) is layout_data[0]
        sbc._save_sbc_recent_code(code)
        return MagicMock(code=code)
    # 缓存对象来自读取后的配置，捕获首次共享对象。
    layout_data = []
    original_begin = sbc._begin_sbc_startup_batch
    def begin(path, data):
        layout_data.append(data)
        original_begin(path, data)
    monkeypatch.setattr(run_sbc, "_begin_sbc_startup_batch", begin)
    monkeypatch.setattr(run_sbc, "open_sbc_chart_dialog", open_window)
    windows = run_sbc.restore_launcher_holdings_windows()
    assert len(windows) == 2 and run_sbc._is_restoring_holdings and persist.call_count == 0
    while queue:
        queue.pop(0)()
    assert len(windows) == 5 and not run_sbc._is_restoring_holdings and persist.call_count == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["sbc_holdings_windows"] == layout["sbc_holdings_windows"]
    assert saved["sbc_recent_codes"] == [f"60010{i}" for i in range(4, -1, -1)]


@pytest.mark.parametrize("history_available,is_unlisted", [(True, False), (False, False), (False, True)])
def test_all_codes_ipc_snapshot_and_history_before_scoring(monkeypatch, history_available, is_unlisted):
    source = pd.DataFrame({"open": [10.0], "trade": [11.0]}, index=["600108"])
    engine, fetcher = MagicMock(), MagicMock()
    engine.get_all_target_codes.return_value = ["600108"]
    engine.auto_select_strategy.return_value = {"name": "test"}
    engine.get_stock_ladder_spec.return_value = {"float_mv_yi": 15, "issue_price": 10}
    engine.is_stock_unlisted.return_value = is_unlisted
    events, cards = [], []
    def snapshot(frame, code):
        assert frame is not source and frame.equals(source)
        return {"open_price": 10.0, "price": 11.0}
    engine.extract_market_snapshot_from_df.side_effect = snapshot
    fetcher.fetch_intraday_bars.return_value = bars(20) if history_available else pd.DataFrame()
    engine.hydrate_from_intraday_df.side_effect = lambda *a, **k: events.append("hydrate") or True
    engine.evaluate_tick.side_effect = lambda *a, **k: events.append("tick") or []
    engine.evaluate_seven_nodes.side_effect = lambda *a, **k: events.append("score") or {}
    workbench = SimpleNamespace(tdx_fetcher=fetcher, selected_data_source="ATS_IPC", _latest_df=source)
    state = SimpleNamespace(engine=engine, workbench=workbench, lbl_meta=MagicMock(),
                            _eval_finished=SimpleNamespace(emit=lambda results, *args: cards.extend(results)))
    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(sbc.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(sbc, "resolve_stock_name", lambda code: "测试")
    monkeypatch.setattr(sbc.TDXRealtimeFetcher, "get_instance", lambda: fetcher)
    sbc.AllCodesStrategyEvalDialog.run_evaluation(state)
    fetcher.fetch_stock_snapshot.assert_not_called()
    if history_available:
        assert events == ["hydrate", "tick", "score"] and not cards[0]["is_error"]
    elif is_unlisted:
        assert events == ["tick", "score"] and not cards[0]["is_error"]
        fetcher.fetch_intraday_bars.assert_not_called()
    else:
        assert events == [] and cards[0]["is_error"]


def test_memory_peek_has_no_disk_sync_and_rejects_stale_day():
    from ats.tdx_realtime_fetcher import TDXGlobalCachePool
    from datetime import datetime
    pool = TDXGlobalCachePool.__new__(TDXGlobalCachePool)
    pool._mutex = threading.RLock()
    frame = bars(20)
    pool._multi_day_df_cache = {("600108", 10): (frame, time.time(), datetime.now().strftime("%Y-%m-%d"))}
    pool._maybe_sync_from_ramdisk = MagicMock(side_effect=AssertionError("UI disk sync"))
    copy = pool.peek_multi_day_df("600108", 10)
    assert copy is not frame and copy.equals(frame)
    pool._multi_day_df_cache[("600108", 10)] = (frame, time.time(), "2000-01-01")
    assert pool.peek_multi_day_df("600108", 10) is None
    pool._maybe_sync_from_ramdisk.assert_not_called()


def test_cached_preview_does_not_initialize_tdx(monkeypatch):
    from datetime import datetime
    frame = bars(20)
    frame["date"] = datetime.now().strftime("%Y-%m-%d")
    pool = SimpleNamespace(peek_multi_day_df=lambda *a: frame.copy())
    monkeypatch.setattr(sbc.TDXGlobalCachePool, "_instance", pool)
    monkeypatch.setattr(sbc.TDXRealtimeFetcher, "get_instance", MagicMock(side_effect=AssertionError("UI initialization")))
    state = SimpleNamespace(code="600108", _current_period_mode="1m", _apply_chart_payload=MagicMock())
    sbc.SBCIntradayChartDialog._render_skeleton_or_cached_frame(state)
    payload = state._apply_chart_payload.call_args[0][0]
    assert payload["is_cached_preview"] and payload["is_preview"]
    assert payload["df_target"].equals(frame)


def test_listing_checks_only_read_cache_and_follow_calendar_revision(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(NewStockFetcher, "_instance", None)
    monkeypatch.setattr(TDXRealtimeFetcher, "_instance", None)
    monkeypatch.setattr(NewStockFetcher, "get_instance", MagicMock(side_effect=AssertionError("UI IPO initialization")))
    monkeypatch.setattr(TDXRealtimeFetcher, "get_instance", MagicMock(side_effect=AssertionError("UI TDX initialization")))
    engine = IntradayStrategyEngine.__new__(IntradayStrategyEngine)
    engine.get_stock_ladder_spec = lambda code: {}
    assert not engine.is_stock_first_listing_day("920199")
    assert not engine.is_stock_unlisted("920199")
    calendar = {"920199": {"listing_date": datetime.now().strftime("%Y-%m-%d"), "status": "首日(N)"}}
    monkeypatch.setattr(NewStockFetcher, "_instance", SimpleNamespace(_cached_ipo_dict=calendar, _last_calendar_fetch_time=1.0))
    assert engine.is_stock_first_listing_day("920199")
    assert not engine.is_stock_unlisted("920199")

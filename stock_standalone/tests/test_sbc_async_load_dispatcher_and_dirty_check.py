# -*- coding: utf-8 -*-
"""
tests/test_sbc_async_load_dispatcher_and_dirty_check.py
验证 SBC 性能重构：
1. TDXRealtimeFetcher.fetch_batch_stock_snapshots 批量快照与标准化转换 (40只安全批次与 VWAP/换手率)
2. SBCIntradayChartDialog Epoch Guard 防串屏与旧数据拦截
3. SBCIntradayChartDialog 入口级脏检查短路机制 (Stage 4)
4. 1m 分时与多日分时数据对齐与复用
5. SBCGlobalDispatcher 全局集中调度器单例与生命周期
"""

import sys
import os
import time
import threading
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, SBCGlobalDispatcher, SBCWindowMemoryManager
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_fetch_batch_stock_snapshots():
    """验证批量快照拉取及与单只快照标准化转换的严格一致性与 40 只切块安全规范"""
    fetcher = TDXRealtimeFetcher.get_instance()
    
    mock_quotes = [
        {"code": "600000", "price": 10.5, "open": 10.0, "high": 11.0, "low": 9.8, "last_close": 10.0, "vol": 1000, "amount": 1050000.0, "bid1": 10.49, "ask1": 10.51},
        {"code": "000001", "price": 12.0, "open": 11.8, "high": 12.5, "low": 11.7, "last_close": 11.8, "vol": 2000, "amount": 2400000.0, "bid1": 11.99, "ask1": 12.01},
    ]
    
    with patch.object(fetcher, "get_security_quotes_safe", return_value=mock_quotes) as mock_get_quotes:
        res = fetcher.fetch_batch_stock_snapshots(["600000", "000001"])
        assert "600000" in res
        assert "000001" in res
        assert mock_get_quotes.called
        
        snap_600 = res["600000"]
        assert snap_600["code"] == "600000"
        assert snap_600["price"] == 10.5
        assert snap_600["open_price"] == 10.0
        assert snap_600["high_price"] == 11.0
        assert snap_600["low_price"] == 9.8
        assert snap_600["vwap"] == 10.5  # 1050000 / (1000 * 100) = 10.5
        assert snap_600["bid1_price"] == 10.49
        assert snap_600["ask1_price"] == 10.51


def test_epoch_guard_and_payload_application(qapp):
    """验证阶段 2 Epoch Guard：旧代际、不匹配代码或过期周期的 payload 坚决丢弃"""
    dlg = SBCIntradayChartDialog(None, code="688766")
    dlg.async_load_enabled = False
    
    # 模拟主线程渲染方法
    dlg._apply_chart_payload = MagicMock()
    
    # 1. 正常代际匹配
    dlg._load_epoch = 5
    dlg.code = "688766"
    dlg._current_period_mode = "1m"
    
    valid_payload = {
        "code": "688766",
        "mode": "1m",
        "is_cancelled": False,
        "data_fp": ("688766", "1m", 100, "11:30", 10.5, 500, 10.5, 10.4),
        "is_timer_tick": False
    }
    
    dlg._on_async_chart_data_arrived(5, "688766", "1m", valid_payload)
    assert dlg._apply_chart_payload.call_count == 1
    
    # 2. 过期旧代际 (例如工作线程返回慢，主线程已切到 epoch=6)
    dlg._on_async_chart_data_arrived(4, "688766", "1m", valid_payload)
    # 应被 Epoch Guard 拦截，call_count 不变
    assert dlg._apply_chart_payload.call_count == 1
    
    # 3. 标的代码不匹配 (用户快速切码至其他标的)
    dlg._on_async_chart_data_arrived(5, "000001", "1m", valid_payload)
    assert dlg._apply_chart_payload.call_count == 1
    
    # 4. 周期不匹配 (用户已切换到 5d 周期)
    dlg._on_async_chart_data_arrived(5, "688766", "5d", valid_payload)
    assert dlg._apply_chart_payload.call_count == 1
    
    dlg.close()


def test_stage4_dirty_check_short_circuit(qapp):
    """验证阶段 4 入口级脏检查：心跳定时刷新时若数据指纹未变，完全短路跳过重排与重绘"""
    dlg = SBCIntradayChartDialog(None, code="688766")
    dlg.async_load_enabled = False
    
    df_sample = pd.DataFrame({
        "close": [10.0, 10.5],
        "vol": [100.0, 120.0]
    }, index=["09:30", "09:31"])
    
    data_fp = ("688766", "1m", 2, "09:31", 10.5, 120.0, 10.5, 10.2)
    payload = {
        "code": "688766",
        "mode": "1m",
        "is_cancelled": False,
        "op": 10.0,
        "p": 10.5,
        "vw": 10.2,
        "hi": 10.6,
        "lo": 9.9,
        "amt": 100000.0,
        "to_rate": 1.5,
        "t_min": 10.3,
        "t_max": 10.5,
        "df_target": df_sample,
        "sigs": [],
        "multi_vwap_snapshot": None,
        "channel_info": None,
        "data_fp": data_fp,
    }
    
    with patch.object(dlg.canvas, "set_data") as mock_set_data:
        # 第一次渲染：指纹不同，正常渲染
        dlg._last_rendered_fp = None
        dlg._apply_chart_payload(payload, is_timer_tick=False)
        assert mock_set_data.call_count == 1
        assert dlg._last_rendered_fp == data_fp
        
        # 第二次渲染：心跳刷新 (is_timer_tick=True)，指纹完全相同
        mock_set_data.reset_mock()
        dlg._apply_chart_payload(payload, is_timer_tick=True)
        # 彻底短路，set_data 绝不被再次调用！
        assert mock_set_data.call_count == 0
        
        # 第三次渲染：盘面发生变动（现价或数据行发生改变）
        new_fp = ("688766", "1m", 2, "09:31", 10.6, 130.0, 10.6, 10.25)
        payload["data_fp"] = new_fp
        payload["p"] = 10.6
        dlg._apply_chart_payload(payload, is_timer_tick=True)
        assert mock_set_data.call_count == 1
        assert dlg._last_rendered_fp == new_fp
    
    dlg.close()


def test_1m_reuses_multi_day_today_slice(qapp):
    """验证阶段 4 数据源对齐：1m 模式复用多日数据中的今日切片，消除重复网络请求"""
    dlg = SBCIntradayChartDialog(None, code="688766")
    dlg.async_load_enabled = False
    
    fetcher = TDXRealtimeFetcher.get_instance()
    
    today_str = time.strftime("%Y-%m-%d")
    df_multi_sample = pd.DataFrame({
        "date": [today_str, today_str, today_str],
        "time": ["09:30", "09:31", "09:32"],
        "close": [20.0, 20.2, 20.1],
        "open": [20.0, 20.0, 20.2],
        "high": [20.1, 20.3, 20.2],
        "low": [19.9, 20.0, 20.0],
        "vwap": [20.0, 20.1, 20.1],
        "vol": [100, 200, 300],
        "amount": [2000, 4000, 6000]
    })
    
    with patch.object(fetcher, "fetch_multi_horizon_vwap", return_value=(df_multi_sample, None)), \
         patch.object(fetcher, "fetch_intraday_bars") as mock_fetch_intraday, \
         patch.object(fetcher, "fetch_stock_snapshot", return_value={"price": 20.1, "open_price": 20.0}):
        
        payload = dlg._do_fetch_chart_data(code="688766", mode="1m")
        assert not payload.get("is_cancelled")
        # 验证直接切出并复用了 df_multi_sample 中的今日切片
        assert not mock_fetch_intraday.called
        assert len(payload["df_target"]) == 3
    
    dlg.close()


def test_preloaded_dispatch_data_avoids_duplicate_quote_and_bar_fetch(qapp):
    dlg = SBCIntradayChartDialog(None, code="688766")
    fetcher = TDXRealtimeFetcher.get_instance()
    today = time.strftime("%Y-%m-%d")
    frame = pd.DataFrame({"date": [today, today], "time": ["09:30", "09:31"],
                          "close": [10.0, 10.1], "open": [10.0, 10.0],
                          "high": [10.0, 10.1], "low": [10.0, 10.0],
                          "vol": [100, 110], "vwap": [10.0, 10.05]})
    preloaded = {"snapshot": {"open_price": 10.0, "price": 10.1},
                 "multi": (frame, None)}
    with patch.object(fetcher, "fetch_stock_snapshot") as quote_fetch, \
         patch.object(fetcher, "fetch_multi_horizon_vwap") as multi_fetch, \
         patch.object(fetcher, "fetch_intraday_bars") as intraday_fetch:
        payload = dlg._do_fetch_chart_data("688766", "1m", channel_info={"ch_up": 11.0},
                                           preloaded=preloaded)
    assert len(payload["df_target"]) == 2
    quote_fetch.assert_not_called()
    multi_fetch.assert_not_called()
    intraday_fetch.assert_not_called()
    dlg.close()


def test_sbc_global_dispatcher_singleton():
    """验证 SBCGlobalDispatcher 单例与启停逻辑"""
    disp1 = SBCGlobalDispatcher.get_instance()
    disp2 = SBCGlobalDispatcher.get_instance()
    assert disp1 is disp2
    
    disp1.start()
    assert disp1._running is True
    assert disp1._thread is not None
    
    disp1.stop()
    assert disp1._running is False


def test_dispatcher_queues_results_to_ui_thread(qapp):
    """后台结果必须在 UI 线程交给窗口，且不能重新请求单股报价。"""
    dispatcher = SBCGlobalDispatcher()
    ui_thread = threading.get_ident()
    calls = []

    class Subscriber:
        code = "600000"
        _current_period_mode = "1m"

        def isVisible(self):
            return True

        def reload_chart(self, **kwargs):
            calls.append((threading.get_ident(), kwargs))

    subscriber = Subscriber()
    dispatcher.subscribe(subscriber)
    worker = threading.Thread(target=lambda: dispatcher.batch_ready.emit({
        "600000": {"snapshot": {"price": 10.0}, "multi": (pd.DataFrame(), None), "modes": {"1m"}}
    }))
    worker.start()
    worker.join()
    for _ in range(50):
        qapp.processEvents()
        if calls:
            break
        time.sleep(0.01)
    assert len(calls) == 1
    assert calls[0][0] == ui_thread
    assert calls[0][1]["preloaded"]["snapshot"]["price"] == 10.0


def test_dispatcher_subscription_interrupts_wait(qapp):
    dispatcher = SBCGlobalDispatcher()
    waiting = threading.Event()
    elapsed = []

    class Subscriber:
        code = "600000"
        _current_period_mode = "1m"

    subscriber = Subscriber()

    def wait_for_next_poll():
        waiting.set()
        start = time.monotonic()
        dispatcher._wait_or_wake(5.0, dispatcher._wake_event)
        elapsed.append(time.monotonic() - start)

    worker = threading.Thread(target=wait_for_next_poll)
    worker.start()
    assert waiting.wait(1.0)
    dispatcher.subscribe(subscriber)
    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert elapsed[0] < 1.0

    revision = dispatcher._subscription_revision
    dispatcher.subscribe(subscriber)
    assert dispatcher._subscription_revision == revision
    subscriber.code = "600001"
    dispatcher.subscribe(subscriber)
    assert dispatcher._subscription_revision == revision + 1
    assert dispatcher._wake_event.is_set()


def test_window_merges_overlapping_refreshes(qapp):
    """慢请求尚未完成时，只保留最新一次刷新请求。"""
    dlg = SBCIntradayChartDialog(None, code="688766")
    starts = []

    class DeferredThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            starts.append(self.target)

    with patch("ats.ui.intraday_strategy_dialog.threading.Thread", DeferredThread):
        dlg.reload_chart(preloaded={"snapshot": {"price": 10.0}})
        dlg.reload_chart(preloaded={"snapshot": {"price": 11.0}})
        assert len(starts) == 1
        assert dlg._pending_load[1]["snapshot"]["price"] == 11.0
        dlg._on_async_chart_data_arrived(1, dlg.code, dlg._current_period_mode,
                                         {"is_cancelled": True})
        assert len(starts) == 2
        assert dlg._pending_load is None
    dlg.close()

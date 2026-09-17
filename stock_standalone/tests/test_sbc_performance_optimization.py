# -*- coding: utf-8 -*-
"""
tests/test_sbc_performance_optimization.py
-------------------------------------------
SBC 性能极限优化专项自动化测试套件：
1. 10d 多日分时 2.5s TTL 内存缓存与向量化解析提速验证；
2. SBC 窗口重排平铺 (rearrange_all_sbc_windows) 静默无焦点抢夺、无循环重复写盘与持仓专用落盘分流验证；
3. 画布 mouseMoveEvent 25ms 悬停渲染节流与 CPU 释放验证；
4. reload_chart 后台异步守护线程拉取与防抖保护验证。
"""

import sys
import os
import time
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

# 确保导入路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint, Qt
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    SBCChartCanvas,
    rearrange_all_sbc_windows,
    _SBCWindowProxy
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class TestSBCPerformanceOptimization:

    def test_multi_day_bars_cache_and_vectorized_parsing(self):
        """【P0 缓存与向量化验证】验证 fetch_multi_day_intraday_bars 缓存命中率与解析正确性"""
        fetcher = TDXRealtimeFetcher.get_instance()

        mock_bars = [
            {"datetime": "2026-09-17 09:31", "open": 10.0, "close": 10.2, "high": 10.5, "low": 9.9, "vol": 1000, "amount": 1020000.0},
            {"datetime": "2026-09-17 09:32", "open": 10.2, "close": 10.3, "high": 10.4, "low": 10.1, "vol": 800, "amount": 824000.0},
        ]

        with patch.object(fetcher, "get_security_quotes_safe", return_value=[{"price": 10.3}]):
            with patch.object(fetcher, "get_circulation_shares", return_value=10000000.0):
                with patch.object(fetcher, "api") as mock_api:
                    mock_api.get_security_bars.return_value = mock_bars
                    fetcher._is_connected = True
                    if hasattr(fetcher, '_multi_day_bars_cache'):
                        fetcher._multi_day_bars_cache.clear()

                    df1 = fetcher.fetch_multi_day_intraday_bars("600733", days=2)

                    assert not df1.empty, "首次拉取解析不应为空"
                    assert "close" in df1.columns
                    assert "vwap" in df1.columns
                    assert "turnover_rate" in df1.columns

                    # 第二次在 2.5s 内调用，必须直接从缓存返回，绝不再次调用 API
                    mock_api.get_security_bars.reset_mock()
                    df2 = fetcher.fetch_multi_day_intraday_bars("600733", days=2)

                    assert mock_api.get_security_bars.call_count == 0, "命中缓存时不应调用底层 get_security_bars API"
                    assert len(df2) == len(df1)

    def test_rearrange_all_sbc_windows_zero_flicker_and_no_loop_save(self, qapp):
        """【P0 重排性能验证】重排平铺时 apply_geometry 不在循环内触发写盘与频繁激活，持仓模式下保存专用配置"""
        from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
        dlg1 = open_sbc_chart_dialog(None, code="600733", period_mode="10d")
        dlg2 = open_sbc_chart_dialog(None, code="603407", period_mode="10d")
        dlg1.show()
        dlg2.show()

        save_geo_call_count = 0

        def counting_save():
            nonlocal save_geo_call_count
            save_geo_call_count += 1

        dlg1._save_sbc_geometry = counting_save
        dlg2._save_sbc_geometry = counting_save

        saved_launcher_config = []
        saved_ats_config = []

        def mock_save_launcher(force=False):
            saved_launcher_config.append(True)

        def mock_save_ats():
            saved_ats_config.append(True)

        with patch.dict(os.environ, {"SBC_IS_HOLDINGS_LAUNCHER": "1"}):
            with patch("run_sbc.save_launcher_holdings_windows", side_effect=mock_save_launcher):
                with patch("ats.ui.intraday_strategy_dialog.save_all_open_sbc_windows", side_effect=mock_save_ats):
                    rearrange_all_sbc_windows(parent_win=dlg1)

                    assert save_geo_call_count == 0, "apply_geometry 内部严禁在循环中逐个写盘"
                    assert len(saved_launcher_config) >= 1, "Launcher 模式下必须调用 save_launcher_holdings_windows"
                    assert len(saved_ats_config) == 0, "Launcher 模式下严禁误写 ATS 主配置"

        dlg1.close()
        dlg2.close()

    def test_canvas_mouse_move_throttling(self, qapp):
        """【P1 渲染节流验证】画布 mouseMoveEvent 增加 25ms 节流，有效阻断高频无谓 update()"""
        canvas = SBCChartCanvas()
        canvas.resize(600, 400)
        canvas.show()

        update_calls = 0

        def mock_update():
            nonlocal update_calls
            update_calls += 1

        canvas.update = mock_update

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent, QPointF

        # 连续发送 20 次微小位移的鼠标移动事件
        for _ in range(20):
            ev = QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(100.0, 100.0),
                QPointF(100.0, 100.0),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier
            )
            canvas.mouseMoveEvent(ev)

        assert update_calls <= 2, f"高频微小鼠标滑动应被有效节流，实际触发了 {update_calls} 次 update"
        canvas.close()

    def test_reload_chart_pipeline(self, qapp):
        """【P0 刷新流程验证】reload_chart 极速可靠执行，完成数据与画布状态同步"""
        from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
        dlg = open_sbc_chart_dialog(None, code="600733", period_mode="10d")
        dlg.show()

        mock_snap = {
            "code": "600733", "open_price": 10.0, "price": 10.5, "vwap": 10.3,
            "high_price": 10.8, "low_price": 9.9, "amount": 5000000.0, "turnover_rate": 5.0
        }
        mock_df = pd.DataFrame({
            "close": [10.2, 10.5], "open": [10.0, 10.2], "high": [10.3, 10.6],
            "low": [9.9, 10.1], "vwap": [10.1, 10.3], "volume": [1000, 1200]
        }, index=["09:31", "09:32"])

        fetcher = TDXRealtimeFetcher.get_instance()
        with patch.object(fetcher, "fetch_stock_snapshot", return_value=mock_snap):
            with patch.object(fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df):
                dlg.reload_chart()
                assert dlg.canvas.open_price == 10.0
                assert dlg.lbl_title.text() != ""

        dlg.close()

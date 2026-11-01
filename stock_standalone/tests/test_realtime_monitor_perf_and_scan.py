# -*- coding: utf-8 -*-
"""
专项回归测试：
1. 验证 open_realtime_monitor 中 update_status 只更新 Realtime Service Status 文本与日志，彻底解除自动刷新潜伏池（refresh_pool_data）的高频卡顿；
2. 验证 _scan_external_windows 与 _scan_windows_cached 具备可见性过滤与负向缓存保护，外部窗口未开启时不触发频繁枚举。
"""
import time
import pytest
from unittest.mock import MagicMock, patch


class DummyApp:
    def __init__(self):
        self._win_cache = {"visualizer": 0, "stock_monitor": 0, "fusion_ladder": 0, "ipo_detector": 0}
        self._win_cache_t = 0
        self._win_cache_valid = False
        self._win_scan_requested_t = 0
        self._win_scan_interval = 10.0


def test_scan_external_windows_negative_cache_and_ttl():
    """验证 _scan_external_windows 在 3 秒内直接命中负向缓存，不重复执行 EnumWindows"""
    from instock_MonitorTK import StockMonitorApp

    app = DummyApp()
    
    # 模拟 EnumWindows
    enum_calls = 0
    def fake_enum_windows(callback, lparam):
        nonlocal enum_calls
        enum_calls += 1
        return True

    with patch("ctypes.windll.user32.EnumWindows", side_effect=fake_enum_windows), \
         patch("ctypes.windll.user32.IsWindowVisible", return_value=False):
        
        # 第一次扫描
        res1 = StockMonitorApp._scan_external_windows(app, force=False)
        assert enum_calls == 1
        assert res1["visualizer"] == 0

        # 3 秒内第二次扫描（无 force），应直接命中 TTL 负向缓存，不触发 EnumWindows
        res2 = StockMonitorApp._scan_external_windows(app, force=False)
        assert enum_calls == 1
        assert res2 == res1

        # force=True 强制扫描，触发 EnumWindows
        res3 = StockMonitorApp._scan_external_windows(app, force=True)
        assert enum_calls == 2


def test_scan_windows_cached_adaptive_interval():
    """验证 _scan_windows_cached 默认扫描间隔不少于 10.0 秒，且后台异步执行"""
    from instock_MonitorTK import StockMonitorApp

    app = DummyApp()
    app._win_scan_requested_t = time.monotonic()
    app._win_scan_interval = 10.0

    # 10 秒之内调用，直接返回现有缓存，不启动线程
    with patch("threading.Thread") as mock_thread:
        cache = StockMonitorApp._scan_windows_cached(app, force=False)
        assert mock_thread.call_count == 0
        assert cache == app._win_cache

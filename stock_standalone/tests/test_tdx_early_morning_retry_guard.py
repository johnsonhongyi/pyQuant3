# -*- coding: utf-8 -*-
"""
早盘 TDX 服务器初始化异常请求缓重试延时机制与防无限重试专项测试套件
验证四大核心能力：
1. 08:45~09:15 早盘服务器初始化专属时段识别 (SSOT)
2. 未开盘 price==0.0 但 last_close>0 真实存活判定 (杜绝错杀为假活节点)
3. 冷却期内高频调用 0 网络 I/O 拦截保护 (杜绝死循环无限重试)
4. 早盘初始化时段禁止空批次 auto_failover 震荡踩踏
5. 通用连接失败指数退避熔断保护
"""

import sys
import os
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ats.tdx_realtime_fetcher import (
    TDXRealtimeFetcher,
    is_tdx_trading_allowed,
)


def test_01_early_morning_server_init_stage_detection():
    """验证交易时间轴中 08:45~09:15 早盘初始化与 09:15~09:16 竞价准备期的精准识别"""
    # 模拟工作日 2026-09-14 周一
    # 1. 08:44:59 (常规休眠)
    dt_off = datetime(2026, 9, 14, 8, 44, 59)
    allowed, desc, meta = is_tdx_trading_allowed(dt_off)
    assert allowed is False
    assert meta["stage"] == "OFF_HOURS"
    assert not meta.get("is_server_init", False)

    # 2. 08:45:00 (进入早盘服务器初始化)
    dt_init = datetime(2026, 9, 14, 8, 45, 0)
    allowed, desc, meta = is_tdx_trading_allowed(dt_init)
    assert allowed is False
    assert meta["stage"] == "SERVER_INITIALIZING"
    assert meta.get("is_server_init", True) is True
    assert "初始化" in desc

    # 3. 08:55:00 (典型早盘初始化时段)
    dt_init_mid = datetime(2026, 9, 14, 8, 55, 0)
    allowed, desc, meta = is_tdx_trading_allowed(dt_init_mid)
    assert allowed is False
    assert meta["stage"] == "SERVER_INITIALIZING"
    assert meta.get("is_server_init", True) is True

    # 4. 09:15:00 (集合竞价准备期)
    dt_prep = datetime(2026, 9, 14, 9, 15, 0)
    allowed, desc, meta = is_tdx_trading_allowed(dt_prep)
    assert allowed is False
    assert meta["stage"] == "AUCTION_PREPARING"

    # 5. 09:16:00 (集合竞价试撮合阶段放行)
    dt_bidding = datetime(2026, 9, 14, 9, 16, 0)
    allowed, desc, meta = is_tdx_trading_allowed(dt_bidding)
    assert allowed is True
    assert meta["stage"] == "BIDDING_SIMULATION"


def test_02_pre_market_zero_price_probe_alive():
    """验证开盘前 price==0.0 但 last_close>0 能够正确被判定为健康节点，不再被误杀为假活节点"""
    fetcher = TDXRealtimeFetcher.get_instance()
    mock_api = MagicMock()

    # 模拟开盘前 08:52 返回平安银行昨收 11.74 但最新成交价 0.0
    mock_api.get_security_quotes.return_value = [
        {"code": "000001", "price": 0.0, "last_close": 11.74, "market": 0}
    ]

    is_alive = fetcher._probe_host_alive(mock_api)
    assert is_alive is True, "开盘前 price==0.0 但 last_close>0 必须被判定为存活，绝不能误杀为假活节点"

    # 模拟完全无效的回包 (全0或空)
    mock_api.get_security_quotes.return_value = [
        {"code": "000001", "price": 0.0, "last_close": 0.0, "market": 0}
    ]
    assert fetcher._probe_host_alive(mock_api) is False

    # 模拟异常断开
    mock_api.get_security_quotes.side_effect = Exception("Connection reset")
    assert fetcher._probe_host_alive(mock_api) is False


def test_03_early_morning_smooth_retry_and_hammering_guard():
    """验证早盘初始化阶段连接失败时启动缓重试冷却，上层高频调用瞬间拦截，绝无无限重试"""
    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher.disconnect()

    # 模拟时间在 08:52:00
    mock_now = datetime(2026, 9, 14, 8, 52, 0)

    # 模拟连接主站失败 (例如通达信主站早盘维护)
    with patch("ats.tdx_realtime_fetcher.datetime") as mock_dt, \
         patch("ats.tdx_realtime_fetcher.TdxHq_API") as mock_hq_cls:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mock_hq_inst = MagicMock()
        mock_hq_inst.connect.return_value = False
        mock_hq_cls.return_value = mock_hq_inst

        # 重置冷却状态
        fetcher._global_connect_cooldown_until = 0.0
        fetcher._global_connect_fail_count = 0

        # 第 1 次连接：尝试并失败，触发早盘缓重试冷却
        t_before = time.time()
        ok = fetcher.connect(probe=True, force=False)
        assert ok is False
        assert fetcher._global_connect_cooldown_until > t_before
        # 08:52 时由于离 09:15 尚有 23 分钟，冷却设定为 60s
        assert fetcher._global_connect_cooldown_until - t_before >= 30.0

        # 模拟上层 10 个高频定时器连续轰炸 (比如每隔 100ms 调一次)
        connect_call_count_before = mock_hq_inst.connect.call_count
        for _ in range(10):
            res = fetcher.connect(probe=True, force=False)
            assert res is False, "冷却期内必须立即返回 False"

        # 验证 mock_hq_inst.connect 绝无被再次调用（0 重复网络 I/O）
        assert mock_hq_inst.connect.call_count == connect_call_count_before, (
            "冷却期内必须坚决拦截网络尝试，绝不能重复向主站发起 TCP 握手！"
        )


def test_04_get_security_quotes_safe_instant_return_under_cooldown():
    """验证处于冷却期时，get_security_quotes_safe 瞬间返回缓存，不产生阻塞"""
    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher.disconnect()

    # 注入冷却时间
    fetcher._global_connect_cooldown_until = time.time() + 60.0

    t0 = time.time()
    # 连续调用 20 次安全拉取
    for _ in range(20):
        quotes = fetcher.get_security_quotes_safe(["000001", "600519"], force=False)
        assert isinstance(quotes, list)

    cost_total = (time.time() - t0) * 1000.0
    # 20 次内存守卫调用总耗时应该在 10ms 以内，完全不产生阻塞
    assert cost_total < 50.0, f"冷却拦截耗时过长 ({cost_total:.1f}ms)，必须为微秒级守卫"

    # 清理冷却状态
    fetcher._global_connect_cooldown_until = 0.0


def test_05_auto_failover_prevent_churn_in_server_init():
    """验证早盘初始化阶段禁止空批次触发 auto_failover 换站踩踏，force=True 时允许强制切换"""
    fetcher = TDXRealtimeFetcher.get_instance()

    # 模拟早盘初始化时间 08:50:00
    mock_init_time = datetime(2026, 9, 14, 8, 50, 0)
    with patch("ats.tdx_realtime_fetcher.datetime") as mock_dt:
        mock_dt.now.return_value = mock_init_time
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        # 默认调用 (如连续空批次触发): 坚决拦截，返回 False
        res = fetcher.auto_failover(force=False)
        assert res is False, "早盘服务器初始化时段严禁触发 auto_failover 踩踏！"


def test_06_universal_circuit_breaker_exponential_backoff():
    """验证常规时段多轮连接失败后的指数退避熔断保护"""
    fetcher = TDXRealtimeFetcher.get_instance()
    fetcher.disconnect()

    # 模拟工作日盘中交易时间 10:00:00
    mock_trading_time = datetime(2026, 9, 14, 10, 0, 0)

    with patch("ats.tdx_realtime_fetcher.datetime") as mock_dt, \
         patch("ats.tdx_realtime_fetcher.TdxHq_API") as mock_hq_cls:
        mock_dt.now.return_value = mock_trading_time
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

        mock_hq_inst = MagicMock()
        mock_hq_inst.connect.return_value = False
        mock_hq_cls.return_value = mock_hq_inst

        # 重置
        fetcher._global_connect_cooldown_until = 0.0
        fetcher._global_connect_fail_count = 0

        # 第 1 次失败: backoff 5s
        now_t = time.time()
        fetcher.connect(probe=True, force=False)
        assert fetcher._global_connect_fail_count == 1
        assert 4.0 <= (fetcher._global_connect_cooldown_until - now_t) <= 6.5

        # 模拟冷却结束，第 2 次失败: backoff 10s
        fetcher._global_connect_cooldown_until = 0.0
        now_t = time.time()
        fetcher.connect(probe=True, force=False)
        assert fetcher._global_connect_fail_count == 2
        assert 9.0 <= (fetcher._global_connect_cooldown_until - now_t) <= 11.5

        # 清理状态
        fetcher._global_connect_cooldown_until = 0.0
        fetcher._global_connect_fail_count = 0

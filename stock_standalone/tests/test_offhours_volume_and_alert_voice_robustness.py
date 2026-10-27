# -*- coding: utf-8 -*-
"""
专项回归测试：
1. 验证 ATS 底部成交量等信息在非交易时间/休市时能从 current_df 正确提取并刷新状态栏；
2. 验证大盘全市成交额定时播报不受 30 分钟文本指纹防抖误杀，确保定时播报总是成功播报；
3. 验证 _check_market_volume_announcement 仅在成功播报后才消耗令牌，防数据为空时提前作废；
4. 验证 AlertNotifier 队列看门狗超时自愈机制，防止 11 点后或下午语音假死；
5. 验证 AlertNotifier 与 AlertManager 语音状态联动同步。
"""
import time
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QLabel

from ats.capital_dragon_engine import CapitalDragonEngine
from ats.alert_notifier import AlertNotifier
from alert_manager import AlertManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_offhours_market_summary_from_current_df(qapp):
    """验证非交易时段当后台 TDX 缓存为空时，能够从 current_df 兜底提取并生成有效成交额 HTML"""
    cde = CapitalDragonEngine.get_instance()
    # 模拟后台缓存为空
    cde._bg_market_summary_cache = None

    # 构建包含四大指数的 mock DataFrame
    data = [
        {"code": "999999", "name": "上证指数", "amount": 672414367744.0, "vol_ratio": 0.85, "price": 3648.3},
        {"code": "399001", "name": "深证成指", "amount": 788543897600.0, "vol_ratio": 0.96, "price": 11245.73},
        {"code": "399006", "name": "创业板指", "amount": 383305646080.0, "vol_ratio": 0.93, "price": 2548.15},
        {"code": "899050", "name": "北证50",   "amount": 12076132352.0,  "vol_ratio": 0.97, "price": 931.64},
    ]
    df_mock = pd.DataFrame(data)

    # 提取大盘摘要
    summary = cde.get_market_indices_and_volume_summary(df_all=df_mock)
    assert summary is not None
    assert summary["total_amt"] > 0
    # 上证 6724.1 + 深证 7885.4 + 北证 120.8 约为 14730 亿
    assert summary["sh_amt"] == pytest.approx(6724.14, rel=1e-2)
    assert summary["sz_amt"] == pytest.approx(7885.44, rel=1e-2)
    assert summary["bj_amt"] == pytest.approx(120.76, rel=1e-2)
    assert summary["cy_amt"] == pytest.approx(3833.06, rel=1e-2)
    assert "formatted_html" in summary
    assert "上证:" in summary["formatted_html"]
    assert "深证:" in summary["formatted_html"]
    assert "创业板:" in summary["formatted_html"]
    assert "北证:" in summary["formatted_html"]
    assert "全市:" in summary["formatted_html"]
    assert "14730" in summary["formatted_html"]


def test_market_volume_alert_exempt_from_fingerprint_debounce():
    """验证大盘全市成交额播报豁免 30 分钟文本结构指纹防抖"""
    mgr = AlertManager()
    mgr.enabled = True
    mgr.voice_enabled = True

    # 构造两条间隔不到 1800 秒但属于不同时刻的成交量播报文本
    msg1 = "全市成交额8500.5亿元，较昨放量500.2亿元，全天预估1.5万亿元。"
    msg2 = "全市成交额10500.8亿元，较昨放量600.5亿元，全天预估1.6万亿元。"

    # 清除历史
    mgr.message_cooldowns.clear()

    # 第一条发送
    with patch.object(mgr, '_do_send_alert') as mock_send:
        mgr.send_alert(msg1, priority=0)
        assert mock_send.called
        assert mock_send.call_args[0][0] == msg1

    # 第二条在紧随其后发送（模拟 30 分钟内再次播报相同结构指纹的成交额）
    with patch.object(mgr, '_do_send_alert') as mock_send2:
        mgr.send_alert(msg2, priority=0)
        # 必须放行，绝对不能被防抖吞掉！
        assert mock_send2.called
        assert mock_send2.call_args[0][0] == msg2


def test_announcement_slot_not_consumed_on_empty_data(qapp):
    """验证成交量定时播报在数据为空时不消耗令牌，数据就绪后才消耗并播报"""
    from ats.ui.main_window import ATSMainWindow
    window = ATSMainWindow.__new__(ATSMainWindow)
    window._announced_market_volume_slots = set()
    window.current_df = None

    import datetime
    now_dt = datetime.datetime.strptime("2026-10-27 10:00:00", "%Y-%m-%d %H:%M:%S")

    # 1. 当数据为空 (total_amt <= 0) 时
    empty_summary = {"total_amt": 0.0, "plain_text": ""}
    with patch.object(CapitalDragonEngine, "get_instance") as mock_cde, \
         patch.object(AlertNotifier, "get_instance") as mock_notifier, \
         patch("JohnsonUtil.commonTips.get_work_day_status", return_value=True):
        
        cde_inst = MagicMock()
        cde_inst.get_market_indices_and_volume_summary.return_value = empty_summary
        mock_cde.return_value = cde_inst
        
        notifier_inst = MagicMock()
        mock_notifier.return_value = notifier_inst

        window._check_market_volume_announcement(now_dt=now_dt)

        # 令牌未被消耗
        assert ("2026-10-27", "10:00") not in window._announced_market_volume_slots
        # 未触发播报
        assert not notifier_inst.notify_market_volume.called

    # 2. 当数据有效 (total_amt > 0) 时
    valid_summary = {"total_amt": 15000.0, "plain_text": "全市成交额1.5万亿"}
    with patch.object(CapitalDragonEngine, "get_instance") as mock_cde, \
         patch.object(AlertNotifier, "get_instance") as mock_notifier, \
         patch("JohnsonUtil.commonTips.get_work_day_status", return_value=True):
        
        cde_inst = MagicMock()
        cde_inst.get_market_indices_and_volume_summary.return_value = valid_summary
        mock_cde.return_value = cde_inst
        
        notifier_inst = MagicMock()
        mock_notifier.return_value = notifier_inst

        window._check_market_volume_announcement(now_dt=now_dt)

        # 令牌成功消耗
        assert ("2026-10-27", "10:00") in window._announced_market_volume_slots
        # 成功触发播报
        assert notifier_inst.notify_market_volume.called


def test_alert_notifier_queue_watchdog():
    """验证 AlertNotifier 队列看门狗在 _is_busy 异常超时时自动强制复位以防卡死"""
    notifier = AlertNotifier.get_instance()
    notifier._is_busy = True
    # 模拟 _is_busy 已卡住了 15 秒
    notifier._busy_start_mono = time.monotonic() - 15.0

    item = {
        "type": "market_volume",
        "title": "测试播报",
        "message": "测试内容",
        "voice_text": "测试语音",
        "parent": None
    }
    notifier._notify_queue.append(item)

    # 触发 _process_queue
    with patch.object(notifier, "_speak_text"):
        notifier._process_queue()

    # 看门狗应自动复位 _is_busy 并重新开始处理 item
    assert notifier._is_busy is True
    assert (time.monotonic() - notifier._busy_start_mono) < 2.0


def test_offhours_market_summary_from_tdx_index_bars_ssot():
    """验证休市/盘后当实时盘口返回空时，能够权威地从通达信日线收盘提取大盘数据 (SSOT 对齐通达信)"""
    cde = CapitalDragonEngine.get_instance()
    cde._bg_market_summary_cache = None

    # 模拟通达信日线返回包含昨日收盘 [-2] 与今日收盘 [-1]
    mock_b_sh = [
        {"amount": 746528047104.0, "vol": 432794304.0, "close": 3697.52},
        {"amount": 672414367744.0, "vol": 417789536.0, "close": 3648.30}
    ]
    mock_b_sz = [
        {"amount": 800000000000.0, "vol": 500000000.0, "close": 11300.0},
        {"amount": 788543897600.0, "vol": 490000000.0, "close": 11245.73}
    ]
    mock_b_cy = [
        {"amount": 400000000000.0, "vol": 200000000.0, "close": 2600.0},
        {"amount": 383305646080.0, "vol": 195000000.0, "close": 2548.15}
    ]
    mock_b_bj = [
        {"amount": 15000000000.0,  "vol": 10000000.0,  "close": 950.0},
        {"amount": 12076132352.0,  "vol": 9800000.0,   "close": 931.64}
    ]

    mock_fetcher = MagicMock()
    mock_fetcher._is_connected = True
    mock_fetcher.api = MagicMock()
    mock_fetcher.api.get_index_bars.side_effect = lambda cat, mkt, code, start, cnt: {
        (1, '000001'): mock_b_sh,
        (0, '399001'): mock_b_sz,
        (0, '399006'): mock_b_cy,
        (2, '899050'): mock_b_bj,
    }.get((mkt, code), [])

    with patch("ats.tdx_realtime_fetcher.TDXRealtimeFetcher.get_instance", return_value=mock_fetcher), \
         patch.object(cde, "_fetch_tdx_index_data", return_value={}):  # 模拟盘后实时五档盘口返回空
        
        cde._compute_market_summary_bg()

        # 验证权威通达信日线收盘数据被正确沉淀到缓存
        summary = cde.get_market_indices_and_volume_summary()
        assert summary is not None
        assert summary["total_amt"] > 0
        # 6724.1 + 7885.4 + 120.8 = 14730.3
        assert summary["sh_amt"] == pytest.approx(6724.14, rel=1e-2)
        assert summary["sz_amt"] == pytest.approx(7885.44, rel=1e-2)
        assert summary["bj_amt"] == pytest.approx(120.76, rel=1e-2)
        assert summary["cy_amt"] == pytest.approx(3833.06, rel=1e-2)
        assert "14730" in summary["formatted_html"]



def test_speak_text_syncs_alert_manager_voice_enabled():
    """验证 _speak_text 播报时自动确保底层 AlertManager 的语音开关保持就绪"""
    notifier = AlertNotifier.get_instance()
    notifier.set_voice_enabled(True)

    mgr = AlertManager()
    mgr.voice_enabled = False  # 模拟被外界误关
    mgr.enabled = False

    with patch.object(mgr, "speak") as mock_speak:
        notifier._speak_text("大盘成交量测试")
        # 底层状态已被自愈为 True
        assert mgr.voice_enabled is True
        assert mgr.enabled is True
        assert mock_speak.called

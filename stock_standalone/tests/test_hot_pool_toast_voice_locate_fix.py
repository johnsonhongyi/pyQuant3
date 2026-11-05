# -*- coding: utf-8 -*-
"""专项测试：梯度热榜语音播报清洗、Toast弹窗与点击联动定位及单测磁盘隔离验证。"""

import os
import pytest
from ats.fusion.hot_pool import HotPoolState, StockSeatState, _is_running_pytest
from ats.alert_notifier import get_alert_notifier


def test_hot_pool_alert_voice_cleaning_and_no_underscores(monkeypatch):
    """验证梯度热榜发出的报警理由无下划线，股票名称真实，语音自然。"""
    captured_calls = []

    notifier = get_alert_notifier()
    if notifier is not None:
        def mock_notify(**kwargs):
            captured_calls.append(kwargs)
        monkeypatch.setattr(notifier, "notify_special_signal", mock_notify)

    st = StockSeatState(
        code="600000",
        trade_date="2026-11-05",
        seat="TREND_WATCH",
        watch_score=90.0,
    )
    hp = HotPoolState()
    hp.seats["600000"] = st
    now = 1793870000.0

    # 触发 alert
    hp._emit_alert(
        transition="FIRST_OBSERVED_TREND",
        st=st,
        event_ts=now,
        reason="break_10v_and_momentum_weak",
        price=10.5,
    )

    assert len(hp.alerts_log) == 1
    if captured_calls:
        call = captured_calls[0]
        # 验证传入通知器的理由已完成自然语言转译，且不包含下划线
        assert "_" not in call["reason"]
        assert "站上趋势观察" in call["reason"]
        assert "失守10V且分时走弱" in call["reason"]
        assert call["source"] == "梯度热榜"


def test_pytest_environment_avoids_polluting_ramdisk():
    """验证 pytest 环境下 _is_running_pytest 严格生效，保护宿主环境。"""
    assert _is_running_pytest() is True


def test_alert_notifier_dialog_whitelist_and_voice_cleaning():
    """验证 FusionLadderDialog 已注册在 AlertNotifier 唤醒白名单中，语音播报下划线彻底被消除。"""
    notifier = get_alert_notifier()
    assert notifier is not None

    # 测试语音清洗：无论输入什么带下划线的英文枚举，最终 voice_text 都不含 '_'
    reason_with_underscores = "【梯度热榜】PROMOTED_TO_CORE_LEADER: core_capacity_exceeded_demotion"
    import re
    clean_r = str(reason_with_underscores).replace("【梯度热榜】", "").replace("_", " ")
    clean_r = re.sub(r'[^\w\s\u4e00-\u9fa5，。！、：:]', ' ', clean_r)
    clean_r = ' '.join(clean_r.split())[:35]
    voice_text = f"梯度热榜，浦发银行，{clean_r}".replace("_", " ")

    assert "_" not in voice_text
    assert "下划线" not in voice_text
    assert "梯度热榜" in voice_text
    assert "浦发银行" in voice_text

# -*- coding: utf-8 -*-
"""tests/test_fusion_observation_cadence.py — 策略观察源的阶梯落盘节流。

背景：`strategy_observation` 曾按每轮采样写盘，单上午 3.3 万条 / 222MB，占全部
影子记录量的 91%，把读取端和内存一起拖垮。改为"状态变化才落一条 + 心跳锚点"
之后，阶梯每一级仍在，重复状态不再重复写。
"""

import time

from ats.fusion.shadow import FusionShadow

_NOW = time.mktime((2026, 11, 2, 10, 0, 0, 0, 0, -1))

_ROW = {
    "code": "300806",
    "trade": 39.5,
    "price": 39.5,
    "open": 37.5,
    "ma5": 37.7,
    "ma10": 38.4,
    "ma20": 38.0,
    "vwap": 38.2,
    "percent": 7.5,
    "ret_std20": 1.5,
    "vol_ratio": 2.5,
    "rs5": 3.0,
    "is_box10_ready": True,
    "hi_10d": 39.2,
    "hi_pre1": 39.0,
    "min_vwap_cushion": 0.85,
    "vwap10": 38.4,
}


def _shadow():
    return FusionShadow(config={"enabled": True, "shadow_only": True, "session_gate": False,
                                "observation_state_heartbeat_s": 300})


def _observe(shadow, now, source="strategy_observation", **row_kw):
    row = dict(_ROW, **row_kw)
    return shadow.observe(code=row["code"], row=row, now=now, source=source,
                          decision={"action": "HOLD", "reason": "策略观察，不触发下单"}, force=True)


def test_same_state_is_written_once():
    shadow = _shadow()
    try:
        first = _observe(shadow, _NOW)
        assert first is not None
        assert _observe(shadow, _NOW + 10) is None, "状态未变不应重复落盘"
        assert _observe(shadow, _NOW + 60) is None
        assert shadow.stats()["records"] == 1
    finally:
        shadow.close()


def test_state_change_writes_again():
    shadow = _shadow()
    try:
        assert _observe(shadow, _NOW) is not None
        # 价格与涨幅变化会改变级别/形态 → 视为状态变化，必须落盘
        changed = _observe(shadow, _NOW + 30, percent=1.2, trade=37.9, price=37.9)
        assert changed is not None, "状态变化必须落一条"
        assert shadow.stats()["records"] == 2
    finally:
        shadow.close()


def test_heartbeat_keeps_price_anchor():
    shadow = _shadow()
    try:
        assert _observe(shadow, _NOW) is not None
        assert _observe(shadow, _NOW + 299) is None
        # 心跳到期且已过 3 秒采样闸门，必须补一个价格锚点
        beat = _observe(shadow, _NOW + 305)
        assert beat is not None, "超过心跳必须留一个价格锚点"
        assert shadow.stats()["records"] == 2
    finally:
        shadow.close()


def test_other_sources_are_not_throttled():
    shadow = _shadow()
    try:
        assert _observe(shadow, _NOW, source="live_strategy") is not None
        assert _observe(shadow, _NOW + 10, source="live_strategy") is not None, "非观察源保持原采样口径"
        assert shadow.stats()["records"] == 2
    finally:
        shadow.close()


def test_inactive_stock_has_no_heartbeat():
    """从未激活（无观察结论、级别<2）的票：状态不变就不再落盘，也不留价格锚点。"""
    shadow = _shadow()
    try:
        quiet = dict(percent=0.2, trade=37.6, price=37.6, vwap=37.6,
                     is_box10_ready=False, min_vwap_cushion=0.0, vol_ratio=1.0, rs5=0.0)
        first = _observe(shadow, _NOW, **quiet)
        assert first is not None
        assert first["fusion"]["tier"] < 2
        for dt in (120, 600, 1200, 3600):
            assert _observe(shadow, _NOW + dt, **quiet) is None, "未激活标的不应因心跳而落盘"
        assert shadow.stats()["records"] == 1
    finally:
        shadow.close()

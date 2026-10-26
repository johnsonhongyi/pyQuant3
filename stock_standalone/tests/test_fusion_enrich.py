# -*- coding: utf-8 -*-
"""ats/fusion/enrich.py 的纯函数测试：口径可复算、缺数据不造假。"""

import pytest

from ats.fusion.enrich import depth_fields, intraday_fields, merge_missing


def _bars(closes, vols=None):
    vols = vols or [1000.0] * len(closes)
    return [{"close": c, "vol": v} for c, v in zip(closes, vols)]


def test_rising_series_scores_high():
    closes = [10.0 + i * 0.01 for i in range(30)]
    out = intraday_fields(_bars(closes), vwap=10.05, price=closes[-1])
    assert out["slope_score"] > 70
    assert out["velocity_pct"] > 0
    assert out["minutes_above_vwap"] > 0
    assert out["intent_score"] > 50
    assert 0 <= out["structure_clarity"] <= 100


def test_falling_series_scores_low_slope():
    closes = [10.0 - i * 0.01 for i in range(30)]
    out = intraday_fields(_bars(closes), vwap=10.2, price=closes[-1])
    assert out["slope_score"] < 50
    assert out["velocity_pct"] < 0
    assert out["minutes_above_vwap"] == 0


def test_insufficient_bars_returns_empty():
    assert intraday_fields(_bars([10.0, 10.1, 10.2])) == {}
    assert intraday_fields(None) == {}


def test_flat_series_has_no_range_clarity():
    closes = [10.0] * 20
    out = intraday_fields(_bars(closes))
    assert out["structure_clarity"] == 0.0
    assert abs(out["velocity_pct"]) < 1e-9


def test_volume_surge_reports_segment_increment():
    vols = [100.0] * 25 + [900.0] * 5
    closes = [10.0 + i * 0.005 for i in range(30)]
    out = intraday_fields(_bars(closes, vols))
    assert out["segment_vol_inc"] > 2.0


def test_depth_fields_filters_invalid():
    assert depth_fields({"taker_buy_ratio": 63.5, "bid_pressure": 0}) == {"taker_buy_ratio": 63.5}
    assert depth_fields({"taker_buy_ratio": None}) == {}
    assert depth_fields(None) == {}


def test_merge_missing_never_overwrites_real_values():
    base = {"slope_score": 0, "intent_score": 88.0, "other": 1}
    extra = {"slope_score": 61.0, "intent_score": 20.0}
    out = merge_missing(base, extra)
    assert out["slope_score"] == 61.0
    assert out["intent_score"] == 88.0
    assert out["other"] == 1


def test_merge_missing_respects_key_whitelist():
    out = merge_missing({}, {"a": 1, "b": 2}, keys=("a",))
    assert out == {"a": 1}

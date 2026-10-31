# -*- coding: utf-8 -*-
"""ats/fusion/enrich.py 的纯函数测试：口径可复算、缺数据不造假。"""

import pytest

from ats.fusion.enrich import day_ret, depth_fields, intraday_fields, merge_missing, relative_fields


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


def test_above_vwap_uses_each_bars_cumulative_vwap():
    out = intraday_fields(_bars([10, 11, 12, 13, 14, 15, 16, 17]), vwap=17, price=17)
    assert out["minutes_above_vwap"] == 7


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


def test_relative_fields_subtracts_market():
    closes = [10.0, 10.1, 10.2, 10.3, 10.4, 11.0]
    out = relative_fields(closes, mkt_ret5=2.0, lookback=5)
    assert out["has_rs"] is True
    assert abs(out["rs5"] - 8.0) < 0.01      # 个股 10% - 大盘 2%
    assert out["mkt_ret5"] == 2.0


def test_relative_fields_insufficient_data():
    assert relative_fields([10.0, 10.1], 0.0) == {}
    assert relative_fields(None, 0.0) == {}
    assert relative_fields([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.0) == {}


def test_day_ret_matches_relative_base():
    closes = [10.0, 10.0, 10.0, 10.0, 10.0, 12.0]
    assert abs(day_ret(closes, 5) - 20.0) < 1e-6
    assert day_ret([10.0], 5) is None


def test_depth_fields_from_5level_memory_row():
    """直接从 df_all_data 内存行的五档挂单量 (b1_v..b5_v / a1_v..a5_v) 与内外盘推算，零网络请求。"""
    row = {
        "b1_v": 500, "b2_v": 400, "b3_v": 300, "b4_v": 200, "b5_v": 100,  # 1500
        "a1_v": 100, "a2_v": 100, "a3_v": 100, "a4_v": 100, "a5_v": 100,  # 500
        "b_vol": 3200,
        "s_vol": 800,
    }
    out = depth_fields(None, row=row)
    assert abs(out["bid_pressure"] - 75.0) < 0.01
    assert abs(out["taker_buy_ratio"] - 80.0) < 0.01


def test_intraday_fields_detects_latent_break_and_rolling_taker():
    """横盘缩量 ≥12 根后放量拉升应识别出 latent_break=True，并产出滚动 10 根外盘占比。"""
    # 前 16 根窄幅横盘 (振幅 < 2.5%), 后 5 根放量突破
    closes = [10.00 + (i % 2) * 0.01 for i in range(16)] + [10.05, 10.10, 10.16, 10.22, 10.30]
    vols = [100.0] * 16 + [350.0] * 5
    out = intraday_fields(_bars(closes, vols), vwap=10.04, price=10.30)
    assert out.get("latent_break") is True
    assert out.get("taker_buy_ratio", 0.0) >= 60.0


def test_shadow_dragon_anomaly_alignment(tmp_path):
    """实盘 FusionShadow 应识别一阳穿三线/突破10日VWAP/排头兵/潜伏转突破并给出 L2+ 赛马跟踪。"""
    import time
    from ats.fusion.regime import FLIP_CONFIRMED, STAGE_WARMING, MarketRegime
    from ats.fusion.shadow import FusionShadow

    now = time.mktime((2026, 10, 27, 10, 15, 0, 0, 0, -1))
    shadow = FusionShadow(
        config={
            "enabled": True,
            "shadow_only": True,
            "log_dir": "shadow_dragon_test",
            "sample_interval_s": 0.0,
        },
        regime_provider=lambda _t: MarketRegime(
            temp=54.0, stage=STAGE_WARMING, slope_5m=3.5, flip_state=FLIP_CONFIRMED
        ),
        root=str(tmp_path),
    )
    try:
        row = {
            "open": 19.80,
            "trade": 20.90,
            "vwap": 20.45,
            "percent": 4.5,
            "high": 21.05,
            "low": 19.75,
            "amount": 680000000.0,
            "volume": 33000.0,
            "ratio": 2.6,
            "turnover": 7.5,
            "ma5d": 20.0,
            "ma10d": 20.1,
            "ma20d": 20.2,
            "ma10dcum": 20.15,
            "category": "半导体;芯片",
            "b1_v": 800, "b2_v": 600, "b3_v": 400, "a1_v": 200, "a2_v": 200,
            "b_vol": 5000, "s_vol": 1500,
        }
        snap = {
            "name": "测试先锋龙",
            "is_leader": True,
            "sector_resonance": 82.0,
            "slope_score": 84.0,
            "intent_score": 86.0,
            "structure_clarity": 80.0,
            "minutes_above_vwap": 15.0,
            "has_rs": True,
            "rs5": 6.5,
            "mkt_ret5": -0.5,
            "latent_break": True,
        }
        # 同板块已有另外 2 只启动，使板块启动家数 >= 3，第一只突破 10 日 VWAP 的龙头应获评 排头兵/夺旗
        shadow.sector_clock.observe("688001", "半导体", now - 60, 2.1, breakout=False)
        shadow.sector_clock.observe("688002", "半导体", now - 30, 1.8, breakout=False)
        rec = shadow.observe(code="688787", row=row, snap=snap, now=now, force=True)
        assert rec is not None
        assert rec["fusion"]["tier"] >= 3
        assert "一阳穿三线" in rec["patterns"]
        assert "突破10日VWAP" in rec["patterns"]
        assert "潜伏转突破" in rec["patterns"]
        assert rec["lead_label"] in ("排头兵", "夺旗")
        assert rec["track"].get("code") == "688787"
    finally:
        shadow.close()

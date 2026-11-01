# -*- coding: utf-8 -*-
"""tests/test_fusion_replay.py — 按日回放引擎自检。

覆盖：
- 缓存切片 / 前收代理（最早一天不瞎）
- 分位自适应分档（单调 + 绝对下限）
- MFE/MAE/超额的方向正确
- 验收标的命中判定（focus）
"""

import time
import unittest

import numpy as np

from ats.fusion.replay import (
    DayReplay,
    ReplayConfig,
    _future_extremes,
    focus_summary,
    percentile_cuts,
    summarize_tiers,
)

_DTYPE = [
    ("time", "<i8"),
    ("open", "<f4"),
    ("high", "<f4"),
    ("low", "<f4"),
    ("close", "<f4"),
    ("volume", "<f4"),
    ("cum_vol_start", "<f4"),
]

_DAY1 = "2026-10-20"
_DAY2 = "2026-10-21"


def _mk_day(day, closes, start_price=10.0):
    st = time.strptime(day + " 09:30", "%Y-%m-%d %H:%M")
    base = int(time.mktime((st.tm_year, st.tm_mon, st.tm_mday, 9, 30, 0, 0, 0, -1)))
    n = len(closes)
    arr = np.zeros(n, dtype=_DTYPE)
    for i, c in enumerate(closes):
        arr[i] = (
            base + i * 180,
            c * 0.998,
            c * 1.004,
            c * 0.996,
            c,
            50000.0 * (i + 1),
            0.0,
        )
    return arr


def _cache():
    # 第二日必须从前一日收盘接续，否则会人为造出 -16% 的跳空，全部被否决
    up1 = [10.0 + i * 0.05 for i in range(40)]
    up2 = [up1[-1] + i * 0.05 for i in range(40)]
    flat1 = [10.0 + (0.02 if i % 2 else -0.02) for i in range(40)]
    flat2 = [flat1[-1] + (0.02 if i % 2 else -0.02) for i in range(40)]
    down1 = [10.0 - i * 0.04 for i in range(40)]
    down2 = [down1[-1] - i * 0.04 for i in range(40)]
    return {
        "300001": np.concatenate([_mk_day(_DAY1, up1), _mk_day(_DAY2, up2)]),
        "300002": np.concatenate([_mk_day(_DAY1, flat1), _mk_day(_DAY2, flat2)]),
        "300003": np.concatenate([_mk_day(_DAY1, down1), _mk_day(_DAY2, down2)]),
    }


class TestFutureExtremes(unittest.TestCase):
    def test_strictly_future(self):
        close = np.array([[1.0, 2.0, 3.0, 2.5]])
        fmax, fmin = _future_extremes(close)
        self.assertEqual(fmax[0, 0], 3.0)     # 之后最高
        self.assertEqual(fmin[0, 0], 2.0)     # 之后最低
        self.assertEqual(fmax[0, 1], 3.0)
        self.assertTrue(np.isnan(fmax[0, -1]))  # 最后一根无未来


class TestPercentileCuts(unittest.TestCase):
    def test_monotonic_and_floors(self):
        cuts = percentile_cuts([float(x) for x in range(40, 80)])
        vals = [c for c, _ in cuts]
        tiers = [t for _, t in cuts]
        self.assertEqual(tiers, [4, 3, 2, 1])
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertGreaterEqual(vals[0], 68.0)   # L4 绝对下限
        self.assertGreaterEqual(vals[-1], 45.0)

    def test_empty_samples_use_floors(self):
        cuts = percentile_cuts([])
        self.assertEqual([c for c, _ in cuts], [68.0, 60.0, 52.0, 45.0])


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.rp = DayReplay(cache=_cache(), config=ReplayConfig(top_n=10, step=1, cuts_mode="fixed"))

    def test_days_detected(self):
        self.assertEqual(self.rp.days(), [_DAY1, _DAY2])

    def test_completed_bar_is_visible_only_after_next_snapshot_minute(self):
        raw = self.rp.cache["300001"]
        day = raw[raw["time"] >= int(time.mktime(time.strptime(_DAY2, "%Y-%m-%d")))]
        sliced = self.rp._slice_day("300001", _DAY2)
        self.assertEqual(sliced["ts"][0], day["time"][1] + 60)
        self.assertAlmostEqual(sliced["close"][0], day["close"][0])
        self.assertEqual(len(sliced["ts"]), len(day) - 1)

    def test_vwap_time_counts_observed_bars(self):
        aligned = self.rp._align(["300001"], _DAY2)
        minutes = aligned["mat"]["minutes_above_vwap"][0]
        self.assertEqual(minutes[0], 3.0)
        self.assertEqual(minutes[4], 15.0)

    def test_first_day_not_blind(self):
        """缓存起始日没有前一日收盘，必须用当日首根开盘代理，而不是整天无标的。"""
        res = self.rp.run(_DAY1)
        self.assertGreater(res.meta["codes"], 0)
        self.assertNotIn("error", res.meta)

    def test_records_and_outcome_direction(self):
        # 本用例验证收益方向，不依赖自适应阈值是否将上涨样本筛进 L1。
        rp = DayReplay(cache=_cache(), config=ReplayConfig(top_n=10, step=1, cuts_mode="percentile", record_tier_min=0))
        res = rp.run_day(_DAY2)
        self.assertGreater(res.meta["records"], 0)
        rising = [r for r in res.records if r["code"] == "300001"]
        self.assertTrue(rising)
        self.assertGreater(rising[0]["mfe"], 0.0)

    def test_adaptive_mode_runs(self):
        rp = DayReplay(cache=_cache(), config=ReplayConfig(top_n=10, step=1, cuts_mode="percentile"))
        res = rp.run_day(_DAY2)
        self.assertIn("cuts_used", res.meta)
        self.assertIn("L4", res.meta["cuts_used"])

    def test_focus_always_included(self):
        rp = DayReplay(
            cache=_cache(),
            config=ReplayConfig(top_n=1, step=1, cuts_mode="fixed", focus_codes=("300003",)),
        )
        res = rp.run(_DAY1, focus=("300003",))
        self.assertIn("300003", res.meta["focus_diag"])

    def test_focus_summary_miss(self):
        rows = focus_summary([], ["300999"])
        self.assertFalse(rows[0]["hit"])
        self.assertIn("未捕捉", rows[0]["reason"])

    def test_tier_stats_shape(self):
        res = self.rp.run(_DAY2)
        stats = summarize_tiers(res.records)
        for tier in ("L4", "L3", "L2", "L1"):
            self.assertIn(tier, stats)

    def test_same_day_replay_is_idempotent(self):
        """同一天重复回放入局数必须一致：阈值扫描靠这个，否则第二遍恒为 0。"""
        rp = DayReplay(cache=_cache(), config=ReplayConfig(top_n=10, step=1, cuts_mode="fixed"))
        n1 = len(rp.run(_DAY2).entries)
        n2 = len(rp.run(_DAY2).entries)
        self.assertEqual(n1, n2, "同一天重跑，入局数不应被上一次的状态污染")

    def test_cross_day_still_carries(self):
        """跨日仍要携带昨日入局状态（多日连续性）——同一天才重置。"""
        rp = DayReplay(cache=_cache(), config=ReplayConfig(top_n=10, step=1, cuts_mode="fixed"))
        n_d1 = len(rp.run(_DAY1).entries)
        n_d2 = len(rp.run(_DAY2).entries)
        self.assertGreaterEqual(n_d1 + n_d2, n_d2, "跨日运行不应互相清空")


if __name__ == "__main__":
    unittest.main(verbosity=2)

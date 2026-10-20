# -*- coding: utf-8 -*-
"""tests/test_premarket_profile.py — 盘前身份层单元测试。

验证：数百列策略基数 -> 身份向量（结构/触发线/防守线/波动预算/先验分/门禁）
以及"按个股波动预算自适应阈值"（文档 §7.2）。
"""

import unittest

from ats.premarket_profile import (
    GATE_PASS,
    GATE_REJECT,
    GATE_WATCH,
    PreMarketProfile,
    StructureClass,
    build_profiles,
)
from ats.signal_state_machine import SignalParams


def _row(**over):
    """构造一行典型 DFall 策略基数（数值取自常见量级）。"""
    base = {
        "code": "600000",
        "name": "浦发银行",
        "trade": 10.50,
        "nhigh": 10.60,
        "nlow": 10.20,
        "resist_today": 10.58,
        "support_today": 10.28,
        "ptop": 11.60,
        "dff2": 6.5,
        "dff3": 5.0,
        "ch_slope_deg": 8.0,
        "ch_supp_slope": 0.35,
        "ch_supp_pos": 0.72,
        "TrendS": 3.0,
        "structure_base_score": 78.0,
        "win": 3.0,
        "power_idx": 2.5,
        "obs_d": 0.0,
        "bullbreak": 0.0,
        "lasth1d": 10.70, "lastl1d": 10.20, "lastp1d": 10.45,
        "lasth2d": 10.55, "lastl2d": 10.10, "lastp2d": 10.30,
        "lasth3d": 10.40, "lastl3d": 10.00, "lastp3d": 10.15,
    }
    base.update(over)
    return base


class StructureClassifyTest(unittest.TestCase):
    def test_channel_up(self):
        p = PreMarketProfile.from_row(_row())
        self.assertEqual(p.structure_class, StructureClass.CHANNEL_UP.value)
        self.assertGreater(p.prior_score, 0.0)

    def test_breakout_base(self):
        p = PreMarketProfile.from_row(_row(bullbreak=1.0))
        self.assertEqual(p.structure_class, StructureClass.BREAKOUT_BASE.value)

    def test_weak_down(self):
        p = PreMarketProfile.from_row(_row(TrendS=-3.0, ch_slope_deg=-8.0, dff2=-5.0))
        self.assertEqual(p.structure_class, StructureClass.WEAK_DOWN.value)

    def test_reversal(self):
        p = PreMarketProfile.from_row(_row(
            TrendS=0.0, ch_slope_deg=0.0, ch_supp_slope=-0.1,
            ch_supp_pos=0.2, dff2=-2.0, dff3=-2.0, bullbreak=0.0,
        ))
        self.assertEqual(p.structure_class, StructureClass.REVERSAL.value)


class LineTest(unittest.TestCase):
    def test_trigger_and_defend_from_df_all(self):
        p = PreMarketProfile.from_row(_row())
        self.assertAlmostEqual(p.trigger_line, 10.58, places=3)
        self.assertAlmostEqual(p.defend_line, 10.28, places=3)

    def test_fallback_to_nhigh_nlow(self):
        p = PreMarketProfile.from_row(_row(resist_today=0, support_today=0))
        self.assertAlmostEqual(p.trigger_line, 10.60, places=3)
        self.assertAlmostEqual(p.defend_line, 10.20, places=3)


class VolBudgetTest(unittest.TestCase):
    def test_multi_day_amplitude_median(self):
        p = PreMarketProfile.from_row(_row())
        # 三日振幅: 4.78% / 4.37% / 3.94% -> 中位 4.37%
        self.assertAlmostEqual(p.vol_budget_pct, 4.37, places=1)

    def test_fallback_single_day(self):
        row = _row()
        for i in range(1, 6):
            for k in ("lasth%dd" % i, "lastl%dd" % i, "lastp%dd" % i):
                row.pop(k, None)
        p = PreMarketProfile.from_row(row)
        self.assertGreater(p.vol_budget_pct, 0.0)


class GateTest(unittest.TestCase):
    def test_pass(self):
        p = PreMarketProfile.from_row(_row())
        self.assertEqual(p.gate, GATE_PASS)

    def test_reject_weak_down(self):
        p = PreMarketProfile.from_row(_row(TrendS=-3.0, ch_slope_deg=-8.0, dff2=-6.0))
        self.assertEqual(p.gate, GATE_REJECT)
        self.assertIn("弱势下行", p.gate_reason)

    def test_reject_high_vol_budget(self):
        # 三天都是宽幅（中位数才会高，单日异常值被中位数稀释，这是刻意保留的鲁棒性）
        row = _row(
            lasth1d=12.0, lastl1d=9.0, lastp1d=10.5,
            lasth2d=11.8, lastl2d=9.2, lastp2d=10.5,
            lasth3d=12.2, lastl3d=9.1, lastp3d=10.5,
        )
        p = PreMarketProfile.from_row(row)
        self.assertEqual(p.gate, GATE_REJECT)
        self.assertIn("波动预算", p.gate_reason)

    def test_single_outlier_day_diluted_by_median(self):
        """单日暴涨暴跌不应把整只股票判死：中位数抗异常值。"""
        row = _row(lasth1d=12.0, lastl1d=9.0, lastp1d=10.5)
        p = PreMarketProfile.from_row(row)
        self.assertNotEqual(p.gate, GATE_REJECT)

    def test_reject_no_price(self):
        p = PreMarketProfile.from_row(_row(trade=0))
        self.assertEqual(p.gate, GATE_REJECT)

    def test_watch_low_prior(self):
        p = PreMarketProfile.from_row(_row(
            dff2=-6.0, dff3=-6.0, win=0.0, power_idx=0.0,
            structure_base_score=10.0, ptop=10.62,
        ))
        self.assertIn(p.gate, (GATE_WATCH, GATE_REJECT))


class AdaptiveParamsTest(unittest.TestCase):
    def test_low_vol_relaxes_pct_and_tightens_vol(self):
        low = SignalParams().derive_for(1.5, 10.0)
        high = SignalParams().derive_for(8.0, 10.0)
        self.assertLess(low.trigger_pct_thresh, high.trigger_pct_thresh)
        self.assertGreaterEqual(low.trigger_vol_thresh, high.trigger_vol_thresh)

    def test_accel_scales_with_board(self):
        main = SignalParams().derive_for(3.0, 10.0)
        gem = SignalParams().derive_for(3.0, 20.0)
        self.assertAlmostEqual(main.accel_pct_thresh, 5.5, places=2)
        self.assertAlmostEqual(gem.accel_pct_thresh, 11.0, places=2)

    def test_profile_carries_adaptive_params(self):
        p = PreMarketProfile.from_row(_row())
        self.assertAlmostEqual(p.board_limit_pct, 10.0, places=2)
        self.assertGreater(p.trigger_params.trigger_pct_thresh, 0.0)

    def test_20cm_board_detected(self):
        p = PreMarketProfile.from_row(_row(code="300001"))
        self.assertAlmostEqual(p.board_limit_pct, 20.0, places=2)


class BatchTest(unittest.TestCase):
    def test_build_profiles(self):
        rows = [_row(code="600000"), _row(code="000001", name="平安银行")]
        out = build_profiles(rows)
        self.assertEqual(len(out), 2)
        self.assertIn("600000", out)
        self.assertIn("000001", out)

    def test_to_dict(self):
        d = PreMarketProfile.from_row(_row()).to_dict()
        for k in ("structure_class", "trigger_line", "defend_line", "gate",
                  "prior_score", "trigger_params"):
            self.assertIn(k, d)


class CctWiringTest(unittest.TestCase):
    def test_cct_exposes_signal_params(self):
        from JohnsonUtil import commonTips as cct
        self.assertEqual(int(cct.ats_signal_bar_seconds), 15)
        self.assertEqual(int(cct.ats_df_sync_interval), 300)
        self.assertTrue(hasattr(cct, "ats_signal_confirm_bars"))
        self.assertTrue(hasattr(cct, "ats_signal_trail_start_pct"))
        self.assertTrue(hasattr(cct, "ats_signal_shadow_mode"))

    def test_params_from_cct(self):
        p = SignalParams.from_cct()
        self.assertGreaterEqual(p.confirm_bars, 1)
        self.assertGreater(p.max_hold_bars, 0)
        self.assertGreater(p.bar_seconds, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

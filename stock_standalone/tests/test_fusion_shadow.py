# -*- coding: utf-8 -*-
"""tests/test_fusion_shadow.py — 影子观察器：落盘、节流、分歧归类、异常隔离。"""

import json
import os
import shutil
import tempfile
import time
import unittest

import pandas as pd

from ats.fusion.regime import FLIP_CONFIRMED, STAGE_WARMING, MarketRegime
from ats.fusion.shadow import FusionShadow

_NOW = time.mktime((2026, 10, 23, 10, 30, 0, 0, 0, -1))

_BASE_CFG = {
    "enabled": True,
    "shadow_only": True,
    "log_dir": "fusion_shadow_test",
    "sample_interval_s": 0.0,
    "max_records_per_day": 1000,
    "state_temp_map": {"NEUTRAL": 50.0},
}

_GOOD_ROW = pd.Series(
    {
        "trade": 12.9,
        "vwap": 12.8,
        "percent": 4.2,
        "high": 13.2,
        "low": 12.3,
        "amount": 900000000.0,
        "volume": 70000.0,
        "ratio": 2.3,
        "turnover": 9.0,
        "vwap_cum_5d": 12.5,
    }
)

_GOOD_SNAP = {
    "name": "测试龙头",
    "taker_buy_ratio": 73.0,
    "bid_pressure": 69.0,
    "slope_score": 86.0,
    "intent_score": 90.0,
    "structure_clarity_score": 82.0,
    "sbc_supp_price": 12.55,
    "is_leader": True,
    "minutes_above_vwap": 28.0,
}


def _regime_provider(_now):
    return MarketRegime(temp=55.0, stage=STAGE_WARMING, slope_5m=4.0, flip_state=FLIP_CONFIRMED)


class TestShadow(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fusion_shadow_")
        self.shadow = FusionShadow(
            config=dict(_BASE_CFG), regime_provider=_regime_provider, root=self.root
        )

    def tearDown(self):
        try:
            self.shadow.close()
        finally:
            shutil.rmtree(self.root, ignore_errors=True)

    def _log_path(self):
        day = time.strftime("%Y-%m-%d", time.localtime(_NOW))
        return os.path.join(self.root, "fusion_shadow_test", "{}_{}.jsonl".format(day, os.getpid()))

    def test_record_written(self):
        rec = self.shadow.observe(
            code="300111",
            row=_GOOD_ROW,
            snap=_GOOD_SNAP,
            decision={"action": "买入", "reason": "放量突破"},
            now=_NOW,
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec["code"], "300111")
        self.assertIn(rec["fusion"]["tier"], (3, 4))
        self.assertEqual(rec["divergence"], "both_buy")

        self.shadow.flush()
        with open(self._log_path(), "r", encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["fusion"]["tier"], rec["fusion"]["tier"])
        self.assertIn("regime", lines[0])

    def test_fusion_only_divergence(self):
        rec = self.shadow.observe(
            code="300222",
            row=_GOOD_ROW,
            snap=_GOOD_SNAP,
            decision={"action": "HOLD", "reason": "无信号"},
            now=_NOW,
        )
        self.assertEqual(rec["divergence"], "fusion_only")

    def test_legacy_only_divergence(self):
        row = pd.Series({"trade": 13.9, "vwap": 12.8, "percent": 9.0, "high": 13.95, "low": 12.3,
                         "amount": 900000000.0, "volume": 70000.0, "ratio": 5.0, "turnover": 20.0})
        rec = self.shadow.observe(
            code="300333",
            row=row,
            snap=_GOOD_SNAP,
            decision={"action": "买入", "reason": "涨幅榜"},
            now=_NOW,
        )
        self.assertEqual(rec["divergence"], "legacy_only")
        self.assertTrue(rec["fusion"]["veto_reason"] or rec["fusion"]["tier"] < 2)

    def test_interval_throttle(self):
        cfg = dict(_BASE_CFG)
        cfg["sample_interval_s"] = 100.0
        shadow = FusionShadow(config=cfg, regime_provider=_regime_provider, root=self.root)
        first = shadow.observe(code="300444", row=_GOOD_ROW, snap=_GOOD_SNAP, now=_NOW)
        second = shadow.observe(code="300444", row=_GOOD_ROW, snap=_GOOD_SNAP, now=_NOW + 1)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(shadow.stats()["skipped_interval"], 1)
        shadow.close()

    def test_exception_is_isolated(self):
        class Boom:
            def get(self, _k):
                raise RuntimeError("boom")

        rec = self.shadow.observe(code="300555", row=_GOOD_ROW, snap=Boom(), now=_NOW)
        self.assertIsNone(rec)
        self.assertEqual(self.shadow.stats()["errors"], 1)

    def test_disabled_is_noop(self):
        cfg = dict(_BASE_CFG)
        cfg["enabled"] = False
        other_root = tempfile.mkdtemp(prefix="fusion_shadow_off_")
        try:
            shadow = FusionShadow(config=cfg, root=other_root)
            self.assertIsNone(shadow.observe(code="300666", row=_GOOD_ROW, snap=_GOOD_SNAP, now=_NOW))
            self.assertFalse(os.path.exists(os.path.join(other_root, "fusion_shadow_test")))
            shadow.close()
        finally:
            shutil.rmtree(other_root, ignore_errors=True)

    def test_stats_counts(self):
        self.shadow.observe(code="300111", row=_GOOD_ROW, snap=_GOOD_SNAP,
                            decision={"action": "买入"}, now=_NOW)
        stats = self.shadow.stats()
        self.assertEqual(stats["records"], 1)
        self.assertEqual(stats["errors"], 0)
        self.assertEqual(sum(stats["tier_counts"].values()), 1)

    def test_missing_fields_are_counted(self):
        row = pd.Series({"trade": 12.9})
        self.shadow.observe(code="300777", row=row, snap={}, now=_NOW)
        stats = self.shadow.stats()
        self.assertIn("vwap", stats["missing"])
        self.assertGreaterEqual(stats["missing"]["vwap"], 1)

    def test_off_session_same_day_is_skipped(self):
        """盘后轮询（同一天 21:11）不应写入当日流水，force 可补录。"""
        lt = time.localtime()
        after_hours = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 21, 11, 0, 0, 0, -1))
        self.assertIsNone(
            self.shadow.observe(code="300888", row=_GOOD_ROW, snap=_GOOD_SNAP, now=after_hours)
        )
        self.assertGreaterEqual(self.shadow.stats().get("skipped_off_session", 0), 1)
        rec = self.shadow.observe(
            code="300888", row=_GOOD_ROW, snap=_GOOD_SNAP, now=after_hours, force=True
        )
        self.assertIsNotNone(rec)

    def test_session_gate_can_be_disabled(self):
        cfg = dict(_BASE_CFG)
        cfg["session_gate"] = False
        root = tempfile.mkdtemp(prefix="fusion_gate_off_")
        try:
            sh = FusionShadow(config=cfg, root=root)
            lt = time.localtime()
            after_hours = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 21, 11, 0, 0, 0, -1))
            self.assertIsNotNone(
                sh.observe(code="300889", row=_GOOD_ROW, snap=_GOOD_SNAP, now=after_hours)
            )
            sh.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

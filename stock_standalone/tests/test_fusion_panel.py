# -*- coding: utf-8 -*-
"""信号面板与"带头价值"衰减 —— 自检。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.fusion.engine import leadership_value
from ats.fusion.panel import build_panel, lead_value_table, render_panel


def _rec(tier=2, structure="CHANNEL", patterns=None, traps=None, time="09:45",
         temp=40.0, consensus=0.3, lead=0.7):
    return {
        "tier": tier, "structure": structure, "patterns": patterns or [],
        "traps": traps or [], "time": time, "temp": temp,
        "consensus": consensus, "lead_value": lead,
        "session": "AM" if time[:2] < "13" else "PM",
    }


class TestLeadershipValue(unittest.TestCase):
    def test_low_temp_low_consensus_is_best(self):
        """温度低、没人跟——带头最值钱。"""
        self.assertGreater(leadership_value(25.0, 0.10), 0.90)

    def test_high_temp_high_consensus_is_cheap(self):
        """温度高、人人趋同——带头基本没有价值（诱多）。"""
        self.assertLess(leadership_value(60.0, 0.85), 0.45)

    def test_monotonic_in_temp(self):
        vals = [leadership_value(t, 0.3) for t in (20, 30, 40, 50, 60, 70)]
        self.assertEqual(vals, sorted(vals, reverse=True), "温度越高，带头价值应单调下降")

    def test_monotonic_in_consensus(self):
        vals = [leadership_value(35.0, c) for c in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)]
        self.assertEqual(vals, sorted(vals, reverse=True), "趋同越高，带头价值应单调下降")

    def test_never_zero(self):
        self.assertGreater(leadership_value(99.0, 1.0), 0.3, "带头不应变成负分或归零")


class TestPanel(unittest.TestCase):
    def _records(self):
        out = []
        for i in range(60):
            out.append(_rec(tier=1 if i % 3 else 2,
                            structure="CHANNEL" if i % 2 else "MAIN_WAVE",
                            patterns=["逆势带头"] if i % 4 == 0 else [],
                            traps=["冲高回落"] if i % 10 == 0 else [],
                            time="09:{:02d}".format(i % 60) if i < 30 else "14:{:02d}".format(i % 60),
                            temp=30.0 + (i % 40)))
        return out

    def test_counts_and_funnel(self):
        recs = self._records()
        p = build_panel(records=recs, entries=[{"t1": 3.0}] * 5, meta={"evaluations": 1000, "codes": 400},
                        deploy_count=2)
        self.assertEqual(p["signals"], 60)
        self.assertEqual(p["deploy"], 2)
        funnel = dict(p["funnel"])
        self.assertEqual(funnel["评估次数"], 1000)
        self.assertEqual(funnel["L1+ 信号"], 60)
        self.assertLessEqual(funnel["L2+ 信号"], 60)
        self.assertLessEqual(funnel["L3+ 信号"], funnel["L2+ 信号"])

    def test_distributions(self):
        p = build_panel(records=self._records(), entries=[], meta={})
        self.assertTrue(p["structure"])
        self.assertTrue(p["hour"])
        self.assertTrue(p["temp_bucket"])
        self.assertIn("冲高回落", p["trap"])
        self.assertIn("逆势带头", p["pattern"])

    def test_render_has_sections(self):
        p = build_panel(records=self._records(), entries=[], meta={"day": "2026-10-23"})
        md = render_panel(p)
        for key in ("信号面板", "漏斗", "级别分布", "结构分布", "时间分布"):
            self.assertIn(key, md)

    def test_empty_is_safe(self):
        p = build_panel(records=[], entries=[], meta={})
        self.assertEqual(p["signals"], 0)
        self.assertIn("信号面板", render_panel(p))

    def test_lead_value_table(self):
        rows = [
            {"lead_value": 0.40, "close_ret": -1.0, "t1": -3.0},
            {"lead_value": 0.50, "close_ret": 0.5, "t1": 0.5},
            {"lead_value": 0.70, "close_ret": 2.0, "t1": 3.0},
            {"lead_value": 0.90, "close_ret": 4.0, "t1": 6.0},
        ]
        t = lead_value_table(rows)
        self.assertEqual(len(t), 4)
        self.assertEqual(t[-1]["n"], 1)
        self.assertGreater(t[-1]["t1"], t[0]["t1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""tests/test_fusion_review.py — 复盘与阈值建议：空样本、样本不足、分位建议。"""

import json
import os
import shutil
import tempfile
import unittest

from ats.fusion.review import load_records, render_markdown, suggest_cuts, summarize


def _rec(tier, rar, veto="", div="both_skip", missing=None):
    return {
        "code": "300001",
        "fusion": {"tier": tier, "rar": rar, "veto_reason": veto},
        "divergence": div,
        "missing": missing or [],
    }


class TestReview(unittest.TestCase):
    def test_empty(self):
        s = summarize([])
        self.assertEqual(s["records"], 0)
        self.assertEqual(s["actionable"], 0)
        cuts = suggest_cuts([], min_samples=30)
        self.assertFalse(cuts["ok"])

    def test_summary_counts(self):
        records = [
            _rec(4, 95.0, div="both_buy"),
            _rec(3, 78.0, div="fusion_only"),
            _rec(1, 55.0, div="legacy_only"),
            _rec(0, 0.0, veto="追高透支(偏离均价7.4%)"),
        ]
        s = summarize(records)
        self.assertEqual(s["records"], 4)
        self.assertEqual(s["tier_counts"][4], 1)
        self.assertEqual(s["actionable"], 3)
        self.assertEqual(s["divergence"]["both_buy"], 1)
        self.assertIn("追高透支", s["veto_reasons"])

    def test_insufficient_samples(self):
        records = [_rec(3, 70.0 + i) for i in range(5)]
        cuts = suggest_cuts(records, min_samples=30)
        self.assertFalse(cuts["ok"])
        self.assertIn("暂不给阈值建议", cuts["reason"])

    def test_percentile_cuts(self):
        records = [_rec(2, float(40 + i)) for i in range(100)]
        cuts = suggest_cuts(records, min_samples=30)
        self.assertTrue(cuts["ok"])
        c = cuts["tier_cuts"]
        self.assertLess(c["l1"], c["l2"])
        self.assertLess(c["l2"], c["l3"])
        self.assertLess(c["l3"], c["l4"])
        self.assertAlmostEqual(c["l4"], 129.0, delta=2.0)

    def test_load_and_render(self):
        root = tempfile.mkdtemp(prefix="fusion_review_")
        try:
            d = os.path.join(root, "logs", "fusion_shadow")
            os.makedirs(d)
            day = "2026-10-23"
            with open(os.path.join(d, day + ".jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps(_rec(4, 90.0), ensure_ascii=False) + "\n")
                f.write("not-a-json\n")
                f.write(json.dumps(_rec(2, 66.0), ensure_ascii=False) + "\n")

            records = load_records(day, root)
            self.assertEqual(len(records), 2)
            md = render_markdown(summarize(records), suggest_cuts(records), day)
            self.assertIn("级别分布", md)
            self.assertIn("阈值建议", md)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

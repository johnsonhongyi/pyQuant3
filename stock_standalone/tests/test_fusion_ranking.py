# -*- coding: utf-8 -*-
"""tests/test_fusion_ranking.py — 四道闸门「与」→「打分排序」的验收。

要证明的四件事：
    1. 每道闸门都能给出单调、可解释的 0~1 存活概率（不是靠条件堆叠）；
    2. 领先度按实测 T+1 排序（冲锋队最差），不是按直觉；
    3. 阶段按实测排序（先锋阵亡最强、攻城略地最差）；
    4. 「与」下被否的票，在打分下仍可能进前 N；而真差的票仍被 min_score 挡在门外。
"""

import unittest

from ats.fusion.ranking import (
    RankConfig,
    rank_entries,
    score_entry,
    surv_consensus,
    surv_entry,
    surv_gap,
    surv_lead,
    surv_phase,
)


def _e(**kw):
    base = dict(
        code="300001", day="2026-10-23", stage="入局",
        theme_rank=0.80, first_pct=2.0, efficiency=0.90, persist=65.0,
        patterns={"两阳加速": 1}, consensus=0.30, lead_value=0.70,
        lead_label="排头兵", lead_score=90.0, phase="反攻", gap_risk=10.0,
        enter_time="09:41", enter_price=10.0, enter_pct=2.5,
    )
    base.update(kw)
    return base


class TestSurvivalCurves(unittest.TestCase):
    def test_consensus_monotonic(self):
        vals = [surv_consensus(x) for x in (0.0, 0.30, 0.45, 0.60, 0.65, 0.90)]
        self.assertEqual(vals[0], 1.0)
        self.assertAlmostEqual(vals[1], 1.0)
        self.assertEqual(vals[-1], 0.0)
        for a, b in zip(vals, vals[1:]):
            self.assertGreaterEqual(a, b, "趋同越高存活概率必须越低")

    def test_lead_order_by_measured_t1(self):
        """冲锋队（−1.98%）必须低于无导向（−1.18%），排头兵最高。"""
        self.assertEqual(surv_lead("排头兵"), 1.0)
        self.assertGreater(surv_lead("排头兵"), surv_lead("夺旗"))
        self.assertGreater(surv_lead("夺旗"), surv_lead("无导向"))
        self.assertGreater(surv_lead("无导向"), surv_lead("冲锋队"))
        self.assertGreater(surv_lead("跟风"), surv_lead("冲锋队"))

    def test_phase_order_by_measured_t1(self):
        """先锋阵亡(+3.94%) > 反攻(+2.76%) > 冰点(−0.77%) > 攻城略地(−1.90%)。"""
        self.assertGreater(surv_phase("先锋阵亡", "排头兵"), surv_phase("反攻"))
        self.assertGreater(surv_phase("反攻"), surv_phase("冰点"))
        self.assertGreater(surv_phase("冰点"), surv_phase("攻城略地"))
        # 先锋阵亡期只有最强的能打
        self.assertGreater(surv_phase("先锋阵亡", "排头兵"),
                           surv_phase("先锋阵亡", "冲锋队"))

    def test_gap_monotonic(self):
        self.assertEqual(surv_gap(0), 1.0)
        self.assertGreater(surv_gap(20), surv_gap(50))
        self.assertGreater(surv_gap(50), surv_gap(80))
        self.assertEqual(surv_gap(100), 0.0)

    def test_entry_pattern_dominates(self):
        """无形态的排头兵必须明显低于带"两阳加速"的（实测 C 路径是亏的）。"""
        with_pat = surv_entry(_e(patterns={"两阳加速": 1}))
        other_pat = surv_entry(_e(patterns={"逆势带头": 1}))
        no_pat = surv_entry(_e(patterns={}))
        self.assertGreater(with_pat, other_pat)
        self.assertGreater(other_pat, no_pat)


class TestScoreEntry(unittest.TestCase):
    def test_score_range(self):
        r = score_entry(_e())
        self.assertTrue(0.0 <= r["score"] <= 100.0)
        self.assertTrue(r["ok"])
        for k in ("entry", "consensus", "lead", "phase", "gap"):
            self.assertIn(k, r["parts"])

    def test_hard_chase_rejected(self):
        r = score_entry(_e(first_pct=7.0))
        self.assertFalse(r["ok"], "首异动已涨 7% 是追高，硬拦")
        self.assertIn("追高", r["reason"])

    def test_hard_gap_rejected(self):
        r = score_entry(_e(gap_risk=95.0))
        self.assertFalse(r["ok"], "跨日风险极值必须硬拦")

    def test_not_entered_rejected(self):
        r = score_entry(_e(stage="观察"))
        self.assertFalse(r["ok"])

    def test_weights_normalized(self):
        c = RankConfig(w_entry=2.0, w_consensus=2.0, w_lead=2.0, w_phase=2.0, w_gap=2.0).normalized()
        self.assertAlmostEqual(
            c.w_entry + c.w_consensus + c.w_lead + c.w_phase + c.w_gap, 1.0)


class TestRankEntries(unittest.TestCase):
    def test_ordering_and_top_n(self):
        rows = [
            _e(code="A", lead_label="排头兵", phase="先锋阵亡"),
            _e(code="B", lead_label="冲锋队", phase="攻城略地"),
            _e(code="C", lead_label="夺旗", phase="反攻", consensus=0.40),
        ]
        picked = rank_entries(rows, RankConfig(min_score=0.0), top_n=2)
        self.assertEqual(len(picked), 2)
        self.assertEqual(picked[0]["code"], "A", "先锋阵亡的排头兵应排第一")
        self.assertEqual([r["rank"] for r in picked], [1, 2])
        self.assertGreater(picked[0]["rank_score"], picked[1]["rank_score"])

    def test_floor_keeps_none(self):
        """真差的票（高趋同+攻城略地+冲锋队+高跨日风险）必须被下限挡住。"""
        bad = _e(code="Z", consensus=0.66, phase="攻城略地", lead_label="冲锋队",
                 patterns={"逆势带头": 1}, persist=50.0, first_pct=4.5, gap_risk=85.0)
        self.assertEqual(rank_entries([bad]), [], "宁可不做：分数未达下限不应进清单")
        self.assertLess(score_entry(bad)["score"], RankConfig().min_score)

    def test_no_pattern_loses_qualification(self):
        """无形态不是"扣分"，是没有下单资格（C 路径默认关闭）。"""
        r = score_entry(_e(patterns={}))
        self.assertFalse(r["ok"])
        self.assertIn("无形态", r["reason"])
        self.assertEqual(rank_entries([_e(patterns={})], RankConfig(min_score=0.0)), [])

    def test_top_n_default_is_five(self):
        """分数区分力弱时，分散比集中安全：默认每日 5 只。"""
        self.assertEqual(RankConfig().top_n, 5)

    def test_soft_gate_admits_what_and_gate_rejected(self):
        """趋同 0.62：旧「与」闸门(consensus_max=0.60)否决，打分仍能进前 N。"""
        from ats.fusion.tracker import is_deployable

        e = _e(consensus=0.62)
        self.assertFalse(is_deployable(e), "旧口径应否决")
        picked = rank_entries([e], RankConfig(), top_n=3)
        self.assertEqual(len(picked), 1, "新口径应放行（分数够高）")

    def test_input_not_mutated(self):
        e = _e()
        before = dict(e)
        rank_entries([e], RankConfig(min_score=0.0), top_n=3)
        self.assertEqual(e, before, "打分不能改写入参")

    def test_deterministic(self):
        rows = [_e(code="A"), _e(code="B"), _e(code="C")]
        a = [r["code"] for r in rank_entries(rows, RankConfig(min_score=0.0), top_n=3)]
        b = [r["code"] for r in rank_entries(list(reversed(rows)), RankConfig(min_score=0.0), top_n=3)]
        self.assertEqual(a, b, "同分时排序必须稳定可复现")


if __name__ == "__main__":
    unittest.main(verbosity=2)

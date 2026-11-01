# -*- coding: utf-8 -*-
"""tests/test_fusion_closed_loop.py — 端到端闭环自检。

验证链路真正闭合：
    实时行/快照 -> 适配 -> 四轴评分 -> L0~L4 -> 影子落盘 -> 复盘汇总 -> 阈值建议

用一个合成的"低温翻转日"跑 30 分钟 × 6 只票，断言：
    - 日志条数 = 期望条数（没有丢、没有重复刷）；
    - 级别出现梯度（既有 L4/L3，也有被否决的 L0）；
    - 复盘能给出分位阈值建议；
    - 早启动与晚启动的同一只票，级别不同。
"""

import json
import os
import shutil
import tempfile
import time
import unittest

import pandas as pd

from ats.fusion.regime import (
    FLIP_ARMED,
    FLIP_CONFIRMED,
    FLIP_IDLE,
    STAGE_COLD,
    STAGE_WARMING,
    MarketRegime,
)
from ats.fusion.review import load_records, render_markdown, suggest_cuts, summarize
from ats.fusion.shadow import FusionShadow

_T0 = time.mktime((2026, 10, 23, 10, 0, 0, 0, 0, -1))
_DAY = "2026-10-23"
_MINUTES = 30


def _regime_at(minute):
    """模拟：0~10 分钟偏冷待机，10 分钟拐头，25 分钟确认。"""
    if minute < 10:
        return MarketRegime(temp=44.0, stage=STAGE_COLD, slope_5m=0.5, flip_state=FLIP_IDLE)
    if minute < 25:
        return MarketRegime(temp=47.0, stage=STAGE_COLD, slope_5m=2.0, flip_state=FLIP_ARMED)
    return MarketRegime(temp=56.0, stage=STAGE_WARMING, slope_5m=4.0, flip_state=FLIP_CONFIRMED)


# 每只票：启动分钟、基准价、均价、最终涨幅、是否已在高位、是否龙头
_SPECS = {
    "300111": dict(start=2, base=12.55, vwap=12.60, pct_end=4.2, high_pos=False, leader=True),
    "300222": dict(start=3, base=12.60, vwap=12.60, pct_end=6.8, high_pos=True, leader=False),
    "300333": dict(start=20, base=11.80, vwap=11.85, pct_end=2.1, high_pos=False, leader=False),
    "300444": dict(start=4, base=12.30, vwap=12.35, pct_end=5.4, high_pos=True, leader=False),
    "300555": dict(start=12, base=8.10, vwap=8.12, pct_end=3.0, high_pos=False, leader=False),
    "300666": dict(start=6, base=21.0, vwap=21.1, pct_end=9.2, high_pos=True, leader=False),
}


def _row_for(code, minute):
    spec = _SPECS[code]
    if minute < spec["start"]:
        pct = 0.2
    else:
        span = max(1, _MINUTES - spec["start"])
        pct = 0.2 + (spec["pct_end"] - 0.2) * (minute - spec["start"]) / span
    price = round(spec["base"] * (1 + pct / 100.0), 3)
    high = round(price * (1.0 if spec["high_pos"] else 1.012), 3)
    low = round(spec["base"] * 0.995, 3)
    return pd.Series(
        {
            "trade": price,
            "vwap": spec["vwap"],
            "percent": round(pct, 2),
            "high": high,
            "low": low,
            "amount": 6.0e8 * (1 + minute / 30.0),
            "volume": 5.0e4 * (1 + minute / 30.0),
            "ratio": 2.2,
            "turnover": 9.0,
            "vwap_cum_5d": round(spec["base"] * 0.99, 3),
        }
    )


def _snap_for(code):
    spec = _SPECS[code]
    return {
        "name": code,
        "taker_buy_ratio": 72.0,
        "bid_pressure": 66.0,
        "slope_score": 84.0,
        "intent_score": 88.0,
        "structure_clarity_score": 80.0,
        "sbc_supp_price": round(spec["base"] * 0.995, 3),
        "neck_price": round(spec["base"] * 1.045, 3),
        "sector_resonance": 78.0 if spec["leader"] else 60.0,
        "velocity_pct": 1.3 if spec["leader"] else 0.8,
        "is_leader": spec["leader"],
        "minutes_above_vwap": 25.0,
    }


class TestClosedLoop(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fusion_loop_")
        cfg = {
            "enabled": True,
            "shadow_only": True,
            "log_dir": "logs/fusion_shadow",
            "sample_interval_s": 0.0,
            "max_records_per_day": 100000,
        }
        self.shadow = FusionShadow(config=cfg, regime_provider=lambda ts: self._regime(ts), root=self.root)
        self.records = []

    def _regime(self, ts):
        return _regime_at(int((ts - _T0) // 60))

    def tearDown(self):
        try:
            self.shadow.close()
        finally:
            shutil.rmtree(self.root, ignore_errors=True)

    def _run(self):
        for minute in range(_MINUTES):
            now = _T0 + minute * 60
            for code in _SPECS:
                rec = self.shadow.observe(
                    code=code,
                    row=_row_for(code, minute),
                    snap=_snap_for(code),
                    decision={"action": "HOLD", "reason": "现有逻辑观望"},
                    name=code,
                    now=now,
                )
                if rec:
                    self.records.append(rec)

    def test_closed_loop(self):
        self._run()
        expected = _MINUTES * len(_SPECS)
        self.assertEqual(len(self.records), expected)

        tiers = [r["fusion"]["tier"] for r in self.records]
        self.assertIn(4, tiers, "翻转确认期应出现 L4")
        self.assertTrue(any(t == 0 for t in tiers), "追高票应被压到 L0")
        self.assertTrue(any(t in (2, 3) for t in tiers), "应出现中间档位")

        # 早启动 vs 晚启动：同一时刻级别必须不同（先手衰减）
        late_minute = self.records[-1]["ts"]
        by_code = {}
        for r in self.records:
            if r["ts"] == late_minute:
                by_code[r["code"]] = r["fusion"]
        # 先手衰减的方向性：30 分钟时，早启动的龙头（300111，启动于第 2 分钟）
        # 必须已经被降到 L3 及以下；刚启动的（300333，启动于第 20 分钟）仍可拿 L4。
        self.assertGreater(by_code["300333"]["tier"], by_code["300111"]["tier"])
        self.assertGreater(by_code["300111"]["age_min"], by_code["300333"]["age_min"])
        self.assertLessEqual(by_code["300111"]["tier"], 3)

        # 落盘 + 复盘闭环
        self.shadow.flush()
        path = os.path.join(self.root, "logs", "fusion_shadow", "{}_{}.jsonl".format(_DAY, os.getpid()))
        with open(path, "r", encoding="utf-8") as f:
            lines = [x for x in f if x.strip()]
        self.assertEqual(len(lines), expected)

        loaded = load_records(_DAY, self.root)
        self.assertEqual(len(loaded), expected)

        summary = summarize(loaded)
        self.assertEqual(summary["records"], expected)
        self.assertGreater(summary["actionable"], 0)

        cuts = suggest_cuts(loaded, min_samples=30)
        self.assertTrue(cuts["ok"], "样本足够时应给出阈值建议")
        self.assertLess(cuts["tier_cuts"]["l1"], cuts["tier_cuts"]["l4"])

        md = render_markdown(summary, cuts, _DAY)
        for section in ("级别分布", "分歧", "阈值建议"):
            self.assertIn(section, md)

    def test_no_duplicate_writes_within_interval(self):
        cfg = {
            "enabled": True,
            "log_dir": "logs/fusion_shadow",
            "sample_interval_s": 5.0,
            "max_records_per_day": 1000,
        }
        shadow = FusionShadow(config=cfg, regime_provider=self._regime, root=self.root)
        try:
            a = shadow.observe(code="300111", row=_row_for("300111", 10), snap=_snap_for("300111"),
                               now=_T0 + 600)
            b = shadow.observe(code="300111", row=_row_for("300111", 10), snap=_snap_for("300111"),
                               now=_T0 + 602)
            self.assertIsNotNone(a)
            self.assertIsNone(b)
            self.assertEqual(shadow.stats()["records"], 1)
        finally:
            shadow.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

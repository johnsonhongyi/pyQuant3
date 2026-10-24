# -*- coding: utf-8 -*-
"""tests/test_fusion_trade_sim.py — T+1 交易模拟自检。

核心不变量：
1. 买入当日绝不卖出（哪怕跌破止损）；
2. 当日跌破止损要记为"被锁"，并量化额外损失；
3. 次日才允许止损/止盈，跳空按开盘价兜底；
4. 限价单未触及区间则 EXPIRED，市价模式必成交；
5. 每日开仓数受限，验收标的强制纳入。
"""

import time
import unittest

import numpy as np

from ats.fusion.trade_sim import T1Simulator, summarize_trades

_DTYPE = [
    ("time", "<i8"),
    ("open", "<f4"),
    ("high", "<f4"),
    ("low", "<f4"),
    ("close", "<f4"),
    ("volume", "<f4"),
    ("cum_vol_start", "<f4"),
]

_D1 = "2026-10-20"
_D2 = "2026-10-21"


def _bars(day, o, h, l, c, start_h=9, start_m=30):
    n = len(c)
    arr = np.zeros(n, dtype=_DTYPE)
    base = int(time.mktime(time.strptime("{} {:02d}:{:02d}".format(day, start_h, start_m), "%Y-%m-%d %H:%M")))
    for i in range(n):
        arr[i] = (base + i * 180, o[i], h[i], l[i], c[i], 10000.0, 0.0)
    return arr


def _mk_cache():
    # 第一天：买入后先跌 3%（跌破止损），尾盘拉回
    o1 = [10.0, 10.0, 9.7, 9.9]
    h1 = [10.05, 10.0, 9.8, 10.0]
    l1 = [9.95, 9.6, 9.65, 9.85]
    c1 = [10.0, 9.7, 9.75, 9.95]
    # 第二天：低开 9.3，随后拉到 10.6
    o2 = [9.3, 9.6, 10.2, 10.5]
    h2 = [9.4, 10.3, 10.6, 10.7]
    l2 = [9.2, 9.5, 10.0, 10.4]
    c2 = [9.35, 10.2, 10.5, 10.6]
    base = np.concatenate([_bars(_D1, o1, h1, l1, c1), _bars(_D2, o2, h2, l2, c2)])
    return {"300001": base, "300002": base.copy(), "300003": base.copy()}


def _decision(ts=None, tier=3, band=(10.0, 10.1), stop=9.8, code="300001"):
    base = int(time.mktime(time.strptime(_D1 + " 09:30", "%Y-%m-%d %H:%M")))
    return {
        "code": code,
        "ts": ts or (base + 180),
        "tier": tier,
        "rar": 80.0,
        "size_pct": 18.0,
        "stop": stop,
        "entry_price": band[1],
        "entry": {"price_lo": band[0], "price_hi": band[1]},
    }


class TestT1(unittest.TestCase):
    def setUp(self):
        self.cache = _mk_cache()
        self.sim = T1Simulator(self.cache, [_D1, _D2])

    def test_no_sell_on_entry_day(self):
        orders, trades = self.sim.simulate([_decision()])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, "FILLED")
        self.assertEqual(len(trades), 1)
        t = trades[0]
        # 卖出必须发生在次日
        self.assertGreaterEqual(t.exit_ts, self._day_start(_D2))

    def test_blocked_stop_recorded(self):
        orders, trades = self.sim.simulate([_decision(stop=9.8)])
        t = trades[0]
        self.assertTrue(t.stop_blocked)
        self.assertLess(t.day0_mae_pct, 0)

    def test_exit_next_day_by_stop_or_target(self):
        orders, trades = self.sim.simulate([_decision(stop=9.8)], target_pct=6.0)
        t = trades[0]
        self.assertIn(t.exit_reason, ("跳空破止损", "止损", "止盈+6%", "VWAP破位次日开盘出", "止损(双触保守)"))
        self.assertGreater(t.exit_price, 0)

    def test_limit_expired_when_band_untouched(self):
        # 买入区间远低于现价，次日也不回落 -> 未成交
        orders, trades = self.sim.simulate([_decision(band=(5.0, 5.05))])
        self.assertEqual(orders[0].status, "EXPIRED")
        self.assertEqual(trades, [])

    def test_market_mode_always_fills(self):
        orders, trades = self.sim.simulate([_decision(band=(5.0, 5.05))], fill_mode="market")
        self.assertEqual(orders[0].status, "FILLED")
        self.assertEqual(len(trades), 1)

    def test_max_per_day_and_focus(self):
        ds = [
            _decision(code="300001", ts=self._day_start(_D1) + 180),
            _decision(code="300002", ts=self._day_start(_D1) + 360),
            _decision(code="300003", ts=self._day_start(_D1) + 540),
        ]
        orders, _ = self.sim.simulate(ds, max_per_day=1)
        self.assertEqual(len(orders), 1)
        orders2, _ = self.sim.simulate(ds, max_per_day=1, focus_codes=("300003",))
        self.assertEqual(len(orders2), 2)   # top1 + 验收标的

    def test_summary_by_window(self):
        _, trades = self.sim.simulate([_decision()])
        s = summarize_trades(trades)
        self.assertEqual(s["all"]["n"], 1)
        self.assertIn("开盘30分", s["by_window"])

    @staticmethod
    def _day_start(day):
        return int(time.mktime(time.strptime(day + " 00:00", "%Y-%m-%d %H:%M")))


if __name__ == "__main__":
    unittest.main(verbosity=2)

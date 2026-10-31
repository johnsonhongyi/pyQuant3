from datetime import datetime, timedelta
import unittest

import signal_engine
from zoneinfo import ZoneInfo

NOW = datetime(2026, 10, 14, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))

CFG = {
    "version": "v1.11",
    "buy": {"max_day_chg": 7.0, "max_positions": 5, "amount_per_trade": 100000},
    "sell": {"take_profit": .1, "stop_loss": -.06},
    "execution": {
        "signal": {"entry_threshold": 62, "vwap_band": {"low": .995, "high": 1.03},
                   "weights": {"trend": 25, "intraday": 25, "relative": 20, "theme": 15, "liquidity": 15}},
        "regime_policy": {"cautious": {"statuses": ["分歧"], "exposure": .5, "min_score": 70, "max_positions": 2}},
    },
}


def bar(day, close, volume=1000, high=None, low=None, open_=None, source="sina"):
    high = close * 1.01 if high is None else high
    low = close * .99 if low is None else low
    open_ = close if open_ is None else open_
    return {"time": day, "open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "amount": close * volume,
            "meta": {"source": source, "stale": False, "fetched_at": NOW.isoformat(),
                     "available_fields": ["volume_shares"]}}


def daily(rising=True, n=25):
    start = datetime(2026, 9, 19)
    rows = []
    for i in range(n):
        day = (start + timedelta(days=i)).date().isoformat() + "T00:00:00+08:00"
        close = 10 + i * 0.1 if rising else 13 - i * 0.12
        rows.append(bar(day, close))
    return rows


def minute(price=12.6):
    rows = []
    start = datetime(2026, 10, 14, 9, 35, tzinfo=NOW.tzinfo)
    for i in range(10):
        clock = (start + timedelta(minutes=5 * i)).isoformat()
        rows.append(bar(clock, price - 0.05 + i * 0.01))
    return rows


def quote(price=12.6, change=None, name="样本"):
    previous = 12.0
    return {"symbol": "600001.SH", "name": name, "price": price, "previous_close": previous,
            "open": 12.0, "high": max(price, 12.2), "change_percent": change if change is not None else (price / previous - 1) * 100,
            "trade_time": "2026-10-14T10:15:00+08:00",
            "meta": {"source": "sina", "stale": False, "fetched_at": NOW.isoformat()}}


def context(ai=None):
    return {"now": NOW, "today": "2026-10-14", "previous_day": "2026-10-13", "cfg": CFG,
            "theme": {"change_percent": 2.0, "rising_nodes": 5, "falling_nodes": 2,
                      "leader_rank": 2, "rank": 1},
            "pool_change_median": 1.0, "ai": ai or {}}


class SignalEngineTests(unittest.TestCase):
    def test_strong_setup_scores_above_threshold(self):
        result = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(), minute(),
                                        daily(), context())
        self.assertEqual(result["blockers"], [])
        self.assertGreaterEqual(result["score"], 70)
        self.assertGreater(result["layers"]["trend"]["score"], 20)
        self.assertGreater(result["layers"]["intraday"]["score"], 20)

    def test_weak_trend_scores_low(self):
        result = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(11.4),
                                        minute(11.4), daily(rising=False), context())
        self.assertLess(result["score"], 60)

    def test_sealed_limit_up_is_blocked(self):
        result = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(13.2, 10.0),
                                        minute(13.2), daily(), context())
        self.assertIn("sealed limit-up", result["blockers"])

    def test_falling_knife_is_blocked(self):
        result = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(11.5, -4.2),
                                        minute(11.5), daily(), context())
        self.assertIn("P4 falling knife", result["blockers"])

    def test_far_above_vwap_is_blocked(self):
        result = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(13.3, 10.8),
                                        minute(12.8), daily(), context())
        self.assertIn("P8 VWAP gate", result["blockers"])

    def test_ai_veto_and_bonus(self):
        veto = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(), minute(),
                                      daily(), context({"veto": True, "delta": 0}))
        self.assertIn("AI veto", veto["blockers"])
        bonus = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(), minute(),
                                       daily(), context({"delta": 12, "status": "admit"}))
        base = signal_engine.evaluate({"symbol": "600001.SH", "name": "样本"}, quote(), minute(),
                                      daily(), context())
        self.assertEqual(bonus["score"], min(100, base["score"] + 12))


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest
from zoneinfo import ZoneInfo

import attribution
import auto_follow as af

NOW = datetime(2026, 10, 14, 10, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
TODAY, PREVIOUS = "2026-10-14", "2026-10-13"


def meta(at=None):
    return {"source": "sina", "stale": False, "fetched_at": (at or NOW).isoformat(),
            "available_fields": ["volume_shares"]}


def bar(day, close, volume=1000, at=None):
    return {"time": day, "open": close, "high": close * 1.01, "low": close * .99, "close": close,
            "volume": volume, "amount": close * volume, "meta": meta(at)}


def daily():
    start = datetime(2026, 9, 19)
    return [bar((start + timedelta(days=i)).date().isoformat() + "T00:00:00+08:00", 10 + i * .1)
            for i in range(25)]


def minute():
    start = datetime(2026, 10, 14, 9, 35, tzinfo=NOW.tzinfo)
    return [bar((start + timedelta(minutes=5 * i)).isoformat(), 12.55 + i * .01) for i in range(10)]


def quote(symbol="600001.SH", price=12.6):
    return {"symbol": symbol, "name": "样本", "price": price, "previous_close": 12.0,
            "open": 12.0, "high": price, "change_percent": (price / 12.0 - 1) * 100,
            "trade_time": NOW.isoformat(), "meta": meta()}


def ladder():
    stock = {"symbol": "600001.SH", "name": "样本", "streak": 3, "is_st": False, "primary_theme": "算力"}
    return {"meta": {"source": "test", "stale": False, "fetched_at": NOW.isoformat(), "trade_date": TODAY},
            "current": {"trade_date": TODAY, "levels": [{"stocks": [stock]}]},
            "previous": {"trade_date": PREVIOUS, "levels": [{"stocks": [stock]}]}}


def overview():
    return {"meta": {"source": "test", "stale": False, "fetched_at": NOW.isoformat()},
            "data": [{"theme": "算力", "name": "算力", "change_percent": 3.0, "rising_nodes": 6,
                      "falling_nodes": 1, "leader_stocks": [{"symbol": "600001.SH", "name": "样本"}]}]}


CFG = {
    "version": "v1.11",
    "buy": {"max_positions": 5, "amount_per_trade": 100000, "max_day_chg": 7,
            "min_market_sentiment": -40, "min_market_sentiment_low_water": -15, "forbid_dead_day": True},
    "sell": {"take_profit": .1, "stop_loss": -.06, "vwap_stop": .02, "break_ma10": True, "max_hold_days": 5},
    "decision_gate": {"kill": {"max_day_loss_pct": .03}},
    "execution": {
        "regime_policy": {
            "attack": {"statuses": ["高位延续"], "exposure": 1.0, "min_score": 60, "max_positions": 5},
            "balanced": {"statuses": ["高位震荡"], "exposure": .8, "min_score": 64, "max_positions": 4},
            "cautious": {"statuses": ["分歧"], "exposure": .5, "min_score": 60, "max_positions": 2},
            "defense": {"statuses": ["强分歧"], "exposure": 0, "min_score": 100, "max_positions": 0},
        },
        "signal": {"entry_threshold": 60, "vwap_band": {"low": .995, "high": 1.03}},
        "ai_gate": {"mode": "overlay", "weight": 12, "ttl_seconds": 900, "fallback": "neutral"},
        "strong_scan": {"enabled": False},
        "optimizer": {"mode": "off"},
    },
}


class Calendar:
    @staticmethod
    def is_trading_day(day, market):
        return True

    @staticmethod
    def prev_trading_day(day, market):
        return PREVIOUS


class LoopCycleTests(unittest.TestCase):
    def api(self, path):
        if path.startswith("/api/v1/short-term/limit-up-ladder"):
            return {"data": ladder()}
        if path.startswith("/api/v1/themes/overview"):
            return {"data": overview()["data"], "meta": overview()["meta"]}
        if path.startswith("/api/v1/quotes/kline"):
            if "period=day" in path:
                return {"data": daily()}
            return {"data": minute()}
        if path.startswith("/api/v1/quotes/realtime"):
            return {"data": [quote()]}
        raise AssertionError("unexpected path " + path)

    def test_divergence_trades_with_reduced_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = attribution.connect(str(Path(tmp) / "account.db"))
            try:
                state = af.initial()
                result = af.cycle(state, CFG, self.api, NOW, Calendar,
                                  {"backend_status": "分歧", "risk_score": 50.9}, False, journal=db)
                self.assertEqual(result, "completed")
                self.assertEqual(state["regime"]["code"], "cautious")
                self.assertEqual(len(state["positions"]), 1)
                position = state["positions"][0]
                self.assertLessEqual(position["shares"] * position["buy_price"], 50000 + 1)
                self.assertGreaterEqual(position["entry_score"], 60)
                self.assertEqual(state["loop"]["funnel"]["fills"], 1)
                self.assertEqual(state["loop"]["regime"], "cautious")
                row = db.execute("SELECT status,score,regime FROM decisions").fetchone()
                self.assertEqual(row[0], "filled")
                self.assertEqual(row[2], "cautious")
            finally:
                db.close()

    def test_defense_does_not_trade(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = attribution.connect(str(Path(tmp) / "account.db"))
            try:
                state = af.initial()
                result = af.cycle(state, CFG, self.api, NOW, Calendar,
                                  {"backend_status": "强分歧", "risk_score": 75}, False, journal=db)
                self.assertEqual(result, "defense")
                self.assertEqual(state["positions"], [])
                self.assertEqual(state["loop"]["regime"], "defense")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

import attribution

NOW = datetime(2026, 10, 21, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def evaluation(symbol="600001.SH", score=72):
    return {"symbol": symbol, "score": score, "raw_score": score,
            "metrics": {"price": 10.0}, "blockers": ["P8 VWAP gate"],
            "layers": {"trend": {"score": 20}}, "ai": {"status": "neutral"}}


def bars():
    rows = []
    closes = [10.0, 10.2, 10.5, 11.0, 11.5, 12.0]
    start = datetime(2026, 10, 14)
    for index, close in enumerate(closes):
        day = (start + timedelta(days=index)).date().isoformat()
        rows.append({"time": day + "T00:00:00+08:00", "close": close, "high": close,
                     "low": close, "open": close, "volume": 1000, "amount": close * 1000,
                     "meta": {"source": "test", "stale": False}})
    return rows


class AttributionTests(unittest.TestCase):
    def test_settle_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = attribution.connect(str(Path(tmp) / "account.db"))
            try:
                day = datetime(2026, 10, 14, 10, 0, tzinfo=NOW.tzinfo)
                attribution.record(db, day, evaluation(), "blocked", "P8 VWAP gate", "cautious", 70)
                api = lambda path: {"data": bars()}
                updated = attribution.settle(db, api, NOW)
                self.assertEqual(updated, 1)
                summary = attribution.summary(db, NOW)
                self.assertEqual(summary["samples"], 1)
                self.assertEqual(summary["settled"], 1)
                self.assertAlmostEqual(summary["blockers"][0]["avg"], 0.10, places=6)
                self.assertEqual(summary["blockers"][0]["reason"], "P8 VWAP gate")
            finally:
                db.close()

    def test_priority_prevents_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = attribution.connect(str(Path(tmp) / "account.db"))
            try:
                day = datetime(2026, 10, 14, 10, 0, tzinfo=NOW.tzinfo)
                attribution.record(db, day, evaluation(), "filled", "", "attack", 60)
                attribution.record(db, day, evaluation(), "blocked", "P8 VWAP gate", "attack", 60)
                row = db.execute("SELECT status FROM decisions").fetchone()
                self.assertEqual(row[0], "filled")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()

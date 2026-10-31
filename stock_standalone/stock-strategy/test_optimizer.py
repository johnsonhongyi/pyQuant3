from datetime import datetime
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo

import optimizer

NOW = datetime(2026, 10, 31, 16, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
CFG = {
    "version": "v1.11",
    "buy": {"max_day_chg": 7.0},
    "sell": {"stop_loss": -0.06, "take_profit": 0.10},
    "execution": {
        "signal": {"entry_threshold": 62, "vwap_band": {"low": .995, "high": 1.03}},
        "regime_policy": {"cautious": {"exposure": .5}},
        "optimizer": {"mode": "auto", "min_samples": 8, "cooldown_days": 3,
                      "max_daily_changes": 1, "rollback_loss_pct": .02,
                      "rollback_trades": 5, "pause_days": 5},
    },
}


def summary(blockers=None, trades=None, buckets=None, regimes=None):
    return {"settled": 20, "samples": 20, "blockers": blockers or [], "trades": trades or {"n": 0},
            "buckets": buckets or [], "regimes": regimes or []}


class OptimizerTests(unittest.TestCase):
    def test_vwap_band_widens_with_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = str(Path(tmp) / "account.db")
            db = sqlite3.connect(str(Path(tmp) / "loop.db"))
            try:
                state = {"initial_cash": 500000}
                result = optimizer.run(db, state, CFG, NOW, account, summary(
                    blockers=[{"reason": "P8 VWAP gate", "n": 12, "win": .70, "avg": .03}]))
                self.assertEqual(result["status"], "applied")
                self.assertEqual(result["proposal"]["key"], "execution.signal.vwap_band.high")
                params = optimizer.load_params(account)
                self.assertAlmostEqual(params["overrides"]["execution.signal.vwap_band.high"], 1.035)
                merged = optimizer.apply_overrides(CFG, params)
                self.assertAlmostEqual(merged["execution"]["signal"]["vwap_band"]["high"], 1.035)
                self.assertEqual(merged["runtime_version"], "v1.11+opt.1")
            finally:
                db.close()

    def test_regime_threshold_tightens_when_high_bucket_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = str(Path(tmp) / "account.db")
            db = sqlite3.connect(str(Path(tmp) / "loop.db"))
            try:
                state = {"initial_cash": 500000}
                result = optimizer.run(db, state, CFG, NOW, account, summary(
                    buckets=[{"bucket": "80+", "n": 10, "win": .70, "avg": .03},
                             {"bucket": "60-69", "n": 10, "win": .30, "avg": -.02}]))
                self.assertEqual(result["status"], "applied")
                self.assertEqual(result["proposal"]["key"], "execution.regime_policy.cautious.min_score")
                self.assertEqual(result["proposal"]["new"], 72)
            finally:
                db.close()

    def test_stop_only_tightens(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = str(Path(tmp) / "account.db")
            db = sqlite3.connect(str(Path(tmp) / "loop.db"))
            try:
                state = {"initial_cash": 500000}
                result = optimizer.run(db, state, CFG, NOW, account, summary(
                    trades={"n": 10, "win_rate": .30, "avg_pnl": -1200, "profit_factor": .5}))
                self.assertEqual(result["status"], "applied")
                self.assertEqual(result["proposal"]["key"], "sell.stop_loss")
                self.assertAlmostEqual(result["proposal"]["new"], -0.055)
            finally:
                db.close()

    def test_drawdown_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = str(Path(tmp) / "account.db")
            Path(account).write_bytes(b"")
            (Path(tmp) / "params.json").write_text(json.dumps({
                "version": "v1.11+opt.1", "base_version": "v1.11",
                "overrides": {"sell.stop_loss": -0.055}, "applied_at": "2026-10-01T16:00:00+08:00",
            }), encoding="utf-8")
            db = sqlite3.connect(str(Path(tmp) / "loop.db"))
            try:
                db.execute("""CREATE TABLE IF NOT EXISTS trades(trade_id TEXT PRIMARY KEY, symbol TEXT, buy_date TEXT,
                              sell_date TEXT, buy_price REAL, sell_price REAL, shares INTEGER, pnl REAL, reason TEXT,
                              score INTEGER, regime TEXT, layers TEXT, mfe REAL, mae REAL, at TEXT)""")
                for index in range(5):
                    db.execute("INSERT INTO trades(trade_id,symbol,sell_date,pnl) VALUES(?,?,?,?)",
                               ("t%d" % index, "600001.SH", "2026-10-2%d" % (index + 1), -3000))
                state = {"initial_cash": 500000}
                result = optimizer.run(db, state, CFG, NOW, account, summary())
                self.assertEqual(result["status"], "rolled_back")
                self.assertEqual(optimizer.load_params(account)["overrides"], {})
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()

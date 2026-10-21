from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import subprocess
import os
import sys
import shutil
import time
import json
import unittest
from unittest.mock import patch

import auto_follow as af

NOW = datetime(2026, 10, 14, 10, 30, tzinfo=af.BJ)
CFG = {"buy": {"max_positions": 5, "amount_per_trade": 100000, "max_day_chg": 7,
               "min_market_sentiment": -40, "min_market_sentiment_low_water": -15, "forbid_dead_day": True},
       "sell": {"take_profit": .1, "stop_loss": -.06, "vwap_stop": .02, "break_ma10": True, "max_hold_days": 5},
       "decision_gate": {"kill": {"max_day_loss_pct": .03}}}


def quote(price=10.2):
    return {"symbol": "600001.SH", "name": "合成样本", "price": price, "previous_close": 10,
            "change_percent": (price / 10 - 1) * 100, "trade_time": NOW.isoformat(),
            "high": price, "open": 10, "meta": {"source": "test", "stale": False, "fetched_at": NOW.isoformat()}}


class Calendar:
    @staticmethod
    def is_trading_day(day, market):
        return True

    @staticmethod
    def prev_trading_day(day, market):
        return "2026-10-13"


class FollowTests(unittest.TestCase):
    def test_utf8_runtime_config_loads_without_windows_default_codec(self):
        cfg = af.load_config()
        self.assertEqual(cfg["version"], "v1.9")
        self.assertEqual(cfg["buy"]["max_positions"], 5)

    def test_stale_cross_day_nan_quotes_fail_closed(self):
        for mutate in (lambda q: q["meta"].update(stale=True),
                       lambda q: q.update(trade_time=(NOW - timedelta(days=1)).isoformat()),
                       lambda q: q.update(price=float("nan")),
                       lambda q: q["meta"].update(source="")):
            q = quote()
            mutate(q)
            with self.assertRaises(ValueError):
                af.quote_ok(q, NOW)

    def test_t1_and_exit_before_entry_kill(self):
        state = af.initial()
        p = {"symbol": "600001.SH", "buy_date": "2026-10-14", "buy_price": 12,
             "shares": 100, "buy_vwap": 12, "buy_vwap10": 12}
        state["positions"] = [p]
        api = lambda path: {"data": [quote()]}
        af.cycle(state, CFG, api, NOW, Calendar, {}, True)
        self.assertEqual(len(state["positions"]), 1)
        p["buy_date"] = "2026-10-13"
        af.cycle(state, CFG, api, NOW, Calendar, {}, True)
        self.assertEqual(state["positions"], [])
        self.assertEqual(state["closed"][0]["reason"], "stop_loss")

    def test_limit_down_does_not_assume_fill(self):
        state = af.initial()
        state["positions"] = [{"symbol": "600001.SH", "buy_date": "2026-10-13",
                               "buy_price": 10, "shares": 100, "buy_vwap": 10, "buy_vwap10": 10}]
        af.cycle(state, CFG, lambda path: {"data": [quote(9)]}, NOW, Calendar, {}, True)
        self.assertEqual(len(state["positions"]), 1)
        self.assertEqual(state["events"][0]["action"], "SKIP_SELL")

    def test_buy_is_deduplicated_and_respects_cash(self):
        state = af.initial()
        state["cash"] = 2500
        c = {"symbol": "600001.SH", "name": "样本", "route": "theme_trend"}
        def api(path):
            if "realtime" in path:
                return {"data": [quote()]}
            return {"data": []}
        with patch.object(af, "candidates", return_value=[c]), patch.object(af, "entry_ok", return_value={"buy_vwap": 10, "buy_vwap10": 9}):
            for _ in range(2):
                af.cycle(state, CFG, api, NOW, Calendar, {"score": 0}, False)
        self.assertEqual(len(state["positions"]), 1)
        self.assertEqual(state["positions"][0]["shares"], 200)
        self.assertAlmostEqual(state["cash"], 460)

    def test_realized_loss_arms_persistent_kill(self):
        state = af.initial()
        state["closed"] = [{"sell_date": "2026-10-14", "pnl": -15000}]
        result = af.cycle(state, CFG, lambda path: self.fail("kill should block API"), NOW, Calendar, {"score": 0}, False)
        self.assertEqual(result, "kill_switch")
        self.assertTrue(state["kill"])

    def test_transaction_rollback_restart_and_single_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "account.db"
            a, b = af.connect(path), af.connect(path)
            try:
                a.execute("BEGIN IMMEDIATE")
                a.execute("INSERT INTO state VALUES(1,'{}')")
                with self.assertRaises(af.sqlite3.OperationalError):
                    b.execute("BEGIN IMMEDIATE")
                a.rollback()
                self.assertIsNone(b.execute("SELECT body FROM state").fetchone())
                a.execute("INSERT INTO state VALUES(1,'{}')")
                self.assertEqual(b.execute("SELECT body FROM state").fetchone()[0], "{}")
            finally:
                a.close()
                b.close()

    def test_entry_rejects_sealed_board_and_stale_daily(self):
        q = quote(11)
        with self.assertRaisesRegex(ValueError, "P4|sealed"):
            af.entry_ok(q, [], [], CFG, NOW, "2026-10-13")
        with self.assertRaisesRegex(ValueError, "intraday"):
            af.entry_ok(quote(), [], [], CFG, NOW, "2026-10-13")

    def test_tdx_shares_and_eastmoney_lots_agree(self):
        self.assertEqual(af.exact_vwap([{"amount": 10000, "volume": 1000,
                         "meta": {"source": "tdx", "available_fields": ["volume_shares"]}}]), 10)
        self.assertEqual(af.exact_vwap([{"amount": 10000, "volume": 10,
                         "meta": {"source": "eastmoney"}}]), 10)
        with self.assertRaises(ValueError):
            af.exact_vwap([{"amount": 10000, "volume": 1000, "meta": {"source": "unknown"}}])

    def test_complete_entry_and_previous_day_freshness(self):
        daily = []
        for i in range(20):
            price = 8 + i * .1
            daily.append({"time": (NOW - timedelta(days=20-i)).isoformat(), "close": price,
                          "amount": price * 1000, "volume": 1000,
                          "meta": {"source": "tdx", "stale": False, "available_fields": ["volume_shares"]}})
        minute = [{"time": (NOW - timedelta(minutes=20-i*5)).isoformat(), "close": 10+i*.02,
                   "amount": 10.1 * (1000+i*100), "volume": 1000+i*100,
                   "meta": {"source": "tdx", "stale": False, "fetched_at": NOW.isoformat(),
                            "available_fields": ["volume_shares"]}} for i in range(4)]
        anchors = af.entry_ok(quote(), minute, daily, CFG, NOW, "2026-10-13")
        self.assertAlmostEqual(anchors["buy_vwap"], 9.9)
        daily[-1]["meta"]["stale"] = True
        with self.assertRaisesRegex(ValueError, "daily source"):
            af.entry_ok(quote(), minute, daily, CFG, NOW, "2026-10-13")

    def test_candidate_routes_and_cross_day_block(self):
        meta = {"source": "test", "stale": False, "fetched_at": NOW.isoformat()}
        ladder = {"meta": meta, "current": {"trade_date": "2026-10-14"},
                  "previous": {"trade_date": "2026-10-13", "levels": [{"stocks": [
                      {"symbol": "600001.SH", "name": "连板样本", "streak": 2}]}]}}
        overview = {"meta": meta, "data": [{"theme": "test", "change_percent": 3,
                    "rising_nodes": 4, "falling_nodes": 1,
                    "leader_stocks": [{"symbol": "000001.SZ", "name": "趋势样本"}]}]}
        pool = af.candidates(ladder, overview, NOW, "2026-10-13")
        self.assertEqual({c["route"] for c in pool}, {"limit_up", "theme_trend"})
        overview['data'][0]['leader_stocks'].append({'symbol':'600001.SH','name':'连板样本'})
        attributed=af.candidates(ladder,overview,NOW,'2026-10-13')
        self.assertEqual(next(c for c in attributed if c['symbol']=='600001.SH')['theme'],'test')
        ladder["current"]["trade_date"] = "2026-10-13"
        with self.assertRaisesRegex(ValueError, "today"):
            af.candidates(ladder, overview, NOW, "2026-10-13")

    def test_stale_or_carry_forward_overview_preserves_ladder_candidates(self):
        ladder_meta = {"source": "test", "stale": False, "fetched_at": NOW.isoformat()}
        ladder = {"meta": ladder_meta, "current": {"trade_date": "2026-10-14"},
                  "previous": {"trade_date": "2026-10-13", "levels": [{"stocks": [
                      {"symbol": "600001.SH", "name": "连板样本", "streak": 2}]}]}}
        stale_overview = {"meta": {"source": "theme-radar:fusion", "stale": True, "carry_forward": True,
                                   "trade_date": "2026-10-13", "fetched_at": NOW.isoformat()},
                          "data": [{"theme": "stale_theme", "change_percent": 5, "rising_nodes": 3, "falling_nodes": 0,
                                    "leader_stocks": [{"symbol": "000002.SZ", "name": "过期龙头"}]}]}
        pool = af.candidates(ladder, stale_overview, NOW, "2026-10-13")
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["symbol"], "600001.SH")
        self.assertEqual(pool[0]["route"], "limit_up")

    def test_native_backend_emotion_requires_coverage_and_freshness(self):
        payload = {"data": {"intraday": {"stale": False, "trade_date": "2026-10-14",
                   "updated_at": NOW.isoformat(), "status": "高位震荡", "risk_score": 20,
                   "metrics": {"high_sample_count": 4, "high_quote_count": 4}}}}
        market = af.backend_market(lambda path: payload, NOW)
        self.assertNotIn("score", market)  # Never invent a Muse sentiment score.
        self.assertEqual(market["risk_score"], 20)
        payload["data"]["intraday"]["metrics"]["high_quote_count"] = 2
        with self.assertRaisesRegex(ValueError, "coverage"):
            af.backend_market(lambda path: payload, NOW)

    def test_backend_divergence_blocks_candidate_requests(self):
        state = af.initial()
        result = af.cycle(state, CFG, lambda path: self.fail("blocked market must not fetch candidates"),
                          NOW, Calendar, {"backend_status": "强分歧", "risk_score": 65}, False)
        self.assertEqual(result, "market_gate")

    def test_control_queue_is_independent_of_account_writer_and_replay_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "account.db"
            account, control = af.connect(path), af.connect_control(path)
            try:
                account.execute("BEGIN IMMEDIATE")
                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('request-123','pause','{}',?)", (NOW.isoformat(),))
                state = af.initial()
                receipts = af.apply_commands(control, state, NOW)
                self.assertFalse(state["enabled"])
                count = len(state["events"])
                self.assertEqual(af.apply_commands(control, state, NOW), receipts)
                self.assertEqual(len(state["events"]), count)
                # Do not acknowledge until the account state commits.
                self.assertEqual(control.execute("SELECT status FROM commands").fetchone()[0], "pending")
                account.rollback()
            finally:
                account.close(); control.close()

    def test_paused_entry_still_monitors_exits(self):
        state = af.initial();state["enabled"] = False
        state["positions"] = [{"symbol":"600001.SH","buy_date":"2026-10-13","buy_price":12,
                              "shares":100,"buy_vwap":12,"buy_vwap10":12}]
        result = af.cycle(state,CFG,lambda path:{"data":[quote()]},NOW,Calendar,{},False)
        self.assertEqual(result,"paused")
        self.assertEqual(len(state["closed"]),1)

    def test_pending_emergency_stop_prevents_buy_during_scan(self):
        state = af.initial()
        with patch.object(af,"candidates",return_value=[{"symbol":"600001.SH","name":"样本","route":"theme_trend"}]):
            af.cycle(state,CFG,lambda path:{"data":[]},NOW,Calendar,{"score":0},False,should_stop=lambda:True)
        self.assertEqual(state["positions"],[])
        self.assertEqual(state["candidates"][0]["reason"],"pending_stop_command")

    def test_watch_process_applies_and_acknowledges_pause_without_market_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=root/'service';service.mkdir()
            for name in ('daily_review.py','market_cache.py','market_network.py','data_store.py','trading_calendar.py'):
                shutil.copyfile(af.SERVICE/name,service/name)
            config=root/'config.json';config.write_text(json.dumps({**CFG,'version':'v1.9'}),encoding='utf-8')
            env={**os.environ,'EASY_STOCK_FOLLOW_SERVICE_DIR':str(service),'EASY_STOCK_FOLLOW_CONFIG':str(config),
                 'EASY_STOCK_FOLLOW_MARKET_SOURCE':'file','EASY_STOCK_DATA_DB':str(root/'http.db'),
                 'PYTHONDONTWRITEBYTECODE':'1'}
            path=root/'account.db'
            account=af.connect(path);control=af.connect_control(path)
            proc=subprocess.Popen([sys.executable,str(af.ROOT/'auto_follow.py'),'--watch','--db',str(path)],
                                  env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('process-pause','pause','{}',?)",(NOW.isoformat(),))
                deadline=time.monotonic()+12
                applied=False
                while time.monotonic()<deadline and proc.poll() is None:
                    if control.execute("SELECT status FROM commands WHERE id='process-pause'").fetchone()[0]=='applied':
                        applied=True;break
                    time.sleep(.1)
                self.assertTrue(applied,'watch must acknowledge a queued control command')
                state=json.loads(account.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
                self.assertFalse(state['enabled'])
                self.assertEqual(state['positions'],[])
                self.assertTrue(state['last_heartbeat'])
            finally:
                proc.terminate();proc.wait(timeout=5)
                if proc.stderr:proc.stderr.close()
                account.close();control.close()


    def test_symbol_supports_kc_and_cy_boards(self):
        self.assertEqual(af.symbol("688787"), "688787.SH")
        self.assertEqual(af.symbol("688787.SH"), "688787.SH")
        self.assertEqual(af.symbol("sh688787"), "688787.SH")
        self.assertEqual(af.symbol("300059"), "300059.SZ")
        self.assertEqual(af.symbol("300059.SZ"), "300059.SZ")
        self.assertEqual(af.symbol("sz300059"), "300059.SZ")

    def test_manual_symbols_in_candidates(self):
        ladder = {"current": {"trade_date": "2026-10-14"}, "previous": {"trade_date": "2026-10-13", "levels": []},
                  "meta": {"source": "test", "stale": False, "fetched_at": NOW.isoformat()}}
        overview = {"meta": {"source": "test", "stale": False, "fetched_at": NOW.isoformat()}, "data": []}
        settings = {"manual_symbols": ["688787.SH", "000001.SZ"]}
        pool = af.candidates(ladder, overview, NOW, "2026-10-13", settings)
        symbols = [c["symbol"] for c in pool]
        self.assertIn("688787.SH", symbols)
        self.assertIn("000001.SZ", symbols)
        self.assertEqual(pool[0]["route"], "manual")
        self.assertEqual(pool[0]["streak"], 99)

    def test_commands_add_and_remove_manual_symbol(self):
        state = af.initial()
        with tempfile.TemporaryDirectory() as temp_dir:
            control = af.connect_control(Path(temp_dir) / "account.db")
            try:
                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('c1','add_symbol',?,?)",
                                (json.dumps("688787"), NOW.isoformat()))
                af.apply_commands(control, state, NOW)
                self.assertEqual(state["settings"].get("manual_symbols"), ["688787.SH"])

                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('c2','remove_symbol',?,?)",
                                (json.dumps("688787.SH"), NOW.isoformat()))
                af.apply_commands(control, state, NOW)
                self.assertEqual(state["settings"].get("manual_symbols"), [])

                control.execute("INSERT INTO commands(id,action,payload,created_at) VALUES('c3','manual_symbols',?,?)",
                                (json.dumps(["688787", "600001"]), NOW.isoformat()))
                af.apply_commands(control, state, NOW)
                self.assertEqual(state["settings"].get("manual_symbols"), ["688787.SH", "600001.SH"])
            finally:
                control.close()


if __name__ == "__main__":
    unittest.main()

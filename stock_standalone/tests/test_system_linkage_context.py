import json
import hashlib
import hmac
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from threading import Thread
from unittest.mock import patch

from pandas import NA

from system_linkage_context import (
    SystemLinkageContextClient, _require_private_host, build_ats_leader_evidence,
    build_instock_candidate_evidence, build_ipo_linkage_evidence,
    classify_linkage_quote_status,
    publish_ats_leader_evidence, publish_instock_candidate_evidence,
)


class _MemoryFavorites:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.applied = []

    def get_favorite_attention_state(self):
        return deepcopy(self.state)

    def get_persistent_favorite_attention_state(self):
        return self.get_favorite_attention_state()

    def apply_favorite_source_intent(self, code, source, action, operation_id, origin="local", expected_revision=None):
        if expected_revision is not None and expected_revision != self.state["favorites_revision"]:
            raise ValueError("favorites_revision_conflict")
        self.applied.append((code, source, action, operation_id, origin))
        if action == "add":
            self.state["sources"].setdefault(code, {})[source] = {"operation_id": operation_id}
            self.state["stocks"] = sorted(set(self.state["stocks"]) | {code})
        elif action == "remove_source":
            self.state["sources"].setdefault(code, {}).pop(source, None)
            if not self.state["sources"][code]:
                self.state["sources"].pop(code)
                self.state["stocks"] = [value for value in self.state["stocks"] if value != code]
        else:
            self.state["sources"].pop(code, None)
            self.state["stocks"] = [value for value in self.state["stocks"] if value != code]
            self.state["tombstones"][code] = {"operation_id": operation_id}
        self.state["favorites_revision"] += 1
        return {"favorites_revision": self.state["favorites_revision"]}

    def set_attention_sync_revision(self, revision, favorites_revision=None):
        self.state["attention_revision"] = revision
        self.state["attention_favorites_revision"] = (
            self.state["favorites_revision"] if favorites_revision is None else favorites_revision
        )


class _MemoryAttentionClient(SystemLinkageContextClient):
    def __init__(self, manager, snapshot):
        super().__init__(SimpleNamespace(linkage_enabled=True, ipc_workspace_id="desk", ipc_node_id="tk-1"))
        self._workspace_id = "desk"
        self._node_id = "tk-1"
        self._attention_enabled = True
        self._favorite_manager = manager
        self.snapshot = deepcopy(snapshot)
        self.sent = []
        self.batch_sizes = []

    def _get_attention_snapshot(self):
        return deepcopy(self.snapshot)

    def _apply_attention_batch(self, snapshot, intents, baseline_favorites_revision):
        if intents:
            self.batch_sizes.append(len(intents))
        for intent in intents:
            snapshot = self._apply_attention_intent(snapshot, intent)
        return snapshot

    def _apply_attention_intent(self, snapshot, intent):
        self.sent.append(deepcopy(intent))
        self.snapshot["revision"] += 1
        now = {"symbol": intent["symbol"], "source": intent["source"],
               "active": intent["action"] == "add", "revision": self.snapshot["revision"],
               "intent_id": intent["intent_id"]}
        rows = [item for item in self.snapshot["sources"]
                if (item.get("symbol"), item.get("source")) != (now["symbol"], now["source"])]
        if intent["action"] == "remove_all":
            for item in self.snapshot["sources"]:
                if item.get("symbol") == intent["symbol"]:
                    item["active"] = False
                    item["revision"] = self.snapshot["revision"]
                    item["intent_id"] = intent["intent_id"]
            self.snapshot["tombstones"] = [item for item in self.snapshot["tombstones"]
                                            if item.get("symbol") != intent["symbol"]]
            self.snapshot["tombstones"].append({"symbol": intent["symbol"], "revision": self.snapshot["revision"],
                                                "intent_id": intent["intent_id"]})
        else:
            rows.append(now)
            self.snapshot["sources"] = rows
            if intent["action"] == "add":
                self.snapshot["tombstones"] = [item for item in self.snapshot["tombstones"]
                                                if item.get("symbol") != intent["symbol"]]
        return deepcopy(self.snapshot)


class SystemLinkageContextTests(unittest.TestCase):
    def test_quote_status_requires_current_trade_date_and_fresh_frame(self):
        self.assertEqual(
            classify_linkage_quote_status(10, None, "2026-10-10", True, 1), "unknown"
        )
        self.assertEqual(
            classify_linkage_quote_status(10, "2026-10-09", "2026-10-10", True, 1), "stale"
        )
        self.assertEqual(
            classify_linkage_quote_status(10, "20261010", "2026-10-10", True, 16), "stale"
        )
        self.assertEqual(
            classify_linkage_quote_status(10, "2026-10-10T00:00:00Z", "20261010", True, 1), "ready"
        )
        self.assertEqual(
            classify_linkage_quote_status(10, "2026/10/10", "2026-10-10", False, 100),
            "market_closed",
        )
        self.assertEqual(
            classify_linkage_quote_status(None, "2026-10-10", "2026-10-10", True, 1),
            "pending_fetch",
        )

    def test_instock_candidate_builder_handles_pandas_missing_values_and_is_dated(self):
        now = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)
        frame = [{"code": "600000", "name": NA, "grade": "A", "score": 92.5, "category": "储能"}]

        first = build_instock_candidate_evidence(frame, "2026-10-10", now=now)
        second = build_instock_candidate_evidence(frame, "2026-10-10", now=now)
        self.assertEqual(first, second)
        self.assertEqual(first[2]["source_id"], "instock.candidates")
        self.assertEqual(first[2]["source_freshness"], "fresh")
        self.assertEqual(first[2]["candidates"][0]["symbol"], "600000.SH")
        self.assertEqual(first[2]["candidates"][0]["name"], "")
        self.assertEqual(first[2]["candidates"][0]["score"], 92.5)
        self.assertTrue(first[2]["candidate_codes_complete"])
        empty = build_instock_candidate_evidence([], "2026-10-10", now=now)
        self.assertIsNotNone(empty)
        self.assertEqual(empty[2]["candidate_count"], 0)
        self.assertEqual(empty[2]["candidates"], [])
        self.assertTrue(empty[2]["candidate_codes_complete"])

        stale = build_instock_candidate_evidence(frame, "2026-10-10", now=now + timedelta(days=1))
        self.assertEqual(stale[2]["source_freshness"], "stale")
        published = {}
        publisher = SimpleNamespace(publish_source_snapshot=lambda *args: published.update({"args": args}) or "queued")
        self.assertEqual(publish_instock_candidate_evidence(frame, publisher, "2026-10-10", now=now), "queued")
        self.assertEqual(published["args"][0], "instock.candidates")
        self.assertIs(publish_instock_candidate_evidence(frame, None, "2026-10-10", now=now), False)

    def test_ats_leader_builder_is_dated_sampled_stable_and_stale_aware(self):
        source_time = datetime(2026, 10, 10, 1, 30, 7, tzinfo=timezone.utc)
        report = {
            "timestamp": source_time.timestamp(),
            "dragon_records_all": [
                {"code": "600000", "name": "浦发银行", "role": "趋势容量中军", "sector": "银行", "priority": 80},
                {"code": "600000", "name": "浦发银行", "role": "空间高度龙", "sector": "银行", "priority": 95},
                {"code": "000001", "name": "指数", "role": "趋势容量中军", "sector": "综合指数/ETF"},
                {"code": "830001", "name": "北交所", "role": "主线先锋"},
                {"code": "600001", "name": "无角色", "role": ""},
            ],
        }

        first = build_ats_leader_evidence(report, now=source_time + timedelta(seconds=10))
        second = build_ats_leader_evidence(report, now=source_time + timedelta(seconds=20))
        self.assertEqual(first, second)
        trade_date, as_of, payload = first
        self.assertEqual(trade_date, "2026-10-10")
        self.assertEqual(as_of, "2026-10-10T01:30:00+00:00")
        self.assertEqual(payload["source_id"], "ats.leader")
        self.assertEqual(payload["source_freshness"], "fresh")
        self.assertEqual(payload["roles"][0]["role"], "空间高度龙")
        self.assertEqual(payload["roles"][0]["classification"], "ats_role_candidate")
        self.assertEqual(payload["candidate_codes"], ["600000.SH"])
        self.assertTrue(payload["coverage"]["is_sample"])
        self.assertFalse(payload["coverage"]["complete"])

        published = {}
        publisher = SimpleNamespace(publish_source_snapshot=lambda *args: published.update({"args": args}) or "queued")
        self.assertEqual(publish_ats_leader_evidence(report, publisher, now=source_time), "queued")
        self.assertEqual(published["args"][0], "ats.leader")
        self.assertEqual(published["args"][1], trade_date)
        self.assertIs(publish_ats_leader_evidence(report, None, now=source_time), False)

        stale = build_ats_leader_evidence(report, now=source_time + timedelta(minutes=2))
        self.assertEqual(stale[2]["source_freshness"], "stale")
        self.assertIsNone(build_ats_leader_evidence({"timestamp": "invalid"}))

    def test_ipo_evidence_builder_keeps_only_dated_non_watch_observations(self):
        records = [
            {"symbol": "600000", "name": "浦发银行", "signal_type": "BREAKOUT",
             "signal_tier": "A", "horse_race_score": 81.5, "horse_race_rank": 2,
             "source_bar_as_of": "2026-10-10T09:31:00"},
            {"symbol": "600000", "name": "浦发银行", "signal_type": "BREAKOUT",
             "signal_tier": "A", "horse_race_score": 95, "horse_race_rank": 1,
             "source_bar_as_of": "2026-10-10T09:31:00"},
            {"symbol": "000001", "signal_type": "WATCH", "source_bar_as_of": "2026-10-10T09:31:00"},
            {"symbol": "600001", "signal_type": "BREAKOUT", "source_bar_as_of": "invalid"},
        ]

        first = build_ipo_linkage_evidence(records, 25)
        second = build_ipo_linkage_evidence(records, 25)
        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        trade_date, as_of, payload = first
        self.assertEqual(trade_date, "2026-10-10")
        self.assertTrue(as_of.endswith("+00:00"))
        self.assertEqual(payload["source_id"], "ats.ipo")
        self.assertEqual(payload["monitored_count"], 25)
        self.assertEqual(payload["coverage"]["is_sample"], True)
        self.assertEqual(len(payload["signals"]), 1)
        self.assertEqual(payload["signals"][0]["symbol"], "600000.SH")
        self.assertEqual(payload["signals"][0]["horse_race_score"], 81.5)
        self.assertEqual(len(payload["signals"][0]["signal_id"]), 64)

    def test_store_and_summarize_read_only_context(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
            )
            client._init_store()
            now = datetime.now(timezone.utc)
            snapshot = {
                "schema_version": 1,
                "snapshot_id": "context-1",
                "received_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=1)).isoformat(),
                "trade_date": "2026-10-10",
                "freshness": "partial",
                "themes": [{"name": "储能", "members": [{"symbol": "600000.SH"}]}],
                "heat": {"stocks": [{"symbol": "600000.SH", "ranks": {"ths": 7}}]},
                "evidence": [{"source_id": "tk.auction", "trade_date": "2026-10-09",
                              "as_of": "2026-10-09T01:25:00Z", "freshness": "stale",
                              "payload": {"state": "POSITIVE", "candidate_codes": ["600000.SH"]}},
                             {"source_id": "ats.leader", "trade_date": "2026-10-10", "freshness": "fresh",
                              "payload": {"source_freshness": "fresh", "candidate_count": 1,
                                          "roles": [{"symbol": "600000.SH", "role": "空间高度龙", "sector": "储能"}]}},
                             {"source_id": "instock.candidates", "trade_date": "2026-10-10", "freshness": "fresh",
                              "payload": {"source_freshness": "fresh", "candidate_count": 2,
                                          "candidate_codes_complete": False,
                                          "candidate_codes": ["600000.SH"],
                                          "candidates": [{"symbol": "600000.SH", "grade": "A", "score": 92}],
                                          "coverage": {"scope": "configured_selector_output", "complete": False,
                                                       "observed_count": 1, "total_count": 2, "is_sample": True}}}],
                "ladder": {"current": {"levels": [{"label": "3板", "stocks": [
                    {"symbol": "600000.SH", "streak": 3}
                ]}]}},
                "coverage": [],
            }
            client._store_snapshot(snapshot)
            client._snapshot = snapshot
            client._events = [{"event_type": "heat.rank_changed", "payload": {
                "symbol": "600000.SH", "from_rank": 12, "to_rank": 7,
            }}]

            summary = client.summary_for_symbol("600000")
            self.assertEqual(summary["state"], "partial")
            self.assertEqual(summary["themes"], ["储能"])
            self.assertEqual(summary["ranks"], {"ths": 7})
            self.assertEqual(summary["ladder"], {"label": "3板", "streak": 3})
            self.assertEqual(summary["leader"]["role"], "空间高度龙")
            self.assertEqual(summary["leader"]["classification"], "ATS 候选角色")
            self.assertEqual(summary["leader"]["freshness"], "fresh")
            self.assertTrue(summary["instock_candidate"]["candidate"])
            self.assertEqual(summary["instock_candidate"]["classification"], "当前候选")
            self.assertEqual(summary["instock_candidate"]["grade"], "A")
            self.assertEqual(summary["auction"]["freshness"], "stale")
            self.assertTrue(summary["auction"]["candidate"])
            self.assertEqual(summary["event_summary"], "heat.rank_changed 12→7")

    def test_instock_nonmatch_discloses_sample_coverage_and_stale_date(self):
        for complete, expected in ((False, "当前样本未列入"), (True, "当前 selector 未列入")):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as root:
                client = SystemLinkageContextClient(
                    SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
                )
                now = datetime.now(timezone.utc)
                payload = {"source_freshness": "fresh", "candidate_count": 50,
                           "candidate_codes_complete": complete, "candidate_codes": ["600001.SH"],
                           "candidates": [], "coverage": {"scope": "configured_selector_output",
                                                               "complete": complete, "observed_count": 1,
                                                               "total_count": 50, "is_sample": not complete}}
                snapshot = {"schema_version": 1, "snapshot_id": "context", "received_at": now.isoformat(),
                            "expires_at": (now + timedelta(minutes=1)).isoformat(), "trade_date": "2026-10-10",
                            "freshness": "fresh", "themes": [], "heat": {"stocks": []}, "coverage": [],
                            "evidence": [{"source_id": "instock.candidates", "trade_date": "2026-10-10",
                                          "freshness": "fresh", "payload": payload}]}
                client._snapshot = snapshot
                client._status = {"state": "fresh"}
                summary = client.summary_for_symbol("600000")
                self.assertFalse(summary["instock_candidate"]["candidate"])
                self.assertEqual(summary["instock_candidate"]["classification"], expected)
                self.assertEqual(summary["instock_candidate"]["candidate_count"], 50)

                snapshot["evidence"][0]["trade_date"] = "2026-10-09"
                summary = client.summary_for_symbol("600000")
                self.assertEqual(summary["instock_candidate"]["freshness"], "stale")
                self.assertEqual(summary["instock_candidate"]["classification"],
                                 "历史样本未列入" if not complete else "历史 selector 未列入")

    def test_private_host_gate_rejects_public_address(self):
        _require_private_host("10.20.30.40")
        with self.assertRaises(ValueError):
            _require_private_host("8.8.8.8")

    def test_context_client_authenticates_with_persisted_node_hmac_without_global_token(self):
        key = b"h" * 32
        with tempfile.TemporaryDirectory() as root:
            key_path = Path(root) / "system_linkage.key"
            key_path.write_text(key.hex(), encoding="ascii")
            observed = {}

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    timestamp = self.headers.get("X-Linkage-Timestamp", "")
                    nonce = self.headers.get("X-Linkage-Nonce", "")
                    node = self.headers.get("X-Linkage-Node-ID", "")
                    workspace = self.headers.get("X-Linkage-Workspace-ID", "")
                    canonical = "\n".join((self.command, self.path, hashlib.sha256(body).hexdigest(),
                                           timestamp, nonce, node, workspace)).encode("utf-8")
                    expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
                    observed["valid"] = hmac.compare_digest(expected, self.headers.get("X-Linkage-Signature", ""))
                    observed["authorization"] = self.headers.get("Authorization")
                    response = b'{"schema_version":1}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)

                def log_message(self, *_args):
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = SystemLinkageContextClient(SimpleNamespace(
                    linkage_enabled=True,
                    stock_strategy_base_url=f"http://127.0.0.1:{server.server_port}",
                    stock_strategy_token_file="", ipc_key_file="system_linkage.key",
                    conf_ini=str(Path(root) / "global.ini"),
                    ipc_workspace_id="desk", ipc_node_id="tk-1",
                ))
                client._resolve_config()
                status, payload = client._request_json("GET", "/api/v1/linkage/context")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)

        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(observed["valid"])
        self.assertIsNone(observed["authorization"])

    def test_context_snapshot_cache_has_a_fixed_history_limit(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
            )
            client._init_store()
            now = datetime.now(timezone.utc).isoformat()
            for index in range(505):
                client._store_snapshot({"snapshot_id": f"context-{index:04d}", "trade_date": "2026-10-10",
                                        "received_at": now, "value": index})
            with client._connection() as connection:
                count = connection.execute("SELECT COUNT(*) FROM linkage_context_snapshots").fetchone()[0]
                latest = connection.execute("SELECT snapshot_id FROM linkage_context_snapshots ORDER BY stored_at DESC,snapshot_id DESC LIMIT 1").fetchone()[0]

        self.assertEqual(count, 500)
        self.assertEqual(latest, "context-0504")

    def test_source_evidence_outbox_is_idempotent_and_retries_until_persisted(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
            )
            client._init_store()
            client._attention_enabled = True
            client._workspace_id = "desk"
            client._node_id = "tk-1"
            payload = {"schema_version": 1, "source_id": "tk.auction", "state": "NEUTRAL"}

            first = client.publish_source_snapshot("tk.auction", "2026-10-10", "2026-10-10T01:25:00Z", payload)
            replay = client.publish_source_snapshot("tk.auction", "2026-10-10", "2026-10-10T01:25:00Z", payload)
            self.assertEqual(first, replay)
            with client._connection() as connection:
                queued = connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0]
            self.assertEqual(queued, 1)

            client._request_json = lambda *_args, **_kwargs: (201, {"status": "stored"})
            client._flush_source_outbox()
            with client._connection() as connection:
                remaining = connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0]
            self.assertEqual(remaining, 0)

    def test_standalone_publisher_flushes_one_pending_evidence_item(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True, stock_strategy_base_url="http://127.0.0.1:20081",
                                ipc_workspace_id="desk", ipc_node_id="ats-1"),
                database_path=str(Path(root) / "context.sqlite3"),
            )
            with patch.dict("os.environ", {"A_STOCK_TOKEN": "secret"}):
                client.prepare_source_publisher()
                client.publish_source_snapshot("ats.ipo", "2026-10-10", "2026-10-10T01:25:00Z",
                                               {"schema_version": 1, "source_id": "ats.ipo", "signals": []})
                seen = []
                client._request_json = lambda method, path, payload: (seen.append((method, path)) or (201, {"status": "stored"}))

                self.assertTrue(client.flush_pending_source_evidence())
            self.assertEqual(seen, [("POST", "/api/v1/linkage/context/evidence")])

    def test_tk_anomaly_queue_batches_on_background_drain(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
            )
            client._init_store()
            client._attention_enabled = True
            client._workspace_id = "desk"
            client._node_id = "tk-1"
            for index in range(2):
                accepted = client.queue_source_event("tk.anomaly", "2026-10-10",
                    f"2026-10-10T01:2{index}:00+00:00",
                    {"event_id": f"event-{index}", "event_type": "pattern", "symbol": "600000.SH"})
                self.assertTrue(accepted)
            self.assertFalse(client.queue_source_event("tk.anomaly", "2026-10-10",
                "2026-10-10T01:30:00+00:00", {"event_type": "trade", "symbol": "600000.SH"}))

            client._drain_source_events()
            with client._connection() as connection:
                row = connection.execute("SELECT payload FROM linkage_context_outbox").fetchone()
            payload = json.loads(bytes(row["payload"]).decode("utf-8"))
            self.assertEqual(payload["source_id"], "tk.anomaly")
            self.assertEqual([item["event_id"] for item in payload["payload"]["events"]], ["event-0", "event-1"])
            self.assertEqual(client._publisher_status, "queued")

    def test_tk_anomaly_queue_retains_events_when_outbox_write_fails(self):
        with tempfile.TemporaryDirectory() as root:
            client = SystemLinkageContextClient(
                SimpleNamespace(linkage_enabled=True), database_path=str(Path(root) / "context.sqlite3")
            )
            client._init_store()
            client._attention_enabled = True
            client._workspace_id = "desk"
            client._node_id = "tk-1"
            client.queue_source_event("tk.anomaly", "2026-10-10", "2026-10-10T01:20:00+00:00",
                                      {"event_id": "event-1", "event_type": "pattern", "symbol": "600000.SH"})

            publish = client.publish_source_snapshot
            attempts = [0]

            def fail_once(*args, **kwargs):
                attempts[0] += 1
                if attempts[0] == 1:
                    raise OSError("temporary sqlite write failure")
                return publish(*args, **kwargs)

            client.publish_source_snapshot = fail_once
            client._drain_source_events()
            self.assertEqual(len(client._source_event_queue), 1)

            client._drain_source_events()
            self.assertEqual(len(client._source_event_queue), 0)
            with client._connection() as connection:
                queued = connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0]
            self.assertEqual(queued, 1)

    def test_attention_sync_pushes_local_source(self):
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": ["600000"],
                                    "sources": {"600000": {"manual": {"local_revision": 1}}},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 0, "sources": [], "tombstones": []})

        client._sync_attention()

        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0]["action"], "add")
        self.assertEqual(client.snapshot["sources"][0]["source"], "manual")
        self.assertTrue(client.snapshot["sources"][0]["active"])
        self.assertEqual(client.batch_sizes, [1])
        self.assertEqual(manager.state["attention_revision"], 1)

    def test_sbc_attention_source_round_trips_workspace_identifier(self):
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": ["600000"],
                                    "sources": {"600000": {"stock-strategy:sbc": {"local_revision": 1}}},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 0,
            "sources": [], "tombstones": []})

        client._sync_attention()

        self.assertEqual(client.sent[0]["source"], "stock-strategy.sbc")
        self.assertEqual(client.snapshot["sources"][0]["source"], "stock-strategy.sbc")

    def test_workspace_sbc_attention_source_projects_to_local_identifier(self):
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": [], "sources": {},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 1,
            "sources": [{"symbol": "600000.SH", "source": "stock-strategy.sbc", "active": True,
                         "revision": 1, "intent_id": "central-sbc-add"}], "tombstones": []})

        client._sync_attention()

        self.assertIn("stock-strategy:sbc", manager.state["sources"]["600000"])

    def test_attention_sync_batches_local_additions(self):
        sources = {f"{index:06d}": {"stock-strategy:sbc": {"local_revision": 1}}
                   for index in range(100000, 100003)}
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": sorted(sources),
                                    "sources": sources, "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 0,
            "sources": [], "tombstones": []})

        client._sync_attention()

        self.assertEqual(client.batch_sizes, [3])
        self.assertEqual(len(client.sent), 3)
        self.assertEqual(manager.state["attention_favorites_revision"], 1)

    def test_newer_central_tombstone_removes_stale_local_source(self):
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 1,
                                    "attention_favorites_revision": 1, "stocks": ["600000"],
                                    "sources": {"600000": {"manual": {"local_revision": 1}}},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 2, "sources": [],
            "tombstones": [{"symbol": "600000.SH", "revision": 2, "intent_id": "attn-remove"}]})

        client._sync_attention()

        self.assertEqual(client.sent, [])
        self.assertFalse(manager.state["stocks"])
        self.assertEqual(manager.applied[0][2], "remove_all")
        self.assertEqual(manager.applied[0][4], "remote_sync")

    def test_newer_central_tombstone_wins_over_offline_local_add(self):
        manager = _MemoryFavorites({"favorites_revision": 2, "attention_revision": 1,
                                    "attention_favorites_revision": 1, "stocks": ["600000"],
                                    "sources": {"600000": {"manual": {"local_revision": 2}}},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 2, "sources": [],
            "tombstones": [{"symbol": "600000.SH", "revision": 2, "intent_id": "central-remove"}]})

        client._sync_attention()

        self.assertEqual(client.sent, [])
        self.assertFalse(manager.state["stocks"])
        self.assertIn("synced_with_conflicts", client._attention_status)
        self.assertEqual(manager.applied[0][2], "remove_all")

    def test_newer_central_add_wins_over_offline_source_removal(self):
        manager = _MemoryFavorites({"favorites_revision": 2, "attention_revision": 1,
                                    "attention_favorites_revision": 1, "stocks": [], "sources": {},
                                    "tombstones": {}, "source_tombstones": {"600000": {
                                        "manual": {"operation_id": "offline-remove", "local_revision": 2},
                                    }}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 2,
            "sources": [{"symbol": "600000.SH", "source": "manual", "active": True,
                         "revision": 2, "intent_id": "central-add"}], "tombstones": []})

        client._sync_attention()

        self.assertEqual(client.sent, [])
        self.assertEqual(manager.state["sources"]["600000"]["manual"]["operation_id"], "central-add")
        self.assertIn("synced_with_conflicts", client._attention_status)

    def test_stale_local_full_tombstone_does_not_remove_newer_central_add(self):
        manager = _MemoryFavorites({"favorites_revision": 1, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": [], "sources": {},
                                    "tombstones": {"600000": {"operation_id": "old-remove", "local_revision": 1}},
                                    "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 2,
            "sources": [{"symbol": "600000.SH", "source": "manual", "active": True,
                         "revision": 2, "intent_id": "new-add"}], "tombstones": []})

        client._sync_attention()

        self.assertEqual(client.sent, [])
        self.assertEqual(manager.state["sources"]["600000"]["manual"]["operation_id"], "new-add")

    def test_attention_revision_conflict_preserves_local_changes_for_reconcile(self):
        manager = _MemoryFavorites({"favorites_revision": 9, "attention_revision": 2,
                                    "attention_favorites_revision": 2, "stocks": [], "sources": {},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 7,
            "sources": [], "tombstones": []})
        client._request_json = lambda *_args, **_kwargs: (409, {"code": "attention_revision_conflict"})

        with self.assertRaisesRegex(ValueError, "attention_revision_conflict"):
            SystemLinkageContextClient._apply_attention_batch(
                client, client.snapshot, [{"intent_id": "retry-me", "symbol": "600000.SH",
                                           "source": "manual", "action": "add"}], 5,
            )

        self.assertEqual(manager.state["attention_revision"], 2)
        self.assertEqual(manager.state["attention_favorites_revision"], 2)
        manager.state["stocks"] = ["600000"]
        manager.state["sources"] = {"600000": {"manual": {"local_revision": 9}}}
        client.snapshot["tombstones"] = [{"symbol": "600000.SH", "revision": 7, "intent_id": "remote-delete"}]
        client._sync_attention()
        self.assertFalse(manager.state["stocks"])
        self.assertEqual(client.sent, [])
        restarted = _MemoryAttentionClient(manager, client.snapshot)
        restarted._sync_attention()
        self.assertFalse(manager.state["stocks"])
        self.assertEqual(restarted.sent, [])

    def test_attention_sync_applies_central_source_to_desktop(self):
        manager = _MemoryFavorites({"favorites_revision": 0, "attention_revision": 0,
                                    "attention_favorites_revision": 0, "stocks": [], "sources": {},
                                    "tombstones": {}, "source_tombstones": {}})
        client = _MemoryAttentionClient(manager, {"schema_version": 1, "revision": 1,
            "sources": [{"symbol": "600000.SH", "source": "stock-strategy:sbc", "active": True,
                         "revision": 1, "intent_id": "attn-add"}], "tombstones": []})

        client._sync_attention()

        self.assertEqual(manager.state["sources"]["600000"]["stock-strategy:sbc"]["operation_id"], "attn-add")
        self.assertEqual(manager.state["stocks"], ["600000"])
        self.assertEqual(manager.applied[0][4], "remote_sync")


    def test_attention_runs_even_when_context_is_unavailable(self):
        client = _MemoryAttentionClient(_MemoryFavorites({}), {})
        calls = []
        client._drain_source_events = lambda: None
        client._flush_source_outbox = lambda: None
        client._sync_attention = lambda: calls.append("attention")
        client._notify = lambda: None
        client.poll_interval = 0.001
        def fail_context(_path):
            client._stop.set()
            raise OSError("context unavailable")
        client._fetch_json = fail_context
        client._run()
        self.assertEqual(calls, ["attention"])
        self.assertEqual(client.latest()[1]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()

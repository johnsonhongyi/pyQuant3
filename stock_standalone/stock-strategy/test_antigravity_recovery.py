"""Isolated outage recovery; no real backend, model, or trading calls."""
import configparser
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import desktop_antigravity_agent as agent
from desktop_strategy_agent import DesktopPeer, _error_details


def catalog():
    return Mock(engine="agy", models=[], default_model="flash-low", probe=Mock(return_value=True))


class RecoveryTests(unittest.TestCase):
    def test_stop_never_sends_an_unsupported_stopped_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "agent"
            (runtime.parent / "stop.request").touch()
            peer, heartbeat, persist = Mock(), Mock(), Mock()
            agent._run_agent_loop(peer, catalog(), runtime, Mock(), heartbeat, persist)
            peer.post.assert_not_called()
            heartbeat.assert_not_called()
            persist.assert_called_once_with("stopped", {"reason": "stop_request"})

    def test_502_disconnect_and_400_recover_without_secondary_heartbeat(self):
        failures = [HTTPError("http://localhost", 502, "Bad Gateway", {}, io.BytesIO()),
                    http.client.RemoteDisconnected("closed"),
                    HTTPError("http://localhost", 400, "Bad Request", {}, io.BytesIO())]
        for error in failures:
            error.peer_operation = "heartbeat"
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "agent"
            heartbeat = Mock(side_effect=[*failures, None])
            persist, peer = Mock(), Mock()
            def next_job(*args, **kwargs):
                (runtime.parent / "stop.request").touch()
                return {"job": None}
            peer.post.side_effect = next_job
            with patch.object(agent, "_wait_for_stop", return_value=False) as wait, patch.object(agent, "_emit_log"):
                agent._run_agent_loop(peer, catalog(), runtime, Mock(), heartbeat, persist)
            self.assertEqual([call.args[0] for call in heartbeat.call_args_list], ["ready"] * 4)
            self.assertEqual([call.args[1] for call in wait.call_args_list[:3]], [10, 20, 40])
            degraded = [call.args[1] for call in persist.call_args_list if call.args[0] == "degraded"]
            self.assertEqual(len(degraded), 3)
            self.assertEqual(degraded[0]["stage"], "backend_ready_heartbeat")
            self.assertEqual(degraded[0]["error_detail"]["http_status"], 502)
            self.assertEqual(degraded[1]["error_detail"]["type"], "RemoteDisconnected")
            self.assertEqual(persist.call_args.args[0], "stopped")

    def test_claim_failure_keeps_original_error_and_does_not_report_to_failed_peer(self):
        peer, heartbeat, persist = Mock(), Mock(), Mock()
        error = HTTPError("http://localhost", 502, "Bad Gateway", {}, io.BytesIO())
        error.peer_operation = "next"
        peer.post.side_effect = error
        with patch.object(agent, "_emit_log"):
            agent._run_agent_loop(peer, catalog(), Path("agent"), Mock(), heartbeat, persist, once=True)
        heartbeat.assert_called_once()
        self.assertEqual(persist.call_args.args[1]["stage"], "unified_job_wait")
        self.assertEqual(persist.call_args.args[1]["error_code"], "next_http_502")

    def test_legacy_queue_fallback_only_on_missing_endpoint(self):
        for status in (404, 405):
            peer = Mock()
            peer.post.side_effect = [HTTPError("http://localhost", status, "unsupported", {}, io.BytesIO()), {"job": None}, {"job": None}]
            agent._run_agent_loop(peer, catalog(), Path("agent"), Mock(), Mock(), Mock(), once=True)
            self.assertEqual([call.args[0] for call in peer.post.call_args_list], ["next", "chat_claim", "claim"])

    def test_backoff_is_interruptible_without_sleep(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "agent"
            (runtime.parent / "stop.request").touch()
            with patch.object(agent.time, "sleep") as sleep:
                self.assertTrue(agent._wait_for_stop(runtime, 60))
                sleep.assert_not_called()


@contextmanager
def backend(folder, first_status=400):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        attempts = 0
        connections = []
        def log_message(self, *args):
            pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            type(self).attempts += 1
            self.connections.append(self.client_address)
            status = first_status if self.attempts == 1 else 200
            if status is None:
                self.close_connection = True
                return
            body = json.dumps({"error": "invalid desktop status"} if status == 400 else {"status": "stored"}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    key = folder / "peer.key"
    key.write_bytes(b"x" * 32)
    config = configparser.ConfigParser()
    config["general"] = {"stock_strategy_base_url": f"http://127.0.0.1:{server.server_port}",
                         "ipc_node_id": "agv-test", "ipc_workspace_id": "ws-test", "ipc_key_file": str(key)}
    path = folder / "bridge.ini"
    with path.open("w", encoding="utf-8") as stream:
        config.write(stream)
    try:
        yield path, Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


class PeerRecoveryTests(unittest.TestCase):
    def test_gateway_error_and_abrupt_disconnect_both_discard_socket_then_reconnect(self):
        for first_status in (502, None):
            with self.subTest(first_status=first_status), tempfile.TemporaryDirectory() as folder, \
                 backend(Path(folder), first_status) as (config, handler):
                peer = DesktopPeer(config)
                with self.assertRaises(OSError) as error:
                    peer.post("heartbeat", {"status": "ready"})
                self.assertEqual(error.exception.peer_operation, "heartbeat")
                self.assertIsNone(peer.connections.http)
                self.assertEqual(peer.post("heartbeat", {"status": "ready"})["status"], "stored")
                peer.connections.http.close()

    def test_http_error_preserves_safe_reason_discards_socket_and_reconnects(self):
        with tempfile.TemporaryDirectory() as folder, backend(Path(folder)) as (config, handler):
            peer = DesktopPeer(config)
            with self.assertRaises(HTTPError) as error:
                peer.post("heartbeat", {"status": "stopped"})
            self.assertEqual(_error_details(error.exception)["server_message"], "invalid desktop status")
            self.assertIsNone(peer.connections.http)
            self.assertEqual(peer.post("heartbeat", {"status": "ready"})["status"], "stored")
            self.assertNotEqual(handler.connections[0], handler.connections[1])
            peer.connections.http.close()


if __name__ == "__main__":
    unittest.main()

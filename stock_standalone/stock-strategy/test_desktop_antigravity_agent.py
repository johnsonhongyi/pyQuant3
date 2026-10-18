import json
import io
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import desktop_antigravity_agent as agent
from desktop_bridge_runtime import ProgressPublisher


class AntigravityChatTests(unittest.TestCase):
    def test_stream_json_chat_uses_codex_progress_contract_and_requested_effort(self):
        publisher_instances = []
        posted = []

        class Publisher:
            def __init__(self, peer, job, heartbeat):
                self.payloads = []
                self.closed = False
                publisher_instances.append(self)

            def publish(self, result):
                self.payloads.append(result)

            def close(self):
                self.closed = True

        def fake_run(command, **kwargs):
            self.assertIn("--effort", command)
            self.assertEqual(command[command.index("--effort") + 1], "high")
            prompt = json.loads(kwargs["stdin_bytes"].decode("utf-8"))
            self.assertEqual(prompt["event"], "user")
            self.assertTrue(kwargs["timeout_seconds"] <= 180)
            stream = kwargs["stdout_callback"]
            conversation_id = "c3b66b04-872b-4fbe-a3a4-058a026ef20a"
            stream(json.dumps({"event": "init", "conversation_id": conversation_id}).encode() + b"\n")
            stream(b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"hello "}}\n')
            stream(b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"world"}}\n')
            stream(json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "hello world",
                                                                   "conversation_id": conversation_id}}).encode() + b"\n")
            return SimpleNamespace(returncode=0, stdout=b"", completed_by_predicate=True)

        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as ledger:
            with patch.object(agent, "ProgressPublisher", Publisher), \
                 patch.object(agent, "run_bounded_cli", side_effect=fake_run), \
                 patch.object(agent, "_post_chat_result", side_effect=lambda peer, payload: posted.append(payload)), \
                 patch.object(agent, "_emit_log"):
                agent.run_antigravity_chat(
                    Mock(),
                    {"id": "job-123", "lease_token": "lease", "remaining_seconds": 90,
                     "context": {"prompt": "offline test prompt", "model": "gemini-3.8-pro", "reasoning_effort": "high"}},
                    "agy", Path(directory),
                    [{"id": "gemini-3.8-pro", "efforts": ["low", "medium", "high", "max"], "default_effort": "medium"}],
                    ledger, Mock(),
                )

        self.assertTrue(publisher_instances[0].closed)
        self.assertTrue(any(item.get("content") == "hello world" for item in publisher_instances[0].payloads))
        self.assertEqual(posted[0]["status"], "completed")
        self.assertEqual(posted[0]["lease_token"], "lease")
        self.assertEqual(posted[0]["result"]["content"], "hello world")
        self.assertEqual(posted[0]["result"]["thread_id"], "c3b66b04-872b-4fbe-a3a4-058a026ef20a")
        self.assertEqual(posted[0]["result"]["reasoning_effort"], "high")
        self.assertTrue(all(item.get("thread_id", "") in ("", "c3b66b04-872b-4fbe-a3a4-058a026ef20a") for item in publisher_instances[0].payloads))
        self.assertEqual(ledger.execute("SELECT result FROM chat_results WHERE id='job-123'").fetchone() is not None, True)

    def test_stream_parser_ignores_malformed_and_non_object_events(self):
        publisher = Mock()
        stream = agent._AntigravityChatStream(publisher, "job", "gemini-3.8-flash", "low")
        stream.feed(b"not-json\n[]\n")
        stream.feed(b'{"event":"init","conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a"}\n')
        stream.feed(b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"ok"}}\n')
        stream.feed(b'{"event":"result","result":{"status":"SUCCESS","response":"ok","conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a"}}')
        stream.finish()
        self.assertEqual("".join(stream.content), "ok")
        self.assertEqual(stream.result_event["status"], "SUCCESS")
        self.assertEqual(stream.thread_id, "c3b66b04-872b-4fbe-a3a4-058a026ef20a")

    def test_progress_publisher_uses_only_valid_agy_conversation_ids(self):
        sent = []

        class Peer:
            def post(self, operation, payload, timeout=8):
                result = payload.get("result", {})
                thread_id = result.get("thread_id")
                if thread_id:
                    uuid.UUID(thread_id)
                sent.append((operation, result))
                return {"status": "stored"}

        job = {"id": "job", "lease_token": "lease"}
        publisher = ProgressPublisher(Peer(), job, Mock())
        try:
            publisher.publish({"content": "start", "model": "gemini-3.8-pro",
                "reasoning_effort": "high", "stage": "model_start"})
            stream = agent._AntigravityChatStream(publisher, "job", "gemini-3.8-pro", "high")
            stream.feed(b'{"event":"init","conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a"}\n')
            stream.feed(b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"ok"}}\n')
            stream.feed(b'{"event":"result","result":{"status":"SUCCESS","response":"ok","conversation_id":"c3b66b04-872b-4fbe-a3a4-058a026ef20a"}}\n')
            deadline = agent.time.monotonic() + 1
            while agent.time.monotonic() < deadline and not any(item[1].get("thread_id") for item in sent):
                agent.time.sleep(0.01)
        finally:
            publisher.close()
        self.assertTrue(sent)
        self.assertTrue(all(operation == "chat_result" for operation, _ in sent))
        self.assertTrue(all(not result.get("thread_id") or result["thread_id"] == stream.thread_id for _, result in sent))

    def test_callback_failure_preserves_the_peer_rejection_reason(self):
        cause = HTTPError("http://127.0.0.1/api", 400, "Bad Request", {}, io.BytesIO(b""))
        cause.peer_code = "CHAT_INVALID_THREAD"
        try:
            raise agent.BoundedCLIError("CLI_OUTPUT_CALLBACK_FAILED") from cause
        except agent.BoundedCLIError as error:
            code, detail = agent._chat_error_info(error)
        self.assertEqual(code, "CHAT_INVALID_THREAD")
        self.assertEqual(detail["http_status"], 400)
        self.assertEqual(detail["callback_error_code"], "CLI_OUTPUT_CALLBACK_FAILED")


if __name__ == "__main__":
    unittest.main()

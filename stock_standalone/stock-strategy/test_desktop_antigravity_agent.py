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
    def test_eligibility_transport_retry_is_bounded_and_never_repeats_output(self):
        import time
        failure = {"status": "ERROR", "error": "Eligibility check failed: failed to get profile picture: EOF"}
        success = {"status": "SUCCESS", "response": "ok"}
        cases = [(failure, False, 2), (failure, True, 1),
                 ({"status":"ERROR", "error":"Eligibility check failed: User location is not supported: EOF"}, False, 1),
                 ({"status": "ERROR", "error": "invalid model selection"}, False, 1),
                 (success, False, 1)]
        for first, partial, expected_calls in cases:
            with self.subTest(first=first, partial=partial), tempfile.TemporaryDirectory() as directory:
                calls = []
                def run(command, **kwargs):
                    calls.append(kwargs["timeout_seconds"])
                    if partial:
                        kwargs["stdout_callback"](b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"partial"}}\n')
                    event = first if len(calls) == 1 else success
                    kwargs["stdout_callback"]((json.dumps({"event": "result", "result": event}) + "\n").encode())
                    return SimpleNamespace(returncode=0)
                with patch.object(agent, "run_bounded_cli", side_effect=run), \
                     patch.object(agent, "_wait_for_stop"), patch.object(agent, "_emit_log"):
                    _, stream = agent._run_agy_stream(
                        ["agy", "--print-timeout", "87s"], prompt_event="prompt", timeout=90,
                        started=time.monotonic(), runtime=Path(directory) / "agent", publisher=None,
                        job_id="job", model="claude", effort="auto", prefix="agv-test-")
                self.assertEqual(len(calls), expected_calls)
                self.assertTrue(all(0 < value <= 90 for value in calls))
                if expected_calls == 2:
                    self.assertLessEqual(calls[1], calls[0])
                    self.assertEqual(stream.result_event["status"], "SUCCESS")

    def test_repeated_eligibility_failure_stops_after_two_attempts(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            def run(command, **kwargs):
                kwargs["stdout_callback"](b'{"event":"result","result":{"status":"ERROR","error":"Eligibility check failed: profile picture: EOF"}}\n')
                return SimpleNamespace(returncode=0)
            with patch.object(agent, "run_bounded_cli", side_effect=run) as runner, \
                 patch.object(agent, "_wait_for_stop"), patch.object(agent, "_emit_log"):
                _, stream = agent._run_agy_stream(
                    ["agy", "--print-timeout", "87s"], prompt_event="prompt", timeout=90,
                    started=time.monotonic(), runtime=Path(directory) / "agent", publisher=None,
                    job_id="job", model="claude", effort="auto", prefix="agv-test-")
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(agent._agy_result_failure(stream.result_event).code, "AGY_ELIGIBILITY_NETWORK_ERROR")

    def test_eligibility_retry_respects_stop_and_remaining_budget(self):
        import time
        for stopped, age in [(True, 0), (False, 80)]:
            with self.subTest(stopped=stopped), tempfile.TemporaryDirectory() as directory:
                if stopped:
                    (Path(directory) / "stop.request").touch()
                def run(command, **kwargs):
                    kwargs["stdout_callback"](b'{"event":"result","result":{"status":"ERROR","error":"Eligibility check failed: profile picture: EOF"}}\n')
                    return SimpleNamespace(returncode=0)
                with patch.object(agent, "run_bounded_cli", side_effect=run) as runner, \
                     patch.object(agent, "_wait_for_stop") as wait:
                    agent._run_agy_stream(
                        ["agy", "--print-timeout", "87s"], prompt_event="prompt", timeout=90,
                        started=time.monotonic() - age, runtime=Path(directory) / "agent", publisher=None,
                        job_id="job", model="claude", effort="auto", prefix="agv-test-")
                self.assertEqual(runner.call_count, 1)
                wait.assert_not_called()

    def test_location_denial_has_dedicated_error_code(self):
        error = agent._agy_result_failure({"status":"ERROR", "error":"FAILED_PRECONDITION (code 400): User location is not supported for the API use."})
        self.assertEqual(error.code,"AGY_LOCATION_UNSUPPORTED")
        self.assertIn("location",agent._chat_error_info(error)[1]["message"])

    def test_upstream_result_error_retains_reason_without_credentials(self):
        error = agent._agy_result_failure({"status": "ERROR", "error": {
            "message": 'invalid model selection: effort unsupported; access_token=secret user@example.com "api_key":"private-key" Bearer bearer-secret'}})
        code, details = agent._chat_error_info(error)
        self.assertEqual(code, "AGY_MODEL_SELECTION_UNVERIFIED")
        self.assertIn("原因未确认", details["message"])
        self.assertIn("effort unsupported", details['upstream_message'])
        self.assertFalse(details['configuration_verified'])
        for secret in ('secret', 'user@example.com', 'private-key', 'bearer-secret'):
            self.assertNotIn(secret, json.dumps(details))

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
            self.assertTrue(kwargs["hidden_console"])
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
                                                                   "usage": {"input_tokens": 14429, "cache_read_tokens": 1000, "output_tokens": 123, "thinking_tokens": 917, "total_tokens": 14552},
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
        result = posted[0]["result"]
        self.assertEqual(result["token_usage"]["inputTokens"], 14429)
        self.assertEqual(result["token_usage"]["cachedInputTokens"], 1000)
        self.assertEqual(result["token_usage"]["reasoningOutputTokens"], 917)
        self.assertLessEqual(result["timings"]["turn_started_ms"], result["timings"]["first_token_ms"])
        self.assertLessEqual(result["timings"]["first_token_ms"], result["timings"]["bridge_to_completed_ms"])
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
        self.assertEqual(stream.token_usage, {})

    def test_dynamic_catalog_filters_unavailable_and_gpt_oss_and_caches_probe(self):
        output = (b"gemini-3.8-flash-high\tGemini 3.8 Flash (High)\n"
                  b"gemini-3.8-flash-low\tGemini 3.8 Flash (Low)\n"
                  b"claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n"
                  b"gpt-oss-120b-medium\tGPT-OSS 120B (Medium)\n"
                  b"gemini-4-argon\tGemini 4 Argon Unavailable\n")
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "agy.exe"
            cli.touch()
            with patch.object(agent, "run_bounded_cli", return_value=SimpleNamespace(stdout=output, returncode=0)) as run:
                catalog = agent.AntigravityCatalog(str(cli))
                self.assertTrue(catalog.probe())
                self.assertEqual(run.call_count, 1)
                self.assertTrue(run.call_args.kwargs["hidden_console"])
                self.assertEqual(catalog.default_model, "gemini-3.8-flash-low")
                self.assertEqual(len(catalog.models), 3)
                self.assertEqual(catalog.models[0]["efforts"], ["high"])
                self.assertEqual(catalog.models[2]["efforts"], ["auto"])
                self.assertEqual(catalog.models[2]["default_effort"], "auto")
                catalog.fetched_at -= 301
                self.assertTrue(catalog.probe())
                self.assertEqual(run.call_count, 2)

    def test_catalog_failure_clears_availability_and_backs_off(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "agy.exe"
            cli.touch()
            with patch.object(agent, "run_bounded_cli", side_effect=agent.BoundedCLIError("CLI_TIMEOUT")) as run:
                catalog = agent.AntigravityCatalog(str(cli))
                self.assertFalse(catalog.probe())
                self.assertEqual(run.call_count, 1)
                self.assertFalse(catalog.status()["models_available"])
                self.assertEqual(catalog.models, [])

    def test_model_and_effort_selection_adapts_to_catalog(self):
        models = agent._parse_model_catalog("gemini-3.8-flash-low\tGemini Flash (Low)\n")
        with self.assertRaisesRegex(agent.BoundedCLIError, "MODEL_UNAVAILABLE"):
            agent._select_model({"model": "removed-model"}, models, "")
        with self.assertRaisesRegex(agent.BoundedCLIError, "EFFORT_UNSUPPORTED"):
            agent._resolve_cli_effort(models[0]["id"], "high", models)
        fixed = agent._parse_model_catalog("claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n")[0]
        with self.assertRaisesRegex(agent.BoundedCLIError, "EFFORT_UNSUPPORTED"):
            agent._resolve_cli_effort(fixed["id"], "high", [fixed])
        self.assertEqual(agent._resolve_cli_effort(fixed["id"], "auto", [fixed]), "auto")

    def test_fixed_model_omits_effort_flag_and_uses_model_default(self):
        posted = []

        def fake_run(command, **kwargs):
            self.assertNotIn("--effort", command)
            self.assertEqual(command[command.index("--model") + 1], "claude-sonnet-4-6")
            stream = kwargs["stdout_callback"]
            conversation_id = "c3b66b04-872b-4fbe-a3a4-058a026ef20a"
            stream(json.dumps({"event": "init", "init": {"model": "claude-sonnet-4-6"},
                               "conversation_id": conversation_id}).encode() + b"\n")
            stream(json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "ok",
                               "conversation_id": conversation_id}}).encode() + b"\n")
            return SimpleNamespace(returncode=0, stdout=b"", completed_by_predicate=True)

        fixed = agent._parse_model_catalog("claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n")
        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as ledger:
            with patch.object(agent, "ProgressPublisher"), patch.object(agent, "run_bounded_cli", side_effect=fake_run), \
                 patch.object(agent, "_post_chat_result", side_effect=lambda peer, payload: posted.append(payload)), \
                 patch.object(agent, "_emit_log"):
                agent.run_antigravity_chat(Mock(), {"id": "fixed-model", "lease_token": "lease",
                    "remaining_seconds": 90, "context": {"prompt": "test", "model": "claude-sonnet-4-6",
                    "reasoning_effort": "auto"}}, "agy", Path(directory), fixed, ledger, Mock())
        self.assertEqual(posted[0]["result"]["reasoning_effort"], "auto")

    def test_failed_receipt_is_durable_and_replayed_without_inference(self):
        job = {"id": "receipt", "lease_token": "lease", "context": {
            "prompt": "probe", "bridge_test": True, "model": "flash-low"}}
        models = [{"id": "flash-low", "efforts": ["low"], "default_effort": "low"}]
        def infer(command, **kwargs):
            event = {'event': 'result', 'result': {'status': 'SUCCESS',
                'response': 'ANTIGRAVITY_BRIDGE_OK',
                'conversation_id': 'c3b66b04-872b-4fbe-a3a4-058a026ef20a'}}
            kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
            return SimpleNamespace(returncode=0, stdout=b'', completed_by_predicate=True)
        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as ledger:
            with patch.object(agent, "ProgressPublisher"), patch.object(agent, "_emit_log"), \
                 patch.object(agent, "run_bounded_cli", side_effect=infer) as run, \
                 patch.object(agent, "_post_chat_result", side_effect=OSError("offline")) as post:
                with self.assertRaises(OSError):
                    agent.run_antigravity_chat(Mock(), job, "agy", Path(directory), models, ledger, Mock())
                self.assertEqual(post.call_count, 1)
                self.assertEqual(post.call_args.args[1]["status"], "completed")
                self.assertIsNone(ledger.execute("SELECT delivered_at FROM result_outbox").fetchone()[0])
                post.side_effect = None
                agent.run_antigravity_chat(Mock(), job, "agy", Path(directory), models, ledger, Mock())
                self.assertIsNotNone(ledger.execute("SELECT delivered_at FROM result_outbox").fetchone()[0])
                self.assertEqual(run.call_count, 1)

    def test_strategy_preserves_usage_and_replays_validated_result(self):
        proposal = {"market_view": "missing evidence", "rotation_view": "unknown", "answer": "observe", "plans": []}
        job = {"id": "strategy", "lease_token": "lease", "context": {
            "model": "claude-sonnet-4-6", "reasoning_effort": "auto", "stocks": []}}
        job['evidence_hash'] = agent.digest(job['context'])
        models = agent._parse_model_catalog("claude-sonnet-4-6\tClaude Sonnet 4.6 (Thinking)\n")
        peer = Mock()

        def run(command, **kwargs):
            self.assertNotIn("--effort", command)
            event = {"event": "result", "result": {"status": "SUCCESS", "response": json.dumps(proposal),
                "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}}}
            kwargs["stdout_callback"](json.dumps(event).encode() + b"\n")
            return SimpleNamespace(returncode=0, stdout=b"")

        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as ledger:
            with patch.object(agent, "ProgressPublisher"), patch.object(agent, "_emit_log"), \
                 patch.object(agent, "ats_evidence", return_value={}), \
                 patch.object(agent, "DesktopRuntimeProbe") as probe, \
                 patch.object(agent, "run_bounded_cli", side_effect=run) as runner:
                probe.return_value.snapshot.return_value = {}
                peer.desktop_runtime_probe = probe.return_value
                for _ in range(2):
                    agent.run_antigravity_strategy(peer, job, "agy", Path(directory), models, ledger, Mock())
                self.assertEqual(runner.call_count, 1)
                saved = json.loads(ledger.execute("SELECT result FROM results").fetchone()[0])
                self.assertEqual(saved["proposal"], proposal)
                self.assertEqual(saved["token_usage"]["inputTokens"], 100)

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

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.agent_hub import AgentHub
from tools.agent_orchestrator import AgentOrchestrator


def _report(summary: str = "done") -> str:
    return json.dumps({
        "task_id": "001",
        "status": "SUCCESS",
        "diff_files": ["ats/example.py"],
        "test_result": {
            "lint": "not_applicable",
            "typecheck": "not_applicable",
            "unit_tests": "pass",
            "failed_cases": [],
        },
        "risk_points": [],
        "summary": summary,
    })


def _project(tmp_path: Path) -> Path:
    hub = tmp_path / ".agent_hub"
    for name in ("inbox", "running", "done", "review", "archive", "events", "dashboard", "artifacts"):
        (hub / name).mkdir(parents=True)
    (hub / "policy.json").write_text(json.dumps({
        "max_running_tasks": 1,
        "required_sections": [
            "Task", "Metadata", "Context", "Files Allowed", "Files Forbidden",
            "Requirements", "Definition of Done", "Verification", "Rollback", "Output Contract"
        ],
    }), encoding="utf-8")
    (hub / "orchestrator.json").write_text(json.dumps({
        "antigravity_executable": __file__,
        "codex_executable": __file__,
        "allowed_verification_prefixes": ["python -m pytest"],
        "scope_ignore_prefixes": [".agent_hub/"],
    }), encoding="utf-8")
    (hub / "AGENT_PROMPT.md").write_text("worker rules", encoding="utf-8")
    (hub / "review_prompt.md").write_text("review rules", encoding="utf-8")
    sections = [
        "# Task\n\nPreview task",
        "## Metadata\n\n- Task-ID: 001",
        "## Context\n\ncontext",
        "## Files Allowed\n\n- `ats/example.py`",
        "## Files Forbidden\n\n- `trade_gateway.py`",
        "## Requirements\n\n- requirement",
        "## Definition of Done\n\n- [ ] done",
        "## Verification\n\n```powershell\npython -m pytest tests/test_example.py -q\n```",
        "## Rollback\n\nrollback",
        "## Output Contract\n\noutput",
    ]
    (hub / "inbox" / "001_preview.md").write_text("\n\n".join(sections), encoding="utf-8")
    return tmp_path


def test_runner_uses_project_local_temp_directory(tmp_path: Path) -> None:
    root = _project(tmp_path)
    captured = {}

    def runner(args, **kwargs):
        captured.update(kwargs["env"])
        return subprocess.CompletedProcess(args, 0, "", "")

    AgentOrchestrator(root, runner=runner)._run(["fake-command"])
    assert captured["TEMP"] == str(root / ".pytest_temp" / "agent_hub_runtime")
    assert captured["TMP"] == captured["TEMP"]


def test_preview_does_not_claim_task(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    report = orchestrator.preview()
    assert report.status == "DRY_RUN"
    assert report.task_id == "001"
    assert (root / ".agent_hub" / "inbox" / "001_preview.md").exists()
    assert not list((root / ".agent_hub" / "running").glob("*.md"))


def test_verification_rejects_unapproved_command(tmp_path: Path) -> None:
    root = _project(tmp_path)
    task = root / ".agent_hub" / "inbox" / "001_preview.md"
    task.write_text(task.read_text(encoding="utf-8").replace(
        "python -m pytest tests/test_example.py -q", "powershell Remove-Item important"
    ), encoding="utf-8")
    orchestrator = AgentOrchestrator(root)
    try:
        orchestrator.preview()
    except Exception as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("unsafe verification command was accepted")


def test_scope_violation_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    task_text = (root / ".agent_hub" / "inbox" / "001_preview.md").read_text(encoding="utf-8")
    violations = orchestrator._scope_violations(
        task_text, {"ats/example.py", "trade_gateway.py", ".agent_hub/artifacts/001/log.txt"}
    )
    assert violations == ["trade_gateway.py"]


def test_write_is_python_39_compatible(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "output.txt"
    AgentOrchestrator._write(target, "line 1\nline 2\n")
    assert target.read_text(encoding="utf-8") == "line 1\nline 2\n"


def test_worker_retries_once_after_transient_auth_failure(tmp_path: Path) -> None:
    root = _project(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args, 1, "", "You are not logged into Antigravity. authentication timed out."
            )
        return subprocess.CompletedProcess(args, 0, _report(), "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    artifact_dir = root / ".agent_hub" / "artifacts" / "001"
    result = orchestrator._invoke_worker("test", artifact_dir, "LOW")
    assert result.returncode == 0
    assert len(calls) == 2
    assert (artifact_dir / "worker_attempt_1_gemini-test_auth_retry.stdout").exists()


def test_worker_does_not_retry_proxy_eligibility_error(tmp_path: Path) -> None:
    root = _project(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 1, "", "Eligibility check failed: EOF")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    result = orchestrator._invoke_worker("test", root / ".agent_hub" / "artifacts" / "001", "LOW")
    assert result.returncode == 1
    assert len(calls) == 1


def test_readonly_profile_uses_plan_mode_without_auto_approval(tmp_path: Path) -> None:
    root = _project(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, _report(), "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": True,
    })
    orchestrator._invoke_worker(
        "audit", root / ".agent_hub" / "artifacts" / "001", "LOW", "P0_READONLY"
    )
    assert calls[0][calls[0].index("--mode") + 1] == "plan"
    assert "--dangerously-skip-permissions" not in calls[0]


def test_worker_enforces_json_schema_and_compacts_output(tmp_path: Path) -> None:
    root = _project(tmp_path)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, _report("完成"), "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    result = orchestrator._invoke_worker(
        "test", root / ".agent_hub" / "artifacts" / "001", "LOW"
    )
    assert result.returncode == 0
    assert "\n" not in result.stdout
    assert json.loads(result.stdout)["summary"] == "完成"


def test_worker_prompt_has_a_bounded_file_read_allowlist(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / ".agent_hub" / "AGENT_PROMPT.md").write_text(
        "conflicting legacy rule: submit the task", encoding="utf-8"
    )
    orchestrator = AgentOrchestrator(root)
    prompt = orchestrator._worker_prompt(root / ".agent_hub" / "inbox" / "001_preview.md")
    assert "AUTHORITATIVE INVOCATION RULES" in prompt
    assert "read/search budget is 12 tool calls total" in prompt
    assert 'READ ALLOWLIST: ["ats/example.py"]' in prompt
    assert "conflicting legacy rule" not in prompt


def test_worker_prompt_includes_authoritative_rework_findings(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / ".agent_hub" / "review").mkdir(exist_ok=True)
    (root / ".agent_hub" / "review" / "001_review.md").write_text(
        "# Review 001\n\n- Decision: REWORK\n\n## Findings\n- fix threshold boundary",
        encoding="utf-8",
    )
    prompt = AgentOrchestrator(root)._worker_prompt(root / ".agent_hub" / "inbox" / "001_preview.md")
    assert "SCOPED REWORK EVIDENCE (authoritative)" in prompt
    assert "fix threshold boundary" in prompt


def test_worker_discards_antigravity_json_envelope(tmp_path: Path) -> None:
    root = _project(tmp_path)
    envelope = json.dumps({
        "conversation_id": "do-not-forward",
        "response": "duplicated verbose response",
        "usage": {"input_tokens": 20000, "output_tokens": 100},
        "json_schema": {"echoed": True},
        "structured_output": json.loads(_report("精简完成")),
    })

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, envelope, "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    result = orchestrator._invoke_worker(
        "test", root / ".agent_hub" / "artifacts" / "001", "LOW"
    )
    compact = json.loads(result.stdout)
    assert compact["summary"] == "精简完成"
    assert "conversation_id" not in compact
    assert "usage" not in compact


def test_worker_accepts_valid_structured_output_from_verbose_transport_error(tmp_path: Path) -> None:
    root = _project(tmp_path)
    envelope = json.dumps({
        "status": "ERROR",
        "error": "x" * 5000,
        "structured_output": json.loads(_report("传输收尾失败但结果有效")),
    })

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, envelope, "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    result = orchestrator._invoke_worker(
        "test", root / ".agent_hub" / "artifacts" / "001", "LOW"
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"] == "传输收尾失败但结果有效"


def test_worker_rejects_verbose_or_non_contract_output(tmp_path: Path) -> None:
    root = _project(tmp_path)

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "analysis first\n" + _report(), "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({
        "worker_model": "gemini-test",
        "worker_fallback_models": [],
        "worker_timeout_seconds": 5,
        "worker_auto_approve_permissions": False,
    })
    result = orchestrator._invoke_worker(
        "test", root / ".agent_hub" / "artifacts" / "001", "LOW"
    )
    assert result.returncode == 2
    assert "Compact report rejected" in result.stderr


def test_release_gate_allows_high_risk_readonly_review(tmp_path: Path) -> None:
    root = _project(tmp_path)
    task = root / ".agent_hub" / "inbox" / "001_preview.md"
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "- Task-ID: 001",
            "- Task-ID: 001\n- Risk: HIGH\n- Permission-Profile: P4_RELEASE_GATE",
        ),
        encoding="utf-8",
    )
    report = AgentOrchestrator(root).preview()
    assert report.status == "DRY_RUN"


def test_forbidden_profile_is_rejected_before_claim(tmp_path: Path) -> None:
    root = _project(tmp_path)
    task = root / ".agent_hub" / "inbox" / "001_preview.md"
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "- Task-ID: 001", "- Task-ID: 001\n- Permission-Profile: P5_FORBIDDEN"
        ),
        encoding="utf-8",
    )
    orchestrator = AgentOrchestrator(root)
    with pytest.raises(Exception, match="cannot be automated"):
        orchestrator.preview()
    assert task.exists()


def test_docs_profile_rejects_business_config(tmp_path: Path) -> None:
    root = _project(tmp_path)
    task = root / ".agent_hub" / "inbox" / "001_preview.md"
    task.write_text(
        task.read_text(encoding="utf-8")
        .replace("- Task-ID: 001", "- Task-ID: 001\n- Permission-Profile: P1_DOCS_SAFE")
        .replace("- `ats/example.py`", "- `config/trading.json`"),
        encoding="utf-8",
    )
    orchestrator = AgentOrchestrator(root)
    with pytest.raises(Exception, match="only allows documentation"):
        orchestrator.preview()


def test_headless_lean_worker_environment_switch(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)

    # 1. 验证默认/设置 standard 时不隔离环境
    orchestrator.config["worker_profile"] = "standard"
    env_std = orchestrator._setup_worker_environment()
    assert env_std.get("USERPROFILE") == os.environ.get("USERPROFILE")

    # 2. 验证设置 headless_lean 时自动隔离至 .worker_profile 目录
    orchestrator.config["worker_profile"] = "headless_lean"
    env_lean = orchestrator._setup_worker_environment()
    expected_profile = str(root / ".agent_hub" / ".worker_profile")
    assert env_lean.get("USERPROFILE") == expected_profile
    assert env_lean.get("HOME") == expected_profile
    assert (root / ".agent_hub" / ".worker_profile" / ".gemini").is_dir()


def test_compact_verification_text() -> None:
    raw = (
        "$ python -m pytest tests/test_demo.py\n"
        "exit=0\n"
        "................. [ 50%]\n"
        "................. [100%]\n"
        "warning: unused import ignored\n"
        "56 passed in 4.97s\n\n"
        "$ python -m compileall -q ats\n"
        "exit=0\n"
    )
    compact = AgentOrchestrator._compact_verification_text(raw, max_lines_per_command=5)
    assert "$ python -m pytest tests/test_demo.py" in compact
    assert "exit=0" in compact
    assert "56 passed in 4.97s" in compact
    assert "$ python -m compileall -q ats" in compact
    # 进度点行应当被过滤
    assert "[ 50%]" not in compact


def test_verification_requires_every_recorded_command_to_pass() -> None:
    assert AgentOrchestrator._verification_succeeded("$ first\nexit=0\n")
    assert not AgentOrchestrator._verification_succeeded(
        "$ first\nexit=0\n\n$ second\nexit=1\n"
    )
    assert not AgentOrchestrator._verification_succeeded("no exit evidence")


def test_scope_requires_explicit_pass_marker() -> None:
    assert AgentOrchestrator._scope_succeeded("Scope: PASS\n\nChanged paths:\na.py\n")
    assert not AgentOrchestrator._scope_succeeded("Changed paths:\n")
    assert not AgentOrchestrator._scope_succeeded(
        "Scope: PASS\n\nChanged paths:\na.py\n\nViolations:\na.py\n"
    )


def test_worker_tool_activity_tracks_consecutive_reads_after_write() -> None:
    log = "\n".join([
        'auto-approving tool confirmation "ViewFile" at step 1',
        'auto-approving tool confirmation "GrepSearch" at step 2',
        'file write "WriteToFile" at step 3',
        'auto-approving tool confirmation "ListDir" at step 4',
    ])
    assert AgentOrchestrator._tool_activity_counts(log) == (3, 1, 1)


def test_worker_monitor_marks_budget_but_does_not_force_terminate(tmp_path: Path) -> None:
    root = _project(tmp_path)
    artifact_dir = root / ".agent_hub" / "artifacts" / "001"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "antigravity.log"

    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.poll_count = 0
            self.terminated = False

        def poll(self):
            self.poll_count += 1
            if self.poll_count >= 3:
                self.returncode = 0
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = 0

        def kill(self):
            self.terminated = True
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    process = FakeProcess()

    def popen_factory(args, **kwargs):
        log_path.write_text(
            "\n".join(
                f'auto-approving tool confirmation "ViewFile" at step {index}'
                for index in range(3)
            ),
            encoding="utf-8",
        )
        return process

    orchestrator = AgentOrchestrator(root, popen_factory=popen_factory)
    orchestrator.config.update({
        "worker_max_readonly_tool_calls": 3,
        "worker_timeout_seconds": 30,
        "worker_no_activity_timeout_seconds": 30,
        "worker_monitor_interval_seconds": 0.05,
    })
    result = orchestrator._run_worker_monitored(
        ["fake-antigravity"], log_path, artifact_dir, os.environ.copy()
    )
    assert result.returncode == 0
    assert not process.terminated
    heartbeat = json.loads((artifact_dir / "worker_heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["status"] == "SUCCESS"
    assert heartbeat["readonly_calls_since_write"] == 3


def test_reviewer_uses_supported_codex_exec_flags(tmp_path: Path) -> None:
    root = _project(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({"review_model": "gpt-test", "review_effort": "low"})
    orchestrator._invoke_reviewer(
        "task", root / ".agent_hub" / "artifacts" / "001", "", ""
    )
    command = calls[0]
    assert command[1] == "exec"
    assert "--ask-for-approval" not in command
    assert "--effort" not in command
    assert 'approval_policy="never"' in command
    assert 'model_reasoning_effort="low"' in command


def test_stale_reviewer_artifact_is_not_reused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    artifact_dir = root / ".agent_hub" / "artifacts" / "001"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    review_file = artifact_dir / "codex_review.md"
    review_file.write_text("DECISION: APPROVED\n", encoding="utf-8")

    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "", "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    result, review = orchestrator._run_reviewer_fresh("task", artifact_dir, "", "", "")
    assert result.returncode == 2
    assert review == ""
    assert not review_file.exists()


def test_compact_diff_has_character_cap(tmp_path: Path) -> None:
    root = _project(tmp_path)

    def runner(args, **kwargs):
        if "--stat" in args:
            return subprocess.CompletedProcess(args, 0, "a.py | 1 +\n", "")
        return subprocess.CompletedProcess(args, 0, "+" + ("x" * 500), "")

    orchestrator = AgentOrchestrator(root, runner=runner)
    orchestrator.config.update({"max_review_diff_lines": 150, "max_review_diff_chars": 100})
    compact = orchestrator._compact_diff(["a.py"])
    assert len(compact) < 150
    assert "truncated" in compact


def test_get_rework_count_and_rework_limit_blocking(tmp_path: Path) -> None:
    root = _project(tmp_path)
    hub = AgentHub(root)

    # 1. 验证初始 rework_count 为 0
    assert hub.get_rework_count("001") == 0

    # 2. 模拟认领、提交和一次打回
    hub.claim("001", "orchestrator/antigravity")
    hub.submit("001", "orchestrator/antigravity", "first attempt")
    hub.review("001", "rework", "codex/orchestrator", "first rework request")

    # 验证打回计数递增为 1 且任务回到 inbox
    assert hub.get_rework_count("001") == 1
    assert (root / ".agent_hub" / "inbox" / "001_preview.md").exists()

    # 3. 测试当已达最大重做限制 (max_rework_cycles = 1) 时的熔断
    def reviewer_runner(args, **kwargs):
        # 模拟 Reviewer 依然返回 REWORK
        return subprocess.CompletedProcess(
            args, 0, "", "Codex reviewed with issues."
        )

    orchestrator = AgentOrchestrator(root, runner=reviewer_runner)
    orchestrator.config["max_rework_cycles"] = 1
    orchestrator.config["auto_review"] = True

    # 构造 codex_review.md 内容为 REWORK
    artifact_dir = root / ".agent_hub" / "artifacts" / "001"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "codex_review.md").write_text("DECISION: REWORK\n", encoding="utf-8")
    (artifact_dir / "verification.log").write_text("$ pytest\nexit=0\n", encoding="utf-8")
    (artifact_dir / "scope_check.md").write_text(
        "Scope: PASS\n\nChanged paths:\nats/example.py\n", encoding="utf-8"
    )

    report = orchestrator.review_existing("001")
    assert report.status == "REWORK_BLOCKED_FOR_HUMAN"
    # 任务被熔断，停留在 done，未被移回 inbox，阻断死循环
    assert not (root / ".agent_hub" / "inbox" / "001_preview.md").exists()
    assert (root / ".agent_hub" / "done" / "001_preview.md").exists()


def test_review_profiles_split_task_checkpoint_and_release(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    orchestrator.config["review_profiles"] = {
        "task_review": {"model": "fast-model", "effort": "low"},
        "p_checkpoint_review": {"model": "medium-model", "effort": "medium"},
        "release_gate": {"model": "high-model", "effort": "high"},
    }
    assert orchestrator._review_profile("task_review")["effort"] == "low"
    assert orchestrator._review_profile("p_checkpoint_review")["effort"] == "medium"
    assert orchestrator._review_profile("release_gate")["effort"] == "high"


def test_task_review_rejects_high_effort_when_quota_policy_forbids_it(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    orchestrator.config["review_profiles"] = {
        "task_review": {"model": "expensive", "effort": "high"}
    }
    orchestrator.config["review_quota_policy"] = {"forbid_high_for_task_review": True}
    with pytest.raises(Exception, match="forbidden"):
        orchestrator._review_profile("task_review")


def test_checkpoint_review_holds_before_all_tasks_are_approved(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    report = orchestrator.checkpoint_review("P1", ["001"])
    assert report.status == "CHECKPOINT_HOLD"
    assert (report.artifact_dir / "P_CHECKPOINT_REVIEW.md").exists()


def test_release_gate_holds_without_approved_checkpoints(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    report = orchestrator.release_gate("r1", ["P1"])
    assert report.status == "RELEASE_HOLD"
    assert (report.artifact_dir / "RELEASE_GATE.md").exists()


def test_parallel_scope_ignores_only_other_owned_paths(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    task_text = (root / ".agent_hub" / "inbox" / "001_preview.md").read_text(encoding="utf-8")
    violations = orchestrator._scope_violations(
        task_text,
        {"ats/example.py", "ats/other.py", "trade_gateway.py"},
        parallel_owned=["ats/other.py"],
    )
    assert violations == ["trade_gateway.py"]


def test_runnable_tasks_can_be_scoped_to_explicit_task_set(tmp_path: Path) -> None:
    root = _project(tmp_path)
    hub = root / ".agent_hub"
    source = (hub / "inbox" / "001_preview.md").read_text(encoding="utf-8")
    second = source.replace("- Task-ID: 001", "- Task-ID: 002").replace(
        "- `ats/example.py`", "- `ats/other.py`"
    )
    (hub / "inbox" / "002_scoped.md").write_text(second, encoding="utf-8")
    orchestrator = AgentOrchestrator(root)
    assert orchestrator.runnable_tasks(2, task_ids=["002"]) == ["002"]


def test_execute_batch_preserves_sibling_file_ownership_after_peer_finishes(tmp_path: Path) -> None:
    from types import SimpleNamespace

    root = _project(tmp_path)
    hub = root / ".agent_hub"
    source = (hub / "inbox" / "001_preview.md").read_text(encoding="utf-8")
    second = source.replace("- Task-ID: 001", "- Task-ID: 002").replace(
        "- `ats/example.py`", "- `ats/other.py`"
    )
    (hub / "inbox" / "002_parallel.md").write_text(second, encoding="utf-8")
    orchestrator = AgentOrchestrator(root)
    captured = {}

    def fake_execute(task_id, parallel_owned_patterns=()):
        captured[task_id] = set(parallel_owned_patterns)
        return SimpleNamespace(task_id=task_id)

    orchestrator.execute = fake_execute
    reports = orchestrator.execute_batch(2, task_ids=["001", "002"])
    assert [item.task_id for item in reports] == ["001", "002"]
    assert "ats/other.py" in captured["001"]
    assert "ats/example.py" in captured["002"]


def test_task_specific_read_budget_is_bounded_by_hard_cap(tmp_path: Path) -> None:
    root = _project(tmp_path)
    orchestrator = AgentOrchestrator(root)
    orchestrator.config["worker_max_readonly_tool_calls"] = 12
    orchestrator.config["worker_max_readonly_tool_calls_hard_cap"] = 24
    task_text = (root / ".agent_hub" / "inbox" / "001_preview.md").read_text(encoding="utf-8")
    assert orchestrator._worker_read_budget(task_text) == 12
    task_text = task_text.replace("- Task-ID: 001", "- Task-ID: 001\n- Readonly-Tool-Budget: 24")
    assert orchestrator._worker_read_budget(task_text) == 24
    too_high = task_text.replace("Readonly-Tool-Budget: 24", "Readonly-Tool-Budget: 25")
    with pytest.raises(Exception, match="between 1 and 24"):
        orchestrator._worker_read_budget(too_high)

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

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

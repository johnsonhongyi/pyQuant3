from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.agent_orchestrator import AgentOrchestrator


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
        return subprocess.CompletedProcess(args, 0, '{"status":"SUCCESS"}', "")

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

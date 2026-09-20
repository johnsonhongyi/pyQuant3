from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.agent_hub import AgentHub, HubError


SECTIONS = (
    "Task",
    "Metadata",
    "Context",
    "Files Allowed",
    "Files Forbidden",
    "Requirements",
    "Definition of Done",
    "Verification",
    "Rollback",
    "Output Contract",
)


def _build_hub(tmp_path: Path) -> AgentHub:
    hub = tmp_path / ".agent_hub"
    for name in ("inbox", "running", "done", "review", "archive", "events", "dashboard"):
        (hub / name).mkdir(parents=True)
    (hub / "policy.json").write_text(
        json.dumps({"max_running_tasks": 1, "required_sections": list(SECTIONS)}),
        encoding="utf-8",
    )
    task = ["# Task", "", "Test task", "", "## Metadata", "", "- Task-ID: 001"]
    for section in SECTIONS[2:]:
        task.extend(("", f"## {section}", "", "- value"))
    (hub / "inbox" / "001_test_task.md").write_text("\n".join(task), encoding="utf-8")
    return AgentHub(tmp_path)


def test_full_approved_lifecycle(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    assert hub.validate() == []

    running = hub.claim("1", "antigravity")
    assert running.parent.name == "running"

    result = hub.submit("001", "antigravity", "tests passed")
    assert "READY_FOR_REVIEW" in result.read_text(encoding="utf-8")

    review = hub.review("001", "approved", "codex", "accepted")
    assert "APPROVED" in review.read_text(encoding="utf-8")

    archived = hub.archive("001")
    assert archived.parent.name == "archive"
    events = (hub.hub / "events" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["action"] for line in events] == [
        "claimed",
        "submitted",
        "reviewed_approved",
        "archived",
    ]


def test_rework_returns_task_to_inbox(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.claim("001", "antigravity")
    hub.submit("001", "antigravity", "partial")
    hub.review("001", "rework", "codex", "missing test")
    assert hub.locate("001").state == "inbox"
    assert (hub.hub / "review" / "001_result_rework.md").exists()


def test_running_limit_prevents_second_claim(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    source = hub.hub / "inbox" / "001_test_task.md"
    second = source.read_text(encoding="utf-8").replace("Task-ID: 001", "Task-ID: 002")
    (hub.hub / "inbox" / "002_other_task.md").write_text(second, encoding="utf-8")
    hub.claim("001", "antigravity")
    with pytest.raises(HubError, match="limit"):
        hub.claim("002", "antigravity")


def test_archive_requires_approved_review(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.claim("001", "antigravity")
    hub.submit("001", "antigravity", "done")
    with pytest.raises(HubError, match="no approved review"):
        hub.archive("001")

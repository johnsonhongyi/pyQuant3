from __future__ import annotations

import json
import re
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


def test_retry_returns_running_task_to_inbox(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.claim("001", "antigravity")
    target = hub.retry("001", "orchestrator", "permission denied")
    assert target.parent.name == "inbox"
    event = json.loads((hub.hub / "events" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["action"] == "returned_for_retry"
    assert event["reason"] == "permission denied"


def _add_task(hub: AgentHub, task_id: str, filename: str, allowed: str, depends: str = "none") -> None:
    source = hub.hub / "inbox" / "001_test_task.md"
    text = source.read_text(encoding="utf-8")
    text = text.replace("Task-ID: 001", f"Task-ID: {task_id}\n- Depends-On: {depends}")
    text = re.sub(r"(?ms)^## Files Allowed\s*$.*?(?=^## |\\Z)", f"## Files Allowed\\n\\n- `{allowed}`\\n\\n", text)
    (hub.hub / "inbox" / filename).write_text(text, encoding="utf-8")


def test_parallel_claim_allows_disjoint_file_ownership(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.policy["max_running_tasks"] = 3
    first = hub.hub / "inbox" / "001_test_task.md"
    text = first.read_text(encoding="utf-8").replace(
        "## Files Allowed\n\n- value", "## Files Allowed\n\n- `src/a.py`"
    )
    first.write_text(text, encoding="utf-8")
    _add_task(hub, "002", "002_other.md", "src/b.py")
    hub.claim("001", "worker-a")
    hub.claim("002", "worker-b")
    assert len(hub._task_files("running")) == 2


def test_parallel_claim_blocks_overlapping_files(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.policy["max_running_tasks"] = 3
    first = hub.hub / "inbox" / "001_test_task.md"
    text = first.read_text(encoding="utf-8").replace(
        "## Files Allowed\n\n- value", "## Files Allowed\n\n- `src/shared.py`"
    )
    first.write_text(text, encoding="utf-8")
    _add_task(hub, "002", "002_conflict.md", "src/shared.py")
    hub.claim("001", "worker-a")
    with pytest.raises(HubError, match="file-conflict"):
        hub.claim("002", "worker-b")


def test_dependency_blocks_until_upstream_is_approved(tmp_path: Path) -> None:
    hub = _build_hub(tmp_path)
    hub.policy["max_running_tasks"] = 3
    _add_task(hub, "002", "002_dependent.md", "src/b.py", depends="001")
    with pytest.raises(HubError, match="dependency:001"):
        hub.claim("002", "worker-b")
    hub.claim("001", "worker-a")
    hub.submit("001", "worker-a", "done")
    hub.review("001", "approved", "codex", "ok")
    hub.claim("002", "worker-b")
    assert hub.locate("002").state == "running"

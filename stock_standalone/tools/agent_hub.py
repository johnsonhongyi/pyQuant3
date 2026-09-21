#!/usr/bin/env python3
"""File-driven task coordination for Codex and local execution agents."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


STATE_DIRS = ("inbox", "running", "done", "archive")
TASK_NAME_RE = re.compile(r"^(?P<id>\d{3,})_(?!result\.md$).+\.md$")


class HubError(RuntimeError):
    """Raised when a requested state transition is unsafe or invalid."""


@dataclass(frozen=True)
class TaskLocation:
    task_id: str
    state: str
    path: Path


class AgentHub:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.hub = self.project_root / ".agent_hub"
        self.policy = self._load_policy()

    def _load_policy(self) -> dict:
        policy_path = self.hub / "policy.json"
        if not policy_path.exists():
            raise HubError(f"Missing policy: {policy_path}")
        return json.loads(policy_path.read_text(encoding="utf-8"))

    def _task_files(self, state: str) -> list[Path]:
        directory = self.hub / state
        if not directory.exists():
            return []
        return sorted(
            path for path in directory.glob("*.md")
            if TASK_NAME_RE.match(path.name) and not path.name.endswith("_result.md")
        )

    def locate(self, task_id: str, states: Iterable[str] = STATE_DIRS) -> TaskLocation:
        normalized = task_id.zfill(3)
        matches: list[TaskLocation] = []
        for state in states:
            for path in self._task_files(state):
                match = TASK_NAME_RE.match(path.name)
                if match and match.group("id") == normalized:
                    matches.append(TaskLocation(normalized, state, path))
        if not matches:
            raise HubError(f"Task {normalized} was not found in {', '.join(states)}")
        if len(matches) > 1:
            locations = ", ".join(str(item.path) for item in matches)
            raise HubError(f"Task {normalized} exists in multiple states: {locations}")
        return matches[0]

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def _event(self, task_id: str, action: str, actor: str, **details: str) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "action": action,
            "actor": actor,
            **details,
        }
        event_path = self.hub / "events" / "events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        with event_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def validate(self) -> list[str]:
        errors: list[str] = []
        required = self.policy.get("required_sections", [])
        seen: dict[str, Path] = {}
        for state in STATE_DIRS:
            for path in self._task_files(state):
                match = TASK_NAME_RE.match(path.name)
                if not match:
                    continue
                task_id = match.group("id")
                if task_id in seen:
                    errors.append(f"duplicate task {task_id}: {seen[task_id]} and {path}")
                seen[task_id] = path
                text = path.read_text(encoding="utf-8")
                for section in required:
                    if not re.search(rf"^#{{1,2}} {re.escape(section)}\s*$", text, re.MULTILINE):
                        errors.append(f"{path}: missing section '{section}'")
                declared = re.search(r"^- Task-ID:\s*(\d+)\s*$", text, re.MULTILINE)
                if not declared or declared.group(1).zfill(3) != task_id:
                    errors.append(f"{path}: Task-ID does not match filename")
        max_running = int(self.policy.get("max_running_tasks", 1))
        running_count = len(self._task_files("running"))
        if running_count > max_running:
            errors.append(f"running task count {running_count} exceeds limit {max_running}")
        return errors

    def claim(self, task_id: str, agent: str) -> Path:
        errors = self.validate()
        if errors:
            raise HubError("Hub validation failed:\n- " + "\n- ".join(errors))
        max_running = int(self.policy.get("max_running_tasks", 1))
        if len(self._task_files("running")) >= max_running:
            raise HubError(f"Running task limit reached ({max_running})")
        item = self.locate(task_id, ("inbox",))
        target = self.hub / "running" / item.path.name
        os.replace(item.path, target)
        self._event(item.task_id, "claimed", agent, from_state="inbox", to_state="running")
        self.write_dashboard()
        return target

    def submit(self, task_id: str, agent: str, summary: str) -> Path:
        item = self.locate(task_id, ("running",))
        target = self.hub / "done" / item.path.name
        os.replace(item.path, target)
        result = self.hub / "done" / f"{item.task_id}_result.md"
        content = (
            f"# Result {item.task_id}\n\n"
            f"- Agent: {agent}\n"
            f"- Submitted-At: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Status: READY_FOR_REVIEW\n\n"
            f"## Summary\n\n{summary.strip()}\n"
        )
        self._atomic_write(result, content)
        self._event(item.task_id, "submitted", agent, from_state="running", to_state="done")
        self.write_dashboard()
        return result

    def retry(self, task_id: str, actor: str, reason: str) -> Path:
        item = self.locate(task_id, ("running",))
        target = self.hub / "inbox" / item.path.name
        os.replace(item.path, target)
        self._event(
            item.task_id,
            "returned_for_retry",
            actor,
            from_state="running",
            to_state="inbox",
            reason=reason,
        )
        self.write_dashboard()
        return target

    def get_rework_count(self, task_id: str) -> int:
        norm_id = task_id.zfill(3)
        event_path = self.hub / "events" / "events.jsonl"
        if not event_path.is_file():
            return 0
        count = 0
        with event_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("task_id") == norm_id and data.get("action") == "reviewed_rework":
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count

    def review(self, task_id: str, decision: str, reviewer: str, summary: str) -> Path:
        item = self.locate(task_id, ("done",))
        decision = decision.lower()
        if decision not in {"approved", "rework", "rework_blocked"}:
            raise HubError("Decision must be approved, rework, or rework_blocked")
        report = self.hub / "review" / f"{item.task_id}_review.md"
        content = (
            f"# Review {item.task_id}\n\n"
            f"- Reviewer: {reviewer}\n"
            f"- Reviewed-At: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Decision: {decision.upper()}\n\n"
            f"## Findings\n\n{summary.strip()}\n"
        )
        self._atomic_write(report, content)
        if decision == "rework":
            target = self.hub / "inbox" / item.path.name
            os.replace(item.path, target)
            result = self.hub / "done" / f"{item.task_id}_result.md"
            if result.exists():
                result.replace(self.hub / "review" / f"{item.task_id}_result_rework.md")
            self._event(item.task_id, "reviewed_rework", reviewer, from_state="done", to_state="inbox")
        elif decision == "rework_blocked":
            # 达到打回熔断上限，任务留在 done 状态，不移回 inbox，等待人工仲裁，阻断无限死循环
            self._event(item.task_id, "reviewed_rework_blocked", reviewer, state="done")
        else:
            self._event(item.task_id, "reviewed_approved", reviewer, state="done")
        self.write_dashboard()
        return report

    def archive(self, task_id: str) -> Path:
        item = self.locate(task_id, ("done",))
        review = self.hub / "review" / f"{item.task_id}_review.md"
        if not review.exists() or "- Decision: APPROVED" not in review.read_text(encoding="utf-8"):
            raise HubError(f"Task {item.task_id} has no approved review")
        target = self.hub / "archive" / item.path.name
        os.replace(item.path, target)
        result = self.hub / "done" / f"{item.task_id}_result.md"
        if result.exists():
            result.replace(self.hub / "archive" / result.name)
        self._event(item.task_id, "archived", "orchestrator", from_state="done", to_state="archive")
        self.write_dashboard()
        return target

    def write_dashboard(self) -> Path:
        lines = [
            "# Agent Hub Status",
            "",
            f"Updated: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for state in STATE_DIRS:
            tasks = self._task_files(state)
            lines.extend((f"## {state.title()} ({len(tasks)})", ""))
            if tasks:
                for path in tasks:
                    first_heading = next(
                        (line[2:].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("# ")),
                        path.stem,
                    )
                    lines.append(f"- `{path.name}`: {first_heading}")
            else:
                lines.append("- None")
            lines.append("")
        dashboard = self.hub / "dashboard" / "STATUS.md"
        self._atomic_write(dashboard, "\n".join(lines))
        return dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ATS file-driven multi-agent coordinator")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("validate")

    claim = sub.add_parser("claim")
    claim.add_argument("task_id")
    claim.add_argument("--agent", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("task_id")
    submit.add_argument("--agent", required=True)
    submit.add_argument("--summary", required=True)

    retry = sub.add_parser("retry")
    retry.add_argument("task_id")
    retry.add_argument("--actor", required=True)
    retry.add_argument("--reason", required=True)

    review = sub.add_parser("review")
    review.add_argument("task_id")
    review.add_argument("--decision", choices=("approved", "rework"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--summary", required=True)

    archive = sub.add_parser("archive")
    archive.add_argument("task_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hub = AgentHub(args.root)
        if args.command == "validate":
            errors = hub.validate()
            if errors:
                print("INVALID")
                for error in errors:
                    print(f"- {error}")
                return 1
            print("VALID")
            return 0
        if args.command == "status":
            path = hub.write_dashboard()
            print(path)
            print(path.read_text(encoding="utf-8"))
            return 0
        if args.command == "claim":
            print(hub.claim(args.task_id, args.agent))
        elif args.command == "submit":
            print(hub.submit(args.task_id, args.agent, args.summary))
        elif args.command == "retry":
            print(hub.retry(args.task_id, args.actor, args.reason))
        elif args.command == "review":
            print(hub.review(args.task_id, args.decision, args.reviewer, args.summary))
        elif args.command == "archive":
            print(hub.archive(args.task_id))
        return 0
    except (HubError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

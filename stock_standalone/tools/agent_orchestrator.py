#!/usr/bin/env python3
"""Controlled Codex -> Antigravity -> verification -> Codex review loop."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

try:
    from tools.agent_hub import AgentHub, HubError
except ModuleNotFoundError:  # Direct execution: python tools/agent_orchestrator.py
    from agent_hub import AgentHub, HubError


Runner = Callable[..., subprocess.CompletedProcess[str]]
VERIFY_BLOCK_RE = re.compile(r"```(?:powershell|bash|text)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


class OrchestratorError(RuntimeError):
    """Raised when an automated stage cannot proceed safely."""


@dataclass(frozen=True)
class FileStamp:
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class RunReport:
    task_id: str
    status: str
    artifact_dir: Path
    message: str


class AgentOrchestrator:
    RISK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    DEFAULT_PERMISSION_PROFILES = {
        "P0_READONLY": {"worker_mode": "plan", "auto_approve": False},
        "P1_DOCS_SAFE": {"worker_mode": "accept-edits", "auto_approve": True},
        "P2_CODE_LOW": {
            "worker_mode": "accept-edits", "auto_approve": True, "max_risk": "LOW"
        },
        "P3_CODE_MEDIUM": {
            "worker_mode": "accept-edits", "auto_approve": True, "max_risk": "MEDIUM"
        },
        "P4_RELEASE_GATE": {"worker_mode": "plan", "auto_approve": False},
        "P5_FORBIDDEN": {"worker_mode": "forbidden", "auto_approve": False},
    }

    def __init__(self, project_root: Path, runner: Runner = subprocess.run) -> None:
        self.root = project_root.resolve()
        self.hub = AgentHub(self.root)
        self.config = json.loads(
            (self.hub.hub / "orchestrator.json").read_text(encoding="utf-8")
        )
        self.runner = runner

    def _run(self, args: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return self.runner(
            list(args),
            cwd=self.root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            **kwargs,
        )

    def preflight(self, require_auth: bool = False) -> list[str]:
        errors = self.hub.validate()
        for key in ("antigravity_executable", "codex_executable"):
            executable = Path(self.config.get(key, ""))
            if not executable.is_file():
                errors.append(f"missing {key}: {executable}")
        if not errors:
            for key in ("antigravity_executable", "codex_executable"):
                result = self._run([self.config[key], "--version"], timeout=20)
                if result.returncode != 0:
                    errors.append(f"{key} version check failed: {result.stderr.strip()}")
        if require_auth and not errors:
            probe_dir = self.hub.hub / "artifacts" / "preflight"
            probe_dir.mkdir(parents=True, exist_ok=True)
            agy_probe = self._run(
                [
                    self.config["antigravity_executable"],
                    "--print",
                    "Reply with exactly PREFLIGHT_OK and do not use tools.",
                    "--output-format",
                    "text",
                    "--mode",
                    "plan",
                    "--sandbox",
                    "--print-timeout",
                    "60s",
                    "--log-file",
                    str(probe_dir / "antigravity_probe.log"),
                ],
                timeout=90,
            )
            if agy_probe.returncode != 0 or "PREFLIGHT_OK" not in agy_probe.stdout:
                errors.append("Antigravity authentication probe failed: " + agy_probe.stderr.strip())
            codex_probe = self._run(
                [
                    self.config["codex_executable"],
                    "--sandbox",
                    "read-only",
                    "--ask-for-approval",
                    "never",
                    "--cd",
                    str(self.root),
                    "exec",
                    "--ephemeral",
                    "-",
                ],
                input="Reply with exactly PREFLIGHT_OK. Do not inspect files or use tools.",
                timeout=90,
            )
            if codex_probe.returncode != 0 or "PREFLIGHT_OK" not in codex_probe.stdout:
                errors.append("Codex authentication probe failed: " + codex_probe.stderr.strip())
        if require_auth and errors:
            errors.append("real execution is disabled until authenticated preflight succeeds")
        return errors

    def select_task(self, task_id: str | None = None) -> str:
        if task_id:
            return self.hub.locate(task_id, ("inbox",)).task_id
        tasks = self.hub._task_files("inbox")
        if not tasks:
            raise OrchestratorError("No task is available in inbox")
        match = re.match(r"(\d{3,})_", tasks[0].name)
        if not match:
            raise OrchestratorError(f"Invalid task filename: {tasks[0].name}")
        return match.group(1)

    def _inventory(self) -> dict[str, FileStamp]:
        result = self._run(["git", "ls-files", "-co", "--exclude-standard", "-z"], timeout=60)
        if result.returncode != 0:
            raise OrchestratorError(f"Cannot inventory workspace: {result.stderr.strip()}")
        inventory: dict[str, FileStamp] = {}
        for raw in result.stdout.split("\0"):
            if not raw:
                continue
            relative = raw.replace("\\", "/")
            path = self.root / raw
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if path.is_file():
                inventory[relative] = FileStamp(stat.st_size, stat.st_mtime_ns)
        return inventory

    @staticmethod
    def _section_items(task_text: str, heading: str) -> list[str]:
        match = re.search(
            rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
            task_text,
            re.MULTILINE | re.DOTALL,
        )
        if not match:
            return []
        return [
            item.strip().strip("`")
            for item in re.findall(r"^-\s+(.+?)\s*$", match.group("body"), re.MULTILINE)
        ]

    def _changed_paths(
        self, before: dict[str, FileStamp], after: dict[str, FileStamp]
    ) -> set[str]:
        return {
            path for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }

    def _scope_violations(self, task_text: str, changed: set[str]) -> list[str]:
        allowed = self._section_items(task_text, "Files Allowed")
        ignored = self.config.get("scope_ignore_prefixes", [])
        violations = []
        for path in sorted(changed):
            if any(path.startswith(prefix) for prefix in ignored):
                continue
            if not any(fnmatch.fnmatch(path, pattern) for pattern in allowed):
                violations.append(path)
        return violations

    def _verification_commands(self, task_text: str) -> list[list[str]]:
        section = re.search(
            r"^## Verification\s*$\n(?P<body>.*?)(?=^## |\Z)",
            task_text,
            re.MULTILINE | re.DOTALL,
        )
        if not section:
            raise OrchestratorError("Task has no Verification section")
        commands: list[list[str]] = []
        for block in VERIFY_BLOCK_RE.findall(section.group("body")):
            for line in block.splitlines():
                command = line.strip()
                if not command or command.startswith("#"):
                    continue
                prefixes = self.config.get("allowed_verification_prefixes", [])
                if not any(command.startswith(prefix) for prefix in prefixes):
                    raise OrchestratorError(f"Verification command is not allowed: {command}")
                commands.append(shlex.split(command, posix=False))
        if not commands:
            raise OrchestratorError("Task has no executable verification command")
        return commands

    def _worker_prompt(self, task_path: Path) -> str:
        protocol = (self.hub.hub / "AGENT_PROMPT.md").read_text(encoding="utf-8")
        task = task_path.read_text(encoding="utf-8")
        return (
            f"{protocol}\n\n"
            "The orchestrator has already claimed this task. Do not call claim or submit. "
            "Implement only this task and write its Output Contract artifacts. "
            "Do not use RunCommand, terminal, shell, or process tools; the orchestrator runs all "
            "verification commands after you finish. Use built-in file search/read/edit tools only.\n\n"
            f"{task}"
        )

    @staticmethod
    def _task_risk(task_text: str) -> str:
        match = re.search(r"^- Risk:\s*(\w+)\s*$", task_text, re.MULTILINE | re.IGNORECASE)
        return match.group(1).upper() if match else "LOW"

    @staticmethod
    def _metadata_value(task_text: str, key: str) -> str | None:
        match = re.search(
            rf"^-\s*{re.escape(key)}:\s*(.+?)\s*$",
            task_text,
            re.MULTILINE | re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    def _permission_profile(self, task_text: str) -> str:
        return (self._metadata_value(task_text, "Permission-Profile") or "P2_CODE_LOW").upper()

    def _permission_profiles(self) -> dict[str, dict[str, object]]:
        profiles = {name: dict(values) for name, values in self.DEFAULT_PERMISSION_PROFILES.items()}
        for name, overrides in self.config.get("permission_profiles", {}).items():
            profiles.setdefault(name, {}).update(overrides)
        return profiles

    def _permission_profile_config(self, task_text: str) -> tuple[str, dict[str, object]]:
        profile_name = self._permission_profile(task_text)
        profile = self._permission_profiles().get(profile_name)
        if profile is None:
            raise OrchestratorError(f"Unknown Permission-Profile: {profile_name}")
        return profile_name, profile

    def _validate_permission_profile(self, task_text: str) -> None:
        profile_name, profile = self._permission_profile_config(task_text)
        worker_mode = str(profile.get("worker_mode", "forbidden"))
        if worker_mode == "forbidden":
            raise OrchestratorError(f"Permission-Profile {profile_name} cannot be automated")
        if worker_mode not in {"plan", "accept-edits"}:
            raise OrchestratorError(
                f"Permission-Profile {profile_name} has invalid worker_mode: {worker_mode}"
            )

        task_risk = self._task_risk(task_text)
        task_rank = self.RISK_RANK.get(task_risk)
        if task_rank is None:
            raise OrchestratorError(f"Unknown task risk: {task_risk}")
        max_risk_value = profile.get("max_risk")
        max_risk = str(max_risk_value).upper() if max_risk_value else None
        max_rank = self.RISK_RANK.get(max_risk) if max_risk else None
        if max_risk and max_rank is None:
            raise OrchestratorError(
                f"Permission-Profile {profile_name} has invalid max_risk: {max_risk}"
            )
        if max_rank is not None and task_rank > max_rank:
            raise OrchestratorError(
                f"Permission-Profile {profile_name} allows <= {max_risk}; task risk is {task_risk}"
            )

        allowed = self._section_items(task_text, "Files Allowed")
        if profile_name == "P1_DOCS_SAFE":
            doc_patterns = (".md", ".txt", ".rst", ".adoc")
            invalid_docs_path = next((
                pattern for pattern in allowed
                if not pattern.startswith(".agent_hub/") and not pattern.endswith(doc_patterns)
            ), None)
            if invalid_docs_path:
                raise OrchestratorError(
                    f"Permission-Profile {profile_name} only allows documentation or "
                    f".agent_hub paths: {invalid_docs_path}"
                )

    @staticmethod
    def _is_transient_auth_failure(result: subprocess.CompletedProcess[str]) -> bool:
        combined = f"{result.stdout}\n{result.stderr}".lower()
        markers = (
            "you are not logged into antigravity",
            "authentication timed out",
            "authentication failed or timed out",
            "silent auth failed",
        )
        return result.returncode != 0 and any(marker in combined for marker in markers)

    def _invoke_worker(
        self, prompt: str, artifact_dir: Path, task_risk: str, profile_name: str = "P2_CODE_LOW"
    ) -> subprocess.CompletedProcess[str]:
        profile = self._permission_profiles().get(profile_name)
        if profile is None:
            raise OrchestratorError(f"Unknown Permission-Profile: {profile_name}")
        worker_mode = str(profile.get("worker_mode", "forbidden"))
        if worker_mode == "forbidden":
            raise OrchestratorError(f"Permission-Profile {profile_name} cannot be automated")
        auto_approve = (
            bool(self.config.get("worker_auto_approve_permissions", False))
            and bool(profile.get("auto_approve", False))
        )
        allowed_risk = self.config.get("max_auto_approve_risk", "LOW").upper()
        if auto_approve:
            task_rank = self.RISK_RANK.get(task_risk)
            allowed_rank = self.RISK_RANK.get(allowed_risk)
            if task_rank is None or allowed_rank is None or task_rank > allowed_rank:
                raise OrchestratorError(
                    f"Automatic permission approval is restricted to <= {allowed_risk} tasks; "
                    f"task risk is {task_risk}"
                )
        primary = self.config.get("worker_model", "").strip()
        models = [primary] if primary else [""]
        models.extend(self.config.get("worker_fallback_models", []))
        attempts: list[subprocess.CompletedProcess[str]] = []
        worker_env = os.environ.copy()
        proxy = self.config.get("worker_proxy", "").strip()
        if proxy:
            worker_env.update({
                "HTTP_PROXY": proxy,
                "HTTPS_PROXY": proxy,
                "ALL_PROXY": proxy,
            })
        for index, model in enumerate(models, start=1):
            safe_model = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model or "default")
            args = [
                self.config["antigravity_executable"],
                "--print",
                prompt,
                "--output-format",
                "json",
                "--mode",
                worker_mode,
                "--sandbox",
                "--print-timeout",
                f"{int(self.config.get('worker_timeout_seconds', 1800))}s",
                "--log-file",
                str(artifact_dir / f"antigravity_{index}_{safe_model}.log"),
            ]
            if model:
                args.extend(("--model", model))
            else:
                args.extend(("--effort", self.config.get("worker_effort", "medium")))
            if auto_approve:
                # Antigravity requires this even for ListDir in print mode. The
                # terminal sandbox and post-run scope enforcement remain mandatory.
                args.append("--dangerously-skip-permissions")
            result = self._run(
                args,
                timeout=int(self.config.get("worker_timeout_seconds", 1800)) + 30,
                env=worker_env,
            )
            attempts.append(result)
            self._write(
                artifact_dir / f"worker_attempt_{index}_{safe_model}.stdout", result.stdout
            )
            self._write(
                artifact_dir / f"worker_attempt_{index}_{safe_model}.stderr", result.stderr
            )
            if self._is_transient_auth_failure(result):
                retry = self._run(
                    args,
                    timeout=int(self.config.get("worker_timeout_seconds", 1800)) + 30,
                    env=worker_env,
                )
                attempts.append(retry)
                self._write(
                    artifact_dir / f"worker_attempt_{index}_{safe_model}_auth_retry.stdout",
                    retry.stdout,
                )
                self._write(
                    artifact_dir / f"worker_attempt_{index}_{safe_model}_auth_retry.stderr",
                    retry.stderr,
                )
                result = retry
            if result.returncode == 0:
                return result
        last = attempts[-1]
        combined_error = "\n\n".join(
            f"Attempt {index} ({models[min(index - 1, len(models) - 1)] or 'default'}):\n{item.stderr}"
            for index, item in enumerate(attempts, start=1)
        )
        return subprocess.CompletedProcess(last.args, last.returncode, last.stdout, combined_error)

    def _invoke_reviewer(
        self, task_text: str, artifact_dir: Path, verification: str, scope: str
    ) -> subprocess.CompletedProcess[str]:
        review_rules = (self.hub.hub / "review_prompt.md").read_text(encoding="utf-8")
        prompt = (
            f"{review_rules}\n\n## TASK\n{task_text}\n\n"
            f"## ORCHESTRATOR VERIFICATION\n{verification}\n\n"
            f"## SCOPE CHECK\n{scope}\n"
        )
        return self._run(
            [
                self.config["codex_executable"],
                "--sandbox",
                "read-only",
                "--ask-for-approval",
                "never",
                "--cd",
                str(self.root),
                "exec",
                "--ephemeral",
                "--output-last-message",
                str(artifact_dir / "codex_review.md"),
                "-",
            ],
            input=prompt,
            timeout=int(self.config.get("review_timeout_seconds", 900)),
        )

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def preview(self, task_id: str | None = None) -> RunReport:
        selected = self.select_task(task_id)
        task = self.hub.locate(selected, ("inbox",))
        task_text = task.path.read_text(encoding="utf-8")
        self._validate_permission_profile(task_text)
        commands = self._verification_commands(task_text)
        message = (
            f"Would run task {selected} with Antigravity, then execute "
            f"{len(commands)} allow-listed verification command(s) and request Codex review."
        )
        return RunReport(selected, "DRY_RUN", self.hub.hub / "artifacts" / selected, message)

    def execute(self, task_id: str | None = None) -> RunReport:
        # Authentication is checked explicitly by `preflight --require-auth` before a run.
        # Repeating two model probes for every task wastes quota and introduces a transient
        # dependency before the task is even claimed; the worker still reports auth errors.
        errors = self.preflight(require_auth=False)
        if errors:
            raise OrchestratorError("Preflight failed:\n- " + "\n- ".join(errors))
        selected = self.select_task(task_id)
        inbox_task = self.hub.locate(selected, ("inbox",))
        task_text = inbox_task.path.read_text(encoding="utf-8")
        self._validate_permission_profile(task_text)
        running_path = self.hub.claim(selected, "orchestrator/antigravity")
        task_text = running_path.read_text(encoding="utf-8")
        artifact_dir = self.hub.hub / "artifacts" / selected
        artifact_dir.mkdir(parents=True, exist_ok=True)
        before = self._inventory()

        worker = self._invoke_worker(
            self._worker_prompt(running_path),
            artifact_dir,
            self._task_risk(task_text),
            self._permission_profile(task_text),
        )
        self._write(artifact_dir / "worker_stdout.json", worker.stdout)
        self._write(artifact_dir / "worker_stderr.log", worker.stderr)
        if worker.returncode != 0:
            self._write(artifact_dir / "orchestrator_failure.md", "# Worker failed\n\n" + worker.stderr)
            return RunReport(selected, "WORKER_FAILED", artifact_dir, "Task remains in running for diagnosis")

        verification_parts: list[str] = []
        verification_ok = True
        for command in self._verification_commands(task_text):
            result = self._run(command, timeout=900)
            rendered = " ".join(command)
            verification_parts.append(
                f"$ {rendered}\nexit={result.returncode}\n{result.stdout}\n{result.stderr}".strip()
            )
            verification_ok = verification_ok and result.returncode == 0
        verification_text = "\n\n".join(verification_parts)
        self._write(artifact_dir / "verification.log", verification_text)

        changed = self._changed_paths(before, self._inventory())
        violations = self._scope_violations(task_text, changed)
        scope_text = "Changed paths:\n" + "\n".join(sorted(changed))
        if violations:
            scope_text += "\n\nViolations:\n" + "\n".join(violations)
        self._write(artifact_dir / "scope_check.md", scope_text)

        summary = (
            f"Worker exit=0; verification={'PASS' if verification_ok else 'FAIL'}; "
            f"scope={'PASS' if not violations else 'FAIL'}"
        )
        self.hub.submit(selected, "orchestrator/antigravity", summary)

        decision = "REWORK"
        review_text = "Automated Codex review was not run."
        if self.config.get("auto_review", True):
            reviewer = self._invoke_reviewer(task_text, artifact_dir, verification_text, scope_text)
            review_file = artifact_dir / "codex_review.md"
            review_text = review_file.read_text(encoding="utf-8") if review_file.exists() else reviewer.stdout
            self._write(artifact_dir / "codex_review_stderr.log", reviewer.stderr)
            if reviewer.returncode == 0 and re.search(r"^DECISION: APPROVED\s*$", review_text, re.MULTILINE):
                decision = "APPROVED"
        if not verification_ok or violations:
            decision = "REWORK"

        self.hub.review(
            selected,
            decision.lower(),
            "codex/orchestrator",
            review_text or summary,
        )
        merge_report = (
            f"# Merge Report {selected}\n\n"
            f"- Generated-At: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Worker: PASS\n"
            f"- Verification: {'PASS' if verification_ok else 'FAIL'}\n"
            f"- Scope: {'PASS' if not violations else 'FAIL'}\n"
            f"- Codex-Decision: {decision}\n"
            f"- Auto-Merge: OFF\n"
            f"- Auto-Archive: OFF\n"
        )
        self._write(self.hub.hub / "decisions" / f"{selected}_merge_report.md", merge_report)
        return RunReport(selected, decision, artifact_dir, summary)

    def review_existing(self, task_id: str) -> RunReport:
        selected = self.select_task(task_id)
        artifact_dir = self.hub.hub / "artifacts" / selected
        verification_path = artifact_dir / "verification.log"
        scope_path = artifact_dir / "scope_check.md"
        if not verification_path.exists() or not scope_path.exists():
            raise OrchestratorError(f"Task {selected} has no complete verification evidence")
        task_path = self.hub.claim(selected, "orchestrator/re-review")
        task_text = task_path.read_text(encoding="utf-8")
        verification_text = verification_path.read_text(encoding="utf-8")
        scope_text = scope_path.read_text(encoding="utf-8")
        verification_ok = "exit=0" in verification_text
        scope_ok = "Violations:" not in scope_text
        self.hub.submit(
            selected,
            "orchestrator/re-review",
            f"Reused evidence; verification={'PASS' if verification_ok else 'FAIL'}; "
            f"scope={'PASS' if scope_ok else 'FAIL'}",
        )
        reviewer = self._invoke_reviewer(task_text, artifact_dir, verification_text, scope_text)
        review_file = artifact_dir / "codex_review.md"
        review_text = review_file.read_text(encoding="utf-8") if review_file.exists() else reviewer.stdout
        self._write(artifact_dir / "codex_review_stderr.log", reviewer.stderr)
        approved = (
            reviewer.returncode == 0
            and verification_ok
            and scope_ok
            and bool(re.search(r"^DECISION: APPROVED\s*$", review_text, re.MULTILINE))
        )
        decision = "APPROVED" if approved else "REWORK"
        self.hub.review(selected, decision.lower(), "codex/orchestrator", review_text)
        merge_report = (
            f"# Merge Report {selected}\n\n"
            f"- Generated-At: {datetime.now(timezone.utc).isoformat()}\n"
            f"- Evidence-Reused: YES\n"
            f"- Verification: {'PASS' if verification_ok else 'FAIL'}\n"
            f"- Scope: {'PASS' if scope_ok else 'FAIL'}\n"
            f"- Codex-Decision: {decision}\n"
            f"- Auto-Merge: OFF\n"
            f"- Auto-Archive: OFF\n"
        )
        self._write(self.hub.hub / "decisions" / f"{selected}_merge_report.md", merge_report)
        return RunReport(selected, decision, artifact_dir, "Existing evidence reviewed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the controlled ATS multi-agent pipeline")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--require-auth", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--task")
    run.add_argument("--execute", action="store_true")
    rereview = sub.add_parser("review-existing")
    rereview.add_argument("--task", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        orchestrator = AgentOrchestrator(args.root)
        if args.command == "preflight":
            errors = orchestrator.preflight(args.require_auth)
            if errors:
                print("PREFLIGHT FAILED")
                print("\n".join(f"- {item}" for item in errors))
                return 1
            print("PREFLIGHT PASSED")
            return 0
        if args.command == "review-existing":
            report = orchestrator.review_existing(args.task)
        else:
            report = orchestrator.execute(args.task) if args.execute else orchestrator.preview(args.task)
        print(json.dumps({
            "task_id": report.task_id,
            "status": report.status,
            "artifact_dir": str(report.artifact_dir),
            "message": report.message,
        }, ensure_ascii=False, indent=2))
        return 0
    except (HubError, OrchestratorError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

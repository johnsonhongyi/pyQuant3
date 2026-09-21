#!/usr/bin/env python3
"""Controlled Codex -> Antigravity -> verification -> Codex review loop."""

from __future__ import annotations

import argparse
import fnmatch
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:
    from tools.agent_hub import AgentHub, HubError
except ModuleNotFoundError:  # Direct execution: python tools/agent_orchestrator.py
    from agent_hub import AgentHub, HubError


Runner = Callable[..., subprocess.CompletedProcess[str]]
PopenFactory = Callable[..., subprocess.Popen[str]]
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
    WORKER_REPORT_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["task_id", "status", "diff_files", "test_result", "risk_points", "summary"],
        "properties": {
            "task_id": {"type": "string"},
            "status": {"enum": ["SUCCESS", "PARTIAL", "FAIL", "BLOCKED"]},
            "diff_files": {"type": "array", "items": {"type": "string"}},
            "test_result": {
                "type": "object",
                "additionalProperties": False,
                "required": ["lint", "typecheck", "unit_tests", "failed_cases"],
                "properties": {
                    "lint": {"enum": ["pass", "fail", "not_applicable"]},
                    "typecheck": {"enum": ["pass", "fail", "not_applicable"]},
                    "unit_tests": {"enum": ["pass", "fail", "not_applicable"]},
                    "failed_cases": {"type": "array", "items": {"type": "string"}},
                },
            },
            "risk_points": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string", "maxLength": 200},
        },
    }
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

    def __init__(
        self,
        project_root: Path,
        runner: Runner = subprocess.run,
        popen_factory: PopenFactory = subprocess.Popen,
    ) -> None:
        self.root = project_root.resolve()
        self.hub = AgentHub(self.root)
        self.config = json.loads(
            (self.hub.hub / "orchestrator.json").read_text(encoding="utf-8")
        )
        self.runner = runner
        self.popen_factory = popen_factory
        self._claim_lock = threading.Lock()

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
                    "exec",
                    "--sandbox",
                    "read-only",
                    "--config",
                    'approval_policy="never"',
                    "--cd",
                    str(self.root),
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

    def _scope_violations(
        self,
        task_text: str,
        changed: set[str],
        parallel_owned: Sequence[str] = (),
    ) -> list[str]:
        allowed = self._section_items(task_text, "Files Allowed")
        ignored = self.config.get("scope_ignore_prefixes", [])
        violations = []
        for path in sorted(changed):
            if any(path.startswith(prefix) for prefix in ignored):
                continue
            if any(fnmatch.fnmatch(path, pattern) for pattern in allowed):
                continue
            if any(fnmatch.fnmatch(path, pattern) for pattern in parallel_owned):
                continue
            violations.append(path)
        return violations

    def _parallel_owned_patterns(self, exclude_task_id: str) -> list[str]:
        patterns: list[str] = []
        for path in self.hub._task_files("running"):
            match = re.match(r"(\d{3,})_", path.name)
            if match and match.group(1) == exclude_task_id.zfill(3):
                continue
            patterns.extend(
                self._section_items(path.read_text(encoding="utf-8"), "Files Allowed")
            )
        return patterns

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
        task = task_path.read_text(encoding="utf-8")
        allowed_files = self._section_items(task, "Files Allowed")
        budget = int(self.config.get("worker_max_readonly_tool_calls", 12))
        return (
            "AUTHORITATIVE INVOCATION RULES: "
            "The orchestrator has already claimed this task. Do not call claim or submit. "
            "Implement only this task and write its Output Contract artifacts. "
            "Do not use RunCommand, terminal, shell, or process tools; the orchestrator runs all "
            "verification commands after you finish. Use built-in file search/read/edit tools only. "
            "Read only the listed files and directly imported contracts needed to edit them; never "
            "browse directories, repository history, unrelated tests, or task archives. Your read/search "
            f"budget is {budget} tool calls total. If the task cannot be completed inside that budget, stop and "
            "return BLOCKED with the missing file path in risk_points.\n"
            f"READ ALLOWLIST: {json.dumps(allowed_files, ensure_ascii=False)}\n\n"
            "Return exactly one compact JSON object matching the required report schema. Do not "
            "echo this prompt, the task, file contents, diffs, reasoning, or logs.\n\n"
            f"{task}"
        )

    def _validate_worker_report(self, stdout: str) -> str:
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise OrchestratorError("Antigravity stdout must contain only one JSON object") from exc
        # Antigravity `--output-format json` wraps the schema-constrained answer
        # with conversation, usage, echoed schema and a duplicate response. Only
        # the validated `structured_output` is allowed past this boundary.
        # A completed model turn can still have a verbose transport error while
        # closing the request; a valid structured_output is authoritative.
        report = envelope.get("structured_output") if isinstance(envelope, dict) else None
        if report is None:
            max_stdout = int(self.config.get("worker_stdout_max_chars", 4000))
            if len(stdout) > max_stdout:
                raise OrchestratorError(
                    f"Antigravity report exceeds {max_stdout} characters; verbose output is rejected"
                )
            report = envelope
        required = set(self.WORKER_REPORT_SCHEMA["required"])
        if not isinstance(report, dict) or set(report) != required:
            raise OrchestratorError("Antigravity report fields do not match the compact contract")
        if report["status"] not in {"SUCCESS", "PARTIAL", "FAIL", "BLOCKED"}:
            raise OrchestratorError("Antigravity report has an invalid status")
        test_result = report["test_result"]
        required_tests = {"lint", "typecheck", "unit_tests", "failed_cases"}
        if not isinstance(test_result, dict) or set(test_result) != required_tests:
            raise OrchestratorError("Antigravity test_result fields do not match the compact contract")
        outcomes = {"pass", "fail", "not_applicable"}
        if any(test_result[key] not in outcomes for key in ("lint", "typecheck", "unit_tests")):
            raise OrchestratorError("Antigravity report has an invalid test outcome")
        if not all(isinstance(report[key], list) for key in ("diff_files", "risk_points")):
            raise OrchestratorError("Antigravity report path and risk fields must be arrays")
        if not isinstance(test_result["failed_cases"], list):
            raise OrchestratorError("Antigravity failed_cases must be an array")
        max_summary = int(self.config.get("worker_summary_max_chars", 200))
        if not isinstance(report["summary"], str) or len(report["summary"]) > max_summary:
            raise OrchestratorError(
                f"Antigravity summary exceeds {max_summary} Unicode characters"
            )
        compact = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        max_stdout = int(self.config.get("worker_stdout_max_chars", 4000))
        if len(compact) > max_stdout:
            raise OrchestratorError(
                f"Antigravity compact report exceeds {max_stdout} characters"
            )
        return compact

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

    def _setup_worker_environment(self) -> dict[str, str]:
        worker_env = os.environ.copy()
        proxy = self.config.get("worker_proxy", "").strip()
        if proxy:
            worker_env.update({
                "HTTP_PROXY": proxy,
                "HTTPS_PROXY": proxy,
                "ALL_PROXY": proxy,
            })

        # 专职 Headless Worker 特殊模式（通过配置开关 worker_profile 自由切换，日常终端完全不影响）
        if self.config.get("worker_profile") == "headless_lean":
            profile_dir = self.hub.hub / ".worker_profile"
            gemini_dir = profile_dir / ".gemini"
            gemini_dir.mkdir(parents=True, exist_ok=True)
            real_home_str = os.environ.get("USERPROFILE") or os.environ.get("HOME", "")
            if real_home_str:
                real_gemini = Path(real_home_str) / ".gemini"
                if real_gemini.is_dir():
                    auth_files = [
                        "oauth_creds.json", "google_accounts.json", "installation_id",
                        "state.json", "settings.json"
                    ]
                    for filename in auth_files:
                        src = real_gemini / filename
                        dst = gemini_dir / filename
                        if src.is_file():
                            try:
                                if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                                    shutil.copy2(src, dst)
                            except Exception:
                                pass
            worker_env["USERPROFILE"] = str(profile_dir)
            worker_env["HOME"] = str(profile_dir)
        return worker_env

    @staticmethod
    def _tool_activity_counts(log_text: str) -> tuple[int, int, int]:
        """Return total reads, writes, and consecutive reads since the last write."""
        read_pattern = re.compile(
            r'(?:tool confirmation|tool call).*?"?'
            r'(ViewFile|ReadFile|ListDir|FindFiles|GrepSearch|Search)' r'"?',
            re.IGNORECASE,
        )
        write_pattern = re.compile(
            r'(?:file write|tool confirmation|tool call).*?"?'
            r'(WriteToFile|Replace|Edit|MultiReplace)' r'"?',
            re.IGNORECASE,
        )
        events = [(match.start(), "read") for match in read_pattern.finditer(log_text)]
        events.extend((match.start(), "write") for match in write_pattern.finditer(log_text))
        reads = writes = reads_since_write = 0
        for _, kind in sorted(events):
            if kind == "write":
                writes += 1
                reads_since_write = 0
            else:
                reads += 1
                reads_since_write += 1
        return reads, writes, reads_since_write

    def _write_worker_heartbeat(
        self,
        artifact_dir: Path,
        *,
        status: str,
        elapsed: float,
        reads: int,
        writes: int,
        reads_since_write: int,
        detail: str = "",
    ) -> None:
        payload = {
            "status": status,
            "elapsed_seconds": round(elapsed, 1),
            "readonly_tool_calls": reads,
            "write_tool_calls": writes,
            "readonly_calls_since_write": reads_since_write,
            "detail": detail[:300],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(
            artifact_dir / "worker_heartbeat.json",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _stop_worker(process: subprocess.Popen[str]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _run_worker_monitored(
        self,
        args: Sequence[str],
        log_path: Path,
        artifact_dir: Path,
        worker_env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        """Run Antigravity with enforceable timeout/read-budget/no-activity gates."""
        log_path.unlink(missing_ok=True)
        timeout_seconds = int(self.config.get("worker_timeout_seconds", 240))
        read_budget = int(self.config.get("worker_max_readonly_tool_calls", 12))
        idle_timeout = int(self.config.get("worker_no_activity_timeout_seconds", 60))
        poll_seconds = max(float(self.config.get("worker_monitor_interval_seconds", 1.0)), 0.05)
        started = time.monotonic()
        last_activity = started
        last_log_size = -1
        reason = ""
        reads = writes = reads_since_write = 0

        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout_file, tempfile.TemporaryFile(
            mode="w+", encoding="utf-8"
        ) as stderr_file:
            process = self.popen_factory(
                list(args),
                cwd=self.root,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=stdout_file,
                stderr=stderr_file,
                env=worker_env,
            )
            while process.poll() is None:
                now = time.monotonic()
                if log_path.exists():
                    log_size = log_path.stat().st_size
                    if log_size != last_log_size:
                        last_log_size = log_size
                        last_activity = now
                    log_text = log_path.read_text(encoding="utf-8", errors="replace")
                    reads, writes, reads_since_write = self._tool_activity_counts(log_text)
                elapsed = now - started
                self._write_worker_heartbeat(
                    artifact_dir,
                    status="RUNNING",
                    elapsed=elapsed,
                    reads=reads,
                    writes=writes,
                    reads_since_write=reads_since_write,
                )
                if read_budget > 0 and reads_since_write >= read_budget:
                    reason = (
                        f"readonly tool budget exceeded: {reads_since_write}/{read_budget} "
                        "consecutive reads without a write"
                    )
                elif timeout_seconds > 0 and elapsed >= timeout_seconds:
                    reason = f"hard timeout reached: {timeout_seconds}s"
                elif idle_timeout > 0 and now - last_activity >= idle_timeout:
                    reason = f"no Antigravity log activity for {idle_timeout}s"
                if reason:
                    self._stop_worker(process)
                    break
                time.sleep(poll_seconds)

            returncode = process.wait()
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read()

        elapsed = time.monotonic() - started
        status = "ABORTED" if reason else ("SUCCESS" if returncode == 0 else "FAILED")
        self._write_worker_heartbeat(
            artifact_dir,
            status=status,
            elapsed=elapsed,
            reads=reads,
            writes=writes,
            reads_since_write=reads_since_write,
            detail=reason,
        )
        if reason:
            returncode = 124
            stderr = (stderr.rstrip() + f"\nWorker aborted: {reason}\n").lstrip("\n")
        return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)

    def _run_worker_attempt(
        self,
        args: Sequence[str],
        log_path: Path,
        artifact_dir: Path,
        worker_env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        # Injected runners keep unit tests deterministic; production uses the hard monitor.
        if self.runner is not subprocess.run:
            return self._run(
                args,
                timeout=int(self.config.get("worker_timeout_seconds", 240)) + 30,
                env=worker_env,
            )
        return self._run_worker_monitored(args, log_path, artifact_dir, worker_env)

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
        worker_env = self._setup_worker_environment()
        for index, model in enumerate(models, start=1):
            safe_model = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model or "default")
            log_path = artifact_dir / f"antigravity_{index}_{safe_model}.log"
            args = [
                self.config["antigravity_executable"],
                f"--print={prompt}",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(self.WORKER_REPORT_SCHEMA, ensure_ascii=False, separators=(",", ":")),
                "--disable-slash-commands",
                "--mode",
                worker_mode,
                "--sandbox",
                "--print-timeout",
                f"{int(self.config.get('worker_timeout_seconds', 1800))}s",
                "--log-file",
                str(log_path),
            ]
            if model:
                args.extend(("--model", model))
            else:
                args.extend(("--effort", self.config.get("worker_effort", "medium")))
            if auto_approve:
                # Antigravity requires this even for ListDir in print mode. The
                # terminal sandbox and post-run scope enforcement remain mandatory.
                args.append("--dangerously-skip-permissions")
            result = self._run_worker_attempt(args, log_path, artifact_dir, worker_env)
            attempts.append(result)
            self._write(
                artifact_dir / f"worker_attempt_{index}_{safe_model}.stdout", result.stdout
            )
            self._write(
                artifact_dir / f"worker_attempt_{index}_{safe_model}.stderr", result.stderr
            )
            if self._is_transient_auth_failure(result):
                retry = self._run_worker_attempt(args, log_path, artifact_dir, worker_env)
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
                try:
                    compact = self._validate_worker_report(result.stdout.strip())
                except OrchestratorError as exc:
                    result = subprocess.CompletedProcess(
                        result.args, 2, "", f"Compact report rejected: {exc}"
                    )
                    attempts[-1] = result
                else:
                    return subprocess.CompletedProcess(result.args, 0, compact, result.stderr)
        last = attempts[-1]
        combined_error = "\n\n".join(
            f"Attempt {index} ({models[min(index - 1, len(models) - 1)] or 'default'}):\n{item.stderr}"
            for index, item in enumerate(attempts, start=1)
        )
        return subprocess.CompletedProcess(last.args, last.returncode, last.stdout, combined_error)

    @staticmethod
    def _compact_verification_text(raw_text: str, max_lines_per_command: int = 15) -> str:
        blocks: list[str] = []
        for block in raw_text.split("\n\n"):
            lines = [line for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            cmd_lines = [l for l in lines if l.startswith("$ ") or l.startswith("exit=")]
            summary_lines = [
                l for l in lines
                if not l.startswith("$ ")
                and not l.startswith("exit=")
                and not re.match(r"^[\.sFExX]+(\s+\[\s*\d+%\])?$", l.strip())
            ]
            trimmed = cmd_lines + summary_lines[-max_lines_per_command:]
            blocks.append("\n".join(trimmed))
        return "\n\n".join(blocks)

    def _compact_diff(self, changed_paths: Iterable[str]) -> str:
        max_lines = int(self.config.get("max_review_diff_lines", 150))
        max_chars = int(self.config.get("max_review_diff_chars", 12000))
        code_paths = [
            p for p in changed_paths
            if not p.startswith(".agent_hub/artifacts/") and not p.endswith(".log")
        ]
        if not code_paths:
            return ""
        cmd = ["git", "diff", "--stat", "--"] + code_paths
        stat_res = self._run(cmd, timeout=30)
        stat_text = stat_res.stdout.strip() if stat_res.returncode == 0 else ""

        diff_cmd = ["git", "diff", "--no-color", "--"] + code_paths
        diff_res = self._run(diff_cmd, timeout=30)
        if diff_res.returncode != 0 or not diff_res.stdout.strip():
            return stat_text
        diff_lines = diff_res.stdout.splitlines()
        if len(diff_lines) > max_lines:
            truncated = diff_lines[:max_lines] + [f"... truncated {len(diff_lines) - max_lines} lines ..."]
            diff_body = "\n".join(truncated)
        else:
            diff_body = "\n".join(diff_lines)
        compact = (stat_text + "\n\n" + diff_body).strip()
        if max_chars > 0 and len(compact) > max_chars:
            omitted = len(compact) - max_chars
            compact = compact[:max_chars].rstrip() + f"\n... truncated {omitted} characters ..."
        return compact

    def _review_profile(self, stage: str) -> dict[str, str]:
        profiles = self.config.get("review_profiles", {})
        defaults = {
            "task_review": {"model": "", "effort": "low"},
            "p_checkpoint_review": {"model": "", "effort": "medium"},
            "release_gate": {"model": "", "effort": "high"},
        }
        profile = dict(defaults.get(stage, defaults["task_review"]))
        profile.update(profiles.get(stage, {}))
        if stage == "task_review" and str(profile.get("effort", "")).lower() == "high":
            if self.config.get("review_quota_policy", {}).get("forbid_high_for_task_review", True):
                raise OrchestratorError("High reasoning is forbidden for ordinary task_review")
        return {k: str(v) for k, v in profile.items()}

    def _invoke_reviewer(
        self,
        task_text: str,
        artifact_dir: Path,
        verification: str,
        scope: str,
        compact_diff: str = "",
        stage: str = "task_review",
        output_name: str = "codex_review.md",
        extra_rules: str = "",
    ) -> subprocess.CompletedProcess[str]:
        review_rules = (self.hub.hub / "review_prompt.md").read_text(encoding="utf-8")
        compact_verification = self._compact_verification_text(verification)
        prompt_parts = [
            review_rules,
            f"## REVIEW STAGE\n{stage}",
            extra_rules.strip(),
            f"## TASK / CHECKPOINT CONTEXT\n{task_text}",
            f"## ORCHESTRATOR VERIFICATION\n{compact_verification}",
            f"## SCOPE CHECK\n{scope}",
        ]
        if compact_diff.strip():
            prompt_parts.append(
                f"## COMPACT DIFF EVIDENCE\n"
                f"> [!NOTE] Orchestrator provided compact diff evidence. Avoid running redundant unconstrained git diff.\n"
                f"{compact_diff.strip()}"
            )
        prompt = "\n\n".join(part for part in prompt_parts if part)

        cmd = [
            self.config["codex_executable"],
            "exec",
            "--sandbox",
            "read-only",
            "--config",
            'approval_policy="never"',
            "--cd",
            str(self.root),
            "--ephemeral",
        ]
        profile = self._review_profile(stage)
        if profile.get("model"):
            cmd.extend(["--model", profile["model"]])
        if profile.get("effort"):
            cmd.extend(["--config", f'model_reasoning_effort="{profile["effort"]}"'])

        cmd.extend([
            "--output-last-message",
            str(artifact_dir / output_name),
            "-",
        ])
        return self._run(
            cmd,
            input=prompt,
            timeout=int(self.config.get("review_timeout_seconds", 900)),
        )

    def _run_reviewer_fresh(
        self,
        task_text: str,
        artifact_dir: Path,
        verification: str,
        scope: str,
        compact_diff: str,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        """Run a reviewer and never accept a review artifact from an older run."""
        review_file = artifact_dir / "codex_review.md"
        review_file.unlink(missing_ok=True)
        started_ns = time.time_ns()
        reviewer = self._invoke_reviewer(
            task_text, artifact_dir, verification, scope, compact_diff,
            stage="task_review", output_name="codex_review.md"
        )
        is_fresh = (
            review_file.exists()
            and review_file.stat().st_mtime_ns >= started_ns
        )
        if reviewer.returncode == 0 and is_fresh:
            return reviewer, review_file.read_text(encoding="utf-8")
        if reviewer.returncode == 0:
            reviewer = subprocess.CompletedProcess(
                reviewer.args,
                2,
                reviewer.stdout,
                (reviewer.stderr.rstrip() + "\nReviewer did not create a fresh codex_review.md\n").lstrip(),
            )
        return reviewer, reviewer.stdout

    @staticmethod
    def _verification_succeeded(verification_text: str) -> bool:
        exit_codes = re.findall(r"(?m)^exit=(-?\d+)\s*$", verification_text)
        return bool(exit_codes) and all(code == "0" for code in exit_codes)

    @staticmethod
    def _scope_succeeded(scope_text: str) -> bool:
        return bool(re.search(r"(?m)^Scope: PASS\s*$", scope_text)) and not bool(
            re.search(r"(?m)^Violations:\s*$", scope_text)
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

    def execute(
        self,
        task_id: str | None = None,
        parallel_owned_patterns: Sequence[str] = (),
    ) -> RunReport:
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
        with self._claim_lock:
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
        active_parallel = list(parallel_owned_patterns) + self._parallel_owned_patterns(selected)
        violations = self._scope_violations(task_text, changed, active_parallel)
        scope_text = f"Scope: {'PASS' if not violations else 'FAIL'}\n\nChanged paths:\n" + "\n".join(sorted(changed))
        if violations:
            scope_text += "\n\nViolations:\n" + "\n".join(violations)
        self._write(artifact_dir / "scope_check.md", scope_text)

        compact_diff = self._compact_diff(changed)
        summary = (
            f"Worker exit=0; verification={'PASS' if verification_ok else 'FAIL'}; "
            f"scope={'PASS' if not violations else 'FAIL'}"
        )
        self.hub.submit(selected, "orchestrator/antigravity", summary)

        decision = "REWORK"
        review_text = "Automated Codex review was not run."
        if self.config.get("auto_review", True):
            reviewer, review_text = self._run_reviewer_fresh(
                task_text, artifact_dir, verification_text, scope_text, compact_diff
            )
            self._write(artifact_dir / "codex_review_stderr.log", reviewer.stderr)
            if reviewer.returncode == 0 and re.search(r"^DECISION: APPROVED\s*$", review_text, re.MULTILINE):
                decision = "APPROVED"
        if not verification_ok or violations:
            decision = "REWORK"

        max_rework = int(self.config.get("max_rework_cycles", 1))
        rework_count = self.hub.get_rework_count(selected)
        if decision == "REWORK" and rework_count >= max_rework:
            decision = "REWORK_BLOCKED_FOR_HUMAN"
            hub_decision = "rework_blocked"
            rework_msg = (
                f"Rework limit reached ({rework_count}/{max_rework}); automated rework blocked for human intervention.\n\n"
                + (review_text or summary)
            )
            self.hub.review(
                selected,
                hub_decision,
                "codex/orchestrator",
                rework_msg,
            )
        else:
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

    def _task_approved(self, task_id: str) -> bool:
        normalized = task_id.zfill(3)
        review = self.hub.hub / "review" / f"{normalized}_review.md"
        if not review.exists():
            return False
        return "- Decision: APPROVED" in review.read_text(encoding="utf-8")

    def runnable_tasks(
        self,
        limit: int | None = None,
        task_ids: Sequence[str] | None = None,
    ) -> list[str]:
        limit = limit or int(self.config.get("batch_default_workers", 2))
        requested = {str(item).zfill(3) for item in (task_ids or [])}
        candidates: list[str] = []
        owned: list[str] = []
        for path in self.hub._task_files("inbox"):
            match = re.match(r"(\d{3,})_", path.name)
            if not match:
                continue
            task_id = match.group(1)
            if requested and task_id not in requested:
                continue
            blockers = self.hub.claim_blockers(task_id)
            blockers = [item for item in blockers if not item.startswith("running-limit:")]
            if blockers:
                continue
            text = path.read_text(encoding="utf-8")
            files = self._section_items(text, "Files Allowed")
            if any(
                self.hub._patterns_overlap(candidate, current)
                for candidate in files for current in owned
            ):
                continue
            candidates.append(task_id)
            owned.extend(files)
            if len(candidates) >= limit:
                break
        return candidates

    def execute_batch(
        self,
        max_workers: int | None = None,
        task_ids: Sequence[str] | None = None,
    ) -> list[RunReport]:
        configured_max = int(self.config.get("batch_max_workers", 3))
        workers = max_workers or int(self.config.get("batch_default_workers", 2))
        workers = max(1, min(workers, configured_max))
        selected = self.runnable_tasks(workers, task_ids=task_ids)
        if not selected:
            return []
        owned_by_task: dict[str, list[str]] = {}
        for task_id in selected:
            task_path = self.hub.locate(task_id, ("inbox",)).path
            owned_by_task[task_id] = self._section_items(
                task_path.read_text(encoding="utf-8"), "Files Allowed"
            )
        reports: list[RunReport] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agent-hub") as pool:
            futures = {}
            for task_id in selected:
                sibling_owned = [
                    pattern
                    for other_id, patterns in owned_by_task.items()
                    if other_id != task_id
                    for pattern in patterns
                ]
                futures[pool.submit(self.execute, task_id, sibling_owned)] = task_id
            for future in as_completed(futures):
                reports.append(future.result())
        return sorted(reports, key=lambda item: item.task_id)

    def _checkpoint_evidence(self, task_ids: Sequence[str]) -> tuple[str, list[str]]:
        blocks: list[str] = []
        missing: list[str] = []
        for task_id in task_ids:
            normalized = task_id.zfill(3)
            if not self._task_approved(normalized):
                missing.append(normalized)
                continue
            merge = self.hub.hub / "decisions" / f"{normalized}_merge_report.md"
            review = self.hub.hub / "review" / f"{normalized}_review.md"
            blocks.append(
                f"### Task {normalized}\n"
                + (merge.read_text(encoding="utf-8") if merge.exists() else "merge report missing")
                + "\n"
                + review.read_text(encoding="utf-8")
            )
        return "\n\n".join(blocks), missing

    def checkpoint_review(self, node: str, task_ids: Sequence[str]) -> RunReport:
        node = re.sub(r"[^A-Za-z0-9_.-]+", "_", node)
        evidence, missing = self._checkpoint_evidence(task_ids)
        artifact_dir = self.hub.hub / "checkpoints" / node
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if missing:
            hold = "未进入 Medium 审查：以下任务尚未 APPROVED：" + ", ".join(missing)
            self._write(artifact_dir / "P_CHECKPOINT_REVIEW.md", hold + "\n")
            return RunReport(node, "CHECKPOINT_HOLD", artifact_dir, hold)
        rules = (
            "这是 P 节点 Final Review，不是普通任务审查。请用中文综合所有已批准任务，"
            "检查跨任务契约、回归证据、风险和回滚边界。不要重新实现代码。"
            "结尾必须是 DECISION: APPROVED 或 DECISION: REWORK。"
        )
        reviewer = self._invoke_reviewer(
            f"P节点: {node}\n任务: {', '.join(task_ids)}",
            artifact_dir,
            evidence,
            "Scope: PASS",
            stage="p_checkpoint_review",
            output_name="P_CHECKPOINT_REVIEW.md",
            extra_rules=rules,
        )
        review_path = artifact_dir / "P_CHECKPOINT_REVIEW.md"
        review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else reviewer.stdout
        approved = reviewer.returncode == 0 and bool(
            re.search(r"^DECISION: APPROVED\s*$", review_text, re.MULTILINE)
        )
        status = "CHECKPOINT_APPROVED" if approved else "CHECKPOINT_REWORK"
        commit_message = (
            f"checkpoint({node}): 完成P节点复核与版本冻结准备\n\n"
            f"- tasks: {', '.join(task_ids)}\n"
            f"- review: {status}\n"
            "- 自动合并: OFF\n- 自动实盘: OFF\n"
        )
        self._write(artifact_dir / "COMMIT_MESSAGE_ZH.txt", commit_message)
        version = (
            f"# {node} 中文版本报告\n\n"
            f"## 1. 节点目标\n完成 {node} 所含任务的工程级收敛、测试证据汇总与独立复核。\n\n"
            f"## 2. 纳入任务\n{', '.join(task_ids)}\n\n"
            f"## 3. 修改前问题与背景\n由各任务 Context 与本节点 Final Review 共同定义，禁止脱离任务书扩大范围。\n\n"
            f"## 4. 关键变化\n汇总节点内已 APPROVED 的实现；具体行为变化以各任务 merge report、review 和 compact diff 为准。\n\n"
            f"## 5. 行为影响\n仅接受已经通过任务级验证的行为变化；跨任务契约冲突由本次 Medium Final Review 仲裁。\n\n"
            f"## 6. 风控边界\n不自动合并、不自动发布、不打开真实交易权限；P5_FORBIDDEN 仍需人工批准。\n\n"
            f"## 7. 测试与范围证据\n所有进入本节点的任务必须先独立 APPROVED；详细证据见 verification、scope_check、merge report。\n\n"
            f"## 8. 修改文件\n以各任务 changed_files 与 Files Allowed 的并集为准；同一文件并发写已由 Hub 文件所有权门阻断。\n\n"
            f"## 9. 回滚方案\n按各任务 Rollback 逆序执行；禁止覆盖其他 Agent 或用户已存在改动。\n\n"
            f"## 10. 已知风险\n由任务 risk_points 与 P节点 Final Review 汇总；未解决 P0/P1 问题时不得进入 Release Gate。\n\n"
            f"## 11. P节点 Final Review\n{review_text.strip()}\n\n"
            f"## 12. Git 版本记录\n见 COMMIT_MESSAGE_ZH.txt；真实 commit/tag 必须显式执行，自动提交保持关闭。\n"
        )
        self._write(artifact_dir / "VERSION_REPORT_ZH.md", version)
        return RunReport(node, status, artifact_dir, f"{node} checkpoint review completed")

    def release_gate(self, release: str, checkpoints: Sequence[str]) -> RunReport:
        release = re.sub(r"[^A-Za-z0-9_.-]+", "_", release)
        artifact_dir = self.hub.hub / "releases" / release
        artifact_dir.mkdir(parents=True, exist_ok=True)
        evidence: list[str] = []
        missing: list[str] = []
        for node in checkpoints:
            path = self.hub.hub / "checkpoints" / node / "P_CHECKPOINT_REVIEW.md"
            if not path.exists():
                missing.append(node)
                continue
            text = path.read_text(encoding="utf-8")
            if not re.search(r"^DECISION: APPROVED\s*$", text, re.MULTILINE):
                missing.append(node)
                continue
            evidence.append(f"## {node}\n{text}")
        if missing:
            msg = "Release Gate HOLD：P节点未全部通过：" + ", ".join(missing)
            self._write(artifact_dir / "RELEASE_GATE.md", msg + "\n")
            return RunReport(release, "RELEASE_HOLD", artifact_dir, msg)
        rules = (
            "这是最终 Release Gate。仅做发布门禁与跨P节点风险仲裁，使用中文。"
            "检查证据完整性、回滚、禁止项和是否存在阻断项；不要修改代码。"
            "结尾必须是 DECISION: APPROVED 或 DECISION: REWORK。"
        )
        reviewer = self._invoke_reviewer(
            f"Release: {release}\nCheckpoints: {', '.join(checkpoints)}",
            artifact_dir,
            "\n\n".join(evidence),
            "Scope: PASS",
            stage="release_gate",
            output_name="RELEASE_GATE.md",
            extra_rules=rules,
        )
        gate_path = artifact_dir / "RELEASE_GATE.md"
        gate_text = gate_path.read_text(encoding="utf-8") if gate_path.exists() else reviewer.stdout
        approved = reviewer.returncode == 0 and bool(
            re.search(r"^DECISION: APPROVED\s*$", gate_text, re.MULTILINE)
        )
        status = "RELEASE_GO" if approved else "RELEASE_NO_GO"
        self._write(
            artifact_dir / "RELEASE_RECORD_ZH.md",
            f"# {release} 发布门禁记录\n\n"
            f"- 状态: {status}\n"
            f"- P节点: {', '.join(checkpoints)}\n"
            "- 自动合并: OFF\n- 自动 Tag: OFF\n- 真实交易权限: 未变更\n\n"
            + gate_text,
        )
        return RunReport(release, status, artifact_dir, "Release gate completed")

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
        verification_ok = self._verification_succeeded(verification_text)
        scope_ok = self._scope_succeeded(scope_text)
        self.hub.submit(
            selected,
            "orchestrator/re-review",
            f"Reused evidence; verification={'PASS' if verification_ok else 'FAIL'}; "
            f"scope={'PASS' if scope_ok else 'FAIL'}",
        )
        task_files = self._section_items(task_text, "Files Allowed")
        compact_diff = self._compact_diff(task_files)
        reviewer, review_text = self._run_reviewer_fresh(
            task_text, artifact_dir, verification_text, scope_text, compact_diff
        )
        self._write(artifact_dir / "codex_review_stderr.log", reviewer.stderr)
        approved = (
            reviewer.returncode == 0
            and verification_ok
            and scope_ok
            and bool(re.search(r"^DECISION: APPROVED\s*$", review_text, re.MULTILINE))
        )
        decision = "APPROVED" if approved else "REWORK"
        max_rework = int(self.config.get("max_rework_cycles", 1))
        rework_count = self.hub.get_rework_count(selected)
        if decision == "REWORK" and rework_count >= max_rework:
            decision = "REWORK_BLOCKED_FOR_HUMAN"
            hub_decision = "rework_blocked"
            rework_msg = (
                f"Rework limit reached ({rework_count}/{max_rework}); automated rework blocked for human intervention.\n\n"
                + review_text
            )
            self.hub.review(selected, hub_decision, "codex/orchestrator", rework_msg)
        else:
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
    batch = sub.add_parser("run-batch")
    batch.add_argument("--execute", action="store_true")
    batch.add_argument("--max-workers", type=int)
    batch.add_argument("--tasks", nargs="+")
    checkpoint = sub.add_parser("checkpoint-review")
    checkpoint.add_argument("--node", required=True)
    checkpoint.add_argument("--tasks", nargs="+", required=True)
    release = sub.add_parser("release-gate")
    release.add_argument("--release", required=True)
    release.add_argument("--checkpoints", nargs="+", required=True)
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
        elif args.command == "checkpoint-review":
            report = orchestrator.checkpoint_review(args.node, args.tasks)
        elif args.command == "release-gate":
            report = orchestrator.release_gate(args.release, args.checkpoints)
        elif args.command == "run-batch":
            if not args.execute:
                selected = orchestrator.runnable_tasks(args.max_workers, task_ids=args.tasks)
                print(json.dumps({"runnable_tasks": selected}, ensure_ascii=False, indent=2))
                return 0
            reports = orchestrator.execute_batch(args.max_workers, task_ids=args.tasks)
            print(json.dumps([{
                "task_id": item.task_id,
                "status": item.status,
                "artifact_dir": str(item.artifact_dir),
                "message": item.message,
            } for item in reports], ensure_ascii=False, indent=2))
            return 0
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

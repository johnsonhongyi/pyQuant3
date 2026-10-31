"""Resolve explicitly configured CLI entry points across supported hosts."""

from __future__ import annotations

from ats.llm.path_utils import safe_resolve_path

import os
import shutil
import re
from pathlib import Path
from typing import Any


def resolve_cli_path(value: Any, executable_name: str) -> str:
    """Return an existing CLI path, including AGY's standard Windows install."""
    configured = value.strip() if isinstance(value, str) else ""
    if configured:
        expanded = os.path.expandvars(configured)
        candidate = Path(expanded).expanduser()
        if candidate.is_file():
            return str(safe_resolve_path(candidate))
        if not any(separator in configured for separator in ("/", "\\")) and not candidate.suffix:
            found = shutil.which(configured)
            if found:
                return str(safe_resolve_path(Path(found)))
        else:
            return ""

    if executable_name == "agy":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            agy_bin = Path(local_app_data) / "agy" / "bin"
            for candidate in (agy_bin / "agy.exe", agy_bin / "agy.ps1"):
                if candidate.is_file():
                    return str(safe_resolve_path(candidate))
    if executable_name == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        candidates = [codex_home / "packages" / package / "current" / "bin" / "codex.exe"
                      for package in ("app-server-daemon", "standalone")]
        available = []
        for candidate in candidates:
            try:
                if not candidate.is_file():continue
                resolved = safe_resolve_path(candidate)
                version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)-x86_64-pc-windows-msvc", resolved.parent.parent.name)
                available.append((tuple(map(int, version.groups())) if version else (0,0,0), str(resolved)))
            except OSError:
                continue  # An updater may replace a junction during discovery.
        if available:
            return max(available, key=lambda item:item[0])[1]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            installed = Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if installed.is_file():
                return str(safe_resolve_path(installed))
            base = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            direct = base / "codex.exe"
            if direct.is_file():
                return str(safe_resolve_path(direct))
            try:
                candidates = [path for path in base.glob("*\\codex.exe") if path.is_file()]
                if candidates:
                    newest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
                    return str(safe_resolve_path(newest))
            except OSError:
                pass
    found = shutil.which(executable_name)
    return str(safe_resolve_path(Path(found))) if found else ""

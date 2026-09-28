"""Resolve explicitly configured CLI entry points across supported hosts."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def resolve_cli_path(value: Any, executable_name: str) -> str:
    """Return an existing CLI path, including AGY's standard Windows install."""
    configured = value.strip() if isinstance(value, str) else ""
    if configured:
        expanded = os.path.expandvars(configured)
        candidate = Path(expanded).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        if not any(separator in configured for separator in ("/", "\\")) and not candidate.suffix:
            found = shutil.which(configured)
            if found:
                return str(Path(found).resolve())
        else:
            return ""

    if executable_name == "agy":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            agy_bin = Path(local_app_data) / "agy" / "bin"
            for candidate in (agy_bin / "agy.exe", agy_bin / "agy.ps1"):
                if candidate.is_file():
                    return str(candidate.resolve())
    if executable_name == "codex":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            direct = base / "codex.exe"
            if direct.is_file():
                return str(direct.resolve())
            try:
                candidates = [path for path in base.glob("*\\codex.exe") if path.is_file()]
                if candidates:
                    newest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
                    return str(newest.resolve())
            except OSError:
                pass
    found = shutil.which(executable_name)
    return str(Path(found).resolve()) if found else ""

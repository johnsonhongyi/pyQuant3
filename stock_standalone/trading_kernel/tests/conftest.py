from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _usable_temp_dir(raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_dir():
            return None
        candidate.resolve()
        if not os.access(str(candidate), os.W_OK):
            return None
        return candidate
    except (OSError, RuntimeError):
        return None


def _ensure_windows_temp_fallback() -> None:
    if os.name != "nt":
        return

    configured = _usable_temp_dir(os.environ.get("TEMP"))
    configured = configured or _usable_temp_dir(os.environ.get("TMP"))
    if configured is not None:
        return

    base = os.environ.get("LOCALAPPDATA")
    fallback = Path(base) / "Temp" if base else Path.home() / "AppData" / "Local" / "Temp"
    fallback.mkdir(parents=True, exist_ok=True)
    fallback = fallback.resolve()

    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(fallback)
    tempfile.tempdir = str(fallback)


_ensure_windows_temp_fallback()

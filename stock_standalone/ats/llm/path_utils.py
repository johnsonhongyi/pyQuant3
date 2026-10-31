"""CLI path handling without initializing desktop logging or configuration."""
from pathlib import Path


def safe_resolve_path(path):
    candidate=Path(path)
    try:
        return candidate.resolve()
    except OSError:
        return candidate.absolute()

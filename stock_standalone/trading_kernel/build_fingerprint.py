from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_kernel.contracts import KERNEL_API_VERSION

DEFAULT_OUTPUT_PATH = Path(".agent_hub") / "artifacts" / "BUILD_FINGERPRINT.json"


class DirtyWorkingTreeError(RuntimeError):
    """Raised when release fingerprint generation is attempted on a dirty git tree."""
    pass


def _git_value(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def build_fingerprint(
    kernel_version: str,
    repo_root: Path | str | None = None,
    *,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
    require_clean: bool = False,
    release_mode: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    commit = git_commit if git_commit is not None else (_git_value(root, "rev-parse", "HEAD") or "unknown")
    dirty = bool(git_dirty) if git_dirty is not None else bool(_git_value(root, "status", "--porcelain"))
    release_ready = bool((not dirty) and commit and commit != "unknown")

    is_release = bool(require_clean or release_mode)
    if is_release and dirty:
        raise DirtyWorkingTreeError(
            "Cannot generate release build fingerprint: git working tree has uncommitted changes"
        )
    if is_release and (not commit or commit == "unknown"):
        raise DirtyWorkingTreeError(
            "Cannot generate release build fingerprint: unable to resolve git commit HEAD"
        )

    identity = {
        "api_version": KERNEL_API_VERSION,
        "git_commit": commit,
        "git_dirty": dirty,
        "kernel_version": str(kernel_version),
        "release_ready": release_ready,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return {
        **identity,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def collect_build_fingerprint(
    repo_root: Path | str | None = None,
    *,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
    require_clean: bool = False,
    release_mode: bool = False,
) -> dict[str, Any]:
    from trading_kernel.kernel_service import TradingKernelService
    return build_fingerprint(
        TradingKernelService.KERNEL_VERSION,
        repo_root=repo_root,
        git_commit=git_commit,
        git_dirty=git_dirty,
        require_clean=require_clean,
        release_mode=release_mode,
    )


def write_build_fingerprint(
    output_path: Path | str | None = None,
    repo_root: Path | str | None = None,
    kernel_version: str | None = None,
    *,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
    require_clean: bool = False,
    release_mode: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    target_path = Path(output_path).resolve() if output_path is not None else (root / DEFAULT_OUTPUT_PATH)
    payload = (
        build_fingerprint(
            kernel_version,
            repo_root=root,
            git_commit=git_commit,
            git_dirty=git_dirty,
            require_clean=require_clean,
            release_mode=release_mode,
        )
        if kernel_version is not None
        else collect_build_fingerprint(
            repo_root=root,
            git_commit=git_commit,
            git_dirty=git_dirty,
            require_clean=require_clean,
            release_mode=release_mode,
        )
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Trading Kernel build fingerprint")
    root = Path(__file__).resolve().parents[1].resolve()
    default_output = root / DEFAULT_OUTPUT_PATH
    parser.add_argument(
        "--output",
        default=str(default_output),
        help=f"Output path for BUILD_FINGERPRINT.json (default: {default_output})",
    )
    parser.add_argument(
        "--repo-root",
        default=str(root),
        help="Repository root directory",
    )
    parser.add_argument(
        "--release",
        "--require-clean",
        "--clean-tree",
        dest="release_mode",
        action="store_true",
        help="Enforce clean working tree gate for release freeze",
    )
    parser.add_argument(
        "--git-commit",
        default=None,
        help="Explicit git commit SHA override",
    )
    parser.add_argument(
        "--git-dirty",
        dest="git_dirty",
        default=None,
        choices=["true", "false"],
        help="Explicit git dirty state override",
    )
    args = parser.parse_args(argv)
    dirty_override = None if args.git_dirty is None else (args.git_dirty.lower() == "true")
    try:
        payload = write_build_fingerprint(
            output_path=Path(args.output),
            repo_root=Path(args.repo_root),
            git_commit=args.git_commit,
            git_dirty=dirty_override,
            require_clean=args.release_mode,
        )
    except DirtyWorkingTreeError as err:
        sys.stderr.write(f"ERROR: {err}\n")
        return 1
    except Exception as err:
        sys.stderr.write(f"ERROR: {err}\n")
        return 1

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_kernel.contracts import KERNEL_API_VERSION


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
) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    commit = _git_value(root, "rev-parse", "HEAD") or "unknown"
    status = _git_value(root, "status", "--porcelain")
    identity = {
        "api_version": KERNEL_API_VERSION,
        "kernel_version": str(kernel_version),
        "git_commit": commit,
        "git_dirty": bool(status),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return {
        **identity,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def collect_build_fingerprint(repo_root: Path | None = None) -> dict[str, Any]:
    from trading_kernel.kernel_service import TradingKernelService
    return build_fingerprint(TradingKernelService.KERNEL_VERSION, repo_root=repo_root)
def write_build_fingerprint(
    output_path: Path,
    repo_root: Path | None = None,
    kernel_version: str | None = None,
) -> dict[str, Any]:
    payload = (
        build_fingerprint(kernel_version, repo_root=repo_root)
        if kernel_version is not None
        else collect_build_fingerprint(repo_root=repo_root)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Trading Kernel build fingerprint")
    parser.add_argument("--output", default=str(Path(__file__).with_name("BUILD_FINGERPRINT.json")))
    args = parser.parse_args()
    payload = write_build_fingerprint(Path(args.output))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

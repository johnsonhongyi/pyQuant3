"""桌面桥强制终止工具：优雅停止超时后，按进程树强杀卡死的桥接进程（仅 process 模式）。"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return 0


def collect_bridge_pids(runtime_dir: Path, status: dict) -> list[int]:
    """收集 bridge.pid 与 status.agent_pid，排除管理器自身。"""
    candidates = [_read_pid(Path(runtime_dir) / "bridge.pid")]
    try:
        candidates.append(int((status or {}).get("agent_pid") or 0))
    except (TypeError, ValueError):
        candidates.append(0)
    return [p for p in dict.fromkeys(candidates) if p > 0 and p != os.getpid()]


def force_kill_pids(pids: list[int]) -> list[int]:
    """taskkill /T /F 整棵进程树；返回已尝试终止的 pid。失败仅忽略，由调用方二次确认存活。"""
    killed = []
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
                    capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                os.kill(int(pid), 9)
            killed.append(pid)
        except (OSError, subprocess.SubprocessError):
            pass
    return killed


def wait_until(predicate_alive, timeout: float) -> bool:
    """等待 predicate_alive() 变 False；返回是否已退出。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not predicate_alive():
            return True
        time.sleep(0.25)
    return not predicate_alive()

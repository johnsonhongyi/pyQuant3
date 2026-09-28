# -*- coding: utf-8 -*-
"""Bounded CLI process execution with timeout and process-tree cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024
_READ_CHUNK_BYTES = 8192


class BoundedCLIError(RuntimeError):
    """Raised with a safe code when a CLI exceeds its process contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BoundedCLIResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    completed_by_predicate: bool = False


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = Path(system_root) / "System32" / "taskkill.exe"
        if taskkill.is_file():
            try:
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=3.0, check=False,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def run_bounded_cli(
    command: Sequence[str],
    *,
    cwd: str | Path,
    stdin_bytes: bytes,
    timeout_seconds: float,
    max_stdout_bytes: int = MAX_STDOUT_BYTES,
    max_stderr_bytes: int = MAX_STDERR_BYTES,
    completion_predicate: Callable[[bytes], bool] | None = None,
) -> BoundedCLIResult:
    """Run a no-shell CLI while bounding captured output and wall time."""
    if (
        not isinstance(command, (list, tuple)) or not command or len(command) > 64
        or any(not isinstance(part, str) or not part or "\x00" in part for part in command)
    ):
        raise BoundedCLIError("CLI_ARGUMENT_INVALID")
    if not isinstance(stdin_bytes, bytes):
        raise BoundedCLIError("CLI_INPUT_INVALID")
    if len(stdin_bytes) > 64 * 1024:
        raise BoundedCLIError("CLI_INPUT_TOO_LARGE")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 0 < float(timeout_seconds) <= 30.0
    ):
        raise BoundedCLIError("CLI_TIMEOUT_INVALID")
    if (
        isinstance(max_stdout_bytes, bool) or not isinstance(max_stdout_bytes, int)
        or not 1 <= max_stdout_bytes <= MAX_STDOUT_BYTES
        or isinstance(max_stderr_bytes, bool) or not isinstance(max_stderr_bytes, int)
        or not 1 <= max_stderr_bytes <= MAX_STDERR_BYTES
    ):
        raise BoundedCLIError("CLI_OUTPUT_LIMIT_INVALID")
    if not Path(cwd).is_dir():
        raise BoundedCLIError("CLI_CWD_INVALID")

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": max_stdout_bytes, "stderr": max_stderr_bytes}
    exceeded = threading.Event()
    buffer_lock = threading.Lock()
    process: subprocess.Popen[bytes] | None = None

    def capture(name: str, stream: object) -> None:
        try:
            while True:
                chunk = stream.read(_READ_CHUNK_BYTES)  # type: ignore[attr-defined]
                if not chunk:
                    return
                target = buffers[name]
                with buffer_lock:
                    remaining = limits[name] - len(target)
                    if remaining > 0:
                        target.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        exceeded.set()
        except (OSError, ValueError):
            return

    try:
        with tempfile.TemporaryFile(mode="w+b") as input_file:
            input_file.write(stdin_bytes)
            input_file.seek(0)
            kwargs = {
                "stdin": input_file,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "cwd": str(Path(cwd).resolve()),
                "shell": False,
                "bufsize": 0,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                kwargs["start_new_session"] = True
            process = subprocess.Popen(list(command), **kwargs)
            input_file.close()
            readers = [
                threading.Thread(
                    target=capture, args=(name, getattr(process, name)),
                    name=f"cli-{name}-capture", daemon=True,
                )
                for name in ("stdout", "stderr")
            ]
            for reader in readers:
                reader.start()
            deadline = time.monotonic() + float(timeout_seconds)
            failure_code = ""
            completed_by_predicate = False
            while process.poll() is None:
                if exceeded.is_set():
                    failure_code = "CLI_OUTPUT_LIMIT"
                    _terminate_process_tree(process)
                    break
                if completion_predicate is not None:
                    with buffer_lock:
                        stdout_snapshot = bytes(buffers["stdout"])
                    if completion_predicate(stdout_snapshot):
                        completed_by_predicate = True
                        _terminate_process_tree(process)
                        break
                if time.monotonic() >= deadline:
                    failure_code = "CLI_TIMEOUT"
                    _terminate_process_tree(process)
                    break
                time.sleep(0.02)
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired as exc:
                    raise BoundedCLIError("CLI_PROCESS_TREE_NOT_REAPED") from exc
            for reader in readers:
                reader.join(timeout=1.0)
            if any(reader.is_alive() for reader in readers):
                _terminate_process_tree(process)
                for stream_name in ("stdout", "stderr"):
                    stream = getattr(process, stream_name)
                    if stream is not None:
                        stream.close()
                for reader in readers:
                    reader.join(timeout=0.5)
                if any(reader.is_alive() for reader in readers):
                    raise BoundedCLIError("CLI_OUTPUT_READER_STUCK")
            if exceeded.is_set() and not failure_code:
                failure_code = "CLI_OUTPUT_LIMIT"
            if failure_code:
                raise BoundedCLIError(failure_code)
            return BoundedCLIResult(
                returncode=int(process.returncode or 0),
                stdout=bytes(buffers["stdout"]),
                stderr=bytes(buffers["stderr"]),
                completed_by_predicate=completed_by_predicate,
            )
    except BoundedCLIError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if process is not None:
            _terminate_process_tree(process)
        raise BoundedCLIError("CLI_START_OR_IO_FAILED") from exc

# -*- coding: utf-8 -*-
"""Local management UI for the independent Codex desktop bridge."""

from __future__ import annotations

import configparser
import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6 import QtCore, QtWidgets


DEFAULT_BACKEND = "http://192.168.50.60:20073"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


_STATUS_LABELS = {
    "registered": "已注册", "agent_starting": "启动中", "ready": "空闲",
    "analyzing": "处理中", "degraded": "异常（可重试）", "stopping": "正在停止",
    "stopped": "已停止", "error": "失败", "failed": "失败", "completed": "已完成",
    "success": "已完成", "pending": "等待中", "queued": "排队中",
    "already_running": "桥接已在运行", "protocol_ready": "协议握手正常",
    "agent_status_write_failed": "Agent 状态写入失败",
    "stop_request_cleanup_failed": "停止请求清理失败",
}
_RESULT_FIELD_LABELS = {
    "overall_assessment": "综合判断", "headline": "核心结论", "decision": "决策",
    "summary": "摘要", "conditions": "判断条件", "questions": "待核实问题",
    "risks": "风险提示", "evidence": "证据", "thread_id": "对话线程",
    "model": "模型", "reasoning_effort": "推理强度", "provider": "提供方",
    "error_code": "错误代码", "status": "状态", "content": "结果内容",
    "description": "说明", "response": "建议", "name": "名称", "text": "内容",
    "metric": "指标", "operator": "比较条件", "anchor_id": "参考项",
    "window": "观察区间", "source_ids": "数据源", "existing_position": "现有持仓",
    "new_position": "新计划", "mode": "方向", "horizon": "周期", "reasons": "理由",
    "next_steps": "后续步骤", "created_at": "完成时间", "completed_at": "完成时间",
}


def _status_label(status, error_code="") -> str:
    if error_code:
        return f"失败（{error_code}）"
    raw = str(status or "").strip()
    return _STATUS_LABELS.get(raw.lower(), raw or "状态未知")


def _decode_nested_json(value, depth: int = 0):
    if depth >= 5:
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return _decode_nested_json(json.loads(stripped), depth + 1)
            except (ValueError, TypeError):
                return value
    if isinstance(value, dict):
        return {str(key): _decode_nested_json(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_nested_json(item, depth + 1) for item in value]
    return value


def _localized_result(value):
    value = _decode_nested_json(value)
    if isinstance(value, dict):
        return {_RESULT_FIELD_LABELS.get(str(key), str(key)): _localized_result(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_localized_result(item) for item in value]
    return value


def _format_history_time(value, result: dict) -> str:
    candidates = (value, result.get("completed_at"), result.get("created_at"), result.get("timestamp"))
    for candidate in candidates:
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            try:
                return datetime.fromtimestamp(float(candidate)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, OSError, OverflowError):
                continue
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = datetime.fromisoformat(candidate.strip().replace("Z", "+00:00"))
                return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, OSError, OverflowError):
                continue
    return "时间未知（旧记录）"


def _friendly_error_code(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    labels = {
        "timeout": "请求超时", "timeouterror": "等待响应超时",
        "model_timeout": "模型响应超时", "rpc_timeout": "Codex 引擎通信超时",
        "connectionerror": "连接失败", "connectionrefusederror": "连接被拒绝",
    }
    return labels.get(raw.lower(), raw.replace("_", " "))


def _format_bridge_log_entry(raw_line: str) -> tuple[str, str, str]:
    line = str(raw_line or "").strip()
    if not line:
        return "", "", ""
    try:
        payload = json.loads(line)
    except (ValueError, TypeError):
        return "", line, line
    if not isinstance(payload, dict):
        return "", str(payload), line

    timestamp = _format_history_time(
        payload.get("at") or payload.get("updated_epoch") or payload.get("timestamp") or payload.get("logged_at"),
        {},
    )
    if timestamp.startswith("时间未知"):
        timestamp = ""
    status = str(payload.get("status") or "").strip()
    error_code = payload.get("error_code") or payload.get("error")
    if status:
        message = _status_label(status)
        if error_code:
            message += f"；错误：{_friendly_error_code(error_code)}"
        details = []
        if payload.get("port"):
            details.append(f"端口 {payload['port']}")
        if payload.get("job_id"):
            details.append(f"任务 {payload['job_id']}")
        if payload.get("thread_id"):
            details.append(f"Thread {payload['thread_id']}")
        if details:
            message += "；" + "；".join(details)
    else:
        message = str(payload.get("message") or payload.get("detail") or "").strip()
        if not message:
            message = json.dumps(_localized_result(payload), ensure_ascii=False, separators=(",", ":"))
        message = " ".join(message.split())[:500]

    fingerprint_payload = {
        key: value for key, value in payload.items()
        if key not in {"at", "updated_epoch", "timestamp", "logged_at"}
    }
    fingerprint = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str)
    return timestamp, message, fingerprint


def _format_bridge_logs(raw_text: str, max_lines: int = 160) -> str:
    entries = []
    for raw_line in str(raw_text or "").splitlines()[-max_lines:]:
        timestamp, message, fingerprint = _format_bridge_log_entry(raw_line)
        if not message:
            continue
        if entries and fingerprint and fingerprint == entries[-1]["fingerprint"]:
            entries[-1]["count"] += 1
            if timestamp:
                entries[-1]["timestamp"] = timestamp
        else:
            entries.append({"timestamp": timestamp, "message": message, "fingerprint": fingerprint, "count": 1})
    formatted = []
    for entry in entries:
        stamp = entry["timestamp"] or "时间未知（旧日志）"
        repeat = f"（连续重复 {entry['count']} 次）" if entry["count"] > 1 else ""
        formatted.append(f"[{stamp}] {entry['message']}{repeat}")
    return "\n".join(formatted)


def _bridge_log_status(task: dict, parent: dict, agent: dict, heartbeat_age) -> str:
    running = bool(task.get("running"))
    detail = agent.get("detail") if isinstance(agent.get("detail"), dict) else {}
    status = agent.get("status") if running else parent.get("status")
    if not status:
        status = "agent_starting" if running else "stopped"
    status_text = _status_label(status)
    error_code = detail.get("error_code") if running else parent.get("error_code")
    if error_code:
        status_text += f"；最近错误：{_friendly_error_code(error_code)}"

    updated = (agent.get("updated_epoch") or parent.get("at")) if running else (parent.get("at") or agent.get("updated_epoch"))
    updated_text = _format_history_time(updated, {}) if updated else "时间未知"
    bridge_text = "运行中" if running else "已停止"
    if running and heartbeat_age is not None:
        age_seconds = max(0, int(heartbeat_age))
        heartbeat_text = (
            f"最近心跳 {updated_text}（已过期 {age_seconds} 秒）"
            if age_seconds > 90 else f"最近心跳 {updated_text}（{age_seconds} 秒前）"
        )
    else:
        heartbeat_text = f"最近状态更新时间 {updated_text}"
    return f"最新状态：桥接{bridge_text}；后端：{status_text}；{heartbeat_text}。"


def _history_order(value, result: dict, rowid: int) -> float:
    for candidate in (value, result.get("completed_at"), result.get("created_at"), result.get("timestamp")):
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            return float(candidate)
        if isinstance(candidate, str) and candidate.strip():
            try:
                return float(candidate)
            except (ValueError, TypeError, OverflowError):
                try:
                    return datetime.fromisoformat(candidate.strip().replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError, OSError, OverflowError):
                    continue
    return float(rowid)


def _history_status(result: dict) -> str:
    error_code = result.get("error_code") or result.get("error")
    status = result.get("status")
    if error_code:
        return _status_label(status or "failed", str(error_code))
    if status:
        return _status_label(status)
    return "已完成"


def _history_summary(result: dict) -> str:
    if result.get("error_code") or result.get("error"):
        return _history_status(result)
    content = _decode_nested_json(result.get("content"))
    candidates = [content] if isinstance(content, str) else []
    if isinstance(content, dict):
        candidates.extend(content.get(key) for key in ("headline", "summary", "overall_assessment", "conclusion", "decision", "text"))
        conditions = content.get("conditions")
        if not any(candidates) and isinstance(conditions, list):
            return f"结构化分析（{len(conditions)} 项条件）"
    candidates.extend(result.get(key) for key in ("summary", "text", "overall_assessment"))
    summary = next((item for item in candidates if isinstance(item, str) and item.strip()), "已保存结果")
    return " ".join(summary.split())[:180]


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # Access denied still means the PID exists.
    try:
        exit_code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value == 259)
    finally:
        kernel32.CloseHandle(handle)


def _bridge_owner_is_alive(pid: int, runtime_root: Path, status_at: float, launch_mode: str) -> bool:
    """Validate a status-file PID against its start time and, for process mode, runtime args."""
    try:
        import psutil
    except ImportError:
        return _process_is_running(pid) and bool(status_at and time.time() - status_at <= 90)
    try:
        process = psutil.Process(pid)
        if status_at and process.create_time() > status_at + 5:
            return False
        if launch_mode == "process":
            expected = os.path.normcase(os.path.abspath(os.fspath(runtime_root)))
            arguments = process.cmdline()
            return any(os.path.normcase(os.path.abspath(arg)) == expected for arg in arguments)
        return process.is_running()
    except (psutil.Error, OSError, ValueError):
        return False


def _token_counts(root: Path, days: int = 7) -> dict:
    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=days)
    data = {
        "available": root.is_dir(),
        "today": {"input": 0, "cached": 0, "output": 0, "total": 0, "turns": 0},
        "week": {"input": 0, "cached": 0, "output": 0, "total": 0, "turns": 0},
        "files_scanned": 0,
    }
    if not root.is_dir():
        return data
    seen_responses = set()
    try:
        files = list(root.rglob("*.jsonl"))
    except OSError:
        return data
    for path in files:
        try:
            if path.stat().st_mtime < cutoff.timestamp():
                continue
            data["files_scanned"] += 1
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if len(line) > 2_000_000:
                        continue
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(event, dict) or event.get("type") != "token_usage_record":
                        continue
                    payload = event.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    response_id = payload.get("response_id")
                    if response_id and response_id in seen_responses:
                        continue
                    if response_id:
                        seen_responses.add(response_id)
                    try:
                        stamp = event.get("timestamp")
                        recorded_at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                        if recorded_at.tzinfo is None:
                            recorded_at = recorded_at.astimezone()
                        recorded_at = recorded_at.astimezone(now.tzinfo)
                    except (ValueError, TypeError, OSError):
                        recorded_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                    if recorded_at < cutoff or recorded_at > now + timedelta(minutes=5):
                        continue
                    usage = payload.get("usage") or payload.get("turn_token_usage") or {}
                    if not isinstance(usage, dict):
                        continue
                    try:
                        raw_input = max(0, int(usage.get("input_tokens", 0) or 0))
                        cached = max(0, int(usage.get("cached_input_tokens", 0) or 0))
                        output = max(0, int(usage.get("output_tokens", 0) or 0))
                        total = max(0, int(usage.get("total_tokens", 0) or 0))
                    except (TypeError, ValueError):
                        continue
                    input_tokens = raw_input + cached if total and raw_input + cached + output == total else raw_input
                    total = total or input_tokens + output
                    bucket = data["week"]
                    bucket["input"] += input_tokens
                    bucket["cached"] += cached
                    bucket["output"] += output
                    bucket["total"] += total
                    bucket["turns"] += 1
                    if recorded_at.date() == now.date():
                        bucket = data["today"]
                        bucket["input"] += input_tokens
                        bucket["cached"] += cached
                        bucket["output"] += output
                        bucket["total"] += total
                        bucket["turns"] += 1
        except OSError:
            continue
    return data


class BridgeController:
    _thread_registry: dict[str, threading.Thread] = {}
    _thread_registry_lock = threading.Lock()

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(os.path.abspath(os.fspath(project_root or Path.cwd())))
        self.runtime_root = self.project_root / "stock-strategy" / "logs" / "desktop-strategy-live"
        self.preference_path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "pyQuant3" / "codex-bridge-manager.json"

    def task_info(self) -> dict:
        command = self.bridge_command()
        status = _read_json(self.runtime_path() / "status.json")
        pid = 0
        try:
            pid = int((self.runtime_path() / "bridge.pid").read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            pass
        running = bool(pid > 0 and _process_is_running(pid))
        agent = _read_json(self.runtime_path() / "agent" / "agent-status.json")
        agent_updated = float(agent.get("updated_epoch") or 0)
        agent_fresh = bool(agent_updated and time.time() - agent_updated <= 90)
        active_statuses = {"registered", "agent_starting", "ready", "analyzing", "degraded", "stopping"}
        try:
            status_pid = int(status.get("agent_pid") or 0)
            status_at = float(status.get("at") or 0)
        except (TypeError, ValueError):
            status_pid, status_at = 0, 0
        if (not running and status_pid > 0 and status.get("status") in active_statuses
                and _bridge_owner_is_alive(status_pid, self.runtime_path(), status_at,
                                           status.get("launch_mode") or self.run_mode())):
            pid = status_pid
            running = True
        # A packaged onefile worker runs inside the manager's process tree, so
        # bridge.pid points at the manager/bootloader PID rather than a child.
        if getattr(sys, "frozen", False) and pid > 0 and agent_fresh and agent.get("status") in (
            "ready", "analyzing", "degraded", "stopping"
        ):
            process_alive = _process_is_running(pid)
            if not process_alive:
                process_alive = self._process_tree_contains(pid, os.getpid())
            if process_alive:
                running = True
                status = {**status, "status": agent.get("status"), "agent_pid": pid}
        last_run = ""
        last_run_at = status.get("at") or (agent.get("updated_epoch") if agent_fresh else 0)
        try:
            if last_run_at:
                last_run = datetime.fromtimestamp(float(last_run_at)).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError, OverflowError):
            pass
        reported_status = agent.get("status") if running and agent_fresh else status.get("status")
        agent_detail = agent.get("detail") if isinstance(agent.get("detail"), dict) else {}
        last_error = agent_detail.get("error_code") or status.get("error_code") or ""
        return {
            "exists": command is not None,
            "state": "Running" if running else "Ready" if command else "Missing",
            "running": running,
            "enabled": self.autostart_enabled(),
            "mode": status.get("launch_mode") or self.run_mode(),
            "last_run": last_run,
            "last_result": _status_label(reported_status, str(last_error)),
            "error": "bridge_binary_missing" if command is None else "",
            "message": str(command or "随管理器打包的 desktop_strategy_bridge.exe 未找到"),
            "status": status,
            "agent_status": agent,
        }

    def bridge_command(self) -> list[str] | None:
        if getattr(sys, "frozen", False):
            return [sys.executable]
        runner_candidates = (
            self.project_root / "stock-strategy" / "tools" / "run_desktop_strategy_bridge.py",
            self.project_root / "stock_standalone" / "stock-strategy" / "tools" / "run_desktop_strategy_bridge.py",
        )
        runner = next((path for path in runner_candidates if path.is_file()), None)
        return [sys.executable, str(runner)] if runner else None

    @staticmethod
    def _process_tree_contains(pid: int, ancestor_pid: int) -> bool:
        if os.name != "nt" or pid <= 0 or ancestor_pid <= 0:
            return False
        script = (
            "$rows=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId;"
            "$parents=@{};foreach($row in $rows){$parents[[int]$row.ProcessId]=[int]$row.ParentProcessId};"
            f"$current={int(pid)};$found=$false;for($i=0;$i -lt 12 -and $current -gt 0;$i++){{"
            f"if($current -eq {int(ancestor_pid)}){{$found=$true;break}};"
            "if(-not $parents.ContainsKey($current)){break};$current=$parents[$current]};"
            "if($found){'1'}else{'0'}"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0 and result.stdout.strip() == "1"
        except (OSError, subprocess.TimeoutExpired):
            return False

    def autostart_enabled(self) -> bool:
        return bool(_read_json(self.preference_path).get("start_with_manager", False))

    def run_mode(self) -> str:
        value = _read_json(self.preference_path).get("run_mode")
        return value if value in ("process", "thread") else "process"

    def task_table_column_widths(self) -> list[int]:
        values = _read_json(self.preference_path).get("task_table_column_widths")
        if not isinstance(values, list):
            return []
        widths = []
        for value in values:
            try:
                width = int(value)
            except (TypeError, ValueError, OverflowError):
                return []
            if width < 48 or width > 2400:
                return []
            widths.append(width)
        return widths

    def save_task_table_column_widths(self, widths: list[int]) -> None:
        safe_widths = []
        for value in widths:
            try:
                width = int(value)
            except (TypeError, ValueError, OverflowError):
                return
            if width < 48 or width > 2400:
                return
            safe_widths.append(width)
        self._write_preferences(task_table_column_widths=safe_widths)

    def set_autostart_enabled(self, enabled: bool) -> None:
        self._write_preferences(start_with_manager=bool(enabled))

    def _write_preferences(self, **updates) -> None:
        preferences = _read_json(self.preference_path)
        preferences.update(updates)
        self.preference_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preference_path.with_suffix(".pending")
        temporary.write_text(json.dumps(preferences, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.preference_path)

    def set_run_mode(self, mode: str) -> None:
        if mode not in ("process", "thread"):
            raise ValueError("unsupported bridge run mode")
        self._write_preferences(run_mode=mode)

    def runtime_path(self, task: dict | None = None) -> Path:
        return self.runtime_root

    @staticmethod
    def _read_config(runtime: Path) -> dict:
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            cfg.read(runtime / "bridge.ini", encoding="utf-8-sig")
            section = cfg["general"] if cfg.has_section("general") else {}
            return {
                "backend": section.get("stock_strategy_base_url", ""),
                "node_id": section.get("ipc_node_id", ""),
                "workspace_id": section.get("ipc_workspace_id", ""),
            }
        except (OSError, configparser.Error, KeyError, TypeError):
            return {}

    @staticmethod
    def _tail(path: Path, max_bytes: int = 96 * 1024, max_lines: int = 160) -> str:
        try:
            size = path.stat().st_size
            with path.open("rb") as stream:
                if size > max_bytes:
                    stream.seek(size - max_bytes)
                    stream.readline()
                raw = stream.read(max_bytes)
            lines = raw.decode("utf-8", errors="replace").splitlines()
            return "\n".join(lines[-max_lines:])
        except OSError:
            return ""

    @staticmethod
    def _history(db_path: Path, limit: int = 20) -> list[dict]:
        if not db_path.is_file():
            return []
        rows_out = []
        try:
            with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
                db.execute("PRAGMA query_only=ON")
                for table, kind in (("chat_results", "AI对话"), ("results", "策略研究")):
                    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    if not exists:
                        continue
                    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
                    if not {"id", "result"}.issubset(columns):
                        continue
                    selected = ["rowid", "id", "result"]
                    selected.extend(name for name in ("thread_id", "created_at") if name in columns)
                    for row in db.execute(
                        f"SELECT {', '.join(selected)} FROM {table} ORDER BY rowid DESC LIMIT ?", (limit,)
                    ):
                        values = dict(zip(selected, row))
                        task_id, raw = str(values["id"]), values["result"]
                        try:
                            result = json.loads(raw) if isinstance(raw, str) else {}
                        except (ValueError, TypeError):
                            result = {}
                        if not isinstance(result, dict):
                            result = {}
                        thread_id = result.get("thread_id") or values.get("thread_id") or ""
                        rows_out.append({
                            "kind": kind, "id": task_id, "model": str(result.get("model") or ""),
                            "thread_id": str(thread_id), "status": _history_status(result),
                            "completed_at": _format_history_time(values.get("created_at"), result),
                            "summary": _history_summary(result), "details": result,
                            "order": _history_order(values.get("created_at"), result, int(values["rowid"])),
                        })
        except (sqlite3.Error, OSError, ValueError):
            return []
        rows_out.sort(key=lambda item: item["order"], reverse=True)
        return rows_out[:limit]

    def snapshot(self, include_tokens: bool = False) -> dict:
        task = self.task_info()
        runtime = self.runtime_path(task)
        parent = _read_json(runtime / "status.json")
        agent = _read_json(runtime / "agent" / "agent-status.json")
        config = self._read_config(runtime)
        heartbeat = float(agent.get("updated_epoch") or 0)
        age = max(0, time.time() - heartbeat) if heartbeat else None
        if task.get("running") and age is not None and age <= 90 and agent.get("status"):
            parent = {**parent, "status": agent["status"], "agent_pid": parent.get("agent_pid") or task.get("status", {}).get("agent_pid"),
                      "port": parent.get("port") or 26776}
        desktop = (agent.get("detail") or {}).get("desktop_runtime") or {}
        db_path = runtime / "agent" / "agent.db"
        result = {
            "task": task, "runtime": str(runtime), "parent": parent, "agent": agent,
            "config": config, "heartbeat_age": age, "desktop": desktop,
            "history": self._history(db_path),
            "logs": _format_bridge_logs(self._tail(runtime / "agent-output.txt")),
            "log_status": _bridge_log_status(task, parent, agent, age),
        }
        if include_tokens:
            codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
            result["tokens"] = _token_counts(codex_home / "sessions")
        return result

    def perform(self, operation: str, enabled: bool | None = None) -> str:
        if operation == "autostart":
            self.set_autostart_enabled(bool(enabled))
            if enabled:
                try:
                    self._start_bridge()
                except Exception:
                    self.set_autostart_enabled(False)
                    raise
                return "已启用随管理器自动启动，并已启动桥接"
            return "已关闭随管理器自动启动；当前桥接继续运行"
        if operation in ("mode_process", "mode_thread"):
            mode = operation.removeprefix("mode_")
            self.set_run_mode(mode)
            return "已设置桥接运行方式；重新启动桥接后生效"
        if operation == "start":
            self._start_bridge()
            return "已启动独立 Codex 桌面桥"
        if operation == "stop":
            stop_request = self.runtime_path() / "agent" / "stop.request"
            if not stop_request.parent.is_dir():
                raise RuntimeError("桥接代理尚未运行，无法请求优雅停止")
            pending = stop_request.with_suffix(".pending")
            pending.write_text("manager-request\n", encoding="utf-8")
            os.replace(pending, stop_request)
            return "已请求停止；当前任务完成后会退出"
        raise ValueError("unsupported bridge operation")

    def _start_bridge(self) -> None:
        command = self.bridge_command()
        if not command:
            raise RuntimeError(
                "未找到 Codex 桌面桥运行器。请在完整源码工程中启动管理器，或使用已内嵌桥接模块的打包版。"
            )
        if self.task_info().get("running"):
            return
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        stop_request = self.runtime_root / "agent" / "stop.request"
        try:
            stop_request.unlink()
        except FileNotFoundError:
            pass
        backend = self._read_config(self.runtime_root).get("backend") or DEFAULT_BACKEND
        mode = self.run_mode()
        arguments = ("--backend", backend, "--runtime", str(self.runtime_root),
                     "--desktop-root", str(self.project_root), "--launch-mode", mode)
        if mode == "thread":
            key = str(self.runtime_root).casefold()
            with self._thread_registry_lock:
                current = self._thread_registry.get(key)
                if current and current.is_alive():
                    return
                thread = threading.Thread(
                    target=self._run_bridge_thread, args=(command, arguments),
                    name="codex-desktop-bridge", daemon=False,
                )
                self._thread_registry[key] = thread
                thread.start()
            return
        command.extend(arguments)
        creationflags = 0
        if os.name == "nt":
            creationflags = (getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                             | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        worker_env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1",
                      "PYQUANT3_CODEX_BRIDGE_WORKER": "1",
                      "PYQUANT3_CODEX_BRIDGE_ARGS": json.dumps(arguments)} if getattr(sys, "frozen", False) else None
        process = subprocess.Popen(
            command, cwd=str(self.project_root), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, creationflags=creationflags,
            env=worker_env,
        )
        time.sleep(0.3)
        if process.poll() is not None:
            if process.returncode == 0 and self.task_info().get("running"):
                return
            status = _read_json(self.runtime_root / "status.json")
            details = str(status.get("error_code") or status.get("status") or "unknown")
            raise RuntimeError(f"桥接进程启动后立即退出，退出码 {process.returncode}，状态 {details}；请查看 {self.runtime_root / 'status.json'}")

    @staticmethod
    def _run_bridge_thread(command: list[str], arguments: tuple[str, ...]) -> None:
        try:
            if getattr(sys, "frozen", False):
                from run_desktop_strategy_bridge import main as run_bridge
            else:
                runner_root = Path(os.path.abspath(command[1])).parent.parent
                if str(runner_root) not in sys.path:
                    sys.path.insert(0, str(runner_root))
                from run_desktop_strategy_bridge import main as run_bridge
            run_bridge(list(arguments))
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            # The bridge owns detailed agent diagnostics; this fallback records only a safe error class.
            runtime_arg = next((arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == "--runtime"), "")
            if runtime_arg:
                path = Path(runtime_arg) / "status.json"
                try:
                    pending = path.with_suffix(".pending")
                    pending.write_text(json.dumps({"status": "degraded", "error_code": type(exc).__name__, "at": time.time()}), encoding="utf-8")
                    os.replace(pending, path)
                except OSError:
                    pass

    def start_if_enabled(self) -> str:
        if not self.autostart_enabled():
            return "随管理器自动启动未启用"
        if self.task_info().get("running"):
            return "Codex 桌面桥已在运行"
        self._start_bridge()
        return "已随管理器启动 Codex 桌面桥"


    def shutdown_for_manager_exit(self) -> None:
        """Gracefully stop an in-process bridge; detached process mode is a service."""
        status = _read_json(self.runtime_root / "status.json")
        active_mode = status.get("launch_mode") or self.run_mode()
        if active_mode != "thread":
            return
        try:
            owner_pid = int(status.get("agent_pid") or 0)
        except (TypeError, ValueError):
            owner_pid = 0
        if owner_pid and owner_pid != os.getpid():
            return
        key = str(self.runtime_root).casefold()
        with self._thread_registry_lock:
            bridge_thread = self._thread_registry.get(key)
        if not bridge_thread or not bridge_thread.is_alive():
            return
        stop_request = self.runtime_root / "agent" / "stop.request"
        stop_request.parent.mkdir(parents=True, exist_ok=True)
        pending = stop_request.with_suffix(".pending")
        pending.write_text("manager-exit\n", encoding="utf-8")
        os.replace(pending, stop_request)
        # Stop after the current Codex turn, then release the gateway and bridge lock.
        bridge_thread.join()
        with self._thread_registry_lock:
            if self._thread_registry.get(key) is bridge_thread:
                self._thread_registry.pop(key, None)


class _SnapshotWorker(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict)

    def __init__(self, controller: BridgeController, include_tokens: bool, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.include_tokens = include_tokens

    def run(self):
        try:
            self.ready.emit(self.controller.snapshot(self.include_tokens))
        except Exception as exc:
            self.ready.emit({"error": type(exc).__name__, "message": str(exc)[:300]})


class _OperationWorker(QtCore.QThread):
    ready = QtCore.pyqtSignal(str, bool, str)

    def __init__(self, controller: BridgeController, operation: str, enabled: bool | None = None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.operation = operation
        self.enabled = enabled

    def run(self):
        try:
            message = self.controller.perform(self.operation, self.enabled)
            self.ready.emit(self.operation, True, message)
        except Exception as exc:
            self.ready.emit(self.operation, False, f"{type(exc).__name__}: {str(exc)[:300]}")


class CodexBridgeManagerDialog(QtWidgets.QDialog):
    def __init__(self, project_root: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Codex 桌面桥管理器")
        self.resize(1020, 760)
        self.setMinimumSize(850, 620)
        self.controller = BridgeController(project_root)
        self._snapshot_worker = None
        self._operation_worker = None
        self._token_cache = None
        self._last_token_scan = 0.0
        self._records = []
        self._column_widths_initialized = False
        self._column_width_save_timer = QtCore.QTimer(self)
        self._column_width_save_timer.setSingleShot(True)
        self._column_width_save_timer.setInterval(400)
        self._column_width_save_timer.timeout.connect(self._save_task_table_column_widths)
        self._build_ui()
        QtCore.QTimer.singleShot(0, self._initialize_task_table_column_widths)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start()
        self.refresh_data()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog { background: #171a21; color: #d7dae0; }
            QLabel { color: #d7dae0; }
            QGroupBox { border: 1px solid #38404c; border-radius: 6px; margin-top: 10px; padding: 8px; color: #93c5fd; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #293241; color: #e5e7eb; border: 1px solid #475569; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #334155; }
            QLineEdit, QPlainTextEdit, QTableWidget { background: #11151b; color: #d7dae0; border: 1px solid #303846; }
            QTabWidget::pane { border: 1px solid #38404c; }
        """)
        root = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("🧩 Codex 桌面桥")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #60a5fa;")
        header.addWidget(title)
        header.addStretch()
        self.status_label = QtWidgets.QLabel("正在读取桥接状态…")
        header.addWidget(self.status_label)
        self.btn_refresh = QtWidgets.QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_data)
        header.addWidget(self.btn_refresh)
        root.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.chk_autostart = QtWidgets.QCheckBox("管理器启动时自动启动桥接")
        self.chk_autostart.setToolTip("启用后，管理器每次启动都会在后台拉起独立桥接；关闭管理器不会停止桥接。勾选时会立即启动。")
        self.chk_autostart.toggled.connect(lambda enabled: self._start_operation("autostart", enabled))
        controls.addWidget(self.chk_autostart)
        controls.addWidget(QtWidgets.QLabel("运行方式："))
        self.cmb_run_mode = QtWidgets.QComboBox()
        self.cmb_run_mode.addItem("独立进程", "process")
        self.cmb_run_mode.addItem("管理器线程", "thread")
        self.cmb_run_mode.setFixedWidth(140)
        self.cmb_run_mode.setToolTip("独立进程会在管理器关闭后继续运行；管理器线程更轻，但退出管理器会停止桥接。")
        self.cmb_run_mode.currentIndexChanged.connect(self._run_mode_changed)
        controls.addWidget(self.cmb_run_mode)
        self.btn_start = QtWidgets.QPushButton("启动桥")
        self.btn_start.clicked.connect(lambda: self._start_operation("start"))
        controls.addWidget(self.btn_start)
        self.btn_stop = QtWidgets.QPushButton("请求停止")
        self.btn_stop.clicked.connect(self._request_stop)
        controls.addWidget(self.btn_stop)
        controls.addStretch()
        controls.addWidget(QtWidgets.QLabel("独立进程在管理器关闭后继续运行；线程模式随管理器退出。"))
        root.addLayout(controls)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        overview = QtWidgets.QWidget()
        overview_layout = QtWidgets.QVBoxLayout(overview)
        info_group = QtWidgets.QGroupBox("桥接与连接")
        form = QtWidgets.QFormLayout(info_group)
        self.info = {}
        for key, label in (
            ("task", "桥接进程"), ("backend", "生产 API"), ("node", "桥接节点"),
            ("workspace", "工作区"), ("heartbeat", "后端心跳"), ("port", "本机网关端口"),
            ("runtime", "本机运行目录"), ("engine", "Codex 引擎路径"),
            ("desktop", "TK / ATS 运行状态"), ("models", "可用模型"),
        ):
            value = QtWidgets.QLabel("—")
            value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            self.info[key] = value
            form.addRow(label + "：", value)
        overview_layout.addWidget(info_group)

        token_group = QtWidgets.QGroupBox("Codex Token 用量")
        token_layout = QtWidgets.QVBoxLayout(token_group)
        self.token_label = QtWidgets.QLabel("等待本机会话统计…")
        self.token_label.setWordWrap(True)
        token_layout.addWidget(self.token_label)
        self.token_note = QtWidgets.QLabel("统计来自当前 Windows 用户的 Codex 本地会话记录，可能包含其他 Codex 会话；不代表订阅额度百分比。")
        self.token_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.token_note.setWordWrap(True)
        token_layout.addWidget(self.token_note)
        overview_layout.addWidget(token_group)
        overview_layout.addStretch()
        self.tabs.addTab(overview, "状态与用量")

        tasks = QtWidgets.QWidget()
        tasks_layout = QtWidgets.QVBoxLayout(tasks)
        self.active_label = QtWidgets.QLabel("当前任务：—")
        self.active_label.setWordWrap(True)
        self.active_label.setStyleSheet("font-size: 14px; color: #fbbf24; padding: 6px;")
        tasks_layout.addWidget(self.active_label)
        self.task_table = QtWidgets.QTableWidget(0, 7)
        self.task_table.setHorizontalHeaderLabels(["类型", "任务 ID", "模型", "Thread", "状态", "完成时间", "摘要"])
        self.task_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.task_table.setWordWrap(False)
        self.task_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.task_table.verticalHeader().setFixedWidth(30)
        self.task_table.verticalHeader().setDefaultSectionSize(27)
        header = self.task_table.horizontalHeader()
        header.setMinimumSectionSize(55)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.sectionResized.connect(lambda *_: self._schedule_task_table_column_save())
        self.task_table.itemSelectionChanged.connect(self._show_task_details)
        tasks_layout.addWidget(self.task_table, 3)
        self.task_details_label = QtWidgets.QLabel("选择任务查看可读结果与状态信息")
        self.task_details_label.setStyleSheet("color: #93c5fd; padding-top: 4px;")
        tasks_layout.addWidget(self.task_details_label)
        self.task_details = QtWidgets.QPlainTextEdit()
        self.task_details.setReadOnly(True)
        self.task_details.setPlaceholderText("选择一条任务记录查看详情；旧记录若未保存完成时间，会标记为时间未知。")
        self.task_details.setMaximumBlockCount(300)
        tasks_layout.addWidget(self.task_details, 2)
        self.tabs.addTab(tasks, "运行任务与历史")

        logs = QtWidgets.QWidget()
        logs_layout = QtWidgets.QVBoxLayout(logs)
        self.log_status_label = QtWidgets.QLabel("最新状态：正在读取…")
        self.log_status_label.setWordWrap(True)
        self.log_status_label.setStyleSheet("color: #93c5fd; padding: 4px 2px;")
        logs_layout.addWidget(self.log_status_label)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        logs_layout.addWidget(self.log_view)
        self.tabs.addTab(logs, "桥接日志")

    def _initialize_task_table_column_widths(self):
        if self._column_widths_initialized:
            return
        header = self.task_table.horizontalHeader()
        saved = self.controller.task_table_column_widths()
        if len(saved) == self.task_table.columnCount():
            widths = saved
        else:
            compact = [80, 115, 92, 120, 94, 135]
            summary_width = max(220, self.task_table.viewport().width() - sum(compact) - 4)
            widths = compact + [summary_width]
        was_blocked = header.blockSignals(True)
        try:
            for index, width in enumerate(widths):
                header.resizeSection(index, width)
        finally:
            header.blockSignals(was_blocked)
        self._column_widths_initialized = True

    def _schedule_task_table_column_save(self):
        if self._column_widths_initialized:
            self._column_width_save_timer.start()

    def _save_task_table_column_widths(self):
        widths = [self.task_table.columnWidth(index) for index in range(self.task_table.columnCount())]
        try:
            self.controller.save_task_table_column_widths(widths)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Codex bridge task column widths could not be saved: %s", type(exc).__name__)

    def refresh_data(self):
        if self._snapshot_worker and self._snapshot_worker.isRunning():
            return
        include_tokens = self._token_cache is None or time.monotonic() - self._last_token_scan >= 60
        worker = _SnapshotWorker(self.controller, include_tokens, self)
        worker.ready.connect(self._render_snapshot)
        worker.finished.connect(lambda current=worker: self._clear_snapshot_worker(current))
        worker.finished.connect(worker.deleteLater)
        self._snapshot_worker = worker
        worker.start()

    def _clear_snapshot_worker(self, worker):
        if self._snapshot_worker is worker:
            self._snapshot_worker = None

    def _render_snapshot(self, snapshot: dict):
        if snapshot.get("error"):
            self.status_label.setText("读取失败：" + snapshot.get("error", ""))
            return
        if snapshot.get("tokens") is not None:
            self._token_cache = snapshot["tokens"]
            self._last_token_scan = time.monotonic()
        if self._token_cache is not None:
            snapshot["tokens"] = self._token_cache

        self._snapshot = snapshot
        task = snapshot.get("task") or {}
        exists = bool(task.get("exists"))
        running = bool(task.get("running"))
        age = snapshot.get("heartbeat_age")
        if not exists:
            state_text = "未找到随包桥接运行器"
        elif running and age is not None and age <= 90:
            state_text = "运行中 · 后端心跳正常"
            if snapshot.get("desktop", {}).get("status") == "degraded":
                state_text += " · TK / ATS 联动不完整"
        elif running:
            state_text = "进程运行中 · 后端心跳缺失或过期"
        else:
            state_text = "运行器就绪 · 桥接已停止"
        self.status_label.setText(state_text)
        self.chk_autostart.blockSignals(True)
        self.chk_autostart.setChecked(bool(task.get("enabled")))
        self.chk_autostart.setEnabled(self._operation_worker is None)
        self.chk_autostart.blockSignals(False)
        self.cmb_run_mode.blockSignals(True)
        mode_index = self.cmb_run_mode.findData(task.get("mode", "process"))
        self.cmb_run_mode.setCurrentIndex(max(0, mode_index))
        self.cmb_run_mode.setEnabled(self._operation_worker is None)
        self.cmb_run_mode.blockSignals(False)
        self.btn_start.setEnabled(exists and not running and self._operation_worker is None)
        self.btn_stop.setEnabled(exists and running and self._operation_worker is None)

        config = snapshot.get("config") or {}
        agent = snapshot.get("agent") or {}
        detail = agent.get("detail") or {}
        parent = snapshot.get("parent") or {}
        desktop = snapshot.get("desktop") or {}
        port = parent.get("port") or "—"
        heartbeat = "无本机成功心跳记录"
        if age is not None:
            heartbeat = f"{int(age)} 秒前" if age < 3600 else f"{int(age / 60)} 分钟前"
        task_state = "运行中" if running else "运行器就绪" if exists else "运行器缺失"
        self.info["task"].setText(
            f"{task_state} · {'管理器联动自启已开' if task.get('enabled') else '管理器联动自启已关'} · "
            f"方式 {'独立进程' if task.get('mode') == 'process' else '管理器线程'} · "
            f"最近更新 {task.get('last_run') or '暂无时间'} · 状态 {task.get('last_result', '状态未知')}"
        )
        self.info["backend"].setText(config.get("backend") or "未配置")
        self.info["node"].setText(config.get("node_id") or agent.get("node_id") or "—")
        self.info["workspace"].setText(config.get("workspace_id") or agent.get("workspace_id") or "—")
        self.info["heartbeat"].setText(heartbeat)
        self.info["port"].setText(str(port))
        self.info["runtime"].setText(snapshot.get("runtime") or "—")
        self.info["desktop"].setText(
            f"桌面发现：{desktop.get('status', '未发现')}；TK PID：{desktop.get('tk_pid') or '—'}；"
            f"ATS PID：{desktop.get('ats_pid') or '—'}"
        )
        models = detail.get("models") or []
        names = [str(item.get("id", "")) for item in models if isinstance(item, dict) and item.get("id")]
        self.info["engine"].setText(detail.get("engine_path") or "—")
        self.info["models"].setText("、".join(names) if names else "目录尚未加载")
        self._render_tokens(snapshot.get("tokens"))
        task_status = agent.get("status", "") if running else "stopped"
        self._render_tasks(snapshot.get("history") or [], detail, task_status)
        self.log_status_label.setText(snapshot.get("log_status") or "最新状态：暂无状态记录")
        logs = snapshot.get("logs") or "尚无桥接日志"
        if self.log_view.toPlainText() != logs:
            self.log_view.setPlainText(logs)

    def _render_tokens(self, tokens: dict | None):
        if not tokens or not tokens.get("available"):
            self.token_label.setText("未找到本机 Codex 会话用量记录。")
            return
        today = tokens.get("today") or {}
        week = tokens.get("week") or {}
        hit = (week.get("cached", 0) / week.get("input", 1) * 100) if week.get("input", 0) else 0
        self.token_label.setText(
            f"今日：{today.get('total', 0):,} tokens（输入 {today.get('input', 0):,} / 缓存 {today.get('cached', 0):,} / 输出 {today.get('output', 0):,}，{today.get('turns', 0)} 轮）\n"
            f"近 7 日：{week.get('total', 0):,} tokens（输入 {week.get('input', 0):,} / 缓存 {week.get('cached', 0):,} / 输出 {week.get('output', 0):,}，缓存占输入 {hit:.1f}%）"
        )

    def _render_tasks(self, history: list[dict], detail: dict, status: str):
        if status == "analyzing":
            scope = detail.get("scope") or "策略研究"
            active = (
                f"当前任务：运行中 · {scope} · ID {detail.get('job_id', '—')} · "
                f"模型 {detail.get('effective_model', '—')} / {detail.get('effective_effort', '—')} · "
                f"耗时 {detail.get('elapsed_seconds', '—')} 秒 · Thread {detail.get('thread_id', '—')}"
            )
        elif status == "stopping":
            active = "当前任务：正在停止桥接代理。"
        elif status == "ready":
            active = "当前任务：空闲，等待 Web 队列。"
        elif status == "stopped":
            active = "当前任务：桥接已停止。"
        else:
            active = f"当前任务：{_status_label(status)}"
        selected_id = ""
        selected_row = self.task_table.currentRow()
        if 0 <= selected_row < len(self._records):
            selected_id = self._records[selected_row].get("id", "")
        self.active_label.setText(active)
        self._records = history
        self.task_table.setRowCount(len(history))
        for row, record in enumerate(history):
            values = (
                record.get("kind", "—"), record.get("id", "")[:14], record.get("model") or "—",
                record.get("thread_id", "")[:14] or "—", record.get("status", "状态未知"),
                record.get("completed_at", "时间未知（旧记录）"), record.get("summary", "无摘要"),
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.task_table.setItem(row, column, item)
        if not history:
            self.task_details_label.setText("暂无历史任务")
            self.task_details.setPlainText("尚无本地完成记录。")
        else:
            selected = next((index for index, record in enumerate(history) if record.get("id") == selected_id), 0)
            self.task_table.selectRow(selected)

    def _show_task_details(self):
        row = self.task_table.currentRow()
        if 0 <= row < len(self._records):
            record = self._records[row]
            details = _decode_nested_json(record.get("details") or {})
            lines = [
                f"类型：{record.get('kind') or '—'}",
                f"任务 ID：{record.get('id') or '—'}",
                f"状态：{record.get('status') or '状态未知'}",
                f"完成时间：{record.get('completed_at') or '时间未知（旧记录）'}",
                f"模型：{record.get('model') or '—'}",
                f"Thread：{record.get('thread_id') or '—'}",
                "",
            ]
            if isinstance(details, dict) and "content" in details:
                content = details.get("content")
                other = {key: value for key, value in details.items() if key != "content"}
                lines.append("对话内容：")
                display_content = _localized_result(content)
                lines.append(display_content if isinstance(display_content, str) else json.dumps(display_content, ensure_ascii=False, indent=2))
                if other:
                    lines.extend(("", "任务信息：", json.dumps(_localized_result(other), ensure_ascii=False, indent=2)))
            elif details:
                lines.extend(("任务结果：", json.dumps(_localized_result(details), ensure_ascii=False, indent=2)))
            else:
                lines.append("没有可显示的结果内容。")
            self.task_details_label.setText(f"任务详情 · {record.get('status', '状态未知')} · {record.get('completed_at', '时间未知（旧记录）')}")
            self.task_details.setPlainText("\n".join(lines)[:12000])

    def _request_stop(self):
        answer = QtWidgets.QMessageBox.question(
            self, "停止 Codex 桌面桥",
            "将请求桥在当前 Codex 任务完成后优雅退出；正在运行的回合会继续，不会被强制中断。是否继续？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._start_operation("stop")

    def _start_operation(self, operation: str, enabled: bool | None = None):
        if self._operation_worker and self._operation_worker.isRunning():
            return
        worker = _OperationWorker(self.controller, operation, enabled, self)
        worker.ready.connect(self._operation_finished)
        worker.finished.connect(lambda current=worker: self._clear_operation_worker(current))
        worker.finished.connect(worker.deleteLater)
        self._operation_worker = worker
        self.chk_autostart.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)
        worker.start()

    def _run_mode_changed(self, index: int):
        mode = self.cmb_run_mode.itemData(index)
        if mode in ("process", "thread"):
            self._start_operation("mode_" + mode)

    def _clear_operation_worker(self, worker):
        if self._operation_worker is worker:
            self._operation_worker = None

    def _operation_finished(self, operation: str, success: bool, message: str):
        if not success:
            QtWidgets.QMessageBox.warning(self, "桥接管理失败", message)
        else:
            self.status_label.setText(message)
        QtCore.QTimer.singleShot(250, self.refresh_data)

    def closeEvent(self, event):
        self.timer.stop()
        for worker in (self._snapshot_worker, self._operation_worker):
            if worker and worker.isRunning() and not worker.wait(1000):
                self.status_label.setText("后台操作尚未结束，请稍后关闭窗口。")
                event.ignore()
                return
        super().closeEvent(event)

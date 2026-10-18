# -*- coding: utf-8 -*-
"""Local management UI and controller for the independent Antigravity desktop bridge."""

from __future__ import annotations

import configparser
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.request import HTTPRedirectHandler, Request, ProxyHandler, build_opener

from PyQt6 import QtCore, QtGui, QtWidgets

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
    key = str(status or "").strip().lower()
    label = _STATUS_LABELS.get(key, status or "未知")
    if error_code:
        label = f"{label}（{error_code}）"
    return str(label)


_DEFAULT_ANTIGRAVITY_MODELS = (
    "gemini-3.8-flash", "gemini-3.8-pro", "gemini-2.5-flash",
)


def _model_display_names(models) -> list[str]:
    """Accept both the worker's model objects and legacy string catalogs."""
    names = []
    if isinstance(models, (list, tuple)):
        for model in models:
            if isinstance(model, str):
                label = model.strip()
            elif isinstance(model, dict):
                model_id = model.get("id") or model.get("model") or model.get("model_id")
                display_name = model.get("name") or model.get("display_name")
                if model_id and display_name and str(model_id) != str(display_name):
                    label = f"{display_name} ({model_id})"
                else:
                    label = model_id or display_name or ""
                label = str(label).strip()
            else:
                continue
            if label and label not in names:
                names.append(label)
    return names or list(_DEFAULT_ANTIGRAVITY_MODELS)


def _short_bridge_id(value: str) -> str:
    raw = str(value or "").strip()
    for prefix in ("codex-", "agv-", "ws-", "tk-"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
            break
    return raw[:8] or "—"


def _bridge_target_name(target: dict) -> str:
    node = str(target.get("node_id") or "").strip().lower()
    provider = str(target.get("provider") or "").strip().lower()
    label = str(target.get("label") or "").strip()
    if node.startswith("agv-") or "antigravity" in provider or "antigravity" in label.lower():
        return "Antigravity"
    if node.startswith("codex-") or "codex" in provider or label.lower().startswith("desktop codex"):
        return "Codex"
    return label[:32] or "桌面桥"


def _format_inventory_heartbeat(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "无记录"
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        else:
            stamp = stamp.astimezone()
        age = (datetime.now().astimezone() - stamp).total_seconds()
    except (ValueError, TypeError, OSError, OverflowError):
        return raw[:40]
    if age < -5:
        relative = "时钟有偏差"
    elif age < 60:
        relative = f"{max(0, int(age))} 秒前"
    elif age < 3600:
        relative = f"{int(age // 60)} 分钟前"
    elif age < 86400:
        relative = f"{int(age // 3600)} 小时前"
    else:
        relative = f"{int(age // 86400)} 天前"
    return f"{stamp.astimezone().strftime('%m-%d %H:%M:%S')} · {relative}"


def _history_timestamp(value) -> tuple[float, str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = datetime.fromtimestamp(float(value)).astimezone()
        return stamp.timestamp(), stamp.strftime("%Y-%m-%d %H:%M:%S")
    raw = str(value or "").strip()
    if not raw:
        return 0.0, "时间未知"
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
        return stamp.timestamp(), stamp.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError, OverflowError):
        try:
            stamp = datetime.fromtimestamp(float(raw)).astimezone()
            return stamp.timestamp(), stamp.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError, OverflowError):
            return 0.0, "时间未知"


_AGV_STAGE_LABELS = {
    "bridge_lock": "获取桥接锁", "config_prepare": "准备桥配置",
    "peer_configure": "配置后端连接", "local_gateway_init": "初始化本机网关",
    "local_gateway_start": "启动本机网关", "backend_register": "注册后台桥",
    "agent_start": "启动 Antigravity Agent", "backend_heartbeat": "发送后端心跳",
    "unified_job_wait": "等待统一任务", "chat_run": "运行 Antigravity 对话",
    "strategy_run": "运行 Antigravity 策略研究", "chat_result_retry": "重试写回对话结果",
    "antigravity_chat_exec": "执行 Antigravity 对话", "antigravity_strategy_exec": "执行 Antigravity 策略研究",
    "bridge_pid_cleanup": "清理桥进程标识", "next": "领取后台任务", "heartbeat": "发送后端心跳",
}


def _agv_error_label(value) -> str:
    raw = str(value or "").strip()
    key = raw.lower()
    if key == "engine_unavailable":
        return "找不到 AGY CLI"
    if "jsondecodeerror" in key:
        return "后台返回了无效 JSON"
    if "connectionrefusederror" in key:
        return "后端拒绝连接"
    if "remotedisconnected" in key:
        return "后端主动关闭连接"
    if "connectionreseterror" in key:
        return "网络连接被重置"
    if "timeout" in key:
        return "等待响应超时"
    if "_http_" in key:
        return "接口返回 HTTP " + key.rsplit("_http_", 1)[1]
    if key.startswith("http "):
        return "接口返回 " + raw.upper()
    return raw.replace("_", " ") or "未知错误"


def _agv_error_detail(value) -> str:
    if not isinstance(value, dict):
        return " ".join(str(value or "").split())[:300]
    parts = []
    kind = str(value.get("cause_type") or value.get("type") or "").lower()
    if kind == "connectionrefusederror":
        parts.append("后端拒绝连接")
    elif kind in ("timeout", "timeouterror", "socket.timeout"):
        parts.append("等待响应超时")
    elif kind == "remotedisconnected":
        parts.append("后端主动关闭连接")
    message = str(value.get("message") or "").strip()
    if message and message not in parts:
        parts.append(message[:220])
    for key, label in (("errno", "errno"), ("winerror", "WinError"), ("status", "HTTP"), ("backend", "后端"), ("path", "路径")):
        item = value.get(key)
        if item is not None and str(item).strip():
            parts.append(f"{label} {str(item)[:140]}")
    return "；".join(parts)[:520]


def _format_agv_logs(raw_text: str, max_lines: int = 160) -> str:
    entries = []
    for raw_line in str(raw_text or "").splitlines()[-max_lines:]:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except (ValueError, TypeError):
            timestamp, message, fingerprint = "", line, line
        else:
            if not isinstance(payload, dict):
                timestamp, message, fingerprint = "", str(payload), line
            else:
                stamp = payload.get("timestamp") or payload.get("at") or payload.get("updated_epoch")
                try:
                    if isinstance(stamp, (int, float)):
                        moment = datetime.fromtimestamp(float(stamp)).astimezone()
                    else:
                        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone()
                    timestamp = moment.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError, OSError, OverflowError):
                    timestamp = ""
                status = str(payload.get("status") or "").strip()
                if status:
                    parts = [_status_label(status)]
                    error_code = payload.get("error_code") or payload.get("error")
                    if error_code:
                        parts.append("错误：" + _agv_error_label(error_code))
                    stage = payload.get("stage")
                    error_info = payload.get("error_detail") if isinstance(payload.get("error_detail"), dict) else {}
                    stage = stage or error_info.get("stage")
                    if stage:
                        parts.append("阶段 " + _AGV_STAGE_LABELS.get(str(stage), str(stage).replace("_", " ")))
                    operation = payload.get("operation") or error_info.get("operation")
                    if operation:
                        parts.append("操作 " + {"next": "领取后台任务", "heartbeat": "发送后端心跳"}.get(str(operation), str(operation)))
                    for field, label in (("job_id", "任务"), ("thread_id", "会话"), ("port", "端口")):
                        if payload.get(field):
                            parts.append(label + " " + str(payload[field])[:64])
                    detail = _agv_error_detail(error_info)
                    if detail:
                        parts.append("详情 " + detail)
                    if payload.get("retry_after_seconds"):
                        parts.append("将在 %s 秒后重试" % payload["retry_after_seconds"])
                    message = "；".join(parts)
                else:
                    message = str(payload.get("message") or payload.get("detail") or "").strip()
                    if not message:
                        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    message = " ".join(message.split())[:520]
                fingerprint_payload = {key: value for key, value in payload.items() if key not in {"timestamp", "at", "updated_epoch"}}
                fingerprint = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str)
        if entries and fingerprint and fingerprint == entries[-1]["fingerprint"]:
            entries[-1]["count"] += 1
            if timestamp:
                entries[-1]["timestamp"] = timestamp
        else:
            entries.append({"timestamp": timestamp, "message": message, "fingerprint": fingerprint, "count": 1})
    return "\n".join(
        "[%s] %s%s" % (
            entry["timestamp"] or "时间未知（旧日志）", entry["message"],
            f"（连续重复 {entry['count']} 次）" if entry["count"] > 1 else "",
        )
        for entry in entries
    ) or "暂无日志。"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _bridge_owner_is_alive(pid: int, runtime_dir: Path, status_at: float = 0.0,
                           launch_mode: str = "process") -> bool:
    if os.name != "nt" or pid <= 0:
        return False
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid))
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        STILL_ACTIVE = 259
        if exit_code.value != STILL_ACTIVE:
            return False
        return True
    finally:
        kernel32.CloseHandle(handle)


class AntigravityBridgeController:
    """Controller for the independent Antigravity desktop bridge."""
    _thread_registry: dict[str, threading.Thread] = {}
    _thread_registry_lock = threading.Lock()

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = Path(os.path.abspath(os.fspath(project_root or Path.cwd())))
        self.runtime_root = self.project_root / "stock-strategy" / "logs" / "desktop-agv-bridge-live"
        self.preference_path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "pyQuant3" / "antigravity-bridge-manager.json"
        self._backend_inventory_cache_key = None
        self._backend_inventory_cache_at = 0.0
        self._backend_inventory_cache = {"ok": False, "targets": []}
        self._backend_inventory_lock = threading.Lock()

    def runtime_path(self) -> Path:
        return self.runtime_root

    def autostart_enabled(self) -> bool:
        prefs = _read_json(self.preference_path)
        return bool(prefs.get("start_with_manager", False))

    def manager_exit_shutdown_forced(self, mode: str | None = None) -> bool:
        return (mode or self.run_mode()) == "thread"

    def stop_on_manager_exit_enabled(self, mode: str | None = None) -> bool:
        if self.manager_exit_shutdown_forced(mode):
            return True
        return bool(_read_json(self.preference_path).get("stop_with_manager", False))

    def set_stop_on_manager_exit_enabled(self, enabled: bool):
        self._write_preferences(stop_with_manager=bool(enabled))

    def run_mode(self) -> str:
        prefs = _read_json(self.preference_path)
        mode = str(prefs.get("run_mode", "process")).strip().lower()
        return "thread" if mode == "thread" else "process"

    def set_autostart_enabled(self, enabled: bool):
        self._write_preferences(start_with_manager=bool(enabled))

    def set_run_mode(self, mode: str):
        normalized = "thread" if str(mode).strip().lower() == "thread" else "process"
        self._write_preferences(run_mode=normalized)

    def _write_preferences(self, **updates):
        self.preference_path.parent.mkdir(parents=True, exist_ok=True)
        prefs = _read_json(self.preference_path)
        prefs.update(updates)
        pending = self.preference_path.with_suffix(".pending")
        pending.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, self.preference_path)

    def _request_bridge_stop(self, reason: str):
        self.runtime_path().mkdir(parents=True, exist_ok=True)
        stop_request = self.runtime_path() / "stop.request"
        pending = stop_request.with_suffix(".pending")
        pending.write_text(str(reason), encoding="ascii")
        os.replace(pending, stop_request)

    def task_info(self) -> dict:
        command = self.bridge_command()
        status = _read_json(self.runtime_path() / "status.json")
        pid = 0
        try:
            pid = int((self.runtime_path() / "bridge.pid").read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            pass
        agent = _read_json(self.runtime_path() / "agent" / "agent-status.json")
        agent_updated = float(agent.get("updated_epoch") or 0)
        agent_fresh = bool(agent_updated and time.time() - agent_updated <= 90)
        active_statuses = {"registered", "agent_starting", "ready", "analyzing", "degraded", "stopping"}
        try:
            status_pid = int(status.get("agent_pid") or 0)
            status_at = float(status.get("at") or 0)
        except (TypeError, ValueError):
            status_pid, status_at = 0, 0
        launch_mode = status.get("launch_mode") or self.run_mode()

        running = False
        if status.get("status") in active_statuses:
            for candidate in dict.fromkeys((pid, status_pid)):
                if candidate > 0 and _bridge_owner_is_alive(candidate, self.runtime_path(), status_at, launch_mode):
                    pid = candidate
                    running = True
                    break

        if (getattr(sys, "frozen", False) and status.get("status") in active_statuses
                and pid > 0 and agent_fresh and agent.get("status") in (
            "ready", "analyzing", "degraded", "stopping"
        )):
            process_alive = _bridge_owner_is_alive(pid, self.runtime_path(), status_at, launch_mode)
            if not process_alive:
                process_alive = self._process_tree_contains(pid, os.getpid())
            if process_alive:
                running = True
                status = {**status, "status": agent.get("status"), "agent_pid": pid}

        last_run = ""
        last_run_at = status.get("at")
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
            "mode": launch_mode if running else self.run_mode(),
            "last_run": last_run,
            "last_result": _status_label(reported_status, str(last_error)),
            "error": "bridge_binary_missing" if command is None else "",
            "message": str(command or "随管理器打包的 desktop_antigravity_bridge 未找到"),
            "status": status,
            "agent_status": agent,
        }

    def bridge_command(self) -> list[str] | None:
        if getattr(sys, "frozen", False):
            return [sys.executable]
        runner_candidates = (
            self.project_root / "stock-strategy" / "tools" / "run_desktop_antigravity_bridge.py",
            self.project_root / "stock_standalone" / "stock-strategy" / "tools" / "run_desktop_antigravity_bridge.py",
        )
        runner = next((path for path in runner_candidates if path.is_file()), None)
        return [sys.executable, str(runner)] if runner else None

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
                "key_file": section.get("ipc_key_file", "") or str(runtime / "peer.key"),
            }
        except (OSError, configparser.Error, KeyError, TypeError):
            return {}

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

    def _start_bridge(self, run_mode: str | None = None) -> str:
        command = self.bridge_command()
        if not command:
            raise FileNotFoundError("run_desktop_antigravity_bridge.py not found")
        if self.task_info().get("running"):
            return "already_running"
        self.runtime_path().mkdir(parents=True, exist_ok=True)
        try:
            (self.runtime_path() / "stop.request").unlink()
        except FileNotFoundError:
            pass

        backend = self._read_config(self.runtime_root).get("backend") or DEFAULT_BACKEND
        mode = run_mode or self.run_mode()
        arguments = (
            "--backend", backend,
            "--runtime", str(self.runtime_root),
            "--desktop-root", str(self.project_root),
            "--launch-mode", mode,
        )

        if mode == "thread":
            with self._thread_registry_lock:
                key = str(self.runtime_path().resolve())
                existing = self._thread_registry.get(key)
                if existing and existing.is_alive():
                    return "already_running"
                if getattr(sys, "frozen", False):
                    from run_desktop_antigravity_bridge import main as run_agv_main
                    th = threading.Thread(
                        target=run_agv_main,
                        kwargs={"argv": list(arguments)},
                        name="stock-agv-manager-thread",
                        daemon=False,
                    )
                    self._thread_registry[key] = th
                    th.start()
                    return "started"
                runner_candidates = (
                    self.project_root / "stock-strategy" / "tools" / "run_desktop_antigravity_bridge.py",
                    self.project_root / "stock_standalone" / "stock-strategy" / "tools" / "run_desktop_antigravity_bridge.py",
                )
                runner = next((p for p in runner_candidates if p.is_file()), None)
                if not runner:
                    raise FileNotFoundError("run_desktop_antigravity_bridge.py not found")
                import importlib.util
                spec = importlib.util.spec_from_file_location("run_desktop_antigravity_bridge", str(runner))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                th = threading.Thread(
                    target=mod.main,
                    kwargs={"argv": list(arguments)},
                    name="stock-agv-manager-thread",
                    daemon=False,
                )
                self._thread_registry[key] = th
                th.start()
                return "started"

        if getattr(sys, "frozen", False):
            command = [sys.executable, "--antigravity-bridge-worker"]
        command = [*command, *arguments]
        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            )
        worker_env = (
            {
                **os.environ,
                "PYINSTALLER_RESET_ENVIRONMENT": "1",
                "PYQUANT3_ANTIGRAVITY_BRIDGE_WORKER": "1",
                "PYQUANT3_ANTIGRAVITY_BRIDGE_ARGS": json.dumps(list(arguments)),
            }
            if getattr(sys, "frozen", False)
            else None
        )
        output_path = self.runtime_root / "agent-output.txt"
        with output_path.open("ab") as output:
            process = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creationflags,
                env=worker_env,
            )
        time.sleep(0.3)
        if process.poll() is not None:
            if process.returncode == 0 and self.task_info().get("running"):
                return "started"
            status = _read_json(self.runtime_root / "status.json")
            error_code = status.get("error_code") or status.get("status") or "unknown"
            raise RuntimeError(f"AGV 桥接进程启动后立即退出，退出码 {process.returncode}，状态 {error_code}；查看日志：{output_path}")
        return "started"

    def perform(self, operation: str, enabled: bool = False, run_mode: str | None = None) -> str:
        if operation == "autostart":
            self.set_autostart_enabled(enabled)
            if enabled and not self.task_info().get("running"):
                try:
                    return self._start_bridge(run_mode)
                except Exception:
                    self.set_autostart_enabled(False)
                    raise
            return "enabled" if enabled else "disabled"
        if operation == "start":
            return self._start_bridge(run_mode)
        if operation == "stop":
            self._request_bridge_stop(str(time.time()))
            return "stop_requested"
        raise ValueError(f"unknown operation: {operation}")

    def start_if_enabled(self) -> str:
        if not self.autostart_enabled():
            return "disabled"
        if self.task_info().get("running"):
            return "already_running"
        return self._start_bridge()

    def shutdown_for_manager_exit(self):
        info = self.task_info()
        if not info.get("running"):
            return
        active_mode = info.get("mode") or self.run_mode()
        if active_mode != "thread" and not self.stop_on_manager_exit_enabled(active_mode):
            return
        try:
            self._request_bridge_stop("manager-exit")
        except OSError:
            return

    def read_history(self, limit: int = 40) -> list[dict]:
        db_path = self.runtime_path() / "agent" / "agent.db"
        if not db_path.is_file():
            return []
        rows_out = []
        db = None
        try:
            db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=1)
            with db:
                db.execute("PRAGMA query_only=ON")
                for table, kind in (("chat_results", "AI 对话"), ("results", "策略研究")):
                    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    if not exists:
                        continue
                    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                    if not {"id", "result"}.issubset(columns):
                        continue
                    selected = ["rowid", "id", "result"]
                    selected.extend(name for name in ("thread_id", "created_at") if name in columns)
                    order_by = "created_at DESC" if "created_at" in columns else "rowid DESC"
                    for row in db.execute(f"SELECT {', '.join(selected)} FROM {table} ORDER BY {order_by} LIMIT ?", (limit,)):
                        values = dict(zip(selected, row))
                        raw = values.get("result")
                        try:
                            result = json.loads(raw) if isinstance(raw, str) else {}
                        except (ValueError, TypeError):
                            result = {}
                        if not isinstance(result, dict):
                            result = {}
                        task_id = str(values.get("id") or "")
                        created_at = values.get("created_at")
                        stamp, completed = _history_timestamp(result.get("completed_at") or created_at)
                        error_code = result.get("error_code") or result.get("error")
                        status = _status_label(result.get("status") or ("failed" if error_code else "completed"), str(error_code or ""))
                        summary = result.get("content") or result.get("answer") or result.get("headline") or result.get("overall_assessment") or ""
                        detail = json.dumps(result, ensure_ascii=False, indent=2, default=str)
                        rows_out.append({
                            "kind": kind, "id": task_id, "model": str(result.get("model") or ""),
                            "status": status, "completed_at": completed,
                            "thread_id": str(result.get("thread_id") or values.get("thread_id") or ""),
                            "summary": " ".join(str(summary).split())[:500], "details": detail,
                            "order": stamp or float(values.get("rowid") or 0),
                        })
        except (sqlite3.Error, OSError, ValueError):
            return []
        finally:
            if db is not None:
                db.close()
        rows_out.sort(key=lambda item: item["order"], reverse=True)
        return rows_out[:limit]

    def backend_bridge_inventory(self, config: dict, force: bool = False) -> dict:
        backend = str(config.get("backend") or "").rstrip("/")
        node = str(config.get("node_id") or "")
        workspace = str(config.get("workspace_id") or "")
        key_file = str(config.get("key_file") or "")
        cache_key = (backend, node, workspace, key_file)
        now = time.monotonic()
        with self._backend_inventory_lock:
            ttl = 15 if self._backend_inventory_cache.get("ok") else 5
            if not force and cache_key == self._backend_inventory_cache_key and now - self._backend_inventory_cache_at < ttl:
                return self._backend_inventory_cache
        try:
            if not backend or not node or not workspace or not key_file:
                raise ValueError("bridge_identity_missing")
            raw_key = Path(key_file).read_bytes().strip()
            key = bytes.fromhex(raw_key.decode("ascii")) if len(raw_key) == 64 else raw_key
            if len(key) < 32:
                raise ValueError("bridge_key_invalid")
            path = "/api/v1/linkage/targets"
            timestamp = str(int(time.time()))
            nonce = secrets.token_hex(24)
            body_hash = hashlib.sha256(b"").hexdigest()
            canonical = "\n".join(("GET", path, body_hash, timestamp, nonce, node, workspace))
            signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
            request = Request(
                backend + path,
                headers={
                    "Accept": "application/json",
                    "X-Linkage-Node-ID": node,
                    "X-Linkage-Workspace-ID": workspace,
                    "X-Linkage-Timestamp": timestamp,
                    "X-Linkage-Nonce": nonce,
                    "X-Linkage-Signature": signature,
                },
                method="GET",
            )
            with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=5) as response:
                raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise ValueError("bridge_inventory_too_large")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("targets"), list):
                raise ValueError("bridge_inventory_invalid")
            targets = []
            for target in payload["targets"][:64]:
                if not isinstance(target, dict):
                    continue
                node_id = str(target.get("node_id") or "")
                workspace_id = str(target.get("workspace_id") or "")
                if not node_id or not workspace_id:
                    continue
                targets.append({
                    "node_id": node_id,
                    "workspace_id": workspace_id,
                    "label": str(target.get("label") or ""),
                    "provider": str(target.get("provider") or ""),
                    "status": str(target.get("status") or "configured"),
                    "online": str(target.get("online") or "").lower() == "true",
                    "desktop_status": str(target.get("desktop_status") or ""),
                    "heartbeat": str(target.get("heartbeat") or ""),
                    "chat_queued": str(target.get("chat_queued") or "0"),
                    "chat_running": str(target.get("chat_running") or "0"),
                    "chat_jobs_status": str(target.get("chat_jobs_status") or "status_unavailable"),
                })
            chat_target = payload.get("chat_target")
            if not isinstance(chat_target, dict):
                chat_target = {}
            strategy_target = payload.get("strategy_target")
            if not isinstance(strategy_target, dict):
                strategy_target = {}
            result = {
                "ok": True,
                "targets": targets,
                "default_node_id": str(payload.get("default_node_id") or ""),
                "chat_target": {
                    "provider": str(chat_target.get("provider") or "hermes"),
                    "node_id": str(chat_target.get("node_id") or ""),
                    "workspace_id": str(chat_target.get("workspace_id") or ""),
                },
                "strategy_target": {
                    "node_id": str(strategy_target.get("node_id") or ""),
                    "workspace_id": str(strategy_target.get("workspace_id") or ""),
                },
                "message": "",
            }
        except Exception as exc:
            detail = _agv_error_detail({
                "type": type(exc).__name__, "message": str(exc)[:220],
                "backend": backend, "status": getattr(exc, "code", None),
                "errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None),
            })
            result = {
                "ok": False, "targets": [],
                "message": f"后台桥名录读取失败：{type(exc).__name__}" + ("；" + detail if detail else ""),
            }
        with self._backend_inventory_lock:
            self._backend_inventory_cache_key = cache_key
            self._backend_inventory_cache_at = time.monotonic()
            self._backend_inventory_cache = result
        return result

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

    def read_logs(self) -> str:
        out = self._tail(self.runtime_path() / "agent-output.txt")
        return out or "暂无日志。"


class _BackendInventoryWorker(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict)
    history_ready = QtCore.pyqtSignal(list)

    def __init__(self, controller: AntigravityBridgeController, config: dict, force: bool = False, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config = config
        self.force = force

    def run(self):
        try:
            self.history_ready.emit(self.controller.read_history())
        except Exception:
            self.history_ready.emit([])
        try:
            self.ready.emit(self.controller.backend_bridge_inventory(self.config, force=self.force))
        except Exception as exc:
            self.ready.emit({"ok": False, "targets": [], "message": f"后台桥名录读取失败：{type(exc).__name__}"})


class AntigravityBridgeManagerDialog(QtWidgets.QDialog):
    """4-Tab Management Dialog for the Antigravity Desktop Bridge."""

    def __init__(self, project_root: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌟 Antigravity (AGV) 桌面桥管理器")
        self.resize(1020, 760)
        self.setMinimumSize(850, 620)
        self.controller = AntigravityBridgeController(project_root)
        self._inventory_worker = None
        self._force_inventory_refresh = False
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start()
        self.refresh_data()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog { background: #171a21; color: #d7dae0; }
            QLabel { color: #d7dae0; }
            QGroupBox { border: 1px solid #38404c; border-radius: 6px; margin-top: 10px; padding: 8px; color: #c084fc; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #293241; color: #e5e7eb; border: 1px solid #475569; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #334155; }
            QLineEdit, QPlainTextEdit, QTableWidget { background: #11151b; color: #d7dae0; border: 1px solid #303846; }
            QTabWidget::pane { border: 1px solid #38404c; }
        """)
        root = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("🌟 Antigravity 桌面桥")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #c084fc;")
        header.addWidget(title)
        header.addStretch()
        self.status_label = QtWidgets.QLabel("正在读取桥接状态…")
        header.addWidget(self.status_label)
        self.btn_refresh = QtWidgets.QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_data)
        header.addWidget(self.btn_refresh)
        root.addLayout(header)

        controls = QtWidgets.QHBoxLayout()
        self.btn_startup_management = QtWidgets.QPushButton("启动管理…")
        self.btn_startup_management.setToolTip("统一设置 Codex 与 Antigravity 桌面桥随管理器启动和退出的行为。")
        self.btn_startup_management.clicked.connect(self._open_startup_management)
        controls.addWidget(self.btn_startup_management)
        controls.addWidget(QtWidgets.QLabel("运行方式："))
        self.cmb_run_mode = QtWidgets.QComboBox()
        self.cmb_run_mode.addItem("独立进程", "process")
        self.cmb_run_mode.addItem("管理器线程", "thread")
        self.cmb_run_mode.setCurrentIndex(1 if self.controller.run_mode() == "thread" else 0)
        self.cmb_run_mode.currentIndexChanged.connect(self._run_mode_changed)
        controls.addWidget(self.cmb_run_mode)
        self.btn_start = QtWidgets.QPushButton("启动桥")
        self.btn_start.clicked.connect(self._start_bridge)
        controls.addWidget(self.btn_start)
        self.btn_stop = QtWidgets.QPushButton("请求停止")
        self.btn_stop.clicked.connect(self._stop_bridge)
        controls.addWidget(self.btn_stop)
        self.btn_probe = QtWidgets.QPushButton("🔄 立即检测")
        self.btn_probe.setText("🔄 检查后台")
        self.btn_probe.setToolTip("强制执行一次 HMAC 只读名录请求，核验后台连通、双桥登记及心跳；不会调用 AGY CLI 或模型。")
        self.btn_probe.clicked.connect(self._run_health_probe)
        controls.addWidget(self.btn_probe)
        controls.addStretch()
        root.addLayout(controls)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab 1: 状态与用量
        overview = QtWidgets.QWidget()
        ov_layout = QtWidgets.QVBoxLayout(overview)
        info_group = QtWidgets.QGroupBox("桥接与引擎状态")
        form = QtWidgets.QFormLayout(info_group)
        self.info = {}
        for key, label in (
            ("task", "桥接进程"), ("backend", "生产 API"), ("node", "桥接节点"),
            ("workspace", "工作区"), ("heartbeat", "后端心跳"), ("port", "网关端口 (26778)"),
            ("runtime", "运行目录"), ("engine", "AGY CLI 路径"), ("models", "可用 Gemini 模型"),
        ):
            val = QtWidgets.QLabel("—")
            val.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(True)
            self.info[key] = val
            form.addRow(label + "：", val)
        ov_layout.addWidget(info_group)

        quota_group = QtWidgets.QGroupBox("Gemini 配额与 Token 用量")
        quota_layout = QtWidgets.QVBoxLayout(quota_group)
        self.quota_label = QtWidgets.QLabel("模型目录: gemini-3.8-flash, gemini-3.8-pro, gemini-2.5-flash\n"
                                           "流式传输: agy stream-json 管道 (200ms 防抖发布)\n"
                                           "调度定位: 盘中秒级异动速问优选 / 策略逐股条件分析")
        quota_layout.addWidget(self.quota_label)
        ov_layout.addWidget(quota_group)
        ov_layout.addStretch()
        self.tabs.addTab(overview, "状态与用量")

        # Tab 2: 后台桥名录
        inventory_tab = QtWidgets.QWidget()
        inv_layout = QtWidgets.QVBoxLayout(inventory_tab)
        self.inventory_summary = QtWidgets.QLabel("正在读取后台桥名录…")
        self.inventory_summary.setWordWrap(True)
        self.inventory_summary.setStyleSheet("color: #93c5fd; padding: 6px;")
        inv_layout.addWidget(self.inventory_summary)
        self.inv_table = QtWidgets.QTableWidget(0, 5)
        self.inv_table.setHorizontalHeaderLabels(["状态", "桥标识", "当前用途", "后台对话", "最近心跳"])
        self.inv_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inv_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.inv_table.setWordWrap(False)
        self.inv_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.inv_table.verticalHeader().setVisible(False)
        self.inv_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        inv_layout.addWidget(self.inv_table, 1)
        self.tabs.addTab(inventory_tab, "后台桥名录")

        # Tab 3: 运行任务与历史
        history_tab = QtWidgets.QWidget()
        hist_layout = QtWidgets.QVBoxLayout(history_tab)
        self.active_label = QtWidgets.QLabel("最近任务：本机记录")
        self.active_label.setWordWrap(True)
        self.active_label.setStyleSheet("color: #fbbf24; padding: 4px;")
        hist_layout.addWidget(self.active_label)
        self.hist_table = QtWidgets.QTableWidget(0, 7)
        self.hist_table.setHorizontalHeaderLabels(["类型", "任务 ID", "模型", "Thread", "状态", "完成时间", "摘要"])
        self.hist_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.hist_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.hist_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.hist_table.setWordWrap(False)
        self.hist_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.horizontalHeader().setStretchLastSection(True)
        self.hist_table.currentCellChanged.connect(self._show_history_detail)
        hist_layout.addWidget(self.hist_table, 1)
        self.history_detail = QtWidgets.QPlainTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setMaximumHeight(180)
        self.history_detail.setPlaceholderText("选择一条任务查看本机缓存的完整回执。")
        hist_layout.addWidget(self.history_detail)
        self.tabs.addTab(history_tab, "运行任务与历史")

        # Tab 4: 桥接日志
        log_tab = QtWidgets.QWidget()
        log_layout = QtWidgets.QVBoxLayout(log_tab)
        self.log_status_label = QtWidgets.QLabel("最新状态：等待桥接日志")
        self.log_status_label.setWordWrap(True)
        self.log_status_label.setStyleSheet("color: #94a3b8; padding: 4px;")
        log_layout.addWidget(self.log_status_label)
        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background: #0d1117; color: #58a6ff; font-family: Consolas, monospace;")
        log_layout.addWidget(self.log_text)
        self.tabs.addTab(log_tab, "桥接日志")

    def _open_startup_management(self):
        opener = getattr(self.parent(), "open_bridge_startup_manager", None)
        if callable(opener):
            opener()

    def _run_mode_changed(self, idx: int):
        mode = self.cmb_run_mode.currentData()
        self.controller.set_run_mode(mode)
        self.refresh_data()

    def _start_bridge(self):
        try:
            self.controller.perform("start", run_mode=self.cmb_run_mode.currentData())
            QtWidgets.QMessageBox.information(self, "启动", "Antigravity 桌面桥启动指令已下发。")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "启动失败", f"启动失败：{e}")
        self.refresh_data()

    def _stop_bridge(self):
        self.controller.perform("stop")
        QtWidgets.QMessageBox.information(self, "停止", "停止请求已下发。")
        self.refresh_data()

    def _run_health_probe(self):
        if self._inventory_worker and self._inventory_worker.isRunning():
            self._force_inventory_refresh = True
            self.inventory_summary.setText("当前状态读取完成后，将强制检查一次后台连通与双桥名录…")
            return
        self.refresh_data(force_inventory=True)

    def refresh_data(self, force_inventory: bool = False):
        info = self.controller.task_info()
        running = info.get("running", False)
        self.status_label.setText("🟢 运行中" if running else "⚪ 未运行")
        self.status_label.setStyleSheet("color: #4ade80;" if running else "color: #94a3b8;")

        config = self.controller._read_config(self.controller.runtime_path())
        status = info.get("status") or {}
        agent = info.get("agent_status") or {}
        detail = agent.get("detail") if isinstance(agent.get("detail"), dict) else {}

        self.info["task"].setText(
            f"PID: {status.get('agent_pid', '—')} ({info.get('mode', 'process')})"
        )
        self.info["backend"].setText(str(config.get("backend") or DEFAULT_BACKEND))
        node_id = str(status.get("node_id") or config.get("node_id") or "")
        workspace_id = str(status.get("workspace_id") or config.get("workspace_id") or "")
        self.info["node"].setText(_short_bridge_id(node_id))
        self.info["node"].setToolTip(node_id)
        self.info["workspace"].setText(_short_bridge_id(workspace_id))
        self.info["workspace"].setToolTip(workspace_id)
        try:
            heartbeat_epoch = float(agent.get("updated_epoch") or 0)
            heartbeat_age = time.time() - heartbeat_epoch if heartbeat_epoch else None
        except (TypeError, ValueError, OverflowError):
            heartbeat_age = None
        self.info["heartbeat"].setText(
            f"{int(max(0, heartbeat_age))} 秒前" if heartbeat_age is not None and heartbeat_age <= 90
            else "后端心跳缺失或已过期"
        )
        remote_status = str(agent.get("status") or status.get("status") or "unknown")
        log_status = "%s；后台最近状态：%s" % (
            "桥接运行中" if running else "桥接未运行", _status_label(remote_status),
        )
        if heartbeat_age is not None:
            log_status += "；最近心跳 %s 秒前" % int(max(0, heartbeat_age))
            if heartbeat_age > 90:
                log_status += "（已过期）"
        else:
            log_status += "；没有本机心跳记录"
        last_error = detail.get("error_code") or detail.get("heartbeat_error") or status.get("error_code")
        if last_error:
            error_detail = detail.get("error_detail") or detail.get("heartbeat_error_detail") or status.get("error_detail")
            detail_text = _agv_error_detail(error_detail)
            log_status += "；最近错误：" + _agv_error_label(last_error) + ("（" + detail_text + "）" if detail_text else "")
        self.log_status_label.setText("最新状态：" + log_status + "。")
        self.info["port"].setText(str(status.get("port") or 26778))
        self.info["runtime"].setText(str(self.controller.runtime_path()))
        self.info["engine"].setText(str(detail.get("engine") or detail.get("engine_path") or "agy CLI (自动探测)"))
        self.info["models"].setText(", ".join(_model_display_names(detail.get("models"))))

        if self._inventory_worker is None or not self._inventory_worker.isRunning():
            self.inventory_summary.setText("正在强制检查后台连通…" if force_inventory else "正在读取后台桥名录…")
            worker = _BackendInventoryWorker(self.controller, config, force=force_inventory, parent=self)
            worker.ready.connect(self._render_backend_inventory)
            worker.history_ready.connect(self._render_history)
            worker.finished.connect(lambda current=worker: self._clear_inventory_worker(current))
            worker.finished.connect(worker.deleteLater)
            self._inventory_worker = worker
            worker.start()

        logs = _format_agv_logs(self.controller.read_logs())
        if self.log_text.toPlainText() != logs:
            self.log_text.setPlainText(logs)

    def _clear_inventory_worker(self, worker):
        if self._inventory_worker is worker:
            self._inventory_worker = None
        if self._force_inventory_refresh:
            self._force_inventory_refresh = False
            QtCore.QTimer.singleShot(0, lambda: self.refresh_data(force_inventory=True))

    def _render_history(self, history: list):
        records = [record for record in history if isinstance(record, dict)]
        self.hist_table.setRowCount(len(records))
        columns = ("kind", "id", "model", "thread_id", "status", "completed_at", "summary")
        for row, record in enumerate(records):
            for column, key in enumerate(columns):
                item = QtWidgets.QTableWidgetItem(str(record.get(key) or "—"))
                if column == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, record.get("details") or "")
                self.hist_table.setItem(row, column, item)
        self.active_label.setText(
            "本机任务历史：最近 %d 条" % len(records)
            + (" · 最新完成 " + str(records[0].get("completed_at") or "时间未知") if records else " · 暂无已缓存任务")
        )
        if records:
            self.hist_table.selectRow(0)
        else:
            self.history_detail.setPlainText("暂无本机缓存的任务回执。")

    def _show_history_detail(self, row: int, _column: int, _previous_row: int, _previous_column: int):
        item = self.hist_table.item(row, 0) if row >= 0 else None
        details = item.data(QtCore.Qt.ItemDataRole.UserRole) if item else ""
        self.history_detail.setPlainText(str(details or "没有可显示的结果内容。")[:12000])

    def _render_backend_inventory(self, inventory: dict):
        if not isinstance(inventory, dict) or not inventory.get("ok"):
            self.inv_table.setRowCount(0)
            self.inventory_summary.setText(
                str((inventory or {}).get("message") or "后台桥名录暂不可用。")
                if isinstance(inventory, dict) else "后台桥名录响应无效。"
            )
            return

        targets = [target for target in inventory.get("targets", []) if isinstance(target, dict)]
        config = self.controller._read_config(self.controller.runtime_path())
        local_node = str(config.get("node_id") or "")
        local_workspace = str(config.get("workspace_id") or "")
        chat = inventory.get("chat_target") or {}
        if not isinstance(chat, dict):
            chat = {}
        chat_provider = str(chat.get("provider") or "")
        chat_node = str(chat.get("node_id") or "") if chat_provider in ("codex_desktop", "antigravity_desktop") else ""
        chat_workspace = str(chat.get("workspace_id") or "")
        strategy = inventory.get("strategy_target") or {}
        if not isinstance(strategy, dict):
            strategy = {}
        strategy_node = str(strategy.get("node_id") or "")
        strategy_workspace = str(strategy.get("workspace_id") or "")
        default_node = str(inventory.get("default_node_id") or "")

        chat_label = "Hermes" if chat_provider == "hermes" else "未设置"
        if chat_node:
            selected = next((target for target in targets if target.get("node_id") == chat_node and target.get("workspace_id") == chat_workspace), None)
            chat_label = (_bridge_target_name(selected) if selected else ("Antigravity" if chat_provider == "antigravity_desktop" else "Codex")) + " · " + _short_bridge_id(chat_node) + " / " + _short_bridge_id(chat_workspace)

        self.inv_table.setRowCount(len(targets))
        local_found = False
        for row, target in enumerate(targets):
            node = str(target.get("node_id") or "")
            workspace = str(target.get("workspace_id") or "")
            is_local = node == local_node and workspace == local_workspace
            is_chat = bool(chat_node and node == chat_node and workspace == chat_workspace)
            is_strategy = bool(strategy_node and node == strategy_node and workspace == strategy_workspace)
            is_default = bool(default_node and node == default_node)
            local_found = local_found or is_local
            online = target.get("online") is True or str(target.get("online") or "").lower() == "true"
            desktop_status = str(target.get("desktop_status") or "")
            if online:
                state = "在线 · " + {"analyzing": "处理中", "ready": "空闲"}.get(desktop_status, _status_label(desktop_status))
            elif desktop_status == "status_unavailable":
                state = "状态不可读"
            elif target.get("heartbeat"):
                state = "心跳过期"
            else:
                state = "已登记 · 无心跳"
            roles = []
            if is_local:
                roles.append("本机")
            if is_chat:
                roles.append("Web 对话")
            if is_strategy:
                roles.append("策略研究")
            if is_default:
                roles.append("默认联动")
            if target.get("chat_jobs_status") == "status_unavailable":
                chat_jobs = "读取失败"
            else:
                chat_jobs = "运行 %s · 排队 %s" % (target.get("chat_running", "0"), target.get("chat_queued", "0"))
            identity = _short_bridge_id(node) + " / " + _short_bridge_id(workspace)
            values = (state, _bridge_target_name(target) + " · " + identity, " / ".join(roles) or "—", chat_jobs, _format_inventory_heartbeat(target.get("heartbeat")))
            details = "节点 ID：%s\n工作区 ID：%s\n状态：%s\n最近心跳：%s" % (
                node, workspace, desktop_status or "未上报", target.get("heartbeat") or "无",
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setToolTip(details)
                if is_local:
                    item.setBackground(QtGui.QBrush(QtGui.QColor("#243b55")))
                self.inv_table.setItem(row, column, item)

        strategy_label = _short_bridge_id(strategy_node) + " / " + _short_bridge_id(strategy_workspace) if strategy_node else "未设置"
        default_label = _short_bridge_id(default_node) if default_node else "未设置"
        local_label = _short_bridge_id(local_node) + " / " + _short_bridge_id(local_workspace)
        local_target = next((target for target in targets if target.get("node_id") == local_node and target.get("workspace_id") == local_workspace), None)
        if not local_target:
            local_state = "本机桥未登记"
        elif local_target.get("online") is True or str(local_target.get("online") or "").lower() == "true":
            local_state = "本机桥在线 · " + _status_label(local_target.get("desktop_status"))
        elif local_target.get("heartbeat"):
            local_state = "本机桥心跳已过期"
        else:
            local_state = "本机桥已登记但无心跳"
        self.inventory_summary.setText(
            "后台登记 %d 个桥 · 本机：%s%s（%s）· Web 对话：%s · 策略研究：%s · 默认联动节点：%s。"
            "Codex 与 Antigravity 管理器均显示完整后台名录。" %
            (len(targets), local_label, "" if local_found else "（本机未登记）", local_state, chat_label, strategy_label, default_label)
        )

    def closeEvent(self, event):
        self.timer.stop()
        worker = self._inventory_worker
        if worker and worker.isRunning() and not worker.wait(1000):
            self.status_label.setText("后台桥名录读取尚未结束，请稍后关闭窗口。")
            event.ignore()
            return
        super().closeEvent(event)

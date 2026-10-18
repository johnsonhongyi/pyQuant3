# -*- coding: utf-8 -*-
"""Local management UI for the independent Codex desktop bridge."""

from __future__ import annotations

import configparser
import hashlib
import hmac
import secrets
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
from urllib.request import HTTPRedirectHandler, Request, ProxyHandler, build_opener

from PyQt6 import QtCore, QtGui, QtWidgets
from .bridge_token_usage import token_usage_text


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
        return f"失败（{_friendly_error_code(error_code)}）"
    raw = str(status or "").strip()
    return _STATUS_LABELS.get(raw.lower(), raw or "状态未知")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _short_bridge_id(value: str) -> str:
    raw = str(value or "").strip()
    for prefix in ("codex-", "agv-", "ws-", "tk-"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
            break
    return raw[:8] or "—"


def _bridge_target_name(label: str, node_id: str = "", provider: str = "") -> str:
    raw = str(label or "").strip()
    if str(node_id or "").strip().lower().startswith("agv-") or "antigravity" in str(provider or "").lower() or "antigravity" in raw.lower():
        return "Antigravity"
    if not raw or raw.lower().startswith("desktop codex") or "ats ai bridge" in raw.lower():
        return "Codex"
    return raw[:32]

def _parse_bridge_heartbeat(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            numeric = float(raw)
        except (ValueError, TypeError, OverflowError):
            numeric = None
    if numeric is not None:
        magnitude = abs(numeric)
        if magnitude >= 1e17:
            numeric /= 1e9
        elif magnitude >= 1e14:
            numeric /= 1e6
        elif magnitude >= 1e11:
            numeric /= 1e3
        try:
            return datetime.fromtimestamp(numeric).astimezone()
        except (ValueError, TypeError, OSError, OverflowError):
            return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    fraction_start = raw.find(".")
    if fraction_start >= 0:
        offsets = [position for position in (raw.find("+", fraction_start), raw.find("-", fraction_start)) if position >= 0]
        offset_start = min(offsets) if offsets else len(raw)
        fraction = raw[fraction_start + 1:offset_start]
        if fraction.isdigit() and len(fraction) > 6:
            raw = raw[:fraction_start + 1] + fraction[:6] + raw[offset_start:]
    for candidate in (raw, raw.replace(" UTC", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).astimezone()
        except (ValueError, TypeError, OSError, OverflowError):
            continue
    return None


def _format_bridge_heartbeat(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "未记录"
    stamp = _parse_bridge_heartbeat(value)
    if stamp is None:
        return "时间不可解析"
    age = (datetime.now().astimezone() - stamp).total_seconds()
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
    return stamp.strftime("%m-%d %H:%M:%S") + " · " + relative

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
    key = raw.lower()
    labels = {
        "timeout": "请求超时", "timeouterror": "等待响应超时",
        "model_timeout": "Codex 响应超时", "rpc_timeout": "Codex 引擎通信超时",
        "connectionerror": "连接失败", "connectionrefusederror": "连接被拒绝",
        "remotedisconnected": "后端主动关闭连接", "urlerror": "网络地址不可达",
        "oserror": "本机或网络 I/O 失败", "permissionerror": "本机路径无权限",
        "filenotfounderror": "本机文件或目录不存在", "connectionreseterror": "网络连接被重置",
        "agent_status_write_failed": "本机桥状态文件写入失败",
        "stop_request_cleanup_failed": "停止标记清理失败",
        "chat_result_oserror": "对话结果写回时发生网络 I/O 错误",
        "chat_result_timeout": "对话结果写回超时",
        "chat_result_remote_disconnected": "结果写回连接被后端关闭",
        "chat_claim_timeout": "领取 Web 任务超时",
        "chat_claim_url_error": "无法连接 Web 后端领取任务",
        "app_server_start_oserror": "Codex 引擎启动或管道通信失败",
        "thread_resume_oserror": "恢复 Codex 会话失败",
        "thread_start_oserror": "创建 Codex 会话失败",
        "result_writeback_oserror": "策略结果写回时发生网络 I/O 错误",
        "backend_register_timeout": "桥注册到 Web 后端超时",
        "backend_register_url_error": "桥无法连接 Web 后端完成注册",
    }
    if key in labels:
        return labels[key]
    for prefix, label in (("chat_result_http_", "对话回执接口返回 HTTP "), ("result_http_", "策略回执接口返回 HTTP "), ("heartbeat_http_", "桥心跳接口返回 HTTP "), ("chat_claim_http_", "任务领取接口返回 HTTP "), ("claim_http_", "任务领取接口返回 HTTP "), ("backend_register_http_", "桥注册接口返回 HTTP ")):
        if key.startswith(prefix):
            return label + key[len(prefix):]
    for suffix, label in (("_oserror", "发生本机或网络 I/O 错误"), ("_timeout", "等待超时"), ("_url_error", "网络地址不可达"), ("_remote_disconnected", "连接被后端关闭")):
        if key.endswith(suffix):
            stage = key[:-len(suffix)]
            return _STAGE_LABELS.get(stage, stage.replace("_", " ")) + "：" + label
    return raw.replace("_", " ")


def _friendly_error_detail(value) -> str:
    if not isinstance(value, dict):
        return " ".join(str(value or "").split())[:260]
    parts = []
    winerror = value.get("winerror")
    errno = value.get("errno")
    code = winerror if winerror is not None else errno
    code_labels = {
        2: "文件不存在", 3: "目录不存在", 5: "访问被拒绝", 13: "访问被拒绝",
        32: "文件正被其他进程占用", 33: "文件锁冲突", 10054: "远端重置连接",
        10060: "网络请求超时", 10061: "后端拒绝连接",
    }
    kind = str(value.get("cause_type") or value.get("type") or "").lower()
    kind_labels = {"oserror":"系统 I/O 错误", "permissionerror":"文件访问被拒绝", "filenotfounderror":"文件或目录不存在", "connectionrefusederror":"后端拒绝连接", "connectionreseterror":"连接被重置", "remotedisconnected":"后端主动关闭连接", "urlerror":"网络地址不可达"}
    if code in code_labels:
        parts.append(code_labels[code])
    elif kind in ("timeout", "timeouterror", "socket.timeout"):
        parts.append("等待响应超时")
    elif kind in kind_labels:
        parts.append(kind_labels[kind])
    elif kind:
        parts.append(kind.replace("error", "错误").replace("os", "系统"))
    message = str(value.get("message") or "").strip()
    if message and message not in parts:
        parts.append(message[:180])
    path = value.get("path") or value.get("path2")
    if path:
        parts.append("路径 " + str(path)[:220])
    backend = value.get("backend")
    if backend:
        parts.append("后端 " + str(backend)[:120])
    return "；".join(parts)[:420]


_STAGE_LABELS = {
    "stop_check": "停止检查", "model_catalog_refresh": "刷新模型目录",
    "desktop_runtime_discovery": "发现桌面运行环境", "backend_ready_heartbeat": "发送后端心跳",
    "strategy_job_claim": "领取策略任务", "chat_job_claim": "领取 Web 对话任务",
    "chat_job_run": "运行 Web 对话", "strategy_context_validate": "校验策略任务",
    "strategy_app_server_start": "启动 Codex 引擎", "strategy_codex_turn": "等待 Codex 分析",
    "strategy_result_writeback": "回写策略结果", "local_status_write": "写入本机状态",
    "app_server_start": "启动 Codex 引擎", "project_setup": "准备 Codex 工作区",
    "thread_resume": "恢复 Codex 会话", "thread_start": "创建 Codex 会话",
    "thread_label": "标记 Codex 会话", "turn_start": "提交 Codex 请求",
    "codex_reply": "等待 Codex 回复", "result_cache": "保存本机回执",
    "result_writeback": "回写 Web 结果", "backend_register": "桥注册",
}


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
        error_info = payload.get("error_detail") if isinstance(payload.get("error_detail"), dict) else {}
        stage = payload.get("stage") or error_info.get("stage")
        if stage:
            details.append("阶段 " + _STAGE_LABELS.get(str(stage), str(stage)))
        operation = payload.get("operation") or error_info.get("operation")
        if operation:
            details.append("操作 " + str(operation))
        error_detail = _friendly_error_detail(error_info)
        if error_detail:
            details.append("详情 " + error_detail)
        if payload.get("retry_after_seconds"):
            details.append("将在 %s 秒后重试" % payload["retry_after_seconds"])
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
        detail_text = _friendly_error_detail(detail.get("error_detail"))
        status_text += f"；最近错误：{_friendly_error_code(error_code)}" + ("（" + detail_text + "）" if detail_text else "")

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
        self._backend_inventory_cache_key = None
        self._backend_inventory_cache_at = 0.0
        self._backend_inventory_cache = {"ok": False, "targets": []}
        self._backend_inventory_lock = threading.Lock()

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
        # bridge.pid can outlive a stopped worker and later be reused by an
        # unrelated process (for example Codex's Node runtime). Require an
        # active status and verify the recorded process identity before treating
        # that PID as the bridge.
        running = False
        if status.get("status") in active_statuses:
            for candidate in dict.fromkeys((pid, status_pid)):
                if candidate > 0 and _bridge_owner_is_alive(
                        candidate, self.runtime_path(), status_at, launch_mode):
                    pid = candidate
                    running = True
                    break
        # A packaged onefile worker runs inside the manager's process tree, so
        # bridge.pid points at the manager/bootloader PID rather than a child.
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
        if launch_mode == "thread" and status_pid == os.getpid():
            with self._thread_registry_lock:
                thread = self._thread_registry.get(str(self.runtime_root).casefold())
                running = bool(thread and thread.is_alive())
        elif launch_mode == "process" and pid == os.getpid():
            running = False
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
            "mode": (status.get("launch_mode") or self.run_mode()) if running else self.run_mode(),
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
        # Source launches may start from the monorepo, strategy root, or a
        # nested development directory. Probe ancestors without walking trees.
        checked = set()
        for anchor in (self.project_root.resolve(), Path(__file__).resolve().parent):
            for root in (anchor, *anchor.parents):
                for relative in (
                    "tools/run_desktop_strategy_bridge.py",
                    "stock-strategy/tools/run_desktop_strategy_bridge.py",
                    "stock_standalone/stock-strategy/tools/run_desktop_strategy_bridge.py",
                ):
                    candidate = root / relative
                    if candidate in checked:
                        continue
                    checked.add(candidate)
                    if candidate.is_file():
                        return [sys.executable, str(candidate)]
        return None

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

    def manager_exit_shutdown_forced(self, mode: str | None = None) -> bool:
        return (mode or self.run_mode()) == "thread"

    def stop_on_manager_exit_enabled(self, mode: str | None = None) -> bool:
        if self.manager_exit_shutdown_forced(mode):
            return True
        return bool(_read_json(self.preference_path).get("stop_with_manager", False))

    def set_stop_on_manager_exit_enabled(self, enabled: bool) -> None:
        self._write_preferences(stop_with_manager=bool(enabled))

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
                "key_file": section.get("ipc_key_file", "") or str(runtime / "peer.key"),
            }
        except (OSError, configparser.Error, KeyError, TypeError):
            return {}

    def backend_bridge_inventory(self, config: dict) -> dict:
        backend = str(config.get("backend") or "").rstrip("/")
        node = str(config.get("node_id") or "")
        workspace = str(config.get("workspace_id") or "")
        key_file = str(config.get("key_file") or "")
        cache_key = (backend, node, workspace, key_file)
        now = time.monotonic()
        with self._backend_inventory_lock:
            ttl = 15 if self._backend_inventory_cache.get("ok") else 5
            if cache_key == self._backend_inventory_cache_key and now - self._backend_inventory_cache_at < ttl:
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
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result = {
                "ok": False,
                "targets": [],
                "default_node_id": "",
                "chat_target": {},
                "message": "后台桥名录读取失败：" + _friendly_error_code(type(exc).__name__) + ("；" + _friendly_error_detail({"type":type(exc).__name__,"message":str(exc)[:220],"path":getattr(exc,"filename",None)}) if str(exc) or getattr(exc,"filename",None) else ""),
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
        backend_targets = self.backend_bridge_inventory(config)
        heartbeat = float(agent.get("updated_epoch") or 0)
        age = max(0, time.time() - heartbeat) if heartbeat else None
        if task.get("running") and age is not None and age <= 90 and agent.get("status"):
            parent = {**parent, "status": agent["status"], "agent_pid": parent.get("agent_pid") or task.get("status", {}).get("agent_pid"),
                      "port": parent.get("port") or 26776}
        desktop = (agent.get("detail") or {}).get("desktop_runtime") or {}
        db_path = runtime / "agent" / "agent.db"
        result = {
            "task": task, "runtime": str(runtime), "parent": parent, "agent": agent,
            "config": config, "backend_targets": backend_targets, "heartbeat_age": age, "desktop": desktop,
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
            self._request_bridge_stop("manager-request")
            return "已请求停止；当前任务完成后会退出"
        raise ValueError("unsupported bridge operation")

    def _request_bridge_stop(self, reason: str) -> None:
        stop_request = self.runtime_path() / "agent" / "stop.request"
        stop_request.parent.mkdir(parents=True, exist_ok=True)
        pending = stop_request.with_suffix(".pending")
        pending.write_text(str(reason) + "\n", encoding="utf-8")
        os.replace(pending, stop_request)

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
        output_path = self.runtime_root / "agent-output.txt"
        with output_path.open("ab") as output:
            process = subprocess.Popen(
                command, cwd=str(self.project_root), stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT,
                close_fds=True, creationflags=creationflags,
                env=worker_env,
            )
        time.sleep(0.3)
        if process.poll() is not None:
            if process.returncode == 0 and self.task_info().get("running"):
                return
            status = _read_json(self.runtime_root / "status.json")
            error_code = status.get("error_code") or status.get("status") or "unknown"
            details = _friendly_error_code(error_code)
            error_detail = _friendly_error_detail(status.get("error_detail"))
            if error_detail:
                details += "（" + error_detail + "）"
            raise RuntimeError(f"桥接进程启动后立即退出，退出码 {process.returncode}，状态 {details}；查看桥接日志：{self.runtime_root / 'agent-output.txt'}")

    @staticmethod
    def _run_bridge_thread(command: list[str], arguments: tuple[str, ...]) -> None:
        try:
            if getattr(sys, "frozen", False):
                from run_desktop_strategy_bridge import main as run_bridge
            else:
                import importlib.util
                runner_path = Path(os.path.abspath(command[1]))
                spec = importlib.util.spec_from_file_location("_codex_desktop_bridge_runner", runner_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load desktop bridge runner: {runner_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                run_bridge = module.main
            run_bridge(list(arguments))
        except (OSError, RuntimeError, ValueError, TypeError, ImportError) as exc:
            runtime_arg = next((arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == "--runtime"), "")
            if runtime_arg:
                path = Path(runtime_arg) / "status.json"
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    pending = path.with_suffix(".pending")
                    detail = {"type":type(exc).__name__, "message":str(exc)[:320], "stage":"manager_thread_start"}
                    record = {"status":"degraded", "error_code":type(exc).__name__, "stage":"manager_thread_start", "error_detail":detail, "at":time.time(), "agent_pid":os.getpid(), "launch_mode":"thread"}
                    pending.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                    os.replace(pending, path)
                    with (Path(runtime_arg) / "agent-output.txt").open("ab") as output:
                        output.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
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
        """Request a graceful bridge stop when configured (thread mode is tied to this process)."""
        task = self.task_info()
        if not task.get("running"):
            return
        active_mode = task.get("mode") or self.run_mode()
        if active_mode != "thread" and not self.stop_on_manager_exit_enabled(active_mode):
            return
        try:
            owner_pid = int((task.get("status") or {}).get("agent_pid") or 0)
        except (TypeError, ValueError):
            owner_pid = 0
        if active_mode == "thread" and owner_pid and owner_pid != os.getpid():
            return
        self._request_bridge_stop("manager-exit")


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
        self.btn_startup_management = QtWidgets.QPushButton("启动管理…")
        self.btn_startup_management.setToolTip("统一设置 Codex 与 Antigravity 桌面桥随管理器启动和退出的行为。")
        self.btn_startup_management.clicked.connect(self._open_startup_management)
        controls.addWidget(self.btn_startup_management)
        controls.addWidget(QtWidgets.QLabel("运行方式："))
        self.cmb_run_mode = QtWidgets.QComboBox()
        self.cmb_run_mode.addItem("独立进程", "process")
        self.cmb_run_mode.addItem("管理器线程", "thread")
        self.cmb_run_mode.setFixedWidth(140)
        self.cmb_run_mode.setToolTip("独立进程可在“桌面桥启动管理”中设置退出行为；管理器线程随管理器进程退出。")
        self.cmb_run_mode.currentIndexChanged.connect(self._run_mode_changed)
        controls.addWidget(self.cmb_run_mode)
        self.btn_start = QtWidgets.QPushButton("启动桥")
        self.btn_start.clicked.connect(lambda: self._start_operation("start"))
        controls.addWidget(self.btn_start)
        self.btn_stop = QtWidgets.QPushButton("请求停止")
        self.btn_stop.clicked.connect(self._request_stop)
        controls.addWidget(self.btn_stop)
        controls.addStretch()
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

        bridges = QtWidgets.QWidget()
        bridges_layout = QtWidgets.QVBoxLayout(bridges)
        self.bridge_inventory_label = QtWidgets.QLabel("正在读取后台桥名录…")
        self.bridge_inventory_label.setWordWrap(True)
        self.bridge_inventory_label.setStyleSheet("color: #93c5fd; padding: 6px;")
        bridges_layout.addWidget(self.bridge_inventory_label)
        self.bridge_inventory_table = QtWidgets.QTableWidget(0, 5)
        self.bridge_inventory_table.setHorizontalHeaderLabels(["状态", "桥标识", "当前用途", "后台对话", "最近心跳"])
        self.bridge_inventory_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bridge_inventory_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.bridge_inventory_table.setWordWrap(False)
        self.bridge_inventory_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.bridge_inventory_table.verticalHeader().setVisible(False)
        self.bridge_inventory_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        bridges_layout.addWidget(self.bridge_inventory_table, 1)
        self.tabs.addTab(bridges, "后台桥名录")

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
        self.cmb_run_mode.blockSignals(True)
        mode_index = self.cmb_run_mode.findData(self.controller.run_mode())
        self.cmb_run_mode.setCurrentIndex(max(0, mode_index))
        current_mode = "管理器线程" if task.get("mode") == "thread" else "独立进程"
        self.cmb_run_mode.setToolTip(
            f"运行方式在下次启动桥时生效；当前：{current_mode}。" if running else
            "运行方式在下次启动桥时生效；管理器线程随管理器退出。"
        )
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
            f"{task_state} · 方式 {'独立进程' if task.get('mode') == 'process' else '管理器线程'} · "
            f"最近更新 {task.get('last_run') or '暂无时间'} · 状态 {task.get('last_result', '状态未知')}"
        )
        self.info["backend"].setText(config.get("backend") or "未配置")
        node_id = str(config.get("node_id") or agent.get("node_id") or "")
        self.info["node"].setText(_short_bridge_id(node_id) if node_id else "—")
        self.info["node"].setToolTip(node_id)
        workspace_id = str(config.get("workspace_id") or agent.get("workspace_id") or "")
        self.info["workspace"].setText(_short_bridge_id(workspace_id) if workspace_id else "—")
        self.info["workspace"].setToolTip(workspace_id)
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
        self._render_backend_inventory(snapshot.get("backend_targets") or {}, config)
        self._render_tokens(snapshot.get("tokens"))
        task_status = agent.get("status", "") if running else "stopped"
        self._render_tasks(snapshot.get("history") or [], detail, task_status)
        self.log_status_label.setText(snapshot.get("log_status") or "最新状态：暂无状态记录")
        logs = snapshot.get("logs") or "尚无桥接日志"
        if self.log_view.toPlainText() != logs:
            self.log_view.setPlainText(logs)

    def _open_startup_management(self):
        opener = getattr(self.parent(), "open_bridge_startup_manager", None)
        if callable(opener):
            opener()

    def _render_backend_inventory(self, inventory: dict, local_config: dict):
        table = self.bridge_inventory_table
        targets = inventory.get("targets") or []
        if not inventory.get("ok"):
            table.setRowCount(0)
            self.bridge_inventory_label.setText(inventory.get("message") or "后台桥名录暂不可用。")
            return
        local_node = str(local_config.get("node_id") or "")
        local_workspace = str(local_config.get("workspace_id") or "")
        chat = inventory.get("chat_target") or {}
        provider = str(chat.get("provider") or "")
        chat_node = str(chat.get("node_id") or "") if provider in ("codex_desktop", "antigravity_desktop") else ""
        chat_workspace = str(chat.get("workspace_id") or "")
        default_node = str(inventory.get("default_node_id") or "")
        strategy = inventory.get("strategy_target") or {}
        strategy_node = str(strategy.get("node_id") or "")
        strategy_workspace = str(strategy.get("workspace_id") or "")
        local_found = False
        if provider in ("codex_desktop", "antigravity_desktop") and chat_node:
            engine = "Antigravity" if provider == "antigravity_desktop" else "Codex"
            chat_label = engine + " · " + _short_bridge_id(chat_node) + " / " + _short_bridge_id(chat_workspace)
        elif provider == "hermes":
            chat_label = "Hermes"
        else:
            chat_label = "未设置" if provider in ("", "unknown") else "读取失败"
        for target in targets:
            if target["node_id"] == chat_node and target["workspace_id"] == chat_workspace:
                chat_label = _bridge_target_name(target.get("label", ""), chat_node, target.get("provider", "")) + " · " + _short_bridge_id(chat_node) + " / " + _short_bridge_id(chat_workspace)
                break
        table.setRowCount(len(targets))
        for row, target in enumerate(targets):
            node = target["node_id"]
            workspace = target["workspace_id"]
            is_local = node == local_node and workspace == local_workspace
            is_chat = node == chat_node and workspace == chat_workspace and bool(chat_node)
            is_default = node == default_node and bool(default_node)
            is_strategy = node == strategy_node and workspace == strategy_workspace and bool(strategy_node)
            local_found = local_found or is_local
            online = bool(target.get("online"))
            desktop_status = str(target.get("desktop_status") or "")
            if online:
                state = "在线 · " + ({"analyzing": "处理中", "ready": "空闲"}.get(desktop_status, _status_label(desktop_status)))
            elif desktop_status == "status_unavailable":
                state = "状态不可读"
            elif target.get("heartbeat"):
                state = "心跳过期"
            else:
                state = "已登记 · 无心跳"
            name = _bridge_target_name(target.get("label", ""), node, target.get("provider", ""))
            identity = _short_bridge_id(node) + " / " + _short_bridge_id(workspace)
            roles = []
            if is_local:
                roles.append("本机")
            if is_chat:
                roles.append("Web 对话")
            if is_strategy:
                roles.append("策略研究")
            if is_default:
                roles.append("默认联动")
            details = "节点 ID：%s\n工作区 ID：%s\n状态：%s\n最近心跳：%s" % (
                node, workspace, desktop_status or "未上报", target.get("heartbeat") or "无",
            )
            heartbeat = _format_bridge_heartbeat(target.get("heartbeat")) if target.get("heartbeat") else (
                "不可读" if desktop_status == "status_unavailable" else "无记录"
            )
            if target.get("chat_jobs_status") == "status_unavailable":
                chat_jobs = "读取失败"
            else:
                chat_jobs = "运行 %s · 排队 %s" % (target.get("chat_running", "0"), target.get("chat_queued", "0"))
            values = (state, name + " · " + identity, " / ".join(roles) or "—", chat_jobs, heartbeat)
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setToolTip(details)
                if is_local:
                    item.setBackground(QtGui.QBrush(QtGui.QColor("#243b55")))
                table.setItem(row, column, item)
        local_label = _short_bridge_id(local_node) + " / " + _short_bridge_id(local_workspace)
        default_label = _short_bridge_id(default_node) if default_node else "未设置"
        strategy_label = _short_bridge_id(strategy_node) + " / " + _short_bridge_id(strategy_workspace) if strategy_node else "未设置"
        self.bridge_inventory_label.setText(
            "后台登记 %d 个桥 · 本机：%s%s · Web 对话：%s · 策略研究：%s · 默认联动节点：%s。"
            "Web 对话与策略研究可按同一节点 / 工作区标识选择。" %
            (len(targets), local_label, "" if local_found else "（本机未登记）", chat_label, strategy_label, default_label)
        )
    def _render_tokens(self, tokens: dict | None):
        if not tokens or not tokens.get("available"):
            self.token_label.setText("未找到本机 Codex 会话用量记录。")
            return
        self.token_label.setText(token_usage_text(tokens))

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

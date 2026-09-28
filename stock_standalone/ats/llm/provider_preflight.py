# -*- coding: utf-8 -*-
"""Read-only readiness checks for IPO LLM providers and their R9 gates."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Mapping
from urllib.parse import urlsplit

from ats.llm.cli_paths import resolve_cli_path


_DISTRIBUTIONS = ("google-antigravity", "litert-lm")
_LOCAL_AUTHORIZATION_KEYS = {
    "stage0_accepted", "provider_accepted", "process_tree_isolation_accepted",
    "acceptance_id",
}
_REMOTE_AUTHORIZATION_KEYS = _LOCAL_AUTHORIZATION_KEYS | {
    "tool_access_isolation_accepted", "remote_egress_isolation_accepted",
}


def _check(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail[:240]}


def _distribution_status(distribution: str) -> str:
    try:
        return "已安装 " + metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "未安装"
    except Exception:
        return "无法确认"


def _is_loopback_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


def _runtime_authorization_ready(
    authorization: Any, approval_id: Any = None, *, remote_required: bool = False,
) -> bool:
    if not isinstance(authorization, Mapping):
        return False
    accepted_keys = set(authorization)
    if remote_required:
        if accepted_keys != _REMOTE_AUTHORIZATION_KEYS:
            return False
        required_flags = _REMOTE_AUTHORIZATION_KEYS - {"acceptance_id"}
    else:
        if frozenset(accepted_keys) not in {
            frozenset(_LOCAL_AUTHORIZATION_KEYS), frozenset(_REMOTE_AUTHORIZATION_KEYS),
        }:
            return False
        required_flags = _LOCAL_AUTHORIZATION_KEYS - {"acceptance_id"}
    return bool(
        all(authorization.get(key) is True for key in required_flags)
        and isinstance(authorization.get("acceptance_id"), str)
        and authorization.get("acceptance_id", "").strip()
        and (approval_id is None or authorization.get("acceptance_id") == approval_id)
    )


def _cli_available(value: Any, name: str) -> bool:
    return bool(resolve_cli_path(value, name))


def inspect_provider_preflight(
    config_path: Path, authorization: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return bounded, non-secret provider diagnostics without enabling runtime."""
    checks: List[Dict[str, str]] = []
    result: Dict[str, Any] = {
        "backend": "未配置",
        "mode": "未知",
        "locality": "未确认",
        "state": "未就绪",
        "execution_allowed": False,
        "checks": checks,
    }
    if not config_path.is_file():
        checks.append(_check("LLM 配置", "未就绪", "缺少 config/llm_config.yaml"))
        checks.append(_check("执行器", "阻断", "spawn Worker、LiteRT 桥接代码与控制线程已具备；运行验收和进程树隔离未通过，旁路保持关闭"))
        return result

    try:
        import yaml
        if config_path.stat().st_size > 128 * 1024:
            raise ValueError("配置文件超过 128 KiB")
        with config_path.open("r", encoding="utf-8") as stream:
            document = yaml.safe_load(stream)
    except ImportError:
        checks.append(_check("LLM 配置", "未就绪", "缺少 PyYAML，无法安全解析"))
        checks.append(_check("执行器", "阻断", "spawn Worker、LiteRT 桥接代码与控制线程已具备；运行验收和进程树隔离未通过，旁路保持关闭"))
        return result
    except (OSError, UnicodeError, ValueError):
        checks.append(_check("LLM 配置", "无效", "配置文件不可读或格式无效"))
        checks.append(_check("执行器", "阻断", "spawn Worker、LiteRT 桥接代码与控制线程已具备；运行验收和进程树隔离未通过，旁路保持关闭"))
        return result
    except Exception:
        checks.append(_check("LLM 配置", "无效", "配置解析失败"))
        checks.append(_check("执行器", "阻断", "spawn Worker、LiteRT 桥接代码与控制线程已具备；运行验收和进程树隔离未通过，旁路保持关闭"))
        return result

    if not isinstance(document, Mapping):
        checks.append(_check("LLM 配置", "无效", "根节点必须为映射"))
        checks.append(_check("执行器", "阻断", "spawn Worker 与控制线程代码已具备；Provider 桥接和进程树隔离未验收，旁路保持关闭"))
        return result
    settings = document.get("llm_settings")
    backends = document.get("backends")
    if not isinstance(settings, Mapping) or not isinstance(backends, Mapping):
        checks.append(_check("LLM 配置", "无效", "缺少 llm_settings 或 backends"))
        checks.append(_check("执行器", "阻断", "spawn Worker 与控制线程代码已具备；Provider 桥接和进程树隔离未验收，旁路保持关闭"))
        return result

    backend_name = settings.get("active_backend")
    backend_name = backend_name if isinstance(backend_name, str) else ""
    backend = backends.get(backend_name)
    if not isinstance(backend, Mapping):
        result["backend"] = backend_name[:80] or "未配置"
        checks.append(_check("LLM 配置", "无效", "Provider 未配置或名称不受支持"))
        checks.append(_check("执行器", "阻断", "未知 Provider 必须失败关闭；禁止自动回退"))
        return result

    result["backend"] = backend_name[:80]
    checks.append(_check("LLM 配置", "有效", "配置可解析；本检查不读取或展示密钥"))
    timeout = settings.get("request_timeout_seconds")
    active_name = settings.get("active_backend")
    fallback_name = settings.get("fallback_backend")
    dual_remote_route = (
        active_name in ("antigravity_cli", "codex_cli")
        and fallback_name in ("antigravity_cli", "codex_cli")
        and fallback_name != active_name
    )
    timeout_ok = (
        isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
        and (timeout == 30.0 or (timeout == 60.0 and dual_remote_route))
    )
    checks.append(_check(
        "Worker 硬截止", "通过" if timeout_ok else "阻断",
        "单 Provider 30 秒；显式双 Provider 回退可用 60 秒" if timeout_ok else "必须显式配置单 Provider 30 秒，或双 Provider 回退 60 秒",
    ))
    if timeout_ok:
        result["request_timeout_seconds"] = float(timeout)

    allow_remote = settings.get("allow_remote") is True
    approval = settings.get("remote_egress")
    approval = approval if isinstance(approval, Mapping) else {}
    approved = bool(
        isinstance(approval.get("approval_id"), str) and approval.get("approval_id", "").strip()
        and isinstance(approval.get("destination"), str) and approval.get("destination", "").strip()
        and isinstance(approval.get("policy_version"), str) and approval.get("policy_version", "").strip()
        and isinstance(approval.get("field_allowlist_by_agent"), Mapping)
        and approval.get("field_allowlist_by_agent")
        and all(
            isinstance(agent, str) and agent.strip()
            and isinstance(fields, list) and fields
            and all(isinstance(field, str) and field.strip() for field in fields)
            for agent, fields in approval.get("field_allowlist_by_agent", {}).items()
        )
    )

    if backend_name == "antigravity_sdk":
        mode = backend.get("execution_mode")
        result["mode"] = str(mode or "未配置")[:80]
        result["locality"] = "本机 LiteRT 候选" if mode == "local_litert" else "未确认/不符合支持模式"
        checks.append(_check(
            "执行模式", "通过" if mode == "local_litert" else "阻断",
            "local_litert" if mode == "local_litert" else "必须显式设置 local_litert；不接受隐式/远端回退",
        ))
        remote_closed = (
            settings.get("allow_remote") is False
            and settings.get("fallback_backend") in (None, "")
        )
        checks.append(_check(
            "远端回退", "通过" if remote_closed else "阻断",
            "本机模式已关闭远端 Provider 与回退链" if remote_closed
            else "本机候选禁止开启远端 Provider 或回退链",
        ))
        for distribution in _DISTRIBUTIONS:
            status = _distribution_status(distribution)
            checks.append(_check(
                "依赖 " + distribution,
                "通过" if status.startswith("已安装 ") else "未就绪",
                status,
            ))
        model_path = backend.get("model_path")
        path_ok = False
        if isinstance(model_path, str) and model_path.strip():
            try:
                candidate = Path(model_path)
                path_ok = candidate.is_absolute() and candidate.suffix.lower() == ".litertlm" and candidate.is_file()
            except (OSError, ValueError):
                path_ok = False
        checks.append(_check(
            "模型文件", "通过" if path_ok else "未就绪",
            "绝对 .litertlm 文件存在" if path_ok else "要求绝对路径且文件存在；不显示路径、不扫描模型内容",
        ))
        model_id = backend.get("model_id")
        model_id_ok = isinstance(model_id, str) and bool(model_id.strip())
        checks.append(_check("模型 ID", "通过" if model_id_ok else "未就绪", "已配置" if model_id_ok else "缺少已验收模型 ID"))
        model_hash = backend.get("model_sha256")
        model_hash_configured = (
            isinstance(model_hash, str) and len(model_hash) == 64
            and all(character in "0123456789abcdefABCDEF" for character in model_hash)
        )
        checks.append(_check(
            "受控模型 SHA-256", "已配置" if model_hash_configured else "未就绪",
            "摘要格式有效；Worker 启动时仍须对模型文件实算比对"
            if model_hash_configured else "缺少 config/llm_config.yaml 中的 model_sha256",
        ))
        checks.append(_check(
            "模型文件哈希", "待验收",
            "UI 轮询不读取完整模型；Worker 启动时才实算并与受控 SHA-256 比对",
        ))
        checks.append(_check("Windows/设备验收", "待验收", "尚无 SDK、LiteRT、设备/GPU 与 Windows 兼容证据"))
        checks.append(_check("原生结构化输出", "待验收", "尚无所选模型的 response_schema / structured_output 验收证据"))
    elif backend_name in {"codex_cli", "antigravity_cli"}:
        result["mode"] = str(backend.get("execution_mode") or "remote_api")[:80]
        result["locality"] = "远端处理边界"
        if allow_remote and approved:
            checks.append(_check("远端审批", "通过", "审批 ID、固定目标与逐 Agent 字段 allowlist 已配置"))
        else:
            checks.append(_check("远端审批", "阻断", "默认禁用；必须显式授权、固定目标并配置逐 Agent 字段 allowlist"))
        enabled = backend.get("enabled") is True
        checks.append(_check(
            "Provider 开关", "通过" if enabled else "阻断",
            "配置显式启用" if enabled else "配置保持关闭",
        ))
        cli_setting = backend.get("cli_path" if backend_name == "antigravity_cli" else "bin_path")
        cli_name = "agy" if backend_name == "antigravity_cli" else "codex"
        cli_ok = _cli_available(cli_setting, cli_name)
        checks.append(_check(
            "agy CLI" if backend_name == "antigravity_cli" else "Codex CLI",
            "通过" if cli_ok else "未就绪",
            "可解析到 CLI 文件" if cli_ok else "找不到配置的 CLI 可执行文件",
        ))
        model_id = backend.get("model_id")
        model_ok = isinstance(model_id, str) and bool(model_id.strip()) and len(model_id) <= 160
        checks.append(_check("固定模型 ID", "通过" if model_ok else "未就绪", "已配置" if model_ok else "需固定模型 ID，避免模型漂移"))
        scratch = backend.get("scratch_cwd")
        scratch_path = Path(scratch).expanduser() if isinstance(scratch, str) and scratch.strip() else None
        if scratch_path is not None and not scratch_path.is_absolute():
            scratch_path = config_path.parent.parent / scratch_path
        scratch_ok = scratch_path is not None and scratch_path.is_dir()
        checks.append(_check(
            "隔离工作目录", "通过" if scratch_ok else "未就绪",
            "专用 scratch_cwd 已存在" if scratch_ok else "需配置并创建专用 scratch_cwd",
        ))
        checks.append(_check(
            "进程树隔离", "通过" if isinstance(authorization, Mapping) and authorization.get("process_tree_isolation_accepted") is True else "待验收",
            "已记录进程树隔离验收" if isinstance(authorization, Mapping) and authorization.get("process_tree_isolation_accepted") is True else "需 Windows Job Object/子进程回收验收",
        ))
        checks.append(_check(
            "工具/MCP 隔离", "通过" if isinstance(authorization, Mapping) and authorization.get("tool_access_isolation_accepted") is True else "待验收",
            "已记录工具与 MCP 隔离验收" if isinstance(authorization, Mapping) and authorization.get("tool_access_isolation_accepted") is True else "CLI 可能继承工具或 MCP；需验收工具面隔离",
        ))
        checks.append(_check(
            "远端网络出口", "通过" if isinstance(authorization, Mapping) and authorization.get("remote_egress_isolation_accepted") is True else "待验收",
            "已记录出口限制验收" if isinstance(authorization, Mapping) and authorization.get("remote_egress_isolation_accepted") is True else "固定 destination 是审计声明；仍需 OS/网络层出口限制",
        ))
        accepted = _runtime_authorization_ready(
            authorization, approval.get("approval_id"), remote_required=True
        )
        provider_accepted = (
            isinstance(authorization, Mapping)
            and authorization.get("provider_accepted") is True
        )
        checks.append(_check(
            "运行授权", "通过" if accepted else "阻断",
            "Stage 0、Provider、进程树、工具与远端出口验收齐全" if accepted else "缺少完整且非默认的运行授权记录",
        ))
        try:
            from ats.llm.remote_sanitizer import validate_remote_policy
            validate_remote_policy(approval)
            sanitizer_available = True
        except Exception:
            sanitizer_available = False
        checks.append(_check(
            "远端字段策略", "通过" if sanitizer_available else "阻断",
            "逐 Agent 字段 allowlist 已完整校验并在 Worker 内投影"
            if sanitizer_available else "目标、字段路径或 allowlist 无效",
        ))
        checks.append(_check(
            "CLI 输出契约", "通过" if provider_accepted else "待验收",
            "需有 JSON Schema 输出、退出码与超时映射的 Provider 实机验收记录"
            if not provider_accepted else "Provider 协议验收已记录",
        ))
        checks.append(_check(
            "远端 Provider 调用入口", "通过",
            "AGY/Codex 适配器接入隔离 Worker；是否执行仍由上列授权与 Fail-Closed 门禁控制",
        ))
        fallback_name = settings.get("fallback_backend")
        if fallback_name not in (None, ""):
            fallback = backends.get(fallback_name) if isinstance(fallback_name, str) else None
            fallback_valid_name = (
                isinstance(fallback_name, str)
                and fallback_name in {"antigravity_cli", "codex_cli"}
                and fallback_name != backend_name
            )
            fallback_enabled = isinstance(fallback, Mapping) and fallback.get("enabled") is True
            fallback_model = (
                isinstance(fallback, Mapping)
                and isinstance(fallback.get("model_id"), str)
                and bool(fallback.get("model_id", "").strip())
                and len(fallback.get("model_id", "")) <= 160
            )
            fallback_cli_setting = (
                fallback.get("cli_path" if fallback_name == "antigravity_cli" else "bin_path")
                if isinstance(fallback, Mapping) and fallback_name in {"antigravity_cli", "codex_cli"}
                else None
            )
            fallback_cli_ok = fallback_valid_name and _cli_available(
                fallback_cli_setting,
                "agy" if fallback_name == "antigravity_cli" else "codex",
            )
            fallback_scratch = fallback.get("scratch_cwd") if isinstance(fallback, Mapping) else None
            fallback_scratch_path = (
                Path(fallback_scratch).expanduser()
                if isinstance(fallback_scratch, str) and fallback_scratch.strip() else None
            )
            if fallback_scratch_path is not None and not fallback_scratch_path.is_absolute():
                fallback_scratch_path = config_path.parent.parent / fallback_scratch_path
            fallback_scratch_ok = fallback_scratch_path is not None and fallback_scratch_path.is_dir()
            fallback_ready = bool(
                fallback_valid_name and fallback_enabled and fallback_model
                and fallback_cli_ok and fallback_scratch_ok and allow_remote and approved
                and _runtime_authorization_ready(
                    authorization, approval.get("approval_id"), remote_required=True,
                )
            )
            checks.append(_check(
                "故障转移 Provider", "通过" if fallback_ready else "阻断",
                f"{fallback_name} 已启用并共享当前远端字段策略"
                if fallback_ready else "备选 Provider、模型、CLI、scratch 或远端授权未完整就绪",
            ))
        elif "fallback_backend" in settings and settings.get("fallback_backend") is not None:
            checks.append(_check("故障转移 Provider", "阻断", "fallback_backend 必须是受支持的 CLI 名称或空值"))
    elif backend_name == "ollama_http":
        result["mode"] = "loopback HTTP"
        result["locality"] = "本机候选（未探测服务）"
        remote_closed = settings.get("allow_remote") is False
        checks.append(_check(
            "远端回退", "通过" if remote_closed else "阻断",
            "显式关闭" if remote_closed else "本机候选必须显式关闭远端回退",
        ))
        url_ok = _is_loopback_url(backend.get("base_url"))
        model_ok = isinstance(backend.get("model"), str) and bool(backend.get("model", "").strip())
        checks.append(_check("服务地址", "通过" if url_ok else "阻断", "HTTP loopback" if url_ok else "仅允许明确的 loopback HTTP 地址"))
        checks.append(_check("模型标识", "通过" if model_ok else "未就绪", "已配置" if model_ok else "缺少模型标识"))
        checks.append(_check("服务探活", "未探测", "不会在 UI 轮询中发起网络请求"))
        checks.append(_check("服务资源/结构化输出", "待验收", "缺少运行位置、取消/关闭与原生 Schema 验收证据"))
    else:
        checks.append(_check("Provider", "阻断", "未知 Provider 必须失败关闭；禁止自动回退"))

    isolation_ready = _runtime_authorization_ready(
        authorization,
        approval.get("approval_id") if backend_name in {"antigravity_cli", "codex_cli"} else None,
        remote_required=backend_name in {"antigravity_cli", "codex_cli"},
    )
    checks.append(_check(
        "Worker/隔离执行器", "通过" if isolation_ready else "待验收",
        "Worker、心跳、硬截止与隔离验收记录齐全" if isolation_ready else "Worker 已接入；Provider 仍须等待独立验收与授权",
    ))
    statuses = {check["status"] for check in checks}
    if "阻断" in statuses or "无效" in statuses:
        result["state"] = "阻断"
    elif statuses.intersection({"未就绪", "待验收", "未探测"}):
        result["state"] = "未就绪"
    else:
        result["state"] = "READY"
    result["execution_allowed"] = (
        result["state"] == "READY" and backend_name in {"antigravity_cli", "codex_cli"}
        and _runtime_authorization_ready(
            authorization, approval.get("approval_id"), remote_required=True
        )
    )
    return result

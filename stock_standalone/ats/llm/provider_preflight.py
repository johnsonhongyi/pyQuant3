# -*- coding: utf-8 -*-
"""Read-only readiness checks for IPO LLM providers.

This module deliberately never constructs or starts a provider. Passing these
checks is diagnostic evidence only; execution remains disabled until the full
R9 Worker, schema, isolation, and acceptance gates are implemented.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Mapping
from urllib.parse import urlsplit


_DISTRIBUTIONS = ("google-antigravity", "litert-lm")


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


def inspect_provider_preflight(config_path: Path) -> Dict[str, Any]:
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
    timeout_ok = (
        isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
        and timeout == 30.0
    )
    checks.append(_check(
        "Worker 硬截止", "通过" if timeout_ok else "阻断",
        "统一配置为 30 秒" if timeout_ok else "必须显式配置为方案约定的 30 秒；不使用代码默认值",
    ))

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
        checks.append(_check(
            "远端回退", "阻断" if allow_remote or settings.get("allow_remote") is not False else "通过",
            "本机候选必须显式关闭远端" if allow_remote or settings.get("allow_remote") is not False else "显式关闭",
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
            checks.append(_check("远端审批", "具备配置", "审批 ID、固定目标与逐 Agent 字段 allowlist 均已填写；仍需验证 sanitizer"))
        else:
            checks.append(_check("远端审批", "阻断", "默认禁用；必须显式授权、固定目标并配置逐 Agent 字段 allowlist"))
        if backend_name == "antigravity_cli" and backend.get("enabled") is not True:
            checks.append(_check("agy CLI", "阻断", "默认禁用；须先通过 OS 强制工具隔离验收"))
        checks.append(_check("OS 强制沙箱", "待验收", "尚无启动前生效的无工具/无 MCP/受限工作区策略证据"))
        if backend_name == "codex_cli":
            checks.append(_check("Codex CLI", "待验收", "本机 CLI 不代表本机推理；远端调用入口尚未接入"))
        try:
            from ats.llm.remote_sanitizer import build_remote_safe_request
            sanitizer_available = callable(build_remote_safe_request)
        except Exception:
            sanitizer_available = False
        checks.append(_check(
            "字段 sanitizer", "已实现" if sanitizer_available else "阻断",
            "逐 Agent allowlist 投影已具备；尚未接入 Provider 请求路径，当前不允许远端调用"
            if sanitizer_available else "逐 Agent allowlist sanitizer 不可用",
        ))
        checks.append(_check(
            "远端 Provider 调用入口", "阻断",
            "当前后端工厂只支持本机 LiteRT；远端后端和 Worker 调用路径尚未实现",
        ))
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

    checks.append(_check(
        "Worker/隔离执行器", "阻断",
        "spawn Worker、LiteRT 桥接、专用控制线程、合并队列、心跳、30 秒熔断和状态发布已有代码；SDK/模型运行、进程树回收和部署验收仍未通过",
    ))
    statuses = {check["status"] for check in checks}
    if "阻断" in statuses or "无效" in statuses:
        result["state"] = "阻断"
    elif "未就绪" in statuses:
        result["state"] = "未就绪"
    else:
        result["state"] = "候选待验收"
    result["execution_allowed"] = False
    return result

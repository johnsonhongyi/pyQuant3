"""Run the persisted shadow evaluation or an explicit synthetic local interface probe."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Source bootstrap is only for imports; persistent data uses the system root.
if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

from sys_utils import get_app_root, safe_resolve_path

APP_ROOT = safe_resolve_path(get_app_root())

from ats.llm.agent_contracts import build_agent_envelope, payload_schema, payload_schema_hash
from ats.llm.ollama_backend import OllamaHTTPBackend, ollama_binding_hash
from ats.llm.shadow_evaluation import collect_shadow_evaluation, save_shadow_evaluation, _report_hash
from ats.llm.worker_protocol import encode_worker_response


def probe_ollama(root: Path, *, start_local_service: bool = False, warm_up: bool = False) -> dict:
    """Only synthetic input; does not issue or persist runtime/Stage authorization."""
    result = {"state": "PROBE_FAILED", "operating_mode": "INTERFACE_PROBE",
              "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "real_data_used": False, "order_submitted": False,
              "entry_authorized": False, "model_promoted": False,
              "runtime_authorized": False, "training_performed": False}
    backend = None
    try:
        import yaml
        path = root / "config/llm_config.yaml"
        if path.stat().st_size > 128 * 1024:
            raise ValueError("LLM_CONFIG_TOO_LARGE")
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        local = config["backends"]["ollama_http"]
        backend = OllamaHTTPBackend(local["base_url"], local["model"])
        result.update(provider_id=backend.provider_id, model_id=backend.model_id)
        result["binding_hash"] = ollama_binding_hash(backend.base_url, backend.model_id)
        if start_local_service:
            if backend.base_url != "http://127.0.0.1:11434":
                raise ValueError("AUTO_START_ONLY_DEFAULT_LOOPBACK_SERVICE")
            from ats.llm.ipo_local_observer import _ensure_local_model
            if not _ensure_local_model(backend.model_id):
                raise ValueError("LOCAL_SERVICE_OR_INSTALLED_MODEL_UNAVAILABLE")
        if warm_up:
            started = time.monotonic()
            warm_request = urllib.request.Request(
                backend.base_url + "/api/generate",
                data=json.dumps({"model": backend.model_id, "stream": False, "keep_alive": "5m",
                                 "options": {"num_ctx": 16384}}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with backend._opener.open(warm_request, timeout=60) as response:
                loaded = json.loads(response.read(64 * 1024))
            if loaded.get("done") is not True or loaded.get("model") != backend.model_id:
                raise ValueError("LOCAL_MODEL_WARMUP_FAILED")
            result["warmup_elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        request = {"request_id": "shadow-probe-" + uuid4().hex, "agent_type": "MARKET_REGIME",
                   "scope_id": "MARKET", "ticker": "", "as_of_time": now,
                   "prompt": "这是合成接口验收，没有真实行情。只输出JSON：情绪50、NEUTRAL、催化和风险列表为空。不得给出交易指令。",
                   "context": {"simulation_only": True, "real_data_used": False},
                   "model_id": backend.model_id, "prompt_version": "ipo.shadow-interface-probe.v1",
                   "evidence_ids": [], "schema_hash": payload_schema_hash("MARKET_REGIME")}
        started = time.monotonic()
        response = backend.generate_request(request, payload_schema("MARKET_REGIME", evidence_ids=[]),
                                            timeout_seconds=30.0)
        result["probe_elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        if response["status"] != "OK":
            result["reason"] = response.get("error_code")
            return result
        envelope = build_agent_envelope(
            "MARKET_REGIME", response["proposal"], request_id=request["request_id"],
            scope_id="MARKET", ticker="", as_of_time=now,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            model_id=backend.model_id, prompt_version=request["prompt_version"], evidence_ids=[])
        encode_worker_response({"request_id": request["request_id"], "status": "OK", "envelope": envelope,
                                "error_code": "", "provider_id": backend.provider_id,
                                "model_id": backend.model_id, "fallback_error_code": ""}, request)
        result.update(state="PROBE_PASSED", provider_id=backend.provider_id, model_id=backend.model_id,
                      native_schema_validated=True, worker_protocol_validated=True, envelope=envelope)
    except Exception as exc:
        message = str(exc)
        result["error_type"] = type(exc).__name__
        result["reason"] = message if re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", message) else type(exc).__name__
    finally:
        result["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        if backend is not None:
            backend.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="IPO 影子评估闭环（不训练、不晋级、不下单）")
    parser.add_argument("--root", type=Path, default=APP_ROOT)
    parser.add_argument("--read-only", action="store_true", help="仅输出已有真实结果评价，不写报告")
    parser.add_argument("--probe-ollama", action="store_true", help="用合成输入验证已配置本机结构化接口")
    parser.add_argument("--start-local-service", action="store_true", help="探针前启动现有 Ollama，不下载模型")
    parser.add_argument("--warm-up", action="store_true", help="探针前独立预载本机模型，最长60秒；不延长Worker 30秒截止")
    parser.add_argument("--json-out", type=Path, help="显式额外保存报告")
    args = parser.parse_args()
    if (args.start_local_service or args.warm_up) and not args.probe_ollama:
        parser.error("--start-local-service / --warm-up 必须与 --probe-ollama 一起使用")
    if args.read_only and args.probe_ollama:
        parser.error("--read-only 不调用模型")
    report = (probe_ollama(args.root, start_local_service=args.start_local_service, warm_up=args.warm_up) if args.probe_ollama
              else collect_shadow_evaluation(args.root) if args.read_only else save_shadow_evaluation(args.root))
    if args.json_out:
        from tools.run_ipo_offline_learning import write_report
        try:
            write_report(args.json_out, report)
        except OSError as exc:
            report.update(state="PERSISTENCE_FAILED", reason=type(exc).__name__)
            if "report_hash" in report:
                report["report_hash"] = _report_hash(report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["state"] in {"SHADOW_EVALUATED", "PROBE_PASSED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

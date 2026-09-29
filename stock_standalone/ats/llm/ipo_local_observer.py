"""Local Ollama commentary on persisted IPO observations; never makes trade decisions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STATUS = Path("data/ipo_learning/local_llm_observation.latest.json")
_DB = Path("data/ipo_learning/shadow_observations.sqlite")
_URL = "http://127.0.0.1:11434/api/generate"


def _ensure_local_model(model: str) -> bool:
    tags_url = "http://127.0.0.1:11434/api/tags"
    for attempt in range(7):
        try:
            with urllib.request.urlopen(tags_url, timeout=1) as response:
                models = json.loads(response.read(64 * 1024)).get("models", [])
            return any(item.get("name") == model for item in models if isinstance(item, dict))
        except (OSError, ValueError, TypeError):
            if attempt == 0:
                executable = shutil.which("ollama")
                if not executable:
                    return False
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                try:
                    subprocess.Popen(
                        [executable, "serve"], creationflags=flags,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except OSError:
                    return False
            time.sleep(0.5)
    return False


def _save(root: Path, status: dict[str, Any]) -> dict[str, Any]:
    path = root / _STATUS
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(status, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return status


def analyze_latest_observation(
    root: str | Path, *, model: str = "qwen3.5:4b",
    observation_hash: str | None = None,
) -> dict[str, Any]:
    """Generate a bounded local explanation from a verified, immutable observation."""
    base = Path(root).resolve()
    status: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": "UNREADY", "model": model, "order_submitted": False,
        "model_promoted": False,
    }
    if model != "qwen3.5:4b":
        status["reason"] = "MODEL_NOT_ALLOWED"
        return _save(base, status)
    if not _ensure_local_model(model):
        status["reason"] = "OLLAMA_OR_MODEL_UNAVAILABLE"
        return _save(base, status)
    database = base / _DB
    if not database.is_file():
        status["reason"] = "NO_OBSERVATION"
        return _save(base, status)
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5) as connection:
            if observation_hash:
                row = connection.execute(
                    "SELECT observation_hash, payload_json FROM shadow_observations "
                    "WHERE observation_hash=?", (observation_hash,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT observation_hash, payload_json FROM shadow_observations "
                    "ORDER BY cutoff DESC LIMIT 1"
                ).fetchone()
        if row is None:
            status["reason"] = "NO_OBSERVATION"
            return _save(base, status)
        digest, payload_json = row
        if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != digest:
            status["reason"] = "OBSERVATION_HASH_MISMATCH"
            return _save(base, status)
        observation = json.loads(payload_json)
        fields = observation.get("fields", {})
        if not isinstance(fields, dict) or not fields:
            status["reason"] = "NO_VALIDATED_FIELDS"
            return _save(base, status)
        status.update({"ticker": observation["ticker"], "observation_hash": digest,
                       "field_count": len(fields)})
        prior = base / _STATUS
        if prior.is_file():
            saved = json.loads(prior.read_text(encoding="utf-8"))
            if (saved.get("state") == "COMPLETED" and saved.get("observation_hash") == digest
                    and saved.get("model") == model and len(fields) < 41):
                status.update({
                    "state": "INSUFFICIENT_DATA", "model_executed": True,
                    "raw_response_hash": hashlib.sha256(
                        str(saved.get("analysis", "")).encode("utf-8")
                    ).hexdigest(),
                    "analysis": f"本机模型已响应；仅 {len(fields)}/41 个必需字段有效，无法可靠判断 IPO 情绪。",
                })
                return _save(base, status)
            if (saved.get("state") == "COMPLETED" and saved.get("observation_hash") == digest
                    and saved.get("model") == model
                    and str(saved.get("analysis", "")).endswith(("。", "！", "？", ".", "!", "?"))):
                return saved
        status["state"] = "RUNNING"
        _save(base, status)
        input_fields = {
            name: {"value": item.get("value"), "available_at": item.get("available_at")}
            for name, item in sorted(fields.items()) if isinstance(item, dict)
        }
        prompt = (
            "你是只读 IPO 数据观察员。只根据下面已验证的观测字段，简述市场情绪线索、"
            "缺失的关键证据和不确定性。不得编造未提供的事实，不得给出买卖、仓位或价格指令。"
            "若字段不足，明确写出无法判断。用中文，最多 160 字。\n"
            + json.dumps({"ticker": observation["ticker"],
                          "cutoff": observation["cutoff"], "fields": input_fields},
                         ensure_ascii=False, sort_keys=True, allow_nan=False)
        )
        request = urllib.request.Request(
            _URL,
            data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                             "think": False,
                             "options": {"num_ctx": 4096, "num_predict": 256,
                                         "temperature": 0.1}},
                            ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 200:
                raise ValueError("OLLAMA_HTTP_ERROR")
            result = json.loads(response.read(128 * 1024))
        answer = str(result.get("response") or "")
        if "</think>" in answer:
            answer = answer.split("</think>", 1)[1]
        answer = answer.strip()[:2000]
        if (not answer or result.get("done") is not True
                or result.get("done_reason") == "length"
                or "<think>" in answer
                or not answer.endswith(("。", "！", "？", ".", "!", "?"))):
            raise ValueError("EMPTY_OR_INCOMPLETE_RESPONSE")
        status["model_executed"] = True
        status["raw_response_hash"] = hashlib.sha256(answer.encode("utf-8")).hexdigest()
        if len(fields) < 41:
            status.update({
                "state": "INSUFFICIENT_DATA",
                "analysis": f"本机模型已响应；仅 {len(fields)}/41 个必需字段有效，无法可靠判断 IPO 情绪。",
            })
        else:
            status.update({"state": "COMPLETED", "analysis": answer})
    except (OSError, sqlite3.Error, UnicodeError, ValueError, TypeError,
            KeyError, urllib.error.URLError, TimeoutError) as exc:
        status.update({"state": "UNREADY", "reason": type(exc).__name__})
    return _save(base, status)

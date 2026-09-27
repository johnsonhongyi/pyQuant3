# -*- coding: utf-8 -*-
"""Read-only R9 preflight; network acquisition is opt-in and never calls an LLM."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ats.strategy.ipo_source_orchestrator import collect_source_readiness  # noqa: E402


def _json_file(path: Path) -> Dict[str, Any]:
    try:
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _version_probe(command: str, explicit: Optional[str] = None) -> Dict[str, Any]:
    candidate = explicit or shutil.which(command)
    if not candidate or not (Path(candidate).is_file() or shutil.which(candidate)):
        return {"available": False, "version": "未找到"}
    try:
        if str(candidate).lower().endswith(".ps1"):
            argv = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned", "-File", candidate, "--version"]
        else:
            argv = [candidate, "--version"]
        completed = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=4.0,
            shell=False, check=False,
        )
        lines = [line.strip() for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip()]
        return {
            "available": completed.returncode == 0,
            "version": lines[0][:120] if lines else "版本未知",
        }
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "version": "无法启动或探测超时"}


def _config_summary() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ipo_config": {"status": "MISSING"},
        "anchors": {"status": "MISSING"},
        "llm": {"status": "MISSING", "execution_allowed": False},
        "stage_acceptance": {},
    }
    config_path = APP_ROOT / "config" / "ipo_sentiment.yaml"
    config = None
    try:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

        config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        result["ipo_config"] = {
            "status": "VALID" if config.verify_integrity() else "HASH_MISMATCH",
            "version": config.config_version,
            "configuration_hash": config.config_hash,
            "data_contract_hash": config.data_contract.config_hash,
            "required_fields": len(config.data_contract.required_fields),
        }
    except Exception as exc:
        result["ipo_config"] = {"status": "INVALID", "reason": type(exc).__name__}

    anchor_path = APP_ROOT / "config" / "listing_anchors.json"
    try:
        from ats.strategy.listing_anchor_store import ListingAnchorStore

        store = ListingAnchorStore(anchor_path)
        anchors = store._load()
        result["anchors"] = {"status": "VALID", "count": len(anchors)}
    except Exception as exc:
        result["anchors"] = {"status": "INVALID", "reason": type(exc).__name__}

    try:
        from ats.llm.provider_preflight import inspect_provider_preflight

        result["llm"] = inspect_provider_preflight(APP_ROOT / "config" / "llm_config.yaml")
    except Exception as exc:
        result["llm"] = {
            "status": "UNREADY", "execution_allowed": False,
            "reason": f"Provider 预检异常: {type(exc).__name__}",
        }
    result["stage_acceptance"] = _json_file(APP_ROOT / "config" / "ipo_stage_acceptance.json")
    return result


def _database_health() -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    pulse_path = APP_ROOT / "market_pulse.db"
    if pulse_path.is_file():
        try:
            with sqlite3.connect(pulse_path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_sentiment)")}
                count = conn.execute("SELECT COUNT(*) FROM daily_sentiment").fetchone()[0] if columns else 0
                latest = conn.execute("SELECT MAX(date) FROM daily_sentiment").fetchone()[0] if columns else None
            output["market_pulse"] = {
                "status": "READY" if columns else "SCHEMA_MISSING",
                "row_count": int(count or 0), "latest_date": latest or "",
                "has_lrrm_state": "lrrm_state" in columns,
                "has_regime_state": "ipo_regime_state" in columns,
                "raw_contract_fields_present": False,
            }
        except (OSError, sqlite3.Error):
            output["market_pulse"] = {"status": "UNAVAILABLE"}
    else:
        output["market_pulse"] = {"status": "MISSING"}

    snapshot_path = APP_ROOT / "data" / "ipo_learning" / "decision_snapshots.sqlite"
    if snapshot_path.is_file():
        try:
            with sqlite3.connect(snapshot_path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as conn:
                total, waiting, latest = conn.execute(
                    "SELECT COUNT(*), SUM(label_status='WAITING_OUTCOME'), MAX(captured_at) FROM decision_snapshots"
                ).fetchone()
            output["decision_snapshots"] = {
                "status": "READY", "count": int(total or 0),
                "waiting_outcome": int(waiting or 0), "latest": latest or "",
            }
        except (OSError, sqlite3.Error):
            output["decision_snapshots"] = {"status": "UNAVAILABLE"}
    else:
        output["decision_snapshots"] = {"status": "NOT_STARTED", "count": 0}
    return output


def run_preflight(code: str, collect_issue_price: bool = False) -> Dict[str, Any]:
    config_summary = _config_summary()
    config = None
    try:
        from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot

        config = IPODecisionConfigSnapshot.from_yaml(str(APP_ROOT / "config" / "ipo_sentiment.yaml"))
    except Exception:
        pass
    acquisition = None
    if collect_issue_price:
        from ats.strategy.ipo_source_orchestrator import collect_issue_price_from_eastmoney

        acquisition = collect_issue_price_from_eastmoney(APP_ROOT, code)
    sources = collect_source_readiness(APP_ROOT, code, config)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": code,
        "cli": {
            "antigravity": _version_probe("agy", os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.ps1")),
            "codex": _version_probe("codex"),
            "llm_invocation_performed": False,
        },
        "configuration": config_summary,
        "databases": _database_health(),
        "acquisition_attempt": acquisition,
        "source_readiness": sources,
        "runtime_authorization": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="新股情绪/自学习只读准入与数据来源自检")
    parser.add_argument("--code", "-c", default="301689", help="六位股票代码")
    parser.add_argument("--collect-issue-price", action="store_true", help="执行一次 Eastmoney IPO 日历刷新，仅采集发行价")
    parser.add_argument("--json-out", type=Path, help="将完整诊断报告写入 JSON 文件")
    args = parser.parse_args()
    if len(args.code) != 6 or not args.code.isdigit():
        parser.error("--code 必须为六位数字")
    report = run_preflight(args.code, args.collect_issue_price)
    sources = report["source_readiness"]
    print(
        f"新股数据契约：{sources['ready_count']}/{sources['required_count']} READY；"
        f"配置={report['configuration']['ipo_config']['status']}；"
        f"LLM execution_allowed={report['configuration']['llm'].get('execution_allowed', False)}"
    )
    if report.get("acquisition_attempt"):
        print(f"发行价采集：{report['acquisition_attempt']['status']} - {report['acquisition_attempt']['reason']}")
    print("\n字段 | 状态/原因 | 来源与计算路线 | 下一步")
    for row in sources["observations"]:
        if row["status"] != "READY":
            print(f"{row['field_id']} | {row['reason']} | {row['source']} / {row['route']} | {row['action']}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["configuration"]["ipo_config"]["status"] == "VALID" else 2


if __name__ == "__main__":
    raise SystemExit(main())

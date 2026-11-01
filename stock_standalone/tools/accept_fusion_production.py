"""只读生产数据验收；报告仅写入显式指定的输出路径。"""
import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import zlib

from ats.fusion.shadow_io import LOG_NAME
from ats.fusion.source_identity import is_replay_record
from ats.fusion.paper_follow import read_paper_account, build_paper_follow


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def accept(root):
    root = Path(root).resolve()
    files = sorted(p for p in (root / "logs/fusion_shadow").glob("*.jsonl*") if LOG_NAME.fullmatch(p.name))
    evidence = files + [p for p in (root / "logs/fusion_iterations").glob("*/manifest.json")]
    evidence += [p for p in [root / "logs/paper_account_state.json", root / "ats/config/ipo_trading_ledger.json"] if p.is_file()]
    before = {str(p): fingerprint(p) for p in evidence}
    days, replay_runs, failures = [], [], []
    for path in files:
        counts, codes, stamps = Counter(), set(), []
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", encoding="utf-8-sig") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    counts["rows"] += 1
                    try:
                        row = json.loads(line)
                        code = str(row.get("code") or "").split(".")[0].zfill(6)
                        if len(code) != 6 or not code.isdigit():
                            counts["invalid_code"] += 1
                        if not row.get("writer_pid") or not row.get("source"):
                            counts["missing_provenance"] += 1
                        ts = float(row.get("ts") or 0)
                        stamp = datetime.fromtimestamp(ts)
                        price = float(row.get("price") or 0)
                        if not math.isfinite(price) or price <= 0:
                            counts["invalid_price"] += 1
                        if stamp.strftime("%Y-%m-%d") != path.name[:10]:
                            counts["timestamp_day_mismatch"] += 1
                        if row.get("trade_date") and str(row["trade_date"])[:10] != path.name[:10]:
                            counts["trade_date_mismatch"] += 1
                        if is_replay_record(row):
                            counts["replay_or_backfill"] += 1
                        else:
                            counts["not_marked_replay"] += 1
                        codes.add(str(row.get("code") or ""))
                        stamps.append(ts)
                    except (ValueError, TypeError, OverflowError, OSError, AttributeError):
                        counts["invalid_rows"] += 1
        except (OSError, EOFError, UnicodeError, zlib.error) as exc:
            failures.append({"file": str(path), "error": str(exc)})
        days.append({"file": str(path), "counts": dict(counts), "distinct_codes": len(codes),
                     "first": datetime.fromtimestamp(min(stamps)).isoformat() if stamps else None,
                     "last": datetime.fromtimestamp(max(stamps)).isoformat() if stamps else None,
                     "volume_ratio_trust": "unverified_legacy_observation"})
    for manifest in (root / "logs/fusion_iterations").glob("*/manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8-sig"))
            config = data.get("config") or {}
            replay_runs.append({"manifest": str(manifest), "status": data.get("status"),
                                "completed_days": [r.get("day") for r in data.get("completed", [])],
                                "use_production_history": config.get("use_production_history"),
                                "persist_context": config.get("persist_context"),
                                "engine_fingerprint": data.get("engine_fingerprint")})
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            failures.append({"file": str(manifest), "error": str(exc)})
    account = read_paper_account(str(root))
    paper = {"read_status": account.get("read_status"), "snapshot_day": account.get("trade_date")}
    if account.get("read_status") == "READY":
        try:
            cycles = build_paper_follow(account, [], datetime.now().strftime("%Y-%m-%d"))["rows"]
            paper.update(cycles=len(cycles), unresolved=sum(bool(r["issues"]) for r in cycles),
                         issues=dict(Counter(i for r in cycles for i in r["issues"])))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            failures.append({"section": "paper", "error": str(exc)})
    changed = [str(p) for p in evidence if fingerprint(p) != before[str(p)]]
    return {"root": str(root), "accepted": False, "shadow_files": days, "replay_runs": replay_runs,
            "paper": paper, "read_errors": failures, "inputs_changed_during_audit": changed,
            "input_sha256": before,
            "limitations": ["开发切片与合成测试不作为生产业务验收证据",
                            "文件哈希一致仅证明检查期间输入未变，不证明历史数据真实或完整",
                            "未核实旧备份及原始成交；未执行 EXE 部署或真实跨交易日验收",
                            "旧影子量比不视为可信实盘观测；缺少记录不推断没有信号"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    production = Path(args.root).resolve()
    if destination == production or production in destination.parents:
        parser.error("验收报告不得写入生产目录")
    report = accept(production)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(report["shadow_files"]), "paper": report["paper"],
                      "changed": report["inputs_changed_during_audit"], "errors": report["read_errors"]}, ensure_ascii=True))

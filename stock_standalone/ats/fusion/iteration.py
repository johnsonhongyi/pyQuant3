# -*- coding: utf-8 -*-
"""逐日影子迭代：按时点复用生产证据，隔离归档与样本外评价。"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta

from ats.fusion.anomaly import PATTERN_COUNTER_HOLD, PATTERN_COUNTER_RECLAIM
from ats.fusion.discovery_audit import summarize_result
from ats.fusion.history_events import HistoricalEvents
from ats.fusion.replay import DayReplay, ReplayConfig, _app_root, day_bounds


def _first_reclaims(result):
    first = {}
    for row in result.records:
        if PATTERN_COUNTER_RECLAIM in row.get("patterns", []):
            first.setdefault(row["code"], row)
    return first


def _compare_production(root, result, first):
    history = HistoricalEvents(root, result.day)
    cutoff = day_bounds(result.day)[0] + 14 * 3600 + 45 * 60
    old = {}
    for ts, code, kind, data in history.events:
        if ts > cutoff:
            break
        if kind == "gradient" and data.get("tier", 0) >= 2 and not data.get("veto"):
            old.setdefault(code, ts)
    if not history.stats["gradient_file_present"] or not history.stats["gradient"] or history.stats["errors"]:
        return {"available": False, "source": history.stats}
    new = {c: r for c, r in first.items() if r.get("ts", 0) <= cutoff}
    common = set(old) & set(new)
    leading = sum(1 for c in common if float(new[c]["ts"]) < old[c])
    return {
        "available": True, "source": history.stats,
        "production_l2_codes": len(old), "reclaim_codes": len(new),
        "both": len(common), "reclaim_only": len(set(new) - set(old)),
        "production_only": len(set(old) - set(new)), "reclaim_earlier": leading,
        "examples": [{"code": c, "production_ts": old[c], "reclaim_ts": new[c]["ts"]}
                     for c in sorted(common)[:100]],
        "note": "生产 L2 与新逆势观察口径不同；同日回放回补已排除。",
    }


def _advice(training):
    usable = [x for x in training if x.get("outcome_samples", 0) > 0 and not x.get("records_truncated")]
    n = sum(x["outcome_samples"] for x in usable)
    if len(usable) < 2 or n < 30:
        return {"status": "insufficient", "days": len(usable), "samples": n,
                "message": "历史已结算样本不足，不生成阈值修改建议。"}
    false_n = sum(x["false_positive_count"] for x in usable)
    opportunity_n = sum(x["opportunity_count"] for x in usable)
    detected_n = sum(x["detected_opportunities"] for x in usable)
    false_rate = false_n / n
    miss_rate = 1 - detected_n / opportunity_n if opportunity_n else None
    checks = []
    if false_rate >= 0.4:
        checks.append("观察信号次日未高于发现价的比例偏高，优先复核量能持续和结构失守。")
    if miss_rate is not None and miss_rate >= 0.5:
        checks.append("广义上涨机会漏报较高，按市场状态和形态分层检查；不宜直接放宽单一阈值。")
    cohorts = {}
    for daily in usable:
        for sample in daily.get("signal_samples", []):
            ratio = sample.get("detail", {}).get("vol_ratio")
            if not isinstance(ratio, (int, float)) or ratio <= 0:
                continue
            group = "量比<1" if ratio < 1 else ("量比1~2" if ratio < 2 else "量比>=2")
            bucket = cohorts.setdefault(group, {"n": 0, "not_above": 0})
            bucket["n"] += 1
            bucket["not_above"] += int(bool(sample.get("not_above")))
    cohorts = {name: {**value, "rate": round(value["not_above"] / value["n"], 4)}
               for name, value in cohorts.items() if value["n"] >= 10}
    return {"status": "review", "days": len(usable), "samples": n,
            "false_rate": round(false_rate, 4), "opportunity_count": opportunity_n,
            "miss_rate": round(miss_rate, 4) if miss_rate is not None else None,
            "volume_cohorts": cohorts, "checks": checks,
            "message": "仅供人工审核；不自动修改配置或交易规则。"}


def _atomic_json(path, data, compressed=False):
    tmp = path + ".tmp"
    with open(tmp, "wb") as raw:
        if compressed:
            with gzip.GzipFile(fileobj=raw, mode="wb") as stream:
                stream.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        else:
            raw.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(tmp, path)


def _next_cached_session(available, index):
    """缺少交易日历时，不跨过可能缺失的工作日假定下一交易日。"""
    if index + 1 >= len(available):
        return None
    start = datetime.strptime(available[index], "%Y-%m-%d").date()
    end = datetime.strptime(available[index + 1], "%Y-%m-%d").date()
    cursor = start + timedelta(days=1)
    while cursor < end:
        if cursor.weekday() < 5:
            return None
        cursor += timedelta(days=1)
    return available[index + 1]


def run_iterations(days=None, top_n=600, step=1, focus=(), output_root=None,
                   history_root=None, progress=None, replay=None):
    """逐日运行并写入独立目录；结果仅供观察和人工决策。"""
    root = history_root or _app_root()
    rp = replay or DayReplay(config=ReplayConfig(top_n=top_n, step=step, track=True, max_records=100000,
                                                 history_root=root, persist_context=False,
                                                 market_path=os.devnull))
    if not rp.cache:
        raise ValueError("找不到可用分钟线缓存")
    if rp.cfg.persist_context or rp.cfg.state_path:
        raise ValueError("逐日迭代必须禁用生产上下文写入和外部跟踪状态")
    rp.cfg.first_only = False
    available = rp.days()
    selected = sorted(set(days or available[-5:]))
    if not selected or any(day not in available for day in selected):
        raise ValueError("所选日期不在分钟缓存中")
    from ats.fusion.paper_follow import read_paper_account, read_shadow_days, build_paper_follow
    from ats.fusion.cross_day import build_cross_day
    paper_snapshot = read_paper_account(root)
    production_series, production_bad_rows = read_shadow_days(root, selected[-1])
    out = output_root or os.path.join(_app_root(), "logs", "fusion_iterations")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:10]
    run_dir = os.path.join(out, run_id)
    os.makedirs(run_dir, exist_ok=False)
    cfg = asdict(rp.cfg)
    fingerprint = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    manifest = {"schema": 1, "run_id": run_id, "status": "running", "days": selected,
                "config": cfg, "config_fingerprint": fingerprint, "completed": [],
                "source_policy": "生产事件按观测时刻可见；回放回补排除；数据不足不补造",
                "paper_source": {"path": paper_snapshot.get("source_path"), "mtime": paper_snapshot.get("source_mtime"),
                                 "snapshot_day": paper_snapshot.get("trade_date"), "read_status": paper_snapshot["read_status"],
                                 "shadow_bad_rows": production_bad_rows},
                "note": "结果隔离保存，不回写生产梯度、会话快照或交易配置。"}
    manifest_path = os.path.join(run_dir, "manifest.json")
    _atomic_json(manifest_path, manifest)
    settled = []
    previous = {}
    try:
        for index, day in enumerate(selected):
            # 当日开盘前只能使用在更早交易日收盘前已完成结算的结果。
            training = [x for x in settled if x.get("next_day") and x["next_day"] < day]
            advice = _advice(training)
            day_index = available.index(day)
            if index and (day_index == 0 or selected[index - 1] != available[day_index - 1]
                          or _next_cached_session(available, day_index - 1) != day):
                previous = {}
                rp.tracker = None
            next_day = _next_cached_session(available, day_index)
            def on_progress(cur, total):
                if progress:
                    progress(index, len(selected), cur, total)
            result = rp.run_day(day, focus=focus, carry_codes=previous.keys(), progress=on_progress)
            if result.meta.get("error"):
                raise RuntimeError("{}: {}".format(day, result.meta["error"]))
            first = _first_reclaims(result)
            latest_carried = {}
            for row in result.records:
                if row.get("carried_observation"):
                    latest_carried[row["code"]] = row
            carry_states = {}
            for code in previous:
                row = latest_carried.get(code)
                if result.meta.get("records_truncated") or row is None or row.get("time", "") < "14:50":
                    carry_states[code] = "数据不足"
                elif {PATTERN_COUNTER_RECLAIM, PATTERN_COUNTER_HOLD} & set(row.get("patterns") or []):
                    carry_states[code] = "收盘前仍满足观察"
                else:
                    carry_states[code] = "收盘前不再满足观察"
            summary = summarize_result(rp, result, next_day, focus)
            summary["production_compare"] = _compare_production(root, result, first)
            summary["previous_observations"] = {
                "day": selected[index - 1] if index else None,
                "carried": len(previous), "observed_again": len(set(previous) & set(first)),
                "not_reobserved": sorted(set(previous) - set(first)),
                "close_states": carry_states,
            }
            summary["prior_day_advice"] = advice
            summary["approximations"] = result.meta.get("approximations", [])
            summary["records_truncated"] = result.meta.get("records_truncated", 0)
            paper = build_paper_follow(paper_snapshot, build_cross_day(production_series, day), day)
            summary["paper_review"] = {
                "read_status": paper_snapshot["read_status"],
                "fills_on_day": sum(str(o.get("timestamp") or "")[:10] == day for o in paper_snapshot.get("orders", [])),
                "holding_cycles": sum(row["remaining"] > 0 for row in paper["rows"]),
                "closed_cycles": sum(row["status"] == "已平仓" for row in paper["rows"]),
                "unresolved_cycles": sum(bool(row["issues"]) for row in paper["rows"]),
                "note": "PAPER原账本按日期截断；历史持仓为成交投影；最新账户就绪状态不作为历史决策证据。",
            }
            artifact = {"schema": 1, "summary": summary, "result": result.to_dict()}
            artifact["paper_follow"] = {"rows": paper["rows"], "source": manifest["paper_source"]}
            filename = day + ".json.gz"
            _atomic_json(os.path.join(run_dir, filename), artifact, compressed=True)
            manifest["completed"].append({"day": day, "file": filename, "summary": summary})
            _atomic_json(manifest_path, manifest)
            settled.append(summary)
            previous = first
        manifest["status"] = "complete"
        _atomic_json(manifest_path, manifest)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        _atomic_json(manifest_path, manifest)
        raise
    return {"run_dir": run_dir, "manifest": manifest, "last_result": result}


def render_iteration(output):
    manifest = output["manifest"]
    lines = ["逐日梯度迭代：{}".format(manifest["status"]), "档案：{}".format(output["run_dir"]), ""]
    for item in manifest["completed"]:
        s = item["summary"]
        prod = s["production_compare"]
        lines.append("{} | 候选 {} | 观察 {} | 次日误报 {} ({}/{}) | 广义漏报 {} ({}/{})".format(
            item["day"], s["candidates"], s["observations_before_1445"],
            "--" if s["false_positive_rate"] is None else "{:.1%}".format(s["false_positive_rate"]),
            s["false_positive_count"], s["outcome_samples"],
            "--" if s["miss_rate"] is None else "{:.1%}".format(s["miss_rate"]),
            s["opportunity_count"] - s["detected_opportunities"], s["opportunity_count"]))
        lines.append("  生产梯度：{}；昨日观察延续 {}/{}；{}".format(
            "对照 {} 只".format(prod["production_l2_codes"]) if prod["available"] else "缺少可靠文件",
            s["previous_observations"]["observed_again"], s["previous_observations"]["carried"],
            s["prior_day_advice"]["message"]))
        focus = s.get("focus_selection") or {}
        lines.append("  逆势重点：同时最多{} / 全天换入{}；次日误报{}；广义机会发现{}".format(
            focus.get("max_simultaneous", 0), focus.get("daily_distinct", 0),
            "--" if focus.get("false_positive_rate") is None else "{:.1%}".format(focus["false_positive_rate"]),
            focus.get("detected_opportunities", 0)))
        if s.get("records_truncated"):
            lines.append("  注意：{} 条评估记录超过上限未归档，统计不完整。".format(s["records_truncated"]))
        if s.get("paper_review"):
            paper = s["paper_review"]
            lines.append("  PAPER：{}；当日成交{} / 持仓周期{} / 已平仓周期{} / 待核{}".format(
                paper["read_status"], paper["fills_on_day"], paper["holding_cycles"], paper["closed_cycles"], paper["unresolved_cycles"]))
    lines.append("\n次日评价仅在下一交易日收盘数据可用时计算；建议不自动应用。")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("days", nargs="*", help="交易日 YYYY-MM-DD；默认最近五天")
    parser.add_argument("--top", type=int, default=600)
    parser.add_argument("--step", type=int, default=1)
    args = parser.parse_args()
    print(render_iteration(run_iterations(days=args.days or None, top_n=args.top, step=args.step)))

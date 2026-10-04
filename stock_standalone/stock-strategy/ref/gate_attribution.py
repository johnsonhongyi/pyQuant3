#!/usr/bin/env python3
"""统一决策门归因(2026-10-01):按因子拆解,回答"到底谁影响了"。
读 logs/decisions_*.json(BUY带factors) + paper_ledger.json closed[],
按因子分组统计:笔数/胜率/平均盈亏/总盈亏。
用法: python3 gate_attribution.py [--market CN|US]
"""
import json, glob, os, sys
from collections import defaultdict

SVC = os.path.dirname(os.path.abspath(__file__))
MARKET = "US" if "--market" in sys.argv and sys.argv[sys.argv.index("--market")+1].upper() == "US" else "CN"

def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return None

def main():
    lg = load(os.path.join(SVC, "logs", "paper_ledger_us.json" if MARKET == "US" else "paper_ledger.json")) or {}
    closed = lg.get("closed", [])
    # 建索引: (code,buy_date) -> BUY factors
    buy_factors = {}
    pat = "decisions_us_*.json" if MARKET == "US" else "decisions_*.json"
    for fp in sorted(glob.glob(os.path.join(SVC, "logs", pat))):
        d = load(fp)
        ds = d.get("decisions", []) if isinstance(d, dict) else (d or [])
        for e in ds:
            if e.get("action") == "BUY" and e.get("factors"):
                buy_factors[(e.get("code"), e.get("factors", {}).get("buy_date") or "")] = e["factors"]
    # 归因维度
    groups = defaultdict(list)
    for t in closed:
        sn = t.get("snapshot", {}) or {}
        key = (t.get("code"), t.get("buy_date") or "")
        f = buy_factors.get(key, {})
        pnl = t.get("pnl", 0) or 0
        bp = t.get("buy_price") or 1
        ret = pnl / (bp * t.get("shares", 1) or 1) * 100 if t.get("shares") else 0
        src = (sn.get("source") or f.get("source") or "?")
        dims = {
            "来源": "P24大阳" if "P24" in src else ("P18补回" if "P18" in src else "P8早盘"),
            "P26板块": "通过" if (sn.get("sector_score") or f.get("p26") or 0) >= 50 else "未过/无",
            "大阳": "是" if (sn.get("dayang") or f.get("p24_dayang")) else "否",
            "池分": "高(>=10)" if (sn.get("pool_score") or f.get("pool_score") or 0) >= 10 else "中(<10)",
        }
        for k, v in dims.items():
            groups["%s=%s" % (k, v)].append((pnl, ret))
    print("=== 因子归因 (%s, 共%d笔已平仓) ===" % (MARKET, len(closed)))
    print("%-14s %4s %6s %8s %10s" % ("因子", "笔数", "胜率", "平均%", "总盈亏"))
    for k in sorted(groups):
        ps = groups[k]
        n = len(ps)
        wins = sum(1 for _, r in ps if r > 0)
        avg = sum(r for _, r in ps) / n if n else 0
        tot = sum(p for p, _ in ps)
        print("%-16s %4d %5.0f%% %7.1f%% %+.0f" % (k, n, wins / n * 100 if n else 0, avg, tot))
    # SKIP 原因统计
    skips = defaultdict(int)
    for fp in sorted(glob.glob(os.path.join(SVC, "logs", pat))):
        d = load(fp)
        ds = d.get("decisions", []) if isinstance(d, dict) else (d or [])
        for e in ds:
            if e.get("action") == "SKIP":
                sk = (e.get("factors") or {}).get("skip_gate") or e.get("why", "")[:12]
                skips[sk] += 1
    if skips:
        print("\n=== SKIP 被哪道门拦下 ===")
        for k, v in sorted(skips.items(), key=lambda x: -x[1])[:10]:
            print("  %-20s %d次" % (k, v))

if __name__ == "__main__":
    main()

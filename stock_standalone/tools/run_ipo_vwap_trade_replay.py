"""Run an offline paper-trade replay using production signals and raw TDX VWAP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Source bootstrap is only for imports; persistent data uses the system root.
if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

from sys_utils import get_app_root, safe_resolve_path

APP_ROOT = safe_resolve_path(get_app_root())

from ats.llm.production_vwap_trade_replay import (
    collect_production_vwap_trade_replay,
    persist_replay_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读生产交易/信号数据库和TDX原始日线，生成VWAP纸面回放与逐笔对账；绝不下单。"
    )
    parser.add_argument("--root", type=Path, default=APP_ROOT, help="ATS程序根目录")
    parser.add_argument(
        "--report-dir", type=Path, default=Path("data/ipo_learning/vwap_trade_replay"),
        help="仅在项目根目录内保存本地CSV与JSON报告",
    )
    parser.add_argument("--no-report", action="store_true", help="仅计算并打印汇总，不写本地文件")
    args = parser.parse_args()

    try:
        report = collect_production_vwap_trade_replay(args.root)
        if not args.no_report:
            report = persist_replay_report(args.root, args.report_dir, report)
        summary = {key: value for key, value in report.items() if not key.startswith("_")}
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

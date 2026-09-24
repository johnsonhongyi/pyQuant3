# -*- coding: utf-8 -*-
"""Shadow Live Test Runner (影子实盘全天候无报单压测启动器).

Guarantees 100% paper trading / simulation mode with NO real-world broker orders.
Monitors system stability, memory footprint, Tick latency, and directive generation.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, Optional

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class ShadowTestHealthMonitor:
    """Collects runtime health metrics during shadow live stress testing."""

    def __init__(self, log_dir: str = "logs", build_identity: Optional[Dict[str, Any]] = None) -> None:
        self.log_dir = log_dir
        self.build_identity = dict(build_identity or {})
        os.makedirs(self.log_dir, exist_ok=True)
        self.start_time = time.time()
        self.rounds_completed = 0
        self.signals_processed = 0
        self.directives_generated = 0
        self.errors_encountered = 0
        self.last_snapshot_ts = 0.0

    def get_memory_rss_mb(self) -> float:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def record_round(
        self,
        *,
        signal_count: int = 0,
        directive_count: int = 0,
        active_positions: int = 0,
        ledger_stats: Optional[Dict[str, Any]] = None,
        paper_execution: str = "NOT_CONNECTED_ISOLATED",
        paper_execution_scope: str = "ISOLATED",
    ) -> Dict[str, Any]:
        self.rounds_completed += 1
        self.signals_processed += signal_count
        self.directives_generated += directive_count
        now = time.time()
        uptime_seconds = round(now - self.start_time, 1)

        metrics = {
            "timestamp": datetime.datetime.now().isoformat(),
            "uptime_seconds": uptime_seconds,
            "rounds_completed": self.rounds_completed,
            "memory_rss_mb": self.get_memory_rss_mb(),
            "signals_processed": self.signals_processed,
            "directives_generated": self.directives_generated,
            "active_positions": active_positions,
            "errors_encountered": self.errors_encountered,
            "ledger_stats": ledger_stats or {},
            "paper_execution": paper_execution,
            "paper_execution_scope": paper_execution_scope,
            "build_identity": self.build_identity,
            "real_broker_orders": 0,
            "status": "HEALTHY" if self.errors_encountered == 0 else "DEGRADED",
        }

        # Daily report dump
        today_str = datetime.date.today().strftime("%Y%m%d")
        report_file = os.path.join(self.log_dir, f"shadow_test_report_{today_str}.jsonl")
        try:
            with open(report_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(metrics, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception as exc:
            self.errors_encountered += 1
            metrics["status"] = "DEGRADED"
            metrics["report_write_error"] = str(exc)

        return metrics


def setup_shadow_environment() -> None:
    """Enforce paper trading and mock/shadow boundaries strictly."""
    os.environ["ATS_SHADOW_MODE"] = "1"
    os.environ["PAPER_TRADING_ONLY"] = "1"
    os.environ["DISABLE_REAL_BROKER_ORDERS"] = "1"
    print("[ShadowRunner] 影子实盘环境锁定完成: 物理报单插头已彻底拔出 (100% 纸面/影子撮合)")


def _collect_runtime_build_identity() -> Dict[str, Any]:
    from trading_kernel.build_fingerprint import collect_build_fingerprint

    identity = collect_build_fingerprint(repo_root=_PROJECT_ROOT)
    exe_sha256 = ""
    if bool(getattr(sys, "frozen", False)):
        digest = hashlib.sha256()
        with open(sys.executable, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        exe_sha256 = digest.hexdigest()
    return {
        "git_commit": str(identity.get("git_commit") or "unknown"),
        "git_dirty": bool(identity.get("git_dirty", True)),
        "fingerprint": str(identity.get("fingerprint") or ""),
        "exe_sha256": exe_sha256,
        "frozen_runtime": bool(getattr(sys, "frozen", False)),
    }


def _resolve_isolated_roots(report_dir: str, state_dir: str) -> tuple[str, str]:
    report_root = os.path.realpath(report_dir)
    state_root = os.path.realpath(state_dir)
    try:
        if os.path.commonpath([report_root, state_root]) != report_root or state_root == report_root:
            raise ValueError("isolated PAPER state directory must be a child of the report directory")
    except (ValueError, OSError) as exc:
        raise ValueError("isolated PAPER state directory must be inside report directory") from exc
    return report_root, state_root


def run_shadow_test(
    dry_run: bool = False,
    interval_seconds: float = 3.0,
    max_rounds: Optional[int] = None,
    candidate_codes: Optional[list[str]] = None,
    log_dir: str = "logs/shadow_reports",
    isolated_paper_state_dir: Optional[str] = None,
) -> Dict[str, Any]:
    setup_shadow_environment()
    monitor = ShadowTestHealthMonitor(
        log_dir=log_dir,
        build_identity=_collect_runtime_build_identity(),
    )
    from ats.signal_ledger import SignalLedger
    from ats.ledger_update_service import LedgerUpdateService
    from ats.strategy.ipo_trading_center import IPOTradingCenter
    from ats.strategy.ipo_vwap_detector_engine import IPOVWAPDetectorEngine

    ledger = SignalLedger()
    candidate_service = LedgerUpdateService(ledger)
    codes = sorted({str(code).strip().zfill(6) for code in (candidate_codes or []) if str(code).strip()})

    print(f"[ShadowRunner] 启动全天候影子实盘压测... (dry_run={dry_run}, interval={interval_seconds}s)")

    target_rounds = 2 if dry_run else (max_rounds or 999999999)
    last_metrics: Dict[str, Any] = {}
    if not codes:
        if isolated_paper_state_dir:
            _resolve_isolated_roots(log_dir, isolated_paper_state_dir)
        monitor.errors_encountered += 1
        last_metrics = monitor.record_round(ledger_stats={"error": "MISSING_CANDIDATE_CODES"})
        last_metrics["status"] = "DEGRADED"
        last_metrics["error"] = "MISSING_CANDIDATE_CODES"
        return last_metrics
    if not dry_run and not isolated_paper_state_dir:
        monitor.errors_encountered += 1
        last_metrics = monitor.record_round(
            ledger_stats={"error": "ISOLATED_PAPER_STATE_REQUIRED"},
            paper_execution="NOT_CONNECTED_ISOLATED",
            paper_execution_scope="ISOLATED",
        )
        last_metrics["status"] = "DEGRADED"
        last_metrics["error"] = "ISOLATED_PAPER_STATE_REQUIRED"
        return last_metrics

    detector = IPOVWAPDetectorEngine() if codes else None
    gateway = None
    paper_execution = "NOT_CONNECTED_ISOLATED"
    if isolated_paper_state_dir:
        from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
        from trading_kernel.kernel_service import TradingKernelService
        from trading_kernel.gateway import KernelGateway
        from ats.unified_paper_account import execute_command_directive

        report_root, state_root = _resolve_isolated_roots(log_dir, isolated_paper_state_dir)
        os.makedirs(state_root, exist_ok=True)
        state_root = os.path.realpath(state_root)
        if os.path.commonpath([report_root, state_root]) != report_root or state_root == report_root:
            raise ValueError("isolated PAPER state directory resolved outside report directory")
        isolation_targets = [
            (os.path.join(state_root, "paper_account_state.json"), state_root),
            (os.path.join(state_root, "kernel_trace.jsonl"), state_root),
            (os.path.join(state_root, "ats_shadow_ledger.json"), state_root),
            (os.path.join(state_root, "reconciliation"), state_root),
            (
                os.path.join(report_root, f"shadow_test_report_{datetime.date.today():%Y%m%d}.jsonl"),
                report_root,
            ),
        ]
        for path, parent in isolation_targets:
            resolved_path = os.path.realpath(path)
            try:
                if os.path.commonpath([parent, resolved_path]) != parent or os.path.islink(path):
                    raise ValueError(f"shadow output path escapes its isolated root: {path}")
            except (ValueError, OSError) as exc:
                raise ValueError(f"shadow output path escapes its isolated root: {path}") from exc
        adapter = PaperExecutionAdapter(
            state_file_path=os.path.join(state_root, "paper_account_state.json")
        )
        tk_service = TradingKernelService(
            journal_path=os.path.join(state_root, "kernel_trace.jsonl"),
            reconciliation_dir=os.path.join(state_root, "reconciliation"),
            paper_adapter=adapter,
            initial_mode="PAPER",
        )
        if tk_service.mode != "PAPER" or tk_service.executor is not adapter:
            raise RuntimeError("isolated TK service did not remain in PAPER mode")
        gateway = KernelGateway(service=tk_service)
        paper_execution = "CONNECTED"

    executor = (
        (lambda directive: execute_command_directive(directive, gateway=gateway))
        if gateway is not None else None
    )
    center = IPOTradingCenter(
        auto_load_ledger=False,
        ledger_file=os.path.join(state_root, "ats_shadow_ledger.json") if gateway is not None else None,
        directive_executor=executor,
    ) if codes else None

    for round_idx in range(1, target_rounds + 1):
        signals = []
        directives = []
        positions = {}
        paper_results = []
        directive_audit = []
        try:
            if detector is not None and center is not None:
                for code in codes:
                    signal = detector.analyze_stock(code, force_refresh=True)
                    if signal is None or float(getattr(signal, "price", 0.0) or 0.0) <= 0:
                        continue
                    signals.append(signal)
                    candidate_service.update_candidate(
                        code=signal.code, name=signal.name, price=signal.price,
                        pct=signal.change_pct, deviation=signal.vwap_diff_pct,
                        source="ATS_SHADOW", observed_at=datetime.datetime.now().isoformat(),
                    )
                center.submit_batch_reports(signals)
                directives = center.get_pending_directives()
                paper_results = []
                directive_audit = []
                if gateway is not None:
                    for directive in directives:
                        executed = bool(center.execute_directive(directive))
                        paper_results.append(executed)
                        envelope = getattr(directive, "audit_envelope", None) or {}
                        directive_audit.append({
                            "directive_id": str(getattr(directive, "directive_id", "") or ""),
                            "request_id": str(envelope.get("request_id") or ""),
                            "order_id": str(envelope.get("order_id") or ""),
                            "execution_id": str(envelope.get("execution_id") or ""),
                            "status": str(envelope.get("status") or ("EXECUTED" if executed else "REJECTED")),
                            "gate_reason": str(envelope.get("gate_reason") or ""),
                        })
                    positions = gateway.get_positions()
                else:
                    positions = center.get_positions() if hasattr(center, "get_positions") else {}
                    directive_audit = []
            else:
                directives, positions = [], {}
                paper_results = []
                directive_audit = []

            # Counts come from live detector, candidate ledger and ATS arbitration.
            stats = {
                "total_entries": len(ledger.entries),
                "radar_count": sum(1 for e in ledger.entries.values() if getattr(e, "tier", "") == "RADAR"),
                "watch_count": sum(1 for e in ledger.entries.values() if getattr(e, "tier", "") == "WATCH"),
                "trade_count": sum(1 for e in ledger.entries.values() if getattr(e, "tier", "") == "TRADE"),
                "inactive_count": sum(1 for e in ledger.entries.values() if getattr(e, "tier", "") == "INACTIVE"),
                "candidate_count": len(codes),
                "valid_signal_count": len(signals),
                "directive_count": len(directives),
                "paper_result_count": len(paper_results),
                "paper_executed_count": sum(1 for item in paper_results if item),
                "paper_order_count": len(gateway.get_order_history()) if gateway is not None else 0,
                "directive_audit": directive_audit,
                "pipeline_status": (
                    "ATS_ARBITRATED_ISOLATED_TK_PAPER" if gateway is not None
                    else "ATS_ARBITRATED_PAPER_NOT_CONNECTED"
                ),
            }

            last_metrics = monitor.record_round(
                signal_count=len(signals),
                directive_count=len(directives),
                active_positions=len(positions),
                ledger_stats=stats,
                paper_execution=paper_execution,
                paper_execution_scope="ISOLATED",
            )

            if dry_run:
                print(f"[ShadowRunner][DryRun] 轮次 {round_idx}/{target_rounds} 成功完成: {last_metrics['status']}")
            else:
                if round_idx % 10 == 0:
                    print(
                        f"[ShadowRunner] 第 {round_idx} 轮完成 | "
                        f"内存: {last_metrics['memory_rss_mb']} MB | "
                        f"账本总数: {stats['total_entries']} | "
                        f"状态: {last_metrics['status']}"
                    )
                time.sleep(interval_seconds)

        except Exception as e:
            monitor.errors_encountered += 1
            print(f"[ShadowRunner][ERROR] 压测轮次发生异常: {e}")
            last_metrics = monitor.record_round(
                signal_count=len(signals),
                directive_count=len(directives),
                active_positions=len(positions),
                ledger_stats={
                    "error": str(e),
                    "candidate_count": len(codes),
                    "directive_count": len(directives),
                    "paper_result_count": len(paper_results),
                    "directive_audit": directive_audit,
                    "pipeline_status": (
                        "ATS_ARBITRATED_ISOLATED_TK_PAPER" if gateway is not None
                        else "ATS_ARBITRATED_PAPER_NOT_CONNECTED"
                    ),
                },
                paper_execution=paper_execution,
                paper_execution_scope="ISOLATED",
            )
            if dry_run:
                break

    print("[ShadowRunner] 影子压测执行完毕，体检报告已生成。")
    return last_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="ATS 影子实盘全天候压测启动器")
    parser.add_argument("--dry-run", action="store_true", help="单次自检测试并退出")
    parser.add_argument("--interval", type=float, default=3.0, help="轮询间隔秒数 (默认 3.0s)")
    parser.add_argument("--max-rounds", type=int, default=None, help="最大执行轮数")
    parser.add_argument("--codes", default="", help="待监控股票代码，逗号分隔；空值不会伪造样例信号")
    parser.add_argument("--report-dir", default="logs/shadow_reports", help="影子报告目录")
    parser.add_argument(
        "--isolated-paper-state-dir",
        default="",
        help="显式启用隔离 TK PAPER，并将状态/审计写入 report-dir 的子目录",
    )
    args = parser.parse_args()

    run_shadow_test(
        dry_run=args.dry_run,
        interval_seconds=args.interval,
        max_rounds=args.max_rounds,
        candidate_codes=[item for item in args.codes.split(",") if item.strip()],
        log_dir=args.report_dir,
        isolated_paper_state_dir=args.isolated_paper_state_dir or None,
    )


if __name__ == "__main__":
    main()

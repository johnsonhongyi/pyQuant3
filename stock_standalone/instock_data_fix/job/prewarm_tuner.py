"""Premarket history prewarm metrics ledger and adaptive auto-tuner."""
import datetime
import json
import logging
import os
import time

DEFAULT_METRICS_PATH = os.environ.get(
    'INSTOCK_PREWARM_METRICS_PATH',
    '/data/InStock/instock/log/prewarm_history_metrics.jsonl'
)


def _resolve_metrics_path(metrics_path=None):
    if metrics_path:
        return metrics_path
    path = DEFAULT_METRICS_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    return path


def record_prewarm_metrics(metrics, metrics_path=None):
    """Append a structured run record to the persistent metrics ledger."""
    path = _resolve_metrics_path(metrics_path)
    record = dict(
        timestamp=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        **metrics
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        logging.info("Prewarm metrics recorded to %s: elapsed=%.2fs throughput=%.1f/s workers=%s",
                     path, record.get('seconds', 0.0), record.get('throughput', 0.0), record.get('workers'))
        return record
    except OSError as exc:
        logging.warning("Failed to record prewarm metrics to %s: %s", path, exc)
        return record


def get_prewarm_history(limit=14, metrics_path=None):
    """Read the recent N prewarm run records from the ledger."""
    path = _resolve_metrics_path(metrics_path)
    if not os.path.isfile(path):
        return []
    records = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logging.warning("Failed to read prewarm metrics history from %s: %s", path, exc)
        return []

    # 按时间倒序返回最近的记录
    return records[-limit:]


def auto_tune_prewarm_config(cpu_total=None, metrics_path=None):
    """
    Analyze past prewarm executions and adaptively tune concurrency and batch settings.
    Strictly observes the hard safety gate: workers <= min(3, cpu_total - 1).
    """
    cpu = cpu_total or os.cpu_count() or 4
    # 严格门禁：最多 3 个 Worker，且最多为 CPU - 1
    max_safe_workers = max(1, min(3, cpu - 1))

    history = get_prewarm_history(limit=7, metrics_path=metrics_path)
    if not history:
        # 场景 1：无历史数据（冷启动），采用基准安全配置
        return {
            "workers": max_safe_workers,
            "max_safe_workers": max_safe_workers,
            "strategy": "cold_start_baseline",
            "history_count": 0,
            "recent_avg_sec": None,
            "recent_avg_throughput": None,
            "recommendation": "首次运行，采用标准安全门禁并发"
        }

    valid_runs = [r for r in history if r.get('seconds') and r.get('seconds') > 0 and r.get('stocks')]
    if not valid_runs:
        return {
            "workers": max_safe_workers,
            "max_safe_workers": max_safe_workers,
            "strategy": "insufficient_valid_history",
            "history_count": len(history),
            "recent_avg_sec": None,
            "recent_avg_throughput": None,
            "recommendation": "历史有效样本不足，维持标准安全门禁"
        }

    recent_runs = valid_runs[-5:]
    avg_sec = sum(r['seconds'] for r in recent_runs) / len(recent_runs)
    avg_throughput = sum(r.get('throughput', r['stocks'] / r['seconds']) for r in recent_runs) / len(recent_runs)

    # 场景 2：耗时过长或检测到机械硬盘寻道摩擦过大（单股平均耗时超过 25ms 或总耗时超 150s）
    # 机械硬盘特性：当发生严重寻道拥塞时，适度降低并发线程反而能减少磁头反复臂移损耗
    if avg_sec > 120.0 or (avg_throughput > 0 and avg_throughput < 45.0):
        tuned_workers = max(1, min(2, max_safe_workers))
        strategy = "hdd_contention_throttling"
        recommendation = f"近几日预热平均耗时较高({avg_sec:.1f}s)，自适应降级至{tuned_workers}进程以减少外置机械硬盘寻道冲突"
    # 场景 3：近期吞吐稳定优秀（吞吐率 >= 100/s 或 耗时 < 60s）
    elif avg_sec < 60.0 or avg_throughput >= 90.0:
        tuned_workers = max_safe_workers
        strategy = "optimal_throughput"
        recommendation = f"近几日预热吞吐极高({avg_throughput:.1f}标的/s)，维持满血安全门禁{tuned_workers}并发"
    # 场景 4：常规平稳状态
    else:
        tuned_workers = max_safe_workers
        strategy = "standard_smooth"
        recommendation = f"近几日运行平稳(平均{avg_sec:.1f}s)，维持推荐安全配置{tuned_workers}并发"

    return {
        "workers": tuned_workers,
        "max_safe_workers": max_safe_workers,
        "strategy": strategy,
        "history_count": len(history),
        "recent_avg_sec": round(avg_sec, 2),
        "recent_avg_throughput": round(avg_throughput, 1),
        "recommendation": recommendation
    }

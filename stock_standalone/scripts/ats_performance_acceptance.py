"""Controlled alternating offline A/B; never substitutes for live/EXE acceptance."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psutil
import numpy as np
import pandas as pd
from scripts.ats_architecture_perf_probe import make_frame, probe, production_bridge


def run(output, samples=101):
    previous = sys.modules.get('ats.tdx_realtime_fetcher')
    sys.modules['ats.tdx_realtime_fetcher'] = types.SimpleNamespace(is_trading_time=lambda: (True, 'offline'))
    original = os.environ.get('ATS_BATCH_DIFF')
    try:
        bridge = production_bridge()
        frame = make_frame(5000)
        results = []
        for repeat in range(3):
            for enabled in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                os.environ['ATS_BATCH_DIFF'] = str(enabled)
                result = probe(bridge, frame, 'diff_all_numeric_columns', samples=samples)
                result.update(repeat=repeat, batch_enabled=bool(enabled),
                              cpu_percent=psutil.cpu_percent(), process_count=len(psutil.pids()))
                results.append(result)
        files = ['ats/ipc_bridge.py', 'ats/frame_merge.py', 'scripts/ats_architecture_perf_probe.py']
        power = subprocess.run(['powercfg', '/getactivescheme'], capture_output=True,
                               text=True, errors='replace', timeout=5)
        report = dict(scope='offline IPC receive only', release_ready=False,
                      live_session=False, exe=False, soak_72h=False,
                      python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__,
                      platform=platform.platform(), cpu_count=psutil.cpu_count(),
                      power_scheme=power.stdout.strip(), recorded_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                      source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
                      samples=samples, warmup=3, results=results)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': output, 'results': results}, ensure_ascii=False))
    finally:
        if previous is None:
            sys.modules.pop('ats.tdx_realtime_fetcher', None)
        else:
            sys.modules['ats.tdx_realtime_fetcher'] = previous
        if original is None:
            os.environ.pop('ATS_BATCH_DIFF', None)
        else:
            os.environ['ATS_BATCH_DIFF'] = original


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='docs/ats_closed_loop/performance_ab_20261003.json')
    parser.add_argument('--samples', type=int, default=101)
    args = parser.parse_args()
    run(args.output, args.samples)

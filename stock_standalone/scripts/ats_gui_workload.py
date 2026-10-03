"""Isolated synthetic Qt workload; never a live trading acceptance report."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from collections import deque

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(seconds, rows):
    import shutil
    output = ROOT / '.ats_validation' / ('gui_soak' if seconds >= 3600 else 'gui_workload')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'config', output / 'config', dirs_exist_ok=True)
    os.environ.update(INSTOCK_APP_ROOT=str(output), ATS_TEST_MODE='1',
                      ATS_PERF='1', QT_QPA_PLATFORM='offscreen')
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    from ats.ipc_bridge import IPCBridge
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher, TDXGlobalCachePool
    from ats.capital_dragon_engine import CapitalDragonEngine
    from JSONData import tdx_hdf5_api
    import data_utils
    # Isolate external transport/history; all Qt frame/projection code stays real.
    IPCBridge.start_realtime_listener = lambda *args, **kwargs: None
    data_utils.send_code_via_pipe = lambda *args, **kwargs: None
    TDXRealtimeFetcher.get_security_quotes_safe = lambda *args, **kwargs: []
    TDXRealtimeFetcher.get_batch_finance_shares = lambda *args, **kwargs: {}
    TDXGlobalCachePool._load_from_ramdisk = lambda *args, **kwargs: None
    CapitalDragonEngine._fetch_tdx_index_data = lambda *args, **kwargs: {}
    CapitalDragonEngine._compute_market_summary_bg = lambda *args, **kwargs: None
    tdx_hdf5_api.load_hdf_db = lambda *args, **kwargs: None
    from ats.ui.main_window import ATSMainWindow
    from ats.performance import snapshot
    from scripts.ats_architecture_perf_probe import make_frame
    import psutil
    app = QApplication([])
    window = ATSMainWindow()
    window.show()
    base = make_frame(rows)
    base.index = [f'{600000 + index:06d}' for index in range(rows)]
    started = time.monotonic()
    previous = [started]
    jitter = deque(maxlen=10000)
    rss = deque(maxlen=10000)
    sent = [0]
    closing = [False]
    from scripts.ats_runtime_acceptance import fingerprint
    initial_fingerprint = fingerprint([sys.executable])
    run_id = os.environ.get('ATS_VALIDATION_RUN_ID', str(uuid.uuid4()))

    def report(code=None):
        values = sorted(jitter)
        return dict(scope='offscreen synthetic Qt; transport/history substituted; no live business acceptance',
                    rows=rows, columns=len(base.columns), frames_sent=sent[0],
                    requested_seconds=seconds, elapsed_sec=time.monotonic()-started,
                    updated_at_epoch=time.time(),
                    run_id=run_id,
                    exit_code=code, completed=code is not None,
                    input_sha256=initial_fingerprint,
                    event_loop_jitter_ms={f'p{p}': values[min(len(values)-1, int(len(values)*p/100))]
                                          for p in (50, 95, 99)} if values else {},
                    sample_capacity=10000, rss_bytes=list(rss),
                    telemetry=snapshot(), release_ready=False)

    checkpoint_stop = threading.Event()
    def checkpoints():
        last_checkpoint = time.monotonic()
        while not checkpoint_stop.wait(1):
            process = psutil.Process()
            rss.append(process.memory_info().rss)
            if time.monotonic() - last_checkpoint >= 60:
                current = report()
                path = output / 'progress.json'
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(current, indent=2), encoding='utf-8')
                temporary.replace(path)
                trend = dict(run_id=run_id, elapsed_sec=current['elapsed_sec'],
                             frames_sent=sent[0], rss_bytes=rss[-1],
                             threads=process.num_threads(),
                             children=len(process.children(recursive=True)),
                             event_loop_jitter_ms=current['event_loop_jitter_ms'],
                             stages=current['telemetry']['summary'])
                with (output / 'resource_trend.jsonl').open('a', encoding='utf-8') as history:
                    history.write(json.dumps(trend) + '\n')
                last_checkpoint = time.monotonic()
    checkpoint_thread = threading.Thread(target=checkpoints, daemon=True)
    checkpoint_thread.start()

    def heartbeat():
        now = time.monotonic()
        jitter.append(max(0, (now - previous[0]) * 1000 - 20))
        previous[0] = now

    def feed():
        frame = base.copy(deep=True)
        sent[0] += 1
        frame['percent'] += (sent[0] % 10) * .01
        frame.attrs.update(sync_session='isolated-gui', source_version=sent[0], ver=sent[0])
        window._queue_latest_ipc_frame(frame)
        if sent[0] % 4 == 0:
            window.refresh_realtime_ui()

    def finish():
        if not closing[0] and time.monotonic() - started >= seconds:
            closing[0] = True
            producer.stop()
            window.close()
        if closing[0] and not window.isVisible():
            app.quit()
        elif time.monotonic() - started >= seconds + 40:
            app.exit(2)

    pulse = QTimer()
    pulse.timeout.connect(heartbeat)
    pulse.start(20)
    producer = QTimer()
    producer.timeout.connect(feed)
    producer.start(250)
    ending = QTimer()
    ending.timeout.connect(finish)
    ending.start(100)
    code = app.exec()
    checkpoint_stop.set()
    checkpoint_thread.join(timeout=5)
    final = report(code)
    final['inputs_unchanged'] = initial_fingerprint == fingerprint([sys.executable])
    (output / 'result.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in final.items() if key not in ('rss_bytes', 'telemetry', 'input_sha256')}))
    return code


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--rows', type=int, default=5000)
    args = parser.parse_args()
    sys.exit(main(args.seconds, args.rows))

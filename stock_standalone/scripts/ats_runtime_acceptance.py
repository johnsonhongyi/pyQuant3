"""Isolated source/packaged startup and bounded shutdown evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(command):
    paths = [ROOT / name for name in (
        'run_ats.py', 'ats/main_ats.py', 'ats/ui/main_window.py',
        'ats/request_gate.py', 'ats/ipc_bridge.py', 'ats/frame_merge.py',
        'ats/signal_ledger.py', 'ats/session_snapshot.py',
        'JSONData/tdx_hdf5_api.py', 'JSONData/sina_data.py',
        'ats/frame_rows.py', 'ats/ledger_guard.py', 'ats/ledger_update_service.py',
        'ats/shutdown.py', 'ats/performance.py', 'ats/tdx_realtime_fetcher.py',
        'ats/capital_dragon_engine.py', 'ats/ui/market_tasks.py',
        'ats/ui/styles.py', 'ats/ui/swing_table.py', 'ats/ui/universe_widget.py',
        'ats/ui/global_market_panel.py')]
    if Path(command[0]).name.lower() != Path(sys.executable).name.lower():
        executable = Path(command[0]).resolve()
        paths.append(executable)
        paths.extend(path for path in (executable.parent / 'sqlite3.dll',
                                      executable.parent / '_sqlite3.pyd') if path.is_file())
    result = {}
    for path in paths:
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        result[str(path)] = digest.hexdigest()
    return result


def check(command, label, timeout=120):
    before = fingerprint(command)
    output = ROOT / '.ats_validation' / ('runtime_' + label)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'config', output / 'config', dirs_exist_ok=True)
    env = dict(os.environ, INSTOCK_APP_ROOT=str(output), ATS_TEST_MODE='1',
               QT_QPA_PLATFORM='offscreen', TEMP=str(output), TMP=str(output))
    started = time.monotonic()
    descendants = {}
    timed_out = False
    peak_rss = 0
    peak_children = 0
    with (output / 'stdout.txt').open('w', encoding='utf-8') as stdout:
        child = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=stdout,
                                 stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        parent = psutil.Process(child.pid)
        while child.poll() is None:
            try:
                processes = [parent] + parent.children(recursive=True)
                peak_children = max(peak_children, len(processes) - 1)
                peak_rss = max(peak_rss, sum(process.memory_info().rss for process in processes))
                for process in processes[1:]:
                    descendants[process.pid] = process.create_time()
            except psutil.Error:
                pass
            if time.monotonic() - started >= timeout:
                timed_out = True
                for pid, created in list(descendants.items()):
                    try:
                        process = psutil.Process(pid)
                        if process.create_time() == created:
                            process.terminate()
                    except psutil.Error:
                        pass
                child.terminate()
                break
            time.sleep(.1)
        code = child.wait(timeout=5)
    leaked = []
    for pid, created in descendants.items():
        try:
            process = psutil.Process(pid)
            if process.create_time() == created and process.is_running():
                leaked.append(pid)
        except psutil.Error:
            pass
    after = fingerprint(command)
    result = dict(label=label, exit_code=code, elapsed_sec=round(time.monotonic()-started, 3),
                  timed_out=timed_out, leaked_children=leaked,
                  peak_tree_rss_bytes=peak_rss, peak_children=peak_children,
                  input_sha256=before, inputs_unchanged=before == after,
                  passed=code == 0 and not timed_out and not leaked and before == after,
                  scope='isolated offscreen startup/shutdown; no live session acceptance')
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe')
    parser.add_argument('--label', choices=['exe', 'pyinstaller', 'nuitka', 'source_launcher', 'source_alternate'])
    parser.add_argument('--entry', choices=['launcher', 'alternate'], default='launcher')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--soak-hours', type=float, default=0)
    parser.add_argument('--interval', type=float, default=60)
    args = parser.parse_args()
    command = [args.exe] if args.exe else ([sys.executable, '-X', 'utf8', '-m', 'ats.main_ats']
        if args.entry == 'alternate' else [sys.executable, '-X', 'utf8', str(ROOT/'run_ats.py')])
    label = args.label or ('exe' if args.exe else 'source_' + args.entry)
    deadline = time.monotonic() + max(0, args.soak_hours) * 3600
    rounds = []
    while True:
        result = check(command, label, args.timeout)
        rounds.append(result)
        if args.soak_hours > 0:
            report = dict(scope='isolated repeated startup/shutdown; excludes live trading and sustained GUI workload',
                          requested_hours=args.soak_hours, rounds=rounds,
                          completed=time.monotonic() >= deadline,
                          passed=all(item['passed'] for item in rounds))
            (ROOT / '.ats_validation' / ('soak_' + label + '.json')).write_text(
                json.dumps(report, indent=2), encoding='utf-8')
        if not result['passed'] or time.monotonic() >= deadline:
            break
        time.sleep(min(max(0, args.interval), max(0, deadline - time.monotonic())))
    sys.exit(0 if all(item['passed'] for item in rounds) else 1)

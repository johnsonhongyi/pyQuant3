"""Regression checks for the window-closed / console-still-running failure."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ats.shutdown import wait_for_threads


@pytest.fixture(scope='module')
def qapp():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(['shutdown-test'])


def completed_drain(errors=()):
    done = threading.Event()
    done.set()
    return SimpleNamespace(done=done, errors=list(errors))


def test_cleanup_threads_use_one_deadline():
    release = threading.Event()
    workers = [threading.Thread(target=release.wait, daemon=True) for _ in range(2)]
    for worker in workers:
        worker.start()
    try:
        assert not wait_for_threads(workers, time.monotonic() + .02)
    finally:
        release.set()
        assert wait_for_threads([None] + workers, time.monotonic() + 2)


def test_final_saves_wait_for_all_owned_process_cleanup(qapp, monkeypatch):
    from ats.ui.main_window import ATSMainWindow
    from ats.ui.sbc_launcher import SBCProcessManager
    import ats.ui.styles as styles
    from ats.bounded_evaluation_store import evaluation_store
    from PyQt6.QtCore import QTimer

    calls = []
    release = threading.Event()
    workers = [threading.Thread(target=release.wait, daemon=True) for _ in range(3)]
    for worker in workers:
        worker.start()
    monkeypatch.setattr(SBCProcessManager, 'get_instance',
                        lambda: SimpleNamespace(_close_workers=[workers[2]]))
    monkeypatch.setattr(styles, 'flush_config_writer',
                        lambda **kwargs: calls.append('config') or True)
    monkeypatch.setattr(evaluation_store, 'flush',
                        lambda **kwargs: calls.append(('archives', kwargs)) or True)
    monkeypatch.setattr(QTimer, 'singleShot', lambda *args: None)
    state = SimpleNamespace(_ipo_close_thread=workers[0], _next_day_close_thread=workers[1],
                            _retry_close_after_workers=lambda: None)
    event = SimpleNamespace(ignore=lambda: calls.append('ignored'))
    try:
        ATSMainWindow._complete_shutdown(state, event)
        assert not state._exit_cleanup_drain.done.is_set()
        assert calls == ['ignored']
    finally:
        release.set()
        assert wait_for_threads(workers, time.monotonic() + 2)
    assert state._exit_cleanup_drain.done.wait(2)
    assert not state._exit_cleanup_drain.errors
    assert calls[1] == 'config'
    assert calls[2][0] == 'archives'
    assert calls[2][1]['force'] and calls[2][1]['require_clean']
    assert not getattr(state, '_exit_cleanup_complete', False)


@pytest.mark.parametrize('outcome', ['archive', 'recovery', 'failure'])
def test_late_archive_is_durable_before_final_close(qapp, monkeypatch, tmp_path, outcome):
    from ats.ui.main_window import ATSMainWindow
    from ats.ui.sbc_launcher import SBCProcessManager
    from ats import bounded_evaluation_store as archive_cache
    from ats.storage_archive import write_json_gzip
    import ats.ui.styles as styles
    import sys_utils
    from PyQt6.QtCore import QTimer

    store = archive_cache.EvaluationStore()
    store._started = True
    path = tmp_path / 'late.json'
    value = {'code': '600000', 'saved_after_child_close': True}

    def failing_writer(*args):
        raise OSError('simulated archive failure')

    store.put(str(path), value, write_json_gzip if outcome == 'archive' else failing_writer)
    monkeypatch.setattr(archive_cache, 'evaluation_store', store)
    monkeypatch.setattr(sys_utils, 'get_app_root', lambda: str(tmp_path))
    monkeypatch.setattr(SBCProcessManager, 'get_instance', lambda: SimpleNamespace(_close_workers=[]))
    monkeypatch.setattr(styles, 'flush_config_writer', lambda **kwargs: True)
    monkeypatch.setattr(QTimer, 'singleShot', lambda *args: None)
    if outcome == 'failure':
        monkeypatch.setattr(store, 'persist_recovery', lambda *args, **kwargs: False)
    state = SimpleNamespace(_retry_close_after_workers=lambda: None)
    ATSMainWindow._complete_shutdown(state, SimpleNamespace(ignore=lambda: None))
    assert state._exit_cleanup_drain.done.wait(2)
    assert not getattr(state, '_exit_cleanup_complete', False)
    if outcome == 'failure':
        assert state._exit_cleanup_drain.errors == ['final archives: drain failed']
        assert store._cache[str(path)]['dirty']
    else:
        assert not state._exit_cleanup_drain.errors
        saved = (Path(str(path) + '.gz') if outcome == 'archive'
                 else Path(archive_cache.recovery_journal_path(tmp_path)))
        with gzip.open(saved, 'rt', encoding='utf-8') as source:
            payload = json.load(source)
        assert (payload if outcome == 'archive' else payload['entries'][0]['value']) == value


@pytest.mark.parametrize('timed_out', [False, True])
def test_failed_final_cleanup_keeps_window_and_does_not_arm_exit(qapp, monkeypatch, timed_out):
    from ats.ui.main_window import ATSMainWindow
    import ats.shutdown as shutdown
    from PyQt6.QtCore import QTimer

    calls = []
    monkeypatch.setattr(shutdown, 'start_exit_watchdog', lambda: calls.append('watchdog'))
    monkeypatch.setattr(QTimer, 'singleShot', lambda *args: calls.append('retry'))
    drain = (SimpleNamespace(done=threading.Event(), errors=[]) if timed_out
             else completed_drain(['final config: drain failed']))
    state = SimpleNamespace(_exit_cleanup_drain=drain,
                            _exit_cleanup_deadline=time.monotonic() - 1,
                            status_bar=SimpleNamespace(showMessage=lambda *args: calls.append('status')))
    ATSMainWindow._complete_shutdown(state, SimpleNamespace(ignore=lambda: calls.append('ignored')))
    assert calls == ['ignored', 'status']
    assert not getattr(state, '_exit_cleanup_complete', False)
    assert state._exit_cleanup_drain is (drain if timed_out else None)


@pytest.mark.parametrize('packaged', [False, True])
def test_watchdog_is_armed_after_drain_and_before_logger_stop(qapp, monkeypatch, packaged):
    from ats.ui.main_window import ATSMainWindow
    from PyQt6.QtWidgets import QMainWindow, QApplication
    from PyQt6.QtGui import QCloseEvent
    from JohnsonUtil import LoggerFactory
    import ats.shutdown as shutdown
    import sys_utils

    class BareWindow(ATSMainWindow):
        def __init__(self):
            QMainWindow.__init__(self)

    calls = []
    window = BareWindow()
    window._exit_cleanup_drain = completed_drain()
    monkeypatch.setattr(sys_utils, 'is_packaged_env', lambda: packaged)
    monkeypatch.setattr(shutdown, 'start_exit_watchdog', lambda: calls.append('watchdog'))

    def stop_logger():
        assert window._exit_cleanup_complete
        calls.append('logger')

    monkeypatch.setattr(LoggerFactory, 'stopLogger', stop_logger)
    monkeypatch.setattr(QMainWindow, 'closeEvent', lambda self, event: (calls.append('close'), event.accept()))
    monkeypatch.setattr(QApplication, 'quit', lambda self=None: calls.append('quit'))
    event = QCloseEvent()
    window._complete_shutdown(event)
    assert event.isAccepted()
    assert calls == (['watchdog'] if packaged else []) + ['logger', 'close', 'quit']
    window.deleteLater()


def test_close_retries_only_final_drain_after_child_windows_are_closed():
    from ats.ui.main_window import ATSMainWindow
    calls = []
    event = object()
    state = SimpleNamespace(_final_close_started=True,
                            _complete_shutdown=lambda pending: calls.append(pending))
    ATSMainWindow.closeEvent(state, event)
    assert calls == [event]


def test_idle_worker_exits_when_parent_dies_even_if_pipe_peer_stays_open(tmp_path):
    import psutil

    helper = tmp_path / 'orphan_parent.py'
    helper.write_text('''
import json
import multiprocessing
import os
from pathlib import Path
import sys
import psutil
sys.path.insert(0, sys.argv[2])

def run_worker(connection, retained_peer, root):
    from ats.next_day_watch_process import _worker_entry
    # Keeping this write handle open prevents EOF after the parent dies.
    _worker_entry(connection, root)
    retained_peer.close()
    (Path(root) / 'worker_drained.txt').write_text('drained', encoding='utf-8')

if __name__ == '__main__':
    root = Path(sys.argv[1])
    os.environ['INSTOCK_APP_ROOT'] = str(root)
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=run_worker, args=(child, parent, str(root)), daemon=True)
    process.start()
    child.close()
    metadata = {'pid': process.pid, 'created': psutil.Process(process.pid).create_time()}
    (root / 'worker.json').write_text(json.dumps(metadata), encoding='utf-8')
    parent.send({'action': 'health'})
    assert parent.poll(8)
    assert parent.recv()['pid'] == process.pid
    os._exit(0)
''', encoding='utf-8')
    metadata_path = tmp_path / 'worker.json'
    try:
        result = subprocess.run([sys.executable, str(helper), str(tmp_path),
                                 str(Path(__file__).resolve().parents[1])],
                                capture_output=True, timeout=12,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
        assert (tmp_path / 'worker_drained.txt').read_text(encoding='utf-8') == 'drained'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        try:
            worker = psutil.Process(metadata['pid'])
            if worker.create_time() == metadata['created']:
                worker.wait(timeout=3)
        except psutil.NoSuchProcess:
            pass
    finally:
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            try:
                worker = psutil.Process(metadata['pid'])
                if worker.create_time() == metadata['created']:
                    worker.kill()
                    worker.wait(timeout=3)
            except psutil.NoSuchProcess:
                pass


def _block_in_child(ready, release):
    ready.set()
    release.wait()


def test_final_cleanup_reaps_owned_daemon_worker_before_hard_exit():
    import multiprocessing
    from ats.shutdown import reap_multiprocessing_children
    context = multiprocessing.get_context('spawn')
    ready, release = context.Event(), context.Event()
    child = context.Process(target=_block_in_child, args=(ready, release), daemon=True)
    child.start()
    try:
        assert ready.wait(5)
        assert reap_multiprocessing_children(time.monotonic() + 3)
        assert not child.is_alive()
    finally:
        if child.is_alive():
            child.terminate()
            child.join(3)
        child.close()


@pytest.mark.parametrize('blocked_component', ['thread', 'executor', 'logger'])
def test_packaged_exit_finishes_even_when_teardown_is_blocked(tmp_path, blocked_component):
    source = '''
import logging
from logging.handlers import QueueListener
from concurrent.futures import ThreadPoolExecutor
import queue
import sys
import threading
from pathlib import Path
from ats.shutdown import start_exit_watchdog

release = threading.Event()
started = threading.Event()
def block():
    started.set()
    release.wait()

component = sys.argv[1]
if component == 'thread':
    threading.Thread(target=block, daemon=False).start()
elif component == 'executor':
    pool = ThreadPoolExecutor(max_workers=1)
    pool.submit(block)
    pool.shutdown(wait=False, cancel_futures=True)
else:
    class BlockedHandler(logging.Handler):
        def emit(self, record):
            block()
    records = queue.Queue()
    listener = QueueListener(records, BlockedHandler())
    listener.start()
    records.put(logging.LogRecord('test', logging.INFO, '', 0, 'exit', (), None))
assert started.wait(2)
Path(sys.argv[2]).write_text('durable cleanup complete', encoding='utf-8')
start_exit_watchdog(timeout_seconds=.2)
if component == 'logger':
    listener.stop()
'''
    saved = tmp_path / 'saved.txt'
    result = subprocess.run([sys.executable, '-c', source, blocked_component, str(saved)],
                            cwd=str(Path(__file__).resolve().parents[1]),
                            capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert saved.read_text(encoding='utf-8') == 'durable cleanup complete'


def test_is_packaged_env_detection_matrix(monkeypatch):
    import sys_utils

    # 1. 默认 python.exe 开发环境 -> False
    monkeypatch.delenv("NUITKA_ONEFILE_DIRECTORY", raising=False)
    monkeypatch.delenv("NUITKA_ONEFILE_BINARY", raising=False)
    monkeypatch.delenv("_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", "C:\\Python39\\python.exe")
    assert not sys_utils.is_packaged_env()

    # 2. PyInstaller 模式 (sys.frozen = True) -> True
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert sys_utils.is_packaged_env()
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    # 3. Nuitka Onefile 模式 (NUITKA_ONEFILE_DIRECTORY) -> True
    monkeypatch.setenv("NUITKA_ONEFILE_DIRECTORY", "C:\\Temp\\ATS_Nuitka")
    assert sys_utils.is_packaged_env()
    monkeypatch.delenv("NUITKA_ONEFILE_DIRECTORY")

    # 4. 独立二进制模式 (sys.executable 为 ATS_Terminal.exe) -> True
    monkeypatch.setattr(sys, "executable", "D:\\Release\\ATS_Terminal.exe")
    assert sys_utils.is_packaged_env()


def test_reap_multiprocessing_children_terminates_descendants_tree(tmp_path):
    """验证多进程具有子孙后代 (类似 Nuitka Onefile Bootstrap -> Payload) 时全树递归杀死."""
    import multiprocessing
    import psutil
    from ats.shutdown import reap_multiprocessing_children

    tree_script = tmp_path / "tree_worker.py"
    tree_script.write_text("""
import subprocess
import sys
import time

if __name__ == '__main__':
    # 派生孙子进程
    sub = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    with open(sys.argv[1], "w") as f:
        f.write(str(sub.pid))
    time.sleep(30)
""", encoding="utf-8")

    sub_pid_file = tmp_path / "grandchild.pid"

    context = multiprocessing.get_context("spawn")
    # 直属子进程运行 tree_script
    import subprocess
    proc = context.Process(
        target=subprocess.run,
        args=([sys.executable, str(tree_script), str(sub_pid_file)],),
        daemon=True,
    )
    proc.start()

    # 等待孙子进程 pid 写入
    deadline = time.monotonic() + 8.0
    while not sub_pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    assert sub_pid_file.exists()
    grandchild_pid = int(sub_pid_file.read_text().strip())
    assert psutil.pid_exists(grandchild_pid)

    # 执行全树递归回收
    assert reap_multiprocessing_children(time.monotonic() + 3.0)
    assert not proc.is_alive()
    # 验证孙子孤儿进程也已被递归杀死
    time.sleep(0.3)
    assert not psutil.pid_exists(grandchild_pid)


def test_packaged_shutdown_schedules_quick_physical_exit(qapp, monkeypatch):
    """验证打包环境下，退出收尾完成时安排 QTimer 物理退出 os._exit(0)."""
    from ats.ui.main_window import ATSMainWindow
    from PyQt6.QtWidgets import QMainWindow, QApplication
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtCore import QTimer
    from JohnsonUtil import LoggerFactory
    import ats.shutdown as shutdown
    import sys_utils

    class BareWindow(ATSMainWindow):
        def __init__(self):
            QMainWindow.__init__(self)

    timer_calls = []
    window = BareWindow()
    window._exit_cleanup_drain = completed_drain()
    monkeypatch.setattr(sys_utils, "is_packaged_env", lambda: True)
    monkeypatch.setattr(shutdown, "start_exit_watchdog", lambda **kwargs: None)
    monkeypatch.setattr(LoggerFactory, "stopLogger", lambda: None)
    monkeypatch.setattr(QMainWindow, "closeEvent", lambda self, event: event.accept())
    monkeypatch.setattr(QApplication, "quit", lambda self=None: None)
    monkeypatch.setattr(QTimer, "singleShot", lambda ms, cb: timer_calls.append((ms, cb)))

    event = QCloseEvent()
    window._complete_shutdown(event)
    assert event.isAccepted()
    # 验证安排了 150ms 物理退出单次定时器
    assert any(ms == 150 for ms, _ in timer_calls)
    window.deleteLater()

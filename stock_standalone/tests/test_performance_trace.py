import logging
import os
import queue

import pytest

from ats import performance_trace as trace


@pytest.fixture(autouse=True)
def stop_trace():
    trace.stop_performance_trace()
    yield
    trace.stop_performance_trace()


def test_flag_enables_persistent_log_and_preserves_other_arguments(tmp_path):
    args = ['ATS_Terminal.exe', '--perf-log', '-log', 'WARN']
    path = trace.configure_performance_trace(str(tmp_path), args, {})
    assert args == ['ATS_Terminal.exe', '-log', 'WARN']
    assert path.endswith('ats_perf_{}.log'.format(os.getpid()))
    trace.perf_logger.debug('[FusionPerf] sort_ms=12.5 data_age_ms=30')
    trace.stop_performance_trace()
    content = open(path, encoding='utf-8').read()
    assert 'sort_ms=12.5 data_age_ms=30' in content
    assert 'dropped_records=0' in content
    assert trace.perf_logger.disabled


def test_disabled_does_not_create_file(tmp_path):
    args = ['ATS_Terminal.exe']
    assert trace.configure_performance_trace(str(tmp_path), args, {}) is None
    assert list(tmp_path.iterdir()) == []
    assert trace.perf_logger.disabled


def test_environment_flag_is_supported(tmp_path):
    args = ['ATS_Terminal.exe']
    path = trace.configure_performance_trace(str(tmp_path), args, {'FUSION_PERF_TRACE': '1'})
    assert path is not None
    trace.stop_performance_trace()
    assert os.path.exists(path)


def test_full_queue_drops_instead_of_blocking():
    records = queue.Queue(maxsize=1)
    handler = trace._DroppingQueueHandler(records)
    handler.enqueue(logging.LogRecord('x', logging.INFO, '', 0, 'first', (), None))
    handler.enqueue(logging.LogRecord('x', logging.INFO, '', 0, 'second', (), None))
    assert records.qsize() == 1
    assert handler.dropped == 1


def test_rotation_limits_each_process_file(tmp_path):
    path = trace.configure_performance_trace(str(tmp_path), ['ATS_Terminal.exe', '--perf-log'], {})
    output = trace._listener.handlers[0]
    output.maxBytes = 160
    output.backupCount = 2
    for i in range(30):
        trace.perf_logger.info('[FusionPerf] measurement %s %s', i, 'x' * 40)
    trace.stop_performance_trace()
    files = list((tmp_path / 'logs' / 'performance').glob('ats_perf_*.log*'))
    assert 1 <= len(files) <= 3
    assert os.path.exists(path)


def test_qt_event_latency_records_to_dedicated_log(tmp_path):
    import time
    from types import SimpleNamespace
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    path = trace.configure_performance_trace(str(tmp_path), ['ATS_Terminal.exe', '--perf-log'], {})
    dialog = SimpleNamespace(isVisible=lambda: True, isMinimized=lambda: False,
        _ui_probe_expected=time.monotonic() - .02, _ui_probe_samples=[1.] * 99)
    FusionLadderDialog._record_ui_event_lag(dialog)
    trace.stop_performance_trace()
    with open(path, encoding='utf-8') as stream:
        content = stream.read()
    assert 'ui_event_lag_ms p95=' in content
    assert 'samples=100' in content
    assert dialog._ui_probe_samples == []


def test_unwritable_destination_disables_trace(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise PermissionError('isolated failure')
    monkeypatch.setattr(trace.os, 'makedirs', fail)
    assert trace.configure_performance_trace(str(tmp_path), ['ATS_Terminal.exe', '--perf-log'], {}) is None
    assert trace.perf_logger.disabled


def test_run_ats_main_enables_and_flushes_log(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import sys
    import run_ats
    import sys_utils
    import ats.bounded_evaluation_store as archive
    import ats.qt_interrupt as interrupt
    import ats.ui.styles as styles

    captured = {}
    class App:
        def __init__(self, args):
            captured['qt_args'] = list(args)
            self.aboutToQuit = SimpleNamespace(connect=lambda callback: None)
        def exec(self):
            trace.perf_logger.debug('[FusionPerf] actual_run_ats_entry=1')
            return 0
    class Window:
        _ipo_learning_console_enabled = False
        _exit_cleanup_complete = True
        def windowTitle(self): return 'test'
        def show(self): pass

    monkeypatch.setattr(sys, 'argv', ['run_ats.py', '--perf-log', '-log', 'WARN'])
    monkeypatch.setattr(run_ats, 'current_dir', str(tmp_path))
    monkeypatch.setattr(run_ats, 'QApplication', App)
    monkeypatch.setattr(run_ats, 'ATSMainWindow', Window)
    monkeypatch.setattr(run_ats, 'is_packaged_env', lambda: False)
    monkeypatch.setattr(run_ats, 'ensure_backend_tk_running', lambda: None)
    monkeypatch.setattr(sys_utils, 'ensure_all_configs_released', lambda: None)
    monkeypatch.setattr(archive.evaluation_store, 'restore_recovery', lambda path: False)
    monkeypatch.setattr(styles, 'apply_dark_tooltip_palette', lambda app: None)
    monkeypatch.setattr(interrupt, 'install_qt_keyboard_interrupt_handler', lambda app, window: None)
    monkeypatch.delenv('ATS_TEST_MODE', raising=False)
    assert run_ats.main() == 0
    assert captured['qt_args'] == ['run_ats.py', '-log', 'WARN']
    path = tmp_path / 'logs' / 'performance' / ('ats_perf_{}.log'.format(os.getpid()))
    assert 'actual_run_ats_entry=1' in path.read_text(encoding='utf-8')


def test_concurrent_producers_flush_without_losing_records(tmp_path):
    import threading
    path = trace.configure_performance_trace(str(tmp_path), ['ATS_Terminal.exe', '--perf-log'], {})
    def produce(worker):
        for index in range(40):
            trace.perf_logger.info('[FusionPerf] worker=%d index=%d', worker, index)
    threads = [threading.Thread(target=produce, args=(worker,)) for worker in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    trace.stop_performance_trace()
    with open(path, encoding='utf-8') as stream:
        lines = stream.readlines()
    records = [line for line in lines if ' worker=' in line]
    assert len(records) == 160
    assert len(set(records)) == 160

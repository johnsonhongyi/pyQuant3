"""Exercise Qt scheduling and Windows-spawn acquisition without live data or orders."""

import os
import threading
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ats.ui import ipo_learning_console as console_module


def _cpu_cycle(self):
    deadline = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        sum(range(5000))
    return {"status": "READY", "pid": os.getpid(), "payload": "x" * 1024 * 1024}


def _spawn_cpu_cycle(root, ticker, labels, channel):
    from ats.ui import ipo_learning_console as child_module
    child_module._SourceAcquisitionWorker._run_cycle = _cpu_cycle
    child_module._source_acquisition_process(root, ticker, labels, channel)


def _spawn_crash(root, ticker, labels, channel):
    os._exit(7)


def _spawn_blocked(root, ticker, labels, channel):
    Path(root, "child.ready").write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(30)


def _spawn_pipeline_cycle(root, ticker, labels, channel):
    from types import SimpleNamespace
    from tools import run_ipo_data_acquisition as acquisition
    from ats.strategy import ipo_gate_context_provider as provider
    from ats.ui import ipo_learning_console as child_module
    def cycle(code, **kwargs):
        kwargs["progress_callback"]({"stage": "ATS_TABLE", "status": "DONE"})
        return {
            "ticker": code, "status": "HISTORICAL", "ready_count": 3, "required_count": 41,
            "source_collection": {"status": "STATIC_ONLY", "mode": "STATIC_HISTORICAL"},
            "historical_analysis": {"status": "NO_HISTORY", "emotion_score": 50.0},
        }
    acquisition.run_ats_learning_cycle = cycle
    provider.get_default_ipo_gate_context_provider = lambda root: SimpleNamespace(
        refresh=lambda: False, status_snapshot=lambda: {"state": "UNREADY"},
    )
    child_module._source_acquisition_process(root, ticker, labels, channel)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def console(app, tmp_path, monkeypatch):
    monkeypatch.setattr(console_module._LearningMonitorWorker, "start", lambda self: None)
    monkeypatch.setattr(console_module._LearningMonitorWorker, "request_refresh", lambda self: None)
    widget = console_module.IPOLearningConsole(project_root=str(tmp_path), simulation_read_only=True)
    yield widget
    widget.stop_monitor()
    widget.close()
    app.processEvents()


def _wait_until(predicate, timeout_ms=12000):
    deadline = time.monotonic() + timeout_ms / 1000
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), "background work did not finish before the test deadline"


@pytest.mark.parametrize("now, delay", [
    (datetime(2026, 9, 30, 10, 0), 300000),
    (datetime(2026, 9, 30, 12, 0), 300000),
    (datetime(2026, 9, 30, 8, 54), 60000),
    (datetime(2026, 9, 30, 20, 55), 12 * 3600000),
    (datetime(2026, 10, 3, 8, 55), 48 * 3600000),
])
def test_schedule_has_no_two_second_off_session_drain(now, delay):
    assert console_module._source_auto_interval_ms(now) == delay


def test_cold_read_is_once_and_busy_ticks_do_not_catch_up(console, monkeypatch):
    console._simulation_read_only = False
    console._source_auto_timer = QTimer(console)
    calls = []
    monkeypatch.setattr(console_module, "_source_auto_interval_ms", lambda: 3600000)
    monkeypatch.setattr(console_module, "_source_poll_window_active", lambda: False)
    monkeypatch.setattr(console, "_start_source_collection", lambda **kw: calls.append(kw))
    # No filesystem/calendar reads are permitted in this UI timer callback.
    monkeypatch.setattr(console_module, "_read_json", lambda *a, **kw: pytest.fail("UI disk read"))
    monkeypatch.setattr(console_module, "_is_market_session_active", lambda: pytest.fail("UI calendar read"))
    console._on_source_auto_tick()
    console._on_source_auto_tick()
    assert len(calls) == 1
    monkeypatch.setattr(console_module, "_source_auto_interval_ms", lambda: 300000)
    monkeypatch.setattr(console_module, "_source_poll_window_active", lambda: True)
    worker = type("BusyWorker", (), {"isRunning": lambda self: True})()
    console._source_worker = worker
    console._on_source_auto_tick()
    console._source_collection_worker_finished(worker)
    QTest.qWait(150)
    assert len(calls) == 1
    assert console._source_worker is None


def test_preopen_is_not_a_repeat_window(console, monkeypatch):
    console._simulation_read_only = False
    console._cold_source_read_pending = False
    console._source_auto_timer = QTimer(console)
    monkeypatch.setattr(console_module, "_source_auto_interval_ms", lambda: 60000)
    monkeypatch.setattr(console_module, "_source_poll_window_active", lambda: False)
    monkeypatch.setattr(console, "_start_source_collection", lambda **kw: pytest.fail("preopen repeat"))
    console._on_source_auto_tick()
    assert console._source_auto_timer.interval() == 60000


def test_refresh_preserves_unchanged_table_items_and_updates_changed_data(console):
    snapshot = {
        "events": [{"timestamp": "t", "event": "BLOCK", "ticker": "301716"}],
        "contracts": [{"field_id": "price", "value": "1"}],
        "acquisition_queue": {"items": [{"ticker": "301716"}], "cursor": 0},
    }
    console._render_snapshot(snapshot)
    event_item = console.event_table.item(0, 0)
    contract_item = console.contract_table.item(0, 2)
    queue_item = console.acquisition_queue_table.item(0, 1)
    console._render_snapshot({**snapshot, "monitor_updated_at": "new heartbeat"})
    assert console.event_table.item(0, 0) is event_item
    assert console.contract_table.item(0, 2) is contract_item
    assert console.acquisition_queue_table.item(0, 1) is queue_item
    snapshot["contracts"][0]["value"] = "2"
    console._render_snapshot(snapshot)
    assert console.contract_table.item(0, 2).text() == "2"
    assert console.event_table.item(0, 0) is event_item


def test_snapshot_details_use_background_reader_and_ignore_old_selection(console, monkeypatch):
    from ats.llm import learning_snapshot_store
    reader_threads = []
    main_thread = threading.get_ident()
    def load(root, snapshot_id):
        reader_threads.append(threading.get_ident())
        time.sleep(0.1)
        return {"ticker": "301716", "snapshot_id": snapshot_id, "input_snapshot": {}}
    monkeypatch.setattr(learning_snapshot_store, "get_snapshot_record", load)
    monkeypatch.setattr(console_module, "_collect_snapshot", lambda root: {})
    console._worker._snapshot_pending.set()
    QThread.start(console._worker)
    first, second = "a" * 64, "b" * 64
    console._render_learning_snapshots([{"snapshot_id": first}, {"snapshot_id": second}])
    console.snapshot_table.selectRow(1)
    ticks = []
    timer = QTimer(console)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(10)
    _wait_until(lambda: "301716" in console.snapshot_detail.toPlainText())
    timer.stop()
    assert console._selected_snapshot_id == second
    assert reader_threads and all(value != main_thread for value in reader_threads)
    assert len(ticks) >= 5
    console._show_snapshot_detail(first, {"ticker": "WRONG"})
    assert "WRONG" not in console.snapshot_detail.toPlainText()


def test_monitor_coalesces_clicks_and_waits_for_ui_ack(app, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(console_module, "_is_market_session_active", lambda: True)
    monkeypatch.setattr(console_module, "_collect_snapshot", lambda root: calls.append(1) or {})
    worker = console_module._LearningMonitorWorker(tmp_path)
    worker._interval = 0.02
    for _ in range(100):
        worker.request_refresh()
    assert worker._commands.qsize() == 1
    worker.start()
    try:
        _wait_until(lambda: len(calls) == 1)
        QTest.qWait(100)
        assert len(calls) == 1
        worker.snapshot_consumed()
        _wait_until(lambda: len(calls) == 2)
    finally:
        worker.stop()
        assert worker.wait(1500)


def test_monitor_survives_collection_error(app, tmp_path, monkeypatch):
    calls, errors, snapshots = [], [], []
    def collect(root):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("file is temporarily locked")
        return {"runtime_status": "recovered"}
    monkeypatch.setattr(console_module, "_is_market_session_active", lambda: True)
    monkeypatch.setattr(console_module, "_collect_snapshot", collect)
    worker = console_module._LearningMonitorWorker(tmp_path)
    worker._interval = 0.02
    worker.monitor_failed.connect(errors.append)
    worker.snapshot_ready.connect(snapshots.append)
    worker.start()
    worker.request_refresh()
    try:
        _wait_until(lambda: bool(snapshots))
        assert errors and snapshots[0]["runtime_status"] == "recovered"
        assert worker.isRunning()
    finally:
        worker.stop()
        assert worker.wait(1500)


def test_spawn_cycle_keeps_qt_responsive_and_drains_large_result(app, tmp_path, monkeypatch):
    monkeypatch.setattr(console_module, "_source_acquisition_process", _spawn_cpu_cycle)
    worker = console_module._SourceAcquisitionWorker(tmp_path, "301716")
    results, ticks = [], []
    worker.completed.connect(results.append)
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(10)
    worker.start()
    try:
        _wait_until(lambda: bool(results))
        assert worker.wait(1500)
        assert results[0]["pid"] != os.getpid()
        assert len(results[0]["payload"]) == 1024 * 1024
        assert len(ticks) > 10
        assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.35
    finally:
        timer.stop()
        worker.stop()
        assert worker.wait(2500)


def test_spawn_pipeline_delivers_status_and_releases_ui_worker(console, monkeypatch):
    monkeypatch.setattr(console_module, "_source_acquisition_process", _spawn_pipeline_cycle)
    console._simulation_read_only = False
    console.edt_acquisition_code.setText("301716")
    console._start_source_collection(collect_labels=False)
    _wait_until(lambda: console._source_worker is None)
    state = console_module._read_json(
        console._root / "data" / "ipo_learning" / "acquisition_queue.latest.json",
    )
    assert state["active"]["stage"] == "COMPLETED"
    assert state["active"]["ticker"] == "301716"
    assert "3/41" in console.lbl_acquisition_status.text()
    assert console.btn_collect_labels.isEnabled()


def test_spawn_crash_degrades_without_stopping_ui(app, tmp_path, monkeypatch):
    monkeypatch.setattr(console_module, "_source_acquisition_process", _spawn_crash)
    worker = console_module._SourceAcquisitionWorker(tmp_path, "301716")
    results = []
    worker.completed.connect(results.append)
    worker.start()
    try:
        _wait_until(lambda: bool(results))
        assert worker.wait(1500)
        assert results[0]["status"] == "UNREADY"
        assert results[0]["reason"]
    finally:
        worker.stop()
        assert worker.wait(2500)


def test_close_stops_blocked_spawn_without_late_completion(app, tmp_path, monkeypatch):
    monkeypatch.setattr(console_module, "_source_acquisition_process", _spawn_blocked)
    worker = console_module._SourceAcquisitionWorker(tmp_path, "301716")
    results = []
    worker.completed.connect(results.append)
    worker.start()
    try:
        _wait_until(lambda: (tmp_path / "child.ready").is_file())
        start = time.monotonic()
        worker.stop()
        assert worker.wait(2000)
        assert time.monotonic() - start < 2
        app.processEvents()
        assert not results
    finally:
        worker.stop()
        assert worker.wait(2500)

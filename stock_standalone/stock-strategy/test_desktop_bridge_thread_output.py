import io
import sys
import threading

from desktop_bridge_thread_output import routed_thread_output


def _write_streams(stdout_text, stderr_text, failures):
    try:
        sys.stdout.write(stdout_text)
        sys.stderr.write(stderr_text)
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as exc:
        failures.append(exc)


def _run_bridge_route(output, prefix, label, started, release, finished, failures):
    try:
        with routed_thread_output(output, prefix):
            _write_streams(f"{label} stdout\n", f"{label} stderr\n", failures)
            started.set()
            if release is not None:
                release.wait(2)
    except Exception as exc:
        failures.append(exc)
    finally:
        finished.set()


def test_parallel_bridge_routes_isolate_logs_and_late_writes_fall_back(monkeypatch):
    fallback_stdout = io.StringIO()
    fallback_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fallback_stdout)
    monkeypatch.setattr(sys, "stderr", fallback_stderr)

    codex_output = io.BytesIO()
    agv_output = io.BytesIO()
    failures = []
    codex_ready = threading.Event()
    release_codex = threading.Event()
    codex_done = threading.Event()
    agv_done = threading.Event()
    codex_thread = threading.Thread(
        target=_run_bridge_route,
        args=(codex_output, "stock-codex-", "codex", codex_ready, release_codex, codex_done, failures),
        name="stock-codex-manager-thread",
    )
    agv_thread = threading.Thread(
        target=_run_bridge_route,
        args=(agv_output, "stock-agv-", "agv", threading.Event(), None, agv_done, failures),
        name="stock-agv-manager-thread",
    )
    late_thread = None
    try:
        codex_thread.start()
        assert codex_ready.wait(2)
        agv_thread.start()
        assert agv_done.wait(2)
        agv_log = agv_output.getvalue()
        agv_output.close()
        late_thread = threading.Thread(
            target=_write_streams,
            args=("late agv stdout\n", "late agv stderr\n", failures),
            name="stock-agv-late-thread",
        )
        late_thread.start()
        late_thread.join(2)
    finally:
        release_codex.set()
        for thread in (codex_thread, agv_thread, late_thread):
            if thread is not None and thread.ident is not None:
                thread.join(2)

    assert codex_done.is_set()
    assert agv_done.is_set()
    assert failures == []
    assert codex_output.getvalue() == b"codex stdout\ncodex stderr\n"
    assert agv_log == b"agv stdout\nagv stderr\n"
    assert fallback_stdout.getvalue() == "late agv stdout\n"
    assert fallback_stderr.getvalue() == "late agv stderr\n"
    assert sys.stdout is fallback_stdout
    assert sys.stderr is fallback_stderr

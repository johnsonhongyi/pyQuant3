import os
import threading
import time
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_favorite_action_is_background_and_completion_returns_to_qt_thread(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ats.ui.base_table import BaseATSTableWidget
    from ats.ui.favorite_actions import submit_favorite_action
    from global_favorites import GlobalFavoriteManager

    app = QApplication.instance() or QApplication(["favorite-action-contract"])
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    ui_thread = threading.get_ident()
    completion_threads = []
    fake_manager = object.__new__(GlobalFavoriteManager)
    monkeypatch.setattr(GlobalFavoriteManager, "_instance", fake_manager)

    def blocked_toggle(_manager, _code):
        entered.set()
        assert release.wait(2)
        return {"status": "added", "persisted": True, "favorites_revision": 1}

    monkeypatch.setattr(GlobalFavoriteManager, "toggle_favorite_stock_result", blocked_toggle)
    window = QMainWindow()
    table = BaseATSTableWidget(window)

    def on_complete(_owner, result, error):
        completion_threads.append(threading.get_ident())
        assert error is None
        assert result["status"] == "added"
        completed.set()

    future = submit_favorite_action(
        table, "toggle_favorite_stock_result", "600000", on_complete=on_complete
    )
    assert entered.wait(1)
    assert not future.done()

    release.set()
    assert future.result(timeout=2)["persisted"] is True
    deadline = time.monotonic() + 2
    while not completed.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert completed.is_set()
    assert completion_threads == [ui_thread]

    failed_completion = threading.Event()
    failure_threads = []

    def failed_toggle(_manager, _code):
        raise OSError("disk_write_failed")

    monkeypatch.setattr(GlobalFavoriteManager, "toggle_favorite_stock_result", failed_toggle)
    failed = submit_favorite_action(
        table, "toggle_favorite_stock_result", "600001",
        on_complete=lambda _owner, _result, error: (
            failure_threads.append(threading.get_ident()),
            failed_completion.set() if isinstance(error, OSError) else None,
        ),
    )
    with pytest.raises(OSError, match="disk_write_failed"):
        failed.result(timeout=2)
    deadline = time.monotonic() + 2
    while not failed_completion.is_set() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert failed_completion.is_set()
    assert failure_threads == [ui_thread]
    assert "disk_write_failed" in window.statusBar().currentMessage()
    table.close()
    window.close()


def test_base_table_toggle_returns_while_favorite_store_is_blocked(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ats.ui.base_table import BaseATSTableWidget
    from global_favorites import GlobalFavoriteManager

    app = QApplication.instance() or QApplication(["base-table-favorite-contract"])
    entered = threading.Event()
    release = threading.Event()
    fake_manager = object.__new__(GlobalFavoriteManager)
    monkeypatch.setattr(GlobalFavoriteManager, "_instance", fake_manager)

    def blocked_toggle(_manager, _code):
        entered.set()
        assert release.wait(2)
        return {"status": "added", "persisted": True, "favorites_revision": 1}

    monkeypatch.setattr(GlobalFavoriteManager, "toggle_favorite_stock_result", blocked_toggle)
    window = QMainWindow()
    table = BaseATSTableWidget(window)

    release_timer = threading.Timer(1.0, release.set)
    release_timer.daemon = True
    release_timer.start()
    started = time.monotonic()
    table._toggle_favorite("600000")
    elapsed = time.monotonic() - started
    assert elapsed < 0.25
    assert entered.wait(1)
    release.set()
    release_timer.cancel()
    deadline = time.monotonic() + 2
    while "重点关注已保存" not in window.statusBar().currentMessage() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert "重点关注已保存" in window.statusBar().currentMessage()
    table.close()
    window.close()


@pytest.mark.parametrize("filename", ["minute_kline_viewer_qt.py", "signal_dashboard_panel.py"])
def test_qaction_checked_flag_never_replaces_favorite_identity(filename):
    import ast
    from pathlib import Path
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    tree = ast.parse((Path(__file__).resolve().parents[1] / filename).read_text(encoding="utf-8"))
    callbacks = [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)
                 and isinstance(node.body, ast.Call)
                 and isinstance(node.body.func, ast.Name)
                 and node.body.func.id == "submit_favorite_action"]
    assert len(callbacks) >= 2
    for node in callbacks:
        calls = []
        env = {"self": object(), "code": "600000", "sector": "test-sector",
               "submit_favorite_action": lambda *args, **kwargs: calls.append(args)}
        callback = eval(compile(ast.Expression(node), filename, "eval"), env)
        action = QAction("test", None)
        action.triggered.connect(callback)
        action.trigger()
        assert len(calls) == 1
        method, identity = calls[0][1:3]
        assert identity == ("test-sector" if "sector" in method else "600000")

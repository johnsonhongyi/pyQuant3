import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from ats.llm import ipo_codex_chat as chat
from ats.llm.cli_process import BoundedCLIError, run_bounded_cli


@pytest.fixture(scope="module")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def seed(root):
    with sqlite3.connect(root / "trading_signals.db") as db:
        db.execute("CREATE TABLE signal_history(date,code,price,action,secret)")
        db.execute("INSERT INTO signal_history VALUES('2026-10-13','600000',10,'买入','never-send-secret')")
    state = root / "data/ipo_learning/paper_auto/state/paper_account_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"initial_capital": 10000, "cash": 9000,
        "positions": {"600000": {"entry_price": 10, "volume": 100, "current_price": 11}},
        "orders": [{"order_id": "buy", "code": "600000", "action": "BUY", "price": 10, "volume": 100,
                    "fee": 0, "timestamp": "2026-10-13T10:00:00"}]}), encoding="utf-8")
    return state


def test_context_is_readonly_and_excludes_unselected_columns(tmp_path):
    seed(tmp_path)
    db_path = tmp_path / "trading_signals.db"
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    evidence, digest = chat.collect_context(tmp_path, "600000")
    assert "never-send-secret" not in json.dumps(evidence)
    assert evidence["sources"]["paper_account"]["reconciliation_issues"] == []
    assert evidence["sources"]["signal_history"]["freshness"] == "DATE_ONLY_NOT_REALTIME"
    assert len(digest) == 64
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before


def test_position_mismatch_is_reported(tmp_path):
    state = seed(tmp_path)
    document = json.loads(state.read_text())
    document["positions"]["600000"]["volume"] = 200
    state.write_text(json.dumps(document), encoding="utf-8")
    evidence, _ = chat.collect_context(tmp_path)
    assert "POSITION_QTY_MISMATCH:600000" in evidence["sources"]["paper_account"]["reconciliation_issues"]


def test_cli_uses_authenticated_exec_and_saves_auditable_conversation(tmp_path, monkeypatch):
    seed(tmp_path)
    monkeypatch.setattr(chat, "resolve_cli_path", lambda *a: "codex.exe")
    seen = []
    def run(command, **kwargs):
        assert command[:2] == ["codex.exe", "exec"]
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "--ignore-user-config" in command
        assert 'model_reasoning_effort="medium"' in command
        assert kwargs["timeout_limit_seconds"] == 180
        payload = kwargs["stdin_bytes"].decode("utf-8")
        assert "never-send-secret" not in payload
        seen.append(payload)
        Path(command[command.index("--output-last-message") + 1]).write_text("模拟现金和持仓核对一致。", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr=b"")
    monkeypatch.setattr(chat, "run_bounded_cli", run)
    result = chat.ask_codex(tmp_path, "session-1", "审核账户")
    assert result["answer"] == "模拟现金和持仓核对一致。"
    chat.ask_codex(tmp_path, "session-1", "解释上一条")
    assert '"history": [{"question": "审核账户"' in seen[-1]
    assert len(chat.load_history(tmp_path, "session-1")) == 2
    assert chat.load_history(tmp_path, "other-session") == []
    assert chat.latest_dialogue(tmp_path)["session"] == "session-1"
    assert len(chat.latest_dialogue(tmp_path)["history"]) == 2
    records = chat.list_analyses(tmp_path)
    restored = chat.latest_dialogue(tmp_path, records[-1]["id"])
    assert len(restored["history"]) == 1
    assert restored["history"][0]["question"] == "审核账户"


def test_missing_data_remains_explicit(tmp_path):
    evidence, _ = chat.collect_context(tmp_path)
    assert evidence["sources"]["signal_history"]["state"] == "UNAVAILABLE"
    assert evidence["sources"]["paper_account"]["state"] == "MISSING"


def test_existing_runner_timeout_contract_stays_closed(tmp_path):
    import sys
    with pytest.raises(BoundedCLIError, match="CLI_TIMEOUT_INVALID"):
        run_bounded_cli([sys.executable, "-V"], cwd=tmp_path, stdin_bytes=b"", timeout_seconds=31)


def test_cancellation_terminates_cli_process(tmp_path):
    import sys
    event = threading.Event()
    event.set()
    with pytest.raises(BoundedCLIError, match="CLI_CANCELLED"):
        run_bounded_cli([sys.executable, "-c", "import time; time.sleep(20)"], cwd=tmp_path,
                        stdin_bytes=b"", timeout_seconds=10, cancel_event=event)


def test_desktop_codex_detected_when_not_on_path(tmp_path, monkeypatch):
    from ats.llm import cli_paths
    executable = tmp_path / "Programs/OpenAI/Codex/bin/codex.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture; never execute")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(cli_paths.shutil, "which", lambda name: None)
    assert cli_paths.resolve_cli_path("codex", "codex") == str(executable)


def test_dialogue_send_runs_in_background_and_renders_answer(tmp_path, monkeypatch, qt_app):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from ats.ui import ipo_codex_dialogue as ui
    app = QApplication.instance() or QApplication([])
    main_thread = threading.get_ident()
    def respond(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return {"answer": "模拟账本核对一致", "context": {"mode": "PAPER_ONLY"}, "context_hash": "a" * 64}
    monkeypatch.setattr(ui, "ask_codex", respond)
    panel = ui.CodexIPODialogue(tmp_path)
    panel.question.setPlainText("对账")
    panel.send.click()
    for _ in range(200):
        app.processEvents()
        if panel.worker is None:
            break
        QTest.qWait(10)
    assert panel.worker is None
    assert "模拟账本核对一致" in panel.transcript.toPlainText()
    assert panel.question.toPlainText() == "对账"
    assert panel.send.isEnabled()
    panel.shutdown()
    panel.close()


def test_code_paste_auto_preview_and_enter(tmp_path, monkeypatch, qt_app):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtTest import QTest
    from ats.ui import ipo_codex_dialogue as ui
    app = QApplication.instance() or QApplication([])
    seen = []
    def collect(root, ticker):
        seen.append(ticker)
        return {"ticker": ticker}, "a" * 64
    monkeypatch.setattr(ui, "collect_context", collect)
    panel = ui.CodexIPODialogue(tmp_path)
    app.clipboard().setText("920885")
    monkeypatch.setattr(ui.QApplication, "clipboard", staticmethod(lambda: SimpleNamespace(text=lambda: "920885")))
    monkeypatch.setattr(panel.ticker, "createStandardContextMenu",
                        lambda: pytest.fail("有效代码右键必须直接粘贴，不打开菜单"))
    panel.ticker.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1)))
    assert panel.ticker.text() == "920885"
    for _ in range(100):
        QTest.qWait(10)
        if "920885" in seen and panel.worker is None:
            break
    assert "920885" in seen
    count = len(seen)
    QTest.keyClick(panel.ticker, Qt.Key.Key_Return)
    for _ in range(100):
        QTest.qWait(10)
        if len(seen) > count and panel.worker is None:
            break
    assert len(seen) > count
    panel.shutdown()
    panel.close()


@pytest.mark.parametrize("clipboard", ["920885", " BJ920885 ", "920885.BJ"])
def test_right_click_replaces_existing_code_and_refreshes(clipboard, qt_app, monkeypatch):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QContextMenuEvent
    from ats.ui.ipo_codex_dialogue import _CodeEdit, QApplication
    editor = _CodeEdit("600000")
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: SimpleNamespace(text=lambda: clipboard)))
    monkeypatch.setattr(editor, "createStandardContextMenu", lambda: pytest.fail("不应弹出菜单"))
    refreshed = []
    editor.returnPressed.connect(lambda: refreshed.append(editor.text()))
    editor.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1)))
    assert editor.text() == "920885"
    assert refreshed == ["920885"]
    editor.close()


def test_restore_labels_roles_and_renders_markdown(tmp_path, qt_app):
    from PyQt6.QtWidgets import QApplication
    from ats.ui.ipo_codex_dialogue import CodexIPODialogue
    app = QApplication.instance() or QApplication([])
    panel = CodexIPODialogue(tmp_path)
    panel._result({"context": {}, "context_hash": "a" * 64, "session": "restored-1",
                   "history": [{"question": "核对数量", "answer": "**核对一致**"}]})
    text = panel.transcript.toPlainText()
    assert "已恢复历史对话" in text
    assert "第 1 轮 · 你" in text and "第 1 轮 · Codex" in text
    assert "**" not in text
    content = panel.transcript.toHtml()
    assert "#e0f2fe" in content and "#ecfdf5" in content
    panel.shutdown()
    panel.close()


def test_windows_cli_does_not_create_console(tmp_path, monkeypatch):
    import os, sys, subprocess
    import ats.llm.cli_process as runner
    if os.name != "nt":
        pytest.skip("Windows-specific creation flags")
    original = subprocess.Popen
    flags = []
    def launch(*args, **kwargs):
        flags.append(kwargs.get("creationflags", 0))
        return original(*args, **kwargs)
    monkeypatch.setattr(runner.subprocess, "Popen", launch)
    run_bounded_cli([sys.executable, "-c", "print('ready')"], cwd=tmp_path, stdin_bytes=b"", timeout_seconds=5)
    assert flags[0] & subprocess.CREATE_NO_WINDOW


def test_name_cache_and_model_supported_efforts(tmp_path, monkeypatch):
    cache = tmp_path / "datacsv/stock_name_cache.json"
    cache.parent.mkdir()
    cache.write_text(json.dumps({"920885": "测试证券"}), encoding="utf-8")
    assert chat.security_name(tmp_path, "920885") == "测试证券"
    assert chat.security_name(tmp_path, "") == "全局分析"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-6-luna", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]}
    ]}), encoding="utf-8")
    choices = chat.model_choices()
    assert choices[0]["model"] == "gpt-6.1-sol"
    assert next(row for row in choices if row["model"] == "gpt-6-luna")["levels"] == ["low", "high"]


def test_current_models_include_61_and_hide_56(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(json.dumps({"models": [
        {"slug": "gpt-5.6-sol", "supported_reasoning_levels": [{"effort": "high"}]}
    ]}), encoding="utf-8")
    names = [row["model"] for row in chat.model_choices()]
    assert names[0] == "gpt-6.1-sol"
    assert not any("5.6" in name for name in names)
    assert "gpt-6-sol" not in names


def test_model_effort_selector_only_offers_supported_levels(tmp_path, qt_app):
    from ats.ui.ipo_codex_dialogue import CodexIPODialogue
    panel = CodexIPODialogue(tmp_path)
    panel._model_options = [{"model": "gpt-6-luna", "levels": ["low", "high"]}]
    panel._update_effort()
    assert [panel.effort.itemData(i) for i in range(panel.effort.count())] == ["low", "high"]
    panel.shutdown()
    panel.close()


@pytest.mark.parametrize("width", [640, 900, 1280])
def test_layout_wraps_and_long_history_does_not_expand_window(width, tmp_path, qt_app):
    from ats.ui.ipo_codex_dialogue import CodexIPODialogue
    panel = CodexIPODialogue(tmp_path)
    panel.analysis_history.addItem("920885 证券名称 " + "很长的历史分析标题" * 60)
    panel.resize(width, 800)
    panel.show()
    qt_app.processEvents()
    assert panel.width() == width
    for widget in (panel.ticker, panel.analysis_history, panel.model, panel.effort,
                   panel.send, panel.restore, panel.stop):
        assert widget.geometry().right() < width
    panel._toggle_evidence()
    assert panel.evidence.isHidden()
    panel._toggle_evidence()
    assert not panel.evidence.isHidden()
    panel.shutdown()
    panel.close()


def test_flow_preserves_ignored_label_width_and_wrapped_height(qt_app):
    from PyQt6.QtWidgets import QWidget, QLabel, QSizePolicy
    from ats.ui.responsive_flow import ResponsiveFlow
    panel = QWidget()
    flow = ResponsiveFlow(panel)
    labels = []
    for _ in range(5):
        label = QLabel("监控状态：" + "正常运行与审核分析" * 8)
        label.setWordWrap(True)
        label.setMaximumWidth(300)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        flow.addWidget(label)
        labels.append(label)
    panel.resize(400, 800)
    panel.show()
    qt_app.processEvents()
    for label in labels:
        assert label.width() > 100
        assert label.height() >= label.heightForWidth(label.width())
        assert label.geometry().right() < panel.width()
    assert labels[-1].y() > labels[0].y()
    panel.close()


def test_standalone_queue_linkage_and_nonblocking_close(tmp_path, qt_app, monkeypatch):
    import time
    from PyQt6.QtWidgets import QTableWidgetItem
    from PyQt6.QtGui import QCloseEvent
    from ats.ui import ipo_learning_console as ui
    from tools import run_ipo_learning_console as launcher
    monkeypatch.setattr(ui._LearningMonitorWorker, "start", lambda self: None)
    monkeypatch.setattr(ui._LearningMonitorWorker, "request_refresh", lambda self: None)
    monkeypatch.setattr(launcher.threading.Thread, "start", lambda self: None)
    window = launcher.StandaloneLearningWindow(project_root=tmp_path, simulation_read_only=True)
    table = window.console.acquisition_queue_table
    table.setRowCount(1)
    table.setItem(0, 1, QTableWidgetItem("301716"))
    table.setItem(0, 2, QTableWidgetItem("鸿富瀚"))
    table.setCurrentCell(0, 2)
    assert window.current_selected_code == "301716"
    assert window.console.codex_dialogue.ticker.text() == "301716"
    pending = {"running": True}
    window.console._source_worker = SimpleNamespace(
        isRunning=lambda: pending["running"], stop=lambda: None,
        wait=lambda timeout: timeout == 0,
    )
    started = time.monotonic()
    event = QCloseEvent()
    window.closeEvent(event)
    assert time.monotonic() - started < 0.5
    assert not event.isAccepted()
    window._poll_close()
    assert "采集" in window.console.runtime_log.toPlainText()
    pending["running"] = False
    window._poll_close()
    assert window._close_ready
    assert "关闭完成" in (tmp_path / "logs" / "ipo_console_lifecycle.log").read_text(encoding="utf-8")


def test_window_height_and_layout_persist_across_reopen(tmp_path, qt_app, monkeypatch):
    from ats.ui import ipo_learning_console as ui
    from tools import run_ipo_learning_console as launcher
    monkeypatch.setattr(ui._LearningMonitorWorker, "start", lambda self: None)
    monkeypatch.setattr(ui._LearningMonitorWorker, "request_refresh", lambda self: None)
    first = launcher.StandaloneLearningWindow(project_root=tmp_path, simulation_read_only=True)
    first.resize(790, 650)
    first.show()
    qt_app.processEvents()
    assert first.height() == 650
    assert first.console.height() < 650
    assert first.console.content_tabs.geometry().bottom() <= first.console.height()
    first.console.main_splitter.setSizes([160, 400])
    first.console._save_splitter("console/header", first.console.main_splitter)
    state = first.console.main_splitter.saveState()
    first._save_geometry()
    first.close()
    first._poll_close()
    second = launcher.StandaloneLearningWindow(project_root=tmp_path, simulation_read_only=True)
    second.show()
    qt_app.processEvents()
    assert second.size() == first.size()
    assert second.console.main_splitter.saveState() == state
    second.close()
    second._poll_close()


def test_packaged_cli_failure_records_os_code_without_prompt(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise BoundedCLIError("CLI_START_OR_IO_FAILED") from PermissionError(13, "private content")
    monkeypatch.setattr(chat, "_ask_codex", fail)
    monkeypatch.setattr(chat, "resolve_cli_path", lambda *args: "C:/Codex/codex.exe")
    with pytest.raises(BoundedCLIError):
        chat.ask_codex(tmp_path, "session", "private question")
    log = (tmp_path / "logs/ipo_codex_diagnostics.jsonl").read_text(encoding="utf-8")
    record = json.loads(log)
    assert record["errno"] == 13
    assert record["cause_type"] == "PermissionError"
    assert "private question" not in log and "private content" not in log


@pytest.mark.parametrize("stderr,code", [
    (b"You've hit your usage limit", "CLI_USAGE_LIMIT"),
    (b"429 Too many requests", "CLI_RATE_LIMIT"),
    (b"error sending request: connection reset", "CLI_NETWORK_ERROR"),
    (b"authentication required", "CLI_AUTH_REQUIRED"),
])
def test_codex_error_classification(stderr, code):
    from ats.llm.codex_cli_backend import CodexCLIBackend
    assert CodexCLIBackend._classify_cli_exit(1, stderr) == code


def test_recent_questions_persist_cap_and_do_not_send(tmp_path, qt_app, monkeypatch):
    from ats.ui import ipo_codex_dialogue as ui
    monkeypatch.setattr(ui._DialogueWorker, "start", lambda self: None)
    panel = ui.CodexIPODialogue(tmp_path)
    for i in range(23):
        panel._start(f"问题{i}")
        panel._finished()
    panel._error("CLI_USAGE_LIMIT")
    assert "额度已耗尽" in panel.status.text()
    assert "codex login" not in panel.status.text()
    panel.shutdown()
    panel.close()
    reopened = ui.CodexIPODialogue(tmp_path)
    assert reopened.recent_questions.count() == 21
    reopened._reuse_question(1)
    assert reopened.question.toPlainText() == "问题22"
    assert reopened.worker is None
    reopened._started_at = __import__('time').monotonic() - 7
    reopened._busy_label = "等待Codex响应"
    reopened._update_busy()
    assert "7秒" in reopened.status.text()
    reopened.shutdown()
    reopened.close()

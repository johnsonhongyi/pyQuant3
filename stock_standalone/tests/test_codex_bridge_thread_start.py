import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from webTools.window_manager.codex_bridge_manager import BridgeController, CodexBridgeManagerDialog


def test_manual_refresh_requests_catalog_without_starting_or_restarting_engine(tmp_path):
    dialog=SimpleNamespace(controller=SimpleNamespace(runtime_root=tmp_path/'runtime'),refresh_data=Mock())
    CodexBridgeManagerDialog._request_catalog_refresh(dialog)
    assert (dialog.controller.runtime_root/'catalog-refresh.request').is_file()
    dialog.refresh_data.assert_called_once_with()


@pytest.mark.parametrize("layout", ["stock-strategy", "stock_standalone/stock-strategy"])
@pytest.mark.parametrize("launch_from", ["root", "strategy", "nested"])
def test_source_entry_discovery_adapts_to_layout_and_launch_directory(tmp_path, layout, launch_from):
    strategy = tmp_path / layout
    runner = strategy / "tools/run_desktop_strategy_bridge.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("def main(args): pass\n", encoding="utf-8")
    nested = strategy / "development/nested"
    nested.mkdir(parents=True)
    start = {"root": tmp_path, "strategy": strategy, "nested": nested}[launch_from]
    with patch.object(sys, "frozen", False, create=True):
        assert BridgeController(start).bridge_command() == [sys.executable, str(runner)]


def test_packaged_entry_does_not_probe_source_files(tmp_path):
    with patch.object(sys, "frozen", True, create=True), patch.object(Path, "is_file", side_effect=AssertionError("source probe")):
        assert BridgeController(tmp_path).bridge_command() == [sys.executable]


def test_source_runner_loads_exact_path_without_tools_path_or_cached_module(tmp_path):
    runner = tmp_path / "project with spaces" / "stock-strategy/tools/run_desktop_strategy_bridge.py"
    runner.parent.mkdir(parents=True)
    marker = tmp_path / "called.json"
    runner.write_text("import json\nfrom pathlib import Path\ndef main(args):\n    Path(args[-1]).write_text(json.dumps(args), encoding='utf-8')\n", encoding="utf-8")
    arguments = ("--runtime", str(tmp_path / "runtime"), "--marker", str(marker))
    stale_main = Mock(side_effect=AssertionError("stale cached module used"))
    clean_path = [entry for entry in sys.path if Path(entry or ".").name != "tools"]
    with patch.object(sys, "frozen", False, create=True), patch.object(sys, "path", clean_path), \
         patch.dict(sys.modules, {"run_desktop_strategy_bridge": SimpleNamespace(main=stale_main)}):
        BridgeController._run_bridge_thread([sys.executable, str(runner)], arguments)
    assert json.loads(marker.read_text(encoding="utf-8")) == list(arguments)
    stale_main.assert_not_called()


def test_missing_dependency_is_reported_without_uncaught_thread_exception(tmp_path):
    runner = tmp_path / "runner.py"
    runner.write_text("import _nonexistent_codex_bridge_dependency_for_test\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    with patch.object(sys, "frozen", False, create=True), patch.object(threading, "excepthook") as hook:
        thread = threading.Thread(target=BridgeController._run_bridge_thread,
            args=([sys.executable, str(runner)], ("--runtime", str(runtime))))
        thread.start()
        thread.join(3)
        assert not thread.is_alive()
        hook.assert_not_called()
    status = json.loads((runtime / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "degraded"
    assert status["error_code"] == "ModuleNotFoundError"
    assert status["stage"] == "manager_thread_start"
    assert status["agent_pid"] == os.getpid()
    assert status["launch_mode"] == "thread"
    assert "_nonexistent_codex_bridge_dependency_for_test" in status["error_detail"]["message"]
    assert json.loads((runtime / "agent-output.txt").read_text(encoding="utf-8"))["error_code"] == "ModuleNotFoundError"


def test_packaged_runner_keeps_embedded_import(tmp_path):
    main = Mock()
    arguments = ("--runtime", str(tmp_path))
    with patch.object(sys, "frozen", True, create=True), \
         patch.dict(sys.modules, {"run_desktop_strategy_bridge": SimpleNamespace(main=main)}):
        BridgeController._run_bridge_thread([sys.executable], arguments)
    main.assert_called_once_with(list(arguments))


def test_missing_source_file_writes_start_failure(tmp_path):
    runtime = tmp_path / "runtime"
    with patch.object(sys, "frozen", False, create=True):
        BridgeController._run_bridge_thread([sys.executable, str(tmp_path / "missing.py")], ("--runtime", str(runtime)))
    status = json.loads((runtime / "status.json").read_text(encoding="utf-8"))
    assert status["error_code"] == "FileNotFoundError"

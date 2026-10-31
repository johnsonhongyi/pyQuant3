import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import Mock, patch

import pytest
from PyQt6 import QtWidgets

from webTools.window_manager import bridge_startup_manager as startup
from webTools.window_manager import antigravity_bridge_manager as agv
from webTools.window_manager import codex_bridge_manager as codex


def test_failed_parent_with_live_source_agent_is_recovered_and_diagnosed(controllers):
    from webTools.window_manager.bridge_watchdog import BridgeWatchdog
    controller=controllers['codex'];runtime=controller.runtime_path()
    (runtime/'agent').mkdir(parents=True)
    (runtime/'status.json').write_text(json.dumps({'status':'degraded','error_code':'RuntimeError','launch_mode':'process','at':time.time()}),encoding='utf-8')
    (runtime/'agent/agent-status.json').write_text(json.dumps({'status':'ready','updated_epoch':time.time()}),encoding='utf-8')
    with patch.object(sys,'frozen',False,create=True),patch.object(codex,'_source_agent_owner',return_value=123456):
        info=controller.task_info()
    assert info['running'] and info['status']['orphan_agent']
    with patch.object(controller,'task_info',return_value=info):
        assert '父桥已退出' in BridgeWatchdog('Codex',controller).diagnose()


def test_source_agent_recovery_requires_exact_script_and_runtime(tmp_path):
    import psutil
    process=Mock();process.pid=123456;process.create_time.return_value=time.time()-10
    script=tmp_path/'stock-strategy/desktop_strategy_agent.py'
    runtime=tmp_path/'runtime'
    process.info={'cmdline':['python',str(script),'--runtime-root',str(runtime/'agent')]}
    with patch.object(psutil,'process_iter',return_value=[process]):
        assert codex._source_agent_owner(runtime,tmp_path,{'updated_epoch':time.time()})==123456
        process.info['cmdline'][-1]=str(tmp_path/'unrelated')
        assert codex._source_agent_owner(runtime,tmp_path,{'updated_epoch':time.time()})==0


def test_startup_dialog_updates_external_process_state(dialog,controllers):
    from PyQt6.QtTest import QTest
    controllers['codex'].task_info.return_value={'running':True,'mode':'process'}
    dialog._status_timer.setInterval(10)
    QTest.qWait(60)
    assert dialog.controls['codex']['active_mode'].text()=='当前：独立进程'


@pytest.fixture
def controllers(tmp_path):
    result = {"codex": codex.BridgeController(tmp_path), "antigravity": agv.AntigravityBridgeController(tmp_path)}
    for key, controller in result.items():
        controller.preference_path = tmp_path / f"{key}-preferences.json"
        controller.runtime_root = tmp_path / key
    return result


@pytest.fixture
def dialog(controllers):
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with patch.object(startup, "BridgeController", return_value=controllers["codex"]), \
         patch.object(startup, "AntigravityBridgeController", return_value=controllers["antigravity"]):
        for controller in controllers.values():
            controller.task_info = Mock(return_value={"running": False})
        window = startup.BridgeStartupManagerDialog()
        yield window
        window.close()
        window.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("key", ["codex", "antigravity"])
def test_mode_selection_persists_without_starting_or_stopping(dialog, controllers, key):
    controller = controllers[key]
    with patch.object(controller, "_start_bridge") as start, patch.object(controller, "_request_bridge_stop") as stop:
        dialog.controls[key]["mode"].setCurrentIndex(1)
        assert controller.run_mode() == "thread"
        assert dialog.controls[key]["stop"].isChecked()
        assert not dialog.controls[key]["stop"].isEnabled()
        dialog.controls[key]["mode"].setCurrentIndex(0)
        assert controller.run_mode() == "process"
        assert dialog.controls[key]["stop"].isEnabled()
        start.assert_not_called()
        stop.assert_not_called()


def test_running_mode_and_future_preference_are_distinct(dialog, controllers):
    controller = controllers["antigravity"]
    controller.task_info.return_value = {"running": True, "mode": "thread"}
    controller.set_run_mode("thread")
    dialog.refresh_settings()
    dialog.controls["antigravity"]["mode"].setCurrentIndex(0)
    assert controller.run_mode() == "process"
    assert dialog.controls["antigravity"]["active_mode"].text() == "待重启切换模式"
    assert "当前运行方式与所选设置不一致" in dialog.controls["antigravity"]["active_mode"].toolTip()
    assert not dialog.controls["antigravity"]["stop"].isEnabled()


@pytest.mark.parametrize("key", ["codex", "antigravity"])
def test_mode_save_failure_rolls_back_selection(dialog, controllers, key):
    with patch.object(controllers[key], "set_run_mode", side_effect=OSError("locked")), \
         patch.object(QtWidgets.QMessageBox, "warning") as warning:
        dialog.controls[key]["mode"].setCurrentIndex(1)
        assert dialog.controls[key]["mode"].currentData() == "process"
        warning.assert_called_once()


@pytest.mark.parametrize("key", ["codex", "antigravity"])
@pytest.mark.parametrize("enabled", [False, True])
def test_independent_bridge_exit_uses_saved_checkbox(controllers, key, enabled):
    controller = controllers[key]
    controller.set_stop_on_manager_exit_enabled(enabled)
    with patch.object(controller, "task_info", return_value={"running": True, "mode": "process"}), \
         patch.object(controller, "_request_bridge_stop") as stop:
        controller.shutdown_for_manager_exit()
        assert stop.call_count == int(enabled)


@pytest.mark.parametrize("key", ["codex", "antigravity"])
def test_exit_does_not_stop_thread_owned_by_other_manager(controllers, key):
    controller = controllers[key]
    with patch.object(controller, "task_info", return_value={"running": True, "mode": "thread", "status": {"agent_pid": os.getpid() + 10000}}), \
         patch.object(controller, "_request_bridge_stop") as stop:
        controller.shutdown_for_manager_exit()
        stop.assert_not_called()


@pytest.mark.parametrize("key,module", [("codex", codex), ("antigravity", agv)])
def test_dead_local_thread_is_not_reported_as_live_even_with_fresh_heartbeat(controllers, key, module):
    controller = controllers[key]
    runtime = controller.runtime_path()
    (runtime / "agent").mkdir(parents=True)
    (runtime / "status.json").write_text(json.dumps({"status": "degraded", "agent_pid": os.getpid(), "launch_mode": "thread", "at": time.time()}), encoding="utf-8")
    (runtime / "agent/agent-status.json").write_text(json.dumps({"status": "ready", "updated_epoch": time.time()}), encoding="utf-8")
    registry_key = str(runtime.resolve()) if key == "antigravity" else str(runtime).casefold()
    thread = Mock()
    thread.is_alive.return_value = False
    with patch.object(module, "_bridge_owner_is_alive", return_value=True), \
         patch.object(sys, "frozen", True, create=True), \
         patch.dict(controller._thread_registry, {registry_key: thread}):
        assert not controller.task_info()["running"]
        thread.is_alive.return_value = True
        assert controller.task_info()["running"]


def test_agv_validates_process_identity_instead_of_only_pid(controllers):
    process = Mock()
    process.create_time.return_value = time.time() + 100
    fake_psutil = Mock()
    fake_psutil.Process.return_value = process
    fake_psutil.Error = RuntimeError
    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        assert not agv._bridge_owner_is_alive(123, controllers["antigravity"].runtime_path(), time.time(), "process")
        process.create_time.return_value = time.time() - 100
        process.cmdline.return_value = ["unrelated.exe", "--runtime", "C:/unrelated"]
        assert not agv._bridge_owner_is_alive(123, controllers["antigravity"].runtime_path(), time.time(), "process")


@pytest.mark.parametrize("key,module", [("codex", codex), ("antigravity", agv)])
def test_manager_pid_is_not_an_independent_bridge_even_with_packaged_fallback(controllers, key, module):
    controller = controllers[key]
    runtime = controller.runtime_path()
    (runtime / "agent").mkdir(parents=True)
    (runtime / "bridge.pid").write_text(str(os.getpid()), encoding="ascii")
    (runtime / "status.json").write_text(json.dumps({"status": "degraded", "agent_pid": os.getpid(), "launch_mode": "process", "at": time.time()}), encoding="utf-8")
    (runtime / "agent/agent-status.json").write_text(json.dumps({"status": "ready", "updated_epoch": time.time()}), encoding="utf-8")
    with patch.object(module, "_bridge_owner_is_alive", return_value=False), \
         patch.object(controller, "_process_tree_contains", return_value=True), \
         patch.object(sys, "frozen", True, create=True):
        assert not controller.task_info()["running"]


@pytest.mark.parametrize("key", ["codex", "antigravity"])
def test_exit_writes_the_stop_file_consumed_by_its_worker(controllers, key):
    controller = controllers[key]
    controller.set_stop_on_manager_exit_enabled(True)
    with patch.object(controller, "task_info", return_value={"running": True, "mode": "process"}):
        controller.shutdown_for_manager_exit()
    stop_file = controller.runtime_path() / ("agent/stop.request" if key == "codex" else "stop.request")
    assert stop_file.read_text(encoding="ascii").strip() == "manager-exit"


@pytest.mark.parametrize(
    ("key", "module"),
    [("codex", codex), ("antigravity", agv)],
)
def test_restart_wait_does_not_treat_backend_registration_as_running(controllers, key, module):
    controller = controllers[key]
    registered = {"status": "registered", "at": 2.0}
    clock = iter((0.0, 0.0, 6.0))
    with patch.object(module, "_read_json", return_value=registered), \
         patch.object(module.time, "monotonic", side_effect=lambda: next(clock)), \
         patch.object(module.time, "sleep"):
        with pytest.raises(RuntimeError, match="registered"):
            controller._wait_for_restart_startup(previous_status_at=1.0, timeout=1.0)


@pytest.mark.parametrize(
    ("key", "module"),
    [("codex", codex), ("antigravity", agv)],
)
def test_restart_wait_requires_agent_starting_and_live_owner(controllers, key, module):
    controller = controllers[key]
    registered = {"status": "registered", "at": 2.0}
    starting = {"status": "agent_starting", "at": 3.0}
    with patch.object(module, "_read_json", side_effect=(registered, starting)) as read_status, \
         patch.object(module.time, "monotonic", side_effect=(0.0, 0.0, 0.0)), \
         patch.object(module.time, "sleep"), \
         patch.object(controller, "task_info", return_value={"running": True}):
        controller._wait_for_restart_startup(previous_status_at=1.0, timeout=1.0)
        assert read_status.call_count == 2

    with patch.object(module, "_read_json", return_value=starting), \
         patch.object(module.time, "monotonic", side_effect=(0.0, 0.0)), \
         patch.object(controller, "task_info", return_value={"running": False}):
        with pytest.raises(RuntimeError, match="已退出"):
            controller._wait_for_restart_startup(previous_status_at=1.0, timeout=1.0)


@pytest.mark.parametrize(
    ("key", "module"),
    [("codex", codex), ("antigravity", agv)],
)
def test_restart_wait_surfaces_backend_registration_failure(controllers, key, module):
    controller = controllers[key]
    degraded = {
        "status": "degraded",
        "stage": "backend_register",
        "error_code": "ValueError",
        "error_detail": {"stage": "backend_register", "message": "write to closed file"},
        "at": 2.0,
    }
    with patch.object(module, "_read_json", return_value=degraded), \
         patch.object(module.time, "monotonic", side_effect=(0.0, 0.0)):
        with pytest.raises(RuntimeError, match="backend_register.*write to closed file"):
            controller._wait_for_restart_startup(previous_status_at=1.0, timeout=1.0)

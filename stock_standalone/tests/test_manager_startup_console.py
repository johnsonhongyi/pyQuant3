"""CPython version-probe compatibility without GUI or real shell execution."""
import ast
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from webTools import startup_console as startup


@pytest.mark.parametrize('output', [
    'Microsoft Windows [Version 10.0.22631.4317]\r\n',
    'Microsoft Windows [Version 10.0.19045.]\r\n',
    'Microsoft Windows [版本 10.0.22631.4317]\r\n',
    'unexpected version output',
])
def test_hidden_probe_returns_same_result_as_pinned_stdlib(monkeypatch, output):
    query = Mock(return_value=output)
    monkeypatch.setattr(subprocess, 'check_output', query)
    args = ('old-system', 'old-release', 'old-version', (sys.platform,))
    expected = platform._syscmd_ver(*args)
    query.reset_mock()
    assert startup._quiet_syscmd_ver(*args) == expected
    assert query.call_args.kwargs['creationflags'] == getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    assert query.call_args.kwargs['stdin'] == subprocess.DEVNULL
    assert query.call_args.kwargs['stderr'] == subprocess.DEVNULL


def test_fallback_commands_are_all_hidden(monkeypatch):
    query = Mock(side_effect=[OSError('missing'), subprocess.CalledProcessError(1, 'command'),
                             'Microsoft Windows [Version 10.0.22631]'])
    monkeypatch.setattr(subprocess, 'check_output', query)
    assert startup._quiet_syscmd_ver(supported_platforms=(sys.platform,)) == ('Microsoft', 'Windows', '10.0.22631')
    assert [call.args[0] for call in query.call_args_list] == ['ver', 'command /c ver', 'cmd /c ver']
    assert all(call.kwargs['creationflags'] == getattr(subprocess, 'CREATE_NO_WINDOW', 0)
               for call in query.call_args_list)


def test_failed_query_preserves_default_version_fields(monkeypatch):
    query = Mock(side_effect=OSError('missing'))
    monkeypatch.setattr(subprocess, 'check_output', query)
    assert startup._quiet_syscmd_ver('system', 'release', 'version', (sys.platform,)) == ('system', 'release', 'version')
    assert query.call_count == 3


def test_unsupported_platform_does_not_launch_shell(monkeypatch):
    query = Mock()
    monkeypatch.setattr(subprocess, 'check_output', query)
    assert startup._quiet_syscmd_ver('system', 'release', 'version', ()) == ('system', 'release', 'version')
    query.assert_not_called()


def test_install_is_idempotent_without_intercepting_general_process_launch(monkeypatch):
    original_popen = subprocess.Popen
    monkeypatch.setattr(startup, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(platform, '_syscmd_ver', lambda: None)
    query = Mock()
    monkeypatch.setattr(subprocess, 'check_output', query)
    startup.install_quiet_version_probe()
    startup.install_quiet_version_probe()
    assert platform._syscmd_ver is startup._quiet_syscmd_ver
    assert subprocess.Popen is original_popen
    query.assert_not_called()


def test_nonwindows_install_leaves_stdlib_untouched(monkeypatch):
    original = platform._syscmd_ver
    monkeypatch.setattr(startup, 'os', SimpleNamespace(name='posix'))
    startup.install_quiet_version_probe()
    assert platform._syscmd_ver is original


def test_manager_installs_guard_before_optional_imports_and_worker_dispatch():
    source = Path(__file__).resolve().parents[1] / 'webTools/manage_window_layout.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    installation = next(node for node in tree.body if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        and node.value.func.id == 'install_quiet_version_probe')
    first_definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    assert installation.lineno < first_definition.lineno
    helper_import = next(node for node in tree.body if isinstance(node, ast.ImportFrom)
                         and any(alias.name == 'install_quiet_version_probe' for alias in node.names))
    assert helper_import.module == 'webTools.startup_console'


def test_bootstrap_module_does_not_eagerly_import_window_manager():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c',
        'import sys; import webTools.startup_console; assert "webTools.window_manager" not in sys.modules; assert "keyboard" not in sys.modules'],
        cwd=root, stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')


def test_delayed_acer_launch_and_retry_do_not_create_cmd():
    source = Path(__file__).resolve().parents[1] / 'webTools/window_manager/core.py'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == 'launch_predatorsense_gui')
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen']
    assert len(calls) == 2  # Cold launch and the subsequent retry must both be covered.
    for call in calls:
        launcher = Mock()
        aumid = r'shell:AppsFolder\AcerIncorporated.PredatorSenseV30_48frkmn4z8aw4!CentenialConvert'
        expression = ast.Expression(body=call)
        eval(compile(ast.fix_missing_locations(expression), str(source), 'eval'),
             {'subprocess': SimpleNamespace(Popen=launcher), 'app_aumid': aumid})
        launcher.assert_called_once_with(['explorer.exe', aumid])


def test_performance_analyzer_fallback_does_not_create_visible_console():
    source = Path(__file__).resolve().parents[1] / 'webTools/window_manager/ui.py'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == 'open_performance_analyzer')
    call = next(node for node in ast.walk(method) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen')
    namespace = {
        'subprocess': SimpleNamespace(Popen=Mock(), CREATE_NEW_CONSOLE=0x10, CREATE_NO_WINDOW=0x08000000),
        'sys': SimpleNamespace(executable='manager.exe', platform='win32'),
        'script_path': r'C:\app\sys_performance_analyzer.py',
    }
    eval(compile(ast.fix_missing_locations(ast.Expression(body=call)), str(source), 'eval'), namespace)
    namespace['subprocess'].Popen.assert_called_once_with(
        ['manager.exe', r'C:\app\sys_performance_analyzer.py'], creationflags=0x08000000)


def test_application_command_shell_is_hidden_for_gui_launches():
    source = Path(__file__).resolve().parents[1] / 'webTools/window_manager/ui.py'
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == '_launch_program')
    flag_assignment = next(node for node in ast.walk(method) if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == 'creationflags'
                                   for target in node.targets))
    call = next(node for node in ast.walk(method) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen')
    popen = Mock()
    namespace = {
        'subprocess': SimpleNamespace(Popen=popen, CREATE_NO_WINDOW=0x08000000),
        'sys': SimpleNamespace(platform='win32'),
        'cmd_run': 'cd /d "C:\\app" && app.exe',
        'target_dir': r'C:\app',
        'sub_env': {},
    }
    body = ast.Module(body=[flag_assignment, ast.Expr(value=call)], type_ignores=[])
    exec(compile(ast.fix_missing_locations(body), str(source), 'exec'), namespace)
    popen.assert_called_once_with(namespace['cmd_run'], shell=True, cwd=r'C:\app',
                                  env={}, creationflags=0x08000000)

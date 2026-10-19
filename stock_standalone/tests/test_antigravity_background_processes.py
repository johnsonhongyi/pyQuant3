"""Background probes must never create visible command shells."""
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from webTools.window_manager import antigravity_manager as manager


def test_cli_version_probe_has_no_console():
    with patch.object(manager.os.path, 'exists', return_value=True), \
         patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='1.4.2')) as run:
        result = manager.get_antigravity_cli_info()
    assert result['available']
    assert run.call_args.kwargs['shell'] is False
    assert run.call_args.kwargs['creationflags'] == getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    assert run.call_args.kwargs['timeout'] == 3


def test_quota_port_probe_has_no_shell_and_bounded_hidden_process():
    process = SimpleNamespace(info={'name': 'language_server.exe', 'pid': 123,
        'cmdline': ['language_server.exe', '--csrf_token', 'isolated-test'], 'create_time': 0})
    with patch.object(manager, 'get_current_account', return_value={}), \
         patch('psutil.process_iter', return_value=[process]), \
         patch('subprocess.check_output', return_value='') as read:
        manager.fetch_antigravity_quotas()
    assert read.call_args.args[0] == ['netstat', '-ano']
    assert read.call_args.kwargs['shell'] is False
    assert read.call_args.kwargs['creationflags'] == getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    assert read.call_args.kwargs['timeout'] == 3

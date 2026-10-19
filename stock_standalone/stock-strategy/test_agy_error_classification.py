"""AGY catalog/network ambiguity must not change selection or replay inference."""
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import desktop_antigravity_agent as agent
from ats.llm.antigravity_cli_backend import AntigravityCLIBackend
from webTools.window_manager.antigravity_bridge_manager import _format_agv_logs


@pytest.mark.parametrize('transport', [': EOF', 'unexpected EOF', 'TLS handshake timeout',
    'proxyconnect tcp: connection refused', 'dial tcp: no such host', 'network is unreachable'])
def test_network_evidence_precedes_remote_model_selection_text(transport):
    message = 'invalid model selection: --effort is not supported; ' + transport
    error = agent._agy_result_failure({'status': 'ERROR', 'error': message})
    assert error.code == 'AGY_NETWORK_ERROR'
    assert AntigravityCLIBackend._classify_result_failure({'status': 'ERROR',
        'error': {'message': message}}) == 'CLI_RESULT_ERROR_NETWORK_FAILURE'
    assert AntigravityCLIBackend._classify_cli_exit(1, message.encode()) == 'CLI_NETWORK_ERROR'


def test_generic_effort_error_is_uncertain_not_proof_of_bad_configuration():
    message = 'invalid model selection (--model "gemini-3.8-flash-medium" --effort "medium"): --effort is not supported'
    error = agent._agy_result_failure({'status': 'ERROR', 'error': message})
    code, details = agent._chat_error_info(error)
    assert code == 'AGY_MODEL_SELECTION_UNVERIFIED'
    assert '原因未确认' in details['message']
    assert message == details['upstream_message']
    assert details['configuration_verified'] is False
    assert AntigravityCLIBackend._classify_result_failure({'status': 'ERROR', 'error': message}) == 'CLI_RESULT_ERROR_MODEL_SELECTION_UNVERIFIED'
    assert AntigravityCLIBackend._classify_cli_exit(1, message.encode()) == 'CLI_MODEL_SELECTION_UNVERIFIED'


def test_network_cause_after_diagnostic_display_limit_is_not_lost():
    error = agent._agy_result_failure({'status': 'ERROR', 'error':
        'invalid model selection ' + 'x' * 700 + ': unexpected EOF'})
    assert error.code == 'AGY_NETWORK_ERROR'
    assert len(error.agy_error_message) <= 640


@pytest.mark.parametrize('message', ['invalid model selection: --effort is not supported',
                                  'invalid model selection: connection reset by peer'])
def test_selection_and_noneligibility_network_errors_never_repeat_inference(tmp_path, monkeypatch, message):
    runner = Mock()
    def run(command, **kwargs):
        event = {'event': 'result', 'result': {'status': 'ERROR', 'error': message}}
        kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
        return SimpleNamespace(stdout=b'', returncode=1)
    runner.side_effect = run
    monkeypatch.setattr(agent, 'run_bounded_cli', runner)
    agent._run_agy_stream(['agy', '--model', 'fixed', '--effort', 'high', '--print-timeout', '87s'],
        prompt_event='{}\n', timeout=90, started=time.monotonic(), runtime=tmp_path,
        publisher=None, job_id='test', model='fixed', effort='high', prefix='test-agy-')
    assert runner.call_count == 1
    assert runner.call_args.args[0][2:6] == ['fixed', '--effort', 'high', '--print-timeout']


def test_catalog_outage_clears_availability_without_claiming_configuration_error(tmp_path, monkeypatch):
    cli = tmp_path / 'agy.exe'
    cli.touch()
    monkeypatch.setattr(agent, 'run_bounded_cli', Mock(side_effect=agent.BoundedCLIError('CLI_TIMEOUT')))
    catalog = agent.AntigravityCatalog(str(cli))
    assert catalog.probe() is False
    assert catalog.models == []
    assert catalog.catalog_error == 'CLI_TIMEOUT'
    assert catalog.retry_at > time.time()


def test_available_catalog_keeps_actual_model_and_fixed_effort(tmp_path, monkeypatch):
    cli = tmp_path / 'agy.exe'
    cli.touch()
    runner = Mock(return_value=SimpleNamespace(returncode=0,
        stdout=b'gemini-3.8-flash-low\tGemini Flash (Low)\n'))
    monkeypatch.setattr(agent, 'run_bounded_cli', runner)
    catalog = agent.AntigravityCatalog(str(cli))
    assert catalog.probe() is True
    assert catalog.model_ids == ['gemini-3.8-flash-low']
    assert catalog.models[0]['efforts'] == ['low']
    assert catalog.catalog_error == ''
    assert runner.call_count == 1


def test_confirmed_local_catalog_mismatch_remains_configuration_error():
    models = [{'id': 'known', 'efforts': ['low'], 'default_effort': 'low'}]
    assert agent._select_model({'model': 'known'}, models, '') == 'known'
    assert agent._resolve_cli_effort('known', 'low', models) == 'low'
    with pytest.raises(agent.BoundedCLIError, match='MODEL_UNAVAILABLE'):
        agent._select_model({'model': 'missing'}, models, '')
    with pytest.raises(agent.BoundedCLIError, match='EFFORT_UNSUPPORTED'):
        agent._resolve_cli_effort('known', 'high', models)


@pytest.mark.parametrize('code', ['AGY_NETWORK_ERROR', 'AGY_MODEL_SELECTION_UNVERIFIED'])
def test_error_log_does_not_turn_recovery_polling_into_task_retry(code):
    text = _format_agv_logs(json.dumps({'status': 'degraded', 'error_code': code,
        'retry_after_seconds': 5, 'error_detail': {'message': '原因未确认'}}))
    assert code in text
    assert '处理建议' in text
    assert '此任务不会自动重试' in text
    assert '不自动更换模型或档位' in text

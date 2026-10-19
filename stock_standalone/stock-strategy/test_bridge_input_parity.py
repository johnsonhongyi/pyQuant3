"""Frozen inputs and real bridge-probe contracts; no network/model calls."""
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import desktop_antigravity_agent as agent
from desktop_bridge_runtime import chat_input, strategy_input, STRATEGY_INSTRUCTIONS
from desktop_strategy_agent import research_schema


CONVERSATION = 'c3b66b04-872b-4fbe-a3a4-058a026ef20a'
MODELS = [{'id': 'gemini-test', 'efforts': ['low', 'high'], 'default_effort': 'low'}]


@pytest.fixture
def execution(monkeypatch):
    calls = []
    peer = Mock()
    monkeypatch.setattr(agent, 'ProgressPublisher', Mock())
    monkeypatch.setattr(agent, '_emit_log', Mock())
    probe = Mock()
    probe.return_value.snapshot.return_value = {'data_root': 'active-root', 'linkage_db': 'active.db'}
    peer.desktop_runtime_probe = probe.return_value
    monkeypatch.setattr(agent, 'DesktopRuntimeProbe', probe)
    monkeypatch.setattr(agent, 'ats_evidence', Mock(return_value={'status': 'missing', 'as_of': 'old'}))

    def run(command, **kwargs):
        calls.append((command, json.loads(kwargs['stdin_bytes'])['message']['content']))
        event = {'event': 'result', 'result': {'status': 'SUCCESS',
            'response': 'ANTIGRAVITY_BRIDGE_OK', 'conversation_id': CONVERSATION,
            'usage': {'input_tokens': 31, 'output_tokens': 7, 'total_tokens': 38}}}
        kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
        return SimpleNamespace(returncode=0, stdout=b'', completed_by_predicate=True)

    monkeypatch.setattr(agent, 'run_bounded_cli', run)
    return peer, calls


def chat(tmp_path, peer, context):
    with sqlite3.connect(':memory:') as db:
        agent.run_antigravity_chat(peer, {'id': 'chat', 'lease_token': 'lease', 'context': context},
                                  'agy', tmp_path, MODELS, db, Mock())


def test_chat_replays_history_when_starting_new_conversation(tmp_path, execution):
    peer, calls = execution
    context = {'model': 'gemini-test', 'prompt': '追问',
               'messages': [{'role': 'user', 'content': '之前的证据'}]}
    chat(tmp_path, peer, context)
    command, prompt = calls[0]
    assert chat_input(context) in prompt
    assert '--conversation' not in command
    assert command[command.index('--mode') + 1] == 'plan'


def test_chat_resumes_only_requested_conversation_without_replaying_history(tmp_path, execution):
    peer, calls = execution
    chat(tmp_path, peer, {'model': 'gemini-test', 'prompt': '追问', 'thread_id': CONVERSATION,
                          'messages': [{'content': '不要重复的旧消息'}]})
    command, prompt = calls[0]
    assert command[command.index('--conversation') + 1] == CONVERSATION
    assert '--continue' not in command
    assert '不要重复的旧消息' not in prompt


def test_bridge_probe_executes_cli_and_preserves_actual_usage(tmp_path, execution):
    peer, calls = execution
    chat(tmp_path, peer, {'model': 'gemini-test', 'prompt': 'ignored',
                          'bridge_test': True, 'thread_id': 'invalid-not-resumed'})
    assert len(calls) == 1
    assert '--conversation' not in calls[0][0]
    result = peer.post.call_args.args[1]['result']
    assert result['thread_id'] == CONVERSATION
    assert result['token_usage']['inputTokens'] == 31


@pytest.mark.parametrize('response', ['', 'wrong response'])
def test_bridge_probe_cannot_succeed_without_model_confirmation(tmp_path, execution, monkeypatch, response):
    peer, calls = execution
    def run(command, **kwargs):
        event = {'event': 'result', 'result': {'status': 'SUCCESS', 'response': response,
                                             'conversation_id': CONVERSATION}}
        kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(agent, 'run_bounded_cli', run)
    with pytest.raises(agent.BoundedCLIError):
        chat(tmp_path, peer, {'model': 'gemini-test', 'prompt': 'probe', 'bridge_test': True})
    assert peer.post.call_args.args[1]['status'] == 'failed'


def test_strategy_full_frozen_input_selection_schema_and_runtime_root(tmp_path, execution, monkeypatch):
    peer, calls = execution
    context = {'trade_date': '2026-10-19', 'stocks': [{'symbol': '000001.SZ',
        'analysis': {'fresh_quote': False, 'source': 'historical', 'metrics': {'detail': 'x' * 3500}}}],
        'rotation': {'theme': 'dated'}, 'account': {'cash': 123}, 'risk': {'readonly': True},
        'ai_runtime': {'model': 'gemini-test', 'reasoning_effort': 'high'}}
    job = {'id': 'strategy', 'lease_token': 'lease', 'context': context,
           'evidence_hash': agent.digest(context), 'question': '保留用户问题'}
    proposal = {'market_view': 'missing', 'rotation_view': 'unknown', 'answer': 'observe', 'plans': []}
    def run(command, **kwargs):
        prompt = json.loads(kwargs['stdin_bytes'])['message']['content']
        assert strategy_input(job) in prompt
        assert STRATEGY_INSTRUCTIONS in prompt
        assert command[command.index('--model') + 1] == 'gemini-test'
        assert command[command.index('--effort') + 1] == 'high'
        assert json.loads(Path(command[command.index('--json-schema') + 1]).read_text()) == research_schema(context)
        event = {'event': 'result', 'result': {'status': 'SUCCESS', 'response': json.dumps(proposal)}}
        kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(agent, 'run_bounded_cli', run)
    with sqlite3.connect(':memory:') as db:
        agent.run_antigravity_strategy(peer, job, 'agy', tmp_path, MODELS, db, Mock())
    agent.ats_evidence.assert_called_once_with(Path('active-root'), ['000001.SZ'], 'active.db')


def test_strategy_rejects_changed_evidence_before_any_side_effect(tmp_path, execution, monkeypatch):
    peer, calls = execution
    job = {'id': 'bad', 'context': {}, 'evidence_hash': 'tampered'}
    with sqlite3.connect(':memory:') as db, pytest.raises(ValueError, match='evidence hash mismatch'):
        agent.run_antigravity_strategy(peer, job, 'agy', tmp_path, MODELS, db, Mock())
    assert not calls
    peer.post.assert_not_called()
    agent.DesktopRuntimeProbe.assert_not_called()


def test_codex_receives_same_frozen_payload_and_instructions(monkeypatch):
    from desktop_strategy_agent import AppServer
    import muse_research_threads as research
    context = {'stocks': [], 'account': {'cash': 42}, 'risk': {'unchanged': True}, 'trade_date': '2026-10-19'}
    job = {'id': 'a' * 32, 'context': context, 'question': '条件判断',
           'evidence_hash': agent.digest(context)}
    proposal = {'market_view': '', 'rotation_view': '', 'answer': 'observe', 'plans': []}
    app = Mock()
    app.tool_audit = []
    app.readonly_overrides.return_value = {}
    app.request.side_effect = lambda method, params: (
        {'thread': {'id': CONVERSATION}, 'model': 'gemini-test', 'reasoningEffort': 'high'}
        if method == 'thread/start' else {'turn': {'id': 'turn'}} if method == 'turn/start' else {})
    app.event.side_effect = [
        {'method': 'item/completed', 'params': {'threadId': CONVERSATION,
            'item': {'type': 'agentMessage', 'text': json.dumps(proposal)}}},
        {'method': 'turn/completed', 'params': {'threadId': CONVERSATION,
            'turn': {'id': 'turn', 'status': 'completed'}}}]
    monkeypatch.setattr(research, 'ensure_project', lambda app: 'project')
    monkeypatch.setattr(research, 'publish_summary', Mock())
    AppServer.analyze(app, job, model='gemini-test', effort='high')
    requests = {call.args[0]: call.args[1] for call in app.request.call_args_list}
    assert strategy_input(job) in requests['turn/start']['input'][0]['text']
    assert requests['thread/start']['developerInstructions'] == STRATEGY_INSTRUCTIONS
    assert requests['turn/start']['outputSchema'] == research_schema(context)


def test_agv_applies_existing_semantic_validation_before_delivery(tmp_path, execution, monkeypatch):
    peer, calls = execution
    job = {'id': 'strategy', 'lease_token': 'lease', 'context': {'stocks': [], 'model': 'gemini-test'}}
    job['evidence_hash'] = agent.digest(job['context'])
    def run(command, **kwargs):
        proposal = {'market_view': '', 'rotation_view': '', 'answer': 'observe', 'plans': []}
        event = {'event': 'result', 'result': {'status': 'SUCCESS', 'response': json.dumps(proposal)}}
        kwargs['stdout_callback'](json.dumps(event).encode() + b'\n')
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(agent, 'run_bounded_cli', run)
    validator = Mock(side_effect=ValueError('AI follow proposal lacks stock evidence'))
    monkeypatch.setattr(agent, 'validate_result', validator)
    with sqlite3.connect(':memory:') as db, pytest.raises(ValueError, match='lacks stock evidence'):
        agent.run_antigravity_strategy(peer, job, 'agy', tmp_path, MODELS, db, Mock())
    peer.post.assert_not_called()
    validator.assert_called_once()


@pytest.mark.parametrize('partial', [False, True])
def test_expired_conversation_restarts_with_history_only_before_output(tmp_path, execution, monkeypatch, partial):
    peer, calls = execution
    attempts = []
    def run(command, **kwargs):
        attempts.append((list(command), json.loads(kwargs['stdin_bytes'])['message']['content']))
        result = ({'status': 'ERROR', 'error': 'Conversation not found'} if len(attempts) == 1
                  else {'status': 'SUCCESS', 'response': 'recovered', 'conversation_id': CONVERSATION})
        if partial:
            kwargs['stdout_callback'](b'{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"partial"}}\n')
        kwargs['stdout_callback'](json.dumps({'event': 'result', 'result': result}).encode() + b'\n')
        return SimpleNamespace(returncode=0, stdout=b'')
    monkeypatch.setattr(agent, 'run_bounded_cli', run)
    context = {'model': 'gemini-test', 'thread_id': CONVERSATION, 'prompt': 'follow-up',
               'messages': [{'role': 'user', 'content': 'original history'}]}
    if partial:
        with pytest.raises(agent.BoundedCLIError):
            chat(tmp_path, peer, context)
        assert len(attempts) == 1
    else:
        chat(tmp_path, peer, context)
        assert len(attempts) == 2
        assert '--conversation' not in attempts[1][0]
        assert chat_input(context) in attempts[1][1]

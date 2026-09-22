from pathlib import Path
import tempfile
from tools.agenthub_command import parse_request, gate

def test_trigger_without_confirmation_is_plan_only():
    with tempfile.TemporaryDirectory() as d:
        r=gate(Path(d), '@agenthub /run 修复信号')
    assert r['decision']=='PLAN_ONLY' and r['confirmed'] is False

def test_confirmation_allows_run():
    with tempfile.TemporaryDirectory() as d:
        r=gate(Path(d), '@agenthub /run 修复信号 /confirm agenthub')
    assert r['decision']=='EXECUTE_ALLOWED'

def test_plain_request_does_not_enter_hub():
    r=parse_request('请直接修改代码')
    assert r['triggered'] is False

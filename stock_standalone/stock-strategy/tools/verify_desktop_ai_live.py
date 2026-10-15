"""Real running TK/ATS evidence + real Codex + isolated Go queue. No orders."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
import auto_follow as af
import follow_ai as ai
from desktop_runtime import discover_runtime


def main():
    desktop=discover_runtime()
    assert desktop['status']=='connected',desktop
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    state=json.load(opener.open('http://192.168.50.60:20073/api/v1/auto-follow',timeout=20))['data']['state']
    state['validation_scope']='real running packaged desktop; isolated queue/account; no execution'
    runtime=ROOT/'.build-cache'/('desktop-live-'+secrets.token_hex(5));runtime.mkdir()
    (runtime/'peer.key').write_text(secrets.token_hex(32),encoding='ascii')
    (runtime/'targets.json').write_text(json.dumps({'targets':[{'node_id':'live-verify','workspace_id':'isolated','base_url':'http://127.0.0.1:26676','key_file':'peer.key','enabled':True}]}),encoding='utf-8')
    (runtime/'bridge.ini').write_text('[general]\nstock_strategy_base_url=http://127.0.0.1:20084\nipc_node_id=live-verify\nipc_workspace_id=isolated\nipc_key_file=peer.key\n',encoding='utf-8')
    account=af.connect(runtime/'account.db');control=af.connect_control(runtime/'account.db');ai.init_ai(control)
    account.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(json.dumps(state),))
    with (runtime/'service.txt').open('wb') as output:
        service=subprocess.Popen([str(ROOT/'.build-cache/follow-integration.exe'),str(runtime)],stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(50):
                try:opener.open('http://127.0.0.1:20084/api/health',timeout=1).close();break
                except OSError:time.sleep(.1)
            reports=[]
            for model,effort in [('gpt-6-luna','low'),('gpt-6.1-sol','low')]:
                state['ai_settings']={**ai.DEFAULT_AI,'enabled':True,'mode':'enforce','node_id':'live-verify','workspace_id':'isolated','model':model,'reasoning_effort':effort}
                now=datetime.now(af.BJ)
                job=ai.enqueue(control,state,now,question='验收真实运行的 TK/ATS：必须调用 get_ats_evidence 与 get_stock_evidence，核验来源目录、运行进程、当日信号和历史信号区别。只给条件计划，不能为验收强行交易。',force=True)
                run=subprocess.run([sys.executable,str(ROOT/'desktop_strategy_agent.py'),'--config',str(runtime/'bridge.ini'),'--desktop-root',str(ROOT.parent),'--runtime-root',str(runtime/'agent'),'--once'],capture_output=True,timeout=360,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                print(run.stdout.decode('utf-8',errors='replace').strip(),flush=True)
                ai.sync_ai(control,state,datetime.now(af.BJ))
                latest=state.get('ai_latest',{})
                assert latest.get('id')==job, 'model job did not return: '+str(runtime)
                result=latest['result'];tools={t['tool'] for t in result['tool_audit']}
                assert result['model']==model and result['reasoning_effort']==effort
                assert {'get_ats_evidence','get_stock_evidence'}<=tools
                assert result['desktop_runtime']['ats_pid']==desktop['ats_pid']
                assert result['ats_evidence_summary']['signal_count']>0
                reports.append({'job_id':job,'thread_id':result['thread_id'],'model':model,'effort':effort,'desktop':result['desktop_runtime'],'ats':result['ats_evidence_summary'],'plans':len(result['proposal']['plans'])})
                print(json.dumps(reports[-1],ensure_ascii=True),flush=True)
            assert reports[0]['thread_id']!=reports[1]['thread_id'],'independent evidence jobs must not replay growing thread history'
            (ROOT/'.build-cache/desktop-ai-live-acceptance.json').write_text(json.dumps({'status':'passed','production_orders':False,'reports':reports}),encoding='utf-8')
        finally:
            service.terminate();service.wait(timeout=10);control.close();account.close()


if __name__=='__main__':main()

"""Exercise existing running TK/ATS watchlist IPC; never send trade commands."""
import json
from pathlib import Path
import sys
import time
import uuid
import urllib.request
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_runtime import discover_runtime,live_store


def main():
    runtime=discover_runtime()
    if runtime.get('status')!='connected':raise SystemExit(json.dumps(runtime))
    root=Path(runtime['data_root'])
    import configparser
    cfg=configparser.ConfigParser(interpolation=None);cfg.read(root/'global.ini',encoding='utf-8-sig')
    node=cfg['general']['ipc_node_id'];workspace=cfg['general']['ipc_workspace_id']
    favorites=json.loads(live_store(root,'favorite_stocks.json').read_text(encoding='utf-8-sig'))['favorite_stocks']
    code=next(c for c in favorites if c.isdigit() and len(c)==6 and c.startswith(('000','001','002','600','601','603','605')))
    # Existing favorite: verify persistence/consumer receipts without expanding the pool.
    symbol=code+('.SH' if code.startswith('6') else '.SZ')
    now=datetime.now(timezone.utc);operation='desktop-verify-'+uuid.uuid4().hex
    payload={'schema_version':1,'type':'WATCHLIST_ADD','request_id':operation,'operation_id':operation,
             'workspace_id':workspace,'target_node_ids':[node],'symbol':symbol,'instrument_type':'stock',
             'source':'stock-strategy.ai-verification','reason':'Verify existing favorite through running TK and ATS; no order',
             'context_refs':[],'observed_trade_date':now.astimezone().date().isoformat(),
             'created_at':now.isoformat(),'expires_at':(now+timedelta(minutes=5)).isoformat()}
    base='http://192.168.50.60:20073';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request=urllib.request.Request(base+'/api/v1/linkage/commands',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base})
    result=json.load(opener.open(request,timeout=20))
    print(json.dumps({'runtime':runtime,'operation_id':operation,'symbol':symbol,'accepted':result},ensure_ascii=True),flush=True)
    for _ in range(60):
        time.sleep(3)
        result=json.load(opener.open(base+'/api/v1/linkage/operations/'+operation,timeout=20))
        Path(__file__).resolve().parents[1].joinpath('.build-cache/running-desktop-acceptance.json').write_text(json.dumps({'runtime':runtime,'operation_id':operation,'result':result}),encoding='utf-8')
        deliveries=result.get('operation',result).get('deliveries',[])
        consumers=[d.get('result',{}).get('result',{}).get('consumers',{}) for d in deliveries]
        if consumers and all(all(c.get(k,{}).get('status')=='synced' for k in ('TK','ATS')) for c in consumers):
            print(json.dumps(result,ensure_ascii=True),flush=True);return
    print(json.dumps(result,ensure_ascii=True),flush=True)
    raise SystemExit('TK/ATS consumer acknowledgement timeout; persistence alone is not success')


if __name__=='__main__':main()

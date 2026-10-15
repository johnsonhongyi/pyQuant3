"""Run the existing LAN JSON IPC gateway and the desktop AI pull agent together."""
import argparse
import configparser
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
import ipaddress

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from desktop_strategy_agent import NoRedirect,DesktopPeer


def prepare(runtime,backend):
    parsed=urlsplit(backend)
    address=ipaddress.ip_address(parsed.hostname or '')
    if parsed.scheme not in ('http','https') or address.version!=4 or not address.is_private or parsed.username or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('private backend URL required')
    runtime.mkdir(parents=True,exist_ok=True)
    config_path=runtime/'bridge.ini'
    cfg=configparser.ConfigParser(interpolation=None)
    if config_path.exists():cfg.read(config_path,encoding='utf-8')
    if not cfg.has_section('general'):
        cfg.add_section('general')
        local=configparser.ConfigParser(interpolation=None);local.read(ROOT.parent/'global.ini',encoding='utf-8-sig')
        workspace=local.get('general','ipc_workspace_id',fallback='') or 'ws-'+secrets.token_hex(12)
        cfg['general'].update({'ipc_node_id':'codex-'+secrets.token_hex(12),'ipc_workspace_id':workspace,
            'ipc_key_file':str((runtime/'peer.key').resolve())})
        descriptor=os.open(runtime/'peer.key',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(descriptor,'w',encoding='ascii') as stream:stream.write(secrets.token_hex(32)+'\n')
    cfg['general']['stock_strategy_base_url']=backend.rstrip('/')
    with config_path.open('w',encoding='utf-8',newline='') as stream:cfg.write(stream)
    DesktopPeer(config_path)
    return config_path,cfg


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',default='http://192.168.50.60:20073')
    parser.add_argument('--runtime',type=Path,default=ROOT/'logs/desktop-strategy-live')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    runtime=args.runtime.resolve();config_path,cfg=prepare(runtime,args.backend)
    peer=DesktopPeer(config_path)
    def status(value):
        value.update({'node_id':peer.node,'workspace_id':peer.workspace,'at':time.time()})
        temporary=runtime/'status.pending';temporary.write_text(json.dumps(value),encoding='utf-8');os.replace(temporary,runtime/'status.json')
        if sys.stdout:print(json.dumps(value),flush=True)
    if args.prepare_only:status({'status':'prepared','network_changed':False});return
    from system_linkage_gateway import SystemLinkageGateway,build_setup_package
    config=SimpleNamespace(cfg=cfg,cfg_file=str(config_path),linkage_enabled=True,ipc_node_id=peer.node,
        ipc_workspace_id=peer.workspace,ipc_key_file=str(runtime/'peer.key'),stock_strategy_base_url=args.backend,
        ipc_bind_host='auto_lan',ipc_advertise_host='auto',ipc_linkage_port=26776,ipc_peer_allowlist=[urlsplit(args.backend).hostname])
    gateway=SystemLinkageGateway(config,database_path=str(runtime/'gateway.db'))
    child=None
    try:
        registration=gateway.start()
        package=build_setup_package(registration,gateway._key)
        package['backend_base_url']=args.backend
        package['label']='Desktop Codex / ATS AI bridge'
        # LAN import uses the existing same-host admin policy; no auth dump or key logging.
        request=Request(args.backend.rstrip('/')+'/api/v1/linkage/targets/import',data=json.dumps(package).encode(),headers={'Content-Type':'application/json'})
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=20) as response:enrolled=json.load(response)
        if not enrolled.get('target_registered'):raise ValueError('desktop target registration failed')
        status({'status':'registered','desktop_status':enrolled.get('desktop_status'),'port':registration['port']})
        command=[sys.executable,str(ROOT/'desktop_strategy_agent.py'),'--config',str(config_path),
            '--desktop-root',str(ROOT.parent),'--runtime-root',str(runtime/'agent')]
        if args.once:command.append('--once')
        with (runtime/'agent-output.txt').open('ab') as output:
            child=subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (runtime/'bridge.pid').write_text(str(os.getpid()),encoding='ascii')
            status({'status':'running','agent_pid':child.pid})
            code=child.wait()
            if code:raise RuntimeError('desktop agent exited')
    except (OSError,ValueError,RuntimeError) as exc:
        status({'status':'degraded','error_code':type(exc).__name__});raise SystemExit(1)
    finally:
        if child and child.poll() is None:
            from ats.llm.cli_process import _terminate_process_tree
            _terminate_process_tree(child)
        gateway.stop()


if __name__=='__main__':main()

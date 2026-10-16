"""Run the existing LAN JSON IPC gateway and the desktop AI pull agent together."""
import argparse
import configparser
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
import ipaddress

def _is_packaged():
    return (getattr(sys, 'frozen', False) or '__compiled__' in globals()
            or 'NUITKA_ONEFILE_DIRECTORY' in os.environ or hasattr(sys, 'nuitka_version'))


def _application_root():
    """Match TK's packaged path contract: persistent paths are rooted beside the EXE."""
    root = Path(os.path.dirname(os.path.abspath(sys.executable)))
    if root.name.lower() in ('webtools', 'window_manager'):
        root = root.parent
        if root.name.lower() == 'webtools':
            root = root.parent
    return root


def _absolute_path(value):
    return Path(os.path.abspath(os.fspath(value)))


if _is_packaged():
    APP_ROOT = _application_root()
    ROOT = APP_ROOT / 'stock-strategy'
else:
    ROOT = _absolute_path(__file__).parent.parent
    APP_ROOT = ROOT.parent
for _path in (ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from desktop_strategy_agent import NoRedirect,DesktopPeer


class _ThreadOutput:
    def __init__(self, owner_thread, stream, fallback):
        self.owner_thread = owner_thread
        self.stream = stream
        self.fallback = fallback

    def write(self, value):
        target = self.stream if threading.get_ident() == self.owner_thread else self.fallback
        if not target:
            return len(value)
        if target is self.stream and isinstance(value, str):
            target.write(value.encode('utf-8', errors='replace'))
            return len(value)
        return target.write(value)

    def flush(self):
        target = self.stream if threading.get_ident() == self.owner_thread else self.fallback
        if target:
            target.flush()

    def isatty(self):
        return False


def prepare(runtime,backend,desktop_root=None):
    desktop_root=_absolute_path(desktop_root or APP_ROOT)
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
        local=configparser.ConfigParser(interpolation=None);local.read(desktop_root/'global.ini',encoding='utf-8-sig')
        workspace=local.get('general','ipc_workspace_id',fallback='') or 'ws-'+secrets.token_hex(12)
        cfg['general'].update({'ipc_node_id':'codex-'+secrets.token_hex(12),'ipc_workspace_id':workspace,
            'ipc_key_file':str(_absolute_path(runtime/'peer.key'))})
        descriptor=os.open(runtime/'peer.key',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(descriptor,'w',encoding='ascii') as stream:stream.write(secrets.token_hex(32)+'\n')
    cfg['general']['stock_strategy_base_url']=backend.rstrip('/')
    with config_path.open('w',encoding='utf-8',newline='') as stream:cfg.write(stream)
    DesktopPeer(config_path)
    return config_path,cfg


def acquire_bridge_lock(runtime):
    """Hold one runtime-scoped lock for the bridge's entire lifetime."""
    runtime.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        identity=os.path.normcase(os.path.abspath(os.fspath(runtime))).encode('utf-8')
        name='Local\\PyQuant3CodexBridge_'+hashlib.sha256(identity).hexdigest()[:32]
        kernel32=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel32.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype=ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype=ctypes.c_uint32
        kernel32.ReleaseMutex.argtypes=[ctypes.c_void_p]
        kernel32.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel32.CreateMutexW(None,False,name)
        if not handle:return None
        if kernel32.WaitForSingleObject(handle,0) not in (0,0x80):
            kernel32.CloseHandle(handle)
            return None
        return _WindowsBridgeLock(kernel32,handle)
    lock=(runtime/'bridge.lock').open('a+b')
    lock.seek(0,os.SEEK_END)
    if lock.tell()==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,ImportError):
        lock.close()
        return None
    return lock


class _WindowsBridgeLock:
    def __init__(self,kernel32,handle):
        self.kernel32=kernel32
        self.handle=handle

    def close(self):
        if self.handle:
            self.kernel32.ReleaseMutex(self.handle)
            self.kernel32.CloseHandle(self.handle)
            self.handle=None


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',default='http://192.168.50.60:20073')
    parser.add_argument('--runtime',type=Path,default=ROOT/'logs/desktop-strategy-live')
    parser.add_argument('--desktop-root',type=Path,default=APP_ROOT)
    parser.add_argument('--launch-mode',choices=('process','thread'),default='process')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args(argv)
    runtime=_absolute_path(args.runtime);desktop_root=_absolute_path(args.desktop_root)
    bridge_lock=acquire_bridge_lock(runtime)
    if bridge_lock is None:
        print(json.dumps({'status':'already_running','runtime':str(runtime),'at':time.time()}),flush=True)
        return
    try:
        config_path,cfg=prepare(runtime,args.backend,desktop_root)
        peer=DesktopPeer(config_path)
    except Exception:
        bridge_lock.close()
        raise
    def status(value):
        value.update({'node_id':peer.node,'workspace_id':peer.workspace,'launch_mode':args.launch_mode,'at':time.time()})
        temporary=runtime/'status.pending';temporary.write_text(json.dumps(value),encoding='utf-8');os.replace(temporary,runtime/'status.json')
        if sys.stdout:print(json.dumps(value),flush=True)
    if args.prepare_only:
        status({'status':'prepared','network_changed':False})
        bridge_lock.close()
        return
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
        agent_runtime=runtime/'agent';agent_runtime.mkdir(parents=True,exist_ok=True)
        agent_arguments=['--config',str(config_path),'--desktop-root',str(desktop_root),'--runtime-root',str(agent_runtime)]
        if args.once:agent_arguments.append('--once')
        with (runtime/'agent-output.txt').open('ab') as output:
            (runtime/'bridge.pid').write_text(str(os.getpid()),encoding='ascii')
            if getattr(sys,'frozen',False) or args.launch_mode=='thread':
                from desktop_strategy_agent import main as run_agent
                status({'status':'agent_starting','agent_pid':os.getpid(),'port':registration['port']})
                previous_stdout,previous_stderr=sys.stdout,sys.stderr
                owner_thread=threading.get_ident()
                sys.stdout=_ThreadOutput(owner_thread,output,previous_stdout)
                sys.stderr=_ThreadOutput(owner_thread,output,previous_stderr)
                try:
                    run_agent(agent_arguments)
                finally:sys.stdout,sys.stderr=previous_stdout,previous_stderr
                status({'status':'stopped','agent_pid':os.getpid()})
            else:
                command=[sys.executable,str(ROOT/'desktop_strategy_agent.py'),*agent_arguments]
                child=subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                status({'status':'agent_starting','agent_pid':child.pid,'port':registration['port']})
                code=child.wait()
                if code:raise RuntimeError('desktop agent exited')
                status({'status':'stopped','agent_pid':child.pid})
    except (OSError,ValueError,RuntimeError,SystemExit) as exc:
        status({'status':'degraded','error_code':type(exc).__name__})
        raise SystemExit(1)
    except Exception as exc:
        status({'status':'degraded','error_code':type(exc).__name__})
        raise
    finally:
        if child and child.poll() is None:
            from ats.llm.cli_process import _terminate_process_tree
            _terminate_process_tree(child)
        gateway.stop()
        bridge_lock.close()


if __name__=='__main__':main()

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pandas as pd
from tk_frame_fingerprint import recover_blocked_sync_ports, has_sync_consumer, full_ack_matches, content_requires_send, request_immediate_ipc_sync


def owner(failures=0):
    obj=SimpleNamespace(_vis_enabled_cache=False,_stream_subscribers={26670:{"subscribed":True,"fail_count":failures}})
    obj._force_sync_26670=True;obj._force_sync_blocked_26670=True
    obj._last_full_try_26670=100;obj._awaiting_full_ack_26670=("session",9)
    return obj


def test_lost_ack_rearms_port_and_same_content_full_send_without_vis():
    obj=owner()
    assert has_sync_consumer(False,obj._stream_subscribers,None)
    assert recover_blocked_sync_ports(obj,159,True)==[]
    assert recover_blocked_sync_ports(obj,160,True)==[26670]
    assert obj._force_sync_26670 and not obj._force_sync_blocked_26670
    assert content_requires_send(b"same",b"same",explicit_request=True)
    assert not full_ack_matches({"port":26670,"sync_session":"session","source_version":9},obj._awaiting_full_ack_26670)
    assert recover_blocked_sync_ports(obj,161,True)==[]


def test_connect_failure_backoff_is_bounded_and_respects_trading_hours_and_unsubscribe():
    obj=owner(3)
    assert recover_blocked_sync_ports(obj,399,True)==[]
    assert recover_blocked_sync_ports(obj,500,False)==[]
    obj._stream_subscribers[26670]["subscribed"]=False
    assert recover_blocked_sync_ports(obj,500,True)==[]
    obj._stream_subscribers[26670]["subscribed"]=True
    assert recover_blocked_sync_ports(obj,400,True)==[26670]


def method(path,name,namespace):
    # Execute production methods without importing/starting the TK/ATS application.
    tree=ast.parse(Path(path).read_text(encoding="utf-8"))
    node=next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),path,"exec"),namespace)
    return namespace[name]


def test_disabling_vis_keeps_shared_ats_baseline_and_pending_request():
    call=method("instock_MonitorTK.py","update_linkage_status",{"logger":Mock(),"tip_var_status_flag":SimpleNamespace(value=False),"request_immediate_ipc_sync":request_immediate_ipc_sync})
    flag=SimpleNamespace(get=lambda:True)
    obj=SimpleNamespace(tip_var=flag,tdx_var=flag,ths_var=flag,dfcf_var=SimpleNamespace(get=lambda:False),auto_adjust_column=False,
        live_strategy=None,_vis_enabled_cache=False,last_vis_var_status=True,_send_df_wake_event=threading.Event(),
        df_ui_prev="baseline",_df_first_send_done=True,_last_send_df_hash="hash",sync_version=7,_force_full_sync_pending=True)
    call(obj)
    assert obj.df_ui_prev=="baseline" and obj._df_first_send_done
    assert obj.sync_version==7 and obj._last_send_df_hash=="hash" and obj._force_full_sync_pending
    assert obj._send_df_wake_event.is_set()


def test_vis_both_transitions_request_one_immediate_sync_without_resetting_versions():
    call=method("instock_MonitorTK.py","update_linkage_status",{"logger":Mock(),"tip_var_status_flag":SimpleNamespace(value=False),"request_immediate_ipc_sync":request_immediate_ipc_sync})
    flag=SimpleNamespace(get=lambda:True)
    for previous,current in ((False,True),(True,False)):
        event=Mock()
        obj=SimpleNamespace(tip_var=flag,tdx_var=flag,ths_var=flag,dfcf_var=SimpleNamespace(get=lambda:False),
            auto_adjust_column=False,live_strategy=None,_vis_enabled_cache=current,last_vis_var_status=previous,
            _send_df_wake_event=event,_force_full_sync_pending=False,sync_version=7,df_ui_prev="baseline")
        obj._stream_subscribers={26670:{"subscribed":True},26671:{"subscribed":False}}
        obj._force_sync_blocked_26670=True;obj._awaiting_full_ack_26670=("session",9)
        call(obj)
        assert obj._force_sync_26670 and not obj._force_sync_blocked_26670
        assert obj._awaiting_full_ack_26670 is None
        assert not hasattr(obj,"_force_sync_26671")
        assert obj._force_full_sync_pending and obj.sync_version==7 and obj.df_ui_prev=="baseline"
        event.set.assert_called_once()
        obj._force_full_sync_pending=False;event.reset_mock()
        call(obj)  # unchanged Vis state must not trigger another immediate sync
        assert not obj._force_full_sync_pending
        event.set.assert_not_called()


def test_ats_transport_recovery_works_with_ui_auto_refresh_off_and_deduplicates():
    call=method("ats/ui/main_window.py","_maintain_ipc_subscription",{"logger":Mock(),"time":SimpleNamespace(time=lambda:1000)})
    obj=SimpleNamespace(is_auto_refresh_enabled=False,_listener_started=True,_last_recv_t=1,_last_pipe_sync_t=1,
                        current_df=pd.DataFrame({"trade":[10]}),_request_full_sync_async=Mock())
    call(obj);call(obj)
    obj._request_full_sync_async.assert_called_once()
    obj._last_recv_t=999;obj._last_pipe_sync_t=0;obj._request_full_sync_async.reset_mock()
    call(obj);obj._request_full_sync_async.assert_not_called()
    obj._is_closing=True;obj._last_recv_t=0
    call(obj);obj._request_full_sync_async.assert_not_called()


def test_ack_failure_is_observable_without_raising(monkeypatch,caplog):
    import sys
    from ats.ipc_bridge import IPCBridge
    monkeypatch.setitem(sys.modules,"data_utils",SimpleNamespace(send_code_via_pipe=lambda *a,**kw:False,PIPE_NAME_TK="isolated"))
    IPCBridge.__new__(IPCBridge)._ack_data_frame({"source_version":9,"sync_session":"session"})
    assert "[IPC ACK]" in caplog.text and "source_version=9" in caplog.text

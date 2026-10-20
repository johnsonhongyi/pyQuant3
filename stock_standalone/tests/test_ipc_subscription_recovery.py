import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pandas as pd
from tk_frame_fingerprint import recover_blocked_sync_ports, has_sync_consumer, full_ack_matches, content_requires_send, request_immediate_ipc_sync, acknowledge_full_sync


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


def test_unrelated_controls_preserve_resample_restore_and_pending_ipc_request():
    call=method("instock_MonitorTK.py","update_linkage_status",{"logger":Mock(),"tip_var_status_flag":SimpleNamespace(value=False),"request_immediate_ipc_sync":request_immediate_ipc_sync})
    flag=SimpleNamespace(get=lambda:True)
    obj=SimpleNamespace(tip_var=flag,tdx_var=flag,ths_var=flag,dfcf_var=SimpleNamespace(get=lambda:False),auto_adjust_column=False,
        live_strategy=None,_vis_enabled_cache=False,last_vis_var_status=True,_send_df_wake_event=threading.Event(),
        df_ui_prev="baseline",_df_first_send_done=True,_last_send_df_hash="hash",sync_version=7,_force_full_sync_pending=True)
    call(obj)
    assert obj.df_ui_prev=="baseline" and obj._df_first_send_done
    assert obj.sync_version==7 and obj._last_send_df_hash=="hash" and obj._force_full_sync_pending
    assert not obj._send_df_wake_event.is_set()
    assert obj.last_vis_var_status is True


def test_vis_both_transitions_request_one_immediate_sync_without_resetting_versions():
    namespace={"logger":Mock(),"tip_var_status_flag":SimpleNamespace(value=False),"request_immediate_ipc_sync":request_immediate_ipc_sync}
    update=method("instock_MonitorTK.py","update_linkage_status",namespace)
    toggle=method("instock_MonitorTK.py","_on_vis_toggle",namespace)
    flag=SimpleNamespace(get=lambda:True)
    for previous,current in ((False,True),(True,False)):
        event=Mock()
        obj=SimpleNamespace(tip_var=flag,tdx_var=flag,ths_var=flag,dfcf_var=SimpleNamespace(get=lambda:False),
            auto_adjust_column=False,live_strategy=None,_vis_enabled_cache=current,last_vis_var_status=previous,
            _send_df_wake_event=event,_force_full_sync_pending=False,sync_version=7,df_ui_prev="baseline")
        obj._stream_subscribers={26670:{"subscribed":True},26671:{"subscribed":False}}
        obj._force_sync_blocked_26670=True;obj._awaiting_full_ack_26670=("session",9)
        obj.update_linkage_status=lambda:update(obj)
        toggle(obj)
        assert obj._force_sync_26670 and not obj._force_sync_blocked_26670
        assert obj._awaiting_full_ack_26670 is None
        assert not hasattr(obj,"_force_sync_26671")
        assert obj._force_full_sync_pending and obj.sync_version==7 and obj.df_ui_prev=="baseline"
        assert obj.last_vis_var_status is None
        event.set.assert_called_once()
        obj._force_full_sync_pending=False;event.reset_mock()
        update(obj)  # unrelated option buttons must not retrigger Vis or cancel a resample restore
        assert not obj._force_full_sync_pending
        event.set.assert_not_called()


def test_ats_transport_recovery_works_with_ui_auto_refresh_off_and_deduplicates():
    call=method("ats/ui/main_window.py","_maintain_ipc_subscription",{"logger":Mock(),"time":SimpleNamespace(time=lambda:1000),"cct":SimpleNamespace(get_work_time=lambda:True)})
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


def test_after_hours_watchdog_only_recovers_cold_start_not_existing_data():
    call=method("ats/ui/main_window.py","_maintain_ipc_subscription",{"logger":Mock(),"time":SimpleNamespace(time=lambda:1000),"cct":SimpleNamespace(get_work_time=lambda:False)})
    obj=SimpleNamespace(_listener_started=True,_last_recv_t=0,_last_pipe_sync_t=0,
        current_df=pd.DataFrame({"trade":[10]}),_request_full_sync_async=Mock())
    call(obj);obj._request_full_sync_async.assert_not_called()
    obj.current_df=None
    call(obj);obj._request_full_sync_async.assert_called_once()


def test_existing_visualizer_pipe_condition_is_independent_of_vis():
    tree=ast.parse(Path("instock_MonitorTK.py").read_text(encoding="utf-8"))
    expr=next(n.test for n in ast.walk(tree) if isinstance(n,ast.If) and "self.viz_conn is not None" in ast.unparse(n.test) and "not sent" in ast.unparse(n.test))
    obj=SimpleNamespace(viz_conn=object(),qt_process=SimpleNamespace(is_alive=lambda:True))
    assert eval(compile(ast.Expression(expr),"instock_MonitorTK.py","eval"),{"self":obj,"vis_enabled":False,"sent":False})


def test_vis_off_still_prevents_automatic_visualizer_launch_or_linkage():
    call=method("instock_MonitorTK.py","open_visualizer",{})
    obj=SimpleNamespace(vis_var=SimpleNamespace(get=lambda:False))
    call(obj,"000001")  # exits before touching selection, queues, windows or processes
    assert not hasattr(obj,"select_code")


def test_old_ack_cannot_overwrite_concurrent_vis_refresh(monkeypatch):
    import tk_frame_fingerprint as sync
    obj=owner();obj._ipc_sync_state_lock=threading.RLock()
    entered=threading.Event();release=threading.Event();started=threading.Event();done=threading.Event()
    original=full_ack_matches
    def paused(*args):
        entered.set()
        assert release.wait(2)
        return original(*args)
    monkeypatch.setattr(sync,"full_ack_matches",paused)
    ack=threading.Thread(target=acknowledge_full_sync,args=(obj,{"port":26670,"sync_session":"session","source_version":9}))
    def refresh():
        started.set();request_immediate_ipc_sync(obj);done.set()
    request=threading.Thread(target=refresh)
    ack.start()
    try:
        assert entered.wait(1)
        request.start();assert started.wait(1)
        assert not done.wait(0.05)
    finally:
        release.set();ack.join(2)
        if request.ident is not None:request.join(2)
    assert not ack.is_alive() and not request.is_alive()
    assert obj._force_full_sync_pending and obj._force_sync_26670
    assert not obj._force_sync_blocked_26670 and obj._awaiting_full_ack_26670 is None


def test_legacy_ack_cannot_cancel_unsent_refresh_but_confirms_sent_full_baseline():
    obj=owner();request_immediate_ipc_sync(obj)
    assert not acknowledge_full_sync(obj,{"port":26670})[0]
    assert obj._force_sync_26670
    obj._awaiting_full_ack_26670=("session",10)
    assert acknowledge_full_sync(obj,{"port":26670})[0]
    assert not obj._force_sync_26670


def test_watchdog_calendar_failure_is_safe_and_does_not_issue_request():
    calendar=Mock(side_effect=ValueError("calendar unavailable"))
    call=method("ats/ui/main_window.py","_maintain_ipc_subscription",{"logger":Mock(),"time":SimpleNamespace(time=lambda:1000),"cct":SimpleNamespace(get_work_time=calendar)})
    obj=SimpleNamespace(_listener_started=True,current_df=pd.DataFrame({"trade":[10]}),_request_full_sync_async=Mock())
    call(obj);obj._request_full_sync_async.assert_not_called()


def test_async_subscription_send_failure_is_logged_and_busy_state_is_released(monkeypatch):
    import sys
    logs=Mock();threads=[];commands=[]
    original_thread=threading.Thread
    def spawn(*args,**kwargs):
        thread=original_thread(*args,**kwargs);threads.append(thread);return thread
    def send(command,**kwargs):
        commands.append(command);return False
    monkeypatch.setitem(sys.modules,"data_utils",SimpleNamespace(send_code_via_pipe=send,PIPE_NAME_TK="isolated"))
    monkeypatch.setattr(threading,"Thread",spawn)
    call=method("ats/ui/main_window.py","_request_full_sync_async",{"logger":logs})
    obj=SimpleNamespace(_pipe_sync_busy=False)
    assert call(obj)
    threads[0].join(2)
    assert not threads[0].is_alive() and not obj._pipe_sync_busy
    assert commands[0]["subscribe"] and commands[0]["port"]==26670
    logs.warning.assert_called_once()


def test_main_window_vis_checkbutton_binds_to_on_vis_toggle():
    tree = ast.parse(Path("instock_MonitorTK.py").read_text(encoding="utf-8"))
    matches = [
        ast.unparse(n) for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and "cb_cmd" in ast.unparse(n.targets) and "_on_vis_toggle" in ast.unparse(n.value)
    ]
    assert len(matches) >= 1, "Vis checkbutton must bind cb_cmd with _on_vis_toggle in main window"
    assert "text == 'Vis'" in matches[0] or 'text == "Vis"' in matches[0]


def test_request_immediate_ipc_sync_resets_backoff_and_clears_deferred_set():
    obj = owner()
    obj._deferred_port_sync = {26670, 26671}
    obj._last_full_try_26670 = 123456.78
    request_immediate_ipc_sync(obj)
    assert obj._force_full_sync_pending is True
    assert obj._force_sync_26670 is True
    assert obj._force_sync_blocked_26670 is False
    assert obj._last_full_try_26670 == 0.0
    assert 26670 not in obj._deferred_port_sync
    # Unsubscribed port 26671 remains in deferred set
    assert 26671 in obj._deferred_port_sync


def test_send_df_after_hours_forced_port_not_pushed_to_deferred_sync():
    tree = ast.parse(Path("instock_MonitorTK.py").read_text(encoding="utf-8"))
    # Verify the direct elif branch guarding deferred_port_sync includes not is_forced_port
    direct_guards = []
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            for stmt in n.body:
                if isinstance(stmt, ast.Expr) and "deferred_port_sync.add(port)" in ast.unparse(stmt):
                    direct_guards.append(ast.unparse(n.test))
    assert len(direct_guards) >= 1
    assert "not is_forced_port" in direct_guards[0]

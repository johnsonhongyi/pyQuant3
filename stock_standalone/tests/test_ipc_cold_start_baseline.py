import pickle
import struct

import pandas as pd

from ipc_sync_manager import IPCSyncManager
from ats.ipc_bridge import IPCBridge


def _diff_df(percent=0.53):
    cols = pd.MultiIndex.from_tuples([("percent", "self"), ("percent", "other")])
    return pd.DataFrame([[percent, -9.8]], index=["688146"], columns=cols)


def test_ipc_sync_manager_rejects_cold_start_diff(monkeypatch):
    mgr = IPCSyncManager(port=29999, service_name="test", auto_start=False) if False else IPCSyncManager(port=29999, service_name="test")
    calls = []
    callbacks = []
    monkeypatch.setattr(mgr, "request_full_sync", lambda **kw: calls.append(kw) or True)
    monkeypatch.setattr(mgr, "_send_received_feedback", lambda: (_ for _ in ()).throw(AssertionError("must not ACK cold diff")))
    mgr.data_callback = lambda df: callbacks.append(df)

    mgr._process_data_package({"type": "UPDATE_DF_DIFF", "data": _diff_df()})

    assert mgr.current_df is None
    assert calls and calls[-1]["force"] is True
    assert callbacks == []


def test_ipc_sync_manager_preserves_ma20d_across_diff(monkeypatch):
    mgr = IPCSyncManager(port=29998, service_name="test2")
    monkeypatch.setattr(mgr, "_send_received_feedback", lambda: None)

    full = pd.DataFrame(
        [{"code": "688146", "trade": 320.12, "percent": 0.10, "ma20d": 301.55}]
    )
    mgr._process_data_package({"type": "UPDATE_DF_ALL", "data": full})
    mgr._process_data_package({"type": "UPDATE_DF_DIFF", "data": _diff_df(0.53)})

    row = mgr.current_df.loc["688146"]
    assert float(row["percent"]) == 0.53
    assert float(row["ma20d"]) == 301.55


class _FakeConn:
    def __init__(self, payload):
        packet = b"DATA" + struct.pack("!I", len(payload)) + payload
        self._packet = packet
        self._offset = 0

    def settimeout(self, _):
        pass
    def recv(self, n):
        if self._offset >= len(self._packet):
            return b""
        out = self._packet[self._offset:self._offset + n]
        self._offset += len(out)
        return out

    def close(self):
        pass


def test_ats_ipc_bridge_rejects_cold_start_diff(monkeypatch):
    import data_utils

    pipe_calls = []
    monkeypatch.setattr(data_utils, "send_code_via_pipe", lambda obj, *_: pipe_calls.append(obj) or True)
    bridge = object.__new__(IPCBridge)
    delivered = []
    body = {"type": "UPDATE_DF_DIFF", "data": _diff_df(0.53)}
    payload = pickle.dumps(("UPDATE_DF_DATA", body), protocol=pickle.HIGHEST_PROTOCOL)

    bridge._handle_client(_FakeConn(payload), delivered.append, None)

    assert not hasattr(bridge, "_cached_df")
    assert delivered == []
    assert pipe_calls and pipe_calls[-1]["cmd"] == "REQ_FULL_SYNC"
    assert pipe_calls[-1]["port"] == 26670

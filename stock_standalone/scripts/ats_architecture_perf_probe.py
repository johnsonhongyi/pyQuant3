"""Offline IPC probe: execute production methods with an in-memory transport.

No GUI, network, ACK pipe, database, or business file is opened. Packet creation
and initial cache copies are outside the timed receiver section. This measures
local processing, not end-to-end latency. Run with: python -X utf8 <this file>.
"""

import ast
import datetime
import json
import math
import os
import pickle
import platform
import queue
import socket
import statistics
import struct
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd


class MemoryConnection:
    def __init__(self, packet):
        self.packet = packet
        self.offset = 0

    def settimeout(self, timeout):
        pass

    def recv(self, size):
        part = self.packet[self.offset:self.offset + size]
        self.offset += len(part)
        return part

    def close(self):
        pass


def production_bridge():
    source = Path(__file__).resolve().parents[1] / "ats" / "ipc_bridge.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IPCBridge")
    namespace = dict(globals(), datetime=datetime.datetime,
                     _MAX_IPC_PAYLOAD_BYTES=256 * 1024 * 1024,
                     _IPC_FRAME_TIMEOUT_SEC=30.0, _IPC_IDLE_TIMEOUT_SEC=5.0)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["IPCBridge"]


def make_frame(rows, columns=128):
    codes = pd.Index([f"{100000 + i:06d}" for i in range(rows)], name="code")
    values = np.arange(rows, dtype=float)
    data = {"close": values / 100 + 10, "percent": values % 20 - 10,
            "name": [f"stock-{i}" for i in range(rows)],
            "category": [f"sector-{i % 30}" for i in range(rows)]}
    data.update({f"metric_{i}": values + i for i in range(columns - len(data))})
    return pd.DataFrame(data, index=codes)


def probe(bridge_type, frame, kind, samples=101):
    is_diff = kind != "full"
    fields = frame.select_dtypes(include="number").columns
    if kind == "diff_12_columns":
        fields = fields[:12]
    payload = frame.iloc[::100].loc[:, fields].copy() if is_diff else frame
    if is_diff:
        payload = payload + 0.01
    body = {"type": "UPDATE_DF_DIFF" if is_diff else "UPDATE_DF_ALL",
            "data": payload, "sync_session": "offline-probe",
            "ver": 1 if is_diff else 0, "source_version": 1 if is_diff else 0}
    encoded = pickle.dumps(("UPDATE_DF_DATA", body), protocol=pickle.HIGHEST_PROTOCOL)
    packet = b"DATA" + struct.pack("!I", len(encoded)) + encoded
    timings = []
    for iteration in range(samples + 3):
        bridge = bridge_type.__new__(bridge_type)
        acked, delivered = [], []
        bridge._ack_data_frame = acked.append
        bridge._request_full_baseline = lambda: False
        if is_diff:
            bridge._cached_df = frame.copy()
            bridge._last_cache_date = datetime.datetime.now().strftime("%Y-%m-%d")
            bridge._cache_sync_session = "offline-probe"
            bridge._cache_sync_version = 0
        connection = MemoryConnection(packet)
        start = time.perf_counter()
        bridge._handle_client(connection, delivered.append, None)
        elapsed = (time.perf_counter() - start) * 1000
        assert len(delivered) == len(acked) == 1
        assert delivered[0].shape == frame.shape
        if iteration == 0:
            expected = frame.copy()
            if is_diff:
                expected.loc[payload.index, fields] = payload
            pd.testing.assert_frame_equal(delivered[0], expected)
            frozen = delivered[0].copy()
            bridge._cached_df.iloc[0, 0] += 1
            pd.testing.assert_frame_equal(delivered[0], frozen)
        if iteration >= 3:
            timings.append(elapsed)
    ordered = sorted(timings)
    return {"rows": len(frame), "columns": len(frame.columns), "kind": kind,
            "changed_rows": len(payload) if is_diff else len(frame),
            "payload_bytes": len(encoded), "samples": samples,
            "p50_ms": round(statistics.median(timings), 3),
            "p95_ms": round(ordered[math.ceil(samples * .95) - 1], 3),
            "max_ms": round(max(timings), 3)}


def run():
    module_name = "ats.tdx_realtime_fetcher"
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = types.SimpleNamespace(is_trading_time=lambda: (True, "offline"))
    try:
        bridge_type = production_bridge()
        results = [probe(bridge_type, make_frame(rows), kind)
                   for rows in (1000, 5000, 10000)
                   for kind in ("full", "diff_12_columns", "diff_all_numeric_columns")]
        print(json.dumps({"scope": "offline receiver only; no network, ACK I/O, GUI or producer serialization",
                          "python": platform.python_version(), "pandas": pd.__version__,
                          "numpy": np.__version__, "warmup": 3, "results": results}, ensure_ascii=False))
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous


if __name__ == "__main__":
    run()

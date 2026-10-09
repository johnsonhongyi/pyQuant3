"""Isolated, synthetic Qt latency probes; never starts a trading service.

Run from the checkout: python tools/audit_monitor_latency.py
Extracts current production methods, stubs persistence/order dispatch, and uses
temporary synthetic cache files. Timings are diagnostics, not pass/fail budgets.
"""
from __future__ import annotations

import ast
import argparse
import gc
import json
import logging
import math
import os
import re
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from types import MethodType, ModuleType, SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem
from ats.compact_cache import CompactBarRecords, read_cache_payload, write_cache_payload


def extract(relative, namespace, classes=(), methods=None, functions=(), constants=()):
    """Execute only selected source symbols, with supplied inert dependencies."""
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    selected = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name in classes:
                selected.append(node)
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name in (methods or {}).get(node.name, ()):
                    selected.append(child)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in constants for target in node.targets):
            selected.append(node)
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(path), "exec"), namespace)


NS = dict(globals(), COLOR_UP="#ff4444", COLOR_DOWN="#00ff88",
          logger=logging.getLogger("latency-audit"))
extract("tk_gui_modules/qt_table_utils.py", NS, classes=("NumericTableWidgetItem",), constants=("_CLEAN_TRANS",))
extract("ats/ui/ipo_subnew_detector_dialog.py", NS, classes=("IPONumericTableWidgetItem",),
        methods={"IPOSubnewDetectorDialog": ("_update_table_row_data", "_on_scan_finished", "_on_tk_stream_data")})
extract("ats/ui/daily_limit_up_dialog.py", NS,
        functions=("compute_ladder_quality_sort_score",),
        methods={"DailyLimitUpDialog": ("_set_table_item", "_populate_table_rows")})
extract("ats/tdx_realtime_fetcher.py", NS,
        methods={"TDXGlobalCachePool": ("peek_multi_day_df", "_ensure_startup_codes_loaded")})
extract("ats/ui/intraday_strategy_dialog.py", NS,
        methods={"SBCIntradayChartDialog": ("_render_skeleton_or_cached_frame",)})
NS.update(_safe_float=lambda v, default=0.: float(v or default),
          _safe_int=lambda v, default=0: int(v or default), get_cached_stock_name=lambda code: code)
# Row rendering imports formatting constants only. Avoid loading application config.
package = ModuleType("JohnsonUtil")
package.__path__ = []
common = ModuleType("JohnsonUtil.commonTips")
common.co2int, common.vis_column_map = [], {}
sys.modules.update({"JohnsonUtil": package, "JohnsonUtil.commonTips": common})


def bind(state, *names):
    for name in names:
        setattr(state, name, MethodType(NS[name], state))


def timed_qt(app, action):
    """Measure one callback and heartbeat starvation on the real Qt event loop."""
    ticks, outcome = [], {}
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start(2)

    def run():
        started = time.perf_counter()
        try:
            action()
        except Exception as exc:
            outcome["error"] = repr(exc)
        outcome["callback_ms"] = (time.perf_counter() - started) * 1000
        QTimer.singleShot(15, app.quit)

    QTimer.singleShot(15, run)
    app.exec()
    timer.stop()
    outcome["max_heartbeat_gap_ms"] = max((b - a for a, b in zip(ticks, ticks[1:])), default=0) * 1000
    if "error" in outcome:
        raise RuntimeError(outcome["error"])
    return {key: round(value, 2) for key, value in outcome.items()}


def signal(code, price):
    return SimpleNamespace(code=code, name=code, price=price, change_pct=1., vwap=10.,
        vwap_diff_pct=1., is_above_vwap=True, consolidation_days=0, pullback_no_touch=False,
        structure_tag="", trend_desc="", has_kline_launch_sig=False, signal_level="WATCH",
        signal_type="WATCH", stop_loss_price=9., extra_data={}, signal_desc="", update_time="10:00")


class Relay(QObject):
    requested = pyqtSignal(object)


def ipo_state(count):
    codes = [f"{600000 + i:06}" for i in range(count)]
    table = QTableWidget(count, 17)
    state = SimpleNamespace(table=table, ipc_df=None, extra_cols=[], manual_codes=[],
        signals_map={code: signal(code, 10 + i / 100) for i, code in enumerate(codes)},
        monitored_codes=codes, _pending_render_queue=deque(), _render_timer=QTimer(),
        lbl_status=QLabel(), worker=None, voice_alert_enabled=False, auto_refresh_enabled=False,
        _refresh_fleet_and_arbitrations_from_cached_signals=lambda: None,
        _stream_ui_lock=threading.Lock(), _stream_ui_pending=False,
        _check_is_trading_time=lambda: (True, "synthetic"))
    bind(state, "_update_table_row_data", "_on_scan_finished", "_on_tk_stream_data")
    for row, code in enumerate(codes):
        table.setItem(row, 0, QTableWidgetItem(code))
        table.setItem(row, 1, QTableWidgetItem(code))
        state._update_table_row_data(state.signals_map[code], target_row=row)
    return state


def qt_probes(app):
    fake_tdx = ModuleType("ats.tdx_realtime_fetcher")
    fake_tdx.TDXGlobalCachePool = SimpleNamespace(get_instance=lambda: SimpleNamespace(flush_if_due=lambda **kw: False))
    sys.modules["ats.tdx_realtime_fetcher"] = fake_tdx
    results = []
    for count in (100, 300, 500):
        state = ipo_state(count)
        state._pending_render_queue.extend(state.signals_map.values())
        results.append(dict(probe="ipo_scan_finished_drain_no_io", rows=count,
                            **timed_qt(app, lambda: state._on_scan_finished(count, 0.))))
        state.table.setSortingEnabled(False)
        # Deliver the current stream callback on a real queued Qt signal.
        relay = Relay()
        callbacks = []
        relay.requested.connect(lambda callback: callbacks.append(callback), Qt.ConnectionType.QueuedConnection)
        state._stream_ui_update_requested = relay.requested
        frame = pd.DataFrame({"trade": [20 + i / 100 for i in range(count)],
                              "changepercent": [2.] * count}, index=state.monitored_codes)
        state._on_tk_stream_data(frame)
        app.processEvents()
        results.append(dict(probe="ipo_stream_full_table", rows=count,
                            **timed_qt(app, callbacks.pop())))
        state.table.setSortingEnabled(True)
        state.table.sortItems(2, Qt.SortOrder.AscendingOrder)
        frame["trade"] = frame["trade"].iloc[::-1].to_numpy()
        state._on_tk_stream_data(frame)
        app.processEvents()
        result = dict(probe="ipo_stream_price_sort", rows=count, **timed_qt(app, callbacks.pop()))
        result["wrong_prices"] = int(sum(
            abs(float(state.table.item(r, 2).text()) - frame.at[state.table.item(r, 0).text(), "trade"]) > .001
            for r in range(count)))
        results.append(result)
        # Control: freeze sorting for the whole batch, then sort once.
        state._on_tk_stream_data(frame)
        app.processEvents()
        callback = callbacks.pop()

        def frozen_update():
            state.table.setSortingEnabled(False)
            try:
                callback()
            finally:
                state.table.setSortingEnabled(True)

        result = dict(probe="ipo_stream_price_sort_frozen_batch_control", rows=count,
                      **timed_qt(app, frozen_update))
        result["wrong_prices"] = int(sum(
            abs(float(state.table.item(r, 2).text()) - frame.at[state.table.item(r, 0).text(), "trade"]) > .001
            for r in range(count)))
        results.append(result)
        state.table.setSortingEnabled(False)
        state.table.deleteLater()
        daily = SimpleNamespace(table=QTableWidget(0, 22), extra_cols=[], fav_manager=None)
        bind(daily, "_set_table_item", "_populate_table_rows")
        records = [dict(code=code, name=code, price=10., pct=9.9, tier_tag="首板", is_limit_up=True)
                   for code in state.monitored_codes]
        results.append(dict(probe="ats_daily_limit_first_render", rows=count,
                            **timed_qt(app, lambda: daily._populate_table_rows(records))))
        results.append(dict(probe="ats_daily_limit_unchanged_render", rows=count,
                            **timed_qt(app, lambda: daily._populate_table_rows(records))))
        daily.table.deleteLater()

    pool = SimpleNamespace(_mutex=threading.RLock(), _multi_day_df_cache={},
                           _history_static_bars={}, _incremental_intraday_pool={})
    bind(pool, "peek_multi_day_df")
    NS["TDXGlobalCachePool"] = SimpleNamespace(_instance=pool)
    state = SimpleNamespace(code="600000", _current_period_mode="10d", lbl_info=QLabel(), lbl_title=QLabel())
    acquired = threading.Event()

    def holder():
        with pool._mutex:
            acquired.set()
            time.sleep(.35)

    worker = threading.Thread(target=holder)
    worker.start()
    acquired.wait(1)
    results.append(dict(probe="sbc_open_preview_contended_mutex_injected_350ms",
                        **timed_qt(app, lambda: NS["_render_skeleton_or_cached_frame"](state))))
    worker.join(1)
    return results


def cache_probes():
    results = []
    with tempfile.TemporaryDirectory(prefix="ats-latency-") as folder:
        path = Path(folder) / "synthetic-cache.bin"
        for count in (10, 40, 80):
            history = {f"{600000 + i:06}": {"records": [
                dict(time=f"2026-09-{20 + j // 240:02} {9 + (j % 240) // 60:02}:{j % 60:02}",
                     date=f"2026-09-{20 + j // 240:02}", close=10 + j / 10000,
                     open=10., high=11., low=9., vol=j + 1, amount=(j + 1) * 10.)
                for j in range(2400)]} for i in range(count)}
            with path.open("wb") as stream:
                write_cache_payload({"history_static_bars": history}, stream)
            del history
            gc.collect()
            calls = []

            def load(**kwargs):
                started = time.perf_counter()
                payload = read_cache_payload(path)
                entries = payload["history_static_bars"]
                payload["history_static_bars"] = {k: v for k, v in entries.items() if k in kwargs["codes"]}
                del entries
                calls.append((time.perf_counter() - started) * 1000)
                return True

            pool = SimpleNamespace(_startup_loaded_codes=set(), _mutex=threading.RLock(), _load_from_ramdisk=load)
            bind(pool, "_ensure_startup_codes_loaded")
            codes = [f"{600000 + i:06}" for i in range(8)]
            started = time.perf_counter()
            for code in codes:
                pool._ensure_startup_codes_loaded([code])
            serial = (time.perf_counter() - started) * 1000
            pool._startup_loaded_codes.clear()
            started = time.perf_counter()
            pool._ensure_startup_codes_loaded(codes)
            batch = (time.perf_counter() - started) * 1000
            results.append(dict(probe="monolithic_cache_selective_decode_lower_bound", cache_codes=count,
                bars_per_code=2400, compressed_mib=round(path.stat().st_size / 1048576, 2),
                eight_separate_reads_ms=round(serial, 2), one_batch_read_ms=round(batch, 2), decode_calls=len(calls)))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional path for synthetic measurements")
    args = parser.parse_args()
    app = QApplication([])
    rendered = json.dumps(dict(qt=qt_probes(app), cache=cache_probes()), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

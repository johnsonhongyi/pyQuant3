"""Test event-loop behavior without loading the Tk/Qt application."""
import ast
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / "instock_MonitorTK.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def function(name):
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)


class TkRefreshRegressionTests(unittest.TestCase):
    def test_busy_cache_never_blocks_or_clears_monitor_rows(self):
        lock = threading.RLock()
        entered = threading.Event()
        release = threading.Event()
        def holder():
            with lock:
                entered.set()
                release.wait(2)
        worker = threading.Thread(target=holder)
        worker.start()
        self.assertTrue(entered.wait(1))
        tree = Mock()
        tree.selection.return_value = []
        tree.yview.return_value = (0, 1)
        tree.xview.return_value = (0, 1)
        cache = SimpleNamespace(_lock=lock)
        window = Mock()
        window.winfo_exists.return_value = True
        ns = dict(self=SimpleNamespace(realtime_service=SimpleNamespace(kline_cache=cache)),
                  tree=tree, log_win=window, logger=Mock(), time=time)
        body = "\n".join("    " + line for line in ast.unparse(function("refresh_pool_data")).splitlines())
        factory = ("def make():\n"
                   "    is_refreshing_pool = False\n"
                   "    current_sort_column = None\n"
                   "    current_sort_reverse = False\n"
                   "    favorites_sync_running = False\n"
                   "    def reset_refreshing_flag():\n"
                   "        nonlocal is_refreshing_pool\n"
                   "        is_refreshing_pool = False\n" + body +
                   "\n    return refresh_pool_data\n")
        try:
            exec(factory, ns)
            refresh = ns["make"]()
            started = time.perf_counter()
            refresh()
            self.assertLess(time.perf_counter() - started, 0.1)
            tree.delete.assert_not_called()
            window.after.assert_called_once()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_concept_windows_yield_between_refreshes_and_coalesce(self):
        callbacks = []
        windows = []
        for name in ("A", "B", "C"):
            win = Mock()
            win._concept_name = name
            win.winfo_exists.return_value = True
            win._chk_auto.get.return_value = True
            win.state.return_value = "normal"
            windows.append(win)
        app = SimpleNamespace(_pg_top10_window_simple={str(i): {"win": w} for i, w in enumerate(windows)},
                              _fill_concept_top10_content=Mock(),
                              after=lambda delay, callback: callbacks.append(callback))
        ns = dict(time=time, logger=Mock(), tk=SimpleNamespace(TclError=RuntimeError))
        exec(compile(ast.Module(body=[function("update_all_top10_windows")], type_ignores=[]), str(SOURCE), "exec"), ns)
        update = ns["update_all_top10_windows"]
        update(app)
        self.assertEqual(app._fill_concept_top10_content.call_count, 1)
        update(app)
        self.assertEqual(len(callbacks), 1)
        windows[1].winfo_exists.return_value = False
        while callbacks:
            callbacks.pop(0)()
        self.assertEqual(app._fill_concept_top10_content.call_count, 2)
        self.assertFalse(app._top10_refresh_pending)


if __name__ == "__main__":
    unittest.main()

"""Verify selection loading without importing Tk application dependencies."""
import ast
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import Mock


class SelectionRefreshTests(unittest.TestCase):
    def owner(self):
        path = Path(__file__).resolve().parents[1] / 'stock_selection_window.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == '_start_candidate_load')
        workers, timers = [], []
        def thread(**kwargs):
            return SimpleNamespace(start=lambda: workers.append(kwargs['target']))
        ns = dict(queue=queue, threading=SimpleNamespace(Thread=thread), logger=Mock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        owner = SimpleNamespace(selector=SimpleNamespace(get_candidates_df=Mock(return_value='frame')),
                                winfo_exists=lambda: True, load_data=Mock(),
                                after=lambda delay, callback: timers.append(callback))
        owner._start_candidate_load = MethodType(ns['_start_candidate_load'], owner)
        return owner, workers, timers, ns

    def test_computation_is_deferred_and_ui_applies_result(self):
        owner, workers, timers, _ = self.owner()
        owner._start_candidate_load(True, '2026-09-30')
        owner._start_candidate_load(True, '2026-09-30')
        owner.selector.get_candidates_df.assert_not_called()
        self.assertEqual(len(workers), 1)
        timers.pop(0)()  # Running worker has not delivered a result yet.
        owner.load_data.assert_not_called()
        workers.pop(0)()
        owner.load_data.assert_not_called()  # Worker cannot touch Tk.
        timers.pop(0)()
        owner.load_data.assert_called_once_with(force=True, target_date='2026-09-30')
        self.assertFalse(owner._candidate_load_running)

    def test_new_date_discards_old_result_and_closed_window_is_safe(self):
        owner, workers, timers, _ = self.owner()
        owner._start_candidate_load(False, '2026-09-29')
        owner._start_candidate_load(True, '2026-09-30')
        workers.pop(0)()
        timers.pop(0)()
        owner.load_data.assert_not_called()
        self.assertEqual(len(workers), 1)
        workers.pop(0)()
        owner.winfo_exists = lambda: False
        timers.pop(0)()
        owner.load_data.assert_not_called()
        self.assertFalse(owner._candidate_load_running)

    def test_worker_failure_preserves_view_and_allows_retry(self):
        owner, workers, timers, ns = self.owner()
        owner.selector.get_candidates_df.side_effect = OSError('cache unavailable')
        owner._start_candidate_load(True, '2026-09-30')
        workers.pop(0)()
        timers.pop(0)()
        self.assertFalse(owner._candidate_load_running)
        owner.load_data.assert_not_called()
        ns['logger'].error.assert_called_once()
        owner._start_candidate_load(True, '2026-09-30')
        self.assertEqual(len(workers), 1)


if __name__ == '__main__':
    unittest.main()

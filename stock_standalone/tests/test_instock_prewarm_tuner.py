import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'instock_data_fix'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tuner = module('prewarm_tuner', ROOT / 'job/prewarm_tuner.py')


class TestPrewarmTuner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.metrics_file = os.path.join(self.temp_dir.name, 'test_metrics.jsonl')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_and_get_metrics(self):
        m1 = {"stocks": 5544, "loaded": 5540, "seconds": 32.5, "workers": 3, "throughput": 170.5}
        m2 = {"stocks": 5544, "loaded": 5542, "seconds": 30.1, "workers": 3, "throughput": 184.2}
        tuner.record_prewarm_metrics(m1, metrics_path=self.metrics_file)
        tuner.record_prewarm_metrics(m2, metrics_path=self.metrics_file)

        history = tuner.get_prewarm_history(limit=10, metrics_path=self.metrics_file)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['stocks'], 5544)
        self.assertIn('timestamp', history[0])

    def test_cold_start_baseline(self):
        decision = tuner.auto_tune_prewarm_config(cpu_total=4, metrics_path=self.metrics_file)
        self.assertEqual(decision['workers'], 3)
        self.assertEqual(decision['strategy'], 'cold_start_baseline')
        self.assertEqual(decision['history_count'], 0)

    def test_optimal_throughput_keeps_full_workers(self):
        # 模拟近期连续 3 天吞吐极高（耗时 30s 左右）
        for _ in range(3):
            tuner.record_prewarm_metrics(
                {"stocks": 5544, "loaded": 5540, "seconds": 32.0, "workers": 3, "throughput": 173.2},
                metrics_path=self.metrics_file
            )

        decision = tuner.auto_tune_prewarm_config(cpu_total=4, metrics_path=self.metrics_file)
        self.assertEqual(decision['workers'], 3)
        self.assertEqual(decision['strategy'], 'optimal_throughput')

    def test_hdd_contention_throttling_adapts_to_2_workers(self):
        # 模拟外置机械硬盘争抢导致平均耗时超过 130s、吞吐暴跌
        for _ in range(3):
            tuner.record_prewarm_metrics(
                {"stocks": 5544, "loaded": 5500, "seconds": 150.0, "workers": 3, "throughput": 36.9},
                metrics_path=self.metrics_file
            )

        decision = tuner.auto_tune_prewarm_config(cpu_total=4, metrics_path=self.metrics_file)
        # 自适应调优降为 2 个 Worker，保护机械硬盘磁头
        self.assertEqual(decision['workers'], 2)
        self.assertEqual(decision['strategy'], 'hdd_contention_throttling')

    def test_strict_safety_gate_never_exceeds_max_safe_workers(self):
        # 即使机器有 16 核，安全门禁上限也绝不允许超过 3
        decision = tuner.auto_tune_prewarm_config(cpu_total=16, metrics_path=self.metrics_file)
        self.assertLessEqual(decision['workers'], 3)
        self.assertLessEqual(decision['max_safe_workers'], 3)


if __name__ == '__main__':
    unittest.main()

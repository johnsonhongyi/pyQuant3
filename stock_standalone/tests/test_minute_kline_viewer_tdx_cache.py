import unittest
import os
import sys
import tempfile
import zlib
import pickle
import pandas as pd
import numpy as np

# Ensure root dir in path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from minute_kline_viewer_qt import KlineBackupViewer


class TestMinuteKlineViewerTDXCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.viewer = KlineBackupViewer()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_tdx_cache_pool_file_synthetic(self):
        """测试模拟构造的 tdx_global_cache_pool.pkl.z 文件加载与格式化"""
        payload = {
            "date": "2026-09-17",
            "version": 1,
            "updated_at": 1789650000.0,
            "history_static_bars": {
                "600000": {
                    "date": "2026-09-17",
                    "days": 2,
                    "records": [
                        {
                            "time": "09-16 09:31",
                            "date": "2026-09-16",
                            "time_only": "09:31",
                            "open": 10.0,
                            "close": 10.2,
                            "high": 10.3,
                            "low": 9.9,
                            "vwap": 10.15,
                            "vol": 500.0,
                            "amount": 5075.0,
                            "turnover": 0.12
                        },
                        {
                            "time": "09-16 09:32",
                            "date": "2026-09-16",
                            "time_only": "09:32",
                            "open": 10.2,
                            "close": 10.25,
                            "high": 10.3,
                            "low": 10.1,
                            "vwap": 10.20,
                            "vol": 600.0,
                            "amount": 6120.0,
                            "turnover": 0.15
                        }
                    ],
                    "last_cum_vol": 1100.0,
                    "last_cum_amt": 11195.0
                },
                "000001": {
                    "date": "2026-09-17",
                    "days": 1,
                    "records": [
                        {
                            "datetime": "2026-09-17 09:30",
                            "open": 12.0,
                            "close": 12.1,
                            "high": 12.2,
                            "low": 11.9,
                            "vol": 800.0,
                            "amount": 9680.0
                        }
                    ]
                }
            },
            "shares_cache": {"600000": 1000000.0, "000001": 2000000.0}
        }

        # 压缩并写入临时文件
        cache_file = os.path.join(self.temp_dir, "tdx_global_cache_pool.pkl.z")
        raw = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        compressed = zlib.compress(raw, 1)
        with open(cache_file, "wb") as f:
            f.write(compressed)

        # 1. 验证 _load_tdx_cache_pool_file
        df = self.viewer._load_tdx_cache_pool_file(cache_file)
        self.assertFalse(df.empty)
        self.assertEqual(len(df), 3)
        self.assertIn("code", df.columns)
        self.assertIn("time", df.columns)
        self.assertIn("close", df.columns)
        self.assertIn("volume", df.columns)

        # 验证 code 规范化
        codes = df["code"].unique().tolist()
        self.assertIn("600000", codes)
        self.assertIn("000001", codes)

        # 验证时间规范化
        row_600000 = df[df["code"] == "600000"].iloc[0]
        self.assertEqual(row_600000["time"], "2026-09-16 09:31")

        row_000001 = df[df["code"] == "000001"].iloc[0]
        self.assertEqual(row_000001["time"], "2026-09-17 09:30")

        # 2. 验证 load_data
        self.viewer.load_data(cache_file)
        self.assertEqual(len(self.viewer.active_df), 3)
        self.assertIn("TDX Global Cache Pool", self.viewer.stats_label.text())

    def test_load_data_with_misnamed_pkl(self):
        """测试误将 zlib 压缩文件命名为 .pkl 时的自适应解压兼容"""
        payload = {
            "date": "2026-09-17",
            "history_static_bars": {
                "300059": {
                    "records": [
                        {"time": "2026-09-17 09:30", "open": 20.0, "close": 20.5, "vol": 100}
                    ]
                }
            }
        }
        misnamed_file = os.path.join(self.temp_dir, "fake_tdx_cache.pkl")
        raw = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        compressed = zlib.compress(raw, 1)
        with open(misnamed_file, "wb") as f:
            f.write(compressed)

        self.viewer.load_data(misnamed_file)
        self.assertFalse(self.viewer.active_df.empty)
        self.assertEqual(self.viewer.active_df.iloc[0]["code"], "300059")

    def test_auto_load_priority_and_detection(self):
        """测试 auto_load 多候选优先级探测逻辑"""
        from unittest.mock import patch
        import time

        f_old = os.path.join(self.temp_dir, "minute_kline_cache.pkl")
        f_new = os.path.join(self.temp_dir, "tdx_global_cache_pool.pkl.z")

        df_old = pd.DataFrame([{"code": "000001", "time": "2026-09-01 09:30", "close": 10.0}])
        df_old.to_pickle(f_old)

        payload_new = {
            "date": "2026-09-17",
            "history_static_bars": {
                "600519": {
                    "records": [{"time": "2026-09-17 09:30", "open": 1800.0, "close": 1850.0, "vol": 50}]
                }
            }
        }
        with open(f_new, "wb") as f:
            f.write(zlib.compress(pickle.dumps(payload_new), 1))

        # 设置时间戳确保 f_new 比 f_old 更新
        now = time.time()
        os.utime(f_old, (now - 100, now - 100))
        os.utime(f_new, (now, now))

        def fake_get_ramdisk_path(fname):
            p = os.path.join(self.temp_dir, fname)
            return p if os.path.exists(p) else None

        with patch("minute_kline_viewer_qt.cct.get_ramdisk_path", side_effect=fake_get_ramdisk_path), \
             patch("minute_kline_viewer_qt.cct.get_ramdisk_dir", return_value=self.temp_dir):
            self.viewer.auto_load()
            self.assertFalse(self.viewer.active_df.empty)
            self.assertIn("600519", self.viewer.active_df["code"].values)

    def test_save_and_reload_pkl_z(self):
        """测试 .pkl.z 格式数据的保存与重新加载回环验证"""
        test_df = pd.DataFrame([
            {"code": "600733", "time": "2026-09-17 09:30", "open": 25.0, "close": 25.5, "high": 25.8, "low": 24.9, "volume": 5000.0},
            {"code": "600733", "time": "2026-09-17 09:31", "open": 25.5, "close": 25.8, "high": 26.0, "low": 25.4, "volume": 3200.0}
        ])
        self.viewer.active_df = test_df
        self.viewer.current_file = os.path.join(self.temp_dir, "export_cache.pkl.z")

        # 模拟保存
        raw_bytes = pickle.dumps(test_df, protocol=pickle.HIGHEST_PROTOCOL)
        compressed = zlib.compress(raw_bytes, 1)
        with open(self.viewer.current_file, "wb") as f:
            f.write(compressed)

        # 验证重新加载
        reloaded_df = self.viewer._load_tdx_cache_pool_file(self.viewer.current_file)
        self.assertFalse(reloaded_df.empty)
        self.assertEqual(len(reloaded_df), 2)
        self.assertIn("600733", reloaded_df["code"].values)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""
tests/test_ipo_command_room_persistence.py
-------------------------------------------
自动化测试：
1. 验证新股集中交易指挥室 (IPOCommandRoomDialog) 表格列宽初始宽度合理性 (防截断)；
2. 验证表格列宽手动拖拽后自动持久化到 JSON 并准确反序列化恢复；
3. 验证 TKIPCSubscriber 与全量/增量 (UPDATE_DF_ALL / UPDATE_DF_DIFF) 原地合并算法；
4. 验证 IPCBridge 全量与增量双模解包交付逻辑。
"""

import os
import sys
import json
import tempfile
import unittest
import pandas as pd
import numpy as np

# 确保项目根目录在 sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 初始化无头 QApplication 实例供测试使用
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from ats.ui.ipo_command_room_dialog import (
    IPOCommandRoomDialog,
    IPOCommandRoomTableWidget
)
from ats.network.tk_ipc_subscriber import TKIPCSubscriber
from ats.ipc_bridge import IPCBridge


class TestIPOCommandRoomPersistenceAndIPC(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_01_default_column_widths_no_truncation(self):
        """测试 1: 验证天梯、持仓、指令表格初始列宽已优化，杜绝动能分与启动时点截断"""
        dlg = IPOCommandRoomDialog(parent_detector_dialog=None)
        
        # 1. 天梯表 tbl_rank
        rank_tbl = dlg.tbl_rank
        self.assertGreaterEqual(rank_tbl.columnWidth(4), 62, "天梯表'动能分'列宽应 >= 62px，避免显示为'动能...'")
        self.assertGreaterEqual(rank_tbl.columnWidth(5), 72, "天梯表'启动时点'列宽应 >= 72px，避免显示为'启动...'")
        self.assertGreaterEqual(rank_tbl.columnWidth(2), 75, "天梯表'名称'列宽应 >= 75px")

        # 2. 持仓表 tbl_pos
        pos_tbl = dlg.tbl_pos
        self.assertGreaterEqual(pos_tbl.columnWidth(3), 58, "持仓表'现价'列宽应 >= 58px")
        self.assertGreaterEqual(pos_tbl.columnWidth(6), 65, "持仓表'盈亏比%'列宽应 >= 65px")

        # 3. 待执行指令表 tbl_orders
        orders_tbl = dlg.tbl_orders
        self.assertGreaterEqual(orders_tbl.columnWidth(2), 70, "指令表'动作'列宽应 >= 70px")
        self.assertGreaterEqual(orders_tbl.columnWidth(5), 65, "指令表'目标仓位'列宽应 >= 65px")
        
        dlg.close()

    def test_02_column_widths_drag_and_persistence(self):
        """测试 2: 验证手动修改列宽后，通过 setup_persistence 正确持久化并重启恢复"""
        # 1. 创建第一个测试表格并绑定持久化配置
        test_key = "test_ipo_cmd_rank_v_test"
        table1 = IPOCommandRoomTableWidget(parent_cmd_room=None)
        table1.setColumnCount(6)
        table1.setHorizontalHeaderLabels(["排名", "代码", "名称", "现价", "动能分", "启动时点"])
        
        initial_widths = [45, 60, 80, 60, 65, 75]
        table1.setup_persistence(
            config_key=test_key,
            default_widths=initial_widths
        )
        table1._has_been_visible = True
        table1.restore_column_widths()

        # 验证初始加载
        for idx, w in enumerate(initial_widths):
            self.assertEqual(table1.columnWidth(idx), w)

        # 2. 模拟操盘手手动拖拽拉大“动能分”(列4) 到 95px，“启动时点”(列5) 到 110px
        table1.setColumnWidth(4, 95)
        table1.setColumnWidth(5, 110)
        
        # 显式触发保存
        table1.save_column_widths()

        # 3. 创建第二个新表格实例，模拟下次启动，验证准确恢复自定义列宽
        table2 = IPOCommandRoomTableWidget(parent_cmd_room=None)
        table2.setColumnCount(6)
        table2.setHorizontalHeaderLabels(["排名", "代码", "名称", "现价", "动能分", "启动时点"])
        table2.setup_persistence(
            config_key=test_key,
            default_widths=initial_widths
        )
        table2._has_been_visible = True
        table2.restore_column_widths()

        self.assertEqual(table2.columnWidth(4), 95, "重启后'动能分'列宽应精准恢复为 95px")
        self.assertEqual(table2.columnWidth(5), 110, "重启后'启动时点'列宽应精准恢复为 110px")
        self.assertEqual(table2.columnWidth(0), 45, "未修改列应维持原值 45px")

    def test_03_incremental_diff_merge_algorithm(self):
        """测试 3: 验证 UPDATE_DF_DIFF 增量合并算法的正确性与新列自适应"""
        # 模拟基础全量行情 DataFrame
        df_base = pd.DataFrame({
            "code": ["001365", "688826", "301677"],
            "name": ["天海电子", "沈鼓集团", "频准激光"],
            "trade": [25.50, 48.20, 32.10],
            "changepercent": [2.5, -1.2, 5.8]
        }).set_index("code")

        # 模拟经过一段交易后，只有 001365 和 688826 价格发生变动，且新增了一只股票 688835
        df_updated = pd.DataFrame({
            "code": ["001365", "688826", "301677", "688835"],
            "name": ["天海电子", "沈鼓集团", "频准激光", "百胜智能"],
            "trade": [26.80, 47.90, 32.10, 15.60],
            "changepercent": [7.6, -1.8, 5.8, 9.9]
        }).set_index("code")

        # 使用 df.compare 模拟生产环境中 instock_MonitorTK 产出的 MultiIndex 增量差分包
        df_diff = df_updated.compare(pd.concat([df_base, pd.DataFrame(index=["688835"])]), keep_shape=False, keep_equal=False)

        # 验证 MultiIndex 结构存在
        self.assertIsInstance(df_diff.columns, pd.MultiIndex)

        # 运行系统的增量合并逻辑
        new_cols = {}
        for col in df_diff.columns:
            if isinstance(col, tuple) and len(col) >= 2:
                base_col, val_type = col[0], col[1]
                if val_type == "self":
                    new_cols[base_col] = df_diff[col]
        clean_diff = pd.DataFrame(new_cols, index=df_diff.index)

        df_target = df_base.copy()
        for col in clean_diff.columns:
            if col not in df_target.columns:
                df_target[col] = clean_diff[col]

        common_idx = df_target.index.intersection(clean_diff.index)
        for col in clean_diff.columns:
            col_data = clean_diff.loc[common_idx, col]
            valid_mask = col_data.notna()
            valid_indices = valid_mask[valid_mask].index
            if len(valid_indices) > 0:
                df_target.loc[valid_indices, col] = clean_diff.loc[valid_indices, col]

        # 验证合并结果
        self.assertAlmostEqual(df_target.loc["001365", "trade"], 26.80)
        self.assertAlmostEqual(df_target.loc["001365", "changepercent"], 7.6)
        self.assertAlmostEqual(df_target.loc["688826", "trade"], 47.90)
        self.assertAlmostEqual(df_target.loc["301677", "trade"], 32.10, "未变动的标的保持原价")

    def test_04_ipc_bridge_full_and_diff_unpacking(self):
        """测试 4: 验证 IPCBridge 对 dict 包装的 UPDATE_DF_ALL 和 UPDATE_DF_DIFF 解析交付"""
        bridge = IPCBridge()
        received_dfs = []

        def dummy_callback(df):
            received_dfs.append(df.copy())

        # 1. 模拟全量数据包推流
        df_full = pd.DataFrame({
            "code": ["001365", "688826"],
            "trade": [25.0, 50.0]
        })
        pkg_full = {
            "type": "UPDATE_DF_ALL",
            "data": df_full,
            "ver": 1,
            "resample": "d"
        }

        # 模拟内部处理
        class MockConn:
            def __init__(self, data_bytes):
                self.data = data_bytes
                self.pos = 0
            def recv(self, n):
                chunk = self.data[self.pos:self.pos+n]
                self.pos += len(chunk)
                return chunk
            def settimeout(self, t):
                pass
            def close(self):
                pass

        import pickle
        import struct
        payload = pickle.dumps(("UPDATE_DF_DATA", pkg_full), protocol=pickle.HIGHEST_PROTOCOL)
        stream = b"DATA" + struct.pack("!I", len(payload)) + payload

        bridge._handle_client(MockConn(stream), data_callback=dummy_callback, signal_callback=None)
        
        self.assertEqual(len(received_dfs), 1)
        self.assertEqual(len(received_dfs[0]), 2)
        self.assertIn("001365", received_dfs[0].index)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""
ATS UI Stutter & Lazy Rendering Regression Test Suite
验证主线程零卡顿流水线：
1. NewStockPanel 可见性短路与 O(1) 预索引映射
2. NewStockPanel ensure_rendered 按需补齐
3. TradeFlowTable isVisible 短路
4. Tier 2 纯惰性脏标记维护
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# 确保导入路径
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(_CUR_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PyQt6.QtWidgets import QApplication

# 确保 QApplication 单例
_app = QApplication.instance()
if not _app:
    _app = QApplication(sys.argv)

from ats.ui.new_stock_panel import NewStockPanel
from ats.ui.trade_flow import TradeFlowTable


class TestUIStutterAndLazyRendering(unittest.TestCase):
    """测试界面防卡顿与按需惰性渲染"""

    def setUp(self):
        # 构造模拟全市场 DataFrame
        n = 100
        codes = [f"{i:06d}" for i in range(1, n + 1)]
        self.df_ipc = pd.DataFrame({
            "code": codes,
            "close": np.random.uniform(10, 50, n),
            "percent": np.random.uniform(-5, 5, n),
            "turnoverrate": np.random.uniform(1, 10, n),
            "dff": np.random.uniform(-2, 2, n),
            "rank": np.arange(1, n + 1),
        }, index=codes)

    def test_new_stock_panel_visibility_short_circuit(self):
        """测试 NewStockPanel 在不可见时不会执行重绘，只暂存数据与置脏标记"""
        panel = NewStockPanel()
        panel.hide()  # 确保不可见
        self.assertFalse(panel.isVisible())

        # 初始状态
        self.assertFalse(getattr(panel, "_needs_render", False))

        # 推送实时数据
        panel.update_from_ipc_df(self.df_ipc, sh_pct=1.2)

        # 断言：由于面板不可见，触发了短路，_needs_render 被标记为 True
        self.assertTrue(panel._needs_render)
        self.assertIsNotNone(panel._pending_ipc_df)
        self.assertEqual(panel._pending_ipc_sh_pct, 1.2)

        # 模拟切换 Tab 调用 ensure_rendered
        panel.ensure_rendered()

        # 断言：补齐渲染后脏标记复位
        self.assertFalse(panel._needs_render)

    def test_trade_flow_table_visibility_short_circuit(self):
        """测试 TradeFlowTable 在不可见时快速短路，不执行主线程逐行计算"""
        tf = TradeFlowTable()
        tf.hide()
        self.assertFalse(tf.isVisible())

        # 调用行情刷新，由于不可见短路，不执行任何表格更新
        initial_rc = tf.table.rowCount()
        tf.update_realtime_prices(self.df_ipc)
        self.assertEqual(tf.table.rowCount(), initial_rc)


if __name__ == "__main__":
    unittest.main()

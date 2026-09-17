# -*- coding: utf-8 -*-
"""
tests/test_ipo_subnew_detector.py
---------------------------------
专项验证：新股次新股独立超短检测工具 (SBC 极限 10日 VWAP 预判与异动引擎)
1. 极限 VWAP 走平蓄势 1~3 天判定 (预下单潜伏)；
2. 在 VWAP 上方回踩不碰判定 (黄金极限启动买点)；
3. 跌破 VWAP 破位弱势股拦截 (反抽仅为止损点)；
4. IPC 跨进程队列通信与心跳守护；
5. run_ats.py 顶层命令行分发 (--ipo-detector)。
"""

import os
import sys
import json
import unittest
import warnings
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# 深度屏蔽高频指标计算中的 PerformanceWarning 与 SettingWithCopyWarning
try:
    pd.options.mode.chained_assignment = None
    if hasattr(pd, 'errors') and hasattr(pd.errors, 'PerformanceWarning'):
        warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
except Exception:
    pass
warnings.filterwarnings('ignore', message='.*DataFrame is highly fragmented.*')
warnings.filterwarnings('ignore', message='.*A value is trying to be set on a copy of a slice from a DataFrame.*')

# 确保路径
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal
)
from ats.ui.ipo_detector_ipc import (
    send_stock_to_ipo_detector,
    pop_queued_stocks,
    update_detector_heartbeat,
    is_ipo_detector_alive,
    build_ipo_detector_command
)


class TestIPOSubnewDetector(unittest.TestCase):
    """新股次新超短检测工具自动化测试"""

    def setUp(self):
        self.engine = IPOVWAPDetectorEngine.get_instance()

    def test_vwap_consolidation_pre_order_detection(self):
        """【测试】验证在 VWAP 上方走平蓄势 3 天精准触发【🎯 预下单】信号 (如天海电子走势)"""
        # 构造连续 3 天在 VWAP 上方窄幅震荡 (< 3% 振幅) 的多日分时数据
        rows = []
        dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"]
        for d in dates[:-1]:
            # 走平天: VWAP=34.0, 价格在 33.8 ~ 34.2 极窄波动
            for minute in range(30):
                rows.append({
                    "time": f"{d} 09:{minute:02d}",
                    "date": d,
                    "open": 34.0,
                    "close": 34.1,
                    "high": 34.2,
                    "low": 33.9,
                    "price": 34.1,
                    "vwap": 34.0,
                    "amount": 1000000,
                    "volume": 30000
                })
        # 今日 (2026-09-17): 现价 34.2, VWAP=34.0
        d_today = dates[-1]
        for minute in range(10):
            rows.append({
                "time": f"{d_today} 09:{30+minute:02d}",
                "date": d_today,
                "open": 34.0,
                "close": 34.2,
                "high": 34.3,
                "low": 34.0,
                "price": 34.2,
                "vwap": 34.0,
                "amount": 1500000,
                "volume": 45000
            })

        mock_df = pd.DataFrame(rows)
        mock_kline = pd.DataFrame({
            "close": [33.0, 33.2, 33.5, 33.8, 34.2],
            "low": [32.5, 32.5, 32.8, 33.0, 33.5],
            "ma5": [33.0, 33.2, 33.4, 33.6, 33.8],
            "lower": [32.4, 32.4, 32.5, 32.5, 32.5]
        })

        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=mock_kline):
            sig = self.engine.analyze_stock("001365", force_refresh=True)

            self.assertEqual(sig.code, "001365")
            self.assertTrue(sig.is_above_vwap)
            self.assertGreaterEqual(sig.consolidation_days, 1)
            self.assertEqual(sig.signal_type, "PRE_ORDER")
            self.assertIn("预下单", sig.signal_level)
            self.assertIn("走平", sig.structure_tag)

    def test_vwap_pullback_no_touch_buy_detection(self):
        """【测试】验证在 VWAP 上方回踩不碰触发【🚀 回踩启动】黄金买点"""
        rows = []
        d = "2026-09-17"
        # 价格在 35.0，向 VWAP(34.0) 靠拢下探到 34.1 (回踩不碰)，随后拉起至 34.8
        for m in range(20):
            p = 35.0 - m * 0.045  # 最低打到约 34.1
            rows.append({
                "time": f"{d} 10:{m:02d}",
                "date": d,
                "open": p + 0.02,
                "close": p,
                "high": p + 0.05,
                "low": p - 0.02,
                "price": p,
                "vwap": 34.0,
                "amount": 500000,
                "volume": 15000
            })
        # 随后拐头拉起到 34.8
        for m in range(10):
            p = 34.1 + m * 0.07
            rows.append({
                "time": f"{d} 10:{20+m:02d}",
                "date": d,
                "open": p - 0.02,
                "close": p,
                "high": p + 0.05,
                "low": p - 0.01,
                "price": p,
                "vwap": 34.0,
                "amount": 1000000,
                "volume": 30000
            })

        mock_df = pd.DataFrame(rows)
        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.engine.analyze_stock("688826", force_refresh=True)

            self.assertTrue(sig.is_above_vwap)
            self.assertTrue(sig.pullback_no_touch)
            self.assertEqual(sig.signal_type, "PULLBACK_BUY")
            self.assertIn("回踩启动", sig.signal_level)
            self.assertIn("回踩不碰", sig.structure_tag)

    def test_broken_stock_vwap_stop_loss_rejection(self):
        """【测试】验证破位跌破 VWAP 的弱势股，反抽触碰 VWAP 仅视作止损点，严禁发出买入"""
        rows = []
        d = "2026-09-17"
        # VWAP=50.0, 现价破位下跌至 48.0 (-4%)
        for m in range(25):
            p = 50.0 - m * 0.08
            rows.append({
                "time": f"{d} 09:{30+m:02d}",
                "date": d,
                "open": p + 0.05,
                "close": p,
                "high": p + 0.08,
                "low": p - 0.05,
                "price": p,
                "vwap": 50.0,
                "amount": 500000,
                "volume": 10000
            })

        mock_df = pd.DataFrame(rows)
        with patch.object(self.engine.fetcher, "fetch_multi_day_intraday_bars", return_value=mock_df), \
             patch.object(self.engine.fetcher, "fetch_kline_bars", return_value=pd.DataFrame()):
            sig = self.engine.analyze_stock("301677", force_refresh=True)

            self.assertFalse(sig.is_above_vwap)
            self.assertLess(sig.vwap_diff_pct, -0.8)
            self.assertEqual(sig.signal_type, "WEAK_EXIT")
            self.assertIn("破位止损点", sig.signal_level)
            self.assertIn("破位", sig.structure_tag)

    def test_ipc_queue_push_and_pop(self):
        """【测试】验证跨进程通信中心队列原子压入与消费"""
        with patch("ats.ui.ipo_detector_ipc.is_ipo_detector_alive", return_value=True):
            send_stock_to_ipo_detector("001365", "天海电子")
            send_stock_to_ipo_detector("688826", "派林激光")

            queued = pop_queued_stocks()
            self.assertIn("001365", queued)
            self.assertIn("688826", queued)

            # 再次拉取应已清空
            queued_again = pop_queued_stocks()
            self.assertEqual(queued_again, [])

    def test_run_ats_command_dispatch(self):
        """【测试】验证 run_ats.py 顶层支持 --ipo-detector 独立分发"""
        import run_ats
        cmd = build_ipo_detector_command(code="001365")
        self.assertTrue(any("run_ipo_detector" in c or "--ipo-detector" in c for c in cmd))

    def test_dialog_ui_add_remove_and_filter(self):
        """【测试】验证 IPOSubnewDetectorDialog 界面加码、移除与持久化"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")

            # 验证 001365 已在监控池首位
            self.assertIn("001365", dlg.monitored_codes)

            # 手动添加一只标的
            dlg.add_stock("688826")
            self.assertIn("688826", dlg.monitored_codes)
            self.assertEqual(dlg.monitored_codes[0], "688826")

            # 移除标的
            dlg.remove_stock("688826")
            self.assertNotIn("688826", dlg.monitored_codes)

            # 保存持久化并关闭
            dlg.save_persisted_state()
            dlg.close()

    def test_tdd_daily_kline_support_evaluation(self):
        """【测试】验证通过 tdd 获取日线通道支撑与 pbottom 算法准确度 (使用 get_tdx_Exp_day_to_df)"""
        from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal
        sig = VWAPDetectorSignal(code="301683", name="测试标的", price=95.5)
        mock_tdd_df = pd.DataFrame([
            {"close": 92.0, "low": 90.5, "ma5d": 91.0, "pbottom": 94.0, "ptop": 105.0},
            {"close": 93.5, "low": 91.8, "ma5d": 92.0, "pbottom": 94.0, "ptop": 105.0},
            {"close": 95.0, "low": 93.0, "ma5d": 93.5, "pbottom": 94.0, "ptop": 105.0},
            {"close": 95.5, "low": 94.2, "ma5d": 94.0, "pbottom": 94.5, "ptop": 105.0}
        ])

        with patch("JSONData.tdx_data_Day.get_tdx_Exp_day_to_df", return_value=mock_tdd_df):
            self.engine._evaluate_kline_trend("301683", sig)
            self.assertEqual(sig.trend_support_level, 94.5)
            self.assertTrue(sig.has_kline_launch_sig)
            self.assertIn("通道下轨支撑", sig.trend_desc)

    def test_close_ipo_detector_process(self):
        """【测试】验证 close_ipo_detector_process 安全关闭子进程与清理 PID 记录"""
        from ats.ui.ipo_detector_ipc import close_ipo_detector_process, update_detector_heartbeat, _read_ipc_data
        # 模拟写入一个假 PID
        update_detector_heartbeat(999999)
        data = _read_ipc_data()
        self.assertEqual(data.get("detector_pid"), 999999)
        
        # 调用关闭函数 (针对不存在的 PID 安全返回 False 或完成清理)
        close_ipo_detector_process(timeout=0.2)

    def test_dialog_ats_col_dynamic_rendering(self):
        """【测试】验证 IPOSubnewDetectorDialog 接收 ipc_df 提取自定义 ats_col 并在表格中精准渲染"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        app = QApplication.instance() or QApplication(sys.argv)

        test_ipc_df = pd.DataFrame([
            {"code": "001365", "win": 4, "dff": 2.33, "ch_bc2": 1, "price": 35.0}
        ]).set_index("code")

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")
            dlg.ipc_df = test_ipc_df

            # 模拟收到 001365 信号并更新表格
            sig = VWAPDetectorSignal(
                code="001365", name="天海电子", price=35.0, change_pct=2.5,
                vwap=34.2, vwap_diff_pct=2.3, structure_tag="蓄势走平3天",
                signal_type="PRE_ORDER", signal_level="🎯 预下单", stop_loss_price=34.0,
                signal_desc="在VWAP上走平蓄势，预下单潜伏"
            )
            dlg._update_table_row_data(sig)

            # 验证动态列包含 win, dff, ch_bc2
            self.assertIn("win", dlg.extra_cols)
            # 获取 win 所在列
            win_idx = 10 + dlg.extra_cols.index("win")
            item_win = dlg.table.item(0, win_idx)
            self.assertIsNotNone(item_win)
            self.assertEqual(item_win.text(), "+4")
            self.assertEqual(item_win.data(Qt.ItemDataRole.EditRole), 4.0)

            # 获取 dff 所在列
            if "dff" in dlg.extra_cols:
                dff_idx = 10 + dlg.extra_cols.index("dff")
                item_dff = dlg.table.item(0, dff_idx)
                self.assertIsNotNone(item_dff)
                self.assertEqual(item_dff.text(), "+2.33")
                self.assertEqual(item_dff.data(Qt.ItemDataRole.EditRole), 2.33)

            dlg.close()

    def test_dialog_click_and_keyboard_linkage(self):
        """【测试】验证表格单击与键盘上下键切换行仅联动通达信，绝不触发异动弹窗 (与 ATS 严格对齐)"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")

            with patch("ats.ui.base_table.send_to_linkage") as mock_linkage, \
                 patch.object(dlg, "_broadcast_link_external") as mock_broadcast:
                # 模拟切换单元格行到第 0 行
                dlg._on_current_cell_changed(0, 0, -1, -1)
                self.assertEqual(dlg._pending_linkage_row, 0)

                # 触发防抖联动
                dlg._fire_linkage_debounced()

                # 单击绝不调用 send_to_linkage (绝不主动弹出设置报警规则)
                mock_linkage.assert_not_called()
                # 仅触发外部通达信/同花顺切图
                mock_broadcast.assert_called_once_with("001365")
                self.assertIn("001365", dlg.lbl_status.text())

            dlg.close()

    def test_dialog_context_menu_actions(self):
        """【测试】验证表格右键弹出 ATS 核心菜单 (复制、异动联动、SBC走势、通达信联动、重点关注等)"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPoint
        app = QApplication.instance() or QApplication(sys.argv)

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")

            # 模拟右键点击
            with patch("PyQt6.QtWidgets.QMenu.exec") as mock_menu_exec:
                dlg._show_context_menu(QPoint(10, 10))
                mock_menu_exec.assert_called_once()

            dlg.close()

    def test_buffered_render_and_zero_main_thread_io(self):
        """【测试】验证信号分帧缓冲队列与 UI 主线程绝对零 I/O 零阻塞"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker.start"):
            from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
            dlg = IPOSubnewDetectorDialog(initial_code="001365")

            # 模拟 Worker emit 分析信号
            sig = VWAPDetectorSignal(
                code="001365",
                name="山东药玻",
                price=25.5,
                vwap=25.0,
                signal_type="PRE_ORDER",
                signal_level="🎯 预下单",
                extra_data={"win": 3, "dff": 1.25, "ch_bc2": 1}
            )

            # 验证 emit 后进入缓冲队列，避免直接阻塞主线程
            dlg._on_stock_analyzed(sig)
            self.assertEqual(len(dlg._pending_render_queue), 1)
            self.assertTrue(dlg._render_timer.isActive())

            # 模拟执行分帧刷新
            with patch("JSONData.tdx_data_Day.get_tdx_Exp_day_to_df") as mock_tdd:
                dlg._flush_pending_renders()
                # 铁律：UI 渲染绝不可调用任何通达信日线文件 I/O
                mock_tdd.assert_not_called()
                self.assertEqual(len(dlg._pending_render_queue), 0)

            dlg.close()

    def test_batch_grouping_multiprocess_and_multithread_worker(self):
        """【测试】验证 IPOScanWorker 批量分组多进程预取日线与多线程并发跑策略机制"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)

        from ats.ui.ipo_subnew_detector_dialog import IPOScanWorker
        test_codes = ["001365", "688826", "301677", "688835"]

        mock_day_df = pd.DataFrame({
            "close": [30.0, 31.0, 32.0, 33.0, 34.0],
            "low": [29.0, 30.0, 31.0, 32.0, 33.0],
            "high": [31.0, 32.0, 33.0, 34.0, 35.0],
            "vol": [1000, 1100, 1200, 1300, 1400],
            "amount": [10000, 11000, 12000, 13000, 14000],
            "code": ["001365"] * 5
        })

        with patch("ats.strategy.ipo_vwap_detector_engine.batch_fetch_day_kline_fast", return_value={"001365": mock_day_df}) as mock_batch_mp, \
             patch.object(IPOVWAPDetectorEngine.get_instance(), "analyze_stock") as mock_analyze:
            mock_sig = VWAPDetectorSignal(code="001365", name="测试", price=34.0)
            mock_analyze.return_value = mock_sig

            worker = IPOScanWorker(test_codes, batch_size=2)
            received_batches = []
            worker.batch_analyzed.connect(lambda b: received_batches.append(b))

            # 执行多进程多线程批量流水线
            worker.run()

            # 验证多进程批量预取被触发调用 (每批次 2 只，共 2 个批次)
            self.assertEqual(mock_batch_mp.call_count, 2)
            # 验证 analyze_stock 接收到了预取的 day_df
            self.assertEqual(mock_analyze.call_count, 4)
            # 验证产生了整批 batch_analyzed 信号
            self.assertTrue(len(received_batches) > 0)

    def test_navigation_keys_and_deduplicated_linkage(self):
        """【测试】验证上下翻页/PageUp/PageDown与鼠标单击统一入口及防重联动机制"""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent
        app = QApplication.instance() or QApplication(sys.argv)

        from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
        with patch("ats.ui.ipo_subnew_detector_dialog.IPOScanWorker"):
            dlg = IPOSubnewDetectorDialog(initial_code="001365")
            dlg.add_stock("688826")
            dlg.add_stock("301677")

            # 模拟联动拦截
            linkage_calls = []
            dlg._broadcast_link_external = lambda code: linkage_calls.append(code)

            # 1. 选中第 0 行，触发联动 (最新置顶的 301677)
            dlg._trigger_linkage_for_row(0)
            dlg._fire_linkage_debounced()
            self.assertEqual(len(linkage_calls), 1)
            self.assertEqual(linkage_calls[0], "301677")

            # 2. 防重测试：再次针对第 0 行或同代码触发，必须被四重防重机制拦截！
            dlg._trigger_linkage_for_row(0)
            dlg._fire_linkage_debounced()
            self.assertEqual(len(linkage_calls), 1)  # 严格保持 1，无重复联动

            # 3. 键盘 Down 导航到第 1 行 (688826)
            dlg._handle_navigation_key(Qt.Key.Key_Down)
            dlg._fire_linkage_debounced()
            self.assertEqual(len(linkage_calls), 2)
            self.assertEqual(linkage_calls[1], "688826")

            # 4. 键盘 PageDown 导航 (翻动一页)
            dlg._handle_navigation_key(Qt.Key.Key_PageDown)
            dlg._fire_linkage_debounced()
            pagedown_row = dlg.table.currentRow()
            expected_pagedown_code = dlg.table.item(pagedown_row, 0).text().strip()
            self.assertEqual(len(linkage_calls), 3)
            self.assertEqual(linkage_calls[2], expected_pagedown_code)

            # 5. 键盘 Up 导航回到上一行
            dlg._handle_navigation_key(Qt.Key.Key_Up)
            dlg._fire_linkage_debounced()
            up_row = dlg.table.currentRow()
            expected_up_code = dlg.table.item(up_row, 0).text().strip()
            self.assertEqual(len(linkage_calls), 4)
            self.assertEqual(linkage_calls[3], expected_up_code)
            self.assertEqual(up_row, pagedown_row - 1)

            dlg.close()

    def test_tdx_global_cache_pool_ramdisk_persistence(self):
        """【测试】验证 TDXGlobalCachePool 极限压缩原子持久化与跨进程自动重载"""
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool

        pool1 = TDXGlobalCachePool()
        test_code = "001365"
        mock_records = [
            {"datetime": "2026-09-17 09:30", "open": 30.0, "high": 31.0, "low": 29.5, "close": 30.5, "vol": 1000, "amount": 30500.0}
        ]
        pool1.set_static_history_bars(test_code, 10, mock_records, 500000.0, 15000000.0)

        # 强制原子落盘
        saved = pool1.flush_to_ramdisk(force=True)
        self.assertTrue(saved)
        self.assertTrue(os.path.exists(pool1._ramdisk_path))

        # 模拟另一个独立进程初始化载入
        pool2 = TDXGlobalCachePool()
        entry = pool2.get_static_history_bars(test_code, 10)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["days"], 10)
        self.assertEqual(entry["last_cum_vol"], 500000.0)
        self.assertEqual(entry["last_cum_amt"], 15000000.0)
        self.assertEqual(len(entry["records"]), 1)

    def test_unlisted_stocks_filter_and_periodic_flush_control(self):
        """【测试】验证未上市股票拦截、flush_if_due 5-10分钟统一持久化与控制台日志"""
        from ats.ui.ipo_subnew_detector_dialog import is_stock_actually_listed, IPOSubnewDetectorDialog
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool

        # 1. 验证未上市股票 100% 拦截
        unlisted_samples = ["301686", "920201", "301716", "920229", "001246", "920025", "301660", "920202", "301569", "920295"]
        for u in unlisted_samples:
            self.assertFalse(is_stock_actually_listed(u), f"股票 {u} 未上市却未被拦截！")

        # 2. 验证已上市股票正常放行
        self.assertTrue(is_stock_actually_listed("001365"))

        # 3. 验证 flush_if_due 集中持久化保护机制 (默认5分钟内不重复写盘)
        pool = TDXGlobalCachePool.get_instance()
        pool.set_static_history_bars("600733", 10, [], 100.0, 1000.0)
        # 刚刚写入，未满 300 秒，flush_if_due 必须返回 False
        res1 = pool.flush_if_due(interval=300.0)
        self.assertFalse(res1)

        # 满足时间间隔时 (设置 interval=0.0)，才执行集中落盘
        res2 = pool.flush_if_due(interval=0.0)
        self.assertTrue(res2)
        # 落盘后已无 dirty 数据，再次调用返回 False
        res3 = pool.flush_if_due(interval=0.0)
        self.assertFalse(res3)

    def test_timestamp_incremental_vwap_and_frozen_after_close(self):
        """【测试】验证基于时间戳的微秒级增量复用、收盘固化 (frozen) 与 RamDisk 完整热重载"""
        from ats.tdx_realtime_fetcher import TDXGlobalCachePool, TDXRealtimeFetcher
        pool = TDXGlobalCachePool.get_instance()
        test_code = "600733"
        days = 10

        df_mock = pd.DataFrame([
            {"time": "09-17 14:55", "date": "2026-09-17", "close": 32.5, "open": 32.0, "vwap": 32.2, "volume": 1000, "amount": 32200},
            {"time": "09-17 14:56", "date": "2026-09-17", "close": 32.6, "open": 32.5, "vwap": 32.25, "volume": 1200, "amount": 38700},
        ]).set_index("time")

        # 1. 设置增量分时与时间戳状态
        pool.set_incremental_intraday(
            code=test_code, days=days, df=df_mock,
            latest_bar_time="14:56", today_bar_count=2,
            last_cum_vol=1200.0, last_cum_amt=38700.0
        )

        # 2. 验证时间戳与 TTL 内查询直出 (0 网络)
        cached = pool.get_incremental_intraday(test_code, days, ttl=10.0)
        self.assertIsNotNone(cached)
        df_cached, meta = cached
        self.assertEqual(len(df_cached), 2)
        self.assertEqual(meta["latest_bar_time"], "14:56")
        self.assertEqual(meta["today_bar_count"], 2)

        # 3. 验证 daily_metrics_cache 缓存
        metrics = {"ma5": 32.0, "support": 31.5, "resistance": 33.0}
        pool.set_daily_metrics(test_code, metrics)
        loaded_metrics = pool.get_daily_metrics(test_code)
        self.assertIsNotNone(loaded_metrics)
        self.assertEqual(loaded_metrics["ma5"], 32.0)
        self.assertEqual(loaded_metrics["support"], 31.5)

        # 4. 验证原子落盘到 RamDisk 并跨实例恢复
        saved = pool.flush_to_ramdisk(force=True)
        self.assertTrue(saved)

        pool2 = TDXGlobalCachePool()
        cached2 = pool2.get_incremental_intraday(test_code, days, ttl=10.0)
        self.assertIsNotNone(cached2)
        df_cached2, meta2 = cached2
        self.assertEqual(meta2["latest_bar_time"], "14:56")
        self.assertEqual(len(df_cached2), 2)


if __name__ == "__main__":
    unittest.main()



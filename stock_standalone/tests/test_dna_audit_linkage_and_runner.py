# -*- coding: utf-8 -*-
"""
tests/test_dna_audit_linkage_and_runner.py — DNA 特征审计多通道自愈联动与通用启动器测试套件
"""

import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

# 将项目根目录添加到系统路径以支持模块导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QWidget, QLineEdit
from PyQt6.QtCore import Qt

# 确保 QApplication 单例存在
app = QApplication.instance()
if not app:
    app = QApplication([])

from ats.ui.multi_period_dialog import QtDnaAuditReportWindow, run_dna_audit_batch_qt
from ats.ui.sector_detail_dialog import ATSSectorDetailDialog


class MockDnaSummary:
    """模拟 DNA 审计结果对象"""
    def __init__(self, code, name, score=88.5, total_pct=5.2, verdict="强劲多头", dna_tag="突破主升"):
        self.code = code
        self.name = name
        self.intent_score = score
        self.total_pct = total_pct
        self.verdict = verdict
        self.dna_tag = dna_tag
        self.history = [{'dff2': 10, 'dff3': 20, 'Rank': 1}]
        self.suggestions = ["量价齐升，主力持续大额净流入", "多周期共振向上突破"]
        self.indicators = {}
        self.custom_metrics = {'dff2': 10, 'dff3': 20, 'Rank': 1}


class TestDnaAuditLinkageAndRunner(unittest.TestCase):

    def setUp(self):
        self.code_to_name = {"600000": "浦发银行", "000001": "平安银行"}
        self.summaries = [
            MockDnaSummary("600000", "浦发银行", score=92.0, total_pct=3.5, verdict="突破主升"),
            MockDnaSummary("000001", "平安银行", score=85.0, total_pct=-1.2, verdict="回踩确认")
        ]

    def test_01_window_creation_and_fill(self):
        """测试 QtDnaAuditReportWindow 独立窗口创建、数据填充与表格行数"""
        win = QtDnaAuditReportWindow(
            self.summaries,
            parent=None,
            code_to_name=self.code_to_name,
            custom_cols=['dff2', 'dff3', 'Rank']
        )
        try:
            self.assertEqual(win.table.rowCount(), 2)
            # 排序根据 score 降序：第0行应为 600000
            self.assertEqual(win.table.item(0, 0).text(), "600000")
            self.assertEqual(win.table.item(0, 1).text(), "浦发银行")
            self.assertEqual(win.table.item(1, 0).text(), "000001")
            self.assertEqual(win.table.item(1, 1).text(), "平安银行")
        finally:
            win.close()

    def test_02_keyboard_stock_activated_linkage(self):
        """测试键盘上下键触发 BaseATSTableWidget.stock_activated 必须 100% 触发 link_stock"""
        win = QtDnaAuditReportWindow(
            self.summaries,
            parent=None,
            code_to_name=self.code_to_name
        )
        try:
            with patch.object(win, 'link_stock') as mock_link:
                # 模拟 BaseATSTableWidget 键盘上下键发射 stock_activated 信号
                win.table.stock_activated.emit("600000", "浦发银行")
                mock_link.assert_called_once_with("600000", "浦发银行")
        finally:
            win.close()

    def test_03_multichannel_linkage_parent_cascade(self):
        """测试 link_stock 级联多通道自愈体系：优先父级 link_stock 或 linkage_cb"""
        # Case A: parent 具有 link_stock
        mock_parent = MagicMock()
        win1 = QtDnaAuditReportWindow(self.summaries, parent=mock_parent)
        try:
            win1.link_stock("600000", "浦发银行", force=True)
            mock_parent.link_stock.assert_called_with("600000", "浦发银行")
        finally:
            win1.close()

        # Case B: parent 具有 linkage_cb
        mock_parent_cb = MagicMock(spec=['linkage_cb'])
        mock_parent_cb.linkage_cb = MagicMock()
        win2 = QtDnaAuditReportWindow(self.summaries, parent=mock_parent_cb)
        try:
            win2.link_stock("000001", "平安银行", force=True)
            mock_parent_cb.linkage_cb.assert_called_with("000001", "平安银行")
        finally:
            win2.close()

    def test_04_fallback_direct_terminal_and_socket(self):
        """测试当 parent 为 None 且无全局主窗口时，兜底直接向 link_manager 和 socket 26668 发送指令"""
        win = QtDnaAuditReportWindow(self.summaries, parent=None)
        try:
            with patch('linkage_service.get_link_manager') as mock_get_lm, \
                 patch('socket.socket') as mock_sock_cls:
                mock_lm = MagicMock()
                mock_get_lm.return_value = mock_lm
                mock_sock = MagicMock()
                mock_sock_cls.return_value.__enter__.return_value = mock_sock

                win.link_stock("600000", "浦发银行", force=True)

                # 验证兜底直接向通达信终端 push
                mock_lm.push.assert_called_with("600000", flags={'tdx': True, 'ths': False, 'dfcf': False})
                # 验证向 26668 socket 发送 CODE|600000
                mock_sock.connect.assert_called_with(('127.0.0.1', 26668))
                mock_sock.sendall.assert_called_with(b"CODE|600000")
        finally:
            win.close()

    def test_05_mouse_cell_click_and_diag_autofill(self):
        """测试单元格点击：第0列点击联动并自动回填父级诊断框"""
        parent_widget = QWidget()
        diag_input = QLineEdit(parent_widget)
        parent_widget.diag_edit = diag_input

        win = QtDnaAuditReportWindow(self.summaries, parent=parent_widget)
        try:
            with patch.object(win, 'link_stock') as mock_link:
                # 点击第0行第0列 (600000)
                win._on_cell_clicked(0, 0)
                mock_link.assert_called_with("600000", "浦发银行", force=True)
                self.assertEqual(diag_input.text(), "600000")
        finally:
            win.close()
            parent_widget.close()

    def test_06_double_click_sbc_and_link(self):
        """测试双击行：触发 link_stock 并且调出 open_sbc_chart_dialog"""
        win = QtDnaAuditReportWindow(self.summaries, parent=None)
        try:
            with patch.object(win, 'link_stock') as mock_link, \
                 patch('ats.ui.intraday_strategy_dialog.open_sbc_chart_dialog') as mock_sbc:
                item = win.table.item(0, 0)
                win._on_item_double_clicked(item)
                mock_link.assert_called_with("600000", "浦发银行", force=True)
                mock_sbc.assert_called_once_with(win, "600000")
        finally:
            win.close()

    def test_07_debounce_same_code_and_allow_different(self):
        """测试防抖：相同代码瞬时防抖，不同代码立即触发"""
        win = QtDnaAuditReportWindow(self.summaries, parent=None)
        try:
            with patch.object(win, '_post_link_actions') as mock_post:
                # 第一次触发 600000
                win.link_stock("600000", "浦发银行")
                self.assertEqual(mock_post.call_count, 1)

                # 瞬时再次触发相同 600000 (被 50ms/200ms 防抖拦截)
                win.link_stock("600000", "浦发银行")
                self.assertEqual(mock_post.call_count, 1)

                # 触发不同股票 000001 (立即执行)
                win.link_stock("000001", "平安银行")
                self.assertEqual(mock_post.call_count, 2)
        finally:
            win.close()

    def test_08_window_reuse_update_report(self):
        """测试 update_report 原地平滑更新报告数据，不销毁不重置视窗"""
        win = QtDnaAuditReportWindow(self.summaries, parent=None)
        try:
            new_sums = [
                MockDnaSummary("002415", "海康威视", score=95.0, total_pct=6.8, verdict="领涨龙头")
            ]
            win.update_report(new_sums, end_date="2026-09-14", resample='w')
            self.assertEqual(win.table.rowCount(), 1)
            self.assertEqual(win.table.item(0, 0).text(), "002415")
            self.assertIn("海康威视", win.windowTitle())
            self.assertIn("2026-09-14", win.windowTitle())
        finally:
            win.close()

    def test_09_run_dna_audit_batch_qt_runner_and_reuse(self):
        """测试统一启动器 run_dna_audit_batch_qt 首次创建与二次平滑复用"""
        parent_win = QWidget()
        try:
            with patch('backtest_feature_auditor.audit_multiple_codes') as mock_audit:
                mock_audit.return_value = self.summaries
                
                # 首次调用：创建新窗口并挂载在 parent_win._dna_audit_win
                win1 = run_dna_audit_batch_qt(
                    {"600000": "浦发银行", "000001": "平安银行"},
                    parent=parent_win
                )
                self.assertIsNotNone(win1)
                self.assertIs(parent_win._dna_audit_win, win1)
                self.assertEqual(win1.table.rowCount(), 2)

                # 二次调用：平滑复用 win1，调用 update_report
                new_sums = [MockDnaSummary("000002", "万科A", score=90.0, total_pct=4.1)]
                mock_audit.return_value = new_sums

                win2 = run_dna_audit_batch_qt(
                    {"000002": "万科A"},
                    parent=parent_win
                )
                self.assertIs(win2, win1)  # 必须是同一对象实例 (原地复用)
                self.assertEqual(win2.table.rowCount(), 1)
                self.assertEqual(win2.table.item(0, 0).text(), "000002")
                win1.close()
        finally:
            parent_win.close()

    def test_10_sector_detail_dialog_link_stock_and_dna_audit(self):
        """测试 ATSSectorDetailDialog.link_stock 代理及 _run_dna_audit 接入通用启动器"""
        mock_parent = MagicMock()
        dialog = ATSSectorDetailDialog("半导体", parent=mock_parent)
        try:
            # 1. 验证 link_stock 正确代理至 parent
            dialog.link_stock("688981", "中芯国际")
            mock_parent.link_stock.assert_called_with("688981", "中芯国际")

            # 2. 验证 _run_dna_audit 统一调用 run_dna_audit_batch_qt
            with patch('ats.ui.multi_period_dialog.run_dna_audit_batch_qt') as mock_qt_runner:
                mock_qt_runner.return_value = MagicMock()
                # 预设表格中有数据
                dialog.table.setRowCount(1)
                dialog.table.setItem(0, 0, MagicMock(text=lambda: "688981"))
                dialog.table.setItem(0, 1, MagicMock(text=lambda: "中芯国际"))

                dialog._run_dna_audit()
                self.assertTrue(mock_qt_runner.called)
                args, kwargs = mock_qt_runner.call_args
                # 第一个参数字典中应包含 688981
                self.assertIn("688981", args[0])
                self.assertIs(kwargs.get('parent'), dialog)
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()

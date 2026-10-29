# -*- coding: utf-8 -*-
"""
自动化测试：验证手工平仓原子清退、一键全平、全自动交易配置持久化、超大日志归档保护与全链路决策流水落盘
"""
import os
import sys
import unittest
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestManualCloseAndAutoTrading(unittest.TestCase):
    def test_trade_gateway_manual_sell_bypass_hours(self):
        """测试老网关在盘后执行手工平仓时能够豁免交易时段检查成功卖出"""
        from trade_gateway import TradeGateway, Position
        gw = TradeGateway(total_capital=100000.0)
        gw._positions["000001"] = Position(
            code="000001", name="平安银行", sector="金融",
            entry_price=10.0, entry_time=datetime.now(),
            shares=1000, position_value=10000.0, strategy_tag="测试",
            stop_loss=9.5, current_price=10.5
        )
        # 执行手工平仓 (带 force_manual=True)
        ok, msg = gw.submit_sell("000001", 11.0, reason="操盘手手动平仓", force_manual=True)
        self.assertTrue(ok, f"手工平仓应成功，但返回: {msg}")
        self.assertNotIn("000001", gw._positions)

    def test_paper_adapter_manual_sell_bypass_reconciliation_block(self):
        """测试新交易内核在处于对账阻断状态下，手工平仓仍能成功执行"""
        from trading_kernel.execution.paper_adapter import PaperExecutionAdapter, ApprovedOrder, Position
        adapter = PaperExecutionAdapter(initial_capital=50000.0)
        adapter.account.positions["600000"] = Position(
            code="600000", entry_price=8.0, volume=1000, current_price=8.5,
            entry_time="2026-10-28 10:00:00"
        )
        # 模拟对账失败被锁死
        adapter._execution_block_reason = "RESTORE_RECONCILIATION_FAILED:MOCK_ERROR"

        # 构造手工平仓订单 (带 MANUAL 前缀)
        order = ApprovedOrder(
            order_id="MANUAL_SELL_600000",
            code="600000",
            action="SELL",
            size_pct=0.0,
            price=8.5,
            stop_price=None,
            request_id="MANUAL_REQ_600000"
        )
        result = adapter.submit_order(order)
        self.assertTrue(result, "手工平仓在阻断状态下应被放行并返回 True")
        self.assertNotIn("600000", adapter.account.positions)

    def test_ipo_trading_center_force_close_and_close_all(self):
        """测试集中交易指挥中心的 force_close_position 与 close_all_positions"""
        from ats.strategy.ipo_trading_center import IPOTradingCenter, IPOTradingPosition
        center = IPOTradingCenter(total_capital=100000.0)
        center.available_cash = 20000.0
        # 添加 2 只持仓
        center._positions["002667"] = IPOTradingPosition(
            code="002667", name="ST威领", shares=500, available_shares=500,
            cost_price=10.0, current_price=20.0, entry_time="2026-10-28 09:30:00",
            entry_date="2026-10-28", entry_reason="打板", signal_tier="S"
        )
        center._positions["688293"] = IPOTradingPosition(
            code="688293", name="奥浦迈", shares=500, available_shares=500,
            cost_price=50.0, current_price=60.0, entry_time="2026-10-28 09:30:00",
            entry_date="2026-10-28", entry_reason="主升", signal_tier="S"
        )

        # 单个平仓
        ok1 = center.force_close_position("002667", price=20.0, reason="操盘手手动平仓")
        self.assertTrue(ok1)
        self.assertNotIn("002667", center._positions)
        self.assertEqual(len(center._closed_positions), 1)
        self.assertEqual(center.available_cash, 20000.0 + 500 * 20.0)

        # 一键全平剩余持仓
        closed_cnt = center.close_all_positions(reason="操盘手一键全平")
        self.assertEqual(closed_cnt, 1)
        self.assertEqual(len(center._positions), 0)
        self.assertEqual(len(center._closed_positions), 2)
        self.assertEqual(center.available_cash, 30000.0 + 500 * 60.0)

    def test_atomic_sell_position_core_no_attribute_error(self):
        """测试 DecisionFlowPanel._atomic_sell_position_core 不再抛出 '_noop_context' 异常"""
        from tk_gui_modules.decision_flow_panel import DecisionFlowPanel
        from trading_kernel.kernel_service import get_kernel_service
        from trading_kernel.execution.paper_adapter import Position

        service = get_kernel_service()
        if service and service.paper_adapter and service.paper_adapter.account:
            service.paper_adapter.account.positions["002808"] = Position(
                code="002808", entry_price=15.0, volume=500, current_price=16.0,
                entry_time="2026-10-28 10:00:00"
            )

        # 模拟调用 DecisionFlowPanel._atomic_sell_position_core
        panel = DecisionFlowPanel.__new__(DecisionFlowPanel)
        panel.parent_app = None

        price = panel._atomic_sell_position_core("002808", "恒久科技", reason="测试原子平仓")
        self.assertGreater(price, 0)
        # 验证持仓已成功出清
        if service and service.paper_adapter and service.paper_adapter.account:
            self.assertNotIn("002808", service.paper_adapter.account.positions)

    def test_linkage_storage_large_file_archive_no_runtime_error(self):
        """测试超大日志文件归档不再抛出 RuntimeError 崩溃"""
        import tempfile
        from pathlib import Path
        from linkage_storage import _archive_one

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            runtime_dir = tmp_path / "runtime"
            archive_dir = tmp_path / "archive"
            runtime_dir.mkdir()
            archive_dir.mkdir()

            # 创建一个超过限制的大文件
            large_file = runtime_dir / "instock_tk.log"
            with open(large_file, "wb") as f:
                f.write(b"x" * (120 * 1024))

            target_archive_file = archive_dir / "instock_tk.log"
            # 执行归档，传入限制 100KB，不应抛出异常
            _archive_one(large_file, target_archive_file, file_limit=100 * 1024)
            self.assertTrue(target_archive_file.exists())
            self.assertEqual(target_archive_file.stat().st_size, 100 * 1024)

    def test_auto_trade_config_persistence(self):
        """测试全自动跟随交易配置能够正常写入和读取持久化配置"""
        from ats.ui.styles import load_config_node, save_config_node
        # 写入 True
        save_config_node("ipo_cmd_auto_follow_trading", True)
        self.assertTrue(load_config_node("ipo_cmd_auto_follow_trading", False))
        # 写入 False
        save_config_node("ipo_cmd_auto_follow_trading", False)
        self.assertFalse(load_config_node("ipo_cmd_auto_follow_trading", True))


if __name__ == "__main__":
    unittest.main()

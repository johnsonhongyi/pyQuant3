from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.paper_adapter import PaperExecutionAdapter


def test_paper_trading_complete_cycle() -> None:
    """测试模拟交易的完整生命周期: 买入 -> 价格上涨/浮盈计算 -> 平仓变现"""
    # 1. 基础初始化
    initial_cash = 1000000.0
    adapter = PaperExecutionAdapter(initial_capital=initial_cash)
    
    # 验证初始状态
    acct = adapter.get_account_snapshot()
    assert acct["cash"] == initial_cash
    assert acct["total_equity"] == initial_cash
    assert acct["total_pnl"] == 0.0
    assert acct["total_pnl_pct"] == 0.0
    assert len(adapter.get_positions()) == 0

    # 2. 模拟 BUY (买入 30% 仓位，价格为 10.0 元)
    buy_order = ApprovedOrder(
        order_id="order_buy_001",
        code="600000",
        action="BUY",
        size_pct=0.30,
        price=10.0,
        stop_price=9.8,
    )
    
    success = adapter.submit_order(buy_order)
    assert success is True

    # 验证买入后资金与持仓变化
    positions = adapter.get_positions()
    acct = adapter.get_account_snapshot()
    
    assert "600000" in positions
    pos = positions["600000"]
    assert pos["entry_price"] == 10.0
    assert pos["volume"] == 30000.0  # 100万 * 30% / 10 = 30000 股
    assert pos["market_value"] == 300000.0
    assert acct["cash"] == 700000.0  # 100万可用现金 - 30万开仓资金
    assert acct["total_equity"] == 1000000.0  # 70万现金 + 30万市值

    # 3. 价格变动 (涨至 12.0 元，计算浮盈与市值扩张)
    adapter.update_market_price("600000", 12.0)
    
    positions = adapter.get_positions()
    pos = positions["600000"]
    acct = adapter.get_account_snapshot()
    
    assert pos["current_price"] == 12.0
    assert pos["market_value"] == 360000.0  # 30000 股 * 12.0 = 36万
    assert pos["pnl"] == 60000.0  # 浮盈 6 万
    assert pos["pnl_pct"] == 20.0  # 盈亏率 +20%
    assert acct["total_equity"] == 1060000.0  # 70万现金 + 36万市值
    assert acct["total_pnl"] == 60000.0
    assert acct["total_pnl_pct"] == 6.0  # 整体账户资产获利 6%

    # 4. 加仓 ADD (以 12.0 元加仓 10% 仓位)
    add_order = ApprovedOrder(
        order_id="order_add_002",
        code="600000",
        action="ADD",
        size_pct=0.10,
        price=12.0,
        stop_price=11.7,
    )
    
    success = adapter.submit_order(add_order)
    assert success is True

    # 账户总权益 106万 * 10% = 10.6万。
    # 加仓股数 = 10.6万 / 12.0 = 8833.3333 股。
    # 扣减现金 10.6万，剩余现金 = 70万 - 10.6万 = 59.4万。
    positions = adapter.get_positions()
    pos = positions["600000"]
    acct = adapter.get_account_snapshot()
    
    assert abs(acct["cash"] - 594000.0) < 1.0
    assert abs(pos["volume"] - 38833.33) < 1.0
    
    # 5. 平仓 SELL (以 13.0 元全平仓位)
    # 将最新价更新至 13.0 元
    adapter.update_market_price("600000", 13.0)
    
    sell_order = ApprovedOrder(
        order_id="order_sell_003",
        code="600000",
        action="SELL",
        size_pct=1.0,
        price=13.0,
        stop_price=None,
    )
    
    success = adapter.submit_order(sell_order)
    assert success is True

    # 验证平仓后，持仓清空，现金全部回流
    positions = adapter.get_positions()
    acct = adapter.get_account_snapshot()
    
    assert "600000" not in positions
    assert len(positions) == 0
    # 平仓后最终现金应当大于 100 万，即本金加实现收益
    assert acct["cash"] == acct["total_equity"]
    assert acct["cash"] > initial_cash
    assert len(adapter.orders) == 3

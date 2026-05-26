from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.execution_adapter import ExecutionAdapter


@dataclass
class Position:
    """个股持仓明细"""
    code: str
    entry_price: float
    volume: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.volume * self.current_price

    @property
    def pnl(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) * self.volume

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "entry_price": round(self.entry_price, 4),
            "volume": round(self.volume, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 4),
            "pnl": round(self.pnl, 4),
            "pnl_pct": round(self.pnl_pct, 4),
        }


@dataclass
class AccountSnapshot:
    """账户资产与资金快照"""
    cash: float
    initial_capital: float = 1000000.0
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def total_equity(self) -> float:
        pos_value = sum(p.market_value for p in self.positions.values())
        return self.cash + pos_value

    @property
    def total_pnl(self) -> float:
        return self.total_equity - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_capital <= 0:
            return 0.0
        return self.total_pnl / self.initial_capital * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": round(self.cash, 4),
            "total_equity": round(self.total_equity, 4),
            "total_pnl": round(self.total_pnl, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
        }


class PaperExecutionAdapter(ExecutionAdapter):
    """Paper Trading 确定性模拟执行适配器"""

    def __init__(self, initial_capital: float = 1000000.0) -> None:
        self.initial_capital = initial_capital
        self.account = AccountSnapshot(cash=initial_capital, initial_capital=initial_capital)
        self.orders: list[dict[str, Any]] = []
        
        # 探测测试环境与物理持久化路径
        import os
        self._is_test = "PYTEST_CURRENT_TEST" in os.environ
        try:
            from sys_utils import get_base_path
            base_dir = get_base_path()
        except ImportError:
            base_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self._state_file = os.path.join(base_dir, "logs", "paper_account_state.json")
        
        self._load_state()

    def _load_state(self) -> None:
        if self._is_test:
            return
        import os
        import json
        if os.path.exists(self._state_file) and os.path.getsize(self._state_file) > 0:
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.initial_capital = float(data.get("initial_capital", self.initial_capital))
                cash = float(data.get("cash", self.initial_capital))
                
                positions = {}
                for code, pos_data in data.get("positions", {}).items():
                    entry_p = float(pos_data.get("entry_price", 0.0))
                    positions[code] = Position(
                        code=pos_data.get("code", code),
                        entry_price=entry_p,
                        volume=float(pos_data.get("volume", 0.0)),
                        current_price=float(pos_data.get("current_price", entry_p))
                    )
                self.orders = list(data.get("orders", []))
                
                # 自愈与热启动机制：从 orders 历史流水中干跑还原出一份“理论持仓”以自动修复任何数据异常
                recon_positions = {}
                recon_cash = self.initial_capital
                if self.orders:
                    try:
                        sorted_orders = sorted(self.orders, key=lambda x: x.get("timestamp", ""))
                        for o in sorted_orders:
                            c = o.get("code")
                            act = o.get("action", "").upper()
                            p = float(o.get("price", 0.0))
                            vol = float(o.get("volume", 0.0))
                            if not c or p <= 0 or vol <= 0:
                                continue
                            
                            if act in {"BUY", "ADD"}:
                                recon_cash -= p * vol
                                if c in recon_positions:
                                    pos = recon_positions[c]
                                    new_vol = pos.volume + vol
                                    new_entry = ((pos.entry_price * pos.volume) + (p * vol)) / new_vol
                                    pos.volume = new_vol
                                    pos.entry_price = new_entry
                                    pos.current_price = p
                                else:
                                    recon_positions[c] = Position(
                                        code=c,
                                        entry_price=p,
                                        volume=vol,
                                        current_price=p
                                    )
                            elif act in {"SELL", "REDUCE"}:
                                recon_cash += p * vol
                                if c in recon_positions:
                                    pos = recon_positions[c]
                                    if act == "SELL" or vol >= pos.volume:
                                        recon_positions.pop(c, None)
                                    else:
                                        pos.volume -= vol
                                        pos.current_price = p
                    except Exception:
                        pass
                
                # 数据异常自动检测与自愈修复：
                # 如果 1) 载入的 positions 为空但理论持仓不为空
                # 或 2) 载入的 positions 数量/代码与理论持仓不一致
                # 我们自动用理论持仓及现金进行覆盖修复，确保数据绝对一致！
                need_heal = False
                if not positions and recon_positions:
                    need_heal = True
                elif len(positions) != len(recon_positions):
                    need_heal = True
                else:
                    for c_code in recon_positions:
                        if c_code not in positions:
                            need_heal = True
                            break
                        if abs(positions[c_code].volume - recon_positions[c_code].volume) > 0.1:
                            need_heal = True
                            break
                
                if need_heal:
                    positions = recon_positions
                    if recon_cash > 0:
                        cash = recon_cash
                    import logging
                    logger = logging.getLogger("PaperExecutionAdapter")
                    logger.info(f"[Self-Healing] Automatically repaired {len(positions)} abnormal positions from orders ledger.")
                
                self.account = AccountSnapshot(cash=cash, initial_capital=self.initial_capital, positions=positions)
            except Exception:
                pass

    def _save_state(self) -> None:
        if self._is_test:
            return
        import os
        import json
        try:
            directory = os.path.dirname(self._state_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            positions_data = {
                code: {
                    "code": pos.code,
                    "entry_price": pos.entry_price,
                    "volume": pos.volume,
                    "current_price": pos.current_price
                }
                for code, pos in self.account.positions.items()
            }
            data = {
                "initial_capital": self.initial_capital,
                "cash": self.account.cash,
                "positions": positions_data,
                "orders": self.orders
            }
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def submit_order(self, order: ApprovedOrder) -> bool:
        if order.size_pct <= 0 or order.price <= 0:
            return False

        action = order.action.upper()
        code = order.code
        price = order.price

        # 当前总资产（用于确定下单绝对金额大小）
        equity = self.account.total_equity

        if action in {"BUY", "ADD"}:
            # 计算开仓金额
            target_value = equity * order.size_pct
            # 如果可用现金不足，进行最大可用资金扣减 (防止穿仓)
            if target_value > self.account.cash:
                target_value = self.account.cash

            if target_value <= 0:
                return False

            volume = target_value / price
            self.account.cash -= target_value

            # 更新仓位账簿
            if code in self.account.positions:
                pos = self.account.positions[code]
                # 计算均价加仓
                new_volume = pos.volume + volume
                new_entry = ((pos.entry_price * pos.volume) + (price * volume)) / new_volume
                pos.volume = new_volume
                pos.entry_price = new_entry
                pos.current_price = price
            else:
                self.account.positions[code] = Position(
                    code=code,
                    entry_price=price,
                    volume=volume,
                    current_price=price,
                )

        elif action in {"SELL", "REDUCE"}:
            if code not in self.account.positions:
                return False

            pos = self.account.positions[code]
            if action == "SELL":
                # 全平仓位
                sell_volume = pos.volume
            else:
                # 减仓一部分
                sell_volume = pos.volume * order.size_pct

            if sell_volume <= 0:
                return False

            cash_returned = sell_volume * price
            self.account.cash += cash_returned
            
            # 更新/移除仓位
            if action == "SELL" or sell_volume >= pos.volume:
                self.account.positions.pop(code)
            else:
                pos.volume -= sell_volume
                pos.current_price = price

        else:
            return False

        # 记录成交单
        self.orders.append({
            "order_id": order.order_id,
            "code": code,
            "action": action,
            "price": round(price, 4),
            "size_pct": round(order.size_pct, 4),
            "volume": round(sell_volume if action in {"SELL", "REDUCE"} else volume, 4),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_state()
        return True

    def cancel_order(self, order_id: str) -> bool:
        # 模拟盘挂单即成，所以撤单默认为 False/忽略
        return False

    def update_market_price(self, code: str, price: float) -> None:
        """更新个股的实时市场价格以计算浮动盈亏"""
        if code in self.account.positions:
            self.account.positions[code].current_price = price

    def get_positions(self) -> dict[str, dict[str, Any]]:
        return {code: pos.to_dict() for code, pos in self.account.positions.items()}

    def get_account_snapshot(self) -> dict[str, Any]:
        return self.account.to_dict()

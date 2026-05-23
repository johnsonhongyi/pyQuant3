from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from trading_kernel.core.risk import ApprovedOrder


class ExecutionAdapter(ABC):
    """交易执行适配器抽象基类 (Dependency Inversion)"""

    @abstractmethod
    def submit_order(self, order: ApprovedOrder) -> bool:
        """提交通过风控评估的获批订单"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤回挂单"""
        pass

    @abstractmethod
    def get_positions(self) -> dict[str, Any]:
        """获取仓位明细"""
        pass

    @abstractmethod
    def get_account_snapshot(self) -> dict[str, Any]:
        """获取账户快照"""
        pass

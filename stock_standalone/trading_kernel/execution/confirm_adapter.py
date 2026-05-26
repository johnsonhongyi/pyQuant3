# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable
from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.execution_adapter import ExecutionAdapter
from trading_kernel.observability.journal import JsonlJournal


class ConfirmExecutionAdapter(ExecutionAdapter):
    """人工确认装饰器适配器 (Phase 7: Human Confirmation Mode)
    
    当处于 CONFIRM 模式时，提交的获批订单不会直接发送至底层 Adapter 执行，
    而是分发给 UI 回调挂件。操盘手可确认、拒绝，或者直接修改下单比例。
    所有的手动干预行为均以 override_metadata 的形式严格记录在 Journal 账簿中，
    实现 100% 可追溯性与幂等回放。
    """

    def __init__(
        self,
        underlying_adapter: ExecutionAdapter,
        journal: JsonlJournal | None = None,
        mode: str = "CONFIRM",  # CONFIRM 或 AUTO
        timeout_seconds: float = 15.0,  # 倒计时秒数，超时自动拒绝
    ) -> None:
        self.underlying_adapter = underlying_adapter
        self.journal = journal
        self._mode = mode
        self.timeout_seconds = timeout_seconds
        
        # 确认回调函数：(order) -> dict[str, Any]
        # 回调函数返回确认结果，格式如：
        # {
        #     "confirmed": True/False,
        #     "size_pct_override": float or None, (手动修改的比例，None 表示采用原比例)
        #     "override_reason": str or None,
        # }
        self._confirm_callback: Callable[[ApprovedOrder], dict[str, Any]] | None = None

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, new_mode: str) -> None:
        if new_mode.upper() in {"CONFIRM", "AUTO"}:
            self._mode = new_mode.upper()

    def set_confirm_callback(self, callback: Callable[[ApprovedOrder], dict[str, Any]]) -> None:
        """注册人工确认弹窗/挂载回调"""
        self._confirm_callback = callback

    def submit_order(self, order: ApprovedOrder) -> bool:
        if self._mode == "AUTO":
            # 全自动模式下直接投递给底层
            return self.underlying_adapter.submit_order(order)

        # 处于 CONFIRM 人明确认模式
        if not self._confirm_callback:
            # 如果未挂载确认回调，为了交易安全，默认视为拒绝，防止由于静默导致假单漏洞
            self._log_override(order, confirmed=False, reason="NO_CONFIRM_CALLBACK_REGISTERED")
            return False

        try:
            # 唤起人工确认流
            res = self._confirm_callback(order)
            confirmed = res.get("confirmed", False)
            size_override = res.get("size_pct_override", None)
            reason = res.get("override_reason", "User Manual Confirmation")

            if not confirmed:
                # 操盘手物理拒绝或超时应答
                self._log_override(order, confirmed=False, reason=reason)
                return False

            # 操盘手物理确认同意
            actual_order = order
            override_meta = None

            if size_override is not None and size_override != order.size_pct:
                # 发生了下单占比的手工修改 (Override Size)
                # 在不修改 DecisionIntent 内核模型的前提下，基于新尺寸重构 ApprovedOrder 送入底层执行
                override_meta = {
                    "original_size_pct": order.size_pct,
                    "actual_size_pct": size_override,
                    "size_changed": True,
                }
                actual_order = ApprovedOrder(
                    order_id=f"{order.order_id}-override",
                    code=order.code,
                    action=order.action,
                    size_pct=size_override,
                    price=order.price,
                    stop_price=order.stop_price,
                )
            
            # 物理投递执行
            success = self.underlying_adapter.submit_order(actual_order)
            
            if success:
                self._log_override(
                    order, 
                    confirmed=True, 
                    reason=reason, 
                    override_meta=override_meta,
                    override_order_id=actual_order.order_id if override_meta else None
                )
            return success

        except Exception as e:
            # 异常情况下，安全起见默认阻断，并详细记录
            self._log_override(order, confirmed=False, reason=f"CONFIRMATION_EXCEPTION: {str(e)}")
            return False

    def cancel_order(self, order_id: str) -> bool:
        return self.underlying_adapter.cancel_order(order_id)

    def get_positions(self) -> dict[str, Any]:
        return self.underlying_adapter.get_positions()

    def get_account_snapshot(self) -> dict[str, Any]:
        return self.underlying_adapter.get_account_snapshot()

    def _log_override(
        self,
        original_order: ApprovedOrder,
        confirmed: bool,
        reason: str,
        override_meta: dict[str, Any] | None = None,
        override_order_id: str | None = None,
    ) -> None:
        """将人工确认/覆盖修改审计细节严格追加到 Journal 账簿中"""
        if not self.journal:
            return

        audit_record = {
            "journal_type": "HUMAN_CONFIRMATION_AUDIT",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "original_order": {
                "order_id": original_order.order_id,
                "code": original_order.code,
                "action": original_order.action,
                "size_pct": original_order.size_pct,
                "price": original_order.price,
                "stop_price": original_order.stop_price,
            },
            "confirmed": confirmed,
            "override_reason": reason,
            "override_metadata": override_meta or {},
            "actual_order_id": override_order_id or original_order.order_id,
        }
        self.journal.append(audit_record)

# -*- coding: utf-8 -*-
"""
ats/network/tk_ipc_subscriber.py
---------------------------------
TK 实时行情与策略信号流式订阅客户端
基于系统统一 IPC 协议与 IPCSyncManager，支持全量快照 (UPDATE_DF_ALL) 与极速增量 (UPDATE_DF_DIFF) 自动合并。
- 适用于新股次新检测工具、集中交易指挥室与 ATS 各子系统；
- 遵循 DRY/KISS/SOLID 原则，零重复开发，极致轻量与线程安全。
"""

import logging
from typing import Optional, Callable, Any
import pandas as pd

from ipc_sync_manager import (
    IPCSyncManager,
    PORT_VISUALIZER,
    PORT_ATS_TERMINAL,
    PORT_MULTI_PERIOD,
    PORT_IPO_DETECTOR,
    FALLBACK_PORTS_MAP,
)

logger = logging.getLogger("TKIPCSubscriber")


class TKIPCSubscriber(IPCSyncManager):
    """
    量化系统标准流式数据订阅者
    - 针对新股次新检测工具、指挥室与 ATS 子组件开箱即用；
    - 支持全量快照初始拉取与常态增量变动广播推送；
    - 线程安全原地合入，自动自愈与握手注册。
    """
    def __init__(
        self,
        port: int = PORT_IPO_DETECTOR,
        service_name: str = "ipo_detector",
        data_callback: Optional[Callable[[pd.DataFrame], None]] = None,
        custom_logger: Optional[Any] = None,
        auto_start: bool = True
    ):
        super().__init__(
            port=port,
            service_name=service_name,
            data_callback=data_callback,
            logger=custom_logger or logger,
            silent_bind_fail=False
        )
        if auto_start:
            self.start()


_GLOBAL_IPO_SUBSCRIBER: Optional[TKIPCSubscriber] = None


def get_ipo_ipc_subscriber(
    data_callback: Optional[Callable[[pd.DataFrame], None]] = None,
    auto_start: bool = True
) -> TKIPCSubscriber:
    """获取新股检测与指挥室专用的全局单例 IPC 订阅器"""
    global _GLOBAL_IPO_SUBSCRIBER
    if _GLOBAL_IPO_SUBSCRIBER is None:
        _GLOBAL_IPO_SUBSCRIBER = TKIPCSubscriber(
            port=PORT_IPO_DETECTOR,
            service_name="ipo_detector",
            data_callback=data_callback,
            auto_start=auto_start
        )
    elif data_callback is not None:
        _GLOBAL_IPO_SUBSCRIBER.data_callback = data_callback
    return _GLOBAL_IPO_SUBSCRIBER

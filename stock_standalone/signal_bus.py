# -*- coding: utf-8 -*-
"""
SignalBus - 统一信号总线

功能：
1. 统一事件分发（形态信号、报警信号、交易信号、风险信号）
2. 订阅/发布模式
3. 事件历史记录（便于追溯）

使用示例：
    bus = SignalBus()
    bus.subscribe(SignalBus.EVENT_PATTERN, handler_func)
    bus.publish(SignalBus.EVENT_PATTERN, "IntradayDetector", {"code": "000001", ...})
"""
from __future__ import annotations
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class BusEvent:
    """总线事件数据结构"""
    event_type: str
    timestamp: datetime
    source: str
    payload: Dict[str, Any]
    
    def __repr__(self):
        return f"BusEvent({self.event_type}, {self.source}, {self.timestamp.strftime('%H:%M:%S')})"


class SignalBus:
    """
    线程安全的信号总线单例
    
    事件类型：
    - EVENT_PATTERN: 形态触发（日内/日K形态检测）
    - EVENT_ALERT: 报警（语音/弹窗）
    - EVENT_TRADE: 交易（建仓/加仓/减仓/清仓）
    - EVENT_RISK: 风险（止损/顶部识别）
    - EVENT_HOTLIST: 热点面板（添加/移除/状态变更）
    - EVENT_PHASE: 阶段变更（仓位状态机阶段切换）
    """
    _instance: Optional['SignalBus'] = None
    _lock = Lock()
    
    # 事件类型常量
    EVENT_PATTERN = "pattern"
    EVENT_ALERT = "alert"
    EVENT_TRADE = "trade"
    EVENT_RISK = "risk"
    EVENT_HOTLIST = "hotlist"
    EVENT_PHASE = "phase"
    
    # 事件优先级（数字越大优先级越高）
    PRIORITY = {
        EVENT_RISK: 100,
        EVENT_TRADE: 80,
        EVENT_PHASE: 60,
        EVENT_PATTERN: 40,
        EVENT_HOTLIST: 30,
        EVENT_ALERT: 20,
    }
    
    def __new__(cls) -> 'SignalBus':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._subscribers: Dict[str, List[Callable[[BusEvent], None]]] = {}
                    instance._history: List[BusEvent] = []
                    instance._max_history = 500
                    instance._initialized = True
                    cls._instance = instance
        return cls._instance
    
    def subscribe(self, event_type: str, handler: Callable[[BusEvent], None]) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型（使用 SignalBus.EVENT_* 常量）
            handler: 回调函数，签名为 func(event: BusEvent) -> None
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"SignalBus: {getattr(handler, '__name__', 'handler')} subscribed to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> bool:
        """
        取消订阅
        
        Returns:
            是否成功取消
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    return True
                except ValueError:
                    pass
        return False
    
    def publish(self, event_type: str, source: str, payload: Dict[str, Any]) -> BusEvent:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            source: 事件来源（模块名）
            payload: 事件数据
            
        Returns:
            创建的事件对象
        """
        event = BusEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            source=source,
            payload=payload
        )
        
        # 记录历史
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        
        # 分发给订阅者
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"SignalBus handler error: {e} (source={source}, type={event_type})")
        
        logger.debug(f"SignalBus: Published {event_type} from {source}")
        return event
    
    def get_history(self, event_type: Optional[str] = None, 
                    limit: int = 100,
                    since: Optional[datetime] = None) -> List[BusEvent]:
        """
        获取事件历史
        
        Args:
            event_type: 筛选特定类型，None 表示全部
            limit: 返回条数限制
            since: 仅返回此时间之后的事件
        """
        with self._lock:
            result = self._history
            
            if event_type:
                result = [e for e in result if e.event_type == event_type]
            
            if since:
                result = [e for e in result if e.timestamp >= since]
            
            return result[-limit:]
    
    def get_recent_by_code(self, code: str, limit: int = 10) -> List[BusEvent]:
        """获取指定股票代码的最近事件"""
        with self._lock:
            result = [
                e for e in self._history 
                if e.payload.get('code') == code
            ]
            return result[-limit:]
    
    def clear_history(self) -> int:
        """清空历史记录，返回清除的条数"""
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count
    
    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """获取订阅者数量"""
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(handlers) for handlers in self._subscribers.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """获取总线统计信息"""
        with self._lock:
            type_counts = {}
            for event in self._history:
                type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
            
            return {
                "total_events": len(self._history),
                "subscriber_count": self.get_subscriber_count(),
                "event_type_counts": type_counts,
                "subscribers_by_type": {
                    k: len(v) for k, v in self._subscribers.items()
                }
            }


# 全局单例访问
_bus_instance: Optional[SignalBus] = None

def get_signal_bus() -> SignalBus:
    """获取全局信号总线实例"""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = SignalBus()
    return _bus_instance


# 便捷函数
def publish_pattern(source: str, code: str, name: str, pattern: str, 
                    price: float, detail: str = "") -> BusEvent:
    """发布形态事件的便捷函数"""
    return get_signal_bus().publish(
        SignalBus.EVENT_PATTERN,
        source,
        {
            "code": code,
            "name": name,
            "pattern": pattern,
            "price": price,
            "detail": detail,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
    )


def publish_phase_change(source: str, code: str, name: str,
                         old_phase: str, new_phase: str,
                         position_ratio: float, reason: str = "") -> BusEvent:
    """发布阶段变更事件的便捷函数"""
    return get_signal_bus().publish(
        SignalBus.EVENT_PHASE,
        source,
        {
            "code": code,
            "name": name,
            "old_phase": old_phase,
            "new_phase": new_phase,
            "position_ratio": position_ratio,
            "reason": reason,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
    )


if __name__ == "__main__":
    # 简单测试
    def test_handler(event: BusEvent):
        print(f"Received: {event}")
    
    bus = get_signal_bus()
    bus.subscribe(SignalBus.EVENT_PATTERN, test_handler)
    
    publish_pattern(
        source="test",
        code="000001",
        name="平安银行",
        pattern="low_open_high_walk",
        price=10.5,
        detail="低开2%走高"
    )
    
    print(f"Stats: {bus.get_stats()}")

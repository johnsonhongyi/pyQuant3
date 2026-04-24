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
from typing import Dict, List, Callable, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from logger_utils import LoggerFactory
logger = LoggerFactory.getLogger(__name__)

# 尝试导入信号标准 (使用类型注解支持)
try:
    from signal_standard import StandardSignal
    _HAS_STANDARD = True
except ImportError:
    StandardSignal = Any  # Fallback for type hinting
    _HAS_STANDARD = False
    logger.warning("signal_standard not found, StandardSignal functionality will be limited")


@dataclass
class BusEvent:
    """总线事件数据结构"""
    event_type: str
    timestamp: datetime
    source: str
    payload: Dict[str, Any]
    signal: Optional['StandardSignal'] = None  # 使用字符串引用避免导入期循环或缺失问题
    
    @property
    def type(self) -> str:
        """Alias for event_type to maintain backward compatibility"""
        return self.event_type

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
    EVENT_HEARTBEAT = "heartbeat"
    EVENT_STRATEGIC_TREND = "strategic_trend"
    
    # 事件优先级（数字越大优先级越高）
    PRIORITY = {
        EVENT_RISK: 100,
        EVENT_TRADE: 80,
        EVENT_PHASE: 60,
        EVENT_PATTERN: 40,
        EVENT_HOTLIST: 30,
        EVENT_STRATEGIC_TREND: 25,
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
                    instance._external_queue = None  # ⭐ [NEW] 外部队列用于跨进程中转
                    instance._initialized = True
                    cls._instance = instance
        return cls._instance
    
    def set_external_queue(self, queue: Any) -> None:
        """设置外部中转队列 (跨进程支持)"""
        with self._lock:
            self._external_queue = queue
            logger.info(f"SignalBus: External bridge queue set (ID={id(queue) if queue else None})")

    def subscribe(self, event_type: str, handler: Callable[[BusEvent], None]) -> None:
        """订阅事件"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"SignalBus: {getattr(handler, '__name__', str(handler))} subscribed to {event_type}. Total subscribers: {len(self._subscribers[event_type])}")
    
    def unsubscribe(self, event_type: str, handler: Callable) -> bool:
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    logger.debug(f"SignalBus: {getattr(handler, '__name__', str(handler))} unsubscribed from {event_type}")
                    return True
                except ValueError:
                    pass
        return False
    
    def publish(self, event_type: str, source: str, payload: Dict[str, Any], 
                signal: Optional['StandardSignal'] = None) -> BusEvent:
        """发布事件"""
        event = BusEvent(
            event_type=event_type,
            timestamp=datetime.now(),
            source=source,
            payload=payload,
            signal=signal
        )
        
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            
            # ⭐ [NEW] 如果设置了外部中转队列，则同时推送到队列
            if self._external_queue:
                try:
                    # 将 event 序列化为 dict 或保持对象 (如果是 mp.Queue 支持的对象)
                    # 为了安全，通常建议推送到 Queue 的是简单对象或 dataclass
                    self._external_queue.put(event, block=False)
                except Exception as e:
                    logger.error(f"SignalBus: Failed to push to external queue: {e}")
        
        handlers = self._subscribers.get(event_type, [])
        # 🛡️ 降级日志等级，避免 ERROR 洪泛
        import os
        # logger.debug(f"📡 [BUS_TRACE] SignalBus({id(self)}, pid={os.getpid()}): Publishing {event_type} from {source}. Found {len(handlers)} handlers.")
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"SignalBus handler error: {e} (source={source}, type={event_type})")
        
        return event

    def get_history(self, event_type: Optional[str] = None, 
                    limit: int = 100,
                    since: Optional[datetime] = None) -> List[BusEvent]:
        with self._lock:
            result = self._history
            if event_type:
                result = [e for e in result if e.event_type == event_type]
            if since:
                result = [e for e in result if e.timestamp >= since]
            return result[-limit:]

    def get_recent_by_code(self, code: str, limit: int = 10) -> List[BusEvent]:
        with self._lock:
            result = [e for e in self._history if e.payload.get('code') == code]
            return result[-limit:]

    def clear_history(self) -> int:
        with self._lock:
            count = len(self._history)
            self._history.clear()
            return count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            type_counts = {}
            for event in self._history:
                type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
            return {
                "total_events": len(self._history),
                "event_type_counts": type_counts
            }


# 全局单例
_bus_instance: Optional[SignalBus] = None

def get_signal_bus() -> SignalBus:
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = SignalBus()
    return _bus_instance


# ==============================================================================
# 统一发布接口
# ==============================================================================

def publish_standard_signal(signal: 'StandardSignal') -> BusEvent:
    """发布标准化信号"""
    return get_signal_bus().publish(
        event_type=signal.type,
        source=signal.source,
        payload=signal.to_dict(),
        signal=signal
    )


def publish_pattern(source: str, code: str, name: str, pattern: str, 
                    price: float, detail: str = "", score: float = 0.0, 
                    count: int = 1, is_high_priority: bool = False,
                    grade: str = "") -> BusEvent:
    """发布形态事件 (自动封装)"""
    if _HAS_STANDARD:
        signal = StandardSignal(
            code=code,
            name=name,
            type=SignalBus.EVENT_PATTERN,
            subtype=pattern,
            price=price,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            score=score,
            count=count,
            detail=detail,
            grade=grade,
            source=source,
            is_high_priority=is_high_priority
        )
        return publish_standard_signal(signal)
    
    return get_signal_bus().publish(
        SignalBus.EVENT_PATTERN,
        source,
        {
            "code": code, "name": name, "pattern": pattern, "price": price,
            "detail": detail, "score": score, "count": count, 
            "is_high_priority": is_high_priority, "grade": grade,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
    )


def publish_phase_change(source: str, code: str, name: str,
                         old_phase: str, new_phase: str,
                         position_ratio: float, reason: str = "") -> BusEvent:
    """发布阶段变更"""
    payload = {
        "code": code, "name": name, "old_phase": old_phase, "new_phase": new_phase,
        "position_ratio": position_ratio, "reason": reason,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    
    if _HAS_STANDARD:
        signal = StandardSignal(
            code=code,
            name=name,
            type=SignalBus.EVENT_PHASE,
            subtype=new_phase,
            price=0.0,
            timestamp=str(payload["timestamp"]),
            detail=reason,
            phase=new_phase,
            source=source,
            metadata=payload
        )
        return get_signal_bus().publish(SignalBus.EVENT_PHASE, source, payload, signal)
        
    return get_signal_bus().publish(SignalBus.EVENT_PHASE, source, payload)


def publish_strategic_trend(source: str, trends: List[Dict[str, Any]]) -> BusEvent:
    """发布战略大格局趋势列表"""
    return get_signal_bus().publish(
        SignalBus.EVENT_STRATEGIC_TREND,
        source,
        {"trends": trends}
    )

from __future__ import annotations
from typing import Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

class SignalType(Enum):
    BUY = "买入"           # 主信号：买入
    SELL = "卖出"          # 主信号：卖出
    ADD = "加仓"           # 增量信号：加仓
    SUB = "减仓"           # 增量信号：减仓
    STOP_LOSS = "止损"     # 风险信号：止损
    TAKE_PROFIT = "止盈"   # 风险信号：止盈
    SHADOW_BUY = "影子买入" # 影子引擎：模拟买入
    SHADOW_SELL = "影子卖出" # 影子引擎：模拟卖出
    VETO = "否决"           # 策略否决：过滤不符合条件的信号

class SignalSource(Enum):
    MANUAL = "手动"
    STRATEGY_ENGINE = "策略引擎"
    SHADOW_ENGINE = "影子策略"

@dataclass
class SignalPoint:
    """可视化信号点数据结构"""
    code: str
    timestamp: datetime | str  # 信号时间
    bar_index: int               # K线索引位置
    price: float                 # 触发价格
    signal_type: SignalType
    source: SignalSource = SignalSource.STRATEGY_ENGINE
    resample: str = 'd'  # 周期标识: 'd', '3d', 'w', 'm'
    reason: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)
    
    @property
    def color(self) -> tuple[int, int, int] | tuple[int, int, int, int]:
        return SIGNAL_VISUAL_CONFIG.get(self.signal_type, {}).get("color", (255, 255, 255))

    @property
    def symbol(self) -> str:
        return SIGNAL_VISUAL_CONFIG.get(self.signal_type, {}).get("symbol", "o")

    @property
    def size(self) -> int:
        return SIGNAL_VISUAL_CONFIG.get(self.signal_type, {}).get("size", 10)

    def to_visual_hit(self) -> dict[str, Any]:
        """转换为可视化交互所需的字典格式"""
        if isinstance(self.timestamp, datetime):
            ts_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        else:
            ts_str = str(self.timestamp)
        
        return {
            "date": ts_str,
            "price": self.price,
            "action": self.signal_type.value,
            "reason": self.reason,
            "resample": self.resample,
            "meta": {
                "code": self.code,
                "date": ts_str,
                "price": self.price,
                "action": self.signal_type.value,
                "source": self.source.value,
                "resample": self.resample,
                "reason": self.reason,
                "indicators": self.debug_info
            }
        }

# 可视化配置变量映射
SIGNAL_VISUAL_CONFIG = {
    SignalType.BUY: {"symbol": 't1', "size": 15, "color": (255, 0, 0)},
    SignalType.SELL: {"symbol": 't', "size": 15, "color": (0, 255, 0)},
    SignalType.ADD: {"symbol": 'p', "size": 12, "color": (255, 100, 100)},
    SignalType.SUB: {"symbol": 'h', "size": 12, "color": (100, 255, 100)},
    SignalType.STOP_LOSS: {"symbol": 'x', "size": 12, "color": (255, 255, 0)},
    SignalType.TAKE_PROFIT: {"symbol": 'star', "size": 15, "color": (255, 215, 0)},
    SignalType.SHADOW_BUY: {"symbol": 't1', "size": 10, "color": (200, 200, 200, 150)},
    SignalType.SHADOW_SELL: {"symbol": 't', "size": 10, "color": (150, 150, 150, 150)},
    SignalType.VETO: {"symbol": 'o', "size": 8, "color": (100, 100, 100, 100)},
}

from dataclasses import dataclass, field
from typing import Any

@dataclass
class StandardSignal:
    """统一信号标准化结构"""
    code: str
    name: str
    type: str                  # 信号类型: pattern, trade, risk, alert, info
    subtype: str               # 子类型: low_open_high_walk, buy, sell, etc.
    price: float
    timestamp: str             # 触发时间戳 (格式: HH:MM:SS)
    
    score: float = 0.0         # 信号强度评分 (通常 0.0 - 1.0)
    count: int = 1             # 日内触发次数 (迭代计数)
    detail: str = ""           # 文本描述
    grade: str = ""            # [NEW] 走势评级 (S/A/B/C)
    
    # 状态上下文
    phase: str = "UNKNOWN"     # 当前持仓阶段 (SCOUT, ACCUMULATE, etc.)
    source: str = ""           # 来源模块
    
    # 元数据
    is_high_priority: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典，便于 JSON/IPC 传输"""
        return {
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "subtype": self.subtype,
            "price": self.price,
            "timestamp": self.timestamp,
            "score": self.score,
            "count": self.count,
            "detail": self.detail,
            "grade": self.grade,
            "phase": self.phase,
            "source": self.source,
            "is_high_priority": self.is_high_priority,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'StandardSignal':
        """从字典还原对象"""
        return cls(**data)


    def __repr__(self):
        priority_flag = " [!] " if self.is_high_priority else " "
        return f"{self.timestamp}{priority_flag}[{self.type.upper()}:{self.subtype}] {self.code} {self.name} @ {self.price:.2f} ({self.detail})"

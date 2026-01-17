# -*- coding: utf-8 -*-
"""
策略接口规范定义

定义所有交易策略必须实现的标准接口,支持策略注册、启用/禁用、信号聚合
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum
import pandas as pd

from signal_types import SignalPoint, SignalType, SignalSource


class StrategyMode(Enum):
    """策略运行模式"""
    BACKTEST = "回测"      # 历史回测模式
    REALTIME = "实时"      # 实时交易模式
    SHADOW = "影子"        # 影子策略模式(仅记录不执行)


@dataclass
class StrategyConfig:
    """策略配置"""
    name: str                          # 策略唯一标识
    display_name: str                  # 显示名称
    description: str = ""              # 策略描述
    enabled: bool = True               # 是否启用
    weight: float = 1.0                # 信号权重 (0.0-1.0)
    mode: StrategyMode = StrategyMode.BACKTEST
    params: Dict[str, Any] = field(default_factory=dict)  # 策略参数


class IStrategy(ABC):
    """
    策略接口基类
    
    所有交易策略必须继承此类并实现抽象方法
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        self._config = config or StrategyConfig(
            name=self.__class__.__name__,
            display_name=self.__class__.__name__
        )
    
    @property
    def name(self) -> str:
        """策略唯一标识"""
        return self._config.name
    
    @property
    def display_name(self) -> str:
        """显示名称"""
        return self._config.display_name
    
    @property
    def description(self) -> str:
        """策略描述"""
        return self._config.description
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._config.enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._config.enabled = value
    
    @property
    def weight(self) -> float:
        """信号权重"""
        return self._config.weight
    
    @property
    def mode(self) -> StrategyMode:
        """运行模式"""
        return self._config.mode
    
    @abstractmethod
    def evaluate_historical(self, code: str, day_df: pd.DataFrame) -> List[SignalPoint]:
        """
        历史回测评估
        
        Args:
            code: 股票代码
            day_df: 日K线数据 (DatetimeIndex, columns: open/high/low/close/volume/amount...)
            
        Returns:
            信号点列表
        """
        pass
    
    @abstractmethod
    def evaluate_realtime(self, code: str, row_data: Dict[str, Any], 
                          snapshot: Dict[str, Any]) -> Optional[SignalPoint]:
        """
        实时评估
        
        Args:
            code: 股票代码
            row_data: 当前tick数据
            snapshot: 持仓快照
            
        Returns:
            信号点 (无信号返回None)
        """
        pass
    
    def validate_data(self, day_df: pd.DataFrame) -> tuple[bool, str]:
        """
        数据校验 (可覆写)
        
        Returns:
            (是否有效, 错误信息)
        """
        if day_df is None or day_df.empty:
            return False, "数据为空"
        if 'close' not in day_df.columns:
            return False, "缺少close列"
        return True, ""


class StrategyRegistry:
    """
    策略注册表
    
    管理所有已注册策略的单例
    """
    _instance: Optional['StrategyRegistry'] = None
    _strategies: Dict[str, IStrategy]
    _enabled: Set[str]
    
    def __new__(cls) -> 'StrategyRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._strategies = {}
            cls._instance._enabled = set()
        return cls._instance
    
    def register(self, strategy: IStrategy) -> None:
        """注册策略"""
        self._strategies[strategy.name] = strategy
        if strategy.enabled:
            self._enabled.add(strategy.name)
    
    def unregister(self, name: str) -> None:
        """注销策略"""
        self._strategies.pop(name, None)
        self._enabled.discard(name)
    
    def enable(self, name: str) -> bool:
        """启用策略"""
        if name in self._strategies:
            self._strategies[name].enabled = True
            self._enabled.add(name)
            return True
        return False
    
    def disable(self, name: str) -> bool:
        """禁用策略"""
        if name in self._strategies:
            self._strategies[name].enabled = False
            self._enabled.discard(name)
            return True
        return False
    
    def get(self, name: str) -> Optional[IStrategy]:
        """获取策略实例"""
        return self._strategies.get(name)
    
    def get_all(self) -> List[IStrategy]:
        """获取所有策略"""
        return list(self._strategies.values())
    
    def get_enabled(self) -> List[IStrategy]:
        """获取所有启用的策略"""
        return [s for s in self._strategies.values() if s.enabled]
    
    def get_enabled_names(self) -> List[str]:
        """获取启用策略名称列表"""
        return list(self._enabled)
    
    def is_enabled(self, name: str) -> bool:
        """检查策略是否启用"""
        return name in self._enabled
    
    def clear(self) -> None:
        """清空所有策略"""
        self._strategies.clear()
        self._enabled.clear()


class SignalConflictResolver:
    """
    信号冲突解决器
    
    处理多策略产生的冲突信号
    """
    
    # 信号优先级 (越大越优先)
    PRIORITY_MAP: Dict[SignalType, int] = {
        SignalType.VETO: 100,           # 否决最高优先
        SignalType.STOP_LOSS: 90,       # 止损次之
        SignalType.TAKE_PROFIT: 80,     # 止盈
        SignalType.SELL: 70,            # 卖出
        SignalType.SUB: 60,             # 减仓
        SignalType.BUY: 50,             # 买入
        SignalType.ADD: 40,             # 加仓
    }
    
    @classmethod
    def resolve(cls, signals: List[SignalPoint]) -> List[SignalPoint]:
        """
        解决信号冲突
        
        规则:
        1. VETO信号具有最高优先级,会否决同一时间点的其他信号
        2. 同一bar的多个信号按优先级排序,保留最高优先级
        3. 不同bar的信号不冲突
        """
        if not signals:
            return []
        
        # 按bar_index分组
        grouped: Dict[int, List[SignalPoint]] = {}
        for sig in signals:
            idx = sig.bar_index
            if idx not in grouped:
                grouped[idx] = []
            grouped[idx].append(sig)
        
        resolved: List[SignalPoint] = []
        for bar_idx, bar_signals in grouped.items():
            # 检查是否有VETO信号
            veto_signals = [s for s in bar_signals if s.signal_type == SignalType.VETO]
            if veto_signals:
                # 有VETO,只保留VETO信号,否决其他
                resolved.extend(veto_signals)
                continue
            
            # 按优先级排序,取最高优先级
            bar_signals.sort(
                key=lambda s: cls.PRIORITY_MAP.get(s.signal_type, 0),
                reverse=True
            )
            
            # 保留最高优先级的一个信号
            if bar_signals:
                resolved.append(bar_signals[0])
        
        # 按bar_index排序
        resolved.sort(key=lambda s: s.bar_index)
        return resolved

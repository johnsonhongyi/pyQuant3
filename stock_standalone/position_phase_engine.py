# -*- coding: utf-8 -*-
"""
Position Phase Engine
仓位状态机引擎
用于管理个股交易的生命周期 (SCOUT -> SURGE -> EXIT)
"""
import enum
from typing import Dict, Any, Tuple, Optional

class TradePhase(enum.Enum):
    IDLE = "IDLE"             # 空仓观望
    SCOUT = "SCOUT"           # 试探 (10%)
    ACCUMULATE = "ACCUMULATE" # 蓄势 (30%)
    LAUNCH = "LAUNCH"         # 启动 (50%)
    SURGE = "SURGE"           # 主升 (70-90%)
    TOP_WATCH = "TOP_WATCH"   # 顶部预警 (减仓)
    EXIT = "EXIT"             # 离场 (0%)

class PositionPhaseEngine:
    """
    阶段性仓位管理引擎
    """
    def __init__(self):
        # 默认仓位配置
        self.phase_ratios = {
            TradePhase.IDLE: 0.0,
            TradePhase.SCOUT: 0.1,
            TradePhase.ACCUMULATE: 0.3,
            TradePhase.LAUNCH: 0.5,
            TradePhase.SURGE: 0.8,
            TradePhase.TOP_WATCH: 0.4,
            TradePhase.EXIT: 0.0
        }

    def evaluate_phase(self, 
                       code: str, 
                       row: Dict[str, Any], 
                       snap: Dict[str, Any], 
                       current_phase: TradePhase = TradePhase.IDLE) -> Tuple[TradePhase, str]:
        """
        评估并更新当前股票的阶段状态
        
        Args:
            code: 股票代码
            row: 实时行情数据 (dict or Series)
            snap: 历史快照/状态数据
            current_phase: 当前所处阶段
            
        Returns:
            (NewPhase, Reason)
        """
        try:
            # 1. 提取基础数据
            current_price = float(row.get('trade', 0))
            open_price = float(row.get('open', 0))
            nclose = float(row.get('nclose', 0)) # 今日均价
            
            # 昨日数据
            last_close = float(row.get('last_close', snap.get('last_close', 0)))
            last_low = float(row.get('last_low', snap.get('last_low', 0)))
            
            # 如果没有昨日低点数据，尝试从 snapshot 或其他字段获取
            if last_low <= 0:
                last_low = float(snap.get('low', 0)) # Fallback, risky

            if current_price <= 0:
                return current_phase, "无实时价格"

            # -----------------------------------------------------
            # 1. 强制离场检查 (Exit Logic)
            # -----------------------------------------------------
            # 用户规则: 回踩破前一日低点
            if last_low > 0 and current_price < last_low:
                return TradePhase.EXIT, f"跌破昨日低点 {last_low}"
            
            # 止损检查 (从 snap 获取成本)
            cost_price = float(snap.get('cost_price', 0))
            if cost_price > 0:
                loss_pct = (current_price - cost_price) / cost_price
                if loss_pct < -0.05: # 硬止损
                    return TradePhase.EXIT, f"触及硬止损 {loss_pct:.2%}"

            # -----------------------------------------------------
            # 2. 反向/抄底逻辑 (Reversal Logic)
            # -----------------------------------------------------
            # 用户规则: 低开走高
            is_low_open = open_price > 0 and last_close > 0 and open_price < last_close * 0.99 # 低开 > 1%
            is_go_high = current_price > open_price and current_price > nclose # 且站上均价
            
            if is_low_open and is_go_high:
                # 只有在空仓或试探阶段才触发，如果已经主升则无需降级
                if current_phase in [TradePhase.IDLE, TradePhase.EXIT]:
                    return TradePhase.SCOUT, "低开走高反弹确认"

            # -----------------------------------------------------
            # 3. 状态流转逻辑
            # -----------------------------------------------------
            
            # [IDLE -> SCOUT]
            # 这里的逻辑主要由外部策略(StockLiveStrategy)的 Buy Signal 触发
            # 如果外部已经买入，这里根据持仓调整状态
            # 但作为纯状态机，我们也可以定义进入条件
            if current_phase == TradePhase.IDLE:
                # 如果外部有强信号 (snapshot里有标志)
                if snap.get('buy_triggered_today'):
                    return TradePhase.SCOUT, "买入信号触发"
            
            # [SCOUT -> ACCUMULATE]
            # 试探成功：站稳成本价上方，且未大涨
            if current_phase == TradePhase.SCOUT:
                if cost_price > 0 and current_price > cost_price * 1.02:
                     return TradePhase.ACCUMULATE, "试探成功，利润垫 > 2%"

            # [ACCUMULATE -> LAUNCH]
            # 蓄势突破：放量突破 (需要量能判断，暂简化)
            if current_phase == TradePhase.ACCUMULATE:
                if row.get('percent', 0) > 5.0: # 涨幅 > 5%
                    return TradePhase.LAUNCH, "蓄势突破，涨幅 > 5%"

            # [LAUNCH -> SURGE]
            # 启动加速：涨停或连板
            if current_phase == TradePhase.LAUNCH:
                 if row.get('percent', 0) > 9.0:
                     return TradePhase.SURGE, "加速涨停"

            return current_phase, "状态维持"

        except Exception as e:
            return current_phase, f"Error: {e}"

    def get_target_position(self, phase: TradePhase) -> float:
        """获取目标仓位"""
        return self.phase_ratios.get(phase, 0.0)

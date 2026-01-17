import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional

from StrongPullbackMA5Strategy import StrongPullbackMA5Strategy
from intraday_decision_engine import IntradayDecisionEngine
from trading_logger import TradingLogger
from signal_types import SignalPoint, SignalType, SignalSource, SIGNAL_VISUAL_CONFIG
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger()

class StrategyController:
    """
    策略控制器：统一管理策略规则、信号生成、交易执行
    直接集成 stock_live_strategy.py 中的逻辑
    """
    master: Any
    trading_logger: TradingLogger
    decision_engine: IntradayDecisionEngine
    pullback_strat: StrongPullbackMA5Strategy
    shadow_engine: IntradayDecisionEngine
    
    def __init__(self, master: Any = None):
        self.master = master
        # 初始化核心组件
        self.trading_logger = TradingLogger()
        self.decision_engine = IntradayDecisionEngine()
        self.pullback_strat = StrongPullbackMA5Strategy(min_score=80)
        
        # 影子引擎用于比对
        self.shadow_engine = IntradayDecisionEngine(max_position=0.3)
        
    def evaluate_historical_signals(self, code: str, day_df: pd.DataFrame) -> List[SignalPoint]:
        """
        全量历史策略回放：集成所有规则
        """
        signals: List[SignalPoint] = []
        if day_df is None or day_df.empty:
            return signals
            
        try:
            # 1. 运行 StrongPullbackMA5 策略 (批量)
            # 该策略内部已实现“首次触发”逻辑，返回的已是过滤后的买点
            is_valid, msg = self.pullback_strat.validate_df(day_df)
            if not is_valid:
                logger.warning(f"Stock {code} historical simulation skip: {msg}")
                pb_results = pd.DataFrame()
            else:
                pb_results = self.pullback_strat.run(day_df)

            if not pb_results.empty:
                for timestamp, row in pb_results.iterrows():
                    try:
                        idx = day_df.index.get_loc(timestamp)
                        signals.append(self._create_signal_point(
                            code=code,
                            timestamp=timestamp,
                            idx=idx,
                            price=float(row.get('close', 0.0)), # type: ignore
                            stype=SignalType.BUY,
                            source=SignalSource.STRATEGY_ENGINE,
                            reason=f"强力回撤: 评分 {row.get('strong_score', 0)}",
                            debug_info=row.to_dict()
                        ))
                    except Exception:
                        continue

            # 2. 模拟盘中决策逻辑 (逐行扫描最近 N 天)
            # 用户要求：标记是最近周期的数据才有意义。缩小扫描窗以减少历史冗余信号。
            eval_window = 20 # 缩减至最近20个交易日
            eval_df = day_df.tail(eval_window)
            
            # 初始化一个模拟 snapshot
            snapshot: Dict[str, Any] = {
                'code': code,
                'market_win_rate': 0.5,
                'loss_streak': 0,
                'highest_since_buy': 0.0
            }
            
            last_action_str = "" # 记录上一个动作，用于过滤连续重复信号
            
            for timestamp, row in eval_df.iterrows():
                try:
                    idx = day_df.index.get_loc(timestamp)
                    
                    # 构造行情行
                    row_dict: Dict[str, Any] = row.to_dict() # type: ignore
                    row_dict['code'] = code
                    row_dict['trade'] = float(row.get('close', 0.0)) # type: ignore
                    
                    # 更新前一个 bar 的快照信息
                    prev_idx = int(idx) - 1 # type: ignore
                    if prev_idx >= 0:
                        snapshot['last_close'] = float(day_df.iloc[prev_idx].get('close', 0.0)) # type: ignore
                        snapshot['nclose'] = float(day_df.iloc[prev_idx].get('close', 0.0)) # type: ignore
                    
                    # 运行决策引擎
                    decision = self.decision_engine.evaluate(row_dict, snapshot)
                    action_str = str(decision.get('action', '无'))
                    
                    # 信号触发逻辑：动作发生变化且属于交易动作 (过滤每天都是“买入”或“持仓”的情况)
                    if action_str != last_action_str and action_str in ("买入", "卖出", "ADD", "加仓", "REDUCE", "减仓", "SUB", "止损", "止盈"):
                        stype = self._map_action_to_signal_type(action_str)
                        signals.append(self._create_signal_point(
                            code=code,
                            timestamp=timestamp,
                            idx=idx,
                            price=float(row.get('close', 0.0)), # type: ignore
                            stype=stype,
                            source=SignalSource.STRATEGY_ENGINE,
                            reason=str(decision.get('reason', '')),
                            debug_info=decision.get('debug', {})
                        ))
                        last_action_str = action_str
                    elif action_str not in ("买入", "卖出", "ADD", "加仓", "REDUCE", "减仓", "SUB", "止损", "止盈"):
                        # 如果当前是中性动作，重置 last_action，允许下次再次触发同一个交易动作
                        last_action_str = ""
                    
                    # 如果是买入，更新快照
                        if action_str in ("买入", "ADD", "加仓"):
                            snapshot['buy_price'] = float(row.get('close', 0.0)) # type: ignore
                            snapshot['highest_since_buy'] = float(row.get('close', 0.0)) # type: ignore
                    
                    # 更新移动最高价用于风险评估
                    if float(snapshot.get('buy_price', 0.0)) > 0:
                        highest_so_far = float(snapshot.get('highest_since_buy', 0.0))
                        snapshot['highest_since_buy'] = max(highest_so_far, float(row.get('close', 0.0))) # type: ignore
                except Exception as e:
                    logger.error(f"Error in step evaluation for {code} at {timestamp}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in evaluate_historical_signals for {code}: {e}", exc_info=True)
            
        return signals

    def get_realtime_decision(self, code: str, row_data: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        实时决策接口：直接对接可视化实时流
        """
        decision = self.decision_engine.evaluate(row_data, snapshot)
        return decision

    def _create_signal_point(self, code: str, timestamp: Any, idx: Any, price: float, stype: SignalType, source: SignalSource, reason: str, debug_info: Optional[Dict[str, Any]] = None) -> SignalPoint:
        return SignalPoint(
            code=code,
            timestamp=timestamp if isinstance(timestamp, datetime) else pd.to_datetime(timestamp),
            bar_index=int(idx),
            price=float(price),
            signal_type=stype,
            source=source,
            reason=str(reason),
            debug_info=debug_info or {}
        )

    def _map_action_to_signal_type(self, action: str) -> SignalType:
        mapping: Dict[str, SignalType] = {
            "买入": SignalType.BUY,
            "BUY": SignalType.BUY,
            "卖出": SignalType.SELL,
            "SELL": SignalType.SELL,
            "加仓": SignalType.ADD,
            "ADD": SignalType.ADD,
            "减仓": SignalType.SUB,
            "REDUCE": SignalType.SUB,
            "SUB": SignalType.SUB,
            "止损": SignalType.STOP_LOSS,
            "止盈": SignalType.TAKE_PROFIT
        }
        upper_action = str(action).upper()
        if upper_action in mapping:
            return mapping[upper_action]
        
        if action in mapping:
            return mapping[action]
            
        return SignalType.BUY # Default placeholder

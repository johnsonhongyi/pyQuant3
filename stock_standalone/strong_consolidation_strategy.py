
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime

from strategy_interface import IStrategy, StrategyConfig, StrategyMode
from signal_types import SignalPoint, SignalType, SignalSource
from signal_message_queue import SignalMessageQueue, SignalMessage

logger = logging.getLogger(__name__)

class StrongConsolidationStrategy(IStrategy):
    """
    强势整理突破策略 (301348模式)
    
    逻辑:
    1. 寻找最近一次中阳突破布林上轨 (Breakout Day)
    2. 检查自Breakout Day以来, 收盘价从未有效跌破 Breakout Day 的收盘价 (Strong Consolidation)
    3. 检查最近2日是否呈现攻击形态 (每日新高, 量能配合)
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        super().__init__(config)
        if not self._config.description:
            self._config.description = "捕捉强势整理后再次突破的个股 (如301348模式)"
        
        # 内部使用 SignalMessageQueue 推送信号
        try:
            from signal_message_queue import SignalMessageQueue
            self.queue = SignalMessageQueue()
        except:
            self.queue = None

    def evaluate_historical(self, code: str, day_df: pd.DataFrame) -> List[SignalPoint]:
        # 本策略主要用于实时监控和即时选股, 历史回测暂返回空或仅作为验证
        # 为简化, 这里暂不实现全历史回测逻辑, 仅对最后一天进行评估
        points = []
        if day_df is None or len(day_df) < 20: 
            return points
            
        # 模拟实时评估最后一行
        # last_row = day_df.iloc[-1].to_dict()
        # snapshot = {
        #     'trade': last_row['close'],
        #     'high': last_row['high'],
        #     'low': last_row['low'],
        #     'open': last_row['open'],
        #     'volume': last_row['volume']
        # }
        
        # 需要传入完整DF进行计算
        sig = self._detect_pattern(code, day_df)
        if sig:
            points.append(sig)
            
            # --- 增强: 实时推送逻辑 (支持手动切换股票触发) ---
            # 如果信号是"今天"(最后一行)触发的, 推送到消息队列
            try:
                # 简单判断: 信号时间是数据最后一行的时间
                if str(sig.timestamp) == str(day_df.index[-1]) and self.queue:
                    # 避免重复推送? SignalMessageQueue未去重, 但UI显示有限制
                    # 构造消息
                    msg = SignalMessage(
                        priority=20, 
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        code=code,
                        name=str(day_df.iloc[-1].get('name', '')), 
                        signal_type='CONSOLIDATION',
                        source='STRATEGY',
                        reason=sig.reason,
                        score=90
                    )
                    self.queue.push(msg)
            except Exception as e:
                logger.error(f"Failed to push signal in evaluate_historical: {e}")
            
        return points

    def evaluate_realtime(self, code: str, row_data: Dict[str, Any], 
                          snapshot: Dict[str, Any]) -> Optional[SignalPoint]:
        """实时评估"""
        # 注意: 实时评估通常只拿到当前tick, 需要历史数据配合
        # 此处假设调用方会提供足够的历史数据上下文, 或者我们在内部维护/获取
        # 实际上 StrategyController 调用 evaluate_realtime 时通常是 Tick 级
        # 对于形态策略, 我们更倾向于在 on_dataframe_updated (分钟/日线更新) 时触发
        # 但遵循接口, 我们可以做简单的判读, 或者依赖外部传入的 day_df (如果接口支持)
        
        # 修正: 标准接口 evaluate_realtime 只有 row_data/snapshot
        # 严格来说无法做基于历史形态的复杂判断. 
        # 本策略更适合作为 "选股器" 运行, 或在 StrategyController 获取到新K线时运行.
        # 
        # 暂时返回 None, 逻辑主要实现在 evaluate_historical (被周期性调用) 
        # 或通过外部独立调用检测.
        return None
        
    def detect_and_push(self, code: str, df: pd.DataFrame) -> bool:
        """
        主动检测并推送信号 (供外部周期性调用)
        """
        sig_point = self._detect_pattern(code, df)
        if sig_point:
            # 推送到消息队列
            if self.queue:
                msg = SignalMessage(
                    priority=20, # 较高优先级
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    code=code,
                    name=str(df.iloc[-1].get('name', '')), # 尝试获取名称
                    signal_type='CONSOLIDATION',
                    source='STRATEGY',
                    reason=sig_point.reason,
                    score=90
                )
                self.queue.push(msg)
                return True
        return False

    def _detect_pattern(self, code: str, df: pd.DataFrame) -> Optional[SignalPoint]:
        """核心形态检测逻辑"""
        if len(df) < 30: return None
        
        # 计算布林带 (如果df里没有)
        if 'upper' not in df.columns:
            # 简单计算
            ma20 = df['close'].rolling(20).mean()
            std20 = df['close'].rolling(20).std()
            df['upper'] = ma20 + 2 * std20
        
        # 1. 寻找最近的有效突破日 (过去20天内)
        # 条件: 收盘价 > upper AND 涨幅 > 3% (中阳)
        # 且在突破前一段时间 (如3天) 是在 upper 下方
        
        lookback = 20
        recent = df.iloc[-lookback:].copy()
        recent['is_breakout'] = (recent['close'] > recent['upper']) & \
                                (recent['close'] > recent['open'] * 1.03)
        
        breakout_days = recent[recent['is_breakout']]
        if breakout_days.empty:
            return None
            
        # 取最近的一次主要突破 (如果有多次, 取最早的那个还是最近的? 
        # 301348模式是: 突破 -> 整理 -> 再突破. 
        # 这里的"启动日"主要指进入强势区的那个点)
        
        # 我们寻找最近的一个"启动点", 假设该点之后一直维持在启动点收盘价之上
        start_idx = None
        start_price = 0.0
        
        # 倒序遍历寻找符合条件的 Breakout
        # 逻辑: 找到一个 Breakout, 且自那之后 Close 始终 >= Breakout_Close * 0.98 (允许微小回撤)
        
        # 简化逻辑: 
        # 1. 必须处于强势区 (Close 近期一直在 MA20 之上)
        # 2. 存在突破日
        
        # 策略定义严格版:
        # A. 5-15天前有一根大阳线突破 upper
        # B. 至今 Close 没有跌破该大阳线的收盘价
        # C. 最近2天 High 创新高 (近期新高)
        
        today_idx = len(df) - 1
        
        # 倒推寻找启动日 (5到20天前)
        subset_breakout = breakout_days[
            (breakout_days.index < df.index[today_idx-3]) &  # 至少3天前
            (breakout_days.index > df.index[today_idx-25])   # 25天内
        ]
        
        if subset_breakout.empty:
            return None
            
        # 取最显著的一次 (涨幅最大) 或 第一天
        breakout_row = subset_breakout.sort_values('percent', ascending=False).iloc[0]
        breakout_date = breakout_row.name
        breakout_close = breakout_row['close']
        
        # A. 验证支撑: 自突破后, 收盘价未有效跌破 breakout_close
        consolidation_df = df.loc[breakout_date:].iloc[1:] # 突破后至今
        if consolidation_df.empty: 
            return None
            
        min_close = consolidation_df['close'].min()
        if min_close < breakout_close * 0.99: # 允许1%误差
            return None
            
        # B. 验证近期强势: 最近2天 连续新高 或 接近新高
        last_2 = df.iloc[-2:]
        if len(last_2) < 2: return None
        
        # 每日 High 都在抬升 (或维持高位)
        # 且最后一天是近期 (10天) 最高收盘价附近
        recent_10_high = df['high'].iloc[-10:].max()
        current_close = df.iloc[-1]['close']
        
        is_attacking = (last_2.iloc[-1]['high'] > last_2.iloc[-2]['high']) or \
                       (current_close >= recent_10_high * 0.98)
                       
        if not is_attacking:
            return None
            
        # C. 量能配合 (非必须, 但最好只关注放量的)
        # volume_ratio = last_2['volume'].mean() / df['volume'].iloc[-10:].mean()
        # if volume_ratio < 0.8: return None
        
        # 符合模式!
        return SignalPoint(
            code=code,
            signal_type=SignalType.BUY,
            timestamp=df.index[-1],
            bar_index=len(df)-1,
            price=current_close,
            source=SignalSource.STRATEGY_ENGINE,
            reason=f"强势整理突破: {breakout_date.strftime('%m-%d')}启动, 支撑{breakout_close:.2f}"
            # score=95 # SignalPoint不包含score, 仅SignalMessage包含
        )


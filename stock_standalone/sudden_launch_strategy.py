
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from strategy_interface import IStrategy, StrategyConfig
from signal_types import SignalPoint, SignalType, SignalSource
from signal_message_queue import SignalMessage, SignalMessageQueue

logger = logging.getLogger(__name__)

class SuddenLaunchStrategy(IStrategy):
    """
    突发启动策略 (Sudden Launch)
    
    逻辑:
    1. 捕捉超跌反弹或底部突发启动
    2. 形态: 一阳穿多线 (MA5/10/60) + 直达布林上轨 + 量能放大
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        super().__init__(config)
        if not self._config.description:
            self._config.description = "捕捉一阳穿多线、直达Upper的突发启动形态"
            
        try:
            self.queue = SignalMessageQueue()
        except:
            self.queue = None

    def evaluate_historical(self, code: str, day_df: pd.DataFrame) -> List[SignalPoint]:
        points = []
        if day_df is None or len(day_df) < 60:
            return points

        sig = self._detect_pattern(code, day_df)
        if sig:
            points.append(sig)
            
            # 手动测试或当天触发时推送
            if str(sig.timestamp) == str(day_df.index[-1]) and self.queue:
                try:
                    msg = SignalMessage(
                        priority=10,  # High priority
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        code=code,
                        name=str(day_df.iloc[-1].get('name', '')),
                        signal_type='SUDDEN_LAUNCH',
                        source='STRATEGY',
                        reason=sig.reason,
                        score=95
                    )
                    self.queue.push(msg)
                except Exception as e:
                    logger.error(f"Failed to push sudden launch signal: {e}")
                    
        return points

    def evaluate_realtime(self, code: str, row_data: Dict[str, Any], 
                          snapshot: Dict[str, Any]) -> Optional[SignalPoint]:
        return None

    def _detect_pattern(self, code: str, df: pd.DataFrame) -> Optional[SignalPoint]:
        """核心检测逻辑"""
        if len(df) < 60: return None
        
        # 1. 计算必要指标
        close = df['close']
        volume = df['volume']
        
        # MA
        ma5 = close.rolling(5).mean()
        ma10 = close.rolling(10).mean()
        ma60 = close.rolling(60).mean()
        
        # Volume MA
        v_ma5 = volume.rolling(5).mean()
        
        # Bollinger
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = ma20 + 2 * std20
        
        # 获取最后一天数据
        curr_idx = df.index[-1]
        c = close.iloc[-1]
        o = df['open'].iloc[-1]
        h = df['high'].iloc[-1]
        v = volume.iloc[-1]
        
        curr_ma5 = ma5.iloc[-1]
        curr_ma10 = ma10.iloc[-1]
        curr_ma60 = ma60.iloc[-1]
        curr_upper = upper.iloc[-1]
        curr_v_ma5 = v_ma5.iloc[-1]
        
        # 2. 条件一: 一阳穿多线 (Cross MA60 is crucial for "Sudden")
        # 收盘站上所有均线
        above_all = (c > curr_ma5) and (c > curr_ma10) and (c > curr_ma60)
        
        # 开盘或最低价需要在至少一根均线之下 (体现"穿")，最好是穿过 MA60
        # 宽松条件: 实体穿过 MA60 (Open < MA60 < Close)
        cross_ma60 = (o < curr_ma60) and (c > curr_ma60)
        
        if not (above_all and cross_ma60):
            return None
            
        # 3. 条件二: 量能放大
        # 比如 > 1.8倍的5日均量
        if v < curr_v_ma5 * 1.8:
            return None
            
        # 4. 条件三: 直达 Upper (High 接近 Upper)
        if h < curr_upper * 0.97: 
            return None
            
        # 5. 条件四 (可选): 涨幅显著 (>3%)
        pct = df['percent'].iloc[-1]
        if pct < 3.0:
            return None
            
        return SignalPoint(
            code=code,
            signal_type=SignalType.BUY,
            timestamp=curr_idx,
            bar_index=len(df)-1,
            price=c,
            source=SignalSource.STRATEGY_ENGINE,
            reason=f"突发启动: 一阳穿三线, 量比{v/curr_v_ma5:.1f}"
        )

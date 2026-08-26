# -*- coding: utf-8 -*-
"""
EarlyStabilizationPioneerStrategy - 逆势企稳先锋策略

专门捕捉在弱市/震荡市中：
1. 底部结构提前企稳 (前低不破、底抬高 Higher Lows)
2. 均线系统紧密收敛 (MA5/10/20 粘合)
3. 资金量能先行 (OBV 拐头向上、量能温和放大)
4. 首阳突破颈线/均线 (一阳穿多线、突破箱体)
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from strategy_interface import IStrategy, StrategyConfig
from signal_types import SignalPoint, SignalType, SignalSource
from signal_message_queue import SignalMessage, SignalMessageQueue
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)


class EarlyStabilizationPioneerStrategy(IStrategy):
    """
    逆势企稳先锋策略 (Early Stabilization Pioneer)
    
    逻辑：
    - 阶段筑底不破底/底抬高 (Higher Lows)
    - 均线收敛走平 (MA5/10/20 Squeeze)
    - OBV/量能先行异动
    - 突破颈线与均线加速启动
    """

    def __init__(self, config: Optional[StrategyConfig] = None, executor: Optional[Any] = None):
        super().__init__(config)
        self.executor = executor
        if not self._config.description:
            self._config.description = "捕捉逆势企稳、底抬高、均线收敛后放量突破先锋形态"

        try:
            self.queue = SignalMessageQueue()
        except Exception:
            self.queue = None

    def evaluate_historical(self, code: str, day_df: pd.DataFrame, 
                            index_df: Optional[pd.DataFrame] = None) -> List[SignalPoint]:
        """
        历史回测 / 日K线全扫描评估
        """
        points: List[SignalPoint] = []
        if day_df is None or len(day_df) < 30:
            return points

        # 对最近 K 线检测是否符合先锋启动形态
        sig = self._detect_pattern(code, day_df, idx=-1, index_df=index_df)
        if sig:
            points.append(sig)

            # 当天触发时异步推入消息队列
            if str(sig.timestamp) == str(day_df.index[-1]) and self.queue:
                try:
                    name = str(day_df.iloc[-1].get('name', code))
                    msg = SignalMessage(
                        priority=10,  # 高优先级
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        code=code,
                        name=name,
                        signal_type='PIONEER_BREAKOUT',
                        source='STRATEGY',
                        reason=sig.reason,
                        score=95
                    )
                    self.queue.push(msg)
                except Exception as e:
                    logger.error(f"推送逆势先锋信号失败: {e}")

        return points

    def evaluate_realtime(self, code: str, row_data: Dict[str, Any], 
                          snapshot: Dict[str, Any]) -> Optional[SignalPoint]:
        """
        日内实时分时点火与突破评估
        """
        try:
            cur_price = float(row_data.get('trade', 0.0) or row_data.get('close', 0.0) or 0.0)
            high_price = float(row_data.get('high', 0.0) or 0.0)
            open_price = float(row_data.get('open', 0.0) or 0.0)
            percent = float(row_data.get('percent', 0.0) or row_data.get('pct_chg', 0.0) or 0.0)
            volume_ratio = float(row_data.get('volume_ratio', 0.0) or row_data.get('ratio', 1.0) or 1.0)
            ma20 = float(row_data.get('ma20', 0.0) or 0.0)
            prev_high = float(row_data.get('prev_high', 0.0) or 0.0)
            
            # 日内启动点火条件：
            # 1. 涨幅在 2.5% 以上
            # 2. 量比放大 (> 1.6)
            # 3. 价格在分时高位运行，突破昨高及 MA20
            if percent >= 2.5 and volume_ratio >= 1.6 and cur_price > 0:
                if ma20 > 0 and cur_price > ma20 and (prev_high <= 0 or cur_price >= prev_high):
                    reason = f"🚀【逆势先锋盘中启动】涨幅 +{percent:.2f}%, 量比 {volume_ratio:.2f}, 突破MA20/昨高"
                    return SignalPoint(
                        code=code,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        bar_index=-1,
                        price=cur_price,
                        signal_type=SignalType.BUY,
                        source=SignalSource.STRATEGY_ENGINE,
                        reason=reason,
                        debug_info={
                            "percent": percent,
                            "volume_ratio": volume_ratio,
                            "cur_price": cur_price,
                            "ma20": ma20
                        }
                    )
        except Exception as e:
            logger.debug(f"evaluate_realtime 异常 ({code}): {e}")
        return None

    def _detect_pattern(self, code: str, df: pd.DataFrame, idx: int = -1,
                        index_df: Optional[pd.DataFrame] = None) -> Optional[SignalPoint]:
        """
        核心形态检测：
        1. 阶段底不破底 / 底抬高 (Higher Lows)
        2. 均线收敛粘合 (MA5/10/20)
        3. OBV先行向上金叉
        4. 突破平台/一阳穿多线
        """
        try:
            if len(df) < 30:
                return None

            close = df['close']
            low = df['low']
            high = df['high']
            volume = df['volume']
            open_p = df['open']

            # 计算均线
            ma5 = close.rolling(5).mean()
            ma10 = close.rolling(10).mean()
            ma20 = close.rolling(20).mean()
            v_ma5 = volume.rolling(5).mean()

            # 计算 OBV
            change = close.diff().fillna(0)
            direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
            obv = (direction * volume).cumsum()
            ma_obv10 = obv.rolling(10).mean()

            c = close.iloc[idx]
            o = open_p.iloc[idx]
            h = high.iloc[idx]
            l = low.iloc[idx]
            v = volume.iloc[idx]
            curr_ma5 = ma5.iloc[idx]
            curr_ma10 = ma10.iloc[idx]
            curr_ma20 = ma20.iloc[idx]
            curr_v_ma5 = v_ma5.iloc[idx]
            curr_obv = obv.iloc[idx]
            curr_ma_obv = ma_obv10.iloc[idx]

            # 1. 涨幅基础过滤 (启动日涨幅 >= 3.0%)
            prev_c = close.iloc[idx - 1]
            pct_chg = (c - prev_c) / prev_c * 100
            if pct_chg < 2.8:
                return None

            # 2. 一阳穿多线 / 突破均线压制
            if not (c > curr_ma5 and c > curr_ma10 and c > curr_ma20):
                return None

            # 3. 均线收敛度校验 (启动前 1~3 天均线密集粘合)
            ma_max = max(curr_ma5, curr_ma10, curr_ma20)
            ma_min = min(curr_ma5, curr_ma10, curr_ma20)
            ma_spread = (ma_max - ma_min) / c
            if ma_spread > 0.055:  # 均线发散过大（>5.5%）排除
                return None

            # 4. 底部结构检验：底不破底 / 底抬高 (Higher Lows)
            # 在过去 25 天内，寻找前半段最低点和后半段支撑
            slice_low = low.iloc[-25:]
            min_early = slice_low.iloc[:15].min()
            min_recent = slice_low.iloc[15:].min()
            
            # 近期低点不破前期低点 (允许 1.5% 容错)
            if min_recent < min_early * 0.985:
                return None

            # 5. 量价先行指标 (OBV 向上且成交量温和放大)
            obv_turn_up = (curr_obv >= curr_ma_obv) or (curr_obv > obv.iloc[idx - 3])
            vol_boost = v >= curr_v_ma5 * 1.30  # 量能大于 5日均量 1.3 倍
            if not (obv_turn_up and vol_boost):
                return None

            # 6. 箱体/颈线突破检验 (突破前 5~10 日的整理平台高点)
            platform_high = high.iloc[-10:-1].max()
            is_breakout = (c >= platform_high * 0.985) or (h >= platform_high)

            # 7. 相对强弱背离（若有大盘数据则对比，若无则检查个股超额动量）
            is_divergent = True
            if index_df is not None and len(index_df) >= 5:
                try:
                    idx_ret3 = (index_df['close'].iloc[idx] / index_df['close'].iloc[idx - 3]) - 1
                    stk_ret3 = (c / close.iloc[idx - 3]) - 1
                    if (stk_ret3 - idx_ret3) < 0.025:  # 相对大盘超额收益不足 2.5%
                        is_divergent = False
                except Exception:
                    pass

            if not (is_breakout and is_divergent):
                return None

            # 构造触发原因与信号点
            reason = (
                f"🔥【逆势先锋启动】涨幅 +{pct_chg:.2f}%, 均线收敛穿线(MA5/10/20), "
                f"底抬高不破, OBV先行金叉, 放量突破颈线({platform_high:.2f})"
            )

            timestamp = df.index[idx]
            bar_index = len(df) - 1 if idx == -1 else idx

            return SignalPoint(
                code=code,
                timestamp=timestamp,
                bar_index=bar_index,
                price=c,
                signal_type=SignalType.BUY,
                source=SignalSource.STRATEGY_ENGINE,
                reason=reason,
                debug_info={
                    "pct_chg": pct_chg,
                    "ma_spread": round(ma_spread * 100, 2),
                    "volume_ratio_5d": round(v / curr_v_ma5, 2) if curr_v_ma5 > 0 else 1.0,
                    "platform_high": platform_high,
                    "higher_low_ratio": round(min_recent / min_early, 3) if min_early > 0 else 1.0
                }
            )
        except Exception as e:
            logger.error(f"检测逆势先锋形态异常 ({code}): {e}")
            return None

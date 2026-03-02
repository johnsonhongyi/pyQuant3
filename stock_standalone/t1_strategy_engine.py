# -*- coding: utf-8 -*-
"""
T+1 (T+0 滚动) 交易策略计算引擎
负责判断个股趋势 (主升浪 vs 震荡)、计算基于均线和ATR的支撑阻力位、并生成自动化交易指令。
"""

import pandas as pd
import numpy as np
from datetime import datetime
import logging
from typing import Dict, Any, Tuple, Union
from enum import Enum

from JohnsonUtil import LoggerFactory
# If available, use the local data provider for ATR calculation
try:
    from JSONData import tdx_data_Day as tdd
except ImportError:
    tdd = None
from JohnsonUtil import johnson_cons as ct
logger = LoggerFactory.getLogger("t1_strategy_engine")

class TrendState(Enum):
    MAIN_WAVE = "主升浪"
    OSCILLATING = "震荡行情"
    WEAK = "弱势"
    UNKNOWN = "未知"

class T1StrategyEngine:
    def __init__(self):
        # 缓存每个股票的预设目标价和ATR，避免频繁计算
        # {code: {'buy_target': float, 'sell_target': float, 'atr': float, 'trend': TrendState, 'last_update': 'YYYY-MM-DD'}}
        self.target_cache: Dict[str, Dict[str, Any]] = {}

    def _calculate_atr(self, code: str, period: int = 5,resample: str = 'd') -> float:
        """从 tdd 获取历史K线计算 ATR"""
        try:
            if tdd is None:
                return 0.0
            
            # Requesting history data
            # df_hist = tdd.get_kline_data(code, days=period + 1)
            # df_hist = tdd.get_tdx_Exp_day_to_df(code,dl=ct.Resample_LABELS_Days[resample], resample=resample, fastohlc=True)
            df_hist = tdd.get_tdx_Exp_day_to_df(code,dl=period + 1, resample=resample, fastohlc=True)

            if df_hist is None or df_hist.empty or len(df_hist) < 2:
                return 0.0

            # Calculate True Range (TR)
            df_hist['prev_close'] = df_hist['close'].shift(1)
            tr1 = df_hist['high'] - df_hist['low']
            tr2 = (df_hist['high'] - df_hist['prev_close']).abs()
            tr3 = (df_hist['low'] - df_hist['prev_close']).abs()
            
            df_hist['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = df_hist['TR'].tail(period).mean()
            return float(atr)
        except Exception as e:
            logger.debug(f">> [T1Engine] ATR calc failed for {code}: {e}")
            return 0.0

    def refresh_targets(self, code: str, snap: Union[Dict[str, Any], pd.Series], current_price: float) -> None:
        """
        每日初次加载或隔日更新时，初始化预判数据。
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        full_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cached = self.target_cache.get(code)
        
        # We want to re-evaluate targets occasionally or at least keep the time updated 
        # But if already updated today, maybe we just update the 'last_time' 
        if cached and cached.get('last_update') == today_str:
            cached['last_time'] = full_time_str
            return # Already updated today
            
        # 1. 提取或计算均线
        # 有些 snap 中已经存有 MA5d / MA10d
        ma5 = float(snap.get('ma5d', 0))
        ma10 = float(snap.get('ma10d', 0))
        ma20 = float(snap.get('ma20d', 0))
        last_close = float(snap.get('last_close', snap.get('lastp1d', current_price)))
        
        # 兜底均线计算保护 (如果外部未传入)
        if ma5 == 0 and last_close > 0:
            ma5 = last_close # Fallback
        if ma10 == 0 and last_close > 0:
            ma10 = last_close * 0.98

        # 2. 定性分析趋势 (Trend Classification)
        trend = TrendState.UNKNOWN
        if ma5 > 0 and ma10 > 0:
            if current_price > ma5 > ma10:
                # 典型的均线多头排列
                if (current_price - ma5) / ma5 > 0.02: 
                    trend = TrendState.MAIN_WAVE
                else:
                    trend = TrendState.OSCILLATING
            elif current_price < ma10:
                trend = TrendState.WEAK
            else:
                trend = TrendState.OSCILLATING
        
        # 3. 计算 ATR (近期波幅)
        atr = self._calculate_atr(code, period=5)
        if atr == 0 and current_price > 0:
            # Fallback (approximate volatility, e.g., 3%)
            atr = current_price * 0.03
            
        # 4. 计算预埋买卖点
        buy_target = 0.0
        sell_target = 0.0
        
        if trend == TrendState.MAIN_WAVE:
            # 主升浪：沿着 MA5 吸纳，卖点偏高 (让利润奔跑，用ATR止盈)
            buy_target = ma5 * 1.01  # MA5 附近一点开始接
            sell_target = current_price + atr * 1.5 # 向上期待1.5倍波幅
        elif trend == TrendState.OSCILLATING:
            # 震荡：均值回归，MA10附近低吸，上轨高抛
            buy_target = ma10 * 1.01
            sell_target = ma5 + atr * 0.8
        else:
            # 弱势：不轻易抄底，极度缩量偏离再接
            buy_target = ma10 * 0.95
            sell_target = ma5
            
        self.target_cache[code] = {
            'buy_target': round(buy_target, 2),
            'sell_target': round(sell_target, 2),
            'atr': round(atr, 2),
            'trend': trend,
            'last_update': today_str,
            'last_time': full_time_str
        }
        logger.info(f"T1 Targets established for {code}: Trend={trend.value}, Buy={buy_target:.2f}, Sell={sell_target:.2f}, ATR={atr:.2f}")

    def evaluate_t0_signal(self, code: str, row: Union[Dict[str, Any], pd.Series], snap: Union[Dict[str, Any], pd.Series], pos: Dict[str, Any]) -> Tuple[str, str, float]:
        """
        核心监控：盘中判断是否触发 T+0 自动化加减仓操作。
        Returns:
            (action, reason, target_price) 
            action defaults to 'HOLD'
        """
        current_price = float(row.get('trade', row.get('price', 0)))
        if current_price <= 0:
            return 'HOLD', "", 0.0
            
        self.refresh_targets(code, snap, current_price)
        targets = self.target_cache.get(code)
        if not targets:
            return 'HOLD', "", 0.0
            
        trend = targets['trend']
        buy_target = targets['buy_target']
        sell_target = targets['sell_target']
        atr = targets['atr']
        
        # 获取持仓信息
        cost_price = float(pos.get('entry_price', snap.get('cost_price', 0)))
        highest_today = float(row.get('high', current_price))
        
        # --- 1. 动态止盈 / 防御 (ATR Trailing Stop) ---
        # 如果从今日最高点回落超过 ATR 的风险倍数，去弱留强
        # 主升浪给的空间大一点，震荡市回落就跑
        atr_multiplier = 1.2 if trend == TrendState.MAIN_WAVE else 0.8
        trailing_stop = highest_today - (atr * atr_multiplier)
        
        if current_price < trailing_stop and current_price > cost_price * 1.01:
            # 有利润垫的情况下，触发跟踪止盈
            return 'REDUCE', f"ATR跟踪止盈 (回落突破 {atr_multiplier}ATR)", current_price

        # --- 2. 震荡市高抛低吸 (T+0预埋卖卖点) ---
        if trend == TrendState.OSCILLATING:
            # 高抛
            if current_price >= sell_target:
                # 若已经有底仓，触及阻力位减仓 T 出
                if current_price > cost_price * 1.02: # 至少有T的利润空间
                    return 'REDUCE', f"触碰阻力预卖位 ({sell_target:.2f}) T+0高抛", current_price
            
            # 低吸 (前提是不能跌破防守线，这里可以结合 VWAP 确认企稳)
            nclose = float(row.get('nclose', 0)) # VWAP
            if current_price <= buy_target and current_price > nclose:
                return 'ADD', f"触碰支撑预买位 ({buy_target:.2f}) T+0吸纳", current_price

        # --- 3. 主升浪顺势加仓 ---
        if trend == TrendState.MAIN_WAVE:
            # 缩量回踩 MA5 买入
            if current_price <= buy_target and current_price >= buy_target * 0.98:
                # 需结合分时图，如果在此停留企稳可加仓 (简单逻辑：当前不大幅跌破均价)
                nclose = float(row.get('nclose', 0))
                if current_price >= nclose * 0.995: 
                    return 'ADD', f"主升浪回踩企稳 ({buy_target:.2f}) 顺势加仓", current_price

        return 'HOLD', "", 0.0

if __name__ == '__main__':
    # 配置基础日志以查看打印
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("--- 测试 T1StrategyEngine ---")
    engine = T1StrategyEngine()
    test_code = '000001' #平安银行
    
    # 模拟外部快照数据
    snap_data = {
        'ma5d': 10.5,
        'ma10d': 10.2,
        'last_close': 10.4
    }
    test_price = 10.6
    
    print(f"\n1. 测试 refresh_targets ({test_code})")
    engine.refresh_targets(test_code, snap_data, test_price)
    
    targets = engine.target_cache.get(test_code)
    print(f"缓存计算结果: {targets}")
    
    print("\n2. 测试 evaluate_t0_signal (模拟主升浪中回调企稳加仓)")
    row_data = {
        'trade': 10.4, # 价格回撤到MA5附近
        'high': 10.8,
        'nclose': 10.4  # VWAP 约 10.4
    }
    pos_info = {'entry_price': 10.2}
    
    action, reason, target_price = engine.evaluate_t0_signal(test_code, row_data, snap_data, pos_info)
    print(f"T+0 判断结果: 行动={action}, 当下价格={target_price}, 理由={reason}")

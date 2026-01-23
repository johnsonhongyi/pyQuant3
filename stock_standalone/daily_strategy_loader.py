# -*- coding: utf-8 -*-
"""
Daily Strategy Loader
策略加载器：将离线选股结果(StockSelector) 转换为 在线跟单任务(TradingHub)

功能：
1. 运行 StockSelector 获取今日潜力股
2. 根据选股理由映射交易策略 (竞价/回踩/突破)
3. 注入 TradingHub.follow_queue 供 StockLiveStrategy 实时监控

Run typical time: 09:00 - 09:20
"""
import logging
from datetime import datetime
from typing import List, Dict

from stock_selector import StockSelector
from trading_hub import get_trading_hub, TrackedSignal, EntryStrategy
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger(name="StrategyLoader")

def map_reason_to_strategy(reason: str, pct: float) -> str:
    """
    根据选股理由映射入场策略
    """
    reason = str(reason)
    
    if "缩量企稳" in reason or "建议:低吸" in reason:
        return "回踩MA5"
    
    if "放量突破" in reason or "建议:右侧" in reason:
        return "突破买入"
        
    if "新晋热股" in reason or "连涨" in reason:
        return "竞价买入" # 激进策略
        
    # 默认策略
    return "回踩MA5"

def load_daily_strategies(force_run: bool = False, min_score: int = 45):
    """
    加载每日策略到跟单队列
    """
    logger.info("开始加载每日策略...")
    
    # 1. 运行选股器
    selector = StockSelector()
    # force=True 确保如果是开盘前重新计算
    df = selector.get_candidates_df(force=force_run)
    
    if df.empty:
        logger.warning("今日无选股结果")
        return

    # [NEW] 初始化形态检测器
    from daily_pattern_detector import DailyPatternDetector
    from JSONData.tdx_hdf5_api import load_hdf_db
    pattern_detector = DailyPatternDetector()

    # 1.5 预加载候选股的历史数据
    all_codes = [str(r['code']).zfill(6) for _, r in df.iterrows()]
    df_hist = load_hdf_db("all_30.h5", table='all', code_l=all_codes)

    hub = get_trading_hub()
    today_str = datetime.now().strftime("%Y-%m-%d")
    count = 0
    
    # 2. 遍历结果并转换
    for _, row in df.iterrows():
        try:
            score = float(row.get('score', 0))
            if score < min_score:
                continue
                
            code = str(row['code']).zfill(6)
            name = str(row.get('name', ''))
            reason = str(row.get('reason', ''))
            price = float(row.get('price', 0))
            
            # [NEW] 结合历史K线进行形态校验
            prev_rows = df_hist.loc[[code]] if df_hist is not None and code in df_hist.index else None
            
            # 利用形态检测器建议策略
            v_shape = pattern_detector.check_volunteer(code, row, prev_rows)
            platform = pattern_detector.check_platform_break(code, row, prev_rows)
            
            # 策略映射
            strategy = map_reason_to_strategy(reason, float(row.get('percent', 0)))

            # 强化策略逻辑
            if v_shape:
                strategy = "V型反转" # 优先级高
                reason += " | [检测] V型反转"
            elif platform:
                strategy = "平台突破"
                reason += " | [检测] 平台突破"
            elif "新晋热股" in reason:
                strategy = "竞价买入"
            
            # 构建信号对象
            # 止损位默认设置：当前价 - 5% (可优化为技术位)
            stop_loss = price * 0.95
            
            signal = TrackedSignal(
                code=code,
                name=name,
                signal_type="每日精选", # Source type
                detected_date=today_str,
                detected_price=price,
                entry_strategy=strategy,
                target_price_low=price * 0.98, # 默认区间
                target_price_high=price * 1.02,
                stop_loss=stop_loss,
                status="TRACKING",
                priority=int(score / 10), # 60分->6, 80分->8
                source="StockSelector",
                notes=f"[AUTO] {reason}"
            )
            
            # 3. 注入 TradingHub
            if hub.add_to_follow_queue(signal):
                count += 1
                logger.info(f"已加载: {code} {name} [{strategy}] Score:{score}")
                
        except Exception as e:
            logger.error(f"处理 {row.get('code')} 失败: {e}")
            
    logger.info(f"策略加载完成，共注入 {count} 条跟单任务")

if __name__ == "__main__":
    # 手动运行时强制刷新
    load_daily_strategies(force_run=False)

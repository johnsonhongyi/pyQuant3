# -*- coding: utf-8 -*-
"""
ats/strategy/ipo_market_sentiment_engine.py
--------------------------------------------
全市场情绪感知与新股次新股量能共振引擎
核心职责：
1. 【大盘量能与周期判别】：
   - 提取上证指数 (999999/000001) 与创业板指 (399006) 实时成交量与 5 日均量；
   - 识别【绝望地量期】(成交量萎缩至冰点，主力逆市建仓潜伏新股)；
   - 识别【放量主升共振期】(大盘中阳放量反弹，新股梯队扩散爆发)；
   - 识别【高潮天量派发期】(放天量滞涨，获利盘兑现警报)。
2. 【新股次新梯队情绪感知】：
   - 统计样本池整体红盘率、VWAP 站稳率、平均涨幅、大涨(>+5%)占比；
   - 产出情绪风向标状态：❄️ 冰点极寒 -> 🌱 绝望孕育 -> 🔥 梯队升温 -> 🌋 狂热高潮。
3. 【纯内存无锁高性能】：
   - 复用 TDXRealtimeFetcher 底层缓存，单次计算 < 1ms，零主线程 I/O。
"""

import os
import sys
import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

logger = logging.getLogger("IPOMarketSentiment")


@dataclass
class MarketSentimentSnapshot:
    """全市场与新股情绪快照"""
    # 大盘指标
    sh_amount_yi: float = 0.0          # 上证成交额(亿元)
    sh_volume_ratio: float = 1.0       # 上证相比前日/均量比率
    index_phase: str = "温和放量"       # 绝望地量 / 温和放量 / 爆发共振 / 天量高潮
    index_desc: str = ""               # 大盘量能描述
    
    # 新股次新板块指标
    ipo_count: int = 0                 # 监控新股总数
    red_ratio: float = 0.0             # 红盘比例 (0~100%)
    vwap_hold_ratio: float = 0.0       # 站上 VWAP 比例 (0~100%)
    avg_change_pct: float = 0.0        # 平均涨跌幅%
    surge_count: int = 0               # 涨幅 > 5% 标的数量
    heat_stage: str = "🔥 梯队升温"    # 冰点极寒 / 绝望孕育 / 梯队升温 / 狂热高潮
    heat_score: float = 65.0           # 情绪热度综合评分 (0~100)
    
    # 策略执行指引
    strategy_guide: str = ""           # 综合操盘指引
    update_time: str = ""              # 更新时间戳


class IPOMarketSentimentEngine:
    """全市场与新股情绪感知单例引擎"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.fetcher = TDXRealtimeFetcher.get_instance()
        self._cached_snapshot: Optional[MarketSentimentSnapshot] = None
        self._last_calc_ts: float = 0.0
        self._cache_ttl: float = 3.0  # 3 秒内存缓存

    def get_market_sentiment(self, ipo_signals: Optional[List[Any]] = None, force_refresh: bool = False) -> MarketSentimentSnapshot:
        """获取最新市场情绪感知快照 (带 3s 内存防抖缓存)"""
        now_ts = time.time()
        if not force_refresh and self._cached_snapshot is not None:
            if now_ts - self._last_calc_ts < self._cache_ttl:
                return self._cached_snapshot

        snap = MarketSentimentSnapshot(update_time=time.strftime("%H:%M:%S"))

        # 1. 评估大盘指数成交量与量能阶段
        self._evaluate_index_volume(snap)

        # 2. 评估新股次新梯队热度
        self._evaluate_ipo_ladder_heat(snap, ipo_signals)

        # 3. 综合生成战略执行指引
        self._synthesize_strategy_guide(snap)

        self._cached_snapshot = snap
        self._last_calc_ts = now_ts
        return snap

    def _evaluate_index_volume(self, snap: MarketSentimentSnapshot):
        """评估上证/创业板成交量与地量/放量周期"""
        try:
            # 优先从快照或日线读取上证指数
            sh_snap = self.fetcher.fetch_stock_snapshot("999999")
            if not sh_snap or not isinstance(sh_snap, dict):
                sh_snap = self.fetcher.fetch_stock_snapshot("000001")

            amount_yi = 0.0
            vol_ratio = 1.0
            if sh_snap and isinstance(sh_snap, dict):
                amt = float(sh_snap.get("amount", 0.0))
                if amt > 0:
                    amount_yi = round(amt / 100000000.0, 1)
                vr = float(sh_snap.get("vol_ratio", sh_snap.get("volume_ratio", 1.0)))
                if vr > 0:
                    vol_ratio = round(vr, 2)

            snap.sh_amount_yi = amount_yi
            snap.sh_volume_ratio = vol_ratio

            # 判定大盘所处量能周期
            # 绝望地量: 量比 < 0.82 或 成交量极度萎缩
            if vol_ratio <= 0.82:
                snap.index_phase = "绝望地量"
                snap.index_desc = f"大盘缩量至地量低谷(量比{vol_ratio:.2f})，绝望孕育期，主力逆市建仓新股"
            elif vol_ratio >= 1.45:
                snap.index_phase = "爆发共振"
                snap.index_desc = f"大盘放量中阳爆发(量比{vol_ratio:.2f})，情绪主升顶峰共振"
            elif vol_ratio >= 2.2:
                snap.index_phase = "天量高潮"
                snap.index_desc = f"大盘放天量冲顶(量比{vol_ratio:.2f})，警惕尾盘或次日获利兑现"
            else:
                snap.index_phase = "温和放量"
                snap.index_desc = f"大盘温和放量运行(量比{vol_ratio:.2f})，多头赛马博弈"
        except Exception as e:
            logger.debug(f"评估大盘指数成交量异常: {e}")
            snap.index_phase = "温和放量"
            snap.index_desc = "大盘运行平稳"

    def _evaluate_ipo_ladder_heat(self, snap: MarketSentimentSnapshot, ipo_signals: Optional[List[Any]]):
        """评估新股次新梯队热度 (红盘率、VWAP站稳率、活跃度)"""
        if not ipo_signals:
            snap.heat_stage = "🔥 梯队升温"
            snap.heat_score = 65.0
            return

        valid_sigs = [s for s in ipo_signals if s and getattr(s, "price", 0.0) > 0]
        snap.ipo_count = len(valid_sigs)
        if not valid_sigs:
            return

        red_count = 0
        vwap_hold_count = 0
        surge_count = 0
        total_chg = 0.0

        for s in valid_sigs:
            chg = getattr(s, "change_pct", 0.0)
            total_chg += chg
            if chg > 0:
                red_count += 1
            if chg >= 5.0:
                surge_count += 1
            if getattr(s, "is_above_vwap", False):
                vwap_hold_count += 1

        n = len(valid_sigs)
        snap.red_ratio = round(red_count / n * 100.0, 1)
        snap.vwap_hold_ratio = round(vwap_hold_count / n * 100.0, 1)
        snap.avg_change_pct = round(total_chg / n, 2)
        snap.surge_count = surge_count

        # 综合计算情绪热度分 (0~100)
        score = (snap.red_ratio * 0.35 + snap.vwap_hold_ratio * 0.40 + min(snap.avg_change_pct * 3.0, 25.0))
        snap.heat_score = round(max(0.0, min(score, 100.0)), 1)

        if snap.heat_score >= 80.0 or snap.surge_count >= 8:
            snap.heat_stage = "🌋 狂热高潮"
        elif snap.heat_score >= 60.0 or snap.red_ratio >= 65.0:
            snap.heat_stage = "🔥 梯队升温"
        elif snap.heat_score >= 40.0:
            snap.heat_stage = "🌱 绝望孕育"
        else:
            snap.heat_stage = "❄️ 冰点极寒"

    def _synthesize_strategy_guide(self, snap: MarketSentimentSnapshot):
        """生成操盘指引"""
        if snap.heat_stage == "🌋 狂热高潮":
            snap.strategy_guide = "新股情绪达狂热顶峰，警惕高潮天量兑现！有持仓逢高锁定利润，严禁追高，防T+1反噬！"
        elif snap.heat_stage == "🔥 梯队升温":
            snap.strategy_guide = "新股梯队赛马共振升温中！早盘优先选择早起爆、VWAP线上贴线惜售的领头羊进击！"
        elif snap.index_phase == "绝望地量" or snap.heat_stage == "🌱 绝望孕育":
            snap.strategy_guide = "市场处于绝望地量潜伏期！跟随主力暗中建仓，在 VWAP 走平 1~3 天回踩不破处预下单潜伏！"
        else:
            snap.strategy_guide = "市场震荡轮动，严格执行买在 VWAP 之上、买错破 VWAP 立即出局的极窄风控！"

# auction_decision_engine.py
# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import logging
from market_sentiment_fsm import MarketSentimentFSM, BiddingSnapshot, SentimentState

logger = logging.getLogger("AuctionDecisionEngine")

@dataclass(frozen=True)
class AuctionSignal:
    code: str
    name: str
    sector: str
    signal_type: str        # 'REVERSAL_BUY', 'REPAIR_BUY', 'FOMO_CHASE'
    price: float
    pct: float
    score: float
    confidence: float
    rule_id: str
    metadata: dict


class AuctionDecisionEngine:
    def __init__(self, fsm: MarketSentimentFSM):
        self.fsm = fsm
        self.last_state: SentimentState = SentimentState.NEUTRAL
        self.last_signals: List[AuctionSignal] = []

    def generate_signals(self, bidding: BiddingSnapshot) -> List[AuctionSignal]:
        """
        根据竞价瞬时快照与当前情绪状态，生成高可信度的竞价开仓信号。
        """
        self.last_signals = []
        
        # 1. 触发 FSM 状态更新
        state = self.fsm.classify(bidding)
        self.last_state = state
        
        explain = self.fsm.explain_state()
        logger.info(f"[DecisionEngine] Pre-market Sentiment: {state.value} | matched: {explain.get('matched_rules')}")
        
        # 2. 状态硬拦截：如果处于 PANIC 或 COOLDOWN，强行短路保护，不产生任何开仓信号
        if state in (SentimentState.PANIC, SentimentState.COOLDOWN):
            logger.info(f"[DecisionEngine] Market is in {state.value}. Risk control active: 0 pre-market signals generated.")
            return []
            
        # 3. 提取竞价股票并排序 (按得分)
        bidding_stocks = sorted(bidding.stock_snap.values(), key=lambda x: x.get('score', 0.0), reverse=True)
        
        # 构造板块到个股的映射
        sector_to_stocks = {}
        for s in bidding.active_sectors:
            sector_to_stocks[s.name] = s
            
        # 昨天最弱板块
        yesterday_worst = self.fsm._yesterday_worst_sectors
        
        signals = []
        
        # 活跃板块（持续性依据）：仅从当前被资金持续认可的活跃板块中挖掘
        current_active_sector_names = {s.name for s in bidding.active_sectors}
        
        # 4. 根据不同情绪状态运行不同决策子模块
        if state == SentimentState.REVERSAL:
            # 情绪反转开仓策略：
            # 寻找属于昨日大跌板块的个股，且昨日个股大跌，今日竞价表现出强劲拉升或抢筹迹象。
            for s in bidding_stocks:
                code = s.get('code', '')
                name = s.get('name', '')
                sector = s.get('category', '')
                score = s.get('score', 0.0)
                pct = s.get('pct', 0.0)
                price = s.get('price', 0.0)
                is_untradable = s.get('is_untradable', False)
                yesterday_pct = s.get('yesterday_pct', s.get('prev_pct', 0.0))
                dff = s.get('dff', 0.0)
                vol_ratio = s.get('volume_ratio', s.get('vol_ratio', 0.0))
                
                if is_untradable or not code:
                    continue
                    
                # 校验个股是否属于昨日最惨板块之一
                is_target_sector = False
                matched_sector = ""
                for sec_name in yesterday_worst:
                    if sec_name in sector:
                        is_target_sector = True
                        matched_sector = sec_name
                        break
                        
                if is_target_sector:
                    # 反转个股条件：开盘抢筹幅度和强度达标
                    # 昨跌 <= -3%, 今日高开 0.0 ~ 4.0%, dff > 0 或 放量
                    if yesterday_pct <= -3.0 and 0.0 < pct < 4.0 and score >= 75.0 and (dff > 0 or vol_ratio >= 1.5):
                        if matched_sector not in current_active_sector_names:
                            continue # 过滤缺乏持续性的板块
                            
                        meta = {
                            "matched_sector": matched_sector,
                            "yesterday_sector_pct": getattr(self.fsm._sector_record_by_name.get(matched_sector), 'avg_pct', 0.0),
                            "stock_pct": pct,
                            "stock_score": score,
                            "yesterday_pct": yesterday_pct,
                            "dff": dff
                        }
                        signals.append(AuctionSignal(
                            code=code,
                            name=name,
                            sector=sector,
                            signal_type='情绪反转买入',
                            price=price,
                            pct=pct,
                            score=score,
                            confidence=0.85,
                            rule_id='大跌板块错杀反转',
                            metadata=meta
                        ))

        elif state == SentimentState.REPAIR:
            # 修复期策略：
            # 板块有大资金介入修复，个股竞价走高，开盘直接买入最强的龙头/排头兵。
            repaired_sectors = explain.get("repaired_worst_sectors", [])
            for s in bidding_stocks:
                code = s.get('code', '')
                name = s.get('name', '')
                sector = s.get('category', '')
                score = s.get('score', 0.0)
                pct = s.get('pct', 0.0)
                price = s.get('price', 0.0)
                is_untradable = s.get('is_untradable', False)
                
                if is_untradable or not code:
                    continue
                    
                # 寻找属于修复板块且得分强劲的个股
                is_repaired_sector = False
                for r_sec in repaired_sectors:
                    if r_sec in sector:
                        is_repaired_sector = True
                        break
                        
                if is_repaired_sector:
                    # 个股必须开盘高于昨日收盘价且高开合理 (0.5% 到 5.0%)，得分 > 80.0
                    if 0.5 <= pct <= 5.0 and score >= 80.0:
                        if sector not in current_active_sector_names:
                            continue
                            
                        meta = {
                            "repaired_sector": sector,
                            "stock_pct": pct,
                            "stock_score": score
                        }
                        signals.append(AuctionSignal(
                            code=code,
                            name=name,
                            sector=sector,
                            signal_type='修复抢筹买入',
                            price=price,
                            pct=pct,
                            score=score,
                            confidence=0.75,
                            rule_id='错杀主线修复抢筹',
                            metadata=meta
                        ))

        # 独立评估主线强延续 CONTINUATION_BUY
        yesterday_top = self.fsm._yesterday_top_sectors
        if state != SentimentState.FOMO:
            for s in bidding_stocks:
                code = s.get('code', '')
                name = s.get('name', '')
                sector = s.get('category', '')
                score = s.get('score', 0.0)
                pct = s.get('pct', 0.0)
                price = s.get('price', 0.0)
                is_untradable = s.get('is_untradable', False)
                yesterday_pct = s.get('yesterday_pct', s.get('prev_pct', 0.0))
                is_limit_up = yesterday_pct >= 9.8
                
                if is_untradable or not code:
                    continue
                    
                is_top_sector = False
                for sec_name in yesterday_top:
                    if sec_name in sector:
                        is_top_sector = True
                        break
                        
                if is_top_sector and (yesterday_pct >= 3.0 or is_limit_up):
                    if -1.0 < pct < 5.0 and score >= 85.0:  # 强延续且未大幅低开，也未过度高开
                        if sector not in current_active_sector_names:
                            continue
                            
                        meta = {
                            "matched_sector": sector,
                            "stock_pct": pct,
                            "stock_score": score,
                            "yesterday_pct": yesterday_pct
                        }
                        signals.append(AuctionSignal(
                            code=code,
                            name=name,
                            sector=sector,
                            signal_type='主线强延续买入',
                            price=price,
                            pct=pct,
                            score=score,
                            confidence=0.80,
                            rule_id='最强主线龙头延续',
                            metadata=meta
                        ))
                        
        elif state == SentimentState.FOMO:
            # 开盘极度过热：限制买入，仅对绝对领先、一字涨停无法买入之外的最强成交前3名标的产生轻仓追高信号
            # 且要求个股竞价得分极高 (>= 92.0)，涨幅合理 (5% 到 8.5% 之间)
            count = 0
            for s in bidding_stocks:
                code = s.get('code', '')
                name = s.get('name', '')
                sector = s.get('category', '')
                score = s.get('score', 0.0)
                pct = s.get('pct', 0.0)
                price = s.get('price', 0.0)
                is_untradable = s.get('is_untradable', False)
                
                if is_untradable or not code:
                    continue
                    
                if 5.0 <= pct <= 8.5 and score >= 92.0:
                    meta = {
                        "fomo_level": "HIGH",
                        "stock_pct": pct,
                        "stock_score": score
                    }
                    signals.append(AuctionSignal(
                        code=code,
                        name=name,
                        sector=sector,
                        signal_type='FOMO_CHASE',
                        price=price,
                        pct=pct,
                        score=score,
                        confidence=0.60,
                        rule_id='FOMO_EXCESSIVE_STRENGTH_CHASE',
                        metadata=meta
                    ))
                    count += 1
                    if count >= 3:
                        break
                        
        # 对生成的信号做截断，单次竞价阶段信号总量不超过 3 只，防范资金过度暴露
        signals = sorted(signals, key=lambda x: x.score, reverse=True)[:3]
        self.last_signals = signals
        return signals


def map_auction_signal_to_dict(sig: AuctionSignal) -> dict:
    """
    将竞价信号映射为 Trading Kernel 的 decision_queue 可接受的标准 dict 格式。
    """
    from datetime import datetime
    return {
        "code": sig.code,
        "name": sig.name,
        "signal_type": sig.signal_type,
        "suggest_price": sig.price,
        "current_price": sig.price,
        "change_pct": sig.pct,
        "pct_diff": sig.pct,
        "priority": sig.score,
        "sector": sig.sector,
        "action": "BUY",
        "reason": f"情绪与竞价决策: {sig.rule_id}",
        "created_at": datetime.now().isoformat(timespec="seconds")
    }


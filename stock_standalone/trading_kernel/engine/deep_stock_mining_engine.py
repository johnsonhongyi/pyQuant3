# -*- coding: utf-8 -*-
"""
Deep Stock Mining Engine (牛股深度挖掘引擎)

专注于挖掘具有大行情基因的顶级标的:
1. 筹码高度集中与获利锁定 (Chip Distribution)
2. 市场 Top 3 最强主线与龙头共振 (Sector & Dragon Leader Resonance)
3. 平台极窄缩量蓄势与放量临界突破 (Consolidation & Explosion Breakout)
4. 主力资金 DFF 持续大举净流入与动量梯级爆发 (Fund Inflow & Momentum)

彻底杜绝毫无目的的频繁买卖。未通过深度挖掘评估的标的一律判定为观望。
"""

from __future__ import annotations

import math
from typing import Dict, Any, Tuple
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("DeepStockMiningEngine")


class DeepStockMiningEngine:
    """
    牛股深度挖掘引擎
    """

    @classmethod
    def evaluate_stock_mining(cls, ctx: Dict[str, Any]) -> Tuple[bool, float, Dict[str, Any]]:
        """
        对个股进行全维度的深度牛股挖掘评估

        Args:
            ctx: 上下文特征数据字典

        Returns:
            Tuple[is_mined_target, mining_score, mining_details]
            - is_mined_target: 是否达到深度挖掘资质 (>= 78分)
            - mining_score: 综合挖掘评分 (0-100)
            - mining_details: 挖掘维度明细
        """
        # 1. 筹码集中与获利因子评估 (权重 25分)
        chip_score, chip_detail = cls._eval_chip_distribution(ctx)

        # 2. 板块主线与龙头共振因子评估 (权重 25分)
        sector_score, sector_detail = cls._eval_sector_dragon_resonance(ctx)

        # 3. 平台缩量蓄势与临界突破因子评估 (权重 25分)
        breakout_score, breakout_detail = cls._eval_consolidation_breakout(ctx)

        # 4. 主力资金流向与动量梯级爆发因子评估 (权重 25分)
        fund_score, fund_detail = cls._eval_fund_inflow_momentum(ctx)

        total_score = round(chip_score + sector_score + breakout_score + fund_score, 2)
        
        # 门槛设定：综合得分 >= 78分 判定为符合深度挖掘的牛股候选
        is_mined_target = bool(total_score >= 78.0)

        mining_details = {
            "chip_score": chip_score,
            "chip_detail": chip_detail,
            "sector_score": sector_score,
            "sector_detail": sector_detail,
            "breakout_score": breakout_score,
            "breakout_detail": breakout_detail,
            "fund_score": fund_score,
            "fund_detail": fund_detail,
            "total_score": total_score,
            "is_mined_target": is_mined_target,
        }

        if is_mined_target:
            import time
            now_ts = time.time()
            code = ctx.get("code", ctx.get("symbol", ""))
            name = ctx.get("name", "")
            
            if not hasattr(cls, "_mined_alert_cache"):
                cls._mined_alert_cache = {}
                
            cache_key = f"{code}_mined" if code else f"{total_score}_mined"
            last_ts = cls._mined_alert_cache.get(cache_key, 0.0)
            if now_ts - last_ts >= 1800.0:  # 30分钟防抖
                cls._mined_alert_cache[cache_key] = now_ts
                logger.info(f"💎 成功挖掘出牛股标的! 代码={code} 名称={name} 得分={total_score} | 明细={mining_details}")

        return is_mined_target, total_score, mining_details

    @classmethod
    def _eval_chip_distribution(cls, ctx: Dict[str, Any]) -> Tuple[float, str]:
        """评估筹码集中度与获利锁定比例"""
        score = 0.0
        reasons = []

        profit_ratio = float(ctx.get("profit_ratio", ctx.get("winner_rate", 0.0)))
        chip_concentration = float(ctx.get("chip_concentration", 0.0))
        price = float(ctx.get("price", 0.0))
        ma20 = float(ctx.get("ma20d", 0.0))
        ma60 = float(ctx.get("ma60d", 0.0))

        # 1.1 获利盘比例评估: 高获利盘(>85%)代表主升顺畅; 极低获利盘(<20%)且放量突破代表无短期获利盘抛压区起爆
        if profit_ratio >= 85.0 or (profit_ratio <= 1.0 and profit_ratio >= 0.85):
            score += 10.0
            reasons.append("获利筹码比例极高(>85%)")
        elif profit_ratio >= 70.0 or (profit_ratio <= 1.0 and profit_ratio >= 0.70):
            score += 6.0
            reasons.append("获利筹码良好(>70%)")
        elif profit_ratio < 20.0 or (0.0 < profit_ratio <= 0.20):
            pct_diff = float(ctx.get("pct_diff", 0.0))
            vol_ratio = float(ctx.get("vol_ratio", 1.0))
            dff = float(ctx.get("dff", 0.0))
            if (pct_diff > 3.5 or vol_ratio >= 1.5) and dff >= 0:
                score += 12.0
                reasons.append("无短期获利盘抛压区+主力资金异动爆发(起爆底座)")

        # 1.2 价格站稳中期主力成本线（MA20/MA60）或底座爆发
        if price > 0 and ma20 > 0 and price >= ma20 * 0.99:
            score += 8.0
            reasons.append("价格站稳MA20成本线/底座")
            if ma60 > 0 and ma20 >= ma60 * 0.99:
                score += 4.0
                reasons.append("MA20/MA60支撑区")
        
        # 1.3 无上方密集解套套牢峰压制
        is_consolidation = bool(ctx.get("is_consolidation_stage", False))
        if not is_consolidation:
            score += 3.0

        detail_str = "; ".join(reasons) if reasons else "筹码分布一般"
        return min(score, 25.0), detail_str

    @classmethod
    def _eval_sector_dragon_resonance(cls, ctx: Dict[str, Any]) -> Tuple[float, str]:
        """评估热点主线板块与龙头地位"""
        score = 0.0
        reasons = []

        sector_heat = float(ctx.get("sector_heat", 0.0))
        is_leader = bool(ctx.get("is_leader", False))
        priority = float(ctx.get("priority", 0.0))
        sector_rank = ctx.get("sector_rank")

        # 2.1 属于 Top 3 / 最强热点板块 (sector_heat >= 75)
        if sector_heat >= 80.0:
            score += 12.0
            reasons.append("所属板块处于极高热度主线(>=80)")
        elif sector_heat >= 60.0:
            score += 7.0
            reasons.append("所属板块处于热点主线(>=60)")

        # 2.2 龙头地位 (Dragon Leader) 显著加分
        if is_leader or priority >= 85.0:
            score += 10.0
            reasons.append("板块核心龙头/极高优先级")
        elif priority >= 70.0:
            score += 5.0
            reasons.append("板块中坚标的")

        # 2.3 龙头排名靠前 (Rank <= 5)
        if sector_rank is not None:
            try:
                rank_val = int(sector_rank)
                if rank_val <= 3:
                    score += 3.0
                    reasons.append("板块龙头Rank前3")
            except Exception:
                pass

        detail_str = "; ".join(reasons) if reasons else "非主线龙头标的"
        return min(score, 25.0), detail_str

    @classmethod
    def _eval_consolidation_breakout(cls, ctx: Dict[str, Any]) -> Tuple[float, str]:
        """评估平台极窄缩量蓄势与放量临界突破"""
        score = 0.0
        reasons = []

        price = float(ctx.get("price", 0.0))
        ptop = float(ctx.get("ptop", 0.0))
        upper = float(ctx.get("upper", 0.0))
        vol_ratio = float(ctx.get("vol_ratio", 1.0))
        vol_shrink_3d = bool(ctx.get("vol_shrink_3d", False))
        is_breakout = bool(ctx.get("breakout", False)) or (ctx.get("pbreak") == 1)

        # 3.1 箱体/平台天花板临界突破
        if is_breakout or (ptop > 0 and price >= ptop * 0.995):
            score += 12.0
            reasons.append("临界突破平台高点/箱体天花板")
        elif upper > 0 and price >= upper * 0.985:
            score += 8.0
            reasons.append("挑战上轨强阻力区")

        # 3.2 突破伴随健康放量 (量比 >= 1.25) 或是前期极窄缩量洗盘后首阳
        if vol_ratio >= 1.25:
            score += 8.0
            reasons.append(f"健康放量突破(量比{vol_ratio:.2f})")
        elif vol_shrink_3d or ctx.get("is_doji", False):
            score += 5.0
            reasons.append("前期极窄缩量洗盘企稳")

        # 3.3 5日均线呈现陡峭主升向上斜率
        ma5d = float(ctx.get("ma5d", 0.0))
        ma5d_prev5 = float(ctx.get("ma5d_prev5", 0.0))
        if ma5d_prev5 > 0 and ma5d >= ma5d_prev5 * 1.01:
            score += 5.0
            reasons.append("MA5斜率陡峭向上")

        detail_str = "; ".join(reasons) if reasons else "无明显临界突破形态"
        return min(score, 25.0), detail_str

    @classmethod
    def _eval_fund_inflow_momentum(cls, ctx: Dict[str, Any]) -> Tuple[float, str]:
        """评估主力资金流向 DFF 与量能动量"""
        score = 0.0
        reasons = []

        dff = float(ctx.get("dff", 0.0))
        dff_positive = bool(ctx.get("dff_positive", dff > 0))
        pct_diff = float(ctx.get("pct_diff", 0.0))

        # 4.1 DFF 主力资金持续强劲净流入
        if dff >= 3.0:
            score += 12.0
            reasons.append(f"主力大资金大幅强劲净流入(DFF={dff:.2f})")
        elif dff_positive or dff > 0.0:
            score += 7.0
            reasons.append(f"主力资金呈净流入(DFF={dff:.2f})")

        # 4.2 动量呈现上攻形态（当日涨幅积极但不暴跌盲拉）
        if 1.0 <= pct_diff <= 7.5:
            score += 8.0
            reasons.append(f"处于黄金动量拉升带({pct_diff:.2f}%)")
        elif pct_diff > 7.5:
            score += 4.0
            reasons.append(f"强劲动量({pct_diff:.2f}%)")
        elif 0.0 <= pct_diff < 1.0:
            score += 5.0
            reasons.append("温和蓄势中")

        # 4.3 均价线 VWAP 上方强支撑
        if ctx.get("price_above_vwap", True):
            score += 5.0
            reasons.append("价格坚挺于VWAP均价线上方")

        detail_str = "; ".join(reasons) if reasons else "资金动量不足"
        return min(score, 25.0), detail_str

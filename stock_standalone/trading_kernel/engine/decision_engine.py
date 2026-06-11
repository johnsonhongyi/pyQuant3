from __future__ import annotations

import math
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("DecisionEngine")

from trading_kernel.core.intent import DecisionIntent, DecisionReason
from trading_kernel.core.signal import StrategySignal


def _num(signal: StrategySignal, key: str, default: float = 0.0) -> float:
    try:
        return float(signal.features.get(key, default))
    except Exception:
        return default


def _confidence(priority: float, sector_heat: float, pct_diff: float, dff: float) -> float:
    score = 0.0
    score += min(max(priority, 0.0), 100.0) * 0.004
    score += min(max(sector_heat, 0.0), 100.0) * 0.003
    score += min(max(pct_diff, 0.0), 8.0) * 0.025
    score += min(max(dff, 0.0), 8.0) * 0.0125
    return round(min(max(score, 0.0), 0.95), 4)


class BaseStrategyBranch:
    """策略分支虚基类"""
    name: str = "BaseBranch"
    
    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        raise NotImplementedError
        
    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        raise NotImplementedError


class SuperTrendMA5Branch(BaseStrategyBranch):
    """分支策略一：超级主升浪沿 MA5 强动量爬升与回踩挂单策略分支 (如 百合花 603823)"""
    name: str = "SuperTrendMA5Branch"
    
    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        ma5_val = ctx["ma5d"]
        ma5_prev5_val = ctx["ma5d_prev5"]
        upper = ctx["upper"]
        
        # 👑 引入极其核心的筹码回整排他逻辑：如果已经进入了深幅筹码回调整固期 (is_consolidation_stage)，则绝对不能判定为超级主升浪！
        is_consolidation = bool(ctx.get("is_consolidation_stage", False))
        
        # 1. 5日线呈现极其陡峭的主升攀升趋势（陡峭度 >= 1.4%，或者是 5 天均线陡升 >= 1.2% 且价格正在挑战上轨）
        is_ma5_steep = (ma5_prev5_val > 0.0 and ma5_val >= ma5_prev5_val * 1.014)
        is_breakout_upper = (upper > 0 and ctx["price"] >= upper * 0.985)
        
        is_dynamic_super = (is_ma5_steep or is_breakout_upper) and not is_consolidation
        
        # 2. 或者是持仓状态下，我们发现买入后个股进入狂飙不加速大阳线状态（收益率已拉开超 4% 且 5日均线处于快速攀升状态）
        pnl_pct = ctx.get("pnl_pct", 0.0)
        is_holding_accelerated = (state == "IN_TRADE" and pnl_pct >= 4.0 and ma5_prev5_val > 0.0 and ma5_val >= ma5_prev5_val * 1.01) and not is_consolidation
        
        # 3. 继承自已生效的主升浪标记
        inherited_setup = str(signal.features.get("setup", "")).upper()
        is_holding_ma5 = (state == "IN_TRADE" and ("MA5" in inherited_setup or "SUPER_TREND" in inherited_setup)) and not is_consolidation
        
        return is_dynamic_super or is_holding_accelerated or is_holding_ma5

    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        action = "HOLD"
        size_pct = 0.0
        regime = ctx["regime"]
        setup = "MA5_SUPER_TREND"
        confidence = ctx["confidence"]
        suggest_price = ctx["price"]
        
        if state in {"FLAT", "ARMED"}:
            # 超级主升浪沿 MA5 强趋势爬升企稳低吸与防踏空策略 (MA5_SUPER_TREND)
            low_price = ctx["low_price"]
            ma5_val = ctx["ma5d"]
            ma10_val = ctx["ma10d"] if ctx["ma10d"] > 0.0 else ctx["sws"]
            
            is_ma5_pullback = (low_price > 0.0 and ma5_val > 0.0 and low_price <= ma5_val * 1.015) and (ctx["price"] >= ma5_val * 0.99)
            is_breakout_upper = (ctx["upper"] > 0 and ctx["price"] >= ctx["upper"] * 0.985)
            is_vol_ok = (ctx["vol_val"] > 0.0 and ctx["vol_val"] < ctx["vol_ma5_val"] * 1.2)
            is_trend_ok = (ma5_val > ma10_val) or (ctx["swl"] > ctx["sws"])
            
            if is_trend_ok and is_vol_ok and (is_ma5_pullback or is_breakout_upper) and (ctx["is_doji"] or ctx["vol_shrink_3d"] or ctx["price"] >= ma5_val * 1.02):
                action = "BUY"
                size_pct = 0.30
                regime = "SWING_LOW_BUY"
                setup = "MA5_SUPER_TREND"
                confidence = 0.88
                suggest_price = ctx["price"]
                
            if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
                action = "BUY"
                is_consolidation = bool(ctx.get("is_consolidation_stage", False))
                if is_consolidation:
                    size_pct = 0.20
                else:
                    size_pct = 0.40 if ctx["is_reentry"] else 0.30
                
        elif state == "IN_TRADE":
            # 止盈：向上强力突破通道天花板或大平台顶
            is_breakout_tp = (ctx["pbreak"] == 1 or (ctx["ptop"] > 0 and ctx["price"] >= ctx["ptop"] * 1.01)) and ctx["pnl_pct"] >= 5.0 and ctx["vol_ratio"] >= 1.4
            is_upper_vol_tp = (ctx["upper"] > 0.0 and ctx["price"] >= ctx["upper"] * 0.97 and ctx["vol_ratio"] >= 1.2 and ctx["pbreak"] == 0 and ctx["pnl_pct"] >= 2.0)
            
            # 👑 优化 T+2 时间保护：如果持仓 >= 2 天且盈亏 < 3.0%，但如果个股是大结构强龙头，或者它并没有继续破位（仍在5日线上方且斜率向上），则宽容扛住不止损
            is_time_failsafe = False
            if ctx["days_held"] >= 2 and ctx["pnl_pct"] < 3.0:
                is_ma5_up = (ctx["ma5d"] >= ctx["ma5d_prev5"] * 1.002) if ctx.get("ma5d_prev5", 0) > 0 else True
                is_price_above_ma5 = (ctx["price"] >= ctx["ma5d"] * 0.99)
                is_dragon = ctx.get("is_leader", False) or ctx.get("is_reentry", False) or ctx.get("was_strong_dragon", False) or (ctx.get("priority", 0) >= 80)
                
                # 如果既不是龙头，且走势已经跌破5日线（或5日线已经拐头向下，表明真实破位了），才触发时间保护平仓
                if not (is_dragon or (is_price_above_ma5 and is_ma5_up)):
                    is_time_failsafe = True

            
            # 🚀 主升结构证伪判定：次日低开高走且未收复昨日高点，或形成三日高点下移的结构
            high_prev1 = ctx.get("high_prev1", 0.0)
            high_prev2 = ctx.get("high_prev2", 0.0)
            high_prev3 = ctx.get("high_prev3", 0.0)
            close_prev1 = ctx.get("close_prev1", 0.0)
            open_today = ctx.get("open", 0.0)
            price = ctx["price"]
            
            is_st_falsified = False
            is_three_peaks_down = (high_prev1 > 0.0 and high_prev2 > 0.0 and high_prev3 > 0.0 and 
                                    high_prev1 < high_prev2 and high_prev2 < high_prev3)
            is_low_open_high_close_fail = (open_today > 0.0 and close_prev1 > 0.0 and high_prev1 > 0.0 and
                                            open_today < close_prev1 and price > open_today and price < high_prev1)
            
            if is_three_peaks_down or is_low_open_high_close_fail:
                # 只在未清仓情况下允许激活
                is_st_falsified = True
            
            # 回补判定
            is_add_back = False
            if ctx["tp_triggered"]:
                is_ma5_climbing = (ctx["ma5d_prev5"] > 0.0 and ctx["ma5d"] >= ctx["ma5d_prev5"] * 1.008)
                ma10_val = ctx["ma10d"] if ctx["ma10d"] > 0.0 else ctx["sws"]
                is_ma5_trend_ok = (ctx["ma5d"] > ma10_val) or (ctx["swl"] > ctx["sws"])
                if is_ma5_climbing and is_ma5_trend_ok:
                    if ctx["low_price"] > 0.0 and ctx["low_price"] <= ctx["ma5d"] * 1.015 and ctx["price"] >= ctx["ma5d"] * 0.985 and ctx["vol_ratio"] < 1.15:
                        is_add_back = True
                        
            if is_st_falsified:
                action = "SELL"
                size_pct = 0.70
                regime = "TAKE_PROFIT_TRIGGERED"
                setup = "ST_DEMOTION_TP"
                confidence = 0.90
            elif is_breakout_tp or is_upper_vol_tp:
                action = "SELL"
                size_pct = 0.70
                regime = "TAKE_PROFIT_TRIGGERED"
                setup = "UPPER_VOL_TP" if is_upper_vol_tp else "BREAKOUT_TAKE_PROFIT"
                confidence = 0.90
            elif is_add_back:
                action = "ADD"
                size_pct = 0.70
                regime = "SWING_LOW_BUY"
                setup = "MA5_TREND_ADD_BACK"
                confidence = 0.88
                
                ma5_slope = (ctx["ma5d"] - ctx["ma5d_prev5"]) / 5.0 if ctx["ma5d_prev5"] > 0.0 else 0.0
                ma5_next_predict = round(ctx["ma5d"] + ma5_slope, 3)
                suggest_price = ma5_next_predict
            elif is_time_failsafe:
                action = "SELL"
                size_pct = 1.00
                regime = "TIME_FAILSAFE"
                setup = "T+2_EXPECTATION_FAIL"
                confidence = 0.95
            elif ctx["pnl_pct"] < -3.0 and ctx["vol_ratio"] >= 1.4:
                action = "SELL"
                size_pct = 1.00
                regime = "VOLUME_BREAKDOWN"
                setup = "VOL_COLLAPSE_平仓"
                confidence = 0.95
                
        return action, size_pct, regime, setup, confidence, suggest_price


class SuperTrendMA10Branch(BaseStrategyBranch):
    """分支策略二：主力均线斜率向上，回踩 10 日均线出现收盘新高且最低点不创新低的止跌反转跟单分支 (SuperTrendMA10Branch)"""
    name: str = "SuperTrendMA10Branch"

    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        ma10_val = ctx["ma10d"] if ctx["ma10d"] > 0 else ctx["sws"]
        ma10_prev5 = ctx["ma10d_prev5"] if ctx["ma10d_prev5"] > 0 else ctx["sws_prev5"]
        is_ma10_up = (ma10_val > 0 and ma10_prev5 > 0 and ma10_val >= ma10_prev5 * 1.002)
        return is_ma10_up or state == "IN_TRADE"

    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        action = "HOLD"
        size_pct = 0.0
        regime = ctx["regime"]
        setup = "MA10_REVERSAL_BUY"
        confidence = ctx["confidence"]
        suggest_price = ctx["price"]

        ma10_val = ctx["ma10d"] if ctx["ma10d"] > 0 else ctx["sws"]

        if state in {"FLAT", "ARMED"}:
            # “回踩 ma10d 出现收盘新高且最低价不创新低” 形成止跌反转结构
            close_prev1 = ctx.get("close_prev1", 0.0)
            low_prev1 = ctx.get("low_prev1", 0.0)
            price = ctx["price"]
            low_price = ctx["low_price"]

            is_reversal = (price > close_prev1 and low_price >= low_prev1) if (close_prev1 > 0 and low_prev1 > 0) else True
            is_pullback = (low_price <= ma10_val * 1.018 and price >= ma10_val * 0.985)
            is_vol_ok = (ctx["vol_ratio"] < 1.15)

            if is_reversal and is_pullback and is_vol_ok:
                action = "BUY"
                size_pct = 0.30
                regime = "SWING_LOW_BUY"
                setup = "MA10_REVERSAL_BUY"
                confidence = 0.88
                suggest_price = price

            if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
                action = "BUY"
                size_pct = 0.40 if ctx["is_reentry"] else 0.30

        elif state == "IN_TRADE":
            is_breakout_tp = (ctx["pbreak"] == 1 or (ctx["ptop"] > 0 and ctx["price"] >= ctx["ptop"] * 1.01)) and ctx["pnl_pct"] >= 5.0 and ctx["vol_ratio"] >= 1.4
            is_upper_vol_tp = (ctx["upper"] > 0.0 and ctx["price"] >= ctx["upper"] * 0.97 and ctx["vol_ratio"] >= 1.2 and ctx["pbreak"] == 0 and ctx["pnl_pct"] >= 2.0)
            
            # 时间保护与走平跌破判定
            ma10_prev5_val = ctx["ma10d_prev5"] if ctx["ma10d_prev5"] > 0.0 else ctx["sws_prev5"]
            is_trend_decaying = (ma10_val > 0.0 and ma10_prev5_val > 0.0 and ma10_val < ma10_prev5_val * 1.001) or (ctx["price"] < ma10_val * 0.985)
            
            is_time_failsafe = False
            if ctx["days_held"] >= 3 and ctx["pnl_pct"] < 3.0 and is_trend_decaying:
                is_time_failsafe = True

            # 黄金回补：大止盈减仓后，在 10 日支撑线止跌反转时加仓
            is_add_back = False
            if ctx["tp_triggered"]:
                close_prev1 = ctx.get("close_prev1", 0.0)
                low_prev1 = ctx.get("low_prev1", 0.0)
                price = ctx["price"]
                low_price = ctx["low_price"]
                is_reversal = (price > close_prev1 and low_price >= low_prev1) if (close_prev1 > 0 and low_prev1 > 0) else True
                is_pullback = (low_price <= ma10_val * 1.018 and price >= ma10_val * 0.985)
                if is_reversal and is_pullback and ctx["vol_ratio"] < 1.15:
                    is_add_back = True

            if is_breakout_tp or is_upper_vol_tp:
                action = "SELL"
                size_pct = 0.70
                regime = "TAKE_PROFIT_TRIGGERED"
                setup = "UPPER_VOL_TP" if is_upper_vol_tp else "BREAKOUT_TAKE_PROFIT"
                confidence = 0.90
            elif is_add_back:
                action = "ADD"
                size_pct = 0.70
                regime = "SWING_LOW_BUY"
                setup = "MA10_TREND_ADD_BACK"
                confidence = 0.88
            elif is_time_failsafe:
                action = "SELL"
                size_pct = 1.00
                regime = "TIME_FAILSAFE"
                setup = "T+2_EXPECTATION_FAIL"
                confidence = 0.95
            elif ctx["pnl_pct"] < -3.0 and ctx["vol_ratio"] >= 1.4:
                action = "SELL"
                size_pct = 1.00
                regime = "VOLUME_BREAKDOWN"
                setup = "VOL_COLLAPSE_平仓"
                confidence = 0.95

        return action, size_pct, regime, setup, confidence, suggest_price


class SwsPullbackBranch(BaseStrategyBranch):
    """分支策略二：经典筹码收集期回踩 SWS 工作支撑线或 MA10 慢趋势爬升策略分支 (如 通富微电 002156)"""
    name: str = "SwsPullbackBranch"
    
    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        sws = ctx["sws"]
        sws_prev5 = ctx["sws_prev5"]
        is_sws_up = (sws > 0 and sws_prev5 > 0 and sws >= sws_prev5 * 0.99)
        return is_sws_up or state == "IN_TRADE"

    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        action = "HOLD"
        size_pct = 0.0
        regime = ctx["regime"]
        setup = "SWS_COLLECT_PULLBACK"
        confidence = ctx["confidence"]
        suggest_price = ctx["price"]
        
        if state in {"FLAT", "ARMED"}:
            if ctx["vol_shrink_3d"] and ctx["is_pullback_support"] and ctx["is_doji"]:
                if ctx["is_collecting_stage"] or ctx["is_consolidation_stage"]:
                    action = "BUY"
                    size_pct = 0.30
                    regime = "SWING_LOW_BUY"
                    setup = "SWS_COLLECT_PULLBACK" if ctx["is_collecting_stage"] else "SWS_CONSOLIDATE_PULLBACK"
                    confidence = 0.88
                    
            if action == "HOLD":
                # 主升浪沿 MA10 爬升企稳低吸买入规则 (TREND_FOLLOW_BUY)
                ma10_val = ctx["ma10d"] if ctx["ma10d"] > 0.0 else ctx["sws"]
                ma10_prev5_val = ctx["ma10d_prev5"] if ctx["ma10d_prev5"] > 0.0 else ctx["sws_prev5"]
                is_ma10_climbing = (ma10_prev5_val > 0.0 and ma10_val >= ma10_prev5_val * 1.005)
                is_ma10_pullback = (ctx["low_price"] > 0.0 and ma10_val > 0.0 and ctx["low_price"] <= ma10_val * 1.015) and (ctx["price"] >= ma10_val * 0.99)
                is_vol_ok = (ctx["vol_val"] > 0.0 and ctx["vol_val"] < ctx["vol_ma5_val"] * 1.05)
                is_trend_ok = (ctx["swl"] > ctx["sws"]) or (ma10_val > ctx["sws"]) or (ctx["ma5d"] > ma10_val)
                
                if is_ma10_climbing and is_ma10_pullback and is_vol_ok and is_trend_ok and (ctx["is_doji"] or ctx["vol_shrink_3d"]):
                    action = "BUY"
                    size_pct = 0.30
                    regime = "SWING_LOW_BUY"
                    setup = "MA10_TREND_FOLLOW"
                    confidence = 0.85
                    
            # 💡 3. 新增尾盘低风险建仓规则 (TAIL_LOW_RISK_ENTRY)：
            # 异动进入视野(dff>0/高优先级/最强龙头) + 回调洗盘缩量跌无可跌(vol_ratio<0.9/回踩均线) + 尾盘时段(14:30-15:00)
            if action == "HOLD":
                time_part = signal.ts.split()[-1] if " " in signal.ts else signal.ts.split("T")[-1]
                try:
                    parts = time_part.split(":")
                    hhmm = int(parts[0]) * 100 + int(parts[1])
                    # [FIX #5] 防止纯日期格式(如'2026-06-05')被误解析为巨大整数
                    if not (800 <= hhmm <= 1600):
                        hhmm = 930
                except Exception:
                    hhmm = 930
                
                is_tail_session = (1430 <= hhmm <= 1500)
                if is_tail_session:
                    has_money_in = (ctx["dff"] > 0 or ctx["priority"] >= 70 or ctx["is_leader"] or ctx["is_reentry"])
                    
                    ma5_v = ctx["ma5d"]
                    ma10_v = ctx["ma10d"] if ctx["ma10d"] > 0 else ctx["sws"]
                    sws_v = ctx["sws"]
                    
                    near_ma5 = (ma5_v > 0 and ctx["price"] <= ma5_v * 1.015 and ctx["price"] >= ma5_v * 0.985)
                    near_ma10 = (ma10_v > 0 and ctx["price"] <= ma10_v * 1.015 and ctx["price"] >= ma10_v * 0.985)
                    near_sws = (sws_v > 0 and ctx["price"] <= sws_v * 1.015 and ctx["price"] >= sws_v * 0.985)
                    
                    is_pullback = (near_ma5 or near_ma10 or near_sws)
                    is_shrink = (ctx["vol_ratio"] < 0.9 or ctx["vol_shrink_3d"] or ctx["is_doji"])
                    
                    if has_money_in and is_pullback and is_shrink:
                        action = "BUY"
                        size_pct = 0.35
                        regime = "SWING_LOW_BUY"
                        setup = "TAIL_LOW_RISK_ENTRY"
                        confidence = 0.90
                        suggest_price = ctx["price"]
                        
            if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
                action = "BUY"
                size_pct = 0.40 if ctx["is_reentry"] else 0.30
                
        elif state == "IN_TRADE":
            is_breakout_tp = (ctx["pbreak"] == 1 or (ctx["ptop"] > 0 and ctx["price"] >= ctx["ptop"] * 1.01)) and ctx["pnl_pct"] >= 5.0 and ctx["vol_ratio"] >= 1.4
            is_upper_vol_tp = (ctx["upper"] > 0.0 and ctx["price"] >= ctx["upper"] * 0.97 and ctx["vol_ratio"] >= 1.2 and ctx["pbreak"] == 0 and ctx["pnl_pct"] >= 2.0)
            # 💡 慢趋势下的自适应不加速判定与时间保护：
            # 在慢趋势中，允许横盘震荡！只有在买入满 3 天，收益率不佳且主力防线 (SWS) 走平下斜或者价格跌破 10日线时，才执行保护！
            sws_val = ctx.get("sws", 0.0)
            sws_prev5 = ctx.get("sws_prev5", 0.0)
            is_trend_decaying = (sws_val > 0.0 and sws_prev5 > 0.0 and sws_val < sws_prev5 * 1.001) or (ctx["price"] < sws_val * 0.985)
            
            is_time_failsafe = False
            max_hold_days = 5 if ctx.get("is_consolidation_stage", False) else 3
            if ctx["days_held"] >= max_hold_days and ctx["pnl_pct"] < -1.5 and is_trend_decaying:
                is_time_failsafe = True
                
            is_weak_no_accelerate = False
            is_swing_low_mode = bool(signal.features.get("is_swing_low_mode", False))
            if (is_swing_low_mode or regime == "SWING_LOW_BUY") and ctx["days_held"] >= 3 and ctx["max_pnl_since_entry"] < 5.0 and is_trend_decaying:
                is_weak_no_accelerate = True
                
            is_add_back = False
            if ctx["tp_triggered"] and (is_swing_low_mode or regime == "SWING_LOW_BUY") and ctx["sws"] > 0:
                if ctx["low_price"] > 0.0 and ctx["low_price"] <= ctx["sws"] * 1.015 and ctx["price"] >= ctx["sws"] * 0.985 and ctx["vol_ratio"] < 0.95:
                    is_add_back = True
                    
            if is_breakout_tp or is_upper_vol_tp:
                action = "SELL"
                size_pct = 0.70
                regime = "TAKE_PROFIT_TRIGGERED"
                setup = "UPPER_VOL_TP" if is_upper_vol_tp else "BREAKOUT_TAKE_PROFIT"
                confidence = 0.90
            elif is_weak_no_accelerate:
                action = "SELL"
                size_pct = 1.00
                regime = "WEAK_NO_ACCELERATE"
                setup = "不加速_平仓避险"
                confidence = 0.95
            elif is_add_back:
                action = "ADD"
                size_pct = 0.70
                regime = "SWING_LOW_BUY"
                setup = "SWS_ADD_BACK"
                confidence = 0.88
            elif is_time_failsafe:
                action = "SELL"
                size_pct = 1.00
                regime = "TIME_FAILSAFE"
                setup = "T+2_EXPECTATION_FAIL"
                confidence = 0.95
            elif ctx["pnl_pct"] < -3.0 and ctx["vol_ratio"] >= 1.4:
                action = "SELL"
                size_pct = 1.00
                regime = "VOLUME_BREAKDOWN"
                setup = "VOL_COLLAPSE_平仓"
                confidence = 0.95
            elif regime != "SWING_LOW_BUY" and (ctx["pct_diff"] < -1.5 or ctx["dff"] < -1.0):
                action = "SELL"
                size_pct = 1.0
            # [FIX #6] 加仓必须满足：主力净流入(dff>=0) 且处于正常波段买入模式(SWING_LOW_BUY)，防止主力流出时无条件追仓超仓
            elif confidence >= 0.80 and ctx.get("dff", -1.0) >= 0.0 and regime == "SWING_LOW_BUY":
                action = "ADD"
                size_pct = 0.20
                
        return action, size_pct, regime, setup, confidence, suggest_price


class TrendMA60Branch(BaseStrategyBranch):
    """分支策略四：大周期 60 日生命支撑线企稳低吸与爆发跟踪分支 (TrendMA60Branch)"""
    name: str = "TrendMA60Branch"

    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        ma60 = ctx.get("ma60d", 0.0)
        ma60_prev5 = ctx.get("ma60d_prev5", 0.0)
        is_ma60_up = (ma60 > 0 and ma60_prev5 > 0 and ma60 >= ma60_prev5 * 0.998)
        return is_ma60_up or state == "IN_TRADE"

    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        action = "HOLD"
        size_pct = 0.0
        regime = ctx["regime"]
        setup = "MA60_LIFELINE_BUY"
        confidence = ctx["confidence"]
        suggest_price = ctx["price"]

        ma60 = ctx.get("ma60d", 0.0)

        if state in {"FLAT", "ARMED"}:
            # 大周期 60 日线附近缩量横盘止跌买入规则
            low_price = ctx["low_price"]
            price = ctx["price"]
            is_pullback_60 = (low_price > 0 and ma60 > 0 and low_price <= ma60 * 1.025 and price >= ma60 * 0.98)
            is_vol_shrink = (ctx["vol_ratio"] < 1.05)

            if is_pullback_60 and is_vol_shrink and ctx["is_doji"]:
                action = "BUY"
                size_pct = 0.30
                regime = "SWING_LOW_BUY"
                setup = "MA60_LIFELINE_BUY"
                confidence = 0.85
                suggest_price = price

            if action == "HOLD" and confidence >= 0.55 and regime == "BREAKOUT_ALLOWED":
                action = "BUY"
                size_pct = 0.40 if ctx["is_reentry"] else 0.30

        elif state == "IN_TRADE":
            # 如果跌破大周期生命支撑线 2.0%，强制无条件物理清仓
            is_ma60_broken = (ma60 > 0 and ctx["price"] < ma60 * 0.98)
            is_time_failsafe = (ctx["days_held"] >= 3 and ctx["pnl_pct"] < 2.0)

            if is_ma60_broken or is_time_failsafe:
                action = "SELL"
                size_pct = 1.00
                regime = "VOLUME_BREAKDOWN"
                setup = "MA60_LIFELINE_STOP"
                confidence = 0.95

        return action, size_pct, regime, setup, confidence, suggest_price


class OscillatingBreakdownBranch(BaseStrategyBranch):
    """分支策略五：震荡回踩破位防御分支 (针对 蓝色光标 300058 / 掌阅科技 603533 这类高位震荡阴跌破位个股)"""
    name: str = "OscillatingBreakdownBranch"
    
    @classmethod
    def match(cls, signal: StrategySignal, state: str, ctx: dict) -> bool:
        sws = ctx["sws"]
        sws_prev5 = ctx["sws_prev5"]
        price = ctx["price"]
        dff = ctx["dff"]
        vol_ratio = ctx["vol_ratio"]
        pct_diff = ctx["pct_diff"]

        # 👑 引入 V 反强力修复豁免机制：防止在急跌诱空次日强承接时被防守误杀
        close_prev1 = ctx.get("close_prev1", 0.0)
        is_yesterday_panic = (close_prev1 > 0.0 and pct_diff < -6.0) or (close_prev1 > 0.0 and close_prev1 <= ctx.get("low_prev1", 0.0) * 1.01)
        is_today_strong_rebound = (price > ctx.get("open", 0.0) and pct_diff > 2.0 and dff > 1.0)
        
        is_v_reversal_exempt = False
        if sws > 0.0:
            is_rebound_above_sws = (price >= sws * 0.998)
            is_dff_recovery = (dff > 1.8 and vol_ratio > 1.3 and price > ctx.get("open", 0.0))
            if is_rebound_above_sws or is_dff_recovery or (is_yesterday_panic and is_today_strong_rebound):
                is_v_reversal_exempt = True

        if is_v_reversal_exempt:
            return False

        # 10日支撑线明显呈向下倾斜趋势，代表已经进入震荡杀跌破位期
        # 优化：收紧向下倾斜门槛从 0.99 至 0.975，避免良性震荡洗盘被误杀
        is_sws_downward = (sws > 0 and sws_prev5 > 0 and sws < sws_prev5 * 0.975)
        
        # 或者持仓状态下价格已经踩穿工作线 1.5% 以上，说明破位已被确认
        is_breakdown_held = (state == "IN_TRADE" and sws > 0 and ctx["low_price"] > 0.0 and ctx["low_price"] < sws * 0.985)
        
        return is_sws_downward or is_breakdown_held

    @classmethod
    def decide(cls, signal: StrategySignal, state: str, ctx: dict) -> tuple[str, float, str, str, float, float]:
        # 防御分支：空仓时绝不买入，持仓时快速止损
        action = "HOLD"
        size_pct = 0.0
        regime = "WATCH_ONLY"
        setup = "OSCILLATING_BREAKDOWN_DEFENSE"
        confidence = 0.10
        suggest_price = ctx["price"]
        
        if state in {"FLAT", "ARMED"}:
            # 空仓过滤强力短路：拒绝开仓，完美避开诱多陷阱
            action = "HOLD"
            size_pct = 0.0
            regime = "WATCH_ONLY"
            setup = "OSCILLATING_BREAKDOWN_DEFENSE"
            confidence = 0.10
        elif state == "IN_TRADE":
            # 持仓阶段，极敏锐破位风控与主动撤离
            is_breakdown = (ctx["sws"] > 0 and ctx["low_price"] > 0.0 and ctx["low_price"] < ctx["sws"] * 0.985)
            is_time_failsafe = (ctx["days_held"] >= 2 and ctx["pnl_pct"] < 3.0)
            is_collapse = (ctx["pct_diff"] < -1.5 or ctx["dff"] < -1.0)
            
            if is_breakdown or is_collapse or is_time_failsafe:
                action = "SELL"
                size_pct = 1.00
                regime = "VOLUME_BREAKDOWN"
                setup = "OSCILLATING_BREAKDOWN_STOP"
                confidence = 0.95
            else:
                action = "HOLD"
                size_pct = 0.0
                
        return action, size_pct, regime, setup, confidence, suggest_price


class StrategyRouter:
    """策略自动路由寻址引擎"""
    branches: list[type[BaseStrategyBranch]] = [
        OscillatingBreakdownBranch,
        SuperTrendMA5Branch,
        SuperTrendMA10Branch,
        SwsPullbackBranch,
        TrendMA60Branch
    ]
    
    _routing_map: dict[str, list[str]] = {}
    
    @classmethod
    def register_static_routes(cls, rmap: dict[str, list[str]]):
        """供外部宿主注入静态强路由规则"""
        if isinstance(rmap, dict):
            cls._routing_map = {k.lower(): [str(c).strip() for c in v if c] for k, v in rmap.items() if v}
    
    @classmethod
    def route(cls, signal: StrategySignal, state: str, ctx: dict) -> type[BaseStrategyBranch]:
        code = str(signal.code).strip()
        rmap = cls._routing_map
        
        # 1. 优先匹配配置文件中的强路由规则 (静态上帝视角干预优先)
        for branch_cls in cls.branches:
            branch_key = branch_cls.name.lower()
            if branch_key in rmap and code in rmap[branch_key]:
                return branch_cls
                
        # 2. 持仓状态下的“动态流转与不一致速度降级/升级应对” (有状态自适应流转)
        if state == "IN_TRADE":
            inherited_setup = str(signal.features.get("setup", "")).upper()
            
            # 👑 践行“升级难，降级快”的迟滞机制：如果持仓已被烙上低级分支或降级的烙印，锁死其升级通道！
            has_demoted_lock = any(x in inherited_setup for x in ["DEMOTED", "MA10", "SWS", "MA60", "COLLECT", "CONSOLIDATE", "BREAKDOWN"])

            # A. 原本处于主升浪 5日线分支 (MA5_SUPER_TREND) 且未被降级锁死
            if ("MA5" in inherited_setup or "SUPER_TREND" in inherited_setup) and not has_demoted_lock:
                high_prev1 = ctx.get("high_prev1", 0.0)
                high_prev2 = ctx.get("high_prev2", 0.0)
                high_prev3 = ctx.get("high_prev3", 0.0)
                close_prev1 = ctx.get("close_prev1", 0.0)
                open_today = ctx.get("open", 0.0)
                price = ctx.get("price", 0.0)
                
                is_three_peaks_down = (high_prev1 > 0.0 and high_prev2 > 0.0 and high_prev3 > 0.0 and 
                                        high_prev1 < high_prev2 and high_prev2 < high_prev3)
                is_low_open_high_close_fail = (open_today > 0.0 and close_prev1 > 0.0 and high_prev1 > 0.0 and
                                                open_today < close_prev1 and price > open_today and price < high_prev1)
                
                # 🚀 降级流转到 10日线支撑分支 (SuperTrendMA10Branch)
                if is_three_peaks_down or is_low_open_high_close_fail or "ST_DEMOTION_TP" in inherited_setup:
                    return SuperTrendMA10Branch
                
                ma5_val = ctx.get("ma5d", 0.0)
                ma5_prev5 = ctx.get("ma5d_prev5", 0.0)
                ma10_val = ctx.get("ma10d", 0.0) if ctx.get("ma10d", 0.0) > 0.0 else ctx.get("sws", 0.0)
                ma10_prev5 = ctx.get("ma10d_prev5", 0.0) if ctx.get("ma10d_prev5", 0.0) > 0.0 else ctx.get("sws_prev5", 0.0)
                
                # 判定不一致：价格跌破了 5日线，或者 5日均线走平，但是 10日线支撑稳定向上
                is_ma5_broken_or_flat = (price < ma5_val) or (ma5_prev5 > 0.0 and ma5_val < ma5_prev5 * 1.002)
                is_ma10_stable = (ma10_val >= ma10_prev5 * 1.002) and (price >= ma10_val * 0.985)
                
                if is_ma5_broken_or_flat and is_ma10_stable:
                    return SuperTrendMA10Branch

            # B. 处于 10日线反转支撑分支 (SuperTrendMA10Branch) 或者是从 MA5 降级下来的
            if "MA10" in inherited_setup or has_demoted_lock:
                ma10_val = ctx.get("ma10d", 0.0) if ctx.get("ma10d", 0.0) > 0.0 else ctx.get("sws", 0.0)
                ma10_prev5 = ctx.get("ma10d_prev5", 0.0) if ctx.get("ma10d_prev5", 0.0) > 0.0 else ctx.get("sws_prev5", 0.0)
                sws_val = ctx.get("sws", 0.0)
                sws_prev5 = ctx.get("sws_prev5", 0.0)
                price = ctx.get("price", 0.0)

                # 1. 10日工作生命线自身安全判定：如果 10日线支撑依然有效且价格未有效破位，则坚定守护当前分支
                is_ma10_stable = (ma10_val > 0.0 and price >= ma10_val * 0.985) and (ma10_val >= ma10_prev5 * 0.998)
                if is_ma10_stable:
                    return SuperTrendMA10Branch

                # 2. 若 10日线已破位，层层退守降级
                is_sws_stable = (sws_val > 0.0 and price >= sws_val * 0.985) and (sws_val >= sws_prev5 * 0.992)
                if is_sws_stable:
                    return SwsPullbackBranch

                # 3. 连 SWS 也宣告失守，退守 60日牛熊生死线，或落入高位雷区清仓
                ma60_val = ctx.get("ma60d", 0.0)
                ma60_prev5 = ctx.get("ma60d_prev5", 0.0)
                is_ma60_stable = (ma60_val > 0.0 and ma60_prev5 > 0.0 and ma60_val >= ma60_prev5 * 0.998 and price >= ma60_val * 0.98)
                if is_ma60_stable:
                    return TrendMA60Branch
                else:
                    return OscillatingBreakdownBranch

            # C. 原本处于 SWS 慢趋势企稳或者大生命线分支
            sws_val = ctx.get("sws", 0.0)
            sws_prev5 = ctx.get("sws_prev5", 0.0)
            ma60_val = ctx.get("ma60d", 0.0)
            ma60_prev5 = ctx.get("ma60d_prev5", 0.0)
            price = ctx.get("price", 0.0)
            
            # 🚀 降级链判定
            is_sws_downward = (sws_val > 0.0 and sws_prev5 > 0.0 and sws_val < sws_prev5 * 0.992)
            is_price_breakdown = (sws_val > 0.0 and price < sws_val * 0.985)

            if is_sws_downward or is_price_breakdown:
                is_ma60_stable = (ma60_val > 0.0 and ma60_prev5 > 0.0 and ma60_val >= ma60_prev5 * 0.998 and price >= ma60_val * 0.98)
                if is_ma60_stable:
                    return TrendMA60Branch
                else:
                    return OscillatingBreakdownBranch
            
            if "MA60" in inherited_setup:
                is_ma60_broken = (ma60_val > 0.0 and price < ma60_val * 0.98)
                if is_ma60_broken:
                    return OscillatingBreakdownBranch
                return TrendMA60Branch
        
        # 3. 常规空仓或 Fallback 特征动态匹配
        # [FIX #3] 如果是回踩低吸/均线支撑信号，跳过防御分支——
        # 防御分支(OscillatingBreakdown)会在 SWS 短期下倾时产生 HOLD，
        # 会将放行的 PULLBACK_BUY 信号在决策层全部拦截，导致中途低吸开仓失效。
        is_pullback_signal = str(signal.signal_type).upper() in {"PULLBACK_BUY", "VWAP_SUPPORT"}
        if not is_pullback_signal and OscillatingBreakdownBranch.match(signal, state, ctx):
            return OscillatingBreakdownBranch
            
        if SuperTrendMA5Branch.match(signal, state, ctx):
            return SuperTrendMA5Branch

        if SuperTrendMA10Branch.match(signal, state, ctx):
            return SuperTrendMA10Branch
            
        if SwsPullbackBranch.match(signal, state, ctx):
            return SwsPullbackBranch

        return TrendMA60Branch


def decide(signal: StrategySignal, state: str) -> DecisionIntent:
    # ── 1. 手工干预或强制平仓与买入逻辑，直接走绿色通道无条件执行 ──
    raw_action = str(signal.features.get("action", "")).upper()
    is_manual_sell = (raw_action == "SELL" or signal.signal_type == "手工平仓" or "手工平仓" in str(signal.features.get("raw_reason", "")))
    is_manual_buy = (raw_action in {"BUY", "ADD"} and (signal.signal_type == "手动买入" or "手动买入" in str(signal.features.get("raw_reason", "")) or "Confirm:" in str(signal.features.get("raw_reason", ""))))
    
    if is_manual_sell or is_manual_buy:
        action = "BUY" if is_manual_buy else "SELL"
        reason = DecisionReason(
            regime="MANUAL_OVERRIDE",
            setup="手动交易" if is_manual_buy else "手工平仓",
            sector_heat=0.0,
            sector_rank=None,
            is_leader=False,
            breakout=False,
            volume_ratio=1.0,
            dff=0.0,
            dff_positive=False,
            price_above_vwap=True,
            confidence_inputs=(),
        )
        return DecisionIntent(
            code=signal.code,
            action=action,
            size_pct=0.30 if action == "BUY" else 1.0,
            stop_price=round(signal.price * 0.98, 3) if action == "BUY" and signal.price > 0 else None,
            confidence=1.0,
            reason=reason,
            expires_at=signal.ts,
        )

    # ── 2. 提取基础属性与公共特征 ──
    priority = _num(signal, "priority")
    sector_heat = _num(signal, "sector_heat")
    pct_diff = _num(signal, "pct_diff")
    dff = _num(signal, "dff")
    price = signal.price
    suggest_price = _num(signal, "suggest_price", price)
    volume_ratio = max(1.0, _num(signal, "hits", 1.0))
    breakout = pct_diff > 0.3 or "BREAKOUT" in signal.signal_type.upper()
    dff_positive = dff > 0
    is_leader = bool(signal.features.get("is_leader", False))
    was_strong_dragon = bool(signal.features.get("was_strong_dragon", False))
    regime = "BREAKOUT_ALLOWED" if sector_heat >= 20 and priority >= 50 else "WATCH_ONLY"
    
    # ── 2.5 竞价爆量突破决策，走独立直接放行通道 ──
    if signal.signal_type == "竞价爆量买入":
        reason = DecisionReason(
            regime="BREAKOUT_ALLOWED",
            setup="竞价巨量抢筹突破",
            sector_heat=sector_heat,
            sector_rank=None,
            is_leader=is_leader,
            breakout=True,
            volume_ratio=volume_ratio,
            dff=dff,
            dff_positive=dff_positive,
            price_above_vwap=True,
            confidence_inputs=(),
        )
        return DecisionIntent(
            code=signal.code,
            action="BUY",
            size_pct=0.30,
            stop_price=round(price * 0.94, 3) if price > 0 else None,
            confidence=0.90,
            reason=reason,
            expires_at=signal.ts,
        )
    
    if state == "IN_TRADE":
        inherited_regime = signal.features.get("regime")
        if inherited_regime:
            regime = inherited_regime
            
    # ── 3. 自愈 Re-entry 联动判定 ──
    is_reentry = False
    reentry_reason_str = ""
    reentry_boost = 1.0
    try:
        from trading_kernel.engine.reentry_tracker import reentry_tracker
        feat_dict = {
            "close": price,
            "high4": _num(signal, "high4"),
            "hmax": _num(signal, "hmax"),
            "low60": _num(signal, "low60"),
            "pbreak": int(_num(signal, "pbreak", 0)),
            "ptop": _num(signal, "ptop"),
            "dff": dff,
            "vol_ratio_5d": volume_ratio
        }
        activated, r_reason, r_boost = reentry_tracker.check_activation(signal.code, feat_dict, current_time_str=signal.ts)
        if activated:
            is_reentry = True
            reentry_reason_str = r_reason
            reentry_boost = r_boost
            regime = "BREAKOUT_ALLOWED"
    except Exception:
        pass

    confidence = _confidence(priority, sector_heat, pct_diff, dff)
    # 👑 引入置信度弹性补偿：
    # 1. 龙头个股（is_leader）在冰点行情下获得额外的胜率补偿加分
    if is_leader:
        confidence = min(0.95, round(confidence + 0.08, 4))
    # 2. 如果大单动量(dff)和放量度(volume_ratio)产生强烈共振，加分补偿
    if dff > 2.0 and volume_ratio > 1.3:
        confidence = min(0.95, round(confidence + 0.05, 4))
        
    if is_reentry:
        confidence = min(0.95, round(confidence * reentry_boost, 4))

    # ── 4. 龙头回踩低吸与大格局突破分批止盈/T+2时间风控特征提取 ──
    vol_shrink_3d = bool(signal.features.get("vol_shrink_3d", False))
    is_pullback_support = bool(signal.features.get("is_pullback_support", False))
    is_collecting_stage = bool(signal.features.get("is_collecting_stage", False))
    is_consolidation_stage = bool(signal.features.get("is_consolidation_stage", False))
    is_doji = bool(signal.features.get("is_doji", False))
    upper = float(_num(signal, "upper", 0.0))
    max_pnl_since_entry = float(_num(signal, "max_pnl_since_entry", 0.0))
    days_held = int(_num(signal, "days_held", 0.0))
    pnl_pct = float(_num(signal, "pnl_pct", 0.0))
    pbreak = int(_num(signal, "pbreak", 0))
    ptop = _num(signal, "ptop", 0.0)
    sws = float(_num(signal, "sws", 0.0))
    sws_prev5 = float(_num(signal, "sws_prev5", 0.0))
    swl = float(_num(signal, "swl", 0.0))
    low_price = float(_num(signal, "low", 0.0))
    ma10d = float(_num(signal, "ma10d", 0.0))
    ma10d_prev5 = float(_num(signal, "ma10d_prev5", 0.0))
    swl_prev5 = float(_num(signal, "swl_prev5", 0.0))
    ma5d_prev5 = float(_num(signal, "ma5d_prev5", 0.0))

    ma60d = float(_num(signal, "ma60d", price))
    ma60d_prev5 = float(_num(signal, "ma60d_prev5", price))

    vol_val = float(_num(signal, "volume", 0.0))
    vol_ma5_val = float(_num(signal, "vol_ma5", 0.0))
    vol_ratio = vol_val / vol_ma5_val if vol_ma5_val > 0 else 1.0

    ma5d = float(_num(signal, "ma5d", 0.0))
    if ma5d <= 0.0:
        ma5d = swl if swl > 0.0 else price

    # 组装完整的上下文参数字典
    ctx = {
        "priority": priority,
        "sector_heat": sector_heat,
        "pct_diff": pct_diff,
        "dff": dff,
        "price": price,
        "volume_ratio": volume_ratio,
        "breakout": breakout,
        "dff_positive": dff_positive,
        "is_leader": is_leader,
        "was_strong_dragon": was_strong_dragon,
        "regime": regime,
        "is_reentry": is_reentry,
        "vol_shrink_3d": vol_shrink_3d,
        "is_pullback_support": is_pullback_support,
        "is_collecting_stage": is_collecting_stage,
        "is_consolidation_stage": is_consolidation_stage,
        "is_doji": is_doji,
        "upper": upper,
        "max_pnl_since_entry": max_pnl_since_entry,
        "days_held": days_held,
        "pnl_pct": pnl_pct,
        "pbreak": pbreak,
        "ptop": ptop,
        "sws": sws,
        "sws_prev5": sws_prev5,
        "swl": swl,
        "low_price": low_price,
        "ma10d": ma10d,
        "ma10d_prev5": ma10d_prev5,
        "swl_prev5": swl_prev5,
        "ma5d_prev5": ma5d_prev5,
        "vol_val": vol_val,
        "vol_ma5_val": vol_ma5_val,
        "vol_ratio": vol_ratio,
        "ma5d": ma5d,
        "confidence": confidence,
        "tp_triggered": bool(signal.features.get("tp_triggered", False)),
        "ma60d": ma60d,
        "ma60d_prev5": ma60d_prev5
    }

    # ── 5. 自动寻找策略路由并激活对应分支决策 ──
    active_branch = StrategyRouter.route(signal, state, ctx)
    action, size_pct, regime, setup, confidence, suggest_price = active_branch.decide(signal, state, ctx)

    if action == "SELL":
        logger.info(
            f"📉 [DecisionEngine] 触发平仓/止损信号: {signal.code} ({signal.name}) | "
            f"策略分支: {active_branch.name} | "
            f"形态原因 (Setup): {setup} | "
            f"运行模式: {regime} | "
            f"持仓天数: {ctx.get('days_held', 0)}天 | "
            f"盈亏比例 (PnL): {ctx.get('pnl_pct', 0.0):.2f}% | "
            f"今日放量比 (VolRatio): {ctx.get('vol_ratio', 1.0):.2f} | "
            f"当前股价: {ctx.get('price', 0.0):.2f} 元"
        )

    # ── 6. 统一动态止损价格设定 ──
    stop_price = None
    
    # 👑 全生命周期自适应防守止损线引擎：不管是买入还是持仓日常(HOLD)，都为柜台提供当下最科学的动态生命防线
    if state == "IN_TRADE" or (action in {"BUY", "ADD"} and suggest_price > 0):
        # A. 如果当前被路由为超级强势主升浪分支，防守线紧咬 5日线下方 1.5% (方案B：强势股挂单收窄至1.5%，防回踩极浅踏空)
        if active_branch == SuperTrendMA5Branch:
            ma5_val = float(_num(signal, "ma5d", swl))
            ma10_val = float(_num(signal, "ma10d", sws))
            # 👑 龙头大结构记忆：如果是核心龙头、重入突击股或高优先级强股，止损放宽到 10 日线下方 1.8% 或 5日线下方 4%，防日内急回踩扫损
            was_strong_dragon = ctx.get("was_strong_dragon", False)
            has_dragon_memory = is_leader or is_reentry or was_strong_dragon or (priority >= 80)
            if has_dragon_memory:
                if ma10_val > 0:
                    stop_price = round(ma10_val * 0.982, 3)
                elif ma5_val > 0:
                    stop_price = round(ma5_val * 0.96, 3)
                else:
                    stop_price = round(suggest_price * 0.95, 3)
            else:
                if ma5_val > 0:
                    stop_price = round(ma5_val * 0.985, 3)
                else:
                    stop_price = round(suggest_price * 0.985, 3)

        # B. 如果当前被路由为主力 10日线反转支撑分支，防守线坚守 10日线下方 1.5%
        elif active_branch == SuperTrendMA10Branch:
            ma10_val = float(_num(signal, "ma10d", sws))
            if ma10_val > 0:
                stop_price = round(ma10_val * 0.985, 3)
            else:
                stop_price = round(suggest_price * 0.975, 3)
        # C. 如果当前被路由为慢趋势企稳 SWS 低吸波段，防守线系于 SWS 工作线下方 1.5%
        elif active_branch == SwsPullbackBranch:
            sws_val = float(_num(signal, "sws", 0.0))
            if sws_val > 0:
                stop_price = round(sws_val * 0.985, 3)
            else:
                stop_price = round(suggest_price * 0.965, 3)
        # D. 如果当前被路由为大周期 60日生命支撑线企稳分支，防守线系于 60日线下方 2.0%
        elif active_branch == TrendMA60Branch:
            if ma60d > 0:
                stop_price = round(ma60d * 0.98, 3)
            else:
                stop_price = round(suggest_price * 0.96, 3)
        # E. 否则 Fallback 至常规止损
        else:
            stop_price = round(suggest_price * 0.98, 3)

    # ── 7. 构造并返回决策意图 ──
    reason = DecisionReason(
        regime=regime,
        setup=setup,
        sector_heat=round(sector_heat, 4),
        sector_rank=None,
        is_leader=is_leader,
        breakout=breakout,
        volume_ratio=round(volume_ratio, 4),
        dff=round(dff, 4),
        dff_positive=dff_positive,
        price_above_vwap=not math.isnan(price) and price > 0,
        confidence_inputs=(
            ("priority", round(priority, 4)),
            ("sector_heat", round(sector_heat, 4)),
            ("pct_diff", round(pct_diff, 4)),
            ("dff", round(dff, 4)),
        ),
    )
    # 动态属性植入
    object.__setattr__(reason, "routed_branch", active_branch.name)
    object.__setattr__(reason, "is_reentry_signal", is_reentry)
    object.__setattr__(reason, "reentry_reason", reentry_reason_str)

    intent = DecisionIntent(
        code=signal.code,
        action=action,
        size_pct=round(size_pct, 4),
        stop_price=stop_price,
        confidence=confidence,
        reason=reason,
        expires_at=signal.ts,
    )
    object.__setattr__(intent, "is_reentry_signal", is_reentry)
    object.__setattr__(intent, "suggest_price", suggest_price)
    return intent


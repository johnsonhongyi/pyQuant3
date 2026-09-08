# -*- coding: utf-8 -*-
"""
ATS Swing Tracker
Implements the MA20d pullback state machine and recommendation logic.
States:
- 回踩中 (Pulling back to MA20)
- 回踩企稳 (Pullback stabilized at MA20)
- 持股中 (Holding/riding trend)
- 已平仓 (Closed/broken support)
"""

class SwingTracker:
    # State constants
    STATE_PULLBACK = "回踩中"
    STATE_STABILIZED = "回踩企稳"
    STATE_HOLDING = "持股中"
    STATE_CLOSED = "已平仓"

    def __init__(self):
        # Maps stock code -> current state string
        self.states = {}

    def get_state(self, code):
        return self.states.get(code, self.STATE_PULLBACK)

    def set_state(self, code, state):
        self.states[code] = state

    def update_stock_state(
        self,
        code,
        name,
        price,
        close_series,
        ma20_series,
        ma5_series,
        supp_price=None,
        ch_slope_deg=None,
        ch_height_pct=None,
        amplitude_pct=None,
        is_traded_or_closed=False,
        swing_tag=None
    ):
        """
        Calculates state transition for a stock based on historical close and MA series,
        integrated with Channel Up and Support Line Stabilization model.
        """
        if len(close_series) < 3 or len(ma20_series) < 3:
            return self.STATE_PULLBACK, "0.00%", "0%", "历史数据不足"

        current_close = close_series[-1]
        prev_close = close_series[-2]
        current_ma20 = ma20_series[-1]
        current_ma5 = ma5_series[-1] if len(ma5_series) > 0 else current_close

        # Calculate deviation from MA20
        deviation = (current_close - current_ma20) / current_ma20 * 100 if current_ma20 > 0 else 0.0

        # 通道与支撑线特征
        supp_p = float(supp_price) if (supp_price is not None and supp_price > 0.01) else current_ma20 * 0.985
        slope_d = float(ch_slope_deg) if ch_slope_deg is not None else 0.0
        ch_h = float(ch_height_pct) if ch_height_pct is not None else 15.0
        amp = float(amplitude_pct) if amplitude_pct is not None else 3.5

        is_channel_up = bool(slope_d >= 0.0 or (current_close >= current_ma20 * 0.98 and current_ma5 >= current_ma20 * 0.99))
        is_above_supp = bool(current_close >= supp_p * 0.985)
        is_dead_stock = bool(amp < 1.9)

        # Get last state
        last_state = self.get_state(code)

        new_state = last_state
        reason = ""
        position = "0%"

        # =========================================================================
        # 核心状态机状态跃迁体系 (实战法尔胜/中农联合与爱尔眼科防御)
        # =========================================================================

        # 1. 严格防御破位：跌破支撑线或 MA20 超过 2.5% (类似爱尔眼科)
        if current_close < supp_p * 0.975 or current_close < current_ma20 * 0.975:
            new_state = self.STATE_CLOSED
            reason = f"跌破支撑线({supp_p:.2f}元)或生命线MA20，防守离场"
            position = "0%"

        elif last_state == self.STATE_PULLBACK:
            # 回踩支撑线/MA20企稳判定 (放宽至通道中下轨健康蓄势带 -2.0% ~ +8.5%，不再被死板的 1.5% 卡死)
            if is_channel_up and is_above_supp and (-2.2 <= deviation <= 8.8) and (current_close >= prev_close * 0.985) and not is_dead_stock:
                new_state = self.STATE_STABILIZED
                if swing_tag and "🚀" in swing_tag:
                    reason = f"支撑线({supp_p:.2f}元)企稳后放量加速，通道高度{ch_h:.1f}%"
                    position = "20%"
                elif swing_tag and "🏆" in swing_tag:
                    reason = f"上升通道(+{slope_d:.1f}°)，稳居支撑({supp_p:.2f}元)，完美双结构"
                    position = "15%"
                else:
                    reason = f"稳居支撑线({supp_p:.2f}元)与MA20上方缩量震荡，企稳信号确认"
                    position = "15%"
            elif is_dead_stock:
                reason = f"振幅过窄({amp:.1f}%)缺乏波动弹性，织布观望"
                position = "0%"
            else:
                reason = f"股价向支撑线({supp_p:.2f}元)/MA20均线回调靠拢中"
                position = "0%"

        elif last_state == self.STATE_STABILIZED:
            # 企稳确认后：若突破 MA5 或放量加速，进入持股主升
            if current_close > current_ma5 and current_close > current_ma20:
                new_state = self.STATE_HOLDING
                if current_close >= prev_close * 1.02:
                    reason = f"企稳起爆加速，放量突破MA5，主升展开 (中农联合模式)"
                    position = "30%"
                else:
                    reason = "企稳确认，站上短期MA5与支撑线，多头量能释放"
                    position = "25%"
            elif not is_above_supp:
                new_state = self.STATE_CLOSED
                reason = f"回踩跌破支撑线({supp_p:.2f}元)，防守出局"
                position = "0%"
            else:
                reason = f"在支撑位({supp_p:.2f}元)蓄势震荡，通道高度{ch_h:.1f}%，待放量起爆"
                position = "15%"

        elif last_state == self.STATE_HOLDING:
            # 持股阶段：若未破位则顺势持有，跌破支撑线/MA20出局
            if current_close < supp_p * 0.98 or current_close < current_ma20 * 0.98:
                new_state = self.STATE_CLOSED
                reason = f"跌破上升通道支撑线({supp_p:.2f}元)，趋势转弱出局"
                position = "0%"
            else:
                reason = f"处于上升通道(+{slope_d:.1f}°)主升波段，稳居支撑线上顺势持有"
                position = f"{min(35, int(20 + max(0, deviation) * 1.5))}%"

        elif last_state == self.STATE_CLOSED:
            # 💥【核心实战升级：防丢失筹码与二次上车】(法尔胜模式)
            # 用户卖出后，若股票依然在上升通道内、在支撑线和 MA20 上方扎实震荡企稳：
            if is_channel_up and is_above_supp and (-2.2 <= deviation <= 8.8) and not is_dead_stock:
                new_state = self.STATE_STABILIZED
                if is_traded_or_closed:
                    reason = f"🎯 卖出后在支撑线({supp_p:.2f}元)/MA20上方扎实企稳，二次上车信号确认"
                    position = "20%"
                else:
                    reason = f"已平仓标的再次回踩支撑线({supp_p:.2f}元)获得强支撑，开启新一轮波段"
                    position = "15%"
            else:
                reason = f"观望状态，等待重回大级别支撑线({supp_p:.2f}元)与MA20之上"
                position = "0%"

        self.set_state(code, new_state)

        # Format returns
        dev_str = f"{deviation:+.2f}%"
        return new_state, dev_str, position, reason


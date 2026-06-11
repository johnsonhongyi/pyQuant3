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

    def update_stock_state(self, code, name, price, close_series, ma20_series, ma5_series):
        """
        Calculates state transition for a stock based on historical close and MA series.
        close_series, ma20_series, ma5_series should be list/array of values ending in current value.
        """
        if len(close_series) < 3 or len(ma20_series) < 3:
            return self.STATE_PULLBACK, 0.0, "0%", "历史数据不足"

        current_close = close_series[-1]
        prev_close = close_series[-2]
        current_ma20 = ma20_series[-1]
        current_ma5 = ma5_series[-1] if len(ma5_series) > 0 else current_close

        # Calculate deviation from MA20
        deviation = (current_close - current_ma20) / current_ma20 * 100
        
        # Get last state
        last_state = self.get_state(code)
        
        new_state = last_state
        reason = ""
        position = "0%"

        # State transition logic
        if last_state == self.STATE_PULLBACK:
            # Check for stabilization: close is above MA20, close >= prev_close (or close >= open),
            # and close is within 1.5% of MA20
            if current_close >= current_ma20 and deviation <= 1.5 and current_close >= prev_close:
                new_state = self.STATE_STABILIZED
                reason = "MA20强支撑附近缩量收阳，企稳信号明晰"
                position = "15%"
            else:
                reason = "股价缩量向大级别MA20均线回调靠拢中"
                position = "0%"
                
        elif last_state == self.STATE_STABILIZED:
            # Check if breakout / holding phase starts: price rises above MA5
            if current_close > current_ma5 and current_close > current_ma20:
                new_state = self.STATE_HOLDING
                reason = "企稳确认，突破短期MA5，多头量能开始释放"
                position = "25%"
            # Check if support fails
            elif current_close < current_ma20 * 0.985: # 1.5% buffer stop loss
                new_state = self.STATE_CLOSED
                reason = "跌破大级别均线MA20，防守离场"
                position = "0%"
            else:
                reason = "支撑位蓄势震荡，观察量能配合"
                position = "15%"

        elif last_state == self.STATE_HOLDING:
            # Check if trend breaks
            if current_close < current_ma20:
                new_state = self.STATE_CLOSED
                reason = "跌破MA20支撑，多头趋势破坏，出局"
                position = "0%"
            else:
                reason = "处于主升浪或多头波段，顺势持有中"
                position = f"{min(30, int(20 + deviation * 2))}%"

        elif last_state == self.STATE_CLOSED:
            # Check if it pullbacks again and stabilizes
            if current_close >= current_ma20 and deviation <= 1.5 and current_close >= prev_close:
                new_state = self.STATE_STABILIZED
                reason = "已平仓股再次回踩均线获得支撑，开启新一轮观察"
                position = "10%"
            else:
                reason = "观望状态，等待重回大级别均线之上"
                position = "0%"

        self.set_state(code, new_state)
        
        # Format returns
        dev_str = f"{deviation:+.2f}%"
        return new_state, dev_str, position, reason

# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)

class IntradayDecisionEngine:
    """
    盘中决策引擎
    ❗ 只有以下数据拥有 BUY / SELL 决策权
    - 当日 OHLC + volume + ratio
    - 当日 MA5 / MA10 相对位置
    - 昨日 last_close / last_nclose

    其他指标只允许减权 / 限制 / 校验
    """
    def evaluate(self, row: dict, snapshot: dict) -> dict:
        debug = {}
        price = float(row.get("trade", 0))
        high = float(row.get("high", 0))
        low = float(row.get("low", 0))
        open_p = float(row.get("open", 0))
        volume = float(row.get("volume", 0))
        ratio = float(row.get("ratio", 0))
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))

        if price <= 0 or ma5 <= 0 or ma10 <= 0:
            return self._hold("价格或均线无效", debug)

        structure = self._intraday_structure(price, high, open_p, ratio)
        debug["structure"] = structure

        action, base_pos, ma_reason = self._ma_decision(price, ma5, ma10)
        debug["ma_decision"] = ma_reason

        if action == "持仓":
            return self._hold(ma_reason, debug)

        base_pos += self._yesterday_anchor(price, snapshot, debug)
        base_pos += self._structure_filter(row, debug)
        base_pos += self._extreme_filter(row, debug)

        final_pos = max(min(base_pos, 0.4), 0)
        if final_pos <= 0:
            return self._hold("仓位被限制为0", debug)

        reason = f"{structure} | {ma_reason}"
        logger.debug(f"DecisionEngine BUY pos={final_pos:.2f} reason={reason} debug={debug}")

        return {
            "action": "买入",
            "position": round(final_pos, 2),
            "reason": reason,
            "debug": debug
        }

    # --------------------------------------------------
    def _intraday_structure(self, price, high, open_p, ratio):
        if high > 0 and (high - price) / high > 0.02 and ratio > 8:
            return "DISTRIBUTE"
        if price > open_p and ratio > 5:
            return "STRONG"
        if price < open_p and ratio > 5:
            return "WEAK"
        return "NEUTRAL"

    def _ma_decision(self, price, ma5, ma10):
        bias = (price - ma5) / ma5
        if price > ma5 > ma10 and bias < 0.015:
            return "买入", 0.2 + bias, "站稳MA5，趋势延续"
        if price < ma5 < ma10:
            return "卖出", -0.3, "跌破MA5/MA10"
        if bias > 0.05:
            return "持仓", 0, "远离MA5，追高风险"
        return "持仓", 0, "结构中性"

    def _yesterday_anchor(self, price, snapshot, debug):
        penalty = 0.0
        last_close = float(snapshot.get("last_close", 0))
        last_nclose = float(snapshot.get("n_nclose", 0))
        if last_close > 0 and price < last_close:
            penalty -= 0.1
        if last_nclose > 0 and price < last_nclose:
            penalty -= 0.15
        debug["yesterday_penalty"] = penalty
        return penalty

    def _structure_filter(self, row, debug):
        penalty = 0.0
        price = float(row.get("trade", 0))
        ma60 = float(row.get("ma60d", 0))
        max5 = float(row.get("max5", 0))
        high4 = float(row.get("high4", 0))
        if ma60 > 0 and price < ma60:
            penalty -= 0.2
        if max5 > 0 and price > max5 * 0.98:
            penalty -= 0.1
        if high4 > 0 and price > high4 * 0.98:
            penalty -= 0.05
        debug["structure_penalty"] = penalty
        return penalty

    def _extreme_filter(self, row, debug):
        penalty = 0.0
        kdj_j = float(row.get("kdj_j", 0))
        macd = float(row.get("macd", 0))
        macd_dif = float(row.get("macddif", 0))
        macd_dea = float(row.get("macddea", 0))
        upper = float(row.get("upper", 0))
        lower = float(row.get("lower", 0))
        if kdj_j > 95 or kdj_j < 5:
            penalty -= 0.1
        if macd > 0.5 or macd < -0.5:
            penalty -= 0.1
        if upper > 0 and row.get("trade", 0) > upper:
            penalty -= 0.1
        if lower > 0 and row.get("trade", 0) < lower:
            penalty -= 0.1
        debug["_extreme_penalty"] = penalty
        return penalty

    def _hold(self, reason, debug):
        return {
            "action": "持仓",
            "position": 0.0,
            "reason": reason,
            "debug": debug
        }

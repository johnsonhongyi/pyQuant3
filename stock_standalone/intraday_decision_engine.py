# -*- coding: utf-8 -*-
"""
盘中决策引擎 - 增强版
支持买入/卖出信号生成、动态仓位计算、趋势强度评估、止损止盈检测
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IntradayDecisionEngine:
    """
    盘中决策引擎 v2
    
    功能：
    - 买入/卖出信号生成（基于 MA5/MA10 和价格结构）
    - 动态仓位计算
    - 趋势强度评估
    - 止损/止盈检测
    
    配置参数（可通过 __init__ 传入）：
    - stop_loss_pct: 止损百分比（默认 5%）
    - take_profit_pct: 止盈百分比（默认 10%）
    - trailing_stop_pct: 移动止盈回撤百分比（默认 3%）
    - max_position: 最大仓位（默认 0.4）
    """
    
    def __init__(self, 
                 stop_loss_pct: float = 0.05,
                 take_profit_pct: float = 0.10,
                 trailing_stop_pct: float = 0.03,
                 max_position: float = 0.4):
        """
        初始化决策引擎
        
        Args:
            stop_loss_pct: 止损百分比，低于成本价此比例触发止损
            take_profit_pct: 止盈百分比，高于成本价此比例触发止盈
            trailing_stop_pct: 移动止盈回撤百分比
            max_position: 单只股票最大仓位比例
        """
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_position = max_position
        
        logger.info(f"IntradayDecisionEngine 初始化: stop_loss={stop_loss_pct:.1%}, "
                   f"take_profit={take_profit_pct:.1%}, trailing={trailing_stop_pct:.1%}, "
                   f"max_pos={max_position:.1%}")

    def evaluate(self, row: dict, snapshot: dict, mode: str = "full") -> dict:
        """
        评估当前行情并生成交易决策
        
        Args:
            row: 当前行情数据（包含 trade, high, low, open, volume, ratio, ma5d, ma10d 等）
            snapshot: 历史快照（包含 last_close, nclose, cost_price 等）
            mode: 评估模式
                  - "full": 完整买卖判断（默认）
                  - "buy_only": 仅评估买入信号
                  - "sell_only": 仅评估卖出信号
        
        Returns:
            dict: {
                "action": "买入" | "卖出" | "持仓" | "止损" | "止盈",
                "position": float (0.0 ~ 1.0),
                "reason": str,
                "debug": dict
            }
        """
        debug = {}
        price = float(row.get("trade", 0))
        high = float(row.get("high", 0))
        low = float(row.get("low", 0))
        open_p = float(row.get("open", 0))
        volume = float(row.get("volume", 0))
        ratio = float(row.get("ratio", 0))
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))

        if price <= 0:
            return self._hold("价格无效", debug)
        
        # ---------- 止损止盈检测（优先级最高） ----------
        if mode in ("full", "sell_only"):
            stop_result = self._stop_check(price, high, snapshot, debug)
            if stop_result["triggered"]:
                return {
                    "action": stop_result["action"],
                    "position": 0.0,
                    "reason": stop_result["reason"],
                    "debug": debug
                }
        
        # ========== 实时行情高优先级决策（优先级次高） ==========
        realtime_result = self._realtime_priority_check(row, snapshot, mode, debug)
        if realtime_result["triggered"]:
            return {
                "action": realtime_result["action"],
                "position": realtime_result["position"],
                "reason": realtime_result["reason"],
                "debug": debug
            }
        
        # ---------- 均线有效性检查 ----------
        if ma5 <= 0 or ma10 <= 0:
            return self._hold("均线数据无效", debug)

        # ---------- 盘中结构分析 ----------
        structure = self._intraday_structure(price, high, open_p, ratio)
        debug["structure"] = structure
        
        # ---------- 趋势强度评估 ----------
        trend_strength = self._trend_strength(row, debug)
        debug["trend_strength"] = trend_strength

        # ---------- 卖出信号检测 ----------
        if mode in ("full", "sell_only"):

            sell_action, sell_pos, sell_reason = self._sell_decision(price, ma5, ma10, snapshot, structure, debug)
            if sell_action == "卖出":
                debug["sell_reason"] = sell_reason
                return {
                    "action": "卖出",
                    "position": sell_pos,
                    "reason": sell_reason,
                    "debug": debug
                }

        # ---------- 买入信号检测 ----------
        if mode in ("full", "buy_only"):
            action, base_pos, ma_reason = self._ma_decision(price, ma5, ma10)
            debug["ma_decision"] = ma_reason

            if action == "持仓":
                return self._hold(ma_reason, debug)
            
            if action == "买入":
                # 应用各种过滤器调整仓位
                base_pos += self._yesterday_anchor(price, snapshot, debug)
                base_pos += self._structure_filter(row, debug)
                base_pos += self._extreme_filter(row, debug)
                
                # 趋势强度加成
                if trend_strength > 0.5:
                    base_pos += 0.1
                elif trend_strength < -0.3:
                    base_pos -= 0.1
                
                # 量能加成
                base_pos += self._volume_bonus(row, debug)

                final_pos = max(min(base_pos, self.max_position), 0)
                if final_pos <= 0:
                    return self._hold("仓位被限制为0", debug)

                reason = f"{structure} | {ma_reason}"
                logger.debug(f"DecisionEngine BUY pos={final_pos:.2f} reason={reason}")

                return {
                    "action": "买入",
                    "position": round(final_pos, 2),
                    "reason": reason,
                    "debug": debug
                }

        return self._hold("无有效信号", debug)

    # ==================== 卖出信号 ====================
    
    def _sell_decision(self, price: float, ma5: float, ma10: float, 
                       snapshot: dict, structure: str, debug: dict) -> tuple:
        """
        卖出信号判定
        
        Returns:
            (action, position_delta, reason)
        """
        reasons = []
        sell_score = 0.0
        
        # 1. MA5/MA10 死叉
        if price < ma5 < ma10:
            sell_score += 0.4
            reasons.append("跌破MA5/MA10")
        
        # 2. 价格远低于 MA5
        if ma5 > 0:
            bias = (price - ma5) / ma5
            if bias < -0.02:  # 低于 MA5 超过 2%
                sell_score += 0.3
                reasons.append(f"低于MA5 {abs(bias):.1%}")
        
        # 3. 盘中结构弱势
        if structure == "DISTRIBUTE":
            sell_score += 0.2
            reasons.append("高位派发")
        elif structure == "WEAK":
            sell_score += 0.1
            reasons.append("盘中走弱")
        
        # 4. 跌破昨日收盘
        last_close = float(snapshot.get("last_close", 0))
        if last_close > 0 and price < last_close * 0.97:
            sell_score += 0.2
            reasons.append(f"跌破昨收{last_close:.2f}")
        
        debug["sell_score"] = sell_score
        debug["sell_reasons"] = reasons
        
        if sell_score >= 0.5:
            return ("卖出", -sell_score, " | ".join(reasons))
        
        return ("持仓", 0, "")
    
    # ==================== 止损止盈 ====================
    
    def _stop_check(self, price: float, high: float, snapshot: dict, debug: dict) -> dict:
        """
        止损止盈检测
        
        Args:
            price: 当前价格
            high: 当日最高价
            snapshot: 快照数据（应包含 cost_price、highest_since_buy）
        
        Returns:
            {"triggered": bool, "action": str, "reason": str}
        """
        cost_price = float(snapshot.get("cost_price", 0))
        highest_since_buy = float(snapshot.get("highest_since_buy", 0))
        
        if cost_price <= 0:
            return {"triggered": False, "action": "", "reason": ""}
        
        pnl_pct = (price - cost_price) / cost_price
        debug["pnl_pct"] = pnl_pct
        
        # 止损检测
        if pnl_pct < -self.stop_loss_pct:
            reason = f"触发止损: 亏损{abs(pnl_pct):.1%} > {self.stop_loss_pct:.1%}"
            logger.warning(f"止损信号: {reason}")
            return {"triggered": True, "action": "止损", "reason": reason}
        
        # 固定止盈检测
        if pnl_pct > self.take_profit_pct:
            reason = f"触发止盈: 盈利{pnl_pct:.1%} > {self.take_profit_pct:.1%}"
            logger.info(f"止盈信号: {reason}")
            return {"triggered": True, "action": "止盈", "reason": reason}
        
        # 移动止盈（回撤止盈）
        if highest_since_buy > 0 and highest_since_buy > cost_price:
            drawdown = (highest_since_buy - price) / highest_since_buy
            if drawdown > self.trailing_stop_pct and pnl_pct > 0.03:  # 仍有盈利才触发
                reason = f"移动止盈: 从最高{highest_since_buy:.2f}回撤{drawdown:.1%}"
                logger.info(f"移动止盈信号: {reason}")
                return {"triggered": True, "action": "止盈", "reason": reason}
        
        return {"triggered": False, "action": "", "reason": ""}

    # ==================== 趋势强度 ====================
    
    def _trend_strength(self, row: dict, debug: dict) -> float:
        """
        计算趋势强度评分
        
        Returns:
            float: -1.0（极弱）到 1.0（极强）
        """
        score = 0.0
        
        price = float(row.get("trade", 0))
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))
        ma20 = float(row.get("ma20d", 0))
        ma60 = float(row.get("ma60d", 0))
        macd = float(row.get("macd", 0))
        
        # 均线多头排列
        if ma5 > 0 and ma10 > 0 and ma20 > 0:
            if price > ma5 > ma10 > ma20:
                score += 0.4
            elif price > ma5 > ma10:
                score += 0.2
            elif price < ma5 < ma10 < ma20:
                score -= 0.4
            elif price < ma5 < ma10:
                score -= 0.2
        
        # MACD 方向
        if macd > 0.1:
            score += 0.2
        elif macd > 0:
            score += 0.1
        elif macd < -0.1:
            score -= 0.2
        elif macd < 0:
            score -= 0.1
        
        # 价格相对 MA60
        if ma60 > 0:
            if price > ma60 * 1.05:
                score += 0.2
            elif price < ma60 * 0.95:
                score -= 0.2
        
        debug["trend_components"] = {
            "ma_alignment": score,
            "macd_direction": macd
        }
        
        return max(-1.0, min(1.0, score))

    # ==================== 量能分析 ====================
    
    def _volume_bonus(self, row: dict, debug: dict) -> float:
        """
        量能加成/惩罚
        
        Returns:
            float: 仓位调整值
        """
        bonus = 0.0
        ratio = float(row.get("ratio", 0))
        volume = float(row.get("volume", 0))
        
        # 换手率分析
        if 3 < ratio < 8:
            bonus += 0.05  # 适度换手，健康上涨
        elif ratio > 15:
            bonus -= 0.1  # 换手过高，可能见顶
        elif ratio < 1:
            bonus -= 0.05  # 量能不足
        
        debug["volume_bonus"] = bonus
        return bonus

    # ==================== 原有方法（保持兼容） ====================
    
    def _intraday_structure(self, price: float, high: float, open_p: float, ratio: float) -> str:
        """判断盘中结构"""
        if high > 0 and (high - price) / high > 0.02 and ratio > 8:
            return "DISTRIBUTE"  # 高位派发
        if price > open_p and ratio > 5:
            return "STRONG"  # 强势上涨
        if price < open_p and ratio > 5:
            return "WEAK"  # 高开低走
        return "NEUTRAL"

    def _ma_decision(self, price: float, ma5: float, ma10: float) -> tuple:
        """均线决策"""
        bias = (price - ma5) / ma5
        if price > ma5 > ma10 and bias < 0.015:
            return "买入", 0.2 + bias, "站稳MA5，趋势延续"
        if price < ma5 < ma10:
            return "卖出", -0.3, "跌破MA5/MA10"
        if bias > 0.05:
            return "持仓", 0, "远离MA5，追高风险"
        return "持仓", 0, "结构中性"

    def _yesterday_anchor(self, price: float, snapshot: dict, debug: dict) -> float:
        """昨日锚点惩罚"""
        penalty = 0.0
        last_close = float(snapshot.get("last_close", 0))
        last_nclose = float(snapshot.get("nclose", 0))
        if last_close > 0 and price < last_close:
            penalty -= 0.1
        if last_nclose > 0 and price < last_nclose:
            penalty -= 0.15
        debug["yesterday_penalty"] = penalty
        return penalty

    def _structure_filter(self, row: dict, debug: dict) -> float:
        """结构过滤"""
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

    def _extreme_filter(self, row: dict, debug: dict) -> float:
        """极端指标过滤"""
        penalty = 0.0
        kdj_j = float(row.get("kdj_j", 0))
        macd = float(row.get("macd", 0))
        upper = float(row.get("upper", 0))
        lower = float(row.get("lower", 0))
        price = float(row.get("trade", 0))
        
        if kdj_j > 95 or kdj_j < 5:
            penalty -= 0.1
        if macd > 0.5 or macd < -0.5:
            penalty -= 0.1
        if upper > 0 and price > upper:
            penalty -= 0.1
        if lower > 0 and price < lower:
            penalty -= 0.1
        debug["extreme_penalty"] = penalty
        return penalty

    # ==================== 实时行情高优先级决策 ====================
    
    def _realtime_priority_check(self, row: dict, snapshot: dict, mode: str, debug: dict) -> dict:
        """
        实时行情高优先级决策（优先级高于普通均线信号）
        
        检测内容：
        1. 开盘高走买入：open > last_close, open ≈ low, trade > nclose
        2. 跌破均价卖出：trade < nclose 且偏离超过阈值
        3. 量能情绪分析：volume/ratio 与前几日对比
        
        Args:
            row: 当前行情数据
            snapshot: 历史快照
            mode: 评估模式
            debug: 调试信息字典
        
        Returns:
            dict: {
                "triggered": bool,
                "action": str,
                "position": float,
                "reason": str
            }
        """
        result = {"triggered": False, "action": "持仓", "position": 0.0, "reason": ""}
        
        # ---------- 数据安全获取（防止除零） ----------
        price = float(row.get("trade", 0))
        open_p = float(row.get("open", 0))
        high = float(row.get("high", 0))
        low = float(row.get("low", 0))
        nclose = float(row.get("nclose", 0))
        volume = float(row.get("volume", 0))
        ratio = float(row.get("ratio", 0))
        
        last_close = float(snapshot.get("last_close", 0))
        last_percent = float(snapshot.get("percent", 0) or 0)
        
        # 前几日量能数据
        last_v1 = float(snapshot.get("lastv1d", 0))
        last_v2 = float(snapshot.get("lastv2d", 0))
        last_v3 = float(snapshot.get("lastv3d", 0))
        
        # 数据有效性检查
        if price <= 0 or open_p <= 0 or last_close <= 0:
            debug["realtime_skip"] = "数据无效"
            return result
        
        # ========== 1. 开盘高走买入策略 ==========
        if mode in ("full", "buy_only"):
            buy_score = 0.0
            buy_reasons = []
            
            # 条件1: 开盘价高于昨日收盘（跳空高开）
            gap_up = (open_p - last_close) / last_close
            if gap_up > 0.002:  # 高开 0.2% 以上
                buy_score += 0.15
                buy_reasons.append(f"跳空高开{gap_up:.1%}")
            
            # 条件2: 开盘价接近当日最低价（开盘即最低，无回调空间）
            if low > 0 and open_p > 0:
                open_to_low_diff = (open_p - low) / open_p
                if open_to_low_diff < 0.005:  # 差距小于 0.5%
                    buy_score += 0.15
                    buy_reasons.append("开盘近最低")
            
            # 条件3: 当前价高于均价（高走态势）
            if nclose > 0 and price > nclose:
                price_above_nclose = (price - nclose) / nclose
                if price_above_nclose > 0.003:  # 高于均价 0.3%
                    buy_score += 0.15
                    buy_reasons.append(f"高走{price_above_nclose:.1%}")
            
            # 条件4: 当前价高于开盘价（持续上攻）
            if price > open_p:
                price_above_open = (price - open_p) / open_p
                if price_above_open > 0.005:
                    buy_score += 0.1
                    buy_reasons.append(f"上攻{price_above_open:.1%}")
            
            # 条件5: 量能配合（换手率健康）
            volume_bonus = self._volume_emotion_score(volume, ratio, last_v1, last_v2, last_v3, debug)
            buy_score += volume_bonus
            
            # 条件6: 多日情绪趋势（使用历史 5 日数据）
            multiday_score = self._multiday_trend_score(row, debug)
            if multiday_score > 0.3:
                buy_score += 0.2
                buy_reasons.append(f"趋势向上({multiday_score:.1f})")
            elif multiday_score > 0.1:
                buy_score += 0.1
                buy_reasons.append(f"趋势偏多({multiday_score:.1f})")
            elif multiday_score < -0.3:
                buy_score -= 0.2
                buy_reasons.append(f"趋势向下({multiday_score:.1f})")
            elif multiday_score < -0.1:
                buy_score -= 0.1
                buy_reasons.append(f"趋势偏空({multiday_score:.1f})")
            
            debug["realtime_buy_score"] = buy_score
            debug["realtime_buy_reasons"] = buy_reasons
            
            # 触发条件：得分 >= 0.4
            if buy_score >= 0.4:
                pos = min(buy_score, self.max_position)
                result = {
                    "triggered": True,
                    "action": "买入",
                    "position": round(pos, 2),
                    "reason": "实时高走买入: " + ", ".join(buy_reasons)
                }
                logger.debug(f"实时买入触发: score={buy_score:.2f} reasons={buy_reasons}")
                return result
        
        # ========== 2. 跌破均价卖出策略 ==========
        if mode in ("full", "sell_only"):
            if nclose > 0 and price < nclose:
                # 计算偏离度
                deviation = (nclose - price) / nclose
                
                # 根据昨日涨幅动态调整阈值
                max_normal_pullback = abs(last_percent) / 500 if abs(last_percent) < 10 else 0.02
                threshold = max(max_normal_pullback, 0.005) + 0.003
                
                if deviation > threshold:
                    # 偏离度越大，仓位越低
                    urgency = min(deviation / 0.03, 1.0)  # 偏离 3% 时最紧急
                    sell_pos = 1.0 - urgency * 0.5  # 最低保留 50%
                    
                    result = {
                        "triggered": True,
                        "action": "卖出",
                        "position": round(sell_pos, 2),
                        "reason": f"跌破均价{deviation:.1%} (阈值{threshold:.1%})"
                    }
                    debug["realtime_sell_deviation"] = deviation
                    logger.debug(f"实时卖出触发: deviation={deviation:.2%} threshold={threshold:.2%}")
                    return result
        
        # ========== 3. 量价信号策略 ==========
        volume_price_result = self._volume_price_signal(row, snapshot, mode, debug)
        if volume_price_result["triggered"]:
            return volume_price_result
        
        return result

    def _volume_emotion_score(self, volume: float, ratio: float, 
                               v1: float, v2: float, v3: float, debug: dict) -> float:
        """
        量能情绪评分
        
        Args:
            volume: 当日成交量
            ratio: 当日换手率
            v1, v2, v3: 前 1/2/3 日成交量
            debug: 调试信息
        
        Returns:
            float: 量能加分 (-0.2 ~ 0.2)
        """
        score = 0.0
        reasons = []
        
        # 换手率健康度检查
        if ratio <= 0:
            debug["volume_emotion"] = "换手率无效"
            return 0.0
        
        if 2 <= ratio <= 8:
            score += 0.05
            reasons.append("换手健康")
        elif ratio > 15:
            score -= 0.1
            reasons.append("换手过高")
        elif ratio < 0.5:
            score -= 0.05
            reasons.append("换手过低")
        
        # 量能放大检查（与前几日对比）
        avg_prev_vol = 0.0
        valid_vols = [v for v in [v1, v2, v3] if v > 0]
        if valid_vols:
            avg_prev_vol = sum(valid_vols) / len(valid_vols)
        
        if avg_prev_vol > 0 and volume > 0:
            vol_ratio = volume / avg_prev_vol
            if vol_ratio > 1.5:
                score += 0.1
                reasons.append(f"量能放大{vol_ratio:.1f}倍")
            elif vol_ratio > 1.2:
                score += 0.05
                reasons.append(f"量能温和放大")
            elif vol_ratio < 0.5:
                score -= 0.1
                reasons.append("量能萎缩")
        
        debug["volume_emotion_score"] = score
        debug["volume_emotion_reasons"] = reasons
        return score

    def _volume_price_signal(self, row: dict, snapshot: dict, mode: str, debug: dict) -> dict:
        """
        量价信号策略
        
        买入信号：
        1. 地量低价：成交量接近地量且价格接近近期低点（人气不活跃但有企稳迹象）
        2. 地量放大爬坡：从地量开始放量上涨（资金开始入场）
        3. 均线交叉蓄能：MA5 上穿 MA20（趋势反转信号）
        
        卖出信号：
        1. 天量高价：成交量异常放大且价格接近近期高点（短期见顶）
        2. 均线死叉：MA5 下穿 MA20（趋势走弱）
        
        Args:
            row: 当前行情数据
            snapshot: 历史快照（包含地量数据）
            mode: 评估模式
            debug: 调试信息
        
        Returns:
            dict: 包含 triggered, action, position, reason
        """
        result = {"triggered": False, "action": "持仓", "position": 0.0, "reason": ""}
        
        # ---------- 数据获取 ----------
        price = float(row.get("trade", 0))
        high = float(row.get("high", 0))
        low = float(row.get("low", 0))
        volume = float(row.get("volume", 0))  # 当日量比（已处理过）
        
        # MA 均线
        ma5 = float(snapshot.get("ma5d", 0) or row.get("ma5d", 0))
        ma20 = float(snapshot.get("ma20d", 0) or row.get("ma20d", 0))
        
        # 地量数据
        lowvol = float(snapshot.get("lowvol", 0))      # 最近最低价的地量
        llowvol = float(snapshot.get("llowvol", 0))    # 30日内地量
        
        # 历史量能
        v1 = float(snapshot.get("lastv1d", 0))
        v2 = float(snapshot.get("lastv2d", 0))
        v3 = float(snapshot.get("lastv3d", 0))
        
        # 3日高低价
        h1 = float(snapshot.get("lasth1d", 0))
        h2 = float(snapshot.get("lasth2d", 0))
        h3 = float(snapshot.get("lasth3d", 0))
        l1 = float(snapshot.get("lastl1d", 0))
        l2 = float(snapshot.get("lastl2d", 0))
        l3 = float(snapshot.get("lastl3d", 0))
        
        # 计算 3 日区间
        high_3d = max(h1, h2, h3) if all([h1, h2, h3]) else 0
        low_3d = min(l1, l2, l3) if all([l1, l2, l3]) else 0
        
        signals = []
        buy_score = 0.0
        sell_score = 0.0
        
        # 注意: volume 已经是量比 = real_volume / last6vol / ratio_t
        # 量比 < 0.5 表示地量，量比 > 1.5 表示放量，量比 > 3 表示天量
        # lowvol/llowvol 是历史地量的真实成交量，需要转换后比较
        
        # ========== 买入信号 ==========
        if mode in ("full", "buy_only"):
            
            # 1. 地量低价买入：当前量比很低（接近地量）+ 价格接近 3 日低点
            # 量比 < 0.6 认为是地量水平
            is_current_low_vol = volume < 0.6
            
            if low_3d > 0:
                # 价格接近 3 日低点
                is_near_low = price <= low_3d * 1.02
                
                if is_current_low_vol and is_near_low:
                    buy_score += 0.25
                    signals.append(f"地量低价(量比{volume:.1f})")
                elif is_current_low_vol:
                    buy_score += 0.1
                    signals.append(f"成交地量(量比{volume:.1f})")
            
            # 2. 地量放大爬坡：昨日量比低 + 今日放量上涨
            # 由于 v1 是真实成交量，需要将 llowvol 和 v1 比较
            if llowvol > 0 and v1 > 0 and volume > 0:
                # 昨日接近 30 日地量
                was_low_vol = v1 <= llowvol * 1.3
                # 今日放量（量比 > 1.5）
                is_volume_up = volume > 1.5
                # 价格上涨
                is_price_up = price > float(snapshot.get("last_close", 0)) * 1.005 if snapshot.get("last_close") else False
                
                if was_low_vol and is_volume_up and is_price_up:
                    buy_score += 0.3
                    signals.append(f"地量放大爬坡(量比{volume:.1f})")
            
            # 3. 均线金叉蓄能 / 平行均线蓄势
            if ma5 > 0 and ma20 > 0:
                ma_diff_pct = (ma5 - ma20) / ma20 if ma20 > 0 else 0
                ma_is_parallel = abs(ma_diff_pct) < 0.005  # 差距 < 0.5% 视为平行
                
                # MA5 > MA20 且差距在 2% 内（刚形成金叉）
                ma_cross_up = ma5 > ma20 and ma_diff_pct < 0.02
                # 价格在 MA5 附近或上方
                price_above_ma = price >= ma5 * 0.98 if ma5 > 0 else False
                
                if ma_cross_up and price_above_ma:
                    buy_score += 0.2
                    signals.append("均线金叉蓄能")
                elif ma_cross_up:
                    buy_score += 0.1
                    signals.append("MA5>MA20")
                elif ma_is_parallel and price_above_ma:
                    # 均线平行且价格在上方 = 蓄势爬坡
                    buy_score += 0.15
                    signals.append("均线平行蓄势")
                
                debug["ma_diff_pct"] = ma_diff_pct * 100
                debug["ma_is_parallel"] = ma_is_parallel
            
            # 4. 沿均线放量爬坡（阳线 + 突破新高）
            hmax = float(row.get("hmax", 0))
            high4 = float(row.get("high4", 0))
            current_high = float(row.get("high", 0))
            current_open = float(row.get("open", 0))
            
            is_yang_line = price > current_open * 1.001 if current_open > 0 else False
            is_vol_up = volume > 1.2  # 量比 > 1.2
            is_new_high = (hmax > 0 and current_high > hmax) or (high4 > 0 and current_high > high4)
            is_near_ma = ma5 > 0 and abs(price - ma5) / ma5 < 0.03
            
            if is_yang_line and is_vol_up and is_new_high:
                buy_score += 0.3
                signals.append("放量突破新高")
            elif is_yang_line and is_vol_up and is_near_ma:
                buy_score += 0.2
                signals.append("沿均线放量爬坡")
            elif is_yang_line and is_new_high:
                buy_score += 0.15
                signals.append("阳线创新高")
            
            debug["vp_buy_score"] = buy_score
            debug["vp_buy_signals"] = signals
            
            if buy_score >= 0.3:
                result = {
                    "triggered": True,
                    "action": "买入",
                    "position": min(buy_score + 0.2, 0.8),
                    "reason": "量价买入: " + ", ".join(signals)
                }
                logger.debug(f"量价买入触发: score={buy_score:.2f} signals={signals}")
                return result
        
        # ========== 卖出信号 ==========
        if mode in ("full", "sell_only"):
            sell_signals = []
            
            # 1. 天量高价：成交量异常放大 + 价格接近 3 日高点
            if volume > 0 and high_3d > 0:
                # 量比异常放大（> 3 倍）
                is_high_vol = volume > 3.0
                # 价格接近 3 日高点
                is_near_high = high >= high_3d * 0.98
                
                if is_high_vol and is_near_high:
                    sell_score += 0.3
                    sell_signals.append("天量高价")
                elif is_high_vol:
                    sell_score += 0.1
                    sell_signals.append("量能异常")
            
            # 2. 均线死叉（需排除平行情况）
            if ma5 > 0 and ma20 > 0:
                ma_diff_pct = (ma20 - ma5) / ma20 if ma20 > 0 else 0
                ma_is_parallel = abs(ma_diff_pct) < 0.005  # 差距 < 0.5% 视为平行
                
                # 只有差距 > 0.5% 且 MA5 < MA20 才算真正死叉
                ma_cross_down = ma5 < ma20 and not ma_is_parallel and ma_diff_pct < 0.02
                # 价格在 MA5 下方
                price_below_ma = price < ma5 * 0.98 if ma5 > 0 else False
                
                if ma_cross_down and price_below_ma:
                    sell_score += 0.25
                    sell_signals.append("均线死叉")
                elif ma_cross_down:
                    sell_score += 0.1
                    sell_signals.append("MA5<MA20")
                # 平行均线不触发卖出信号
            
            debug["vp_sell_score"] = sell_score
            debug["vp_sell_signals"] = sell_signals
            
            if sell_score >= 0.3:
                result = {
                    "triggered": True,
                    "action": "卖出",
                    "position": max(0.3, 1.0 - sell_score),
                    "reason": "量价卖出: " + ", ".join(sell_signals)
                }
                logger.debug(f"量价卖出触发: score={sell_score:.2f} signals={sell_signals}")
                return result
        
        return result

    def _multiday_trend_score(self, row: dict, debug: dict) -> float:
        """
        多日情绪趋势评分
        
        利用最近 5 天的 OHLC 数据分析趋势强度
        结合 MACD 序列和 KDJ 判断情绪方向
        
        Args:
            row: 当前行情数据（包含 lastp1d~5d, lasth1d~5d, lastl1d~5d, lasto1d~5d 等）
            debug: 调试信息
        
        Returns:
            float: 趋势评分 (-1.0 ~ 1.0)，正值看多，负值看空
        """
        score = 0.0
        reasons = []
        
        # ---------- 1. 价格趋势分析（5日收盘价） ----------
        closes = []
        for i in range(1, 6):
            c = float(row.get(f"lastp{i}d", 0))
            if c > 0:
                closes.append(c)
        
        if len(closes) >= 3:
            # 检查连续上涨/下跌
            up_count = sum(1 for i in range(len(closes)-1) if closes[i] > closes[i+1])
            down_count = sum(1 for i in range(len(closes)-1) if closes[i] < closes[i+1])
            
            if up_count >= 3:
                score += 0.2
                reasons.append(f"连涨{up_count}日")
            elif up_count >= 2:
                score += 0.1
                reasons.append("近期上涨")
            
            if down_count >= 3:
                score -= 0.2
                reasons.append(f"连跌{down_count}日")
            elif down_count >= 2:
                score -= 0.1
                reasons.append("近期下跌")
            
            # 价格重心判断（最近收盘 vs 5日均价）
            if closes:
                avg_close = sum(closes) / len(closes)
                latest_close = closes[0]
                if avg_close > 0:
                    price_position = (latest_close - avg_close) / avg_close
                    if price_position > 0.02:
                        score += 0.1
                        reasons.append("价格偏高")
                    elif price_position < -0.02:
                        score -= 0.1
                        reasons.append("价格偏低")
        
        # ---------- 2. 高低点趋势（5日最高/最低价） ----------
        highs = [float(row.get(f"lasth{i}d", 0)) for i in range(1, 6) if row.get(f"lasth{i}d", 0)]
        lows = [float(row.get(f"lastl{i}d", 0)) for i in range(1, 6) if row.get(f"lastl{i}d", 0)]
        
        if len(highs) >= 3 and len(lows) >= 3:
            # 高点抬升
            if highs[0] > highs[1] > highs[2]:
                score += 0.15
                reasons.append("高点抬升")
            elif highs[0] < highs[1] < highs[2]:
                score -= 0.15
                reasons.append("高点下降")
            
            # 低点抬升
            if lows[0] > lows[1] > lows[2]:
                score += 0.15
                reasons.append("低点抬升")
            elif lows[0] < lows[1] < lows[2]:
                score -= 0.15
                reasons.append("低点下降")
        
        # ---------- 3. MACD 趋势分析 ----------
        macd = float(row.get("macd", 0))
        macd_dif = float(row.get("macddif", 0))
        macd_dea = float(row.get("macddea", 0))
        
        # MACD 柱子方向
        if macd > 0:
            score += 0.1
            reasons.append("MACD柱正")
        elif macd < 0:
            score -= 0.1
            reasons.append("MACD柱负")
        
        # DIF/DEA 金叉死叉
        if macd_dif > macd_dea and macd_dif > 0:
            score += 0.1
            reasons.append("DIF>DEA")
        elif macd_dif < macd_dea and macd_dif < 0:
            score -= 0.1
            reasons.append("DIF<DEA")
        
        # MACD 序列趋势（最近6日）
        macd_history = []
        for i in range(1, 7):
            m = float(row.get(f"macdlast{i}", 0))
            if m != 0:
                macd_history.append(m)
        
        if len(macd_history) >= 3:
            # 柱子连续放大/缩小
            if all(macd_history[i] > macd_history[i+1] for i in range(min(3, len(macd_history)-1))):
                score += 0.1
                reasons.append("MACD放大")
            elif all(macd_history[i] < macd_history[i+1] for i in range(min(3, len(macd_history)-1))):
                score -= 0.1
                reasons.append("MACD缩小")
        
        # ---------- 4. KDJ 超买超卖 ----------
        kdj_j = float(row.get("kdj_j", 50))
        kdj_k = float(row.get("kdj_k", 50))
        kdj_d = float(row.get("kdj_d", 50))
        
        if kdj_j > 80 and kdj_k > 80:
            score -= 0.1
            reasons.append("KDJ超买")
        elif kdj_j < 20 and kdj_k < 20:
            score += 0.1
            reasons.append("KDJ超卖")
        
        # J 值方向
        if kdj_j > kdj_k > kdj_d:
            score += 0.05
            reasons.append("KDJ金叉")
        elif kdj_j < kdj_k < kdj_d:
            score -= 0.05
            reasons.append("KDJ死叉")
        
        # ---------- 5. 布林带位置 ----------
        upper = float(row.get("upper", 0))
        lower = float(row.get("lower", 0))
        price = float(row.get("trade", 0))
        
        if upper > 0 and lower > 0 and price > 0:
            boll_mid = (upper + lower) / 2
            boll_width = upper - lower
            
            if boll_width > 0:
                # 价格在布林带中的位置 (0~1, 超过1为突破上轨)
                boll_pos = (price - lower) / boll_width
                if boll_pos > 0.9:
                    score -= 0.1
                    reasons.append("接近上轨")
                elif boll_pos < 0.1:
                    score += 0.1
                    reasons.append("接近下轨")
        
        # ---------- 6. 多日最高价突破 ----------
        hmax = float(row.get("hmax", 0))
        high4 = float(row.get("high4", 0))
        max5 = float(row.get("max5", 0))
        current_high = float(row.get("high", 0))
        
        if hmax > 0 and current_high > hmax:
            score += 0.2
            reasons.append("突破历史高")
        elif max5 > 0 and current_high > max5:
            score += 0.1
            reasons.append("突破5日高")
        
        # 限制得分范围
        score = max(-1.0, min(1.0, score))
        
        debug["multiday_trend_score"] = score
        debug["multiday_trend_reasons"] = reasons
        return score

    def _hold(self, reason: str, debug: dict) -> dict:
        """返回持仓决策"""
        return {
            "action": "持仓",
            "position": 0.0,
            "reason": reason,
            "debug": debug
        }


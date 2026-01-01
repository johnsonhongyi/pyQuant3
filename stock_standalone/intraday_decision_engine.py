# -*- coding: utf-8 -*-
"""
盘中决策引擎 - 增强版
支持买入/卖出信号生成、动态仓位计算、趋势强度评估、止损止盈检测
"""
import logging
import datetime as dt
from typing import Any, Union

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
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    max_position: float
    
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
        
        logger.info(f"IntradayDecisionEngine 初始化: stop_loss={stop_loss_pct:.1%}, " +
                   f"take_profit={take_profit_pct:.1%}, trailing={trailing_stop_pct:.1%}, " +
                   f"max_pos={max_position:.1%}")

    def evaluate(self, row: dict[str, Any], snapshot: dict[str, Any], mode: str = "full") -> dict[str, Any]:
        """
        评估当前行情并生成买卖决策及详尽的调试信息
        
        Args:
            row: 当前行情数据字典 (由 df_all.loc[code].to_dict() 提供)
            snapshot: 辅助快照数据 (包含昨收、昨量、成本价等)
            mode: 评估模式 ("full", "buy_only", "sell_only")
            
        Returns:
            dict: {
                "action": str ("买入", "卖出", "持仓", "止损", "止盈", "警告"),
                "position": float (新目标持仓, 0.0-1.0),
                "reason": str (触发理由),
                "debug": dict (盘中结构、趋势强度等分析信息)
            }
        """
        code = row.get("code", "unknown")
        debug: dict[str, Any] = {}
        price = float(row.get("trade", 0))
        high = float(row.get("high", 0))
        debug["high_val"] = high
        low = float(row.get("low", 0)) # 用于后续分析
        open_p = float(row.get("open", 0))
        volume = float(row.get("volume", 0))
        ratio = float(row.get("ratio", 0))
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))
        
        # 💥 关键点：获取实时均价 nclose (VWAP)，优先从 row 取，其次从 snapshot 取
        nclose = float(row.get("nclose", snapshot.get("nclose", 0)))
        debug["nclose"] = nclose

        if price <= 0:
            logger.warning(f"Engine: {code} price is 0, skip evaluate")
            return self._hold("价格无效", debug)
        
        # ---------- 基础行情分析（提前进行以填充调试信息） ----------
        # 1. 均线有效性检查
        if ma5 > 0 and ma10 > 0:
            # 盘中结构分析
            structure = self._intraday_structure(price, high, open_p, ratio)
            debug["structure"] = structure
            
            # 趋势强度评估
            trend_strength = self._trend_strength(row, debug)
            debug["trend_strength"] = trend_strength
        else:
            structure = "UNKNOWN"
            trend_strength = 0.0
            debug["structure"] = structure
            debug["trend_strength"] = trend_strength
            debug["analysis_skip"] = "均线数据无效"
            debug["trend_strength"] = trend_strength
            debug["analysis_skip"] = "均线数据无效"
        
        # ---------- 策略进化：痛感与防御机制 (Pain & Defense) ----------
        # 1. 记仇机制 (PTSD)：如果这只票最近连续让你亏钱，就别碰它！
        loss_streak = int(snapshot.get("loss_streak", 0))
        if loss_streak >= 2:
            # 连续亏损 2 次：进入"冷宫"
            if mode != "sell_only":
                return self._hold(f"黑名单:连续亏损{loss_streak}次", debug)
        elif loss_streak == 1:
            # 刚亏过 1 次：在此基础上买入需加倍谨慎 (扣分)
            debug["PTSD扣分"] = -0.15

        # 2. 环境感知 (Sensing)：如果全市场胜率低，开启防御模式
        market_win_rate = float(snapshot.get("market_win_rate", 0.5))
        defense_level = 0.0
        if market_win_rate < 0.3:
            defense_level = 0.2 # 极难买入
            debug["环境防御"] = "极高(胜率<30%)"
        elif market_win_rate < 0.45:
            defense_level = 0.1 # 提高门槛
            debug["环境防御"] = "中等(胜率<45%)"
        
        # 将防御等级存入 snapshot/debug 供后续买入逻辑扣减
        debug["defense_level"] = defense_level
        
        # ---------- 0. 选股分权重加成 (New: 对应 “反向验证” 需求) ----------
        # 根据 StockSelector 的评分增加基础权重，评分越高，买入信心越足
        selection_score = float(snapshot.get("score", 0))
        selection_bonus = 0.0
        if selection_score >= 65:
            selection_bonus = 0.2
            debug["选股加成"] = f"顶格推荐({selection_score})"
        elif selection_score >= 55:
            selection_bonus = 0.15
            debug["选股加成"] = f"高分推荐({selection_score})"
        elif selection_score >= 45:
            selection_bonus = 0.08
            debug["选股加成"] = f"强势入选({selection_score})"
        
        debug["selection_bonus"] = selection_bonus
        
        # ---------- 💥 涨跌停与一字板过滤 (New) ----------
        last_close = float(snapshot.get("last_close", 0))
        limit_info = self._is_price_limit(row.get("code", ""), price, last_close, high, low, open_p, ratio, snapshot)
        debug.update(limit_info)
        
        # 1. 一字涨停或封死涨停：持仓不动，信号无效
        if limit_info["limit_up"]:
            if limit_info["one_word"]:
                return self._hold("一字涨停，持仓观望", debug)
            if mode != "buy_only":
                return self._hold("封死涨停，利润奔跑", debug)
            else:
                return self._hold("已封涨停，无法买入", debug)
        
        # 2. 跌停状态：信号通常无效 (排队想卖也卖不掉，买入则大忌)
        if limit_info["limit_down"]:
            return self._hold("处于跌停状态，信号无效", debug)

        # ---------- 实时高优先级决策（包含跌破均价、开盘高开下杀等） ----------
        is_t1_restricted = False
        if snapshot.get('buy_date'):
            # import datetime as dt
            today_str = dt.datetime.now().strftime('%Y-%m-%d')
            if snapshot['buy_date'].startswith(today_str):
                is_t1_restricted = True

        priority_result = self._realtime_priority_check(row, snapshot, mode, debug, is_t1_restricted)
        if priority_result["triggered"]:
            # 【优化】如果卖出是因为"高开下杀放量"，且未返回均线，则执行
            return priority_result

        # ---------- 基础止损止盈检查 (New: 增加 T+1 限制) ----------
        if mode in ("full", "sell_only"):
            if is_t1_restricted:
                debug["sell_skip"] = "T+1限制，跳过止损检测"
            else:
                stop_result = self._stop_check(row, snapshot, debug)
                if stop_result["triggered"]:
                    return {
                        "action": stop_result["action"],
                        "position": stop_result["position"],
                        "reason": stop_result["reason"],
                        "debug": debug
                    }
        
        # ========== 实时行情高优先级决策（优先级次高） ==========
        realtime_result = self._realtime_priority_check(row, snapshot, mode, debug, is_t1_restricted)
        if realtime_result["triggered"]:
            return {
                "action": realtime_result["action"],
                "position": realtime_result["position"],
                "reason": realtime_result["reason"],
                "debug": debug
            }
        
        # 如果均线无效，虽然过了实时检查，但常规买卖逻辑无法继续
        if ma5 <= 0 or ma10 <= 0:
            return self._hold("均线数据无效", debug)

        # ---------- 卖出信号检测 ----------
        if mode in ("full", "sell_only"):
            if is_t1_restricted:
                debug["sell_skip"] = "T+1限制，跳过卖出信号检测"
            else:
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
            
            # 【新增】支撑位开仓检测 (Support Rebound)
            # 即使均线信号平平，如果跌到了强支撑位且企稳，也是高胜率开仓点
            support_score, support_reason = self._support_rebound_check(row, snapshot, debug)
            if support_score > 0.1:
                if action == "持仓":
                    # 支撑位反转：覆盖原有的观望信号
                    action = "买入"
                    base_pos = 0.2  # 基础仓位
                    ma_reason = f"[支撑反弹] {support_reason}"
                elif action == "买入":
                    # 双重确认
                    base_pos += 0.1
                    ma_reason += f" & {support_reason}"
            
            debug["ma_decision"] = ma_reason

            if action == "持仓":
                return self._hold(ma_reason, debug)
            
            if action == "买入":
                # 💥 核心修正：结构性熔断机制 💥
                # 如果盘中结构判定为"派发"(冲高大幅回落)，坚决禁止开仓，无论其他指标多好
                # 这直接解决了"冲高回落收盘还是大于前日收盘加是加仓信号"的非理性行为
                if structure == "派发":
                    debug["refuse_buy"] = "结构为派发(冲高回落)"
                    return self._hold(f"结构{structure}禁买", debug)
                
                # 1. 应用基础过滤器
                base_pos += self._yesterday_anchor(price, snapshot, debug)
                base_pos += self._structure_filter(row, debug)
                base_pos += self._extreme_filter(row, debug)
                
                # 2. 趋势强度与多日情绪加成
                multiday_score = self._multiday_trend_score(row, debug)
                if trend_strength > 0.5 or multiday_score > 0.3:
                    base_pos += 0.1
                elif trend_strength < -0.3:
                    base_pos -= 0.1
                
                # 3. 量能与均价约束 (关键点)
                base_pos += self._volume_bonus(row, debug)
                
                # --- 进化: 应用防御惩罚 ---
                base_pos -= defense_level
                if "PTSD扣分" in debug:
                    base_pos += debug["PTSD扣分"] # 这是一个负数
                
                # 4. 选股分加成
                base_pos += selection_bonus
                
                # 5. 支撑位得分加成
                if support_score > 0:
                    base_pos += support_score
                    debug["支撑加成"] = support_score
                
                # 如果价格在今日今日成交均价（nclose）下方，极大程度严控买入
                if nclose > 0 and price < nclose:
                    penalty = 0.3
                    if structure == "走弱":
                        penalty = 0.4
                    # 注意：派发已被熔断，这里不需要重复 check
                    
                    # 例外：如果是强支撑位抄底(score>0.2)且偏离均价不远，由于是左侧交易，允许在均价线下
                    if support_score > 0.2 and (nclose - price)/nclose < 0.01:
                         penalty = 0.1 # 减轻惩罚
                         debug["均价约束"] = "支撑位豁免"
                    
                    base_pos -= penalty
                    if "均价约束" not in debug:
                        debug["均价/结构约束"] = f"线下{structure}，扣减{penalty}"
                    
                # 【新增】昨日均价线约束
                last_nclose = float(snapshot.get("nclose", 0))
                if last_nclose > 0 and price < last_nclose:
                    # 同样，若有强支撑，减轻惩罚
                    if support_score > 0.2:
                        base_pos -= 0.05
                    else:
                        base_pos -= 0.15
                        debug["昨日锚点约束"] = "低于昨均价"

                # 6. 低位大仓位逻辑 (靠近 low10/low60 加成)
                low10 = float(snapshot.get("low10", 0))
                low60 = float(snapshot.get("low60", 0))
                if (low10 > 0 and price < low10 * 1.02) or (low60 > 0 and price < low60 * 1.03):
                    if structure != "派发" and price > nclose:
                        base_pos += 0.1
                        debug["开仓权重"] = "低位加成"

                # 【新增】VWAP (成交均价) 趋势判定：过滤无效震荡单
                # 逻辑：均价线代表当日/昨日的市场平均成本。成本下移说明趋势走弱。
                # 只有在 "重心上移" 或 "低位企稳" 时才开仓。
                vwap_score = self._vwap_trend_check(row, snapshot, debug)
                base_pos += vwap_score
                
                # 如果 VWAP 趋势严重走坏 (score < -0.2) 且没有强支撑豁免，直接熔断
                if vwap_score < -0.2 and support_score < 0.15:
                    return self._hold(f"趋势重心下移({debug.get('VWAP趋势', '')})", debug)

                final_pos = max(min(base_pos, self.max_position * 1.2), 0)
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
                       snapshot: dict[str, Any], structure: str, debug: dict[str, Any]) -> tuple[str, float, str]:
        """
        卖出信号判定
        
        Returns:
            (action, position_delta, reason)
        """
        sell_score = 0.0
        last_close = float(snapshot.get("last_close", 0))
        high = float(debug.get("high_val", 0)) # 在 evaluate 中已通过 row 获取
        if high <= 0: # 降级方案
            high = price
        
        reasons: list[str] = []
        if price > ma5 * 1.05:
            sell_score += 0.2
            reasons.append("短线乖离过大")
        if price < ma10:
            sell_score += 0.15
            reasons.append("价格低于MA10")
        if structure in ["派发", "走弱"]:
            sell_score += 0.1
            reasons.append(f"结构{structure}")
        if last_close > 0 and price < last_close * 0.97:
            sell_score += 0.2
            reasons.append(f"跌破昨收{last_close:.2f}")
            
        # 额外加分项：反弹无力/均价线压制检测
        nclose = float(debug.get("nclose", snapshot.get("nclose", 0)))
        if nclose > 0:
             if price < nclose * 0.985:
                 sell_score += 0.25 # 增加权重
                 reasons.append("深跌均价线下")
             elif price < nclose:
                 # 衝高回落后的反抽无力
                 if high > nclose * 1.005 and (high - price)/high > 0.03:
                     # "华力创通"式：上午冲高失败，持续远离均价线
                     sell_score += 0.35
                     reasons.append("衝高回落且均价线压制(抛压大)")
                 else:
                     sell_score += 0.15
                     reasons.append("均价线下运行")
        
        # 【新增】利用 snapshot 中的日内追踪字段进行更精确的冲高回落检测
        pump_height = float(snapshot.get('pump_height', 0))
        pullback_depth = float(snapshot.get('pullback_depth', 0))
        
        # 急速冲高回落检测：泵高 > 3%，回撤 > 2.5%，且已跌破均价
        if pump_height > 0.03 and pullback_depth > 0.025 and price < nclose:
            sell_score += 0.45  # 高权重
            reasons.append(f"急速冲高回落(泵高{pump_height:.1%}回撤{pullback_depth:.1%})")
            
        # 二次冲高失败检测：如果 high 距离日内最高还有较大差距，说明反弹乏力
        highest_today = float(snapshot.get('highest_today', high))
        if highest_today > 0 and high < highest_today * 0.985 and price < nclose:
            # 日内次高点也无法触及前高的 98.5%，反弹乏力
            sell_score += 0.2
            reasons.append("二次冲高失败")
            
        # “连阳持仓”保护逻辑：如果是强势连阳，且未出现结构走弱，略微调低卖出分数
        # 注意：这里我们无法直接获取 row，但可以使用 debug 中缓存的信息或 snapshot
        # 为了兼容性，我们修改 _multiday_trend_score 使其能处理 snapshot
        multiday_score = self._multiday_trend_score(snapshot, debug)
        if multiday_score > 0.3 and structure not in ["派发", "走弱"]:
            sell_score -= 0.15
            debug["持仓保护"] = "连阳护航"
        
        debug["sell_score"] = sell_score
        debug["sell_reasons"] = reasons
        
        if sell_score >= 0.5 or (structure == "派发" and sell_score >= 0.35):
            # 派发结构下，更低的分数即可触发卖出
            return ("卖出", -max(sell_score, 0.5), " | ".join(reasons))
        
        return ("持仓", 0, "")
    
    # ==================== 止损止盈 ====================
    
    def _stop_check(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> dict[str, Any]:
        """
        全量止损止盈及技术位破位检测
        """
        price = float(row.get("trade", 0))
        high = float(row.get("high", 0))
        low = float(row.get("low", 0))
        volume = float(row.get("volume", 0))
        nclose = float(debug.get("nclose", snapshot.get("nclose", 0)))
        cost_price = float(snapshot.get("cost_price", 0))
        highest_since_buy = float(snapshot.get("highest_since_buy", 0))
        
        if cost_price <= 0 or price <= 0:
            return {"triggered": False, "action": "", "position": 1.0, "reason": ""}
        
        pnl_pct = (price - cost_price) / cost_price
        debug["盈亏比例"] = pnl_pct
        
        # 1. 基础百分比止损 (分批)
        if pnl_pct < -self.stop_loss_pct:
            # 达到硬止损线，全清
            return {"triggered": True, "action": "止损", "position": 0.0, "reason": f"硬止损触发: 亏损{abs(pnl_pct):.1%}"}
        
        if pnl_pct < -0.025: # 预警止损收紧到 2.5%
            # 检查是否有反弹无力迹象（低于均价）或结构走弱
            structure = debug.get("structure", "UNKNOWN")
            if (nclose > 0 and price < nclose) or structure in ["派发", "走弱"]:
                # 如果是派发，直接全清，不再减半
                target_pos = 0.0 if structure == "派发" else 0.4
                return {"triggered": True, "action": "预警止损", "position": target_pos, "reason": f"结构{structure}且亏损{abs(pnl_pct):.1%}"}

        # 2. 基础百分比止盈 (分三步)
        if pnl_pct >= self.take_profit_pct:
            return {"triggered": True, "action": "目标止盈", "position": 0.0, "reason": f"达到目标止盈: {pnl_pct:.1%}"}
        
        if 0.05 <= pnl_pct < self.take_profit_pct:
            # 盈利 5% 减 30% 保护利润
            debug["分步止盈"] = "第一目标已达"
            # 保持盈利 5% 的减仓建议可以通过实时判断后续给出

        # 3. 分级移动止盈 (回撤保护，根据盈利幅度动态调整回撤容忍度)
        if highest_since_buy > 0 and highest_since_buy > cost_price:
            drawdown = (highest_since_buy - price) / highest_since_buy
            
            # 分级回撤阈值：盈利越高，容忍度越大
            if pnl_pct >= 0.08:
                # 盈利 > 8%：容忍 5% 回撤
                trailing_threshold = 0.05
                debug["移动止盈档位"] = "高盈利档(8%+)"
            elif pnl_pct >= 0.05:
                # 盈利 5-8%：容忍 4% 回撤
                trailing_threshold = 0.04
                debug["移动止盈档位"] = "中盈利档(5-8%)"
            elif pnl_pct >= 0.03:
                # 盈利 3-5%：容忍 3% 回撤
                trailing_threshold = 0.03
                debug["移动止盈档位"] = "低盈利档(3-5%)"
            else:
                trailing_threshold = self.trailing_stop_pct  # 默认阈值
                
            if pnl_pct > 0.03 and drawdown > trailing_threshold:
                # 保留部分仓位让利润继续奔跑
                retain_pos = 0.2 if pnl_pct >= 0.05 else 0.3
                return {"triggered": True, "action": "移动止盈", "position": retain_pos, "reason": f"最高回撤{drawdown:.1%}(阈值{trailing_threshold:.1%})"}

        # 4. 技术位破位检测 (大开大合)
        low10 = float(snapshot.get("low10", 0))
        low60 = float(snapshot.get("low60", 0))
        hmax = float(snapshot.get("hmax", 0))
        lower = float(snapshot.get("lower", 0))
        
        # 平台破位/关键支撑
        break_reason = ""
        if lower > 0 and price < lower:
            break_reason = "跌破布林下轨"
        elif low10 > 0 and price < low10 * 0.995:
            break_reason = "跌破10日低点"
        elif hmax > 0 and price < hmax * 0.985: # 原高点转支撑失效
            break_reason = f"跌破平台支撑({hmax:.2f})"
        
        if low60 > 0 and price < low60 * 0.98: # 60日大底破位
            break_reason = "跌破60日底线"
            
        if break_reason:
            # 如果是带量破位（量比 > 2）
            if volume > 2.0:
                return {"triggered": True, "action": "强制清仓", "position": 0.0, "reason": f"放量破位: {break_reason}"}
            else:
                return {"triggered": True, "action": "破位减仓", "position": 0.3, "reason": break_reason}

        # 5. 布林压力位逻辑 (upper1-5)
        uppers = [snapshot.get(f'upper{i}', 0) for i in range(1, 6)]
        for i, up in enumerate(reversed(uppers)):
            level = 5 - i
            if up > 0 and price >= up:
                # 触及 upper4/5 时检查盘中结构
                structure = debug.get("structure", "中性")
                if level >= 4:
                    if structure in ["派发", "走弱"] or (volume > 2.5 and price < nclose):
                        return {"triggered": True, "action": "高位止盈", "position": 0.3 if level == 5 else 0.5, "reason": f"触及布林{level}轨压力+盘中走弱"}
                    debug["布林压力"] = f"触及{level}轨，观察中"
                break

        # 6. 大开大合逻辑 (大幅振幅且回落)
        if nclose > 0:
            daily_amplitude = (high - low) / nclose if nclose > 0 else 0
            if daily_amplitude > 0.08: # 振幅超过 8%
                # 如果从高位回撤显著且低于均价
                if high > 0 and (high - price) / high > 0.04 and price < nclose:
                    return {"triggered": True, "action": "振幅减仓", "position": 0.2, "reason": f"大开大合(振幅{daily_amplitude:.1%})且回落"}

        return {"triggered": False, "action": "", "position": 1.0, "reason": ""}

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
        
        debug["趋势分量"] = {
            "均线排列": score,
            "MACD方向": macd
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
        
        debug["量能加成"] = bonus
        return bonus

    # ==================== 原有方法（保持兼容） ====================
    
    def _intraday_structure(self, price: float, high: float, open_p: float, ratio: float) -> str:
        """判断盘中结构"""
        # 优化“派发”判定：即使换手率没到 8，如果回落严重且带量，也算派发
        fall_from_high = (high - price) / high if high > 0 else 0
        
        # 增加对“冲高回落”的敏感度
        if high > 0:
            # 1. 严重回落：回落 > 3.5%
            if fall_from_high > 0.035:
                # 【修正逻辑】如果回落虽然大，但依然保持在 昨日收盘 2% 以上，且高于开盘价，视为“强洗盘”而非完全派发
                # 用户需求: "冲高回落收盘还是大于前日收盘加是加仓信号"
                # 我们这里放宽对“强洗盘”的判定，交给后续逻辑去决定是否买入
                if open_p > 0 and price > open_p and ratio > 2:
                     return "震荡" # 中性偏强
                
                return "派发"

            # 2. 较大量能下的回落：回落 > 2% 且换手 > 4
            if fall_from_high > 0.02 and ratio > 4:
                return "派发"
        
        if price > open_p and ratio > 5:
            return "强势"
        if price < open_p and ratio > 3.5: # 降低走弱判断的换手阈值，更早识别走弱
            return "走弱"
        
        return "中性"

    def _ma_decision(self, price: float, ma5: float, ma10: float) -> tuple[str, float, str]:
        """均线决策"""
        bias = (price - ma5) / ma5
        if price > ma5 > ma10 and bias < 0.015:
            return "买入", 0.2 + bias, "站稳MA5，趋势延续"
        if price < ma5 < ma10:
            return "卖出", -0.3, "跌破MA5/MA10"
        if bias > 0.05:
            return "持仓", 0, "远离MA5，追高风险"
        return "持仓", 0, "均线结构中性"

    def _yesterday_anchor(self, price: float, snapshot: dict, debug: dict) -> float:
        """昨日锚点惩罚"""
        penalty = 0.0
        last_close = float(snapshot.get("last_close", 0))
        last_nclose = float(snapshot.get("nclose", 0))
        if last_close > 0 and price < last_close:
            penalty -= 0.1
        if last_nclose > 0 and price < last_nclose:
            penalty -= 0.15
        debug["昨日约束"] = penalty
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
        debug["结构约束"] = penalty
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
        debug["指标约束"] = penalty
        return penalty

    def _vwap_trend_check(self, row: dict, snapshot: dict, debug: dict) -> float:
        """
        VWAP (均价) 趋势过滤器
        User Requirement: 通过实时数据的均价线和昨天的均价来判定小趋势走高还是小转大
        """
        current_nclose = float(row.get("nclose", 0))
        last_nclose = float(snapshot.get("nclose", 0)) # 昨日均价
        price = float(row.get("trade", 0))
        
        score = 0.0
        
        if current_nclose > 0 and last_nclose > 0:
            # 1. 重心上移 (Trend Up)
            if current_nclose > last_nclose:
                # 趋势健康：均价上移且价格在均价之上
                if price > current_nclose:
                    score += 0.15
                    debug["VWAP趋势"] = f"重心上移(>{last_nclose:.2f})+价强"
                else:
                    score += 0.05
                    debug["VWAP趋势"] = "重心上移+震荡"
            
            # 2. 重心下移 (Trend Down)
            elif current_nclose < last_nclose:
                # 趋势走弱：均价下移
                debug["VWAP趋势"] = f"重心下移(<{last_nclose:.2f})"
                
                # 如果价格在今日均价之下，且均价低于昨日均价 -> 双重空头趋势
                if price < current_nclose:
                    score -= 0.3  # 重罚，过滤大部分无效买单
                    debug["VWAP趋势"] += "+价弱"
                else:
                    # 价格在均价之上，可能是反抽，需谨慎
                    score -= 0.1
                    debug["VWAP趋势"] += "+反抽"
                    
            # 3. 小转大判定 (Small turning Big)
            # 如果昨日均价和前日均价接近(震荡)，今日突然大幅拉离昨日均价
            last_nclose_2 = float(snapshot.get("lastnclose1d", last_nclose)) # 暂无lastnclose1d字段，用last_nclose兜底
            # 这里简化为：如果重心上移幅度超过 1.5%，确认为趋势爆发
            if current_nclose > last_nclose * 1.015:
                score += 0.1
                debug["VWAP趋势"] += "|爆发"

        return score

    # ==================== 实时行情高优先级决策 ====================
    
    def _realtime_priority_check(self, row: dict[str, Any], snapshot: dict[str, Any], mode: str, debug: dict[str, Any], is_t1_restricted: bool = False) -> dict[str, Any]:
        """
        实时行情高优先级决策（优先级高于普通均线信号）
        """
        result = {"triggered": False, "action": "持仓", "position": 0.0, "reason": "", "debug": debug}
        
        # 引入 VWAP 趋势检查，作为实时决策的基石
        # User Rule: 有效买卖单需参考均价线趋势
        vwap_score = self._vwap_trend_check(row, snapshot, debug)
        vwap_trend_ok = vwap_score >= -0.05 # 允许 mild weakness, 但 heavy weakness (-0.3) 免谈
        
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

        # 提取最近 5 日 OHLC 数据
        last_closes = [float(snapshot.get(f"lastp{i}d", 0)) for i in range(1, 6)]
        last_lows = [float(snapshot.get(f"lastl{i}d", 0)) for i in range(1, 6)]
        last_highs = [float(snapshot.get(f"lasth{i}d", 0)) for i in range(1, 6)]
        last_opens = [float(snapshot.get(f"lasto{i}d", 0)) for i in range(1, 6)]
        
        # 数据有效性检查
        if price <= 0 or open_p <= 0 or last_close <= 0:
            debug["realtime_skip"] = "数据无效"
            return result

        # ========== 0. 预研分析：超跌与泵感检测 ==========
        debug["win"] = snapshot.get("win", 0)
        debug["sum_perc"] = snapshot.get("sum_perc", 0)
        debug["red"] = snapshot.get("red", 0)
        debug["gren"] = snapshot.get("gren", 0)

        is_oversold = False
        oversold_reason = ""
        if last_closes[0] > 0 and last_closes[4] > 0:
            # 5日累计跌幅
            drop_5d = (last_closes[0] - last_closes[4]) / last_closes[4]
            # 快速下跌定义：5日跌 > 10% 且最近3日低点下移
            if drop_5d < -0.10 and last_lows[0] < last_lows[1] < last_lows[2]:
                is_oversold = True
                oversold_reason = f"5日超跌{abs(drop_5d):.1%}"

        morning_pump = False
        pump_height = 0.0
        if open_p > 0 and high > open_p:
            pump_height = (high - open_p) / open_p
            if pump_height > 0.025: # 早盘泵高超过 2.5%
                morning_pump = True
        
        # ========== 1. 开盘高走买入策略 ==========
        if mode in ("full", "buy_only"):
            buy_score = 0.0
            buy_reasons = []
            
            # 风险熔断：如果是派发结构，严禁开盘高走买入
            structure = debug.get("structure", "UNKNOWN")
            if structure == "派发":
                debug["realtime_skip"] = "派发结构禁买"
                return result
            
            # 趋势熔断：如果重心显著下移，禁止普通高开买入 (User Requirement)
            if not vwap_trend_ok:
                 # 除非是超跌反弹或极强突破，否则不买
                 # 这里我们设置一个标记，后续如果有强力理由才放行
                 debug["realtime_warn"] = "VWAP重心下移，需极强信号"

            # 条件1: 开盘价高于昨日收盘（跳空高开）
            gap_up = (open_p - last_close) / last_close
            if gap_up > 0.01:  # 提高到 1.0% 以上才算有效高开
                buy_score += 0.15
                buy_reasons.append(f"显著高开{gap_up:.1%}")
            elif gap_up > 0.003:
                buy_score += 0.05
                buy_reasons.append(f"微幅高开{gap_up:.1%}")
            
            # 条件2: 开盘价接近当日最低价（开盘即最低，无回调空间）
            if low > 0 and open_p > 0:
                open_to_low_diff = (open_p - low) / open_p
                if open_to_low_diff < 0.005:  # 差距小于 0.5%
                    buy_score += 0.15
                    buy_reasons.append("开盘近最低")
            
            # 条件3: 当前价高于均价（高走态势）
            if nclose > 0 and price > nclose:
                price_above_nclose = (price - nclose) / nclose
                if price_above_nclose > 0.008:  # 提高到 0.8% 以上
                    buy_score += 0.15
                    buy_reasons.append(f"稳步高走{price_above_nclose:.1%}")
                elif price_above_nclose > 0.003:
                    buy_score += 0.05
                    buy_reasons.append(f"站稳均价")
            
            # 【新增】风险项：如果虽然高开但已经跌破今日均价，大幅扣分
            if nclose > 0 and price < nclose:
                buy_score -= 0.35
                buy_reasons.append("已跌破今日均价")
            
            # 条件4: 当前价高于开盘价（持续上攻）
            if price > open_p:
                price_above_open = (price - open_p) / open_p
                if price_above_open > 0.01: # 提高到 1% 以上
                    buy_score += 0.1
                    buy_reasons.append(f"显著上攻{price_above_open:.1%}")
            
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

            # 条件7: 超跌反弹模式 (高优先级加分)
            if is_oversold and price > nclose:
                # 如果超跌后今日站上均线，是一个极佳的反弹切入点
                buy_score += 0.3
                buy_reasons.append(f"超跌反弹({oversold_reason})")

            # 条件8: 大阳变盘点/惜售爆发检测 (Consolidation & Momentum Breakout)
            win = int(snapshot.get("win", 0))
            sum_perc = float(snapshot.get("sum_perc", 0))
            red = int(snapshot.get("red", 0))
            
            # 情况 A: 强势惜售后的加速 (win >= 3，小幅连阳后爆发)
            if win >= 3 and (sum_perc / win < 3.5):
                # 盘中表现：突破分时均价且已经产生一定涨幅
                if price > nclose and (price - last_close) / last_close > 0.01:
                    buy_score += 0.25
                    buy_reasons.append(f"惜售连阳({win}d)加速")

            # 情况 B: 中线走红后的变盘突破 (red >= 5，站稳5日线后横盘爆发)
            gren = int(snapshot.get("gren", 0))
            if red >= 5 and abs(sum_perc) < 12:
                # 变盘信号：价格拉升封锁波动，突破今日开盘价并站稳均线
                if price > open_p * 1.005 and price > nclose:
                    # 趋势纯度加成
                    purity_bonus = 0.1 if (red - gren) >= 5 else 0.0
                    
                    # 分别处理：“高开高走”和“低开高走”
                    if open_p >= last_close: # 高开/平开
                        buy_score += (0.2 + purity_bonus)
                        buy_reasons.append(f"中线红柱({red}d)突破")
                    elif price > last_close * 1.005: # 低开反转大阳
                        buy_score += (0.3 + purity_bonus)
                        buy_reasons.append(f"低开爆发反转")
            
            # 情况 C: 极强趋势确认 (win >= 5 + 站稳均价)
            if win >= 5 and price > nclose:
                buy_score += 0.15
                buy_reasons.append("极强波段确认")

            # 【新增】条件9: 冲高回落企稳买入 (User Request: 冲高回落收盘还是大于前日收盘加是加仓信号)
            # 逻辑：当日由高点回落，但 Price > Last Close * 1.02 (保持强势)，且 Price > Nclose (均价支撑)
            if high > 0 and (high - price) / high > 0.025: # 回落幅度 > 2.5%
                if price > last_close * 1.02 and price > nclose:
                     # 必须有量能配合，证明是换手而非出货
                     if ratio > 3:
                         buy_score += 0.25
                         buy_reasons.append(f"冲高回落企稳(>{last_close:.2f})")
            
            
            # 【新增】条件9: 早盘 MA5/MA10 回踩买入检测 (预埋单策略)
            # 早盘黄金窗口: 09:30-10:00，价格回踩均线附近是最佳买点
            # import datetime as dt
            now_time = dt.datetime.now()
            is_morning_window = 930 <= int(now_time.strftime('%H%M')) <= 1000
            
            ma5 = float(row.get("ma5d", 0))
            ma10 = float(row.get("ma10d", 0))
            
            if is_morning_window and ma5 > 0 and ma10 > 0 and price > nclose and structure != "派发":
                # MA5 回踩检测：价格在 MA5 ± 1% 区间
                ma5_bias = abs(price - ma5) / ma5
                if ma5_bias < 0.01:  # 距离 MA5 在 1% 以内
                    buy_score += 0.25
                    buy_reasons.append(f"早盘回踩MA5({ma5_bias:.1%})")
                    
                # MA10 回踩检测：价格在 MA10 ± 1.5% 区间
                ma10_bias = abs(price - ma10) / ma10
                if ma10_bias < 0.015:  # 距离 MA10 在 1.5% 以内
                    buy_score += 0.20
                    buy_reasons.append(f"早盘回踩MA10({ma10_bias:.1%})")
                    
                # 如果同时满足靠近 MA5 和 MA10，且价格在两者之间，是极佳买点
                if ma10 < price < ma5 and price > nclose:
                    buy_score += 0.15
                    buy_reasons.append("MA5/MA10夹板支撑")
            
            debug["实时买入分"] = buy_score
            debug["实时买入理由"] = buy_reasons
            
            # --- 动态阈值判定 ---
            threshold = 0.55
            
            # 进化: 叠加防御等级
            defense_level = float(debug.get("defense_level", 0.0))
            threshold += defense_level # 胜率越低，门槛越高 e.g. 0.55 + 0.2 = 0.75
            
            if not vwap_trend_ok:
                 threshold = max(threshold, 0.8) # 趋势不好时，至少需要 0.8
            
            # 触发条件
            if buy_score >= threshold:
                # 【新增】追高过滤：如果偏离 MA5 超过 3.5%，实时策略也不宜直接切入
                bias_ma5 = (price - float(row.get("ma5d", 0))) / float(row.get("ma5d", 1)) if float(row.get("ma5d", 0)) > 0 else 0
                if bias_ma5 > 0.035:
                    debug["realtime_skip"] = f"追高风险(MA5偏离{bias_ma5:.1%})"
                    return result

                pos = min(buy_score, self.max_position)
                
                # --- 信号迭代逻辑：跟单与加强 ---
                if snapshot.get("buy_triggered_today", False):
                    prev_score = float(snapshot.get("last_buy_score", 0))
                    msg_prefix = "[持续跟单]"
                    if buy_score > prev_score and volume > last_v1 * 0.5:
                        msg_prefix = "[跟单放量]"
                    buy_reasons.insert(0, msg_prefix)
                
                return {
                    "triggered": True,
                    "action": "买入",
                    "position": round(pos, 2),
                    "reason": "实时高走买入: " + ", ".join(buy_reasons),
                    "debug": debug
                }

        # ========== 2. 跌破均价卖出策略 (具备记忆与诱多识别) ==========
        if mode in ("full", "sell_only"):
            # A. 核心偏离检测
            deviation = (nclose - price) / nclose if nclose > 0 else 0
            # 动态阈值建议：昨涨 5% 容忍 1.5%，昨涨 10% 容忍 2.5% 左右的非典型波动
            max_normal_pullback = abs(last_percent) / 500 if abs(last_percent) < 10 else 0.02
            threshold = max(max_normal_pullback, 0.005) + 0.003

            if price < nclose and (deviation > threshold or snapshot.get("sell_triggered_today", False)):
                # 如果曾经破位且现在还没收回均线，持续报警
                already_broken = snapshot.get("sell_triggered_today", False)
                prefix = "[破位持续] " if already_broken else ""
                
                # 【优化逻辑】只有高开下杀带量且没返回均线的是核心卖点
                # 判断是否为“高开下杀放量”场景
                is_high_open = open_p > last_close * 1.02 # 高开 2%+
                is_heavy_vol = ratio > 5.0 or (snapshot.get('lastv1d', 0) > 0 and volume > snapshot['lastv1d'] * 0.8) # 换手大或成交量接近昨日 80%

                if is_high_open and is_heavy_vol:
                    # 这就是用户强调的：高开下杀放量且跌破均线 (致命信号)
                    sell_pos = 0.0 # 建议全清
                    return {
                        "triggered": True,
                        "action": "卖出",
                        "position": sell_pos,
                        "reason": f"高开下杀带量破位(泵高{pump_height:.1%}, 偏离{deviation:.1%})",
                        "debug": debug
                    }

                # 普通破位逻辑
                if morning_pump:
                    sell_multiplier = 1.0 + (pump_height * 10.0)
                    urgency = min(deviation / 0.02 * sell_multiplier, 1.0)
                    sell_pos = 1.0 - (1.0 - urgency) * 0.5
                    reason = f"{prefix}诱多后破位(泵高{pump_height:.1%}, 偏离{deviation:.1%})"
                else:
                    urgency = min(deviation / 0.03, 1.0)
                    sell_pos = 1.0 - urgency * 0.5
                    reason = f"{prefix}跌破均线 {deviation:.1%} (阈值{threshold:.1%})"
                
                return {
                    "triggered": True,
                    "action": "卖出",
                    "position": round(sell_pos, 2),
                    "reason": reason,
                    "debug": debug
                }
            
            # 修复逻辑：如果曾经破位，但现在稳稳站回均线 1%，可解除报警 (StockLiveStrategy 侧维护 snapshot)
            if snapshot.get("sell_triggered_today", False) and price > nclose * 1.01:
                debug["sell_memory_reset"] = True

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
            score -= 0.15 # 加大惩罚
            reasons.append("极低换手")
        
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
        
        debug["成交情绪分"] = score
        debug["成交情绪理由"] = reasons
        return score

    def _volume_price_signal(self, row: dict[str, Any], snapshot: dict[str, Any], mode: str, debug: dict[str, Any]) -> dict[str, Any]:
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
        result = {"triggered": False, "action": "持仓", "position": 0.0, "reason": "", "debug": debug}
        
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
        
        # 最近极大/极小成交量量比
        hvolume = float(snapshot.get("hvolume", 0))
        lvolume = float(snapshot.get("lvolume", 0))
        debug["hvolume"] = hvolume
        debug["lvolume"] = lvolume
        
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
            # 量比 < 0.6 认为是地量水平，或者接近历史纪录的地量
            is_current_low_vol = volume < 0.6 or (lvolume > 0 and volume <= lvolume * 1.1)
            
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
                # 昨日接近 30 日地量，或者接近纪录地量
                was_low_vol = (v1 <= llowvol * 1.3) or (lvolume > 0 and v1 <= lvolume * 1.2)
                # 今日开始温和放量（量比 > 1.25 且比昨日大）
                is_volume_up = volume > 1.25 and (v1 > 0 and volume > v1)
                # 价格上涨
                is_price_up = price > float(snapshot.get("last_close", 0)) * 1.005 if snapshot.get("last_close") else False
                
                if was_low_vol and is_volume_up and is_price_up:
                    buy_score += 0.35 # 稍微提高分值
                    signals.append(f"地量突破(量比{volume:.1f})")
            
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
                
                debug["均线差距%"] = ma_diff_pct * 100
                debug["均线平行"] = ma_is_parallel
            
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
            
            debug["量价买入分"] = buy_score
            debug["量价买入信号"] = signals
            
            if buy_score >= 0.3:
                result = {
                    "triggered": True,
                    "action": "买入",
                    "position": min(buy_score + 0.2, 0.8),
                    "reason": "量价买入: " + ", ".join(signals),
                    "debug": debug
                }
                logger.debug(f"量价买入触发: score={buy_score:.2f} signals={signals}")
                return result
        
        # ========== 卖出信号 ==========
        if mode in ("full", "sell_only"):
            sell_signals = []
            
            # 1. 天量高价：成交量异常放大 + 价格接近 3 日高点
            if volume > 0 and high_3d > 0:
                # 量比异常放大（> 3 倍），或者触及/超过最近最高量量比
                is_high_vol = volume > 3.0 or (hvolume > 0 and volume >= hvolume * 0.95)
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
            
            debug["量价卖出分"] = sell_score
            debug["量价卖出信号"] = sell_signals
            
            if sell_score >= 0.3:
                result = {
                    "triggered": True,
                    "action": "卖出",
                    "position": max(0.3, 1.0 - sell_score),
                    "reason": "量价卖出: " + ", ".join(sell_signals),
                    "debug": debug
                }
                logger.debug(f"量价卖出触发: score={sell_score:.2f} signals={sell_signals}")
                return result
        
        return result

    def _multiday_trend_score(self, source_data: dict[str, Any], debug: dict[str, Any]) -> float:
        """
        多日情绪趋势评分
        
        source_data: 可以是 row 或 snapshot
        
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
        price = float(source_data.get("trade", 0))
        
        # ---------- 1. 价格趋势分析（5日收盘价） ----------
        closes = []
        for i in range(1, 6):
            c = float(source_data.get(f"lastp{i}d", 0))
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
            
            # 【新增】5日线回补逻辑 (次日反包/收回均线)
            # 判断逻辑：昨日收盘 < 昨日MA5，但今日 (price) > 当前MA5 且 今日价格 > 昨日收盘
            last_close = float(source_data.get("last_close", 0))
            last_ma5 = float(source_data.get("lastma5d", 0))
            current_ma5 = float(source_data.get("ma5d", 0))
            if last_ma5 > 0 and last_close < last_ma5 and price > current_ma5 and price > last_close:
                # 配合成交量判断回补有效性
                score += 0.25 # 给予显著加分
                reasons.append("5日线回补")
                # 如果还站稳了均价线，信心更强 (在 _realtime_priority_check 中会进一步加分)
        
        # ---------- 2. 高低点趋势（5日最高/最低价） ----------
        highs = [float(source_data.get(f"lasth{i}d", 0)) for i in range(1, 6) if source_data.get(f"lasth{i}d", 0)]
        lows = [float(source_data.get(f"lastl{i}d", 0)) for i in range(1, 6) if source_data.get(f"lastl{i}d", 0)]
        
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
        macd = float(source_data.get("macd", 0))
        macd_dif = float(source_data.get("macddif", 0))
        macd_dea = float(source_data.get("macddea", 0))
        
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
            m = float(source_data.get(f"macdlast{i}", 0))
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
        kdj_j = float(source_data.get("kdj_j", 50))
        kdj_k = float(source_data.get("kdj_k", 50))
        kdj_d = float(source_data.get("kdj_d", 50))
        
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
        upper = float(source_data.get("upper", 0))
        lower = float(source_data.get("lower", 0))
        # price = float(source_data.get("trade", 0)) # Moved to top
        
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
        hmax = float(source_data.get("hmax", 0))
        high4 = float(source_data.get("high4", 0))
        max5 = float(source_data.get("max5", 0))
        current_high = float(source_data.get("high", 0))
        
        if hmax > 0 and current_high > hmax:
            score += 0.2
            reasons.append("突破历史高")
        elif max5 > 0 and current_high > max5:
            score += 0.1
            reasons.append("突破5日高")

        # ---------- 7. 连阳加速与五日线强度 (New) ----------
        win = int(source_data.get("win", 0))
        sum_perc = float(source_data.get("sum_perc", 0))
        red = int(source_data.get("red", 0))

        if win >= 2:
            # 强势惜售：高低点持续抬升
            win_score = min(win * 0.1, 0.4)
            score += win_score
            reasons.append(f"加速连阳({win}d)")
            
            # 惜售待变盘判断：如果连阳天数多但涨幅不大 (sum_perc / win < 3%)
            if win >= 3 and (sum_perc / win < 3.0):
                score += 0.15
                reasons.append("强势惜售")

        if red >= 3:
            # 长期站稳五日线，通常意味着强撑或主力控盘
            gren = int(source_data.get("gren", 0))
            net_strength = red - gren
            
            if red >= 5:
                # 连续5日以上红（站稳5日线），如果是窄幅震荡，则变盘概率大
                if abs(sum_perc) < 10: 
                    score += 0.2
                    reasons.append(f"中线走红({red}d)")
                else:
                    score += 0.1
                    reasons.append(f"站稳5日线({red}d)")
            
            # 趋势纯度加成：红多绿少代表趋势极为平滑
            if net_strength >= 6:
                score += 0.15
                reasons.append("极强趋势纯度")
            elif net_strength <= 0 and red > 0:
                score -= 0.1
                reasons.append("趋势震荡不稳")
        
        # 限制得分范围
        score = max(-1.0, min(1.0, score))
        
        debug["multiday_trend_score"] = score
        debug["multiday_trend_reasons"] = reasons
        return score

    def _hold(self, reason: str, debug: dict[str, Any], position: float = 0.0) -> dict[str, Any]:
        """返回持仓决策"""
        # logger.debug(f"Engine HOLD: {reason}")
        return {
            "action": "持仓",
            "position": position,
            "reason": reason,
            "debug": debug
        }


    def _is_price_limit(self, code: str, price: float, last_close: float, high: float, low: float, open_p: float, ratio: float, snapshot: dict[str, Any]) -> dict[str, bool]:
        """
        判断是否处于涨跌停状态，并识别一字板
        """
        if last_close <= 0:
            return {"limit_up": False, "limit_down": False, "one_word": False}
            
        # 涨停比例 (主板 10%, 创业/科创 20%, ST 5%)
        limit_ratio = 0.10
        if code.startswith(('30', '68')):
            limit_ratio = 0.20
        # 简单通过名称判断 ST
        if "ST" in snapshot.get("name", "").upper():
            limit_ratio = 0.05
            
        # 计算价格上限和下限 (考虑四舍五入偏差，增加 0.01 冗余)
        limit_up_price = round(last_close * (1 + limit_ratio), 2)
        limit_down_price = round(last_close * (1 - limit_ratio), 2)
        
        is_up = price >= limit_up_price - 0.005 # 兼容极小波动
        is_down = price <= limit_down_price + 0.005
        
        # 一字板判定：开盘=最高=最低=当前，且成交极小 (或振幅为0)
        is_one_word = False
        if is_up or is_down:
            # 振幅为 0 且成交换手极低
            if high == low == open_p == price:
                is_one_word = True
            elif ratio < 0.2 and high == low:
                 is_one_word = True
                
        return {"limit_up": is_up, "limit_down": is_down, "one_word": is_one_word}

    # ==================== 支撑位开仓策略 (New) ====================
    
    def _support_rebound_check(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> tuple[float, str]:
        """
        支撑位企稳检测
        
        检测价格是否回踩重要均线(MA20/MA60)或重要低点(Low10)并获得支撑
        
        Returns:
            (score, reason_str)
        """
        score = 0.0
        reasons = []
        
        price = float(row.get("trade", 0))
        if price <= 0:
            return 0.0, ""
            
        # 1. 均线支撑 (MA10/MA20/MA60)
        ma10 = float(row.get("ma10d", 0))
        ma20 = float(row.get("ma20d", 0))
        ma60 = float(row.get("ma60d", 0))
        
        # MA20: 趋势线 (俗称生命线)
        if ma20 > 0 and price > ma20:
            # 回踩幅度 < 1.0%
            if abs(price - ma20) / ma20 < 0.01:
                score += 0.20
                reasons.append(f"踩MA20趋势线")
        
        # MA60: 牛熊线 (强支撑)
        if ma60 > 0 and price > ma60:
            # 回踩幅度 < 1.5%
            if abs(price - ma60) / ma60 < 0.015:
                # 只有在趋势还未完全崩坏时才有效
                if price > ma60 * 1.05: # 之前涨过，现在回踩
                     pass 
                score += 0.25
                reasons.append(f"踩MA60牛熊线")
                
        # MA10: 短线支撑 (只在强趋势中有效)
        if ma10 > 0 and price > ma10:
             if abs(price - ma10) / ma10 < 0.008:
                 # 需结合多日趋势分
                 trend_score = debug.get("trend_strength", 0)
                 if trend_score > 0.3:
                     score += 0.15
                     reasons.append(f"踩MA10短线撑")

        # 2. 结构支撑 (前低/布林/缺口)
        low10 = float(snapshot.get("low10", 0))
        hmax = float(snapshot.get("hmax", 0)) # 近期高点
        lower = float(snapshot.get("lower", 0)) # 布林下轨
        
        # 10日低点支撑 (双底预期)
        if low10 > 0 and price >= low10:
            if (price - low10) / low10 < 0.015:
                score += 0.2
                reasons.append("10日双底支撑")

        # 平台突破后的回踩 (Price near Max5 or Hmax but still above)
        # 这里逻辑稍微复杂，暂且略过，重点在均线和低点
        
        # 布林下轨支撑 (超跌反弹)
        if lower > 0 and price <= lower * 1.01:
            score += 0.15
            reasons.append("布林下轨超跌")
            
        # 3. 辅助验证
        # 必须是非单边下跌 (Looking for stabilization)
        # 简单判断：当前价格 > 今日开盘价 (收阳) OR 下影线较长
        open_p = float(row.get("open", 0))
        low = float(row.get("low", 0))
        
        is_stable = False
        if open_p > 0:
            if price > open_p: # 阳线
                is_stable = True
            elif low > 0 and (price - low) / low > 0.005: # 长下影线 > 0.5%
                is_stable = True
                reasons.append("长下影企稳")
        
        if score > 0 and not is_stable:
             # 如果到了支撑位但还在阴跌，打折
             score *= 0.5
             reasons.append("(未企稳)")
        
        if score > 0:
            return score, "+".join(reasons)
            
        return 0.0, ""

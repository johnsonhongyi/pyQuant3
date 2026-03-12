# -*- coding: utf-8 -*-
"""
盘中决策引擎 - 增强版
支持买入/卖出信号生成、动态仓位计算、趋势强度评估、止损止盈检测
"""
from __future__ import annotations
import logging
import datetime as dt
from typing import Any
from daily_top_detector import detect_top_signals
import pandas as pd
from JohnsonUtil.commonTips import timed_ctx
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
        """
        debug: dict[str, Any] = {}
        # ---------- 基础字段预取与预处理 (Field Extraction & Preprocessing) ----------
        price = float(row.get("trade", 0))
        if price <= 0:
            return self._hold("价格无效", debug)
            
        high = float(row.get("high", price))
        low = float(row.get("low", price))
        open_p = float(row.get("open", price))
        ratio = float(row.get("volume_ratio", row.get("ratio", 0)))
        
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))
        ma20 = float(row.get("ma20d", 0))
        ma60 = float(row.get("ma60d", 0))
        
        nclose = float(row.get("nclose", snapshot.get("nclose", price)))
        last_close = float(snapshot.get("last_close", snapshot.get("lastp1d", 0)))
        
        # 调试信息基础
        debug.update({
            "nclose": nclose,
            "high_val": high,
            "trade": price,
            "ratio": ratio
        })
        
        # ---------- 基础行情分析 ----------
        # 1. 均线与结构分析
        if ma5 > 0 and ma10 > 0:
            structure = self._intraday_structure(price, high, open_p, ratio)
            trend_strength = self._trend_strength(row, debug)
        else:
            structure = "UNKNOWN"
            trend_strength = 0.0
            debug["analysis_skip"] = "均线数据无效"
            
        debug["structure"] = structure
        debug["trend_strength"] = trend_strength

        # ==============================================================================
        # 💥 [CRITICAL] P0 风控优先级：止损/止盈信号必须优先于所有其他逻辑
        # Fix: 在涨跌停过滤之前检查止损，避免 "跌停Hold" 覆盖 "止损EXIT" 的矛盾
        # ==============================================================================
        is_t1_restricted = False
        if snapshot.get('buy_date'):
            today_str = dt.datetime.now().strftime('%Y-%m-%d')
            if snapshot['buy_date'].startswith(today_str):
                is_t1_restricted = True
        
        # 仅在持有仓位且非T+1时执行优先止损检查
        if mode in ("full", "sell_only") and not is_t1_restricted:
            cost_price = float(snapshot.get("cost_price", 0))
            if cost_price > 0:  # 有持仓才检查止损
                early_stop_result = self._stop_check(row, snapshot, debug)
                if early_stop_result["triggered"]:
                    debug["early_stop_priority"] = True
                    return {
                        "action": early_stop_result["action"],
                        "position": early_stop_result["position"],
                        "reason": f"[风控优先] {early_stop_result['reason']}",
                        "debug": debug
                    }
        
        # 💥 [NEW] 提前进行顶部信号检测，供后续全局使用
        day_df = snapshot.get('day_df', pd.DataFrame())
        cache_dict = snapshot.setdefault('top_detector_cache', {})
        with timed_ctx("eval.0_top_detector"):
            top_info = detect_top_signals(day_df, row, cache_dict=cache_dict) # 传入 row 作为当前 tick
        debug["top_score"] = top_info['score']
        debug["top_signals"] = top_info['signals']
        
        # ==============================================================================
        # 💥 [NEW] P0.9 主升浪持仓保护与顶部信号拦截 (High Priority)
        # ==============================================================================
        with timed_ctx("eval.1_main_wave_hold"):
            hold_decision = self._main_wave_hold_check(row, snapshot, debug, top_info=top_info)
        if hold_decision:
            # 如果主升浪逻辑接管，直接返回
            return {
                "action": hold_decision["action"],
                "position": round(hold_decision["position"], 2),
                "reason": hold_decision["reason"],
                "debug": debug
            }
        
        # ---------- 策略进化：痛感与防御机制 (Pain & Defense) ----------
        # 0. 基础过滤：时间窗口与涨跌停 (Basic Filters)
        base_pos = 0.0
        # --- 时间窗口过滤 (Time window filter) ---
        time_penalty, time_msg = self._time_structure_filter(debug)
        if time_penalty < -0.5: # 严重不建议的时间点
            return self._hold(time_msg, debug)
        base_pos += time_penalty
        if time_msg:
            debug["时间窗口说明"] = time_msg

        # --- 涨停/跌停过滤 (Limit price filter) ---
        limit_refuse, limit_msg = self._limit_price_filter(row, debug)
        if limit_refuse:
            return self._hold(limit_msg, debug)

        # 💥 [New] 严格追高限制 (Anti-Chasing)
        # 如果日内涨幅超过 7%，且当前不是为了卖出，则坚决不追
        pct_now = float(row.get('percent', 0))
        if pct_now > 7.0 and mode != "sell_only":
            # 唯一的例外：如果有极强的题材或外部加分 (可配置)
            # 但为了安全起见，默认禁止
            debug["refuse_reason"] = f"涨幅{pct_now:.2f}%过高"
            return self._hold(f"禁止追高(>{pct_now:.1f}%)", debug)
        elif pct_now > 5.0 and mode != "sell_only":
            # 5-7% 之间，扣分惩罚
            base_pos -= 0.15
            debug["追高惩罚"] = -0.15

        # 1. 记仇机制 (PTSD)：如果这只票最近连续让你亏钱，就别碰它！
        streak_val = snapshot.get("loss_streak", 0)
        loss_streak = int(streak_val) if not pd.isna(streak_val) else 0
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

        # 3. 实时情绪感知 (Realtime Emotion & Pattern)
        # rt_emotion: 0-100, >60 偏强, <40 偏弱
        rt_emotion = float(snapshot.get("rt_emotion", 50))
        rt_bonus = 0.0
        if rt_emotion > 75:
            rt_bonus = 0.1
            debug["实时情绪加成"] = f"高涨({rt_emotion})"
        elif rt_emotion < 30:
            rt_bonus = -0.1
            debug["实时情绪扣分"] = f"低迷({rt_emotion})"
        
        # 4. V型反转信号 (V-Shape Reversal)
        v_shape_signal = bool(snapshot.get("v_shape_signal", False))
        v_shape_bonus = 0.0
        if v_shape_signal:
            v_shape_bonus = 0.15
            debug["形态加成"] = "V型反转"

        debug["rt_bonus"] = rt_bonus
        debug["v_shape_bonus"] = v_shape_bonus
        
        # 5. 55188 外部加分 (外部人气与资金流向)
        # 人气排名 (1-100), 主力排名 (1-100), 主力净占比%
        hr_val = snapshot.get('hot_rank', 999)
        hot_rank = int(hr_val) if not pd.isna(hr_val) else 999
        zr_val = snapshot.get('zhuli_rank', 999)
        zhuli_rank = int(zr_val) if not pd.isna(zr_val) else 999
        net_ratio_ext = float(snapshot.get('net_ratio_ext', 0))
        hot_tag = snapshot.get('hot_tag', "")
        
        popularity_bonus = 0.0
        if 1 <= hot_rank <= 20: popularity_bonus = 0.15
        elif 1 <= hot_rank <= 50: popularity_bonus = 0.10
        elif 1 <= hot_rank <= 100: popularity_bonus = 0.05
        
        capital_bonus = min(max(net_ratio_ext * 0.005, -0.1), 0.15) # 映射主力净占比到仓位加成
        if 1 <= zhuli_rank <= 100:
             capital_bonus += 0.05
             
        debug["popularity_bonus"] = popularity_bonus
        debug["capital_bonus"] = round(capital_bonus, 2)
        debug["hot_info"] = {"rank": hot_rank, "tag": hot_tag}
        debug["zhuli_info"] = {"rank": zhuli_rank, "ratio": net_ratio_ext}
        
        # 5.1 题材挖掘与板块持续性 (Concept Mining & Persistence)
        theme_name = snapshot.get('theme_name', "")
        theme_logic = snapshot.get('theme_logic', "")
        sector_score = float(snapshot.get('sector_score', 0.0))
        
        sector_bonus = 0.0
        if theme_name:
            # 基础加成 (只要有题材)
            sector_bonus = 0.05
            # 持续性加成 (倍率提升)
            sector_bonus += sector_score * 0.15 # 0 -> 0.15
            debug["题材名称"] = theme_name
            debug["题材逻辑"] = theme_logic[:30] + "..." if len(theme_logic) > 30 else theme_logic
        
        debug["sector_bonus"] = round(sector_bonus, 2)
        
        # ---------- 0. 选股分权重加成 (New: 对应 “反向验证” 需求) ----------
        # 根据 StockSelector 的评分增加基础权重，评分越高，买入信心越足
        selection_score = float(snapshot.get("score", 0))
        
        # [NEW] 引入前期矢量化预处理计算出的 `structure_base_score` 作为结构底分评估
        structure_base_score = float(snapshot.get("structure_base_score", 50.0))
        historical_signal = snapshot.get("last_signal", "HOLD") # 用于区分新开仓还是做T
        
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

        # --- 周期区域判断 (New: User Recommendation) ---
        self.cycle_stage = int(row.get('cycle_stage', 2)) # 默认主升
        debug["周期阶段"] = self.cycle_stage # 1:启动 2:主升 3:脉冲 4:回落
        
        # --- 1. 实时买入决策判定 ---
        if mode in ("full", "buy_only"):
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
        with timed_ctx("eval.2_sell_check"):
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
        with timed_ctx("eval.3_buy_check"):
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
                
                # --- 模式识别：加速股模式 & MA60 突破 (提前判断以支持升级) ---
                # [新增] MA60 突破 + Red > 5 加速模式
                ma60_result = self._check_ma60_red5_acceleration(row, snapshot, debug)
                if ma60_result["triggered"]:
                    if action == "持仓": 
                        action = "买入"
                    base_pos += ma60_result["bonus"]
                    ma_reason += f" | {ma60_result['reason']}"

                acc_result = self._check_acceleration_pattern(row, snapshot, debug)
                if acc_result["is_acc"]:
                    if action == "持仓": 
                        action = "买入"
                    base_pos += acc_result["bonus"]
                    ma_reason += f" | {acc_result['reason']}"

                debug["ma_decision"] = ma_reason

                if action == "持仓":
                    # [迭代优化] 虽然均线判定持仓，但如果是加速股，应该给予更强的正面理由
                    is_holding = float(snapshot.get("cost_price", 0)) > 0
                    if is_holding:
                        rv_val = snapshot.get('red', 0)
                        red_val = int(rv_val) if not pd.isna(rv_val) else 0
                        if red_val >= 5 and price > ma5:
                            ma_reason = f"加速延续(Red{red_val}) | {ma_reason}"
                    return self._hold(ma_reason, debug)
                
                if action == "买入":
                    # 💥 核心修正：结构性熔断机制 💥
                    # 如果盘中结构判定为"派发"(冲高大幅回落)，坚决禁止开仓，无论其他指标多好
                    if structure == "派发":
                        debug["refuse_buy"] = "结构为派发(冲高回落)"
                        return self._hold(f"结构{structure}禁买", debug)
                    
                    # (模式识别已移至上方)

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
                    
                    # 【新增】单阳惩罚 (One-Day Wonder Penalty)
                    # 统计发现 win=1 时买入胜率为 0%，需连续确认
                    wd_val = snapshot.get('win', 0)
                    win_days = int(wd_val) if not pd.isna(wd_val) else 0
                    if win_days == 1:
                        base_pos -= 0.15
                        debug["单阳惩罚"] = -0.15
                    
                    # 3. 量能与均价约束 (关键点)
                    # 【新增】量能模糊区间惩罚
                    # 统计发现 volume 在 0.8-1.2 之间胜率仅 18%
                    current_vol = float(row.get('volume', 0))
                    if 0.8 <= current_vol <= 1.2:
                        base_pos -= 0.10
                        debug["量能模糊"] = -0.10
                        
                    base_pos += self._volume_bonus(row, debug)
                    
                    # --- 进化: 应用防御惩罚 ---
                    base_pos -= defense_level
                    if "PTSD扣分" in debug:
                        base_pos += debug["PTSD扣分"] # 这是一个负数
                    
                    # 4. 选股分加成
                    base_pos += selection_bonus
                    
                    # [NEW] 结构预处理分加成 (Structure Base Score Bonus)
                    if structure_base_score >= 75:
                        base_pos += 0.15
                        debug["结构加成"] = f"强底分({structure_base_score})"
                    elif structure_base_score <= 40:
                        base_pos -= 0.15
                        debug["结构惩罚"] = f"弱底分({structure_base_score})"
                        
                    # [NEW] 信号延续：如果历史信号是买入，今天触发则是追加做T买点，稍微放宽或增加权重
                    if historical_signal in ("BUY", "买入", "1", 1) and structure_base_score > 50:
                        base_pos += 0.1
                        debug["做T加持"] = "前日买点延续"
                    
                    # 5. 支撑位得分加成 & 实时信号加成
                    if support_score > 0:
                        base_pos += support_score
                        debug["支撑加成"] = support_score
                    
                    # 注入实时信号加成
                    base_pos += rt_bonus
                    base_pos += v_shape_bonus
                    
                    # 注入 55188 外部信号加成
                    base_pos += popularity_bonus
                    base_pos += capital_bonus
                    base_pos += sector_bonus
                    
                    # 如果价格在今日今日成交均价（nclose）下方，【硬性拒绝】买入
                    # User Rule: 不允许任何低于分时均线（VWAP）的买入
                    if nclose > 0 and price < nclose:
                        # 例外：极强的支撑位抄底(score>0.25)且偏离均价极近(<0.5%)，由于是左侧交易，允许在均价线下波动
                        if support_score > 0.25 and (nclose - price)/nclose < 0.005:
                              debug["均价约束"] = "支撑位极近豁免"
                        else:
                            return self._hold(f"低于分时均线(VWAP:{nclose:.2f})禁买", debug)
                        
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

                    # --- [新增] 智能加仓逻辑 (Smart Positioning) ---
                    # 如果当前已经是持仓状态，则判定是否符合加仓条件
                    is_holding = float(snapshot.get("cost_price", 0)) > 0
                    if is_holding:
                        # [迭代优化] 用户需求：如果保持加速状态且红柱高位，继续持仓甚至加仓
                        rv2_val = snapshot.get('red', 0)
                        red_val = int(rv2_val) if not pd.isna(rv2_val) else 0
                        wv2_val = snapshot.get('win', 0)
                        win_val = int(wv2_val) if not pd.isna(wv2_val) else 0
                        if red_val >= 5 and price > ma5 and win_val >= 2:
                            debug["迭代持仓"] = f"Red{red_val}加速延续"
                            # 如果评分本身很高，允许维持高分，这样就不会触发卖出/减仓
                            base_pos = max(base_pos, 0.45) 
                        
                        add_pos_decision = self._check_add_position(row, snapshot, debug)
                        if not add_pos_decision["allow"]:
                            # 如果不是为了持仓，而是为了新买入/加仓，则受限于 add_pos_decision
                            # 但如果是为了维持"持仓"，我们这里已经在 evaluate 流程中了
                            pass 
                        else:
                            debug["加仓信号"] = "符合条件"

                    # ==============================================================================
                    # 💥 最终门槛大幅提高 (根据回测，得分 < 0.3 胜率极低)
                    # MIN_BUY_SCORE 从隐性 ~0.3 提升至显性 0.40
                    # ==============================================================================
                    debug["实时买入分"] = round(base_pos, 2)
                    
                    if base_pos < 0.40:  # Hard Threshold
                        return self._hold(f"评分不足({base_pos:.2f}<0.4)", debug)

                    final_pos = max(min(base_pos, self.max_position * 1.2), 0)
                    # Double check to ensure non-zero if we passed the threshold (though logically 0.4 > 0)
                    if final_pos <= 0:
                         return self._hold("仓位由风控限制为0", debug)

                    reason = f"{structure} | {ma_reason} | 得分{base_pos:.2f}"
                    if is_holding: reason = "[加仓] " + reason
                    logger.info(f"DecisionEngine {'ADD' if is_holding else 'BUY'} pos={final_pos:.2f} reason={reason}")

                    return {
                        "action": "买入",
                        "position": round(final_pos, 2),
                        "reason": reason,
                        "debug": debug
                    }

        return self._hold("无有效信号", debug)

    def evaluate_dynamic(self, base_eval: dict, row: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
            """
            动态卖出信号计算，只针对 tick 变化字段
            保留基础 evaluate 的 debug 与基础计算结果，避免重复计算均线、选股加成等
            """
            debug = base_eval.get("debug", {}).copy()

            price = float(row.get("trade", 0))
            if price <= 0:
                return {"action": "持仓", "reason": "价格无效", "debug": debug}

            high = float(row.get("high", price))
            low = float(row.get("low", price))
            nclose = float(row.get("nclose", snapshot.get("nclose", price)))
            pct_now = float(row.get("percent", 0))

            # 更新 snapshot 高低点
            snapshot["highest_today"] = max(snapshot.get("highest_today", price), high)
            snapshot["highest_since_buy"] = max(snapshot.get("highest_since_buy", price), high)
            snapshot["low_val"] = min(snapshot.get("low_val", price), low)

            debug["trade"] = price
            debug["high_val"] = high
            debug["low_val"] = low
            debug["percent"] = pct_now
            debug["nclose"] = nclose

            # ---------- 高优先级止损/止盈 ----------
            stop_result = self._stop_check(row, snapshot, debug)
            if stop_result["triggered"]:
                return {
                    "action": stop_result["action"],
                    "position": stop_result.get("position", 0),
                    "reason": f"[动态止损] {stop_result['reason']}",
                    "debug": debug
                }

            # ---------- 涨跌停过滤 ----------
            last_close = float(snapshot.get("last_close", 0))
            limit_info = self._is_price_limit(row.get("code", ""), price, last_close, high, low, row.get("open", price), row.get("ratio", 0), snapshot)
            debug.update(limit_info)

            if limit_info.get("limit_up", False):
                return {"action": "持仓", "reason": "一字涨停/封涨停动态持仓", "debug": debug}
            if limit_info.get("limit_down", False):
                return {"action": "持仓", "reason": "跌停，信号无效", "debug": debug}

            # ---------- 高位/趋势卖出逻辑 ----------
            # 复用 base_eval 中的 top_signals/top_score

            # 从 base_eval debug 中获取 top_info，保证 score 和 signals 都存在

            top_info_base = base_eval.get("debug", {})
            top_info = {
                "score": top_info_base.get("score", 0.0),
                "signals": top_info_base.get("signals", [])
            }

            hold_decision = self._main_wave_hold_check(row, snapshot, debug, top_info=top_info)

            if hold_decision:
                return {
                    "action": hold_decision["action"],
                    "position": round(hold_decision.get("position", 0), 2),
                    "reason": f"[动态主升浪保护] {hold_decision['reason']}",
                    "debug": debug
                }

            # ---------- 实时高优先级决策 ----------
            is_t1_restricted = False
            if snapshot.get('buy_date'):
                today_str = dt.datetime.now().strftime('%Y-%m-%d')
                if snapshot['buy_date'].startswith(today_str):
                    is_t1_restricted = True
            # ---------- 实时优先卖出 ----------
            priority_result = self._realtime_priority_check(row, snapshot, mode="sell_only", debug=debug, _is_t1_restricted=is_t1_restricted)
            if priority_result["triggered"]:
                return priority_result

            # ---------- 常规卖出判断 ----------
            sell_action, sell_pos, sell_reason = self._sell_decision(
                price,
                snapshot.get('ma5d', 0),
                snapshot.get('ma10d', 0),
                snapshot,
                snapshot.get('structure', 'UNKNOWN'),
                debug
            )
            if sell_action == "卖出":
                debug["sell_reason"] = sell_reason
                return {"action": "卖出", "position": sell_pos, "reason": sell_reason, "debug": debug}

            # 默认持仓
            return {"action": "持仓", "reason": "无动态卖出触发", "debug": debug}

    # ==================== 卖出信号 ====================
    
    def _sell_decision(self, price: float, ma5: float, ma10: float, 
                       snapshot: dict[str, Any], structure: str, debug: dict[str, Any]) -> tuple[str, float, str]:
        """
        卖出信号判定 (精准版)
        
        核心理念：卖出和买入一样，需要多维度信号共振，而非单一条件即触发。
        优先在局部高点（反弹高位）卖出，而非在低点全量抛售。
        
        三大支柱 (Pillars):
          P1 - 趋势压力 (Trend Pressure): 均线/乖离/结构
          P2 - 量价背离 (Volume-Price Divergence): 量能衰竭
          P3 - 价格行为 (Price Action): 冲高回落/二次顶

        规则：需要至少两个支柱同时触发，且得分 >= 0.65 才卖出。
        """
        sell_score = 0.0
        pillar_hits: list[str] = []  # 记录哪些支柱被触发
        reasons: list[str] = []

        last_close = float(snapshot.get("last_close", 0))
        nclose = float(debug.get("nclose", snapshot.get("nclose", 0)))
        high = float(debug.get("high_val", 0))
        if high <= 0:
            high = price
        highest_today = float(snapshot.get('highest_today', high))
        volume = float(debug.get("volume_ratio", snapshot.get("volume", 1.0)))

        # ================================================================
        # 💡 最优卖点前置条件：价格必须在局部相对高位才值得卖出
        # "不是无脑卖，卖也尽量最优的卖点尽量高"
        # 如果价格已经跌到远离当日高点，说明最优卖点已过，现在触发只是追杀
        # 这种情况由 _stop_check 处理，不在这里触发主动卖出
        # ================================================================
        if highest_today > 0:
            distance_from_high = (highest_today - price) / highest_today
            # 移除 4% 跌幅限制：结构破坏在下跌多少时都应该触发卖出
            pass
        
        # ================================================================
        # 支柱 1 (P1): 趋势压力
        # - 严重乖离 (远高于均线，获利了结时机)
        # - 均线下穿结构
        # - 派发/走弱形态
        # ================================================================
        p1_score = 0.0
        if price > ma5 * 1.07:  # 乖离超过 7%，高位卖出时机
            p1_score += 0.35
            if ma5 <= 0:
                raise ValueError(f"MA5无效，数据异常! price={price}, row={ma5} snapshot={snapshot}")
            reasons.append(f"乖离过大({(price/ma5-1):.1%})")
        elif price > ma5 * 1.04:  # 乖离 4-7%
            p1_score += 0.15
            reasons.append("中度乖离")
            
        if price < ma10:
            p1_score += 0.20
            reasons.append("跌破MA10")

        if structure in ["派发", "走弱"]:
            p1_score += 0.25
            reasons.append(f"结构{structure}")
        elif structure == "中性" and nclose > 0 and price < nclose * 0.995:
            p1_score += 0.10  # 中性结构但均价线下方
            
        if p1_score >= 0.25:
            pillar_hits.append("趋势压力")
            sell_score += p1_score

        # ================================================================
        # 支柱 2 (P2): 量价背离
        # - 均价线显著下移
        # - 绿盘配合均价线压制
        # - 冲高回落但量能萎缩
        # ================================================================
        p2_score = 0.0
        vwap_trend_score = float(debug.get("VWAP趋势分", 0))  # 从 debug 中复用已算好的分数

        if nclose > 0 and price < nclose * 0.985:
            p2_score += 0.30
            reasons.append("深入均价线下方")
        elif nclose > 0 and price < nclose:
            # 均价线下方 + 量能是否异常
            if volume < 0.6:
                p2_score += 0.20
                reasons.append("均价下且缩量")
            else:
                p2_score += 0.10

        percent = float(snapshot.get('percent', 0.0))
        if percent < -1.5 and price < nclose:
            p2_score += 0.25
            reasons.append(f"绿盘({percent:.1f}%)且均价压制")
            
        # 急速冲高后量能骤减 (冲高时放量,下跌时缩量 → 主力减持迹象)
        pump_height = float(snapshot.get('pump_height', 0))
        pullback_depth = float(snapshot.get('pullback_depth', 0))
        if pump_height > 0.025 and pullback_depth > 0.02 and volume < 0.8:
            p2_score += 0.30
            reasons.append(f"冲高回落量能萎缩(↑{pump_height:.1%}↓{pullback_depth:.1%})")

        if p2_score >= 0.20:
            pillar_hits.append("量价背离")
            sell_score += p2_score

        # ================================================================
        # 支柱 3 (P3): 价格行为 (局部顶部特征)
        # - 高点下移（二次及以上冲高均低于前高）
        # - 昨收破位
        # - 当日最低价平台破位
        # ================================================================
        p3_score = 0.0
        highest_since_buy = float(snapshot.get('highest_since_buy', high))
        
        # 二次冲高失败（最优卖点：反弹到相对高点但仍低于前高）
        if highest_today > 0 and high < highest_today * 0.985 and price < nclose:
            p3_score += 0.25
            reasons.append("日内二次冲高失败")
        
        # 持有高点下移（买入后每次反弹都更低）
        if highest_since_buy > 0 and high < highest_since_buy * 0.98 and nclose > 0 and price < nclose:
            p3_score += 0.30
            reasons.append(f"反弹高点持续下移")

        # 跌破昨收触发加权
        if last_close > 0 and price < last_close * 0.97:
            p3_score += 0.20
            reasons.append(f"跌破昨收({last_close:.2f})")
            
        # 当日破位主杀
        low_val = float(debug.get("low_val", snapshot.get("low_val", 0)))
        if price < last_close * 0.97 and low_val > 0 and price <= low_val * 1.01:
            p3_score += 0.15
            reasons.append("日内破位主杀")

        if p3_score >= 0.25:
            pillar_hits.append("价格行为")
            sell_score += p3_score

        # ================================================================
        # 特殊豁免：连阳强势持仓保护
        # 如果是强势连阳且结构未走坏，扣减评分、保护仓位
        # ================================================================
        multiday_score = self._multiday_trend_score(snapshot, debug)
        if multiday_score > 0.3 and structure not in ["派发", "走弱"]:
            sell_score -= 0.20
            debug["持仓保护"] = "连阳护航"
            reasons.append("⚠️ 连阳持仓保护")

        debug["sell_score"] = round(sell_score, 2)
        debug["sell_pillars"] = pillar_hits
        debug["sell_reasons"] = reasons
        
        # 触发条件：需两个独立支柱 + 总分 >= 0.65（派发结构降低），追杀式（仅靠分数但无支柱）门槛拒绝
        n_pillars = len(pillar_hits)
        threshold = 0.50 if structure == "派发" else 0.65
        
        if n_pillars >= 2 and sell_score >= threshold:
            return ("卖出", -max(sell_score, 0.5), " | ".join(p for p in reasons if "⚠️" not in p))
        elif structure == "派发" and sell_score >= 0.45 and n_pillars >= 1:
            # 派发结构：单支柱豁免，门槛低
            return ("卖出", -0.5, " | ".join(p for p in reasons if "⚠️" not in p))
        
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
        
        # --- [New] 🚨 提前预警与主动防守 (Early Detection Sell Logic) 🚨 ---
        # 目标：在达到 2.5% 的硬性预警前，通过结构、均线、流动性特征提前识别风险。
        vwap_trend_score = self._vwap_trend_check(row, snapshot, debug)
        structure = debug.get("structure", "UNKNOWN")
        
        # A. 均线下移严重 (VWAP Downtrend) + 破位
        if vwap_trend_score < -0.3 and price < nclose and pnl_pct < -0.01:
            return {"triggered": True, "action": "主动防守", "position": 0.3, "reason": f"均线下移明显且亏损{abs(pnl_pct):.1%}"}
            
        # B. 反弹无力与拒绝 (Failed Rebounds)
        # 记录的日内高点
        highest_today = float(snapshot.get('highest_today', high))
        highest_since_buy = float(snapshot.get('highest_since_buy', high))
        
        if nclose > 0 and price < nclose:
            # 高点下移 (Lower Highs): 日内最高点无法突破，且当前价又跌回均线之下
            if highest_since_buy > 0 and high < highest_since_buy * 0.985 and pnl_pct < -0.015:
                # 已经是第二次/第三次冲高失败
                return {"triggered": True, "action": "主动减仓", "position": 0.4, "reason": f"高点下移反弹无力,亏损{abs(pnl_pct):.1%}"}
                
            # 强拒绝 (Strong Rejection): 反弹触及均价线附近即被打回
            distance_to_vwap = (nclose - high) / nclose
            if 0 < distance_to_vwap < 0.005 and (high - price) / high > 0.015 and pnl_pct < -0.01:
                return {"triggered": True, "action": "主动防守", "position": 0.3, "reason": "触及均线受阻回落(强拒绝)"}
                
            # 极弱反弹 (Weak Rejection): 远离均线的小幅反弹，随后继续下跌
            if distance_to_vwap > 0.015 and (high - price) / high > 0.01 and volume < 0.6 and pnl_pct < -0.015:
                # 缩量且离均线很远的反弹失败
                return {"triggered": True, "action": "极弱止损", "position": 0.2, "reason": "远端弱势反弹失败伴随缩量"}
                
        # C. 流动性衰竭 (Liquidity Drain)
        # 连续上涨后量能不足导致的阴跌
        if structure == "派发" and volume < 0.5 and pnl_pct < -0.015:
             return {"triggered": True, "action": "流动性预警", "position": 0.4, "reason": "派发结构伴随量能枯竭"}

        # 2. 传统预警止损 (-2.5%)
        if pnl_pct < -0.025: # 预警止损收紧到 2.5%
            # 检查是否有反弹无力迹象（低于均价）或结构走弱
            if (nclose > 0 and price < nclose) or structure in ["派发", "走弱"]:
                # 如果是派发，直接全清，不再减半
                target_pos = 0.0 if structure == "派发" else 0.4
                return {"triggered": True, "action": "预警止损", "position": target_pos, "reason": f"结构{structure}且亏损{abs(pnl_pct):.1%}"}

        # --- 每日中轴趋势止损 (Daily Midline Stop-Loss) ---
        # 依赖于 StockLiveStrategy 注入的 snapshot 数据
        mid_rising = snapshot.get('midline_rising', False)
        mid_falling = snapshot.get('midline_falling', False)
        
        # 3. 趋势止损：中轴连跌且今日价格在均价之下 (Weakening Trend)
        if mid_falling and price < nclose and pnl_pct < -0.015:
            return {"triggered": True, "action": "趋势止损", "position": 0.3, "reason": "日线中轴重心下移且弱于均价"}

        # 4. 也是趋势止损：如果中轴没有上升，且今日高开低走(或冲高回落)跌破均价
        if not mid_rising:
             # 检查是否大幅回撤
             if high > 0 and (high - price) / high > 0.02 and price < nclose:
                 return {"triggered": True, "action": "回撤止损", "position": 0.3, "reason": "中轴未升+日内冲高回落破均价"}

        # 3. 均值回归止损 (Mean Reversion Stop)
        # 低开低走，且被均线压制，且中轴下移 -> 极弱，不做反弹幻想
        if mid_falling:
            open_p = float(row.get("open", 0))
            ma5 = float(row.get("ma5d", 0))
            if open_p > 0 and price < open_p and ma5 > 0 and price < ma5:
                 return {"triggered": True, "action": "极弱止损", "position": 0.0, "reason": "极弱形态(中轴降+被均线压制)"}


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
    
    def _trend_strength(self, row: dict[str, Any], debug: dict[str, Any]) -> float:
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
    
    def _volume_bonus(self, row: dict[str, Any], debug: dict[str, Any]) -> float:
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
    
    def _time_structure_filter(self, debug: dict[str, Any]) -> tuple[float, str]:
        """
        根据交易时间段应用结构性加成或惩罚
        用户反馈：9:20-9:45 相对低位, 10:00-11:00 短期高点, 下午需稳在均线上
        """
        now = dt.datetime.now().time()
        curr_min = now.hour * 60 + now.minute
        
        # 9:30-9:45 (570-585)
        if 570 <= curr_min <= 585:
            return 0.05, "开盘低位择机区"
        
        # 10:00-11:00 (600-660)
        if 600 <= curr_min <= 660:
            return -0.15, "早盘高位风险区(慎追)"
        
        # 14:50-15:00 (890-900) -> 尾盘禁买一刀切
        if 890 <= curr_min <= 900:
            return -1.0, "尾盘禁买(14:50后)"

        # 14:30-14:50 (870-890) -> 风险区
        if 870 <= curr_min < 890:
            return -0.20, "尾盘风险区(慎开)"
            
        return 0, ""

    def _limit_price_filter(self, row: dict[str, Any], debug: dict[str, Any]) -> tuple[bool, str]:
        """
        价格限制过滤器：防止在涨停板或跌停板错误交易
        """
        percent = float(row.get('percent', 0))
        # 涨停板判定 (通常 > 9.8% 且买一量大)
        if percent > 9.85:
            return True, "涨停板禁止追高"
        
        # 跌停板判定
        if percent < -9.85:
            return True, "跌停板禁止抄底"
            
        return False, ""

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

    def _yesterday_anchor(self, price: float, snapshot: dict[str, Any], debug: dict[str, Any]) -> float:
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

    def _structure_filter(self, row: dict[str, Any], debug: dict[str, Any]) -> float:
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

    def _extreme_filter(self, row: dict[str, Any], debug: dict[str, Any]) -> float:
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

    def _check_ma60_red5_acceleration(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> dict[str, Any]:
        """
        检查 MA60 突破 + Red > 5 加速模式
        逻辑：
        1. 价格站在 MA60 之上 (或刚突破)
        2. 站稳 5 日线已经 5 天以上 (red > 5)
        3. 沿着 5 日线加速 (price > ma5, win >= 2, vwap 趋势向上)
        """
        price = float(row.get("trade", 0))
        ma60 = float(row.get("ma60d", 0))
        ma5 = float(row.get("ma5d", 0))
        rv3_val = snapshot.get("red", 0)
        red = int(rv3_val) if not pd.isna(rv3_val) else 0
        wv3_val = snapshot.get("win", 0)
        win = int(wv3_val) if not pd.isna(wv3_val) else 0
        nclose = float(debug.get("nclose", snapshot.get("nclose", 0)))
        
        result = {"triggered": False, "bonus": 0.0, "reason": ""}
        
        if price <= 0 or ma60 <= 0 or ma5 <= 0:
            return result
            
        # 基础条件：站住 MA60 且 Red > 5
        if price > ma60 and red >= 5:
            # 加速条件：价格在 MA5 之上，且今日均价线向上，且连阳
            if price > ma5 and price >= nclose and win >= 2:
                result["triggered"] = True
                result["bonus"] = 0.35 # 给予较大的权重
                result["reason"] = f"MA60突破加速(Red{red},Win{win})"
                
                # 如果刚突破 MA60 (比如价格离 MA60 很近)，额外加分
                if (price - ma60) / ma60 < 0.03:
                    result["bonus"] += 0.1
                    result["reason"] += "+刚逾MA60"
                    
        return result

    def _check_acceleration_pattern(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> dict[str, Any]:
        """
        检查“加速股”模式：
        1. 回踩 5/10/20 日线后重新放量向上加速
        2. 收盘于布林上轨 (upper) 2-4% 处且昨日也是高分的次日模式
        """
        price = float(row.get("trade", 0))
        ma5 = float(row.get("ma5d", 0))
        ma10 = float(row.get("ma10d", 0))
        ma20 = float(row.get("ma20d", 0))
        volume = float(row.get("volume", 0))
        ratio = float(row.get("ratio", 0))
        nclose = float(debug.get("nclose", snapshot.get("nclose", 0)))
        
        result = {"is_acc": False, "bonus": 0.0, "reason": ""}
        
        if price <= 0 or ma5 <= 0:
            return result
            
        # 模式1: 回踩均线后加速 (典型强庄股二次启动)
        # 条件：过去2日有过回探，今日价格 > ma5 且价格 > nclose 且量能比 > 1.2
        last_l1 = float(snapshot.get("lastl1d", 0))
        if last_l1 > 0 and last_l1 < ma5 * 1.01 and price > ma5 * 1.01 and price > nclose and volume > 1.25:
             result["is_acc"] = True
             result["bonus"] += 0.15
             result["reason"] = "回踩5日线加速"
        
        # 模式2: 布林上轨偏离加速 (加速段特征)
        uppers = [snapshot.get(f'upper{i}', 0) for i in range(1, 6)]
        up4 = uppers[3] # upper4
        if up4 > 0:
            up_bias = (price - up4) / up4
            # 强势加速区：处于上轨上方 2%-5% 且带量站稳
            if 0.02 <= up_bias <= 0.05 and price > nclose and ratio > 4:
                result["is_acc"] = True
                result["bonus"] += 0.2
                result["reason"] += " | 上轨偏离加速" if result["reason"] else "上轨偏离加速"
        
        # 模式3: 极致力度(成交量爆炸)加速 (Quantified Volume Acceleration)
        # 逻辑：量比 > 2.0 (倍量) + 涨幅 > 3% + 站稳均价线 + 位于5日线上方
        pct = (price - float(snapshot.get('last_close', 0))) / float(snapshot.get('last_close', 1))
        if volume > 2.0 and pct > 0.03 and price > nclose and price > ma5:
             result["is_acc"] = True
             result["bonus"] += 0.25
             result["reason"] += " | 倍量暴力加速" if result["reason"] else "倍量暴力加速"

        # 模式4: 主升浪结构加速 (Main Wave Acceleration)
        # 逻辑: 股价 > Upper线 (站上上轨) 且昨日涨幅 > 0 (连阳延续)
        # User defined: "站上upper开始都是加速结构"
        upper = float(snapshot.get('upper', 0)) # 今日布林上轨
        if upper > 0 and price > upper and pct > 0.0:
             result["is_acc"] = True
             result["bonus"] += 0.30
             result["reason"] += " | 站上Upper加速" if result["reason"] else "站上Upper加速"
        
        return result

    def _vwap_trend_check(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> float:
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
            # 这里简化为：如果重心上移幅度超过 1.5%，确认为趋势爆发
            if current_nclose > last_nclose * 1.015:
                score += 0.1
                debug["VWAP趋势"] += "|爆发"

        return score

    # ==================== 实时行情高优先级决策 ====================
    
    def _realtime_priority_check(self, row: dict[str, Any], snapshot: dict[str, Any], mode: str, debug: dict[str, Any], _is_t1_restricted: bool = False) -> dict[str, Any]:
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

        
        # 数据有效性检查
        if price <= 0 or open_p <= 0 or last_close <= 0:
            debug["realtime_skip"] = "数据无效"
        # 数据有效性检查
        if price <= 0 or open_p <= 0 or last_close <= 0:
            debug["realtime_skip"] = "数据无效"
            return result

        # ========== Priority 0. V型反转直接介入 Check ==========
        # 如果出现 V型反转信号，且当前不是下跌趋势(MACD>0 或 价格>均价)，立即买入
        if snapshot.get("v_shape_signal", False):
            # 简单趋势过滤：均价必须上移 且 价格 > 均价
            if vwap_trend_ok and price > nclose:
                 return {
                    "triggered": True,
                    "action": "买入",
                    "position": 0.4, # 初始仓位不错
                    "reason": "V型反转确立+趋势向上",
                    "debug": debug
                }

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
            if gap_up > 0.05: # 极端高开，必须有巨量支撑 (Moni-trap prevention)
                if ratio > 12 or volume > last_v1 * 0.4:
                    buy_score += 0.4
                    buy_reasons.append(f"强力高开({gap_up:.1%})且放量")
                else:
                    buy_score -= 0.2
                    debug["refuse_reason"] = f"高开无量({gap_up:.1%}, ratio={ratio:.1f})"
            elif gap_up > 0.01:  # 提高到 1.0% 以上才算有效高开
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
            
            # [NEW] 融合结构预处理分 (structure_base_score)
            structure_base_score = float(snapshot.get("structure_base_score", 50.0))
            if structure_base_score >= 75:
                 buy_score += 0.2
                 buy_reasons.append(f"强底分({structure_base_score})")
            elif structure_base_score <= 40:
                 buy_score -= 0.2
                 buy_reasons.append(f"弱底分({structure_base_score})")
                 
            # [NEW] 判断是否是顺势做T
            historical_signal = snapshot.get("last_signal", "HOLD")
            if historical_signal in ("BUY", "买入", "1", 1) and structure_base_score > 50:
                 buy_score += 0.15
                 buy_reasons.append("做T加持")
                 
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
            # Move definitions up to support Cond 9
            wv5_val = snapshot.get("win", 0)
            win = int(wv5_val) if not pd.isna(wv5_val) else 0
            sum_perc = float(snapshot.get("sum_perc", 0))
            rv5_val = snapshot.get("red", 0)
            red = int(rv5_val) if not pd.isna(rv5_val) else 0

            # [新增] 条件9: 主升浪加速启动 (Opening Low-High Acceleration)
            # 用户痛点：开盘5分钟最低走高，随后加速封板，容易丢失
            # 特征：低开或平开(gap<1%) -> 开盘即最低 -> 快速拉升 -> 量能配合
            is_main_wave_candidate = (win >= 2 or red >= 5)
            open_near_low = (low > 0 and (open_p - low)/open_p < 0.005) # 开盘即最低
            rapid_pull_up = (price > open_p * 1.025) # 快速拉升 > 2.5%
            
            if is_main_wave_candidate and open_near_low and rapid_pull_up:
                # 进一步检查量能：必须有量才能确认是加速
                # 1. 换手率达标(>1.0% in early) OR 2. 量比放大(>1.5)
                vol_confirmed = (ratio > 0.8) or (volume > 1.5)
                
                if vol_confirmed and price > nclose:
                    acc_score = 0.35
                    acc_msg = "主升加速(开盘最低走高)"
                    
                    # 如果是低开拉起，含金量更高 (洗盘结束)
                    if open_p < last_close:
                        acc_score += 0.1
                        acc_msg += "[低开金身]"
                    
                    buy_score += acc_score
                    buy_reasons.append(acc_msg)

            # (Conditions for Cond 8 continue below using already defined win/red/sum_perc)
            
            # [New] 中轴线趋势加成
            mid_rising = snapshot.get('midline_rising', False)
            mid_falling = snapshot.get('midline_falling', False)
            
            if mid_rising:
                buy_score += 0.1
                buy_reasons.append("中轴重心上移")
            elif mid_falling:
                # 除非是超跌反弹，否则中轴下移要扣分
                if not is_oversold:
                    buy_score -= 0.15
                    buy_reasons.append("中轴重心下移")

            # 情况 A: 强势惜售后的加速 (win >= 3，小幅连阳后爆发)
            if win >= 3 and (sum_perc / win < 3.5):
                # 盘中表现：突破分时均价且已经产生一定涨幅
                if price > nclose and (price - last_close) / last_close > 0.01:
                    buy_score += 0.25
                    buy_reasons.append(f"惜售连阳({win}d)加速")

            # 情况 B: 中线走红后的变盘突破 (red >= 5，站稳5日线后横盘爆发)
            gv_val = snapshot.get("gren", 0)
            gren = int(gv_val) if not pd.isna(gv_val) else 0
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
            last_high = float(snapshot.get("last_high", 0))
            
            yesterday_pattern = str(snapshot.get("pattern", "")).lower()
            is_stabilized_target = "stabilization" in yesterday_pattern or "rising_structure" in yesterday_pattern or "企稳" in yesterday_pattern
            is_ma60_reversal = "ma60_reversal" in yesterday_pattern
            
            if is_morning_window and ma5 > 0 and structure != "派发":
                # [Optimization] Lowest Price Entry for Stabilized Targets
                if is_stabilized_target:
                    # 企稳结构股：等待回踩昨日高点或MA5
                    # 只要价格在 [last_high*0.995, last_high*1.01] 或 [ma5*0.995, ma5*1.01] 范围内
                    hit_ma5 = abs(price - ma5) / ma5 < 0.01
                    hit_prev_high = abs(price - last_high) / last_high < 0.01 if last_high > 0 else False
                    
                    if hit_ma5 or hit_prev_high:
                        buy_score += 0.35
                        reason = "企稳股低吸回踩: " + ("MA5" if hit_ma5 else "") + ("YesterdayHigh" if hit_prev_high else "")
                        buy_reasons.append(reason)
                    elif price > last_high * 1.03:
                        # 企稳股开盘冲太快，适当扣分防止追高，除非量比极大
                        if float(row.get('ratio', 1)) < 15:
                            buy_score -= 0.15
                            debug["refuse_reason"] = "企稳股早盘涨幅过大且无巨量"
                
                # [New] [User Request] MA60 反转启动次日加速 logic
                elif is_ma60_reversal:
                    # 次日特征：低开高走 或 高开高走 (Opening is the Low)
                    open_is_low = (low > 0 and (open_p - low) / open_p < 0.005)
                    if open_is_low and price > open_p:
                        buy_score += 0.45 
                        buy_reasons.append("MA60反转次日加速(低点已现)")
                    elif gap_up > 0 and price > open_p:
                         buy_score += 0.35
                         buy_reasons.append("MA60反转次日高走")
                
                else:
                    # 普通强势股加成逻辑
                    ma5_bias = abs(price - ma5) / ma5
                    if ma5_bias < 0.01:
                        buy_score += 0.25
                        buy_reasons.append(f"早盘回踩MA5({ma5_bias:.1%})")
                    
                    ma10_bias = abs(price - ma10) / ma10
                    if ma10_bias < 0.015:
                        buy_score += 0.20
                        buy_reasons.append(f"早盘回踩MA10({ma10_bias:.1%})")
            
            debug["实时买入分"] = buy_score
            debug["实时买入理由"] = buy_reasons
            
            # --- 动态阈值判定 ---
            threshold = 0.55
            
            # 进化: 叠加防御等级
            defense_level = float(debug.get("defense_level", 0.0))
            threshold += defense_level # 胜率越低，门槛越高 e.g. 0.55 + 0.2 = 0.75
            
            if not vwap_trend_ok:
                 threshold = max(threshold, 0.8) # 趋势不好时，至少需要 0.8
            
            # --- [NEW] 基于周期阶段的动态门槛调整 ---
            if self.cycle_stage == 3: # 脉冲扩张阶段
                threshold += 0.25 # 极大提高门槛 (e.g. 0.55 -> 0.80)
                debug["cycle_penalty"] = "+0.25 (脉冲扩张阶段)"
                # 尾盘禁止在扩张期买入
                if int(now_time.strftime('%H%M')) >= 1400:
                    debug["refuse_reason"] = "扩张期尾盘禁止开仓"
                    return self._hold("扩张期尾盘拦截", debug)
                    
            elif self.cycle_stage == 4: # 见顶回落阶段
                threshold = 0.95 # 几乎禁止买入
                debug["cycle_penalty"] = "Threshold=0.95 (见顶回落阶段)"
                
            elif self.cycle_stage == 1: # 筑底启动阶段
                threshold -= 0.05 # 略微降低门槛，鼓励试错
                debug["cycle_bonus"] = "-0.05 (筑底启动阶段)"

            # 触发条件
            if buy_score >= threshold:
                # 【新增】高位风险拦截：如果顶部信号评分过高 (>0.45)，禁止任何买入/补仓
                top_score = debug.get("top_score", 0)
                if top_score > 0.45:
                    debug["refuse_reason"] = f"高位顶部预警({top_score})"
                    return self._hold(f"高位风险拦截({top_score})", debug)

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
                # ================================================================
                # 💡 最优卖点守卫: 如果价格已经离日内高点过远(>3.5%)，
                # 说明最优出货点已过, 且如果高点已触破则价格在下跌途中,
                # 此时"破均线"触发的提示失去实际意义 (更像追杀而非主动卖出),
                # 止损由 _stop_check 接管，这里只处理"主动最优卖出"信号。
                # ================================================================
                highest_today_g = float(snapshot.get('highest_today', price))
                dist_from_high = (highest_today_g - price) / highest_today_g if highest_today_g > 0 else 0
                
                # 如果离日内高点超过 3.5%，且不是第一次破位报警，则不重复触发，让 _stop_check 接管
                if dist_from_high > 0.035 and snapshot.get("sell_triggered_today", False):
                    debug["sell_skip_reason"] = f"离高点{dist_from_high:.1%}已过最优点, _stop_check接管"
                else:
                    already_broken = snapshot.get("sell_triggered_today", False)
                    prefix = "[破位持续] " if already_broken else ""
                    
                    # 【新热点板块龙头保护】识别 连阳、主升、核心 标签
                    reason_str = str(snapshot.get('reason', '')).lower()
                    is_main_wave = any(tag in reason_str for tag in ["连阳", "主升", "核心", "热门", "龙头"])
                    momentum_floor = 0.5 if "核心" in reason_str or "龙头" in reason_str else (0.4 if is_main_wave else 0.2)
                    
                    # 判断场景
                    is_high_open = open_p > last_close * 1.02 # 高开 2%+
                    is_heavy_vol = ratio > 5.0 or (snapshot.get('lastv1d', 0) > 0 and volume > snapshot['lastv1d'] * 0.8) # 换手大或成交量接近昨日 80%

                    # [User Request] 不跌破前日收盘价，或者实时盘中大幅回撤跌破前日收盘价都不清仓
                    # 除非是那种极端见顶放量下杀
                    is_breaking_last_close = price < last_close

                    # --- [New] Profit Band Protection: SWL -> SWS Shift ---
                    swl = float(row.get("SWL", 0))
                    sws = float(row.get("SWS", 0))
                    orig_reason = snapshot.get('reason', '')
                    if "领涨带" in str(orig_reason) or "SWL" in str(orig_reason):
                        if price < swl and price > sws:
                                # 跌出强领涨带，进入波动带，需收紧止盈
                                urgency = (swl - price) / swl if swl > 0 else 0
                                sell_pos = max(0.4, 1.0 - urgency * 5) # 剧烈回落则大幅减仓
                                return {
                                    "triggered": True,
                                    "action": "卖出",
                                    "position": round(sell_pos, 2),
                                    "reason": f"跌出SWL强领涨带, 支撑转SWS({sws:.2f})",
                                    "debug": debug
                                }

                    if is_high_open and is_heavy_vol and is_breaking_last_close:
                        # 高开下杀放量且跌破前收 (这是致命信号，主升浪也得先撤)
                        sell_pos = 0.1 if is_main_wave else 0.0 # 主升浪优选留一点观察位
                        reason = f"高开下杀放量且破前收(核心卖点), 偏离{deviation:.1%}"
                    elif not is_breaking_last_close:
                        # 虽然跌破均线，但还在前收之上，主升浪保护
                        urgency = min(deviation / 0.03, 1.0)
                        min_pos = max(0.5 if is_main_wave else 0.3, momentum_floor)
                        sell_pos = max(min_pos, 1.0 - urgency * 0.5)
                        reason = f"{prefix}跌破均线但守在前收之上(主升浪保护:{min_pos:.1f})" if is_main_wave else f"{prefix}跌破均线但守在前收之上(偏离{deviation:.1%})"
                    else:
                        # 普通破位且跌破前收
                        if morning_pump:
                            sell_multiplier = 1.0 + (pump_height * 10.0)
                            urgency = min(deviation / 0.02 * sell_multiplier, 1.0)
                            min_pos = momentum_floor
                            sell_pos = max(min_pos, 1.0 - (1.0 - urgency) * 0.5)
                            reason = f"{prefix}诱多后破位前收(主升浪保护:{min_pos:.1f})" if is_main_wave else f"{prefix}诱多后破位前收(偏离{deviation:.1%})"
                        else:
                            urgency = min(deviation / 0.03, 1.0)
                            min_pos = momentum_floor
                            sell_pos = max(min_pos, 1.0 - urgency * 0.5)
                            reason = f"{prefix}跌破均线与前收(主升浪保护:{min_pos:.1f})" if is_main_wave else f"{prefix}跌破均线与前收 {deviation:.1%}"
                    
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
            
        # ========== 4. 跌穿昨日最低价 (User defined priority rule) ==========
        last_low = float(snapshot.get("last_low", 0))
        if last_low > 0 and price < last_low:
             return {
                 "triggered": True,
                 "action": "卖出",
                 "position": 0.0,
                 "reason": f"跌穿昨低({last_low:.2f})破位主杀",
                 "debug": debug
             }
        
        return result

    def _volume_emotion_score(self, volume: float, ratio: float, 
                               v1: float, v2: float, v3: float, debug: dict[str, Any]) -> float:
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
        
        if 2 <= ratio <= 12:
            score += 0.15 # 增加健康换手权重
            reasons.append("换手健康放量")
        elif ratio > 20:
            score -= 0.1
            reasons.append("换手过高风险")
        elif ratio < 0.3:
            score -= 0.2 # 加大惩罚
            reasons.append("极低无量")
        
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

        volume = float(row.get("volume", 0))  # 当日量比（已处理过）
        
        # MA 均线
        ma5 = float(snapshot.get("ma5d", 0) or row.get("ma5d", 0))
        ma20 = float(snapshot.get("ma20d", 0) or row.get("ma20d", 0))
        
        # 地量数据

        llowvol = float(snapshot.get("llowvol", 0))    # 30日内地量
        
        # 最近极大/极小成交量量比
        hvolume = float(snapshot.get("hvolume", 0))
        lvolume = float(snapshot.get("lvolume", 0))
        debug["hvolume"] = hvolume
        debug["lvolume"] = lvolume
        
        # 历史量能
        v1 = float(snapshot.get("lastv1d", 0))

        
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
                # 【新增】高位风险拦截：量价策略也要看顶部评分
                top_score = debug.get("top_score", 0)
                if top_score > 0.45:
                    debug["refuse_reason_vp"] = f"量价买入被高位拦截({top_score})"
                    return result

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
        wv6_val = source_data.get("win", 0)
        win = int(wv6_val) if not pd.isna(wv6_val) else 0
        sum_perc = float(source_data.get("sum_perc", 0))
        rv6_val = source_data.get("red", 0)
        red = int(rv6_val) if not pd.isna(rv6_val) else 0

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
            gv2_val = source_data.get("gren", 0)
            gren = int(gv2_val) if not pd.isna(gv2_val) else 0
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
        
        # ---------- 8. 主升浪结构完整性 (Structural Integrity) ----------
        # User Defined: "每个周期的这样的结构是都各自的主升浪模式 (有新高没有新低)"
        # 检查日线级别结构：Today High > Prev High AND Today Low >= Prev Low (if possible to check)
        # 检查最近3日结构：Highs Increasing AND Lows Increasing
        if len(highs) >= 2 and len(lows) >= 2:
            # 昨高 > 前高, 昨低 > 前低
            struct_ok_1 = highs[0] > highs[1] and lows[0] >= lows[1]
            # 今高 > 昨高, 今低 > 昨低 (需要实时数据)
            today_high = float(source_data.get("high", 0))
            today_low = float(source_data.get("low", 0))
            last_high = highs[0]
            last_low = lows[0]
            
            struct_ok_realtime = False
            if today_high > 0 and last_high > 0:
                # 容忍盘中震荡，只要 Low 不破昨天 Low 太多 (比如 -1%)，且 High 摸过新高
                struct_ok_realtime = (today_high >= last_high) or (today_low >= last_low)
                
                # 严格主升结构定义：Today High > Last High AND Today Low > Last Low
                if today_high > last_high and today_low > last_low:
                     score += 0.25
                     reasons.append("主升结构(新高无新低)")
                elif not struct_ok_realtime:
                     # 结构破坏风险
                     score -= 0.1
                     reasons.append("结构承压")
        
        # 限制得分范围
        score = max(-1.0, min(1.0, score))
        
        debug["multiday_trend_score"] = score
        debug["multiday_trend_reasons"] = reasons
        return score

    def _check_add_position(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any]) -> dict[str, Any]:
        """
        智能加仓策略判定
        
        逻辑细节:
        - 必须盈利 > 1%
        - 趋势强度 > 0.5 (强上升趋势)
        - 禁止高位放量下杀加仓 (价格低于均价且量能 > 1.5)
        - 禁止低开下杀加仓 (低开且价格持续低于开盘)
        - 统计学 win 计数不减 (代表持仓日线未破)
        """
        price = float(row.get("trade", 0))
        cost_price = float(snapshot.get("cost_price", 0))
        trend_strength = debug.get("trend_strength", 0.0)
        
        # 1. 盈利要求：必须盈利 > 1.0% (防止加仓摊平变深陷)
        pnl = (price - cost_price) / cost_price
        if pnl < 0.01:
            return {"allow": False, "reason": f"盈利不足加仓要求({pnl:.1%}<1%)"}
        
        # 2. 趋势要求：强上升趋势
        if trend_strength < 0.5:
             return {"allow": False, "reason": f"趋势强度不足({trend_strength:.2f}<0.5)"}
             
        # 3. 量能异常检测：禁止高位放量下杀加仓
        nclose = debug.get("nclose", snapshot.get("nclose", 0))
        volume = float(row.get("volume", 0))
        if price < nclose and volume > 1.5:
             return {"allow": False, "reason": "均价线下放量下杀"}
             
        # 4. 开盘表现：低开下杀禁止加仓
        open_p = float(row.get("open", 0))
        last_close = float(snapshot.get("last_close", 0))
        if last_close > 0 and open_p < last_close * 0.99 and price < open_p:
             return {"allow": False, "reason": "低开且价格弱于开盘"}

        # 5. 板块环境辅助 (可选)
        sector_bonus = debug.get("sector_bonus", 0)
        if sector_bonus < 0:
             return {"allow": False, "reason": "板块效应转弱"}

        return {"allow": True, "reason": "符合智能加仓环境"}


    def _hold(self, reason: str, debug: dict[str, Any], position: float = 0.0) -> dict[str, Any]:
        """返回持仓决策"""
        # logger.debug(f"Engine HOLD: {reason}")
        return {
            "action": "持仓" if position > 0 else "观望",
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
    
    # ==================== 主升浪持仓保护 ====================

    def _main_wave_hold_check(self, row: dict[str, Any], snapshot: dict[str, Any], debug: dict[str, Any], top_info: dict = None) -> dict[str, Any] | None:
        """
        主升浪持仓保护逻辑 (002667 模型优化)
        """
        wv4_val = snapshot.get('win', 0)
        win = int(wv4_val) if not pd.isna(wv4_val) else 0
        rv4_val = snapshot.get('red', 0)
        red = int(rv4_val) if not pd.isna(rv4_val) else 0
        
        # 定义主升浪阶段：连阳3日以上 或 站稳5日线5日以上
        is_main_wave = win >= 3 or red >= 5
        
        if not is_main_wave:
            return None
            
        debug["持仓阶段"] = "主升浪"
        
        price = float(row.get('trade', 0))
        ma5 = float(row.get('ma5d', 0))
        ma20 = float(row.get('ma20d', 0) or snapshot.get('ma20d', 0))
        nclose = float(row.get('nclose', 0))
        last_close = float(snapshot.get('last_close', 0))
        volume = float(row.get('volume', 0)) # 实时量比
        open_p = float(row.get('open', 0))
        high = float(row.get('high', 0))
        
        # 1. 乖离率检查：如果偏离 20 日线过远 (>15%)，主升浪保护需极度谨慎
        bias_ma20 = (price - ma20) / ma20 if ma20 > 0 else 0
        is_extreme_bias = bias_ma20 > 0.15
        
        if is_extreme_bias:
            debug["主升状态"] = f"极端乖离({bias_ma20:.1%})"
        
        # 实时顶部信号检测 (从外部传入或重新计算)
        if top_info is None:
            day_df = snapshot.get('day_df', pd.DataFrame())
            top_info = detect_top_signals(day_df, row) # 传入 row 作为当前 tick
        
        # 💥 [NEW] 将指标注入 debug，映射到 live 报警
        debug["td_setup"] = snapshot.get('td_setup', 0)
        debug["top_score"] = top_info['score']
        
        # 💥 [NEW] D+1/D+2 稳定性检查 (缩量十字星企稳)
        yesterday_pattern = str(snapshot.get("pattern", "")).lower()
        is_stabilizing = "stabilization" in yesterday_pattern or "rising_structure" in yesterday_pattern or "企稳" in yesterday_pattern
        
        body_ratio = abs(price - open_p) / open_p if open_p > 0 else 1.0
        is_curr_doji = body_ratio < 0.015
        is_curr_shrunk = volume < 1.1 # 盘中成交量比不高
        
        if is_main_wave and (is_stabilizing or (is_curr_doji and is_curr_shrunk)):
             if price > ma5 * 0.995: # 守住五日线
                 return {
                    "triggered": True,
                    "action": "持有",
                    "position": 1.0,
                    "reason": "主升浪稳定性确认(缩量企稳/D+1/D+2)",
                    "debug": debug
                }
        
        # 💥 [NEW] 核心逻辑：高位放量滞涨/阴跌，主升浪也要“弃船”
        # 如果 top_score 已经很高，或者在高位放量 (量比>2.0) 且破均线
        is_vol_exhaustion = volume > 2.0 and price < nclose
        
        if top_info['score'] > 0.40 or (is_extreme_bias and is_vol_exhaustion):
            reason = f"主升高位分歧: {', '.join(top_info['signals'])}" if top_info['score'] > 0.4 else "高位放量破均线(主升避险)"
            return {
                "triggered": True,
                "action": "卖出",
                "position": 0.4 if top_info['score'] > 0.6 else 0.7, 
                "reason": reason
            }
            
        # 💥 [New] [User Request] 5-6日动能周期识别
        wc_val = snapshot.get("win", 0)
        win_count = int(wc_val) if not pd.isna(wc_val) else 0
        if win_count >= 5:
            # 动能衰竭期：只要跌破分时均线 或 产生冲高回落，立即保护
            if price < nclose or (high > 0 and (high - price) / high > 0.04):
                return {
                    "triggered": True,
                    "action": "卖出",
                    "position": 0.5, # 减仓一半，识别动能切换
                    "reason": f"动能周期达标({win_count}d)+分时弱势",
                    "debug": debug
                }

        # 💥 [New] 派发结构杀跌拦截 (300548 案例)
        # 如果当日高位回落幅度很大 且 跌破昨日收盘价 且 跌破今日均价
        if high > 0 and (high - price) / high > 0.05: # 大幅杀跌
            if price < last_close and price < nclose:
                 return {
                    "triggered": True,
                    "action": "卖出",
                    "position": 0.0, # 清仓
                    "reason": "派发结构确认(高位杀跌破前收)",
                    "debug": debug
                }
            
        # 核心保护：只要在 5 日线之上，且跌幅未破位（不破昨日收盘且不破今日均价），坚决持仓
        # 002667 案例：在 1.30 之前虽然波动，但未破关键支撑
        
        # 止损熔断：跌破昨日收盘价 且 跌破今日均价 且 跌破 MA5（三合一确认清仓）
        # 如果是极端高位，只要两项破位就该走
        is_breaking = 0
        if last_close > 0 and price < last_close: is_breaking += 1
        if nclose > 0 and price < nclose: is_breaking += 1
        if ma5 > 0 and price < ma5: is_breaking += 1
        
        if (is_extreme_bias and is_breaking >= 2) or (is_breaking >= 3):
             return {
                "triggered": True,
                "action": "强制清仓",
                "position": 0.0,
                "reason": f"主升浪破位(高位分歧): {'+'.join(['破昨收' if price < last_close else '', '破均线' if price < nclose else '', '破MA5' if price < ma5 else ''])}"
            }
            
        # 回踩保护：只要高位缩量回调不破 MA5，视为买点/持有
        # [User Request] 极端高位时不建议“回踩买入”
        if ma5 > 0 and price > ma5 * 0.99:
            if is_extreme_bias and volume < 0.8:
                 # 高位缩量下跌，虽未破位但也需警惕
                 return {
                    "triggered": True,
                    "action": "持有",
                    "position": 0.8, # 减一点点，不焊死
                    "reason": "主升高位缩量(MA5护航)"
                }
            return {
                "triggered": True,
                "action": "持有",
                "position": 1.0,
                "reason": "主升浪 MA5 护航"
            }
            
        return None

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

        # --- [New] SWS/SWL Profit Band Logic ---
        swl = float(row.get("SWL", 0))
        sws = float(row.get("SWS", 0))
        if price > swl and swl > 0:
            score += 0.15
            reasons.append("处于SWL强力领涨带")
            debug["profit_band"] = "SWL"
        elif price > sws and sws > 0:
            score += 0.05
            reasons.append("处于SWS小浪波动带")
            debug["profit_band"] = "SWS"
        
        # --- [New] Stabilization Pattern Bonus ---
        # yesterday_pattern = str(snapshot.get("pattern", ""))
        # if "stabilization" in yesterday_pattern or "rising_structure" in yesterday_pattern:
        #     score += 0.1
        #     reasons.append(f"昨日信号({yesterday_pattern})加成")

        # 2. 结构支撑 (前低/布林/缺口)
        low10 = float(snapshot.get("low10", 0))

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

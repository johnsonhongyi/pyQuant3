# -*- coding: utf-8 -*-
"""
ats/intraday_strategy_engine.py — 单独分时交易策略与策略路由引擎
支持新股首日分批卖出（策略A）、留仓赌趋势（策略B）以及策略自定制编辑解析。
能够推断时间轴阶段、进行实时条件评估并走策略路由下发实盘信号。
"""

import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time
from typing import Dict, List, Any, Optional, Tuple

from sys_utils import get_app_root, get_conf_path
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyEngine")

class IntradayStrategyEngine:
    """分时交易策略引擎"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, config_filename="intraday_newstock_strategies.json"):
        self.config_path = get_conf_path(config_filename, get_app_root())
        self.strategies: List[Dict[str, Any]] = []
        self.active_strategy: Optional[Dict[str, Any]] = None
        self.rule_state_map: Dict[str, Dict[str, Any]] = {} # code -> state
        self.load_config()

    def load_config(self) -> bool:
        """从 JSON 加载策略配置"""
        if not os.path.exists(self.config_path):
            alt_path = os.path.join(get_app_root(), "config", "intraday_newstock_strategies.json")
            if os.path.exists(alt_path):
                self.config_path = alt_path
        if not os.path.exists(self.config_path):
            logger.warning(f"Strategy config file not found: {self.config_path}")
            return False
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.strategies = data.get("strategies", [])
            logger.info(f"✅ 成功加载 {len(self.strategies)} 套分时交易策略配置")
            return True
        except Exception as e:
            logger.error(f"❌ 加载分时策略配置失败: {e}")
            return False

    def save_config(self, data: Dict[str, Any]) -> bool:
        """保存自定制策略配置"""
        try:
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config_path)
            self.strategies = data.get("strategies", [])
            logger.info("✅ 策略配置文件更新落盘成功")
            return True
        except Exception as e:
            logger.error(f"❌ 保存策略配置文件失败: {e}")
            return False

    def get_open_price_tier(self, open_price: float) -> Tuple[str, str, str]:
        """
        开盘价档位速查判定
        返回: (tier_name, default_strategy_id, action_mode)
        """
        if open_price >= 467.0:
            return ("乐观档", "strategy_b_new_stock_trend_hold", "trend_hold")
        elif open_price >= 412.0:
            return ("乐观下沿", "strategy_a_new_stock_batch_sell", "standard")
        elif open_price >= 336.0:
            return ("中性档", "strategy_a_new_stock_batch_sell", "standard")
        elif open_price >= 280.0:
            return ("中性下沿", "strategy_a_new_stock_batch_sell", "decelerated")
        else:
            return ("保守档", "strategy_a_new_stock_batch_sell", "hold_rebound")

    def get_all_target_codes(self) -> List[str]:
        """获取所有 JSON 策略配置中指定的目标股票代码列表（去除重复与格式化）"""
        codes = []
        for st in self.strategies:
            t_codes = st.get("target_codes", [])
            t_code = st.get("target_code", "")
            if isinstance(t_codes, list):
                for tc in t_codes:
                    c_clean = "".join(filter(str.isdigit, str(tc))).zfill(6)
                    if c_clean and c_clean not in codes and c_clean != "000000":
                        codes.append(c_clean)
            if t_code:
                c_clean = "".join(filter(str.isdigit, str(t_code))).zfill(6)
                if c_clean and c_clean not in codes and c_clean != "000000":
                    codes.append(c_clean)
        return codes

    def get_code_strategy_map(self) -> Dict[str, Dict[str, Any]]:
        """获取全量代码与策略绑定映射字典 {code: strategy_dict}"""
        code_map = {}
        for c in self.get_all_target_codes():
            code_map[c] = self.auto_select_strategy(0.0, code=c)
        return code_map

    def get_default_target_code(self) -> Optional[str]:
        """获取 JSON 配置文件中的首个目标股票代码，无则返回 None"""
        all_codes = self.get_all_target_codes()
        return all_codes[0] if all_codes else None

    def get_strategy_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """按 strategy_id 获取对应的策略字典"""
        for st in self.strategies:
            if st.get("id") == strategy_id:
                return st
        return None

    def auto_select_strategy(self, open_price: float, code: Optional[str] = None, is_b_conditions_met: bool = True) -> Dict[str, Any]:
        """根据股票代码 code 或开盘价与条件自动选择对应策略（支持多 code 专用策略与通用规则）"""
        if code:
            c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
            for st in self.strategies:
                target_codes = st.get("target_codes", [])
                target_code = st.get("target_code", "")
                if isinstance(target_codes, list) and any(c_clean == "".join(filter(str.isdigit, str(tc))).zfill(6) for tc in target_codes if tc):
                    return st
                if target_code and c_clean == "".join(filter(str.isdigit, str(target_code))).zfill(6):
                    return st

        tier_name, strat_id, mode = self.get_open_price_tier(open_price)
        if strat_id == "strategy_b_new_stock_trend_hold" and not is_b_conditions_met:
            # 即使 Open >= 467，若 4 条件不满足，降级至 策略A 标准
            strat_id = "strategy_a_new_stock_batch_sell"

        for st in self.strategies:
            if st.get("id") == strat_id:
                return st
        return self.strategies[0] if self.strategies else {}

    def get_current_phase(self, time_str: str, strategy: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        根据盘中时间 'HH:MM' 推算当前所属的时间轴阶段
        按时间跨度狭窄度优先匹配，避免长时段覆盖专有短时段
        """
        if not strategy:
            return None, -1
        
        phases = strategy.get("phases", [])
        clean_t = time_str[-8:] if len(time_str) >= 8 else time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        matched_phases = []
        for idx, ph in enumerate(phases):
            s_time = ph.get("start_time", "00:00")
            e_time = ph.get("end_time", "23:59")
            if s_time <= clean_t <= e_time:
                try:
                    sh, sm = map(int, s_time.split(":"))
                    eh, em = map(int, e_time.split(":"))
                    span = (eh * 60 + em) - (sh * 60 + sm)
                except Exception:
                    span = 9999
                matched_phases.append((span, idx, ph))

        if matched_phases:
            matched_phases.sort(key=lambda x: x[0])
            best = matched_phases[0]
            return best[2], best[1]

        # 兜底：根据时间段就近选择
        if clean_t < "09:25":
            return phases[0] if phases else None, 0
        elif clean_t >= "14:50":
            return phases[-1] if len(phases) >= 4 else phases[0], len(phases)-1
            
        return phases[1] if len(phases) >= 2 else None, 1

    def _get_stock_state(self, code: str, open_price: float) -> Dict[str, Any]:
        """获取或初始化某股票的策略运行状态机"""
        c_clean = str(code).zfill(6)
        if c_clean not in self.rule_state_map:
            self.rule_state_map[c_clean] = {
                "open_price": open_price,
                "max_price": open_price,
                "min_price": open_price,
                "remaining_ratio": 1.0,
                "triggered_rules": set(),
                "execution_logs": [],
                "signals": []
            }
        state = self.rule_state_map[c_clean]
        if open_price > 0 and state["open_price"] <= 0:
            state["open_price"] = open_price
        return state

    def evaluate_tick(
        self,
        code: str,
        tick_row: Dict[str, Any],
        open_price: float,
        current_time_str: str,
        bid1_price: float = 0.0,
        strategy: Optional[Dict[str, Any]] = None,
        is_b_conditions_met: bool = True,
        bar_index: int = 0
    ) -> List[SignalPoint]:
        """
        评估单个分时/Tick 节点，触发逻辑规则并生成 SignalPoint
        """
        if open_price <= 0:
            return []

        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, open_price)
        
        # 1. 动态选择策略
        if strategy is None:
            strategy = self.auto_select_strategy(open_price, code=c_clean, is_b_conditions_met=is_b_conditions_met)

        tier_name, _, action_mode = self.get_open_price_tier(open_price)
        
        # 保守档不卖出，等待反弹
        if action_mode == "hold_rebound":
            return []

        # 2. 提取当前价格与时间
        price = float(tick_row.get("trade", tick_row.get("close", 0.0)))
        if price <= 0:
            return []
            
        state["max_price"] = max(state["max_price"], price)
        state["min_price"] = min(state["min_price"], price) if state["min_price"] > 0 else price
        
        clean_time = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_time) > 5 and ":" in clean_time:
            clean_time = clean_time[:5]

        phase, phase_idx = self.get_current_phase(clean_time, strategy)
        if not phase:
            return []

        generated_signals: List[SignalPoint] = []
        rules = phase.get("rules", [])

        # 3. 逐条评估阶段内规则
        for rule in rules:
            rule_id = rule.get("rule_id", "")
            if rule_id in state["triggered_rules"]:
                continue

            cond_mode = rule.get("condition_mode", "all")
            # 条件模式校验（如仅在 decelerated 模式触发）
            if cond_mode != "all" and cond_mode != action_mode:
                continue

            is_triggered = False
            trigger_reason = ""
            
            # 规则条件匹配判断
            if rule_id == "rule_a1_surge":
                if price >= open_price * 1.10:
                    is_triggered = True
                    trigger_reason = f"开盘冲高≥10% (现价:{price:.2f} >= 目标:{open_price*1.10:.2f})"
            elif rule_id == "rule_a1_surge_decelerated":
                if price >= open_price * 1.05:
                    is_triggered = True
                    trigger_reason = f"中性下沿冲高≥5% (现价:{price:.2f} >= 目标:{open_price*1.05:.2f})"
            elif rule_id == "rule_a1_timeout":
                if clean_time >= "10:00" and "rule_a1_surge" not in state["triggered_rules"] and "rule_a1_surge_decelerated" not in state["triggered_rules"]:
                    is_triggered = True
                    trigger_reason = "10:00整冲高未触发兜底卖出30%"
            elif rule_id == "rule_a2_halt_30":
                if state["max_price"] >= open_price * 1.30:
                    is_triggered = True
                    trigger_reason = f"+30%临停复牌卖30% (最高:{state['max_price']:.2f} >= 临停阈值:{open_price*1.30:.2f})"
            elif rule_id == "rule_a3_overnight_check":
                if clean_time >= "14:50" and price >= open_price * 1.20:
                    is_triggered = True
                    trigger_reason = f"14:50仍高出开盘20%(现价:{price:.2f})，保留10%过夜，清仓其余"
            elif rule_id == "rule_a3_clear_all":
                if clean_time >= "14:50" and "rule_a3_overnight_check" not in state["triggered_rules"]:
                    is_triggered = True
                    trigger_reason = "14:50~14:57 尾盘市价清仓剩余全部"
            elif rule_id == "rule_b1_surge":
                if price >= open_price * 1.08:
                    is_triggered = True
                    trigger_reason = f"策略B开盘冲高≥8% (现价:{price:.2f} >= 目标:{open_price*1.08:.2f})"
            elif rule_id == "rule_b1_timeout":
                if clean_time >= "10:00" and "rule_b1_surge" not in state["triggered_rules"]:
                    is_triggered = True
                    trigger_reason = "策略B 10:00整超时卖出20%"
            elif rule_id == "rule_b2_halt_60":
                if state["max_price"] >= open_price * 1.60:
                    is_triggered = True
                    trigger_reason = f"+60%临停复牌未创新高再卖33% (最高:{state['max_price']:.2f})"
            elif rule_id == "rule_b3_trailing_stop":
                high_t = state.get("high_t", state["max_price"])
                if price <= high_t * 0.90:
                    is_triggered = True
                    trigger_reason = f"T日高点({high_t:.2f})回撤10%移动止盈清仓(现价:{price:.2f})"

            # 4. 触发动作与信号路由生成
            if is_triggered:
                sell_ratio = float(rule.get("sell_ratio", 0.30))
                order_type = rule.get("order_type", "market_price")
                price_offset_ratio = float(rule.get("price_offset_ratio", 1.02))
                
                # 计算建议挂单价格 (价格笼子限制: 买一价 * 1.02)
                suggested_limit_price = price
                if order_type == "limit_price_cage":
                    ref_bid = bid1_price if bid1_price > 0 else price
                    suggested_limit_price = round(ref_bid * price_offset_ratio, 2)
                elif order_type == "limit" and "limit_price_expr" in rule:
                    suggested_limit_price = round(open_price * 1.28, 2)

                # 标记规则已触发
                state["triggered_rules"].add(rule_id)
                actual_sell_ratio = min(sell_ratio, state["remaining_ratio"])
                state["remaining_ratio"] = max(0.0, state["remaining_ratio"] - actual_sell_ratio)

                sig_msg = f"[{rule.get('name')}] {trigger_reason} | 卖出{actual_sell_ratio*100:.0f}% 建议挂单:{suggested_limit_price:.2f}"
                log_entry = f"{clean_time} {sig_msg}"
                state["execution_logs"].append(log_entry)
                logger.info(f"⚡ [IntradayStrategyEngine] {c_clean} {log_entry}")

                sp = SignalPoint(
                    code=c_clean,
                    timestamp=clean_time,
                    bar_index=bar_index,
                    price=price,
                    signal_type=SignalType.SELL,
                    reason=f"[{rule_id}] {trigger_reason}",
                    source=SignalSource.STRATEGY_ENGINE
                )
                # 附加扩展数据给路由
                sp.sell_ratio = actual_sell_ratio
                sp.suggested_price = suggested_limit_price
                sp.order_type = order_type
                sp.rule_id = rule_id
                sp.phase_id = phase.get("phase_id")
                
                state["signals"].append(sp)
                generated_signals.append(sp)

        return generated_signals

    def reset_state(self, code: Optional[str] = None):
        """重置股票判定状态"""
        if code:
            c_clean = str(code).zfill(6)
            if c_clean in self.rule_state_map:
                del self.rule_state_map[c_clean]
        else:
            self.rule_state_map.clear()

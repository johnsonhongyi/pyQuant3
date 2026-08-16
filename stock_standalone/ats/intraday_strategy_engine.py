# -*- coding: utf-8 -*-
"""
ats/intraday_strategy_engine.py — 单独分时交易策略与策略路由引擎
支持新股首日分批卖出（策略A）、留仓赌趋势（策略B）以及频准激光（688826）8/18 专属上市盯盘与阶梯策略。
能够推断时间轴阶段、进行 7 节点动态评分、形态分类、实盘条件评估与阶段实操指引生成。
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
    """分时交易策略与新股阶梯盯盘引擎"""
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

    def get_stock_ladder_spec(self, code: Optional[str] = None) -> Dict[str, Any]:
        """
        获取证券阶梯规格配置（优先从 JSON 专属策略中读取，如 688826 频准激光）
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else "688826"
        st = self.auto_select_strategy(0.0, code=c_clean)
        if st and "stock_spec" in st:
            return st["stock_spec"]

        # 默认回退 688826 频准激光标准规格
        issue_p = 186.88
        return {
            "code": c_clean,
            "name": "频准激光" if c_clean == "688826" else "新股标的",
            "issue_price": issue_p,
            "float_shares_wan": 761.78,
            "float_mv_yi": 14.24,
            "lottery_rate": "0.02014%",
            "price_ladder": [
                {"name": "+100%", "gain_pct": 100.0, "price": round(issue_p * 2.0, 2), "meaning": "翻倍"},
                {"name": "+200%", "gain_pct": 200.0, "price": round(issue_p * 3.0, 2), "meaning": "强势基准"},
                {"name": "+300%", "gain_pct": 300.0, "price": round(issue_p * 4.0, 2), "meaning": "高频发区间"},
                {"name": "+400%", "gain_pct": 400.0, "price": round(issue_p * 5.0, 2), "meaning": "强势上限"},
                {"name": "+500%", "gain_pct": 500.0, "price": round(issue_p * 6.0, 2), "meaning": "极端行情"}
            ],
            "turnover_ladder": [
                {"level": "弱换手", "range": "<40%", "min": 0.0, "max": 40.0, "meaning": "关注度不足"},
                {"level": "标准换手", "range": "50-70%", "min": 50.0, "max": 70.0, "meaning": "健康"},
                {"level": "高换手", "range": "70-90%", "min": 70.0, "max": 90.0, "meaning": "充分交换"},
                {"level": "极高换手", "range": ">90%", "min": 90.0, "max": 999.0, "meaning": "过热/分歧"}
            ],
            "intensity_benchmark": {
                "metric": "成交额/流通市值(14.24亿)",
                "threshold": 2.5,
                "meaning": "资金强度极高"
            }
        }

    def get_timeline_nodes_def(self, code: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取 7 节点标准时序定义列表"""
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else "688826"
        st = self.auto_select_strategy(0.0, code=c_clean)
        if st and "timeline_nodes" in st:
            return st["timeline_nodes"]

        # 默认回退 7 节点标准定义
        return [
            {
                "node_id": "node_1_auction",
                "node_num": "①",
                "time_str": "9:25",
                "time_range": "09:15~09:25",
                "name": "集合竞价定盘",
                "weight": 0.15,
                "focus": "开盘价/涨幅、买卖盘口厚度",
                "strong_signals": "高开+200%以上(>560.64元)；买一量>>卖一量；买单持续堆积",
                "risk_signals": "高开后买单快速撤单；卖盘压单沉重；开盘价远低于预期",
                "action_guide": "若高开>560元且买盘充沛，启动强势持有/冲高阶梯卖出；若远低于373元谨慎对待"
            },
            {
                "node_id": "node_2_first_wave",
                "node_num": "②",
                "time_str": "9:40",
                "time_range": "09:25~09:40",
                "name": "早盘第一波攻击",
                "weight": 0.15,
                "focus": "开盘后第一波放量方向",
                "strong_signals": "放量上攻突破开盘价；量价齐升；快速脱离成本区",
                "risk_signals": "放量砸盘跌破开盘价；高开低走；量增价跌",
                "action_guide": "冲高较开盘涨10%以上挂买一价*1.02卖出首批50%；跌破开盘价且无反弹果断减仓"
            },
            {
                "node_id": "node_3_turnover",
                "node_num": "③",
                "time_str": "10:00",
                "time_range": "09:40~10:00",
                "name": "换手质量检验",
                "weight": 0.20,
                "focus": "换手率进度、价格是否抬升",
                "strong_signals": "持续换手且价格抬升；10min换手>15%；低点不断抬高",
                "risk_signals": "巨量但价格不涨；放量滞涨；低点下移",
                "action_guide": "10:00前未触发冲高则10:00市价卖30%；若量缩价稳低点抬高则持有等待分歧承接"
            },
            {
                "node_id": "node_4_divergence",
                "node_num": "④",
                "time_str": "11:00",
                "time_range": "10:00~11:00",
                "name": "分歧承接测试",
                "weight": 0.15,
                "focus": "回落后承接力、是否破分时均价线",
                "strong_signals": "回落后快速收回；均价线向上；缩量回调后放量上攻",
                "risk_signals": "一路下跌不回头；破均价线无量承接；反弹无力",
                "action_guide": "均线不破且放量再起可持有博午后；破均线且反抽不过均线坚决离场"
            },
            {
                "node_id": "node_5_afternoon",
                "node_num": "⑤",
                "time_str": "14:00",
                "time_range": "13:00~14:00",
                "name": "午后突破验证",
                "weight": 0.10,
                "focus": "午后是否再创新高、板块联动",
                "strong_signals": "突破上午最高价；午后放量上涨；激光/半导体设备板块同步走强",
                "risk_signals": "午后弱势缩量；冲高回落；板块分化",
                "action_guide": "突破上午最高价继续持有；若冲高回落且板块走弱逢高派发剩余仓位"
            },
            {
                "node_id": "node_6_closing_rally",
                "node_num": "⑥",
                "time_str": "14:50",
                "time_range": "14:30~14:50",
                "name": "尾盘抢筹强度",
                "weight": 0.15,
                "focus": "尾盘方向、量能变化",
                "strong_signals": "放量创新高；尾盘抢筹；封板或逼近最高价",
                "risk_signals": "放量跳水；尾盘恐慌抛售；快速回落",
                "action_guide": "尾盘抢筹坚决且逼近最高准备保留过夜仓；若放量跳水尾盘市价清仓"
            },
            {
                "node_id": "node_7_closing_structure",
                "node_num": "⑦",
                "time_str": "15:00",
                "time_range": "14:50~15:00",
                "name": "收盘结构与锁仓",
                "weight": 0.10,
                "focus": "收盘价位置、收盘/最高价比例",
                "strong_signals": "收盘接近最高(收盘/最高>90%)；缩量横盘守住涨幅",
                "risk_signals": "收盘远低于最高(收盘/最高<80%)；放量跳水",
                "action_guide": "收盘/最高>90%且综合评分>=8.0可留10%~20%过夜，次日竞价关注；否则清仓"
            }
        ]

    def get_open_price_tier(self, open_price: float, code: Optional[str] = None) -> Tuple[str, str, str]:
        """
        开盘价档位速查判定
        返回: (tier_name, default_strategy_id, action_mode)
        """
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if c_clean == "688826":
            if open_price >= 560.64:
                return ("乐观档(+200%基准)", "strategy_pinzhun_laser_688826", "trend_hold")
            elif open_price >= 467.0:
                return ("乐观下沿(+150%)", "strategy_pinzhun_laser_688826", "standard")
            elif open_price >= 373.76:
                return ("中性档(+100%翻倍)", "strategy_pinzhun_laser_688826", "standard")
            elif open_price >= 280.0:
                return ("中性下沿(+50%)", "strategy_pinzhun_laser_688826", "decelerated")
            else:
                return ("保守档(<+50%)", "strategy_pinzhun_laser_688826", "hold_rebound")

        # 通用新股标准档位
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
        if not codes:
            codes = ["688826"]
        return codes

    def get_code_strategy_map(self) -> Dict[str, Dict[str, Any]]:
        """获取全量代码与策略绑定映射字典 {code: strategy_dict}"""
        code_map = {}
        for c in self.get_all_target_codes():
            code_map[c] = self.auto_select_strategy(0.0, code=c)
        return code_map

    def get_default_target_code(self) -> Optional[str]:
        """获取首个目标股票代码，无则默认 688826"""
        all_codes = self.get_all_target_codes()
        return all_codes[0] if all_codes else "688826"

    def get_strategy_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """按 strategy_id 获取对应的策略字典"""
        for st in self.strategies:
            if st.get("id") == strategy_id:
                return st
        return None

    def auto_select_strategy(self, open_price: float, code: Optional[str] = None, is_b_conditions_met: bool = True) -> Dict[str, Any]:
        """根据股票代码 code 或开盘价与条件自动选择对应策略"""
        if code:
            c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
            for st in self.strategies:
                target_codes = st.get("target_codes", [])
                target_code = st.get("target_code", "")
                if isinstance(target_codes, list) and any(c_clean == "".join(filter(str.isdigit, str(tc))).zfill(6) for tc in target_codes if tc):
                    return st
                if target_code and c_clean == "".join(filter(str.isdigit, str(target_code))).zfill(6):
                    return st

        tier_name, strat_id, mode = self.get_open_price_tier(open_price, code=code)
        if strat_id == "strategy_b_new_stock_trend_hold" and not is_b_conditions_met:
            strat_id = "strategy_a_new_stock_batch_sell"

        for st in self.strategies:
            if st.get("id") == strat_id:
                return st
        # 默认优先 strategy_pinzhun_laser_688826 或 strategy_a_new_stock_batch_sell
        for st in self.strategies:
            if st.get("id") == "strategy_a_new_stock_batch_sell":
                return st
        return self.strategies[0] if self.strategies else {}

    def get_current_phase(self, time_str: str, strategy: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        根据盘中时间 'HH:MM' 推算当前所属的时间轴阶段
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

        if clean_t < "09:25":
            return phases[0] if phases else None, 0
        elif clean_t >= "14:50":
            return phases[-1] if len(phases) >= 4 else phases[0], len(phases)-1
            
        return phases[1] if len(phases) >= 2 else None, 1

    def _get_stock_state(self, code: str, open_price: float) -> Dict[str, Any]:
        """获取或初始化某股票的策略运行与 7 节点评分状态机"""
        c_clean = str(code).zfill(6)
        if c_clean not in self.rule_state_map:
            self.rule_state_map[c_clean] = {
                "open_price": open_price,
                "max_price": open_price,
                "min_price": open_price,
                "high_am": open_price, # 上午最高价
                "remaining_ratio": 1.0,
                "triggered_rules": set(),
                "execution_logs": [],
                "signals": [],
                "manual_scores": {}, # node_id -> float (人工覆盖评分)
                "timeline_eval_cache": {} # 7 节点评估缓存
            }
        state = self.rule_state_map[c_clean]
        if open_price > 0 and state["open_price"] <= 0:
            state["open_price"] = open_price
        return state

    def set_manual_node_score(self, code: str, node_id_or_idx: Any, score: float):
        """设置某节点的人工打分覆盖"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        state["manual_scores"][str(node_id_or_idx)] = float(score)

    def set_node_custom_param(self, code: str, node_id: str, value: float):
        """设置某节点的校准价格或换手率参数"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        if "node_custom_params" not in state:
            state["node_custom_params"] = {}
        state["node_custom_params"][str(node_id)] = float(value)

    def reset_node_custom_params(self, code: str):
        """重置所有节点的校准参数与人工打分"""
        c_clean = str(code).zfill(6)
        state = self._get_stock_state(c_clean, 0.0)
        state["node_custom_params"] = {}
        state["manual_scores"] = {}

    def evaluate_seven_nodes(
        self,
        code: str,
        current_time_str: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float = 0.0,
        turnover_rate: float = 0.0,
        amount: float = 0.0, # 成交金额(元)
        bid1_price: float = 0.0,
        ask1_price: float = 0.0,
        sector_strengths: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        全面评估 7 大时序节点，生成各节点观察值、强中弱判定、节点分(0-10)、加权得分、形态分类与实操建议。
        支持根据用户在表格中输入的校准价格/换手率全自动重新推导评分。
        """
        c_clean = str(code).zfill(6)
        spec = self.get_stock_ladder_spec(c_clean)
        nodes_def = self.get_timeline_nodes_def(c_clean)
        state = self._get_stock_state(c_clean, open_price)
        custom_params = state.setdefault("node_custom_params", {})

        clean_t = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        # 记录全天最高/最低与上午最高
        if price > 0:
            state["max_price"] = max(state.get("max_price", price), high_price, price)
            min_p = state.get("min_price", price)
            state["min_price"] = min(min_p, low_price, price) if min_p > 0 else price
            if clean_t < "13:00":
                state["high_am"] = max(state.get("high_am", price), state["max_price"])

        max_p = state.get("max_price", high_price if high_price > 0 else price)
        min_p = state.get("min_price", low_price if low_price > 0 else price)
        high_am = state.get("high_am", max_p)
        vwap_val = vwap if vwap > 0 else (price if price > 0 else open_price)

        issue_p = float(spec.get("issue_price", 186.88))
        float_mv_yi = float(spec.get("float_mv_yi", 14.24)) # 亿元
        amount_yi = (amount / 1e8) if amount > 1e5 else 0.0 # 转换为亿元
        intensity_ratio = (amount_yi / float_mv_yi) if float_mv_yi > 0 else 0.0

        gain_from_issue = ((price - issue_p) / issue_p * 100.0) if (issue_p > 0 and price > 0) else 0.0
        gain_from_open = ((price - open_price) / open_price * 100.0) if (open_price > 0 and price > 0) else 0.0
        close_high_ratio = (price / max_p) if max_p > 0 else 1.0

        node_results = []
        total_weighted_score = 0.0
        current_node_idx = 0
        current_node_info = None

        # 7 节点时间截点列表
        time_milestones = ["09:25", "09:40", "10:00", "11:00", "14:00", "14:50", "15:00"]

        for idx, nd in enumerate(nodes_def):
            n_id = nd.get("node_id", f"node_{idx+1}")
            n_name = nd.get("name", "")
            n_time = nd.get("time_str", time_milestones[idx] if idx < len(time_milestones) else "15:00")
            n_weight = float(nd.get("weight", 0.15))
            m_time = time_milestones[idx] if idx < len(time_milestones) else "15:00"

            # 判定节点活跃状态: 已过(completed)、当前(active)、待到达(pending)
            if idx == 0:
                is_active = (clean_t <= m_time)
                is_completed = (clean_t > m_time)
            else:
                prev_m = time_milestones[idx-1]
                is_active = (prev_m < clean_t <= m_time)
                is_completed = (clean_t > m_time)

            if is_active:
                current_node_idx = idx
                current_node_info = nd

            # 1. 提取/推算盘中实际观察值与校准参数
            observed_val = ""
            judgment = "中" # 强 / 中 / 弱
            auto_score = 5.0 # 0 - 10
            remarks = ""
            input_val = 0.0
            input_unit = "元"

            if idx == 0: # 9:25 集合竞价 (校准开盘价)
                default_op = open_price if open_price > 0 else (issue_p * 3.0 if issue_p > 0 else 565.0)
                cur_op = float(custom_params.get(n_id, default_op))
                input_val = cur_op
                input_unit = "元"
                open_gain_issue = ((cur_op - issue_p) / issue_p * 100.0) if (issue_p > 0 and cur_op > 0) else 0.0
                observed_val = f"开盘:{cur_op:.2f}元 (较发行价{open_gain_issue:+.1f}%)"

                strong_ref = issue_p * 3.0 # +200%
                double_ref = issue_p * 2.0 # +100%
                if cur_op >= strong_ref: # >= +200% 强势基准
                    judgment = "强"
                    auto_score = 9.0
                    remarks = f"高开>={open_gain_issue:+.0f}%超预期，做多意愿极强"
                elif cur_op >= double_ref: # >= +100% 翻倍
                    judgment = "中"
                    auto_score = 7.0
                    remarks = "开盘落在+100%~+200%中性区间，量价正常"
                else:
                    judgment = "弱"
                    auto_score = 4.0
                    remarks = "开盘低于翻倍线，关注度略显不足"

            elif idx == 1: # 9:40 早盘第一波攻击 (校准 9:40 现价)
                default_p1 = price if price > 0 else (open_price * 1.10 if open_price > 0 else 625.0)
                cur_p1 = float(custom_params.get(n_id, default_p1))
                input_val = cur_p1
                input_unit = "元"
                cur_gain_open = ((cur_p1 - open_price) / open_price * 100.0) if open_price > 0 else 0.0
                observed_val = f"现价:{cur_p1:.2f}元 (较开盘{cur_gain_open:+.1f}%)"
                if cur_gain_open >= 10.0 or cur_p1 >= open_price * 1.10:
                    judgment = "强"
                    auto_score = 9.0
                    remarks = "放量上攻突破开盘价并涨超10%，攻击迅猛"
                elif cur_p1 >= open_price:
                    judgment = "中"
                    auto_score = 6.5
                    remarks = "维持在开盘价上方震荡，等待方向选择"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "跌破开盘价走弱，出现分歧砸盘"

            elif idx == 2: # 10:00 换手质量检验 (校准 10:00 换手率)
                cur_to = float(custom_params.get(n_id, turnover_rate if turnover_rate > 0 else 62.5))
                input_val = cur_to
                input_unit = "%"
                observed_val = f"换手率:{cur_to:.1f}% 金额:{amount_yi:.2f}亿"
                if cur_to >= 15.0 and price >= open_price:
                    judgment = "强"
                    auto_score = 8.5
                    remarks = "换手充沛且价格抬升，承接有力"
                elif cur_to >= 10.0:
                    judgment = "中"
                    auto_score = 6.0
                    remarks = "换手稳步推进，量能温和"
                else:
                    judgment = "弱"
                    auto_score = 4.0
                    remarks = "换手偏低或放量滞涨，警惕承接衰竭"

            elif idx == 3: # 11:00 分歧承接测试 (校准 11:00 价格)
                default_p3 = price if price > 0 else (open_price if open_price > 0 else 625.0)
                cur_p3 = float(custom_params.get(n_id, default_p3))
                input_val = cur_p3
                input_unit = "元"
                vwap_diff = ((cur_p3 - vwap_val) / vwap_val * 100.0) if vwap_val > 0 else 0.0
                observed_val = f"现价:{cur_p3:.2f}元 (偏离均价{vwap_diff:+.1f}%)"
                if cur_p3 >= vwap_val and cur_p3 >= open_price:
                    judgment = "强"
                    auto_score = 8.5
                    remarks = "回落快速收回均线之上，均价线斜率向上"
                elif cur_p3 >= vwap_val * 0.95 or cur_p3 >= open_price * 0.95:
                    judgment = "中"
                    auto_score = 6.0
                    remarks = "贴近分时均线窄幅拉锯，承接尚可"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "跌破分时均线且反抽无力，重心下移"

            elif idx == 4: # 14:00 午后突破验证 (校准 14:00 价格)
                default_p4 = price if price > 0 else (open_price if open_price > 0 else 625.0)
                cur_p4 = float(custom_params.get(n_id, default_p4))
                input_val = cur_p4
                input_unit = "元"
                observed_val = f"现价:{cur_p4:.2f}元 / 上午最高:{high_am:.2f}元"
                if cur_p4 >= high_am and cur_p4 > open_price:
                    judgment = "强"
                    auto_score = 9.0
                    remarks = "午后放量突破上午最高价，趋势延续"
                elif cur_p4 >= vwap_val or cur_p4 >= open_price * 0.90:
                    judgment = "中"
                    auto_score = 6.5
                    remarks = "午后震荡蓄势，未破关键支撑"
                else:
                    judgment = "弱"
                    auto_score = 4.0
                    remarks = "午后持续走弱回落，板块分化"

            elif idx == 5: # 14:50 尾盘抢筹强度 (校准 14:50 价格)
                default_p5 = price if price > 0 else (open_price if open_price > 0 else 625.0)
                cur_p5 = float(custom_params.get(n_id, default_p5))
                input_val = cur_p5
                input_unit = "元"
                cur_ch_ratio = (cur_p5 / max_p) if max_p > 0 else 1.0
                observed_val = f"现价:{cur_p5:.2f}元 (收盘/最高: {cur_ch_ratio*100:.1f}%)"
                if cur_ch_ratio >= 0.95 or (cur_p5 >= max_p * 0.98):
                    judgment = "强"
                    auto_score = 9.5
                    remarks = "尾盘放量抢筹逼近最高价，资金意愿坚决"
                elif cur_ch_ratio >= 0.88:
                    judgment = "中"
                    auto_score = 6.5
                    remarks = "尾盘平稳维持，无恐慌跳水"
                else:
                    judgment = "弱"
                    auto_score = 3.0
                    remarks = "尾盘放量跳水抛售，走弱明显"

            elif idx == 6: # 15:00 收盘结构与锁仓 (校准收盘价)
                default_p6 = price if price > 0 else (open_price if open_price > 0 else 625.0)
                cur_p6 = float(custom_params.get(n_id, default_p6))
                input_val = cur_p6
                input_unit = "元"
                cur_ch_ratio = (cur_p6 / max_p) if max_p > 0 else 1.0
                observed_val = f"收盘:{cur_p6:.2f}元 锁仓比:{cur_ch_ratio*100:.1f}%"
                if cur_ch_ratio >= 0.90 and intensity_ratio >= 2.0:
                    judgment = "强"
                    auto_score = 9.5
                    remarks = "收盘/最高>90%强锁仓，资金强度极高"
                elif cur_ch_ratio >= 0.80 or cur_p6 >= open_price * 0.90:
                    judgment = "中"
                    auto_score = 6.5
                    remarks = "守住大部分涨幅，形态结构健康"
                else:
                    judgment = "弱"
                    auto_score = 3.5
                    remarks = "收盘远低于最高(<80%)，兑现压力沉重"

            # 2. 检查是否有用户人工打分覆盖 (Manual Score Override)
            manual_score = None
            if str(n_id) in state.get("manual_scores", {}):
                manual_score = float(state["manual_scores"][str(n_id)])
            elif str(idx) in state.get("manual_scores", {}):
                manual_score = float(state["manual_scores"][str(idx)])

            final_score = manual_score if manual_score is not None else auto_score
            weighted_score = round(final_score * n_weight, 3)
            total_weighted_score += weighted_score

            node_results.append({
                "node_id": n_id,
                "node_num": nd.get("node_num", f"#{idx+1}"),
                "time_str": n_time,
                "name": n_name,
                "weight": n_weight,
                "weight_pct": f"{int(n_weight*100)}%",
                "focus": nd.get("focus", ""),
                "strong_signals": nd.get("strong_signals", ""),
                "risk_signals": nd.get("risk_signals", ""),
                "observed_val": observed_val,
                "judgment": judgment,
                "auto_score": auto_score,
                "final_score": round(final_score, 1),
                "input_val": input_val,
                "input_unit": input_unit,
                "weighted_score": weighted_score,
                "action_guide": nd.get("action_guide", ""),
                "remarks": remarks,
                "is_active": is_active,
                "is_completed": is_completed
            })

        total_score_rounded = round(total_weighted_score, 2)

        # 3. 动态根据策略中的 grade_levels 判定形态与 T+1 操作建议
        pattern = "未知形态"
        t1_advice = "--"
        pattern_color = "#ffffff"

        grade_levels = spec.get("scoring_rules", {}).get("grade_levels", [])
        if not grade_levels:
            st = self.auto_select_strategy(open_price, code=c_clean)
            if st and "scoring_rules" in st:
                grade_levels = st["scoring_rules"].get("grade_levels", [])

        if grade_levels:
            for gl in grade_levels:
                min_s = float(gl.get("min_score", 0.0))
                if total_score_rounded >= min_s:
                    pattern = gl.get("pattern", "未知形态")
                    t1_advice = gl.get("advice", "--")
                    pattern_color = gl.get("color", "#ffffff")
                    break
        else:
            if total_score_rounded >= 8.0:
                pattern = "A型·超强趋势"
                t1_advice = "★关注竞价接力，强势可参与"
                pattern_color = "#00ff88"
            elif total_score_rounded >= 6.5:
                pattern = "B型·强势换手"
                t1_advice = "★观察次日竞价，回踩不破可试"
                pattern_color = "#38bdf8"
            elif total_score_rounded >= 5.0:
                pattern = "C型·冲高兑现"
                t1_advice = "★谨慎，等二次确认"
                pattern_color = "#ffaa44"
            else:
                pattern = "D/E型·弱势或衰竭"
                t1_advice = "★回避，防回撤"
                pattern_color = "#ff4444"

        # 4. 当前阶段自动解析与实操指引 (Action Guidance Engine)
        if not current_node_info and nodes_def:
            current_node_info = nodes_def[min(current_node_idx, len(nodes_def)-1)]

        active_name = current_node_info.get("name", "盘中阶段") if current_node_info else "盘中监测"
        active_time = current_node_info.get("time_str", clean_t) if current_node_info else clean_t

        # 自动诊断当前情况并给出具体操作动作
        current_status_diagnosis = ""
        action_execution_text = ""

        if clean_t < "09:25":
            current_status_diagnosis = f"当前处于【集合竞价定盘阶段】。发行价 {issue_p:.2f} 元，重点观察 9:25 最终撮合价格与盘口委买厚度。"
            if open_price >= 560.64:
                action_execution_text = "【操作建议】高开达到 +200% 强势基准 (>=560.64元)！开盘后优先按策略B持有观察或准备在较开盘涨10%处挂买一价*1.02卖出首批50%。"
            elif open_price >= 373.76:
                action_execution_text = "【操作建议】开盘落在翻倍区间 (+100%~+200%)。执行策略A标准分批：早盘冲高+10%申报价格笼子卖出50%，若10:00前未冲高则10:00市价卖30%。"
            else:
                action_execution_text = "【操作建议】开盘低于翻倍线 (<373.76元)，按保守档应对，不急于低位割肉，观察开盘是否有放量反弹拉升。"

        elif "09:25" <= clean_t < "09:40":
            current_status_diagnosis = f"当前处于【早盘第一波攻击阶段】。现价 {price:.2f} 元 (较开盘 {gain_from_open:+.1f}%)，最高 {max_p:.2f} 元。"
            if price >= open_price * 1.10:
                action_execution_text = f"【操作建议 🔴 触发卖出】股价较开盘已冲高 >= 10% (目标价 {open_price*1.10:.2f}元)！立即按买一价*1.02限价申报卖出 50% 仓位锁定利润！"
            elif price >= open_price:
                action_execution_text = f"【操作建议 ⏳ 监控冲高】股价在开盘价上方稳健上行，未达+10%卖点(目标 {open_price*1.10:.2f}元)，继续持股盯盘，勿提前抢跑。"
            else:
                action_execution_text = f"【操作建议 ⚠️ 风险防范】股价跌破开盘价 {open_price:.2f} 元！若反抽无力或换手滞涨，需提高警惕准备在10:00执行减仓。"

        elif "09:40" <= clean_t < "10:00":
            current_status_diagnosis = f"当前处于【换手质量检验阶段】。当前换手率 {turnover_rate:.1f}%，成交金额 {amount_yi:.2f} 亿元，分时低点 {min_p:.2f} 元。"
            if clean_t >= "09:59":
                action_execution_text = "【操作建议 🔔 10:00整兜底】若此前冲高50%未触发，在 10:00:00 整按市价果断卖出 30% 仓位执行纪律兜底！"
            elif turnover_rate >= 15.0 and price >= open_price:
                action_execution_text = "【操作建议 ✅ 健康换手】10分钟换手超15%且价格稳步抬升，属于健康充分交换，剩余仓位继续持有等待分歧承接。"
            else:
                action_execution_text = "【操作建议 ⚠️ 观察承接】换手推进中，若出现放量滞涨且低点下移，准备在 10:00 执行兜底减仓。"

        elif "10:00" <= clean_t < "11:30" or "11:30" <= clean_t < "13:00":
            current_status_diagnosis = f"当前处于【分歧承接测试阶段】。现价 {price:.2f} 元，分时均价 VWAP 为 {vwap_val:.2f} 元。"
            if price >= vwap_val:
                action_execution_text = f"【操作建议 🛡️ 守线持有】股价稳稳运行在分时均线 ({vwap_val:.2f}元) 上方，承接良好，剩余仓位安心持有博弈午后突破；若盘中触及+30%临停复牌前挂 Open*1.28 限价单卖30%。"
            else:
                action_execution_text = f"【操作建议 ⚠️ 破线警惕】股价跌破分时均线 ({vwap_val:.2f}元)！若反抽不过均线，建议逢反弹高点主动减仓，严防阴跌。"

        elif "13:00" <= clean_t < "14:30":
            current_status_diagnosis = f"当前处于【午后突破验证阶段】。现价 {price:.2f} 元，上午最高价 {high_am:.2f} 元。"
            if price >= high_am:
                action_execution_text = f"【操作建议 🔥 突破新高】午后成功突破上午最高价 {high_am:.2f} 元！主力做多趋势强化，保持锁仓，关注激光/半导体板块协同性。"
            else:
                action_execution_text = f"【操作建议 ⏳ 震荡观察】午后尚未突破上午高点 ({high_am:.2f}元)，若缩量横盘维持在均线上方可继续观察，破均线则分批派发。"

        elif "14:30" <= clean_t < "14:50":
            current_status_diagnosis = f"当前处于【尾盘抢筹强度检验阶段】。收盘/最高价比例为 {close_high_ratio*100:.1f}%。"
            if close_high_ratio >= 0.90:
                action_execution_text = "【操作建议 🚀 尾盘抢筹】尾盘放量上攻逼近全天最高价！锁仓迹象明显，准备在 14:50 之后保留 10%~20% 底仓过夜博次日溢价。"
            else:
                action_execution_text = "【操作建议 ⚠️ 准备清仓】尾盘回落且收盘/最高 < 90%，不满足留仓条件，准备在 14:50~14:57 尾盘全部市价清仓，不留隔夜仓。"

        else: # 14:50 ~ 15:00
            current_status_diagnosis = f"当前处于【收盘结构与锁仓结算阶段】。综合加权得分 {total_score_rounded:.2f} 分，形态判定【{pattern}】。"
            if close_high_ratio >= 0.90 and total_score_rounded >= 8.0:
                action_execution_text = f"【操作建议 🌙 优质锁仓过夜】收盘/最高 {close_high_ratio*100:.1f}% >= 90% 且综合评分达 {total_score_rounded:.2f} 分(A型)！保留 10% 底仓过夜，次日开盘 9:25 关注竞价接力！"
            else:
                action_execution_text = "【操作建议 🚪 尾盘市价清仓】未达成超强锁仓条件(或评分<8.0)，执行策略A纪律，在 14:57 前按买一价市价全部清仓，规避次日低开风险！"

        eval_result = {
            "code": c_clean,
            "name": spec.get("name", "频准激光"),
            "current_time": clean_t,
            "open_price": open_price,
            "price": price,
            "high_price": max_p,
            "low_price": min_p,
            "vwap": vwap_val,
            "turnover_rate": turnover_rate,
            "amount_yi": amount_yi,
            "intensity_ratio": round(intensity_ratio, 2),
            "close_high_ratio": round(close_high_ratio, 3),
            "gain_from_issue": round(gain_from_issue, 2),
            "gain_from_open": round(gain_from_open, 2),
            "node_results": node_results,
            "total_weighted_score": total_score_rounded,
            "pattern": pattern,
            "t1_advice": t1_advice,
            "pattern_color": pattern_color,
            "active_node_name": active_name,
            "active_node_time": active_time,
            "current_status_diagnosis": current_status_diagnosis,
            "action_execution_text": action_execution_text
        }

        state["timeline_eval_cache"] = eval_result
        return eval_result

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
        评估单个分时/Tick 节点，触发阶梯买卖规则并生成 SignalPoint
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
            if cond_mode != "all" and cond_mode != action_mode:
                continue

            is_triggered = False
            trigger_reason = ""
            
            # 规则条件匹配判断
            if rule_id in ["rule_a1_surge", "rule_pz_surge_10"]:
                if price >= open_price * 1.10:
                    is_triggered = True
                    trigger_reason = f"开盘冲高≥10% (现价:{price:.2f} >= 目标:{open_price*1.10:.2f})"
            elif rule_id == "rule_a1_surge_decelerated":
                if price >= open_price * 1.05:
                    is_triggered = True
                    trigger_reason = f"中性下沿冲高≥5% (现价:{price:.2f} >= 目标:{open_price*1.05:.2f})"
            elif rule_id in ["rule_a1_timeout", "rule_pz_timeout"]:
                if clean_time >= "10:00" and "rule_a1_surge" not in state["triggered_rules"] and "rule_pz_surge_10" not in state["triggered_rules"]:
                    is_triggered = True
                    trigger_reason = "10:00整冲高未触发兜底卖出30%"
            elif rule_id in ["rule_a2_halt_30", "rule_pz_halt_30"]:
                if state["max_price"] >= open_price * 1.30:
                    is_triggered = True
                    trigger_reason = f"+30%临停复牌卖30% (最高:{state['max_price']:.2f} >= 临停阈值:{open_price*1.30:.2f})"
            elif rule_id in ["rule_a3_overnight_check", "rule_pz_overnight_check"]:
                if clean_time >= "14:50" and price >= open_price * 1.20:
                    is_triggered = True
                    trigger_reason = f"14:50仍高出开盘20%(现价:{price:.2f})，保留10%过夜，清仓其余"
            elif rule_id in ["rule_a3_clear_all", "rule_pz_clear_all"]:
                if clean_time >= "14:50" and "rule_a3_overnight_check" not in state["triggered_rules"] and "rule_pz_overnight_check" not in state["triggered_rules"]:
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
                sp.sell_ratio = actual_sell_ratio
                sp.suggested_price = suggested_limit_price
                sp.order_type = order_type
                sp.rule_id = rule_id
                sp.phase_id = phase.get("phase_id")
                
                state["signals"].append(sp)
                generated_signals.append(sp)

        return generated_signals

    def extract_market_snapshot_from_df(self, df: Optional[pd.DataFrame], code: str) -> Dict[str, Any]:
        """
        全自动从实时推送的 DataFrame 中解析当前股票的行情快照
        包含：open, price/trade, high, low, vwap, turnover_rate, amount, volume, buy/bid1, sell/ask1 等
        """
        c_clean = str(code).zfill(6)
        res = {
            "open_price": 0.0,
            "price": 0.0,
            "high_price": 0.0,
            "low_price": 0.0,
            "vwap": 0.0,
            "turnover_rate": 0.0,
            "amount": 0.0,
            "volume": 0.0,
            "bid1_price": 0.0,
            "ask1_price": 0.0,
            "time_str": datetime.now().strftime("%H:%M:%S")
        }

        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return res

        row = None
        # 1. 尝试从 Index 匹配
        if c_clean in df.index:
            row = df.loc[c_clean]
        elif str(code) in df.index:
            row = df.loc[str(code)]
        else:
            # 2. 尝试从 'code' 列匹配
            code_col = next((c for c in ('code', 'symbol', 'sec_code') if c in df.columns), None)
            if code_col:
                matched = df[df[code_col].astype(str).str.contains(c_clean)]
                if not matched.empty:
                    row = matched.iloc[0]

        if row is None:
            return res

        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        try:
            # 开盘价
            res["open_price"] = float(row.get('open', row.get('open_price', row.get('Open', 0.0))))
            
            # 当前价/收盘价
            res["price"] = float(row.get('close', row.get('trade', row.get('price', row.get('Close', 0.0)))))
            
            # 最高价/最低价
            res["high_price"] = float(row.get('high', row.get('high_price', row.get('High', res['price']))))
            res["low_price"] = float(row.get('low', row.get('low_price', row.get('Low', res['price']))))
            
            # 换手率 (%)
            res["turnover_rate"] = float(row.get('turnover', row.get('turnover_rate', row.get('turnover_ratio', 0.0))))
            
            # 成交金额 (元)
            res["amount"] = float(row.get('amount', row.get('money', row.get('Amount', 0.0))))
            
            # 成交量 (股/手)
            res["volume"] = float(row.get('volume', row.get('vol', row.get('Volume', 0.0))))
            
            # 买一价 / 卖一价
            res["bid1_price"] = float(row.get('buy', row.get('bid1', row.get('buy1', res['price']))))
            res["ask1_price"] = float(row.get('sell', row.get('ask1', row.get('sell1', res['price']))))
            
            # 时间字段
            t_val = row.get('time', row.get('timestamp', row.get('datetime', '')))
            if t_val:
                res["time_str"] = str(t_val)[-8:] if len(str(t_val)) >= 8 else str(t_val)

            # 动态计算 VWAP
            if res["amount"] > 0 and res["volume"] > 0:
                # 若 volume 是手，换算为股 (*100)
                unit_vol = res["volume"] if res["volume"] > 1e4 else (res["volume"] * 100)
                if unit_vol > 0:
                    res["vwap"] = round(res["amount"] / unit_vol, 2)
            if res["vwap"] <= 0:
                if res["open_price"] > 0:
                    res["vwap"] = round((res["open_price"] + res["price"] + res["high_price"] + res["low_price"]) / 4.0, 2)
                else:
                    res["vwap"] = res["price"]

        except Exception as e:
            logger.warning(f"Error parsing market row from DataFrame: {e}")

        return res

    def generate_scenario_intraday_df(self, scenario_type: str = "A_SUPER_TREND", code: str = "688826") -> pd.DataFrame:
        """
        生成 8/18 全天分时模拟回测情景数据（9:15 到 15:00 精确时间对齐，共 241 根分时记录）
        情景可选:
        - 'A_SUPER_TREND': A型·超强主升主线 (+336% 超强封板锁仓，得分 > 8.0)
        - 'B_STRONG_TURNOVER': B型·强势换手洗盘 (+189% 强势换手承接，得分 6.5~8.0)
        - 'C_SURGE_AND_CASH': C型·冲高兑现回落 (+105% 冲高回落走弱，得分 5.0~6.5)
        - 'D_WEAK_EXHAUSTION': D/E型·弱势衰竭走弱 (+60% 高开低走破位，得分 < 5.0)
        """
        times = []
        # 1. 集合竞价 09:15 ~ 09:25 (10 min)
        for m in range(15, 26):
            times.append(f"09:{m:02d}")
        # 2. 上午分时 09:30 ~ 11:30 (121 min)
        for h in range(9, 12):
            start_m = 30 if h == 9 else 0
            end_m = 31 if h == 11 else 60
            for m in range(start_m, end_m):
                times.append(f"{h:02d}:{m:02d}")
        # 3. 下午分时 13:00 ~ 15:00 (121 min)
        for h in range(13, 16):
            start_m = 0
            end_m = 1 if h == 15 else 60
            for m in range(start_m, end_m):
                times.append(f"{h:02d}:{m:02d}")

        issue_p = 186.88
        float_shares = 7617800 # 761.78万股
        float_mv = 14.24 * 1e8 # 14.24亿元
        n = len(times)

        records = []
        cum_volume = 0
        cum_amount = 0.0
        running_high = 0.0
        running_low = 99999.0

        if scenario_type == "A_SUPER_TREND":
            open_p = 580.0 # +210% 强势高开
            base_curve = np.linspace(open_p, 815.0, n)
            # 叠加早盘冲高与午后突破脉冲
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:45":
                    p = open_p + (i - 11) * 5.5 + np.sin(i)*2.0 # 冲高至 650
                elif "09:45" < t <= "10:30":
                    p = 640.0 + np.sin(i*0.3)*6.0
                elif "10:30" < t <= "11:30":
                    p = 680.0 + (i - 70) * 1.2 # 逼近 730 (+30% 临停)
                elif "13:00" <= t <= "14:00":
                    p = 750.0 + (i - 130) * 0.8 # 突破上午最高
                elif "14:00" < t <= "14:50":
                    p = 790.0 + (i - 190) * 0.6 # 尾盘抢筹逼近最高 820
                else:
                    p = 815.0 - (i - 230) * 0.2 # 收盘 815 (收盘/最高 99.4%)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.65 / n * (1.5 if t < "10:00" or t > "14:30" else 0.8))
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        elif scenario_type == "B_STRONG_TURNOVER":
            open_p = 490.0 # +162% 乐观下沿
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:40":
                    p = open_p + (i - 11) * 4.0 # 冲高至 530
                elif "09:40" < t <= "10:30":
                    p = 530.0 - (i - 21) * 0.6 # 回踩均线至 505
                elif "10:30" < t <= "11:30":
                    p = 510.0 + np.sin(i*0.2)*4.0
                elif "13:00" <= t <= "14:30":
                    p = 525.0 + (i - 130) * 0.3
                else:
                    p = 540.0 + np.sin(i)*2.0 # 收盘 540
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.62 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        elif scenario_type == "C_SURGE_AND_CASH":
            open_p = 395.0 # +111% 翻倍中性档
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:40":
                    p = open_p + (i - 11) * 4.5 # 冲高至 440 (+11.4% 触发冲高卖出50%)
                elif "09:40" < t <= "11:30":
                    p = 440.0 - (i - 21) * 0.45 # 冲高后逐步回落至 395
                else:
                    p = 395.0 - (i - 130) * 0.12 # 尾盘震荡收 382 (收盘/最高约 87%)
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.52 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        else: # D_WEAK_EXHAUSTION
            open_p = 420.0
            for i, t in enumerate(times):
                if t <= "09:25":
                    p = open_p
                elif "09:30" <= t <= "09:45":
                    p = open_p - (i - 11) * 3.5 # 放量砸盘跌破开盘价
                elif "09:45" < t <= "11:30":
                    p = 370.0 - (i - 26) * 0.5 # 持续阴跌
                else:
                    p = 330.0 - (i - 130) * 0.2 # 尾盘跳水至 310
                
                running_high = max(running_high, p)
                running_low = min(running_low, p)
                step_vol = int(float_shares * 0.42 / n)
                cum_volume += step_vol
                cum_amount += step_vol * p
                vwap = cum_amount / cum_volume if cum_volume > 0 else p
                turnover = (cum_volume / float_shares) * 100.0

                records.append({
                    "time": t, "open": open_p, "close": round(p, 2), "trade": round(p, 2),
                    "high": round(running_high, 2), "low": round(running_low, 2),
                    "vwap": round(vwap, 2), "turnover": round(turnover, 2),
                    "amount": round(cum_amount, 2), "volume": cum_volume,
                    "buy": round(p * 0.998, 2), "sell": round(p * 1.002, 2)
                })

        df_res = pd.DataFrame(records)
        df_res.set_index("time", drop=False, inplace=True)
        return df_res

    def run_full_day_backtest(self, code: str, df_intraday: pd.DataFrame) -> Dict[str, Any]:
        """
        全天分时模拟回测运行器：输入分时 DataFrame，输出完整 7 节点评分演进、阶梯买卖点与最终形态
        """
        c_clean = str(code).zfill(6)
        self.reset_state(c_clean)
        
        all_signals = []
        timeline_history = []
        open_p = 0.0

        for idx, (t_str, row) in enumerate(df_intraday.iterrows()):
            if idx == 0 or open_p <= 0:
                open_p = float(row.get("open", row.get("close", 0.0)))
            
            p = float(row.get("trade", row.get("close", 0.0)))
            h = float(row.get("high", p))
            l = float(row.get("low", p))
            vw = float(row.get("vwap", p))
            to = float(row.get("turnover", 0.0))
            amt = float(row.get("amount", 0.0))
            b1 = float(row.get("buy", p))

            # 1. 评估阶梯交易信号
            sigs = self.evaluate_tick(
                code=c_clean,
                tick_row=row.to_dict(),
                open_price=open_p,
                current_time_str=t_str,
                bid1_price=b1,
                bar_index=idx
            )
            all_signals.extend(sigs)

            # 2. 评估 7 节点时序状态机
            eval_res = self.evaluate_seven_nodes(
                code=c_clean,
                current_time_str=t_str,
                open_price=open_p,
                price=p,
                high_price=h,
                low_price=l,
                vwap=vw,
                turnover_rate=to,
                amount=amt
            )

            timeline_history.append({
                "time": t_str,
                "price": p,
                "score": eval_res.get("total_weighted_score", 0.0),
                "pattern": eval_res.get("pattern", "--"),
                "remaining_ratio": self._get_stock_state(c_clean, open_p).get("remaining_ratio", 1.0)
            })

        state = self._get_stock_state(c_clean, open_p)
        final_eval = self.evaluate_seven_nodes(
            code=c_clean,
            current_time_str="15:00",
            open_price=open_p,
            price=df_intraday.iloc[-1]["close"],
            high_price=df_intraday["high"].max(),
            low_price=df_intraday["low"].min(),
            vwap=df_intraday.iloc[-1]["vwap"],
            turnover_rate=df_intraday.iloc[-1]["turnover"],
            amount=df_intraday.iloc[-1]["amount"]
        )

        return {
            "code": c_clean,
            "open_price": open_p,
            "total_bars": len(df_intraday),
            "signals": all_signals,
            "execution_logs": state.get("execution_logs", []),
            "final_evaluation": final_eval,
            "timeline_history": timeline_history,
            "remaining_ratio": state.get("remaining_ratio", 0.0)
        }

    def reset_state(self, code: Optional[str] = None):
        """重置股票判定状态"""
        if code:
            c_clean = str(code).zfill(6)
            if c_clean in self.rule_state_map:
                del self.rule_state_map[c_clean]
        else:
            self.rule_state_map.clear()


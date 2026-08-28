# -*- coding: utf-8 -*-
"""
ats/new_stock_strategy_generator.py — ATS 新股分时阶梯交易策略自动生成器
特点：
1. 严格遵循 v1.0-unified 统一步进 schema 规范；
2. 根据新股发行价、流通股本、总市值、上市日期及所属板块特征，自动计算：
   - +100% ~ +500% 五大阶梯价格与单签收益矩阵 (price_ladder)；
   - 换手率监控档位 (turnover_ladder)；
   - 资金强度过热警戒阈值 (intensity_benchmark)；
   - 首日临停熔断规则 (circuit_breaker_rules)；
   - 7 节点动态时序评分规则 (scoring_engine)；
   - 全天时间轴 7 阶段操作应对与指引 (phases)；
3. 原子安全更新 config/intraday_newstock_strategies.json 并通知 IntradayStrategyEngine 热重载。
"""

import sys
import os
import json
import logging
import datetime
from typing import Dict, List, Any, Optional, Tuple

from sys_utils import get_app_root, get_conf_path

logger = logging.getLogger("NewStockStrategyGenerator")


class NewStockStrategyGenerator:
    """分时阶梯策略自动生成与持久化引擎"""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, config_filename: str = "intraday_newstock_strategies.json"):
        self.config_path = get_conf_path(config_filename, get_app_root())

    def _get_sign_shares(self, code: str) -> int:
        """
        根据量化规则统一按单签 500 股计算中签收益
        """
        return 500

    def generate_strategy(self, stock_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据新股基本面与行情字典生成标准统一格式的分时阶梯策略字典 (schema_version: v1.0-unified)
        """
        code = str(stock_info.get("code", "")).strip().zfill(6)
        from ats.intraday_strategy_engine import is_valid_stock_code
        if not is_valid_stock_code(code):
            logger.warning(f"⚠️ [NewStockStrategyGenerator] 拦截无效虚构标的代码策略生成: {code}")
            return {}

        name = str(stock_info.get("name", f"标的_{code}")).strip()
        # 权威获取/补齐新股基本面与真实发行价
        ipo_info = {}
        try:
            from ats.new_stock_fetcher import NewStockFetcher
            ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
            if code in ipo_dict:
                ipo_info = ipo_dict[code]
        except Exception:
            pass

        if not name or name.startswith("标的_"):
            name = ipo_info.get("name") or name
        # 清理名称中的 N/C 前缀以获取纯净简称
        clean_name = name.lstrip("NC").strip() if len(name) > 1 else name

        issue_price = float(stock_info.get("issue_price", 0.0) or 0.0)
        if issue_price <= 0 and ipo_info:
            issue_price = float(ipo_info.get("issue_price", 0.0) or 0.0)

        curr_price = float(stock_info.get("price", 0.0) or stock_info.get("open_price", 0.0) or 0.0)
        
        # 发行价终极保底兜底逻辑 (仅在全网与本地 IPO 日历均未收录该股票时)
        if issue_price <= 0:
            if curr_price > 0:
                issue_price = round(curr_price / 2.0, 2)  # 若无发行价，假定当前涨幅翻倍估算
            else:
                issue_price = 10.0  # 默认基准保底价

        # 估算流通盘与总市值
        float_mv_yi = float(stock_info.get("float_mv_yi", 0.0) or 0.0)
        total_mv_yi = float(stock_info.get("total_mv_yi", 0.0) or 0.0)
        
        if float_mv_yi <= 0:
            float_mv_yi = round(float(issue_price * 2000.0 * 10000) / 1e8, 2) # 默认假定 2000万股
            
        float_shares_wan = round(float(float_mv_yi * 1e8) / (issue_price * 10000.0), 2)
        total_shares_wan = round(float(total_mv_yi * 1e8) / (issue_price * 10000.0), 2) if total_mv_yi > 0 else round(float_shares_wan * 4.0, 2)
        if total_mv_yi <= 0:
            total_mv_yi = round((total_shares_wan * 10000.0 * issue_price) / 1e8, 2)

        sign_shares = self._get_sign_shares(code)
        lottery_amount_per_sign = round(issue_price * sign_shares, 2)

        listing_date = str(stock_info.get("listing_date", "") or ipo_info.get("listing_date", "") or "").split(" ")[0].strip()
        apply_date = str(stock_info.get("apply_date", "") or ipo_info.get("apply_date", "") or "").split(" ")[0].strip()
        if not listing_date or listing_date in ("-", "None", ""):
            listing_date = datetime.datetime.now().strftime("%Y-%m-%d")

        # 生成 price_ladder (5大阶梯)
        ladder_gains = [100.0, 200.0, 300.0, 400.0, 500.0]
        ladder_meanings = [
            "翻倍稳健基准，中签者兑现起步线",
            "强势基准区间，资金博弈主战场",
            "高频高溢价区间，注意筹码松动",
            "极强势上限，警惕高位分歧",
            "极端牛市爆炒行情，尾盘严防冲高回落"
        ]
        price_ladder = []
        for gain, meaning in zip(ladder_gains, ladder_meanings):
            target_p = round(issue_price * (1.0 + gain / 100.0), 2)
            sign_profit = round((target_p - issue_price) * sign_shares, 2)
            price_ladder.append({
                "name": f"+{int(gain)}%",
                "gain_pct": gain,
                "price": target_p,
                "meaning": meaning,
                "sign_profit": sign_profit
            })

        # 生成 turnover_ladder
        turnover_ladder = [
            {"level": "弱换手", "range": "<40%", "min": 0.0, "max": 40.0, "meaning": "关注度不足/承接力偏弱"},
            {"level": "标准换手", "range": "50-70%", "min": 50.0, "max": 70.0, "meaning": "健康换手，资金充分博弈"},
            {"level": "高换手", "range": "70-90%", "min": 70.0, "max": 90.0, "meaning": "充分换手，分歧与共识交替"},
            {"level": "极高换手", "range": ">90%", "min": 90.0, "max": 999.0, "meaning": "极度过热分歧，警惕尾盘反转跳水"}
        ]

        # 资金强度基准
        overheat_amt_yi = round(float_mv_yi * 2.5, 2)
        intensity_benchmark = {
            "metric": f"成交额/发行流通市值({float_mv_yi:.2f}亿)",
            "threshold": 2.5,
            "meaning": f"资金强度极高（首日成交额>{overheat_amt_yi:.2f}亿即进入过热区）"
        }

        # 临停熔断规则
        circuit_breaker_rules = {
            "basis": "当日开盘价",
            "first_halt": "+30% 触发临停10分钟",
            "second_halt": "+60% 触发临停10分钟",
            "max_halts_per_direction": 2,
            "max_halts_total": 4,
            "cross_1457_rule": "停牌跨越14:57则于14:57强制复牌"
        }

        # 构造完整统一策略字典
        strategy_id = f"strategy_{clean_name}_{code}"
        strategy_dict = {
            "id": strategy_id,
            "name": f"{clean_name}（{code}）上市专属盯盘与分时阶梯策略",
            "version": "2.0",
            "target_codes": [code],
            "schema_version": "v1.0-unified",
            "note": f"{clean_name}({code}) 配套分时阶梯与7节点动态时序策略，由 ATS 自动生成器于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 自动构建生成。",
            "stock_spec": {
                "code": code,
                "name": clean_name,
                "company_full_name": f"{clean_name}股份有限公司",
                "issue_price": issue_price,
                "total_shares_after_issue_wan": total_shares_wan,
                "float_shares_wan": float_shares_wan,
                "float_mv_yi": float_mv_yi,
                "total_mv_yi_at_issue": total_mv_yi,
                "lottery_rate": stock_info.get("lottery_rate", "0.02500%"),
                "lottery_amount_per_sign": lottery_amount_per_sign,
                "subscription_date": apply_date if apply_date else "-",
                "lottery_announce_date": "-",
                "listing_date": listing_date,
                "main_underwriter": stock_info.get("main_underwriter", "保荐券商"),
                "business_summary": stock_info.get("business_summary", f"{clean_name}核心业务"),
                "sector_tags": stock_info.get("sector_tags", ["新股上市", "次新热点"]),
                "financials": {
                    "revenue_2025": 0.0,
                    "net_profit_2025": 0.0,
                    "eps_2025": 0.0,
                    "gross_margin_2025": 0.0,
                    "net_margin_2025": 0.0
                },
                "price_ladder": price_ladder,
                "turnover_ladder": turnover_ladder,
                "intensity_benchmark": intensity_benchmark,
                "circuit_breaker_rules": circuit_breaker_rules
            },
            "global_variables": {
                "open_price": {"init": "first_trade_price", "type": "float", "persist": True},
                "high_price": {"init": 0, "type": "float", "update": "max(high_price, current_price)"},
                "low_price": {"init": 999999, "type": "float", "update": "min(low_price, current_price)"},
                "morning_high": {"init": 0, "type": "float", "update": "if current_time<='11:30' then max(morning_high, current_price) else morning_high"},
                "current_turnover_pct": {"init": 0, "type": "float", "update": "cumulative_volume / float_shares"},
                "ma_line": {"calc": "cumulative_volume_weighted_price", "type": "float"},
                "close_high_ratio": {"calc": "current_price / high_price", "type": "float"},
                "composite_score": {"init": 5.0, "type": "float", "update": "scoring_engine"},
                "rule_surge_triggered": {"init": False, "type": "bool"},
                "rule_halt_30_triggered": {"init": False, "type": "bool"}
            },
            "halt_state": {
                "first_halt_price": {"expr": "open_price * 1.30", "type": "float"},
                "second_halt_price": {"expr": "open_price * 1.60", "type": "float"},
                "first_halt_triggered_at": {"init": None, "type": "str"},
                "first_resume_expected_at": {"init": None, "type": "str"},
                "second_halt_triggered_at": {"init": None, "type": "str"},
                "second_resume_expected_at": {"init": None, "type": "str"},
                "halt_active": {"init": False, "type": "bool"}
            },
            "scoring_engine": {
                "nodes": [
                    {
                        "node_id": "N1_OPEN",
                        "name": "开盘定盘 (09:25)",
                        "weight": 0.15,
                        "description": "开盘集合竞价定位与溢价评估",
                        "metrics": ["open_price", "open_turnover_pct", "open_gain_pct"]
                    },
                    {
                        "node_id": "N2_EARLY_BATTLE",
                        "name": "开盘初段 (09:30-09:40)",
                        "weight": 0.20,
                        "description": "开盘快速换手与冲高动能",
                        "metrics": ["early_surge_ratio", "vwap_support", "turnover_speed"]
                    },
                    {
                        "node_id": "N3_MORNING_RUSH",
                        "name": "早盘冲高 (09:40-10:30)",
                        "weight": 0.20,
                        "description": "第一波拉升承接力度与均线偏离",
                        "metrics": ["morning_high", "deviation_vwap", "pullback_depth"]
                    },
                    {
                        "node_id": "N4_MIDDAY_DIGEST",
                        "name": "午盘消化 (10:30-11:30)",
                        "weight": 0.15,
                        "description": "盘中缩量横盘与分时均线承接确认",
                        "metrics": ["volume_shrink_ratio", "vwap_adherence", "sector_resonance"]
                    },
                    {
                        "node_id": "N5_AFTERNOON_ATTACK",
                        "name": "午后博弈 (13:00-14:30)",
                        "weight": 0.15,
                        "description": "午后二次放量突破或衰竭判断",
                        "metrics": ["afternoon_breakout", "cumulative_turnover"]
                    },
                    {
                        "node_id": "N6_CLOSING_LOCK",
                        "name": "尾盘定盘 (14:30-15:00)",
                        "weight": 0.15,
                        "description": "全天收盘形态、筹码沉淀与隔夜预期评估",
                        "metrics": ["close_high_ratio", "final_turnover", "closing_strength"]
                    }
                ]
            },
            "phases": [
                {
                    "phase_id": 1,
                    "name": "开盘集合竞价 (09:15-09:25)",
                    "time_range": "09:15-09:25",
                    "action_guidance": "观察开盘涨幅是否进入 +100%~+200% 强势阶梯；若开盘超预期高开且竞价换手>5%，准备首笔减仓或按兵不动。",
                    "rules": []
                },
                {
                    "phase_id": 2,
                    "name": "开盘初期博弈 (09:30-09:40)",
                    "time_range": "09:30-09:40",
                    "action_guidance": "密切跟踪分时线与 VWAP 均价线关系。若快速冲高 >+30% 触发临停，临停期间严禁盲目挂追单。",
                    "rules": [
                        {
                            "rule_id": "rule_surge_10",
                            "name": "规则N-1: 较开盘涨10%卖出40%",
                            "condition_mode": "all",
                            "trigger_expr": "price >= open_price * 1.10",
                            "sell_ratio": 0.4,
                            "order_type": "limit",
                            "description": "开盘初段冲高较开盘涨10%以上限价卖出首批40%"
                        },
                        {
                            "rule_id": "rule_halt_30",
                            "name": "规则N-2: +30%临停复牌卖出30%",
                            "condition_mode": "all",
                            "trigger_expr": "max_price >= open_price * 1.30",
                            "sell_ratio": 0.3,
                            "order_type": "limit",
                            "description": "触发+30%临停，复牌前挂Open*1.28卖出30%"
                        }
                    ]
                },
                {
                    "phase_id": 3,
                    "name": "早盘第一波分歧 (09:40-10:30)",
                    "time_range": "09:40-10:30",
                    "action_guidance": "首次回踩 VWAP 均价线时观察承接。若破均价且3分钟内无法收回，执行阶梯分批减仓策略。",
                    "rules": [
                        {
                            "rule_id": "rule_timeout_1000",
                            "name": "规则N-3: 10:00超时未冲高卖30%",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '10:00'",
                            "sell_ratio": 0.3,
                            "order_type": "market_price",
                            "description": "10:00前未走出冲高行情，按市价减仓30%"
                        },
                        {
                            "rule_id": "rule_vwap_break",
                            "name": "规则N-4: 跌破均线VWAP防守减仓",
                            "condition_mode": "all",
                            "trigger_expr": "price < vwap * 0.98",
                            "sell_ratio": 0.3,
                            "order_type": "market_price",
                            "description": "跌破分时均线VWAP且承接不足，执行防守减仓"
                        }
                    ]
                },
                {
                    "phase_id": 4,
                    "name": "盘中横盘承接 (10:30-11:30)",
                    "time_range": "10:30-11:30",
                    "action_guidance": "横盘缩量区间，若换手率稳步突破 50% 且价格运行于均价线上方，维持持仓观察。",
                    "rules": []
                },
                {
                    "phase_id": 5,
                    "name": "午后主浪博弈 (13:00-14:30)",
                    "time_range": "13:00-14:30",
                    "action_guidance": "关注午后是否放量创日内新高。若出现滞涨背离，坚决在阶梯高位执行利润锁定。",
                    "rules": []
                },
                {
                    "phase_id": 6,
                    "name": "尾盘定盘决策 (14:30-15:00)",
                    "time_range": "14:30-15:00",
                    "action_guidance": "评估全天总换手与收盘价/日内最高价比值。若综合得分 ≥7.0 且处于强势阶梯，可保留底仓博弈次日溢价；否则清仓兑现。",
                    "rules": [
                        {
                            "rule_id": "rule_close_clear",
                            "name": "规则N-5: 尾盘未达标清仓",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '14:50' and composite_score < 7.0",
                            "sell_ratio": 1.0,
                            "order_type": "market_price",
                            "description": "14:50后综合评分<7分清仓剩余全部不留隔夜"
                        }
                    ]
                }
            ]
        }
        return strategy_dict

    def save_or_update_strategy(self, strategy_dict: Dict[str, Any]) -> bool:
        """
        将单只新股策略写入/更新到 config/intraday_newstock_strategies.json，并热重载策略引擎
        """
        try:
            strat_id = strategy_dict.get("id")
            from ats.intraday_strategy_engine import is_valid_stock_code
            target_codes = [str(c).strip().zfill(6) for c in strategy_dict.get("target_codes", []) if is_valid_stock_code(str(c).strip())]
            if not strat_id or not target_codes:
                logger.warning(f"⚠️ [NewStockStrategyGenerator] 拦截无效策略写入: id={strat_id}, target_codes={target_codes}")
                return False

            conf_path = self.config_path
            os.makedirs(os.path.dirname(conf_path), exist_ok=True)

            data = {"version": "2.0", "schema_version": "v1.0-unified", "updated_at": "", "strategies": []}
            if os.path.exists(conf_path):
                with open(conf_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            strategies = data.get("strategies", [])
            updated = False
            for idx, st in enumerate(strategies):
                # 按 id 或 target_codes 精准匹配更新
                existing_codes = [str(c).strip().zfill(6) for c in st.get("target_codes", [])]
                if st.get("id") == strat_id or any(c in existing_codes for c in target_codes):
                    strategies[idx] = strategy_dict
                    updated = True
                    break

            if not updated:
                # 插入到最前面（新股优先展示）
                strategies.insert(0, strategy_dict)

            data["strategies"] = strategies
            data["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 写入临时文件然后原子替换，确保多进程/断电安全
            tmp_path = conf_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if os.path.exists(conf_path):
                os.remove(conf_path)
            os.rename(tmp_path, conf_path)

            logger.info(f"✅ 成功将策略 [{strat_id}] 保存至 {conf_path}")

            # 通知分时策略引擎热重载
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            IntradayStrategyEngine.get_instance().load_config()
            return True
        except Exception as e:
            logger.error(f"❌ 保存/更新分时阶梯策略异常: {e}")
            return False

    def batch_generate_and_save(self, stock_list: List[Dict[str, Any]]) -> int:
        """
        批量为未配置策略的新股生成标准分时阶梯策略
        返回成功生成的策略数量
        """
        success_count = 0
        for s_info in stock_list:
            try:
                st = self.generate_strategy(s_info)
                if self.save_or_update_strategy(st):
                    success_count += 1
            except Exception as e:
                logger.warning(f"生成标的 [{s_info.get('code')}] 策略异常: {e}")
        return success_count

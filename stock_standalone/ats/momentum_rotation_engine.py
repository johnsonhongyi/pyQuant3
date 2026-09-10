# -*- coding: utf-8 -*-
"""
ats/momentum_rotation_engine.py — T+1 满仓轮动切换·强势快速开平仓中枢 (SSOT)
=============================================================================
核心业务定位：
针对量化交易中“东一榔头西一棒子”、策略单日产生 100+ 只杂毛股导致无从下手、以及
“满仓轮动切换、不空仓、持续挖掘潜能”的极致资金高周转复利诉求。

双核主力起爆特质判决体系 (SSOT 闭环验证)：
=============================================================================
【模式 1: 梯量大阳阶梯推进型】(以 301176 逸豪新材 / 688135 利扬芯片 为代表)
1. 振幅扩张度 (avg_amp_3d >= 5.5% 且当日振幅 >= 5.0%)；
2. 温和梯量柱 (当日量比 vol_ratio 在 [1.15, 3.20] 黄金区间)；
3. 通道下轨黄金伏击位 (ch_pos 在 [5.0%, 60.0%] 之间，盈亏比极高)；
4. 阶梯台阶跳跃与均价洗盘容差 (close >= nclose * 0.985，保全尾盘洗盘黄金买点)。

【模式 2: 异动冲高回踩·两日 VWAP 高位有效震荡微升型】(以 603318 水发燃气 为代表)
1. T-2 日冲高异动试盘留下上影线，散户追高被套；但收盘死守 VWAP 机构成本线；
2. T-1 日分时下杀震荡走低 (诱空恐慌)，但成交量极度萎缩 (vol < 0.90 * lastv1d，地量洗盘)；
3. 两日加权均价 VWAP 呈【有效高位震荡微升】(nclose >= last_nclose1d * 0.995 且 <= last_nclose1d * 1.035)；
4. 通道下轨黄金支撑企稳 (ch_pos 在 [5.0%, 55.0%])，低点不创新低 (low >= lastl1d * 0.985)；
5. 次日弱转强跳空高开或早盘直线反包涨停！
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Union

try:
    from logger_utils import LoggerFactory
    logger = LoggerFactory.getLogger("MomentumRotationEngine")
except Exception:
    import logging
    logger = logging.getLogger("MomentumRotationEngine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MomentumRotationEngine:
    """T+1 满仓轮动强势快速开平仓中枢 (SSOT)"""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        """安全浮点数转换，防止 None、NaN 崩溃"""
        if val is None:
            return default
        try:
            f = float(val)
            return default if (math.isnan(f) or math.isinf(f)) else f
        except (ValueError, TypeError):
            return default

    def evaluate_stock_rotation(self, row: Union[Dict[str, Any], pd.Series]) -> Dict[str, Any]:
        """
        对单只标的进行 T+1 满仓轮动潜能评分与开平仓决策 (双核引擎)
        
        :param row: 包含日线/分时宽表指标的字典或 pd.Series
        :return: 包含 rotation_score, pattern_type, signal, advice, entry_range, stop_loss, target 等决策字典
        """
        code = str(row.get("code", row.get("symbol", "")))
        name = str(row.get("name", code))
        close_p = self._safe_float(row.get("close", row.get("trade", row.get("now", 0.0))))
        open_p = self._safe_float(row.get("open", 0.0))
        high_p = self._safe_float(row.get("high", close_p))
        low_p = self._safe_float(row.get("low", close_p))
        
        lastp1d = self._safe_float(row.get("lastp1d", row.get("lastp", row.get("llastp", 0.0))))
        lasto1d = self._safe_float(row.get("lasto1d", row.get("lopen", 0.0)))
        lasth1d = self._safe_float(row.get("lasth1d", row.get("lhigh", 0.0)))
        lasth2d = self._safe_float(row.get("lasth2d", 0.0))
        lasth3d = self._safe_float(row.get("lasth3d", 0.0))
        
        lastl1d = self._safe_float(row.get("lastl1d", row.get("llow", 0.0)))
        lastl2d = self._safe_float(row.get("lastl2d", 0.0))
        lastl3d = self._safe_float(row.get("lastl3d", 0.0))
        
        vol = self._safe_float(row.get("vol", row.get("volume", 0.0)))
        lastv1d = self._safe_float(row.get("lastv1d", row.get("lvol", 0.0)))
        lastv2d = self._safe_float(row.get("lastv2d", 0.0))
        
        nclose = self._safe_float(row.get("nclose", row.get("vwap", close_p)))
        last_nclose1d = self._safe_float(row.get("last_nclose1d", row.get("vwap1d", row.get("last_vwap1d", 0.0))))
        td_sell = self._safe_float(row.get("td_sell", 0.0))
        
        # 通道字段
        ch_dir = int(self._safe_float(row.get("ch_dir", 0.0)))
        ch_slope_deg = self._safe_float(row.get("ch_slope_deg", 0.0))
        ch_pos = self._safe_float(row.get("ch_pos", 50.0))
        ch_lower = self._safe_float(row.get("ch_lower", 0.0))
        ch_mid = self._safe_float(row.get("ch_mid", 0.0))
        ch_upper = self._safe_float(row.get("ch_upper", 0.0))
        ch_supp_price = self._safe_float(row.get("ch_supp_price", 0.0))

        if close_p <= 0.01:
            return {
                "code": code, "name": name, "rotation_score": 0.0,
                "is_qualified": False, "signal": "INVALID_DATA",
                "reason": "价格无效"
            }

        # ---------------------------------------------------------------------
        # 1. 共同基准底座 (通道健康度与下轨黄金伏击位)
        # ---------------------------------------------------------------------
        is_ascending_channel = (ch_dir == 1) and (ch_slope_deg >= 3.0)
        
        # 通道位置评分
        if not is_ascending_channel:
            score_pos = 5.0 if ch_pos < 40.0 else 0.0
        else:
            if 5.0 <= ch_pos <= 45.0:
                score_pos = 25.0
            elif 45.0 < ch_pos <= 60.0:
                score_pos = 20.0
            elif 60.0 < ch_pos <= 80.0:
                score_pos = 10.0
            elif ch_pos < 5.0:
                score_pos = 18.0
            else:
                score_pos = 0.0

        if ch_supp_price > 0.01 and abs(close_p - ch_supp_price) / ch_supp_price <= 0.025:
            score_pos = min(25.0, score_pos + 3.0)

        # ---------------------------------------------------------------------
        # 2. 双核形态模式识别 (Pattern 1 vs Pattern 2)
        # ---------------------------------------------------------------------
        amp_today = ((high_p - low_p) / low_p * 100.0) if low_p > 0.01 else 0.0
        truer = self._safe_float(row.get("truer", amp_today))
        truer1d = self._safe_float(row.get("truer1d", amp_today))
        avg_amp = max(amp_today, (truer + truer1d) / 2.0 if truer1d > 0 else amp_today)

        vol_ratio = (vol / lastv1d) if lastv1d > 0.01 else 1.0
        sys_vr = self._safe_float(row.get("vol_ratio", 0.0))
        if sys_vr > 0.01:
            vol_ratio = sys_vr

        # 模式 2 (水发燃气型) 核心指标:
        # 两日加权均价 VWAP 平台有效高位微升: nclose 相比 last_nclose1d 在 [-0.5%, +3.8%]
        vwap_platform_rising = False
        if last_nclose1d > 0.01 and nclose > 0.01:
            vwap_diff_pct = (nclose - last_nclose1d) / last_nclose1d * 100.0
            vwap_platform_rising = (-0.6 <= vwap_diff_pct <= 4.0)

        # 模式 2 判定: 前日冲高试盘 (lasth1d > lasth2d) + 当日缩量洗盘 (vol_ratio <= 0.95) + VWAP平台微升 + 低点不破
        is_pattern_2 = (
            vwap_platform_rising and (vol_ratio <= 0.95) and 
            (lasth1d >= lasth2d * 0.99) and (low_p >= lastl1d * 0.985) and
            (5.0 <= ch_pos <= 60.0)
        )

        # 模式 1 (逸豪新材型) 判定: 梯量温和放大 + 连阳或台阶抬升
        is_pattern_1 = (
            (1.15 <= vol_ratio <= 3.20) and 
            (close_p >= lastp1d * 0.995 or open_p >= lasto1d * 0.995) and
            (lasth1d >= lasth2d * 0.99) and (lastl1d >= lastl2d * 0.99) and
            (close_p >= nclose * 0.985)
        )

        # ---------------------------------------------------------------------
        # 3. 四维立体评分计算
        # ---------------------------------------------------------------------
        if is_pattern_2:
            # 【模式 2: 水发燃气型】评分体系
            pattern_type = "PATTERN_2_VWAP_PLATFORM_REVERSAL"
            # 振幅收敛进入变盘临界点
            score_amp = 25.0 if avg_amp >= 3.5 else 18.0
            # 地量洗盘量能得分
            if 0.60 <= vol_ratio <= 0.90:
                score_vol = 25.0 # 极佳地量洗盘
            elif vol_ratio < 0.60:
                score_vol = 18.0
            else:
                score_vol = 20.0
            # 台阶与VWAP得分
            score_step = 25.0
        else:
            # 【模式 1: 逸豪新材型】评分体系
            pattern_type = "PATTERN_1_STEPPED_VOLUME_LAUNCH"
            # 振幅扩张度
            if avg_amp < 3.0:
                score_amp = 0.0
            elif avg_amp >= 8.5:
                score_amp = 25.0
            else:
                score_amp = 10.0 + (avg_amp - 3.0) / 5.5 * 15.0

            # 梯量柱健康度
            if 1.15 <= vol_ratio <= 2.80:
                score_vol = 25.0
            elif 1.00 <= vol_ratio < 1.15:
                score_vol = 15.0
            elif 2.80 < vol_ratio <= 3.80:
                score_vol = 18.0
            elif vol_ratio > 3.80:
                score_vol = max(0.0, 25.0 - (vol_ratio - 3.80) * 10.0)
            else:
                score_vol = max(0.0, vol_ratio * 12.0)

            # 台阶与均价容差得分
            score_step = 0.0
            has_higher_lows = (lastl1d >= lastl2d * 0.99) if lastl2d > 0 else True
            has_higher_highs = (lasth1d >= lasth2d * 0.99) if lasth2d > 0 else True
            if has_higher_lows and has_higher_highs:
                score_step += 10.0
            elif has_higher_lows or has_higher_highs:
                score_step += 5.0

            if (close_p >= lastp1d * 0.995) or (open_p >= lasto1d * 0.995):
                score_step += 5.0

            if close_p >= (nclose * 0.985):
                score_step += 7.0

            if td_sell < 5.0:
                score_step += 3.0

        total_score = round(score_amp + score_vol + score_pos + score_step, 1)

        # ---------------------------------------------------------------------
        # 4. 硬防线一票否决 (三大安全护城河: 严杀 002999 式避雷针出货)
        # ---------------------------------------------------------------------
        veto = False
        veto_reasons = []
        upper_shadow = ((high_p - close_p) / close_p * 100.0) if close_p > 0.01 else 0.0
        
        # 4.1 九转高位见顶衰竭序列 (td_sell >= 7 严厉一票否决, 002999 打满 9)
        if td_sell >= 7.0:
            veto = True
            veto_reasons.append(f"九转高位卖点见顶衰竭 (td_sell={td_sell})")

        # 4.2 高位放量避雷针长上影线 (上影线 >= 5.5% 且处于高位中枢, 002999 上影 8.9%)
        if upper_shadow >= 5.5 and (ch_pos >= 45.0 or high_p >= ch_mid):
            veto = True
            veto_reasons.append(f"高位长上影避雷针出货 (上影={upper_shadow:.1f}%)")

        # 4.3 盘中触碰通道上轨天花板承压回落 (002999 冲到 8.10 上轨铁顶)
        if ch_upper > 0.01 and high_p >= ch_upper * 0.985 and close_p < high_p * 0.96:
            veto = True
            veto_reasons.append("盘中触及通道上轨铁顶承压大幅回落")

        # 4.4 常规破位与死水拦截
        if ch_lower > 0.01 and close_p < ch_lower * 0.97:
            veto = True
            veto_reasons.append("严重破通道下轨")
        if ch_pos > 80.0:
            veto = True
            veto_reasons.append("通道位置 > 80% 超买追高")
        if vol_ratio > 4.5:
            veto = True
            veto_reasons.append("脉冲天量对倒风险")
        if avg_amp < 2.0 and not is_pattern_2:
            veto = True
            veto_reasons.append("无振幅织布死水")

        if veto:
            total_score = min(total_score, 45.0)

        is_qualified = (total_score >= 68.0) and not veto

        # ---------------------------------------------------------------------
        # 5. 交易指令与开平仓路线图
        # ---------------------------------------------------------------------
        entry_low = round(close_p * 0.99, 2)
        entry_high = round(close_p * 1.01, 2)
        base_low = min(low_p, lastl1d) if lastl1d > 0 else low_p
        stop_loss = round(max(ch_lower * 0.98, base_low * 0.98), 2)
        target_price = round(ch_upper if ch_upper > close_p else close_p * 1.15, 2)

        if is_pattern_2 and total_score >= 70.0:
            signal = "🚀 平台微升·地量洗盘反包"
            advice = "T-2冲高被套试盘，T-1地量洗盘且两日VWAP平台微升，主力暗中托底，次日极大概率弱转强反包！"
        elif total_score >= 80.0:
            signal = "🚀 极品起爆·满仓伏击"
            advice = "T日尾盘绝佳买点，振幅活跃且温和梯量，下轨企稳次日极高确定性爆发！"
        elif total_score >= 68.0:
            signal = "🎯 梯量突破·蓄势主升"
            advice = "多头结构良好，低点台阶持续抬升，可满仓配置或顺势跟进。"
        elif ch_pos >= 80.0:
            signal = "⚠️ 高位风险·分批落袋"
            advice = "逼近通道上轨阻力区，严禁追高，持股者逢高平仓获利换股。"
        else:
            signal = "⏸️ 观望蓄势·能量不足"
            advice = "波动率或量能未达起爆临界点，不建议满仓介入。"

        return {
            "code": code,
            "name": name,
            "close": close_p,
            "rotation_score": total_score,
            "pattern_type": pattern_type,
            "is_qualified": is_qualified,
            "score_breakdown": {
                "amplitude": round(score_amp, 1),
                "volume": round(score_vol, 1),
                "position": round(score_pos, 1),
                "stepping": round(score_step, 1)
            },
            "metrics": {
                "avg_amp_3d": round(avg_amp, 2),
                "vol_ratio": round(vol_ratio, 2),
                "ch_pos": round(ch_pos, 2),
                "ch_slope_deg": round(ch_slope_deg, 2),
                "vwap_diff_pct": round((nclose - last_nclose1d)/last_nclose1d*100, 2) if last_nclose1d > 0 else 0.0,
                "nclose_ratio": round(close_p / nclose, 3) if nclose > 0 else 1.0
            },
            "signal": signal,
            "advice": advice,
            "entry_range": f"{entry_low:.2f} ~ {entry_high:.2f}",
            "stop_loss": stop_loss,
            "target_price": target_price,
            "veto": veto,
            "veto_reasons": veto_reasons
        }

    def filter_and_rank_universe(
        self, 
        df_universe: pd.DataFrame, 
        top_n: int = 5,
        min_score: float = 65.0
    ) -> pd.DataFrame:
        if df_universe is None or df_universe.empty:
            empty_df = pd.DataFrame()
            empty_df.attrs["__error__"] = {
                "code": "EMPTY_UNIVERSE",
                "exc_type": "ValueError",
                "exc_msg": "输入的股票池数据为空"
            }
            return empty_df

        results = []
        for idx, row in df_universe.iterrows():
            eval_res = self.evaluate_stock_rotation(row)
            if eval_res.get("is_qualified", False) and eval_res.get("rotation_score", 0) >= min_score:
                results.append({
                    "code": eval_res["code"],
                    "name": eval_res["name"],
                    "close": eval_res["close"],
                    "rotation_score": eval_res["rotation_score"],
                    "pattern_type": eval_res.get("pattern_type", ""),
                    "signal": eval_res["signal"],
                    "avg_amp_3d": eval_res["metrics"]["avg_amp_3d"],
                    "vol_ratio": eval_res["metrics"]["vol_ratio"],
                    "ch_pos": eval_res["metrics"]["ch_pos"],
                    "ch_slope_deg": eval_res["metrics"]["ch_slope_deg"],
                    "entry_range": eval_res["entry_range"],
                    "stop_loss": eval_res["stop_loss"],
                    "target_price": eval_res["target_price"],
                    "advice": eval_res["advice"]
                })

        if not results:
            df_out = pd.DataFrame(columns=[
                "code", "name", "close", "rotation_score", "pattern_type", "signal", 
                "avg_amp_3d", "vol_ratio", "ch_pos", "entry_range", "stop_loss", "target_price"
            ])
            return df_out

        df_ranked = pd.DataFrame(results).sort_values(by="rotation_score", ascending=False).reset_index(drop=True)
        return df_ranked.head(top_n)


rotation_engine = MomentumRotationEngine.get_instance()

def evaluate_momentum_rotation(row: Union[Dict[str, Any], pd.Series]) -> Dict[str, Any]:
    return rotation_engine.evaluate_stock_rotation(row)

def get_top_rotation_candidates(df_universe: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    return rotation_engine.filter_and_rank_universe(df_universe, top_n=top_n)

# -*- coding: utf-8 -*-
"""
ats/multi_period_channel_strategy.py — 多周期通道与支撑线共振量化策略引擎
=============================================================================
核心职责：
1. 对齐通达信【GG通道走势(60,1,5.6,60,8,8,6)】指标及系统自适应通道算法；
2. 针对 5 大周期 (d, 2d, 3d, w, m) 分别测算：
   - 通道三轨 (ch_upper, ch_mid, ch_lower)
   - 动态支撑线 (supp_price)
   - 反转确认位 (reversal_price)
   - 支撑线上判定 (close >= supp_price * 0.995)
   - 偏离度 (dist_to_supp_pct) 与通道倾角 (slope_deg)
3. 多周期支撑线上共振判决模型 (Resonance Model)：
   - 统计处于支撑线之上的周期数量 (above_support_count)；
   - 识别大级别支撑向小级别层层垫高的发散态势；
   - 输出统一量化评分 (score: 0~100)、形态定性 (pattern_name) 与实战买入建议 (buy_suggest)。
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

# 确保上一级项目根目录在 sys.path 中 (支持在 ats/ 目录直接命令行调用)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from logger_utils import LoggerFactory
    logger = LoggerFactory.getLogger("MultiPeriodChannelStrategy")
except Exception:
    import logging
    logger = logging.getLogger("MultiPeriodChannelStrategy")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from JSONData import tdx_data_Day as tdd
from ats.channel_bottom_reversal_strategy import classify_channel_type
from ats.multi_period_resampler import get_multi_period_klines, normalize_kline_df

DEFAULT_PERIODS = ['d', '2d', '3d', 'w', 'm']
PERIOD_NAMES = {
    'd': '日线',
    '2d': '2日线',
    '3d': '3日线',
    'w': '周线',
    'm': '月线'
}


def calculate_single_period_channel(df_kline: pd.DataFrame, period_tag: str = 'd') -> Dict[str, Any]:
    """
    极速测算单周期通道特征与支撑线。
    """
    if df_kline is None or len(df_kline) < 5:
        return {
            "period": period_tag,
            "period_cn": PERIOD_NAMES.get(period_tag, period_tag),
            "close": 0.0,
            "supp_price": 0.0,
            "reversal_price": 0.0,
            "ch_upper": 0.0,
            "ch_mid": 0.0,
            "ch_lower": 0.0,
            "slope_deg": 0.0,
            "is_above_support": False,
            "is_above_reversal": False,
            "dist_to_supp_pct": 0.0,
            "channel_type": "unknown",
            "channel_type_cn": "数据不足",
            "score": 0.0
        }

    closes = df_kline['close'].values.astype(np.float64)
    highs = df_kline['high'].values.astype(np.float64) if 'high' in df_kline.columns else closes
    lows = df_kline['low'].values.astype(np.float64) if 'low' in df_kline.columns else closes
    n = len(closes)
    curr_close = float(closes[-1])

    # 1. 优先使用 tdd.calc_trend_channel 获取通达信指标与支撑线
    supp_p = 0.0
    rev_p = 0.0
    ch_up = 0.0
    ch_mid = 0.0
    ch_lo = 0.0
    slope_deg = 0.0

    try:
        if n >= 10:
            df_chan = tdd.calc_trend_channel(df_kline.copy())
            supp_p = float(df_chan['ch_supp_price'].iloc[-1])
            rev_p = float(df_chan['reversal_line'].iloc[-1])
            ch_up = float(df_chan['ch_upper'].iloc[-1])
            ch_mid = float(df_chan['ch_mid'].iloc[-1])
            ch_lo = float(df_chan['ch_lower'].iloc[-1])
            slope_deg = float(df_chan['ch_slope_deg'].iloc[-1])
    except Exception as e:
        logger.debug(f"[{period_tag}] calc_trend_channel 异常，使用通道分类兜底: {e}")

    # 2. 结合 classify_channel_type 进行通道类型与支撑线校验兜底
    cls_info = classify_channel_type(df_kline)
    ch_type = cls_info.get("channel_type", "horizontal")
    ch_type_cn = cls_info.get("channel_type_cn", "横盘震荡")
    cls_supp = float(cls_info.get("supp_price", 0.0))
    cls_slope = float(cls_info.get("supp_slope_deg", 0.0))

    # 支撑线防御兜底：如果 calc_trend_channel 算出的支撑线为 0 或明显异常，使用分类器支撑线
    if supp_p <= 0.01 or (curr_close > 0 and supp_p > curr_close * 1.5):
        supp_p = cls_supp if cls_supp > 0.01 else float(lows[-1])

    # 反转线防御兜底
    if rev_p <= 0.01:
        rev_p = supp_p * 1.03

    if abs(slope_deg) < 1e-4:
        slope_deg = cls_slope

    # 3. 核心判决：收盘价是否在支撑线之上 (容许 0.5% 微小毛刺)
    is_above_support = bool(curr_close >= supp_p * 0.995)
    is_above_reversal = bool(curr_close >= rev_p * 0.995)

    dist_to_supp_pct = (curr_close - supp_p) / max(1e-4, supp_p) * 100.0

    # 单周期打分 (0 ~ 100)
    base_score = 50.0
    if is_above_support:
        base_score += 25.0
        # 处于支撑线上方 0%~8% 的最佳拉升黄金带
        if 0.0 <= dist_to_supp_pct <= 8.0:
            base_score += 15.0
        elif dist_to_supp_pct > 8.0:
            base_score += 10.0
    else:
        # 破位惩罚
        base_score -= 20.0

    if is_above_reversal:
        base_score += 10.0

    if slope_deg > 2.0:
        base_score += 10.0
    elif slope_deg < -3.0:
        base_score -= 10.0

    score = min(100.0, max(10.0, round(base_score, 1)))

    return {
        "period": period_tag,
        "period_cn": PERIOD_NAMES.get(period_tag, period_tag),
        "close": round(curr_close, 3),
        "supp_price": round(supp_p, 3),
        "reversal_price": round(rev_p, 3),
        "ch_upper": round(ch_up, 3),
        "ch_mid": round(ch_mid, 3),
        "ch_lower": round(ch_lo, 3),
        "slope_deg": round(slope_deg, 2),
        "is_above_support": is_above_support,
        "is_above_reversal": is_above_reversal,
        "dist_to_supp_pct": round(dist_to_supp_pct, 2),
        "channel_type": ch_type,
        "channel_type_cn": ch_type_cn,
        "score": score
    }


def evaluate_multi_period_channel_strategy(
    df_daily: pd.DataFrame,
    periods: Optional[List[str]] = None,
    as_of_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    【多周期通道支撑线上量化策略统一评估引擎】
    输入:
      df_daily: 日 K 线 DataFrame
      periods: 周期列表，默认 ['d', '2d', '3d', 'w', 'm']
      as_of_date: 可选回测截断日期 (防未来函数)
    输出:
      完整的共振评估结果字典 (包含各周期详情、共振度、信号形态、建议买入区间、量化评分)
    """
    if periods is None:
        periods = DEFAULT_PERIODS

    # 1. 纯向量化重采样为多周期 K 线字典
    multi_klines = get_multi_period_klines(df_daily, periods=periods, as_of_date=as_of_date)

    # 2. 遍历测算每个周期的通道与支撑线特征
    period_details: Dict[str, Dict[str, Any]] = {}
    above_supp_count = 0
    above_rev_count = 0
    scores = []

    for p in periods:
        k_df = multi_klines.get(p)
        detail = calculate_single_period_channel(k_df, period_tag=p)
        period_details[p] = detail
        if detail["is_above_support"]:
            above_supp_count += 1
        if detail["is_above_reversal"]:
            above_rev_count += 1
        scores.append(detail["score"])

    total_periods = len(periods)
    above_ratio = above_supp_count / max(1, total_periods)

    d_info = period_details.get('d', {})
    w_info = period_details.get('w', {})
    m_info = period_details.get('m', {})

    is_d_above = d_info.get("is_above_support", False)
    is_w_above = w_info.get("is_above_support", False)
    is_m_above = m_info.get("is_above_support", False)

    # 3. 支撑线阶梯递增性检查 (Ladder Support Structure)
    # 如: m <= w <= 3d <= 2d <= d
    supp_list = [period_details[p]["supp_price"] for p in periods if period_details[p]["supp_price"] > 0]
    is_ladder_aligned = False
    if len(supp_list) >= 3:
        # 逆序比对：大级别到小级别是否单调不减
        # periods 顺序为 ['d', '2d', '3d', 'w', 'm']
        # 期望 supp_d >= supp_2d >= supp_3d >= supp_w >= supp_m (允许 3% 测量误差)
        supp_d = d_info.get("supp_price", 0.0)
        supp_w = w_info.get("supp_price", 0.0)
        supp_m = m_info.get("supp_price", 0.0)
        if supp_d >= supp_w * 0.97 >= supp_m * 0.95:
            is_ladder_aligned = True

    # 4. 多周期共振形态定性与综合评分 (0~100)
    curr_p = d_info.get("close", 0.0)
    supp_d_p = d_info.get("supp_price", curr_p)

    # ── 核心防御：下降通道与空头破位拦截 ──
    # 仅当日线自身处于下降通道且下倾破位 (或斜率严重负倾斜且跌破日线支撑) 时定性为防诱多
    is_down_trend = (d_info.get("channel_type") == "descending" and d_info.get("slope_deg", 0.0) <= -2.0) or (d_info.get("slope_deg", 0.0) <= -3.0 and not is_d_above)

    if is_down_trend:
        pattern_name = "🔴 下降通道·空头探底防诱多"
        signal_level = "AVOID"
        base_score = 25.0
        buy_suggest = "⛔ 严禁上车 (通道处于下行趋势，警惕脉冲诱多)"
    elif above_supp_count == 5 and is_ladder_aligned:
        pattern_name = "🚀 五周期支撑共振·顶配主升起爆"
        signal_level = "STRONG_BUY"
        base_score = 96.0
        buy_suggest = f"🎯 现价 {curr_p:.2f} 顺势追入 / 回踩日支撑 {supp_d_p:.2f} 预埋"
    elif above_supp_count >= 4 and is_d_above and is_w_above and (d_info.get("slope_deg", 0.0) >= -1.0):
        pattern_name = "👑 多周期通道共振·突破拉升"
        signal_level = "BUY"
        base_score = 90.0
        buy_suggest = f"🚀 顺势建仓 / 依托日支撑 {supp_d_p:.2f} 挂单上车"
    elif is_d_above and is_w_above and (d_info.get("dist_to_supp_pct", 99.0) <= 4.0) and (d_info.get("slope_deg", 0.0) >= -1.0):
        pattern_name = "💎 核心大级别支撑·回踩企稳"
        signal_level = "BUY"
        base_score = 84.0
        buy_suggest = f"💎 回踩企稳买点 / 支撑位 {supp_d_p:.2f} 挂单吸筹"
    elif above_supp_count >= 3 and not is_down_trend:
        pattern_name = "🟡 多周期局部支撑·中继蓄势"
        signal_level = "HOLD"
        base_score = 72.0
        buy_suggest = f"🟡 箱体震荡观望 / 支撑 {supp_d_p:.2f} 吸、阻力抛"
    else:
        pattern_name = "🔴 弱势破位·跌破多周期支撑"
        signal_level = "AVOID"
        base_score = 30.0
        buy_suggest = "⛔ 严禁上车 (跌破多周期支撑线，破位风险)"

    # 均线与动能微调
    avg_score = float(np.mean(scores)) if scores else 50.0
    final_score = round(base_score * 0.65 + avg_score * 0.35, 1)
    if is_down_trend or signal_level == "AVOID":
        final_score = min(48.0, final_score)
    final_score = min(99.0, max(15.0, final_score))

    # 止损价位：日线支撑位下浮 3% 或前期波谷
    stop_loss = round(supp_d_p * 0.97, 2)
    # 第一目标位与第二目标位
    target_1 = round(max(curr_p * 1.08, d_info.get("ch_upper", curr_p * 1.08)), 2)
    target_2 = round(target_1 * 1.10, 2)

    is_buy_signal = bool(signal_level in ("STRONG_BUY", "BUY") and final_score >= 80.0)

    # 可解释性原因陈述
    reasons = []
    reasons.append(f"{above_supp_count}/{total_periods} 周期处于支撑线上")
    if is_ladder_aligned:
        reasons.append("支撑线层层垫高向上发散")
    reasons.append(f"日线支撑:{supp_d_p:.2f}(偏离{d_info.get('dist_to_supp_pct', 0.0):+.1f}%)")
    reasons.append(f"周线支撑:{w_info.get('supp_price', 0.0):.2f}")
    if m_info.get("supp_price", 0.0) > 0:
        reasons.append(f"月线支撑:{m_info.get('supp_price', 0.0):.2f}")
    reason_str = " | ".join(reasons)

    return {
        "is_buy_signal": is_buy_signal,
        "signal_level": signal_level,
        "pattern_name": pattern_name,
        "score": final_score,
        "close": curr_p,
        "entry_price": curr_p,
        "stop_loss": stop_loss,
        "target_price_1": target_1,
        "target_price_2": target_2,
        "above_support_count": above_supp_count,
        "above_reversal_count": above_rev_count,
        "is_ladder_aligned": is_ladder_aligned,
        "buy_suggest": buy_suggest,
        "reason": reason_str,
        "period_details": period_details
    }


if __name__ == "__main__":
    # ── 命令行使用与演示 ──
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    target_code = sys.argv[1] if len(sys.argv) > 1 else "600108"
    dl_days = int(sys.argv[2]) if len(sys.argv) > 2 else 250

    print("=" * 68)
    print(f"🎯 [MultiPeriodChannelStrategy] 多周期通道支撑线上共振策略演示")
    print(f"   目标标的: {target_code} | 拉取历史天数: {dl_days}")
    print("=" * 68)

    try:
        df_daily = tdd.get_tdx_append_now_df_api(target_code, dl=dl_days)
        if df_daily is None or df_daily.empty:
            df_daily = tdd.get_tdx_Exp_day_to_df(target_code)
    except Exception as e:
        print(f"⚠️ 读取通达信日线异常: {e}")
        df_daily = None

    if df_daily is not None and not df_daily.empty:
        res = evaluate_multi_period_channel_strategy(df_daily)

        print(f"✅ 测算完成: 现价 {res['close']:.2f} | 多周期评分: {res['score']:.1f} 分")
        print(f"🏆 形态定性: {res['pattern_name']}")
        print(f"🚦 信号评级: {res['signal_level']} (买入触发: {res['is_buy_signal']})")
        print(f"💡 操作建议: {res['buy_suggest']}")
        print(f"🎯 止损价位: {res['stop_loss']:.2f} | 目标区间: {res['target_price_1']:.2f} ~ {res['target_price_2']:.2f}")
        print(f"📋 逻辑诊断: {res['reason']}\n")

        print("📊 各周期通道支撑位与共振明细:")
        print(f"{'周期':<8} {'现价':<8} {'支撑位':<8} {'反转位':<8} {'站上支撑':<8} {'偏离%':<10} {'通道类型':<10} {'倾角':<8}")
        print("-" * 68)
        for p, d in res["period_details"].items():
            above_str = "✅ 站上" if d["is_above_support"] else "❌ 跌破"
            print(f"{d['period_cn']:<8} {d['close']:<8.2f} {d['supp_price']:<8.2f} {d['reversal_price']:<8.2f} {above_str:<8} {d['dist_to_supp_pct']:<+10.1f} {d['channel_type_cn']:<10} {d['slope_deg']:<+8.1f}°")

        print("\n💡 【使用方法说明】:")
        print("1. 命令行直接执行:")
        print("   python multi_period_channel_strategy.py [股票代码(默认600108)] [历史天数(默认250)]")
        print("2. Python 代码中导入使用:")
        print("   from ats.multi_period_channel_strategy import evaluate_multi_period_channel_strategy")
        print("   eval_res = evaluate_multi_period_channel_strategy(df_daily)")
        print("   if eval_res['is_buy_signal']:")
        print("       print('买入信号触发:', eval_res['buy_suggest'])")
        print("=" * 68)


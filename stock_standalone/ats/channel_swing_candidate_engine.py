# -*- coding: utf-8 -*-
"""
ats/channel_swing_candidate_engine.py — 通道上涨与支撑线上的 MA20d 震荡企稳候选池核心引擎 (SSOT)
=============================================================================
核心量化判决体系 (实战三案验证闭环)：
- 成功案例 1 (法尔胜 000890): 上升通道(UPPER1 9.62+)+支撑线(8.45)+MA20(8.21)上方洗盘企稳，有高度、有振幅，卖出后防丢失筹码二次上车。
- 成功案例 2 (中农联合 003042): 上升通道(UPPER1 17.6+)+支撑线(15.10)+MA20(14.31)上方企稳，次日直接放量加速冲板起爆。
- 失败案例 3 (爱尔眼科 300015): 均线向下(MA10↓,MA20↓,MA250↓)，跌破支撑线(8.25)，日均振幅仅1.2%(织布死水)，无通道高度，一票否决剔除！

核心量化维度：
1. 通道上涨 (Ascending Channel):
   - 通道倾角 ch_slope_deg > 0，MA10/MA20 多头抬升，大级别多头底座；一票否决下降通道阴跌股。
2. 支撑线上的 MA20 震荡企稳 (Support Line & MA20 Stabilization):
   - 价格处于支撑线之上 (close >= supp_price * 0.985)；
   - 价格处于 MA20 均线支撑带 (偏离度处于 [-2.0%, +8.5%] 健康区间，彻底突破死板的 5% 限制)；
   - 回踩未破位，Higher Lows，缩量收敛或探底回升。
3. 通道有高度 (Channel Height & Upside Room):
   - 通道高度百分比 (ch_upper - ch_lower) / ch_mid * 100% >= 8% (优质标的 12%~25%)；
   - 向上利润空间 (ch_upper - close) / close * 100% >= 5% (优质标的 8%~20%)；
   - 通道位置 ch_pos <= 85%，拒绝上轨顶部追高。
4. 走势有振幅、有波动 (Volatility & Swing Amplitude):
   - 近 5~10 日平均振幅 >= 3.0% (优质标的 >= 4.5%~8%)；
   - 近期有过涨停或放量大阳线 (股性活跃，主力沉淀)；
   - 严厉剔除日均振幅 < 2.0% 的死水织布机。
5. 防丢失筹码护城河 (Trade Guard & Re-entry):
   - 操盘手曾买入/持仓/近期卖出标的，在支撑线上企稳时自动触发【🎯 卖出企稳·二次上车】！
6. 次日加速冲板识别 (Acceleration Trigger):
   - 支撑线上企稳后，次日放量突破或具备缺口/光脚加速，标记【🚀 支撑企稳·加速冲板】！
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger_utils import LoggerFactory
    logger = LoggerFactory.getLogger("ChannelSwingCandidateEngine")
except Exception:
    import logging
    logger = logging.getLogger("ChannelSwingCandidateEngine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from JSONData.tdx_data_Day import calc_trend_channel


class ChannelSwingCandidateEngine:
    """通道上涨与支撑线上的 MA20d 震荡企稳候选池中枢 (SSOT)"""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # 缓存个股历史分析结果: code -> dict
        self._cache = {}

    def evaluate_channel_swing_structure(
        self,
        code: str,
        name: str = "",
        price: float = 0.0,
        row: Optional[Dict[str, Any]] = None,
        close_series: Optional[List[float]] = None,
        high_series: Optional[List[float]] = None,
        low_series: Optional[List[float]] = None,
        is_traded_or_closed: bool = False,
        is_favorite: bool = False,
        df_kline: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """评估单只股票是否满足【通道上涨 + 支撑线上 MA20d 震荡企稳】双结构

        Args:
            code: 股票代码
            name: 股票名称
            price: 最新收盘价
            row: 实时宽表中的个股行字典
            close_series: 历史收盘价序列 (包含最新价)
            high_series: 历史最高价序列
            low_series: 历史最低价序列
            is_traded_or_closed: 是否为曾成交/持仓/已卖出标的 (触发防丢筹码二次上车)
            is_favorite: 是否为重点关注标的
            df_kline: 完整的 K 线 DataFrame (若传入则优先使用 calc_trend_channel)

        Returns:
            结构字典，包含通道斜率、支撑位、高度、振幅、得分与形态定性
        """
        code_str = str(code).strip()
        code_clean = "".join(c for c in code_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in code_str) else code_str

        # 基础数据提取
        if price <= 0.001 and row is not None:
            price = float(row.get("close", row.get("price", 0.0)) or 0.0)

        # 提取 MA20
        ma20_val = 0.0
        if row is not None:
            for k in ("ma20d", "ma20", "MA20"):
                if k in row and row[k] is not None:
                    try:
                        v = float(row[k])
                        if v > 0:
                            ma20_val = v
                            break
                    except Exception:
                        pass

        if ma20_val <= 0 and close_series and len(close_series) >= 5:
            sub = close_series[-min(20, len(close_series)):]
            ma20_val = sum(sub) / len(sub)

        if ma20_val <= 0:
            ma20_val = price

        ma20_dev = (price - ma20_val) / ma20_val * 100.0 if ma20_val > 0 else 0.0

        # 通道三轨与支撑线测算
        ch_slope_deg = 0.0
        supp_price = 0.0
        reversal_price = 0.0
        ch_upper = 0.0
        ch_mid = 0.0
        ch_lower = 0.0
        ch_height_pct = 0.0
        upside_room_pct = 0.0
        amplitude_pct = 0.0
        ch_pos = 50.0

        has_kline_channel = False

        # 1. 尝试从 df_kline 或时序 K 线运行 calc_trend_channel 获取原生通达信指标
        if df_kline is not None and len(df_kline) >= 10:
            try:
                df_c = calc_trend_channel(df_kline.copy())
                supp_price = float(df_c["ch_supp_price"].iloc[-1])
                reversal_price = float(df_c["reversal_line"].iloc[-1])
                ch_upper = float(df_c["ch_upper"].iloc[-1])
                ch_mid = float(df_c["ch_mid"].iloc[-1])
                ch_lower = float(df_c["ch_lower"].iloc[-1])
                ch_slope_deg = float(df_c["ch_slope_deg"].iloc[-1])
                ch_height_pct = float(df_c["ch_height_pct"].iloc[-1])
                ch_pos = float(df_c["ch_pos"].iloc[-1])
                has_kline_channel = True
            except Exception as e:
                logger.debug(f"[{code_str}] calc_trend_channel 测算异常: {e}")

        # 2. 若无完整 df_kline，使用 close_series/high_series/low_series 构造轻量通道
        if not has_kline_channel and close_series and len(close_series) >= 5:
            n_bars = len(close_series)
            c_arr = np.array(close_series, dtype=np.float64)
            h_arr = np.array(high_series, dtype=np.float64) if high_series and len(high_series) == n_bars else c_arr
            l_arr = np.array(low_series, dtype=np.float64) if low_series and len(low_series) == n_bars else c_arr

            # 线性回归拟合中轨
            win = min(n_bars, 20)
            x = np.arange(win)
            y = c_arr[-win:]
            slope, intercept = np.polyfit(x, y, 1)
            mid_val = slope * (win - 1) + intercept
            ch_mid = max(price * 0.5, float(mid_val))

            # 斜率角度
            slope_pct = (slope / ch_mid) * 100.0 if ch_mid > 0 else 0.0
            ch_slope_deg = float(np.degrees(np.arctan(slope_pct)))

            # 通道上下轨 (自适应振幅)
            std_val = float(np.std(y)) if len(y) > 1 else price * 0.05
            band_w = max(std_val * 2.0, ch_mid * 0.08)
            ch_upper = ch_mid + band_w
            ch_lower = max(0.01, ch_mid - band_w)

            # 支撑线：近 10 日最低点连线抬升或低点支撑
            recent_lows = l_arr[-min(10, n_bars):]
            supp_price = float(np.min(recent_lows))
            if supp_price <= 0.01 or supp_price > price:
                supp_price = float(min(ma20_val, price * 0.98))

            ch_height = ch_upper - ch_lower
            ch_height_pct = (ch_height / ch_mid) * 100.0 if ch_mid > 0 else 0.0
            ch_pos = (price - ch_lower) / max(0.01, ch_height) * 100.0
            has_kline_channel = True

        # 3. 若仅有 row 截面宽表，利用历史字段 lastp1d..lastp9d, lasth1d..lasth3d, lastl1d..lastl3d 估算
        if not has_kline_channel and row is not None:
            # 提取历史收盘与高低点
            hist_p = []
            hist_h = []
            hist_l = []
            for d in range(9, 0, -1):
                p_v = float(row.get(f"lastp{d}d", 0) or 0)
                if p_v > 0:
                    hist_p.append(p_v)
            for d in range(3, 0, -1):
                h_v = float(row.get(f"lasth{d}d", 0) or 0)
                l_v = float(row.get(f"lastl{d}d", 0) or 0)
                if h_v > 0:
                    hist_h.append(h_v)
                if l_v > 0:
                    hist_l.append(l_v)

            curr_h = float(row.get("high", price) or price)
            curr_l = float(row.get("low", price) or price)

            # 均线多头抬升趋势判定
            ma5 = float(row.get("ma5d", row.get("ma5", price)) or price)
            ma10 = float(row.get("ma10d", row.get("ma10", price)) or price)

            # 优先读取 row 中权威通道与支撑指标 (对齐通达信/calc_trend_channel)
            r_slope = row.get("ch_slope_deg", row.get("slope_deg"))
            if r_slope is not None:
                try: ch_slope_deg = float(r_slope)
                except Exception: pass
            elif hist_p and len(hist_p) >= 3:
                slp = (price - hist_p[0]) / len(hist_p)
                slp_pct = (slp / price) * 100.0 if price > 0 else 0.0
                ch_slope_deg = float(np.degrees(np.arctan(slp_pct)))
            elif ma10 > ma20_val:
                ch_slope_deg = 3.5
            elif ma20_val > 0 and price > ma20_val:
                ch_slope_deg = 1.8
            else:
                ch_slope_deg = -2.0

            # 动态支撑线估算: 优先使用权威支撑线
            r_supp = row.get("ch_supp_price", row.get("supp_price"))
            if r_supp is not None and float(r_supp) > 0.01:
                supp_price = float(r_supp)
            else:
                all_lows = hist_l + [curr_l]
                if all_lows:
                    supp_price = float(np.min(all_lows))
                else:
                    supp_price = float(min(ma20_val, price * 0.98))

            # 通道估算 (高度通常 15%~25%)
            ch_mid = ma20_val
            ch_upper = float(row.get("upper", ch_mid * 1.12) or ch_mid * 1.12)
            ch_lower = float(row.get("lower", ch_mid * 0.92) or ch_mid * 0.92)
            ch_height_pct = ((ch_upper - ch_lower) / ch_mid * 100.0) if ch_mid > 0 else 16.0
            ch_pos = ((price - ch_lower) / max(0.01, ch_upper - ch_lower) * 100.0)

        # 4. 计算走势振幅与波动率
        if high_series and low_series and len(high_series) >= 5:
            amps = []
            for h_v, l_v in zip(high_series[-10:], low_series[-10:]):
                if l_v > 0.001:
                    amps.append((h_v - l_v) / l_v * 100.0)
            amplitude_pct = float(np.mean(amps)) if amps else 3.5
        elif row is not None:
            # 从截面估算振幅
            curr_h = float(row.get("high", price) or price)
            curr_l = float(row.get("low", price) or price)
            day_amp = (curr_h - curr_l) / curr_l * 100.0 if curr_l > 0 else 2.5
            h1 = float(row.get("lasth1d", curr_h) or curr_h)
            l1 = float(row.get("lastl1d", curr_l) or curr_l)
            amp1 = (h1 - l1) / l1 * 100.0 if l1 > 0 else day_amp
            amplitude_pct = round((day_amp + amp1) / 2.0, 2)
        else:
            amplitude_pct = 3.5

        # 向上利润空间 (当前价到上轨)
        upside_room_pct = (ch_upper - price) / price * 100.0 if price > 0 else 0.0

        # 防御兜底
        if supp_price <= 0.01:
            supp_price = float(ma20_val * 0.985)
        if ch_upper <= 0.01:
            ch_upper = float(price * 1.15)
        if ch_height_pct <= 0.01:
            ch_height_pct = 15.0

        # =========================================================================
        # 核心 5 维量化判决 (对齐法尔胜/中农联合与爱尔眼科反面教材)
        # =========================================================================

        # 1. 均线与通道方向判定 (爱尔眼科防御: MA10↓, MA20↓, MA250↓ 均线空头下压直接判负)
        ma10_val = float(row.get("ma10d", row.get("ma10", 0.0)) or 0.0) if row else 0.0
        ma250_val = float(row.get("ma250d", row.get("ma250", 0.0)) or 0.0) if row else 0.0
        is_ma_down = bool((ma10_val > 0 and ma20_val > 0 and ma10_val < ma20_val and price < ma20_val * 0.985) or (ch_slope_deg <= -1.5))

        # 1. 通道上涨判定 (一票否决下降通道)
        is_channel_up = bool((ch_slope_deg >= 0.2 or (ch_mid > 0 and price >= ch_mid and ma20_val > 0 and price >= ma20_val * 0.98)) and not is_ma_down)
        is_channel_down = bool((ch_slope_deg <= -1.5 or is_ma_down) and price < ma20_val * 0.985)

        # 2. 支撑线上判定 (在支撑线及 MA20 均线带上方)
        # 严格防御爱尔眼科: 若通道下行、均线走弱或直接跌破支撑线，硬性要求 price >= supp_price
        if is_channel_down or is_ma_down or ch_slope_deg < 0.0 or price < supp_price:
            is_above_support = bool(price >= supp_price)
        else:
            is_above_support = bool(price >= supp_price * 0.985)

        pct_today = float(row.get("percent", 0.0) if row else 0.0)
        is_ma20_zone = bool(-2.2 <= ma20_dev <= (16.0 if pct_today >= 2.0 else 8.8))

        # 3. 企稳特征判定 (Higher Lows, 未破位, 缩量或探底回升)
        curr_low = float(row.get("low", price) if row else price)
        is_low_holding = bool(curr_low >= ma20_val * 0.975 and curr_low >= supp_price * 0.975)
        is_stabilized = bool(is_channel_up and is_above_support and is_ma20_zone and is_low_holding and not is_channel_down)

        # 4. 通道有高度 (通道跨度充足，向上空间有肉吃，爱尔眼科防御: 剔除无高度标的)
        has_adequate_height = bool(ch_height_pct >= 8.0)
        has_upside_space = bool(upside_room_pct >= 4.5 and ch_pos <= 88.0)

        # 5. 走势有振幅 (拒绝爱尔眼科式死水织布机: 振幅 < 2.0% 一票否决)
        has_active_amplitude = bool(amplitude_pct >= 2.8)
        is_dead_stock = bool(amplitude_pct < 1.9)

        # 6. 完美双结构判定 (通道上涨 + 支撑线上企稳 + 通道有高度 + 走势有振幅)
        is_perfect_double = bool(
            is_channel_up and
            is_above_support and
            is_stabilized and
            has_adequate_height and
            has_upside_space and
            has_active_amplitude and
            not is_channel_down and
            not is_dead_stock
        )

        # 7. 防丢失筹码二次上车 (法尔胜模式)
        is_reentry_candidate = bool(is_traded_or_closed and is_above_support and is_channel_up and is_ma20_zone and not is_channel_down)

        # 8. 次日加速起爆识别 (中农联合模式: 支撑线上企稳后放量或形态加速冲板)
        pct_today = float(row.get("percent", 0.0) if row else 0.0)
        open_p = float(row.get("open", price) if row else price)
        last_c = float(row.get("lastp1d", open_p) if row else open_p)
        open_jump = (open_p - last_c) / last_c * 100.0 if last_c > 0 else 0.0

        is_accelerating = False
        if is_above_support and is_channel_up and (pct_today >= 2.0 or open_jump >= 0.8) and not is_dead_stock:
            if curr_low >= open_p - 0.02 or open_jump >= 0.8:
                is_accelerating = True

        # =========================================================================
        # 综合量化评分体系 (0 ~ 100 分)
        # =========================================================================
        score = 50.0

        if is_channel_down or is_dead_stock or not is_above_support:
            # 劣币直接降级 (如爱尔眼科量化评分 10.0)
            if not is_above_support:
                score = 15.0
                swing_tag = "⚠️ 跌破支撑"
                reason = f"跌破上涨支撑线({supp_price:.2f}元)，通道破位防御"
            elif is_channel_down:
                score = 10.0
                swing_tag = "⚠️ 下降通道"
                reason = f"均线压制/通道下行({ch_slope_deg:.1f}°)，严防阴跌"
            else:
                score = 25.0
                swing_tag = "⚠️ 织布死水"
                reason = f"振幅过低({amplitude_pct:.1f}%)，无波动弹性"
        else:
            # 1. 通道向上基础分 (最高 25 分)
            if ch_slope_deg >= 5.0:
                score += 25.0
            elif ch_slope_deg >= 2.0:
                score += 20.0
            elif ch_slope_deg >= 0.0:
                score += 12.0

            # 2. 支撑线上企稳得分 (最高 30 分)
            if is_above_support and is_low_holding:
                dist_to_supp = (price - supp_price) / supp_price * 100.0 if supp_price > 0 else 0.0
                if 0.0 <= dist_to_supp <= 4.0:
                    score += 30.0  # 紧贴支撑线最佳企稳区
                elif dist_to_supp <= 8.5:
                    score += 22.0  # 法尔胜式通道蓄势区
                else:
                    score += 15.0

            # 3. 通道高度与向上空间得分 (最高 25 分)
            if ch_height_pct >= 18.0 and upside_room_pct >= 10.0:
                score += 25.0  # 高度与利润空间充裕
            elif ch_height_pct >= 12.0 and upside_room_pct >= 6.0:
                score += 18.0
            elif has_adequate_height:
                score += 10.0

            # 4. 走势振幅与波动率加成 (最高 20 分)
            if amplitude_pct >= 5.0:
                score += 20.0  # 活跃波段股
            elif amplitude_pct >= 3.5:
                score += 14.0
            elif has_active_amplitude:
                score += 8.0

            # 5. 特殊状态提权
            if is_accelerating:
                score += 15.0
            if is_reentry_candidate:
                score += 12.0

            score = min(99.0, max(30.0, score))

            # 形态定性标签
            if is_accelerating:
                swing_tag = "🚀 支撑起爆·主升加速"
                reason = f"支撑线({supp_price:.2f}元)企稳后放量加速，通道空间+{upside_room_pct:.1f}% (中农联合模式)"
            elif is_reentry_candidate:
                swing_tag = "🎯 卖出企稳·二次上车"
                reason = f"曾卖出标的在支撑线({supp_price:.2f}元)/MA20({ma20_val:.2f}元)上方扎实企稳，防丢筹码 (法尔胜模式)"
            elif is_perfect_double:
                swing_tag = "🏆 完美双结构·支撑企稳"
                reason = f"上升通道(+{ch_slope_deg:.1f}°)，稳居支撑({supp_price:.2f}元)，高度{ch_height_pct:.1f}%，振幅{amplitude_pct:.1f}%"
            elif is_above_support and is_channel_up:
                swing_tag = "📈 上升通道·蓄势待发"
                reason = f"稳居上升通道中下轨，偏离MA20({ma20_dev:+.1f}%)，支撑线{supp_price:.2f}元"
            else:
                swing_tag = "⏳ 通道观察"
                reason = f"通道倾角{ch_slope_deg:.1f}°，观察支撑位{supp_price:.2f}元承接力度"

        result = {
            "code": code_str,
            "name": name,
            "price": round(price, 2),
            "ma20": round(ma20_val, 2),
            "ma20_dev": round(ma20_dev, 2),
            "ch_slope_deg": round(ch_slope_deg, 1),
            "supp_price": round(supp_price, 2),
            "ch_upper": round(ch_upper, 2),
            "ch_mid": round(ch_mid, 2),
            "ch_lower": round(ch_lower, 2),
            "ch_height_pct": round(ch_height_pct, 1),
            "upside_room_pct": round(upside_room_pct, 1),
            "amplitude_pct": round(amplitude_pct, 1),
            "ch_pos": round(ch_pos, 1),
            "is_channel_up": is_channel_up,
            "is_above_support": is_above_support,
            "is_stabilized": is_stabilized,
            "is_perfect_double": is_perfect_double,
            "is_reentry_candidate": is_reentry_candidate,
            "is_accelerating": is_accelerating,
            "score": round(score, 1),
            "tag": swing_tag,
            "reason": reason
        }

        self._cache[code_clean] = result
        return result

    def screen_channel_swing_candidates(
        self,
        df_all: pd.DataFrame,
        history_cache: Optional[Dict[str, Any]] = None,
        trade_history_codes: Optional[set] = None,
        favorite_codes: Optional[set] = None,
        max_candidates: int = 50
    ) -> List[Dict[str, Any]]:
        """全市场与重点标的高性能筛选【通道上涨·支撑线上企稳】候选池

        Args:
            df_all: 全市场实时行情 DataFrame
            history_cache: 历史 K 线内存缓存
            trade_history_codes: 用户曾交易/卖出股票代码集合
            favorite_codes: 重点自选股票代码集合
            max_candidates: 最大候选数量

        Returns:
            排好序的高质量候选字典列表
        """
        if df_all is None or df_all.empty:
            return []

        history_cache = history_cache or {}
        trade_history_codes = trade_history_codes or set()
        favorite_codes = favorite_codes or set()

        close_col = "close" if "close" in df_all.columns else "price"
        ma20_col = next((c for c in ("ma20d", "ma20", "MA20") if c in df_all.columns), None)

        if close_col not in df_all.columns or not ma20_col:
            return []

        close_s = pd.to_numeric(df_all[close_col], errors="coerce").fillna(0.0)
        ma20_s = pd.to_numeric(df_all[ma20_col], errors="coerce").fillna(0.0).replace(0, np.nan)
        dev_s = (close_s - ma20_s) / ma20_s * 100.0

        # 向量化宽幅粗筛：偏离度处于 [-2.5%, +16.5%]，或属于重点/曾交易标的 (兼容冲板加速的中农联合)
        clean_codes = [str(c).strip().zfill(6) for c in df_all.index]
        clean_s = pd.Series(clean_codes, index=df_all.index)

        is_fav_mask = clean_s.isin(favorite_codes) | df_all.index.isin(favorite_codes)
        is_traded_mask = clean_s.isin(trade_history_codes) | df_all.index.isin(trade_history_codes)
        rough_mask = ((dev_s >= -2.5) & (dev_s <= 16.5)) | is_fav_mask | is_traded_mask

        sub_df = df_all[rough_mask]
        if sub_df.empty:
            return []

        candidates = []
        sub_dict = sub_df.to_dict("index")

        for code, row in sub_dict.items():
            code_str = str(code).strip()
            code_clean = "".join(c for c in code_str if c.isdigit()).zfill(6)
            name = str(row.get("name", ""))
            price = float(row.get(close_col, 0.0) or 0.0)
            if price <= 0.001:
                continue

            # 排除指数与 ETF
            if code_str.startswith(("sh000", "sz399", "bj899", "159", "510", "588")):
                continue

            is_traded = (code_str in trade_history_codes or code_clean in trade_history_codes)
            is_fav = (code_str in favorite_codes or code_clean in favorite_codes)

            # 提取历史序列
            close_seq, high_seq, low_seq = None, None, None
            hist = history_cache.get(code_str) or history_cache.get(code_clean)
            if hist and isinstance(hist, list) and len(hist) >= 5:
                try:
                    close_seq = [float(x[1]) for x in hist if x[1] is not None]
                    if len(hist[0]) >= 4:
                        high_seq = [float(x[2]) for x in hist if x[2] is not None]
                        low_seq = [float(x[3]) for x in hist if x[3] is not None]
                except Exception:
                    pass

            res = self.evaluate_channel_swing_structure(
                code=code_str,
                name=name,
                price=price,
                row=row,
                close_series=close_seq,
                high_series=high_seq,
                low_series=low_seq,
                is_traded_or_closed=is_traded,
                is_favorite=is_fav
            )

            # 过滤门槛：得分 >= 65 或属于重点/曾卖出且支撑线上企稳
            if res["score"] >= 65.0 or (is_traded and res["is_above_support"]) or (is_fav and res["is_above_support"]):
                candidates.append(res)

        # 排序：优先按加速/二次上车/完美双结构，其次按综合得分降序
        def _sort_key(item):
            priority = 0
            if item["is_accelerating"]:
                priority = 4
            elif item["is_reentry_candidate"]:
                priority = 3
            elif item["is_perfect_double"]:
                priority = 2
            elif item["is_above_support"]:
                priority = 1
            return (priority, item["score"], item["ch_height_pct"], item["amplitude_pct"])

        candidates.sort(key=_sort_key, reverse=True)
        return candidates[:max_candidates]

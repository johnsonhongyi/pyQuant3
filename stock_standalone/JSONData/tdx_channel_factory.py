# -*- coding: utf-8 -*-
"""
JSONData/tdx_channel_factory.py — 通达信自动通道、KX 上涨支撑线与 CDP 支撑反转统一算法工厂 (SSOT)
===================================================================================================
职责：
1. 统一通道计算：严格对齐通达信《GG通道线走势》公式（TC2/BC2/NOD/FORCAST/SLOPE/AT5/UT5/MID/UP/DN）；
2. 统一支撑线计算：严格对齐通达信 KX_RAW:=DRAWLINE(LOW<=LLV(LOW,20),LOW,HIGH>=HHV(HIGH,20),LLV(LOW,4),1)；
3. 统一 CDP 支撑/反转：E:=(H+L+O+2*C)/5, 支撑=2*E-H, 反转=E-(H-L)；
4. 彻底消除 trade_visualizer_qt6.py 与 JSONData/tdx_data_Day.py 的双轨重复实现，实现 100% 单一真实源 (SSOT)。
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


@dataclass
class TDXChannelResult:
    """通达信通道与支撑线权威计算结果数据结构"""
    # 通道三轨序列 (全长 N)
    mid: np.ndarray
    upper: np.ndarray
    lower: np.ndarray

    # 回归斜率与方向
    slope: float
    slope_deg: float
    ch_dir: int  # 1: 上升通道, -1: 下降通道, 0: 平行通道

    # 相对位置与尺寸
    ch_pos: float  # 最新收盘价通道位置 (%)
    ch_pos_series: np.ndarray  # 全长位置序列
    ch_height: float  # 最新通道宽度 (upper - lower)
    ch_height_pct: float  # 通道宽度占中轨比例 (%)

    # 锚点指标
    tc2: int
    bc2: int
    nod: int
    start_idx: int  # 趋势通道起点绝对索引 (n - max(tc2, bc2))
    idx_far: int
    upper_price: float
    lower_price: float
    limit_min: float
    limit_max: float

    # 可视化线段集
    lines_for_visualizer: List[Dict[str, np.ndarray]]

    # 最新上涨支撑线核心指标
    supp_price: float  # 最新支撑线基准价格 (元)
    supp_slope: float  # 支撑线斜率
    supp_slope_deg: float  # 支撑线倾角 (°)
    supp_days: int  # 支撑线距今天数
    supp_pos: float  # 现价相对于支撑线偏离度 (%)
    is_broken: bool  # 现价是否有效跌破支撑线

    # 通达信 CDP 支撑反转
    cdp_support: float  # 2*E - HIGH
    cdp_reversal: float  # E - (HIGH - LOW)
    cdp_resistance: float  # 2*E - LOW
    cdp_breakthrough: float  # E + (HIGH - LOW)


class TDXChannelFactory:
    """通达信自动通道与上涨支撑线权威工厂类"""

    @classmethod
    def calculate(
        cls,
        data: Union[pd.DataFrame, Dict[str, np.ndarray]],
        ur: int = 6,
        lr: int = 6
    ) -> TDXChannelResult:
        """
        全量计算通达信通道、KX DRAWLINE 支撑线及 CDP 支撑反转。
        支持传入 pd.DataFrame 或字典。
        """
        # 1. 提取并校验输入数据
        if isinstance(data, pd.DataFrame):
            n = len(data)
            high = data['high'].values.astype(np.float64)
            low = data['low'].values.astype(np.float64)
            close = data['close'].values.astype(np.float64)
            open_p = data['open'].values.astype(np.float64) if 'open' in data.columns else close
        else:
            high = np.asarray(data['high'], dtype=np.float64)
            low = np.asarray(data['low'], dtype=np.float64)
            close = np.asarray(data['close'], dtype=np.float64)
            open_p = np.asarray(data.get('open', close), dtype=np.float64)
            n = len(close)

        if n < 5:
            # 数据极端不足时安全回退
            empty_arr = np.zeros(n, dtype=np.float64)
            return TDXChannelResult(
                mid=empty_arr, upper=empty_arr, lower=empty_arr,
                slope=0.0, slope_deg=0.0, ch_dir=0, ch_pos=50.0,
                ch_pos_series=empty_arr, ch_height=0.0, ch_height_pct=0.0,
                tc2=1, bc2=1, nod=1, start_idx=0, idx_far=0, upper_price=0.0, lower_price=0.0,
                limit_min=0.0, limit_max=0.0, lines_for_visualizer=[],
                supp_price=0.0, supp_slope=0.0, supp_slope_deg=0.0,
                supp_days=0, supp_pos=0.0, is_broken=False,
                cdp_support=0.0, cdp_reversal=0.0, cdp_resistance=0.0, cdp_breakthrough=0.0
            )

        high_s = pd.Series(high)
        low_s = pd.Series(low)

        # ---------------------------------------------------------------------
        # 2. 通达信《GG通道线走势》权威核心计算
        # UR:=6; LR:=6;
        # TC1:=IF(H=HHV(H,6*UR),H,DRAWNULL); TC2:=CONST(BARSLAST(TC1=H))+1;
        # BC1:=IF(L=LLV(L,6*LR),L,DRAWNULL); BC2:=CONST(BARSLAST(BC1=L))+1;
        # ---------------------------------------------------------------------
        hhv_win = min(n, 6 * ur)
        llv_win = min(n, 6 * lr)

        tc1_mask = (high == high_s.rolling(hhv_win, min_periods=1).max().values)
        bc1_mask = (low == low_s.rolling(llv_win, min_periods=1).min().values)

        tc1_idx = np.where(tc1_mask)[0]
        bc1_idx = np.where(bc1_mask)[0]

        tc2_init = int(n - tc1_idx[-1]) if len(tc1_idx) > 0 else 1
        bc2_init = int(n - bc1_idx[-1]) if len(bc1_idx) > 0 else 1
        tc2 = max(1, tc2_init)
        bc2 = max(1, bc2_init)

        # 宏观趋势基准方向：高点在远端 (tc2 > bc2) 为下跌主浪；低点在远端 (bc2 > tc2) 为上升主浪
        macro_dir = -1 if tc2 > bc2 else (1 if bc2 > tc2 else 0)

        def _calc_raw_channel(t_len: int, b_len: int):
            nod_val = abs(t_len - b_len)
            if nod_val < 2:
                nod_val = max(t_len, b_len, 5)
            anc = min(t_len, b_len)
            anc_idx = n - anc
            r_start = max(0, anc_idx - (nod_val + 1) + 1)
            r_slice = close[r_start:anc_idx + 1]
            kl = len(r_slice)
            if kl < 2:
                return None
            xm = (kl - 1.0) / 2.0
            xdev = np.arange(kl, dtype=np.float64) - xm
            vx = kl * (kl * kl - 1.0) / 12.0
            ym = np.mean(r_slice)
            slp = np.dot(xdev, r_slice - ym) / vx if vx > 1e-8 else 0.0
            icp = ym - slp * xm
            npv = slp * (kl - 1.0) + icp

            cb = np.arange(n, 0, -1, dtype=np.float64)
            m = npv - slp * (cb - anc)

            c_start = max(0, n - max(t_len, b_len))
            c_end = min(n - 1, n - min(t_len, b_len))
            r_h = high[c_start:c_end + 1]
            r_m = m[c_start:c_end + 1]
            r_l = low[c_start:c_end + 1]
            at = np.max(r_h - r_m) if len(r_h) > 0 else 0.0
            ut = np.max(r_m - r_l) if len(r_l) > 0 else 0.0
            at = max(0.0, float(at))
            ut = max(0.0, float(ut))

            up = m + at
            lo = m - ut
            return m, up, lo, slp, t_len, b_len, nod_val

        def _is_channel_valid(res_tuple) -> bool:
            if res_tuple is None:
                return False
            m_arr, up_arr, lo_arr, slp, t_l, b_l, _ = res_tuple
            c_now = close[-1]
            m_now = m_arr[-1]
            lo_now = lo_arr[-1]
            up_now = up_arr[-1]
            # 1. 最新中轨与下轨必须为正数
            if m_now <= 0.05 or lo_now <= 0.01:
                return False
            # 2. 中轨不可过度偏离最新收盘价 (45% ~ 220%)
            if c_now > 0.1 and (m_now < c_now * 0.45 or m_now > c_now * 2.2):
                return False
            # 3. 通道宽度必须具有物理意义
            if (up_now - lo_now) <= 0.01:
                return False
            # 4. 股价相对通道位置不可严重脱节脱轨 (-80% ~ 220%)
            w_now = max(up_now - lo_now, 1e-6)
            pos_now = (c_now - lo_now) / w_now * 100.0
            if pos_now < -80.0 or pos_now > 220.0:
                return False
            return True

        channel_res = _calc_raw_channel(tc2, bc2)
        raw_valid = _is_channel_valid(channel_res)
        anchor = min(tc2, bc2)
        raw_slope = channel_res[3] if channel_res is not None else 0.0

        # 自适应次级波段重构 (当原通道穿底/塌缩或严重脱轨失真时介入)
        need_adaptive = not raw_valid
        if need_adaptive and anchor > 3 and n > anchor:
            if bc2 < tc2:
                # 底点距今更近：股票已见底反弹，在 [n - bc2, n] 内寻找有效推进高点
                sub_h = high[n - bc2:]
                rel_max = int(np.argmax(sub_h))
                tc2_cand = max(1, bc2 - rel_max)
                cand_res = _calc_raw_channel(tc2_cand, bc2)
                if _is_channel_valid(cand_res):
                    channel_res = cand_res
                    tc2 = tc2_cand
            else:
                # 高点距今更近：股票见顶回调，在 [n - tc2, n] 内寻找回调低点
                sub_l = low[n - tc2:]
                rel_min = int(np.argmin(sub_l))
                bc2_cand = max(1, tc2 - rel_min)
                cand_res = _calc_raw_channel(tc2, bc2_cand)
                if _is_channel_valid(cand_res):
                    channel_res = cand_res
                    bc2 = bc2_cand

        # 稳健保底兜底 (彻底杜绝任何 0.01 塌缩或负数穿底，三轨对齐通达信 clamp 约束)
        is_fallback = not _is_channel_valid(channel_res)
        if is_fallback:
            win = min(n, max(15, min(30, int(n * 0.5))))
            r_slice = close[-win:]
            kl = len(r_slice)
            xm = (kl - 1.0) / 2.0
            xdev = np.arange(kl, dtype=np.float64) - xm
            vx = kl * (kl * kl - 1.0) / 12.0
            ym = np.mean(r_slice)
            local_slope = np.dot(xdev, r_slice - ym) / vx if vx > 1e-8 else 0.0
            icp = ym - local_slope * xm
            np_val = local_slope * (kl - 1.0) + icp
            currbarscount = np.arange(n, 0, -1, dtype=np.float64)
            mid = np_val - local_slope * (currbarscount - 1.0)
            c_now = close[-1]
            mid = np.maximum(c_now * 0.5, mid)
            std_p = np.std(r_slice) if kl > 1 else c_now * 0.05
            band_w = max(std_p * 2.0, c_now * 0.06)
            upper = mid + band_w
            lower = np.maximum(0.01, mid - band_w)
            tc2 = max(1, min(n, tc2))
            bc2 = max(1, min(n, bc2))
            nod = abs(tc2 - bc2) if abs(tc2 - bc2) >= 2 else 5
            slope = raw_slope if (macro_dir == -1 and raw_slope < 0) else local_slope
        else:
            mid, upper, lower, slope, tc2, bc2, nod = channel_res

        # 对齐通达信原版三轨限制 (最低限制/最高限制约束)
        limit_min = np.min(low[-100:]) * 0.90 if n >= 100 else np.min(low) * 0.90
        limit_max = np.max(high[-100:]) * 1.10 if n >= 100 else np.max(high) * 1.10
        mid = np.clip(mid, limit_min, limit_max)
        upper = np.clip(upper, limit_min, limit_max)
        lower = np.clip(lower, limit_min, limit_max)

        upper_price = high[n - tc2]
        lower_price = low[n - bc2]

        ch_width = upper - lower
        ch_width_safe = np.where(ch_width > 1e-8, ch_width, 1e-8)
        ch_pos_series = (close - lower) / ch_width_safe * 100.0
        ch_pos_now = float(ch_pos_series[-1])

        # 方向判定：保底兜底且宏观大趋势为下跌通道时锁定为 -1 (如 600353 破位)；有效通道则尊重其真实斜率
        if is_fallback and macro_dir == -1:
            ch_dir = -1
        else:
            ch_dir = 1 if slope > 1e-8 else (-1 if slope < -1e-8 else 0)

        mid_last = mid[-1] if mid[-1] > 1e-8 else 1.0
        effective_slope = slope if (ch_dir == 1 and slope > 0) or (ch_dir == -1 and slope < 0) else (-abs(slope) if ch_dir == -1 else abs(slope))
        ch_slope_pct = effective_slope / mid_last * 100.0
        ch_slope_deg = float(np.degrees(np.arctan(ch_slope_pct)))

        ch_height = float(ch_width[-1])
        ch_height_pct = float((ch_height / mid_last) * 100.0)

        # ---------------------------------------------------------------------
        # 3. 对齐通达信原版规则: IF(CURRBARSCOUNT<=MAX(TC2,BC2), ..., DRAWNULL)
        # 趋势起点 start_idx = n - max(tc2, bc2)，起点之前的历史 K 线全部置为 np.nan (DRAWNULL)
        # 彻底杜绝通道线从图表左边界全长横穿，严格从趋势起点起笔画至最新终点
        # ---------------------------------------------------------------------
        start_idx = max(0, n - max(tc2, bc2))
        if start_idx > 0:
            mid[:start_idx] = np.nan
            upper[:start_idx] = np.nan
            lower[:start_idx] = np.nan
            ch_pos_series[:start_idx] = np.nan

        # ---------------------------------------------------------------------
        # 4. 通达信 KX 上涨支撑线权威计算 (DRAWLINE 动态连续对齐)
        # KX_RAW:=DRAWLINE(LOW<=LLV(LOW,20), LOW, HIGH>=HHV(HIGH,20), LLV(LOW,4), 1);
        # ---------------------------------------------------------------------
        llv20 = low_s.rolling(20, min_periods=1).min().values
        hhv20 = high_s.rolling(20, min_periods=1).max().values
        llv4 = low_s.rolling(4, min_periods=1).min().values

        cond1 = (low <= llv20)
        cond2 = (high >= hhv20)

        # 严格遵照通达信 DRAWLINE 语义：
        # COND1 触发时确立起点；后续波浪推进中，COND2 发生时终点动态更新至波段最新极值；
        # 当出现新的 COND1 时开启新一轮波段。
        pairs = []
        curr_c1 = -1
        last_c2 = -1
        for i in range(n):
            if cond1[i]:
                if curr_c1 != -1 and last_c2 != -1 and last_c2 > curr_c1:
                    pairs.append((curr_c1, low[curr_c1], last_c2, llv4[last_c2]))
                    last_c2 = -1
                curr_c1 = i
            elif cond2[i] and curr_c1 != -1:
                last_c2 = i

        if curr_c1 != -1 and last_c2 != -1 and last_c2 > curr_c1:
            pairs.append((curr_c1, low[curr_c1], last_c2, llv4[last_c2]))

        # 生成可视化线段数据 (Qt Line Segments)
        lines_for_visualizer = []
        idx_far = min(n - tc2, n - bc2)

        # 对齐通达信主图：支撑线严格从波段最低点起笔 (DRAWLINE 起点)，向右延伸至最新终点
        if pairs:
            # 最新反弹波段 (通达信主图同款白色支撑线，从最低点 i_A 起笔延伸至最新交易日)
            last_i_A, last_p_A, last_i_B, last_p_B = pairs[-1]
            k_val = (last_p_B - last_p_A) / float(last_i_B - last_i_A)
            x_indices = np.arange(last_i_A, n)
            y_vals = k_val * (x_indices - last_i_A) + last_p_A
            valid_mask = (y_vals >= limit_min) & (y_vals <= limit_max)
            x_draw = x_indices[valid_mask]
            y_draw = y_vals[valid_mask]
            if len(x_draw) > 1:
                lines_for_visualizer.append({'x': x_draw, 'y': y_draw})

            # 若存在历史波段且其起点在当前通道视窗内，仅保留其有效区间，绝不横穿后续行情
            for i_A, price_A, i_B, price_B in pairs[:-1]:
                if i_A >= start_idx:
                    k_val = (price_B - price_A) / float(i_B - i_A)
                    end_bar = min(n, i_B + 5)
                    x_indices = np.arange(i_A, end_bar)
                    y_vals = k_val * (x_indices - i_A) + price_A
                    valid_mask = (y_vals >= limit_min) & (y_vals <= limit_max)
                    x_draw = x_indices[valid_mask]
                    y_draw = y_vals[valid_mask]
                    if len(x_draw) > 1:
                        lines_for_visualizer.append({'x': x_draw, 'y': y_draw})

        # 计算最新有效支撑线特征指标
        supp_slope = 0.0
        supp_days = bc2
        supp_price_last = lower[-1]

        if pairs:
            last_i_A, last_p_A, last_i_B, last_p_B = pairs[-1]
            supp_k = (last_p_B - last_p_A) / float(last_i_B - last_i_A)
            supp_slope = supp_k
            supp_price_last = supp_k * ((n - 1) - last_i_A) + last_p_A
            supp_days = (n - 1) - last_i_A
        else:
            supp_k = (close[-1] - lower_price) / max(1, bc2)
            supp_slope = supp_k
            supp_price_last = lower_price + supp_k * bc2
            supp_days = bc2

        supp_price_last = max(0.01, float(supp_price_last))
        c_last = close[-1] if close[-1] > 1e-8 else 1.0
        supp_slope_pct = supp_slope / c_last * 100.0
        supp_slope_deg = float(np.degrees(np.arctan(supp_slope_pct)))
        supp_pos = float((close[-1] - supp_price_last) / supp_price_last * 100.0)
        is_broken = bool(close[-1] < supp_price_last)

        # ---------------------------------------------------------------------
        # 5. 通达信同款 CDP 支撑反转计算
        # E:=(HIGH+LOW+OPEN+2*CLOSE)/5;
        # 明日阻力:=2*E-LOW; 明日支撑:=2*E-HIGH;
        # 明日突破:=E+(HIGH-LOW); 明日反转:=E-(HIGH-LOW);
        # ---------------------------------------------------------------------
        h_last = high[-1]
        l_last = low[-1]
        o_last = open_p[-1]
        c_last = close[-1]
        e_val = (h_last + l_last + o_last + 2.0 * c_last) / 5.0
        cdp_support = float(2.0 * e_val - h_last)
        cdp_reversal = float(e_val - (h_last - l_last))
        cdp_resistance = float(2.0 * e_val - l_last)
        cdp_breakthrough = float(e_val + (h_last - l_last))

        return TDXChannelResult(
            mid=mid,
            upper=upper,
            lower=lower,
            slope=float(effective_slope),
            slope_deg=ch_slope_deg,
            ch_dir=ch_dir,
            ch_pos=ch_pos_now,
            ch_pos_series=ch_pos_series,
            ch_height=ch_height,
            ch_height_pct=ch_height_pct,
            tc2=tc2,
            bc2=bc2,
            nod=nod,
            start_idx=start_idx,
            idx_far=idx_far,
            upper_price=float(upper_price),
            lower_price=float(lower_price),
            limit_min=float(limit_min),
            limit_max=float(limit_max),
            lines_for_visualizer=lines_for_visualizer,
            supp_price=supp_price_last,
            supp_slope=float(supp_slope),
            supp_slope_deg=supp_slope_deg,
            supp_days=int(supp_days),
            supp_pos=supp_pos,
            is_broken=is_broken,
            cdp_support=cdp_support,
            cdp_reversal=cdp_reversal,
            cdp_resistance=cdp_resistance,
            cdp_breakthrough=cdp_breakthrough
        )

    @classmethod
    def get_visualizer_channel(
        cls,
        df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
        """供 trade_visualizer_qt6.py 调用的三轨及中轴拟合"""
        res = cls.calculate(df)
        return res.mid, res.upper, res.lower, res.slope, res.idx_far

    @classmethod
    def get_kx_trend_lines(
        cls,
        df: pd.DataFrame,
        limit_low: Optional[float] = None,
        limit_high: Optional[float] = None,
        idx_far: int = 0
    ) -> List[Dict[str, np.ndarray]]:
        """供 trade_visualizer_qt6.py 调用的 KX 上涨支撑线图元坐标集"""
        res = cls.calculate(df)
        return res.lines_for_visualizer

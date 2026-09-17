# -*- coding: utf-8 -*-
"""
ats/strategy/ipo_vwap_detector_engine.py
----------------------------------------
新股次新股极限 10 日 VWAP 预判结构与异动检测引擎
核心量化逻辑 (操盘手超短哲学)：
1. 只捕捉在 VWAP 上的强势走势结构；
2. 识别“在 VWAP 上走平蓄势 1~3 天”的潜伏预判结构 (预下单)；
3. “回踩 VWAP 不破不碰”是黄金极限买点；买入打了止损就说明买点错了，止损极窄；
4. 破位跌到 VWAP 之下的股反抽到 VWAP 只是高点止损逃命点，严禁开仓；
5. 结合大趋势 K 线 (日K/2D) 下轨通道支撑与【🚀启动】信号共振。
"""

import os
import sys
import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from sys_utils import resolve_stock_name

logger = logging.getLogger("IPOVWAPDetector")


@dataclass
class VWAPDetectorSignal:
    """个股 VWAP 结构检测结果与预下单信号"""
    code: str
    name: str
    price: float = 0.0
    change_pct: float = 0.0
    vwap: float = 0.0
    vwap_diff_pct: float = 0.0        # 现价与 VWAP 偏离度: (price - vwap) / vwap * 100
    
    # VWAP 核心形态特征
    structure_tag: str = "常规"       # 蓄势走平3天 / 回踩不碰 / 强势突破 / 破位弱势
    consolidation_days: int = 0       # 在 VWAP 上方走平蓄势天数 (1~3天)
    pullback_no_touch: bool = False   # 是否处于在 VWAP 上方回踩不碰状态
    is_above_vwap: bool = False       # 现价是否在 VWAP 之上
    
    # 大趋势 K 线特征
    trend_support_level: float = 0.0  # 大趋势通道/均线支撑价位
    trend_slope_deg: float = 0.0      # 通道斜率角度
    has_kline_launch_sig: bool = False# 日K/2D 是否有【🚀启动】信号
    trend_desc: str = ""              # 大趋势描述 (例如: "日K通道下轨支撑")
    
    # 最终决策信号
    signal_type: str = "WATCH"        # PRE_ORDER(预下单) / PULLBACK_BUY(回踩不碰) / BREAKOUT(起爆) / WEAK_EXIT(破位止损点) / WATCH(观望)
    signal_level: str = "⚪"          # 🎯 预下单 / 🚀 回踩启动 / ⚡ 放量加速 / ⚠️ 破位反抽 / ⏱️ 观察
    signal_desc: str = ""             # 详细解释说明
    stop_loss_price: float = 0.0      # 极窄建议止损位 (通常紧贴 VWAP 或次低点)
    update_time: str = ""             # 更新时间戳


_IPO_NAME_MEM_CACHE: Dict[str, str] = {}

def resolve_fast_ipo_name(clean_code: str) -> str:
    """0ms 本地优先解析新股次新股名称，杜绝网络阻塞与 Warning 刷屏"""
    if clean_code in _IPO_NAME_MEM_CACHE:
        return _IPO_NAME_MEM_CACHE[clean_code]

    try:
        from ats.new_stock_fetcher import NewStockFetcher
        fetcher = NewStockFetcher.get_instance()
        ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
        if clean_code in ipo_dict:
            nm = ipo_dict[clean_code].get("name", "")
            if nm:
                _IPO_NAME_MEM_CACHE[clean_code] = nm
                return nm
    except Exception:
        pass

    if not clean_code.startswith("920"):
        try:
            from sys_utils import resolve_stock_name
            nm = resolve_stock_name(clean_code)
            if nm and "个股" not in nm and not nm.startswith("0") and not nm.startswith("6") and not nm.startswith("3"):
                _IPO_NAME_MEM_CACHE[clean_code] = nm
                return nm
        except Exception:
            pass

    fallback = f"N{clean_code[-4:]}" if clean_code.startswith(("920", "688", "301")) else f"新股{clean_code}"
    _IPO_NAME_MEM_CACHE[clean_code] = fallback
    return fallback


class IPOVWAPDetectorEngine:
    """新股次新股 VWAP 预判结构与异动检测引擎"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.fetcher = TDXRealtimeFetcher.get_instance()
        # 短期内存评估缓存 (避免高频轮询重复计算相同周期的 K 线)
        self._eval_cache: Dict[str, Tuple[VWAPDetectorSignal, float]] = {}
        self._cache_ttl = 2.0  # 2 秒 TTL

    def analyze_stock(self, code: str, force_refresh: bool = False) -> VWAPDetectorSignal:
        """
        全面分析一只标的的 10日 VWAP 结构、走平蓄势天数、回踩不碰特征及大趋势 K 线支撑
        """
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        now_ts = time.time()
        
        if not force_refresh and clean_code in self._eval_cache:
            cached_sig, cache_time = self._eval_cache[clean_code]
            if now_ts - cache_time < self._cache_ttl:
                return cached_sig

        name = resolve_fast_ipo_name(clean_code)
        sig = VWAPDetectorSignal(code=clean_code, name=name, update_time=time.strftime("%H:%M:%S"))

        try:
            # 1. 获取 10 日多日分时与 VWAP 数据 (若是新股首日，自动返回当天全部数据)
            df_multi = self.fetcher.fetch_multi_day_intraday_bars(clean_code, days=10)
            if df_multi is None or df_multi.empty:
                # 降级拉取 1 日分时或实时快照
                df_multi = self.fetcher.fetch_multi_day_intraday_bars(clean_code, days=1)
                
            if df_multi is not None and not df_multi.empty:
                self._evaluate_vwap_structure(df_multi, sig)
            else:
                sig.signal_desc = "分时数据拉取中..."
                
            # 2. 获取大趋势 K 线通道与支撑 (日K 与 2D K线)
            self._evaluate_kline_trend(clean_code, sig)

            # 3. 综合裁决预下单与异动信号 (操盘手核心逻辑)
            self._synthesize_final_decision(sig)

        except Exception as e:
            logger.debug(f"分析标的 {clean_code} 结构异常: {e}")
            sig.signal_desc = f"分析提示: {e}"

        self._eval_cache[clean_code] = (sig, now_ts)
        return sig

    def _evaluate_vwap_structure(self, df: pd.DataFrame, sig: VWAPDetectorSignal):
        """
        评估分时多日 VWAP 结构：
        1. 计算当前现价、VWAP 均价与偏离度；
        2. 识别是否在 VWAP 上走平 1~3 天 (振幅收敛，紧贴 VWAP)；
        3. 识别是否在 VWAP 上方回踩不碰。
        """
        last_row = df.iloc[-1]
        p = float(last_row.get("close", last_row.get("price", 0.0)))
        vw = float(last_row.get("vwap", p))
        op = float(df.iloc[0].get("open", p))

        sig.price = p
        sig.vwap = vw
        sig.is_above_vwap = (p >= vw)
        if vw > 0:
            sig.vwap_diff_pct = round((p - vw) / vw * 100.0, 2)

        # 每日分组分析
        if "date" in df.columns:
            date_groups = df.groupby("date")
            dates = list(date_groups.groups.keys())
        else:
            dates = ["today"]
            date_groups = [(dates[0], df)]

        n_days = len(dates)
        
        # ── 关键算法 1: 检测在 VWAP 附近走平蓄势天数 (1~3天) ──
        # 核心定义: 每日分时价格紧密围绕/贴合 VWAP 上方，全日振幅 <= 4.0%，且收盘价在 VWAP 之上或偏离 <= 1.5%
        flat_days_count = 0
        # 倒序检查最近 3 个交易日 (从最新前一日往前回溯)
        recent_dates = dates[-4:-1] if n_days >= 4 else (dates[:-1] if n_days > 1 else dates)
        
        for d in reversed(recent_dates):
            day_df = df[df["date"] == d] if "date" in df.columns else df
            if day_df.empty or len(day_df) < 10:
                continue
            d_high = float(day_df["high"].max()) if "high" in day_df.columns else float(day_df["close"].max())
            d_low = float(day_df["low"].min()) if "low" in day_df.columns else float(day_df["close"].min())
            d_vw = float(day_df["vwap"].iloc[-1]) if "vwap" in day_df.columns else float(day_df["close"].mean())
            d_close = float(day_df["close"].iloc[-1])
            
            # 日内振幅
            d_range_pct = (d_high - d_low) / d_low * 100.0 if d_low > 0 else 10.0
            # 收盘与该日 VWAP 距离
            d_diff_to_vw = abs(d_close - d_vw) / d_vw * 100.0 if d_vw > 0 else 10.0
            
            # 满足在 VWAP 走平蓄势条件: 振幅收敛 (< 5.0%) 且贴合 VWAP (< 2.5%) 且低点未深度破位
            if d_range_pct <= 5.0 and d_diff_to_vw <= 2.5 and d_low >= d_vw * 0.975:
                flat_days_count += 1
            else:
                break
                
        sig.consolidation_days = flat_days_count

        # ── 关键算法 2: 检测“在 VWAP 上方回踩不碰 / 浅踩不破” ──
        # 核心定义:
        # 当日或近期价格处于 VWAP 之上 (price > vwap)
        # 最近 15~30 根分时线曾向 VWAP 靠拢下探 (min_low 逼近 vwap, 例如 0% <= (min_low - vwap)/vwap <= 1.5%)
        # 但坚决未跌穿 VWAP (min_low >= vwap * 0.996)，随后反身向上拉起 (当前 price > min_low 且最新分时为红柱)
        today_df = df[df["date"] == dates[-1]] if "date" in df.columns else df
        if len(today_df) >= 15 and sig.is_above_vwap:
            recent_sub = today_df.tail(30)
            rec_low = float(recent_sub["low"].min()) if "low" in recent_sub.columns else float(recent_sub["close"].min())
            rec_vwap = float(recent_sub["vwap"].iloc[-1]) if "vwap" in recent_sub.columns else vw
            
            # 回踩逼近 VWAP: 距离在 0% ~ 1.8% 之间，且未跌破 (rec_low >= rec_vwap * 0.995)
            low_dist = (rec_low - rec_vwap) / rec_vwap * 100.0 if rec_vwap > 0 else 999.0
            if 0.0 <= low_dist <= 2.0 and p > rec_low:
                sig.pullback_no_touch = True

        # 设置建议止损价位: 严格锚定在 VWAP 处 (买入打止损说明买点错了，止损极窄)
        sig.stop_loss_price = round(vw * 0.995, 2)

    def _evaluate_kline_trend(self, code: str, sig: VWAPDetectorSignal):
        """
        评估大趋势 K 线 (日K/2D 通道支撑与启动信号):
        利用 fetcher.fetch_kline_bars 计算通道下轨与启动标签
        """
        try:
            # 1. 拉取日 K 线 (100 根)
            df_day = self.fetcher.fetch_kline_bars(code, category="day", count=100)
            if df_day is not None and not df_day.empty and len(df_day) >= 5:
                # 检查通道与均线支撑
                last_k = df_day.iloc[-1]
                c = float(last_k.get("close", sig.price))
                l = float(last_k.get("low", c))
                ma5 = float(last_k.get("ma5", c)) if "ma5" in last_k else c
                
                # 简易通道下轨估计: 20日最低点或布林下轨
                if "lower" in df_day.columns:
                    lower_band = float(last_k.get("lower", l))
                else:
                    lower_band = float(df_day["low"].tail(20).min()) if len(df_day) >= 20 else l
                    
                sig.trend_support_level = round(lower_band, 2)
                
                # 检查是否有底部企稳或启动阳线 (缩量横盘后第一根阳线或突破 MA5)
                # 检查前几根 K 线的下影线或连续低位星线
                recent_day_lows = df_day["low"].tail(5).tolist()
                is_double_bottom = len(recent_day_lows) >= 4 and abs(recent_day_lows[-1] - min(recent_day_lows)) / c < 0.02
                
                if c >= ma5 and (c - lower_band) / lower_band < 0.08:
                    sig.has_kline_launch_sig = True
                    sig.trend_desc = "日K通道下轨支撑企稳"
                elif is_double_bottom:
                    sig.has_kline_launch_sig = True
                    sig.trend_desc = "日K双底反转企稳"
                else:
                    sig.trend_desc = "常规震荡"
                    
                # 计算近 5 根 K 线斜率
                if len(df_day) >= 5:
                    c_first = float(df_day["close"].iloc[-5])
                    c_last = float(df_day["close"].iloc[-1])
                    if c_first > 0:
                        slope = (c_last - c_first) / c_first * 100.0
                        sig.trend_slope_deg = round(math.degrees(math.atan(slope / 5.0)), 1)
        except Exception as e:
            logger.debug(f"评估标的 {code} K线趋势异常: {e}")

    def _synthesize_final_decision(self, sig: VWAPDetectorSignal):
        """
        根据操盘手现场明确的超短线买卖点哲学，裁决最终信号与预警：
        - 黄金信号 1: 🎯 [预下单·VWAP蓄势] —— 在 VWAP 走平 1~3 天，价格紧贴 VWAP 上方，K线支撑，可预挂单；
        - 黄金信号 2: 🚀 [回踩不碰·启动] —— 在 VWAP 之上运行，回踩不碰，极限优质买点，止损极窄；
        - 突破信号 3: ⚡ [放量突破·起爆] —— 突破 VWAP，斜率拉升；
        - 弱势警示 4: ⚠️ [跌破VWAP·高点止损点] —— 破位弱势，反抽只作止损逃命点，严禁买入！
        """
        # 1. 破位弱势股直接拦截 (VWAP价格区域是很多破位股反弹的止损点)
        if not sig.is_above_vwap and sig.vwap_diff_pct < -0.8:
            sig.signal_type = "WEAK_EXIT"
            sig.signal_level = "⚠️ 破位止损点"
            sig.structure_tag = "破位运行"
            sig.signal_desc = f"现价处于 VWAP 下方 ({sig.vwap_diff_pct:+.1f}%)，反抽 VWAP({sig.vwap:.2f}) 仅为被套止损点，严禁开仓!"
            return

        # 2. 黄金买点: 回踩不碰 (回踩靠拢 VWAP 但不碰到跌破，极限买点)
        if sig.pullback_no_touch:
            sig.signal_type = "PULLBACK_BUY"
            sig.signal_level = "🚀 回踩启动"
            sig.structure_tag = "回踩不碰"
            sig.signal_desc = f"价格在 VWAP({sig.vwap:.2f}) 之上强势回踩不碰! 极限买点确立，建议止损价 {sig.stop_loss_price:.2f}元"
            return

        # 3. 预判潜伏结构: 在 VWAP 走平 1~3 天 (博反弹/加速预下单)
        if sig.consolidation_days >= 1:
            sig.signal_type = "PRE_ORDER"
            day_str = f"{sig.consolidation_days}天" if sig.consolidation_days < 3 else "3天+"
            sig.signal_level = "🎯 预下单"
            sig.structure_tag = f"在VWAP走平{day_str}"
            k_desc = f" ({sig.trend_desc})" if sig.trend_desc else ""
            sig.signal_desc = f"在 VWAP 上方已走平蓄势 {day_str}{k_desc}，可预挂单潜伏，博加速拉升! 破 VWAP({sig.vwap:.2f}) 即止损"
            return

        # 4. 放量突破 / 强势上攻
        if sig.is_above_vwap and sig.vwap_diff_pct >= 2.0:
            sig.signal_type = "BREAKOUT"
            sig.signal_level = "⚡ 放量加速"
            sig.structure_tag = "强势主升"
            sig.signal_desc = f"现价站上 VWAP 上方 +{sig.vwap_diff_pct:.1f}%，分时多头推升加速中"
            return

        # 5. 常规在 VWAP 上方运行
        if sig.is_above_vwap:
            sig.signal_type = "WATCH"
            sig.signal_level = "⏱️ 站稳VWAP"
            sig.structure_tag = "线上震荡"
            sig.signal_desc = f"处于 VWAP({sig.vwap:.2f}) 之上震荡观察，等待回踩不碰或走平确认"
            return

        # 6. 默认观望
        sig.signal_type = "WATCH"
        sig.signal_level = "⚪ 观望"
        sig.structure_tag = "常规震荡"
        sig.signal_desc = "多空平衡，暂无极限预下单结构"

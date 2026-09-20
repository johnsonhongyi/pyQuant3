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
"""
新股次新股 VWAP 策略与交易指挥官：【新股情绪全面感知与多周期通道突破策略 1 代】
========================================================================================

【版本背景与实战痛点】：
传统的新股/次新股监控与交易策略往往陷入“见山是山”的教条陷阱：
1. 股价在 VWAP 之下即一刀切认定为“破位出局”，无法识别 60F 级别底台蓄势、下降通道突破与大箱体共振；
2. 面对先行者龙头暴涨冲顶，未能结合 A 股 T+1 交易制度，导致在次日冲高时误开仓追高成为接盘侠；
3. 先行者龙头冲顶由多次 30% 临停推升，冲顶加速后复牌往往戛然而止剧烈跳水，事后市价抛售根本无法成交。

【策略 1 代四大核心技术支柱】：
1. 💡 多周期共振与通道突破预埋（蓝色光标 300058 同款架构）：
   - 识别 3~4 日大平底箱体（低点收敛 <= 4.5%）；
   - 识别 60F 突破下降通道阻力线，且尾盘放量收在当日最高价附近；
   - 防守线从遥远的 10d VWAP 智能迁移至 60F 底台支撑位 -0.8%，向下风险不足 1.5%；
   - 生成 SWING_PREORDER (🔭 通道突破) 限价预埋买单，享有免遭全局避险误杀特权。
2. 🌋 临停计数与冲刺高潮感知（沈鼓集团 601091 同款架构）：
   - 追踪日内/跨日累积 30%/60% 临停断点，记录 suspension_count (2~4次)；
   - 感知聚集的人气量能与加速冲刺，严密防御复牌后的断崖式跳水。
3. 💻 计算机算法提前设计高抛挂单限价 (climax_preset_sell_price)：
   - 操盘手实战铁律：高位能够从容逃顶的筹码，均是计算机提前根据算法挂出的限价单；
   - 提前计算顶点挂单价（如 ≈ 82.18 元），平仓阶段以 LIMIT 限价单在交易所提前排队成交。
4. 🛑 T+1 追高买入禁令守卫 (is_t1_forbidden_buy)：
   - 严格区分上市首日（当天有首发惜售价值）与上市次日及之后；
   - 非首日且高位冲刺狂飙（涨幅 >= 15% 或偏离 VWAP >= 20% 或临停），严禁开新仓追高买入！
"""

import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.strategy.channel_secondary_buy_strategy import (
    evaluate_channel_secondary_buy,
    SecondaryBuyStage,
    IPOTradePlan,
)
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
    
    # 早盘基石价与时间切片特征 (9:15-10:00 核心优化)
    open_anchor_price: float = 0.0    # 早盘开盘基石价 (Anchor Price)
    morning_low_price: float = 0.0    # 早盘开盘前30分钟最低价
    launch_time_str: str = ""         # 拔地而起启动时间点 (如 "09:32")
    launch_slope_deg: float = 0.0     # 拔地而起启动角斜率 (度)
    vwap_adhesion_ratio: float = 0.0  # VWAP 站稳率 / 贴线率 (0~100%)
    sbc_activity_pct: float = 0.0     # SBC 多日综合活跃度%
    is_ipo_first_day: bool = False    # 是否为首发上市首日/新股极早期
    is_morning_scare_rebound: bool = False # 是否为早盘集合竞价恐吓深跌后快速拉起
    
    # 赛马冒泡排位特征 (逐日赛马优化，冒泡寻找爆款)
    horse_race_score: float = 50.0    # 赛马综合动能得分 (0~100)
    horse_race_tier: str = "⚪ 观察"   # 🥇 领头羊 / 🥈 梯队前锋 / 🎯 线上蓄势 / ⏱️ 迟滞跟风 / 🚨 疯狂平仓 / ⛔ 破位出局
    horse_race_rank: int = 999        # 赛马排位 (1, 2, 3...)

    # 底部结构与动能抓手 (全面进化操盘手超短哲学：底部缩量平底/双底企稳、动能拐头加速与预埋单)
    has_bottom_base: bool = False     # 是否构筑了底部平底/双底企稳扎实结构
    base_support_level: float = 0.0   # 底部平台核心防守支撑价
    base_consolidation_bars: int = 0  # 底部横盘缩量蓄势 Bar 数量
    base_inflection_confirmed: bool = False # 底部动能拐头与放量上翘是否确认
    rebound_to_vwap_space_pct: float = 0.0  # 距 VWAP 的向上反弹盈亏比空间%

    # 操盘手深度实战哲学：临停计数、计算机提前挂单卖出、T+1制度守卫与多日通道突破
    suspension_count: int = 0         # 临停触发次数 (如沈鼓集团累计4次临停高潮)
    climax_preset_sell_price: float = 0.0 # 计算机算法提前计算好的高抛挂单卖出价
    is_t1_forbidden_buy: bool = False # T+1 次日+狂飙追高禁令 (只卖不买，防核按钮)
    is_swing_channel_breakout: bool = False # 60F下降通道突破+多日平底箱体尾盘收新高 (蓝色光标同款)
    multi_day_base_support: float = 0.0 # 多日大箱体底台支撑价 (如蓝色光标 12.88)
    
    # 大趋势 K 线特征
    trend_support_level: float = 0.0  # 大趋势通道/均线支撑价位
    trend_slope_deg: float = 0.0      # 通道斜率角度
    has_kline_launch_sig: bool = False# 日K/2D 是否有【🚀启动】信号
    trend_desc: str = ""              # 大趋势描述 (例如: "日K通道下轨支撑")
    
    # 最终决策信号 (买错就出局终极闭环)
    signal_type: str = "WATCH"        # PRE_ORDER / PULLBACK_BUY / BREAKOUT / WEAK_EXIT / CLIMAX_EXIT / IPO_FIRST_BUY / WATCH
    signal_level: str = "⚪"          # 🎯 预下单 / 🚀 回踩启动 / 🔥 首发吸筹 / ⚡ 放量加速 / 🚨 疯狂平仓 / ⛔ 破位出局 / ⏱️ 观察
    signal_tier: str = "WATCH"        # 👑 SSS 绝杀级 / 🥇 S 级接力 / 🎯 A 级潜伏 / 🚨 ALERT 警报 / ⏱️ WATCH
    signal_desc: str = ""             # 详细解释说明
    stop_loss_price: float = 0.0      # 极窄建议止损位 (通常紧贴 VWAP 或次低点，买错就出局)
    is_climax_exit: bool = False      # 是否触发极端高潮平仓 (天量滞涨/过山车预警)
    
    # 全局集中交易调度仲裁 (交易中心汇交全数据后反哺，消除“各管一摊，不知山外有山”)
    global_fleet_role: str = ""       # LEADER / VANGUARD / FOLLOWER / STOP_LOSS / CLIMAX_EXIT / ICE_ABORT
    global_arbitration_desc: str = "" # 全局仲裁决议说明 (例如: "🥇【全池领头羊】96分 09:31启动，集中重仓 35%！")
    relative_to_leader_gap: float = 0.0 # 与全池第一领头羊的动能得分差值
    
    # 长期通道企稳与底部结构次级买点 (688826/300058同款架构)
    channel_stage: str = ""           # SECONDARY_BUY / PULLBACK_STABLE / FIRST_BREAKOUT / BASE_DRYUP / DESCENDING_CHANNEL / INVALIDATED
    channel_stage_cn: str = ""        # 👑 次级买点 / ⏳ 缩量回踩 / 🚀 首次试盘 / 📦 平底箱体 / 📉 通道寻底 / ⛔ 破位失效
    higher_low_stop: float = 0.0      # 次级买点抬高底防守止损位
    base_low_invalid: float = 0.0     # 大底极限防守位 (跌破彻底作废)
    quality_grade: str = ""           # 形态评级: SS / S / A
    strategy_tag: str = ""            # 策略 Tag: CHANNEL_SECONDARY_BUY / IPO_BID_SURGE / IPO_VWAP_STABLE / SUBNEW_PULLBACK_REENTRY
    trade_plan: Optional[Any] = None  # 不可变 IPOTradePlan 对象

    update_time: str = ""             # 更新时间戳
    extra_data: Dict[str, Any] = field(default_factory=dict)  # 后台预提取的日线指标与自定义列数据 (0ms内存供UI读取)




_IPO_NAME_MEM_CACHE: Dict[str, str] = {}
_DISK_NAME_JSON_CACHE: Optional[Dict[str, str]] = None

def resolve_fast_ipo_name(clean_code: str) -> str:
    """0ms 本地优先解析新股次新股名称，杜绝网络阻塞与 Warning 刷屏，纯内存无锁设计"""
    clean_code = str(clean_code).strip().zfill(6)
    if clean_code in _IPO_NAME_MEM_CACHE:
        return _IPO_NAME_MEM_CACHE[clean_code]

    # 1. 优先从 NewStockFetcher 内存快照获取
    try:
        from ats.new_stock_fetcher import NewStockFetcher
        fetcher = NewStockFetcher.get_instance()
        ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
        if clean_code in ipo_dict:
            nm = str(ipo_dict[clean_code].get("name", "")).strip()
            if nm and not nm.startswith("个股_") and not nm.isdigit() and nm != clean_code:
                _IPO_NAME_MEM_CACHE[clean_code] = nm
                return nm
    except Exception:
        pass

    # 2. 查本地磁盘已有的 stock_name_cache.json 内存字典
    try:
        from sys_utils import _resolved_name_cache
        if clean_code in _resolved_name_cache:
            nm = _resolved_name_cache[clean_code]
            if nm and not nm.startswith("个股_") and not nm.isdigit() and nm != clean_code:
                _IPO_NAME_MEM_CACHE[clean_code] = nm
                return nm
    except Exception:
        pass

    # 3. 优先从 IPC 的实时行情 df 中提取名字 (纯内存 0ms，零 H5，对齐主系统)
    try:
        from multi_period_strategy_engine import get_global_ipc_sync_manager
        ipc_mgr = get_global_ipc_sync_manager()
        if ipc_mgr:
            ipc_df = ipc_mgr.get_current_df()
            if ipc_df is not None and not ipc_df.empty:
                nm = ""
                cand_idx = [clean_code, clean_code.lstrip('0'), f"sh{clean_code}", f"sz{clean_code}", f"bj{clean_code}"]
                for c_k in cand_idx:
                    if c_k in ipc_df.index and 'name' in ipc_df.columns:
                        nm = str(ipc_df.loc[c_k, 'name']).strip()
                        break
                if not nm and 'code' in ipc_df.columns and 'name' in ipc_df.columns:
                    matched = ipc_df[ipc_df['code'].astype(str).str.zfill(6) == clean_code]
                    if not matched.empty:
                        nm = str(matched.iloc[0]['name']).strip()
                if nm and not nm.startswith("个股_") and not nm.isdigit() and nm != clean_code:
                    _IPO_NAME_MEM_CACHE[clean_code] = nm
                    return nm
    except Exception:
        pass

    # 4. 查本地 datacsv/stock_name_cache.json 文件 (全市场 5600+ 股票名称 UTF-8 内存镜像)
    global _DISK_NAME_JSON_CACHE
    if _DISK_NAME_JSON_CACHE is None:
        _DISK_NAME_JSON_CACHE = {}
        try:
            from sys_utils import get_app_root
            cache_file = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8", errors="ignore") as f:
                    _DISK_NAME_JSON_CACHE = json.load(f)
        except Exception:
            _DISK_NAME_JSON_CACHE = {}
    if clean_code in _DISK_NAME_JSON_CACHE:
        nm = str(_DISK_NAME_JSON_CACHE[clean_code]).strip()
        if nm and not nm.startswith("个股_") and not nm.isdigit() and nm != clean_code:
            _IPO_NAME_MEM_CACHE[clean_code] = nm
            return nm

    # 5. 终极轻量直连兜底 (0.8s 极速 HTTP，彻底零 HDF5，精准前缀: 5/6/11 -> sh, 9/8/4 -> bj, 0/3/1 -> sz)
    try:
        import urllib.request
        prefix = "sh" if clean_code.startswith(("6", "5", "11")) else ("bj" if clean_code.startswith(("9", "8", "4")) else "sz")
        url = f"http://hq.sinajs.cn/list={prefix}{clean_code}"
        req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            content = resp.read().decode("gbk", errors="ignore")
            if '="' in content:
                parts = content.split('="')[1].split(',')
                if parts and parts[0]:
                    real_name = parts[0].strip()
                    if real_name and not real_name.startswith("个股_") and real_name != clean_code and not real_name.isdigit():
                        _IPO_NAME_MEM_CACHE[clean_code] = real_name
                        if _DISK_NAME_JSON_CACHE is not None:
                            _DISK_NAME_JSON_CACHE[clean_code] = real_name
                            try:
                                from sys_utils import get_app_root
                                c_file = os.path.join(get_app_root(), "datacsv", "stock_name_cache.json")
                                with open(c_file, "w", encoding="utf-8") as f:
                                    json.dump(_DISK_NAME_JSON_CACHE, f, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                        return real_name
    except Exception:
        pass

    fallback = f"N{clean_code[-4:]}" if clean_code.startswith(("920", "688", "301")) else f"新股{clean_code}"
    _IPO_NAME_MEM_CACHE[clean_code] = fallback
    return fallback


def preload_ipo_stock_names(codes: List[str]):
    """单线程批量预热解析全量股票名称 (纯内存，零 HDF5，零 I/O 阻塞)"""
    for cd in codes:
        try:
            clean_cd = "".join(c for c in str(cd) if c.isdigit()).zfill(6)
            if clean_cd:
                resolve_fast_ipo_name(clean_cd)
        except Exception:
            pass


def _fetch_single_day_ohlc_direct(clean_code: str, dl: int = 60) -> Optional[pd.DataFrame]:
    """
    单只股票日线 fastohlc 极速读取 (纯通达信本地 txt 或直连网络，零 H5，零锁)
    """
    try:
        from JSONData import tdx_data_Day as tdd
        df = tdd.get_tdx_Exp_day_to_df(clean_code, dl=dl, fastohlc=True)
        if df is not None and not df.empty:
            return df.copy()
    except Exception:
        pass
    return None


def batch_fetch_day_kline_fast(codes: List[str], dl: int = 60) -> Dict[str, pd.DataFrame]:
    """
    【对齐 --sbc-holdings 的极简稳定单线程顺序日线获取引擎】
    - 纯单线程顺序读取通达信本地日线或网络，单只仅 1~2ms，全量 30 只仅需 30ms；
    - 零线程池、零进程池、零 HDF5，彻底杜绝多线程竞争与 C 库底层冲突。
    """
    clean_codes = ["".join(c for c in str(cd) if c.isdigit()).zfill(6) for cd in codes]
    clean_codes = list(dict.fromkeys(clean_codes))
    if not clean_codes:
        return {}

    res_map = {}
    for c in clean_codes:
        df = _fetch_single_day_ohlc_direct(c, dl)
        if df is not None and not df.empty:
            res_map[c] = df
    return res_map


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
        # 盘中历史前 9 天分时长效缓存 (标的代码 -> (日期YYYY-MM-DD, 历史DataFrame))
        # 彻底攻克“现在还是慢”：首次拉取 10 天分时并缓存前 9 天；高频轮询仅拉取当天 1 天(20ms)，内存拼接极速重算 VWAP
        self._history_multi_day_cache: Dict[str, Tuple[str, pd.DataFrame]] = {}

    def _fetch_multi_day_bars_fast(self, clean_code: str, days: int = 10) -> Tuple[Optional[pd.DataFrame], float]:
        """
        【增量极速分时引擎】盘中长效缓存前 N-1 天历史分时 + 当日时间戳增量复用
        - 优先利用底层 TDXGlobalCachePool 的 RamDisk 与时间戳增量；
        - 单股耗时从 450ms 暴降至 0~2ms (命中缓存) 或 15~25ms (网络轻量增量)；
        - 与 SBC 走势窗口 100% 共享复用底层分时与计算结果。
        """
        t0 = time.perf_counter()
        today_date_str = time.strftime("%Y-%m-%d")

        # 优先使用底层统一的多日分时获取接口 (自带静态缓存 + 时间戳增量复用 + RamDisk 持久化)
        df_multi = self.fetcher.fetch_multi_day_intraday_bars(clean_code, days=days)
        if df_multi is None or df_multi.empty:
            df_multi = self.fetcher.fetch_multi_day_intraday_bars(clean_code, days=1)

        # 维护 _history_multi_day_cache 兼容性
        if df_multi is not None and not df_multi.empty and "date" in df_multi.columns:
            try:
                dates = sorted(df_multi["date"].astype(str).unique())
                if len(dates) > 1:
                    last_d = dates[-1]
                    df_hist_part = df_multi[df_multi["date"].astype(str) < last_d].copy()
                    if not df_hist_part.empty:
                        self._history_multi_day_cache[clean_code] = (today_date_str, df_hist_part)
            except Exception:
                pass

        cost_ms = (time.perf_counter() - t0) * 1000
        return df_multi, cost_ms

    def analyze_stock(self, code: str, force_refresh: bool = False, day_df: Optional[pd.DataFrame] = None) -> VWAPDetectorSignal:
        """
        全面分析一只标的的 10日 VWAP 结构、走平蓄势天数、回踩不碰特征及大趋势 K 线支撑
        """
        t_total_start = time.perf_counter()
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        now_ts = time.time()
        
        if not force_refresh and clean_code in self._eval_cache and day_df is None:
            cached_sig, cache_time = self._eval_cache[clean_code]
            if now_ts - cache_time < self._cache_ttl:
                return cached_sig

        name = resolve_fast_ipo_name(clean_code)
        sig = VWAPDetectorSignal(code=clean_code, name=name, update_time=time.strftime("%H:%M:%S"))

        bars_ms = 0.0
        strat_ms = 0.0
        try:
            # 1. 增量极速获取 10 日多日分时与 VWAP 数据
            df_multi, bars_ms = self._fetch_multi_day_bars_fast(clean_code, days=10)
                
            t_strat_start = time.perf_counter()
            if df_multi is not None and not df_multi.empty:
                self._evaluate_vwap_structure(df_multi, sig, day_df=day_df)
                self._evaluate_bottom_base_structure(df_multi, sig, day_df=day_df)
            else:
                sig.signal_desc = "分时数据拉取中..."

            # ⚡ 早盘集合竞价与实时盘口快照融合 (09:15~09:30 时段分钟线尚未生成今日 Bar，自动融合最新盘口)
            current_hm = time.strftime("%H:%M")
            if "09:15" <= current_hm < "09:30" or sig.price <= 0:
                try:
                    snap = self.fetcher.fetch_stock_snapshot(clean_code)
                    if snap and isinstance(snap, dict):
                        sp_p = float(snap.get("price", 0.0))
                        b1_p = float(snap.get("buy", snap.get("bid1", 0.0)))
                        a1_p = float(snap.get("sell", snap.get("ask1", 0.0)))
                        op_p = float(snap.get("open", 0.0))
                        lc_p = float(snap.get("last_close", 0.0))

                        eff_p = sp_p if sp_p > 0 else (b1_p if b1_p > 0 else (op_p if op_p > 0 else (a1_p if a1_p > 0 else 0.0)))
                        if eff_p > 0:
                            sig.price = eff_p
                            if lc_p > 0:
                                sig.change_pct = round((eff_p - lc_p) / lc_p * 100.0, 2)
                            if sig.vwap > 0:
                                sig.vwap_diff_pct = round((eff_p - sig.vwap) / sig.vwap * 100.0, 2)
                            sig.is_above_vwap = (eff_p >= sig.vwap)
                except Exception:
                    pass
                
            # 2. 获取大趋势 K 线通道与支撑 (日K 与 2D K线，优先复用已有的 day_df，或使用 fastohlc 极速模式)
            self._evaluate_kline_trend(clean_code, sig, day_df=day_df)

            # 3. 综合裁决预下单与异动信号 (操盘手核心逻辑)
            self._synthesize_final_decision(sig)
            strat_ms = (time.perf_counter() - t_strat_start) * 1000

        except Exception as e:
            logger.debug(f"分析标的 {clean_code} 结构异常: {e}")
            sig.signal_desc = f"分析提示: {e}"

        total_cost_ms = (time.perf_counter() - t_total_start) * 1000
        sig.extra_data["_perf_bars_ms"] = round(bars_ms, 1)
        sig.extra_data["_perf_strat_ms"] = round(strat_ms, 1)
        sig.extra_data["_perf_total_ms"] = round(total_cost_ms, 1)

        self._eval_cache[clean_code] = (sig, now_ts)
        return sig

    def _evaluate_vwap_structure(self, df: pd.DataFrame, sig: VWAPDetectorSignal, day_df: Optional[pd.DataFrame] = None):
        """
        评估分时多日 VWAP 结构与早盘基石价时间切片：
        1. 计算当前现价、VWAP 均价与偏离度；
        2. 计算开盘基石价 (Anchor)、早盘最低价、启动时间点与拔地而起斜率；
        3. 计算 VWAP 站稳率与 SBC 活跃度；
        4. 识别首发上市惜售吸筹、早盘竞价恐吓洗盘、极端高潮放量滞涨平仓；
        5. 识别是否在 VWAP 上走平 1~3 天与回踩不碰特征。
        """
        last_row = df.iloc[-1]
        p = float(last_row.get("close", last_row.get("price", 0.0)))
        vw = float(last_row.get("vwap", p))
        op = float(df.iloc[0].get("open", p))

        sig.price = p
        sig.vwap = vw
        sig.open_anchor_price = op
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

        # ⚡ 涨跌幅精确计算：优先提取上一交易日收盘价 (昨收 last_close)
        last_close = 0.0
        if len(dates) >= 2:
            prev_day_df = df[df["date"] == dates[-2]]
            if not prev_day_df.empty:
                last_close = float(prev_day_df.iloc[-1].get("close", 0.0))
        if last_close <= 0 and day_df is not None and not day_df.empty:
            if len(day_df) >= 2:
                last_close = float(day_df.iloc[-2].get("close", 0.0))
        if last_close <= 0:
            last_close = float(last_row.get("last_close", last_row.get("prev_close", 0.0)))

        if last_close > 0 and p > 0:
            sig.change_pct = round((p - last_close) / last_close * 100.0, 2)

        n_days = len(dates)
        today_df = df[df["date"] == dates[-1]] if "date" in df.columns else df

        # ── 核心特征 1: 计算 SBC 多日综合活跃度 (对齐 SBC 走势图均活跃度) ──
        try:
            day_amps = []
            for d in dates:
                sub_d = df[df["date"] == d] if "date" in df.columns else df
                if sub_d.empty:
                    continue
                d_h = float(sub_d["high"].max()) if "high" in sub_d.columns else float(sub_d["close"].max())
                d_l = float(sub_d["low"].min()) if "low" in sub_d.columns else float(sub_d["close"].min())
                if d_l > 0:
                    day_amps.append((d_h - d_l) / d_l * 100.0)
            if day_amps:
                sig.sbc_activity_pct = round(float(np.mean(day_amps)), 1)
        except Exception:
            sig.sbc_activity_pct = 0.0

        # ── 核心特征 2: 早盘开盘基石价、最低价与 9:15-10:00 时间切片拔地而起 ──
        if not today_df.empty:
            t_open = float(today_df.iloc[0].get("open", op))
            sig.open_anchor_price = t_open

            # 统计早盘前 30 分钟 (至多前 30 根 K 棒) 最低点
            morning_sub = today_df.head(30)
            m_low = float(morning_sub["low"].min()) if "low" in morning_sub.columns else float(morning_sub["close"].min())
            sig.morning_low_price = m_low

            # 统计今日在 VWAP 之上的站稳率
            above_count = 0
            for _, r in today_df.iterrows():
                bar_c = float(r.get("close", 0.0))
                bar_vw = float(r.get("vwap", bar_c))
                if bar_c >= bar_vw:
                    above_count += 1
            sig.vwap_adhesion_ratio = round(above_count / len(today_df) * 100.0, 1)

            # 寻找拔地而起启动时点: 首次价格连续 3 根站上 VWAP 并拉开与开盘价差距
            launch_found = False
            for idx, (_, r) in enumerate(today_df.iterrows()):
                bar_c = float(r.get("close", 0.0))
                bar_vw = float(r.get("vwap", bar_c))
                if bar_c >= bar_vw and bar_c >= t_open * 1.008:
                    # 标准分时时间换算 (杜绝 09:179 等越界)
                    raw_t = str(r.get("time", "")).strip()
                    calc_time = ""
                    if len(raw_t) >= 5 and ":" in raw_t:
                        parts = raw_t[-5:].split(":")
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            calc_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                    if not calc_time:
                        digits = "".join(c for c in raw_t if c.isdigit())
                        if len(digits) >= 4:
                            calc_time = f"{int(digits[:2]):02d}:{int(digits[2:4]):02d}"
                    if not calc_time:
                        if idx < 120:
                            tot_m = 9 * 60 + 30 + idx
                        else:
                            tot_m = 13 * 60 + (idx - 120)
                        calc_time = f"{tot_m // 60:02d}:{tot_m % 60:02d}"

                    sig.launch_time_str = calc_time
                    # 计算拔地而起角斜率: 从开盘/低点到当前启动点的角斜率
                    elapsed_min = max(1, idx + 1)
                    rise_pct = (bar_c - m_low) / max(m_low, 0.01) * 100.0
                    sig.launch_slope_deg = round(math.degrees(math.atan((rise_pct / elapsed_min) / 1.5)), 1)
                    launch_found = True
                    break
            if not launch_found:
                sig.launch_time_str = "未启动"
                sig.launch_slope_deg = 0.0


            # 判定是否为上市首日/初期 (严密基于上市日期与今日对比)
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                fetcher = NewStockFetcher.get_instance()
                ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
                info = ipo_dict.get(sig.code, {})
                ld = str(info.get("listing_date") or "").strip()
                today_str = time.strftime("%Y-%m-%d")
                if ld and (ld == today_str or ld >= today_str):
                    sig.is_ipo_first_day = True
            except Exception:
                pass

            # 判定早盘竞价恐吓洗盘: 开盘深幅低开 (<= -12%)，随后在 VWAP 或开盘价上方放量翻红拔起
            if last_close > 0 and t_open > 0:
                open_chg = (t_open - last_close) / last_close * 100.0
                if open_chg <= -12.0 and p >= t_open and p >= vw:
                    sig.is_morning_scare_rebound = True

            # 判定极端高潮放量平仓点与临停加速冲刺 (沈鼓集团同款：经历连续临停冲向82.59顶点，加速后复牌戛然而止)
            t_high = float(today_df["high"].max()) if "high" in today_df.columns else float(today_df["close"].max())
            
            # (1) 临停计数感知：检测跳停断点或涨幅越过临停阈值 (+30%, +60%)
            susp_cnt = 0
            if t_open > 0 and t_high >= t_open * 1.28:
                susp_cnt += 1
            if t_open > 0 and t_high >= t_open * 1.58:
                susp_cnt += 1
            sig.suspension_count = susp_cnt

            # (2) 计算机算法提前设计高抛挂单价 (Pre-calculated Limit Sell Exit)
            # 操盘手血泪洞见：高点能卖出的都是提前计算机算法挂单，跳水时一秒杀几十点根本卖不掉
            if sig.vwap_diff_pct >= 20.0 or sig.suspension_count >= 1:
                if sig.suspension_count >= 2:
                    calc_sell_p = t_high * 0.995 if t_high > p else p * 1.02
                elif sig.suspension_count == 1:
                    calc_sell_p = t_open * 1.60 if t_open > 0 else vw * 1.45
                else:
                    calc_sell_p = t_open * 1.30 if t_open > 0 else vw * 1.35
                sig.climax_preset_sell_price = round(calc_sell_p, 2)
            else:
                sig.climax_preset_sell_price = round(vw * 1.25, 2) if vw > 0 else round(p * 1.25, 2)

            # (3) T+1 制度买入拦截禁令：非首日且高位冲刺狂飙，当天买入无卖出权，严禁追高接盘！
            if not sig.is_ipo_first_day and (sig.vwap_diff_pct >= 20.0 or sig.change_pct >= 15.0 or sig.suspension_count >= 1):
                sig.is_t1_forbidden_buy = True

            # (4) 极端高潮滞涨与长上影跳水平仓判定
            if sig.vwap_diff_pct >= 25.0:
                # 偏离 VWAP 超过 25%，且自高位回撤超过 3.5%
                if t_high > 0 and (t_high - p) / t_high * 100.0 >= 3.5:
                    sig.is_climax_exit = True
                # 或日内偏离 VWAP 超过 38.0% 达到情绪狂暴极值
                elif sig.vwap_diff_pct >= 38.0:
                    sig.is_climax_exit = True

        # ── 关键算法 1: 检测在 VWAP 附近走平蓄势天数 (1~3天) ──
        flat_days_count = 0
        recent_dates = dates[-4:-1] if n_days >= 4 else (dates[:-1] if n_days > 1 else dates)
        for d in reversed(recent_dates):
            day_sub = df[df["date"] == d] if "date" in df.columns else df
            if day_sub.empty or len(day_sub) < 10:
                continue
            d_high = float(day_sub["high"].max()) if "high" in day_sub.columns else float(day_sub["close"].max())
            d_low = float(day_sub["low"].min()) if "low" in day_sub.columns else float(day_sub["close"].min())
            d_vw = float(day_sub["vwap"].iloc[-1]) if "vwap" in day_sub.columns else float(day_sub["close"].mean())
            d_close = float(day_sub["close"].iloc[-1])
            
            d_range_pct = (d_high - d_low) / d_low * 100.0 if d_low > 0 else 10.0
            d_diff_to_vw = abs(d_close - d_vw) / d_vw * 100.0 if d_vw > 0 else 10.0
            
            if d_range_pct <= 5.0 and d_diff_to_vw <= 2.5 and d_low >= d_vw * 0.975:
                flat_days_count += 1
            else:
                break
        sig.consolidation_days = flat_days_count

        # ── 关键算法 2: 检测“在 VWAP 上方回踩不碰 / 浅踩不破” ──
        if len(today_df) >= 15 and sig.is_above_vwap:
            recent_sub = today_df.tail(30)
            rec_low = float(recent_sub["low"].min()) if "low" in recent_sub.columns else float(recent_sub["close"].min())
            rec_vwap = float(recent_sub["vwap"].iloc[-1]) if "vwap" in recent_sub.columns else vw
            low_dist = (rec_low - rec_vwap) / rec_vwap * 100.0 if rec_vwap > 0 else 999.0
            if 0.0 <= low_dist <= 2.0 and p > rec_low:
                sig.pullback_no_touch = True

        # 设置建议止损价位: 严格锚定在 VWAP 处 (买入打止损说明买点错了，止损极窄，买错就出局)
        sig.stop_loss_price = round(vw * 0.995, 2)

    def _evaluate_bottom_base_structure(self, df: pd.DataFrame, sig: VWAPDetectorSignal, day_df: Optional[pd.DataFrame] = None):
        """
        【操盘手图解核心落地：寻找底部结构与动能抓手】
        1. 适用场景：经历较大幅度下杀/远离 VWAP (负偏离或微幅波动) 的新股次新标的；
        2. 结构抓手 (Base Structure)：
           - 底部横盘平底 (Flat Base)：在底部区间连续多根 Bar (>=10 根) 不再创新低，振幅极度收敛 (<=3.0%)，成交量萎缩磨底；
           - 双底 / W底 (Double Bottom)：二次探底未破前低 (低点差 <= 2.0%)，且分时价格已脱离低点；
        3. 动能抓手 (Momentum Inflection)：
           - 量能激活：分时成交量较筑底横盘均量温和放大 (>= 1.25 倍)；
           - 均价/价格上翘：价格站上短均线或分时均价线，斜率由平转陡；
           - 突破局部微型下行通道：突破下行受压斜线或平台颈线；
        4. 极窄止损与反弹空间：
           - 止损锚定底部平台支撑位 -0.8% (买错跌破底台即斩出局，风险极低)；
           - 计算向上回抽 VWAP 的盈亏比空间 (rebound_to_vwap_space_pct)。
        """
        if df is None or df.empty:
            return

        p = sig.price
        vw = sig.vwap
        if p <= 0:
            return

        # 向上回抽 VWAP 的反弹空间
        if vw > p:
            sig.rebound_to_vwap_space_pct = round((vw - p) / p * 100.0, 1)
        else:
            sig.rebound_to_vwap_space_pct = 0.0

        # 取今日或近期分时 Bar
        if "date" in df.columns:
            last_date = df["date"].iloc[-1]
            sub_df = df[df["date"] == last_date]
            # 如果今日 Bar 较少 (如早盘前30分钟)，结合昨日后半段
            if len(sub_df) < 30 and len(df) >= 40:
                sub_df = df.tail(60)
        else:
            sub_df = df.tail(60)

        if len(sub_df) < 15:
            return

        closes = sub_df["close"].values if "close" in sub_df.columns else sub_df["price"].values
        lows = sub_df["low"].values if "low" in sub_df.columns else closes
        highs = sub_df["high"].values if "high" in sub_df.columns else closes
        vols = sub_df["volume"].values if "volume" in sub_df.columns else (sub_df["vol"].values if "vol" in sub_df.columns else np.ones(len(sub_df)))

        min_low = float(np.min(lows))
        if min_low <= 0:
            return

        # 1. 结构抓手检测：
        # A. 底部平底检测：寻找最近 12~35 根 Bar 的平稳支撑带
        recent_window = min(35, len(sub_df))
        rec_lows = lows[-recent_window:]
        rec_highs = highs[-recent_window:]
        rec_vols = vols[-recent_window:]
        rec_min = float(np.min(rec_lows))
        rec_max = float(np.max(rec_highs))

        range_pct = (rec_max - rec_min) / rec_min * 100.0 if rec_min > 0 else 999.0

        # 统计底部不创新低的 Bar 数
        flat_bars = 0
        for val in reversed(rec_lows):
            if val >= rec_min * 0.995:
                flat_bars += 1
            else:
                break

        # B. 双底检测：寻找两次探底
        has_double_bottom = False
        if len(sub_df) >= 20:
            mid = len(sub_df) // 2
            low1 = float(np.min(lows[:mid]))
            low2 = float(np.min(lows[mid:]))
            if abs(low1 - low2) / max(low1, 0.01) <= 0.02 and p >= low2:
                has_double_bottom = True

        # 平底特征判定：波动区间较窄 (<= 3.2%)，且持续至少 8 根 Bar
        is_flat_base = (range_pct <= 3.5 and flat_bars >= 8 and p >= rec_min and p <= rec_min * 1.05)

        # C. 日K或大级别双底/通道下轨共振加持
        k_support_boost = (sig.has_kline_launch_sig or (sig.trend_support_level > 0 and abs(p - sig.trend_support_level) / sig.trend_support_level <= 0.03))

        has_base = (is_flat_base or has_double_bottom or (k_support_boost and flat_bars >= 6))

        if has_base:
            sig.has_bottom_base = True
            base_supp = rec_min if rec_min > 0 else min_low
            sig.base_support_level = round(base_supp, 2)
            sig.base_consolidation_bars = flat_bars
            # 极窄底台止损线：跌破平台底部 -0.8% 坚决出局斩仓
            sig.stop_loss_price = round(base_supp * 0.992, 2)

            # 2. 动能抓手与拐点检测：
            # (1) 缩量与放量对比：
            if len(rec_vols) >= 6:
                base_avg_vol = float(np.mean(rec_vols[:-3])) if len(rec_vols) > 3 else float(np.mean(rec_vols))
                latest_vol = float(np.mean(rec_vols[-3:]))
                vol_surge = (latest_vol >= base_avg_vol * 1.25) or (latest_vol > 0 and base_avg_vol == 0)
            else:
                vol_surge = False

            # (2) 价格/均线上翘与斜率：
            slope_up = (sig.launch_slope_deg >= 18.0) or (p >= rec_min * 1.01 and p > closes[-2])
            
            # (3) 局部突破：价格脱离底部横盘中轴
            breakout_base = (p >= (rec_min + rec_max) / 2.0 and p > closes[-2])

            if (vol_surge and slope_up) or breakout_base or (sig.launch_slope_deg >= 22.0) or (is_flat_base and p > closes[-2]):
                sig.base_inflection_confirmed = True

        # D. 【多日大平底箱体与 60F 通道突破尾盘收最高检测 (蓝色光标同款结构)】
        # 操盘手神级图解：4日大箱体平底(12.6~13.0) + 60F突破下降通道 + 尾盘放量收最高
        if "date" in df.columns:
            date_list = sorted(df["date"].astype(str).unique().tolist())
            if len(date_list) >= 3:
                recent_days = date_list[-4:]  # 最近 3~4 个交易日
                day_lows = []
                day_highs = []
                for d_k in recent_days[:-1]:
                    sub_d = df[df["date"] == d_k]
                    if not sub_d.empty:
                        d_l = float(sub_d["low"].min()) if "low" in sub_d.columns else float(sub_d["close"].min())
                        d_h = float(sub_d["high"].max()) if "high" in sub_d.columns else float(sub_d["close"].max())
                        if d_l > 0:
                            day_lows.append(d_l)
                            day_highs.append(d_h)

                if len(day_lows) >= 2:
                    min_box_l = min(day_lows)
                    max_box_l = max(day_lows)
                    # 连续多日低点波动收敛在 4.5% 以内 (大箱体筑底)
                    is_multi_day_box = ((max_box_l - min_box_l) / min_box_l * 100.0 <= 4.5)
                    
                    # 尾盘收最高判定：今日收盘在当日最高价附近，且站上底台
                    t_today_df = df[df["date"] == date_list[-1]]
                    t_high = float(t_today_df["high"].max()) if "high" in t_today_df.columns else p
                    is_late_high = (p >= t_high * 0.990 and p >= min_box_l * 1.015)
                    
                    # 60F / 日K 通道支撑或启动共振
                    has_k_support = (sig.has_kline_launch_sig or sig.trend_support_level > 0 or sig.change_pct > 0)
                    
                    if is_multi_day_box and is_late_high and has_k_support:
                        sig.is_swing_channel_breakout = True
                        sig.has_bottom_base = True
                        sig.base_inflection_confirmed = True
                        
                        # 止损线精准锚定在 60F 支撑线 (如 12.88) 或多日箱体底部
                        supp_anchor = sig.trend_support_level if (sig.trend_support_level > 0 and abs(p - sig.trend_support_level) / p < 0.05) else min_box_l
                        sig.base_support_level = round(supp_anchor, 2)
                        sig.multi_day_base_support = round(supp_anchor, 2)
                        sig.base_consolidation_bars = len(day_lows) * 240
                        sig.stop_loss_price = round(supp_anchor * 0.992, 2)

    def _evaluate_kline_trend(self, code: str, sig: VWAPDetectorSignal, day_df: Optional[pd.DataFrame] = None):
        """
        评估大趋势 K 线 (日K/2D 通道支撑与启动信号):
        优先使用外部预取的 day_df 或通过 tdd fastohlc=True 极速读取本地通达信原始日线 (单股仅 8ms，跳过繁复指标与内存碎片)
        """
        try:
            clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
            df_day = day_df

            # 1. 若外部未传入，优先从权威本地日线引擎 tdd (tdx_data_Day) 读取日线 (fastohlc=True 极速模式)
            if df_day is None or df_day.empty:
                try:
                    from JSONData import tdx_data_Day as tdd
                    df_day = tdd.get_tdx_Exp_day_to_df(clean_code, dl=60, fastohlc=True)
                    if df_day is not None and not df_day.empty:
                        df_day = df_day.copy()
                except Exception as e_tdd:
                    logger.debug(f"通过 tdd fastohlc 获取标的 {clean_code} 日线异常: {e_tdd}")

            # 2. 兜底回退至 fetcher
            if (df_day is None or df_day.empty) and hasattr(self.fetcher, "fetch_kline_bars"):
                try:
                    df_day = self.fetcher.fetch_kline_bars(clean_code, category="day", count=60)
                except Exception:
                    df_day = None

            if df_day is not None and not df_day.empty and len(df_day) >= 3:
                last_k = df_day.iloc[-1]
                c = float(last_k.get("close", sig.price if sig.price > 0 else 0.0))
                if c <= 0 and sig.price > 0:
                    c = sig.price
                l = float(last_k.get("low", c))

                if "ma5d" in last_k:
                    ma5 = float(last_k.get("ma5d", c))
                elif "close" in df_day.columns and len(df_day) >= 5:
                    ma5 = float(df_day["close"].tail(5).mean())
                else:
                    ma5 = c

                pbottom = float(last_k.get("pbottom", 0.0))
                ptop = float(last_k.get("ptop", 0.0))

                if pbottom > 0:
                    lower_band = pbottom
                elif "lower" in df_day.columns:
                    lower_band = float(last_k.get("lower", l))
                elif len(df_day) >= 20 and "low" in df_day.columns:
                    lower_band = float(df_day["low"].tail(20).min())
                else:
                    lower_band = l

                if ptop <= 0 and len(df_day) >= 20 and "high" in df_day.columns:
                    ptop = float(df_day["high"].tail(20).max())

                sig.trend_support_level = round(lower_band, 2)

                recent_day_lows = df_day["low"].tail(5).tolist() if "low" in df_day.columns else [l]
                is_double_bottom = len(recent_day_lows) >= 4 and abs(recent_day_lows[-1] - min(recent_day_lows)) / max(c, 0.01) < 0.02
                is_near_support = (lower_band > 0 and c >= lower_band * 0.98 and (c - lower_band) / lower_band < 0.08)

                if is_near_support and c >= ma5:
                    sig.has_kline_launch_sig = True
                    sig.trend_desc = f"日K通道下轨支撑({lower_band:.2f})企稳"
                elif is_double_bottom:
                    sig.has_kline_launch_sig = True
                    sig.trend_desc = "日K双底反转企稳"
                elif ptop > 0 and c >= ptop * 0.98:
                    sig.trend_desc = f"日K逼近通道顶({ptop:.2f})"
                elif c >= ma5:
                    sig.trend_desc = "日K站上MA5"
                else:
                    sig.trend_desc = "日K震荡蓄势"

                if len(df_day) >= 5 and "close" in df_day.columns:
                    c_first = float(df_day["close"].iloc[-5])
                    c_last = float(df_day["close"].iloc[-1])
                    if c_first > 0:
                        slope = (c_last - c_first) / c_first * 100.0
                        sig.trend_slope_deg = round(math.degrees(math.atan(slope / 5.0)), 1)

                try:
                    sig.extra_data = last_k.to_dict()
                except Exception:
                    pass

                # 长期通道底部结构次级买点评估 (688826/300058同款架构)
                self._evaluate_channel_secondary_buy_structure(clean_code, sig, df_day)
        except Exception as e:
            logger.debug(f"评估标的 {code} K线趋势异常: {e}")

    def _evaluate_channel_secondary_buy_structure(self, clean_code: str, sig: VWAPDetectorSignal, df_day: Optional[pd.DataFrame]):
        """长期通道企稳与底部结构次级买点评估"""
        if df_day is None or df_day.empty or len(df_day) < 15:
            return
        try:
            curr_quote = {"price": sig.price} if sig.price > 0 else None
            sec_eval = evaluate_channel_secondary_buy(
                df_60m=df_day,
                df_day=df_day,
                current_quote=curr_quote,
                code=clean_code,
                name=sig.name
            )
            stage_val = sec_eval.get("stage", SecondaryBuyStage.DESCENDING_CHANNEL)
            sig.channel_stage = stage_val
            stage_cn_map = {
                SecondaryBuyStage.SECONDARY_BUY: "👑 次级买点",
                SecondaryBuyStage.PULLBACK_STABLE: "⏳ 缩量回踩",
                SecondaryBuyStage.FIRST_BREAKOUT: "🚀 首次试盘",
                SecondaryBuyStage.BASE_DRYUP: "📦 平底箱体",
                SecondaryBuyStage.DESCENDING_CHANNEL: "📉 通道寻底",
                SecondaryBuyStage.INVALIDATED: "⛔ 破位失效",
            }
            sig.channel_stage_cn = stage_cn_map.get(stage_val, "")
            sig.higher_low_stop = float(sec_eval.get("hard_stop", 0.0))
            sig.base_low_invalid = float(sec_eval.get("invalid_price", 0.0))
            sig.quality_grade = str(sec_eval.get("quality_grade", "A"))
            sig.strategy_tag = str(sec_eval.get("strategy_tag", ""))
            sig.trade_plan = sec_eval.get("trade_plan", None)

            # 若触发次级买点确认
            if stage_val == SecondaryBuyStage.SECONDARY_BUY:
                sig.has_bottom_base = True
                sig.base_inflection_confirmed = True
                if sig.higher_low_stop > 0:
                    sig.stop_loss_price = sig.higher_low_stop
        except Exception as e:
            logger.debug(f"评估标的 {clean_code} 通道次级买点异常: {e}")

    def _synthesize_final_decision(self, sig: VWAPDetectorSignal):
        """
        根据操盘手现场明确的超短线买卖点与执行闭环哲学，裁决最终信号与预警：
        - 终极风险 1: 🚨 [极端高潮平仓·锁定利润] —— 偏离 VWAP 极大天量滞涨，主力疯狂兑现，坚决平仓，严禁买入！
        - 铁律风控 2: ⛔ [破位止损出局·买错就出局] —— 跌破 VWAP 超过 0.6%，买错立斩，严禁加仓幻想！
        - 首日黄金 3: 🔥 [首发吸筹·极限进击] —— 首日/上市初期在 VWAP 线上微幅爬升且回踩不碰，惜售锁定成本！
        - 洗盘反转 4: ⚡ [恐吓洗盘起爆·反包突围] —— 早盘竞价深跌恐吓洗盘后放量反包站上 VWAP！
        - 经典黄金 5: 🚀 [回踩不碰·启动买点] —— 在 VWAP 之上强势回踩不碰，极限买点！
        - 潜伏预下单 6: 🎯 [预下单·VWAP蓄势] —— 在 VWAP 走平 1~3 天，价格紧贴 VWAP 上方；
        - 突破加速 7: ⚡ [放量加速·主升推进] —— 突破 VWAP，分时加速。
        """
        # 1. 极端高潮放量平仓点 (防类似沈鼓集团 82.59 疯狂过山车杀跌)
        if sig.is_climax_exit:
            sig.signal_type = "CLIMAX_EXIT"
            sig.signal_level = "🚨 疯狂平仓"
            sig.signal_tier = "ALERT"
            sig.structure_tag = "极端高潮放量"
            sell_guide = f"坚决平仓保利，建议提前算法挂单≈¥{sig.climax_preset_sell_price:.2f}分批止盈逃顶!" if sig.climax_preset_sell_price > 0 else "坚决平仓保利，严禁追买!"
            sig.signal_desc = f"现价偏离VWAP达极限(+{sig.vwap_diff_pct:.1f}%)且冲高天量滞涨，主力疯狂兑现，{sell_guide}"
            return

        # 2. 首日上市吸筹黄金买点 (全天贴线惜售，丝毫不碰 VWAP，首日标杆最高优先 👑 SSS级)
        if sig.is_ipo_first_day and sig.is_above_vwap and sig.vwap_diff_pct <= 15.0 and sig.vwap_adhesion_ratio >= 65.0:
            sig.signal_type = "IPO_FIRST_BUY"
            sig.signal_level = "🔥 首发吸筹"
            sig.signal_tier = "SSS"
            sig.structure_tag = "首日贴线惜售"
            sig.signal_desc = f"首发上市紧贴VWAP({sig.vwap:.2f})上方爬升且回踩不碰，主力筹码高度惜售，全天黄金进击点!"
            return

        # 3. 【操盘手神级图解：60F下降通道突破 + 多日平底箱体尾盘收新高 (蓝色光标同款 🎯 A级)】
        if not sig.is_ipo_first_day and getattr(sig, "is_swing_channel_breakout", False):
            sig.signal_type = "SWING_PREORDER"
            sig.signal_level = "🔭 通道突破"
            sig.signal_tier = "A"
            sig.structure_tag = "多日平底+通道突破"
            space_str = f"博周一冲破VWAP(空间+{sig.rebound_to_vwap_space_pct:.1f}%)" if sig.rebound_to_vwap_space_pct > 0 else "大级别反转蓄势"
            sig.signal_desc = f"60F突破下降通道+多日平底({sig.base_support_level:.2f})箱体突破，尾盘放量收最高! 虽在VWAP({sig.vwap:.2f})下但属大级别拐点，极窄止损{sig.stop_loss_price:.2f}元(60F底台)，{space_str}!"
            return

        # 3.5 【操盘手实战定调：长期通道底部结构次级买点 (688826/300058同款 👑 S4/S5级)】
        if not sig.is_ipo_first_day and sig.channel_stage == "SECONDARY_BUY":
            sig.signal_type = "SECONDARY_BUY"
            sig.signal_level = "👑 次级买点"
            sig.signal_tier = sig.quality_grade or "S"
            sig.structure_tag = f"通道次级买点({sig.quality_grade or 'S'})"
            plan = getattr(sig, "trade_plan", None)
            if plan:
                plan_hint = f"买区[{plan.buy_zone_lower:.2f}~{plan.buy_zone_upper:.2f}], 止损{plan.higher_low_stop:.2f}元, 目标1:{plan.target_1_channel_mid:.2f}元"
            else:
                plan_hint = f"止损{sig.higher_low_stop:.2f}元"
            sig.signal_desc = f"长期下降通道企稳，回踩抬高底放量确认次级买点! {plan_hint}"
            return

        # 4. 【操盘手核心进化：寻找结构与动能抓手，底部企稳预埋与放量共振】
        # 大量新股超跌偏离 VWAP 人气很弱，但有些开始底部缩量企稳加速，需要预埋单，不能等涨起来到了 VWAP 再追！
        if not sig.is_ipo_first_day and sig.has_bottom_base and sig.base_inflection_confirmed:
            # 判断是放量加速冲锋 (共振突击 🥇 S级)，还是横盘平底初现拐点 (预埋潜伏 🎯 A级)
            if sig.launch_slope_deg >= 25.0 or sig.change_pct >= 2.0 or (sig.price >= sig.base_support_level * 1.025):
                sig.signal_type = "BASE_BREAKOUT"
                sig.signal_level = "⚡ 筑底共振"
                sig.signal_tier = "S"
                sig.structure_tag = "底部放量共振"
                space_str = f"博反弹距VWAP+{sig.rebound_to_vwap_space_pct:.1f}%空间" if sig.rebound_to_vwap_space_pct > 0 else "主升推进"
                sig.signal_desc = f"底部平底/双底({sig.base_support_level:.2f})缩量企稳后放量加速拐头! {space_str}，极窄止损{sig.stop_loss_price:.2f}元"
                return
            else:
                sig.signal_type = "BASE_PREORDER"
                sig.signal_level = "🎯 筑底预埋"
                sig.signal_tier = "A"
                sig.structure_tag = "底部缩量平底"
                space_str = f"向上距VWAP空间+{sig.rebound_to_vwap_space_pct:.1f}%" if sig.rebound_to_vwap_space_pct > 0 else ""
                sig.signal_desc = f"底部({sig.base_support_level:.2f})缩量企稳横盘构筑扎实结构，动能拐头初现! 提前预埋单挂单潜伏，{space_str}，买错跌破{sig.stop_loss_price:.2f}元立斩!"
                return

        # 4. 破位弱势股直接拦截 (买错就出局终极闭环，仅对无筑底结构的破位标的一票否决 🚨 ALERT级)
        if not sig.is_above_vwap and sig.vwap_diff_pct < -0.6:
            sig.signal_type = "WEAK_EXIT"
            sig.signal_level = "⛔ 破位止损点"
            sig.signal_tier = "ALERT"
            sig.structure_tag = "破位运行"
            first_day_hint = "【首日破位避险】" if sig.is_ipo_first_day else ""
            sig.signal_desc = f"{first_day_hint}跌破生命线VWAP({sig.vwap:.2f})达{sig.vwap_diff_pct:.1f}%且无筑底结构，买错坚决止损出局，严禁加仓幻想接飞刀!"
            return

        # 4. 经典黄金买点: 回踩不碰 (回踩靠拢 VWAP 但不碰到跌破，极限买点 🥇 S级)
        if sig.pullback_no_touch:
            sig.signal_type = "PULLBACK_BUY"
            sig.signal_level = "🚀 回踩启动"
            sig.signal_tier = "S"
            sig.structure_tag = "回踩不碰"
            sig.signal_desc = f"价格在 VWAP({sig.vwap:.2f}) 之上强势回踩不碰! 极限买点确立，建议止损价 {sig.stop_loss_price:.2f}元"
            return

        # 5. 早盘恐吓洗盘反包买点 (首日为 👑 SSS级，常规次新为 🥇 S级)
        if sig.is_morning_scare_rebound and sig.is_above_vwap:
            sig.signal_type = "SCARE_REBOUND"
            sig.signal_level = "⚡ 恐吓反包"
            sig.signal_tier = "SSS" if sig.is_ipo_first_day else "S"
            sig.structure_tag = "低开恐吓反包"
            prefix_txt = "【首日恐吓反包】" if sig.is_ipo_first_day else ""
            sig.signal_desc = f"{prefix_txt}早盘竞价低开恐吓洗盘完毕，放量站上VWAP({sig.vwap:.2f})拔地而起，主力反向点火进击!"
            return

        # 6. 预判潜伏结构: 在 VWAP 走平 1~3 天 (博反弹/加速预下单 🎯 A级)
        if sig.consolidation_days >= 1:
            sig.signal_type = "PRE_ORDER"
            day_str = f"{sig.consolidation_days}天" if sig.consolidation_days < 3 else "3天+"
            sig.signal_level = "🎯 预下单"
            sig.signal_tier = "A"
            sig.structure_tag = f"在VWAP走平{day_str}"
            k_desc = f" ({sig.trend_desc})" if sig.trend_desc else ""
            sig.signal_desc = f"在 VWAP 上方已走平蓄势 {day_str}{k_desc}，可预挂单潜伏，博加速拉升! 破 VWAP({sig.vwap:.2f}) 即止损"
            return

        # 7. 放量突破 / 强势上攻 (🥇 S级)
        if sig.is_above_vwap and sig.vwap_diff_pct >= 2.0:
            sig.signal_type = "BREAKOUT"
            sig.signal_level = "⚡ 放量加速"
            sig.signal_tier = "S"
            sig.structure_tag = "强势主升"
            sig.signal_desc = f"现价站上 VWAP 上方 +{sig.vwap_diff_pct:.1f}%，分时多头推升加速中"
            return

        # 8. 常规在 VWAP 上方运行
        if sig.is_above_vwap:
            sig.signal_type = "WATCH"
            sig.signal_level = "⏱️ 站稳VWAP"
            sig.signal_tier = "WATCH"
            sig.structure_tag = "线上震荡"
            sig.signal_desc = f"处于 VWAP({sig.vwap:.2f}) 之上震荡观察，等待回踩不碰或走平确认"
            return

        # 9. 默认观望
        sig.signal_type = "WATCH"
        sig.signal_tier = "WATCH"
        sig.signal_level = "⚪ 观望"
        sig.structure_tag = "常规震荡"
        sig.signal_desc = "多空平衡，暂无极限预下单结构"


def batch_evaluate_horse_race_ranking(signals: List[VWAPDetectorSignal]) -> List[VWAPDetectorSignal]:
    """
    【逐日赛马冒泡排位引擎 (Horse Race Momentum Engine)】
    - 结合早盘启动时效 (30%) + 拔地而起斜率 (25%) + VWAP站稳率 (20%) + SBC活跃度 (15%) + 日K趋势 (10%)；
    - 实时对检测池内所有标的进行冒泡打分排位；
    - 动态授予 🥇 赛马领头羊 / 🥈 梯队前锋 / 🎯 线上蓄势 / ⏱️ 迟滞跟风 / 🚨 疯狂平仓 / ⛔ 破位出局 梯队标签；
    - 返回按 horse_race_score 降序冒泡排列的信号列表。
    """
    if not signals:
        return []

    for sig in signals:
        if not sig or sig.price <= 0:
            continue

        # 1. 极端高潮或破位股处理
        if sig.is_climax_exit:
            sig.horse_race_score = 99.0
            sig.horse_race_tier = "🚨 疯狂平仓"
            continue

        # 【核心进化】：长期通道次级买点专属高动能赛马打分 (88~95分，第一梯队前锋)
        if sig.signal_type == "SECONDARY_BUY" or sig.channel_stage == "SECONDARY_BUY":
            base_score = 88.0
            grade_bonus = 5.0 if sig.quality_grade == "SS" else (3.0 if sig.quality_grade == "S" else 0.0)
            sig.horse_race_score = round(min(95.0, base_score + grade_bonus), 1)
            sig.horse_race_tier = "👑 次级买点"
            continue

        # 【核心进化】：底部结构共振与跨日通道突破标的专属高动能赛马打分 (打破只有站上VWAP才给高分的死板逻辑)
        if sig.signal_type in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER"):
            if sig.signal_type == "BASE_BREAKOUT":
                base_score = 82.0
            elif sig.signal_type == "SWING_PREORDER":
                base_score = 80.0  # 跨日通道突破稳居前列(80~86分)，绝不抢早盘龙头第一，但也绝不垫底！
            else:
                base_score = 76.0
            # 结构加分：横盘 Bar 数越多结构越稳 (+0~8分)
            struct_bonus = min(8.0, sig.base_consolidation_bars * 0.4) if sig.signal_type != "SWING_PREORDER" else 4.0
            # 动能拐点加分：斜率或反弹空间 (+0~8分)
            slope_bonus = min(5.0, sig.launch_slope_deg * 0.15) if sig.launch_slope_deg > 0 else 2.0
            space_bonus = min(5.0, sig.rebound_to_vwap_space_pct * 0.3) if sig.rebound_to_vwap_space_pct > 0 else 0.0
            sig.horse_race_score = round(min(94.0, base_score + struct_bonus + slope_bonus + space_bonus), 1)
            if sig.signal_type == "BASE_BREAKOUT":
                sig.horse_race_tier = "⚡ 筑底共振"
            elif sig.signal_type == "SWING_PREORDER":
                sig.horse_race_tier = "🔭 通道突破"
            else:
                sig.horse_race_tier = "🎯 筑底预埋"
            continue

        if not sig.is_above_vwap:
            sig.horse_race_score = max(5.0, 40.0 + sig.vwap_diff_pct * 2.0)
            sig.horse_race_tier = "⛔ 破位出局"
            continue

        # 2. 早盘启动时间分 (Time Decay Factor)
        # 盘后/非实时模式：launch_time_str 为空时以 vwap_diff_pct 作代理评分，让盘后排位有实际意义
        t_str = sig.launch_time_str
        if t_str and t_str != "未启动":
            if t_str <= "09:40":
                time_score = 95.0
            elif t_str <= "09:50":
                time_score = 85.0
            elif t_str <= "10:00":
                time_score = 75.0
            elif t_str <= "10:30":
                time_score = 60.0
            else:
                time_score = 45.0
        else:
            # 盘后代理时间分：VWAP 偏离度越高表示当日表现越强势
            vd = sig.vwap_diff_pct
            if vd >= 20.0:
                time_score = 98.0   # 极度偏离 VWAP (高潮冲刺区)
            elif vd >= 12.0:
                time_score = 90.0   # 强势放量主升
            elif vd >= 6.0:
                time_score = 80.0   # VWAP 上方加速运行
            elif vd >= 2.0:
                time_score = 65.0   # VWAP 上方温和震荡
            elif vd >= 0.0:
                time_score = 50.0   # 贴近 VWAP 观察
            else:
                time_score = max(5.0, 30.0 + vd * 1.5)  # 破位降分

        # 3. 拔地而起角斜率分 (Surge Slope Score)
        # 盘后/非实时模式：launch_slope_deg 为 0 时以 change_pct 日涨跌幅作代理斜率分
        slope = sig.launch_slope_deg
        if slope >= 50.0:
            slope_score = 98.0
        elif slope >= 35.0:
            slope_score = 85.0
        elif slope >= 20.0:
            slope_score = 70.0
        elif slope > 0:
            slope_score = 55.0
        else:
            # 盘后代理斜率分：日涨跌幅反映当日冲击力
            cp = sig.change_pct
            if cp >= 15.0:
                slope_score = 98.0
            elif cp >= 8.0:
                slope_score = 85.0
            elif cp >= 3.0:
                slope_score = 70.0
            elif cp >= 0.0:
                slope_score = 55.0
            else:
                slope_score = max(10.0, 40.0 + cp * 1.5)

        # 4. VWAP 站稳与贴线率分
        hold_score = min(100.0, max(20.0, sig.vwap_adhesion_ratio))

        # 5. SBC 活跃度分
        act = sig.sbc_activity_pct
        if act >= 200.0:
            act_score = 98.0
        elif act >= 100.0:
            act_score = 88.0
        elif act >= 40.0:
            act_score = 75.0
        else:
            act_score = 55.0

        # 6. 日K通道与启动信号分
        k_score = 85.0 if sig.has_kline_launch_sig else 65.0

        # 综合赛马动能分
        raw_score = (
            time_score * 0.30 +
            slope_score * 0.25 +
            hold_score * 0.20 +
            act_score * 0.15 +
            k_score * 0.10
        )
        if getattr(sig, "horse_race_score", 50.0) != 50.0 and (not t_str or t_str == "未启动"):
            sig.horse_race_score = max(sig.horse_race_score, round(max(0.0, min(100.0, raw_score)), 1))
        else:
            sig.horse_race_score = round(max(0.0, min(100.0, raw_score)), 1)

    # 冒泡降序排序
    ranked_signals = sorted(signals, key=lambda s: getattr(s, "horse_race_score", 0.0), reverse=True)

    # 分配赛马排名与梯队徽章
    normal_rank = 1
    for sig in ranked_signals:
        if sig.is_climax_exit:
            sig.horse_race_tier = "🚨 疯狂平仓"
            sig.horse_race_rank = 0
            continue

        # 【核心进化】：长期通道次级买点标的享有正常赛马位次与专属徽章 (哪怕股价在 10d VWAP 下方也不被误判为破位出局)
        if sig.signal_type == "SECONDARY_BUY" or sig.channel_stage == "SECONDARY_BUY":
            sig.horse_race_rank = normal_rank
            sig.horse_race_tier = "👑 次级买点"
            normal_rank += 1
            continue

        # 【核心进化】：底部结构共振、预埋与跨日通道突破标的享有正常赛马位次与专属徽章
        if sig.signal_type in ("BASE_BREAKOUT", "BASE_PREORDER", "SWING_PREORDER"):
            sig.horse_race_rank = normal_rank
            if sig.signal_type == "BASE_BREAKOUT":
                sig.horse_race_tier = "⚡ 筑底共振"
            elif sig.signal_type == "SWING_PREORDER":
                sig.horse_race_tier = "🔭 通道突破"
            else:
                sig.horse_race_tier = "🎯 筑底预埋"
            normal_rank += 1
            continue

        if not sig.is_above_vwap:
            sig.horse_race_tier = "⛔ 破位出局"
            sig.horse_race_rank = 999
            continue

        sig.horse_race_rank = normal_rank
        if normal_rank == 1 and sig.horse_race_score >= 80.0:
            sig.horse_race_tier = "🥇 领头羊"
        elif normal_rank <= 5 and sig.horse_race_score >= 70.0:
            sig.horse_race_tier = "🥈 梯队前锋"
        elif sig.consolidation_days >= 1:
            sig.horse_race_tier = "🎯 线上蓄势"
        elif sig.launch_time_str > "10:00" or sig.horse_race_score < 65.0:
            sig.horse_race_tier = "⏱️ 迟滞跟风"
        else:
            sig.horse_race_tier = "⚡ 多头攻击"

        normal_rank += 1

    return ranked_signals

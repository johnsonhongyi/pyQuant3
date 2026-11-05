# -*- coding: utf-8 -*-
"""ats/fusion/hot_pool.py — 梯度热榜持续跟踪：口径、候选激活、最小席位判定与原子持久化。

严格遵守《梯度热榜持续跟踪：复审修订与执行方案》：
- 绝不修改既有内核等级、保底与交易执行（严禁修改 kernel.py、is_structure_prejudged 等）；
- 板块联动是入池证据，不是涨幅排名的别名；
- 双 10V 口径与前 9 日量价完整性校验硬门禁；
- 预登记试验参数（Provisional Config），标记 is_provisional = True；
- 三路候选输入（盘前日线种子、盘中板块激活、跨日继承），一条盘中状态链；
- 单写者 HotPoolState，按 (trade_date, event_ts, code) 顺序推进，先更新全市场 SectorPulse，再评估个股；
- 四席位独立评分，三类时间戳（candidate_seeded/activated_ts, first_observed_ts, first_alert_ts）严格分离；
- 跨进程原子持久化（ats.persistence_lock）与 (day, code, transition, pulse_id) 幂等提示输出。
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from ats.fusion.sector import SectorMap, ThemeMap, get_sector_map, get_theme_map

def _app_root() -> str:
    try:
        from sys_utils import get_app_root
        return get_app_root()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


try:
    from ats.persistence_lock import directory_write_lock, replace_with_retry
    _HAS_PERSIST_LOCK = True
except Exception:
    _HAS_PERSIST_LOCK = False

logger = logging.getLogger(__name__)


# =====================================================================
# 1. 试验参数集 (Provisional & Calibrated Config)
# =====================================================================

@dataclass
class HotPoolProvisionalConfig:
    """预登记可调整的初始试验参数集。

    标记 is_provisional = True，供 Step 1/Step 2 跑通验证，留待 Step 4 在校准集上网格优化。
    """
    is_provisional: bool = True

    # 板块脉冲时间窗与群起门禁
    pulse_window_sec: int = 180           # 同步脉冲时间窗（秒）
    min_pulse_active_count: int = 3       # 最少同步脉冲人数
    min_pulse_active_ratio: float = 0.15  # 最低有效成员异动占比 (active / valid)
    min_coverage_ratio: float = 0.50      # 最低行情覆盖率硬门禁 (valid / total_members)
    min_valid_members: int = 4            # 最小有效报价成员数（防止过小板块虚构群起）
    min_sector_alpha_pct: float = 0.35    # 板块相对市场中位数超额阈值 (%)
    min_member_delta_pct: float = 0.60    # 个体短窗增量涨幅阈值 (%)
    pulse_decay_timeout_sec: int = 300    # 脉冲衰减超时进入 EXPIRED 时间（秒）

    # 路径 1: 盘前日线水下止跌基座候选初筛阈值 (underwater_base_pool)
    premarket_seed_budget: int = 350      # 盘前种子名额上限（收敛至具备结构的 ~150–450 只）
    underwater_max_amp: float = 18.0      # 近 5/6 日最大振幅上限 (%)
    underwater_min_depth: float = -12.0   # 距 10V 下方最大深度 (%)
    underwater_max_depth: float = 2.0     # 距 10V 上方最大容差 (%)
    underwater_low_lift_pct: float = -1.5 # 昨低相对 10 日最低点下移容差 (%)，止跌企稳

    # 路径 2: 盘中板块激活与预算
    intraday_activation_budget: int = 100 # 单轮重计算预算上限
    intraday_min_bias_vwap: float = 0.00  # 盘中相对分时 VWAP 容差 (%)，至少站稳分时 VWAP
    intraday_min_delta_pct: float = 0.50  # 盘中正向增量涨幅 (%)
    intraday_min_vol_ratio: float = 0.80  # 量比承接初筛

    # 10V 结构判定容差
    vwap10_tolerance_retest: float = 0.995 # 10V 回测承接容差
    vwap10_tolerance_break: float = 0.985  # 10V 失守下限容差


# =====================================================================
# 2. 双 10V 质量核验与 SBC VWAP 源比对
# =====================================================================

@dataclass


@dataclass
class HotPoolCalibratedConfig(HotPoolProvisionalConfig):
    """Step 4 经过校准集与留出验证集网格实证后的转正定稿配置。"""
    is_provisional: bool = False
    premarket_seed_budget: int = 400


@dataclass
class Dual10VQuality:
    """双 10V 质量与有效性评估契约。"""
    static_10v: float = 0.0
    static_quality: str = "unavailable"  # "verified_amt_vol" | "tp_fallback" | "unavailable"
    dynamic_10v: Optional[float] = None
    dynamic_10v_usable: bool = False
    unusable_reason: str = ""
    obs_freshness: str = "unknown"
    vwap_timing_freshness: str = "unknown"
    prev9_keys_present: bool = False
    asof_date: str = ""
    evaluated_at: float = 0.0


def evaluate_10v_quality(
    daily_ctx: Dict[str, Any],
    obs_evidence: Optional[Dict[str, Any]],
    trade_date: str,
    today_vwap: float = 0.0,
    today_volume: float = 0.0,
    evaluated_at: float = 0.0,
) -> Dual10VQuality:
    """显式核验静态 10V（截至昨日日线）与动态 10V（含今日实时累计量价）。

    硬门禁：若缺少有效成交额/成交量、前 9 日量价键缺失或非当日 same_day 新鲜特征，
    dynamic_10v_usable 必须为 False，严禁把 including_current["10"] 用于趋势判定！
    """
    now_ts = evaluated_at if evaluated_at > 0 else time.time()
    res = Dual10VQuality(asof_date=trade_date, evaluated_at=now_ts)

    daily = daily_ctx or {}
    v10 = float(daily.get("vwap10") or 0.0)
    res.static_10v = v10

    # 检查前 9 日量价键
    v9_val = daily.get("vwap_prev9_value")
    v9_vol = daily.get("vwap_prev9_volume")
    has_prev9 = (v9_val is not None and v9_vol is not None and float(v9_val) > 0 and float(v9_vol) > 0)
    res.prev9_keys_present = has_prev9

    if v10 <= 0.0:
        res.static_quality = "unavailable"
    elif has_prev9:
        res.static_quality = "verified_amt_vol"
    else:
        # context.py:236 校验失败时这两个键直接缺失，此时静态 vwap10 含有典型价 tp 回退
        res.static_quality = "tp_fallback"

    # 评估动态 10V (含今日累计)
    if not isinstance(obs_evidence, dict):
        res.dynamic_10v_usable = False
        res.unusable_reason = "missing_obs_evidence"
        return res

    obs_fresh = str(obs_evidence.get("freshness") or "unknown")
    res.obs_freshness = obs_fresh

    vwap_dict = obs_evidence.get("vwap") or {}
    timing_dict = vwap_dict.get("timing") or {}
    timing_fresh = str(timing_dict.get("freshness") or "unknown")
    res.vwap_timing_freshness = timing_fresh

    incl = vwap_dict.get("including_current") or {}
    dyn_10 = incl.get("10")
    if dyn_10 is not None:
        try:
            res.dynamic_10v = float(dyn_10)
        except (ValueError, TypeError):
            res.dynamic_10v = None

    # 硬性门禁核验
    if obs_fresh != "same_day":
        res.dynamic_10v_usable = False
        res.unusable_reason = f"obs_freshness_not_same_day({obs_fresh})"
    elif timing_fresh != "same_day":
        res.dynamic_10v_usable = False
        res.unusable_reason = f"vwap_timing_not_same_day({timing_fresh})"
    elif not has_prev9:
        res.dynamic_10v_usable = False
        res.unusable_reason = "missing_prev9_value_volume_keys"
    elif today_vwap > 0.0 and today_volume > 0.0:
        val_total = float(v9_val) + today_vwap * today_volume
        vol_total = float(v9_vol) + today_volume
        calc_dyn10 = val_total / vol_total if vol_total > 0 else 0.0
        res.dynamic_10v = round(calc_dyn10, 4)
        res.dynamic_10v_usable = (res.dynamic_10v > 0.0)
        if not res.dynamic_10v_usable:
            res.unusable_reason = "calc_dynamic_10v_non_positive"
    elif res.dynamic_10v is not None and res.dynamic_10v > 0.0:
        res.dynamic_10v_usable = True
    else:
        res.dynamic_10v_usable = False
        res.unusable_reason = "missing_valid_today_vwap_or_volume"

    return res


def compare_sbc_vwap_source(
    period_mode: str,
    df_view_vwap: float,
    dynamic_10v: Optional[float],
    source: str,
    ts: float,
    volume_unit: str = "shares",
) -> Dict[str, Any]:
    """SBC 分时金色均价线与观察层动态 10V 的核源记录。

    显式记录图表显示周期（1m/3d/5d/10d）、输入来源、时间戳和成交量单位。
    """
    diff = None
    diff_pct = None
    if dynamic_10v is not None and dynamic_10v > 0 and df_view_vwap > 0:
        diff = round(df_view_vwap - dynamic_10v, 4)
        diff_pct = round((df_view_vwap / dynamic_10v - 1.0) * 100.0, 3)

    return {
        "period_mode": period_mode,
        "df_view_vwap": df_view_vwap,
        "dynamic_10v": dynamic_10v,
        "source": source,
        "ts": ts,
        "volume_unit": volume_unit,
        "diff": diff,
        "diff_pct": diff_pct,
        "is_same_concept": (period_mode == "10d" and diff_pct is not None and abs(diff_pct) < 1.0),
        "note": "SBC多日分时累计cumsum vs Fusion前9日加权累计，需在10d模式与相同单位下方可直接比对",
    }


# =====================================================================
# 3. 行业与多概念双轨板块脉冲引擎 (SectorPulseEngine)
# =====================================================================

@dataclass
class SectorPulse:
    """单个板块在特定时窗内的脉冲状态。"""
    sector_key: str                     # "industry:计算机-IT服务" 或 "theme:人形机器人"
    sector_type: str                    # "industry" | "theme"
    sector_name: str                    # 纯净板块名称
    first_pulse_ts: float = 0.0         # 首次群起时间戳
    last_pulse_ts: float = 0.0          # 最新脉冲时间戳
    total_member_count: int = 0         # 全市场该板块总成员数分母
    valid_count: int = 0                # 当日新鲜有效报价成员数
    active_count: int = 0               # 同窗正向增量异动成员数
    coverage_ratio: float = 0.0         # valid_count / max(1, total_member_count)
    active_ratio: float = 0.0           # active_count / max(1, valid_count)
    active_members: List[Dict[str, Any]] = field(default_factory=list) # [{code, start_ts, delta_pct, vol_ratio}]
    sector_alpha_pct: float = 0.0       # 板块相对市场超额 (%)
    sustained_bars: int = 0             # 持续根数
    max_drawback_pct: float = 0.0       # 最大回撤 (%)
    re_pulse_count: int = 0             # 二次脉冲次数
    state: str = "IDLE"                 # IDLE | NEW_IMPULSE | SUSTAINED | DECAY_WATCH | EXPIRED | REACTIVATED
    peak_pct: float = 0.0               # 脉冲峰值涨幅
    source: str = "live_snapshot"
    asof_ts: float = 0.0
    trade_date: str = ""
    freshness: str = "same_day"

    @property
    def is_confirmed(self) -> bool:
        """是否处于已确认的群起共振状态。"""
        return self.state in ("NEW_IMPULSE", "SUSTAINED", "REACTIVATED")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SectorPulse:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class SectorPulseEngine:
    """双轨板块脉冲引擎：全量维护二级行业与多概念板块的群起、持续、衰减与再激活。

    严禁 split(";", 1)[0] 单标签截断，严禁静默合并名称相近板块。
    具有硬性最低行情覆盖率门禁 (min_coverage_ratio) 与状态滞回。
    """

    def __init__(
        self,
        config: Optional[HotPoolProvisionalConfig] = None,
        sector_map: Optional[SectorMap] = None,
        theme_map: Optional[ThemeMap] = None,
    ):
        self.config = config or HotPoolProvisionalConfig()
        self.sector_map = sector_map or get_sector_map()
        self.theme_map = theme_map or get_theme_map()

        self.pulses: Dict[str, SectorPulse] = {}
        # 记录个股历史价格窗口: code -> [(ts, price, pct)] 用于计算短窗增量
        self._price_windows: Dict[str, List[Tuple[float, float, float]]] = {}
        # 缓存全市场各板块固定成员列表: sector_key -> set[code]
        self._sector_members_cache: Dict[str, Set[str]] = {}
        self._cache_initialized = False

    def init_membership(self, all_codes: Iterable[str]) -> None:
        """显式初始化全市场成员与各行业/概念的从属映射（建立权威总成员数分母）。"""
        self._sector_members_cache.clear()
        broad_concepts = getattr(ThemeMap, "BROAD", set())

        for raw_code in all_codes:
            code = str(raw_code).zfill(6)
            # 1. 二级行业
            sec = self.sector_map.get(code) if self.sector_map else "未分类"
            if sec and sec != "未分类":
                k_ind = f"industry:{sec}"
                self._sector_members_cache.setdefault(k_ind, set()).add(code)

            # 2. 多概念 (复用 ThemeMap.BROAD 过滤)
            if self.theme_map:
                tags = self.theme_map.get(code)
                for t in tags:
                    t_str = str(t).strip()
                    if t_str and t_str not in broad_concepts and t_str not in ("0", "--", "nan", "None"):
                        k_thm = f"theme:{t_str}"
                        self._sector_members_cache.setdefault(k_thm, set()).add(code)

        self._cache_initialized = True

    def _init_sector_membership(self, all_codes: Iterable[str]) -> None:
        """懒加载初始化全市场成员与各行业/概念的从属映射。"""
        if self._cache_initialized and self._sector_members_cache:
            return
        self.init_membership(all_codes)

    def get_stock_sectors(self, code: str) -> List[Tuple[str, str, str]]:
        """获取单个股票的所有所属板块: List[(sector_key, sector_type, sector_name)]。"""
        code = str(code).zfill(6)
        out = []
        sec = self.sector_map.get(code) if self.sector_map else "未分类"
        if sec and sec != "未分类":
            out.append((f"industry:{sec}", "industry", sec))

        if self.theme_map:
            broad_concepts = getattr(ThemeMap, "BROAD", set())
            for t in self.theme_map.get(code):
                t_str = str(t).strip()
                if t_str and t_str not in broad_concepts and t_str not in ("0", "--", "nan", "None"):
                    out.append((f"theme:{t_str}", "theme", t_str))
        return out

    def step_frame(
        self,
        trade_date: str,
        event_ts: float,
        quotes_map: Dict[str, Dict[str, Any]],
        market_pct: float = 0.0,
        source: str = "live_snapshot",
    ) -> Dict[str, SectorPulse]:
        """原子批处理：在同一 (trade_date, event_ts) 切片更新全市场 SectorPulse。

        quotes_map: {code: {"price": float, "percent": float, "volume": float, "vwap": float, ...}}
        """
        self._init_sector_membership(quotes_map.keys())
        w_sec = self.config.pulse_window_sec

        # 1. 更新各股滚动窗口，计算短窗增量 delta_pct
        deltas: Dict[str, float] = {}
        for code, q in quotes_map.items():
            px = float(q.get("price") or q.get("trade") or q.get("close") or 0.0)
            pct = float(q.get("percent") or q.get("pct") or 0.0)
            if px <= 0.0:
                continue
            hist = self._price_windows.setdefault(code, [])
            hist.append((event_ts, px, pct))
            # 修剪超出窗口的历史
            cutoff = event_ts - w_sec
            while len(hist) > 1 and hist[0][0] < cutoff:
                hist.pop(0)

            # 计算增量涨幅
            base_pct = hist[0][2]
            delta = pct - base_pct
            deltas[code] = delta

        # 2. 依次评估各板块脉冲
        for sector_key, members in self._sector_members_cache.items():
            tot_count = len(members)
            if tot_count < self.config.min_valid_members:
                continue

            sec_type, sec_name = sector_key.split(":", 1)
            pulse = self.pulses.get(sector_key)
            if pulse is None:
                pulse = SectorPulse(
                    sector_key=sector_key,
                    sector_type=sec_type,
                    sector_name=sec_name,
                    total_member_count=tot_count,
                    trade_date=trade_date,
                    source=source,
                )
                self.pulses[sector_key] = pulse

            pulse.total_member_count = tot_count
            pulse.asof_ts = event_ts
            pulse.trade_date = trade_date

            # 统计当日有效报价成员数与短窗异动成员
            valid_members = []
            active_list = []
            valid_pct_sum = 0.0

            for c in members:
                q = quotes_map.get(c)
                if not q:
                    continue
                px = float(q.get("price") or q.get("trade") or q.get("close") or 0.0)
                if px <= 0.0:
                    continue
                pct = float(q.get("percent") or q.get("pct") or 0.0)
                valid_members.append(c)
                valid_pct_sum += pct

                # 检查个体增量涨幅与量比承接
                d_pct = deltas.get(c, 0.0)
                vol_r = float(q.get("ratio") or q.get("vol_ratio") or 1.0)
                if d_pct >= self.config.min_member_delta_pct:
                    active_list.append({
                        "code": c,
                        "start_ts": event_ts,
                        "delta_pct": round(d_pct, 2),
                        "pct": round(pct, 2),
                        "vol_ratio": round(vol_r, 2),
                    })

            n_valid = len(valid_members)
            pulse.valid_count = n_valid
            cov_ratio = n_valid / max(1, tot_count)
            pulse.coverage_ratio = round(cov_ratio, 3)

            n_active = len(active_list)
            pulse.active_count = n_active
            act_ratio = n_active / max(1, n_valid) if n_valid > 0 else 0.0
            pulse.active_ratio = round(act_ratio, 3)
            pulse.active_members = active_list

            sec_avg_pct = (valid_pct_sum / n_valid) if n_valid > 0 else 0.0
            sec_alpha = sec_avg_pct - market_pct
            pulse.sector_alpha_pct = round(sec_alpha, 2)

            # 状态滞回与硬门禁
            # 硬门禁：覆盖率必须 >= min_coverage_ratio 且 n_valid >= min_valid_members
            is_coverage_ok = (cov_ratio >= self.config.min_coverage_ratio and n_valid >= self.config.min_valid_members)

            # 群起条件
            is_impulse_trigger = (
                is_coverage_ok
                and n_active >= self.config.min_pulse_active_count
                and act_ratio >= self.config.min_pulse_active_ratio
                and sec_alpha >= self.config.min_sector_alpha_pct
            )

            if is_impulse_trigger:
                pulse.last_pulse_ts = event_ts
                if sec_avg_pct > pulse.peak_pct:
                    pulse.peak_pct = sec_avg_pct

                if pulse.state in ("IDLE", "EXPIRED"):
                    if pulse.first_pulse_ts > 0.0:
                        # 曾发生过群起，属于二次群起
                        pulse.state = "REACTIVATED"
                        pulse.re_pulse_count += 1
                    else:
                        pulse.state = "NEW_IMPULSE"
                        pulse.first_pulse_ts = event_ts
                    pulse.sustained_bars = 1
                    pulse.max_drawback_pct = 0.0
                elif pulse.state == "DECAY_WATCH":
                    pulse.state = "REACTIVATED"
                    pulse.re_pulse_count += 1
                    pulse.sustained_bars += 1
                elif pulse.state in ("NEW_IMPULSE", "SUSTAINED", "REACTIVATED"):
                    pulse.state = "SUSTAINED"
                    pulse.sustained_bars += 1
            else:
                # 未达群起标准时的衰减与失效处理
                if pulse.state in ("NEW_IMPULSE", "SUSTAINED", "REACTIVATED"):
                    pulse.state = "DECAY_WATCH"
                    if pulse.peak_pct > 0.0 and sec_avg_pct < pulse.peak_pct:
                        drawback = pulse.peak_pct - sec_avg_pct
                        if drawback > pulse.max_drawback_pct:
                            pulse.max_drawback_pct = round(drawback, 2)
                elif pulse.state == "DECAY_WATCH":
                    # 检查是否衰减超时
                    elapsed = event_ts - pulse.last_pulse_ts
                    if elapsed > self.config.pulse_decay_timeout_sec:
                        pulse.state = "EXPIRED"

        return self.pulses


# =====================================================================
# 4. 三路候选激活数据契约 (CandidateActivation)
# =====================================================================

@dataclass
class CandidateActivation:
    """三路候选激活统一数据契约。"""
    code: str
    trade_date: str
    ts: float
    source: str          # "premarket_seed" | "intraday_sector_pulse" | "cross_day_carry"
    reason: str
    sector: str
    evidence_ids: Dict[str, Any] = field(default_factory=dict)
    candidate_seeded_ts: float = 0.0     # 盘前装入待扫候选池时间（不计入早发现）
    candidate_activated_ts: float = 0.0  # 盘中激活入池时间

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CandidateActivation:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# =====================================================================
# 5. 内存级最小席位判定状态机 (HotPoolState)
# =====================================================================

@dataclass
class StockSeatState:
    """个股在热榜席位中的完整跟踪状态。"""
    code: str
    trade_date: str
    seat: str = "NONE"                  # "BOTTOM_WATCH" | "TREND_WATCH" | "CORE_LEADER" | "EVICTED" | "NONE"
    sector_confirm_state: str = "PENDING_SECTOR" # "PENDING_SECTOR" | "SECTOR_CONFIRMED"
    primary_sector: str = ""

    # 三类关键时间戳严格分离
    candidate_seeded_ts: float = 0.0     # 盘前种子时间（不计入早发现）
    candidate_activated_ts: float = 0.0  # 盘中激活时间（不计入早发现）
    first_observed_ts: float = 0.0       # 盘中首次满足席位准入的时间（早发现）
    first_alert_ts: float = 0.0          # 首次触发状态转移提示的时间

    # 轨迹与时限记录
    first_10v_reclaim_ts: float = 0.0    # 首次站上/收复 10V 时间
    seat_enter_ts: float = 0.0           # 进入当前席位的时间
    promoted_ts: float = 0.0             # 晋级时间
    last_valid_ts: float = 0.0           # 最新有效更新时间
    peak_price: float = 0.0              # 观察期最高价
    max_drawdown_pct: float = 0.0        # 观察期最大回撤
    sustained_bars: int = 0              # 席位维持根数

    # 淘汰与恢复履历
    from_seat: str = ""                  # 淘汰前所在席位
    evicted_ts: float = 0.0              # 淘汰时间
    eviction_reason: str = ""            # 淘汰原因
    eviction_price: float = 0.0          # 淘汰时价格
    eviction_count: int = 0              # 累计淘汰次数

    # 评分与实时量价缓存
    price: float = 0.0                   # 实时现价
    pct: float = 0.0                     # 实时涨幅%
    watch_score: float = 0.0
    alpha_vs_sector: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StockSeatState:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class HotPoolState:
    """单写者最小席位判定状态机。

    严格按 (trade_date, event_ts, code) 顺序推进！
    先更新全市场 SectorPulse，再评估候选池内各股。
    """

    def __init__(
        self,
        config: Optional[HotPoolProvisionalConfig] = None,
        sector_engine: Optional[SectorPulseEngine] = None,
    ):
        self.config = config or HotPoolProvisionalConfig()
        self.sector_engine = sector_engine or SectorPulseEngine(config=self.config)

        # 候选池: code -> CandidateActivation
        self.candidates: Dict[str, CandidateActivation] = {}
        # 个股席位状态: code -> StockSeatState
        self.seats: Dict[str, StockSeatState] = {}
        # 淘汰归档记录: code -> List[Dict[str, Any]]
        self.evicted_history: Dict[str, List[Dict[str, Any]]] = {}

        # 审计与去重事件提示
        self.late_frame_audit_log: List[Dict[str, Any]] = []
        self.events_log: List[Dict[str, Any]] = []
        self.alerts_log: List[Dict[str, Any]] = []
        self._emitted_alert_keys: Set[Tuple[str, str, str, str]] = set() # (day, code, transition, pulse_id)

        # 板块第一龙头跟踪 (sector -> code)
        self.prime_leader_by_sector: Dict[str, str] = {}

        self.last_valid_ts: float = 0.0
        self.current_trade_date: str = ""

        # 预算延迟排队
        self.budget_delayed_queue: List[str] = []
        self.budget_delayed_count: int = 0
        self.budget_delay_ms: float = 0.0

    # -----------------------------------------------------------------
    # 路径 1: 盘前日线种子 (premarket_seed) — 精确收敛至 ~150–450 只
    # -----------------------------------------------------------------
    def seed_from_daily_context(
        self,
        trade_date: str,
        all_codes: Iterable[str],
        daily_ctx_getter: Callable[[str, str], Dict[str, Any]],
        seed_ts: float = 0.0,
    ) -> int:
        """基于截至昨日的日线预计算三类种子，绝不修改 is_structure_prejudged。

        1. 10V 上方演进种子;
        2. 10V 首次站上/回测承接种子;
        3. 水下止跌基座种子 (underwater_base_pool)。
        仅记录 candidate_seeded_ts，绝不计为早发现时点！
        """
        self.current_trade_date = trade_date
        ts = seed_ts if seed_ts > 0 else time.time()
        count = 0

        scored_seeds: List[Tuple[float, str, str, float, float, float]] = []

        for raw_code in all_codes:
            code = str(raw_code).zfill(6)
            daily = daily_ctx_getter(code, trade_date)
            if not daily:
                continue

            v10 = float(daily.get("vwap10") or 0.0)
            c_pre = float(daily.get("close_pre1") or 0.0)
            lo_pre = float(daily.get("lo_pre1") or 0.0)
            lo_10 = float(daily.get("lo_10d") or 0.0)
            amp_6 = float(daily.get("amp_6d") or daily.get("amp_10d") or 0.0)
            disp = float(daily.get("vwap_disp") or 99.0)

            if v10 <= 0.0 or c_pre <= 0.0:
                continue

            reason = ""
            seed_score = 0.0
            # 1. 10V 上方演进种子 (必须具备结构预判底色、或箱体就绪、或昨日强突破、或多日站稳收敛)
            is_surf = (
                bool(daily.get("is_structure_prejudged"))
                or bool(daily.get("is_box10_ready"))
                or bool(daily.get("prev_strong_vwap"))
                or (
                    c_pre >= v10
                    and int(daily.get("vwap10_hold_days") or 0) >= 3
                    and disp <= 3.5
                    and amp_6 <= 16.0
                    and float(daily.get("prev_close_pos") or 0.0) >= 0.55
                )
            )
            if is_surf:
                reason = "premarket_10v_surfing_seed"
                seed_score = 80.0 + (30.0 if daily.get("is_structure_prejudged") else 0.0) + (20.0 if daily.get("is_box10_ready") else 0.0) + (15.0 if daily.get("wash_quality") == 1.0 else 0.0) + (10.0 if daily.get("prev_strong_vwap") == 1.0 else 0.0) - min(20.0, disp * 2.0)

            # 2. 10V 首次站上/回测承接种子 (昨低曾回踩测试 10V 附近且收盘站回)
            elif (
                lo_pre <= v10 * 1.015
                and c_pre >= v10 * self.config.vwap10_tolerance_break
                and int(daily.get("vwap10_touch_count") or 0) >= 2
                and float(daily.get("prev_close_pos") or 0.0) >= 0.50
                and amp_6 <= 18.0
            ):
                reason = "premarket_10v_reclaim_seed"
                seed_score = 70.0 + int(daily.get("vwap10_touch_count") or 0) * 2.0 - disp * 2.0

            # 3. 水下止跌基座种子 (underwater_base_pool: 处于 10V 水下，振幅收敛，且低点明确止跌)
            else:
                dist_v10 = (c_pre / v10 - 1.0) * 100.0
                is_underwater = (self.config.underwater_min_depth <= dist_v10 < 0.0)
                is_amp_tight = (amp_6 <= self.config.underwater_max_amp)
                is_low_lift = (
                    lo_pre > lo_10 * 1.005
                    or (c_pre >= lo_10 * 1.02 and float(daily.get("prev_close_pos") or 0.0) >= 0.50)
                )
                if is_underwater and is_amp_tight and is_low_lift:
                    reason = "premarket_underwater_base_seed"
                    seed_score = 60.0 + max(0.0, 18.0 - amp_6) + (10.0 if float(daily.get("prev_close_pos") or 0.0) >= 0.6 else 0.0)

            if reason:
                scored_seeds.append((seed_score, code, reason, v10, c_pre, amp_6))

        # 按质量打分降序排列，并受 premarket_seed_budget (默认 350) 约束
        scored_seeds.sort(key=lambda x: x[0], reverse=True)
        picked_seeds = scored_seeds[: self.config.premarket_seed_budget]

        for _, code, reason, v10, c_pre, amp_6 in picked_seeds:
            secs = self.sector_engine.get_stock_sectors(code)
            pri_sec = secs[0][0] if secs else "industry:未分类"
            act = CandidateActivation(
                code=code,
                trade_date=trade_date,
                ts=ts,
                source="premarket_seed",
                reason=reason,
                sector=pri_sec,
                evidence_ids={"v10": v10, "close_pre": c_pre, "amp_6d": amp_6},
                candidate_seeded_ts=ts,
            )
            self.candidates[code] = act
            count += 1

        return count

    # -----------------------------------------------------------------
    # 路径 2: 盘中板块激活 (intraday_sector_pulse)
    # -----------------------------------------------------------------
    def activate_from_sector_pulse(
        self,
        trade_date: str,
        event_ts: float,
        sector_pulse: SectorPulse,
        quotes_map: Dict[str, Dict[str, Any]],
        daily_ctx_getter: Callable[[str, str], Dict[str, Any]],
    ) -> List[str]:
        """当板块脉冲处于确认群起状态时，激活该板块成员加入候选池。

        不等待 2.2% 涨幅、不要求昨涨，不受 Top600 / scored[:20] 截断。
        记录 candidate_activated_ts。
        """
        if not sector_pulse.is_confirmed:
            return []

        activated_codes = []
        members = self.sector_engine._sector_members_cache.get(sector_pulse.sector_key, set())

        for c in members:
            if c in self.candidates:
                continue

            q = quotes_map.get(c)
            if not q:
                continue
            px = float(q.get("price") or q.get("trade") or q.get("close") or 0.0)
            if px <= 0.0:
                continue

            daily = daily_ctx_getter(c, trade_date)
            v10 = float(daily.get("vwap10") or 0.0) if daily else 0.0
            dist_v10 = ((px / v10 - 1.0) * 100.0) if v10 > 0 else 0.0

            # 只要在脉冲中有正向增量，或属于水下基座/迫近 10V
            is_active_member = any(m["code"] == c for m in sector_pulse.active_members)
            is_near_10v = (self.config.underwater_min_depth <= dist_v10 <= self.config.underwater_max_depth)

            if is_active_member or is_near_10v:
                # 检查预算控制
                if len(activated_codes) >= self.config.intraday_activation_budget:
                    self.budget_delayed_queue.append(c)
                    self.budget_delayed_count += 1
                    continue

                act = CandidateActivation(
                    code=c,
                    trade_date=trade_date,
                    ts=event_ts,
                    source="intraday_sector_pulse",
                    reason=f"pulse_confirmed_{sector_pulse.sector_key}",
                    sector=sector_pulse.sector_key,
                    evidence_ids={"pulse_state": sector_pulse.state, "dist_v10": dist_v10},
                    candidate_activated_ts=event_ts,
                )
                self.candidates[c] = act
                activated_codes.append(c)

        return activated_codes

    # -----------------------------------------------------------------
    # 路径 3: 跨日继承 (cross_day_carry)
    # -----------------------------------------------------------------
    def carry_from_previous_day(
        self,
        trade_date: str,
        carried_states: Dict[str, StockSeatState],
        carry_ts: float = 0.0,
    ) -> int:
        """昨日处于 BOTTOM_WATCH / TREND_WATCH / CORE_LEADER 的标的优先恢复入候选池。"""
        self.current_trade_date = trade_date
        ts = carry_ts if carry_ts > 0 else time.time()
        count = 0

        for code, old_st in carried_states.items():
            if old_st.seat in ("BOTTOM_WATCH", "TREND_WATCH", "CORE_LEADER"):
                act = CandidateActivation(
                    code=code,
                    trade_date=trade_date,
                    ts=ts,
                    source="cross_day_carry",
                    reason=f"carried_from_{old_st.seat}",
                    sector=old_st.primary_sector,
                    candidate_seeded_ts=ts,
                )
                self.candidates[code] = act
                # 初始化席位状态，等待新鲜行情到达后重评
                st = StockSeatState(
                    code=code,
                    trade_date=trade_date,
                    seat=old_st.seat,
                    sector_confirm_state="PENDING_SECTOR",
                    primary_sector=old_st.primary_sector,
                    first_observed_ts=old_st.first_observed_ts,
                    first_10v_reclaim_ts=old_st.first_10v_reclaim_ts,
                    seat_enter_ts=ts,
                )
                self.seats[code] = st
                count += 1

        return count

    # -----------------------------------------------------------------
    # 席位评分函数 (分席位独立打分，绝不混排)
    # -----------------------------------------------------------------
    def compute_base_watch_score(
        self,
        quote: Dict[str, Any],
        daily: Dict[str, Any],
        pulse: Optional[SectorPulse],
    ) -> float:
        """底部潜伏观察席打分：低点抬升、振幅收敛、分时承接稳固。"""
        px = float(quote.get("price") or quote.get("trade") or quote.get("close") or 0.0)
        vw = float(quote.get("vwap") or px)
        bias_vwap = ((px / vw - 1.0) * 100.0) if vw > 0 else 0.0
        vol_r = float(quote.get("ratio") or quote.get("vol_ratio") or 1.0)
        amp_6d = float(daily.get("amp_6d") or daily.get("amp_10d") or 15.0)

        score = 50.0 + max(0.0, 20.0 - amp_6d) + min(10.0, bias_vwap * 5.0) + min(10.0, vol_r * 3.0)
        if pulse and pulse.is_confirmed:
            score += 15.0
        return round(score, 2)

    def compute_trend_watch_score(
        self,
        quote: Dict[str, Any],
        daily: Dict[str, Any],
        pulse: Optional[SectorPulse],
        dual_10v: Dual10VQuality,
    ) -> float:
        """10V 趋势观察席打分：10V 站稳程度、前9日量价完整度、分时双线上方。"""
        px = float(quote.get("price") or quote.get("trade") or quote.get("close") or 0.0)
        vw = float(quote.get("vwap") or px)
        pct = float(quote.get("percent") or quote.get("pct") or 0.0)

        ref_10v = dual_10v.dynamic_10v if dual_10v.dynamic_10v_usable else dual_10v.static_10v
        bias_10v = ((px / ref_10v - 1.0) * 100.0) if ref_10v > 0 else 0.0
        bias_vwap = ((px / vw - 1.0) * 100.0) if vw > 0 else 0.0

        score = 70.0 + min(15.0, bias_10v * 3.0) + min(10.0, bias_vwap * 4.0) + min(10.0, pct * 0.5)
        if dual_10v.dynamic_10v_usable:
            score += 10.0
        if pulse and pulse.is_confirmed:
            score += 15.0
        return round(score, 2)

    def compute_leader_race_score(
        self,
        quote: Dict[str, Any],
        pulse: Optional[SectorPulse],
        state: StockSeatState,
    ) -> float:
        """核心领涨席赛马打分：早涨、多涨、少回落、板块超额持续。"""
        pct = float(quote.get("percent") or quote.get("pct") or 0.0)
        sec_alpha = state.alpha_vs_sector
        mdd = state.max_drawdown_pct

        score = 100.0 + min(30.0, pct * 2.0) + min(20.0, sec_alpha * 4.0) - min(25.0, mdd * 5.0)
        return round(score, 2)

    # -----------------------------------------------------------------
    # 主驱动入口: step_frame (原子批处理，严格时序)
    # -----------------------------------------------------------------
    def step_frame(
        self,
        trade_date: str,
        event_ts: float,
        quotes_map: Dict[str, Dict[str, Any]],
        daily_ctx_getter: Callable[[str, str], Dict[str, Any]],
        obs_evidence_map: Optional[Dict[str, Dict[str, Any]]] = None,
        market_pct: float = 0.0,
        source: str = "live_snapshot",
    ) -> Dict[str, StockSeatState]:
        """按 (trade_date, event_ts, code) 顺序推进状态机。

        1. 先更新全市场 SectorPulseEngine；
        2. 触发盘中板块激活入候选池；
        3. 遍历候选池，评估四席位准入、晋级、降级与淘汰；
        4. 换龙头 (LEADER_SWITCH) 与幂等提示输出。
        对重复帧幂等；迟到帧只记入审计日志。
        """
        obs_map = obs_evidence_map or {}

        # 1. 迟到帧与重复帧幂等拦截
        if event_ts < self.last_valid_ts:
            self.late_frame_audit_log.append({
                "trade_date": trade_date,
                "event_ts": event_ts,
                "last_valid_ts": self.last_valid_ts,
                "reason": "late_frame_ignored",
            })
            return self.seats

        if event_ts == self.last_valid_ts and trade_date == self.current_trade_date:
            # 重复时间戳帧，直接返回（幂等，不重复产生事件）
            return self.seats

        self.last_valid_ts = event_ts
        self.current_trade_date = trade_date

        # Step 1: 先更新全市场板块脉冲
        pulses = self.sector_engine.step_frame(
            trade_date=trade_date,
            event_ts=event_ts,
            quotes_map=quotes_map,
            market_pct=market_pct,
            source=source,
        )

        # Step 2: 盘中板块群起激活候选
        for pulse in pulses.values():
            if pulse.is_confirmed:
                self.activate_from_sector_pulse(
                    trade_date=trade_date,
                    event_ts=event_ts,
                    sector_pulse=pulse,
                    quotes_map=quotes_map,
                    daily_ctx_getter=daily_ctx_getter,
                )

        # Step 3: 按快照依次更新候选池中各 code 的席位状态
        for code in list(self.candidates.keys()):
            q = quotes_map.get(code)
            if not q:
                continue

            px = float(q.get("price") or q.get("trade") or q.get("close") or 0.0)
            if px <= 0.0:
                continue

            daily = daily_ctx_getter(code, trade_date)
            obs_ev = obs_map.get(code)
            today_vw = float(q.get("vwap") or px)
            today_vol = float(q.get("volume") or q.get("vol") or 0.0)
            open_px = float(q.get("open") or px)
            pct = float(q.get("percent") or q.get("pct") or 0.0)

            # 评估 10V 双轨质量
            dual_10v = evaluate_10v_quality(
                daily_ctx=daily,
                obs_evidence=obs_ev,
                trade_date=trade_date,
                today_vwap=today_vw,
                today_volume=today_vol,
                evaluated_at=event_ts,
            )

            # 获取所属板块及最佳脉冲状态
            stock_secs = self.sector_engine.get_stock_sectors(code)
            best_pulse: Optional[SectorPulse] = None
            pri_sec = stock_secs[0][0] if stock_secs else "industry:未分类"

            for s_key, _, _ in stock_secs:
                p = pulses.get(s_key)
                if p and (best_pulse is None or p.active_count > best_pulse.active_count):
                    best_pulse = p
                    pri_sec = s_key

            is_sector_confirmed = (best_pulse is not None and best_pulse.is_confirmed)
            sec_confirm_state = "SECTOR_CONFIRMED" if is_sector_confirmed else "PENDING_SECTOR"

            # 现有个股席位状态
            st = self.seats.get(code)
            if st is None:
                st = StockSeatState(
                    code=code,
                    trade_date=trade_date,
                    seat="NONE",
                    sector_confirm_state=sec_confirm_state,
                    primary_sector=pri_sec,
                    candidate_seeded_ts=self.candidates[code].candidate_seeded_ts,
                    candidate_activated_ts=self.candidates[code].candidate_activated_ts,
                )
                self.seats[code] = st

            st.last_valid_ts = event_ts
            st.primary_sector = pri_sec
            st.sector_confirm_state = sec_confirm_state

            # 记录最新现价与涨幅
            st.price = px
            st.pct = pct

            # 更新最高价与回撤
            if px > st.peak_price:
                st.peak_price = px
            elif st.peak_price > 0.0:
                dd = (st.peak_price - px) / st.peak_price * 100.0
                if dd > st.max_drawdown_pct:
                    st.max_drawdown_pct = round(dd, 2)

            # 计算个股对所属板块的超额
            sec_pct = best_pulse.sector_alpha_pct + market_pct if best_pulse else 0.0
            st.alpha_vs_sector = round(pct - sec_pct, 2)

            # 当日新鲜个股量价承接与正向增量异动动能
            # 必须满足：1. 站稳分时 VWAP；2. 具备正向短窗增量或拉升动能；3. 量比有效
            vol_r = float(q.get("ratio") or q.get("vol_ratio") or 1.0)
            above_vwap = (px >= today_vw * (1.0 + self.config.intraday_min_bias_vwap / 100.0))
            pw = self.sector_engine._price_windows.get(code) or []
            delta_p = (pct - pw[0][2]) if len(pw) > 1 else (pct if px >= open_px else 0.0)
            has_momentum = (delta_p >= self.config.intraday_min_delta_pct or (pct >= 1.2 and px >= open_px))
            vol_valid = (vol_r >= self.config.intraday_min_vol_ratio)

            has_intraday_support = (above_vwap and has_momentum and vol_valid)
            has_strategy_obs = (
                isinstance(obs_ev, dict)
                and obs_ev.get("freshness") == "same_day"
                and any(
                    isinstance(obs_ev.get("early_signals", {}).get(k), dict)
                    and obs_ev["early_signals"][k].get("value") == 1
                    for k in ("sig_bottom", "sig_launch", "sig_start", "has_bottom_base")
                )
            )
            has_self_evidence = (has_intraday_support or has_strategy_obs)

            # 有效 10V 支撑与站上
            ref_10v = dual_10v.dynamic_10v if dual_10v.dynamic_10v_usable else dual_10v.static_10v
            is_above_10v = (ref_10v > 0.0 and px >= ref_10v * self.config.vwap10_tolerance_retest)
            is_break_10v = (ref_10v > 0.0 and px < ref_10v * self.config.vwap10_tolerance_break)

            # -------------------------------------------------------------
            # 四席位状态转移逻辑 (准入、晋级、降级、淘汰)
            # -------------------------------------------------------------
            current_seat = st.seat

            # 1. 未入席 (NONE) -> 准入判定
            if current_seat == "NONE":
                # 准入 10V 趋势观察席 (TREND_WATCH)
                # 必须：有效 10V 结构 + 当日自身新鲜量价承接/异动
                if is_above_10v and has_self_evidence:
                    self._transition_seat(st, "TREND_WATCH", event_ts, "10v_structure_reclaim", px, best_pulse)
                    if st.first_10v_reclaim_ts == 0.0:
                        st.first_10v_reclaim_ts = event_ts

                # 准入底部潜伏观察席 (BOTTOM_WATCH)
                # 必须同时具备：① 昨日水下低点止跌/收敛的底部证据；② 当日自身新鲜量价承接/异动
                # 严禁无自身承接的跟风股仅凭“板块群起＋昨日底部结构”入席！
                elif has_self_evidence:
                    amp_6d = float(daily.get("amp_6d") or daily.get("amp_10d") or 20.0)
                    c_pre = float(daily.get("close_pre1") or 0.0)
                    lo_pre = float(daily.get("lo_pre1") or 0.0)
                    lo_10 = float(daily.get("lo_10d") or 0.0)
                    dist_v10 = ((c_pre / ref_10v - 1.0) * 100.0) if ref_10v > 0 else -5.0

                    is_underwater = (self.config.underwater_min_depth <= dist_v10 < 0.0)
                    is_amp_tight = (amp_6d <= self.config.underwater_max_amp)
                    is_low_lift = (
                        lo_pre > lo_10 * 1.005
                        or (c_pre >= lo_10 * 1.02 and float(daily.get("prev_close_pos") or 0.0) >= 0.50)
                    )
                    if is_underwater and is_amp_tight and is_low_lift:
                        self._transition_seat(st, "BOTTOM_WATCH", event_ts, "bottom_base_and_intraday_support", px, best_pulse)

            # 2. 底部潜伏观察席 (BOTTOM_WATCH)
            elif current_seat == "BOTTOM_WATCH":
                st.sustained_bars += 1
                st.watch_score = self.compute_base_watch_score(q, daily, best_pulse)

                # 晋级条件：收复 10V（且双 10V 有效核验通过）且分时 VWAP 承接稳固 -> 晋级 TREND_WATCH
                if is_above_10v and px >= today_vw:
                    self._transition_seat(st, "TREND_WATCH", event_ts, "reclaim_10v_and_vwap", px, best_pulse)
                    if st.first_10v_reclaim_ts == 0.0:
                        st.first_10v_reclaim_ts = event_ts

                # 降级/淘汰条件：跌破基座止损位或分时持续失守且板块退潮
                elif px < today_vw * 0.97 and (best_pulse is None or best_pulse.state in ("DECAY_WATCH", "EXPIRED")):
                    self._evict_stock(st, event_ts, "bottom_break_and_pulse_decay", px, best_pulse)

            # 3. 10V 趋势观察席 (TREND_WATCH)
            elif current_seat == "TREND_WATCH":
                st.sustained_bars += 1
                st.watch_score = self.compute_trend_watch_score(q, daily, best_pulse, dual_10v)

                # 晋级条件：在 10V 与当日 VWAP 双线上方，板块已确认，且超额扩张 -> 晋级 CORE_LEADER
                if (
                    is_above_10v
                    and px >= today_vw
                    and is_sector_confirmed
                    and st.alpha_vs_sector >= 1.0
                    and st.max_drawdown_pct <= 2.5
                ):
                    self._transition_seat(st, "CORE_LEADER", event_ts, "lead_race_breakout", px, best_pulse)

                # 降级/淘汰条件：连续失守 10V 且失去分时 VWAP 承接
                elif is_break_10v and px < today_vw:
                    self._evict_stock(st, event_ts, "break_10v_and_vwap_support", px, best_pulse)

            # 4. 核心领涨席 (CORE_LEADER)
            elif current_seat == "CORE_LEADER":
                st.sustained_bars += 1
                st.watch_score = self.compute_leader_race_score(q, best_pulse, st)

                # 降级条件：超额衰减或回撤过大，退回 TREND_WATCH
                if st.alpha_vs_sector < 0.0 or st.max_drawdown_pct > 3.5 or not is_sector_confirmed:
                    self._transition_seat(st, "TREND_WATCH", event_ts, "leader_alpha_decay", px, best_pulse)

                # 淘汰条件：严重破位失守 10V
                elif is_break_10v:
                    self._evict_stock(st, event_ts, "leader_break_10v", px, best_pulse)

            # 5. 降级/淘汰记录席 (EVICTED)
            elif current_seat == "EVICTED":
                # 重新站回结构且再次确认个股自身承接与板块共振才允许恢复 (rearm)
                if is_above_10v and has_self_evidence and is_sector_confirmed:
                    self._transition_seat(st, "TREND_WATCH", event_ts, "rearmed_structure_reclaim", px, best_pulse)

        # Step 4: 检查板块内换龙头 (LEADER_SWITCH)
        self._check_leader_switches(event_ts)

        return self.seats

    def _check_leader_switches(self, event_ts: float) -> None:
        """检查各板块内部领涨龙头更替，并生成 LEADER_SWITCH 提示。"""
        # 按板块汇总处于 CORE_LEADER 的标的
        sec_leaders: Dict[str, List[StockSeatState]] = {}
        for st in self.seats.values():
            if st.seat == "CORE_LEADER" and st.primary_sector:
                sec_leaders.setdefault(st.primary_sector, []).append(st)

        for sec, leaders in sec_leaders.items():
            if not leaders:
                continue
            # 按 watch_score 降序排序
            leaders.sort(key=lambda s: s.watch_score, reverse=True)
            new_top = leaders[0]
            old_top_code = self.prime_leader_by_sector.get(sec)

            if old_top_code is None:
                self.prime_leader_by_sector[sec] = new_top.code
            elif old_top_code != new_top.code:
                # 发生了换龙头！
                self.prime_leader_by_sector[sec] = new_top.code
                pulse = self.sector_engine.pulses.get(sec)
                p_id = str(int(pulse.first_pulse_ts)) if pulse else "0"
                self._emit_alert(
                    transition="LEADER_SWITCH",
                    st=new_top,
                    event_ts=event_ts,
                    reason=f"leader_switch_from_{old_top_code}_to_{new_top.code}",
                    price=new_top.peak_price,
                    pulse_id=p_id,
                )

    def _transition_seat(
        self,
        st: StockSeatState,
        to_seat: str,
        event_ts: float,
        reason: str,
        price: float,
        pulse: Optional[SectorPulse] = None,
    ) -> None:
        """执行席位状态转移，记录时间戳与审计事件，并发出去重后的提示。"""
        old_seat = st.seat
        st.seat = to_seat
        st.seat_enter_ts = event_ts
        st.sustained_bars = 1

        if st.first_observed_ts == 0.0 and to_seat in ("BOTTOM_WATCH", "TREND_WATCH"):
            st.first_observed_ts = event_ts
        if to_seat in ("TREND_WATCH", "CORE_LEADER") and old_seat in ("BOTTOM_WATCH", "TREND_WATCH"):
            st.promoted_ts = event_ts

        evt = {
            "type": "SEAT_TRANSITION",
            "code": st.code,
            "trade_date": st.trade_date,
            "ts": event_ts,
            "from_seat": old_seat,
            "to_seat": to_seat,
            "reason": reason,
            "price": price,
            "first_observed_ts": st.first_observed_ts,
            "first_alert_ts": st.first_alert_ts,
        }
        self.events_log.append(evt)

        # 触发去重提示
        p_id = str(int(pulse.first_pulse_ts)) if pulse else "0"
        trans_name = ""
        if old_seat == "NONE" and to_seat == "BOTTOM_WATCH":
            trans_name = "FIRST_OBSERVED_BOTTOM"
        elif old_seat == "NONE" and to_seat == "TREND_WATCH":
            trans_name = "FIRST_OBSERVED_TREND"
        elif old_seat == "BOTTOM_WATCH" and to_seat == "TREND_WATCH":
            trans_name = "PROMOTED_TO_TREND"
        elif to_seat == "CORE_LEADER":
            trans_name = "PROMOTED_TO_CORE_LEADER"
        elif old_seat == "CORE_LEADER" and to_seat == "TREND_WATCH":
            trans_name = "DEMOTED_TO_TREND"
        elif old_seat == "EVICTED" and to_seat == "TREND_WATCH":
            trans_name = "REARMED"

        if trans_name:
            self._emit_alert(trans_name, st, event_ts, reason, price, pulse_id=p_id)

    def _evict_stock(
        self,
        st: StockSeatState,
        event_ts: float,
        reason: str,
        price: float,
        pulse: Optional[SectorPulse] = None,
    ) -> None:
        """淘汰标的至 EVICTED 记录席，完整保留履历。"""
        from_seat = st.seat
        st.from_seat = from_seat
        st.seat = "EVICTED"
        st.evicted_ts = event_ts
        st.eviction_reason = reason
        st.eviction_price = price
        st.eviction_count += 1
        st.seat_enter_ts = event_ts
        st.sustained_bars = 0

        record = {
            "from_seat": from_seat,
            "first_observed_ts": st.first_observed_ts,
            "promoted_ts": st.promoted_ts,
            "evicted_ts": event_ts,
            "eviction_reason": reason,
            "eviction_price": price,
            "eviction_count": st.eviction_count,
        }
        self.evicted_history.setdefault(st.code, []).append(record)

        evt = {
            "type": "SEAT_EVICTION",
            "code": st.code,
            "trade_date": st.trade_date,
            "ts": event_ts,
            "from_seat": from_seat,
            "to_seat": "EVICTED",
            "reason": reason,
            "price": price,
        }
        self.events_log.append(evt)

        p_id = str(int(pulse.first_pulse_ts)) if pulse else "0"
        self._emit_alert("EVICTED", st, event_ts, reason, price, pulse_id=p_id)

    def _emit_alert(
        self,
        transition: str,
        st: StockSeatState,
        event_ts: float,
        reason: str,
        price: float,
        pulse_id: str = "0",
    ) -> None:
        """按 (day, code, transition, pulse_id) 幂等去重发提示。"""
        key = (st.trade_date, st.code, transition, pulse_id)
        if key in self._emitted_alert_keys:
            return
        self._emitted_alert_keys.add(key)

        if st.first_alert_ts == 0.0:
            st.first_alert_ts = event_ts

        alert = {
            "type": "ALERT",
            "transition": transition,
            "code": st.code,
            "trade_date": st.trade_date,
            "ts": event_ts,
            "time": time.strftime("%H:%M:%S", time.localtime(event_ts)),
            "seat": st.seat,
            "primary_sector": st.primary_sector,
            "sector_confirm_state": st.sector_confirm_state,
            "price": price,
            "watch_score": st.watch_score,
            "alpha_vs_sector": st.alpha_vs_sector,
            "reason": reason,
            "first_observed_ts": st.first_observed_ts,
            "first_alert_ts": st.first_alert_ts,
        }
        self.alerts_log.append(alert)

    # -----------------------------------------------------------------
    # 序列化与反序列化
    # -----------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """导出全量状态为字典。"""
        return {
            "current_trade_date": self.current_trade_date,
            "last_valid_ts": self.last_valid_ts,
            "candidates": {c: ca.to_dict() for c, ca in self.candidates.items()},
            "seats": {c: st.to_dict() for c, st in self.seats.items()},
            "evicted_history": self.evicted_history,
            "events_log": self.events_log,
            "alerts_log": self.alerts_log,
            "prime_leader_by_sector": self.prime_leader_by_sector,
            "pulses": {k: p.to_dict() for k, p in self.sector_engine.pulses.items()},
            "config": asdict(self.config),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HotPoolState:
        """从字典恢复全量状态。"""
        cfg_data = data.get("config") or {}
        cfg = HotPoolProvisionalConfig(**{k: v for k, v in cfg_data.items() if k in HotPoolProvisionalConfig.__dataclass_fields__})
        instance = cls(config=cfg)
        instance.current_trade_date = data.get("current_trade_date", "")
        instance.last_valid_ts = data.get("last_valid_ts", 0.0)

        for c, ca_d in (data.get("candidates") or {}).items():
            instance.candidates[c] = CandidateActivation.from_dict(ca_d)
        for c, st_d in (data.get("seats") or {}).items():
            instance.seats[c] = StockSeatState.from_dict(st_d)
        instance.evicted_history = data.get("evicted_history") or {}
        instance.events_log = data.get("events_log") or []
        instance.alerts_log = data.get("alerts_log") or []
        instance.prime_leader_by_sector = data.get("prime_leader_by_sector") or {}

        # 恢复已发提示 key
        for al in instance.alerts_log:
            k = (al.get("trade_date", ""), al.get("code", ""), al.get("transition", ""), "0")
            instance._emitted_alert_keys.add(k)

        # 恢复板块脉冲
        for k, p_d in (data.get("pulses") or {}).items():
            instance.sector_engine.pulses[k] = SectorPulse.from_dict(p_d)

        return instance


# =====================================================================
# 6. 跨进程原子持久化与开盘恢复工具函数
# =====================================================================

def save_hot_pool_state(
    state: HotPoolState,
    log_dir: Optional[str] = None,
    ramdisk_dir: Optional[str] = None,
) -> bool:
    """跨进程原子持久化当前交易日热榜状态。

    优先写入 G:\fusion_shadow\hot_pool_{day}.json（若可用），
    同时落盘至 logs/fusion_shadow/hot_pool_{day}.json。
    复用 ats.persistence_lock 原子锁与替换。
    """
    day = state.current_trade_date or time.strftime("%Y-%m-%d")
    payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)

    dirs = []
    if ramdisk_dir and os.path.exists(ramdisk_dir):
        dirs.append(ramdisk_dir)
    elif os.path.exists(r"G:\fusion_shadow"):
        dirs.append(r"G:\fusion_shadow")
    if log_dir and log_dir not in dirs:
        dirs.append(log_dir)
    if not dirs:
        dirs.append(os.path.join(_app_root(), "logs", "fusion_shadow"))

    success = False
    for target_dir in dirs:
        try:
            os.makedirs(target_dir, exist_ok=True)
            final_path = os.path.join(target_dir, f"hot_pool_{day}.json")
            tmp_path = os.path.join(target_dir, f"hot_pool_{day}.json.tmp_{int(time.time()*1000)}")

            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(payload)

            if _HAS_PERSIST_LOCK:
                with directory_write_lock(target_dir):
                    replace_with_retry(tmp_path, final_path)
            else:
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.replace(tmp_path, final_path)
            success = True
        except Exception as exc:
            logger.warning("[HotPool] 保存状态失败 %s: %s", target_dir, exc)

    return success


def load_hot_pool_state(
    day: str,
    log_dir: Optional[str] = None,
    ramdisk_dir: Optional[str] = None,
) -> Optional[HotPoolState]:
    """加载指定交易日的热榜状态。"""
    dirs = []
    if ramdisk_dir and os.path.exists(ramdisk_dir):
        dirs.append(ramdisk_dir)
    elif os.path.exists(r"G:\fusion_shadow"):
        dirs.append(r"G:\fusion_shadow")
    if log_dir and os.path.exists(log_dir) and log_dir not in dirs:
        dirs.append(log_dir)

    try:
        from ats.ui.fusion_ladder_dialog import _shadow_dir_candidates
        for cd in _shadow_dir_candidates():
            if cd and os.path.exists(cd) and cd not in dirs:
                dirs.append(cd)
    except Exception:
        pass

    fallback_dir = os.path.join(_app_root(), "logs", "fusion_shadow")
    if os.path.exists(fallback_dir) and fallback_dir not in dirs:
        dirs.append(fallback_dir)

    for target_dir in dirs:
        p = os.path.join(target_dir, f"hot_pool_{day}.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return HotPoolState.from_dict(data)
            except Exception as exc:
                logger.warning("[HotPool] 读取状态异常 %s: %s", p, exc)
    return None


def load_previous_day_carry_states(
    current_day: str,
    log_dir: Optional[str] = None,
    ramdisk_dir: Optional[str] = None,
) -> Dict[str, StockSeatState]:
    """开盘自动寻找上一有效交易日的 hot_pool 档案，提取昨日收盘处于在席状态的标的。"""
    dirs = []
    if ramdisk_dir and os.path.exists(ramdisk_dir):
        dirs.append(ramdisk_dir)
    elif os.path.exists(r"G:\fusion_shadow"):
        dirs.append(r"G:\fusion_shadow")
    if log_dir and os.path.exists(log_dir) and log_dir not in dirs:
        dirs.append(log_dir)

    try:
        from ats.ui.fusion_ladder_dialog import _shadow_dir_candidates
        for cd in _shadow_dir_candidates():
            if cd and os.path.exists(cd) and cd not in dirs:
                dirs.append(cd)
    except Exception:
        pass

    fallback_dir = os.path.join(_app_root(), "logs", "fusion_shadow")
    if os.path.exists(fallback_dir) and fallback_dir not in dirs:
        dirs.append(fallback_dir)

    all_files = []
    for d in dirs:
        if os.path.exists(d):
            all_files.extend(glob.glob(os.path.join(d, "hot_pool_*.json")))

    prev_days = []
    for f in all_files:
        base = os.path.basename(f)
        # hot_pool_2026-11-04.json
        parts = base.replace("hot_pool_", "").replace(".json", "")
        if parts < current_day:
            prev_days.append(parts)

    if not prev_days:
        return {}

    latest_prev_day = sorted(set(prev_days))[-1]
    prev_state = load_hot_pool_state(latest_prev_day, log_dir, ramdisk_dir)
    if not prev_state:
        return {}

    carry = {}
    for code, st in prev_state.seats.items():
        if st.seat in ("BOTTOM_WATCH", "TREND_WATCH", "CORE_LEADER"):
            carry[code] = st
    return carry

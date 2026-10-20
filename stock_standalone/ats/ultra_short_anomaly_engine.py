# -*- coding: utf-8 -*-
"""
ats/ultra_short_anomaly_engine.py — ATS 全底层超短线特异潜能挖掘与市场温度周期赛马（去弱留强）核心引擎 (SSOT)
========================================================================================================
核心设计理念（源自实盘 688689 银河微电 / 300571 平治信息 / 300299 富春股份 / SBC 多日分时缓存 / 64.3℃ 市场温度闭环）：
1. 【阶段一：连续杀跌阶段点“小级别企稳异动”与特异底座挖掘 (Idiosyncratic Base & SBC Structure Mining)】：
   - 深度穿透 **SBC 多日分时内存缓存 (`TDXGlobalCachePool` + `SBCIndicatorCache`)** 与全市场宽表预计算多日字段；
   - 识别 **【📈 连续杀跌 + 小级别企稳异动 + 今天高开破反转加速】**（如 688689 银河微电、300299 富春股份、300571 平治信息）：
     * 连续杀跌：多日分时高点与重心沿多日均价线逐级下杀（累计回撤 >= 4.5%），无像样反弹，到达阶段支撑线 (`支撑 ch_supp`)；
     * 小级别企稳异动：在阶段低点出现多日低点走平（如银河微电 33.3->33.2->33.1，富春股份 5.4->5.3->5.45）或日内午后底抬高企稳，并伴随探底拉回均线收红 / 脉冲试盘小幅放量；
     * 今天高开加速结构：今日平高开/跳空高开，不破小级别企稳底座，放量突破 SBC `反转线 (rev)` / 昨高 `1D` / 多日 `5D VWAP` 直接进入主升加速！
2. 【阶段二：盘中“赛马逻辑突然冒头”毫秒级捕获 (Horse-Race Emergence Capture)】：
   - 聚焦重点关注池（★ 自选股 + 精选观察池 + SBC 盯盘缓存池 + 资金主线 + 新股次新股）；
   - 实时融合分时价格、VWAP 均价线、SBC 反转线/支撑线、虚拟量比、涨速 DFF、OpeningBubble 阶梯跃迁；
   - 毫秒级捕获【🚀 高开破反转线加速（银河微电/富春股份模式）】与【🏇 盘中破颈线赛马突然冒头（平治信息模式）】。
3. 【阶段三：市场温度从冷到热感知与“冷时跟单、过热未加速即出局”去弱留强铁律 (Temperature Culling)】：
   - 实时感知全市场温度（0℃ ~ 100℃）从冰点/偏冷 -> 回暖升温 -> 过热高潮（如 64.3℃, 3590家上涨）的动态演进；
   - 在市场偏冷时异动跟单的个股（Cold-Market Anomaly Seed），当市场升温至过热区（>= 60℃ 或较跟单时升温 >= 10℃）：
     * 若已借势主升加速脱离成本区 -> 【👑 加速晋级·留强锁仓 (STRONG_LOCKED)】；
     * 若在普涨过热期仍滞涨未加速、受阻反转线/颈线或冲高回落跌破 VWAP -> 【⚠️ 过热未加速·去弱出局 (OVERHEAT_CULL_EXIT)】！
4. 【极限性能保证】：
   - 纯 NumPy 零拷贝矩阵运算 + SBC 历史分时按日 O(1) 摘要缓存 + `__slots__` 轻量状态机，全市场 5500 只股票单次扫描耗时 < 3ms，零磁盘 I/O，零主线程阻塞。
"""

import math
import time
import threading
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional, Any, Set
import numpy as np
import pandas as pd

from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("UltraShortAnomalyEngine")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clean_code(c: Any) -> str:
    if isinstance(c, str) and len(c) == 6 and c.isdigit():
        return c
    s = str(c).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else s


def _is_index_or_etf(code: str, name: str = "") -> bool:
    c = _clean_code(code)
    if c.startswith(("399", "999", "899", "510", "512", "513", "515", "516", "518", "588", "159")):
        return True
    if c in ("000001", "000300", "000016", "000905", "000852", "000688"):
        if name and any(k in name for k in ("平安", "银行", "机械", "港务", "健康")):
            return False
        if name and any(k in name for k in ("上证", "指数", "沪深", "中证", "科创")):
            return True
    if name and any(k in name for k in ("指数", "ETF", "成指", "综指", "北证50", "科创50", "创业板指")):
        return True
    return False


# =============================================================================
# 1. 市场温度周期定义与赛马状态常量
# =============================================================================

TEMP_REGIME_ICE_COLD = "ICE_COLD"           # ❄️ 冰点极寒 (< 35℃)
TEMP_REGIME_COLD_WEAK = "COLD_WEAK"         # 🌨️ 偏冷分歧 (35℃ ~ 48℃)
TEMP_REGIME_WARMING = "WARMING_HORSE"       # 🌱 回暖赛马 (48℃ ~ 60℃)
TEMP_REGIME_OVERHEATED = "OVERHEATED_TEST"  # 🔥 过热大考 (>= 60℃, 去弱留强审判期)
TEMP_REGIME_COOLING_EBB = "COOLING_EBB"     # 🌊 冲高退潮 (从高点回落 >= 6℃)

TEMP_REGIME_LABELS = {
    TEMP_REGIME_ICE_COLD: "❄️ 冰点极寒(逆势选种)",
    TEMP_REGIME_COLD_WEAK: "🌨️ 偏冷分歧(特异试盘)",
    TEMP_REGIME_WARMING: "🌱 回暖升温(赛马点火)",
    TEMP_REGIME_OVERHEATED: "🔥 过热大考(未加速出局)",
    TEMP_REGIME_COOLING_EBB: "🌊 冲高退潮(防守汰弱)",
}

# 昨日/阶段点特异结构类型
STRUCT_SBC_KILL_STABILIZE_ACCEL = "SBC_KILL_STABILIZE_HIGH_OPEN_ACCEL"  # 📈 SBC连杀小企稳·高开加速 (银河微电/富春股份)
STRUCT_HIGH_OPEN_KILL_REBOUND = "HIGH_OPEN_KILL_REBOUND"                # 🎯 阶段点高开杀跌·深V收红
STRUCT_SPIKE_PULLBACK_MILD_VOL = "SPIKE_PULLBACK_MILD_VOL"              # ⚡ 阶段点冲高回落·放量试盘 (平治信息)
STRUCT_STAGE_IDIOSYNCRATIC = "STAGE_IDIOSYNCRATIC_HOLD"                 # 🛡️ 阶段低点·逆势特异抗跌
STRUCT_FOCUS_COLD_SPARK = "FOCUS_COLD_SPARK"                            # ❄️ 重点池冷盘逆势点火

STRUCT_LABELS = {
    STRUCT_SBC_KILL_STABILIZE_ACCEL: "📈 连杀小企稳·高开加速",
    STRUCT_HIGH_OPEN_KILL_REBOUND: "🎯 阶段高开杀跌·深V收红",
    STRUCT_SPIKE_PULLBACK_MILD_VOL: "⚡ 冲高回落·小幅放量试盘",
    STRUCT_STAGE_IDIOSYNCRATIC: "🛡️ 阶段低点·逆势特异承接",
    STRUCT_FOCUS_COLD_SPARK: "❄️ 重点池·冷盘逆势异动",
}

# 赛马生命周期与去弱留强状态
RACE_STATE_STRONG_LOCKED = "STRONG_LOCKED"        # 👑 加速晋级·留强
RACE_STATE_HORSE_EMERGING = "HORSE_EMERGING"      # 🏇 赛马突然冒头
RACE_STATE_COLD_SEED_WATCH = "COLD_SEED_WATCH"    # 🌱 冷盘特异跟单(观察)
RACE_STATE_OVERHEAT_EXIT = "OVERHEAT_CULL_EXIT"   # ⚠️ 过热未加速·出局
RACE_STATE_WEAK_BROKEN_EXIT = "WEAK_BROKEN_EXIT"  # ⛔ 冲高回落/破位·淘汰

RACE_STATE_LABELS = {
    RACE_STATE_STRONG_LOCKED: "👑 特异加速·留强",
    RACE_STATE_HORSE_EMERGING: "🏇 赛马突然冒头",
    RACE_STATE_COLD_SEED_WATCH: "🌱 阶段特异蓄势",
    RACE_STATE_OVERHEAT_EXIT: "⚠️ 过热未加速·出局",
    RACE_STATE_WEAK_BROKEN_EXIT: "⛔ 冲高回落·去弱淘汰",
}

RACE_STATE_SORT_WEIGHT = {
    RACE_STATE_HORSE_EMERGING: 90000.0,   # 正在突然冒头的赛马最优先提醒操盘手捕捉
    RACE_STATE_STRONG_LOCKED: 85000.0,    # 已经高开加速/主升的留强真龙
    RACE_STATE_COLD_SEED_WATCH: 50000.0,  # 蓄势待发特异种子
    RACE_STATE_OVERHEAT_EXIT: 20000.0,    # 过热未加速需立即去弱出局警示
    RACE_STATE_WEAK_BROKEN_EXIT: 10000.0, # 破位弱势淘汰
}


@dataclass
class UltraShortConfig:
    """超短特异挖掘与温度周期赛马参数配置"""
    # 温度阈值
    cold_temp_threshold: float = 48.0          # 偏冷市场温度上限 (℃)
    overheat_temp_threshold: float = 60.0      # 过热大考市场温度门槛 (℃，如图5的 64.3℃)
    temp_rise_cull_delta: float = 10.0         # 从跟单到当前升温触发未加速大考的温差 (℃)
    # 阶段点与特异结构参数
    min_mild_vol_ratio_1d: float = 1.05        # 昨日小幅放量下限
    max_mild_vol_ratio_1d: float = 3.20        # 昨日小幅放量上限 (排除天量见顶)
    min_idiosyncratic_alpha_1d: float = 1.0    # 昨日相对大盘/中位数特异超额 (%)
    # 盘中赛马冒头与加速参数
    emerging_min_pct: float = 1.6              # 赛马冒头最小涨幅 (%)
    emerging_min_vol_ratio: float = 1.15       # 赛马冒头最小虚拟量比
    accel_main_board_pct: float = 5.5          # 10cm 主板确认主升加速涨幅 (%)
    accel_20cm_board_pct: float = 7.5          # 20cm/30cm 双创北交确认主升加速涨幅 (%)
    # 过热未加速去弱淘汰参数
    overheat_stagnant_max_pct: float = 4.2     # 过热期仍低于此涨幅视为未加速滞涨 (%)
    overheat_min_gain_from_entry: float = 1.5  # 过热期较入池跟单价最小应有推进幅度 (%)
    max_pullback_from_high_pct: float = 2.8    # 冒头后从日内高点最大允许回落幅度 (%)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# 2. 市场温度从冷到热全周期感知器 (MarketTemperatureCycleTracker)
# =============================================================================

class MarketTemperatureCycleTracker:
    """
    感知市场温度从冷到热、从低到高的全周期演进轨迹：
    - 统计当前上涨/下跌/平盘家数、全市场均幅、中位数涨幅；
    - 追踪今日开盘温度、最低冰点温度、最高高潮温度、昨日基准温度；
    - 计算近 5m / 15m 温度变化斜率与当前所处情绪阶段 (Regime)。
    """
    __slots__ = (
        'today_str', 'curr_temp', 'open_temp', 'min_temp', 'max_temp',
        'prev_day_temp', 'up_count', 'down_count', 'flat_count', 'total_count',
        'avg_pct', 'median_pct', 'prev_median_pct', 'sh_pct', 'sh_prev_pct',
        'temp_slope_5m', 'temp_slope_15m', 'regime', 'regime_label',
        '_history'
    )

    def __init__(self):
        self.today_str: str = time.strftime("%Y-%m-%d")
        self.curr_temp: float = 50.0
        self.open_temp: float = 50.0
        self.min_temp: float = 50.0
        self.max_temp: float = 50.0
        self.prev_day_temp: float = 50.0
        self.up_count: int = 0
        self.down_count: int = 0
        self.flat_count: int = 0
        self.total_count: int = 0
        self.avg_pct: float = 0.0
        self.median_pct: float = 0.0
        self.prev_median_pct: float = 0.0
        self.sh_pct: float = 0.0
        self.sh_prev_pct: float = 0.0
        self.temp_slope_5m: float = 0.0
        self.temp_slope_15m: float = 0.0
        self.regime: str = TEMP_REGIME_COLD_WEAK
        self.regime_label: str = TEMP_REGIME_LABELS[TEMP_REGIME_COLD_WEAK]
        self._history: deque = deque(maxlen=180)  # (timestamp, temp)

    def reset_daily(self, today_str: Optional[str] = None):
        self.today_str = today_str or time.strftime("%Y-%m-%d")
        self._history.clear()
        self.open_temp = 50.0
        self.min_temp = 100.0
        self.max_temp = 0.0
        self.temp_slope_5m = 0.0
        self.temp_slope_15m = 0.0

    def update_from_arrays(
        self,
        pcts: np.ndarray,
        per1d_arr: Optional[np.ndarray] = None,
        sh_pct: float = 0.0,
        sh_prev_pct: float = 0.0,
        now_ts: Optional[float] = None,
        overheat_threshold: float = 60.0,
        cold_threshold: float = 48.0,
    ) -> Dict[str, Any]:
        """使用纯 NumPy 向量化秒算市场温度与冷热梯度 (耗时 < 0.2ms)"""
        now = now_ts if now_ts is not None else time.time()
        curr_day = time.strftime("%Y-%m-%d", time.localtime(now))
        if curr_day != self.today_str:
            self.reset_daily(curr_day)

        valid_pcts = pcts[~np.isnan(pcts)]
        total = int(len(valid_pcts))
        if total <= 0:
            return self.to_dict()

        up = int(np.sum(valid_pcts > 0.0))
        down = int(np.sum(valid_pcts < 0.0))
        flat = total - up - down

        # 与 DistributionBarChart (market_tasks.distribution_projection) 100% 同源温度定义：
        # temp = up / total * 100.0 (如图5: 3590 / (3590+1778+216) = 64.3℃)
        raw_temp = (up / float(total)) * 100.0
        avg_p = float(np.mean(valid_pcts))
        med_p = float(np.median(valid_pcts))

        self.up_count = up
        self.down_count = down
        self.flat_count = flat
        self.total_count = total
        self.avg_pct = round(avg_p, 2)
        self.median_pct = round(med_p, 2)
        self.curr_temp = round(raw_temp, 1)
        self.sh_pct = round(float(sh_pct), 2)
        self.sh_prev_pct = round(float(sh_prev_pct), 2)

        # 昨日温度与昨日中位数评估 (用于判断昨日是否处于偏冷/回落环境)
        if per1d_arr is not None and len(per1d_arr) > 0:
            v_p1 = per1d_arr[~np.isnan(per1d_arr)]
            if len(v_p1) > 10:
                up_1d = int(np.sum(v_p1 > 0.0))
                self.prev_day_temp = round((up_1d / float(len(v_p1))) * 100.0, 1)
                self.prev_median_pct = round(float(np.median(v_p1)), 2)

        # 初始化或更新日内开盘/最低/最高温度锚点
        if not self._history:
            self.open_temp = self.curr_temp
            self.min_temp = self.curr_temp
            self.max_temp = self.curr_temp
        else:
            if self.curr_temp < self.min_temp:
                self.min_temp = self.curr_temp
            if self.curr_temp > self.max_temp:
                self.max_temp = self.curr_temp

        self._history.append((now, self.curr_temp))

        # 计算 5m / 15m 温度变化量
        t_5m_ago = self.curr_temp
        t_15m_ago = self.open_temp
        for ts_h, temp_h in reversed(self._history):
            age_sec = now - ts_h
            if age_sec <= 300.0:
                t_5m_ago = temp_h
            if age_sec <= 900.0:
                t_15m_ago = temp_h
            else:
                break
        self.temp_slope_5m = round(self.curr_temp - t_5m_ago, 1)
        self.temp_slope_15m = round(self.curr_temp - t_15m_ago, 1)

        # 判定当前市场温度周期阶段 (Regime)
        drop_from_max = self.max_temp - self.curr_temp
        rise_from_min = self.curr_temp - min(self.min_temp, self.prev_day_temp)

        if self.curr_temp >= overheat_threshold or (self.curr_temp >= 57.5 and self.avg_pct >= 1.05):
            if drop_from_max >= 6.0 and self.temp_slope_5m < -1.5:
                self.regime = TEMP_REGIME_COOLING_EBB
            else:
                self.regime = TEMP_REGIME_OVERHEATED
        elif drop_from_max >= 6.5 and self.curr_temp < 55.0:
            self.regime = TEMP_REGIME_COOLING_EBB
        elif self.curr_temp < 35.0:
            self.regime = TEMP_REGIME_ICE_COLD
        elif self.curr_temp < cold_threshold:
            if rise_from_min >= 5.0 and self.temp_slope_5m >= 1.5:
                self.regime = TEMP_REGIME_WARMING
            else:
                self.regime = TEMP_REGIME_COLD_WEAK
        else:
            # 48℃ ~ 60℃
            self.regime = TEMP_REGIME_WARMING

        self.regime_label = TEMP_REGIME_LABELS.get(self.regime, "🌱 回暖赛马")
        return self.to_dict()

    @property
    def is_overheated(self) -> bool:
        return self.regime == TEMP_REGIME_OVERHEATED or self.curr_temp >= 60.0

    @property
    def is_cold_or_ice(self) -> bool:
        return self.regime in (TEMP_REGIME_ICE_COLD, TEMP_REGIME_COLD_WEAK) or self.curr_temp < 48.0

    def get_trend_arrow_text(self) -> str:
        """生成简洁的温度趋势与阶段提示文案（供图表与顶栏直接展示）"""
        delta_day = self.curr_temp - self.min_temp
        if self.is_overheated:
            return f"🔥过热大考(低{self.min_temp:.0f}℃→{self.curr_temp:.1f}℃ | 未加速出局)"
        elif self.regime == TEMP_REGIME_WARMING:
            return f"🌱升温赛马(低{self.min_temp:.0f}℃↑+{delta_day:.1f}℃)"
        elif self.regime == TEMP_REGIME_COOLING_EBB:
            return f"🌊降温分歧(高{self.max_temp:.0f}℃↓)"
        elif self.regime == TEMP_REGIME_ICE_COLD:
            return f"❄️冰点选种({self.curr_temp:.1f}℃逆势关注)"
        return f"🌨️偏冷试盘(低{self.min_temp:.0f}℃→{self.curr_temp:.1f}℃)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "today_str": self.today_str,
            "curr_temp": self.curr_temp,
            "open_temp": self.open_temp,
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "prev_day_temp": self.prev_day_temp,
            "temp_rise_from_min": round(self.curr_temp - min(self.min_temp, self.prev_day_temp), 1),
            "temp_drop_from_max": round(self.max_temp - self.curr_temp, 1),
            "temp_slope_5m": self.temp_slope_5m,
            "temp_slope_15m": self.temp_slope_15m,
            "up_count": self.up_count,
            "down_count": self.down_count,
            "flat_count": self.flat_count,
            "total_count": self.total_count,
            "avg_pct": self.avg_pct,
            "median_pct": self.median_pct,
            "prev_median_pct": self.prev_median_pct,
            "sh_pct": self.sh_pct,
            "sh_prev_pct": self.sh_prev_pct,
            "regime": self.regime,
            "regime_label": self.regime_label,
            "trend_summary": self.get_trend_arrow_text(),
        }


# =============================================================================
# 3. 单股超短特异赛马轻量状态槽 (UltraShortHorseItem)
# =============================================================================

class UltraShortHorseItem:
    """单只股票的特异底座、SBC分时缓存结构、赛马冒头轨迹与温度周期去弱留强状态容器 (__slots__ 零字典开销)"""
    __slots__ = (
        'code', 'name', 'sector', 'is_focus_pool', 'is_20cm_board',
        'structure_type', 'structure_label', 'structure_desc',
        'down_days_count', 'stage_low_price', 'neck_price',
        'sbc_supp_price', 'sbc_rev_price', 'sbc_vwap_5d', 'has_sbc_cache', 'sbc_drop_pct',
        'vol_ratio_1d', 'alpha_1d', 'alpha_today',
        'entry_ts', 'entry_time_str', 'entry_price', 'entry_pct', 'entry_temp',
        'was_cold_anomaly', 'first_emerge_ts', 'first_emerge_time_str',
        'curr_price', 'curr_pct', 'open_pct', 'high_pct', 'low_pct',
        'vwap', 'vol_ratio', 'amount_yi', 'turnover_pct', 'dff_speed',
        'tier_jumps', 'neck_break_pct', 'is_gap_open_low', 'is_above_vwap',
        'is_accelerated', 'race_state', 'race_state_label',
        'horse_score', 'stop_loss_price', 'target_desc', 'decision_reason',
        'updated_ts'
    )

    def __init__(self, code: str, name: str = ""):
        self.code: str = code
        self.name: str = name
        self.sector: str = "主流活跃"
        self.is_focus_pool: bool = False
        self.is_20cm_board: bool = code.startswith(("688", "689", "300", "301", "920", "83", "87", "43"))

        # 阶段一：昨日/阶段点特异结构底座 & SBC 多日分时缓存特征
        self.structure_type: str = ""
        self.structure_label: str = ""
        self.structure_desc: str = ""
        self.down_days_count: int = 0
        self.stage_low_price: float = 0.0
        self.neck_price: float = 0.0       # 多日压制颈线位 / SBC 反转线 (rev_line 或 lasth1d)
        self.sbc_supp_price: float = 0.0   # SBC 支撑线 (支撑 33.75 / 5.72)
        self.sbc_rev_price: float = 0.0    # SBC 反转线 (反转 35.78 / 5.84)
        self.sbc_vwap_5d: float = 0.0      # SBC 多日黄色累计均价线 (5D VWAP)
        self.has_sbc_cache: bool = False   # 是否命中 SBC 盯盘分时缓存
        self.sbc_drop_pct: float = 0.0     # SBC 多日连续杀跌累计幅度 (%)
        self.vol_ratio_1d: float = 1.0     # 昨日小幅放量倍数
        self.alpha_1d: float = 0.0         # 昨日相对大盘/群体超额 (%)
        self.alpha_today: float = 0.0      # 今日相对大盘/群体超额 (%)

        # 首次发现与温度锚点 (用于“冷时异动跟单 -> 过热未加速出局”判决)
        self.entry_ts: float = 0.0
        self.entry_time_str: str = "--:--"
        self.entry_price: float = 0.0
        self.entry_pct: float = 0.0
        self.entry_temp: float = 50.0
        self.was_cold_anomaly: bool = False
        self.first_emerge_ts: float = 0.0
        self.first_emerge_time_str: str = "--:--"

        # 实时盘口与分时赛马特征
        self.curr_price: float = 0.0
        self.curr_pct: float = 0.0
        self.open_pct: float = 0.0
        self.high_pct: float = 0.0
        self.low_pct: float = 0.0
        self.vwap: float = 0.0
        self.vol_ratio: float = 1.0
        self.amount_yi: float = 0.0
        self.turnover_pct: float = 0.0
        self.dff_speed: float = 0.0
        self.tier_jumps: int = 0
        self.neck_break_pct: float = 0.0
        self.is_gap_open_low: bool = False
        self.is_above_vwap: bool = True
        self.is_accelerated: bool = False

        # 赛马状态与去弱留强结论
        self.race_state: str = RACE_STATE_COLD_SEED_WATCH
        self.race_state_label: str = RACE_STATE_LABELS[RACE_STATE_COLD_SEED_WATCH]
        self.horse_score: float = 0.0
        self.stop_loss_price: float = 0.0
        self.target_desc: str = ""
        self.decision_reason: str = ""
        self.updated_ts: float = 0.0

    # ── 跨模块统一兼容属性别名 (供 CapitalDragonEngine / FavoritePanel / NewStockPanel 无缝读取) ──
    @property
    def horse_state(self) -> str:
        if self.race_state == RACE_STATE_STRONG_LOCKED:
            return "KEEP_STRONG_ACCEL"
        if self.race_state == RACE_STATE_HORSE_EMERGING:
            return "HORSE_SURGE_EMERGE"
        if self.race_state == RACE_STATE_COLD_SEED_WATCH:
            return "STAGE_BASE_WATCH"
        return self.race_state

    @property
    def horse_label(self) -> str:
        return self.race_state_label

    @property
    def base_pattern(self) -> str:
        return self.structure_type or "NONE"

    @property
    def base_label(self) -> str:
        return self.structure_label

    @property
    def total_score(self) -> float:
        return self.horse_score

    @property
    def support_price(self) -> float:
        return self.sbc_supp_price if self.sbc_supp_price > 0 else self.stage_low_price

    @property
    def yesterday_high(self) -> float:
        return self.neck_price

    @property
    def action_advice(self) -> str:
        return self.target_desc

    @property
    def reason(self) -> str:
        return self.decision_reason

    def to_dict(self, curr_market_temp: float = 50.0) -> Dict[str, Any]:
        temp_chain = f"{self.entry_temp:.0f}℃→{curr_market_temp:.0f}℃"
        return {
            "code": self.code,
            "name": self.name,
            "sector": self.sector,
            "is_focus_pool": self.is_focus_pool,
            "is_20cm_board": self.is_20cm_board,
            "structure_type": self.structure_type,
            "structure_label": self.structure_label,
            "structure_desc": self.structure_desc,
            "down_days_count": self.down_days_count,
            "stage_low_price": round(self.stage_low_price, 2),
            "neck_price": round(self.neck_price, 2),
            "sbc_supp_price": round(self.sbc_supp_price, 2),
            "sbc_rev_price": round(self.sbc_rev_price, 2),
            "sbc_vwap_5d": round(self.sbc_vwap_5d, 2),
            "has_sbc_cache": self.has_sbc_cache,
            "sbc_drop_pct": round(self.sbc_drop_pct, 2),
            "vol_ratio_1d": round(self.vol_ratio_1d, 2),
            "alpha_1d": round(self.alpha_1d, 2),
            "alpha_today": round(self.alpha_today, 2),
            "entry_ts": self.entry_ts,
            "entry_time_str": self.entry_time_str,
            "entry_price": round(self.entry_price, 2),
            "entry_pct": round(self.entry_pct, 2),
            "entry_temp": round(self.entry_temp, 1),
            "temp_chain": temp_chain,
            "was_cold_anomaly": self.was_cold_anomaly,
            "first_emerge_ts": self.first_emerge_ts,
            "first_emerge_time_str": self.first_emerge_time_str,
            "curr_price": round(self.curr_price, 2),
            "curr_pct": round(self.curr_pct, 2),
            "open_pct": round(self.open_pct, 2),
            "high_pct": round(self.high_pct, 2),
            "low_pct": round(self.low_pct, 2),
            "vwap": round(self.vwap, 2),
            "vol_ratio": round(self.vol_ratio, 2),
            "amount_yi": round(self.amount_yi, 2),
            "turnover_pct": round(self.turnover_pct, 2),
            "dff_speed": round(self.dff_speed, 2),
            "tier_jumps": self.tier_jumps,
            "neck_break_pct": round(self.neck_break_pct, 2),
            "is_gap_open_low": self.is_gap_open_low,
            "is_above_vwap": self.is_above_vwap,
            "is_accelerated": self.is_accelerated,
            "race_state": self.race_state,
            "race_state_label": self.race_state_label,
            "horse_state": self.horse_state,
            "horse_label": self.horse_label,
            "horse_score": round(self.horse_score, 1),
            "total_score": round(self.horse_score, 1),
            "stop_loss_price": round(self.stop_loss_price, 2),
            "target_desc": self.target_desc,
            "decision_reason": self.decision_reason,
            "sort_priority": round(
                RACE_STATE_SORT_WEIGHT.get(self.race_state, 10000.0)
                + (5000.0 if self.is_focus_pool else 0.0)
                + (3000.0 if self.has_sbc_cache else 0.0)
                + self.horse_score * 20.0
                + self.curr_pct * 30.0,
                2
            ),
        }


# =============================================================================
# 4. 超短线特异潜能挖掘与温度周期赛马核心引擎 (UltraShortAnomalyEngine)
# =============================================================================

class UltraShortAnomalyEngine:
    """
    ATS 超短线全底层异动特异挖掘、SBC分时缓存结构识别、赛马冒头捕获与温度周期去弱留强引擎 (单例 SSOT)
    """
    _instance: Optional['UltraShortAnomalyEngine'] = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> 'UltraShortAnomalyEngine':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.config = UltraShortConfig()
        self.temp_tracker = MarketTemperatureCycleTracker()
        self._items: Dict[str, UltraShortHorseItem] = {}
        self._sbc_hist_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._cached_report: Dict[str, Any] = {}
        self._cached_ts: float = 0.0
        self._today_str: str = time.strftime("%Y-%m-%d")
        self._fav_cache_set: Set[str] = set()
        self._fav_cache_ts: float = 0.0
        self._universe_sig: Any = None
        self._cached_clean_codes: Optional[np.ndarray] = None
        self._cached_valid_mask: Optional[np.ndarray] = None
        self._state_lock = threading.RLock()

    def reset_daily(self, today_str: Optional[str] = None):
        with self._state_lock:
            self._today_str = today_str or time.strftime("%Y-%m-%d")
            self._items.clear()
            self._sbc_hist_cache.clear()
            self._cached_report.clear()
            self._cached_ts = 0.0
            self.temp_tracker.reset_daily(self._today_str)

    def get_cached_report(self, max_age: float = 5.0, fallback_stale: bool = True) -> Dict[str, Any]:
        with self._state_lock:
            if self._cached_report:
                if (time.time() - self._cached_ts <= max_age) or fallback_stale:
                    return dict(self._cached_report)
            t_dict = self.temp_tracker.to_dict()
            return {
                "market_temp": t_dict["curr_temp"],
                "market_temp_info": t_dict,
                "temp_regime": t_dict["regime"],
                "temp_regime_label": t_dict["regime_label"],
                "temp_trend_summary": t_dict["trend_summary"],
                "candidates": [],
                "emerging_codes": [],
                "strong_codes": [],
                "overheat_exit_codes": [],
                "horse_emerge_count": 0,
                "keep_strong_count": 0,
                "overheat_cull_count": 0,
                "stats": {
                    "total_tracked": 0,
                    "focus_count": 0,
                    "emerging_count": 0,
                    "strong_count": 0,
                    "cull_exit_count": 0,
                },
                "elapsed_ms": 0.0,
            }

    def get_horse_item(self, code: str) -> Optional[Dict[str, Any]]:
        c_clean = _clean_code(code)
        with self._state_lock:
            item = self._items.get(c_clean)
            if item is not None:
                return item.to_dict(self.temp_tracker.curr_temp)
        return None

    def get_stock_item(self, code: str) -> Optional[UltraShortHorseItem]:
        """直接获取轻量状态槽实例 (__slots__, 零拷贝 O(1) 访问)"""
        c_clean = _clean_code(code)
        with self._state_lock:
            return self._items.get(c_clean)

    # -------------------------------------------------------------------------
    # 💥 [核心能力] 穿透读取 SBC 盯盘分时缓存 (TDXGlobalCachePool + SBCIndicatorCache)
    # 识别：【多日连续杀跌 + 阶段点小级别企稳异动 + 今天高开突破反转线加速结构】
    # -------------------------------------------------------------------------
    def _get_sbc_cached_codes(self) -> Set[str]:
        """获取当前已在 SBC 内存分时缓存池中驻留的盯盘代码集合 (零网络IO)"""
        codes: Set[str] = set()
        try:
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool
            pool = getattr(TDXGlobalCachePool, "_instance", None)
            if pool is not None:
                for k in list(getattr(pool, "_history_static_bars", {}).keys()):
                    codes.add(_clean_code(k))
                for k in list(getattr(pool, "_incremental_intraday_pool", {}).keys()):
                    if isinstance(k, tuple) and k:
                        codes.add(_clean_code(k[0]))
                for k in list(getattr(pool, "_daily_metrics_cache", {}).keys()):
                    codes.add(_clean_code(k))
        except Exception:
            pass
        return codes

    def _inspect_sbc_intraday_cache(self, code: str, today_str: str) -> Optional[Dict[str, Any]]:
        """
        从进程内 SBC 分时缓存 (TDXGlobalCachePool + SBCIndicatorCache) 提取多日分时结构：
        - 历史交易日按 (code, today_str) 缓存，单日仅聚合一次 (<0.05ms)，后续每 Tick 零开销复用！
        """
        c_clean = _clean_code(code)
        cache_key = (c_clean, today_str)
        cached_hist = self._sbc_hist_cache.get(cache_key)
        if cached_hist is not None and cached_hist.get("has_bars", False):
            return cached_hist

        sbc_supp = 0.0
        sbc_rev = 0.0
        sbc_vwap_5d = 0.0
        day_summaries: List[Dict[str, float]] = []

        # 1. 读取 SBCIndicatorCache 通道支撑/反转线
        try:
            from ats.ui.intraday_strategy_dialog import SBCIndicatorCache
            ind = SBCIndicatorCache.get(c_clean, "day")
            if ind:
                sbc_supp = _safe_float(ind.get("ch_supp", 0.0))
                sbc_rev = _safe_float(ind.get("rev", 0.0))
        except Exception:
            pass

        # 2. 读取 TDXGlobalCachePool 驻留内存的 SBC 多日分时与指标缓存 (绝不发起网络请求)
        try:
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool
            pool = getattr(TDXGlobalCachePool, "_instance", None)
            if pool is not None:
                dm_entry = getattr(pool, "_daily_metrics_cache", {}).get(c_clean)
                if isinstance(dm_entry, dict):
                    metrics = dm_entry.get("metrics", dm_entry)
                    if isinstance(metrics, dict):
                        if sbc_supp <= 0:
                            sbc_supp = _safe_float(metrics.get("ch_supp_price", metrics.get("ch_supp", 0.0)))
                        if sbc_rev <= 0:
                            sbc_rev = _safe_float(metrics.get("reversal_line", metrics.get("rev", 0.0)))

                recs = None
                hist_entry = getattr(pool, "_history_static_bars", {}).get(c_clean)
                if isinstance(hist_entry, dict) and hist_entry.get("records"):
                    recs = hist_entry["records"]
                else:
                    inc_pool = getattr(pool, "_incremental_intraday_pool", {})
                    for d_win in (10, 6, 5, 3, 2):
                        inc_entry = inc_pool.get((c_clean, d_win))
                        if isinstance(inc_entry, dict) and isinstance(inc_entry.get("df"), pd.DataFrame):
                            df_inc = inc_entry["df"]
                            if not df_inc.empty and "date" in df_inc.columns:
                                recs = df_inc[df_inc["date"].astype(str) < today_str].to_dict("records")
                                break

                if recs:
                    by_date: Dict[str, List[Dict[str, Any]]] = {}
                    for r in recs:
                        d_str = str(r.get("date", ""))[:10]
                        if d_str and d_str < today_str:
                            by_date.setdefault(d_str, []).append(r)

                    for d_str in sorted(by_date.keys()):
                        d_bars = by_date[d_str]
                        if not d_bars:
                            continue
                        closes_d = [_safe_float(b.get("close", b.get("price", 0.0))) for b in d_bars]
                        closes_d = [p for p in closes_d if p > 0]
                        if not closes_d:
                            continue
                        highs_d = [max(_safe_float(b.get("high", 0.0)), p) for b, p in zip(d_bars, closes_d)]
                        lows_d = [
                            _safe_float(b.get("low", 0.0)) if _safe_float(b.get("low", 0.0)) > 0 else p
                            for b, p in zip(d_bars, closes_d)
                        ]
                        n_b = len(closes_d)
                        mid_idx = max(1, n_b // 2)
                        am_low = min(lows_d[:mid_idx])
                        pm_low = min(lows_d[mid_idx:]) if n_b > mid_idx else am_low
                        pm_high = max(highs_d[mid_idx:]) if n_b > mid_idx else max(highs_d)
                        last_vwap = _safe_float(d_bars[-1].get("vwap", closes_d[-1]), closes_d[-1])
                        day_summaries.append({
                            "date": d_str,
                            "open": closes_d[0],
                            "high": max(highs_d),
                            "low": min(lows_d),
                            "close": closes_d[-1],
                            "am_low": am_low,
                            "pm_low": pm_low,
                            "pm_high": pm_high,
                            "vwap": last_vwap,
                        })
        except Exception:
            pass

        if not day_summaries and sbc_supp <= 0 and sbc_rev <= 0:
            return None

        info: Dict[str, Any] = {
            "has_bars": bool(len(day_summaries) >= 2),
            "sbc_supp": sbc_supp,
            "sbc_rev": sbc_rev,
            "sbc_vwap_5d": sbc_vwap_5d,
            "kill_days": 0,
            "cum_drop_pct": 0.0,
            "has_small_stabilize": False,
            "stabilize_desc": "",
            "prev_high": 0.0,
            "prev_low": 0.0,
            "prev_close": 0.0,
        }

        if len(day_summaries) >= 2:
            last_d = day_summaries[-1]
            prev_d = day_summaries[-2]
            sbc_vwap_5d = last_d["vwap"]
            info["sbc_vwap_5d"] = sbc_vwap_5d
            info["prev_high"] = last_d["high"]
            info["prev_low"] = last_d["low"]
            info["prev_close"] = last_d["close"]

            peak_high = max(d["high"] for d in day_summaries)
            stage_low = min(last_d["low"], prev_d["low"])
            cum_drop_pct = (peak_high - stage_low) / peak_high * 100.0 if peak_high > 0 else 0.0
            info["cum_drop_pct"] = round(cum_drop_pct, 2)

            kill_days = 0
            for i in range(1, len(day_summaries)):
                if (
                    day_summaries[i]["high"] <= day_summaries[i - 1]["high"] * 1.005
                    or day_summaries[i]["close"] <= day_summaries[i - 1]["close"] * 1.003
                ):
                    kill_days += 1
            info["kill_days"] = kill_days

            low_diff_pct = abs(last_d["low"] - prev_d["low"]) / max(0.01, prev_d["low"]) * 100.0
            multi_low_flat = (low_diff_pct <= 2.2) or (last_d["low"] >= prev_d["low"] * 0.995)
            intraday_hl = (last_d["pm_low"] >= last_d["am_low"] * 0.997)
            rebound_from_low = (last_d["close"] - last_d["low"]) / max(0.01, last_d["low"]) * 100.0
            pm_pulse_pct = (last_d["pm_high"] - last_d["low"]) / max(0.01, last_d["low"]) * 100.0

            if cum_drop_pct >= 4.2 and kill_days >= 1 and (multi_low_flat or intraday_hl) and (rebound_from_low >= 0.75 or pm_pulse_pct >= 1.5):
                info["has_small_stabilize"] = True
                if sbc_supp <= 0:
                    info["sbc_supp"] = round(stage_low, 2)
                if sbc_rev <= 0:
                    info["sbc_rev"] = round(max(last_d["high"], sbc_vwap_5d), 2)
                info["stabilize_desc"] = (
                    f"SBC分时连杀{kill_days}日(-{cum_drop_pct:.1f}%)至支撑{info['sbc_supp']:.2f}，"
                    f"小级别企稳({prev_d['low']:.2f}→{last_d['low']:.2f})拉回+{rebound_from_low:.1f}%"
                )

        if info["has_bars"]:
            self._sbc_hist_cache[cache_key] = info
        return info

    def _collect_focus_pool_codes(self, extra_focus_codes: Optional[Set[str]] = None) -> Set[str]:
        """汇聚 ATS 全模块重点关注个股池 (带 5s 内存 TTL 缓存，零阻塞)"""
        now = time.time()
        if now - self._fav_cache_ts > 5.0 or not self._fav_cache_set:
            fav_s: Set[str] = set()
            try:
                from global_favorites import GlobalFavoriteManager
                for c in (GlobalFavoriteManager().get_favorite_stocks() or []):
                    cc = _clean_code(c)
                    if cc:
                        fav_s.add(cc)
            except Exception:
                pass
            self._fav_cache_set = fav_s
            self._fav_cache_ts = now

        focus_set = set(self._fav_cache_set)
        if extra_focus_codes:
            for c in extra_focus_codes:
                cc = _clean_code(c)
                if cc:
                    focus_set.add(cc)
        focus_set.update(self._get_sbc_cached_codes())
        return focus_set

    def analyze_universe(
        self,
        df_all: Optional[pd.DataFrame],
        focus_codes: Optional[Set[str]] = None,
        mainline_sectors: Optional[Set[str]] = None,
        sh_pct: Optional[float] = None,
        force: bool = False,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        全底层数据向量化扫描与温度周期赛马去弱留强主入口 (纯内存零拷贝 < 5ms)
        """
        if df_all is None or df_all.empty:
            return self.get_cached_report(fallback_stale=True)

        now = now_ts if now_ts is not None else time.time()
        curr_day = time.strftime("%Y-%m-%d", time.localtime(now))
        if curr_day != self._today_str:
            self.reset_daily(curr_day)

        if not force and self._cached_report and (now - self._cached_ts < 0.8):
            return dict(self._cached_report)

        t0 = time.perf_counter()
        cfg = self.config

        try:
            focus_set = self._collect_focus_pool_codes(focus_codes)
            sbc_cached_set = self._get_sbc_cached_codes()

            n_rows = len(df_all)
            cols_set = set(df_all.columns)

            def _col_f64(candidates: Tuple[str, ...], default_val: float = 0.0) -> np.ndarray:
                for col in candidates:
                    if col in cols_set:
                        s = df_all[col]
                        kind = s.dtype.kind
                        if kind in "fc":
                            arr = s.to_numpy(dtype=np.float64, copy=False)
                            if np.isnan(arr).any() or np.isinf(arr).any():
                                return np.nan_to_num(arr, nan=default_val, posinf=default_val, neginf=default_val)
                            return arr
                        if kind in "iu":
                            return s.to_numpy(dtype=np.float64, copy=False)
                        return pd.to_numeric(s, errors="coerce").fillna(default_val).to_numpy(dtype=np.float64, copy=False)
                return np.full(n_rows, default_val, dtype=np.float64)

            closes = _col_f64(("close", "price", "trade", "now"), 0.0)
            opens = _col_f64(("open", "open_price"), 0.0)
            highs = _col_f64(("high", "high_price"), 0.0)
            lows = _col_f64(("low", "low_price"), 0.0)
            pcts = _col_f64(("percent", "pct", "ratio"), 0.0)
            vwaps = _col_f64(("nclose", "vwap", "avg_price"), 0.0)
            vrs = _col_f64(("vol_ratio", "vr", "volume_ratio"), 1.0)
            dffs = _col_f64(("dff", "DFF"), 0.0)
            dff3s = _col_f64(("dff3", "DFF3"), 0.0)

            lastp1d = _col_f64(("lastp1d", "lastp", "pre_close", "llastp", "last_close"), 0.0)
            lastp2d = _col_f64(("lastp2d",), 0.0)

            lasto1d = _col_f64(("lasto1d", "lopen"), 0.0)
            lasth1d = _col_f64(("lasth1d", "lhigh", "yesterday_high"), 0.0)
            lasth2d = _col_f64(("lasth2d",), 0.0)
            lasth3d = _col_f64(("lasth3d",), 0.0)
            lasth4d = _col_f64(("lasth4d",), 0.0)

            lastl1d = _col_f64(("lastl1d", "llow"), 0.0)
            lastl2d = _col_f64(("lastl2d",), 0.0)
            lastl3d = _col_f64(("lastl3d",), 0.0)

            lastv1d = _col_f64(("lastv1d", "lvol"), 0.0)
            lastv2d = _col_f64(("lastv2d",), 0.0)
            lastv3d = _col_f64(("lastv3d",), 0.0)
            lastv4d = _col_f64(("lastv4d",), 0.0)

            per1d = _col_f64(("per1d",), 0.0)
            per2d = _col_f64(("per2d",), 0.0)
            per3d = _col_f64(("per3d",), 0.0)
            per4d = _col_f64(("per4d",), 0.0)

            ch_pos = _col_f64(("ch_pos",), 50.0)
            ch_supp = _col_f64(("ch_supp_price", "ch_supp", "ch_lower"), 0.0)
            rev_line = _col_f64(("reversal_line", "rev"), 0.0)

            raw_amt = _col_f64(("amount", "turnover"), 0.0)
            max_amt = float(np.max(raw_amt)) if n_rows > 0 else 0.0
            if max_amt > 1e7:
                amts_yi = raw_amt * 1e-8
            elif max_amt > 1000.0:
                amts_yi = raw_amt * 1e-4
            else:
                amts_yi = raw_amt
            turnovers = _col_f64(("turnoverratio", "turnover_rate", "hsl", "ratio"), 0.0)

            # 代码与有效个股掩码（签名级缓存，避免每 Tick 5500 次字符串清洗）
            raw_codes = df_all["code"].to_numpy() if "code" in cols_set else df_all.index.to_numpy()
            names = df_all["name"].to_numpy() if "name" in cols_set else raw_codes
            sig = (n_rows, str(raw_codes[0]) if n_rows else "", str(raw_codes[-1]) if n_rows else "")
            if self._universe_sig == sig and self._cached_clean_codes is not None and self._cached_valid_mask is not None:
                clean_codes = self._cached_clean_codes
                valid_base_mask = self._cached_valid_mask
            else:
                clean_codes = np.array([_clean_code(c) for c in raw_codes], dtype=object)
                valid_base_mask = np.array([
                    not _is_index_or_etf(clean_codes[i], str(names[i]))
                    and "ST" not in str(names[i]).upper()
                    and "退" not in str(names[i])
                    for i in range(n_rows)
                ], dtype=bool)
                self._universe_sig = sig
                self._cached_clean_codes = clean_codes
                self._cached_valid_mask = valid_base_mask

            valid_stock_mask = valid_base_mask & (closes > 0.5)

            cat_col = next((c for c in ("category", "industry", "hy", "sector") if c in cols_set), None)
            sectors_arr = df_all[cat_col].to_numpy() if cat_col else None

            # 提取上证指数当日与昨日涨跌幅
            sh_pct_val = float(sh_pct) if sh_pct is not None else 0.0
            sh_prev_pct = 0.0
            if sh_pct is None:
                for idx_i in range(min(n_rows, 20)):
                    cc = clean_codes[idx_i]
                    if cc in ("999999", "000001") and (
                        str(raw_codes[idx_i]).startswith("sh") or "上证" in str(names[idx_i]) or cc == "999999"
                    ):
                        sh_pct_val = float(pcts[idx_i])
                        sh_prev_pct = float(per1d[idx_i])
                        break

            # 3. 更新市场温度周期追踪器 (从冷到热全周期感知)
            stock_pcts = pcts[valid_stock_mask]
            stock_per1d = per1d[valid_stock_mask]
            temp_info = self.temp_tracker.update_from_arrays(
                pcts=stock_pcts,
                per1d_arr=stock_per1d,
                sh_pct=sh_pct_val,
                sh_prev_pct=sh_prev_pct,
                now_ts=now,
                overheat_threshold=cfg.overheat_temp_threshold,
                cold_threshold=cfg.cold_temp_threshold,
            )
            curr_temp = self.temp_tracker.curr_temp
            mkt_med_1d = self.temp_tracker.prev_median_pct
            mkt_med_today = self.temp_tracker.median_pct

            # 4. 补齐缺失的历史派生基准 (零除保护)
            safe_lastp1d = np.where(lastp1d > 0.01, lastp1d, np.where(closes > 0.01, closes / (1.0 + pcts / 100.0), 1.0))
            safe_lastp2d = np.where(lastp2d > 0.01, lastp2d, safe_lastp1d / np.maximum(0.5, 1.0 + per1d / 100.0))
            safe_lasto1d = np.where(lasto1d > 0.01, lasto1d, safe_lastp2d)
            safe_lasth1d = np.where(lasth1d > 0.01, lasth1d, np.maximum(safe_lastp1d, safe_lasto1d))
            safe_lastl1d = np.where(lastl1d > 0.01, lastl1d, np.minimum(safe_lastp1d, safe_lasto1d))
            safe_vwap = np.where(vwaps > 0.01, vwaps, (opens + highs + lows + closes) * 0.25)
            safe_open = np.where(opens > 0.01, opens, safe_lastp1d)
            safe_high = np.where(highs > 0.01, highs, np.maximum(closes, safe_open))
            safe_low = np.where(lows > 0.01, lows, np.minimum(closes, safe_open))

            eff_per1d = np.where(
                np.abs(per1d) > 1e-4,
                per1d,
                (safe_lastp1d - safe_lastp2d) / np.maximum(0.01, safe_lastp2d) * 100.0,
            )

            # ── 向量化特征一：连续杀跌无像样反弹 & 阶段低点定位 ──────────────
            down_d2 = (per2d <= 0.45) | ((lasth2d > 0) & (lasth3d > 0) & (lasth2d <= lasth3d * 1.005))
            down_d3 = (per3d <= 0.45) | ((lasth3d > 0) & (lasth4d > 0) & (lasth3d <= lasth4d * 1.005))
            down_d4 = (per4d <= 0.45)
            down_days_prev = down_d2.astype(np.int32) + down_d3.astype(np.int32) + down_d4.astype(np.int32)

            multi_peak_h = np.maximum(
                safe_lasth1d,
                np.maximum(
                    np.where(lasth2d > 0.01, lasth2d, safe_lasth1d),
                    np.maximum(
                        np.where(lasth3d > 0.01, lasth3d, safe_lasth1d),
                        np.where(lasth4d > 0.01, lasth4d, safe_lasth1d),
                    ),
                ),
            )
            min_low_multi = np.minimum(
                safe_lastl1d,
                np.where(lastl2d > 0.01, lastl2d, safe_lastl1d),
            )
            min_low_multi = np.minimum(min_low_multi, np.where(lastl3d > 0.01, lastl3d, min_low_multi))
            multi_drop_pct = (multi_peak_h - min_low_multi) / np.maximum(0.01, multi_peak_h) * 100.0

            max_rebound_prev = np.maximum(per2d, np.maximum(per3d, per4d))
            no_strong_rebound = (max_rebound_prev <= 3.2)

            near_multi_low = (safe_lastl1d <= min_low_multi * 1.04)
            near_supp_or_rev = (
                ((ch_supp > 0.01) & (safe_lastl1d <= ch_supp * 1.05))
                | ((rev_line > 0.01) & (safe_lastl1d <= rev_line * 1.06))
                | (ch_pos <= 48.0)
                | (dff3s <= -3.5)
                | (multi_drop_pct >= 5.5)
            )
            is_stage_low_drop = (
                ((down_days_prev >= 2) & no_strong_rebound & (near_multi_low | near_supp_or_rev))
                | ((down_days_prev >= 1) & (multi_drop_pct >= 6.0) & near_multi_low)
                | ((down_days_prev >= 1) & (dff3s <= -7.5) & near_multi_low)
            )

            # ── 向量化特征二：昨日小幅温和放量异动倍数 (vol_ratio_1d) ─────────
            denom_v_cnt = (lastv2d > 0).astype(np.float64) + (lastv3d > 0).astype(np.float64) + (lastv4d > 0).astype(np.float64)
            mean_prev_vol = np.where(
                denom_v_cnt > 0,
                (np.maximum(0.0, lastv2d) + np.maximum(0.0, lastv3d) + np.maximum(0.0, lastv4d)) / np.maximum(1.0, denom_v_cnt),
                lastv1d,
            )
            vol_ratio_1d = np.where((lastv1d > 0) & (mean_prev_vol > 0), lastv1d / mean_prev_vol, 1.0)
            vol_ratio_1d = np.clip(vol_ratio_1d, 0.2, 10.0)
            is_mild_vol_1d = (vol_ratio_1d >= cfg.min_mild_vol_ratio_1d) & (vol_ratio_1d <= cfg.max_mild_vol_ratio_1d)

            # ── 向量化特征三：SBC 连续杀跌小级别企稳异动 & 阶段点特异结构 ──────
            range_1d = np.maximum(0.01, safe_lasth1d - safe_lastl1d)
            body_low_1d = np.minimum(safe_lasto1d, safe_lastp1d)
            lower_shadow_ratio = (body_low_1d - safe_lastl1d) / range_1d
            upper_shadow_ratio = (safe_lasth1d - np.maximum(safe_lasto1d, safe_lastp1d)) / range_1d
            close_pos_1d = (safe_lastp1d - safe_lastl1d) / range_1d
            kill_from_open_pct = (safe_lasto1d - safe_lastl1d) / np.maximum(0.01, safe_lasto1d) * 100.0
            rebound_from_low_1d_pct = (safe_lastp1d - safe_lastl1d) / np.maximum(0.01, safe_lastl1d) * 100.0
            spike_from_prev_pct = (safe_lasth1d - safe_lastp2d) / np.maximum(0.01, safe_lastp2d) * 100.0

            prev_low_ref = np.where(lastl2d > 0.01, lastl2d, safe_lastl1d)
            small_platform_hold = (np.abs(safe_lastl1d - prev_low_ref) / np.maximum(0.01, prev_low_ref) <= 0.025) | (
                safe_lastl1d >= prev_low_ref * 0.992
            )
            open_pct_today = (safe_open - safe_lastp1d) / np.maximum(0.01, safe_lastp1d) * 100.0
            eff_rev_ref = np.where(rev_line > 0.01, rev_line, safe_lasth1d)

            # 形态 S：【📈 SBC连续杀跌 + 小级别企稳异动 + 今天高开/突破反转线加速结构】
            struct_sbc_mask = (
                is_stage_low_drop
                & ((multi_drop_pct >= 5.0) | (down_days_prev >= 2))
                & small_platform_hold
                & ((rebound_from_low_1d_pct >= 1.2) | ((eff_per1d >= 0.1) & (vol_ratio_1d >= 1.05)))
                & (open_pct_today >= -0.35)
                & (safe_low >= safe_lastl1d * 0.998)
                & ((closes >= eff_rev_ref * 0.995) | (pcts >= 2.8))
            )

            # 形态 A：【阶段点高开杀跌 -> 探底深V承接 -> 反弹收红】
            struct_a_mask = (
                is_stage_low_drop
                & (safe_lasto1d >= safe_lastp2d * 0.992)
                & (kill_from_open_pct >= 1.2)
                & ((safe_lastp1d >= safe_lasto1d * 0.996) | (eff_per1d >= 0.0))
                & ((lower_shadow_ratio >= 0.30) | (close_pos_1d >= 0.50))
            )

            # 形态 B：【阶段点异动冲高回落 + 小幅放量试盘】
            struct_b_mask = (
                is_stage_low_drop
                & (spike_from_prev_pct >= 1.8)
                & (upper_shadow_ratio >= 0.22)
                & (safe_lastp1d >= safe_lastl1d * 1.006)
                & (eff_per1d >= -1.8)
                & (is_mild_vol_1d | (vol_ratio_1d >= 1.02))
            )

            bench_1d = min(sh_prev_pct, mkt_med_1d)
            bench_today = min(sh_pct_val, mkt_med_today)
            alpha_1d_arr = eff_per1d - bench_1d
            alpha_today_arr = pcts - bench_today

            is_focus_arr = np.isin(clean_codes, list(focus_set)) if focus_set else np.zeros(n_rows, dtype=bool)
            is_sbc_cached_arr = np.isin(clean_codes, list(sbc_cached_set)) if sbc_cached_set else np.zeros(n_rows, dtype=bool)

            # 形态 C：【阶段低点逆势特异抗跌】
            struct_c_mask = (
                is_stage_low_drop
                & ~struct_sbc_mask
                & ~struct_a_mask
                & ~struct_b_mask
                & (alpha_1d_arr >= cfg.min_idiosyncratic_alpha_1d)
                & (eff_per1d >= 0.0)
                & (vol_ratio_1d >= 1.02)
            )

            # 形态 D：【重点关注池 (★) / SBC 盯盘池冷盘逆势异动种子】
            struct_d_mask = (
                (is_focus_arr | is_sbc_cached_arr)
                & ~struct_sbc_mask
                & ~struct_a_mask
                & ~struct_b_mask
                & ~struct_c_mask
                & ((alpha_today_arr >= 2.0) | (pcts >= 2.5) | is_sbc_cached_arr)
            )

            candidate_mask = valid_stock_mask & (
                struct_sbc_mask | struct_a_mask | struct_b_mask | struct_c_mask | struct_d_mask
            )

            with self._state_lock:
                existing_tracked = set(self._items.keys())
            if existing_tracked:
                tracked_mask = np.isin(clean_codes, list(existing_tracked))
                candidate_mask = candidate_mask | (valid_stock_mask & tracked_mask)

            cand_indices = np.flatnonzero(candidate_mask)
            # 若候选超过 120 只，优先保留重点池、已跟踪池及涨幅前列 Top 120，保障极端情况 < 5ms
            if len(cand_indices) > 120:
                prio_key = (
                    is_focus_arr[cand_indices].astype(np.float64) * 1000.0
                    + is_sbc_cached_arr[cand_indices].astype(np.float64) * 800.0
                    + pcts[cand_indices]
                )
                top_order = np.argsort(prio_key)[::-1][:120]
                cand_indices = cand_indices[top_order]

            bubble_engine = None
            try:
                from ats.opening_bubble_engine import get_opening_bubble_engine
                bubble_engine = get_opening_bubble_engine()
            except Exception:
                pass

            now_hhmm = time.strftime("%H:%M", time.localtime(now))
            results_list: List[Dict[str, Any]] = []
            emerging_codes: List[str] = []
            strong_codes: List[str] = []
            overheat_exit_codes: List[str] = []

            with self._state_lock:
                for idx in cand_indices:
                    c_clean = str(clean_codes[idx])
                    name_str = str(names[idx]).strip()
                    p_curr = float(closes[idx])
                    p_open = float(safe_open[idx])
                    p_high = float(safe_high[idx])
                    p_low = float(safe_low[idx])
                    p_last1 = float(safe_lastp1d[idx])
                    pct_curr = float(pcts[idx])
                    vwap_curr = float(safe_vwap[idx])
                    vr_curr = max(float(vrs[idx]), 0.1)
                    amt_yi = float(amts_yi[idx])
                    turn_pct = float(turnovers[idx])
                    dff_val = float(dffs[idx])
                    is_focus = bool(is_focus_arr[idx])

                    sbc_info = self._inspect_sbc_intraday_cache(c_clean, curr_day)
                    has_sbc_stabilize = bool(sbc_info and sbc_info.get("has_small_stabilize", False))

                    h1 = float(safe_lasth1d[idx])
                    if sbc_info and sbc_info.get("prev_high", 0.0) > 0.01:
                        h1 = max(h1, float(sbc_info["prev_high"]))
                    sbc_rev_p = float(rev_line[idx]) if rev_line[idx] > 0.01 else 0.0
                    if sbc_info and sbc_info.get("sbc_rev", 0.0) > 0.01:
                        sbc_rev_p = float(sbc_info["sbc_rev"])

                    sbc_supp_p = float(ch_supp[idx]) if ch_supp[idx] > 0.01 else 0.0
                    if sbc_info and sbc_info.get("sbc_supp", 0.0) > 0.01:
                        sbc_supp_p = float(sbc_info["sbc_supp"])

                    neck_p = sbc_rev_p if sbc_rev_p > 0.01 else (h1 if h1 > 0.01 else p_last1 * 1.02)
                    stage_low_p = float(min_low_multi[idx]) if min_low_multi[idx] > 0.01 else float(safe_lastl1d[idx])
                    if sbc_supp_p > 0.01:
                        stage_low_p = min(stage_low_p, sbc_supp_p)

                    item = self._items.get(c_clean)
                    is_new_item = False
                    if item is None:
                        item = UltraShortHorseItem(c_clean, name_str)
                        self._items[c_clean] = item
                        is_new_item = True

                    item.name = name_str
                    item.is_focus_pool = is_focus or item.is_focus_pool
                    item.has_sbc_cache = bool(sbc_info is not None)
                    item.sbc_supp_price = sbc_supp_p if sbc_supp_p > 0 else stage_low_p
                    item.sbc_rev_price = sbc_rev_p if sbc_rev_p > 0 else neck_p
                    item.sbc_vwap_5d = float(sbc_info.get("sbc_vwap_5d", 0.0)) if sbc_info else 0.0
                    item.sbc_drop_pct = (
                        float(sbc_info.get("cum_drop_pct", 0.0))
                        if (sbc_info and sbc_info.get("cum_drop_pct", 0.0) > 0)
                        else float(multi_drop_pct[idx])
                    )

                    if sectors_arr is not None:
                        sec_raw = str(sectors_arr[idx]).strip()
                        if sec_raw and sec_raw not in ("nan", "None", "--", ""):
                            item.sector = sec_raw.split(";")[0].split(",")[0].strip() or "主流活跃"

                    kill_d = max(
                        int(down_days_prev[idx]),
                        int(sbc_info.get("kill_days", 0)) if sbc_info else 0,
                    )
                    item.down_days_count = max(item.down_days_count, kill_d)
                    item.stage_low_price = stage_low_p
                    item.neck_price = neck_p
                    item.vol_ratio_1d = float(vol_ratio_1d[idx])
                    item.alpha_1d = float(alpha_1d_arr[idx])
                    item.alpha_today = float(alpha_today_arr[idx])

                    is_sbc_pattern = bool(struct_sbc_mask[idx] or has_sbc_stabilize)

                    if is_sbc_pattern:
                        item.structure_type = STRUCT_SBC_KILL_STABILIZE_ACCEL
                        item.structure_label = STRUCT_LABELS[STRUCT_SBC_KILL_STABILIZE_ACCEL]
                        if sbc_info and sbc_info.get("stabilize_desc"):
                            item.structure_desc = (
                                f"{sbc_info['stabilize_desc']} | 反转线{item.sbc_rev_price:.2f}"
                                f"(昨量比{item.vol_ratio_1d:.2f}x, 昨超额{item.alpha_1d:+.1f}%)"
                            )
                        else:
                            item.structure_desc = (
                                f"连续杀跌{max(2, item.down_days_count)}日(-{item.sbc_drop_pct:.1f}%)至支撑({stage_low_p:.2f})，"
                                f"小级别企稳拉回+{rebound_from_low_1d_pct[idx]:.1f}%，反转线{item.sbc_rev_price:.2f}"
                            )
                    elif struct_a_mask[idx]:
                        item.structure_type = STRUCT_HIGH_OPEN_KILL_REBOUND
                        item.structure_label = STRUCT_LABELS[STRUCT_HIGH_OPEN_KILL_REBOUND]
                        item.structure_desc = (
                            f"连跌{item.down_days_count}日无反弹至阶段点({stage_low_p:.2f})，"
                            f"昨高开急杀-{kill_from_open_pct[idx]:.1f}%后深V承接反弹收红"
                            f"(昨量比{item.vol_ratio_1d:.2f}x, 超额{item.alpha_1d:+.1f}%)"
                        )
                    elif struct_b_mask[idx]:
                        item.structure_type = STRUCT_SPIKE_PULLBACK_MILD_VOL
                        item.structure_label = STRUCT_LABELS[STRUCT_SPIKE_PULLBACK_MILD_VOL]
                        item.structure_desc = (
                            f"连跌{item.down_days_count}日阶段低点，昨逆势冲高+{spike_from_prev_pct[idx]:.1f}%回落试盘，"
                            f"小幅放量{item.vol_ratio_1d:.2f}x守稳支撑(超额{item.alpha_1d:+.1f}%)"
                        )
                    elif struct_c_mask[idx]:
                        item.structure_type = STRUCT_STAGE_IDIOSYNCRATIC
                        item.structure_label = STRUCT_LABELS[STRUCT_STAGE_IDIOSYNCRATIC]
                        item.structure_desc = (
                            f"阶段点({stage_low_p:.2f})逆大盘抗跌收红，昨超额{item.alpha_1d:+.1f}%，量比{item.vol_ratio_1d:.2f}x"
                        )
                    elif not item.structure_type:
                        item.structure_type = STRUCT_FOCUS_COLD_SPARK
                        item.structure_label = STRUCT_LABELS[STRUCT_FOCUS_COLD_SPARK]
                        item.structure_desc = f"重点关注池标的，今日逆大盘超额{item.alpha_today:+.1f}%放量异动"

                    if is_new_item or item.entry_ts <= 0:
                        item.entry_ts = now
                        item.entry_time_str = now_hhmm
                        item.entry_price = p_curr
                        item.entry_pct = pct_curr
                        is_yesterday_cold_base = item.structure_type in (
                            STRUCT_SBC_KILL_STABILIZE_ACCEL,
                            STRUCT_HIGH_OPEN_KILL_REBOUND,
                            STRUCT_SPIKE_PULLBACK_MILD_VOL,
                            STRUCT_STAGE_IDIOSYNCRATIC,
                        )
                        if is_yesterday_cold_base and self.temp_tracker.prev_day_temp < 52.0:
                            item.entry_temp = min(curr_temp, self.temp_tracker.prev_day_temp)
                            item.was_cold_anomaly = True
                        else:
                            item.entry_temp = curr_temp
                            item.was_cold_anomaly = bool(
                                curr_temp <= cfg.cold_temp_threshold or is_yesterday_cold_base
                            )

                    item.curr_price = p_curr
                    item.curr_pct = pct_curr
                    item.open_pct = (p_open - p_last1) / p_last1 * 100.0 if p_last1 > 0.01 else 0.0
                    item.high_pct = (p_high - p_last1) / p_last1 * 100.0 if p_last1 > 0.01 else pct_curr
                    item.low_pct = (p_low - p_last1) / p_last1 * 100.0 if p_last1 > 0.01 else pct_curr
                    item.vwap = vwap_curr
                    item.vol_ratio = vr_curr
                    item.amount_yi = amt_yi
                    item.turnover_pct = turn_pct
                    item.dff_speed = dff_val
                    item.updated_ts = now

                    if bubble_engine is not None:
                        b_state = bubble_engine._states.get(c_clean)
                        if b_state is not None:
                            item.tier_jumps = int(getattr(b_state, "tier_jumps", 0))

                    item.neck_break_pct = (p_curr - neck_p) / neck_p * 100.0 if neck_p > 0.01 else 0.0
                    open_low_dip_pct = (p_open - p_low) / p_open * 100.0 if p_open > 0.01 else 0.0
                    item.is_gap_open_low = bool(
                        (item.open_pct >= 0.35 or p_open >= neck_p * 0.992) and (open_low_dip_pct <= 0.75)
                    )
                    item.is_above_vwap = bool(p_curr >= vwap_curr * 0.997)

                    accel_thresh = cfg.accel_20cm_board_pct if item.is_20cm_board else cfg.accel_main_board_pct
                    drawdown_from_high = item.high_pct - item.curr_pct

                    is_sbc_high_open_accel = bool(
                        is_sbc_pattern
                        and item.open_pct >= 0.0
                        and item.neck_break_pct >= 0.5
                        and item.curr_pct >= 3.8
                        and item.vol_ratio >= 1.35
                        and item.is_above_vwap
                        and drawdown_from_high <= 1.8
                    )
                    is_now_accelerated = bool(
                        is_sbc_high_open_accel
                        or (item.curr_pct >= accel_thresh and drawdown_from_high <= 1.8 and item.is_above_vwap)
                        or (item.curr_pct >= 9.5 and drawdown_from_high <= 0.5)
                        or (
                            item.is_gap_open_low
                            and item.neck_break_pct >= 1.5
                            and item.curr_pct >= 4.2
                            and item.vol_ratio >= 1.6
                            and item.is_above_vwap
                        )
                    )
                    if is_now_accelerated:
                        item.is_accelerated = True

                    is_emerging_now = bool(
                        item.curr_pct >= cfg.emerging_min_pct
                        and item.vol_ratio >= cfg.emerging_min_vol_ratio
                        and item.is_above_vwap
                        and (item.neck_break_pct >= -0.4 or item.tier_jumps >= 1 or item.dff_speed >= 0.6)
                        and item.alpha_today >= 1.0
                        and drawdown_from_high <= 2.2
                    )
                    if (is_emerging_now or is_now_accelerated) and item.first_emerge_ts <= 0:
                        item.first_emerge_ts = now
                        item.first_emerge_time_str = now_hhmm

                    temp_rise = curr_temp - item.entry_temp
                    gain_from_entry = (p_curr - item.entry_price) / item.entry_price * 100.0 if item.entry_price > 0.01 else 0.0
                    broken_stage_low = bool(p_curr < float(safe_lastl1d[idx]) * 0.992)
                    severe_high_drop = bool(
                        item.high_pct >= 2.5
                        and drawdown_from_high >= cfg.max_pullback_from_high_pct
                        and not item.is_above_vwap
                    )

                    is_overheat_env = bool(
                        curr_temp >= cfg.overheat_temp_threshold
                        or (curr_temp >= 56.0 and temp_rise >= cfg.temp_rise_cull_delta)
                    )
                    is_stagnant_in_overheat = bool(
                        item.was_cold_anomaly
                        and is_overheat_env
                        and not is_now_accelerated
                        and (
                            item.curr_pct < cfg.overheat_stagnant_max_pct
                            or not item.is_above_vwap
                            or item.neck_break_pct < -0.5
                            or (gain_from_entry < cfg.overheat_min_gain_from_entry and item.dff_speed <= 0.2)
                        )
                    )

                    if is_now_accelerated:
                        item.stop_loss_price = max(vwap_curr * 0.992, neck_p * 0.99)
                    else:
                        item.stop_loss_price = max(stage_low_p, min(p_low, vwap_curr * 0.985))

                    if is_sbc_pattern:
                        base_struct_score = 35.0
                    elif struct_a_mask[idx]:
                        base_struct_score = 32.0
                    elif struct_b_mask[idx]:
                        base_struct_score = 30.0
                    else:
                        base_struct_score = 22.0
                    focus_bonus = (10.0 if item.is_focus_pool else 0.0) + (4.0 if item.has_sbc_cache else 0.0)
                    emerge_score = min(
                        30.0,
                        max(0.0, item.curr_pct * 2.2)
                        + (8.0 if item.neck_break_pct >= 0 else 0.0)
                        + (6.0 if item.is_gap_open_low else 0.0),
                    )
                    vol_vwap_score = min(
                        16.0,
                        max(0.0, (item.vol_ratio - 1.0) * 4.5) + (6.0 if item.is_above_vwap else -10.0),
                    )
                    alpha_score = min(12.0, max(0.0, item.alpha_1d * 1.2 + item.alpha_today * 1.0))
                    raw_score = base_struct_score + focus_bonus + emerge_score + vol_vwap_score + alpha_score

                    if broken_stage_low:
                        item.race_state = RACE_STATE_WEAK_BROKEN_EXIT
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_WEAK_BROKEN_EXIT]
                        item.horse_score = max(10.0, min(45.0, raw_score - 35.0))
                        item.decision_reason = (
                            f"⛔ [结构破位去弱] 跌破小级别企稳低点({safe_lastl1d[idx]:.2f})，"
                            f"逆势承接逻辑失效，果断淘汰出局"
                        )
                        item.target_desc = "立即出局/剔除关注"
                        overheat_exit_codes.append(c_clean)

                    elif is_stagnant_in_overheat:
                        item.race_state = RACE_STATE_OVERHEAT_EXIT
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_OVERHEAT_EXIT]
                        item.horse_score = max(20.0, min(55.0, raw_score - 25.0))
                        stagnant_detail = (
                            f"受阻反转/颈线({neck_p:.2f})" if item.neck_break_pct < 0
                            else (f"跌破VWAP({vwap_curr:.2f})" if not item.is_above_vwap else f"涨幅仅{item.curr_pct:+.2f}%未加速")
                        )
                        item.decision_reason = (
                            f"⚠️ [过热未加速·出局] 冷盘异动跟单({item.entry_temp:.0f}℃)→当前市场温度已达"
                            f"{curr_temp:.1f}℃(上涨{self.temp_tracker.up_count}家过热)，该股{stagnant_detail}，"
                            f"主力无拉升意愿，防退潮补跌主动出局 | {item.structure_desc}"
                        )
                        item.target_desc = "逢高主动出局(去弱换强)"
                        overheat_exit_codes.append(c_clean)

                    elif severe_high_drop:
                        item.race_state = RACE_STATE_WEAK_BROKEN_EXIT
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_WEAK_BROKEN_EXIT]
                        item.horse_score = max(10.0, min(45.0, raw_score - 35.0))
                        item.decision_reason = (
                            f"⛔ [冲高回落去弱] 日内摸高+{item.high_pct:.1f}%后回落{drawdown_from_high:.1f}%且跌破VWAP({vwap_curr:.2f})，"
                            f"伪强诱多，去弱淘汰"
                        )
                        item.target_desc = "立即出局/剔除关注"
                        overheat_exit_codes.append(c_clean)

                    elif is_now_accelerated:
                        item.race_state = RACE_STATE_STRONG_LOCKED
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_STRONG_LOCKED]
                        item.horse_score = min(99.5, max(82.0, raw_score + 10.0))
                        if is_sbc_high_open_accel:
                            accel_tag = f"连杀小企稳后今高开({item.open_pct:+.1f}%)破反转线({neck_p:.2f})加速"
                        elif item.is_gap_open_low:
                            accel_tag = f"跳空光脚突破反转/颈线({neck_p:.2f})加速"
                        else:
                            accel_tag = f"放量{item.vol_ratio:.1f}x突破反转/颈线({neck_p:.2f})主升加速"
                        item.decision_reason = (
                            f"👑 [去弱留强·特异加速] 温度{item.entry_temp:.0f}℃→{curr_temp:.1f}℃共振，{accel_tag}，"
                            f"稳居VWAP({vwap_curr:.2f})之上 | 底座: {item.structure_desc}"
                        )
                        item.target_desc = f"留强锁仓/冲板 (防守位 {item.stop_loss_price:.2f})"
                        strong_codes.append(c_clean)

                    elif is_emerging_now:
                        item.race_state = RACE_STATE_HORSE_EMERGING
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_HORSE_EMERGING]
                        item.horse_score = min(95.0, max(72.0, raw_score + 5.0))
                        neck_str = (
                            f"突破反转/颈线{neck_p:.2f}(+{item.neck_break_pct:.1f}%)"
                            if item.neck_break_pct >= 0
                            else f"冲击反转/颈线{neck_p:.2f}"
                        )
                        item.decision_reason = (
                            f"🏇 [赛马突然冒头] {'★重点池 ' if item.is_focus_pool else ''}{neck_str}，"
                            f"量比{item.vol_ratio:.2f}x点火站稳VWAP({vwap_curr:.2f})，超额{item.alpha_today:+.1f}% | "
                            f"底座: {item.structure_desc}"
                        )
                        item.target_desc = f"赛马跟单狙击 (突破{neck_p:.2f}加仓 / 止损{item.stop_loss_price:.2f})"
                        emerging_codes.append(c_clean)

                    else:
                        item.race_state = RACE_STATE_COLD_SEED_WATCH
                        item.race_state_label = RACE_STATE_LABELS[RACE_STATE_COLD_SEED_WATCH]
                        item.horse_score = min(78.0, max(45.0, raw_score))
                        item.decision_reason = (
                            f"🌱 [阶段特异种子] {item.structure_desc} | "
                            f"今日待放量突破反转/颈线({neck_p:.2f})触发赛马冒头 (现距反转线{item.neck_break_pct:+.1f}%)"
                        )
                        item.target_desc = f"盯紧反转线 {neck_p:.2f} 点火突破"

                    results_list.append(item.to_dict(curr_temp))

            results_list.sort(key=lambda x: x["sort_priority"], reverse=True)

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            focus_cnt = sum(1 for r in results_list if r["is_focus_pool"])
            report = {
                "market_temp": curr_temp,
                "market_temp_info": temp_info,
                "temp_regime": self.temp_tracker.regime,
                "temp_regime_label": self.temp_tracker.regime_label,
                "temp_trend_summary": self.temp_tracker.get_trend_arrow_text(),
                "candidates": results_list,
                "emerging_codes": emerging_codes,
                "strong_codes": strong_codes,
                "overheat_exit_codes": overheat_exit_codes,
                "horse_emerge_count": len(emerging_codes),
                "keep_strong_count": len(strong_codes),
                "overheat_cull_count": len(overheat_exit_codes),
                "stats": {
                    "total_tracked": len(results_list),
                    "focus_count": focus_cnt,
                    "emerging_count": len(emerging_codes),
                    "strong_count": len(strong_codes),
                    "cull_exit_count": len(overheat_exit_codes),
                },
                "elapsed_ms": round(elapsed_ms, 2),
            }
            with self._state_lock:
                self._cached_report = report
                self._cached_ts = now
            return report

        except Exception as exc:
            logger.error(f"[UltraShortAnomalyEngine] analyze_universe error: {exc}", exc_info=True)
            return self.get_cached_report(fallback_stale=True)

    def analyze_as_dataframe(
        self,
        df_all: Optional[pd.DataFrame],
        focus_codes: Optional[Set[str]] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        """
        符合全局工程规范的 DataFrame 接口返回：
        - 成功：返回包含赛马排名与去弱留强决策的 pd.DataFrame，并在 attrs['market_temp'] 附带市场温度周期字典；
        - 失败：返回空 pd.DataFrame 并设置 df.attrs['__error__']，绝不抛出异常中断主循环。
        """
        try:
            if df_all is None or df_all.empty:
                empty_df = pd.DataFrame()
                empty_df.attrs["__error__"] = {
                    "code": "EMPTY_INPUT_FRAME",
                    "exc_type": "ValueError",
                    "exc_msg": "df_all is None or empty",
                }
                return empty_df
            report = self.analyze_universe(df_all=df_all, focus_codes=focus_codes, force=force)
            cands = report.get("candidates", [])
            out_df = pd.DataFrame(cands) if cands else pd.DataFrame()
            out_df.attrs["market_temp"] = report.get("market_temp_info", {})
            out_df.attrs["stats"] = report.get("stats", {})
            return out_df
        except Exception as exc:
            err_df = pd.DataFrame()
            err_df.attrs["__error__"] = {
                "code": "ULTRA_SHORT_ENGINE_ERROR",
                "exc_type": type(exc).__name__,
                "exc_msg": str(exc),
            }
            return err_df


def get_ultra_short_anomaly_engine() -> UltraShortAnomalyEngine:
    return UltraShortAnomalyEngine.get_instance()

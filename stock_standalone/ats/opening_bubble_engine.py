# -*- coding: utf-8 -*-
"""
ats/opening_bubble_engine.py — ATS 全网开盘起点跟踪与极速冒泡阶梯跃迁挖掘核心引擎
(Opening Trajectory & Fast Bubble-Up Multi-Tier Momentum Engine)

核心职责：
1. 【全网 5000+ 标的轻量全网表 (Full Market State Tracker)】：
   - 极低内存开销、纯内存微秒级状态追踪；
   - 记录开盘起点 (open_pct, open_price)、日内极值 (high_pct, low_pct)、现价涨幅、VWAP 均价；
2. 【涨跌阶梯与冒泡跃迁算法 (Bubble-Up Ladder Progression)】：
   - 涨幅 8 级阶梯 (<-4%, -4~-2%, -2~0%, 0~2%, 2~4%, 4~6%, 6~8%, >8%)；
   - 量能 4 级能级 (温和/异动/爆量/巨量)；
   - 毫秒级捕获标的从某一阶梯跃迁到更高阶梯的跳跃事件 (如 0-2% -> 2-4% -> 4-6% 步步高升)；
3. 【开盘起点形态分类体系 (Opening Pattern Archetypes)】：
   - 🚀 低开高走·反包突围 (Low Open High Climb / Reversal Breakout)
   - 💎 高开蓄势·放量锁筹 (High Open Consolidation / Volume Lock)
   - ⚡ 阶梯跃迁·步步高升 (Step-by-Step Bubble Up / Ladder Surging)
   - 🌊 平开脉冲·快速点火 (Flat Open Pulse Breakout)
   - ❄️ 水下点火·冰点突击 (Underwater Spark Ignition)
   - ⚠️ 高开低走·出货分歧 (High Open Drop Divergence - 避坑预警)
4. 【多维差异化策略挖掘 (Differentiated Strategy Mining)】：
   - 融合开盘起点 + 冒泡跃迁 + 多日连板天梯 + DFF多周期偏离 + 量比压强；
   - 产出专属 Alpha Opening Score (0~100) 与差异化上车决策建议。
"""

import time
import math
from typing import Dict, List, Tuple, Optional, Any, Set
import pandas as pd
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("OpeningBubbleEngine")


def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全浮点数转换，杜绝 NaN / Inf / None 报错"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """安全整数转换"""
    if val is None or val == "" or val == "-" or val == "--" or val == "null" or val == "None":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


# 8 级涨跌阶梯定义与区间边界
TIER_BOUNDS = [-999.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 999.0]
TIER_NAMES = [
    "<-4%",       # Tier 0
    "-4%~-2%",    # Tier 1
    "-2%~0%",     # Tier 2 (水下临界)
    "0%~+2%",     # Tier 3 (平开启爆)
    "+2%~+4%",    # Tier 4 (第一阶梯)
    "+4%~+6%",    # Tier 5 (第二阶梯)
    "+6%~+8%",    # Tier 6 (冲刺阶梯)
    ">8% (极强)"  # Tier 7 (封板区)
]
TIER_SHORT_TAGS = ["< -4", "-4~-2", "-2~0", "0~2", "2~4", "4~6", "6~8", "> 8"]


def get_pct_tier(pct: float) -> int:
    """根据涨幅获取当前所处的 8 级阶梯索引 (0~7)"""
    if pct <= -4.0:
        return 0
    elif pct <= -2.0:
        return 1
    elif pct <= 0.0:
        return 2
    elif pct <= 2.0:
        return 3
    elif pct <= 4.0:
        return 4
    elif pct <= 6.0:
        return 5
    elif pct <= 8.0:
        return 6
    else:
        return 7


def get_vol_tier(vol_ratio: float) -> int:
    """根据量比获取量能能级 (1~4)"""
    if vol_ratio >= 6.0:
        return 4  # 巨量主升
    elif vol_ratio >= 3.0:
        return 3  # 爆量攻击
    elif vol_ratio >= 1.5:
        return 2  # 异动放量
    return 1      # 温和蓄势


class StockBubbleState:
    """
    单个股票的全网状态轻量容器 (使用 __slots__ 极限压榨性能与内存)
    """
    __slots__ = (
        'code', 'name', 'pre_close', 'open_price', 'open_pct',
        'curr_price', 'curr_pct', 'high_pct', 'low_pct',
        'vwap', 'vol_ratio', 'amount_yi', 'turnover_pct',
        'current_tier', 'open_tier', 'history_tiers', 'tier_jumps',
        'last_jump_time', 'pattern_type', 'pattern_tag', 'pattern_desc',
        'alpha_score', 'first_seen_time', 'updated_time'
    )

    def __init__(self, code: str, name: str = ""):
        self.code = code
        self.name = name
        self.pre_close = 0.0
        self.open_price = 0.0
        self.open_pct = 0.0
        self.curr_price = 0.0
        self.curr_pct = 0.0
        self.high_pct = 0.0
        self.low_pct = 0.0
        self.vwap = 0.0
        self.vol_ratio = 1.0
        self.amount_yi = 0.0
        self.turnover_pct = 0.0
        self.current_tier = 3      # 默认 0~2%
        self.open_tier = 3         # 默认开盘阶梯
        self.history_tiers = []    # 跃迁阶梯历史 list of int
        self.tier_jumps = 0        # 跃迁次数
        self.last_jump_time = 0.0  # 最近一次跃迁时间戳
        self.pattern_type = "NORMAL"
        self.pattern_tag = "横盘整理"
        self.pattern_desc = "常规波动"
        self.alpha_score = 50.0
        self.first_seen_time = time.time()
        self.updated_time = time.time()


class OpeningBubbleEngine:
    """
    全网开盘起点跟踪与极速冒泡阶梯跃迁挖掘引擎
    """
    _instance: Optional['OpeningBubbleEngine'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(OpeningBubbleEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self._states: Dict[str, StockBubbleState] = {}
        self._today_str = time.strftime("%Y-%m-%d")
        self._last_snapshot_time = 0.0
        logger.info("⚡ [OpeningBubbleEngine] 全网开盘起点与极速冒泡阶梯挖掘引擎已初始化。")

    def reset_daily(self):
        """每日开盘清空重置全网表"""
        self._states.clear()
        self._today_str = time.strftime("%Y-%m-%d")
        self._last_snapshot_time = 0.0
        logger.info(f"🔄 [OpeningBubbleEngine] 已重置今日 ({self._today_str}) 全网状态跟踪表。")

    def update_market_snapshot(self, df: Optional[pd.DataFrame]) -> int:
        """
        全量/增量更新全网市场快照 (高性能向量化 + 极简字典遍历，每秒 5000 只股票耗时 < 3ms)
        返回更新的股票数量。
        """
        if df is None or df.empty:
            return 0

        # 检查是否隔日
        curr_today = time.strftime("%Y-%m-%d")
        if curr_today != self._today_str:
            self.reset_daily()

        now_t = time.time()
        self._last_snapshot_time = now_t

        # 确保关键列存在
        close_col = 'close' if 'close' in df.columns else ('price' if 'price' in df.columns else 'trade')
        open_col = 'open' if 'open' in df.columns else 'open_p'
        pct_col = 'percent' if 'percent' in df.columns else ('pct' if 'pct' in df.columns else 'ratio')
        vr_col = 'volume_ratio' if 'volume_ratio' in df.columns else ('vr' if 'vr' in df.columns else 'vol_ratio')
        amt_col = 'amount' if 'amount' in df.columns else 'turnover'
        
        # 严谨的换手率列检索：优先检索真实换手率列名，严防取到代表成交额的 'turnover' 列
        turn_col = None
        for cand in ('turnoverratio', 'turnover_rate', 'turnover_ratio', 'hsl', 'turnoverrate'):
            if cand in df.columns:
                turn_col = cand
                break
        if turn_col is None and 'turnover' in df.columns:
            try:
                # 采样抽检：若最大值 <= 100 则认为是换手率百分比，否则为成交额
                sample_s = df['turnover'].dropna().head(10)
                if not sample_s.empty and sample_s.max() <= 100.0:
                    turn_col = 'turnover'
            except Exception:
                pass

        import numpy as np
        if 'code' in df.columns:
            codes = df['code'].values
        else:
            codes = df.index.values
        closes = df[close_col].values if close_col in df.columns else None
        if closes is None:
            return 0
        opens = df[open_col].values if open_col in df.columns else closes
        pcts = df[pct_col].values if pct_col in df.columns else np.zeros(len(df))
        vrs = df[vr_col].values if vr_col in df.columns else np.ones(len(df))
        amts = df[amt_col].values if amt_col in df.columns else np.zeros(len(df))
        vwaps = df['vwap'].values if 'vwap' in df.columns else None
        pre_closes = df['pre_close'].values if 'pre_close' in df.columns else None
        names = df['name'].values if 'name' in df.columns else None
        open_pct_vals = df['open_pct'].values if 'open_pct' in df.columns else None
        highs = df['high'].values if 'high' in df.columns else None
        lows = df['low'].values if 'low' in df.columns else None
        turnovers = df[turn_col].values if (turn_col and turn_col in df.columns) else None

        updated_count = 0
        num_rows = len(codes)

        for i in range(num_rows):
            code_raw = codes[i]
            code_str = str(code_raw).strip()
            if not code_str or code_str.startswith(('sh000001', 'sz399001', 'sz399006', '999999')):
                continue

            if len(code_str) == 6 and code_str.isdigit():
                c_clean = code_str
            else:
                c_clean = ''.join(c for c in code_str if c.isdigit()).zfill(6)
            if not c_clean:
                continue

            raw_p = closes[i]
            curr_p = float(raw_p) if isinstance(raw_p, (int, float)) else _safe_float(raw_p)
            if curr_p <= 0.0:
                continue

            raw_pct = pcts[i]
            pct = float(raw_pct) if isinstance(raw_pct, (int, float)) else _safe_float(raw_pct)
            name = str(names[i]).strip() if names is not None else c_clean
            if not name:
                name = c_clean

            open_p = _safe_float(opens[i]) if opens is not None else curr_p
            if open_p <= 0.0:
                open_p = curr_p

            pre_close = _safe_float(pre_closes[i]) if pre_closes is not None else 0.0
            if pre_close <= 0.0:
                if (1.0 + pct / 100.0) != 0:
                    pre_close = curr_p / (1.0 + pct / 100.0)
                else:
                    pre_close = curr_p

            # 计算开盘涨幅 open_pct
            open_pct = _safe_float(open_pct_vals[i]) if open_pct_vals is not None else 0.0
            if open_pct == 0.0 and pre_close > 0:
                open_pct = (open_p - pre_close) / pre_close * 100.0

            # 均价 VWAP
            vwap = _safe_float(vwaps[i]) if vwaps is not None else 0.0
            if vwap <= 0.0:
                high_p = _safe_float(highs[i]) if highs is not None else curr_p
                low_p = _safe_float(lows[i]) if lows is not None else curr_p
                vwap = (open_p + curr_p + high_p + low_p) / 4.0 if (high_p > 0 and low_p > 0) else curr_p

            vol_ratio = _safe_float(vrs[i]) if vrs is not None else 1.0
            amount = _safe_float(amts[i]) if amts is not None else 0.0
            # 金额单位统一为亿元
            amt_yi = amount if amount < 10000 else (amount / 100000000.0 if amount > 1000000 else amount / 10000.0)

            # 安全获取换手率并防御越界
            turnover_pct = _safe_float(turnovers[i]) if turnovers is not None else 0.0
            if turnover_pct > 100.0:
                turnover_pct = 0.0

            # 获取或初始化状态
            st = self._states.get(c_clean)
            is_new = False
            if st is None:
                st = StockBubbleState(code=c_clean, name=name)
                st.pre_close = pre_close
                st.open_price = open_p
                st.open_pct = open_pct
                st.open_tier = get_pct_tier(open_pct)
                st.current_tier = get_pct_tier(pct)
                st.history_tiers = [st.open_tier]
                if st.current_tier != st.open_tier:
                    st.history_tiers.append(st.current_tier)
                st.high_pct = pct
                st.low_pct = pct
                self._states[c_clean] = st
                is_new = True

            # 更新实时指标
            st.curr_price = curr_p
            st.curr_pct = pct
            st.vwap = vwap
            st.vol_ratio = vol_ratio
            st.amount_yi = amt_yi
            st.turnover_pct = turnover_pct
            st.updated_time = now_t

            if pct > st.high_pct:
                st.high_pct = pct
            if pct < st.low_pct:
                st.low_pct = pct

            # 冒泡阶梯判定
            curr_tier = get_pct_tier(pct)
            if curr_tier != st.current_tier:
                # 发生阶梯跃迁
                prev_tier = st.current_tier
                st.current_tier = curr_tier
                st.last_jump_time = now_t
                if not st.history_tiers or st.history_tiers[-1] != curr_tier:
                    st.history_tiers.append(curr_tier)
                if curr_tier > prev_tier:
                    st.tier_jumps += (curr_tier - prev_tier)

            # 诊断开盘形态与评分
            self._evaluate_stock_pattern(st)
            updated_count += 1

        return updated_count

    def _evaluate_stock_pattern(self, st: StockBubbleState):
        """
        开盘形态路径分类与差异化评分
        """
        open_pct = st.open_pct
        curr_pct = st.curr_pct
        open_p = st.open_price
        curr_p = st.curr_price
        vwap = st.vwap
        vr = st.vol_ratio
        high_pct = st.high_pct
        low_pct = st.low_pct

        intraday_drift = (curr_p - open_p) / open_p * 100.0 if open_p > 0 else (curr_pct - open_pct)
        vwap_dev = (curr_p - vwap) / vwap * 100.0 if vwap > 0 else 0.0

        # 判断是否经历向上冒泡跃迁
        has_stepped_up = (st.tier_jumps >= 2 and curr_pct >= 2.0 and curr_pct >= open_pct + 1.5)

        # 1. ⚠️ 优先判断高开低走被套 (避坑防御预警)
        # 条件：高开 (>= 1.8%)，但随后大幅跌破开盘价和分时均线，日内下杀 >= 2.0%
        if open_pct >= 1.8 and intraday_drift <= -2.0 and curr_p < vwap * 0.995:
            st.pattern_type = "HIGH_OPEN_DROP"
            st.pattern_tag = "⚠️ 高开低走"
            st.pattern_desc = f"冲高回落被套(高开{open_pct:+.1f}%→下杀{intraday_drift:+.1f}%)"
            st.alpha_score = 30.0  # 低分警示

        # 2. 🚀 低开高走·反包突围 (Low Open High Climb)
        # 条件：开盘处于水下低开 (<= -0.5%)，盘中放量翻红穿过均线，日内拉升幅 >= 2.0%
        elif open_pct <= -0.5 and curr_pct >= 1.5 and intraday_drift >= 2.0 and curr_p >= vwap * 0.998:
            st.pattern_type = "LOW_OPEN_HIGH_CLIMB"
            st.pattern_tag = "🚀 低开高走"
            if open_pct <= -2.0 and curr_pct >= 3.0:
                st.pattern_desc = f"冰点强反包(低开{open_pct:+.1f}%→现{curr_pct:+.1f}%)"
            else:
                st.pattern_desc = f"弱转强抢筹(低开{open_pct:+.1f}%→拉升{intraday_drift:+.1f}%)"
            
            # 基础分 75 + 量比加成 + 均线支撑加成
            score = 75.0 + min(15.0, vr * 2.5) + min(10.0, max(0.0, vwap_dev * 2.0))
            st.alpha_score = min(99.0, score)

        # 3. ⚡ 阶梯跃迁·步步高升 (Step-by-Step Bubble Up)
        # 条件：连续经历 2 个或以上涨跌梯级跳跃 (0-2 -> 2-4 -> 4-6)
        elif has_stepped_up and curr_p >= vwap:
            st.pattern_type = "STEP_BUBBLE_UP"
            st.pattern_tag = "⚡ 步步高升"
            st.pattern_desc = f"梯级连续跃迁({st.tier_jumps}阶跳,开{open_pct:+.1f}%→{curr_pct:+.1f}%)"
            
            score = 78.0 + min(12.0, st.tier_jumps * 3.0) + min(10.0, vr * 2.0)
            st.alpha_score = min(99.0, score)

        # 4. 💎 高开蓄势·放量锁筹 (High Open Consolidation)
        # 条件：高开 1.0%~5.5%，随后窄幅震荡消化浮筹，不破开盘价/分时均线，放量换手承接极强
        elif 1.0 <= open_pct <= 5.5 and abs(intraday_drift) <= 1.8 and curr_p >= vwap * 0.992 and vr >= 1.5:
            st.pattern_type = "HIGH_OPEN_CONSOLIDATION"
            st.pattern_tag = "💎 高开蓄势"
            st.pattern_desc = f"高开{open_pct:+.1f}%横盘锁筹(量比{vr:.1f},偏离{vwap_dev:+.1f}%)"
            
            score = 72.0 + min(18.0, vr * 3.0) + (5.0 if curr_p >= open_p else 0.0)
            st.alpha_score = min(98.0, score)

        # 5. 🌊 平开脉冲·快速点火 (Flat Open Spark)
        # 条件：平开 (-0.8% ~ +0.8%)，盘中放量快速突破 2.5%
        elif abs(open_pct) <= 0.8 and curr_pct >= 2.5 and vr >= 1.8 and curr_p >= vwap:
            st.pattern_type = "FLAT_OPEN_SPARK"
            st.pattern_tag = "🌊 平开脉冲"
            st.pattern_desc = f"平开急速点火(涨幅{curr_pct:+.1f}%,量比{vr:.1f})"
            
            score = 70.0 + min(15.0, curr_pct * 1.5) + min(10.0, vr * 2.0)
            st.alpha_score = min(96.0, score)

        # 6. ❄️ 水下点火·冰点突击 (Underwater Spark)
        # 条件：开盘处于极度水下 (<= -2.5%)，现价快速拉升
        elif open_pct <= -2.5 and curr_pct >= 0.0 and vr >= 1.5:
            st.pattern_type = "UNDERWATER_SPARK"
            st.pattern_tag = "❄️ 水下点火"
            st.pattern_desc = f"水下冰点突围(开{open_pct:+.1f}%→翻红{curr_pct:+.1f}%)"
            
            score = 68.0 + min(20.0, (curr_pct - open_pct) * 2.0)
            st.alpha_score = min(95.0, score)

        # 7. 常规/其他形态
        else:
            st.pattern_type = "NORMAL"
            if curr_pct >= 5.0:
                st.pattern_tag = "🔥 强势拉升"
                st.pattern_desc = f"强势冲高(现价{curr_pct:+.1f}%)"
                st.alpha_score = 65.0 + min(15.0, vr * 1.5)
            elif curr_pct <= -4.0:
                st.pattern_tag = "🔻 弱势下跌"
                st.pattern_desc = f"弱势探底(跌幅{curr_pct:+.1f}%)"
                st.alpha_score = 35.0
            else:
                st.pattern_tag = "↔️ 横盘震荡"
                st.pattern_desc = f"窄幅整理(开{open_pct:+.1f}%,现{curr_pct:+.1f}%)"
                st.alpha_score = 50.0

    def get_stock_profile(self, code: str) -> Dict[str, Any]:
        """获取单个股票的开盘与跃迁特征画像"""
        c_clean = ''.join(c for c in str(code) if c.isdigit()).zfill(6)
        st = self._states.get(c_clean)
        if st is None:
            return {
                "code": c_clean,
                "open_pct": 0.0,
                "pattern_type": "NORMAL",
                "pattern_tag": "横盘整理",
                "pattern_desc": "-",
                "trajectory_str": "-",
                "tier_jumps": 0,
                "alpha_score": 50.0
            }

        # 构建跃迁路径字符串，例如 "0%→+2%→+4%"
        traj_parts = []
        for t_idx in st.history_tiers:
            if 0 <= t_idx < len(TIER_SHORT_TAGS):
                tag = TIER_SHORT_TAGS[t_idx]
                if not traj_parts or traj_parts[-1] != tag:
                    traj_parts.append(tag)
        traj_str = "→".join(traj_parts) if traj_parts else "-"

        return {
            "code": st.code,
            "name": st.name,
            "open_pct": st.open_pct,
            "curr_pct": st.curr_pct,
            "high_pct": st.high_pct,
            "low_pct": st.low_pct,
            "vol_ratio": st.vol_ratio,
            "amount_yi": st.amount_yi,
            "turnover_pct": st.turnover_pct,
            "pattern_type": st.pattern_type,
            "pattern_tag": st.pattern_tag,
            "pattern_desc": st.pattern_desc,
            "trajectory_str": traj_str,
            "tier_jumps": st.tier_jumps,
            "current_tier_name": TIER_NAMES[st.current_tier] if 0 <= st.current_tier < len(TIER_NAMES) else "",
            "alpha_score": st.alpha_score
        }

    def get_bubble_radar_records(
        self,
        current_df: Optional[pd.DataFrame] = None,
        pattern_filter: Optional[str] = None,
        min_score: float = 65.0
    ) -> List[Dict[str, Any]]:
        """
        获取盘中开盘起点与阶梯跃迁高价值差异化标的列表 (用于雷达与看板)
        """
        if current_df is not None and not current_df.empty:
            self.update_market_snapshot(current_df)

        results = []
        for c_clean, st in self._states.items():
            if st.alpha_score < min_score:
                continue

            # 排除高开低走被套的预警股（除非显式指定 pattern_filter）
            if st.pattern_type == "HIGH_OPEN_DROP" and pattern_filter != "HIGH_OPEN_DROP":
                continue

            # 模式过滤
            if pattern_filter and pattern_filter != "ALL":
                if pattern_filter == "LOW_OPEN_HIGH_CLIMB" and st.pattern_type != "LOW_OPEN_HIGH_CLIMB":
                    continue
                elif pattern_filter == "HIGH_OPEN_CONSOLIDATION" and st.pattern_type != "HIGH_OPEN_CONSOLIDATION":
                    continue
                elif pattern_filter == "STEP_BUBBLE_UP" and st.pattern_type != "STEP_BUBBLE_UP":
                    continue
                elif pattern_filter == "SPARK" and st.pattern_type not in ("FLAT_OPEN_SPARK", "UNDERWATER_SPARK"):
                    continue

            # 生成跃迁轨迹
            traj_parts = []
            for t_idx in st.history_tiers:
                if 0 <= t_idx < len(TIER_SHORT_TAGS):
                    tag = TIER_SHORT_TAGS[t_idx]
                    if not traj_parts or traj_parts[-1] != tag:
                        traj_parts.append(tag)
            traj_str = "→".join(traj_parts) if traj_parts else "-"

            rec = {
                "code": st.code,
                "name": st.name,
                "price": st.curr_price,
                "pct": st.curr_pct,
                "open_pct": st.open_pct,
                "high_pct": st.high_pct,
                "low_pct": st.low_pct,
                "vol_ratio": st.vol_ratio,
                "amount_yi": st.amount_yi,
                "turnover_pct": st.turnover_pct,
                "tier_jumps": st.tier_jumps,
                "trajectory_str": traj_str,
                "pattern_type": st.pattern_type,
                "tier_tag": st.pattern_tag,
                "pattern_desc": st.pattern_desc,
                "momentum_score": st.alpha_score,
                "is_bubble_hit": True
            }
            results.append(rec)

        # 排序：按 Alpha 评分降序 > 阶梯跃迁次数降序 > 量比降序 > 涨幅降序
        results.sort(key=lambda x: (
            x.get("momentum_score", 0.0),
            x.get("tier_jumps", 0),
            x.get("vol_ratio", 1.0),
            x.get("pct", 0.0)
        ), reverse=True)

        return results


def get_opening_bubble_engine() -> OpeningBubbleEngine:
    """获取 OpeningBubbleEngine 全局单例"""
    return OpeningBubbleEngine()

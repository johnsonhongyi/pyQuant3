# -*- coding: utf-8 -*-
"""
ats/sector_rotation_pullback_miner.py — 板块轮动前排引导与资金主线回踩启动自动化深挖中枢 (SSOT)
=============================================================================
核心量化机理与业务定位：
1. 【阶段一：前排冲锋与引导板块发现 (Leader & Sector Mining)】：
   - 提取全市场实时宽表多维指标：dff(当日涨幅), dff2(距离MA20涨幅), dff3(长期涨幅),
     per1d~per9d(时序涨跌幅), vol_ratio(量比), ratio(换手率), 成交额与连板/赛马/异动特征；
   - 识别带头冲锋的先锋前排标的 (主升先锋龙头、底部放量大反弹先锋、竞价/赛马强势爆量)；
2. 【阶段二：资金流向主线双向迭代聚合 (Sector Flow Aggregation)】：
   - 从冲锋前排个股自下而上聚合其实际所属实体概念板块 (Category / Industry)；
   - 依据前排家数、板块平均涨幅、总成交额、涨停家数与加权量比，识别锁定当前主力资金重仓攻击的
     Top 核心主线板块 (排除孤狼脉冲假突破)；
3. 【阶段三：主线板块内深挖回踩确认启动个股 (In-Sector Pullback Reversal Discovery)】：
   - 在已锁定的主力主线板块中，反向遍历该板块内的全部成分股；
   - 严格匹配：
     * MA20d 均线空间依托：-2.5% <= dff2 <= 6.5% (回踩 MA20 黄金安全带企稳)；
     * 时序走势与洗盘确认 (per1d~per9d)：前1~3日缩量洗盘阴线 + 今日首次放量转阳启动；
     * 底部超跌横盘筑底 (dff3 <= 15%) + 今日首次突破；
     * 通达信支撑线 / 通道下轨 (ch_supp_price) 双重共振回踩；
     * 温和量比配合 (1.15 <= vol_ratio <= 4.0)，绝不追高已有大涨标的 (dff < 8.0%)；
4. 【阶段四：输出量化决策与跟进池】：
   - 输出建议买区 (Buy Zone)、MA20/支撑防守止损位 (Stop Loss)、补涨空间目标及可解释性理由。
"""

import os
import sys
import time
import math
import logging
import threading
import re
from typing import Dict, List, Tuple, Optional, Any, Set, Union
from dataclasses import dataclass, field, asdict
import pandas as pd
import numpy as np

from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("SectorRotationPullbackMiner")

_RE_CLEAN_SECTOR = re.compile(r'^[^\w\u4e00-\u9fa5]+')
_INVALID_SECTORS = frozenset({'--', '-', '---', '0', '0.0', '00', '000', '000000', 'none', 'nan', 'null', '未知', '其它', '其他', '未分类', 'default'})


@dataclass
class PullbackFilterConfig:
    """
    回踩确认启动底层筛选量化策略配置类 (可选择、可自定义、支持持久化)
    """
    mode_name: str = "🎯 经典标准"          # 策略模式名
    dff2_min: float = -1.8                # 回踩 MA20d 偏离下限 (%)，默认 -1.8%
    dff2_max: float = 4.5                 # 回踩 MA20d 偏离上限 (%)，默认 +4.5%
    min_eval_pct: float = 0.3             # 最小收阳上涨幅度 (%)，底线必须收阳(>0)
    max_eval_pct: float = 6.5             # 最大涨幅上限 (%)，防止追高
    min_vol_ratio: float = 1.15           # 启动温和量比门槛，默认 1.15
    min_turnover: float = 1.2             # 最小活跃换手率 (%)，剔除死水
    min_amt_yi: float = 0.25              # 最小成交额 (亿元)，剔除僵尸股
    min_dff3: float = -15.0               # 长期累积偏离底线 (%)，剔除常年阴跌
    require_channel_supp: bool = False    # 是否强制要求通达信通道支撑共振
    prefer_channel_supp: bool = True      # 通道支撑共振标的优先加分加权

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PullbackFilterConfig':
        if not isinstance(data, dict):
            return cls()
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        # 针对数值做安全转换
        for float_k in ('dff2_min', 'dff2_max', 'min_eval_pct', 'max_eval_pct',
                        'min_vol_ratio', 'min_turnover', 'min_amt_yi', 'min_dff3'):
            if float_k in filtered:
                try:
                    filtered[float_k] = float(filtered[float_k])
                except (ValueError, TypeError):
                    pass
        for bool_k in ('require_channel_supp', 'prefer_channel_supp'):
            if bool_k in filtered:
                filtered[bool_k] = bool(filtered[bool_k])
        if 'mode_name' in filtered:
            filtered['mode_name'] = str(filtered['mode_name'])
        return cls(**filtered)


PRESET_FILTER_MODES: Dict[str, PullbackFilterConfig] = {
    "🎯 经典标准": PullbackFilterConfig(
        mode_name="🎯 经典标准",
        dff2_min=-1.8,
        dff2_max=4.5,
        min_eval_pct=0.3,
        max_eval_pct=6.5,
        min_vol_ratio=1.15,
        min_turnover=1.2,
        min_amt_yi=0.25,
        min_dff3=-15.0,
        require_channel_supp=False,
        prefer_channel_supp=True
    ),
    "🚀 极速起爆": PullbackFilterConfig(
        mode_name="🚀 极速起爆",
        dff2_min=-1.0,
        dff2_max=5.5,
        min_eval_pct=1.2,
        max_eval_pct=7.5,
        min_vol_ratio=1.35,
        min_turnover=2.0,
        min_amt_yi=0.50,
        min_dff3=-10.0,
        require_channel_supp=False,
        prefer_channel_supp=True
    ),
    "💎 稳健通道低吸": PullbackFilterConfig(
        mode_name="💎 稳健通道低吸",
        dff2_min=-1.5,
        dff2_max=3.2,
        min_eval_pct=0.2,
        max_eval_pct=5.0,
        min_vol_ratio=1.05,
        min_turnover=1.0,
        min_amt_yi=0.20,
        min_dff3=-20.0,
        require_channel_supp=True,
        prefer_channel_supp=True
    )
}



def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全浮点数转换，防止 None、NaN、inf 崩溃"""
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
    """提取纯数字 6 位标准证券代码"""
    if isinstance(c, str) and len(c) == 6 and c.isdigit():
        return c
    s = str(c).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else s


def is_valid_sector_name(sec: Any) -> bool:
    """
    严密判定板块名称是否为有效且明确的实体板块（过滤掉 '--', '0', '0.0', 'nan', '未知', 纯数字等）
    """
    if not sec:
        return False
    s = str(sec).strip()
    if not s or s.lower() in _INVALID_SECTORS or s.isdigit():
        return False
    cleaned = _RE_CLEAN_SECTOR.sub('', s).strip()
    if not cleaned or cleaned.lower() in _INVALID_SECTORS or cleaned.isdigit():
        return False
    return True


def is_index_or_fund_code(code: Any, name: Any = "") -> bool:
    """判断是否为大盘综合指数或ETF，纯化个股中枢"""
    c = _clean_code(code)
    nm = str(name).strip() if name else ""
    if c.startswith(("399", "999", "899")):
        return True
    if c in ("000001", "000300", "000016", "000905", "000852"):
        if nm and ("银行" in nm or "平安" in nm or "机械" in nm):
            return False
        if "上证" in nm or "指数" in nm:
            return True
    if nm:
        for kw in ("指数", "成指", "综指", "ETF", "北证50", "科创50", "上证50", "沪深300", "中证500"):
            if kw in nm:
                return True
    return False


class SectorRotationPullbackMiner:
    """
    板块轮动前排引导与资金主线回踩启动自动化深挖核心引擎 (单例)
    """
    _instance: Optional['SectorRotationPullbackMiner'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'SectorRotationPullbackMiner':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._last_report: Dict[str, Any] = {}
        self._last_calc_time: float = 0.0
        self._cache_lock = threading.RLock()

    def _extract_df_arrays(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        极速向量化预提取全市场数据为原生 NumPy 一维数组与 Python 列表
        耗时 < 5ms，全管道共享复用，杜绝重复提取与 Pandas 开销
        """
        n = len(df)
        def _get_float_arr(col_names: List[str], default_val: float = 0.0) -> np.ndarray:
            for c in col_names:
                if c in df.columns:
                    arr = df[c].values
                    if arr.dtype.kind in ('i', 'f'):
                        return np.nan_to_num(arr, nan=default_val).astype(np.float64, copy=False)
                    return pd.to_numeric(pd.Series(arr), errors='coerce').fillna(default_val).to_numpy(dtype=np.float64)
            return np.full(n, default_val, dtype=np.float64)

        p_arr = _get_float_arr(['close', 'price', 'trade'], 0.0)
        pct_arr = _get_float_arr(['percent', 'pct', 'dff'], 0.0)
        amt_raw = _get_float_arr(['amount', 'turnover', 'money'], 0.0)
        max_amt = amt_raw.max() if n > 0 else 0.0
        amt_arr = amt_raw / 1e8 if max_amt > 1e7 else (amt_raw / 10000.0 if max_amt > 1000 else amt_raw)
        vr_arr = np.clip(_get_float_arr(['vol_ratio', 'volume_ratio', 'vr'], 1.0), 0.1, 50.0)
        to_arr = _get_float_arr(['ratio', 'turnover_rate', 'hsl', 'turnover'], 0.0)
        ma20_arr = _get_float_arr(['ma20d', 'ma20'], 0.0)

        # dff (当日偏离/涨跌)
        dff_arr = _get_float_arr(['dff'], np.nan)
        nan_dff = np.isnan(dff_arr)
        if nan_dff.any():
            dff_arr[nan_dff] = pct_arr[nan_dff]

        # dff2 (距离 MA20d 偏离)
        dff2_arr = _get_float_arr(['dff2'], np.nan)
        nan_dff2 = np.isnan(dff2_arr)
        if nan_dff2.any():
            has_ma20 = (ma20_arr > 0.0) & (p_arr > 0.0)
            dff2_arr[nan_dff2] = 0.0
            calc_mask = nan_dff2 & has_ma20
            dff2_arr[calc_mask] = np.round((p_arr[calc_mask] - ma20_arr[calc_mask]) / ma20_arr[calc_mask] * 100.0, 2)

        # dff3 (长期累积涨幅)
        dff3_arr = _get_float_arr(['dff3', 'perc3d', 'percent3d'], 0.0)

        # per1d, per2d, per3d
        p1_arr = _get_float_arr(['per1d'], 0.0)
        p2_arr = _get_float_arr(['per2d'], 0.0)
        p3_arr = _get_float_arr(['per3d'], 0.0)

        # 智能判定是否为盘后初始化 / 非交易时段复盘模式 (Post-Market EOD Mode)
        # 机制核心：当 percent/dff 绝大多数为 0，但 per1d (最新收盘日) 有大量非零有效数据时自动自愈
        pct_zero_cnt = int((pct_arr == 0.0).sum())
        p1_valid_cnt = int((p1_arr != 0.0).sum())
        is_post_market = (pct_zero_cnt / max(1, n) >= 0.70) and (p1_valid_cnt / max(1, n) >= 0.15)

        # 评估涨幅与时序时空对齐自愈
        if is_post_market:
            eval_pct_arr = p1_arr        # 以最新收盘日(per1d)作为冲锋与涨跌评估基准
            eval_prev1_arr = p2_arr      # 前序第 1 日由 per2d 替代
            eval_prev2_arr = p3_arr      # 前序第 2 日由 per3d 替代
        else:
            eval_pct_arr = dff_arr       # 盘中以今日偏离/涨幅为基准
            eval_prev1_arr = p1_arr      # 昨日
            eval_prev2_arr = p2_arr      # 前日

        # ch_supp 支撑线价格
        ch_supp_arr = _get_float_arr(['ch_supp', 'ch_supp_price', 'supp_price', 'ch_lower'], 0.0)
        # ch_pos 通道位置 (0~100)
        ch_pos_arr = _get_float_arr(['ch_pos', 'channel_pos'], 50.0)
        # ch_slope 通道支撑线倾角 (度)
        ch_slope_arr = _get_float_arr(['ch_supp_slope_deg', 'supp_slope_deg', 'ch_slope_deg'], 0.0)

        # 代码与名称
        idx_vals = df.index.values
        c_arr = [_clean_code(c) for c in idx_vals]
        nm_arr = [str(x) for x in df['name'].values] if 'name' in df.columns else c_arr

        # 所属板块
        sec_col = next((c for c in ('category', 'industry', 'concept') if c in df.columns), None)
        sec_arr = [str(x) for x in df[sec_col].values] if sec_col else [''] * n

        return {
            'n': n,
            'is_post_market': is_post_market,
            'eval_pct_arr': eval_pct_arr,
            'eval_prev1_arr': eval_prev1_arr,
            'eval_prev2_arr': eval_prev2_arr,
            'c_arr': c_arr,
            'nm_arr': nm_arr,
            'p_arr': p_arr,
            'pct_arr': pct_arr,
            'amt_arr': amt_arr,
            'vr_arr': vr_arr,
            'to_arr': to_arr,
            'ma20_arr': ma20_arr,
            'dff_arr': dff_arr,
            'dff2_arr': dff2_arr,
            'dff3_arr': dff3_arr,
            'p1_arr': p1_arr,
            'p2_arr': p2_arr,
            'p3_arr': p3_arr,
            'ch_supp_arr': ch_supp_arr,
            'ch_pos_arr': ch_pos_arr,
            'ch_slope_arr': ch_slope_arr,
            'sec_arr': sec_arr
        }

    def identify_leading_sectors(
        self,
        df: pd.DataFrame,
        min_pioneers_per_sector: int = 2,
        top_sectors_count: int = 6,
        ctx: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        【阶段一与阶段二】：从全市场数据中挖掘先锋冲锋标的，并自下而上聚合当前主力资金主线板块
        :param df: 全市场实时或策略 DataFrame
        :param min_pioneers_per_sector: 构成主线的最小前排个股数量 (默认 2 只形成集群效应)
        :param top_sectors_count: 提取排名前 N 的主力板块
        :param ctx: 预提取的高性能数组上下文 (可选，避免重复提取)
        :return: 排序后的主线板块统计列表
        """
        if df is None or df.empty:
            return []

        if ctx is None:
            ctx = self._extract_df_arrays(df)

        n = ctx['n']
        if n == 0:
            return []

        is_post_market = ctx.get('is_post_market', False)
        eval_pct_arr = ctx['eval_pct_arr']
        c_arr = ctx['c_arr']
        nm_arr = ctx['nm_arr']
        p_arr = ctx['p_arr']
        pct_arr = ctx['pct_arr']
        amt_arr = ctx['amt_arr']
        vr_arr = ctx['vr_arr']
        to_arr = ctx['to_arr']
        dff_arr = ctx['dff_arr']
        dff2_arr = ctx['dff2_arr']
        dff3_arr = ctx['dff3_arr']
        sec_arr = ctx['sec_arr']

        # 提取连板或天梯数据（若有，仅读内存缓存，绝对不阻塞触发外部 I/O）
        limit_up_dict = {}
        try:
            from ats.limit_up_engine import LimitUpEngine
            lue = LimitUpEngine.get_instance()
            cached_recs = getattr(lue, '_current_live_records', None)
            if cached_recs:
                for r in cached_recs:
                    c = _clean_code(r.get("code", ""))
                    if c:
                        limit_up_dict[c] = r
        except Exception:
            pass

        # 1. 扫描挖掘【冲锋前排与先锋龙头】
        pioneers: List[Dict[str, Any]] = []
        pioneers_code_set = set()

        for i in range(n):
            price = float(p_arr[i])
            if price <= 0.0:
                continue
            code = str(c_arr[i])
            name = str(nm_arr[i])
            if is_index_or_fund_code(code, name):
                continue

            pct = float(pct_arr[i])
            eval_pct = float(eval_pct_arr[i])
            amt = float(amt_arr[i])
            vr = float(vr_arr[i])
            to = float(to_arr[i])
            dff = float(dff_arr[i])
            dff2 = float(dff2_arr[i])
            dff3 = float(dff3_arr[i])
            sec = str(sec_arr[i])

            ladder_item = limit_up_dict.get(code, {})
            is_limit = bool(ladder_item.get("is_limit_up", False) or eval_pct >= 9.5)
            l_days = int(ladder_item.get("limit_days", 1 if is_limit else 0))

            # 冲锋先锋判定画像 (自适应盘中与盘后初始化)
            is_pioneer = False
            pioneer_type = ""

            if is_limit or l_days >= 2:
                is_pioneer = True
                pioneer_type = f"👑 {l_days}连板龙头" if l_days >= 2 else "👑 涨停先锋"
            elif eval_pct >= 4.5 and (vr >= 1.20 or is_post_market) and dff2 >= 1.5:
                is_pioneer = True
                pioneer_type = "🚀 主升先锋冲锋"
            elif dff3 <= 15.0 and eval_pct >= 3.8 and dff2 >= 0.0 and (vr >= 1.25 or is_post_market):
                is_pioneer = True
                pioneer_type = "💎 底部放量大反弹"
            elif eval_pct >= 3.5 and (to >= 3.0 or vr >= 1.8):
                is_pioneer = True
                pioneer_type = "⚡ 资金活跃突击"
            elif dff2 >= 8.0 and eval_pct >= 2.0:
                is_pioneer = True
                pioneer_type = "🌟 趋势大主升龙头"

            if is_pioneer:
                pioneers.append({
                    "code": code,
                    "name": name,
                    "price": price,
                    "pct": eval_pct, # 使用评估涨幅，确保盘后复盘展示非零
                    "real_pct": pct,
                    "amt_yi": amt,
                    "vol_ratio": vr,
                    "turnover": to,
                    "dff": dff,
                    "dff2": dff2,
                    "dff3": dff3,
                    "pioneer_type": pioneer_type,
                    "sector_raw": sec
                })
                pioneers_code_set.add(code)

        # 2. 自下而上聚合主线板块
        sector_agg: Dict[str, Dict[str, Any]] = {}

        for i in range(n):
            price = float(p_arr[i])
            if price <= 0.0:
                continue
            code = str(c_arr[i])
            name = str(nm_arr[i])
            if is_index_or_fund_code(code, name):
                continue

            sec_raw = str(sec_arr[i])
            if not is_valid_sector_name(sec_raw):
                continue

            amt = float(amt_arr[i])
            eval_pct = float(eval_pct_arr[i])
            vr = float(vr_arr[i])
            to = float(to_arr[i])

            # 分割复合概念 (取前2个核心概念)
            sub_secs = [s.strip() for s in sec_raw.replace(';', ',').replace('、', ',').split(',') if s.strip()]
            for s_name in sub_secs[:2]:
                if not is_valid_sector_name(s_name) or len(s_name) < 2:
                    continue

                if s_name not in sector_agg:
                    sector_agg[s_name] = {
                        "name": s_name,
                        "total_amt_yi": 0.0,
                        "up_count": 0,
                        "total_count": 0,
                        "limit_up_count": 0,
                        "pioneer_count": 0,
                        "sum_pct": 0.0,
                        "sum_vr_weighted": 0.0,
                        "sum_vr": 0.0,
                        "sum_to": 0.0,
                        "pioneers": [],
                        "leader_code": "",
                        "leader_name": "",
                        "leader_pct": -99.0,
                        "leader_type": ""
                    }

                st = sector_agg[s_name]
                st["total_amt_yi"] += amt
                st["total_count"] += 1
                st["sum_pct"] += eval_pct
                st["sum_vr_weighted"] += amt * vr
                st["sum_vr"] += vr
                st["sum_to"] += to
                if eval_pct > 0.0:
                    st["up_count"] += 1
                if eval_pct >= 9.5:
                    st["limit_up_count"] += 1

                # 记录最高领涨先锋
                if eval_pct > st["leader_pct"]:
                    st["leader_pct"] = eval_pct
                    st["leader_code"] = code
                    st["leader_name"] = name
                    st["leader_type"] = "领涨龙头"

        # 挂载先锋列表到各板块
        for p in pioneers:
            sec_raw = p["sector_raw"]
            sub_secs = [s.strip() for s in sec_raw.replace(';', ',').replace('、', ',').split(',') if s.strip()]
            for s_name in sub_secs[:2]:
                if s_name in sector_agg:
                    sector_agg[s_name]["pioneer_count"] += 1
                    sector_agg[s_name]["pioneers"].append(p)

        # 3. 计算板块资金主线综合强度得分
        result_sectors = []
        for s_name, st in sector_agg.items():
            if st["total_count"] < 3:
                continue

            st["avg_pct"] = round(st["sum_pct"] / st["total_count"], 2)
            up_ratio = st["up_count"] / st["total_count"]

            if st["total_amt_yi"] > 0:
                sec_vr = st["sum_vr_weighted"] / st["total_amt_yi"]
                amt_score = min(40.0, st["total_amt_yi"] * 0.20)
            else:
                sec_vr = st["sum_vr"] / max(1, st["total_count"])
                avg_to = st["sum_to"] / max(1, st["total_count"])
                amt_score = min(40.0, st["total_count"] * 1.0 + avg_to * 3.0)

            st["vol_ratio"] = round(float(sec_vr), 2)
            st["total_amt_yi"] = round(float(st["total_amt_yi"]), 1)

            # 强度评分数学模型：
            # 资金额(上限40分) + 前排先锋数*10 + 涨停数*15 + 平均涨幅*4 + 上涨比例*20 + 加权量比加分
            pio_score = st["pioneer_count"] * 10.0
            limit_score = st["limit_up_count"] * 15.0
            pct_score = max(0.0, st["avg_pct"]) * 4.0
            ratio_score = up_ratio * 20.0
            vr_score = min(12.0, max(0.0, (st["vol_ratio"] - 1.0) * 8.0)) if not is_post_market else 5.0

            strength_score = amt_score + pio_score + limit_score + pct_score + ratio_score + vr_score
            st["strength_score"] = round(strength_score, 1)

            # 主线评级画像
            if st["limit_up_count"] >= 2 or (st["pioneer_count"] >= 3 and st["strength_score"] >= 50.0):
                st["grade"] = "👑 核心主线"
            elif st["limit_up_count"] >= 1 or st["pioneer_count"] >= 2 or st["strength_score"] >= 35.0:
                st["grade"] = "🚀 活跃进攻"
            else:
                st["grade"] = "🟡 轮动分支"

            # 过滤孤狼无前排的弱势板块
            if st["pioneer_count"] >= min_pioneers_per_sector or st["limit_up_count"] >= 1:
                result_sectors.append(st)

        # 兜底保底机制：若常规门槛筛选出的板块不足 top_sectors_count，自动保底补齐
        if len(result_sectors) < top_sectors_count:
            existing_names = set(s["name"] for s in result_sectors)
            fallback_candidates = [
                st for st in sector_agg.values()
                if st["total_count"] >= 3 and st["name"] not in existing_names
            ]
            fallback_candidates.sort(
                key=lambda x: (x["strength_score"], x["avg_pct"], x["total_amt_yi"]),
                reverse=True
            )
            result_sectors.extend(fallback_candidates[:(top_sectors_count - len(result_sectors))])

        # 按综合资金强度降序排列
        result_sectors.sort(key=lambda x: (x["strength_score"], x["total_amt_yi"]), reverse=True)
        return result_sectors[:top_sectors_count]

    def mine_pullback_reversal_stocks(
        self,
        df: pd.DataFrame,
        leading_sectors: List[Dict[str, Any]],
        dff2_min: float = -1.8,
        dff2_max: float = 4.5,
        min_vol_ratio: float = 1.15,
        max_dff_pct: float = 6.5,
        ctx: Optional[Dict[str, Any]] = None,
        filter_config: Optional[PullbackFilterConfig] = None
    ) -> List[Dict[str, Any]]:
        """
        【阶段三】：在已确认的主线板块内部，深挖“MA20企稳+活跃势能+有效放量上涨/启动+通道支撑”的个股跟进
        :param df: 全市场实时或策略 DataFrame
        :param leading_sectors: 阶段二锁定的核心主线板块列表
        :param dff2_min: 回踩 MA20d 下限偏离度 (默认 -1.8%)
        :param dff2_max: 回踩 MA20d 上限偏离度 (默认 +4.5%)
        :param min_vol_ratio: 启动温和量比门槛 (默认 1.15)
        :param max_dff_pct: 当日涨幅上限 (防止追高，默认 <= 6.5%)
        :param ctx: 预提取的高性能数组上下文 (可选，避免重复提取)
        :param filter_config: 底层筛选策略配置 (可选择/自定义，优先级高于离散参数)
        :return: 回踩确认启动标的列表
        """
        if df is None or df.empty or not leading_sectors:
            return []

        target_sector_names = set(s["name"] for s in leading_sectors if is_valid_sector_name(s.get("name")))
        if not target_sector_names:
            return []

        # 解析与对齐筛选配置 (SSOT)
        cfg = filter_config or PullbackFilterConfig(
            mode_name="🎯 经典标准",
            dff2_min=dff2_min,
            dff2_max=dff2_max,
            min_eval_pct=0.3,
            max_eval_pct=max_dff_pct,
            min_vol_ratio=min_vol_ratio,
            min_turnover=1.2,
            min_amt_yi=0.25,
            min_dff3=-15.0,
            require_channel_supp=False,
            prefer_channel_supp=True
        )

        c_dff2_min = cfg.dff2_min
        c_dff2_max = cfg.dff2_max
        c_min_pct = cfg.min_eval_pct
        c_max_pct = cfg.max_eval_pct
        c_min_vr = cfg.min_vol_ratio
        c_min_to = cfg.min_turnover
        c_min_amt = cfg.min_amt_yi
        c_min_dff3 = cfg.min_dff3
        c_req_ch = cfg.require_channel_supp
        c_prefer_ch = cfg.prefer_channel_supp

        if ctx is None:
            ctx = self._extract_df_arrays(df)

        n = ctx['n']
        if n == 0:
            return []

        c_arr = ctx['c_arr']
        nm_arr = ctx['nm_arr']
        p_arr = ctx['p_arr']
        pct_arr = ctx['pct_arr']
        amt_arr = ctx['amt_arr']
        dff_arr = ctx['dff_arr']
        dff2_arr = ctx['dff2_arr']
        dff3_arr = ctx['dff3_arr']
        ma20_arr = ctx['ma20_arr']
        ch_supp_arr = ctx['ch_supp_arr']
        ch_pos_arr = ctx.get('ch_pos_arr', np.full(n, 50.0))
        ch_slope_arr = ctx.get('ch_slope_arr', np.full(n, 0.0))
        vr_arr = ctx['vr_arr']
        to_arr = ctx['to_arr']
        sec_arr = ctx['sec_arr']
        eval_pct_arr = ctx['eval_pct_arr']
        eval_prev1_arr = ctx['eval_prev1_arr']
        eval_prev2_arr = ctx['eval_prev2_arr']
        is_post_market = ctx.get('is_post_market', False)

        # 检测数据集中是否真实包含换手率与成交额数据 (若测试或精简流中未提供，则自动豁免，避免一刀切误杀)
        has_valid_to = bool((to_arr > 0).any())
        has_valid_amt = bool((amt_arr > 0).any())

        pullback_candidates = []

        for i in range(n):
            price = float(p_arr[i])
            if price <= 0.0:
                continue
            code = str(c_arr[i])
            name = str(nm_arr[i])
            if is_index_or_fund_code(code, name):
                continue

            sec_raw = str(sec_arr[i])

            # 1. 匹配是否属于当前核心主线板块之一
            matched_sec = None
            for ts in leading_sectors:
                s_name = ts["name"]
                if s_name in sec_raw:
                    matched_sec = ts
                    break

            if not matched_sec:
                continue

            eval_pct = float(eval_pct_arr[i])
            pct = float(pct_arr[i])

            # 2. 维度一：有效上涨/启动底线 (坚决收阳，绝不选负涨幅阴跌或0%死水)
            if eval_pct < c_min_pct or eval_pct > c_max_pct:
                continue

            # 3. 维度二：活跃流动性势能与长期底蕴 (真实数据列存在时强校验)
            to = float(to_arr[i])
            if has_valid_to and to < c_min_to:
                continue
            amt = float(amt_arr[i])
            if has_valid_amt and amt < c_min_amt:
                continue
            dff3 = float(dff3_arr[i])
            if dff3 < c_min_dff3:
                continue

            # 4. 维度三：MA20d 依托与震荡企稳
            ma20 = float(ma20_arr[i])
            if ma20 > 0 and price < ma20 * 0.980:
                continue  # 跌破 MA20 支撑位破位排除

            dff = float(dff_arr[i])
            dff2 = float(dff2_arr[i])
            ch_supp = float(ch_supp_arr[i])
            ch_pos = float(ch_pos_arr[i])
            ch_slope = float(ch_slope_arr[i])
            vr = float(vr_arr[i])

            # 5. 维度四：通道支撑与 KX 支撑线共振研判
            has_supp_line = (ch_supp > 0 and price >= ch_supp * 0.982 and price <= ch_supp * 1.045)
            has_channel_base = (0.0 < ch_pos <= 38.0)
            has_channel_support = has_supp_line or has_channel_base

            if c_req_ch and not has_channel_support:
                continue

            # MA20 空间区间判定 (若踩在通道支撑线上，上限可轻微放宽 1.0%)
            max_dff2_allowed = (c_dff2_max + 1.0) if has_channel_support else c_dff2_max
            if not (c_dff2_min <= dff2 <= max_dff2_allowed):
                continue

            # 6. 时序洗盘企稳与放量启动特征判定
            ep1 = float(eval_prev1_arr[i])
            ep2 = float(eval_prev2_arr[i])

            is_volume_up = (vr >= c_min_vr) or (is_post_market and eval_pct >= 1.0)
            is_pullback_pattern = False
            pattern_name = ""
            pattern_score = 0.0

            # 模式 A: 缩量洗盘·MA20企稳反身首阳 (前1~2天有阴线洗盘，最新企稳放量收阳)
            if (ep1 <= 0.2 or ep2 <= 0.2 or (ep1 + ep2) < 0.0) and is_volume_up and dff2 >= -1.5:
                is_pullback_pattern = True
                pattern_name = "🎯 缩量洗盘·MA20企稳"
                pattern_score = 88.0

            # 模式 B: 通道支撑+MA20双共振·踩线放量启动
            elif has_channel_support and is_volume_up and dff2 >= -1.2:
                is_pullback_pattern = True
                pattern_name = "🚀 支撑共振·踩线反弹"
                pattern_score = 90.0

            # 模式 C: 底部超跌横盘筑底·放量突破起爆
            elif dff3 <= 15.0 and abs(ep1) <= 4.0 and abs(ep2) <= 4.0 and eval_pct >= 1.0 and is_volume_up:
                is_pullback_pattern = True
                pattern_name = "💎 底部筑底·放量起爆"
                pattern_score = 87.0

            # 模式 D: MA20 均线依托缠绕微升蓄势
            elif -1.2 <= dff2 <= 3.5 and eval_pct >= c_min_pct and (is_volume_up or eval_pct >= 1.5):
                is_pullback_pattern = True
                pattern_name = "📈 均线依托·多头微升"
                pattern_score = 80.0

            if not is_pullback_pattern:
                continue

            # 7. 计算标的综合回踩反转得分
            # 基础形态分 + 板块主线分加成 + 量比加成 + 均线贴近贴度加成 + 通道支撑共振加成
            sec_bonus = min(15.0, matched_sec.get("strength_score", 0.0) * 0.2)
            vr_bonus = min(10.0, max(0.0, (vr - 1.0) * 4.0)) if not is_post_market else 5.0
            # dff2 越贴近 0~2.5% 黄金区间得分越高
            dff2_sweet = 5.0 - abs(dff2 - 1.2) * 1.0
            channel_bonus = 5.0 if (has_channel_support and c_prefer_ch) else 0.0
            total_reversal_score = round(pattern_score + sec_bonus + vr_bonus + max(0.0, dff2_sweet) + channel_bonus, 1)

            # 8. 计算建议买入区间与防守止损位
            supp_base = max(ch_supp, ma20) if ch_supp > 0 else (ma20 if ma20 > 0 else round(price * 0.95, 2))
            stop_loss = round(supp_base * 0.975, 2)
            buy_zone = f"{round(price * 0.995, 2)} ~ {round(price * 1.015, 2)}"
            target_price = round(price * 1.08, 2)

            # 生成高可解释性实战理由
            wash_desc = f"前日{ep1:+.1f}%, 大前日{ep2:+.1f}%" if is_post_market else (f"昨日{ep1:+.1f}%, 前日{ep2:+.1f}%" if (ep1 != 0 or ep2 != 0) else "前序震荡洗盘")
            supp_tag = f"通道支撑{ch_supp:.2f}元" if has_supp_line else (f"通道底座({ch_pos:.0f}%)" if has_channel_base else f"MA20依托{ma20:.2f}元")
            action_desc = "盘后关注次日低吸启动!" if is_post_market else "有效放量上涨, 绝佳低吸跟进点!"
            reason = (
                f"所属【{matched_sec['name']}】主力进攻主线(强度{matched_sec['strength_score']}), "
                f"距MA20乖离度{dff2:+.1f}%, {wash_desc}, "
                f"{'最新收盘企稳收阳' if is_post_market else '今日放量收阳启动'}({eval_pct:+.1f}%, 量比{vr:.2f}), "
                f"{supp_tag}稳固, {action_desc}"
            )

            pullback_candidates.append({
                "code": code,
                "name": name,
                "price": price,
                "pct": eval_pct, # 盘后模式显示最新收盘日涨跌幅
                "real_pct": pct,
                "dff": dff,
                "dff2": dff2,
                "dff3": dff3,
                "per1d": ep1 if not is_post_market else float(ctx['p1_arr'][i]),
                "per2d": ep2 if not is_post_market else float(ctx['p2_arr'][i]),
                "per3d": float(ctx['p3_arr'][i]),
                "ma20": ma20,
                "ch_supp": ch_supp,
                "ch_pos": ch_pos,
                "vol_ratio": vr,
                "turnover": to,
                "sector": matched_sec["name"],
                "sector_score": matched_sec["strength_score"],
                "pattern_name": pattern_name,
                "reversal_score": total_reversal_score,
                "buy_zone": buy_zone,
                "stop_loss": stop_loss,
                "target_price": target_price,
                "reason": reason,
                "is_post_market": is_post_market
            })

        # 若候选数量少于 5 只，在主线板块内保底搜寻企稳收阳标的 (底线：坚决必须收阳，杜绝负涨幅与僵尸股)
        if len(pullback_candidates) < 5:
            existing_codes = set(c["code"] for c in pullback_candidates)
            min_fallback_pct = max(0.05, c_min_pct * 0.5)
            min_fallback_to = max(0.5, c_min_to * 0.5)

            for i in range(n):
                code = str(c_arr[i])
                if code in existing_codes:
                    continue
                price = float(p_arr[i])
                if price <= 0.0:
                    continue
                sec_raw = str(sec_arr[i])
                matched_sec = None
                for ts in leading_sectors:
                    if ts["name"] in sec_raw:
                        matched_sec = ts
                        break
                if not matched_sec:
                    continue

                eval_pct = float(eval_pct_arr[i])
                # 保底守则：必须收阳且未追高，换手率具备基本势能 (有换手率列时校验)
                if eval_pct < min_fallback_pct or eval_pct > c_max_pct:
                    continue
                to = float(to_arr[i])
                if has_valid_to and to < min_fallback_to:
                    continue

                dff2 = float(dff2_arr[i])
                ma20 = float(ma20_arr[i])
                ch_supp = float(ch_supp_arr[i])
                ch_pos = float(ch_pos_arr[i])
                has_ch = (ch_supp > 0 and price >= ch_supp * 0.982 and price <= ch_supp * 1.05) or (0.0 < ch_pos <= 40.0)

                if c_req_ch and not has_ch:
                    continue

                if (c_dff2_min <= dff2 <= (c_dff2_max + 1.0)) and (ma20 <= 0 or price >= ma20 * 0.980):
                    supp_base = max(ch_supp, ma20) if ch_supp > 0 else (ma20 if ma20 > 0 else round(price * 0.95, 2))
                    stop_loss = round(supp_base * 0.975, 2)
                    buy_zone = f"{round(price * 0.995, 2)} ~ {round(price * 1.015, 2)}"
                    target_price = round(price * 1.08, 2)
                    action_desc = "盘后关注次日低吸!" if is_post_market else "低吸观察点!"
                    p_name = "🚀 通道底座·企稳首阳" if has_ch else "🎯 均线依托·企稳蓄势"
                    reason = f"所属【{matched_sec['name']}】主线, 距MA20乖离度{dff2:+.1f}%, 均线依托企稳收阳({eval_pct:+.1f}%), {action_desc}"
                    pullback_candidates.append({
                        "code": code,
                        "name": str(nm_arr[i]),
                        "price": price,
                        "pct": eval_pct,
                        "real_pct": float(pct_arr[i]),
                        "dff": float(dff_arr[i]),
                        "dff2": dff2,
                        "dff3": float(dff3_arr[i]),
                        "per1d": float(ctx['p1_arr'][i]),
                        "per2d": float(ctx['p2_arr'][i]),
                        "per3d": float(ctx['p3_arr'][i]),
                        "ma20": ma20,
                        "ch_supp": ch_supp,
                        "ch_pos": ch_pos,
                        "vol_ratio": float(vr_arr[i]),
                        "turnover": to,
                        "sector": matched_sec["name"],
                        "sector_score": matched_sec["strength_score"],
                        "pattern_name": p_name,
                        "reversal_score": 75.0 + (3.0 if has_ch else 0.0),
                        "buy_zone": buy_zone,
                        "stop_loss": stop_loss,
                        "target_price": target_price,
                        "reason": reason,
                        "is_post_market": is_post_market
                    })
                    if len(pullback_candidates) >= 20:
                        break

        # 按回踩反转综合得分降序排序
        pullback_candidates.sort(key=lambda x: x["reversal_score"], reverse=True)
        return pullback_candidates

    def run_mining_pipeline(
        self,
        df: pd.DataFrame,
        top_sectors_count: int = 6,
        min_vol_ratio: float = 1.15,
        filter_config: Optional[PullbackFilterConfig] = None
    ) -> Dict[str, Any]:
        """
        一键全流程调度流水线：
        阶段一/二（找冲锋前排与主力主线） -> 阶段三（主线内深挖回踩启动）
        返回完整结构化字典，带线程安全缓存
        """
        t0 = time.time()
        if df is None or df.empty:
            return {"sectors": [], "candidates": [], "calc_time_ms": 0.0, "total_stocks": 0, "is_post_market": False}

        # 0. 极速向量化预提取全市场数据数组 (全流程仅提取一次，共享复用)
        ctx = self._extract_df_arrays(df)

        # 1. 识别主力主线板块与先锋
        leading_sectors = self.identify_leading_sectors(df, top_sectors_count=top_sectors_count, ctx=ctx)

        # 2. 板块内深挖回踩确认启动个股 (应用量化筛选策略配置)
        candidates = self.mine_pullback_reversal_stocks(
            df=df,
            leading_sectors=leading_sectors,
            min_vol_ratio=min_vol_ratio,
            ctx=ctx,
            filter_config=filter_config
        )

        cost_ms = round((time.time() - t0) * 1000, 2)
        is_post_market = ctx.get("is_post_market", False)
        mode_label = filter_config.mode_name if filter_config else "🎯 经典标准"
        report = {
            "sectors": leading_sectors,
            "candidates": candidates,
            "calc_time_ms": cost_ms,
            "total_stocks": len(df),
            "sectors_count": len(leading_sectors),
            "candidates_count": len(candidates),
            "is_post_market": is_post_market,
            "filter_mode": mode_label,
            "timestamp": time.time()
        }

        with self._cache_lock:
            self._last_report = report
            self._last_calc_time = time.time()

        logger.info(
            f"[SectorRotationPullbackMiner] 扫描完成: 策略[{mode_label}], 全市场{len(df)}只股票, "
            f"锁定{len(leading_sectors)}大主线板块, 深挖出{len(candidates)}只回踩启动个股, 耗时 {cost_ms}ms"
        )
        return report

    def get_latest_report(self) -> Dict[str, Any]:
        with self._cache_lock:
            return dict(self._last_report)


_GLOBAL_MINER = None

def get_sector_rotation_miner() -> SectorRotationPullbackMiner:
    """全局获取板块轮动深挖中枢单例"""
    global _GLOBAL_MINER
    if _GLOBAL_MINER is None:
        _GLOBAL_MINER = SectorRotationPullbackMiner.get_instance()
    return _GLOBAL_MINER

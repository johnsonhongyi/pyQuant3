# -*- coding: utf-8 -*-
"""
ats/capital_dragon_engine.py — ATS 资金趋势与真龙辨识度核心量化引擎 (SSOT)
=============================================================================
职责定位：
1. 【资金流向与流动性深度度量】：
   - 全市场成交额分级：超大容量中军 (>=15亿/Top30)、主流活跃 (3~15亿)、微盘孤狼 (<1亿降权)；
   - 换手率、量比与主力资金沉淀度量；
2. 【主线板块资金集聚识别】：
   - 聚合板块总成交额、上涨比率、涨停梯队集聚度，甄别市场前 3 大核心增量主线；
3. 【真龙四维角色精准画像】：
   - 【👑 空间高度龙】：全市场连板最高、情绪风向标 (对接 LimitUpEngine)；
   - 【🛡️ 趋势容量中军】：大成交额容量龙头、自适应通道多头向上、机构游资合力底座；
   - 【🚀 主线板块先锋】：Top 核心主线最早涨停/拔起攻坚的领头羊；
   - 【💎 弱转强卡位龙】：分歧转一致、竞价/开盘放量逆袭的接力龙；
4. 【资金趋势买点决策与诱多铁壁拦截】：
   - 分歧低吸点 (VWAP/通道支撑)、放量突破确认点、中军缩量企稳点；
   - 识别并精准拦截【⚠️ 孤狼脉冲】与【⛔ 破位诱多】。
"""

import os
import time
import math
import logging
import threading
from typing import Dict, List, Tuple, Optional, Any, Set
import pandas as pd
import numpy as np

from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("CapitalDragonEngine")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "" or val == "-" or val == "--":
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clean_code(c: Any) -> str:
    s = str(c).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else s


def is_index_or_fund(code: Any, name: Any = "") -> bool:
    """
    判断标的是否属于指数、ETF或大盘综合指数，纯化个股龙头中枢 (排除 399xxx, 999xxx, 899xxx, 000001等)
    严格区分深市个股与指数代码，杜绝将 000852(石化机械)、000010(*ST美丽) 等深市个股误判为指数
    """
    raw_s = str(code).strip().lower()
    c = _clean_code(code)
    nm = str(name).strip() if name is not None else ""

    # 1. 常见指数代码前缀 (深证指数 399xxx, 通达信/上证指数 999xxx, 北证指数 899xxx)
    if c.startswith(("399", "999", "899")):
        return True

    # 2. 带有显式指数前缀的代码 (如 sh000001, sh000300, sh000016, sh000905, sh000852, sh000010)
    if raw_s.startswith("sh") and c in ("000001", "000300", "000016", "000905", "000852", "000010"):
        return True

    # 3. 常见指数/板块名称特征 (如包含“指数”、“成指”、“综指”、“ETF”等关键字)
    if nm:
        for kw in ("指数", "成指", "综指", "ETF", "北证50", "科创50", "上证50", "中小100", "创业板指", "沪深300", "中证500", "中证1000", "上证180"):
            if kw in nm:
                return True

    # 4. 纯 6 位数字代码 000001：若名称含“平安”或“银行”，或前缀为 sz 则为个股；仅当名称含“上证”或代码为 999999 时才为指数
    if c == "000001":
        if nm and ("银行" in nm or "平安" in nm):
            return False
        if "上证" in nm or raw_s.startswith("sh"):
            return True
        return False  # 纯代码 000001 且无明确上证标识时默认为平安银行个股，避免污染

    # 其余纯数字 000xxx、001xxx、002xxx、003xxx 均为深市 A 股 (如 000852 石化机械, 000010 *ST美丽)
    return False


# 权威官方大盘与核心综合指数代码集合 (主要指数置顶梯队)
MAJOR_INDEX_CODES = {
    '999999', '000001', '399001', '399006', '399005', '899050',
    '000300', '399300', '000016', '000688', '399688', '000905', '399905', '000852'
}


def is_major_index(code: Any, name: Any = "") -> bool:
    """判定标的是否属于大盘核心指数 (上证/深证/创业板/中小100/北证50/沪深300等)"""
    raw_s = str(code).strip().lower()
    c = _clean_code(code)
    nm = str(name).strip() if name else ""

    # 1. 检查是否在权威核心指数代码池中
    if c in MAJOR_INDEX_CODES:
        # 纯指数代码前缀：999xxx (上证指数), 399xxx (深证/创业板/中小100), 899xxx (北证50)
        if c.startswith(("999", "399", "899")):
            return True
        # 对于 000xxx 系列代码 (如 000001, 000300, 000016, 000905, 000852)：
        # 必须带 sh 前缀，或者名称包含明确指数特征，杜绝误判深市个股 (如 000001 平安银行, 000852 石化机械, 000905 厦门港务)
        if raw_s.startswith("sh"):
            return True
        if nm:
            for kw in ("指数", "成指", "综指", "上证", "中证", "沪深", "科创", "创业板", "北证"):
                if kw in nm:
                    return True
        return False

    return is_index_or_fund(code, name)


def compute_dragon_buy_type_sort_score(
    action_type: str,
    is_dual_accel: bool = False,
    is_gap_accel: bool = False,
    is_open_low_accel: bool = False,
    amount_yi: float = 0.0,
    pct: float = 0.0
) -> float:
    """
    计算资金主线买点类型的绝对量化得分 (对齐天梯形态质量与龙头突击梯队 SSOT):
    👑 梯队 1: 👑双加速买点 (基准 90,000 分，双重主升加速绝对优先)
    🚀 梯队 2: 🚀缺口加速买点 (基准 70,000 分，跳空高开且缺口未补)
    ⚡ 梯队 3: ⚡光脚加速买点 (基准 55,000 分，开盘即最低)
    🔥 梯队 4: 常规强势主升买点 (基准 40,000 分，如 领涨龙头 / 主升趋势加速 / 主线率先冲关 / 启动首板封死)
    🎯 梯队 5: 通道支撑与分歧低吸买点 (基准 25,000 分，如 通道支撑企稳 / 高位分歧低吸 / 顺应主线共振)
    📋 梯队 6: 其它常规观察买点 (基准 10,000 分)
    ⚠️ 梯队 7: 破位诱多/孤狼 (基准 1,000 分)

    同梯队内部微观决胜:
    - 攻击型买点加成 (领涨龙头 +3000, 主升加速 +2000, 冲关/首板 +1500)
    - 涨幅动能加成 (0 ~ 1000 分)
    - 流动性微调加成 (min(500.0, amount_yi * 5.0)，绝不越级压倒形态)
    """
    act = str(action_type or "")
    is_dual = is_dual_accel or ("双加速" in act)
    is_gap = is_gap_accel or ("缺口加速" in act)
    is_open_low = is_open_low_accel or ("光脚加速" in act)

    if is_dual:
        base = 90000.0
    elif is_gap:
        base = 70000.0
    elif is_open_low:
        base = 55000.0
    elif any(k in act for k in ("领涨龙头", "主升趋势加速", "主线率先冲关", "启动首板", "锁仓换手")):
        base = 40000.0
    elif any(k in act for k in ("通道支撑企稳", "高位分歧低吸", "顺应主线共振")):
        base = 25000.0
    elif any(k in act for k in ("破位", "诱多", "孤狼")):
        base = 1000.0
    else:
        base = 10000.0

    action_bonus = 0.0
    if "领涨龙头" in act:
        action_bonus = 3000.0
    elif "主升趋势加速" in act:
        action_bonus = 2000.0
    elif any(k in act for k in ("冲关", "首板", "锁仓")):
        action_bonus = 1500.0
    elif "通道支撑企稳" in act:
        action_bonus = 500.0

    pct_bonus = min(1000.0, max(0.0, pct) * 50.0)
    amt_bonus = min(500.0, max(0.0, amount_yi) * 5.0)

    return round(base + action_bonus + pct_bonus + amt_bonus, 2)


def get_dragon_extra_cols() -> List[str]:
    """获取资金主线与龙头中枢追加的动态自定义列（排除基础列已有的字段，若没有且在 ats_col 中则自动添加）"""
    try:
        from JohnsonUtil import commonTips as cct
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['ch_bc2']
    # 资金主线默认已有基础列（已有则无需重复添加）：
    # 代码(code)、名称(name)、龙头角色(role)、所属主线(sector)、现价(price/close/trade)、
    # 涨幅%(pct/percent)、虚拟量比(vol_ratio/vr)、成交额(amount/amt_yi)、换手率%(turnover)、
    # 资金买点类型(action_type/buy_type)、建议买入区间(buy_zone)、止损参考(stop_loss)、核心逻辑与驱动(reason)
    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'trade', 'pct', 'percent', 'ratio',
        'vol_ratio', 'vr', 'amount', 'amount_yi', 'amt_yi', 'turnover', 'turnover_rate',
        'action_type', 'buy_type', 'role', 'sector', 'buy_zone', 'stop_loss', 'reason'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_dragon_table_headers(extra_cols: Optional[List[str]] = None) -> List[str]:
    """获取资金主线表格标准表头字段名称列表（在资金买点类型后面平滑嵌入自定义列）"""
    if extra_cols is None:
        extra_cols = get_dragon_extra_cols()
    try:
        from JohnsonUtil import commonTips as cct
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}
    base_pre = [
        "代码", "名称", "龙头角色", "所属主线", "现价", "涨幅%", "虚拟量比",
        "成交额(亿)", "换手率%", "资金买点类型"
    ]
    extra_headers = [col_map.get(c, col_map.get(c.lower(), c.upper())) for c in extra_cols]
    base_post = ["建议买入区间", "止损参考", "核心逻辑与驱动"]
    return base_pre + extra_headers + base_post


class CapitalDragonEngine:
    """
    资金趋势与主线龙头核心量化引擎 (单例)
    """
    _instance: Optional['CapitalDragonEngine'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'CapitalDragonEngine':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._cached_report: Dict[str, Any] = {}
        self._cached_time: float = 0.0
        self._cached_df_len: int = 0
        self._cached_df_first_code: str = ""
        self._cache_lock = threading.RLock()
        self._dragon_codes_set: Set[str] = set()
        self._trap_codes_set: Set[str] = set()
        # 实时指数行情缓存 (完全由 TDX API 真实拉取填充，严禁伪造硬编码数据)
        self._index_data_cache: Dict[str, Dict[str, float]] = {}
        self._index_cache_ts: float = 0.0

        # ─── 大盘摘要后台独立线程缓存（主线程只读，0阻塞）─────────────────────────
        # _bg_market_summary_cache: 最新计算完成的摘要，主线程只读（无锁读取可接受）
        # _bg_market_summary_ts: 缓存写入时间戳
        # _bg_updater_running: 防止重复启动后台线程
        self._bg_market_summary_cache: Dict[str, Any] = {}
        self._bg_market_summary_ts: float = 0.0
        self._bg_updater_running: bool = False
        self._bg_updater_lock = threading.Lock()

    def get_cached_report(self, max_age: float = 5.0, df_check: Optional[pd.DataFrame] = None, fallback_stale: bool = False) -> Optional[Dict[str, Any]]:
        """获取最近缓存的分析报告 (零开销，极速，支持 fallback_stale 宽松回退模式避免主线程卡死)"""
        with self._cache_lock:
            if self._cached_report:
                age = time.time() - self._cached_time
                if age <= max_age:
                    if df_check is not None and getattr(self, '_cached_df_len', 0) > 0:
                        # 仅在数据集长度剧烈突变 (>50%) 时视作失效，轻微波动不击穿缓存
                        diff_ratio = abs(len(df_check) - self._cached_df_len) / max(self._cached_df_len, 1)
                        if diff_ratio > 0.5:
                            return None
                    return dict(self._cached_report)
                if fallback_stale and age <= 180.0:
                    # 容忍 180 秒内的陈旧缓存，保障 UI 交互与排序 100% 丝滑响应
                    return dict(self._cached_report)
        return None

    def _fetch_tdx_index_data(self, index_codes: List[str]) -> Dict[str, Dict[str, float]]:
        """
        使用通达信原生 TDX API 接口 (TDXRealtimeFetcher) 获取大盘综合指数真实成交额与盘口数据 (带 3 秒轻量防抖缓存)
        针对 399xxx (深市指数), 999xxx (通达信沪指), 899xxx (北证50), 000001 (上证指数), 159915 等标的
        """
        now = time.time()
        tdx_intv = float(getattr(cct, 'ats_tdx_interval', 5.0) or 5.0)
        if self._index_data_cache and (now - self._index_cache_ts < tdx_intv):
            return dict(self._index_data_cache)

        results = dict(self._index_data_cache)

        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            fetcher = TDXRealtimeFetcher.get_instance()

            # 核心基准指数强制优先保证 (通达信市场划分: 1=上交所, 0=深交所, 2=北交所)
            core_reqs = [
                (1, '999999'), (1, '000001'), (0, '399001'),
                (0, '399006'), (2, '899050'), (0, '399005'), (0, '159915')
            ]
            seen_pairs = set()
            req_pairs = []
            for mkt, cd in core_reqs:
                if (mkt, cd) not in seen_pairs:
                    seen_pairs.add((mkt, cd))
                    req_pairs.append((mkt, cd))

            for c in index_codes:
                if c is None:
                    continue
                c_clean = _clean_code(c)
                if not c_clean or len(c_clean) != 6 or not c_clean.isdigit():
                    continue
                if c_clean.startswith(('89', '920', '83', '87', '88', '43', '82')):
                    mkt = 2  # 北交所 (如 899050 北证50)
                elif c_clean.startswith(('60', '68', '99', '11', '51', '58', '90')):
                    mkt = 1  # 上交所 (如 999999 上证指数, 510300 ETF)
                elif c_clean == '000001':
                    mkt = 1  # 000001 上证指数在通达信行情API中属于上海市场
                else:
                    mkt = 0  # 深交所 (如 399001 深成指, 399006 创业板指, 399005 中小100, 159915 创业板ETF)
                if (mkt, c_clean) not in seen_pairs:
                    seen_pairs.add((mkt, c_clean))
                    req_pairs.append((mkt, c_clean))

            if req_pairs:
                with fetcher._conn_lock:
                    if not fetcher._is_connected or not fetcher.api:
                        fetcher.connect()
                    if fetcher._is_connected and fetcher.api:
                        chunk_size = 10
                        all_quotes = []
                        for idx_chk in range(0, len(req_pairs), chunk_size):
                            chk = req_pairs[idx_chk:idx_chk + chunk_size]
                            try:
                                quotes = fetcher.api.get_security_quotes(chk)
                                if quotes:
                                    all_quotes.extend(quotes)
                                else:
                                    # 单只回退探查，杜绝单只不可识别代码击穿整个批次
                                    for single_p in chk:
                                        try:
                                            sq = fetcher.api.get_security_quotes([single_p])
                                            if sq:
                                                all_quotes.extend(sq)
                                        except Exception:
                                            pass
                            except Exception:
                                for single_p in chk:
                                    try:
                                        sq = fetcher.api.get_security_quotes([single_p])
                                        if sq:
                                            all_quotes.extend(sq)
                                    except Exception:
                                        pass

                        if all_quotes:
                            for q in all_quotes:
                                q_code = str(q.get('code', '')).strip().zfill(6)
                                raw_amt = float(q.get('amount', 0.0) or 0.0)
                                # 通达信 TDX 原生 API 返回的 amount 永远是以【元】为单位，严格除以 1e8 转换为亿元
                                amt_yi = raw_amt / 1e8
                                p = float(q.get('price', 0.0) or 0.0)
                                if amt_yi > 0:
                                    val_dict = {
                                        'amount_yi': round(amt_yi, 2),
                                        'price': p,
                                        'last_close': float(q.get('last_close', 0.0) or 0.0),
                                        'vol': float(q.get('vol', 0.0) or 0.0)
                                    }
                                    results[q_code] = val_dict
                                    results[f"sh{q_code}"] = val_dict
                                    results[f"sz{q_code}"] = val_dict
                                    results[f"bj{q_code}"] = val_dict

                                    # 999999 与 000001 (上证指数) 跨代码全映射支持
                                    if q_code in ('999999', '000001'):
                                        results['999999'] = val_dict
                                        results['000001'] = val_dict
                                        results['sh999999'] = val_dict
                                        results['sh000001'] = val_dict

            self._index_data_cache = results
            self._index_cache_ts = now
        except Exception as e_tdx:
            logger.warning(f"[CapitalDragonEngine] TDX API fetch error: {e_tdx}")

        return results

    def _get_virtual_vol_ratio(self, df: pd.DataFrame) -> pd.Series:
        """
        获取或计算全市场的虚拟量比序列 (SSOT)
        支持：
        1. 直接从 df 的 vol_ratio 列提取；
        2. 若 volume 列存在且中位数/均值在 0~20 之间（已被 calc_compute_volume 转换为虚拟量比强度），直接复用；
        3. 对仍为 0 (<=0.05) 的股票，结合原始成交量 (vol/volume) 与昨量 (lastv1d/last6vol) 按交易进度动态投影放大；
        4. 兜底返回 1.0 (基准量比)，严禁出现 0.00x。
        """
        if df is None or df.empty:
            return pd.Series(1.0, index=df.index if df is not None else [])

        res_vr = pd.Series(1.0, index=df.index)
        has_extracted = False

        # 优先 1: 读取 vol_ratio / vr / volume_ratio
        for col in ('vol_ratio', 'vr', 'volume_ratio'):
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                if (s > 0).any():
                    res_vr = s.copy()
                    has_extracted = True
                    break

        # 优先 2: 检查 volume 列是否已是虚拟量比（系统 data_utils.calc_compute_volume 注入特征：数值通常在 0.1 ~ 30 之间）
        if not has_extracted and 'volume' in df.columns:
            s_vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0)
            if 0 < s_vol.max() <= 50.0 and s_vol.quantile(0.9) <= 15.0:
                res_vr = s_vol.copy()
                has_extracted = True

        # 优先 3: 对仍为 0 或极其微小 (<= 0.05) 的股票，结合日内交易时间比例进行向量化动态投影
        need_calc_mask = (res_vr <= 0.05)
        if need_calc_mask.any():
            try:
                from JohnsonUtil import commonTips as cct
                ratio_t = float(cct.get_work_time_ratio(resample='d'))
            except Exception:
                ratio_t = 1.0
            ratio_t = max(0.05, min(ratio_t, 1.0))

            raw_vol = None
            for v_col in ('vol', 'volume', 'trade_vol'):
                if v_col in df.columns:
                    cand = pd.to_numeric(df[v_col], errors='coerce').fillna(0.0)
                    if (cand > 0).any():
                        raw_vol = cand
                        break

            base_vol = None
            for b_col in ('lastv1d', 'last6vol', 'l6vol', 'prev_vol', 'vol_ma5'):
                if b_col in df.columns:
                    cand = pd.to_numeric(df[b_col], errors='coerce').fillna(0.0)
                    if (cand > 0).any():
                        base_vol = cand.replace(0.0, np.nan)
                        break

            if raw_vol is not None and base_vol is not None:
                proj_vol = raw_vol / ratio_t
                calc_vr = (proj_vol / base_vol).fillna(1.0).clip(0.1, 50.0)
                res_vr.loc[need_calc_mask] = calc_vr.loc[need_calc_mask]

        # 终极大兜底：所有 <= 0.05 的值强制置为 1.0 (正常基准)，杜绝显示 0.00x！
        res_vr = res_vr.replace(0.0, 1.0)
        res_vr[res_vr <= 0.05] = 1.0
        return res_vr.clip(0.1, 50.0).round(2)

    def analyze_capital_dragon_universe(
        self,
        df_all: Optional[pd.DataFrame],
        sh_pct: float = 0.0,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        全量分析全市场资金分布、核心主线、龙头角色画像与资金趋势买点。
        带 1.0 秒轻量防抖缓存，避免高频 IPC 广播下重复沉重运算。
        """
        if df_all is None or df_all.empty:
            with self._cache_lock:
                return dict(self._cached_report)

        now = time.time()
        if not force and (now - self._cached_time < 1.0) and self._cached_report:
            with self._cache_lock:
                return dict(self._cached_report)

        t0 = time.time()

        # 1. 规范化提取基础字段 (向量化处理，超高速)
        df = df_all.copy(deep=False)
        close_col = 'close' if 'close' in df.columns else ('price' if 'price' in df.columns else None)
        pct_col = 'percent' if 'percent' in df.columns else ('pct' if 'pct' in df.columns else None)
        amt_col = 'amount' if 'amount' in df.columns else ('turnover' if 'turnover' in df.columns else None)

        if not close_col or not pct_col:
            return {}

        # 提取连板天梯数据
        ladder_dict = {}
        try:
            from ats.limit_up_engine import LimitUpEngine
            lue = LimitUpEngine.get_instance()
            radar_recs = lue.get_intraday_radar_records(current_df=df)
            for r in radar_recs:
                c = _clean_code(r.get("code", ""))
                if c:
                    ladder_dict[c] = r
        except Exception as e_lue:
            logger.debug(f"[CapitalDragonEngine] Load limit up records error: {e_lue}")

        # 2. 向量化预计算资金与涨幅指标
        codes_series = pd.Series([_clean_code(c) for c in df.index], index=df.index)
        prices = pd.to_numeric(df[close_col], errors='coerce').fillna(0.0)
        pcts = pd.to_numeric(df[pct_col], errors='coerce').fillna(0.0)
        
        # 成交金额转换 (统一转为亿元)
        amts_yi = pd.Series(0.0, index=df.index)
        if amt_col:
            raw_amt = pd.to_numeric(df[amt_col], errors='coerce').fillna(0.0)
            # 若原始值已经小于 10000 说明已经是亿元或万元单位，根据均值自适应判断
            if raw_amt.max() > 1e7:
                amts_yi = raw_amt / 1e8
            elif raw_amt.max() > 1000:
                amts_yi = raw_amt / 10000.0
            else:
                amts_yi = raw_amt

        # 换手率
        turnover_s = pd.Series(0.0, index=df.index)
        for t_col in ('turnover_rate', 'turnover', 'hsl', 'ratio'):
            if t_col in df.columns:
                cand = pd.to_numeric(df[t_col], errors='coerce').fillna(0.0)
                if 0.0 < cand.max() <= 100.0:
                    turnover_s = cand
                    break

        # 板块分类列
        sec_col = next((c for c in ('category', 'industry', 'concept') if c in df.columns), None)
        sectors = df[sec_col].astype(str).str.strip() if sec_col else pd.Series('', index=df.index)

        # 多周期特征
        def _get_series(col_names):
            for c in col_names:
                if c in df.columns:
                    return pd.to_numeric(df[c], errors='coerce').fillna(0.0)
            return pd.Series(0.0, index=df.index)

        dff_s = _get_series(['dff', 'DFF'])
        dff2_s = _get_series(['dff2', 'DFF2'])
        dff3_s = _get_series(['dff3', 'DFF3'])
        ch_supp_s = _get_series(['ch_supp', 'ch_lower'])
        ma20_s = _get_series(['ma20d', 'ma20', 'MA20'])

        # 提取开盘价、最低价、昨收与昨日最高价用于分时加速形态量化判定
        open_s = _get_series(['open', 'open_price', 'Open'])
        low_s = _get_series(['low', 'low_price', 'Low'])
        last_c_s = _get_series(['last_close', 'lastp', 'pre_close', 'close_last', 'last_c'])
        yesterday_h_s = _get_series(['lasth1d', 'lasth', 'yesterday_high', 'last_high'])

        # 昨收兜底计算
        missing_lc = (last_c_s <= 0.0) & (prices > 0.0)
        if missing_lc.any():
            calc_lc = prices[missing_lc] / (1.0 + pcts[missing_lc] / 100.0)
            last_c_s.loc[missing_lc] = calc_lc.round(2)

        missing_yh = (yesterday_h_s <= 0.0)
        if missing_yh.any():
            yesterday_h_s.loc[missing_yh] = last_c_s.loc[missing_yh]

        # 提取全市场系统的虚拟量比序列 (SSOT)
        vol_ratio_s = self._get_virtual_vol_ratio(df)
        try:
            from JohnsonUtil import commonTips as cct
            ratio_t = float(cct.get_work_time_ratio(resample='d'))
        except Exception:
            ratio_t = 1.0
        ratio_t = max(0.05, min(ratio_t, 1.0))

        # 3. 统计主线板块资金集聚度 (板块聚合时过滤大盘指数以纯化板块属性，个股/指数候选池保留全部标的)
        sector_stats = {}
        names_list = df['name'].astype(str).tolist() if 'name' in df.columns else [''] * len(df)
        is_idx_mask = [is_index_or_fund(c, names_list[i]) for i, c in enumerate(codes_series)]
        valid_stock_mask = (prices > 0.0) & (~pd.Series(is_idx_mask, index=df.index))
        valid_all_mask = (prices > 0.0)

        # 针对 399xxx, 999xxx, 899xxx, 000001, 159915 等大盘指数从 TDX 接口获取真实成交额 (TDX API SSOT)
        idx_row_indices = [i for i, is_idx in enumerate(is_idx_mask) if is_idx]
        if idx_row_indices:
            idx_codes_to_fetch = [str(codes_series.iloc[i]).strip() for i in idx_row_indices]
            tdx_idx_data = self._fetch_tdx_index_data(idx_codes_to_fetch)
            for i in idx_row_indices:
                c_clean = str(codes_series.iloc[i]).strip()
                raw_c = str(df.index[i]).strip()
                info = (tdx_idx_data.get(c_clean) or 
                        tdx_idx_data.get(raw_c) or 
                        tdx_idx_data.get(f"sh{c_clean}") or 
                        tdx_idx_data.get(f"sz{c_clean}") or 
                        tdx_idx_data.get(f"bj{c_clean}"))
                if not info and c_clean in ('999999', '000001'):
                    info = tdx_idx_data.get('999999') or tdx_idx_data.get('000001')

                if info:
                    real_amt = info.get('amount_yi', 0.0)
                    if real_amt > 0:
                        amts_yi.iloc[i] = real_amt
                    real_vr = info.get('vol_ratio')
                    if real_vr is not None and real_vr > 0.05 and i < len(vol_ratio_s):
                        vol_ratio_s.iloc[i] = real_vr
                    real_p = info.get('price', 0.0)
                    if real_p > 0 and prices.iloc[i] <= 0:
                        prices.iloc[i] = real_p
                else:
                    logger.debug(f"[CapitalDragonEngine] TDX API did not return quote for index: {c_clean} ({raw_c})")
        
        # 预先向量化计算个股加速结构
        accel_cache = {}
        for idx in df[valid_all_mask].index:
            code_str = codes_series.loc[idx]
            op = float(open_s.loc[idx])
            lp = float(low_s.loc[idx])
            lc = float(last_c_s.loc[idx])
            yh = float(yesterday_h_s.loc[idx])

            # 1. 开盘即最低 / 极小下影加速 (Open is Low / 光脚加速)
            low_diff_pct = round((op - lp) / op * 100.0, 3) if op > 0 else 999.0
            is_open_low = bool(op > 0 and lp > 0 and (lp >= op - 0.015 or low_diff_pct <= 0.15) and (op >= lc * 0.98))

            # 2. 跳空高开且留有跳空缺口加速 (Gap-Up Acceleration / 缺口加速)
            open_jump_pct = round((op - lc) / lc * 100.0, 2) if lc > 0 else 0.0
            is_gap = bool(open_jump_pct >= 0.8 and lp > lc and (yh <= 0 or lp >= yh - 0.015))

            # 结合天梯数据
            ladder_info = ladder_dict.get(code_str, {})
            if ladder_info:
                if ladder_info.get("is_open_low_accel", False):
                    is_open_low = True
                if ladder_info.get("is_gap_accel", False):
                    is_gap = True

            is_dual = bool(is_open_low and is_gap)
            accel_t = ""
            if is_dual:
                accel_t = "👑双加速"
            elif is_gap:
                accel_t = "🚀缺口加速"
            elif is_open_low:
                accel_t = "⚡光脚加速"

            accel_cache[code_str] = {
                "is_open_low": is_open_low,
                "is_gap": is_gap,
                "is_dual": is_dual,
                "accel_tag": accel_t
            }

        for idx in df[valid_stock_mask].index:
            code_str = codes_series.loc[idx]
            sec = sectors.loc[idx]
            if not sec or sec in ('--', 'nan', '未知', '其它', '其他', '0', '0.0', 'None'):
                continue
            amt = float(amts_yi.loc[idx])
            p_val = float(pcts.loc[idx])
            vr_val = float(vol_ratio_s.loc[idx]) if idx in vol_ratio_s.index else 1.0
            
            ac_info = accel_cache.get(code_str, {})
            has_dual = ac_info.get("is_dual", False)
            has_gap = ac_info.get("is_gap", False)
            has_ol = ac_info.get("is_open_low", False)

            # 分割复合板块名 (如 "软件服务;人工智能;大数据")
            sub_secs = [s.strip() for s in sec.replace(';', ',').replace('、', ',').split(',') if s.strip()]
            for s_name in sub_secs[:2]: # 仅取最核心的前2个概念
                if len(s_name) < 2:
                    continue
                if s_name not in sector_stats:
                    sector_stats[s_name] = {
                        "name": s_name,
                        "total_amt_yi": 0.0,
                        "up_count": 0,
                        "limit_up_count": 0,
                        "total_count": 0,
                        "dual_accel_count": 0,
                        "gap_accel_count": 0,
                        "open_low_count": 0,
                        "accel_total_count": 0,
                        "avg_pct": 0.0,
                        "sum_pct": 0.0,
                        "sum_vr_weighted": 0.0,
                        "sum_vr": 0.0,
                        "vol_ratio": 1.0,
                        "proj_amt_yi": 0.0,
                        "leader_code": "",
                        "leader_name": "",
                        "leader_pct": -99.0,
                        "leader_amt_yi": 0.0,
                        "leader_vr": 1.0,
                        "leader_buy_type": ""
                    }
                st = sector_stats[s_name]
                st["total_amt_yi"] += amt
                st["total_count"] += 1
                st["sum_pct"] += p_val
                st["sum_vr_weighted"] += amt * vr_val
                st["sum_vr"] += vr_val
                if p_val > 0.0:
                    st["up_count"] += 1
                if p_val >= 9.5: # 涨停门槛
                    st["limit_up_count"] += 1
                
                # 统计板块内部群起加速能力 (这些显性反应了板块强度能力)
                if has_dual:
                    st["dual_accel_count"] += 1
                elif has_gap:
                    st["gap_accel_count"] += 1
                elif has_ol:
                    st["open_low_count"] += 1

                # 记录板块领涨先锋
                if p_val > st["leader_pct"]:
                    st["leader_pct"] = p_val
                    st["leader_code"] = codes_series.loc[idx]
                    st["leader_name"] = str(df.loc[idx, 'name']) if 'name' in df.columns else ""
                    st["leader_amt_yi"] = amt
                    st["leader_vr"] = vr_val

        # 计算板块综合资金强度得分
        top_sectors = []
        for s_name, st in sector_stats.items():
            if st["total_count"] < 3:
                continue
            st["avg_pct"] = round(st["sum_pct"] / st["total_count"], 2)
            up_ratio = st["up_count"] / st["total_count"]

            # 板块虚拟量比：成交额加权虚拟量比（资金权重优先），无成交额时使用算术平均
            if st["total_amt_yi"] > 0:
                sec_vr = st["sum_vr_weighted"] / st["total_amt_yi"]
            else:
                sec_vr = st["sum_vr"] / max(1, st["total_count"])
            st["vol_ratio"] = round(float(sec_vr), 2)
            st["proj_amt_yi"] = round(float(st["total_amt_yi"] / ratio_t), 1)
            
            # 板块加速结构汇总
            st["accel_total_count"] = st["dual_accel_count"] + st["gap_accel_count"] + st["open_low_count"]
            accel_bonus = min(15.0, (
                st["dual_accel_count"] * 4.0 + 
                st["gap_accel_count"] * 2.5 + 
                st["open_low_count"] * 1.5
            ))

            # 板块资金强度 = 成交额(亿)*0.15 + 涨停数*15 + 平均涨幅*4 + 上涨占比*20 + 虚拟量比加速加分 + 加速结构加分
            vr_bonus = min(15.0, max(0.0, (st["vol_ratio"] - 1.0) * 8.0))
            strength_score = (
                min(40.0, st["total_amt_yi"] * 0.15) +
                st["limit_up_count"] * 15.0 +
                max(0.0, st["avg_pct"]) * 4.0 +
                up_ratio * 20.0 +
                vr_bonus +
                accel_bonus
            )
            st["strength_score"] = round(strength_score, 1)
            
            # 主线评级
            if st["limit_up_count"] >= 3 or (st["strength_score"] >= 65 and st["total_amt_yi"] >= 50.0):
                st["grade"] = "👑 核心主线"
            elif st["limit_up_count"] >= 1 or st["strength_score"] >= 45:
                st["grade"] = "🚀 活跃赛道"
            else:
                st["grade"] = "🟡 轮动分支"
                
            top_sectors.append(st)

        # 按资金强度降序排列，取 Top 5 核心主线
        top_sectors.sort(key=lambda x: x["strength_score"], reverse=True)

        # 4. 全市场龙头多维角色精准画像 (True Dragon Hierarchy)
        dragon_records = []
        dragon_codes_set = set()
        trap_codes_set = set()

        # 计算全市场成交额排名前 35 (容量中军候选池，用于极限性能模式精准遴选，统一基于准确的 amts_yi 排序)
        top_amt_s = amts_yi[valid_all_mask].sort_values(ascending=False)
        top_35_amt_codes = set(str(c).strip().zfill(6) for c in codes_series.loc[top_amt_s.index[:35]].values.ravel())
        extra_cols = get_dragon_extra_cols()

        for idx in df[valid_all_mask].index:
            code_str = codes_series.loc[idx]
            name_str = str(df.loc[idx, 'name']) if 'name' in df.columns else code_str
            price_val = float(prices.loc[idx])
            pct_val = float(pcts.loc[idx])
            amt_yi = float(amts_yi.loc[idx])
            turnover_val = float(turnover_s.loc[idx])
            sec_str = str(sectors.loc[idx])
            
            dff = float(dff_s.loc[idx])
            dff2 = float(dff2_s.loc[idx])
            dff3 = float(dff3_s.loc[idx])
            ch_supp = float(ch_supp_s.loc[idx])
            ma20_val = float(ma20_s.loc[idx])

            # 是否属于 Top 核心主线板块
            matched_main_sec = ""
            for ts in top_sectors[:5]:
                if ts["name"] in sec_str:
                    matched_main_sec = ts["name"]
                    break

            # 不再过滤大盘综合指数与宽基ETF，保留大盘与板块综合指数便于操盘手即时观测全景大势
            clean_sec = sec_str.split(';')[0].split(',')[0].strip() if sec_str not in ('0', '', 'None', 'nan') else ""
            final_sec = matched_main_sec or clean_sec
            if not final_sec:
                final_sec = "综合指数/ETF" if is_index_or_fund(code_str, name_str) else "主流活跃"

            # 提取连板信息
            ladder_info = ladder_dict.get(code_str, {})
            l_days = int(ladder_info.get("limit_days", 0))
            is_limit_up = bool(ladder_info.get("is_limit_up", False) or pct_val >= 9.5)
            bid_amt_yi = float(ladder_info.get("bid_amount_yi", 0.0))
            is_first_limit = bool(ladder_info.get("is_first_board", False) or (is_limit_up and l_days <= 1))

            # 提取加速形态
            ac_info = accel_cache.get(code_str, {})
            accel_tag = ac_info.get("accel_tag", "")
            is_dual_accel = ac_info.get("is_dual", False)
            is_gap_accel = ac_info.get("is_gap", False)
            is_open_low_accel = ac_info.get("is_open_low", False)

            # 趋势通道状态判决
            has_channel_base = (dff2 > 0.0 or dff3 > 0.0 or (ma20_val > 0 and price_val >= ma20_val * 0.98))
            is_channel_down = (dff2 < -5.0 and dff3 < -5.0 and ma20_val > 0 and price_val < ma20_val * 0.95)

            is_idx = is_major_index(code_str, name_str) or is_index_or_fund(code_str, name_str) or final_sec == "综合指数/ETF"

            # ── 💡 铁壁拦截：孤狼脉冲与破位诱多 (核心指数免受个股拦截) ──
            if not is_idx and is_channel_down and not matched_main_sec and not is_limit_up:
                trap_codes_set.add(code_str)
                continue  # 破位诱多，彻底剔除

            if not is_idx and amt_yi < 0.8 and not is_limit_up and (not matched_main_sec or pct_val < 3.0):
                # 成交额不足 8000 万且无板块无涨停的边缘杂毛
                trap_codes_set.add(code_str)
                continue

            # ── 💡 四维真龙画像定位 ──
            dragon_role = ""
            role_priority = 0
            base_action = ""
            action_tip = ""
            buy_zone = ""
            stop_loss = round(price_val * 0.95, 2)
            reason = ""

            # 1. 【👑 空间高度龙】：市场连板天梯标杆 (3板及以上，或全市场最高板)
            if l_days >= 3 or (is_limit_up and l_days >= 2 and l_days == max((r.get('limit_days', 0) for r in ladder_dict.values()), default=0)):
                dragon_role = "👑 空间高度龙"
                role_priority = 100
                if is_limit_up:
                    base_action = "👑 领涨龙头" if is_dual_accel else "🔒 锁仓换手板"
                    buy_zone = f"{price_val:.2f}"
                    action_tip = "情绪空间总龙头，开板可关注分歧换手回封机会"
                    reason = f"市场最高连板梯队 ({l_days}连板), 情绪总标杆, 巨资封单{bid_amt_yi:.2f}亿"
                else:
                    base_action = "💎 高位分歧低吸"
                    buy_zone = f"{round(price_val * 0.97, 2)} ~ {price_val:.2f}"
                    action_tip = "高位分歧承接，关注首阴或日内分时均线低吸机会"
                    reason = f"空间高度龙盘中分歧 ({l_days}板预期), 资金换手承接充分"

            # 2. 【🛡️ 趋势容量中军】：成交额排名前 35 或成交额>=8亿，且通道多头向上的机构游资合力大票 (含大盘宽基ETF)
            elif (code_str in top_35_amt_codes or amt_yi >= 8.0) and has_channel_base:
                dragon_role = "🛡️ 趋势容量中军"
                role_priority = 90
                supp_ref = max(ch_supp, ma20_val) if ch_supp > 0 else (ma20_val if ma20_val > 0 else round(price_val * 0.95, 2))
                stop_loss = round(supp_ref * 0.97, 2)
                
                if pct_val >= 4.0:
                    base_action = "🚀 主升趋势加速"
                    buy_zone = f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                    action_tip = "容量大票放量主升，顺势持股或回踩分时均线加仓"
                    reason = f"全市场成交额巨量排头 (成交{amt_yi:.1f}亿), 多头通道稳健向上 (DFF2={dff2:.1f})"
                else:
                    base_action = "🎯 通道支撑企稳"
                    role_priority = 76  # 缩量企稳防守中军，基准优先级适度让位给主升加速与主线先锋
                    buy_zone = f"{supp_ref:.2f} ~ {round(supp_ref * 1.02, 2)}"
                    action_tip = "大票缩量回踩通道中轨/支撑位，低吸性价比极高"
                    reason = f"百亿级别容量中军 (成交{amt_yi:.1f}亿) 回踩多头支撑位 ({supp_ref:.2f}元), 机构承接有力"

            # 3. 【🚀 主线板块先锋】：Top 3 核心主线最早拔起或涨停的领跑者
            elif matched_main_sec and (is_limit_up or (pct_val >= 5.0 and code_str == top_sectors[0]["leader_code"])):
                dragon_role = "🚀 主线板块先锋"
                role_priority = 85
                buy_zone = f"{price_val:.2f}" if is_limit_up else f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                stop_loss = round(price_val * 0.96, 2)
                base_action = "👑 领涨龙头" if (is_limit_up or pct_val >= 8.0) else "⚡ 主线率先冲关"
                action_tip = "核心主线带队大哥，享受板块助攻溢价"
                reason = f"所属【{matched_main_sec}】核心主线率先拔起封板 (+{pct_val:.1f}%), 带动整个赛道爆发"

            # 4. 【💎 弱转强/分歧转一致】：主线内强势换手首板或跳空拔起
            elif is_limit_up and is_first_limit and amt_yi >= 2.0:
                dragon_role = "💎 强势换手首板"
                role_priority = 80
                buy_zone = f"{price_val:.2f}"
                stop_loss = round(price_val * 0.95, 2)
                base_action = "👑 领涨龙头" if is_dual_accel else "🔥 启动首板封死"
                action_tip = "量价结构健康的首板标的，次日关注接力一进二"
                reason = f"成交额达标 (成交{amt_yi:.1f}亿/换手{turnover_val:.1f}%), 封板坚决"

            # 5. 【📈 核心主线高辨识度标的】：主线涨幅前列且成交活跃
            elif matched_main_sec and pct_val >= 4.0 and amt_yi >= 2.5:
                dragon_role = "📈 主线共振中坚"
                role_priority = 70
                buy_zone = f"{round(price_val * 0.98, 2)} ~ {price_val:.2f}"
                stop_loss = round(price_val * 0.96, 2)
                base_action = "🌊 顺应主线共振"
                action_tip = "跟随核心主线放量上攻，注意高抛低吸"
                reason = f"所属【{matched_main_sec}】主流赛道放量走强 (成交{amt_yi:.1f}亿, 涨幅+{pct_val:.1f}%)"

            if is_idx and not dragon_role:
                dragon_role = "🛡️ 趋势容量中军"
                role_priority = 98
                supp_ref = max(ch_supp, ma20_val) if ch_supp > 0 else (ma20_val if ma20_val > 0 else round(price_val * 0.95, 2))
                stop_loss = round(supp_ref * 0.97, 2)
                base_action = "🎯 通道支撑企稳" if pct_val < 4.0 else "🚀 主升趋势加速"
                action_tip = "权威大盘与核心综合指数，观测全市场风向标与宏观流动性"
                reason = f"权威大盘核心指数 (成交{amt_yi:.1f}亿, 涨跌幅{pct_val:+.2f}%)，全景大势锚点"
                buy_zone = f"{supp_ref:.2f} ~ {round(supp_ref * 1.02, 2)}"

            if dragon_role:
                dragon_codes_set.add(code_str)
                vr_val = float(vol_ratio_s.loc[idx]) if idx in vol_ratio_s.index else 1.0

                # 结合分时结构形态加速能力融合买点类型 (对齐龙头突击与天梯: 👑双加速·👑 领涨龙头 / 🚀缺口加速·👑 领涨龙头 等)
                if accel_tag:
                    action_type = f"{accel_tag}·{base_action}"
                    if is_dual_accel:
                        role_priority += 25
                        reason = f"【👑双加速主升结构】{reason}"
                    elif is_gap_accel:
                        role_priority += 15
                        reason = f"【🚀缺口加速(跳空未补)】{reason}"
                    elif is_open_low_accel:
                        role_priority += 8
                        reason = f"【⚡光脚加速(开盘即最低)】{reason}"
                else:
                    action_type = base_action

                # 计算买点类型的绝对量化得分 (对齐天梯形态质量与龙头突击梯队 SSOT)
                buy_type_score = compute_dragon_buy_type_sort_score(
                    action_type=action_type,
                    is_dual_accel=is_dual_accel,
                    is_gap_accel=is_gap_accel,
                    is_open_low_accel=is_open_low_accel,
                    amount_yi=amt_yi,
                    pct=pct_val
                )

                # 提取动态自定义列 (ats_col)
                extra_dict = {}
                for ec in extra_cols:
                    val_raw = None
                    for k in (ec, ec.lower(), ec.upper()):
                        if k in df.columns:
                            val_raw = df.loc[idx, k]
                            break
                    # 若 df 中无该列，尝试回退使用引擎内部已推导的特征 (如 dff, dff2, dff3)
                    if val_raw is None:
                        ec_l = ec.lower()
                        if ec_l == 'dff':
                            val_raw = dff
                        elif ec_l == 'dff2':
                            val_raw = dff2
                        elif ec_l == 'dff3':
                            val_raw = dff3
                    extra_dict[ec] = cct.format_col_value(ec, val_raw)

                rec = {
                    "code": code_str,
                    "name": name_str,
                    "role": dragon_role,
                    "priority": role_priority,
                    "buy_type_sort_score": buy_type_score,
                    "sector": final_sec,
                    "price": price_val,
                    "pct": pct_val,
                    "amount_yi": round(amt_yi, 2),
                    "vol_ratio": round(vr_val, 2),
                    "turnover": round(turnover_val, 2),
                    "action_type": action_type,
                    "action_tip": action_tip,
                    "buy_zone": buy_zone,
                    "stop_loss": stop_loss,
                    "reason": reason if vr_val < 2.0 else f"{reason}, 虚拟量比加速({vr_val:.1f}x)",
                    "dff": dff,
                    "dff2": dff2,
                    "dff3": dff3,
                    "limit_days": l_days,
                    "is_limit_up": is_limit_up,
                    "accel_tag": accel_tag,
                    "is_dual_accel": is_dual_accel,
                    "is_gap_accel": is_gap_accel,
                    "is_open_low_accel": is_open_low_accel,
                    "is_top35_amt": (code_str in top_35_amt_codes),
                    "is_index": is_idx,
                    "extra_cols": extra_dict
                }
                for ec, val in extra_dict.items():
                    rec[ec] = val
                dragon_records.append(rec)

        # 回填核心主线 Top Sectors 中先锋个股的资金买点类型 (SSOT)
        dragon_action_map = {d["code"]: d.get("action_type", "") for d in dragon_records}
        for st in top_sectors:
            l_c = st.get("leader_code", "")
            if l_c in dragon_action_map and dragon_action_map[l_c]:
                st["leader_buy_type"] = dragon_action_map[l_c]
            elif l_c:
                ac_info = accel_cache.get(l_c, {})
                tag = ac_info.get("accel_tag", "")
                p_val = st.get("leader_pct", 0.0)
                base_act = "冲板先锋" if p_val >= 9.5 else ("领涨先锋" if p_val >= 5.0 else "领涨突破")
                st["leader_buy_type"] = f"{tag}·{base_act}" if tag else f"⚡ {base_act}"

        def _get_dragon_tier(r):
            if r.get("is_index", False) or is_major_index(r.get("code", ""), r.get("name", "")) or r.get("sector") == "综合指数/ETF":
                return 0
            return 1

        # 1. 优化前的全部 300+ 只全量候选池 (主要指数享有绝对置顶优先级，排在所有个股之上)
        dragon_records_all = list(dragon_records)
        dragon_records_all.sort(
            key=lambda x: (
                1000000 if _get_dragon_tier(x) == 0 else 0,
                x["priority"],
                x.get("buy_type_sort_score", 0.0),
                x["amount_yi"],
                x["pct"]
            ),
            reverse=True
        )

        # 2. 精准收敛池 (开启极限性能模式时生效：主要指数 100% 绝对保留，容量中军严格从 top_35_amt 中精选 Top 20 绝对中军，总池收敛至 Top 50)
        converged = []
        midcap_kept = 0
        for r in dragon_records_all:
            if _get_dragon_tier(r) == 0:
                converged.append(r)
            elif "容量" in r["role"]:
                if r.get("is_top35_amt", False) and midcap_kept < 20:
                    midcap_kept += 1
                    converged.append(r)
            else:
                converged.append(r)
        converged.sort(
            key=lambda x: (
                1000000 if _get_dragon_tier(x) == 0 else 0,
                x["priority"],
                x.get("buy_type_sort_score", 0.0),
                x["amount_yi"],
                x["pct"]
            ),
            reverse=True
        )
        dragon_records_converged = converged[:50]

        report = {
            "timestamp": now,
            "calc_cost_ms": round((time.time() - t0) * 1000, 1),
            "top_sectors": top_sectors[:5],
            "extra_cols": extra_cols,
            "dragon_records": dragon_records_converged,
            "dragon_records_converged": dragon_records_converged,
            "dragon_records_all": dragon_records_all,
            "dragon_codes_set": dragon_codes_set,
            "trap_codes_set": trap_codes_set,
            "space_dragon_count": sum(1 for r in dragon_records_converged if "空间" in r["role"]),
            "midcap_dragon_count": sum(1 for r in dragon_records_converged if "容量" in r["role"]),
            "pioneer_dragon_count": sum(1 for r in dragon_records_converged if "先锋" in r["role"]),
            "all_space_count": sum(1 for r in dragon_records_all if "空间" in r["role"]),
            "all_midcap_count": sum(1 for r in dragon_records_all if "容量" in r["role"]),
            "all_pioneer_count": sum(1 for r in dragon_records_all if "先锋" in r["role"]),
            "all_total_count": len(dragon_records_all),
            "converged_total_count": len(dragon_records_converged),
            "dual_accel_count": sum(1 for r in dragon_records_converged if "双加速" in r.get("accel_tag", "")),
            "gap_accel_count": sum(1 for r in dragon_records_converged if "缺口加速" in r.get("accel_tag", "")),
            "open_low_count": sum(1 for r in dragon_records_converged if "光脚加速" in r.get("accel_tag", "")),
            "accel_total_count": sum(1 for r in dragon_records_converged if r.get("accel_tag"))
        }

        with self._cache_lock:
            self._cached_report = report
            self._cached_time = now
            self._cached_df_len = len(df)
            c_col = 'code' if 'code' in df.columns else None
            self._cached_df_first_code = str(df[c_col].iloc[0]) if (c_col and len(df) > 0) else (str(df.index[0]) if len(df) > 0 else "")
            self._dragon_codes_set = dragon_codes_set
            self._trap_codes_set = trap_codes_set

        logger.debug(
            f"[CapitalDragonEngine] Completed analysis in {report['calc_cost_ms']}ms: "
            f"TopSectors={len(top_sectors[:5])}, Dragons={len(dragon_records)} "
            f"(Space={report['space_dragon_count']}, Mid={report['midcap_dragon_count']}, Pioneer={report['pioneer_dragon_count']})"
        )
        return report

    def get_dragon_codes(self) -> Set[str]:
        with self._cache_lock:
            return set(self._dragon_codes_set)

    def is_true_dragon(self, code: str) -> bool:
        c = _clean_code(code)
        with self._cache_lock:
            return c in self._dragon_codes_set

    def is_isolated_trap(self, code: str) -> bool:
        c = _clean_code(code)
        with self._cache_lock:
            return c in self._trap_codes_set

    def get_dragon_info(self, code: str) -> Optional[Dict[str, Any]]:
        c = _clean_code(code)
        with self._cache_lock:
            recs = self._cached_report.get("dragon_records", [])
            for r in recs:
                if r["code"] == c:
                    return dict(r)
        return None

    def get_market_indices_and_volume_summary(self, df_all: Optional[pd.DataFrame] = None, now_dt: Optional[Any] = None) -> Dict[str, Any]:
        """
        获取全市场四大核心指数（上证、深证、创业板、北证）的资金、量比，以及全市交易额和较昨日增减交易额 (SSOT)

        ⚡ 极限性能优化版 (2026-09-11):
        - 主线程调用：仅读 _bg_market_summary_cache（< 0.1ms，零网络IO）
        - 生产环境后台线程（_start_market_summary_bg_updater）每 5s 独立拉取 TDX 数据更新缓存
        - 测试环境（df_all is not None）：直接从 DataFrame 提取，支持离线单元测试（保持原逻辑）
        """
        # ── 测试环境（df_all 传入）：保留完整原逻辑，直接从 df 提取 ──────────────────
        if df_all is not None and not df_all.empty:
            return self._compute_market_summary_from_df(df_all, now_dt)

        # ── 生产环境：主线程只读后台缓存（< 0.1ms，零阻塞）────────────────────────
        cached = self._bg_market_summary_cache
        if cached:
            return dict(cached)

        # 首次启动缓存为空时返回空占位（不阻塞主线程）
        return {'formatted_html': '', 'plain_text': '', 'sh_amt': 0.0, 'sz_amt': 0.0,
                'cy_amt': 0.0, 'bj_amt': 0.0, 'total_amt': 0.0, 'diff_amt': 0.0, 'diff_str': ''}

    def _compute_market_summary_from_df(self, df_all: pd.DataFrame, now_dt: Optional[Any] = None) -> Dict[str, Any]:
        """从传入的 df_all 提取大盘摘要（单元测试与强制刷新专用，与主线程调用完全解耦）"""
        import datetime
        if now_dt is None:
            now_dt = datetime.datetime.now()
        prev_data = getattr(self, '_yesterday_index_amounts', {}) or {}
        extracted = {}
        code_col = 'code' if 'code' in df_all.columns else None
        codes_s = df_all[code_col].astype(str).str.strip().str.zfill(6) if code_col else df_all.index.astype(str).str.strip().str.zfill(6)
        for idx_key, target_code in [('sh', '999999'), ('sz', '399001'), ('cy', '399006'), ('bj', '899050')]:
            cand_codes = [target_code, '000001'] if idx_key == 'sh' else [target_code]
            for cand in cand_codes:
                match_mask = (codes_s == cand)
                if match_mask.any():
                    row = df_all[match_mask].iloc[0]
                    raw_amt = float(row.get('amount', 0.0) or 0.0)
                    amt_yi = (raw_amt / 1e8) if raw_amt > 1e6 else raw_amt
                    raw_vr = float(row.get('vol_ratio', row.get('volume', 1.0)) or 1.0)
                    extracted[idx_key] = {'amount_yi': amt_yi, 'vol_ratio': raw_vr}
                    break
        res = self._build_summary_result(extracted, prev_data, now_dt)

        self._bg_market_summary_cache = res
        self._bg_market_summary_ts = time.time()
        return res


    def _compute_market_summary_bg(self) -> None:
        """
        后台线程专属：拉取 TDX API + 计算大盘摘要 → 写入 _bg_market_summary_cache
        本函数**绝不**在主线程中调用，完全运行于独立 daemon 线程。
        """
        import datetime
        now_dt = datetime.datetime.now()
        today_str = now_dt.strftime('%Y-%m-%d')

        # ① 获取/刷新昨日指数收盘基准（每天拉取一次，内存持久缓存）
        prev_data = getattr(self, '_yesterday_index_amounts', None)
        if not prev_data or getattr(self, '_yesterday_cache_date', '') != today_str:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                with fetcher._conn_lock:
                    if not fetcher._is_connected or not fetcher.api:
                        fetcher.connect()
                    if fetcher._is_connected and fetcher.api:
                        b_sh = fetcher.api.get_index_bars(4, 1, '000001', 0, 3)
                        b_sz = fetcher.api.get_index_bars(4, 0, '399001', 0, 3)
                        b_cy = fetcher.api.get_index_bars(4, 0, '399006', 0, 3)
                        b_bj = fetcher.api.get_index_bars(4, 2, '899050', 0, 3)

                        p_sh = b_sh[-2]['amount'] / 1e8 if b_sh and len(b_sh) >= 2 else 0.0
                        p_sz = b_sz[-2]['amount'] / 1e8 if b_sz and len(b_sz) >= 2 else 0.0
                        p_cy = b_cy[-2]['amount'] / 1e8 if b_cy and len(b_cy) >= 2 else 0.0
                        p_bj = b_bj[-2]['amount'] / 1e8 if b_bj and len(b_bj) >= 2 else 0.0
                        v_sh = b_sh[-2]['vol'] if b_sh and len(b_sh) >= 2 else 1.0
                        v_sz = b_sz[-2]['vol'] if b_sz and len(b_sz) >= 2 else 1.0
                        v_cy = b_cy[-2]['vol'] if b_cy and len(b_cy) >= 2 else 1.0
                        v_bj = b_bj[-2]['vol'] if b_bj and len(b_bj) >= 2 else 1.0
                        prev_data = {
                            'sh': p_sh, 'sz': p_sz, 'cy': p_cy, 'bj': p_bj,
                            'total': p_sh + p_sz + p_bj,
                            'vol_sh': v_sh, 'vol_sz': v_sz, 'vol_cy': v_cy, 'vol_bj': v_bj
                        }
                        self._yesterday_index_amounts = prev_data
                        self._yesterday_cache_date = today_str
            except Exception as e_prev:
                logger.debug(f"[CapitalDragonEngine] 后台获取昨日指数基准异常: {e_prev}")
                prev_data = getattr(self, '_yesterday_index_amounts', {}) or {}

        # ② 拉取四大指数实时行情
        extracted = {}
        try:
            need_fetch = ['999999', '000001', '399001', '399006', '899050', '399005']
            tdx_res = self._fetch_tdx_index_data(need_fetch)
            for k, c in [('sh', '999999'), ('sz', '399001'), ('cy', '399006'), ('bj', '899050')]:
                info = tdx_res.get(c) or (tdx_res.get('000001') if c == '999999' else None)
                if info and float(info.get('amount_yi', 0.0) or 0.0) > 0:
                    a_yi = float(info.get('amount_yi', 0.0))
                    prev_vol = prev_data.get(f'vol_{k}', 1.0) if prev_data else 1.0
                    cur_vol = float(info.get('vol', 0.0) or 0.0)
                    try:
                        ratio_t = float(cct.get_work_time_ratio(resample='d'))
                    except Exception:
                        ratio_t = 1.0
                    ratio_t = max(0.05, min(ratio_t, 1.0))
                    calc_vr = round(cur_vol / (max(prev_vol, 1.0) * ratio_t), 2) if (cur_vol > 0 and prev_vol > 1000.0) else 1.0
                    if calc_vr <= 0.05 or calc_vr > 50.0:
                        calc_vr = 1.0
                    extracted[k] = {'amount_yi': a_yi, 'vol_ratio': calc_vr}
        except Exception as e_tdx:
            logger.debug(f"[CapitalDragonEngine] 后台TDX拉取大盘指数异常: {e_tdx}")

        if not extracted:
            return  # 拉取失败，保留旧缓存，不用空结果覆盖

        # ③ 写入后台缓存（原子覆盖，主线程下次读取即为最新值）
        res = self._build_summary_result(extracted, prev_data, now_dt)
        self._bg_market_summary_cache = res
        self._bg_market_summary_ts = time.time()

    def _build_summary_result(self, extracted: Dict, prev_data: Dict, now_dt: Any) -> Dict[str, Any]:
        """从 extracted 和 prev_data 组装大盘摘要结果字典（纯计算，无 IO）"""
        import datetime
        if now_dt is None:
            now_dt = datetime.datetime.now()

        sh_amt = round(extracted.get('sh', {}).get('amount_yi', 0.0), 1)
        sh_vr  = round(extracted.get('sh', {}).get('vol_ratio', 1.0), 2)
        sz_amt = round(extracted.get('sz', {}).get('amount_yi', 0.0), 1)
        sz_vr  = round(extracted.get('sz', {}).get('vol_ratio', 1.0), 2)
        cy_amt = round(extracted.get('cy', {}).get('amount_yi', 0.0), 1)
        cy_vr  = round(extracted.get('cy', {}).get('vol_ratio', 1.0), 2)
        bj_amt = round(extracted.get('bj', {}).get('amount_yi', 0.0), 1)
        bj_vr  = round(extracted.get('bj', {}).get('vol_ratio', 1.0), 2)

        total_amt = round(sh_amt + sz_amt + bj_amt, 1)

        prev_total = prev_data.get('total', 0.0) if prev_data else 0.0
        diff_amt = 0.0
        if prev_total > 0:
            now_hour = now_dt.hour
            if now_hour >= 15 or now_hour < 9:
                diff_amt = round(total_amt - prev_total, 1)
            else:
                try:
                    ratio_t = float(cct.get_work_time_ratio(resample='d'))
                except Exception:
                    ratio_t = 1.0
                ratio_t = max(0.05, min(ratio_t, 1.0))
                diff_amt = round(total_amt - (prev_total * ratio_t), 1)

        diff_str = f"+{diff_amt:.1f}亿" if diff_amt > 0 else f"{diff_amt:.1f}亿"
        diff_color = "#ff5555" if diff_amt >= 0 else "#00ff88"

        formatted_html = (
            f"<span style='color:#8e8e93;'>上证:</span> <span style='color:#ffffff; font-weight:bold;'>{sh_amt:.1f}亿</span> <span style='color:#00ff88;'>({sh_vr:.2f}x)</span> &nbsp;|&nbsp; "
            f"<span style='color:#8e8e93;'>深证:</span> <span style='color:#ffffff; font-weight:bold;'>{sz_amt:.1f}亿</span> <span style='color:#00ff88;'>({sz_vr:.2f}x)</span> &nbsp;|&nbsp; "
            f"<span style='color:#8e8e93;'>创业板:</span> <span style='color:#ffffff; font-weight:bold;'>{cy_amt:.1f}亿</span> <span style='color:#00ff88;'>({cy_vr:.2f}x)</span> &nbsp;|&nbsp; "
            f"<span style='color:#8e8e93;'>北证:</span> <span style='color:#ffffff; font-weight:bold;'>{bj_amt:.1f}亿</span> <span style='color:#00ff88;'>({bj_vr:.2f}x)</span> &nbsp;|&nbsp; "
            f"<span style='color:#8e8e93;'>全市:</span> <span style='color:#e3b341; font-weight:bold;'>{total_amt:.1f}亿</span> "
            f"<span style='color:{diff_color}; font-weight:bold;'>(较昨 {diff_str})</span>"
        )
        plain_text = (
            f"上证: {sh_amt:.1f}亿 ({sh_vr:.2f}x) | 深证: {sz_amt:.1f}亿 ({sz_vr:.2f}x) | "
            f"创业板: {cy_amt:.1f}亿 ({cy_vr:.2f}x) | 北证: {bj_amt:.1f}亿 ({bj_vr:.2f}x) | "
            f"全市: {total_amt:.1f}亿 (较昨 {diff_str})"
        )
        return {
            "sh_amt": sh_amt, "sh_vr": sh_vr,
            "sz_amt": sz_amt, "sz_vr": sz_vr,
            "cy_amt": cy_amt, "cy_vr": cy_vr,
            "bj_amt": bj_amt, "bj_vr": bj_vr,
            "total_amt": total_amt,
            "diff_amt": diff_amt,
            "diff_str": diff_str,
            "formatted_html": formatted_html,
            "plain_text": plain_text
        }

    def start_market_summary_bg_updater(self, interval_sec: Optional[float] = None) -> None:
        """
        启动大盘摘要后台定期刷新线程（daemon，每 interval_sec 秒刷新一次，默认接入 cct.ats_tdx_interval）。
        应在主窗口初始化时（_init_status_clock 后）调用一次，并发调用自动幂等。
        """
        if interval_sec is None:
            interval_sec = float(getattr(cct, 'ats_tdx_interval', 5.0) or 5.0)

        with self._bg_updater_lock:
            if self._bg_updater_running:
                return
            self._bg_updater_running = True

        def _loop():
            init_intv = float(getattr(cct, 'ats_tdx_interval', interval_sec) or interval_sec)
            logger.info(f"[CapitalDragonEngine] 大盘摘要后台刷新线程已启动 (基准间隔 {init_intv}s, 动态跟随 cct.ats_tdx_interval)")
            while True:
                try:
                    self._compute_market_summary_bg()
                except Exception as e_loop:
                    logger.debug(f"[CapitalDragonEngine] 后台摘要刷新异常: {e_loop}")
                cur_intv = float(getattr(cct, 'ats_tdx_interval', interval_sec) or interval_sec)
                time.sleep(cur_intv)

        t = threading.Thread(target=_loop, daemon=True, name="MarketSummaryBgUpdater")
        t.start()



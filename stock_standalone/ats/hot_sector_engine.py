# -*- coding: utf-8 -*-
"""
ats/hot_sector_engine.py — 强势板块龙头突击与三维买点定位引擎
功能：
1. 自动聚合市场 Top 3 强势板块（如 CPO、国家大基建、存储芯片等）成分股与多日自选池；
2. 结合底层多日底座数据（DFF2/DFF3/VWAP累积抬升/排位）与 TDX 秒级高频盘口数据；
3. 实时计算量比爆发力、日内 VWAP 偏离度、五档买盘承接力与分时攻角；
4. 智能判定【👑 领涨龙头】、【🚀 先锋突破】、【🎯 VWAP回踩】、【⚠️ 破位转弱】；
5. 提供建议买入区间 (Buy Zone) 与防守止损位，生成秒级 Hot Alpha 跟单排行榜。
"""

import os
import sys
import time
import logging
import threading
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from sys_utils import get_app_root
from JohnsonUtil import commonTips as cct

logger = logging.getLogger("HotSectorEngine")


def is_valid_sector_name(sec: Any) -> bool:
    """
    严密判定板块名称是否为有效且明确的实体板块（过滤掉 '--', '0', '0.0', 'nan', '未知', 纯数字等）
    """
    if sec is None:
        return False
    s = str(sec).strip()
    if not s:
        return False
    # 过滤占位符与无意义值
    if s.lower() in ('--', '-', '---', '0', '0.0', '00', '000', '000000', 'none', 'nan', 'null', '未知', '其它', '其他', '未分类', 'default'):
        return False
    # 过滤纯数字（例如股票代码或数字ID被误作为板块名）
    if s.isdigit():
        return False
    # 去除特殊前缀符号后如果为空或依然是无效词
    import re
    cleaned = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', s).strip()
    if not cleaned or cleaned.lower() in ('--', '-', '---', '0', '0.0', '00', '000', '000000', 'none', 'nan', 'null', '未知', '其它', '其他', '未分类'):
        return False
    if cleaned.isdigit():
        return False
    return True


class HotSectorEngine:
    """
    强势板块龙头突击跟单引擎 (单例)
    """
    _instance: Optional['HotSectorEngine'] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'HotSectorEngine':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.fetcher = TDXRealtimeFetcher.get_instance()
        self.top_sectors: List[Tuple[str, float, str, int]] = [] # [(name, score, pct_str, count)]
        self.sector_to_codes: Dict[str, List[str]] = {}
        self.code_to_sector: Dict[str, str] = {}
        self.tracked_codes: List[str] = []
        self._last_alpha_results: List[Dict[str, Any]] = []
        self._results_lock = threading.RLock()
        self.worker: Optional['HotSectorAlphaWorker'] = None

    def extract_top_sectors_from_heatmap(
        self,
        sectors_list: List[Tuple[Any, ...]],
        sector_to_codes_map: Optional[Dict[str, List[str]]] = None,
        top_n: int = 3,
        sort_mode: int = 0
    ) -> List[str]:
        """
        从板块热力图数据中提取排名前 top_n 的真实强势板块名称。
        支持联动跟随热力图当前的排序规则 (0: 强度得分降序, 1: 涨跌幅降序, 2: 活跃成员数降序)
        """
        if not sectors_list:
            return []

        import re
        def safe_float_pct(val_str):
            try:
                return float(str(val_str).replace("%", "").replace("+", ""))
            except Exception:
                return -9999.0

        def _get_sort_val(item):
            try:
                if sort_mode == 1:
                    return safe_float_pct(item[2]) if len(item) > 2 else -9999.0
                elif sort_mode == 2:
                    return int(item[3]) if len(item) > 3 else -9999
                else:
                    return float(item[1]) if len(item) > 1 else -9999.0
            except Exception:
                return -9999.0

        # 基于指定排序规则降序排序，提取真实的 Top N 强势板块
        sorted_by_strength = sorted(sectors_list, key=_get_sort_val, reverse=True)

        top_secs = []
        for item in sorted_by_strength:
            raw_name = str(item[0]).strip()
            if not is_valid_sector_name(raw_name):
                continue
            clean_sec = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', raw_name).strip()
            sec_name = clean_sec if clean_sec else raw_name
            if not is_valid_sector_name(sec_name):
                continue
            # 🛡️ 自动过滤虚拟系统聚合池 (如 "实时报警" / "🔔 实时报警")，保留真实题材概念赛道 (竞价挖掘)
            if any(ex in sec_name for ex in ("实时报警", "系统报警", "异动汇总")):
                continue
            if sec_name and sec_name not in top_secs:
                top_secs.append(sec_name)
            if len(top_secs) >= top_n:
                break

        if sector_to_codes_map:
            self.sector_to_codes = {k: v for k, v in sector_to_codes_map.items() if is_valid_sector_name(k)}
            self.code_to_sector = {}
            for sec, codes in self.sector_to_codes.items():
                clean_sec_key = re.sub(r'^[^\w\u4e00-\u9fa5]+', '', str(sec)).strip()
                target_sec_name = clean_sec_key or str(sec).strip()
                if not is_valid_sector_name(target_sec_name):
                    continue
                for c in codes:
                    c_clean = str(c).strip().zfill(6)
                    self.code_to_sector[c_clean] = target_sec_name

        return top_secs

    def build_target_universe(
        self,
        top_sector_names: List[str],
        current_df: Optional[pd.DataFrame] = None,
        manual_watchlist: Optional[List[str]] = None,
        max_total_stocks: int = 120
    ) -> Tuple[List[str], Dict[str, str], Dict[str, Any], Dict[str, str]]:
        """
        构建目标股票池、板块映射、多日特征快照与名称映射。
        :return: (target_codes, sector_map, multi_period_cache, name_map)
        """
        target_codes_set = set()
        sector_map = {}
        multi_period_cache = {}
        name_map = {}

        # 0. 过滤非明确板块
        valid_top_sectors = [s for s in top_sector_names if is_valid_sector_name(s)]

        # 1. 提取 Top 强势板块的成分股
        for sec in valid_top_sectors:
            codes_in_sec = self.sector_to_codes.get(sec, [])
            for c in codes_in_sec:
                c_clean = str(c).strip().zfill(6)
                if c_clean:
                    target_codes_set.add(c_clean)
                    sector_map[c_clean] = sec

        # 2. 如果 current_df 包含 category，进行板块成分股动态补全
        if current_df is not None and not current_df.empty and 'category' in current_df.columns:
            try:
                for sec in valid_top_sectors:
                    # 匹配 category 列包含板块名的股票 (禁用 regex 避免括号告警)
                    mask = current_df['category'].astype(str).str.contains(sec, case=False, na=False, regex=False)
                    df_matched = current_df[mask]
                    for c_idx in df_matched.index[:40]: # 每个强板块最多取40只
                        c_clean = str(c_idx).strip().zfill(6)
                        if c_clean:
                            target_codes_set.add(c_clean)
                            if c_clean not in sector_map:
                                sector_map[c_clean] = sec
            except Exception as e:
                logger.debug(f"动态提取板块成分股异常: {e}")

        # 3. 匹配手动重点关注池 (仅当其属于当前有效热点板块时才确保纳入，杜绝非热点自选股伪造板块侵入)
        if manual_watchlist:
            for c in manual_watchlist:
                c_clean = str(c).strip().zfill(6)
                if c_clean and c_clean in sector_map:
                    target_codes_set.add(c_clean)

        # 4. 从 current_df 提取多日底蕴特征与名称
        if current_df is not None and not current_df.empty:
            for code_clean in target_codes_set:
                row = None
                if code_clean in current_df.index:
                    row = current_df.loc[code_clean]
                else:
                    c_num = "".join(filter(str.isdigit, code_clean))
                    if c_num in current_df.index:
                        row = current_df.loc[c_num]

                if row is not None:
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]

                    # 提取名称
                    name = str(row.get('name', '')).strip()
                    if name and name not in ('nan', '--', '0', '未知'):
                        name_map[code_clean] = name

                    # 提取多日加速与量价特征
                    try:
                        dff = float(row.get('dff', row.get('DFF', 0.0)) or 0.0)
                    except Exception:
                        dff = 0.0
                    try:
                        dff2 = float(row.get('dff2', row.get('DFF2', 0.0)) or 0.0)
                    except Exception:
                        dff2 = 0.0
                    try:
                        dff3 = float(row.get('dff3', row.get('DFF3', 0.0)) or 0.0)
                    except Exception:
                        dff3 = 0.0
                    try:
                        rank_val = int(row.get('Rank', row.get('rank', 999)) or 999)
                    except Exception:
                        rank_val = 999
                    try:
                        perc3d = float(row.get('perc3d', row.get('percent3d', 0.0)) or 0.0)
                    except Exception:
                        perc3d = 0.0
                    try:
                        # 换手率提取 (注意：Sina数据中 turnover 为成交额元，需过滤掉 >100 的大数，优先取 turnover_rate / hsl / ratio)
                        raw_to = row.get('turnover_rate', row.get('hsl', row.get('turnover_ratio', row.get('ratio', 0.0))))
                        turnover_val = float(raw_to or 0.0)
                        if turnover_val > 100.0 or turnover_val < 0.0:
                            turnover_val = 0.0
                    except Exception:
                        turnover_val = 0.0
                    try:
                        # 真实量比提取 (兼容 volume_ratio / vol_ratio / ratio)
                        raw_vr = row.get('volume_ratio', row.get('vol_ratio', row.get('volume', 1.0)))
                        vol_r = float(raw_vr or 1.0)
                        if vol_r > 100.0: # 若是成交手数而非量比
                            vol_r = float(row.get('volume_ratio', row.get('vol_ratio', 1.0)) or 1.0)
                    except Exception:
                        vol_r = 1.0
                    try:
                        outstanding_val = float(row.get('outstanding', row.get('totals', 0.0)) or 0.0)
                    except Exception:
                        outstanding_val = 0.0

                    # 提取动态自定义扩展列 (如 ch_bc2 等)
                    extra_vals = {}
                    try:
                        from ats.ui.favorite_panel import get_ats_extra_cols
                        from JohnsonUtil import commonTips as cct
                        extra_cols = get_ats_extra_cols()
                        for ec in extra_cols:
                            ec_val = '--'
                            for k in (ec, ec.lower(), ec.upper()):
                                if k in row:
                                    ec_val = cct.format_col_value(ec, row[k])
                                    break
                            extra_vals[ec] = ec_val
                    except Exception:
                        pass

                    multi_period_cache[code_clean] = {
                        "dff": dff,
                        "dff2": dff2,
                        "dff3": dff3,
                        "rank": rank_val,
                        "perc3d": perc3d,
                        "turnover": turnover_val,
                        "outstanding": outstanding_val,
                        "vol_ratio": vol_r,
                        "extra_vals": extra_vals
                    }

        all_target_codes = list(target_codes_set)[:max_total_stocks]
        return all_target_codes, sector_map, multi_period_cache, name_map

    def compute_hot_alpha_leaderboard(
        self,
        top_sector_names: List[str],
        current_df: Optional[pd.DataFrame] = None,
        manual_watchlist: Optional[List[str]] = None,
        segment_mode: str = "30m"
    ) -> List[Dict[str, Any]]:
        """
        同步计算最新 Hot Alpha 跟单排行榜
        """
        codes, sec_map, mp_cache, n_map = self.build_target_universe(
            top_sector_names, current_df, manual_watchlist
        )
        if not codes:
            return []

        results = self.fetcher.fetch_multi_stock_alpha_quotes(
            codes=codes,
            sector_map=sec_map,
            multi_period_cache=mp_cache,
            name_map=n_map,
            segment_mode=segment_mode
        )

        with self._results_lock:
            self._last_alpha_results = results
            self.tracked_codes = codes

        return results

    def get_latest_results(self) -> List[Dict[str, Any]]:
        with self._results_lock:
            return list(self._last_alpha_results)

    def start_polling_worker(
        self,
        get_top_sectors_fn: Callable[[], List[str]],
        get_current_df_fn: Callable[[], Optional[pd.DataFrame]],
        get_manual_watchlist_fn: Optional[Callable[[], List[str]]] = None,
        interval_seconds: float = 1.5,
        on_update_callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        """启动后台独立秒级计算 Worker 线程"""
        self.stop_polling_worker()
        self.worker = HotSectorAlphaWorker(
            engine=self,
            get_top_sectors_fn=get_top_sectors_fn,
            get_current_df_fn=get_current_df_fn,
            get_manual_watchlist_fn=get_manual_watchlist_fn,
            interval_seconds=interval_seconds,
            on_update_callback=on_update_callback
        )
        self.worker.start()

    def stop_polling_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker = None


class HotSectorAlphaWorker(threading.Thread):
    """
    后台高频秒级强势板块龙头 Alpha 扫描 Worker
    """
    def __init__(
        self,
        engine: HotSectorEngine,
        get_top_sectors_fn: Callable[[], List[str]],
        get_current_df_fn: Callable[[], Optional[pd.DataFrame]],
        get_manual_watchlist_fn: Optional[Callable[[], List[str]]] = None,
        interval_seconds: float = 1.5,
        on_update_callback: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        super().__init__(daemon=True, name="HotSectorAlphaWorker")
        self.engine = engine
        self.get_top_sectors = get_top_sectors_fn
        self.get_current_df = get_current_df_fn
        self.get_manual_watchlist = get_manual_watchlist_fn
        self.interval = max(0.8, float(interval_seconds))
        self.callback = on_update_callback
        self._running = False

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        logger.info("🚀 HotSectorAlphaWorker 强势板块龙头跟单 Worker 启动")

        while self._running:
            try:
                top_secs = self.get_top_sectors() if self.get_top_sectors else []
                curr_df = self.get_current_df() if self.get_current_df else None
                manual_list = self.get_manual_watchlist() if self.get_manual_watchlist else None

                if top_secs or manual_list:
                    results = self.engine.compute_hot_alpha_leaderboard(
                        top_sector_names=top_secs,
                        current_df=curr_df,
                        manual_watchlist=manual_list
                    )
                    if results and self.callback:
                        self.callback(results)
            except Exception as e:
                logger.debug(f"HotSectorAlphaWorker 轮询异常: {e}")

            time.sleep(self.interval)

        logger.info("🛑 HotSectorAlphaWorker 强势板块龙头跟单 Worker 停止")

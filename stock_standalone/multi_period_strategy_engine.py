import pandas as pd
import json
import os
from typing import Dict, List, Optional
from JohnsonUtil import LoggerFactory
from sys_utils import get_app_root, get_conf_path
logger = LoggerFactory.getLogger("MultiPeriodStrategyEngine")

_global_ipc_manager = None

def get_global_ipc_sync_manager():
    """获取全局 IPCSyncManager 单例，用于跨进程获取 TK 监控端实时行情"""
    global _global_ipc_manager
    if _global_ipc_manager is None:
        try:
            from ipc_sync_manager import IPCSyncManager
            candidate_ports = [26671, 26679, 26680, 26681, 26682, 26683]
            for p in candidate_ports:
                try:
                    mgr = IPCSyncManager(port=p, logger=logger)
                    mgr.start()
                    if getattr(mgr, '_bind_event', None):
                        mgr._bind_event.wait(timeout=0.5)
                    if getattr(mgr, 'is_bound', False):
                        _global_ipc_manager = mgr
                        logger.info(f"⚡ [IPC 同步单例] 成功绑定并启动于端口 Port={p}")
                        break
                    else:
                        mgr.stop()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Failed to initialize IPCSyncManager: {e}")
    return _global_ipc_manager

class MultiPeriodStrategyEngine:
    SUPPORTED_PERIODS = ['d', '2d', '3d', 'w', 'm', '45d', '3M']
    
    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self._period_dfs: Dict[str, pd.DataFrame] = {}
        self._strategies: List[dict] = []
        self._missing_periods: Dict[str, str] = {}  # period -> 缺失原因
        self.config_path = get_conf_path("multi_period_strategies.json")
        self.last_stats: dict = {}

    @staticmethod
    def _extract_cols_from_expr(expr_str: str) -> set:
        """从策略表达式中精准提取所有引用的变量列名（自动预处理展开模版语法如 {1-4}）"""
        if not expr_str or not isinstance(expr_str, str):
            return set()
        import re
        try:
            from query_engine_util import query_engine
            if query_engine:
                expr_str = query_engine._preprocess_query(expr_str)
        except Exception:
            pass

        tokens = set(re.findall(r'\b[a-zA-Z_]\w*\b', expr_str))
        py_keywords = {
            'and', 'or', 'not', 'in', 'is', 'if', 'else', 'True', 'False', 'None',
            'df', 'pd', 'np', 'abs', 'max', 'min', 'GREATEST', 'LEAST', 'ABS', 'MAX', 'MIN',
            'result', 'signal', 'case', 'regex', 'contains', 'str'
        }
        cols = tokens - py_keywords
        expanded_cols = set(cols)
        for c in cols:
            if c.endswith('_d'):
                expanded_cols.add(c[:-2])
        return expanded_cols

    def ensure_strategy_ipc_columns(self, df: pd.DataFrame, strategy_expr: str = "", force_refresh: bool = False, force_refresh_ipc: bool = False) -> pd.DataFrame:
        """
        通过 IPC 工厂模式按需抓取策略中所需但 df 中缺失或为初始缺省值的列。
        性能与稳定性规则:
        1. 向量化匹配 (Vectorized Reindex)，全面替代逐列 Python 循环与字典构建；
        2. 一次性批量落盘并巩固 BlockManager (consolidate)，彻底防范 pandas BlockManager Gaps 碎片化异常；
        3. 若列已存在且无需重刷，秒级跳过直接返回。
        """
        if df is None or df.empty:
            return df

        needed_cols = self._extract_cols_from_expr(strategy_expr)
        
        # 判定 df 中需要从 IPC 抓取/全自动回补的列
        missing_cols = set(needed_cols)
        default_core_cols = {
            'vwap_cum_2d', 'vwap_cum_3d', 'vwap_cum_4d', 'vwap_cum_5d',
            'last_vwap_cum_2d', 'last_vwap_cum_3d', 'last_nclose1d', 'last_nclose3d',
            'Trends', 'nclose', 'sig_bottom', 'sig_launch'
        }
        missing_cols.update(default_core_cols)

        ipc_mgr = get_global_ipc_sync_manager()
        last_recv = getattr(ipc_mgr, 'last_recv_t', 0.0) if ipc_mgr is not None else 0.0
        df_ipc_ts = getattr(df, '_ipc_enriched_ts', 0.0)

        # 判定是否需要向 df 注入/同步最新 IPC 数据（当 df 未同步最新包、含缺失列或请求强刷时）
        cols_to_fill = [c for c in missing_cols if c not in df.columns or df[c].isna().all()]
        needs_ipc_sync = (df_ipc_ts < last_recv) or (df_ipc_ts == 0.0) or len(cols_to_fill) > 0 or force_refresh

        # 🚀 快速快照判定：若已是最新 IPC 数据，且无缺失列，且未强刷，秒级返回
        if not needs_ipc_sync:
            return df

        try:
            import time
            import re
            import numpy as np
            if ipc_mgr is not None:
                ipc_df = ipc_mgr.get_current_df()
                now_ts = time.time()

                try:
                    from JohnsonUtil import commonTips as cct
                    is_work_time = cct.get_work_time()
                except Exception:
                    is_work_time = False

                cache_expired = (now_ts - last_recv > 900.0) if is_work_time else False
                has_valid_ipc = (ipc_df is not None and not ipc_df.empty and len(ipc_df.columns) >= 20)

                need_socket_sync = (not has_valid_ipc or cache_expired or force_refresh_ipc)
                if need_socket_sync:
                    ipc_mgr.request_full_sync()
                    for _ in range(25):
                        time.sleep(0.1)
                        ipc_df = ipc_mgr.get_current_df()
                        if ipc_df is not None and not ipc_df.empty and len(ipc_df.columns) >= 20:
                            last_recv = getattr(ipc_mgr, 'last_recv_t', time.time())
                            logger.info(f"⚡ [IPC 工厂单例缓存] 成功完整获取 {len(ipc_df)} 行 {len(ipc_df.columns)} 列实时行情快照至策略引擎")
                            break

                if ipc_df is not None and not ipc_df.empty:
                    cols_to_sync = set(missing_cols)
                    if force_refresh or needs_ipc_sync:
                        cols_to_sync.update(ipc_df.columns)

                    # ⚡ [向量化重排] 将 ipc_df 索引统一转换为 6 位补零 Code 格式
                    ipc_df_indexed = ipc_df.copy()
                    ipc_df_indexed.index = [str(c).strip().zfill(6) for c in ipc_df_indexed.index]
                    
                    df_codes = df['code'] if 'code' in df.columns else df.index
                    df_code_strs = [str(c).strip().zfill(6) for c in df_codes]

                    ipc_sub = ipc_df_indexed.reindex(df_code_strs)
                    ipc_sub.index = df.index

                    new_series_dict = {}
                    for col in cols_to_sync:
                        target_col = col
                        clean_col = re.sub(r'_(d|1d|2d|3d|4d|5d|w|m|45d|3m)$', '', col)
                        if target_col not in ipc_sub.columns:
                            if clean_col in ipc_sub.columns:
                                target_col = clean_col
                            elif target_col.endswith('_d') and target_col[:-2] in ipc_sub.columns:
                                target_col = target_col[:-2]

                        if target_col in ipc_sub.columns:
                            s_ipc = ipc_sub[target_col]
                            # 只要 IPC 中有真实高密值，优先覆盖已有的 fallback/估算缺省列
                            new_series_dict[col] = s_ipc
                            base_alias = col[:-2] if col.endswith('_d') else f"{col}_d"
                            if base_alias not in new_series_dict:
                                new_series_dict[base_alias] = s_ipc

                    if new_series_dict:
                        new_cols_df = pd.DataFrame(new_series_dict, index=df.index)
                        # ⚡ [100% 安全 BlockManager 巩固] 彻底消除 Gaps in blk ref_locs 内存碎片化异常
                        keep_cols = [c for c in df.columns if c not in new_cols_df.columns]
                        df = pd.concat([df[keep_cols], new_cols_df], axis=1).copy()
                        setattr(df, '_ipc_enriched_ts', last_recv if last_recv > 0 else time.time())

        except Exception as ex_ipc:
            logger.debug(f"IPC fetch for missing strategy cols failed: {ex_ipc}")

        # 🛡️ 自动安全兜底：如果 IPC 依然没有获取到该列，先通过日线 OHLCV/多日量价估计计算 VWAP 成本列
        df = self.compute_daily_vwap_fallbacks(df)

        fallback_cols_dict = {}
        for col in missing_cols:
            if col not in df.columns or df[col].isna().all():
                c_low = col.lower()
                if 'vwap' in c_low or 'nclose' in c_low or c_low.startswith('lastp') or c_low.startswith('close'):
                    fallback_cols_dict[col] = df['close'] if 'close' in df.columns else 0.0
                elif c_low.startswith('lasth') or c_low.startswith('h'):
                    fallback_cols_dict[col] = df['high'] if 'high' in df.columns else (df['close'] if 'close' in df.columns else 0.0)
                elif c_low.startswith('lastl') or (c_low.startswith('l') and not c_low.startswith('lastv')):
                    fallback_cols_dict[col] = df['low'] if 'low' in df.columns else (df['close'] if 'close' in df.columns else 0.0)
                elif c_low.startswith('ma'):
                    fallback_cols_dict[col] = df['close'] if 'close' in df.columns else 0.0
                elif 'trends' in c_low:
                    fallback_cols_dict[col] = 60
                elif 'volume' in c_low or 'lastv' in c_low:
                    fallback_cols_dict[col] = df['volume'] if 'volume' in df.columns else 0.0
                elif 'per' in c_low or 'percent' in c_low:
                    fallback_cols_dict[col] = df['percent'] if 'percent' in df.columns else 0.0
                else:
                    fallback_cols_dict[col] = 0.0

        if fallback_cols_dict:
            fb_df = pd.DataFrame(fallback_cols_dict, index=df.index)
            keep_cols = [c for c in df.columns if c not in fb_df.columns]
            df = pd.concat([df[keep_cols], fb_df], axis=1).copy()

        return df

    @staticmethod
    def compute_daily_vwap_fallbacks(df: pd.DataFrame) -> pd.DataFrame:
        """
        当缺少分时/IPC 实时分钟 Bar 数据时，利用日线 OHLCV 与历史多日量价 (close, lastp1d, lastp2d, volume, lastv1d...)
        动态估计计算跨日 VWAP/TWAP 机构成本线衍生列 (vwap_cum_2d, vwap_cum_3d, nclose, last_vwap_cum_2d 等)，
        防止单纯将缺失列填充为 close 导致 nclose >= 1.005 * vwap_cum_2d 等条件 100% 误判为 0 命中。
        """
        if df is None or df.empty:
            return df

        p0 = df['close'] if 'close' in df.columns else (df['trade'] if 'trade' in df.columns else None)
        if p0 is None:
            return df

        import numpy as np

        v0 = df['volume'] if 'volume' in df.columns else (df['vol'] if 'vol' in df.columns else pd.Series(1.0, index=df.index))
        
        # 抽取历史多日收盘与成交量
        p1 = df['lastp1d'] if 'lastp1d' in df.columns else p0
        p2 = df['lastp2d'] if 'lastp2d' in df.columns else p1
        p3 = df['lastp3d'] if 'lastp3d' in df.columns else p2
        p4 = df['lastp4d'] if 'lastp4d' in df.columns else p3
        p5 = df['lastp5d'] if 'lastp5d' in df.columns else p4

        v1 = df['lastv1d'] if 'lastv1d' in df.columns else v0
        v2 = df['lastv2d'] if 'lastv2d' in df.columns else v1
        v3 = df['lastv3d'] if 'lastv3d' in df.columns else v2
        v4 = df['lastv4d'] if 'lastv4d' in df.columns else v3
        v5 = df['lastv5d'] if 'lastv5d' in df.columns else v4

        # 估计 nclose (今日分时 VWAP)
        if 'nclose' not in df.columns or df['nclose'].isna().all():
            if 'amount' in df.columns and 'volume' in df.columns:
                amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
                vol = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
                mask = (vol > 0) & (amt > 0)
                nclose_series = p0.copy()
                ratio = amt[mask] / (vol[mask] * 100.0)
                valid_ratio = (ratio > 0.3 * p0[mask]) & (ratio < 3.0 * p0[mask])
                nclose_series[mask & valid_ratio] = ratio[valid_ratio]
                df['nclose'] = nclose_series
            elif 'open' in df.columns and 'high' in df.columns and 'low' in df.columns:
                df['nclose'] = (df['open'] + df['high'] + df['low'] + df['close'] * 2.0) / 5.0
            else:
                df['nclose'] = p0

        if 'last_nclose1d' not in df.columns or df['last_nclose1d'].isna().all():
            df['last_nclose1d'] = p1
            df['last_nclose'] = p1
        if 'last_nclose2d' not in df.columns or df['last_nclose2d'].isna().all():
            df['last_nclose2d'] = p2
        if 'last_nclose3d' not in df.columns or df['last_nclose3d'].isna().all():
            df['last_nclose3d'] = p3

        # 估计 跨日加权累计 VWAP (vwap_cum_2d, vwap_cum_3d, vwap_cum_4d, vwap_cum_5d)
        w_sum_2d = np.maximum(1.0, v0 + v1)
        w_sum_3d = np.maximum(1.0, v0 + v1 + v2)
        w_sum_4d = np.maximum(1.0, v0 + v1 + v2 + v3)
        w_sum_5d = np.maximum(1.0, v0 + v1 + v2 + v3 + v4)

        last_w_sum_2d = np.maximum(1.0, v1 + v2)
        last_w_sum_3d = np.maximum(1.0, v1 + v2 + v3)

        if 'vwap_cum_2d' not in df.columns or df['vwap_cum_2d'].isna().all():
            c_val = (p0 * v0 + p1 * v1) / w_sum_2d
            df['vwap_cum_2d'] = c_val
            df['vwap_cum_2d_d'] = c_val

        if 'vwap_cum_3d' not in df.columns or df['vwap_cum_3d'].isna().all():
            c_val = (p0 * v0 + p1 * v1 + p2 * v2) / w_sum_3d
            df['vwap_cum_3d'] = c_val
            df['vwap_cum_3d_d'] = c_val

        if 'vwap_cum_4d' not in df.columns or df['vwap_cum_4d'].isna().all():
            c_val = (p0 * v0 + p1 * v1 + p2 * v2 + p3 * v3) / w_sum_4d
            df['vwap_cum_4d'] = c_val
            df['vwap_cum_4d_d'] = c_val

        if 'vwap_cum_5d' not in df.columns or df['vwap_cum_5d'].isna().all():
            c_val = (p0 * v0 + p1 * v1 + p2 * v2 + p3 * v3 + p4 * v4) / w_sum_5d
            df['vwap_cum_5d'] = c_val
            df['vwap_cum_5d_d'] = c_val

        if 'last_vwap_cum_2d' not in df.columns or df['last_vwap_cum_2d'].isna().all():
            c_val = (p1 * v1 + p2 * v2) / last_w_sum_2d
            df['last_vwap_cum_2d'] = c_val
            df['last_vwap_cum_2d_d'] = c_val

        if 'last_vwap_cum_3d' not in df.columns or df['last_vwap_cum_3d'].isna().all():
            c_val = (p1 * v1 + p2 * v2 + p3 * v3) / last_w_sum_3d
            df['last_vwap_cum_3d'] = c_val
            df['last_vwap_cum_3d_d'] = c_val

        return df
        
    def load_period_data(self, period: str, top_now: pd.DataFrame, force_reload: bool = False, end: str = None, readonly: bool = True) -> pd.DataFrame:
        """加载指定周期数据（保持周期原始大小写格式如 '3M'；readonly 为直接传递的界面选择状态，end=截止日期）"""
        from JSONData import tdx_data_Day as tdd

        res_period = str(period).strip()

        # 如果强制重载，则从缓存字典中弹出
        if force_reload:
            with self.lock:
                self._period_dfs.pop(res_period, None)

        if not force_reload:
            with self.lock:
                if res_period in self._period_dfs:
                    return self._period_dfs[res_period]

        try:
            logger.info(f"Loading period data for: {res_period} (readonly={readonly}, end={end})...")
            from JohnsonUtil import johnson_cons as ct
            from JohnsonUtil import commonTips as cct
            from data_utils import complete_indicators_pipeline

            dl_map = {
                'd': 120, '2d': 200, '3d': 200, '5d': 300, 
                'w': 300, 'W': 300, 'm': 550, 'M': 550, '45d': 3000, '3M': 4000, '3m': 4000
            }
            dl = dl_map.get(res_period, ct.Resample_LABELS_Days.get(res_period, 300))
            df, lastp_df = tdd.get_append_lastp_to_df(top_now, dl=dl, resample=res_period, readonly=readonly, end=end)
            
            if df is not None and not df.empty:
                if res_period == 'd':
                    df = self.ensure_strategy_ipc_columns(df, force_refresh=force_reload)
                df = complete_indicators_pipeline(df, logger, resample=res_period)
                with self.lock:
                    self._period_dfs[res_period] = df
                    self._period_dfs[period] = df
                    self._missing_periods.pop(res_period, None)
                    self._missing_periods.pop(period, None)
                return df
            else:
                with self.lock:
                    self._missing_periods[res_period] = "获取数据为空"
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error loading period {res_period}: {e}")
            with self.lock:
                self._missing_periods[res_period] = str(e)
            return pd.DataFrame()
            
    def set_period_df(self, period: str, df: pd.DataFrame):
        with self.lock:
            self._period_dfs[period] = df
        
    def evaluate_strategy(self, strategy_config: dict, active_periods: List[str] = None, force_refresh: bool = False) -> pd.DataFrame:
        if active_periods is None:
            active_periods = list(strategy_config['conditions'].keys())
            
        pass_codes_dict = {}
        
        cross_mode = strategy_config.get('cross_mode', 'intersection')
        self.last_stats = {
            "periods": {},
            "missing": dict(self._missing_periods),  # 快zhao缺失周期快照
            "final": {"total": 0, "pass": 0, "ratio": 0.0, "mode": cross_mode}
        }
        
        for period in active_periods:
            p_norm = str(period).strip()
            
            # 🛡️ 优先检查内存中是否已有有效 DataFrame，若有则自动清理过期的 missing 标记
            df = self._period_dfs.get(p_norm, self._period_dfs.get(period))
            if df is not None and not df.empty:
                with self.lock:
                    self._missing_periods.pop(p_norm, None)
                    self._missing_periods.pop(period, None)
            elif p_norm in self._missing_periods or period in self._missing_periods:
                reason = self._missing_periods.get(p_norm, self._missing_periods.get(period))
                # 缺失数据的周期：自适应跳过过滤，但在 stats 中记录
                self.last_stats["periods"][period] = {
                    "total": 0, "pass": 0, "ratio": 0.0,
                    "status": "NO_DATA",
                    "reason": reason
                }
                logger.warning(f"[ADAPTIVE] Period [{period}] has no data (reason: {reason}), skipping filter for this period.")
                continue

            if df is None or df.empty:
                logger.warning(f"Period {period} (norm: {p_norm}) data not found or empty.")
                continue
                
            cond = strategy_config['conditions'].get(period, strategy_config['conditions'].get(p_norm))
            if not cond or not cond.get('enabled', True):
                # 周期已勾选但策略未配置该周期或该周期被关闭过滤 → 不作为限制条件参与筛选，仅做展示
                logger.info(f"Period {period} has no condition or is disabled in strategy, skip filtering calculation.")
                total_cnt = len(df)
                self.last_stats["periods"][period] = {
                    "total": total_cnt,
                    "pass": total_cnt,
                    "ratio": 100.0
                }
                continue

            filter_expr = cond.get('filter', '') if isinstance(cond, dict) else str(cond)

            # ⚡ [AUTOMATIC STRATEGY ENRICHMENT] 必须在 fillna(0) 前按需补齐该策略特有缺失列（如 VWAP/nclose/Trends 等）
            if p_norm in ('d', '1d', 'day'):
                df = self.ensure_strategy_ipc_columns(df, strategy_expr=filter_expr, force_refresh=force_refresh)
                with self.lock:
                    self._period_dfs[p_norm] = df
                    self._period_dfs[period] = df

            df_clean = df.fillna(0)

            try:
                from query_engine_util import query_engine
                if query_engine:
                    filtered_df = query_engine.execute(df_clean, filter_expr)
                else:
                    filtered_df = df_clean.query(filter_expr)
                passed_in_period = set(filtered_df.index)
                
                # 获取底表（通常为 'd' 周期）的全量股票，用以对比提取出该周期缺失数据的股票
                base_period = 'd'
                if base_period not in self._period_dfs:
                    base_period = list(self._period_dfs.keys())[0] if self._period_dfs else None
                
                missing_codes = set()
                if base_period and base_period in self._period_dfs:
                    base_codes = set(self._period_dfs[base_period].index)
                    missing_codes = base_codes - set(df_clean.index)
                
                # 缺失数据的股票在交集过滤时默认免检通过，防止误杀
                pass_codes_dict[period] = passed_in_period | missing_codes
                
                total_cnt = len(df_clean)
                pass_cnt = len(filtered_df)
                ratio = (pass_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
                self.last_stats["periods"][period] = {
                    "total": total_cnt,
                    "pass": pass_cnt,
                    "ratio": ratio
                }
                logger.info(f"Period {period} pass count: {pass_cnt}, missing(exempt): {len(missing_codes)}")
            except Exception as e:
                logger.error(f"Error evaluating period {period} condition: {e}")
                # 出现个别条件语法或求解异常时降级放行全量，防止误剔除导致全盘 Hit 归零
                if df_clean is not None and not df_clean.empty:
                    pass_codes_dict[period] = set(df_clean.index)
                
        if not pass_codes_dict:
            # 如果所有勾选的周期在策略中都没有配置过滤规则，默认返回全市场股票且结果中这些周期通过列设为 True
            base_period = 'd'
            if base_period not in self._period_dfs and self._period_dfs:
                base_period = list(self._period_dfs.keys())[0]
            total_market = len(self._period_dfs[base_period]) if base_period in self._period_dfs else 0
            self.last_stats["final"] = {
                "total": total_market,
                "pass": total_market,
                "ratio": 100.0,
                "mode": cross_mode
            }
            if base_period in self._period_dfs:
                result_df = self._period_dfs[base_period].copy()
                for period in active_periods:
                    result_df[f'pass_{period}'] = True
                return result_df
            return pd.DataFrame()
            
        if cross_mode == 'intersection':
            final_codes = set.intersection(*pass_codes_dict.values())
        else:
            final_codes = set.union(*pass_codes_dict.values())
            
        logger.info(f"Final pass count after {cross_mode}: {len(final_codes)}")
        
        # 寻找最短周期作为底表 (优先 d, 然后是存在的最短)
        base_period = 'd'
        if base_period not in self._period_dfs:
            if self._period_dfs:
                base_period = list(self._period_dfs.keys())[0]
            else:
                return pd.DataFrame()
            
        base_df = self._period_dfs[base_period]
        
        # 过滤存在的 codes
        valid_codes = [c for c in final_codes if c in base_df.index]
        result_df = base_df.loc[valid_codes].copy()
        
        for period in active_periods:
            if period in pass_codes_dict:
                result_df[f'pass_{period}'] = result_df.index.isin(pass_codes_dict[period])
            else:
                result_df[f'pass_{period}'] = True
                
        total_market = len(base_df)
        final_pass = len(valid_codes)
        final_ratio = (final_pass / total_market * 100) if total_market > 0 else 0.0
        
        self.last_stats["final"] = {
            "total": total_market,
            "pass": final_pass,
            "ratio": final_ratio,
            "mode": cross_mode
        }
                
        return result_df

    def load_strategies(self):
        loaded_from_file = False
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._strategies = data.get('strategies', [])
                    loaded_from_file = True
            except Exception as e:
                logger.error(f"Failed to load strategies config: {e}")
                
        # 预置高级多周期策略模板列表
        presets = [
            {
                "id": "tpl_macro_trend_ma60_rebound_launch",
                "name": "★ 大周期启动+回踩MA60d企稳次日加速 [日科化学模式]",
                "conditions": {
                    "w": {"filter": "dif > 0 or dif > dea or close > ma20d", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "close > ma201d or dif > dea", "weight": 1.2, "enabled": True},
                    "d": {"filter": "{or: lastl{1-4}d <= 1.06 * ma60{1-4}d and lastl{1-4}d >= 0.94 * ma60{1-4}d} and percent > 2.5 and close > open and (lastv0d > 1.3 * lastv1d or volume > 1.3 * lastv1d) and close > lastp1d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_bottom_oversold_wash_breakout",
                "name": "★ 底部超跌洗盘+缩量企稳+放量拉升 [反转启动]",
                "conditions": {
                    "w": {"filter": "close > lower or dif > dea or close > ma5d", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "close > ma5d and (dif > dea or macd > macdlast1) and close < 1.3 * ma60d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "percent > 1.5 and close > open and close > ma5d and (lastv0d > 1.3 * lastv1d or volume > 1.3 * lastv1d) and (lastv1d < lastv2d or lastv2d < lastv3d) and close < 1.25 * ma20d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_trend_ma20_ma60_pullback_launch",
                "name": "★ 趋势股MA20/MA60整固+低开高走启动 [趋势启动]",
                "conditions": {
                    "w": {"filter": "close > ma20d and (dif > dea or ma5d > ma10d)", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "close > ma201d and close > lastp1d and ma20{1-2}d >= ma60{1-2}d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "ma20d >= ma60d and close >= 0.98 * ma20d and percent > 1.0 and close > open and (lastv0d > 1.2 * lastv1d or volume > lastv1d) and lastv1d <= 1.15 * lastv2d and percent < 7.5", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_multi_day_vol_shrink_rebound",
                "name": "9日多级地量洗盘+低位爆发放量 [全Col多级低吸]",
                "conditions": {
                    "3d": {"filter": "close > ma10d", "weight": 1.2, "enabled": True},
                    "2d": {"filter": "close > ma5d and (dif > dea or k > d)", "weight": 1.1, "enabled": True},
                    "d": {"filter": "{or: lastv{1-3}d < 0.65 * lastv{4-7}d} and lastv0d > 1.35 * lastv1d and percent > 2.0 and close > open and close > ma5d and close < 1.2 * ma20d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_ma_step_resonance_launch",
                "name": "MA20/MA60多级阶梯整固+主力起跳 [多级均线启动]",
                "conditions": {
                    "w": {"filter": "close > ma5d and close > ma20d and dif > dea", "weight": 1.5, "enabled": True},
                    "d": {"filter": "ma20{1-2}d > ma60{1-2}d and {and: abs(per{1-3}d) < 3.5} and lastv0d > 1.4 * lastv1d and percent > 1.8 and close > open and close > lastp1d and percent < 8.0", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_strong_pullback_rebound",
                "name": "强势结构回踩反包与放量启动",
                "conditions": {
                    "2d": {"filter": "strong_structure_score > 60 and {or: lastv{1-2}d > lastv{2-3}d}", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "strong_structure_score > 55", "weight": 1.2, "enabled": True},
                    "d": {"filter": "strong_structure_score > 65 and close > ma5d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_ma_resonance_advanced",
                "name": "多周期均线共振多头 [MA20/MA60多级展开]",
                "conditions": {
                    "m": {"filter": "ma5d > ma10d and close > ma5d", "weight": 1.5, "enabled": True},
                    "w": {"filter": "ma5d > ma10d and ma20{1-2}d > ma60{1-2}d and close > ma5d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "ma5d > ma10d and ma10d > ma20d and ma20{1-3}d > ma60{1-3}d and close > ma201d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_volume_ma_breakout",
                "name": "成交量推升+MA60突破 [lastv+MA列]",
                "conditions": {
                    "w": {"filter": "close > ma60d and lastv1d > lastv2d", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "close > ma201d and {or: lastv{1-2}d > 1.2 * lastv{2-3}d}", "weight": 1.2, "enabled": True},
                    "d": {"filter": "close > ma60d and lastv1d > lastv2d and close > lastp1d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_boll_ma_resonance",
                "name": "BOLL与均线共振突破 [upper+MA列]",
                "conditions": {
                    "45d": {"filter": "close > upper1 or close > hmax", "weight": 1.5, "enabled": True},
                    "w": {"filter": "close > upper1 and ma201d > ma601d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "close > lastp1d and (close > upper or close > upper1)", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_macd_kdj_resonance",
                "name": "多周期MACD与KDJ低位金叉/共振",
                "conditions": {
                    "w": {"filter": "dif > dea and {or: macd{1-3}d > 0}", "weight": 1.5, "enabled": True},
                    "3d": {"filter": "dif > dea and k > d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "dif > dea and k > d and j > 0", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_bottom_reversal",
                "name": "大周期触底 + 小周期启动",
                "conditions": {
                    "m": {"filter": "close > ma10d and close > lastp1d", "weight": 1.5, "enabled": True},
                    "w": {"filter": "close > lastp1d and lastp1d > lastp2d and close > ma5d", "weight": 1.2, "enabled": True},
                    "d": {"filter": "close > ma10d", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            },
            {
                "id": "tpl_pressure_break",
                "name": "大周期压力突破",
                "conditions": {
                    "45d": {"filter": "close > upper1 or close > hmax", "weight": 1.5, "enabled": True},
                    "w": {"filter": "close > upper1", "weight": 1.2, "enabled": True},
                    "d": {"filter": "close > lastp1d and close > upper", "weight": 1.0, "enabled": True}
                },
                "cross_mode": "intersection"
            }
        ]

        write_needed = False
        if not self._strategies:
            self._strategies = presets
            write_needed = True
        else:
            # 自动增量检查并补齐缺失的高级模板
            existing_ids = {s.get('id') for s in self._strategies if isinstance(s, dict)}
            new_templates = [p for p in presets if p['id'] not in existing_ids]
            if new_templates:
                for tpl in reversed(new_templates):
                    self._strategies.insert(0, tpl)
                write_needed = True

        if write_needed:
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump({"strategies": self._strategies}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to auto-save strategy presets: {e}")

        return self._strategies

    def save_strategies(self, strategies: List[dict]) -> bool:
        """保存策略配置"""
        self._strategies = strategies
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump({"strategies": self._strategies}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save strategies config: {e}")
            return False

    def validate_condition(self, filter_str: str, period: str) -> tuple[bool, str]:
        """验证过滤表达式的合法性 (集成 query_engine 自适应语法展开与动态补齐)"""
        if not filter_str.strip():
            return True, "表达式为空"
            
        import re
        from query_engine_util import query_engine
        cleaned_expr = query_engine._preprocess_query(filter_str) if query_engine else filter_str.strip()

        if query_engine and not query_engine._is_balanced(cleaned_expr):
            return False, "❌ 语法错误: 括号或大括号未成对闭合"

        # 1. 如果当前内存中已有对应周期的数据，拷贝以防修改
        if period in self._period_dfs and not self._period_dfs[period].empty:
            try:
                df = self._period_dfs[period].copy()
            except Exception:
                df = self._period_dfs[period]
            if str(period).strip() in ('d', '1d', 'day'):
                df = self.ensure_strategy_ipc_columns(df, strategy_expr=filter_str)
        else:
            # 2. 否则，构造一个包含常用字段的 Dummy DataFrame 进行语法验证
            dummy_cols = [
                'open', 'close', 'high', 'low', 'volume', 'percent', 'ratio', 'lvol',
                'ma5d', 'ma10d', 'ma20d', 'ma30d', 'ma60d', 'ma120d', 'ma250d',
                'lastp1d', 'lastp2d', 'lastp3d', 'lasth1d', 'lasth2d', 'lasth3d',
                'lastv1d', 'lastv2d', 'lastv3d', 'lastv4d', 'lastv5d', 'lastv6d', 'lastv7d', 'lastv8d', 'lastv9d',
                'macd', 'macd1d', 'macd2d', 'macdlast1', 'macdlast2', 'macdlast3', 'macdlast4', 'macdlast5', 'macdlast6',
                'dif', 'dif1d', 'macddif', 'macddif1', 'macddif2', 'macddif3', 'macddif4', 'macddif5', 'macddif6',
                'dea', 'dea1d', 'macddea', 'macddea1', 'macddea2', 'macddea3', 'macddea4', 'macddea5', 'macddea6',
                'k', 'k1d', 'd', 'd1d', 'j', 'j1d', 'kdj_k', 'kdj_d', 'kdj_j', 'rsi',
                'upper', 'lower', 'upper1', 'lower1', 'upper2', 'lower2', 'upper3', 'lower3',
                'ma201d', 'ma202d', 'ma601d', 'ma602d', 'ma603d', 'ma604d', 'ma605d', 'per1d', 'per2d', 'per3d', 'per4d', 'per5d',
                'hmax', 'hmin', 'ptop', 'pbottom', 'pbreak', 'pdays', 'Rank', 'SWL', 'SWS', 'dff', 'dff2', 'dff3'
            ]
            data = {col: [1.0, 2.0] for col in dummy_cols}
            df = pd.DataFrame(data, index=['000001', '000002'])

        # 为验证自动补充表达式中引用的未知变量列，防止校验报错
        mentioned = set(re.findall(r'\b[a-zA-Z_]\w*\b', cleaned_expr))
        py_keywords = {'and', 'or', 'not', 'in', 'is', 'if', 'else', 'True', 'False', 'None', 'df', 'pd', 'np', 'abs', 'max', 'min', 'GREATEST', 'LEAST', 'ABS', 'MAX', 'MIN'}
        for var in (mentioned - py_keywords):
            if var not in df.columns:
                df[var] = 1.0

        try:
            if query_engine:
                query_engine.execute(df, cleaned_expr)
            else:
                df.query(cleaned_expr)
            return True, "✅ 语法验证通过"
        except Exception as e:
            err_msg = str(e).split('\n')[0]
            return False, f"❌ 语法错误: {err_msg}"

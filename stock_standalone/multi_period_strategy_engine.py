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

    def ensure_strategy_ipc_columns(self, df: pd.DataFrame, strategy_expr: str = "", force_refresh: bool = False) -> pd.DataFrame:
        """
        通过 IPC 工厂模式按需抓取策略中所需但 df 中缺失或为初始缺省值的列。
        规则:
        1. 提取策略表达式中的变量列；
        2. 仅向 IPC 提取 Missing 的列（多余列不抓取）；当 force_refresh=True 时强制重刷最新行情列；
        3. 若 IPC 未连接或无该列，执行自动安全兜底。
        """
        if df is None or df.empty:
            return df

        needed_cols = self._extract_cols_from_expr(strategy_expr)
        
        # 判定 df 中真正缺失或需要从 IPC 更新的列
        missing_cols = set()
        for col in needed_cols:
            if force_refresh or col not in df.columns:
                missing_cols.add(col)
            else:
                s = df[col]
                if s.isna().all():
                    missing_cols.add(col)

        if not strategy_expr:
            default_core_cols = {
                'vwap_cum_2d', 'vwap_cum_3d', 'vwap_cum_4d', 'vwap_cum_5d',
                'last_vwap_cum_2d', 'last_vwap_cum_3d', 'last_nclose1d', 'last_nclose3d',
                'Trends', 'nclose', 'sig_bottom', 'sig_launch'
            }
            if force_refresh:
                missing_cols.update(default_core_cols)
            else:
                for col in default_core_cols:
                    if col not in df.columns or df[col].isna().all():
                        missing_cols.add(col)

        if not missing_cols:
            return df

        try:
            import time
            import re
            import numpy as np
            ipc_mgr = get_global_ipc_sync_manager()
            if ipc_mgr is not None:
                ipc_df = ipc_mgr.get_current_df()
                if ipc_df is None or ipc_df.empty:
                    ipc_mgr.request_full_sync()
                    for _ in range(5):
                        time.sleep(0.1)
                        ipc_df = ipc_mgr.get_current_df()
                        if ipc_df is not None and not ipc_df.empty:
                            break

                if ipc_df is not None and not ipc_df.empty:
                    # 构建包含 6 位 zfill 字符串、原始字符串和 int 键的容错 val_map 映射
                    df_codes = df['code'] if 'code' in df.columns else df.index
                    df_code_strs = [str(c).strip().zfill(6) for c in df_codes]

                    for col in missing_cols:
                        target_col = col
                        clean_col = re.sub(r'_(d|1d|2d|3d|4d|5d|w|m|45d|3m)$', '', col)
                        if target_col not in ipc_df.columns:
                            if clean_col in ipc_df.columns:
                                target_col = clean_col
                            elif target_col.endswith('_d') and target_col[:-2] in ipc_df.columns:
                                target_col = target_col[:-2]

                        if target_col in ipc_df.columns:
                            s_ipc = ipc_df[target_col]
                            val_map = {}
                            for k, v in s_ipc.items():
                                sk = str(k).strip()
                                val_map[sk] = v
                                val_map[sk.zfill(6)] = v
                                if sk.isdigit():
                                    val_map[int(sk)] = v

                            ipc_vals = [val_map.get(c_str, val_map.get(orig_c, np.nan)) for c_str, orig_c in zip(df_code_strs, df_codes)]
                            ipc_series = pd.Series(ipc_vals, index=df.index)

                            valid_mask = ipc_series.notna()
                            if col not in df.columns or force_refresh:
                                if col in df.columns:
                                    df.loc[valid_mask, col] = ipc_series[valid_mask]
                                else:
                                    df[col] = ipc_series
                            else:
                                df.loc[valid_mask & df[col].isna(), col] = ipc_series[valid_mask & df[col].isna()]

                            base_alias = col[:-2] if col.endswith('_d') else f"{col}_d"
                            if base_alias not in df.columns or force_refresh:
                                df[base_alias] = df[col]
        except Exception as ex_ipc:
            logger.debug(f"IPC fetch for missing strategy cols failed: {ex_ipc}")

        # 🛡️ 自动安全兜底：如果 IPC 依然没有获取到该列，设置默认安全 fallback 值，防范 query/eval 崩溃
        for col in missing_cols:
            if col not in df.columns or df[col].isna().all():
                c_low = col.lower()
                if 'vwap' in c_low or 'nclose' in c_low or c_low.startswith('lastp') or c_low.startswith('close'):
                    df[col] = df['close'] if 'close' in df.columns else 0.0
                elif c_low.startswith('lasth') or c_low.startswith('h'):
                    df[col] = df['high'] if 'high' in df.columns else (df['close'] if 'close' in df.columns else 0.0)
                elif c_low.startswith('lastl') or (c_low.startswith('l') and not c_low.startswith('lastv')):
                    df[col] = df['low'] if 'low' in df.columns else (df['close'] if 'close' in df.columns else 0.0)
                elif c_low.startswith('ma'):
                    df[col] = df['close'] if 'close' in df.columns else 0.0
                elif 'trends' in c_low:
                    df[col] = 60.0
                elif 'volume' in c_low or 'lastv' in c_low:
                    df[col] = df['volume'] if 'volume' in df.columns else 0.0
                elif 'per' in c_low or 'percent' in c_low:
                    df[col] = df['percent'] if 'percent' in df.columns else 0.0
                else:
                    df[col] = 0.0

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
            df_clean = df.fillna(0)
            
            if not cond or not cond.get('enabled', True):
                # 周期已勾选但策略未配置该周期或该周期被关闭过滤 → 不作为限制条件参与筛选，仅做展示
                logger.info(f"Period {period} has no condition or is disabled in strategy, skip filtering calculation.")
                total_cnt = len(df_clean)
                self.last_stats["periods"][period] = {
                    "total": total_cnt,
                    "pass": total_cnt,
                    "ratio": 100.0
                }
                continue
                
            try:
                filter_expr = cond.get('filter', '') if isinstance(cond, dict) else str(cond)
                # 💥 只有策略中用到的、且当前 df 中 Missing 或 force_refresh 的列才通过 IPC 精准提取并自动补全，多余列不抓取；若无 IPC 数据则自动安全兜底
                df_clean = self.ensure_strategy_ipc_columns(df_clean, filter_expr, force_refresh=force_refresh)

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
            df = self._period_dfs[period].copy()
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

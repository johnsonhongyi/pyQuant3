import pandas as pd
import json
import os
from typing import Dict, List, Optional
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger("MultiPeriodStrategyEngine")

class MultiPeriodStrategyEngine:
    SUPPORTED_PERIODS = ['d', '2d', '3d', 'w', 'm', '45d', '3M']
    
    def __init__(self):
        self._period_dfs: Dict[str, pd.DataFrame] = {}
        self._strategies: List[dict] = []
        self.config_path = "config/multi_period_strategies.json"
        self.last_stats: dict = {}
        
    def load_period_data(self, period: str, top_now: pd.DataFrame) -> pd.DataFrame:
        """加载指定周期数据（复用 tdd.get_append_lastp_to_df）"""
        from JSONData import tdx_data_Day as tdd
        from JohnsonUtil import johnson_cons as ct
        
        # 如果已经加载过该周期，直接复用缓存
        if period in self._period_dfs and not self._period_dfs[period].empty:
            logger.info(f"Reusing cached data for period {period}...")
            return self._period_dfs[period]
            
        # 默认取 60 个 k 线，大周期可以多取
        dl = ct.Resample_LABELS_Days.get(period, 60)
        try:
            logger.info(f"Loading data for period {period}...")
            # 兼容 45d 和 3M 的 resample
            df, _ = tdd.get_append_lastp_to_df(top_now, dl=dl, resample=period)
            
            # 使用 calc_indicators 确保所有均线和计算指标齐全
            from data_utils import calc_indicators
            if df is not None and not df.empty:
                df = calc_indicators(df, logger, resample=period)
                self._period_dfs[period] = df
            return df
        except Exception as e:
            logger.error(f"Failed to load period {period}: {e}")
            return pd.DataFrame()
            
    def set_period_df(self, period: str, df: pd.DataFrame):
        self._period_dfs[period] = df
        
    def evaluate_strategy(self, strategy_config: dict, active_periods: List[str] = None) -> pd.DataFrame:
        if active_periods is None:
            active_periods = list(strategy_config['conditions'].keys())
            
        pass_codes_dict = {}
        
        cross_mode = strategy_config.get('cross_mode', 'intersection')
        self.last_stats = {
            "periods": {},
            "final": {"total": 0, "pass": 0, "ratio": 0.0, "mode": cross_mode}
        }
        
        for period in active_periods:
            if period not in self._period_dfs or self._period_dfs[period].empty:
                logger.warning(f"Period {period} data not found or empty.")
                continue
                
            cond = strategy_config['conditions'].get(period)
            if not cond:
                continue
                
            df = self._period_dfs[period]
            try:
                # 兼容 NaN 处理
                df_clean = df.fillna(0)
                filtered_df = df_clean.query(cond['filter'])
                pass_codes_dict[period] = set(filtered_df.index)
                
                total_cnt = len(df_clean)
                pass_cnt = len(filtered_df)
                ratio = (pass_cnt / total_cnt * 100) if total_cnt > 0 else 0.0
                self.last_stats["periods"][period] = {
                    "total": total_cnt,
                    "pass": pass_cnt,
                    "ratio": ratio
                }
                logger.info(f"Period {period} pass count: {pass_cnt}")
            except Exception as e:
                logger.error(f"Error evaluating period {period} condition: {e}")
                
        if not pass_codes_dict:
            base_period = 'd'
            if base_period not in self._period_dfs and self._period_dfs:
                base_period = list(self._period_dfs.keys())[0]
            total_market = len(self._period_dfs[base_period]) if base_period in self._period_dfs else 0
            self.last_stats["final"] = {
                "total": total_market,
                "pass": 0,
                "ratio": 0.0,
                "mode": cross_mode
            }
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
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._strategies = data.get('strategies', [])
            except Exception as e:
                logger.error(f"Failed to load strategies config: {e}")
                
        if not self._strategies:
            # 预置 6 套模板
            self._strategies = [
                {
                    "id": "tpl_bottom_reversal",
                    "name": "大周期触底 + 小周期启动",
                    "conditions": {
                        "m": {"filter": "close > ma10d and close > lastp1d", "weight": 1.5},
                        "w": {"filter": "close > lastp1d and lastp1d > lastp2d and close > ma5d", "weight": 1.2},
                        "d": {"filter": "close > ma10d", "weight": 1.0}
                    },
                    "cross_mode": "intersection"
                },
                {
                    "id": "tpl_ma_resonance",
                    "name": "均线共振多头",
                    "conditions": {
                        "m": {"filter": "ma5d > ma10d and close > ma5d", "weight": 1.5},
                        "w": {"filter": "ma5d > ma10d and close > ma5d", "weight": 1.2},
                        "d": {"filter": "ma5d > ma10d and ma10d > ma20d and close > ma5d", "weight": 1.0}
                    },
                    "cross_mode": "intersection"
                },
                {
                    "id": "tpl_pressure_break",
                    "name": "大周期压力突破",
                    "conditions": {
                        "45d": {"filter": "close > upper1 or close > hmax", "weight": 1.5},
                        "w": {"filter": "close > upper1", "weight": 1.2},
                        "d": {"filter": "close > lastp1d and close > upper", "weight": 1.0}
                    },
                    "cross_mode": "intersection"
                }
            ]
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump({"strategies": self._strategies}, f, ensure_ascii=False, indent=2)
        return self._strategies

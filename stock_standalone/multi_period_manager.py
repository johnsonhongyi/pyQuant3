import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional

class MultiPeriodManager:
    """
    多周期数据管理器
    支持将不同周期 (D, W, M, 5m等) 的 DataFrame 合并为 MultiIndex 结构，并进行内存优化。
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def optimize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        深度优化 DataFrame 类型以节省内存
        - float64 -> float32
        - int64 -> int32
        """
        initial_mem = df.memory_usage().sum() / (1024**2)
        
        # 处理数值列
        for col in df.columns:
            col_type = df[col].dtype
            if col_type == 'float64':
                df[col] = df[col].astype('float32')
            elif col_type == 'int64':
                # 尝试转换为 int32，如果范围允许
                if df[col].min() > -2147483648 and df[col].max() < 2147483647:
                    df[col] = df[col].astype('int32')
                else:
                    df[col] = df[col].astype('float32') # 无法容纳则转为 float32
                    
        final_mem = df.memory_usage().sum() / (1024**2)
        self.logger.info(f"[MultiPeriod] Memory Optimized: {initial_mem:.2f}MB -> {final_mem:.2f}MB (节省 {((initial_mem-final_mem)/initial_mem)*100:.1f}%)")
        return df

    def merge_periods(self, period_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        将多个周期的 DataFrame 合并为一个 MultiIndex DataFrame
        period_dfs: {'D': df_day, 'W': df_week, 'M': df_month}
        要求所有词典中的 df 索引均包含股票代码 (code/index)
        """
        if not period_dfs:
            return pd.DataFrame()

        processed_dfs = []
        for period, df in period_dfs.items():
            if df.empty:
                continue
            
            # 确保 index 是字符串类型的代码
            df_copy = df.copy()
            if 'code' in df_copy.columns:
                df_copy = df_copy.set_index('code')
            df_copy.index = df_copy.index.astype(str)
            
            # 给列打上多级索引标签 (Period, Metric)
            df_copy.columns = pd.MultiIndex.from_product([[period], df_copy.columns])
            processed_dfs.append(df_copy)

        if not processed_dfs:
            return pd.DataFrame()

        # 按照索引 (股票代码) 横向连接
        # 使用 outer join 确保不丢失股票，由 query 引擎处理缺失值
        combined_df = pd.concat(processed_dfs, axis=1)
        
        # 进行内存优化
        combined_df = self.optimize_dtypes(combined_df)
        
        return combined_df

    def batch_load_all_periods(self, resamples: List[str] = ['d', '2d', '3d', 'w', 'm']) -> pd.DataFrame:
        """
        自动调用外部接口加载所有指定周期的数据并合并。
        """
        from instock_MonitorTK import test_single_thread
        
        dfs = {}
        for rs in resamples:
            try:
                self.logger.info(f"[MultiPeriod] Loading resample: {rs}")
                df = test_single_thread(single=True, resample=rs)
                if df is not None and not df.empty:
                    dfs[rs] = df
            except Exception as e:
                self.logger.error(f"[MultiPeriod] Failed to load {rs}: {e}")
        
        return self.merge_periods(dfs)

    def compute_resonance_score(self, df: pd.DataFrame) -> pd.Series:
        """
        计算“多周期共振评分” (Resonance Score)
        通过向量化运算评估各个周期强度的叠加：
        - 越多周期站上均线/轨道分越高
        - 越多点位同步放量分越高
        """
        if df.empty or not isinstance(df.columns, pd.MultiIndex):
            return pd.Series(dtype=float)
            
        # 健壮地获取当前存在的周期列表，并排除保留前缀
        all_periods = df.columns.get_level_values(0).unique()
        periods = [p for p in all_periods if p != 'SYSTEM']
        
        score = pd.Series(0.0, index=df.index)
        
        # 权重设置：日线权重最高，周线次之
        weights = {'d': 1.0, '2d': 0.8, '3d': 0.7, 'w': 1.2, 'm': 0.5}
        
        for p in periods:
            w = weights.get(p.lower(), 1.0)
            p_df = df[p]
            
            # 1. 价格动能因素 (站上布林上轨或MA)
            if 'percent' in p_df.columns:
                score += p_df['percent'].clip(-10, 10) * 0.2 * w
            
            # 2. 蓄势特征 (如果定义了 upper1/resist)
            resist_col = 'upper1' if 'upper1' in p_df.columns else ('high4' if 'high4' in p_df.columns else None)
            if resist_col and 'close' in p_df.columns:
                # 距离压力位的紧凑度 (越接近或刚突破 分越高)
                dist = (p_df['close'] - p_df[resist_col]) / p_df[resist_col]
                score += np.where((dist > -0.02) & (dist < 0.05), 5.0 * w, 0.0)
            
            # 3. 量能配合 (volume > 1.2)
            vol_col = 'volume' if 'volume' in p_df.columns else 'vol_ratio'
            if vol_col in p_df.columns:
                score += np.where(p_df[vol_col] > 1.2, 3.0 * w, 0.0)

        return score.fillna(0)

    def get_selection_top(self, df: pd.DataFrame, top_n: int = 50, sort_by_resonance: bool = True) -> pd.DataFrame:
        """
        精选功能：返回筛选后的前 top_n 只股票。
        默认使用“共振评分”排序以确保质量。
        """
        if df.empty:
            return df
            
        if sort_by_resonance:
            resonance_score = self.compute_resonance_score(df)
            # 注入临时列用于排序
            df_with_score = df.copy()
            df_with_score[('SYSTEM', 'score')] = resonance_score
            result = df_with_score.sort_values(by=('SYSTEM', 'score'), ascending=False).head(top_n)
            return result.drop(columns=[('SYSTEM', 'score')])
        
        # 降级逻辑：按第一周期的涨幅排序
        first_period = df.columns.levels[0][0]
        if ('percent') in df[first_period].columns:
            return df.sort_values(by=(first_period, 'percent'), ascending=False).head(top_n)
            
        return df.head(top_n)

    def detect_safe_location(self, df: pd.DataFrame, period: str = 'd') -> pd.Series:
        """
        位置安全性检测：必须在低位或稳健位置
        - 价格距离 60 日低点涨幅 < 25% (潜伏区)
        - 价格距离 MA60 偏移 < 12% (非乖离区)
        """
        p_df = df[period] if isinstance(df.columns, pd.MultiIndex) else df
        
        # 1. 距离 MA60
        ma_col = 'ma60d' if 'ma60d' in p_df.columns else 'ma60'
        if ma_col not in p_df.columns:
            return pd.Series(True, index=df.index) # 缺数据则保守通过
            
        near_ma = (p_df['close'] < p_df[ma_col] * 1.12)
        
        # 2. 距离近期低点 (使用 lastl 系列尽量估算)
        l_cols = [f'lastl{i}d' for i in range(1, 30) if f'lastl{i}d' in p_df.columns]
        if l_cols:
            min_l = p_df[l_cols + ['low']].min(axis=1)
            not_too_high = (p_df['close'] < min_l * 1.25)
            return near_ma & not_too_high
            
        return near_ma

    def detect_short_term_surge(self, df: pd.DataFrame, period: str = 'd') -> pd.Series:
        """
        短期涨幅检测 (反追高逻辑): 
        - 5日涨幅 < 15%
        - 20日涨幅 < 35%
        避免一日游和高位接盘
        """
        p_df = df[period] if isinstance(df.columns, pd.MultiIndex) else df
        
        def get_p(n): return p_df[f'lastp{n}d'] if f'lastp{n}d' in p_df.columns else p_df['close']
        
        p5 = get_p(5)
        p20 = get_p(20)
        
        is_surge_5 = (p_df['close'] > p5 * 1.15)
        is_surge_20 = (p_df['close'] > p20 * 1.35)
        
        return ~(is_surge_5 | is_surge_20)

    def detect_pattern_up_down_up(self, df: pd.DataFrame, period: str = 'd') -> pd.Series:
        """
        检测“上下上”结构 (Up-Down-Up) - 最终优化版
        """
        p_df = df[period] if isinstance(df.columns, pd.MultiIndex) else df
        
        def get_c(n): return p_df[f'lastp{n}d'] if f'lastp{n}d' in p_df.columns else p_df['close']
        def get_h(n): return p_df[f'lasth{n}d'] if f'lasth{n}d' in p_df.columns else p_df['high']
        def get_v(n): return p_df[f'lastv{n}d'] if f'lastv{n}d' in p_df.columns else p_df['vol']
        
        c0, v0 = p_df['close'], p_df.get('vol', p_df.get('volume', 1))
        c1, h2, v2 = get_c(1), get_h(2), get_v(2)
        c3 = get_c(3)

        # 1. 结构验证
        up1 = (get_c(2) > c3 * 1.01) # 第一浪
        down = (c1 < h2) & (c1 > get_c(2) * 0.98) # 洗盘
        
        # 2. 挖掘出的启动核心 (0.5% ~ 6% 为佳，超过8%则偏离)
        pct = p_df.get('percent', 0)
        up2 = (pct > 0.5) & (pct < 6.5) & (c0 > c1)
        
        # 3. 限制过快拉升
        is_safe_v = (c0 < c3 * 1.15) 
        
        return pd.Series(up1 & down & up2 & is_safe_v, index=df.index)

    def detect_bottom_consolidation(self, df: pd.DataFrame, period: str = 'd', window: int = 15) -> pd.Series:
        """
        检测“底部盘踞多日” (Bottom Consolidation)
        """
        p_df = df[period] if isinstance(df.columns, pd.MultiIndex) else df
        
        ma_col = 'ma60d' if 'ma60d' in p_df.columns else 'ma60'
        if ma_col not in p_df.columns: return pd.Series(False, index=df.index)
            
        near_ma = (p_df['close'] > p_df[ma_col] * 0.94) & (p_df['close'] < p_df[ma_col] * 1.08)
        
        h_cols = [f'lasth{i}d' for i in range(1, window) if f'lasth{i}d' in p_df.columns]
        l_cols = [f'lastl{i}d' for i in range(1, window) if f'lastl{i}d' in p_df.columns]
        
        if len(h_cols) >= 5:
            max_h = p_df[h_cols + ['high']].max(axis=1)
            min_l = p_df[l_cols + ['low']].min(axis=1)
            narrow_range = (max_h - min_l) / min_l < 0.12 
            # 必须是小阳启动
            is_start = (p_df.get('percent', 0) > 0.3)
            return near_ma & narrow_range & is_start
            
        return near_ma

    def get_ready_to_launch_candidates(self, df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
        """
        获取“蓄势启动”精选个股 (最终策略版)
        """
        if df.empty or not isinstance(df.columns, pd.MultiIndex):
            return pd.DataFrame()

        # 1. 周期对齐
        p_name = 'd' if 'd' in df.columns.levels[0] else df.columns.levels[0][0]
        
        # 2. 基本面/位置过滤
        is_safe_pos = self.detect_safe_location(df, p_name)
        is_not_surge = self.detect_short_term_surge(df, p_name)
        
        # 3. 形态检测
        is_up_down_up = self.detect_pattern_up_down_up(df, p_name)
        is_consolidated = self.detect_bottom_consolidation(df, p_name)
        
        # 4. 量价协同 (挖掘出的最优量能区间: 1.1 ~ 3.0)
        vol_col = (p_name, 'vol_ratio') if (p_name, 'vol_ratio') in df.columns else (p_name, 'volume')
        try:
            is_vol_confirmed = (df[vol_col] >= 1.1) & (df[vol_col] < 3.0)
        except Exception:
            is_vol_confirmed = pd.Series(True, index=df.index)
        
        launch_mask = is_safe_pos & is_not_surge & (is_up_down_up | is_consolidated) & is_vol_confirmed
        
        candidates = df[launch_mask]
        
        # 使用共振评分精选 Top 50
        return self.get_selection_top(candidates, top_n=top_n, sort_by_resonance=True)

# 全局单例
multi_period_mgr = MultiPeriodManager()

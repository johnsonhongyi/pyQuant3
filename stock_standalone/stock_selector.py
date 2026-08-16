# encoding: utf-8
import pandas as pd
import numpy as np
import os
import sys
import datetime
import logging
import sqlite3
import re
import threading
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory
from sys_utils import get_app_root
# 尝试复用决策引擎中的部分逻辑（如果适用）
try:
    from intraday_decision_engine import IntradayDecisionEngine
except ImportError:
    IntradayDecisionEngine = None

import data_utils

class StockSelector:
    """
    强势股筛选器
    
    功能：
    1. 读取 df_all_realtime 数据
    2. 基于技术指标筛选强势股 (趋势、量能、结构)
    3. 生成筛选日志，用于后续分析优化
    """
    
    # --- 全局多线程安全缓区 ---
    _global_candidates_cache: Dict[str, pd.DataFrame] = {}
    _cache_lock = threading.Lock()

    @classmethod
    def get_candidates_cache(cls, key: str) -> Optional[pd.DataFrame]:
        with cls._cache_lock:
            return cls._global_candidates_cache.get(key)

    @classmethod
    def set_candidates_cache(cls, key: str, value: pd.DataFrame):
        with cls._cache_lock:
            cls._global_candidates_cache[key] = value

    # def __init__(self, log_path="selection_log.csv", df: Optional[pd.DataFrame] = None):
    def __init__(self, df: Optional[pd.DataFrame] = None, resample: str = 'd'):
        self.data_path = r'g:\top_all.h5'
        if not os.path.exists(self.data_path):
             # 尝试在当前工程目录下寻找
             local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'top_all.h5')
             if os.path.exists(local_path):
                 self.data_path = local_path
             else:
                 # 尝试在 app root 寻找
                 cwd_path = os.path.join(get_app_root(), 'top_all.h5')
                 if os.path.exists(cwd_path):
                     self.data_path = cwd_path
        
        # self.log_path = log_path # Deprecated: moved to SQLite
        self.df_all_realtime = df  # 实时数据引用
        self.resample = resample  # 周期标识: 'd', '3d', 'w', 'm'
        self._setup_logger()
        
        self.db_logger: Optional['TradingLogger'] = None
        # 初始化数据库记录器
        try:
            from trading_logger import TradingLogger
            self.db_logger = TradingLogger()
        except ImportError:
            self.logger.error("无法导入 TradingLogger，无法使用数据库存储功能")

        # 初始化决策引擎（可选，用于辅助判断）
        self.decision_engine = IntradayDecisionEngine() if IntradayDecisionEngine else None
        self._last_hotspots: List[tuple] = []

    def _setup_logger(self):
        self.logger = LoggerFactory.getLogger()
        # self.logger = LoggerFactory.getLogger('StockSelector')
        # self.logger.setLevel(logging.INFO)

    def load_data(self) -> pd.DataFrame:
        """[COMBINED] 加载数据：结合基础元数据与实时传入的指标数据"""
        # 1. 加载基础数据 (含 HDF5 或 缓存)
        base_df = pd.DataFrame()
        try:
            if os.path.exists(self.data_path):
                base_df = pd.read_hdf(self.data_path, 'top_all')
        except Exception as e:
            self.logger.error(f"加载基础 HDF5 数据失败: {e}")

        if base_df.empty:
            # 尝试从 scraper 缓存加载作为备选基础
            try:
                from scraper_55188 import load_cache
                base_df = load_cache()
            except Exception as e:
                self.logger.warning(f"加载 scraper 缓存作为基础数据失败: {e}")

        # 2. 如果没有实时数据，直接返回基础数据
        if self.df_all_realtime is None or self.df_all_realtime.empty:
            return base_df

        # 3. 如果没有基础数据，直接使用实时数据
        if base_df.empty:
            return self.df_all_realtime.copy()
        
        # 4. 结合逻辑：以实时数据 (rt_df) 为准，补齐/更新指标
        try:
            rt_df = self.df_all_realtime.copy()
            # [FIX] 避免 index 名与 column 名冲突
            if rt_df.index.name == 'code':
                rt_df.index.name = 'code_rt_idx'
                
            if 'code' not in rt_df.columns:
                rt_df['code'] = rt_df.index.astype(str)
            
            if base_df.index.name == 'code':
                base_df.index.name = 'code_base_idx'
                
            if 'code' not in base_df.columns:
                base_df['code'] = base_df.index.astype(str)
            
            # 确保 code 格式一致 (6位)
            base_df['code'] = base_df['code'].apply(lambda x: str(x).zfill(6))
            rt_df['code'] = rt_df['code'].apply(lambda x: str(x).zfill(6))
            
            # [SYNC-PRIORITY] 定义需要从实时数据中强制同步/覆盖的指标列
            # sync_cols = ['trade', 'price', 'percent', 'change_pct', 'vol', 'amount', 'ratio', 'high', 'low', 'open', 'lastp1d', 'last6vol', 'lastbuy',
            #         'volume', 'close', 'buy', 'lastp', 'llastp', 'couts'
            #         ]
            sync_cols = [
                # --- 同步 / 展示 ---
                'trade', 'price', 'percent', 'change_pct',
                'vol', 'amount', 'ratio', 'high', 'low', 'open',
                'lastp1d', 'last6vol', 'lastbuy','category',

                # --- calc_indicators 输入依赖 ---
                'volume', 'close', 'buy', 'lastp', 'llastp', 'couts',
                
                # --- [NEW] 重心与历史因子同步 (用于超短结构) ---
                'lasth1d', 'lastl1d', 'lasto1d', 'lastp2d',
                'lasth2d', 'lastl2d', 'lasto2d', 'lastp3d',
                'ma5d', 'ma51d',
            ]
            sync_cols = [c for c in sync_cols if c in rt_df.columns]
            
            # 剔除基础数据中的旧列，防止 merge 产生重复或后缀列
            base_df_clean = base_df.drop(columns=[c for c in sync_cols if c in base_df.columns])
            
            self.logger.info(f"结合实时数据：同步 {len(sync_cols)} 个核心指标")
            combined_df = pd.merge(base_df_clean, rt_df[['code'] + sync_cols], on='code', how='left')
            
            # [FIX] 重新设置索引为 code，确保 downstream 逻辑（如 iterrows）取到的是代码而非 RangeIndex
            if 'code' in combined_df.columns:
                combined_df.set_index('code', inplace=True, drop=False)

            # [RENAME-MAP] 响应用户反馈：处理 volume (量比) 与 vol (成交量) 的歧义
            # if 'volume' in combined_df.columns:
            #     combined_df.rename(columns={'volume': 'vol_ratio'}, inplace=True)

            # if 'last6vol' in combined_df.columns:
            #     combined_df.columns:['vol_ratio'] = np.where(combined_df['last6vol'] > 0,combined_df['volume'] / combined_df['last6vol'],0.0).round(1)
            
            if {'last6vol', 'volume'}.issubset(combined_df.columns):
                ratio = combined_df['volume'] / combined_df['last6vol']
                combined_df['vol_ratio'] = ratio.replace([np.inf, -np.inf], 0).fillna(0).round(1)
            else:
                combined_df['vol_ratio'] = 0.0

            # 将实时采集的 vol 映射为 volume (成交量) 和 amount (如果缺失)
            if 'vol' in combined_df.columns:
                combined_df['volume'] = combined_df['vol']
                if 'amount' not in combined_df.columns:
                    # 兜底：如果 amount 缺失，使用 vol 作为临时 amount (若 vol 已经是额) 或根据价格估算
                    combined_df['amount'] = combined_df['vol']
            
            return combined_df
        except Exception as e:
            self.logger.error(f"结合数据集失败: {e}")
            
        return base_df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """补充必要的计算指标 (明确调用数据中心计算链)"""
        if df.empty:
            return df

        # 确保基础数值转换
        cols_to_fix = ['close', 'open', 'high', 'low', 'volume', 'amount']
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # [FIX] 如果缺少核心列（如 volume），跳过复杂的计算链，避免 KeyError
        if 'volume' not in df.columns:
            # 尝试从 scraper 字段映射
            if 'change_pct' in df.columns:
                df['percent'] = df['change_pct']
            return df
            
        # [FIX] 兼容实时数据的列名 (实时数据常使用 'trade' 或 'price' 表示现价)
        if 'close' not in df.columns:
            if 'trade' in df.columns:
                df['close'] = df['trade']
            elif 'price' in df.columns:
                df['close'] = df['price']
        
        if 'percent' not in df.columns and 'change_pct' in df.columns:
            df['percent'] = df['change_pct']

        # 调用 data_utils 中的标准计算链 (包含量能扩缩逻辑)
        # resample 使用实例化时传入的参数
        # try:
        #     df = data_utils.calc_indicators(df, self.logger, resample=self.resample)
        # except Exception as e:
        #     self.logger.warning(f"data_utils.calc_indicators skipped: {e}")
        
        return df

    def get_historical_selected_codes(self, days: int = 5) -> Dict[str, int]:
        """获取过去 N 天被选中的股票频次"""
        if self.db_logger is None:
            return {}
        
        try:
            # 获取最近 N 天的所有记录
            # 简单起见，从 signal_history 或 selection_history 中取
            # 这里使用 selection_history 比较贴切
            conn = sqlite3.connect(self.db_logger.db_path)
            query = f"SELECT code, COUNT(*) as cnt FROM selection_history WHERE date >= date('now', '-{days} days') AND date < date('now') GROUP BY code"
            df_hist = pd.read_sql_query(query, conn)
            conn.close()
            return dict(zip(df_hist['code'], df_hist['cnt']))
        except Exception as e:
            self.logger.error(f"获取历史选股统计失败: {e}")
            return {}
    def get_selection_dates(self) -> List[str]:
        """获取所有有选股记录的日期列表"""
        if self.db_logger is None:
            return []
        
        try:
            conn = sqlite3.connect(self.db_logger.db_path)
            query = "SELECT DISTINCT date FROM selection_history ORDER BY date DESC"
            df_hist = pd.read_sql_query(query, conn)
            conn.close()
            return df_hist['date'].tolist()
        except Exception as e:
            self.logger.error(f"获取选股历史日期统计失败: {e}")
            return []

    def load_popularity_profile(self, lookback_days: int = 7) -> Dict[str, Dict[str, Any]]:
        """
        [NEW] 加载全网人气共振实时与多日历史持续性画像
        1. 实时缓存: popularity_resonance_cache.json (东财/同花顺/淘股吧/龙虎榜)
        2. 历史归档: datacsv/popularity_resonance_*.csv.gz (多日历史热度沉淀与连榜天数)
        """
        pop_profile: Dict[str, Dict[str, Any]] = {}
        
        # 1. 尝试读取实时 popularity_resonance_cache.json
        app_root = get_app_root()
        cache_paths = [
            os.path.join(app_root, "popularity_resonance_cache.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "popularity_resonance_cache.json"),
            os.path.join(os.getcwd(), "popularity_resonance_cache.json")
        ]
        
        realtime_cache = {}
        for cp in cache_paths:
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        realtime_cache = json.load(f)
                    break
                except Exception as e:
                    self.logger.debug(f"读取人气缓存失败 {cp}: {e}")
        
        # 解析实时共振
        res_list = realtime_cache.get("resonance_results", [])
        for item in res_list:
            c = str(item.get("code", "")).zfill(6)
            if not c: continue
            plat_cnt = int(item.get("platforms", 0))
            sc = int(item.get("score", 0))
            pop_profile[c] = {
                "resonance_score": sc,
                "platforms": plat_cnt,
                "details": str(item.get("details", "")),
                "streak_days": 1,
                "is_resonance": (plat_cnt >= 2 or sc >= 200)
            }
        
        # 2. 扫描 datacsv/popularity_resonance_*.csv.gz 统计多日持续上榜天数 (streak_days)
        csv_dirs = [
            os.path.join(app_root, "datacsv"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "datacsv"),
            os.path.join(os.getcwd(), "datacsv")
        ]
        
        hist_files = []
        for d in csv_dirs:
            if os.path.exists(d):
                for fname in os.listdir(d):
                    if fname.startswith("popularity_resonance_") and (fname.endswith(".csv.gz") or fname.endswith(".csv")):
                        hist_files.append(os.path.join(d, fname))
                if hist_files:
                    break
        
        hist_files.sort(reverse=True)
        recent_files = hist_files[:lookback_days]
        
        code_appear_count = {}
        for fpath in recent_files:
            try:
                df_pop_day = pd.read_csv(fpath, usecols=['code'])
                for c_val in df_pop_day['code'].dropna():
                    c_clean = str(c_val).strip().zfill(6)
                    code_appear_count[c_clean] = code_appear_count.get(c_clean, 0) + 1
            except Exception:
                pass
        
        # 合并多日持续性天数
        for c, cnt in code_appear_count.items():
            if c in pop_profile:
                pop_profile[c]["streak_days"] = max(pop_profile[c]["streak_days"], cnt)
            else:
                pop_profile[c] = {
                    "resonance_score": 0,
                    "platforms": 0,
                    "details": "历史人气榜",
                    "streak_days": cnt,
                    "is_resonance": False
                }
                
        return pop_profile

    def _calc_trend_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        [极限向量化] 计算趋势质量指标 (TQI & Pulse Frequency)
        利用宽表历史字段 (lastp1d...lastp10d) 进行横向矢量计算
        """
        if df.empty:
            return df
        
        n_days = 10 # 宽表通常包含最近 10 日历史
        
        # 1. 涨跌比 (Up-Down Ratio) - 更多涨，更少跌
        up_count = pd.Series(0, index=df.index)
        # 获取现价列
        curr_p = df['trade'] if 'trade' in df.columns else (df['price'] if 'price' in df.columns else df.get('close', 0.0))
        
        # 比较: 现价 vs 昨收, 昨收 vs 前收...
        up_count += (curr_p > df['lastp1d']).astype(int) if 'lastp1d' in df.columns else 0
        for i in range(1, n_days):
            c_curr = f'lastp{i}d'
            c_prev = f'lastp{i+1}d'
            if c_curr in df.columns and c_prev in df.columns:
                up_count += (df[c_curr] > df[c_prev]).astype(int)
        
        df['up_ratio'] = up_count / n_days
        
        # 2. 异动频率 (Pulse Frequency) - 近期大阳或大放量次数
        pulse_count = pd.Series(0, index=df.index)
        # 判定标准: 涨幅 > 4% 或 虚拟量比 > 1.8
        pct_curr = df['percent'] if 'percent' in df.columns else pd.Series(0, index=df.index)
        vol_ratio = df['volume'] if 'volume' in df.columns else pd.Series(1.0, index=df.index)
        
        # 使用 np.where 确保标量与向量混合运算的安全
        pulse_count += np.where((pct_curr > 4.0) | (vol_ratio > 1.8), 1, 0)
        
        # 历史脉冲 (利用 per1d, per2d... 如果存在)
        for i in range(1, n_days):
            c_per = f'per{i}d'
            if c_per in df.columns:
                pulse_count += np.where(df[c_per] > 4.0, 1, 0)
        
        df['pulse_freq'] = pulse_count / n_days
        
        # 3. 趋势强度评分 (TQI)
        # 权重: 涨跌比(60%) + 异动频率(40%)
        df['tqi_score'] = (df['up_ratio'] * 60 + df['pulse_freq'] * 40).round(1)
        
        return df

    def filter_strong_stocks(self, df: pd.DataFrame, today: Optional[str] = None, top10: int = 10) -> pd.DataFrame:
        """执行优化后的筛选逻辑 (支持分时自适应流动性门槛、板块军团梯队、多周期通道挤压突破与竞价抢跑)"""
        resample = self.resample # 使用当前实例的周期标识
        if df.empty:
            return df
            
        # 0. 预计算趋势质量指标 (分级基础)
        df = self._calc_trend_quality(df)

        if today is None:
            today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 1. 动态时段自适应流动性门槛与特权豁免
        now_str = datetime.datetime.now().strftime("%H:%M")
        if now_str < "09:35":
            dyn_amount_threshold = 15000000 # 1500万 (早盘竞价与开盘秒板窗口)
        elif now_str < "10:00":
            dyn_amount_threshold = 35000000 # 3500万 (早盘快速发酵窗口)
        else:
            dyn_amount_threshold = 80000000 # 8000万 (盘中常态门槛)

        # 基础活跃度过滤 (非停牌，成交额满足动态门槛 或 具备涨停/爆发特权)
        mask = pd.Series(True, index=df.index)
        if 'volume' in df.columns:
            mask &= (df['volume'] > 0)
        
        if 'amount' in df.columns:
            amt = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
            pct_col = pd.to_numeric(df.get('per1d', df.get('percent', df.get('pct', df.get('change_pct', 0)))), errors='coerce').fillna(0)
            ratio_col = pd.to_numeric(df.get('ratio', df.get('volume_ratio', 1.0)), errors='coerce').fillna(1.0)
            
            # 特权豁免条件：涨停、大阳抢跑、高量比异动
            is_limit_up = (pct_col >= 9.2) | (pct_col >= 19.0) # 主板或创业/科创板涨停
            is_surge = (pct_col >= 4.5) & (ratio_col >= 1.5)  # 大阳且放量
            is_exempt = is_limit_up | is_surge
            
            # 满足动态金额 或 满足特权豁免
            mask &= ((amt >= dyn_amount_threshold) | is_exempt)
            
        df_active = df[mask].copy()
        if df_active.empty:
            self.logger.info(f"无满足流动性/特权要求的股票 (时段门槛: {dyn_amount_threshold/1e4:.0f}万)")
            return pd.DataFrame()
        
        # 获取历史选股频次
        hist_counts = self.get_historical_selected_codes(days=5)
        # 加载全网人气共振与多日持续性画像 (东财/同花顺/淘股吧/龙虎榜 + 历史连榜天数)
        pop_profile = self.load_popularity_profile(lookback_days=7)

        # --- 2. 板块军团爆发深度分析与梯队构建 (Sector Squadron & Echelon Engine) ---
        concept_dict = {}
        for code_val, row in df_active.iterrows():
            raw_c = row.get('category', row.get('sector', ''))
            if pd.isna(raw_c) or str(raw_c).lower() == 'nan': continue
            cats = [c.strip() for c in re.split('[;|]', str(raw_c)) if c.strip() and c.strip() != '0']
            if not cats and isinstance(raw_c, str):
                cats = [c.strip() for c in re.split('[;,| ]', raw_c) if c.strip() and c.strip() != '0']
            
            row_pct = float(row.get('per1d', row.get('percent', row.get('pct', row.get('change_pct', 0)))))
            row_amt = float(row.get('amount', 0))
            code_s = str(row.get('code', code_val)).zfill(6)
            
            for c in cats:
                if c not in concept_dict:
                    concept_dict[c] = {
                        'stocks': [],
                        'limit_up_count': 0,
                        'surge_count': 0,
                        'total_amount': 0.0,
                        'pcts': []
                    }
                concept_dict[c]['stocks'].append({
                    'code': code_s,
                    'pct': row_pct,
                    'amount': row_amt,
                    'name': str(row.get('name', ''))
                })
                concept_dict[c]['pcts'].append(row_pct)
                concept_dict[c]['total_amount'] += row_amt
                if row_pct >= 9.2:
                    concept_dict[c]['limit_up_count'] += 1
                elif row_pct >= 4.5:
                    concept_dict[c]['surge_count'] += 1

        # 计算板块综合热度得分：(涨停数*3 + 大阳数*1.5 + 平均涨幅)
        concept_scores = []
        for c, stats in concept_dict.items():
            if len(stats['pcts']) >= 2:
                avg_pct = sum(stats['pcts']) / len(stats['pcts'])
                heat_score = stats['limit_up_count'] * 3.0 + stats['surge_count'] * 1.5 + avg_pct
                concept_scores.append((c, heat_score, avg_pct, stats['limit_up_count'], stats['stocks'], stats['total_amount']))

        concept_scores.sort(key=lambda x: x[1], reverse=True)
        top_hot_names = [x[0] for x in concept_scores[:top10]]
        self.logger.info(f"Top {top10} Hot Concepts: {[(x[0], round(x[1], 1), f'涨停:{x[3]}') for x in concept_scores[:top10]]}")
        self._last_hotspots = [(x[0], x[2]) for x in concept_scores]

        # 梯队角色映射字典
        echelon_map: Dict[str, Dict[str, Any]] = {} # code -> {'role': '空间龙头/主线先锋/主线中军/弹性标的', 'theme': '光通信', 'bonus': int}
        
        # 识别超级主线 (涨停 >= 2 或 热度排名 Top 5)
        for rank_idx, (c_name, heat_sc, avg_p, lu_cnt, st_list, tot_amt) in enumerate(concept_scores[:top10]):
            st_list.sort(key=lambda x: (x['pct'], x['amount']), reverse=True)
            # 1. 主线先锋 (前 2 名涨幅最高且 >= 5% 的标的)
            for s in st_list[:2]:
                if s['pct'] >= 4.5:
                    code_key = s['code']
                    if code_key not in echelon_map or echelon_map[code_key]['bonus'] < 70:
                        echelon_map[code_key] = {
                            'role': '【主线先锋】',
                            'theme': c_name,
                            'bonus': 70
                        }
            
            # 2. 主线中军 (板块内成交额 Top 2 且涨幅 >= 2% 的容量标的)
            st_by_amt = sorted(st_list, key=lambda x: x['amount'], reverse=True)
            for s in st_by_amt[:2]:
                if s['amount'] >= 300000000 and s['pct'] >= 2.0: # 成交额 >= 3亿
                    code_key = s['code']
                    if code_key not in echelon_map:
                        echelon_map[code_key] = {
                            'role': '【主线中军】',
                            'theme': c_name,
                            'bonus': 50
                        }
                        
            # 3. 20cm 弹性先锋 (300/688 开头且涨幅 >= 8%)
            for s in st_list:
                if (s['code'].startswith('30') or s['code'].startswith('68')) and s['pct'] >= 8.0:
                    code_key = s['code']
                    if code_key not in echelon_map or echelon_map[code_key]['bonus'] < 60:
                        echelon_map[code_key] = {
                            'role': '【弹性先锋】',
                            'theme': c_name,
                            'bonus': 60
                        }

        selected_records = []

        for idx, row in df_active.iterrows():
            data = row.to_dict()
            code_str = str(row.get('code', idx)).zfill(6)
            data['code'] = code_str

            price = float(data.get('price', data.get('trade', data.get('close', 0))))
            pct = float(data.get('per1d', data.get('percent', data.get('pct', data.get('change_pct', 0)))))
            ratio = float(data.get('ratio', data.get('volume_ratio', 0))) # 核心量比
            lastp1d = float(data.get('lastp1d', 0))

            last6v = float(data.get('last6vol', 0))
            vol_raw = float(data.get('vol', data.get('volume', 0)))
            vol_ratio_l6 = vol_raw / last6v if last6v > 0 else 0.0

            if pct == 0 and lastp1d > 0:
                pct = round((price - lastp1d) / lastp1d * 100, 2)
            data['percent'] = pct
            
            reason = []
            score = 0
            echelon_info = echelon_map.get(code_str, None)
            
            # --- A. 板块梯队暴击加分与角色赋予 ---
            if echelon_info:
                score += echelon_info['bonus']
                reason.append(f"{echelon_info['role']}({echelon_info['theme']})")

            # --- B. 趋势与结构分析 ---
            try:
                ma5 = float(data.get('ma5d', 0))
                ma10 = float(data.get('ma10d', 0))
                ma20 = float(data.get('ma20d', 0))
                ma60 = float(data.get('ma60d', 0))
                
                high_p = float(data.get('high', 0))
                low_p = float(data.get('low', 0))
                open_p = float(data.get('open', 0))
                amplitude = (high_p - low_p) / lastp1d * 100 if lastp1d > 0 else 0
                
                # 破位检测
                is_broken = False
                if ma20 > 0 and price < ma20 * 0.985:
                    is_broken = True
                if ma60 > 0 and price < ma60 * 0.98:
                    is_broken = True
                
                if is_broken and pct < 2.0:
                    score -= 100
                    reason.append("趋势破位")
                
                # 1. 均线状态
                if ma5 > 0 and ma10 > 0 and ma20 > 0:
                    if ma5 > ma10 > ma20:
                        score += 30
                        reason.append("多头排列")
                
                ma5_1d = float(data.get('ma51d', 0))
                if ma5 > 0 and ma5_1d > 0 and ma5 > ma5_1d:
                    score += 15
                    reason.append("均线向上")

                # 2. 多周期通道挤压与爆量突破 (Squeeze & Launch)
                upper1d = float(data.get('upper1', data.get('ch_upper', 0)))
                lower1d = float(data.get('lower1', data.get('ch_lower', 0)))
                mid1d = float(data.get('mid1', data.get('ch_mid', (upper1d + lower1d)/2 if upper1d > 0 and lower1d > 0 else 0)))
                
                is_squeeze_breakout = False
                if upper1d > 0 and mid1d > 0 and lower1d > 0:
                    band_width = (upper1d - lower1d) / mid1d
                    # 通道宽度处于挤压期 (< 12%) 且今日大阳突破上轨
                    if band_width < 0.12 and price > upper1d * 0.995 and (ratio > 1.5 or vol_ratio_l6 > 1.5):
                        is_squeeze_breakout = True
                        score += 65
                        reason.append("通道挤压爆量突破")
                    elif price > upper1d:
                        score += 25
                        reason.append("突破通道上轨")

                # 3. 突破前高判断
                last_h1d = float(data.get('lasth1d', data.get('lastp1d', 0)))
                last_h2d = float(data.get('lasth2d', 0))
                if last_h1d > 0 and price > last_h1d * 1.01:
                    score += 25
                    reason.append("突破昨日高点")
                elif last_h2d > 0 and price > last_h2d:
                    score += 15
                    reason.append("突破前两日高点")

                # 4. 动能与连涨 (连板/主升空间龙头判定)
                limit_days = getattr(cct, 'compute_lastdays', 5)
                consecutive_rise = 0
                if lastp1d > 0 and price > lastp1d:
                    consecutive_rise += 1
                    for d in range(1, limit_days):
                        curr_p = float(data.get(f'lastp{d}d', 0))
                        prev_p = float(data.get(f'lastp{d+1}d', 0))
                        if prev_p > 0 and curr_p > prev_p:
                            consecutive_rise += 1
                        else:
                            break
                
                # 连板/空间龙头赋予超高优先级
                last_pct1d = float(data.get('per1d', 0))
                if last_pct1d >= 9.2 and pct >= 9.2:
                    score += 80
                    reason.append("【空间龙头连板】")
                elif consecutive_rise >= 3:
                    score += consecutive_rise * 10
                    reason.append(f"{consecutive_rise}连阳主升")
                
                # 5. 早盘竞价与开盘抢跑异动 (09:25 - 09:35 Sniffer)
                if open_p > 0 and lastp1d > 0:
                    open_pct = (open_p - lastp1d) / lastp1d * 100
                    if 2.0 <= open_pct <= 8.5 and price >= open_p and (ratio > 1.8 or vol_ratio_l6 > 1.8):
                        score += 45
                        reason.append("竞价抢跑强启动")

                # 6. 回调买点 (缩量回踩 MA5/10)
                is_pullback = False
                if ma5 > 0 and 0 <= (price - ma5) / ma5 < 0.02:
                    if ratio < 1.1 and price >= ma5:
                        score += 30
                        reason.append("强势缩量回踩")
                        is_pullback = True

                # 7. 资金成交额
                amount = float(data.get('amount', 0))
                if amount > 500000000:
                    score += 20
                    reason.append("主力大资金")
                elif amount > 200000000:
                    score += 10

            except Exception as e:
                self.logger.error(f"Error filtering {code_str}: {e}")

            # --- C. 今日涨跌与量能精细判断 ---
            if 3.0 <= pct <= 8.5:
                score += 20
                if ratio > 1.2: score += 10
            elif pct > 9.2:
                score += 35 # 涨停大幅加分
                reason.append("冲击涨停/封死")
            
            if 1.5 < ratio < 5.0:
                score += 20
                reason.append("健康放量")
            elif ratio >= 5.0:
                score += 15
                reason.append("巨量爆发")

            # --- D. 全网人气共振与多日持续性画像 (Popularity Resonance & Persistence) ---
            pop_info = pop_profile.get(code_str)
            is_pop_leader = False
            if pop_info:
                p_platforms = pop_info.get('platforms', 0)
                p_streak = pop_info.get('streak_days', 0)
                p_details = pop_info.get('details', '')
                
                # 1. 多平台共振加分
                if p_platforms >= 3:
                    score += 50
                    reason.append(f"【全网三台共振】({p_details})")
                    is_pop_leader = True
                elif p_platforms == 2:
                    score += 30
                    reason.append(f"【双台共振】({p_details})")
                    is_pop_leader = True
                elif pop_info.get('resonance_score', 0) >= 200:
                    score += 25
                    reason.append("【高人气标的】")
                    is_pop_leader = True

                # 2. 多日持续性在榜天数加成 (龙头持续性)
                if p_streak >= 3:
                    score += 40
                    reason.append(f"【多日持续人气龙(连榜{p_streak}天)】")
                    is_pop_leader = True
                elif p_streak == 2:
                    score += 20
                    reason.append("【2日连榜人气】")

                # 3. 走势与人气健康度风控 (防止高位破位接盘散户诱多)
                if is_broken and pct < 1.0:
                    score -= 60
                    reason.append("高位派发(诱多风险)")
                    is_pop_leader = False

            # --- E. 走势分级与状态标签 ---
            hist_cnt = hist_counts.get(code_str, 0)
            tqi = data.get('tqi_score', 0)
            up_r = data.get('up_ratio', 0)
            stage = int(data.get('cycle_stage', 2))
            
            status_tag = "蓄势"
            grade = "C"
            
            # 直通特权判定：空间龙头、主线先锋、通道挤压爆量突破、竞价抢跑、全网共振人气龙
            is_vip_launch = (echelon_info is not None) or is_squeeze_breakout or ("空间龙头" in "|".join(reason)) or ("竞价抢跑" in "|".join(reason)) or (is_pop_leader and pct >= 3.5)
            
            if score >= 120 or is_vip_launch:
                grade = "S"
                if echelon_info:
                    status_tag = echelon_info['role']
                elif is_pop_leader and pct >= 3.5:
                    status_tag = "【人气共振龙】"
                elif "空间龙头" in "|".join(reason):
                    status_tag = "【空间龙头】"
                elif is_squeeze_breakout:
                    status_tag = "通道爆量突破"
                else:
                    status_tag = "主升加速"
            elif score >= 85:
                grade = "A"
                status_tag = "启动浪" if not is_pullback else "上升中继"
            elif score >= 60:
                grade = "B"
                status_tag = "蓄势待发"
            else:
                grade = "C"
                status_tag = "震荡蓄势"

            if not is_broken:
                if grade == "S": score += 30
                elif grade == "A": score += 20

            # 最终筛选门槛 (score >= 70，确保龙头与主线先锋绝不遗漏)
            if score >= 70 and reason:
                reason = list(dict.fromkeys(reason))
                
                # 自动生成操作建议
                if pct >= 9.2:
                    reason.append("建议:涨停持股/排单")
                elif is_vip_launch and pct > 4.0:
                    reason.append("建议:右侧追入/主线跟进")
                elif is_pullback:
                    reason.append("建议:低吸关注")
                else:
                    reason.append("建议:择机介入")
                
                advices = [r for r in reason if r.startswith("建议:")]
                others = [r for r in reason if not r.startswith("建议:")]
                final_reason = "|".join(others + advices)
                
                record = {
                    'date': today,
                    'code': code_str,
                    'name': data.get('name', ''),
                    'score': score,
                    'price': price,
                    'percent': pct,
                    'change_pct': pct,
                    'zhuli_rank': data.get('zhuli_rank', '-'),
                    'ratio': ratio,
                    'volume': round(vol_ratio_l6, 1),
                    'amount': amount,
                    'reason': final_reason,
                    'status': status_tag,
                    'grade': grade,
                    'pop_streak': pop_info.get('streak_days', 0) if pop_info else 0,
                    'pop_platforms': pop_info.get('platforms', 0) if pop_info else 0,
                    'pop_score': pop_info.get('resonance_score', 0) if pop_info else 0,
                    'pop_details': pop_info.get('details', '') if pop_info else '',
                    'tqi': tqi,
                    'ma5': ma5 if 'ma5' in locals() else 0.0,
                    'ma10': ma10 if 'ma10' in locals() else 0.0,
                    'open': float(data.get('open', 0)),
                    'category': "|".join([c.strip() for c in re.split('[;|]', str(data.get('category', ''))) if c.strip()]),
                    'stage': stage, 
                    'resample': resample,
                    'rank': int(data.get('Rank', data.get('rank', 0))),
                    'yesterday_pct': float(data.get('per1d', 0.0)),
                    'sum_perc': float(data.get('sum_perc', 0.0)),
                    'win': float(data.get('win', 0.0)),
                    'user_status': '待定',
                    'user_reason': ''
                }
                selected_records.append(record)

        df_selected = pd.DataFrame(selected_records)
        if df_selected.empty:
            return pd.DataFrame(columns=['date', 'code', 'name', 'score', 'price', 'percent', 'ratio', 'volume', 'amount', 'reason', 'status', 'grade', 'tqi', 'ma5', 'ma10', 'category', 'resample'])

        # 排序：优先按 grade (S > A > B > C)、score、amount 排序
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4}
        df_selected['grade_rank'] = df_selected['grade'].map(lambda x: grade_order.get(x, 9))
        df_selected.sort_values(by=['grade_rank', 'score', 'amount'], ascending=[True, False, False], inplace=True)
        df_selected.drop(columns=['grade_rank'], inplace=True)
        
        # 保留优质标的
        df_selected = df_selected.head(cct.stock_select_limit)
        self.logger.info(f"筛选完成，命中 {len(df_selected)} 只股票 (分级S/A/B, Top {cct.stock_select_limit})")
        
        # 保存日志
        self.save_selection_log(df_selected)
        return df_selected

    def get_market_hotspots(self) -> List[tuple]:
        """获取当前市场热点板块及其平均涨幅"""
        if not hasattr(self, '_last_hotspots') or not self._last_hotspots:
            # 运行筛选逻辑以初始化热点
            df = self.load_data()
            if df.empty: return []
            df = self.calculate_indicators(df)
            self.filter_strong_stocks(df)
        
        return getattr(self, '_last_hotspots', [])

    def save_selection_log(self, df_selected: pd.DataFrame):
        """保存筛选结果到数据库"""
        if df_selected.empty or self.db_logger is None:
            return
            
        # 强制 key 为 str
        records = [{str(k): v for k, v in record.items()} for record in df_selected.to_dict('records')]
        self.db_logger.log_selection(records)
        
        self.logger.info(f"筛选结果已保存至数据库 (SQLite): {len(records)} 条")
        
    def get_candidate_codes(self) -> List[str]:
        """获取筛选出的代码列表，供 stock_live_strategy 调用"""
        df = self.get_candidates_df()
        if df.empty:
            return []
        return df['code'].tolist()

    def get_candidates_df(self, force: bool = False, logical_date: Optional[str] = None, resample: Optional[str] = None) -> pd.DataFrame:
        """
        获取筛选结果。
        :param force: 是否强制重新运行策略。如果为 False，则优先从数据库加载存量数据。
        :param logical_date: 逻辑日期，格式 'YYYY-MM-DD'。如果提供，则使用此日期进行数据查询；否则使用系统当前日期。
        :param resample: 如果提供，则覆盖实例的周期标识。
        """
        if resample:
            self.resample = resample
        
        # if not logical_date:
        #     is_trading = cct.get_work_time_duration()
        #     # 不开市是最近的交易日, 开市交易期用的是上一个交易日
        #     logical_date = cct.get_last_trade_date() if is_trading else cct.get_today()
            
        # target_date = logical_date

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")

        if not logical_date:
            # 判断今天是否交易日（而不是是否在交易时间段）
            is_trade_day = cct.get_trade_date_status()  # ✅ 用这个

            if is_trade_day:
                logical_date = today_str
            else:
                logical_date = cct.get_last_trade_date()

        target_date = logical_date

        # # ✅ 简化 today 判断（避免重复调用）
        is_today = (target_date == today_str)
        
        # # 放宽 '今日' 的判定，只要是要找当天/最近交易日皆视为 today
        # is_today = (target_date == today_str or target_date == cct.get_last_trade_date())
        
        # [NEW] 采用多线程安全的类级全局缓存封装访问
        cache_key = f"{target_date}_{self.resample}"
        if not force:
            cached_df = self.get_candidates_cache(cache_key)
            if cached_df is not None:
                return cached_df

        # 1. 尝试从数据库加载 (SQLite)
        if not force and self.db_logger:
            try:
                df_history = self.db_logger.get_selections_df(date=target_date, resample=self.resample)
                
                # 如果返回的是 list (pandas import fail)，转 df
                if isinstance(df_history, list):
                    df_history = pd.DataFrame(df_history)

                if not df_history.empty:
                    self.logger.info(f"加载历史选股记录 (DB [{self.resample}]), 日期: {target_date}, 数量: {len(df_history)} 条")
                    if 'code' in df_history.columns:
                        df_history['code'] = df_history['code'].apply(lambda x: str(x).zfill(6))
                    
                    # 🚀 [加固] 无论今日还是历史模式，对 category (板块概念) 进行健壮的题材重构与全覆盖更新补齐
                    if self.df_all_realtime is not None and not self.df_all_realtime.empty:
                        if 'category' not in df_history.columns:
                            df_history['category'] = ''
                        
                        rt_all = self.df_all_realtime
                        if 'category' in rt_all.columns:
                            # 构建一个 code -> category 的快速映射字典
                            if rt_all.index.name == 'code' or 'code' in rt_all.index.names:
                                code_to_cat = rt_all['category'].fillna('').astype(str).to_dict()
                            elif 'code' in rt_all.columns:
                                code_to_cat = dict(zip(rt_all['code'].apply(lambda x: str(x).zfill(6)), rt_all['category'].fillna('').astype(str)))
                            else:
                                code_to_cat = {str(k).zfill(6): str(v) for k, v in rt_all['category'].fillna('').to_dict().items()}
                            
                            # 无论原本是否有截断或脏数据，只要字典里有，就直接用实时最新最全题材覆盖
                            mapped_cats = df_history['code'].map(code_to_cat)
                            mapped_cats = mapped_cats.dropna()
                            mapped_cats = mapped_cats[~mapped_cats.isin(['', '0', 'nan', 'NaN'])]
                            if not mapped_cats.empty:
                                df_history.loc[mapped_cats.index, 'category'] = mapped_cats
                    
                    self.set_candidates_cache(cache_key, df_history.copy())
                    return df_history
            except Exception as e:
                self.logger.error(f"读取历史数据失败: {e}")

        # 2. 如果不是今天，且数据库没数据，不运行实时策略（因为实时策略用的是当前价格）
        if not is_today:
            self.logger.warning(f"指定日期 {target_date} 无历史记录，且非今日，跳过实时策略计算。")
            return pd.DataFrame()

        # 3. 运行今日实时策略逻辑
        self.logger.info(f"正在运行实时选股策略 (日期: {today_str} 模拟is_today {is_today}, 周期: {self.resample})")
        df = self.load_data()
        df = self.calculate_indicators(df)
        df_res = self.filter_strong_stocks(df, today=today_str)
        
        self.set_candidates_cache(cache_key, df_res.copy() if not df_res.empty else df_res)
        return df_res

if __name__ == '__main__':
    # 测试运行
    # 可以传入 df 进行测试: selector = StockSelector(df=some_df)
    selector = StockSelector()
    candidates = selector.get_candidate_codes()
    print(f"Candidates: {candidates[:10]} ... Total: {len(candidates)}")

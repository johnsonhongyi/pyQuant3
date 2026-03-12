# encoding: utf-8
import pandas as pd
import numpy as np
import os
import sys
import datetime
import logging
import sqlite3
import re
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory
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

    # def __init__(self, log_path="selection_log.csv", df: Optional[pd.DataFrame] = None):
    def __init__(self, df: Optional[pd.DataFrame] = None, resample: str = 'd'):
        self.data_path = r'g:\top_all.h5'
        if not os.path.exists(self.data_path):
             # 尝试在当前工程目录下寻找
             local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'top_all.h5')
             if os.path.exists(local_path):
                 self.data_path = local_path
             else:
                 # 尝试在 CWD 寻找
                 cwd_path = os.path.join(os.getcwd(), 'top_all.h5')
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
        """加载数据：优先使用传入的实时数据，否则读取 top_all.h5"""
        if self.df_all_realtime is not None and not self.df_all_realtime.empty:
            self.logger.info(f"使用实时传入的数据进行筛选: {len(self.df_all_realtime)} 条")
            # 这里的 df_all 已经是 DataFrame 了，直接返回（或者 copy 以防修改原数据）
            return self.df_all_realtime.copy()

        try:
            if not os.path.exists(self.data_path):
                self.logger.error(f"数据文件不存在: {self.data_path}")
                return pd.DataFrame()
            
            # 读取 HDF5
            df = pd.read_hdf(self.data_path, 'top_all')
            self.logger.info(f"成功加载数据: {len(df)} 条")
            return df
        except Exception as e:
            self.logger.error(f"加载数据失败: {e}")
            return pd.DataFrame()

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
            
        # [FIX] 兼容实时数据的列名 (实时数据常使用 'trade' 表示现价)
        if 'close' not in df.columns and 'trade' in df.columns:
            df['close'] = df['trade']

        # 调用 data_utils 中的标准计算链 (包含量能扩缩逻辑)
        # resample 使用实例化时传入的参数
        try:
            df = data_utils.calc_indicators(df, self.logger, resample=self.resample)
        except Exception as e:
            self.logger.warning(f"data_utils.calc_indicators skipped: {e}")
        
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

    def filter_strong_stocks(self, df: pd.DataFrame, today: Optional[str] = None) -> pd.DataFrame:
        """执行优化后的筛选逻辑"""
        resample = self.resample # 使用当前实例的周期标识
        if df.empty:
            return df

        if today is None:
            today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 1. 基础过滤 (非停牌，成交额需大于 1.5亿 提高流动性门槛，确保可操作性)
        mask = pd.Series(True, index=df.index)
        if 'volume' in df.columns:
            mask &= (df['volume'] > 0)
        if 'amount' in df.columns:
            # 提高门槛：1.5亿以上，排除流流动性差的僵尸股
            mask &= (df['amount'] >= 150000000) 
            
        df_active = df[mask].copy()
        if df_active.empty:
            self.logger.info("无满足高流动性要求的股票 (Threshold: 1.5亿)")
            return pd.DataFrame()
        
        # 获取历史选股频次
        hist_counts = self.get_historical_selected_codes(days=5)

        # --- Pre-calculate Market Hot Concepts ---
        concept_dict = {}
        for _, row in df_active.iterrows():
            raw_c = row.get('category', row.get('sector', '')) # 兼容 scraper 的 sector 字段
            if pd.isna(raw_c) or str(raw_c).lower() == 'nan': continue
            cats = [c.strip() for c in str(raw_c).split(';') if c.strip() and c.strip() != '0']
            if not cats and isinstance(raw_c, str):
                # 兼容逗号或空格分隔
                cats = [c.strip() for c in re.split('[;, ]', raw_c) if c.strip() and c.strip() != '0']
            
            pct = float(row.get('percent', row.get('change_pct', 0))) # 兼容 scraper 的 change_pct
            for c in cats:
                concept_dict.setdefault(c, []).append(pct)
        
        concept_scores = []
        for c, pcts in concept_dict.items():
            if len(pcts) >= 3: 
                avg = sum(pcts) / len(pcts)
                concept_scores.append((c, avg))
        
        concept_scores.sort(key=lambda x: x[1], reverse=True)
        top_hot_names = [x[0] for x in concept_scores[:5]]
        self.logger.info(f"Top 5 Concepts: {top_hot_names}")
        self._last_hotspots = concept_scores # 缓存供外部查询
        
        # --- [NEW] Identify Sector Leaders (Top 5 per Hot Theme) ---
        protected_leaders = set()
        for c_name in top_hot_names:
            # 在当前活跃股中找属于该题材的
            sector_stocks = []
            for code, row in df_active.iterrows():
                raw_c = row.get('category', row.get('sector', ''))
                if pd.notna(raw_c) and c_name in str(raw_c):
                    sector_stocks.append({
                        'code': str(code).zfill(6),
                        'percent': float(row.get('percent', 0)),
                        'amount': float(row.get('amount', 0))
                    })
            # 按涨幅和成交额排序，取前 5 名
            sector_stocks.sort(key=lambda x: (x['percent'], x['amount']), reverse=True)
            for s in sector_stocks[:5]:
                protected_leaders.add(s['code'])
        
        self.logger.info(f"Protected Sector Leaders: {len(protected_leaders)} stocks from Top 5 Themes")

        selected_records = []

        for code, row in df_active.iterrows():
            data = row.to_dict()
            code_str = str(code).zfill(6)
            data['code'] = code_str
            
            reason = []
            score = 0
            
            # --- 预设默认值避免 UnboundError ---
            ma5 = ma10 = ma20 = 0.0
            price = 0.0
            amount = 0.0
            ratio = 0.0
            is_pullback = False

            # A. 趋势判断
            try:
                ma5 = float(data.get('ma5d', 0))
                ma10 = float(data.get('ma10d', 0))
                ma20 = float(data.get('ma20d', 0)) 
                price = float(data.get('trade', data.get('close', 0.0))) 
                amount = float(data.get('amount', 0))
                
                # 1. 均线状态：三线顺排是强势基础
                if ma5 > 0 and ma10 > 0 and ma20 > 0:
                    if ma5 > ma10 > ma20:
                        score += 15
                        reason.append("三线多排")
                    elif ma5 > ma10:
                        score += 5
                        reason.append("均线多排")

                # 2. 突破历史高点判断
                upper1d = float(data.get('upper1', 0))
                if upper1d > 0 and price > upper1d:
                    ratio = float(data.get('ratio', 1.0))
                    if ratio > 1.5: # 适度放量突破
                        score += 25
                        reason.append("放量突破")
                    else:
                        score += 10
                        reason.append("尝试突破")

                # 3. 动能：连涨逻辑
                limit_days = getattr(cct, 'compute_lastdays', 5)
                consecutive_rise = 0
                lastp1d = float(data.get('lastp1d', 0))
                if lastp1d > 0 and price > lastp1d:
                    consecutive_rise += 1
                    for d in range(1, limit_days):
                        curr_p = float(data.get(f'lastp{d}d', 0))
                        prev_p = float(data.get(f'lastp{d+1}d', 0))
                        if prev_p > 0 and curr_p > prev_p:
                            consecutive_rise += 1
                        else:
                            break
                
                if consecutive_rise >= 3:
                    score += consecutive_rise * 6 # 提升权重 from 5 to 6
                    reason.append(f"{consecutive_rise}连阳")
                    if consecutive_rise >= 5:
                        score += 15 # 大主升波 bonus
                        reason.append("主升波段")
                
                # 4. 回调买点 (缩量企稳)
                is_pullback = False
                if ma5 > 0 and 0 < (price - ma5) / ma5 < 0.015: # 稍微放宽回调幅度
                    ratio = float(data.get('ratio', 1.0))
                    if ratio < 1.1 and price >= ma5: # 缩量且守住 MA5
                        score += 20
                        reason.append("缩量企稳")
                        is_pullback = True
                
                # 5. 资金强度 (成交额权重)
                amount = float(data.get('amount', 0))
                if amount > 500000000: # 5亿以上大资金
                    score += 20 # 提升权重 from 15 to 20
                    reason.append("主力活跃")
                elif amount > 200000000:
                    score += 10 # from 5 to 10

            except Exception as e:
                self.logger.error(f"Error filtering {code}: {e}")

            # B. 今日涨跌与量能精细判断
            pct = float(data.get('percent', 0))
            ratio = float(data.get('ratio', 0))
            
            # 优选 3% - 8% 的稳健涨幅，避免已涨停难以介入，也避免冲高回落
            if 3.0 <= pct <= 8.5:
                score += 15
                if ratio > 1.2: score += 10 # 量价齐升
            elif pct > 9.5:
                score += 15 # 冲击涨停权重提升
                reason.append("冲击涨停")
            elif -2.0 <= pct < 2.0 and is_pullback:
                score += 15 # 提升权重 from 10 to 15
            
            # C. 放量情况 (量比)
            if 1.5 < ratio < 4.0: # 健康放量
                score += 15
                reason.append("健康放量")
            elif ratio >= 4.0: # 巨量
                score += 10
                reason.append("巨量成交")
            
            # D. 板块效应
            stock_cats = []
            raw_c_val = data.get('category', '')
            if pd.notna(raw_c_val) and str(raw_c_val).lower() != 'nan':
                 stock_cats = [c.strip() for c in str(raw_c_val).split(';') if c.strip()]
            
            strong_sector_hit = [c for c in stock_cats if c in top_hot_names]
            if strong_sector_hit:
                score += 15 # 提升权重 from 10 to 15
                reason.append(f"热点:{strong_sector_hit[0]}")
                # [针对性保护] 如果是核心热点前 5 名龙头
                if code_str in protected_leaders:
                    score += 50
                    reason.append("板块龙头")

            # F. [New] 特定模式筛选 (MA60 反转 / 布林上轨攻击)
            try:
                # 1. MA60 反转选股
                ma60 = float(data.get('ma60d', 0))
                if ma60 > 0:
                    # 最近 1-2 日有探底 (破MA60)
                    last_low1d = float(data.get('lastl1d', 0)) # 假设有这些字段
                    # 或者从 ma60 乖离判断整理
                    ma60_bias = (price - ma60) / ma60
                    if -0.01 < ma60_bias < 0.04 and pct > 2.0:
                        # 穿过前两日最高
                        max_h_2d = max(float(data.get('lastp1d', 0)), float(data.get('lastp2d', 0)))
                        if price > max_h_2d and price > ma60:
                             score += 30
                             reason.append("MA60反转启动")
                
                # 2. 布林上轨攻击 (Upper Attack)
                upper1d = float(data.get('upper1', 0))
                if upper1d > 0:
                    if price > upper1d:
                        score += 20
                        reason.append("站稳上轨")
                        # 检查是否连续攻击 (昨收也在上轨附近或之上)
                        last_close1d = float(data.get('lastp1d', 0))
                        upper2d = float(data.get('upper2', 0))
                        if last_close1d > upper2d * 0.99:
                             score += 15
                             reason.append("连续上轨攻击")

                # 3. [User NEW] 触底反弹 + 新高连阳 (Safety Priority)
                # 检查是否从低位起涨：price 站上 MA10/MA20，且连阳
                if consecutive_rise >= 2 and ma20 > 0:
                    dist_to_ma20 = (price - ma20) / ma20
                    if 0 < dist_to_ma20 < 0.05: # 距离 20 日线不远，属于反弹初中期
                        score += 35
                        reason.append("触底反弹启动")
                        if consecutive_rise >= 3:
                            score += 20
                            reason.append("新高连阳(安全)")

                # 4. [Negative Scoring] 冲高回落保护
                high_p = float(data.get('high', 0))
                if high_p > price:
                    upper_shadow = (high_p - price) / (high_p - lastp1d + 0.01) if lastp1d > 0 else 0
                    if upper_shadow > 0.4: # 上影线过长
                        score -= 30
                        reason.append("冲高回落(结构转弱)")
            except Exception:
                pass

            # E. 历史对比：标签化
            hist_cnt = hist_counts.get(code_str, 0)
            status_tag = ""
            if hist_cnt >= 3:
                score += 20
                reason.append("多日持续强势")
                status_tag = "持续型"
            elif hist_cnt == 0 and score > 40:
                score += 10
                reason.append("新晋热股")
                status_tag = "新晋型"
            elif hist_cnt > 0:
                score += 5
                reason.append("反复走强")
                status_tag = "反复型"

            # 最终筛选阈值大幅提高 (score >= 80) 以确保结果精简且高质
            if score >= 80 and reason: 
                reason = list(dict.fromkeys(reason)
)
                
                # 自动生成建议
                if is_pullback and pct < 2:
                    reason.append("建议:低吸关注")
                elif "放量突破" in reason and pct > 4:
                    reason.append("建议:右侧追入")
                elif hist_cnt >= 3 and pct > 0:
                    reason.append("建议:强者恒强")
                
                # 拼接理由
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
                    'change_pct': pct, # 兼容别名
                    'zhuli_rank': data.get('zhuli_rank', '-'), # 增加主力排名
                    'ratio': ratio,
                    'volume': float(data.get('volume', 0)),
                    'amount': amount,
                    'reason': final_reason,
                    'status': status_tag,
                    'ma5': ma5,
                    'ma10': ma10,
                    'open': float(data.get('open', 0)),
                    'category': "|".join(stock_cats[:3]),
                    'resample': resample
                }
                selected_records.append(record)

        df_selected = pd.DataFrame(selected_records)
        if not df_selected.empty:
            # 理由去重
            df_selected.sort_values(by=['score', 'amount'], ascending=False, inplace=True)
            
            # [CRITICAL] 仅保留前 200 名优质标的
            df_selected = df_selected.head(200)
            
            self.logger.info(f"筛选完成，命中 {len(df_selected)} 只股票 (Threshold >= 80, Top 200 Limiter)")
            
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
        :param force: 是否强制重新运行策略。如果为 False，则优先从数据库加载今日已存数据。
        :param logical_date: 逻辑日期，格式 'YYYY-MM-DD'。如果提供，则使用此日期进行数据查询；否则使用系统当前日期。
        :param resample: 如果提供，则覆盖实例的周期标识。
        """
        if resample:
            self.resample = resample
        
        today = logical_date if logical_date else datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 非强制模式下，先检查今日是否有存量数据 (From SQLite)
        if not force and self.db_logger:
            try:
                # 注意：这里可能需要更新 get_selections_df 以支持 resample
                df_today = self.db_logger.get_selections_df(date=today, resample=self.resample)
                
                # 如果返回的是 list (pandas import fail)，转 df
                if isinstance(df_today, list):
                    df_today = pd.DataFrame(df_today)

                if not df_today.empty:
                    self.logger.info(f"检测到今日已运行过策略 (DB [{self.resample}]), 加载存量数据: {len(df_today)} 条")
                    if 'code' in df_today.columns:
                        df_today['code'] = df_today['code'].apply(lambda x: str(x).zfill(6))
                    return df_today
            except Exception as e:
                self.logger.error(f"读取今日历史数据失败: {e}, 将重新运行策略")

        # 运行策略逻辑
        df = self.load_data()
        df = self.calculate_indicators(df)
        df_res = self.filter_strong_stocks(df, today=today)
        return df_res

if __name__ == '__main__':
    # 测试运行
    # 可以传入 df 进行测试: selector = StockSelector(df=some_df)
    selector = StockSelector()
    candidates = selector.get_candidate_codes()
    print(f"Candidates: {candidates[:10]} ... Total: {len(candidates)}")

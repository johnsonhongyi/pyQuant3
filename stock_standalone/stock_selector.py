# encoding: utf-8
import pandas as pd
import numpy as np
import os
import sys
import datetime
import logging
import sqlite3
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
    def __init__(self, df: Optional[pd.DataFrame] = None):
        self.data_path = r'g:\top_all.h5'
        # self.log_path = log_path # Deprecated: moved to SQLite
        self.df_all_realtime = df  # 实时数据引用
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

        # 调用 data_utils 中的标准计算链 (包含量能扩缩逻辑)
        # resample 默认为 'd'
        df = data_utils.calc_indicators(df, self.logger, resample='d')
        
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
        if df.empty:
            return df

        if today is None:
            today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 1. 基础过滤 (非停牌，成交额需大于 8000万 提高流动性门槛)
        df_active = df[(df['volume'] > 0) & (df['amount'] > 80000000)].copy()
        if df_active.empty:
            self.logger.info("无满足基础流动性要求的股票 (amount > 80M)")
            return pd.DataFrame()
        
        # 获取历史选股频次
        hist_counts = self.get_historical_selected_codes(days=5)

        # --- Pre-calculate Market Hot Concepts ---
        concept_dict = {}
        for _, row in df_active.iterrows():
            raw_c = row.get('category', '')
            if pd.isna(raw_c) or str(raw_c).lower() == 'nan': continue
            cats = [c.strip() for c in str(raw_c).split(';') if c.strip() and c.strip() != '0']
            pct = float(row.get('percent', 0))
            for c in cats:
                concept_dict.setdefault(c, []).append(pct)
        
        concept_scores = []
        for c, pcts in concept_dict.items():
            if len(pcts) >= 3: 
                avg = sum(pcts) / len(pcts)
                concept_scores.append((c, avg))
        
        concept_scores.sort(key=lambda x: x[1], reverse=True)
        top_concepts = set([x[0] for x in concept_scores[:15]]) # 缩小到 Top 15
        self.logger.info(f"Top 5 Concepts: {[x[0] for x in concept_scores[:5]]}")

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
                upper1d = float(data.get('upper1d', 0))
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
                    score += consecutive_rise * 5 
                    reason.append(f"{consecutive_rise}连涨")
                
                # 4. 回调买点 (缩量企稳)
                is_pullback = False
                if ma5 > 0 and 0 < (price - ma5) / ma5 < 0.012: 
                    ratio = float(data.get('ratio', 1.0))
                    if ratio < 1.0 and price >= ma5: # 缩量且守住 MA5
                        score += 20
                        reason.append("缩量企稳")
                        is_pullback = True
                
                # 5. 资金强度 (成交额权重)
                amount = float(data.get('amount', 0))
                if amount > 500000000: # 5亿以上大资金
                    score += 15
                    reason.append("主力活跃")
                elif amount > 200000000:
                    score += 5

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
                score += 10
                reason.append("冲击涨停")
            elif -2.0 <= pct < 2.0 and is_pullback:
                score += 10 # 强势回调震荡
            
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
            
            strong_sector_hit = [c for c in stock_cats if c in top_concepts]
            if strong_sector_hit:
                score += 10 
                reason.append(f"热点:{strong_sector_hit[0]}")

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

            # 最终筛选阈值提高 (score >= 45)
            if score >= 45 and reason: 
                reason = list(dict.fromkeys(reason))
                
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
                    'ratio': ratio,
                    'volume': float(data.get('volume', 0)),
                    'amount': amount,
                    'reason': final_reason,
                    'status': status_tag,
                    'ma5': ma5,
                    'ma10': ma10,
                    'open': float(data.get('open', 0)),
                    'category': "|".join(stock_cats[:3])
                }
                selected_records.append(record)

        df_selected = pd.DataFrame(selected_records)
        if not df_selected.empty:
            # 理由去重
            df_selected.sort_values(by=['score', 'amount'], ascending=False, inplace=True)
            self.logger.info(f"筛选完成，命中 {len(df_selected)} 只股票 (阈值>=45)")
            
            # 保存日志
            self.save_selection_log(df_selected)
            
        return df_selected

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

    def get_candidates_df(self, force: bool = False, logical_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取筛选结果。
        :param force: 是否强制重新运行策略。如果为 False，则优先从数据库加载今日已存数据。
        :param logical_date: 逻辑日期，格式 'YYYY-MM-DD'。如果提供，则使用此日期进行数据查询；否则使用系统当前日期。
        """
        today = logical_date if logical_date else datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 非强制模式下，先检查今日是否有存量数据 (From SQLite)
        if not force and self.db_logger:
            try:
                df_today = self.db_logger.get_selections_df(date=today)
                
                # 如果返回的是 list (pandas import fail)，转 df
                if isinstance(df_today, list):
                    df_today = pd.DataFrame(df_today)

                if not df_today.empty:
                    self.logger.info(f"检测到今日已运行过策略 (DB)，加载存量数据: {len(df_today)} 条")
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

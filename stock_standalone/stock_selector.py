# encoding: utf-8
import pandas as pd
import numpy as np
import os
import sys
import datetime
import logging
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

class StockSelector:
    """
    强势股筛选器
    
    功能：
    1. 读取 g:\\top_all.h5 数据
    2. 基于技术指标筛选强势股 (趋势、量能、结构)
    3. 生成筛选日志，用于后续分析优化
    """
    def __init__(self, log_path="selection_log.csv"):
        self.data_path = r'g:\top_all.h5'
        self.log_path = log_path
        self._setup_logger()
        # 初始化决策引擎（可选，用于辅助判断）
        self.decision_engine = IntradayDecisionEngine() if IntradayDecisionEngine else None

    def _setup_logger(self):
        self.logger = LoggerFactory.getLogger('StockSelector')
        # self.logger.setLevel(logging.INFO)

    def load_data(self) -> pd.DataFrame:
        """加载 top_all.h5 数据"""
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
        """补充必要的计算指标 (如果 top_all 中缺少)"""
        # 假设 df 包含: close, open, high, low, volume
        # 这里进行简单的向量化计算，或者依赖 provided columns
        
        # 确保数值列为 float
        cols = ['close', 'open', 'high', 'low', 'volume', 'amount']
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 示例：计算简单的均线（如果数据是 Snapshot day data，通常需要历史数据才能算 MA）
        # 注意：top_all.h5 通常是一张快照表 (One row per stock)。
        # 如果没有历史 ma5/ma10/ma20 列，我们只能基于当前状态做筛选，或者假设 top_all 已经包含了这些指标。
        # 常见的 pyQuant/JohnsonUtil 架构中，top_all 可能已经包含了 ma5d, ma10d 等。
        
        return df

    def filter_strong_stocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """执行筛选逻辑"""
        if df.empty:
            return df

        # 1. 基础过滤 (非停牌，非极小盘等)
        # 假设 exclusion 逻辑 (比如 percent = 0 可能是停牌)
        df_active = df[df['volume'] > 0].copy()
        
        # --- Pre-calculate Market Hot Concepts ---
        concept_dict = {}
        for _, row in df_active.iterrows():
            raw_c = row.get('category', '')
            if pd.isna(raw_c) or str(raw_c).lower() == 'nan': continue
            cats = [c.strip() for c in str(raw_c).split(';') if c.strip() and c.strip() != '0']
            pct = float(row.get('percent', 0))
            for c in cats:
                concept_dict.setdefault(c, []).append(pct)
        
        # Calculate avg percent and filter valid concepts (e.g. at least 3 stocks)
        concept_scores = []
        for c, pcts in concept_dict.items():
            if len(pcts) >= 3: # Min 3 stocks in concept
                avg = sum(pcts) / len(pcts)
                # Count positive ratio or just use avg
                concept_scores.append((c, avg))
        
        # Get Top 20 concepts
        concept_scores.sort(key=lambda x: x[1], reverse=True)
        top_concepts = set([x[0] for x in concept_scores[:20]])
        self.logger.info(f"Top 5 Concepts: {[x[0] for x in concept_scores[:5]]}")

        selected_records = []
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        for code, row in df_active.iterrows():
            # 将 Series 转为 dict 方便处理
            data = row.to_dict()
            data['code'] = code
            
            # --- 筛选核心逻辑 ---
            # 利用 data_utils.py 生成的预处理字段: upper1d, lastp1d, lastl1d 等
            
            reason = []
            score = 0
            
            # A. 趋势判断
            try:
                # 动态获取最近 N 天的 upper 和 close 与当前价格比较
                # cct.compute_lastdays 是预定义的天数，例如 5
                
                ma5 = float(data.get('ma5d', 0))
                ma10 = float(data.get('ma10d', 0))
                ma20 = float(data.get('ma20d', 0)) 
                price = float(data.get('trade', data.get('close', 0.0))) 
                
                # 1. 多头排列
                if ma5 > 0 and ma10 > 0:
                    if price > ma5 and ma5 > ma10:
                        trend_score = 10
                        if ma20 > 0 and ma10 > ma20:
                            trend_score += 10 # 完美多头
                            
                        # 检查是否突破上轨 (upper1d)
                        upper1d = float(data.get('upper1d', 0))
                        if upper1d > 0 and price > upper1d:
                            trend_score += 10
                            reason.append("突破上轨")
                            
                        score += trend_score
                        if trend_score >= 10:
                            reason.append("多头趋势")

                # 2. 动能 (基于 data_utils 的强动能逻辑)
                # 动态检查最近 cct.compute_lastdays 天的趋势
                # 要求: 每天的收盘价和低点都抬高 (或宽松一点)
                
                limit_days = getattr(cct, 'compute_lastdays', 5)
                consecutive_rise = 0
                
                # Check current day vs 1d
                lastp1d = float(data.get('lastp1d', 0))
                lastl1d = float(data.get('lastl1d', 0))
                
                # 如果今日比昨日强 (现价>昨收 且 现价>昨上轨?) -> 简单比较 Close 和 Low
                if lastp1d > 0 and price > lastp1d and (lastl1d == 0 or float(data.get('low', 0)) > lastl1d):
                    consecutive_rise += 1
                    
                    # Check history backwards
                    for d in range(1, limit_days):
                        # Compare d with d+1 (e.g., 1d vs 2d)
                        curr_p = float(data.get(f'lastp{d}d', 0))
                        prev_p = float(data.get(f'lastp{d+1}d', 0))
                        curr_l = float(data.get(f'lastl{d}d', 0))
                        prev_l = float(data.get(f'lastl{d+1}d', 0))
                        
                        if prev_p > 0 and curr_p > prev_p and (prev_l == 0 or curr_l > prev_l):
                            consecutive_rise += 1
                        else:
                            break
                
                
                if consecutive_rise >= 2:
                    score += consecutive_rise * 5 # 连涨天数越多分越高
                    reason.append(f"{consecutive_rise}连涨")

            except Exception as e:
                self.logger.error(f"Error filtering {code}: {e}")

            # B. 形态判断 (N日新高 / 突破)
            pct = float(data.get('percent', 0))
            if pct > 3.0:
                score += 10
            if pct > 9.0: 
                score += 5
                reason.append("涨停冲击")
            
            # C. 量能判断
            ratio = float(data.get('ratio', 0))
            if 3 < ratio < 15:
                score += 10
            elif ratio > 15:
                score += 5
                reason.append("放量")
            
            # D. 板块效应 (Concept/Category Analysis)
            # Check if stock belongs to top performing sectors
            stock_cats = []
            raw_c_val = data.get('category', '')
            if pd.notna(raw_c_val) and str(raw_c_val).lower() != 'nan':
                 stock_cats = [c.strip() for c in str(raw_c_val).split(';') if c.strip()]
            
            strong_sector_hit = [c for c in stock_cats if c in top_concepts]
            if strong_sector_hit:
                score += 10 * len(strong_sector_hit)
                # reason.append(f"板块:{','.join(strong_sector_hit)}")
                # 仅添加前3个强板块
                for hit in strong_sector_hit[:3]:
                    reason.append(f"强板块:{hit}")

            # D. 利用 Decision Engine (如果可用)
            if self.decision_engine:
                 pass

            # 阈值筛选
            if score >= 25: # 调整阈值
                record = {
                    'date': today,
                    'code': code,
                    'name': data.get('name', ''),
                    'score': score,
                    'price': price,
                    'percent': pct,
                    'volume': float(data.get('volume', 0)),
                    'reason': "|".join(reason),
                    'ma5': ma5,
                    'ma10': ma10,
                    'category': str(data.get('category', '')) if pd.notna(data.get('category')) else ''
                }
                selected_records.append(record)

        # 转换为 DataFrame
        df_selected = pd.DataFrame(selected_records)
        if not df_selected.empty:
            # 统计同类型理由的数量，便于优先级查找
            reason_counts = df_selected['reason'].value_counts().to_dict()
            df_selected['reason'] = df_selected['reason'].apply(lambda x: f"{x} [同类:{reason_counts.get(x, 0)}]")
            
            df_selected.sort_values(by='score', ascending=False, inplace=True)
            self.logger.info(f"筛选完成，命中 {len(df_selected)} 只股票")
            
            # 保存日志
            self.save_selection_log(df_selected)
            
        return df_selected

    def save_selection_log(self, df_selected: pd.DataFrame):
        """保存筛选结果到日志文件 (CSV / DB)"""
        # CSV append mode
        if os.path.exists(self.log_path):
            df_selected.to_csv(self.log_path, mode='a', header=False, index=False, encoding='utf-8')
        else:
            df_selected.to_csv(self.log_path, mode='w', header=True, index=False, encoding='utf-8')
        
        self.logger.info(f"筛选日志已更新: {self.log_path}")
        
    def get_candidate_codes(self) -> List[str]:
        """获取筛选出的代码列表，供 stock_live_strategy 调用"""
        df = self.get_candidates_df()
        if df.empty:
            return []
        return df['code'].tolist()

    def get_candidates_df(self) -> pd.DataFrame:
        """获取筛选结果完整 DataFrame"""
        df = self.load_data()
        df = self.calculate_indicators(df)
        df_res = self.filter_strong_stocks(df)
        return df_res

if __name__ == '__main__':
    # 测试运行
    selector = StockSelector()
    candidates = selector.get_candidate_codes()
    print(f"Candidates: {candidates[:10]} ... Total: {len(candidates)}")

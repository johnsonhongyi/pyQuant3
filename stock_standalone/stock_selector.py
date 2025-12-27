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
        self.logger = LoggerFactory.getLogger('StockSelector')
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

        # 1. 基础过滤 (非停牌，非极小盘，成交额需大于 5000万 确保流动性)
        df_active = df[(df['volume'] > 0) & (df['amount'] > 50000000)].copy()
        if df_active.empty:
            self.logger.info("无活跃且成交额达标的股票")
            return pd.DataFrame()
        
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
            code_str = str(code).zfill(6)
            data['code'] = code_str
            
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
                
                # 1. 均线状态与斜率
                if ma5 > 0 and ma10 > 0:
                    ma5_1d = float(data.get('ma5d', 0)) 
                    # 检查 MA5 是否向上偏转
                    if price > ma5 and ma5 > ma10:
                        score += 5
                        if ma5 > ma5_1d > 0:
                            score += 5
                            reason.append("趋势向上")
                        else:
                            reason.append("均线多排")
                        
                        if ma20 > 0 and ma10 > ma20:
                            score += 10
                            reason.append("中期强势")

                    # 2. 突破判断
                    upper1d = float(data.get('upper1d', 0))
                    if upper1d > 0 and price > upper1d:
                        ratio = float(data.get('ratio', 1.0))
                        if ratio > 1.2:
                            score += 20
                            reason.append("放量突破")
                        else:
                            score += 10
                            reason.append("缩量尝试突破")

                # 3. 动能：N连涨 + 价格结构
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
                
                # 4. 回调买点判断 (价格回调至 MA5/MA10 附近且量能萎缩)
                is_pullback = False
                if ma5 > 0 and 0 < (price - ma5) / ma5 < 0.015: 
                    ratio = float(data.get('ratio', 1.0))
                    if ratio < 0.9: # 明确缩量
                        score += 20
                        reason.append("缩量回踩")
                        is_pullback = True
                
                # 5. 极度活跃 (成交额 > 3亿)
                amount = float(data.get('amount', 0))
                if amount > 300000000:
                    score += 10
                    reason.append("资金活跃")

                # --- 动态生成操作建议 (Advice) ---
                advice = []
                if is_pullback:
                    advice.append("建议:回踩买入")
                elif "放量突破" in reason:
                    advice.append("建议:强势追涨")
                elif "缩量尝试突破" in reason:
                    advice.append("建议:观察量能配合")
                elif consecutive_rise >= 4:
                    advice.append("建议:高位减仓")
                elif "均线多排" in reason and len(reason) == 1:
                    # 仅有多头而无其他动能，降级处理
                    score -= 5
                
                if advice:
                    reason.extend(advice)

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
                reason.append(f"热点:{strong_sector_hit[0]}") # 仅显示最强一个增加辨识度

            # D. 利用 Decision Engine (如果可用)
            if self.decision_engine:
                 pass

            # 阈值筛选 (必须有明确理由且分值达标)
            if score >= 30 and reason: 
                # 理由去重并保持顺序
                reason = list(dict.fromkeys(reason))
                
                # 优化建议排序，确保“建议”在最后
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
                    'volume': float(data.get('volume', 0)),
                    'reason': final_reason,
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
            
            # 保存日志 (升级为 SQLite)
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

    def get_candidates_df(self, force=False) -> pd.DataFrame:
        """
        获取筛选结果。
        :param force: 是否强制重新运行策略。如果为 False，则优先从数据库加载今日已存数据。
        """
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
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
        df_res = self.filter_strong_stocks(df)
        return df_res

if __name__ == '__main__':
    # 测试运行
    # 可以传入 df 进行测试: selector = StockSelector(df=some_df)
    selector = StockSelector()
    candidates = selector.get_candidate_codes()
    print(f"Candidates: {candidates[:10]} ... Total: {len(candidates)}")

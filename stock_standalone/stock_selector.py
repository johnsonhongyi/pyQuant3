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
        curr_p = df['trade'] if 'trade' in df.columns else df['close']
        
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

    def filter_strong_stocks(self, df: pd.DataFrame, today: Optional[str] = None) -> pd.DataFrame:
        """执行优化后的筛选逻辑"""
        resample = self.resample # 使用当前实例的周期标识
        if df.empty:
            return df
            
        # 0. 预计算趋势质量指标 (分级基础)
        df = self._calc_trend_quality(df)

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
                # 题材龙头排序：优先使用 per1d 涨幅
                row_pct = float(row.get('per1d', row.get('percent', row.get('pct', 0))))
                if pd.notna(raw_c) and c_name in str(raw_c):
                    sector_stocks.append({
                        'code': str(code).zfill(6),
                        'percent': row_pct,
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
            
            # 兼容字段：优先使用 per1d (今日涨幅)
            price = float(data.get('trade', data.get('close', 0)))
            pct = float(data.get('per1d', data.get('percent', data.get('pct', 0))))
            lastp1d = float(data.get('lastp1d', 0))
            if pct == 0 and lastp1d > 0:
                pct = round((price - lastp1d) / lastp1d * 100, 2)
            data['percent'] = pct # 回填以供后续评估使用
            
            reason = []
            score = 0
            
            # --- 预设默认值避免 UnboundError ---
            ma5 = ma10 = ma20 = 0.0
            # price, pct, amount 已在上方提取并存入变量及 data['percent']
            ratio = float(data.get('ratio', 1.0))
            is_pullback = False

            # A. 趋势判断
            try:
                # price, pct, amount 已在上方提取
                
                # 1. 均线状态：三线顺排是强势基础
                if ma5 > 0 and ma10 > 0 and ma20 > 0:
                    if ma5 > ma10 > ma20:
                        score += 15
                        reason.append("三线多排")
                    elif ma5 > ma10:
                        score += 5
                        reason.append("均线多排")
                else:
                    if ma5 > ma10:
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
                
                # 3. 量能配合 (Volume Support) - 寻找持续性放量
                vma5 = float(data.get('vma5', 0))
                is_pulse_risk = False
                if amount > 0 and vma5 > 0:
                    vol_ratio = amount / vma5
                    if vol_ratio > 1.5 and vol_ratio < 6.0: # 适度放量
                        score += 30
                        reason.append("量能配合")
                    elif vol_ratio >= 6.0: # 极速放量 (需警惕脉冲诱多)
                        score -= 50 # 严厉惩罚脉冲诱多
                        is_pulse_risk = True
                        reason.append("放量过激(诱多风险)")
                
                # 3.A 偏离度检查 (Deviation Check) - 预防洗盘初期或过热
                is_overheated = False
                if ma5 > 0:
                    deviation = (price - ma5) / ma5
                    if deviation > 0.12: # 离 5 日线太远，容易洗盘
                        score -= 40
                        is_overheated = True
                        reason.append("乖离过大(洗盘风险)")
                
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

                # 4. [Structural Pattern] 大级别底部与回踩启动 (针对 600519 类型)
                # 引入衰减因子: 在启动前 1-2 天分数最高，随连阳天数增加而衰减
                # 这样可以精准捕捉 03-13 这种临界点
                decay = max(0.2, 1.0 - (consecutive_rise - 1) * 0.3) if consecutive_rise > 0 else 1.0
                
                # [NEW] 缩量横盘突破识别
                max5 = float(data.get('max5', 0))
                min5 = float(data.get('min5', 0))
                
                if max5 > 0 and min5 > 0:
                    consolidation_width = (max5 - min5) / min5
                    if code_str == '603817' or code_str == '300672': self.logger.info(f"DEBUG {code_str}: max5={max5}, min5={min5}, width={consolidation_width:.4f}, breakout={price > max5}")
                    
                    # 4.A 窄幅横盘突破 (短期动力)
                    if consolidation_width < 0.05 and price > max5 * 0.995:
                        score += 60 * decay
                        reason.append(f"横盘突破(时效:{consecutive_rise}d)")
                    
                    # 4.B 大级别平台突破 (周线/宏观动力)
                    # 检查是否突破了近 20 日甚至更长的高点 (基于 TDD 注入的 lasth1d..10d 及 max5)
                    # 如果当前价远超近两周高位，且属于启动前 3 日
                    if price > max5 * 1.02 and consecutive_rise <= 3:
                        score += 30
                        reason.append("大级别平台突破")

                # 利用 tdd 指标: hmax, max10, upper, lower
                hmax = float(data.get('hmax', 0))
                lower = float(data.get('lower', 0))
                # 如果股价在 ma60 之上，且距离 ma60 较近 (回踩)
                if ma60 > 0 and price > ma60 * 0.99 and price < ma60 * 1.05:
                    # 如果近期有过从 [lower] 附近的拉起，说明底部已构筑
                    if lower > 0 and price > lower * 1.05:
                        score += 40 * decay
                        reason.append("大级别底部构筑")
                        if 1 <= consecutive_rise <= 2: # 刚启动阶段
                            score += 20 * decay
                            reason.append("回踩确认启动")
                
                # 特征：中阳吞没 (突破近期 max10/hmax 阻力)
                max10 = float(data.get('max10', 0))
                if max10 > 0 and price > max10 * 1005 and pct > 2.0:
                    score += 25 * decay
                    reason.append("突破近期平台")
                
                # [NEW] 开盘结构与临界突破 (盘中发掘)
                high4 = float(data.get('high4', 0))
                if high4 > 0 and price > high4:
                    score += 20 * decay
                    reason.append("突破4日高点")
                
                # 低开高走 / 高开高走 (03-13 模型)
                opened = float(data.get('open', 0))
                if opened > 0 and lastp1d > 0:
                    # 低开反包 (03-13 是低开高走反包昨高)
                    if opened < lastp1d and price > lastp1d * 1.01:
                        score += 30 * decay
                        reason.append("低开反包(强)")
                    # 高开高走 (加速)
                    elif opened > lastp1d * 1.005 and price > opened:
                        score += 20 * decay
                        reason.append("高开加速")

                # [NEW] 反包新高结构
                last_high1d = float(data.get('lasth1d', 0))
                last_pct1d = float(data.get('per1d', 0))
                if price > last_high1d and last_pct1d < 0.5: # 昨低迷今反转
                    score += 25 * decay
                    reason.append("反包启动")

                # 5. [Negative Scoring] 冲高回落保护
                high_p = float(data.get('high', 0))
                if high_p > price:
                    upper_shadow = (high_p - price) / (high_p - lastp1d + 0.01) if lastp1d > 0 else 0
                    if upper_shadow > 0.4: # 上影线过长
                        score -= 30
                        reason.append("冲高回落(结构转弱)")
            except Exception:
                pass

            # E. 走势分级与状态标签 (重心调整)
            hist_cnt = hist_counts.get(code_str, 0)
            tqi = data.get('tqi_score', 0)
            up_r = data.get('up_ratio', 0)
            stage = int(data.get('cycle_stage', 2))
            
            status_tag = ""
            grade = "C"
            
            # --- 走势分级逻辑 2.0 (增强双轨直通: 主升爆发 & 触底反弹) ---
            is_ma60_resistance = False
            is_ma60_support = False
            is_expansion_breakout = any("突破" in r or "启动" in r for r in reason) # 识别主升爆发标志
            
            ma60 = float(data.get('ma60d', 0))
            if ma60 > 0:
                ma10 = float(data.get('ma10', 0))
                # 场景 A: 下降通道反弹压力 
                if ma10 > 0 and ma10 < ma60 * 0.98 and price < ma60 * 1.015:
                    is_ma60_resistance = True
                # 场景 B: 趋势扭转后的回踩 (Rebound 型)
                elif ma10 > 0 and ma10 > ma60 * 0.99 and price > ma60 * 0.98 and price < ma60 * 1.05:
                    is_ma60_support = True

            # 核心过滤器: 
            # 1. 顺势加速类: TQI 极高
            # 2. 抄底反转类: MA60 支撑且分值达 80 
            # 3. 主升爆点类: 高分触发 (score >= 80) 或 横盘突破关键词直通 (豁免压力位)
            # 修正: 如果是主升突破，即使 ma10 < ma60 也不拦截 (因为是突破中)
            if ((((tqi >= 60 and up_r >= 0.7 and stage in (2, 3)) or (up_r >= 0.8 and stage == 2)) or 
                 (score >= 80 and not is_ma60_resistance) or 
                 (score >= 50 and is_expansion_breakout)) and (not is_ma60_resistance or is_expansion_breakout)):
                
                # 分级调优: 满足形态分 130 或 TQI 极致则为 S
                
                # 分级调优: 满足形态分 130 或 TQI 极致则为 S
                # 封顶逻辑: 过热或诱多风险下，等级封顶为 B
                if score >= 130 or (tqi >= 80 and up_r >= 0.85):
                    grade = "S"
                    status_tag = "极强启动" if is_ma60_support else "主升加速"
                elif score >= 85 or (tqi >= 60 and up_r >= 0.7):
                    grade = "A"
                    status_tag = "上升中继" if not is_ma60_support else "趋势回归(A)"
                elif score >= 50 or tqi >= 45:
                    grade = "B"
                    status_tag = "低位转强"
                else:
                    grade = "C"
                    status_tag = "震荡蓄势"
                
                score += 30 # S/A/B 通用奖分
                reason.append(f"{grade}级:趋势确认")
            # 回踩支撑处理 (正向激励)
            elif is_ma60_support:
                grade = "A" if (tqi >= 40 or up_r >= 0.6) else "B"
                status_tag = "趋势回踩确认"
                score += 35
                reason.append("分级调整:MA60支撑回踩")
            # 压力位处理 (B级降级)
            elif is_ma60_resistance and (tqi >= 45 or up_r >= 0.6):
                grade = "B" 
                status_tag = "反弹压力位"
                score -= 30
                reason.append("分级降级:MA60下降压力")
            # B级: 模式启动
            elif score > 60 or stage == 1:
                grade = "B"
                status_tag = "启动/蓄势"
                score += 10
            
            # [特供逻辑] 高位中继/接力 (空中接力)
            # 特征: 虽今日涨幅不大，但处于 S/A 级且缩量不破 MA5/10
            if grade in ("S", "A") and is_pullback:
                status_tag = "空中接力"
                score += 20
                reason.append("强势股高位接力")
                
            if hist_cnt >= 3:
                score += 10
                reason.append("持续上榜")
            elif hist_cnt == 0 and grade == "S":
                reason.append("主升初显")

            # 最终筛选阈值大幅提高 (score >= 80) 以确保结果精简且高质
            if score >= 80 and reason: 
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
                    'change_pct': pct, # 兼容别名
                    'zhuli_rank': data.get('zhuli_rank', '-'), # 增加主力排名
                    'ratio': ratio,
                    'volume': float(data.get('volume', 0)),
                    'amount': amount,
                    'reason': final_reason,
                    'status': status_tag,
                    'grade': grade, # 新增分级
                    'tqi': tqi,     # 新增质量分
                    'ma5': ma5,
                    'ma10': ma10,
                    'open': float(data.get('open', 0)),
                    'category': "|".join(stock_cats[:3]),
                    'stage': stage, 
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
